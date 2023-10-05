#
# Copyright 2017 Pixar
#
# Licensed under the Apache License, Version 2.0 (the "Apache License")
# with the following modification; you may not use this file except in
# compliance with the Apache License and the following modification to it:
# Section 6. Trademarks. is deleted and replaced with:
#
# 6. Trademarks. This License does not grant permission to use the trade
#    names, trademarks, service marks, or product names of the Licensor
#    and its affiliates, except as required to comply with Section 4(c) of
#    the License and to reproduce the content of the NOTICE file.
#
# You may obtain a copy of the Apache License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the Apache License with the above modification is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the Apache License for the specific
# language governing permissions and limitations under the Apache License.
#
from __future__ import print_function

# Check whether this script is being run under Python 2 first. Otherwise,
# any Python 3-only code below will cause the script to fail with an
# unhelpful error message.
import sys
if sys.version_info.major == 2:
    sys.exit("ERROR: USD does not support Python 2. Use a supported version "
             "of Python 3 instead.")

import argparse
import codecs
import contextlib
import ctypes
import datetime
import distutils
import fnmatch
import glob
import locale
import multiprocessing
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
import zipfile

if sys.version_info.major >= 3:
    from urllib.request import urlopen
    from shutil import which
else:
    from urllib2 import urlopen

    # Doesn't deal with .bat / .cmd like shutil.which, but only option
    # available with stock python-2
    from distutils.spawn import find_executable as which

# Helpers for printing output
verbosity = 1

def Print(msg):
    if verbosity > 0:
        print(msg)

def PrintWarning(warning):
    if verbosity > 0:
        print("WARNING:", warning)

def PrintStatus(status):
    if verbosity >= 1:
        print("STATUS:", status)

def PrintInfo(info):
    if verbosity >= 2:
        print("INFO:", info)

def PrintCommandOutput(output):
    if verbosity >= 3:
        sys.stdout.write(output)

def PrintError(error):
    if verbosity >= 3 and sys.exc_info()[1] is not None:
        import traceback
        traceback.print_exc()
    print("ERROR:", error)

# Helpers for determining platform
def Windows():
    return platform.system() == "Windows"
def Linux():
    return platform.system() == "Linux"
def MacOS():
    return platform.system() == "Darwin"

if MacOS():
    import apple_utils

def Python3():
    return sys.version_info.major == 3

def GetLocale():
    return sys.stdout.encoding or locale.getdefaultlocale()[1] or "UTF-8"

def GetCommandOutput(command):
    """Executes the specified command and returns output or None."""
    try:
        return subprocess.check_output(
            shlex.split(command), 
            stderr=subprocess.STDOUT).decode(GetLocale(), 'replace').strip()
    except subprocess.CalledProcessError:
        pass
    return None

def GetXcodeDeveloperDirectory():
    """Returns the active developer directory as reported by 'xcode-select -p'.
    Returns None if none is set."""
    if not MacOS():
        return None

    return GetCommandOutput("xcode-select -p")

def GetVisualStudioCompilerAndVersion():
    """Returns a tuple containing the path to the Visual Studio compiler
    and a tuple for its version, e.g. (14, 0). If the compiler is not found
    or version number cannot be determined, returns None."""
    if not Windows():
        return None

    msvcCompiler = which('cl')
    if msvcCompiler:
        # VisualStudioVersion environment variable should be set by the
        # Visual Studio Command Prompt.
        match = re.search(
            r"(\d+)\.(\d+)",
            os.environ.get("VisualStudioVersion", ""))
        if match:
            return (msvcCompiler, tuple(int(v) for v in match.groups()))
    return None

def IsVisualStudioVersionOrGreater(desiredVersion):
    if not Windows():
        return False

    msvcCompilerAndVersion = GetVisualStudioCompilerAndVersion()
    if msvcCompilerAndVersion:
        _, version = msvcCompilerAndVersion
        return version >= desiredVersion
    return False

def IsVisualStudio2022OrGreater():
    VISUAL_STUDIO_2022_VERSION = (17, 0)
    return IsVisualStudioVersionOrGreater(VISUAL_STUDIO_2022_VERSION)

def IsVisualStudio2019OrGreater():
    VISUAL_STUDIO_2019_VERSION = (16, 0)
    return IsVisualStudioVersionOrGreater(VISUAL_STUDIO_2019_VERSION)

def IsVisualStudio2017OrGreater():
    VISUAL_STUDIO_2017_VERSION = (15, 0)
    return IsVisualStudioVersionOrGreater(VISUAL_STUDIO_2017_VERSION)

def GetPythonInfo(context):
    """Returns a tuple containing the path to the Python executable, shared
    library, and include directory corresponding to the version of Python
    currently running. Returns None if any path could not be determined.

    This function is used to extract build information from the Python 
    interpreter used to launch this script. This information is used
    in the Boost and USD builds. By taking this approach we can support
    having USD builds for different Python versions built on the same
    machine. This is very useful, especially when developers have multiple
    versions installed on their machine, which is quite common now with 
    Python2 and Python3 co-existing.
    """

    # If we were given build python info then just use it.
    if context.build_python_info:
        return (context.build_python_info['PYTHON_EXECUTABLE'],
                context.build_python_info['PYTHON_LIBRARY'],
                context.build_python_info['PYTHON_INCLUDE_DIR'],
                context.build_python_info['PYTHON_VERSION'])

    # First we extract the information that can be uniformly dealt with across
    # the platforms:
    pythonExecPath = sys.executable
    pythonVersion = sysconfig.get_config_var("py_version_short")  # "2.7"

    # Lib path is unfortunately special for each platform and there is no
    # config_var for it. But we can deduce it for each platform, and this
    # logic works for any Python version.
    def _GetPythonLibraryFilename(context):
        if Windows():
            return "python{version}{suffix}.lib".format(
                version=sysconfig.get_config_var("py_version_nodot"),
                suffix=('_d' if context.buildDebug and context.debugPython
                        else ''))
        elif Linux():
            return sysconfig.get_config_var("LDLIBRARY")
        elif MacOS():
            return "libpython{version}.dylib".format(
                version=(sysconfig.get_config_var('LDVERSION') or
                         sysconfig.get_config_var('VERSION') or
                         pythonVersion))
        else:
            raise RuntimeError("Platform not supported")

    pythonIncludeDir = sysconfig.get_path("include")
    if not pythonIncludeDir or not os.path.isdir(pythonIncludeDir):
        # as a backup, and for legacy reasons - not preferred because
        # it may be baked at build time
        pythonIncludeDir = sysconfig.get_config_var("INCLUDEPY")

    # if in a venv, installed_base will be the "original" python,
    # which is where the libs are ("base" will be the venv dir)
    pythonBaseDir = sysconfig.get_config_var("installed_base")
    if not pythonBaseDir or not os.path.isdir(pythonBaseDir):
        # for python-2.7
        pythonBaseDir = sysconfig.get_config_var("base")

    if Windows():
        pythonLibPath = os.path.join(pythonBaseDir, "libs",
                                     _GetPythonLibraryFilename(context))
    elif Linux():
        pythonMultiarchSubdir = sysconfig.get_config_var("multiarchsubdir")
        # Try multiple ways to get the python lib dir
        for pythonLibDir in (sysconfig.get_config_var("LIBDIR"),
                             os.path.join(pythonBaseDir, "lib")):
            if pythonMultiarchSubdir:
                pythonLibPath = \
                    os.path.join(pythonLibDir + pythonMultiarchSubdir,
                                 _GetPythonLibraryFilename(context))
                if os.path.isfile(pythonLibPath):
                    break
            pythonLibPath = os.path.join(pythonLibDir,
                                         _GetPythonLibraryFilename(context))
            if os.path.isfile(pythonLibPath):
                break
    elif MacOS():
        pythonLibPath = os.path.join(pythonBaseDir, "lib",
                                     _GetPythonLibraryFilename(context))
    else:
        raise RuntimeError("Platform not supported")

    return (pythonExecPath, pythonLibPath, pythonIncludeDir, pythonVersion)

def GetCPUCount():
    try:
        return multiprocessing.cpu_count()
    except NotImplementedError:
        return 1

def Run(cmd, logCommandOutput = True):
    """Run the specified command in a subprocess."""
    PrintInfo('Running "{cmd}"'.format(cmd=cmd))

    with codecs.open("log.txt", "a", "utf-8") as logfile:
        logfile.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        logfile.write("\n")
        logfile.write(cmd)
        logfile.write("\n")

        # Let exceptions escape from subprocess calls -- higher level
        # code will handle them.
        if logCommandOutput:
            p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, 
                                 stderr=subprocess.STDOUT)
            while True:
                l = p.stdout.readline().decode(GetLocale(), 'replace')
                if l:
                    logfile.write(l)
                    PrintCommandOutput(l)
                elif p.poll() is not None:
                    break
        else:
            p = subprocess.Popen(shlex.split(cmd))
            p.wait()

    if p.returncode != 0:
        # If verbosity >= 3, we'll have already been printing out command output
        # so no reason to print the log file again.
        if verbosity < 3:
            with open("log.txt", "r") as logfile:
                Print(logfile.read())
        raise RuntimeError("Failed to run '{cmd}'\nSee {log} for more details."
                           .format(cmd=cmd, log=os.path.abspath("log.txt")))

@contextlib.contextmanager
def CurrentWorkingDirectory(dir):
    """Context manager that sets the current working directory to the given
    directory and resets it to the original directory when closed."""
    curdir = os.getcwd()
    os.chdir(dir)
    try: yield
    finally: os.chdir(curdir)

def CopyFiles(context, src, dest):
    """Copy files like shutil.copy, but src may be a glob pattern."""
    filesToCopy = glob.glob(src)
    if not filesToCopy:
        raise RuntimeError("File(s) to copy {src} not found".format(src=src))

    instDestDir = os.path.join(context.instDir, dest)
    for f in filesToCopy:
        PrintCommandOutput("Copying {file} to {destDir}\n"
                           .format(file=f, destDir=instDestDir))
        shutil.copy(f, instDestDir)

def CopyDirectory(context, srcDir, destDir):
    """Copy directory like shutil.copytree."""
    instDestDir = os.path.join(context.instDir, destDir)
    if os.path.isdir(instDestDir):
        shutil.rmtree(instDestDir)    

    PrintCommandOutput("Copying {srcDir} to {destDir}\n"
                       .format(srcDir=srcDir, destDir=instDestDir))
    shutil.copytree(srcDir, instDestDir)

def AppendCXX11ABIArg(buildFlag, context, buildArgs):
    """Append a build argument that defines _GLIBCXX_USE_CXX11_ABI
    based on the settings in the context. This may either do nothing
    or append an entry to buildArgs like:

      <buildFlag>="-D_GLIBCXX_USE_CXX11_ABI={0, 1}"

    If buildArgs contains settings for buildFlag, those settings will
    be merged with the above define."""
    if context.useCXX11ABI is None:
        return

    cxxFlags = ["-D_GLIBCXX_USE_CXX11_ABI={}".format(context.useCXX11ABI)]
    
    # buildArgs might look like:
    # ["-DFOO=1", "-DBAR=2", ...] or ["-DFOO=1 -DBAR=2 ...", ...]
    #
    # See if any of the arguments in buildArgs start with the given
    # buildFlag. If so, we want to take whatever that buildFlag has
    # been set to and merge it in with the cxxFlags above.
    #
    # For example, if buildArgs = ['-DCMAKE_CXX_FLAGS="-w"', ...]
    # we want to add "-w" to cxxFlags.
    splitArgs = [shlex.split(a) for a in buildArgs]
    for p in [item for arg in splitArgs for item in arg]:
        if p.startswith(buildFlag):
            (_, _, flags) = p.partition("=")
            cxxFlags.append(flags)

    buildArgs.append('{flag}="{flags}"'.format(
        flag=buildFlag, flags=" ".join(cxxFlags)))

def FormatMultiProcs(numJobs, generator):
    tag = "-j"
    if generator:
        if "Visual Studio" in generator:
            tag = "/M:" # This will build multiple projects at once.
        elif "Xcode" in generator:
            tag = "-j "

    return "{tag}{procs}".format(tag=tag, procs=numJobs)

def RunCMake(context, force, extraArgs = None):
    """Invoke CMake to configure, build, and install a library whose 
    source code is located in the current working directory."""
    # Create a directory for out-of-source builds in the build directory
    # using the name of the current working directory.
    srcDir = os.getcwd()
    instDir = (context.usdInstDir if srcDir == context.usdSrcDir
               else context.instDir)
    buildDir = os.path.join(context.buildDir, os.path.split(srcDir)[1])
    if force and os.path.isdir(buildDir):
        shutil.rmtree(buildDir)

    if not os.path.isdir(buildDir):
        os.makedirs(buildDir)

    generator = context.cmakeGenerator

    # On Windows, we need to explicitly specify the generator to ensure we're
    # building a 64-bit project. (Surely there is a better way to do this?)
    # TODO: figure out exactly what "vcvarsall.bat x64" sets to force x64
    if generator is None and Windows():
        if IsVisualStudio2022OrGreater():
            generator = "Visual Studio 17 2022"
        elif IsVisualStudio2019OrGreater():
            generator = "Visual Studio 16 2019"
        elif IsVisualStudio2017OrGreater():
            generator = "Visual Studio 15 2017 Win64"

    if generator is not None:
        generator = '-G "{gen}"'.format(gen=generator)

    # Note - don't want to add -A (architecture flag) if generator is, ie, Ninja
    if IsVisualStudio2019OrGreater() and "Visual Studio" in generator:
        generator = generator + " -A x64"

    toolset = context.cmakeToolset
    if toolset is not None:
        toolset = '-T "{toolset}"'.format(toolset=toolset)

    # On MacOS, enable the use of @rpath for relocatable builds.
    osx_rpath = None
    if MacOS():
        osx_rpath = "-DCMAKE_MACOSX_RPATH=ON"

        # For macOS cross compilation, set the Xcode architecture flags.
        targetArch = apple_utils.GetTargetArch(context)

        if context.targetNative or targetArch == apple_utils.GetHostArch():
            extraArgs.append('-DCMAKE_XCODE_ATTRIBUTE_ONLY_ACTIVE_ARCH=YES')
        else:
            extraArgs.append('-DCMAKE_XCODE_ATTRIBUTE_ONLY_ACTIVE_ARCH=NO')

        extraArgs.append('-DCMAKE_OSX_ARCHITECTURES={0}'.format(targetArch))

    # We use -DCMAKE_BUILD_TYPE for single-configuration generators 
    # (Ninja, make), and --config for multi-configuration generators 
    # (Visual Studio); technically we don't need BOTH at the same
    # time, but specifying both is simpler than branching
    config = "Release"
    if context.buildDebug:
        config = "Debug"
    elif context.buildRelease:
        config = "Release"
    elif context.buildRelWithDebug:
        config = "RelWithDebInfo"

    # Append extra argument controlling libstdc++ ABI if specified.
    AppendCXX11ABIArg("-DCMAKE_CXX_FLAGS", context, extraArgs)

    with CurrentWorkingDirectory(buildDir):
        Run('cmake '
            '-DCMAKE_INSTALL_PREFIX="{instDir}" '
            '-DCMAKE_PREFIX_PATH="{depsInstDir}" '
            '-DCMAKE_BUILD_TYPE={config} '
            '{osx_rpath} '
            '{generator} '
            '{toolset} '
            '{extraArgs} '
            '"{srcDir}"'
            .format(instDir=instDir,
                    depsInstDir=context.instDir,
                    config=config,
                    srcDir=srcDir,
                    osx_rpath=(osx_rpath or ""),
                    generator=(generator or ""),
                    toolset=(toolset or ""),
                    extraArgs=(" ".join(extraArgs) if extraArgs else "")))
        Run("cmake --build . --config {config} --target install -- {multiproc}"
            .format(config=config,
                    multiproc=FormatMultiProcs(context.numJobs, generator)))

def GetCMakeVersion():
    """
    Returns the CMake version as tuple of integers (major, minor) or
    (major, minor, patch) or None if an error occured while launching cmake and
    parsing its output.
    """

    output_string = GetCommandOutput("cmake --version")
    if not output_string:
        PrintWarning("Could not determine cmake version -- please install it "
                     "and adjust your PATH")
        return None

    # cmake reports, e.g., "... version 3.14.3"
    match = re.search(r"version (\d+)\.(\d+)(\.(\d+))?", output_string)
    if not match:
        PrintWarning("Could not determine cmake version")
        return None

    major, minor, patch_group, patch = match.groups()
    if patch_group is None:
        return (int(major), int(minor))
    else:
        return (int(major), int(minor), int(patch))

def PatchFile(filename, patches, multiLineMatches=False):
    """Applies patches to the specified file. patches is a list of tuples
    (old string, new string)."""
    if multiLineMatches:
        oldLines = [open(filename, 'r').read()]
    else:
        oldLines = open(filename, 'r').readlines()
    newLines = oldLines
    for (oldString, newString) in patches:
        newLines = [s.replace(oldString, newString) for s in newLines]
    if newLines != oldLines:
        PrintInfo("Patching file {filename} (original in {oldFilename})..."
                  .format(filename=filename, oldFilename=filename + ".old"))
        shutil.copy(filename, filename + ".old")
        open(filename, 'w').writelines(newLines)

def DownloadFileWithCurl(url, outputFilename):
    # Don't log command output so that curl's progress
    # meter doesn't get written to the log file.
    Run("curl {progress} -L -o {filename} {url}".format(
        progress="-#" if verbosity >= 2 else "-s",
        filename=outputFilename, url=url), 
        logCommandOutput=False)

def DownloadFileWithPowershell(url, outputFilename):
    # It's important that we specify to use TLS v1.2 at least or some
    # of the downloads will fail.
    cmd = "powershell [Net.ServicePointManager]::SecurityProtocol = \
            [Net.SecurityProtocolType]::Tls12; \"(new-object \
            System.Net.WebClient).DownloadFile('{url}', '{filename}')\""\
            .format(filename=outputFilename, url=url)

    Run(cmd,logCommandOutput=False)

def DownloadFileWithUrllib(url, outputFilename):
    r = urlopen(url)
    with open(outputFilename, "wb") as outfile:
        outfile.write(r.read())

def DownloadURL(url, context, force, extractDir = None, 
        dontExtract = None):
    """Download and extract the archive file at given URL to the
    source directory specified in the context. 

    dontExtract may be a sequence of path prefixes that will
    be excluded when extracting the archive.

    Returns the absolute path to the directory where files have 
    been extracted."""
    with CurrentWorkingDirectory(context.srcDir):
        # Extract filename from URL and see if file already exists. 
        filename = url.split("/")[-1]       
        if force and os.path.exists(filename):
            os.remove(filename)

        if os.path.exists(filename):
            PrintInfo("{0} already exists, skipping download"
                      .format(os.path.abspath(filename)))
        else:
            PrintInfo("Downloading {0} to {1}"
                      .format(url, os.path.abspath(filename)))

            # To work around occasional hiccups with downloading from websites
            # (SSL validation errors, etc.), retry a few times if we don't
            # succeed in downloading the file.
            maxRetries = 5
            lastError = None

            # Download to a temporary file and rename it to the expected
            # filename when complete. This ensures that incomplete downloads
            # will be retried if the script is run again.
            tmpFilename = filename + ".tmp"
            if os.path.exists(tmpFilename):
                os.remove(tmpFilename)

            for i in range(maxRetries):
                try:
                    context.downloader(url, tmpFilename)
                    break
                except Exception as e:
                    PrintCommandOutput("Retrying download due to error: {err}\n"
                                       .format(err=e))
                    lastError = e
            else:
                errorMsg = str(lastError)
                if "SSL: TLSV1_ALERT_PROTOCOL_VERSION" in errorMsg:
                    errorMsg += ("\n\n"
                                 "Your OS or version of Python may not support "
                                 "TLS v1.2+, which is required for downloading "
                                 "files from certain websites. This support "
                                 "was added in Python 2.7.9."
                                 "\n\n"
                                 "You can use curl to download dependencies "
                                 "by installing it in your PATH and re-running "
                                 "this script.")
                raise RuntimeError("Failed to download {url}: {err}"
                                   .format(url=url, err=errorMsg))

            shutil.move(tmpFilename, filename)

        # Open the archive and retrieve the name of the top-most directory.
        # This assumes the archive contains a single directory with all
        # of the contents beneath it, unless a specific extractDir is specified,
        # which is to be used.
        archive = None
        rootDir = None
        members = None
        try:
            if zipfile.is_zipfile(filename):
                archive = zipfile.ZipFile(filename)
                if extractDir:
                    rootDir = extractDir
                else:
                    rootDir = archive.namelist()[0].split('/')[0]
                if dontExtract != None:
                    members = (m for m in archive.namelist() 
                               if not any((fnmatch.fnmatch(m, p)
                                           for p in dontExtract)))
            else:
                raise RuntimeError("unrecognized archive file type")

            with archive:
                extractedPath = os.path.abspath(rootDir)
                if force and os.path.isdir(extractedPath):
                    shutil.rmtree(extractedPath)

                if os.path.isdir(extractedPath):
                    PrintInfo("Directory {0} already exists, skipping extract"
                              .format(extractedPath))
                else:
                    PrintInfo("Extracting archive to {0}".format(extractedPath))

                    # Extract to a temporary directory then move the contents
                    # to the expected location when complete. This ensures that
                    # incomplete extracts will be retried if the script is run
                    # again.
                    tmpExtractedPath = os.path.abspath("extract_dir")
                    if os.path.isdir(tmpExtractedPath):
                        shutil.rmtree(tmpExtractedPath)

                    archive.extractall(tmpExtractedPath, members=members)

                    shutil.move(os.path.join(tmpExtractedPath, rootDir),
                                extractedPath)
                    shutil.rmtree(tmpExtractedPath)

                return extractedPath
        except Exception as e:
            # If extraction failed for whatever reason, assume the
            # archive file was bad and move it aside so that re-running
            # the script will try downloading and extracting again.
            shutil.move(filename, filename + ".bad")
            raise RuntimeError("Failed to extract archive {filename}: {err}"
                               .format(filename=filename, err=e))

############################################################
# 3rd-Party Dependencies

AllDependencies = list()
AllDependenciesByName = dict()

class Dependency(object):
    def __init__(self, name, installer, *files):
        self.name = name
        self.installer = installer
        self.filesToCheck = files

        AllDependencies.append(self)
        AllDependenciesByName.setdefault(name.lower(), self)

    def Exists(self, context):
        return any([os.path.isfile(os.path.join(context.instDir, f))
                    for f in self.filesToCheck])

class PythonDependency(object):
    def __init__(self, name, getInstructions, moduleNames):
        self.name = name
        self.getInstructions = getInstructions
        self.moduleNames = moduleNames

    def Exists(self, context):
        # If one of the modules in our list imports successfully, we are good.
        for moduleName in self.moduleNames:
            try:
                pyModule = __import__(moduleName)
                return True
            except:
                pass

        return False

def AnyPythonDependencies(deps):
    return any([type(d) is PythonDependency for d in deps])

############################################################
# boost

if Windows():
    BOOST_VERSION_FILE = "include/boost/boost/version.hpp"
else:
    BOOST_VERSION_FILE = "include/boost/version.hpp"

def InstallBoost_Helper(context, force, buildArgs):

    # In general we use boost 1.70.0 to adhere to VFX Reference Platform CY2020.
    # However, there are some cases where a newer version is required.
    # - Building with Python 3.10 requires boost 1.76.0 or newer.
    #   (https://github.com/boostorg/python/commit/cbd2d9)
    # - Building with Visual Studio 2022 requires boost 1.78.0 or newer.
    #   (https://github.com/boostorg/build/issues/735)
    # - Building on MacOS requires boost 1.78.0 or newer to resolve Python 3
    #   compatibility issues on Big Sur and Monterey.
    pyInfo = GetPythonInfo(context)
    pyVer = (int(pyInfo[3].split('.')[0]), int(pyInfo[3].split('.')[1]))
    if context.buildPython and pyVer >= (3, 10):
        BOOST_URL = "https://boostorg.jfrog.io/artifactory/main/release/1.80.0/source/boost_1_80_0.zip"
    elif IsVisualStudio2022OrGreater():
        BOOST_URL = "https://boostorg.jfrog.io/artifactory/main/release/1.80.0/source/boost_1_80_0.zip"
    elif MacOS():
        BOOST_URL = "https://boostorg.jfrog.io/artifactory/main/release/1.80.0/source/boost_1_80_0.zip"
    else:
        BOOST_URL = "https://boostorg.jfrog.io/artifactory/main/release/1.80.0/source/boost_1_80_0.zip"

    # Documentation files in the boost archive can have exceptionally
    # long paths. This can lead to errors when extracting boost on Windows,
    # since paths are limited to 260 characters by default on that platform.
    # To avoid this, we skip extracting all documentation.
    #
    # For some examples, see: https://svn.boost.org/trac10/ticket/11677
    dontExtract = [
        "*/doc/*",
        "*/libs/*/doc/*",
        "*/libs/wave/test/testwave/testfiles/utf8-test-*"
    ]
    print("BOOST1")
    with CurrentWorkingDirectory(DownloadURL(BOOST_URL, context, force, 
                                             dontExtract=dontExtract)):
        if Windows():
            bootstrap = "bootstrap.bat"
        else:
            bootstrap = "./bootstrap.sh"
            # zip doesn't preserve file attributes, so force +x manually.
            Run('chmod +x ' + bootstrap)
            Run('chmod +x ./tools/build/src/engine/build.sh')

        # For cross-compilation on macOS we need to specify the architecture
        # for both the bootstrap and the b2 phase of building boost.
        print("context.instDir", context.instDir)
        print("bootstrap", bootstrap)
        bootstrapCmd = '{bootstrap} --prefix="{instDir}"'.format(
            bootstrap=bootstrap, instDir=context.instDir)

        macOSArch = ""

        if MacOS():
            if apple_utils.GetTargetArch(context) == \
                        apple_utils.TARGET_X86:
                macOSArch = "-arch {0}".format(apple_utils.TARGET_X86)
            elif apple_utils.GetTargetArch(context) == \
                        apple_utils.GetTargetArmArch():
                macOSArch = "-arch {0}".format(
                        apple_utils.GetTargetArmArch())
            elif context.targetUniversal:
                (primaryArch, secondaryArch) = \
                        apple_utils.GetTargetArchPair(context)
                macOSArch="-arch {0} -arch {1}".format(
                        primaryArch, secondaryArch)

            if macOSArch:
                bootstrapCmd += " cxxflags=\"{0}\" " \
                                " cflags=\"{0}\" " \
                                " linkflags=\"{0}\"".format(macOSArch)
            bootstrapCmd += " --with-toolset=clang"

        print("BOOST2")
        Run(bootstrapCmd)

        print("BOOST3")
        # b2 supports at most -j64 and will error if given a higher value.
        num_procs = min(64, context.numJobs)

        # boost only accepts three variants: debug, release, profile
        boostBuildVariant = "profile"
        if context.buildDebug:
            boostBuildVariant= "debug"
        elif context.buildRelease:
            boostBuildVariant= "release"
        elif context.buildRelWithDebug:
            boostBuildVariant= "profile"

        print("BOOST", context.instDir)
        print("BOOST", context.buildDir)

        b2_settings = [
            '--prefix="{instDir}"'.format(instDir=context.instDir),
            '--build-dir="{buildDir}"'.format(buildDir=context.buildDir),
            '-j{procs}'.format(procs=num_procs),
            'address-model=64',
            'link=shared',
            'runtime-link=shared',
            'threading=multi', 
            'variant={variant}'.format(variant=boostBuildVariant),
            '--with-atomic',
            '--with-regex',
            '--with-log'
        ]

        if context.buildPython:
            b2_settings.append("--with-python")
            pythonInfo = GetPythonInfo(context)
            # This is the only platform-independent way to configure these
            # settings correctly and robustly for the Boost jam build system.
            # There are Python config arguments that can be passed to bootstrap 
            # but those are not available in boostrap.bat (Windows) so we must 
            # take the following approach:
            projectPath = 'python-config.jam'
            with open(projectPath, 'w') as projectFile:
                # Note that we must escape any special characters, like 
                # backslashes for jam, hence the mods below for the path 
                # arguments. Also, if the path contains spaces jam will not
                # handle them well. Surround the path parameters in quotes.
                projectFile.write('using python : %s\n' % pythonInfo[3])
                projectFile.write('  : "%s"\n' % pythonInfo[0].replace("\\","/"))
                projectFile.write('  : "%s"\n' % pythonInfo[2].replace("\\","/"))
                projectFile.write('  : "%s"\n' % os.path.dirname(pythonInfo[1]).replace("\\","/"))
                if context.buildDebug and context.debugPython:
                    projectFile.write('  : <python-debugging>on\n')
                projectFile.write('  ;\n')
            b2_settings.append("--user-config=python-config.jam")

            if context.buildDebug and context.debugPython:
                b2_settings.append("python-debugging=on")

            # b2 with -sNO_COMPRESSION=1 fails with the following error message:
            #     error: at [...]/boost_1_61_0/tools/build/src/kernel/modules.jam:107
            #     error: Unable to find file or target named
            #     error:     '/zlib//zlib'
            #     error: referred to from project at
            #     error:     'libs/iostreams/build'
            #     error: could not resolve project reference '/zlib'

            # But to avoid an extra library dependency, we can still explicitly
            # exclude the bzip2 compression from boost_iostreams (note that
            # OpenVDB uses blosc compression).
            b2_settings.append("-sNO_BZIP2=1")

        if force:
            b2_settings.append("-a")

        if Windows():
            # toolset parameter for Visual Studio documented here:
            # https://github.com/boostorg/build/blob/develop/src/tools/msvc.jam
            if context.cmakeToolset == "v143":
                b2_settings.append("toolset=msvc-14.3")
            elif context.cmakeToolset == "v142":
                b2_settings.append("toolset=msvc-14.2")
            elif context.cmakeToolset == "v141":
                b2_settings.append("toolset=msvc-14.1")
            elif IsVisualStudio2022OrGreater():
                b2_settings.append("toolset=msvc-14.3")
            elif IsVisualStudio2019OrGreater():
                b2_settings.append("toolset=msvc-14.2")
            elif IsVisualStudio2017OrGreater():
                b2_settings.append("toolset=msvc-14.1")

        if MacOS():
            # Must specify toolset=clang to ensure install_name for boost
            # libraries includes @rpath
            b2_settings.append("toolset=clang")

            if macOSArch:
                b2_settings.append("cxxflags=\"{0}\"".format(macOSArch))
                b2_settings.append("cflags=\"{0}\"".format(macOSArch))
                b2_settings.append("linkflags=\"{0}\"".format(macOSArch))

        if context.buildDebug:
            b2_settings.append("--debug-configuration")

        # Add on any user-specified extra arguments.
        b2_settings += buildArgs

        # Append extra argument controlling libstdc++ ABI if specified.
        AppendCXX11ABIArg("cxxflags", context, b2_settings)

        b2 = "b2" if Windows() else "./b2"
        Run('{b2} {options} install'
            .format(b2=b2, options=" ".join(b2_settings)))

def InstallBoost(context, force, buildArgs):
    # Boost's build system will install the version.hpp header before
    # building its libraries. We make sure to remove it in case of
    # any failure to ensure that the build script detects boost as a 
    # dependency to build the next time it's run.
    try:
        InstallBoost_Helper(context, force, buildArgs)
    except:
        versionHeader = os.path.join(context.instDir, BOOST_VERSION_FILE)
        if os.path.isfile(versionHeader):
            try: os.remove(versionHeader)
            except: pass
        raise

# The default installation of boost on Windows puts headers in a versioned 
# subdirectory, which we have to account for here. Specifying "layout=system" 
# would cause the Windows header install to match Linux/MacOS, but the 
# "layout=system" flag also changes the naming of the boost dlls in a 
# manner that causes problems for dependent libraries that rely on boost's
# trick of automatically linking the boost libraries via pragmas in boost's
# standard include files. Dependencies that use boost's pragma linking
# facility in general don't have enough configuration switches to also coerce 
# the naming of the dlls and so it is best to rely on boost's most default
# settings for maximum compatibility.
#
# On behalf of versions of visual studio prior to vs2022, we still support
# boost 1.70. We don't completely know if boost 1.78 is in play on Windows, 
# until we have determined whether Python 3 has been selected as a target. 
# That isn't known at this point in the script, so we simplify the logic by 
# checking for any of the possible boost header locations that are possible
# outcomes from running this script.
BOOST = Dependency("boost", InstallBoost, 
                   "include/boost/version.hpp",
                   "include/boost-1_80/boost/version.hpp",
                   "include/boost-1_80/boost/version.hpp")

############################################################
# USD

def InstallUSD(context, force, buildArgs):
    with CurrentWorkingDirectory(context.usdSrcDir):
        extraArgs = []

        extraArgs.append('-DPXR_PREFER_SAFETY_OVER_SPEED={}'
                         .format('ON' if context.safetyFirst else 'OFF'))

        if context.buildPython:
            extraArgs.append('-DPXR_ENABLE_PYTHON_SUPPORT=ON')
            extraArgs.append('-DPXR_USE_PYTHON_3={}'
                             .format('ON' if Python3() else 'OFF'))

            # Many people on Windows may not have python with the 
            # debugging symbol ( python27_d.lib ) installed, this is the common case 
            # where one downloads the python from official download website. Therefore we 
            # can still let people decide to build USD with release version of python if 
            # debugging into python land is not what they want which can be done by setting the 
            # debugPython
            if context.buildDebug and context.debugPython:
                extraArgs.append('-DPXR_USE_DEBUG_PYTHON=ON')
            else:
                extraArgs.append('-DPXR_USE_DEBUG_PYTHON=OFF')

            # CMake has trouble finding the executable, library, and include
            # directories when there are multiple versions of Python installed.
            # This can lead to crashes due to USD being linked against one
            # version of Python but running through some other Python
            # interpreter version. This primarily shows up on macOS, as it's
            # common to have a Python install that's separate from the one
            # included with the system.
            #
            # To avoid this, we try to determine these paths from Python
            # itself rather than rely on CMake's heuristics.
            pythonInfo = GetPythonInfo(context)
            if pythonInfo:
                prefix = "Python3" if Python3() else "Python2"
                extraArgs.append('-D{prefix}_EXECUTABLE="{pyExecPath}"'
                                 .format(prefix=prefix, 
                                         pyExecPath=pythonInfo[0]))
                extraArgs.append('-D{prefix}_LIBRARY="{pyLibPath}"'
                                 .format(prefix=prefix,
                                         pyLibPath=pythonInfo[1]))
                extraArgs.append('-D{prefix}_INCLUDE_DIR="{pyIncPath}"'
                                 .format(prefix=prefix,
                                         pyIncPath=pythonInfo[2]))
        else:
            extraArgs.append('-DPXR_ENABLE_PYTHON_SUPPORT=OFF')

        if context.buildShared:
            extraArgs.append('-DBUILD_SHARED_LIBS=ON')
        elif context.buildMonolithic:
            extraArgs.append('-DPXR_BUILD_MONOLITHIC=ON')

        if context.buildDebug:
            extraArgs.append('-DTBB_USE_DEBUG_BUILD=ON')
        else:
            extraArgs.append('-DTBB_USE_DEBUG_BUILD=OFF')

        if context.buildDocs:
            extraArgs.append('-DPXR_BUILD_DOCUMENTATION=ON')
        else:
            extraArgs.append('-DPXR_BUILD_DOCUMENTATION=OFF')
    
        if context.buildTests:
            extraArgs.append('-DPXR_BUILD_TESTS=ON')
        else:
            extraArgs.append('-DPXR_BUILD_TESTS=OFF')

        if context.buildExamples:
            extraArgs.append('-DPXR_BUILD_EXAMPLES=ON')
        else:
            extraArgs.append('-DPXR_BUILD_EXAMPLES=OFF')

        if context.buildTutorials:
            extraArgs.append('-DPXR_BUILD_TUTORIALS=ON')
        else:
            extraArgs.append('-DPXR_BUILD_TUTORIALS=OFF')

        if context.buildTools:
            extraArgs.append('-DPXR_BUILD_USD_TOOLS=ON')
        else:
            extraArgs.append('-DPXR_BUILD_USD_TOOLS=OFF')
            
        if context.buildImaging:
            extraArgs.append('-DPXR_BUILD_IMAGING=ON')
            if context.enablePtex:
                extraArgs.append('-DPXR_ENABLE_PTEX_SUPPORT=ON')
            else:
                extraArgs.append('-DPXR_ENABLE_PTEX_SUPPORT=OFF')

            if context.enableOpenVDB:
                extraArgs.append('-DPXR_ENABLE_OPENVDB_SUPPORT=ON')
            else:
                extraArgs.append('-DPXR_ENABLE_OPENVDB_SUPPORT=OFF')

            if context.buildEmbree:
                extraArgs.append('-DPXR_BUILD_EMBREE_PLUGIN=ON')
            else:
                extraArgs.append('-DPXR_BUILD_EMBREE_PLUGIN=OFF')

            if context.buildPrman:
                if context.prmanLocation:
                    extraArgs.append('-DRENDERMAN_LOCATION="{location}"'
                                     .format(location=context.prmanLocation))
                extraArgs.append('-DPXR_BUILD_PRMAN_PLUGIN=ON')
            else:
                extraArgs.append('-DPXR_BUILD_PRMAN_PLUGIN=OFF')                
            
            if context.buildOIIO:
                extraArgs.append('-DPXR_BUILD_OPENIMAGEIO_PLUGIN=ON')
            else:
                extraArgs.append('-DPXR_BUILD_OPENIMAGEIO_PLUGIN=OFF')
                
            if context.buildOCIO:
                extraArgs.append('-DPXR_BUILD_OPENCOLORIO_PLUGIN=ON')
            else:
                extraArgs.append('-DPXR_BUILD_OPENCOLORIO_PLUGIN=OFF')

        else:
            extraArgs.append('-DPXR_BUILD_IMAGING=OFF')

        if context.buildUsdImaging:
            extraArgs.append('-DPXR_BUILD_USD_IMAGING=ON')
        else:
            extraArgs.append('-DPXR_BUILD_USD_IMAGING=OFF')

        if context.buildUsdview:
            extraArgs.append('-DPXR_BUILD_USDVIEW=ON')
        else:
            extraArgs.append('-DPXR_BUILD_USDVIEW=OFF')

        if context.buildAlembic:
            extraArgs.append('-DPXR_BUILD_ALEMBIC_PLUGIN=ON')
            if context.enableHDF5:
                extraArgs.append('-DPXR_ENABLE_HDF5_SUPPORT=ON')

                # CMAKE_PREFIX_PATH isn't sufficient for the FindHDF5 module 
                # to find the HDF5 we've built, so provide an extra hint.
                extraArgs.append('-DHDF5_ROOT="{instDir}"'
                                 .format(instDir=context.instDir))
            else:
                extraArgs.append('-DPXR_ENABLE_HDF5_SUPPORT=OFF')
        else:
            extraArgs.append('-DPXR_BUILD_ALEMBIC_PLUGIN=OFF')

        if context.buildDraco:
            extraArgs.append('-DPXR_BUILD_DRACO_PLUGIN=ON')
            draco_root = (context.dracoLocation
                          if context.dracoLocation else context.instDir)
            extraArgs.append('-DDRACO_ROOT="{}"'.format(draco_root))
        else:
            extraArgs.append('-DPXR_BUILD_DRACO_PLUGIN=OFF')

        if context.buildMaterialX:
            extraArgs.append('-DPXR_ENABLE_MATERIALX_SUPPORT=ON')
        else:
            extraArgs.append('-DPXR_ENABLE_MATERIALX_SUPPORT=OFF')

        if context.buildPythonDocs:
            extraArgs.append('-DPXR_BUILD_PYTHON_DOCUMENTATION=ON')
        else:
            extraArgs.append('-DPXR_BUILD_PYTHON_DOCUMENTATION=OFF')

        if Windows():
            # Increase the precompiled header buffer limit.
            extraArgs.append('-DCMAKE_CXX_FLAGS="/Zm150"')

        # Make sure to use boost installed by the build script and not any
        # system installed boost
        extraArgs.append('-DBoost_NO_BOOST_CMAKE=On')
        extraArgs.append('-DBoost_NO_SYSTEM_PATHS=True')
        extraArgs += buildArgs

        RunCMake(context, force, extraArgs)

# USD = Dependency("USD", InstallUSD, "include/pxr/pxr.h")

############################################################
# Install script

programDescription = """\
Installation Script for USD

Builds and installs USD and 3rd-party dependencies to specified location.

- Libraries:
The following is a list of libraries that this script will download and build
as needed. These names can be used to identify libraries for various script
options, like --force or --build-args.

{libraryList}

- Downloading Libraries:
If curl or powershell (on Windows) are installed and located in PATH, they
will be used to download dependencies. Otherwise, a built-in downloader will 
be used.

- Specifying Custom Build Arguments:
Users may specify custom build arguments for libraries using the --build-args
option. This values for this option must take the form <library name>,<option>. 
For example:

%(prog)s --build-args boost,cxxflags=... USD,-DPXR_STRICT_BUILD_MODE=ON ...
%(prog)s --build-args USD,"-DPXR_STRICT_BUILD_MODE=ON -DPXR_HEADLESS_TEST_MODE=ON" ...

These arguments will be passed directly to the build system for the specified 
library. Multiple quotes may be needed to ensure arguments are passed on 
exactly as desired. Users must ensure these arguments are suitable for the
specified library and do not conflict with other options, otherwise build 
errors may occur.

- Python Versions and DCC Plugins:
Some DCCs may ship with and run using their own version of Python. In that case,
it is important that USD and the plugins for that DCC are built using the DCC's
version of Python and not the system version. This can be done by running
%(prog)s using the DCC's version of Python.

If %(prog)s does not automatically detect the necessary information, the flag
--build-python-info can be used to explicitly pass in the Python that you want
USD to use to build the Python bindings with. This flag takes 4 arguments: 
Python executable, Python include directory Python library and Python version.

Note that this is primarily an issue on MacOS, where a DCC's version of Python
is likely to conflict with the version provided by the system.

- C++11 ABI Compatibility:
On Linux, the --use-cxx11-abi parameter can be used to specify whether to use
the C++11 ABI for libstdc++ when building USD and any dependencies. The value
given to this parameter will be used to define _GLIBCXX_USE_CXX11_ABI for
all builds.

If this parameter is not specified, the compiler's default ABI will be used.

For more details see:
https://gcc.gnu.org/onlinedocs/libstdc++/manual/using_dual_abi.html
""".format(
    libraryList=" ".join(sorted([d.name for d in AllDependencies])))

parser = argparse.ArgumentParser(
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description=programDescription)

parser.add_argument("install_dir", type=str, 
                    help="Directory where USD will be installed")
parser.add_argument("-n", "--dry_run", dest="dry_run", action="store_true",
                    help="Only summarize what would happen")
                    
group = parser.add_mutually_exclusive_group()
group.add_argument("-v", "--verbose", action="count", default=1,
                   dest="verbosity",
                   help="Increase verbosity level (1-3)")
group.add_argument("-q", "--quiet", action="store_const", const=0,
                   dest="verbosity",
                   help="Suppress all output except for error messages")

group = parser.add_argument_group(title="Build Options")
group.add_argument("-j", "--jobs", type=int, default=GetCPUCount(),
                   help=("Number of build jobs to run in parallel. "
                         "(default: # of processors [{0}])"
                         .format(GetCPUCount())))
group.add_argument("--build", type=str,
                   help=("Build directory for USD and 3rd-party dependencies " 
                         "(default: <install_dir>/build)"))

BUILD_DEBUG = "debug"
BUILD_RELEASE = "release"
BUILD_RELWITHDEBUG = "relwithdebuginfo"
group.add_argument("--build-variant", default=BUILD_RELEASE,
                   choices=[BUILD_DEBUG, BUILD_RELEASE, BUILD_RELWITHDEBUG],
                   help=("Build variant for USD and 3rd-party dependencies. "
                         "(default: {})".format(BUILD_RELEASE)))

if MacOS():
    group.add_argument("--build-target",
                       default=apple_utils.GetBuildTargetDefault(),
                       choices=apple_utils.GetBuildTargets(),
                       help=("Build target for macOS cross compilation. "
                             "(default: {})".format(
                                apple_utils.GetBuildTargetDefault())))

group.add_argument("--build-args", type=str, nargs="*", default=[],
                   help=("Custom arguments to pass to build system when "
                         "building libraries (see docs above)"))
group.add_argument("--build-python-info", type=str, nargs=4, default=[],
                   metavar=('PYTHON_EXECUTABLE', 'PYTHON_INCLUDE_DIR', 'PYTHON_LIBRARY', 'PYTHON_VERSION'),
                   help=("Specify a custom python to use during build"))
group.add_argument("--force", type=str, action="append", dest="force_build",
                   default=[],
                   help=("Force download and build of specified library "
                         "(see docs above)"))
group.add_argument("--force-all", action="store_true",
                   help="Force download and build of all libraries")
group.add_argument("--generator", type=str,
                   help=("CMake generator to use when building libraries with "
                         "cmake"))
group.add_argument("--toolset", type=str,
                   help=("CMake toolset to use when building libraries with "
                         "cmake"))
if MacOS():
    codesignDefault = True if apple_utils.IsHostArm() else False
    group.add_argument("--codesign", dest="macos_codesign",
                       default=codesignDefault, action="store_true",
                       help=("Enable code signing for macOS builds "
                             "(defaults to enabled on Apple Silicon)"))

if Linux():
    group.add_argument("--use-cxx11-abi", type=int, choices=[0, 1],
                       help=("Use C++11 ABI for libstdc++. (see docs above)"))

group = parser.add_argument_group(title="3rd Party Dependency Build Options")
group.add_argument("--src", type=str,
                   help=("Directory where dependencies will be downloaded "
                         "(default: <install_dir>/src)"))
group.add_argument("--inst", type=str,
                   help=("Directory where dependencies will be installed "
                         "(default: <install_dir>)"))

group = parser.add_argument_group(title="USD Options")

(SHARED_LIBS, MONOLITHIC_LIB) = (0, 1)
subgroup = group.add_mutually_exclusive_group()
subgroup.add_argument("--build-shared", dest="build_type",
                      action="store_const", const=SHARED_LIBS, 
                      default=SHARED_LIBS,
                      help="Build individual shared libraries (default)")
subgroup.add_argument("--build-monolithic", dest="build_type",
                      action="store_const", const=MONOLITHIC_LIB,
                      help="Build a single monolithic shared library")

subgroup = group.add_mutually_exclusive_group()
subgroup.add_argument("--tests", dest="build_tests", action="store_true",
                      default=False, help="Build unit tests")
subgroup.add_argument("--no-tests", dest="build_tests", action="store_false",
                      help="Do not build unit tests (default)")
subgroup = group.add_mutually_exclusive_group()
subgroup.add_argument("--examples", dest="build_examples", action="store_true",
                      default=True, help="Build examples (default)")
subgroup.add_argument("--no-examples", dest="build_examples", action="store_false",
                      help="Do not build examples")
subgroup = group.add_mutually_exclusive_group()
subgroup.add_argument("--tutorials", dest="build_tutorials", action="store_true",
                      default=True, help="Build tutorials (default)")
subgroup.add_argument("--no-tutorials", dest="build_tutorials", action="store_false",
                      help="Do not build tutorials")
subgroup = group.add_mutually_exclusive_group()
subgroup.add_argument("--tools", dest="build_tools", action="store_true",
                     default=True, help="Build USD tools (default)")
subgroup.add_argument("--no-tools", dest="build_tools", action="store_false",
                      help="Do not build USD tools")
subgroup = group.add_mutually_exclusive_group()
subgroup.add_argument("--docs", dest="build_docs", action="store_true",
                      default=False, help="Build documentation")
subgroup.add_argument("--no-docs", dest="build_docs", action="store_false",
                      help="Do not build documentation (default)")
subgroup = group.add_mutually_exclusive_group()
subgroup.add_argument("--python-docs", dest="build_python_docs", action="store_true",
                      default=False, help="Build Python docs")
subgroup.add_argument("--no-python-docs", dest="build_python_docs", action="store_false",
                      help="Do not build Python documentation (default)")
subgroup = group.add_mutually_exclusive_group()
subgroup.add_argument("--python", dest="build_python", action="store_true",
                      default=True, help="Build python based components "
                                         "(default)")
subgroup.add_argument("--no-python", dest="build_python", action="store_false",
                      help="Do not build python based components")
subgroup = group.add_mutually_exclusive_group()
subgroup.add_argument("--prefer-safety-over-speed", dest="safety_first",
                      action="store_true", default=True, help=
                      "Enable extra safety checks (which may negatively "
                      "impact performance) against malformed input files "
                      "(default)")
subgroup.add_argument("--prefer-speed-over-safety", dest="safety_first",
                      action="store_false", help=
                      "Disable performance-impacting safety checks against "
                      "malformed input files")

subgroup = group.add_mutually_exclusive_group()
subgroup.add_argument("--debug-python", dest="debug_python", action="store_true",
                      help="Define Boost Python Debug if your Python library comes with Debugging symbols.")

subgroup.add_argument("--no-debug-python", dest="debug_python", action="store_false",
                      help="Don't define Boost Python Debug if your Python library comes with Debugging symbols.")

(NO_IMAGING, IMAGING, USD_IMAGING) = (0, 1, 2)

args = parser.parse_args()

class InstallContext:
    def __init__(self, args):
        # Assume the USD source directory is in the parent directory
        self.usdSrcDir = os.path.normpath(
            os.path.join(os.path.abspath(os.path.dirname(__file__)), ".."))

        # Directory where USD will be installed
        self.usdInstDir = os.path.abspath(args.install_dir)

        # Directory where dependencies will be installed
        self.instDir = (os.path.abspath(args.inst) if args.inst 
                        else self.usdInstDir)

        # Directory where dependencies will be downloaded and extracted
        self.srcDir = (os.path.abspath(args.src) if args.src
                       else os.path.join(self.usdInstDir, "src"))
        
        # Directory where USD and dependencies will be built
        self.buildDir = (os.path.abspath(args.build) if args.build
                         else os.path.join(self.usdInstDir, "build"))

        # Determine which downloader to use.  The reason we don't simply
        # use urllib2 all the time is that some older versions of Python
        # don't support TLS v1.2, which is required for downloading some
        # dependencies.
        if which("curl"):
            self.downloader = DownloadFileWithCurl
            self.downloaderName = "curl"
        elif Windows() and which("powershell"):
            self.downloader = DownloadFileWithPowershell
            self.downloaderName = "powershell"
        else:
            self.downloader = DownloadFileWithUrllib
            self.downloaderName = "built-in"

        # CMake generator and toolset
        self.cmakeGenerator = args.generator
        self.cmakeToolset = args.toolset

        # Number of jobs
        self.numJobs = args.jobs
        if self.numJobs <= 0:
            raise ValueError("Number of jobs must be greater than 0")

        # Build arguments
        self.buildArgs = dict()
        for a in args.build_args:
            (depName, _, arg) = a.partition(",")
            if not depName or not arg:
                raise ValueError("Invalid argument for --build-args: {}"
                                 .format(a))
            if depName.lower() not in AllDependenciesByName:
                raise ValueError("Invalid library for --build-args: {}"
                                 .format(depName))

            self.buildArgs.setdefault(depName.lower(), []).append(arg)

        # Build python info
        self.build_python_info = dict()
        if args.build_python_info:
            self.build_python_info['PYTHON_EXECUTABLE'] = args.build_python_info[0]
            self.build_python_info['PYTHON_INCLUDE_DIR'] = args.build_python_info[1]
            self.build_python_info['PYTHON_LIBRARY'] = args.build_python_info[2]
            self.build_python_info['PYTHON_VERSION'] = args.build_python_info[3]

        # Build type
        self.buildDebug = (args.build_variant == BUILD_DEBUG)
        self.buildRelease = (args.build_variant == BUILD_RELEASE)
        self.buildRelWithDebug = (args.build_variant == BUILD_RELWITHDEBUG)

        self.debugPython = args.debug_python

        self.buildShared = (args.build_type == SHARED_LIBS)
        self.buildMonolithic = (args.build_type == MONOLITHIC_LIB)

        # Build target and code signing
        if MacOS():
            self.buildTarget = args.build_target
            apple_utils.SetTarget(self, self.buildTarget)

            self.macOSCodesign = \
                (args.macos_codesign if hasattr(args, "macos_codesign")
                 else False)
        else:
            self.buildTarget = ""

        self.useCXX11ABI = \
            (args.use_cxx11_abi if hasattr(args, "use_cxx11_abi") else None)
        self.safetyFirst = args.safety_first

        # Dependencies that are forced to be built
        self.forceBuildAll = args.force_all
        self.forceBuild = [dep.lower() for dep in args.force_build]

        # Optional components
        self.buildTests = args.build_tests
        self.buildDocs = args.build_docs
        self.buildPython = args.build_python
        self.buildExamples = args.build_examples
        self.buildTutorials = args.build_tutorials
        self.buildTools = args.build_tools

    def GetBuildArguments(self, dep):
        return self.buildArgs.get(dep.name.lower(), [])
       
    def ForceBuildDependency(self, dep):
        # Never force building a Python dependency, since users are required
        # to build these dependencies themselves.
        if type(dep) is PythonDependency:
            return False
        return self.forceBuildAll or dep.name.lower() in self.forceBuild

try:
    context = InstallContext(args)
except Exception as e:
    PrintError(str(e))
    sys.exit(1)

verbosity = args.verbosity

# Augment PATH on Windows so that 3rd-party dependencies can find libraries
# they depend on. In particular, this is needed for building IlmBase/OpenEXR.
extraPaths = []
extraPythonPaths = []
if Windows():
    extraPaths.append(os.path.join(context.instDir, "lib"))
    extraPaths.append(os.path.join(context.instDir, "bin"))

if extraPaths:
    paths = os.environ.get('PATH', '').split(os.pathsep) + extraPaths
    os.environ['PATH'] = os.pathsep.join(paths)

if extraPythonPaths:
    paths = os.environ.get('PYTHONPATH', '').split(os.pathsep) + extraPythonPaths
    os.environ['PYTHONPATH'] = os.pathsep.join(paths)

# Determine list of dependencies that are required based on options
# user has selected.
requiredDependencies = [BOOST]

dependenciesToBuild = []
for dep in requiredDependencies:
    if context.ForceBuildDependency(dep) or not dep.Exists(context):
        if dep not in dependenciesToBuild:
            dependenciesToBuild.append(dep)

# Verify toolchain needed to build required dependencies
if (not which("g++") and
    not which("clang") and
    not GetXcodeDeveloperDirectory() and
    not GetVisualStudioCompilerAndVersion()):
    PrintError("C++ compiler not found -- please install a compiler")
    sys.exit(1)

# Error out if a 64bit version of python interpreter is not being used
isPython64Bit = (ctypes.sizeof(ctypes.c_voidp) == 8)
if not isPython64Bit:
    PrintError("64bit python not found -- please install it and adjust your"
               "PATH")
    sys.exit(1)

if which("cmake"):
    # Check cmake minimum version requirements
    pyInfo = GetPythonInfo(context)
    pyVer = (int(pyInfo[3].split('.')[0]), int(pyInfo[3].split('.')[1]))
    if context.buildPython and pyVer >= (3, 10):
        # Python 3.10 is not supported prior to 3.24
        cmake_required_version = (3, 24)
    elif IsVisualStudio2022OrGreater():
        # Visual Studio 2022 is not supported prior to 3.24
        cmake_required_version = (3, 24)
    elif Windows():
        # Visual Studio 2017 and 2019 are verified to work correctly with 3.14
        cmake_required_version = (3, 14)
    elif MacOS():
        # Apple Silicon is not supported prior to 3.19
        cmake_required_version = (3, 19)
    else:
        # Linux, and vfx platform CY2020, are verified to work correctly with 3.14
        cmake_required_version = (3, 14)

    cmake_version = GetCMakeVersion()
    if not cmake_version:
        PrintError("Failed to determine CMake version")
        sys.exit(1)

    if cmake_version < cmake_required_version:
        def _JoinVersion(v):
            return ".".join(str(n) for n in v)
        PrintError("CMake version {req} or later required to build USD, "
                   "but version found was {found}".format(
                       req=_JoinVersion(cmake_required_version),
                       found=_JoinVersion(cmake_version)))
        sys.exit(1)
else:
    PrintError("CMake not found -- please install it and adjust your PATH")
    sys.exit(1)

if context.buildDocs:
    if not which("doxygen"):
        PrintError("doxygen not found -- please install it and adjust your PATH")
        sys.exit(1)
        
    if not which("dot"):
        PrintError("dot not found -- please install graphviz and adjust your "
                   "PATH")
        sys.exit(1)

# Summarize
summaryMsg = """
Building with settings:
  USD source directory          {usdSrcDir}
  USD install directory         {usdInstDir}
  3rd-party source directory    {srcDir}
  3rd-party install directory   {instDir}
  Build directory               {buildDir}
  CMake generator               {cmakeGenerator}
  CMake toolset                 {cmakeToolset}
  Downloader                    {downloader}

  Building                      {buildType}
"""

if context.useCXX11ABI is not None:
    summaryMsg += """\
    Use C++11 ABI               {useCXX11ABI}
"""

summaryMsg += """
  Dependencies                  {dependencies}"""

if context.buildArgs:
    summaryMsg += """
  Build arguments               {buildArgs}"""

def FormatBuildArguments(buildArgs):
    s = ""
    for depName in sorted(buildArgs.keys()):
        args = buildArgs[depName]
        s += """
                                {name}: {args}""".format(
            name=AllDependenciesByName[depName].name,
            args=" ".join(args))
    return s.lstrip()

if args.dry_run:
    sys.exit(0)

# Scan for any dependencies that the user is required to install themselves
# and print those instructions first.
pythonDependencies = \
    [dep for dep in dependenciesToBuild if type(dep) is PythonDependency]
if pythonDependencies:
    for dep in pythonDependencies:
        Print(dep.getInstructions())
    sys.exit(1)

# Ensure directory structure is created and is writable.
for dir in [context.usdInstDir, context.instDir, context.srcDir, 
            context.buildDir]:
    try:
        if os.path.isdir(dir):
            testFile = os.path.join(dir, "canwrite")
            open(testFile, "w").close()
            os.remove(testFile)
        else:
            os.makedirs(dir)
    except Exception as e:
        PrintError("Could not write to directory {dir}. Change permissions "
                   "or choose a different location to install to."
                   .format(dir=dir))
        sys.exit(1)

try:
    # Download and install 3rd-party dependencies, followed by USD.
    for dep in dependenciesToBuild:
        PrintStatus("Installing {dep}...".format(dep=dep.name))
        dep.installer(context, 
                      buildArgs=context.GetBuildArguments(dep),
                      force=context.ForceBuildDependency(dep))
except Exception as e:
    PrintError(str(e))
    sys.exit(1)

# Done. Print out a final status message.
requiredInPythonPath = set([
    os.path.join(context.usdInstDir, "lib", "python")
])
requiredInPythonPath.update(extraPythonPaths)

requiredInPath = set([
    os.path.join(context.usdInstDir, "bin")
])
requiredInPath.update(extraPaths)

if Windows():
    requiredInPath.update([
        os.path.join(context.usdInstDir, "lib"),
        os.path.join(context.instDir, "bin"),
        os.path.join(context.instDir, "lib")
    ])

if MacOS():
    if context.macOSCodesign:
        apple_utils.Codesign(context.usdInstDir, verbosity > 1)

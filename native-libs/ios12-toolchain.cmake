# CMake toolchain for Linux -> iOS 12.0 arm64 cross-compilation (Clang + cctools-port)
# Usage:
#   cmake -B build-ios12 -DCMAKE_TOOLCHAIN_FILE=/path/to/oldcook/native-libs/ios12-toolchain.cmake \
#         -DIOS_SDK_ROOT=/path/to/oldcook/sdks/iPhoneOS14.5.sdk \
#         -DCCTOOLS_BIN=/path/to/cctools-port/bin

set(CMAKE_SYSTEM_NAME iOS)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_OSX_ARCHITECTURES "arm64" CACHE STRING "Target iOS architecture")
set(CMAKE_OSX_DEPLOYMENT_TARGET "12.0" CACHE STRING "Minimum iOS deployment version")

if(NOT DEFINED IOS_SDK_ROOT)
  if(DEFINED ENV{IOS_SDK_ROOT})
    set(IOS_SDK_ROOT "$ENV{IOS_SDK_ROOT}")
  else()
    set(IOS_SDK_ROOT "${CMAKE_CURRENT_LIST_DIR}/../sdks/iPhoneOS14.5.sdk")
  endif()
endif()

if(NOT DEFINED CCTOOLS_BIN AND DEFINED ENV{CCTOOLS_BIN})
  set(CCTOOLS_BIN "$ENV{CCTOOLS_BIN}")
endif()

set(CMAKE_OSX_SYSROOT "${IOS_SDK_ROOT}" CACHE PATH "iOS SDK sysroot")
set(CMAKE_C_COMPILER clang)
set(CMAKE_CXX_COMPILER clang++)

set(_IOS12_TARGET_FLAGS "--target=arm64-apple-ios12.0 -isysroot ${IOS_SDK_ROOT} -miphoneos-version-min=12.0")
if(DEFINED CCTOOLS_BIN)
  set(_IOS12_TARGET_FLAGS "${_IOS12_TARGET_FLAGS} -B${CCTOOLS_BIN}")
  set(CMAKE_AR "${CCTOOLS_BIN}/arm64-apple-darwin14-ar" CACHE FILEPATH "Archiver")
  set(CMAKE_RANLIB "${CCTOOLS_BIN}/arm64-apple-darwin14-ranlib" CACHE FILEPATH "Ranlib")
  set(CMAKE_INSTALL_NAME_TOOL "${CCTOOLS_BIN}/arm64-apple-darwin14-install_name_tool" CACHE FILEPATH "install_name_tool")
endif()

set(CMAKE_C_FLAGS_INIT "${_IOS12_TARGET_FLAGS}")
set(CMAKE_CXX_FLAGS_INIT "${_IOS12_TARGET_FLAGS}")
set(CMAKE_ASM_FLAGS_INIT "${_IOS12_TARGET_FLAGS}")
set(CMAKE_EXE_LINKER_FLAGS_INIT "${_IOS12_TARGET_FLAGS}")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "${_IOS12_TARGET_FLAGS}")

set(CMAKE_FIND_ROOT_PATH "${IOS_SDK_ROOT}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

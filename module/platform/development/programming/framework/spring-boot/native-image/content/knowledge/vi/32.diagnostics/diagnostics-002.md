# Thiếu C compiler, linker, header hoặc thư viện hệ thống

## 1. Vì sao Native Image cần toolchain C/C++?

Build ứng dụng Spring Boot thành GraalVM Native Image không chỉ là biên dịch source Java. Spring AOT chuẩn bị mã khởi tạo và metadata; Native Image phân tích reachability, tạo mã máy và liên kết thành executable cho hệ điều hành/kiến trúc đích. Quá trình này cần một toolchain native phù hợp, thường gồm C compiler, linker, system headers và các thư viện phát triển của nền tảng.

Vì vậy, dự án có thể compile Java và chạy JAR thành công nhưng native build vẫn thất bại vì máy thiếu GCC/Clang, linker, Windows SDK, Xcode Command Line Tools hoặc thư viện hệ thống. Đây là lỗi môi trường build, không nhất thiết là lỗi Spring AOT hay RuntimeHints.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, bài học này giúp nhận diện từng thành phần toolchain, cài đặt đúng theo Linux/Windows/macOS, kiểm tra PATH và biến môi trường, phân biệt lỗi compiler với lỗi dependency, và chuẩn hóa native build trên CI. Yêu cầu cụ thể thay đổi theo GraalVM distribution, version, OS và target architecture; luôn đối chiếu tài liệu đúng phiên bản.

## 2. Các thành phần của native toolchain

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| C compiler | Biên dịch mã C và phần runtime/native support | GCC, Clang, MSVC |
| Linker | Kết hợp object files và libraries thành executable | GNU ld, lld, Apple ld, MSVC linker |
| Assembler | Chuyển assembly thành object code | GNU as, integrated assembler |
| System headers | Khai báo API/struct/constants của OS và thư viện | libc headers, Windows SDK headers |
| System libraries | Cung cấp implementation để linker liên kết | libc, libpthread hoặc runtime libraries tùy nền tảng |
| Development packages | Cung cấp headers, linker metadata và symlinks | libc-dev, zlib-devel |
| Build utilities | Công cụ phụ trợ của toolchain | make, pkg-config, archiver |
| SDK/platform tools | API và libraries của nền tảng đích | Windows SDK, Xcode SDK |

Không phải mọi project cần cài riêng tất cả các gói trong bảng. Một số distribution cung cấp hoặc yêu cầu toolchain cụ thể; một số native build dùng compiler/linker từ hệ thống. Hãy kiểm tra prerequisite chính thức trước khi cài package.

## 3. Phân biệt Java compiler với C compiler

JDK có `javac` để biên dịch Java source thành bytecode. Việc `javac -version` chạy được không chứng minh có C compiler hoặc linker.

Các lệnh kiểm tra khác nhau:

```bash
java -version
javac -version
native-image --version
cc --version
gcc --version
clang --version
ld --version
```

Một số lệnh có thể không tồn tại nếu distribution không dùng tool đó. Ví dụ máy dùng Clang có thể không có GCC; macOS có linker của Apple chứ không dùng GNU ld. Trên Windows, MSVC toolchain được kiểm tra bằng Developer Command Prompt và `cl.exe`, không phải `gcc`.

Hãy xác định compiler mà Native Image thực sự phát hiện qua build log. Không cài đồng thời nhiều compiler một cách tùy tiện rồi hy vọng build chọn đúng.

## 4. Đọc thông báo lỗi để xác định thiếu thành phần nào

Một số lỗi thường gặp:

| Thông báo hoặc dấu hiệu | Thành phần có thể thiếu |
|---|---|
| `C compiler not found` | GCC/Clang/MSVC hoặc compiler không nằm trong PATH |
| `Unable to execute gcc` | Compiler không cài, sai PATH hoặc môi trường shell không đầy đủ |
| `linker command failed` | Linker thiếu, sai toolchain hoặc không tương thích |
| `ld: cannot find -l...` | Thiếu library hoặc development package |
| `fatal error: ...h: No such file` | Thiếu system/development headers |
| `cannot find crt1.o` / `Scrt1.o` | Thiếu C runtime development files hoặc linker search path |
| `undefined reference to ...` | Thiếu library, sai thứ tự/link flags hoặc ABI mismatch |
| `cannot find -lz` | Thiếu zlib development library/linker metadata |
| `Windows SDK not found` | Thiếu hoặc không chọn đúng Windows SDK |
| `xcrun: error: invalid active developer path` | Xcode Command Line Tools chưa cài/chưa chọn |
| `unsupported target architecture` | Toolchain/SDK không hỗ trợ target đã chọn |

Thông báo có thể khác theo GraalVM version và linker. Tìm lỗi đầu tiên trong build log, không chỉ dòng cuối “build failed”. Các lỗi sau có thể chỉ là hệ quả của một prerequisite ban đầu bị thiếu.

## 5. Linux: cài compiler và linker cơ bản

Trên Debian/Ubuntu, bộ công cụ thường dùng là build-essential:

```bash
sudo apt-get update
sudo apt-get install -y build-essential
```

Gói này thường cài GCC/G++, make và một số thành phần build cơ bản. Tùy Native Image prerequisites và dependency, có thể cần thêm development package như zlib:

```bash
sudo apt-get install -y zlib1g-dev
```

Trên Fedora/RHEL-family, các package group tương đương có thể gồm:

```bash
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y zlib-devel
```

Tên package và package manager thay đổi theo distribution/version. Một số bản Enterprise Linux yêu cầu bật repository tương ứng hoặc cài package compiler riêng. Kiểm tra tài liệu GraalVM và OS image đang sử dụng.

Không chạy lệnh cài package trên production runtime image chỉ để sửa build. C compiler và header thường thuộc builder stage/CI runner, không cần đưa vào final container image.

## 6. Linux: kiểm tra compiler, linker và headers

Sau khi cài toolchain:

```bash
which cc
which gcc
which ld
cc --version
gcc --version
ld --version
```

Kiểm tra compiler có thể compile và link một chương trình tối thiểu:

```bash
cat > /tmp/toolchain-check.c <<'EOF'
#include <stdio.h>

int main(void) {
    puts("native toolchain ready");
    return 0;
}
EOF

cc /tmp/toolchain-check.c -o /tmp/toolchain-check
/tmp/toolchain-check
```

Nếu compiler chạy nhưng không tìm thấy `stdio.h`, system headers/development package có thể thiếu. Nếu compile thành công nhưng link fail, xem linker, C runtime files và library search paths.

Đây là smoke test cho C toolchain. Nó không chứng minh mọi prerequisite của GraalVM Native Image hoặc dependency cụ thể đã có; native build thực tế vẫn là bước xác nhận cuối.

## 7. zlib và các system development libraries

Một số Native Image toolchain hoặc dependency có thể yêu cầu zlib development files. Cần phân biệt:
- Runtime library: shared object dùng khi executable chạy.
- Development package: header và linker metadata cần khi build.
- Static library: archive `.a` nếu build/link mode cần.
- Runtime package: package cung cấp file cần có trong final image.

Ví dụ trên Debian/Ubuntu là `zlib1g-dev`; trên Fedora/RHEL thường là `zlib-devel`. Tên và yêu cầu phụ thuộc OS và GraalVM version.

Không cài một danh sách thư viện theo thói quen nếu compiler không yêu cầu. Đọc lỗi `-lxxx` hoặc missing header, xác định package cung cấp file tương ứng, rồi cài đúng development package. Sau đó xác minh linker tìm thấy library trong đúng architecture và sysroot.

## 8. pkg-config và library search paths

Một số native dependency sử dụng `pkg-config` để lấy compiler/linker flags:

```bash
pkg-config --version
pkg-config --cflags --libs zlib
```

Nếu lệnh không tìm thấy package, có thể thiếu development package hoặc file `.pc` không nằm trong search path. Biến môi trường `PKG_CONFIG_PATH` bổ sung thư mục metadata, nhưng không nên đặt một path tùy ý trước khi xác định vị trí package.

Các biến như `CPATH`, `C_INCLUDE_PATH`, `LIBRARY_PATH` hoặc `LD_LIBRARY_PATH` có thể ảnh hưởng compiler/linker/runtime resolution. Dùng chúng có chủ đích, ghi lại trong CI và tránh global overrides làm build local khác CI.

Không dùng `LD_LIBRARY_PATH` để chữa lỗi linker ở build time nếu vấn đề thực tế là thiếu development package. Linker search path và dynamic loader runtime path là hai giai đoạn khác nhau.

## 9. Linux: kiểm tra kiến trúc và sysroot

Toolchain cần tạo binary cho target phù hợp. Kiểm tra:

```bash
uname -m
cc -dumpmachine
file /usr/bin/cc
```

Nếu build container `linux/amd64` nhưng muốn tạo artifact `linux/arm64`, compiler host-native thông thường có thể không tự cross-compile. Cần toolchain/sysroot và cấu hình cross-compilation được GraalVM/Native Image hỗ trợ cho target đó.

Không nhầm architecture của host với architecture của container builder hoặc target image. Trong CI multi-arch, ghi rõ platform cho từng job và xác minh ELF machine type của executable.

## 10. Windows: Visual Studio Build Tools và Windows SDK

Trên Windows, Native Image thường cần Microsoft C/C++ toolchain tương ứng với GraalVM release, bao gồm MSVC compiler/linker và Windows SDK. Cài Visual Studio hoặc Visual Studio Build Tools với workload **Desktop development with C++** và thành phần Windows SDK phù hợp.

Sau khi cài, mở **x64 Native Tools Command Prompt for Visual Studio** hoặc Developer PowerShell tương ứng. Kiểm tra:

```powershell
cl
where.exe cl
where.exe link
where.exe rc
```

`cl.exe` là compiler, `link.exe` là linker, còn `rc.exe` là resource compiler thường đi kèm SDK. Các tool phải đến từ cùng toolchain/architecture mong muốn.

Mở terminal thông thường có thể không có các biến môi trường Visual Studio như INCLUDE/LIB/PATH. Nếu build fail vì không tìm thấy compiler dù đã cài, thử đúng Developer Command Prompt trước khi cài lại.

## 11. Windows: kiểm tra SDK headers và libraries

MSVC cần Windows SDK headers/libraries. Nếu thông báo thiếu `windows.h`, linker không tìm thấy system library hoặc SDK version, kiểm tra Visual Studio Installer:

- Desktop development with C++ workload.
- MSVC toolset phù hợp architecture.
- Windows 10/11 SDK version được hỗ trợ.
- CMake/Ninja nếu build workflow yêu cầu.
- Environment variables do Developer Command Prompt thiết lập.

Không tự copy thư mục SDK vào PATH/INCLUDE bằng tay nếu Visual Studio đã có script môi trường chính thức. Dùng installer và command prompt tương ứng để tránh trộn SDK versions.

Native Image trên Windows có các prerequisite cụ thể theo GraalVM distribution/version. Kiểm tra tài liệu chính thức trước khi chọn Visual Studio toolset; không suy ra mọi JDK/GraalVM release đều hỗ trợ cùng compiler version.

## 12. macOS: Xcode Command Line Tools

Trên macOS, toolchain native thường đến từ Xcode hoặc Xcode Command Line Tools, gồm Clang, linker và macOS SDK headers/libraries.

Cài đặt nếu chưa có:

```bash
xcode-select --install
```

Kiểm tra:

```bash
xcode-select -p
xcrun --find clang
clang --version
xcrun --show-sdk-path
```

Nếu developer directory trỏ tới Xcode cũ hoặc không tồn tại, chọn lại đường dẫn Xcode/Command Line Tools bằng cơ chế `xcode-select` theo hướng dẫn Apple. Không tự đặt SDKROOT đến một SDK không tương thích.

macOS có cả Intel và Apple Silicon. Kiểm tra architecture của GraalVM, JDK, compiler và target binary; tránh trộn x86_64 toolchain với arm64 build ngoài workflow cross-compilation được hỗ trợ.

## 13. PATH và biến môi trường của CI

Một lỗi thường gặp là compiler đã được cài nhưng job native không nhìn thấy do PATH khác shell cài đặt. Kiểm tra ngay trong cùng job và cùng step chạy build:

Linux/macOS:

```bash
command -v cc
command -v gcc
command -v clang
printf '%s\n' "$PATH"
```

Windows PowerShell:

```powershell
Get-Command cl -ErrorAction SilentlyContinue
Get-Command link -ErrorAction SilentlyContinue
$env:PATH
```

Không chỉ kiểm tra trên runner host nếu build chạy trong container. Compiler cần tồn tại trong chính build environment nơi Native Image compiler thực thi. Với CI nhiều job, mỗi job có filesystem/environment riêng; cài toolchain ở job trước không tự làm nó có mặt ở job sau.

## 14. Phân biệt lỗi compiler với lỗi linker

Compiler dịch source thành object file; linker kết hợp object files và libraries thành executable. Dấu hiệu phân biệt:

- Compiler không được tìm thấy: lỗi xảy ra trước khi compile.
- Header không tìm thấy: compiler bắt đầu nhưng preprocessing/compile fail.
- Symbol undefined: object đã được tạo nhưng linker không tìm được implementation.
- Library not found: linker không tìm được file library.
- ABI mismatch: library được tìm thấy nhưng symbol/architecture/version không tương thích.

Khi linker báo `undefined reference`, tìm symbol và library cần cung cấp nó. Kiểm tra thứ tự library arguments nếu dùng static linking, architecture và ABI. Không thêm library ngẫu nhiên hoặc tắt kiểm tra linker để vượt qua lỗi.

## 15. Kiểm tra native toolchain mà GraalVM thực sự sử dụng

Một máy có nhiều compiler có thể khiến build dùng nhầm toolchain. Kiểm tra:
- GraalVM distribution/version và native-image executable path.
- Compiler được Native Image phát hiện trong build log.
- PATH/INCLUDE/LIB/SDKROOT trong process build.
- Target architecture và linker.
- Compiler version có nằm trong support range của GraalVM release không.

Trên Linux có thể kiểm tra:

```bash
command -v native-image
command -v cc
command -v ld
native-image --version
```

Trên Windows:

```powershell
Get-Command native-image
Get-Command cl
Get-Command link
native-image --version
```

Nếu plugin Maven/Gradle chạy trong daemon hoặc process khác, bảo đảm daemon được khởi động từ môi trường có toolchain đúng. Sau khi thay PATH/toolchain, dừng/restart daemon build để process cũ không giữ environment cũ.

## 16. Toolchain trong Docker builder stage

Nếu native build chạy trong Docker, compiler và development packages phải nằm trong builder stage:

```dockerfile
FROM build-image AS build
WORKDIR /workspace

# Cài compiler và development packages theo OS của builder.
# Sau đó chạy Maven/Gradle và Native Image build.
COPY . .
RUN ./mvnw -Pnative -DskipTests package

FROM runtime-image AS runtime
WORKDIR /app
COPY --from=build /workspace/target/orders-service /app/orders-service
USER 10001:10001
ENTRYPOINT ["/app/orders-service"]
```

Đây là cấu trúc minh họa; `build-image` phải có GraalVM và prerequisite native toolchain phù hợp. Không copy compiler, header và package manager vào final runtime image nếu ứng dụng không cần chúng lúc chạy.

Builder và runtime có thể khác nhau, nhưng binary ABI, libc và shared library dependencies phải tương thích. Thành công ở builder không bảo đảm final image có đủ runtime libraries; kiểm tra image cuối riêng.

## 17. CI runner: chuẩn hóa prerequisite

Một job native ổn định nên có bước kiểm tra toolchain trước khi chạy Maven/Gradle:

```bash
set -euo pipefail

java -version
native-image --version
cc --version
ld --version

./mvnw -Pnative -DskipTests package
```

Đây là ví dụ cho Linux runner có `cc` và `ld`; trên macOS dùng `clang`/Apple linker, trên Windows dùng MSVC checks. Không dùng cùng script kiểm tra compiler cho mọi OS mà không có nhánh platform phù hợp.

Pin builder image hoặc runner image theo version. Nếu cài package trong job, ghi package version và repository source. Điều này giúp native build có thể tái lập và hỗ trợ điều tra khi runner image được cập nhật.

## 18. Chẩn đoán lỗi thiếu header hoặc library

Khi gặp lỗi cụ thể:

1. Lấy dòng lỗi đầu tiên có tên header/library.
2. Xác định compiler/linker đang chạy và target architecture.
3. Tìm package OS cung cấp file đó.
4. Cài development package trong builder/CI environment.
5. Xác minh file header và library tồn tại.
6. Kiểm tra compiler/linker search path.
7. Chạy C smoke test tối thiểu nếu cần.
8. Chạy lại native build và lưu log.

Ví dụ Linux:

```bash
# Tìm package theo tên file trên Debian-family nếu apt-file đã được cài/cập nhật
apt-file search zlib.h
```

Công cụ tra package phụ thuộc distribution và repository. Không cài runtime package khi compiler cần header; cần development package tương ứng.

Nếu thiếu symbol, package có thể đã được cài nhưng version/ABI không phù hợp. Xác minh library version và architecture trước khi thay đổi linker flags.

## 19. Các lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Java compile pass, native build báo compiler missing | JDK có javac nhưng chưa có C toolchain | Cài compiler/linker đúng OS |
| GCC có trên host nhưng job không thấy | Build chạy trong container/job khác hoặc PATH khác | Kiểm tra trong đúng process environment |
| `stdio.h` không tìm thấy | Thiếu libc development headers | Cài development package |
| `zlib.h` không tìm thấy | Thiếu zlib development package | Cài package tương ứng OS |
| `cannot find -lz` | Thiếu zlib library/linker metadata | Cài zlib development package, kiểm tra architecture |
| `crt1.o` thiếu | C runtime development files hoặc sysroot không đầy đủ | Cài toolchain/libc dev và kiểm tra sysroot |
| Windows không tìm thấy `cl.exe` | Terminal không được khởi tạo MSVC environment | Dùng Developer Command Prompt |
| macOS invalid developer path | Xcode tools chưa cài/chọn sai | Cài/chọn Command Line Tools |
| Linker undefined symbols | Thiếu library, ABI mismatch hoặc sai link flags | Xác định symbol/provider và version |
| Binary build được nhưng final container fail | Runtime shared libraries/loader thiếu | Kiểm tra ELF và final image |

## 20. Bài thực hành: chuẩn bị toolchain cho native build

**Bối cảnh:** Order API build JAR thành công trên CI nhưng native job fail vì compiler hoặc system library chưa có.

**Bước 1 — Xác định nền tảng.** Ghi OS, architecture, GraalVM distribution/version và build tool version.

**Bước 2 — Kiểm tra compiler/linker.** Chạy các lệnh phù hợp: `cc/gcc/clang/ld`, MSVC `cl/link`, hoặc Xcode `clang/xcrun`.

**Bước 3 — Kiểm tra headers.** Tạo C smoke test có `stdio.h`; nếu lỗi, kiểm tra development headers.

**Bước 4 — Xử lý library thiếu.** Đọc thông báo `-l...` hoặc header cụ thể, cài development package đúng distribution/architecture.

**Bước 5 — Kiểm tra môi trường build.** Xác minh PATH, INCLUDE/LIB hoặc SDK path trong cùng job/container chạy Native Image.

**Bước 6 — Chạy native build.** Chạy Maven/Gradle native task với toolchain đã pin; lưu build log và compiler identity.

**Bước 7 — Kiểm tra executable.** Xác nhận architecture, loader và shared library dependencies.

**Bước 8 — Kiểm tra final image.** Chạy executable trong runtime image và xác nhận các thư viện runtime cần thiết đã có.

Tiêu chí hoàn thành: compiler/linker/headers đúng nền tảng; Native Image nhận đúng toolchain; native build hoàn tất; binary đúng architecture; final image chạy được với runtime dependencies tối thiểu.

## 21. Kết luận

Native Image build cần toolchain native bên cạnh JDK: C compiler, linker, system headers và development libraries phù hợp. Linux thường dùng GCC/Clang cùng development packages; Windows cần MSVC và Windows SDK; macOS dùng Xcode Command Line Tools. Phiên bản và prerequisite cụ thể phải theo GraalVM distribution/release đang sử dụng.

Khi build fail, phân biệt lỗi compiler, header, linker, library, ABI và PATH. Kiểm tra ngay trong đúng runner/container thực hiện native build, cài development packages ở builder stage, rồi xác minh executable và final runtime image riêng. Một JAR build thành công chỉ chứng minh Java pipeline hoạt động; nó không chứng minh native toolchain đã sẵn sàng.

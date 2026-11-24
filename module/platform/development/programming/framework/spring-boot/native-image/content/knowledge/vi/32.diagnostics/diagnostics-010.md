# Binary không chạy do sai kiến trúc, libc hoặc thư viện liên kết

Ứng dụng Spring Boot chạy tốt trong builder container nhưng dừng ngay khi chuyển sang runtime container thường gặp lỗi ở tầng hệ điều hành: executable được build cho CPU khác, dynamic loader không tồn tại, glibc không tương thích hoặc thiếu shared library. Đây là nhóm lỗi của **native binary và môi trường Linux**, khác với lỗi Spring AOT như thiếu reflection/resource hints.

Native Image tạo executable phụ thuộc vào hệ điều hành, kiến trúc CPU, ABI và cách liên kết thư viện. Vì vậy, build thành công chưa chứng minh binary chạy được trên image cuối. Bài học này hướng dẫn chẩn đoán từ ELF header, interpreter, dynamic dependencies đến glibc/musl và CPU instruction set; đồng thời chỉ cách chọn builder/runtime image, kiểm tra final container và sửa lỗi có hệ thống.

Bài học thuộc chương **Chẩn đoán** của module **`SPRING_BOOT_NATIVE_IMAGE`**. Module hướng dẫn biên dịch Spring Boot bằng Spring AOT thành GraalVM Native Image để đánh giá startup và memory, thực hành Maven/Gradle, cấu hình reflection/resource, kiểm thử tương thích, đóng gói container và vận hành bản native.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt lỗi sai định dạng/kiến trúc ELF với lỗi thiếu dynamic loader hoặc shared library.
- Xác định kiến trúc của host, container image và executable.
- Đọc ELF header, program interpreter, `DT_NEEDED`, RPATH/RUNPATH và symbol version.
- Phân tích `Exec format error`, `No such file or directory`, `GLIBC_2.xx not found`, lỗi thiếu shared library và `Illegal instruction`.
- Phân biệt executable liên kết động, mostly-static và fully-static.
- Chọn glibc hay musl runtime theo cách binary được build.
- Kiểm tra CPU instruction set và lựa chọn `-march` phù hợp.
- Tạo binary riêng cho `linux/amd64` và `linux/arm64`.

## 2. Bốn lớp tương thích của native executable

Một Linux native executable cần thỏa mãn đồng thời bốn điều kiện:

| Lớp | Điều cần khớp | Ví dụ lỗi |
|---|---|---|
| Định dạng và kiến trúc | ELF format, 32/64-bit, CPU architecture | `Exec format error`, `wrong ELF class` |
| Dynamic loader | Đường dẫn interpreter trong ELF phải tồn tại | File có thật nhưng báo `No such file or directory` |
| ABI và libc | Binary tương thích glibc/musl và symbol version runtime | `GLIBC_2.xx not found`, lỗi relocation |
| Shared libraries và CPU features | Các `.so` cần thiết và instruction set phải có | `libfoo.so: cannot open`, `Illegal instruction` |

Container image đóng gói filesystem và khai báo platform, nhưng container vẫn dùng kernel của host. Vì vậy, binary phải phù hợp với kiến trúc CPU và khả năng thực thi của host hoặc có cơ chế emulation. Docker có thể chọn biến thể image theo platform, nhưng không tự sửa binary sai kiến trúc đã được copy vào image.

~~~mermaid
flowchart TD
    A["Binary không khởi chạy"] --> B{"ELF đúng kiến trúc?"}
    B -- "Không" --> C["Build đúng target CPU/OS"]
    B -- "Có" --> D{"PT_INTERP tồn tại?"}
    D -- "Không" --> E["Chọn loader/base image phù hợp"]
    D -- "Có" --> F{"Libc và symbol version khớp?"}
    F -- "Không" --> G["Khớp glibc/musl hoặc rebuild"]
    F -- "Có" --> H{"Đủ shared libraries?"}
    H -- "Không" --> I["Cài đúng runtime library"]
    H -- "Có" --> J{"CPU hỗ trợ instruction?"}
    J -- "Không" --> K["Rebuild với -march phù hợp"]
    J -- "Có" --> L["Kiểm tra cấu hình và lỗi ứng dụng"]
~~~

## 3. Xác định kiến trúc host, image và executable

Trên Linux host:

~~~bash
uname -m
~~~

Giá trị thường gặp:

| `uname -m` | Docker platform | ELF machine |
|---|---|---|
| `x86_64` | `linux/amd64` | x86-64 |
| `aarch64` | `linux/arm64` | AArch64 |

Kiểm tra image và Docker daemon:

~~~bash
docker image inspect --format '{{.Os}}/{{.Architecture}}' orders-service:native
docker info --format '{{.OSType}}/{{.Architecture}}'
~~~

Kiểm tra executable:

~~~bash
file ./orders-service
readelf -h ./orders-service
~~~

Trong ELF header, chú ý `Class` (ELF64/ELF32), `Data`, `Machine` và `Type`. Ví dụ output `ELF 64-bit ... x86-64` không thể chạy native trên ARM64; output `ARM aarch64` không thể chạy native trên x86-64.

Không suy luận kiến trúc từ tag image. Image đa kiến trúc có manifest list; Docker chọn biến thể theo host khi pull, nhưng binary được copy vào từng biến thể vẫn phải đúng kiến trúc.

## 4. Chẩn đoán `Exec format error`

Ví dụ:

~~~text
exec /app/orders-service: exec format error
~~~

Lỗi này thường cho biết kernel không thể thực thi file theo định dạng hoặc kiến trúc hiện tại. Nguyên nhân thường gặp:

- Binary được build cho `linux/amd64` nhưng runtime host là `linux/arm64`, hoặc ngược lại.
- Binary được tạo cho hệ điều hành khác như macOS/Windows.
- File bị hỏng, copy nhầm artifact hoặc không phải ELF executable.
- Host không có emulation cho foreign architecture.

Kiểm tra:

~~~bash
uname -m
file /app/orders-service
readelf -h /app/orders-service | grep -E 'Class:|Machine:'
docker image inspect --format '{{.Os}}/{{.Architecture}}' orders-service:native
~~~

Ưu tiên build binary trên runner có kiến trúc trùng với platform phát hành:

~~~bash
# Runner x86-64
docker buildx build --platform linux/amd64 -t orders-service:native-amd64 .

# Runner ARM64
docker buildx build --platform linux/arm64 -t orders-service:native-arm64 .
~~~

Docker Buildx hỗ trợ QEMU emulation, native builder nodes và cross-compilation. Native Image compile là bước nặng; chạy compiler dưới QEMU có thể chậm hoặc phụ thuộc toolchain. Với release, native builder node cho từng kiến trúc thường dễ kiểm soát hơn.

`--platform` chọn platform của image/build stage. Nó không tự biến executable đã build trên host thành binary cho target khác. Hãy kiểm tra `file` trên executable sau native compile.

Có thể chạy image amd64 trên host ARM64 nếu host đã cấu hình QEMU/binfmt:

~~~bash
docker run --rm --platform linux/amd64 orders-service:native-amd64
~~~

Emulation hữu ích cho kiểm tra tương thích cơ bản. Benchmark hiệu năng phải chạy trên CPU native vì QEMU làm thay đổi chi phí thực thi.

## 5. File tồn tại nhưng báo `No such file or directory`

Ví dụ:

~~~text
/app/orders-service: No such file or directory
~~~

trong khi `ls -l /app/orders-service` xác nhận file thực sự tồn tại. Với ELF liên kết động, kernel đọc segment `PT_INTERP` để tìm dynamic loader. Nếu loader được ghi trong binary không có trong runtime image, lệnh thực thi có thể báo file không tồn tại.

Đọc program headers:

~~~bash
readelf -l /app/orders-service | grep -A1 INTERP
~~~

Ví dụ:

~~~text
[Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]
~~~

Kiểm tra đường dẫn interpreter trong **runtime filesystem**:

~~~bash
ls -l /lib64/ld-linux-x86-64.so.2
~~~

Đây là ví dụ cho glibc x86-64; ARM64 dùng loader path khác. Không tạo symlink giả trỏ sang loader của libc khác kiến trúc hoặc ABI.

### Kiểm tra binary trong final image

Builder stage có thể có loader và thư viện mà final stage không có. Có thể copy executable từ image cuối để phân tích trên host:

~~~bash
docker create --name native-inspect orders-service:native
docker cp native-inspect:/app/orders-service ./orders-service-from-image
docker rm native-inspect
file ./orders-service-from-image
readelf -l ./orders-service-from-image | grep -A1 INTERP
~~~

Distroless và `scratch` thường không có shell, `ls` hoặc package manager. Dùng debug image hoặc container chẩn đoán có cùng root filesystem; đừng coi việc `docker exec ... sh` thất bại là lỗi của executable.

## 6. Hiểu glibc, musl và ABI

`libc` cung cấp các chức năng nền tảng như cấp phát bộ nhớ, xử lý chuỗi, thread và system-call wrappers. Hai họ libc phổ biến:

- **glibc:** dùng bởi Debian, Ubuntu, Oracle Linux, Red Hat Enterprise Linux và nhiều distro khác.
- **musl:** dùng bởi Alpine Linux.

Binary liên kết động với glibc thường cần glibc loader và symbol của glibc. Alpine dùng musl, nên không mặc định có loader hoặc ABI glibc mà binary yêu cầu. Binary build cho musl cũng không nên giả định sẽ chạy trên glibc nếu chưa xác minh.

### 6.1. Lỗi `GLIBC_2.xx not found`

Ví dụ:

~~~text
/app/orders-service: /lib64/libc.so.6:
version GLIBC_2.34 not found (required by /app/orders-service)
~~~

Binary cần symbol version glibc mới hơn phiên bản trong runtime. Nguyên nhân thường là builder dùng distro mới còn runtime dùng distro cũ.

Kiểm tra symbol version mà binary tham chiếu:

~~~bash
readelf --version-info /app/orders-service | grep GLIBC_
~~~

Kiểm tra glibc trong runtime:

~~~bash
ldd --version
~~~

Trên glibc-based runtime, `ldd --version` hiển thị phiên bản glibc. Trên musl-based image, đừng diễn giải output của loader như phiên bản glibc. Nếu runtime image tối giản không có công cụ này, dùng debug image hoặc kiểm tra package/version của libc theo cách phù hợp.

### 6.2. Sửa glibc mismatch

**Build trên baseline glibc thấp nhất cần hỗ trợ.** Nếu production chạy nhiều phiên bản distro, chọn builder tương thích baseline thấp nhất và kiểm thử trên tất cả runtime mục tiêu. Binary build trên glibc mới có thể yêu cầu symbol không tồn tại trên runtime cũ; build trên baseline cũ thường chạy được trên glibc mới hơn nếu các dependency khác cũng tương thích.

**Đồng bộ builder và runtime OS family/version.** Ví dụ cả hai cùng dựa trên Oracle Linux 9. Cách này giảm rủi ro ABI mismatch nhưng vẫn phải kiểm tra thư viện bổ sung.

**Cân nhắc mostly-static hoặc fully-static.** Mostly-static vẫn cần libc tương thích; fully-static với musl có thể bỏ phụ thuộc libc runtime. Xem phần 9 trước khi chọn.

Không khắc phục bằng cách copy `libc.so.6` hoặc dynamic loader tùy tiện từ builder vào runtime. Trộn glibc và loader khác phiên bản có thể gây lỗi ABI khó đoán.

## 7. Chẩn đoán thiếu shared library

Lỗi thường gặp:

~~~text
error while loading shared libraries: libfoo.so.1:
cannot open shared object file: No such file or directory
~~~

Binary tìm thấy dynamic loader nhưng loader không tìm thấy shared library cần thiết.

### 7.1. Liệt kê dependencies

Trên binary đáng tin cậy do pipeline của bạn tạo:

~~~bash
ldd ./orders-service
~~~

Ví dụ:

~~~text
linux-vdso.so.1
libz.so.1 => /lib64/libz.so.1
libc.so.6 => /lib64/libc.so.6
/lib64/ld-linux-x86-64.so.2
~~~

Nếu thấy `libfoo.so.1 => not found`, runtime image thiếu thư viện hoặc loader không tìm thấy nó trong các đường dẫn đã cấu hình.

**Lưu ý bảo mật:** không chạy `ldd` trên executable không đáng tin cậy. Một số implementation có thể gọi dynamic loader hoặc thực thi thành phần của binary. Với file không tin cậy, dùng phân tích tĩnh:

~~~bash
objdump -p ./unknown-binary | grep NEEDED
readelf -d ./unknown-binary | grep NEEDED
~~~

Các lệnh này cho biết `DT_NEEDED` trực tiếp; chúng không nhất thiết liệt kê toàn bộ dependency bắc cầu như `ldd`.

### 7.2. RPATH, RUNPATH và library search

Đọc các dynamic entries:

~~~bash
readelf -d ./orders-service | grep -E 'RPATH|RUNPATH|NEEDED'
~~~

Dynamic linker glibc tìm library dựa trên dependency path, `RPATH`/`RUNPATH`, `LD_LIBRARY_PATH`, cache của loader và thư mục mặc định. `RUNPATH` thường chỉ áp dụng cho dependency trực tiếp của object khai báo nó; dependency bắc cầu có thể cần cấu hình riêng.

Có thể bật trace loader trong môi trường glibc:

~~~bash
LD_DEBUG=libs ./orders-service
~~~

Lệnh này cho thấy dynamic linker tìm thư viện ở đâu và vì sao bỏ qua một đường dẫn. Chỉ dùng khi chẩn đoán vì output rất nhiều.

### 7.3. Sửa lỗi thiếu library

1. Xác định package runtime cung cấp đúng file `.so` bị thiếu.
2. Cài package đó trong final stage, hoặc copy thư viện theo chính sách đóng gói đã kiểm soát.
3. Đảm bảo architecture và ABI của thư viện khớp với executable.
4. Nếu dùng thư mục riêng, cấu hình RUNPATH/library path phù hợp hoặc dùng `ldconfig` trên glibc image có hỗ trợ.
5. Chạy lại kiểm tra trên final image, không chỉ builder.

Không copy toàn bộ `/usr/lib` từ builder sang runtime. Cách đó có thể kéo theo nhiều phiên bản thư viện xung đột. Cũng không đặt `LD_LIBRARY_PATH` toàn cục để che mọi lỗi; hãy thêm đúng package hoặc đường dẫn cần thiết.

## 8. Phân biệt glibc và musl trong container

Alpine nhỏ gọn nhưng dùng musl. Binary Native Image build mặc định trên glibc-based builder thường không chạy trực tiếp trên Alpine chỉ bằng cách copy file.

Triệu chứng có thể gồm:

- Dynamic loader path `/lib64/ld-linux-...` không tồn tại.
- `Error loading shared library ...`.
- `Error relocating ...: symbol not found`.
- Binary khởi chạy được nhưng một native dependency lỗi khi gọi.

Quy trình xử lý:

1. Dùng `file` và `readelf -l` xác định binary cần loader nào.
2. Kiểm tra runtime image có glibc hay musl.
3. Xác định native dependencies như JNI, database driver native, compression, crypto và thư viện C/C++.
4. Chọn runtime glibc phù hợp hoặc build binary theo musl toolchain.
5. Chạy integration tests trên đúng final image.

Không cho rằng gói compatibility của Alpine thay thế đầy đủ mọi phiên bản glibc. Các lớp tương thích có thể hữu ích cho một số ứng dụng, nhưng không bảo đảm mọi binary, loader path và native dependency đều tương thích.

## 9. Dynamic, mostly-static và fully-static Native Image

GraalVM Native Image mặc định tạo binary liên kết động. Tùy môi trường triển khai, có thể chọn:

| Kiểu liên kết | Cách hoạt động | Runtime cần gì? |
|---|---|---|
| Dynamic (mặc định) | Liên kết với shared libraries lúc chạy | Dynamic loader, libc và mọi `.so` cần thiết |
| Mostly-static | Liên kết tĩnh thư viện native ngoại trừ libc | Vẫn cần libc tương thích; có thể còn phụ thuộc `libstdc++`/`libgcc` |
| Fully-static | Liên kết tĩnh cả libc bằng musl | Không cần dynamic shared-library loader cho executable đó |

### 9.1. Fully-static với musl

Lệnh minh họa:

~~~bash
native-image --static --libc=musl \
  -jar application.jar \
  -o orders-service
~~~

Cần có musl toolchain và static libraries tương ứng trong builder. Kiểm tra tài liệu của GraalVM version đang dùng và giới hạn architecture trước khi áp dụng; tài liệu hiện hành ghi nhận musl chưa được hỗ trợ trên Linux AArch64.

Kiểm tra binary:

~~~bash
ldd ./orders-service
~~~

Với fully-static binary, output thường cho biết `not a dynamic executable`. Có thể triển khai trong image rất tối giản như `scratch` nếu ứng dụng không cần CA certificates, timezone database, file cấu hình, thư mục tạm hoặc runtime assets khác.

### 9.2. Mostly-static

~~~bash
native-image --static-nolibc \
  -jar application.jar \
  -o orders-service
~~~

Mostly-static liên kết tĩnh các thư viện liên quan ngoại trừ libc. Nó vẫn cần libc, cụ thể là glibc trong trường hợp build theo glibc. Đây là lựa chọn hữu ích khi muốn giảm số shared libraries cần cài trong Debian-based Distroless hoặc runtime glibc khác.

Không nhầm `--static-nolibc` với fully-static: binary này không thể mặc định chạy trên `scratch` vì vẫn cần libc runtime.

### 9.3. Chọn phương án

- Chọn dynamic nếu muốn dùng base image glibc tiêu chuẩn và quản lý package runtime rõ ràng.
- Chọn mostly-static nếu muốn giảm shared dependencies khác nhưng vẫn triển khai trên glibc.
- Chọn fully-static/musl nếu cần executable tự chứa và architecture/toolchain của dự án hỗ trợ.

Static linking không giải quyết sai kiến trúc CPU, CPU instruction set không tương thích hoặc file runtime bên ngoài mà ứng dụng cần.

## 10. Lỗi `Illegal instruction` và CPU instruction set

Nếu process bắt đầu rồi kết thúc với:

~~~text
Illegal instruction (core dumped)
~~~

hoặc exit code do `SIGILL`, binary có thể chứa instruction mà CPU đích không hỗ trợ. Một nguyên nhân là build với `-march=native` trên CPU mới rồi chạy trên CPU cũ hơn.

Native Image có tùy chọn `-march` để điều khiển tập instruction mà compiler được phép dùng. Theo tài liệu GraalVM hiện hành, mặc định là `x86-64-v3` trên x64 và `armv8-a` trên AArch64; giá trị mặc định có thể phụ thuộc phiên bản.

Kiểm tra CPU và machine types:

~~~bash
lscpu
native-image -march=list
~~~

| Lựa chọn | Khi nào dùng |
|---|---|
| `-march=native` | Binary chỉ chạy trên cùng hoặc CPU có feature tương đương máy build |
| `-march=compatibility` | Phân phối tới nhiều máy, gồm CPU cũ hơn; ưu tiên tương thích |
| `-march=x86-64-v3` hoặc machine type cụ thể | Khi fleet production đã chuẩn hóa CPU feature level |

Ví dụ build ưu tiên tương thích:

~~~bash
native-image -march=compatibility \
  -jar application.jar \
  -o orders-service
~~~

Nếu dùng Maven/Gradle plugin, truyền option qua cấu hình Native Build Tools theo phiên bản plugin. Ghi lại `-march` trong build manifest vì thay đổi này có thể làm thay đổi binary và hiệu năng.

Không dùng `-march=native` trên runner không đại diện CPU production nếu binary sẽ chạy trên nhiều thế hệ CPU. Hãy kiểm thử trên máy có instruction set thấp nhất trong fleet được hỗ trợ.

## 11. Quy trình chẩn đoán ELF có thể lặp lại

Với executable đáng tin cậy, chạy theo thứ tự:

~~~bash
BIN=./orders-service

# 1. File type and architecture
file "$BIN"
readelf -h "$BIN" | grep -E 'Class:|Data:|Machine:|Type:'

# 2. Dynamic loader
readelf -l "$BIN" | grep -A1 INTERP || true

# 3. Direct dependencies and search paths
readelf -d "$BIN" | grep -E 'NEEDED|RPATH|RUNPATH' || true

# 4. Required glibc symbol versions
readelf --version-info "$BIN" | grep GLIBC_ || true

# 5. Full dependency resolution (trusted binary only)
ldd "$BIN"
~~~

Sau đó chạy cùng kiểm tra trên file được copy từ **final image**. Nếu binary trong builder và binary trong final image có SHA-256 khác nhau, xác định chính xác bước nào đã thay đổi file.

### Kiểm tra file và image bằng Docker

~~~bash
docker image inspect \
  --format '{{.Os}}/{{.Architecture}} {{.Id}}' \
  orders-service:native

docker create --name inspect-native orders-service:native
docker cp inspect-native:/app/orders-service ./orders-service-from-image
docker rm inspect-native

file ./orders-service-from-image
readelf -h ./orders-service-from-image
~~~

Lệnh `docker cp` giúp lấy executable từ image để phân tích bằng tool trên host, kể cả khi runtime image không có shell. Với Distroless, dùng debug image hoặc container chẩn đoán có cùng base filesystem.

## 12. Ma trận triệu chứng và cách xử lý

| Triệu chứng | Lớp lỗi có khả năng | Kiểm tra đầu tiên | Hướng sửa |
|---|---|---|---|
| `exec format error` | Sai ELF format/architecture | `file`, `readelf -h`, `uname -m` | Build đúng OS/CPU hoặc cấu hình emulation |
| `cannot execute binary file` | Sai kiến trúc hoặc file không phải executable phù hợp | `file`, permission, ELF header | Dùng đúng artifact và executable permission |
| File tồn tại nhưng `No such file or directory` | Thiếu `PT_INTERP` loader | `readelf -l`, loader path trong final rootfs | Dùng runtime có loader phù hợp hoặc rebuild |
| `wrong ELF class` | 32/64-bit hoặc ABI class không khớp | `readelf -h` trên executable và `.so` | Dùng đúng kiến trúc/bitness của dependency |
| `GLIBC_2.xx not found` | Runtime glibc cũ hơn symbol binary cần | `readelf --version-info`, `ldd --version` | Build trên glibc baseline thấp hơn hoặc nâng runtime |
| `libfoo.so: cannot open shared object file` | Thiếu shared library hoặc sai search path | `ldd`, `readelf -d`, `LD_DEBUG=libs` | Cài đúng package hoặc sửa RUNPATH/library path |
| `Error relocating ... symbol not found` | ABI/libc mismatch hoặc `.so` sai version | `file`, `readelf -d` | Đồng bộ libc và native library; rebuild nếu cần |
| `Illegal instruction` / `SIGILL` | CPU thiếu instruction feature | `lscpu`, build flags và `-march` | Build với `-march=compatibility` hoặc target feature chung |
| Chạy trong builder nhưng lỗi trong final image | Builder có loader/library mà runtime không có | Lặp ELF checks trên file và rootfs cuối | Thêm runtime dependency tối thiểu hoặc chọn base phù hợp |
| Chỉ chạy khi dùng `LD_LIBRARY_PATH` | Library search path không được đóng gói đúng | `readelf -d`, `LD_DEBUG=libs` | Đưa thư viện vào runtime path/RUNPATH rõ ràng |

## 13. Thiết kế build matrix cho amd64 và arm64

GraalVM cung cấp Linux distributions cho x64 và AArch64; hãy kiểm tra compatibility guide của đúng GraalVM release và option đang dùng. Đặc biệt, tài liệu hiện hành ghi nhận musl chưa được hỗ trợ trên Linux AArch64, vì vậy không giả định quy trình fully-static của amd64 có thể áp dụng nguyên trạng cho arm64.

Nếu sản phẩm chạy trên cả x86-64 và ARM64, hãy coi mỗi kiến trúc là một artifact riêng:

| Thuộc tính | amd64 | arm64 |
|---|---|---|
| Runner | Linux x86-64 | Linux AArch64 |
| Build platform | `linux/amd64` | `linux/arm64` |
| ELF machine | x86-64 | AArch64 |
| Native executable | `orders-service-amd64` | `orders-service-arm64` |
| Binary SHA-256 | Riêng | Riêng |
| Integration test | Chạy trên amd64 | Chạy trên arm64 |

Pipeline có thể dùng hai native runner để build song song, sau đó đóng gói image variants và publish manifest list. Mỗi binary cần được kiểm tra ELF header, loader, shared dependencies và smoke test trên đúng architecture.

Docker Buildx có thể ghép nhiều platform vào một image manifest list:

~~~bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag registry.example.com/orders-service:1.0.0 \
  --push .
~~~

Để lệnh này tạo native executable đúng kiến trúc, builder strategy phải thực sự tạo được binary cho từng target. Với Native Image, ưu tiên native builder node cho từng kiến trúc; không giả định việc Buildx chọn platform là đã cross-compile đúng binary.

Lưu checksum và test evidence riêng cho từng platform. Khi pull image đa kiến trúc, Docker chọn biến thể phù hợp với host, nhưng vẫn cần xác minh manifest list có đủ platform mà sản phẩm cam kết hỗ trợ.

## 14. Kiểm thử final image trước khi phát hành

Không dừng ở việc kiểm tra binary chạy được trong builder. Final image là môi trường thực tế mà production sẽ chạy.

Quy trình tối thiểu:

1. Build native executable cho đúng target architecture.
2. Đóng gói vào runtime image cuối.
3. Kiểm tra platform image và ELF machine.
4. Kiểm tra `PT_INTERP`, shared libraries và libc compatibility.
5. Khởi chạy container với cùng user, filesystem permissions và environment production.
6. Chờ readiness endpoint.
7. Gọi một request thực tế để xác nhận server có thể phục vụ traffic.
8. Kiểm tra log, exit code và signal khi container dừng.

Ví dụ:

~~~bash
docker run -d --name orders-native-test \
  -p 18080:8080 \
  orders-service:native

docker logs orders-native-test
curl --fail http://localhost:18080/actuator/health
docker stop orders-native-test
docker rm orders-native-test
~~~

Điều chỉnh health path và port theo ứng dụng. Nếu Actuator bị bảo vệ bởi Spring Security, dùng cấu hình test phù hợp hoặc probe endpoint readiness đã được thiết kế.

Với container Distroless hoặc `scratch`, không yêu cầu shell để kiểm tra. Dùng health probe từ host/orchestrator và công cụ phân tích trên bản copy của executable.

## 15. Những cách sửa dễ tạo lỗi mới

| Cách làm | Rủi ro |
|---|---|
| Copy `libc.so.6` từ builder sang runtime | Trộn glibc và loader khác version, phát sinh lỗi ABI khó đoán |
| Cài hàng loạt package development vào runtime | Image lớn, tăng attack surface và khó kiểm soát dependency |
| Đặt `LD_LIBRARY_PATH` rộng cho mọi thư mục | Có thể nạp nhầm library version hoặc thư viện không tin cậy |
| Dùng `-march=native` trên runner CPU mới | Binary có thể SIGILL trên CPU production cũ hơn |
| Build amd64 rồi đổi tag thành arm64 | Tag không đổi machine code trong ELF |
| Chỉ chạy test trong builder image | Builder có thể che giấu thiếu loader/shared library của runtime |
| Dùng `ldd` trên file không tin cậy | Một số implementation có thể thực thi code trong quá trình phân tích |
| Giả định Alpine tương thích glibc | Alpine dùng musl; loader và ABI có thể không khớp |
| Giả định `--static-nolibc` chạy được trên `scratch` | Mostly-static vẫn cần libc runtime |

## 16. Checklist chẩn đoán trước khi release

- [ ] Xác định host architecture và Docker daemon platform.
- [ ] Kiểm tra platform của final image/manifest.
- [ ] Dùng `file` và `readelf -h` xác nhận ELF machine và class.
- [ ] Kiểm tra `PT_INTERP` và xác nhận loader tồn tại trong runtime filesystem.
- [ ] Kiểm tra `DT_NEEDED`, RPATH/RUNPATH và shared-library resolution.
- [ ] Kiểm tra glibc symbol versions và libc của runtime.
- [ ] Xác định rõ binary được build cho glibc hay musl.
- [ ] Phân biệt dynamic, mostly-static và fully-static.
- [ ] Kiểm tra CPU instruction set và `-march`.
- [ ] Build binary riêng cho từng kiến trúc được hỗ trợ.
- [ ] Chạy smoke/integration test trên đúng final image.
- [ ] Lưu ELF inspection, dependency list, binary digest và image digest cùng build evidence.

## 17. Bài tập tự kiểm tra

**Câu 1.** Vì sao một file executable tồn tại nhưng shell vẫn báo `No such file or directory`?

**Gợi ý:** kernel có thể không tìm thấy dynamic loader được khai báo trong segment `PT_INTERP`.

**Câu 2.** `exec format error` khác `GLIBC_2.xx not found` như thế nào?

**Gợi ý:** lỗi đầu thường xảy ra khi kernel không chấp nhận định dạng/kiến trúc; lỗi sau xảy ra khi loader tìm thấy binary nhưng libc runtime thiếu symbol version cần thiết.

**Câu 3.** Vì sao `ldd` nên chỉ dùng trên binary đáng tin cậy?

**Gợi ý:** một số implementation có thể gọi dynamic loader hoặc thực thi thành phần của file trong lúc truy vấn dependency.

**Câu 4.** Binary `--static-nolibc` có chạy được trên `scratch` không?

**Gợi ý:** không thể mặc định. Mostly-static vẫn cần libc runtime.

**Câu 5.** Khi nào nên chọn `-march=compatibility`?

**Gợi ý:** khi binary cần chạy trên nhiều thế hệ CPU hoặc CPU cũ hơn máy build.

**Câu 6.** Docker Buildx có tự chuyển một executable amd64 thành arm64 khi build `--platform linux/arm64` không?

**Gợi ý:** không. Build stage phải tạo được native binary cho target; dùng native runner/builder node hoặc quy trình cross-build đã xác minh.

**Câu 7.** Vì sao kiểm thử binary trong builder stage chưa đủ?

**Gợi ý:** builder có thể chứa loader và shared libraries không có trong final runtime image.

## 18. Tài liệu tham khảo

- [GraalVM — Installation on Linux Platforms](https://www.graalvm.org/docs/getting-started/linux/): Linux x64/AArch64 và prerequisite toolchain của Native Image.
- [GraalVM — Native Image Compatibility Guide](https://www.graalvm.org/reference-manual/native-image/metadata/Compatibility/): các giới hạn tương thích Native Image theo platform.
- [GraalVM — Optimizations and Performance](https://www.graalvm.org/reference-manual/native-image/optimizations-and-performance/): `-march`, machine type và lựa chọn tối ưu theo CPU.
- [GraalVM — Build Static or Mostly-Static Native Executables](https://www.graalvm.org/reference-manual/native-image/StaticImages/): dynamic, mostly-static, fully-static và musl/glibc.
- [Docker — Multi-platform builds](https://docs.docker.com/build/building/multi-platform/): platform manifests, QEMU, native nodes và cross-compilation strategies.
- [Docker — Dockerfile reference](https://docs.docker.com/reference/dockerfile/): `--platform`, `BUILDPLATFORM` và `TARGETPLATFORM`.
- [Linux man-pages — execve(2)](https://man7.org/linux/man-pages/man2/execve.2.html): hành vi kernel khi thực thi ELF và dynamic interpreter.
- [Linux man-pages — ldd(1)](https://man7.org/linux/man-pages/man1/ldd.1.html): hiển thị shared-object dependencies và lưu ý bảo mật.
- [Linux man-pages — ld.so(8)](https://man7.org/linux/man-pages/man8/ld.so.8.html): dynamic linker/loader và cơ chế tìm shared libraries.
- [GNU Binutils — readelf(1)](https://www.man7.org/linux/man-pages/man1/readelf.1.html): đọc ELF header, program headers, dynamic section và symbol version.

**Ghi nhớ:** Chẩn đoán binary Native Image theo thứ tự: kiến trúc ELF, dynamic loader, libc/ABI, shared libraries và CPU instruction set. Luôn kiểm tra executable trong final runtime image. Build riêng cho từng kiến trúc, chọn libc phù hợp và dùng `-march` theo CPU thấp nhất mà sản phẩm cần hỗ trợ.

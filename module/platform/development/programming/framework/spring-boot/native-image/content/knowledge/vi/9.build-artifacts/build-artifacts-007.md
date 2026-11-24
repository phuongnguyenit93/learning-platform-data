# Xác định hệ điều hành, kiến trúc và thư viện liên kết của binary

## 1. Vì sao phải kiểm tra binary trước khi phát hành?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng Spring AOT và GraalVM Native Image để tạo executable native. Khác với JAR chứa bytecode Java có thể chạy trên JVM tương thích, executable native gắn với **hệ điều hành, kiến trúc CPU, ABI và các thư viện native** mà nó được biên dịch/link.

Một binary build thành công trên máy developer chưa chắc chạy được trong production container. Ví dụ, binary Linux x86-64 có thể không chạy trên ARM64; executable liên kết động với glibc có thể không chạy trong image chỉ có musl; hoặc runtime container thiếu phiên bản shared library mà binary yêu cầu.

Vì vậy, trước khi đóng gói và phát hành, cần trả lời được:

- File là định dạng executable nào và dành cho hệ điều hành nào?
- Binary được tạo cho kiến trúc CPU nào?
- Nó dùng ABI/libc nào và yêu cầu loader nào?
- Những shared library nào cần có khi chạy?
- Runtime image có đủ dependency và tương thích với binary không?

Đây là bước xác minh **artifact và môi trường thực thi**. Nó bổ sung cho kiểm thử chức năng Spring AOT/native: một binary đúng định dạng vẫn có thể thiếu reflection metadata hoặc resource, và một ứng dụng đúng chức năng trên máy build vẫn có thể không khởi chạy trên image triển khai.

## 2. Hệ điều hành, kiến trúc và ABI là ba thông tin khác nhau

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Hệ điều hành/format | Linux ELF, Windows PE, macOS Mach-O | Định dạng executable và quy ước hệ điều hành |
| CPU architecture | x86-64, AArch64/ARM64 | Tập lệnh CPU mà binary chứa |
| ABI | Linux GNU/glibc ABI, Linux musl ABI | Quy ước gọi hàm, symbol, kiểu dữ liệu và liên kết với thư viện hệ thống |
| Dynamic loader | `ld-linux-x86-64.so.2`, loader musl | Thành phần nạp các shared library khi khởi chạy |
| Shared libraries | `libc.so.6`, `libz.so.1`, `libstdc++.so.6` | Các thư viện động mà executable yêu cầu |

Không thể suy ra ABI chỉ từ chữ “Linux” hoặc chỉ từ architecture. Hai binary đều là ELF x86-64 vẫn có thể phụ thuộc libc và phiên bản symbol khác nhau. Tương tự, một image container có thể chạy trên host ARM64 nhờ emulation, nhưng điều đó không làm binary x86-64 trở thành binary ARM64 native.

## 3. Định dạng executable: ELF, PE và Mach-O

GraalVM Native Image tạo executable phù hợp với nền tảng build/target được hỗ trợ.

- **ELF (Executable and Linkable Format):** phổ biến trên Linux, dùng cho executable, object file và shared library.
- **PE/COFF:** định dạng executable và object phổ biến trên Windows, ví dụ file `.exe`.
- **Mach-O:** định dạng executable và library của macOS.

Dùng lệnh `file` để nhận diện nhanh:

```bash
file ./application
```

Ví dụ output Linux có thể tương tự:

```text
application: ELF 64-bit LSB pie executable, x86-64, dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2
```

Thông tin này cho biết file là ELF 64-bit, kiến trúc x86-64 và có dynamic interpreter. Output thực tế thay đổi theo toolchain, link mode và kiến trúc.

Trên Windows có thể kiểm tra file bằng công cụ PE inspection phù hợp; trên macOS có thể dùng `file` và `otool`. Không sử dụng `ldd` để kiểm tra PE hoặc Mach-O.

## 4. Xác định kiến trúc của binary và máy chạy

Trên Linux:

```bash
uname -m
file ./application
readelf -h ./application
```

- `uname -m` cho biết kiến trúc kernel/host đang chạy.
- `file` nhận diện định dạng và architecture của binary.
- `readelf -h` đọc ELF header, gồm class, data encoding, type và machine.

Các giá trị thường gặp:

| Output machine | Kiến trúc | Ví dụ target |
|---|---|---|
| `Advanced Micro Devices X86-64` | x86-64 / AMD64 | Linux amd64 |
| `AArch64` | ARM 64-bit | Linux arm64 |
| `Intel 80386` | x86 32-bit | Linux 386 |
| `ARM` | ARM 32-bit | Một số hệ thống embedded |

Docker dùng tên platform như `linux/amd64` và `linux/arm64`. Có thể kiểm tra kiến trúc image bằng:

```bash
docker image inspect application:latest --format '{{.Os}}/{{.Architecture}}'
```

Lệnh này hiển thị metadata image, không kiểm tra từng executable bên trong. Với multi-architecture manifest, image tag có thể trỏ tới nhiều manifest/platform; registry/runtime chọn biến thể phù hợp. Hãy kiểm tra cả platform image và binary thực tế nếu image chứa nhiều artifact.

## 5. Đọc ELF header, program headers và dynamic section

`readelf` là công cụ quan trọng để kiểm tra ELF mà không cần thực thi binary.

### ELF header

```bash
readelf -h ./application
```

Các trường cần chú ý:

- **Class:** ELF32 hay ELF64.
- **Data:** little endian hay big endian.
- **Type:** executable, shared object hoặc loại khác.
- **Machine:** CPU architecture.
- **Entry point:** địa chỉ bắt đầu thực thi.

### Program headers và interpreter

```bash
readelf -l ./application
```

Tìm mục `INTERP` hoặc dòng tương tự:

```text
[Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]
```

Đây là dynamic loader mà kernel cần tìm khi chạy executable. Nếu loader không tồn tại trong runtime filesystem, process có thể báo “No such file or directory” dù file executable thực sự có mặt. Đây là lỗi thường gặp khi copy binary glibc sang image Alpine/musl không có glibc loader.

### Dynamic section

```bash
readelf -d ./application
```

Tìm các mục `NEEDED` để xem shared library dependency được ghi trong ELF. Ví dụ:

```text
Shared library: [libz.so.1]
Shared library: [libc.so.6]
```

Các dependency này cần được loader tìm thấy tại runtime. Không phải mọi binary đều có dynamic section; executable link tĩnh có thể không liệt kê `NEEDED`.

## 6. Xác định shared libraries cần thiết

Trên Linux, `ldd` có thể hiển thị các shared library mà executable liên kết động cần:

```bash
ldd ./application
```

Output minh họa:

```text
linux-vdso.so.1
libz.so.1 => /lib/x86_64-linux-gnu/libz.so.1
libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6
/lib64/ld-linux-x86-64.so.2
```

Nếu xuất hiện `not found`, thư viện được yêu cầu không được tìm thấy trong môi trường hiện tại. Cần xác định package runtime cung cấp library đó và bảo đảm đúng architecture/ABI.

**Cảnh báo thao tác:** không chạy `ldd` trực tiếp trên binary không tin cậy. Tùy nền tảng và loại executable, một số cách triển khai `ldd` lịch sử có thể kích hoạt code. Với artifact chưa tin cậy, ưu tiên đọc metadata bằng `readelf -d` hoặc công cụ phân tích ELF tĩnh.

Có thể dùng `objdump -p` để xem dynamic dependencies:

```bash
objdump -p ./application | grep NEEDED
```

Kết quả `NEEDED` liệt kê tên library, chưa chứng minh library sẽ được resolve thành công trong container. Cần kiểm tra tiếp trong runtime filesystem.

## 7. glibc và musl: vì sao cùng Linux nhưng không tương thích mặc định?

Linux distributions thường dùng libc khác nhau:

- **glibc:** phổ biến trong Debian, Ubuntu, Fedora, RHEL và nhiều bản phân phối Linux khác.
- **musl:** được Alpine Linux sử dụng mặc định, thiết kế gọn và phù hợp với môi trường tối giản.

Một executable native link động với glibc thường yêu cầu loader và symbol version của glibc. Alpine mặc định dùng musl; việc chỉ copy executable glibc vào Alpine thường không đủ để chạy. Ngược lại, binary build cho musl cũng không mặc nhiên chạy trên mọi glibc distribution nếu các giả định ABI khác nhau.

Kiểm tra binary cần dynamic interpreter nào bằng:

```bash
readelf -l ./application | grep interpreter
```

Kiểm tra dynamic dependencies bằng:

```bash
readelf -d ./application | grep NEEDED
```

Không kết luận binary “static” chỉ vì `ldd` không liệt kê thư viện. Một executable có thể static-link một số thành phần nhưng vẫn dùng dynamic library khác; hãy xem ELF metadata và test thực tế.

Với GraalVM Native Image, lựa chọn build distribution/toolchain và chế độ linking có ảnh hưởng tới khả năng triển khai. Chọn builder và runtime base tương thích ngay từ đầu, thay vì đợi đến khi container startup mới phát hiện mismatch.

## 8. Symbol version và yêu cầu phiên bản glibc

Một binary link động có thể yêu cầu symbol version cụ thể. Ví dụ executable build trên môi trường glibc mới có thể tham chiếu `GLIBC_2.xx`; runtime image có glibc cũ hơn sẽ không cung cấp symbol đó.

Có thể kiểm tra version yêu cầu trong ELF:

```bash
readelf --version-info ./application
```

Hoặc lọc thông tin symbol version:

```bash
objdump -T ./application | grep GLIBC_
```

Các lệnh này giúp nhận diện yêu cầu symbol version. Không nên chỉ dựa vào version glibc được ghi trong tên image; kiểm tra binary và thư viện thật bên trong image.

Cách xử lý thường là:

- Build trong môi trường có glibc tương thích với runtime base.
- Chọn runtime image có glibc đủ mới và được hỗ trợ.
- Dùng toolchain/target phù hợp nếu cần static hoặc musl build.
- Tránh nâng libc tùy tiện trong container production vì có thể ảnh hưởng các package khác.

Nguyên tắc thực tế: **build trên nền tảng tương thích với runtime**, hoặc dùng quy trình cross-build có kiểm soát và test trên đúng target.

## 9. Kiểm tra runtime container

Binary phải được kiểm tra bên trong chính image triển khai, không chỉ trên host build.

```bash
docker run --rm --entrypoint sh application:latest -c '
  uname -m
  cat /etc/os-release
  ls -l /app
'
```

Lệnh trên giả định image có shell và các tiện ích này; distroless/scratch image có thể không có. Với image tối giản, dùng container debug tương thích hoặc kiểm tra bằng công cụ runtime bên ngoài. Không thay đổi entrypoint production chỉ để tiện kiểm tra.

Có thể chạy ứng dụng và quan sát exit code/log:

```bash
docker run --rm -p 8080:8080 application:latest
```

Sau đó gửi request từ host:

```bash
curl -i http://localhost:8080/actuator/health
```

Endpoint Actuator chỉ có nếu ứng dụng đã thêm Actuator và cấu hình exposure phù hợp. Nếu không, dùng endpoint nghiệp vụ đã biết.

Nếu container thoát ngay với lỗi loader/shared library, kiểm tra interpreter và `NEEDED`. Nếu process chạy nhưng endpoint lỗi reflection/resource, đó là lớp vấn đề khác, cần kiểm tra metadata Spring AOT/GraalVM và test chức năng.

## 10. Xác minh kiến trúc multi-platform

Khi phát hành image đa kiến trúc, cần tạo binary riêng cho từng target hoặc dùng cơ chế build multi-platform mà toolchain hỗ trợ. Một executable x86-64 không tự chuyển thành ARM64 khi Docker tạo manifest list.

Kiểm tra image platform:

```bash
docker buildx imagetools inspect registry.example.com/orders:1.0
```

Output cho biết các platform manifest mà tag tham chiếu. Cần xác minh mỗi platform thực sự chứa binary đúng architecture:

- Build target `linux/amd64` phải chứa ELF x86-64.
- Build target `linux/arm64` phải chứa ELF AArch64.
- Runtime base và shared libraries của mỗi platform phải cùng kiến trúc và ABI.
- Chạy smoke test trên host/native runner phù hợp hoặc môi trường emulation đã được xác nhận.

Cross-compilation native có các giới hạn phụ thuộc GraalVM version, toolchain và thư viện native. Không giả định chỉ cần đặt `--platform linux/arm64` trong Docker là mọi bước GraalVM tự động cross-compile đúng.

## 11. Build và kiểm tra artifact Spring Boot Native Image

Với Maven, build native theo cấu hình dự án:

```bash
./mvnw -Pnative native:compile
```

Với Gradle:

```bash
./gradlew nativeCompile
```

Tên và vị trí executable phụ thuộc artifact name, plugin version, OS và cấu hình. Sau khi build, tìm đúng file trong output Maven/Gradle rồi chạy các bước kiểm tra:

```bash
file ./path/to/application
readelf -h ./path/to/application
readelf -l ./path/to/application
readelf -d ./path/to/application
```

Trên Linux, kiểm tra host:

```bash
uname -m
cat /etc/os-release
```

Sau đó so sánh với platform và libc của runtime container. Không chạy native binary trong bước build chỉ để xác nhận file tồn tại; cần kiểm tra chức năng, dependency và điều kiện triển khai.

## 12. Phân loại lỗi theo dấu hiệu

| Triệu chứng | Nhóm nguyên nhân | Hướng xác minh |
|---|---|---|
| `Exec format error` | Sai OS format hoặc architecture | `file`, `readelf -h`, platform image |
| `No such file or directory` dù binary tồn tại | Dynamic loader/interpreter không có | `readelf -l`, kiểm tra runtime base |
| `error while loading shared libraries` | Thiếu shared library | `readelf -d`, kiểm tra package trong image |
| `GLIBC_x.y not found` | Runtime glibc quá cũ | `readelf --version-info`, chọn base tương thích |
| Binary chạy host nhưng lỗi container | Khác libc, loader, architecture hoặc file runtime | Kiểm tra trong image thực tế |
| Process khởi động nhưng endpoint lỗi | Metadata, resource, cấu hình hoặc nghiệp vụ | Native integration test và log ứng dụng |
| Binary quá lớn | Link mode, dependency và thành phần được giữ lại | Phân tích build report và cấu hình Native Image |

Lỗi “No such file or directory” dù file có thật thường gây nhầm lẫn. Kernel có thể không tìm thấy **interpreter** được ghi trong ELF header, không phải executable path. Vì thế, kiểm tra `readelf -l` là bước quan trọng.

## 13. Checklist phát hành artifact

Trước khi đưa native image vào registry/production, ghi nhận:

- [ ] Artifact là đúng định dạng cho hệ điều hành đích.
- [ ] Architecture của binary khớp platform image.
- [ ] ABI/libc và dynamic loader phù hợp runtime.
- [ ] Tất cả shared library `NEEDED` được cung cấp.
- [ ] Symbol version không vượt quá thư viện runtime.
- [ ] Runtime image có CA certificates, timezone data và file runtime cần thiết.
- [ ] Container chạy bằng user/quyền phù hợp và có thể khởi động.
- [ ] Smoke test endpoint và các luồng nghiệp vụ quan trọng pass.
- [ ] Image tag/digest, builder và toolchain version được ghi lại.
- [ ] Mỗi platform trong multi-arch image đã được xác minh độc lập.

Checklist này nên được thực hiện trong pipeline phát hành để tránh tình trạng máy developer chạy được nhưng production không chạy.

## 14. Bài thực hành: phân tích binary và chạy trong container

**Bối cảnh:** đã có executable Spring Boot Native Image được build trên Linux.

**Bước 1 — Nhận diện binary.**

```bash
file ./application
readelf -h ./application
```

Ghi lại ELF class, machine architecture và loại file.

**Bước 2 — Kiểm tra interpreter và thư viện.**

```bash
readelf -l ./application
readelf -d ./application
readelf --version-info ./application
```

Ghi lại dynamic loader, danh sách `NEEDED` và symbol version yêu cầu.

**Bước 3 — So sánh với môi trường runtime.** Xác định OS, architecture và libc trong container base. Kiểm tra library path và phiên bản thư viện cần thiết.

**Bước 4 — Chạy container.** Khởi chạy image, quan sát exit code/log và gọi endpoint. Nếu lỗi loader, xử lý ABI/dependency trước khi điều tra Spring.

**Bước 5 — Kiểm thử chức năng native.** Chạy các request bao phủ JSON, reflection, resource, validation và tích hợp thực tế. Ghi rõ lỗi thuộc lớp hệ thống hay lớp ứng dụng.

**Bước 6 — Ghi artifact manifest.** Lưu binary checksum, image digest, OS/architecture, builder/runtime base, GraalVM version và dependency quan trọng để có thể truy vết lần phát hành.

## 15. Kết luận

Executable GraalVM Native Image phụ thuộc vào **định dạng hệ điều hành, kiến trúc CPU, ABI/libc, dynamic loader và shared libraries**. Các công cụ như `file`, `readelf`, `objdump` và kiểm tra container giúp xác định yêu cầu đó trước khi triển khai. Một binary build thành công chưa chắc chạy trên mọi Linux image; cần xác minh trong đúng runtime filesystem và từng kiến trúc phát hành.

Khi phân biệt rõ lỗi hệ thống (format, architecture, loader, library) với lỗi ứng dụng (Spring AOT hints, reflection, resource, configuration), nhóm phát triển có thể xử lý đúng tầng, tạo artifact tái lập và vận hành Spring Boot Native Image ổn định hơn.

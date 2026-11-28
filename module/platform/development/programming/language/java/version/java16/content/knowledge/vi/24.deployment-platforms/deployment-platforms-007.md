# Giới hạn tính di động của application image và runtime image

Trong hệ sinh thái Java, JAR chứa bytecode thường có thể chạy trên nhiều hệ điều hành và kiến trúc nếu JDK đích tương thích. Tuy nhiên, runtime image tạo bằng `jlink` và application image tạo bằng `jpackage` thường gắn với một nền tảng cụ thể vì chúng chứa launcher, JVM và thư viện native của hệ điều hành/CPU đó.

Vì vậy, cần phân biệt artifact ứng dụng có thể dùng chung với runtime và gói ứng dụng phải tạo riêng theo target. Bài viết dùng thuật ngữ **runtime image** cho đầu ra của `jlink` và **application image** cho kiểu gói `app-image` của `jpackage`. Application image trong bài này không phải Docker/OCI image.

## 1. Phân biệt JAR, runtime image và application image

Ba loại artifact giải quyết các nhu cầu khác nhau:

| Artifact | Chứa gì? | Tính di động điển hình |
|---|---|---|
| JAR ứng dụng | Bytecode `.class`, metadata và tài nguyên ứng dụng | Thường dùng chung giữa các OS/CPU nếu class-file version, API và dependency tương thích |
| Runtime image (`jlink`) | JVM, module Java được chọn, launcher và thư viện native của runtime | Gắn với OS/CPU và ABI của JDK dùng để tạo image |
| Application image (`jpackage --type app-image`) | Launcher ứng dụng, application files, runtime image và cấu trúc thư mục theo nền tảng | Gắn với OS/CPU; có thể còn phụ thuộc phiên bản hệ điều hành và native dependencies |

Ví dụ, `orders-service.jar` thuần Java có thể chạy trên Windows x64 và Linux ARM64. Nhưng runtime image tạo từ JDK Windows x64 không thể được copy sang Linux ARM64 để chạy. Application image được tạo từ runtime Windows x64 cũng không trở thành gói Linux chỉ bằng cách đổi tên thư mục.

## 2. JAR có thể dùng chung, nhưng vẫn có điều kiện

Bytecode Java không chứa lệnh máy x64 hoặc ARM64. JVM đọc bytecode và diễn giải hoặc JIT biên dịch thành mã máy phù hợp với kiến trúc đang chạy. Do đó, cùng một JAR có thể được sử dụng trên nhiều nền tảng khi:

- JDK đích hỗ trợ class-file version của ứng dụng.
- Các API Java mà ứng dụng sử dụng tồn tại trong JDK đích.
- Dependency Java tương thích với phiên bản Java đó.
- Native dependency, nếu có, có biến thể đúng OS/CPU/ABI.
- Cấu hình bên ngoài, tài nguyên và đường dẫn không giả định một hệ điều hành cụ thể.

Ví dụ, có thể biên dịch ứng dụng theo Java 21 để giữ khả năng chạy trên các JDK tương thích:

```sh
javac --release 21 -d out src/com/example/Main.java
jar --create --file app.jar --main-class com.example.Main -C out .
```

`--release 21` kiểm soát mức ngôn ngữ, class-file version và tập API được phép sử dụng. Nó không tạo JAR riêng cho x64 hay ARM64.

Tính portable của JAR không đồng nghĩa ứng dụng chắc chắn portable. Nếu thư viện tải `libcodec.so`, `codec.dll` hoặc executable phụ trợ, cần kiểm tra các file đó theo từng target. Ứng dụng cũng có thể phụ thuộc vào shell, đường dẫn file, biến môi trường, timezone, font hoặc certificate store của hệ điều hành.

## 3. Runtime image của jlink gắn với nền tảng nào?

`jlink` liên kết các module Java cần thiết cùng thành phần runtime thành một runtime image nhỏ hơn JDK đầy đủ. Image này thường có thư mục `bin`, thư viện JVM, module và các thành phần native cần để chạy trên nền tảng đích.

Ví dụ tạo runtime image:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output runtime
```

Ví dụ chỉ chọn `java.base` và `java.logging` để minh họa cú pháp. Với ứng dụng thật, cần xác định đầy đủ module phụ thuộc. Có thể dùng `jdeps` để hỗ trợ phân tích dependency tĩnh:

```sh
jdeps --multi-release 21 --print-module-deps app.jar
```

`jdeps` không thể phát hiện chắc chắn mọi module được tải động qua reflection, service loading, plugin hoặc tên class được cấu hình lúc chạy. Hãy bổ sung module cần thiết dựa trên kiến trúc ứng dụng và kiểm thử các chức năng thực tế. Tùy nhu cầu, có thể dùng `--bind-services` để liên kết các provider service phù hợp.

Runtime image do `jlink` tạo chứa binary của JDK đầu vào. Do đó:

- Runtime image Windows x64 dành cho Windows x64.
- Runtime image Windows ARM64 dành cho tiến trình Windows ARM64.
- Runtime image Linux x64 cần phù hợp ABI/libc của Linux target.
- Runtime image Linux ARM64 musl dành cho môi trường ARM64/musl tương ứng.
- Runtime image macOS ARM64 dành cho macOS ARM64.

`jlink` không phải công cụ cross-compiler để chuyển một runtime x64 thành ARM64 hoặc chuyển runtime glibc thành musl. Hãy tạo runtime bằng JDK/module phù hợp với nền tảng đích. Nếu cần nhiều target, duy trì nhiều runtime image riêng.

## 4. Application image của jpackage chứa gì?

`jpackage --type app-image` tạo một thư mục ứng dụng có launcher và cấu trúc tài nguyên theo hệ điều hành. Thông thường, application image có runtime riêng được tạo từ JDK dùng để chạy `jpackage`, hoặc dùng runtime image được cung cấp qua `--runtime-image`.

Ví dụ tạo application image từ một runtime image đã tạo trước:

```sh
jpackage \
  --type app-image \
  --name OrdersApp \
  --input target \
  --main-jar orders-app.jar \
  --runtime-image runtime
```

Trong ví dụ này:

- `--type app-image` yêu cầu tạo application image dạng thư mục.
- `--input target` chỉ thư mục chứa application input, chẳng hạn JAR và dependency cần đóng gói.
- `--main-jar` chỉ JAR khởi chạy.
- `--runtime-image` đưa runtime image đã chuẩn bị vào application image.

Nếu bỏ `--runtime-image`, `jpackage` tạo runtime image bằng `jlink` từ JDK đang dùng, với module cần thiết được xác định theo cấu hình đóng gói. Vì vậy, kiến trúc và nền tảng của JDK chạy `jpackage` ảnh hưởng đến runtime được tạo.

Application image là thư mục có thể chạy trên target phù hợp; nó chưa nhất thiết là installer. `jpackage` còn có thể tạo định dạng cài đặt của từng hệ điều hành như MSI/EXE, PKG/DMG, DEB hoặc RPM tùy nền tảng và công cụ hỗ trợ.

## 5. Application image và runtime image có giới hạn di động khác nhau ra sao?

Runtime image chủ yếu đóng gói môi trường chạy Java. Application image bổ sung launcher và nội dung ứng dụng, nhưng thường chứa runtime nên kế thừa giới hạn nền tảng của runtime đó.

| Tiêu chí | Runtime image (`jlink`) | Application image (`jpackage`) |
|---|---|---|
| Mục tiêu | Cung cấp runtime Java đã tinh gọn | Cung cấp ứng dụng có launcher và runtime để chạy |
| Thành phần chính | JVM, module Java, native runtime files | Launcher, application files, runtime và cấu trúc theo OS |
| Phụ thuộc OS/CPU | Có | Có |
| Có chứa ứng dụng không? | Không nhất thiết; có thể chỉ chứa runtime | Có application input và launcher |
| Có thể dùng chung giữa Windows/Linux/macOS không? | Không | Không |
| Có thể dùng cho nhiều app cùng target không? | Có thể, nếu chính sách cập nhật và module phù hợp | Thường gắn với một ứng dụng cụ thể |
| Tạo riêng theo target? | Có | Có |

Application image không phải một lớp trừu tượng làm cho runtime trở nên portable. Nó là gói ứng dụng hoàn chỉnh hơn, vì vậy còn có thêm các yếu tố phụ thuộc như launcher native, file cấu hình, script và native dependency của ứng dụng.

## 6. Các yếu tố làm giảm tính di động của gói

Ngay cả khi runtime và JAR đã đúng kiến trúc, application image vẫn có thể không chạy ở môi trường khác vì:

- **OS ABI và thư viện hệ thống:** Linux glibc và Alpine musl có thể không tương thích nhị phân; Windows/macOS cũng có yêu cầu runtime riêng.
- **Kiến trúc CPU:** x64 và ARM64 cần JVM và native library phù hợp với tiến trình.
- **Phiên bản hệ điều hành:** binary có thể phụ thuộc API hoặc system library chỉ có trên phiên bản OS mới hơn.
- **Native dependency:** JNI/JNA, Java agent, codec, driver hoặc executable phụ trợ cần đúng target.
- **Cấu hình và filesystem:** đường dẫn, separator, quyền file, thư mục tạm, case sensitivity và vị trí cài đặt khác nhau.
- **Tài nguyên hệ thống:** certificate store, timezone database, locale, font và cấu hình DNS có thể khác.
- **Cơ chế bảo mật và ký mã:** Windows code signing, macOS signing/notarization, quyền thực thi và chính sách endpoint có thể ảnh hưởng việc cài/chạy.

Do đó, “cùng OS và CPU” cũng chưa chắc đủ. Cần xác định phiên bản hệ điều hành tối thiểu, ABI, thư viện native và yêu cầu vận hành của gói.

## 7. Ví dụ ma trận artifact cho nhiều nền tảng

Một ứng dụng phát hành cho Windows x64, Windows ARM64, Linux x64 glibc, Linux ARM64 musl và macOS ARM64 có thể tổ chức artifact như sau:

| Artifact | Có thể dùng chung? | Ghi chú |
|---|---|---|
| `orders-app.jar` | Thường có | Chỉ khi bytecode/API và dependency tương thích |
| `runtime-windows-x64` | Không | JVM và launcher Windows x64 |
| `runtime-windows-arm64` | Không | JVM và launcher Windows ARM64 |
| `runtime-linux-x64-glibc` | Không | Binary ELF x64 gắn với glibc target |
| `runtime-linux-arm64-musl` | Không | Binary ELF ARM64 gắn với musl target |
| `runtime-macos-arm64` | Không | Runtime Mach-O ARM64 |
| JNI/JNA native files | Không, trừ khi binary universal/multi-arch hợp lệ | Cần đúng OS/CPU/ABI |
| Application image | Không | Chứa launcher/runtime và cấu trúc theo target |

Pipeline có thể build JAR một lần, sau đó tạo runtime image và application image riêng cho từng target. Nếu ứng dụng có native dependency, pipeline cần lấy hoặc build native artifact riêng theo OS/CPU/libc.

Ví dụ đặt tên đầu ra:

```text
orders-app-2.4.0.jar
orders-app-2.4.0-windows-x64-app-image.zip
orders-app-2.4.0-windows-arm64-app-image.zip
orders-app-2.4.0-linux-x64-glibc-app-image.tar.gz
orders-app-2.4.0-linux-arm64-musl-app-image.tar.gz
orders-app-2.4.0-macos-arm64-app-image.zip
```

Tên file chỉ là quy ước để nhận diện target. Trong release metadata, nên ghi thêm JDK vendor/version, OS minimum, architecture, libc/ABI, native dependencies và checksum.

## 8. Tạo runtime và application image theo từng target

Quy trình build tổng quát cho mỗi target:

1. Build JAR ứng dụng bằng mức Java đã thống nhất, ví dụ `--release 21`.
2. Xác định module Java cần có trong runtime image.
3. Dùng JDK đúng OS/CPU/libc để chạy `jlink`.
4. Kiểm tra runtime image bằng cách chạy `runtime/bin/java -version` và đọc `os.arch`.
5. Dùng `jpackage --type app-image --runtime-image runtime` để đóng gói application image.
6. Kiểm tra cấu trúc thư mục, launcher, runtime và native dependency trong gói cuối.
7. Chạy smoke test và integration test trên target thực tế.
8. Lưu checksum/digest, thông tin JDK và kết quả test cùng artifact.

`jlink` và `jpackage` là công cụ đóng gói theo nền tảng. Không nên giả định có thể chạy một lần trên Windows x64 rồi tạo ra runtime Windows ARM64, Linux ARM64 hoặc macOS ARM64 chỉ bằng cách đổi tham số tên kiến trúc. Hãy dùng runner hoặc môi trường build đúng target, hoặc dùng quy trình cross-build được nhà cung cấp JDK và công cụ đóng gói hỗ trợ rõ ràng.

Ví dụ pipeline trên runner Linux ARM64:

```sh
java -version
java -XshowSettings:properties -version 2>&1 | grep -E 'os.name|os.arch|java.home'

jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging \
  --output runtime

jpackage \
  --type app-image \
  --name OrdersApp \
  --input target \
  --main-jar orders-app.jar \
  --runtime-image runtime
```

Đây là ví dụ trên một target Linux ARM64; module list cần được điều chỉnh cho ứng dụng. Nếu target là Alpine, JDK và runtime phải là bản musl phù hợp. Nếu target là Linux glibc, dùng JDK tương thích glibc và xác định mức glibc tối thiểu được hỗ trợ.

## 9. Cập nhật runtime và ứng dụng

Đóng gói runtime cùng application image giúp ứng dụng ít phụ thuộc JDK cài sẵn trên máy người dùng. Tuy nhiên, nhóm phát triển chịu trách nhiệm cập nhật runtime trong mỗi bản phát hành.

Khi JDK có bản vá bảo mật:

- Chọn patch release mới từ nhà cung cấp đang dùng.
- Tạo lại runtime image bằng JDK mới và module list đã kiểm thử.
- Tạo lại application image/installer theo từng target.
- Chạy regression test và kiểm tra native dependency.
- Phát hành artifact mới cùng checksum hoặc chữ ký.
- Có quy trình cập nhật/rollback cho người dùng đã cài ứng dụng.

Không nên copy runtime cũ sang gói ứng dụng mới vô thời hạn. Runtime được đóng gói riêng vẫn cần nhận CPU/security update như JDK cài đặt tập trung.

Nếu nhiều ứng dụng cùng dùng một runtime image, cần quản lý tương thích và vòng đời runtime đó. Runtime dùng chung có thể giảm dung lượng lưu trữ, nhưng cập nhật runtime có thể ảnh hưởng nhiều ứng dụng cùng lúc; lựa chọn này cần được kiểm thử và quản trị như một thành phần nền tảng.

## 10. Application image không phải Docker/OCI image

Hai thuật ngữ “image” dễ gây nhầm lẫn:

- **`jpackage` application image:** thư mục ứng dụng gồm launcher, runtime và application files theo nền tảng desktop/server.
- **Docker/OCI image:** filesystem layers và metadata dùng để tạo container, thường chứa JRE/JDK, application JAR, cấu hình và entrypoint.

Một Docker image cũng bị ràng buộc bởi kiến trúc CPU và môi trường hệ điều hành/container runtime. Docker manifest list có thể trỏ đến nhiều image cho `linux/amd64` và `linux/arm64`, nhưng từng image con vẫn chứa runtime và native dependency của kiến trúc tương ứng.

Application image do `jpackage` tạo có thể được đưa vào một Docker image nếu cách đóng gói và launcher phù hợp, nhưng hai định dạng không thay thế cho nhau. Với dịch vụ container, thường nên chọn base image JDK/JRE phù hợp rồi copy JAR hoặc runtime image vào container; với ứng dụng desktop, `jpackage` app image/installer có thể phù hợp hơn.

## 11. Kiểm thử tính di động của gói cuối

Không kiểm thử chỉ bằng JAR nếu sản phẩm sẽ phát hành application image. Cần kiểm tra đúng artifact người dùng sẽ cài hoặc chạy.

Checklist:

- [ ] JAR có class-file version và API phù hợp với runtime đích.
- [ ] Runtime image được tạo từ JDK đúng OS, CPU và libc/ABI.
- [ ] `runtime/bin/java -version` và `os.arch` xác nhận đúng runtime.
- [ ] Application image chứa launcher, runtime và application files như mong đợi.
- [ ] JNI/JNA, agent, native library và executable phụ trợ khớp kiến trúc tiến trình.
- [ ] Kiểm tra quyền file, thư mục tạm, đường dẫn, chứng chỉ và tài nguyên hệ thống.
- [ ] Chạy smoke test, integration test và quy trình cài đặt/nâng cấp/gỡ bỏ trên target.
- [ ] Kiểm tra bản vá JDK và quy trình phát hành lại application image.
- [ ] Ghi nhận OS minimum, architecture, libc/ABI, vendor/version và checksum.

Nếu một application image chạy trên máy build nhưng lỗi trên máy đích, hãy kiểm tra kiến trúc JVM, native dependencies, OS minimum và cấu hình môi trường trước khi kết luận JAR có vấn đề.

## 12. Ghi nhớ

- JAR thuần Java thường portable giữa các nền tảng có JDK tương thích.
- Runtime image do `jlink` tạo chứa JVM và native runtime files, nên gắn với OS/CPU/ABI.
- Application image do `jpackage` tạo chứa launcher, ứng dụng và thường có runtime riêng; nó kế thừa giới hạn nền tảng của runtime.
- `jlink` không chuyển runtime x64 thành ARM64 hoặc glibc thành musl.
- Muốn phát hành nhiều target, build runtime và application image riêng theo target.
- Native dependency, OS minimum, libc, cấu hình và quyền hệ thống đều ảnh hưởng tính di động.
- Runtime đóng gói cùng ứng dụng vẫn cần cập nhật bảo mật.
- `jpackage` application image khác Docker/OCI image.

Hãy xem JAR là artifact ứng dụng có thể dùng chung khi các dependency cho phép; runtime image và application image là artifact triển khai cần xác định rõ target. Cách phân chia này giúp pipeline build, kiểm thử và cập nhật runtime có thể lặp lại trên các nền tảng Java hiện đại.

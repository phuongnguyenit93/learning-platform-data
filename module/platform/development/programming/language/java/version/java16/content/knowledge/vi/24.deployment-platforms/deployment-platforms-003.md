# Kiểm tra native dependency trước khi chuyển ứng dụng sang Alpine

Trước khi chuyển một ứng dụng Java từ image Linux dùng `glibc` sang Alpine dùng `musl libc`, cần lập danh sách và kiểm tra toàn bộ thành phần native mà ứng dụng sử dụng. File `.class` và JAR chứa bytecode Java thường có thể chạy trên cả hai môi trường, nhưng thư viện JNI/JNA, Java agent có mã native và executable phụ trợ phải tương thích với hệ điều hành, kiến trúc CPU, ABI và C library của image đích.

Việc kiểm tra không dừng ở dependency khai báo trực tiếp. Native library có thể được kéo vào qua dependency bắc cầu, được đóng gói bên trong JAR, được giải nén khi chạy hoặc chỉ được nạp khi một chức năng cụ thể được gọi. Vì vậy, cần kết hợp phân tích dependency, kiểm tra ELF và chạy thử trong đúng image Alpine/musl dự kiến triển khai.

## 1. Phân biệt dependency Java thuần và dependency native

Một dependency Java thuần chỉ chứa bytecode và tài nguyên Java. Nếu phiên bản bytecode tương thích với JDK đang chạy, dependency đó thường không phụ thuộc glibc hay musl.

Dependency native có thể chứa hoặc sử dụng:

- Thư viện shared object trên Linux, thường có phần mở rộng `.so`.
- Thư viện JNI được nạp bằng `System.load` hoặc `System.loadLibrary`.
- Thư viện được JNA nạp hoặc giải nén từ JAR ra thư mục tạm.
- Native transport, codec, compression, database engine hoặc thư viện mật mã.
- Java agent, profiler, APM agent có thành phần native.
- Executable ngoài được gọi bằng `ProcessBuilder` hoặc script shell.

Một thư viện Java có thể trông như dependency thuần nhưng lại tải native binary ở runtime. Ví dụ, driver database nhúng hoặc thư viện nén có thể đóng gói các file `.so` theo từng hệ điều hành và kiến trúc rồi chọn một file khi ứng dụng khởi động hoặc khi gọi một chức năng cụ thể.

Một số thư viện phổ biến có thể cần kiểm tra native artifact tùy phiên bản và cách cấu hình gồm SQLite JDBC, RocksDB JNI, Snappy, Zstandard, Netty native transport và Tomcat Native. Danh sách này chỉ là gợi ý để rà soát; không có nghĩa mọi phiên bản của các thư viện đó đều không tương thích với musl. Phải xác nhận classifier, binary và ma trận nền tảng của đúng phiên bản đang dùng.

## 2. Lập danh sách dependency trực tiếp và bắc cầu

Đầu tiên, tạo dependency tree của runtime classpath. Một thư viện native có thể được thêm vào bởi framework hoặc một thư viện khác mà mã nguồn ứng dụng không khai báo trực tiếp.

### Maven

```sh
./mvnw dependency:tree -Dscope=runtime
```

Để tập trung vào một dependency nghi ngờ:

```sh
./mvnw dependency:tree -Dscope=runtime -Dincludes=org.rocksdb:rocksdbjni
```

### Gradle

```sh
./gradlew dependencies --configuration runtimeClasspath
```

Kiểm tra đường đi của một dependency cụ thể:

```sh
./gradlew dependencyInsight \
  --dependency rocksdbjni \
  --configuration runtimeClasspath
```

Đối chiếu dependency tree với tài liệu phát hành của từng thư viện. Cần ghi lại version, classifier, kiến trúc được hỗ trợ, loại libc và cách thư viện chọn native binary khi chạy.

| Thông tin cần ghi | Câu hỏi cần trả lời |
|---|---|
| Dependency và version | Thành phần nào kéo thư viện vào? |
| Native artifact | Có `.so`, executable hoặc native agent không? |
| OS và CPU | Có binary cho Linux `amd64` và/hoặc `arm64` không? |
| libc/ABI | Binary được build cho glibc, musl hay có cả hai biến thể? |
| Cách nạp | Nạp trực tiếp từ đường dẫn, giải nén vào temp hay tự tải khi chạy? |
| Hỗ trợ | Nhà cung cấp có công bố và kiểm thử Alpine/musl cho phiên bản đó không? |

Dependency tree giúp tìm nguồn gốc thư viện, nhưng không chứng minh binary native tương thích. Cần kiểm tra cả nội dung artifact và runtime behavior.

## 3. Tìm native binary bên trong JAR

Có thể liệt kê nội dung một JAR bằng `jar tf`:

```sh
jar tf library.jar | grep -E '\.so([.][0-9]+)*$|\.dll$|\.dylib$'
```

Nếu thư viện đóng gói native binary theo classifier hoặc thư mục nền tảng, tên đường dẫn có thể thể hiện `linux-x86_64`, `linux-aarch64`, `linux-musl` hoặc một biến thể tương tự. Không nên chỉ dựa vào tên thư mục để kết luận ABI; hãy trích xuất và kiểm tra file thực tế.

Với ứng dụng đóng gói dạng fat JAR hoặc Spring Boot executable JAR, một JAR khác có thể nằm bên trong thư mục như `BOOT-INF/lib`. `jar tf app.jar` chỉ liệt kê tên JAR lồng bên trong, không tự mở nội dung của từng JAR đó. Cần trích xuất các JAR lồng và lặp lại việc kiểm tra.

Ví dụ trên Linux có thể tạo thư mục kiểm tra riêng:

```sh
mkdir -p /tmp/native-audit
cd /tmp/native-audit
jar xf /app/app.jar
find . -type f \
  \( -name '*.so' -o -name '*.so.*' -o -name '*.dll' -o -name '*.dylib' \) \
  -print
```

Nếu ứng dụng dùng Spring Boot, kiểm tra tiếp các JAR trong `BOOT-INF/lib`. Cũng cần xem các dependency có tự tải binary từ resource hoặc tải từ mạng ở lần chạy đầu tiên hay không; những file đó có thể không xuất hiện trong JAR ứng dụng ban đầu.

`jdeps` hữu ích để phân tích dependency Java và module, ví dụ:

```sh
jdeps --multi-release 25 --print-module-deps app.jar
```

Nhưng `jdeps` không phải công cụ quét ABI ELF và không thể xác nhận một `.so` được build cho musl. Không dùng kết quả `jdeps` làm bằng chứng rằng ứng dụng không có native dependency.

## 4. Kiểm tra ELF, kiến trúc và shared library

Native binary Linux thường ở định dạng ELF. Sau khi trích xuất file `.so` hoặc executable, kiểm tra định dạng, kiến trúc và dependency động.

```sh
file /tmp/native-audit/path/libcodec.so
readelf -h /tmp/native-audit/path/libcodec.so
readelf -d /tmp/native-audit/path/libcodec.so | grep NEEDED
```

Các thông tin cần chú ý:

- `file` và `readelf -h` cho biết ELF class, endianness và machine architecture, ví dụ x86-64 hoặc AArch64.
- `readelf -d` liệt kê các shared library mà binary khai báo phụ thuộc qua mục `NEEDED`.
- Với executable có dynamic loader, `readelf -l` có thể hiển thị ELF interpreter mà binary yêu cầu.

Ví dụ kiểm tra interpreter:

```sh
readelf -l /usr/bin/some-helper | grep interpreter
```

Đường dẫn loader và danh sách symbol cần thiết có thể cho thấy binary được build cho môi trường glibc hoặc musl. Một file `.so` có tên giống nhau vẫn có thể khác kiến trúc, ABI hoặc dependency.

Trong image Alpine, có thể cài công cụ kiểm tra vào một image debug riêng hoặc tạm thời trong giai đoạn audit:

```sh
apk add --no-cache file binutils
```

Không nhất thiết phải giữ các công cụ này trong production image. Khi kiểm tra bằng `ldd`, chỉ dùng với binary đáng tin cậy trong môi trường kiểm soát; với file không rõ nguồn gốc, ưu tiên phân tích ELF tĩnh bằng `readelf`.

## 5. Kiểm tra native library được nạp lúc runtime

Quét JAR không phát hiện được mọi trường hợp. Native library có thể được:

- Tải từ resource rồi giải nén vào thư mục tạm.
- Chọn theo `os.name`, `os.arch` hoặc thuộc tính hệ thống.
- Nạp thông qua JNA hoặc JNI khi một chức năng lần đầu được gọi.
- Được Java agent nạp trước khi `main` bắt đầu.
- Gọi từ một executable bên ngoài thông qua `ProcessBuilder`.

Tìm trong source và cấu hình các điểm nạp thường gặp:

```java
System.load("/opt/native/libcodec.so");
System.loadLibrary("codec");
```

Rà soát cấu hình JVM như `-agentpath`, `-agentlib`, `-javaagent`, thuộc tính `java.library.path`, cấu hình JNA và các thư mục chứa native artifact. Với JNA, hãy kiểm tra phiên bản thư viện, cơ chế tìm kiếm và thư mục giải nén native của nó.

Nếu container dùng user không phải root hoặc filesystem read-only, kiểm tra thêm thư mục tạm. Một thư viện có thể tương thích ABI nhưng vẫn không nạp được nếu không thể ghi file native đã giải nén, hoặc file không có quyền thực thi phù hợp. Có thể cấu hình `java.io.tmpdir` đến một vị trí được cấp quyền ghi và được mount phù hợp.

## 6. Kiểm tra thư viện theo từng kiến trúc

Image đa kiến trúc không đảm bảo mọi native dependency trong ứng dụng đều đa kiến trúc. Một JAR có thể chứa binary x86-64 nhưng không có binary AArch64, hoặc ngược lại.

Hãy kiểm tra riêng từng target:

| Target | Cần xác minh |
|---|---|
| `linux/amd64` | JVM musl và mọi `.so`/executable có binary x86-64 tương thích |
| `linux/arm64` | JVM musl và mọi `.so`/executable có binary AArch64 tương thích |
| Kiến trúc khác | Nhà cung cấp JDK và native dependency có phát hành, duy trì binary tương ứng không |

Không nên build một native library trên máy x86 rồi copy sang image arm64. Nếu build native từ source, cần toolchain và target ABI chính xác. Kiểm thử trên máy cùng kiến trúc là tốt nhất; nếu dùng emulation, vẫn nên có kiểm thử cuối cùng trên phần cứng hoặc runner thực tế của kiến trúc đích.

## 7. Chạy thử trong image Alpine/musl đích

Sau khi phân tích tĩnh, chạy ứng dụng bằng đúng image JDK/JRE musl sẽ triển khai. Không dùng image glibc ở bước kiểm thử cuối vì nó có thể che giấu lỗi tương thích.

Ví dụ kiểm tra runtime cơ bản:

```sh
docker run --rm \
  --entrypoint sh \
  eclipse-temurin:25-jre-alpine-3.24 \
  -c 'java -version && ldd --version && apk info musl'
```

Sau đó chạy ứng dụng trong image đã build:

```sh
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -p 8080:8080 \
  my-service:alpine-test
```

Ví dụ trên giả định ứng dụng không cần ghi dữ liệu vào root filesystem và native library có thể nạp từ vị trí không yêu cầu thực thi file trong `/tmp`. Nếu thư viện giải nén `.so` vào `/tmp` rồi nạp bằng dynamic loader, mount `noexec` có thể khiến việc nạp thất bại; cần kiểm tra hành vi thực tế và cấp quyền tối thiểu phù hợp cho thư mục tạm.

Chỉ kiểm tra JVM khởi động là chưa đủ. Một số native dependency chỉ được nạp khi ứng dụng thực hiện chức năng tương ứng. Cần chạy smoke test và integration test cho tất cả đường chức năng quan trọng, ví dụ:

- Mở kết nối database và thực hiện truy vấn.
- Đọc/ghi dữ liệu qua embedded database nếu có.
- Nén và giải nén dữ liệu bằng native codec.
- Thiết lập network transport native.
- Xử lý ảnh, font, âm thanh hoặc tài liệu nếu có dùng thư viện native.
- Chạy agent giám sát, profiler hoặc công cụ bảo mật.
- Gọi executable phụ trợ và kiểm tra exit code, stdout/stderr.

## 8. Dấu hiệu lỗi thường gặp và cách điều tra

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `UnsatisfiedLinkError` | Không tìm thấy `.so`, sai kiến trúc, thiếu dependency hoặc ABI không tương thích | Xác định đường dẫn nạp, kiểm tra ELF, `NEEDED` và loader |
| `Error loading shared library` | Loader hoặc shared library không có trong image | Kiểm tra libc, dynamic loader và package runtime |
| `wrong ELF class` hoặc machine không phù hợp | Binary 32/64-bit hoặc kiến trúc CPU không khớp | Dùng `file` và `readelf -h` |
| `Error relocating` hoặc symbol không tìm thấy | Symbol/ABI không có trong libc hoặc dependency hiện tại | Kiểm tra binary được build cho musl hay glibc và version dependency |
| `Permission denied` khi nạp native | File hoặc thư mục không có quyền phù hợp; mount có thể là `noexec` | Kiểm tra owner, mode, mount options và `java.io.tmpdir` |
| Ứng dụng khởi động được nhưng một API thất bại | Native code chỉ được nạp khi chức năng đó chạy | Tạo integration test cho đúng chức năng và đường gọi |

Không nên xử lý lỗi bằng cách thêm hàng loạt package hoặc lớp tương thích vào image trước khi xác định binary đang thiếu gì. Hãy xác định dependency cụ thể, kiểm tra hỗ trợ musl từ nhà cung cấp và chọn bản dựng đúng ABI.

## 9. Quy trình chuyển ứng dụng sang Alpine

Một quy trình có thể áp dụng cho dự án thực tế:

1. Chốt JDK musl và phiên bản Alpine còn được nhà cung cấp duy trì.
2. Xuất dependency tree của runtime classpath cho Maven hoặc Gradle.
3. Lập danh sách JNI/JNA, agent, native transport, codec và executable ngoài.
4. Quét JAR/fat JAR và giải nén kiểm tra các native artifact lồng bên trong.
5. Kiểm tra ELF class, kiến trúc, loader và shared-library dependency.
6. Xác nhận nhà cung cấp có binary musl cho đúng phiên bản và kiến trúc.
7. Build image thử nghiệm, chạy bằng user và filesystem policy gần với production.
8. Chạy integration test trên `amd64` và `arm64` nếu cả hai kiến trúc được triển khai.
9. Theo dõi log khởi động, lỗi nạp native, hiệu năng và mức dùng tài nguyên.
10. Chỉ chuyển production khi mọi native dependency bắt buộc đã được xác nhận và có kế hoạch cập nhật.

Nếu một dependency thiết yếu chỉ có binary glibc và không có bản musl được duy trì, cân nhắc thay thư viện hoặc chọn JDK image dùng glibc. Giữ Alpine bằng mọi giá không phải mục tiêu kỹ thuật; mục tiêu là một runtime được hỗ trợ và có thể vận hành ổn định.

## 10. Ghi nhớ

- Bytecode Java thường độc lập với libc, còn JVM và native binary thì không.
- Rà soát dependency bắc cầu, không chỉ dependency trực tiếp.
- Kiểm tra nội dung JAR và cả JAR lồng bên trong fat JAR.
- `jdeps` phân tích dependency Java, không xác nhận ABI của ELF.
- Dùng `file` và `readelf` để kiểm tra kiến trúc, loader và shared-library dependency.
- Native library có thể chỉ được nạp khi một chức năng chạy; cần integration test trong image musl thật.
- Kiểm tra riêng `amd64` và `arm64`, thư mục tạm, quyền file và Java agent.
- Nếu native stack bắt buộc chỉ hỗ trợ glibc, hãy chọn image glibc được duy trì.

Chuyển ứng dụng Java sang Alpine là một thay đổi ở runtime và native dependency. Khi dependency tree, ELF metadata và các đường chạy thực tế đều được kiểm tra, nhóm phát triển có thể đưa ra quyết định dựa trên bằng chứng về khả năng tương thích musl trước khi triển khai.

# Kiểm thử binary trên môi trường chạy thực để phát hiện thiếu thư viện

Một **GraalVM Native Image** là executable native được tạo cho một hệ điều hành và kiến trúc cụ thể. Việc biên dịch thành công trên máy phát triển chưa chứng minh binary sẽ chạy được trong container hoặc máy chủ production. Môi trường chạy có thể thiếu shared library, dùng phiên bản libc không tương thích, không có thư viện JNI, thiếu chứng chỉ CA, timezone database hoặc resource mà ứng dụng cần đọc.

Vì vậy, sau khi build Spring Boot Native Image, cần kiểm thử **chính executable đã tạo trong môi trường chạy gần với production nhất**. Bài học này hướng dẫn kiểm tra kiến trúc và ABI, liệt kê thư viện động, xác minh JNI và serialization, chạy smoke test trong run image thực tế, rồi chẩn đoán các lỗi thường gặp trên Linux, macOS, Windows và container.

## 1. Vì sao build thành công nhưng binary vẫn không chạy?

Native Image compiler kiểm tra và liên kết chương trình trong môi trường build. Một số dependency hệ thống được liên kết động và chỉ được nạp khi executable khởi chạy. Máy build có thể đã cài sẵn thư viện mà run image không có.

Ví dụ:

- Máy build có `libz.so.1`, nhưng container runtime không có.
- Binary được build trên hệ thống có glibc mới, trong khi máy đích dùng glibc cũ hơn.
- JNI library tồn tại trên laptop nhưng không được copy vào image.
- JNI library chính có mặt, nhưng một thư viện phụ thuộc của nó bị thiếu.
- Executable là Linux x86-64 nhưng được chạy trên node ARM64.
- Container có binary nhưng thiếu CA certificate hoặc timezone data.
- Ứng dụng cần file cấu hình, template hoặc native resource không được đưa vào image.
- Container chạy bằng user không có quyền đọc file hoặc ghi thư mục tạm.

Luồng kiểm thử nên đi theo thứ tự:

~~~mermaid
flowchart TD
    A["Native executable đã build"] --> B["Kiểm tra OS, CPU architecture và ABI"]
    B --> C["Liệt kê shared library dependencies"]
    C --> D["Kiểm tra JNI libraries và metadata"]
    D --> E["Kiểm tra resource, CA, timezone, permissions"]
    E --> F["Chạy trong run image / host đích"]
    F --> G["Smoke test và integration test"]
    G --> H{"Tất cả đường đi quan trọng hoạt động?"}
    H -->|Có| I["Đóng gói và phát hành artifact"]
    H -->|Không| J["Phân tích loader, log, syscall và cấu hình"]
    J --> B
~~~

**Điểm mấu chốt:** kiểm tra file binary trên máy build chỉ là bước đầu. Kết quả cần được xác nhận trên runtime image hoặc máy đích sẽ thực sự chạy ứng dụng.

## 2. Binary native phụ thuộc vào nền tảng nào?

Executable native không phải artifact đa nền tảng như một file JAR Java. Nó được tạo cho một target cụ thể:

| Thành phần | Ví dụ | Rủi ro khi khác môi trường |
|---|---|---|
| Hệ điều hành | Linux, Windows, macOS | Định dạng executable và API hệ điều hành khác nhau |
| CPU architecture | x86-64, AArch64/ARM64 | Instruction set và ABI không tương thích |
| Binary format | ELF, PE, Mach-O | Loader của OS chỉ hiểu định dạng tương ứng |
| C library | glibc, musl | Binary cần symbol hoặc ABI mà runtime không cung cấp |
| C++ runtime | libstdc++, libc++ | JNI/native dependency có thể yêu cầu runtime cụ thể |
| Shared libraries | zlib, OpenSSL, libstdc++ | Thiếu file hoặc sai major version sẽ không load được |
| JNI libraries | libpayment.so, libcrypto-adapter.so | Không tìm thấy file, sai kiến trúc hoặc thiếu dependency con |

Ví dụ lỗi:

~~~text
cannot execute binary file: Exec format error
~~~

Thông báo này thường xuất hiện khi định dạng hoặc kiến trúc binary không phù hợp với môi trường chạy. Hãy kiểm tra `file` và kiến trúc của node/container trước khi điều tra reflection hoặc Spring.

Một binary Linux x86-64 không thể được đổi thành ARM64 chỉ bằng cách copy file. Cần build riêng cho target hoặc dùng cơ chế build đa kiến trúc với builder/toolchain phù hợp.

## 3. Kiểm tra định dạng và kiến trúc trước khi chạy

Trên Linux:

~~~bash
# Kiểm tra loại binary và kiến trúc
file ./application

# Số kiến trúc máy
uname -m
uname -s
~~~

Ví dụ kết quả:

~~~text
application: ELF 64-bit LSB pie executable, x86-64, ...
x86_64
Linux
~~~

Nếu binary là AArch64, máy chạy phải hỗ trợ ARM64. Trong container, kiểm tra cả host và platform của image:

~~~bash
docker image inspect example/orders:native \
  --format '{{.Os}}/{{.Architecture}}'
~~~

Trên macOS:

~~~bash
file ./application
uname -m
otool -hv ./application
~~~

`file` giúp nhận diện Mach-O và kiến trúc. `otool` cung cấp thông tin header và dependency của binary trên macOS.

Trên Windows PowerShell:

~~~powershell
Get-Item .\application.exe | Select-Object Name, Length, LastWriteTime
$env:PROCESSOR_ARCHITECTURE
~~~

Có thể dùng Developer Command Prompt với `dumpbin /headers application.exe` để xem machine type và định dạng PE. Công cụ Dependencies cũng giúp quan sát dependency bắc cầu và kiến trúc DLL.

**Không dùng binary build cho OS này để kiểm thử trên OS khác.** Nếu mục tiêu triển khai là Linux container, kiểm thử trong Linux run image hoặc node Linux có kiến trúc giống production.

## 4. Shared library là gì và vì sao cần kiểm tra?

Shared library là thư viện native được loader nạp khi process khởi chạy hoặc khi chương trình yêu cầu. Trên Linux, các file thường có hậu tố `.so`; macOS dùng `.dylib` hoặc framework; Windows dùng `.dll`.

Một native executable có thể phụ thuộc vào:

- C library và dynamic loader.
- Thư viện hệ thống như zlib, OpenSSL hoặc C++ runtime.
- Thư viện native do ứng dụng hoặc dependency cung cấp.
- JNI library được gọi từ Java code.
- Các dependency bắc cầu của JNI library.

Ví dụ, ứng dụng gọi thư viện mã hóa qua JNI. File `libcrypto-adapter.so` có thể tồn tại, nhưng chính nó lại cần `libssl.so` hoặc `libcrypto.so`. Nếu dependency bắc cầu không có trong run image, loader vẫn không thể nạp JNI library.

Tên thư viện minh họa không có nghĩa mọi native image đều cần chúng. **Chỉ thêm đúng thư viện được binary hoặc JNI dependency yêu cầu**, tránh cài toàn bộ package hệ thống theo phỏng đoán.

## 5. Kiểm tra dependency trên Linux bằng readelf và ldd

Với ELF binary, bắt đầu bằng:

~~~bash
# Kiểm tra loại binary và kiến trúc
file ./application

# Liệt kê dynamic section và các thư viện NEEDED
readelf -d ./application | grep NEEDED

# Kiểm tra dynamic loader/interpreter
readelf -l ./application | grep interpreter

# Xem symbol version requirements, nếu cần
readelf --version-info ./application
~~~

Dynamic section có thể cho thấy các dependency như:

~~~text
Shared library: [libc.so.6]
Shared library: [libz.so.1]
Shared library: [libstdc++.so.6]
~~~

Danh sách thực tế tùy toolchain, cấu hình và native dependency. Một số binary có thể liên kết tĩnh một phần hoặc toàn bộ một số thư viện; vì vậy không phải lúc nào cũng có danh sách `NEEDED` dài.

Để xem loader có tìm được dependency trong môi trường hiện tại:

~~~bash
ldd ./application
~~~

Nếu có:

~~~text
libz.so.1 => not found
~~~

thì runtime hiện tại chưa tìm thấy thư viện đó trong search path. Cần cài package cung cấp đúng SONAME vào runtime image hoặc cấu hình đường dẫn phù hợp.

**Chỉ chạy `ldd` trên binary đáng tin cậy do dự án tạo ra.** Với file không rõ nguồn, ưu tiên `readelf -d` hoặc `objdump -p` để đọc thông tin ELF mà không cần nhờ loader thực thi binary.

Nếu `ldd` trả về `not a dynamic executable`, không vội kết luận binary bị hỏng. Có thể binary được liên kết tĩnh, không phải ELF phù hợp hoặc được tạo cho kiến trúc/ABI khác. Đối chiếu với `file` và `readelf`.

## 6. Hiểu glibc, musl và lỗi phiên bản ABI

Trên Linux, binary có thể phụ thuộc glibc hoặc musl. Hai implementation này không thể thay thế cho nhau một cách tùy ý.

Một lỗi thường gặp:

~~~text
version 'GLIBC_2.34' not found
~~~

Điều đó cho biết binary yêu cầu symbol version của glibc mới hơn phiên bản runtime đang cung cấp. Các nguyên nhân có thể gồm build trên distribution mới rồi chạy trên distribution cũ, hoặc dùng run image không tương thích với môi trường build.

Hướng xử lý:

1. Xác định glibc mà binary yêu cầu bằng `readelf --version-info`.
2. Kiểm tra glibc trong runtime image.
3. Build trên base image/toolchain tương thích với runtime mục tiêu.
4. Hoặc chọn runtime image có glibc mới hơn và được tổ chức hỗ trợ.
5. Build lại và chạy kiểm thử trên đúng run image.

Alpine Linux thường dùng musl thay vì glibc. Một binary được build cho glibc không mặc nhiên chạy được trên Alpine. Nếu muốn dùng Alpine/musl, phải xác nhận GraalVM và toolchain của phiên bản đang dùng hỗ trợ target musl, build với cấu hình phù hợp (ví dụ tùy chọn `--libc=musl` nếu được hỗ trợ) và kiểm thử trên chính runtime musl đó.

Không nên chỉ cài một gói tương thích glibc không chính thức vào Alpine rồi xem đó là giải pháp production. Điều này làm tăng độ phức tạp ABI và rủi ro vận hành.

## 7. Kiểm tra thư viện trên macOS và Windows

### macOS

Dùng `otool -L` để xem các dynamic libraries:

~~~bash
file ./application
otool -L ./application
otool -l ./application
~~~

Nếu dependency có install name trỏ tới một đường dẫn không tồn tại, loader có thể báo `Library not loaded`. Kiểm tra đường dẫn, `@rpath`, `@loader_path` và `@executable_path`; không copy thư viện vào một thư mục bất kỳ rồi giả định loader sẽ tìm thấy.

### Windows

Trong Developer Command Prompt:

~~~bat
dumpbin /headers application.exe
dumpbin /dependents application.exe
~~~

`dumpbin /dependents` liệt kê DLL được import trực tiếp. Dùng công cụ Dependencies để xem thêm dependency bắc cầu và kiến trúc DLL.

Các lỗi như:

~~~text
The code execution cannot proceed because VCRUNTIME140.dll was not found
~~~

cho thấy runtime DLL cần thiết không có trên máy. Cần cài hoặc đóng gói đúng Microsoft Visual C++ runtime theo chính sách phát hành của ứng dụng, với đúng kiến trúc.

**Không trộn DLL x86 với executable x64**, và không lấy DLL từ một máy phát triển bất kỳ rồi chép vào production mà không kiểm tra nguồn, phiên bản và license.

## 8. JNI: kiểm tra cả metadata lẫn native library

JNI cho phép Java code gọi hàm native và native code gọi ngược vào Java. Với Native Image, cần kiểm tra hai lớp riêng:

1. **JNI metadata:** các class, method, field hoặc constructor mà native code truy cập qua JNI phải được nhận diện/đăng ký theo yêu cầu của Native Image.
2. **Native library:** file thư viện JNI và mọi dependency bắc cầu phải có trong môi trường chạy, đúng OS, kiến trúc và ABI.

Ví dụ Java khai báo native method:

~~~java
public final class NativeChecksum {

    static {
        System.loadLibrary("checksum");
    }

    public native long calculate(byte[] data);
}
~~~

Trên Linux, thư viện thường có tên `libchecksum.so`. Khi chạy, dynamic loader còn phải tìm được các thư viện mà `libchecksum.so` phụ thuộc.

Lỗi thường gặp:

~~~text
java.lang.UnsatisfiedLinkError: no checksum in java.library.path
~~~

hoặc:

~~~text
java.lang.UnsatisfiedLinkError: /opt/native/libchecksum.so:
libcrypto.so.3: cannot open shared object file: No such file or directory
~~~

Lỗi thứ nhất thường liên quan tới việc tìm JNI library. Lỗi thứ hai cho biết JNI library đã được tìm thấy nhưng một dependency của nó bị thiếu.

### Kiểm tra JNI library trên Linux

~~~bash
file /opt/native/libchecksum.so
readelf -d /opt/native/libchecksum.so | grep NEEDED
ldd /opt/native/libchecksum.so
~~~

Nếu thư viện nằm ngoài các thư mục loader mặc định, cần bố trí nó vào thư mục phù hợp hoặc cấu hình search path. `LD_LIBRARY_PATH` có thể giúp loader tìm shared library, nhưng nên ưu tiên đường dẫn triển khai rõ ràng, cấu hình RUNPATH/RPATH phù hợp hoặc cơ chế package của container.

`java.library.path` là thuộc tính tìm JNI library ở tầng Java runtime; nó không thay thế search path của dynamic loader cho dependency bắc cầu của file ELF. Hãy kiểm tra cả hai lớp nếu dùng `System.loadLibrary`.

### JNI metadata

GraalVM có cấu hình riêng cho JNI, thường được biểu diễn trong `jni-config.json` ở các toolchain sử dụng file metadata. Spring `RuntimeHints` cũng có API JNI để đăng ký kiểu cần thiết khi phù hợp với phiên bản Spring Framework.

Tracing Agent có thể ghi nhận JNI access trong các luồng đã chạy. Tuy nhiên, agent chỉ thấy những đường đi được thực thi; cần test cả callback từ native code vào Java, không chỉ lời gọi Java sang native.

## 9. Serialization: binary chạy được vẫn có thể thiếu kiểu dữ liệu

Serialization không phải shared library của hệ điều hành. Đây là một nhóm dynamic access khác cần kiểm tra khi chuyển ứng dụng sang Native Image.

Java serialization, framework serializer hoặc data binding có thể cần constructor, field, record component, method hoặc metadata của kiểu dữ liệu. Native Image có thể không suy ra đầy đủ các kiểu được lựa chọn động qua object graph hoặc dữ liệu bên ngoài.

Ví dụ một DTO:

~~~java
public record PaymentEvent(
    String paymentId,
    BigDecimal amount
) implements Serializable {
}
~~~

Nếu ứng dụng dùng Java serialization cho kiểu được chọn động, hãy xác nhận kiểu đó được đăng ký cho serialization theo yêu cầu của GraalVM. Với Spring, có thể dùng serialization hints trong `RuntimeHints` hoặc annotation phù hợp cho binding/serialization. Đừng nhầm reflection hint cho constructor với serialization registration; hai mục đích này có thể cần metadata riêng.

Các lỗi như `ClassNotFoundException`, `InvalidClassException` hoặc thiếu reflection registration trong lúc deserialize cần được phân loại riêng:

- Class có trong executable hay không?
- Kiểu có được đăng ký cho serialization không?
- Constructor/field cần thiết có được chuẩn bị không?
- Schema hoặc `serialVersionUID` có tương thích giữa các phiên bản không?
- Dữ liệu được serialize trên JVM có tương thích với phiên bản native đang chạy không?

Test nên dùng dữ liệu đại diện, bao gồm dữ liệu được lưu từ phiên bản trước, không chỉ serialize rồi deserialize trong cùng một tiến trình mới.

## 10. Thử nghiệm trong đúng run image của container

Một sai lầm phổ biến là build trong builder image rồi chỉ copy executable vào một image cực nhỏ hoặc `scratch`. Builder có thể có compiler, libc, OpenSSL, zlib và nhiều công cụ mà run image không có.

Với Cloud Native Buildpacks, builder và run image có vai trò khác nhau:

- **Builder image** cung cấp môi trường detect/build, compiler, buildpacks và công cụ tạo artifact.
- **Run image** cung cấp hệ điều hành và các thư viện cần thiết để chạy artifact.
- **Final application image** kết hợp executable, launch metadata và các thành phần runtime cần thiết.

Nếu dùng Spring Boot `bootBuildImage` hoặc `spring-boot:build-image`, hãy kiểm thử chính image được tạo ra:

~~~bash
docker image inspect example/orders:native \
  --format '{{.Os}}/{{.Architecture}}'

docker run --rm --publish 8080:8080 example/orders:native
~~~

Không kiểm thử riêng executable trong builder rồi kết luận image runtime sẽ chạy. Hãy chạy smoke test trong final image hoặc một image có cùng run image và package runtime.

Nếu tự viết Dockerfile multi-stage, stage build và stage runtime phải được lựa chọn có chủ đích. Ví dụ cấu trúc khái quát:

~~~dockerfile
FROM build-stage AS build
WORKDIR /workspace
COPY . .
RUN ./gradlew nativeCompile

FROM runtime-base AS runtime
WORKDIR /app
COPY --from=build /workspace/build/native/nativeCompile/application /app/application
USER 10001
ENTRYPOINT ["/app/application"]
~~~

Đây là skeleton, không phải Dockerfile hoàn chỉnh cho mọi dự án. `runtime-base` phải cung cấp libc và shared libraries cần thiết; nếu ứng dụng dùng JNI, cần copy JNI libraries và cấu hình loader path. Không chọn `scratch` trước khi xác nhận binary thực sự không cần shared library hoặc file hệ thống khác.

## 11. Tại sao distroless hoặc scratch vẫn có thể lỗi?

Image nhỏ giúp giảm bề mặt tấn công và dung lượng triển khai, nhưng không có nghĩa mọi native executable đều có thể chạy trong image tối giản.

`scratch` không cung cấp shell, package manager, CA bundle, timezone data hoặc shared libraries. `distroless` cũng chỉ chứa tập file được chọn cho mục đích cụ thể; không phải mọi biến thể đều có libc, CA certificate hoặc thư viện native mà ứng dụng yêu cầu.

Trước khi chọn image tối giản, xác minh:

- Dynamic loader có mặt ở đường dẫn mà ELF interpreter yêu cầu.
- glibc/musl và các shared library có đúng phiên bản.
- JNI libraries cùng dependency bắc cầu có trong image.
- CA certificate bundle có mặt nếu gọi HTTPS.
- Timezone database có mặt nếu ứng dụng cần zone như `Asia/Ho_Chi_Minh`.
- Resource ngoài, file cấu hình, font, locale hoặc thư mục tạm có sẵn theo yêu cầu.
- User không đặc quyền có quyền đọc/chạy executable và ghi các thư mục được phép.

Nếu thiếu shell trong distroless, có thể dùng debug image tương ứng hoặc chạy công cụ chẩn đoán ở một container tạm có cùng filesystem/runtime packages. Không nhất thiết phải cài shell vào image production chỉ để debug.

## 12. Kiểm tra resource và file hệ thống ngoài shared library

Một binary có thể khởi động nhưng vẫn thất bại ở một tính năng vì thiếu file môi trường:

| Thành phần | Triệu chứng | Cách xác minh |
|---|---|---|
| CA certificate bundle | HTTPS báo PKIX/certificate path error | Kiểm tra đường dẫn CA và package chứng chỉ |
| Timezone database | Zone ID không tìm thấy hoặc thời gian hiển thị sai | Kiểm tra `/usr/share/zoneinfo` và timezone runtime |
| Locale data | Định dạng ngày/số hoặc ký tự khác mong đợi | Kiểm tra locale và dữ liệu locale có trong image |
| Font | PDF/ảnh thiếu chữ hoặc lỗi render | Kiểm tra font file và fontconfig nếu dùng |
| Template/config/schema | Không tìm thấy resource | Phân biệt classpath resource và file system mount |
| Thư mục `/tmp` | Lỗi tạo file tạm | Kiểm tra tồn tại, quyền ghi và dung lượng |
| DNS resolver | Không kết nối được hostname | Kiểm tra DNS trong container/network namespace |
| File socket/device | Không mở được thiết bị hoặc socket | Kiểm tra mount, quyền và policy container |

Classpath resource cần được đưa vào Native Image bằng resource hints hoặc cơ chế AOT phù hợp. File bên ngoài như `/etc/orders/rules.json` phải được mount/copy vào runtime filesystem. Việc một file có trong repository không bảo đảm nó sẽ tồn tại ở đường dẫn filesystem tương ứng trong container.

## 13. Chạy smoke test có ý nghĩa trên runtime image

Một smoke test nên xác nhận các đường đi quan trọng, không chỉ kiểm tra process còn sống.

Ví dụ:

~~~bash
# Chạy container ở background
docker run -d --name orders-native-test \
  -p 18080:8080 \
  example/orders:native

# Đợi ứng dụng sẵn sàng; thời gian khởi động native vẫn có thể khác nhau.
for attempt in $(seq 1 30); do
  if curl --fail --silent http://localhost:18080/actuator/health >/dev/null; then
    break
  fi
  sleep 1
done

# Kiểm tra health endpoint
curl --fail http://localhost:18080/actuator/health

# Kiểm tra một nghiệp vụ có serialization
curl --fail \
  -H 'Content-Type: application/json' \
  -d '{"paymentId":"P-100","amount":125.50}' \
  http://localhost:18080/api/payments

# Kết thúc container test
docker rm -f orders-native-test
~~~

Các URL và endpoint chỉ là ví dụ; thay bằng API thực của ứng dụng. Nếu ứng dụng dùng database hoặc broker, smoke test nên xác nhận kết nối tới dependency đó trong môi trường test. Với JNI, gọi ít nhất một native method thật. Với serialization, dùng payload có kiểu dữ liệu động và kiểm tra dữ liệu trả về.

Nếu không có Actuator, dùng endpoint readiness do ứng dụng cung cấp. Không dùng TCP port mở làm bằng chứng duy nhất rằng toàn bộ ứng dụng đã sẵn sàng.

## 14. Chạy bằng user không đặc quyền và filesystem hạn chế

Container production thường chạy non-root và có thể dùng read-only root filesystem. Binary chạy được với quyền root chưa chắc chạy được trong cấu hình đó.

Kiểm tra:

- User có quyền execute file binary và JNI libraries.
- File cấu hình, certificate và resource có quyền đọc.
- Ứng dụng chỉ ghi vào volume/thư mục được cho phép.
- `java.io.tmpdir` hoặc thư mục tạm native mà thư viện sử dụng có thể ghi được.
- Port được chọn phù hợp với user và policy của container.
- Không có giả định rằng process được phép tạo file trong thư mục cài đặt.

Ví dụ chạy container với user cụ thể:

~~~bash
docker run --rm \
  --user 10001:10001 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --publish 8080:8080 \
  example/orders:native
~~~

Đây là ví dụ hardening. Nếu ứng dụng cần ghi file upload hoặc dữ liệu, mount volume riêng với owner/permission phù hợp. Không bật `--read-only` trước khi biết rõ ứng dụng cần ghi vào đâu; hãy dùng nó như một bài kiểm thử để phát hiện các giả định filesystem.

## 15. Chẩn đoán thiếu thư viện bằng strace và loader diagnostics

Trên Linux, `strace` giúp quan sát file open và syscall thất bại:

~~~bash
strace -f -e trace=file -o /tmp/orders-files.log ./application
~~~

Sau đó tìm các dòng có `ENOENT` hoặc `EACCES`:

~~~bash
grep -E 'ENOENT|EACCES' /tmp/orders-files.log
~~~

`ENOENT` cho biết đường dẫn không tồn tại tại thời điểm truy cập; `EACCES` cho biết quyền truy cập bị từ chối. Cần phân biệt file tùy chọn được thử nhiều vị trí với dependency thực sự làm ứng dụng thất bại.

Với glibc dynamic loader, có thể bật:

~~~bash
LD_DEBUG=libs ./application
~~~

Loader sẽ in thông tin tìm kiếm thư viện. Output có thể rất lớn và chứa đường dẫn môi trường; chỉ bật trong phiên debug.

Khi lỗi chỉ xuất hiện trong container, chạy chẩn đoán **bên trong cùng runtime image** hoặc một image debug tương đương. `ldd` trên host build không chứng minh thư viện có trong container.

## 16. Ma trận lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `Exec format error` | Sai OS hoặc CPU architecture | Build đúng target và kiểm tra image platform |
| `No such file or directory` dù binary tồn tại | ELF interpreter/dynamic loader không có | Kiểm tra `readelf -l`, runtime libc và loader path |
| `libxyz.so: cannot open shared object file` | Thiếu shared library hoặc loader không tìm thấy | Kiểm tra `readelf -d`, `ldd`, cài package hoặc sửa search path |
| `GLIBC_2.xx not found` | Runtime glibc cũ hơn yêu cầu binary | Build trên base tương thích hoặc nâng run image |
| `Error loading shared library` trên Alpine | Khác biệt musl/glibc hoặc thiếu dependency | Dùng đúng libc target, build lại cho musl nếu được hỗ trợ |
| `UnsatisfiedLinkError: no ... in java.library.path` | JNI library không được tìm thấy | Kiểm tra tên file, đường dẫn, OS/arch và cấu hình load |
| JNI library tìm thấy nhưng báo thiếu lib phụ thuộc | Thiếu dependency bắc cầu | Chạy `ldd` trên chính JNI library trong runtime image |
| `PKIX path building failed` | CA certificate thiếu hoặc truststore không phù hợp | Cài/cung cấp CA bundle và test HTTPS |
| Zone ID không tìm thấy | Thiếu timezone database hoặc dữ liệu zone | Cung cấp tzdata hoặc cấu hình phù hợp |
| `Permission denied` | User không có quyền execute/read/write | Sửa owner, mode và volume mount |
| Deserialize thất bại trên native | Thiếu serialization/reflection metadata hoặc schema mismatch | Đăng ký kiểu cần thiết và test dữ liệu đại diện |
| Resource trả về null | Resource hint hoặc đường dẫn file sai | Kiểm tra classpath resource và file mount |

Thông báo `No such file or directory` khi file executable vẫn hiện diện thường khiến người mới tìm nhầm đường dẫn binary. Trên Linux, một nguyên nhân quan trọng là **interpreter được ghi trong ELF header không có trong runtime image**. Dùng `readelf -l` để kiểm tra mục `Requesting program interpreter`.

## 17. Test trên đúng kiến trúc và run image phát hành

CI nên có ít nhất một job kiểm thử trên cùng loại OS/libc/architecture với môi trường triển khai.

Ví dụ ma trận:

| Artifact | Runtime test | Điều cần xác nhận |
|---|---|---|
| Linux x86-64, glibc | Run image production x86-64 | Loader, glibc, JNI, certificate và API |
| Linux ARM64, glibc | Run image/node ARM64 | Binary đúng kiến trúc, native dependencies cùng kiến trúc |
| Linux musl/Alpine | Runtime musl thực tế | Binary được build đúng musl target và mọi thư viện có mặt |
| Windows x64 | Windows host/runtime tương ứng | PE/DLL dependencies và JNI DLL |
| macOS ARM64 | macOS ARM64 | Mach-O dependencies, framework và native libraries |

Không nhất thiết phải hỗ trợ mọi target. Chỉ cần xác định platform thực sự phát hành và kiểm thử từng platform đó. Nếu image multi-arch, kiểm tra từng manifest platform và chạy smoke test trên runner/node tương ứng; việc manifest tồn tại không chứng minh binary ở mọi architecture đều hoạt động.

## 18. Quy trình kiểm thử trước khi phát hành

Một pipeline kiểm tra binary có thể gồm:

1. **Ghi nhận build target:** OS, architecture, GraalVM/JDK version, libc/toolchain, builder và run image.
2. **Kiểm tra binary:** `file`, ELF interpreter, `NEEDED` libraries, symbol versions.
3. **Kiểm tra JNI:** xác nhận library file, kiến trúc, metadata và dependency bắc cầu.
4. **Kiểm tra serialization:** chạy test với các kiểu và payload được chọn động.
5. **Kiểm tra resource:** CA, timezone, locale, font, template, config và file ngoài.
6. **Chạy final image:** không chỉ chạy trên builder hoặc host build.
7. **Chạy non-root/read-only test:** xác nhận quyền file, thư mục tạm và volume.
8. **Smoke/integration test:** gọi endpoint, truy cập database/broker, HTTPS, JNI và serialization.
9. **Lưu artifact và bằng chứng:** image digest, binary checksum, dependency report, log test và toolchain version.

Nếu có nhiều môi trường runtime, chạy ma trận theo từng target. Một test pass trên Ubuntu glibc không chứng minh binary tương thích Alpine musl hoặc Windows.

## 19. Bài thực hành: phát hiện thư viện bị thiếu trong container

Giả sử ứng dụng Spring Boot có endpoint gọi thư viện JNI `checksum` để tính checksum cho file. Trên máy dev, ứng dụng chạy bình thường; trong runtime container, endpoint trả lỗi `UnsatisfiedLinkError`.

### Bước 1 — Kiểm tra binary ứng dụng

~~~bash
file ./application
readelf -l ./application | grep interpreter
readelf -d ./application | grep NEEDED
~~~

Xác định target và các dependency trực tiếp của executable.

### Bước 2 — Kiểm tra JNI library

~~~bash
file ./lib/libchecksum.so
readelf -d ./lib/libchecksum.so | grep NEEDED
ldd ./lib/libchecksum.so
~~~

Nếu thấy:

~~~text
libcrypto.so.3 => not found
~~~

thì cần cung cấp đúng package có `libcrypto.so.3` trong runtime image hoặc build lại JNI library với dependency phù hợp.

### Bước 3 — Kiểm tra đường dẫn

Đảm bảo `libchecksum.so` thực sự có trong image, đúng quyền đọc và đúng kiến trúc. Xác nhận code dùng `System.loadLibrary("checksum")` có thể tìm thấy library theo cơ chế của runtime; kiểm tra thêm search path cho dependency bắc cầu của ELF loader.

### Bước 4 — Chạy trong final image

Khởi động chính image sẽ phát hành, gọi endpoint tính checksum và xác nhận kết quả. Nếu container tối giản không có `ldd`, dùng debug image tương đương hoặc kiểm tra ELF trên host với `readelf`, rồi xác nhận bằng smoke test trong final runtime.

### Bước 5 — Kiểm tra cả serialization

Gửi payload có trường binary/base64 hoặc DTO được deserialize trước khi gọi JNI. Xác nhận cả bước deserialize lẫn native method đều hoạt động, để phân biệt lỗi metadata serialization với lỗi loader JNI.

### Bảng ghi nhận

| Hạng mục | Kết quả cần ghi |
|---|---|
| OS/architecture | Linux x86-64, ARM64 hoặc target thực tế |
| libc/runtime | glibc/musl và phiên bản |
| Native executable dependencies | Danh sách `NEEDED`, interpreter |
| JNI dependencies | File JNI và dependency bắc cầu |
| Serialization | Kiểu/payload đã kiểm thử |
| Runtime image | Builder/run image tag hoặc digest |
| Permissions | User, quyền file, thư mục tạm |
| Smoke test | Endpoint và native operation thành công |

## 20. Ghi nhớ

Native executable chỉ chạy ổn định khi **binary, OS, kiến trúc, ABI, shared libraries, JNI libraries và runtime resources** khớp với môi trường đích. Build thành công trên máy phát triển không chứng minh các dependency hệ thống đã có trong final container.

Hãy kiểm tra ELF/PE/Mach-O, dynamic loader và dependency bằng công cụ của nền tảng; kiểm tra JNI library cùng các thư viện bắc cầu; đăng ký metadata cho serialization/JNI khi cần; và chạy smoke test trên chính run image hoặc máy có cấu hình tương đương production. Các file CA, timezone, font, template, quyền truy cập và thư mục tạm cũng là một phần của runtime contract.

**Bằng chứng phát hành nên là kết quả chạy của artifact cuối trong môi trường đích**, đi kèm platform, image digest, dependency report và test log. Cách làm này giúp phát hiện lỗi thiếu thư viện trước khi native executable được triển khai rộng.

### Tài liệu tham khảo

- GraalVM — Native Image Compatibility and Runtime: https://www.graalvm.org/reference-manual/native-image/
- GraalVM — JNI in Native Image: https://www.graalvm.org/reference-manual/native-image/dynamic-features/JNI/
- GraalVM — Serialization in Native Image: https://www.graalvm.org/reference-manual/native-image/dynamic-features/Serialization/
- Spring Boot — Container Images: https://docs.spring.io/spring-boot/reference/packaging/container-images/
- Linux man-pages — ldd(1), readelf(1), ld.so(8).

Cú pháp công cụ và metadata có thể khác theo phiên bản GraalVM, hệ điều hành và builder. Khi triển khai, hãy kiểm tra đúng toolchain và runtime image đã được pin trong dự án.

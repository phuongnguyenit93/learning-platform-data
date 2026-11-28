# Alpine Linux port từ Java 16 và khác biệt musl với glibc

Java 16 đưa hỗ trợ Alpine Linux vào OpenJDK thông qua JEP 386. Điểm kỹ thuật quan trọng của thay đổi này là HotSpot có thể chạy trên hệ thống dùng `musl libc`, thư viện C mặc định của Alpine, bên cạnh các bản dựng Linux quen thuộc dùng `glibc`.

Đây là một thay đổi ở nền tảng triển khai của JDK, không phải cú pháp Java mới. Mã Java thuần vẫn chạy trên JVM tương thích, nhưng JVM và các thư viện native phải phù hợp với hệ điều hành, kiến trúc CPU và C library của môi trường chạy. Khác biệt này vẫn rất quan trọng khi đóng gói ứng dụng Java vào container hiện đại.

## 1. JEP 386 đã thay đổi điều gì?

Trước thay đổi này, nhiều bản dựng OpenJDK cho Linux được xây dựng để sử dụng `glibc`. Alpine Linux dùng `musl libc`, nên một binary JDK phụ thuộc `glibc` không thể mặc nhiên chạy như trên Ubuntu hoặc Debian. Các image Alpine trước đây thường phải thêm lớp tương thích hoặc dùng một bản dựng JDK riêng phù hợp với musl.

JEP 386 đưa port Alpine Linux vào OpenJDK 16, với mục tiêu hỗ trợ HotSpot trên Alpine và các môi trường Linux dùng musl. Port ban đầu tập trung vào kiến trúc x64 và AArch64. Nhờ vậy, nhà cung cấp JDK có thể phát hành binary và container image được xây dựng cho musl.

Ý nghĩa thực tế:

- Có thể chạy JVM được xây dựng cho musl trực tiếp trên Alpine mà không phải giả định rằng môi trường đã có glibc.
- Container Java có thể dùng Alpine làm base image khi toàn bộ thành phần native tương thích.
- Ứng dụng Java vẫn cần kiểm tra các thư viện native, JNI/JNA và công cụ hệ thống đi kèm.

JEP 386 không biến một JDK glibc thành JDK musl. Cần chọn đúng bản dựng JDK dành cho C library của image đích.

## 2. musl libc và glibc là gì?

`libc` là thư viện C cung cấp các dịch vụ nền tảng mà chương trình native thường sử dụng, chẳng hạn cấp phát bộ nhớ, xử lý chuỗi, luồng, file, thời gian và giao tiếp với hệ điều hành.

- **glibc** là GNU C Library, được dùng phổ biến trên nhiều bản phân phối Linux như Debian, Ubuntu và Red Hat Enterprise Linux.
- **musl libc** là một implementation khác của giao diện C library, được Alpine Linux chọn làm thư viện mặc định. musl có thiết kế gọn nhẹ và hướng đến tính tuân thủ các tiêu chuẩn liên quan.

Cả hai đều cung cấp các chức năng C library, nhưng không có nghĩa binary liên kết với thư viện này sẽ tương thích nhị phân hoàn toàn với thư viện kia.

| Tiêu chí | glibc | musl libc |
|---|---|---|
| Môi trường thường gặp | Debian, Ubuntu, RHEL và nhiều distro Linux khác | Alpine Linux và một số hệ thống Linux khác |
| Mục tiêu thiết kế | Thư viện C GNU với hệ sinh thái và mức tương thích rộng | Thư viện C gọn nhẹ, đơn giản và hướng đến tiêu chuẩn |
| Binary native | Thường liên kết với loader, symbol và ABI của glibc | Liên kết với loader và ABI của musl |
| Thư viện native bên thứ ba | Nhiều nhà cung cấp phát hành binary glibc | Cần binary musl hoặc bản dựng tương thích đã được kiểm chứng |
| Lựa chọn triển khai | Phù hợp khi phụ thuộc native chủ yếu nhắm đến glibc | Phù hợp khi cần Alpine và toàn bộ native stack hỗ trợ musl |

Sự khác biệt nằm ở userspace và ABI của C library, không phải ở ngôn ngữ Java hay ở việc Alpine dùng một loại kernel Linux khác.

## 3. Vì sao JVM cần bản dựng phù hợp với musl?

JVM không chỉ là bytecode Java. HotSpot là chương trình native, được biên dịch thành binary cho hệ điều hành và kiến trúc CPU cụ thể. Khi khởi động, JVM cần dynamic loader và các thư viện hệ thống mà binary của nó liên kết đến.

Một JDK được xây dựng cho glibc có thể yêu cầu loader hoặc symbol của glibc. Alpine mặc định cung cấp musl, nên việc chỉ sao chép thư mục JDK glibc vào image Alpine không đảm bảo JVM khởi động được. Có thể gặp lỗi thiếu loader, thiếu shared library hoặc symbol không được hỗ trợ.

Vì vậy, khi chọn JDK cho container, phải khớp ít nhất các yếu tố:

1. Hệ điều hành và phiên bản base image.
2. Kiến trúc CPU, ví dụ `amd64` hoặc `arm64`.
3. C library mà bản dựng JDK yêu cầu, ví dụ glibc hoặc musl.
4. Phiên bản JDK và chính sách hỗ trợ của nhà cung cấp.

Không nên xem các lớp tương thích như `gcompat` là giải pháp bảo đảm cho mọi ứng dụng glibc. Chúng có thể giúp một số chương trình hoạt động, nhưng không thay thế việc chọn binary native đúng ABI và kiểm thử các phụ thuộc thực tế.

## 4. Ảnh hưởng đến ứng dụng Java và thư viện native

Bytecode Java trong file `.class` hoặc JAR không được biên dịch trực tiếp theo glibc hay musl. Nếu ứng dụng chỉ dùng Java API thuần và JDK tương thích, cùng một JAR thường có thể chạy trên cả hai loại image.

Rủi ro xuất hiện khi JVM hoặc ứng dụng nạp mã native. Các thành phần thường cần kiểm tra gồm:

- Thư viện JNI do dự án tự viết hoặc do thư viện bên thứ ba cung cấp.
- Thư viện JNA và các gói có binary native đóng sẵn.
- Native transport, thư viện nén, xử lý ảnh, cơ sở dữ liệu nhúng hoặc thư viện mật mã.
- Java agent, profiler, APM agent và công cụ giám sát có thành phần native.
- Executable phụ trợ được gọi bằng `ProcessBuilder`.

Ví dụ, một JAR có thể chạy tốt trên Alpine cho đến khi gọi `System.loadLibrary("imagecodec")`. Nếu file `libimagecodec.so` được build cho glibc, JVM musl có thể không nạp được thư viện đó. Cần tìm binary musl do nhà cung cấp phát hành hoặc build lại từ source bằng toolchain phù hợp.

### JNI và thư viện native

JNI xác định cách Java gọi mã native, nhưng không làm cho binary native trở nên độc lập với nền tảng. Thư viện `.so` vẫn phải khớp hệ điều hành, kiến trúc, ABI và các thư viện phụ thuộc.

Khi build JNI cho Alpine:

- Build trên môi trường musl tương ứng hoặc dùng toolchain cross-compile đã cấu hình rõ target musl.
- Kiểm tra toàn bộ dependency của `.so`, không chỉ file thư viện chính.
- Đóng gói các runtime package cần thiết vào image cuối.
- Kiểm thử bằng chính image production và kiến trúc CPU đích.

Build một thư viện native trên Ubuntu rồi chép sang Alpine ở bước cuối không tự chuyển binary đó từ glibc sang musl. Multi-stage Docker build cũng không thay đổi ABI của file đã biên dịch.

## 5. Chọn Alpine hay image dùng glibc?

Alpine thường có base image nhỏ, hữu ích khi kích thước image là một mục tiêu quan trọng. Tuy nhiên, kích thước base image nhỏ không tự động làm ứng dụng khởi động nhanh hơn, an toàn hơn hoặc tổng image cuối cùng nhỏ hơn. Nếu cần thêm nhiều gói tương thích và công cụ debug, lợi thế kích thước có thể giảm.

| Tình huống | Hướng lựa chọn |
|---|---|
| Ứng dụng chủ yếu dùng Java API thuần, JDK có bản musl được hỗ trợ | Có thể chọn Alpine sau khi kiểm thử runtime |
| Tất cả JNI/JNA và native agent đều có bản musl tương thích | Alpine là lựa chọn khả thi |
| Một thư viện native quan trọng chỉ phát hành binary glibc | Chọn image glibc hoặc thay thế thư viện bằng bản hỗ trợ musl |
| Cần tương thích rộng với phần mềm native phổ biến | Ưu tiên image glibc như Ubuntu hoặc UBI |
| Đội vận hành cần công cụ chẩn đoán quen thuộc và hỗ trợ từ nhà cung cấp | Chọn base image nằm trong ma trận hỗ trợ của nhà cung cấp |

Tài liệu image Gradle hiện hành cũng mô tả Alpine là biến thể nhỏ nhất nhưng dùng musl, nên một số native library cần xử lý bổ sung; Ubuntu được chọn làm base mặc định với mức tương thích rộng hơn. Đây là tiêu chí thực tế khi cân nhắc chi phí vận hành cùng kích thước image.

## 6. Ví dụ dùng JDK musl trong Docker

Ví dụ dưới đây dùng các tag Eclipse Temurin Alpine hiện hành để minh họa build và runtime cùng dựa trên Alpine 3.24. Tag cụ thể cần được kiểm tra lại trong danh sách image của nhà cung cấp khi cập nhật phiên bản.

```dockerfile
# Build ứng dụng bằng JDK được xây dựng cho Alpine/musl.
FROM eclipse-temurin:25-jdk-alpine-3.24 AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -B -DskipTests package

# Chạy ứng dụng bằng runtime JRE cũng dành cho Alpine/musl.
FROM eclipse-temurin:25-jre-alpine-3.24 AS runtime
WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Trong ví dụ:

- Build stage và runtime stage dùng cùng họ image Alpine và cùng phiên bản Alpine.
- JDK và JRE đều là bản dựng dành cho musl.
- Artifact JAR được chuyển từ build stage sang runtime stage.
- Nếu dự án tạo JNI hoặc executable native, các artifact đó phải được build cho musl và kiến trúc runtime.

Nếu dùng `jlink` để tạo runtime riêng, hãy tạo runtime bằng JDK dành cho đúng target platform và đưa runtime đó vào image tương thích. `jlink` chỉ chọn module và tạo runtime image; nó không chuyển một runtime glibc thành musl hoặc ngược lại.

Không cần giữ JDK trong production image nếu ứng dụng chỉ cần runtime. Dùng JRE image hoặc runtime tùy chỉnh giúp tránh mang theo compiler và công cụ phát triển không cần thiết.

## 7. Kiểm tra libc và thư viện trong container

Khi chẩn đoán môi trường, có thể kiểm tra hệ điều hành, kiến trúc, libc và JDK ngay trong container:

```sh
cat /etc/os-release
uname -m
ldd --version
apk info musl
java -version
```

Trên Alpine, `ldd --version` thường hiển thị thông tin của musl. `apk info musl` xác nhận package musl được cài đặt. Những lệnh này giúp xác định môi trường, nhưng chưa đủ để kết luận mọi thư viện native của ứng dụng tương thích.

Nếu cần kiểm tra một executable hoặc shared library, có thể dùng `file` và `readelf` từ gói công cụ phù hợp trong môi trường debug:

```sh
file /app/native/libimagecodec.so
readelf -d /app/native/libimagecodec.so | grep NEEDED
```

`readelf -d` hiển thị các thư viện động mà file yêu cầu. Với executable, `readelf -l` có thể cho biết dynamic loader được khai báo trong ELF interpreter. Không nên chỉ dựa vào tên file `.so`; hãy kiểm tra kiến trúc và dependency thực tế.

## 8. Kiểm thử trước khi đưa lên production

Kiểm thử trên máy phát triển dùng glibc không đủ để xác nhận ứng dụng sẽ chạy trên Alpine. Cần chạy integration test trong đúng image, đúng kiến trúc và đúng runtime mà production sử dụng.

Checklist kiểm thử:

- JVM khởi động và báo đúng phiên bản JDK.
- Tất cả JNI/JNA, agent và thư viện native được nạp thành công.
- Các executable gọi qua `ProcessBuilder` chạy được trên Alpine.
- DNS, kết nối mạng, TLS, chứng chỉ CA và timezone hoạt động đúng trong môi trường triển khai.
- Các chức năng dùng locale, font, xử lý ảnh hoặc nén được kiểm tra nếu ứng dụng có sử dụng.
- Health check, log, metrics, profiling và thao tác shutdown hoạt động đúng.
- Image được build cho từng kiến trúc mục tiêu, đặc biệt khi triển khai cả `amd64` và `arm64`.

Không cần kiểm tra mọi khác biệt libc nếu ứng dụng không dùng chức năng liên quan, nhưng phải kiểm thử các đường chạy thực tế có gọi native code hoặc tiện ích hệ thống.

## 9. Lưu ý về phiên bản JDK và hỗ trợ hiện nay

JEP 386 được giới thiệu trong Java 16, nhưng Java 16 là feature release không thuộc nhóm LTS và đã qua thời gian hỗ trợ thông thường. Không nên chọn JDK 16 cho triển khai production mới chỉ vì bài học này nói về port Alpine.

Hãy dùng một phiên bản JDK LTS còn được nhà cung cấp hỗ trợ và chọn đúng biến thể Alpine/musl của phiên bản đó. Ví dụ, danh sách Docker Official Images của Eclipse Temurin hiện công bố các tag Alpine cho JDK 21 và JDK 25, cùng các tag JRE tương ứng. Không phải mọi nhà cung cấp hoặc mọi phiên bản JDK đều có đủ mọi tổ hợp hệ điều hành và kiến trúc; hãy xác nhận ma trận hỗ trợ trước khi ghim tag hoặc digest.

Khi cập nhật image, cần cập nhật cả bản vá bảo mật của JDK lẫn base Alpine. Nên ghim phiên bản cụ thể hoặc digest cho bản dựng có thể tái lập, đồng thời có quy trình định kỳ nâng bản vá.

## 10. Ghi nhớ

- JEP 386 đưa port Alpine/musl vào OpenJDK từ Java 16; đây là thay đổi nền tảng của JVM, không phải thay đổi cú pháp Java.
- Alpine dùng musl libc, trong khi nhiều Linux image phổ biến dùng glibc.
- Bytecode Java thường có thể dùng chung, nhưng JVM và native library phải khớp libc, kiến trúc và ABI.
- Không sao chép JDK hoặc `.so` glibc vào Alpine rồi giả định chúng sẽ chạy.
- Alpine có thể giảm kích thước image, nhưng cần đánh giá khả năng tương thích native và chi phí vận hành.
- Dùng JDK LTS hiện được hỗ trợ, chọn đúng bản dựng musl và kiểm thử trong image production.

## Tài liệu tham khảo

- [JEP 386: Alpine Linux Port](https://openjdk.org/jeps/386) — mục tiêu và phạm vi port Alpine trong OpenJDK.
- [Eclipse Temurin Official Images](https://github.com/docker-library/docs/blob/master/eclipse-temurin/README.md) — tag JDK/JRE Alpine, lưu ý musl và cách tạo runtime bằng `jlink`.
- [Gradle Docker Images](https://docs.gradle.org/current/userguide/docker.html) — so sánh base image Alpine với Ubuntu và lưu ý về native libraries.
- [AdoptOpenJDK 16 Available](https://blog.adoptopenjdk.net/2021/03/adoptopenjdk-16-available/) — bối cảnh JEP 386 khi Java 16 được phát hành.

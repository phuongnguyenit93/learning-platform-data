# Phân biệt JAR modular với runtime image

JAR modular và runtime image đều thuộc Java Module System, nhưng giải quyết hai bài toán khác nhau. **JAR modular là artifact ứng dụng hoặc thư viện có module descriptor**. **Runtime image là môi trường chạy Java đã được liên kết từ các module cần thiết**, thường được tạo bằng jlink.

JAR modular được phân phối như một file archive trong module path và cần một Java runtime phù hợp. Runtime image chứa runtime cần thiết cùng các module ứng dụng đã được liên kết. Vì vậy, runtime image giúp triển khai ứng dụng mà không yêu cầu người dùng cài JDK hoặc JRE riêng.

## 1. JAR modular

JAR modular là file JAR có module descriptor, thường là module-info.class ở thư mục gốc. Descriptor khai báo tên module, dependency, package được export hoặc open, service được sử dụng và provider được cung cấp.

Ví dụ:

~~~text
com.example.app.jar
|-- module-info.class
|-- com/
    |-- example/
        |-- app/
            |-- Main.class
~~~

Module descriptor:

~~~java
module com.example.app {
    requires java.logging;
    exports com.example.app.api;
}
~~~

Tạo JAR modular từ thư mục out đã chứa module-info.class và class đã biên dịch:

~~~bash
jar --create --file mods/com.example.app.jar --main-class com.example.app.Main -C out .
~~~

Kiểm tra archive:

~~~bash
jar --describe-module --file mods/com.example.app.jar
jar --list --file mods/com.example.app.jar
~~~

Chạy module từ module path:

~~~bash
java --module-path mods --module com.example.app
~~~

Hoặc chỉ định main class:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

JAR modular chỉ đóng gói module ứng dụng hoặc thư viện. Nó không tự mang theo toàn bộ Java runtime. Khi chạy, lệnh java vẫn được lấy từ JDK/JRE cài trên máy hoặc từ runtime image phân phối kèm ứng dụng.

## 2. Runtime image

Runtime image là cấu trúc thư mục chứa runtime Java đã được liên kết với tập module được chọn. Công cụ jlink tạo image từ các module có thể resolve, gồm module nền tảng của JDK và module ứng dụng trên module path.

Cấu trúc thường gặp:

~~~text
app-image/
|-- bin/
|   |-- java
|   |-- keytool
|   |-- app
|-- conf/
|-- legal/
|-- lib/
|   |-- modules
|   |-- security/
|-- release
~~~

Tên file và thư mục chi tiết có thể khác theo hệ điều hành và cấu hình. Điểm quan trọng là image có Java launcher và module image chứa các module đã liên kết. Nó không phải một file JAR duy nhất.

Runtime image có thể bao gồm module Java nền tảng mà ứng dụng cần, module ứng dụng được link, provider module phù hợp với service binding, Java launcher và các thành phần runtime cần thiết.

Runtime image được tạo cho nền tảng mục tiêu. Image tạo trên Windows không chạy trực tiếp trên Linux hoặc macOS. Khi phát hành nhiều nền tảng, cần tạo image tương ứng cho từng hệ điều hành và kiến trúc.

## 3. So sánh

| Tiêu chí | JAR modular | Runtime image |
|---|---|---|
| Bản chất | Archive chứa một module | Môi trường Java đã liên kết |
| Định dạng | Một file JAR | Thư mục image có cấu trúc runtime |
| Thành phần | Class, resource và module descriptor | Java runtime, module image và launcher |
| Mục đích | Phân phối module ứng dụng hoặc thư viện | Triển khai runtime tùy chỉnh |
| Runtime cần có | Cần JDK/JRE tương thích ở nơi chạy | Đã chứa runtime cần thiết |
| Công cụ tạo | javac và jar | jlink |
| Số module | Một JAR modular đại diện một module | Một image có thể chứa nhiều module |
| Nền tảng | JAR thường dùng trên nhiều nền tảng có runtime phù hợp | Image gắn với hệ điều hành và kiến trúc mục tiêu |
| Cách khởi chạy | java --module-path ... --module ... | Java launcher nằm trong image |

Không nên xem runtime image là một loại JAR lớn. JAR modular là artifact phân phối module; runtime image là đầu ra triển khai chứa môi trường chạy đã được liên kết.

## 4. jlink và module path

jlink đọc module descriptor, resolve dependency graph và liên kết các module được chọn thành runtime image. Module ứng dụng được cung cấp qua module path cùng các module hệ thống của JDK.

Ví dụ thư mục module:

~~~text
mods/
|-- com.example.app.jar
|-- com.example.data.jar
|-- com.example.logging.jar
~~~

Giả sử com.example.app yêu cầu com.example.data, còn com.example.data yêu cầu java.sql. Khi link module gốc com.example.app, jlink resolve dependency cần thiết và đưa module trong graph vào image.

Lệnh trên Linux hoặc macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output app-image
~~~

Trên Windows, dùng dấu chấm phẩy để phân tách module path:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output app-image
~~~

Module path gồm thư mục jmods của JDK và thư mục chứa JAR modular. add-modules chỉ định root module. jlink resolve dependency requires từ root module và tạo image ở thư mục output.

Không cần liệt kê thủ công dependency bắc cầu nếu chúng được khai báo đúng trong requires. Mọi module ứng dụng cần link phải có mặt trên module path và là module mà jlink có thể resolve.

## 5. Tạo launcher tùy chỉnh

Có thể yêu cầu jlink tạo launcher có tên riêng:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --launcher app=com.example.app/com.example.app.Main --output app-image
~~~

Launcher app được tạo trong thư mục bin của image. Người dùng chạy ứng dụng bằng launcher này mà không cần tự viết lệnh java --module.

Nếu không tạo launcher tùy chỉnh, gọi Java launcher trực tiếp:

~~~bash
app-image/bin/java --module com.example.app
~~~

Trên Windows, executable tương ứng nằm trong thư mục bin và có tên java.exe.

Launcher tùy chỉnh đơn giản hóa script triển khai và cố định entry point. Nó không tự đóng gói tài nguyên ngoài như file cấu hình, dữ liệu hoặc chứng chỉ mà ứng dụng cần.

## 6. Chọn module cho image

jlink bắt đầu từ một hoặc nhiều root module. Các dependency requires được resolve theo module graph.

| Tùy chọn | Ý nghĩa |
|---|---|
| --module-path | Vị trí tìm module đầu vào |
| --add-modules | Root module cần link |
| --bind-services | Resolve thêm provider module cho service được sử dụng |
| --limit-modules | Giới hạn tập module quan sát được khi resolve |
| --launcher | Tạo launcher tùy chỉnh cho module và main class |
| --output | Thư mục runtime image đầu ra |
| --list-plugins | Liệt kê plugin jlink có sẵn |

Ví dụ ứng dụng dùng ServiceLoader và cần provider module:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output app-image
~~~

--bind-services yêu cầu linker xem xét provider module phù hợp với service được sử dụng trong module graph. Nếu ứng dụng tải plugin động hoặc có cấu hình plugin riêng, cần thiết kế tập module được link phù hợp; không giả định mọi plugin JAR sẽ tự xuất hiện trong image.

Có thể đưa nhiều root module:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app,com.example.monitoring --output app-image
~~~

Mỗi root có thể kéo theo dependency riêng. Image chứa tập module cần thiết theo cấu hình resolve và tùy chọn linker.

## 7. Tối ưu runtime image

jlink có tùy chọn giảm kích thước image hoặc bỏ thành phần không cần thiết:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --strip-debug --no-header-files --no-man-pages --compress=2 --output app-image
~~~

- --strip-debug loại bỏ thông tin debug khỏi module được link.
- --no-header-files không đưa header native vào image.
- --no-man-pages không đưa trang hướng dẫn vào image.
- --compress=2 áp dụng mức nén mà JDK hỗ trợ.

Các tùy chọn này có thể giảm dung lượng nhưng cũng loại bỏ nội dung hữu ích cho phát triển hoặc chẩn đoán. Không nên áp dụng máy móc cho image dùng trong debug. Hãy đo kích thước và kiểm tra ứng dụng sau khi link.

Kích thước image không chỉ phụ thuộc số JAR ứng dụng. Module JDK có thể kéo theo module khác, provider có thể được bind, và native runtime component cũng chiếm dung lượng. Kiểm tra danh sách module sau khi tạo để biết image thực sự chứa gì.

## 8. Kiểm tra và chạy image

Dùng Java launcher trong image để liệt kê module:

~~~bash
app-image/bin/java --list-modules
~~~

Mô tả một module:

~~~bash
app-image/bin/java --describe-module com.example.app
~~~

Kiểm tra phiên bản runtime:

~~~bash
app-image/bin/java --version
~~~

Chạy ứng dụng:

~~~bash
app-image/bin/java --module com.example.app
~~~

Hoặc chạy launcher tùy chỉnh:

~~~bash
app-image/bin/app
~~~

Nếu ứng dụng không khởi chạy, kiểm tra root module, requires dependency, provider cần thiết, launcher, file cấu hình, resource ngoài JAR, native library, hệ điều hành và kiến trúc mục tiêu.

Một image link thành công không bảo đảm mọi tính năng ứng dụng đều hoạt động. Resource ngoài module, cấu hình, native library và kết nối hệ thống bên ngoài vẫn cần được kiểm thử.

## 9. Giới hạn của jlink và automatic module

jlink cần module có cấu trúc phù hợp để tạo image. Automatic module không phải đầu vào thay thế trực tiếp cho explicit module trong quy trình link thông thường. Nếu thư viện chỉ có JAR không module descriptor và đang được dùng như automatic module, cần chuyển nó thành explicit module hoặc đóng gói lại phù hợp trước khi link.

Hướng xử lý:

- Nâng cấp thư viện lên phiên bản cung cấp module-info.class.
- Tạo module descriptor nếu có thể kiểm soát source và dependency.
- Đóng gói lại thành modular JAR và kiểm tra package, service metadata, dependency.
- Thay thế thư viện bằng implementation đã hỗ trợ module system.

Không tạo descriptor giả chỉ để jlink chấp nhận artifact nếu chưa xác định đúng requires, exports, opens, uses và provides. Descriptor sai có thể làm ứng dụng resolve được nhưng lỗi khi chạy.

jlink tạo runtime image chứ không tạo installer hoàn chỉnh. Nếu cần bộ cài, shortcut, file association hoặc tích hợp hệ điều hành, có thể kết hợp jpackage với runtime image và tài nguyên triển khai.

## 10. JAR modular, runtime image và jpackage

~~~text
Source code
    |
    | javac
    v
Compiled module
    |
    | jar
    v
Modular JAR(s)
    |
    | jlink
    v
Custom runtime image
    |
    | jpackage
    v
Application package / installer
~~~

| Công cụ | Đầu ra | Vai trò |
|---|---|---|
| javac | Class file và module-info.class | Biên dịch module |
| jar | Modular JAR | Đóng gói module ứng dụng hoặc thư viện |
| jlink | Runtime image | Liên kết runtime tùy chỉnh |
| jpackage | Gói ứng dụng hoặc installer | Đóng gói ứng dụng cho người dùng cuối, có thể kèm runtime image |

jpackage có thể dùng runtime image đã tạo hoặc tạo image phù hợp trong quá trình đóng gói tùy cấu hình. JAR modular và runtime image có thể cùng xuất hiện trong pipeline phát hành nhưng phục vụ mục đích khác nhau.

## 11. Chọn artifact phân phối

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Phân phối thư viện để ứng dụng khác sử dụng | Modular JAR |
| Phân phối module ứng dụng cho môi trường đã có Java phù hợp | Modular JAR hoặc nhiều modular JAR |
| Muốn người dùng không cần cài JDK/JRE riêng | Runtime image |
| Chỉ muốn chứa module Java ứng dụng cần | Runtime image bằng jlink |
| Chạy ứng dụng trên nhiều hệ điều hành | Tạo image riêng cho từng nền tảng |
| Cần installer, shortcut hoặc tích hợp hệ điều hành | jpackage, thường kết hợp runtime image |
| Cần cập nhật thư viện độc lập | Modular JAR |
| Cần runtime đã kiểm soát module và phiên bản | Runtime image |

Nếu môi trường máy chủ đã quản lý Java runtime, modular JAR có thể dễ cập nhật và triển khai hơn. Nếu phát hành ứng dụng desktop hoặc công cụ độc lập cho người dùng cuối, runtime image giúp kiểm soát runtime và tránh phụ thuộc vào Java cài đặt trên máy.

## 12. Ghi nhớ

JAR modular là file archive có module descriptor, dùng để phân phối một module. Runtime image là môi trường Java đã liên kết từ các module được chọn, có Java launcher và runtime component cần thiết. jlink lấy module từ module path, resolve dependency và tạo image; nó không chỉ đóng gói lại JAR.

Dùng modular JAR khi cần phân phối module độc lập và dùng runtime image khi cần phân phối cả môi trường chạy tùy chỉnh. Kiểm tra module bằng jar --describe-module, kiểm tra nội dung image bằng java --list-modules và chạy ứng dụng bằng launcher nằm trong image. Với phát hành cho người dùng cuối, cân nhắc jpackage để tạo gói cài đặt phù hợp nền tảng.

## Tài liệu tham khảo

- Oracle JDK — The jlink Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html
- Oracle JDK — The jar Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html
- Oracle JDK — The jpackage Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html
- Java Platform Module System — Module API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html

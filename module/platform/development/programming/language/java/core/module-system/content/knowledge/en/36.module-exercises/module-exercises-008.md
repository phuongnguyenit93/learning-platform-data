# Tạo runtime image bằng jlink

jlink là công cụ của JDK dùng để tạo runtime image tùy chỉnh từ các module đã được resolve. Thay vì yêu cầu máy đích cài JDK hoặc JRE đầy đủ, ứng dụng có thể được phân phối cùng một image chứa Java runtime và các module cần thiết để chạy ứng dụng.

JAR modular và runtime image giải quyết hai việc khác nhau. JAR modular đóng gói một module ứng dụng hoặc thư viện. Runtime image là môi trường chạy Java đã liên kết từ một tập module, thường được tạo bằng jlink. Nếu cần installer, shortcut hoặc tích hợp hệ điều hành, có thể dùng jpackage sau bước tạo image.

## 1. jlink tạo ra gì?

Runtime image là một thư mục có cấu trúc chứa runtime Java đã liên kết. Cấu trúc thường gặp:

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

Chi tiết file và thư mục phụ thuộc hệ điều hành, kiến trúc và cấu hình jlink. Thư mục bin chứa Java launcher và các công cụ runtime được giữ lại. lib chứa module image và thư viện runtime; conf chứa cấu hình; legal chứa thông tin giấy phép.

Image không phải JAR hay installer. Nó là môi trường Java có thể chạy trực tiếp trên nền tảng tương ứng. Image tạo cho Windows không thể được coi là image dùng chung cho Linux hoặc macOS. Cần tạo và kiểm thử image riêng cho từng hệ điều hành và kiến trúc mục tiêu.

## 2. Điều kiện đầu vào

jlink cần các module có thể resolve. Thông thường cần:

- JDK phù hợp với phiên bản Java mà ứng dụng yêu cầu.
- Các module ứng dụng có module descriptor hợp lệ.
- Các dependency modular cần thiết.
- Thư mục jmods của JDK để tìm module nền tảng.
- Một thư mục output dành cho image mới.

jlink làm việc với explicit module như module hệ thống, modular JAR, JMOD hoặc exploded module. JAR trên classpath và automatic module không phải đầu vào thay thế trực tiếp cho explicit module trong quy trình link. Nếu thư viện chỉ là JAR thường, hãy nâng cấp hoặc modular hóa nó trước khi link.

Kiểm tra công cụ:

~~~bash
java --version
javac --version
jlink --version
~~~

Đảm bảo java, javac và jlink đến từ cùng một JDK. JAVA_HOME nên trỏ tới JDK đó; thư mục jmods thường nằm tại JAVA_HOME/jmods.

## 3. Chuẩn bị ứng dụng modular

Ví dụ module có tên com.example.app và main class com.example.app.Main.

Cấu trúc source:

~~~text
src/
|-- com.example.app/
    |-- module-info.java
    |-- com/
        |-- example/
            |-- app/
                |-- Main.java
~~~

Module descriptor:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Main class:

~~~java
package com.example.app;

import java.util.logging.Logger;

public class Main {
    private static final Logger LOG =
            Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOG.info("Application started");
        System.out.println("Hello from a custom runtime image");
    }
}
~~~

java.base được mọi module phụ thuộc ngầm định nên không cần khai báo requires java.base.

Biên dịch module vào thư mục mods:

~~~bash
javac -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

Sau khi biên dịch, thư mục exploded module có module-info.class và các class trong package. Có thể đóng gói thành modular JAR nếu pipeline build cần archive:

~~~bash
jar --create --file mods/com.example.app.jar --main-class com.example.app.Main -C mods/com.example.app .
~~~

jlink có thể sử dụng exploded module hoặc modular JAR làm đầu vào. Không cần tạo JAR chỉ để giải nén lại nếu build đã tạo sẵn exploded module hợp lệ.

## 4. Tạo runtime image cơ bản

Lệnh jlink cần biết nơi tìm module hệ thống và module ứng dụng:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output app-image
~~~

Ý nghĩa:

1. --module-path chỉ định vị trí tìm module. Ví dụ gồm thư mục jmods của JDK và thư mục mods chứa exploded module hoặc modular JAR.
2. --add-modules chỉ định root module cần đưa vào cấu hình.
3. jlink resolve các requires của root module và dependency cần thiết.
4. --output chỉ định thư mục runtime image đầu ra.

Trên Windows, dấu phân cách module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output app-image
~~~

Trên Linux và macOS, dấu phân cách thường là dấu hai chấm. Dùng đúng dấu phân cách của hệ điều hành trong script build.

Nếu module path thiếu dependency, jlink báo lỗi resolution. Hãy xác định module thiếu và bổ sung đúng artifact; không thêm ngẫu nhiên mọi JAR vào để che lỗi.

## 5. Root module và dependency resolution

--add-modules chỉ định root module cần có trong image. jlink dùng module descriptor để resolve các dependency requires, bao gồm dependency bắc cầu cần thiết cho module graph.

Ví dụ:

~~~text
com.example.app
    |
    +-- requires com.example.orders
    |       |
    |       +-- requires com.example.persistence
    |
    +-- requires java.logging
~~~

Nếu com.example.app là root, các dependency cần thiết sẽ được resolve theo descriptor. Không cần liệt kê từng dependency requires nếu module graph được khai báo đầy đủ.

Có thể chỉ định nhiều root module:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app,com.example.monitoring --output app-image
~~~

Dùng nhiều root khi một module cần có mặt nhưng không được kéo vào qua dependency thông thường. Tùy chọn --limit-modules giới hạn tập module được quan sát trong quá trình resolution. Nếu giới hạn quá chặt, dependency hợp lệ có thể không được tìm thấy.

## 6. Dùng jlink với ServiceLoader

Nếu ứng dụng dùng ServiceLoader, module consumer cần khai báo uses và module provider cần khai báo provides ... with ....

Ví dụ consumer:

~~~java
module com.example.app {
    uses com.example.spi.GreetingService;
}
~~~

Provider module:

~~~java
module com.example.greeting.provider {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.greeting.provider.DefaultGreetingService;
}
~~~

Nếu muốn linker tìm và liên kết provider phù hợp với các service được sử dụng, dùng --bind-services:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output app-image
~~~

--bind-services yêu cầu resolution xem xét service binding và provider module phù hợp trên module path. Provider cần có module descriptor đúng và nằm trong các nguồn module mà linker quan sát.

Không giả định mọi plugin sẽ tự động xuất hiện trong image. Plugin tải động từ thư mục ngoài image hoặc từ ModuleLayer riêng cần chiến lược phân phối và nạp riêng. Nếu plugin phải nằm trong image, xác định rõ root/service binding và kiểm tra module thực tế có được link hay không.

## 7. Tạo launcher tùy chỉnh

Có thể yêu cầu jlink tạo launcher có tên riêng:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --launcher app=com.example.app/com.example.app.Main --output app-image
~~~

Launcher app được tạo trong thư mục bin của image. Cú pháp launcher là tên launcher, dấu bằng, rồi module name và main class được phân tách bằng dấu gạch chéo.

Nếu không tạo launcher riêng, gọi Java launcher bên trong image:

~~~bash
app-image/bin/java --module com.example.app
~~~

Trên Windows, executable tương ứng nằm trong app-image/bin và có tên java.exe. Tên và phần mở rộng launcher tùy nền tảng.

Launcher tùy chỉnh cố định entry point nhưng không tự đóng gói file cấu hình, dữ liệu, chứng chỉ, native library hoặc file ngoài module mà ứng dụng cần. Những tài nguyên đó phải được đưa vào gói triển khai theo cách riêng.

## 8. Tối ưu kích thước image

jlink có các tùy chọn để giảm kích thước hoặc bỏ thành phần không cần thiết:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --strip-debug --no-header-files --no-man-pages --compress=2 --output app-image
~~~

| Tùy chọn | Tác dụng |
|---|---|
| --strip-debug | Loại bỏ thông tin debug khỏi module được link |
| --no-header-files | Không đưa header native vào image |
| --no-man-pages | Không đưa trang hướng dẫn vào image |
| --compress=2 | Bật mức nén tương ứng mà JDK hỗ trợ |
| --include-locales | Giới hạn locale data được đưa vào image |

Các tùy chọn tối ưu có thể làm mất dữ liệu hữu ích cho debug hoặc chẩn đoán. Hãy tạo image baseline trước, đo kích thước, áp dụng từng tùy chọn và chạy lại test.

Nếu ứng dụng cần locale ngoài tập mặc định, kiểm tra module jdk.localedata và cấu hình include-locales phù hợp. Không loại bỏ dữ liệu locale chỉ để giảm dung lượng nếu ứng dụng cần định dạng ngày, số hoặc thông điệp ở các locale đó.

## 9. Phân tích module cần thiết

jdeps có thể phân tích dependency bytecode và gợi ý các module hệ thống cần thiết:

~~~bash
jdeps --module-path "$JAVA_HOME/jmods:mods" --print-module-deps mods/com.example.app.jar
~~~

Kết quả hỗ trợ xác định dependency được phát hiện từ bytecode. jdeps không phát hiện đầy đủ mọi dependency tạo động bằng reflection, ServiceLoader, tên class từ cấu hình, JNI hoặc native code. Không xem kết quả này là danh sách đầy đủ tuyệt đối; hãy kết hợp với module descriptor, cấu hình ứng dụng và test runtime.

Kiểm tra descriptor của archive:

~~~bash
jar --describe-module --file mods/com.example.app.jar
~~~

## 10. Kiểm tra image sau khi tạo

Chạy các lệnh kiểm tra từ Java launcher nằm trong image.

Liệt kê module:

~~~bash
app-image/bin/java --list-modules
~~~

Mô tả module ứng dụng:

~~~bash
app-image/bin/java --describe-module com.example.app
~~~

Kiểm tra phiên bản runtime:

~~~bash
app-image/bin/java --version
~~~

Chạy ứng dụng bằng image:

~~~bash
app-image/bin/java --module com.example.app
~~~

Hoặc chạy launcher tùy chỉnh:

~~~bash
app-image/bin/app
~~~

Trên Windows, dùng executable trong thư mục app-image/bin. Dùng Java launcher của image giúp xác nhận ứng dụng đang chạy với runtime đã link thay vì vô tình dùng JDK cài toàn cục trên máy phát triển.

## 11. Kiểm thử trên môi trường sạch

Một runtime image nên được kiểm thử trong môi trường không dựa vào JDK của máy build. Copy image sang máy ảo hoặc container phù hợp nền tảng, nơi không cài JDK khác, rồi chạy ứng dụng.

Kiểm thử tối thiểu:

- Launcher khởi động đúng module và main class.
- Các module dependency có mặt trong image.
- Service provider được tìm thấy nếu ứng dụng dùng ServiceLoader.
- File cấu hình và resource bên ngoài module được tìm thấy.
- Native library và JNI hoạt động nếu ứng dụng có dùng.
- Locale, timezone, charset và security configuration đáp ứng nhu cầu.
- Kết nối database, network và hệ thống ngoài hoạt động.
- Logging, file output và đường dẫn tương đối đúng trong thư mục triển khai.
- Ứng dụng khởi động được sau khi đổi working directory.
- Image chạy trên đúng hệ điều hành và kiến trúc mục tiêu.

Một image link thành công chỉ chứng minh quá trình liên kết module hoàn tất. Nó không chứng minh mọi đường chạy nghiệp vụ hoặc dependency ngoài JDK đều hoạt động.

## 12. Giới hạn của jlink

jlink không phải công cụ đóng gói mọi loại JAR thành runtime. Các module đầu vào phải có thể resolve theo module system. JAR không modular, automatic module và classpath dependency cần được xử lý trước khi link.

Các hướng xử lý thư viện cũ:

- Nâng cấp lên phiên bản cung cấp module-info.class.
- Tạo module descriptor phù hợp nếu có thể kiểm soát source và dependency.
- Đóng gói lại thành explicit modular JAR và kiểm tra package, service metadata, reflection cùng dependency.
- Thay thư viện bằng implementation hỗ trợ module system.

Không tạo module descriptor giả chỉ để jlink chấp nhận archive. Descriptor cần phản ánh đúng requires, exports, opens, uses và provides. Module resolve thành công nhưng khai báo sai vẫn có thể làm ứng dụng lỗi khi chạy.

jlink cũng không tự tạo installer, shortcut, file association hoặc service registration của hệ điều hành. Nếu cần các chức năng đó, dùng jpackage hoặc công cụ đóng gói nền tảng phù hợp.

## 13. Kết hợp với jpackage

Pipeline phát hành thường có dạng:

~~~text
Source code
    |
    | javac
    v
Compiled named modules
    |
    | jar (nếu cần)
    v
Modular JARs
    |
    | jlink
    v
Custom runtime image
    |
    | jpackage
    v
Application package / installer
~~~

jpackage có thể sử dụng runtime image đã tạo hoặc tạo image phù hợp trong quá trình đóng gói tùy cấu hình. jlink tập trung tạo runtime image; jpackage tập trung tạo gói ứng dụng cho người dùng cuối.

Khi phát hành, tạo gói riêng cho từng nền tảng mục tiêu, kiểm tra yêu cầu giấy phép và kiểm thử installer trên môi trường sạch. Runtime image không tự cập nhật theo JDK mới; khi cần bản vá bảo mật hoặc cập nhật JDK, cần tạo lại và phát hành image mới.

## 14. Lỗi thường gặp

- **Thiếu module trên module path:** jlink không resolve được dependency. Bổ sung đúng modular artifact hoặc JMOD.
- **Đưa automatic module vào link:** chuyển dependency thành explicit module trước khi link.
- **Chọn root module chưa đủ:** module cần thiết nhưng không có quan hệ dependency hoặc service binding có thể không được đưa vào image.
- **Quên uses/provides:** ServiceLoader không tìm được provider như mong đợi.
- **Dùng sai dấu phân cách module path:** Windows dùng dấu chấm phẩy; Linux và macOS thường dùng dấu hai chấm.
- **Tạo launcher sai module/main class:** kiểm tra tên module và fully qualified main class.
- **Giả định mọi tài nguyên đều được link:** file cấu hình, dữ liệu và native library bên ngoài module cần đóng gói riêng.
- **Chỉ test trên máy build:** có thể vô tình dùng JDK hoặc thư viện đã cài sẵn. Kiểm thử bằng image trên môi trường sạch.
- **Dùng một image cho mọi hệ điều hành:** tạo image theo nền tảng và kiến trúc mục tiêu.
- **Không rebuild khi cập nhật JDK:** runtime image là snapshot của runtime được link; cần tạo lại image khi cập nhật JDK.

## 15. Quy trình thực hành

1. Xác nhận module ứng dụng có module-info.class và dependency được khai báo đúng.
2. Biên dịch module bằng javac.
3. Đóng gói modular JAR nếu pipeline yêu cầu.
4. Chạy jar --describe-module để kiểm tra descriptor.
5. Dùng jdeps rà soát dependency bytecode và đối chiếu module descriptor.
6. Chạy jlink với module path gồm JDK jmods và module ứng dụng.
7. Chọn root module bằng --add-modules; thêm --bind-services khi cần service binding.
8. Tạo launcher bằng --launcher nếu muốn entry point riêng.
9. Áp dụng tối ưu kích thước sau khi có baseline.
10. Kiểm tra image bằng java --list-modules, --describe-module và --version.
11. Chạy ứng dụng bằng launcher trong image.
12. Kiểm thử trên môi trường sạch và từng nền tảng phát hành.
13. Dùng jpackage nếu cần installer hoặc gói phân phối tích hợp hệ điều hành.

## 16. Ghi nhớ

jlink tạo runtime image tùy chỉnh từ các module có thể resolve. Chỉ định module path, chọn root module, để linker resolve dependency và ghi image ra thư mục output. Có thể dùng --bind-services cho service provider, --launcher để tạo lối khởi chạy riêng và các tùy chọn strip/compress để giảm kích thước.

JAR modular là đầu vào phân phối module; runtime image là môi trường chạy đã link. Image cần được kiểm tra bằng chính Java launcher của nó và kiểm thử trên nền tảng mục tiêu. Với ứng dụng dành cho người dùng cuối, jpackage có thể đóng gói runtime image thành installer. Hãy rebuild image khi cập nhật JDK để nhận bản vá và thay đổi runtime mới.

## Tài liệu tham khảo

- Oracle JDK — The jlink Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html
- Oracle JDK — The jar Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html
- Oracle JDK — The jdeps Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html
- Oracle JDK — The jpackage Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html

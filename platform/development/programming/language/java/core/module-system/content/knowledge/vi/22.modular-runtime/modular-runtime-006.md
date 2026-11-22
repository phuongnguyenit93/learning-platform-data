# java --describe-module

java --describe-module là tùy chọn của Java launcher dùng để hiển thị mô tả của một module rồi kết thúc. Tùy chọn viết tắt là -d. Đây là công cụ tra cứu module trong môi trường Java đang chạy, hữu ích khi kiểm tra tên module, dependency, package được export, service được dùng hoặc provider được khai báo.

Cú pháp cơ bản:

~~~bash
java --describe-module module_name
~~~

Hoặc dạng ngắn:

~~~bash
java -d module_name
~~~

Lệnh không chạy main class của module. Nó yêu cầu launcher tìm module theo cấu hình module path hiện tại, in mô tả module và thoát. Vì vậy, đây là bước kiểm tra nhanh khi một ứng dụng modular không resolve được module như dự kiến.

## 1. Cú pháp và cách hoạt động

Dạng tổng quát:

~~~bash
java [launcher-options] --describe-module module_name
~~~

Tham số module_name là tên module, ví dụ java.base, java.sql hoặc com.example.payment. Đây là tên module được khai báo trong module-info.java, không phải tên package, tên class main hay tên file JAR.

Ví dụ:

~~~bash
java --describe-module java.base
java -d java.sql
~~~

Hai lệnh trên mô tả module hệ thống. Với module ứng dụng nằm trên module path, truyền thêm --module-path:

~~~bash
java --module-path mods --describe-module com.example.payment
~~~

Nếu module nằm trong thư mục plugins:

~~~bash
java --module-path "mods;plugins" --describe-module com.example.payment
~~~

Trên Windows, dấu chấm phẩy phân tách các phần tử module path. Trên Linux và macOS, dùng dấu hai chấm:

~~~bash
java --module-path "mods:plugins" --describe-module com.example.payment
~~~

Tùy chọn -p là dạng viết tắt của --module-path:

~~~bash
java -p mods --describe-module com.example.payment
~~~

Các launcher option phải được đặt trước module_name. Khi đã chỉ định --describe-module, launcher in mô tả và kết thúc thay vì tiếp tục tìm main class để chạy ứng dụng.

## 2. Đọc kết quả mô tả module

Ví dụ, một module ứng dụng có thể được mô tả như sau:

~~~text
com.example.payment
exports com.example.payment.api
requires java.base mandated
requires com.example.customer
uses com.example.payment.spi.PaymentProvider
provides com.example.payment.spi.PaymentProvider
    with com.example.payment.internal.DefaultPaymentProvider
~~~

Ý nghĩa các phần thường gặp:

| Dòng kết quả | Ý nghĩa |
|---|---|
| Tên module ở dòng đầu | Tên module được mô tả; có thể kèm version nếu descriptor cung cấp |
| exports package | Package được module export để module khác truy cập API public |
| exports package to ... | Qualified export: chỉ các module được nêu tên mới được truy cập package |
| opens package | Package được mở cho reflection sâu theo quy tắc module |
| opens package to ... | Qualified open dành cho một nhóm module |
| requires module | Module phụ thuộc vào module khác |
| requires ... transitive | Dependency được truyền tiếp tới module phụ thuộc vào module hiện tại |
| requires ... static | Dependency chỉ bắt buộc tại thời điểm biên dịch |
| uses service | Module khai báo tiêu thụ service |
| provides service with provider | Module khai báo implementation cung cấp cho service |
| mandated | Dependency được yêu cầu ngầm theo quy tắc ngôn ngữ hoặc runtime, thường gặp với java.base |

Kết quả là bản tóm tắt của module descriptor mà runtime nhận diện. Nó giúp kiểm tra module đã được đóng gói với metadata nào, nhưng không chứng minh toàn bộ ứng dụng có thể khởi động thành công. Các vấn đề như thiếu module khác, lỗi khởi tạo provider hoặc lỗi cấu hình runtime vẫn có thể xuất hiện khi chạy ứng dụng.

## 3. Kiểm tra module hệ thống

JDK cung cấp nhiều module hệ thống. Có thể mô tả trực tiếp một module:

~~~bash
java --describe-module java.base
java --describe-module java.logging
java --describe-module java.sql
java --describe-module java.xml
~~~

java.base là module nền tảng và được mọi module phụ thuộc ngầm định. Các module như java.sql hoặc java.xml cung cấp API chuyên biệt.

Nếu chưa biết chính xác tên module nào có thể được runtime quan sát, dùng:

~~~bash
java --list-modules
~~~

Lệnh này liệt kê các module quan sát được rồi kết thúc. Sau đó có thể lấy một tên từ danh sách và đưa vào --describe-module.

Để lọc danh sách trên shell:

~~~bash
java --list-modules | grep java.sql
~~~

Trên PowerShell:

~~~powershell
java --list-modules | Select-String java.sql
~~~

Nếu lệnh trả về module name kèm version, có thể dùng tên module trước ký tự @ cho tùy chọn --describe-module.

## 4. Mô tả module ứng dụng trên module path

Giả sử dự án đã đóng gói module com.example.payment thành:

~~~text
build/
|-- mods/
    |-- com.example.payment.jar
    |-- com.example.customer.jar
~~~

Kiểm tra module:

~~~bash
java --module-path build/mods \
     --describe-module com.example.payment
~~~

Launcher tìm module theo tên module trong các vị trí được chỉ định. Nó không yêu cầu tên file JAR phải giống tên module. Một JAR tên payment-library.jar vẫn có thể chứa module tên com.example.payment.

Nếu kết quả báo không tìm thấy module, kiểm tra lần lượt:

1. Đã truyền đúng thư mục chứa modular JAR hoặc exploded module chưa?
2. File JAR có module-info.class hợp lệ hoặc Automatic-Module-Name phù hợp không?
3. Tên module truyền vào có khớp tên trong descriptor không?
4. Có module cùng tên bị trùng trên module path hoặc upgrade module path không?
5. Đang chạy đúng JDK và đúng cấu hình module path dự kiến không?

Có thể dùng --list-modules cùng module path để xem các module mà launcher nhận diện:

~~~bash
java --module-path build/mods --list-modules
~~~

Sau đó mô tả module cần kiểm tra:

~~~bash
java --module-path build/mods \
     --describe-module com.example.payment
~~~

## 5. Kết hợp với upgrade module path

--upgrade-module-path chỉ định nơi tìm các bản thay thế cho module có thể nâng cấp trong runtime image. Nếu ứng dụng đang thay thế một module hệ thống được phép nâng cấp, cần tính đến đường dẫn này khi kiểm tra.

Ví dụ:

~~~bash
java --upgrade-module-path upgrades \
     --module-path mods \
     --describe-module java.xml
~~~

Module được tìm thấy qua upgrade module path có thể thay thế module tương ứng trong runtime image theo quy tắc của module system. Nếu kết quả mô tả khác với mong đợi, hãy kiểm tra cả upgrade module path lẫn module path.

Không nên thêm upgrade module path chỉ để sửa lỗi module not found. Trước tiên xác định module thuộc loại module ứng dụng hay module hệ thống có thể nâng cấp.

## 6. Phân biệt java --describe-module và jar --describe-module

Hai lệnh có tên gần giống nhau nhưng phục vụ hai điểm kiểm tra khác nhau.

| Lệnh | Đầu vào | Mục đích |
|---|---|---|
| java --describe-module module_name | Tên module và cấu hình module path của launcher | Mô tả module mà runtime có thể tìm thấy trong cấu hình hiện tại |
| jar --describe-module --file library.jar | File JAR cụ thể | Mô tả module descriptor hoặc automatic module name của archive |

Ví dụ kiểm tra trực tiếp một JAR:

~~~bash
jar --describe-module --file build/mods/payment-library.jar
~~~

Ví dụ kiểm tra cùng module thông qua module path:

~~~bash
java --module-path build/mods \
     --describe-module com.example.payment
~~~

Dùng jar khi câu hỏi là: “Archive này chứa module descriptor hoặc automatic module name nào?”. Dùng java khi câu hỏi là: “Với module path và JDK hiện tại, launcher nhận diện module này ra sao?”.

Nếu JAR là modular JAR, jar --describe-module có thể in descriptor lấy từ archive. Nếu JAR không có module-info.class nhưng có Automatic-Module-Name, công cụ có thể hiển thị tên automatic module. Nếu không có tên khai báo, tên automatic module có thể được suy ra từ tên file theo quy tắc đặt tên.

## 7. Phân biệt với các tùy chọn launcher liên quan

| Tùy chọn | Công dụng |
|---|---|
| --describe-module hoặc -d | In descriptor của một module rồi thoát |
| --list-modules | Liệt kê module quan sát được rồi thoát |
| --module-path hoặc -p | Chỉ định nơi tìm module ứng dụng |
| --upgrade-module-path | Chỉ định module thay thế module hệ thống có thể nâng cấp |
| --add-modules | Thêm root module vào tập module được resolve |
| --show-module-resolution | Hiển thị thông tin về module được resolve khi khởi chạy |
| --validate-modules | Kiểm tra xung đột và lỗi module trên các đường dẫn module |

Ví dụ, để quan sát quá trình resolve khi chạy ứng dụng:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Để kiểm tra module path có xung đột hay lỗi cấu hình:

~~~bash
java --module-path mods --validate-modules
~~~

Hai lệnh này trả lời câu hỏi khác với --describe-module. Một lệnh mô tả descriptor của một module; các lệnh còn lại cung cấp thông tin về resolution hoặc xác thực module graph.

## 8. Ví dụ quy trình chẩn đoán

Giả sử ứng dụng báo không truy cập được package com.example.payment.api. Có thể kiểm tra theo quy trình sau.

**Bước 1: Xác định module có được tìm thấy không.**

~~~bash
java --module-path mods --list-modules
~~~

Nếu module không xuất hiện, kiểm tra vị trí JAR, cấu trúc archive và module path.

**Bước 2: Mô tả module.**

~~~bash
java --module-path mods --describe-module com.example.payment
~~~

Tìm dòng exports com.example.payment.api. Nếu package không được export, module khác không thể truy cập API public của package đó theo quy tắc truy cập thông thường.

**Bước 3: Kiểm tra qualified export.**

Nếu kết quả là:

~~~text
exports com.example.payment.api to com.example.app
~~~

Chỉ module com.example.app được nhận quyền truy cập package qua qualified export. Một module khác dù đọc được module com.example.payment vẫn không được truy cập package này.

**Bước 4: Kiểm tra dependency.**

Tìm dòng requires để biết module có khai báo dependency tới module cần thiết hay không. Phân biệt requires, requires transitive và requires static vì chúng có tác động khác nhau tới resolution và readability.

**Bước 5: Kiểm tra cấu hình tổng thể.**

Nếu descriptor đúng nhưng ứng dụng vẫn không chạy, dùng --validate-modules và --show-module-resolution khi khởi chạy để tìm xung đột, module thiếu hoặc module graph khác dự kiến.

## 9. Các giới hạn và lỗi thường gặp

- **Dùng tên JAR thay cho tên module:** tham số của --describe-module là module name, không phải đường dẫn file JAR.
- **Quên module path:** module ứng dụng không nằm trong runtime image phải được cung cấp qua --module-path hoặc một cơ chế tìm module tương ứng.
- **Nhầm package với module:** một module có thể export nhiều package; truyền tên package sẽ không mô tả module.
- **Nhầm java với jar:** java mô tả module theo cấu hình launcher; jar kiểm tra archive cụ thể.
- **Kỳ vọng lệnh khởi chạy ứng dụng:** --describe-module in descriptor và kết thúc, không gọi main method.
- **Cho rằng exports và opens giống nhau:** exports cấp quyền truy cập API theo module; opens cho phép deep reflection theo quy tắc của module system.
- **Cho rằng descriptor đúng đồng nghĩa ứng dụng chạy được:** lệnh không kiểm tra toàn bộ logic khởi tạo và hành vi runtime của ứng dụng.
- **Bỏ qua module path thay thế:** upgrade module path có thể ảnh hưởng module mà runtime sử dụng.

## 10. Ghi nhớ

java --describe-module module_name là cách nhanh để xem module descriptor mà Java launcher tìm thấy trong cấu hình hiện tại. Dùng --module-path khi mô tả module ứng dụng, --list-modules để tìm tên module, và --validate-modules hoặc --show-module-resolution khi cần chẩn đoán module graph.

Khi kiểm tra một archive độc lập, dùng jar --describe-module --file. Khi kiểm tra ứng dụng thực tế, dùng java --describe-module cùng module path mà ứng dụng sẽ sử dụng. Kết hợp hai góc nhìn này giúp phân biệt lỗi đóng gói JAR với lỗi tìm module trong cấu hình runtime.

## Tài liệu tham khảo

- Oracle Java Launcher — The java Command: https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- Oracle JDK 24 — The jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html

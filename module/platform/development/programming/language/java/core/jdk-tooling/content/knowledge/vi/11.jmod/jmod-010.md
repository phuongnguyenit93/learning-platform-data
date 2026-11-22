# Khi nào nên dùng JMOD trong Java

JMOD là định dạng archive của JDK dành cho module ở giai đoạn phát triển và liên kết runtime. Điểm quan trọng khi quyết định dùng JMOD là mục tiêu đóng gói: JMOD phù hợp khi cần cung cấp đầu vào cho `jlink` hoặc cần đóng gói thêm thành phần như native library, lệnh, cấu hình, header và legal notice. Với ứng dụng Java thông thường chỉ gồm class và resource, modular JAR thường phù hợp hơn để chạy và phân phối.

Bài này giải thích những tình huống nên dùng JMOD, những tình huống không cần dùng, cách tạo một JMOD cho module Java 17+, cách đưa JMOD vào `jlink` và cách chọn định dạng phù hợp cho từng bước phát hành.

## 1. JMOD giải quyết nhu cầu nào?

Một JAR thường chứa class file, resource và metadata như manifest hoặc module descriptor. Nó là định dạng phổ biến để chạy ứng dụng classpath hoặc named module.

JMOD mở rộng cách đóng gói module. Ngoài class và resource, JMOD có thể chứa các nhóm nội dung bổ sung:

| Nhóm | Nội dung có thể đóng gói | Khi có ích |
|---|---|---|
| `classes` | Class file và resource của module | Mọi module cần liên kết |
| `bin` | Lệnh hoặc executable đi kèm module | Module cung cấp công cụ thực thi |
| `conf` | Tệp cấu hình | Runtime cần cấu hình được phân phối cùng module |
| `include` | Header phục vụ tích hợp native | Module có API native hoặc tích hợp C/C++ |
| `legal` | Giấy phép và thông tin bản quyền | Phân phối thành phần có nghĩa vụ pháp lý |
| `lib` | Native library và thư viện hỗ trợ | Module phụ thuộc mã native |
| `man` | Trang hướng dẫn lệnh | Phân phối tài liệu cho lệnh đi kèm |

Không phải JMOD nào cũng có tất cả các nhóm này. Một JMOD chỉ chứa Java classes có thể chỉ có thư mục `classes`; các nhóm khác xuất hiện khi quy trình đóng gói cung cấp chúng.

JMOD hữu ích khi cần đưa các thành phần module vào quy trình tạo runtime image bằng `jlink`. Nó cho phép toolchain xử lý nội dung module ở giai đoạn liên kết, kể cả các thành phần không chỉ là class Java.

## 2. Trường hợp nên dùng JMOD

### 2.1. Khi tạo custom runtime bằng jlink

Đây là lý do phổ biến nhất để dùng JMOD trong phát triển ứng dụng modular. `jlink` nhận các module từ module path và liên kết chúng cùng những dependency cần thiết thành một runtime image.

JMOD là một trong các định dạng đầu vào mà `jlink` có thể sử dụng. Nếu bạn xây dựng module riêng và muốn nó được đưa vào runtime image, có thể đóng gói module thành JMOD rồi cung cấp archive đó cho `jlink`.

Quy trình tổng quát:

1. Viết module và khai báo `module-info.java`.
2. Biên dịch module thành class file.
3. Tạo JMOD từ thư mục class đã biên dịch.
4. Dùng `jlink` với JMOD và các JMOD của JDK.
5. Kiểm thử runtime image tạo ra trên nền tảng đích.

Cách này phù hợp khi muốn phân phối ứng dụng kèm runtime Java tối giản, giảm yêu cầu người dùng phải cài JDK/JRE riêng.

### 2.2. Khi module cần mang theo native library hoặc thành phần ngoài Java

Nếu module có native library, executable, header, cấu hình hoặc legal notice cần được tích hợp vào runtime image, JMOD cung cấp các vùng đóng gói phù hợp.

Ví dụ, một module có thể cần:

- Native library được nạp qua JNI hoặc cơ chế native access phù hợp.
- Executable hỗ trợ module.
- Tệp cấu hình phải có trong runtime image.
- Header dùng khi build hoặc tích hợp native.
- Legal notice cần phân phối cùng module.

Các thành phần native gắn với hệ điều hành và kiến trúc CPU. Khi đóng gói nội dung native, cần tạo và kiểm thử artifact cho nền tảng mục tiêu. Không thể lấy một native library dành cho Windows rồi kỳ vọng runtime image trên Linux sử dụng được.

`jmod create` có các tùy chọn như `--libs`, `--cmds`, `--config`, `--header-files`, `--legal-notices` và `--man-pages` để thêm từng nhóm nội dung. Chỉ đưa vào những thành phần mà module thực sự cần.

### 2.3. Khi phát triển module hoặc toolchain cho JDK

JMOD là một phần của hệ sinh thái công cụ JDK. Các module hệ thống trong thư mục `jmods` của JDK được lưu dưới dạng JMOD để các công cụ liên kết có thể sử dụng.

Khi xây dựng module tùy chỉnh cho runtime image, phát triển thành phần nền tảng hoặc làm việc với quy trình tích hợp module ở cấp JDK, JMOD là định dạng phù hợp cho giai đoạn đóng gói và liên kết.

Với dự án ứng dụng thông thường, không cần chuyển mọi module thành JMOD chỉ vì dự án dùng JPMS. Hãy chọn định dạng theo bước tiếp theo của quy trình.

### 2.4. Khi cần đóng gói module cùng metadata phục vụ liên kết

JMOD có thể ghi module version, main class và target platform metadata. Các thông tin này hữu ích trong quy trình build và liên kết runtime.

Ví dụ:

~~~powershell
jmod create --class-path mods/com.example.app --main-class com.example.app.Main --module-version 1.0.0 build/com.example.app.jmod
~~~

Trong lệnh này:

- `--class-path` trỏ tới thư mục chứa class file và resource của module.
- `--main-class` ghi lớp chính của module.
- `--module-version` ghi phiên bản module.
- Đối số cuối cùng là đường dẫn JMOD được tạo.

Metadata này hỗ trợ công cụ và quy trình đóng gói. Nó không biến JMOD thành một tệp có thể chạy trực tiếp bằng `java -jar`.

## 3. Khi nào không cần dùng JMOD?

### 3.1. Khi chỉ cần chạy hoặc phân phối ứng dụng Java

Nếu ứng dụng chỉ gồm class file và resource, modular JAR thường là lựa chọn đơn giản hơn. Java launcher có thể chạy modular JAR trên module path:

~~~powershell
java --module-path app-modules --module com.example.app/com.example.app.Main
~~~

Nếu JAR có main class metadata, có thể bỏ phần `/main-class`:

~~~powershell
java --module-path app-modules --module com.example.app
~~~

Đối với ứng dụng classpath truyền thống, executable JAR có manifest `Main-Class` vẫn là định dạng quen thuộc:

~~~powershell
java -jar app.jar
~~~

JMOD không được thiết kế để thay thế modular JAR trong quy trình chạy ứng dụng thông thường.

### 3.2. Khi không tạo custom runtime

Nếu người dùng đã có Java runtime phù hợp và bạn chỉ cần phân phối một module Java, modular JAR thường đáp ứng đủ. Không cần thêm bước `jmod create` và `jlink` nếu không có yêu cầu đóng gói runtime hoặc thành phần đặc biệt.

### 3.3. Khi muốn chạy JMOD trực tiếp bằng Java launcher

JMOD không phải định dạng runtime archive. Không dùng các lệnh sau như cách chạy ứng dụng:

~~~powershell
java -jar app.jmod
java --module-path build/app.jmod --module com.example.app
~~~

Để chạy named module, dùng modular JAR hoặc module đã bung ra trên module path. Để dùng JMOD, đưa nó vào quy trình liên kết runtime, thường là `jlink`.

### 3.4. Khi jpackage đã nhận được đầu vào phù hợp

`jpackage` có thể đóng gói ứng dụng từ JAR/module và tạo application image hoặc installer. Nếu cần runtime tùy chỉnh, có thể tạo runtime image trước bằng `jlink`, sau đó truyền runtime image cho `jpackage` bằng `--runtime-image`.

JMOD có thể tham gia ở bước `jlink`; `jpackage` nhận runtime image đã tạo, chứ không dùng JMOD như tệp chạy ứng dụng.

## 4. Phân biệt JMOD, modular JAR và runtime image

| Định dạng | Vai trò chính | Dùng trực tiếp với Java launcher? | Dùng với jlink? |
|---|---|---|---|
| JAR thông thường | Đóng gói class/resource cho classpath | Có, nếu cấu hình chạy phù hợp | Không phải lựa chọn chuẩn cho module liên kết tường minh |
| Modular JAR | Phân phối named module cho runtime | Có, trên module path | Có thể dùng làm đầu vào module path khi phù hợp |
| JMOD | Đóng gói module cho giai đoạn phát triển/liên kết, có thể chứa nội dung native và hệ thống | Không | Có |
| Runtime image | Bộ runtime Java đã được liên kết cho ứng dụng hoặc tập module | Có, thông qua bin/java hoặc launcher | Đây là kết quả của jlink, không phải đầu vào JMOD |

Quyết định theo mục tiêu:

- Cần gửi một module cho người dùng chạy trên Java đã cài: chọn modular JAR.
- Cần gửi một ứng dụng classpath đơn giản: chọn executable JAR.
- Cần tạo runtime Java riêng, chọn lọc module: dùng `jlink`; JMOD là một định dạng đầu vào phù hợp.
- Cần đóng gói native library, lệnh, cấu hình hoặc header vào module cho quá trình liên kết: cân nhắc JMOD.
- Cần tạo installer: dùng `jpackage`, có thể đưa runtime image được tạo từ `jlink`.

## 5. Ví dụ thực hành: từ module Java đến JMOD

Ví dụ sau dùng JDK 17 trở lên và tạo một JMOD có thể đưa vào `jlink`.

Cấu trúc dự án:

~~~text
project/
├── src/
│   ├── module-info.java
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
├── mods/
└── build/
~~~

Nội dung `src/module-info.java`:

~~~java
module com.example.app {
    exports com.example.app;
}
~~~

Nội dung `src/com/example/app/Main.java`:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "JMOD" : String.join(" ", args);
        System.out.println("Hello, " + target + "!");
    }
}
~~~

Từ thư mục `project`, tạo thư mục đầu ra và biên dịch module:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.app, build | Out-Null
javac -d mods/com.example.app src/module-info.java src/com/example/app/Main.java
~~~

Trước khi tạo JMOD, có thể chạy module đã biên dịch trực tiếp từ thư mục module:

~~~powershell
java --module-path mods --module com.example.app/com.example.app.Main "modular app"
~~~

Kết quả:

~~~text
Hello, modular app!
~~~

Tạo JMOD:

~~~powershell
jmod create --class-path mods/com.example.app --main-class com.example.app.Main --module-version 1.0.0 build/com.example.app.jmod
~~~

Kiểm tra archive và metadata:

~~~powershell
jmod list build/com.example.app.jmod
jmod describe build/com.example.app.jmod
~~~

Danh sách entry của ví dụ sẽ có các thành phần chính tương tự:

~~~text
classes/module-info.class
classes/com/example/app/Main.class
~~~

Mô tả module có thể cho biết tên module, version, package export, module phụ thuộc và main class. Output chính xác tùy JDK và metadata của module.

## 6. Dùng JMOD để tạo runtime image với jlink

Sau khi tạo `build/com.example.app.jmod`, có thể dùng `jlink` để liên kết module ứng dụng cùng module nền tảng cần thiết của JDK.

Trên Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;build" --add-modules com.example.app --output runtime
~~~

Trên Linux/macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:build" --add-modules com.example.app --output runtime
~~~

Giải thích:

- `--module-path` chỉ định thư mục JMOD hệ thống của JDK và thư mục chứa JMOD ứng dụng.
- `--add-modules` chọn module gốc cần liên kết.
- `jlink` tự phân giải các module phụ thuộc cần thiết.
- `--output` chỉ định thư mục runtime image sẽ được tạo.

Chạy ứng dụng bằng runtime vừa tạo.

PowerShell trên Windows:

~~~powershell
.\runtime\bin\java.exe -m com.example.app/com.example.app.Main "custom runtime"
~~~

Linux/macOS:

~~~bash
./runtime/bin/java -m com.example.app/com.example.app.Main "custom runtime"
~~~

Kết quả:

~~~text
Hello, custom runtime!
~~~

Runtime image chứa Java launcher và các module đã liên kết. Người dùng có thể chạy ứng dụng bằng runtime này mà không cần cài một JDK đầy đủ riêng, miễn là runtime image được tạo cho nền tảng tương ứng và có đủ module, resource, native component cần thiết.

## 7. Đóng gói thêm thành phần ngoài class bằng JMOD

Khi module cần nhiều hơn class và resource, `jmod create` cho phép thêm các thư mục tương ứng.

Ví dụ khái quát:

~~~powershell
jmod create --class-path mods/com.example.app --libs native-libs --config config --legal-notices legal --main-class com.example.app.Main --module-version 1.0.0 build/com.example.app.jmod
~~~

Các tùy chọn bổ sung:

- `--libs`: thêm thư viện native vào nhóm `lib`.
- `--cmds`: thêm executable hoặc command vào nhóm `bin`.
- `--config`: thêm tệp cấu hình vào nhóm `conf`.
- `--header-files`: thêm header vào nhóm `include`.
- `--legal-notices`: thêm legal notice vào nhóm `legal`.
- `--man-pages`: thêm trang hướng dẫn vào nhóm `man`.
- `--target-platform`: ghi nền tảng mục tiêu cho JMOD khi nội dung phụ thuộc nền tảng.

Các đường dẫn đầu vào phải tồn tại và chứa đúng nội dung dự kiến. Không thêm thư mục rỗng hoặc tệp không liên quan chỉ để lấp đầy archive.

Nếu module chứa native library, phải bảo đảm binary tương ứng với nền tảng và kiến trúc mà runtime image sẽ chạy. `--target-platform` giúp ghi metadata nền tảng, nhưng không chuyển đổi một native binary từ nền tảng này sang nền tảng khác.

## 8. JMOD trong quy trình jpackage

Khi mục tiêu cuối cùng là tạo installer, quy trình có thể gồm các bước:

1. Tạo JMOD từ module ứng dụng.
2. Dùng `jlink` để tạo runtime image có module ứng dụng và dependency.
3. Dùng `jpackage` để đóng gói ứng dụng cùng runtime image thành application image hoặc installer phù hợp hệ điều hành.

Ví dụ lệnh `jpackage` khi đã có runtime image và ứng dụng được chuẩn bị theo cách phù hợp:

~~~powershell
jpackage --type app-image --name ExampleApp --module-path app-modules --module com.example.app/com.example.app.Main --runtime-image runtime --dest packages
~~~

Ở ví dụ này, `--runtime-image` nhận runtime image đã tạo. JMOD đã được dùng ở bước `jlink`; không truyền JMOD vào `jpackage` như thể đó là JAR chính.

Với ứng dụng classpath hoặc modular JAR đơn giản, có thể để `jpackage` tạo runtime nếu phù hợp với cấu hình đầu vào. Chỉ cần thêm bước JMOD/`jlink` khi có lý do rõ ràng như runtime tùy chỉnh hoặc thành phần module đặc biệt.

## 9. Những giới hạn cần cân nhắc

### 9.1. JMOD không phải định dạng chạy trực tiếp

JMOD phục vụ giai đoạn phát triển và liên kết. Java launcher chạy class, JAR hoặc module trên module path; nó không dùng JMOD như một modular JAR thông thường.

### 9.2. JMOD có thể gắn với nền tảng

Nếu archive chứa native library, executable hoặc thành phần phụ thuộc hệ điều hành, artifact cần được xây dựng và kiểm thử cho nền tảng tương ứng. Đừng chia sẻ một JMOD có native content như một artifact độc lập nền tảng nếu thành phần bên trong không thực sự portable.

### 9.3. Cần JDK phù hợp

Các công cụ `jmod` và `jlink` đi kèm JDK. Một runtime image rút gọn được phân phối cho người dùng có thể không chứa các công cụ này. Hãy dùng JDK build phù hợp để tạo JMOD và liên kết runtime.

### 9.4. Dependency phải được khai báo và có sẵn

JMOD không tự giải quyết dependency thiếu. Module descriptor cần khai báo các module mà ứng dụng yêu cầu; các module đó phải có mặt trên module path khi `jlink` thực hiện liên kết.

### 9.5. Kiểm thử runtime image sau khi liên kết

Việc `jlink` tạo thành công không chứng minh mọi tính năng ứng dụng sẽ chạy đúng. Cần kiểm tra resource, service provider, reflection, native library, cấu hình và các module được nạp động. Các dependency không được thể hiện đầy đủ trong module graph có thể cần được bổ sung tường minh.

## 10. Lỗi thường gặp khi chọn hoặc dùng JMOD

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Muốn chạy JMOD bằng `java -jar` | Nhầm JMOD với executable JAR | Dùng modular JAR hoặc chạy runtime image được tạo từ JMOD |
| `jlink` không tìm thấy module | Module path không chứa JMOD hoặc tên module sai | Kiểm tra `--module-path`, `jmod describe` và tên trong module descriptor |
| `jlink` báo thiếu dependency | Module được yêu cầu chưa có trong module path | Thêm JMOD/JAR phụ thuộc và kiểm tra `requires` |
| JMOD không có class mong đợi | `--class-path` trỏ sai thư mục hoặc module chưa biên dịch đầy đủ | Kiểm tra output của `javac` và dùng `jmod list` |
| Runtime image thiếu native library | Chưa đưa native library vào JMOD hoặc sai nhóm đóng gói | Kiểm tra `--libs`, entry `lib/` và nền tảng native |
| Runtime image tạo được nhưng ứng dụng lỗi lúc chạy | Thiếu module nạp động, resource hoặc service provider | Kiểm thử tính năng thực tế; xem lại module graph và cấu hình `jlink` |
| `jmod` không được nhận diện | Đang dùng runtime thay vì JDK hoặc PATH sai | Dùng `jmod` trong thư mục `bin` của JDK |
| JMOD native không chạy trên máy khác | Binary được build cho OS/CPU khác | Build và kiểm thử native component theo nền tảng đích |

## 11. Quy trình quyết định nhanh

Hãy trả lời các câu hỏi theo thứ tự:

1. Ứng dụng chỉ cần chạy trên Java đã cài sẵn và chỉ có class/resource? Dùng JAR, thường là modular JAR nếu ứng dụng dùng JPMS.
2. Cần cung cấp runtime Java riêng, chỉ gồm các module cần thiết? Dùng `jlink`; có thể cung cấp module qua JMOD hoặc modular JAR phù hợp.
3. Module cần đóng gói native library, command, config, header hoặc legal notice cho quá trình liên kết? Dùng JMOD.
4. Cần installer hoặc application image cho hệ điều hành? Dùng `jpackage`; truyền runtime image nếu đã tạo custom runtime.
5. Có native content? Kiểm tra target OS/architecture và kiểm thử trên môi trường đích.

Không cần dùng JMOD chỉ vì dự án có `module-info.java`. Modular JAR đã hỗ trợ chạy named module. JMOD trở nên có giá trị khi quy trình cần archive dành cho liên kết runtime hoặc cần đóng gói các thành phần module ngoài class/resource.

## 12. Checklist trước khi quyết định dùng JMOD

- [ ] Đã xác định mục tiêu là chạy JAR, tạo runtime image hay tạo installer.
- [ ] Đã xác định có cần `jlink` để tạo runtime tùy chỉnh hay không.
- [ ] Đã xác định module có cần native library, command, config, header hoặc legal notice không.
- [ ] Nếu chỉ phân phối module Java cho runtime đã cài, đã cân nhắc modular JAR.
- [ ] Nếu dùng JMOD, module descriptor và dependency đã được chuẩn bị.
- [ ] Đã tạo và kiểm tra JMOD bằng `jmod list`/`jmod describe`.
- [ ] Nếu dùng `jlink`, module path chứa JMOD ứng dụng và các module JDK cần thiết.
- [ ] Nếu có native content, đã kiểm tra OS/architecture mục tiêu.
- [ ] Đã chạy thử runtime image trên môi trường tương ứng.
- [ ] Nếu cần installer, đã chọn đúng loại gói qua `jpackage`.

JMOD nên được chọn khi cần đóng gói module cho bước liên kết runtime, đặc biệt với `jlink`, hoặc khi module cần mang theo native library, lệnh, cấu hình, header và legal notice. Với ứng dụng Java thông thường, modular JAR vẫn là định dạng thuận tiện để chạy và phân phối. Hãy bắt đầu từ cách ứng dụng sẽ được chạy và những thành phần cần đi cùng nó, rồi chọn JAR, JMOD, runtime image hoặc installer cho đúng giai đoạn.

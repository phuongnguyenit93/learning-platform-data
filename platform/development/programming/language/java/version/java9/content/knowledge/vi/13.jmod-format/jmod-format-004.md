# JMOD làm đầu vào cho công cụ jlink

JMOD là định dạng đóng gói module của nền tảng Java, được đưa vào từ Java 9 cùng với hệ thống module. Công cụ **jlink** có thể đọc các tệp JMOD trên module path, phân giải quan hệ phụ thuộc giữa các module rồi tạo một runtime image gọn cho ứng dụng. Cách làm này vẫn được dùng trong các JDK hiện hành: thư mục **jmods** của một JDK chứa các JMOD của những module nền tảng.

Bài này tập trung vào cách kiểm tra JMOD, đưa JMOD vào module path của jlink và tự đóng gói một module thành JMOD để liên kết.

## 1. JMOD giữ những gì?

Một JMOD đóng gói nội dung của một module. Ngoài bytecode Java, định dạng này có thể chứa các thành phần bổ sung mà một modular JAR thông thường không có cấu trúc riêng để lưu trữ, chẳng hạn thư viện native, lệnh native, tệp cấu hình, header và tài liệu pháp lý.

Các JMOD của JDK thường nằm tại **JAVA_HOME/jmods**. Ví dụ:

- **java.base.jmod** chứa module nền tảng bắt buộc của Java.
- **java.logging.jmod** chứa API logging.
- Các module khác của JDK cũng được đóng gói tương tự trong thư mục này.

Một JMOD có thể chứa các vùng dữ liệu sau. Không phải tệp nào cũng có đủ tất cả các vùng.

| Vùng | Nội dung |
|---|---|
| **classes** | module-info.class, các lớp Java và tài nguyên của module |
| **bin** | Lệnh hoặc chương trình native đi kèm module |
| **lib** | Thư viện native |
| **conf** | Tệp cấu hình |
| **include** | Header dùng khi tích hợp native |
| **legal** | Thông tin giấy phép và thông báo pháp lý |
| **man** | Trang hướng dẫn lệnh |

Có thể dùng **jmod list** để xem các mục được đóng gói và **jmod describe** để xem thông tin module như tên, phiên bản, requires, exports, provides, main class hoặc target platform.

## 2. JMOD tham gia vào quá trình jlink như thế nào?

Quy trình liên kết runtime image diễn ra theo các bước:

1. **jlink** tìm module trong các thư mục được khai báo bằng **--module-path**.
2. **--add-modules** chỉ định các module gốc mà ứng dụng cần.
3. jlink đọc module descriptor, lần theo các quan hệ **requires** và bổ sung những module phụ thuộc cần thiết.
4. Nếu cần đưa cả các module cung cấp implementation cho service vào image, có thể dùng **--bind-services**.
5. jlink tạo thư mục runtime image chứa các module đã liên kết cùng những thành phần runtime cần thiết.

JMOD là đầu vào ở thời điểm liên kết. Ứng dụng chạy bằng runtime image đã tạo; lệnh **java** không nạp trực tiếp tệp JMOD như một module trên runtime module path.

Module path của jlink có thể chứa thư mục JMOD, modular JAR hoặc module đã được bung thành thư mục. Module được liên kết phải là module tường minh có descriptor; automatic module không phải đầu vào phù hợp cho jlink.

## 3. Phân biệt JMOD, modular JAR và runtime image

| Thành phần | Vai trò |
|---|---|
| Modular JAR | Đóng gói module Java theo định dạng JAR; có thể dùng trên runtime module path và làm đầu vào cho jlink |
| JMOD | Đóng gói module cùng các vùng dữ liệu bổ sung như native library, cấu hình và header; dùng ở thời điểm liên kết |
| jlink | Đọc các module trên module path, giải quyết phụ thuộc và tạo runtime image |
| Runtime image | Môi trường chạy đã chứa các module được chọn; có thể chạy bằng executable java nằm trong image |

Nếu module chỉ gồm lớp Java và tài nguyên thông thường, modular JAR thường đã đáp ứng được nhu cầu. JMOD hữu ích khi cần đóng gói thêm thành phần native hoặc các vùng dữ liệu phục vụ quá trình tạo runtime image.

## 4. Kiểm tra JMOD có sẵn trong JDK

Trước tiên, xác nhận **JAVA_HOME** trỏ đến một JDK có thư mục **jmods**. Công cụ **jmod** và **jlink** nên được gọi từ cùng JDK để tránh trộn lẫn bộ công cụ và module đầu vào.

PowerShell trên Windows:

~~~powershell
$env:JAVA_HOME
Get-ChildItem "$env:JAVA_HOME\jmods\*.jmod" | Select-Object -First 5 -ExpandProperty Name

jmod describe "$env:JAVA_HOME\jmods\java.logging.jmod"
jmod list "$env:JAVA_HOME\jmods\java.logging.jmod" | Select-Object -First 10
~~~

Bash trên Linux hoặc macOS:

~~~bash
printf '%s\n' "$JAVA_HOME"
ls "$JAVA_HOME/jmods" | head -n 5

jmod describe "$JAVA_HOME/jmods/java.logging.jmod"
jmod list "$JAVA_HOME/jmods/java.logging.jmod" | head -n 10
~~~

**jmod describe** giúp xác nhận tên module và các quan hệ module. **jmod list** cho biết những tệp thực tế nằm trong archive. Nếu cần kiểm tra nội dung sau khi bung, có thể dùng **jmod extract --dir <thư-mục-đích> <tệp-jmod>**.

## 5. Dùng JMOD của JDK làm đầu vào cho jlink

Ví dụ sau tạo một runtime image chỉ chứa **java.base** và **java.logging**. Thư mục đầu ra cần chưa tồn tại hoặc đang rỗng.

PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.base,java.logging --output .\runtime-logging

.\runtime-logging\bin\java.exe --list-modules
~~~

Bash:

~~~bash
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging --output ./runtime-logging

./runtime-logging/bin/java --list-modules
~~~

Danh sách module trong runtime image sẽ có dạng sau; phần phiên bản phụ thuộc JDK đang dùng:

~~~text
java.base@<jdk-version>
java.logging@<jdk-version>
~~~

jlink tự bổ sung các module phụ thuộc cần thiết. Vì vậy, không cần liệt kê thủ công toàn bộ module mà một module gốc yêu cầu. Khi ứng dụng dùng ServiceLoader và cần các provider được tìm thấy trên module path, hãy cân nhắc thêm **--bind-services** để jlink đưa các provider cùng phụ thuộc của chúng vào image.

Lưu ý về đường dẫn:

- **--module-path** trỏ đến thư mục chứa các module, ví dụ thư mục **jmods**; không trỏ đến một tệp JMOD đơn lẻ.
- Khi ghép nhiều thư mục trên Windows, dùng dấu chấm phẩy (**;**). Trên Linux và macOS, dùng dấu hai chấm (**:**).
- Runtime image được tạo cho nền tảng của bộ JDK và các module đầu vào tương ứng. Không dùng JMOD chứa native binary của một hệ điều hành hoặc kiến trúc khác để tạo image cho nền tảng hiện tại.

## 6. Tạo JMOD từ module của ứng dụng

Có thể đóng gói module do ứng dụng tự xây dựng bằng **jmod create**. Thư mục lớp đầu vào phải chứa **module-info.class** cùng các lớp đã biên dịch.

Ví dụ cấu trúc mã nguồn:

~~~text
src/
  module-info.java
  com/
    example/
      greetings/
        Main.java
~~~

Tệp **module-info.java**:

~~~java
module com.example.greetings {
    exports com.example.greetings;
}
~~~

Tệp **Main.java**:

~~~java
package com.example.greetings;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a linked JMOD module");
    }
}
~~~

Các lệnh sau minh họa trên PowerShell, chạy từ thư mục dự án:

~~~powershell
New-Item -ItemType Directory -Force .\build\mods\com.example.greetings, .\build\jmods | Out-Null

javac -d .\build\mods\com.example.greetings .\src\module-info.java .\src\com\example\greetings\Main.java

jmod create --class-path .\build\mods\com.example.greetings --main-class com.example.greetings.Main --module-version 1.0 .\build\jmods\com.example.greetings.jmod

jmod describe .\build\jmods\com.example.greetings.jmod

jlink --module-path "$env:JAVA_HOME\jmods;.\build\jmods" --add-modules com.example.greetings --output .\runtime-greetings

.\runtime-greetings\bin\java.exe -m com.example.greetings
~~~

Trên Bash, phần lệnh tương ứng:

~~~bash
mkdir -p build/mods/com.example.greetings build/jmods

javac -d build/mods/com.example.greetings src/module-info.java src/com/example/greetings/Main.java

jmod create --class-path build/mods/com.example.greetings --main-class com.example.greetings.Main --module-version 1.0 build/jmods/com.example.greetings.jmod

jmod describe build/jmods/com.example.greetings.jmod

jlink --module-path "$JAVA_HOME/jmods:build/jmods" --add-modules com.example.greetings --output runtime-greetings

./runtime-greetings/bin/java -m com.example.greetings
~~~

Kết quả chạy chương trình:

~~~text
Hello from a linked JMOD module
~~~

Tên module được lấy từ **module-info.java**. Tùy chọn **--module-version** ghi phiên bản module vào JMOD; **--main-class** khai báo lớp khởi chạy để runtime image có thể chạy module bằng **java -m**. Nếu module không phải ứng dụng có điểm vào, có thể bỏ **--main-class**.

## 7. Đóng gói thêm thành phần native và cấu hình

Khi module cần mang theo thành phần ngoài lớp Java, **jmod create** có các tùy chọn tương ứng:

- **--libs**: thư mục thư viện native.
- **--cmds**: thư mục lệnh native.
- **--config**: thư mục cấu hình.
- **--header-files**: thư mục header.
- **--legal-notices**: thư mục thông báo pháp lý.
- **--man-pages**: thư mục trang hướng dẫn.
- **--target-platform**: ghi nhận nền tảng mục tiêu cho JMOD.

Chỉ truyền những tùy chọn có nội dung thực tế. Nếu JMOD chứa thư viện hoặc lệnh native, cần xây dựng chúng cho đúng hệ điều hành và kiến trúc đích. Có thể dùng **jmod describe** để kiểm tra thông tin target platform đã được ghi nhận.

## 8. Lỗi thường gặp khi đưa JMOD vào jlink

| Hiện tượng | Nguyên nhân thường gặp và cách kiểm tra |
|---|---|
| jlink báo không tìm thấy module | Module path chưa trỏ đến thư mục chứa JMOD, tên module trong **--add-modules** sai hoặc module chưa được đóng gói. Dùng **jmod describe** và kiểm tra lại đường dẫn. |
| jlink không liên kết được một automatic module | jlink cần module tường minh có descriptor. Bổ sung module descriptor phù hợp rồi đóng gói lại module. |
| Runtime image không chạy được native library | JMOD hoặc native library được xây dựng cho nền tảng khác. Kiểm tra target platform, hệ điều hành và kiến trúc. |
| Không tạo được image ở thư mục đầu ra | Thư mục **--output** đã chứa dữ liệu. Chọn một đường dẫn mới hoặc một thư mục rỗng. |
| Thiếu implementation của service | Provider không nằm trong tập module được liên kết. Kiểm tra khai báo **uses/provides** và cân nhắc **--bind-services**. |

Khi cần chẩn đoán, nên kiểm tra theo thứ tự: module path, tên module, descriptor, các quan hệ requires, target platform và thư mục output. **jmod list** và **jmod describe** là hai lệnh hữu ích để xác minh đầu vào trước khi chạy lại jlink.

## 9. Nguyên tắc sử dụng

- Dùng **jmod** và **jlink** thuộc cùng một JDK; giữ rõ phiên bản JDK dùng để tạo runtime image.
- Đưa vào module path đúng thư mục chứa JMOD hoặc modular JAR.
- Chỉ khai báo các module gốc ứng dụng cần bằng **--add-modules**; để jlink tự phân giải phụ thuộc.
- Kiểm tra module descriptor và các provider service nếu ứng dụng sử dụng ServiceLoader.
- Giữ native library và JMOD đúng nền tảng đích.
- Dùng **jmod describe/list** để kiểm tra đầu vào và **java --list-modules** để xác minh runtime image sau khi tạo.

Khi nắm được vai trò của JMOD trên module path, có thể dùng các JMOD có sẵn trong JDK hoặc tự đóng gói module ứng dụng rồi đưa vào jlink để tạo runtime image theo đúng tập module cần thiết.
# Liệt kê nội dung JMOD bằng jmod list

JMOD (Java Module) là định dạng archive do JDK cung cấp để đóng gói nội dung module ở giai đoạn phát triển và liên kết runtime. Một tệp JMOD có thể chứa class file, lệnh, thư viện native, cấu hình, header, tài liệu và thông tin pháp lý. Công cụ `jmod list` liệt kê các entry có trong một JMOD, giúp kiểm tra archive đã chứa đúng những thành phần cần thiết hay chưa.

Bài này hướng dẫn sử dụng `jmod list` trong JDK 17 trở lên, cách tìm JMOD của JDK, cách tạo một JMOD minh họa để kiểm tra, cách đọc kết quả và cách phân biệt việc liệt kê với mô tả hoặc giải nén archive.

## 1. JMOD là gì và dùng khi nào?

JMOD là định dạng archive dành cho module trong quy trình phát triển JDK và ứng dụng modular. So với một JAR thông thường, JMOD có thể lưu nhiều loại nội dung hơn, không chỉ class và resource Java.

Một JMOD có thể có các nhóm nội dung như:

| Nhóm nội dung | Vai trò |
|---|---|
| `classes` | Class file và resource của module |
| `bin` | Các lệnh hoặc executable đi kèm module |
| `conf` | Tệp cấu hình |
| `include` | Header phục vụ tích hợp native |
| `legal` | Thông tin bản quyền và giấy phép |
| `lib` | Thư viện native hoặc thư viện hỗ trợ |
| `man` | Trang hướng dẫn lệnh |

Không phải mọi JMOD đều chứa đủ các nhóm trên. Nội dung thực tế phụ thuộc module và cách tạo archive. Các entry thường được hiển thị với tiền tố nhóm, chẳng hạn `classes/module-info.class` hoặc `classes/java/lang/String.class`.

JMOD chủ yếu được dùng làm đầu vào cho `jlink` để tạo runtime image. Nó không phải định dạng phân phối thông thường để chạy trực tiếp bằng `java -jar`, và Java launcher không dùng JMOD như một modular JAR trên module path.

## 2. Công cụ jmod và cú pháp list

`jmod` là công cụ dòng lệnh đi kèm JDK. Cú pháp cơ bản để liệt kê một archive:

~~~text
jmod list <jmod-file>
~~~

Ví dụ:

~~~powershell
jmod list "$env:JAVA_HOME/jmods/java.base.jmod"
~~~

Lệnh đọc JMOD được chỉ định và in ra danh sách entry bên trong. Nó không giải nén hoặc thay đổi archive.

Nếu biến môi trường `JAVA_HOME` chưa được thiết lập, hãy dùng đường dẫn đầy đủ tới thư mục cài JDK, ví dụ:

~~~powershell
jmod list "C:/Program Files/Java/jdk-17/jmods/java.base.jmod"
~~~

Trên Linux hoặc macOS:

~~~bash
jmod list "$JAVA_HOME/jmods/java.base.jmod"
~~~

Đảm bảo `JAVA_HOME` trỏ tới JDK có thư mục `jmods`. Một số bản cài runtime rút gọn không có thư mục này vì chúng không chứa toàn bộ công cụ và module archive của JDK.

## 3. Liệt kê JMOD có sẵn trong JDK

JDK thường lưu các module archive chuẩn trong thư mục `jmods` ngay dưới `JAVA_HOME`.

Trên PowerShell, liệt kê tên các JMOD:

~~~powershell
Get-ChildItem "$env:JAVA_HOME/jmods" -Filter *.jmod |
    Select-Object -ExpandProperty Name
~~~

Sau đó liệt kê nội dung module cụ thể, ví dụ `java.base`:

~~~powershell
jmod list "$env:JAVA_HOME/jmods/java.base.jmod"
~~~

`java.base` là module nền tảng của Java Platform, chứa nhiều lớp cơ bản như `java.lang`, `java.util` và các package nền tảng khác. JMOD này có thể rất lớn, nên kết quả liệt kê có thể gồm hàng nghìn entry.

Để lọc một số entry cần quan sát trên PowerShell:

~~~powershell
jmod list "$env:JAVA_HOME/jmods/java.base.jmod" |
    Select-String "module-info.class|java/lang/String.class"
~~~

Trên Linux/macOS, dùng `grep`:

~~~bash
jmod list "$JAVA_HOME/jmods/java.base.jmod" |
    grep -E 'module-info.class|java/lang/String.class'
~~~

Lọc đầu ra chỉ giúp đọc nhanh một phần danh sách. Nếu cần xác nhận đầy đủ archive, hãy lưu và xem toàn bộ output hoặc kiểm tra trực tiếp các nhóm entry liên quan.

## 4. Tạo một JMOD mẫu để thực hành

Có thể tự tạo một module nhỏ, biên dịch thành class file rồi đóng gói thành JMOD. Ví dụ này sử dụng Java 17 trở lên.

Cấu trúc dự án:

~~~text
project/
├── src/
│   ├── module-info.java
│   └── com/
│       └── example/
│           └── hello/
│               └── Main.java
├── mods/
└── build/
~~~

Nội dung `src/module-info.java`:

~~~java
module com.example.hello {
    exports com.example.hello;
}
~~~

Nội dung `src/com/example/hello/Main.java`:

~~~java
package com.example.hello;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "JMOD" : String.join(" ", args);
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Từ thư mục gốc `project`, tạo thư mục đầu ra và biên dịch module:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.hello, build | Out-Null
javac -d mods/com.example.hello src/module-info.java src/com/example/hello/Main.java
~~~

Tạo JMOD:

~~~powershell
jmod create --class-path mods/com.example.hello --main-class com.example.hello.Main --module-version 1.0.0 build/com.example.hello.jmod
~~~

Trong lệnh trên:

- `create` yêu cầu tạo một JMOD mới.
- `--class-path` chỉ định thư mục chứa class file và resource của module đã biên dịch.
- `--main-class` ghi lớp chính vào metadata module.
- `--module-version` ghi phiên bản module.
- Đối số cuối cùng là đường dẫn JMOD sẽ được tạo.

Liệt kê nội dung JMOD vừa tạo:

~~~powershell
jmod list build/com.example.hello.jmod
~~~

Kết quả rút gọn có dạng:

~~~text
classes/module-info.class
classes/com/example/hello/Main.class
~~~

Các entry cụ thể phụ thuộc nội dung module. Vì ví dụ chỉ có module descriptor và một lớp Java nên danh sách chủ yếu gồm hai class file này.

## 5. Đọc và hiểu kết quả jmod list

Mỗi dòng đầu ra đại diện cho một entry trong JMOD. Đường dẫn thường được phân nhóm theo phần nội dung.

Ví dụ:

~~~text
classes/module-info.class
classes/com/example/hello/Main.class
~~~

Có thể diễn giải:

- `classes/` là nhóm class và resource của module.
- `module-info.class` là module descriptor đã biên dịch.
- `com/example/hello/Main.class` là bytecode của lớp `com.example.hello.Main`.

Nếu JMOD được tạo với native library hoặc tệp cấu hình, danh sách có thể chứa entry thuộc các nhóm tương ứng như `lib/` hoặc `conf/`. Nếu module có command, header hoặc legal notice, các entry đó cũng xuất hiện theo nhóm mà công cụ đóng gói sử dụng.

`jmod list` chỉ liệt kê tên entry và vị trí của chúng trong archive. Nó không hiển thị đầy đủ nội dung file, không giải thích dependency và không xác minh rằng ứng dụng sẽ chạy thành công. Dùng công cụ phù hợp cho các câu hỏi sâu hơn.

## 6. Phân biệt list, describe và extract

Công cụ `jmod` có các subcommand cho những mục đích khác nhau:

| Lệnh | Mục đích | Khi sử dụng |
|---|---|---|
| `jmod list file.jmod` | Liệt kê các entry | Xác nhận file nào có trong archive |
| `jmod describe file.jmod` | Hiển thị mô tả module | Xem tên module, requires, exports, main class và metadata |
| `jmod extract --dir out file.jmod` | Giải nén nội dung | Cần kiểm tra hoặc xử lý file thực tế |
| `jmod create ... file.jmod` | Tạo archive | Đóng gói module từ class và resource |
| `jmod hash ...` | Ghi hash phụ thuộc theo cấu hình | Phục vụ quy trình liên kết module đặc thù |

Ví dụ mô tả module vừa tạo:

~~~powershell
jmod describe build/com.example.hello.jmod
~~~

Ví dụ giải nén vào thư mục riêng:

~~~powershell
jmod extract --dir extracted build/com.example.hello.jmod
~~~

Sau khi extract, có thể xem các tệp trong thư mục `extracted` bằng công cụ hệ điều hành. `extract` làm phát sinh các file trên đĩa; `list` chỉ đọc danh sách entry nên phù hợp hơn khi chỉ cần kiểm tra nhanh.

Không dùng `jar --list` để thay thế cho `jmod list` khi làm việc với JMOD. JAR và JMOD phục vụ các quy trình đóng gói khác nhau; hãy sử dụng công cụ được JDK cung cấp cho đúng định dạng.

## 7. Kiểm tra module descriptor và class file

Một entry quan trọng trong JMOD là `classes/module-info.class`. Nó chứa thông tin module đã được compiler tạo ra từ `module-info.java`.

Có thể xem mô tả module bằng:

~~~powershell
jmod describe build/com.example.hello.jmod
~~~

Có thể dùng `javap` để kiểm tra descriptor đã biên dịch sau khi extract:

~~~powershell
javap -v extracted/classes/module-info.class
~~~

Đầu ra verbose của `javap` có thể cho biết module name, các module được yêu cầu, package được xuất hoặc mở và provider được khai báo.

Đối với module mẫu, có thể chạy chương trình từ thư mục module đã biên dịch bằng:

~~~powershell
java --module-path mods --module com.example.hello/com.example.hello.Main
~~~

Kết quả:

~~~text
Hello, JMOD!
~~~

Lệnh này chạy module từ thư mục exploded module trong `mods`, không chạy trực tiếp JMOD. Nếu cần dùng JMOD để tạo runtime tùy chỉnh, hãy đưa archive vào module path của `jlink` theo quy trình liên kết runtime.

## 8. JMOD và jlink

Một lý do quan trọng để tạo và kiểm tra JMOD là sử dụng nó trong quy trình `jlink`. `jlink` tạo runtime image từ các module đầu vào và những dependency cần thiết.

Ví dụ, nếu JMOD được đặt trong thư mục `build` và JDK có thư mục `jmods`, trên Windows có thể tạo runtime image như sau:

~~~powershell
jlink --module-path "$env:JAVA_HOME/jmods;build" --add-modules com.example.hello --output runtime
~~~

Trên Linux/macOS, dấu phân cách module path là dấu hai chấm:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:build" --add-modules com.example.hello --output runtime
~~~

`jlink` đọc module archive và liên kết các module được chọn thành runtime image. Trước khi chạy, hãy chắc chắn JMOD có module descriptor hợp lệ, tên module đúng và mọi module phụ thuộc đều có mặt.

JMOD có thể chứa native code hoặc dữ liệu gắn với nền tảng. Khi đóng gói module có thành phần native, cần tạo và kiểm thử trên hệ điều hành/kiến trúc đích phù hợp.

## 9. Lọc và lưu danh sách entry

Với JMOD lớn, output có thể dài. Có thể lưu danh sách vào file để xem hoặc so sánh sau này.

PowerShell:

~~~powershell
jmod list "$env:JAVA_HOME/jmods/java.base.jmod" |
    Out-File -Encoding utf8 build/java-base-entries.txt
~~~

Linux/macOS:

~~~bash
jmod list "$JAVA_HOME/jmods/java.base.jmod" > build/java-base-entries.txt
~~~

Có thể lọc entry theo nhóm:

~~~powershell
Select-String "^classes/" build/java-base-entries.txt
Select-String "^lib/" build/java-base-entries.txt
Select-String "^conf/" build/java-base-entries.txt
~~~

Để so sánh nội dung giữa hai phiên bản JMOD, tạo danh sách từ từng archive rồi dùng công cụ diff phù hợp. Lưu ý rằng thay đổi phiên bản JDK có thể làm danh sách class, resource hoặc native library thay đổi đáng kể; so sánh entry không tự giải thích nguyên nhân của thay đổi.

Không chỉnh sửa file JMOD trực tiếp bằng cách thay entry trong archive. Nếu cần thay đổi nội dung, hãy tạo lại JMOD từ các thành phần đầu vào đã cập nhật.

## 10. Lỗi thường gặp khi dùng jmod list

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Error: file not found` | Đường dẫn JMOD sai hoặc JMOD không tồn tại | Kiểm tra `JAVA_HOME`, thư mục `jmods` và tên file |
| `jmod is not recognized` hoặc không tìm thấy lệnh | JDK bin chưa nằm trên PATH | Gọi bằng đường dẫn đầy đủ hoặc cấu hình PATH tới JDK |
| `Error: invalid JMOD file` | File bị hỏng, không đúng định dạng hoặc không phải JMOD hợp lệ | Lấy lại archive từ nguồn tin cậy hoặc tạo lại bằng `jmod create` |
| Danh sách không có class mong đợi | Class chưa được biên dịch hoặc không nằm trong class-path khi tạo JMOD | Kiểm tra output của `javac` và tham số `--class-path` |
| Không thấy module descriptor | Module không được biên dịch như explicit module hoặc JMOD tạo thiếu module-info | Kiểm tra `module-info.java` và `module-info.class` trong thư mục đầu vào |
| Đường dẫn có khoảng trắng làm lệnh lỗi | Đường dẫn chưa được đặt trong dấu ngoặc kép | Đặt toàn bộ đường dẫn trong dấu ngoặc kép |
| Nhầm JMOD với JAR khi chạy ứng dụng | Dùng JMOD ở vị trí của modular JAR | Dùng modular JAR trên Java launcher hoặc dùng JMOD làm đầu vào cho `jlink` |
| Output quá lớn hoặc khó đọc | Đang liệt kê module có nhiều entry | Lọc bằng `Select-String`/`grep` hoặc lưu output ra file |

Khi có lỗi, xác định lỗi xảy ra ở bước nào: tìm JMOD, đọc archive, tạo JMOD, mô tả module, extract hay liên kết runtime. Dùng `jmod list` để kiểm tra entry; dùng `jmod describe` để xem metadata; dùng `jmod extract` chỉ khi cần kiểm tra file thực tế.

## 11. Checklist khi liệt kê JMOD

- [ ] Đang dùng lệnh `jmod` từ đúng JDK.
- [ ] Đường dẫn tới JMOD tồn tại và trỏ đúng archive cần kiểm tra.
- [ ] Dùng đúng cú pháp `jmod list <jmod-file>`.
- [ ] Đã xác nhận entry quan trọng như `classes/module-info.class` và class/resource cần thiết.
- [ ] Đã phân biệt entry list với nội dung module metadata.
- [ ] Dùng `jmod describe` nếu cần xem dependency, exports hoặc main class.
- [ ] Chỉ dùng `jmod extract` khi thực sự cần giải nén file.
- [ ] Không nhầm JMOD với JAR khi chạy bằng Java launcher.
- [ ] Nếu JMOD có native content, đã xét tới hệ điều hành và kiến trúc đích.
- [ ] Nếu dùng cho `jlink`, đã xác nhận module descriptor và dependency cần thiết.

`jmod list` là cách trực tiếp để kiểm tra những entry được đóng gói trong JMOD. Hãy bắt đầu bằng đúng đường dẫn archive, đọc các nhóm entry để xác nhận class và resource, rồi dùng `jmod describe` hoặc `jmod extract` khi cần thêm thông tin. Phân biệt rõ JMOD với modular JAR để chọn đúng công cụ ở bước đóng gói, chạy ứng dụng và tạo runtime image.

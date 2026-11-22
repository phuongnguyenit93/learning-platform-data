# Classpath trong JShell

JShell là môi trường REPL cho phép nhập và chạy từng đoạn mã Java. Khi muốn thử một thư viện hoặc lớp đã được biên dịch ở bên ngoài, JShell cần biết nơi tìm các class file đó. Classpath cung cấp danh sách thư mục và archive mà compiler cùng execution engine của JShell dùng để tìm lớp.

Bạn có thể đặt classpath ngay khi khởi động JShell bằng `--class-path`, hoặc cập nhật môi trường trong phiên bằng lệnh `/env --class-path`. Bài này sử dụng JDK 17 trở lên, hướng dẫn cách dùng classpath với thư mục class, JAR và nhiều dependency, đồng thời phân biệt classpath với module path.

## 1. Classpath có vai trò gì trong JShell?

Classpath là danh sách vị trí chứa các class file mà Java cần tìm khi biên dịch hoặc chạy mã. Mỗi entry thường là:

- Thư mục gốc chứa cây package đã biên dịch.
- Tệp JAR chứa class và resource.
- Tệp ZIP chứa class file.

Ví dụ, nếu có class `com.example.Greeting` nằm trong:

~~~text
project/
├── out/
│   └── com/
│       └── example/
│           └── Greeting.class
└── lib/
    └── greeting.jar
~~~

thì classpath có thể trỏ tới thư mục `out` hoặc archive `lib/greeting.jar`.

Trong JShell, sau khi thiết lập classpath, bạn có thể import package và sử dụng các lớp đã biên dịch:

~~~java
import com.example.Greeting;

System.out.println(new Greeting().message());
~~~

Classpath không tự biên dịch source code của thư viện. Lớp bên ngoài phải được biên dịch thành `.class` và nằm trong một thư mục hoặc archive mà classpath trỏ tới.

## 2. Đặt classpath khi khởi động JShell

Dùng tùy chọn `--class-path`:

~~~powershell
jshell --class-path out
~~~

Nếu lớp nằm trong JAR:

~~~powershell
jshell --class-path lib/greeting.jar
~~~

Bạn cũng có thể truyền nhiều thư mục hoặc JAR trong cùng một classpath.

Trên Windows, các entry được phân tách bằng dấu chấm phẩy:

~~~powershell
jshell --class-path "out;lib/greeting.jar;lib/logging.jar"
~~~

Trên Linux và macOS, dùng dấu hai chấm:

~~~bash
jshell --class-path "out:lib/greeting.jar:lib/logging.jar"
~~~

Đặt toàn bộ giá trị classpath trong dấu ngoặc kép khi có khoảng trắng hoặc nhiều entry. Ví dụ trên Windows:

~~~powershell
jshell --class-path "build/classes;C:\Java Libraries\greeting.jar"
~~~

Ví dụ trên Linux/macOS:

~~~bash
jshell --class-path "build/classes:/opt/java libraries/greeting.jar"
~~~

Nếu không dùng `--class-path` và biến môi trường `CLASSPATH` không được đặt, JShell tìm class trong thư mục hiện tại (`.`). Tùy chọn `--class-path` ghi đè giá trị `CLASSPATH` của môi trường.

## 3. Biên dịch một lớp Java rồi sử dụng trong JShell

Tạo source `src/com/example/Greeting.java`:

~~~java
package com.example;

public class Greeting {
    private final String name;

    public Greeting(String name) {
        this.name = name;
    }

    public String message() {
        return "Hello, " + name + "!";
    }
}
~~~

Từ thư mục gốc dự án, biên dịch lớp vào thư mục `out`:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac -d out src/com/example/Greeting.java
~~~

Sau khi biên dịch, file phải nằm tại:

~~~text
out/com/example/Greeting.class
~~~

Khởi động JShell với thư mục `out`:

~~~powershell
jshell --class-path out
~~~

Nhập các snippet:

~~~java
import com.example.Greeting;
Greeting greeting = new Greeting("JShell");
System.out.println(greeting.message());
~~~

Dòng được in ra:

~~~text
Hello, JShell!
~~~

Ví dụ này cho thấy classpath trỏ tới thư mục gốc của package tree. Không trỏ trực tiếp tới file `Greeting.class`, và không trỏ tới thư mục `com/example`; hãy trỏ tới thư mục cha chứa `com`.

## 4. Đóng gói class thành JAR và thêm vào classpath

Với thư viện được phân phối dưới dạng JAR, quy trình tương tự nhưng classpath trỏ tới archive.

Từ thư mục dự án đã có `out/com/example/Greeting.class`, tạo JAR:

~~~powershell
New-Item -ItemType Directory -Force -Path lib | Out-Null
jar --create --file lib/greeting.jar -C out .
~~~

Kiểm tra nội dung JAR:

~~~powershell
jar --list --file lib/greeting.jar
~~~

Bạn sẽ thấy entry tương tự:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Greeting.class
~~~

Khởi động JShell với JAR:

~~~powershell
jshell --class-path lib/greeting.jar
~~~

Dùng lớp:

~~~java
import com.example.Greeting;
System.out.println(new Greeting("JAR").message());
~~~

Kết quả:

~~~text
Hello, JAR!
~~~

JAR không bắt buộc phải có executable manifest `Main-Class` để dùng làm dependency trong classpath. JShell chỉ cần JAR chứa đúng package và class mà snippet tham chiếu.

## 5. Sử dụng nhiều JAR và dependency bắc cầu

Một thư viện có thể phụ thuộc vào thư viện khác. Khi đó, classpath phải chứa cả thư viện trực tiếp lẫn dependency mà nó cần.

Ví dụ:

~~~text
project/
├── lib/
│   ├── greeting.jar
│   ├── model.jar
│   └── logging.jar
└── out/
~~~

Nếu `greeting.jar` sử dụng lớp trong `model.jar` và `logging.jar`, hãy thêm cả ba vào classpath.

Windows:

~~~powershell
jshell --class-path "lib/greeting.jar;lib/model.jar;lib/logging.jar"
~~~

Linux/macOS:

~~~bash
jshell --class-path "lib/greeting.jar:lib/model.jar:lib/logging.jar"
~~~

Có thể dùng wildcard để đưa các JAR trong một thư mục vào classpath:

~~~powershell
jshell --class-path "lib/*"
~~~

Classpath wildcard như `lib/*` bao gồm các JAR trong thư mục đó. Thứ tự mở rộng các JAR không được bảo đảm. Nếu có nhiều phiên bản cùng chứa một class, kết quả tìm lớp có thể phụ thuộc thứ tự classpath; nên loại bỏ JAR trùng hoặc chỉ định thứ tự tường minh khi cần kết quả ổn định.

Nếu gặp `NoClassDefFoundError` hoặc `ClassNotFoundException`, hãy kiểm tra cả thư viện chính và dependency của nó. Thêm riêng JAR đầu tiên có thể chưa đủ.

## 6. Cập nhật classpath trong một phiên JShell bằng /env

Nếu đã mở JShell mà chưa đặt classpath, dùng lệnh `/env`:

~~~text
jshell> /env --class-path out
|  Setting new options and restoring state.
~~~

Sau đó import lớp:

~~~java
import com.example.Greeting;
System.out.println(new Greeting("updated classpath").message());
~~~

`/env` cập nhật môi trường thực thi và khởi động lại execution state. JShell chạy startup scripts và phát lại lịch sử các snippet hợp lệ theo thứ tự. Vì vậy, các snippet trước đó có thể được đánh giá lại trong môi trường mới.

Điều này hữu ích khi cần bổ sung thư viện sau khi bắt đầu phiên, nhưng có thể ảnh hưởng tới trạng thái đang thử nghiệm. Nếu snippet phụ thuộc vào side effect bên ngoài như ghi file, gọi API hoặc cập nhật database, việc replay cần được cân nhắc. Hãy lưu các đoạn mã quan trọng bằng `/save` trước khi thay đổi môi trường.

Có thể xem các thiết lập môi trường hiện tại bằng:

~~~text
jshell> /env
|     --class-path out
~~~

Để xem cú pháp và các tùy chọn môi trường khác:

~~~text
jshell> /help context
~~~

Khi cập nhật classpath, hãy truyền danh sách đầy đủ các entry cần dùng. Giá trị classpath mới có thể thay thế đường dẫn đã thiết lập trước đó; đừng giả định một đường dẫn mới luôn được nối tự động vào đường dẫn cũ.

## 7. Ví dụ hoàn chỉnh: tạo JAR và mở JShell với classpath

Có thể thực hiện toàn bộ quy trình từ thư mục dự án bằng các lệnh sau.

Tạo cấu trúc:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── Greeting.java
├── out/
└── lib/
~~~

Nội dung `Greeting.java`:

~~~java
package com.example;

public class Greeting {
    public String message(String name) {
        return "Welcome, " + name + "!";
    }
}
~~~

Biên dịch và đóng gói:

~~~powershell
New-Item -ItemType Directory -Force -Path out, lib | Out-Null
javac -d out src/com/example/Greeting.java
jar --create --file lib/greeting.jar -C out .
~~~

Khởi động JShell:

~~~powershell
jshell --class-path lib/greeting.jar
~~~

Nhập:

~~~java
import com.example.Greeting;
Greeting service = new Greeting();
System.out.println(service.message("Java learner"));
~~~

Kết quả:

~~~text
Welcome, Java learner!
~~~

Thoát JShell:

~~~text
jshell> /exit
~~~

Nếu muốn dùng class file trực tiếp thay vì tạo JAR, khởi động bằng `jshell --class-path out`. Cả thư mục class và JAR đều là classpath entry hợp lệ.

## 8. Classpath và module path khác nhau thế nào?

Classpath và module path giải quyết hai cách tìm code khác nhau.

| Đặc điểm | Classpath | Module path |
|---|---|---|
| Đầu vào | Thư mục class, JAR hoặc ZIP | Named module, thường là modular JAR hoặc exploded module |
| Mô hình | Unnamed module | Named modules |
| Khai báo dependency | Thường qua build/classpath | Qua `module-info.java` và `requires` |
| Kiểm soát package | Ít ràng buộc module | Có `exports`, `opens` và readability |
| JShell option | `--class-path` | `--module-path`, `--add-modules` |

Nếu muốn sử dụng một thư viện thông thường trên classpath, dùng:

~~~powershell
jshell --class-path lib/greeting.jar
~~~

Nếu thư viện là named module, dùng module path và yêu cầu module được resolve:

~~~powershell
jshell --module-path mods --add-modules com.example.greeting
~~~

Sau đó import package được module export. Nếu module không export package cần dùng, chỉ thêm module vào `--add-modules` không làm package đó trở nên truy cập được. Hãy kiểm tra module descriptor và quyền export.

Không đặt một modular JAR vào classpath với kỳ vọng JShell sẽ áp dụng đầy đủ quy tắc module của nó. Khi muốn dùng JPMS, hãy dùng module path.

## 9. Những giới hạn quan trọng

### 9.1. Lớp trong unnamed package không truy cập được

JShell không thể truy cập lớp nằm trong default package (unnamed package). Hãy đặt lớp thư viện trong một package có tên, ví dụ `com.example`, biên dịch lớp đó và thêm thư mục/JAR vào classpath.

### 9.2. Source code phải được biên dịch

`--class-path` tìm class file trong thư mục và archive. Nó không tự biên dịch một tệp `.java` tùy ý thành thư viện. Biên dịch bằng `javac` hoặc build tool trước, rồi thêm output vào classpath.

### 9.3. Classpath không thay thế module path

Một named module có thể cần module resolution và package exports. Nếu thư viện được thiết kế như module, hãy cấu hình `--module-path` và `--add-modules` thay vì chỉ thêm JAR vào classpath.

### 9.4. Classpath trùng lặp có thể gây nhầm lẫn

Nếu hai JAR có cùng fully qualified class name, JVM có thể nạp class từ entry được tìm thấy trước theo thứ tự classpath. Điều này dễ gây lỗi `NoSuchMethodError`, `NoSuchFieldError` hoặc hành vi không nhất quán khi các phiên bản API khác nhau.

Dùng một phiên bản thư viện thống nhất và loại bỏ dependency cũ khỏi classpath.

### 9.5. Classpath của JShell không tự cấu hình ứng dụng khác

Classpath được đặt cho tiến trình JShell hiện tại. Nó không tự cập nhật classpath cho IDE, Maven, Gradle hoặc lệnh `java` chạy riêng bên ngoài.

## 10. Lỗi thường gặp khi cấu hình classpath

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `package ... does not exist` | Classpath không chứa thư mục/JAR có package | Kiểm tra đường dẫn và cấu trúc package trong archive |
| `cannot find symbol` | Class chưa biên dịch, import sai hoặc dependency thiếu | Biên dịch lại, import đúng tên và thêm dependency |
| `ClassNotFoundException` | Runtime không tìm thấy class được nạp | Kiểm tra classpath lúc khởi động và class name |
| `NoClassDefFoundError` | Class chính tìm thấy nhưng dependency cần khi chạy bị thiếu hoặc không thể khởi tạo | Bổ sung JAR phụ thuộc và đọc nguyên nhân gốc trong stack trace |
| `NoSuchMethodError` hoặc `NoSuchFieldError` | Nạp nhầm phiên bản thư viện không tương thích | Kiểm tra JAR trùng, thứ tự classpath và API version |
| Đường dẫn có khoảng trắng không hoạt động | Giá trị classpath bị tách thành nhiều đối số | Đặt toàn bộ classpath trong dấu ngoặc kép |
| Windows không tìm thấy JAR thứ hai | Dùng dấu `:` thay vì `;` | Dùng dấu chấm phẩy trên Windows |
| Linux/macOS không tìm thấy JAR thứ hai | Dùng dấu `;` thay vì `:` | Dùng dấu hai chấm trên Linux/macOS |
| `/env` làm snippet chạy lại | `/env` khởi động lại execution state và replay lịch sử hợp lệ | Lưu snippet; cân nhắc side effect trước khi đổi môi trường |
| Không import được lớp default package | JShell không truy cập lớp trong unnamed package | Chuyển lớp vào package có tên rồi biên dịch lại |

## 11. Quy trình chẩn đoán classpath

Khi JShell không tìm thấy một lớp:

1. Xác định fully qualified class name, ví dụ `com.example.Greeting`.
2. Xác nhận class đã được biên dịch thành `Greeting.class`.
3. Kiểm tra đường dẫn tương ứng với package, ví dụ `out/com/example/Greeting.class`.
4. Đảm bảo classpath trỏ tới thư mục gốc `out`, không trỏ vào thư mục package con.
5. Nếu dùng JAR, liệt kê nội dung bằng `jar --list --file`.
6. Kiểm tra mọi dependency mà class đó cần.
7. Xác nhận dấu phân cách classpath đúng hệ điều hành và đường dẫn có khoảng trắng đã được quote.
8. Dùng `/env` để xem cấu hình hiện tại hoặc khởi động lại JShell với classpath đầy đủ.
9. Nếu thư viện là named module, chuyển sang module path và kiểm tra `module-info.java`.

Có thể kiểm tra nội dung JAR bằng:

~~~powershell
jar --list --file lib/greeting.jar
~~~

Và xem classpath đang được JShell sử dụng:

~~~text
jshell> /env
~~~

## 12. Checklist trước khi dùng thư viện ngoài trong JShell

- [ ] Thư viện đã được biên dịch thành class file.
- [ ] Class nằm trong package có tên, không phải unnamed package.
- [ ] Classpath trỏ tới thư mục gốc package tree hoặc đúng JAR.
- [ ] Tất cả dependency cần thiết đều có trong classpath.
- [ ] Nhiều entry dùng đúng dấu phân cách theo hệ điều hành.
- [ ] Đường dẫn có khoảng trắng được đặt trong dấu ngoặc kép.
- [ ] Dùng `--class-path` khi khởi động hoặc `/env --class-path` trong phiên.
- [ ] Đã kiểm tra cấu hình bằng `/env`.
- [ ] Đã lưu snippet quan trọng trước khi dùng `/env`, vì lệnh này replay lịch sử.
- [ ] Nếu thư viện là named module, đã dùng module path thay vì classpath.

Classpath giúp JShell sử dụng các lớp và thư viện Java đã biên dịch ở bên ngoài phiên tương tác. Hãy trỏ tới thư mục gốc chứa package hoặc JAR, đưa đầy đủ dependency vào danh sách và chọn dấu phân cách theo hệ điều hành. Khi cần đổi classpath trong phiên, dùng `/env --class-path` và nhớ rằng JShell sẽ khởi động lại execution state rồi phát lại lịch sử snippet. Nếu thư viện dùng JPMS, cấu hình module path và module resolution thay cho classpath.

## Tài liệu tham khảo

- Oracle, Java Shell User's Guide, JDK 17 — External Code: https://docs.oracle.com/en/java/javase/17/jshell/external-code.html
- Oracle, The jshell Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jshell.html
- Oracle, The java Command, JDK 17 — class path option: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html

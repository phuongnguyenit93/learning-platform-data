# Biên dịch một class Java bằng javac

`javac` là trình biên dịch Java đi kèm JDK. Công cụ nhận mã nguồn .java, kiểm tra cú pháp và kiểu dữ liệu, sau đó tạo bytecode trong các tệp .class để JVM có thể nạp và thực thi.

Khi biên dịch một class, cần xác định tệp nguồn, tên class, package, thư viện phụ thuộc và thư mục nhận kết quả. Với class đơn giản không có package hay thư viện ngoài, chỉ cần chạy `javac HelloOne.java` trong thư mục chứa tệp. Với dự án có package, nên chỉ định thư mục output bằng `-d` để giữ đúng cấu trúc package.

## 1. Từ file .java đến file .class

Quy trình cơ bản:

~~~text
HelloOne.java
     |
     | javac
     v
HelloOne.class
     |
     | java (JVM)
     v
Chương trình chạy
~~~

- **Source file (.java)** chứa khai báo class, interface, enum, record và mã nguồn Java.
- **Compiler (javac)** phân tích cú pháp, kiểm tra kiểu, xử lý annotation processor nếu có và sinh bytecode.
- **Class file (.class)** chứa bytecode cùng metadata cần thiết để JVM liên kết và thực thi class.
- **Java launcher (java)** khởi tạo JVM, tìm class theo classpath/module path rồi gọi phương thức `main` nếu đó là điểm vào của ứng dụng.

Biên dịch một class không tạo ra tệp thực thi native độc lập. Tệp .class cần JVM tương thích để chạy. Nó cũng không tự đóng gói các thư viện phụ thuộc; classpath hoặc module path khi chạy vẫn phải cung cấp các dependency cần thiết.

Một tệp nguồn có thể khai báo nhiều top-level class không phải public. `javac` có thể tạo nhiều tệp .class từ một tệp .java; class lồng nhau cũng có thể tạo class file riêng với tên có ký hiệu $. Vì vậy, một lần biên dịch một source file không nhất thiết chỉ tạo đúng một class file.

## 2. Ví dụ đơn giản: biên dịch một class không có package

Tạo tệp `HelloOne.java` với nội dung:

~~~java
public class HelloOne {
    public static void main(String[] args) {
        System.out.println("Hello from javac!");
    }
}
~~~

Tên tệp phải trùng chính xác với tên của top-level public class: `HelloOne.java`. Java phân biệt chữ hoa và chữ thường trong tên class. Nếu khai báo `public class HelloOne` nhưng lưu thành `helloone.java`, compiler thường báo lỗi tên class công khai phải khớp tên tệp.

Mở terminal tại thư mục chứa source file và kiểm tra compiler:

~~~sh
javac -version
~~~

Biên dịch:

~~~sh
javac HelloOne.java
~~~

Nếu không có lỗi, compiler tạo `HelloOne.class` trong thư mục hiện tại (với ví dụ không khai báo package). Chạy class bằng Java launcher:

~~~sh
java HelloOne
~~~

Kết quả stdout:

~~~text
Hello from javac!
~~~

Khi chạy, ghi tên class `HelloOne`, không ghi phần mở rộng .class. Java launcher cần tên class, không phải đường dẫn tệp class.

## 3. Biên dịch vào thư mục output riêng bằng -d

Trong dự án thực tế, không nên để các tệp .class lẫn với source file. Tùy chọn `-d` chỉ định thư mục đích cho class file:

~~~sh
mkdir out
javac -d out HelloOne.java
java -cp out HelloOne
~~~

Thư mục `out` phải tồn tại trước khi gọi `javac -d out`; compiler không tự tạo thư mục output gốc. Nếu thư mục đã tồn tại, không cần tạo lại.

Trên PowerShell, có thể tạo thư mục nếu chưa có:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out HelloOne.java
java -cp out HelloOne
~~~

`-d out` khiến class file được ghi vào `out`. Khi chạy, `-cp out` thêm thư mục đó vào classpath để Java launcher tìm class. `-d` của compiler và `-cp` của launcher là hai tùy chọn ở hai giai đoạn khác nhau.

Cấu trúc sau khi biên dịch ví dụ không có package:

~~~text
project/
├── HelloOne.java
└── out/
    └── HelloOne.class
~~~

## 4. Biên dịch class có package

Khi source file khai báo package, đường dẫn thư mục nên phản ánh tên package. Ví dụ, tạo `src/com/example/Greeter.java`:

~~~java
package com.example;

public class Greeter {
    public static void main(String[] args) {
        System.out.println("Hello from com.example!");
    }
}
~~~

Phần `package com.example;` đặt class trong package `com.example`. Tên class đầy đủ (fully qualified class name) là `com.example.Greeter`.

Tạo output directory rồi biên dịch từ thư mục gốc dự án:

~~~sh
mkdir -p out
javac -d out src/com/example/Greeter.java
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out src/com/example/Greeter.java
~~~

Sau khi biên dịch, cấu trúc output là:

~~~text
out/
└── com/
    └── example/
        └── Greeter.class
~~~

Chạy bằng tên class đầy đủ và classpath là thư mục gốc của cây package:

~~~sh
java -cp out com.example.Greeter
~~~

Kết quả:

~~~text
Hello from com.example!
~~~

Không đặt classpath là `out/com/example` khi muốn chạy `com.example.Greeter`. Classpath phải trỏ đến thư mục gốc chứa thư mục `com`; JVM tự nối các thành phần package để tìm class file.

## 5. Biên dịch class phụ thuộc class khác

Một class có thể tham chiếu class khác trong cùng dự án hoặc trong thư viện JAR. Compiler phải tìm được các kiểu được tham chiếu để kiểm tra và biên dịch.

Giả sử có hai source file:

~~~text
src/
└── com/example/
    ├── MessageFormatter.java
    └── Main.java
~~~

`MessageFormatter.java`:

~~~java
package com.example;

public class MessageFormatter {
    public String format(String name) {
        return "Welcome, " + name + "!";
    }
}
~~~

`Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        MessageFormatter formatter = new MessageFormatter();
        System.out.println(formatter.format("Java"));
    }
}
~~~

Cách rõ ràng nhất khi biên dịch một nhóm class là liệt kê tất cả source file:

~~~sh
mkdir -p out
javac -d out src/com/example/MessageFormatter.java src/com/example/Main.java
java -cp out com.example.Main
~~~

Kết quả:

~~~text
Welcome, Java!
~~~

Nếu chỉ truyền `Main.java` và compiler cần `MessageFormatter`, `javac` có thể tìm và biên dịch source dependency thông qua source path. Có thể chỉ định rõ source path:

~~~sh
javac -sourcepath src -d out src/com/example/Main.java
~~~

Để lệnh build dễ lặp lại và tránh phụ thuộc vào quy tắc tìm source ngầm định, nên chỉ rõ source path hoặc liệt kê các source file cần biên dịch.

## 6. Thêm thư viện ngoài bằng classpath

Nếu class tham chiếu một thư viện được đóng gói trong JAR, hãy cung cấp JAR đó cho compiler bằng `-cp` (hoặc `-classpath`). Classpath là danh sách thư mục và JAR chứa các class mà compiler cần tìm.

Ví dụ, nếu dependency nằm tại `lib/utility.jar`:

~~~sh
javac -cp lib/utility.jar -d out src/com/example/Main.java
~~~

Khi có nhiều mục classpath, dùng ký tự phân tách theo hệ điều hành:

- Windows: dấu chấm phẩy `;`.
- macOS/Linux: dấu hai chấm `:`.

Ví dụ trên Linux/macOS:

~~~sh
javac -cp "lib/utility.jar:lib/logging.jar" -d out src/com/example/Main.java
~~~

Ví dụ trên Windows:

~~~powershell
javac -cp "lib\utility.jar;lib\logging.jar" -d out src\com\example\Main.java
~~~

Classpath cần thiết ở cả hai giai đoạn nếu ứng dụng dùng thư viện đó: lúc biên dịch để compiler tìm kiểu, và lúc chạy để JVM tìm class được tham chiếu. Ví dụ chạy trên Linux/macOS:

~~~sh
java -cp "out:lib/utility.jar:lib/logging.jar" com.example.Main
~~~

Trên Windows, dùng dấu chấm phẩy trong classpath:

~~~powershell
java -cp "out;lib\utility.jar;lib\logging.jar" com.example.Main
~~~

Đặt classpath ở lệnh `javac` không tự động lưu cấu hình đó vào tệp .class. Khi chạy, cần truyền classpath tương ứng hoặc cấu hình môi trường chạy của build tool/IDE.

## 7. Chọn phiên bản Java đích với --release

`javac` mặc định biên dịch theo phiên bản ngôn ngữ và API của JDK đang dùng. Nếu dự án cần tương thích với một phiên bản Java cụ thể, hãy cân nhắc tùy chọn `--release`:

~~~sh
javac --release 17 -d out HelloOne.java
~~~

`--release 17` yêu cầu compiler hỗ trợ phát hành Java 17 và tạo class file phù hợp với Java 17, đồng thời giới hạn API nền tảng có thể sử dụng theo phiên bản đó. Tùy chọn này có từ JDK 9; compiler phải là JDK 17 hoặc mới hơn để nhắm tới release 17.

Không nên nhầm `--release` với việc chỉ đổi phiên bản `java` dùng để chạy compiler. Cần kiểm tra cả compiler và runtime mục tiêu:

~~~sh
javac -version
java -version
~~~

Nếu dùng compiler mới hơn nhưng cần tạo bytecode chạy trên Java cũ, `--release` thường an toàn hơn cặp tùy chọn riêng `-source` và `-target`, vì `--release` còn ràng buộc tập API Java SE được phép dùng.

## 8. Các tùy chọn javac hữu ích khi biên dịch một class

| Tùy chọn | Mục đích |
|---|---|
| `-d <directory>` | Chọn thư mục nhận class file |
| `-cp` / `-classpath` | Chỉ định classpath để tìm class/JAR phụ thuộc |
| `-sourcepath` | Chỉ định nơi tìm source file phụ thuộc |
| `--release <version>` | Chọn phiên bản Java đích và API nền tảng tương ứng |
| `-encoding UTF-8` | Chỉ định encoding của source file |
| `-g` | Sinh thông tin debug trong class file |
| `-parameters` | Giữ tên tham số phương thức để reflection có thể đọc |
| `-Xlint:all` | Bật nhiều cảnh báo compiler |
| `-Werror` | Báo lỗi khi có warning |
| `-verbose` | In thông tin chi tiết về hoạt động biên dịch |

Ví dụ một lệnh biên dịch có kiểm tra cảnh báo và chỉ định phiên bản:

~~~sh
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/Greeter.java
~~~

Dùng `-encoding UTF-8` giúp kết quả ổn định khi source có ký tự tiếng Việt và môi trường build khác nhau. Nên bật cảnh báo để phát hiện vấn đề sớm; không nên thêm `-Werror` nếu dự án chưa có chính sách xử lý warning rõ ràng.

Có thể đưa danh sách source file dài vào argument file để tránh lệnh quá dài:

~~~text
# sources.args
--release
17
-d
out
src/com/example/Greeter.java
src/com/example/Main.java
~~~

Chạy:

~~~sh
javac @sources.args
~~~

Argument file hữu ích trong script build hoặc khi có nhiều source file; với một class đơn giản, lệnh trực tiếp dễ đọc hơn.

## 9. Quy trình biên dịch một class từ đầu đến cuối

Với class đơn giản không package, có thể làm theo các bước:

1. Cài JDK và bảo đảm terminal tìm thấy `javac` và `java`.
2. Tạo source file có tên khớp public class.
3. Kiểm tra package declaration; nếu có package, giữ đúng cây thư mục source.
4. Xác định dependency cần cho compiler và runtime.
5. Tạo thư mục output nếu dùng `-d`.
6. Chạy `javac` với các tùy chọn cần thiết.
7. Kiểm tra class file được tạo trong đúng vị trí.
8. Chạy class bằng `java` với tên class đầy đủ và classpath đúng.
9. Đối chiếu stdout hoặc hành vi thực tế với mong đợi.

Đối với dự án lớn, nên để Gradle hoặc Maven quản lý source set, dependency, output directory và phiên bản Java. Lệnh `javac` thủ công phù hợp để học cơ chế, biên dịch nhanh một class hoặc chẩn đoán lỗi compiler.

## 10. Lỗi thường gặp và cách xử lý

| Lỗi/hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `'javac' is not recognized` hoặc `command not found` | Chưa cài JDK hoặc PATH không chứa thư mục `bin` của JDK | Kiểm tra JDK, `JAVA_HOME` và PATH; mở terminal mới |
| `class X is public, should be declared in a file named X.java` | Tên file không khớp tên public top-level class | Đổi tên file hoặc tên class để khớp chính xác |
| `package ... does not exist` | Thiếu dependency hoặc classpath/sourcepath sai | Bổ sung JAR, thư mục class hoặc source path phù hợp |
| `cannot find symbol` | Sai tên, thiếu import, class dependency chưa được tìm thấy hoặc lỗi chữ hoa/thường | Kiểm tra khai báo, import, package và classpath |
| `';' expected` hoặc lỗi cú pháp | Source có cú pháp sai hoặc thiếu dấu phân cách | Đọc dòng compiler báo, kiểm tra dấu ngoặc, dấu chấm phẩy và cấu trúc |
| `invalid source release` | Compiler không hỗ trợ phiên bản được yêu cầu | Dùng JDK đủ mới hoặc chọn `--release` được hỗ trợ |
| `error: release version ... not supported` | JDK compiler cũ hơn release đích | Nâng JDK dùng để biên dịch |
| `Could not find or load main class` | Chạy sai tên class, classpath không chứa package root hoặc class chưa được tạo | Dùng tên class đầy đủ và đặt classpath đúng thư mục gốc |
| `UnsupportedClassVersionError` | Runtime cũ hơn phiên bản bytecode được biên dịch | Chạy bằng JDK tương thích hoặc biên dịch với `--release` thấp hơn |
| Class file cũ vẫn chạy dù source đã sửa | Chạy nhầm output directory hoặc chưa biên dịch lại source mới | Xác minh `-d` và classpath; build lại class |

Lỗi biên dịch thường khiến compiler không tạo được class file hợp lệ cho phần source có lỗi. Khi compiler báo lỗi, hãy sửa lỗi đầu tiên rồi biên dịch lại; các lỗi tiếp theo có thể chỉ là hệ quả của lỗi trước.

## 11. Checklist kiểm tra

- [ ] Đang dùng JDK có `javac` và `java`.
- [ ] Tên file khớp với tên public top-level class.
- [ ] Package declaration và đường dẫn source nhất quán.
- [ ] Classpath/sourcepath chứa đủ dependency cần thiết.
- [ ] Thư mục output đã tồn tại nếu dùng `-d`.
- [ ] Phiên bản Java đích phù hợp với runtime dự kiến.
- [ ] Compiler hoàn tất mà không có lỗi.
- [ ] Class file nằm đúng thư mục và package path.
- [ ] Lệnh chạy dùng tên class đầy đủ và classpath đúng.
- [ ] Kết quả chạy khớp với mong đợi.

Khi biên dịch một class, hãy kiểm soát rõ source file, package, dependency và output directory. `javac` sẽ tạo bytecode; `java` dùng JVM để nạp class file và chạy chương trình. Nắm vững hai bước này giúp bạn hiểu lỗi build và dễ dàng mở rộng từ một class sang nhiều package hoặc dự án Java hoàn chỉnh.
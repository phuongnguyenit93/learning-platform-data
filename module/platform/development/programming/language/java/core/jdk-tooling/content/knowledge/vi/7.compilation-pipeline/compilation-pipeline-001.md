# Source code trong Java compilation pipeline

Source code là đầu vào của quy trình biên dịch Java. Đây là văn bản chứa khai báo package, import, class, interface, enum, record, phương thức và các cấu trúc ngôn ngữ khác. Compiler `javac` đọc các tệp nguồn, kiểm tra cú pháp và kiểu, phân giải các kiểu phụ thuộc, sau đó tạo bytecode trong các tệp `.class`.

Hiểu cấu trúc source code và cách compiler tìm các tệp nguồn giúp bạn tổ chức dự án rõ ràng, xử lý lỗi biên dịch nhanh hơn và biết chính xác những gì cần đưa vào một lần build.

## 1. Source code nằm ở đâu trong quy trình biên dịch?

Một quy trình Java đơn giản:

~~~text
Tệp .java
   |
   v
Đọc ký tự và phân tích cú pháp
   |
   v
Phân giải tên và kiểm tra kiểu
   |
   v
Xử lý annotation (nếu được cấu hình)
   |
   v
Sinh bytecode
   |
   v
Tệp .class
   |
   v
JVM nạp và thực thi
~~~

Ở mức khái quát, compiler thực hiện các công việc sau:

1. **Đọc và phân tích cú pháp:** giải mã tệp nguồn, nhận diện package/import/declaration và tạo cấu trúc cú pháp.
2. **Nhập symbol và phân giải kiểu:** tìm các class, interface, method, field và kiểm tra tên được tham chiếu có tồn tại, có thể truy cập và dùng đúng kiểu hay không.
3. **Xử lý annotation:** nếu annotation processor được cấu hình hoặc kích hoạt, compiler gọi processor; processor có thể sinh thêm source file hoặc resource cho các vòng xử lý tiếp theo.
4. **Phân tích ngữ nghĩa và luồng:** kiểm tra quy tắc kiểu, quyền truy cập, definite assignment và các ràng buộc của ngôn ngữ.
5. **Sinh class file:** tạo bytecode và metadata trong tệp `.class`.

Đây là mô tả khái niệm để hiểu vai trò của source code. Chi tiết nội bộ của compiler có thể khác nhau theo phiên bản và không phải API mà ứng dụng nên phụ thuộc.

## 2. Tệp nguồn Java và compilation unit

Tệp nguồn Java thông thường có phần mở rộng `.java`. Một compilation unit có thể gồm:

- Khai báo `package` (có thể không có).
- Các khai báo `import` (có thể không có).
- Một hoặc nhiều khai báo kiểu cấp cao nhất như class, interface, enum, record hoặc annotation interface.

Ví dụ:

~~~java
package com.example;

import java.time.LocalDate;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> names = List.of("Java", "JDK");
        System.out.println(LocalDate.now());
        System.out.println(names);
    }
}
~~~

Trong ví dụ:

- `package com.example;` đặt kiểu `Main` vào package `com.example`.
- `import` cho phép dùng tên đơn giản `LocalDate` và `List` thay vì tên đầy đủ.
- `public class Main` khai báo một lớp công khai.
- `main` là điểm vào của ứng dụng trong cách khởi chạy truyền thống.

Tệp nguồn không chứa bytecode. Sau khi biên dịch, compiler tạo tệp class tương ứng, ví dụ `com/example/Main.class` khi dùng thư mục đầu ra có cấu trúc package.

### 2.1. Tên tệp và tên kiểu

Theo quy ước thông dụng với `javac`, kiểu cấp cao nhất được khai báo là public nằm trong tệp có tên trùng với tên kiểu:

| Khai báo | Tên tệp |
|---|---|
| `public class Main` | `Main.java` |
| `public interface Repository` | `Repository.java` |
| `public record User` | `User.java` |
| `public enum Status` | `Status.java` |

Một tệp có thể chứa các kiểu cấp cao nhất không public khác, nhưng nên giữ mỗi kiểu public trong tệp riêng để cấu trúc dễ tìm và bảo trì.

Tên tệp có phân biệt hoa thường trên nhiều hệ thống. `Main.java` và `main.java` không nên được xem là hai cách viết có thể thay thế nhau.

### 2.2. Package và cấu trúc thư mục

Package nhóm các kiểu liên quan và tránh xung đột tên. Với package `com.example.service`, cấu trúc thư mục thường là:

~~~text
src/
└── com/
    └── example/
        └── service/
            └── UserService.java
~~~

Đầu tệp `UserService.java`:

~~~java
package com.example.service;

public class UserService {
    public String name() {
        return "User service";
    }
}
~~~

Khi biên dịch, `javac` sử dụng đường dẫn thư mục để tìm source file và sắp xếp class file theo package. Package con là package riêng; `import com.example.*` không tự nhập các kiểu trong `com.example.service`.

Nếu không có khai báo `package`, kiểu thuộc unnamed package. Cách này có thể dùng cho ví dụ rất nhỏ, nhưng dự án thực tế nên đặt kiểu trong package có tên để quản lý phụ thuộc và tránh xung đột.

### 2.3. Import

Các dạng import thường gặp:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.*;
import static java.lang.Math.PI;
import static java.lang.Math.max;
~~~

- Import một kiểu cụ thể giúp dùng tên đơn giản.
- Import theo package với `*` áp dụng cho các kiểu trực tiếp trong package đó, không bao gồm package con.
- Static import cho phép tham chiếu thành viên static mà không cần viết tên kiểu ở mỗi lần dùng.
- Import chỉ giúp trình biên dịch phân giải tên; nó không tự đóng gói thư viện vào ứng dụng và không làm một dependency trở nên có sẵn khi chạy.

Các kiểu trong `java.lang` như `String`, `System` và `Math` được import ngầm, nên không cần khai báo `import java.lang.*`.

## 3. Nhiều source file cùng tham gia một lần biên dịch

Trong ứng dụng thực tế, một lớp thường sử dụng kiểu được khai báo ở tệp khác. Ví dụ cấu trúc:

~~~text
project/
└── src/
    └── com/
        └── example/
            ├── Greeting.java
            └── Main.java
~~~

Tệp `Greeting.java`:

~~~java
package com.example;

public class Greeting {
    public String message() {
        return "Hello from source code";
    }
}
~~~

Tệp `Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        Greeting greeting = new Greeting();
        System.out.println(greeting.message());
    }
}
~~~

Biên dịch cả hai tệp:

~~~bash
javac -encoding UTF-8 -d out src/com/example/Greeting.java src/com/example/Main.java
~~~

Chạy:

~~~bash
java -cp out com.example.Main
~~~

Kết quả:

~~~text
Hello from source code
~~~

`javac` biên dịch các source file trong cùng lượt và tự phân giải tham chiếu giữa chúng. Thứ tự tên tệp trên dòng lệnh không quyết định thứ tự phụ thuộc.

## 4. Source path và class path

Compiler cần tìm các kiểu mà source code tham chiếu. Chúng có thể đến từ source file khác hoặc từ class file/JAR đã biên dịch.

| Đường dẫn | Dùng để tìm |
|---|---|
| `--source-path` hoặc `-sourcepath` | Source file bổ sung `.java` |
| `--class-path`, `-classpath` hoặc `-cp` | Class file và thư viện dạng JAR |
| `--module-path` | Module đã biên dịch |
| `--module-source-path` | Source file của một hoặc nhiều module |

Ví dụ, nếu `Main.java` tham chiếu `Greeting` nhưng bạn chỉ truyền `Main.java` vào compiler, hãy đặt source root:

~~~bash
javac -encoding UTF-8 -sourcepath src -d out src/com/example/Main.java
~~~

Compiler tìm `Greeting.java` theo package path bên dưới `src` và có thể biên dịch tệp đó như một source dependency.

Nếu `Greeting` đã được biên dịch thành class file trong thư mục `lib-classes`, dùng class path:

~~~bash
javac -cp lib-classes -d out src/com/example/Main.java
~~~

Khi có nhiều JAR hoặc thư mục, phân tách đường dẫn bằng ký tự theo hệ điều hành:

~~~bash
# macOS / Linux
javac -cp "lib/a.jar:lib/b.jar" -d out src/com/example/Main.java
~~~

~~~powershell
# Windows PowerShell
javac -cp "lib/a.jar;lib/b.jar" -d out src/com/example/Main.java
~~~

Đừng nhầm source path với class path: một đường dẫn tìm source code; đường dẫn kia tìm kiểu đã biên dịch và thư viện. Nếu không chỉ định source path trong chế độ không module, compiler có thể tìm source file trên class path theo quy tắc mặc định, nhưng cấu hình tường minh thường dễ hiểu và ổn định hơn.

## 5. Encoding của source code

Tệp Java là văn bản. Compiler phải giải mã byte trong tệp thành ký tự trước khi phân tích cú pháp. Nếu editor lưu UTF-8 nhưng compiler đọc bằng charset mặc định khác, ký tự tiếng Việt hoặc ký tự ngoài ASCII có thể bị lỗi.

Nên thống nhất UTF-8 trong dự án và khai báo rõ khi biên dịch:

~~~bash
javac -encoding UTF-8 -d out src/com/example/Main.java
~~~

Một ví dụ có tiếng Việt:

~~~java
public class VietnameseText {
    public static void main(String[] args) {
        System.out.println("Xin chào Java");
    }
}
~~~

Lưu tệp bằng UTF-8 rồi biên dịch:

~~~bash
javac -encoding UTF-8 VietnameseText.java
java VietnameseText
~~~

Kết quả:

~~~text
Xin chào Java
~~~

Tùy chọn `-encoding` điều khiển cách `javac` đọc source file. Nó không quyết định encoding của dữ liệu đầu ra mà chương trình ghi ra terminal; phần đó phụ thuộc cách ứng dụng xuất dữ liệu và môi trường console.

## 6. Thư mục source và thư mục output

Nên tách source code khỏi class file được tạo ra:

~~~text
project/
├── src/
│   └── com/example/
│       ├── Greeting.java
│       └── Main.java
└── out/
    └── com/example/
        ├── Greeting.class
        └── Main.class
~~~

Dùng `-d` để chỉ định output directory:

~~~bash
javac -encoding UTF-8 -d out src/com/example/Greeting.java src/com/example/Main.java
~~~

Nếu bỏ `-d`, `javac` thường ghi class file bên cạnh source file. Điều này có thể làm thư mục source lẫn tệp sinh ra, khiến việc quản lý, đóng gói và làm sạch build khó hơn.

Một số tùy chọn hữu ích khác:

| Tùy chọn | Vai trò |
|---|---|
| `-d directory` | Thư mục class file đầu ra |
| `-s directory` | Thư mục source file được sinh bởi annotation processor |
| `-encoding UTF-8` | Charset đọc source file |
| `-g` | Sinh thông tin debug |
| `-Xlint:all` | Bật cảnh báo bổ sung |
| `-Werror` | Dừng biên dịch nếu có warning |

## 7. Module source code

Trong dự án dùng Java Platform Module System, một module có thể chứa tệp `module-info.java` để khai báo tên module, các module cần dùng và package được export.

Ví dụ:

~~~text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/Main.java
~~~

`module-info.java`:

~~~java
module com.example.app {
    exports com.example;
}
~~~

`Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from module");
    }
}
~~~

Biên dịch module:

~~~bash
javac --module-source-path src -d out -m com.example.app
~~~

Chạy module:

~~~bash
java --module-path out -m com.example.app/com.example.Main
~~~

Khi biên dịch một module, compiler xét module declaration và các module phụ thuộc trên module path. Khi biên dịch nhiều module cùng lúc, cấu trúc source tree cần theo module source path. Không đặt `module-info.java` vào package như một lớp Java thông thường.

## 8. Annotation và source code được sinh tự động

Annotation có thể cung cấp metadata cho compiler, framework hoặc công cụ build. Ví dụ:

~~~java
@Override
public String toString() {
    return "Example";
}
~~~

Một số thư viện sử dụng annotation processor để sinh mã nguồn hoặc metadata trong quá trình biên dịch. Processor có thể đọc annotation và model của chương trình, sau đó tạo source file mới cho compiler xử lý ở vòng tiếp theo.

Các tùy chọn thường gặp:

- `-processor`: chỉ định annotation processor.
- `--processor-path`: nơi tìm processor trên class path.
- `--processor-module-path`: nơi tìm processor trên module path.
- `-proc:none`: tắt annotation processing.
- `-s generated-sources`: thư mục đặt source file do processor sinh ra.

Source file được sinh tự động là một phần của compilation pipeline, nhưng cần phân biệt với source code do lập trình viên duy trì. Không nên chỉnh sửa trực tiếp tệp sinh ra nếu lần build tiếp theo sẽ tạo lại chúng.

## 9. Chẩn đoán lỗi từ source code

Các lỗi source code thường được phát hiện trước khi class file được tạo.

| Loại lỗi | Ví dụ | Ý nghĩa |
|---|---|---|
| Lỗi cú pháp | Thiếu dấu `;` hoặc dấu `}` | Cấu trúc source không đúng ngữ pháp |
| Không tìm thấy symbol | Gọi tên class/method chưa được khai báo hoặc import | Compiler không phân giải được tên |
| Sai kiểu | Gán `String` vào biến `int` | Kiểu dữ liệu không tương thích |
| Không đủ quyền truy cập | Dùng thành viên `private` từ lớp khác | Vi phạm quy tắc access control |
| Lỗi package/path | Package khai báo và vị trí source tree không khớp | Compiler không tìm được source hoặc tên kiểu mong đợi |
| Lỗi encoding | Ký tự bị hỏng khi đọc source | Charset của tệp và compiler không thống nhất |

Ví dụ lỗi kiểu:

~~~java
public class TypeError {
    public static void main(String[] args) {
        int count = "three";
    }
}
~~~

Compiler báo kiểu không tương thích vì chuỗi không thể gán trực tiếp cho biến `int`. Lỗi này khác lỗi runtime: chương trình chưa tạo được class file hợp lệ cho lần biên dịch đó.

Có thể bật cảnh báo bổ sung:

~~~bash
javac -Xlint:all -encoding UTF-8 -d out src/com/example/Main.java
~~~

Nếu muốn warning cũng làm build thất bại, thêm `-Werror` sau khi đã xử lý các warning hiện có:

~~~bash
javac -Xlint:all -Werror -encoding UTF-8 -d out src/com/example/Main.java
~~~

## 10. Quy trình thực hành

Với dự án gồm `Main.java` và `Greeting.java` trong package `com.example`, có thể làm theo thứ tự:

1. **Tổ chức source tree:** đặt source root là `src` và thư mục con theo package.
2. **Kiểm tra tên tệp:** bảo đảm kiểu public có tên trùng với tệp chứa nó.
3. **Kiểm tra package/import:** package declaration khớp với package dự kiến; import chỉ tới kiểu có thể truy cập.
4. **Thống nhất encoding:** lưu source file bằng UTF-8.
5. **Biên dịch:** dùng `javac -encoding UTF-8 -Xlint:all -d out ...`.
6. **Đọc diagnostics:** xử lý lỗi cú pháp, symbol, kiểu và quyền truy cập.
7. **Kiểm tra output:** xác nhận class file được tạo theo cấu trúc package trong `out`.
8. **Chạy thử:** dùng `java -cp out com.example.Main` để xác nhận ứng dụng khởi chạy.

Khi dự án lớn hơn, hãy để Maven, Gradle hoặc IDE quản lý source set và compilation task, nhưng vẫn hiểu các khái niệm `source-path`, `class-path`, module path và output directory mà compiler sử dụng.

## 11. Ghi nhớ

Source code là bản mô tả chương trình ở cấp ngôn ngữ Java; compiler đọc các compilation unit, phân giải các kiểu phụ thuộc, kiểm tra cú pháp/ngữ nghĩa và tạo class file. Package/import quyết định cách đặt tên và tham chiếu kiểu. Cấu trúc thư mục nên phản ánh package/module. Encoding, source path, class path và output directory quyết định compiler đọc đầu vào và ghi đầu ra ở đâu.

Khi gặp lỗi build, hãy kiểm tra tệp nguồn, package, import, encoding và đường dẫn tìm kiểu trước khi điều tra bytecode hoặc JVM runtime.

Tài liệu tham khảo: [The javac Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), các mục *Source Files*, *Arrangement of Source Code*, *Configuring a Compilation* và *Annotation Processing*; [Java Language Specification, Chapter 7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html).
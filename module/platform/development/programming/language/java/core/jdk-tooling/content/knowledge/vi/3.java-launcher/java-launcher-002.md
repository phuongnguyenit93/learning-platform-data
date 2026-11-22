# Chạy class bằng Java launcher

## 1. Java launcher làm gì?

Java launcher là chương trình dòng lệnh `java` đi kèm JDK. Nó khởi động Java Virtual Machine (JVM), tìm và nạp lớp cần chạy, sau đó gọi phương thức entry point của lớp đó. Khi làm việc với một chương trình Java đã biên dịch, launcher nhận tên lớp đầy đủ và đường dẫn chứa các tệp bytecode.

Cần phân biệt hai lệnh trong quy trình cơ bản:

- `javac` biên dịch mã nguồn `.java` thành bytecode `.class`.
- `java` khởi chạy lớp đã biên dịch trên JVM.

Ví dụ luồng làm việc:

~~~text
Hello.java --javac--> Hello.class --java--> JVM chạy phương thức main
~~~

Lệnh tổng quát để chạy một lớp trên classpath:

~~~bash
java [JVM options] -cp <classpath> <ten-lop-day-du> [tham-so-ung-dung...]
~~~

Trong đó:

- `JVM options` là tùy chọn cấu hình máy ảo, ví dụ `-Xmx512m` hoặc `-Dapp.mode=dev`.
- `-cp` hoặc `--class-path` chỉ định nơi launcher tìm lớp và thư viện.
- `<ten-lop-day-du>` là tên lớp theo quy tắc Java, gồm package nếu lớp nằm trong package.
- Các giá trị sau tên lớp được truyền vào `main(String[] args)` của chương trình.

Các tùy chọn dành cho launcher/JVM phải nằm trước tên lớp chính. Những đối số đặt sau tên lớp được xem là đối số của ứng dụng.

## 2. Điểm vào chương trình: phương thức `main`

Với Java 17, một lớp có thể được khởi chạy theo cách thông thường khi cung cấp phương thức main công khai, tĩnh và trả về void:

~~~java
public static void main(String[] args)
~~~

`String[] args` là mảng chứa các đối số mà người chạy truyền vào. Có thể khai báo tham số dạng varargs `String... args` vì nó tương đương với mảng `String[]` ở cấp kiểu dữ liệu.

Ví dụ lớp đơn giản:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from Java!");
    }
}
~~~

Giả sử tệp được lưu thành `Hello.java`. Biên dịch và chạy:

~~~bash
javac Hello.java
java Hello
~~~

Kết quả:

~~~text
Hello from Java!
~~~

Ở đây không cần ghi đuôi `.class` trong lệnh `java Hello`. Launcher nhận tên lớp `Hello`, tìm tệp bytecode `Hello.class` trên classpath và gọi phương thức main.

Với lớp trong package, tên lớp phải bao gồm package. Ví dụ:

~~~java
package com.example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from com.example!");
    }
}
~~~

Lưu mã nguồn ở `src/com/example/Hello.java`, biên dịch vào thư mục `out` rồi chạy bằng tên đầy đủ:

~~~bash
javac -d out src/com/example/Hello.java
java -cp out com.example.Hello
~~~

Kết quả:

~~~text
Hello from com.example!
~~~

Một số quy tắc quan trọng:

- Dùng tên lớp đầy đủ như `com.example.Hello`, không dùng đường dẫn tệp `com/example/Hello.class`.
- Không thêm phần mở rộng `.class` sau tên lớp.
- Nếu lớp có khai báo `package`, cấu trúc thư mục bytecode phải phản ánh package đó.
- Tên package và lớp phân biệt chữ hoa/chữ thường.
- Phương thức main theo quy ước Java 17 phải là `public static void main(String[] args)` hoặc dạng varargs tương đương. Một phương thức `main` không tĩnh, không công khai hoặc có kiểu trả về khác không phải entry point thông thường mà launcher tìm kiếm.

## 3. Ví dụ hoàn chỉnh: biên dịch và chạy một class

Tạo cấu trúc thư mục sau từ thư mục gốc dự án:

~~~text
java-launcher-demo/
├── src/
│   └── com/
│       └── example/
│           └── Greeter.java
└── out/
~~~

Nội dung `src/com/example/Greeter.java`:

~~~java
package com.example;

public class Greeter {
    public static void main(String[] args) {
        String name = args.length == 0
                ? "Java"
                : String.join(" ", args);

        System.out.println("Hello, " + name + "!");
    }
}
~~~

Biên dịch với JDK 17 trở lên, đồng thời yêu cầu compiler dùng API và bytecode Java 17:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/com/example/Greeter.java
~~~

Chạy lớp mà không truyền đối số:

~~~bash
java -cp out com.example.Greeter
~~~

Stdout:

~~~text
Hello, Java!
~~~

Truyền đối số cho ứng dụng:

~~~bash
java -cp out com.example.Greeter Ada Lovelace
~~~

Stdout:

~~~text
Hello, Ada Lovelace!
~~~

Truyền tên có dấu cách thành một đối số duy nhất bằng cách đặt trong dấu nháy:

~~~bash
java -cp out com.example.Greeter "Ada Lovelace"
~~~

Stdout vẫn là:

~~~text
Hello, Ada Lovelace!
~~~

Trong ví dụ này, chương trình dùng `String.join(" ", args)` nên cả hai cách truyền hai từ riêng biệt và một chuỗi có dấu cách đều tạo ra cùng lời chào. Nếu ứng dụng cần phân biệt từng đối số, hãy đọc riêng `args[0]`, `args[1]` thay vì ghép chúng.

Trên Windows PowerShell, các lệnh tương ứng có thể chạy từ thư mục gốc dự án:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src/com/example/Greeter.java
java -cp out com.example.Greeter "Ada Lovelace"
~~~

Nếu thư mục `out` đã tồn tại, lệnh tạo thư mục vẫn giữ nguyên nội dung thư mục đó. Trong một lần build sạch, nên dùng thư mục đầu ra riêng cho lần biên dịch hiện tại để tránh vô tình chạy bytecode cũ còn sót lại.

## 4. Classpath: nơi tìm class và thư viện

Classpath là danh sách thư mục và tệp JAR mà Java launcher dùng để tìm các lớp trên classpath (unnamed module). Khi chạy chương trình, classpath phải chứa lớp chính và tất cả thư viện cần thiết tại thời điểm chạy.

Hai cách khai báo phổ biến:

~~~bash
java -cp out com.example.Greeter
java --class-path out com.example.Greeter
~~~

`-cp` và `--class-path` có cùng ý nghĩa. Có thể truyền nhiều mục classpath, phân tách bằng ký tự phụ thuộc hệ điều hành:

| Môi trường | Dấu phân cách | Ví dụ |
|---|---|---|
| Windows | Dấu chấm phẩy `;` | `out;lib/example.jar` |
| Linux/macOS | Dấu hai chấm `:` | `out:lib/example.jar` |

Ví dụ ứng dụng cần các JAR nằm trong thư mục `lib`:

~~~bash
# Windows
java -cp "out;lib/*" com.example.Greeter

# Linux/macOS
java -cp "out:lib/*" com.example.Greeter
~~~

Mẫu `lib/*` yêu cầu launcher đưa các tệp JAR trực tiếp trong thư mục `lib` vào classpath. Nó không tìm JAR đệ quy trong các thư mục con. Dùng dấu nháy quanh toàn bộ classpath để tránh shell diễn giải ký tự đặc biệt ngoài ý muốn.

Classpath được phân tích theo thứ tự từ trái sang phải. Nếu nhiều mục chứa cùng một tên lớp, mục xuất hiện trước có thể được dùng trước. Vì vậy, tránh để nhiều phiên bản của cùng thư viện trên classpath; chúng có thể gây lỗi khó đoán như `NoSuchMethodError` hoặc hành vi không nhất quán.

Nếu không chỉ định `-cp` hoặc `--class-path`, launcher sử dụng classpath mặc định, thường là thư mục làm việc hiện tại. Biến môi trường `CLASSPATH` cũng có thể đặt giá trị mặc định này. Khi lệnh đã chỉ định `-cp`, classpath trong lệnh sẽ thay thế giá trị mặc định từ `CLASSPATH`.

Trong thực tế, nên khai báo classpath tường minh trong script chạy hoặc cấu hình của IDE/CI. Đường dẫn tương đối như `out` được tính từ thư mục làm việc hiện tại của tiến trình, không tự động tính từ vị trí tệp `.java`.

## 5. Truyền đối số cho chương trình

Mọi giá trị đặt sau tên lớp chính được chuyển vào mảng `args`. Launcher không tự diễn giải các giá trị này thành tùy chọn JVM.

Ví dụ:

~~~bash
java -cp out com.example.Greeter "Ada Lovelace" 3
~~~

Với lệnh trên, chương trình nhận:

| Biểu thức | Giá trị |
|---|---|
| `args.length` | `2` |
| `args[0]` | `Ada Lovelace` |
| `args[1]` | `3` |

Nếu cần một giá trị số, chương trình phải tự chuyển kiểu và kiểm tra lỗi đầu vào:

~~~java
public class Sum {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println("Usage: Sum <a> <b>");
            System.exit(1);
            return;
        }

        try {
            int a = Integer.parseInt(args[0]);
            int b = Integer.parseInt(args[1]);
            System.out.println(a + b);
        } catch (NumberFormatException ex) {
            System.err.println("Arguments must be integers.");
            System.exit(1);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -d out Sum.java
java -cp out Sum 12 30
~~~

Stdout:

~~~text
42
~~~

Nếu truyền sai số lượng hoặc định dạng, ứng dụng tự xử lý và có thể kết thúc với mã thoát khác 0. Launcher chỉ chuyển đối số; việc kiểm tra ý nghĩa và tính hợp lệ thuộc về chương trình.

## 6. Tùy chọn JVM và thứ tự đặt tham số

Một số tùy chọn thường đặt trước tên lớp:

| Tùy chọn | Tác dụng |
|---|---|
| `-Xms128m` | Đặt kích thước heap ban đầu. |
| `-Xmx512m` | Đặt giới hạn heap tối đa. |
| `-Dapp.mode=dev` | Đặt system property có tên `app.mode` và giá trị `dev`. |
| `-ea` hoặc `-enableassertions` | Bật câu lệnh assertion. |
| `-verbose:class` | In thông tin nạp lớp; hữu ích khi chẩn đoán class loading. |
| `--version` | In phiên bản launcher/JDK rồi kết thúc. |
| `--help` | Hiển thị trợ giúp của launcher. |

Ví dụ kết hợp cấu hình JVM và classpath:

~~~bash
java -Xms128m -Xmx512m -Dapp.mode=dev -ea -cp out com.example.Greeter "Ada Lovelace"
~~~

Trong chương trình, có thể đọc system property:

~~~java
String mode = System.getProperty("app.mode", "default");
System.out.println(mode);
~~~

Thứ tự có ý nghĩa. Ví dụ:

~~~bash
# -Dapp.mode=dev là tùy chọn JVM
java -Dapp.mode=dev -cp out com.example.Greeter

# --debug là đối số của ứng dụng
java -cp out com.example.Greeter --debug
~~~

Ở lệnh thứ hai, `--debug` được truyền vào `args`. Nó không phải tùy chọn launcher vì nó nằm sau tên lớp. Nếu cần ứng dụng hiểu `--debug`, chính mã ứng dụng phải phân tích đối số đó.

## 7. Chạy class có phụ thuộc vào class khác

Một lớp có thể biên dịch thành công nhưng vẫn không chạy được nếu thiếu thư viện phụ thuộc trong runtime classpath. Classpath lúc biên dịch và lúc chạy là hai cấu hình độc lập: compiler cần tìm được kiểu mà mã nguồn tham chiếu; launcher cần tìm được bytecode của tất cả lớp được sử dụng khi chạy.

Ví dụ có hai lớp:

`src/com/example/Message.java`:

~~~java
package com.example;

public class Message {
    public static String greeting(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

`src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Message.greeting(name));
    }
}
~~~

Biên dịch cả hai lớp vào `out`:

~~~bash
javac --release 17 -d out src/com/example/Message.java src/com/example/Main.java
~~~

Chạy lớp có phương thức main:

~~~bash
java -cp out com.example.Main "JDK Tooling"
~~~

Stdout:

~~~text
Hello, JDK Tooling!
~~~

Trong dự án có thư viện bên ngoài, thêm thư mục output và JAR phụ thuộc vào classpath runtime. Ví dụ trên Linux/macOS:

~~~bash
java -cp "out:lib/library-a.jar:lib/library-b.jar" com.example.Main
~~~

Trên Windows:

~~~powershell
java -cp "out;lib/library-a.jar;lib/library-b.jar" com.example.Main
~~~

Không nên giả định rằng việc compiler tìm thấy thư viện lúc build đồng nghĩa launcher tự tìm thấy thư viện lúc chạy. Cần cấu hình cả hai giai đoạn.

## 8. Chạy class thuộc named module

Với dự án dùng Java Platform Module System (JPMS), module được đặt trên module path. Khi đó, dùng tùy chọn `--module-path` và `-m` (hoặc `--module`) để chỉ định module cùng lớp chính.

Ví dụ cấu trúc:

~~~text
src/
├── module-info.java
└── com/
    └── example/
        └── Main.java
~~~

`module-info.java`:

~~~java
module com.example.app {
}
~~~

`src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from module!");
    }
}
~~~

Biên dịch module vào thư mục `mods/com.example.app`:

~~~bash
javac --release 17 -d mods/com.example.app src/module-info.java src/com/example/Main.java
~~~

Chạy lớp main của module:

~~~bash
java --module-path mods -m com.example.app/com.example.Main
~~~

Stdout:

~~~text
Hello from module!
~~~

Cú pháp `-m module/class` chỉ định tên module và tên đầy đủ của lớp chính. Module path chứa các module đã biên dịch hoặc modular JAR. Đây là cơ chế khác với classpath:

- Classpath chủ yếu tìm lớp trên classpath và đưa chúng vào unnamed module.
- Module path tìm các module có mô tả module và áp dụng quy tắc phụ thuộc/đóng gói của JPMS.

Không đặt thư mục module vào classpath rồi kỳ vọng launcher tự chạy nó như một named module. Hãy chọn classpath hoặc module path theo cách dự án được đóng gói.

## 9. Phân biệt chạy class, chạy JAR và source-file mode

Java launcher hỗ trợ nhiều chế độ khởi chạy. Chúng dùng chung lệnh `java` nhưng cách chỉ định chương trình khác nhau.

| Chế độ | Cú pháp | Khi dùng |
|---|---|---|
| Chạy class | `java -cp out com.example.Main` | Có bytecode lớp chính và muốn chỉ định classpath. |
| Chạy JAR executable | `java -jar app.jar` | JAR có manifest khai báo `Main-Class`. |
| Chạy module | `java --module-path mods -m module.name/com.example.Main` | Ứng dụng được tổ chức thành named module. |
| Source-file mode | `java Hello.java` | Chạy trực tiếp một tệp nguồn; launcher tự biên dịch theo cơ chế source-file mode, có từ Java 11. |

Khi chạy JAR:

~~~bash
java -jar app.jar
~~~

Launcher đọc lớp khởi chạy từ thuộc tính `Main-Class` trong manifest. Các đối số ứng dụng đặt sau tên JAR. Ở chế độ `-jar`, classpath truyền riêng bằng `-cp` không được dùng để thay thế classpath do JAR xác định; nếu cần thư viện ngoài, hãy đóng gói hoặc cấu hình đường dẫn phụ thuộc phù hợp.

Source-file mode:

~~~bash
java Hello.java
~~~

là cách tiện lợi cho chương trình nhỏ hoặc thử nghiệm. Nếu đã có `.class` và muốn chủ động quản lý output, dependency và cấu hình runtime, hãy dùng chế độ chạy class được mô tả ở các phần trước.

## 10. Chạy từ terminal, IDE và script

Dù khởi chạy từ terminal, IDE hay script, JVM vẫn cần các thông tin tương tự: JDK/runtime được chọn, lớp chính hoặc module, classpath/module path, tùy chọn JVM và đối số ứng dụng.

Trong IDE, cấu hình Run thường gồm:

- Main class: ví dụ `com.example.Main`.
- Working directory: thư mục mà các đường dẫn tương đối của ứng dụng được tính từ đó.
- Use classpath of module: module/project output và thư viện cần thiết.
- VM options: ví dụ `-Xmx512m` hoặc `-Dapp.mode=dev`.
- Program arguments: đối số được truyền vào `main(String[] args)`.

Khi chạy bằng script, nên ghi rõ thư mục làm việc và classpath. Ví dụ Bash:

~~~bash
#!/usr/bin/env bash
set -eu
cd /path/to/project
java -cp "out:lib/*" com.example.Main "$@"
~~~

`"$@"` chuyển tiếp từng đối số script nhận được thành đối số riêng cho chương trình Java. Trên Windows, script PowerShell có thể dùng:

~~~powershell
Set-Location "C:\path\to\project"
java -cp "out;lib/*" com.example.Main @args
exit $LASTEXITCODE
~~~

Dùng đường dẫn thực tế của dự án khi cấu hình script. Với CI, hãy cố định JDK cần dùng và để bước build tạo thư mục output trước bước chạy.

## 11. Lỗi thường gặp khi chạy class

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `Could not find or load main class` | Classpath thiếu thư mục output, sai tên lớp hoặc đang chạy từ thư mục làm việc khác. | Kiểm tra `-cp`, working directory, package và tên lớp đầy đủ. |
| `ClassNotFoundException` | Mã dùng reflection hoặc thư viện yêu cầu một lớp không có trong runtime classpath/module path. | Bổ sung JAR/module đúng phiên bản và kiểm tra cấu hình runtime. |
| `NoClassDefFoundError` | Một lớp cần thiết không được tìm thấy khi JVM nạp hoặc sử dụng lớp. | Kiểm tra dependency lúc chạy; so sánh classpath runtime với dependency của build. |
| `Main method not found` | Thiếu entry point đúng chuẩn hoặc chữ ký main không hợp lệ. | Dùng `public static void main(String[] args)`. |
| `UnsupportedClassVersionError` | Bytecode được biên dịch bằng phiên bản Java mới hơn runtime đang chạy. | Dùng runtime phù hợp hoặc build với `javac --release` theo phiên bản thấp hơn cần hỗ trợ. |
| `NoSuchMethodError` / `NoSuchFieldError` | Runtime nạp phiên bản thư viện không tương thích với phiên bản dùng lúc biên dịch. | Loại bỏ JAR trùng/lệch phiên bản và sắp xếp lại dependency. |
| `Exception in thread "main"` | Chương trình đã được khởi chạy nhưng phát sinh ngoại lệ không được xử lý. | Đọc stack trace, tìm frame đầu tiên thuộc mã ứng dụng và xử lý nguyên nhân. |
| Lệnh `java` không được nhận diện | JDK chưa nằm trong `PATH` hoặc terminal đang dùng cấu hình môi trường cũ. | Kiểm tra `java -version`, `where java` trên Windows hoặc `which java` trên macOS/Linux. |

Một cách chẩn đoán nhanh:

1. Xác nhận runtime: chạy `java -version`.
2. Xác nhận thư mục hiện tại: kiểm tra nơi chứa thư mục `out`.
3. Xác nhận bytecode đã được tạo: kiểm tra `out/com/example/Main.class`.
4. Chạy lại với tên lớp đầy đủ và classpath tường minh.
5. Nếu lỗi là thiếu dependency, bổ sung đúng JAR/module vào runtime path.
6. Nếu lỗi xảy ra sau khi chương trình bắt đầu chạy, xử lý stack trace như lỗi ứng dụng thay vì lỗi launcher.

Khi cần xem lớp được nạp từ đâu, có thể dùng `-verbose:class` để in thông tin class loading. Output này có thể dài; chỉ bật khi cần điều tra.

## 12. Checklist trước khi chạy class

- Đã biên dịch mã nguồn thành công bằng `javac`.
- Đang chạy đúng JDK/runtime mong muốn.
- Đã xác định đúng tên lớp chính, bao gồm package.
- Classpath chứa thư mục output và toàn bộ dependency cần thiết.
- Working directory phù hợp với các đường dẫn tương đối.
- Tùy chọn JVM được đặt trước tên lớp.
- Đối số ứng dụng được đặt sau tên lớp và được quote đúng nếu chứa dấu cách.
- Nếu dùng JPMS, module path và tên module/lớp chính được khai báo đúng.
- Đã kiểm tra stdout, stderr và exit code khi chạy trong script hoặc CI.

Khi chạy một class đã biên dịch, hãy xác định tên lớp đầy đủ và vị trí chứa bytecode trước, sau đó dùng `java -cp <classpath> <ten-lop-day-du>`. Nếu chương trình cần thư viện, module hoặc cấu hình JVM, bổ sung chúng trước tên lớp; các đối số đặt sau tên lớp sẽ được chuyển vào `main`.

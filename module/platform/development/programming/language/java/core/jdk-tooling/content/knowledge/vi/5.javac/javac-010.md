# Lỗi biên dịch Java

Lỗi biên dịch xảy ra khi trình biên dịch Java `javac` không thể chuyển mã nguồn thành bytecode hợp lệ. Khi đó, lệnh biên dịch kết thúc với trạng thái khác 0 và thường không tạo được đầy đủ các tệp `.class` cần thiết. Nguyên nhân có thể nằm ở cú pháp, kiểu dữ liệu, tên lớp/phương thức, quyền truy cập, package, dependency, module hoặc cấu hình phiên bản Java.

Biết cách đọc diagnostic của `javac` giúp bạn sửa đúng nguyên nhân thay vì đoán. Hãy bắt đầu từ thông báo đầu tiên có ý nghĩa, xác định vị trí và biểu thức liên quan, rồi biên dịch lại để kiểm tra. Một lỗi gốc có thể kéo theo nhiều thông báo khác, vì vậy sửa từng nguyên nhân theo thứ tự thường hiệu quả hơn sửa hàng loạt các dòng báo lỗi.

## 1. Phân biệt lỗi biên dịch, cảnh báo và lỗi runtime

Ba loại kết quả sau có ý nghĩa khác nhau:

- **Compile-time error:** mã nguồn vi phạm cú pháp hoặc quy tắc của ngôn ngữ/kiểu dữ liệu, hoặc compiler không tìm thấy lớp/phương thức cần thiết. `javac` không thể hoàn thành việc biên dịch.
- **Compiler warning:** mã vẫn có thể biên dịch, nhưng compiler cảnh báo về một cấu trúc đáng ngờ, không an toàn hoặc có thể gây lỗi. Warning không nhất thiết làm lệnh thất bại, trừ khi bật `-Werror` hoặc build tool cấu hình warning thành lỗi.
- **Runtime error/exception:** mã đã biên dịch và chương trình bắt đầu chạy, nhưng trong lúc thực thi xảy ra vấn đề, ví dụ `NullPointerException`, `ArithmeticException` hoặc `FileNotFoundException`.

Ví dụ, gán một chuỗi vào biến `int` là lỗi kiểu dữ liệu và bị phát hiện khi biên dịch. Gọi phương thức trên một tham chiếu đang là `null` thường chỉ phát sinh `NullPointerException` khi dòng lệnh đó được thực thi.

| Giai đoạn | Ví dụ | Công cụ/vị trí phát hiện |
|---|---|---|
| Biên dịch | Thiếu dấu `;`, sai kiểu, không tìm thấy symbol | `javac` |
| Khởi chạy/nạp lớp | Thiếu lớp lúc runtime, phiên bản class không tương thích | Java launcher/JVM |
| Thực thi | `NullPointerException`, lỗi I/O, lỗi logic | JVM và ứng dụng |

Không phải mọi thông báo có chữ “Java error” đều là lỗi biên dịch. Ví dụ `ClassNotFoundException` có thể xảy ra lúc runtime do thiếu dependency trên classpath, trong khi `package ... does not exist` thường là lỗi biên dịch khi compiler không tìm thấy package cần thiết.

## 2. Đọc thông báo lỗi của `javac`

Một diagnostic thường cho biết:

1. Tên tệp nguồn.
2. Số dòng và có thể có vị trí cột.
3. Dòng mã nguồn gây vấn đề.
4. Dấu `^` chỉ vị trí compiler phát hiện vấn đề.
5. Loại diagnostic và thông điệp giải thích.

Ví dụ minh họa:

~~~text
src/Main.java:4: error: incompatible types: String cannot be converted to int
        int age = "twenty";
                  ^
1 error
~~~

Cách đọc:

- `src/Main.java:4` cho biết tệp và dòng có vấn đề.
- `error` cho biết đây là lỗi làm biên dịch thất bại.
- `incompatible types` cho biết hai kiểu dữ liệu không tương thích.
- `String cannot be converted to int` nêu chiều chuyển đổi không hợp lệ.
- Dấu `^` đánh dấu biểu thức mà compiler đang chỉ ra.

Thông điệp cụ thể, cách xuống dòng và vị trí dấu `^` có thể khác giữa các phiên bản JDK. Hãy dựa vào nội dung diagnostic và mã nguồn thực tế, không phụ thuộc tuyệt đối vào một chuỗi thông báo cố định.

### Nên đọc lỗi theo thứ tự nào?

- Đọc lỗi đầu tiên trong tệp do bạn viết hoặc tệp liên quan trực tiếp đến thay đổi vừa thực hiện.
- Xem dòng được chỉ ra và một vài dòng trước đó; dấu lỗi có thể xuất hiện ở nơi compiler nhận ra vấn đề, còn nguyên nhân thật có thể nằm ở khai báo phía trước.
- Kiểm tra tên symbol, kiểu dữ liệu, chữ ký phương thức và package.
- Sửa một nguyên nhân gốc rồi chạy lại compiler.
- Chỉ xử lý các lỗi tiếp theo sau khi lỗi đầu tiên đã được giải quyết.

Một dấu ngoặc nhọn thiếu hoặc một khai báo sai ở đầu tệp có thể khiến compiler phân tích sai nhiều dòng phía sau. Khi có hàng chục diagnostic liên tiếp, hãy tìm lỗi cú pháp hoặc khai báo đầu tiên thay vì sửa từng thông báo cuối.

## 3. Các nhóm lỗi biên dịch thường gặp

### 3.1. Lỗi cú pháp

Lỗi cú pháp xảy ra khi mã nguồn không tuân theo grammar của Java. Các nguyên nhân phổ biến gồm:

- Thiếu dấu chấm phẩy `;`.
- Thiếu hoặc thừa dấu ngoặc `{}`, `()` hoặc `[]`.
- Đặt `else`, `catch` hoặc `finally` sai vị trí.
- Viết sai cấu trúc khai báo lớp, phương thức hoặc câu lệnh.
- Dùng từ khóa sai ngữ cảnh.

Ví dụ sai:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello")
    }
}
~~~

Dòng `println` thiếu dấu `;`. Sửa lại:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
~~~

Biên dịch và chạy:

~~~text
javac Main.java
java Main
~~~

Stdout:

~~~text
Hello
~~~

Khi gặp `';' expected`, `')' expected`, `illegal start of expression` hoặc thông báo tương tự, kiểm tra cấu trúc câu lệnh hiện tại và các dấu ngoặc ở những dòng ngay trước đó. Đừng mặc định rằng dấu `^` luôn trỏ đúng ký tự cần chèn.

### 3.2. Lỗi không tìm thấy symbol — `cannot find symbol`

Compiler không tìm thấy tên biến, phương thức, lớp hoặc trường mà mã đang tham chiếu.

Ví dụ sai:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println(mesage);
    }
}
~~~

Tên biến đã khai báo hoặc dự định dùng là `message`, nhưng dòng in lại viết `mesage`. Compiler không thể tìm thấy symbol đó.

Sửa:

~~~java
public class Main {
    public static void main(String[] args) {
        String message = "Hello";
        System.out.println(message);
    }
}
~~~

Những nguyên nhân khác:

- Biến chưa được khai báo hoặc nằm ngoài scope.
- Viết sai chữ hoa/chữ thường; tên Java phân biệt hoa thường.
- Gọi nhầm tên phương thức hoặc trường.
- Import thiếu lớp.
- Lớp chưa có trong source path/classpath/module path.
- Dùng API không tồn tại trong phiên bản Java mục tiêu.
- Một khai báo trước đó thất bại khiến compiler không nhận diện được symbol phía sau.

Khi đọc `cannot find symbol`, chú ý phần `symbol:` và `location:` trong diagnostic nếu có. Chúng cho biết compiler đang tìm loại thành phần nào và trong lớp/phạm vi nào.

### 3.3. Lỗi không tương thích kiểu — `incompatible types`

Java là ngôn ngữ định kiểu tĩnh. Compiler kiểm tra kiểu của biểu thức và yêu cầu kiểu phù hợp với nơi sử dụng.

Ví dụ sai:

~~~java
public class Main {
    public static void main(String[] args) {
        int quantity = "five";
    }
}
~~~

`"five"` có kiểu `String`, trong khi `quantity` có kiểu `int`.

Có hai cách sửa tùy ý định:

~~~java
int quantity = 5;
~~~

Hoặc:

~~~java
String quantity = "five";
~~~

Không nên ép kiểu chỉ để làm mất thông báo lỗi. Chỉ dùng cast khi phép chuyển đổi có ý nghĩa và hợp lệ. Ví dụ, cast từ `Object` sang một kiểu cụ thể có thể gây `ClassCastException` khi chạy nếu đối tượng thực tế không thuộc kiểu đó.

### 3.4. Sai chữ ký hoặc số lượng tham số phương thức

Compiler báo các thông điệp như `method ... cannot be applied to given types` khi không tìm được overload phù hợp với số lượng, thứ tự hoặc kiểu đối số.

Ví dụ:

~~~java
public class Main {
    static void greet(String name, int times) {
        System.out.println(name + " " + times);
    }

    public static void main(String[] args) {
        greet("Lan");
    }
}
~~~

Phương thức cần hai tham số nhưng lời gọi chỉ truyền một. Sửa bằng cách truyền đủ đối số:

~~~java
greet("Lan", 2);
~~~

Khi gọi phương thức, kiểm tra:

- Tên phương thức và lớp chứa phương thức.
- Số lượng tham số.
- Thứ tự và kiểu của từng đối số.
- Phương thức có phải `static` hay cần một đối tượng để gọi.
- Quyền truy cập và generic type nếu có overload.

Không thể tự động truyền `null` cho mọi kiểu primitive. Ví dụ `int` không nhận `null`; `Integer` là kiểu tham chiếu và có thể nhận `null`, nhưng cần xử lý khả năng null khi sử dụng.

### 3.5. Lỗi truy cập — `has private access` hoặc `... is not public`

Một thành viên có thể tồn tại nhưng không thể được truy cập từ vị trí gọi vì quy tắc access modifier.

Ví dụ:

~~~java
class Account {
    private int balance = 100;
}

public class Main {
    public static void main(String[] args) {
        Account account = new Account();
        System.out.println(account.balance);
    }
}
~~~

`balance` là `private`, nên lớp `Main` không thể truy cập trực tiếp. Có thể cung cấp phương thức công khai để đọc giá trị:

~~~java
class Account {
    private int balance = 100;

    public int getBalance() {
        return balance;
    }
}

public class Main {
    public static void main(String[] args) {
        Account account = new Account();
        System.out.println(account.getBalance());
    }
}
~~~

Stdout:

~~~text
100
~~~

Khi lỗi liên quan đến access modifier, kiểm tra phạm vi `private`, package-private, `protected`, `public`, quan hệ package và quan hệ kế thừa. Trong ứng dụng modular, còn phải kiểm tra module có `exports` package cần truy cập hay không.

### 3.6. Lỗi gọi thành viên instance từ ngữ cảnh static

Phương thức `main` truyền thống là `static`, nên không có `this` và không thể truy cập trực tiếp thành viên instance nếu chưa có đối tượng.

Ví dụ sai:

~~~java
public class Main {
    private String name = "Java";

    public static void main(String[] args) {
        System.out.println(name);
    }
}
~~~

`name` thuộc một đối tượng `Main`, còn `main` thuộc lớp. Tạo đối tượng rồi truy cập thành viên:

~~~java
public class Main {
    private String name = "Java";

    public static void main(String[] args) {
        Main app = new Main();
        System.out.println(app.name);
    }
}
~~~

Hoặc nếu dữ liệu thực sự dùng chung ở cấp lớp, cân nhắc khai báo `static`. Không chuyển mọi trường thành `static` chỉ để làm compiler im lặng; hãy chọn phạm vi trạng thái theo mô hình đối tượng.

### 3.7. Lỗi checked exception chưa được xử lý

Một số exception là checked exception. Phương thức có thể ném checked exception phải khai báo `throws` hoặc xử lý bằng `try-catch` theo quy tắc của Java.

Ví dụ sai:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class Main {
    public static void main(String[] args) {
        String text = Files.readString(Path.of("data.txt"));
        System.out.println(text);
    }
}
~~~

`Files.readString` có thể ném `IOException`. Sửa bằng cách xử lý ngoại lệ:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class Main {
    public static void main(String[] args) throws IOException {
        String text = Files.readString(Path.of("data.txt"));
        System.out.println(text);
    }
}
~~~

Hoặc dùng `try-catch` nếu ứng dụng cần xử lý tại chỗ. Khai báo `throws` không làm cho lỗi I/O biến mất; nó chuyển trách nhiệm xử lý cho caller. Chọn cách xử lý dựa trên mục tiêu của ứng dụng.

### 3.8. Lỗi tên tệp và tên public class

Một tệp nguồn chỉ có thể có một public top-level class theo tên tệp tương ứng. Ví dụ, nếu khai báo:

~~~java
public class Customer {
}
~~~

thì tệp phải có tên `Customer.java`. Nếu lớp public tên `Customer` nhưng tệp là `Main.java`, compiler báo lỗi tên tệp không phù hợp.

Hãy kiểm tra:

- Tên tệp và tên public class khớp nhau, bao gồm chữ hoa/chữ thường trên hệ thống phân biệt hoa thường.
- Mỗi public top-level class nằm trong tệp đúng tên.
- Package declaration phù hợp với cấu trúc dự án và cách build.
- Không có hai lớp cùng tên đầy đủ trong cùng một lần biên dịch.

### 3.9. Lỗi package và import

Thông báo `package ... does not exist` thường cho biết compiler không tìm thấy package hoặc dependency cần thiết trong source path, classpath hay module path.

Ví dụ, mã có:

~~~java
import com.example.util.Texts;
~~~

nhưng thư mục chứa `Texts.class` hoặc `Texts.java` không nằm trong đường dẫn compiler đang tìm kiếm.

Cách xử lý:

- Kiểm tra `package` ở đầu tệp nguồn.
- Đảm bảo cấu trúc thư mục phản ánh tên package.
- Thêm thư mục gốc chứa package vào classpath/source path.
- Kiểm tra JAR phụ thuộc đã được thêm vào classpath chưa.
- Nếu dùng module, kiểm tra module path và khai báo `requires`.

Import không tải thư viện từ Internet. Nó chỉ giúp mã nguồn dùng tên kiểu ngắn hơn; compiler vẫn cần tìm được định nghĩa lớp ở một vị trí đã cấu hình.

### 3.10. Lỗi generic và type inference

Generic giúp compiler kiểm tra kiểu phần tử của collection và API tổng quát. Một khai báo kiểu không phù hợp có thể gây lỗi `incompatible types`, `no suitable method found` hoặc lỗi inference.

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        names.add(10);
    }
}
~~~

`List<String>` chỉ nhận giá trị `String`, vì vậy `names.add(10)` không hợp lệ.

Sửa bằng cách thêm chuỗi:

~~~java
names.add("10");
~~~

Nếu cần lưu nhiều kiểu dữ liệu, hãy chọn một kiểu chung phù hợp hoặc mô hình lớp/interface rõ ràng. Tránh dùng raw type như `List` để né kiểm tra kiểu; điều đó làm mất một phần lợi ích an toàn của generic và thường dẫn đến warning.

### 3.11. Lỗi lambda và method reference

Lambda cần một target type phù hợp, thường là functional interface. Nếu compiler không suy luận được kiểu hoặc chữ ký không khớp, nó sẽ báo lỗi về kiểu, overload hoặc biểu thức lambda.

Ví dụ hợp lệ:

~~~java
import java.util.function.Predicate;

public class Main {
    public static void main(String[] args) {
        Predicate<String> nonEmpty = text -> !text.isEmpty();
        System.out.println(nonEmpty.test("Java"));
    }
}
~~~

Stdout:

~~~text
true
~~~

Nếu biểu thức lambda không có target type rõ ràng, khai báo biến bằng functional interface cụ thể hoặc cung cấp kiểu tham số khi cần. Khi dùng method reference, kiểm tra số lượng và kiểu tham số mà phương thức tham chiếu nhận.

### 3.12. Lỗi trùng lặp khai báo

Compiler không cho phép khai báo hai biến cục bộ cùng tên trong một scope, hai phương thức có cùng signature trong cùng lớp, hoặc hai lớp cùng tên đầy đủ trong cùng tập nguồn.

Ví dụ:

~~~java
public class Main {
    public static void main(String[] args) {
        int count = 1;
        int count = 2;
        System.out.println(count);
    }
}
~~~

Sửa bằng cách chỉ khai báo một lần rồi gán lại nếu cần:

~~~java
int count = 1;
count = 2;
~~~

Với phương thức, Java không phân biệt overload chỉ dựa vào kiểu trả về. Hai phương thức có cùng tên và cùng danh sách kiểu tham số không thể được phân biệt chỉ vì một phương thức trả về `int`, phương thức còn lại trả về `String`.

## 4. Lỗi do phiên bản Java và API

Mã nguồn có thể hợp lệ trên JDK mới nhưng không biên dịch khi dự án nhắm đến phiên bản Java cũ hơn. Nguyên nhân thường là dùng cú pháp ngôn ngữ hoặc API chưa có trong phiên bản mục tiêu.

Ví dụ, nếu dự án phải chạy trên Java 17, hãy biên dịch bằng `--release 17`:

~~~text
javac --release 17 -d out src/Main.java
~~~

`--release` cấu hình mức ngôn ngữ, phiên bản class file và tập API nền tảng công khai tương ứng. Đây là cách phù hợp để kiểm tra tính tương thích với một phiên bản Java mục tiêu khi dùng JDK mới hơn.

Không nên chỉ dùng `-source 17 -target 17` khi cần kiểm soát API nền tảng mục tiêu. Hai tùy chọn đó kiểm soát mức cú pháp và định dạng class file, nhưng không tự giới hạn API nền tảng theo cùng cách `--release` thực hiện.

Một số thông báo liên quan:

- `... is not supported in -source ...`: cú pháp không được hỗ trợ ở mức ngôn ngữ đã chọn.
- `cannot find symbol` cho API mới: API có thể chưa tồn tại trong release mục tiêu hoặc dependency chưa được tìm thấy.
- `invalid source release`: JDK compiler hiện tại không hỗ trợ mức source/release được yêu cầu.
- `class file has wrong version`: compiler đang đọc class file được tạo bởi phiên bản mới hơn mức nó hỗ trợ.

Kiểm tra compiler đang dùng:

~~~text
java --version
javac --version
~~~

Nếu IDE dùng một JDK khác terminal, kiểm tra cấu hình Project SDK, Java compiler và build tool. Phiên bản hiển thị trong terminal không đảm bảo IDE dùng cùng compiler.

## 5. Lỗi classpath, module path và dependency khi biên dịch

Compiler phải tìm được các lớp mà mã nguồn tham chiếu. Với ứng dụng classpath, dùng `-cp` hoặc `--class-path`:

~~~text
javac -cp "lib/*" -d out src/Main.java
~~~

Trên Windows, dấu phân cách giữa nhiều mục classpath là `;`; trên macOS/Linux là `:`. Dấu `*` trong ví dụ đưa các JAR trong thư mục `lib` vào classpath.

Với ứng dụng modular, dùng module path:

~~~text
javac --module-path mods -d out src/module-info.java src/com/example/Main.java
~~~

Cú pháp đầy đủ phụ thuộc cấu trúc module và vị trí source file. Các module được dùng phải có trong module path và module descriptor phải khai báo quan hệ cần thiết, chẳng hạn `requires`. Package cần được truy cập từ module khác phải được export phù hợp.

Phân biệt các tình huống:

| Diagnostic | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| `package ... does not exist` | Thiếu dependency hoặc sai classpath/source path | JAR, thư mục package, `-cp` |
| `module not found` | Module không có trên module path | `--module-path`, tên module |
| `module ... does not read ...` | Thiếu quan hệ readability | `requires` hoặc cấu hình module |
| `package ... is not visible` | Package chưa export hoặc không được đọc | `exports`, module descriptor |
| `cannot access ...` | Class file không tương thích, thiếu dependency hoặc quyền truy cập | Phiên bản JDK, classpath, module |

Một dependency có thể tồn tại lúc chạy nhưng lại thiếu lúc biên dịch, hoặc ngược lại. Cần bảo đảm classpath/module path dùng cho `javac` và runtime phù hợp với cùng bộ dependency của ứng dụng.

## 6. Lỗi annotation processing

Annotation processor là thành phần chạy trong quá trình biên dịch để đọc annotation và có thể sinh mã nguồn hoặc tài nguyên bổ sung. Các thư viện như MapStruct hoặc một số công cụ sinh mã có thể phụ thuộc vào annotation processing.

Triệu chứng thường gặp:

- Compiler báo không tìm thấy kiểu hoặc phương thức được kỳ vọng do code generation chưa chạy.
- Thông báo không tìm thấy annotation processor.
- Processor phát ra diagnostic `error` vì cấu hình annotation hoặc đầu vào không hợp lệ.
- Mã được sinh ra không có trong thư mục output/source output.

Một số tùy chọn liên quan:

- `-processorpath`: chỉ định nơi tìm annotation processor.
- `-processor`: chỉ định processor cần chạy.
- `-proc:none`: tắt annotation processing.
- `-s`: chỉ định thư mục chứa source file được sinh ra.
- `-Akey=value`: truyền tùy chọn cho annotation processor.

Ví dụ tắt annotation processing để kiểm tra một lỗi độc lập với processor:

~~~text
javac -proc:none -d out src/Main.java
~~~

Chỉ dùng `-proc:none` để khoanh vùng vấn đề khi biết dự án không cần code generation cho lần biên dịch đó. Nếu ứng dụng phụ thuộc mã được sinh tự động, tắt processor có thể tạo thêm lỗi `cannot find symbol` vì các lớp sinh ra không tồn tại.

## 7. Warning và cách kiểm soát chất lượng biên dịch

Warning cho biết compiler phát hiện cấu trúc đáng chú ý nhưng vẫn có thể biên dịch. Các warning phổ biến gồm:

- Dùng API đã deprecated.
- Dùng raw type hoặc unchecked conversion.
- Có phép cast dư thừa.
- Có vấn đề về serializable class.
- Có tài nguyên hoặc cấu trúc mã đáng kiểm tra.

Bật nhóm warning bằng `-Xlint`:

~~~text
javac -Xlint:all -d out src/Main.java
~~~

Có thể bật một nhóm cụ thể, ví dụ:

~~~text
javac -Xlint:deprecation -d out src/Main.java
javac -Xlint:unchecked -d out src/Main.java
~~~

Dùng `-Werror` để biến warning thành lỗi:

~~~text
javac -Xlint:all -Werror -d out src/Main.java
~~~

`-Werror` hữu ích trong CI để giữ chất lượng mã nhất quán, nhưng chỉ nên bật sau khi dự án đã xử lý các warning hiện có. Nếu bật ngay trên một codebase có nhiều warning cũ, build có thể thất bại dù thay đổi mới không tạo thêm lỗi.

Không nên tắt warning một cách rộng rãi chỉ để build xanh. Nếu cần suppression, dùng annotation `@SuppressWarnings` ở phạm vi nhỏ nhất có thể và ghi rõ lý do khi warning có rủi ro thực tế.

## 8. Ví dụ quy trình biên dịch đầy đủ với Java 17+

Tạo cấu trúc thư mục:

~~~text
project/
  src/
    Main.java
  out/
~~~

Nội dung `src/Main.java`:

~~~java
public class Main {
    public static void main(String[] args) {
        int first = 10;
        int second = 20;
        System.out.println("Total: " + (first + second));
    }
}
~~~

Biên dịch:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/Main.java
~~~

Nếu compiler không báo lỗi, chạy:

~~~text
java -cp out Main
~~~

Stdout:

~~~text
Total: 30
~~~

Giải thích:

- `--release 17` kiểm tra mã nguồn theo Java 17.
- `-encoding UTF-8` chỉ định encoding của mã nguồn.
- `-Xlint:all` bật nhóm warning.
- `-d out` đặt nơi lưu class file.
- `-cp out` chỉ định thư mục tìm lớp khi chạy.

Trong PowerShell hoặc Command Prompt, ví dụ này dùng đường dẫn tương đối và không cần dấu phân cách classpath nhiều mục. Khi thêm thư viện, hãy dùng đúng ký tự phân cách theo hệ điều hành.

## 9. Quy trình xử lý lỗi biên dịch có hệ thống

Khi `javac` thất bại, làm theo quy trình:

1. **Xác nhận compiler:** chạy `javac --version` và kiểm tra đường dẫn executable.
2. **Tái hiện bằng lệnh rõ ràng:** ghi lại đầy đủ command line, working directory, classpath/module path và phiên bản mục tiêu.
3. **Đọc diagnostic đầu tiên có ý nghĩa:** xác định tệp, dòng, symbol, kiểu hoặc package được nêu.
4. **Mở rộng ngữ cảnh:** đọc dòng lỗi cùng các khai báo, import và method signature liên quan.
5. **Kiểm tra nguyên nhân gốc:** cú pháp, scope, type, access, dependency, module hoặc annotation processing.
6. **Sửa một nhóm nguyên nhân liên quan:** tránh thay đổi nhiều thứ không liên quan cùng lúc.
7. **Biên dịch lại:** xác nhận lỗi đã biến mất và xem diagnostic mới.
8. **Chạy kiểm thử phù hợp:** biên dịch thành công không chứng minh logic đúng; chạy chương trình và test để kiểm tra hành vi.
9. **Ghi lại cấu hình build:** lưu JDK/release, dependency và các tùy chọn cần thiết trong build script để người khác tái hiện.

Nếu build tool như Maven hoặc Gradle báo lỗi, hãy tìm phần đầu tiên có `Compilation failure`, `Compilation error` hoặc diagnostic từ `javac`. Các lỗi tải dependency, cấu hình plugin hay lỗi test có thể xảy ra ở giai đoạn khác và cần xử lý riêng.

## 10. Một số tùy chọn `javac` hữu ích khi chẩn đoán

| Tùy chọn | Công dụng |
|---|---|
| `-Xdiags:verbose` | Hiển thị diagnostic chi tiết hơn trong các trường hợp compiler hỗ trợ |
| `-Xlint:all` | Bật nhiều nhóm warning |
| `-Werror` | Xem warning là lỗi biên dịch |
| `--release 17` | Biên dịch theo phiên bản Java mục tiêu |
| `-encoding UTF-8` | Chỉ định encoding mã nguồn |
| `-d out` | Chỉ định thư mục class file đầu ra |
| `-cp` / `--class-path` | Chỉ định nơi tìm lớp và dependency |
| `--module-path` | Chỉ định nơi tìm module |
| `-sourcepath` | Chỉ định nơi tìm thêm mã nguồn được tham chiếu |
| `-proc:none` | Tắt annotation processing |
| `-verbose` | In thêm thông tin về hoạt động compiler |

Ví dụ bật diagnostic chi tiết và warning:

~~~text
javac -Xdiags:verbose -Xlint:all -d out src/Main.java
~~~

Không phải tùy chọn nào cũng phù hợp với mọi phiên bản JDK. Nếu compiler báo tùy chọn không hợp lệ, xem trợ giúp `javac --help` và tài liệu của đúng JDK đang cài. Các tùy chọn bắt đầu bằng `-X` có thể là tùy chọn nâng cao phụ thuộc phiên bản.

## 11. Lỗi thường gặp và cách khoanh vùng nhanh

### `';' expected` hoặc `')' expected`

**Nguyên nhân:** thiếu dấu kết thúc câu lệnh hoặc dấu ngoặc đóng; đôi khi lỗi nằm ở dòng phía trước.

**Xử lý:** kiểm tra câu lệnh hiện tại và cặp ngoặc của khối gần nhất. Biên dịch lại sau khi sửa một lỗi cú pháp gốc.

### `cannot find symbol`

**Nguyên nhân:** sai tên, chưa khai báo, sai scope, thiếu import hoặc thiếu dependency.

**Xử lý:** kiểm tra phần `symbol` và `location`, sau đó xác nhận khai báo và đường dẫn tìm lớp.

### `incompatible types`

**Nguyên nhân:** kiểu biểu thức không tương thích với kiểu biến, tham số hoặc giá trị trả về.

**Xử lý:** sửa kiểu ở nguồn hoặc chuyển đổi có chủ đích. Không cast tùy tiện để che lỗi.

### `method ... cannot be applied to given types`

**Nguyên nhân:** sai số lượng, thứ tự hoặc kiểu đối số; không có overload phù hợp.

**Xử lý:** so sánh chữ ký phương thức với lời gọi, kiểm tra generic và kiểu suy luận.

### `package ... does not exist`

**Nguyên nhân:** thiếu thư viện, sai classpath/source path hoặc package không được module cung cấp.

**Xử lý:** xác nhận dependency đã có trong compile classpath/module path; import không tự tải thư viện.

### `class X is public, should be declared in a file named X.java`

**Nguyên nhân:** tên tệp không khớp tên public top-level class.

**Xử lý:** đổi tên tệp hoặc lớp để chúng khớp nhau.

### `unreported exception ...; must be caught or declared to be thrown`

**Nguyên nhân:** checked exception chưa được xử lý hoặc khai báo.

**Xử lý:** thêm `try-catch` phù hợp hoặc khai báo `throws` ở phương thức và để caller xử lý.

### `invalid source release` hoặc cú pháp không được hỗ trợ

**Nguyên nhân:** JDK compiler quá cũ hoặc mức source/release không phù hợp.

**Xử lý:** dùng JDK hỗ trợ phiên bản mục tiêu, hoặc hạ `--release` nếu dự án cho phép.

### `warning: ...` nhưng build vẫn thất bại

**Nguyên nhân:** build bật `-Werror` hoặc cấu hình plugin coi warning là lỗi.

**Xử lý:** xác định warning nào đang bị nâng thành lỗi. Sửa nguyên nhân hoặc điều chỉnh chính sách warning có chủ đích, không xóa warning một cách mù quáng.

## 12. Checklist trước khi kết luận lỗi đã được sửa

- [ ] Dùng đúng JDK và `javac` mà dự án yêu cầu.
- [ ] Tên tệp, tên public class và package khớp nhau.
- [ ] Không còn lỗi cú pháp hoặc dấu ngoặc thiếu.
- [ ] Biến, lớp, phương thức và trường được khai báo trong đúng scope.
- [ ] Kiểu đối số, kiểu trả về và generic phù hợp.
- [ ] Quyền truy cập và quan hệ kế thừa đúng.
- [ ] Checked exception được xử lý hoặc khai báo.
- [ ] Classpath/module path chứa dependency cần thiết.
- [ ] Annotation processor được cấu hình nếu dự án cần code generation.
- [ ] `--release` khớp phiên bản Java triển khai.
- [ ] Warning được xem xét theo chính sách build.
- [ ] Lệnh biên dịch chạy thành công và tạo class file ở thư mục mong muốn.
- [ ] Chương trình hoặc test chạy thành công sau khi biên dịch.

Lỗi biên dịch là phản hồi của compiler về những quy tắc mà mã nguồn chưa đáp ứng. Đọc đúng diagnostic, phân biệt lỗi cú pháp với lỗi kiểu và lỗi dependency, rồi tái hiện bằng một lệnh `javac` rõ ràng sẽ giúp bạn tìm đúng nguyên nhân. Khi biên dịch thành công, tiếp tục chạy test để xác nhận hành vi của chương trình.
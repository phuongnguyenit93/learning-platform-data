# Phân biệt lỗi biên dịch, liên kết và lỗi khi chạy trong Java 17

Khi thực hành Java 17, một chương trình có thể thất bại ngay lúc biên dịch, khi JVM nạp và liên kết các lớp, hoặc trong lúc chương trình thực thi. Cả ba trường hợp đôi khi đều được gọi chung là “lỗi Java”, nhưng **nguyên nhân, dấu hiệu nhận biết và cách sửa khác nhau**.

Bài này giúp bạn xác định lỗi xảy ra ở giai đoạn nào, đọc thông báo lỗi đúng cách và chọn bước xử lý phù hợp trong môi trường Java 17.

## 1. Ba giai đoạn cần phân biệt

Xét luồng cơ bản từ mã nguồn đến chương trình đang chạy:

```text
Mã nguồn Java (.java)
        |
        | javac: phân tích cú pháp, kiểm tra kiểu và quy tắc ngôn ngữ
        v
Bytecode (.class)              <-- Lỗi biên dịch: không tạo được bytecode hợp lệ
        |
        | java khởi động JVM; nạp và liên kết các lớp cần dùng
        |   - verification: kiểm tra tính hợp lệ của bytecode
        |   - preparation: chuẩn bị vùng dữ liệu tĩnh theo đặc tả
        |   - resolution: giải quyết tham chiếu biểu tượng đến lớp/phương thức/trường
        v
Các lớp sẵn sàng sử dụng    <-- Lỗi liên kết: bytecode/thành phần runtime không tương thích
        |
        | khởi tạo lớp khi cần, thực thi main và các phương thức
        v
Chương trình đang chạy        <-- Lỗi khi chạy: thao tác, dữ liệu, tài nguyên, môi trường...
```

**Lưu ý quan trọng:** sơ đồ là mô hình để học, không phải lịch trình cứng. JVM có thể **nạp lớp và giải quyết tham chiếu khi chương trình đã bắt đầu chạy**. Vì thế một `LinkageError` có thể chỉ xuất hiện khi gọi tới một phương thức nhất định, dù `main` đã chạy trước đó. Hãy phân loại theo **bản chất nguyên nhân**, không chỉ theo thời điểm nhìn thấy lỗi.

| Tiêu chí | Lỗi biên dịch (*compile-time error*) | Lỗi liên kết (*linkage error*) | Lỗi khi chạy (*runtime failure*) |
| --- | --- | --- | --- |
| Giai đoạn phát hiện điển hình | `javac` xử lý mã nguồn | JVM nạp, kiểm tra, chuẩn bị hoặc giải quyết tham chiếu của lớp | Mã đã bắt đầu thực thi, gặp điều kiện không hợp lệ hoặc sự cố |
| Dấu hiệu thường gặp | `error: ...`, không biên dịch thành công | `java.lang.NoSuchMethodError`, `NoClassDefFoundError`, `UnsupportedClassVersionError` | `ArithmeticException`, `NullPointerException`, `IOException`, `OutOfMemoryError`... |
| Nguyên nhân thường gặp | Sai cú pháp, kiểu dữ liệu, ký hiệu, truy cập hoặc ràng buộc lúc biên dịch | Các tệp `.class`, thư viện hoặc runtime không khớp với nhau | Dữ liệu đầu vào, logic thực thi, trạng thái đối tượng, tài nguyên hoặc dịch vụ bên ngoài |
| Hướng xử lý đầu tiên | Sửa mã nguồn hoặc cấu hình compiler/dependency biên dịch | Kiểm tra phiên bản runtime, classpath/module path, bản JAR và tính đồng bộ của bản build | Đọc stack trace, nguyên nhân gốc, giá trị đầu vào và điều kiện khi lỗi xảy ra |

Trong Java, **“liên kết”** ở đây chủ yếu nói tới *JVM linking* theo Java Virtual Machine Specification. Không nên hiểu máy móc như bước liên kết tệp đối tượng bằng linker của C/C++.

## 2. Lỗi biên dịch: `javac` từ chối mã nguồn

Trình biên dịch `javac` kiểm tra cú pháp, kiểu dữ liệu, tên biến/phương thức/lớp, quyền truy cập, quy tắc ngoại lệ kiểm tra (*checked exceptions*) và những ràng buộc khác của ngôn ngữ Java. Khi có lỗi biên dịch, lệnh `javac` trả trạng thái thất bại và không tạo ra **bản class mới hợp lệ cho phần mã đó**.

### Ví dụ 1: Sai kiểu dữ liệu

Tạo tệp `CompileErrorDemo.java`:

```java
public class CompileErrorDemo {
    public static void main(String[] args) {
        int quantity = "ten";
        System.out.println(quantity);
    }
}
```

Biên dịch:

```bash
javac CompileErrorDemo.java
```

Thông báo đặc trưng:

```text
CompileErrorDemo.java:3: error: incompatible types: String cannot be converted to int
        int quantity = "ten";
                       ^
```

Compiler biết rõ kiểu `String` không thể gán trực tiếp cho biến `int`. Thay bằng `int quantity = 10;` hoặc chủ động chuyển đổi chuỗi theo quy tắc thích hợp:

```java
int quantity = Integer.parseInt("10");
```

Phương án `parseInt` **biên dịch được**, nhưng vẫn có thể phát sinh `NumberFormatException` khi chạy nếu chuỗi không phải một số nguyên hợp lệ. Đây là ví dụ cho thấy **hết lỗi biên dịch không bảo đảm không có lỗi khi chạy**.

### Ví dụ 2: Không tìm thấy ký hiệu

```java
public class MissingSymbolDemo {
    public static void main(String[] args) {
        System.out.println(result);
    }
}
```

`javac` có thể báo:

```text
error: cannot find symbol
    System.out.println(result);
                       ^
  symbol:   variable result
```

Biến `result` chưa được khai báo trong phạm vi nhìn thấy được. Trong dự án thực tế, thông báo `cannot find symbol` còn có thể do tên phương thức sai, import sai hoặc **dependency không có trên compile classpath**.

### Ví dụ 3: Ngoại lệ kiểm tra chưa được xử lý

```java
import java.nio.file.Files;
import java.nio.file.Path;

public class CheckedExceptionDemo {
    public static void main(String[] args) {
        String data = Files.readString(Path.of("settings.txt"));
        System.out.println(data);
    }
}
```

`Files.readString` có thể ném `IOException`. Vì đây là checked exception, mã trên cần xử lý bằng `try/catch` hoặc khai báo `throws IOException`. Nếu không, `javac` báo lỗi biên dịch kiểu `unreported exception IOException; must be caught or declared to be thrown`.

Ví dụ biên dịch được:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CheckedExceptionDemo {
    public static void main(String[] args) throws IOException {
        String data = Files.readString(Path.of("settings.txt"));
        System.out.println(data);
    }
}
```

Khai báo `throws` **không bảo đảm tệp tồn tại**. Nếu `settings.txt` không có hoặc không đọc được, ngoại lệ vẫn có thể xảy ra khi chạy.

### Nhận diện nhanh lỗi biên dịch

- Lệnh thất bại là `javac ...`, hoặc bước compile của Maven/Gradle/IDE.
- Thông báo thường chỉ **tên tệp nguồn, số dòng, vị trí và mô tả lỗi**.
- Việc cần làm là sửa mã nguồn, cấu hình source/release hoặc compile classpath.
- Khi đã có tệp `.class` từ lần build trước, **đừng nhầm tệp cũ với thành công của lần biên dịch mới**. Cần dựa vào trạng thái của lệnh build hiện tại.

## 3. Lỗi liên kết: JVM không thể sử dụng các lớp như bytecode mong đợi

Sau khi `javac` tạo bytecode, JVM phải nạp các lớp, kiểm tra định dạng và tính hợp lệ của bytecode, chuẩn bị dữ liệu lớp và giải quyết các tham chiếu đến lớp, phương thức, trường. Một số lỗi ở các bước này thuộc họ **`java.lang.LinkageError`**.

Điểm thường gây nhầm là: **mỗi tệp Java có thể đã biên dịch thành công**, nhưng các tệp `.class`/JAR được ghép với nhau ở môi trường chạy lại không đồng bộ.

### Ví dụ 4: `NoSuchMethodError` khi thay thư viện mà không biên dịch lại chương trình

Trước tiên, tạo hai tệp trong cùng thư mục.

Tệp `Greeter.java`, bản đầu:

```java
public class Greeter {
    public static String say() {
        return "Hello";
    }
}
```

Tệp `App.java`:

```java
public class App {
    public static void main(String[] args) {
        System.out.println(Greeter.say());
    }
}
```

Biên dịch và chạy:

```bash
javac Greeter.java App.java
java App
```

Kết quả:

```text
Hello
```

Giả sử sau đó người khác thay đổi **chỉ `Greeter.java`** thành:

```java
public class Greeter {
    public static String greet() {
        return "Hi";
    }
}
```

Lần này chỉ biên dịch lớp đã thay đổi, **giữ nguyên `App.class` cũ**:

```bash
javac Greeter.java
java App
```

Khi chạy, JVM có thể báo:

```text
Exception in thread "main" java.lang.NoSuchMethodError:
    'java.lang.String Greeter.say()'
    at App.main(App.java:3)
```

Điều gì đã xảy ra?

1. `App.class` được biên dịch khi `Greeter` **còn** phương thức tĩnh `say()`.
2. `Greeter.class` mới đã bỏ phương thức đó và thay bằng `greet()`.
3. `App.class` vẫn chứa tham chiếu tới chữ ký `Greeter.say(): String`.
4. Khi JVM giải quyết lời gọi, phương thức tương ứng không còn tồn tại nên ném `NoSuchMethodError`.

Đây là **lỗi liên kết ở runtime**, dù từng lệnh `javac` đã chạy thành công. Nếu ngay từ đầu biên dịch lại cả hai tệp nguồn sau khi sửa API, `javac` sẽ phát hiện lời gọi `Greeter.say()` không còn hợp lệ và báo **lỗi biên dịch**. Chính sự **không đồng bộ giữa các bản class đã biên dịch** làm khác biệt hai tình huống.

**Cách xử lý:** đồng bộ phiên bản thư viện với phiên bản chương trình, sửa lời gọi thành `greet()` rồi build lại phần phụ thuộc và ứng dụng. Trong dự án có nhiều JAR, kiểm tra lớp nào thực tế được class loader nạp và có vô tình dùng bản JAR cũ hay không.

### Một số lỗi liên kết thường gặp

| Loại lỗi | Ý nghĩa điển hình | Kiểm tra đầu tiên |
| --- | --- | --- |
| `NoSuchMethodError` | Bytecode gọi phương thức/chữ ký mà lớp runtime không có | JAR phiên bản nào đang được nạp? Caller và thư viện có được build đồng bộ? |
| `NoSuchFieldError` | Bytecode tham chiếu trường không còn tồn tại trong lớp runtime | Phiên bản lớp, tên/kiểu trường, dependency bị thay đổi |
| `NoClassDefFoundError` | JVM cần một định nghĩa lớp nhưng không thể tìm/nạp/hoàn tất sử dụng nó theo yêu cầu; cũng có thể xảy ra sau lỗi khởi tạo lớp | Dependency runtime, classpath/module path; đặc biệt xem thông báo và `Caused by` |
| `IncompatibleClassChangeError` | Hình dạng nhị phân của lớp/phương thức đã thay đổi theo cách không tương thích | Phần API đã đổi giữa hai bản JAR hoặc class |
| `IllegalAccessError` | Bytecode cố truy cập thành phần không còn được phép truy cập ở runtime | Thay đổi mức truy cập, quan hệ lớp, module exports; version không khớp |
| `UnsupportedClassVersionError` | Runtime không hỗ trợ phiên bản class file được nạp | `java -version` và phiên bản bytecode khi build |
| `ClassFormatError` hoặc `VerifyError` | Tệp class không hợp lệ về định dạng hoặc vi phạm quy tắc xác minh bytecode | Bytecode được tạo/chỉnh sửa bởi công cụ nào, có tương thích runtime không |

Các kiểu lỗi trên kế thừa trực tiếp hoặc gián tiếp `LinkageError`. Danh sách này là những ví dụ hữu ích, không phải toàn bộ các lớp con có thể gặp.

### Ví dụ 5: Java 17 biên dịch được, runtime cũ không đọc được

Giả sử ứng dụng được biên dịch thành class file của **Java 17**, nhưng môi trường triển khai lại chạy bằng JVM Java 11.

- Class file Java 17 có **major version 61**.
- JVM Java 11 hỗ trợ class file tối đa tương ứng Java 11 (**major version 55**).
- Khi nạp class 61, JVM Java 11 không thể chấp nhận định dạng phiên bản đó và có thể ném `UnsupportedClassVersionError`.

Để kiểm tra môi trường:

```bash
java -version
javac -version
```

Để kiểm tra phiên bản class file:

```bash
javap -verbose App.class
```

Tìm dòng `major version: 61` nếu file được biên dịch cho Java 17. Cách xử lý là chạy bằng runtime hỗ trợ phiên bản class file, hoặc biên dịch lại hướng tới một phiên bản đích được hỗ trợ **nếu mã nguồn và API cho phép**. Không có cách chữa đúng bằng cách chỉ đổi tên tệp `.class` hay sửa số phiên bản bằng tay.

### Phân biệt `NoClassDefFoundError` và `ClassNotFoundException`

Hai tên này đều gợi ý “thiếu lớp”, nhưng ý nghĩa trong API Java khác nhau:

- **`NoClassDefFoundError`:** là một `LinkageError`; thường xuất hiện khi JVM thực thi bytecode cần lớp mà trước đó được tham chiếu hợp lệ nhưng hiện không định nghĩa được trong runtime. Nó cũng có thể xuất hiện với thông báo `Could not initialize class ...` khi lớp đã thất bại trong quá trình khởi tạo trước đó.
- **`ClassNotFoundException`:** là một **checked exception**, thường được báo khi chương trình chủ động yêu cầu tìm lớp theo tên, chẳng hạn `Class.forName("com.example.Missing")`, mà class loader không tìm được. Nó **không** là lớp con của `LinkageError`.

Ví dụ:

```java
public class LoadByNameDemo {
    public static void main(String[] args) throws ClassNotFoundException {
        Class.forName("example.DoesNotExist");
    }
}
```

Đoạn mã trên biên dịch được nhưng ném `ClassNotFoundException` khi chạy nếu tên lớp không tồn tại. Vì vậy, đừng dựa duy nhất vào cụm chữ “ClassNotFound” để kết luận ngay rằng đã gặp `LinkageError`.

### Khởi tạo lớp không đồng nghĩa với liên kết lớp

Theo mô hình JVM, **initialization** (thực thi bộ khởi tạo tĩnh, gán giá trị tĩnh có tính toán...) là bước khác với **linking**. Nếu một static initializer ném ngoại lệ, bạn có thể thấy `ExceptionInInitializerError`; những lần dùng lớp tiếp theo có thể xuất hiện `NoClassDefFoundError: Could not initialize class ...`.

Ví dụ:

```java
public class InitializationDemo {
    static final int VALUE = Integer.parseInt("invalid");

    public static void main(String[] args) {
        System.out.println(VALUE);
    }
}
```

Đoạn mã **biên dịch hợp lệ**. Khi JVM khởi tạo lớp, biểu thức `Integer.parseInt("invalid")` ném `NumberFormatException`, thường được bao trong `ExceptionInInitializerError`. Trong trường hợp này, sửa **dữ liệu và logic khởi tạo** mới giải quyết tận gốc, chứ không phải cứ thấy `Error` là đổi phiên bản JAR.

## 4. Lỗi khi chạy: chương trình đã thực thi nhưng gặp điều kiện không hợp lệ

Một chương trình có thể vượt qua mọi kiểm tra của compiler và nạp/liên kết những lớp cần thiết, rồi vẫn thất bại do **giá trị dữ liệu**, **trạng thái chương trình**, **logic xử lý** hoặc **hệ thống bên ngoài**.

### Ví dụ 6: Chia cho 0

Tạo tệp `RuntimeErrorDemo.java`:

```java
public class RuntimeErrorDemo {
    public static void main(String[] args) {
        int divisor = Integer.parseInt(args[0]);
        int result = 100 / divisor;
        System.out.println("Result = " + result);
    }
}
```

Biên dịch:

```bash
javac RuntimeErrorDemo.java
```

Chạy với đầu vào hợp lệ:

```bash
java RuntimeErrorDemo 5
```

```text
Result = 20
```

Chạy với mẫu số bằng 0:

```bash
java RuntimeErrorDemo 0
```

Thông báo điển hình:

```text
Exception in thread "main" java.lang.ArithmeticException: / by zero
    at RuntimeErrorDemo.main(RuntimeErrorDemo.java:4)
```

`javac` không thể suy ra trước giá trị đối số được người dùng truyền lúc chạy. `ArithmeticException` ở đây là **runtime exception**, không phải lỗi biên dịch hoặc lỗi liên kết.

Đoạn mã này còn có thể gặp:

- `ArrayIndexOutOfBoundsException` khi không truyền đối số `args[0]`.
- `NumberFormatException` khi truyền một giá trị như `abc`.
- Lỗi logic nếu bạn không kiểm tra giới hạn dữ liệu, dù chương trình đôi khi vẫn in ra kết quả.

Một phiên bản xử lý đầu vào rõ ràng hơn:

```java
public class SafeDivisionDemo {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Cach dung: java SafeDivisionDemo <so-nguyen-khac-0>");
            return;
        }

        try {
            int divisor = Integer.parseInt(args[0]);
            if (divisor == 0) {
                System.err.println("Mau so phai khac 0.");
                return;
            }
            System.out.println("Result = " + (100 / divisor));
        } catch (NumberFormatException e) {
            System.err.println("Doi so phai la so nguyen hop le.");
        }
    }
}
```

Đoạn mã kiểm soát những điều kiện đầu vào cụ thể. Nó không có nghĩa phải bắt mọi `RuntimeException` trong toàn bộ ứng dụng; trong dự án thực tế, lỗi cần được xử lý ở tầng có đủ thông tin để khắc phục, ghi log hoặc trả phản hồi phù hợp.

### Các lỗi khi chạy khác

| Triệu chứng | Tình huống thường gây ra | Hướng điều tra |
| --- | --- | --- |
| `NullPointerException` | Truy cập phương thức/trường qua tham chiếu `null` | Biến nào `null`, vì sao đường xử lý cho phép `null` |
| `IndexOutOfBoundsException` | Chỉ số nằm ngoài giới hạn danh sách/chuỗi/mảng | Giá trị index và kích thước dữ liệu |
| `ClassCastException` | Ép kiểu tham chiếu không hợp lệ tại runtime | Kiểu thực tế của đối tượng |
| `NumberFormatException` | Chuỗi không chuyển được thành số theo định dạng mong đợi | Dữ liệu đầu vào, kiểm tra và thông báo lỗi |
| `IOException` | Đọc/ghi tệp hoặc thao tác I/O thất bại | Đường dẫn, quyền, trạng thái tệp, nguồn dữ liệu |
| `OutOfMemoryError` | JVM không đáp ứng được yêu cầu cấp phát bộ nhớ | Mức dùng bộ nhớ, heap, dữ liệu giữ lại, cấu hình/runtime |

**Không phải mọi lỗi khi chạy đều là `RuntimeException`.** `IOException` là checked exception nhưng có thể thực sự được ném lúc chạy. `OutOfMemoryError` là `Error`. Ngoài ra còn có **lỗi logic** khiến chương trình cho kết quả sai mà không ném bất kỳ ngoại lệ nào.

## 5. Vì sao đã biên dịch thành công vẫn gặp lỗi liên kết hoặc lỗi khi chạy?

Ba loại kiểm tra nhìn vào các thông tin khác nhau:

- **Compiler** làm việc với mã nguồn và các định nghĩa nó nhìn thấy **trong lúc build**. Nó không biết chắc dữ liệu đầu vào tương lai, trạng thái mạng/tệp hay chính xác mọi JAR sẽ được triển khai.
- **JVM linking** làm việc với các định nghĩa lớp mà class loader thực sự nạp **trong môi trường chạy**. Nếu bản runtime khác bản build, những tham chiếu đã biên dịch có thể không còn hợp lệ.
- **Execution** làm việc với dữ liệu và trạng thái thay đổi theo thời gian. Những lỗi như chia cho 0 hay kết nối thất bại phụ thuộc hoàn cảnh khi chạy.

Ví dụ cùng là lời gọi `Greeter.say()` nhưng có thể gây lỗi khác nhau:

| Tình huống | Kết quả |
| --- | --- |
| `Greeter.java` hiện tại không có `say()`, bạn biên dịch `App.java` từ mã nguồn | Thường là lỗi biên dịch như `cannot find symbol`. |
| `App.class` cũ từng được biên dịch với `say()`, nhưng runtime dùng `Greeter.class` mới đã bỏ `say()` | `NoSuchMethodError` trong quá trình liên kết/giải quyết lời gọi. |
| `Greeter.say()` tồn tại, nhưng trong thân phương thức có phép tính gây `ArithmeticException` | Lỗi khi chạy trong logic của phương thức. |

Đây là lý do tên thông báo và các dòng `Caused by` quan trọng hơn câu khẳng định chung “ứng dụng không chạy được”.

## 6. Quy trình chẩn đoán khi thực hành Java 17

### Bước 1: Xác định lệnh thực sự thất bại

- Nếu lệnh `javac` hoặc bước **compile** trong build thất bại, bắt đầu từ thông báo compiler.
- Nếu đã chạy `java` và thấy `NoSuchMethodError`, `NoClassDefFoundError`, `UnsupportedClassVersionError`..., kiểm tra các lớp/JAR/runtime được dùng.
- Nếu thấy stack trace của `ArithmeticException`, `NullPointerException`, `IOException`..., tìm đường gọi gây lỗi và trạng thái dữ liệu.

Đừng kết luận mọi lỗi xuất hiện sau lệnh `java` đều là “lỗi khi chạy” theo nghĩa **logic chương trình**. Lỗi liên kết thường cũng chỉ được phát hiện trong quá trình khởi chạy hoặc thực thi.

### Bước 2: Xác nhận phiên bản môi trường

```bash
java -version
javac -version
```

Với bài thực hành Java 17, hãy xác nhận cả compiler lẫn runtime thực sự trỏ đến Java 17. Máy có nhiều JDK hoặc IDE dùng JDK khác terminal là nguồn nhầm lẫn phổ biến.

Nếu cần kiểm tra file `.class`:

```bash
javap -verbose App.class
```

Xem `major version` (Java 17 là `61`) và các thông tin lớp/phương thức được biên dịch. Phiên bản class file cho biết **mức bytecode**, không khẳng định chương trình chắc chắn chạy được trên mọi runtime cùng phiên bản.

### Bước 3: Xem classpath, module path và các dependency

Trong ứng dụng thông thường, runtime cần tìm được **đúng phiên bản** các lớp mà chương trình dựa vào.

```bash
java -cp . App
```

Ở đây `-cp .` đặt thư mục hiện tại vào classpath; đây là ví dụ đơn giản không có JAR bên ngoài. Trong dự án thực tế, classpath có thể do IDE, Maven, Gradle hoặc tập lệnh khởi chạy thiết lập.

Các công cụ hữu ích của JDK 17:

```bash
jar tf my-library.jar
jdeps my-app.jar
```

`jar tf` liệt kê nội dung JAR; `jdeps` hỗ trợ phân tích phụ thuộc tĩnh. Chúng **không bảo đảm phát hiện mọi phụ thuộc được nạp động qua reflection hoặc cấu hình**.

Khi cần quan sát lớp nào JVM HotSpot 17 thực sự nạp, có thể dùng:

```bash
java -Xlog:class+load=info -cp . App
```

Lệnh in nhiều thông tin chẩn đoán; tìm tên lớp và nguồn tải để phát hiện JAR bất ngờ. `-Xlog` là tiện ích chẩn đoán của JVM HotSpot, không nên coi mọi tùy chọn của nó là hợp đồng chung cho tất cả các bản hiện thực JVM.

### Bước 4: Đọc stack trace từ chỗ có ích

Ví dụ:

```text
Exception in thread "main" java.lang.ArithmeticException: / by zero
    at RuntimeErrorDemo.main(RuntimeErrorDemo.java:4)
```

Cách đọc:

1. `ArithmeticException` là **loại lỗi**; `/ by zero` mô tả điều kiện.
2. `RuntimeErrorDemo.java:4` cho biết vị trí trong mã nguồn được biên dịch (nếu có thông tin dòng).
3. Các dòng `at ...` tiếp theo, nếu có, thể hiện chuỗi lời gọi.
4. Nếu có `Caused by: ...`, lần theo chuỗi nguyên nhân để tìm lỗi gốc. Với `NoClassDefFoundError`, điều này đặc biệt quan trọng vì nguyên nhân có thể là lỗi khởi tạo lớp từ trước.

Thông báo trên chỉ là minh họa; số dòng, cách trình bày và các dòng stack trace phụ thuộc mã nguồn và runtime thực tế.

### Bước 5: Sửa ở đúng tầng và thử lại

| Phát hiện | Hành động phù hợp |
| --- | --- |
| `javac` báo sai kiểu, không tìm thấy biến/phương thức | Sửa mã nguồn hoặc dependency ở compile classpath, sau đó biên dịch lại. |
| `NoSuchMethodError`/`NoSuchFieldError` | Đồng bộ API, JAR và ứng dụng; build lại các lớp dùng API đã đổi. |
| `NoClassDefFoundError` | Kiểm tra dependency runtime, class loader, module path và lỗi khởi tạo lớp gốc. |
| `UnsupportedClassVersionError` | Chọn runtime phù hợp với bytecode hoặc biên dịch đúng mức tương thích được hỗ trợ. |
| `NullPointerException`/`ArithmeticException` | Kiểm tra dữ liệu, bất biến của chương trình, xử lý đầu vào và test tình huống gây lỗi. |
| `IOException` hoặc lỗi môi trường | Kiểm tra quyền truy cập, đường dẫn, tài nguyên, dịch vụ ngoài và khả năng khôi phục. |

Trong môi trường sử dụng **Java Platform Module System (JPMS)** của Java 17, còn có lỗi cấu hình hoặc giải quyết mô-đun khi biên dịch/khởi động, chẳng hạn thiếu mô-đun được `requires`. Chúng cũng có thể ngăn ứng dụng chạy nhưng **không phải thông báo lỗi mô-đun nào cũng là `LinkageError`**. Phân loại dựa vào lỗi thực tế và giai đoạn phát hiện.

## 7. So sánh qua ba bài thực hành ngắn

| Bài thực hành | Cách tạo tình huống | Kết quả mong đợi | Cách giải quyết |
| --- | --- | --- | --- |
| **Biên dịch** | Gán chuỗi `"ten"` trực tiếp vào biến `int` trong `CompileErrorDemo` | `javac` báo `incompatible types` | Sửa kiểu hoặc chuyển đổi dữ liệu có kiểm soát |
| **Liên kết** | Build `App` với `Greeter.say()`, sau đó chỉ thay `Greeter.class` bằng bản không còn `say()` | `java App` báo `NoSuchMethodError` | Cập nhật caller/API và build lại đồng bộ |
| **Khi chạy** | Build `RuntimeErrorDemo` rồi chạy `java RuntimeErrorDemo 0` | `ArithmeticException: / by zero` | Kiểm tra mẫu số và xử lý đầu vào |

Ba trường hợp cho thấy **cùng một môi trường JDK 17** có thể tạo ra ba nhóm lỗi rất khác nhau; lựa chọn đúng cách điều tra sẽ tiết kiệm nhiều thời gian hơn việc xóa và cài lại JDK mỗi khi gặp lỗi.

## 8. Câu hỏi tự kiểm tra

**1. Vì sao `javac` thành công nhưng `java` vẫn có thể báo `NoSuchMethodError`?**  
Vì class file/JAR khi chạy có thể khác API mà caller đã dùng lúc biên dịch. JVM không tìm được phương thức với chữ ký phù hợp trong lớp thực tế được nạp.

**2. `NumberFormatException` trong `Integer.parseInt(args[0])` có phải lỗi biên dịch không?**  
Không. Cú pháp và kiểu có thể hoàn toàn hợp lệ; ngoại lệ chỉ xuất hiện khi chuỗi đầu vào không biểu diễn số nguyên hợp lệ.

**3. `NoClassDefFoundError` có luôn có nghĩa là tệp JAR bị thiếu không?**  
Không. Ngoài thiếu định nghĩa lớp ở runtime, nó có thể liên quan đến việc lớp đã thất bại khi khởi tạo. Đọc thông báo đầy đủ và chuỗi nguyên nhân.

**4. Thấy lỗi sau khi gõ `java App` thì có được khẳng định đó là lỗi logic khi chạy không?**  
Không. JVM có thể phát hiện lỗi liên kết khi nạp lớp hoặc giải quyết tham chiếu trong lúc chạy.

**5. Biên dịch cho Java 17 rồi chạy bằng JVM Java 11 có thể xảy ra lỗi gì?**  
`UnsupportedClassVersionError` do JVM cũ không hỗ trợ class file Java 17 (major version 61).

**6. Khi cần tìm tệp JAR có lớp sai phiên bản, nên kiểm tra gì?**  
Kiểm tra runtime classpath/module path, các dependency được triển khai và nguồn lớp được nạp; nếu dùng HotSpot có thể xem log class loading.

## Tài liệu chính thức

- [Java Language Specification, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html) — các quy tắc của ngôn ngữ và những điều compiler cần kiểm tra.
- [Java Virtual Machine Specification, Java SE 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) — các giai đoạn nạp, liên kết, khởi tạo lớp.
- [Java SE 17 API — LinkageError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html) — họ lỗi liên kết của JVM.
- [Java SE 17 API — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html) — ngoại lệ không bắt buộc khai báo tại thời điểm biên dịch.
- [Java 17 javac Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) và [Java 17 java Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) — công cụ biên dịch và chạy, tùy chọn cần thiết để chẩn đoán.

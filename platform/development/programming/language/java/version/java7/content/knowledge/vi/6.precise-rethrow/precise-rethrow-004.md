# Quan hệ giữa kiểu `catch` và danh sách `throws` trong Java hiện đại

> **Ngữ cảnh Java 7 – Ném lại ngoại lệ (rethrow).** Khi bắt rồi ném lại ngoại lệ, kiểu được khai báo trong `catch`, nội dung khối `try` và danh sách `throws` của method liên hệ với nhau thông qua **kiểm tra checked exception lúc biên dịch**. Từ Java 7, cơ chế *precise rethrow* cho phép compiler suy ra các kiểu checked exception cụ thể ngay cả khi tham số `catch` được khai báo rộng như `Exception`, với điều kiện quan trọng về tính `final` hoặc *effectively final*. Các nguyên tắc này tiếp tục áp dụng trong Java 17+.

## 1. Phân biệt bốn khái niệm trước khi viết code

Hãy đọc đoạn Java sau:

```java
static void load() throws IOException {
    try {
        readFile();
    } catch (IOException error) {
        System.err.println("Đọc thất bại");
        throw error;
    }
}
```

Đây là **snippet minh họa**, với `readFile()` là method giả định có thể ném `IOException` và import `java.io.IOException`. Bốn thành phần có vai trò riêng:

| Thành phần | Vai trò |
| --- | --- |
| `try` | Bao các biểu thức/lệnh có thể phát sinh ngoại lệ |
| `catch (IOException error)` | Chọn ngoại lệ phù hợp với kiểu `IOException` (hoặc subtype) và cung cấp một biến tham chiếu đến đối tượng bị ném |
| `throw error;` | **Ném** đối tượng ngoại lệ đã bắt để nó tiếp tục lan truyền đến tầng gọi |
| `throws IOException` trên method | Công bố/cho phép phương thức có thể **để ngoại lệ checked này thoát ra**; compiler dùng thông tin đó để kiểm tra caller |

Hai từ khóa dễ nhầm nhất là **`throw`** (một câu lệnh thực thi) và **`throws`** (một phần của khai báo method/constructor). Một method có `throws` không có nghĩa nó chắc chắn phát sinh exception mỗi lần gọi; nó công bố những loại checked exception mà caller phải tính đến.

**Không có quy tắc “kiểu của `catch` phải trùng nguyên văn danh sách `throws`”.** Điều quan trọng là các **checked exception có thể thoát khỏi thân method**, theo phân tích của compiler, phải được khai báo trong `throws` bằng cùng loại hoặc một supertype phù hợp, trừ khi chúng được xử lý bởi một catch bao quanh.

## 2. Checked và unchecked exception quyết định nghĩa vụ `throws`

Các loại exception thường gặp:

- **Checked:** `IOException`, `SQLException`, `ParseException`, `ClassNotFoundException` và các lớp ứng dụng kế thừa `Exception` nhưng không kế thừa `RuntimeException`. Nếu có thể lan truyền ra khỏi method, chúng cần được xử lý hoặc khai báo.
- **Unchecked:** `RuntimeException` và các subtype (chẳng hạn `NumberFormatException`, `IllegalArgumentException`, `NullPointerException`), cùng `Error` và các subtype. Trình biên dịch không bắt buộc đưa chúng vào danh sách `throws`.
- `Throwable` và một số subclass nằm ngoài hai nhánh unchecked vẫn thuộc checked exception theo Java Language Specification, dù code ứng dụng thông thường ít khai báo trực tiếp `throws Throwable`.

Ví dụ:

```java
static int parseCount(String text) {
    return Integer.parseInt(text);  // Có thể ném NumberFormatException.
}
```

Method này **không cần `throws NumberFormatException`**, bởi đó là unchecked exception. Có thể khai báo để cung cấp tài liệu API, nhưng không nên cho rằng việc thêm `throws` làm runtime hay compiler bắt lỗi đó theo cách mới.

Trái lại:

```java
static String readText(Path path) throws IOException {
    return Files.readString(path);
}
```

Snippet trên dùng `Path`/`Files` với import thích hợp; `Files.readString(Path)` được thêm từ Java 11, còn chính sách checked exception tồn tại trước Java 7. `readString` có thể ném `IOException`, nên method `readText` hoặc phải bắt và xử lý lỗi này, hoặc khai báo `throws IOException`.

**Vai trò của caller:** khi gọi method có `throws IOException`, caller có thể `catch (IOException e)` hoặc tiếp tục khai báo `throws IOException`; nếu không có phương án nào phù hợp, Java báo lỗi biên dịch. Caller không cần `catch` mọi exception unchecked có thể xảy ra.

## 3. Ba đường đi cơ bản từ `try` đến `throws`

Xét method thấp hơn:

```java
static void mayFail() throws IOException {
    // Thao tác có thể phát sinh IOException.
}
```

### 3.1. Không bắt lỗi: khai báo để truyền tiếp

```java
static void propagate() throws IOException {
    mayFail();
}
```

`propagate` có thể để `IOException` thoát ra, vì vậy khai báo `throws IOException`. Nó không cần câu lệnh `throw` tường minh: exception từ method được gọi tự lan truyền khi không có handler phù hợp.

### 3.2. Bắt và xử lý hoàn toàn: không cần `throws` cho lỗi đã xử lý

```java
static boolean recover() {
    try {
        mayFail();
        return true;
    } catch (IOException error) {
        return false; // Fallback hợp lệ theo hợp đồng method.
    }
}
```

`recover` không bắt buộc khai báo `throws IOException`, vì ngoại lệ checked đó đã được bắt và không được ném ra ngoài. Điều này chỉ đúng khi **nhánh `catch`, `finally` và những lệnh khác** cũng không phát sinh checked exception chưa xử lý.

### 3.3. Bắt rồi ném lại: nghĩa vụ `throws` quay trở lại

```java
static void observeAndPropagate() throws IOException {
    try {
        mayFail();
    } catch (IOException error) {
        System.err.println("Có lỗi I/O");
        throw error;
    }
}
```

`throw error` làm cùng đối tượng `IOException` tiếp tục đi ra khỏi method. Vì thế `observeAndPropagate` cần khai báo `throws IOException` hoặc được xử lý bởi một handler bao ngoài nếu method ở trong ngữ cảnh khác. Ghi log trước khi ném lại không được xem là “đã xử lý xong”.

Ba snippet này minh họa cấu trúc với `mayFail` đã được định nghĩa. Chúng cho thấy chính **cách dùng biến exception trong thân `catch`** quyết định lỗi có thoát ra hay không; tên kiểu trong tham số catch không tự động biến thành danh sách `throws`.

## 4. Mối quan hệ giữa kiểu tĩnh của `catch` và `throw error`

Nếu viết:

```java
catch (IOException error) {
    throw error;
}
```

`error` có kiểu tĩnh `IOException`. Với việc ném lại biến này, phương thức có thể cần `throws IOException` (hoặc khai báo một supertype như `Exception`, nếu hợp đồng cho phép). Tuy nhiên, để chính xác hơn, có hai tình huống:

1. **Ném lại tham số catch không bị gán lại:** compiler có thể dùng *precise rethrow* để xét những checked exception cụ thể mà `try` thật sự có thể ném và lọt vào catch, thay vì chỉ nhìn kiểu khai báo rộng của tham số.
2. **Ném một biến khác hoặc tham số catch đã bị gán lại:** compiler dựa vào kiểu tĩnh của biểu thức ném, khiến kiểu `Exception` có thể yêu cầu `throws Exception` rộng hơn.

Tính năng thứ nhất là một điểm cải tiến từ **Java 7** vẫn được dùng. Hãy xem ví dụ có thể chạy và phản ví dụ không biên dịch bên dưới.

## 5. Precise rethrow: `catch (Exception e)` nhưng `throws` vẫn cụ thể

Giả sử method tầng thấp khai báo:

```java
static void lowLevel(int mode) throws IOException, SQLException {
    // Có thể ném IOException hoặc SQLException.
}
```

Trước khi xét các điều kiện, trực giác thông thường có thể cho rằng:

```java
static void service(int mode) throws IOException, SQLException {
    try {
        lowLevel(mode);
    } catch (Exception error) {
        throw error;
    }
}
```

sẽ bắt buộc phải khai báo `throws Exception`, vì biến `error` có kiểu tĩnh `Exception`. **Với Java 7 trở lên, nhận định đó không đúng trong trường hợp này.** Compiler thấy trong `try` chỉ có thể phát sinh hai loại checked exception cụ thể `IOException` và `SQLException` từ lời gọi `lowLevel`, và tham số `error` không được gán lại. Quy tắc *precise rethrow* cho phép giữ danh sách `throws IOException, SQLException` chính xác hơn.

Điều này không biến `Exception` thành `IOException` tại runtime. Nếu một `IOException` bị ném, đối tượng gốc vẫn là `IOException`; nếu `SQLException` bị ném, nó vẫn là `SQLException`. Tính năng chỉ cải thiện **phân tích tĩnh về checked exceptions được ném ra**.

### 5.1. Ví dụ hoàn chỉnh: rethrow chính xác dù catch rộng

Lưu thành `PreciseRethrowDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class PreciseRethrowDemo {
    static void lowLevel(int mode) throws IOException, SQLException {
        if (mode == 1) {
            throw new IOException("disk");
        }
        if (mode == 2) {
            throw new SQLException("db");
        }
    }

    static void service(int mode) throws IOException, SQLException {
        try {
            lowLevel(mode);
        } catch (Exception error) {
            System.out.println("service=" + error.getClass().getSimpleName());
            throw error; // Java 7+: precise rethrow.
        }
    }

    public static void main(String[] args) {
        for (int mode = 0; mode < 3; mode++) {
            try {
                service(mode);
                System.out.println("caller=" + mode + ": OK");
            } catch (IOException | SQLException error) {
                System.out.println(
                    "caller=" + mode + ": "
                    + error.getClass().getSimpleName()
                );
            }
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 --release 17 PreciseRethrowDemo.java
java PreciseRethrowDemo
```

Stdout:

```text
caller=0: OK
service=IOException
caller=1: IOException
service=SQLException
caller=2: SQLException
```

**Tại sao đây là một ví dụ quan trọng?**

- `lowLevel` chỉ khai báo hai checked exception cụ thể; `service` gọi nó trong `try`.
- `catch (Exception error)` bắt được cả hai, cũng có thể bắt nhiều unchecked exceptions trong thực thi.
- Biến `error` **không bị gán lại**, nên compiler áp dụng precise rethrow đối với checked exceptions phù hợp từ khối try.
- `service` khai báo `throws IOException, SQLException`; không phải khai báo `throws Exception` chỉ vì viết `catch (Exception error)`.
- `main` xử lý cả hai với multi-catch nên không cần khai báo chúng trong `throws`.
- Cùng một ngoại lệ được truyền qua service sang caller. In `getClass().getSimpleName()` thể hiện runtime class vẫn nguyên vẹn.

**Giới hạn suy luận:** compiler dựa vào các **loại ngoại lệ mà khối `try` có thể ném theo khai báo và phân tích tĩnh**, không đọc tâm lý người viết hay đoán riêng từ dữ liệu runtime. Nếu method được gọi khai báo `throws Exception` rộng, caller không thể giả định compiler sẽ tự biết nó “thực tế chỉ ném IOException”.

## 6. Điều kiện `final` / *effectively final* và những trường hợp mất precise rethrow

Quy tắc precise rethrow trong Java 7+ áp dụng khi biểu thức `throw` là một biến tham số của `catch` được khai báo `final` hoặc là *effectively final* theo quy tắc của ngôn ngữ. Trong catch đơn như `catch (Exception e)`, biến là *effectively final* khi không bị gán lại.

### 6.1. Không gán lại tham số catch: có precise rethrow

```java
static void valid() throws IOException, SQLException {
    try {
        lowLevel(1);
    } catch (Exception error) {
        System.err.println(error.getMessage());
        throw error;
    }
}
```

Với `lowLevel` như đã khai báo, Java 17 biên dịch được. Thêm modifier `final` tường minh cho tham số cũng hợp lệ:

```java
catch (final Exception error) {
    throw error;
}
```

Cả hai là snippet đặt trong ngữ cảnh có `try` và method tương ứng.

### 6.2. Gán lại tham số catch: mất precise rethrow

Ví dụ **cố ý không biên dịch** nếu method chỉ khai báo `throws IOException, SQLException`:

```java
static void invalid() throws IOException, SQLException {
    try {
        lowLevel(1);
    } catch (Exception error) {
        error = new Exception("replaced", error);
        throw error;  // ERROR: cần xử lý/khai báo Exception rộng hơn.
    }
}
```

Vì tham số `error` được gán lại, nó không còn *effectively final*. Khi đó `throw error` được phân tích theo kiểu tĩnh `Exception`; danh sách chỉ gồm `IOException, SQLException` không đáp ứng yêu cầu. Nếu thay bằng `throws Exception`, ví dụ có thể biên dịch, nhưng hợp đồng API trở nên rộng hơn và loại lỗi được ném đã thực sự bị thay bằng đối tượng mới.

### 6.3. Ném biến alias không giống ném lại tham số catch

Ví dụ này cũng **không biên dịch** với danh sách `throws` hẹp:

```java
static void invalidAlias() throws IOException, SQLException {
    try {
        lowLevel(1);
    } catch (Exception error) {
        Exception alias = error;
        throw alias; // ERROR: alias không phải catch parameter.
    }
}
```

Dù `alias` không bị gán lại, nó là **biến cục bộ khác**, không phải tham số `catch` trực tiếp. Quy tắc precise rethrow đặc biệt không tự lan sang mọi alias. Compiler xét kiểu tĩnh `Exception` của alias.

**Ứng dụng:** nếu chỉ muốn ghi log hoặc bổ sung ngữ cảnh trước khi ném lại, hãy giữ `throw error;` trực tiếp và đừng gán lại biến ngoại lệ. Nếu thực sự muốn thay exception, thực hiện *exception translation* có chủ đích và thiết kế lại `throws`/loại exception theo hợp đồng tầng trên.

## 7. Multi-catch và danh sách `throws`

Java 7 cũng cho phép:

```java
catch (IOException | SQLException error) {
    throw error;
}
```

Ở đây, biến của **multi-catch** là *implicitly final* (không được gán lại) và kiểu tĩnh của nó được suy ra từ các alternative. Khi ném lại, Java vẫn phân tích những loại checked exception tương ứng với khối try. Method thường khai báo các kiểu cụ thể còn thoát ra, ví dụ:

```java
static void service(int mode) throws IOException, SQLException {
    try {
        lowLevel(mode);
    } catch (IOException | SQLException error) {
        throw error;
    }
}
```

Đây là snippet dùng lại `lowLevel` ở phần trước. Hai exception ở `catch` không có quan hệ cha–con, nên multi-catch hợp lệ. Nếu có nhiều alternative mà mỗi loại cần một chính sách khác nhau, nên viết các catch tách biệt thay vì gộp vì mục đích làm ngắn code.

**Khác biệt so với catch rộng:**

| Cú pháp | Các loại được bắt | Khả năng giữ `throws` cụ thể |
| --- | --- | --- |
| `catch (IOException e) { throw e; }` | IOException và subtype | Thông thường `throws IOException` là đủ |
| `catch (IOException \| SQLException e) { throw e; }` | Hai nhóm exception được chỉ rõ | Có thể `throws IOException, SQLException` |
| `catch (Exception e) { throw e; }`, e không bị gán lại | Nhiều exception hơn | Java 7+ có thể suy ra tập checked cụ thể từ try bằng precise rethrow |
| `catch (Exception e) { e = ...; throw e; }` | Nhiều exception hơn | Khi ném lại biến đã gán, thường phải cho phép `Exception` rộng hơn |
| `catch (Exception e) { throw new IOException("...", e); }` | Nhiều exception hơn | Ném đối tượng mới có kiểu `IOException`; `throws IOException` phù hợp, nhưng đây là translation |

**Lưu ý về kiểu runtime:** danh sách `throws` và kiểu tĩnh của tham số `catch` không biến đổi đối tượng đã bị ném. Chúng chủ yếu là thông tin phục vụ kiểm tra lúc biên dịch và tài liệu API. Khi đổi thành `new IOException(...)` thì mới tạo **một ngoại lệ khác**, và nên truyền lỗi gốc làm `cause`.

## 8. Xử lý hết checked exceptions: method không cần khai báo chúng

Nếu toàn bộ checked exceptions từ `try` được bắt và **không ném lại**, method không cần `throws` cho những lỗi đã xử lý.

Lưu thành `HandledExceptionDemo.java`:

```java
import java.io.IOException;

public class HandledExceptionDemo {
    static void read(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("disk");
        }
    }

    static String safeRead(boolean fail) {
        try {
            read(fail);
            return "OK";
        } catch (IOException error) {
            return "FALLBACK";
        }
    }

    public static void main(String[] args) {
        System.out.println(safeRead(false));
        System.out.println(safeRead(true));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 HandledExceptionDemo.java
java HandledExceptionDemo
```

```text
OK
FALLBACK
```

`safeRead` không cần `throws IOException` bởi nhánh `catch` đã chuyển lỗi thành một giá trị fallback theo hợp đồng. Trong hệ thống thực tế, **fallback chỉ an toàn khi nó có ý nghĩa nghiệp vụ**: không được âm thầm trả thành công cho lỗi dữ liệu hoặc hạ tầng quan trọng chỉ để làm mất `throws`.

Nếu nhánh `catch` gọi một helper có thể ném checked exception khác, chẳng hạn `auditFailure(...) throws SQLException`, thì phương thức vẫn phải xử lý hoặc khai báo `SQLException` đó. Điều kiện áp dụng cho **toàn bộ thân method**, không riêng nội dung `try`.

## 9. Exception translation: kiểu `throws` thay đổi khi bạn ném đối tượng mới

Khi một tầng cần chuyển lỗi hạ tầng sang lỗi domain, nó có thể dùng một exception khác. Loại exception **thực sự được ném ra** sau khi translation, không phải tên type trong `catch`, mới chi phối khai báo `throws`.

### 9.1. Chuyển sang checked exception

```java
static void importData() throws ImportException {
    try {
        lowLevel(1);
    } catch (IOException | SQLException error) {
        throw new ImportException("Không thể nhập dữ liệu", error);
    }
}
```

Đây là snippet dùng class giả định `ImportException extends Exception`, có constructor `(String, Throwable)`. Nếu `ImportException` checked, method khai báo `throws ImportException` (hoặc supertype cho phép); không cần `throws IOException, SQLException` khi hai lỗi gốc đã được catch và được bọc thành checked exception mới. **Giữ `error` làm cause** giúp truy vết.

### 9.2. Chuyển sang unchecked exception

Nếu exception domain kế thừa `RuntimeException`, method không bị bắt buộc khai báo `throws` cho exception đó. Đây là một lựa chọn thiết kế API có tác động đến trách nhiệm caller, không phải “thủ thuật” để né checked exception.

Lưu thành `ExceptionTranslationDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class ExceptionTranslationDemo {
    static final class ImportFailure extends RuntimeException {
        ImportFailure(Throwable cause) {
            super("import failed", cause);
        }
    }

    static void lowLevel(int mode) throws IOException, SQLException {
        if (mode == 1) {
            throw new IOException("disk");
        }
        if (mode == 2) {
            throw new SQLException("db");
        }
    }

    static void service(int mode) {
        try {
            lowLevel(mode);
        } catch (IOException | SQLException error) {
            throw new ImportFailure(error);
        }
    }

    public static void main(String[] args) {
        for (int mode = 0; mode < 3; mode++) {
            try {
                service(mode);
                System.out.println("import=" + mode + ": OK");
            } catch (ImportFailure error) {
                System.out.println(
                    "import=" + mode + ": "
                    + error.getCause().getClass().getSimpleName()
                );
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ExceptionTranslationDemo.java
java ExceptionTranslationDemo
```

```text
import=0: OK
import=1: IOException
import=2: SQLException
```

**Điều thay đổi:** `service` không khai báo checked `throws`, bởi nó đã bắt hai checked exceptions và ném `ImportFailure` unchecked. **Điều được giữ:** nguyên nhân thực sự vẫn có thể được tìm thông qua `getCause()`. Trong ứng dụng lớn, nên định nghĩa mapping lỗi và chiến lược log nhất quán ở ranh giới API.

## 10. Các nguồn checked exception khác cũng ảnh hưởng đến `throws`

Không chỉ câu lệnh `throw e` được compiler phân tích. Những nguồn sau cũng có thể buộc method khai báo hoặc xử lý checked exception:

| Nguồn | Ví dụ | Điều cần xét |
| --- | --- | --- |
| Lời gọi method | `Files.readString(path)` | Tham chiếu đến `throws` được công bố bởi API đó |
| Constructor | `new FileInputStream(path.toFile())` | Constructor có thể ném `FileNotFoundException` |
| Câu lệnh `throw` | `throw new IOException("disk");` | Exception mới là checked |
| Thân `catch` | `audit(error)` có `throws SQLException` | Lỗi mới phát sinh trong handler có thể thoát |
| Thân `finally` | `cleanup()` có `throws IOException` | Lỗi cleanup cần được xử lý/khai báo, có thể ảnh hưởng đến lỗi gốc |
| Đóng tài nguyên trong try-with-resources | `reader.close()` | `close()` có thể ném checked exception ngay cả khi thân try thành công |
| Ném lại tham số catch | `throw error;` | Phân tích precise rethrow hay kiểu tĩnh, tùy điều kiện |

### 10.1. Try-with-resources và kiểu `close()`

Khi dùng:

```java
static String loadFirstLine(Path file) throws IOException {
    try (BufferedReader reader =
             Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
        return reader.readLine();
    }
}
```

Đây là snippet với import `java.io.BufferedReader`, `java.io.IOException`, `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets`. `Files.newBufferedReader` và `readLine` có thể ném `IOException`, cũng như thao tác `close` của `BufferedReader`. Vì vậy method khai báo `throws IOException`.

Một chi tiết quan trọng: nếu khai báo tài nguyên theo kiểu `AutoCloseable` rộng, method `close()` của interface đó khai báo `throws Exception`; kiểu khai báo của resource có thể khiến compiler yêu cầu xử lý ngoại lệ rộng hơn so với tài nguyên được khai báo là `Closeable`/`BufferedReader` (với `close() throws IOException`). **Kiểu tĩnh của tài nguyên và của method được gọi đều ảnh hưởng đến exception analysis**.

Với try-with-resources, nếu thân try ném lỗi và `close()` cũng ném, lỗi khi đóng thường nằm trong `getSuppressed()` của lỗi chính. Khi rethrow hoặc wrap, đừng làm mất cause/suppressed information một cách vô ý. Đây là cơ chế có từ Java 7 và vẫn áp dụng hiện nay.

### 10.2. `finally` không bảo đảm “đóng mọi chuyện”

`finally` có thể tự ném checked exception; method phải tính đến nó. Nếu `finally` ném exception trong lúc một exception khác đang lan truyền, exception từ `finally` có thể thay thế đường lỗi trước đó. Với tài nguyên `AutoCloseable`, ưu tiên try-with-resources phù hợp để quản lý đóng an toàn, thay vì viết `finally` phức tạp chỉ để đóng các stream.

## 11. Luật khai báo `throws` khi override một method

Một API class/interface có thể công bố kiểu lỗi checked cho method. Khi class con override, **danh sách checked exceptions được khai báo không được mở rộng vượt hợp đồng của method cha**. Có thể giữ cùng loại, dùng subtype hẹp hơn hoặc loại bỏ checked exception khi implementation xử lý nội bộ.

Ví dụ chạy được trên JDK 17+; lưu thành `OverrideThrowsDemo.java`:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class OverrideThrowsDemo {
    interface Loader {
        void load() throws IOException;
    }

    static final class SpecificLoader implements Loader {
        @Override
        public void load() throws FileNotFoundException {
            throw new FileNotFoundException("config");
        }
    }

    public static void main(String[] args) {
        Loader loader = new SpecificLoader();
        try {
            loader.load();
        } catch (IOException error) {
            System.out.println("loader=" + error.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 OverrideThrowsDemo.java
java OverrideThrowsDemo
```

```text
loader=FileNotFoundException
```

Giải thích:

- Interface `Loader.load` khai báo `throws IOException`.
- Implementation được phép khai báo `throws FileNotFoundException`, là subtype của `IOException`.
- Biến `loader` có kiểu tĩnh `Loader`, nên caller dựa vào hợp đồng `throws IOException` của interface, dù runtime class là `SpecificLoader`.
- Nếu override khai báo `throws SQLException` không có quan hệ phù hợp với `IOException`, đó sẽ là lỗi biên dịch.
- Unchecked exceptions không chịu hạn chế danh sách `throws` theo cách checked exceptions, nhưng vẫn cần thiết kế hành vi API rõ ràng.

**Liên hệ với catch/rethrow:** nếu một method override bị giới hạn bởi `throws IOException`, việc bắt rồi ném lại một checked exception khác như `SQLException` sẽ không hợp lệ khi nó thoát ra, trừ khi bạn xử lý hoặc chuyển đổi lỗi đúng với hợp đồng của method cha.

## 12. Những hiểu nhầm về danh sách `throws`

### 12.1. `throws` không có nghĩa method chắc chắn ném exception

`void run() throws IOException` là **khai báo khả năng/cho phép** đối với checked exception. Method có thể hoàn tất bình thường, không ném gì ở lần gọi cụ thể. Compiler không mô phỏng mọi đường đi runtime để kết luận một ngoại lệ chắc chắn xảy ra.

### 12.2. `throws Exception` hợp lệ nhưng thường quá rộng

Method không override có thể khai báo `throws Exception`, điều này đủ rộng để cho phép `IOException` và `SQLException` thoát ra. Tuy nhiên, caller thường phải xử lý một kiểu rộng hơn và khó biết chiến lược phục hồi cụ thể. Nhờ precise rethrow của Java 7, nhiều method có thể giữ danh sách `throws` nhỏ và rõ ngay cả khi dùng một catch rộng để ghi log.

### 12.3. `catch (Exception e)` không bắt `Error`

`Exception` và `Error` là hai nhánh khác nhau dưới `Throwable`. Việc catch `Exception` không tự bắt các `Error` như `OutOfMemoryError`. Thông thường ứng dụng không nên dùng `catch (Throwable)` làm giải pháp mặc định cho mọi lỗi chỉ để “đảm bảo không thoát”.

### 12.4. Kiểu tĩnh của `catch` không quyết định hoàn toàn bộ ngoại lệ runtime

`catch (IOException e)` có thể nhận `FileNotFoundException` vì class con phù hợp, và khi `throw e` thì runtime object vẫn là `FileNotFoundException`. Compiler quan tâm đến loại ngoại lệ được cho phép trong chương trình; JVM dùng đối tượng thực tế để truyền lỗi.

### 12.5. `throw new Exception(...)` khác `throw e`

`throw e` có thể ném lại chính đối tượng đã bắt, giữ stack trace/cause gốc. `throw new Exception("...", e)` tạo đối tượng khác có cause. Việc tạo ngoại lệ mới có thể làm **thay đổi** danh sách `throws` được yêu cầu: kiểu `Exception` mới thường phải được khai báo/handle rộng hơn, trừ khi nó là unchecked hoặc được xử lý bởi catch bao ngoài.

### 12.6. `throws` không phải một phần của chữ ký method để overload

Không thể định nghĩa hai method có cùng tên và cùng tham số chỉ khác danh sách `throws` rồi gọi chúng như hai overload riêng. `throws` thuộc hợp đồng ngoại lệ của khai báo, nhưng **không phải thành phần phân biệt overload**. Ví dụ:

```java
void process() throws IOException { }
void process() throws SQLException { } // ERROR: duplicate method signature.
```

Đây là ví dụ **cố ý không biên dịch**.

## 13. Bảng quyết định nhanh khi review `catch` và `throws`

| Mã trong catch hoặc method | Checked exception có thể thoát? | Hợp đồng cần xem xét |
| --- | --- | --- |
| Gọi `load() throws IOException` và không bắt | Có: `IOException` | `throws IOException` hoặc supertype |
| `catch (IOException e) { return fallback; }` | Không còn `IOException` từ nhánh này | Method có thể không cần `throws IOException` |
| `catch (IOException e) { throw e; }` | Có: `IOException` | `throws IOException` phù hợp |
| `catch (IOException \| SQLException e) { throw e; }` | Có thể có cả hai | `throws IOException, SQLException` |
| `catch (Exception e) { throw e; }`, e *effectively final*, try chỉ có hai checked types trên | Compiler dùng precise rethrow | `throws IOException, SQLException` vẫn hợp lệ |
| `catch (Exception e) { e = new Exception(...); throw e; }` | Có thể ném kiểu `Exception` mới | Xử lý hoặc khai báo `throws Exception` |
| `catch (Exception e) { Exception x = e; throw x; }` | Throw expression có kiểu tĩnh `Exception` | Cần xử lý/khai báo `Exception` |
| `catch (IOException e) { throw new IllegalStateException(e); }` | Ném unchecked `IllegalStateException` | Không bắt buộc khai báo checked `throws` cho lỗi đó |
| Khối `catch` xử lý IO nhưng `finally` có thể ném SQL | Có: `SQLException` từ finally | Xử lý/khai báo `SQLException` |
| Try-with-resources với `close() throws IOException` | Có thể IO ở lúc đóng | `throws IOException` hoặc xử lý nó |

Bảng mô tả các trường hợp riêng lẻ trong giả định không có checked exception khác từ những lệnh phụ trợ. Trong code thật, phải phân tích **toàn bộ** đường đi của method.

## 14. Quy trình sửa lỗi biên dịch liên quan `catch` và `throws`

Khi gặp thông báo kiểu *unreported exception ... must be caught or declared to be thrown*, làm theo các bước:

1. **Xác định biểu thức gây ra checked exception:** lời gọi API, constructor, `throw`, `close()` hay `finally`.
2. **Xem API đang khai báo những gì:** đừng dựa vào một loại exception xảy ra trong lần chạy trước để suy ra toàn bộ khả năng.
3. **Xem catch có bắt hết không:** một `catch` rộng hay hẹp? Có nhánh nào ném lại, gọi helper có `throws` hoặc ném exception mới không?
4. **Đối với `throw e`:** kiểm tra e có đúng là catch parameter và có `final`/*effectively final* không; precise rethrow có áp dụng không?
5. **Thiết kế hợp đồng tầng trên:** truyền checked exception cụ thể bằng `throws`, xử lý tại chỗ khi có recovery đúng, hoặc chuyển thành lỗi domain có cause phù hợp.
6. **Kiểm tra override/interface:** không mở rộng danh sách checked exceptions vượt method cha.
7. **Chạy compiler và test các đường lỗi:** tập trung cả case bình thường, từng loại exception, cause và cleanup.

**Tránh hai kiểu “sửa nhanh” dễ gây lỗi thiết kế:** tự động mở mọi method thành `throws Exception` mà không xét API; hoặc bọc tất cả checked exceptions thành `RuntimeException` chỉ để trình biên dịch không yêu cầu xử lý. Chọn phương án theo trách nhiệm của tầng ứng dụng.

## 15. Câu hỏi thực hành có đáp án

**Câu 1.** Method gọi `read() throws IOException`, bắt `IOException` rồi chỉ trả `false`. Có cần `throws IOException` không?  
**Đáp án:** Không cần vì lỗi từ `read` đã được xử lý, nếu không có nguồn IOException khác có thể thoát ra.

**Câu 2.** Method dùng `catch (IOException e) { throw e; }`. Có thể khai báo `throws IOException` không?  
**Đáp án:** Có. Caller sẽ phải bắt hoặc khai báo tiếp exception checked đó.

**Câu 3.** Từ Java 7, vì sao `catch (Exception e) { throw e; }` có thể đi với `throws IOException, SQLException`?  
**Đáp án:** Nếu e là catch parameter final/effectively final và khối try chỉ có thể phát sinh hai loại checked exceptions tương ứng, precise rethrow giúp compiler suy ra tập cụ thể.

**Câu 4.** Nếu thêm `e = new Exception("new");` trước `throw e`, điều gì thay đổi?  
**Đáp án:** Tham số catch không còn effectively final; compiler phân tích throw theo kiểu tĩnh `Exception`, khiến `throws IOException, SQLException` không đủ.

**Câu 5.** Đổi thành `Exception alias = e; throw alias;` có giữ precise rethrow không?  
**Đáp án:** Không. Alias không phải catch parameter, vì thế `throw alias` theo kiểu tĩnh `Exception`.

**Câu 6.** Dùng `catch (IOException | SQLException e) { throw e; }`, có bắt buộc method khai báo `throws Exception` không?  
**Đáp án:** Không. Nếu đây là hai checked exceptions có thể thoát ra và không có loại checked khác, `throws IOException, SQLException` phù hợp.

**Câu 7.** Một `finally` có thể ném `SQLException` dù `catch` đã xử lý `IOException`. Method có cần khai báo SQL không?  
**Đáp án:** Có, nếu SQL exception từ `finally` không được handler nào khác xử lý.

**Câu 8.** Interface khai báo `void load() throws IOException`. Implementation có thể khai báo `throws FileNotFoundException` và `throws SQLException` không?  
**Đáp án:** Có thể dùng `FileNotFoundException` vì là subtype của `IOException`; không thể tự mở rộng sang `SQLException` checked không được interface cho phép.

**Câu 9.** Có thể overload hai method chỉ khác nhau ở `throws` không?  
**Đáp án:** Không. Danh sách `throws` không dùng để phân biệt method signature khi overload.

**Bài thực hành A:** Chạy `PreciseRethrowDemo`, bỏ modifier `throws SQLException` khỏi `service` rồi xem lỗi compiler. Tiếp theo thay `catch (Exception e)` bằng `catch (IOException | SQLException e)` và xác minh danh sách `throws` cụ thể vẫn hoạt động.

**Bài thực hành B:** Tạo hai phiên bản method: một phiên bản ném trực tiếp `error`, một phiên bản gán lại `error` rồi ném. Biên dịch bằng `javac --release 17` để quan sát sự khác biệt trong yêu cầu `throws`.

**Bài thực hành C:** Dùng try-with-resources đọc một file, làm tài nguyên được khai báo `BufferedReader` rồi thử với biến có kiểu `AutoCloseable`. Tra cứu `close()` của từng kiểu và giải thích vì sao các checked exceptions được compiler yêu cầu có thể khác nhau.

## 16. Tài liệu chuẩn

- [Java Language Specification 17, `11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): cách compiler xác định những checked exception có thể thoát ra.
- [JLS 17, `11.2.2 — Exception Analysis of Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.2): quy tắc precise rethrow đối với tham số catch `final` hoặc effectively final.
- [JLS 17, `14.20 — The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): cơ chế catch, alternative, thứ tự và tính final của biến catch.
- [JLS 17, `8.4.6 — Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): ý nghĩa `throws` trong khai báo method.
- [JLS 17, `8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): hạn chế checked exceptions khi override.

**Ghi nhớ:** `catch` cho biết loại lỗi nào được chặn lại; `throw e` cho biết lỗi có được truyền tiếp hay không; `throws` xác định hợp đồng checked exceptions được phép thoát khỏi method. **Java 7 precise rethrow** giúp một catch rộng vẫn có thể giữ `throws` cụ thể khi ném lại nguyên tham số catch không bị gán lại. Để code hiện đại rõ và an toàn, luôn xét cả kiểu tĩnh, nguồn checked exceptions, hành vi catch/finally và ràng buộc API của caller.

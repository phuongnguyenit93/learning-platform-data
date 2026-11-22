# Precise rethrow và suy ra tập checked exception hẹp hơn trong Java

**Precise rethrow** là khả năng phân tích ngoại lệ của trình biên dịch Java, được bổ sung từ **Java 7**, cho phép một phương thức **bắt ngoại lệ bằng kiểu rộng** (ví dụ `catch (Exception e)`) nhưng khi thực hiện `throw e;`, trình biên dịch có thể xác định **những loại checked exception cụ thể thực sự có thể được ném lại** từ `try` tương ứng. Nhờ đó, chữ ký phương thức không phải luôn khai báo `throws Exception` một cách quá rộng.

Cơ chế này quan trọng khi mã cần ghi nhận một sự cố ở tầng hiện tại nhưng vẫn **ném lại đúng đối tượng exception gốc** cho tầng gọi. Nó đặc biệt hữu ích khi một `try` chứa nhiều thao tác có thể ném các checked exception khác nhau, và chương trình muốn giữ một handler chung mà không đánh mất tính chính xác của hợp đồng `throws`.

Điểm cần ghi nhớ từ đầu: **precise rethrow là phân tích ở thời điểm biên dịch; nó không biến đổi đối tượng ngoại lệ ở runtime, không tự thêm `catch`, không retry thao tác và không chuyển checked exception thành unchecked exception**.

## 1. Vấn đề mà precise rethrow giải quyết

Xét hai thao tác: đọc tệp có thể ném `IOException`, ghi cơ sở dữ liệu có thể ném `SQLException`. Một dịch vụ cần thực hiện đúng một trong hai, ghi nhận lỗi rồi để caller quyết định.

Trước khi xét precise rethrow, người học dễ viết:

```java
static void run(boolean fileMode) throws Exception {
    try {
        if (fileMode) {
            readFile();   // throws IOException
        } else {
            queryDb();    // throws SQLException
        }
    } catch (Exception e) {
        System.out.println("Ghi nhận lỗi");
        throw e;
    }
}
```

Đây là **đoạn minh họa**: `readFile()` và `queryDb()` chưa được định nghĩa, và chữ ký `throws Exception` được viết cố ý rộng. Nếu API thực sự chỉ công bố hai loại checked exception trên, `throws Exception` khiến caller phải xử lý kiểu quá chung. Caller không còn thấy rõ hợp đồng cụ thể từ chữ ký.

Trên Java 7+, khi tham số `catch` thỏa điều kiện *final/effectively final*, Java cho phép viết chính xác hơn:

```java
static void run(boolean fileMode)
        throws IOException, SQLException {
    try {
        if (fileMode) {
            readFile();   // throws IOException
        } else {
            queryDb();    // throws SQLException
        }
    } catch (Exception e) {
        System.out.println("Ghi nhận lỗi");
        throw e;
    }
}
```

Đây cũng là **đoạn minh họa không chạy độc lập**, cần `import java.io.IOException; import java.sql.SQLException;` và hai phương thức tương ứng. Điều đáng chú ý là **biến `e` khai báo là `Exception`**, nhưng compiler vẫn chấp nhận chữ ký `throws IOException, SQLException`, không cần khai báo `throws Exception`.

Tại sao? Bởi compiler phân tích **các loại checked exception có thể phát sinh từ `try`, được handler này bắt và ném lại**. Tham số `e` không bị gán lại, nên tập loại lỗi dùng để kiểm tra lệnh `throw e` có thể hẹp hơn kiểu khai báo `Exception`.

## 2. Ví dụ Java 17 hoàn chỉnh: một `catch`, hai loại checked exception

Lưu chương trình sau thành **`PreciseRethrowDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class PreciseRethrowDemo {
    static void readFile() throws IOException {
        throw new IOException("Không đọc được tệp");
    }

    static void queryDb() throws SQLException {
        throw new SQLException("Không truy cập được DB");
    }

    static void execute(boolean fileMode)
            throws IOException, SQLException {
        try {
            if (fileMode) {
                readFile();
            } else {
                queryDb();
            }
        } catch (Exception e) {
            System.out.println("Service bắt: "
                    + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            execute(true);
        } catch (IOException | SQLException e) {
            System.out.println("Caller: " + e.getMessage());
        }

        try {
            execute(false);
        } catch (IOException | SQLException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac -encoding UTF-8 --release 17 PreciseRethrowDemo.java
java PreciseRethrowDemo
```

**Stdout chính xác** trên console hỗ trợ UTF-8:

```text
Service bắt: IOException
Caller: Không đọc được tệp
Service bắt: SQLException
Caller: Không truy cập được DB
```

Phân tích:

1. `readFile()` công bố checked `IOException`; `queryDb()` công bố checked `SQLException`.
2. `execute` có thể gọi một trong hai. Compiler phân tích cả hai đường đi từ chữ ký và thân `try`.
3. `catch (Exception e)` bắt cả hai loại vì chúng kế thừa `Exception`.
4. `e` không hề bị gán lại. Vì vậy `throw e` được **phân tích chính xác**: hai loại checked exception cần tính đến là `IOException` và `SQLException`.
5. Chữ ký `throws IOException, SQLException` là đủ. `main` vẫn bắt theo kiểu đã khai báo.
6. Khi chạy, `throw e` ném lại **đúng đối tượng** đã được bắt, không tạo instance mới và không thay đổi loại runtime của nó.

`Exception` trong handler là **kiểu tĩnh rộng**; đối tượng thật ở lần thứ nhất là `IOException`, lần thứ hai là `SQLException`. Precise rethrow không biến hai loại đó thành `Exception` mới.

## 3. Quy tắc cốt lõi: tham số `catch` phải là `final` hoặc *effectively final*

Precise rethrow áp dụng khi đối tượng được ném bằng **tham số của mệnh đề `catch`**, với điều kiện tham số ấy được khai báo `final` hoặc **effectively final**.

- `final`: biến được khai báo với từ khóa `final`, nên không được gán lại.
- *Effectively final*: không ghi `final` nhưng chương trình **không gán lại** tham số sau khi nhận giá trị ban đầu.
- `throw e;`: biểu thức ném tham số của handler. Compiler có thể theo dõi nguồn các exception mà handler này bắt từ `try`.

Ví dụ:

```java
catch (Exception e) {
    log(e);
    throw e; // e effectively final, nếu log không gán lại e.
}
```

Đây là **phần thân handler minh họa** với `log(e)` giả định đã định nghĩa. Gọi phương thức và đọc thuộc tính của `e` **không làm mất** tính effectively final. Trái lại, phép gán `e = other;` sẽ làm mất tính chất đó.

Viết `final` tường minh cũng hợp lệ:

```java
catch (final Exception e) {
    throw e;
}
```

Từ khóa `final` ràng buộc **biến tham chiếu**, không khiến toàn bộ đối tượng exception bất biến. Các API cho phép thay đổi dữ liệu trên `Throwable` (ví dụ `addSuppressed` hoặc `setStackTrace`) vẫn có quy tắc riêng. Precise rethrow quan tâm tới **khả năng tham số chuyển sang tham chiếu khác**, không đánh đồng với sự bất biến của object.

## 4. Vì sao việc gán lại `e` phá khả năng suy ra tập hẹp?

Hãy xét phương thức sau. Đây là **phản ví dụ cố ý không biên dịch** trên Java 17:

```java
import java.io.IOException;

class ReassignCatchParameter {
    static void read() throws IOException {
        throw new IOException("Lỗi I/O");
    }

    static void relay() throws IOException {
        try {
            read();
        } catch (Exception e) {
            e = new IOException("Đã thay lỗi"); // Gán lại e.
            throw e; // Compiler phải xét kiểu rộng Exception.
        }
    }
}
```

Vì `e` được khai báo kiểu `Exception` và đã bị **gán lại**, compiler không được áp dụng quy tắc precise rethrow cho tham số này như trước. `throw e` có thể ném một `Exception` theo kiểu tĩnh rộng, nên chữ ký chỉ `throws IOException` không đủ. Lỗi thường thể hiện dưới dạng **unreported exception java.lang.Exception; must be caught or declared to be thrown**.

Điều này không có nghĩa mọi phép gán lại `e` đều bị Java cấm. Với **single-catch parameter** không có `final`, việc gán lại có thể hợp lệ về cú pháp, nhưng làm thay đổi đối tượng đang được tham chiếu và khả năng phân tích checked exception.

Các lựa chọn đúng tùy mục tiêu:

- Nếu cần **giữ cùng đối tượng**, không gán lại `e` và dùng `throw e;`.
- Nếu muốn **tạo ngoại lệ mới** với hợp đồng khác, hãy tạo biến/đối tượng mới, giữ lỗi gốc qua `cause` nếu thích hợp.
- Nếu thực sự cho phép ném một `Exception` bất kỳ, khai báo `throws Exception` là hợp lệ nhưng cần cân nhắc độ rộng của API.

Không nên đổi `e` thành một instance mới rồi gọi đó là “rethrow nguyên bản”: caller sẽ nhận object mới chứ không phải exception đã phát sinh ở thao tác gốc.

## 5. Định nghĩa chính xác: suy ra từ `try` nào?

Khi một `catch` bắt nhiều loại có thể ném ra từ `try`, compiler không chỉ nhìn **tên loại của tham số `catch`**. Nó xét những exception có thể được phát sinh bởi **khối `try` tương ứng**, và những loại mà handler hiện tại có thể bắt, sau khi tính đến các handler đứng trước.

Có thể hình dung quá trình phân tích cho một `throw e` trong handler final/effectively final:

1. Xác định **`try` gắn với handler chứa `e`**.
2. Xác định các loại exception có thể phát sinh theo phân tích tĩnh từ `try`, bao gồm các lời gọi phương thức và những cấu trúc hợp lệ bên trong.
3. Xác định trong số đó loại nào **được handler hiện tại bắt**, không bị một handler trước trong cùng chuỗi `catch` bắt mất.
4. Dùng các loại tương ứng trong việc kiểm tra những **checked exception** của `throw e`.
5. Những loại là **unchecked** không yêu cầu `throws` trong chữ ký theo quy tắc catch-or-declare.

Đây là **mô hình suy luận thực hành**, không phải trình tự từng bước của bộ máy JVM. Ngôn ngữ Java quy định các điều kiện kiểm tra tại **compile time**, còn JVM vẫn nhận một đối tượng exception đơn lẻ khi chạy.

Không nên hiểu rằng compiler “chạy thử” nhánh `if` với dữ liệu thật để biết chính xác một exception runtime cụ thể. Nó phân tích **khả năng** từ kiểu và cấu trúc, không biết mọi giá trị đầu vào trong tương lai.

## 6. Handler trước đã bắt một loại: tập loại còn lại có thể hẹp hơn

Precise rethrow tính đến việc những exception cụ thể đã được `catch` **đứng trước** xử lý.

Ví dụ Java 17 đầy đủ, lưu **`EarlierCatchDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class EarlierCatchDemo {
    static void execute(boolean ioFailure)
            throws IOException, SQLException {
        if (ioFailure) {
            throw new IOException("Tệp lỗi");
        }
        throw new SQLException("DB lỗi");
    }

    static void relay(boolean ioFailure) throws SQLException {
        try {
            execute(ioFailure);
        } catch (IOException e) {
            System.out.println("I/O đã xử lý: " + e.getMessage());
        } catch (Exception e) {
            System.out.println("Lỗi còn lại: "
                    + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        relaySafely(true);
        relaySafely(false);
    }

    static void relaySafely(boolean ioFailure) {
        try {
            relay(ioFailure);
        } catch (SQLException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 EarlierCatchDemo.java
java EarlierCatchDemo
```

**Stdout chính xác**:

```text
I/O đã xử lý: Tệp lỗi
Lỗi còn lại: SQLException
Caller: DB lỗi
```

Giải thích:

- `execute` có thể phát sinh `IOException` hoặc `SQLException`.
- `catch (IOException e)` đầu tiên xử lý đường I/O và **không ném tiếp**.
- `catch (Exception e)` phía sau không còn nhận `IOException` từ `try` đó, do loại này đã được handler trước bắt.
- Vì `e` trong handler sau là effectively final, `throw e` được kiểm tra chính xác; với các checked exception của `try` trong ví dụ, chỉ còn **`SQLException`**.
- Do đó `relay` chỉ cần khai báo `throws SQLException`, không cần `throws Exception` hay `throws IOException`.

Đừng nhầm với tình huống handler `catch (IOException e)` **ném một ngoại lệ mới**: exception phát sinh từ thân `catch` trước không được thử bắt bởi handler `catch (Exception e)` tiếp theo ở cùng cấu trúc. Nó sẽ đi ra phạm vi bao ngoài hoặc caller theo quy tắc lan truyền.

## 7. Multi-catch và precise rethrow liên quan như thế nào?

Java 7 cũng giới thiệu **multi-catch**: một handler có thể nêu nhiều kiểu exception bằng dấu `|`, ví dụ:

```java
catch (IOException | SQLException e) {
    throw e;
}
```

Với multi-catch:

- Tham số `e` của multi-catch là **implicitly final**: không thể gán lại.
- Handler chỉ nhận **một đối tượng exception** tại mỗi lần thực thi, thuộc một trong các loại đã liệt kê.
- Khi `throw e`, đối tượng thật được ném lại; không tạo object mới.
- Compiler có thể giữ các loại checked exception riêng biệt trong phân tích, thay vì buộc công bố một kiểu cha quá rộng.
- Các kiểu liệt kê trong cùng multi-catch **không được có quan hệ subtype với nhau**, ví dụ `IOException | Exception` không hợp lệ.

Ví dụ hoàn chỉnh, lưu **`MultiCatchPreciseDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchPreciseDemo {
    static void task(boolean io) throws IOException, SQLException {
        if (io) {
            throw new IOException("Lỗi tệp");
        }
        throw new SQLException("Lỗi DB");
    }

    static void relay(boolean io) throws IOException, SQLException {
        try {
            task(io);
        } catch (IOException | SQLException e) {
            System.out.println("Relay: " + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        for (boolean io : new boolean[] {true, false}) {
            try {
                relay(io);
            } catch (IOException | SQLException e) {
                System.out.println("Caller: " + e.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 MultiCatchPreciseDemo.java
java MultiCatchPreciseDemo
```

**Stdout chính xác**:

```text
Relay: IOException
Caller: Lỗi tệp
Relay: SQLException
Caller: Lỗi DB
```

Trong multi-catch, không thể viết `e = new IOException("x");` vì tham số ngầm định `final`. Hai cơ chế **multi-catch** và **precise rethrow** phối hợp tốt, nhưng là hai khái niệm khác nhau:

- Multi-catch cho phép **gộp cú pháp xử lý** nhiều loại exception không có quan hệ subtype.
- Precise rethrow cho phép **kiểm tra chính xác checked exception ở lệnh ném lại** khi điều kiện trên tham số được đáp ứng.

Không phải cứ dùng multi-catch mới có precise rethrow: ví dụ `catch (Exception e)` với `e` effectively final ở phần trước đã chứng minh điều ngược lại.

## 8. `catch (Exception e)` vẫn bắt những loại khác ngoài checked exception

`Exception` là lớp cha của `RuntimeException`. Vì vậy một `catch (Exception e)` cũng có thể bắt các unchecked exception như `IllegalArgumentException` và `NullPointerException` phát sinh trong `try`. Tuy nhiên, điều đó **không bắt buộc** phương thức khai báo `throws RuntimeException` hoặc `throws NullPointerException`.

Ví dụ:

```java
static void run(String text) throws IOException {
    try {
        readFile();                   // throws IOException
        Integer.parseInt(text);       // Có thể ném NumberFormatException
    } catch (Exception e) {
        throw e;
    }
}
```

Đây là **phương thức minh họa**, cần `readFile()` được định nghĩa và `IOException` được import. Chữ ký `throws IOException` đủ về mặt checked exception vì `NumberFormatException` là một lớp con unchecked của `RuntimeException`. Khi chạy, handler có thể nhận một trong hai và ném lại đúng object; caller phải quyết định có bắt những unchecked exception đó hay không theo hợp đồng.

**`catch (Exception e)` không bắt các lớp `Error`**, vì `Error` là nhánh anh em của `Exception` dưới `Throwable`. Không nên thay thành `catch (Throwable e)` chỉ để “bắt tất cả” trong mã nghiệp vụ: nhiều `Error` nghiêm trọng và không phù hợp để tiếp tục bình thường.

Một đoạn Java biên dịch được **không bảo đảm** mọi nhánh lỗi đã được xử lý an toàn. Precise rethrow chỉ giải quyết mức chính xác của hợp đồng checked exception khi compiler kiểm tra.

## 9. Kiểu tĩnh của phương thức được gọi đặt giới hạn cho sự chính xác

Compiler phân tích **chữ ký và cấu trúc mã nhìn thấy được**, không tự suy ra kiểu ngoại lệ từ những gì bạn *biết* về cách triển khai ở runtime.

Giả sử API công bố:

```java
static void externalApi() throws Exception {
    throw new IOException("Lỗi I/O");
}
```

Đây là **phương thức minh họa**, cần import `IOException`. Mặc dù thân minh họa chỉ ném `IOException`, **caller** thấy chữ ký `throws Exception`; compiler phải tính đến khả năng checked exception thuộc kiểu `Exception` từ hợp đồng đã công bố.

Bởi vậy đoạn **cố ý không biên dịch** sau không thể dựa vào precise rethrow để chỉ khai báo `IOException`:

```java
static void caller() throws IOException {
    try {
        externalApi();  // Declared throws Exception
    } catch (Exception e) {
        throw e;        // Có thể phải khai báo throws Exception
    }
}
```

Bởi `externalApi()` được khai báo `throws Exception`, tại vị trí gọi, loại checked exception có thể phát sinh theo phân tích là `Exception`, không chỉ `IOException`. Dù tham số `e` effectively final, nó không thể làm chữ ký caller chính xác hơn thông tin có được từ API được gọi.

Sửa theo **hợp đồng thật sự**:

- Nếu sở hữu `externalApi` và chắc chắn hợp đồng chỉ có lỗi I/O, thay chữ ký của nó thành `throws IOException` để caller có thông tin chính xác.
- Nếu API chủ đích cho phép mọi `Exception` checked, caller có thể khai báo `throws Exception` hoặc bắt/chuyển các trường hợp tương ứng.
- Nếu đổi tầng trừu tượng bằng wrapper mới, hãy chủ động thiết kế hợp đồng và giữ cause; không coi đó là precise rethrow của đối tượng gốc.

Đừng “ép kiểu” exception để qua compiler khi không có bảo đảm về loại runtime thực tế. Một `ClassCastException` trong xử lý lỗi chỉ khiến tình huống tệ hơn.

## 10. Checked exception của tài nguyên cũng nằm trong phân tích `try`

Một khối `try-with-resources` có thể phát sinh checked exception **khi đóng resource**, dù thân `try` không ném checked exception nào. Vì vậy precise rethrow không chỉ nhìn các lệnh nghiệp vụ ở giữa dấu ngoặc nhọn: phải tính cả những thao tác đóng do cấu trúc ngôn ngữ thực hiện.

Ví dụ Java 17 độc lập **`ResourcePreciseDemo.java`**:

```java
import java.io.IOException;

public class ResourcePreciseDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đang đóng");
            throw new IOException("Không đóng được");
        }
    }

    static void use() throws IOException {
        try (Resource resource = new Resource()) {
            System.out.println("Trong try");
        } catch (Exception e) {
            System.out.println("Catch: "
                    + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            use();
        } catch (IOException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ResourcePreciseDemo.java
java ResourcePreciseDemo
```

**Stdout chính xác**:

```text
Trong try
Đang đóng
Catch: IOException
Caller: Không đóng được
```

`close()` khai báo `throws IOException`. Dù thân `try` chỉ in ra console, kết thúc phạm vi sẽ gọi `close()`, nơi ném `IOException`. Handler rộng `catch (Exception e)` nhận lỗi, rồi `throw e`; compiler cho phép `use() throws IOException` vì phân tích checked exception bao gồm lỗi có thể phát sinh khi đóng tài nguyên.

Nếu **cả thân `try` và `close()` cùng ném exception**, `try-with-resources` thường giữ lỗi của thân làm exception chính và gắn lỗi đóng làm **suppressed exception**. `throw e` giữ nguyên đối tượng chính và danh sách suppressed hiện có; nó không tự xóa lỗi đóng. Đừng dùng `finally` có `throw` mới một cách vô ý để che mất lỗi gốc.

## 11. Precise rethrow và ném lại đúng đối tượng

`catch (Exception e) { throw e; }` **không tự gọi `new Exception(...)`**. Ở runtime, `throw e` dùng đúng reference tới đối tượng đã bắt. Precise rethrow là việc *compiler tính nghĩa vụ checked exception*, không phải tạo object mới hoặc gỡ bỏ stack trace.

Ví dụ nhận diện identity trong **`IdentityPreciseDemo.java`**:

```java
import java.io.IOException;

public class IdentityPreciseDemo {
    static IOException original;

    static void relay() throws IOException {
        original = new IOException("Lỗi gốc");
        try {
            throw original;
        } catch (Exception e) {
            System.out.println("Trong catch: " + (e == original));
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            relay();
        } catch (IOException e) {
            System.out.println("Tại caller: " + (e == original));
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 IdentityPreciseDemo.java
java IdentityPreciseDemo
```

**Stdout chính xác**:

```text
Trong catch: true
Tại caller: true
Message: Lỗi gốc
```

Mục đích của field `original` chỉ để kiểm tra identity, không phải mẫu chia sẻ exception qua biến `static` cho chương trình đa luồng. Ở mã thực, hãy để cơ chế ném và bắt truyền thông tin lỗi.

`throw e` thông thường cũng không tự tạo stack trace mới chỉ vì ném lại. Nếu cần đổi loại lỗi do tầng trừu tượng, dùng wrapper với `cause` (ví dụ `new IllegalStateException("Không nạp được", e)`); đó là **đối tượng mới**, không còn cùng identity, và khác precise rethrow nguyên bản.

## 12. Kết hợp với các handler lồng nhau

Một `try` bên trong có thể bắt và giải quyết `IOException`; `try` bên ngoài chỉ còn thấy những exception được truyền lên thực tế theo phân tích luồng.

Ví dụ khung:

```java
static void dispatch() throws SQLException {
    try {
        try {
            readFile();  // throws IOException
        } catch (IOException e) {
            System.out.println("Đã xử lý I/O");
        }

        queryDb();       // throws SQLException
    } catch (Exception e) {
        throw e;
    }
}
```

Đây là **đoạn minh họa**, cần hai phương thức `readFile` và `queryDb` cùng import các loại exception. Nếu handler I/O bên trong kết thúc bình thường và không ném lại, outer `try` không để `IOException` ấy thoát ra. `throw e` ở handler ngoài có thể được kiểm tra với checked exception còn lại là `SQLException`.

Ngược lại, nếu handler trong `catch (IOException e)` viết `throw e;` thì `IOException` có thể lan ra phạm vi ngoài. Khi đó cần khai báo hoặc xử lý nó; precise rethrow không tự “xóa” một exception có thể thực sự thoát ra.

Lưu ý: việc đặt các `catch` riêng biệt còn giúp mã dễ đọc. Đừng lồng nhiều tầng chỉ để đạt chữ ký hẹp hơn nếu một tổ chức handler đơn giản đã thể hiện rõ trách nhiệm xử lý.

## 13. Trường hợp không thuộc precise rethrow

Dễ nhầm các trường hợp sau là cùng một cơ chế:

### 13.1. Ném một biến ngoại lệ không phải tham số `catch`

```java
static void rethrowVariable(Exception saved) throws Exception {
    throw saved;
}
```

Đây là **phương thức hợp lệ không có `main`**. `saved` là tham số phương thức, **không phải tham số `catch` gắn với `try`**. Dù bạn không gán lại `saved`, compiler không dùng quy tắc precise rethrow từ một `try` như với catch parameter. Vì kiểu tĩnh của `saved` là `Exception`, chữ ký `throws Exception` là phù hợp.

### 13.2. Tạo đối tượng exception mới

```java
catch (Exception e) {
    throw new Exception("Lỗi mới", e);
}
```

Đây là **đoạn handler minh họa**. Lệnh ném biểu thức `new Exception(...)`, không phải `throw e`. Exception mới có loại checked `Exception`; phương thức phải bắt/khai báo nó theo hợp đồng. Cơ chế precise rethrow dành cho tham số catch không làm loại exception mới trở thành `IOException` chỉ vì `cause` của nó là `IOException`.

### 13.3. Chỉ có một `catch` cụ thể

```java
catch (IOException e) {
    throw e;
}
```

Handler này ném lại kiểu khai báo `IOException`; ngay cả không bàn về precise rethrow, chữ ký `throws IOException` đã hiển nhiên đúng. Hiệu quả nổi bật nhất của precise rethrow là tình huống **bắt kiểu rộng** nhưng không buộc công bố tất cả checked exception thuộc kiểu rộng.

### 13.4. Bọc checked exception thành unchecked

```java
catch (IOException e) {
    throw new IllegalStateException("Tầng dịch vụ lỗi", e);
}
```

Đoạn này tạo **unchecked exception** mới, giữ `IOException` qua `getCause()`; không yêu cầu khai báo checked `IOException` từ việc ném wrapper. Nhưng đây là **đổi hợp đồng**, không phải precise rethrow. Lựa chọn này chỉ nên dùng khi hợp đồng tầng mới yêu cầu một ngoại lệ ứng dụng phù hợp.

## 14. Precise rethrow không xóa trách nhiệm xử lý lỗi

Một chữ ký gọn không có nghĩa mọi thất bại đều được phục hồi. Khi rethrow:

- Phương thức hiện tại vẫn **kết thúc bất thường** nếu exception thoát ra.
- Caller vẫn cần biết nên thử phương án dự phòng, trả lỗi cho người dùng, dừng yêu cầu hay chuyển tiếp.
- `finally` và `try-with-resources` vẫn tham gia cleanup theo quy tắc; không tự rollback dữ liệu hoặc hoàn tác mọi side effect.
- Các unchecked exception có thể đi lên dù không xuất hiện trong `throws`.
- Kiểu tĩnh chính xác hơn giúp **caller đọc API và dùng `catch` cụ thể**; không bảo đảm hệ thống không có lỗi runtime.
- Nếu không có việc gì cần làm ở tầng trung gian, có thể **bỏ `catch` chỉ để ném lại**, để exception lan tự nhiên.

Một nơi phù hợp để dùng handler bắt rộng rồi rethrow là tầng cần bổ sung ngữ cảnh **mà không được làm thay đổi hợp đồng checked exception**. Nhưng hãy xem liệu bắt cụ thể hoặc multi-catch có rõ ràng hơn; đừng dùng `catch (Exception e)` vô điều kiện, vì nó còn bắt nhiều `RuntimeException` có thể là bug.

## 15. Lỗi thường gặp

| Hiểu sai | Cách hiểu đúng |
| --- | --- |
| “`catch (Exception e)` rồi `throw e` luôn phải `throws Exception`.” | Java 7+ có precise rethrow khi `e` final/effectively final; có thể khai báo các checked exception hẹp hơn. |
| “Precise rethrow chuyển checked thành unchecked.” | Không; nó chỉ phân tích tập checked exception có thể ném lại chính xác hơn. |
| “Chỉ multi-catch mới có precise rethrow.” | Không; single-catch rộng `catch (Exception e)` cũng có thể được phân tích chính xác. |
| “`catch (Exception e)` chỉ bắt checked exception.” | Nó còn bắt `RuntimeException`, nhưng không bắt `Error`. |
| “`throw e` tạo đối tượng exception mới.” | Nó ném lại cùng object mà `e` tham chiếu, nếu `e` chưa bị gán lại. |
| “Một handler đứng sau vẫn nhận loại đã bị handler trước bắt.” | Không; các handler được xét theo thứ tự, loại đã bắt ở trước không được chuyển sang handler sau. |
| “Compiler biết chắc lúc chạy chỉ ném `IOException` dù callee khai báo `throws Exception`.” | Compiler kiểm tra hợp đồng tĩnh; kiểu `Exception` rộng vẫn phải được xét. |
| “Viết `throws IOException` là đủ chỉ vì exception ban đầu có cause là IOException.” | Một wrapper checked mới có thể là `Exception`; cause không thay đổi kiểu checked của wrapper. |
| “Gán lại `e` vẫn giữ precise rethrow như cũ.” | Gán lại tham số single-catch làm mất điều kiện effectively final; multi-catch còn cấm gán lại. |
| “Precise rethrow tự xử lý cleanup và retry.” | Không; đó là những vấn đề riêng về luồng thực thi, tài nguyên và chính sách. |

## 16. Tự kiểm tra với các tình huống

**Câu 1.** Thân `try` có thể ném `IOException` và `SQLException`; handler `catch (Exception e) { throw e; }` không gán lại `e`. Có cần `throws Exception` không?  
**Đáp án:** Không nhất thiết. `throws IOException, SQLException` có thể đủ theo precise rethrow, nếu đó là các checked exception có thể thoát ra và không có loại checked khác phát sinh ở handler.

**Câu 2.** Trong `catch (Exception e)`, thêm `e = new IOException("khác");` trước `throw e;` có còn precise rethrow không?  
**Đáp án:** Không theo cơ chế dành cho catch parameter final/effectively final, vì `e` đã bị gán lại. Nếu chữ ký chỉ `throws IOException`, compiler có thể yêu cầu kiểu rộng hơn `Exception`.

**Câu 3.** `catch (IOException | SQLException e)` có thể gán lại `e` không?  
**Đáp án:** Không. Tham số multi-catch implicitly final.

**Câu 4.** Thân `try` có `IOException` và `SQLException`, nhưng handler đầu bắt `IOException` và xử lý xong. Handler sau là `catch (Exception e) { throw e; }`. Tập checked exception cần xét cho handler sau là gì?  
**Đáp án:** Theo ví dụ thông thường, còn `SQLException`; `IOException` đã được handler trước bắt, miễn là handler trước không ném thêm lỗi checked cần tính riêng.

**Câu 5.** Vì sao precise rethrow không thể thu hẹp khi gọi một API công bố `throws Exception` nhưng bạn biết phiên bản hiện tại chỉ ném `IOException`?  
**Đáp án:** Compiler phải xét hợp đồng tĩnh của lời gọi, trong đó `Exception` vẫn là kiểu checked có thể phát sinh.

**Câu 6.** `throw e` có sửa message, cause hoặc stack trace của exception gốc không?  
**Đáp án:** Bản thân lệnh không tạo object mới hay tự thay đổi các thuộc tính đó. Dữ liệu có thể bị thay đổi bởi code khác hoặc cơ chế đặc biệt của JVM, nhưng không vì hành động rethrow đơn thuần.

**Câu 7.** Nếu resource `close()` khai báo `throws IOException` nhưng thân `try` không ném checked exception, `catch (Exception e) { throw e; }` có thể khiến phương thức cần `throws IOException` không?  
**Đáp án:** Có. Phân tích ngoại lệ của `try-with-resources` tính cả lỗi có thể ném khi đóng tài nguyên.

**Câu 8.** Một handler `catch (Exception e) { throw new IOException("mới"); }` có phải precise rethrow không?  
**Đáp án:** Không. Nó ném một đối tượng mới có kiểu checked `IOException`; luật kiểm tra loại ném mới áp dụng, không phải phân tích `throw e` của tham số catch.

**Câu 9.** Một phương thức `throws IOException, SQLException` có thể còn ném `NullPointerException` không?  
**Đáp án:** Có. Đây là unchecked exception, không bắt buộc khai báo.

**Câu 10.** Vì sao không nên viết `catch (Exception e)` ở khắp mọi nơi chỉ để tận dụng precise rethrow?  
**Đáp án:** Vì phạm vi bắt quá rộng có thể vô tình bao gồm lỗi lập trình; chỉ nên bắt khi tầng hiện tại thật sự cần làm việc có ý nghĩa trước khi chuyển lỗi đi.

## 17. Checklist kiểm tra một đoạn precise rethrow

Khi review một phương thức chứa `throw e`, hãy lần lượt kiểm tra:

1. **`e` có phải tham số của `catch` không?** Một tham số phương thức thông thường không hưởng quy tắc này theo cách tương tự.
2. **`e` có final hoặc effectively final không?** Không được có phép gán lại.
3. **`try` tương ứng có thể ném những checked exception nào?** Xem cả chữ ký phương thức được gọi, cấu trúc bên trong và `close()` của tài nguyên.
4. **Có handler nào đứng trước đã bắt một số loại?** Chỉ các exception còn tới được handler hiện tại mới liên quan với precise rethrow của handler ấy.
5. **Có exception mới ném từ handler không?** Cần tính riêng, không coi nó là rethrow nguyên bản.
6. **Chữ ký `throws` có mô tả đúng tập checked exception có thể thoát ra?** Không ghi quá hẹp trái quy tắc, cũng hạn chế kiểu rộng không cần thiết.
7. **Có unchecked exception không?** Không phải khai báo nhưng vẫn phải quản lý rủi ro theo hợp đồng.
8. **Có thực sự cần `catch` không?** Nếu handler chỉ `throw e` mà không bổ sung giá trị, để exception tự lan truyền có thể đơn giản hơn.
9. **Caller có hành động xử lý cuối phù hợp không?** Chữ ký chính xác giúp caller xử lý, không thay thế chính sách phục hồi.
10. **Ví dụ đã chạy trên phiên bản Java dùng trong dự án chưa?** Precise rethrow có từ Java 7; các API và cú pháp khác trong ví dụ có thể yêu cầu phiên bản mới hơn.

## 18. Kết luận

**Precise rethrow** giúp Java suy ra **tập checked exception hẹp hơn** khi một handler bắt kiểu rộng nhưng ném lại **chính tham số catch final/effectively final** bằng `throw e;`. Compiler dựa vào các checked exception có thể phát sinh từ `try` tương ứng, có tính tới những handler đứng trước và cấu trúc tài nguyên, thay vì đơn giản bắt chữ ký phải `throws Exception` chỉ vì `e` có kiểu khai báo `Exception`.

Multi-catch phối hợp tốt với precise rethrow vì tham số của nó ngầm định `final`, nhưng không phải điều kiện bắt buộc để precise rethrow hoạt động. Không gán lại `e`, không nhầm `throw e` với `throw new ...`, và không mong compiler suy luận hẹp hơn chữ ký tĩnh của API được gọi.

Quy tắc thực hành là: **để tầng hiện tại xử lý khi có khả năng phục hồi; nếu cần ghi nhận rồi lan truyền, giữ nguyên ngoại lệ và khai báo tập checked exception chính xác nhất mà ngôn ngữ cho phép**.

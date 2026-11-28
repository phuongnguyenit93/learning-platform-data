# Try, catch, finally và multi-catch

Trong ứng dụng Java, không phải mọi thao tác đều thành công: một chuỗi đầu vào có thể không chuyển được thành số, tệp có thể không tồn tại, quyền truy cập bị từ chối, kết nối mạng có thể gián đoạn. **Exception** cho phép một phần mã thông báo sự cố và chuyển quyền điều khiển tới nơi có khả năng xử lý, thay vì trộn lẫn kết quả hợp lệ với những mã lỗi không rõ nghĩa.

Bài này thuộc chương **Ngoại lệ và vòng đời tài nguyên** của module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Trọng tâm là cú pháp, luồng thực thi và cách thiết kế với `try`, `catch`, `finally`, **multi-catch** trong Java SE 27. Với tài nguyên cần giải phóng, bài cũng làm rõ vì sao nên dùng `try-with-resources` thay vì mặc định đóng tài nguyên thủ công trong `finally`.

Các cú pháp được giới thiệu đều đang được hỗ trợ trong Java 27, không cần bật preview. Ví dụ tách bạch giữa **quy tắc của ngôn ngữ** và **quy ước thiết kế ứng dụng**; không phải mọi exception đều nên bị bắt hoặc chuyển thành giá trị mặc định.

## 1. Nắm ngữ cảnh: exception là gì?

Một exception là đối tượng thuộc `Throwable` hoặc một subclass của nó. Khi một thao tác ném exception, luồng thực thi thông thường bị gián đoạn và Java tìm handler phù hợp, bắt đầu từ các `catch` liên quan.

Hệ phân cấp thường gặp:

```text
Throwable
├── Error
│   └── OutOfMemoryError
└── Exception
    ├── IOException              (checked)
    │   └── FileNotFoundException
    ├── SQLException             (checked)
    └── RuntimeException        (unchecked)
        ├── IllegalArgumentException
        │   └── NumberFormatException
        ├── NullPointerException
        └── ArithmeticException
```

| Nhóm | Ví dụ | Quy tắc khi biên dịch |
| --- | --- | --- |
| **Checked exception** | `IOException`, `SQLException` | Mã gây ra exception phải xử lý hoặc khai báo theo quy tắc exception checking của Java |
| **Unchecked exception (runtime)** | `NumberFormatException`, `IllegalArgumentException` | Không bị buộc phải `catch` hay khai báo `throws` |
| **Error** | `OutOfMemoryError`, `LinkageError` | Unchecked; ứng dụng thông thường không nên cố nuốt hoặc phục hồi từ phần lớn trường hợp này |

Lưu ý, `Exception` bao gồm cả checked exceptions lẫn `RuntimeException`; còn `Error` là nhánh khác trực tiếp dưới `Throwable`. `catch (Exception e)` sẽ bắt những subtype tương thích của `Exception`, nhưng không bắt `Error`.

### 1.1. `throw` khác `throws`

- `throw` là **câu lệnh** thực sự ném một đối tượng exception.
- `throws` là một phần của **khai báo method/constructor**, mô tả các checked exceptions có thể được truyền tới mã gọi.

```java
import java.io.IOException;

static String requireCode(String code) throws IOException {
    if (code == null || code.isBlank()) {
        throw new IOException("Missing code");
    }
    return code;
}
```

Đây chỉ là ví dụ cú pháp; với dữ liệu đầu vào không hợp lệ trong một API thông thường, `IllegalArgumentException` có thể phù hợp hơn `IOException`. Chọn kiểu exception dựa trên ý nghĩa sự cố, không dựa vào việc muốn thử `catch`.

## 2. Cấu trúc `try`, `catch` và `finally`

Một câu lệnh `try` thông thường có thể có một hoặc nhiều `catch`, một `finally`, hoặc cả hai:

```java
try {
    // Thực hiện công việc có thể gây exception
} catch (SpecificException ex) {
    // Xử lý loại sự cố cụ thể
} catch (AnotherException ex) {
    // Xử lý loại sự cố khác
} finally {
    // Công việc cần chạy khi thoát khỏi cấu trúc try/catch
}
```

`SpecificException` và `AnotherException` trong ví dụ trên là tên minh họa; khi viết mã thực tế, thay bằng các exception class có thể bắt được.

Các dạng hợp lệ với `try` thông thường:

```java
try {
    runTask();
} catch (IllegalStateException ex) {
    recover(ex);
}
```

```java
try {
    runTask();
} finally {
    recordCompletion();
}
```

```java
try {
    runTask();
} catch (IllegalStateException ex) {
    recover(ex);
} finally {
    recordCompletion();
}
```

Các hàm `runTask`, `recover` và `recordCompletion` ở đây đại diện cho các hành động của ứng dụng. Với `try` **thông thường**, không được bỏ cả `catch` lẫn `finally`. Riêng `try-with-resources` có resource specification và được phép không có `catch`/`finally`.

### 2.1. Nhiệm vụ của từng khối

- **`try`:** khoanh vùng những thao tác cần xử lý ngoại lệ và các lệnh phải thực hiện theo luồng bình thường.
- **`catch`:** chỉ chạy nếu có exception phù hợp được ném trong phần được bảo vệ, và khối đó là handler đầu tiên phù hợp.
- **`finally`:** chạy sau phần `try` và `catch` liên quan theo quy tắc hoàn tất câu lệnh, dù luồng rời khỏi vì `return`, `throw`, `break` hay `continue`.

Không có `catch` phù hợp thì exception tiếp tục được truyền ra ngoài sau khi `finally` liên quan hoàn thành. `finally` **không tự xử lý** exception: nó chỉ là nơi thực hiện công việc trong quá trình rời khối.

## 3. Luồng thực thi: khối nào chạy, khối nào bị bỏ qua?

Xét đoạn mã:

```java
static void process(String raw) {
    try {
        int value = Integer.parseInt(raw);
        System.out.println("Parsed: " + value);
    } catch (NumberFormatException ex) {
        System.out.println("Invalid integer");
    } finally {
        System.out.println("Finished attempt");
    }
}
```

Hai lần gọi:

```java
process("27");
// Parsed: 27
// Finished attempt

process("abc");
// Invalid integer
// Finished attempt
```

Sơ đồ:

```text
                 Vào try
                     |
                     v
             Có ném exception?
                /         \
             không        có
               |           |
               |       Tìm catch đầu tiên
               |           | phù hợp
               |         /   \
               |       có    không
               |       |       |
               |     catch   Propagate
               |       |       |
               +-------+-------+
                       |
                       v
                    finally
                       |
                       v
             Kết thúc / return / throw
```

Nếu exception xuất hiện giữa các câu lệnh trong `try`, những câu lệnh **sau vị trí ném** trong cùng đường thực thi sẽ không được chạy:

```java
try {
    int n = Integer.parseInt("wrong"); // Ném NumberFormatException
    System.out.println(n);             // Không chạy
} catch (NumberFormatException ex) {
    System.out.println("Cannot parse");
}
```

Nếu chính khối `catch` ném một exception khác, các `catch` còn lại **của cùng câu lệnh `try`** không tự động bắt exception mới đó. Nó sẽ truyền tới handler ở cấp ngoài, sau khi `finally` của câu lệnh hiện tại được thực hiện theo quy tắc.

## 4. `catch` được chọn theo kiểu thực tế và theo thứ tự

Java xét các `catch` theo thứ tự **từ trên xuống dưới** và chọn handler đầu tiên mà kiểu exception runtime tương thích với kiểu được khai báo.

```java
static void parse(String input) {
    try {
        Integer.parseInt(input);
    } catch (NumberFormatException ex) {
        System.out.println("Sai định dạng số");
    } catch (IllegalArgumentException ex) {
        System.out.println("Đối số không hợp lệ khác");
    }
}
```

`NumberFormatException` là subclass của `IllegalArgumentException`. Vì thế, handler cụ thể hơn cần đứng trước.

### 4.1. Lỗi sắp xếp `catch` từ rộng đến hẹp

Đoạn sau **không biên dịch**:

```java
try {
    Integer.parseInt("oops");
} catch (IllegalArgumentException ex) {
    System.out.println("Illegal argument");
} catch (NumberFormatException ex) { // Lỗi biên dịch: đã bị catch ở trên
    System.out.println("Number format");
}
```

Với `catch (IllegalArgumentException ex)` đứng trước, mọi `NumberFormatException` đã bị handler đó bắt. Handler `NumberFormatException` phía sau trở nên không thể đạt tới.

Vì vậy:

1. Xử lý subtype cụ thể trước khi xử lý superclass.
2. Đặt handler cho lỗi có thể phục hồi một cách có ý nghĩa lên trước handler mang tính tổng quát.
3. Không thêm `catch (Exception ex)` như một cách “bảo hiểm” mặc định nếu code không có chiến lược xử lý phù hợp.

### 4.2. Lựa chọn handler theo hợp đồng

Một `catch` tốt thường thực hiện một trong các việc: chuyển sự cố sang kết quả nghiệp vụ đã quy định, thử lại ở nơi có đủ thông tin và giới hạn retry, bọc exception để chuyển qua ranh giới abstraction, hoặc ghi thông tin có ích rồi truyền lỗi cho tầng có trách nhiệm.

Ví dụ, thiếu một tệp cấu hình **tùy chọn** có thể dẫn đến dùng giá trị mặc định. Nhưng thiếu tệp cấu hình **bắt buộc** không nên bị biến thành “không có dữ liệu” vì làm vậy sẽ che giấu lỗi vận hành.

## 5. Multi-catch: nhiều kiểu exception, một nhánh xử lý

Khi hai hoặc nhiều exception cần được xử lý **giống nhau**, Java cho phép khai báo một `catch` chứa các kiểu được ngăn cách bằng `|`:

```java
static int divide(String numerator, String denominator) {
    try {
        int a = Integer.parseInt(numerator);
        int b = Integer.parseInt(denominator);
        return a / b;
    } catch (NumberFormatException | ArithmeticException ex) {
        System.out.println("Input or divisor invalid: " + ex.getMessage());
        return 0; // Giá trị dự phòng chỉ phục vụ ví dụ
    }
}
```

`NumberFormatException` xuất hiện khi không phân tích được số nguyên; `ArithmeticException` xuất hiện khi chia số nguyên cho 0. Cả hai là unchecked exceptions, **không có quan hệ cha–con trực tiếp với nhau**, nên có thể đứng chung trong một multi-catch.

Trong ví dụ, `0` chỉ là **chính sách minh họa**, không phải khuyến nghị chung: nếu 0 cũng là kết quả hợp lệ, caller sẽ không biết phép chia thất bại. API thực tế nên chọn hợp đồng lỗi rõ ràng, chẳng hạn ném lại exception, trả kiểu kết quả phân biệt thành công/thất bại, hoặc xử lý tại ranh giới phù hợp.

### 5.1. Tránh lặp logic ở nhiều `catch`

Nếu viết hai khối có cùng nội dung:

```java
try {
    perform();
} catch (NumberFormatException ex) {
    reportInvalidInput(ex);
} catch (ArithmeticException ex) {
    reportInvalidInput(ex);
}
```

Có thể thay bằng:

```java
try {
    perform();
} catch (NumberFormatException | ArithmeticException ex) {
    reportInvalidInput(ex);
}
```

`perform` và `reportInvalidInput` đại diện cho mã ứng dụng; mục tiêu là cho thấy **cùng hành vi xử lý** có thể được viết một lần.

### 5.2. Multi-catch với checked exceptions

Multi-catch không chỉ dành cho unchecked exceptions. Hai kiểu checked độc lập như `IOException` và `SQLException` cũng có thể dùng chung:

```java
import java.io.IOException;
import java.sql.SQLException;

static void runIntegration() {
    try {
        readRemoteFile();    // throws IOException
        updateDatabase();    // throws SQLException
    } catch (IOException | SQLException ex) {
        throw new IllegalStateException("Integration failed", ex);
    }
}
```

Hai lời gọi `readRemoteFile` và `updateDatabase` là các phương thức minh họa có khai báo `throws` tương ứng. `IllegalStateException` ở đây giữ exception gốc làm **cause**; trong hệ thống thực tế, nên chọn exception nghiệp vụ/abstraction phù hợp hơn khi cần.

Không có một ưu tiên ngầm định giữa các kiểu trong cùng dấu `|`. Mỗi exception được bắt nếu kiểu runtime tương thích với **một trong các alternatives**.

## 6. Các ràng buộc khi viết multi-catch

### 6.1. Alternatives không được có quan hệ subtype với nhau

Đây là ví dụ **sai**:

```java
// Ví dụ không hợp lệ, được comment để tránh chạy nhầm:
// try {
//     Integer.parseInt("invalid");
// } catch (NumberFormatException | IllegalArgumentException ex) {
//     System.out.println(ex.getMessage());
// }
```

`NumberFormatException extends IllegalArgumentException`, nên hai kiểu không được xuất hiện cùng một union type trong `catch`. Thay vào đó, bắt `IllegalArgumentException` nếu thực sự muốn cùng xử lý mọi subtype của nó, hoặc dùng `NumberFormatException` nếu chỉ quan tâm lỗi parse.

Tương tự, `catch (IOException | Exception ex)` không hợp lệ vì `IOException` là subtype của `Exception`.

### 6.2. Mỗi alternative phải là kiểu exception có thể bắt

Các alternatives là các class types thuộc `Throwable` hoặc subclass của nó. Không thể viết `catch (String | IOException ex)`. Không thể dùng một type variable `T extends Throwable` trực tiếp làm catch type.

Kiểu được sử dụng phải phù hợp với các exception mà body `try` có thể ném theo quy tắc phân tích tại compile time. Ví dụ, compiler sẽ báo khi bắt một **checked exception cụ thể không thể được ném** bởi đoạn code liên quan. Với unchecked exceptions, compiler không yêu cầu chứng minh khả năng được ném theo cùng cách.

### 6.3. Tham số multi-catch là `final` ngầm định

`ex` trong multi-catch **không thể được gán lại**:

```java
try {
    Integer.parseInt("oops");
} catch (NumberFormatException | ArithmeticException ex) {
    System.out.println(ex.getMessage());
    // ex = new IllegalArgumentException("other"); // Lỗi biên dịch
}
```

Compiler coi tham số multi-catch là `implicitly final`, kể cả khi không viết từ khóa `final`. Điều này giúp giữ nguyên tham chiếu tới exception mà handler đang xử lý và liên quan tới khả năng **precise rethrow** ở mục 7.

### 6.4. Kiểu khai báo của tham số là một kiểu chung

Với `catch (IOException | SQLException ex)`, mã bên trong không thể tùy tiện gọi những method chỉ có riêng trên `SQLException`. Compiler xác định kiểu chung phù hợp (theo *least upper bound* của các alternatives); với hai kiểu này, các phương thức chung từ `Exception`/`Throwable`, như `getMessage()` hoặc `getCause()`, có thể được dùng.

```java
try {
    runRemoteOperation(); // Có thể ném IOException hoặc SQLException
} catch (IOException | SQLException ex) {
    System.err.println(ex.getMessage());
    // ex.getSQLState(); // Không thể gọi trực tiếp với kiểu chung
}
```

Nếu xử lý thật sự khác nhau, hãy dùng **hai catch riêng biệt** thay vì ép chúng vào một nhánh rồi kiểm tra lại `instanceof` phức tạp.

## 7. Ném lại exception và precise rethrow

Đôi khi handler chỉ bổ sung thông tin, rồi ném lại exception để tầng gọi xử lý. Java hỗ trợ khả năng **precise rethrow** đối với một số exception parameters.

```java
import java.io.IOException;
import java.sql.SQLException;

static void loadData() throws IOException, SQLException {
    try {
        readRemoteFile(); // throws IOException
        updateDatabase(); // throws SQLException
    } catch (Exception ex) {
        System.err.println("Data operation failed: " + ex.getMessage());
        throw ex;
    }
}
```

Trong ví dụ này, `ex` không bị gán lại nên là **effectively final**. Compiler có thể phân tích các checked exception thực sự có thể thoát khỏi `try`, cho phép khai báo `throws IOException, SQLException` thay vì bắt buộc nới rộng thành `throws Exception`.

Với multi-catch, tham số `ex` vốn **implicitly final**, nên cũng có thể ném lại:

```java
static void loadData() throws IOException, SQLException {
    try {
        readRemoteFile();
        updateDatabase();
    } catch (IOException | SQLException ex) {
        throw ex;
    }
}
```

Các phương thức `readRemoteFile` và `updateDatabase` được giả định đã khai báo checked exceptions như trên; hai đoạn `loadData` là **hai cách triển khai thay thế**, không cùng tồn tại trong một class với cùng chữ ký.

Precise rethrow không có nghĩa Java đoán loại exception từ bất kỳ biến nào. Nó dựa trên quy tắc kiểm tra exception của `try` và trạng thái `final`/`effectively final` của **catch parameter**; nếu gán lại tham số uni-catch, lợi ích suy luận chính xác này có thể không còn áp dụng.

## 8. `finally` thực sự chạy khi nào?

`finally` chạy sau khi `try` hoàn tất bình thường hoặc đột ngột, và sau `catch` nếu một handler được chọn. Điều này gồm các tình huống như ném exception, `return`, `break` và `continue`.

### 8.1. `finally` vẫn chạy trước khi trả kết quả

```java
static int parsePositive(String raw) {
    try {
        int value = Integer.parseInt(raw);
        if (value <= 0) {
            return 0;
        }
        return value;
    } catch (NumberFormatException ex) {
        return 0;
    } finally {
        System.out.println("Parse attempt complete");
    }
}
```

`finally` chạy trước khi method thực sự trả kết quả đã chọn. Nếu input hợp lệ, handler `catch` bị bỏ qua nhưng `finally` vẫn chạy.

### 8.2. `finally` chạy cả khi không có `catch` phù hợp

```java
static void fail() {
    try {
        throw new IllegalStateException("Failed");
    } finally {
        System.out.println("Cleanup notification");
    }
}
```

Nếu gọi `fail()`, dòng `Cleanup notification` được in ra, rồi exception `IllegalStateException` tiếp tục truyền tới caller. `finally` không “nuốt” exception khi chính nó hoàn tất bình thường.

### 8.3. Tại sao không nói `finally` “luôn luôn” chạy theo nghĩa tuyệt đối?

`finally` có bảo đảm mạnh **trong quá trình điều khiển Java thông thường**, nhưng không phải biện pháp đảm bảo tuyệt đối khi tiến trình hoặc JVM không tiếp tục thực thi. Ví dụ, nếu gọi `Runtime.getRuntime().halt(...)` hoặc JVM bị kết thúc đột ngột, khối `finally` có thể không chạy. Không sử dụng `finally` như cơ chế duy nhất bảo đảm thực thi nghiệp vụ bắt buộc trước các sự kiện mất tiến trình.

Tương tự, nếu luồng bị kẹt vô hạn trong `try` và không rời khỏi đó, nó cũng chưa tới `finally`.

## 9. Cạm bẫy: `return` hoặc `throw` bên trong `finally`

Một `finally` hoàn tất **đột ngột** có thể làm mất lý do hoàn tất trước đó của `try` hoặc `catch`. Đây là một điểm quan trọng trong JLS 14.20.2.

### 9.1. `return` trong `finally` ghi đè kết quả

```java
static int surprising() {
    try {
        return 1;
    } finally {
        return 2;
    }
}

System.out.println(surprising()); // 2
```

Đây là đoạn mã hợp lệ về cú pháp nhưng **không nên áp dụng**. Lệnh `return 2` khiến kết quả `return 1` đang chờ bị thay thế.

### 9.2. Ném lỗi mới từ `finally` có thể che lỗi gốc

```java
static void risky() {
    try {
        throw new IllegalArgumentException("Original problem");
    } finally {
        throw new IllegalStateException("Failure in cleanup");
    }
}
```

Exception được truyền ra từ `risky()` là `IllegalStateException`. Exception `IllegalArgumentException` ban đầu **không tự động được thêm** vào `getSuppressed()` chỉ vì mã sử dụng `finally` thủ công.

Khi logic trong `finally` có thể thất bại, cần thiết kế để tránh che lỗi nghiệp vụ quan trọng. Với tài nguyên `AutoCloseable`, **`try-with-resources`** giải quyết trường hợp lỗi từ body và `close()` một cách an toàn và có quy tắc hơn.

### 9.3. Khuyến nghị sử dụng `finally` hiện nay

Dùng `finally` cho những việc cần thực hiện khi rời phạm vi nhưng **không phải việc đóng tài nguyên `AutoCloseable` có thể chuyển sang `try-with-resources`**, chẳng hạn cập nhật một chỉ số đo lường hoặc thông báo việc kết thúc một nỗ lực. Ngay cả công việc này cũng phải xét khả năng ném exception và tác dụng phụ.

Tránh `return`, `throw` và logic nghiệp vụ quan trọng dễ thất bại trong `finally`. Không xem `finally` là nơi “sửa kết quả” sau khi phương thức đã quyết định thành công hay thất bại.

## 10. `try-with-resources`: cách quản lý tài nguyên nên ưu tiên

Tên chương có yếu tố **vòng đời tài nguyên**. Trong Java 27, cách thông dụng để giải phóng file handles, streams, readers hoặc các đối tượng `AutoCloseable` là **`try-with-resources`**, không phải tự viết một chuỗi `close()` trong `finally`.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String firstLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Ở đây:

1. `Files.newBufferedReader` tạo resource.
2. Body đọc dòng đầu tiên; `readLine()` có thể trả `null` nếu tệp rỗng.
3. Resource được `close()` tự động khi rời `try`, kể cả khi body ném exception hoặc `return`.
4. Nếu có nhiều resources, chúng được đóng **theo thứ tự ngược với thứ tự khai báo**.

Đây là cơ chế ổn định trong Java hiện đại, giúp giảm lỗi quên đóng và tránh phải tự quản lý hai exception cùng lúc.

### 10.1. Có thể kết hợp `catch` và `finally`

```java
static String readHeader(Path path) {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    } catch (IOException ex) {
        throw new java.io.UncheckedIOException("Cannot read header", ex);
    } finally {
        System.out.println("Read attempt finished");
    }
}
```

Với `try-with-resources` như trên, những resources được đóng **trước khi chạy các `catch` và `finally` gắn với câu lệnh đó**. `catch (IOException ex)` có thể bắt lỗi phát sinh từ việc mở, đọc hoặc đóng reader theo những quy tắc tương ứng.

Nếu chỉ cần đọc toàn bộ nội dung tệp một lần, `Files.readString(path)` tự xử lý việc mở/đóng resources ở bên trong; caller không cần tạo thêm `finally` để đóng tài nguyên không sở hữu trực tiếp.

### 10.2. Resource tham chiếu effectively final

Java hiện hành còn cho phép dùng biến resource đã khai báo trước nếu biến đó `final` hoặc **effectively final**:

```java
BufferedReader reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
```

Ví dụ này vẫn cần được đặt trong một method khai báo hoặc xử lý `IOException` thích hợp. Đây là cú pháp đã ổn định, không cần viết lại theo mẫu cleanup thủ công để tương thích Java 27.

## 11. Suppressed exceptions: khác với `cause`

Với `try-with-resources`, có tình huống **body ném exception** và **`close()` cũng ném exception**. Java giữ lỗi từ body làm exception chính và đính kèm lỗi khi đóng vào danh sách **suppressed exceptions**.

```java
import java.io.IOException;

static final class BrokenResource implements AutoCloseable {
    @Override
    public void close() throws IOException {
        throw new IOException("Failure while closing");
    }
}

static void demonstrateSuppression() {
    try (BrokenResource resource = new BrokenResource()) {
        throw new IllegalStateException("Failure in body");
    } catch (IllegalStateException ex) {
        System.out.println(ex.getMessage());           // Failure in body
        System.out.println(ex.getSuppressed().length);  // 1
        System.out.println(ex.getSuppressed()[0].getMessage());
        // Failure while closing
    } catch (IOException ex) {
        throw new java.io.UncheckedIOException(ex);
    }
}
```

Điểm khác biệt:

| Cơ chế | Dùng khi | Cách xem |
| --- | --- | --- |
| **Cause** | Một exception xảy ra **vì** một exception khác và được bọc/chuyển tầng | `ex.getCause()` |
| **Suppressed** | Có nhiều exception liên quan tới quá trình xử lý, nhưng chỉ một exception được truyền làm lỗi chính (đặc biệt khi đóng resources) | `ex.getSuppressed()` |

`Throwable` hỗ trợ `initCause`/các constructors nhận cause và `addSuppressed`/`getSuppressed`. Thông thường hãy để `try-with-resources` tự xử lý suppressed exceptions; không tự thêm suppressed một cách tùy tiện.

Nếu **body hoàn tất bình thường** nhưng `close()` thất bại, exception của việc đóng có thể trở thành exception chính. Suppression không có nghĩa mọi lỗi của `close()` đều luôn bị giấu đi.

## 12. Multi-catch kết hợp với `finally` và `try-with-resources`

Một API đọc tệp có thể phân biệt một số tình huống **không thể mở tệp** với các lỗi I/O còn lại:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

static String readRequiredTitle(Path path) {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        String title = reader.readLine();
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Title missing");
        }
        return title;
    } catch (NoSuchFileException | AccessDeniedException ex) {
        // Hai lỗi có cùng chính sách: không thể mở tệp bắt buộc.
        throw new UncheckedIOException("Required file unavailable", ex);
    } catch (IOException ex) {
        // Lỗi I/O khác, ví dụ đọc dữ liệu hoặc đóng tài nguyên thất bại.
        throw new UncheckedIOException("Unable to read title", ex);
    } finally {
        // Ví dụ thông báo kết thúc; không dùng để đóng reader.
        System.out.println("Read attempt complete");
    }
}
```

Trong ví dụ:

- `NoSuchFileException` và `AccessDeniedException` là các exception class độc lập, cùng thuộc nhánh `IOException`, nên có thể dùng chung multi-catch.
- Handler `IOException` rộng hơn phải đứng **sau** handler cụ thể.
- Lỗi dữ liệu nghiệp vụ `IllegalArgumentException` không bị `catch (IOException)` nuốt.
- `UncheckedIOException` giữ nguyên cause `IOException`; caller có thể quyết định xử lý tiếp hoặc chuyển thành phản hồi lỗi phù hợp ở tầng biên.
- Resource được đóng trước khi các handler và `finally` ở đây chạy.

Thông báo trong `finally` chỉ nhằm minh họa luồng thực thi. Trong ứng dụng production, logging/metrics nên có trách nhiệm và mức độ phù hợp; tránh in trực tiếp đường dẫn hoặc thông tin nhạy cảm vào nơi không được kiểm soát.

## 13. Chọn cách xử lý exception ở ranh giới API

### 13.1. Khi nào catch và xử lý tại chỗ?

Catch tại chỗ khi method **thực sự biết** cách xử lý:

- Có giá trị mặc định đã được hợp đồng nghiệp vụ cho phép, ví dụ tệp cấu hình tùy chọn không tồn tại.
- Có đường phục hồi rõ ràng, như sử dụng bản sao lưu đã xác minh.
- Cần chuyển exception kỹ thuật thành exception của tầng API, có giữ cause.
- Cần làm thêm một thao tác đã được quy định rồi rethrow.

Nếu không có chiến lược phục hồi, có thể để exception truyền ra thông qua `throws` thay vì bắt rồi bỏ qua.

### 13.2. Giữ lại cause khi chuyển tầng

Ví dụ:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String loadText(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException ex) {
        throw new UncheckedIOException("Unable to load document", ex);
    }
}
```

Không thay bằng `throw new IllegalStateException("Unable to load document");` nếu việc mất cause làm người vận hành không tìm được sự cố gốc. Tránh vừa log stack trace ở mọi tầng vừa ném lại, vì điều đó thường gây log lặp và khó phân tích.

### 13.3. `catch (Exception)`, `catch (RuntimeException)` và `catch (Throwable)`

`catch (Exception)` có thể hợp lý ở một **ranh giới điều phối** (như xử lý một tác vụ mà không để tác vụ khác dừng), nếu có chính sách lỗi cụ thể. Nhưng nó không nên là phản xạ cho mọi `try`.

`catch (RuntimeException)` chủ yếu bắt các lỗi unchecked trong nhánh đó. Nó không bao gồm checked exception như `IOException` và không bao gồm `Error`.

`catch (Throwable)` bắt cả `Error`, dễ dẫn đến cố tiếp tục khi trạng thái runtime không còn đáng tin cậy. Tránh dùng trong xử lý nghiệp vụ thông thường, trừ các trường hợp đặc biệt được thiết kế cẩn thận bởi framework/runtime.

## 14. Những lỗi triển khai thường gặp

| Cách làm | Vấn đề | Thay thế hợp lý |
| --- | --- | --- |
| `catch (Exception ex) {}` | Nuốt lỗi, không còn dấu vết thất bại | Chỉ catch khi có chính sách xử lý; giữ cause/rethrow khi cần |
| `catch (Exception)` trước `catch (IOException)` | Handler sau có thể không thể đạt tới | Đặt handler cụ thể trước handler rộng |
| `catch (NumberFormatException \| IllegalArgumentException ex)` | Alternatives có quan hệ subtype | Chọn loại phù hợp hoặc tách logic có mục đích |
| Gán lại biến `ex` trong multi-catch | Tham số implicitly final | Giữ nguyên exception gốc |
| `return` trong `finally` | Ghi đè return/exception đang chờ | Hoàn tất logic quyết định kết quả trong `try` hoặc `catch` |
| `throw` mới trong `finally` | Có thể che lỗi gốc, không tự suppression | Dùng `try-with-resources` cho `AutoCloseable` |
| Đóng reader thủ công trong `finally` | Dễ bỏ sót và xử lý khó khi `close()` cũng ném lỗi | `try (var reader = ... )` |
| Catch và trả `null` vô điều kiện | Người dùng không phân biệt lỗi và dữ liệu rỗng | Dùng hợp đồng lỗi hoặc kiểu kết quả rõ ràng |
| Log rồi rethrow ở mọi tầng | Trùng stack trace, tăng nhiễu giám sát | Log có ngữ cảnh ở ranh giới có trách nhiệm |
| Bỏ cause khi bọc exception | Mất nguồn gốc sự cố | Chuyển cause vào constructor phù hợp |
| Dùng exception cho nhánh nghiệp vụ bình thường | Khó đọc, tốn chi phí và tạo lỗi giả | Kiểm tra điều kiện trực tiếp khi phù hợp |
| Cố catch `Error` để tiếp tục | Có thể che lỗi JVM nghiêm trọng | Để runtime xử lý, trừ thiết kế chuyên biệt |
| Coi `finally` chắc chắn chạy khi tiến trình bị kill | Không có bảo đảm trong trường hợp dừng bất thường | Thiết kế khôi phục/durable state ngoài tiến trình |

## 15. Ví dụ tổng hợp tự chạy: `try`, multi-catch, `return` và `finally`

Đặt đoạn dưới vào file `Demo.java`. Ví dụ cố tình không truy cập file hay database, nên kết quả xác định và chạy được chỉ với JDK 27:

```java
public class Demo {
    static int divide(String left, String right) {
        try {
            System.out.println("Starting calculation");
            int a = Integer.parseInt(left);
            int b = Integer.parseInt(right);
            return a / b;
        } catch (NumberFormatException | ArithmeticException ex) {
            System.out.println(
                    "Cannot calculate: " + ex.getClass().getSimpleName());
            return -1; // Quy ước chỉ để minh họa
        } finally {
            System.out.println("Calculation attempt finished");
        }
    }

    public static void main(String[] args) {
        System.out.println("Result: " + divide("20", "4"));
        System.out.println("---");

        System.out.println("Result: " + divide("wrong", "4"));
        System.out.println("---");

        System.out.println("Result: " + divide("20", "0"));
    }
}
```

Chạy:

```shell
javac Demo.java
java Demo
```

Kết quả:

```text
Starting calculation
Calculation attempt finished
Result: 5
---
Starting calculation
Cannot calculate: NumberFormatException
Calculation attempt finished
Result: -1
---
Starting calculation
Cannot calculate: ArithmeticException
Calculation attempt finished
Result: -1
```

Điểm cần quan sát:

1. Khi phép chia hợp lệ, không có `catch` nào chạy.
2. Khi dữ liệu là `"wrong"`, `Integer.parseInt` ném `NumberFormatException`; phần phép chia không được thực hiện.
3. Khi mẫu số là `"0"`, phép chia số nguyên ném `ArithmeticException`.
4. Cả hai lỗi được xử lý trong **một multi-catch** vì dùng cùng chính sách minh họa.
5. `finally` chạy trước khi phương thức hoàn tất `return` ở cả ba nhánh.

Trong API thực tế, `-1` có thể là kết quả hợp lệ; nên tránh dùng một số nguyên “đặc biệt” để báo lỗi nếu hợp đồng không phân biệt được thất bại với thành công.

## 16. Checklist review và kiểm thử

Khi review mã có exception handling trong Java 27:

1. **`try` có bao quanh đúng thao tác cần bảo vệ không?** Tránh bao quá rộng khiến người đọc không biết lệnh nào thực sự ném lỗi.
2. **Checked exceptions được catch hoặc khai báo đúng chưa?** Không chuyển tất cả thành unchecked chỉ để giảm từ khóa.
3. **Các `catch` đã từ cụ thể đến tổng quát chưa?** Đảm bảo không có handler bị che khuất.
4. **Multi-catch có dùng cho cùng một chính sách xử lý không?** Không gộp các sự cố khác bản chất chỉ để giảm dòng.
5. **Các alternatives có quan hệ subtype không?** Nếu có, union catch không hợp lệ.
6. **Handler có làm mất cause hoặc suppressed exceptions không?** Giữ ngữ cảnh khi chuyển tầng.
7. **`finally` có chứa `return` hoặc `throw` không?** Kiểm tra nguy cơ che kết quả/lỗi gốc.
8. **Tài nguyên `AutoCloseable` có dùng `try-with-resources` không?** Xét cả lỗi `close()` và thứ tự đóng.
9. **Handler có vô tình nuốt exception không?** Đặc biệt khi trả `null`, `0` hoặc collection rỗng.
10. **Log có đủ ngữ cảnh và không lộ bí mật không?** Tránh log trùng ở nhiều tầng.
11. **Đã kiểm thử đường thành công và lỗi chưa?** Bao gồm thiếu file, lỗi quyền truy cập, lỗi parse, lỗi resource closing, return trong `try` và lỗi trong `catch`.
12. **Có phụ thuộc `finally` để bảo đảm việc sống còn của dữ liệu không?** Xem xét riêng trường hợp tiến trình dừng đột ngột.

## 17. Tổng kết

`try` xác định phạm vi mã cần bảo vệ; `catch` chọn handler đầu tiên tương thích với **kiểu exception thực tế**; `finally` thực hiện công việc khi rời khỏi cấu trúc `try` theo quy tắc hoàn tất của Java. Khi nhiều exception có cùng chính sách xử lý, **multi-catch** cho phép dùng một nhánh `catch (A | B ex)`, miễn là các kiểu thay thế không có quan hệ subtype và tham số exception không bị gán lại.

Hai điều dễ gây lỗi cần ghi nhớ: **`finally` vẫn chạy khi `return`/`throw`**, nhưng chính `return` hoặc `throw` trong `finally` có thể **ghi đè** kết quả hay exception gốc; và **`catch` không tự đồng nghĩa với phục hồi** — bắt lỗi mà không có chính sách xử lý thường chỉ che giấu sự cố.

Trong Java 27, với streams, readers, sockets hay các resources `AutoCloseable`, hãy **ưu tiên `try-with-resources`**. Cơ chế này đóng resources theo quy tắc rõ ràng và lưu lỗi đóng thành suppressed exceptions khi cần. Thiết kế exception handling hiệu quả không phải là viết nhiều `catch` nhất, mà là giữ đúng ranh giới trách nhiệm, giữ nguyên thông tin lỗi và làm rõ hợp đồng cho caller.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — §11 Exceptions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-11.html) — phân loại checked/unchecked, quy tắc kiểm tra và truyền exception.
- [Java Language Specification, Java SE 27 — §14.20 The try Statement](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.20) — cú pháp `try`, `catch`, `finally` và multi-catch.
- [Java Language Specification, Java SE 27 — §14.20.1 Execution of try-catch](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.20.1) — lựa chọn handler theo thứ tự và kiểu exception.
- [Java Language Specification, Java SE 27 — §14.20.2 Execution of try-finally](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.20.2) — quy tắc hoàn tất đột ngột và ảnh hưởng của `finally`.
- [Java Language Specification, Java SE 27 — §14.20.3 Try-with-resources](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.20.3) — quản lý resource, thứ tự đóng và suppression.
- [Java Language Specification, Java SE 27 — §11.2.2 Exception Analysis of Statements](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-11.html#jls-11.2.2) — kiểm tra checked exceptions và precise rethrow.
- [Throwable — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Throwable.html) — `getCause()`, `getSuppressed()`, `addSuppressed()`.
- [AutoCloseable — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/AutoCloseable.html) — hợp đồng `close()` và `try-with-resources`.
- [Files — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html) — `newBufferedReader` và `readString`.

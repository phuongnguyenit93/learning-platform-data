# Phân tích các ngoại lệ thực sự phát sinh từ khối `try` trong Java: precise rethrow

## 1. Ý nghĩa và phạm vi của bài

Khi xử lý một lỗi trong `catch`, đôi khi chương trình cần ghi log, bổ sung ngữ cảnh rồi **ném lại chính ngoại lệ đó** để tầng gọi phía trên quyết định cách phục hồi:

```java
try {
    performOperation();
} catch (Exception ex) {
    logFailure(ex);
    throw ex;
}
```

Đây là **đoạn minh họa đặt trong phương thức**; `performOperation` và `logFailure` chỉ đại diện cho các phương thức của ứng dụng, không phải API Java có sẵn.

Câu hỏi quan trọng: nếu khối `try` chỉ có thể phát sinh các *checked exception* loại `IOException` và `SQLException`, tại sao một biến được khai báo `Exception ex` trong `catch` vẫn có thể được ném lại mà phương thức chỉ cần `throws IOException, SQLException`, thay vì `throws Exception`?

Từ **Java 7**, ngôn ngữ hỗ trợ **precise rethrow** (ném lại ngoại lệ với phân tích kiểu chính xác hơn): trình biên dịch xem xét những ngoại lệ *checked* mà khối `try` **có khả năng ném ra theo mã nguồn và chữ ký phương thức**, đồng thời xem ngoại lệ nào có thể lọt tới `catch`, để quyết định kiểu ngoại lệ cần khai báo khi `throw ex;`.

Tính năng này **vẫn áp dụng trong Java hiện đại**. Nó liên quan trực tiếp đến xử lý ngoại lệ và kiểm tra kiểu tại thời điểm biên dịch; không phải API đã bị loại bỏ hay kỹ thuật legacy.

> Phân biệt từ “thực sự”: ở đây là những loại ngoại lệ mà trình biên dịch xác định **có thể phát sinh từ khối `try` theo phân tích tĩnh**, chứ **không phải** danh sách ngoại lệ đã xuất hiện ở một lần chạy, hoặc chỉ những ngoại lệ tình cờ xảy ra khi chạy thử.

## 2. Nền tảng: checked và unchecked exception

Java phân biệt:

| Loại | Ví dụ | Quy tắc khai báo/bắt |
| --- | --- | --- |
| Checked exception | `IOException`, `SQLException`, `ParseException` | Thông thường phải được bắt bằng `catch` hoặc khai báo trong `throws` |
| Unchecked exception | `IllegalArgumentException`, `NullPointerException`, `IllegalStateException` | Là các lớp con của `RuntimeException`; không bị bắt buộc khai báo `throws` |
| Lỗi nghiêm trọng của JVM | `OutOfMemoryError`, `StackOverflowError` | Là các lớp con của `Error`; cũng không thuộc cơ chế bắt buộc khai báo checked |

`Exception` là lớp cha của nhiều ngoại lệ checked và cũng là lớp cha của `RuntimeException`. Do đó `catch (Exception ex)` có thể bắt cả hai nhóm này, nhưng **không bắt `Error`**.

Khi khai báo:

```java
static void readFile() throws java.io.IOException {
    // Nội dung thực thi đọc tệp
}
```

trình biên dịch phải coi `readFile()` có thể ném `IOException` tại vị trí được gọi. Dù ở một lần chạy hàm không ném lỗi, **kiểu checked trong chữ ký vẫn là một phần của phân tích**. Ngược lại, một ngoại lệ unchecked vẫn có thể xuất hiện từ nhiều câu lệnh dù không được ghi trong `throws`.

Để hiểu precise rethrow, hãy theo dõi **đường đi của các loại checked exception** qua `try` và các `catch` thay vì đoán theo giá trị thực tế của biến ở runtime.

## 3. Trình biên dịch phân tích các ngoại lệ từ `try` như thế nào?

Xét tình huống:

```java
static void load(boolean fail) throws java.io.IOException {
    if (fail) {
        throw new java.io.IOException("file");
    }
}

static void query(boolean fail) throws java.sql.SQLException {
    if (fail) {
        throw new java.sql.SQLException("db");
    }
}
```

Khi gọi hai phương thức trong cùng `try`:

```java
try {
    load(failFile);
    query(failDb);
} catch (Exception ex) {
    throw ex;
}
```

trình biên dịch xét được hai kiểu checked cần quan tâm:

- `load(...)` có thể ném `IOException`.
- `query(...)` có thể ném `SQLException`.

Với `catch (Exception ex)` và biến `ex` **không bị gán lại**, Java có thể suy luận rằng ném lại `ex` không cần khai báo mọi loại checked exception thuộc họ `Exception`. Phương thức chỉ cần:

```java
static void run(boolean failFile, boolean failDb)
        throws java.io.IOException, java.sql.SQLException {
    try {
        load(failFile);
        query(failDb);
    } catch (Exception ex) {
        throw ex; // Precise rethrow
    }
}
```

Ba đoạn trên thuộc **cùng một lớp Java**; phần chạy hoàn chỉnh được đưa ở mục 5.

Có thể mô hình hóa phép phân tích:

```text
Khối try
  |
  +-- load(...)  --------> IOException (checked)
  |
  +-- query(...) --------> SQLException (checked)
  |
  +-- Các lỗi unchecked có thể xảy ra
  |
  v
catch (Exception ex)
  |
  +-- ghi log / kiểm tra / bổ sung ngữ cảnh
  |
  +-- throw ex;   (ex không bị gán lại)
       |
       +-- checked: IOException, SQLException
       +-- unchecked: không bị bắt buộc khai báo throws
```

**Không có bước nào cần chạy chương trình để thu thập danh sách ngoại lệ.** Compiler phân tích câu lệnh, nhánh mã và đặc tả của các phương thức/constructor có thể gọi đến. Ngoại lệ được khai báo rộng trong `throws` của một phương thức được gọi cũng ảnh hưởng tới phân tích, ngay cả khi phần cài đặt hiện tại thường chỉ ném một kiểu con hẹp hơn.

## 4. Điều kiện để precise rethrow có hiệu lực

### 4.1. Phải ném lại chính tham số được bắt

Đối với cú pháp `catch (Exception ex)`, `throw ex;` là thao tác ném lại cùng đối tượng ngoại lệ. Compiler có thể phân tích chính xác hơn khi **tham số bắt ngoại lệ là `final` hoặc không bị gán lại** trong thân `catch`.

```java
try {
    load(failFile);
    query(failDb);
} catch (Exception ex) {
    System.err.println(ex.getMessage());
    throw ex; // ex không bị gán lại
}
```

Các thao tác như đọc `ex.getMessage()`, ghi log hay gán giá trị tham chiếu `ex` cho một biến khác **không phải** phép gán lại `ex`. Tuy nhiên, gán lại chính biến `ex` làm mất điều kiện quan trọng của precise rethrow.

### 4.2. Không gán lại tham số `catch`

Đoạn sau **cố ý không biên dịch** với chữ ký chỉ khai báo hai ngoại lệ cụ thể:

```java
// Ví dụ sai: đặt trong cùng lớp với load/query ở trên.
static void badRun(boolean failFile, boolean failDb)
        throws java.io.IOException, java.sql.SQLException {
    try {
        load(failFile);
        query(failDb);
    } catch (Exception ex) {
        ex = new Exception("replaced");
        throw ex; // Lỗi checked: Exception chưa được xử lý/khai báo
    }
}
```

Ở đây `ex` đã bị thay bằng một đối tượng `Exception` khác, nên không thể áp dụng quy tắc suy luận checked exception hẹp cho `throw ex;`. Theo kiểu khai báo của biến, compiler phải xét `Exception` nói chung. **Không sửa bằng cách thêm `throws Exception` chỉ để qua biên dịch** nếu hợp đồng API vốn chỉ định `IOException` và `SQLException`; hãy giữ nguyên ngoại lệ gốc hoặc thiết kế việc chuyển đổi lỗi một cách có chủ đích.

Có thể viết rõ `catch (final Exception ex)` để ngăn việc gán lại ngay từ lúc biên dịch; precise rethrow cũng hoạt động khi không khai báo `final` miễn là tham số không bị gán lại.

### 4.3. Không nhầm “ném lại” với “ném lỗi mới”

Hai câu lệnh có ý nghĩa khác nhau:

```java
throw ex;                           // Ném lại đối tượng ngoại lệ gốc
// throw new Exception(ex);          // Tạo một ngoại lệ mới, kiểu checked Exception
// throw new IllegalStateException(ex); // Bọc lỗi bằng unchecked exception mới
```

Dòng `throw ex` giữ đối tượng và nguyên nhân gốc của lỗi. Khi tạo `new Exception(ex)`, kiểu ném là `Exception` mới; precise rethrow của tham số `catch` **không áp dụng** cho đối tượng mới. Muốn chuyển sang lỗi ở một tầng trừu tượng cao hơn, nên chọn kiểu ngoại lệ phản ánh hợp đồng API và giữ `cause`, ví dụ `new MyServiceException("...", ex)` khi hệ thống có định nghĩa kiểu đó.

## 5. Chương trình đầy đủ: quan sát phân tích tĩnh và hành vi thực tế

Tạo tệp **`PreciseRethrowDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class PreciseRethrowDemo {

    static void load(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("file");
        }
    }

    static void query(boolean fail) throws SQLException {
        if (fail) {
            throw new SQLException("db");
        }
    }

    // Chỉ khai báo hai checked exception đến từ khối try.
    static void run(boolean failFile, boolean failDb)
            throws IOException, SQLException {
        try {
            load(failFile);
            query(failDb);
        } catch (Exception ex) {
            System.out.println("log: "
                    + ex.getClass().getSimpleName());
            throw ex; // ex không bị gán lại => precise rethrow
        }
    }

    public static void main(String[] args) {
        for (int i = 0; i < 3; i++) {
            try {
                run(i == 1, i == 2);
                System.out.println("OK");
            } catch (IOException ex) {
                System.out.println("caught IOException");
            } catch (SQLException ex) {
                System.out.println("caught SQLException");
            }
        }
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac -encoding UTF-8 PreciseRethrowDemo.java
java PreciseRethrowDemo
```

**Stdout chính xác:**

```text
OK
log: IOException
caught IOException
log: SQLException
caught SQLException
```

Diễn biến theo từng vòng lặp:

1. `i = 0`: cả hai cờ lỗi là `false`, không có ngoại lệ; in `OK`.
2. `i = 1`: `load(true)` ném `IOException`; `query(...)` không được chạy. Khối `catch (Exception ex)` ghi log rồi ném lại; `main` bắt `IOException`.
3. `i = 2`: `load(false)` thành công, `query(true)` ném `SQLException`; khối `catch` ghi log rồi ném lại; `main` bắt `SQLException`.

**Điểm quyết định:** mặc dù trong mỗi lần chạy chỉ có tối đa một ngoại lệ nảy sinh, chữ ký của `run` vẫn phải bao quát **cả hai khả năng checked** do phân tích tĩnh của compiler. Vì thế `run` không thể chỉ khai báo kiểu lỗi đã thấy ở lần chạy thử.

## 6. Quan hệ với `multi-catch` và thứ tự `catch`

Java 7 cũng cho phép **multi-catch** để xử lý nhiều kiểu ngoại lệ bằng cùng một nhánh:

```java
static void runMulti(boolean failFile, boolean failDb)
        throws java.io.IOException, java.sql.SQLException {
    try {
        load(failFile);
        query(failDb);
    } catch (java.io.IOException | java.sql.SQLException ex) {
        System.err.println("Operation failed: "
                + ex.getClass().getSimpleName());
        throw ex;
    }
}
```

Biến ngoại lệ trong multi-catch **không thể bị gán lại**. Compiler biết các nhánh lỗi được nêu cụ thể là `IOException` hoặc `SQLException`. Phần thân phía trên cũng chỉ minh họa trong cùng lớp với `load/query`.

So sánh:

| Cách viết | Khi nào phù hợp | Ảnh hưởng đến phân tích |
| --- | --- | --- |
| `catch (Exception ex) { throw ex; }` | Cần lớp bao quát để ghi log và ném lại, nhưng muốn chữ ký checked chính xác | Precise rethrow có thể giới hạn checked exception theo `try`, nếu tham số không bị gán lại |
| `catch (IOException | SQLException ex) { throw ex; }` | Muốn nêu rõ hai loại được xử lý cùng nhau | Các kiểu được liệt kê tường minh; biến multi-catch không gán lại được |
| `catch (IOException ex) { ... } catch (SQLException ex) { ... }` | Cần cách phục hồi hoặc thông điệp khác nhau cho từng lỗi | Mỗi nhánh xử lý loại tương ứng |

`catch` được xét từ trên xuống dưới. **Nhánh rộng đặt trước nhánh hẹp sẽ làm nhánh hẹp không thể tới**, chẳng hạn:

```java
// Không biên dịch: nhánh IOException đã bị Exception bắt trước.
try {
    load(true);
} catch (Exception ex) {
    System.out.println("broad");
} catch (java.io.IOException ex) {
    System.out.println("narrow");
}
```

Đồng thời, trong multi-catch không được dùng hai kiểu mà một kiểu là lớp con của kiểu kia, ví dụ `catch (IOException | Exception ex)`: nhánh `IOException` bị kiểu `Exception` bao trùm. Hãy khai báo các kiểu không có quan hệ kế thừa chồng lấn, và đặt `catch` cụ thể trước `catch` rộng nếu có nhiều nhánh.

## 7. “Có thể ném ra” được tính ở những vị trí nào?

Để biết kiểu checked nào thực sự được tính vào phân tích, hãy liệt kê nguồn ngoại lệ theo **đúng khối `try`**:

| Nguồn trong `try` | Ví dụ | Phân tích compiler |
| --- | --- | --- |
| Lệnh `throw` trực tiếp | `throw new IOException("x");` | Có thể phát sinh `IOException` |
| Gọi một phương thức | `Files.readString(path)` | Xem checked exception trong chữ ký được gọi, ví dụ `IOException` |
| Khởi tạo đối tượng | `new FileInputStream(path)` | Constructor có thể ném checked exception theo chữ ký |
| Phương thức bên trong một nhánh điều kiện | `if (flag) read();` | Compiler xét đường chạy có thể đi vào nhánh; không chỉ nhìn giá trị `flag` ở một lần thử |
| Tài nguyên của `try-with-resources` | Mở, đọc, đóng tài nguyên | Checked exception từ khởi tạo, thân `try` **và `close()`** có thể liên quan |
| Gọi hàm qua API trả kiểu rộng | `operation() throws Exception` | Nếu chữ ký cho phép `Exception`, compiler thường không thể tự suy ra rằng implementation hiện tại chỉ ném `IOException` |

Một ý đặc biệt quan trọng: **chữ ký phương thức được gọi là hợp đồng tại biên giới phân tích**. Nếu một phương thức được khai báo `throws IOException` nhưng implementation hiện tại chỉ tạo `FileNotFoundException`, nơi gọi vẫn phải coi nó có thể phát sinh `IOException`. Nếu phương thức được gọi khai báo `throws Exception`, `catch(Exception ex) { throw ex; }` không tự thu hẹp thành `IOException` chỉ vì các lần chạy đã quan sát được lỗi đó.

Phân tích này có xét cấu trúc luồng điều khiển và cách các ngoại lệ bị bắt tại những `catch` khác. Nó **không phải** phân tích hoàn hảo mọi giá trị dữ liệu, mọi hệ thống tệp hoặc mọi kết nối mạng tại runtime.

### Khi một ngoại lệ checked đã được xử lý trước đó

Xét phương thức minh họa với hai ngoại lệ như trên:

```java
static void handleDbLocally(boolean failFile, boolean failDb)
        throws java.io.IOException {
    try {
        load(failFile);
        query(failDb);
    } catch (java.sql.SQLException ex) {
        System.out.println("handled database error");
    } catch (Exception ex) {
        throw ex;
    }
}
```

Nhánh `catch (SQLException ex)` đã xử lý `SQLException` đến từ `try`. Ở nhánh `catch (Exception ex)` phía sau, kiểu checked còn liên quan đến việc ném lại là `IOException`; phương thức chỉ cần khai báo `throws IOException`. Nếu `catch` trước đó **ném lại** `SQLException` thay vì xử lý, hợp đồng `throws` của phương thức phải xét thêm trường hợp đó.

### `try-with-resources`: đừng quên `close()`

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static void readOneLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        reader.readLine();
    } catch (Exception ex) {
        throw ex;
    }
}
```

Đây là đoạn đặt trong lớp với các `import` ở đầu tệp. Các thao tác mở, đọc và **đóng** `BufferedReader` đều có thể liên quan tới `IOException`. Khi thân `try` ném ngoại lệ và `close()` cũng thất bại, try-with-resources giữ ngoại lệ chính và thường thêm lỗi đóng vào danh sách **suppressed exceptions**. Precise rethrow không làm mất cơ chế này; có thể kiểm tra `ex.getSuppressed()` nếu cần chẩn đoán.

Cần kiểm tra loại tài nguyên cụ thể: `AutoCloseable.close()` khai báo `throws Exception`, trong khi nhiều loại cụ thể như `BufferedReader.close()` khai báo hẹp hơn. Nếu biến tài nguyên được khai báo bằng một kiểu quá rộng, phân tích checked exception có thể phải chấp nhận loại `Exception` rộng hơn.

## 8. Giới hạn: phân tích tĩnh không bằng kết quả chạy thử

Có ba khái niệm cần tách:

1. **Declared exception (khai báo):** kiểu checked trong `throws` hoặc lệnh `throw` mà compiler nhìn thấy.
2. **Potential exception (có thể xảy ra theo phân tích):** kiểu checked mà compiler xác định có thể thoát khỏi một đường xử lý tương ứng.
3. **Observed exception (đã quan sát lúc chạy):** đối tượng ngoại lệ cụ thể phát sinh ở một lượt chạy với dữ liệu, môi trường và đường đi nhất định.

Ví dụ, phương thức khai báo:

```java
static void fetch() throws java.io.IOException {
    throw new java.io.FileNotFoundException("missing");
}
```

`FileNotFoundException` là lớp con của `IOException`. Nếu gọi `fetch()` từ một `try`, nơi gọi nhìn thấy hợp đồng checked `IOException`; không thể chỉ dựa vào implementation hiện tại để rút gọn mọi nơi sử dụng thành `FileNotFoundException`.

Thêm nữa, unchecked exception như `NullPointerException` hay `IllegalArgumentException` có thể xuất hiện mà không được khai báo. `catch (Exception ex)` sẽ bắt được `RuntimeException` (vì nó kế thừa `Exception`) và `throw ex` có thể ném lại mà **không cần ghi nó trong `throws`**. Việc không thấy kiểu unchecked trong chữ ký không đồng nghĩa với việc runtime không thể xảy ra.

Ngược lại, một số checked exception có thể bị compiler nhận diện là **không thể được ném từ `try`**. Đoạn sau **cố ý không biên dịch**:

```java
try {
    System.out.println("hello");
} catch (java.io.IOException ex) {
    System.out.println(ex.getMessage());
}
```

Không có nguồn `IOException` checked phù hợp trong thân `try`, nên một `catch(IOException)` ở đây không hợp lệ. Đừng thêm `catch` cho một ngoại lệ checked bất kỳ chỉ vì muốn xử lý “mọi trường hợp”. Nên lựa chọn các nhánh dựa trên API thực tế được gọi.

## 9. Nên ghi log, ném lại hay chuyển đổi ngoại lệ?

Trong hệ thống có nhiều tầng, `catch` không nhất thiết phải xử lý hết lỗi. Một mẫu đơn giản là giữ nguyên ngữ nghĩa và chuyển trách nhiệm cho tầng trên:

```java
try {
    load(failFile);
    query(failDb);
} catch (Exception ex) {
    System.err.println("Operation failed: "
            + ex.getClass().getSimpleName());
    throw ex;
}
```

Đây là đoạn minh họa thuộc lớp có `load/query`. Khi ném lại ngoại lệ gốc, stack trace của ngoại lệ vẫn gắn với đối tượng ban đầu; điều này có ích khi tìm điểm phát sinh. Nhưng **không nhất thiết tầng nào cũng cần log lỗi**: ghi log lặp ở nhiều tầng gây nhiễu. Chỉ log ở tầng có thể bổ sung ngữ cảnh hữu ích, và cẩn thận với dữ liệu nhạy cảm.

Khi thật sự cần chuyển đổi lỗi sang mức trừu tượng của API, hãy tạo ngoại lệ mới với nguyên nhân:

```java
try {
    load(true);
} catch (java.io.IOException ex) {
    throw new IllegalStateException("Unable to load content", ex);
}
```

Ở ví dụ này, `IllegalStateException` là unchecked nên không bắt buộc ghi `throws`, nhưng nó đã **thay đổi hợp đồng xử lý lỗi**. Dùng cách này khi API/thiết kế thực sự yêu cầu, không phải để che các checked exception cho tiện. Nếu cần lỗi nghiệp vụ có thể phục hồi được, một checked exception chuyên biệt cũng có thể thích hợp.

Với kết nối, tập tin và tài nguyên cần đóng, ưu tiên `try-with-resources` để không rò rỉ tài nguyên. Đừng nuốt ngoại lệ bằng một `catch (Exception ex) {}` trống; làm thế che giấu thất bại và có thể khiến chương trình tiếp tục với dữ liệu không hợp lệ.

## 10. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Hiểu “ngoại lệ thực sự phát sinh” là lỗi đã thấy khi chạy thử | Bỏ sót đường chạy khác hoặc lỗi trong hợp đồng `throws` | Phân tích tĩnh tất cả nguồn checked có thể xảy ra |
| Cho rằng `catch (Exception ex)` luôn buộc `throws Exception` | Khai báo API quá rộng dù `ex` không bị gán lại | Áp dụng precise rethrow, giữ chữ ký checked cụ thể |
| Gán lại `ex` rồi `throw ex` | Không còn điều kiện suy luận kiểu hẹp | Không gán lại tham số; chỉ thêm ngữ cảnh khi log |
| Đổi `throw ex` thành `throw new Exception(ex)` tùy tiện | Tạo kiểu checked rộng hơn và làm thay đổi hợp đồng API | Giữ ngoại lệ gốc hoặc bọc lỗi theo chủ đích |
| Chỉ xét ngoại lệ thân `try`, quên `close()` | Bỏ sót ngoại lệ từ tài nguyên | Kiểm tra try-with-resources và khai báo `close` |
| Nghĩ các `RuntimeException` phải liệt kê trong `throws` | Hiểu nhầm checked/unchecked | Chỉ checked exception bị bắt buộc xử lý/khai báo |
| Bắt `Exception` trước `IOException` | Nhánh hẹp không thể tiếp cận | Bắt cụ thể trước, rộng sau |
| Đưa `IOException` vào `catch` khi `try` không thể ném nó | Lỗi biên dịch vì checked exception không thể xuất hiện | Chỉ bắt loại được compiler cho phép |
| Dựa vào implementation đang ném kiểu con để khai báo hẹp ở nơi gọi | Không khớp với `throws` công khai của phương thức được gọi | Dựa vào chữ ký API và luồng xử lý |
| Bắt rồi bỏ qua lỗi hoặc log lặp lại ở mọi tầng | Mất thông tin hoặc nhiễu log | Xử lý tại đúng tầng; nếu chưa xử lý, ném lại hoặc chuyển đổi có nguyên nhân |

**Lưu ý thiết kế:** Precise rethrow là một **cải tiến về phân tích kiểu**; nó không tự khôi phục giao dịch, mở lại kết nối hoặc làm cho `catch (Exception)` trở thành phương án tối ưu cho mọi mã. Khi lỗi khác nhau cần cách xử lý khác nhau, các `catch` cụ thể vẫn là lựa chọn rõ ràng.

## 11. Bài tập tự kiểm tra

**Bài 1.** `read()` khai báo `throws IOException`; `save()` khai báo `throws SQLException`. Khối `try` gọi cả hai; `catch (Exception ex)` chỉ ghi log và `throw ex`. Phương thức chứa đoạn mã cần khai báo những checked exception nào?

**Bài 2.** Cũng tình huống trên, nhưng trong `catch` có lệnh `ex = new Exception("changed")` trước `throw ex;`. Vì sao chữ ký `throws IOException, SQLException` không còn đủ?

**Bài 3.** Phương thức `load()` khai báo `throws IOException` nhưng trong lần chạy đang xét luôn trả về thành công. Có thể bỏ `IOException` khỏi chữ ký phương thức gọi nó chỉ dựa trên kết quả chạy thử không?

**Bài 4.** Một `try-with-resources` dùng tài nguyên có `close() throws Exception`, dù thân `try` không khai báo checked exception. Khi ném lại trong `catch (Exception ex)`, compiler có thể vẫn yêu cầu khai báo `Exception` không?

**Bài 5.** Tại sao `catch (IOException ex)` có thể là lỗi biên dịch khi `try` chỉ gọi `System.out.println(...)`, nhưng `catch (RuntimeException ex)` có thể hợp lệ trong những ngữ cảnh tương tự?

### Đáp án

1. `throws IOException, SQLException`. Java 7+ có thể phân tích chính xác hơn các checked exception thoát khỏi `try` nếu tham số `catch` không bị gán lại.
2. Vì tham số `ex` đã bị gán lại: lệnh `throw ex` không còn đủ điều kiện precise rethrow. Kiểu khai báo là `Exception` nên phải xử lý/khai báo kiểu đó hoặc thiết kế lại luồng lỗi.
3. Không. Compiler căn cứ vào chữ ký checked exception và các đường thực thi có thể xảy ra theo phân tích tĩnh, không phải một kết quả chạy.
4. Có. Khi `close()` của kiểu tài nguyên được khai báo ném `Exception`, khả năng này là một phần của try-with-resources. Phân tích không thể tự loại bỏ chỉ vì thân khối không có thao tác checked.
5. `IOException` là checked, và Java kiểm tra tính khả dĩ theo `try`. `RuntimeException` là unchecked, có thể phát sinh mà không cần chữ ký `throws`, nên quy tắc bắt buộc kiểm tra không giống nhau.

**Tóm tắt:** Để phân tích đúng ngoại lệ thực sự có thể phát sinh từ một khối `try`, hãy đọc các lệnh `throw`, chữ ký của phương thức/constructor được gọi, đường đi qua `catch` và việc đóng tài nguyên. Với `catch (Exception ex)` mà `ex` không bị gán lại, **precise rethrow** từ Java 7 cho phép giữ chữ ký `throws` ở các kiểu checked cụ thể có thể thoát ra, thay vì buộc khai báo `Exception` một cách quá rộng.
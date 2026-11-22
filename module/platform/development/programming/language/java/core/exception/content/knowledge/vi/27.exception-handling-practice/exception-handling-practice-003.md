# Chuyển nhiều khối catch giống nhau thành multi-catch trong Java

> **Chủ đề:** Java Core → Exception → Thực hành. Bài hướng dẫn refactor nhiều nhánh `catch` xử lý tương tự thành **multi-catch** (`catch (TypeA | TypeB ex)`) từ Java 7, áp dụng trong Java 17+. Mục tiêu không chỉ giảm mã lặp, mà còn **giữ nguyên hành vi, chính sách xử lý, loại ngoại lệ, nguyên nhân gốc và khả năng chẩn đoán**. Có chương trình trước–sau chạy độc lập, bài tập, kiểm thử JUnit 5 và các trường hợp không nên gom.

## 1. Nhận diện bài toán: các catch gần như giống hệt nhau

Một phương thức có thể gặp nhiều exception đã biết nhưng cùng có chính sách xử lý:

~~~java
// Trích đoạn: fetchValue có thể throws IOException, SQLException.
try {
    return fetchValue();
} catch (IOException ex) {
    recordFailure(ex);
    return "fallback";
} catch (SQLException ex) {
    recordFailure(ex);
    return "fallback";
}
~~~

Hai nhánh chỉ khác **loại ngoại lệ**; cả hai gọi cùng hàm ghi nhận và trả cùng kết quả. Sao chép nội dung có thể dẫn đến việc một nhánh được sửa mà nhánh kia bị bỏ quên, ví dụ chỉ một nhánh bổ sung metric, log hoặc cleanup.

Java cho phép gộp bằng toán tử `|` **trong phần khai báo tham số catch**:

~~~java
try {
    return fetchValue();
} catch (IOException | SQLException ex) {
    recordFailure(ex);
    return "fallback";
}
~~~

Khi một trong hai loại được ném từ khối `try`, cùng một thân `catch` chạy. **Đây không phải bitwise OR hay logical OR trên giá trị boolean**: dấu `|` trong ngữ cảnh này kết hợp các kiểu exception thay thế. Khi refactor, chỉ có một `catch` được chọn cho mỗi exception được xử lý; không chạy tuần tự hai nhánh.

**Điều kiện cần:** các loại exception thực sự có **cùng chính sách** tại ranh giới này. Hai thân cùng dài hoặc đều gọi `log.error` chưa đủ để chứng minh semantics giống nhau.

## 2. Khi nào multi-catch phù hợp?

Thường phù hợp khi:

- Hai hay nhiều ngoại lệ có thể được xử lý bằng **cùng một fallback value**.
- Cùng được chuyển thành một exception cấp cao **với cause được giữ**.
- Cùng dẫn tới một trạng thái kết thúc tác vụ, ví dụ fail-fast tại boundary.
- Cùng cần ghi một sự kiện chẩn đoán với operation/request ID, trong khi loại gốc vẫn giữ bằng `ex.getClass()`.
- Cùng được truyền tiếp cho caller theo đúng chữ ký `throws`.
- Cùng hành vi retry/backoff, **đã chứng minh retry an toàn cho cả hai**.
- Thân `catch` không cần truy cập những phương thức chỉ có ở một subtype riêng.

Ví dụ:

~~~java
// Trích đoạn bên trong phương thức của ứng dụng.
try {
    performOperation();
} catch (IOException | SQLException ex) {
    throw new DataAccessFailure("operation failed", ex);
}
~~~

`DataAccessFailure` là lớp do ứng dụng định nghĩa, có constructor nhận `String, Throwable`. `ex` vẫn là **đối tượng exception thực tế** vừa được ném; `new DataAccessFailure(..., ex)` giữ chuỗi nguyên nhân.

**Không nên gom** nếu IOException là lỗi không nên retry nhưng SQLException là lỗi tạm thời nên retry; hoặc IOException cần khôi phục resource còn SQLException cần rollback transaction riêng. Khi policies khác nhau, giữ `catch` riêng giúp người đọc thấy đúng ý định.

## 3. Cú pháp multi-catch chính xác

Cú pháp cơ bản:

~~~java
try {
    riskyOperation();
} catch (IOException | SQLException ex) {
    handle(ex);
}
~~~

Quy tắc:

1. Các alternative cách nhau bằng một dấu `|` bên trong **cùng cặp ngoặc** của `catch`.
2. Chỉ có **một biến** ở cuối danh sách, ở ví dụ là `ex`.
3. Các kiểu phải là kiểu exception phù hợp: subtype của `Throwable`, tuân quy tắc checked/unchecked và khả năng exception thực sự được ném.
4. **Không một alternative nào được là subtype của alternative khác** trong cùng một multi-catch; đây là lỗi biên dịch.
5. Biến `ex` trong multi-catch là **implicitly final**; không thể gán lại một giá trị khác.
6. Các `catch` khác, nếu có, vẫn được xét **theo thứ tự từ trên xuống**, với quy tắc handler rộng đứng sau handler hẹp.
7. Các exception không được bắt vẫn tiếp tục propagate; multi-catch không tự biến exception thành thành công.

Cú pháp sai:

~~~java
// SAI: không phải cú pháp nhiều biến trong một catch.
catch (IOException io | SQLException sql) {
    // ...
}
~~~

Cú pháp đúng:

~~~java
catch (IOException | SQLException ex) {
    // Một tham số ex duy nhất.
}
~~~

Tên `ex` có scope trong thân `catch`; ngoài thân đó nó không tồn tại. Có thể dùng tên khác, ví dụ `failure`, nếu rõ hơn.

## 4. Hai điều kiện biên dịch dễ bị bỏ sót

### 4.1. Các kiểu trong cùng multi-catch không được có quan hệ kế thừa trực tiếp

Ví dụ không hợp lệ:

~~~java
// SAI: FileNotFoundException là con của IOException.
catch (java.io.FileNotFoundException | java.io.IOException ex) {
    // Compile error: alternatives related by subclassing.
}
~~~

Tại sao? `IOException` đã bao gồm `FileNotFoundException`; thêm alternative hẹp tạo dư thừa, làm cho hợp đồng bắt lỗi mơ hồ. Nếu chính sách thực sự giống nhau, chỉ cần:

~~~java
catch (java.io.IOException ex) {
    // Bắt cả FileNotFoundException và các IOException khác.
}
~~~

Nhưng **không nên thay hai ngoại lệ không liên quan bằng một lớp cha quá rộng chỉ cho ngắn**. Ví dụ `catch (Exception ex)` có thể nuốt luôn lỗi runtime không dự kiến và `InterruptedException`. `IOException | SQLException` nói rõ chính xác hai họ lỗi mà bạn chủ động xử lý.

### 4.2. Biến catch của multi-catch không thể gán lại

~~~java
// SAI: ex được coi là final trong multi-catch.
catch (IOException | SQLException ex) {
    ex = new IOException("replacement"); // Compile error.
}
~~~

Hãy tạo biến mới để chuyển đổi, hoặc trực tiếp tạo wrapper:

~~~java
catch (IOException | SQLException ex) {
    RuntimeException wrapped =
            new IllegalStateException("operation failed", ex);
    throw wrapped;
}
~~~

Không nên gán đè exception gốc rồi làm mất `cause`. Việc biến multi-catch là final còn giúp giữ rõ exception nào thực sự được bắt.

## 5. Kiểu của biến ex trong thân multi-catch

Một câu hỏi thường gặp: `ex` là `IOException` hay `SQLException`?

Trong runtime, nó vẫn tham chiếu tới đối tượng cụ thể được ném. Nhưng tại compile time, những method có thể gọi trực tiếp trên `ex` được xác định theo **kiểu chung thích hợp** của các alternative. Với `IOException | SQLException`, các thao tác chung của `Throwable`/`Exception` như sau đều dùng được:

~~~java
catch (IOException | SQLException ex) {
    String type = ex.getClass().getSimpleName();
    String message = ex.getMessage();
    Throwable cause = ex.getCause();
    // Gọi logger truyền Throwable đầy đủ.
}
~~~

Ngược lại, `SQLException.getSQLState()` không phải method của `IOException`, nên không thể gọi `ex.getSQLState()` trực tiếp trên biến union đó.

Nếu policy thực sự cần SQL state, giữ hai nhánh riêng; hoặc thực hiện phân loại có kiểu rõ ràng khi điều đó **chỉ nhằm thêm context, không thay đổi outcome**:

~~~java
catch (IOException | SQLException ex) {
    if (ex instanceof SQLException sql) {
        recordSqlState(sql.getSQLState());
    }
    recordFailure(ex);
    throw new DataAccessFailure("operation failed", ex);
}
~~~

Đoạn này là trích đoạn trong lớp có `recordSqlState`, `recordFailure` và `DataAccessFailure`. Java 17 hỗ trợ pattern matching `instanceof`. Nếu trong `catch` xuất hiện nhiều `instanceof` với các đường xử lý khác nhau, đó là dấu hiệu nên xem lại quyết định gom: hai `catch` riêng có thể rõ hơn.

## 6. Ví dụ Java 17 đầy đủ: trước và sau khi refactor

Chương trình cố ý tạo **hai lỗi checked khác họ**: `IOException` (nguồn file) và `SQLException` (nguồn database). Cả hai phải trả cùng một fallback tại ranh giới đang xét. Nhánh thành công giữ kết quả cũ. Không phụ thuộc file hay database thật, nên stdout xác định.

Lưu vào **`MultiCatchRefactorDemo.java`**:

~~~java
import java.io.IOException;
import java.sql.SQLException;
import java.util.List;

public class MultiCatchRefactorDemo {
    static String fetch(String source) throws IOException, SQLException {
        if ("file".equals(source)) {
            throw new IOException("disk unavailable");
        }
        if ("db".equals(source)) {
            throw new SQLException("database unavailable");
        }
        return "ready";
    }

    static String fallback(Exception failure) {
        return "fallback(" + failure.getClass().getSimpleName()
                + ": " + failure.getMessage() + ")";
    }

    // Trước refactor: hai thân catch giống hệt nhau.
    static String before(String source) {
        try {
            return "value=" + fetch(source);
        } catch (IOException ex) {
            return fallback(ex);
        } catch (SQLException ex) {
            return fallback(ex);
        }
    }

    // Sau refactor: gộp đúng hai họ lỗi có cùng policy.
    static String after(String source) {
        try {
            return "value=" + fetch(source);
        } catch (IOException | SQLException ex) {
            return fallback(ex);
        }
    }

    // Multi-catch không buộc phải nuốt hoặc bọc exception.
    static void relay(String source) throws IOException, SQLException {
        try {
            fetch(source);
        } catch (IOException | SQLException ex) {
            throw ex;
        }
    }

    public static void main(String[] args) {
        for (String source : List.of("ok", "file", "db")) {
            System.out.println(source + ": before=" + before(source)
                    + " | after=" + after(source));
        }

        try {
            relay("file");
        } catch (IOException ex) {
            System.out.println("relay file: "
                    + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        } catch (SQLException ex) {
            throw new AssertionError("Unexpected SQL exception", ex);
        }

        try {
            relay("db");
        } catch (SQLException ex) {
            System.out.println("relay db: "
                    + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        } catch (IOException ex) {
            throw new AssertionError("Unexpected IO exception", ex);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac MultiCatchRefactorDemo.java
java MultiCatchRefactorDemo
~~~

**Stdout chính xác:**

~~~text
ok: before=value=ready | after=value=ready
file: before=fallback(IOException: disk unavailable) | after=fallback(IOException: disk unavailable)
db: before=fallback(SQLException: database unavailable) | after=fallback(SQLException: database unavailable)
relay file: IOException: disk unavailable
relay db: SQLException: database unavailable
~~~

### Phân tích

1. `fetch("ok")` hoàn tất bình thường và hai phương thức đều trả `"value=ready"`.
2. `fetch("file")` ném `IOException`. `before` chọn `catch IOException`; `after` chọn multi-catch. Cả hai chuyển vào cùng helper `fallback` và giữ cùng kiểu/message.
3. `fetch("db")` ném `SQLException`; chính sách cũng giống trường hợp file.
4. `relay` minh họa **ném lại nguyên exception** từ multi-catch. Caller vẫn bắt riêng `IOException` và `SQLException`.
5. `List.of` giữ đúng thứ tự ba trường hợp. Không có concurrency, timeout hoặc dữ liệu I/O thực nên thứ tự output cố định.
6. Trong ứng dụng thật, `fallback` có thể đồng thời cập nhật một metric và trả một `Result` có cấu trúc; không bắt buộc return chuỗi như ví dụ.
7. Chương trình chứng minh **tính tương đương theo những tình huống đã định nghĩa**, không thay thế test hồi quy đầy đủ cho code production.

**Bài học từ code:** rút gọn một nhánh catch không làm thay đổi runtime class của exception. Việc gộp phù hợp khi chính sách của các lỗi giống nhau, không phải vì chúng đều là checked exception.

## 7. Precise rethrow: ném lại mà vẫn giữ hợp đồng checked exception

Một lợi ích quan trọng của multi-catch là ném lại `ex` **không bắt buộc** phải khai báo `throws Exception` quá rộng. Với ví dụ:

~~~java
// Trích từ một lớp có fetch(String).
static void relay(String source) throws IOException, SQLException {
    try {
        fetch(source);
    } catch (IOException | SQLException ex) {
        throw ex;
    }
}
~~~

Compiler biết `ex` chỉ có thể mang các loại mà handler ấy bắt từ `try`. Phương thức có thể công bố đúng `throws IOException, SQLException`; caller xử lý riêng hai ngoại lệ và không phải bắt mọi `Exception`.

Đây là **precise rethrow** được Java hỗ trợ từ Java 7, liên quan tới phân tích loại exception của compiler, đặc biệt khi tham số catch không bị gán lại. Multi-catch parameter là implicitly final nên không có trường hợp code trong catch gán đè biến đó.

Không nhầm hai dạng:

~~~java
// Giữ nguyên exception object và stack gốc.
throw ex;
~~~

và:

~~~java
// Tạo exception mới, cần gắn cause để giữ dấu vết.
throw new IllegalStateException("request failed", ex);
~~~

Dạng thứ hai đổi abstraction/hợp đồng: caller có thể thấy `IllegalStateException` thay vì `IOException`/`SQLException`. Dùng khi API cố ý chuyển lỗi kỹ thuật thành lỗi domain hoặc unchecked, **không phải bước tự động của refactor multi-catch**.

### Precise rethrow có thể áp dụng cho catch đơn không?

Có. Các cải tiến phân tích checked exceptions của Java 7 không chỉ dành cho cú pháp có dấu `|`. Với một `catch (Exception ex)` **không được gán lại**, compiler đôi khi xác định những checked exception có thể thoát theo ngữ cảnh `try`. Nhưng dùng `catch (Exception)` để xử lý mọi lỗi vẫn có thể tạo nghĩa quá rộng: compiler chấp nhận không có nghĩa chính sách runtime tốt.

## 8. Thứ tự handler và tính reachability

Java thử các `catch` theo thứ tự xuất hiện. Handler rộng đặt trước có thể làm handler phía sau **không thể đến được**, dẫn đến lỗi biên dịch.

Ví dụ sai:

~~~java
// SAI: catch(Exception) đã bao gồm IOException và SQLException.
try {
    fetch(source);
} catch (Exception ex) {
    handle(ex);
} catch (IOException | SQLException ex) {
    handle(ex);
}
~~~

Mã đã được refactor đúng phải đảm bảo:

- Multi-catch của các loại hẹp/đích danh đặt trước handler rộng có ý nghĩa khác.
- Không có alternative nào là subtype của alternative khác trong **cùng** danh sách.
- Các handler còn lại vẫn xử lý các họ exception khác theo đúng policy.
- Mã bên trong `try` có thể ném các checked exceptions tương ứng; không thêm một alternative checked mà compiler biết chắc không có đường ném.
- Không vô tình gộp `RuntimeException` hoặc `Exception` như một cách bắt mọi sự cố.

Ví dụ hợp lệ:

~~~java
try {
    fetch(source);
} catch (IOException | SQLException ex) {
    recordExpectedInfrastructureFailure(ex);
} catch (RuntimeException unexpected) {
    reportProgrammingOrContractFailure(unexpected);
}
~~~

Đây là mã minh họa với các helper do ứng dụng định nghĩa. Không phải mọi `RuntimeException` đều là bug, nhưng handler này được tách vì **chính sách** của nhánh runtime khác hai loại checked đã biết.

## 9. Không gom nếu hai policy thực sự khác nhau

Giả sử hệ thống có logic:

~~~java
try {
    storeOrder();
} catch (IOException ex) {
    // Lỗi I/O trong bước đọc local file: đánh dấu input không khả dụng.
    markInputUnavailable(ex);
} catch (SQLException ex) {
    // Lỗi giao dịch: rollback và chuyển nguyên nhân để retry theo chính sách DB.
    rollbackTransaction();
    throw new RepositoryFailure("database write failed", ex);
}
~~~

Gom thành:

~~~java
catch (IOException | SQLException ex) {
    log.warn("operation failed", ex);
}
~~~

là **thay đổi semantics nguy hiểm**: mất rollback, nuốt lỗi SQL, đảo outcome, có thể để hệ thống ở trạng thái sai. Dù cả hai thân cũ có một số dòng logging giống nhau, phần khác nhau mang tính nghiệp vụ và phải được giữ lại.

Phương án tốt hơn là trích xuất đúng phần chung:

~~~java
try {
    storeOrder();
} catch (IOException ex) {
    recordCommonContext(ex);
    markInputUnavailable(ex);
} catch (SQLException ex) {
    recordCommonContext(ex);
    rollbackTransaction();
    throw new RepositoryFailure("database write failed", ex);
}
~~~

Đây là các đoạn minh họa không chạy độc lập vì còn thiếu class/helper. Khi policies khác nhau, chia sẻ hàm nhỏ (`recordCommonContext`) rõ ràng hơn multi-catch có nhiều `instanceof`.

**Các tín hiệu cần giữ catch riêng:** số lần retry khác nhau, mức log khác nhau, transaction rollback khác nhau, fallback không giống nhau, trạng thái trả về khác, timeout/hủy cần xử lý đặc biệt hoặc subtype-specific API cần đọc.

## 10. InterruptedException cần chính sách riêng

Một sai lầm thường thấy khi gom các loại ngoại lệ cho tiện:

~~~java
// Có thể biên dịch theo ngữ cảnh nhưng rất dễ sai về policy.
try {
    blockingOperation();
    databaseOperation();
} catch (InterruptedException | SQLException ex) {
    log.warn("operation failed", ex);
    return;
}
~~~

Đoạn trên chỉ minh họa, giả định `blockingOperation` ném `InterruptedException`, `databaseOperation` ném `SQLException` và method có thể `return`. Vấn đề: `InterruptedException` là tín hiệu về việc **thread đang chờ** bị ngắt. Với nhiều blocking APIs như `Thread.sleep`, `Object.wait` và `Thread.join`, interrupt flag được xóa khi ném exception.

Nếu method không thể truyền `InterruptedException` lên (chẳng hạn `Runnable.run()`), nó thường cần `Thread.currentThread().interrupt()` rồi thoát. `SQLException` lại có chính sách xử lý DB hoàn toàn khác. Gom hai ngoại lệ vào một handler chung mà không phục hồi cờ có thể làm hỏng giao thức cancellation.

Hãy tách:

~~~java
try {
    blockingOperation();
    databaseOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (SQLException ex) {
    recordDatabaseFailure(ex);
    return;
}
~~~

Một ngoại lệ chỉ nên vào multi-catch với `InterruptedException` nếu **thật sự** có cùng chính sách interrupt và ứng dụng đã chứng minh điều đó, tình huống hiếm. Tránh chỉ vì cả hai nhánh kết thúc bằng `return` mà bỏ qua trạng thái thread.

## 11. Giữ nguyên cause, stack trace và các lỗi bị suppress

Refactor multi-catch không đòi hỏi tạo exception mới. Nếu cùng một lỗi đi lên đúng abstraction, có thể `throw ex` hoặc để tự propagate. Nếu đổi tầng abstraction, bọc bằng constructor nhận `cause`:

~~~java
catch (IOException | SQLException ex) {
    throw new DataAccessFailure("unable to load order", ex);
}
~~~

Không làm như sau:

~~~java
catch (IOException | SQLException ex) {
    throw new IllegalStateException(ex.getMessage()); // Mất cause.
}
~~~

Dạng thứ hai khiến caller khó tìm stack trace gốc và metadata kỹ thuật. Ngoài `getCause()`, một `Throwable` còn có suppressed exceptions (thường phát sinh từ `try-with-resources`). Multi-catch **không làm mất** những dữ liệu này nếu bạn chuyển nguyên object đúng cách. Đừng chỉ copy message rồi bỏ throwable.

### Try-with-resources vẫn hoạt động

~~~java
// Trích đoạn minh họa, có Connection connection được mở thích hợp.
try (java.sql.Connection c = connection) {
    writeData(c);
} catch (java.sql.SQLException | IllegalStateException ex) {
    reportFailure(ex);
}
~~~

Đây là đoạn không độc lập; `writeData`, `connection`, `reportFailure` do ứng dụng cung cấp. `try-with-resources` chịu trách nhiệm đóng resource theo hợp đồng; nếu thao tác trong try và việc đóng cùng ném lỗi, lỗi đóng có thể được đưa vào `getSuppressed()`. Việc gộp catch **không biến failure thành transaction rollback** và không thay thế trách nhiệm `commit`/`rollback` theo kiến trúc DB.

## 12. Logging: gom handler không có nghĩa spam log ít lần theo mặc định

Một lợi ích code-level của multi-catch là tập trung policy log cho nhiều loại lỗi:

~~~java
catch (IOException | SQLException ex) {
    log.error("event=order_load_failed operation={} orderId={}",
            operation, orderId, ex);
    throw new OrderLoadFailure("load failed", ex);
}
~~~

Đây là ví dụ dùng một API logger kiểu SLF4J; cần dependency logger và các biến/class được định nghĩa trong dự án. Nếu tầng trên cũng ghi cùng stack trace rồi ném tiếp, **vẫn có log trùng**, dù tầng này đã multi-catch. Quy tắc log ownership độc lập với cú pháp catch:

- Tầng chỉ chuyển lỗi: thêm context/cause rồi rethrow; có thể không cần `ERROR` log tại chỗ.
- Tầng sở hữu outcome cuối: ghi một sự kiện failure đủ operation/request ID/business ID/Throwable.
- Retry/fallback/compensation là **sự kiện riêng** có thể cần log hoặc metrics phù hợp.
- Không dùng message của exception như machine-readable error code.
- Phân biệt severity và chính sách cho IOException/SQLException nếu chúng không thật sự giống nhau.

Nếu một handler multi-catch có 10 câu `if (ex instanceof ...)` chỉ để chọn message/log level thì refactor có thể khiến code khó đọc hơn hai catch đơn giản.

## 13. Đừng gộp chỉ vì cách viết thân catch giống nhau

Hai đoạn trông giống hệt:

~~~java
catch (IOException ex) {
    retry(ex);
}
catch (SQLException ex) {
    retry(ex);
}
~~~

nhưng helper `retry(ex)` có thể dựa vào runtime type và thực hiện các policy khác nhau; cần đọc hợp đồng helper trước khi kết luận refactor an toàn. Tính tương đương không chỉ là cùng các dòng text, mà còn gồm:

- Callback/tham số được truyền có cùng nghĩa không?
- Có đọc subtype field (SQLState, file path, status) ở nơi khác không?
- Exception nào cần restore interrupt flag?
- Số lần thử, delay và idempotency có bằng nhau không?
- Có cần rollback/compensation trước khi retry?
- Mức log và public error code có cùng không?
- Caller sẽ thấy loại exception nào sau khi handler kết thúc?

Nếu cùng method `handle(ex)` nhưng bên trong phân nhánh theo class, multi-catch có thể vẫn đúng ở mức cơ chế; tuy nhiên refactor nên được đánh giá theo **độ rõ ràng của hợp đồng** chứ không chỉ số dòng.

## 14. Từng bước refactor an toàn trong IDE

Một quy trình thực hành có thể lặp lại:

1. **Khoanh vùng một khối try:** đọc các nguồn exception có thể xảy ra và mọi catch hiện tại.
2. **Tìm các thân catch giống nhau:** so sánh cả return, throw, finally, logging, cleanup và trạng thái được thay đổi.
3. **Xác nhận cùng policy:** không chỉ cùng câu chữ; cùng outcome, retry, interrupt và transaction semantics.
4. **Kiểm tra quan hệ kiểu:** các exception trong cùng `|` không là subtype của nhau.
5. **Kiểm tra subtype-specific method:** nếu thân catch dùng `getSQLState()`, `getFile()`, v.v., cần đổi cấu trúc hoặc giữ catch riêng.
6. **Thay bằng một multi-catch:** giữ body đúng nguyên nghĩa, không tự ý đổi fallback hay tạo wrapper khác.
7. **Biên dịch:** compiler bắt unreachable catches, type alternatives liên quan nhau và việc gán lại `ex`.
8. **Chạy unit tests:** case cho từng alternative và các lỗi không thuộc danh sách.
9. **Kiểm tra side effect:** nguyên nhân, callback count, metrics, log count, rollback/retry.
10. **Đánh giá readability:** nếu phải thêm nhiều `instanceof`, rollback policy hoặc cast, quay lại catch riêng.
11. **Kiểm tra binary/public contract:** refactor internal không nhất thiết đổi API; nếu đổi `throws`/kiểu wrapper public, cần xem compatibility.
12. **Review diff:** số dòng giảm là kết quả phụ; invariant quan trọng là hành vi không đổi.

IDE có thể đề xuất “Join multiple catch sections” hoặc tương tự, nhưng developer vẫn phải đánh giá chính sách xử lý. Một quick fix hợp cú pháp không thể thay thế việc hiểu nghiệp vụ.

## 15. Bộ test JUnit 5: chứng minh hành vi trước–sau

Các phương thức `before`, `after`, `relay` của chương trình `MultiCatchRefactorDemo` có package-private visibility. Nếu đặt lớp test sau trong **cùng package**, có thể gọi trực tiếp để kiểm tra. Đây là **mã JUnit 5**, cần dependency và test engine, không chạy chỉ bằng `javac` JDK thuần.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.io.IOException;
import java.sql.SQLException;
import org.junit.jupiter.api.Test;

class MultiCatchRefactorDemoTest {
    @Test
    void sameResultForSuccessAndEachHandledException() {
        for (String source : new String[] {"ok", "file", "db"}) {
            assertEquals(MultiCatchRefactorDemo.before(source),
                    MultiCatchRefactorDemo.after(source), source);
        }
    }

    @Test
    void ioExceptionIsStillRethrownAsIoException() {
        IOException ex = assertThrows(IOException.class,
                () -> MultiCatchRefactorDemo.relay("file"));
        assertEquals("disk unavailable", ex.getMessage());
    }

    @Test
    void sqlExceptionIsStillRethrownAsSqlException() {
        SQLException ex = assertThrows(SQLException.class,
                () -> MultiCatchRefactorDemo.relay("db"));
        assertEquals("database unavailable", ex.getMessage());
    }

    @Test
    void successRemainsSuccessful() {
        assertDoesNotThrow(() -> MultiCatchRefactorDemo.relay("ok"));
        assertEquals("value=ready",
                MultiCatchRefactorDemo.after("ok"));
    }
}
~~~

Các test cần phân biệt:

- Đường thành công trước/sau **trả đúng cùng giá trị**.
- Từng alternative có ít nhất một test riêng để phát hiện trường hợp một loại không còn được bắt.
- Nếu policy là rethrow, caller vẫn nhận **kiểu gốc** và message/cause theo hợp đồng.
- Nếu policy bọc thành `DomainException`, kiểm tra `getCause()` và error code, không chỉ assert wrapper.
- Nếu có side effect, xác nhận chính sách cleanup/transaction và không ghi log/metric ngoài dự kiến.
- Nếu handler chỉ dùng `fallback`, test nên xác minh lỗi programming khác vẫn propagate, không bị nuốt bởi catch quá rộng.

Bộ JUnit bên trên kiểm tra hành vi theo ví dụ tối giản. Trong dự án thật, có thể dùng fake/mock dependency để gây chính xác từng exception ở cùng điểm, thay vì phải tác động tới file/DB thật.

## 16. Test checked và unchecked exception một cách nhất quán

Một lời gọi trong `try` có thể ném cả checked exception được khai báo và unchecked exception ngoài dự kiến. Nếu trước refactor chỉ bắt `IOException` và `SQLException`, sau refactor cũng chỉ nên bắt **đúng hai họ ấy**.

Ví dụ:

~~~java
// Đoạn minh họa.
try {
    fetch(source);
} catch (IOException | SQLException ex) {
    return fallback(ex);
}
~~~

Nếu `fetch` gặp `NullPointerException` do bug thì nó không tự trở thành fallback. Đây thường là behavior mong muốn: không biến bug thành kết quả thành công giả. Nếu đổi sang:

~~~java
catch (Exception ex) {
    return fallback(ex);
}
~~~

thì chương trình có thể nuốt hàng loạt `RuntimeException` khác và cả những loại checked exception không thuộc policy đã thiết kế. Test nên có một case phun `IllegalStateException` hoặc `NullPointerException` qua fake dependency để chắc chắn nó vẫn propagate.

**Đừng ném unchecked exception giả chỉ để chạm nhánh checked catch.** Test cho `catch (IOException | SQLException ex)` cần tạo đúng `IOException` và đúng `SQLException`; test chỉ tạo `RuntimeException` không kiểm tra được handler này.

## 17. Multi-catch và đa hình: khi nào chỉ cần một catch cha?

Nếu mọi lỗi đều kế thừa một base type đã được thiết kế cho domain:

~~~java
// Trích đoạn với base class DomainFailure.
catch (DomainFailure ex) {
    handleDomainFailure(ex);
}
~~~

có thể rõ hơn một danh sách hàng chục subtype. Nhưng chỉ đúng nếu **mọi subtype của DomainFailure** đều cần chính sách đó, kể cả subtype mới thêm về sau.

Dùng multi-catch:

~~~java
catch (ValidationFailure | ConflictFailure ex) {
    handleExpectedRejection(ex);
}
~~~

phù hợp hơn khi chỉ hai subtype không có quan hệ kế thừa trực tiếp với nhau và không muốn bắt những subtype khác của base class. Các tên class này là minh họa và phải được định nghĩa nếu dùng trong dự án.

Trước khi chọn, hỏi: hệ thống cần policy cho **toàn bộ họ lỗi** hay chỉ **một tập lỗi cụ thể**? Một `catch (DomainFailure)` có thể quá rộng về tương lai khi hệ thống bổ sung subtype báo sự cố hạ tầng. Multi-catch giúp biểu đạt danh sách lựa chọn có chủ đích.

## 18. Tác động tới hiệu năng và bảo trì

Multi-catch chủ yếu là **cải tiến cấu trúc và khả năng bảo trì**. Nó có thể giảm duplicate bytecode/handler code trong vài tình huống, nhưng không nên hứa hẹn tăng tốc đáng kể hoặc giảm chi phí `Throwable` chỉ vì đổi hai catch thành một.

Một ngoại lệ vẫn được tạo/ném/tra handler theo JVM; chi phí stack trace, log hoặc I/O không biến mất nhờ dấu `|`. Nếu exception xuất hiện thường xuyên như **luồng điều khiển bình thường**, cần đánh giá thiết kế result/condition riêng thay vì chỉ tối ưu catch. Nếu lỗi hiếm và catch giống nhau, multi-catch làm code dễ review hơn và giảm nguy cơ sửa lệch policy.

Về khả năng bảo trì:

- Một chỗ để cập nhật handler chung.
- Dễ nhận diện tập exception được cố ý phục hồi.
- Giảm việc copy-paste log/wrap lỗi.
- Tránh việc bổ sung ID hoặc cleanup ở một nhánh mà quên nhánh khác.
- Nhưng có thể **giảm clarity** nếu danh sách `|` quá dài hoặc policy chỉ “na ná” nhau.

Không bắt buộc tất cả catch phải được gom. Code rõ nghĩa và đúng invariant quan trọng hơn một con số lines-of-code thấp.

## 19. Các lỗi phổ biến khi làm bài tập

1. **Gom hai subtype có quan hệ cha–con:** `FileNotFoundException | IOException` không hợp lệ.
2. **Đặt tên biến cho từng alternative:** multi-catch chỉ có một `ex`.
3. **Gán lại tham số `ex`:** biến trong multi-catch là implicitly final.
4. **Đưa handler cha lên trước:** `catch(Exception)` trước handler hẹp làm unreachable code.
5. **Thay danh sách bằng `catch(Exception)` cho tiện:** nuốt lỗi không dự kiến.
6. **Gom theo cách viết nhưng bỏ qua policy:** retry, rollback, fallback, cancel/interrupt có thể khác.
7. **Dùng subtype-specific method trên union parameter:** `getSQLState()` không gọi trực tiếp khi `ex` có thể là `IOException`.
8. **Bọc lại exception nhưng bỏ cause:** `new RuntimeException(ex.getMessage())` mất nguyên nhân gốc.
9. **Log rồi throw ở mọi tầng:** multi-catch không tự loại duplication logs.
10. **Coi `InterruptedException` như lỗi bất kỳ:** có thể làm mất interrupt flag và khiến worker không dừng.
11. **Bắt lỗi không thể được ném từ try:** compiler có thể báo checked exception never thrown.
12. **Thêm `return` để gộp hai catch:** vô tình biến thất bại thành success hoặc bỏ lỡ rollback.
13. **Giả định kiểu compile-time của ex là subtype cụ thể:** `ex` phải phù hợp các alternative.
14. **Ném lại bằng wrapper mới mà không cập nhật hợp đồng API:** caller có thể đổi cách bắt ngoại lệ.
15. **Chỉ test một alternative:** nhánh còn lại có thể bị thay đổi mà không ai thấy.
16. **Cho rằng ít code luôn nhanh hơn:** không có benchmark hoặc bằng chứng hiệu năng.
17. **Quên try-with-resources/suppressed exceptions:** handler cần giữ Throwable đầy đủ khi chẩn đoán.
18. **Lạm dụng `instanceof` trong multi-catch:** nếu phần lớn thân catch rẽ nhánh trở lại, nên giữ catch riêng.

## 20. Bài luyện tập theo mức độ

### Bài A — Refactor đúng hai nhánh giống nhau

Cho code:

~~~java
try {
    export();
} catch (IOException ex) {
    markFailed(ex);
    return false;
} catch (SQLException ex) {
    markFailed(ex);
    return false;
}
~~~

Yêu cầu: viết lại bằng multi-catch và giữ nguyên behavior. Đáp án:

~~~java
try {
    export();
} catch (IOException | SQLException ex) {
    markFailed(ex);
    return false;
}
~~~

Đây là trích đoạn, không phải chương trình đầy đủ. Điều kiện: `export()` có khả năng ném hai loại checked, `markFailed` nhận tham số chung như `Exception`/`Throwable` và được thiết kế dùng chung policy.

### Bài B — Phát hiện code không hợp lệ

~~~java
// SAI: hai alternative có quan hệ cha–con.
catch (java.io.FileNotFoundException | java.io.IOException ex) {
    return "failed";
}
~~~

Sửa: nếu tất cả IOException cùng policy, dùng `catch (IOException ex)`; nếu muốn xử lý riêng FileNotFoundException, tách một catch hẹp **đứng trước** catch IOException và dùng chính sách khác. Không thể đặt hai alternative này trong cùng multi-catch.

### Bài C — Giữ nguyên checked exception cho caller

Từ hai catch có `throw ex` riêng, gộp:

~~~java
static void load() throws IOException, SQLException {
    try {
        readFromSources();
    } catch (IOException | SQLException ex) {
        throw ex;
    }
}
~~~

Đoạn này cần `readFromSources()` được định nghĩa thích hợp. Kiểm tra compiler chấp nhận `throws IOException, SQLException` và test caller vẫn bắt đúng từng subtype.

### Bài D — Không gộp khi chính sách khác

~~~java
catch (IOException ex) {
    useCachedValue();
} catch (SQLException ex) {
    rollbackTransaction();
    throw new StorageFailure("db failed", ex);
}
~~~

Đáp án: **giữ hai nhánh riêng**. Việc cố rút thành một multi-catch sẽ khiến handler phải dùng `instanceof` hoặc làm sai outcome. Có thể trích helper dùng chung nếu thực sự có thao tác giống nhau, nhưng không đánh mất phần khác.

### Bài E — Viết test cho lỗi thứ ba

Tạo fake `fetch` có thể ném `IllegalStateException` bên cạnh IOException/SQLException. Kiểm tra multi-catch không nuốt `IllegalStateException`. Nếu refactor vô tình chuyển sang `catch(Exception)`, test phải phát hiện lỗi thay đổi hợp đồng.

## 21. Checklist trước khi merge thay đổi

- Hai hoặc nhiều catch cũ xử lý **cùng policy**, không chỉ cùng câu log?
- Các exception là alternative hợp lệ, không có quan hệ subtype giữa chúng?
- Những checked exception đó thực sự có thể phát sinh từ `try`?
- Biến `ex` có cần method riêng của từng subtype không?
- Thứ tự các handler hẹp/rộng giữ nguyên?
- `throw ex` hay wrap có giữ đúng checked-exception contract và `cause`?
- Có xử lý đặc biệt cho `InterruptedException`, rollback và cancellation?
- Có log trùng hoặc thay đổi severity/error code ngoài ý muốn?
- Fallback value, return/throw, trạng thái tài nguyên và side effect có giống trước?
- Test bao phủ đường success và **từng** alternative?
- Test có chứng minh lỗi ngoài tập alternative không bị nuốt?
- Code sau refactor có dễ hiểu hơn hai nhánh cũ không?

## 22. Tổng kết

**Multi-catch** trong Java cho phép dùng một thân handler cho nhiều kiểu exception bằng `catch (A | B ex)`. Đây là lựa chọn tốt khi các exception **khác kiểu nhưng thật sự có cùng cách xử lý**. Nó loại trùng lặp và làm rõ tập lỗi được chủ động bắt, trong khi exception runtime vẫn giữ kiểu/cause riêng.

Khi thực hành, hãy giữ năm nguyên tắc: **kiểm tra chính sách**, **tuân quy tắc subtype và thứ tự catch**, **không gán lại tham số multi-catch**, **bảo toàn cause/precise rethrow**, và **test từng loại lỗi trước–sau**. Nếu policies khác nhau hoặc thân handler phải phân nhánh theo kiểu liên tục, các catch riêng thường đúng và dễ bảo trì hơn.

### Tài liệu tham khảo

- [Java Language Specification §14.20 — The try statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20)
- [Java Language Specification §11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html)
- [Oracle — Catching Multiple Exception Types and Rethrowing Exceptions](https://docs.oracle.com/javase/8/docs/technotes/guides/language/catch-multiple.html)
- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html)
- [Java SE 17 — SQLException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html)

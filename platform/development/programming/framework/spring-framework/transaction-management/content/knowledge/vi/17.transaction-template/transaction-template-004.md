# Trả kết quả từ callback và xử lý ngoại lệ với TransactionTemplate

## Mục tiêu học tập

Trong Spring Framework, `TransactionTemplate` giúp bao một khối mã Java trong transaction theo cách **lập trình** (programmatic transaction management). Hai tình huống cần nắm vững là **callback trả một kết quả** và **callback thất bại hoặc yêu cầu rollback**. Hành vi của chúng ảnh hưởng trực tiếp đến tính đúng đắn của nghiệp vụ:

- `execute(TransactionCallback<T>)` chạy callback, kết thúc transaction theo quy tắc của transaction manager rồi **trả về `T`** nếu quá trình hoàn tất thành công. Callback có thể trả object, collection, record, `Optional<T>` hoặc `null`.
- `executeWithoutResult(Consumer<TransactionStatus>)` phù hợp với thao tác không cần giá trị trả về; callback nhận `TransactionStatus` để có thể yêu cầu rollback.
- Nếu callback **ném `RuntimeException` hoặc `Error`** ra khỏi callback, với `TransactionTemplate` và transaction manager thông thường, Spring tiến hành rollback rồi **truyền lỗi tới caller**. Nếu rollback gặp lỗi, lỗi transaction có thể thay thế lỗi ban đầu.
- Nếu callback **bắt exception rồi trả về bình thường**, transaction manager không tự biết đó là lỗi nghiệp vụ cần rollback. Nếu chưa bị đánh dấu rollback-only, Spring thường cố commit.
- Nếu callback gọi `status.setRollbackOnly()` rồi trả một giá trị, **giá trị đó không đồng nghĩa dữ liệu đã commit**. Với một physical transaction mới bình thường, Spring có thể rollback rồi vẫn trả chính giá trị callback; với transaction tham gia outer, lỗi/`UnexpectedRollbackException` có thể xuất hiện ở ranh giới giao dịch ngoài.
- Callback `TransactionCallback<T>` **không khai báo `throws` checked exception**; `IOException`/`SQLException` cần được xử lý, chuyển thành unchecked exception, hoặc báo kết quả lỗi và quyết định rollback rõ ràng.
- Transaction boundary không chạy qua một tác vụ async trả về sau; trả `CompletableFuture` hay stream lười không khiến transaction bao trùm phần thực thi về sau.

Bài này trình bày bản chất API, bảng kết quả/rollback, những lỗi xử lý exception thường gặp và **một ví dụ Java 17 + Spring JDBC/H2 chạy được**. Phạm vi chính là transaction đồng bộ (imperative) sử dụng `PlatformTransactionManager`; với reactive transaction, hãy dùng `TransactionalOperator` và Reactor context thay vì suy diễn trực tiếp từ ví dụ này.

## 1. `TransactionTemplate` thực hiện nhiệm vụ gì?

Transaction programmatic không phải tự viết `connection.setAutoCommit(false)`, `commit()` và `rollback()` trong từng service. Thay vào đó, Spring quản lý vòng đời dựa trên `PlatformTransactionManager`. Bạn cung cấp **phần nghiệp vụ** trong một callback.

```text
Caller
   |
   |  T result = transactionTemplate.execute(status -> { ...; return value; });
   v
TransactionTemplate
   |
   +-- getTransaction(transactionDefinition)
   |       mở physical transaction hoặc tham gia transaction hiện có
   |
   +-- gọi TransactionCallback.doInTransaction(status)
   |       JDBC/Repository/DAO thực thi trong transaction tương ứng
   |
   +-- Callback trả T thành công?
   |       -> gọi transactionManager.commit(status)
   |           (có thể thực sự commit, rollback do rollback-only,
   |            hoặc chỉ hoàn thành scope tham gia outer)
   |
   +-- Callback ném RuntimeException/Error?
   |       -> rollback(status) rồi truyền exception
   |
   +-- Sau completion thành công:
           -> trả kết quả T cho caller
```

**Ba tầng cần tách biệt:**

1. **Kết quả của callback:** giá trị do `return ...` trong Java tạo ra. Đó không phải thông điệp bảo đảm commit.
2. **Trạng thái transaction:** `TransactionStatus`, `isRollbackOnly()`, `isNewTransaction()` và quyết định của transaction manager. Không phải lúc nào callback cũng có physical transaction độc lập.
3. **Kết quả dữ liệu đã commit trên database:** chỉ kiểm chứng được khi giao dịch vật lý thật sự commit; nếu tham gia outer, có thể phải chờ outer hoàn thành.

Với implemention `TransactionTemplate` thông thường của Spring, callback được gọi trong `try`, runtime failure dẫn đến rollback, còn đường success gọi `commit(status)` rồi mới `return result`. Một transaction manager đặc biệt triển khai `CallbackPreferringPlatformTransactionManager` có thể xử lý callback qua nhánh riêng; vì vậy hãy hiểu đây là **hợp đồng Spring và luồng điển hình**, không dùng cấu trúc nội bộ như một API để lập trình nghiệp vụ.

## 2. `execute(TransactionCallback<T>)`: callback có giá trị trả về

Khai báo khái niệm:

```java
@FunctionalInterface
public interface TransactionCallback<T> {
    T doInTransaction(TransactionStatus status);
}
```

Đây là chữ ký được giản lược để học, không phải tệp bạn cần tự tạo; trong Spring, interface nằm ở `org.springframework.transaction.support.TransactionCallback`. Callback nhận `TransactionStatus` của scope hiện tại và trả `T`. Đầu ra của `execute` có thể là `null`; caller có trách nhiệm xử lý null.

Ví dụ dùng lambda:

```java
String invoiceCode = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO invoices(code) VALUES (?)", "INV-001"
    );
    return "INV-001";
});
```

Đây là **snippet trong service** đã có `template`, `jdbcTemplate` và bảng `invoices`, không phải chương trình độc lập. Trong một transaction mới không lỗi, Spring commit INSERT rồi mới trả chuỗi cho caller. Nếu commit thất bại thì caller **không nhận được return bình thường**; nó nhận exception do quá trình transaction completion.

### 2.1. Java generic `T` được suy luận như thế nào?

`T` là kiểu giá trị callback trả về:

```java
// Trả String:
String code = template.execute(status -> "INV-001");

// Trả Integer:
Integer count = template.execute(status ->
    jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM invoices", Integer.class
    )
);

// Trả một object không mutable:
record CreateResult(String code, int rowsAffected) {}
CreateResult result = template.execute(status -> {
    int updated = jdbcTemplate.update(
        "INSERT INTO invoices(code) VALUES (?)", "INV-002"
    );
    return new CreateResult("INV-002", updated);
});

// Trả Optional thay vì dùng null để biểu diễn không tìm thấy:
Optional<String> value = template.execute(status ->
    Optional.ofNullable(findCodeById(10L))
);
```

Đây là **các snippet độc lập về ý tưởng**, không ghép trực tiếp thành một class Java: `findCodeById` và schema cần có trong ứng dụng; `Optional` cần import. Giá trị `updated` của JDBC là số hàng mà statement tác động, **không phải chứng nhận commit cuối cùng** nếu transaction outer sau đó rollback.

**Một cách làm tốt:** trả DTO/record đơn giản đã được materialize trong transaction; tránh trả JPA entity còn cần lazy-loading về sau hoặc `Stream` mà caller chưa consume. Transaction đóng trước khi xử lý lazy evaluation có thể gây `LazyInitializationException` hoặc dùng connection ngoài transaction.

### 2.2. `return null` không phải một lệnh rollback

```java
String result = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO audit_event(label) VALUES (?)", "NONE"
    );
    return null;
});
```

Trong transaction mới, nếu SQL và commit đều thành công, bản ghi **vẫn được commit**, dù `result == null`. `null` chỉ là **giá trị kết quả Java**; nó không kích hoạt rollback.

Ngược lại, `return "SUCCESS"` cũng không chứng minh transaction đã được commit nếu callback đánh dấu rollback-only hoặc scope đang tham gia một transaction ngoài.

### 2.3. Không unbox kết quả nullable khi không chắc chắn

```java
// Dễ gặp NullPointerException ở caller:
int count = template.execute(status -> null);

// Rõ ràng hơn:
Integer countOrNull = template.execute(status -> null);
int safeCount = (countOrNull == null) ? 0 : countOrNull;
```

Đây là **hai snippet so sánh**, không nên chạy đồng thời trong ví dụ. Lỗi unbox xảy ra **sau khi execute đã trả giá trị `null`**; với physical transaction mới đã commit, `NullPointerException` ở caller không tự quay lại rollback giao dịch vừa hoàn tất. Nếu null có ý nghĩa nghiệp vụ, dùng `Optional` hoặc kiểu kết quả rõ ràng và kiểm tra trước khi sử dụng.

## 3. `executeWithoutResult`: chạy callback không cần kết quả

Kể từ Spring Framework 5.2, `TransactionOperations` (được `TransactionTemplate` triển khai) có phương thức tiện ích:

```java
template.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "UPDATE accounts SET last_reviewed = CURRENT_TIMESTAMP WHERE id = ?",
        42L
    );
});
```

Đây là snippet dùng bảng `accounts` có cột tương ứng. Callback nhận `TransactionStatus` nhưng **kiểu callback là `Consumer<TransactionStatus>`**, không trả `T`. Nó thích hợp cho thao tác update, delete, audit, batch processing khi caller chỉ cần biết transaction thành công hay thất bại qua control flow/exception.

So sánh:

| API | Lambda | Giá trị caller nhận | Khi dùng |
|---|---|---|---|
| `execute(TransactionCallback<T>)` | `status -> { ...; return value; }` | `T` hoặc `null` | Cần DTO, id, số lượng, kết quả truy vấn |
| `executeWithoutResult(Consumer<TransactionStatus>)` | `status -> { ...; }` | Không có giá trị (`void`) | Chỉ cần side effect DB và xử lý exception |
| `execute(status -> { ...; return null; })` | Có `return null` | `null` | Hợp lệ, nhưng kém rõ ý hơn `executeWithoutResult` cho callback void |

**Ghi nhớ:** `executeWithoutResult` không phải chạy transaction “fire-and-forget”. Nó vẫn **đồng bộ**: lời gọi chỉ hoàn tất sau khi transaction template hoàn thành scope và có thể ném exception như `execute`. Đừng nhầm với chạy async.

## 4. Bảng quyết định: callback kết thúc như thế nào?

Giả định các trường hợp đầu là một **physical transaction mới**, sử dụng Spring transaction manager JDBC thông thường và không có lỗi hệ thống phát sinh khi commit/rollback.

| Điều xảy ra trong callback | Quyết định transaction | Kết quả ở caller |
|---|---|---|
| Trả `"OK"`, không đánh dấu rollback-only | Commit | `execute(...)` trả `"OK"` sau completion |
| Trả `null`, không đánh dấu rollback-only | Commit | `execute(...)` trả `null` |
| Kết thúc callback `void` bình thường | Commit | `executeWithoutResult(...)` trả `void` |
| Ném `IllegalArgumentException` ra ngoài callback | Rollback | Ngoại lệ được truyền tới caller nếu rollback thành công |
| Ném `Error` ra ngoài callback | Rollback | `Error` được truyền lại nếu rollback thành công |
| Bắt ngoại lệ bên trong rồi trả `"HANDLED"` | Thường commit | `"HANDLED"`; không có rollback tự động chỉ vì exception đã bị catch |
| Gọi `status.setRollbackOnly()` rồi trả `"NOT_SAVED"` | Rollback toàn physical transaction mới | Caller **có thể nhận `"NOT_SAVED"` bình thường** |
| Callback thành công nhưng `commit()` thất bại | Không thể báo success bình thường | Caller nhận transaction/system exception; outcome thực tế cần đánh giá |
| Callback ném lỗi và rollback **cũng** thất bại | Không có guarantee cleanup thành công | Caller có thể nhận `TransactionException` của rollback, có thể che lỗi gốc |

**Ngoại lệ quan trọng với transaction đang tham gia outer:** `execute` có thể chỉ hoàn thành **logical scope** chứ không commit physical transaction. Transaction outer vẫn còn sống, và `UnexpectedRollbackException` có thể chỉ xuất hiện khi outer cố commit. Không suy luận “execute đã trả kết quả => dữ liệu đã được commit vật lý” nếu propagation đang là `REQUIRED` và có outer transaction.

## 5. `RuntimeException` và `Error`: rollback rồi truyền lỗi

Một pattern phổ biến:

```java
try {
    String result = template.execute(status -> {
        jdbcTemplate.update(
            "INSERT INTO payments(reference) VALUES (?)",
            "PAY-01"
        );

        if (paymentInvalid()) {
            throw new IllegalStateException("payment invalid");
        }
        return "PAY-01";
    });

    // Chỉ đến đây khi execute trả bình thường.
    sendSuccessResponse(result);
} catch (IllegalStateException ex) {
    // Callback đã làm transaction manager xử lý rollback,
    // nếu không xảy ra lỗi rollback nghiêm trọng.
    sendFailureResponse(ex.getMessage());
}
```

Đây là **snippet nghiệp vụ**, các hàm `paymentInvalid`/`sendSuccessResponse`/`sendFailureResponse` phải được ứng dụng cung cấp. Với transaction mới và lỗi unchecked thoát ra callback, Spring gọi rollback. Code trong nhánh `catch` ở caller diễn ra **sau** khi template đã cố gắng rollback; nó không “điều khiển việc rollback” bằng cách catch ở phía ngoài.

**Vì sao không catch rồi nuốt lỗi ở trong callback?** Vì `TransactionTemplate` chỉ biết callback cuối cùng trả bình thường; nó không có thông tin rằng một exception đã xảy ra rồi bị xử lý. Nếu nghiệp vụ thật sự cho phép tiếp tục và commit thì catch bên trong có thể đúng. Nếu muốn hủy tất cả, phải **ném lại unchecked exception** hoặc gọi `status.setRollbackOnly()`.

### 5.1. Catch **ngoài** callback và catch **trong** callback không giống nhau

**Catch bên ngoài** — lỗi thoát khỏi callback:

```java
try {
    template.executeWithoutResult(status -> {
        jdbcTemplate.update("INSERT INTO events(label) VALUES (?)", "FIRST");
        throw new IllegalStateException("bad input");
    });
} catch (IllegalStateException ex) {
    // TransactionTemplate đã gọi rollback trước khi lỗi đến đây.
}
```

**Catch bên trong** — callback trả bình thường:

```java
template.executeWithoutResult(status -> {
    jdbcTemplate.update("INSERT INTO events(label) VALUES (?)", "FIRST");
    try {
        throw new IllegalStateException("bad input");
    } catch (IllegalStateException ex) {
        // Giả sử đây là lỗi có thể bỏ qua.
        // Không ném lại và không đánh dấu rollback-only.
    }
    // TransactionTemplate thấy callback kết thúc bình thường:
    // có thể COMMIT INSERT "FIRST".
});
```

Các snippet giả định đã có bảng `events` và template/jdbcTemplate đúng datasource; không phải chương trình standalone. Điểm cần nhớ không nằm ở vị trí hình thức của `try/catch`, mà ở **exception cuối cùng có thoát khỏi callback boundary không** và status có **rollback-only** hay không.

### 5.2. Ngoại lệ từ JDBC/Spring data access

`JdbcTemplate` chuyển nhiều `SQLException` thành các `DataAccessException` **unchecked** (ví dụ `DuplicateKeyException`). Khi một `DataAccessException` thoát khỏi callback, nó kích hoạt rollback theo cơ chế unchecked. Nhưng nếu bạn bắt lỗi ở bên trong callback rồi bỏ qua, transaction manager có thể cố commit. Với một số database (ví dụ PostgreSQL), lỗi SQL có thể đặt transaction vào trạng thái aborted, khiến không thể tiếp tục/commit bình thường nếu không rollback về savepoint phù hợp. Vì vậy “nuốt `DataAccessException`” không phải cách khôi phục transaction an toàn.

Nếu cần bỏ qua một batch item lỗi nhưng vẫn giữ phần đúng, cân nhắc savepoint/`Propagation.NESTED` với manager/driver hỗ trợ hoặc tách transaction phù hợp, thay vì catch mọi lỗi rồi để transaction commit bừa.

## 6. `status.setRollbackOnly()`: rollback không cần ném exception

Khi nghiệp vụ quyết định không ghi dữ liệu dù callback vẫn có thể trả kết quả (ví dụ validation tổng hợp), dùng `TransactionStatus.setRollbackOnly()`:

```java
record SaveOutcome(boolean saved, String reason) {}

SaveOutcome outcome = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO reservations(ref) VALUES (?)", "R-01"
    );

    boolean valid = false; // Giá trị giả lập để minh họa.
    if (!valid) {
        status.setRollbackOnly();
        return new SaveOutcome(false, "quota exceeded");
    }
    return new SaveOutcome(true, "created");
});
```

Đây là snippet, cần schema `reservations` và biến template/jdbcTemplate trong service. Nếu template đang quản lý **physical transaction mới**, Spring thấy rollback-only khi xử lý completion, rollback dữ liệu rồi vẫn có thể trả `SaveOutcome(false, ...)` bình thường. Chính sách application phải coi `saved=false` là lỗi nghiệp vụ, **không trả HTTP 201 chỉ vì execute không ném exception**.

**Đừng viết như sau:**

```java
String result = template.execute(status -> {
    jdbcTemplate.update("INSERT INTO events(label) VALUES (?)", "x");
    status.setRollbackOnly();
    return "COMMITTED"; // Giá trị gây hiểu nhầm: dữ liệu bị rollback.
});
```

Đây là **snippet sai về ý nghĩa thông điệp**. Giá trị trả về không tự phản ánh outcome DB. Sửa thành DTO nói rõ `rejected`/`notSaved`, hoặc ném business exception nếu caller cần phân biệt rõ ràng qua control flow.

### 6.1. `isRollbackOnly()` và `isNewTransaction()`

Callback có thể truy vấn status:

```java
template.execute(status -> {
    boolean newPhysical = status.isNewTransaction();
    boolean marked = status.isRollbackOnly();

    // Dùng để ghi log/chẩn đoán, không dùng như lời hứa commit.
    return "new=" + newPhysical + ", rollbackOnly=" + marked;
});
```

Đây là snippet, không cần truyền status sang thread khác. `isNewTransaction()` giúp phân biệt scope bắt đầu physical transaction mới với scope tham gia transaction có sẵn. `isRollbackOnly()` phản ánh rollback-only tại thời điểm kiểm tra; một outer transaction hoặc manager có thể quyết định rollback sau đó, nên `false` **không bảo đảm commit về sau**.

### 6.2. Khi có transaction outer

Giả sử outer đã mở transaction A. Một `TransactionTemplate` bên trong với mặc định `PROPAGATION_REQUIRED` sẽ **tham gia** A:

```text
outer transaction A bắt đầu
    |
    +-- inner TransactionTemplate.execute(...)
    |     status.isNewTransaction() == false
    |     inner đánh dấu rollback-only
    |     inner có thể trả về giá trị
    |
    +-- outer vẫn chạy, tưởng có thể commit
    |
    +-- outer commit A -> rollback vì global rollback-only
                            có thể ném UnexpectedRollbackException
```

Đây là mô hình logic, không phải một output universal cho mọi manager. Khi nội bộ đánh dấu rollback-only trên logical scope tham gia A, A có thể bị đánh dấu **global rollback-only**; outer cố commit sẽ gặp `UnexpectedRollbackException` để không tưởng rằng commit thành công.

Đặc biệt, **không dùng kết quả trả về từ inner `execute` như chứng nhận commit vật lý**. Chỉ khi transaction ngoài hoàn tất mới biết kết quả toàn transaction A.

Nếu cần tách một công việc phải commit riêng, `PROPAGATION_REQUIRES_NEW` có thể tạo transaction vật lý độc lập, nhưng vẫn có rủi ro pool/lock và bất nhất nghiệp vụ giữa inner/outer. Nếu cần partial rollback, `NESTED`/savepoint có semantics khác; không tự động đồng nhất với việc gọi `setRollbackOnly()` ở scope `REQUIRED`.

## 7. Checked exception: xử lý thế nào khi callback không khai báo `throws`?

`TransactionCallback<T>.doInTransaction(TransactionStatus)` **không** khai báo `throws IOException` hay `throws SQLException`. Điều đó có nghĩa lambda theo giao diện này không thể trực tiếp để một checked exception chưa xử lý thoát ra trong Java.

Ví dụ **không biên dịch**:

```java
String content = template.execute(status -> {
    return Files.readString(Path.of("input.txt")); // IOException chưa xử lý.
});
```

Đây là **ví dụ cố ý sai**, `Files.readString` ném checked `IOException`. Java compiler yêu cầu xử lý nó.

### 7.1. Chuyển checked exception thành unchecked exception khi cần rollback

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

String content = template.execute(status -> {
    try {
        String data = Files.readString(Path.of("input.txt"));
        jdbcTemplate.update(
            "INSERT INTO documents(text_content) VALUES (?)", data
        );
        return data;
    } catch (IOException ex) {
        throw new UncheckedIOException("cannot load document", ex);
    }
});
```

Đây là snippet cần `documents`, `template` và `jdbcTemplate`. Nếu đọc file lỗi, `UncheckedIOException` thoát khỏi callback, Spring rollback transaction DB. Sự thất bại đọc file không phải thứ DB rollback được, nhưng những SQL đã thực thi **trong cùng transaction** sẽ được rollback.

Đối với checked exception ứng dụng, có thể dùng **unchecked business exception** với `cause`:

```java
try {
    template.execute(status -> {
        try {
            invokeCheckedService();
            return "OK";
        } catch (CheckedBusinessException ex) {
            throw new IllegalStateException("cannot finish business action", ex);
        }
    });
} catch (IllegalStateException ex) {
    // Xem getCause() để nhận diện loại lỗi gốc nếu cần.
}
```

Đây là snippet với các type/method nghiệp vụ tượng trưng. Không nên bọc **mọi** checked exception thành một loại runtime duy nhất nếu caller cần phân biệt lỗi retryable, lỗi validation hay lỗi hệ thống; hãy thiết kế exception hierarchy và log nguyên nhân phù hợp.

### 7.2. Bắt checked exception, rollback-only rồi trả kết quả nghiệp vụ

Không phải lỗi nào cũng cần throw ra caller. Ví dụ một import job muốn trả `ImportResult(success=false, reason=...)` thay vì ném exception:

```java
record ImportResult(boolean saved, String message) {}

ImportResult result = template.execute(status -> {
    try {
        String csv = readCsvChecked();
        storeCsvInDatabase(csv);
        return new ImportResult(true, "saved");
    } catch (IOException ex) {
        status.setRollbackOnly();
        return new ImportResult(false, "cannot read CSV");
    }
});
```

Đây là snippet: `readCsvChecked` và `storeCsvInDatabase` phải được định nghĩa trong ứng dụng. **Bắt exception và gắn rollback-only là hai hành động riêng**. Nếu quên `setRollbackOnly()` trong nhánh trả lỗi, những SQL trước đó có thể được commit.

Trong transaction mới, kết quả `ImportResult(false, ...)` có thể đến caller **mà không có exception** dù DB rollback; bạn phải xử lý `saved=false` chứ không giả định `execute` trả bình thường đồng nghĩa thành công.

### 7.3. Không nhầm với quy tắc checked exception của `@Transactional`

`@Transactional` (declarative transaction management) mặc định rollback khi unchecked `RuntimeException`/`Error`, còn checked exception thông thường không rollback nếu không cấu hình `rollbackFor`. Nhưng `TransactionTemplate` có hợp đồng callback **không khai báo checked exception**; không thể copy máy móc quy tắc “checked exception không rollback” sang việc trả kết quả từ callback của `TransactionTemplate`.

**Chi tiết triển khai Spring:** Trong nhánh transaction manager thông thường (không phải callback-preferring), `TransactionTemplate.execute` có một nhánh phòng vệ `catch (Throwable)`: nếu một checked throwable bất thường vượt qua giao diện (chẳng hạn kỹ thuật sneaky throw), Spring cố rollback rồi bọc vào `UndeclaredThrowableException`. Đây **không phải pattern khuyên dùng**; hãy xử lý/convert checked exception rõ ràng để code Java dễ đọc và lỗi có ngữ nghĩa.

### 7.4. Lỗi từ callback và lỗi rollback có thể chồng lên nhau

Nếu callback ném `IllegalStateException` nhưng quá trình rollback lại thất bại do lỗi kết nối, caller có thể nhận `TransactionSystemException` hay một exception khác liên quan rollback thay vì exception nghiệp vụ ban đầu. Spring cố bảo lưu/tham chiếu lỗi gốc trong một số trường hợp, nhưng đừng viết code chỉ bắt một exception class và giả định mọi rollback đều thành công.

Với lỗi transaction system, cần log cả exception và cause, đánh dấu request thất bại, không tự động retry một thao tác không idempotent nếu chưa rõ DB có commit/rollback đến đâu.

## 8. Ví dụ chạy được: kiểm chứng return, void, exception, catch, rollback-only và null

Demo dùng **Java 17**, **Spring JDBC**, **H2 in-memory** và **`JdbcTransactionManager`**. Nó không cần Spring Boot, web server hay AOP proxy: `TransactionTemplate` nhận transaction manager trực tiếp và thực hiện mọi callback đồng bộ trên JDBC connection được Spring quản lý.

Chương trình chạy **bảy tình huống**:

1. Callback trả `String` sau một INSERT thành công.
2. Callback void ghi một INSERT qua `executeWithoutResult`.
3. Callback ném unchecked exception: INSERT bị rollback.
4. Callback catch exception ở bên trong rồi trả kết quả: INSERT được commit.
5. Callback gọi `status.setRollbackOnly()` nhưng vẫn trả `String`: INSERT bị rollback, caller vẫn nhận chuỗi.
6. Helper ném checked `IOException` được chuyển thành `UncheckedIOException`: INSERT rollback.
7. Callback trả `null`: INSERT vẫn commit, caller nhận `null`.

Sau đó một callback đọc ra danh sách labels được commit, cho thấy **giá trị return và kết quả database là hai điều cần quan sát riêng**.

### 8.1. Cấu trúc dự án

```text
transaction-template-callback-demo/
├── pom.xml
└── src/main/java/com/example/callback/Main.java
```

### 8.2. Tệp `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>transaction-template-callback-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-jdbc` kéo theo transaction infrastructure. H2 là database trong bộ nhớ. Các version cố định giúp tái lập demo với JDK 17+. Trong dự án thực, quản lý dependency bằng BOM/version được hỗ trợ và thay `DriverManagerDataSource` bằng connection pool đã cấu hình phù hợp.

### 8.3. Tệp `src/main/java/com/example/callback/Main.java`

```java
package com.example.callback;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class Main {

    private static void add(JdbcTemplate jdbc, String label) {
        jdbc.update(
            "INSERT INTO callback_events(label) VALUES (?)",
            label
        );
    }

    private static int rows(JdbcTemplate jdbc) {
        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM callback_events",
            Integer.class
        );
        return count;
    }

    private static List<String> labels(JdbcTemplate jdbc) {
        return jdbc.queryForList(
            "SELECT label FROM callback_events ORDER BY id",
            String.class
        );
    }

    // Mô phỏng API Java có checked exception.
    private static void checkedFailure() throws IOException {
        throw new IOException("io-unavailable");
    }

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:callback_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.execute(
            "CREATE TABLE callback_events (" +
            "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, " +
            "label VARCHAR(80) NOT NULL)"
        );

        JdbcTransactionManager manager = new JdbcTransactionManager(ds);
        TransactionTemplate tx = new TransactionTemplate(manager);

        // 1. Callback trả String, transaction commit.
        String first = tx.execute(status -> {
            add(jdbc, "A");
            return "A-created";
        });
        System.out.println("success result=" + first +
                " rows=" + rows(jdbc));

        // 2. Callback void, transaction commit.
        tx.executeWithoutResult(status -> add(jdbc, "B"));
        System.out.println("void rows=" + rows(jdbc));

        // 3. Unchecked exception thoát khỏi callback -> rollback.
        try {
            tx.execute(status -> {
                add(jdbc, "C");
                throw new IllegalStateException("boom");
            });
        } catch (IllegalStateException ex) {
            System.out.println("outside caught=" + ex.getMessage());
        }
        System.out.println("after outside catch rows=" + rows(jdbc));

        // 4. Exception đã được bắt TRONG callback -> commit.
        String handled = tx.execute(status -> {
            add(jdbc, "D");
            try {
                throw new IllegalArgumentException("local");
            } catch (IllegalArgumentException ex) {
                return "handled-inside";
            }
        });
        System.out.println("inside result=" + handled +
                " rows=" + rows(jdbc));

        // 5. Đánh dấu rollback-only nhưng vẫn trả String.
        String rejected = tx.execute(status -> {
            add(jdbc, "E");
            status.setRollbackOnly();
            return "E-not-committed";
        });
        System.out.println("rollbackOnly result=" + rejected +
                " rows=" + rows(jdbc));

        // 6. Checked IOException -> chuyển thành UncheckedIOException.
        try {
            tx.execute(status -> {
                add(jdbc, "F");
                try {
                    checkedFailure();
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
                return "never-returned";
            });
        } catch (UncheckedIOException ex) {
            System.out.println(
                "checked adapted=" + ex.getCause().getMessage()
            );
        }
        System.out.println("after checked failure rows=" + rows(jdbc));

        // 7. return null KHÔNG phải rollback.
        String noValue = tx.execute(status -> {
            add(jdbc, "G");
            return null;
        });
        System.out.println("null result=" + (noValue == null) +
                " rows=" + rows(jdbc));

        // Trả một List<String> được lấy đầy đủ trong transaction.
        List<String> committed = tx.execute(status -> labels(jdbc));
        System.out.println("committed labels=" + committed);
    }
}
```

**Điểm cần xem trong chương trình:**

- `tx.execute(...)` chạy xong mới có giá trị `String` hoặc `List<String>`; không có `@Transactional`/proxy ẩn nào cần thiết cho callback trong demo.
- `JdbcTemplate` dùng datasource được cùng transaction manager quản lý. Các câu lệnh `add(...)` tham gia JDBC transaction của callback.
- Mỗi lần `tx.execute` ở `main` được gọi **khi chưa có transaction ngoài**, vì vậy với propagation mặc định `REQUIRED` mỗi callback tạo **một physical transaction mới**. Đây là điều kiện khiến hành vi rollback-only trả bình thường ở case 5 dễ dự đoán.
- `checkedFailure()` khai báo `throws IOException`, được catch rồi bọc unchecked ngay bên trong lambda. Không có sneaky throw.
- `labels(jdbc)` được materialize thành `List<String>` trong callback; không trả stream lazy sau khi transaction đóng.
- Mỗi case in `rows(jdbc)` **sau** completion, sử dụng connection mới khi không còn Spring transaction active, để xác minh dữ liệu thực sự đã commit/rollback.

### 8.4. Chạy và output dự kiến

Từ thư mục `transaction-template-callback-demo` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.callback.Main
```

Các dòng **do chương trình** in ra, không kể log Maven/driver tùy môi trường:

```text
success result=A-created rows=1
void rows=2
outside caught=boom
after outside catch rows=2
inside result=handled-inside rows=3
rollbackOnly result=E-not-committed rows=3
checked adapted=io-unavailable
after checked failure rows=3
null result=true rows=4
committed labels=[A, B, D, G]
```

Đọc theo timeline:

| Case | Callback có insert gì? | Callback trả/ném gì? | Dữ liệu còn lại |
|---|---|---|---|
| 1 | A | Trả `"A-created"` | A được commit |
| 2 | B | Void, kết thúc bình thường | A và B |
| 3 | C | `IllegalStateException("boom")` thoát khỏi callback | C bị rollback |
| 4 | D | Bắt lỗi trong lambda, trả `"handled-inside"` | D được commit |
| 5 | E | `setRollbackOnly()`, trả `"E-not-committed"` | E bị rollback dù caller có chuỗi |
| 6 | F | Checked IOException được chuyển thành UncheckedIOException | F bị rollback |
| 7 | G | Trả `null` bình thường | G được commit |

Đây là ví dụ Java **được thiết kế để chạy được** với các dependency đã khai báo. Kết quả trên là **dự kiến theo semantics của Spring JDBC/H2**, không phải kết quả đo từ một lần chạy Maven trong bài này. Nếu dùng engine khác hoặc thay propagation, hãy tự chạy tích hợp và đọc exception/commit thực tế.

## 9. Phân biệt lỗi nghiệp vụ, lỗi transaction và lỗi sau commit

Có ít nhất ba nguồn lỗi:

### 9.1. Lỗi trong callback trước khi commit

Ví dụ validation thất bại hoặc SQL ném `DataAccessException`. `RuntimeException` thoát ra sẽ khiến template yêu cầu rollback. Nếu rollback thành công, exception gốc thường được truyền tới caller.

**Phương án:** đặt rollback policy rõ ràng, trả business error đúng loại, không tiếp tục coi request thành công.

### 9.2. Lỗi trong bước transaction completion

Callback có thể **trả kết quả hợp lệ**, nhưng `transactionManager.commit(status)` vẫn có thể thất bại: deadlock, serialization failure, constraint kiểm tra trễ, mất kết nối, database unavailable, hoặc lỗi ở synchronization callback.

```text
callback tính result="OK"
        |
        v
commit(status)
   |
   +-- thành công -> execute() trả "OK"
   |
   +-- thất bại -> execute() ném exception,
                   caller KHÔNG nhận return bình thường
```

**Không gửi response "thành công" hoặc publish message bên trong callback trước khi commit chỉ vì đã tạo `result`.** Đặc biệt với timeout/connection loss tại COMMIT, có trường hợp application không thể biết chắc server đã commit hay chưa. Hãy dùng idempotency key, kiểm tra transaction outcome hoặc reconciliation trước khi retry thao tác không idempotent.

### 9.3. Side effect sau callback nhưng trước/ngoài database completion

Gửi email, HTTP request, message, file write hoặc cập nhật cache trong callback **không được rollback cùng JDBC transaction**. Nếu SQL về sau rollback, side effect vẫn có thể đã xảy ra.

```java
String id = template.execute(status -> {
    String generatedId = createOrderInDatabase();
    emailService.sendOrderCreated(generatedId); // Có side effect.
    return generatedId;
});
```

Đây là snippet với các method ứng dụng tượng trưng. Có thể gửi email thành công nhưng commit DB thất bại. Đừng khắc phục bằng một `catch` vô điều kiện rồi gửi mail bù; hãy cân nhắc transactional outbox, after-commit hooks (với giới hạn riêng) hoặc workflow idempotent.

Kể cả code gọi `emailService.send...` **sau** `execute` trả bình thường, một transaction outer đang còn mở có thể chưa commit vật lý. Khi cần thông báo sau khi **transaction cuối cùng** commit, phải căn theo boundary vật lý và cơ chế phối hợp tương ứng.

## 10. Giá trị lỗi như `Optional.empty()`, `Either.Left` hoặc `Result.failure` không tự rollback

Trong Java, có thể thiết kế API không throw mà trả một “kết quả thất bại”:

```java
record SaveDecision(boolean accepted, String reason) {}

SaveDecision decision = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO orders(reference) VALUES (?)", "A-100"
    );

    if (validationFailed()) {
        return new SaveDecision(false, "invalid order");
    }
    return new SaveDecision(true, "created");
});
```

Đây là snippet giả lập `validationFailed`. Nếu branch lỗi chỉ `return new SaveDecision(false,...)` mà không ném exception hoặc `setRollbackOnly()`, transaction mới **có thể commit INSERT**. Spring TransactionTemplate **không tự phân tích semantics** của DTO, `Optional.empty()`, `Either`, `Try`, `ResponseEntity`, `CompletableFuture` hay bất kỳ lớp kết quả custom nào để quyết định rollback.

Một cách đúng nếu muốn rollback khi `accepted=false`:

```java
SaveDecision decision = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO orders(reference) VALUES (?)", "A-101"
    );

    if (validationFailed()) {
        status.setRollbackOnly();
        return new SaveDecision(false, "invalid order");
    }
    return new SaveDecision(true, "created");
});
```

Cách khác: ném unchecked business exception và catch **ngoài callback**. Lựa chọn nào phù hợp phụ thuộc API contract:

- **Exception** tốt khi transaction thất bại bất thường hoặc caller buộc phải xử lý lỗi; rollback xảy ra do exception thoát callback.
- **Result object + rollback-only** tốt khi muốn diễn đạt lỗi nghiệp vụ dự kiến và trả dữ liệu có cấu trúc; caller **bắt buộc** đọc trạng thái kết quả.
- **Result object không rollback** phù hợp nếu lỗi được báo nhưng thao tác DB trước đó **được chủ động phép commit** (ví dụ ghi nhận một bản audit nghiệp vụ); không coi mọi lỗi kết quả là rollback mặc định.

Đừng dựa vào Spring 6.1+ xử lý một số kiểu return value đặc biệt của **declarative `@Transactional` interception** rồi suy rằng `TransactionTemplate` sẽ có policy tương tự cho custom callback result. Hai cơ chế có đường xử lý khác nhau; với template, hãy quyết định rollback rõ ràng bằng exception hoặc `TransactionStatus`.

## 11. `TransactionTemplate` và exception trong transaction lồng nhau

### 11.1. Mặc định `PROPAGATION_REQUIRED`

Mặc định `TransactionTemplate` có `PROPAGATION_REQUIRED`:

- Nếu chưa có transaction cùng manager/resource, nó mở mới.
- Nếu đã có transaction hợp lệ, nó **tham gia** transaction vật lý đó.
- Nếu inner scope đánh dấu rollback-only hoặc ném lỗi không được xử lý trong transaction outer, phần xử lý outer có thể cuối cùng rollback toàn transaction.

Ví dụ khái niệm:

```java
TransactionTemplate outer = new TransactionTemplate(manager);
TransactionTemplate inner = new TransactionTemplate(manager);

outer.executeWithoutResult(outerStatus -> {
    insertOuterRow();

    try {
        inner.executeWithoutResult(innerStatus -> {
            insertInnerRow(); // Tham gia cùng physical transaction A.
            throw new IllegalStateException("inner invalid");
        });
    } catch (IllegalStateException expected) {
        // Inner đã yêu cầu rollback. Vì inner tham gia A,
        // A có thể đã bị đánh dấu rollback-only.
    }

    insertAnotherOuterRow();
    // Có thể gặp UnexpectedRollbackException khi outer cố commit.
});
```

Đây là **snippet minh họa**; `manager`, `insertOuterRow`... chưa được định nghĩa. Với manager dựa trên `AbstractPlatformTransactionManager` và mặc định đánh dấu global rollback-only khi một participating transaction thất bại, outer không thể commit thành công bằng cách chỉ nuốt exception. `UnexpectedRollbackException` là thông báo rằng physical transaction không thể được commit như caller mong đợi.

### 11.2. `PROPAGATION_REQUIRES_NEW`

Nếu inner phải commit/rollback độc lập, có thể dùng:

```java
TransactionTemplate independent = new TransactionTemplate(manager);
independent.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
```

Trong snippet này, cần import `TransactionDefinition` và có `manager`. Khi outer A đang mở, Spring suspend A, tạo transaction B; B hoàn thành rồi resume A. Inner B lỗi và được catch trong outer **không tự** đánh dấu A rollback-only, nhưng nếu unchecked exception tiếp tục thoát khỏi callback outer thì A vẫn có thể rollback.

**Đánh đổi:** B thường cần connection riêng và có thể commit ngay cả khi A rollback, gây rủi ro connection pool/lock hoặc sự không nhất quán nghiệp vụ. Không dùng REQUIRES_NEW chỉ để tránh hiểu xử lý exception.

### 11.3. `PROPAGATION_NESTED` hoặc savepoint

Khi muốn **partial rollback** trong một physical transaction JDBC, `PROPAGATION_NESTED` có thể dùng savepoint, nếu transaction manager/driver hỗ trợ. Nó khác với `REQUIRES_NEW` vì không commit vật lý độc lập: outer rollback toàn bộ vẫn loại cả phần inner từng thành công.

`TransactionStatus` cũng kế thừa `SavepointManager`, cho phép chủ động `createSavepoint()`, `rollbackToSavepoint(...)` và `releaseSavepoint(...)` nếu có hỗ trợ. Đây là một chiến lược **thay thế có chủ đích**, không phải mặc định của `execute`.

## 12. Những lỗi lập trình thường gặp khi return và catch exception

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| `catch (Exception ignored)` bên trong callback rồi trả `"SUCCESS"` | Transaction có thể commit dù nghiệp vụ thất bại | Catch đúng lỗi phục hồi, ném lại hoặc `setRollbackOnly()` |
| Trả DTO `success=false` mà không đánh dấu rollback | Có thể commit dữ liệu trước đó | Định nghĩa result contract và rollback policy rõ ràng |
| `status.setRollbackOnly()` rồi trả `"COMMITTED"` | Caller bị đánh lừa vì rollback có thể xảy ra | Trả `notSaved`/`rejected` hoặc throw |
| Catch exception ngoài `execute` rồi tin rollback chắc chắn thành công | Rollback có thể bị lỗi; commit outcome đôi khi không chắc | Kiểm tra `TransactionException`/cause và tính idempotent trước retry |
| Trả JPA lazy entity/stream để xử lý ngoài callback | Transaction đóng, lazy access có thể lỗi hoặc chạy ngoài scope | Materialize DTO trong callback |
| Trả `null` vào biến primitive | `NullPointerException` sau transaction | Dùng nullable type/Optional, kiểm tra null |
| Đặt `try/catch` ở caller nhưng gửi email trong callback | Email đã gửi dù DB rollback | Outbox hoặc after-commit phù hợp |
| Nghĩ callback trả `CompletableFuture` sẽ giữ transaction đến khi Future xong | Transaction kết thúc khi callback trả, async code chạy ngoài scope | Quản lý transaction trong worker thực thi, không chuyền status/thread-bound resource |
| Dùng `status` sau khi callback trả hoặc từ thread khác | Status/resource không còn trong scope hợp lệ | Chỉ dùng trong callback đồng bộ |
| Dùng `TransactionTemplate` inner REQUIRED nhưng tưởng commit độc lập | Outer rollback có thể hủy toàn bộ; `UnexpectedRollbackException` | Hiểu physical boundary, chọn propagation phù hợp |
| Chạy callback với manager của datasource A nhưng SQL dùng datasource B | SQL B có thể nằm ngoài transaction của A | Chỉ định manager/resource đúng và test đa datasource |
| Gọi `TransactionAspectSupport.currentTransactionStatus()` trong callback template không có AOP invocation | Có thể gặp `NoTransactionException` | Dùng `status` được truyền vào callback |
| Đưa checked exception ra lambda trực tiếp | Lỗi biên dịch Java | Catch và wrap unchecked hoặc return result + rollback-only |
| Lặp lại callback tự động sau commit failure mà không idempotency | Có thể ghi trùng khi outcome không rõ | Idempotency key, retry có kiểm soát, reconciliation |
| Nghĩ `executeWithoutResult` là async | Return sai thời điểm hoặc giả định cleanup sai | Hiểu nó vẫn đồng bộ; không trả object |
| Tự gọi `commit()`/`rollback()` trên JDBC connection bên trong template | Làm rối transaction manager và connection lifecycle | Để Spring quản lý, sử dụng status để yêu cầu rollback |

## 13. Kiểm thử và chẩn đoán trong dự án thực

### 13.1. Integration test phải kiểm tra cả return lẫn DB

Một unit test mock callback có thể xác nhận Java trả DTO, nhưng không chứng minh transaction commit/rollback. Với bài toán quan trọng, chạy integration test trên DB thật hoặc Testcontainers:

1. Bắt đầu từ dữ liệu có trạng thái rõ ràng.
2. Gọi service dùng `TransactionTemplate.execute`.
3. Kiểm tra giá trị trả về hoặc exception tại caller.
4. Sau khi physical transaction hoàn tất, dùng transaction/connection khác truy vấn dữ liệu đã commit.
5. Test thêm lỗi được catch trong callback, `setRollbackOnly()`, lỗi constraint, lỗi commit giả lập, transaction outer tham gia và rollback-only propagation.
6. Nếu cần retry, test idempotency khi callback có side effect ngoài DB.
7. Theo dõi `DataAccessException` và `TransactionException` từ manager, không chỉ class exception ở business layer.

### 13.2. Chẩn đoán status trong callback

```java
String info = template.execute(status -> {
    boolean newTx = status.isNewTransaction();
    boolean rollbackOnly = status.isRollbackOnly();
    boolean actualTx =
        TransactionSynchronizationManager.isActualTransactionActive();

    return "new=" + newTx +
        ", marked=" + rollbackOnly +
        ", active=" + actualTx;
});
```

Đây là snippet, cần import `TransactionSynchronizationManager`. Trong transaction manager JDBC và callback mở physical transaction mới, thường thấy `new=true, marked=false, active=true`. Nhưng đừng dùng `isActualTransactionActive()` làm chứng nhận commit: cờ này chỉ mô tả trạng thái thread-bound hiện tại, không phải kết quả completion.

### 13.3. Logging hữu ích

Có thể bật DEBUG cho:

```text
org.springframework.transaction
org.springframework.jdbc.datasource
```

Dùng logging để quan sát begin, participating, commit, rollback, suspend/resume và exception. Tùy Spring version/manager, thông điệp có thể khác. Với production, tránh log PII và SQL parameters nhạy cảm. Luôn kiểm tra DB state thực tế sau completion thay vì chỉ suy từ một dòng “commit requested”.

### 13.4. `TransactionOperations` giúp testable hơn

`TransactionTemplate` implements `TransactionOperations`. Ở service, có thể inject giao diện:

```java
public final class OrderWriter {
    private final TransactionOperations transactions;
    private final OrderRepository orders;

    public OrderWriter(
            TransactionOperations transactions,
            OrderRepository orders) {
        this.transactions = transactions;
        this.orders = orders;
    }

    public String save(String input) {
        return transactions.execute(status -> orders.insert(input));
    }
}
```

Đây là class minh họa, cần `OrderRepository` và bean `TransactionOperations` được cấu hình (có thể dùng `TransactionTemplate`). Thiết kế dựa trên giao diện giúp thay bằng mock/stub ở unit tests; tuy nhiên **integration test** vẫn cần để xác nhận rollback/commit thật. Đừng thay test database bằng một mock cho tất cả nghiệp vụ có ràng buộc transaction.

## 14. Lựa chọn mẫu xử lý lỗi phù hợp

**Mẫu A — exception là failure, caller xử lý qua catch**

```java
try {
    Receipt receipt = template.execute(status -> {
        return writeAndBuildReceipt();
    });
    return HttpResult.success(receipt);
} catch (BusinessRuntimeException ex) {
    return HttpResult.rejected(ex.getMessage());
}
```

Snippet: `Receipt`, `HttpResult`, `BusinessRuntimeException` và `writeAndBuildReceipt` do ứng dụng định nghĩa. Thích hợp khi lỗi là ngoại lệ (không phải outcome thông thường) và muốn transaction rollback một cách tự nhiên.

**Mẫu B — business rejection là kết quả có cấu trúc**

```java
record Outcome(boolean committed, String reason) {}

Outcome outcome = template.execute(status -> {
    if (!isValid()) {
        status.setRollbackOnly();
        return new Outcome(false, "validation failed");
    }
    writeData();
    return new Outcome(true, "accepted");
});
```

Đây là snippet, `isValid`/`writeData` chưa được khai báo. Chữ `committed` chỉ chính xác khi **scope đang quản lý physical transaction mới và completion thành công**. Nếu code có thể tham gia outer, nên đổi tên thành `accepted`/`savedInScope` để không tuyên bố commit vật lý quá sớm.

**Mẫu C — thao tác không có kết quả**

```java
template.executeWithoutResult(status -> {
    verifyPreconditions();
    performUpdates();
});
```

Đây là snippet; thất bại cần throw unchecked hoặc mark rollback-only. Dùng `executeWithoutResult` giúp API thể hiện rõ business code không sinh output.

**Mẫu D — checked exception khi đọc resource bên ngoài**

```java
ImportOutcome outcome = template.execute(status -> {
    try {
        InputData input = readFromExternalResource();
        writeDb(input);
        return ImportOutcome.ok();
    } catch (IOException ex) {
        status.setRollbackOnly();
        return ImportOutcome.failed("resource unavailable");
    }
});
```

Đây là snippet, các kiểu/factory tự định nghĩa. Đảm bảo cơ chế xử lý khi `writeDb` ném `DataAccessException` vẫn rõ ràng; chỉ `IOException` được catch ở đây.

**Mẫu nào cũng phải trả lời ba câu:** (1) Ai quyết định thất bại? (2) Có rollback toàn transaction không, hay chỉ một phần? (3) Caller có thể biết **thực tế đã commit vật lý chưa** ở thời điểm nhận kết quả?

## 15. Các câu hỏi tự kiểm tra

1. **`execute` khác `executeWithoutResult` như thế nào?** — Cả hai chạy transaction đồng bộ; `execute` trả `T`/`null`, `executeWithoutResult` không trả giá trị.
2. **Callback ném unchecked exception ra ngoài sẽ ra sao?** — Template yêu cầu rollback, sau đó truyền exception (nếu rollback không tự lỗi).
3. **Callback catch lỗi rồi trả bình thường thì Spring có biết để rollback không?** — Không tự biết; nếu không có rollback-only, nó có thể commit.
4. **`return null` có nghĩa rollback không?** — Không.
5. **`status.setRollbackOnly()` rồi trả `"OK"` có commit được không?** — Với physical transaction mới thông thường, dữ liệu rollback nhưng caller vẫn có thể nhận `"OK"`; kết quả như vậy gây hiểu nhầm.
6. **Callback có thể trực tiếp ném `IOException` mà không catch không?** — Không theo chữ ký `TransactionCallback<T>` vì nó không khai báo checked throws.
7. **Có phải checked exception luôn dẫn đến commit trong TransactionTemplate như mặc định `@Transactional`?** — Không. Phải xử lý checked exception trong callback; nếu chuyển thành unchecked/mark rollback-only thì rollback.
8. **Khi callback trả `CompletableFuture`, transaction có tự chờ tương lai hoàn tất không?** — Không. `TransactionTemplate` xử lý callback đồng bộ, không kéo dài transaction tới asynchronous completion.
9. **Khi inner `execute` tham gia transaction A, giá trị return chứng minh A đã commit chưa?** — Chưa. A có thể rollback sau đó.
10. **Nếu callback thành công nhưng commit thất bại, caller sẽ thế nào?** — Không nhận return bình thường; nhận lỗi transaction. Cần đánh giá outcome thực tế trước retry.
11. **Vì sao gửi message trong callback có thể tạo bất nhất?** — Side effect broker/email không tự rollback cùng JDBC transaction nếu DB commit thất bại.
12. **Nên kiểm chứng gì trong integration test?** — Cả giá trị return/exception và dữ liệu sau physical transaction completion, qua DB connection khác nếu cần.

## 16. Tóm tắt

- Dùng `execute(TransactionCallback<T>)` khi cần trả dữ liệu; dùng `executeWithoutResult` khi chỉ cần thao tác.
- `return` tạo **Java result**, không phải cam kết DB. `null` không rollback; `"SUCCESS"` không thay thế kiểm tra transaction completion.
- Unchecked `RuntimeException`/`Error` thoát callback → Spring rollback rồi truyền lỗi trong luồng thông thường.
- Catch lỗi **bên trong** callback rồi nuốt → có thể commit; nếu muốn rollback, throw tiếp hoặc `status.setRollbackOnly()`.
- `setRollbackOnly()` trong transaction mới có thể cho phép callback trả **business result** dù rollback; khi tham gia outer, cần tính đến rollback-only và `UnexpectedRollbackException`.
- Checked exception không được khai báo trong `TransactionCallback<T>`: catch/convert unchecked hoặc catch + rollback-only + result rõ ràng.
- `TransactionTemplate` quản lý transaction **đồng bộ**. Future/lazy stream/external side effect không tự đi theo JDBC transaction.
- Với lỗi commit/rollback, không khẳng định transaction đã thành công hoặc retry mù quáng; kiểm tra dữ liệu và thiết kế idempotency.

## Tài liệu tham khảo

- Spring Framework — Programmatic Transaction Management (`TransactionTemplate`, callback, rollback-only): https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework 6.2 — `TransactionTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework — `TransactionOperations` (`executeWithoutResult`): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionOperations.html
- Spring Framework — `TransactionCallback<T>` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionCallback.html
- Spring Framework — `TransactionStatus` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — `UnexpectedRollbackException` và transaction propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Declarative rollback rules, để đối chiếu checked/unchecked: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — `PlatformTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html
- Spring Framework — Source `TransactionTemplate.java` và cách xử lý rollback/checked Throwable: https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-tx/src/main/java/org/springframework/transaction/support/TransactionTemplate.java

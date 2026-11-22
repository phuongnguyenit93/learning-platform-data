# Đọc chuỗi nguyên nhân, SQLState và log mà không lộ dữ liệu nhạy cảm

Khi Spring Data JPA gặp lỗi, exception nhìn thấy ở tầng service thường chỉ là lớp ngoài cùng của nhiều lớp bọc. Nguyên nhân có thể nằm ở Spring exception translation, JPA, Hibernate, JDBC hoặc chính hệ quản trị cơ sở dữ liệu. Chẩn đoán đúng cần đọc chuỗi nguyên nhân (cause chain), tìm SQLException liên quan, diễn giải SQLState cùng vendor error code và đối chiếu với log có đủ ngữ cảnh.

Log phục vụ chẩn đoán cũng có thể làm lộ dữ liệu khách hàng, thông tin đăng nhập, giá trị tham số truy vấn hoặc nội dung nghiệp vụ. Vì vậy, cần tách thông tin kỹ thuật cần thiết khỏi dữ liệu nhạy cảm, dùng correlation ID để nối các log cùng một request và chỉ bật log SQL/bind parameter ở môi trường kiểm soát.

## 1. Vì sao exception có nhiều lớp?

Một thao tác repository có thể đi qua nhiều tầng:

1. Service gọi Spring Data repository.
2. Spring Data gọi EntityManager và JPA provider.
3. Hibernate tạo SQL và gọi JDBC.
4. JDBC driver gửi lệnh đến database.
5. Database trả lỗi; driver tạo SQLException.
6. Hibernate/JPA có thể bọc lỗi thành exception của provider hoặc PersistenceException.
7. Spring có thể dịch lỗi ở repository boundary thành một DataAccessException phù hợp.

Do đó, exception ở service có thể là `DataIntegrityViolationException`, trong khi SQLException sâu hơn mới chứa SQLState và vendor code. Một lỗi commit có thể được nhìn thấy dưới dạng `TransactionSystemException` hoặc exception khác tùy transaction manager và provider.

Một số kiểu exception thường gặp:

| Exception | Ý nghĩa thường gặp |
|---|---|
| `DataAccessException` | Lớp exception runtime chung của Spring cho lỗi truy cập dữ liệu |
| `DataIntegrityViolationException` | Vi phạm constraint, chẳng hạn NOT NULL, foreign key hoặc unique |
| `DuplicateKeyException` | Lỗi khóa trùng, thường là unique/primary key |
| `BadSqlGrammarException` | SQL không hợp lệ hoặc database không chấp nhận cú pháp |
| `CannotAcquireLockException` | Không lấy được khóa cần thiết |
| `QueryTimeoutException` | Truy vấn vượt thời gian cho phép |
| `OptimisticLockingFailureException` | Cập nhật thất bại do xung đột version/optimistic lock |
| `PersistenceException` | Lỗi ở tầng JPA |
| `TransactionSystemException` | Lỗi trong quá trình hoàn tất transaction, thường gặp khi commit/rollback |

Tên và cách dịch exception cụ thể phụ thuộc Spring, JPA provider, JDBC driver và database. Không phải mọi lỗi đều được dịch thành cùng một loại exception. Khi chẩn đoán, hãy giữ cả exception ngoài cùng lẫn nguyên nhân bên trong.

## 2. Đọc cause chain đúng cách

`Throwable.getCause()` trả về nguyên nhân trực tiếp của exception hiện tại. Có thể lần theo chuỗi này để tìm nguyên nhân sâu nhất:

```java
static Throwable deepestCause(Throwable error) {
    Set<Throwable> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());

    Throwable current = error;

    while (current != null
            && current.getCause() != null
            && visited.add(current)) {
        current = current.getCause();
    }

    return current;
}
```

Cần import `java.util.Collections`, `java.util.IdentityHashMap` và `java.util.Set`.

Tuy nhiên, nguyên nhân sâu nhất không phải lúc nào cũng chứa toàn bộ thông tin hữu ích. Một số JDBC driver lưu các lỗi SQL liên tiếp qua `SQLException.getNextException()`, thay vì chỉ qua `getCause()`. Exception cũng có thể chứa suppressed exceptions. Vì vậy, khi xử lý lỗi database, hãy kiểm tra cả cause chain, SQL exception chain và suppressed exceptions.

Ví dụ một chuỗi có thể có dạng:

```text
DataIntegrityViolationException
  -> ConstraintViolationException (Hibernate)
      -> SQLException
          SQLState: 23505
          Vendor code: 0 hoặc mã riêng của driver
```

Đây là ví dụ minh họa cho lỗi unique constraint; tên exception và vendor code thực tế thay đổi theo database và driver.

Không nên chỉ log `error.getMessage()` rồi bỏ qua cause chain. Message ở lớp ngoài có thể chỉ ghi “could not execute statement”, trong khi exception sâu hơn mới cho biết constraint hoặc SQLState.

## 3. SQLState và vendor error code

`SQLException` cung cấp hai trường quan trọng:

- `getSQLState()`: mã trạng thái SQL do driver/database cung cấp, thường là chuỗi năm ký tự theo phân loại SQLState.
- `getErrorCode()`: mã lỗi riêng của nhà cung cấp database hoặc driver. Giá trị và ý nghĩa phụ thuộc hệ quản trị.

SQLState giúp phân loại lỗi theo nhóm. Một số class code thường gặp:

| SQLState class | Nhóm lỗi |
|---|---|
| `08` | Lỗi kết nối |
| `22` | Lỗi dữ liệu, ví dụ chuyển đổi hoặc giá trị không hợp lệ |
| `23` | Vi phạm ràng buộc toàn vẹn |
| `40` | Transaction rollback |
| `42` | Lỗi cú pháp SQL hoặc quy tắc truy cập |

Ví dụ `23505` thường biểu thị unique violation trong PostgreSQL. MySQL có thể trả SQLState `23000` cùng vendor error code `1062` cho duplicate entry. Đây là ví dụ theo database cụ thể; không được dùng một vendor code như thể nó có cùng ý nghĩa trên mọi hệ quản trị.

Khi đọc mã lỗi:

1. Xem SQLState class để xác định nhóm lỗi.
2. Tra vendor code trong tài liệu của đúng database và phiên bản driver.
3. Đối chiếu constraint, bảng/cột và câu SQL liên quan.
4. Kiểm tra nguyên nhân gốc và thời điểm lỗi xảy ra.
5. Không kết luận chỉ từ một mã nếu thiếu ngữ cảnh transaction hoặc schema.

SQLState có thể là `null`, vendor code có thể bằng `0`, và một chuỗi SQLException có thể chứa nhiều lỗi. Ứng dụng cần xử lý các trường hợp thiếu mã.

## 4. Tìm SQLException bên trong exception của Spring/JPA

Có thể duyệt cause chain, suppressed exceptions và `SQLException.getNextException()` để lấy mã SQL mà không cần log message:

```java
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.Set;

record SqlFailure(String sqlState, int vendorCode) {
}

static SqlFailure findSqlFailure(Throwable error) {
    Set<Throwable> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());
    Deque<Throwable> pending = new ArrayDeque<>();

    if (error != null) {
        pending.add(error);
    }

    while (!pending.isEmpty()) {
        Throwable current = pending.removeFirst();

        if (!visited.add(current)) {
            continue;
        }

        if (current instanceof SQLException sql) {
            String state = sql.getSQLState();
            int code = sql.getErrorCode();

            if (state != null || code != 0) {
                return new SqlFailure(state, code);
            }

            SQLException next = sql.getNextException();
            if (next != null) {
                pending.addLast(next);
            }
        }

        Throwable cause = current.getCause();
        if (cause != null) {
            pending.addLast(cause);
        }

        for (Throwable suppressed : current.getSuppressed()) {
            if (suppressed != null) {
                pending.addLast(suppressed);
            }
        }
    }

    return null;
}
```

Đoạn code trên dùng tập hợp identity để tránh duyệt lặp nếu exception graph có vòng tham chiếu. Nó trả về SQLException đầu tiên tìm được có SQLState hoặc vendor code. Nếu ứng dụng cần phân tích nhiều lỗi trong một batch, hãy điều chỉnh để thu thập toàn bộ SQLException thay vì chỉ lấy lỗi đầu tiên.

Với Spring `DataAccessException`, có thể xem `getMostSpecificCause()` để lấy cause sâu nhất theo chuỗi nguyên nhân thông thường. Tuy nhiên, cách đó không thay thế việc duyệt `SQLException.getNextException()`.

## 5. Đừng nhầm lỗi tại save với lỗi tại flush hoặc commit

JPA có thể trì hoãn gửi SQL xuống database. Vì vậy:

- `save()` có thể chỉ persist/merge entity vào persistence context.
- SQL có thể được gửi khi flush tự động trước query, khi gọi `flush()`, hoặc khi transaction commit.
- Constraint violation có thể chỉ xuất hiện tại flush/commit, dù dòng `save()` trước đó không ném lỗi.
- Transactional method có thể chạy xong phần thân method nhưng transaction proxy vẫn gặp lỗi khi commit sau khi method trả về.

Ví dụ:

```java
@Transactional
public void createCustomer(Customer customer) {
    customerRepository.save(customer);

    // Chưa chắc SQL INSERT đã được thực thi tại đây.
    // Lỗi constraint có thể xuất hiện khi flush hoặc commit.
}
```

Khi cần buộc kiểm tra lỗi ghi trong phạm vi method, có thể dùng `saveAndFlush()` hoặc `EntityManager.flush()`:

```java
@Transactional
public void createCustomer(Customer customer) {
    customerRepository.save(customer);
    entityManager.flush();
}
```

Flush gửi các thay đổi đang chờ xuống database nhưng không commit transaction. Transaction vẫn có thể rollback sau đó. Để bắt lỗi commit, cần quan sát lời gọi ở phía ngoài ranh giới transactional proxy; một try/catch bên trong method không bắt được lỗi phát sinh sau khi thân method đã trả về và proxy đang commit.

Không nên thêm flush vào mọi thao tác chỉ để chẩn đoán vì nó có thể thay đổi thời điểm SQL được thực thi và ảnh hưởng hiệu năng.

## 6. Log an toàn: ghi điều gì và tránh điều gì?

Một log chẩn đoán hữu ích thường cần:

- Tên thao tác nghiệp vụ hoặc repository operation.
- Tên loại entity/repository, không cần dump toàn bộ entity.
- Correlation ID hoặc trace ID để nối các log.
- Loại exception ở tầng ứng dụng.
- SQLState và vendor code nếu có.
- Thời điểm, môi trường, phiên bản ứng dụng và tên transaction/job khi phù hợp.
- Một mã lỗi nội bộ ổn định để hỗ trợ tìm kiếm.

Tránh ghi trực tiếp:

- Password, access token, refresh token, API key, cookie hoặc session secret.
- Số thẻ, tài khoản ngân hàng, thông tin thanh toán.
- Email, số điện thoại, địa chỉ hoặc định danh cá nhân nếu không cần thiết.
- Request/response body, entity `toString()` hoặc toàn bộ DTO có dữ liệu khách hàng.
- Giá trị bind parameter của truy vấn khi chúng chứa dữ liệu thật.
- Toàn bộ message của exception nếu driver có thể đưa giá trị dữ liệu vào message.
- SQL được ghép với literal nhạy cảm.

Đặc biệt, không bật bind parameter logging trong production chỉ để tìm một lỗi. SQL statement thường chỉ cho biết cấu trúc câu truy vấn, nhưng bind log có thể ghi giá trị thực của từng tham số. Một exception message hoặc stack trace cũng có thể chứa tên bảng, cột, giá trị bị từ chối hoặc dữ liệu do driver đưa vào.

Hãy ưu tiên allow-list các trường log được phép ghi, thay vì cố gắng tìm và che mọi chuỗi nhạy cảm bằng một vài biểu thức chính quy. Nếu cần định danh bản ghi, dùng ID nội bộ đã được phân loại phù hợp hoặc giá trị đã giả danh hóa; không đưa dữ liệu cá nhân vào correlation ID.

## 7. Ghi log có cấu trúc và giữ thông tin hữu ích

Ví dụ dưới đây ghi loại lỗi và mã database mà không đưa message, SQL hoặc tham số vào log thông thường:

```java
private static final Logger log =
        LoggerFactory.getLogger(CustomerService.class);

void logPersistenceFailure(
        String operation,
        String correlationId,
        RuntimeException error) {

    Throwable root = deepestCause(error);
    SqlFailure sql = findSqlFailure(error);

    log.error(
        "Persistence operation failed: operation={}, correlationId={}, " +
        "exceptionType={}, rootCauseType={}, sqlState={}, vendorCode={}",
        operation,
        correlationId,
        error.getClass().getSimpleName(),
        root == null ? "unknown" : root.getClass().getSimpleName(),
        sql == null ? null : sql.sqlState(),
        sql == null ? null : sql.vendorCode()
    );
}
```

Cần import SLF4J `Logger` và `LoggerFactory`, đồng thời đặt hai helper ở phần trước trong cùng class hoặc một utility phù hợp. Ví dụ không truyền đối tượng exception làm tham số cuối để logger tự in toàn bộ stack trace và message. Nếu tổ chức cần stack trace đầy đủ, hãy gửi vào hệ thống log có quyền truy cập hạn chế, chính sách lưu giữ rõ ràng và bước lọc dữ liệu nhạy cảm đã được kiểm chứng.

Không nên nuốt exception sau khi log. Hãy chuyển lỗi thành phản hồi phù hợp hoặc ném lại để transaction được xử lý đúng. Nếu catch một exception rồi tiếp tục trong transaction đã bị đánh dấu rollback-only, thao tác commit sau đó vẫn có thể thất bại.

## 8. Dùng correlation ID để nối log

Một request có thể đi qua controller, service, repository, transaction listener và tác vụ nền. Correlation ID giúp tìm các dòng log thuộc cùng một luồng mà không cần ghi dữ liệu người dùng.

Ví dụ với SLF4J MDC:

```java
import org.slf4j.MDC;

try (MDC.MDCCloseable ignored =
        MDC.putCloseable("correlationId", correlationId)) {
    customerService.updateCustomer(command);
}
```

Cấu hình pattern của logging framework để đưa `correlationId` vào mỗi dòng log. Với Spring Boot Actuator/Micrometer Tracing, có thể dùng trace ID/span ID được tích hợp sẵn nếu ứng dụng đã cấu hình tracing.

MDC thường dựa trên thread-local. Khi chuyển công việc qua `@Async`, executor hoặc thread pool, MDC không tự động được bảo đảm truyền sang thread khác. Nếu cần correlation ID trong tác vụ nền, hãy cấu hình `TaskDecorator` hoặc cơ chế context propagation tương ứng để sao chép và khôi phục MDC; không giữ context cũ trên thread pool sau khi task kết thúc.

Correlation ID phải được tạo hoặc xác thực ở biên tin cậy. Không dùng trực tiếp một header tùy ý của client làm giá trị có thể chứa nội dung nhạy cảm hoặc ký tự điều khiển; giới hạn độ dài và chuẩn hóa giá trị trước khi đưa vào log.

## 9. Bật log SQL có kiểm soát

Khi cần xem câu SQL Hibernate tạo ra, có thể bật logger theo profile chẩn đoán. Ví dụ với Hibernate 6:

```yaml
# application-diagnostics.yml
logging:
  level:
    org.hibernate.SQL: DEBUG
```

Nếu cần xem bind parameter, Hibernate 6 dùng category:

```yaml
logging:
  level:
    org.hibernate.orm.jdbc.bind: TRACE
```

Với Hibernate 5, category bind thường gặp là:

```yaml
logging:
  level:
    org.hibernate.type.descriptor.sql.BasicBinder: TRACE
```

Bind logging có thể lộ dữ liệu thật. Chỉ bật trong môi trường phát triển hoặc kiểm thử với dữ liệu giả, trong thời gian ngắn và theo quyền truy cập phù hợp. Không bật các category TRACE này trên production để chẩn đoán thông thường. Câu SQL cũng có thể chứa literal hoặc tên schema nhạy cảm nếu ứng dụng tạo native SQL theo cách không an toàn.

Ưu tiên dùng logger có thể bật/tắt theo profile và thu thập log tập trung. Tránh bật `spring.jpa.show-sql` một cách lâu dài vì việc in SQL trực tiếp ra console khó kiểm soát đồng nhất với chính sách logging của ứng dụng. Sau khi tái hiện lỗi, tắt mức log chi tiết và xác nhận cấu hình production không còn bind logging.

## 10. Đọc log theo nhóm lỗi

| Dấu hiệu | Hướng kiểm tra |
|---|---|
| SQLState class `23` hoặc `DataIntegrityViolationException` | Kiểm tra NOT NULL, unique, foreign key, độ dài cột và dữ liệu đầu vào |
| SQLState class `08` | Kiểm tra kết nối, network, database availability, pool timeout và driver |
| SQLState class `22` | Kiểm tra kiểu dữ liệu, conversion, precision/scale và giá trị vượt giới hạn |
| SQLState class `40` | Kiểm tra deadlock, serialization failure, transaction retry và thứ tự lấy khóa |
| SQLState class `42` | Kiểm tra tên bảng/cột, schema, cú pháp, quyền truy cập và câu query sinh ra |
| `OptimisticLockingFailureException` | Kiểm tra `@Version`, dữ liệu bị cập nhật đồng thời và cách xử lý retry |
| `QueryTimeoutException` hoặc lock timeout | Kiểm tra query plan, index, khóa đang giữ và thời gian transaction |
| `TransactionSystemException` khi hoàn tất method | Xem cause chain, flush/commit và transaction manager |

Đây là bản đồ định hướng, không phải kết luận tự động. Một SQLState hoặc exception class có thể có nhiều nguyên nhân cụ thể. Hãy xác minh bằng tài liệu database đang dùng, schema, SQL shape và transaction context.

## 11. Quy trình chẩn đoán một lỗi production

1. Lấy correlation ID, thời điểm, operation và phiên bản ứng dụng từ log an toàn.
2. Xác định exception ngoài cùng và loại exception Spring/JPA mà service nhận được.
3. Đọc cause chain, suppressed exceptions và `SQLException.getNextException()`.
4. Trích SQLState cùng vendor code; tra tài liệu đúng database/driver.
5. Xác định lỗi xảy ra khi query, flush hay commit; kiểm tra ranh giới `@Transactional`.
6. Đối chiếu schema, constraint, mapping entity, index, trạng thái kết nối và lock contention.
7. Nếu cần SQL chi tiết, tái hiện bằng dữ liệu giả trong môi trường kiểm soát và bật logger trong thời gian ngắn.
8. Ghi lại SQL shape và vị trí tham số; không ghi giá trị nhạy cảm của bind parameter.
9. Sửa nguyên nhân gốc, bổ sung kiểm thử hồi quy và tắt log chẩn đoán chi tiết sau khi hoàn tất.

Khi chia sẻ log với đồng nghiệp hoặc đưa vào ticket, hãy loại bỏ token, thông tin cá nhân, giá trị tham số, connection string và dữ liệu nghiệp vụ. Chỉ giữ phần stack trace hoặc SQLState cần thiết để người nhận có thể tái hiện vấn đề bằng dữ liệu đã giả danh hóa.

## 12. Những lỗi thường gặp khi chẩn đoán

**Chỉ đọc exception ngoài cùng.** Message có thể rất chung chung. Hãy duyệt cause chain và SQLException chain.

**Cho rằng root cause luôn là SQLException đầu tiên.** Một exception sâu hơn có thể là nguyên nhân gốc, còn `getNextException()` chứa lỗi bổ sung. Giữ toàn bộ cấu trúc lỗi khi phân tích.

**Cho rằng save() thành công nghĩa là commit thành công.** JPA có thể trì hoãn SQL đến flush/commit. Hãy kiểm tra lỗi ở ranh giới transaction.

**Dựa vào vendor code mà không biết database.** Vendor code không có ý nghĩa thống nhất giữa các hệ quản trị. Ghi nhận loại database và phiên bản driver cùng mã lỗi.

**Bật TRACE bind parameter trong production.** Giá trị tham số có thể chứa PII hoặc bí mật. Dùng dữ liệu giả và môi trường kiểm soát.

**Log cả entity hoặc request body.** `toString()` có thể chứa password, token, email hoặc dữ liệu nhạy cảm khác. Chỉ ghi các trường allow-list.

**Chỉ ghi log mà không có correlation ID.** Khó nối các log từ nhiều tầng hoặc nhiều thread. Truyền trace/correlation context có kiểm soát, nhất là khi dùng async.

**Bắt exception rồi bỏ qua.** Điều này có thể che lỗi và để transaction ở trạng thái rollback-only. Xử lý lỗi có chủ đích và bảo đảm caller nhận được kết quả đúng.

## Kết luận

Chẩn đoán lỗi Spring Data JPA cần kết hợp exception ngoài cùng, cause chain, SQLException chain, SQLState và vendor error code. SQLState giúp phân nhóm, còn vendor code phải được tra theo đúng database và driver. Khi ghi log, hãy dùng correlation ID và các trường kỹ thuật đã allow-list; tránh message, entity, request body và bind parameter chứa dữ liệu thật. Chỉ bật SQL/bind logging trong môi trường kiểm soát, rồi tắt sau khi tái hiện lỗi. Cách làm này giữ được thông tin cần thiết để tìm nguyên nhân mà không biến hệ thống log thành nơi lưu trữ dữ liệu nhạy cảm.
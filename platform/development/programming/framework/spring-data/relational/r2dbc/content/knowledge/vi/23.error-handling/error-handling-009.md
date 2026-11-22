# Giữ nguyên nguyên nhân lỗi và tránh ghi log thông tin nhạy cảm

Trong Spring Data Relational R2DBC, lỗi từ database và driver thường đi qua nhiều tầng trước khi tới API hoặc worker: R2DBC driver phát exception, Spring có thể dịch lỗi sang nhóm `DataAccessException`, service có thể chuyển nó thành exception nghiệp vụ, rồi controller hoặc message handler quyết định cách phản hồi. Khi chuyển đổi lỗi, ứng dụng cần giữ nguyên nguyên nhân gốc để phục vụ chẩn đoán. Đồng thời, việc ghi log phải được kiểm soát vì exception, câu SQL, tham số bind và dữ liệu request có thể chứa thông tin cá nhân hoặc bí mật.

Hai yêu cầu này bổ trợ cho nhau: **giữ cause trong chuỗi exception để không mất thông tin kỹ thuật, nhưng chỉ ghi ra log những trường đã được chọn và làm sạch theo chính sách bảo mật**. Giữ nguyên cause không có nghĩa là phải ghi toàn bộ exception, message, SQL hoặc payload vào log ở mọi nơi.

## 1. Đường đi của lỗi trong ứng dụng R2DBC

Một thao tác database reactive có thể phát lỗi từ nhiều nguồn:

- Lỗi kết nối hoặc timeout khi mở connection.
- Lỗi cú pháp SQL hoặc sai kiểu dữ liệu.
- Vi phạm unique, foreign key, `NOT NULL` hoặc `CHECK` constraint.
- Deadlock, serialization failure hoặc lỗi transaction.
- Lỗi mapping/conversion giữa kiểu SQL và kiểu Java.
- Lỗi do ứng dụng hủy hoặc hết thời gian xử lý.

Ví dụ, một lệnh INSERT được thực hiện qua repository:

```java
Mono<Customer> saveCustomer(Customer customer) {
    return customerRepository.save(customer);
}
```

Khi database từ chối thao tác, driver phát lỗi qua reactive publisher. Tùy đường truy cập dữ liệu và cơ chế exception translation, tầng Spring có thể chuyển lỗi driver thành một exception thuộc hệ thống `DataAccessException`. Service có thể giữ nguyên exception đó hoặc ánh xạ sang exception nghiệp vụ.

Luồng tổng quát:

```text
Database / R2DBC driver
          |
          v
R2dbcException hoặc lỗi driver khác
          |
          v
Spring exception translation (nếu áp dụng)
          |
          v
DataAccessException / lỗi mapping
          |
          v
Service chuyển đổi sang lỗi nghiệp vụ
          |
          v
API handler / worker boundary
          |
          +----> phản hồi an toàn cho caller
          |
          +----> log có chọn lọc, không lộ dữ liệu nhạy cảm
```

Không phải mọi lỗi đều là lỗi SQL. Một lỗi timeout ở HTTP client, lỗi serialize hoặc lỗi validation có thể đi vào cùng reactive pipeline. Hãy phân loại theo loại lỗi và nguồn phát thay vì coi mọi exception đều là database failure.

## 2. Nguyên nhân gốc (cause) là gì?

Java exception có thể bọc một exception khác. Exception ngoài thường mô tả ý nghĩa ở tầng hiện tại; cause giữ lại lỗi thấp hơn đã dẫn đến nó.

Ví dụ:

```text
CustomerRegistrationException
    caused by DataIntegrityViolationException
        caused by R2dbcDataIntegrityViolationException
            caused by R2dbcException (SQLSTATE / vendor code)
```

Trong chuỗi trên:

- `CustomerRegistrationException` diễn đạt lỗi theo nghiệp vụ đăng ký khách hàng.
- `DataIntegrityViolationException` cho biết thao tác vi phạm toàn vẹn dữ liệu ở tầng truy cập dữ liệu.
- Exception R2DBC giữ thông tin cụ thể hơn về driver/database.
- `R2dbcException` có thể cung cấp SQL state, mã lỗi vendor và thông tin liên quan theo driver.

Giữ cause giúp đội phát triển phân biệt lỗi nghiệp vụ với nguyên nhân kỹ thuật, đồng thời hỗ trợ phân loại lỗi theo database mà không phải đưa chi tiết nội bộ ra API.

## 3. Tạo exception mới nhưng giữ cause

Khi cần chuyển lỗi kỹ thuật thành lỗi ở tầng service, hãy dùng constructor nhận `Throwable cause`:

```java
public class CustomerRegistrationException extends RuntimeException {

    public CustomerRegistrationException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Ánh xạ lỗi trong reactive pipeline bằng `onErrorMap`:

```java
public Mono<Customer> register(Customer customer) {
    return customerRepository.save(customer)
        .onErrorMap(DataIntegrityViolationException.class,
            error -> new CustomerRegistrationException(
                "Không thể hoàn tất đăng ký khách hàng",
                error
            ));
}
```

`onErrorMap` thay tín hiệu lỗi bằng exception mới. Exception mới giữ exception cũ làm cause, vì vậy chuỗi nguyên nhân vẫn có thể được truy vết ở nơi được phép.

Message mới được viết theo ngữ cảnh nghiệp vụ và không chứa email, số điện thoại, câu SQL hay giá trị tham số. Nếu cần hiển thị email đã dùng, hãy cân nhắc chính sách riêng cho response; không đưa dữ liệu đó vào exception message một cách mặc định vì message có thể bị ghi log ở nhiều tầng.

### 3.1. Không tạo exception mới chỉ với message

Không nên:

```java
return customerRepository.save(customer)
    .onErrorMap(error -> new CustomerRegistrationException(
        "Đăng ký thất bại: " + error.getMessage(),
        null
    ));
```

Đoạn code trên có hai vấn đề:

- Cause gốc bị mất vì truyền `null`.
- Message của driver hoặc database có thể chứa SQL, tên bảng/cột, dữ liệu bind hoặc chi tiết hạ tầng.

Nên:

```java
return customerRepository.save(customer)
    .onErrorMap(error -> new CustomerRegistrationException(
        "Không thể hoàn tất đăng ký khách hàng",
        error
    ));
```

### 3.2. Không dùng getMessage() thay cho cause

`error.getMessage()` chỉ trả về chuỗi mô tả. Nó không giữ kiểu exception, stack trace hay cause chain. Việc ghép chuỗi message vào exception mới không tương đương với:

```java
new CustomerRegistrationException("Đăng ký thất bại", error);
```

Khi cần bổ sung ngữ cảnh, hãy thêm operation code hoặc mã nghiệp vụ an toàn vào exception mới, đồng thời truyền exception gốc vào constructor.

### 3.3. Không bọc lỗi nhiều lần mà không có ý nghĩa

Mỗi tầng không nên tạo một exception mới chỉ để đổi tên rồi lại bọc tiếp. Một chuỗi cause quá dài với các message giống nhau làm việc chẩn đoán khó hơn.

Chỉ chuyển đổi khi có ranh giới ngữ nghĩa rõ ràng, ví dụ:

- Từ lỗi driver sang lỗi truy cập dữ liệu.
- Từ lỗi dữ liệu sang lỗi nghiệp vụ mà caller hiểu được.
- Từ lỗi nghiệp vụ sang HTTP status hoặc mã lỗi API.

Nếu không cần đổi loại lỗi, hãy truyền nguyên exception lên trên.

## 4. Phân biệt onErrorMap, onErrorResume và doOnError

Các toán tử Reactor xử lý lỗi theo mục đích khác nhau:

| Toán tử | Tác dụng | Tín hiệu downstream |
|---|---|---|
| `onErrorMap` | Chuyển exception thành exception khác | Vẫn là `onError`, nhưng loại lỗi có thể thay đổi |
| `onErrorResume` | Chuyển lỗi thành một Publisher fallback | Có thể là giá trị, empty hoặc một lỗi khác |
| `doOnError` | Quan sát lỗi để log/metric | Giữ nguyên lỗi, không tự xử lý hoặc thay thế lỗi |
| `onErrorReturn` | Thay lỗi bằng một giá trị mặc định | Có thể hoàn tất thành công |
| `doFinally` | Quan sát complete/error/cancel | Không thay đổi tín hiệu đã xảy ra |

### 4.1. Dùng onErrorMap để giữ nguyên lỗi gốc

```java
return repository.save(entity)
    .onErrorMap(DataAccessException.class,
        error -> new EntityWriteException(
            "Không thể lưu dữ liệu",
            error
        ));
```

Lỗi tiếp tục là `onError`; chỉ exception được bọc lại. Caller có thể kiểm tra `EntityWriteException`, còn cause giữ thông tin từ Spring/driver.

### 4.2. Dùng doOnError để quan sát, không nuốt lỗi

```java
return repository.save(entity)
    .doOnError(error -> log.warn(
        "Entity write failed; operation={}",
        "customer.create"
    ));
```

`doOnError` chạy callback khi lỗi đi qua, sau đó lỗi vẫn truyền xuống downstream. Đây là vị trí phù hợp để phát metric hoặc ghi một log event đã được làm sạch.

Không nên biến `doOnError` thành nơi gọi một Publisher khác rồi `subscribe()` riêng. Callback này không chờ thao tác reactive được tạo bên trong nó. Nếu cần gửi log/audit bất đồng bộ và việc gửi đó là một phần của use case, hãy compose publisher bằng toán tử thích hợp hoặc ghi outbox.

### 4.3. onErrorResume có thể làm lỗi biến mất

```java
return repository.findById(id)
    .onErrorResume(error -> Mono.empty());
```

Đoạn code trên chuyển mọi lỗi thành empty. Caller không thể phân biệt “không tìm thấy bản ghi” với “database bị lỗi”. Chỉ dùng fallback cho loại lỗi đã xác định và khi giá trị thay thế có ý nghĩa nghiệp vụ.

Nếu chỉ muốn đổi loại exception, dùng `onErrorMap`; không dùng `onErrorResume` chỉ để bọc lỗi.

## 5. Giữ cause không có nghĩa phải log toàn bộ cause chain

Một điểm cần phân biệt:

- **Exception chain trong bộ nhớ:** giữ cause để các tầng có thể phân loại và chẩn đoán.
- **Log event:** dữ liệu được ghi bền vững vào hệ thống log, có thể được nhiều người hoặc hệ thống truy cập.
- **API response:** dữ liệu gửi cho client hoặc caller bên ngoài.

Ba nơi này có mục đích và quyền truy cập khác nhau. Một exception có thể chứa SQL, tên schema, tên constraint, đường dẫn file, hostname, username database, email hoặc một phần giá trị dữ liệu. Ghi toàn bộ exception bằng `log.error("...", error)` có thể in message và cause chain, làm lộ các thông tin đó.

Có thể giữ cause trong exception và chỉ ghi một log event đã chọn lọc:

```java
return repository.save(customer)
    .onErrorMap(error -> new CustomerRegistrationException(
        "Không thể hoàn tất đăng ký khách hàng",
        error
    ));
```

Ở boundary, ghi các trường an toàn:

```java
log.error(
    "Customer registration failed; operation={}, correlationId={}, errorType={}",
    "customer.register",
    correlationId,
    error.getClass().getSimpleName()
);
```

Ví dụ này không truyền `Throwable` cuối cùng vào logger nên không in tự động toàn bộ message/stack trace. Nếu cần stack trace để điều tra, hãy dùng một kênh log được kiểm soát, bảo đảm exception/message đã được rà soát hoặc làm sạch theo chính sách của hệ thống.

Không nên xóa cause chỉ để log an toàn. Hãy tách việc giữ nguyên nhân lỗi khỏi quyết định dữ liệu nào được phép xuất hiện trong log.

## 6. Những dữ liệu không nên ghi log

Trong ứng dụng R2DBC, dữ liệu nhạy cảm có thể xuất hiện ở nhiều nơi hơn body HTTP. Một số loại cần tránh ghi trực tiếp:

| Loại dữ liệu | Ví dụ | Cách xử lý |
|---|---|---|
| Bí mật xác thực | Password, API key, client secret, private key | Không ghi log; chỉ log tên credential/config key nếu cần |
| Token | Access token, refresh token, JWT, session cookie | Không ghi token; dùng correlation/trace ID riêng |
| Dữ liệu cá nhân | Email, số điện thoại, địa chỉ, ngày sinh, số định danh | Tránh log; nếu cần liên kết, dùng ID nội bộ hoặc token hóa phù hợp |
| Dữ liệu thanh toán | Số thẻ, CVV, tài khoản ngân hàng, thông tin giao dịch nhạy cảm | Không ghi nội dung đầy đủ; tuân thủ chính sách dữ liệu thanh toán |
| Nội dung request/response | JSON chứa hồ sơ, mật khẩu hoặc thông tin cá nhân | Không log toàn body; ghi metadata allowlist |
| Giá trị bind R2DBC | Email, mã khách hàng, nội dung truy vấn, dữ liệu LOB | Không bật bind-value logging ở production |
| Câu SQL có dữ liệu nhúng | SQL ghép chuỗi chứa giá trị người dùng | Dùng bind parameter và không log SQL đã nội suy |
| Exception message | Driver message chứa SQL, giá trị hoặc chi tiết kết nối | Ghi loại lỗi/mã lỗi đã chọn; bảo vệ log chi tiết nếu cần |
| Header HTTP | `Authorization`, `Cookie`, `Set-Cookie` | Loại bỏ hoặc che hoàn toàn các header nhạy cảm |

Không phải mọi ID đều là dữ liệu công khai. ID tài khoản, tenant hoặc đơn hàng có thể cho phép liên kết hành vi người dùng. Hãy phân loại theo chính sách dữ liệu của hệ thống và chỉ log định danh tối thiểu cần thiết.

## 7. Tránh log SQL và giá trị bind ngoài ý muốn

Một thao tác R2DBC có thể được ghi lại bởi nhiều lớp:

- Logger của ứng dụng.
- Spring Framework/Spring Data.
- R2DBC driver.
- Connection pool.
- Database audit hoặc query log.
- APM/tracing agent.

Ngay cả khi code ứng dụng không log entity, cấu hình DEBUG/TRACE ở driver hoặc thư viện truy cập dữ liệu có thể ghi câu SQL và tham số bind. Trong production, không bật mức log chi tiết chỉ để điều tra một lỗi nếu chưa đánh giá dữ liệu có thể bị lộ.

Ví dụ truy vấn an toàn về mặt bind:

```java
databaseClient.sql("""
        SELECT id, email
        FROM app_user
        WHERE email = :email
        """)
    .bind("email", email)
    .map((row, metadata) -> new UserSummary(
        row.get("id", Long.class),
        row.get("email", String.class)
    ))
    .one();
```

Bind parameter giúp tách dữ liệu khỏi cấu trúc SQL và chống SQL injection theo đúng cách sử dụng. Nhưng bind parameter không tự bảo đảm rằng logger của driver không ghi giá trị đó. Cần quản lý riêng cấu hình logging.

Không ghép giá trị vào SQL để dễ đọc log:

```java
// Không nên: giá trị email được nhúng vào chuỗi SQL.
String sql = "SELECT id FROM app_user WHERE email = '" + email + "'";
```

Ngoài nguy cơ SQL injection, chuỗi SQL đã nội suy có thể xuất hiện trong exception hoặc log. Hãy giữ SQL cố định và bind giá trị.

## 8. Ghi log có cấu trúc và allowlist trường dữ liệu

Một log event tốt nên trả lời được:

- Thao tác nào thất bại?
- Xảy ra ở service hoặc component nào?
- Request/job nào liên quan?
- Loại lỗi hoặc nhóm lỗi nào?
- Thời điểm và mức độ nghiêm trọng?
- Có thể tra cứu trace hoặc correlation nào?

Ví dụ trường an toàn có thể gồm:

```text
event=customer.register.failed
operation=customer.register
correlation_id=7b2...
error_type=DataIntegrityViolationException
error_category=DATA_INTEGRITY
duration_ms=42
```

Đây là dữ liệu minh họa. Không đưa raw email, token, password, request body, SQL bind value hoặc toàn bộ exception message vào event.

### 8.1. Ưu tiên allowlist hơn denylist

Allowlist nghĩa là chỉ ghi những trường đã được phê duyệt. Denylist nghĩa là ghi tất cả rồi cố gắng loại bỏ một số tên trường nhạy cảm. Denylist dễ bỏ sót trường mới, alias hoặc dữ liệu nằm sâu trong object.

Ví dụ allowlist cho một thao tác tạo customer:

- Tên operation cố định: `customer.register`.
- Correlation ID do hệ thống tạo hoặc đã được xác thực/chuẩn hóa.
- Error category: `DATA_INTEGRITY`, `CONNECTION`, `TIMEOUT` hoặc `UNKNOWN`.
- Exception class đơn giản.
- Thời gian xử lý và kết quả.
- Constraint code đã được phân loại nếu không tiết lộ schema nhạy cảm.

Không serialize toàn bộ entity hoặc DTO request thành JSON để ghi log. Khi schema thay đổi, cách serialize toàn object có thể vô tình thêm field nhạy cảm vào log.

### 8.2. Dùng parameterized logging

Với SLF4J:

```java
log.warn(
    "Database operation failed; operation={}, errorType={}",
    operation,
    errorType
);
```

Parameterized logging giúp tránh nối chuỗi thủ công và giảm chi phí tạo message khi log level bị tắt. Tuy nhiên, nó không tự làm sạch dữ liệu. Nếu `operation` hoặc giá trị khác đến từ input không tin cậy, vẫn cần kiểm soát nội dung trước khi ghi.

## 9. Tránh log injection và log forging

Người dùng có thể gửi dữ liệu chứa ký tự xuống dòng hoặc ký tự điều khiển. Nếu ghi trực tiếp chuỗi đó vào log dạng văn bản, kẻ tấn công có thể tạo dòng log giả hoặc làm sai cấu trúc parser.

Ví dụ input:

```text
guest
level=ERROR event=login.success user=admin
```

Nếu ghi raw input vào log, dòng thứ hai có thể trông như một event độc lập. Cách phòng vệ:

- Không log raw input không cần thiết.
- Dùng logger có cấu trúc để encode giá trị theo format JSON.
- Giới hạn độ dài trường văn bản.
- Loại bỏ hoặc encode CR, LF và ký tự điều khiển khi ghi trường text.
- Không cho client tự đặt tên event, severity hoặc key log tùy ý.
- Dùng operation name và error code cố định do ứng dụng kiểm soát.

Một hàm làm sạch đơn giản cho trường text không nhạy cảm:

```java
static String safeLogText(String value) {
    if (value == null) {
        return "";
    }

    String normalized = value
        .replace('\r', ' ')
        .replace('\n', ' ')
        .replace('\t', ' ');

    return normalized.length() <= 120
        ? normalized
        : normalized.substring(0, 120);
}
```

Hàm này chỉ minh họa xử lý ký tự điều khiển và độ dài. Nó **không** biến dữ liệu nhạy cảm thành dữ liệu an toàn. Không gọi `safeLogText(email)` rồi cho rằng email đã được phép ghi log; chính sách đúng vẫn là không log email nếu không có lý do và phê duyệt.

## 10. Masking, redaction và pseudonymization

Ba khái niệm thường bị nhầm:

- **Masking:** che một phần giá trị, ví dụ chỉ hiển thị bốn ký tự cuối.
- **Redaction:** loại bỏ giá trị khỏi log hoặc thay bằng nhãn như `[REDACTED]`.
- **Pseudonymization:** thay giá trị bằng mã thay thế để liên kết các event mà không hiển thị giá trị gốc.

Ví dụ, nếu chính sách cho phép hiển thị một phần mã giao dịch:

```text
transaction_ref=********4821
```

Không áp dụng masking tùy tiện cho mọi loại dữ liệu. Với password, access token, refresh token, private key và CVV, không nên ghi một phần; hãy loại bỏ hoàn toàn.

Nếu cần liên kết cùng một khách hàng qua nhiều log, có thể dùng ID nội bộ không trực tiếp tiết lộ danh tính hoặc pseudonym được tạo bằng HMAC với khóa bảo vệ. Hash thường không có khóa có thể bị dò ngược với dữ liệu có không gian giá trị nhỏ như số điện thoại hoặc email. Không dùng SHA-256(email) đơn thuần như một biện pháp ẩn danh mạnh.

Việc masking/redaction nên diễn ra trước khi dữ liệu được đưa vào logger hoặc tại một lớp logging có kiểm soát. Không dựa hoàn toàn vào việc xóa dữ liệu sau khi log đã được gửi tới hệ thống tập trung, bản sao, archive hoặc alert.

## 11. Log exception an toàn mà vẫn giữ khả năng điều tra

Một chiến lược phù hợp là tách log nghiệp vụ an toàn khỏi chẩn đoán kỹ thuật chi tiết.

### 11.1. Log event an toàn ở application boundary

```java
public Mono<Customer> register(Customer customer, String correlationId) {
    return customerRepository.save(customer)
        .onErrorMap(error -> new CustomerWriteException(
            "Không thể lưu khách hàng",
            error
        ))
        .doOnError(error -> log.error(
            "Customer write failed; operation={}, correlationId={}, errorType={}",
            "customer.register",
            safeCorrelationId(correlationId),
            error.getClass().getSimpleName()
        ));
}
```

Ví dụ này giữ cause trong `CustomerWriteException`, nhưng log chỉ ghi operation, correlation ID đã chuẩn hóa và loại exception. Nó không truyền Throwable vào logger nên không in cause chain.

Trong một ứng dụng lớn, nên tránh log cùng một lỗi ở mọi tầng. Service có thể chuyển đổi exception mà không log; controller advice, message listener hoặc worker boundary ghi một event duy nhất khi lỗi rời khỏi use case.

### 11.2. Chọn metadata kỹ thuật an toàn

Với lỗi R2DBC, một số metadata có thể hữu ích:

- Loại exception.
- SQLSTATE hoặc mã lỗi vendor đã được phân loại.
- Operation code cố định.
- Constraint category hoặc tên constraint nếu chính sách cho phép.
- Thời gian xử lý.
- Correlation/trace ID.

Ví dụ lấy SQLSTATE mà không ghi message:

```java
static Optional<String> findSqlState(Throwable error) {
    for (Throwable current = error;
         current != null;
         current = current.getCause()) {

        if (current instanceof R2dbcException r2dbcException) {
            return Optional.ofNullable(r2dbcException.getSqlState());
        }
    }

    return Optional.empty();
}
```

Sau đó có thể ánh xạ SQLSTATE sang category đã biết:

```java
static String classifySqlState(String sqlState) {
    if (sqlState == null) {
        return "UNKNOWN";
    }

    if (sqlState.startsWith("08")) {
        return "CONNECTION";
    }

    if (sqlState.startsWith("23")) {
        return "DATA_INTEGRITY";
    }

    if (sqlState.startsWith("40")) {
        return "TRANSACTION_ROLLBACK";
    }

    return "DATABASE_ERROR";
}
```

Các class SQLSTATE ở trên theo quy ước SQLSTATE phổ biến, nhưng việc phân loại cuối cùng vẫn cần xét database và driver. Không ghi SQLSTATE như thể nó luôn đủ để xác định nguyên nhân nghiệp vụ; nó là metadata kỹ thuật để hỗ trợ chẩn đoán.

### 11.3. Khi cần stack trace đầy đủ

Trong một số sự cố khó tái hiện, stack trace đầy đủ rất hữu ích. Tuy nhiên, logger thường in cả exception message và cause chain. Trước khi ghi:

- Xác định exception message có thể chứa SQL, bind value hoặc PII không.
- Kiểm tra driver có nhúng URL kết nối, username hoặc tên schema vào message không.
- Chỉ gửi tới sink có phân quyền và retention phù hợp.
- Áp dụng masking/redaction trước khi ghi nếu cần.
- Không gửi cùng log chi tiết tới console công khai, client response hoặc kênh chat không được phép.

Nếu chưa thể bảo đảm nội dung stack trace an toàn, hãy ghi metadata có chọn lọc và giữ cause trong exception để debugger hoặc môi trường chẩn đoán được kiểm soát có thể truy cập khi cần.

## 12. Trả lỗi an toàn cho HTTP client

Không trả trực tiếp `exception.getMessage()`, stack trace hoặc `cause.toString()` trong response:

```java
// Không nên.
return ResponseEntity.internalServerError()
    .body(error.getMessage());
```

Message có thể tiết lộ:

- Tên bảng, schema hoặc cột nội bộ.
- Câu SQL và điều kiện truy vấn.
- Hostname, port hoặc tên database.
- Thông tin xác thực hoặc URL kết nối.
- Dữ liệu của một người dùng khác.
- Chi tiết constraint hoặc implementation không nên công khai.

Thay vào đó, trả mã lỗi và nội dung tổng quát:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(CustomerWriteException.class)
    ResponseEntity<ProblemDetail> handleCustomerWrite(
            CustomerWriteException error) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "Không thể xử lý yêu cầu hiện tại"
        );
        problem.setTitle("Lỗi xử lý dữ liệu");
        problem.setProperty("code", "CUSTOMER_WRITE_FAILED");

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(problem);
    }
}
```

Với lỗi nghiệp vụ đã xác định, có thể trả status cụ thể như 400, 404, 409 hoặc 422 và mã lỗi ổn định. Với lỗi hạ tầng không dự đoán được, trả thông báo tổng quát và correlation ID để hỗ trợ tra cứu qua kênh được bảo vệ.

Không đưa cause hoặc stack trace vào `ProblemDetail`.

## 13. Correlation ID và tracing trong reactive pipeline

Correlation ID giúp liên kết các log event của cùng request hoặc workflow mà không phải ghi toàn bộ dữ liệu request.

Ví dụ log:

```text
event=order.write.failed
correlation_id=7b2f...
operation=order.create
error_category=DATA_INTEGRITY
```

Trong ứng dụng reactive, không nên giả định `ThreadLocal` luôn giữ đúng request context vì pipeline có thể chuyển thread. Reactor Context là cơ chế phù hợp để truyền metadata theo subscription; các integration của Micrometer Tracing/Observation có thể hỗ trợ trace context và MDC tùy cấu hình.

Ví dụ truy xuất correlation ID từ Reactor Context:

```java
Mono<Order> createOrder(Order order) {
    return Mono.deferContextual(contextView -> {
        String correlationId = contextView.getOrDefault(
            "correlationId", "unknown"
        );

        return orderRepository.save(order)
            .doOnError(error -> log.error(
                "Order write failed; operation={}, correlationId={}, errorType={}",
                "order.create",
                safeCorrelationId(correlationId),
                error.getClass().getSimpleName()
            ));
    });
}
```

Ví dụ dùng key `correlationId` tự định nghĩa. Trong hệ thống thực tế, ưu tiên chuẩn tracing và context propagation mà ứng dụng đang dùng thay vì tự tạo một cơ chế song song. Không đưa token, email hoặc request body vào Reactor Context chỉ để tiện log.

Nếu correlation ID đến từ HTTP header bên ngoài, cần kiểm tra độ dài và ký tự hợp lệ trước khi sử dụng. Không tin một giá trị tùy ý của client để đặt tên event hoặc điều khiển cấu trúc log.

## 14. Log lỗi ở một nơi có trách nhiệm

Một lỗi có thể đi qua repository, service, controller advice và global WebFlux error handler. Nếu mỗi tầng đều ghi stack trace, một lỗi đơn lẻ có thể tạo nhiều log giống nhau và tăng nguy cơ lộ dữ liệu.

Nên phân vai:

| Tầng | Trách nhiệm phù hợp |
|---|---|
| Repository | Trả publisher và giữ nguyên lỗi; thường không log lỗi rồi rethrow |
| Service | Chuyển lỗi sang ngữ nghĩa nghiệp vụ khi cần; chỉ log nếu có thông tin vận hành riêng và không trùng boundary |
| Controller advice / message boundary | Ánh xạ lỗi thành response hoặc acknowledgement; ghi event cuối cùng theo chính sách |
| Global error handler | Xử lý lỗi chưa được phân loại, gắn correlation ID và ghi một event an toàn |
| Worker/consumer boundary | Ghi trạng thái retry, dead-letter hoặc thất bại của job theo mã job an toàn |

Không phải mọi kiến trúc đều có đúng các tầng trên. Nguyên tắc là xác định một boundary chịu trách nhiệm log lỗi cuối cùng, còn các tầng giữa truyền hoặc chuyển đổi exception mà không nhân bản log.

### 14.1. Tránh log rồi throw lại cùng lỗi ở mọi tầng

Không nên:

```java
public Mono<Customer> save(Customer customer) {
    return repository.save(customer)
        .doOnError(error -> log.error("Repository failed", error));
}
```

và sau đó service, controller advice lại ghi toàn bộ stack trace. Điều này vừa tạo log trùng, vừa có thể ghi dữ liệu nhạy cảm nhiều lần.

Nếu repository không có ngữ cảnh cần thiết để xử lý lỗi, hãy để nó truyền lỗi. Boundary cuối cùng ghi một event an toàn:

```java
public Mono<Customer> save(Customer customer) {
    return repository.save(customer);
}
```

## 15. Logging SQL, bind values và cấu hình production

Khi điều tra lỗi R2DBC, developer đôi khi bật DEBUG/TRACE cho package driver hoặc Spring để xem SQL. Cách này có thể hữu ích ở môi trường local/test với dữ liệu giả, nhưng có rủi ro ở production.

Checklist cấu hình:

- Không bật bind parameter logging mặc định trong production.
- Không ghi `Authorization`, `Cookie`, `Set-Cookie` hoặc credential headers.
- Không ghi toàn bộ request/response body có dữ liệu cá nhân.
- Không ghi entity, DTO hoặc `Map` chưa được allowlist.
- Kiểm tra APM agent, SQL instrumentation và connection pool logger có capture parameter hay không.
- Giữ mức log TRACE/DEBUG cho thời gian ngắn, có phê duyệt và phạm vi hẹp khi cần điều tra.
- Dùng dữ liệu giả hoặc đã khử định danh ở môi trường phát triển.
- Tắt hoặc che dữ liệu nhạy cảm trong database audit/query log theo chính sách tương ứng.

Không giả định chỉ vì ứng dụng dùng bind parameter nên giá trị bind không thể xuất hiện trong log. Logger có thể được cấu hình để ghi chúng.

## 16. Bảo vệ hệ thống log sau khi ghi

Thông tin đã được ghi an toàn vẫn cần được bảo vệ trong suốt vòng đời:

- Phân quyền truy cập theo vai trò và nhu cầu công việc.
- Mã hóa khi truyền và khi lưu nếu nền tảng hỗ trợ.
- Đặt retention phù hợp và xóa theo chính sách.
- Không gửi log production tới tài khoản cá nhân hoặc dịch vụ chưa được phê duyệt.
- Kiểm soát export, download và chia sẻ log.
- Theo dõi truy cập bất thường vào hệ thống log.
- Tránh đưa dữ liệu nhạy cảm vào alert title, chat notification hoặc dashboard công khai.

Log là một kho dữ liệu vận hành. Nó có thể được sao chép sang nhiều hệ thống, được index và giữ lâu hơn database nguồn. Vì vậy, phòng ngừa tại thời điểm tạo log quan trọng hơn việc hy vọng có thể xóa sau này.

## 17. Kiểm thử việc giữ cause và không lộ dữ liệu

Kiểm thử lỗi nên xác nhận cả hai mặt: nguyên nhân gốc được giữ và log/response không chứa dữ liệu nhạy cảm.

### 17.1. Kiểm tra cause chain

```java
@Test
void preservesOriginalCause() {
    RuntimeException rootCause = new RuntimeException("driver failure");

    CustomerRegistrationException wrapped =
        new CustomerRegistrationException("Registration failed", rootCause);

    assertSame(rootCause, wrapped.getCause());
}
```

Test này xác nhận constructor giữ đúng object cause. Với reactive mapping, có thể kiểm tra exception phát ra:

```java
StepVerifier.create(customerService.register(customer))
    .expectErrorSatisfies(error -> {
        assertInstanceOf(CustomerRegistrationException.class, error);
        assertInstanceOf(DataIntegrityViolationException.class,
            error.getCause());
    })
    .verify();
```

Ví dụ giả định repository phát `DataIntegrityViolationException`. Test thực tế nên dùng lỗi được tạo có chủ đích hoặc database tích hợp để xác nhận exception translation.

### 17.2. Kiểm tra log không chứa secret

Có thể dùng appender test hoặc log capture để xác nhận event không chứa dữ liệu nhạy cảm:

```java
assertThat(capturedLogs)
    .doesNotContain("secret-token-value")
    .doesNotContain("customer-private-email@example.com")
    .contains("customer.register")
    .contains("correlationId");
```

Đây là ví dụ kiểm tra chuỗi. Trong dự án thực tế, dùng logger/appender test đang có và kiểm tra cả formatted message, structured fields và throwable được đính kèm.

### 17.3. Kiểm tra API response

Xác nhận response chỉ có mã lỗi và thông báo công khai đã định nghĩa; không chứa:

- SQL hoặc bind value.
- Exception class nội bộ nếu không cần công khai.
- Stack trace.
- Database hostname, username hoặc connection URL.
- Token, password hoặc PII.

### 17.4. Kiểm tra log injection

Gửi input chứa CR/LF và xác nhận nó không tạo thêm log record hoặc thay đổi key/severity của event. Với structured logging, kiểm tra JSON output được encode hợp lệ và trường input không thể thoát khỏi giá trị của nó.

## 18. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tạo exception mới nhưng không truyền cause | Mất exception gốc, stack trace và metadata driver | Dùng constructor `(message, cause)` |
| Nối `getMessage()` vào exception mới | Có thể lộ SQL/PII và vẫn mất cause chain | Dùng message an toàn, giữ Throwable làm cause |
| Log `error.getMessage()` không kiểm soát | Message driver có thể chứa dữ liệu nhạy cảm | Log error type/category và metadata allowlist |
| Gọi `log.error("...", error)` ở mọi tầng | In nhiều cause chain, có thể lộ SQL/PII và tạo log trùng | Chọn một boundary log cuối cùng |
| Log toàn bộ entity/request body | Có thể ghi password, token, PII và dữ liệu thanh toán | Ghi trường allowlist đã phê duyệt |
| Bật TRACE cho R2DBC driver ở production | Có thể lộ SQL và bind values | Dùng mức log an toàn; bật chẩn đoán có kiểm soát |
| Trả `exception.getMessage()` cho client | Tiết lộ schema, SQL hoặc hạ tầng | Trả mã lỗi và thông báo tổng quát |
| Dùng `onErrorResume` để che mọi lỗi | Caller không phân biệt lỗi kỹ thuật với empty | Chỉ fallback cho loại lỗi được xác định |
| Log input không tin cậy nguyên văn | Có nguy cơ log injection/forging | Structured logging, encode CR/LF và giới hạn độ dài |
| Hash email bằng SHA-256 rồi coi là ẩn danh | Có thể dò ngược do không gian giá trị nhỏ | Dùng ID nội bộ hoặc HMAC với khóa bảo vệ khi phù hợp |
| Redact sau khi đã gửi log | Bản sao/archive/alert có thể vẫn chứa dữ liệu | Làm sạch trước khi ghi hoặc gửi |
| Đưa token vào Reactor Context/MDC | Token có thể bị instrumentation tự động ghi | Chỉ truyền correlation/trace metadata an toàn |
| Parse exception message để phân loại lỗi | Dễ hỏng theo driver/version/locale | Dùng SQLSTATE, vendor code và metadata có cấu trúc |

## 19. Quy trình xử lý một lỗi database an toàn

Khi một thao tác R2DBC thất bại, có thể áp dụng trình tự sau:

1. **Giữ lỗi gốc:** không bỏ cause khi chuyển exception.
2. **Phân loại:** xác định lỗi kết nối, timeout, toàn vẹn dữ liệu, transaction, mapping hay lỗi khác.
3. **Chuyển ngữ nghĩa:** nếu cần, ánh xạ sang exception nghiệp vụ với message không chứa dữ liệu nhạy cảm.
4. **Giữ lỗi đi đúng boundary:** không nuốt lỗi trước transaction manager hoặc caller nếu use case phải thất bại.
5. **Chọn metadata log:** operation code, correlation ID, error category, exception type và mã lỗi được phép.
6. **Loại dữ liệu nhạy cảm:** không ghi payload, token, password, raw bind values hoặc message chưa được kiểm soát.
7. **Log một lần ở boundary:** tránh mỗi tầng ghi cùng stack trace.
8. **Phản hồi an toàn:** trả HTTP status/mã lỗi công khai, không trả cause hoặc stack trace.
9. **Bảo vệ log sink:** phân quyền, retention và mã hóa theo chính sách.
10. **Kiểm thử:** xác nhận cause chain còn nguyên và log/response không chứa secret hoặc PII.

## 20. Nguyên tắc cần nhớ

- Exception mới nên giữ exception cũ làm cause bằng constructor `(message, cause)`.
- Không thay cause bằng chuỗi `getMessage()`; message không giữ kiểu lỗi và có thể chứa SQL hoặc dữ liệu nhạy cảm.
- Dùng `onErrorMap` để đổi loại lỗi mà vẫn giữ tín hiệu `onError`; dùng `onErrorResume` chỉ khi thực sự có fallback.
- `doOnError` quan sát lỗi nhưng không xử lý hoặc nuốt lỗi.
- Giữ cause trong bộ nhớ không có nghĩa phải ghi toàn bộ cause chain vào log.
- Không log password, API key, access/refresh token, private key, session cookie, CVV hoặc dữ liệu nhạy cảm tương tự.
- Không log toàn bộ entity, request/response body, SQL bind values hoặc exception message chưa được kiểm soát.
- Ưu tiên log có cấu trúc và allowlist trường an toàn: operation, correlation ID, error category, exception type, thời gian.
- Dùng SQLSTATE/vendor code có cấu trúc để phân loại khi phù hợp; không parse message tùy tiện.
- Tránh log cùng một exception ở mọi tầng; chọn application boundary chịu trách nhiệm ghi event.
- Structured logging và parameterized logging không tự làm sạch dữ liệu; vẫn cần kiểm soát đầu vào.
- Chống log injection bằng encoding, loại CR/LF, giới hạn độ dài và không cho input điều khiển cấu trúc event.
- Không trả exception message, SQL, stack trace hoặc cause cho API client.
- Truyền correlation/trace ID an toàn qua Reactor Context; không đưa secret vào context chỉ để log.
- Bảo vệ log sink bằng phân quyền, mã hóa, retention và kiểm soát chia sẻ.
- Kiểm thử cả việc giữ cause và việc không lộ dữ liệu nhạy cảm trong log/response.

Giữ nguyên nguyên nhân lỗi giúp chẩn đoán sự cố R2DBC mà không làm mất thông tin từ Spring hoặc driver. Nhưng log là một đầu ra có vòng đời và quyền truy cập riêng, vì vậy không nên ghi mọi thứ mà exception đang chứa. Khi chuyển exception bằng cause chain, phân loại lỗi bằng metadata có cấu trúc, log theo allowlist và trả response công khai đã được kiểm soát, ứng dụng vừa giữ được khả năng điều tra vừa giảm nguy cơ rò rỉ dữ liệu nhạy cảm.

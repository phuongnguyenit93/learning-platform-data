# Giữ nguyên nguyên nhân lỗi và giới hạn dữ liệu nhạy cảm trong log

## 1. Bài toán: xử lý lỗi Redis mà vẫn chẩn đoán được và không làm lộ dữ liệu

Một ứng dụng Spring Boot dùng Spring Data Redis để đọc cache, lưu phiên, thực hiện thao tác Hash và nhận thông điệp. Khi Redis mất kết nối hoặc serializer gặp dữ liệu không hợp lệ, một lỗi kỹ thuật có thể đi qua nhiều tầng:

```text
Lettuce / Redis connection
          |
          | RedisCommandTimeoutException hoặc lỗi I/O
          v
Spring Data Redis
          |
          | Chuyển đổi / bọc exception
          v
Repository / Service
          |
          | CacheAccessException
          v
REST Controller / Reactive handler
          |
          v
HTTP error + telemetry
```

Trong quá trình này, hai yêu cầu đôi khi bị hiểu nhầm là đối lập:

1. **Giữ nguyên nguyên nhân lỗi:** exception ở tầng trên cần giữ liên kết với lỗi gốc để có thể tìm hiểu lỗi kết nối, timeout, serializer, dữ liệu sai kiểu hoặc lệnh Redis thất bại.
2. **Giới hạn dữ liệu nhạy cảm trong log:** không đưa mật khẩu, token, session ID, toàn bộ Redis key, dữ liệu value, nội dung lệnh hoặc chi tiết của người dùng vào log chỉ để chẩn đoán sự cố.

Ví dụ hai cách xử lý đều có vấn đề:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    throw new RuntimeException("Redis error");
}
```

Đoạn trên làm mất **cause** vì không truyền `ex` vào exception mới.

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    log.error("Redis failed, key={}, value={}, exception={}",
            key, value, ex.getMessage(), ex);
    throw ex;
}
```

Đoạn thứ hai có thể làm lộ thông tin nhạy cảm. Key Redis đôi khi chứa email, số điện thoại, user ID hoặc session identifier. Value có thể chứa dữ liệu cá nhân. Thông điệp `ex.getMessage()` hoặc **stack trace đầy đủ** từ driver cũng có thể chứa key, command, URL kết nối hoặc tham số.

**Nguyên tắc chính:** giữ nguyên đối tượng lỗi trong **chuỗi `cause` của exception**, nhưng **không tự động đẩy toàn bộ exception, message và dữ liệu nghiệp vụ ra log**. Log nên dùng các thuộc tính đã được lựa chọn và kiểm soát.

Bài học thuộc chương **Xử lý lỗi** trong **Spring Data Redis**. Mục tiêu là triển khai xử lý lỗi dễ điều tra, an toàn dữ liệu và nhất quán qua RedisTemplate, reactive Redis, listener và REST API.

## 2. Phân biệt nguyên nhân lỗi, thông điệp lỗi và thông tin được phép ghi log

Một exception Java có nhiều thành phần:

```text
Class/type:        RedisConnectionFailureException
Message:           Có thể chứa địa chỉ server / nội dung lệnh
Cause:             Lỗi cấp thấp hơn, ví dụ lỗi I/O
Suppressed:        Lỗi phụ trong xử lý tài nguyên
Stack trace:       Vị trí lỗi trong các lớp Java
Context:           Tên thao tác, request ID, thời gian, số lần retry
```

Những thành phần này không có mức độ an toàn giống nhau.

| Thành phần | Giá trị chẩn đoán | Rủi ro khi xuất ra log |
|---|---|---|
| Exception class | Biết nhóm lỗi kỹ thuật | Thường thấp hơn payload |
| Cause class | Biết nguyên nhân cấp thấp | Thường thấp hơn raw message |
| Exception message | Có thể chứa thông tin chi tiết của driver | Có thể mang key, URI, lệnh hoặc dữ liệu người dùng |
| Stack trace đầy đủ | Biết đường đi của lỗi | Có thể chứa exception messages, suppressed exceptions và chi tiết hạ tầng |
| Redis key | Xác định tài nguyên lỗi | Có thể chứa định danh cá nhân hoặc token |
| Redis value | Biết nội dung được xử lý | Rất dễ chứa thông tin nhạy cảm |
| Raw Redis command | Hữu ích để gỡ lỗi protocol | Có thể chứa payload, mật khẩu, script arguments |
| Operation name cố định | Biết chức năng đang lỗi | Thường an toàn nếu lấy từ allowlist |
| Error category | Phân nhóm để cảnh báo | Thường an toàn |
| Trace ID nội bộ | Liên kết các bước xử lý | Thường an toàn nếu được tạo và quản lý đúng |
| Timing/duration | Đo timeout và độ trễ | Thường an toàn |
| Retry attempt | Biết lỗi đã lặp bao nhiêu lần | Thường an toàn |

**Giữ nguyên exception** không đồng nghĩa **được phép ghi toàn bộ exception ra mọi log sink**. Thông tin để tái hiện/chẩn đoán có thể được giữ trong object cause chain trong quá trình chạy, trong hệ thống quan sát được kiểm soát, hoặc trong một môi trường gỡ lỗi hạn chế quyền.

### 2.1. Một Redis key cũng có thể là dữ liệu nhạy cảm

Ví dụ:

```text
session:7f3c88b7a0e94c7ba...
user:lan@example.com:profile
password-reset:one-time-token
auth:bearer:eyJ...
tenant:acme:customer:8490...
```

Ngay cả khi value là `true`, tên key vẫn có thể tiết lộ danh tính, trạng thái phiên hoặc token. Không nên mặc định “key là metadata nên được log”.

### 2.2. Stack trace không mặc định an toàn

Một lệnh quen thuộc:

```java
log.error("Redis failed", ex);
```

thường khiến logging framework in exception class, message, cause chain và stack trace. Nếu exception message chứa chuỗi kết nối hoặc nội dung dữ liệu, dữ liệu đó có thể đi thẳng tới hệ thống log tập trung.

Trong production, **không áp dụng việc log throwable đầy đủ như một quy tắc chung** cho mọi Redis exception. Nếu thực sự cần stack trace, phải đánh giá nội dung mà thư viện có thể nhúng vào message và dùng kênh chẩn đoán hạn chế quyền hoặc cơ chế trích xuất thông tin đã được làm sạch.

## 3. Cơ chế chuyển đổi exception của Spring Data Redis

Spring Data Redis hoạt động trên các Redis drivers, thường là **Lettuce**. Lỗi từ driver có thể được ánh xạ sang exception của Spring Data Redis và hệ thống **Spring DataAccessException**.

Một số loại thường gặp:

| Nhóm lỗi | Dấu hiệu ở tầng ứng dụng | Ý nghĩa xử lý |
|---|---|---|
| Không kết nối được Redis | `RedisConnectionFailureException` hoặc cause kết nối | Redis hoặc mạng tạm không khả dụng |
| Timeout | `QueryTimeoutException` hoặc cause timeout từ driver | Lệnh không nhận được phản hồi trong ngân sách |
| Lỗi command hoặc server | `RedisSystemException`/`DataAccessException` thích hợp | Phải xét lệnh, quyền, cấu hình, trạng thái server |
| Lỗi serialize/deserialize | `SerializationException` hoặc cause liên quan | Có thể sai schema hoặc byte không tương thích |
| Sai kiểu Redis | Lỗi command như `WRONGTYPE` được bọc | Cần kiểm tra schema/type, không coi là cache miss |
| Sai xác thực/ACL | Lỗi từ driver/server, có thể được chuyển đổi | Cấu hình hoặc phân quyền cần sửa |
| Không tìm thấy key | `GET` trả `null`/`Mono.empty()` | **Không phải một exception** |

Tên exception cụ thể có thể phụ thuộc phiên bản Spring Data Redis, driver và loại lệnh. Do đó, **không chỉ dựa vào một chuỗi thông báo lỗi** để phân loại:

```java
if (ex.getMessage().contains("timeout")) {
    // Fragile: message thay đổi hoặc có thể null.
}
```

Ưu tiên phân loại bằng **type** của exception và những thuộc tính có cấu trúc mà thư viện cung cấp, đồng thời giữ `cause` gốc khi bọc.

### 3.1. Một cause chain hợp lệ

```text
CacheAccessException: "Redis read failed"
    caused by RedisConnectionFailureException
        caused by RedisCommandTimeoutException
```

Exception ở tầng service có một **thông điệp an toàn, ổn định**, nhưng nguyên nhân kỹ thuật vẫn được giữ trong `getCause()` để phần xử lý nội bộ thích hợp có thể kiểm tra.

### 3.2. Không làm mất nguyên nhân bằng cách dựng exception chỉ từ message

Sai:

```java
catch (DataAccessException ex) {
    throw new IllegalStateException(ex.getMessage());
}
```

Vì:

- `getCause()` của exception mới là `null`.
- Type gốc bị thay bởi một thông điệp text khó phân loại.
- Message gốc có thể chứa thông tin nhạy cảm và bị đưa sang response/log ở tầng trên.

Đúng hơn:

```java
catch (DataAccessException ex) {
    throw new CacheAccessException(
            RedisFailureCategory.OTHER_REDIS_ERROR,
            ex
    );
}
```

Exception mới giữ **cause là chính object `ex`**, không chỉ sao chép message.

## 4. Thiết kế exception nghiệp vụ với thông điệp an toàn và cause gốc

### 4.1. Phân loại lỗi theo nhóm hữu hạn

```java
package com.example.redis.errors;

public enum RedisFailureCategory {
    CONNECTION,
    TIMEOUT,
    SERIALIZATION,
    OTHER_REDIS_ERROR
}
```

Đây là **enum do ứng dụng định nghĩa**, không phải một exception của Spring. Giá trị hữu hạn giúp các bảng điều khiển không phải dùng raw error messages làm metric label.

### 4.2. Exception giữ original cause

```java
package com.example.redis.errors;

public final class CacheAccessException extends RuntimeException {

    private final RedisFailureCategory category;
    private final String safeOperation;

    public CacheAccessException(
            String safeOperation,
            RedisFailureCategory category,
            Throwable originalCause) {

        // Thông điệp của wrapper được cố định và không chứa key/value.
        super("Redis dependency operation failed", originalCause);

        this.safeOperation = safeOperation;
        this.category = category;
    }

    public RedisFailureCategory category() {
        return category;
    }

    public String safeOperation() {
        return safeOperation;
    }
}
```

Trong ví dụ, `safeOperation` phải là giá trị từ **allowlist của code**, chẳng hạn:

```text
product_cache_read
product_cache_write
session_lookup
```

Không lấy nguyên `safeOperation` từ request path, tên Redis key, input người dùng hoặc một Redis command động. Một trường đặt tên “safe” không tự trở thành an toàn nếu dữ liệu đầu vào không được kiểm soát.

Ví dụ sử dụng:

```java
throw new CacheAccessException(
        "product_cache_read",
        RedisFailureCategory.CONNECTION,
        originalException
);
```

Kết quả:

- Message công khai của wrapper được giới hạn.
- Tầng trên có thể xem `category` và `safeOperation`.
- `getCause()` trả về original exception; cause chain được giữ.

## 5. Xây service dùng RedisTemplate và không log dữ liệu nhạy cảm

Giả sử ứng dụng đọc JSON đã lưu dưới Redis key có ID sản phẩm. Trong code nghiệp vụ, ID có thể có ý nghĩa, nhưng không cần đưa full key vào log.

### 5.1. Đường đọc có phân loại lỗi

```java
package com.example.redis.errors;

import java.util.Optional;

import org.springframework.dao.DataAccessException;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.SerializationException;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;

    public ProductCacheReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Optional<String> read(long productId) {
        if (productId <= 0) {
            throw new IllegalArgumentException(
                    "productId phải là số dương"
            );
        }

        String key = "product:detail:v3:" + productId;

        try {
            String value = redis.opsForValue().get(key);
            return Optional.ofNullable(value);

        } catch (DataAccessException | SerializationException ex) {
            throw new CacheAccessException(
                    "product_cache_read",
                    categorize(ex),
                    ex
            );
        }
    }

    private static RedisFailureCategory categorize(RuntimeException ex) {
        if (ex instanceof RedisConnectionFailureException) {
            return RedisFailureCategory.CONNECTION;
        }

        if (ex instanceof QueryTimeoutException) {
            return RedisFailureCategory.TIMEOUT;
        }

        if (ex instanceof SerializationException) {
            return RedisFailureCategory.SERIALIZATION;
        }

        return RedisFailureCategory.OTHER_REDIS_ERROR;
    }
}
```

Ở đây:

1. `GET` trả `null` nếu không có key, được biểu diễn bằng `Optional.empty()`.
2. Lỗi kết nối, command hoặc serialization được bọc thành `CacheAccessException`.
3. **Original exception được truyền làm cause**.
4. Service **không log full key, value hoặc toàn bộ throwable**.
5. Tầng biên API sẽ quyết định log một lần với các field an toàn.

Một vài Redis error có thể đến từ lỗi lập trình hoặc exception không thuộc nhóm đã bắt. Không nên dùng `catch (Exception)` với mục tiêu nuốt toàn bộ lỗi. Nếu cần bao trùm thêm lỗi từ thư viện, phải phân loại type cụ thể và đảm bảo không che lỗi code.

### 5.2. Lỗi serializer cần giữ nguyên nguyên nhân nhưng không lộ payload

Nếu Redis chứa JSON không phù hợp với model:

```java
ProductProfile value = jsonTemplate
        .opsForValue()
        .get("profile:v3:42");
```

serializer có thể ném lỗi giải mã. Không nên làm:

```java
log.warn("Invalid redis value: {}", rawJson);
```

Thay vào đó, ghi nhóm lỗi và phiên bản schema:

```text
event=redis_operation_failed
operation=profile_cache_read
category=SERIALIZATION
schemaVersion=3
exceptionClass=SerializationException
```

Thông tin này giúp tìm đúng loại vấn đề mà không đưa JSON người dùng vào hệ thống log.

**Không coi serializer error là cache miss theo mặc định.** Nếu lỗi bị nuốt, ứng dụng có thể âm thầm ghi lại cache sai hoặc che một sự cố triển khai thay đổi schema.

## 6. Chỉ ghi log tại ranh giới xử lý phù hợp

Một anti-pattern phổ biến là mỗi tầng đều ghi cùng lỗi:

```text
Redis Driver        -> log error
Repository          -> log error + throw
Service             -> log error + throw
Controller Advice   -> log error
API Gateway         -> log error
```

Một lỗi Redis đơn lẻ tạo ra nhiều dòng stack trace, làm:

- Tăng chi phí ghi log.
- Tăng nguy cơ xuất hiện dữ liệu nhạy cảm ở nhiều nơi.
- Khó đếm số lỗi thật.
- Dễ tạo **log storm** khi Redis mất kết nối trên toàn hệ thống.

Một quy tắc thực tế:

- **Tầng thấp** giữ nguyên exception, bổ sung ngữ cảnh **an toàn** nếu cần rồi propagate.
- **Tầng có quyền quyết định fallback/retry** xử lý đúng nhóm lỗi, ghi metric.
- **Tầng biên** ghi log sự kiện lỗi một lần theo định dạng đã kiểm soát.
- Những nơi khác không lặp lại cùng stack trace vô ích.

Ví dụ:

```text
Repository -> CacheAccessException(original cause)
        |
        v
Service -> quyết định propagate
        |
        v
ControllerAdvice -> log event an toàn một lần
        |
        v
Response -> mã lỗi chung + errorId
```

Nếu một lỗi đã được xử lý hoàn toàn bằng fallback, tầng biên có thể không nhận exception nữa; khi đó tầng xử lý fallback cần ghi metric và một log an toàn có giới hạn, thay vì để sự cố Redis biến mất hoàn toàn khỏi quan sát.

## 7. Logging an toàn tại tầng API: giữ cause, không in raw throwable

### 7.1. Chuẩn hóa response

Không trả exception message từ Redis trực tiếp cho client:

```java
return ResponseEntity.status(500).body(ex.getMessage());
```

Message có thể chứa thông tin hạ tầng hoặc dữ liệu của một yêu cầu khác. Thay vào đó, trả một mã lỗi ổn định và một ID dùng để đối chiếu log.

```json
{
  "code": "REDIS_DEPENDENCY_UNAVAILABLE",
  "message": "Dịch vụ tạm thời không khả dụng",
  "errorId": "93acbfbb-36a0-4ca0-aefa-e1d24a06c9bc"
}
```

Đây là ví dụ về cấu trúc response; giá trị `errorId` thực tế phải được tạo riêng cho sự kiện lỗi.

### 7.2. ControllerAdvice chỉ ghi field đã kiểm soát

```java
package com.example.redis.errors;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class RedisErrorAdvice {

    private static final Logger log =
            LoggerFactory.getLogger(RedisErrorAdvice.class);

    public record ApiError(
            String code,
            String message,
            String errorId
    ) {
    }

    @ExceptionHandler(CacheAccessException.class)
    public ResponseEntity<ApiError> handle(CacheAccessException ex) {

        String errorId = UUID.randomUUID().toString();
        Throwable root = rootCause(ex);

        // Cố ý KHÔNG thêm ex như một argument cuối của log.
        // Có thể giữ cause trong object mà không xuất raw messages.
        log.warn(
                "event=redis_dependency_failure"
                + " operation={} category={} exceptionType={}"
                + " rootCauseType={} errorId={}",
                ex.safeOperation(),
                ex.category(),
                ex.getCause().getClass().getName(),
                root.getClass().getName(),
                errorId
        );

        ApiError body = new ApiError(
                "REDIS_DEPENDENCY_UNAVAILABLE",
                "Dịch vụ tạm thời không khả dụng",
                errorId
        );

        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(body);
    }

    private static Throwable rootCause(Throwable failure) {
        Throwable current = failure;

        // Cause chain thường không tạo vòng; giới hạn bước
        // để tránh một Throwable bất thường gây vòng vô hạn.
        for (int i = 0; i < 32; i++) {
            Throwable next = current.getCause();

            if (next == null || next == current) {
                break;
            }

            current = next;
        }

        return current;
    }
}
```

Các đặc điểm quan trọng:

- `ex.getCause()` vẫn được giữ nguyên trong `CacheAccessException`.
- Log sử dụng `operation` từ code, category và tên class.
- Log **không ghi Redis key, value, query hoặc exception message**.
- Log **không truyền `ex` vào vị trí `Throwable` của SLF4J** nên không tự in cause chain.
- HTTP response không lộ exception class, host Redis, key hoặc stack trace.
- `errorId` giúp liên kết response với một sự kiện log.

Không nhất thiết mọi lỗi Redis phải trả 503. Lựa chọn HTTP 503 trong ví dụ dành cho tình huống đường đọc hiện tại phụ thuộc Redis và không có fallback. Với các loại lỗi hoặc hợp đồng API khác, cần chọn status phù hợp; không nên biến mọi lỗi đầu vào thành “Redis unavailable”.

### 7.3. Giữ đầy đủ cause để làm gì nếu không log stack?

Cause chain có thể phục vụ:

- Điều kiện retry/fallback ở tầng xử lý nội bộ.
- Thu thập thông tin theo chính sách bảo mật trong môi trường chẩn đoán được kiểm soát.
- Phân loại chính xác lỗi thư viện.
- Kiểm thử rằng wrapper không làm mất lỗi gốc.
- Debug tại ứng dụng khi có quyền truy cập phù hợp.

Nếu cần tăng độ chi tiết, ưu tiên bổ sung **thông tin an toàn có cấu trúc**: exception type, operation, thời gian, phase, node role, retry count, component, error ID. Chỉ cho phép full throwable vào log chuyên biệt khi đã đánh giá driver/serializer và giới hạn được dữ liệu nhạy cảm có thể có trong message.

## 8. Quy tắc dữ liệu được phép ghi và không được ghi

Một chính sách log rõ ràng giúp đội phát triển không phải quyết định lại cho từng endpoint.

### 8.1. Nên ghi các field đã được phép

Ví dụ:

```text
event             = redis_dependency_failure
operation         = session_lookup
category          = TIMEOUT
component         = auth-service
redisCommandClass = GET
durationMs        = 803
attempt           = 2
exceptionType     = QueryTimeoutException
rootCauseType     = RedisCommandTimeoutException
errorId           = 93acbfbb-36a0-4ca0-aefa-e1d24a06c9bc
```

Các field như `operation`, `component`, `redisCommandClass` nên được chọn từ **enum hoặc allowlist**. `durationMs` và `attempt` là dữ liệu đo đạc có giới hạn.

`rootCauseType` nói nguyên nhân thuộc nhóm nào mà không phát tán `getMessage()` của driver.

### 8.2. Không ghi những thứ sau theo mặc định

- Password, access token, session token, refresh token, API key.
- Redis URI có user/password hoặc tham số xác thực.
- Redis key có chứa email, số điện thoại, tenant ID hoặc định danh người dùng.
- Toàn bộ Redis command, nhất là `SET`, `HSET`, Lua arguments, `AUTH`.
- Redis value: JSON, serialized object, Hash fields, Stream payload.
- Nội dung Pub/Sub message.
- Dữ liệu phản hồi từ Redis dùng trong quyết định phân quyền.
- Raw `ex.getMessage()`, `ex.toString()` hoặc stack trace từ thư viện chưa được đánh giá.
- Payload mà ứng dụng chuẩn bị ghi nhưng Redis từ chối.
- Toàn bộ request/response HTTP trong một log lỗi Redis.

Ngay cả việc ghi chuỗi đã thay một số ký tự bằng `***` cũng có thể không đủ nếu format khác, dữ liệu được mã hóa hoặc exception chứa cùng dữ liệu ở nhiều vị trí.

### 8.3. Dùng tên namespace thay vì full key

Thay vì:

```text
key=session:eyJhbGciOiJIUzI1Ni...
```

ghi:

```text
namespace=session
operation=session_lookup
```

Namespace phải được lấy từ code hoặc một bảng ánh xạ hữu hạn, không ghép trực tiếp một chuỗi do user cung cấp.

Nếu cần phân biệt một logical key qua nhiều log, cân nhắc **mã định danh giả danh có kiểm soát**:

```text
keyFingerprint=HMAC-SHA256(secret, rawKey) [cắt ngắn đủ dài]
```

HMAC với secret quản lý an toàn thường khó bị đoán lại hơn việc dùng SHA-256 không khóa cho những ID có không gian giá trị nhỏ. Tuy nhiên:

- Fingerprint vẫn có thể là dữ liệu liên kết hoạt động theo thời gian; phải có retention và kiểm soát quyền.
- Không ghi secret vào code/log.
- Không dùng fingerprint như cơ chế xác thực.
- Không biến fingerprint có cardinality cao thành tag metric.
- Với nhiều trường hợp, chỉ cần namespace và error ID là đủ; không phải lỗi nào cũng cần fingerprint.

### 8.4. Địa chỉ Redis cũng nên được cân nhắc

Host/port có thể hữu ích để biết một replica hay shard lỗi, nhưng full connection URL dễ chứa thông tin xác thực.

Ưu tiên một node identifier đã chuẩn hóa:

```text
redisNodeRole=replica
redisNodeAlias=cache-node-2
```

thay vì nối toàn bộ `redis://username:password@host:port` vào log.

## 9. Chẩn đoán nguyên nhân gốc mà không phụ thuộc exception message

### 9.1. Phân nhóm theo type

Tầng ứng dụng có thể giữ:

```java
new CacheAccessException(
        "profile_cache_read",
        RedisFailureCategory.SERIALIZATION,
        serializationException
);
```

Khi điều tra:

```text
operation=profile_cache_read
category=SERIALIZATION
rootCauseType=JsonMappingException
schemaVersion=3
```

Đó là đủ để nhóm phát triển biết phải xem schema, format serializer và quá trình chuyển phiên bản mà không cần xem dữ liệu profile thật.

### 9.2. Không suy luận chỉ dựa trên root-cause class

Một cùng loại lỗi I/O có thể xuất hiện vì:

- Redis server tạm quá tải.
- Mạng bị ngắt.
- Timeout quá thấp.
- Connection bị đóng trong failover.
- Client pool hoặc event loop bị nghẽn.

Exception class là tín hiệu ban đầu, không phải toàn bộ nguyên nhân. Cần kết hợp telemetry:

```text
client latency p95/p99
Redis INFO stats
connection failures
pool pending
server role/topology
retry attempts
time window
deployment version
```

Có thể lưu thông tin này dưới các nhãn đã được kiểm soát. Tránh bật log raw commands chỉ để đoán vấn đề.

### 9.3. Safe error context nên bất biến khi lan qua tầng

Một exception wrapper có thể gắn:

```text
safeOperation = product_cache_read
category = TIMEOUT
```

Khi qua nhiều tầng, không nên thay liên tục bằng những message chứa key:

```java
throw new RuntimeException(
        "Failed to read " + key + " because " + ex.getMessage(),
        ex
);
```

Dù cause được giữ, wrapper message mới lại có thể lộ key khi bất cứ nơi nào gọi `toString()` hoặc in stack.

Nên dùng message an toàn, gắn context có cấu trúc hoặc thông tin riêng với khả năng kiểm soát ở boundary.

## 10. Phân biệt cache miss và Redis lỗi

Một lỗi thiết kế nghiêm trọng:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    return null;
}
```

Cách này biến mọi lỗi thành “không có key”:

```text
Redis GET trả null        -> MISS hợp lệ
Redis connection timeout  -> cũng trả null
Serializer hỏng           -> cũng trả null
AUTH/ACL lỗi              -> cũng trả null
```

Hậu quả:

- Ứng dụng không biết Redis đang lỗi.
- Cache miss ratio bị thổi phồng.
- Database có thể bị quá tải khi fallback.
- Các lỗi dữ liệu bị che khuất.
- Không còn cause chain để phân tích.

Một kết quả rõ hơn:

```text
CACHE_HIT
CACHE_MISS
CACHE_ERROR_CONNECTION
CACHE_ERROR_TIMEOUT
CACHE_ERROR_SERIALIZATION
```

Có thể thiết kế kiểu trả về phân biệt các trạng thái này hoặc để `null`/`Optional.empty()` biểu thị miss và dùng exception cho lỗi.

**Không coi `SerializationException` là miss theo mặc định** nếu Redis có thể đang giữ byte sai schema cần được điều tra.

## 11. Fallback an toàn khi Redis chỉ là cache

Không phải mọi lỗi Redis đều buộc API thất bại. Nếu dữ liệu có một **nguồn có thẩm quyền** khác, có thể đọc từ nguồn đó khi Redis mất kết nối.

Ví dụ logic:

```text
GET cache
   |
   +-- Hit --------> Trả cache
   |
   +-- Miss -------> Đọc database -> Có thể nạp lại cache
   |
   +-- Redis down -> Đọc database (fallback có kiểm soát)
   |
   +-- Serializer error -> Báo lỗi / cách ly theo chính sách
```

Điểm cần thiết kế:

- Chỉ fallback cho những nhóm lỗi được cho phép, ví dụ mất kết nối.
- Không bao giờ coi lỗi phân quyền hoặc serializer sai là cache miss một cách âm thầm.
- Ghi metric `redis_fallback_total`, phân loại lỗi.
- Dùng concurrency/rate limit cho fallback để database không bị áp đảo khi Redis outage.
- Có timeout tổng cho API.
- Nếu fallback cũng thất bại, phải giữ được **cả thông tin lỗi Redis và lỗi nguồn** mà không ghi payload ra log.

### 11.1. Giữ hai nguyên nhân khi fallback cũng thất bại

Ví dụ một custom exception:

```java
package com.example.redis.errors;

public final class CacheFallbackException extends RuntimeException {

    public CacheFallbackException(
            Throwable sourceFailure,
            Throwable redisFailure) {

        super(
                "Both cache and authoritative source failed",
                sourceFailure
        );

        // Lỗi database là nguyên nhân chính của lần fallback thất bại.
        // Lỗi Redis là một lỗi liên quan được giữ để chẩn đoán.
        addSuppressed(redisFailure);
    }
}
```

Mã ý tưởng:

```java
try {
    return readFromRedis();
} catch (RedisConnectionFailureException redisFailure) {
    try {
        return readFromDatabase();
    } catch (RuntimeException sourceFailure) {
        throw new CacheFallbackException(
                sourceFailure,
                redisFailure
        );
    }
}
```

Ở đây `cause` là lỗi từ nguồn có thẩm quyền, còn lỗi Redis nằm trong `getSuppressed()`. Cả hai không bị mất, trong khi wrapper message không chứa dữ liệu người dùng.

**Lưu ý:** khi log `CacheFallbackException` với full throwable, suppressed exception cũng có thể bị in ra cùng message. Vì vậy quy tắc log an toàn tại boundary vẫn phải được áp dụng.

### 11.2. Không fallback cho dữ liệu Redis có thẩm quyền nếu không có nguồn thay thế

Một số ứng dụng dùng Redis làm nơi lưu trạng thái duy nhất (counter, lock, session, Stream pending). Nếu Redis lỗi, không thể bịa một bản dữ liệu từ database không tồn tại.

Chỉ bật fallback khi hệ thống thực sự có nguồn dữ liệu khác và có định nghĩa rõ ràng về tính nhất quán.

## 12. Reactor và ReactiveRedisTemplate: giữ cause qua onErrorMap

Spring Data Redis Reactive sử dụng `Mono` và `Flux`. Lỗi Redis thường đi qua tín hiệu `onError`.

### 12.1. Dùng onErrorMap với original exception

Ví dụ:

```java
package com.example.redis.errors;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.serializer.SerializationException;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveProfileCacheReader {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveProfileCacheReader(
            ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<String> read(long userId) {
        String key = "profile:cache:v3:" + userId;

        return redis.opsForValue()
                .get(key)
                .onErrorMap(
                        DataAccessException.class,
                        ex -> new CacheAccessException(
                                "profile_cache_read",
                                RedisFailureCategory.OTHER_REDIS_ERROR,
                                ex
                        )
                )
                .onErrorMap(
                        SerializationException.class,
                        ex -> new CacheAccessException(
                                "profile_cache_read",
                                RedisFailureCategory.SERIALIZATION,
                                ex
                        )
                );
    }
}
```

`onErrorMap` tạo wrapper **nhưng vẫn giữ `ex` làm cause**. Trong ứng dụng thực, có thể áp dụng hàm phân loại type cho nhóm `DataAccessException` thay vì luôn dùng `OTHER_REDIS_ERROR`.

**Lưu ý phân biệt:**

- `Mono.empty()` là kết quả không có dữ liệu, không phải tín hiệu lỗi.
- `onErrorMap` không áp dụng với `Mono.empty()`.
- `onErrorResume` dùng để thay thế lỗi bằng một Publisher khác khi đã có chính sách fallback.
- `onErrorComplete` có thể nuốt lỗi; không dùng tùy tiện để biến sự cố Redis thành hoàn thành rỗng.

### 12.2. onErrorResume có thể che mất sự cố nếu không có telemetry

Ví dụ có rủi ro:

```java
return redis.opsForValue()
        .get(key)
        .onErrorResume(ex -> Mono.empty());
```

Mọi lỗi bị biến thành miss, kể cả serializer hỏng và lỗi quyền truy cập. Client có thể không biết Redis đang down, còn đội vận hành không có số liệu sự cố.

Tốt hơn là giới hạn fallback theo type:

```java
return redis.opsForValue()
        .get(key)
        .onErrorResume(
                RedisConnectionFailureException.class,
                ex -> {
                    // Ghi metric/log an toàn về fallback, không log key.
                    return authoritativeSource.read(userId);
                }
        );
```

`authoritativeSource.read(userId)` chỉ là một Publisher do ứng dụng cung cấp; nó phải có giới hạn tải và chính sách lỗi riêng.

Ví dụ cần import `RedisConnectionFailureException` từ Spring Data Redis và định nghĩa `authoritativeSource` tương ứng. Nếu Redis exception bị một tầng khác bọc thành `CacheAccessException`, hãy áp dụng fallback đúng **vị trí trong chuỗi** hoặc phân loại wrapper thay vì mong đợi cùng một exception type.

### 12.3. Không tạo log trùng tại doOnError và boundary

Một chuỗi như:

```java
return redis.opsForValue()
        .get(key)
        .doOnError(ex -> log.error("Redis error", ex))
        .onErrorMap(ex -> new CacheAccessException(
                "profile_cache_read",
                RedisFailureCategory.OTHER_REDIS_ERROR,
                ex
        ));
```

có thể vừa log raw throwable vừa làm tầng API log thêm một lần. Nên chỉ instrument thành metric/telemetry an toàn tại service, còn log sự kiện xử lý cuối ở boundary.

### 12.4. Reactor Context và trace ID

Với WebFlux, công việc có thể chuyển giữa nhiều luồng. Không nên cho rằng `ThreadLocal` hoặc MDC truyền qua mọi operator nếu chưa cấu hình cơ chế context propagation.

Nếu cần correlation:

- Sử dụng tracing (ví dụ OpenTelemetry) hoặc `Reactor Context` theo cấu hình thực tế.
- Tránh đặt user token, Redis key hoặc payload vào trace baggage.
- Nếu nhận request ID từ HTTP header do client gửi, phải kiểm tra định dạng và giới hạn độ dài; không coi chuỗi tùy ý của client là field log an toàn.
- Không ghi trace/baggage chứa thông tin bí mật vào message của exception.

## 13. Redis Streams, Pub/Sub và listener: lỗi không được âm thầm mất

Không phải mọi Redis operation đều diễn ra trong một HTTP request.

### 13.1. Pub/Sub listener

Một `MessageListener` có thể nhận byte payload:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    try {
        process(message.getBody());
    } catch (RuntimeException ex) {
        // Ghi lỗi có kiểm soát, không log raw body.
        recordSafeFailure(
                "pubsub_message_process",
                ex.getClass().getName()
        );
    }
}
```

**Không log thẳng `new String(message.getBody())`** khi payload có thể chứa thông tin người dùng.

Redis Pub/Sub thông thường không có cơ chế phát lại/ACK. Nếu listener lỗi sau khi nhận, ghi log và giữ cause không tự làm thông điệp xuất hiện lại. Với tác vụ bắt buộc không được mất, cần cơ chế giao hàng bền vững hơn.

### 13.2. Redis Streams consumer group

Với Stream, một entry có thể còn pending nếu chưa ACK. Khi xử lý lỗi:

```text
XREADGROUP -> nhận entry
        |
        v
Xử lý nghiệp vụ
        |
      Lỗi
        |
        v
Không XACK
        |
        v
Retry/reclaim theo chính sách
```

Log nên chứa:

```text
streamAlias=orders_events
consumerGroup=billing
failureCategory=DOWNSTREAM_TIMEOUT
deliveryAttempt=3
```

Cẩn trọng với `RecordId`, stream key và payload. Nếu stream ID được coi là thông tin an toàn trong hệ thống cụ thể, có thể dùng làm correlation; nếu ID liên kết trực tiếp tới dữ liệu nhạy cảm hoặc thuộc tập dễ truy vấn, phải xem xét chính sách. **Không log toàn bộ Hash/MapRecord** chỉ vì việc parse lỗi.

### 13.3. Lỗi giải mã Stream payload

Nếu consumer không đọc được một entry, cần có chính sách:

- Giữ entry pending để retry có giới hạn khi lỗi tạm thời.
- Nếu payload lỗi vĩnh viễn, chuyển sang dead-letter stream/queue phù hợp trước khi ACK bản gốc.
- Lưu định danh sự kiện và mã lỗi an toàn.
- Không copy raw payload vào log hoặc dead-letter không có kiểm soát truy cập.
- Có thể cần bảo vệ dữ liệu nhạy cảm trong dead-letter storage tương tự nguồn.

Ghi thông báo “deserialization failed” mà không làm mất cause giúp người vận hành phân biệt schema mismatch với Redis connection timeout. Nhưng sự khác biệt phải thể hiện bằng **error type/category**, không cần xuất body.

## 14. Redis Pipeline, Transaction và Lua: lỗi có thể có ngữ cảnh nhạy cảm

### 14.1. Pipeline

Với `RedisTemplate.executePipelined(...)`, ứng dụng có thể gửi nhiều lệnh và thu kết quả sau đó. Một số lỗi có thể xuất hiện ở thời điểm đọc kết quả hoặc deserialize.

Không nên log toàn bộ danh sách lệnh/arguments khi một batch thất bại:

```text
Batch 500 operations
Operation 237 failed
```

Thay vào đó có thể lưu:

```text
operation=batch_profile_cache_fill
batchSize=500
failureCategory=SERIALIZATION
exceptionType=SerializationException
```

Nếu cần tìm key cụ thể, dùng một error ID và một cơ chế kiểm tra giới hạn trên môi trường cho phép, không đưa mọi key và value vào hệ thống log tập trung.

### 14.2. MULTI/EXEC

Trong giao dịch Redis, cần phân biệt:

- Lệnh chưa được gửi thành công.
- `EXEC` đã chạy nhưng ứng dụng chưa nhận được kết quả.
- Lỗi khi giải mã response.
- Xung đột `WATCH` khiến giao dịch không thực thi.

Một lỗi mạng sau `EXEC` không đủ để khẳng định “tất cả lệnh đều chưa được thực hiện”. **Giữ cause chain** để phân tích, nhưng quyết định retry phải dựa trên idempotency và ngữ nghĩa transaction, không chỉ dựa vào tên exception.

### 14.3. Lua script

Lua script có thể nhận arguments chứa token, payload hoặc khóa nhạy cảm. Khi script lỗi, raw error text có thể mang tên script hoặc chi tiết lệnh.

Không log nguyên script text và toàn bộ `KEYS`/`ARGV` theo mặc định. Ghi:

```text
scriptAlias=atomic_cache_update_v2
failureCategory=OTHER_REDIS_ERROR
redisOperation=EVAL
```

Script alias nên được định nghĩa cố định trong code. Nếu cần tra cứu nội dung script, mã nguồn đã version-control là nguồn phù hợp hơn log production.

## 15. Retry: giữ nguyên cause và không tạo lỗi nghiệp vụ mới

Một timeout Redis có thể xảy ra **sau khi Redis đã thực thi lệnh** nhưng trước khi client nhận được phản hồi.

Ví dụ:

```text
Client                  Redis
   |                      |
   | INCR counter -------->|
   |                      | counter tăng 1
   |    [network timeout] |
   |                      |
   | Retry INCR ---------->|
   |                      | counter tăng lần nữa
```

Nếu ứng dụng chỉ thấy `QueryTimeoutException` rồi retry tất cả lệnh, một `INCR` có thể bị thực hiện hai lần.

### 15.1. Phân biệt đọc và ghi

| Thao tác | Rủi ro retry sau timeout |
|---|---|
| `GET` | Thường an toàn hơn về tác dụng phụ; vẫn có thêm tải |
| `HGET` | Chủ yếu là đọc; cần timeout/rate limit |
| `SET` cùng giá trị | Có thể idempotent về value, nhưng TTL/side effect cần xét |
| `INCR` | Có thể tăng hai lần |
| `LPUSH` | Có thể thêm phần tử trùng |
| `XADD` | Có thể tạo thêm entry |
| Lua script chứa ghi | Tùy nội dung script |
| `XACK` | Có thể đã ACK nhưng response bị mất; cần kiểm tra trạng thái |

**Nguyên nhân lỗi được giữ nguyên không có nghĩa retry luôn đúng.** Phải phân loại ngữ nghĩa lệnh và có operation ID/idempotency khi cần.

### 15.2. Retry có giới hạn

Một chính sách retry thực tế cần:

- Chỉ retry nhóm lỗi tạm thời đã được xác định.
- Giới hạn số lần thử.
- Sử dụng backoff/jitter tránh retry storm.
- Có timeout tổng cho request.
- Dừng retry khi phát hiện cấu hình/serializer/schema lỗi.
- Ghi `attempt` và `failureCategory` thay vì mỗi lần in raw stack trace.
- Dùng circuit breaker/bulkhead khi Redis đang lỗi toàn diện.

Nếu cuối cùng thất bại, giữ cause kỹ thuật trong wrapper để phục vụ xử lý phù hợp. Khi chuyển sang lỗi API, không đưa message gốc ra response.

## 16. Redaction ở log pipeline không thay thế an toàn tại nguồn

Có hệ thống cấu hình bộ lọc ở Logback, logging agent hoặc log collector để che chuỗi bí mật. Đây có thể là một lớp bảo vệ bổ sung, nhưng không đủ nếu code đã ghi toàn bộ Redis value.

Ví dụ payload:

```json
{
  "accessToken": "secret",
  "profile": {
    "phone": "...",
    "email": "..."
  }
}
```

Một bộ lọc chỉ tìm chuỗi `"password="` sẽ không che được `"accessToken"` hoặc dữ liệu cá nhân ở cấu trúc JSON. Dữ liệu có thể xuất hiện qua:

- JSON escaping.
- Base64.
- Exception message từ serializer.
- Nested field.
- Chuỗi được nối với prefix khác.
- Log format không giống lúc kiểm thử.

### 16.1. Ưu tiên allowlist logging

Thay vì:

```java
log.warn("Redis call failed: {}", requestObject);
```

dùng:

```java
log.warn(
        "Redis call failed operation={} category={}",
        "profile_cache_read",
        RedisFailureCategory.SERIALIZATION
);
```

Danh sách field được phép giúp đơn giản hóa đánh giá bảo mật và tuân thủ retention.

### 16.2. Nếu buộc phải log một phần dữ liệu

Cần định nghĩa cụ thể:

- Mục đích chẩn đoán nào đòi hỏi field đó?
- Field có nằm trong dữ liệu cá nhân/bí mật không?
- Có thể dùng alias, bucket hoặc fingerprint không?
- Ai có quyền đọc log?
- Log được giữ trong bao lâu?
- Có giới hạn độ dài và encoding không?
- Có kế hoạch xóa hoặc giảm độ chi tiết sau khi khắc phục không?

Không nên xuất toàn bộ payload chỉ để tiết kiệm thời gian điều tra một lỗi hiếm.

## 17. Bảo vệ metric và tracing khỏi dữ liệu nhạy cảm

Việc không log secret vào SLF4J chưa đủ nếu cùng dữ liệu được đưa vào metric hoặc tracing.

### 17.1. Metric labels phải có cardinality hữu hạn

Tốt:

```text
redis_operation_failures_total{
  operation="product_cache_read",
  category="TIMEOUT",
  component="catalog"
}
```

Không tốt:

```text
redis_operation_failures_total{
  key="user:lan@example.com:profile",
  exception_message="GET ...",
  request_id="uuid-mỗi-request"
}
```

Các nhãn như full Redis key hoặc request ID vừa có nguy cơ lộ dữ liệu vừa tạo **cardinality explosion** gây tốn RAM và storage của hệ thống metric.

### 17.2. Trace spans

Có thể ghi các span attributes:

```text
db.system=redis
db.operation.name=GET
app.redis.operation=product_cache_read
error.type=TIMEOUT
```

Cần kiểm soát:

- Raw statement/command arguments.
- Full key và value.
- Exception event có tự ghi message và stack trace không.
- URL kết nối có credentials không.
- Trace baggage chứa thông tin cá nhân không.

Một số instrumentation mặc định có thể tự thêm exception message/stack trace. Vì vậy, chính sách an toàn cần bao gồm **tracing exporters**, không chỉ logger.

### 17.3. Correlation ID

Correlation ID giúp nối:

```text
HTTP request errorId
        |
        +--> redis operation metric
        |
        +--> database fallback span
        |
        +--> API response
```

Nên tạo ID ngẫu nhiên nội bộ hoặc dùng trace ID được hệ thống tracing cấp. Nếu nhận ID từ client, phải kiểm tra định dạng và độ dài trước khi dùng trong log. Không sử dụng access token của user làm correlation ID.

## 18. Quan sát sự cố Redis mà không cần log payload

Có thể kết hợp thông tin ứng dụng với các chỉ số Redis server.

### 18.1. Những số liệu hữu ích

| Metric | Câu hỏi |
|---|---|
| Client connection failures | Redis có mất kết nối không? |
| Command timeouts | Timeout tăng ở thời điểm nào? |
| Retry attempts | Retry có tạo thêm tải không? |
| Operation latency p95/p99 | Lỗi có đi cùng latency tăng? |
| Error category | Connection/timeout/serialization/command |
| Redis CPU/memory/network | Server có quá tải không? |
| Client pending commands | Lệnh có xếp hàng trong driver không? |
| Connection pool acquisition time | Có tranh chấp pool không? |
| Replica role/lag | Có sự cố topology hoặc replication không? |
| Schema/serializer version | Lỗi có gắn với phiên bản triển khai mới không? |

Các lệnh Redis phục vụ điều tra trên môi trường được cấp quyền:

```redis
INFO stats
INFO commandstats
INFO memory
INFO clients
SLOWLOG GET 10
LATENCY LATEST
```

**Thận trọng:** `SLOWLOG` có thể chứa tên command và arguments theo cơ chế Redis; nếu value chứa dữ liệu nhạy cảm, kết quả thu được cũng cần được xử lý như dữ liệu nhạy cảm. Không lấy toàn bộ slowlog rồi đẩy vào một nơi quan sát ít được bảo vệ.

Không bật `MONITOR` tùy tiện trên production: nó có thể gây áp lực hiệu năng và phơi bày commands/arguments.

### 18.2. Phân biệt client timeout và server execution time

Một API có thể timeout 800 ms dù Redis thực thi lệnh chỉ vài ms:

```text
Client queue / pool wait
       |
Network send
       |
Redis execution
       |
Network receive
       |
Deserialize
```

`SLOWLOG` chủ yếu phản ánh thời gian xử lý lệnh ở Redis, không tính toàn bộ thời gian client đợi. Do đó cần đo cả client-side latency và server-side metrics.

Không nên log raw command để chẩn đoán queue latency nếu các metric pending commands, pool wait và p99 đã đủ.

## 19. Một mẫu xử lý lỗi có thể áp dụng xuyên tầng

Một cấu trúc trách nhiệm rõ ràng:

```text
Redis client / serializer
         |
         | throws original exception
         v
Repository / Redis adapter
         |
         | classify error type
         | wrap with safe context + original cause
         v
Business service
         |
         +-- Nếu Redis chỉ là cache và lỗi được phép:
         |      fallback có giới hạn + safe metrics
         |
         +-- Nếu Redis là nguồn bắt buộc:
         |      propagate
         v
ControllerAdvice / reactive global error handler
         |
         | log 1 sự kiện an toàn
         | không raw key/value/message/stack
         v
HTTP response
         |
         | generic code + errorId
         v
Client
```

Mẫu này cân bằng:

- **Chẩn đoán:** cause chain được giữ qua mọi tầng.
- **Bảo mật:** chỉ log các trường hữu hạn/được phép.
- **Vận hành:** metric và error ID đủ để biết tần suất và vị trí.
- **Tính đúng đắn:** miss khác error; fallback và retry có điều kiện.
- **Độ tin cậy:** không tạo log storm hoặc che sự cố khi Redis down.

### 19.1. Phân công trách nhiệm

| Thành phần | Nên làm | Không nên làm |
|---|---|---|
| Redis adapter | Wrap cause, gắn operation/category | In full key/value hoặc nuốt lỗi |
| Service | Quyết định fallback/retry theo nghiệp vụ | Retry mù quáng mọi ghi |
| Global error handler | Chuẩn hóa mã lỗi, log an toàn một lần | Trả `ex.getMessage()` cho client |
| Metrics | Đếm theo nhóm lỗi hữu hạn | Dùng key/userId/message làm label |
| Tracing | Liên kết request và dependency | Gửi raw Redis statements/secret |
| Log collector | Retention, access control, redaction bổ sung | Là biện pháp bảo vệ duy nhất |
| SRE/Operations | Điều tra bằng số liệu và kênh an toàn | Bật MONITOR/raw command log vô thời hạn |

## 20. Những lỗi thiết kế thường gặp

### Lỗi 1: Bỏ cause khi bọc exception

```java
throw new RuntimeException("Cache failed");
```

Nguyên nhân thật biến mất. Dùng constructor có `cause`:

```java
throw new CacheAccessException(
        "cache_read",
        RedisFailureCategory.OTHER_REDIS_ERROR,
        ex
);
```

### Lỗi 2: Gộp message gốc vào wrapper

```java
throw new RuntimeException("Failed: " + ex.getMessage(), ex);
```

Dù cause vẫn còn, wrapper message có thể lộ chi tiết Redis. Dùng message an toàn.

### Lỗi 3: Log full key và value khi có lỗi

Key có thể chứa token hoặc user ID; value có thể chứa dữ liệu cá nhân. Ưu tiên namespace/operation cố định.

### Lỗi 4: Log full throwable theo mặc định

```java
log.error("Redis error", ex);
```

Có thể in các message nhạy cảm. Chỉ sử dụng trong kênh được kiểm soát nếu đã đánh giá dữ liệu của driver/serializer.

### Lỗi 5: Biến mọi lỗi thành null

```java
catch (Exception ex) {
    return null;
}
```

Che timeout, auth failure, `WRONGTYPE`, serializer mismatch. Cache miss cần được phân biệt với lỗi.

### Lỗi 6: Ghi cùng lỗi ở mọi tầng

Tạo nhiều dòng và log storm, khó đếm sự cố. Chọn ranh giới log rõ ràng.

### Lỗi 7: Trả exception message ra API

Có thể tiết lộ địa chỉ Redis, key hoặc lệnh. Trả mã lỗi và correlation ID.

### Lỗi 8: Lưu secret trong exception custom fields

Một exception có thể được log tự động ở nơi khác. Không gắn raw payload, password hay token vào `getMessage()`/`toString()` của wrapper.

### Lỗi 9: Dùng exception message làm metric label

Tạo cardinality không giới hạn và có thể lộ dữ liệu. Phân nhóm bằng enum.

### Lỗi 10: Xem Redis timeout là lệnh chưa chạy

Một lệnh ghi có thể đã chạy nhưng response bị mất; retry không idempotent có thể nhân đôi tác dụng.

### Lỗi 11: Fallback cả lỗi serialization

Lỗi schema đáng ra cần được điều tra nhưng bị coi thành cache miss. Chỉ fallback đúng nhóm lỗi được phép.

### Lỗi 12: Tự log nội dung message từ Pub/Sub/Stream

Payload có thể chứa dữ liệu cá nhân hoặc token. Ghi loại sự kiện và mã lỗi được kiểm soát.

### Lỗi 13: Dùng redaction regex làm bảo vệ duy nhất

Dữ liệu có thể ở dạng nested JSON, escaped, binary hoặc nằm trong cause chain. Giảm thông tin ngay tại nơi tạo log.

### Lỗi 14: Không xét tracing auto-instrumentation

Trace exporter có thể tự thu exception message hoặc statement. Phải có chính sách ở tracing tương tự logging.

### Lỗi 15: Cho phép client tùy ý đặt request ID dùng trong log

Header quá dài hoặc chứa ký tự bất thường có thể làm log khó xử lý hoặc gây injection. Kiểm tra định dạng/độ dài hoặc dùng ID do server tạo.

### Lỗi 16: Log kết nối Redis dạng URI đầy đủ

URI có thể chứa credentials. Ghi role/alias đã được kiểm soát thay vì username/password.

### Lỗi 17: Log toàn bộ SLOWLOG/MONITOR output

Các công cụ này có thể chứa tham số lệnh. Chỉ sử dụng với quyền phù hợp và dữ liệu đã được giới hạn.

### Lỗi 18: Không ghi nhận fallback thành công

API trả 200 nhưng Redis đang down hàng giờ. Cần metric fallback và cảnh báo, không chỉ log lỗi request thất bại.

### Lỗi 19: Chỉ dựa vào tên exception ngoài cause

Các lớp wrapper có thể che nguyên nhân thấp hơn. Giữ cause chain và phân loại theo contract của thư viện.

### Lỗi 20: Tắt mọi thông tin chẩn đoán để tránh rò rỉ

Không cần chọn giữa “in toàn bộ dữ liệu” và “không có log”. Operation, category, exception class, error ID, duration và retry count có thể cung cấp tín hiệu mạnh mà ít lộ thông tin.

## 21. Bài tập thực hành

### Bài tập A: Bảo toàn cause

Tạo một exception gốc:

```java
RuntimeException original =
        new RuntimeException("secret-value-from-driver");
```

Bọc theo cách đúng:

```java
CacheAccessException wrapped = new CacheAccessException(
        "product_cache_read",
        RedisFailureCategory.OTHER_REDIS_ERROR,
        original
);
```

Kiểm tra bằng một bài unit test hoặc trình debug:

```java
assertSame(original, wrapped.getCause());
```

Sau đó so sánh với `new RuntimeException("Redis error")` và quan sát exception mới không còn liên kết tới original.

**Điểm cần nhớ:** tạo wrapper message an toàn và truyền cause như tham số riêng.

### Bài tập B: Log nội dung nhạy cảm

Giả sử Redis key có chứa một session token thử nghiệm:

```text
session:demo-secret-token-123
```

Thử so sánh hai thiết kế **trong môi trường test**:

```java
log.warn("Redis key {} failed", key);
```

và:

```java
log.warn(
        "Redis failed operation={} category={}",
        "session_lookup",
        RedisFailureCategory.CONNECTION
);
```

Xác định dòng nào làm rò rỉ token và vì sao. Không sử dụng token thật.

### Bài tập C: Phân biệt miss và error

Giả lập ba tình huống:

1. Redis trả `null` vì key không tồn tại.
2. Redis throw `RedisConnectionFailureException`.
3. Serializer throw `SerializationException`.

Kỳ vọng:

```text
Case 1 -> cache miss hợp lệ.
Case 2 -> lỗi kết nối, giữ cause.
Case 3 -> lỗi serialization, giữ cause.
```

Không được gộp cả ba thành `Optional.empty()`.

### Bài tập D: HTTP error response

Tạo `CacheAccessException` với cause có message giả chứa thông tin mật. Gọi handler và kiểm tra:

- HTTP response không chứa message của cause.
- Log chỉ chứa operation/category/exception type/error ID.
- `wrapped.getCause()` vẫn trỏ về exception gốc.
- Không có raw key/value trong nội dung ghi log.

### Bài tập E: Fallback hai nguồn

Giả lập:

```text
Redis connection error
        |
        v
Database fallback error
```

Dùng `CacheFallbackException` với database failure làm cause và Redis failure làm suppressed. Xác định cả hai lỗi đều còn trong object exception nhưng response/log chỉ dùng field an toàn.

### Bài tập F: Reactive error signal

Với một `Mono.error(original)` giả lập, dùng `onErrorMap` để bọc với cause và kiểm tra subscriber nhận đúng `CacheAccessException`.

So sánh với:

```java
.onErrorResume(ex -> Mono.empty())
```

và giải thích vì sao cách thứ hai che giấu lỗi Redis.

### Bài tập G: Log storm khi outage

Giả lập Redis mất kết nối khiến 1.000 request lỗi trong cùng khoảng thời gian. Thiết kế:

- Metric counter ghi đủ số lỗi theo category.
- Log sampling/rate limit phù hợp để không phát 1.000 full stack traces.
- Một alert theo tỷ lệ lỗi và latency.
- Một error ID cho từng request thất bại nếu cần liên hệ API.
- Không ghi full key/value ngay cả khi bật chế độ debug.

Lưu ý log sampling **không làm thay đổi độ chính xác của metric counter** nếu metric được thu tại đúng vị trí.

## 22. Câu hỏi tự kiểm tra

**1. Vì sao `throw new RuntimeException(ex.getMessage())` là sai khi muốn giữ nguyên nguyên nhân lỗi?**

Vì exception mới không liên kết với original cause. Đồng thời, message gốc có thể chứa dữ liệu nhạy cảm.

**2. Có phải gọi `log.error("Redis failed", ex)` luôn an toàn nếu không log key trực tiếp?**

Không. Exception message và stack trace có thể chứa thông tin nhạy cảm do driver hoặc serializer đưa vào.

**3. Cách bọc exception nào giữ được cause?**

Constructor nhận `Throwable cause`, ví dụ `new CacheAccessException("cache_read", category, ex)`.

**4. GET trả `null` có giống Redis timeout không?**

Không. `null` thường biểu thị key không tồn tại; timeout là lỗi cần phân loại riêng.

**5. Những field nào có thể hữu ích để log mà không cần payload?**

Operation từ allowlist, error category, exception class, root-cause class, duration, retry attempt và error ID nội bộ.

**6. Vì sao không nên dùng raw key trong metric label?**

Key có thể chứa dữ liệu nhạy cảm và mỗi key có giá trị khác nhau, tạo cardinality lớn.

**7. Lỗi serializer có nên tự động fallback như cache miss không?**

Không mặc định. Nó có thể phản ánh schema sai hoặc dữ liệu không tương thích; cần xử lý có chủ đích.

**8. Retry `INCR` sau timeout có chắc an toàn không?**

Không. Redis có thể đã tăng counter trước khi client nhận timeout, làm retry tăng lần hai.

**9. Nếu fallback database cũng thất bại, có thể giữ cả hai lỗi không?**

Có. Dùng exception cause cho lỗi chính và `addSuppressed` hoặc cấu trúc lỗi rõ ràng để giữ lỗi Redis liên quan, nhưng không in raw message ra log.

**10. Vì sao chỉ dùng regex redaction ở collector chưa đủ?**

Vì dữ liệu có nhiều format, nested structure và exception message bất ngờ. Cần kiểm soát dữ liệu ngay tại điểm tạo log.

**11. Với WebFlux, dùng MDC ThreadLocal có luôn giữ trace ID qua mọi operator không?**

Không. Cần cơ chế context propagation phù hợp hoặc Reactor Context, đồng thời không để secret vào baggage.

**12. Có thể chỉ log mỗi error ID mà không giữ cause không?**

Không nên. Error ID hỗ trợ tương quan nhưng nếu nguyên nhân bị mất ngay khi wrap, hệ thống khó phân loại và điều tra sâu.

**13. Với Redis Streams, một lỗi xử lý có nên vừa log payload vừa `XACK` cho xong không?**

Không. Payload có thể nhạy cảm; ACK chỉ khi tác vụ đã hoàn tất hoặc đã được xử lý theo chính sách lỗi bền vững.

**14. Nếu API trả 200 nhờ fallback, có còn phải ghi nhận lỗi Redis không?**

Có. Ghi metric/log an toàn ở mức phù hợp để phát hiện Redis đang gặp sự cố dù API vẫn phục vụ được.

**15. Vì sao exception class và root-cause class vẫn chưa đủ để kết luận Redis server bị lỗi?**

Vì timeout hoặc lỗi I/O có thể xuất phát từ mạng, client queue, pool hoặc failover; cần kết hợp telemetry ở cả client và server.

## 23. Ghi nhớ

- **Giữ nguyên nguyên nhân lỗi bằng `cause` hoặc `suppressed`**, không thay bằng text `ex.getMessage()`.
- **Không mặc định log raw throwable an toàn**: message và stack trace có thể chứa Redis key, value, command, URI hoặc dữ liệu nhạy cảm.
- **Phân loại lỗi bằng type/category**, ghi log với operation từ allowlist, exception class, root-cause class, duration và error ID.
- **Cache miss không phải Redis error**. Không nuốt timeout hoặc serialization exception thành `null`/`Mono.empty()` khi chưa có chính sách.
- **Chỉ fallback cho lỗi phù hợp**, có giới hạn tải; nếu fallback cũng lỗi, giữ cả hai nguyên nhân mà không đưa thông tin mật ra response.
- **Reactive `onErrorMap` phải giữ original cause**; `onErrorResume`/`onErrorComplete` có thể che sự cố nếu dùng không cẩn thận.
- **Retry và timeout không chứng minh lệnh ghi chưa chạy**; cần cân nhắc idempotency với `INCR`, `XADD`, Lua và các thao tác khác.
- **Logging, metrics và tracing đều cần kiểm soát dữ liệu**. Không sử dụng raw Redis key hoặc exception message làm metric label/trace attribute.
- **Giảm dữ liệu tại nguồn, log một lần ở boundary**, kết hợp metric/sampling để tránh log storm.
- **HTTP response chỉ nên chứa mã lỗi và error ID an toàn**, không phát tán details nội bộ của Redis.

### Tài liệu tham khảo

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html).
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html).
- [Spring Framework — DataAccessException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataAccessException.html).
- [Spring Data Redis — RedisConnectionFailureException](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/RedisConnectionFailureException.html).
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- [OWASP — Sensitive Data Exposure](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).
- [Redis — SLOWLOG](https://redis.io/docs/latest/commands/slowlog/).
- [Redis — INFO](https://redis.io/docs/latest/commands/info/).

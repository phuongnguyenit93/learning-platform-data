# Retry có giới hạn, khoảng lùi và điều kiện lỗi được phép thử lại

Trong Spring Data Relational R2DBC, truy vấn và thao tác ghi được thực thi bất đồng bộ qua `Mono` hoặc `Flux`. Một số lỗi chỉ mang tính tạm thời, chẳng hạn kết nối database bị gián đoạn trong thời gian ngắn, pool chưa cấp được connection hoặc database từ chối transaction do xung đột đồng thời. Với những lỗi phù hợp, ứng dụng có thể đăng ký lại publisher để thử thực hiện thao tác một lần nữa.

Retry không nên được áp dụng cho mọi exception. Lỗi cú pháp SQL, sai kiểu dữ liệu, vi phạm constraint, thiếu quyền hoặc dữ liệu đầu vào không hợp lệ thường không tự biến mất sau một khoảng chờ. Thử lại các lỗi này chỉ lặp cùng một thất bại và tạo tải thừa. Một chính sách retry tốt cần có số lần thử lại tối đa, khoảng lùi giữa các lần thử, điều kiện xác định lỗi được phép retry và giới hạn tổng thời gian.

Trong Reactor, API `Retry` kết hợp với `retryWhen` cho phép biểu diễn các quy tắc đó. Khi dùng với R2DBC, còn phải chú ý transaction boundary và tính idempotent: retry một thao tác ghi có thể chạy lại SQL sau khi database đã thực thi thành công nhưng client chưa nhận được phản hồi.

## 1. Retry trong reactive pipeline nghĩa là gì?

Retry là đăng ký lại publisher nguồn sau khi publisher phát `onError`. Reactor không tiếp tục từ đúng câu lệnh bị lỗi; nó subscribe lại upstream theo cách publisher đó được xây dựng.

Ví dụ:

```java
Mono<Customer> customer = customerRepository.findById(42L)
        .retry(2);
```

Nếu truy vấn lỗi, Reactor có thể subscribe lại source tối đa hai lần. Với một publisher cold của Spring Data R2DBC, mỗi subscription thường thực hiện lại thao tác database. Nếu source hoàn tất bình thường, kể cả complete rỗng, retry không kích hoạt.

Với `retry(2)`, con số `2` là số lần đăng ký lại sau lần đầu, không phải tổng số lần thực hiện. Tối đa có ba lần thực thi: lần đầu và hai lần retry.

### Retry không xử lý empty completion

Một repository `findById` không tìm thấy hàng thường trả `Mono.empty()`. Đây là complete bình thường, không phải lỗi. Vì vậy:

```java
customerRepository.findById(id)
        .retry(3);
```

không truy vấn lại chỉ vì không tìm thấy customer. Nếu cần hành động khi dữ liệu không tồn tại, dùng `switchIfEmpty`. Retry dành cho tín hiệu lỗi được phân loại là có thể phục hồi.

### Retry không tự tạo transaction mới

`retryWhen` đăng ký lại publisher upstream. Việc có transaction mới cho mỗi lần thử hay không phụ thuộc vị trí retry so với transaction boundary. Đây là điểm đặc biệt quan trọng với R2DBC và được trình bày ở phần transaction bên dưới.

## 2. Phân biệt lỗi tạm thời và lỗi không thể phục hồi

Không có một danh sách lỗi retry phù hợp cho mọi database. Cần dựa trên loại exception được driver phát ra, exception translation của Spring và semantics của database.

Các nhóm thường gặp:

| Nhóm lỗi | Ví dụ | Có nên retry? |
| --- | --- | --- |
| Lỗi tài nguyên tạm thời | Connection tạm thời không khả dụng, resource bị gián đoạn | Có thể, nếu giới hạn thời gian và số lần |
| Timeout tạm thời | Query timeout do quá tải ngắn hạn hoặc kết nối chậm | Có thể, nếu retry còn nằm trong deadline nghiệp vụ |
| Xung đột transaction | Deadlock hoặc serialization conflict | Có thể, thường cần chạy lại toàn bộ transaction |
| Mất kết nối | Connection reset, database failover | Có thể, nhưng kết quả của thao tác ghi có thể chưa rõ |
| Lỗi cú pháp SQL | Sai tên bảng/cột, SQL không hợp lệ | Không |
| Lỗi dữ liệu | Sai kiểu, giá trị vượt giới hạn, JSON không hợp lệ | Không |
| Vi phạm constraint | Duplicate key, foreign key, check constraint | Thường không; xử lý theo nghiệp vụ |
| Lỗi xác thực/phân quyền | Sai thông tin đăng nhập, thiếu quyền | Không, trừ khi có quy trình phục hồi credential riêng |
| Không tìm thấy hàng | `Mono.empty()` hoặc update count bằng 0 | Không phải lỗi retry mặc định |

### Các kiểu exception có thể dùng để phân loại

R2DBC SPI định nghĩa nhóm exception, trong đó có:

- `R2dbcTransientException`: lỗi được phân loại là tạm thời.
- `R2dbcTransientResourceException`: lỗi tài nguyên tạm thời, là một loại transient exception.
- `R2dbcTimeoutException`: lỗi timeout được driver biểu diễn theo SPI.
- `R2dbcNonTransientException`: lỗi không được phân loại là tạm thời.

Spring cũng có hệ exception ở tầng DAO, ví dụ `TransientDataAccessException` cho nhóm lỗi truy cập dữ liệu có thể tạm thời. Việc exception được dịch sang loại Spring nào phụ thuộc translator, driver và phiên bản. Một số driver có thể bọc exception gốc trong cause chain.

Không nên chỉ kiểm tra tên class bằng chuỗi hoặc bắt mọi `DataAccessException`. Hãy kiểm tra exception thực tế trong môi trường của ứng dụng, sau đó viết predicate retry theo các loại lỗi được xác nhận.

## 3. Retry có giới hạn bằng `Retry.max`

Reactor cung cấp `Retry.max(maxAttempts)` để thử lại tối đa một số lần, không thêm khoảng chờ có chủ đích:

```java
Mono<Customer> result = customerRepository.findById(id)
        .retryWhen(Retry.max(2));
```

`Retry.max(2)` cho phép tối đa hai lần retry sau lần đầu. Đây là cách ngắn gọn, nhưng các lần thử có thể diễn ra liên tiếp. Khi database đang quá tải hoặc vừa mất kết nối, retry tức thì có thể làm tăng tải và tạo vòng lặp áp lực.

Có thể dùng `Retry.fixedDelay` nếu muốn khoảng chờ cố định:

```java
Mono<Customer> result = customerRepository.findById(id)
        .retryWhen(Retry.fixedDelay(
                3,
                Duration.ofMillis(250)
        ));
```

Ví dụ này cho phép ba lần retry, mỗi lần cách nhau khoảng 250 ms. Với lỗi kéo dài hoặc nhiều request cùng thất bại, exponential backoff thường phù hợp hơn.

## 4. Exponential backoff

Exponential backoff tăng khoảng chờ sau mỗi lần retry. Reactor cung cấp `Retry.backoff(maxAttempts, minBackoff)`:

```java
Mono<Customer> result = customerRepository.findById(id)
        .retryWhen(Retry.backoff(
                3,
                Duration.ofMillis(100)
        ));
```

Khoảng chờ tăng dần theo số lần retry, bắt đầu từ mức tối thiểu đã cấu hình. Chính sách có thể đặt giới hạn trên:

```java
Retry retryPolicy = Retry.backoff(
            4,
            Duration.ofMillis(100)
        )
        .maxBackoff(Duration.ofSeconds(2));
```

Backoff giúp database có thời gian phục hồi thay vì nhận nhiều lần thử liên tiếp. Tuy nhiên, không nên để khoảng chờ tăng vô hạn. `maxBackoff` giới hạn thời gian chờ tối đa giữa các lần retry.

### Jitter tránh nhiều client retry cùng lúc

Nếu hàng nghìn request gặp cùng một sự cố và đều retry sau đúng 100 ms, chúng có thể đồng loạt gửi lại tại cùng thời điểm. Hiện tượng này được gọi là *thundering herd*.

Jitter thêm độ biến thiên ngẫu nhiên vào khoảng chờ:

```java
Retry retryPolicy = Retry.backoff(
            4,
            Duration.ofMillis(100)
        )
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5);
```

`jitter(0.5)` cho phép Reactor biến thiên khoảng chờ quanh giá trị backoff theo cấu hình jitter. Các request vì vậy ít có khả năng retry đồng loạt. Hãy chọn mức jitter phù hợp với deadline và tải của hệ thống.

## 5. Chỉ retry những exception được cho phép

Một chính sách retry nên có predicate lọc lỗi. Ví dụ, chỉ retry các exception được xác định là transient:

```java
private boolean isRetryable(Throwable error) {
    for (Throwable cause = error;
         cause != null;
         cause = cause.getCause()) {

        if (cause instanceof R2dbcTransientException
                || cause instanceof TransientDataAccessException
                || cause instanceof TimeoutException) {
            return true;
        }
    }

    return false;
}
```

Các import liên quan:

```java
import io.r2dbc.spi.R2dbcTransientException;
import org.springframework.dao.TransientDataAccessException;

import java.util.concurrent.TimeoutException;
```

Đoạn code minh họa việc kiểm tra cause chain vì exception thực tế có thể được bọc qua nhiều lớp. Danh sách trên chỉ là điểm bắt đầu; hãy bổ sung hoặc loại bỏ loại lỗi dựa trên driver và exception translation mà ứng dụng đang dùng. Không phải mọi `TimeoutException` đều có thể retry an toàn, đặc biệt khi timeout xảy ra sau khi một lệnh ghi có thể đã được database thực thi.

Áp dụng predicate:

```java
Retry retryPolicy = Retry.backoff(
            3,
            Duration.ofMillis(150)
        )
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(this::isRetryable);

Mono<Customer> result = customerRepository.findById(id)
        .retryWhen(retryPolicy);
```

Nếu lỗi không vượt qua predicate, Reactor truyền lỗi đó xuống downstream ngay, không chờ và không thử lại.

### Không retry duplicate key một cách máy móc

Duplicate key thường biểu thị dữ liệu đã tồn tại hoặc có race condition. Retry cùng một `INSERT` với cùng khóa thường chỉ tạo cùng lỗi lần nữa. Thay vào đó, hãy chọn semantics rõ ràng: trả conflict, đọc lại bản ghi, dùng upsert hoặc xử lý idempotency key.

### Không retry lỗi validation và SQL grammar

Sai kiểu dữ liệu, sai cú pháp SQL, thiếu cột hoặc vi phạm constraint thường cần sửa code/dữ liệu. Retry không làm câu lệnh hợp lệ hơn.

## 6. Tạo một chính sách retry dùng lại

Nên gom cấu hình vào một method hoặc bean thay vì lặp lại nhiều con số trong service:

```java
@Configuration
public class RetryConfiguration {

    @Bean
    Retry r2dbcRetryPolicy() {
        return Retry.backoff(3, Duration.ofMillis(100))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(this::isRetryable)
                .doBeforeRetry(signal -> log.warn(
                        "Retry R2DBC attempt={}, cause={}",
                        signal.totalRetries() + 1,
                        signal.failure().getClass().getSimpleName()
                ));
    }

    private boolean isRetryable(Throwable error) {
        for (Throwable cause = error;
             cause != null;
             cause = cause.getCause()) {
            if (cause instanceof R2dbcTransientException
                    || cause instanceof TransientDataAccessException) {
                return true;
            }
        }
        return false;
    }
}
```

Đây là cấu hình minh họa. Cần khai báo logger và imports tương ứng trong dự án. Không ghi toàn bộ SQL, bind values, token hoặc dữ liệu nhạy cảm vào log retry. Loại exception và số lần retry thường đủ để điều tra ban đầu.

`Retry` là một strategy có thể tái sử dụng; không nên lưu trạng thái nghiệp vụ thay đổi của một request trong bean retry. Mỗi subscription có tín hiệu retry riêng.

## 7. Số lần thử: retry count khác total attempts

Reactor dùng tham số `maxAttempts` để chỉ số lần retry tối đa, không tính lần subscribe đầu tiên.

| Cấu hình | Lần chạy tối đa |
| --- | ---: |
| Không retry | 1 |
| `Retry.max(1)` | 2 |
| `Retry.max(2)` | 3 |
| `Retry.backoff(3, ...)` | 4 |

Nếu yêu cầu nghiệp vụ nói “thử tổng cộng tối đa 3 lần”, cấu hình retry tối đa thường là `2`, vì lần đầu đã là một lần thử. Hãy đặt tên biến và log rõ ràng để tránh nhầm lẫn.

`RetrySignal.totalRetries()` thường bắt đầu từ 0 cho lần retry đầu tiên. Nếu log số thứ tự retry cho người vận hành, cộng 1 để hiển thị lần retry đầu tiên là 1.

## 8. Ghi log và quan sát retry

Retry cần quan sát được. Nếu không có log/metric, hệ thống có thể đang thử lại liên tục mà người vận hành chỉ nhìn thấy latency tăng.

Reactor cung cấp hook như `doBeforeRetry` và `doAfterRetry` trên retry spec:

```java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(this::isRetryable)
        .doBeforeRetry(signal -> log.warn(
                "Database operation failed; retry={}, errorType={}",
                signal.totalRetries() + 1,
                signal.failure().getClass().getSimpleName()
        ));
```

Nên theo dõi:

- Số lần retry theo operation và loại exception.
- Số request cuối cùng thành công sau retry.
- Số request thất bại sau khi hết retry.
- Thời gian chờ backoff và tổng latency.
- Tỷ lệ timeout, connection failure, deadlock hoặc serialization conflict.
- Connection pool pending acquire và thời gian chờ connection.

Không đưa ID nhạy cảm, nội dung SQL có dữ liệu người dùng hoặc secret vào metric label; cardinality cao cũng có thể làm hệ thống metrics quá tải.

### `doOnError` đặt trước hay sau retry

Vị trí operator quyết định lỗi nào được quan sát:

```java
source
    .doOnError(error -> log.warn("Một lần thực thi source lỗi", error))
    .retryWhen(retryPolicy)
    .doOnError(error -> log.error("Cuối cùng vẫn thất bại", error));
```

`doOnError` trước `retryWhen` có thể quan sát từng lỗi của lần thực thi upstream. `doOnError` sau `retryWhen` quan sát lỗi cuối cùng đi xuống downstream, chẳng hạn lỗi không được retry hoặc lỗi sau khi đã hết số lần retry.

Không nên log stack trace đầy đủ ở mọi lần retry trong một outage lớn nếu điều đó tạo thêm áp lực I/O log. Có thể log gọn từng retry và ghi chi tiết ở lần thất bại cuối cùng.

## 9. Xử lý khi đã hết số lần retry

Khi retry exhaustion xảy ra, Reactor mặc định có thể phát `RetryExhaustedException` chứa nguyên nhân cuối cùng. Có thể cấu hình giữ nguyên lỗi cuối để tầng trên xử lý:

```java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(100))
        .filter(this::isRetryable)
        .onRetryExhaustedThrow((spec, signal) -> signal.failure());
```

Nếu muốn phát lỗi nghiệp vụ riêng, có thể ánh xạ sau retry:

```java
return repository.findById(id)
        .retryWhen(retryPolicy)
        .onErrorMap(this::isRetryable,
                error -> new CustomerStoreUnavailableException(error));
```

Chỉ ánh xạ lỗi retryable còn lại nếu đó là ý nghĩa mà service muốn công bố. Không biến mọi lỗi thành “database unavailable”, vì lỗi validation hoặc constraint cần giữ semantics khác.

Nếu cần giữ nguyên exception gốc, có thể dùng `onRetryExhaustedThrow` như ví dụ trước. Việc chọn giữ lỗi cuối hay bọc thành lỗi service nên nhất quán với API và observability.

## 10. Retry và timeout: giới hạn thời gian tổng thể

Giới hạn số lần retry không tự bảo đảm request hoàn tất trong thời gian chấp nhận được. Mỗi lần thử có thể kéo dài tới timeout của driver hoặc query, cộng thêm các khoảng backoff.

Có thể đặt timeout cho từng lần thực thi và timeout tổng cho cả chuỗi:

```java
Mono<Customer> result = Mono.defer(() ->
            customerRepository.findById(id)
        )
        .timeout(Duration.ofSeconds(2))
        .retryWhen(retryPolicy)
        .timeout(Duration.ofSeconds(7));
```

Trong ví dụ:

- Timeout 2 giây nằm trước `retryWhen`, nên giới hạn một lần subscribe vào source.
- `retryWhen` có thể đăng ký lại source sau lỗi timeout nếu predicate cho phép.
- Timeout 7 giây nằm sau `retryWhen`, nên giới hạn tổng thời gian của cả chuỗi retry.

Timeout tổng có thể hủy pipeline trong lúc đang chờ backoff hoặc đang thực thi một lần thử. Cancellation sẽ được truyền upstream; với transaction, cần bảo đảm transaction manager xử lý cleanup/rollback đúng.

Không nên đặt tổng timeout nhỏ hơn cả thời gian dự kiến của một lần thử và backoff rồi kỳ vọng đủ số lần retry. Hãy tính deadline dựa trên thời gian query, số lần retry, backoff và thời gian xử lý ở tầng ứng dụng.

### Retry budget

Một request HTTP thường có deadline từ gateway hoặc client. Retry phải nằm trong ngân sách thời gian còn lại. Ví dụ, nếu request chỉ còn 1 giây trước deadline nhưng backoff tiếp theo là 2 giây, retry đó không giúp người dùng và chỉ kéo dài tài nguyên bị chiếm giữ.

Có thể giới hạn `maxBackoff`, tổng timeout và số lần retry; với hệ thống phức tạp hơn, truyền deadline/cancellation budget xuyên qua service để các tầng không retry vượt ngân sách chung.

## 11. Retry có thể thực thi lại toàn bộ upstream

Đặt `retryWhen` ở đâu rất quan trọng. Reactor đăng ký lại phần upstream nằm trước operator retry. Vì vậy, mọi thao tác trong phần đó có thể chạy lại.

Ví dụ:

```java
return repository.findById(id)
        .flatMap(customer -> externalService.loadDetails(customer))
        .retryWhen(retryPolicy);
```

Nếu `externalService.loadDetails` lỗi và predicate cho phép retry, truy vấn repository cũng có thể chạy lại. Nếu chỉ muốn retry một thao tác cụ thể, đặt retry gần publisher đó:

```java
return repository.findById(id)
        .flatMap(customer ->
                externalService.loadDetails(customer)
                        .retryWhen(externalRetryPolicy)
        );
```

Tương tự, nếu một chuỗi gồm đọc, tính toán và ghi được bọc bởi retry, cả chuỗi có thể được chạy lại. Hãy xác định rõ ranh giới của thao tác có thể retry và side effect nào nằm trong upstream.

### `defer` giúp tạo lại thao tác cho mỗi lần thử

Khi cần tạo publisher mới cho mỗi subscription, có thể dùng `Mono.defer`:

```java
return Mono.defer(() -> customerRepository.findById(id))
        .retryWhen(retryPolicy);
```

Các publisher R2DBC thông dụng vốn đã lazy, nhưng `defer` hữu ích nếu cần gọi lại factory method, tạo statement hoặc đọc giá trị mới cho từng lần thử. Đảm bảo dữ liệu/command được tái tạo có chủ đích; không sinh một business identifier mới cho mỗi retry nếu thao tác cần giữ cùng idempotency key.

## 12. Retry thao tác đọc và thao tác ghi khác nhau

### Thao tác đọc

Đọc dữ liệu thường dễ retry hơn vì việc đọc lại không tạo thêm dữ liệu. Ví dụ:

```java
public Mono<Customer> getCustomer(Long id) {
    return Mono.defer(() -> customerRepository.findById(id))
            .retryWhen(readRetryPolicy);
}
```

Tuy vậy, kết quả đọc ở lần retry có thể khác nếu dữ liệu thay đổi giữa các lần thử. Nếu nghiệp vụ yêu cầu snapshot nhất quán, cần xem xét transaction/isolation và thời điểm thực hiện.

### Thao tác ghi

Retry ghi cần thận trọng hơn. Giả sử ứng dụng gửi `INSERT`, database commit thành công, nhưng kết nối bị ngắt trước khi client nhận phản hồi. Client thấy lỗi và không biết chắc hàng đã được tạo hay chưa. Retry cùng lệnh có thể tạo duplicate key.

Tương tự, retry một lệnh tăng số dư hoặc gửi một giao dịch có thể thực hiện tác dụng phụ hai lần nếu lần đầu đã commit.

Trước khi retry ghi, cần trả lời:

- Database có thể đã thực thi lệnh trước khi lỗi xuất hiện không?
- Gửi lại cùng lệnh có tạo thêm tác dụng phụ không?
- Có unique key hoặc idempotency key để nhận diện cùng một yêu cầu không?
- Có thể đọc lại trạng thái để xác định lần trước đã thành công không?
- Retry có nằm trong transaction mới cho mỗi lần thử không?

Không coi mọi lỗi connection là bằng chứng rằng database chưa ghi dữ liệu.

## 13. Idempotency bảo vệ thao tác ghi khi retry

Một thao tác idempotent có thể được thực hiện nhiều lần mà trạng thái cuối cùng vẫn giống thực hiện một lần, theo semantics nghiệp vụ.

Ví dụ cập nhật trạng thái thành một giá trị cố định:

```sql
UPDATE customer
SET status = 'ACTIVE'
WHERE id = 42;
```

Thực hiện lại cùng lệnh thường vẫn để trạng thái là `ACTIVE`, nên có tính idempotent ở mức dữ liệu đó. Ngược lại:

```sql
UPDATE account
SET balance = balance + 100
WHERE id = 42;
```

thực hiện hai lần sẽ cộng 200, không phải 100. Đây không phải thao tác idempotent.

### Dùng idempotency key

Với lệnh tạo giao dịch, có thể gắn một request key duy nhất và lưu nó cùng kết quả:

```sql
CREATE TABLE payment_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    amount DECIMAL(18, 2) NOT NULL,
    status VARCHAR(30) NOT NULL
);
```

Mỗi yêu cầu logic giữ nguyên cùng `idempotency_key` qua các lần retry. Database unique constraint ngăn cùng yêu cầu được tạo thành hai hàng. Khi gặp duplicate key, service có thể đọc bản ghi theo key và trả kết quả đã lưu nếu payload tương ứng.

Idempotency key cần được tạo một lần ở biên nhận request và giữ nguyên khi retry. Không tạo key mới bên trong `defer` nếu mỗi lần retry phải đại diện cho cùng một yêu cầu logic.

### Upsert và conflict handling

Một số database hỗ trợ upsert như PostgreSQL `INSERT ... ON CONFLICT`. Upsert có thể giúp thao tác create-or-update trở nên nguyên tử hơn so với read-then-insert. Tuy nhiên, semantics cập nhật khi conflict phải được thiết kế rõ; upsert không tự làm mọi side effect bên ngoài trở thành idempotent.

## 14. Retry và reactive transaction: tạo transaction mới cho mỗi lần thử

Đây là quy tắc quan trọng khi retry các thao tác ghi trong R2DBC.

Nếu retry được đặt bên trong một transaction đã mở, lần thử tiếp theo có thể vẫn chạy trong cùng transaction context. Sau lỗi SQL, database có thể đánh dấu transaction hiện tại là failed/aborted hoặc connection không còn ở trạng thái có thể tiếp tục. Chỉ subscribe lại statement trong transaction đã hỏng không tương đương bắt đầu một transaction sạch.

Với thao tác cần transaction, thường nên đặt ranh giới transaction **bên trong** publisher được retry, để mỗi subscription của retry tạo một transaction mới. Khi một lần thử lỗi, transaction của lần đó rollback và được cleanup trước lần thử tiếp theo.

### Dùng `TransactionalOperator`

```java
public Mono<Customer> updateCustomer(Long id, String name) {
    return Mono.defer(() ->
            transactionalOperator.transactional(
                    customerRepository.findById(id)
                            .switchIfEmpty(Mono.error(
                                    new CustomerNotFoundException(id)
                            ))
                            .flatMap(customer -> {
                                customer.setName(name);
                                return customerRepository.save(customer);
                            })
            )
    ).retryWhen(writeRetryPolicy);
}
```

`Mono.defer` tạo một publisher transaction cho mỗi lần subscription vào phần upstream. `retryWhen` nằm bên ngoài `TransactionalOperator`, vì vậy mỗi lần retry subscribe lại `defer`, bắt đầu một transaction mới. Khi một lần thử phát lỗi, transaction operator nhận lỗi và rollback trước khi retry policy cho phép thử tiếp.

Điều này vẫn chỉ an toàn nếu thao tác ghi có thể retry theo nghiệp vụ và lỗi được phân loại đúng. Tạo transaction mới không giải quyết được tình huống lần ghi trước đã commit nhưng phản hồi bị mất; idempotency vẫn cần thiết.

### Dùng một bean có method `@Transactional`

Một cách khác là tách thao tác transaction thành bean riêng:

```java
@Service
public class CustomerWriteTransaction {

    @Transactional
    public Mono<Customer> update(Long id, String name) {
        return customerRepository.findById(id)
                .switchIfEmpty(Mono.error(
                        new CustomerNotFoundException(id)
                ))
                .flatMap(customer -> {
                    customer.setName(name);
                    return customerRepository.save(customer);
                });
    }
}
```

Service bên ngoài áp dụng retry:

```java
public Mono<Customer> updateWithRetry(Long id, String name) {
    return Mono.defer(() -> transactionWorker.update(id, name))
            .retryWhen(writeRetryPolicy);
}
```

Lời gọi `transactionWorker.update(...)` đi qua Spring proxy. Mỗi lần `defer` gọi method proxy và publisher được subscribe, transaction interceptor có thể tạo transaction mới. Tránh gọi method `@Transactional` bằng self-invocation trong cùng object vì lời gọi nội bộ thường không đi qua proxy.

### Không đặt retry bên trong method transaction nếu cần transaction mới

Mẫu dễ gây nhầm:

```java
@Transactional
public Mono<Customer> updateWithRetry(Long id, String name) {
    return doUpdate(id, name)
            .retryWhen(writeRetryPolicy);
}
```

Ở đây retry operator nằm trong publisher được transaction interceptor bao quanh. Các lần subscribe lại upstream có thể vẫn nằm trong transaction context hiện tại, tùy cách transaction boundary và driver xử lý. Với lỗi làm transaction rollback/aborted, không nên dựa vào cách này để tạo transaction mới cho mỗi lần thử.

Nếu yêu cầu mỗi attempt là một transaction riêng, đặt transaction operator bên trong `defer` và retry bên ngoài, hoặc gọi một transactional bean qua proxy từ publisher được retry.

## 15. Retry lỗi deadlock và serialization conflict

Deadlock hoặc serialization conflict có thể xảy ra khi nhiều transaction cạnh tranh cùng dữ liệu. Database thường hủy một transaction để phá deadlock hoặc bảo vệ isolation. Một lần thử lại toàn bộ transaction có thể thành công khi lịch thực thi đã thay đổi.

Khi retry các lỗi này:

- Retry toàn bộ đơn vị transaction, không chỉ statement cuối cùng.
- Mở transaction mới cho mỗi lần thử.
- Giữ transaction ngắn để giảm thời gian giữ lock.
- Giữ thứ tự truy cập resource nhất quán giữa các transaction nếu có thể.
- Giới hạn số lần thử và thêm backoff/jitter.
- Không retry nếu thao tác có side effect ngoài database mà không có cơ chế idempotency/outbox.

Exception cụ thể và SQL state dùng để nhận diện deadlock/serialization phụ thuộc database. Hãy dùng exception class hoặc mã lỗi đã được xác minh trong driver hiện tại; đừng giả định mọi database dùng cùng mã.

## 16. Không retry mọi lỗi của một pipeline lớn

Giả sử pipeline gồm đọc database, gọi dịch vụ thanh toán và ghi audit:

```java
return customerRepository.findById(id)
        .flatMap(paymentService::charge)
        .flatMap(payment -> auditRepository.save(toAudit(payment)))
        .retryWhen(retryPolicy);
```

Retry ở cuối có thể chạy lại cả việc đọc, gọi thanh toán và ghi audit nếu bất kỳ upstream nào phát lỗi phù hợp predicate. Nếu payment provider đã thu tiền nhưng phản hồi bị timeout, retry có thể thu tiền lần nữa.

Nên đặt retry đúng phạm vi và dùng idempotency key cho dịch vụ ngoài:

```java
return customerRepository.findById(id)
        .flatMap(customer -> paymentService.charge(
                customer,
                requestId
        ).retryWhen(paymentRetryPolicy))
        .flatMap(payment -> auditRepository.save(toAudit(payment)));
```

Ngay cả khi retry chỉ bọc `paymentService.charge`, thao tác thanh toán vẫn cần idempotency key do provider hỗ trợ hoặc cơ chế tương đương. Với database write, transaction boundary cần được thiết kế riêng như phần trước.

## 17. Kết hợp `timeout`, `retryWhen` và cancellation

Một chính sách hoàn chỉnh thường kết hợp:

- Timeout cho một lần query/attempt.
- Retry có giới hạn và backoff.
- Timeout tổng cho request.

Ví dụ:

```java
Mono<Customer> result = Mono.defer(() ->
            customerRepository.findById(id)
        )
        .timeout(Duration.ofSeconds(2))
        .retryWhen(readRetryPolicy)
        .timeout(Duration.ofSeconds(6));
```

Timeout đầu giới hạn mỗi lần thực thi source. Timeout cuối giới hạn toàn bộ thời gian bao gồm các lần retry và backoff. Khi timeout tổng xảy ra, pipeline bị cancel; không có lý do để tiếp tục retry nếu request đã hết deadline.

Với ghi trong transaction, cancellation cần được truyền tới transaction manager để rollback/cleanup. Không nuốt cancellation hoặc tạo subscription tách rời khiến thao tác tiếp tục chạy sau khi caller đã ngừng chờ.

### Không nhầm timeout với bằng chứng thao tác chưa chạy

Timeout chỉ cho biết caller không nhận được kết quả đúng hạn. Nó không chứng minh database chưa thực thi câu lệnh. Một lệnh insert/update có thể đã commit nhưng phản hồi đến muộn hoặc bị mất. Vì vậy, timeout khi ghi phải được xem là kết quả không chắc chắn cho tới khi ứng dụng xác định trạng thái qua idempotency key hoặc truy vấn đối soát.

## 18. Retry và backpressure

`retryWhen` điều khiển việc đăng ký lại publisher khi có lỗi; nó không phải cơ chế điều tiết số lượng request đang chạy toàn hệ thống. Nếu nhiều request đồng thời cùng retry, tổng tải database vẫn có thể tăng đáng kể.

Các biện pháp cần kết hợp:

- Giới hạn số lần retry cho mỗi request.
- Dùng backoff và jitter.
- Giới hạn concurrency của luồng xử lý batch bằng `flatMap` có concurrency phù hợp hoặc `concatMap` khi cần tuần tự.
- Giới hạn thời gian chờ connection pool.
- Đặt timeout tổng và deadline ở tầng gọi.
- Theo dõi tỷ lệ retry để phát hiện sự cố trước khi tạo retry storm.
- Cân nhắc circuit breaker hoặc load shedding ở tầng phù hợp nếu hệ thống cần ngừng gọi một dependency đang lỗi kéo dài.

Không nên tăng concurrency để bù cho database đang quá tải. Retry và concurrency không đúng mức có thể làm pool cạn nhanh hơn.

## 19. Kiểm thử retry có giới hạn và backoff

Kiểm thử nên xác nhận số lần subscribe, loại lỗi được retry, thời gian chờ và lỗi cuối cùng.

### Thử lại khi lỗi transient rồi thành công

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> operation = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        return Mono.error(new R2dbcTransientException("temporary"));
    }
    return Mono.just("ok");
});

StepVerifier.create(operation.retryWhen(Retry.max(3)))
        .expectNext("ok")
        .verifyComplete();

assertThat(attempts).hasValue(3);
```

Publisher được tạo bằng `defer` để mỗi subscription tăng bộ đếm và mô phỏng một lần thực thi mới.

### Không retry lỗi không được phép

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> operation = Mono.defer(() -> {
    attempts.incrementAndGet();
    return Mono.error(new IllegalArgumentException("invalid input"));
});

StepVerifier.create(operation.retryWhen(
                Retry.max(3).filter(this::isRetryable)
        ))
        .expectError(IllegalArgumentException.class)
        .verify();

assertThat(attempts).hasValue(1);
```

Lỗi không khớp predicate được truyền xuống ngay, không có lần retry.

### Xác nhận giới hạn retry

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> operation = Mono.defer(() -> {
    attempts.incrementAndGet();
    return Mono.error(new R2dbcTransientException("still unavailable"));
});

StepVerifier.create(operation.retryWhen(Retry.max(2)))
        .expectError()
        .verify();

assertThat(attempts).hasValue(3);
```

Có một lần chạy ban đầu và hai lần retry.

### Kiểm thử backoff bằng virtual time

Không nên làm test chậm bằng cách chờ thật hàng trăm mili giây cho mỗi lần retry. Reactor Test hỗ trợ virtual time:

```java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            attempts.incrementAndGet();
            return Mono.<String>error(
                    new R2dbcTransientException("temporary")
            );
        }).retryWhen(Retry.backoff(
                2,
                Duration.ofSeconds(1)
        ).jitter(0))
)
        .thenAwait(Duration.ofSeconds(5))
        .expectError()
        .verify();

assertThat(attempts).hasValue(3);
```

Virtual time giúp kiểm thử scheduler-based delay nhanh và ổn định hơn. Với jitter, test có thể cố định jitter về 0 hoặc kiểm tra khoảng thời gian trong biên cho phép.

### Kiểm thử transaction mới cho từng attempt

Với thao tác ghi, cần integration test xác nhận mỗi lần retry có transaction mới và lần thất bại trước đã rollback. Có thể dùng một test service có `TransactionalOperator`, đếm số lần gọi work và quan sát dữ liệu cuối trong database. Mock repository không đủ để chứng minh connection/transaction được mở lại đúng cách.

## 20. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Query không tìm thấy vẫn không fallback retry | Empty completion không phải `onError` | Dùng `switchIfEmpty` cho dữ liệu thiếu |
| Lỗi validation bị thử lại nhiều lần | Predicate quá rộng hoặc dùng `retry()` không lọc | Chỉ retry exception transient đã xác nhận |
| Database bị quá tải nặng hơn | Retry tức thì hoặc nhiều request retry đồng loạt | Dùng backoff, jitter, giới hạn và theo dõi retry |
| Số lần thực thi nhiều hơn dự kiến | Nhầm `maxAttempts` là tổng số lần thử | Tính thêm lần subscribe ban đầu |
| Lệnh ghi tạo duplicate | Retry sau timeout dù lần đầu có thể đã commit | Idempotency key, unique constraint hoặc upsert |
| Retry trong transaction vẫn lỗi | Lần thử lại dùng transaction đã aborted | Đặt transaction boundary bên trong publisher được retry |
| Cả chuỗi side effect chạy lại | Retry đặt quá xa upstream | Thu hẹp phạm vi retry và bảo vệ side effect |
| Request vượt deadline | Không có timeout tổng hoặc backoff quá dài | Đặt timeout/budget tổng thể |
| Lỗi cuối bị che bởi retry exhaustion | Dùng exception mặc định mà không giữ cause rõ | Cấu hình `onRetryExhaustedThrow` hoặc ánh xạ lỗi có chủ đích |
| Không thấy từng lần retry trong log | Log đặt sau retry hoặc thiếu hook | Dùng `doBeforeRetry`; log lỗi cuối ở downstream |
| Retry không chạy với exception bọc | Predicate chỉ kiểm tra outer exception | Xem cause chain hoặc exception translation |
| Retry một timeout ghi gây tác dụng phụ hai lần | Timeout không chứng minh database chưa thực thi | Thiết kế idempotency và đối soát trạng thái |

## 21. Quy trình thiết kế retry cho R2DBC

Khi thêm retry cho một thao tác repository hoặc SQL, hãy thực hiện theo thứ tự:

1. Xác định lỗi thực tế từ driver/Spring và phân loại transient hay permanent.
2. Xác định thao tác là đọc hay ghi; kiểm tra side effect có an toàn khi chạy lại không.
3. Xác định chính xác upstream nào sẽ được subscribe lại khi retry đặt ở vị trí hiện tại.
4. Chọn số lần retry tối đa, backoff, max backoff và jitter.
5. Viết predicate chỉ cho phép các exception được xác nhận.
6. Đặt timeout cho từng attempt và timeout tổng phù hợp deadline.
7. Với ghi có transaction, bảo đảm mỗi attempt dùng transaction mới nếu lỗi có thể làm transaction hiện tại không thể tiếp tục.
8. Dùng unique constraint/idempotency key/upsert cho thao tác ghi có thể được gửi lại sau kết quả không chắc chắn.
9. Ghi log/metric cho từng retry và lỗi cuối, không để lộ dữ liệu nhạy cảm.
10. Kiểm thử transient success, permanent failure, exhaustion, backoff, timeout, cancellation và transaction rollback bằng driver/database thật.

## 22. Ghi nhớ

- Retry là subscribe lại publisher upstream sau `onError`; nó không kích hoạt với empty completion.
- `Retry.max(n)` và `Retry.backoff(n, ...)` dùng `n` làm số lần retry tối đa sau lần chạy đầu.
- Exponential backoff giúp giảm áp lực khi dependency đang phục hồi; `maxBackoff` giới hạn thời gian chờ.
- Jitter phân tán thời điểm retry, giảm nguy cơ nhiều request cùng gửi lại đồng loạt.
- Dùng `.filter(...)` để chỉ retry lỗi transient đã xác nhận; không retry SQL grammar, validation, constraint hoặc authorization một cách máy móc.
- Kiểm tra cause chain và exception translation của driver/Spring; loại exception thực tế phụ thuộc database và phiên bản.
- `retryWhen` có thể chạy lại toàn bộ upstream; đặt nó đúng phạm vi và đánh giá mọi side effect có thể lặp.
- Retry thao tác ghi cần idempotency vì timeout/mất kết nối không chứng minh database chưa commit.
- Với thao tác cần transaction, đặt transaction boundary bên trong publisher được retry để mỗi attempt có thể mở transaction mới.
- Timeout từng attempt và timeout tổng có mục đích khác nhau; retry phải nằm trong deadline nghiệp vụ.
- Theo dõi số lần retry, loại lỗi, latency, exhaustion và connection pool để phát hiện retry storm.
- Kiểm thử backoff bằng virtual time và kiểm thử transaction/idempotency bằng database/driver thật.

Một chính sách retry tốt cho R2DBC không chỉ là thêm `retryWhen`. Nó cần xác định lỗi nào có thể phục hồi, thao tác nào an toàn khi chạy lại, mỗi lần thử có transaction phù hợp hay không và tổng thời gian có còn nằm trong deadline. Giới hạn retry, backoff, jitter và idempotency giúp hệ thống phục hồi có kiểm soát thay vì khuếch đại sự cố database.

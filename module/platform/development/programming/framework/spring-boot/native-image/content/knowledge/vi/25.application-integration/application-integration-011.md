# Kiểm thử đường đi ít gặp như lỗi dữ liệu, retry và khôi phục kết nối

## 1. Vì sao phải kiểm thử đường đi lỗi?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng Spring AOT rồi biên dịch thành GraalVM Native Image. Một luồng nghiệp vụ có thể chạy tốt khi mọi dịch vụ đều khỏe, nhưng thất bại khi response bị cắt giữa chừng, database restart, kết nối cũ trong pool đã hết hạn hoặc message được gửi lại sau timeout.

Các tình huống này thường ít xuất hiện trong happy-path test. Chúng lại quyết định độ tin cậy của ứng dụng khi triển khai thật. Native executable còn có những điểm cần xác nhận riêng: DNS/TLS, truststore, native library, connection pool, thời điểm tạo client và khả năng khởi tạo lại tài nguyên sau khi kết nối bị mất.

Bài học này tập trung vào cách xác định lỗi nào có thể phục hồi, cách retry mà không nhân đôi tác động nghiệp vụ, cách tái lập kết nối và cách kiểm tra cùng một hành vi trên JVM lẫn native executable.

Một nguyên tắc xuyên suốt: **chỉ retry thao tác có khả năng thành công khi thử lại, và chỉ khi việc thử lại không tạo tác động nghiệp vụ trùng lặp**.

## 2. Phân loại lỗi trước khi thiết kế retry

Không phải lỗi nào cũng nên retry. Trước hết hãy phân biệt lỗi do dữ liệu/request, lỗi cấu hình/quyền, lỗi tạm thời của hạ tầng và lỗi không rõ kết quả.

| Nhóm lỗi | Ví dụ | Retry? | Hướng xử lý |
| --- | --- | --- | --- |
| Dữ liệu không hợp lệ | JSON sai schema, thiếu field bắt buộc, mã tiền tệ không hợp lệ | Không | Trả lỗi validation rõ ràng, không gọi hệ thống phụ thuộc |
| Vi phạm nghiệp vụ | Số dư không đủ, trạng thái đơn hàng không cho phép | Không | Trả lỗi domain và yêu cầu luồng nghiệp vụ phù hợp |
| Xác thực/phân quyền | HTTP 401/403, credential hết hạn hoặc thiếu quyền | Thường không retry mù | Refresh credential nếu có quy trình rõ; nếu không thì fail fast |
| Lỗi cấu hình | Host sai, port sai, certificate không tin cậy | Không retry liên tục | Sửa cấu hình, truststore hoặc deployment |
| Lỗi tạm thời | Timeout, connection reset, HTTP 503, database failover | Có điều kiện | Retry có giới hạn, backoff và idempotency |
| Rate limit | HTTP 429 hoặc quota tạm thời | Có điều kiện | Tôn trọng Retry-After, giới hạn retry và tải |
| Kết quả không xác định | Client timeout sau khi server có thể đã commit | Chỉ khi thao tác idempotent | Tra cứu trạng thái hoặc gửi lại cùng idempotency key |
| Lỗi lập trình | NullPointerException, invariant bị phá | Không | Sửa code; retry chỉ làm lỗi lặp lại |

Phân loại dựa trên exception type, HTTP status, SQLState/vendor code và ngữ cảnh thao tác. Không dùng một rule chung như “mọi RuntimeException đều retry” hoặc “mọi HTTP 5xx đều retry”. Một số lỗi 5xx có thể là lỗi xác định, còn một số 4xx như 429 có thể là giới hạn tạm thời.

### 2.1. Transient không đồng nghĩa với an toàn để retry

Một timeout có thể chỉ ra rằng client không nhận được response trong thời gian cho phép. Nó không chứng minh server chưa thực hiện thao tác.

Ví dụ:

1. Client gửi yêu cầu tạo thanh toán.
2. Server ghi nhận thanh toán thành công.
3. Response bị mất trên mạng.
4. Client timeout và gửi lại yêu cầu.
5. Nếu server không nhận diện request trùng, khách hàng có thể bị trừ tiền hai lần.

Do đó, quyết định retry phải xét cả **khả năng lỗi tạm thời** và **tính lặp an toàn của thao tác**.

## 3. Xử lý lỗi dữ liệu ở ranh giới tích hợp

### 3.1. Kiểm tra cấu trúc trước khi gọi dịch vụ ngoài

Một request cần được xác thực trước khi tạo side effect:

~~~java
public record CreateTransferRequest(
    @NotBlank String sourceAccount,
    @NotBlank String destinationAccount,
    @NotNull @Positive BigDecimal amount,
    @NotBlank String currency,
    @NotBlank String idempotencyKey
) {
}
~~~

Ngoài Bean Validation, domain layer cần kiểm tra quy tắc như hai tài khoản không được trùng, currency được hỗ trợ và số tiền nằm trong giới hạn nghiệp vụ. Không dựa hoàn toàn vào validation ở controller vì message consumer, batch job hoặc internal caller có thể gọi service trực tiếp.

Thứ tự xử lý nên rõ ràng:

1. Parse và kiểm tra cấu trúc input.
2. Xác thực invariant và quyền nghiệp vụ.
3. Chuẩn hóa dữ liệu theo hợp đồng.
4. Tạo idempotency record hoặc transaction cần thiết.
5. Gọi dịch vụ ngoài.
6. Lưu kết quả và trả response.

Request không hợp lệ phải bị từ chối trước khi gọi provider, ghi giao dịch hoặc phát message.

### 3.2. Response sai hoặc thiếu dữ liệu

Không giả định hệ thống ngoài luôn trả payload đúng schema. Các trường hợp cần kiểm tra:

- response rỗng khi hợp đồng yêu cầu body;
- JSON hợp lệ về cú pháp nhưng thiếu field bắt buộc;
- enum mới mà client chưa biết;
- số thập phân vượt giới hạn hoặc sai scale;
- timestamp không có timezone;
- encoding không hợp lệ;
- response bị cắt giữa chừng hoặc content length không khớp;
- pagination cursor lặp lại khiến vòng lặp không kết thúc.

Phân biệt lỗi parse/schema với lỗi tạm thời của mạng. Một response sai schema thường cần đưa vào dead-letter/quarantine hoặc báo lỗi tích hợp; retry cùng payload thường không sửa được dữ liệu.

### 3.3. Partial failure

Một request có thể hoàn thành một phần. Ví dụ batch gồm 100 bản ghi, 97 bản ghi đã được xử lý và 3 bản ghi thất bại. Retry toàn bộ batch có thể xử lý trùng 97 bản ghi thành công.

Thiết kế phù hợp:

- xác định kết quả theo từng item;
- dùng business key/idempotency key cho mỗi item;
- lưu trạng thái thành công/thất bại riêng;
- chỉ retry phần thất bại có thể phục hồi;
- giới hạn số lần retry và lưu nguyên nhân cuối cùng.

Với workflow nhiều bước, cân nhắc saga/compensation hoặc outbox/inbox thay vì cố gắng gói nhiều hệ thống độc lập vào một lần retry.

## 4. Thiết kế retry có giới hạn

Một retry policy nên trả lời được các câu hỏi:

- Những exception/status nào được retry?
- Tối đa bao nhiêu lần thử, tính cả lần đầu?
- Khoảng chờ giữa các lần thử là bao lâu?
- Có exponential backoff và jitter không?
- Deadline tổng của request là bao nhiêu?
- Thao tác có idempotent không?
- Hết retry thì trả lỗi, fallback hay đưa vào hàng đợi?

Không có retry policy phù hợp cho mọi dependency. Retry cho truy vấn đọc có thể khác retry cho lệnh ghi, và retry tới database có thể khác retry tới payment provider.

### 4.1. Exponential backoff

Một cách tính khoảng chờ tăng dần:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Trong đó:

- \(d_0\): thời gian chờ ban đầu;
- \(n\): số thứ tự lần retry;
- \(d_{\max}\): giới hạn thời gian chờ.

Nếu nhiều instance retry cùng thời điểm, chúng có thể tạo một đợt tải dồn lên dependency. **Jitter** thêm độ ngẫu nhiên vào thời gian chờ để phân tán các lần thử.

Một dạng full jitter thường dùng:

\[
w_n \sim U(0,\min(d_{\max}, d_0 \times 2^{n-1}))
\]

Khoảng chờ thực tế phải nằm trong deadline tổng. Nếu request chỉ còn 100 ms mà backoff dự kiến 500 ms, không nên tiếp tục retry rồi trả response muộn.

### 4.2. Giới hạn số lần thử và retry budget

Ví dụ một thao tác cho phép tối đa 3 lần thử, gồm lần đầu và 2 lần retry. Nếu cả 3 lần đều thất bại, trả lỗi cuối cùng hoặc chuyển sang quy trình xử lý bất đồng bộ đã định nghĩa.

Retry budget có thể giới hạn tổng số lần retry theo dependency hoặc theo khoảng thời gian. Khi dependency đang suy giảm, budget ngăn retry chiếm hết thread, connection và CPU của ứng dụng.

Không xếp chồng nhiều retry layer mà không tính tổng số lần thử. Ví dụ HTTP client retry 3 lần, service retry 3 lần và gateway retry 3 lần có thể tạo tối đa 27 lần gọi tới hệ thống đích.

### 4.3. Tôn trọng deadline và timeout

Mỗi lần thử phải có timeout nhỏ hơn hoặc bằng thời gian còn lại của request. Cần phân biệt:

- connect timeout: thời gian thiết lập kết nối;
- response/read timeout: thời gian chờ dữ liệu;
- pool acquisition timeout: thời gian chờ lấy connection;
- operation deadline: giới hạn tổng của cả thao tác, gồm retry và backoff.

Timeout tổng cần được truyền xuyên các layer nếu client/framework hỗ trợ. Nếu chỉ cấu hình timeout cho từng lần thử mà không có deadline tổng, một request có thể kéo dài lâu hơn dự kiến.

## 5. Idempotency cho thao tác ghi

### 5.1. Idempotency key

Client gửi một key ổn định cho cùng một ý định nghiệp vụ:

~~~http
POST /transfers
Idempotency-Key: 9b77d1a2-transaction-104
Content-Type: application/json
~~~

Server lưu key cùng trạng thái và kết quả:

| Trạng thái | Hành vi khi nhận lại cùng key |
| --- | --- |
| Chưa có key | Tạo record và xử lý lần đầu |
| Đang xử lý | Trả trạng thái đang xử lý hoặc response phù hợp theo contract |
| Đã thành công | Trả lại kết quả đã lưu |
| Đã thất bại vĩnh viễn | Trả lại lỗi đã lưu, không thực hiện side effect lần nữa |
| Cùng key nhưng payload khác | Từ chối vì một key đại diện cho một ý định duy nhất |

Key phải có phạm vi duy nhất phù hợp, chẳng hạn tenant + operation + key. Lưu fingerprint của payload để phát hiện trường hợp client tái sử dụng key với nội dung khác.

### 5.2. Idempotency không chỉ là kiểm tra key trong bộ nhớ

Trong ứng dụng chạy nhiều replica, map trong memory của một process không đủ. Record idempotency cần được lưu ở nơi chia sẻ và có ràng buộc unique/transaction phù hợp.

Với hệ thống thanh toán hoặc tạo đơn hàng:

- ghi idempotency record và trạng thái nghiệp vụ trong transaction;
- dùng unique constraint để chống hai request đồng thời cùng key;
- lưu kết quả đủ để trả lại cho lần gọi sau;
- đặt retention phù hợp với thời gian client có thể retry;
- tránh lưu dữ liệu nhạy cảm không cần thiết.

Nếu provider bên ngoài hỗ trợ idempotency key, truyền cùng key qua mọi lần retry. Không tạo key mới cho mỗi lần thử.

## 6. Retry HTTP client và dịch vụ bên ngoài

### 6.1. Chọn lỗi có thể retry

Ví dụ thường có thể cân nhắc retry có điều kiện:

- connection reset trước khi nhận response;
- connect/read timeout;
- HTTP 502, 503 hoặc 504 khi hợp đồng provider cho phép;
- HTTP 429 theo Retry-After hoặc policy quota;
- lỗi DNS tạm thời đã được xác định là có thể phục hồi.

Không retry tự động:

- HTTP 400 do payload sai;
- HTTP 401/403 khi chưa có bước refresh credential hợp lệ;
- HTTP 404 nếu tài nguyên không tồn tại theo nghĩa nghiệp vụ;
- lỗi validation/schema từ response;
- TLS certificate/hostname mismatch;
- lỗi cấu hình endpoint hoặc protocol.

Một số provider có quy ước khác. Dựa vào contract của provider và error code cụ thể, không chỉ dựa vào status class.

### 6.2. Tôn trọng Retry-After

Khi server trả HTTP 429 hoặc 503 với header Retry-After, client nên tuân thủ giá trị này nếu nó nằm trong deadline và policy cho phép. Header có thể biểu diễn số giây hoặc HTTP date. Nếu thời gian chờ vượt deadline, trả lỗi hoặc chuyển sang xử lý bất đồng bộ thay vì giữ request vô hạn.

### 6.3. Ví dụ cấu hình Resilience4j Retry

Ví dụ cấu hình cho một adapter đọc dữ liệu:

~~~yaml
resilience4j:
  retry:
    instances:
      archiveRead:
        max-attempts: 3
        wait-duration: 200ms
        enable-exponential-backoff: true
        exponential-backoff-multiplier: 2
        enable-randomized-wait: true
        randomized-wait-factor: 0.5
        retry-exceptions:
          - java.io.IOException
        ignore-exceptions:
          - com.example.billing.InvalidDocumentException
~~~

Đây là cấu hình minh họa; cần kiểm tra tên property và dependency integration theo version Resilience4j đang dùng. max-attempts thường tính cả lần gọi đầu. Danh sách exception phải được điều chỉnh theo client thực tế và không nên retry mọi lỗi I/O nếu lỗi đó có thể là cấu hình cố định.

Đặt retry tại ranh giới adapter để policy gắn với dependency cụ thể. Với lệnh ghi, chỉ bật retry khi có idempotency hoặc cơ chế xác minh kết quả không xác định.

### 6.4. Không retry bên trong mọi tầng

Nếu service gọi adapter, adapter lại retry, và gateway cũng retry, tổng số lần thử có thể tăng theo cấp số nhân. Chọn một layer chịu trách nhiệm retry cho từng dependency và ghi rõ số lần thử tối đa, deadline tổng, loại lỗi được retry, nơi lưu idempotency key và hành vi khi hết retry.

## 7. Khôi phục kết nối database

### 7.1. Connection pool có thể giữ connection đã chết

Ứng dụng Spring Boot thường dùng connection pool như HikariCP. Khi database failover, restart hoặc network bị gián đoạn, một connection đã mượn có thể không còn dùng được. Pool cần phát hiện và loại bỏ connection lỗi; ứng dụng cũng cần xử lý lỗi của operation đang chạy.

Không giả định rằng chỉ cần gọi lại getConnection() là mọi transaction được khôi phục. Connection cũ có thể đã ở trạng thái lỗi, transaction có thể đã rollback hoặc kết quả commit có thể không rõ.

### 7.2. Cấu hình pool theo môi trường

Ví dụ các thuộc tính Hikari thường cần xem xét:

~~~yaml
spring:
  datasource:
    hikari:
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1500000
      keepalive-time: 300000
      maximum-pool-size: 10
~~~

Các giá trị trên chỉ để minh họa cách cấu hình, không phải khuyến nghị dùng nguyên xi. Chọn maxLifetime thấp hơn giới hạn connection của database/proxy/load balancer, và đặt keepalive phù hợp với giới hạn hạ tầng. Không đặt keepalive lớn hơn hoặc bằng max lifetime. Kiểm tra khả năng hỗ trợ và điều kiện áp dụng của phiên bản HikariCP.

Validation thường diễn ra khi pool cần xác nhận connection; không bật query kiểm tra riêng một cách máy móc nếu driver đã hỗ trợ JDBC validation. Theo dõi pool active/idle/pending và timeout để xác định vấn đề.

### 7.3. Retry transaction như một đơn vị mới

Khi connection lỗi giữa transaction, không nên tiếp tục dùng transaction/connection cũ. Nếu thao tác có thể retry an toàn, lần thử tiếp theo phải chạy trong một transaction mới.

Một cách tổ chức là để lớp ngoài điều phối retry, còn một bean riêng thực hiện transaction:

~~~java
@Service
class TransferFacade {

    private final Retry retry;
    private final TransferTransaction transaction;

    TransferFacade(Retry retry, TransferTransaction transaction) {
        this.retry = retry;
        this.transaction = transaction;
    }

    TransferResult transfer(TransferCommand command) {
        return Retry.decorateSupplier(
            retry,
            () -> transaction.execute(command)
        ).get();
    }
}

@Service
class TransferTransaction {

    @Transactional
    public TransferResult execute(TransferCommand command) {
        // Đọc trạng thái, kiểm tra invariant và ghi thay đổi
        // trong một transaction mới của lần thử này.
        return performTransfer(command);
    }
}
~~~

Đây là cấu trúc minh họa dùng Resilience4j Retry và Spring transaction proxy. TransferTransaction là bean riêng để lời gọi đi qua proxy @Transactional; không gọi method transactional bằng self-invocation trong cùng object. Cần cấu hình transaction propagation phù hợp và bảo đảm không có transaction ngoài bao quanh toàn bộ retry loop.

Không retry lỗi constraint, dữ liệu không hợp lệ hoặc lỗi nghiệp vụ. Với lỗi commit có kết quả không xác định, phải tra cứu theo idempotency/business key trước khi chạy lại.

### 7.4. Phân loại lỗi SQL

Spring dịch nhiều JDBC exception thành hệ phân cấp DataAccessException. Có thể cân nhắc retry một số lỗi transient như lỗi kết nối tạm thời, deadlock hoặc serialization failure theo database cụ thể.

Không retry chung toàn bộ DataAccessException. Ví dụ unique constraint violation thường là lỗi xác định; retry ngay cùng câu lệnh không làm nó biến mất. Dựa vào SQLState/vendor code và exception translation của driver.

Với deadlock/serialization failure, retry phải chạy lại toàn transaction để đọc lại dữ liệu và tính lại quyết định nghiệp vụ. Không chỉ chạy lại câu SQL cuối cùng trong transaction đã thất bại.

## 8. Khôi phục kết nối HTTP, message broker và SDK

### 8.1. Tạo client một lần, phục hồi transport đúng cách

HTTP client, database pool và message broker client thường quản lý connection pool/event loop bên trong. Không tạo client mới cho mỗi request chỉ để né lỗi connection. Điều đó có thể làm tăng socket, thread và handshake.

Thay vào đó:

- dùng client bean có lifecycle rõ ràng;
- cấu hình connect/read timeout và pool eviction;
- để client loại bỏ connection hỏng theo API của thư viện;
- dùng retry ở operation boundary với deadline;
- đóng client khi ApplicationContext shutdown;
- theo dõi connection pool và lỗi reconnect.

Nếu SDK không hỗ trợ reconnect an toàn, cần xác định liệu phải tạo lại client hay khởi động lại integration component. Không tự gọi close()/reconnect() từ nhiều thread đồng thời nếu vendor không bảo đảm thread safety.

### 8.2. Message broker và redelivery

Message broker thường cung cấp at-least-once delivery. Consumer có thể xử lý xong nhưng chết trước khi ack; broker gửi lại message.

Consumer cần idempotent:

- dùng message ID hoặc business key để ghi nhận đã xử lý;
- commit thay đổi dữ liệu và inbox/processed marker trong cùng transaction nếu có thể;
- chỉ ack sau khi công việc bền vững hoàn tất;
- phân biệt lỗi tạm thời với poison message;
- giới hạn redelivery và chuyển message không thể xử lý sang dead-letter queue.

Không retry poison message vô hạn. Một payload sai schema sẽ tiếp tục sai ở mọi lần giao lại và có thể chặn partition/queue.

### 8.3. Outbox/inbox cho side effect nhiều hệ thống

Khi transaction database cần phát event, dùng transactional outbox để ghi business state và event trong cùng transaction. Publisher gửi event sau đó; consumer dùng inbox/idempotency để chống xử lý trùng.

Outbox không tạo exactly-once delivery xuyên mọi hệ thống. Nó giúp bảo đảm event được lưu cùng transaction và có thể phát lại; consumer vẫn phải xử lý duplicate an toàn.

## 9. Circuit breaker, bulkhead và fallback

Retry hữu ích khi lỗi ngắn hạn. Nếu dependency đã mất kết nối trong thời gian dài, retry liên tục chỉ làm tăng tải và kéo dài request.

### 9.1. Circuit breaker

Circuit breaker theo dõi kết quả gọi dependency:

- **Closed:** cho phép request đi qua và ghi nhận kết quả.
- **Open:** chặn lời gọi trong một khoảng thời gian khi tỷ lệ lỗi vượt ngưỡng.
- **Half-open:** cho phép một số probe để xác nhận dependency đã phục hồi.

Retry và circuit breaker giải quyết hai tình huống khác nhau. Retry xử lý lỗi tạm thời trong một operation; circuit breaker ngăn nhiều operation tiếp tục gọi một dependency đang suy giảm.

### 9.2. Bulkhead

Bulkhead giới hạn số request đồng thời tới dependency. Khi provider chậm, số thread/connection chờ không được tăng vô hạn. Giới hạn concurrency, queue và timeout phải phù hợp với capacity thực tế của hệ thống ngoài.

### 9.3. Fallback phải giữ đúng ngữ nghĩa

Fallback có thể là:

- trả cache có ghi rõ dữ liệu stale nếu nghiệp vụ cho phép;
- đưa command vào queue để xử lý bất đồng bộ;
- trả trạng thái pending;
- từ chối có kiểm soát với mã lỗi retryable cho caller.

Không trả response thành công giả nếu side effect chưa hoàn tất. Ví dụ không được báo “đã thanh toán” chỉ vì payment provider timeout. Hãy trả trạng thái chưa xác định/pending và cung cấp cách tra cứu.

## 10. Kiểm thử lỗi và khôi phục bằng fault injection

Happy-path test không tạo ra được các điều kiện mạng và hệ thống hiếm gặp. Dùng công cụ mô phỏng lỗi ở ranh giới tích hợp:

| Công cụ/cách làm | Có thể mô phỏng |
| --- | --- |
| WireMock hoặc MockWebServer | HTTP 429/503, timeout, connection close, response sai schema |
| Testcontainers | Khởi động database/broker thật trong container, dừng và khởi động lại service |
| Toxiproxy | Latency, bandwidth limit, reset, timeout và mất kết nối giữa hai thành phần |
| Fault injection trong test double | Lỗi theo lần gọi: lần 1 fail, lần 2 success; lỗi lặp lại; response partial |
| Chaos tooling ở môi trường test | Pod restart, network disruption, dependency unavailable |

Fault injection nên có phạm vi kiểm soát: môi trường test, dữ liệu riêng, timeout hữu hạn và khả năng dọn dẹp. Không chạy thử nghiệm phá kết nối trên production nếu chưa có quy trình được phê duyệt.

### 10.1. Test retry có kiểm soát

Ví dụ một HTTP stub trả 503 hai lần rồi 200:

~~~java
stubFor(get(urlEqualTo("/documents/doc-1"))
    .inScenario("temporary-outage")
    .whenScenarioStateIs(Scenario.STARTED)
    .willReturn(aResponse().withStatus(503))
    .willSetStateTo("second-attempt"));

stubFor(get(urlEqualTo("/documents/doc-1"))
    .inScenario("temporary-outage")
    .whenScenarioStateIs("second-attempt")
    .willReturn(aResponse().withStatus(503))
    .willSetStateTo("available"));

stubFor(get(urlEqualTo("/documents/doc-1"))
    .inScenario("temporary-outage")
    .whenScenarioStateIs("available")
    .willReturn(okJson("{\"id\":\"doc-1\"}")));
~~~

Test xác nhận operation cuối cùng thành công, số lần gọi đúng theo policy, thời gian hoàn tất nằm trong deadline và không có request thừa sau khi đã thành công.

Trong unit test, inject Clock, Sleeper hoặc scheduler giả để không phải chờ thời gian thật. Trong integration test, có thể dùng thời gian chờ ngắn nhưng vẫn kiểm tra số lần gọi và deadline.

### 10.2. Test lỗi vĩnh viễn không bị retry

Stub trả 400 do payload sai. Xác nhận client chỉ gọi một lần, trả lỗi validation/integration phù hợp và không tạo thêm side effect.

### 10.3. Test timeout sau khi server đã commit

Mô phỏng server thực hiện side effect nhưng làm rơi response. Client timeout và retry cùng idempotency key. Xác nhận chỉ có một giao dịch được tạo và lần gọi sau nhận lại kết quả đã lưu.

### 10.4. Test database restart

Với Testcontainers hoặc Toxiproxy:

1. Khởi động database và ứng dụng.
2. Thực hiện một truy vấn thành công.
3. Dừng database hoặc cắt kết nối.
4. Gọi operation trong thời gian database unavailable.
5. Khởi động lại database.
6. Xác nhận pool loại bỏ connection lỗi, operation mới kết nối lại và dữ liệu nhất quán.

Không chỉ kiểm tra log có dòng “reconnected”. Hãy kiểm tra một operation nghiệp vụ thực tế sau khi phục hồi.

## 11. Kiểm thử riêng trên Native Image

Native executable phải được kiểm tra trong môi trường gần với deployment target. JVM integration test không xác nhận hoàn toàn hành vi native vì runtime, TLS, DNS, reflection, class initialization và native libraries có thể khác.

Các nhóm cần chạy trên native:

- startup khi dependency đang unavailable;
- retry sau connection reset và sau timeout;
- kết nối lại database/broker sau restart;
- TLS handshake và truststore/CA bundle;
- HTTP response sai schema và dữ liệu biên;
- connection pool sau thời gian idle;
- graceful shutdown khi request hoặc message đang xử lý;
- native library/driver có JNI hoặc service loading.

### 11.1. Cấu hình phải được đọc ở runtime

Endpoint, credential, timeout, region và trust material theo môi trường phải được cung cấp lúc chạy. Không tạo database connection, HTTP connection hoặc đọc secret trong static initializer/AOT processing.

Kiểm tra:

- không có credential trong generated code hoặc image heap;
- environment variable/config tree được bind đúng trong native executable;
- file CA/truststore được đóng gói hoặc mount theo thiết kế;
- đường dẫn và quyền đọc đúng trong container;
- không phụ thuộc file local chỉ tồn tại trên máy build.

### 11.2. Native image và TLS

Nếu JVM kết nối HTTPS được nhưng native executable gặp lỗi trust/certificate, kiểm tra:

- CA certificate có trong truststore mà native runtime sử dụng không;
- custom truststore có được cung cấp ở runtime không;
- DNS/hostname/SNI có khớp certificate không;
- certificate chain và thời hạn chứng chỉ có hợp lệ không;
- cấu hình SSL của thư viện có cần resource metadata hoặc native support bổ sung không.

Không tắt hostname verification hoặc trust-all certificates để “sửa” lỗi test. Hãy sửa trust chain và cấu hình certificate đúng.

### 11.3. Test cùng kịch bản trên JVM và native

Giữ cùng contract suite và test data. Chạy một lần với JVM artifact, một lần với native executable trong cùng phiên bản dependency và cấu hình tương đương. Ghi nhận khác biệt:

| Quan sát | JVM | Native |
| --- | --- | --- |
| Lần gọi đầu sau khi dependency restart | Thành công/thất bại theo policy | Thành công/thất bại theo cùng policy |
| Số lần retry | Số lần thực tế | Số lần thực tế |
| Deadline tổng | Thời gian đo được | Thời gian đo được |
| Kết quả nghiệp vụ | Record/state | Record/state |
| Reconnect | Pool/client phục hồi | Pool/client phục hồi |
| TLS và resource | Certificate/resource được tìm thấy | Certificate/resource được tìm thấy |

So sánh kết quả và tính đúng đắn trước khi so sánh hiệu năng. Native startup nhanh không bù được một retry policy tạo duplicate transaction.

## 12. Quan sát retry và recovery trong production

Mỗi dependency nên có metrics riêng:

- số lần gọi ban đầu và số lần retry;
- retry count theo exception/status;
- retry exhausted;
- circuit breaker state và transition;
- request latency và deadline exceeded;
- connection pool active/idle/pending/timeout;
- reconnect success/failure;
- message redelivery và dead-letter count;
- idempotency duplicate hit/conflict.

Log nên có correlation ID, operation ID, dependency name, attempt number, elapsed time và error category. Không log token, password, payload chứa dữ liệu cá nhân hoặc connection string có credential.

Metric retry tăng liên tục có thể báo dependency suy giảm hoặc timeout quá thấp. Nếu chỉ đo tỷ lệ request cuối cùng thành công, retry storm có thể bị che giấu vì user vẫn nhận được kết quả trong khi hệ thống tạo nhiều tải phụ.

## 13. Những lỗi thiết kế thường gặp

| Cách làm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Retry mọi exception | Lặp lỗi validation, auth và bug | Allowlist lỗi transient |
| Retry lệnh ghi không có idempotency | Tạo giao dịch/side effect trùng | Idempotency key và trạng thái bền vững |
| Retry vô hạn | Cạn thread, connection và queue | Giới hạn attempts, deadline và retry budget |
| Backoff cố định cho mọi instance | Nhiều client retry cùng lúc | Exponential backoff và jitter |
| Retry ở nhiều layer | Khuếch đại số lần gọi | Chỉ định một retry owner cho mỗi dependency |
| Tiếp tục transaction đã lỗi | Dùng connection/transaction không còn hợp lệ | Tạo transaction mới cho mỗi lần thử |
| Tạo HTTP client mới cho mỗi lần lỗi | Rò rỉ socket/thread, tăng handshake | Quản lý client lifecycle và pool |
| Ack message trước khi commit | Mất message khi process chết | Ack sau khi xử lý bền vững |
| Retry poison message vô hạn | Chặn queue/partition | Giới hạn redelivery và dead-letter |
| Fallback thành công giả | Caller tin side effect đã hoàn tất | Trả pending/unknown và cung cấp trạng thái tra cứu |
| Chỉ test bằng mock happy path | Không phát hiện lỗi mạng/metadata | Fault injection và native contract test |

## 14. Quy trình xử lý một sự cố kết nối

Khi dependency chập chờn, thực hiện theo trình tự:

1. **Phân loại lỗi:** xác định timeout, reset, 429, 5xx, lỗi TLS, lỗi auth hay lỗi dữ liệu.
2. **Xác định trạng thái nghiệp vụ:** thao tác có thể đã commit hay chưa; tra cứu bằng business key/idempotency key nếu cần.
3. **Kiểm tra retry policy:** attempts, backoff, jitter, deadline và retry budget.
4. **Kiểm tra client/pool:** connection cũ có bị loại bỏ không, pool có còn capacity không, client có hỗ trợ reconnect không.
5. **Khôi phục dependency:** xác nhận DNS, network, TLS, database/broker và credential.
6. **Chạy operation mới:** dùng transaction/connection hợp lệ và cùng idempotency key nếu retry cùng ý định.
7. **Xác minh kết quả:** kiểm tra dữ liệu đã commit, message đã ack và không có side effect trùng.
8. **Ghi nhận nguyên nhân:** metrics, attempt count, thời gian phục hồi và lỗi cuối cùng.

Không đánh dấu sự cố đã phục hồi chỉ vì health check trả 200. Hãy xác nhận luồng nghiệp vụ thực sự có thể đọc/ghi qua dependency.

## 15. Checklist trước khi phát hành

- [ ] Lỗi được phân loại thành permanent, transient hoặc outcome-unknown.
- [ ] Validation dữ liệu chạy trước side effect.
- [ ] Response sai schema/partial payload có cách xử lý rõ ràng.
- [ ] Retry chỉ áp dụng cho lỗi có khả năng phục hồi.
- [ ] Số lần thử, backoff, jitter, deadline và retry budget được giới hạn.
- [ ] HTTP 429/503 xử lý Retry-After theo contract.
- [ ] Thao tác ghi có idempotency key hoặc cơ chế tra cứu kết quả.
- [ ] Transaction retry chạy trong transaction mới.
- [ ] Database pool/client có lifecycle và timeout phù hợp.
- [ ] Message consumer xử lý duplicate, redelivery và poison message.
- [ ] Circuit breaker/bulkhead/fallback giữ đúng ngữ nghĩa nghiệp vụ.
- [ ] Đã fault-inject timeout, reset, unavailable, response sai và restart dependency.
- [ ] Cùng kịch bản đã chạy trên JVM và native executable.
- [ ] Native runtime đọc endpoint, secret, CA và config từ nguồn runtime.
- [ ] Có metrics cho retry, exhausted, reconnect, pool và dead-letter.
- [ ] Log không chứa credential hoặc payload nhạy cảm.

**Ghi nhớ:** đường đi lỗi cần được thiết kế và kiểm thử như một phần của hợp đồng tích hợp. Phân loại lỗi trước, retry có deadline và idempotency, tạo transaction/kết nối mới khi cần, rồi xác minh trạng thái nghiệp vụ sau khi phục hồi. Chạy fault-injection suite trên native executable trong môi trường gần production để phát hiện các khác biệt mà JVM test không thể chứng minh.

## Tài liệu tham khảo

- [Spring Framework — Data Access and Transaction Management](https://docs.spring.io/spring-framework/reference/data-access.html): exception translation và transaction management.
- [Spring Boot — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html): cấu hình datasource và connection pool.
- [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry): attempts, interval function và retry configuration.
- [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): closed/open/half-open và giới hạn lời gọi.
- [Testcontainers for Java](https://java.testcontainers.org/): kiểm thử với database, broker và dependency thật trong container.
- [Toxiproxy](https://github.com/Shopify/toxiproxy): mô phỏng lỗi mạng, latency và gián đoạn kết nối.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): metadata cần thiết cho reflection, resource và các truy cập động.

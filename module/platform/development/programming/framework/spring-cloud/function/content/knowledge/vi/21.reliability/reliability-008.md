
# Giới hạn thời gian và hủy tác vụ bên ngoài

## 1. Mục tiêu bài học

Một Function gọi dịch vụ thanh toán, truy vấn database hoặc chờ một API đối tác có thể bị treo lâu hơn thời gian người gọi chấp nhận. Nếu chỉ đặt timeout ở HTTP response, công việc bên dưới có thể vẫn chạy; nếu hủy một message consumer quá sớm, database có thể đã commit nhưng broker chưa nhận ACK. Vì vậy, timeout và cancellation cần được thiết kế xuyên suốt từ adapter tới thao tác I/O.

Trong module **SPRING_CLOUD_FUNCTION**, logic nghiệp vụ được phát triển bằng `Supplier`, `Function` và `Consumer`, đăng ký qua `FunctionCatalog`, ghép thành pipeline và triển khai qua HTTP, sự kiện hoặc serverless. Cùng một hàm có thể được gọi ở nhiều môi trường, nhưng deadline, timeout và cách hủy phụ thuộc vào adapter, client và loại tác vụ.

Bài thuộc chương **Độ tin cậy**, tập trung vào **giới hạn thời gian và hủy tác vụ bên ngoài**. Sau bài này, bạn có thể:

- Phân biệt timeout, deadline, cancellation và việc tác vụ thật sự dừng.
- Đặt ngân sách thời gian cho toàn request và từng bước gọi bên ngoài.
- Cấu hình timeout cho HTTP client, JDBC/database, broker và serverless.
- Hiểu giới hạn của `Future.cancel`, `CompletableFuture.orTimeout`, interrupt và Reactor cancellation.
- Truyền deadline còn lại qua các service mà không cộng dồn timeout quá mức.
- Xử lý trường hợp timeout nhưng side effect có thể đã commit.
- Phối hợp timeout với transaction, retry, idempotency và ACK.
- Kiểm thử cả lỗi timeout lẫn việc tác vụ có thực sự được hủy hay không.

> **Nguyên tắc xuyên suốt:** Timeout giới hạn thời gian chờ hoặc phát tín hiệu thất bại; nó không tự chứng minh công việc bên ngoài đã dừng hay chưa commit. Hãy đặt timeout ở đúng client/driver, truyền deadline, thiết kế cancellation có hợp tác và bảo vệ side effect bằng idempotency.

## 2. Bốn khái niệm không nên đánh đồng

| Khái niệm | Ý nghĩa | Điều không thể tự kết luận |
|---|---|---|
| Timeout | Một khoảng chờ/hoạt động vượt giới hạn | Tác vụ bên ngoài đã dừng |
| Deadline | Thời điểm cuối cùng mà toàn operation phải hoàn tất | Mọi tầng tự biết deadline |
| Cancellation | Yêu cầu hủy công việc đang chạy | Tác vụ đã hủy ngay lập tức |
| Completion | Tác vụ kết thúc thành công/thất bại/hủy | Caller chắc chắn đã nhận được kết quả |

Ví dụ client gửi request tới dịch vụ thanh toán:

~~~text
Client gửi POST
     |
     v
Payment service nhận yêu cầu
     |
     v
Payment service tạo giao dịch
     |
     v
Response bị chậm/mất
     |
Client timeout và ngừng chờ
     |
     +---- Payment service có thể vẫn đang xử lý
~~~

Client đã timeout, nhưng giao dịch có thể vẫn được tạo. Timeout là **trạng thái quan sát của caller**, không phải bằng chứng rằng server đã rollback.

### 2.1. Timeout ở một tầng không tự hủy mọi tầng

Một request có thể đi qua:

~~~text
HTTP client
    |
API gateway
    |
Spring Cloud Function adapter
    |
Application service
    |
HTTP client / JDBC driver / broker client
    |
External system
~~~

Nếu HTTP client timeout, nó có thể đóng socket hoặc gửi cancellation xuống transport. Nhưng server từ xa có thể đã nhận toàn bộ request và tiếp tục xử lý. Nếu application thread bị interrupt, driver có thể không hỗ trợ hủy ngay. Nếu Reactor gửi cancel, Publisher upstream có thể không có cơ chế dừng một I/O đã commit.

Vì vậy cần phân biệt **hủy lời gọi ở caller**, **hủy tác vụ ở process hiện tại** và **dừng side effect ở hệ thống bên ngoài**.

## 3. Timeout, deadline và ngân sách thời gian

Timeout thường được cấu hình theo một bước; deadline là giới hạn tuyệt đối cho toàn operation. Ví dụ request có deadline 3 giây:

~~~text
Tổng ngân sách: 3000 ms
  |
  +-- lấy connection: tối đa 300 ms
  |
  +-- gọi API đối tác: tối đa 1500 ms
  |
  +-- ghi DB: tối đa 700 ms
  |
  +-- serialize/response/ACK: giữ lại ít nhất 500 ms
~~~

Các con số chỉ là ví dụ. Cần đo latency thực tế và chừa thời gian cho cleanup, response hoặc ACK.

### 3.1. Timeout từng bước có thể cộng dồn quá deadline

Nếu ba dependency mỗi dependency có timeout 3 giây và được gọi tuần tự, tổng thời gian có thể gần 9 giây, chưa kể overhead. Trong khi caller chỉ chờ 4 giây, service có thể tiếp tục làm việc sau khi caller đã bỏ cuộc.

Không đặt mọi timeout bằng nhau theo thói quen. Tính ngân sách từ **deadline tổng**, rồi phân bổ cho các bước.

### 3.2. Deadline còn lại giảm dần qua từng tầng

Nếu request bắt đầu với deadline 17:00:03 và service A đã dùng 1 giây, service B chỉ còn khoảng 2 giây. Không truyền lại “timeout 3 giây” ở mỗi hop vì như vậy tổng thời gian có thể vượt giới hạn ban đầu.

Mỗi tầng nên tính:

~~~text
remaining = deadline - now
effectiveTimeout = min(localCap, remaining - responseReserve)
~~~

Nếu ngân sách còn lại không đủ cho một thao tác, từ chối sớm hoặc chuyển sang quy trình bất đồng bộ có trạng thái thay vì bắt đầu một công việc chắc chắn không kịp.

### 3.3. Monotonic clock và wall clock

Trong cùng process, đo thời lượng bằng monotonic clock (ví dụ `System.nanoTime()`) tránh bị ảnh hưởng khi đồng hồ hệ thống được chỉnh. Khi truyền deadline giữa các process, thường phải gửi một mốc thời gian có thể trao đổi (ví dụ epoch timestamp) hoặc một header timeout còn lại.

Đồng hồ giữa máy có thể lệch. Vì vậy, không nên tin tuyệt đối một deadline wall-clock từ client; validate phạm vi, giới hạn local cap và trừ một phần dự phòng. Trong một process, chuyển deadline sang monotonic remaining duration để tính thời gian chờ.

## 4. Chọn loại timeout theo từng thao tác

Không có một timeout duy nhất bao phủ mọi loại I/O.

| Tầng | Timeout thường cần quan tâm | Rủi ro nếu thiếu |
|---|---|---|
| Connection pool | Thời gian chờ lấy connection | Request xếp hàng vô hạn |
| DNS/connect/TLS | Thiết lập kết nối | Treo trước khi gửi request |
| HTTP response | Chờ response | Caller đợi quá lâu |
| Socket read/write | Đọc/ghi dữ liệu | Kết nối sống nhưng không tiến triển |
| JDBC connect | Mở kết nối DB | Thread chờ network |
| SQL statement/query | Thực thi câu lệnh | Query giữ tài nguyên quá lâu |
| Transaction | Tổng thời gian giao dịch | Giữ lock/connection lâu |
| Broker delivery/visibility | Thời gian xử lý trước ACK/visibility expiry | Message bị redeliver khi vẫn đang xử lý |
| Serverless invocation | Thời gian tối đa của handler | Runtime dừng invocation |
| Toàn request | Deadline tổng | Các timeout từng bước cộng dồn |

Timeout ở pool, connect, read và response có thể khác nhau. Một timeout response không nhất thiết giới hạn thời gian chờ connection pool hoặc thời gian server xử lý sau khi client ngắt kết nối.

### 4.1. Timeout per-attempt và timeout tổng

Nếu retry một lời gọi ba lần, cần phân biệt:

- **Per-attempt timeout:** giới hạn từng lần gọi.
- **Overall deadline:** giới hạn cả attempts, backoff và xử lý kết quả.

~~~text
Overall deadline: 2500 ms
  Attempt 1: tối đa 600 ms
  Backoff: 100 ms
  Attempt 2: tối đa 600 ms
  Backoff: 200 ms
  Attempt 3: chỉ dùng phần ngân sách còn lại
~~~

Nếu tổng ngân sách gần hết, không bắt đầu attempt mới. Retry policy cần phối hợp với deadline, không chỉ kiểm tra số lần thử.

## 5. Java blocking: timeout khi chờ không có nghĩa task đã dừng

Một cách thường gặp là chạy tác vụ trong `ExecutorService` rồi đợi `Future`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

ExecutorService executor = new ThreadPoolExecutor(
        8,
        8,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.AbortPolicy());

Future<PaymentResult> future =
        executor.submit(() -> paymentClient.charge(command));

try {
    PaymentResult result = future.get(2, TimeUnit.SECONDS);
    return result;
} catch (TimeoutException timeout) {
    future.cancel(true);
    throw new PaymentTimeoutException(
            "Payment call exceeded its deadline", timeout);
}
~~~

`future.get(timeout)` giới hạn thời gian **caller chờ kết quả**. `future.cancel(true)` yêu cầu hủy và có thể interrupt thread đang chạy, nhưng không bảo đảm task hoặc socket I/O lập tức dừng.

### 5.1. Interrupt là cơ chế hợp tác

Một task Java có thể kiểm tra interrupt:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    doSmallUnitOfWork();
}
~~~

Khi chờ trong một số API interruptible, thread có thể nhận `InterruptedException`. Khi bắt exception mà không ném tiếp, thường cần khôi phục cờ interrupt:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationCancelledException(ex);
}
~~~

Không bỏ qua interrupt rồi tiếp tục làm việc như không có gì. Tuy nhiên, nhiều lời gọi native/network/database không dừng chỉ vì thread được interrupt; cần timeout/cancel API của chính client hoặc driver.

### 5.2. Không tạo thread vô hạn để né timeout

Không tạo một thread mới cho mỗi request rồi để các task bị treo không giới hạn. Khi dependency chậm, thread và connection có thể tăng đến cạn tài nguyên.

Dùng executor có giới hạn, queue có giới hạn, timeout ở I/O client và cơ chế từ chối khi quá tải. Cần quan sát số task đang chạy, queue depth và task bị timeout.

## 6. CompletableFuture: timeout kết quả và hủy công việc là hai việc khác nhau

Java cung cấp `orTimeout` và `completeOnTimeout`:

~~~java
CompletableFuture<PaymentResult> future =
        paymentClient.chargeAsync(command);

return future.orTimeout(2, TimeUnit.SECONDS);
~~~

`orTimeout` hoàn tất future bằng lỗi timeout nếu quá hạn. Nó không tự bảo đảm rằng request đã gửi tới hệ thống ngoài bị hủy. Tương tự:

~~~java
return paymentClient.lookupAsync(id)
        .completeOnTimeout(
                PaymentResult.unknown(id),
                2,
                TimeUnit.SECONDS);
~~~

`completeOnTimeout` cung cấp giá trị thay thế cho caller khi quá hạn; tác vụ gốc có thể vẫn tiếp tục. Không dùng một kết quả fallback để tuyên bố giao dịch đã thất bại hoặc chưa được tạo.

### 6.1. cancel() của CompletableFuture không đảm bảo interrupt computation

`CompletableFuture.cancel(true)` không có semantics giống việc interrupt một thread do ứng dụng trực tiếp quản lý; tham số `mayInterruptIfRunning` không được dùng để điều khiển quá trình tính toán underlying theo cách nhiều người kỳ vọng.

Nếu cần dừng công việc thật sự, giữ handle của client/task có hỗ trợ cancellation và gọi API hủy tương ứng. Ví dụ HTTP client có thể cung cấp handle/subscription để hủy request; database driver có thể hỗ trợ cancel statement.

### 6.2. Không dùng common pool cho I/O blocking không kiểm soát

`CompletableFuture.supplyAsync(...)` không truyền executor thường dùng common ForkJoinPool. I/O blocking kéo dài có thể chiếm worker dùng chung. Dùng executor riêng có giới hạn hoặc client non-blocking phù hợp.

## 7. WebClient và Reactor: timeout phát tín hiệu, cancellation truyền ngược

Với `Mono`, có thể đặt timeout ở boundary gọi dependency:

~~~java
Mono<PaymentResult> result =
        webClient.post()
                .uri("/payments")
                .bodyValue(command)
                .retrieve()
                .bodyToMono(PaymentResult.class)
                .timeout(Duration.ofSeconds(2));
~~~

Nếu không có kết quả trong thời gian giới hạn, Reactor phát lỗi timeout và hủy subscription upstream theo semantics của operator. Client connector có thể đóng/hủy request đang chạy. Nhưng server từ xa có thể đã nhận request và vẫn tiếp tục xử lý; cancellation không rollback một giao dịch đã commit.

### 7.1. timeout trên Flux có thể là idle timeout

Với `Flux`, `timeout(Duration)` thường giới hạn khoảng thời gian chờ tín hiệu tiếp theo; timer có thể được đặt lại sau mỗi phần tử. Nó hữu ích để phát hiện luồng im lặng, nhưng không nhất thiết giới hạn tổng tuổi thọ của một stream liên tục phát dữ liệu.

Nếu cần deadline tổng cho stream, dùng một cơ chế deadline bao ngoài hoặc giới hạn thời lượng stream theo semantics phù hợp. `take(Duration)` có thể kết thúc stream bình thường khi hết thời gian, khác với timeout phát lỗi. Phải chọn kết quả đúng với hợp đồng.

### 7.2. Quan sát cancellation khác quan sát error

~~~java
Mono<PaymentResult> operation =
        remoteCall()
            .doOnError(error -> metrics.recordFailure())
            .doOnCancel(() -> metrics.recordCancellation())
            .doFinally(signal -> logTerminalSignal(signal));
~~~

`doOnError` không được gọi chỉ vì downstream cancel. `doOnCancel` quan sát tín hiệu hủy; `doFinally` có thể quan sát complete/error/cancel. Đừng gộp mọi cancellation thành lỗi dependency.

### 7.3. Hủy upstream không bảo đảm hủy side effect bên ngoài

Cancellation có thể truyền qua các Publisher, nhưng mỗi adapter phải hỗ trợ. Một Publisher tùy biến bỏ qua cancel, một JDBC call blocking hoặc một remote server đã commit có thể tiếp tục hoạt động.

Đối với blocking I/O trong Reactor:
- Dùng scheduler phù hợp để không chặn event loop.
- Cấu hình timeout của driver/socket/query.
- Không xem việc cancel subscription là bằng chứng JDBC đã dừng.
- Thiết kế idempotency/tra cứu trạng thái nếu kết quả commit không rõ.

 
## 8. Cấu hình timeout cho WebClient/Reactor Netty

Một HTTP request có nhiều giai đoạn. Ví dụ cấu hình Reactor Netty:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

ConnectionProvider pool = ConnectionProvider.builder("payment-client")
        .maxConnections(100)
        .pendingAcquireTimeout(Duration.ofMillis(300))
        .build();

HttpClient httpClient = HttpClient.create(pool)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
        .responseTimeout(Duration.ofSeconds(2));

WebClient paymentWebClient = WebClient.builder()
        .baseUrl("https://payment.example")
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
~~~

Các giới hạn trong ví dụ có ý nghĩa riêng:

- `pendingAcquireTimeout` giới hạn thời gian chờ lấy connection từ pool.
- `CONNECT_TIMEOUT_MILLIS` giới hạn giai đoạn thiết lập kết nối TCP.
- `responseTimeout` của Reactor Netty giới hạn khoảng thời gian đọc response theo semantics của connector, không nên mặc định coi là deadline tổng của nghiệp vụ.
- `Mono.timeout` ở boundary có thể giới hạn tổng thời gian caller chờ Publisher kết quả.

Ví dụ kết hợp:

~~~java
Mono<PaymentResult> charge =
        paymentWebClient.post()
                .uri("/payments")
                .bodyValue(command)
                .retrieve()
                .bodyToMono(PaymentResult.class)
                .timeout(Duration.ofSeconds(3));
~~~

Deadline tổng phải đủ lớn hơn các phase timeout cần thiết nhưng vẫn nằm trong ngân sách caller. Đặt timeout per-request mà không xét pool/connect/read có thể để một giai đoạn khác chờ lâu ngoài ý muốn.

### 8.1. Read timeout và write timeout

Read timeout thường giới hạn khoảng không có dữ liệu đọc; write timeout giới hạn một thao tác ghi bị đình trệ. Chúng không nhất thiết là thời gian tối đa toàn bộ HTTP request. Tên property và cách cấu hình phụ thuộc connector/client.

Nếu thêm Netty handler, hãy hiểu handler được áp dụng cho từng connection và lifecycle của nó. Không gắn timeout handler bừa bãi làm ảnh hưởng mọi request trên connection được tái sử dụng. Ưu tiên cấu hình client chính thức của phiên bản đang dùng và kiểm thử connection reuse.

### 8.2. Đừng chỉ đặt timeout ở gateway

Gateway timeout sau 3 giây không tự dừng request downstream. Nếu gateway ngắt response nhưng application tiếp tục gọi payment/DB, tài nguyên vẫn bị tiêu thụ.

Truyền deadline còn lại tới application và các outbound client; mỗi tầng phải từ chối công việc mới khi không còn ngân sách.

## 9. Database/JDBC: timeout lấy connection, query và transaction

Một thao tác JDBC có thể chờ ở nhiều nơi:

1. Chờ connection pool cấp connection.
2. Mở socket/kết nối tới database.
3. Chờ server thực thi SQL.
4. Đọc kết quả qua network.
5. Chờ lock hoặc transaction commit.

Một timeout tổng ở HTTP không thay thế timeout tại các tầng này.

### 9.1. Query timeout ở JDBC

JDBC cung cấp `Statement.setQueryTimeout`:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT status FROM payment WHERE payment_id = ?")) {

    statement.setString(1, paymentId);
    statement.setQueryTimeout(2);

    try (ResultSet rs = statement.executeQuery()) {
        if (rs.next()) {
            return rs.getString("status");
        }
        return null;
    }
}
~~~

`setQueryTimeout(2)` yêu cầu driver giới hạn thời gian thực thi statement theo đơn vị giây. Driver/database có thể có semantics và độ chính xác khác nhau; cần xác minh bằng database thực. Query timeout không đồng nghĩa mọi thao tác network hoặc thời gian lấy connection đều bị giới hạn.

### 9.2. Connection pool timeout khác query timeout

Với HikariCP, `connectionTimeout` giới hạn thời gian chờ lấy connection từ pool. Nó không giới hạn thời gian SQL chạy trên connection đã cấp. Cấu hình pool, JDBC driver connect/socket timeout và statement/query timeout phải được cân đối riêng.

### 9.3. Database-side statement timeout

Database có thể hỗ trợ giới hạn query ở phía server. Ví dụ PostgreSQL có `statement_timeout`. Server-side timeout hữu ích khi client mất kết nối hoặc không thể gửi cancel đúng lúc, nhưng phải cấu hình theo role/session/transaction và cân nhắc query hợp lệ dài.

Một lệnh bị timeout/cancel có thể làm transaction hiện tại rơi vào trạng thái lỗi tùy database. Ứng dụng cần rollback/đóng transaction đúng cách trước khi tái sử dụng connection.

### 9.4. Spring transaction timeout không phải timeout vạn năng

`@Transactional(timeout = 3)` có thể đặt timeout cho transaction mới theo transaction manager và resource hỗ trợ. Nó không đảm bảo interrupt mọi Java code, dừng một HTTP request hoặc hủy một external side effect.

~~~java
@Transactional(timeout = 3)
public void updateOrder(Order order) {
    repository.save(order);
}
~~~

Timeout transaction thường được truyền xuống resource-aware operations khi framework/driver hỗ trợ. Hãy kiểm tra transaction manager, JDBC/JPA provider và câu lệnh thực tế; không dùng annotation thay cho query timeout hoặc socket timeout.

### 9.5. Hủy query là best effort

JDBC có `Statement.cancel()` và `Connection.setNetworkTimeout` trong API. Driver có thể gửi lệnh cancel tới database, nhưng network lỗi hoặc query đã hoàn tất có thể khiến kết quả không rõ. Khi timeout xảy ra gần commit, phải xác minh trạng thái theo idempotency key/business key trước khi chạy lại.

## 10. Timeout và transaction: caller hết giờ không có nghĩa transaction rollback

Xét một application service đồng bộ:

~~~text
HTTP caller deadline: 2 giây
       |
       v
Application service bắt đầu transaction
       |
       v
UPDATE order
       |
       v
DB chờ lock 4 giây
       |
Caller timeout sau 2 giây
       |
       +---- Thread/DB call có thể vẫn đang chạy
       |
       v
DB có thể commit sau khi caller đã bỏ cuộc
~~~

Nếu caller chỉ ngừng chờ, transaction vẫn có thể hoàn tất. Nếu framework hủy thread, driver có thể không dừng query. Nếu query bị cancel trước commit, transaction có thể rollback, nhưng phải xác minh.

### 10.1. Không chạy side effect sau khi caller timeout một cách vô chủ

Nếu request hết deadline, cần quyết định nghiệp vụ:

- Công việc không còn cần thiết: yêu cầu hủy và xác minh nó đã dừng.
- Công việc phải hoàn tất dù caller rời đi: chuyển thành job bất đồng bộ có ID/trạng thái và trả `202 Accepted`.
- Kết quả commit chưa rõ: lưu/tra cứu trạng thái theo idempotency key.
- Có thể đã tạo side effect: không retry mù quáng; reconcile hoặc dùng operation idempotent.

Đừng bắt đầu một thread detached để tiếp tục cập nhật DB sau khi HTTP request đã trả timeout mà không có cơ chế lưu trạng thái công việc và quan sát kết quả.

### 10.2. Không giữ transaction DB trong khi chờ dịch vụ bên ngoài

~~~java
@Transactional
public PaymentResult placeOrder(OrderCommand command) {
    orderRepository.save(command.toOrder());
    return paymentClient.charge(command); // Không nên chờ remote trong DB transaction.
}
~~~

Nếu payment chậm, transaction DB giữ connection/lock lâu. Nếu payment đã thành công nhưng DB rollback, hai hệ thống lệch nhau. Nếu retry toàn method, lệnh payment có thể được gửi lại.

Tách workflow: ghi trạng thái cần thiết trong transaction, gọi payment với idempotency key theo quy trình có kiểm soát, rồi cập nhật trạng thái; hoặc dùng outbox/saga khi cần điều phối nhiều bước.

### 10.3. Timeout ở transaction commit

Lỗi connection khi commit có thể khiến client không biết database đã commit hay chưa. Không suy luận “commit báo lỗi tức là rollback”. Hãy truy vấn theo business key/operation ID từ connection mới và áp dụng reconciliation.

## 11. Deadline propagation giữa các service

Một hệ thống nhiều service cần truyền **ngân sách còn lại**, không chỉ một timeout cố định.

~~~text
Ingress nhận deadline 4 giây
    |
    +-- validate/auth dùng 200 ms
    |
    v
Service A còn 3.8 giây
    |
    +-- gọi Service B, gửi remaining ~3.8 giây
    |
    v
Service B còn lại sau xử lý
    |
    +-- gọi DB với cap cục bộ và remaining
~~~

### 11.1. Header deadline là hợp đồng của hệ thống

Có thể dùng header nội bộ như `X-Request-Deadline` hoặc `X-Timeout-Ms`, nhưng phải thống nhất semantics:

- Là epoch deadline hay duration còn lại?
- Có giới hạn tối đa do server áp dụng không?
- Có trừ network/clock skew reserve không?
- Có được phép client tự đặt vô hạn không?
- Header có bị gateway xóa/ghi đè không?

Không có một HTTP header tùy ý nào tự trở thành chuẩn toàn hệ thống. Với gRPC, deadline/context có cơ chế riêng; khi chuyển qua HTTP hoặc message, cần mapping rõ.

### 11.2. Chuyển deadline wall-clock thành remaining duration

Khi nhận epoch deadline, server kiểm tra giá trị trong phạm vi cho phép rồi tính remaining. Sau đó dùng monotonic clock nội bộ để quản lý thời lượng, tránh bị thay đổi đồng hồ trong lúc xử lý.

Nếu deadline đã hết hoặc còn quá ít, trả lỗi/đưa sang async flow sớm; không khởi động thêm công việc bên ngoài.

### 11.3. Dành ngân sách cho response và ACK

Không tiêu hết deadline vào outbound request cuối cùng. Cần giữ lại thời gian cho:

- Commit/rollback transaction.
- Ghi log/metric cần thiết.
- Serialize response hoặc tạo error response.
- ACK/checkpoint message nếu adapter quản lý.
- Cleanup/release connection.

Reserve phụ thuộc latency thực tế; đo p95/p99 thay vì đặt một con số tùy ý.

## 12. Cancellation token cho công việc hợp tác

Một số tác vụ không thể bị hủy tự động. Có thể truyền một abstraction cancellation xuống các bước có khả năng kiểm tra.

~~~java
package example.functions;

public interface CancellationToken {
    boolean isCancellationRequested();

    default void throwIfCancellationRequested() {
        if (isCancellationRequested()) {
            throw new OperationCancelledException();
        }
    }
}
~~~

Exception ứng dụng có thể định nghĩa như sau:

~~~java
public class OperationCancelledException extends RuntimeException {
    public OperationCancelledException() {
        super("Operation was cancelled");
    }

    public OperationCancelledException(Throwable cause) {
        super("Operation was cancelled", cause);
    }
}
~~~

Token có thể được triển khai bằng `AtomicBoolean`, context framework hoặc cơ chế cancellation sẵn có. Executor ở ví dụ trên nên được quản lý như bean có lifecycle và shutdown khi ứng dụng dừng; không tạo pool mới cho mỗi request.

### 12.1. Kiểm tra giữa các bước

~~~java
public Result process(Input input, CancellationToken token) {
    token.throwIfCancellationRequested();

    Prepared prepared = prepare(input);

    token.throwIfCancellationRequested();

    ExternalResult external = client.call(prepared);

    token.throwIfCancellationRequested();

    return finalizeResult(external);
}
~~~

Token chỉ có tác dụng nếu code và dependency **hợp tác kiểm tra**. Nó không dừng một method đang chặn trong JDBC hoặc một remote server đã nhận request.

### 12.2. Cancellation không thay thế timeout ở I/O

Một token giúp ứng dụng quyết định không bắt đầu bước tiếp theo. Nhưng nếu đang chờ socket, phải có socket/read timeout hoặc API cancel tương ứng. Kết hợp:
- Deadline để biết còn bao nhiêu thời gian.
- Cancellation token để truyền yêu cầu dừng.
- Timeout ở client/driver để giới hạn I/O.
- Idempotency để chịu được kết quả không rõ.

### 12.3. Đừng biến cancellation thành lỗi nghiệp vụ thông thường

Cancellation thường biểu thị caller hoặc runtime không còn chờ operation. Nó khác validation error và khác transient service failure. Không retry tự động một operation chỉ vì bị cancel; trước hết cần biết side effect đã xảy ra chưa và ai còn chịu trách nhiệm hoàn tất.

## 13. Áp dụng timeout trong Spring Cloud Function

Một Function có thể nhận input, tính kết quả và gọi dependency. Tuy nhiên, `FunctionCatalog` không tự cung cấp một deadline tổng cho mọi Function.

### 13.1. FunctionCatalog không phải timeout manager

`catalog.lookup("chargePayment")` tìm bean theo tên và kiểu phù hợp. Nó không tự:
- Đặt timeout cho JDBC, HTTP client hoặc broker client.
- Hủy thread đang chạy.
- Gửi cancellation tới server ngoài.
- Giới hạn thời gian toàn pipeline composition.
- Đảm bảo transaction rollback khi caller timeout.

Timeout phải được đặt ở **boundary biết loại công việc**: HTTP client cho outbound HTTP, JDBC/driver cho query, transaction manager cho transaction, adapter cho invocation/message lifecycle.

### 13.2. Giữ Function thuần và đặt deadline ở application boundary

~~~java
@Bean
Function<OrderCommand, Quote> calculateQuote() {
    return command -> new Quote(
            command.orderId(),
            command.quantity(),
            Math.multiplyExact(command.quantity(), 125_000L));
}
~~~

Hàm tính toán thuần không cần timeout I/O. Nếu một workflow gọi dịch vụ ngoài, có thể tạo application service riêng:

Record trung gian dưới đây là một kiểu domain minh họa:

~~~java
public record PricedOrder(OrderCommand command, Price price) {}
~~~

~~~java
@Service
public class QuoteApplicationService {

    private final Function<PricedOrder, Quote> calculate;
    private final PricingClient pricingClient;

    public QuoteApplicationService(
            Function<PricedOrder, Quote> calculate,
            PricingClient pricingClient) {
        this.calculate = calculate;
        this.pricingClient = pricingClient;
    }

    public Mono<Quote> quote(OrderCommand command) {
        return pricingClient.fetchPrice(command.sku())
                .timeout(Duration.ofMillis(800))
                .map(price -> calculate.apply(
                        new PricedOrder(command, price)))
                .timeout(Duration.ofSeconds(2));
    }
}
~~~

Đây là ví dụ minh họa; `PricingClient` trả `Mono<Price>`, còn `PricedOrder` là record domain được khai báo trong ứng dụng. Timeout 800 ms giới hạn bước pricing; timeout 2 giây bao Publisher workflow. Nếu pricing timeout, Reactor phát lỗi và hủy subscription upstream theo khả năng của client.

### 13.3. Message<T> có thể mang metadata deadline

Spring Cloud Function có thể làm việc với Spring Message. Adapter có thể đọc header deadline/trace rồi chuyển thành một context ứng dụng. Tuy nhiên, không nên để domain Function phụ thuộc trực tiếp vào một header transport tùy ý.

Một lựa chọn là truyền rõ context:

~~~java
public record ExecutionContext(
        Instant deadline,
        String correlationId) {}

public record CommandEnvelope<T>(
        T payload,
        ExecutionContext context) {}
~~~

Adapter ánh xạ metadata HTTP/message/serverless vào `ExecutionContext`. Application service tính remaining budget và truyền xuống client. Khi cần tái sử dụng lõi thuần, giữ context ở workflow boundary thay vì nhúng mọi header vào domain model.

### 13.4. Composition không tự cộng deadline

`validateOrder|calculateQuote|chargePayment` chỉ mô tả thứ tự composition. Nếu từng Function có timeout 2 giây, tổng pipeline vẫn có thể vượt 2 giây. Hãy đặt một deadline tổng ở workflow và timeout riêng cho outbound call; mỗi bước dùng ngân sách còn lại.

## 14. Supplier, Function và Consumer với tác vụ bên ngoài

### 14.1. Supplier có thể bị chặn khi lấy dữ liệu

Một `Supplier<OrderCommand>` có thể poll nguồn ngoài:

~~~java
@Bean
Supplier<OrderCommand> pollOrder(QueueClient queue) {
    return () -> queue.pollNext();
}
~~~

Nếu `pollNext` chờ vô hạn, thread kích hoạt Supplier có thể bị giữ mãi. Đặt poll timeout/long-poll duration tại client nguồn và một deadline cho lần gọi Supplier. Không dùng timeout của HTTP adapter để thay thế timeout của queue client.

Nếu Supplier lấy một message rồi trả về, cancellation của caller sau đó không tự đưa message về queue. Cần semantics visibility/lease/ack của nguồn.

### 14.2. Function gọi dịch vụ ngoài

~~~java
@Bean
Function<OrderCommand, Mono<EnrichedOrder>> enrich(
        InventoryClient inventory) {
    return command -> inventory.lookup(command.sku())
            .timeout(Duration.ofSeconds(1))
            .map(stock -> new EnrichedOrder(command, stock));
}
~~~

Function reactive trả Publisher; adapter phải subscribe/quan sát completion theo contract. Timeout phát lỗi nếu inventory không phản hồi đúng hạn. Nếu server inventory đã xử lý nhưng response mất, retry cần idempotency hoặc thao tác read-only phù hợp.

### 14.3. Consumer cần hoàn tất side effect trước khi trả

~~~java
@Bean
Consumer<OrderCreated> saveOrder(OrderApplicationService service) {
    return service::handle;
}
~~~

Với Consumer imperative, method `handle` cần hoàn tất transaction trước khi trả về nếu binder dựa vào invocation completion để ACK. Nếu method chỉ khởi chạy tác vụ async rồi return, adapter có thể ACK trước khi DB commit.

Với reactive consumer, dùng chữ ký và lifecycle mà binder hỗ trợ; không tự subscribe rồi bỏ terminal signal.

### 14.4. Đừng đặt timeout trong một Function thuần chỉ để cắt caller

Một phép tính CPU-bound thuần có thể chạy lâu, nhưng timeout của caller không tự dừng vòng lặp Java. Nếu cần giới hạn CPU, kiểm tra deadline/cancellation token theo từng batch hoặc chia nhỏ công việc; tránh để một tác vụ CPU vô hạn chiếm worker.

## 15. Messaging: thời gian xử lý và visibility/lease

Một message broker có thể có thời gian visibility, lock hoặc delivery lease. Nếu consumer xử lý lâu hơn khoảng thời gian này, broker có thể giao lại message trong khi consumer đầu tiên vẫn đang chạy.

~~~text
Broker giao message cho Consumer A
        |
        v
Consumer A xử lý DB 45 giây
        |
Visibility/lease hết sau 30 giây
        |
        v
Broker giao cùng message cho Consumer B
        |
        +-- A vẫn chạy
        +-- B cũng xử lý
~~~

Cả hai có thể cùng thực hiện side effect. Inbox/unique constraint ngăn ghi trùng ở storage, nhưng contention và duplicate work vẫn tiêu tốn tài nguyên.

### 15.1. Ngân sách xử lý phải nằm trong delivery lease

Đặt deadline xử lý ngắn hơn visibility/lease timeout đủ để commit và ACK. Nếu công việc hợp lệ dài hơn lease, dùng cơ chế gia hạn visibility/lease/heartbeat của broker hoặc chuyển sang job bất đồng bộ có trạng thái.

Không giả định mọi binder hỗ trợ gia hạn lease bằng một API chung.

### 15.2. Kafka: max poll interval và consumer liveness

Với Kafka consumer, thời gian giữa các lần poll và các timeout session/heartbeat ảnh hưởng tới membership và rebalance. Nếu xử lý record lâu hơn giới hạn cấu hình như `max.poll.interval.ms`, consumer có thể bị coi là không còn tiến triển và partition được giao lại.

Tăng timeout chỉ che được một số workload dài; nó không thay thế bounded processing, pause/resume, concurrency có kiểm soát và idempotency. Cần kiểm tra property của Kafka client/binder đang dùng.

### 15.3. RabbitMQ và message acknowledgement timeout

Rabbit consumer có thể bị ảnh hưởng bởi timeout ACK, channel/connection và requeue. Nếu consumer giữ message quá lâu mà không ACK, broker hoặc client có thể đóng channel theo cấu hình/version và message có thể được giao lại.

Kiểm tra prefetch, concurrency, consumer timeout, retry và dead-letter policy. Không lấy delivery tag làm business key.

### 15.4. Không ACK chỉ vì timeout của caller

Nếu application service timeout nhưng trạng thái DB chưa rõ, đừng bắt lỗi rồi trả bình thường cho Consumer. Nếu transaction đã commit, inbox giúp lần giao lại no-op; nếu chưa commit, adapter cần nhận lỗi để retry/DLQ theo policy.

## 16. Serverless: deadline của invocation

Serverless runtime thường đặt giới hạn thời gian cho một invocation. Khi hết thời gian, nền tảng có thể dừng runtime, hủy execution hoặc gọi lại event tùy trigger. Những semantics này không đồng nhất giữa cloud provider và loại event source.

### 16.1. Dùng thời gian còn lại từ runtime

Một adapter serverless nên lấy remaining execution time từ context API mà nền tảng cung cấp (nếu có), sau đó:
- Trừ thời gian cleanup/response.
- Giới hạn outbound HTTP/DB timeout theo remaining.
- Không bắt đầu retry mới nếu không còn ngân sách.
- Ghi trạng thái job nếu công việc phải tiếp tục sau invocation.

Không hard-code một giá trị timeout cố định lớn hơn thời gian runtime cho phép.

### 16.2. Invocation timeout không rollback remote side effect

~~~text
Serverless handler gửi lệnh tạo payment
          |
          v
Payment provider chấp nhận
          |
          v
Handler vượt deadline, runtime dừng
          |
          v
Trigger gọi lại event
          |
          v
Lệnh payment có thể được gửi lần nữa
~~~

Dùng provider idempotency key ổn định theo operation, tra cứu trạng thái payment và thiết kế reconciliation. Không dùng memory của invocation trước để chống trùng.

### 16.3. Chuyển công việc dài sang async job

Nếu công việc thường xuyên vượt thời gian invocation, không kéo dài timeout đến mức tối đa một cách máy móc. Có thể nhận event, ghi job/outbox, trả trạng thái accepted và để worker có lifecycle riêng xử lý; client tra cứu trạng thái bằng operation ID.

## 17. Kết hợp timeout với retry

Timeout thường là lỗi có thể retry, nhưng không phải timeout nào cũng an toàn. Nếu thao tác là read-only, retry có thể phù hợp. Nếu thao tác đã tạo payment/order hoặc gửi email, cần idempotency trước khi retry.

### 17.1. Per-attempt timeout và overall deadline trong Reactor

~~~java
Mono<PaymentResult> payment =
        Mono.defer(() -> paymentClient.charge(command))
            .timeout(Duration.ofMillis(700))
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                    .filter(error ->
                        error instanceof TimeoutException
                        || error instanceof TemporaryPaymentException))
            .timeout(Duration.ofSeconds(2));
~~~

Giả sử `paymentClient.charge` trả `Mono<PaymentResult>` lạnh và gửi cùng idempotency key trong `command`:

- Timeout 700 ms giới hạn từng attempt.
- `Retry.backoff(2, ...)` cho tối đa hai lần retry thêm.
- Timeout ngoài 2 giây giới hạn toàn chuỗi, gồm attempts và backoff.
- `Mono.defer` tạo lại lời gọi cho mỗi subscription/retry nếu client method tạo Publisher mới.
- Nếu payment provider đã nhận lệnh nhưng response timeout, provider phải hỗ trợ idempotency hoặc service cần tra cứu trạng thái trước khi gửi lại.

Không cộng thời gian retry vào deadline vô hạn. Outer timeout có thể kết thúc caller trước khi retry budget dùng hết.

### 17.2. Không retry nếu remaining budget quá thấp

Trước mỗi attempt, kiểm tra deadline còn lại. Nếu chỉ còn 50 ms trong khi connect timeout tối thiểu là 200 ms, bắt đầu request mới thường chỉ làm tăng tải và chắc chắn không kịp response.

Retry policy nên:
- Giới hạn số attempts.
- Dùng backoff/jitter phù hợp.
- Không vượt deadline tổng.
- Không retry lỗi validation/conflict.
- Dùng idempotency cho thao tác có side effect.
- Để một phần ngân sách cho response/ACK.

### 17.3. Timeout và circuit breaker

Nếu dependency đang quá tải, retry ngay có thể làm tình hình tệ hơn. Circuit breaker có thể từ chối nhanh khi tỷ lệ lỗi vượt ngưỡng; concurrency limit và bulkhead ngăn một dependency chiếm hết worker.

Timeout là giới hạn thời gian; circuit breaker là quyết định có gửi request hay không. Hai cơ chế bổ sung nhau nhưng không thay thế idempotency.

## 18. Timeout sau side effect: trạng thái có thể không rõ

Một request tạo payment có thể timeout ở nhiều thời điểm:

~~~text
A. Trước khi request tới provider
   → Có thể chưa có side effect.

B. Provider nhận request, chưa xử lý xong
   → Trạng thái đang xử lý.

C. Provider đã commit payment, response bị mất
   → Payment đã tạo dù caller timeout.

D. Provider trả response, client mất kết nối trước khi nhận
   → Caller không biết kết quả.
~~~

Không thể phân biệt chắc chắn A/B/C/D chỉ từ `TimeoutException` ở caller.

### 18.1. Dùng idempotency key ổn định

Một operation nên có ID ổn định, ví dụ `paymentOperationId`. Mọi retry dùng cùng key; không tạo UUID mới trong mỗi attempt.

~~~text
charge(key=pay-901) → response timeout
charge(key=pay-901) → provider trả kết quả cũ
~~~

Nếu provider hỗ trợ idempotency, xác minh phạm vi key, thời gian retention và cách xử lý cùng key nhưng payload khác. Nếu không hỗ trợ, lưu trạng thái operation và truy vấn/reconcile theo mã tham chiếu trước khi gửi lại.

### 18.2. Query trạng thái trước khi quyết định retry

~~~text
Timeout từ payment provider
       |
       v
Tra cứu operationId
       |
       +-- SUCCEEDED → ghi nhận thành công
       |
       +-- FAILED_FINAL → kết thúc thất bại
       |
       +-- PROCESSING → chờ/poll theo deadline
       |
       +-- NOT_FOUND → có thể gửi lại theo policy
       |
       +-- UNKNOWN → giữ trạng thái cần đối soát
~~~

`NOT_FOUND` chỉ có ý nghĩa nếu provider đảm bảo tra cứu nhất quán và đủ dữ liệu để kết luận. Một hệ thống eventual consistency có thể chưa hiển thị payment vừa tạo; đừng gửi lại ngay chỉ vì lần tra cứu đầu không thấy.

### 18.3. Không biến timeout thành FAILED chắc chắn

Nếu caller timeout nhưng provider có thể đã commit, trạng thái nội bộ nên biểu diễn `UNKNOWN` hoặc `PENDING_RECONCILIATION` thay vì `FAILED`. Điều này giúp tránh gửi lệnh bù trừ hoặc thanh toán lần nữa dựa trên giả định sai.

## 19. Cancellation và compensation là hai cơ chế khác nhau

Cancellation yêu cầu một tác vụ đang chạy dừng. Compensation là một thao tác nghiệp vụ mới nhằm khôi phục trạng thái sau khi side effect trước đó đã xảy ra.

Ví dụ:
- Hủy một HTTP request đang chờ response là cancellation.
- Hoàn tiền sau khi payment đã capture là compensation.
- Hủy subscription của Reactor không tự tạo refund.
- Rollback DB không thể thu hồi email đã gửi hoặc message đã publish.

### 19.1. Khi nào cần compensation?

Nếu workflow gồm nhiều bước không thể nằm trong một transaction:

~~~text
Create order
    |
    v
Reserve inventory
    |
    v
Charge payment
    |
    v
Confirm order
~~~

Nếu charge payment thành công nhưng bước confirm thất bại, workflow có thể cần release inventory hoặc refund. Đây là saga/compensation theo quy tắc nghiệp vụ; timeout chỉ là một tín hiệu khiến trạng thái cần được kiểm tra.

### 19.2. Compensation cũng có thể timeout

Lệnh refund có thể timeout sau khi provider đã thực hiện. Compensation phải có operation ID/idempotency key riêng, trạng thái theo dõi và reconciliation; không retry mù quáng vì “đó là bước hoàn tác”.

### 19.3. Cancellation không thay thế cleanup

Khi hủy task, vẫn cần giải phóng tài nguyên cục bộ: connection, file, lock, subscription và executor task. Dùng try-with-resources, `finally` hoặc cancellation hook phù hợp. Không giữ resource vô thời hạn khi caller đã hết deadline.




## 20. Timeout trong HTTP inbound và outbound

### 20.1. Inbound timeout không tự giới hạn service method

HTTP server/gateway có thể dừng chờ response sau một khoảng thời gian. Nhưng application thread hoặc outbound call có thể vẫn chạy. Đặt deadline ở request boundary rồi truyền remaining budget xuống service/client.

### 20.2. Outbound timeout cần nằm ở outbound client

Nếu Function gọi WebClient, cấu hình timeout ở WebClient/Reactor Netty. Nếu gọi RestClient/RestTemplate, cấu hình request factory/client tương ứng. Nếu gọi SDK, dùng timeout của SDK. Không chỉ đặt timeout trên inbound controller rồi kỳ vọng mọi client downstream tự dừng.

### 20.3. Response timeout không giống socket inactivity timeout

Một client có thể có:
- Connection acquisition timeout.
- Connect timeout.
- TLS handshake timeout.
- Response/read timeout.
- Write timeout.
- Overall Publisher/request deadline.

Đọc đúng semantics từng property của thư viện. Một read timeout có thể là giới hạn thời gian không nhận dữ liệu giữa hai lần đọc, không phải giới hạn tổng thời gian server xử lý.

## 21. Timeout trong broker và serverless: đồng bộ các giới hạn

Một consumer cần đảm bảo thời gian xử lý phù hợp với delivery lease/visibility timeout. Nếu message bị giao lại khi consumer đầu vẫn đang xử lý, hai worker có thể cùng chạy.

~~~text
Processing deadline < visibility/lease timeout
       |
       +-- đủ thời gian commit
       +-- đủ thời gian ACK
       +-- có reserve cho network jitter
~~~

Nếu workload có thể dài hơn lease, dùng heartbeat/extend visibility nếu broker hỗ trợ hoặc chuyển sang job bền vững. Không tăng lease vô hạn vì consumer chết có thể làm message bị giữ quá lâu.

Với serverless, overall deadline phải nhỏ hơn invocation limit và chừa cleanup/response. Nếu trigger có retry, tổng số lần xử lý còn bao gồm reinvocation; idempotency phải bao phủ toàn bộ.

### 21.1. Deadline và retry broker

Binder retry có thể tạo nhiều lần xử lý trong một delivery; broker redelivery có thể tạo lần nhận mới. Đừng chỉ đếm retry trong application. Observability cần phân biệt attempt trong Function, delivery count của broker (nếu có) và invocation count của serverless.

### 21.2. Batch processing

Với batch message, deadline tổng cần phân bổ cho từng record. Nếu record cuối làm hết thời gian, binder có thể retry cả batch tùy semantics; những record đã commit cần idempotency riêng. Dùng partial batch response/checkpoint khi nền tảng hỗ trợ.

## 22. Quản lý thread và connection khi timeout hàng loạt

Khi dependency chậm, timeout làm caller trả lỗi nhưng task bên dưới vẫn chạy có thể dẫn tới **resource leak về mặt tải**: request mới tiếp tục vào trong khi task cũ chưa dừng.

Cần theo dõi:
- Số request đang chờ dependency.
- Số task đã timeout nhưng vẫn còn chạy.
- Thread pool active/queue/rejected count.
- Connection pool active/idle/pending acquire.
- Query đang chạy lâu và lock wait.
- Cancellation request và cancellation thực sự quan sát được.
- Tỷ lệ timeout theo dependency/operation.

### 22.1. Bulkhead và giới hạn queue

Executor/pool nên có giới hạn. Khi queue đầy, từ chối sớm bằng lỗi quá tải có thể tốt hơn nhận thêm công việc rồi để tất cả timeout. Đặt giới hạn riêng cho dependency chậm để nó không chiếm toàn bộ thread/connection của ứng dụng.

### 22.2. Không tạo executor mới cho mỗi request

Tạo một thread pool cho từng request khiến số thread không kiểm soát. Dùng executor bean quản lý lifecycle, giới hạn worker/queue và shutdown đúng khi ứng dụng dừng.

### 22.3. Timeout không giải phóng connection nếu driver vẫn chạy

Nếu JDBC query bị timeout ở HTTP layer nhưng driver tiếp tục query, connection vẫn bị chiếm. Cần query/network timeout phía driver/database và kiểm tra connection được trả pool an toàn sau lỗi.

## 23. Kiểm thử timeout và cancellation

Một test tốt phải phân biệt:
1. Caller đã nhận timeout.
2. Cancellation đã được phát.
3. Upstream có quan sát cancellation.
4. Side effect đã xảy ra hay chưa.

Chỉ assert `expectError(TimeoutException.class)` chưa đủ nếu mục tiêu là kiểm tra cancellation.

### 23.1. StepVerifier xác minh timeout hủy upstream

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutCancellationTest {

    @Test
    void timeoutCancelsUpstreamSubscription() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Mono<String> source = Mono.<String>never()
                .doOnCancel(() -> cancelled.set(true));

        StepVerifier.withVirtualTime(() ->
                    source.timeout(Duration.ofSeconds(2)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(2))
                .expectError(java.util.concurrent.TimeoutException.class)
                .verify();

        assertTrue(cancelled.get());
    }
}
~~~

`Mono.never` không tạo I/O thật, nhưng kiểm tra được operator timeout gửi cancellation upstream khi timer thắng. Test này **không chứng minh** một JDBC driver hoặc server ngoài đã dừng.

### 23.2. Test cancellation do subscriber chủ động

~~~java
@Test
void subscriberCancellationReachesSource() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Mono<String> source = Mono.<String>never()
            .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(source)
            .thenCancel()
            .verify();

    assertTrue(cancelled.get());
}
~~~

Ở đây không có timeout; subscriber chủ động cancel. Hai trường hợp cần được đo riêng trong metrics vì nguyên nhân và cách phản ứng có thể khác.

### 23.3. Test retry timeout có giới hạn

~~~java
@Test
void timeoutRetryStopsAtConfiguredAttempts() {
    AtomicInteger calls = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.<String>never();
    });

    StepVerifier.withVirtualTime(() ->
                source.timeout(Duration.ofSeconds(1))
                    .retryWhen(Retry.max(2)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectError()
            .verify();

    assertEquals(3, calls.get());
}
~~~

Test minh họa một lần đầu cộng hai retry. Trong test thật, thêm bộ lọc exception và deadline tổng; xác minh số attempts chứ không chỉ trạng thái terminal.

### 23.4. Kiểm thử WebClient với server giả lập

Dùng MockWebServer/WireMock hoặc một HTTP test server để:
- Trì hoãn response vượt timeout.
- Đóng connection giữa response.
- Trả response ngay sát deadline.
- Trả 5xx hoặc 429 theo policy.
- Ghi nhận request count và idempotency key qua retry.

Một test client timeout chỉ chứng minh client ngừng chờ theo cấu hình. Nếu server đã nhận request, test phải kiểm tra side effect server-side hoặc tra cứu operation status; không suy luận server đã dừng chỉ vì socket đóng.

### 23.5. Kiểm thử JDBC/database timeout

Với database integration test, tạo query chờ lock hoặc query có thời lượng kiểm soát, đặt query/transaction timeout rồi xác minh:
- Exception được truyền về application.
- Transaction rollback đúng theo database/driver.
- Connection được trả pool an toàn.
- Không còn query tiếp tục chiếm tài nguyên ngoài ý muốn.
- Nếu commit outcome không rõ, tra cứu bằng operation key từ connection mới.

Một unit test mock repository ném `TimeoutException` không xác minh được behavior của JDBC driver.

### 23.6. Test timeout sau commit

Mô phỏng:
1. Transaction ghi dữ liệu và commit.
2. Test harness làm mất response/ACK trước khi caller quan sát.
3. Caller timeout hoặc broker giao lại.
4. Cùng operation ID được gửi lần nữa.
5. Assert chỉ có một business effect và trạng thái cũ được tra cứu.

Đây là test quan trọng để chứng minh timeout không dẫn tới side effect trùng.

## 24. Quan sát timeout và cancellation trong production

Nên phân biệt timeout ở caller, cancellation được gửi và tác vụ thực sự kết thúc.

Metric/log gợi ý:

| Metric/trường | Ý nghĩa |
|---|---|
| `request_deadline_remaining_ms` | Ngân sách còn lại khi bắt đầu một bước |
| `dependency_timeout_total` | Số lần dependency timeout |
| `operation_cancel_requested_total` | Số yêu cầu cancellation |
| `operation_cancel_observed_total` | Số task/Publisher quan sát cancellation |
| `operation_completed_after_caller_timeout_total` | Tác vụ kết thúc sau khi caller đã timeout |
| `outbound_inflight` | Số lời gọi ngoài đang chạy |
| `executor_queue_depth` | Công việc đang chờ trong executor |
| `connection_pool_pending` | Request chờ connection |
| `db_query_duration` | Thời gian thực thi query |
| `message_processing_duration` | Thời gian xử lý message |
| `message_redelivery_total` | Lượt giao lại nếu adapter cung cấp |
| `timeout_after_commit_total` | Số trường hợp đã commit nhưng caller/ACK timeout nếu quan sát được |

Tên metric là gợi ý của ứng dụng, không phải metric mặc định của Spring Cloud Function.

### 24.1. Ghi rõ timeout ở phase nào

Một log chỉ ghi `TimeoutException` không đủ để điều tra. Hãy ghi operation, dependency, phase (pool/connect/read/query/overall), deadline còn lại, attempt, correlation ID và trạng thái commit nếu biết.

Không log token, payload nhạy cảm hoặc thông tin thanh toán. Dùng trace ID để nối các hop và tránh ghi cùng stack trace ở mọi tầng.

### 24.2. Alert theo dấu hiệu cạn tài nguyên

Timeout tăng đồng thời với connection pool pending, executor queue và outbound inflight tăng có thể chỉ ra dependency chậm khiến task cũ chưa dừng. Nếu caller đã trả lỗi nhưng tác vụ vẫn chạy, hệ thống có thể tiếp tục tiêu thụ tài nguyên và timeout thêm request mới.

Theo dõi p95/p99 latency, số task quá deadline còn sống, query lâu, pool saturation và tỷ lệ cancellation được quan sát so với cancellation được yêu cầu.

## 25. Một helper deadline dùng monotonic clock

Khi nhiều bước cần dùng cùng ngân sách, tạo một đối tượng deadline để tránh mỗi tầng tự đặt timeout mới.

~~~java
package example.functions;

import java.time.Duration;

public final class Deadline {

    private final long expiresAtNanos;

    private Deadline(long expiresAtNanos) {
        this.expiresAtNanos = expiresAtNanos;
    }

    public static Deadline after(Duration budget) {
        if (budget.isNegative() || budget.isZero()) {
            throw new IllegalArgumentException(
                    "Budget must be positive");
        }
        return new Deadline(System.nanoTime() + budget.toNanos());
    }

    public Duration remaining() {
        long nanos = expiresAtNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0, nanos));
    }

    public boolean isExpired() {
        return remaining().isZero();
    }

    public Duration timeoutFor(
            Duration localCap, Duration responseReserve) {

        Duration usable = remaining().minus(responseReserve);

        if (usable.isNegative() || usable.isZero()) {
            throw new DeadlineExceededException();
        }

        return usable.compareTo(localCap) < 0
                ? usable
                : localCap;
    }
}
~~~

`DeadlineExceededException` là exception ứng dụng tự định nghĩa. Helper trên dành cho **một process** vì dùng `System.nanoTime`. Không serialize giá trị `expiresAtNanos` sang service khác; monotonic clock của hai process không cùng mốc.

### 25.1. Truyền deadline qua nhiều bước

~~~java
public Mono<PaymentResult> charge(
        PaymentCommand command, Deadline deadline) {

    Duration timeout = deadline.timeoutFor(
            Duration.ofMillis(700),
            Duration.ofMillis(100));

    return paymentClient.charge(command)
            .timeout(timeout);
}
~~~

Trước mỗi outbound call, tính lại remaining. Nếu bước trước đã dùng gần hết ngân sách, bước sau tự nhận timeout ngắn hơn hoặc bị từ chối trước khi bắt đầu.

### 25.2. Không nhầm deadline với timeout mặc định

Một deadline là trạng thái của **một operation cụ thể**. Không lưu deadline request vào singleton field dùng chung giữa các request; mỗi invocation cần context riêng. Không chia sẻ mutable deadline giữa các message độc lập.

## 26. Những lỗi thiết kế thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ đặt timeout ở API gateway | Downstream vẫn tiếp tục chạy | Truyền deadline và đặt timeout ở outbound client |
| Nghĩ timeout nghĩa là task đã dừng | Task cũ vẫn giữ thread/connection | Theo dõi cancellation và timeout tại driver |
| Dùng `Future.cancel(true)` rồi coi đã hủy | Blocking I/O có thể bỏ qua interrupt | Dùng client/driver cancellation và query timeout |
| Dùng `completeOnTimeout` cho payment | Trả fallback trong khi payment có thể đã commit | Trạng thái UNKNOWN, idempotency và tra cứu |
| Dùng `Mono.timeout` cho toàn bộ Flux để giới hạn tổng tuổi thọ | Có thể chỉ phát hiện idle giữa các phần tử | Deadline tổng/giới hạn duration đúng semantics |
| Dùng read timeout như overall deadline | Stream liên tục vẫn có thể chạy lâu | Thêm deadline tổng |
| Retry timeout mà không có idempotency | Tạo side effect trùng | Key ổn định và storage/provider dedupe |
| Transaction DB bao quanh HTTP call dài | Giữ lock/connection, không atomic với remote | Outbox/saga hoặc workflow nhiều bước |
| ACK trước commit | Message có thể mất khi DB rollback | Commit trước ACK, inbox cho redelivery |
| Fire-and-forget trong Consumer | Binder có thể ACK trước completion | Trả/đợi completion theo adapter contract |
| Timeout từng bước bằng nhau | Tổng thời gian vượt deadline caller | Phân bổ remaining budget |
| Retry lồng nhiều tầng | Thời gian và số lần gọi tăng ngoài dự kiến | Một retry owner chính và overall deadline |
| Executor không giới hạn | Thread/queue tăng khi dependency chậm | Bulkhead, bounded queue và rejection |
| Hủy bằng cờ nhưng code không kiểm tra | Cancellation không có tác dụng | Hợp tác kiểm tra token/interrupt |
| Coi cancel là rollback | Remote side effect có thể đã commit | Reconcile/compensation |
| Timeout transaction là timeout mọi I/O | Driver/socket vẫn có thể chờ | Timeout pool, connect, query và network riêng |

### 26.1. Anti-pattern: timeout rồi trả success giả

~~~java
try {
    return paymentClient.charge(command);
} catch (TimeoutException ex) {
    return PaymentResult.success(command.operationId());
}
~~~

Mã này biến “không biết kết quả” thành “thành công”. Nếu provider chưa xử lý, hệ thống báo sai; nếu provider đã xử lý, kết quả cần được tra cứu. Trả một trạng thái `PENDING`/`UNKNOWN` có ý nghĩa hơn nếu API hỗ trợ.

### 26.2. Anti-pattern: đặt timeout thấp hơn khả năng xử lý hợp lệ

Timeout quá ngắn làm các request hợp lệ liên tục bị hủy, tăng retry và tải. Chọn timeout theo phân bố latency, SLA, deadline caller và ngân sách tài nguyên; theo dõi p95/p99 và tỷ lệ timeout thay vì chỉ chọn một con số đẹp.

### 26.3. Anti-pattern: timeout cao để che dependency bị treo

Timeout rất dài làm connection, thread và message lease bị giữ lâu. Điều tra nguyên nhân, giới hạn concurrency và có circuit breaker/bulkhead khi cần; không chỉ tăng timeout để hết alert.

## 27. Checklist trước khi đưa production

### 27.1. Deadline và timeout

- [ ] Có deadline tổng cho operation/request.
- [ ] Timeout từng bước được phân bổ theo remaining budget.
- [ ] Có reserve cho commit, response, ACK và cleanup.
- [ ] Connection pool, connect, read/write, query và transaction có giới hạn phù hợp.
- [ ] Retry/backoff nằm trong overall deadline.
- [ ] Deadline từ client được validate và giới hạn local cap.

### 27.2. Cancellation

- [ ] Biết cancellation được phát ở tầng nào.
- [ ] Biết client/driver/Publisher có hỗ trợ cancel đến đâu.
- [ ] Interrupt không bị nuốt; code blocking có hợp tác.
- [ ] Không fire-and-forget rồi coi invocation đã hoàn tất.
- [ ] Resource được giải phóng khi cancel/timeout.
- [ ] Có metric phân biệt cancellation requested và observed.

### 27.3. Transaction và side effect

- [ ] Caller timeout không bị coi là bằng chứng transaction rollback.
- [ ] Timeout gần commit có cách tra cứu trạng thái.
- [ ] Side effect có idempotency key ổn định.
- [ ] Không giữ DB transaction quanh remote call dài.
- [ ] Broker ACK chỉ sau completion/commit theo contract binder.
- [ ] Compensation là operation có trạng thái/key riêng.
- [ ] Công việc dài được chuyển sang job bền vững khi cần.

### 27.4. Kiểm thử và vận hành

- [ ] Test timeout và cancellation riêng biệt.
- [ ] Test timeout per-attempt và deadline tổng.
- [ ] Test client timeout khi server đã nhận request.
- [ ] Test query timeout bằng database/driver thật.
- [ ] Test commit rồi mất response/ACK.
- [ ] Test message lease/visibility hết hạn trong khi consumer đang chạy.
- [ ] Theo dõi task còn chạy sau caller timeout.
- [ ] Có metric pool saturation, retry, redelivery và operation UNKNOWN.
- [ ] Test shutdown và cleanup khi task đang bị hủy.

## 28. Bài tập thực hành

**Bài 1 — Timeout hay deadline?** Một request có deadline 2 giây và gọi ba dependency tuần tự, mỗi dependency timeout 2 giây. Vì sao request có thể mất gần 6 giây? Hãy phân bổ remaining budget.

**Bài 2 — Future.cancel.** `future.get(1, SECONDS)` ném TimeoutException rồi code gọi `future.cancel(true)`. Điều gì được đảm bảo và điều gì không?

**Bài 3 — CompletableFuture.** Phân biệt `orTimeout` và `completeOnTimeout`. Vì sao cả hai không tự chứng minh external request đã dừng?

**Bài 4 — Reactor Mono.** `Mono.timeout(Duration.ofSeconds(1))` phát tín hiệu nào khi không có kết quả? Cancellation được truyền tới đâu và giới hạn ở đâu?

**Bài 5 — Reactor Flux.** Vì sao `Flux.timeout(Duration)` có thể là idle timeout chứ không phải deadline tổng? Khi nào `take(Duration)` có semantics khác?

**Bài 6 — HTTP.** Một WebClient có connection pool timeout, connect timeout, response timeout và `Mono.timeout` tổng. Hãy nêu vai trò của từng loại.

**Bài 7 — JDBC.** Vì sao Hikari connectionTimeout không giới hạn thời gian SQL chạy? Cần cấu hình thêm những timeout nào?

**Bài 8 — Transaction.** HTTP caller timeout sau 2 giây nhưng DB query commit ở giây thứ 3. Caller có thể kết luận gì? Hệ thống nên làm gì khi request được gửi lại?

**Bài 9 — Retry.** Một lệnh payment timeout sau khi provider đã capture. Vì sao retry cùng lệnh có thể nguy hiểm? Thiết kế idempotency/reconciliation.

**Bài 10 — Deadline propagation.** Service A đã dùng 800 ms trong deadline 2 giây. Service B nên nhận timeout 2 giây hay remaining budget? Vì sao cần response reserve?

**Bài 11 — Supplier.** Một Supplier poll queue với long-poll 20 giây nhưng invocation chỉ còn 3 giây. Cần giới hạn bước poll ra sao?

**Bài 12 — Consumer.** Một Consumer khởi chạy CompletableFuture ghi DB rồi return. Binder có thể ACK lúc nào? Cách sửa?

**Bài 13 — Message lease.** Visibility timeout là 30 giây nhưng consumer có thể xử lý 45 giây. Hai consumer có thể cùng chạy không? Cần cơ chế gì?

**Bài 14 — Serverless.** Invocation timeout sau khi payment provider chấp nhận giao dịch. Tại sao lần reinvocation cần dùng operation ID cũ?

**Bài 15 — Cancellation và compensation.** Phân biệt cancel HTTP request với refund payment đã capture. Vì sao refund cũng cần idempotency?

**Bài 16 — StepVerifier.** Viết test xác nhận timeout phát TimeoutException và upstream nhận cancel. Vì sao test Mono.never không chứng minh JDBC đã dừng?

**Bài 17 — Metrics.** Đề xuất các metric phân biệt timeout caller, cancellation requested, cancellation observed và task completed after timeout.

**Bài 18 — FunctionCatalog.** Vì sao composition `validate|calculate|charge` không tự có deadline tổng? Deadline nên được quản lý ở đâu?

### Gợi ý đáp án

- **Bài 1:** Timeout từng dependency có thể cộng dồn; mỗi bước phải dùng remaining budget của deadline tổng.
- **Bài 2:** Caller ngừng chờ và Future nhận yêu cầu cancel; task chỉ dừng nếu hỗ trợ interrupt/cancel. I/O ngoài có thể tiếp tục.
- **Bài 3:** `orTimeout` hoàn tất future bằng lỗi timeout; `completeOnTimeout` hoàn tất bằng fallback. Underlying work có thể tiếp tục.
- **Bài 4:** Mono phát lỗi timeout và hủy upstream subscription; adapter/driver/server có thể không dừng side effect đã commit.
- **Bài 5:** Timeout của Flux có thể theo khoảng chờ tín hiệu tiếp theo; `take(Duration)` kết thúc bình thường sau khoảng thời gian, không nhất thiết phát lỗi timeout.
- **Bài 6:** Pool timeout chờ connection, connect timeout thiết lập kết nối, response timeout theo semantics đọc response, Mono timeout giới hạn caller chờ toàn Publisher.
- **Bài 7:** Hikari giới hạn lấy connection từ pool; cần driver connect/socket, statement/query và transaction timeout phù hợp.
- **Bài 8:** Caller chỉ biết response timeout; DB có thể đã commit. Tra cứu theo operation key hoặc xử lý idempotent.
- **Bài 9:** Provider có thể đã capture; dùng idempotency key ổn định và query trạng thái trước khi gửi lại.
- **Bài 10:** Truyền remaining budget, trừ response/cleanup reserve để không vượt deadline gốc.
- **Bài 11:** Poll duration phải ngắn hơn remaining budget, chừa thời gian xử lý/response; hoặc không bắt đầu poll.
- **Bài 12:** Binder có thể thấy Consumer return và ACK trước DB completion. Chờ completion hoặc dùng reactive/async contract adapter hỗ trợ.
- **Bài 13:** Có; message có thể redeliver khi consumer đầu vẫn chạy. Gia hạn lease/heartbeat hoặc rút ngắn xử lý, đồng thời idempotent.
- **Bài 14:** Cùng operation ID giúp provider nhận diện cùng lệnh và trả kết quả cũ thay vì tạo payment thứ hai.
- **Bài 15:** Cancel là yêu cầu dừng tác vụ; refund là side effect mới để bù trừ. Refund có thể timeout/retry nên cần key riêng.
- **Bài 16:** Dùng `doOnCancel` và StepVerifier virtual time; Mono.never chỉ kiểm tra operator/Publisher cancellation, không mô phỏng driver.
- **Bài 17:** Đo timeout_total, cancel_requested_total, cancel_observed_total, task_completed_after_timeout_total và outbound_inflight.
- **Bài 18:** FunctionCatalog chỉ ghép hàm; application workflow/adapter deadline context quản lý overall deadline và từng client timeout.

## 29. Ghi nhớ

- Timeout, deadline, cancellation và completion là những khái niệm khác nhau.
- Timeout ở caller **không chứng minh** task bên dưới đã dừng hoặc transaction đã rollback.
- Dùng deadline tổng và truyền remaining budget; timeout từng bước phải nằm trong ngân sách chung.
- `Future.cancel(true)` và `CompletableFuture.orTimeout` không bảo đảm hủy external I/O.
- Reactor timeout phát lỗi và gửi cancellation upstream; adapter, driver và remote server phải hỗ trợ mới dừng được công việc thật.
- Phân biệt connection-pool, connect, response/read/write, query và transaction timeout.
- Đặt timeout đúng boundary trong WebClient, JDBC/driver, broker và serverless; `FunctionCatalog` không tự quản lý deadline.
- Với side effect không rõ kết quả sau timeout, dùng idempotency key, query trạng thái và reconciliation; không retry mù quáng.
- Cancellation là yêu cầu dừng; compensation là thao tác nghiệp vụ mới để khôi phục trạng thái.
- Kiểm thử timeout, cancellation, commit-after-timeout, broker redelivery và tài nguyên còn chạy sau deadline; quan sát cả cancellation requested lẫn observed.




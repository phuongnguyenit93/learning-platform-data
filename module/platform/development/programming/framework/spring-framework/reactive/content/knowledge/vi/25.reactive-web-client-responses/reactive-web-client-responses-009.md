# Timeout, retry có điều kiện và tính lũy đẳng của yêu cầu trong Spring WebClient

## 1. Vì sao phải kết hợp timeout, retry và idempotency?

Một HTTP client hoạt động qua mạng luôn có thể gặp lỗi: DNS chậm, không lấy được connection từ pool, kết nối TCP thất bại, server phản hồi chậm, response bị ngắt giữa chừng hoặc dependency tạm thời quá tải. **Timeout** giới hạn thời gian ứng dụng chờ. **Retry** thử lại khi lỗi có khả năng tạm thời. **Idempotency** bảo đảm việc gửi lại cùng một thao tác không tạo thêm hiệu ứng ngoài ý muốn.

Ba cơ chế này phải được thiết kế cùng nhau.

Ví dụ một ứng dụng gửi lệnh tạo đơn hàng:

1. Client gửi POST /orders.
2. Server tạo đơn hàng thành công.
3. Response bị mất trên đường truyền.
4. Client không biết server đã xử lý hay chưa và timeout.
5. Nếu client gửi lại POST một cách mù quáng, server có thể tạo đơn hàng thứ hai.

Timeout giúp client không chờ vô hạn, nhưng không chứng minh server chưa thực hiện thao tác. Retry giúp phục hồi lỗi tạm thời, nhưng có thể gửi trùng thao tác. Idempotency key cho phép server nhận diện lần gửi lại của cùng một thao tác logic và trả lại kết quả đã lưu.

Bài học này trình bày:

- Các tầng timeout của WebClient và Reactor Netty.
- Khác biệt giữa timeout của transport và timeout của Reactor Publisher.
- Phân loại lỗi có thể retry và lỗi không nên retry.
- Exponential backoff, jitter, giới hạn số lần thử và tổng deadline.
- Ngữ nghĩa safe/idempotent của HTTP theo RFC 9110.
- Idempotency-Key, fingerprint, lưu kết quả và xử lý request đồng thời.
- Khả năng phát lại request body khi retry.
- Cách kiểm thử retry bằng MockWebServer và StepVerifier.
- Ví dụ Java 17, Spring Boot 3.3.5 và WebClient có cấu hình timeout/retry rõ ràng.

## 2. Timeout trong HTTP client

Timeout là giới hạn thời gian cho một hoạt động cụ thể. Không có một timeout duy nhất bao phủ mọi giai đoạn của request.

Một request WebClient có thể trải qua:

~~~text
Subscribe
   |
   v
Acquire connection từ pool
   |
   v
DNS resolution
   |
   v
TCP connect
   |
   v
TLS handshake (HTTPS)
   |
   v
Gửi request headers/body
   |
   v
Chờ response headers
   |
   v
Đọc response body
   |
   v
Decode body thành object
   |
   v
Complete
~~~

Nếu chỉ đặt một timeout ở cấp Mono, ứng dụng có thể giới hạn thời gian tổng thể của pipeline, nhưng không biết chính xác giai đoạn nào bị chậm. Nếu chỉ đặt response timeout, việc chờ connection hoặc pool có thể vẫn kéo dài theo giới hạn khác.

### 2.1. Những loại timeout thường gặp

| Loại | Giới hạn hoạt động | Cấu hình thường dùng |
| --- | --- | --- |
| **Pool acquire timeout** | Chờ connection khả dụng trong connection pool | ConnectionProvider.pendingAcquireTimeout |
| **Connect timeout** | Thiết lập kết nối TCP tới remote host | ChannelOption.CONNECT_TIMEOUT_MILLIS |
| **DNS timeout** | Phân giải tên miền | Resolver/transport configuration |
| **TLS handshake timeout** | Hoàn tất bắt tay TLS | HttpClient.secure(...) |
| **Response timeout** | Khoảng chờ response/read theo connector | HttpClient.responseTimeout |
| **Read timeout** | Không có dữ liệu đọc trong thời gian quy định | ReadTimeoutHandler |
| **Write timeout** | Ghi dữ liệu ra transport quá lâu | WriteTimeoutHandler |
| **Publisher timeout** | Một Mono/Flux không phát tín hiệu trong thời gian quy định | Mono.timeout / Flux.timeout |
| **Business deadline** | Toàn bộ thao tác nghiệp vụ, có thể gồm nhiều HTTP call | Deadline ở service/application layer |

Tên và khả năng cấu hình cụ thể phụ thuộc HTTP connector. WebClient có thể dùng Reactor Netty, JDK HttpClient, Jetty hoặc connector khác. Ví dụ dưới đây dùng Reactor Netty.

### 2.2. Pool acquire timeout

WebClient thường dùng connection pool khi chạy trên Reactor Netty. Nếu pool đã đạt giới hạn và không có connection rảnh, request phải chờ một slot.

Có thể cấu hình:

~~~java
ConnectionProvider provider = ConnectionProvider.builder("orders")
    .maxConnections(50)
    .pendingAcquireTimeout(Duration.ofSeconds(2))
    .maxIdleTime(Duration.ofSeconds(20))
    .build();
~~~

- **maxConnections** giới hạn số connection được quản lý cho host/pool tương ứng.
- **pendingAcquireTimeout** giới hạn thời gian chờ lấy connection.
- **maxIdleTime** giới hạn thời gian connection nằm idle trong pool.

Nếu pool quá nhỏ, request có thể timeout trước khi được gửi tới server. Đây là lỗi capacity/pool, không nhất thiết là server chậm. Cần theo dõi active, idle và pending connections trước khi tăng timeout.

### 2.3. Connect timeout

Connect timeout giới hạn thời gian thiết lập kết nối TCP. Với Reactor Netty:

~~~java
HttpClient httpClient = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000);
~~~

Giá trị trên tính bằng millisecond. Timeout này không giới hạn thời gian server xử lý request sau khi kết nối thành công.

### 2.4. Response timeout

Có thể cấu hình response timeout:

~~~java
HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(3));
~~~

Đây là cấu hình ở tầng Reactor Netty. Nó giới hạn thời gian chờ dữ liệu response theo cơ chế của connector; nó không tương đương một deadline tổng thể cho toàn bộ business operation.

Với response streaming, cần phân biệt thời gian chờ giữa các lần đọc dữ liệu và thời gian toàn bộ stream tồn tại. Một stream hợp lệ có thể kéo dài nhiều phút nhưng vẫn phát dữ liệu định kỳ.

### 2.5. Read timeout và write timeout

Nếu cần giới hạn hoạt động đọc/ghi ở Netty pipeline:

~~~java
HttpClient httpClient = HttpClient.create()
    .doOnConnected(connection -> connection
        .addHandlerLast(new ReadTimeoutHandler(5))
        .addHandlerLast(new WriteTimeoutHandler(5))
    );
~~~

Các handler này có semantics riêng và có thể ảnh hưởng đến kết nối được tái sử dụng. Chỉ thêm khi hiểu rõ idle behavior của request/connection. Không bật mọi timeout với cùng một giá trị theo thói quen; hãy chọn theo đặc tính payload và dịch vụ đích.

### 2.6. Timeout ở cấp Mono và Flux

Reactor cung cấp toán tử timeout:

~~~java
Mono<OrderResponse> response = webClient.get()
    .uri("/orders/{id}", id)
    .retrieve()
    .bodyToMono(OrderResponse.class)
    .timeout(Duration.ofSeconds(5));
~~~

Với Mono, timeout giới hạn thời gian chờ kết quả từ lúc subscribe tới khi Mono phát kết quả/hoàn tất theo semantics của toán tử.

Với Flux:

~~~java
Flux<Quote> quotes = webClient.get()
    .uri("/quotes")
    .retrieve()
    .bodyToFlux(Quote.class)
    .timeout(Duration.ofSeconds(10));
~~~

Timeout trên Flux thường giới hạn khoảng thời gian chờ tín hiệu tiếp theo; timer được áp dụng lại sau mỗi tín hiệu. Nó hữu ích cho idle timeout của stream, nhưng không phải một deadline tổng cho toàn bộ stream nếu stream liên tục phát dữ liệu.

Nếu cần giới hạn toàn bộ một thao tác gồm nhiều lần retry, đặt deadline ở ngoài retry sequence. Ví dụ:

~~~java
Mono<OrderResponse> operation =
    Mono.defer(this::oneAttempt)
        .retryWhen(retryPolicy)
        .timeout(Duration.ofSeconds(8));
~~~

Timeout ngoài cùng giới hạn tổng thời gian của chuỗi attempt và backoff. Nếu cần timeout riêng từng attempt, đặt timeout bên trong oneAttempt.

### 2.7. Timeout không có nghĩa server đã dừng xử lý

Khi client timeout, Reactor hủy subscription ở phía client. Điều đó không bảo đảm server đã hủy công việc hoặc transaction.

Có thể xảy ra:

- Request chưa tới server.
- Server đã nhận nhưng chưa xử lý.
- Server đã thực hiện side effect nhưng response chưa về.
- Server đã trả response nhưng connection bị mất.
- Client đã nhận headers nhưng body bị ngắt.

Vì vậy, timeout của POST/command tạo dữ liệu thường tạo ra **kết quả không xác định**. Nếu request có thể tạo side effect, phải dùng idempotency hoặc cơ chế truy vấn trạng thái trước khi gửi lại.

## 3. Cấu hình WebClient với Reactor Netty

Một WebClient nên được tái sử dụng. Cấu hình connector một lần thay vì tạo client mới cho mỗi request.

Ví dụ:

~~~java
@Configuration
public class WebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider ordersConnectionProvider() {
        return ConnectionProvider.builder("orders")
            .maxConnections(50)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(20))
            .build();
    }

    @Bean
    WebClient ordersWebClient(
        WebClient.Builder builder,
        ConnectionProvider ordersConnectionProvider
    ) {
        HttpClient httpClient = HttpClient
            .create(ordersConnectionProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            .responseTimeout(Duration.ofSeconds(3));

        return builder
            .baseUrl("https://orders.example")
            .clientConnector(
                new ReactorClientHttpConnector(httpClient)
            )
            .build();
    }
}
~~~

Các import chính:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;

import reactor.netty.resources.ConnectionProvider;
import reactor.netty.http.client.HttpClient;
~~~

Cấu hình này minh họa:

- Chờ pool tối đa 2 giây.
- Kết nối TCP tối đa 2 giây.
- Response timeout 3 giây.
- Tối đa 50 connection trong pool.
- Connection idle tối đa 20 giây.

Giá trị thực tế phải dựa trên latency mục tiêu, tải, connection pool và timeout của dịch vụ đích. Timeout của proxy/load balancer cũng cần được tính vào.

### 3.1. WebClient không chỉ hỗ trợ Reactor Netty

Nếu ứng dụng dùng JDK HttpClient hoặc Jetty connector, API timeout sẽ khác. Không đưa cấu hình Netty vào một WebClient đang dùng connector khác và kỳ vọng nó có tác dụng.

Có thể kiểm tra connector được tạo trong cấu hình Spring Boot và khai báo rõ dependency nếu cần hành vi nhất quán.

### 3.2. Không đặt timeout quá thấp

Timeout quá thấp có thể làm request hợp lệ bị hủy trong lúc server vẫn đang xử lý. Nếu sau đó client retry, server có thể nhận nhiều request cùng thao tác.

Đặt timeout dựa trên:

- Latency p50, p95 và p99.
- Thời gian xử lý bình thường của dependency.
- Thời gian chờ pool.
- Kích thước request/response.
- Thời gian TLS và network.
- Deadline tổng của nghiệp vụ.
- Mức độ an toàn khi retry.

## 4. Retry trong Reactor

Retry là thao tác subscribe lại vào Publisher khi Publisher phát onError và chiến lược cho phép thử lại.

Ví dụ đơn giản:

~~~java
Mono<String> response = webClient.get()
    .uri("/health")
    .retrieve()
    .bodyToMono(String.class)
    .retry(2);
~~~

**retry(2)** có nghĩa là tối đa hai lần resubscribe sau lần ban đầu: tổng cộng có thể có ba attempt. Toán tử retry không phân biệt lỗi tạm thời hay lỗi vĩnh viễn; nếu không lọc, nó có thể lặp cả lỗi 400, lỗi deserialize hoặc lỗi cấu hình.

Với HTTP client, hãy dùng retry có điều kiện.

### 4.1. Những lỗi thường có thể retry

Tùy API contract và nghiệp vụ, các trường hợp sau có thể là lỗi tạm thời:

- Connection reset hoặc connection bị đóng bất ngờ.
- Connect timeout.
- Response timeout.
- HTTP 408 Request Timeout.
- HTTP 502 Bad Gateway.
- HTTP 503 Service Unavailable.
- HTTP 504 Gateway Timeout.
- HTTP 429 Too Many Requests nếu xử lý đúng Retry-After.

HTTP 500 có thể là lỗi tạm thời hoặc lỗi ứng dụng. Chỉ retry nếu contract của dịch vụ đích cho phép và có giới hạn.

### 4.2. Những lỗi thường không nên retry tự động

| Lỗi | Lý do |
| --- | --- |
| 400 Bad Request | Payload hoặc cú pháp request sai |
| 401 Unauthorized | Cần xác thực/token hợp lệ |
| 403 Forbidden | Không có quyền |
| 404 Not Found | Tài nguyên không tồn tại |
| 409 Conflict | Xung đột nghiệp vụ hoặc trạng thái |
| 422 Unprocessable Content | Dữ liệu không thỏa quy tắc |
| JSON decode error | Response không đúng schema |
| SSL certificate error | Lỗi cấu hình/chứng thư, retry thường không giúp |
| Invalid URI/configuration | Lỗi cấu hình ở client |
| Validation error | Cần sửa dữ liệu, không gửi lại nguyên payload |

Đây là chính sách khởi đầu, không phải luật cứng cho mọi API. Ví dụ 404 có thể tạm thời trong hệ thống eventual consistency; 409 có thể có contract retry riêng. Hãy để tài liệu API đích quyết định.

### 4.3. RetryBackoffSpec

Reactor cung cấp **Retry.backoff(...)**:

~~~java
Retry retryPolicy = Retry.backoff(
        2,
        Duration.ofMillis(200)
    )
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(this::isRetryable)
    .doBeforeRetry(signal ->
        log.warn(
            "Retry attempt {}, cause={}",
            signal.totalRetries() + 1,
            signal.failure().getClass().getSimpleName()
        )
    );
~~~

- **backoff(2, ...)**: tối đa hai lần retry sau attempt ban đầu.
- **maxBackoff(...)**: giới hạn thời gian chờ tối đa.
- **jitter(...)**: thêm độ ngẫu nhiên để tránh nhiều client retry đồng thời.
- **filter(...)**: chỉ retry exception được chọn.
- **doBeforeRetry(...)**: ghi nhận attempt và nguyên nhân.

RetryBackoffSpec là immutable/copy-on-write, có thể được cấu hình như một policy dùng lại.

### 4.4. Exponential backoff

Backoff tăng dần sau mỗi lần thất bại. Ví dụ với mức đầu 200 ms và multiplier 2:

| Lần retry | Delay cơ sở |
| --- | ---: |
| Retry 1 | 200 ms |
| Retry 2 | 400 ms |
| Retry 3 | 800 ms |
| Retry 4 | 1.600 ms |

Giá trị thực tế còn bị giới hạn bởi maxBackoff và điều chỉnh bởi jitter.

Backoff giúp dịch vụ đích có thời gian phục hồi. Nếu client retry liên tục ngay lập tức, một sự cố nhỏ có thể biến thành retry storm.

### 4.5. Jitter

Giả sử 10.000 client cùng nhận 503 và đều chờ đúng 1 giây, chúng có thể đồng loạt gửi lại sau 1 giây. Jitter phân tán thời điểm retry, giảm tải đột biến.

Trong Reactor:

~~~java
Retry.backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(3))
    .jitter(0.5);
~~~

Giá trị jitter phải nằm trong khoảng 0.0 đến 1.0. Mặc định của RetryBackoffSpec là 0.5.

### 4.6. Retry-After và HTTP 429/503

Server có thể trả header **Retry-After** để đề nghị client chờ một khoảng thời gian trước khi thử lại. Giá trị có thể là số giây hoặc HTTP-date.

Một Retry.backoff cố định không tự động bảo đảm tuân thủ Retry-After. Nếu API đích yêu cầu header này, cần đọc header và xây dựng delay tương ứng, đồng thời áp dụng giới hạn tối đa để không vượt deadline của nghiệp vụ.

Không bỏ qua Retry-After rồi retry dày hơn yêu cầu của server. Với 429, retry sớm có thể khiến client tiếp tục bị rate-limit.

## 5. Tính lũy đẳng (idempotency) của HTTP

Một thao tác là **idempotent** nếu thực hiện nhiều lần cùng một request có cùng hiệu ứng dự kiến trên trạng thái server như thực hiện một lần.

Ví dụ:

- PUT /profiles/42 đặt profile về cùng một nội dung. Gửi lại không tạo thêm profile mới.
- DELETE /profiles/42 xóa cùng một resource. Lần thứ hai có thể trả 404, nhưng trạng thái cuối vẫn là resource đã bị xóa.
- GET /profiles/42 đọc dữ liệu và không yêu cầu thay đổi trạng thái nghiệp vụ.

Idempotency nói về **hiệu ứng dự kiến**, không bắt buộc response của mọi lần giống nhau. Server vẫn có thể ghi log, cập nhật audit history hoặc tăng metric ở mỗi lần nhận request.

### 5.1. Safe và idempotent không giống nhau

- **Safe**: method được định nghĩa là chỉ đọc, không yêu cầu thay đổi trạng thái tài nguyên.
- **Idempotent**: gửi cùng request nhiều lần có cùng hiệu ứng dự kiến như một lần.

Một method có thể idempotent nhưng không safe. PUT và DELETE là ví dụ.

Theo RFC 9110:

| HTTP method | Safe | Idempotent | Ghi chú |
| --- | --- | --- | --- |
| GET | Có | Có | Đọc representation |
| HEAD | Có | Có | Lấy metadata tương tự GET |
| OPTIONS | Có | Có | Hỏi khả năng giao tiếp |
| TRACE | Có | Có | Phản hồi thông tin request theo semantics của method |
| PUT | Không | Có | Thay thế/tạo trạng thái theo URI |
| DELETE | Không | Có | Xóa resource được định danh |
| POST | Không | Không mặc định | Có thể tạo side effect |
| PATCH | Không | Không mặc định | Tùy semantics của patch document |

Không suy luận idempotency chỉ từ tên method. Một endpoint POST có thể được thiết kế idempotent bằng contract, còn một endpoint GET được thiết kế sai có thể gây side effect ngoài semantics HTTP.

### 5.2. Khi nào được retry?

RFC 9110 cho phép client tự động retry một request idempotent khi communication failure xảy ra trước khi client đọc được response, vì lặp lại request không làm thay đổi hiệu ứng dự kiến.

Với method không idempotent như POST, client không nên tự động retry nếu không có cách biết request chưa được áp dụng hoặc có cơ chế bảo đảm thao tác thực sự idempotent.

Đây là lý do một POST timeout cần được xử lý cẩn thận: server có thể đã tạo dữ liệu nhưng response bị mất.

## 6. Idempotency-Key cho POST và thao tác có side effect

**Idempotency-Key** là một key duy nhất do client tạo cho một thao tác logic. Client gửi cùng key khi retry thao tác đó. Server lưu key và kết quả để nhận diện request trùng.

Ví dụ:

~~~http
POST /api/orders
Content-Type: application/json
Idempotency-Key: "8e03978e-40d5-43e8-bc93-6894a57f9324"

{
  "customerId": "C-42",
  "sku": "BK-01",
  "quantity": 2
}
~~~

Nếu response đầu tiên bị mất, client gửi lại cùng payload và cùng key. Server có thể trả lại kết quả đã lưu thay vì tạo đơn hàng thứ hai.

**Idempotency-Key không tự tạo ra idempotency.** Nếu server không đọc và lưu key, header chỉ là metadata. Client phải biết API đích có hỗ trợ header này và contract của API quy định cách dùng ra sao.

### 6.1. Tạo key một lần cho một thao tác logic

Tạo key trước khi bắt đầu chuỗi retry:

~~~java
String idempotencyKey = UUID.randomUUID().toString();

return orderClient.create(command, idempotencyKey);
~~~

Trong mọi attempt của thao tác đó, dùng lại cùng key. Không tạo UUID mới bên trong mỗi lần retry vì server sẽ nhìn mỗi attempt như một thao tác khác.

Khi người dùng chủ động tạo một đơn hàng mới, tạo key mới. Không tái sử dụng key của thao tác trước cho payload khác.

### 6.2. Key phải gắn với payload

Server nên lưu fingerprint của request cùng key. Fingerprint có thể được tạo từ:

- Hash toàn bộ payload sau canonicalization.
- Một số field nghiệp vụ quan trọng.
- Request digest hoặc chữ ký.
- Các field được quy định trong API contract.

Nếu cùng key nhưng payload khác, server phải từ chối thay vì coi đó là retry hợp lệ. Nếu không kiểm tra payload, một client có thể vô tình tái sử dụng key và nhận nhầm kết quả của một request khác.

### 6.3. Server lưu idempotency record như thế nào?

Một bảng lưu trữ có thể gồm:

| Field | Mục đích |
| --- | --- |
| tenant_id | Phạm vi người dùng/tenant |
| operation | Endpoint hoặc loại thao tác |
| idempotency_key | Key từ request |
| request_fingerprint | Hash/định danh payload |
| status | PROCESSING, COMPLETED hoặc FAILED |
| response_status | HTTP status đã lưu |
| response_body | Kết quả cần trả lại |
| created_at | Thời điểm bắt đầu |
| expires_at | Thời điểm hết hạn |

Tạo unique constraint trên phạm vi key phù hợp, ví dụ tenant + operation + idempotency_key.

Luồng xử lý khái niệm:

1. Nhận request và validate key.
2. Tính fingerprint từ payload.
3. Thử tạo idempotency record với trạng thái PROCESSING một cách atomic.
4. Nếu tạo mới thành công, thực hiện nghiệp vụ.
5. Lưu kết quả và chuyển record sang COMPLETED trong transaction phù hợp.
6. Nếu key đã tồn tại và fingerprint giống, trả lại kết quả đã lưu.
7. Nếu key tồn tại nhưng fingerprint khác, trả lỗi theo contract.
8. Nếu key đang PROCESSING, trả trạng thái conflict/in-progress hoặc chờ theo chính sách đã công bố.

### 6.4. Xử lý request đồng thời

Hai request cùng key có thể đến gần như đồng thời. Nếu chỉ kiểm tra bằng thao tác read-then-write, cả hai có thể cùng thấy key chưa tồn tại và cùng tạo đơn hàng.

Cần unique constraint hoặc cơ chế atomic reservation để chỉ một request trở thành owner của thao tác. Request còn lại phải quan sát trạng thái PROCESSING/COMPLETED và xử lý theo contract.

Không chỉ dựa vào Redis GET rồi SET rời rạc nếu không có thao tác atomic phù hợp. Nếu dùng Redis, database hoặc distributed lock, phải xử lý expiry, crash và owner recovery.

### 6.5. Side effect bên ngoài database

Nếu thao tác tạo đơn hàng còn gọi payment gateway hoặc gửi message sang broker, transaction database đơn thuần không bảo đảm toàn bộ side effect cùng commit.

Có thể dùng:

- Transactional outbox để ghi sự kiện cần phát trong cùng transaction với dữ liệu nghiệp vụ.
- Idempotency key tiếp tục được truyền tới payment provider nếu provider hỗ trợ.
- Consumer idempotency để chống xử lý message trùng.
- State machine cho thao tác dài, có trạng thái pending/completed/failed rõ ràng.

Không tuyên bố exactly-once chỉ vì đã có một header. Thực tế thường xây dựng hiệu ứng **effectively-once** bằng deduplication bền vững, transaction và consumer idempotent.

### 6.6. Thời hạn lưu key

Server cần công bố thời gian lưu key. Nếu xóa key quá sớm, client retry muộn có thể tạo side effect mới. Nếu giữ vô hạn, kho idempotency sẽ tăng không giới hạn.

Retention nên dài hơn cửa sổ retry/recovery mà API cam kết, có index phù hợp và chính sách xóa record đã hết hạn.

### 6.7. Trạng thái của đặc tả Idempotency-Key

Tại thời điểm bài học này được biên soạn, tài liệu **draft-ietf-httpapi-idempotency-key-header-08** là Internet-Draft đang được thảo luận trong IETF, chưa phải RFC đã ban hành. Draft mô tả key duy nhất, fingerprint, expiry và cách xử lý duplicate/concurrent request.

Các API thực tế có thể có contract riêng về dấu ngoặc kép, key length, phạm vi key, status code và retention. Hãy làm theo tài liệu của dịch vụ đích; không giả định mọi server đều tuân theo cùng một phiên bản draft.

## 7. Kết hợp timeout, retry và idempotency trong WebClient

Một client an toàn cần xác định:

1. Timeout của mỗi attempt.
2. Deadline tổng của thao tác.
3. Những lỗi được retry.
4. Số lần retry tối đa.
5. Backoff và jitter.
6. Request body có thể phát lại không.
7. Thao tác có idempotent hay có idempotency key không.
8. Response lỗi có được decode và release đúng cách không.

Ví dụ:

~~~java
Mono<OrderResponse> createOrder(
    CreateOrderCommand command,
    String idempotencyKey
) {
    return Mono.defer(() -> webClient.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .header("Idempotency-Key", idempotencyKey)
        .bodyValue(command)
        .retrieve()
        .bodyToMono(OrderResponse.class)
        .timeout(Duration.ofSeconds(2))
    )
    .retryWhen(retryPolicy)
    .timeout(Duration.ofSeconds(7));
}
~~~

Ý nghĩa:

- Mono.defer tạo request pipeline mới cho mỗi lần subscribe/retry.
- Timeout 2 giây giới hạn mỗi attempt.
- retryPolicy lọc lỗi tạm thời và chờ backoff.
- Timeout 7 giây giới hạn toàn bộ chuỗi attempt và backoff.
- Cùng command và idempotencyKey được dùng trong mọi attempt.

Nếu API tuân theo Structured Header syntax của draft hiện tại, giá trị Idempotency-Key có thể cần được gửi dưới dạng string có dấu ngoặc kép. Một số API đã triển khai trước đó dùng UUID không có dấu ngoặc kép. Luôn tuân theo contract của server đích.

### 7.1. Retry phải tạo request mới

Không subscribe thủ công vào cùng một ClientResponse hoặc giữ một body stream đã tiêu thụ rồi cố gửi lại. Mỗi attempt cần tạo request mới.

Với DTO/record bất biến và bodyValue, việc serialize lại thường có thể thực hiện. Với Publisher, file InputStream hoặc nguồn chỉ đọc một lần, phải tạo lại nguồn cho mỗi attempt.

Ví dụ body Publisher:

~~~java
Mono.defer(() -> {
    Flux<DataBuffer> body = fileService.openFreshBody();

    return webClient.post()
        .uri("/upload")
        .body(body, DataBuffer.class)
        .retrieve()
        .bodyToMono(UploadResponse.class);
})
.retryWhen(retryPolicy);
~~~

Đây là snippet giả định fileService.openFreshBody() mở được một nguồn mới mỗi lần gọi. Không dùng lại một InputStream đã bị consume.

### 7.2. Retry và response body

Khi dùng retrieve(), status 4xx/5xx mặc định trở thành WebClientResponseException. Exception có status và thông tin response để phân loại retry.

Nếu dùng onStatus() để decode body lỗi, hãy đọc body trong callback đó và chuyển thành exception mang đủ thông tin. Không cố đọc cùng response body nhiều lần.

Với exchangeToMono()/exchangeToFlux(), xử lý response trong callback và consume body cần thiết. Framework sẽ giải phóng body chưa được consume khi callback kết thúc theo contract của API.

### 7.3. Tránh retry toàn bộ lỗi

Không viết:

~~~java
webClient.get()
    .uri("/orders")
    .retrieve()
    .bodyToMono(OrderResponse.class)
    .retryWhen(Retry.indefinitely());
~~~

Cách này có thể retry vô hạn lỗi 400, 401, lỗi decode, lỗi certificate hoặc lỗi lập trình. Nó còn có thể giữ request chạy vô hạn và gây tải dây chuyền.

Dùng filter và giới hạn attempt:

~~~java
Retry retryPolicy = Retry.backoff(2, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(this::isRetryable);
~~~

## 8. Phân loại lỗi cho WebClient

Một classifier nên xem cả HTTP status lẫn exception transport.

Ví dụ chính sách:

~~~java
private boolean isRetryable(Throwable error) {
    if (error instanceof WebClientResponseException response) {
        int status = response.getStatusCode().value();

        return status == 408
            || status == 502
            || status == 503
            || status == 504;
    }

    if (error instanceof TimeoutException) {
        return true;
    }

    if (error instanceof WebClientRequestException) {
        if (hasCause(error, SSLException.class)
                || hasCause(error, UnknownHostException.class)) {
            return false;
        }

        return hasCause(error, ConnectException.class)
            || hasCause(error, SocketTimeoutException.class)
            || hasCause(error, IOException.class)
            || hasCauseNamed(
                error,
                "ConnectTimeoutException",
                "ReadTimeoutException",
                "PrematureCloseException"
            );
    }

    return false;
}
~~~

Đây là classifier minh họa. Exception cụ thể phụ thuộc connector, phiên bản Netty và transport. Trong production, cần quan sát cause chain thực tế và mở rộng theo các lỗi được xác nhận là transient.

### 8.1. Vì sao không đưa mọi 5xx vào retry?

Một số 5xx có thể là lỗi tạm thời, nhưng 500 cũng có thể là lỗi code hoặc dữ liệu khiến request nào cũng thất bại. Chỉ retry các status được API đích mô tả là có thể phục hồi.

### 8.2. Vì sao không retry 401/403?

401 có thể cần refresh token; 403 thường là không có quyền. Nếu hệ thống có token refresh, hãy thực hiện một luồng refresh có giới hạn và chỉ retry request sau khi token được thay mới. Không để retry policy lặp vô hạn với cùng credential sai.

### 8.3. Xử lý 429

Với 429, đọc Retry-After. Nếu server không cung cấp header, dùng backoff theo policy. Nếu có header, chọn delay phù hợp nhưng vẫn phải tuân thủ deadline tổng và giới hạn tối đa.

Không dùng một retry policy chung cho mọi dependency. Dịch vụ thanh toán, catalog và notification có thể có contract lỗi và SLA khác nhau.

## 9. Retry budget, circuit breaker và tải hệ thống

Retry có thể giúp phục hồi lỗi ngắn hạn, nhưng cũng có thể làm sự cố nặng hơn nếu mọi client cùng retry.

Một chiến lược production nên có:

- Số lần retry nhỏ và cố định.
- Exponential backoff và jitter.
- Deadline tổng cho nghiệp vụ.
- Connection pool có giới hạn.
- Rate limit và bulkhead.
- Circuit breaker khi dependency liên tục thất bại.
- Metrics riêng cho attempt ban đầu và retry.
- Giới hạn tổng số lần retry qua các tầng.

Nếu frontend retry 3 lần, service A retry 3 lần và service B retry 3 lần, một thao tác logic có thể tạo nhiều request tới dependency. Hãy tính retry amplification trên toàn call graph.

### 9.1. Không retry ở mọi tầng một cách độc lập

Chọn một tầng chịu trách nhiệm retry cho mỗi dependency. Nếu cả gateway, service và SDK đều retry, cần thống nhất budget và deadline.

### 9.2. Circuit breaker

Circuit breaker có thể ngăn request mới đi tới dependency đang lỗi liên tục. Khi circuit open, client nhận lỗi nhanh thay vì tiếp tục chờ timeout và retry.

Retry và circuit breaker có thể phối hợp, nhưng thứ tự operator ảnh hưởng hành vi. Thiết kế theo contract của thư viện resilience đang dùng và kiểm thử thứ tự thực thi.

### 9.3. Bulkhead và connection pool

Giới hạn số request đồng thời để một dependency chậm không chiếm toàn bộ tài nguyên của ứng dụng. Connection pool, pending acquire queue và concurrency limit cần được đặt theo tải dự kiến.

Không tăng maxConnections vô hạn để che giấu pool acquire timeout. Điều đó có thể tăng số socket, memory và áp lực lên server đích.

## 10. Ví dụ hoàn chỉnh Java 17+: WebClient có timeout, retry và idempotency key

Ví dụ dùng **Spring Boot 3.3.5**, Spring Framework 6.1.x, Java 17, Reactor Netty và MockWebServer.

Client gửi lệnh tạo đơn hàng qua POST. Nó:

- Đặt connect và response timeout ở Reactor Netty.
- Đặt timeout riêng cho mỗi attempt.
- Đặt deadline tổng cho toàn chuỗi retry.
- Chỉ retry một nhóm lỗi tạm thời.
- Dùng exponential backoff và jitter.
- Giữ nguyên Idempotency-Key qua mọi attempt.
- Kiểm tra request thực tế bằng MockWebServer.

Cấu trúc:

~~~text
webclient-timeout-retry-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/retrydemo/
    │           ├── CreateOrderCommand.java
    │           ├── OrderResponse.java
    │           ├── OrderClient.java
    │           └── OrderClientConfiguration.java
    └── test/
        └── java/
            └── com/example/retrydemo/
                └── OrderClientTest.java
~~~

### 10.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webclient-timeout-retry-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.2. CreateOrderCommand.java

~~~java
package com.example.retrydemo;

import java.math.BigDecimal;

public record CreateOrderCommand(
    String customerId,
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}
~~~

### 10.3. OrderResponse.java

~~~java
package com.example.retrydemo;

public record OrderResponse(
    String orderId,
    String status
) {}
~~~

### 10.4. OrderClientConfiguration.java

~~~java
package com.example.retrydemo;

import java.time.Duration;

import io.netty.channel.ChannelOption;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class OrderClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider orderConnectionProvider() {
        return ConnectionProvider.builder("order-client")
            .maxConnections(50)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(20))
            .build();
    }

    @Bean
    WebClient orderWebClient(
        WebClient.Builder builder,
        ConnectionProvider orderConnectionProvider
    ) {
        HttpClient httpClient = HttpClient
            .create(orderConnectionProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            .responseTimeout(Duration.ofSeconds(3));

        return builder
            .baseUrl("https://orders.example")
            .clientConnector(
                new ReactorClientHttpConnector(httpClient)
            )
            .build();
    }
}
~~~

ConnectionProvider được Spring quản lý vòng đời và dispose khi ApplicationContext đóng. WebClient có thể được tái sử dụng cho nhiều request.

### 10.5. OrderClient.java

~~~java
package com.example.retrydemo;

import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.TimeoutException;

import javax.net.ssl.SSLException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public class OrderClient {

    private static final Logger log =
        LoggerFactory.getLogger(OrderClient.class);

    private final WebClient webClient;
    private final Duration perAttemptTimeout;
    private final Duration totalTimeout;
    private final Retry retryPolicy;

    public OrderClient(
        WebClient webClient,
        Duration perAttemptTimeout,
        Duration totalTimeout
    ) {
        this.webClient = webClient;
        this.perAttemptTimeout = perAttemptTimeout;
        this.totalTimeout = totalTimeout;

        this.retryPolicy = Retry
            .backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .jitter(0.25)
            .filter(this::isRetryable)
            .doBeforeRetry(signal ->
                log.warn(
                    "Retry order request: attempt={}, error={}",
                    signal.totalRetries() + 1,
                    signal.failure().getClass().getSimpleName()
                )
            );
    }

    public Mono<OrderResponse> create(
        CreateOrderCommand command,
        String idempotencyKey
    ) {
        return Mono.defer(() -> webClient.post()
                .uri("/api/orders")
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .accept(org.springframework.http.MediaType.APPLICATION_JSON)
                .header(
                    "Idempotency-Key",
                    "\"" + idempotencyKey + "\""
                )
                .bodyValue(command)
                .retrieve()
                .bodyToMono(OrderResponse.class)
                .timeout(perAttemptTimeout)
            )
            .retryWhen(retryPolicy)
            .timeout(totalTimeout);
    }

    private boolean isRetryable(Throwable error) {
        if (error instanceof WebClientResponseException response) {
            int status = response.getStatusCode().value();

            return status == 408
                || status == 502
                || status == 503
                || status == 504;
        }

        if (error instanceof TimeoutException) {
            return true;
        }

        if (error instanceof WebClientRequestException) {
            if (hasCause(error, SSLException.class)
                    || hasCause(error, UnknownHostException.class)) {
                return false;
            }

            return hasCause(error, ConnectException.class)
                || hasCause(error, SocketTimeoutException.class)
                || hasCause(error, IOException.class)
                || hasCauseNamed(
                    error,
                    Set.of(
                        "ConnectTimeoutException",
                        "ReadTimeoutException",
                        "PrematureCloseException"
                    )
                );
        }

        return false;
    }

    private static boolean hasCause(
        Throwable error,
        Class<? extends Throwable> type
    ) {
        for (Throwable current = error;
             current != null;
             current = current.getCause()) {
            if (type.isInstance(current)) {
                return true;
            }
            if (current.getCause() == current) {
                break;
            }
        }
        return false;
    }

    private static boolean hasCauseNamed(
        Throwable error,
        Set<String> names
    ) {
        for (Throwable current = error;
             current != null;
             current = current.getCause()) {
            if (names.contains(current.getClass().getSimpleName())) {
                return true;
            }
            if (current.getCause() == current) {
                break;
            }
        }
        return false;
    }
}
~~~

Các điểm cần hiểu:

- **Mono.defer** tạo lại request cho mỗi attempt.
- **bodyValue(command)** dùng lại cùng DTO.
- Cùng **idempotencyKey** được gắn vào mọi attempt.
- Timeout 2 giây giới hạn từng attempt.
- Retry tối đa hai lần sau attempt ban đầu.
- Deadline 7 giây giới hạn cả chuỗi attempt và backoff.
- Chỉ một nhóm lỗi được retry.
- 400, 401, 403, 404, 409, 422 và lỗi decode không được retry theo classifier này.

Trong production, classifier cần được kiểm chứng với cause chain của connector thực tế. Ví dụ trên không bao gồm 429 vì client cần đọc và tôn trọng Retry-After theo contract của server.

### 10.6. OrderClientTest.java

~~~java
package com.example.retrydemo;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class OrderClientTest {

    private MockWebServer server;
    private OrderClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .build();

        client = new OrderClient(
            webClient,
            java.time.Duration.ofSeconds(2),
            java.time.Duration.ofSeconds(7)
        );
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void retries503AndReusesSameIdempotencyKey() throws Exception {
        server.enqueue(
            new MockResponse()
                .setResponseCode(503)
                .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE
                )
                .setBody("{\"code\":\"TEMPORARY_UNAVAILABLE\"}")
        );

        server.enqueue(
            new MockResponse()
                .setResponseCode(201)
                .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE
                )
                .setBody(
                    "{\"orderId\":\"ORD-100\",\"status\":\"created\"}"
                )
        );

        CreateOrderCommand command = new CreateOrderCommand(
            "C-42",
            "BK-01",
            2,
            new BigDecimal("12.50")
        );

        String key = "8e03978e-40d5-43e8-bc93-6894a57f9324";

        StepVerifier.create(client.create(command, key))
            .assertNext(response -> {
                assertEquals("ORD-100", response.orderId());
                assertEquals("created", response.status());
            })
            .verifyComplete();

        RecordedRequest first =
            server.takeRequest(2, TimeUnit.SECONDS);
        RecordedRequest second =
            server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(first);
        assertNotNull(second);

        assertEquals("POST", first.getMethod());
        assertEquals("/api/orders", first.getPath());
        assertEquals("POST", second.getMethod());

        String expectedHeader = "\"" + key + "\"";

        assertEquals(
            expectedHeader,
            first.getHeader("Idempotency-Key")
        );
        assertEquals(
            expectedHeader,
            second.getHeader("Idempotency-Key")
        );

        assertEquals(
            first.getBody().readUtf8(),
            second.getBody().readUtf8()
        );

        assertEquals(2, server.getRequestCount());
    }

    @Test
    void doesNotRetryBadRequest() {
        server.enqueue(
            new MockResponse()
                .setResponseCode(400)
                .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE
                )
                .setBody("{\"code\":\"INVALID_ORDER\"}")
        );

        CreateOrderCommand command = new CreateOrderCommand(
            "C-42",
            "BK-01",
            0,
            BigDecimal.ONE
        );

        StepVerifier.create(
                client.create(command, "key-for-invalid-order")
            )
            .expectError(
                WebClientResponseException.BadRequest.class
            )
            .verify();

        assertEquals(1, server.getRequestCount());
    }
}
~~~

Test đầu xếp một response 503 rồi response 201. Nó xác nhận client retry đúng một lần, giữ nguyên Idempotency-Key và gửi lại cùng body.

Test thứ hai trả 400 và xác nhận request chỉ được gửi một lần. Đây là kiểm tra quan trọng để tránh retry các lỗi payload không thể tự phục hồi.

### 10.7. Chạy test

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn clean test
~~~

MockWebServer nhận HTTP request thật do WebClient gửi, nên test có thể kiểm tra method, path, header, body và số lần request. Không cần gọi dịch vụ orders bên ngoài.

## 11. Tạo Idempotency-Key ở tầng nghiệp vụ

Một service có thể tạo key cho thao tác mới:

~~~java
public Mono<OrderResponse> submitNewOrder(
    CreateOrderCommand command
) {
    String key = UUID.randomUUID().toString();

    return orderClient.create(command, key);
}
~~~

Nếu tầng trên có thể tự retry cả submitNewOrder, việc tạo key bên trong method này có thể tạo key mới ở mỗi lần gọi. Trong trường hợp đó, key nên được tạo ở ranh giới bắt đầu thao tác logic và truyền xuyên suốt các tầng.

Ví dụ:

~~~java
String key = commandContext.idempotencyKey();

return orderClient.create(command, key);
~~~

Command context cần giữ key ổn định khi ứng dụng phục hồi hoặc tiếp tục một thao tác đã bắt đầu.

### 11.1. Không tạo key mới cho mỗi retry

Sai:

~~~java
Mono.defer(() -> {
    String key = UUID.randomUUID().toString();

    return orderClient.create(command, key);
}).retryWhen(retryPolicy);
~~~

Mỗi lần retry tạo key khác, server không thể nhận diện đó là cùng thao tác.

Đúng:

~~~java
String key = UUID.randomUUID().toString();

Mono.defer(() -> orderClient.create(command, key))
    .retryWhen(retryPolicy);
~~~

Cùng key được dùng cho tất cả lần gửi của thao tác này.

## 12. Observability và vận hành

Một retry policy khó vận hành nếu chỉ ghi log "request failed". Nên theo dõi:

- Số request logic.
- Số attempt ban đầu và attempt retry.
- Tỷ lệ retry theo dependency và status.
- Timeout theo pool/connect/response/total.
- Latency của từng attempt và tổng latency.
- Retry exhaustion.
- Số request bị circuit breaker từ chối.
- Idempotency duplicate hit.
- Idempotency key conflict do payload khác.
- Request đang PROCESSING quá lâu.
- Client cancel và connection reset.

Không ghi idempotency key đầy đủ nếu key có thể được dùng như thông tin nhạy cảm. Có thể log hash rút gọn hoặc correlation ID riêng.

### 12.1. Retry exhaustion

Khi hết số lần retry, Reactor phát lỗi retry exhausted với nguyên nhân cuối được gắn vào cause. Có thể dùng Exceptions.isRetryExhausted(...) để phân biệt trong error mapping.

Không biến mọi retry exhaustion thành lỗi 500 chung nếu client cần biết dependency nào thất bại. Trả mã lỗi ổn định và ghi dependency/attempt trong log.

### 12.2. Deadline xuyên nhiều service

Nếu request đi qua nhiều service, truyền deadline hoặc remaining timeout thay vì mỗi service tự đặt một timeout dài. Tổng thời gian của các dependency phải nằm trong deadline của request gốc.

Ví dụ:
- Gateway có deadline 8 giây.
- Service A dành tối đa 5 giây cho dependency B.
- Service A giữ thời gian còn lại cho xử lý và response.
- Retry của B phải nằm trong budget 5 giây.

Không để mỗi tầng retry 3 lần và chờ 10 giây nếu deadline request gốc chỉ 8 giây.

## 13. Những lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Request chờ quá lâu trước khi gửi | Chờ connection pool hoặc DNS | Cấu hình pool acquire và resolver timeout |
| TCP connect mất nhiều thời gian | Connect timeout chưa phù hợp | Đặt CONNECT_TIMEOUT_MILLIS |
| Server phản hồi chậm | Chưa có response timeout | Cấu hình HttpClient.responseTimeout |
| Toàn bộ nghiệp vụ vượt deadline | Chỉ đặt timeout transport | Đặt deadline ngoài cùng cho operation |
| Retry cả lỗi 400 | Retry không có filter | Dùng RetryBackoffSpec.filter |
| Retry vô hạn | Dùng Retry.indefinitely | Giới hạn attempts và deadline |
| Nhiều client retry cùng lúc | Không có jitter | Dùng exponential backoff và jitter |
| 429 vẫn bị rate-limit | Bỏ qua Retry-After | Parse và tuân thủ Retry-After |
| POST tạo đơn hàng trùng | Retry sau timeout nhưng server không deduplicate | Dùng Idempotency-Key và lưu kết quả bền vững |
| Retry nhưng key thay đổi | Tạo UUID bên trong mỗi attempt | Tạo key một lần cho thao tác logic |
| Cùng key nhưng payload khác | Server chỉ kiểm tra key, không kiểm tra fingerprint | Lưu và so sánh request fingerprint |
| Hai request cùng key cùng tạo side effect | Check-then-insert không atomic | Unique constraint/atomic reservation |
| Retry file upload thất bại | Body stream chỉ đọc một lần | Tạo lại nguồn body cho từng attempt |
| Timeout nhưng server vẫn xử lý | Client cancel không rollback remote operation | Dùng idempotency và truy vấn trạng thái |
| Retry khuếch đại tải | Nhiều tầng cùng retry | Thống nhất retry budget toàn call graph |
| Chỉ nhìn status cuối mà không biết số attempt | Thiếu metrics retry | Ghi retry count, latency và dependency |
| Dùng 500 làm transient trong mọi trường hợp | Không phân biệt lỗi server tạm thời và lỗi code | Chọn status theo API contract |
| Chờ timeout dài hơn deadline của caller | Timeout không đồng bộ giữa các tầng | Truyền remaining deadline |
| Lưu idempotency key quá ngắn | Key hết hạn trước khi client retry | Công bố và thiết kế retention phù hợp |

## 14. Checklist thiết kế timeout và retry

Trước khi đưa WebClient vào production, hãy xác nhận:

1. Connector thực tế là Reactor Netty, JDK HttpClient hay Jetty?
2. Pool acquire timeout đã được cấu hình?
3. Connect timeout đã được cấu hình?
4. TLS handshake và DNS có giới hạn phù hợp?
5. Response timeout có phù hợp với latency và streaming behavior?
6. Timeout ở cấp Mono/Flux có đúng semantics?
7. Deadline tổng bao gồm cả backoff và retry?
8. Retry chỉ áp dụng cho lỗi transient?
9. 400/401/403/404/409/422 có bị loại khỏi retry theo contract?
10. 429 có tôn trọng Retry-After?
11. Retry có giới hạn attempt, backoff và jitter?
12. Có tránh retry storm và retry amplification?
13. Request body có thể tạo lại ở mỗi attempt?
14. HTTP method có idempotent theo RFC 9110 và API contract?
15. POST/PATCH có side effect đã có Idempotency-Key khi cần?
16. Key có duy nhất cho mỗi thao tác logic và giữ nguyên qua retry?
17. Server lưu fingerprint và kết quả một cách atomic?
18. Request đồng thời cùng key được xử lý đúng?
19. Có retention/expiry policy?
20. Có metrics cho timeout, retry, duplicate và exhaustion?
21. Có test retry thành công sau 503?
22. Có test không retry lỗi 400?
23. Có test key/body được giữ nguyên qua các attempt?
24. Có test timeout và retry budget ở cấp integration?

## 15. Bài tập thực hành

**Bài 1 — Connect timeout:** Cấu hình CONNECT_TIMEOUT_MILLIS và thử gọi một host không thể kết nối. Quan sát exception và thời gian kết thúc.

**Bài 2 — Response timeout:** Dùng MockWebServer trì hoãn response headers. Đặt responseTimeout và quan sát lỗi.

**Bài 3 — Pool acquire timeout:** Giới hạn maxConnections nhỏ, giữ connection lâu và gửi thêm request để quan sát pendingAcquireTimeout.

**Bài 4 — Mono timeout:** Thêm timeout ở bodyToMono và so sánh với responseTimeout của Reactor Netty.

**Bài 5 — Flux idle timeout:** Tạo stream phát dữ liệu theo chu kỳ. Thử Flux.timeout với khoảng idle khác nhau và giải thích timer reset sau mỗi phần tử.

**Bài 6 — Retry 503:** Cho MockWebServer trả 503 rồi 200. Xác minh số request và kết quả cuối.

**Bài 7 — Không retry 400:** Trả 400 và xác minh classifier không resubscribe.

**Bài 8 — Jitter:** Chạy nhiều client cùng nhận lỗi tạm thời. Quan sát thời điểm retry có được phân tán hay không.

**Bài 9 — Retry-After:** Trả 429 với Retry-After. Viết policy chờ đúng thời gian và vẫn tôn trọng deadline tổng.

**Bài 10 — Idempotency key:** Gửi POST hai lần cùng key và cùng payload. Thiết kế server trả cùng kết quả mà chỉ tạo một order.

**Bài 11 — Fingerprint conflict:** Gửi cùng key nhưng payload khác. Xác minh server từ chối theo contract.

**Bài 12 — Concurrent duplicate:** Gửi hai request đồng thời cùng key. Chứng minh chỉ một request được xử lý side effect.

**Bài 13 — Lost response:** Giả lập server đã ghi order nhưng đóng connection trước khi client đọc response. Retry cùng key và xác minh không tạo order thứ hai.

**Bài 14 — Replay body:** Gửi body bằng Flux hoặc file stream. Làm cho attempt đầu thất bại và chứng minh attempt sau tạo được nguồn body mới.

## 16. Ghi nhớ

Timeout giới hạn thời gian chờ ở từng tầng; retry thử lại khi lỗi có khả năng tạm thời; idempotency bảo vệ trạng thái server khi request bị gửi lại. Không cơ chế nào thay thế hai cơ chế còn lại.

Với WebClient, hãy kết hợp timeout của Reactor Netty cho pool/connect/response với timeout ở cấp Mono/Flux và deadline tổng. Dùng RetryBackoffSpec có filter, giới hạn attempts, exponential backoff và jitter. Chỉ retry status/exception được xác định là transient.

Theo RFC 9110, safe methods và PUT/DELETE có semantics idempotent; POST/PATCH không idempotent mặc định. Khi cần retry thao tác tạo dữ liệu, tạo một Idempotency-Key cho mỗi thao tác logic, giữ nguyên key và payload qua mọi attempt, đồng thời yêu cầu server lưu fingerprint và kết quả một cách atomic.

Timeout sau khi gửi request có thể để lại kết quả không xác định. Hãy thiết kế client, server, transaction, outbox, retry budget và observability cùng nhau để phục hồi lỗi mà không tạo side effect trùng.

## 17. Tài liệu tham khảo

- Spring Framework Reference — WebClient Configuration and Timeouts: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework Reference — WebClient retrieve(): https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework Reference — WebClient exchangeToMono/exchangeToFlux: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Reactor Netty Reference — HTTP Client Timeout Configuration: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Reactor Core API — RetryBackoffSpec: https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html
- Reactor Reference Guide — Error Handling and Retry: https://projectreactor.io/docs/core/release/reference/
- RFC 9110 — HTTP Semantics, Safe and Idempotent Methods: https://www.rfc-editor.org/rfc/rfc9110.html
- IETF Internet-Draft — The Idempotency-Key HTTP Header Field, draft-ietf-httpapi-idempotency-key-header-08 (work in progress): https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/
- MDN — Idempotency-Key header: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Idempotency-Key
- Spring Framework API — WebClient: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/reactive/function/client/WebClient.html

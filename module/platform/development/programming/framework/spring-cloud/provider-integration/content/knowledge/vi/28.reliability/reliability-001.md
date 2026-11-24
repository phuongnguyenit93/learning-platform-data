# Đặt thời hạn toàn thao tác và timeout cho từng lần gọi

Một request của Spring Boot có thể gọi lần lượt database, Azure Blob Storage và Service Bus. Nếu mỗi client đều được cấu hình timeout riêng nhưng không có giới hạn chung, tổng thời gian xử lý có thể dài hơn nhiều so với thời gian người gọi chờ. Ngược lại, đặt timeout quá ngắn cho mọi kết nối có thể làm request thất bại ngay cả khi dịch vụ chỉ đang có độ trễ tạm thời.

Cần phân biệt **deadline của toàn thao tác** với **timeout của từng lần gọi**. Deadline xác định thời điểm muộn nhất nghiệp vụ được phép hoàn thành; timeout của từng lần gọi giới hạn thời gian dành cho một bước như lấy kết nối, gửi HTTP request, truy vấn database hoặc gửi message. Các timeout con phải nằm trong ngân sách còn lại của thao tác cha.

Bài thuộc chương **Độ tin cậy** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng; chú trọng danh tính/quyền, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **deadline**, **timeout toàn request**, **timeout một lần gọi**, **connect timeout**, **response/read timeout** và **idle timeout**.
2. Phân bổ một ngân sách thời gian cho nhiều bước tuần tự hoặc song song trong Spring Boot.
3. Truyền phần thời gian còn lại cho HTTP client, Azure SDK, database và messaging client.
4. Thiết kế retry/backoff sao cho không vượt deadline, tránh retry storm và xử lý được thao tác không idempotent.
5. Hiểu khác biệt giữa timeout và cancellation, đặc biệt khi dùng synchronous SDK, CompletableFuture hoặc Reactor.
6. Kiểm thử timeout bằng fake clock, mock client, test server và môi trường cloud test.
7. Quan sát latency, timeout, retry và deadline exhaustion mà không log dữ liệu nhạy cảm.

## 2. Deadline và timeout không phải một khái niệm

**Deadline** là mốc thời gian cuối cùng mà một thao tác phải hoàn tất. **Timeout** là giới hạn thời lượng của một hoạt động cụ thể hoặc của toàn bộ request. Một deadline có thể bao gồm nhiều timeout con và cả thời gian chờ trong hàng đợi.

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| **Operation deadline** | Nghiệp vụ này phải hoàn tất muộn nhất khi nào? | API tạo đơn hàng có ngân sách 2,5 giây |
| **Overall request timeout** | Người gọi hoặc ingress chờ request tối đa bao lâu? | HTTP client chờ response tối đa 3 giây |
| **Per-call timeout** | Một lần gọi downstream được phép mất bao lâu? | Gọi Blob tối đa 800 ms trong ngân sách còn lại |
| **Connect timeout** | Client chờ thiết lập kết nối trong bao lâu? | TCP/TLS hoặc proxy connection tối đa 300 ms |
| **Response/read timeout** | Client chờ response hoặc dữ liệu đọc tiếp tối đa bao lâu theo semantics transport? | Chờ response từ HTTP server tối đa 900 ms |
| **Connection-pool acquisition timeout** | Chờ lấy connection khả dụng từ pool tối đa bao lâu? | Chờ pool tối đa 100 ms |
| **Idle timeout** | Kết nối không hoạt động bao lâu thì bị đóng? | Proxy đóng tunnel idle sau một khoảng thời gian |
| **Queue/lock timeout** | Một tác vụ/message có thể chờ hoặc được giữ trong bao lâu? | Service Bus message lock hoặc thời gian chờ nhận message |

Tên gọi và semantics cụ thể phụ thuộc client/transport. Ví dụ **response timeout** của một HTTP provider có thể đo thời gian chờ response/read theo từng giai đoạn, không nhất thiết giới hạn toàn bộ operation từ lúc bắt đầu tới khi đọc xong body.

### Ví dụ: timeout riêng lẻ có thể cộng dồn

Giả sử một API có ba lời gọi tuần tự:

~~~text
Request của người dùng
    ├── Database query: tối đa 2 giây
    ├── Blob upload: tối đa 2 giây
    └── Service Bus send: tối đa 2 giây
~~~

Nếu mỗi lần gọi dùng timeout 2 giây và không có deadline chung, tổng thời gian có thể vượt 6 giây, chưa tính validation, serialization, lấy token, chờ connection pool và retry.

Nếu người dùng chỉ chờ 3 giây, request có thể bị client hoặc gateway ngắt trong khi server vẫn tiếp tục upload Blob hay gửi message. Điều đó tạo ra trạng thái khó xác định: **người gọi thấy timeout nhưng tác dụng phụ có thể đã xảy ra**.

## 3. Ngân sách thời gian của một thao tác

Một operation deadline nên bao gồm toàn bộ thời gian mà hệ thống kiểm soát được:

- Chờ admission control, thread pool, scheduler hoặc connection pool.
- Xác thực và lấy token nếu cần.
- DNS, proxy, TCP, TLS và kết nối đến dịch vụ.
- Gửi request, chờ response, đọc body và xử lý kết quả.
- Retry, backoff và thời gian chờ giữa các lần thử.
- Ghi database, settlement message, cleanup và tạo response.
- Khoảng dự phòng để trả lỗi có kiểm soát hoặc hoàn tất tác vụ dọn dẹp.

### Ví dụ phân bổ ngân sách 2.500 ms

| Giai đoạn | Ngân sách minh họa | Ghi chú |
| --- | ---: | --- |
| Xác thực request, validation và admission | 150 ms | Bao gồm thời gian chờ trước nghiệp vụ |
| Database query | 450 ms | Tính cả connection-pool wait nếu thao tác cần kết nối |
| Blob upload | 850 ms | Có thể gồm nhiều HTTP request/chunk theo SDK |
| Service Bus send | 400 ms | Theo timeout của messaging client |
| Dự phòng retry/backoff | 350 ms | Chỉ dùng khi còn deadline và lỗi có thể retry |
| Hoàn tất, serialization và trả response | 300 ms | Không để hết ngân sách trước bước trả kết quả |
| **Tổng** | **2.500 ms** | Deadline của operation |

Các số trên chỉ là ví dụ để thiết kế. Ngân sách thực tế phải dựa vào SLO, phân phối latency, payload, vùng triển khai, giới hạn dịch vụ và yêu cầu nghiệp vụ.

**Không chia timeout đều cho mọi dependency.** Một truy vấn cache có thể chỉ cần vài chục millisecond; upload một tệp lớn có thể cần lâu hơn. Phân bổ theo độ quan trọng và đặc tính dịch vụ.

## 4. Deadline cha và timeout con

Khi một request gọi nhiều dependency, mỗi lời gọi con phải dùng **thời gian còn lại**, không bắt đầu một timeout mới độc lập với deadline ban đầu.

~~~mermaid
flowchart TD
    A[Inbound request: deadline 2500 ms] --> B[Validation: 150 ms]
    B --> C[Database call: tối đa 450 ms]
    C --> D[Blob call: tối đa min 850 ms, remaining]
    D --> E[Service Bus call: tối đa min 400 ms, remaining]
    E --> F[Response và cleanup]
    A -. hết deadline ở bất kỳ bước nào .-> X[Ngừng bắt đầu công việc mới / trả lỗi timeout]
~~~

Quy tắc:

\[
T_{child} = \min(T_{configured}, T_{remaining})
\]

Trong đó:

- (T_{configured}) là timeout tối đa được cấu hình cho dependency.
- (T_{remaining}) là phần ngân sách còn lại của operation.
- (T_{child}) không được lớn hơn thời gian còn lại.

Ví dụ, Blob được cấu hình tối đa 850 ms nhưng database đã tiêu thụ 1.900 ms trong ngân sách 2.500 ms. Thời gian còn lại chỉ 600 ms; Blob call phải dùng tối đa 600 ms hoặc bỏ qua nếu nghiệp vụ không còn khả năng hoàn tất an toàn.

### Deadline là hạn cuối, không phải mục tiêu phải dùng hết

Nếu thao tác hoàn thành sớm thì trả kết quả ngay. Không cần chờ đủ ngân sách. Nếu phần thời gian còn lại quá nhỏ để một lời gọi có cơ hội hoàn thành hoặc cleanup, có thể từ chối bắt đầu lời gọi mới và trả lỗi có kiểm soát.

## 5. Đo thời gian trong JVM bằng monotonic clock

Trong cùng một tiến trình JVM, nên dùng **System.nanoTime()** để đo thời lượng và deadline tương đối. Không dùng **System.currentTimeMillis()** để tính elapsed time vì đồng hồ hệ thống có thể được đồng bộ hoặc điều chỉnh.

- **Instant/UTC wall clock** phù hợp ghi timestamp và trao đổi mốc thời gian giữa hệ thống.
- **System.nanoTime()** phù hợp đo thời gian trôi qua trong một tiến trình.
- Giá trị nanoTime không phải thời điểm lịch và không được gửi sang máy khác.

### Lớp Deadline tối giản

~~~java
import java.time.Duration;

public final class Deadline {

    private final long expiresAtNanos;

    private Deadline(long expiresAtNanos) {
        this.expiresAtNanos = expiresAtNanos;
    }

    public static Deadline after(Duration budget) {
        if (budget == null || budget.isNegative() || budget.isZero()) {
            throw new IllegalArgumentException(
                    "Deadline budget must be positive");
        }

        long now = System.nanoTime();
        long durationNanos = budget.toNanos();
        return new Deadline(now + durationNanos);
    }

    public Duration remaining() {
        long remainingNanos = expiresAtNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0L, remainingNanos));
    }

    public boolean isExpired() {
        return remaining().isZero();
    }

    public Duration cap(Duration configuredTimeout) {
        if (configuredTimeout == null ||
                configuredTimeout.isNegative() ||
                configuredTimeout.isZero()) {
            throw new IllegalArgumentException(
                    "Configured timeout must be positive");
        }

        Duration remaining = remaining();
        if (remaining.isZero()) {
            return Duration.ZERO;
        }

        return configuredTimeout.compareTo(remaining) < 0
                ? configuredTimeout
                : remaining;
    }
}
~~~

Đây là helper minh họa cho ngân sách thời gian ngắn trong một tiến trình. Ứng dụng production nên bổ sung kiểm tra overflow khi chấp nhận duration rất lớn, quy tắc truyền context, metric và cách xử lý deadline đã hết. Không lưu expiresAtNanos vào database hoặc truyền qua network.

### Dùng deadline cho từng lời gọi

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

@FunctionalInterface
interface TimedCall<T> {
    T execute(Duration timeout) throws Exception;
}

public final class DeadlineCalls {

    private DeadlineCalls() {}

    public static <T> T invoke(
            Deadline deadline,
            Duration configuredTimeout,
            TimedCall<T> call) throws Exception {

        Duration timeout = deadline.cap(configuredTimeout);
        if (timeout.isZero()) {
            throw new TimeoutException("Operation deadline exceeded");
        }

        // Adapter phải thực sự áp dụng timeout nhận được
        // vào client/driver; truyền Duration một mình không tự hủy I/O.
        return call.execute(timeout);
    }
}
~~~

Ví dụ sử dụng:

~~~java
Deadline deadline = Deadline.after(Duration.ofMillis(2500));

String result = DeadlineCalls.invoke(
        deadline,
        Duration.ofMillis(850),
        timeout -> blobGateway.upload(document, timeout));
~~~

**Điều kiện quan trọng:** blobGateway.upload phải chuyển timeout vào HTTP client/SDK hoặc một cơ chế thực sự giới hạn operation. Nếu adapter bỏ qua tham số timeout, helper chỉ kiểm tra ngân sách trước khi gọi; nó không thể cưỡng chế một lời gọi I/O đang chạy.

## 6. Truyền deadline qua nhiều service

Trong kiến trúc nhiều service, deadline cần được truyền theo cách có thể diễn giải ở mỗi hop.

Có hai cách phổ biến:

- **Absolute deadline:** truyền thời điểm UTC cuối cùng, ví dụ một header nội bộ X-Request-Deadline. Service nhận tính phần còn lại từ đồng hồ UTC của nó, có tính đến clock skew.
- **Remaining timeout/budget:** truyền thời gian còn lại, ví dụ X-Request-Timeout-Ms. Service nhận khởi tạo một deadline cục bộ từ ngân sách này.

Một số giao thức như **gRPC** có cơ chế deadline/timeout riêng. Với HTTP REST, header tùy chỉnh phải có hợp đồng rõ ràng giữa các service; không nên tự nhận một header từ Internet là đáng tin.

### Quy tắc khi truyền deadline

1. Tạo deadline tại biên tin cậy đầu tiên, chẳng hạn API gateway hoặc service nhận request.
2. Nếu caller gửi timeout, áp dụng **giới hạn tối đa do service quy định**; không để caller yêu cầu hàng phút nếu API chỉ cho phép vài giây.
3. Khi gọi service con, truyền **phần ngân sách còn lại** sau thời gian đã tiêu thụ.
4. Service con không được kéo dài deadline cha.
5. Dành một khoảng dự phòng cho response, settlement và cleanup.
6. Khi deadline hết, ngừng bắt đầu công việc mới và hủy/cancel công việc đang chạy nếu client hỗ trợ an toàn.

Không truyền System.nanoTime() qua network. Mỗi tiến trình có monotonic clock riêng. Nếu truyền absolute UTC, cần tính đến sai lệch đồng hồ; nếu truyền remaining duration, cần quy định rõ đơn vị, giới hạn và cách xử lý giá trị âm/không hợp lệ.

### Ví dụ luồng nhiều service

~~~mermaid
sequenceDiagram
    participant U as API Gateway
    participant O as Orders API
    participant D as Database
    participant B as Blob service
    participant M as Service Bus
    U->>O: Request + budget 2500 ms
    O->>D: Query, timeout theo remaining
    D-->>O: Result
    O->>B: Upload, timeout theo remaining
    B-->>O: Blob reference
    O->>M: Send, timeout theo remaining
    M-->>O: Accepted
    O-->>U: Response trước deadline
~~~

Nếu database tiêu thụ 1.200 ms, Blob và Service Bus chỉ được chia phần ngân sách còn lại. Mỗi service con cũng có thể áp deadline riêng cho công việc nội bộ, nhưng không được vượt hạn cuối được caller tin cậy truyền xuống.

## 7. Phân biệt timeout ở HTTP client

Một HTTP request thường trải qua nhiều giai đoạn:

~~~text
Chờ connection pool
    → DNS
    → TCP connect
    → TLS handshake
    → gửi request
    → chờ response headers
    → đọc response body
    → xử lý kết quả
~~~

Không phải HTTP client nào cũng có một timeout bao trùm tất cả giai đoạn. Cần xem đúng semantics của transport.

| Timeout | Tác động | Ví dụ cấu hình |
| --- | --- | --- |
| Pool acquisition | Chờ connection khả dụng | Connection-request timeout |
| Connect | Thiết lập kết nối đến host/proxy | Connect timeout |
| TLS handshake | Hoàn tất bắt tay TLS | Có thể nằm trong connect/handshake timeout riêng của transport |
| Response/read | Chờ response hoặc dữ liệu đọc | Response/read timeout |
| Whole call | Từ lúc bắt đầu tới khi hoàn tất response | Request/call timeout nếu client hỗ trợ |
| Business deadline | Bao gồm queue, nhiều lời gọi và xử lý nghiệp vụ | Deadline context của ứng dụng |

### Ví dụ Spring RestClient với connect và read timeout

Với Spring Framework hỗ trợ **RestClient**, có thể cấu hình một request factory. Ví dụ dùng **SimpleClientHttpRequestFactory**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PartnerHttpConfiguration {

    @Bean
    RestClient partnerRestClient() {
        SimpleClientHttpRequestFactory requestFactory =
                new SimpleClientHttpRequestFactory();

        requestFactory.setConnectTimeout(300);
        requestFactory.setReadTimeout(900);

        return RestClient.builder()
                .requestFactory(requestFactory)
                .build();
    }
}
~~~

Ở ví dụ này:

- Connect timeout 300 ms giới hạn thời gian thiết lập kết nối theo khả năng request factory.
- Read timeout 900 ms giới hạn thời gian chờ đọc theo semantics của implementation.
- Hai giá trị **không tự tạo một operation deadline 1.200 ms**.
- Pool wait, DNS, TLS và thời gian xử lý có thể có behavior riêng theo request factory/JDK.

Nếu cần connection pool và kiểm soát chi tiết hơn, có thể dùng Apache HttpComponents hoặc một HTTP provider khác, nhưng phải cấu hình **connection acquisition**, **connect**, **response** và **overall deadline** theo đúng API của provider.

### Timeout ở WebClient/Reactor Netty

Với ứng dụng reactive, có thể cấu hình timeout ở connector và giới hạn publisher ở cấp operation:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class PartnerWebClientConfiguration {

    @Bean
    WebClient partnerWebClient() {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
                .responseTimeout(Duration.ofMillis(900));

        return WebClient.builder()
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

Giới hạn toàn operation có thể đặt ở publisher:

~~~java
Mono<PartnerResponse> response = webClient.get()
        .uri("/status")
        .retrieve()
        .bodyToMono(PartnerResponse.class)
        .timeout(Duration.ofMillis(1200));
~~~

**Mono.timeout** giới hạn thời gian publisher hoàn thành sau khi được subscribe và phát tín hiệu timeout/cancel theo semantics Reactor. Cần bảo đảm subscription bắt đầu ở đúng thời điểm đo deadline và cancellation thực sự được connector/remote client xử lý. Nó không thể hoàn tác một tác dụng phụ đã xảy ra ở server.

## 8. Timeout với Azure SDK for Java

Azure SDK for Java có nhiều builder và transport; không nên coi timeout của một Blob client là timeout chung cho mọi Azure service.

Với HTTP-based SDK, cần phân biệt:

- **HTTP transport timeout:** connect, response/read, write và các thiết lập pool tùy provider.
- **SDK retry policy:** số lần thử lại, backoff, retryable status/error và các giới hạn theo dịch vụ.
- **Service operation semantics:** upload/download có thể gồm nhiều request hoặc chunk; thời gian toàn thao tác không chỉ là một HTTP exchange.
- **Credential timeout:** Azure Identity có thể cần kết nối riêng để lấy token; cấu hình transport cho Blob chưa chắc cấu hình transport lấy token.
- **Application deadline:** bao trùm cả token acquisition, các request/chunk, retry và xử lý sau khi SDK trả về.

### Ví dụ cấu hình HTTP transport cho Blob

Với Azure Core Netty provider, có thể tạo HTTP client có connect/response timeout rồi gắn vào **BlobServiceClientBuilder**. API cụ thể cần đối chiếu phiên bản azure-core-http-netty đang được BOM quản lý.

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import java.time.Duration;

TokenCredential credential =
        new DefaultAzureCredentialBuilder().build();

HttpClient httpClient = new NettyAsyncHttpClientBuilder()
        .connectTimeout(Duration.ofMillis(300))
        .responseTimeout(Duration.ofMillis(900))
        .build();

BlobServiceClient blobClient = new BlobServiceClientBuilder()
        .endpoint(blobEndpoint)
        .credential(credential)
        .httpClient(httpClient)
        .buildClient();
~~~

Ví dụ minh họa timeout cho **HTTP transport**. Nó không bảo đảm toàn bộ upload lớn hoàn thành trong 900 ms: upload có thể chia thành nhiều request/chunk, retry và xử lý dữ liệu. Nó cũng chưa chứng minh token acquisition dùng cùng transport.

### Retry options không thay deadline

Một SDK có thể tự retry lỗi tạm thời. Nếu mỗi attempt được phép mất 900 ms và SDK retry nhiều lần, tổng thời gian có thể vượt ngân sách operation. Vì thế cần:

- Chọn retry count/backoff phù hợp với SLO.
- Kiểm tra khả năng giới hạn thời gian của từng attempt trong SDK/service.
- Đặt operation deadline ở tầng ứng dụng và không bắt đầu attempt mới khi hết ngân sách.
- Kiểm soát cancellation khi SDK hỗ trợ.
- Không lặp vô hạn với 401/403 hoặc lỗi cấu hình cố định.

Một số Azure service có **retry options riêng** và semantics khác nhau. Ví dụ Storage SDK có tùy chọn retry cho request Storage; Service Bus SDK có retry options của client messaging. Không dùng một cấu hình retry chung rồi giả định mọi SDK áp dụng giống nhau.

### Upload lớn và nhiều request

Một lần gọi nghiệp vụ upload có thể gồm:

1. Khởi tạo/kiểm tra điều kiện.
2. Upload block/chunk.
3. Retry từng request.
4. Commit block list.
5. Xử lý response và trả kết quả.

Do đó, nếu mỗi HTTP request có response timeout 900 ms, operation upload có thể dài hơn 900 ms. Cần đặt giới hạn toàn operation ở tầng phù hợp và chọn chunk size/concurrency theo kích thước file, băng thông và service limits.

## 9. Timeout cho database và connection pool

Timeout database thường có nhiều lớp độc lập:

| Loại | Ví dụ | Nếu thiếu giới hạn |
| --- | --- | --- |
| Connection pool acquisition | Hikari connectionTimeout | Thread chờ connection lâu khi pool cạn |
| Connection establishment | JDBC driver connect/login timeout | Kết nối tới DB treo do network |
| Query/statement timeout | JDBC Statement.setQueryTimeout hoặc driver-specific option | Query kéo dài chiếm connection |
| Transaction timeout | Spring transaction timeout | Transaction giữ lock/connection quá lâu |
| Socket/read timeout | Driver network timeout | Chờ dữ liệu từ DB không giới hạn phù hợp |

### Ví dụ HikariCP và JDBC

Một cấu hình minh họa:

~~~yaml
spring:
  datasource:
    hikari:
      connection-timeout: 500
      validation-timeout: 300
~~~

Đây là timeout chờ lấy connection và kiểm tra connection theo HikariCP; nó **không phải query timeout**.

Với JDBC, có thể giới hạn statement:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                     "select status from orders where id = ?")) {

    statement.setLong(1, orderId);
    statement.setQueryTimeout(1);

    try (ResultSet resultSet = statement.executeQuery()) {
        // Xử lý kết quả
    }
}
~~~

setQueryTimeout dùng đơn vị giây trong JDBC API; driver/database có thể có khác biệt về cách ngắt query. Cần kiểm tra query timeout, network timeout và transaction behavior của driver cụ thể.

### Transaction timeout và external calls

Không giữ một database transaction mở trong khi chờ upload Blob hoặc gửi Service Bus lâu nếu không cần thiết. Một transaction kéo dài có thể giữ lock/connection, tăng contention và làm hệ thống mất khả năng phục hồi.

Nên cân nhắc:

- Commit dữ liệu nghiệp vụ trước hoặc dùng outbox pattern để phát sự kiện bền vững.
- Không gọi dịch vụ cloud chậm trong transaction database nếu có thể tách bước.
- Dùng transaction timeout phù hợp và cleanup khi deadline hết.
- Thiết kế compensation/idempotency nếu nhiều dịch vụ không thể tham gia cùng một transaction phân tán.

## 10. Timeout cho messaging và background worker

Messaging có semantics khác HTTP request-response. Một consumer thường thực hiện:

~~~text
Receive message
    → Xử lý nghiệp vụ
    → Ghi dữ liệu
    → Complete / acknowledge / checkpoint
~~~

Các timeout cần phân biệt:

| Loại | Ý nghĩa |
| --- | --- |
| Receive wait timeout | Chờ có message trong khoảng thời gian nhất định |
| Message lock / visibility timeout | Khoảng thời gian consumer có quyền xử lý message trước khi message có thể được giao lại |
| Processing deadline | Thời gian tối đa cho nghiệp vụ xử lý một message |
| Settlement timeout | Thời gian dành cho complete/abandon/dead-letter/ack |
| Lock renewal | Gia hạn lock khi xử lý lâu và dịch vụ hỗ trợ |

Với Azure Service Bus, **message lock duration** và **auto lock renewal** không phải operation deadline. Nếu xử lý vượt lock, message có thể được giao lại; hai consumer có thể cùng thực hiện tác dụng phụ nếu thiết kế không idempotent.

Với AWS SQS, khái niệm **visibility timeout** có vai trò tương tự ở mức giao nhận. Với Google Cloud Pub/Sub, cần phân biệt **ack deadline** và cơ chế lease extension. Các tên gọi khác nhau nhưng cùng đặt ra câu hỏi: consumer còn giữ quyền xử lý message trong bao lâu?

### Deadline của worker

Worker nên có deadline xử lý message, đồng thời dành thời gian cho settlement. Ví dụ, nếu lock còn 30 giây và nghiệp vụ dự kiến dùng 25 giây, không nên dùng toàn bộ 25 giây cho downstream call rồi không còn thời gian complete message.

Khi deadline hết:

- Dừng công việc mới.
- Hủy downstream request nếu cancellation được hỗ trợ.
- Nếu chưa thể xác nhận kết quả nghiệp vụ, xử lý settlement theo chính sách: abandon, retry, dead-letter hoặc để lock hết hạn theo thiết kế.
- Đảm bảo lần giao lại không tạo tác dụng phụ trùng.

**Timeout không có nghĩa message đã thất bại ở phía dịch vụ.** Nếu client mất response sau khi broker đã nhận message, retry có thể gửi trùng. Dùng message ID, idempotency key, outbox/inbox hoặc deduplication phù hợp.

## 11. Retry phải nằm trong deadline

Retry có ích với lỗi tạm thời nhưng làm tăng thời gian và số request. Retry policy cần xét:

1. Lỗi có thể khôi phục không? Ví dụ 429/503 hoặc connection reset có thể retry tùy operation.
2. Operation có an toàn khi lặp không?
3. Thời gian còn lại có đủ cho attempt tiếp theo và cleanup không?
4. Dịch vụ có cung cấp **Retry-After** hoặc gợi ý backoff không?
5. Các tầng retry khác có đang cùng retry không?

### Công thức ngân sách retry

Với (n) lần thử, mỗi attempt có timeout (t_i) và khoảng backoff (b_i):

\[
T_{retry} = \sum_{i=1}^{n} t_i + \sum_{i=1}^{n-1} b_i
\]

Để operation không vượt deadline:

\[
T_{retry} \leq T_{remaining}
\]

Đây là điều kiện cần ở mức ngân sách; vẫn cần dành thời gian cho các bước trước/sau và overhead của scheduler/transport.

### Ví dụ retry có giới hạn

Ngân sách còn lại 1.000 ms, mỗi attempt tối đa 300 ms:

| Thành phần | Ngân sách |
| --- | ---: |
| Attempt 1 | 300 ms |
| Backoff 1 | 100 ms |
| Attempt 2 | 300 ms |
| Backoff 2 | 100 ms |
| Attempt 3 | 150 ms |
| Hoàn tất/cleanup | 50 ms |
| **Tổng** | **1.000 ms** |

Attempt cuối được rút xuống 150 ms vì chỉ còn ngân sách đó. Nếu SDK không hỗ trợ điều chỉnh timeout theo từng attempt, application có thể phải giảm retry count hoặc dùng cơ chế client/adapter hỗ trợ deadline.

### Exponential backoff và jitter

Backoff tăng dần giúp tránh retry liên tục:

\[
b_k = \min(b_{max}, b_0 \times 2^{k-1}) + jitter
\]

Jitter giúp các client không cùng retry đúng một thời điểm sau sự cố. Trong thực tế, cần kết hợp với **Retry-After** khi dịch vụ cung cấp và không vượt deadline còn lại.

Không retry tự động các lỗi thường mang tính cấu hình hoặc quyền như **401/403** nếu không có lý do cụ thể. Retry không sửa được tenant sai, role thiếu, endpoint không tồn tại hoặc proxy authentication sai.

## 12. Timeout, cancellation và tác dụng phụ

Timeout ở caller và dừng công việc ở server là hai sự kiện khác nhau.

~~~mermaid
sequenceDiagram
    participant C as HTTP caller
    participant A as Spring Boot API
    participant B as Azure Blob
    C->>A: Request
    A->>B: Upload
    C--xA: Caller timeout / disconnect
    Note over A,B: Server có thể vẫn đang upload
    B-->>A: Upload thành công
    Note over C,A: Caller đã không nhận được response
~~~

Nếu client timeout sau khi request đã gửi, có thể xảy ra các trạng thái:

- Azure chưa nhận request.
- Azure đã nhận nhưng chưa xử lý xong.
- Azure đã hoàn thành, nhưng response bị mất.
- Server vẫn tiếp tục công việc dù caller đã disconnect.

Do đó, không thể coi **timeout = thao tác chưa xảy ra**.

### Khác biệt giữa timeout và cancel

- **Timeout:** một giới hạn thời gian đã hết.
- **Cancel:** tín hiệu yêu cầu dừng computation/I/O đang chạy.
- **Abort:** transport/SDK thực sự ngừng request hoặc đóng tài nguyên liên quan.
- **Compensation:** thao tác nghiệp vụ khác để xử lý tác dụng phụ đã xảy ra.

Không phải client nào cũng propagate cancellation xuống socket hoặc SDK operation. Future.cancel(true) chỉ gửi interrupt; thư viện blocking có thể không phản ứng. CompletableFuture.orTimeout làm future hoàn thành bằng TimeoutException nhưng **không bảo đảm network call bên dưới đã dừng**. Reactor cancellation thường propagate qua publisher/connector, nhưng tác dụng phụ ở remote server vẫn có thể đã được thực hiện.

### Khi timeout sau một thao tác ghi

Với Blob upload, nếu timeout xảy ra khi commit block list, cần kiểm tra blob trạng thái trước khi thử lại nếu nghiệp vụ không idempotent. Với Service Bus send, message có thể đã được broker nhận dù client không nhận acknowledgment. Với database commit, transaction có thể đã commit trước khi kết nối bị ngắt.

Thiết kế bền vững thường dùng:

- Idempotency key hoặc deterministic resource/message ID.
- Conditional write/ETag nếu phù hợp.
- Outbox/inbox pattern cho database và messaging.
- Truy vấn trạng thái sau timeout khi có thể.
- Compensation rõ ràng thay vì giả định rollback tự động trên nhiều dịch vụ.

## 13. Áp dụng trong Spring Boot: một deadline cho cả request

Một cách tổ chức là tạo **Deadline context** ở tầng application service và truyền nó qua các adapter. Tránh để mỗi repository/client tự tạo timeout mặc định mà không biết ngân sách cha.

### 13.1. Ví dụ service orchestration

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.stereotype.Service;

@Service
public class OrderWorkflow {

    private final OrderRepository orders;
    private final DocumentGateway documents;
    private final EventPublisher events;

    public OrderWorkflow(
            OrderRepository orders,
            DocumentGateway documents,
            EventPublisher events) {
        this.orders = orders;
        this.documents = documents;
        this.events = events;
    }

    public OrderResult create(CreateOrderCommand command) throws Exception {
        Deadline deadline = Deadline.after(Duration.ofMillis(2500));

        ensureTime(deadline);
        Order order = orders.save(command, deadline.cap(
                Duration.ofMillis(450)));

        ensureTime(deadline);
        String blobName = documents.upload(
                command.document(),
                deadline.cap(Duration.ofMillis(850)));

        ensureTime(deadline);
        events.publish(
                new OrderCreated(order.id(), blobName),
                deadline.cap(Duration.ofMillis(400)));

        ensureTime(deadline);
        return new OrderResult(order.id(), blobName);
    }

    private static void ensureTime(Deadline deadline)
            throws TimeoutException {
        if (deadline.isExpired()) {
            throw new TimeoutException("Order operation deadline exceeded");
        }
    }
}
~~~

Các interface minh họa:

~~~java
public interface DocumentGateway {
    String upload(Document document, Duration timeout);
}

public interface EventPublisher {
    void publish(OrderCreated event, Duration timeout);
}
~~~

**Đây là pseudocode định hướng kiến trúc**: adapter phải áp dụng timeout nhận được vào SDK/driver thật và có cách báo lỗi/cancel phù hợp. Việc deadline.cap chỉ tính timeout tối đa; nó không tự đặt timeout cho JDBC hoặc Azure SDK nếu adapter bỏ qua giá trị đó.

Nếu orders.save dùng transaction, cần kiểm tra transaction timeout và connection/query timeout riêng. Không giả định Duration truyền vào gateway tự động điều khiển transaction manager.

### 13.2. Ánh xạ timeout theo dependency

| Adapter | Timeout cần cấu hình |
| --- | --- |
| JDBC repository | Pool acquisition, connection, query/statement, transaction |
| RestClient/WebClient | Connect, response/read, pool acquisition và whole publisher/request |
| Azure Blob SDK | HTTP transport, SDK retry, thời gian toàn upload |
| Azure Service Bus | Send/receive timeout, lock/renewal và settlement |
| Cosmos DB | Request/connection timeout, retry/throttling và query/page iteration |
| Key Vault | HTTP transport, retry và thời gian toàn operation |
| Executor/thread pool | Thời gian chờ queue, giới hạn concurrency và deadline trước khi bắt đầu |

## 14. Timeout ở tầng server và ingress

Ngay cả khi client/SDK đã có timeout, cần kiểm tra timeout của các lớp bao quanh request:

~~~text
External caller
    → API gateway / ingress / load balancer
        → Servlet container / reactive server
            → Spring controller
                → Application service deadline
                    → Downstream client timeouts
~~~

Quy tắc thực tế:

- Deadline của application cần đủ nhỏ để server có thể trả lỗi có kiểm soát trước khi ingress đóng kết nối.
- Client timeout nên đủ lớn để nhận response hoặc timeout có ý nghĩa từ server, nhưng không buộc người dùng chờ vô hạn.
- Không đặt server timeout dài hơn tất cả downstream timeout cộng lại nếu không có lý do.
- Với async MVC, WebFlux, background task hoặc streaming, timeout cần phù hợp lifecycle và semantics riêng; không áp một property chung cho mọi request.
- Khi caller disconnect, ứng dụng nên quyết định công việc nào có thể dừng và công việc nào phải hoàn tất để bảo đảm tính nhất quán.

**spring.mvc.async.request-timeout** chỉ liên quan đến xử lý request bất đồng bộ của Spring MVC theo cấu hình tương ứng; nó không phải timeout tổng quát cho mọi controller đồng bộ, JDBC và Azure SDK. Luôn xem timeout ở từng tầng thực tế.

## 15. Quan sát và đo lường timeout

Một hệ thống đáng tin cậy phải biết timeout xảy ra ở đâu, không chỉ đếm tổng số HTTP 500.

### Metrics nên theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| Operation duration | Thời gian tổng của nghiệp vụ |
| Deadline remaining at call start | Ngân sách còn lại khi bắt đầu dependency call |
| Per-call duration | Latency theo từng dependency/operation |
| Timeout count by phase | Timeout ở pool, connect, response, query hoặc operation |
| Retry count | Số attempt và số lần retry |
| Deadline exhausted count | Operation hết ngân sách trước khi hoàn tất |
| Cancellation count | Số tác vụ nhận yêu cầu cancel |
| Late completion count | Tác vụ hoàn thành sau khi caller đã timeout/disconnect |
| Queue/lock renewal count | Tình trạng xử lý messaging kéo dài |

### Log và trace

Nên ghi:

- Operation name, correlation/trace ID.
- Dependency/service name và operation type.
- Timeout được cấu hình và remaining budget tại thời điểm gọi.
- Attempt number, backoff duration, status/error code.
- Duration thực tế và phase gây timeout.

Không ghi access token, secret, SAS URL, connection string, payload chứa dữ liệu cá nhân hoặc toàn bộ header nhạy cảm. Tránh dùng request ID làm metric label có cardinality quá cao; đưa nó vào log/trace phù hợp hơn.

### Phân biệt latency cao với deadline quá ngắn

Một service có tỷ lệ timeout tăng có thể do:

- SLO mới quá thấp so với latency thực tế.
- Pool quá nhỏ khiến request chờ lâu trước khi gửi.
- Proxy/DNS/TLS làm tăng connect time.
- Azure throttling/429 làm tăng backoff.
- Retry ở nhiều lớp chồng nhau.
- Consumer tăng replicas nhưng downstream không scale theo.
- Network egress hoặc Private Endpoint bị nghẽn.

Không chỉ tăng timeout để che một bottleneck; xem phân vị **p50/p95/p99**, throughput, concurrency, pool saturation và error codes trước khi điều chỉnh.

## 16. Kiểm thử deadline và timeout

### 16.1. Unit test với fake clock

Không nên dùng Thread.sleep dài trong unit test để kiểm tra logic deadline. Có thể inject abstraction clock/ticker để điều khiển thời gian trôi qua và kiểm tra:

- Khi còn ngân sách, adapter nhận timeout không lớn hơn remaining.
- Khi deadline hết, không bắt đầu downstream call mới.
- Timeout con bị cap theo timeout cấu hình.
- Retry/backoff không vượt ngân sách.
- Lỗi timeout được ánh xạ sang kết quả nghiệp vụ đúng.

Lớp Deadline minh họa ở trên gọi trực tiếp System.nanoTime(). Để test deterministic, có thể tách **Ticker/MonotonicClock interface** và inject implementation giả lập.

### 16.2. Integration test với HTTP server giả

Dùng một HTTP test server có thể mô phỏng:

- Chậm thiết lập kết nối hoặc chậm trả response.
- Trả response headers nhanh nhưng body chậm.
- Đóng kết nối giữa chừng.
- Trả 429/503 cùng Retry-After.
- Nhận request nhưng không gửi response để kiểm tra timeout/cancellation.

Kiểm tra cả status/error mapping, thời gian thực tế, số lần request và việc transport có giải phóng connection hay không.

### 16.3. Test Azure SDK và managed services

Trong môi trường Azure dev/test:

1. Chạy đúng identity và endpoint của runtime.
2. Tạo Blob test hoặc Service Bus test resource có cleanup.
3. Cấu hình transport timeout/retry theo test profile.
4. Tạo tình huống lỗi mạng/403/429 có kiểm soát khi dịch vụ hoặc môi trường cho phép.
5. Kiểm tra operation deadline bao gồm thời gian SDK retry, không chỉ một HTTP request.
6. Xác nhận cancellation không khiến ứng dụng bỏ qua tác dụng phụ đã xảy ra.

Azurite hữu ích để test một phần Blob API, nhưng không mô phỏng đầy đủ Azure throttling, managed identity, RBAC, Private Endpoint hay latency của dịch vụ thật.

### 16.4. Test messaging

Với Service Bus, kiểm tra:

- Receive wait timeout.
- Processing deadline nhỏ hơn hoặc tương thích lock duration/renewal.
- Settlement timeout.
- Redelivery khi worker chết hoặc lock hết hạn.
- Idempotency khi sender không nhận acknowledgment nhưng broker đã nhận message.

Không chỉ test rằng send() ném timeout; cần xác minh message có tồn tại ở broker hay không trong môi trường test và consumer có xử lý trùng an toàn không.

## 17. So sánh với AWS và Google Cloud

| Chủ đề | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| HTTP client | Azure Core HttpClient theo transport | AWS SDK HTTP client theo service/client | HTTP/gRPC transport tùy API |
| Timeout request | HTTP transport + SDK options + application deadline | HTTP client + SDK client configuration + application deadline | Client settings/gRPC deadline + application deadline |
| Retry | Azure SDK/service retry options | SDK retry strategy và service behavior | Client retry settings và RPC behavior |
| Messaging lease | Service Bus lock/renewal, Event Hubs processing/checkpoint | SQS visibility timeout, Kinesis checkpoint | Pub/Sub ack deadline/lease extension |
| Database | JDBC/Cosmos request/query options | JDBC/DynamoDB request options | JDBC/Firestore/Spanner client options |
| Deadline propagation | Application context hoặc giao thức có hỗ trợ | Tương tự, phụ thuộc client/giao thức | gRPC có deadline semantics phổ biến |
| Vận hành | Azure Monitor/OTel và SDK diagnostics | CloudWatch/OTel và SDK metrics | Cloud Monitoring/OTel và client metrics |

Các provider khác nhau về tên property, transport và retry semantics. Một **timeout 1 giây** ở HTTP provider này không nhất thiết có cùng nghĩa với **timeout 1 giây** ở provider khác. Khi chuyển cloud, phải kiểm tra cả connect/read/operation deadline, cancellation và message lease/ack.

## 18. Bài thực hành: giới hạn một workflow 2,5 giây

**Bối cảnh:** API POST /orders thực hiện ba việc: lưu order vào database, upload chứng từ vào Blob và gửi sự kiện OrderCreated vào Service Bus. Toàn bộ request phải có deadline 2.500 ms.

### Phần A — Xác định ngân sách

1. Đặt deadline 2.500 ms tại application boundary.
2. Phân bổ thời gian cho validation, database, Blob, Service Bus, retry và response.
3. Đặt timeout cho từng adapter bằng giá trị nhỏ hơn giữa timeout cấu hình và remaining budget.
4. Đảm bảo connection-pool wait, token acquisition và retry được tính trong ngân sách.

### Phần B — Triển khai adapter

1. Với JDBC, đặt connection-pool acquisition và query/transaction timeout phù hợp.
2. Với Blob, cấu hình HTTP transport timeout và SDK retry; đo toàn upload, kể cả chunk.
3. Với Service Bus, cấu hình send timeout, tính thời gian settlement và thiết kế message ID/idempotency.
4. Truyền deadline qua application service; không tạo deadline mới cho mỗi dependency.

### Phần C — Thử lỗi

1. Cho database trả kết quả chậm hơn ngân sách dự kiến; xác nhận Blob không bắt đầu khi deadline đã hết.
2. Làm Blob request timeout sau khi server có thể đã nhận dữ liệu; kiểm tra trạng thái blob trước retry theo thiết kế.
3. Cho Service Bus send mất acknowledgment; xác minh khả năng message trùng và consumer idempotency.
4. Mô phỏng 429/503 và backoff; xác nhận tổng thời gian không vượt deadline.
5. Ngắt caller giữa lúc xử lý; kiểm tra server có tiếp tục công việc và cách xử lý tác dụng phụ.
6. Thu thập trace gồm tổng duration, per-call duration, remaining budget, attempt count và timeout phase.

### Sản phẩm cần nộp

- Sơ đồ workflow với deadline và timeout từng bước.
- Bảng timeout cấu hình theo HTTP, database, Blob và Service Bus.
- Kết quả test khi deadline còn thời gian và khi deadline hết.
- Bằng chứng retry/backoff không vượt ngân sách.
- Giải thích tình huống timeout nhưng tác dụng phụ đã xảy ra, cùng chiến lược idempotency/compensation.

### Câu hỏi tự kiểm tra

1. Vì sao ba dependency cùng có timeout 2 giây không bảo đảm API hoàn tất trong 2 giây?
2. Khác biệt giữa connect timeout, read timeout và operation deadline là gì?
3. Tại sao phải dùng System.nanoTime() để tính elapsed time trong JVM?
4. Vì sao không được truyền trực tiếp giá trị nanoTime() qua HTTP?
5. Nếu caller timeout nhưng Blob đã upload xong, API nên xử lý retry như thế nào?
6. Vì sao CompletableFuture.orTimeout() không bảo đảm hủy network request?
7. Retry có thể khiến tổng thời gian vượt deadline theo cách nào?
8. Vì sao Service Bus lock duration không phải processing deadline?
9. Query timeout khác connection-pool acquisition timeout ra sao?
10. Vì sao spring.mvc.async.request-timeout không thay thế timeout của Azure SDK?

## 19. Ghi nhớ

- **Deadline** giới hạn toàn bộ nghiệp vụ; **per-call timeout** giới hạn một bước. Mọi timeout con phải bị giới hạn bởi phần ngân sách còn lại của deadline cha.
- Ngân sách cần tính cả queue/pool wait, DNS/TLS/proxy, token acquisition, request/response, retry/backoff và cleanup.
- Dùng **monotonic clock** trong một tiến trình; khi truyền qua service, trao đổi absolute UTC deadline hoặc remaining budget theo hợp đồng rõ ràng.
- Connect/read/response timeout không tự động là whole-operation timeout. Kiểm tra semantics của HTTP transport, JDBC driver, Azure SDK và messaging client.
- Retry phải giới hạn theo deadline, backoff/jitter và idempotency. Không retry vô hạn lỗi cấu hình/quyền.
- Timeout và cancellation không chứng minh remote side effect chưa xảy ra. Cần idempotency, outbox/inbox, trạng thái kiểm tra lại hoặc compensation.
- Kiểm thử trên runtime/dependency thật và quan sát p95/p99, deadline exhaustion, retry, cancellation và late completion.

## Tài liệu tham khảo

- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Project Reactor — Mono timeout](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Azure SDK for Java — HTTP client pipeline](https://learn.microsoft.com/azure/developer/java/sdk/http-client-pipelines)
- [Azure SDK for Java — Retry policy](https://learn.microsoft.com/azure/developer/java/sdk/retries)
- [Azure Storage Blob client library for Java](https://learn.microsoft.com/java/api/overview/azure/storage-blob-readme)
- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [HikariCP configuration](https://github.com/brettwooldridge/HikariCP#gear-configuration-knobs-baby)
- [JDBC Statement API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html)

# Phân biệt timeout bên gọi với yêu cầu đã hoàn tất bên đích

Trong giao tiếp HTTP giữa các microservice, **timeout ở caller không có nghĩa server chưa xử lý request**. Caller chỉ biết rằng nó **không nhận được kết quả đúng hạn**. Tại thời điểm đó, request có thể chưa tới server, đang chạy, đã ghi dữ liệu thành công nhưng response bị chậm hoặc bị mất, hoặc đã thất bại tại server. Nếu caller lập tức gửi lại một thao tác ghi mà không có bảo vệ, hệ thống có thể tạo **đơn hàng trùng, trừ tồn kho hai lần hoặc thanh toán lặp**.

Bài thuộc chương **Thời gian chờ** trong module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Trọng tâm là phân biệt **trạng thái mà HTTP client quan sát được** với **kết quả thực tế tại instance đích**, trong bối cảnh Spring Cloud LoadBalancer định tuyến theo service ID, lấy `ServiceInstance` từ discovery/health supplier, còn RestClient, WebClient hoặc OpenFeign thực thi HTTP request. Nội dung đi từ timeline, mô hình nhất quán đến lab mô phỏng, idempotency, timeout budget, retry và khả năng quan sát.

> Nguyên tắc quan trọng nhất: **“Không nhận được response” là một trạng thái bất định, không phải bằng chứng “server đã rollback”.** Chỉ có cơ chế xác minh kết quả, idempotency hoặc hợp đồng nghiệp vụ phù hợp mới giúp caller quyết định hành động an toàn.

## 1. Một timeout có thể che giấu nhiều kết quả khác nhau

Giả sử `order-service` gửi request `POST /api/orders` đến service ID `payment-service`. LoadBalancer chọn một instance rồi HTTP client gửi request. Caller đặt response/read timeout 1 giây.

Có nhiều khả năng:

| Tình huống | Trạng thái bên đích | Caller có thể thấy | Có an toàn gửi lại POST ngay? |
|---|---|---|---|
| Không chọn được instance | Request chưa đến server đích | Lỗi chọn đích | Cần xác định lỗi discovery; retry tùy ngữ cảnh |
| Không thiết lập được kết nối | Request có thể chưa được gửi | Connection error/timeout | Cần phân loại giai đoạn và rủi ro |
| Request đã đến, server đang xử lý | Có thể commit sau khi caller timeout | Read/response timeout | **Không biết**; phải dùng idempotency/xác minh |
| Server đã commit, đang chuẩn bị response | Thao tác đã thành công | Read timeout | **Không** retry mù với key mới |
| Server đã gửi response nhưng mạng làm mất/trễ | Thao tác có thể đã thành công | Read timeout/reset | Phải xử lý như kết quả bất định |
| Server xử lý thất bại trước commit | Không tạo thay đổi mong muốn | Timeout hoặc lỗi HTTP nếu response đến | Cần xác minh và theo contract |

Không thể phân biệt mọi hàng trong bảng chỉ từ một exception `SocketTimeoutException` hoặc `WebClientRequestException`. Tên exception thể hiện **điều client quan sát**, không cho biết chắc transaction bên đích đã commit hay chưa.

### Bốn khái niệm không được đánh đồng

- **Timeout**: giới hạn thời gian chờ của một thành phần bị vượt qua.
- **Cancellation**: caller không còn muốn kết quả và có thể gửi tín hiệu ngắt; không mặc nhiên đảo ngược công việc đã làm.
- **Transaction rollback**: việc khôi phục trạng thái giao dịch theo semantics của resource manager tại server.
- **Idempotency**: gửi cùng yêu cầu nhiều lần vẫn không tạo thêm tác dụng phụ vượt quá hợp đồng đã định.

Một client hủy kết nối không có quyền tự “rollback” transaction database đã commit ở một tiến trình khác.

## 2. Timeline: caller timeout nhưng server đã hoàn tất

Ví dụ một instance nhận POST, ghi bản ghi và commit tại khoảng 300 ms, nhưng có thêm bước chậm trước khi gửi response. Caller đặt timeout 1.000 ms:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as order-service (caller)
    participant LB as Spring Cloud LoadBalancer
    participant S as payment-service instance
    participant DB as Database

    C->>LB: POST http://payment-service/api/orders
    LB-->>C: Chọn instance B
    C->>S: POST /api/orders, Idempotency-Key=abc
    S->>DB: Lưu đơn và commit
    DB-->>S: COMMIT OK ở ~300 ms
    Note over S: Response bị trì hoãn
    Note over C: Hết response timeout ở ~1000 ms
    C--xS: Caller ngừng chờ / đóng request
    S-->>C: HTTP 201 ở ~3000 ms (caller không còn nhận)
    Note over S,DB: Đơn hàng vẫn tồn tại sau timeout bên gọi
~~~

Timeline được dựng để giải thích; trong thực tế thứ tự có thể khác. Sau khi caller đóng kết nối, thao tác ghi response muộn có thể thất bại. Nhưng nếu DB đã commit, lỗi gửi response **không tự làm thay đổi kết quả commit trước đó**.

Có thể viết dưới dạng ba trục thời gian:

~~~text
t=0ms    caller bắt đầu POST, LoadBalancer chọn đích
t=300ms  server commit bản ghi #1001
t=1000ms caller timeout; UI nhận thông báo "chưa xác định kết quả"
t=3000ms server hoàn thành bước sau commit / cố gửi response
t=3500ms caller GET trạng thái theo idempotency key -> thấy #1001
~~~

Nếu caller trả về cho người dùng “thất bại chắc chắn” tại t=1000ms, người dùng có thể bấm gửi lại và tạo lần ghi mới trong khi lệnh đầu đã thành công.

## 3. Spring Cloud LoadBalancer tác động ở bước nào?

LoadBalancer chọn **nơi gửi HTTP request**, không quản lý transaction trong server đích:

~~~mermaid
flowchart TD
    A["Caller tạo request với service ID"] --> B["ServiceInstanceListSupplier: discovery, cache, health/filter"]
    B --> C{"Có ServiceInstance?"}
    C -->|Không| D["Không gửi HTTP tới instance"]
    C -->|Có| E["LoadBalancer chọn A hoặc B"]
    E --> F["HTTP transport thiết lập kết nối và gửi request"]
    F --> G["Server xử lý, có thể commit"]
    G --> H{"Response có về caller kịp timeout?"}
    H -->|Có| I["Caller biết HTTP status/response"]
    H -->|Không| J["Caller chỉ biết timeout; kết quả server bất định"]
~~~

Điểm quan trọng:

1. **Discovery và health check** cho biết các instance đủ điều kiện tại thời điểm chọn, không chứng minh request sau đó chắc chắn thành công.
2. **Round Robin, Random và chính sách khác** quyết định instance được thử, không quyết định request có commit hay không.
3. **Timeout của HTTP client** liên quan tới kết nối và nhận response; nó không truyền lệnh rollback transaction của một server đã xử lý.
4. **Retry qua LoadBalancer** có thể chọn **instance khác**. Nếu mỗi instance lưu trạng thái idempotency riêng trong RAM, retry tới instance khác có thể tạo dữ liệu trùng.
5. Cache instance list lỗi thời có thể gây lỗi kết nối; nhưng khi request đã gửi tới backend, vẫn phải xử lý kết quả bất định nếu response bị mất.

## 4. Phân biệt các loại timeout trên đường đi

“Timeout” không phải một đồng hồ duy nhất. Một request có thể đi qua nhiều giới hạn độc lập:

| Thành phần/giai đoạn | Ví dụ giới hạn | Ý nghĩa khi hết hạn |
|---|---|---|
| Chờ lấy connection từ pool | Pending acquire timeout | Có thể request chưa được gửi |
| Chọn instance / lookup discovery | Deadline ứng dụng hoặc cấu hình liên quan | Có thể chưa có đích |
| Mở TCP socket | Connect timeout | Chưa thiết lập kết nối TCP theo transport |
| TLS handshake | Handshake timeout | Không hoàn tất kênh bảo mật |
| Gửi request body | Write timeout hoặc deadline ứng dụng | Không biết server đã nhận phần nào nếu kết nối lỗi |
| Đợi response/đọc từ socket | Read/response timeout | Có thể server đang xử lý hoặc đã hoàn tất |
| Tổng thao tác nghiệp vụ | End-to-end deadline | Caller ngừng chờ vì ngân sách thời gian |
| Gateway/proxy | Upstream timeout | Proxy có thể trả HTTP 504 khi nó còn gửi được response |

Cần đọc tài liệu của **HTTP connector cụ thể** vì “read timeout” đôi khi là giới hạn chờ giữa các lần đọc, không phải toàn bộ thời gian HTTP request. Với streaming/SSE, response hợp lệ có thể giữ kết nối rất lâu và chỉ gửi heartbeat định kỳ.

### HTTP 408, 503 và 504 không tương đương exception timeout ở caller

- `408 Request Timeout` là một **HTTP status** do server gửi trong tình huống server chờ request của client quá lâu theo semantics HTTP.
- `503 Service Unavailable` là **HTTP status** báo khả năng phục vụ không sẵn sàng hoặc quá tải; có thể do server/gateway tạo ra.
- `504 Gateway Timeout` là **HTTP status** mà một gateway/proxy có thể trả khi không nhận được response từ upstream đúng hạn.
- **Client-side timeout** xảy ra khi chính HTTP client ngừng chờ; trường hợp này có thể **không nhận được HTTP status nào** từ đích.

Một số proxy sử dụng mã 499 trong log cho “client closed request”; đó không phải mã HTTP status chuẩn phổ quát, và không chứng minh request server đã rollback.

## 5. Vì sao hủy request không bảo đảm hủy tác dụng phụ?

Trong request-response HTTP thông thường, client và server là **hai tiến trình độc lập**.

Nếu caller hết hạn chờ:

- TCP connection có thể bị đóng/reset, hoặc logical HTTP/2 stream bị cancel.
- Server framework có thể phát hiện client disconnect khi ghi response hoặc nhận cancellation; không có bảo đảm phát hiện ngay trong mọi blocking operation.
- Nếu transaction đã commit, việc hủy response không tự đảo ngược dữ liệu.
- Nếu một tác vụ được chuyển sang queue/job executor, nó có thể tiếp tục ngay cả khi HTTP request gốc kết thúc.
- Một downstream service tiếp theo có thể đã nhận lệnh và xử lý thành công dù caller gốc không còn đợi.

Với `WebClient`, cancellation trong reactive pipeline có thể lan truyền upstream và giải phóng I/O; tuy nhiên nó **không phải distributed transaction rollback**. Với `RestClient` hoặc OpenFeign đồng bộ, thread gọi có thể ngừng chờ nhưng backend đã xử lý xong hay chưa vẫn cần xác minh.

**Tín hiệu cancel mang ý nghĩa “người gọi không còn đợi”, không phải “xóa toàn bộ công việc đã diễn ra”.**

## 6. Ví dụ lab: một service ghi nhận kết quả trước khi response bị trễ

Dựng một backend `payment-service` với endpoint `POST /api/orders`. Để minh họa kết quả đã hoàn tất bên đích, backend **lưu một biên nhận ngay trước khi cố ý chờ 3 giây rồi mới trả response**.

Các kiểu dùng trong lab:

~~~java
package demo.payment;

record CreateOrderRequest(String sku, int quantity) {}

record OrderReceipt(long orderId, String sku, int quantity) {}
~~~

Ứng dụng Spring MVC mẫu:

~~~java
package demo.payment;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PaymentApplication {

    private final Map<String, OrderReceipt> receiptsByKey =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(1000);

    public static void main(String[] args) {
        SpringApplication.run(PaymentApplication.class, args);
    }

    @PostMapping("/api/orders")
    ResponseEntity<OrderReceipt> createOrder(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody CreateOrderRequest request)
            throws InterruptedException {

        // Chỉ mô phỏng lưu trạng thái: một JVM, không durable.
        OrderReceipt receipt = receiptsByKey.computeIfAbsent(
            key,
            unused -> new OrderReceipt(
                sequence.incrementAndGet(),
                request.sku(),
                request.quantity()
            )
        );

        System.out.println(
            "SERVER_STORED key=" + key +
            " orderId=" + receipt.orderId()
        );

        // Chỉ dùng trong lab để tạo response đến chậm.
        Thread.sleep(3000);

        return ResponseEntity.status(HttpStatus.CREATED).body(receipt);
    }

    @GetMapping("/api/orders/by-key/{key}")
    ResponseEntity<OrderReceipt> findByKey(@PathVariable String key) {
        return ResponseEntity.of(
            Optional.ofNullable(receiptsByKey.get(key))
        );
    }
}
~~~

**Giới hạn của code demo:**

- `ConcurrentHashMap` là **in-memory state**, mất khi restart và không chia sẻ giữa các instance. Nó chỉ giúp chứng minh rằng **caller timeout không xóa trạng thái đã ghi trong cùng tiến trình**.
- `computeIfAbsent` giúp tái dùng cùng biên nhận cho một key trong tiến trình; production cần database shared, unique constraint, transaction và đối chiếu request payload.
- `Thread.sleep(3000)` là cách giả lập response chậm, **không dùng** để xử lý nghiệp vụ thật. Nếu server thread bị interrupt khi client ngắt kết nối, trạng thái đã lưu trước đó vẫn có thể tồn tại.
- Endpoint tra cứu theo key là công cụ phục vụ lab. Production cần authentication/authorization và không cho phép dò key hay xem biên nhận của người khác.
- Response `201` được dùng cho đơn giản; nếu replay một request với key cũ, production cần quy định trả lại cùng response gốc hoặc status phù hợp theo hợp đồng idempotency.

Giả sử bạn đã build ứng dụng thành `payment-service.jar`, chạy:

~~~bash
java -jar payment-service.jar --server.port=18081
~~~

Trước hết kiểm tra backend trực tiếp:

~~~bash
curl -i http://localhost:18081/api/orders/by-key/demo-001
~~~

Khi chưa có request nào dùng `demo-001`, endpoint minh họa trả `404`. Đây là trạng thái **chưa có biên nhận trong RAM của tiến trình**, không phải bằng chứng tổng quát không có giao dịch ngoài hệ thống.

## 7. Dùng curl để chứng minh client timeout không rollback

Để tách vấn đề Spring Cloud khỏi bản chất HTTP, thử gửi trực tiếp tới backend với timeout phía client ngắn hơn delay response:

~~~bash
curl -v --max-time 1 \
  -X POST "http://localhost:18081/api/orders" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-001" \
  -d '{"sku":"sku-42","quantity":1}'
~~~

Lệnh `--max-time 1` đặt deadline 1 giây cho tổng thao tác curl. Backend đã lưu biên nhận trước khi cố chờ 3 giây. Caller có thể kết thúc bằng thông báo timeout, trong khi log server đã ghi:

~~~text
SERVER_STORED key=demo-001 orderId=1001
~~~

Sau timeout, truy vấn lại:

~~~bash
curl -i http://localhost:18081/api/orders/by-key/demo-001
~~~

Kết quả dự kiến khi process vẫn chạy:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"orderId":1001,"sku":"sku-42","quantity":1}
~~~

Tức là **client không có response cho POST, nhưng trạng thái server đã thay đổi**.

Nếu chạy lại cùng lệnh POST với **chính key `demo-001`**, trong cùng một JVM, `computeIfAbsent` không tạo thêm biên nhận mới cho key đó. Nếu thay sang **`demo-002`**, server demo sẽ tạo thêm bản ghi; đó chính là rủi ro khi caller retry với key mới.

### Thực nghiệm đảo chiều

Thử điều chỉnh timeout client lớn hơn thời gian sleep, ví dụ `--max-time 5`. Khi đó caller có nhiều cơ hội nhận HTTP `201`, nhưng bản chất ghi nhận dữ liệu bên đích vẫn như trước.

Thử chủ động đóng curl trước khi có response. Tùy server, client transport và trạng thái request, backend có thể vẫn chạy hoặc phát hiện disconnect. Điều cần quan sát không phải “luôn chạy” mà là **không thể dựa riêng vào disconnect để kết luận rollback**.

## 8. Tích hợp RestClient với Spring Cloud LoadBalancer

Để thực hành đúng phạm vi module, tiếp theo đặt một caller `order-service` gọi backend bằng `http://payment-service` thay vì `localhost:18081`.

Dependencies trong Gradle có Spring Boot/Spring Cloud BOM tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Với môi trường thử nghiệm, cấu hình `SimpleDiscoveryClient`:

~~~yaml
server:
  port: 18090

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - uri: http://localhost:18081
~~~

Chỉ một instance để kết quả lab có thể tái lập. Khi thêm instance khác, cần dùng **shared durable idempotency store** trước khi thử retry ghi qua nhiều instance.

Tạo builder `@LoadBalanced` với read timeout ngắn hơn delay của backend:

~~~java
package demo.caller;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();

        factory.setConnectTimeout(1000);
        factory.setReadTimeout(1000);

        return RestClient.builder().requestFactory(factory);
    }

    @Bean
    RestClient paymentRestClient(
            RestClient.Builder loadBalancedRestClientBuilder) {
        return loadBalancedRestClientBuilder
            .baseUrl("http://payment-service")
            .build();
    }
}
~~~

Các giá trị timeout bằng mili giây trong API request factory này. Với production, chọn HTTP transport có pooling và cấu hình tương thích với phiên bản đang dùng. Đặc biệt, `read timeout` phụ thuộc request factory/connector; nó **không tương đương một deadline end-to-end duy nhất**.

### Caller gửi POST và phân biệt lỗi

~~~java
package demo.caller;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

record CreateOrderRequest(String sku, int quantity) {}

record OrderReceipt(long orderId, String sku, int quantity) {}

@Service
class PaymentGateway {

    private final RestClient paymentRestClient;

    PaymentGateway(RestClient paymentRestClient) {
        this.paymentRestClient = paymentRestClient;
    }

    OrderReceipt createOrder(String idempotencyKey) {
        return paymentRestClient.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .header("Idempotency-Key", idempotencyKey)
            .body(new CreateOrderRequest("sku-42", 1))
            .retrieve()
            .body(OrderReceipt.class);
    }

    OrderReceipt findByKey(String idempotencyKey) {
        return paymentRestClient.get()
            .uri("/api/orders/by-key/{key}", idempotencyKey)
            .retrieve()
            .body(OrderReceipt.class);
    }
}
~~~

Gọi `createOrder("demo-lb-001")` sẽ sử dụng service ID `payment-service` và LoadBalancer chọn instance 18081. Backend lưu biên nhận rồi ngủ 3 giây, trong khi RestClient có thể timeout sau khoảng 1 giây chờ dữ liệu.

Ở boundary của ứng dụng, có thể phân biệt timeout transport với HTTP response lỗi:

~~~java
try {
    OrderReceipt receipt = gateway.createOrder("demo-lb-001");
    // Có response thành công: xử lý biên nhận.
} catch (ResourceAccessException ex) {
    // Có thể là read/connect timeout hoặc I/O.
    // KHÔNG kết luận createOrder chưa thực thi ở server.
    // Chuyển sang trạng thái UNKNOWN/PENDING_VERIFICATION.
} catch (org.springframework.web.client.RestClientResponseException ex) {
    // Đã có HTTP response lỗi; phân loại theo status/contract.
}
~~~

Ví dụ `ResourceAccessException` chỉ là nhóm lỗi I/O thường gặp của RestClient; **không phải mọi lỗi chọn instance trước HTTP đều được đảm bảo thuộc class này**. Cần kiểm tra exception chain và connector thực tế, không dựa trên một catch duy nhất.

Nếu caller đã nhận `HTTP 201`, nó có bằng chứng request thành công theo contract. Nếu timeout, hãy dùng `findByKey("demo-lb-001")` để kiểm tra, thay vì tạo một POST với key mới.

## 9. Những điều cần hiểu về read timeout và connect timeout

### Connect timeout

Lỗi ở bước thiết lập kết nối thường có khả năng request chưa đến HTTP server đích. Tuy nhiên, nếu caller đang đi qua proxy, proxy kết nối/retry hoặc một connector có nhiều bước, cần dựa trên chứng cứ transport để biết chính xác yêu cầu đã được gửi tới đâu.

### Response/read timeout

Lỗi ở bước **chờ response** mang mức độ bất định cao hơn. Request có thể đã được server nhận, đã gửi tới database và đã commit. Nếu gọi lệnh ghi, hãy xem đây là **unknown outcome** cho tới khi xác minh hoặc có hợp đồng chống thực thi lặp.

### Timeout tổng

Ngay cả khi connect timeout 1 giây và read timeout 1 giây, điều đó **không có nghĩa** lời gọi luôn kết thúc trong đúng tối đa 2 giây. Nó còn có thể bao gồm thời gian chờ connection pool, discovery, TLS, chuyển hướng, nhiều lần đọc và retry tùy HTTP stack.

Vì vậy production cần **ngân sách deadline tổng** theo SLO, không chỉ hai con số timeout nằm rời rạc ở transport.

## 10. WebClient: hủy subscription không chứng minh server hủy transaction

Với WebClient, lỗi thường được phát qua tín hiệu reactive thay vì ném đồng bộ tại thời điểm tạo `Mono`.

Ví dụ WebClient dùng Reactor Netty:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1000)
        .responseTimeout(Duration.ofSeconds(1));

    return WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient));
}
~~~

Giả định `WebClient` được tạo từ builder này với `baseUrl("http://payment-service")`.

~~~java
Mono<OrderReceipt> result = paymentWebClient.post()
    .uri("/api/orders")
    .header("Idempotency-Key", "demo-web-001")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateOrderRequest("sku-42", 1))
    .retrieve()
    .bodyToMono(OrderReceipt.class);
~~~

Request thực tế thường được thực hiện khi publisher được **subscribe**, không phải ngay khi tạo biến `result`. Với response timeout, pipeline có thể phát lỗi và đóng/cancel tài nguyên kết nối. Nhưng backend đã ghi dữ liệu trước thời điểm đó vẫn có thể hoàn tất nghiệp vụ.

Có thể thêm deadline application-level:

~~~java
Mono<OrderReceipt> limited = result
    .timeout(Duration.ofSeconds(2));
~~~

`Mono.timeout` hủy upstream khi vượt ngưỡng trong pipeline reactive, nhưng cũng **không rollback giao dịch ở server**. Deadline operator và `responseTimeout` của Reactor Netty đo các khía cạnh khác nhau; cần kiểm tra tài liệu connector/phiên bản để tránh vô tình cấu hình trùng hoặc nhận định sai lúc xảy ra lỗi.

Nếu business contract cần chắc chắn sau timeout, xây thêm thao tác `GET /api/orders/by-key/{key}` theo cơ chế idempotency thay vì làm `onErrorResume(error -> createOrder(newKey))`.

## 11. OpenFeign: readTimeout cũng chỉ giới hạn thời gian caller chờ

Trong một project dùng Spring Cloud OpenFeign:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "payment-service")
interface PaymentClient {

    @PostMapping("/api/orders")
    OrderReceipt create(
        @RequestHeader("Idempotency-Key") String key,
        @RequestBody CreateOrderRequest request
    );

    @GetMapping("/api/orders/by-key/{key}")
    OrderReceipt findByKey(@PathVariable("key") String key);
}
~~~

Cấu hình Feign client theo service name:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          payment-service:
            connectTimeout: 1000
            readTimeout: 1000
~~~

Cần dependency và `@EnableFeignClients` tương ứng, đồng thời Spring Cloud LoadBalancer phải được tích hợp nếu muốn chọn instance theo service ID.

Khi `PaymentClient.create(...)` gặp read timeout, hãy phân loại nó là **caller không nhận kết quả đúng hạn**, không suy rằng server chắc chắn chưa tạo đơn. Feign có thể báo lỗi theo exception của Feign/transport như `RetryableException` tùy tình huống; cần đọc cause và cấu hình `Retryer`/`ErrorDecoder` thực tế.

**OpenFeign, RestClient và WebClient khác API và cách báo lỗi; không client nào tự bảo đảm request ghi được thực hiện đúng một lần chỉ nhờ timeout.**

## 12. Làm sao xác minh trạng thái sau timeout?

Một cơ chế thường dùng là tạo **idempotency key** khi bắt đầu thao tác nghiệp vụ và giữ nó qua mọi attempt cùng một thao tác.

~~~mermaid
flowchart TD
    A["Caller gửi POST với key K"] --> B{"Có response thành công?"}
    B -->|Có| C["Lưu result / order ID"]
    B -->|Không, timeout| D["Đánh dấu outcome UNKNOWN"]
    D --> E["GET status theo K hoặc query kết quả"]
    E --> F{"Đã có kết quả?"}
    F -->|COMPLETED| C
    F -->|PENDING| G["Chờ/backoff rồi kiểm tra tiếp"]
    G --> E
    F -->|NOT_FOUND| H["Cân nhắc retry cùng key K"]
    H --> A
    F -->|Không xác minh được| I["Giữ trạng thái UNKNOWN / đối soát"]
~~~

Mô hình này cần cẩn trọng ở nhánh `NOT_FOUND`: **không tìm thấy tại thời điểm query chưa chắc chứng minh thao tác đầu chưa được nhận hoặc chưa commit**. Server có thể đang xử lý, replication đang trễ, hoặc idempotency record chưa được ghi. Nếu retry, phải dùng **chính key K** và đảm bảo server có cơ chế xử lý atomic để hai request cạnh tranh không tạo hai kết quả.

### Trạng thái nên tách riêng

| Trạng thái theo hợp đồng API | Ý nghĩa |
|---|---|
| `PENDING` | Đã tiếp nhận, đang xử lý |
| `COMPLETED` | Tác vụ đã hoàn tất và kết quả có thể đọc |
| `FAILED` | Tác vụ thất bại theo hợp đồng, không cần tự suy từ timeout |
| `UNKNOWN` (phía caller) | Caller chưa thể xác minh kết quả |
| `NOT_FOUND` | Không có record tại nguồn được truy vấn, **không đủ** để suy ra chắc chắn chưa bao giờ nhận request |

Với thao tác kéo dài, API có thể trả `202 Accepted` và một operation ID để client poll, hoặc dùng callback/event để báo kết quả. `202` chỉ báo đã chấp nhận xử lý, không có nghĩa công việc đã hoàn tất thành công.

## 13. Idempotency key: cơ chế chống thực thi lặp thực sự

Một `Idempotency-Key` là định danh duy nhất cho **một ý định nghiệp vụ**, ví dụ “tạo đơn với giỏ hàng X”. Caller phải sinh key trước attempt đầu tiên và dùng **cùng key** khi retry hoặc khi hỏi trạng thái.

~~~text
POST key=order-7f2a -> kết quả có orderId=1001
POST key=order-7f2a -> không tạo orderId=1002
POST key=order-7f2a -> trả lại kết quả đã ghi hoặc trạng thái xử lý
~~~

Nhưng thêm header không đủ. Server phải triển khai một giao thức có tính nhất quán, ít nhất:

1. **Khóa request theo phạm vi đúng**: ví dụ tenant/account + idempotency key; không dùng key giữa các khách hàng khác nhau như cùng một thao tác.
2. **Ràng buộc nội dung**: lưu fingerprint/hash của request; nếu cùng key nhưng body khác, trả lỗi conflict như `409` theo contract.
3. **Đảm bảo atomic**: dùng unique constraint, transaction hoặc một cơ chế đồng bộ bền vững; hai request cạnh tranh với cùng key không được tạo hai bản ghi.
4. **Lưu trạng thái PENDING/COMPLETED/FAILED và kết quả** đủ lâu để caller có thể retry hoặc tra cứu theo nhu cầu.
5. **Trả lại kết quả nhất quán**: bản replay nên trả cùng operation/result hoặc trạng thái tiến trình; không thực hiện lại side effect đã commit.
6. **Dùng shared store giữa các replica**: nếu instance A và B độc lập, key trong RAM ở A không bảo vệ retry sang B.
7. **Dọn key có quy tắc**: TTL idempotency phải bao phủ khoảng caller có thể retry/đối soát, không quá ngắn.
8. **Bảo vệ quyền tra cứu**: caller chỉ được xem trạng thái của giao dịch có quyền sở hữu.

Mô hình transaction đơn giản:

~~~sql
-- Minh họa PostgreSQL; không phải toàn bộ schema production.
CREATE TABLE idempotency_records (
    tenant_id VARCHAR(100) NOT NULL,
    request_key VARCHAR(200) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    order_id BIGINT,
    PRIMARY KEY (tenant_id, request_key)
);
~~~

Một worker xử lý lệnh có thể tạo record theo unique key trong cùng transaction với việc ghi order hoặc quản lý trạng thái pending bằng quy trình riêng. Khi gặp key đã tồn tại, hệ thống kiểm tra hash và trạng thái, không tạo thêm một order mới.

**Chỉ có unique key nhưng ghi side effect ở một hệ thống khác trước khi lưu key cũng chưa đủ bảo vệ**. Với payment gateway, message broker hoặc downstream không hỗ trợ transaction chung, cần outbox, saga, key được downstream công nhận hoặc cơ chế đối soát chuyên biệt.

### HTTP method idempotent chưa phải đủ để chống gửi lặp nghiệp vụ

Theo semantics HTTP, GET/PUT/DELETE có các quy tắc idempotency riêng, còn POST thường không mặc định idempotent. Tuy nhiên, thực tế còn phụ thuộc backend: một GET bị thiết kế sai vẫn có thể thay đổi trạng thái; một PUT có thể tạo log/thông báo phụ; DELETE có thể kích hoạt side effect ngoại vi. Hãy dựa trên **contract và cách server cài đặt**, không chỉ tên HTTP method.

## 14. Retry sau timeout: chọn lại instance có thể làm rủi ro tăng lên

Spring Cloud LoadBalancer có thể chọn một instance khác cho retry, tùy cấu hình và chính sách. Ví dụ:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant LB as LoadBalancer
    participant A as Instance A
    participant DB as Shared DB
    participant B as Instance B

    C->>LB: POST key=K, attempt 1
    LB-->>C: Instance A
    C->>A: POST key=K
    A->>DB: Commit orderId=1001
    Note over C: Timeout trước khi nhận response
    C->>LB: Retry POST key=K, attempt 2
    LB-->>C: Instance B
    C->>B: POST key=K
    B->>DB: Tra cứu unique key K
    DB-->>B: Đã COMPLETED, orderId=1001
    B-->>C: Kết quả của K, không tạo đơn mới
~~~

Nếu A và B sử dụng **hai bộ nhớ idempotency độc lập**, B có thể không thấy K và tạo thêm một đơn. Do đó, giải pháp chống trùng phải đúng trong **toàn bộ phạm vi LoadBalancer có thể chọn**, không chỉ một JVM.

### Khi nào retry hợp lý?

- Retry **read-only request** khi lỗi tạm thời và ngân sách deadline còn cho phép, với kiểm tra side effect thực tế.
- Retry **ghi request** chỉ khi contract cho phép, dùng cùng key và backend xử lý idempotency chính xác.
- Giới hạn số attempts, exponential backoff/jitter khi phù hợp và tổng deadline.
- Không retry liên tiếp khi mọi instance đều quá tải hoặc circuit breaker đang mở.
- Không bật retry trùng nhau ở HTTP client, Spring Cloud LoadBalancer, gateway và service mesh.
- Theo dõi attempt number và instance được chọn để phát hiện một request nghiệp vụ tạo nhiều HTTP attempts.

Nếu mỗi request được phép tối đa ba attempts, hệ thống nhận 100 nghiệp vụ/giây có thể tạo tới 300 HTTP attempts/giây khi nhiều lần thử đều thất bại. Tải khuếch đại vào chính dependency đang yếu có thể làm timeout ngày càng nhiều.

## 15. Chia timeout budget theo deadline nghiệp vụ

Giả sử một endpoint caller phải phản hồi trong tối đa **4 giây**. Không thể để mỗi downstream có read timeout 4 giây và thêm ba retry: tổng thời gian có thể vượt rất xa deadline.

Một bản ngân sách minh họa:

| Giai đoạn | Ngân sách tham khảo |
|---|---:|
| Xác thực và xử lý đầu vào | 200 ms |
| Lookup instance / pool acquisition / kết nối | 300 ms |
| Attempt HTTP đầu tiên | 1.200 ms |
| Backoff trước retry | 200 ms |
| Attempt HTTP thứ hai | 1.200 ms |
| Ghi trạng thái/đóng response | 400 ms |
| Dự phòng cho scheduling/biến động | 500 ms |
| **Tổng** | **4.000 ms** |

Các khoảng trên là ví dụ **phân bổ ngân sách**, không phải công thức phải áp dụng cứng cho mọi client. Cần đo p95/p99 và đường đi thực tế: một attempt có thể gồm nhiều bước, timeout của request factory có semantics riêng, nhiều downstream có thể chạy nối tiếp hoặc song song.

Thực hành tốt:

- Tạo một **deadline tổng** ở boundary nghiệp vụ.
- Với mỗi attempt, dùng `remaining budget` để chọn thời gian chờ phù hợp, thay vì cho phép attempt tiếp theo tiêu trọn timeout ban đầu.
- Nếu không đủ thời gian để xác minh kết quả sau một write timeout, trả trạng thái PENDING/UNKNOWN với operation ID hoặc đưa vào luồng đối soát.
- Không kéo dài đồng bộ vô hạn chỉ để “chờ chắc chắn”, vì thread/connection pool có thể bị cạn.

## 16. Khi nào một kết quả được xem là “hoàn tất” ở server?

Câu “server đã hoàn tất” cũng cần định nghĩa chính xác:

| Mốc ở server | Có thể gọi là hoàn tất nghiệp vụ? |
|---|---|
| Controller bắt đầu nhận request | Chưa |
| Server đã parse/validate input | Chưa |
| Đã enqueue một job | Chỉ “accepted”; job có thể chưa thực thi |
| Database transaction commit thành công | Đã lưu tác dụng phụ thuộc phạm vi transaction |
| Gọi downstream payment và được xác nhận | Có thể đã hoàn tất một phần; phụ thuộc contract và đối soát |
| Đã ghi HTTP response lên socket | Chưa chứng minh caller nhận được |
| Caller đã nhận HTTP 2xx và giải mã response | Caller có bằng chứng từ contract; vẫn cần xử lý semantics nghiệp vụ |

Ngay cả database commit cũng chưa chắc đồng nghĩa **toàn bộ quy trình liên dịch vụ** hoàn tất. Một đơn hàng có thể được tạo trong DB nhưng bước trừ tồn kho hoặc gửi sự kiện còn pending. Với workflow nhiều bước, cần trạng thái operation rõ ràng, outbox/saga hoặc event-driven reconciliation.

Đừng coi `200 OK` từ một endpoint health là bằng chứng một thao tác ghi đã hoàn tất; health check chỉ đo khả dụng tại một thời điểm, không mang thông tin transaction cụ thể.

## 17. Quan sát từ hai phía để xác định kết quả

Khi tìm nguyên nhân timeout trong production, cần ghép dữ liệu **caller + LoadBalancer + server đích + database/dependency** theo cùng operation ID hoặc idempotency key.

| Nơi quan sát | Cần đo/log gì? |
|---|---|
| Caller | request ID, key, attempt, timeout type, elapsed time, deadline còn lại |
| LoadBalancer | service ID, instance đã chọn, số ứng viên, lý do không chọn được |
| HTTP transport | pool wait, connect time, TLS, request send time, time-to-first-byte, response read |
| Server | request received, handler started, side effect started, commit success/failure, response write |
| Database | transaction/unique key, order ID, commit timestamp, conflict/duplicate detection |
| Retry/resilience | attempts, backoff, instance thay đổi, circuit breaker state |
| Status API/đối soát | operation state và thời gian hoàn tất cuối |

Ví dụ log mục tiêu:

~~~text
caller: POST operation=op-42 key=K attempt=1 instance=A
server-A: received operation=op-42 key=K
server-A: committed operation=op-42 orderId=1001
caller: read_timeout operation=op-42 elapsed_ms=1000
caller: status_query operation=op-42 key=K
server-A: status_query key=K -> COMPLETED orderId=1001
caller: reconciled operation=op-42 -> SUCCESS
~~~

Đây là định dạng minh họa, không phải format mặc định của Spring Cloud. Trong hệ thống thực, đừng ghi full payment token, dữ liệu thẻ, cookie, Authorization header hoặc PII vào log. Key nhạy cảm cần được che hoặc hash khi quan sát.

### Thận trọng khi so timestamp giữa các máy

Nếu caller và server dùng clock lệch nhau, “commit trước hay sau timeout” không nên kết luận chỉ bằng cách trừ timestamp giữa hai máy. Dùng distributed trace có context nhất quán, operation ID, event ordering, monotonic time cho elapsed duration cục bộ và đồng bộ đồng hồ để hỗ trợ phân tích.

Nếu server xử lý xong nhưng proxy đã trả 504, log backend vẫn có thể ghi status thành công ở một lớp và log gateway ghi timeout ở lớp khác. Hai sự kiện **không mâu thuẫn**: chúng đo kết quả ở hai ranh giới khác nhau.

## 18. Checklist kiểm thử kết quả bất định

Bộ kiểm thử nên cố tình tạo các failure windows thay vì chỉ gọi API khỏe mạnh.

| Kịch bản | Điều cần kiểm chứng |
|---|---|
| Backend commit nhanh, response trễ hơn timeout | Caller timeout nhưng tra cứu key thấy kết quả đã có |
| Backend chết trước khi xử lý | Không có kết quả; retry theo contract |
| Backend chết sau commit, trước response | Caller thấy unknown; retry cùng key không tạo trùng |
| Mạng cắt giữa lúc gửi request body | Hệ thống không kết luận sai chưa nhận request |
| Gateway trả 504 | Đối soát được trạng thái backend thay vì coi chắc chắn rollback |
| Retry cùng key đến instance khác | Shared idempotency store không tạo side effect lặp |
| Retry cùng key nhưng body khác | Server từ chối conflict theo hợp đồng |
| Status API trả PENDING | Caller không tạo key mới; poll/backoff có giới hạn |
| Status API tạm lỗi | Caller giữ UNKNOWN và có đường đối soát |
| Read timeout quá dài | Thread/pool không bị giữ vượt SLO |
| Read timeout quá ngắn | Hệ thống không tạo hàng loạt retry giả |
| POST có hai attempt chạy chồng | Unique constraint/transaction đảm bảo một kết quả |
| Cache/discovery chứa instance đã chết | Phân biệt lỗi chọn/kết nối với transaction đã nhận |
| Response HTTP 2xx nhưng decode lỗi | Không retry POST với key mới chỉ vì client decode thất bại |

Đặc biệt kiểm thử tình huống **cùng idempotency key tới hai replica đồng thời**. Code `ConcurrentHashMap` của lab chỉ chứng minh hành vi trong một JVM; nó **không phải** test chứng minh tính idempotent phân tán.

### Kiểm thử có thể tái lập với lab

1. Chạy backend mẫu ở `localhost:18081`.
2. Gửi `POST` với `--max-time 1`, key `demo-001`; xác nhận curl báo timeout.
3. Kiểm tra log `SERVER_STORED` và `GET /api/orders/by-key/demo-001` có cùng order ID.
4. Gửi lại cùng key; xác nhận ID không đổi trong tiến trình.
5. Gửi key khác; quan sát bản ghi mới, qua đó thấy vì sao retry với key mới nguy hiểm.
6. Dùng caller RestClient `@LoadBalanced` với read timeout 1 giây; xác minh cùng hiện tượng qua service ID.
7. Thử WebClient hoặc OpenFeign với timeout tương đương, ghi loại exception/error signal thay vì giả định giống RestClient.
8. Nếu mở rộng hai instance, thay bộ nhớ demo bằng shared durable storage trước khi kết luận về idempotency.

## 19. Các lỗi thiết kế thường gặp

- Trả lỗi “tạo đơn thất bại” cho người dùng **chỉ vì caller timeout**, trong khi backend có thể đã commit.
- Hủy publisher WebClient hoặc đóng TCP rồi nghĩ transaction server tự rollback.
- Retry POST với **idempotency key mới** cho cùng một ý định nghiệp vụ.
- Chỉ lưu key trong RAM của một instance, trong khi LoadBalancer có thể chọn instance khác cho retry.
- Chỉ kiểm tra HTTP status; bỏ qua các lỗi xảy ra khi server đã xử lý nhưng response bị mất.
- Dùng status `NOT_FOUND` trên replica đọc trễ như bằng chứng request đầu không tồn tại.
- Tự nhận có exactly-once chỉ vì client retry một lần hoặc server dùng một map không durable.
- Đặt read timeout = deadline nghiệp vụ, rồi vẫn cho phép retry thêm nhiều lần.
- Retry không giới hạn khi dependency quá tải, tạo retry storm.
- Nhầm HTTP 504 từ gateway với một transaction rollback tại backend.
- Coi exception `ResourceAccessException` hay `RetryableException` là bản ghi nghiệp vụ “chưa thực hiện”.
- Thiếu correlation ID/idempotency key, khiến không thể nối log caller với commit backend.
- Trả về biên nhận từ status endpoint không có authentication hoặc phân quyền truy cập.
- Dùng key giống nhau cho hai payload khác nhau mà không phát hiện conflict.
- Bỏ qua các tác dụng phụ bên ngoài DB như thanh toán, gửi message hoặc email khi thiết kế idempotency.

## 20. Tổng kết

Khi **caller timeout**, điều chắc chắn chỉ là caller **không có kết quả đúng hạn**. Không được tự suy ra server chưa nhận request, chưa commit, đã rollback hoặc không còn xử lý. Với thao tác đọc, có thể retry thận trọng trong một deadline; với thao tác ghi, cần **idempotency key dùng lại trên mọi attempt**, **kho trạng thái chung và bền vững**, khả năng **tra cứu/đối soát kết quả** và xử lý trạng thái **UNKNOWN** rõ ràng.

Spring Cloud LoadBalancer giúp tìm và chọn `ServiceInstance` từ discovery, cache, health check và routing policy; **nó không quyết định transaction ở server**. RestClient, WebClient và OpenFeign cung cấp các cơ chế timeout khác nhau, nhưng không client nào biến timeout thành bảo đảm “chưa thực hiện”. Để giao tiếp liên dịch vụ ổn định, cần phối hợp **timeout budget, retry có giới hạn, idempotency, observability và hợp đồng xác minh trạng thái**, đặc biệt khi yêu cầu có tác dụng phụ.


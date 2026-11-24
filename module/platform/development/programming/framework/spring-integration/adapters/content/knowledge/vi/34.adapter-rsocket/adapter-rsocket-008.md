# Reconnect và resume trong RSocket Adapter

## 1. Bối cảnh: kết nối có thể mất giữa lúc xử lý message

Trong module **SPRING_INTEGRATION_ADAPTERS**, ứng dụng kết nối hệ thống ngoài với Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`. Với **Adapter RSocket**, kết nối thường được giữ lâu để trao đổi request-response, fire-and-forget hoặc luồng dữ liệu liên tục. Điều gì xảy ra nếu Wi-Fi của client mất ba giây, một node server khởi động lại, hoặc load balancer đóng một kết nối đang có request chưa trả lời?

Giả sử ứng dụng kho dùng route `inventory.events` để nhận các thay đổi tồn kho:

~~~text
Client                              Server RSocket
  |---- SETUP -------------------------->|
  |---- REQUEST_STREAM inventory.events>|
  |<---- Event #101 ---------------------|
  |<---- Event #102 ---------------------|
  |            MẤT KẾT NỐI              |
  X-------------------------------------X
  |        Kết nối được khôi phục?       |
  |        Còn Event #103, #104?        |
~~~

Cần tách ba câu hỏi:

1. **Kết nối còn hoạt động không?** Liên quan đến transport, RSocket KEEPALIVE và phát hiện lỗi.
2. **Có thể tiếp tục phiên/stream đang dở không?** Liên quan đến khả năng **resume** ở tầng RSocket.
3. **Dữ liệu hoặc thao tác nghiệp vụ có bị mất, trùng hay thực hiện hai lần không?** Liên quan đến **idempotency, lưu vết tiến độ và lưu trữ bền vững ở tầng ứng dụng**.

Bài học **Reconnect và resume** giải thích ba câu hỏi trong bối cảnh adapter/gateway của Spring Integration. Mục tiêu sau bài học là:

- Phân biệt reconnect transport, retry một request và RSocket session resume.
- Cấu hình chính sách kết nối lại với `RSocketRequester` và cơ chế resume khi cả hai phía hỗ trợ.
- Biết các điều kiện khiến resume thành công hoặc bị từ chối.
- Thiết kế consumer/producer và message flow chịu được mất mạng mà không tạo hiệu ứng nghiệp vụ ngoài ý muốn.
- Xây dựng kịch bản kiểm thử ngắt mạng, restart server, vượt thời gian giữ session và xử lý request trùng.

## 2. Từ TCP đến nghiệp vụ: các tầng phục hồi

| Tầng | Sự cố | Cách xử lý | Điều không được bảo đảm |
| --- | --- | --- | --- |
| Transport | TCP/WebSocket đóng, timeout | Mở transport mới | Request đang thực hiện tự hoàn thành |
| RSocket connection | `SETUP` cũ không còn dùng được | **Reconnect** để tạo kết nối/phiên mới | Tự tiếp tục stream cũ |
| RSocket session | Transport mất nhưng cả hai phía còn state | **Resume** nếu thương lượng và lưu frame thành công | Bảo đảm giao dịch DB chỉ chạy một lần |
| Reactor Publisher | `Mono`/`Flux` kết thúc bằng lỗi | `retryWhen` hoặc tái đăng ký có điều kiện | Retry mọi thao tác đều an toàn |
| Spring Integration | Message dở dang/không có reply | Error flow, idempotent receiver, lưu tiến độ, message store | Channel bộ nhớ tự thành durable queue |
| Nghiệp vụ | Lệnh đã được xử lý nhưng reply thất lạc | Idempotency key, uniqueness, transaction, query trạng thái | RSocket tự khử trùng lặp thao tác |

**Reconnect** và **resume** là hai chiến lược khác nhau. Reconnect mở kết nối/phiên mới cho các hoạt động tiếp theo. Resume thử nối một transport mới vào **cùng phiên RSocket còn được lưu trạng thái**, rồi trao đổi vị trí frame để truyền bù những frame cần thiết.

Trong rsocket-java, `RSocketConnector.reconnect(Retry)` và `RSocketConnector.resume(Resume)` là **hai chế độ loại trừ nhau**; nếu cùng cấu hình thì resume được ưu tiên. Đừng hiểu việc khai báo cả hai là có cơ chế dự phòng tự động từ resume sang reconnect.

## 3. Phát hiện mất kết nối: KEEPALIVE và timeout

RSocket có frame `KEEPALIVE` để thăm dò tình trạng kết nối. Phía gửi có thể cấu hình:

- **`keepAliveInterval`:** chu kỳ gửi KEEPALIVE.
- **`maxLifeTime`:** thời gian tối đa cho phép trước khi coi peer không còn phản hồi phù hợp.

Ở rsocket-java, có thể đặt trên `RSocketConnector` từ Spring:

~~~java
import java.time.Duration;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector ->
        connector.keepAlive(
            Duration.ofSeconds(20),
            Duration.ofSeconds(90)
        )
    )
    .tcp("localhost", 7000);
~~~

Đây là ví dụ lựa chọn thông số, không phải các giá trị bắt buộc cho mọi môi trường. Phải dựa vào độ trễ mạng, cấu hình proxy/load balancer, tài nguyên server và thời gian cần phát hiện lỗi.

**KEEPALIVE không phải reconnect hoặc resume.** Nó giúp phát hiện một kết nối không còn khỏe. Một timeout quá ngắn sẽ gây ngắt giả khi mạng chập chờn; một timeout quá dài khiến ứng dụng nhận ra lỗi chậm. TCP keepalive của hệ điều hành và RSocket KEEPALIVE cũng là những cơ chế khác nhau.

### Những tình huống có thể làm ngắt kết nối

| Tình huống | Dấu hiệu cần quan sát | Khả năng phục hồi |
| --- | --- | --- |
| Điện thoại đổi mạng, mất Wi-Fi ngắn | Transport đứt; client còn tiến trình | Có thể resume nếu server giữ session |
| Proxy/LB đóng kết nối idle | Transport kết thúc hoặc timeout | Cần xem cấu hình idle timeout, KEEPALIVE, resume |
| RSocket server restart | Phiên trong RAM bị xóa | Thông thường phải mở phiên mới; resume thường bị từ chối |
| Client bị kill | Subscription và state client mất | Phải tạo phiên mới, khôi phục tiến độ từ nơi lưu bền vững |
| Server vẫn chạy, nhưng handler ném lỗi nghiệp vụ | Stream/request có tín hiệu `onError` | Không nên reconnect chỉ vì lỗi validation/nghiệp vụ |
| Mất kết nối lâu hơn thời gian giữ session | Session/frame store hết hạn | Resume có thể thất bại, cần chính sách khôi phục ứng dụng |

## 4. Reconnect: tạo kết nối mới để tiếp tục nhận yêu cầu

Với Spring Framework 6, `RSocketRequester.Builder.tcp(...)` tạo requester dùng **kết nối chia sẻ**, thường thiết lập kết nối khi có request và có thể thiết lập lại cho những request tiếp theo sau khi connection cũ mất. Điều này **không có nghĩa** request-response đang dang dở hoặc request-stream cũ tự được phát lại khi không bật resume.

Ở rsocket-java, API mức thấp `RSocketConnector.reconnect(Retry)` cho phép chỉ định chính sách tái kết nối. Sau khi connection chết, lần đăng ký tiếp theo sẽ lấy `RSocket` mới; downstream request vẫn cần cân nhắc retry riêng nếu muốn tự chạy lại thao tác đã lỗi.

### 4.1. Cấu hình reconnect trên Spring RSocketRequester

Ví dụ sau dùng Spring Boot 3 / Spring Framework 6 / rsocket-java 1.1.x:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

@Configuration
class InventoryRSocketClientConfig {

    @Bean
    RSocketRequester inventoryRequester(RSocketRequester.Builder builder) {
        return builder
            .rsocketConnector(connector -> connector
                .keepAlive(
                    Duration.ofSeconds(20),
                    Duration.ofSeconds(90)
                )
                .reconnect(
                    Retry.backoff(5, Duration.ofMillis(500))
                        .maxBackoff(Duration.ofSeconds(8))
                        .jitter(0.3)
                )
            )
            .tcp("localhost", 7000);
    }
}
~~~

Ý nghĩa:

- `RSocketRequester.Builder` giữ vai trò cấu hình Spring codec, MIME và request route.
- `rsocketConnector(...)` mở đường tùy biến connector của rsocket-java.
- `reconnect(Retry.backoff(...))` đặt chính sách retry cho lần lấy connection mới theo cơ chế connector.
- `keepAlive(...)` phục vụ phát hiện peer mất kết nối.
- `tcp(...)` tạo requester cho RSocket server; ứng dụng có thể gửi nhiều request qua một connection.

Số lần retry trong ví dụ là **giới hạn**, giúp tránh một vòng kết nối vô hạn khó quản lý. Hệ thống chạy liên tục có thể chọn chính sách khác kèm giới hạn tải, quan sát lỗi và khả năng hủy. Backoff kèm jitter giúp giảm hiện tượng nhiều client đồng loạt kết nối lại ngay khi server khôi phục.

### 4.2. Reconnect không đồng nghĩa retry request

Giả sử client đã gửi lệnh tạo đơn, server ghi đơn vào DB, nhưng đường truyền mất trước khi reply đến client:

~~~text
Client                     Server                Database
   |--- createOrder #A ----->|                       |
   |                         |---- INSERT order ---->|
   |                         |<--- COMMIT -----------|
   X--- connection lost -----X                       |
   |                                                 |
   |-- reconnect (session mới) ---------------------> |
   |-- tự gửi lại createOrder #A ? ------------------>|
~~~

Nếu client tự gửi lại lệnh mà server không hỗ trợ idempotency, một đơn hàng có thể được tạo **hai lần**. Kết nối mới chỉ giúp trao đổi thêm message; nó không cho biết giao dịch trước đã commit hay chưa.

Với thao tác **chỉ đọc và không tạo hiệu ứng phụ**, retry sau lỗi transport có thể phù hợp. Ví dụ với `orders.status`:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.Exceptions;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

record OrderQuery(String orderId) {}
record OrderStatus(String orderId, String status) {}

class OrderStatusClient {
    private final RSocketRequester requester;

    OrderStatusClient(RSocketRequester requester) {
        this.requester = requester;
    }

    Mono<OrderStatus> lookup(String orderId) {
        return Mono.defer(() -> requester
                .route("orders.status")
                .data(new OrderQuery(orderId))
                .retrieveMono(OrderStatus.class))
            .timeout(Duration.ofSeconds(3))
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(300))
                    .filter(this::isRetryable)
            );
    }

    private boolean isRetryable(Throwable failure) {
        Throwable unwrapped = Exceptions.unwrap(failure);
        return unwrapped instanceof IOException
            || unwrapped instanceof TimeoutException;
    }
}
~~~

`Mono.defer` bảo đảm mỗi lần subscribe/retry tạo lại publisher request. `retryWhen` ở đây áp dụng cho **thao tác `lookup`**, không phải mọi route; timeout tổng thể và việc phân loại ngoại lệ phải điều chỉnh theo hệ thống. Các lỗi RSocket có thể được bọc trong exception khác; hàm `isRetryable` chỉ minh họa cách **lọc lỗi**, không phải bộ nhận diện đầy đủ mọi lỗi mạng. Trong production, phải phân loại exception thực tế và không retry lỗi validation/authentication hoặc lỗi nghiệp vụ vĩnh viễn.

**Không sao chép nguyên retry cho `orders.create`, chuyển tiền hoặc ghi thanh toán** khi chưa có idempotency key và xử lý trùng phía server.

## 5. Resume: tiếp tục phiên RSocket đang tồn tại

**RSocket Resume** là tính năng tùy chọn của protocol. Khi transport mất, ứng dụng có thể giữ lại trạng thái kết nối logic và các frame chưa được peer xác nhận ở mức giao thức. Client mở transport mới rồi gửi yêu cầu resume; nếu server vẫn giữ session phù hợp, hai bên thống nhất vị trí byte/frame và trao đổi lại frame còn thiếu.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: SETUP (resume enabled, token=T)
    C->>S: REQUEST_STREAM inventory.events
    S-->>C: PAYLOAD event #101
    S-->>C: PAYLOAD event #102
    Note over C,S: Transport gián đoạn, hai bên còn session state
    C->>S: New transport + RESUME(token=T, positions)
    S-->>C: RESUME_OK(last received position)
    Note over C,S: Truyền bù frame còn thiếu nếu đủ dữ liệu lưu
    S-->>C: Tiếp tục PAYLOAD
~~~

Sơ đồ mô tả một **lần resume thành công**. Nó không nói rằng event đã được ghi vào database, chuyển tiếp qua Kafka hoặc xác nhận ở tầng nghiệp vụ.

### 5.1. Điều kiện bắt buộc

1. Client yêu cầu hỗ trợ resume từ khi mở phiên ban đầu (`SETUP` có cờ resume và token).
2. Server **có bật và chấp nhận resume**, không chỉ hỗ trợ RSocket request-response.
3. Client và server còn **state của phiên cũ** và thông tin định vị các frame đã nhận/gửi.
4. Các frame cần truyền bù vẫn nằm trong **frame store** và phiên chưa hết thời gian lưu.
5. Client kết nối lại đến instance có thể tìm đúng session theo token. Với nhiều server instance, không thể tùy ý chuyển node nếu state chỉ được giữ trong RAM cục bộ.
6. Các thuộc tính phiên như data MIME type, metadata MIME type và định dạng mã hóa **không thay đổi** giữa phiên cũ và lần resume.

Resume là nỗ lực phục hồi có điều kiện; client luôn phải chuẩn bị trường hợp thất bại.

### 5.2. RESUME, RESUME_OK và REJECTED_RESUME

| Frame/tín hiệu | Ý nghĩa |
| --- | --- |
| `SETUP` có resume flag/token | Client yêu cầu phiên có khả năng resume ngay từ đầu |
| `RESUME` | Client chủ động đề nghị tiếp tục phiên qua transport mới với token và vị trí đã nhận |
| `RESUME_OK` | Server chấp nhận, trả vị trí đã nhận từ client |
| `ERROR[REJECTED_RESUME]` | Server từ chối tiếp tục phiên: token lạ, state hết hạn hoặc frame không còn phù hợp |
| `KEEPALIVE` | Dùng theo dõi kết nối và hỗ trợ việc xác định tiến độ nhận ở tầng protocol |

Khi nhận `REJECTED_RESUME`, không được tiếp tục thử resume mãi với cùng phiên đã bị từ chối. Ứng dụng cần chuyển sang **quy trình khởi tạo session mới**, đồng thời quyết định có cần truy vấn trạng thái hay khôi phục dữ liệu theo checkpoint nghiệp vụ.

### 5.3. Vị trí frame khác checkpoint nghiệp vụ

RSocket dùng vị trí truyền nhận của những frame có ngữ nghĩa resumable để tìm đoạn phải truyền lại. Đây là cơ chế ở **tầng giao thức**. Nếu application đã nhận event nhưng chưa commit xử lý, vị trí frame không cho biết ứng dụng đã ghi xong dữ liệu.

Ví dụ:

~~~text
Frame  event #102 đã tới client
  -> Consumer đã decode
  -> Spring Integration nhận message
  -> Database transaction chưa COMMIT
  -> Mất kết nối
~~~

Một lần resume thành công không nhất thiết làm lại giao dịch DB bị hỏng ở bước cuối. Để bảo đảm hiệu ứng nghiệp vụ, cần một checkpoint/idempotency key ở tầng ứng dụng hoặc một nguồn event có offset bền vững và khả năng replay.

## 6. Cấu hình resume phía server và client

Trong rsocket-java, `io.rsocket.core.Resume` là cấu hình cho resume. Mặc định tính năng này **không được bật** trên `RSocketConnector` và `RSocketServer`. Đoạn dưới minh họa cấu hình cùng Spring Boot 3; cách khởi tạo bean có thể cần điều chỉnh nếu ứng dụng tự tạo server hoặc dùng phiên bản thư viện khác.

### 6.1. Server: bật resume bằng customizer

~~~java
import io.rsocket.core.Resume;
import org.springframework.boot.rsocket.server.RSocketServerCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class RSocketServerResumeConfiguration {

    @Bean
    RSocketServerCustomizer enableResume() {
        return server -> server.resume(new Resume());
    }
}
~~~

Với server RSocket TCP do Spring Boot khởi tạo, cấu hình transport vẫn cần hiện diện:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

`RSocketServerCustomizer` nhận đối tượng `io.rsocket.core.RSocketServer`, và `server.resume(new Resume())` cho phép server hỗ trợ phiên resumable. **Bật bean này không bảo đảm mọi yêu cầu sẽ được resume**: server phải giữ được session/frame trong khoảng thời gian yêu cầu, client cũng phải bật resume và LB phải chuyển request tới nơi có session đúng.

### 6.2. Client: bật resume ngay từ SETUP

~~~java
import io.rsocket.core.Resume;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
class RSocketResumeClientConfiguration {

    @Bean
    RSocketRequester resumableRequester(RSocketRequester.Builder builder) {
        return builder
            .rsocketConnector(connector ->
                connector.resume(new Resume())
            )
            .tcp("localhost", 7000);
    }
}
~~~

Client có thể tiếp tục sử dụng route của Spring:

~~~java
Flux<InventoryEvent> events = resumableRequester
    .route("inventory.events")
    .data(new InventorySubscription("warehouse-a"))
    .retrieveFlux(InventoryEvent.class);
~~~

Ở đây `InventoryEvent` và `InventorySubscription` là **DTO minh họa**. Trong chương trình chạy thực tế, định nghĩa các kiểu này theo hợp đồng payload và codec đã chọn. Ví dụ không thêm `retryWhen` tùy ý vì việc retry một `Flux` sau lỗi có thể tạo một **subscription mới**, khác với resume subscription cũ.

### 6.3. Các thiết lập cần rà soát khi vận hành

`Resume` và connector của phiên bản rsocket-java cụ thể cung cấp điểm cấu hình về:

- **Thời gian giữ phiên:** timeout trước khi session không còn có thể resume.
- **Retry/backoff của resume:** bao nhiêu lần và khi nào thử mở lại transport.
- **Resume token:** định danh đủ duy nhất để server tìm session cũ.
- **Frame store:** lưu frame có thể cần truyền lại; bộ nhớ và thời gian giữ phải có giới hạn.
- **Keepalive:** phát hiện đứt kết nối trước khi hết thời gian ứng dụng sẵn sàng chờ.

Không áp dụng một cấu hình số cố định cho mọi server. Khi chọn timeout và frame store, phải tính đến lượng stream, băng thông lúc mất mạng, tốc độ phát event, số client đồng thời và mức sử dụng bộ nhớ. Resume frame buffer có thể tăng nhanh khi nhiều client mất kết nối mà server vẫn tạo dữ liệu liên tục.

## 7. Reconnect và resume ảnh hưởng thế nào đến Spring Integration?

Một luồng inbound đơn giản:

~~~mermaid
flowchart LR
    A["RSocket client"] --> B["RSocket responder / inbound gateway"]
    B --> C["MessageChannel"]
    C --> D["IntegrationFlow"]
    D --> E["Service / DB / queue"]
    E --> F["Reply"]
    F --> A
~~~

Nếu **reconnect** tạo phiên mới, request cũ có thể thất bại và client phải quyết định gửi lại. Nếu **resume** thành công, RSocket cố duy trì phiên/stream cũ trên transport mới. Tuy nhiên **`MessageChannel` không mặc nhiên lưu trữ message bền vững**: ví dụ `DirectChannel` xử lý đồng bộ, còn queue/channel store phải được cấu hình riêng nếu cần khả năng tồn tại sau restart.

Trong Spring Integration, các điểm cần cân nhắc gồm:

| Thành phần | Khi mất kết nối | Điều cần thiết kế |
| --- | --- | --- |
| Inbound RSocket gateway / `@MessageMapping` | Request đầu vào có thể lỗi, bị hủy hoặc tiếp tục nếu resume thành công | Timeout, mapping exception, correlation ID |
| `MessageChannel` | Message đã vào channel có thể đang được xử lý | Sự khác nhau giữa bộ nhớ và lưu trữ bền vững |
| `IntegrationFlow` | Handler có thể chạy xong trước khi reply gửi được | Idempotent receiver và kết quả có thể truy vấn lại |
| Outbound RSocket gateway | Reply từ hệ thống ngoài có thể không đến | Chính sách retry theo tính chất route |
| Error flow / `errorChannel` | Thu nhận lỗi ở các ranh giới được cấu hình | Phân loại lỗi vận chuyển và lỗi nghiệp vụ |
| Database / event store | Commit có thể xảy ra độc lập với reply RSocket | Transaction, unique key, checkpoint và replay |

Không nên coi `errorChannel` là một dịch vụ lưu bền hoặc một công cụ tự động khôi phục request. Nó chỉ tham gia đường xử lý lỗi khi flow được cấu hình để chuyển lỗi qua đó.

### 7.1. Phân biệt lỗi request với lỗi kết nối

Giả sử client gọi route `orders.submit`, handler Spring Integration từ chối vì `quantity = -1`. Dù đây là tín hiệu lỗi trên RSocket, **mở lại kết nối không làm số lượng trở thành hợp lệ**. Chính sách retry phải lọc theo nhóm lỗi:

- **Có thể tạm thời:** đứt transport, peer không trả lời trong thời gian giới hạn, một số tình huống quá tải có retry-after rõ ràng.
- **Không nên retry tự động:** payload sai schema, dữ liệu không hợp lệ, thiếu quyền, route không tồn tại, lỗi hợp đồng.
- **Không rõ kết quả:** timeout khi thao tác có side effect. Phải kiểm tra trạng thái bằng request ID hoặc idempotency trước khi quyết định thực thi lại.

## 8. Bảo đảm nghiệp vụ: idempotency và checkpoint

Resume ở tầng RSocket giúp nối lại stream trong điều kiện phù hợp. Nó **không phải exactly-once delivery/processing ở tầng nghiệp vụ**. Kết quả quan trọng thường là *effective-once* dựa trên thiết kế deduplication và transaction.

### 8.1. Mẫu idempotency key cho lệnh ghi

Client gửi một request ID không đổi khi thử lại:

~~~json
{
  "requestId": "8cfa2e7b-0a94-4d0b-a9fe-88e6a640b2a5",
  "orderId": "ORD-102",
  "quantity": 3
}
~~~

Server cần xử lý tương đương:

~~~text
BEGIN TRANSACTION
  1. Kiểm tra/ghi requestId với UNIQUE constraint.
  2. Nếu đã xử lý: đọc kết quả của lần đầu và trả lại.
  3. Nếu mới: thực hiện thao tác nghiệp vụ.
  4. Ghi kết quả ứng với requestId.
COMMIT
~~~

Quy tắc 1–4 phải được thực hiện **nguyên tử trong ranh giới transaction phù hợp**. Mẫu đơn giản kiểu `if (!seen) { createOrder(); seen.add(id); }` trong một `ConcurrentHashMap` không bảo đảm an toàn khi có nhiều instance hoặc restart. Với hệ thống gửi event sang Kafka/JMS, có thể cần transactional outbox hoặc một thiết kế deduplication nhất quán với broker.

Khi reply thất lạc, client có thể gửi lại **cùng request ID** hoặc gọi route `orders.status` để biết server đã tạo đơn chưa. Client không tạo request ID mới cho mỗi lần retry của cùng một ý định nghiệp vụ.

### 8.2. Checkpoint cho event stream

Với route `inventory.events`, mỗi event nên có `eventId` hoặc một vị trí đơn điệu theo phạm vi thích hợp, ví dụ `sequence`:

~~~json
{
  "eventId": "stock-000103",
  "sequence": 103,
  "sku": "SKU-18",
  "available": 42
}
~~~

Một consumer có thể:

1. Nhận event qua RSocket.
2. Bắt đầu transaction, kiểm tra eventId đã xử lý chưa.
3. Ghi thay đổi nghiệp vụ và checkpoint `sequence=103` trong cùng transaction.
4. Commit rồi mới cập nhật trạng thái tiến độ mà ứng dụng sử dụng.
5. Nếu reconnect tạo session mới, yêu cầu server **replay từ checkpoint** nếu server có event log bền vững và route hỗ trợ `fromSequence`.

**Lưu ý:** `fromSequence` là **tham số hợp đồng nghiệp vụ do bạn định nghĩa**, không phải tính năng mặc định của RSocket Resume. Để replay sau server restart, phía nguồn phải có nơi lưu event/offset bền vững; chỉ một stream trong RAM không thể tự phát lại event cũ.

### 8.3. Backpressure không thay thế durability

RSocket truyền `REQUEST_N` để điều phối nhu cầu nhận trong request-stream/channel. Khi một bên tạm thời không nhận nhanh được, backpressure giúp giảm áp lực phát dữ liệu. Nhưng nếu peer chết và session không thể phục hồi, **backpressure không thể xây lại state đã mất**. Cần thiết kế frame store có giới hạn, buffer hợp lý và cơ chế replay từ nguồn dữ liệu nếu muốn giữ lịch sử.

## 9. Chọn chiến lược theo tình huống

| Tình huống | Lựa chọn chính | Vì sao |
| --- | --- | --- |
| Gửi truy vấn trạng thái đơn, request-response | Reconnect + retry có lọc lỗi và timeout | Đọc trạng thái thường an toàn để thử lại |
| Gửi lệnh tạo đơn/thanh toán | Reconnect + idempotency key, query kết quả trước retry không an toàn | Reply có thể thất lạc sau commit |
| Stream telemetry có thể bỏ sót một vài mẫu | Reconnect + subscribe lại, lưu metric mất dữ liệu | Đơn giản, chi phí thấp |
| Stream thay đổi dữ liệu cần giữ tính liên tục khi mất mạng ngắn | Resume nếu cả hai phía và LB hỗ trợ; kết hợp checkpoint | Tiếp tục stream ngắt quãng, có phương án khi resume thất bại |
| Consumer phải khôi phục sau restart client/server | Reconnect + replay từ event log/offset bền vững | Resume dựa vào state của phiên còn tồn tại |
| Nhiều instance phía server với LB | Sticky routing/session-aware resume hoặc cơ chế state chia sẻ được thiết kế | Resume token phải tìm đúng state phiên |
| Route được publish cho nhiều client công nghệ khác nhau | Công bố rõ resume capability và fallback | Không phải mọi RSocket implementation đều hỗ trợ resume |

Không nên bật resume chỉ vì nghe có vẻ “an toàn hơn”. Tính năng này tiêu tốn bộ nhớ lưu frame, phức tạp hóa vòng đời session và đòi hỏi tích hợp giữa client, server và cân bằng tải. Chọn dựa trên yêu cầu phục hồi thực tế và khả năng vận hành.

## 10. Kịch bản kiểm thử reconnect và resume

### 10.1. Phân biệt hai đường kiểm thử

**Đường A — Reconnect:** tắt resume, cấu hình chính sách reconnect, dùng một route request-response. Làm server không sẵn sàng ngắn hạn, phục hồi server rồi gửi **request mới**. Kết quả cần chứng minh là request mới có thể dùng kết nối mới; request cũ đã thất bại không mặc nhiên tự hoàn tất.

**Đường B — Resume:** bật resume **trên cả client lẫn server**, mở một request-stream và theo dõi sự kiện. Cắt transport trong khoảng thời gian nhỏ hơn session lifetime **nhưng giữ tiến trình server/client hoạt động**. Sau đó cho client kết nối lại đến đúng server. Kiểm tra stream còn tiếp diễn và không thất lạc các payload có thể resume trong điều kiện test.

### 10.2. Ma trận test

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Mất TCP trong thời gian ngắn, cả hai phía giữ session | Resume có thể thành công nếu frame còn đủ |
| Resume không bật ở server | Client không thể resume phiên, phải xử lý lỗi |
| Restart server xóa in-memory session | Resume thường bị từ chối; fallback tạo phiên mới |
| Chờ quá session timeout | Resume có thể thất bại, không retry vô hạn token cũ |
| Chuyển request resume sang instance LB không có state | Resume thất bại trừ khi có cơ chế lưu/định tuyến state phù hợp |
| Đang tạo đơn, commit xong nhưng reply thất lạc | Request ID bảo đảm lần retry không tạo đơn thứ hai |
| Đang nhận event #102, gián đoạn trước checkpoint #102 | Sau fallback replay, event trùng được nhận diện và xử lý an toàn |
| Mất mạng trong request-stream có backpressure | Theo dõi bộ nhớ/frame store, giới hạn buffer và các tín hiệu cancel/error |
| Dừng ứng dụng chủ động | Không coi `dispose`/shutdown là mất mạng có thể resume vô hạn |

Không nên chỉ kiểm thử bằng cách gọi thẳng Java method của `@MessageMapping` hoặc `IntegrationFlow`: cách đó bỏ qua transport, SETUP, KEEPALIVE, RESUME và frame store. Tạo test đi qua RSocket client/server thật hoặc môi trường test tương đương; bổ sung kiểm tra nghiệp vụ bằng database hoặc event store khi có side effect.

### 10.3. Điều cần quan sát

Log/metrics nên có:

- Số lần thiết lập kết nối mới, retry/reconnect và thời gian đến khi thành công.
- Số lần đề nghị resume, chấp nhận `RESUME_OK`, từ chối `REJECTED_RESUME`.
- Tuổi session, số lượng session chưa hết hạn, dung lượng frame store và tỉ lệ dọn dẹp.
- Số lượng active streams, error/cancel, timeout, backpressure và độ trễ trả lời.
- Correlation ID, request ID, event ID và số lần deduplication ở tầng nghiệp vụ.

Không ghi ra log token xác thực, resume token hoặc toàn bộ payload nhạy cảm. Phân biệt việc server **khởi động lại** với việc chỉ **ngắt transport** khi phân tích kết quả test.

## 11. Lỗi thường gặp và cách khoanh vùng

| Biểu hiện | Điều cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Client kết nối lại nhưng stream cũ không tiếp tục | Có đang chạy reconnect thay cho resume? | Xác nhận hai phía bật resume ngay từ SETUP |
| `REJECTED_RESUME` sau khi server restart | State/token phiên đã mất | Tạo phiên mới và phục hồi từ checkpoint bền vững |
| Resume thành công nhưng thiếu sự kiện nghiệp vụ | Checkpoint nằm sau/before transaction, nguồn không lưu event | Dùng event log và replay + deduplication |
| Mỗi lần mất mạng lại tạo thêm một đơn | Retry lệnh ghi mà không có idempotency | Giữ request ID, xử lý transaction và unique constraint |
| Reconnect liên tục làm quá tải server | Retry không có backoff/jitter hoặc giới hạn | Backoff, jitter, giới hạn retry, giám sát |
| Session sống lâu, RAM tăng | Frame store tích lũy khi client không nhận | Giới hạn session lifetime/buffer, kiểm soát stream |
| LB chuyển client sang server khác, resume lỗi | Session state cục bộ không ở node mới | Sticky routing hoặc cơ chế session state hỗ trợ |
| Không phát hiện disconnect nhanh | KEEPALIVE/maxLifetime, LB idle timeout | Tinh chỉnh interval, lifetime và timeout môi trường |
| Message đã vào channel nhưng không reply | Handler bị treo, lỗi nghiệp vụ, message không có reply path | Kiểm tra `MessageChannel`, `IntegrationFlow`, timeout và error handling |
| `retryWhen` khôi phục một phần, sau đó lại sinh stream mới | Retry tạo subscription mới | Phân biệt replay nghiệp vụ với protocol resume và chọn đúng cơ chế |

Khi điều tra, đi theo thứ tự: **transport → KEEPALIVE/SETUP → reconnect hoặc RESUME/RESUME_OK → RSocket route → codec → Spring Integration channel → giao dịch nghiệp vụ → reply/checkpoint**. Không gộp mọi vấn đề thành “RSocket tự reconnect lỗi”.

## 12. Thực hành và câu hỏi tự kiểm tra

### Bài tập A — Reconnect có kiểm soát

Tạo client gọi route `orders.status` mỗi vài giây, cấu hình backoff và thử tắt/mở server. Ghi thời điểm connection lỗi, thời điểm request mới thành công và số lần retry. Giải thích request đang chờ tại thời điểm server tắt có tự chạy lại hay cần code retry ở tầng Publisher.

### Bài tập B — Resume request-stream

Tạo route `inventory.events` phát sequence tăng dần. Bật resume ở cả hai phía, mô phỏng mất transport ngắn nhưng **không restart tiến trình server**. Kiểm tra nhận đủ sequence khi phiên còn hợp lệ; sau đó lặp lại bằng cách restart server và quan sát đường fallback.

### Bài tập C — Không tạo trùng đơn hàng

Tạo route `orders.submit` có `requestId`. Mô phỏng server commit thành công nhưng reply bị mất, rồi retry cùng `requestId`. Hoàn thiện xử lý idempotent ở storage để tổng số đơn tạo ra vẫn bằng một. Giải thích tại sao `MessageChannel` và RSocket Resume không tự bảo đảm điều này.

### Bài tập D — Chọn chiến lược

Cho ba hệ thống: dashboard theo dõi nhiệt độ bỏ sót dữ liệu được; luồng CDC cần đủ event; API tạo hóa đơn có thể bị retry. Đề xuất cơ chế cho mỗi hệ thống, chỉ rõ khi nào cần resume, khi nào cần log/checkpoint và khi nào bắt buộc dùng idempotency key.

## 13. Tổng kết

- **KEEPALIVE** hỗ trợ phát hiện mất kết nối; **reconnect** mở kết nối mới cho các request tiếp theo; **resume** cố gắng giữ phiên và stream đang tồn tại khi state cần thiết vẫn còn.
- Trong rsocket-java, `reconnect(Retry)` và `resume(Resume)` là hai chế độ thay thế nhau. Resume cần bật cả client lẫn server, đúng token/session, còn frame lưu và chưa quá hạn.
- Resume có thể bị từ chối, đặc biệt khi server restart, hết hạn session hoặc client được đưa tới node không giữ state.
- **Retry một Publisher** là quyết định ở tầng ứng dụng. Retry sau lỗi không đồng nghĩa với protocol resume và có thể chạy lại side effect.
- Spring Integration cần timeout, error handling, idempotency, checkpoint và lưu trữ bền vững phù hợp để đạt yêu cầu nghiệp vụ sau mất mạng.
- Hãy kiểm thử cả mất transport ngắn lẫn restart/thất bại resume, và luôn xác minh trạng thái trong database/event store đối với thao tác ghi.

## Tài liệu tham khảo

- [RSocket Protocol — Resuming Operation](https://rsocket.io/about/protocol/): điều kiện resume, RESUME, RESUME_OK, REJECTED_RESUME và implied positions.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, connection setup và cách tùy biến `RSocketConnector`.
- [RSocket Java — RSocketConnector API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html): `reconnect`, `resume`, `keepAlive` và giới hạn giữa các chế độ.
- [RSocket Java — RSocketServer API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html): cấu hình hỗ trợ resume phía server.

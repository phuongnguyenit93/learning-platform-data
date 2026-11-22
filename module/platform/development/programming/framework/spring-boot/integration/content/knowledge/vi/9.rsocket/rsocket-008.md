# Phân biệt timeout, reconnect và cơ chế resume theo thư viện trong RSocket

RSocket kết hợp nhiều kiểu tương tác bất đồng bộ trên một kết nối dài hạn: request-response, fire-and-forget, request-stream và request-channel. Khi tích hợp RSocket vào Spring Boot, ba khái niệm rất dễ bị gộp thành một là **timeout**, **reconnect** và **resume**. Chúng giải quyết ba vấn đề riêng:

- **Timeout**: quyết định *đợi một thao tác hoặc một tín hiệu tối đa bao lâu* trước khi coi là quá hạn.
- **Reconnect**: tìm cách *tạo lại kết nối/phiên truyền thông mới* sau khi kết nối cũ mất hoặc không thiết lập được.
- **Resume**: cố gắng *khôi phục phiên RSocket cũ cùng trạng thái các stream và frame chưa đồng bộ* sau khi mất kết nối vật lý, nếu cả client và server còn đủ trạng thái.

Đây là bài thuộc chương **RSocket** của **SPRING_BOOT_INTEGRATION**, module chuyên tổ chức các luồng tích hợp hệ thống trong Spring Boot qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và adapter của Spring Integration. Vì vậy, ngoài API Reactor/RSocket, bài còn làm rõ ranh giới giữa truyền tải và nghiệp vụ, tính an toàn khi phát lại, giao dịch, xử lý trùng lặp, giới hạn tài nguyên, kiểm thử và quan sát vận hành.

**Phạm vi phiên bản:** Ví dụ cấu hình Spring theo mô hình Spring Boot 3.x, Spring Framework 6.x và rsocket-java 1.x, minh họa API của `RSocketRequester.Builder`, `RSocketConnector` và `RSocketServerCustomizer`. Khi nâng phiên bản Boot/Framework/rsocket-java, đối chiếu chữ ký API của phiên bản dự án trước khi áp dụng. Thư viện khác nền Java, hoặc gateway/broker trung gian, có thể không hỗ trợ resume hoặc có chính sách reconnect khác.

## 1. Một tình huống thực tế cần cả ba khái niệm

`order-service` mở kết nối RSocket đến `inventory-service` để gửi yêu cầu kiểm tra tồn kho và nhận luồng cập nhật tồn kho. Trên đường truyền có thể xảy ra nhiều kiểu gián đoạn:

1. `inventory-service` vẫn kết nối nhưng truy vấn SQL quá chậm; một request chờ quá 800 ms.
2. Kết nối TCP hoặc WebSocket bị mất vì proxy reset, mạng chập chờn hay pod bị di chuyển.
3. Trong lúc mất mạng ngắn, client vẫn muốn giữ request-stream đang theo dõi tồn kho và nhận tiếp các frame còn thiếu khi đường truyền quay lại.

Từ phía client, cả ba tình huống đều có vẻ như “đang đợi thì không nhận dữ liệu”, nhưng giải pháp khác nhau:

| Sự cố | Cơ chế chính | Kết quả mong muốn | Điều cơ chế không bảo đảm |
| --- | --- | --- | --- |
| Một request quá hạn | Timeout cấp thao tác | Dừng đợi và trả lỗi/đi đường dự phòng | Tự tái lập kết nối hoặc rollback side effect |
| Transport mất và muốn phục vụ request mới | Reconnect | Có RSocket mới, tạo SETUP và tiếp nhận request tiếp theo | Giữ nguyên stream cũ hoặc bảo đảm replay |
| Transport mất ngắn, trạng thái phiên còn | Resume | Bắt lại đúng phiên đã nhận diện và tiếp tục các stream/frame còn thiếu | Thành công khi server restart/mất state hoặc lưu dữ liệu mãi |
| Caller muốn thử lại một business command | Retry request | Phát lại thao tác theo retry policy | Chỉ xử lý nghiệp vụ một lần nếu không có idempotency |

Sơ đồ quyết định:

~~~mermaid
flowchart TD
    A["Một RPC/stream có vấn đề"] --> B{"Chỉ thao tác quá hạn?"}
    B -->|Có| C["Timeout: phát lỗi/cancel; xử lý kết quả chưa rõ"]
    B -->|Không: mất transport| D{"Cả hai phía có bật resume và còn session/frame?"}
    D -->|Có| E["Gửi RESUME, chờ RESUME_OK; tiếp tục phiên cũ"]
    D -->|Không/Resume bị từ chối| F["Kết nối mới bằng SETUP nếu chính sách cho phép"]
    F --> G["Khôi phục nghiệp vụ bằng đọc lại/re-subscribe/retry idempotent"]
    C --> H["Quyết định fallback/retry theo hợp đồng"]
    E --> I["Theo dõi stream tiếp tục và kiểm tra giới hạn SLA"]
~~~

Nhánh “khôi phục nghiệp vụ” ở đây là **chính sách ứng dụng**, không phải một hiệu ứng mặc định của giao thức.

## 2. Phân lớp timeout: yêu cầu nghiệp vụ, TCP, keepalive và phiên resume

Trong thực tế có nhiều đồng hồ đo thời gian. Cùng một từ “timeout” trong log chưa cho biết đồng hồ nào đã hết.

### 2.1. Timeout của một request-response

Trong Spring, `RSocketRequester` trả `Mono<T>` cho `request-response`. Người gọi có thể áp dụng toán tử Reactor `timeout(Duration)`:

~~~java
import java.time.Duration;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

public class InventoryClient {
    private final RSocketRequester requester;

    public InventoryClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<StockReply> readStock(String sku) {
        return requester.route("inventory.stock")
                .data(new StockQuery(sku))
                .retrieveMono(StockReply.class)
                .timeout(Duration.ofMillis(800));
    }
}
~~~

`StockQuery` và `StockReply` là DTO của ứng dụng; phía server có thể dùng `@MessageMapping("inventory.stock")`. Khi không có response trước 800 ms, toán tử `timeout` phát lỗi (thường là `TimeoutException`) và hủy subscription upstream. **Hết thời gian chờ không chứng minh server chưa chạy hoặc chưa commit giao dịch.** Cancel đi trên giao thức khi có thể, nhưng DB/HTTP side effect đang thực thi có thể đã hoàn tất.

Nếu service viết dữ liệu, mọi lần retry sau timeout cần một `requestId` ổn định và ràng buộc chống trùng. Nếu chỉ đọc, retry có thể đơn giản hơn, nhưng vẫn nên giới hạn tổng thời gian và công suất.

### 2.2. Timeout của request-stream

Với `Flux<T>`, `timeout(Duration)` thông dụng kiểm tra độ trễ **giữa các tín hiệu tiếp theo** (bao gồm chờ tín hiệu đầu), không nhất thiết là “toàn bộ stream tối đa X giây”. Ví dụ:

~~~java
public Flux<StockEvent> watchStock(String sku) {
    return requester.route("inventory.watch")
            .data(new StockQuery(sku))
            .retrieveFlux(StockEvent.class)
            .timeout(Duration.ofSeconds(15));
}
~~~

Nếu stream bình thường có một sự kiện mỗi vài phút, timeout 15 giây sẽ ngắt một luồng đang hoạt động đúng. Phải thiết kế tín hiệu heartbeat ở cấp ứng dụng, chọn timeout theo khoảng trống hợp lệ, hoặc sử dụng một cơ chế deadline **toàn phiên** khác nếu đó mới là yêu cầu. Một stream chạy vô hạn không nhất thiết có “response hoàn tất” để áp dụng timeout như Mono.

Đừng quên rằng Reactor `timeout` quan sát khoảng im lặng của **publisher ở chỗ đặt operator**. Nếu pipeline có `delayElements`, `publishOn`, buffer hoặc các toán tử chậm, timeout có thể đo thời gian *sau* bước biến đổi chứ không chỉ thời gian mạng.

### 2.3. TCP connect timeout, handshake và network idle timeout

Trước khi có stream RSocket phải có transport (ví dụ TCP hoặc WebSocket) và trao đổi SETUP. Hết hạn lúc **thiết lập kết nối** là vấn đề khác với một request đã gửi.

Các nơi có thể đặt giới hạn:

- Reactor Netty client/transport: thời gian TCP connect, TLS handshake, proxy handshake, idle handler (nếu có).
- RSocket client setup: một giới hạn tổng thể cho việc tạo một RSocket khả dụng ở tầng client.
- Hạ tầng: ingress, load balancer, NAT và service mesh có thể cắt kết nối idle theo policy riêng.

Ví dụ minh họa với API rsocket-java cấp thấp (không phải `RSocketRequester.Builder`):

~~~java
import io.rsocket.RSocket;
import io.rsocket.core.RSocketConnector;
import io.rsocket.transport.netty.client.TcpClientTransport;
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<RSocket> connected = RSocketConnector.create()
        .connect(TcpClientTransport.create("inventory.internal", 9898))
        .timeout(Duration.ofSeconds(4));
~~~

Đoạn trên áp dụng **giới hạn chờ cho Mono tạo kết nối/SETUP**. Muốn cài TCP connect timeout, hãy cấu hình `TcpClient` của Reactor Netty và chuyển client đó cho `TcpClientTransport` theo API của phiên bản đang dùng. Hạn chế đưa một thời hạn cố định “4 giây” vào mọi môi trường vì mạng nội bộ, TLS, proxy và DNS có thể có ngân sách khác nhau. Thư viện có thể phát những loại lỗi kết nối khác nhau; nhận diện từ exception/status thực tế thay vì bắt mọi lỗi rồi gán là timeout.

### 2.4. RSocket KEEPALIVE không phải request timeout

RSocket có frame `KEEPALIVE` dùng để kiểm tra peer còn sống. rsocket-java cung cấp cấu hình ở tầng connector:

~~~java
connector.keepAlive(
    Duration.ofSeconds(20),  // khoảng gửi KEEPALIVE
    Duration.ofSeconds(90)   // max lifetime không thấy phản hồi hợp lệ
);
~~~

Về mặt giao thức, hai thông số chính được gửi qua SETUP. Khi quá `maxLifeTime` mà không nhận được phản hồi keepalive hợp lệ, transport/phiên có thể được coi là mất. **Không có yêu cầu nào rằng một business request phải hoàn thành trong 90 giây**; để giới hạn một request cần timeout riêng. Ngược lại, timeout của Mono sau 800 ms không nhất thiết làm hỏng toàn bộ connection RSocket.

Đặt keepalive quá dày có thể sinh traffic không cần thiết, đặc biệt với hàng nghìn connection. Đặt max lifetime quá ngắn dễ tạo false positive khi có GC pause, tắc nghẽn hoặc network jitter. Giới hạn idle của proxy/NAT cần được kiểm tra cùng các lựa chọn này.

### 2.5. Resume session duration cũng không phải request timeout

Khi bật resume, thư viện có thể giữ trạng thái phiên một khoảng sau khi transport đứt. Giá trị `sessionDuration` trả lời: **giữ cơ hội phục hồi phiên trong bao lâu**. Nó không đo thời gian chạy business command và không đồng nghĩa với TTL message được lưu lâu dài.

Một yêu cầu đã chờ 800 ms có thể timeout ngay cả khi phiên có thể resume trong 2 phút. Tương tự, phiên có thể hết hạn 2 phút trong lúc business request đang chờ và phải được kết thúc theo policy.

## 3. Reconnect: tạo kết nối mới, không nối lại tiến độ stream cũ

Khi dùng **reconnect không có resume**, client tìm cách tạo RSocket mới khi transport trước đó mất. SETUP mới đồng nghĩa một connection/session mới về mặt RSocket. Các stream đang ở session cũ không được giao thức tự chuyển sang session mới; nếu còn nhu cầu theo dõi dữ liệu, ứng dụng phải subscribe lại hoặc dùng API đọc tiếp theo cursor.

Trong rsocket-java, `RSocketConnector.reconnect(Retry)` là lựa chọn của thư viện, có chính sách retry để tìm connection mới. API có hành vi đáng lưu ý: RSocket được chia sẻ/cached trong khi connection còn sống; sau khi mất kết nối, lần truy cập tiếp theo có thể kích hoạt quá trình reconnect.

Ví dụ theo API của rsocket-java:

~~~java
import io.rsocket.core.RSocketConnector;
import io.rsocket.transport.netty.client.TcpClientTransport;
import java.time.Duration;
import reactor.util.retry.Retry;

var connector = RSocketConnector.create()
        .reconnect(Retry.backoff(5, Duration.ofMillis(300))
                .maxBackoff(Duration.ofSeconds(5)))
        .keepAlive(Duration.ofSeconds(20), Duration.ofSeconds(90));

var sharedSocket = connector.connect(
        TcpClientTransport.create("inventory.internal", 9898));
~~~

`sharedSocket` ở đây là `Mono<RSocket>`. Việc để Mono còn sống, cache connection và kích hoạt reconnect khi truy cập lại thuộc **cơ chế `reconnect` của rsocket-java**; không nên đánh đồng với mọi hàm `retryWhen` bên ngoài. Các giới hạn 5 lần, 300 ms, 5 giây là ví dụ để thảo luận, không phải thông số mặc định được khuyên cho mọi dịch vụ.

Tài liệu API rsocket-java nhấn mạnh: **`reconnect(Retry)` không tự retry các request riêng lẻ đã thất bại**. Nếu cần thử lại request sau khi có connection mới, tầng request vẫn phải có retry policy phù hợp.

### Reconnect tại Spring RSocketRequester.Builder

Spring Framework cung cấp callback `rsocketConnector(...)` để truy cập phần cấu hình connector cấp thấp:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

@Configuration
public class InventoryRSocketClientConfig {

    @Bean
    RSocketRequester inventoryRequester(RSocketRequester.Builder builder) {
        return builder
                .rsocketConnector(connector -> connector
                        .keepAlive(Duration.ofSeconds(20),
                                Duration.ofSeconds(90))
                        .reconnect(Retry.backoff(
                                5, Duration.ofMillis(300))
                                .maxBackoff(Duration.ofSeconds(5))))
                .tcp("inventory.internal", 9898);
    }
}
~~~

Đây là lựa chọn **reconnect**, không bật resume. `RSocketRequester.Builder` do Spring Boot auto-config có sẵn codec và cấu hình phù hợp với Spring Messaging; cần tự tạo requester/channel tới đúng service. Tùy cách khởi tạo của builder và thời điểm thiết lập kết nối, việc tạo bean có thể cần server sẵn sàng; thiết kế readiness/lazy construction nếu startup không được phụ thuộc một backend đang online.

Ví dụ ứng dụng có thể chỉ retry một RPC *đọc dữ liệu* đối với lỗi gián đoạn transport:

~~~java
import io.rsocket.exceptions.ConnectionErrorException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<StockReply> readWithRetry(RSocketRequester requester, StockQuery query) {
    return requester.route("inventory.stock")
            .data(query)
            .retrieveMono(StockReply.class)
            .retryWhen(Retry.backoff(2, Duration.ofMillis(250))
                    .filter(error -> isTransientConnectionFailure(error)))
            .timeout(Duration.ofSeconds(2));
}
~~~

`isTransientConnectionFailure(Throwable)` là **hàm phân loại lỗi do ứng dụng phải viết**, tùy các exception/status của thư viện đang dùng; không giả định mọi exception đều retryable. `ConnectionErrorException` là ví dụ họ lỗi kết nối của rsocket-java; cần kiểm tra thực tế có bị wrap bởi Spring/Reactor hay không. Số lần retry phải nằm trong một ngân sách thời gian tổng, tránh “5 lần reconnect × 2 lần request retry × 3 tầng service” làm tăng số lượt gọi theo cấp số nhân.

**Điểm thiết kế:** cấp connector retry kết nối, còn cấp request quyết định *có được phép gửi lại thao tác nghiệp vụ hay không*. Nếu request là `reserveInventory`, retry sau timeout có thể trừ kho lần nữa nếu không có idempotency.

### Không có resume thì stream đang chạy ra sao?

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: SETUP (connection A)
    C->>S: REQUEST_STREAM watchStock
    S-->>C: Event #101
    S-->>C: Event #102
    Note over C,S: Transport của connection A bị cắt
    C->>S: SETUP (connection B - reconnect)
    Note over C,S: Stream trên A không tự sống lại trên B
    C->>S: REQUEST_STREAM watchStock(afterVersion=102)
    S-->>C: Event #103 từ nguồn có cursor
~~~

`afterVersion` ở đây là hợp đồng ứng dụng và đòi hỏi server có nguồn lưu sự kiện đủ để đọc tiếp. Reconnect chỉ tạo lại đường truyền; mọi logic checkpoint, dedup và bù khoảng trống dữ liệu thuộc ứng dụng.

## 4. Resume: khôi phục một phiên RSocket nếu cả hai bên còn trạng thái

**Resumption** là tính năng *tùy chọn* của giao thức RSocket. Nó được thiết kế cho trường hợp transport mất tạm thời nhưng client và server **vẫn giữ được trạng thái phiên**. Khi thương lượng resume trong SETUP, hai phía có thể ghi nhớ frame chưa được phía kia xác nhận và các vị trí frame đã nhận.

Khi kết nối vật lý mới được lập để phục hồi, client gửi **`RESUME`** cùng resume identification token và vị trí frame đã nhận; server kiểm tra token, vị trí frame, session và dữ liệu còn giữ:

- Nếu hợp lệ, server gửi **`RESUME_OK`** cùng vị trí cần thiết. Hai bên phát lại các frame chưa được xác nhận theo vị trí và có thể tiếp tục các stream hiện hữu.
- Nếu không thể khôi phục, server gửi lỗi **`REJECTED_RESUME`** (hoặc lỗi kết nối phù hợp). Client phải xử lý việc mất phiên theo chính sách; không giả vờ stream cũ vẫn còn.
- Nếu transport mất quá lâu hoặc bộ đệm frame thiếu dữ liệu để khớp lại vị trí, resume có thể thất bại.
- Nếu server restart làm mất session/token/frame store, resume thông thường **không còn nền tảng** để phục hồi. Không có bảo đảm tự sống qua process crash.

~~~mermaid
sequenceDiagram
    participant C as Client + resume state
    participant S as Server + resume state
    C->>S: SETUP (resume requested, token)
    C->>S: REQUEST_STREAM
    S-->>C: PAYLOAD E1
    Note over C,S: Mất TCP/WebSocket, nhưng session vẫn còn trong bộ nhớ
    S--xC: PAYLOAD E2 chưa được client xác nhận
    C->>S: Transport mới + RESUME(token, lastReceivedPosition)
    S-->>C: RESUME_OK(lastReceivedPosition)
    S-->>C: Phát lại frame còn thiếu E2
    S-->>C: PAYLOAD E3 (stream tiếp tục)
~~~

Các *frame position* và *resume token* thuộc giao thức. Không thiết kế logic ứng dụng dựa trên việc “frame nào được nhận một lần duy nhất” mà bỏ qua crash/timeout của business side effect: resume không tự biến hệ thống thành exactly-once transaction.

### Điều kiện để resume có thể thành công

| Điều kiện | Hệ quả khi thiếu |
| --- | --- |
| Client và server cùng bật/hỗ trợ resume | Không thể thương lượng một phiên có khả năng resume |
| Resume token đúng và session server chưa bị xóa | `REJECTED_RESUME` hoặc lỗi connection |
| Client/server giữ frame buffer đủ cho các vị trí chưa xác nhận | Không thể tái lập luồng frame nhất quán |
| Vẫn trong session duration/policy | Session có thể đã hết hạn |
| Transport mới tới được server nắm session tương ứng | Cần session affinity hoặc cơ chế chia sẻ state được hỗ trợ |
| Business publisher/handler còn tiếp tục khi transport mất | Resume không tái tạo được state nghiệp vụ đã bị hủy |

Ở hệ thống nhiều replica, một client có thể reconnect đến pod khác không chứa resume session. Nếu không có thiết kế session routing/state phù hợp, resume thất bại ngay cả khi pod cũ vẫn còn sống. “Có load balancer” không đồng nghĩa “có resume xuyên pod”.

### Resume không giống lưu thông điệp vào broker

RSocket resume chủ yếu dành cho một phiên **đang tồn tại** với frame state trong một khoảng thời gian hữu hạn. Nó không tự tạo durable subscription, dead-letter queue, persistent event log hoặc cơ chế phát lại lịch sử. Nếu ứng dụng cần chắc chắn nhận các sự kiện sau một giờ ngừng hoạt động hoặc sau server restart, hãy sử dụng lưu trữ ứng dụng, broker hoặc event log với offset/cursor. Khi đó reconnect kết hợp truy xuất lại nguồn dữ liệu mới có thể đáp ứng SLA.

## 5. Bật resume theo rsocket-java và Spring Boot

Một số API cấp thấp của rsocket-java có hỗ trợ trực tiếp:

- `RSocketConnector.resume(Resume)` ở client.
- `RSocketServer.resume(Resume)` ở server.
- `Resume.sessionDuration(Duration)` và `Resume.retry(Retry)` để điều khiển thời hạn session và thử nối lại (phụ thuộc phiên bản cụ thể).
- `RSocketServerCustomizer` của Spring Boot giúp cấu hình instance `io.rsocket.core.RSocketServer` trước khi server được khởi chạy.

**Không bật resume chỉ một phía.** Broker/gateway/driver có thể không hỗ trợ resume ngay cả khi client và server phía ứng dụng có API. Cần xác minh tại runtime.

### 5.1. Cấu hình server Spring Boot RSocket

Phần phụ thuộc Maven cơ bản:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
~~~

Khai báo RSocket TCP port độc lập theo mô hình Spring Boot:

~~~yaml
spring:
  rsocket:
    server:
      port: 9898
      transport: tcp
~~~

`spring.rsocket.server.port` yêu cầu Boot tạo server độc lập; với cấu hình WebSocket trên server WebFlux cần các property riêng như `mapping-path`. Cấu hình broker/proxy phải thống nhất transport TCP hoặc WebSocket, TLS và route.

Để bật resume ở tầng server, ví dụ dùng bean customizer (áp dụng với Spring Boot 3.x và rsocket-java 1.x):

~~~java
import io.rsocket.core.Resume;
import java.time.Duration;
import org.springframework.boot.rsocket.server.RSocketServerCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RSocketServerResumeConfig {

    @Bean
    RSocketServerCustomizer enableResumeOnServer() {
        return server -> server.resume(
                new Resume()
                        .sessionDuration(Duration.ofMinutes(2))
        );
    }
}
~~~

Bean `RSocketServerCustomizer` được áp dụng lên server do Boot quản lý. Nếu server thực tế được tạo thủ công hoặc do một starter khác quản lý, bean này có thể không có tác dụng; cần kiểm tra cấu hình hạ tầng đang dùng.

**Thận trọng:** `sessionDuration` càng dài có thể giữ càng nhiều phiên/frame trong bộ nhớ và tăng rủi ro hết tài nguyên nếu nhiều client ngắt kết nối. Giới hạn bộ đệm frame, số session và chính sách eviction/cleanup cần được kiểm chứng theo API của rsocket-java đang chạy; không chỉ tăng từ 2 lên 30 phút và kỳ vọng miễn phí.

### 5.2. Cấu hình client Spring RSocketRequester với resume

Client cũng cần bật resume trên **connector**, sử dụng cùng transport đến server:

~~~java
import io.rsocket.core.Resume;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

@Configuration
public class RSocketResumeClientConfig {

    @Bean
    RSocketRequester resumableInventoryRequester(
            RSocketRequester.Builder builder) {

        return builder
                .rsocketConnector(connector -> connector
                        .keepAlive(Duration.ofSeconds(20),
                                Duration.ofSeconds(90))
                        .resume(new Resume()
                                .sessionDuration(Duration.ofMinutes(2))
                                .retry(Retry.backoff(
                                        8, Duration.ofMillis(300))
                                        .maxBackoff(Duration.ofSeconds(4)))))
                .tcp("inventory.internal", 9898);
    }
}
~~~

Cấu hình này là **phương án khác** so với bean bật `reconnect(Retry)` ở mục 3. Không triển khai cả hai cấu hình cho cùng một client kỳ vọng được “resume rồi fallback reconnect” tự động.

Theo API `RSocketConnector` của rsocket-java 1.x, **`reconnect(Retry)` và `resume(Resume)` loại trừ lẫn nhau**; nếu đặt cả hai, cấu hình resume được ưu tiên. Vì vậy chuỗi gọi:

~~~java
connector.reconnect(reconnectPolicy)
         .resume(new Resume().retry(resumePolicy));
~~~

**Không có nghĩa** thư viện sẽ tự thử resume, rồi chuyển sang reconnect nếu hết session. Nếu resume bị từ chối hoặc hết thời hạn, ứng dụng phải quyết định tạo một requester/connection mới bằng SETUP và phục hồi nghiệp vụ từ checkpoint. Không suy ra có fallback tự động nếu chưa thấy hành vi đó trong phiên bản thư viện cụ thể.

### 5.3. Đừng dùng lại danh tính/điểm tiếp nối sai

Resume token là danh tính phiên dùng trong giao thức, **không phải** `orderId`, `userId` hay idempotency key của business operation. Không xem token như dữ liệu nghiệp vụ có thể tái sử dụng tùy ý. Nếu phải tạo một session mới, hãy dùng protocol setup mới và khôi phục nghiệp vụ theo cursor đã lưu, không “chế” lại token để giả lập phiên cũ.

Với deploy nhiều replica, cần bảo đảm đường đi của RESUME tới endpoint giữ session. Các lựa chọn như sticky session hoặc lưu trạng thái phân tán phải được đánh giá dựa trên **khả năng thực sự của thư viện/broker**, không chỉ cấu hình routing trong ingress.

## 6. Giao thức, API thư viện và chính sách ứng dụng là ba lớp khác nhau

Dễ mắc sai lầm khi đọc một API tên `retry` hoặc `timeout` rồi mặc định nó có cùng nghĩa ở mọi nơi:

| Lớp | API/khái niệm | Tác động trực tiếp | Không tự bảo đảm |
| --- | --- | --- | --- |
| Reactor | `Mono.timeout(Duration)` | Hết hạn chờ một tín hiệu/kết quả ở publisher | Reconnect hoặc rollback SQL |
| Reactor | `Flux.timeout(Duration)` | Phát lỗi khi khoảng trống tín hiệu vượt hạn | Tổng tuổi thọ stream cố định |
| Reactor | `retryWhen(Retry)` | Subscribe lại publisher sau lỗi hợp lệ | Idempotency hoặc giữ stream cũ |
| RSocket protocol | SETUP/KEEPALIVE | Khởi tạo/liveness của connection | Mọi request hoàn thành trước deadline |
| rsocket-java | `RSocketConnector.reconnect(Retry)` | Tìm RSocket connection mới theo retry | Tự retry request riêng lẻ, stream cũ |
| RSocket protocol | RESUME/RESUME_OK | Thử tiếp tục session đã thương lượng | Thành công khi frame/session mất |
| rsocket-java | `RSocketConnector.resume(Resume)` | Bật/resume và retry transport cho phiên cũ | Tự fallback sang kết nối mới khi resume lỗi |
| Spring Boot | `spring.rsocket.server.*`, customizer | Mở/configure RSocket server | Đặt SLA của từng route hoặc exactly-once |
| Application | Deadline, cursor, inbox, outbox | Đáp ứng yêu cầu nghiệp vụ | Hoạt động tự động nếu thiếu state/store |

Điểm dễ nhầm khác là `retryWhen` ở tầng publisher có thể **subscribe lại một nguồn tạo request**. Với request-response, điều này thường tương đương **gửi lại request**. Với stream, retry sau khi lỗi có thể tạo một stream mới bắt đầu từ đầu; nếu publisher không có cursor, client có thể nhận trùng hoặc bỏ lỡ sự kiện.

### Ba ngữ nghĩa khác nhau khi xử lý request-stream

~~~mermaid
flowchart LR
    A["Stream A đang chạy"] --> B{"Mất transport"}
    B --> C["Reconnect thuần"]
    C --> D["Stream A lỗi; ứng dụng mở stream B mới"]
    B --> E["Resume thành công"]
    E --> F["Giữ session logic và tiếp tục frame/stream A"]
    B --> G["Resume thất bại"]
    G --> H["Đọc checkpoint rồi mở stream mới nếu cần"]
~~~

Không thể bảo vệ dữ liệu nghiệp vụ chỉ bằng việc chọn một trong ba nhánh: request consumer vẫn cần xử lý version/sequence và chống xử lý trùng khi replay hoặc khi publish lại.

## 7. Thiết kế end-to-end cho nghiệp vụ có side effect

Giả sử `inventory-service` nhận RSocket request `reserveStock` và giảm số lượng tồn kho trong SQL. Client có thể timeout sau khi server commit nhưng trước khi nhận response; hoặc có thể reconnect và gửi lại cùng command. Muốn tổng tác động chỉ một lần phải bổ sung **idempotency key**.

Ví dụ DTO của ứng dụng:

~~~java
public record ReserveCommand(
        String requestId,
        String orderId,
        String sku,
        int quantity
) {}

public record ReserveResult(
        String reservationId,
        String status
) {}
~~~

Server sử dụng một database transaction bao gồm lưu kết quả theo khóa `(callerId, requestId)` và thay đổi tồn kho. Một bảng minh họa:

~~~sql
CREATE TABLE inventory_command_receipts (
    caller_id         VARCHAR(120) NOT NULL,
    request_id        VARCHAR(120) NOT NULL,
    reservation_id    VARCHAR(120) NOT NULL,
    result_status     VARCHAR(40) NOT NULL,
    created_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (caller_id, request_id)
);
~~~

Thứ tự xử lý:

1. Xác thực caller và kiểm tra command.
2. Bắt đầu transaction SQL.
3. Thử ghi biên nhận theo `callerId + requestId` với unique constraint; nếu đã tồn tại, trả lại kết quả đã ghi mà không trừ kho lần nữa.
4. Cập nhật tồn kho và reservation cùng transaction, commit.
5. Trả response; nếu response mất do timeout/connection break, client có thể retry cùng `requestId` để lấy lại cùng kết quả.

Cần xử lý đua tranh giữa hai request có cùng ID ở mức database, thay vì chỉ `SELECT` rồi mới `INSERT` không khóa. Nếu command còn phát sự kiện vào broker, cân nhắc **transactional outbox** để nhất quán giữa SQL commit và việc công bố event. RSocket resume không thay thế giao dịch hay outbox.

### Reconnect và resume có cùng yêu cầu business idempotency không?

Có. Resume làm giảm nhu cầu tạo stream/request mới khi **khôi phục phiên thành công**, nhưng không giải quyết mọi trường hợp: session có thể bị từ chối, caller có thể timeout hoặc server đã thực hiện side effect trước khi xác nhận đến client. Vì vậy các command nghiệp vụ có side effect vẫn cần idempotency và cơ chế truy vấn lại kết quả không rõ trạng thái.

Ví dụ `requestId` nên sinh ở đầu luồng nghiệp vụ, rồi giữ nguyên cho mọi lần retry; không sinh UUID mới trong một `Mono.defer` mỗi lần `retryWhen` subscribe, nếu mục tiêu là chính xác cùng một command.

## 8. Cấu hình chiến lược theo SLA, thay vì lấy chung một con số

Giả sử API `checkout` có thời hạn 2 giây và inventory-service có p99 bình thường 120 ms:

| Cơ chế | Ví dụ cấu hình | Ý nghĩa thực tế | Cần quan sát |
| --- | --- | --- | --- |
| Request timeout | 600–800 ms | Hạn xử lý một lời gọi inventory trong ngân sách checkout | Tỷ lệ timeout, latency p95/p99 |
| Connection setup timeout | 2–4 giây | Thời gian chờ tạo phiên ở thời điểm startup hoặc truy cập | Connect latency, DNS/TLS errors |
| Keepalive interval | 20 giây | Kiểm tra peer theo chu kỳ | Keepalive send/ack, false positives |
| Keepalive max lifetime | 90 giây | Giới hạn không nhận tín hiệu liveness phù hợp | Connection close cause |
| Reconnect delay | Backoff 300 ms tới vài giây | Giảm tải khi server đang lỗi | Attempt count, reconnect success |
| Resume window | Ví dụ 2 phút | Thời gian còn cơ hội phục hồi session | Resume success/reject, session count, buffered bytes |
| Business retry | 0–2 lần, có filter | Tăng khả năng thành công cho operation an toàn | Retry amplification, duplicate suppression |

Các con số trên **chỉ để minh họa cách suy nghĩ**; không nên sao chép như cấu hình production mặc định. Chúng có thể không thể đồng thời tối ưu: ví dụ keepalive 90 giây mới phát hiện đứt kết nối trong khi request timeout chỉ 800 ms; vì thế client cần quyết định xử lý request timeout trước, không ngồi chờ keepalive xác nhận transport đã chết.

### Phân tầng ngân sách thời gian

Nếu endpoint tổng thời gian 2 giây, không cấp 2 giây cho mỗi downstream liên tiếp. Lời gọi inventory và các bước theo sau cần được phân bổ riêng theo SLA. `timeout` nên đặt đúng mức scope:

~~~java
Mono<CheckoutResult> checkout(CheckoutCommand command) {
    return checkInventory(command)
            .timeout(Duration.ofMillis(700))
            .flatMap(stock -> reserveAndPay(command, stock))
            .timeout(Duration.ofMillis(1800)); // ngân sách pipeline
}
~~~

Ví dụ chỉ minh họa cách giới hạn từng phần và toàn luồng; `checkInventory` và `reserveAndPay` là hàm nghiệp vụ ứng dụng. Trong production có thể dùng deadline tuyệt đối được truyền theo metadata để tránh ngân sách bị reset mỗi khi qua thêm một service. Cũng phải tính thời gian thread scheduling, serialization, DB, TLS/transport và response.

## 9. Kiểm thử các failure mode theo hành vi quan sát được

Unit test của `timeout` khác integration test của reconnect/resume: resume cần **hai endpoint, frame state và transport thực** để thấy được RESUME/RESUME_OK. Có thể dùng Reactor `StepVerifier` với `VirtualTimeScheduler` cho các logic timeout của publisher; với reconnect/resume nên dùng test integration trên TCP/WebSocket và mô phỏng cắt mạng mà không giết process (sau đó thử thêm kịch bản giết process).

| Ca kiểm thử | Cách tạo tình huống | Kỳ vọng |
| --- | --- | --- |
| Request chậm nhưng connection còn | Handler trả sau timeout 800 ms | Mono timeout/cancel; connection không bắt buộc bị tái lập |
| Stream không có event 15 giây | Không gửi payload tiếp | `Flux.timeout` phát lỗi theo khoảng trống tín hiệu |
| TCP không kết nối được | Tắt listener hoặc chặn port | Connect timeout/failure theo transport policy |
| Mất transport, reconnect bật | Cắt TCP và gọi mới sau khi server trở lại | SETUP mới, request mới chạy; stream cũ không tự phục hồi |
| Mất transport, resume cả hai phía | Cắt mạng ngắn, giữ hai process/state | Có thể RESUME_OK và tiếp tục stream/frame chưa đồng bộ |
| Resume không bật server | Client yêu cầu resume | Setup/resume không được chấp nhận theo library/protocol |
| Mất kết nối dài hơn session policy | Ngắt mạng quá thời hạn | Resume bị từ chối/hết hiệu lực; cần recovery ở application |
| Server restart trong lúc ngắt | Restart mất session store | Không kỳ vọng resume thành công trên process mới |
| Resume đi nhầm pod | Load balancer chuyển tới pod khác | Có thể reject vì không có token/session tương ứng |
| Retry command sau timeout | Client gửi lại cùng `requestId` | Chỉ một thay đổi tồn kho, trả kết quả nhất quán |
| Retry quá nhiều tầng | Bật retry ở requester và service khác | Tổng số attempt bị giới hạn và không gây storm |
| Frame buffer đầy | Tạm mất transport, producer phát nhanh | Policy tài nguyên làm resume thất bại hoặc backpressure theo cấu hình |

### Test nào thật sự chứng minh resume?

Một ca test tốt cần nhận diện **cùng stream logic** còn tiếp tục sau transport break, không chỉ thấy client kết nối được lần nữa. Bản ghi có thể gồm:

- Token/session được thương lượng lúc SETUP, nhưng không log token bí mật dạng nguyên văn ở production.
- Có attempt **RESUME**, server trả **RESUME_OK**.
- Phần frame bị gián đoạn đã được trao đổi lại theo protocol; không có một SETUP mới thay thế session cũ.
- Dữ liệu nhận vẫn đáp ứng thứ tự/version của hợp đồng và không bị ứng dụng phát trùng không kiểm soát.

Ngược lại, nếu test chỉ kiểm tra “sau khi bật lại mạng, gọi API thành công” thì rất có thể đang đo **reconnect** chứ không phải **resume**.

## 10. Quan sát vận hành và xử lý sự cố

Cần ghi log/metric riêng cho ba tầng:

| Tầng | Metric và log nên có | Câu hỏi cần trả lời |
| --- | --- | --- |
| Application timeout | `route`, `duration`, `timeoutType`, `requestId` | Route chậm do DB hay downstream? |
| Transport/keepalive | Connection opens/closes, keepalive misses, close reason | Mạng không ổn định, proxy idle, TLS? |
| Reconnect | Attempt count, backoff duration, new SETUP success | Mất bao lâu để có connection mới? |
| Resume | RESUME attempts, RESUME_OK, REJECTED_RESUME, session expiry | Còn state và frame hay không? |
| Frame/session store | Buffered bytes, active/disconnected sessions, eviction | Có nguy cơ cạn bộ nhớ? |
| Stream | Active streams, reconnect/re-subscribe count, cursor gap | Stream đã tiếp tục hay bị mở mới? |
| Business idempotency | Duplicate command count, receipt hits, conflict | Side effect có bị nhân đôi? |

Trên dashboard, nên tách đồ thị **RPC timeout** khỏi **reconnect attempts** và **resume success rate**. Một lượng timeout tăng có thể do SQL quá tải trong khi connection vẫn hoàn toàn khỏe. Ngược lại, số reconnect tăng liên tục nhưng timeout không nhiều có thể báo hiệu proxy đang cắt kết nối idle. Nếu resume liên tục bị từ chối sau khi scale số pod, nghi vấn session affinity/state loss cần được kiểm tra trước khi tăng thời hạn resume.

Không ghi đầy đủ payload nhạy cảm, token xác thực, resume token hoặc dữ liệu khách hàng vào log. Dùng correlation ID, trace ID và message/request ID theo hợp đồng. Các span tracing của một nghiệp vụ có thể trải qua nhiều connection RSocket; không suy ra một TCP connection bằng một giao dịch nghiệp vụ.

### Quy trình chẩn đoán ngắn

1. Xác định lỗi phát ra bởi toán tử Reactor timeout, TCP/handshake, keepalive, hay protocol resume.
2. Xem `route`, loại tương tác (response/stream/channel), thời gian và trạng thái subscription.
3. Nếu có reconnect, kiểm tra lần kết nối mới dùng SETUP nào và liệu request cũ có bị phát lại không.
4. Nếu có resume, kiểm tra cả client lẫn server đã bật, cùng session còn sống, frame buffer đủ và RESUME_OK có xuất hiện không.
5. Đối chiếu kết quả SQL/business với request ID trước khi chạy lại command có side effect.
6. Điều chỉnh SLA, retry, timeout hoặc frame retention dựa trên dữ liệu test/metric; kiểm tra tải và bộ nhớ sau thay đổi.

## 11. Những câu hỏi dễ nhầm khi thiết kế

**“Đã đặt `Mono.timeout`, cần cấu hình `RSocketConnector.reconnect` nữa không?”**

Có thể cần nếu ứng dụng phải phục vụ các request mới sau khi transport mất. `Mono.timeout` chỉ quy định thời gian chờ publisher; nó không tự tạo connection mới. Tuy nhiên, chỉ bật reconnect mà không có idempotency vẫn có nguy cơ gửi lại thao tác ghi.

**“RSocket có keepalive thì request có bao giờ timeout không?”**

Có. Keepalive xác định liveness của peer; business request vẫn có thể chậm do query hoặc downstream. Cần timeout theo route/SLA, độc lập với keepalive.

**“Khi reconnect thành công, request-stream cũ có tự nối tiếp không?”**

Không theo ngữ nghĩa reconnect thuần. Kết nối mới là session mới; ứng dụng phải mở stream và dùng cursor/version nếu cần lấy lại sự kiện chưa nhận.

**“Bật resume ở client là đủ?”**

Không. Server và mọi endpoint trong đường đi cần hỗ trợ resume; phiên/token và frame store phải còn. Một server restart hoặc chuyển request sang pod không có session thường làm resume thất bại.

**“Bật `resume` và `reconnect` trên cùng RSocketConnector để có cả hai?”**

Theo rsocket-java 1.x, hai cấu hình loại trừ nhau và **resume được ưu tiên**. Muốn fallback sau resume failure phải lập trình chiến lược rõ ràng, kiểm tra phiên bản cụ thể và khôi phục trạng thái nghiệp vụ.

**“Resume bảo đảm không mất sự kiện khi ứng dụng offline cả ngày?”**

Không. Resume phụ thuộc trạng thái phiên hữu hạn và frame buffer; nếu yêu cầu lưu bền vững, dùng event log/broker hoặc storage hỗ trợ replay.

**“REQUEST_FNF đã gửi thì có thể coi là thành công?”**

Không thể suy ra đã thực hiện side effect từ việc client phát đi frame hoặc complete ở phía client. Fire-and-forget không mang business response xác nhận. Nếu cần chắc chắn, dùng giao thức có acknowledgment/receipt hoặc mẫu lưu trữ bền vững thích hợp.

### Bảng chọn cơ chế

| Mục tiêu thực tế | Cách tiếp cận |
| --- | --- |
| Không cho request-response chờ mãi | `Mono.timeout` + timeout budget của application |
| Phát hiện kết nối chết dù không có request | KEEPALIVE/lifetime và/hoặc transport idle policy |
| Tiếp tục phục vụ request **mới** sau mất mạng | `RSocketConnector.reconnect(Retry)` + recovery ở tầng request |
| Giữ stream/frame của phiên **đang có** khi đứt ngắn | `RSocketConnector.resume(Resume)` và server resume, đủ session/frame state |
| Nhận đủ mọi event qua restart/offline lâu | Broker/event store + cursor/offset + retry + idempotency |
| Tránh thực hiện hai lần lệnh ghi sau timeout/retry | `requestId` ổn định, unique receipt, transaction/outbox |

## 12. Checklist trước khi đưa vào production

- Định nghĩa rõ loại timeout nào đang cấu hình: thời hạn request, khoảng trống event, connect/handshake, keepalive lifetime, hay resume session window.
- Chọn **reconnect hoặc resume** theo khả năng của rsocket-java/server và bài toán, không dựa vào tên API.
- Cấu hình retry backoff, số lần thử, tổng deadline và limit concurrency; chống retry storm.
- Nếu dùng resume, xác nhận hỗ trợ cả hai đầu, phạm vi session duration, kích thước buffer frame, routing qua load balancer và hành vi khi server restart.
- Với streaming, có cursor/checkpoint và đường khôi phục từ storage khi resume không thể tiếp tục.
- Với request có side effect, áp dụng idempotency key và transaction; khi có broker, cân nhắc outbox.
- Kiểm thử transport thật, thời gian gián đoạn ngắn/dài, session affinity, resume rejected và idempotency sau timeout.
- Đưa timeout/reconnect/resume vào metric, trace, log an toàn và capacity planning.

### Tài liệu kỹ thuật để đối chiếu phiên bản

- [Spring Boot Reference – RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): cấu hình server, `RSocketRequester.Builder` và auto-configuration.
- [Spring Framework Reference – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, routing, `rsocketConnector` callback.
- [rsocket-java – RSocketConnector source](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java): ngữ nghĩa cụ thể của `reconnect(Retry)`, `resume(Resume)` và keepalive; xem tag release của phiên bản chạy thực tế.
- [RSocket Protocol – Resuming Operation](https://rsocket.io/about/protocol/): SETUP, KEEPALIVE, RESUME, RESUME_OK, REJECTED_RESUME và giới hạn giao thức.

**Ghi nhớ:** **timeout** chấm dứt việc chờ một tín hiệu/thao tác; **reconnect** xây dựng một connection/session mới; **resume** cố cứu một session cũ với frame/stream state còn giữ. Không cơ chế nào tự bảo đảm nghiệp vụ exactly-once hoặc lưu sự kiện qua mọi dạng outage. Cần thiết kế timeout, retry và khôi phục trạng thái theo hợp đồng dữ liệu, giao dịch và SLA của hệ thống Spring Boot thực tế.


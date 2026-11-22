# Thiết lập, duy trì và đóng kết nối RSocket

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vòng đời một kết nối RSocket từ lúc cấu hình đến lúc đóng.
- Tạo client bằng Spring Framework qua **RSocketRequester**.
- Cấu hình server TCP hoặc WebSocket bằng Spring Boot.
- Gửi dữ liệu ở bước thiết lập kết nối và xử lý frame **SETUP** bằng **@ConnectMapping**.
- Duy trì kết nối bằng keepalive, chọn chiến lược reconnect hoặc session resumption.
- Đóng tài nguyên đúng lúc và nhận biết các lỗi thường gặp.

Ví dụ dùng Java 17+, Spring Boot 3.5.x và Spring Framework do Spring Boot quản lý. Hãy giữ các phiên bản Spring Boot, Spring Framework và RSocket Java tương thích theo dependency management của dự án.

## 1. Vòng đời kết nối RSocket

RSocket là giao thức trao đổi thông điệp hai chiều trên một kết nối byte stream như TCP hoặc WebSocket. Sau khi kết nối được thiết lập, cả hai phía đều có thể gửi yêu cầu; khái niệm client/server chỉ mô tả vai trò trong lúc bắt đầu kết nối. Mỗi phía có thể đóng vai requester hoặc responder tùy từng yêu cầu.

RSocket hỗ trợ bốn kiểu tương tác:

| Kiểu | Ý nghĩa |
|---|---|
| Request-Response | Gửi một thông điệp và nhận một phản hồi. |
| Request-Stream | Gửi một yêu cầu và nhận một luồng nhiều phần tử. |
| Channel | Hai phía trao đổi các luồng dữ liệu theo cả hai chiều. |
| Fire-and-Forget | Gửi một thông điệp không chờ payload phản hồi. |

Một kết nối có thể mang nhiều request stream đồng thời. Vì vậy, cần phân biệt **vòng đời kết nối** với **vòng đời từng request**. Một request kết thúc không có nghĩa là kết nối đã đóng.

Các giai đoạn chính:

1. **Cấu hình:** ứng dụng chọn transport, địa chỉ, codec, metadata và chính sách keepalive.
2. **Kết nối transport:** client mở TCP hoặc WebSocket tới server.
3. **SETUP:** client gửi frame SETUP chứa phiên bản giao thức, MIME type, thông số keepalive và có thể có setup data/metadata.
4. **Chấp nhận hoặc từ chối:** server xử lý SETUP. Nếu cấu hình hoặc xác thực không hợp lệ, server có thể từ chối kết nối.
5. **Trao đổi dữ liệu:** hai phía gửi request-response, request-stream, channel hoặc fire-and-forget trên cùng kết nối.
6. **Duy trì:** KEEPALIVE phát hiện transport đã mất kết nối; reconnect hoặc resume xử lý tình huống gián đoạn theo chính sách ứng dụng.
7. **Đóng:** ứng dụng dừng nhận công việc mới, xử lý các request đang chạy theo chính sách shutdown rồi giải phóng requester hoặc server.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant T as TCP / WebSocket
    participant S as RSocket Server
    C->>T: Mở transport
    T->>S: Thiết lập transport
    C->>S: SETUP (MIME, keepalive, setup data)
    S-->>C: Chấp nhận hoặc từ chối
    C->>S: REQUEST_RESPONSE / STREAM / CHANNEL / FNF
    S-->>C: PAYLOAD hoặc tín hiệu kết thúc
    C-->>S: KEEPALIVE định kỳ
    S-->>C: KEEPALIVE phản hồi
    C->>S: dispose() / đóng transport
~~~

Spring cung cấp **RSocketRequester** để làm việc ở mức ứng dụng. Lớp này đóng gói việc định tuyến, mã hóa và giải mã payload. Phía dưới, nó dùng RSocket Java để quản lý kết nối và transport.

## 2. Chuẩn bị và khởi chạy RSocket server

### 2.1. Thêm dependency

Với Maven và Spring Boot, dùng starter sau. Spring Boot tự quản lý phiên bản các thư viện liên quan:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
~~~

Starter cung cấp hạ tầng RSocket và các codec mặc định mà Spring Boot có thể cấu hình. Nếu dự án không dùng Spring Boot, cần tự khai báo các module Spring Messaging, RSocket Java, Reactor và transport phù hợp.

### 2.2. Mở server TCP

Trong `application.properties` của ứng dụng server:

~~~properties
spring.rsocket.server.port=7000
~~~

Khi có dependency và port, Spring Boot tự cấu hình RSocket server cùng **RSocketMessageHandler**. Các bean **@Controller** có **@MessageMapping** hoặc **@ConnectMapping** được dùng để xử lý thông điệp.

Ví dụ controller:

~~~java
package com.example.rsocketserver;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.rsocket.annotation.ConnectMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class GreetingController {

    @ConnectMapping("client.connect")
    public Mono<Void> onConnect(@Payload String clientId) {
        if (clientId == null || clientId.isBlank()) {
            return Mono.error(
                new IllegalArgumentException("clientId is required")
            );
        }

        System.out.println("Connected client: " + clientId);
        return Mono.empty();
    }

    @MessageMapping("greeting")
    public Mono<String> greeting(@Payload String name) {
        return Mono.just("Hello, " + name);
    }
}
~~~

Lớp khởi động của server:

~~~java
package com.example.rsocketserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketServerApplication.class, args);
    }
}
~~~

Trong ví dụ, `client.connect` là route ở cấp thiết lập kết nối. `greeting` là route của một request thông thường. Hai route này thuộc hai giai đoạn khác nhau.

### 2.3. Dùng WebSocket

Nếu cần đưa RSocket qua WebFlux WebSocket endpoint, cấu hình:

~~~properties
spring.rsocket.server.mapping-path=/rsocket
spring.rsocket.server.transport=websocket
~~~

Cách tích hợp này cần ứng dụng WebFlux và Reactor Netty. Một RSocket server TCP độc lập và một RSocket endpoint WebSocket gắn vào web server là hai cách triển khai khác nhau; hãy chọn theo hạ tầng mạng và client cần kết nối.

## 3. Tạo kết nối từ client bằng RSocketRequester

### 3.1. Tạo requester

Spring Boot tự cấu hình một bean **RSocketRequester.Builder**. Builder này có scope prototype vì nó mang trạng thái cấu hình; mỗi cấu hình kết nối nên dùng một instance riêng.

~~~java
RSocketRequester requester = builder
    .tcp("localhost", 7000);
~~~

Hoặc kết nối WebSocket bằng URI endpoint:

~~~java
RSocketRequester requester = builder
    .websocket(URI.create("ws://localhost:8080/rsocket"));
~~~

Đoạn WebSocket cần import `java.net.URI`.

Việc gọi **tcp()** hoặc **websocket()** tạo ra requester/client đã được cấu hình; nó **chưa nhất thiết mở socket ngay tại dòng lệnh đó**. Kết nối được thiết lập khi ứng dụng thực hiện request đầu tiên. Các request đồng thời qua cùng requester dùng chung kết nối. Khi transport bị mất, các request tiếp theo có thể kích hoạt việc thiết lập lại kết nối theo cơ chế của client.

Do đó, trong ứng dụng Spring, thường nên giữ một requester trong service singleton và tái sử dụng nó. Tránh tạo requester mới cho từng message hoặc chia sẻ một builder đã thay đổi cấu hình giữa nhiều kết nối.

### 3.2. Gửi thông tin trong SETUP

Builder cho phép khai báo dữ liệu và metadata ở cấp kết nối:

- **setupData(...)**: payload dữ liệu của frame SETUP.
- **setupRoute(...)**: route trong metadata của frame SETUP.
- **setupMetadata(...)**: metadata bổ sung cùng MIME type.
- **dataMimeType(...)** và **metadataMimeType(...)**: MIME type áp dụng cho dữ liệu và metadata trên kết nối.

Ví dụ client gửi tên định danh trong SETUP:

~~~java
RSocketRequester requester = builder
    .setupRoute("client.connect")
    .setupData("client-demo")
    .tcp("localhost", 7000);
~~~

Server nhận route **client.connect** bằng **@ConnectMapping** và đọc **client-demo** qua **@Payload**. Setup data hữu ích cho thông tin khởi tạo như client identifier hoặc capability. Không nên gửi mật khẩu, access token dài hạn hay dữ liệu bí mật dưới dạng setup data thông thường; hãy dùng cơ chế xác thực phù hợp, metadata bảo mật và TLS.

### 3.3. Gửi request sau khi kết nối

Sau khi requester sẵn sàng, tạo request bằng route, dữ liệu và kiểu phản hồi mong đợi:

~~~java
Mono<String> response = requester
    .route("greeting")
    .data("Ada")
    .retrieveMono(String.class);
~~~

**retrieveMono** khai báo phản hồi đơn; **retrieveFlux** dùng khi server trả về một luồng. **send()** phù hợp với fire-and-forget và trả về **Mono<Void>** xác nhận việc gửi message, không đảm bảo handler phía nhận đã xử lý xong nghiệp vụ.

Các publisher của Reactor là lazy: request chỉ chạy khi publisher được subscribe. Trong service reactive, nên trả **Mono** hoặc **Flux** cho caller để caller điều phối việc thực thi, timeout và hủy subscription. Chỉ dùng **block()** ở ranh giới đồng bộ có chủ đích, chẳng hạn một chương trình demo dòng lệnh hoặc một đoạn tích hợp không-reactive.

## 4. Ví dụ client hoàn chỉnh

Service dưới đây giữ một requester dùng chung, gửi định danh ở SETUP, gọi route **greeting** và giải phóng requester khi Spring đóng bean.

~~~java
package com.example.rsocketclient;

import java.time.Duration;

import jakarta.annotation.PreDestroy;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingClient {

    private final RSocketRequester requester;

    public GreetingClient(RSocketRequester.Builder builder) {
        this.requester = builder
            .setupRoute("client.connect")
            .setupData("client-demo")
            .rsocketConnector(connector -> connector
                .keepAlive(
                    Duration.ofSeconds(20),
                    Duration.ofSeconds(90)
                )
            )
            .tcp("localhost", 7000);
    }

    public Mono<String> greet(String name) {
        return requester
            .route("greeting")
            .data(name)
            .retrieveMono(String.class);
    }

    @PreDestroy
    public void close() {
        requester.dispose();
    }
}
~~~

Ứng dụng client có thể gọi service khi khởi động:

~~~java
package com.example.rsocketclient;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RSocketClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketClientApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(GreetingClient client) {
        return args -> client.greet("Ada")
            .doOnNext(System.out::println)
            .block();
    }
}
~~~

Chạy server trước, sau đó chạy client. Với Maven Wrapper, chạy **mvnw.cmd spring-boot:run** trong thư mục dự án server, rồi chạy lệnh tương tự trong thư mục dự án client. Nếu cả hai ứng dụng đã cấu hình dependency và package như ví dụ, kết quả nghiệp vụ là:

~~~text
Connected client: client-demo
Hello, Ada
~~~

Dòng **Connected client: client-demo** xuất hiện ở log server khi client thực hiện request đầu tiên và frame SETUP được xử lý. Dòng **Hello, Ada** được in ở client. Log thời gian khởi động của Spring Boot không được tính vào kết quả này.

## 5. Duy trì kết nối

### 5.1. Keepalive và phát hiện transport bị mất

RSocket dùng frame KEEPALIVE để hai phía biết đầu kia còn phản hồi. Hai tham số quan trọng:

- **Interval:** khoảng thời gian giữa các KEEPALIVE do phía client gửi.
- **Max lifetime:** khoảng thời gian tối đa chờ phản hồi KEEPALIVE từ đầu kia trước khi kết luận kết nối đã mất.

Cấu hình qua **RSocketConnector** trong **RSocketRequester.Builder**:

~~~java
.rsocketConnector(connector -> connector
    .keepAlive(
        Duration.ofSeconds(20),
        Duration.ofSeconds(90)
    )
)
~~~

Hai giá trị trên chỉ là ví dụ. Chọn interval và max lifetime theo độ trễ mạng, timeout của proxy/load balancer, loại client và mức độ nhạy với việc phát hiện mất kết nối. Max lifetime nên đủ lớn để cho phép nhiều heartbeat bị trễ hoặc mất; đặt quá ngắn dễ làm kết nối bị đánh dấu chết khi mạng chỉ tạm thời chậm.

KEEPALIVE giúp phát hiện transport không còn phản hồi. Nó không chứng minh một route nghiệp vụ đang khỏe, không thay thế timeout của từng request và không tự khôi phục dữ liệu nghiệp vụ bị thất bại. Nếu cần kiểm tra sức khỏe service, hãy có request health/probe ở cấp ứng dụng.

### 5.2. Reconnect

Reconnect tạo một kết nối mới khi kết nối cũ bị mất. RSocket Java cho phép cấu hình chính sách retry trên connector:

~~~java
.rsocketConnector(connector -> connector
    .keepAlive(
        Duration.ofSeconds(20),
        Duration.ofSeconds(90)
    )
    .reconnect(
        Retry.backoff(5, Duration.ofSeconds(1))
            .maxBackoff(Duration.ofSeconds(30))
    )
)
~~~

Cần import **reactor.util.retry.Retry**. Ví dụ trên cho phép tối đa năm lần thử lại, bắt đầu với khoảng nghỉ một giây và tăng dần đến tối đa ba mươi giây. Đây là chính sách mẫu; giới hạn và backoff phải phù hợp với tải, thời gian khôi phục server và ngân sách thời gian của request.

Có hai lớp retry cần phân biệt:

1. **Reconnect của connection client:** quyết định cách tạo lại kết nối khi transport mất.
2. **Retry của request:** quyết định có gửi lại một request đã thất bại hay không.

Một request đã lỗi không tự động được thực thi lại chỉ vì connector có reconnect policy. Muốn thử lại request, caller phải subscribe lại, thường thông qua **retryWhen**:

~~~java
return requester
    .route("greeting")
    .data(name)
    .retrieveMono(String.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(500))
            .filter(error -> isTransientConnectionError(error))
    );
~~~

**isTransientConnectionError** là predicate do ứng dụng định nghĩa dựa trên các lỗi mạng có thể phục hồi. Không retry lỗi validation, lỗi nghiệp vụ hoặc mọi exception một cách mù quáng. Với lệnh có side effect như tạo đơn hàng hoặc trừ tiền, chỉ retry khi API có idempotency key hoặc cơ chế chống xử lý trùng; nếu không, lần thử đầu có thể đã được server thực hiện trước khi phản hồi bị mất.

### 5.3. Session resumption

Session resumption là cơ chế giao thức để tiếp tục một phiên RSocket sau khi transport bị gián đoạn, với điều kiện hai phía đều hỗ trợ và cấu hình resume. Nó giữ trạng thái cần thiết để phục hồi các stream bị gián đoạn, vì vậy tốn tài nguyên bộ nhớ và quản lý trạng thái hơn reconnect thông thường.

Phân biệt:

| Cơ chế | Hành vi |
|---|---|
| Reconnect | Tạo một kết nối mới. Request lỗi cần chính sách retry riêng nếu muốn gửi lại. |
| Resume | Cố gắng khôi phục phiên và các stream còn tiếp tục được sau khi transport gián đoạn. |
| Retry request | Gửi lại một thao tác ở tầng ứng dụng; có nguy cơ lặp side effect nếu thao tác không idempotent. |

Trong RSocket Java, **reconnect(Retry)** và **resume(Resume)** là hai lựa chọn loại trừ lẫn nhau; nếu cấu hình cả hai, resume được ưu tiên. Chỉ bật resume khi client và server đều được cấu hình tương thích và ứng dụng thật sự cần khả năng tiếp tục stream. Nếu chỉ cần kết nối lại rồi thực hiện request mới, reconnect thường đơn giản hơn.

### 5.4. Timeout, backpressure và subscription

Giữ kết nối lâu không có nghĩa mọi request đều được phép chờ vô hạn.

- Đặt timeout theo từng thao tác hoặc theo yêu cầu nghiệp vụ.
- Với **Flux**, xử lý backpressure và hủy subscription khi caller không còn cần dữ liệu.
- Dùng **take**, **timeout**, **onErrorResume** hoặc các operator phù hợp để quản lý vòng đời stream.
- Không nuốt lỗi kết nối bằng cách biến mọi lỗi thành giá trị mặc định; hãy ghi log và phân loại lỗi.
- Không gọi **subscribe()** rải rác trong service nếu có thể trả publisher cho tầng gọi. Subscription tự tạo làm khó kiểm soát lỗi, cancellation và shutdown.

## 6. Xử lý sự kiện kết nối và đóng kết nối

### 6.1. @ConnectMapping dùng cho SETUP

**@ConnectMapping** xử lý frame SETUP khi kết nối bắt đầu và các thông báo metadata push tiếp theo. Có thể giới hạn handler theo route như **client.connect**; nếu không khai báo route, handler có thể khớp mọi kết nối/metadata push.

Trên server, handler phải trả **void** hoặc **Mono<Void>**. Khi xử lý bất đồng bộ bằng **Mono<Void>**, kết nối được chấp nhận sau khi publisher hoàn tất; nếu publisher phát lỗi, kết nối mới có thể bị từ chối.

Không giữ việc xử lý SETUP chờ một request khác được gửi qua chính requester của kết nối đó. SETUP cần được hoàn tất trước khi hai phía bắt đầu các request thông thường. Nếu cần server gửi dữ liệu ngay khi client kết nối, hãy tách việc gửi đó khỏi luồng xử lý SETUP và thực thi bất đồng bộ sau khi kết nối đã được chấp nhận.

**Lưu ý:** **@ConnectMapping** không phải callback ngắt kết nối. Nó xử lý SETUP và METADATA_PUSH, không đại diện cho sự kiện đóng transport.

### 6.2. Theo dõi khi kết nối đóng

Ở tầng RSocket Java, một đối tượng **RSocket** cung cấp **onClose()**, trả về **Mono<Void>** kết thúc khi tài nguyên đóng. Publisher hoàn tất bình thường khi đóng bình thường và phát lỗi khi đóng do lỗi. Có thể dùng tín hiệu này để dọn registry client hoặc giải phóng tài nguyên gắn với một kết nối.

Ví dụ ở mức khái niệm khi ứng dụng đang nắm một đối tượng RSocket sống:

~~~java
rsocket.onClose()
    .doOnError(error ->
        log.warn("RSocket connection closed with error", error)
    )
    .doFinally(signal ->
        connectedClients.remove(clientId)
    )
    .subscribe();
~~~

Trong đoạn minh họa, **log**, **connectedClients** và **clientId** là thành phần do ứng dụng định nghĩa. Không giả định mọi **RSocketRequester** đều trả về đối tượng này. Phương thức **requester.rsocket()** có thể trả **null** khi requester được tạo qua builder TCP/WebSocket; nó chỉ có sẵn trong một số trường hợp requester bọc một RSocket đang hoạt động. Nếu cần quản lý vòng đời kết nối phía server ở mức thấp, hãy thiết kế nơi sở hữu đối tượng RSocket/SocketAcceptor để đăng ký **onClose()** một cách rõ ràng.

### 6.3. Đóng requester ở client

**RSocketRequester** triển khai **Disposable**. Gọi **dispose()** sẽ đóng kết nối transport bên dưới và thông báo cho các subscriber. Có thể kiểm tra trạng thái bằng **isDisposed()**.

~~~java
requester.dispose();

if (requester.isDisposed()) {
    System.out.println("Requester đã được dispose");
}
~~~

Trong Spring, đặt thao tác giải phóng ở **@PreDestroy**, như ví dụ **GreetingClient**. Khi shutdown:

1. Ngừng nhận công việc mới hoặc ngừng tạo request mới.
2. Hủy hoặc chờ các stream đang chạy theo timeout shutdown của ứng dụng.
3. Gọi **requester.dispose()** để đóng requester.
4. Để Spring đóng ApplicationContext và các tài nguyên còn lại.

Không dispose requester sau từng request nếu nhiều request đang dùng chung kết nối. Làm như vậy sẽ đóng kết nối mà các request khác còn cần.

### 6.4. Đóng server

Với Spring Boot, server RSocket được quản lý theo vòng đời ApplicationContext. Khi ứng dụng dừng, Spring đóng server được auto-configure cùng các bean liên quan.

Nếu tự tạo server bằng RSocket Java, giữ lại **CloseableChannel** trả về từ thao tác bind và gọi **dispose()** khi ứng dụng shutdown. Không bỏ mất handle này nếu ứng dụng cần đóng server có kiểm soát.

## 7. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Connection refused | Server chưa chạy, sai host/port hoặc firewall chặn TCP. | Kiểm tra log server, port đang listen và địa chỉ client dùng. |
| SETUP bị từ chối | Handler **@ConnectMapping** phát lỗi, setup route không khớp hoặc thông tin xác thực không hợp lệ. | Xem log server và kiểm tra setup route/data/metadata. |
| Payload không giải mã được | Hai phía dùng MIME type hoặc codec không tương thích. | Kiểm tra **RSocketStrategies**, encoder, decoder và MIME type. |
| Kết nối bị đóng khi idle | Proxy timeout, heartbeat không phù hợp hoặc mạng có khoảng mất gói dài. | Đối chiếu keepalive interval/max lifetime với timeout hạ tầng. |
| Request đầu tiên thất bại | Requester mới chỉ được cấu hình; transport thực tế được mở khi có request. | Kiểm tra server đã sẵn sàng trước khi client gửi request. |
| Kết nối đã hồi phục nhưng thao tác không chạy lại | Reconnect không đồng nghĩa retry request. | Thêm retry có giới hạn cho request có thể thử lại an toàn. |
| Server xử lý thao tác hai lần | Retry một request có side effect sau khi phản hồi đầu tiên bị mất. | Dùng idempotency key hoặc cơ chế chống trùng. |
| Tài nguyên/kết nối tồn tại sau shutdown | Requester không được dispose hoặc stream chưa được hủy. | Kiểm tra **@PreDestroy**, subscription và chính sách shutdown. |

## 8. Checklist triển khai

- [ ] Server đã mở đúng transport và port hoặc WebSocket mapping path.
- [ ] Client và server dùng MIME type, codec và metadata tương thích.
- [ ] Requester được tái sử dụng cho các request cùng vòng đời.
- [ ] Setup route/data chỉ chứa thông tin cần thiết để khởi tạo kết nối.
- [ ] Keepalive phù hợp với timeout của mạng và proxy.
- [ ] Reconnect và retry request được cấu hình như hai chính sách riêng.
- [ ] Các request có side effect có bảo vệ idempotency trước khi retry.
- [ ] **@ConnectMapping** hoàn tất nhanh và không chờ request trên chính kết nối vừa thiết lập.
- [ ] Có đường dọn registry/tài nguyên khi kết nối đóng nếu ứng dụng quản lý client đang kết nối.
- [ ] Client requester được dispose khi ứng dụng shutdown.
- [ ] Các stream đang chạy có timeout, cancellation và backpressure phù hợp.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): RSocketRequester, SETUP, codecs, annotated responders và ConnectMapping.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): starter, server auto-configuration, TCP/WebSocket và requester builder.
- [Spring Framework Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): dispose(), isDisposed(), rsocket() và rsocketClient().
- [RSocket Java — RSocketConnector](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java): keepalive, reconnect và resume.
- [RSocket Protocol](https://rsocket.io/about/protocol/): SETUP, KEEPALIVE, request frames và session resumption.

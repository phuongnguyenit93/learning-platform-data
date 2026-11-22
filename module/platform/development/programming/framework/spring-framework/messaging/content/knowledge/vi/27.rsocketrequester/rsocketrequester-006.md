# Gửi một chiều bằng `RSocketRequester.send()`

## Mục tiêu

Sau bài này, bạn có thể tạo một request RSocket chỉ gửi dữ liệu sang phía nhận, chọn đúng interaction model Fire-and-Forget bằng `send()`, kết hợp `Mono<Void>` vào luồng reactive và hiểu chính xác điều gì được xác nhận khi Mono hoàn tất.

## 1. Gửi một chiều trong RSocket là gì?

RSocket định nghĩa bốn interaction model chính:

| Interaction | Dữ liệu gửi | Dữ liệu nhận | Trường hợp phù hợp |
|---|---|---|---|
| Request-Response | Một message | Một response | Cần kết quả hoặc xác nhận nghiệp vụ ngay trong cùng request |
| Request-Stream | Một message | Một stream response | Gửi điều kiện truy vấn rồi nhận nhiều kết quả |
| Channel | Một stream | Một stream | Hai phía trao đổi nhiều message theo thời gian |
| Fire-and-Forget | Một message | Không có response | Gửi sự kiện hoặc thông báo mà bên gửi không cần kết quả trả về |

Fire-and-Forget là mô hình gửi một chiều. Bên gửi tạo một request, bên nhận có thể xử lý payload, nhưng giao thức không tạo response payload cho request đó. Trong RSocket protocol, loại request này được biểu diễn bằng frame `REQUEST_FNF`.

Trong Spring, `RSocketRequester` thuộc module `spring-messaging` và cung cấp API fluent để khai báo route, payload, metadata và interaction cần thực hiện. Phương thức `send()` chọn Fire-and-Forget.

Điểm cần nhớ nhất: `send()` trả về `Mono<Void>`. Mono này báo việc payload đã được gửi thành công hay gặp lỗi ở quá trình gửi. Nó **không xác nhận** rằng handler ở máy nhận đã chạy, xử lý xong hay lưu dữ liệu thành công.

## 2. Cấu trúc lời gọi

~~~java
Mono<Void> completion = requester
        .route("audit.record")
        .data(event)
        .send();
~~~

Ý nghĩa từng bước:

1. `route("audit.record")`: khai báo route được gửi trong metadata của request. Phía nhận dùng route này để tìm handler tương ứng.
2. `data(event)`: đặt object làm payload. Spring sẽ dùng encoder đã đăng ký trong `RSocketStrategies` để tuần tự hóa object.
3. `send()`: thực hiện Fire-and-Forget và trả về `Mono<Void>`.

`send()` là thao tác kết thúc việc khai báo request. Không gọi thêm `retrieveMono()` hoặc `retrieveFlux()` sau nó để lấy response; Fire-and-Forget không có response payload.

Payload có thể là một object đơn, chuỗi, byte array hoặc kiểu dữ liệu khác mà encoder phía gửi và decoder phía nhận cùng hỗ trợ. Nếu cần gửi metadata bổ sung, có thể thêm `metadata(value, mimeType)` trước `data(...)`. Với composite metadata mặc định, mỗi giá trị metadata phải có encoder phù hợp và phía nhận phải đăng ký cách giải mã tương ứng.

## 3. Vòng đời của `Mono<Void>`

`Mono<Void>` là một Reactive Streams Publisher không phát ra giá trị dữ liệu. Nó chỉ có thể hoàn tất hoặc phát tín hiệu lỗi.

- **Complete:** thao tác gửi payload đã hoàn tất thành công theo góc nhìn của requester.
- **Error:** requester gặp lỗi trong quá trình kết nối, mã hóa hoặc gửi payload.
- **Không có response nghiệp vụ:** requester không nhận được kết quả xử lý từ handler.

Mono là một phần của reactive pipeline. Nếu tạo Mono rồi bỏ qua, request sẽ không được kích hoạt. Hãy trả Mono về cho thành phần reactive bên ngoài hoặc kết hợp nó với pipeline đang chạy.

~~~java
public Mono<Void> publish(AuditEvent event) {
    return requester.route("audit.record")
            .data(event)
            .send()
            .doOnSuccess(ignored ->
                    log.debug("RSocket payload đã được gửi"))
            .doOnError(error ->
                    log.warn("Không gửi được RSocket payload", error));
}
~~~

Cách dùng này giữ quyền subscribe ở tầng gọi. Ví dụ, một WebFlux controller có thể trả trực tiếp `Mono<Void>` từ service. Trong chương trình imperative hoặc đoạn demo chạy từ command line, có thể gọi `block(Duration)` tại ranh giới imperative để chờ thao tác gửi; không block trên event-loop của WebFlux/Reactor Netty.

Tránh gọi `subscribe()` bên trong service chỉ để “cho request chạy”. Việc tự subscribe tách thao tác gửi khỏi lifecycle của request hiện tại, khiến tầng gọi khó kiểm soát lỗi, thời điểm hoàn tất và việc hủy tác vụ. Nếu thật sự cần một tác vụ nền độc lập, phải có nơi quản lý subscription và xử lý lỗi rõ ràng.

## 4. Ví dụ Spring Boot: gửi một sự kiện audit

Ví dụ dưới đây dùng Java 17+ và Spring Boot. Đặt phần nhận ở ứng dụng server, phần gửi ở ứng dụng client. Cả hai cần dependency `spring-boot-starter-rsocket`; hai phía phải dùng DTO tương thích và codec tương thích.

### 4.1. Dependency

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
~~~

Spring Boot tự cấu hình `RSocketStrategies` và các codec JSON/CBOR phổ biến. Nếu dùng kiểu dữ liệu hoặc MIME type riêng, hãy đăng ký encoder/decoder tương ứng ở cả hai phía.

### 4.2. DTO dùng chung

~~~java
package com.example.rsocket;

public record AuditEvent(
        String eventId,
        String action,
        long occurredAtEpochMillis
) {
}
~~~

`eventId` là định danh sự kiện. Trong hệ thống có retry hoặc có khả năng gửi trùng, phía nhận có thể dùng ID này để triển khai xử lý idempotent.

### 4.3. Phía nhận: khai báo route

Cấu hình server bằng `application.properties`:

~~~properties
spring.rsocket.server.port=7000
~~~

Tạo handler:

~~~java
package com.example.rsocket.server;

import com.example.rsocket.AuditEvent;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class AuditReceiver {

    private final AuditService auditService;

    public AuditReceiver(AuditService auditService) {
        this.auditService = auditService;
    }

    @MessageMapping("audit.record")
    public Mono<Void> receive(AuditEvent event) {
        return auditService.store(event);
    }
}
~~~

Ví dụ service để quan sát việc handler được gọi:

~~~java
package com.example.rsocket.server;

import com.example.rsocket.AuditEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class AuditService {

    private static final Logger log =
            LoggerFactory.getLogger(AuditService.class);

    public Mono<Void> store(AuditEvent event) {
        return Mono.fromRunnable(() ->
                log.info("Received eventId={}, action={}",
                        event.eventId(), event.action()));
    }
}
~~~

`@MessageMapping("audit.record")` ánh xạ route mà client gửi tới. Handler nhận payload đã được giải mã thành `AuditEvent`. Việc trả về `Mono<Void>` biểu thị handler không tạo response payload; pipeline của service vẫn cần được trả về để Spring quản lý quá trình xử lý.

Trong ứng dụng thật, thay phần ghi log bằng thao tác lưu trữ phù hợp. Nếu dùng R2DBC hoặc repository reactive, trả về trực tiếp Mono từ thao tác lưu. Nếu gọi API hoặc thư viện blocking, không thực hiện blocking I/O trực tiếp trên event-loop; hãy chọn cách tích hợp và scheduler phù hợp.

### 4.4. Phía gửi: gọi `send()`

Spring Boot cung cấp bean `RSocketRequester.Builder`. Tạo requester kết nối tới server và tái sử dụng requester đó:

~~~java
package com.example.rsocket.client;

import com.example.rsocket.AuditEvent;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class AuditPublisher {

    private final RSocketRequester requester;

    public AuditPublisher(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("localhost", 7000);
    }

    public Mono<Void> publish(AuditEvent event) {
        return requester.route("audit.record")
                .data(event)
                .send();
    }
}
~~~

Khi tầng gọi subscribe vào Mono được trả về, requester thực hiện request. Kết nối được thiết lập khi cần sử dụng; việc tạo requester bằng builder không đồng nghĩa payload đã được gửi.

Ví dụ kết hợp trong một WebFlux handler:

~~~java
@PostMapping("/audit")
public Mono<Void> publish(@RequestBody AuditEvent event) {
    return auditPublisher.publish(event);
}
~~~

Khi Mono hoàn tất, ứng dụng gửi biết thao tác gửi đã hoàn tất. Điều đó **không có nghĩa** bản ghi đã được commit ở database phía server. Nếu API HTTP cần trả mã `202 Accepted`, hãy hiểu đây là xác nhận của tầng gửi theo hợp đồng ứng dụng; không được diễn giải thành xác nhận xử lý thành công ở hệ thống nhận.

## 5. Chọn `send()` hay phương thức khác?

| API | Interaction | Giá trị trả về | Khi nào chọn |
|---|---|---|---|
| `send()` | Fire-and-Forget | `Mono<Void>` | Chỉ cần gửi payload, không cần response |
| `retrieveMono(Type.class)` | Request-Response | `Mono<Type>` | Cần một response hoặc ACK nghiệp vụ |
| `retrieveFlux(Type.class)` | Request-Stream hoặc Request-Channel, tùy cardinality đầu vào | `Flux<Type>` | Cần nhận nhiều response |
| `sendMetadata()` | Metadata-Push | `Mono<Void>` | Gửi metadata ở cấp kết nối, không phải một payload nghiệp vụ theo route |

Nếu nghiệp vụ cần biết “server đã nhận và lưu thành công chưa?”, hãy thiết kế một xác nhận tường minh. Cách đơn giản là dùng Request-Response: handler trả về một DTO ACK và client gọi `retrieveMono(Ack.class)`. Nếu cần gửi một chiều nhưng vẫn cần phản hồi về sau, có thể thiết kế một route ACK riêng hoặc một luồng sự kiện hai chiều; khi đó phải quản lý correlation ID và timeout.

## 6. Lỗi thường gặp và cách xử lý

### Tạo Mono nhưng không subscribe

~~~java
public void publish(AuditEvent event) {
    requester.route("audit.record")
            .data(event)
            .send(); // Mono bị bỏ đi, request không được kích hoạt
}
~~~

**Cách sửa:** đổi phương thức thành `Mono<Void>` và trả publisher cho tầng gọi. Chỉ subscribe ở ranh giới imperative hoặc tại thành phần thật sự sở hữu lifecycle của tác vụ nền.

### Nghĩ rằng Mono hoàn tất nghĩa là server đã xử lý xong

Đây là nhầm lẫn quan trọng nhất. `send()` không trả response và không cung cấp xác nhận về trạng thái xử lý ở remote. Log “payload sent” ở client không thay thế được log, metric hoặc trạng thái nghiệp vụ ở server.

**Cách sửa:** nếu cần ACK, dùng Request-Response hoặc thiết kế kênh xác nhận riêng. Nếu dữ liệu không được phép mất, cân nhắc durable message broker, transactional outbox và cơ chế retry có kiểm soát thay vì dựa vào Fire-and-Forget.

### Route giữa hai phía không khớp

Client gửi `audit.record` nhưng handler khai báo route khác thì handler mong muốn không được gọi.

**Cách sửa:** thống nhất route như một phần contract giữa hai ứng dụng; kiểm tra cả dấu chấm, tên và route pattern.

### Hai phía không thống nhất codec

Client gửi object nhưng server không có decoder tương ứng, hoặc MIME type không tương thích, có thể gây lỗi mã hóa/giải mã.

**Cách sửa:** dùng codec được hỗ trợ ở cả hai phía; với DTO JSON/CBOR, kiểm tra `RSocketStrategies` và dependency. Với metadata tùy chỉnh, đăng ký encoder và decoder cùng MIME type.

### Nuốt lỗi gửi

Nếu dùng `onErrorResume(error -> Mono.empty())` mà không ghi nhận hoặc chuyển lỗi đi, tầng gọi có thể tưởng request thành công.

**Cách sửa:** log và chuyển lỗi theo chính sách của ứng dụng. Lưu ý lỗi transport/serialization có thể xuất hiện trên Mono; lỗi xử lý nghiệp vụ ở remote không được trả về như response của Fire-and-Forget.

### Retry gây xử lý trùng

Khi trạng thái gửi không chắc chắn, retry có thể làm phía nhận thấy cùng một sự kiện nhiều lần.

**Cách sửa:** gắn `eventId` ổn định, lưu dấu đã xử lý ở phía nhận và thiết kế thao tác idempotent. Không giả định Fire-and-Forget tự cung cấp exactly-once delivery.

### Nhầm `send()` với `sendMetadata()`

`send()` gửi request Fire-and-Forget có route/payload. `sendMetadata()` phát một metadata notification ở cấp kết nối. Chọn đúng API theo loại dữ liệu và phạm vi của thông tin cần truyền.

## 7. Sơ đồ luồng

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng gửi
    participant Req as RSocketRequester
    participant Server as RSocket server
    participant Handler as @MessageMapping handler

    App->>Req: route + data + send()
    Req->>Server: REQUEST_FNF (payload + metadata)
    Server->>Handler: dispatch theo route
    Req-->>App: Mono<Void> complete hoặc error
    Note over App,Handler: Không có response payload xác nhận xử lý remote
~~~

Sơ đồ cho thấy hai luồng cần phân biệt: việc gửi ở phía requester và việc xử lý ở phía responder. Fire-and-Forget không nối kết quả xử lý của handler trở lại Mono phía gửi.

## 8. Checklist khi áp dụng

- [ ] Đã chọn Fire-and-Forget vì bên gửi không cần response nghiệp vụ.
- [ ] Route trong `route(...)` khớp với `@MessageMapping(...)`.
- [ ] Payload có encoder/decoder tương thích ở hai phía.
- [ ] Mono từ `send()` được trả về hoặc subscribe tại nơi quản lý lifecycle.
- [ ] Lỗi gửi được ghi nhận và xử lý.
- [ ] Không diễn giải Mono complete thành xác nhận remote đã lưu dữ liệu.
- [ ] Nếu có retry, phía nhận xử lý idempotent bằng định danh sự kiện.
- [ ] Nếu cần đảm bảo giao nhận hoặc ACK, đã chọn cơ chế phù hợp hơn Fire-and-Forget.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): các interaction model, `RSocketRequester`, `send()`, route, payload và annotated responders.
- [Spring Framework Javadoc — RSocketRequester.RetrieveSpec](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html): hợp đồng trả về của `send()` và sự khác biệt với `retrieveMono()`.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): cấu hình server, `RSocketStrategies` và `RSocketRequester.Builder`.

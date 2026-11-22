# Ánh xạ mô hình tương tác từ kiểu đầu vào và đầu ra

Trong Spring Messaging RSocket, Spring xác định mô hình tương tác của một phương thức xử lý dựa trên **cardinality** (số lượng thông điệp) của payload đầu vào và giá trị trả về. Kiểu Java khai báo trong chữ ký phương thức quyết định cardinality: một giá trị, nhiều giá trị hay không có giá trị. Tên route và số phần tử thực tế phát ra khi chạy không thay đổi quy tắc này.

Bốn mô hình RSocket là Request-Response, Request-Stream, Fire-and-Forget và Channel. Kết nối RSocket có tính hai chiều: sau khi kết nối được thiết lập, cả hai đầu đều có thể khởi tạo request và xử lý request từ đầu kia.

## 1. Hiểu cardinality của đầu vào và đầu ra

Spring xét payload của phương thức, thường là tham số được đánh dấu bằng **@Payload**. Có thể bỏ annotation này khi Spring có thể nhận diện tham số không phải kiểu đơn giản là payload.

| Cardinality | Đầu vào | Đầu ra |
|---|---|---|
| **0** | Phương thức không có tham số payload | **void** hoặc **Mono<Void>** |
| **1** | Một đối tượng cụ thể hoặc **Mono<T>** | Một đối tượng cụ thể hoặc **Mono<T>** |
| **Many** | **Flux<T>** | **Flux<T>** |

Một số điểm cần phân biệt:

- **Mono<T>** biểu diễn tối đa một giá trị theo hợp đồng single-value của Reactor; Spring xếp nó vào cardinality **1**.
- **Flux<T>** biểu diễn một luồng có thể phát ra nhiều giá trị; Spring xếp nó vào cardinality **Many**, kể cả khi luồng rỗng hoặc chỉ phát một phần tử ở một lần chạy cụ thể.
- **List<T>** là **một đối tượng payload**. **Mono<List<T>>** vẫn là cardinality **1**; nó gửi một payload chứa danh sách.
- **Flux<T>** là nhiều payload riêng biệt theo luồng. Nếu muốn truyền từng phần tử qua mạng, dùng **Flux<T>** thay vì gói tất cả vào một **List<T>**.
- Với đầu vào, không có tham số payload là cardinality **0**. Các tham số hạ tầng như **RSocketRequester**, **@DestinationVariable**, **@Header** hoặc **@Headers** không làm tăng cardinality của payload.

Cardinality được xác định từ kiểu khai báo, không phải từ số phần tử cuối cùng. Ví dụ, một phương thức nhận **Flux<Event>** vẫn là đầu vào Many dù publisher chỉ phát một event; phương thức trả **Flux<Result>** vẫn là đầu ra Many dù lần chạy đó chỉ có một kết quả.

## 2. Bảng ánh xạ đầu vào/đầu ra

Đối với các phương thức responder dùng **@MessageMapping**, Spring hỗ trợ các tổ hợp sau:

| Cardinality đầu vào | Cardinality đầu ra | Mô hình tương tác | Ý nghĩa |
|---|---|---|---|
| 0 hoặc 1 | 0 | Fire-and-Forget hoặc Request-Response | Nhận không quá một payload và không phát giá trị phản hồi |
| 0 hoặc 1 | 1 | Request-Response | Nhận không quá một payload, trả một giá trị theo kiểu single-value |
| 0 hoặc 1 | Many | Request-Stream | Nhận không quá một payload, phát một luồng phản hồi |
| Many | 0, 1 hoặc Many | Channel (Request-Channel) | Nhận một luồng payload; responder có thể không phát phản hồi, phát một giá trị hoặc phát một luồng |

### Request-Response

Dùng khi một request cần một kết quả tương ứng. Đầu vào có thể là một payload hoặc không có payload; đầu ra là một giá trị cụ thể hoặc **Mono<T>**.

Ví dụ phù hợp: tra cứu trạng thái đơn hàng, lấy hồ sơ người dùng hoặc tính một kết quả dựa trên một yêu cầu.

### Request-Stream

Dùng khi một request ban đầu tạo ra nhiều kết quả theo thời gian. Đầu vào là một payload hoặc không có payload; đầu ra là **Flux<T>**.

Ví dụ phù hợp: theo dõi giá cổ phiếu, nhận các phép đo cảm biến hoặc lấy các sự kiện phát sinh sau một truy vấn đăng ký.

### Fire-and-Forget

Dùng khi bên gửi chỉ cần gửi một thông điệp và không cần dữ liệu phản hồi ở cấp ứng dụng. Đầu vào có thể là một payload hoặc không có payload; đầu ra không có giá trị (**void** hoặc **Mono<Void>**).

Ví dụ phù hợp: gửi telemetry, ghi nhận một sự kiện phụ hoặc phát lệnh không yêu cầu xác nhận nghiệp vụ. Nếu bên gửi cần biết thao tác đã được xử lý thành công, hãy thiết kế một phản hồi có dữ liệu, chẳng hạn **Mono<Receipt>**, và dùng Request-Response.

### Channel (Request-Channel)

Dùng khi hai bên trao đổi các luồng thông điệp trên cùng một tương tác. Đầu vào của responder là **Flux<T>**; đầu ra có thể là **void**/**Mono<Void>**, một giá trị hoặc **Flux<R>**.

Ví dụ phù hợp: chat hai chiều, truyền dữ liệu tương tác, điều khiển thiết bị liên tục hoặc trao đổi các sự kiện theo thời gian thực. Channel hỗ trợ back pressure: nhu cầu nhận dữ liệu được truyền ngược về phía phát để điều tiết tốc độ.

**Lưu ý về hàng đầu tiên của bảng:** Spring liệt kê cả Fire-and-Forget và Request-Response cho đầu vào 0/1, đầu ra 0. Khi phía gọi không cần phản hồi, dùng Fire-and-Forget. Nếu hợp đồng nghiệp vụ cần xác nhận, nên trả một kiểu dữ liệu xác nhận rõ ràng thay vì dựa vào một kết thúc không có payload.

## 3. Ví dụ phương thức responder

Đoạn mã sau minh họa các chữ ký phương thức tiêu biểu. Đây là một lớp controller dành cho ứng dụng đã có Spring Messaging, Reactor và cấu hình RSocket; riêng đoạn mã không phải ứng dụng độc lập có thể chạy bằng **java** mà không có các dependency và cấu hình đó.

~~~java
import java.time.Instant;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DeviceRSocketController {

    @MessageMapping("device.status")
    public Mono<DeviceStatus> status(DeviceQuery query) {
        return Mono.just(new DeviceStatus(query.deviceId(), "ONLINE"));
    }

    @MessageMapping("device.history")
    public Flux<Reading> history(DeviceQuery query) {
        return Flux.just(
            new Reading(query.deviceId(), 21.5, Instant.parse("2026-01-01T10:00:00Z")),
            new Reading(query.deviceId(), 22.0, Instant.parse("2026-01-01T10:00:01Z"))
        );
    }

    @MessageMapping("audit.append")
    public Mono<Void> append(AuditEvent event) {
        return Mono.fromRunnable(() ->
            System.out.println("Saved event " + event.id())
        );
    }

    @MessageMapping("chat.exchange")
    public Flux<ChatMessage> exchange(@Payload Flux<ChatMessage> incoming) {
        return incoming.map(message ->
            new ChatMessage("server", "Received: " + message.body())
        );
    }

    @MessageMapping("server.time")
    public Mono<Instant> time() {
        return Mono.just(Instant.now());
    }

    public record DeviceQuery(String deviceId) {}
    public record DeviceStatus(String deviceId, String state) {}
    public record Reading(String deviceId, double value, Instant at) {}
    public record AuditEvent(String id) {}
    public record ChatMessage(String sender, String body) {}
}
~~~

Ánh xạ của từng phương thức:

| Phương thức | Đầu vào | Đầu ra | Mô hình |
|---|---|---|---|
| **status** | **DeviceQuery** (1) | **Mono<DeviceStatus>** (1) | Request-Response |
| **history** | **DeviceQuery** (1) | **Flux<Reading>** (Many) | Request-Stream |
| **append** | **AuditEvent** (1) | **Mono<Void>** (0) | Fire-and-Forget hoặc Request-Response theo tương tác phía gọi |
| **exchange** | **Flux<ChatMessage>** (Many) | **Flux<ChatMessage>** (Many) | Channel |
| **time** | Không có payload (0) | **Mono<Instant>** (1) | Request-Response |

Ở phương thức **exchange**, **@Payload** làm rõ rằng **Flux<ChatMessage>** là luồng payload đầu vào. Nếu bỏ tham số này và chỉ nhận **RSocketRequester**, **@Header** hoặc biến route, phương thức không có payload đầu vào.

## 4. Chọn mô hình từ phía gọi bằng RSocketRequester

**RSocketRequester** cung cấp API fluent để gửi dữ liệu và khai báo kiểu phản hồi. Mô hình tương tác được suy ra từ cardinality của dữ liệu gửi và phương thức lấy kết quả.

~~~java
// Request-Response: một payload, một kết quả.
Mono<DeviceStatus> status = requester.route("device.status")
    .data(new DeviceQuery("sensor-01"))
    .retrieveMono(DeviceStatus.class);

// Request-Stream: một payload, một luồng kết quả.
Flux<Reading> readings = requester.route("device.history")
    .data(new DeviceQuery("sensor-01"))
    .retrieveFlux(Reading.class);

// Fire-and-Forget: gửi payload, không nhận payload phản hồi.
Mono<Void> sent = requester.route("audit.append")
    .data(new AuditEvent("event-001"))
    .send();

// Request-Response không có payload đầu vào.
Mono<Instant> serverTime = requester.route("server.time")
    .retrieveMono(Instant.class);

// Channel: gửi một luồng payload và nhận một luồng phản hồi.
Flux<ChatMessage> replies = requester.route("chat.exchange")
    .data(outboundMessages, ChatMessage.class)
    .retrieveFlux(ChatMessage.class);
~~~

Trong ví dụ Channel, **outboundMessages** là một **Flux<ChatMessage>**. Overload **data(Publisher, Class)** giúp khai báo kiểu phần tử khi gửi publisher nhiều giá trị; điều này hữu ích cho việc chọn encoder và tránh phải suy luận kiểu ở từng phần tử. Có overload nhận **ParameterizedTypeReference** khi kiểu phần tử là generic.

Một số quy tắc khi gọi:

- Bỏ qua **.data(...)** khi request không có payload.
- Dùng **.retrieveMono(Type.class)** khi hợp đồng trả một kết quả.
- Dùng **.retrieveFlux(Type.class)** khi hợp đồng trả một luồng kết quả.
- Dùng **.send()** cho Fire-and-Forget. **Mono<Void>** từ **send()** chỉ cho biết thông điệp đã được gửi thành công; nó **không xác nhận** responder đã xử lý xong nghiệp vụ.
- Với Channel, gửi publisher đầu vào và nhận publisher phản hồi. Tài liệu RSocketRequester nêu tổ hợp Many-to-one là không hợp lệ ở API requester; vì vậy nên giữ hợp đồng gọi Channel theo dạng luồng phản hồi (**retrieveFlux**) ngay cả khi ứng dụng hiện chỉ phát một phần tử.

## 5. Payload, metadata và serialization

Cardinality chỉ quyết định hình thức trao đổi thông điệp. Nó không quyết định cách mã hóa dữ liệu.

- **Payload** là dữ liệu nghiệp vụ được gửi trong request hoặc response.
- **Metadata** mang thông tin định tuyến, xác thực hoặc dữ liệu phụ trợ. Trong Spring, metadata đã đăng ký có thể được nhận qua **@Header** hoặc **@Headers**; biến trong route có thể được nhận qua **@DestinationVariable**.
- **RSocketStrategies** cấu hình encoder và decoder cho payload/metadata. Các codec trong **spring-web** hỗ trợ những định dạng như JSON, CBOR và Protobuf tùy dependency được đăng ký.
- Route của RSocket được truyền qua metadata. Route chỉ chọn handler; nó không tự quyết định Request-Response hay Request-Stream.

Ví dụ cấu hình codec CBOR:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
    .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
    .build();
~~~

Spring Boot có thể tự cấu hình hạ tầng RSocket và **RSocketStrategies** khi dùng starter phù hợp. Có thể tùy chỉnh codec bằng bean hoặc cấu hình strategies dùng chung cho requester và responder.

**@ConnectMapping** xử lý sự kiện ở cấp kết nối, như frame **SETUP** ban đầu và thông báo **METADATA_PUSH**. Phương thức này chỉ trả **void** hoặc **Mono<Void>**; nó không thuộc bảng ánh xạ request của **@MessageMapping**.

## 6. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| **Mono<List<T>>** là stream vì chứa danh sách | Đây là một payload duy nhất; cardinality là 1 |
| **Flux<T>** chỉ có một phần tử thì là Request-Response | Kiểu vẫn là Many; cardinality không dựa trên số phần tử ở runtime |
| Một tham số **Flux<T>** chỉ là cách viết khác của nhiều tham số đơn | Nó biểu diễn luồng payload đầu vào và làm tương tác trở thành Channel |
| **Mono<Void>** trả về một đối tượng rỗng | Đây là đầu ra không có giá trị, cardinality 0 |
| Fire-and-Forget xác nhận thao tác nghiệp vụ đã hoàn tất | Đây là tương tác một chiều; cần response payload nếu cần acknowledgment |
| **@Header** hoặc **@DestinationVariable** là payload | Chúng là metadata/route data, không làm thay đổi cardinality payload |
| Tên route quyết định mô hình tương tác | Mô hình được xác định bởi cardinality đầu vào/đầu ra và cách phía gọi khởi tạo request |

Một lỗi thiết kế phổ biến là dùng Fire-and-Forget cho thao tác mà bên gọi cần biết kết quả. Khi cần xác nhận, trả về một kiểu có ý nghĩa nghiệp vụ như **Mono<AuditReceipt>** và gọi bằng Request-Response. Ngược lại, không nên thu toàn bộ một luồng thành **Mono<List<T>>** chỉ để dễ xử lý nếu yêu cầu thực sự là truyền kết quả dần dần; làm vậy thay đổi hợp đồng từ nhiều payload thành một payload.

## 7. Quy trình chọn chữ ký phương thức

1. Xác định bên gửi có payload hay không.
2. Nếu có một payload, dùng kiểu đối tượng hoặc **Mono<T>**; nếu gửi nhiều payload liên tiếp, dùng **Flux<T>**.
3. Xác định bên gọi cần không có phản hồi, một kết quả hay một luồng kết quả.
4. Chọn **void**/**Mono<Void>**, kiểu đơn/**Mono<T>** hoặc **Flux<T>** tương ứng.
5. Đối chiếu tổ hợp với bảng ánh xạ và chọn API requester tương ứng: **send**, **retrieveMono** hoặc **retrieveFlux**.
6. Kiểm thử cả hai đầu của kết nối: kiểu payload, kiểu phản hồi, trường hợp publisher rỗng, lỗi và back pressure.

Nếu phương thức nhận **Flux** hoặc trả **Flux**, hãy kiểm thử luồng với nhiều phần tử và kiểm tra việc hủy subscription/back pressure. Với Fire-and-Forget, kiểm thử riêng lỗi xử lý ở responder vì completion của **send()** không phải acknowledgment nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): mô hình tương tác, cardinality, **@MessageMapping**, **RSocketRequester**, metadata và codecs.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): auto-configuration, starter và **RSocketStrategies**.

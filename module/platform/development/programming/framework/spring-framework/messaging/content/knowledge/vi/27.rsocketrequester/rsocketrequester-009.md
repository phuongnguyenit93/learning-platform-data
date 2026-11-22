# Truyền Publisher đầu vào cho tương tác request-channel

## Mục tiêu

Trong RSocket, request-channel là kiểu tương tác hai chiều: bên khởi tạo gửi một luồng thông điệp và bên nhận có thể trả về một luồng thông điệp khác trên cùng request. Với Spring, có thể biểu diễn luồng đầu vào bằng Reactive Streams Publisher, thường là Reactor Flux, rồi khai báo kiểu phản hồi bằng retrieveFlux.

Cách này phù hợp với các luồng dữ liệu liên tục hoặc theo lô như telemetry, cập nhật trạng thái, sự kiện nghiệp vụ, dữ liệu cảm biến và xử lý nhiều lệnh trong một phiên tương tác. Client có thể tiếp tục gửi phần tử mới trong khi vẫn nhận phản hồi từ server.

## 1. Phân biệt request-channel với các kiểu tương tác khác

Spring xác định kiểu tương tác dựa trên số lượng phần tử mà đầu vào và đầu ra có thể phát:

| Đầu vào | Đầu ra | Kiểu tương tác |
| --- | --- | --- |
| Một giá trị hoặc Mono | Một giá trị hoặc Mono | Request-Response |
| Một giá trị hoặc Mono | Flux | Request-Stream |
| Publisher nhiều giá trị, ví dụ Flux | Flux | Request-Channel |
| Một giá trị | Không có phản hồi | Fire-and-Forget |

Điểm quyết định request-channel là đầu vào có tính chất nhiều phần tử. Khi dùng RSocketRequester, tổ hợp thường gặp là:

~~~java
Flux<Response> responses = requester.route("some.route")
    .data(requestPublisher, Request.class)
    .retrieveFlux(Response.class);
~~~

retrieveFlux thực hiện request-stream hoặc request-channel tùy theo đầu vào là một payload hay nhiều payload. Với một Publisher nhiều phần tử như Flux, Spring dùng request-channel. Publisher đầu vào và Flux đầu ra tạo thành hai luồng dữ liệu gắn với cùng một request.

Không dùng retrieveMono cho Publisher nhiều phần tử. RSocket không có tương tác many-to-one; retrieveMono sẽ phát sinh lỗi khi payload đầu vào là Publisher nhiều giá trị. Nếu cần nhận đúng một kết quả tổng hợp sau khi gửi nhiều phần tử, hãy nhận bằng retrieveFlux rồi chuyển thành Mono bằng single() hoặc singleOrEmpty() theo quy tắc số kết quả mong đợi.

## 2. Truyền Publisher bằng RSocketRequester

RSocketRequester cung cấp chuỗi API fluent để khai báo route, metadata, payload đầu vào và kiểu phản hồi:

- route(String, Object...) xác định route của responder. Route được gửi trong metadata của request.
- data(Object) nhận một giá trị cụ thể, một Reactive Streams Publisher hoặc một producer có thể được ReactiveAdapterRegistry chuyển thành Publisher.
- data(Object, Class<?>) nhận thêm kiểu phần tử. Với Publisher đồng nhất kiểu, Spring có thể tìm Encoder tương thích một lần ở đầu luồng thay vì kiểm tra kiểu và tìm Encoder cho từng phần tử.
- data(Object, ParameterizedTypeReference<?>) dùng khi kiểu phần tử có generic type, chẳng hạn Envelope<OrderEvent>.
- retrieveFlux(Class<?>) hoặc retrieveFlux(ParameterizedTypeReference<?>) khai báo kiểu phần tử phản hồi và trả về Flux.

Ví dụ tối thiểu:

~~~java
Flux<Command> commands = Flux.just(command1, command2, command3);

Flux<Acknowledgement> acknowledgements = requester.route("commands.process")
    .data(commands, Command.class)
    .retrieveFlux(Acknowledgement.class);
~~~

Nếu bỏ type hint, có thể dùng data(commands). Với luồng nhiều phần tử cùng kiểu, overload có Class<?> thường rõ ràng hơn và giúp tránh việc tra cứu Encoder lặp lại. Type hint phải khớp với kiểu thực tế của từng phần tử.

Với phần tử có kiểu generic, truyền ParameterizedTypeReference cho kiểu của từng phần tử Publisher:

~~~java
Flux<Envelope<OrderEvent>> events = ...;

ParameterizedTypeReference<Envelope<OrderEvent>> eventType =
    new ParameterizedTypeReference<>() {};

Flux<Acknowledgement> replies = requester.route("orders.ingest")
    .data(events, eventType)
    .retrieveFlux(Acknowledgement.class);
~~~

Type reference ở đây mô tả Envelope<OrderEvent>, không phải kiểu Flux bao bên ngoài.

## 3. Ví dụ: gửi luồng giá và nhận cảnh báo

Ví dụ dùng Java 17 record làm payload. Client gửi nhiều PriceTick; server lọc các tick có giá từ 100 trở lên và trả về từng PriceAlert tương ứng.

### DTO

Đặt mỗi record trong file riêng:

~~~java
import java.math.BigDecimal;

public record PriceTick(
    String symbol,
    long sequence,
    BigDecimal price
) {}
~~~

~~~java
public record PriceAlert(
    String symbol,
    long sequence,
    String message
) {}
~~~

### Responder phía server

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
class PriceChannelController {

    @MessageMapping("prices.watch")
    Flux<PriceAlert> watch(@Payload Flux<PriceTick> ticks) {
        return ticks
            .filter(tick -> tick.price().compareTo(new BigDecimal("100.00")) >= 0)
            .map(tick -> new PriceAlert(
                tick.symbol(),
                tick.sequence(),
                "Giá vượt ngưỡng: " + tick.price()
            ));
    }
}
~~~

Flux<PriceTick> biểu thị đầu vào nhiều phần tử; Flux<PriceAlert> biểu thị đầu ra nhiều phần tử. Cặp cardinality many-to-many này được ánh xạ thành request-channel. Spring nhận và giải mã từng payload rồi chuyển chúng thành phần tử của Flux đầu vào. Kết quả từ Flux trả về được mã hóa và gửi ngược về requester.

### Requester phía client

Giả sử requester đã được cấu hình và kết nối tới server:

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Flux;

class PriceChannelClient {

    private final RSocketRequester requester;

    PriceChannelClient(RSocketRequester requester) {
        this.requester = requester;
    }

    Flux<PriceAlert> watch() {
        Flux<PriceTick> ticks = Flux.just(
            new PriceTick("ACME", 1, new BigDecimal("98.50")),
            new PriceTick("ACME", 2, new BigDecimal("101.25")),
            new PriceTick("ACME", 3, new BigDecimal("103.00"))
        );

        return requester.route("prices.watch")
            .data(ticks, PriceTick.class)
            .retrieveFlux(PriceAlert.class);
    }
}
~~~

Có thể chạy ví dụ trong một ứng dụng demo bằng cách đăng ký xử lý kết quả:

~~~java
client.watch()
    .doOnNext(System.out::println)
    .blockLast();
~~~

Kết quả gồm hai cảnh báo vì tick đầu tiên có giá thấp hơn ngưỡng:

~~~text
PriceAlert[symbol=ACME, sequence=2, message=Giá vượt ngưỡng: 101.25]
PriceAlert[symbol=ACME, sequence=3, message=Giá vượt ngưỡng: 103.00]
~~~

Đây là các đoạn mã trong một ứng dụng Spring đã cấu hình RSocket và codec; chúng không phải chương trình Java độc lập có thể chạy chỉ bằng javac. blockLast() chỉ dùng để minh họa trong ứng dụng dòng lệnh hoặc test. Trong ứng dụng reactive thực tế, nên trả Flux cho tầng gọi tiếp theo và tránh block trên event-loop thread.

## 4. Cấu hình kết nối và codec

Một requester TCP cơ bản có thể được tạo như sau:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .tcp("localhost", 7000);
~~~

Kết nối được thiết lập khi request được thực hiện. Có thể dùng WebSocket thay cho TCP bằng builder tương ứng nếu server được cấu hình trên WebSocket.

Với Spring Boot, dependency spring-boot-starter-rsocket cung cấp hạ tầng RSocket và hỗ trợ tự cấu hình RSocketStrategies. Có thể cấu hình server TCP trong application.properties:

~~~properties
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
~~~

Boot tự cấu hình các codec Jackson JSON/CBOR khi các dependency tương ứng có mặt. Nếu dùng Spring Framework trực tiếp hoặc payload là kiểu tùy chỉnh, hãy cấu hình Encoder và Decoder tương ứng trong RSocketStrategies ở cả hai phía. Codec phải tương thích với data MIME type của kết nối; nếu hai phía không thống nhất định dạng, payload có thể không giải mã được.

## 5. Backpressure và vòng đời Publisher

RSocket mang semantics Reactive Streams qua ranh giới mạng. Với request-stream và request-channel, bên nhận gửi tín hiệu demand để điều tiết số phần tử được truyền. Trong request-channel, điều tiết này áp dụng cho luồng phản hồi và luồng payload đầu vào; producer không cần chủ động đẩy vô hạn dữ liệu vào socket.

Một số nguyên tắc khi triển khai:

- Trả về Publisher từ responder. Không gọi subscribe() bên trong phương thức @MessageMapping để tự tách luồng khỏi vòng đời request do Spring quản lý.
- Chỉ request bắt đầu khi Flux phản hồi được subscribe. Nếu không có subscriber, chuỗi reactive chưa được tiêu thụ.
- Tránh collectList() với luồng lớn hoặc không giới hạn vì thao tác này giữ toàn bộ phần tử trong bộ nhớ.
- Dùng concatMap khi cần xử lý tuần tự và giữ thứ tự; dùng flatMap với giới hạn concurrency khi xử lý song song là phù hợp.
- Nếu nguồn là hot Publisher, kiểm tra thời điểm phát dữ liệu và chính sách lưu đệm. Một nguồn đã phát trước khi request được subscribe có thể làm mất phần tử đối với subscriber đến sau.
- Khi phía gọi hủy subscription, request có thể được hủy theo cơ chế Reactive Streams. Các operator và tác vụ phía ứng dụng nên tôn trọng cancellation để dừng công việc không còn cần thiết.
- Xử lý lỗi bằng các operator như onErrorMap hoặc onErrorResume ở đúng tầng. Một lỗi không được xử lý trong luồng thường làm kết thúc tương tác.

Backpressure không thay thế giới hạn tài nguyên ở tầng ứng dụng. Vẫn cần giới hạn concurrency, kích thước buffer, thời gian xử lý và thời gian sống của kết nối theo tải thực tế.

## 6. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| retrieveMono phát sinh lỗi khi gửi Flux | Đầu vào là nhiều payload nhưng đang yêu cầu một kết quả kiểu request-response | Dùng retrieveFlux; nếu chỉ cần một kết quả, dùng single() hoặc singleOrEmpty() sau retrieveFlux |
| Server không nhận được request | Route trong route(...) không khớp @MessageMapping hoặc server chưa lắng nghe đúng transport/port | Đối chiếu chính xác route và cấu hình kết nối |
| Lỗi encode/decode payload | Thiếu Encoder/Decoder hoặc data MIME type không tương thích | Cấu hình RSocketStrategies và codec thống nhất ở hai phía |
| Lỗi chuyển đổi generic type | Chỉ truyền Class<?> làm mất thông tin kiểu lồng nhau | Dùng ParameterizedTypeReference cho kiểu của từng phần tử |
| Luồng không phát dữ liệu | Flux chưa được subscribe, nguồn hot đã phát trước subscription hoặc nguồn không tạo phần tử | Kiểm tra subscriber và vòng đời của Publisher |
| Tốn bộ nhớ khi chạy lâu | Buffer không giới hạn, collectList() trên luồng lớn hoặc xử lý song song không giới hạn | Giới hạn buffer/concurrency và giữ pipeline có backpressure |

## 7. Checklist triển khai

1. Xác định đầu vào thực sự là luồng nhiều phần tử; dùng Flux hoặc Publisher nhiều giá trị.
2. Khai báo responder nhận Flux<T> và trả Flux<R> khi cần luồng hai chiều.
3. Dùng route(...) trùng với route của @MessageMapping.
4. Gọi data(publisher, ElementType.class) hoặc overload ParameterizedTypeReference cho phần tử generic.
5. Dùng retrieveFlux(ResponseType.class) để nhận luồng phản hồi.
6. Cấu hình codec và data MIME type tương thích giữa requester và responder.
7. Kiểm tra backpressure, cancellation, error handling, concurrency và giới hạn bộ nhớ.
8. Test với nhiều phần tử đầu vào, phản hồi xen kẽ, nguồn rỗng, lỗi giữa luồng và trường hợp client hủy subscription.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket và RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocketRequester.RequestSpec — Spring Framework 7.0 API](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RequestSpec.html)
- [RSocketRequester.RetrieveSpec — Spring Framework 7.0 API](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)

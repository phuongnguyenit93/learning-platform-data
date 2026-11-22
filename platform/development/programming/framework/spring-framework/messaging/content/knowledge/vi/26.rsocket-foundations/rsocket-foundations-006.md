# Request-channel và luồng dữ liệu hai chiều

> Phạm vi: Spring Framework RSocket, Java 17+ và Project Reactor. Bài này giải thích cách một request-channel gửi một luồng dữ liệu từ requester đến responder đồng thời nhận một luồng dữ liệu ngược lại; cách Spring ánh xạ mô hình đó bằng Flux, @MessageMapping và RSocketRequester; cùng các nguyên tắc backpressure, hoàn tất, hủy và xử lý lỗi.

## 1. Request-channel là gì?

RSocket cung cấp bốn interaction model chính:

| Interaction | Dữ liệu gửi | Dữ liệu nhận | Trường hợp phù hợp |
|---|---|---|---|
| Request-Response | Một message | Một message | Gọi một thao tác và nhận một kết quả. |
| Request-Stream | Một message | Một stream | Gửi tiêu chí một lần rồi nhận nhiều kết quả. |
| Request-Channel | Một stream | Một stream | Hai bên trao đổi nhiều message đồng thời trong cùng một request. |
| Fire-and-Forget | Một message | Không có response payload | Gửi sự kiện một chiều, không cần kết quả. |

Request-channel là interaction model cho phép requester gửi nhiều message trong khi responder cũng gửi nhiều message trở lại. Hai luồng có thể hoạt động đồng thời, không cần đợi toàn bộ luồng request kết thúc mới bắt đầu nhận response.

Ví dụ thực tế:

- Một client gửi liên tục các lệnh điều khiển thiết bị và nhận trạng thái thiết bị sau từng lệnh.
- Một ứng dụng gửi các đoạn dữ liệu âm thanh hoặc tín hiệu cảm biến, đồng thời nhận phản hồi phân tích.
- Một client gửi các thao tác chỉnh sửa tài liệu và nhận các thay đổi hoặc xác nhận từ server.
- Một phiên xử lý dữ liệu tương tác, trong đó client vừa gửi đầu vào vừa nhận kết quả tăng dần.

Request-channel không phải là một topic broadcast hay một hàng đợi lưu trữ message. Nó là một request có vòng đời, có luồng đầu vào và luồng đầu ra. Khi request kết thúc hoặc bị hủy, các luồng thuộc request đó cũng kết thúc theo semantics của RSocket.

## 2. Cơ chế ở tầng RSocket

Sau khi kết nối RSocket được thiết lập, requester bắt đầu channel bằng frame REQUEST_CHANNEL. Frame ban đầu mang payload đầu tiên (nếu có) và lượng demand ban đầu dành cho response stream. Các payload request tiếp theo được gửi bằng PAYLOAD frame. Responder cũng gửi PAYLOAD frame để phát response về requester.

Luồng tổng quát:

~~~text
Requester                                      Responder
    |                                              |
    |------ REQUEST_CHANNEL (payload đầu tiên) --->|
    |                                              |
    |------ PAYLOAD (request tiếp theo) ---------->|
    |<----- PAYLOAD (response đầu tiên) -----------|
    |------ PAYLOAD (request tiếp theo) ---------->|
    |<----- PAYLOAD (response tiếp theo) ----------|
    |<----- PAYLOAD (response tiếp theo) ----------|
    |------ PAYLOAD (request tiếp theo) ---------->|
    |                                              |
    |------ COMPLETE / kết thúc request stream --->|
    |<----- COMPLETE / kết thúc response stream ---|
    |                                              |
~~~

Các frame request và response có thể xen kẽ. Requester không phải gửi hết dữ liệu trước rồi mới nhận phản hồi. Responder có thể xử lý từng phần dữ liệu đến và phát kết quả khi có thể.

RSocket cũng định nghĩa các frame điều khiển như REQUEST_N, CANCEL, ERROR và COMPLETE:

- REQUEST_N thông báo số payload bổ sung mà bên nhận sẵn sàng nhận.
- CANCEL hủy một request đang hoạt động.
- ERROR kết thúc request với lỗi.
- COMPLETE báo rằng một phía đã hoàn thành việc phát payload của mình.

RSocket là giao thức hai chiều và đối xứng. Sau khi kết nối được thiết lập, cả hai phía đều có thể khởi tạo request. Trong một request-channel cụ thể, requester và responder vẫn có vai trò rõ ràng đối với hai luồng của request đó.

## 3. Spring xác định request-channel bằng Flux

Spring dùng cardinality của đầu vào và đầu ra để suy ra interaction model của phương thức @MessageMapping:

| Đầu vào của handler | Giá trị trả về | Interaction model |
|---|---|---|
| Một payload hoặc không có payload | Một giá trị / Mono | Request-Response hoặc Fire-and-Forget tùy chữ ký. |
| Một payload hoặc không có payload | Flux | Request-Stream. |
| Flux payload | void hoặc Mono<Void> | Request-Channel không có response payload. |
| Flux payload | Một giá trị hoặc Mono | Request-Channel với response đơn. |
| Flux payload | Flux | Request-Channel với response stream. |

Trường hợp hai luồng đều có nhiều phần tử thường là trường hợp thể hiện rõ nhất dữ liệu hai chiều: handler nhận Flux<Request> và trả về Flux<Response>.

Spring hỗ trợ các kiểu Reactive Streams như Mono và Flux. Với request-channel, đầu vào của handler là publisher nhiều giá trị; đầu ra cũng có thể là publisher nhiều giá trị. Spring chuyển các tín hiệu reactive thành luồng payload RSocket tương ứng.

## 4. Viết responder với @MessageMapping

Ví dụ dưới đây nhận nhiều lệnh từ client và phát một sự kiện phản hồi cho mỗi lệnh. Route RSocket là chat.channel:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class ChatChannelController {

    public record ClientCommand(String text) {}

    public record ServerEvent(long sequence, String message) {}

    @MessageMapping("chat.channel")
    public Flux<ServerEvent> channel(Flux<ClientCommand> commands) {
        return commands
                .index()
                .map(indexed -> new ServerEvent(
                        indexed.getT1(),
                        "Processed: " + indexed.getT2().text()
                ));
    }
}
~~~

Giải thích:

1. @MessageMapping("chat.channel") khai báo route của request.
2. Tham số Flux<ClientCommand> thể hiện nhiều payload đầu vào.
3. index() thêm số thứ tự bắt đầu từ 0 cho từng command.
4. map() chuyển mỗi command thành một ServerEvent.
5. Flux<ServerEvent> là response stream được gửi ngược về requester.

Vì cả input và output đều là Flux, Spring xác định đây là Request-Channel. Mỗi command có thể tạo một response tương ứng. Khi publisher đầu vào hoàn tất và phép biến đổi đã xử lý xong các phần tử còn lại, response Flux cũng hoàn tất.

Trong ví dụ thực tế, phần xử lý có thể gọi service bất đồng bộ. Dùng concatMap khi cần giữ thứ tự xử lý và thứ tự response:

~~~java
@MessageMapping("orders.channel")
public Flux<OrderReply> processOrders(Flux<OrderCommand> commands) {
    return commands.concatMap(orderService::process);
}
~~~

Đoạn thứ hai giả định orderService.process(OrderCommand) trả về Mono<OrderReply>. concatMap xử lý tuần tự từng command và giữ thứ tự response. Nếu nghiệp vụ cho phép xử lý song song, có thể dùng flatMap với concurrency phù hợp; khi đó thứ tự response có thể khác thứ tự request.

## 5. Gửi request-channel từ client bằng RSocketRequester

RSocketRequester là API fluent của Spring để tạo request và mã hóa/giải mã data cùng metadata. Với một publisher nhiều phần tử, truyền publisher vào data() và nhận response bằng retrieveFlux():

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Flux;

RSocketRequester requester =
        RSocketRequester.builder().tcp("localhost", 7000);

Flux<ClientCommand> outgoing = Flux.just(
        new ClientCommand("open"),
        new ClientCommand("update"),
        new ClientCommand("close")
);

Flux<ServerEvent> incoming = requester
        .route("chat.channel")
        .data(outgoing, ClientCommand.class)
        .retrieveFlux(ServerEvent.class);

incoming.subscribe(
        event -> System.out.println(event.sequence() + ": " + event.message()),
        error -> System.err.println("Channel failed: " + error.getMessage()),
        () -> System.out.println("Channel completed")
);
~~~

Cần hiểu ba bước:

- route() chọn route metadata để responder tìm đúng handler.
- data() cung cấp publisher đầu vào. Ở đây outgoing là Flux nên requester gửi nhiều payload.
- retrieveFlux() khai báo response là một stream ServerEvent.

Tổ hợp nhiều request payload và response stream tạo request-channel. Requester không cần gọi một API tên requestChannel riêng; Spring suy ra interaction model từ cardinality của data publisher và kiểu response được yêu cầu.

Ví dụ dùng Flux.just có nguồn dữ liệu hữu hạn. Client gửi ba command rồi hoàn tất đầu vào. Server xử lý chúng và phát các ServerEvent. Đây là ví dụ dễ kiểm thử, nhưng trong ứng dụng tương tác lâu dài, đầu vào thường là một publisher có thể phát thêm dữ liệu trong khi response đang được tiêu thụ.

## 6. Trao đổi liên tục với publisher sống

Để gửi dữ liệu theo thời gian thực, client có thể dùng Reactor Sinks làm nguồn command. Ví dụ dùng unicast sink với hàng đợi giới hạn:

~~~java
import java.util.concurrent.ArrayBlockingQueue;

import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.Disposable;
import reactor.core.publisher.Sinks;

Sinks.Many<ClientCommand> outgoing = Sinks.many()
        .unicast()
        .onBackpressureBuffer(new ArrayBlockingQueue<>(128));

Disposable channelSubscription = requester
        .route("chat.channel")
        .data(outgoing.asFlux(), ClientCommand.class)
        .retrieveFlux(ServerEvent.class)
        .subscribe(
                event -> System.out.println("Server: " + event.message()),
                error -> System.err.println("Channel failed: " + error.getMessage()),
                () -> System.out.println("Channel completed")
        );

// Gửi nhiều command trong khi response stream đang được subscribe.
Sinks.EmitResult first = outgoing.tryEmitNext(new ClientCommand("start"));
Sinks.EmitResult second = outgoing.tryEmitNext(new ClientCommand("move"));
Sinks.EmitResult third = outgoing.tryEmitNext(new ClientCommand("stop"));

// Kiểm tra EmitResult trong ứng dụng thật để xử lý trường hợp queue đầy
// hoặc sink đã kết thúc.
if (first.isFailure() || second.isFailure() || third.isFailure()) {
    System.err.println("Could not enqueue every command");
}

// Khi không gửi thêm request payload:
outgoing.tryEmitComplete();
~~~

Đây là ví dụ minh họa phần publisher hai chiều. Kiểu ClientCommand và ServerEvent dùng chung với ví dụ controller ở trên. Trong một service thực tế, requester thường được tạo và quản lý bởi Spring configuration hoặc dependency injection; cần quản lý vòng đời kết nối và Disposable theo vòng đời phiên làm việc.

Một số điểm cần lưu ý:

- Đăng ký subscriber vào response Flux trước khi phát các command nếu cần nhận phản hồi ngay.
- Sink unicast chỉ cho phép một subscriber; điều này phù hợp với một request-channel tiêu thụ publisher đó.
- Hàng đợi giới hạn tránh giữ vô hạn dữ liệu khi producer nhanh hơn consumer.
- Luôn kiểm tra EmitResult. Khi queue đầy, sink đã bị hủy hoặc đã hoàn tất, việc phát thêm có thể thất bại.
- Khi cần kết thúc bình thường, gọi tryEmitComplete() để đóng luồng request đầu vào và chờ response stream hoàn tất.
- Khi hủy Disposable, requester hủy subscription của response; việc hủy được truyền thành CANCEL cho request đang hoạt động.

Không nên dùng một hàng đợi vô hạn cho nguồn dữ liệu nóng có thể phát nhanh hơn tốc độ xử lý của remote peer. Một queue giới hạn buộc ứng dụng phải quyết định rõ cách xử lý overflow: từ chối dữ liệu mới, retry có kiểm soát, giảm tốc độ producer hoặc ghi dữ liệu vào một hệ thống lưu trữ phù hợp.

## 7. Backpressure giữa hai phía

Backpressure là điểm quan trọng của request-channel. RSocket mang Reactive Streams semantics qua ranh giới mạng. Bên nhận thông báo demand bằng số lượng message mà nó sẵn sàng nhận. Khi cần thêm dữ liệu, nó gửi REQUEST_N. Publisher phía gửi phải tôn trọng demand này.

Với Spring và Reactor:

- Flux/Mono biểu diễn nguồn dữ liệu và tín hiệu reactive.
- Subscriber tạo demand khi yêu cầu phần tử.
- Reactor và RSocket truyền demand qua giao thức, không cần ứng dụng tự tạo REQUEST_N frame.
- Khi consumer chậm, nguồn dữ liệu có thể được yêu cầu phát chậm lại nếu nguồn hỗ trợ backpressure.
- Một nguồn hot hoặc không thể điều tiết vẫn có thể cần buffer hoặc chính sách overflow ở tầng ứng dụng.

Request-channel có hai hướng dữ liệu. Mỗi hướng có vòng đời và demand riêng. Requester tiêu thụ response stream bằng subscriber; responder tiêu thụ request stream bằng handler. Phía nào xử lý chậm thì demand ở hướng tương ứng sẽ điều tiết tốc độ phát của phía còn lại.

Backpressure không phải rate limit theo user, không phải cơ chế lưu message bền vững và không thay thế giới hạn kích thước payload. Hệ thống vẫn cần giới hạn tốc độ nghiệp vụ, kích thước message, số channel đồng thời và bộ nhớ dành cho buffer.

### Ví dụ điều tiết nguồn

Với nguồn hữu hạn hoặc có thể điều tiết, các toán tử Reactor cho phép kiểm soát tốc độ và số phần tử:

~~~java
Flux<ClientCommand> outgoing = commandSource
        .onBackpressureBuffer(128)
        .limitRate(32);
~~~

limitRate điều tiết số lượng phần tử được yêu cầu từ upstream theo từng nhóm demand. onBackpressureBuffer ở đây có giới hạn 128 phần tử; ứng dụng cần xác định hành vi khi buffer đầy và không nên xem buffer là giải pháp thay thế cho việc điều tiết producer.

## 8. Hoàn tất, hủy và lỗi

Một request-channel có hai luồng payload. Cần phân biệt việc một phía ngừng gửi dữ liệu với việc toàn bộ request đã kết thúc:

- Khi publisher đầu vào hoàn tất, requester không gửi thêm request payload. Responder vẫn có thể hoàn thành hoặc phát nốt response đã tạo.
- Khi response publisher của responder hoàn tất, requester nhận tín hiệu complete và response Flux kết thúc.
- Khi requester hủy response subscription, RSocket gửi CANCEL cho request đang hoạt động; responder nên giải phóng tài nguyên liên quan.
- Khi một phía phát lỗi, request kết thúc theo lỗi giao thức; phía còn lại nhận lỗi và cần dọn dẹp tài nguyên.
- Khi kết nối RSocket bị đóng, các request đang hoạt động trên kết nối có thể bị lỗi hoặc hủy tùy tình huống và cấu hình resumption.

Có thể gắn doFinally để quan sát vòng đời và giải phóng tài nguyên:

~~~java
@MessageMapping("telemetry.channel")
public Flux<TelemetryReply> telemetry(Flux<TelemetrySample> samples) {
    return samples
            .map(this::process)
            .doFinally(signal -> releaseChannelResources());
}
~~~

Trong ví dụ, process và releaseChannelResources đại diện cho logic ứng dụng. doFinally chạy khi luồng hoàn tất, lỗi hoặc bị hủy. Việc giải phóng tài nguyên phải idempotent và an toàn khi có nhiều đường kết thúc.

Không nuốt lỗi bằng cách thay mọi lỗi thành một response thành công giả. Hãy phân biệt lỗi nghiệp vụ có thể biểu diễn thành payload với lỗi giao thức hoặc lỗi hệ thống cần kết thúc request.

## 9. Phân biệt request-channel với các interaction model khác

| Nhu cầu | Chọn | Lý do |
|---|---|---|
| Gửi một lệnh và nhận một kết quả | Request-Response | Cardinality một-một. |
| Gửi một tiêu chí và nhận nhiều kết quả | Request-Stream | Đầu vào đơn, đầu ra nhiều. |
| Gửi nhiều lệnh và nhận nhiều phản hồi khi đang gửi | Request-Channel | Nhiều payload ở cả hai hướng. |
| Gửi một sự kiện không cần response | Fire-and-Forget | Một chiều, không có response payload. |
| Gửi notification độc lập không thuộc request cụ thể | Metadata Push | Dùng frame METADATA_PUSH ở cấp connection. |

Request-channel khác Request-Stream ở chỗ requester cũng có thể gửi nhiều payload sau frame khởi tạo. Nó khác Metadata Push vì channel gắn với một request có vòng đời riêng, còn metadata push là thông báo metadata ở cấp kết nối.

Nếu client chỉ gửi một object và server trả về Flux, hãy dùng Request-Stream. Không cần request-channel chỉ vì response có nhiều phần tử. Nếu client cần tiếp tục gửi thêm dữ liệu trong lúc nhận response, request-channel mới là lựa chọn phù hợp.

## 10. Cấu hình responder và serialization

Trong ứng dụng Spring Framework thuần, RSocketMessageHandler phát hiện các bean @Controller có @MessageMapping và tạo responder. Ứng dụng cần kết nối responder đó với RSocketServer. Trong Spring Boot, auto-configuration có thể tạo RSocketMessageHandler và cấu hình requester builder.

Một cấu hình handler tối giản trong Spring Framework:

~~~java
@Configuration
public class RSocketServerConfig {

    @Bean
    public RSocketMessageHandler rsocketMessageHandler() {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRouteMatcher(new PathPatternRouteMatcher());
        return handler;
    }
}
~~~

Đoạn này chỉ tạo message handler; server transport vẫn phải được bind với responder do handler.responder() cung cấp. PathPatternRouteMatcher dùng route separator mặc định là dấu chấm cho RSocket route; route RSocket là metadata, không phải URL HTTP. Ví dụ chat.channel là một route phân cấp.

RSocketRequester và RSocketMessageHandler dùng RSocketStrategies để mã hóa và giải mã data cùng metadata. Các codec cơ bản của spring-core hỗ trợ String, byte[] và ByteBuffer. Để truyền DTO/record dưới dạng JSON hoặc CBOR, cần encoder/decoder tương ứng; các codec Jackson thường đến từ spring-web và có thể được cấu hình trong RSocketStrategies. Spring Boot starter RSocket cung cấp cấu hình codec tự động theo dependency có mặt.

Hai phía phải thống nhất MIME type và cấu trúc payload. Nếu server mong đợi ClientCommand nhưng client gửi JSON có schema khác, lỗi decode có thể xảy ra trước khi handler xử lý. Khi thay đổi schema, hãy cân nhắc tương thích ngược và phiên bản hóa message.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Handler không được gọi | Route client không khớp @MessageMapping | So sánh chính xác route metadata, kể cả dấu chấm và tên route. |
| Spring không nhận đây là channel | Đầu vào handler không phải Flux hoặc publisher nhiều phần tử | Dùng Flux<T> làm payload đầu vào khi cần nhiều request payload. |
| Chỉ nhận được response một lần | Client dùng retrieveMono hoặc handler chỉ trả về một giá trị | Dùng retrieveFlux và trả Flux nếu cần response stream. |
| Request gửi được nhưng không có response | Handler trả về Flux rỗng, filter loại mọi phần tử hoặc lỗi xảy ra trước khi emit | Kiểm tra publisher đầu vào, toán tử reactive và log lỗi đã làm sạch. |
| Producer nhanh làm tăng bộ nhớ | Nguồn hot phát nhanh hơn consumer và buffer không giới hạn | Dùng backpressure-aware source, queue giới hạn và chính sách overflow. |
| Channel không kết thúc | Publisher đầu vào không complete hoặc response publisher không complete | Kiểm tra vòng đời cả hai Flux và điều kiện hoàn tất. |
| Không giải phóng tài nguyên khi client rời đi | Không xử lý cancellation | Dùng doFinally và cleanup an toàn cho COMPLETE, ERROR, CANCEL. |
| Không decode được DTO | Codec, MIME type hoặc schema không tương thích | Kiểm tra RSocketStrategies, encoder/decoder và MIME type. |
| Server phản hồi sai thứ tự | Dùng flatMap với tác vụ hoàn thành không theo thứ tự | Dùng concatMap nếu nghiệp vụ yêu cầu giữ thứ tự. |

## 12. Checklist thiết kế request-channel

1. Cả hai phía có thực sự cần gửi nhiều payload trong cùng một request không?
2. Handler có dùng Flux cho input stream và kiểu trả về phù hợp với response stream không?
3. Client có dùng data(Publisher, elementClass) và retrieveFlux đúng kiểu không?
4. Nguồn dữ liệu có hỗ trợ backpressure hay cần buffer giới hạn?
5. Có giới hạn số phần tử, tốc độ, kích thước payload và số channel đồng thời không?
6. Khi đầu vào complete, response có thể hoàn tất theo quy tắc nghiệp vụ không?
7. Khi client cancel hoặc connection lỗi, tài nguyên có được giải phóng không?
8. Hai phía có cùng codec, MIME type và schema không?
9. Route có ổn định và được phân quyền phù hợp không?
10. Có kiểm thử trường hợp producer nhanh, consumer chậm, lỗi giữa luồng và hủy giữa chừng không?

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, RSocketRequester, @MessageMapping, cardinality của Flux/Mono và annotated responders.
- [RSocket Protocol — REQUEST_CHANNEL](https://rsocket.io/about/protocol/): REQUEST_CHANNEL, PAYLOAD, REQUEST_N, COMPLETE, CANCEL và flow control.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): auto-configuration cho RSocketMessageHandler, RSocketStrategies và RSocketRequester.Builder.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): Flux, Sinks, backpressure, cancellation và xử lý lỗi.

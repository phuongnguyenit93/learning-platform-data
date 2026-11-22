# Thực nghiệm request-channel, backpressure và cancellation

Trong RSocket, **Request-Channel** là interaction model cho phép requester gửi một luồng message đến responder, đồng thời responder gửi một luồng message ngược lại. Hai chiều hoạt động trên cùng một request stream và có thể phát dữ liệu độc lập. Đây là lựa chọn phù hợp cho những trao đổi liên tục hai chiều như đồng bộ trạng thái, cộng tác thời gian thực, điều khiển thiết bị hoặc xử lý một chuỗi command có phản hồi tương ứng.

Khi thực nghiệm Request-Channel, cần quan sát ba hành vi:

- **Request-Channel:** hai phía đều có thể gửi nhiều payload trên cùng một request.
- **Backpressure:** mỗi phía điều khiển tốc độ nhận dữ liệu của mình bằng demand; phía gửi phải tôn trọng demand đó.
- **Cancellation:** khi subscriber hủy channel, việc truyền và xử lý dữ liệu liên quan phải kết thúc theo vòng đời của request.

Một test tốt phải chứng minh được dữ liệu đi theo cả hai chiều, demand thực sự điều tiết việc phát và cancellation được truyền tới publisher nguồn. Chỉ kiểm tra rằng một Flux phát ra vài phần tử không đủ để chứng minh hành vi của RSocket channel qua mạng.

## 1. Request-Channel là gì?

RSocket có bốn interaction model chính:

| Interaction model | Requester gửi | Responder trả về | Tình huống phù hợp |
|---|---|---|---|
| Request-Response | Một message | Một message | Tra cứu hoặc cập nhật có một kết quả |
| Request-Stream | Một message | Một stream | Gửi tham số rồi nhận nhiều kết quả |
| Fire-and-Forget | Một message | Không có response payload | Gửi một thông báo không cần kết quả |
| Request-Channel | Một stream | Một stream | Trao đổi dữ liệu liên tục theo cả hai chiều |

Request-Channel không đơn giản là hai request độc lập chạy song song. Hai luồng payload thuộc cùng một interaction, chia sẻ vòng đời và có thể được điều tiết bằng flow control của RSocket.

Ví dụ, client gửi các lệnh theo dõi thiết bị và server gửi trạng thái xử lý:

- Client → Server: SubscribeDevice, ChangeSamplingRate, StopDevice.
- Server → Client: DeviceReady, SampleReceived, DeviceWarning.

Client có thể tiếp tục gửi lệnh trong khi server vẫn đang phát các trạng thái hoặc kết quả trước đó. Hai chiều không cần phát cùng số lượng phần tử và cũng không cần hoàn tất cùng thời điểm.

### Phân biệt với MessageChannel của Spring

Tên gọi dễ gây nhầm lẫn:

- **RSocket Request-Channel** là interaction model hai chiều của protocol.
- **Spring MessageChannel** là abstraction để gửi một Spring Message đến channel.
- **Spring Integration request channel** thường là channel dùng để chuyển request đến một handler trong integration flow.

Các khái niệm này có thể được dùng cùng nhau trong một hệ thống, nhưng không đồng nghĩa. Một RSocket Request-Channel không tự động là một Spring Integration channel và một MessageChannel không tự tạo ra giao thức hai chiều.

## 2. Request-Channel được biểu diễn bằng Flux như thế nào?

Trong Spring Framework, một annotated responder có thể nhận một Flux đầu vào và trả về một Flux đầu ra:

~~~java
@Controller
class DeviceChannelController {

    private final DeviceService deviceService;

    DeviceChannelController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @MessageMapping("devices.control")
    Flux<DeviceReply> control(Flux<DeviceCommand> commands) {
        return commands.concatMap(
            command -> deviceService.handle(command)
                .map(result -> new DeviceReply(
                    command.commandId(),
                    result.status()
                )),
            1
        );
    }
}
~~~

Trong ví dụ:

- Tham số Flux<DeviceCommand> là stream command từ requester đến responder.
- Giá trị trả về Flux<DeviceReply> là stream response từ responder về requester.
- Route devices.control xác định handler.
- concatMap xử lý từng command theo thứ tự và giới hạn prefetch ở mức một phần tử trong pipeline này.

Đây là hình thức tự nhiên để triển khai Request-Channel với Spring annotated responder. Phía requester gửi một Publisher nhiều phần tử và yêu cầu một Flux response.

Requester có thể gọi như sau:

~~~java
Flux<DeviceCommand> outbound = Flux.just(
    new DeviceCommand("cmd-1", "START"),
    new DeviceCommand("cmd-2", "SET_RATE"),
    new DeviceCommand("cmd-3", "STOP")
);

Flux<DeviceReply> inbound = requester
    .route("devices.control")
    .data(outbound, DeviceCommand.class)
    .retrieveFlux(DeviceReply.class);
~~~

Việc truyền một Publisher nhiều phần tử vào data và nhận một Flux bằng retrieveFlux tạo ra interaction hai chiều. Dùng overload có element class giúp Spring biết kiểu của từng phần tử trong stream để chọn encoder phù hợp.

### Ví dụ DTO

~~~java
record DeviceCommand(
    String commandId,
    String action
) {}

record DeviceReply(
    String commandId,
    String status
) {}

record DeviceResult(String status) {}
~~~

Các DTO này chỉ minh họa payload của bài thực hành. Trong ứng dụng thật, cần xác định schema, validation, correlation ID, xử lý command trùng và quy tắc lỗi riêng.

## 3. Hai chiều có vòng đời độc lập

Request-Channel có hai chiều stream:

1. Requester → Responder: requester phát command hoặc dữ liệu đầu vào.
2. Responder → Requester: responder phát response, acknowledgement hoặc event.

Mỗi chiều có thể hoàn tất độc lập. Ví dụ client đã gửi xong toàn bộ command nhưng server vẫn cần phát các kết quả đang xử lý. Khi Publisher đầu vào của client complete, điều đó chỉ biểu thị client không gửi thêm payload; không có nghĩa response stream phải complete ngay lập tức.

Tương tự, responder có thể hoàn tất stream phản hồi trong khi phía requester vẫn đang gửi dữ liệu, tùy theo hợp đồng và logic xử lý. Channel chỉ hoàn tất bình thường khi cả hai phía hoàn tất phần gửi của mình.

Cần phân biệt ba tín hiệu:

- **Complete:** một phía đã gửi xong dữ liệu theo chiều của mình.
- **Error:** một lỗi kết thúc interaction theo semantics của protocol.
- **Cancel:** requester hoặc responder hủy request đang hoạt động; channel bị kết thúc.

Không dùng việc outbound Flux complete để suy luận rằng toàn bộ channel đã kết thúc. Nếu cần biết toàn bộ trao đổi đã hoàn tất, hãy quan sát completion của response Flux.

## 4. Thử nghiệm một channel hai chiều hoàn chỉnh

Một bài thực hành cơ bản nên có một server handler và một requester thật. Server nhận command rồi trả acknowledgement tương ứng.

Handler:

~~~java
@Controller
class EchoChannelController {

    @MessageMapping("lab.echo")
    Flux<EchoReply> echo(Flux<EchoCommand> commands) {
        return commands
            .map(command -> new EchoReply(
                command.sequence(),
                "ACK-" + command.value()
            ));
    }
}

record EchoCommand(long sequence, String value) {}

record EchoReply(long sequence, String result) {}
~~~

Requester:

~~~java
Flux<EchoCommand> commands = Flux.just(
    new EchoCommand(1, "alpha"),
    new EchoCommand(2, "beta"),
    new EchoCommand(3, "gamma")
);

Flux<EchoReply> replies = requester
    .route("lab.echo")
    .data(commands, EchoCommand.class)
    .retrieveFlux(EchoReply.class);
~~~

Có thể kiểm tra kết quả bằng StepVerifier:

~~~java
StepVerifier.create(replies)
    .assertNext(reply -> {
        assertEquals(1, reply.sequence());
        assertEquals("ACK-alpha", reply.result());
    })
    .assertNext(reply -> {
        assertEquals(2, reply.sequence());
        assertEquals("ACK-beta", reply.result());
    })
    .assertNext(reply -> {
        assertEquals(3, reply.sequence());
        assertEquals("ACK-gamma", reply.result());
    })
    .verifyComplete();
~~~

Test này cần chạy trong một integration test có RSocket server thực sự được khởi động và requester kết nối tới server. Nếu chỉ gọi trực tiếp method echo bằng Flux cục bộ, test mới xác nhận logic biến đổi dữ liệu, chưa xác nhận route, encoding, channel interaction hoặc protocol flow control.

Trong test tích hợp, hãy dùng port động hoặc transport test được cấu hình riêng, khởi động server trước khi tạo requester và dispose cả server lẫn connection sau test. Không dùng một port cố định có thể bị một test khác chiếm.

## 5. Backpressure hoạt động ở cả hai chiều

Reactive Streams dùng demand để điều tiết số phần tử subscriber muốn nhận. Trong RSocket, flow control được truyền qua protocol bằng các frame REQUEST_N.

Đối với Request-Channel, mỗi phía có thể phát REQUEST_N để cấp credit cho phía bên kia. Vì vậy:

- Demand của requester điều tiết số response mà responder được phép phát.
- Demand của responder điều tiết số request payload mà requester được phép gửi tiếp.
- Hai chiều có thể có demand khác nhau.
- Credit đã cấp được cộng dồn; phía phát không được gửi vượt lượng credit đang có.

Ví dụ, requester chỉ cấp demand cho một response tại một thời điểm. Responder phải tôn trọng giới hạn đó trước khi gửi response tiếp theo. Ở chiều ngược lại, nếu responder chỉ yêu cầu một command mỗi lần, requester không được đẩy một lượng command tùy ý vào stream.

Backpressure là flow control theo từng stream. Nó không thay thế giới hạn tổng số channel hoặc tổng số request mà server chấp nhận. Một client vẫn có thể mở nhiều channel, vì vậy server cần thêm admission control và giới hạn concurrency ở cấp ứng dụng.

### Thử nghiệm demand bằng StepVerifier

Có thể bắt đầu với demand nhỏ rồi tăng dần:

~~~java
StepVerifier.create(replies, 1)
    .expectNextMatches(reply -> reply.sequence() == 1)
    .thenRequest(1)
    .expectNextMatches(reply -> reply.sequence() == 2)
    .thenRequest(1)
    .expectNextMatches(reply -> reply.sequence() == 3)
    .verifyComplete();
~~~

Test này cho subscriber ban đầu một credit response, sau đó yêu cầu thêm từng phần tử. Nó kiểm tra cách consumer điều khiển response stream.

Lưu ý: initial request N trong RSocket protocol phải là số dương. Hãy dùng một demand ban đầu hợp lệ như một phần tử khi kiểm thử channel qua transport thật; đừng giả định demand bằng 0 trong StepVerifier luôn được ánh xạ trực tiếp thành một REQUEST_CHANNEL frame hợp lệ.

## 6. Điều tiết luồng command ở phía requester

Nếu nguồn command là một Flux có khả năng tuân thủ demand, RSocket có thể điều tiết việc yêu cầu phần tử từ nguồn đó. Có thể thêm các operator để giới hạn tốc độ yêu cầu hoặc số phần tử được giữ ở từng bước.

Ví dụ:

~~~java
Flux<DeviceCommand> outbound = commandSource
    .limitRate(4)
    .doOnRequest(n -> metrics.recordCommandDemand(n))
    .doOnCancel(() -> metrics.recordCommandStreamCancelled());
~~~

limitRate chia các request demand lớn thành các đợt nhỏ hơn theo cấu hình. Nó không đặt giới hạn toàn cục số channel và không phải rate limiter theo giây.

Nếu command được tạo từ một nguồn hot không thể tạm dừng, cần một chính sách hữu hạn để xử lý chênh lệch tốc độ:

~~~java
Flux<DeviceCommand> outbound = hotCommandSource
    .onBackpressureBuffer(
        128,
        dropped -> metrics.incrementCommandOverflow(),
        BufferOverflowStrategy.ERROR
    );
~~~

Buffer 128 phần tử ở đây là ví dụ cho một giới hạn cục bộ. Khi đầy, publisher phát lỗi thay vì tiếp tục giữ dữ liệu không giới hạn. Chỉ dùng buffer nếu nghiệp vụ cho phép chờ; với command quan trọng, cần xác định cơ chế lưu bền vững hoặc trả lỗi để producer thử lại an toàn.

Không thêm buffer lớn theo thói quen. Nếu nguồn đã tuân thủ backpressure, để demand truyền ngược thường đơn giản và ít tốn bộ nhớ hơn.

## 7. Điều tiết xử lý ở phía responder

Responder cũng cần quyết định tốc độ tiêu thụ command. Ví dụ dùng concatMap với prefetch nhỏ để xử lý tuần tự:

~~~java
@MessageMapping("devices.commands")
Flux<CommandAck> commands(Flux<DeviceCommand> inbound) {
    return inbound
        .concatMap(
            command -> deviceService.process(command)
                .map(result -> new CommandAck(
                    command.commandId(),
                    result.status()
                )),
            1
        );
}
~~~

concatMap bảo đảm xử lý theo thứ tự đầu vào và chỉ chạy một inner publisher tại một thời điểm trong pipeline này. Điều này phù hợp khi các command phụ thuộc thứ tự, chẳng hạn START phải xảy ra trước STOP.

Nếu các command độc lập và downstream chịu được nhiều operation đồng thời, có thể dùng flatMap với giới hạn:

~~~java
return inbound.flatMap(
    command -> deviceService.process(command)
        .map(result -> new CommandAck(
            command.commandId(),
            result.status()
        )),
    8,
    1
);
~~~

Giới hạn 8 áp dụng cho subscription này. Với nhiều channel cùng lúc, tổng tải có thể lớn hơn nhiều. Nếu cần bảo vệ database hoặc dịch vụ bên ngoài ở cấp toàn ứng dụng, hãy dùng bulkhead hoặc admission control dùng chung.

Nếu thứ tự response phải khớp thứ tự command trong khi vẫn xử lý đồng thời, cân nhắc flatMapSequential. Operator này giữ thứ tự phát kết quả nhưng có thể phải buffer kết quả của operation hoàn tất sớm hơn.

## 8. Cancellation là gì?

Cancellation xảy ra khi subscriber không còn muốn nhận hoặc tiếp tục một interaction. Với RSocket, requester có thể gửi frame CANCEL cho request stream đang hoạt động. Responder nhận cancellation phải kết thúc stream tương ứng.

Trong Spring/Reactor, cancellation được biểu diễn bằng tín hiệu cancel của Subscription. Khi pipeline được kết nối đúng cách, tín hiệu này có thể truyền ngược qua các operator đến publisher nguồn.

Ví dụ ghi nhận cancellation phía responder:

~~~java
@MessageMapping("lab.cancel")
Flux<Progress> progress(Flux<WorkCommand> commands) {
    return commands
        .concatMap(workService::run)
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                metrics.incrementChannelCancellation();
            }
        });
}
~~~

doFinally chạy khi pipeline kết thúc bằng complete, error hoặc cancel. Chỉ tăng metric cancellation khi signal là CANCEL; không coi mọi kết thúc là hủy.

Cancellation đặc biệt quan trọng khi handler đang:

- Đọc dữ liệu từ database hoặc một stream bên ngoài.
- Theo dõi trạng thái thiết bị.
- Chạy một tác vụ dài.
- Giữ subscription đến hot publisher.
- Chờ một dịch vụ downstream.
- Tiêu thụ tài nguyên có thể giải phóng khi không còn subscriber.

Không nên chỉ dừng phát response mà vẫn để nguồn tiếp tục làm việc vô ích. Hãy kiểm tra publisher nguồn có hỗ trợ cancellation và giải phóng tài nguyên trong finally hoặc doFinally phù hợp.

## 9. Hủy channel từ requester

Có thể dùng operator take để dừng sau một số response nhất định:

~~~java
Flux<Progress> firstTwo = requester
    .route("lab.cancel")
    .data(workCommands, WorkCommand.class)
    .retrieveFlux(Progress.class)
    .take(2);
~~~

take(2) hoàn tất downstream sau hai phần tử và hủy subscription upstream. Với RSocket channel, cancellation kết thúc interaction đang hoạt động. Nó không chỉ có nghĩa “tạm dừng nhận response”; request channel đã bị hủy.

Test:

~~~java
StepVerifier.create(firstTwo)
    .expectNextCount(2)
    .verifyComplete();
~~~

Để xác nhận cancellation thực sự tới server, không chỉ kiểm tra downstream hoàn tất. Hãy đặt probe phía responder, chẳng hạn CountDownLatch hoặc Sinks.One, được kích hoạt khi publisher nhận SignalType.CANCEL; sau đó test chờ probe với deadline.

~~~java
assertTrue(
    serverCancellation.await(5, TimeUnit.SECONDS),
    "Responder did not observe channel cancellation"
);
~~~

Chờ theo sự kiện có deadline giúp test xác định được việc cancellation đã truyền tới responder. Không dùng Thread.sleep để đoán thời điểm server nhận CANCEL.

## 10. Hoàn tất một chiều khác với hủy toàn channel

Đây là điểm quan trọng khi thiết kế protocol ứng dụng:

- Khi outbound Publisher của requester complete, requester đã gửi xong command. Server vẫn có thể tiếp tục phát các response còn lại.
- Khi response Flux của requester complete, responder đã gửi xong response. Điều đó không tự động có nghĩa mọi command phía requester đã được gửi xong.
- Khi requester cancel response subscription, channel bị hủy; đây là kết thúc interaction chứ không phải chỉ đóng một nửa luồng.
- Khi một phía phát error, interaction kết thúc theo semantics lỗi của RSocket.

Ví dụ client có thể gửi xong một batch command nhưng vẫn đợi server tổng hợp kết quả cuối cùng. Khi đó, hãy complete outbound source một cách bình thường và tiếp tục subscribe response Flux cho tới khi complete.

Không dùng take(0), cancel hoặc dispose để biểu thị “tôi không còn command mới” nếu vẫn cần nhận kết quả. Hãy complete Publisher gửi đi; chỉ cancel khi muốn dừng toàn bộ interaction.

## 11. Kiểm thử cancellation với nguồn có thể quan sát

Một publisher test có thể ghi nhận cancellation bằng AtomicBoolean:

~~~java
AtomicBoolean sourceCancelled = new AtomicBoolean();

Flux<WorkCommand> commands = Flux
    .<WorkCommand>never()
    .doOnCancel(() -> sourceCancelled.set(true));

Flux<Progress> progress = requester
    .route("work.long-running")
    .data(commands, WorkCommand.class)
    .retrieveFlux(Progress.class)
    .take(1);
~~~

Khi response đầu tiên đến và take(1) hủy upstream, có thể kiểm tra sourceCancelled. Tuy nhiên, với Request-Channel thật, cần xác định publisher nào đang bị hủy và probe ở đúng phía. Việc hủy response subscription không nên được suy luận từ một test Flux cục bộ không đi qua transport.

Một integration test có thể:

1. Mở channel tới server.
2. Gửi command bắt đầu một công việc dài.
3. Nhận một progress response.
4. Hủy subscription từ requester.
5. Chờ probe phía responder báo cancellation.
6. Xác nhận service dừng công việc hoặc giải phóng subscription/tài nguyên.
7. Xác nhận không còn response mới được phát cho channel đã hủy.

Nếu tác vụ bên dưới không hỗ trợ hủy, cancellation của Reactor không thể tự động dừng một thread hoặc lời gọi blocking đang chạy. Khi đó cần timeout ở client, interrupt/cancel API nếu thư viện hỗ trợ và quản lý tài nguyên ở cấp tác vụ.

## 12. Kiểm thử lỗi và race giữa hai chiều

Hai chiều của channel có thể phát dữ liệu đồng thời, vì vậy test cần xem xét các tình huống cạnh tranh:

- Client phát command cuối cùng trong lúc server đang gửi response.
- Client complete outbound stream trong khi server còn response đang chờ.
- Server phát lỗi khi client vẫn còn command chưa gửi.
- Client cancel trong lúc server đang xử lý một command.
- Network connection bị đóng khi cả hai phía đang có demand.
- Response đến muộn sau khi phía client đã hủy interaction.

Không nên giả định một thứ tự toàn cục giữa hai chiều. RSocket đảm bảo semantics của từng stream và flow control, nhưng ứng dụng cần correlation ID hoặc sequence number để ghép response với command tương ứng.

Ví dụ response có thể mang commandId:

~~~java
record WorkCommand(String commandId, String operation) {}

record WorkReply(
    String commandId,
    String status,
    long sequence
) {}
~~~

Khi response có thể đến không theo thứ tự vì server xử lý song song, client nên ghép theo commandId thay vì dựa vào vị trí phần tử trong Flux.

Khi cần thứ tự tuyệt đối, dùng xử lý tuần tự ở responder hoặc thêm sequence number và quy tắc reorder rõ ràng.

## 13. Phân biệt kiểm thử đơn vị và kiểm thử transport

Một số hành vi có thể kiểm tra bằng publisher cục bộ; một số cần RSocket thật.

| Mục tiêu | Kiểu test phù hợp | Điều test chứng minh |
|---|---|---|
| Mapping command sang reply | Unit test | Logic ứng dụng đúng |
| concatMap xử lý tuần tự | Unit test với StepVerifier | Thứ tự và số operation đồng thời |
| flatMap concurrency | Unit test với bộ đếm active | Giới hạn trong một subscription |
| Backpressure của Flux cục bộ | StepVerifier/TestPublisher | Publisher tôn trọng demand |
| Route được ánh xạ đúng | RSocket integration test | Spring responder nhận đúng route |
| Request-Channel hai chiều | RSocket integration test | Requester và responder trao đổi hai stream qua transport |
| REQUEST_N truyền qua mạng | Integration test có probe | Flow control giữa hai phía |
| CANCEL truyền tới responder | Integration test có cancellation probe | Vòng đời request kết thúc ở phía server |
| Mất kết nối giữa channel | Transport integration test | Error/reconnect/resume theo cấu hình thực tế |

Virtual time hữu ích cho các operator Reactor có sử dụng scheduler được thay thế. Nó không tự điều khiển timer của TCP, Reactor Netty hoặc broker thật. Với integration test transport, dùng thời gian thật nhưng chờ tín hiệu có deadline.

## 14. Một kịch bản thực nghiệm đầy đủ

Có thể xây dựng bài lab với route devices.session:

**Responder:**

~~~java
@Controller
class DeviceSessionController {

    @MessageMapping("devices.session")
    Flux<SessionReply> session(Flux<SessionCommand> commands) {
        return commands
            .limitRate(2)
            .concatMap(command ->
                deviceService.execute(command)
                    .map(result -> new SessionReply(
                        command.id(),
                        result.message()
                    )),
                1
            )
            .doFinally(signal -> {
                if (signal == SignalType.CANCEL) {
                    deviceMetrics.channelCancelled();
                }
            });
    }
}
~~~

**Requester:**

~~~java
Flux<SessionCommand> commands = Flux.just(
    new SessionCommand("1", "OPEN"),
    new SessionCommand("2", "SET_MODE"),
    new SessionCommand("3", "READ"),
    new SessionCommand("4", "CLOSE")
);

Flux<SessionReply> replies = requester
    .route("devices.session")
    .data(commands, SessionCommand.class)
    .retrieveFlux(SessionReply.class);
~~~

**Test:**

~~~java
StepVerifier.create(replies, 1)
    .assertNext(reply -> assertEquals("1", reply.commandId()))
    .thenRequest(1)
    .assertNext(reply -> assertEquals("2", reply.commandId()))
    .thenRequest(2)
    .assertNext(reply -> assertEquals("3", reply.commandId()))
    .assertNext(reply -> assertEquals("4", reply.commandId()))
    .verifyComplete();
~~~

Kịch bản này kiểm tra stream hai chiều ở mức application contract: client gửi nhiều command, server xử lý và trả nhiều reply, requester điều khiển demand của response. Khi chạy qua RSocket server thật, nó còn kiểm tra route, serialization và channel transport.

Để mở rộng lab:

1. Thay concatMap bằng flatMap có concurrency bằng hai; đo thứ tự response và số operation đồng thời.
2. Thêm delay bất đồng bộ vào service và điều khiển response demand bằng StepVerifier.
3. Dùng nguồn command dài hoặc không kết thúc để kiểm thử cancellation.
4. Hủy requester sau một progress response và chờ probe phía server.
5. Thử complete outbound source trước rồi xác nhận response stream vẫn được tiêu thụ đến completion.
6. Làm service phát lỗi ở command thứ hai và kiểm tra channel kết thúc theo chính sách lỗi.
7. Dùng nhiều requester đồng thời để kiểm tra giới hạn channel và tài nguyên toàn server.

## 15. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Dùng một object thay vì Publisher cho input | Tạo Request-Stream hoặc Request-Response thay vì Channel | Truyền Flux input và nhận Flux output |
| Nhầm Request-Channel với hai request độc lập | Mất vòng đời và flow control chung | Dùng một channel interaction |
| Nghĩ outbound complete là channel complete | Có thể bỏ lỡ response còn lại | Tiếp tục tiêu thụ response Flux |
| Dùng cancel để báo hết command | Hủy toàn bộ interaction | Complete outbound Publisher bình thường |
| Bỏ qua demand | Tạo buffer hoặc tải không kiểm soát | Dùng operator và nguồn tuân thủ backpressure |
| Cho rằng REQUEST_N giới hạn toàn server | Chỉ điều tiết demand của stream | Thêm admission control và giới hạn concurrency |
| Dùng flatMap không giới hạn | Downstream có thể bị quá tải | Đặt concurrency và prefetch rõ ràng |
| Dùng take(1) rồi mong channel tiếp tục | take hủy subscription upstream | Dùng completion hoặc giao thức stop riêng |
| Không có commandId/sequence | Khó ghép response khi xử lý song song | Thêm correlation ID hoặc sequence |
| Chỉ unit test Flux cục bộ | Không kiểm tra protocol, route hoặc cancellation qua mạng | Bổ sung integration test RSocket |
| Dùng Thread.sleep để chờ CANCEL | Test flaky và khó chẩn đoán | Dùng latch/probe với deadline |
| Giả định cancellation dừng blocking call | Tác vụ blocking có thể vẫn chạy | Dùng API có khả năng cancel và timeout nội bộ |

## 16. Checklist trước khi đưa channel vào production

- [ ] Đã xác định rõ dữ liệu đi theo cả hai chiều.
- [ ] Requester gửi Publisher nhiều phần tử và nhận Flux response.
- [ ] Responder nhận Flux input và trả Flux output.
- [ ] Route và kiểu phần tử được khai báo thống nhất.
- [ ] Có commandId/correlation ID để ghép request với response.
- [ ] Đã xác định có cần giữ thứ tự response hay cho phép xử lý song song.
- [ ] Concurrency và prefetch được giới hạn phù hợp.
- [ ] Backpressure được kiểm thử ở cả hai chiều.
- [ ] Nguồn hot có buffer hữu hạn và overflow policy.
- [ ] Complete một chiều được phân biệt với cancel toàn channel.
- [ ] Cancellation được kiểm thử ở requester và responder.
- [ ] Tác vụ downstream giải phóng tài nguyên khi bị cancel.
- [ ] Error handling không để channel tiếp tục trong trạng thái không xác định.
- [ ] Có integration test với RSocket transport thật.
- [ ] Có metric active channel, demand, cancellation, error và processing latency.
- [ ] Có giới hạn số channel đồng thời ở cấp ứng dụng.

## 17. Tài liệu tham khảo

- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — các interaction model, RSocketRequester, annotated responders và cách truyền Publisher.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — REQUEST_CHANNEL, REQUEST_N, CANCEL, COMPLETE và flow control hai chiều.
- [Project Reactor Reference: Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — StepVerifier, demand, cancellation và kiểm thử Publisher.
- [Project Reactor API: Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) — concatMap, flatMap, limitRate và các operator xử lý stream.

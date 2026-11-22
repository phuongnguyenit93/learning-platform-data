# Nhịp heartbeat để phát hiện kết nối không còn hoạt động trong Spring WebFlux

## 1. Heartbeat là gì?

Khi một endpoint trả về một luồng HTTP dài hạn, server có thể không gửi dữ liệu nghiệp vụ trong nhiều giây hoặc nhiều phút. Trong khoảng im lặng đó, client có thể đã đóng tab, mất mạng, chuyển mạng, tắt thiết bị hoặc bị proxy đóng kết nối. Nếu upstream chỉ phát event khi có thay đổi nghiệp vụ, server có thể không thực hiện lần ghi nào trong thời gian dài và việc phát hiện kết nối đã hỏng bị trì hoãn.

**Heartbeat** là một tín hiệu nhỏ được gửi định kỳ trong lúc stream đang hoạt động. Nó giúp:

- Tạo hoạt động ghi định kỳ trên kết nối.
- Giúp server nhận ra lần ghi thất bại khi client đã ngắt.
- Giúp proxy/load balancer thấy luồng vẫn có dữ liệu đi qua, tránh idle timeout ngoài ý muốn.
- Cho phép client theo dõi liveness nếu heartbeat được biểu diễn thành event mà client nhìn thấy.
- Tạo mốc quan sát để đo thời gian sống của stream và phát hiện kết nối bất thường.

Trong Spring WebFlux, heartbeat thường được tạo bằng Reactor **Flux.interval(...)** rồi ghép với publisher dữ liệu nghiệp vụ. Với Server-Sent Events (SSE), một comment-only event là lựa chọn tốt khi mục tiêu là giữ luồng hoạt động và phát hiện disconnect ở phía server mà không tạo message nghiệp vụ cho JavaScript client.

Heartbeat không phải bằng chứng tuyệt đối rằng ứng dụng phía client đã nhận và xử lý dữ liệu. Nó là tín hiệu liveness ở một tầng cụ thể của kết nối. Muốn xác nhận client đã nhận hoặc xử lý, cần cơ chế acknowledgement riêng.

## 2. Vì sao streaming cần heartbeat?

Một response streaming có thể tồn tại lâu hơn rất nhiều so với request/response thông thường:

~~~text
Client mở HTTP stream
       |
       v
Server gửi response headers
       |
       v
Stream được giữ mở
       |
       +---- không có dữ liệu nghiệp vụ trong 30 giây
       |
       +---- không có dữ liệu nghiệp vụ trong 2 phút
       |
       +---- client có thể đã rời mạng
       |
       v
Server chỉ biết có vấn đề khi lần ghi tiếp theo thất bại
~~~

Giả sử server chỉ gửi thông báo khi đơn hàng đổi trạng thái. Nếu đơn hàng không đổi trong 20 phút, publisher không phát item mới. Kết nối có thể vẫn tồn tại, nhưng server không có thao tác ghi nào để phát hiện client đã biến mất.

Spring Framework khuyến nghị gửi dữ liệu định kỳ khi stream response, ví dụ **text/event-stream** hoặc **application/x-ndjson**, để phát hiện client disconnect sớm hơn. Dữ liệu này có thể là comment-only SSE, empty SSE event hoặc một no-op record mà client biết cách bỏ qua.

Một heartbeat tạo thêm lần ghi trên response. Nếu kết nối đã đóng, thao tác ghi có thể thất bại. Lỗi hoặc cancellation sau đó được truyền ngược qua reactive chain để publisher và tài nguyên liên quan được dọn dẹp.

Điều này đặc biệt hữu ích khi upstream đang giữ một subscription tới Kafka, Redis Pub/Sub, message broker, database change feed hoặc nguồn event khác. Khi client rời đi, ứng dụng cần hủy subscription đó để không tiếp tục tiêu thụ tài nguyên cho một người nhận không còn tồn tại.

## 3. Phân biệt heartbeat ở các tầng

Không phải mọi cơ chế keep-alive đều có cùng mục tiêu.

| Cơ chế | Tầng | Tác dụng | Client JavaScript có thấy không? |
| --- | --- | --- | --- |
| SSE comment heartbeat | HTTP application payload | Tạo lần ghi định kỳ trong response SSE | Không phát message event |
| SSE named heartbeat event | HTTP application payload | Tạo dữ liệu heartbeat mà client có thể xử lý | Có, qua addEventListener |
| NDJSON heartbeat record | HTTP application payload | Gửi một JSON record no-op theo framing NDJSON | Có, client phải parse và bỏ qua |
| WebSocket Ping/Pong | WebSocket protocol | Kiểm tra peer phản hồi ở tầng WebSocket | Thường do WebSocket implementation xử lý |
| HTTP/2 PING | HTTP/2 connection protocol | Kiểm tra trạng thái connection bằng PING/ACK | Không phải message nghiệp vụ |
| TCP keepalive | TCP transport | Probe peer ở tầng TCP sau khoảng idle do hệ điều hành cấu hình | Không |

**SSE heartbeat và TCP keepalive không thay thế nhau.** TCP keepalive là probe ở tầng transport, thường có chu kỳ dài tùy hệ điều hành và có thể không được bật mặc định. Một reverse proxy cũng có thể áp dụng idle timeout ở tầng HTTP; TCP probe không nhất thiết được tính như một HTTP response payload mới.

HTTP/2 PING là cơ chế của connection HTTP/2. Reactor Netty có thể dùng PING/ACK để kiểm tra connection khi cấu hình idle timeout phù hợp. Nó không thay thế heartbeat ở tầng ứng dụng nếu client cần nhận tín hiệu nghiệp vụ hoặc proxy cần thấy response stream có dữ liệu.

Với SSE hoặc NDJSON qua HTTP, heartbeat payload là cách trực tiếp để tạo hoạt động ghi định kỳ trên chính response stream.

## 4. SSE comment-only heartbeat

SSE có cú pháp text đơn giản. Một event thông thường có thể gồm id, event, data và dòng trống kết thúc event:

~~~text
id: 42
event: order-update
data: {"orderId":"A-42","status":"SHIPPED"}

~~~

SSE cũng hỗ trợ comment, với dòng bắt đầu bằng dấu hai chấm:

~~~text
:keep-alive

~~~

Comment được gửi qua kết nối nhưng không tạo message event cho listener của EventSource. Đây là đặc điểm hữu ích của heartbeat comment: server có thể phát một lần ghi mà không làm client xử lý thêm một thông báo nghiệp vụ.

Spring cung cấp **ServerSentEvent<T>** và builder có method **comment(String)**:

~~~java
ServerSentEvent<String> heartbeat =
    ServerSentEvent.<String>builder()
        .comment("keep-alive")
        .build();
~~~

Để phát một chuỗi heartbeat định kỳ:

~~~java
Flux<ServerSentEvent<String>> heartbeats =
    Flux.interval(Duration.ofSeconds(15))
        .map(tick -> ServerSentEvent.<String>builder()
            .comment("keep-alive")
            .build());
~~~

**Flux.interval** phát tick đầu tiên sau khoảng thời gian đã cấu hình, rồi tiếp tục theo chu kỳ. Mỗi tick được chuyển thành một SSE comment.

Không cần đặt data hoặc id cho comment heartbeat. Đặc biệt, tránh tăng SSE event ID chỉ vì gửi heartbeat; Last-Event-ID nên đại diện cho event dữ liệu mà client có thể replay, không phải các lần keep-alive.

## 5. Heartbeat dạng event mà client nhìn thấy

Có lúc ứng dụng client cũng cần biết server còn gửi heartbeat. Khi đó dùng một SSE event có tên riêng và có data:

~~~java
ServerSentEvent<String> heartbeat =
    ServerSentEvent.<String>builder("alive")
        .event("heartbeat")
        .build();
~~~

Wire format có dạng:

~~~text
event: heartbeat
data: alive

~~~

JavaScript có thể lắng nghe:

~~~javascript
const source = new EventSource("/api/orders/A-42/events");
let lastHeartbeatAt = Date.now();

source.addEventListener("heartbeat", () => {
    lastHeartbeatAt = Date.now();
});

source.addEventListener("order-update", event => {
    const update = JSON.parse(event.data);
    renderOrder(update);
});

source.onerror = () => {
    console.log("SSE connection interrupted; EventSource may reconnect");
};
~~~

**EventSource** không phát message callback cho comment-only heartbeat. Nếu cần client watchdog, hãy dùng named heartbeat event hoặc một cơ chế khác mà client có thể quan sát.

Có thể chọn hai mục tiêu riêng:

- **Server-side disconnect detection:** comment-only heartbeat thường đủ.
- **Client-side liveness watchdog:** named heartbeat event giúp JavaScript cập nhật thời điểm heartbeat gần nhất.

SSE là giao thức một chiều từ server tới client. Named heartbeat event vẫn không chứng minh client đã xử lý thành công dữ liệu theo nghiệp vụ; nếu cần xác nhận, client phải gửi acknowledgement qua request riêng hoặc dùng giao thức hai chiều như WebSocket.

## 6. Chọn khoảng heartbeat như thế nào?

Không có một khoảng thời gian phù hợp cho mọi hệ thống. Hãy bắt đầu từ timeout ngắn nhất của các thành phần trên đường đi:

- Browser hoặc ứng dụng client.
- Reverse proxy / ingress.
- Load balancer.
- API gateway hoặc CDN.
- Firewall/NAT.
- HTTP server và transport.
- Chính sách timeout của ứng dụng.

Heartbeat phải đến trước idle timeout nhỏ nhất với một khoảng dự phòng cho scheduler jitter, tải hệ thống và độ trễ mạng.

Ví dụ, nếu proxy đóng stream sau 60 giây không có payload, có thể bắt đầu thử heartbeat 15–20 giây. Đây chỉ là điểm khởi đầu; cần đo trên hạ tầng thật và điều chỉnh theo timeout thực tế.

| Idle timeout ngắn nhất | Khoảng heartbeat thử nghiệm | Ghi chú |
| --- | --- | --- |
| 30 giây | 8–10 giây | Chừa khoảng dự phòng rõ ràng |
| 60 giây | 15–20 giây | Ví dụ phổ biến cho stream HTTP |
| 120 giây | 30–40 giây | Xác minh thêm timeout của client và proxy |
| Không rõ | Đo timeout thực tế trước | Không chọn một giá trị ngẫu nhiên rồi coi là bảo đảm |

Một công thức khởi đầu dễ nhớ là đặt heartbeat nhỏ hơn đáng kể so với idle timeout ngắn nhất, chẳng hạn khoảng một phần ba timeout đó. Đây là quy tắc thiết kế ban đầu, không phải yêu cầu của HTTP hay Spring.

Cần cân bằng ba yếu tố:

1. **Phát hiện disconnect:** chu kỳ ngắn giúp lần ghi thất bại xảy ra sớm hơn.
2. **Chi phí:** mỗi kết nối nhận thêm heartbeat; hàng chục nghìn kết nối sẽ tạo lượng write và scheduler activity đáng kể.
3. **Timeout trung gian:** heartbeat phải đủ sớm để không bị proxy hoặc load balancer đóng stream.

Không đặt chu kỳ quá ngắn chỉ để có cảm giác an toàn. Hãy đo số kết nối đồng thời, số heartbeat mỗi giây, CPU, network write và số stream bị đóng do timeout.

## 7. Ghép heartbeat với luồng dữ liệu nghiệp vụ

Một cách đơn giản cho nguồn dữ liệu dài hạn:

~~~java
Flux<ServerSentEvent<OrderUpdate>> dataEvents =
    service.events(orderId)
        .map(update -> ServerSentEvent.<OrderUpdate>builder(update)
            .event("order-update")
            .build());

Flux<ServerSentEvent<OrderUpdate>> heartbeats =
    Flux.interval(Duration.ofSeconds(15))
        .map(tick -> ServerSentEvent.<OrderUpdate>builder()
            .comment("keep-alive")
            .build());

return Flux.merge(dataEvents, heartbeats);
~~~

**Flux.merge** cho phép event nghiệp vụ và heartbeat cùng được phát xuống response. Khi nguồn dữ liệu nghiệp vụ im lặng, heartbeat vẫn tạo lần ghi định kỳ.

**Lưu ý về nguồn hữu hạn:** **Flux.interval** là publisher không tự hoàn tất. Nếu ghép nó bằng **Flux.merge** với một nguồn nghiệp vụ hữu hạn, response sẽ tiếp tục mở sau khi nguồn nghiệp vụ đã hoàn tất vì heartbeat vẫn còn chạy. Cách đơn giản trên phù hợp khi endpoint được thiết kế là stream dài hạn, kết thúc khi client disconnect hoặc ứng dụng hủy stream.

Nếu nguồn nghiệp vụ có thể hoàn tất bình thường, nên gắn vòng đời heartbeat với vòng đời nguồn. Ví dụ dưới đây chia sẻ một subscription nguồn bằng **publish**, rồi dùng tín hiệu completion của nguồn để dừng timer:

~~~java
public final class HeartbeatStreams {
    private HeartbeatStreams() {
    }

    public static <T> Flux<ServerSentEvent<T>> withHeartbeat(
            Flux<T> source,
            Duration interval) {

        return source.publish(shared -> {
            Flux<ServerSentEvent<T>> data = shared.map(value ->
                ServerSentEvent.<T>builder(value)
                    .event("update")
                    .build()
            );

            Mono<Boolean> sourceCompleted =
                shared.then(Mono.just(Boolean.TRUE));

            Flux<ServerSentEvent<T>> heartbeat =
                Flux.interval(interval)
                    .onBackpressureDrop()
                    .map(tick ->
                        ServerSentEvent.<T>builder()
                            .comment("keep-alive")
                            .build()
                    )
                    .takeUntilOther(sourceCompleted);

            return Flux.merge(data, heartbeat);
        });
    }
}
~~~

Ở đây:

- **publish** chia sẻ cùng một lần subscribe tới source cho nhánh data và nhánh theo dõi completion.
- **sourceCompleted** chỉ phát true khi nguồn nghiệp vụ hoàn tất bình thường.
- **takeUntilOther** dừng timer heartbeat khi nguồn hoàn tất.
- **Flux.merge** hoàn tất khi cả nhánh dữ liệu và nhánh heartbeat đã hoàn tất.
- Nếu downstream hủy stream, cancellation được truyền ngược qua hai nhánh và tới nguồn chia sẻ.

**onBackpressureDrop()** phù hợp với tick heartbeat vì heartbeat là tín hiệu phụ. Nếu client chậm và không có demand, có thể bỏ một tick thay vì tích lũy một hàng đợi heartbeat. Không áp dụng chính sách drop tương tự cho event nghiệp vụ nếu làm mất dữ liệu là không chấp nhận được.

Nếu nguồn nghiệp vụ là stream vô hạn, sourceCompleted không phát tín hiệu và heartbeat tiếp tục cho tới khi client ngắt hoặc upstream kết thúc bằng lỗi. Nếu nguồn phát lỗi, lỗi được truyền xuống và timer bị hủy cùng stream.

## 8. Phân biệt heartbeat với timeout của dữ liệu nghiệp vụ

Heartbeat trả lời câu hỏi: “Có thể tiếp tục ghi dữ liệu qua response stream không?” Nó không nhất thiết trả lời câu hỏi: “Nguồn nghiệp vụ có còn phát event không?”

Ví dụ, một feed chứng khoán có thể không có thay đổi trong một khoảng thời gian. Heartbeat vẫn phát đều, trong khi dữ liệu nghiệp vụ không có event mới. Điều đó có thể hoàn toàn bình thường.

Nếu nghiệp vụ quy định rằng không có event trong 2 phút là bất thường, hãy đặt timeout trên publisher dữ liệu nghiệp vụ trước khi ghép heartbeat:

~~~java
Flux<Quote> quotes =
    quoteService.stream(symbol)
        .timeout(Duration.ofMinutes(2));

return HeartbeatStreams.withHeartbeat(
    quotes,
    Duration.ofSeconds(15)
);
~~~

Ở đây heartbeat không che giấu sự im lặng của nguồn quote vì **timeout** được đặt trên **quotes** trước khi heartbeat được thêm vào.

Nếu đặt **timeout** trên stream đã ghép heartbeat, mỗi heartbeat sẽ làm mới inactivity timer. Khi đó timeout chỉ đo thời gian không có bất kỳ frame nào, không còn đo thời gian không có dữ liệu nghiệp vụ.

Hãy đặt tên metric riêng cho hai loại thời gian:

- **time_since_last_heartbeat**: thời gian từ lần heartbeat gần nhất.
- **time_since_last_business_event**: thời gian từ event nghiệp vụ gần nhất.

Hai metric trả lời hai câu hỏi vận hành khác nhau.

## 9. NDJSON heartbeat: dùng record có kiểu rõ ràng

NDJSON không có cú pháp comment như SSE. Mỗi dòng phải là một JSON document độc lập. Không chèn dòng **:keep-alive** vào stream NDJSON vì nó không còn là JSON hợp lệ.

Một cách làm là dùng envelope có trường type:

~~~java
public record StreamFrame(
    String type,
    Object payload,
    Instant sentAt
) {
    public static StreamFrame heartbeat() {
        return new StreamFrame("heartbeat", null, Instant.now());
    }

    public static StreamFrame data(Object payload) {
        return new StreamFrame("data", payload, Instant.now());
    }
}
~~~

Publisher:

~~~java
Flux<StreamFrame> frames = Flux.merge(
    service.events(orderId).map(StreamFrame::data),
    Flux.interval(Duration.ofSeconds(15))
        .onBackpressureDrop()
        .map(tick -> StreamFrame.heartbeat())
);
~~~

Response dùng media type **application/x-ndjson**. Các dòng có thể trông như:

~~~json
{"type":"heartbeat","payload":null,"sentAt":"2026-11-08T02:00:15Z"}
{"type":"heartbeat","payload":null,"sentAt":"2026-11-08T02:00:30Z"}
{"type":"data","payload":{"orderId":"A-42","status":"SHIPPED"},"sentAt":"2026-11-08T02:00:31Z"}
~~~

Client parse từng dòng và bỏ qua frame có type là heartbeat. Không trộn JSON record với dòng văn bản không có framing.

Giống SSE, nếu nguồn NDJSON hữu hạn thì phải gắn vòng đời heartbeat với nguồn hoặc chấp nhận rõ rằng endpoint sẽ tiếp tục mở sau khi dữ liệu kết thúc.

## 10. WebSocket heartbeat và acknowledgement

WebSocket là kết nối hai chiều. Ngoài heartbeat dạng message do ứng dụng định nghĩa, giao thức WebSocket có control frame Ping và Pong.

- Ping được gửi để kiểm tra peer.
- Peer phản hồi Pong theo WebSocket protocol.
- Server hoặc client có thể dùng timeout để đánh dấu kết nối không còn phản hồi.
- STOMP over WebSocket và SockJS có cơ chế heartbeat riêng theo giao thức.

Điều này khác SSE comment: SSE comment chỉ đi từ server tới client và không yêu cầu client gửi ACK.

Nếu hệ thống cần server biết client vẫn có thể phản hồi, WebSocket Ping/Pong hoặc application-level acknowledgement phù hợp hơn. Nếu chỉ cần giữ HTTP stream có hoạt động ghi định kỳ để phát hiện disconnect khi write, SSE comment thường đơn giản hơn.

Không gửi chuỗi "ping" trong WebSocket data frame rồi gọi đó là protocol Ping. Data frame và control Ping frame là hai loại frame khác nhau.

## 11. Phát hiện client disconnect và dọn dẹp publisher

Khi client đóng kết nối, server có thể phát hiện vấn đề ở lần ghi tiếp theo. Tùy server adapter và thời điểm disconnect, reactive chain có thể kết thúc bằng error hoặc cancellation.

Vì vậy, không nên giả định mọi disconnect đều xuất hiện dưới đúng một loại exception hoặc chỉ là CANCEL. Hãy dùng **doFinally** để quan sát mọi terminal signal:

~~~java
return HeartbeatStreams.withHeartbeat(
        service.events(orderId),
        Duration.ofSeconds(15))
    .doFinally(signal -> {
        log.info("Stream {} terminated with {}",
            orderId, signal);
    });
~~~

**SignalType** có thể là:

- **ON_COMPLETE**: publisher hoàn tất bình thường.
- **ON_ERROR**: publisher kết thúc bằng lỗi.
- **CANCEL**: downstream hủy subscription.

Nếu chỉ muốn đếm cancellation:

~~~java
.doOnCancel(() ->
    log.info("Client cancelled stream for {}", orderId))
~~~

Nếu cần dọn tài nguyên bất kể kết quả, **doFinally** là nơi phù hợp cho cleanup đơn giản. Với tài nguyên bất đồng bộ như session tới broker, subscription tới hệ thống ngoài hoặc resource có thao tác đóng reactive, cân nhắc **usingWhen** để cleanup theo lifecycle và xử lý lỗi cleanup rõ ràng.

Ví dụ nguồn event cần cleanup:

~~~java
Flux<OrderUpdate> updates =
    Flux.usingWhen(
        eventClient.openSubscription(orderId),
        subscription -> subscription.events(),
        subscription -> subscription.close(),
        (subscription, error) -> subscription.close(),
        subscription -> subscription.close()
    );
~~~

Đây là mẫu minh họa; **eventClient** và kiểu subscription do ứng dụng định nghĩa. **usingWhen** gắn thao tác cleanup với complete, error và cancel. Không giữ subscription toàn cục cho mỗi client nếu nó cần được giải phóng khi client rời stream.

### 11.1. Không nuốt lỗi ghi response

Tránh xử lý mọi lỗi bằng cách trả một response fallback:

~~~java
return stream
    .onErrorResume(error -> Flux.empty());
~~~

Nếu response đã bắt đầu ghi, việc chuyển thành empty publisher không thể làm client nhận lại status hoặc headers mới. Nó còn có thể che giấu nguyên nhân stream bị ngắt.

Nên phân loại lỗi:

- Client disconnect / write failure: ghi metric phù hợp và dọn subscription.
- Lỗi nguồn dữ liệu: ghi nhận và áp dụng chính sách retry/fallback của nghiệp vụ.
- Lỗi lập trình: để error handler ghi nhận và xử lý đúng.
- Cancellation do client đóng stream: cleanup, không cố gửi thêm body cho kết nối đã đóng.

## 12. Proxy, load balancer và response buffering

Heartbeat chỉ có ích nếu byte được đẩy ra khỏi ứng dụng đủ thường xuyên. Một số thành phần trung gian có thể buffer response, nén dữ liệu hoặc áp idle timeout riêng.

Khi triển khai streaming qua reverse proxy:

1. Tắt hoặc cấu hình buffering phù hợp cho endpoint SSE/NDJSON.
2. Kiểm tra proxy có flush từng event/chunk không.
3. Đặt idle timeout lớn hơn chu kỳ heartbeat với khoảng dự phòng.
4. Kiểm tra timeout ở cả ingress, load balancer và CDN.
5. Xác minh compression có làm trì hoãn việc flush payload nhỏ không.
6. Kiểm thử qua đúng đường mạng production, không chỉ gọi localhost.

Với Nginx, endpoint SSE thường cần **proxy_buffering off;**. Có thể dùng header **X-Accel-Buffering: no** nếu kiến trúc Nginx cho phép. Tên cấu hình cụ thể phụ thuộc reverse proxy; không có một cấu hình chung cho mọi gateway.

Spring WebFlux ghi và flush dữ liệu theo codec/media type. Với SSE, framework xử lý từng event để tránh chờ gom toàn bộ stream. Tuy nhiên, proxy hoặc middleware bên ngoài vẫn có thể buffer, nên phải kiểm tra end-to-end.

Một heartbeat được tạo trong Reactor nhưng vẫn nằm trong buffer của proxy chưa giúp client hoặc intermediary thấy hoạt động mạng. Hãy kiểm tra bằng **curl -N** hoặc một client streaming thật qua cùng ingress mà người dùng sẽ đi qua.

## 13. Reactor Netty idle timeout và HTTP/2 PING

Reactor Netty cung cấp timeout ở tầng transport/server:

- **idleTimeout** giới hạn thời gian connection không có hoạt động theo cấu hình server.
- Với HTTP/2, Reactor Netty hỗ trợ PING/ACK để kiểm tra peer khi idle timeout và các tham số PING được cấu hình.
- Nếu không cấu hình idle timeout phù hợp, HTTP/2 PING health check có thể không được kích hoạt theo cách mong muốn.

HTTP/2 PING kiểm tra connection ở tầng HTTP/2. Một connection HTTP/2 có thể mang nhiều stream; PING không thay thế event heartbeat ở từng stream ứng dụng nếu client cần heartbeat event hoặc cần cập nhật trạng thái nghiệp vụ.

TCP keepalive là cơ chế khác. Reactor Netty ghi nhận **SO_KEEPALIVE** không mặc định được bật trong mọi cấu hình và thời gian probe thường phụ thuộc hệ điều hành. Không dựa vào TCP keepalive để đáp ứng một idle timeout HTTP ngắn như 30 hoặc 60 giây.

Hãy chọn tầng phù hợp:

| Mục tiêu | Cơ chế nên xem xét |
| --- | --- |
| Giữ response SSE có hoạt động payload | SSE comment heartbeat |
| Client JavaScript cần biết heartbeat | Named SSE heartbeat event |
| Stream JSON record | NDJSON heartbeat envelope |
| Kiểm tra WebSocket peer | WebSocket Ping/Pong hoặc STOMP heartbeat |
| Kiểm tra HTTP/2 connection | HTTP/2 PING/ACK của transport |
| Phát hiện lỗi kết nối TCP lâu dài | TCP keepalive và timeout transport |

## 14. Backpressure và tải khi có nhiều client

Mỗi client stream có thể có một publisher heartbeat riêng. Với hàng nghìn hoặc hàng chục nghìn kết nối, heartbeat tạo số lượng write định kỳ đáng kể.

Giả sử có 10.000 kết nối và mỗi kết nối gửi heartbeat mỗi 15 giây. Trung bình server tạo khoảng 667 heartbeat mỗi giây, chưa tính event nghiệp vụ và overhead network. Khi tăng số client, hãy đo:

- Số heartbeat phát mỗi giây.
- Số stream đang hoạt động.
- Số write pending và thời gian write.
- Số disconnect, error và cancellation.
- Scheduler queue và CPU.
- Buffer/backpressure của downstream.
- Tài nguyên upstream như subscription tới broker.

Heartbeat không phải dữ liệu nghiệp vụ nên có thể drop khi downstream chưa có demand. Không nên buffer heartbeat không giới hạn; heartbeat cũ không còn giá trị khi một tick mới sắp tới.

Ngược lại, không drop event nghiệp vụ nếu hệ thống cần bảo đảm mọi event được giao. Tách chính sách backpressure của heartbeat khỏi chính sách event dữ liệu.

Tránh tạo một scheduler riêng cho từng client. **Flux.interval** sử dụng scheduler mặc định của Reactor; nếu cần scheduler riêng, hãy quản lý lifecycle và giới hạn thread rõ ràng.

## 15. Client watchdog và reconnect

Nếu dùng comment-only SSE, JavaScript không nhận event callback cho heartbeat. Nếu client cần watchdog, hãy phát named heartbeat event và cập nhật timestamp khi nhận được:

~~~javascript
const source = new EventSource("/api/orders/A-42/events");
let lastHeartbeatAt = Date.now();

source.addEventListener("heartbeat", () => {
    lastHeartbeatAt = Date.now();
});

source.addEventListener("order-update", event => {
    const update = JSON.parse(event.data);
    renderOrder(update);
});

const watchdog = setInterval(() => {
    const silentFor = Date.now() - lastHeartbeatAt;

    if (silentFor > 45000) {
        console.warn("No heartbeat received recently");
    }
}, 5000);
~~~

Ví dụ này chỉ minh họa watchdog phía client. Trong ứng dụng thực tế, cần clear timer khi đóng EventSource và cân nhắc timer throttling ở browser background tab.

**EventSource** tự reconnect khi kết nối bị gián đoạn theo chính sách của trình duyệt. Trường **retry** trong SSE có thể gợi ý thời gian chờ trước lần reconnect; nó **không phải heartbeat interval**.

Nếu cần replay event sau reconnect:

- Gán id ổn định cho event nghiệp vụ.
- Server đọc Last-Event-ID và tiếp tục từ vị trí phù hợp.
- Không gán ID mới cho comment heartbeat.
- Giữ chính sách replay/idempotency rõ ràng để không xử lý event trùng.

Không coi reconnect thành bảo đảm không mất dữ liệu. Server cần lưu hoặc tái tạo event theo ID nếu contract yêu cầu replay.

## 16. Java 17+ Spring Boot WebFlux demo hoàn chỉnh

Demo tạo endpoint SSE cho một order. Nguồn nghiệp vụ giả lập chỉ phát một update mỗi 45 giây; heartbeat comment được phát mỗi 15 giây. Khi client disconnect, cancellation hoặc write error đi qua reactive chain và được quan sát bằng **doFinally**.

### 16.1. Cấu trúc dự án

~~~text
webflux-heartbeat-demo/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      OrderUpdate.java
      OrderEventService.java
      HeartbeatStreams.java
      OrderStreamController.java
    test/java/demo/
      HeartbeatStreamsTest.java
~~~

### 16.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot quản lý phiên bản Spring Framework và Reactor tương thích qua dependency management. Không cần tự ghim một phiên bản Reactor khác nếu chưa có yêu cầu cụ thể.

### 16.3. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 16.4. OrderUpdate.java

~~~java
package demo;

import java.time.Instant;

public record OrderUpdate(
    String orderId,
    long sequence,
    String status,
    Instant occurredAt
) {
}
~~~

Record biểu diễn một event nghiệp vụ. sequence có thể dùng làm SSE ID trong demo; hệ thống thật nên dùng ID ổn định từ event store hoặc nguồn dữ liệu.

### 16.5. OrderEventService.java

~~~java
package demo;

import java.time.Duration;
import java.time.Instant;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class OrderEventService {

    public Flux<OrderUpdate> stream(String orderId) {
        // Demo: giả lập một thay đổi nghiệp vụ mỗi 45 giây.
        return Flux.interval(Duration.ofSeconds(45))
            .map(sequence -> new OrderUpdate(
                orderId,
                sequence + 1,
                "PROCESSING",
                Instant.now()
            ));
    }
}
~~~

Trong ứng dụng thật, thay Flux.interval giả lập bằng publisher từ Kafka, Redis Pub/Sub, database change stream hoặc event service. Không dùng timer giả lập làm nguồn nghiệp vụ trong production.

### 16.6. HeartbeatStreams.java

~~~java
package demo;

import java.time.Duration;
import org.springframework.http.codec.ServerSentEvent;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class HeartbeatStreams {
    private HeartbeatStreams() {
    }

    public static <T> Flux<ServerSentEvent<T>> withHeartbeat(
            Flux<T> source,
            Duration interval) {

        return source.publish(shared -> {
            Flux<ServerSentEvent<T>> data = shared.map(value ->
                ServerSentEvent.<T>builder(value)
                    .event("order-update")
                    .build()
            );

            Mono<Boolean> sourceCompleted =
                shared.then(Mono.just(Boolean.TRUE));

            Flux<ServerSentEvent<T>> heartbeat =
                Flux.interval(interval)
                    .onBackpressureDrop()
                    .map(tick ->
                        ServerSentEvent.<T>builder()
                            .comment("keep-alive")
                            .build()
                    )
                    .takeUntilOther(sourceCompleted);

            return Flux.merge(data, heartbeat);
        });
    }
}
~~~

Method dùng publish để chia sẻ cùng một subscription của nguồn. Nhánh theo dõi completion giúp timer dừng khi nguồn hữu hạn hoàn tất. Với nguồn vô hạn, timer chỉ dừng khi downstream hủy hoặc nguồn kết thúc bằng lỗi.

### 16.7. OrderStreamController.java

~~~java
package demo;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

@RestController
public class OrderStreamController {
    private static final Logger log =
        LoggerFactory.getLogger(OrderStreamController.class);

    private static final Duration HEARTBEAT_INTERVAL =
        Duration.ofSeconds(15);

    private final OrderEventService service;

    public OrderStreamController(OrderEventService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/api/orders/{orderId}/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<OrderUpdate>> events(
            @PathVariable String orderId) {

        return HeartbeatStreams.withHeartbeat(
                service.stream(orderId),
                HEARTBEAT_INTERVAL
            )
            .doFinally((SignalType signal) ->
                log.info("Order stream {} ended with {}",
                    orderId, signal));
    }
}
~~~

Endpoint trả text/event-stream. Khi chưa có update, client vẫn nhận comment heartbeat. Khi nguồn phát update, client nhận event order-update. doFinally quan sát complete, error và cancel.

### 16.8. HeartbeatStreamsTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class HeartbeatStreamsTest {

    @Test
    void emitsHeartbeatWhenBusinessSourceIsQuiet() {
        StepVerifier.withVirtualTime(() ->
                HeartbeatStreams.withHeartbeat(
                    Flux.<String>never(),
                    Duration.ofSeconds(10)
                ))
            .thenAwait(Duration.ofSeconds(10))
            .expectNextMatches(event ->
                "keep-alive".equals(event.comment())
                    && event.data() == null)
            .thenCancel()
            .verify();
    }

    @Test
    void finiteSourceCompletionStopsHeartbeat() {
        StepVerifier.withVirtualTime(() ->
                HeartbeatStreams.withHeartbeat(
                    Flux.just("completed"),
                    Duration.ofSeconds(10)
                ))
            .expectNextMatches(event ->
                "order-update".equals(event.event())
                    && "completed".equals(event.data()))
            .verifyComplete();
    }

    @Test
    void cancellationPropagatesToBusinessSource() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Flux<String> source =
            Flux.<String>never()
                .doOnCancel(() -> cancelled.set(true));

        StepVerifier.withVirtualTime(() ->
                HeartbeatStreams.withHeartbeat(
                    source,
                    Duration.ofSeconds(10)
                ))
            .thenAwait(Duration.ofSeconds(10))
            .expectNextMatches(event ->
                "keep-alive".equals(event.comment()))
            .thenCancel()
            .verify();

        assertTrue(cancelled.get());
    }

    @Test
    void sourceEventCarriesItsBusinessData() {
        OrderUpdate update = new OrderUpdate(
            "A-42",
            7,
            "SHIPPED",
            Instant.parse("2026-11-08T02:00:00Z")
        );

        StepVerifier.withVirtualTime(() ->
                HeartbeatStreams.withHeartbeat(
                    Flux.just(update),
                    Duration.ofSeconds(10)
                ))
            .expectNextMatches(event ->
                "order-update".equals(event.event())
                    && update.equals(event.data()))
            .verifyComplete();
    }
}
~~~

Các test dùng virtual time của Reactor nên không phải chờ thật 10 giây. Chúng xác minh heartbeat xuất hiện khi nguồn im lặng, timer dừng khi nguồn hữu hạn hoàn tất và cancellation được truyền về nguồn.

### 16.9. Chạy ứng dụng

Tại thư mục dự án:

~~~bash
./gradlew bootRun
~~~

Hoặc nếu đã cài Gradle:

~~~bash
gradle bootRun
~~~

Mở stream:

~~~bash
curl -N -i http://localhost:8080/api/orders/A-42/events
~~~

Trong khoảng 45 giây trước update nghiệp vụ đầu tiên, response có các comment heartbeat cách nhau khoảng 15 giây:

~~~text
:keep-alive

:keep-alive

event: order-update
data: {"orderId":"A-42","sequence":1,"status":"PROCESSING","occurredAt":"..."}

~~~

Dấu ba chấm là phần timestamp phụ thuộc thời điểm chạy. Các comment heartbeat không được JavaScript EventSource phát thành message event.

Dừng curl bằng Ctrl+C để hủy client stream. Server sẽ phát hiện disconnect ở lần ghi tiếp theo hoặc khi transport báo connection đã đóng; doFinally ghi lại terminal signal tương ứng.

Chạy test:

~~~bash
./gradlew test
~~~

Không cần Thread.sleep trong test. Virtual time giúp kiểm tra chu kỳ heartbeat và cancellation một cách xác định.

## 17. Kiểm thử streaming qua WebTestClient

Ngoài unit test cho publisher, có thể dùng WebTestClient để xác minh endpoint khai báo đúng media type và stream được đọc theo kiểu SSE:

~~~java
var result = client.get()
    .uri("/api/orders/A-42/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
    .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
    .returnResult(
        new ParameterizedTypeReference<ServerSentEvent<OrderUpdate>>() {}
    );

StepVerifier.create(result.getResponseBody())
    .expectNextMatches(event ->
        "keep-alive".equals(event.comment()))
    .thenCancel()
    .verify(Duration.ofSeconds(20));
~~~

Đây là mẫu integration test cần WebTestClient, ParameterizedTypeReference, ServerSentEvent và StepVerifier. Trong test thực tế, nên cấu hình heartbeat interval ngắn hơn, ví dụ một giây, để không phải chờ 15 giây. Sau khi nhận event, thenCancel đóng stream và kiểm tra cancellation.

Không dùng expectBodyList cho một SSE stream vô hạn vì test sẽ chờ body hoàn tất. Dùng returnResult để lấy publisher response body và tiêu thụ một số event có chủ đích.

## 18. Cách quan sát heartbeat trong production

Nên ghi metric và log theo stream lifecycle, không log toàn bộ heartbeat ở mức INFO cho từng kết nối nếu lưu lượng lớn.

Các metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| active_streams | Số stream hiện đang mở |
| heartbeat_sent_total | Tổng heartbeat đã phát |
| stream_disconnect_total | Số stream kết thúc do disconnect/write failure |
| stream_cancel_total | Số stream nhận cancellation |
| stream_error_total | Số stream kết thúc bằng error |
| stream_duration_seconds | Thời gian sống của stream |
| time_since_last_business_event | Thời gian từ event nghiệp vụ gần nhất |
| time_since_last_heartbeat | Thời gian từ heartbeat gần nhất |

Không nên coi mọi ON_ERROR là client disconnect. Lỗi có thể đến từ upstream, serialization, timeout, bug hoặc transport. Hãy phân loại exception và ghi metric riêng khi có thể.

Nếu có hàng nghìn client, không ghi một log INFO cho từng heartbeat. Ghi log khi stream mở/đóng, khi lỗi, hoặc khi phát hiện tình huống bất thường; dùng counter/histogram cho heartbeat bình thường.

## 19. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ gửi dữ liệu khi nghiệp vụ thay đổi | Kết nối có thể im lặng quá lâu và disconnect được phát hiện muộn | Gửi heartbeat định kỳ |
| Dùng heartbeat comment nhưng mong JavaScript nhận message | EventSource bỏ qua comment trong event dispatch | Dùng named heartbeat event nếu client cần watchdog |
| Dùng SSE comment trong NDJSON | Dòng không còn là JSON hợp lệ | Dùng JSON envelope có type=heartbeat |
| Ghép Flux.interval vô hạn với nguồn hữu hạn bằng merge | Response không hoàn tất khi nguồn dữ liệu đã xong | Dừng timer theo completion của nguồn hoặc không thêm heartbeat nếu không cần |
| Không hủy upstream khi client rời đi | Subscription tới broker/service vẫn giữ tài nguyên | Quan sát doFinally, dùng usingWhen khi cần cleanup bất đồng bộ |
| Chỉ bắt cancellation | Một số disconnect được biểu diễn thành write error | Quan sát complete/error/cancel bằng doFinally và phân loại lỗi |
| Cho rằng heartbeat chứng minh client đã xử lý message | Nhầm lẫn write liveness với application acknowledgement | Dùng acknowledgement riêng nếu cần xác nhận |
| Chọn heartbeat dài hơn proxy idle timeout | Proxy đóng stream trước lần heartbeat tiếp theo | Đặt interval nhỏ hơn timeout ngắn nhất với khoảng dự phòng |
| Proxy buffer response | Heartbeat không tới client đúng thời điểm | Tắt hoặc điều chỉnh buffering, xác minh flush qua ingress |
| Dùng TCP keepalive thay heartbeat HTTP | TCP probe có thể không làm mới HTTP idle timer | Dùng application heartbeat cho SSE/NDJSON |
| Dùng timeout sau khi đã merge heartbeat | Heartbeat làm mới timer và che giấu sự im lặng của nguồn nghiệp vụ | Đặt timeout trên publisher nghiệp vụ trước khi ghép |
| Buffer heartbeat không giới hạn | Tăng memory và gửi heartbeat cũ không còn hữu ích | Drop tick heartbeat khi downstream chậm |
| Drop event nghiệp vụ để giảm tải | Mất dữ liệu quan trọng | Chỉ drop heartbeat; chọn backpressure policy riêng cho event |
| Gán event ID cho heartbeat | Làm thay đổi Last-Event-ID không cần thiết | Chỉ gán ID cho event nghiệp vụ có thể replay |
| Log mọi heartbeat ở INFO | Log volume tăng nhanh theo số client | Dùng metric; log mở/đóng và lỗi |
| Dùng Thread.sleep để tạo heartbeat | Chặn thread và phá reactive pipeline | Dùng Flux.interval |
| Gọi subscribe riêng cho heartbeat | Lifecycle tách khỏi response và khó cleanup | Ghép publisher rồi return một Flux duy nhất |
| Dùng một publisher global cho mọi client mà không hiểu sharing | Client có thể chia sẻ lifecycle hoặc dữ liệu ngoài ý muốn | Tạo publisher theo subscription và quản lý fan-out rõ ràng |

## 20. Checklist thiết kế heartbeat

Trước khi đưa stream vào production, hãy xác định:

1. Stream dùng SSE, NDJSON, WebSocket hay protocol khác?
2. Heartbeat cần chỉ để server phát hiện disconnect hay client cũng cần nhìn thấy?
3. Idle timeout ngắn nhất của proxy, load balancer, gateway và server là bao nhiêu?
4. Chu kỳ heartbeat có đủ ngắn và có khoảng dự phòng không?
5. Response có thực sự flush qua toàn bộ proxy chain không?
6. Nếu source hữu hạn hoàn tất, heartbeat timer có dừng không?
7. Nếu client disconnect, upstream subscription có bị cancel/cleanup không?
8. Lỗi ghi response được phân biệt với lỗi nghiệp vụ như thế nào?
9. Heartbeat có bị drop khi downstream chậm thay vì tích lũy vô hạn không?
10. Event nghiệp vụ có bị ảnh hưởng bởi backpressure policy của heartbeat không?
11. Client có cần named heartbeat event hoặc watchdog không?
12. Reconnect có dùng event ID/Last-Event-ID để replay không?
13. Có metric active stream, heartbeat, error, cancel và duration không?
14. Đã kiểm thử qua reverse proxy/ingress thực tế chưa?

| Nhu cầu | Lựa chọn |
| --- | --- |
| SSE server-side keep-alive | Comment-only ServerSentEvent.comment(...) |
| SSE client watchdog | Named event heartbeat có data |
| NDJSON keep-alive | JSON envelope type=heartbeat |
| Nguồn hữu hạn | Dừng timer khi source hoàn tất |
| Nguồn dài hạn | Timer chạy cho tới cancel/error/complete |
| Cleanup subscription | doFinally, usingWhen |
| Timer không chặn thread | Flux.interval |
| Bỏ heartbeat khi client chậm | onBackpressureDrop |
| Timeout dữ liệu nghiệp vụ | timeout trước khi merge heartbeat |
| WebSocket peer liveness | Ping/Pong hoặc STOMP heartbeat |
| HTTP/2 connection health | PING/ACK ở transport |
| Client reconnect/replay | SSE retry và Last-Event-ID |

## 21. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Vì sao WebFlux stream cần gửi heartbeat khi không có event nghiệp vụ?

**Đáp án:** Để tạo lần ghi định kỳ, giúp phát hiện disconnect sớm hơn và tránh intermediary đóng stream do idle timeout.

**Câu 2.** SSE comment-only heartbeat có gọi onmessage trong EventSource không?

**Đáp án:** Không. Comment được bỏ qua trong event dispatch; nó vẫn là dữ liệu truyền trên response stream.

**Câu 3.** Nếu JavaScript cần biết heartbeat gần nhất thì nên dùng dạng nào?

**Đáp án:** Named SSE event như event: heartbeat với data, rồi lắng nghe bằng addEventListener("heartbeat", ...).

**Câu 4.** Vì sao TCP keepalive không thay thế SSE heartbeat?

**Đáp án:** TCP keepalive hoạt động ở tầng transport, thường có chu kỳ và cấu hình khác. Nó không nhất thiết làm mới HTTP idle timeout hoặc tạo event cho client.

**Câu 5.** Flux.interval có hoàn tất tự nhiên không?

**Đáp án:** Không. Nó tiếp tục phát tick cho tới khi bị cancel hoặc kết thúc do lỗi. Vì vậy khi ghép với nguồn hữu hạn cần dừng timer theo lifecycle của nguồn.

**Câu 6.** Vì sao ví dụ dùng publish khi nguồn dữ liệu có thể hoàn tất?

**Đáp án:** publish chia sẻ một subscription cho nhánh dữ liệu và nhánh theo dõi completion, tránh subscribe nguồn hai lần để phát hiện lúc nguồn hoàn tất và dừng heartbeat.

**Câu 7.** doFinally khác doOnCancel thế nào?

**Đáp án:** doFinally chạy khi complete, error hoặc cancel và nhận SignalType; doOnCancel chỉ quan sát cancellation.

**Câu 8.** Có nên dùng timeout trên stream đã ghép heartbeat để phát hiện nguồn nghiệp vụ im lặng không?

**Đáp án:** Không. Heartbeat sẽ làm mới inactivity timer. Đặt timeout trên publisher nghiệp vụ trước khi ghép heartbeat.

**Câu 9.** NDJSON có thể dùng comment :keep-alive như SSE không?

**Đáp án:** Không. NDJSON yêu cầu mỗi dòng là JSON document; dùng record envelope có type=heartbeat.

**Câu 10.** Nếu response bị proxy buffer, heartbeat có tác dụng không?

**Đáp án:** Có thể không tới client đúng thời điểm. Cần cấu hình proxy flush/buffering phù hợp và kiểm thử end-to-end.

**Câu 11.** Heartbeat comment có chứng minh client đã xử lý event nghiệp vụ không?

**Đáp án:** Không. Nó chỉ tạo payload ghi định kỳ. Muốn xác nhận client xử lý cần acknowledgement riêng hoặc giao thức hai chiều.

**Câu 12.** Nếu client chậm, có nên buffer vô hạn các heartbeat đã trễ không?

**Đáp án:** Không. Heartbeat cũ không còn hữu ích; có thể drop tick heartbeat khi downstream thiếu demand, nhưng phải có chính sách backpressure riêng cho event nghiệp vụ.

## 22. Ghi nhớ và tài liệu chính thức

- Heartbeat là tín hiệu nhỏ được gửi định kỳ trong stream dài hạn để tạo hoạt động ghi và phát hiện disconnect sớm hơn.
- Với SSE, comment-only heartbeat là cách gọn vì không tạo message event cho EventSource.
- Nếu JavaScript cần watchdog, dùng named heartbeat event có data.
- Với NDJSON, dùng record JSON có type heartbeat; không dùng comment SSE.
- Chọn interval dựa trên idle timeout ngắn nhất của proxy, load balancer, gateway và server, có khoảng dự phòng.
- Flux.interval không tự hoàn tất; gắn timer với lifecycle của source nếu nguồn có thể hữu hạn.
- publish có thể chia sẻ một upstream subscription khi cần vừa phát data vừa theo dõi source completion.
- doFinally quan sát complete/error/cancel; cleanup subscription cần được gắn với lifecycle reactive.
- Timeout trên publisher nghiệp vụ phải đặt trước khi ghép heartbeat nếu muốn phát hiện business source im lặng.
- TCP keepalive, HTTP/2 PING, SSE comment và WebSocket Ping/Pong thuộc các tầng khác nhau.
- Heartbeat không thay thế acknowledgement nếu cần xác nhận client đã xử lý dữ liệu.

Tài liệu chính thức:

1. [Spring Framework Reference — Reactive Core: Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): khuyến nghị gửi dữ liệu định kỳ cho text/event-stream và application/x-ndjson để phát hiện client disconnect; mô tả comment-only SSE và no-op heartbeat.
2. [Spring Framework Javadoc — ServerSentEvent.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ServerSentEvent.Builder.html): API comment, event, id, retry và data.
3. [Spring Framework Reference — WebFlux Controller Return Types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): trả Flux và ServerSentEvent từ controller.
4. [Project Reactor Reference — Handling Errors and doFinally](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): terminal signals, cancellation và cleanup.
5. [Project Reactor Javadoc — Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): interval, publish, merge, takeUntilOther, onBackpressureDrop và doFinally.
6. [Reactor Netty Reference — HTTP Server](https://projectreactor.io/docs/netty/release/reference/http-server.html): server idle timeout và HTTP/2 PING/ACK health check.
7. [Reactor Netty Reference — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): TCP keepalive và HTTP/2 connection health check.
8. [Spring Framework Reference — WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket.html): lựa chọn WebSocket cho giao tiếp hai chiều.

# Chọn server streaming cho dữ liệu liên tục

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện workload phù hợp với server-streaming RPC.
- Phân biệt server streaming với polling, SSE, WebSocket, bidirectional streaming và messaging.
- Thiết kế Protobuf contract cho subscription và cập nhật dữ liệu liên tục.
- Quản lý flow control, bounded buffer, cancellation và deadline.
- Thiết kế reconnect/resume bằng sequence hoặc cursor ở tầng ứng dụng.
- Đánh giá tác động của stream dài hạn tới load balancing, scale và shutdown.
- Kiểm thử streaming qua Spring gRPC server bằng generated client stub.

## 1. Bài toán dữ liệu liên tục

Một số client cần nhận dữ liệu ngay khi server có thay đổi: giá thị trường, trạng thái đơn hàng, tiến độ xử lý, telemetry thiết bị hoặc cập nhật tồn kho. Nếu client liên tục gọi API để hỏi dữ liệu mới, hệ thống tạo nhiều request dù phần lớn lần hỏi không có thay đổi. Cách này làm tăng tải, tạo độ trễ giữa hai lần polling và khiến client phải tự chọn chu kỳ hỏi.

**Server streaming** cho phép client gửi một request đăng ký, sau đó server gửi nhiều response message trên cùng một RPC. Server chủ động phát dữ liệu khi có cập nhật; client không cần gửi request mới cho từng bản tin.

Trong **SPRING_GRPC**, server streaming phù hợp với service-to-service hoặc client backend cần một luồng cập nhật có kiểu dữ liệu Protobuf, status gRPC, metadata và lifecycle rõ ràng. Đây là một lựa chọn cho dữ liệu liên tục khi luồng chủ yếu đi từ server tới client.

Server streaming không tự biến thành event store bền vững. Nếu client offline cần đọc lại toàn bộ event đã bỏ lỡ, phải bổ sung log/cursor hoặc dùng message broker/event platform làm nguồn dữ liệu.

## 2. Server-streaming RPC hoạt động thế nào?

Trong Protobuf, server-streaming method có một request và response được khai báo là stream:

~~~proto
rpc WatchPrices(WatchPricesRequest) returns (stream PriceUpdate);
~~~

Vòng đời cơ bản:

1. Client mở RPC và gửi một WatchPricesRequest.
2. Server xác thực, kiểm tra subscription và đăng ký nguồn dữ liệu.
3. Server phát nhiều PriceUpdate qua cùng call.
4. Server kết thúc bằng onCompleted() khi luồng hữu hạn hoàn tất, hoặc onError() khi gặp lỗi.
5. Client có thể hủy call khi không còn cần dữ liệu.

Một RPC server-streaming có thể hữu hạn hoặc kéo dài. Ví dụ tải báo cáo theo từng chunk thường hữu hạn; subscription giá thị trường có thể kéo dài đến khi client hủy, deadline hết hoặc server đóng kết nối.

Server streaming là một chiều dữ liệu sau request ban đầu. Nếu client cần gửi lệnh điều khiển thường xuyên trong cùng call, cân nhắc bidirectional streaming hoặc tách lệnh thành unary RPC riêng.

## 3. Khi nào nên chọn server streaming?

Server streaming phù hợp khi:

- Client cần nhận nhiều cập nhật từ một subscription hoặc truy vấn ban đầu.
- Dữ liệu chủ yếu đi từ server tới client.
- Client có thể xử lý từng message khi nhận, không cần chờ toàn bộ kết quả.
- Cần giảm polling và giữ một RPC có lifecycle rõ.
- Có thể giới hạn tốc độ, buffer và thời gian sống của stream.
- Client/server đều hỗ trợ gRPC và HTTP/2.

Ví dụ: một service giám sát đăng ký theo device_id, server gửi các trạng thái mới; một backend theo dõi tiến độ batch, server phát phần trăm hoàn tất; một client giao dịch đăng ký theo symbol và nhận từng thay đổi giá.

Không nên chọn server streaming chỉ vì dữ liệu có nhiều bản ghi. Nếu client cần tải collection tĩnh, pagination qua unary RPC thường đơn giản hơn. Nếu cần truyền file lớn, chunked upload/download có thể phù hợp, nhưng phải thiết kế resume, checksum và giới hạn kích thước riêng.

## 4. So sánh với polling, SSE, WebSocket và messaging

| Cơ chế | Hướng dữ liệu | Phù hợp khi | Giới hạn cần cân nhắc |
| --- | --- | --- | --- |
| Polling REST | Client hỏi định kỳ | Dữ liệu đổi ít, độ trễ cập nhật không quá quan trọng | Request thừa, chu kỳ polling tạo độ trễ. |
| Server streaming gRPC | Server gửi nhiều message sau một request | Backend/client gRPC cần feed có kiểu dữ liệu và status RPC | Stream gắn với connection/call; reconnect và replay phải thiết kế. |
| SSE | Server đẩy event một chiều tới browser | Web browser cần cập nhật qua HTTP đơn giản | Một chiều; browser/API gateway cần hỗ trợ stream lâu dài. |
| WebSocket | Hai chiều | Browser/app cần giao tiếp realtime hai chiều | Phải tự định nghĩa message contract, auth, heartbeat và flow control ở tầng ứng dụng. |
| Bidirectional gRPC | Hai chiều qua một RPC | Client và server đều cần gửi message liên tục | Phức tạp hơn server streaming; cần quản lý hai chiều và backpressure. |
| Message broker/event log | Producer phát, consumer đọc | Cần buffering, consumer độc lập, replay hoặc fan-out bền vững | Có thêm broker, eventual consistency và vận hành consumer. |

Browser không gọi gRPC native trực tiếp theo cách Fetch gọi REST. Nếu client là browser, cân nhắc SSE, WebSocket hoặc gRPC-Web tùy contract và proxy. Với consumer cần nhận event khi offline và replay từ offset cũ, broker/event log phù hợp hơn một RPC stream thuần.

## 5. Kiến trúc subscription server-streaming

~~~mermaid
flowchart LR
  C["gRPC client"] -->|"Watch request"| S["Spring gRPC service"]
  S -->|"Subscribe"| F["Domain feed / event source"]
  F -->|"Updates"| S
  S -->|"Response stream"| C
  C -->|"Cancel / deadline"| S
~~~

Service nhận request, xác minh quyền truy cập, đăng ký vào feed và chuyển từng update sang response observer. Khi call bị cancel hoặc deadline hết, service phải hủy subscription và dừng công việc liên quan.

Nếu nguồn dữ liệu đã có event log, service có thể đọc từ cursor rồi chuyển sang live updates. Nếu nguồn chỉ phát event trong bộ nhớ, client offline có thể bỏ lỡ dữ liệu; khi đó contract phải nói rõ stream chỉ cung cấp dữ liệu từ thời điểm đăng ký.

## 6. Thiết kế Protobuf contract cho feed liên tục

Ví dụ service phát giá theo symbol:

~~~proto
syntax = "proto3";

package acme.market.v1;

option java_package = "com.acme.market.grpc";
option java_multiple_files = true;

message WatchPricesRequest {
  string symbol = 1;
  int64 resume_after_sequence = 2;
  bool include_snapshot = 3;
}

message PriceUpdate {
  string symbol = 1;
  int64 sequence = 2;
  int64 price_minor_units = 3;
  string currency_code = 4;
  int64 published_at_epoch_millis = 5;
}

service MarketData {
  rpc WatchPrices(WatchPricesRequest) returns (stream PriceUpdate);
}
~~~

symbol xác định nguồn dữ liệu. sequence giúp phát hiện gap, duplicate và thứ tự. resume_after_sequence là cursor do contract định nghĩa để client yêu cầu tiếp tục sau một update đã nhận. include_snapshot cho phép client yêu cầu trạng thái hiện tại trước khi nhận cập nhật mới.

Dùng integer đơn vị nhỏ nhất của tiền thay vì floating point để tránh sai số số thực. Định nghĩa rõ currency, đơn vị, timezone và ý nghĩa timestamp. Không dùng timestamp làm sequence vì nhiều update có thể cùng thời điểm hoặc đồng hồ giữa node không đồng bộ.

Nếu server không hỗ trợ resume, bỏ field cursor hoặc trả lỗi rõ ràng; không để client hiểu nhầm rằng chỉ cần gửi sequence là server có thể replay.

## 7. Snapshot và live update không được tạo khoảng trống

Một lỗi thường gặp là server đọc snapshot hiện tại rồi mới đăng ký listener. Nếu dữ liệu đổi giữa hai thao tác, client không nhận được update đó.

Có hai hướng an toàn:

- Nguồn dữ liệu cung cấp thao tác atomic: lấy snapshot cùng vị trí log/sequence, sau đó đọc tiếp từ vị trí đó.
- Dùng event log có cursor: xác định offset snapshot, phát các event sau offset rồi chuyển sang tail/live.

Ví dụ client nhận snapshot ở sequence 100, sau đó server phát sequence 101 trở đi. Nếu server không thể đảm bảo chuyển tiếp liền mạch, client cần phát hiện gap và gọi API snapshot/resync.

Không khẳng định server streaming tự bảo đảm snapshot consistency. Đây là semantics của domain feed hoặc event store, phải được thiết kế và kiểm thử riêng.

## 8. Triển khai server service trong Spring gRPC

Generated base class cung cấp method nhận request và StreamObserver cho response. Service được đăng ký với gRPC server theo cơ chế của starter Spring đang dùng:

~~~java
final class MarketDataGrpcService
        extends MarketDataGrpc.MarketDataImplBase {
    private final PriceFeed priceFeed;

    MarketDataGrpcService(PriceFeed priceFeed) {
        this.priceFeed = priceFeed;
    }

    @Override
    public void watchPrices(
            WatchPricesRequest request,
            StreamObserver<PriceUpdate> responseObserver) {
        // Kiểm tra symbol, quyền truy cập và cursor.
        // Đăng ký feed và phát nhiều update qua responseObserver.
        // Hủy subscription khi call bị cancel hoặc kết thúc.
    }
}
~~~

Đây là skeleton thể hiện ranh giới service; phần đăng ký feed và flow control phụ thuộc API domain của ứng dụng. Không giữ StreamObserver trong singleton field dùng chung cho nhiều client. Mỗi RPC cần state riêng gồm subscription, queue, cancellation và cursor.

Service không nên block một Netty event loop để chờ dữ liệu. Đăng ký callback hoặc publisher bất đồng bộ; mọi công việc blocking phải chạy trên executor phù hợp và có giới hạn.

## 9. Cancellation phải hủy subscription

Client có thể ngừng nhận dữ liệu bất kỳ lúc nào. Phía server có thể dùng ServerCallStreamObserver để theo dõi cancellation:

~~~java
ServerCallStreamObserver<PriceUpdate> call =
    (ServerCallStreamObserver<PriceUpdate>) responseObserver;

AtomicBoolean closed = new AtomicBoolean();
PriceFeed.Subscription subscription =
    priceFeed.subscribe(request.getSymbol(), update -> {
        if (!closed.get() && !call.isCancelled()) {
            // Đưa update vào outbound queue có giới hạn.
        }
    });

call.setOnCancelHandler(() -> {
    closed.set(true);
    subscription.close();
});
~~~

Đoạn mã minh họa lifecycle và API ServerCallStreamObserver.setOnCancelHandler(). Trong implementation hoàn chỉnh, đăng ký cancellation cần được phối hợp với thời điểm tạo subscription để không bỏ lỡ trường hợp call bị cancel ngay khi setup. Khi nguồn dữ liệu hoàn tất hoặc lỗi, service cũng phải đóng subscription và gửi đúng một terminal signal.

Không chỉ kiểm tra call.isCancelled() mỗi khi event tới mà bỏ quên unregister listener. Nếu không hủy subscription, feed vẫn giữ callback và object của client sau khi RPC đã kết thúc.

## 10. Flow control và bounded buffer

Nguồn dữ liệu có thể phát nhanh hơn tốc độ client nhận. Nếu server cứ gọi onNext() và tích lũy vô hạn message chưa gửi, heap có thể tăng cho tới khi process quá tải.

Với gRPC Java, ServerCallStreamObserver.isReady() cho biết transport hiện có khả năng nhận thêm message mà không cần buffer quá nhiều. setOnReadyHandler() cho phép server tiếp tục drain khi call trở nên ready.

Một stream producer nên:

- Đưa update vào queue có giới hạn theo số message hoặc byte.
- Chỉ drain khi isReady() là true.
- Dừng drain khi queue rỗng hoặc transport không còn ready.
- Đăng ký on-ready handler để tiếp tục gửi khi transport sẵn sàng.
- Chọn chính sách khi queue đầy: drop/coalesce dữ liệu có thể thay thế, ghi vào log để replay, hoặc kết thúc stream bằng status phù hợp.

Client cũng có thể kiểm soát số response message được phép nhận trước khi yêu cầu thêm. Với async stub, cấu hình manual inbound flow control trong beforeStart:

~~~java
AtomicReference<ClientCallStreamObserver<WatchPricesRequest>> callRef =
    new AtomicReference<>();

stub.watchPrices(request, new ClientResponseObserver<>() {
    @Override
    public void beforeStart(
            ClientCallStreamObserver<WatchPricesRequest> call) {
        call.disableAutoRequestWithInitial(1);
        callRef.set(call);
    }

    @Override
    public void onNext(PriceUpdate update) {
        processAndPersist(update);
        callRef.get().request(1);
    }

    @Override
    public void onError(Throwable error) {
        handleStreamFailure(error);
    }

    @Override
    public void onCompleted() {
        markStreamComplete();
    }
});
~~~

Ví dụ yêu cầu thêm một message sau khi xử lý xong message hiện tại. Nếu xử lý bất đồng bộ, chỉ gọi request(1) sau khi worker đã hoàn tất hoặc đã nhận message vào một queue có giới hạn. Không yêu cầu thêm message trước khi có capacity, nếu không manual flow control mất ý nghĩa.

Không dùng unbounded queue. Với feed giá, có thể chỉ giữ giá mới nhất theo symbol nếu contract cho phép bỏ các intermediate update. Với audit/event stream, không được drop tùy tiện; cần durable log và cursor để consumer đọc lại.

Mọi lời gọi onNext, onError và onCompleted cho cùng observer phải được tuần tự hóa. Nếu feed gọi callback đồng thời từ nhiều thread, dùng serial executor hoặc cơ chế đồng bộ riêng cho từng stream.

## 11. Client nhận stream bằng async stub

Client dùng generated async stub và StreamObserver để nhận từng message:

~~~java
List<PriceUpdate> updates = new CopyOnWriteArrayList<>();
AtomicReference<Throwable> failure = new AtomicReference<>();
CountDownLatch terminal = new CountDownLatch(1);

MarketDataGrpc.MarketDataStub stub =
    MarketDataGrpc.newStub(channel)
        .withDeadlineAfter(30, TimeUnit.SECONDS);

stub.watchPrices(
    WatchPricesRequest.newBuilder()
        .setSymbol("ACME")
        .setIncludeSnapshot(true)
        .build(),
    new StreamObserver<>() {
        @Override
        public void onNext(PriceUpdate update) {
            updates.add(update);
        }

        @Override
        public void onError(Throwable error) {
            failure.set(error);
            terminal.countDown();
        }

        @Override
        public void onCompleted() {
            terminal.countDown();
        }
    });
~~~

Đây là ví dụ stream hữu hạn trong test. Feed liên tục có thể không gọi onCompleted() cho tới khi client hủy hoặc server kết thúc. Không chờ terminal latch vô hạn với subscription dài hạn; dùng cancellation, deadline và điều kiện dừng của ứng dụng.

Callback onNext() nên xử lý nhanh. Nếu phải ghi database hoặc gọi service khác, chuyển công việc sang bounded executor/queue; không block callback thread lâu và không tạo queue không giới hạn.

## 12. Hủy stream từ client

Để chủ động cancel một server-streaming call, client có thể dùng ClientResponseObserver và giữ ClientCallStreamObserver:

~~~java
AtomicReference<ClientCallStreamObserver<WatchPricesRequest>> callRef =
    new AtomicReference<>();
CountDownLatch firstUpdate = new CountDownLatch(1);

stub.watchPrices(
    WatchPricesRequest.newBuilder().setSymbol("ACME").build(),
    new ClientResponseObserver<>() {
        @Override
        public void beforeStart(
                ClientCallStreamObserver<WatchPricesRequest> call) {
            callRef.set(call);
        }

        @Override
        public void onNext(PriceUpdate update) {
            firstUpdate.countDown();
        }

        @Override
        public void onError(Throwable error) {}

        @Override
        public void onCompleted() {}
    });

if (firstUpdate.await(5, TimeUnit.SECONDS)) {
    callRef.get().cancel("client no longer needs feed", null);
}
~~~

Trong code production, kiểm tra reference trước khi cancel và xử lý trường hợp không nhận được message đầu tiên. Cancellation là tín hiệu chấm dứt call; phía server phải truyền tín hiệu đó tới feed subscription và worker liên quan.

Không coi việc đóng channel là cách duy nhất để dừng một subscription. Nếu channel được dùng cho nhiều RPC, cancel đúng call để không ảnh hưởng các RPC khác.

## 13. Deadline và thời gian sống của stream

gRPC deadline giới hạn thời gian sống của một RPC. Với server-streaming hữu hạn, đặt deadline theo thời gian xử lý mong đợi. Với subscription dài hạn, deadline hữu hạn vẫn cần được cân nhắc: khi hết deadline, call kết thúc và client phải mở call mới nếu còn muốn nhận dữ liệu.

Có thể thiết kế stream theo phiên có thời hạn, ví dụ 5 phút, sau đó client reconnect bằng cursor. Cách này giúp rotate connection, làm mới credential và tránh giữ stream vô hạn qua proxy/load balancer.

Không bỏ deadline chỉ vì stream được kỳ vọng chạy lâu. Nếu cần subscription dài hạn, xác định lease/session duration, reconnect policy, cursor và cách refresh authentication.

## 14. Heartbeat và keepalive

Hai cơ chế thường bị nhầm:

- **HTTP/2 keepalive ping** kiểm tra transport/connection còn hoạt động theo cấu hình client/server.
- **Application heartbeat message** là message trong Protobuf stream, cho biết feed hoặc application session vẫn tiến triển.

Keepalive không chứng minh dữ liệu nghiệp vụ còn mới. Một connection có thể sống nhưng source feed đã ngừng phát event. Ngược lại, không phải feed nào cũng cần heartbeat nếu không có yêu cầu phát hiện idle.

Nếu thêm heartbeat vào schema, định nghĩa rõ message heartbeat có sequence hay không, client có tính nó vào business progress không và server gửi theo chu kỳ nào. Tránh heartbeat quá dày làm tăng tải khi có nhiều subscription.

## 15. Reconnect và resume sau khi mất kết nối

Server streaming không tự replay message bị bỏ lỡ. Khi connection bị reset hoặc server restart, client nhận terminal error và cần mở RPC mới.

Để resume an toàn:

1. Mỗi update có sequence/event ID ổn định.
2. Client lưu cursor cuối cùng đã xử lý thành công.
3. Khi reconnect, client gửi resume_after_sequence hoặc cursor token.
4. Server đọc lại event sau cursor từ nguồn có retention.
5. Client deduplicate nếu một update được gửi lại sau khi client crash giữa xử lý và lưu cursor.
6. Nếu cursor đã hết retention, server trả trạng thái yêu cầu snapshot/resync.

Cursor nên gắn với partition/stream/tenant phù hợp và không cho phép client đọc dữ liệu ngoài quyền. Không dùng một sequence toàn cục nếu các symbol hoặc tenant có ordering độc lập.

Nếu source không lưu event, chỉ có thể tiếp tục từ trạng thái mới nhất hoặc snapshot. Hợp đồng cần nói rõ dữ liệu trung gian có thể mất.

## 16. Ordering và consistency

Server streaming gửi message theo thứ tự server gọi onNext() trên call. Nhưng thứ tự nghiệp vụ còn phụ thuộc nguồn dữ liệu và concurrency:

- Nhiều producer có thể phát event đồng thời.
- Event từ nhiều partition không có một total order tự nhiên.
- Timestamp không bảo đảm thứ tự khi đồng hồ lệch.
- Client xử lý song song có thể hoàn tất side effect khác thứ tự nhận.

Nếu cần thứ tự theo symbol/order/device, gắn sequence theo aggregate và tuần tự hóa publish trong phạm vi đó. Client kiểm tra sequence tăng, phát hiện gap và yêu cầu resync. Định nghĩa rõ update là snapshot mới nhất hay event delta; với delta, bỏ một message có thể khiến state sai.

## 17. Authentication và authorization cho subscription

Subscription có thể tồn tại lâu hơn một request unary. Khi mở stream, server cần xác thực metadata/credential và kiểm tra quyền truy cập symbol, tenant hoặc device được yêu cầu.

Các điểm cần thiết:

- Không tin filter hoặc tenant ID chỉ do client gửi.
- Xác minh quyền cho resource trong request.
- Giới hạn số stream đồng thời theo principal/tenant.
- Xem xét credential expiry trong stream dài hạn; reconnect có thể cần token mới.
- Hủy stream khi quyền bị thu hồi nếu hệ thống yêu cầu enforcement tức thời.
- Không ghi bearer token vào log.

Metadata được kiểm tra khi call bắt đầu không tự động refresh giữa stream. Nếu policy yêu cầu cập nhật quyền ngay, cần cơ chế revoke signal hoặc giới hạn session duration.

## 18. Scale, load balancing và connection draining

Một stream dài hạn thường được gắn với một backend đã được chọn khi RPC bắt đầu. Load balancer không tự di chuyển một stream đang mở sang instance khác khi backend quá tải hoặc bị drain.

Điều này ảnh hưởng:

- Một backend có thể giữ nhiều subscription trong thời gian dài.
- Phân phối số RPC không đồng nghĩa phân phối đều số subscriber hoặc message rate.
- Khi deploy, server cần graceful shutdown và chính sách kết thúc stream.
- Client cần reconnect/resume khi backend drain hoặc restart.
- Proxy/load balancer cần timeout và HTTP/2 support phù hợp với thời gian sống của stream.

Theo dõi active stream count, subscriber theo backend, outbound queue bytes, message rate và thời gian sống của stream. Khi rolling deploy, báo client reconnect bằng status phù hợp và cursor để tránh mất dữ liệu.

## 19. Kiểm thử server streaming qua Spring

Integration test cần gọi server qua generated stub và gRPC transport đang chạy. Test nên xác minh:

1. Client gửi subscription với filter hợp lệ.
2. Server phát snapshot hoặc các update theo contract.
3. Message có sequence/payload đúng thứ tự.
4. Client nhận lỗi với status phù hợp khi filter hoặc quyền không hợp lệ.
5. Cancel từ client làm server hủy subscription.
6. Deadline kết thúc stream trong thời gian hữu hạn.
7. Reconnect bằng cursor không bỏ sót hoặc nhân đôi side effect.
8. Channel được đóng và server theo đúng Spring lifecycle.

Dùng CountDownLatch, queue và timeout hữu hạn để đồng bộ callback. Không dùng Thread.sleep() để đợi event. Test feed liên tục nên điều khiển được nguồn dữ liệu giả, phát event theo lệnh và xác nhận observer nhận được đúng số message.

## 20. Observability cho stream liên tục

Một RPC stream có thể kéo dài nhiều phút, vì vậy metric theo call đơn thuần chưa đủ. Nên theo dõi:

- Active stream count theo service/method/backend.
- Stream duration và số lần disconnect/cancel.
- Message rate, bytes sent và queue depth.
- Số lần reconnect, resume success và cursor expired.
- Sequence gap, duplicate và resync count.
- Deadline exceeded, RESOURCE_EXHAUSTED và UNAVAILABLE.
- Subscriber lag so với event source.

Dùng trace/correlation ID để nối quá trình subscribe và reconnect. Không dùng symbol, user ID hoặc stream ID có cardinality cao làm metric label nếu số lượng không giới hạn; lưu trong log/trace có kiểm soát.

## 21. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng polling quá dày cho feed thay đổi liên tục | Request thừa và cập nhật trễ giữa hai lần hỏi | Cân nhắc server streaming hoặc SSE. |
| Dùng server streaming cho client cần gửi điều khiển liên tục | Không có chiều client-to-server sau request đầu | Dùng bidi hoặc RPC điều khiển riêng. |
| Coi stream là durable event log | Client offline bị mất update | Dùng cursor với event store hoặc broker retention. |
| Không giới hạn outbound queue | Heap tăng khi client chậm | Bounded buffer và chính sách overflow. |
| Gọi onNext từ nhiều thread không đồng bộ | Race và sai thứ tự observer | Tuần tự hóa callback theo stream. |
| Không hủy subscription khi client cancel | Listener/worker bị rò rỉ | Đăng ký on-cancel cleanup. |
| Stream vô hạn không deadline/session policy | Giữ connection và credential quá lâu | Session duration, reconnect và resume. |
| Chỉ dùng keepalive để kiểm tra feed | Transport sống nhưng dữ liệu đã stale | Theo dõi application heartbeat/source progress. |
| Không có sequence/cursor | Không phát hiện gap hoặc duplicate sau reconnect | Event ID/sequence và resume contract. |
| Giả định load balancer di chuyển stream | Backend drain làm call bị ngắt | Client reconnect tới backend mới. |

## 22. Ma trận quyết định

| Câu hỏi | Nếu câu trả lời là “có” | Hướng cân nhắc |
| --- | --- | --- |
| Dữ liệu chủ yếu đi từ server tới client? | Có | Server streaming là ứng viên tốt. |
| Client cần gửi message liên tục trong cùng session? | Có | Bidirectional streaming. |
| Client là browser và chỉ cần event một chiều? | Có | SSE hoặc gRPC-Web tùy contract. |
| Client offline cần replay event bền vững? | Có | Broker/event log với cursor. |
| Chỉ cần đọc trạng thái mới nhất với tần suất thấp? | Có | Unary RPC hoặc polling có thể đơn giản hơn. |
| Feed có thể phát nhanh hơn consumer? | Có | Cần flow control và bounded buffer. |
| Cần thứ tự/gap detection sau reconnect? | Có | Sequence/cursor và resync semantics. |

Chọn server streaming khi lợi ích của push liên tục lớn hơn chi phí giữ stream, vận hành connection dài hạn và xây dựng reconnect/resume.

## 23. Bài tập thực hành

Thiết kế MarketData.WatchPrices trong Spring gRPC:

1. Định nghĩa request theo symbol và cursor, response có sequence, price và timestamp.
2. Implement server service đăng ký feed và phát update qua response observer.
3. Dùng ServerCallStreamObserver để nhận cancellation và xử lý readiness.
4. Đặt outbound queue có giới hạn và xác định policy khi client chậm.
5. Viết async client nhận update, kiểm tra sequence và cancel stream.
6. Đặt deadline/session duration và reconnect bằng cursor sau khi server restart.
7. Kiểm thử snapshot-to-live không có gap.
8. Kiểm tra authorization, giới hạn subscriber và cleanup subscription.
9. Đo active stream, message rate, queue depth, disconnect và resume success.

**Tiêu chí hoàn thành:** client nhận được nhiều update theo contract; server kiểm soát buffer/flow control; cancellation giải phóng subscription; reconnect phát hiện gap/duplicate và không giả định stream tự replay.

## 24. Ghi nhớ

- Server streaming dùng một request để mở luồng nhiều response theo hướng server-to-client.
- Phù hợp feed liên tục, tiến độ, telemetry và subscription khi client cần nhận update ngay.
- Polling, SSE, WebSocket, bidi gRPC và broker giải quyết các kiểu tương tác khác nhau; chọn theo client và durability.
- Protobuf contract nên có sequence/event ID, cursor và semantics snapshot/resume rõ.
- Snapshot và live subscription phải chuyển tiếp không tạo khoảng trống.
- ServerCallStreamObserver.isReady() và on-ready handler hỗ trợ flow control; outbound buffer phải có giới hạn.
- Cancellation phải hủy feed subscription và worker liên quan.
- Deadline/session duration hữu hạn giúp rotate connection và credential; reconnect/resume cần cursor.
- Stream dài hạn bị gắn với backend đã chọn; load balancer không tự di chuyển stream đang mở.
- Kiểm thử qua generated stub, đồng bộ callback bằng latch/queue và xác minh cleanup.

Chọn server streaming cho dữ liệu liên tục khi client chủ yếu nhận nhiều cập nhật từ server qua một subscription; kết hợp flow control, cancellation, cursor và reconnect để stream vận hành ổn định trong hệ Spring gRPC.

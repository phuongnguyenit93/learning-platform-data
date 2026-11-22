# Hủy, lỗi, đóng phiên và giải phóng tài nguyên trong Spring WebFlux WebSocket

## 1. Vì sao lifecycle của WebSocket cần được quản lý rõ ràng?

WebSocket giữ một kết nối hai chiều mở trong thời gian dài. Một phiên có thể nhận và gửi hàng nghìn message, đồng thời giữ subscription tới broker, timer, hàng đợi, cache theo phiên, buffer hoặc tài nguyên bên ngoài. Khi client đóng tab, mất mạng, gửi dữ liệu không hợp lệ, server gặp lỗi hoặc ứng dụng bắt đầu shutdown, tất cả hoạt động gắn với phiên phải kết thúc đúng cách.

Trong Spring WebFlux, lifecycle này được biểu diễn bằng Reactive Streams:

- Inbound: WebSocketSession.receive() trả về Flux<WebSocketMessage>.
- Outbound: WebSocketSession.send(Publisher<WebSocketMessage>) trả về Mono<Void>.
- Handler: WebSocketHandler.handle(WebSocketSession) trả về Mono<Void> biểu diễn thời điểm xử lý phiên hoàn tất.
- Close: WebSocketSession.close(CloseStatus) trả về Mono<Void> để gửi WebSocket close frame.
- Close status: WebSocketSession.closeStatus() trả về Mono<CloseStatus>, có thể hoàn tất rỗng nếu transport kết thúc mà không có close status.

**Nguyên tắc cốt lõi:** phải nối inbound, outbound và tài nguyên phiên vào cùng một reactive lifecycle. Khi một phía kết thúc, phía còn lại và các tài nguyên phụ thuộc phải được hủy hoặc đóng theo chính sách đã chọn.

Không gọi subscribe() riêng cho các luồng trong handler, không dùng block() để chờ message và không dựa vào một biến boolean kiểm tra connection còn mở để điều phối lifecycle. Hãy để completion, error và cancellation truyền qua publisher.

## 2. WebSocket session có hai luồng độc lập

Spring WebFlux mô hình hóa một phiên bằng một luồng nhận và một luồng gửi:

~~~text
                   WebSocketSession
                          |
             +------------+------------+
             |                         |
             v                         v
      receive(): Flux              send(Publisher)
             |                         |
             v                         v
      Client -> Server             Server -> Client
             |                         |
             +------------+------------+
                          |
                          v
                 handle(): Mono<Void>
                          |
                          v
             complete / error / cancel
                          |
                          v
             close và cleanup tài nguyên
~~~

receive() phát các message đến từ client. Luồng này hoàn tất khi kết nối đóng và có thể kết thúc bằng lỗi nếu transport gặp sự cố.

send(...) nhận một publisher các message đi ra, ghi chúng lên kết nối và hoàn tất khi publisher nguồn hoàn tất cũng như thao tác ghi hoàn tất. Nếu publisher nguồn bị cancel, thao tác gửi cũng dừng theo.

Handler phải compose hai luồng thành một Mono<Void> thống nhất. Tùy nghiệp vụ, phiên có thể kết thúc khi inbound kết thúc, outbound kết thúc, một nhánh phát lỗi hoặc ứng dụng chủ động gọi session.close(...).

### 2.1. Echo handler đơn giản

Nếu mọi message nhận được đều tạo đúng một message phản hồi, có thể ghép trực tiếp inbound với outbound:

~~~java
class EchoHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> replies = session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> session.textMessage("echo: " + text));

        return session.send(replies);
    }
}
~~~

Khi client gửi một text message, handler tạo response tương ứng. Khi inbound hoàn tất, publisher phản hồi cũng hoàn tất; khi việc ghi thất bại, lỗi được truyền qua send và handle.

Đây là mẫu phù hợp khi outbound chỉ phụ thuộc inbound. Khi server còn có một feed riêng, chẳng hạn event từ broker hoặc thông báo định kỳ, cần compose thêm feed đó và xác định rõ điều gì xảy ra khi inbound đóng.

## 3. Ba terminal signal cần phân biệt

Reactive Streams có ba kết quả kết thúc chính:

| Signal | Ý nghĩa | Việc cần làm |
| --- | --- | --- |
| ON_COMPLETE | Publisher kết thúc bình thường | Hoàn tất nhánh phụ thuộc và đóng tài nguyên |
| ON_ERROR | Publisher kết thúc do lỗi | Ghi nhận lỗi, map close status phù hợp, cleanup |
| CANCEL | Subscriber hủy subscription | Dừng nguồn, hủy tác vụ và giải phóng tài nguyên |

Ba signal này không tương đương nhau.

Ví dụ:

- Client gửi close frame hợp lệ: inbound thường hoàn tất bình thường.
- Client mất mạng đột ngột: adapter có thể phát error hoặc completion tùy transport và thời điểm phát hiện.
- Server shutdown hoặc một nhánh xử lý khác kết thúc phiên: outbound có thể nhận cancellation.
- Handler bị hủy từ bên ngoài: toàn bộ subscription phía dưới phải nhận cancellation.

Không giả định mọi client disconnect luôn được biểu diễn thành CANCEL hoặc luôn có một exception cụ thể. Hãy xử lý terminal signal tổng quát và dùng closeStatus() để đọc close code khi transport có cung cấp.

## 4. Kết hợp inbound và outbound đúng lifecycle

Có hai cấu trúc thường gặp.

### 4.1. Một outbound stream được tạo từ inbound

Nếu mỗi message vào tạo ra một message ra, dùng một pipeline duy nhất:

~~~java
Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> output = session.receive()
        .concatMap(message ->
            process(message.getPayloadAsText())
                .map(session::textMessage)
        );

    return session.send(output);
}
~~~

concatMap xử lý tuần tự và giữ thứ tự message. Nếu công việc cho từng message độc lập và có thể chạy song song, có thể dùng flatMap với concurrency giới hạn. Không chọn concurrency vô hạn cho message đến từ client không tin cậy.

### 4.2. Inbound và outbound có nguồn riêng

Một phiên chat hoặc dashboard có thể vừa nhận lệnh client vừa đẩy event từ server:

~~~java
Mono<Void> input = session.receive()
    .concatMap(message -> processCommand(message.getPayloadAsText()))
    .then();

Flux<WebSocketMessage> serverEvents =
    eventService.events(session.getId())
        .map(session::textMessage);

Mono<Void> output = session.send(serverEvents);
~~~

Hai publisher cần được kết hợp thành một lifecycle. Nếu inbound kết thúc mà serverEvents vẫn vô hạn, chỉ chờ cả hai hoàn tất sẽ giữ subscription outbound tiếp tục chạy. Nếu chính sách ứng dụng là “một nhánh dừng thì phiên kết thúc”, có thể dùng Mono.firstWithSignal:

~~~java
return Mono.firstWithSignal(input, output);
~~~

firstWithSignal phát terminal signal đầu tiên trong các Mono cạnh tranh: complete, empty completion hoặc error. Khi một nhánh kết thúc, nhánh còn lại bị cancel. Đây là lựa chọn rõ ràng khi inbound close phải hủy feed outbound, hoặc outbound kết thúc thì không cần tiếp tục nhận message.

Spring cũng minh họa cách compose inbound và outbound độc lập bằng input.and(output) trong tài liệu WebFlux WebSocket. Hãy chọn toán tử theo semantics mong muốn của ứng dụng; cần hiểu nhánh nào được phép sống tiếp sau khi nhánh kia hoàn tất và bảo đảm cancellation truyền đến upstream.

### 4.3. Không gửi bằng nhiều subscription độc lập

Tránh gọi session.send nhiều lần cho cùng một phiên hoặc tự subscribe nhiều publisher outbound:

~~~java
// Không nên: hai writer độc lập cùng điều khiển một session.
session.send(replies).subscribe();
session.send(notifications).subscribe();
return session.receive().then();
~~~

Thay vào đó, hợp nhất các nguồn message và gọi send một lần:

~~~java
Flux<WebSocketMessage> outbound = Flux.merge(
    replies,
    notifications
);

return session.send(outbound);
~~~

merge cho phép nhiều nguồn phát đồng thời và có thể xen kẽ message giữa các nguồn. Nếu cần thứ tự toàn cục nghiêm ngặt, hãy đưa message vào một hàng đợi có thứ tự hoặc dùng cách compose tuần tự phù hợp. Dù chọn cách nào, chỉ có một publisher outbound điều khiển việc ghi session.

## 5. Cancellation phải truyền tới nguồn dữ liệu

Giả sử mỗi WebSocket session đăng ký một subscription tới Redis Pub/Sub. Khi client rời đi, chỉ đóng socket là chưa đủ. Subscription tới Redis vẫn có thể tồn tại và tiếp tục nhận message nếu nó không nằm trong cùng reactive chain.

Luồng đúng:

~~~text
Client disconnect
       |
       v
session.receive() complete/error
       |
       v
input lifecycle terminates
       |
       v
combined handler terminates
       |
       v
session.send publisher is cancelled
       |
       v
event feed is cancelled
       |
       v
broker subscription is closed
       |
       v
session registry entry is removed
~~~

Khi cancellation truyền đúng, upstream có cơ hội dừng công việc và giải phóng tài nguyên. Nếu một service tự gọi subscribe() rồi giữ subscription trong một map toàn cục mà không liên kết với lifecycle của session, cancellation của WebSocket không tự động hủy subscription đó.

Hãy kiểm tra các nguồn được tạo cho từng session:

- Message broker subscription.
- Database change stream hoặc cursor.
- Timer và scheduled task.
- Sink hoặc queue theo session.
- File/channel hoặc stream dữ liệu.
- Tác vụ xử lý message bất đồng bộ.
- Entry trong registry lưu các session đang hoạt động.

## 6. Dùng usingWhen để mở và đóng tài nguyên bất đồng bộ

doFinally phù hợp để ghi metric hoặc thực hiện cleanup đồng bộ, ngắn. Nếu việc đóng tài nguyên trả về một publisher, dùng Flux.usingWhen hoặc Mono.usingWhen.

usingWhen quản lý resource theo ba đường kết thúc:

1. Resource closure hoàn tất bình thường.
2. Resource closure phát lỗi.
3. Downstream cancel.

Ví dụ khung:

~~~java
Flux<String> messages = Flux.usingWhen(
    subscriptionService.open(sessionId),
    subscription -> subscription.messages(),
    subscription -> subscription.close(),
    (subscription, error) -> subscription.close(),
    subscription -> subscription.close()
);
~~~

Tham số thứ hai tạo publisher sử dụng resource. Ba callback cuối thực hiện cleanup tương ứng với complete, error và cancel.

Đây là cách phù hợp cho broker subscription có thao tác unsubscribe bất đồng bộ:

- Mở subscription khi WebSocket bắt đầu dùng feed.
- Phát message từ subscription.
- Khi client đóng hoặc handler bị hủy, gọi close/unsubscribe.
- Khi feed lỗi, vẫn gọi cleanup trước khi kết thúc luồng.
- Khi feed hoàn tất bình thường, cũng đóng resource.

Đặt toàn bộ công việc cần resource còn mở bên trong callback resource closure. Đừng lấy resource ra ngoài rồi tiếp tục dùng nó sau khi usingWhen đã kết thúc.

## 7. doFinally, doOnCancel và doOnError

Các operator quan sát lifecycle có phạm vi khác nhau:

| Operator | Khi chạy | Dùng cho |
| --- | --- | --- |
| doOnComplete | Complete | Ghi nhận hoàn tất bình thường |
| doOnError | Error | Log hoặc tăng metric lỗi |
| doOnCancel | Cancel | Ghi nhận subscription bị hủy |
| doFinally | Complete, error hoặc cancel | Log terminal signal, metric tổng quát |

Ví dụ:

~~~java
Mono<Void> lifecycle = Mono.firstWithSignal(input, output)
    .doOnError(error ->
        log.error("WebSocket session failed: {}", session.getId(), error)
    )
    .doFinally(signal ->
        log.info(
            "WebSocket session {} terminated with {}",
            session.getId(),
            signal
        )
    );
~~~

doFinally nhận SignalType. Nó phù hợp để ghi nhận lifecycle, nhưng callback là synchronous và không phải nơi lý tưởng để chờ một thao tác đóng tài nguyên bất đồng bộ.

Nếu cần cleanup bất đồng bộ, dùng usingWhen. Nếu có một Disposable đồng bộ như timer riêng, có thể gọi dispose() trong callback cleanup và bảo đảm callback đó chạy trên cả complete, error lẫn cancel.

Không chỉ dùng doOnTerminate để giải phóng tài nguyên vì nó không bao gồm cancellation.

## 8. Đóng WebSocket session có chủ đích

Để chủ động đóng một phiên, gọi:

~~~java
session.close(CloseStatus.NORMAL);
~~~

Method này trả về Mono<Void>. Phải compose publisher đó vào pipeline để close frame thực sự được gửi và completion/error được quan sát:

~~~java
return session.receive()
    .takeUntil(message ->
        "bye".equals(message.getPayloadAsText())
    )
    .then(session.close(CloseStatus.NORMAL));
~~~

Khi client gửi message bye, takeUntil bao gồm message kích hoạt rồi hoàn tất luồng. Sau đó handler gọi close với status bình thường.

Không gọi session.close(...) rồi bỏ publisher đi. Việc tạo một Mono không có nghĩa close frame đã được gửi; thao tác chỉ chạy khi publisher được subscribe.

### 8.1. Close handshake

WebSocket close là một handshake ở tầng WebSocket:

1. Một phía gửi Close control frame cùng close status.
2. Phía kia phản hồi bằng Close frame.
3. Kết nối được đóng.

HTTP status 101 chỉ là status của handshake nâng cấp HTTP sang WebSocket. Nó không phải close status của phiên WebSocket.

Khi close handshake bắt đầu, không tiếp tục gửi message nghiệp vụ như thể session vẫn hoạt động. Hãy dừng các publisher gửi message và cleanup tài nguyên gắn với session.

### 8.2. Đọc close status

~~~java
return session.closeStatus()
    .doOnNext(status ->
        log.info(
            "Session {} closed with code {} and reason {}",
            session.getId(),
            status.getCode(),
            status.getReason()
        )
    )
    .then();
~~~

closeStatus() cung cấp status đóng do local hoặc remote endpoint tạo ra. Publisher có thể hoàn tất rỗng nếu kết nối kết thúc mà không có close status, ví dụ transport bị mất đột ngột.

Không dựa vào close status để quyết định có cleanup hay không. Cleanup vẫn phải chạy khi publisher complete, error hoặc cancel.

## 9. Chọn CloseStatus phù hợp

Spring cung cấp các hằng CloseStatus cho các trường hợp phổ biến:

| Code | Spring constant | Ý nghĩa |
| --- | --- | --- |
| 1000 | NORMAL | Đóng bình thường |
| 1002 | PROTOCOL_ERROR | Lỗi protocol |
| 1003 | NOT_ACCEPTABLE | Không chấp nhận loại dữ liệu nhận được |
| 1008 | POLICY_VIOLATION | Message vi phạm policy |
| 1009 | TOO_BIG_TO_PROCESS | Message quá lớn |
| 1011 | SERVER_ERROR | Server gặp lỗi không mong đợi |
| 1012 | SERVICE_RESTARTED | Service đang restart |
| 1013 | SERVICE_OVERLOAD | Service quá tải |

Ví dụ:

~~~java
return session.close(CloseStatus.POLICY_VIOLATION);
~~~

Các mã 1005, 1006 và 1015 là giá trị dành riêng, không được gửi như status code trong Close control frame. 1006 thường được dùng để biểu diễn việc kết nối đóng bất thường mà không nhận được close frame; không chủ động gọi close với mã này.

Chọn close code theo nguyên nhân có thể giúp client quyết định có nên reconnect hay hiển thị lỗi. Không đưa stack trace, token, dữ liệu cá nhân hoặc chi tiết nội bộ vào reason string.

## 10. Map lỗi ứng dụng thành close status

Lỗi xảy ra khi xử lý message có thể được map thành close status phù hợp.

Ví dụ:

~~~java
return processMessages(session)
    .onErrorResume(
        InvalidClientMessageException.class,
        error -> session.close(CloseStatus.POLICY_VIOLATION)
    )
    .onErrorResume(
        error -> session.close(CloseStatus.SERVER_ERROR)
    );
~~~

Một policy đơn giản:

- Message vi phạm quy tắc nghiệp vụ: 1008.
- Payload vượt giới hạn: 1009.
- Lỗi protocol hoặc message type không hợp lệ: 1002 hoặc 1003 tùy tình huống.
- Lỗi không mong đợi trong server: 1011.
- Server đang quá tải: 1013 nếu ứng dụng có chính sách từ chối phù hợp.

Không map tất cả lỗi thành 1000. Đóng bình thường có thể khiến client hiểu rằng phiên kết thúc thành công và không cần hiển thị lỗi.

Cũng không gửi exception message nguyên bản cho client. Log chi tiết ở server; phía client chỉ cần close code và reason an toàn, ngắn gọn.

### 10.1. Không nuốt lỗi bằng Mono.empty

Tránh:

~~~java
return processMessages(session)
    .onErrorResume(error -> Mono.empty());
~~~

Cách này biến lỗi thành completion bình thường. Client có thể nhận close behavior không phản ánh nguyên nhân và metric error bị mất nếu không ghi nhận trước.

Nếu cần phục hồi một lỗi nghiệp vụ có thể tiếp tục phiên, hãy xử lý rõ lỗi đó thành một message protocol có cấu trúc. Nếu lỗi khiến session không thể tiếp tục, map sang close status rồi kết thúc.

### 10.2. Phân biệt lỗi ứng dụng và lỗi transport

| Loại lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Client gửi sai dữ liệu | JSON sai schema, command không được phép | Close 1008 hoặc phản hồi lỗi theo protocol |
| Message quá lớn | Vượt giới hạn nghiệp vụ | Close 1009 hoặc giới hạn frame phù hợp |
| Lỗi xử lý nội bộ | Null pointer, bug, service lỗi | Log server-side và close 1011 |
| Broker/database lỗi | Feed không còn hoạt động | Dừng feed, log, close hoặc chuyển sang degraded state theo policy |
| Client mất mạng | TCP reset, transport error | Cleanup; close status có thể không có |
| Client đóng bình thường | Close frame hợp lệ | Hoàn tất và cleanup bình thường |

Không coi mọi error signal là client disconnect. Lỗi có thể đến từ validation, serialization, broker, transport hoặc code của ứng dụng.

## 11. Cleanup tài nguyên: mỗi loại có một cách đóng

Một WebSocket session thường giữ nhiều loại resource:

| Resource | Cách cleanup |
| --- | --- |
| Reactor subscription | Truyền cancellation về upstream |
| Broker subscription | Gọi unsubscribe/close bất đồng bộ |
| Timer hoặc Disposable | Gọi dispose |
| Session registry entry | Remove đúng session ID |
| Database cursor | Close/cancel query |
| File/channel | Đóng channel |
| Pooled DataBuffer | Release đúng ownership |
| Sink theo session | Complete/error và bỏ reference |
| Queue theo session | Ngừng producer và giải phóng queue |

Cleanup nên có các tính chất:

1. **Idempotent:** gọi nhiều lần không làm hỏng trạng thái.
2. **Bao phủ mọi terminal path:** complete, error và cancel.
3. **Có thứ tự:** dừng producer trước khi bỏ registry hoặc đóng resource mà producer còn dùng.
4. **Không chặn event loop:** thao tác blocking phải được chuyển sang scheduler phù hợp.
5. **Không giữ reference:** bỏ map entry, listener và callback sau khi phiên kết thúc.
6. **Có quan sát:** log/metric cho số phiên mở, đóng, lỗi và thời gian sống.

Không dùng một static map để giữ resource vĩnh viễn. Nếu cần registry cho session đang hoạt động, hãy remove entry trong callback cleanup của resource.

## 12. DataBuffer và WebSocketMessage: tránh memory leak

Trên một số runtime như Reactor Netty, buffer có thể được pooled và reference-counted. Khi message được nhận, framework quản lý vòng đời buffer. Nếu ứng dụng giữ message để xử lý sau một asynchronous boundary, buffer có thể đã được release trước khi code bất đồng bộ đọc xong.

### 12.1. Đọc payload đồng bộ trước khi chuyển sang async

Nếu chỉ cần String, hãy chuyển payload ngay trong pipeline:

~~~java
return session.receive()
    .map(WebSocketMessage::getPayloadAsText)
    .concatMap(text -> messageService.process(text));
~~~

String đã được tạo trước khi chuyển sang asynchronous operation, vì vậy không cần giữ lại WebSocketMessage chỉ để đọc text sau đó.

### 12.2. Giữ message khi cần dùng sau ranh giới async

Nếu phải chuyển chính message hoặc payload buffer sang công việc bất đồng bộ, dùng retain và release đúng lifecycle:

~~~java
return session.receive()
    .concatMap(message -> {
        message.retain();

        return messageService.processMessage(message)
            .doFinally(signal -> message.release());
    })
    .then();
~~~

retain() tăng reference count khi runtime dùng pooled buffer. release() giảm reference count sau khi công việc kết thúc. doFinally bao phủ complete, error và cancel của publisher xử lý message.

Chỉ retain khi thực sự cần giữ buffer. Không release một message mà ứng dụng chưa retain hoặc không sở hữu. Không release hai lần. Không giữ buffer trong cache hoặc queue lâu dài mà không có một ownership policy rõ ràng.

### 12.3. Buffer bị loại bỏ trong operator

Nếu tự viết pipeline xử lý DataBuffer và dùng các operator có thể prefetch hoặc discard item như filter, skip hoặc một số operator buffering, cần xử lý buffer bị loại bỏ bằng cơ chế discard phù hợp, ví dụ doOnDiscard(DataBuffer.class, DataBufferUtils::release) trong trường hợp ứng dụng sở hữu buffer đó.

Với message cấp cao như String hoặc DTO được codec decode, hãy để framework quản lý buffer. Chỉ đi xuống tầng DataBuffer khi có yêu cầu thực sự về byte-level processing.

## 13. Backpressure và xử lý message tuần tự

WebSocket có thể nhận message nhanh hơn khả năng xử lý của ứng dụng. Nếu handler tạo nhiều công việc bất đồng bộ đồng thời mà không giới hạn, queue và bộ nhớ có thể tăng liên tục.

concatMap xử lý từng message theo thứ tự:

~~~java
Mono<Void> input = session.receive()
    .concatMap(message ->
        commandService.execute(message.getPayloadAsText())
    )
    .then();
~~~

Dùng flatMap khi các message độc lập và cho phép xử lý đồng thời:

~~~java
Mono<Void> input = session.receive()
    .flatMap(
        message -> commandService.execute(message.getPayloadAsText()),
        8
    )
    .then();
~~~

Tham số concurrency giới hạn số công việc đang chạy cùng lúc. Nếu thứ tự phản hồi phải giống thứ tự request, dùng concatMap hoặc gắn sequence ID và sắp xếp ở tầng protocol.

Không tạo queue không giới hạn cho từng session. Nếu client gửi quá nhanh, có thể cần:

- Giới hạn message size.
- Giới hạn số request đang xử lý.
- Áp dụng rate limit theo user/session.
- Từ chối command vượt quota.
- Đóng phiên khi vi phạm policy.
- Đo queue depth và processing latency.

## 14. Close session không thay thế cleanup

Hai hành động này khác nhau:

- session.close(CloseStatus) đóng WebSocket protocol connection.
- Cleanup resource đóng broker subscription, timer, database cursor, queue, buffer và registry entry.

Một session có thể đã đóng nhưng broker subscription vẫn còn nếu nó được tạo ngoài reactive chain. Ngược lại, resource có thể được cleanup khi handler bị cancel ngay cả khi không gửi được close frame vì client đã mất mạng.

Vì vậy, cần cả hai cơ chế:

1. Dùng close status khi connection còn đủ khả năng thực hiện close handshake.
2. Dùng reactive lifecycle để giải phóng tài nguyên bất kể close handshake có thành công hay không.

Đừng đặt toàn bộ cleanup trong một nhánh chỉ chạy khi gọi close bình thường.

## 15. Graceful shutdown khi ứng dụng dừng

Khi server chuẩn bị shutdown, các WebSocket session đang mở có thể cần được đóng có kiểm soát.

Một quy trình thường gặp:

1. Ngừng nhận session mới hoặc đánh dấu service đang shutdown.
2. Từ chối command mới hoặc trả thông báo service đang dừng.
3. Gửi close status phù hợp, thường dùng 1012 khi service restart.
4. Chờ trong một khoảng grace period có giới hạn.
5. Hủy các session còn lại khi hết thời gian.
6. Cleanup broker subscription, timer và registry.
7. Để server hoàn tất shutdown.

Không giữ ứng dụng shutdown vô thời hạn chỉ vì một WebSocket client không phản hồi close handshake. Cần timeout cho giai đoạn graceful shutdown và có metric số session còn lại.

Nếu có session registry, registry nên cung cấp cách lấy snapshot các session hiện hoạt và yêu cầu close một cách reactive. Tránh lặp qua một mutable map không đồng bộ trong khi các session khác đang được tạo hoặc đóng.

## 16. Logging và metrics cho session lifecycle

Nên log các sự kiện lifecycle, không log toàn bộ payload message ở production nếu payload có thể chứa dữ liệu nhạy cảm.

Các metric hữu ích:

| Metric | Mục đích |
| --- | --- |
| websocket_active_sessions | Số phiên đang mở |
| websocket_open_total | Tổng phiên đã mở |
| websocket_close_total | Tổng phiên đã đóng |
| websocket_error_total | Tổng phiên kết thúc do lỗi |
| websocket_cancel_total | Tổng phiên bị cancel |
| websocket_close_code_total | Số lần đóng theo close code |
| websocket_session_duration | Thời gian sống của phiên |
| websocket_inbound_messages_total | Số message nhận |
| websocket_outbound_messages_total | Số message gửi |
| websocket_feed_active | Số subscription feed đang hoạt động |

Log tối thiểu nên có session ID, user ID đã được phép log, close code nếu có, terminal signal, thời gian sống và loại lỗi. Không log token, cookie, raw authentication header hoặc payload nhạy cảm.

Khi closeStatus() empty, ghi nhận là “no close status received” thay vì tự gán 1000 hoặc 1006 vào close frame đã gửi. Đây là trạng thái quan sát, không phải status do server chủ động phát.

## 17. Java 17+ Spring Boot WebFlux demo hoàn chỉnh

Demo dưới đây có các behavior:

- Endpoint WebSocket tại /ws/chat.
- Client gửi text message, server echo lại.
- Server đồng thời phát event định kỳ.
- Client gửi /close để yêu cầu đóng bình thường.
- Message vượt giới hạn bị đóng với policy violation.
- Feed riêng của mỗi session được quản lý bằng usingWhen.
- Feed được cleanup khi complete, error hoặc cancel.
- Handler compose inbound và outbound bằng Mono.firstWithSignal.

### 17.1. Cấu trúc dự án

~~~text
webflux-websocket-lifecycle/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      WebSocketConfig.java
      ChatWebSocketHandler.java
      PolicyViolationException.java
      SessionFeed.java
      SessionFeedService.java
    test/java/demo/
      SessionFeedServiceTest.java
~~~

### 17.2. build.gradle

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

Spring Boot quản lý phiên bản Spring Framework và Reactor tương thích. Demo dùng Java 17 và WebFlux starter để chạy trên Reactor Netty.

### 17.3. DemoApplication.java

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

### 17.4. PolicyViolationException.java

~~~java
package demo;

public class PolicyViolationException extends RuntimeException {
    public PolicyViolationException(String message) {
        super(message);
    }
}
~~~

Exception này biểu diễn message không đáp ứng policy của endpoint, ví dụ payload vượt giới hạn ký tự. Handler map lỗi sang close status 1008.

### 17.5. SessionFeed.java

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

final class SessionFeed {
    private final String sessionId;
    private final Sinks.Empty<Void> closed = Sinks.empty();
    private final AtomicBoolean closeStarted = new AtomicBoolean();

    SessionFeed(String sessionId) {
        this.sessionId = sessionId;
    }

    String sessionId() {
        return sessionId;
    }

    Flux<String> events() {
        return Flux.interval(Duration.ofSeconds(5))
            .map(sequence ->
                "update-" + sequence + " for " + sessionId
            )
            .takeUntilOther(closed.asMono());
    }

    Mono<Void> close() {
        return Mono.fromRunnable(() -> {
            if (closeStarted.compareAndSet(false, true)) {
                closed.tryEmitEmpty();
            }
        });
    }

    boolean isClosed() {
        return closeStarted.get();
    }
}
~~~

SessionFeed đại diện cho một resource gắn với một session. Feed phát event định kỳ. Khi close signal được phát, takeUntilOther dừng timer và hoàn tất publisher.

Trong ứng dụng thực tế, resource này có thể là subscription tới broker hoặc database change feed. Method close() khi đó sẽ unsubscribe/close resource thật.

### 17.6. SessionFeedService.java

~~~java
package demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
class SessionFeedService {
    private final ConcurrentMap<String, SessionFeed> active =
        new ConcurrentHashMap<>();

    Mono<SessionFeed> open(String sessionId) {
        return Mono.fromSupplier(() -> {
            SessionFeed feed = new SessionFeed(sessionId);
            SessionFeed existing = active.putIfAbsent(sessionId, feed);

            if (existing != null) {
                throw new IllegalStateException(
                    "Feed already exists for session " + sessionId
                );
            }

            return feed;
        });
    }

    Mono<Void> close(SessionFeed feed) {
        return feed.close()
            .doFinally(signal ->
                active.remove(feed.sessionId(), feed)
            );
    }

    Flux<String> events(String sessionId) {
        return Flux.usingWhen(
            open(sessionId),
            SessionFeed::events,
            this::close,
            (feed, error) -> close(feed),
            this::close
        );
    }

    int activeCount() {
        return active.size();
    }
}
~~~

events(sessionId) tạo một resource cho mỗi subscription. usingWhen gọi close khi feed hoàn tất, phát lỗi hoặc bị cancel. Map active chỉ giữ các feed đang hoạt động và entry được remove trong cleanup.

### 17.7. ChatWebSocketHandler.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SynchronousSink;

@Component
class ChatWebSocketHandler implements WebSocketHandler {
    private static final Logger log =
        LoggerFactory.getLogger(ChatWebSocketHandler.class);

    private static final int MAX_TEXT_LENGTH = 1024;

    private final SessionFeedService feedService;

    ChatWebSocketHandler(SessionFeedService feedService) {
        this.feedService = feedService;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .handle((String text, SynchronousSink<String> sink) -> {
                if (text.length() > MAX_TEXT_LENGTH) {
                    sink.error(new PolicyViolationException(
                        "Message exceeds the allowed length"
                    ));
                } else {
                    sink.next(text);
                }
            })
            .publish(messages -> {
                AtomicBoolean closeRequested = new AtomicBoolean();

                Mono<Void> input = messages
                    .takeUntil("/close"::equals)
                    .doOnNext(text -> {
                        if ("/close".equals(text)) {
                            closeRequested.set(true);
                        }
                    })
                    .then()
                    .then(Mono.defer(() ->
                        closeRequested.get()
                            ? session.close(CloseStatus.NORMAL)
                            : Mono.<Void>empty()
                    ));

                Flux<WebSocketMessage> replies = messages
                    .filter(text -> !"/close".equals(text))
                    .map(text -> session.textMessage("echo: " + text));

                Flux<WebSocketMessage> updates =
                    feedService.events(session.getId())
                        .map(session::textMessage);

                Mono<Void> output = session.send(
                    Flux.merge(replies, updates)
                );

                return Mono.firstWithSignal(input, output)
                    .doOnError(error ->
                        log.error(
                            "WebSocket session {} failed",
                            session.getId(),
                            error
                        )
                    )
                    .onErrorResume(
                        PolicyViolationException.class,
                        error -> closeSafely(
                            session,
                            CloseStatus.POLICY_VIOLATION
                        )
                    )
                    .onErrorResume(
                        error -> closeSafely(
                            session,
                            CloseStatus.SERVER_ERROR
                        )
                    )
                    .doFinally(signal ->
                        log.info(
                            "WebSocket session {} ended with {}",
                            session.getId(),
                            signal
                        )
                    )
                    .then(
                        session.closeStatus()
                            .doOnNext(status ->
                                log.info(
                                    "WebSocket session {} close code {}",
                                    session.getId(),
                                    status.getCode()
                                )
                            )
                            .then()
                    );
            });
    }

    private Mono<Void> closeSafely(
            WebSocketSession session,
            CloseStatus status) {

        return session.close(status)
            .onErrorResume(closeError -> {
                log.debug(
                    "Could not complete close handshake for session "
                        + session.getId(),
                    closeError
                );
                return Mono.empty();
            });
    }
}
~~~

Giải thích lifecycle:

1. session.receive() tạo inbound stream.
2. handle kiểm tra giới hạn message trước khi chia sẻ dữ liệu cho hai nhánh.
3. publish(Function) chia sẻ một subscription inbound cho nhánh theo dõi lifecycle và nhánh tạo echo; không subscribe socket hai lần.
4. Khi nhận /close, nhánh input kết thúc và compose session.close(CloseStatus.NORMAL).
5. Nhánh output hợp nhất echo và server feed rồi gọi session.send đúng một lần.
6. Mono.firstWithSignal kết thúc handler khi một nhánh complete hoặc error, đồng thời cancel nhánh còn lại.
7. Khi output bị cancel, Flux.usingWhen của feed chạy cleanup cancellation.
8. Lỗi policy đóng bằng 1008; lỗi không mong đợi đóng bằng 1011.
9. doFinally ghi terminal signal; closeStatus() đọc status nếu transport có cung cấp.

closeSafely xử lý trường hợp kết nối đã mất và không thể hoàn tất close handshake. Lỗi close được log, nhưng cleanup của các publisher vẫn phải chạy.

### 17.8. WebSocketConfig.java

~~~java
package demo;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration
class WebSocketConfig {

    @Bean
    HandlerMapping webSocketMapping(ChatWebSocketHandler handler) {
        Map<String, WebSocketHandler> handlers =
            Map.of("/ws/chat", handler);

        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setOrder(-1);
        mapping.setUrlMap(handlers);

        return mapping;
    }
}
~~~

Spring Boot WebFlux auto-configuration cung cấp hạ tầng WebSocket adapter khi WebFlux config đang hoạt động. Nếu tự xây dựng ứng dụng không dùng WebFlux config, cần đăng ký WebSocketHandlerAdapter theo hướng dẫn Spring Framework.

Không thêm EnableWebFlux chỉ để map một WebSocket handler vào Spring Boot app; cấu hình handler mapping riêng là đủ cho ví dụ này.

### 17.9. SessionFeedServiceTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class SessionFeedServiceTest {

    @Test
    void completionReleasesFeed() {
        SessionFeedService service = new SessionFeedService();

        Flux<String> oneEvent = Flux.usingWhen(
            service.open("complete-session"),
            feed -> feed.events().take(1),
            service::close,
            (feed, error) -> service.close(feed),
            service::close
        );

        StepVerifier.withVirtualTime(() -> oneEvent)
            .thenAwait(Duration.ofSeconds(5))
            .expectNext("update-0 for complete-session")
            .verifyComplete();

        assertEquals(0, service.activeCount());
    }

    @Test
    void cancellationReleasesFeed() {
        SessionFeedService service = new SessionFeedService();

        StepVerifier.withVirtualTime(() ->
                service.events("cancelled-session"))
            .thenAwait(Duration.ofSeconds(5))
            .expectNext("update-0 for cancelled-session")
            .thenCancel()
            .verify();

        assertEquals(0, service.activeCount());
    }

    @Test
    void errorReleasesFeed() {
        SessionFeedService service = new SessionFeedService();

        Flux<String> failed = Flux.usingWhen(
            service.open("failed-session"),
            feed -> Flux.<String>error(
                new IllegalStateException("feed failed")
            ),
            service::close,
            (feed, error) -> service.close(feed),
            service::close
        );

        StepVerifier.create(failed)
            .expectErrorMessage("feed failed")
            .verify();

        assertEquals(0, service.activeCount());
    }
}
~~~

Ba test xác minh cleanup chạy khi resource closure complete, error và cancel. Virtual time cho phép kiểm tra timer mà không cần chờ thật. Không dùng Thread.sleep.

### 17.10. Chạy ứng dụng

Tại thư mục dự án:

~~~bash
./gradlew bootRun
~~~

Hoặc:

~~~bash
gradle bootRun
~~~

Kết nối bằng browser console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/chat");

socket.onopen = () => {
    socket.send("hello");
};

socket.onmessage = event => {
    console.log("received:", event.data);
};

socket.onclose = event => {
    console.log("closed:", event.code, event.reason);
};

socket.onerror = error => {
    console.error("websocket error", error);
};
~~~

Server trả message echo gần như ngay lập tức và phát thêm event định kỳ. Để yêu cầu đóng bình thường:

~~~javascript
socket.send("/close");
~~~

Để kiểm tra policy violation, gửi text vượt quá 1024 ký tự. Server sẽ đóng phiên với close code 1008. Trong demo, feed được cleanup sau khi output publisher bị cancel.

Chạy test:

~~~bash
./gradlew test
~~~

Test xác minh ba đường cleanup của resource feed. Chúng không thay thế kiểm thử handshake qua network; khi đưa endpoint vào production, nên bổ sung integration test với WebSocketClient hoặc client tương thích để kiểm tra close handshake, reconnect và transport error.

## 18. Ví dụ WebSocketClient phía client

Spring WebFlux cũng có WebSocketClient. execute(URI, WebSocketHandler) trả Mono<Void> đại diện cho lifecycle của client session.

~~~java
WebSocketClient client = new ReactorNettyWebSocketClient();
URI uri = URI.create("ws://localhost:8080/ws/chat");

Mono<Void> conversation = client.execute(uri, session ->
    session.send(
        Mono.just(session.textMessage("hello"))
    )
    .then(
        session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .next()
            .doOnNext(System.out::println)
            .then()
    )
    .then(
        session.close(CloseStatus.NORMAL)
    )
);
~~~

Client gửi một message, đọc response đầu tiên, rồi đóng session bình thường. Nếu caller cancel conversation, client handler cũng nhận cancellation và các publisher nhận/gửi phải kết thúc theo lifecycle.

Không gọi subscribe() riêng rồi bỏ publisher của execute. Hãy trả Mono về caller để caller quyết định subscribe, timeout, cancel và xử lý lỗi.

## 19. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đóng socket, quên broker subscription | Resource upstream vẫn hoạt động | Gắn subscription vào usingWhen |
| Chỉ cleanup trong doOnComplete | Bỏ sót error và cancel | Dùng usingWhen hoặc doFinally phù hợp |
| Chỉ bắt error, không xử lý cancel | Client rời đi nhưng task vẫn chạy | Đảm bảo cancellation truyền tới publisher |
| Dùng subscribe riêng cho feed | Lifecycle tách khỏi handler | Return publisher và compose với send |
| Gọi close mà không compose Mono | Close frame có thể chưa được gửi | Chain session.close(...) vào Mono |
| Gọi session.send nhiều lần | Nhiều writer tranh quyền ghi | Hợp nhất message source rồi send một lần |
| Để output vô hạn sau khi inbound đóng | Feed vẫn giữ resource | Dùng composition kết thúc nhánh còn lại |
| Dùng Mono.when mà không hiểu semantics | Có thể chờ tất cả nhánh hoàn tất | Chọn toán tử theo chính sách kết thúc session |
| Nuốt lỗi thành Mono.empty | Lỗi bị biến thành đóng bình thường | Map lỗi thành close status có chủ đích |
| Dùng close code 1006 để gửi close frame | Dùng mã dành riêng không hợp lệ | Để transport biểu diễn abnormal closure |
| Coi HTTP 101 là close status | Nhầm handshake với close handshake | Đọc CloseStatus của WebSocket |
| Dùng isOpen() làm điều kiện đồng bộ | Race giữa check và thao tác gửi | Dựa vào reactive signal và xử lý lỗi ghi |
| Giữ WebSocketMessage qua async boundary mà không retain | Pooled buffer có thể đã được release | Copy payload đồng bộ hoặc retain/release |
| Retain nhưng không release | Memory leak | Release trong doFinally của công việc giữ message |
| Cleanup chặn event loop | Tăng latency và nghẽn server | Dùng cleanup reactive hoặc scheduler phù hợp |
| Registry không remove session | Memory leak và trạng thái stale | Remove entry trong cleanup |
| Queue outbound không giới hạn | Tăng RAM khi client chậm | Áp backpressure, giới hạn queue và quota |
| Log toàn bộ payload | Có thể lộ dữ liệu nhạy cảm | Log metadata, close code và correlation ID |
| Dùng close status 1000 cho mọi lỗi | Client hiểu nhầm phiên kết thúc bình thường | Map lỗi sang 1008/1009/1011 phù hợp |

## 20. Checklist trước khi đưa WebSocket lên production

1. Handler có trả một Mono<Void> duy nhất đại diện cho lifecycle phiên không?
2. Inbound và outbound được compose theo đúng chính sách kết thúc chưa?
3. Khi inbound đóng, feed outbound có bị cancel không?
4. Khi output lỗi, inbound có bị hủy không?
5. Broker/database subscription có cleanup khi complete, error và cancel không?
6. session.close(...) có được compose và await không?
7. Close code có phản ánh đúng nguyên nhân không?
8. Client disconnect bất thường có được xử lý dù closeStatus() empty không?
9. Có giới hạn message size, concurrency và queue không?
10. Có retain/release nếu giữ pooled message qua async boundary không?
11. Session registry có remove entry trong cleanup không?
12. Cleanup có idempotent và không block event loop không?
13. Có metric active sessions, close codes, errors, cancels và duration không?
14. Có test cho complete, error và cancel không?
15. Có integration test cho handshake, normal close và abnormal disconnect không?
16. Graceful shutdown có grace period và giới hạn thời gian không?

| Yêu cầu | API hoặc cơ chế |
| --- | --- |
| Nhận message | session.receive() |
| Gửi message | session.send(...) |
| Đóng bình thường | session.close(CloseStatus.NORMAL) |
| Đóng do policy | CloseStatus.POLICY_VIOLATION |
| Đóng do lỗi server | CloseStatus.SERVER_ERROR |
| Đọc close code | session.closeStatus() |
| Kết thúc khi nhánh đầu tiên dừng | Mono.firstWithSignal(...) |
| Cleanup async theo complete/error/cancel | Flux.usingWhen(...) |
| Quan sát terminal signal | doFinally(...) |
| Quan sát cancellation | doOnCancel(...) |
| Giữ pooled message | message.retain() |
| Release message đã retain | message.release() |

## 21. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** WebSocketHandler.handle trả về kiểu gì và biểu diễn điều gì?

**Đáp án:** Mono<Void> biểu diễn thời điểm xử lý session hoàn tất. Handler phải compose inbound, outbound và cleanup vào lifecycle đó.

**Câu 2.** receive() và send(...) khác nhau thế nào?

**Đáp án:** receive() là Flux message inbound, hoàn tất khi kết nối đóng. send(...) ghi publisher outbound và trả Mono<Void> hoàn tất khi nguồn message cùng thao tác ghi kết thúc.

**Câu 3.** Khi client đóng kết nối, vì sao phải cancel outbound feed?

**Đáp án:** Feed có thể vô hạn và giữ subscription tới broker hoặc resource khác. Cancellation dừng nguồn và kích hoạt cleanup.

**Câu 4.** doFinally bao phủ những signal nào?

**Đáp án:** Complete, error và cancel. Nó phù hợp cho quan sát lifecycle hoặc cleanup đồng bộ ngắn.

**Câu 5.** Khi nào nên dùng usingWhen?

**Đáp án:** Khi cần mở resource và đóng nó bất đồng bộ trong cả ba trường hợp complete, error và cancel.

**Câu 6.** session.close(CloseStatus.NORMAL) có thực hiện ngay khi tạo Mono không?

**Đáp án:** Không. Đây là reactive publisher; phải subscribe hoặc compose nó vào lifecycle để close handshake được thực hiện.

**Câu 7.** 1000 và 1008 khác nhau thế nào?

**Đáp án:** 1000 là đóng bình thường; 1008 là đóng do message vi phạm policy.

**Câu 8.** 1006 có thể được gửi trong Close control frame không?

**Đáp án:** Không. 1006 là mã dành riêng để biểu diễn abnormal closure khi không nhận close frame.

**Câu 9.** Vì sao closeStatus() có thể hoàn tất rỗng?

**Đáp án:** Transport có thể kết thúc mà không nhận được WebSocket close status, ví dụ mất mạng hoặc kết nối bị reset.

**Câu 10.** Khi nào cần gọi message.retain()?

**Đáp án:** Khi cần giữ message hoặc pooled DataBuffer để sử dụng sau khi rời khỏi synchronous receive callback hoặc qua asynchronous boundary.

**Câu 11.** Vì sao phải release message đã retain?

**Đáp án:** Retain tăng reference count của pooled buffer. Release đúng lúc đưa reference count về mức cho phép buffer được thu hồi.

**Câu 12.** Mono.firstWithSignal(input, output) có ý nghĩa gì?

**Đáp án:** Publisher phát terminal signal đầu tiên trong hai Mono; nhánh còn lại bị cancel. Dùng khi một phía kết thúc thì phiên không cần tiếp tục.

**Câu 13.** Đóng WebSocket session có tự động unsubscribe mọi broker subscription do ứng dụng tạo không?

**Đáp án:** Không. Broker subscription phải nằm trong reactive lifecycle hoặc có cleanup callback riêng như usingWhen.

**Câu 14.** Vì sao không nên gọi subscribe() riêng trong WebSocketHandler?

**Đáp án:** Subscription độc lập không còn được điều khiển bởi lifecycle của handler; cancellation và lỗi của session có thể không truyền tới publisher đó.

## 22. Ghi nhớ và tài liệu chính thức

- WebSocketHandler trả Mono<Void> đại diện cho toàn bộ xử lý session.
- receive() và send(...) là hai luồng reactive cần được compose.
- Khi một phía kết thúc theo policy, hủy phía còn lại để upstream resource được cleanup.
- session.close(CloseStatus) gửi close handshake và phải được compose.
- closeStatus() có thể empty khi transport kết thúc bất thường.
- Dùng close code phù hợp: 1000 bình thường, 1008 policy, 1009 quá lớn, 1011 lỗi server.
- usingWhen quản lý cleanup async cho complete, error và cancel.
- doFinally quan sát cả ba terminal signal; doOnCancel chỉ quan sát cancellation.
- Không để broker subscription, timer, registry hoặc queue sống lâu hơn WebSocket session.
- Pooled DataBuffer cần ownership rõ ràng; retain phải đi cùng release.
- Không dùng subscribe thủ công hoặc nhiều writer độc lập cho cùng session.

Tài liệu chính thức:

1. [Spring Framework Reference — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-websocket.html): WebSocketHandler, receive/send composition, cancellation, close session, client API và DataBuffer.
2. [Spring Framework Javadoc — WebSocketSession](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html): close, closeStatus, receive, send và session metadata.
3. [Spring Framework Javadoc — CloseStatus](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/socket/CloseStatus.html): close code, constant và ý nghĩa.
4. [Spring Framework Javadoc — WebSocketMessage](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html): payload, retain và release.
5. [Spring Framework Reference — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html): pooled buffer, reference counting, retain/release và discard.
6. [Project Reactor Javadoc — Flux.usingWhen](https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Flux.html): asynchronous resource cleanup trên complete, error và cancel.
7. [Project Reactor Javadoc — Mono.firstWithSignal](https://docs.spring.io/projectreactor/reactor-core/docs/current/api/reactor/core/publisher/Mono.html): chọn terminal signal đầu tiên từ nhiều Mono.
8. [Spring Framework Javadoc — WebSocketClient](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/reactive/socket/client/WebSocketClient.html): execute handshake và quản lý client session.

# Streaming bị treo, mất ngữ cảnh hoặc chặn luồng reactive

Trong hệ thống dùng Spring AI Tool Calling, giao diện có thể ngừng nhận token dù ứng dụng vẫn đang làm việc; một tool có thể thấy `tenantId` rỗng sau khi chuyển thread; hoặc WebFlux báo lỗi khi callback gọi `block()` trên luồng xử lý non-blocking. Ba biểu hiện này nhìn giống “stream bị treo”, nhưng cách khắc phục khác nhau. Bài học hướng dẫn truy vết từ HTTP/SSE qua Reactor, `ChatClient`, `ToolCallingAdvisor`, `ToolCallback` đến dịch vụ ngoài và bộ nhớ hội thoại.

Giả định Spring AI **2.1.x**: `ChatClient.stream()` dùng đường streaming/reactive của model, nhưng tool calling vẫn chứa phần thực thi **imperative** có thể blocking. `ToolCallingAdvisor` quản lý các vòng mô hình → callback → mô hình, còn việc giữ trạng thái giữa các lượt hội thoại thuộc session memory hoặc lớp điều phối ứng dụng. Không nên xem “có Flux” là bằng chứng mọi phần bên trong đều non-blocking.

## 1. Xác định chính xác luồng nào bị dừng

Một request streaming thường đi qua các tầng:

~~~mermaid
flowchart TD
    UI[Trình duyệt / SSE client] --> HTTP[WebFlux endpoint]
    HTTP --> RX[Reactor Flux]
    RX --> CLIENT[ChatClient + advisor chain]
    CLIENT --> MODEL[ChatModel streaming]
    MODEL --> LOOP{Có tool call hoàn chỉnh?}
    LOOP -->|Không| TOKENS[Text chunks đến subscriber]
    LOOP -->|Có| MGR[ToolCallingManager]
    MGR --> TOOL[ToolCallback đồng bộ]
    TOOL --> SERVICE[DB / HTTP / nghiệp vụ]
    SERVICE --> MGR
    MGR --> CLIENT
    TOKENS --> UI
~~~

Để điều tra, thu thập `requestId`, `sessionId` (sau khi xác thực quyền sở hữu), model name, `toolName`, thời gian bắt đầu/kết thúc mỗi model round, callback, HTTP connection và trạng thái subscription. Không log raw tool arguments, tool results, access token hoặc nội dung nhạy cảm.

| Biểu hiện quan sát | Giả thuyết đầu tiên | Dấu hiệu phân biệt |
| --- | --- | --- |
| Chưa nhận một token nào | Stream chưa subscribe, provider chậm, callback đang chạy hoặc proxy buffer | Có log subscribe? Có tool.started? Có dữ liệu trên network? |
| Nhận vài token rồi đứng | Model chuyển sang tool call, tool blocking, upstream mất kết nối hoặc downstream không đọc | Có tool.started nhưng không có tool.finished? |
| Câu trả lời mất thông tin lượt trước | Thiếu session ID, memory advisor đặt sai vòng hoặc lịch sử tool không đầy đủ | Prompt round kế tiếp và active history có gì? |
| `block()` báo lỗi trên `reactor-http-nio-*` | Blocking ở event-loop | Stack trace và tên thread khi lỗi |
| Không có lỗi nhưng browser mãi loading | Flux không complete, side subscription không được dispose, SSE/proxy buffer | Có `doFinally`? Client nhận event nào? |
| Hai request dùng chung lịch sử sai | Session ID/cache mutable dùng chung, hai turn cùng session chạy đồng thời | Có session overlap và message xen kẽ? |

Điều đầu tiên cần làm là **xác định tầng cuối cùng có tiến độ**. Đừng tăng timeout hoặc thay model ngay khi chưa biết callback, mạng hay SSE đang giữ luồng.

## 2. Hiểu khoảng lặng hợp lệ trong một vòng tool calling

`ChatClient.prompt().stream().content()` trả `Flux<String>` chứa **phần văn bản**. Khi model tạo tool call, nó có thể không tạo text; `ToolCallingAdvisor` nhận tool call hoàn chỉnh, chạy callback, đưa kết quả về model và chờ model tiếp tục. Trong thời gian callback chạy, `content()` không nhất thiết phát bất kỳ token mới nào.

Ví dụ thời gian:

~~~text
00.000s  Client subscribe
00.240s  Model round 1 bắt đầu
00.900s  Model trả tool call: lookup_delivery
00.910s  Callback bắt đầu
05.800s  Dịch vụ vận chuyển trả kết quả
05.820s  Callback kết thúc
05.900s  Model round 2 bắt đầu với tool result
06.150s  Assistant.delta đầu tiên
06.700s  Assistant.completed
~~~

Nếu chỉ đo `assistant.delta`, UI thấy khoảng lặng gần sáu giây dù vòng lặp đang hoạt động bình thường. Gửi event trạng thái tool qua một kênh quan sát riêng khi cần giao diện hiển thị “đang tra cứu”; không tự tạo token giả để che việc callback mất nhiều thời gian.

### Tool-call argument delta và complete call

Spring AI 2.1 có `ToolCallPart` cho các model/provider hỗ trợ stream arguments. Các part đánh dấu partial bởi `StreamingParts.isPartial(part)` chỉ là những mảnh arguments đang được sinh:

~~~java
Flux<ChatResponse> chunks = chatClient.prompt()
    .user(question)
    .tools(orderTools)
    .stream()
    .chatResponse();

return chunks.doOnNext(response ->
    response.getResults().forEach(generation -> {
        for (MessagePart part : generation.getOutput().getParts()) {
            if (part instanceof ToolCallPart toolPart
                    && StreamingParts.isPartial(part)) {
                var call = toolPart.toolCall();
                progress.showPreparingTool(call.id(), call.name());
            }
        }
    }));
~~~

Đoạn minh họa quan sát chunk (cần import các lớp message/part của Spring AI). **Partial part không phải yêu cầu thực thi tool**: `AssistantMessage.hasToolCalls()` và `getToolCalls()` bỏ qua chúng. JSON của một delta đơn lẻ thường chưa hoàn chỉnh; không parse hoặc gọi callback từ từng fragment. Model sau đó phát tool call hoàn chỉnh để advisor thực thi. Một số provider không stream arguments, nên UI có thể không nhận event preparing nào.

Tool call hoàn chỉnh được `ToolCallingAdvisor` xử lý và lọc khỏi stream ngoài; nếu cần nhìn thấy request tool ở từng model round, phải quan sát **bên trong** vòng advisor.

## 3. Phân biệt Flux chưa subscribe với Flux đang chờ

Reactor `Flux` là mô tả luồng xử lý; nó không tự chạy khi chưa được subscribe. Một controller chỉ tạo `Flux` và không có subscriber sẽ không gọi model. Với WebFlux, framework tự subscribe khi endpoint trả reactive body. Trong service, đừng tạo một `Flux` rồi bỏ qua giá trị trả về hoặc chỉ gắn `map` mà không trả chuỗi đã gắn operator.

Ví dụ quan sát lifecycle ở ranh giới request:

~~~java
Flux<String> tokens = chatClient.prompt()
    .user(question)
    .tools(orderTools)
    .stream()
    .content();

return tokens
    .doOnSubscribe(subscription -> log.info(
        "stream subscribed requestId={}", requestId))
    .doOnNext(token -> meterRegistry.counter("chat.stream.chunks").increment())
    .doOnError(ex -> log.warn(
        "stream failed requestId={} errorType={}",
        requestId, ex.getClass().getSimpleName()))
    .doOnCancel(() -> log.info(
        "stream cancelled requestId={}", requestId))
    .doFinally(signal -> log.info(
        "stream finalized requestId={} signal={}", requestId, signal));
~~~

Giải thích:

- Không thấy `doOnSubscribe`: controller/client có thể chưa đăng ký luồng, route không được gọi hoặc subscription bị chặn trước đó.
- Có subscribe, không có `doOnNext`: kiểm tra provider, advisor/tool loop và callback; chưa thể kết luận bị treo.
- Có `doOnCancel`: browser hoặc tầng khác đã hủy, hoặc timeout operator phát cancellation.
- Có `doFinally(CANCEL)` nhưng HTTP call của tool vẫn chạy: callback blocking không nhất thiết bị dừng ngay.
- Có `doOnComplete`/`doFinally(ON_COMPLETE)` ở server nhưng client vẫn loading: kiểm tra buffering, cách parse SSE và lifecycle phía browser.

Đừng gọi `subscribe()` bên trong service/controller để “kích hoạt stream” rồi đồng thời trả lại cùng `Flux` cho WebFlux. Hai subscription có thể phát sinh hai model requests và lặp side effect của tool. Mỗi user request cần một đường subscription được quản lý rõ ràng.

## 4. Streaming từ WebFlux ra SSE

Spring WebFlux hỗ trợ `Flux<ServerSentEvent<T>>`; từng event được ghi khi phát sinh. Với browser `EventSource` chuẩn, URL phải dùng GET. Nếu gửi prompt bằng POST và nhận `text/event-stream`, dùng `fetch()` cùng reader SSE, hoặc tách POST tạo request và GET subscribe theo request ID.

Ví dụ endpoint POST được client đọc bằng `fetch()`:

~~~java
import java.security.Principal;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

record StreamRequest(String conversationId, String question) {}

@RestController
class AssistantStreamController {

    private static final Logger log =
        LoggerFactory.getLogger(AssistantStreamController.class);

    private final ChatClient chatClient;
    private final ConversationAccess access;
    private final OrderTools orderTools;

    AssistantStreamController(
            ChatClient chatClient,
            ConversationAccess access,
            OrderTools orderTools) {
        this.chatClient = chatClient;
        this.access = access;
        this.orderTools = orderTools;
    }

    @PostMapping(
        value = "/api/chat/stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<ServerSentEvent<String>> stream(
            @RequestBody StreamRequest request,
            Principal principal) {

        return Mono.fromCallable(() ->
                access.requireOwned(principal, request.conversationId()))
            .subscribeOn(Schedulers.boundedElastic())
            .flatMapMany(sessionId -> chatClient.prompt()
                .user(request.question())
                .tools(orderTools)
                .advisors(SessionAdvisors.session(sessionId))
                .stream()
                .content()
                .map(token -> ServerSentEvent.builder(token)
                    .event("assistant.delta")
                    .build()))
            .doOnError(ex -> log.warn(
                "chat stream failed errorType={}",
                ex.getClass().getSimpleName()))
            .doFinally(signal -> log.info(
                "chat stream finished signal={}", signal));
    }
}
~~~

Đây là một ví dụ ghép hai vấn đề: `access.requireOwned(...)` là thao tác **có thể blocking** ở repository nên được đặt vào `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; còn `ChatClient.stream()` vẫn trả các delta theo từng chunk. `SessionAdvisors.session(sessionId)` giả định `ChatClient` đã được cấu hình SessionAdvisors. Trong ứng dụng thật, bảo vệ endpoint bằng authentication và authorization, giới hạn input, xử lý error event có cấu trúc và tránh dùng một instance tool chứa state mutable cho nhiều user.

**Giới hạn của ví dụ:** offload việc xác minh quyền sang boundedElastic **không có nghĩa** các tool callbacks bên trong vòng chat đã tự chuyển sang boundedElastic. Callback blocking cần thiết kế scheduler, timeout và isolation riêng theo đường thực thi thực tế. Không được chuyển `.stream()` thành `.call()` chỉ để hết lỗi event-loop nếu UI vẫn cần stream token.

### Kiểm tra bằng client và proxy

Thử endpoint trong môi trường test với client không buffer:

~~~bash
curl -N -i \
  -H "Accept: text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"conversationId":"conv-test","question":"Tra cứu đơn ORD-100"}' \
  http://localhost:8080/api/chat/stream
~~~

- Nếu curl thấy từng event còn browser không thấy, kiểm tra frontend parser, `fetch` reader, buffering hoặc timeout ở reverse proxy.
- Nếu cả curl và browser đều không thấy event, kiểm tra subscribe/model/tool.
- Nếu server đã gửi nhưng proxy dồn đến cuối, cân nhắc cấu hình proxy cho SSE: tắt buffering với đúng route, dùng `text/event-stream`, giữ kết nối không bị idle-timeout bất hợp lý; một số proxy cần cấu hình riêng như `proxy_buffering off`.
- Đừng truyền dữ liệu nhạy cảm trong query string GET; nếu dùng `EventSource`, tạo request bằng POST và nhận một request ID đã được kiểm tra quyền trước khi subscribe.

## 5. Chặn luồng reactive: nơi nào đang gọi API blocking?

Reactor thường xử lý HTTP bằng ít event-loop threads, ví dụ `reactor-http-nio-3`. Một callback đồng bộ chạy JDBC, `RestClient`, `Thread.sleep(...)` hoặc gọi `block()` có thể chiếm thread này nếu đường điều phối thực thi nó ngay trên event-loop. Kết quả là không chỉ một chat chậm; nhiều request khác cũng mất khả năng tiến triển.

| Tình huống | Dấu hiệu | Hành động |
| --- | --- | --- |
| `Mono.block()` trên non-blocking thread | `IllegalStateException: block()/blockFirst()/blockLast() are blocking...` | Bỏ block trong đường reactive; compose bằng `flatMap` |
| JDBC hoặc HTTP sync ở `map/doOnNext` | Thread dump giữ `reactor-http-nio-*` lâu | Dời blocking call sang boundedElastic hoặc service async |
| `Thread.sleep(...)` trong callback/adapter | Không có token, event-loop chậm | Dùng scheduler/timer phù hợp; tuyệt đối không sleep trên event-loop |
| `Flux.collectList()` trước SSE | UI nhận tất cả token ở cuối | Trả Flux để stream từng event |
| `blockLast()` trong controller | Controller giữ thread đợi stream kết thúc | Trả reactive publisher trực tiếp |
| Đồng bộ hóa bằng `synchronized` rộng | Nhiều request đứng ở cùng monitor | Thu hẹp lock; serialize đúng theo session hoặc operation |

Reactor khuyến nghị bọc **nguồn blocking** bằng `Mono.fromCallable` và đặt `subscribeOn(Schedulers.boundedElastic())` sát nguồn:

~~~java
Mono<Order> loadOrder(String tenantId, String orderId) {
    return Mono.fromCallable(
            () -> jdbcOrderRepository.findForTenant(tenantId, orderId))
        .subscribeOn(Schedulers.boundedElastic());
}

Mono<String> summary(String tenantId, String orderId) {
    return loadOrder(tenantId, orderId)
        .map(order -> "Trạng thái: " + order.status());
}
~~~

`boundedElastic` dùng lượng thread giới hạn cho công việc blocking; nó không tạo năng lực vô hạn. Nếu database chậm hoặc lượng job vượt queue, latency vẫn tăng. Đặt pool/database/HTTP timeouts và giới hạn concurrency theo downstream.

**Không hiểu nhầm các operator:**

- `subscribeOn` quyết định scheduler cho quá trình subscription của phần upstream, nhưng một provider async vẫn có thể phát sự kiện trên thread khác.
- `publishOn` chuyển xử lý của các operator **sau** nó sang scheduler. Đặt `publishOn(boundedElastic())` **sau** `chatClient.stream().content()` không chứng minh `ToolCallingManager`/callback trước đó đã chạy trên boundedElastic.
- `doOnNext` nên dùng để ghi metric/log nhẹ; không đặt DB query blocking tại đây.
- Trả `Mono<T>` từ phương thức `@Tool` đồng bộ không mặc nhiên biến callback thành non-blocking hoặc bảo đảm framework sẽ await kết quả. Thiết kế theo contract ToolCallback và version cụ thể.

Nếu workflow chỉ cần câu trả lời **một lần** và cố ý dùng `ChatClient.call()` blocking, có thể offload toàn bộ lời gọi sang scheduler:

~~~java
Mono<String> answer = Mono.fromCallable(() ->
        chatClient.prompt()
            .user(question)
            .tools(orderTools)
            .call()
            .content())
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là một `Mono` trả đáp án cuối; **không phải** giải pháp giữ token streaming. Với streaming tool calling, cần kiểm tra scheduler của advisor/callback, dùng I/O có thời hạn, hoặc tự điều phối những đoạn blocking trên scheduler riêng theo đúng thiết kế.

## 6. Mất ngữ cảnh: có ít nhất ba loại context khác nhau

Trong một pipeline reactive có tool calling, “context” có thể chỉ những đối tượng không giống nhau:

| Context | Nơi lưu | Mục đích | Có tự đi theo thread khác không? |
| --- | --- | --- | --- |
| Reactor `Context` | Theo subscriber | Correlation ID, request-scoped metadata trong chain reactive | Đi theo subscription khi dùng operator Reactor đúng cách |
| ChatClient advisor context | Trong `ChatClientRequest` và advisor chain | Session ID, event filter, dữ liệu advisor đọc | Theo request/advisor; không đồng nghĩa Reactor Context |
| `ToolContext` | Trong tool calling options | Tenant/actor/request metadata chuyển tới callback | Được chuyển qua callback theo Spring AI; không tự tạo quyền |
| `SecurityContextHolder`, MDC | ThreadLocal ở nhiều cấu hình imperative | Auth, trace/log correlation | Có thể mất khi đổi thread nếu không propagate |

Không suy rằng một `requestId` được đặt vào Reactor `Context` sẽ tự hiện diện trong `ToolContext`; cũng không suy rằng `SessionAdvisors.session(id)` tạo security context cho service nghiệp vụ. Mỗi ranh giới cần mapping rõ ràng.

### Ví dụ mapping context có chủ đích

Giả sử một `RequestScope` được tạo từ principal đã xác thực:

~~~java
record RequestScope(
    String requestId,
    String tenantId,
    String sessionId
) {}

Flux<String> startChat(ChatClient chatClient, String question) {
    return Flux.deferContextual(ctx -> {
        RequestScope scope = ctx.get(RequestScope.class);
        return chatClient.prompt()
            .user(question)
            .advisors(SessionAdvisors.session(scope.sessionId()))
            .toolContext(Map.of(
                "requestId", scope.requestId(),
                "tenantId", scope.tenantId()
            ))
            .stream()
            .content();
    });
}

// scope do lớp xác thực/quản lý conversation tạo tại server
Flux<String> tokens = startChat(chatClient, question)
    .contextWrite(context -> context.put(RequestScope.class, scope));
~~~

`Flux.deferContextual` đọc metadata của đúng subscriber khi subscription bắt đầu; nó không cần ThreadLocal. `ToolContext` chỉ nhận các giá trị đã lựa chọn từ `RequestScope`. Scope này **phải do server xây dựng và kiểm tra quyền**, không lấy tenant/role từ lời nhắc hoặc arguments do model sinh.

Với `SecurityContextHolder`/MDC ở code imperative, nếu cần sang scheduler khác thì dùng cơ chế context propagation phù hợp của Spring Security, Reactor hoặc Micrometer, hoặc truyền explicit context do server xác thực. Đừng tự thêm principal vào một singleton field `currentUser` vì nhiều stream đồng thời sẽ ghi đè lên nhau.

## 7. Mất hội thoại vì thiếu session memory hoặc sai advisor order

Lịch sử bên trong một vòng tool calling và bộ nhớ giữa nhiều lượt người dùng có phạm vi khác nhau:

- `ToolCallingAdvisor` mặc định giữ lịch sử các model rounds **trong một turn**, đưa assistant tool call + tool response sang round tiếp theo.
- Session Memory khôi phục lịch sử qua **nhiều turn**, phân vùng bằng session ID.
- `ToolExecutionResult.conversationHistory()` dùng để tiếp tục vòng khi tự điều phối; nó không tự persist lịch sử qua request mới.

Trong Spring AI 2.1, cấu hình `SessionAdvisors` kết hợp `SessionMemoryAdvisor` (bên trong tool loop, order mặc định `HIGHEST_PRECEDENCE + 1000`) và `SessionTurnAdvisor` (bên ngoài loop, `+200`). `ToolCallingAdvisor` ở `+300`.

Ví dụ cấu hình:

~~~java
@Bean
ChatClient chatClient(ChatModel chatModel, SessionService sessionService) {
    return ChatClient.builder(chatModel)
        .defaultAdvisors(
            SessionAdvisors.builder(sessionService).build()
        )
        .build();
}

Flux<String> ask(ChatClient client, String sessionId, String question) {
    return client.prompt()
        .user(question)
        .advisors(SessionAdvisors.session(sessionId))
        .stream()
        .content();
}
~~~

`SessionAdvisors.session(sessionId)` phải có trong **mỗi** request. Nếu thiếu ID, SessionMemoryAdvisor báo lỗi thay vì dùng session mặc định. Nếu mỗi lần lại tạo một session ID mới, model sẽ không thấy turn trước; nếu mọi user dùng chung một ID, hội thoại có thể bị trộn và lộ dữ liệu.

### Kiểm tra chính xác cái gì đã được lưu

Với Session Memory 2.1, phân biệt:

- **Event log**: mọi message/event đã append, bao gồm phần lịch sử bị compaction che khỏi prompt.
- **Active view**: những message memory advisor thực sự đưa lại vào prompt.
- **Prompt của model round**: active view đã kết hợp với message mới của turn hiện tại.

Tool-call integrity rất quan trọng: assistant message có tool call phải được theo sau bởi tool response phù hợp; nếu cắt giữa cặp, provider có thể từ chối prompt. Session Memory giữ cửa sổ theo turn và có read guard phát `WARN` khi cặp tool call/result không đầy đủ. Nếu một `EventFilter` loại `TOOL` message nhưng vẫn giữ assistant tool call, read guard có thể loại cả cặp khỏi prompt, khiến người dùng thấy “mất kết quả tool”.

Nếu tự gắn `ToolCallingAdvisor` và memory advisor, kiểm tra `conversationHistoryEnabled`/`disableInternalConversationHistory()`. Với auto-registered advisor, Spring AI nhận diện `MemoryAdvisor` nằm trong loop và tắt internal history tương ứng để tránh ghi lặp. Một custom advisor sai order hoặc một memory adapter tự viết có thể tạo lịch sử trùng hay bỏ sót.

### Hai turn cùng session đang chạy song song

Session Memory không tự serialize request theo session. Nếu hai tool loops cùng ghi vào một session, message có thể xen kẽ hoặc turn sau đóng một tool call của turn trước khi nó còn đang chạy. Ứng dụng phải **xếp hàng/serialize** theo session ID hoặc từ chối request mới khi turn trước chưa kết thúc. Đừng dùng `synchronized` trên toàn bộ ChatClient vì như vậy mọi user phải chờ nhau; khóa/queue phải theo từng session.

## 8. ToolContext đúng nhưng callback vẫn thấy null

Nếu `@Tool` có tham số `ToolContext`:

~~~java
@Tool(name = "lookup_delivery", description = "Tra cứu giao hàng")
public String lookupDelivery(
        @ToolParam(description = "Mã đơn hàng") String orderId,
        ToolContext context) {

    String tenantId = (String) context.getContext().get("tenantId");
    if (tenantId == null) {
        throw new IllegalStateException("Missing trusted tenantId");
    }
    return deliveryService.findForTenant(tenantId, orderId);
}
~~~

Phải truyền context ở request:

~~~java
chatClient.prompt()
    .user(question)
    .tools(deliveryTools)
    .toolContext(Map.of(
        "tenantId", authenticatedTenantId,
        "requestId", requestId
    ))
    .stream()
    .content();
~~~

Nếu callback nhìn thấy null, kiểm tra:

1. `toolContext(...)` có được thêm vào **đúng ChatClient prompt** hay không.
2. Callback có đúng signature cho `ToolContext` và có chuyển tiếp context khi bọc `ToolCallback` không.
3. Có tự tạo `Prompt`/`ToolCallingChatOptions` ở model round sau mà quên chuyển context không.
4. Có gọi lại model/tool từ một nested `subscribe()` khác hoặc scheduler với context mới không.
5. Dữ liệu trong context có thật sự đến từ principal/tenant đã xác thực không.

Không sửa bằng cách cho model tự điền `tenantId` trong tool schema: đó là lỗ hổng cross-tenant access. Service vẫn phải kiểm tra authorization trên tài nguyên thực tế.

## 9. Truy vết vòng tool bằng advisor đúng vị trí

`ToolCallingAdvisor` có order mặc định `HIGHEST_PRECEDENCE + 300`. Một `StreamAdvisor` order `+400` nằm **bên trong** vòng và nhìn thấy các chunk của từng model iteration, kể cả những tool-call chunks mà stream bên ngoài đã lọc.

Ví dụ advisor quan sát lightweight:

~~~java
import org.springframework.ai.chat.client.ChatClientRequest;
import org.springframework.ai.chat.client.ChatClientResponse;
import org.springframework.ai.chat.client.advisor.api.StreamAdvisor;
import org.springframework.ai.chat.client.advisor.api.StreamAdvisorChain;
import org.springframework.core.Ordered;
import reactor.core.publisher.Flux;

public final class StreamDiagnosticsAdvisor implements StreamAdvisor {

    private final ChatProgressSink progress;

    public StreamDiagnosticsAdvisor(ChatProgressSink progress) {
        this.progress = progress;
    }

    @Override
    public String getName() {
        return "StreamDiagnosticsAdvisor";
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 400;
    }

    @Override
    public Flux<ChatClientResponse> adviseStream(
            ChatClientRequest request,
            StreamAdvisorChain chain) {
        return chain.nextStream(request)
            .doOnSubscribe(s -> progress.modelRoundStarted())
            .doOnNext(chunk -> progress.modelChunkObserved(chunk))
            .doOnError(progress::modelRoundFailed)
            .doFinally(progress::modelRoundFinished);
    }
}
~~~

`ChatProgressSink` là interface do ứng dụng định nghĩa; nó nên publish event nhỏ, non-blocking và được gắn với request cụ thể. Không dùng một sink mutable singleton toàn cục khiến user A nhận trạng thái của user B. Không ghi toàn bộ chunk/arguments vào logs.

**Advisor không chứng minh callback đã chạy.** Quan sát `tool.call.requested` chỉ cho biết mô hình đề xuất tool; tool có thể chưa được thực thi vì cần confirmation, bị chặn quyền hoặc chưa được resolve. Để biết trạng thái `tool.started`/`tool.succeeded`/`tool.failed`, instrument bên trong `ToolCallback` hoặc service nghiệp vụ.

Nếu ứng dụng đã custom `ToolAdvisor`, đừng đăng ký thêm một tool advisor để quan sát: `DefaultChatClient` chỉ chấp nhận một tool advisor trong chain. Observer nên triển khai `StreamAdvisor` thông thường.

## 10. Tại sao lỗi reactive chỉ xảy ra khi có tool?

Ở nhánh không gọi tool, model có thể stream non-blocking bình thường. Ở nhánh có tool:

~~~text
model streaming
   -> tool call hoàn chỉnh
   -> ToolCallingManager
   -> ToolCallback.call(...)
   -> repository/JDBC, RestClient hoặc code blocking khác
   -> result
   -> model streaming round kế tiếp
~~~

Vì thế cùng endpoint có thể chạy tốt với câu hỏi dễ nhưng đứng khi truy vấn nghiệp vụ. Trong Spring AI 2.1, đường tool calling còn imperative, dù `ChatClient.stream()` là reactive. Dùng thread dump, tracing và timed callback để xác định thread nào thực sự thực thi `ToolCallback.call(...)` trong bản Spring AI/provider đang dùng.

Các biện pháp:

- Nếu provider có client bất đồng bộ thực sự, ưu tiên API non-blocking ở những phần điều phối do ứng dụng sở hữu.
- Nếu callback buộc phải dùng JDBC/REST sync, chạy nó trong executor/scheduler được quản lý đúng tại ranh giới blocking, tránh event-loop; kiểm tra thực tế bằng thread name và test dưới tải.
- Đặt deadline/timeout tại client HTTP/DB cụ thể, không chỉ timeout cho SSE.
- Dùng bulkhead hoặc giới hạn concurrency với external service chậm.
- Theo dõi queue length và số request đang chờ boundedElastic, vì chuyển blocking sang pool riêng không loại bỏ quá tải.
- Với workflow dài, trả request ID và stream event tiến độ từ job/service; không bắt HTTP connection giữ vô hạn khi một side effect cần chờ nhiều phút.

Không đơn giản thêm `publishOn(Schedulers.boundedElastic())` ở cuối Flux rồi kết luận tool callback đã được cách ly. Cần quan sát scheduling tại **đúng đoạn thực thi**.

## 11. Timeout, retry và cancel phải giữ đúng kết quả nghiệp vụ

Một operator như:

~~~java
Flux<String> limited = chatClient.prompt()
    .user(question)
    .tools(orderTools)
    .stream()
    .content()
    .timeout(Duration.ofSeconds(30));
~~~

`timeout(Duration)` trên Flux thường đo **khoảng im lặng giữa các tín hiệu onNext**. Nếu tool cần 35 giây nhưng không có token, stream có thể timeout ngay cả khi callback vẫn chạy và side effect có thể đã được commit. Timeout ở đường UI không chứng minh external operation thất bại.

Phân biệt:

- **Idle timeout**: không có tín hiệu mới trong một khoảng thời gian; có thể điều chỉnh khi tool đang chạy.
- **Deadline tổng request**: thời hạn kết thúc toàn bộ workflow; phải quản lý riêng và truyền đến service/tool theo khả năng.
- **HTTP connect/read timeout**: cấu hình tại client provider.
- **Cancellation**: downstream ngừng nhận; không bảo đảm interrupt một callback blocking hoặc rollback một external transaction.

Khi một tool thay đổi dữ liệu bị timeout, dùng trạng thái nghiệp vụ `UNKNOWN`, operation ID/idempotency key do server quản lý và cơ chế đối soát. Đừng tự `retry()` toàn bộ `chatClient.prompt().stream()`: resubscribe có thể phát lại model call, các tool đã chạy và gửi side effect lần nữa.

Nếu cần retry, chỉ retry tại tầng sở hữu operation với giới hạn attempts, backoff và idempotency. Với tool chỉ đọc, có thể dùng chính sách khác tool ghi. Khi client hủy SSE, tiếp tục quản lý trạng thái job/operation phía server nếu side effect có thể vẫn đang chạy; client kết nối lại để truy vấn trạng thái.

## 12. SSE, WebSocket và backpressure

Trong SSE hoặc WebSocket, client chậm có thể khiến buffer tăng:

- Đừng giữ toàn bộ token vào `collectList()` để rồi mới gửi.
- Nếu cần kênh event riêng cho tool status, dùng queue/broker theo request có giới hạn kích thước.
- Tách event có thể gộp (token/progress) khỏi event không nên mất (operation succeeded/failed). Với sự kiện quan trọng, lưu bền vững hoặc cho client tra cứu trạng thái.
- Không lưu một `Sinks.Many` cho tất cả người dùng rồi broadcast dữ liệu nhạy cảm.
- Định nghĩa hành vi khi queue đầy: drop/coalesce những tiến độ không quan trọng hoặc kết thúc stream có mã lỗi rõ ràng.
- Ghi nhận số subscriber, bytes/event đã gửi, overflow và canceled streams.

`ServerSentEvent` có `id` và `event`; nếu ứng dụng yêu cầu resume sau reconnect, lưu sequence per request và hỗ trợ `Last-Event-ID`. Một Reactor sink trong bộ nhớ không tự replay sau restart. WebSocket cần xử lý reconnect/resubscribe ở client, authentication và destination authorization ở server.

## 13. Quy trình chẩn đoán từ ngoài vào trong

Thực hiện theo thứ tự để tìm ranh giới lỗi nhanh:

1. **Client:** xem Network tab hoặc `curl -N`. Có status 200 và `text/event-stream`? Response có từng frame `data:` hay dồn tới cuối? Client dùng `EventSource` GET hay POST `fetch`?
2. **Controller:** có request log và `doOnSubscribe`? Có hơn một subscription? Có `block()`, `collectList()`, `last()` hoặc `subscribe()` tự gọi?
3. **ChatClient:** có chạy `.stream()` không? `ToolCallingAdvisor` có được auto-register không? Có custom `ToolAdvisor` hay disable auto-registration?
4. **Model:** round nào bắt đầu, chunk cuối ở thời điểm nào, model có trả complete tool call hay chỉ partial arguments? Provider có hỗ trợ streaming tool calls không?
5. **Tool:** callback nào bắt đầu? Thread name là gì? Có kết thúc? Timeout của DB/HTTP provider bao lâu? Có worker pool bị nghẽn?
6. **Memory:** session ID của từng turn có giống nhau không? Có quyền sở hữu không? Active history chứa tool result không? Có `WARN` về incomplete tool-call pair?
7. **Transport:** response đã flush ra socket chưa? Reverse proxy có buffering, idle timeout hoặc số kết nối tối đa gây nghẽn không?
8. **Cancellation/retry:** ai hủy publisher? Có thao tác side effect đang `UNKNOWN`? Có request nào bị replay bởi retry chung không?

Ghi kết luận theo mẫu:

~~~text
requestId=req-44
sessionId=conv-12 (đã xác thực)
modelRound=2
lastModelChunkAt=10:00:02.100
toolName=lookup_delivery
toolStartedAt=10:00:02.120
toolFinishedAt=10:00:07.440
streamLastEmitAt=10:00:07.610
streamFinalSignal=ON_COMPLETE
threadAtTool=boundedElastic-3
diagnosis=Độ trễ provider 5.32s; không phải deadlock Reactor
~~~

Trên production, dùng request/tool IDs và timestamp đã được xác thực/lọc, không log raw credentials hay thông tin đơn hàng. Timestamp đơn giản có thể chưa đủ nếu các instance lệch đồng hồ; dùng monotonic duration cho latency và trace IDs cho tương quan chéo service.

## 14. Ma trận lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra/khắc phục |
| --- | --- | --- |
| SSE không có token tới khi kết thúc | `collectList`, `blockLast` hoặc proxy buffering | Trả `Flux` trực tiếp; kiểm tra flush và proxy |
| UI im lặng trong lúc tra cứu | `content()` chỉ phát text, callback đang chạy | Phát tool progress riêng; đo latency callback |
| Model có tool call nhưng callback không chạy | Auto ToolCallingAdvisor tắt hoặc thiếu tool | Kiểm tra advisor chain/registration |
| Partial tool-call JSON không gọi callback | Chưa có complete ToolCallPart | Chờ complete call; không parse delta |
| `block()` lỗi trên event-loop | Sync operation trong reactive thread | Compose non-blocking hoặc offload đúng nguồn |
| Đã thêm boundedElastic mà vẫn nghẽn | Chỉ chuyển downstream `publishOn`; upstream tool còn blocking | Instrument thread ở callback; chuyển đúng execution boundary |
| Có token nhưng browser không hiện dần | Frontend parser, fetch reader hoặc proxy | So sánh `curl -N` với Network tab |
| ToolContext mất tenant | Không truyền `toolContext` ở round sau, wrapper bỏ context | Propagate explicit context và validate server-side |
| Turn 2 quên kết quả | Session ID mới, memory chưa cấu hình | `SessionAdvisors` + ID ổn định đã authorize |
| Prompt bị loại tool result | Lịch sử thiếu cặp call/result, EventFilter bỏ TOOL | Kiểm tra event log, active view, read guard WARN |
| Hai chat xen kẽ lịch sử | Hai turn cùng session chạy song song | Serialize theo session |
| Stream cancel nhưng tool vẫn làm | Callback blocking không bị interrupt ngay | Theo dõi operation và reconcile, không retry mù |
| Stream kết thúc dù tool đang chờ duyệt | Tool Call Confirmation cố ý pause | Kiểm tra metadata awaiting decision và luồng resume |
| Nhiều lần gửi email sau lỗi | `retry` cả ChatClient turn | Idempotency và retry có scope theo operation |

## 15. Kiểm thử tái hiện và xác nhận sửa lỗi

Kiểm thử nên tái hiện từng dạng lỗi bằng fake model, fake callback và HTTP test client:

| Kịch bản | Kiểm tra |
| --- | --- |
| Stream chỉ có text | Subscriber nhận nhiều token và `ON_COMPLETE` |
| Tool call rồi text | Callback chạy một lần; round sau nhận tool result |
| Tool chạy chậm nhưng không lỗi | Tool progress vẫn có; stream không bị coi là failed chỉ vì không có token |
| Callback blocking trên event-loop | Test phát hiện thread blocking hoặc BlockHound trong môi trường phù hợp |
| Callback timeout sau side effect | Ghi `UNKNOWN`; không chạy lại operation với key mới |
| Model chỉ gửi partial tool call | Callback chưa chạy; complete call mới trigger thực thi |
| Không cung cấp session ID | SessionMemoryAdvisor báo lỗi có chủ đích |
| Hai turn liên tiếp cùng ID | Turn sau nhận active view đúng |
| Hai turn đồng thời cùng session | App serialize hoặc từ chối turn thứ hai |
| ToolContext qua scheduler/wrapper | Tenant/request ID không mất; callback không nhận actor ID do model tạo |
| SSE client disconnect | Phát `CANCEL`; cleanup subscription; operation có trạng thái rõ |
| Proxy buffering | Integration test xác nhận mỗi SSE event được flush khi phát sinh |
| Queue bị đầy | Không mất event nghiệp vụ quan trọng, không tăng RAM vô hạn |

Với Reactor, dùng `StepVerifier` để kiểm tra số chunk, completion và error; dùng `StepVerifier.withVirtualTime(...)` cho timeout/timer khi có thể. Với WebFlux, dùng `WebTestClient` để xác minh media type, SSE event name/ID, cancellation và thời điểm nhận. Khi muốn xác định thread thực thi callback, fake tool có thể ghi tên thread và duration; test dưới tải nhỏ sẽ phát hiện việc event-loop bị giữ bất thường.

### Minh họa StepVerifier cho Flux có timeout

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.concat(
            Mono.just("token đầu"),
            Mono.delay(Duration.ofSeconds(10)).map(i -> "token sau")
        )
        .timeout(Duration.ofSeconds(5)))
    .expectNext("token đầu")
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
~~~

Ví dụ này chỉ chứng minh **idle timeout của Flux**; nó chưa kiểm thử Spring AI hay tool callback. Để kiểm thử nghiệp vụ, thêm fake `ChatModel` trả tool call và fake provider có thể commit trước khi mất response, rồi assert operation ledger, không phát sinh side effect trùng.

## Bài thực hành

Xây dựng assistant tra cứu đơn hàng có `lookup_order` và `lookup_delivery`, dùng `ChatClient.stream()`, Spring WebFlux SSE và Session Memory 2.1. Tạo ba lỗi có chủ đích trong môi trường test:

1. Thêm một lời gọi repository blocking trực tiếp vào `doOnNext` để quan sát độ trễ/luồng; sau đó bọc đúng nguồn bằng `Mono.fromCallable(...).subscribeOn(boundedElastic())` và so sánh.
2. Bỏ `SessionAdvisors.session(sessionId)` ở turn thứ hai; xem lỗi và so sánh với việc giữ session ID ổn định. Tiếp tục giả lập hai turn cùng session chạy đồng thời và chứng minh cơ chế serialize.
3. Cho fake provider chậm rồi model trả tool call trong khi `.stream().content()` không phát text; thêm observer advisor và callback events để phân biệt khoảng lặng hợp lệ với callback không kết thúc.

Viết test xác minh cả số model rounds, tool execution count, lịch sử tool result, Reactor final signal và event stream phía client. Với tool có side effect, giả lập timeout sau commit và xác nhận hệ thống trả trạng thái chưa xác minh, không retry toàn bộ chat.

Sau khi hoàn thành, hãy giải thích: Vì sao `.stream()` không bảo đảm callback non-blocking? Vì sao `publishOn(boundedElastic())` cuối Flux có thể không sửa được luồng upstream đang bị chặn? Vì sao một session ID và một Reactor Context không phải cùng một loại dữ liệu?

## Ghi nhớ

Streaming bị “treo” có thể là khoảng chờ tool hợp lệ, provider không phát text, publisher chưa subscribe, proxy buffering, một callback blocking giữ event-loop hoặc tool loop đang chờ confirmation. Hãy đo các ranh giới rõ ràng từ subscription đến model round, callback, session và transport. Trong Spring AI 2.1, `ToolCallingAdvisor` quản lý vòng tool, `.stream().content()` chỉ chuyển text, Session Memory giữ ngữ cảnh giữa các turn và `ToolContext` mang metadata cho callback. Offload **đúng nguồn blocking**, propagate identity/context có chủ đích, serialize theo session, phân biệt timeout với side effect failure và kiểm thử cả cancellation lẫn tool-call integrity.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 — ChatClient streaming / Implementation Notes](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI 2.1.0 — Session Memory ChatClient Integration](https://docs.spring.io/spring-ai/reference/api/session/chat-client.html)
- [Spring Framework — WebFlux Controller Return Values / SSE](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — WebClient Synchronous Use](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html)
- [Reactor — FAQ: Wrap a Synchronous Blocking Call](https://projectreactor.io/docs/core/release/reference/faq.html)
- [Reactor — Adding Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)

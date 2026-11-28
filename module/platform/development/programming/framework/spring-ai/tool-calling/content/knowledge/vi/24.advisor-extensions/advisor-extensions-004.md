# Xử lý cả đường gọi đồng bộ và đường streaming

Khi mở rộng advisor trong Spring AI, một tính năng chạy đúng với `ChatClient.call()` chưa chắc đã hoạt động với `ChatClient.stream()`. Đường đồng bộ làm việc với một phản hồi hoàn chỉnh; đường streaming phát ra nhiều phần dữ liệu theo thời gian. Nếu advisor chỉ chặn đường đồng bộ, nó có thể bỏ qua luồng streaming. Nếu áp dụng cách xử lý đồng bộ vào `Flux`, nó có thể làm mất khả năng phát từng phần, tăng độ trễ, gây lỗi luồng hoặc làm sai vòng tool calling.

Trong module **SPRING_AI_TOOL_CALLING**, vấn đề càng quan trọng: mô hình có thể yêu cầu công cụ bằng `@Tool` hoặc `ToolCallback`, ứng dụng thực thi công cụ qua `ToolCallingManager`, rồi gửi kết quả trở lại mô hình. Một advisor tùy chỉnh dùng để ghi nhận sự kiện, giới hạn chính sách, điều chỉnh request hoặc quan sát kết quả phải xử lý đúng cả hai chế độ và tôn trọng quyền thực thi từ ứng dụng.

Bài viết sử dụng API **Spring AI 2.1.0**: `CallAdvisor`, `StreamAdvisor`, `BaseAdvisor`, `ToolCallingAdvisor`, `ChatClientRequest` và `ChatClientResponse`. Các ví dụ tập trung vào luồng điều phối của `ChatClient`. Chi tiết ở các nhánh Spring AI 1.x có thể khác, đặc biệt vì Spring AI 2.x chuyển vòng tool calling từ `ChatModel` sang `ToolCallingAdvisor`.

## 1. Phân biệt đường đồng bộ và streaming

Hai cách gọi thông thường:

~~~java
// Đồng bộ: nhận câu trả lời sau khi hoàn thành.
String answer = chatClient.prompt()
    .user("Đơn ORD-8F31A2 đang ở đâu?")
    .tools(orderTools)
    .call()
    .content();

// Streaming: nhận các phần nội dung khi được phát ra.
Flux<String> contentStream = chatClient.prompt()
    .user("Đơn ORD-8F31A2 đang ở đâu?")
    .tools(orderTools)
    .stream()
    .content();
~~~

Trong đường đồng bộ, `.call()` chờ phản hồi, và `.content()` trả nội dung được trích ra từ phản hồi. Trong đường streaming, `.stream().content()` trả `Flux<String>`; luồng được xử lý khi có subscriber. Hai đoạn trên có thể cho ra cùng một nội dung cuối nhưng **không cùng lifecycle**.

| Khía cạnh | Đồng bộ `call()` | Streaming `stream()` |
|---|---|---|
| API advisor | `CallAdvisor` | `StreamAdvisor` |
| Method | `adviseCall(...)` | `adviseStream(...)` |
| Chain | `CallAdvisorChain.nextCall(...)` | `StreamAdvisorChain.nextStream(...)` |
| Kiểu kết quả tại advisor | `ChatClientResponse` | `Flux<ChatClientResponse>` |
| Thời điểm quan sát | Khi nhận được phản hồi đầy đủ | Khi từng chunk được phát; có complete/error/cancel |
| Cách xử lý điển hình | Validate request, gọi chain, quan sát response | Biến đổi/thăm dò Flux mà không làm mất streaming |
| Rủi ro | Timeout, exception, gọi lặp | Blocking event-loop, subscribe nhiều lần, bỏ sót cancellation, gom cả stream |

**Lưu ý:** streaming nội dung trả lời không có nghĩa callback Java được khai báo bằng `@Tool` tự biến thành công cụ reactive. Nhiều tool có phương thức đồng bộ gọi REST/SDK; vòng tool calling có thể thực thi tool rồi tiếp tục stream câu trả lời. Cần phân biệt streaming ở kết nối model–client với kiểu thực thi của dịch vụ nghiệp vụ.

## 2. Giao diện advisor trong Spring AI

Spring AI 2.1.0 đặt các giao diện trong package `org.springframework.ai.chat.client.advisor.api`.

~~~java
public interface CallAdvisor extends Advisor {
    ChatClientResponse adviseCall(
        ChatClientRequest request,
        CallAdvisorChain chain
    );
}

public interface StreamAdvisor extends Advisor {
    Flux<ChatClientResponse> adviseStream(
        ChatClientRequest request,
        StreamAdvisorChain chain
    );
}
~~~

Khi cần tiếp tục xử lý bởi advisor kế tiếp hoặc chat model, gọi:

~~~java
// Đường đồng bộ
ChatClientResponse result = callChain.nextCall(request);

// Đường streaming
Flux<ChatClientResponse> chunks = streamChain.nextStream(request);
~~~

`ChatClientRequest` chứa `Prompt` cùng `context` dành cho advisor chain. `ChatClientResponse` bọc phản hồi model và context của chain. `getOrder()` trên `Advisor` quy định thứ tự các advisor; `getName()` cung cấp tên phục vụ logs/observability.

Một advisor có thể chỉ implement `CallAdvisor` hoặc chỉ `StreamAdvisor` nếu chức năng của nó thực sự chỉ áp dụng cho một chế độ. Tuy nhiên, nếu cùng `ChatClient` phục vụ cả REST đồng bộ lẫn SSE streaming, những chính sách chung như kiểm soát truy cập, giới hạn nghiệp vụ và audit nên được triển khai cho cả hai đường.

## 3. Mô hình thực thi của advisor chain

Mỗi advisor có thể kiểm tra/biến đổi request, gọi advisor kế tiếp, rồi xử lý response. Chain vận hành như một ngăn xếp:

~~~mermaid
sequenceDiagram
    participant U as Ứng dụng
    participant A as Advisor A (order nhỏ)
    participant B as Advisor B (order lớn)
    participant M as ChatModel
    U->>A: Request
    A->>B: nextCall / nextStream
    B->>M: nextCall / nextStream
    M-->>B: Response hoặc Flux chunks
    B-->>A: Response hoặc Flux chunks
    A-->>U: Kết quả
~~~

Giá trị order **nhỏ hơn chạy trước** ở chiều request và chạy sau ở chiều response. Nếu hai advisor có cùng order, không nên phụ thuộc vào thứ tự của chúng.

Với streaming, chiều phản hồi là một publisher, không phải một giá trị đã có sẵn. Advisor A chỉ nhận được một `Flux` từ B; các chunks đến sau khi có subscription. Vì vậy, các thao tác cần làm ở thời điểm nhận từng chunk phải nằm trong reactive pipeline.

Ví dụ khác nhau:

~~~java
// Đồng bộ: lệnh sau nextCall chạy khi đã có phản hồi.
ChatClientResponse response = chain.nextCall(request);
audit.recordCompletion();
return response;

// Streaming: lệnh sau nextStream chạy khi Flux được tạo,
// có thể trước khi có chunk đầu tiên hoặc chưa có subscription.
Flux<ChatClientResponse> flux = chain.nextStream(request);
audit.recordCompletion(); // SAI nếu muốn ghi lúc stream hoàn tất.
return flux;
~~~

Trên đường streaming, dùng `doOnComplete` khi stream thành công hoặc `doFinally` khi cần xử lý cả complete, error và cancel.

## 4. Vai trò của ToolCallingAdvisor trên cả hai đường

Trong Spring AI 2.1.0, `DefaultChatClient` tự đăng ký một `ToolCallingAdvisor`, trừ khi được cấu hình tắt. Advisor này triển khai cả `CallAdvisor` và `StreamAdvisor`, đồng thời đánh dấu `ToolAdvisor` để framework bảo đảm chỉ có một advisor phụ trách vòng tool calling trong chain.

Vòng xử lý khái quát:

~~~mermaid
flowchart TD
    A["ChatClient.call() hoặc .stream()"] --> B[ToolCallingAdvisor]
    B --> C[Gửi definitions đến model]
    C --> D{Model yêu cầu tool?}
    D -- Không --> E[Trả phản hồi/stream cuối]
    D -- Có --> F[ToolCallingManager chọn và chạy ToolCallback]
    F --> G[Ghép ToolResponseMessage vào history]
    G --> C
~~~

Đường đồng bộ và đường streaming có **cùng trách nhiệm nghiệp vụ**: giữ ID lời gọi công cụ, thực thi callback theo quyền đã xác thực, nối kết quả vào lịch sử và tiếp tục cho đến khi model không còn yêu cầu công cụ. Khác biệt ở cách nhận các response chunks và lúc xác định được một tool call hoàn chỉnh.

### Quan hệ với advisor tùy chỉnh

Một advisor quan sát thông thường chỉ implement `CallAdvisor`/`StreamAdvisor` và để `ToolCallingAdvisor` quản lý tool loop. Không đánh dấu advisor quan sát bằng `ToolAdvisor`, vì marker này dành cho advisor thực sự thay thế việc điều phối công cụ.

Nếu ứng dụng thêm **hai** implementation của `ToolAdvisor`, framework từ chối xây dựng chain nhằm ngăn tool được thực thi hai lần.

## 5. Ví dụ: một advisor quan sát cả call và stream

Giả sử ứng dụng muốn ghi thời gian xử lý và số chunk để theo dõi chất lượng phục vụ mà không ghi nội dung người dùng, arguments hay kết quả tool. Advisor sau hoạt động trong cả hai chế độ.

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClientRequest;
import org.springframework.ai.chat.client.ChatClientResponse;
import org.springframework.ai.chat.client.advisor.api.CallAdvisor;
import org.springframework.ai.chat.client.advisor.api.CallAdvisorChain;
import org.springframework.ai.chat.client.advisor.api.StreamAdvisor;
import org.springframework.ai.chat.client.advisor.api.StreamAdvisorChain;
import org.springframework.core.Ordered;

import reactor.core.publisher.Flux;

public final class ToolLifecycleAdvisor
        implements CallAdvisor, StreamAdvisor {

    private static final Logger log =
        LoggerFactory.getLogger(ToolLifecycleAdvisor.class);

    @Override
    public String getName() {
        return "tool-lifecycle";
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 400;
    }

    @Override
    public ChatClientResponse adviseCall(
            ChatClientRequest request,
            CallAdvisorChain chain) {

        long started = System.nanoTime();
        try {
            ChatClientResponse response = chain.nextCall(request);
            log.info(
                "mode=call outcome=success elapsedMs={}",
                elapsedMs(started)
            );
            return response;
        }
        catch (RuntimeException error) {
            log.warn(
                "mode=call outcome=error type={} elapsedMs={}",
                error.getClass().getSimpleName(),
                elapsedMs(started)
            );
            throw error;
        }
    }

    @Override
    public Flux<ChatClientResponse> adviseStream(
            ChatClientRequest request,
            StreamAdvisorChain chain) {

        return Flux.defer(() -> {
            long started = System.nanoTime();
            AtomicLong chunkCount = new AtomicLong();

            return chain.nextStream(request)
                .doOnNext(chunk -> chunkCount.incrementAndGet())
                .doOnError(error -> log.warn(
                    "mode=stream errorType={}",
                    error.getClass().getSimpleName()
                ))
                .doFinally(signal -> log.info(
                    "mode=stream termination={} chunks={} elapsedMs={}",
                    signal,
                    chunkCount.get(),
                    elapsedMs(started)
                ));
        });
    }

    private static long elapsedMs(long started) {
        return TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - started
        );
    }
}
~~~

Giải thích các quyết định trong ví dụ:

- `adviseCall` gọi `chain.nextCall(request)` đúng một lần, trả nguyên `ChatClientResponse`, và ném lại exception.
- `adviseStream` trả `Flux<ChatClientResponse>`, không `block()`, không `collectList()` và không tự `subscribe()`.
- `Flux.defer` khởi tạo bộ đếm và thời điểm bắt đầu cho **mỗi subscription**, tránh dùng chung trạng thái đếm giữa các request.
- `doOnNext` chỉ đếm chunk, không sửa output và không log dữ liệu nhạy cảm.
- `doOnError` nhận thông tin lỗi; `doFinally` chạy khi complete, error **hoặc cancel**.
- `Ordered.HIGHEST_PRECEDENCE + 400` đặt advisor ở **bên trong** `ToolCallingAdvisor` mặc định (order +300), nên có thể quan sát từng vòng model call của tool loop.

Đây là advisor quan sát, không phải bộ thực thi tool. Phần xác thực quyền, validation và xử lý lỗi nghiệp vụ vẫn đặt trong callback hoặc application service.

## 6. Đăng ký advisor và gọi hai chế độ

Dùng một `ChatClient` với advisor vừa tạo:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
    .defaultAdvisors(new ToolLifecycleAdvisor())
    .build();
~~~

Tool có thể là đối tượng chứa method `@Tool`:

~~~java
public final class OrderTools {

    private final OrderService orderService;

    public OrderTools(OrderService orderService) {
        this.orderService = orderService;
    }

    @Tool(
        description = "Tra cứu trạng thái đơn hàng mà người dùng được phép xem"
    )
    public OrderStatusResult getOrderStatus(
            @ToolParam(description = "Mã đơn hàng")
            String orderNumber,
            ToolContext toolContext) {

        Actor actor = verifiedActor(toolContext);
        return orderService.getAuthorizedStatus(
            actor, orderNumber
        );
    }
}
~~~

`OrderService`, `Actor` và `verifiedActor(...)` là thành phần nghiệp vụ minh họa. `Actor` phải được tạo từ thông tin xác thực phía server; không yêu cầu model cung cấp vai trò hay tenant trong JSON arguments.

~~~java
// Gọi đồng bộ
String answer = chatClient.prompt()
    .user("Tra cứu trạng thái đơn ORD-8F31A2")
    .tools(orderTools)
    .toolContext(Map.of("actor", authenticatedActor))
    .call()
    .content();

// Gọi streaming
Flux<String> answerFlux = chatClient.prompt()
    .user("Tra cứu trạng thái đơn ORD-8F31A2")
    .tools(orderTools)
    .toolContext(Map.of("actor", authenticatedActor))
    .stream()
    .content();
~~~

Cùng một tool và advisor được dùng trong cả hai lời gọi. Trong một controller WebFlux, có thể trả `answerFlux` cho client dưới dạng SSE và để framework quản lý subscription, hủy luồng và kết nối.

Chú ý: `.tools(...)` bổ sung tool của request vào `.defaultTools(...)` đã cấu hình trên client, không thay thế chúng. Với tool có side effect hoặc quyền hạn đặc biệt, chỉ công bố theo phạm vi request phù hợp.

## 7. Khi nào dùng BaseAdvisor thay vì hai interface?

`BaseAdvisor` mở rộng cả `CallAdvisor` và `StreamAdvisor`. Nó cung cấp phương thức `before(...)` và `after(...)` dùng chung cho các thao tác sửa request hoặc xem phản hồi tổng hợp, giảm số lượng code trùng.

~~~java
public final class PromptTagAdvisor implements BaseAdvisor {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 100;
    }

    @Override
    public ChatClientRequest before(
            ChatClientRequest request,
            AdvisorChain chain) {

        Prompt updated = request.prompt().augmentUserMessage(
            "Hãy trình bày trạng thái đơn hàng ngắn gọn, rõ ràng."
        );

        return request.mutate()
            .prompt(updated)
            .build();
    }

    @Override
    public ChatClientResponse after(
            ChatClientResponse response,
            AdvisorChain chain) {

        return response;
    }
}
~~~

`BaseAdvisor` phù hợp khi logic chỉ là biến đổi request và xử lý response tổng hợp, không cần điều khiển từng chunk. Mặc định của nó triển khai cả hai đường, dùng scheduler phù hợp cho xử lý streaming.

Khi cần kiểm soát việc stream, quan sát từng chunk, thay đổi cách xử lý complete/error/cancel, hoặc cần retry có chủ đích, nên triển khai trực tiếp cả `CallAdvisor` và `StreamAdvisor` như `ToolLifecycleAdvisor`.

**Đừng nhầm:** `BaseAdvisor.after(...)` trong chế độ streaming xử lý một phản hồi đã tổng hợp; nó không tự động chạy một lần cho từng chunk. Nếu cần quan sát từng fragment để đẩy trạng thái lên UI, hãy dùng `StreamAdvisor.adviseStream(...)`.

## 8. Chọn vị trí bên trong hay bên ngoài tool loop

Thứ tự advisor không chỉ ảnh hưởng trước/sau, mà còn quyết định việc advisor quan sát **một yêu cầu người dùng** hay **từng vòng gọi model** trong tool calling.

Spring AI 2.1.0 đặt `ToolCallingAdvisor.DEFAULT_ORDER` ở `Ordered.HIGHEST_PRECEDENCE + 300`.

| Order của advisor tùy chỉnh | Vị trí so với tool loop | Hành vi |
|---|---|---|
| Nhỏ hơn +300, ví dụ +100 | Bên ngoài | Có xu hướng thấy đầu request và kết quả cuối sau toàn bộ vòng tool |
| Lớn hơn +300, ví dụ +400 | Bên trong | Chạy mỗi lần `ToolCallingAdvisor` gọi xuống model trong vòng tool |
| Bằng +300 | Không bảo đảm thứ tự | Nên tránh |

Ví dụ người dùng hỏi: “Kiểm tra tồn kho rồi tính phí vận chuyển”. Model có thể gọi `lookupInventory` ở vòng một, `calculateShipping` ở vòng hai, rồi trả lời ở vòng ba.

~~~text
Outer Advisor (+100)
  ToolCallingAdvisor (+300)
    Inner Advisor (+400): model iteration #1 -> lookupInventory
    Tool execution -> ToolResponseMessage
    Inner Advisor (+400): model iteration #2 -> calculateShipping
    Tool execution -> ToolResponseMessage
    Inner Advisor (+400): model iteration #3 -> final answer
Outer Advisor nhận kết quả cuối
~~~

Vì vậy:

- Đếm số **request của người dùng**: đặt advisor ở ngoài tool loop.
- Đếm số **lần gọi model / quan sát tool-call intent**: đặt advisor ở trong tool loop.
- Đo **thời gian toàn tác vụ**: đo bên ngoài.
- Đo **thời gian từng vòng model**: đo bên trong.
- Kiểm soát **thực thi tool**: đưa authorization vào tool/application service, không phụ thuộc vào logging advisor.

Lưu ý rằng advisor ở ngoài loop có thể không thấy các tool call message trung gian trong response cuối. Không thể dùng dữ liệu cuối rồi suy ra chính xác mọi vòng nếu chưa có instrument bên trong.

## 9. Streaming là dữ liệu tăng dần, không phải phản hồi đã hoàn chỉnh

Khi model stream text, các `ChatClientResponse` nhận được có thể chứa phần nội dung ngắn, metadata hoặc delta của tool call. Không nên giả định mỗi chunk là một câu đầy đủ hoặc một JSON object đầy đủ.

Ví dụ nội dung:

~~~text
chunk 1: "Đơn "
chunk 2: "ORD-8F31A2 "
chunk 3: "đang được "
chunk 4: "vận chuyển."
~~~

Nếu advisor muốn kiểm tra chuỗi đầu ra để nhận diện dữ liệu nhạy cảm hoặc cấu trúc JSON, không thể xử lý mỗi chunk độc lập theo giả định một chunk chứa toàn bộ từ, câu hoặc document. Dữ liệu có thể bị chia ở bất kỳ ranh giới nào.

Có ba kiểu xử lý:

1. **Quan sát từng chunk**: đếm, ghi metric, đẩy sự kiện theo tiến độ, giữ nguyên luồng.
2. **Tổng hợp để đọc kết quả**: dùng aggregator nếu cần báo cáo cuối cùng mà vẫn trả stream.
3. **Biến đổi theo trạng thái**: cần parser incremental hoặc bộ đệm có giới hạn, đặc biệt nếu yêu cầu kiểm tra định dạng/PII.

Nếu tác vụ yêu cầu phải thẩm định toàn bộ nội dung trước khi phát cho người dùng, streaming raw text từng phần có thể không đáp ứng yêu cầu. Hãy chọn luồng kiểm duyệt thích hợp hoặc trì hoãn phát cho đến khi đủ dữ liệu để quyết định.

## 10. Quan sát kết quả cuối mà không chặn streaming

Spring AI cung cấp `ChatClientMessageAggregator` để tổng hợp các `ChatClientResponse` thành một phản hồi phục vụ đọc/ghi nhận cuối vòng mà không bắt ứng dụng tự `collectList()`.

Ví dụ bên trong một `StreamAdvisor`:

~~~java
@Override
public Flux<ChatClientResponse> adviseStream(
        ChatClientRequest request,
        StreamAdvisorChain chain) {

    Flux<ChatClientResponse> source = chain.nextStream(request);

    return new ChatClientMessageAggregator()
        .aggregateChatClientResponse(
            source,
            complete -> audit.recordSafeSummary(complete)
        );
}
~~~

`audit.recordSafeSummary(...)` là API minh họa của ứng dụng; nó chỉ nên trích xuất thông tin an toàn như response finish reason hoặc cờ có/không tool call, không ghi raw prompts/arguments/results tùy tiện.

Aggregator hữu ích khi muốn quan sát **response đã tổng hợp**. Nó không phải nơi tự thực thi tool call. Trong vòng streaming của `ToolCallingAdvisor`, framework chịu trách nhiệm tổng hợp các chunks cần thiết để phát hiện **tool call hoàn chỉnh** rồi chạy `ToolCallingManager`.

Nếu chỉ cần metrics số chunk và thời gian, dùng `doOnNext` / `doFinally` là nhẹ hơn. Nếu callback tổng hợp tốn CPU hoặc bộ nhớ, cần xem xét kích thước output và giới hạn tài nguyên.

## 11. Tool call arguments dạng streaming: xử lý partial và complete

Một số model/provider hỗ trợ phát từng fragment của tool-call arguments. Spring AI 2.1.0 đưa fragment đó vào `ToolCallPart` được đánh dấu `StreamingParts.isPartial(part)`.

Ví dụ model đang tạo arguments:

~~~text
partial 1: {"order
partial 2: Number":"ORD
partial 3: -8F31A2"}
complete: {"orderNumber":"ORD-8F31A2"}
~~~

Các mảnh partial **không phải một tool call hoàn chỉnh**. Chúng có thể không tạo thành JSON hợp lệ, và không được thực thi qua `ToolCallingManager`. Spring AI chỉ xử lý lời gọi đầy đủ theo hợp đồng tool calling.

Ví dụ theo dõi tiến trình ở UI:

~~~java
chatClient.prompt()
    .user("Kiểm tra đơn ORD-8F31A2")
    .tools(orderTools)
    .stream()
    .chatResponse()
    .subscribe(response ->
        response.getResults().forEach(generation -> {
            for (MessagePart part : generation.getOutput().getParts()) {
                if (part instanceof ToolCallPart toolCallPart
                        && StreamingParts.isPartial(part)) {

                    ToolCall delta = toolCallPart.toolCall();

                    progressSink.accept(
                        delta.id(),
                        delta.name()
                    );
                }
            }
        })
    );
~~~

Các class `MessagePart`, `ToolCallPart` và `StreamingParts` theo API streaming của Spring AI; `progressSink` là callback ứng dụng nhận sự kiện. Ví dụ chỉ đẩy **ID và tên tool**, tránh hiển thị fragments arguments vì chúng có thể chứa dữ liệu cá nhân hoặc thông tin nhạy cảm. Trong REST controller thực tế, để reactive runtime quản lý subscription; không subscribe trực tiếp để biến một request WebFlux thành tác vụ chạy ngoài lifecycle kết nối.

`AssistantMessage.getToolCalls()` và `ChatResponse.hasToolCalls()` bỏ qua partial tool-call parts. Framework chỉ thực thi sau khi có thông tin đầy đủ; nếu advisor tự xử lý partial như yêu cầu thật, có thể gọi tool quá sớm hoặc gọi nhiều lần khi stream ra từng fragment.

`stream().content()` chỉ tập trung vào text, nên không thể dùng nó để quan sát phần tool-call argument delta vốn không có text. Khi cần sự kiện tool call, đọc `chatResponse()` hoặc quan sát ở advisor/observability layer thích hợp.

## 12. Mở rộng hook của ToolCallingAdvisor phải làm đủ hai phía

Nếu cần can thiệp **bên trong vòng điều phối tool** thay vì chỉ quan sát trước/sau, Spring AI 2.1.0 cho phép subclass `ToolCallingAdvisor` và override các hook đồng bộ, streaming tương ứng.

| Giai đoạn vòng tool | Đường đồng bộ | Đường streaming | Mục đích |
|---|---|---|---|
| Khởi tạo vòng | `doInitializeLoop` | `doInitializeLoopStream` | Chuẩn bị index, session, context |
| Trước mỗi vòng model | `doBeforeCall` | `doBeforeStream` | Bổ sung/lọc tool definitions, cập nhật request |
| Sau mỗi vòng model | `doAfterCall` | `doAfterStream` | Audit, kiểm tra response đã tổng hợp |
| Kết thúc vòng | `doFinalizeLoop` | `doFinalizeLoopStream` | Tổng kết metrics, làm sạch tài nguyên |
| Chuẩn bị lịch sử vòng kế | `doGetNextInstructionsForToolCall` | `doGetNextInstructionsForToolCallStream` | Giữ message và tool response đúng thứ tự |

Ví dụ khung ở mức method:

~~~java
@Override
protected ChatClientRequest doBeforeCall(
        ChatClientRequest request,
        CallAdvisorChain chain) {

    return restrictToolsToAuthorizedSet(request);
}

@Override
protected ChatClientRequest doBeforeStream(
        ChatClientRequest request,
        StreamAdvisorChain chain) {

    return restrictToolsToAuthorizedSet(request);
}
~~~

`restrictToolsToAuthorizedSet(...)` là helper minh họa, cần trả `ChatClientRequest` mới với options/tool definitions được lọc hợp lệ. Cùng một policy phải áp dụng cho cả hai đường. Helper **không thay thế** authorization khi tool thực thi, bởi bản thân callback vẫn phải kiểm tra quyền trên tài nguyên cụ thể.

Một số lưu ý:

- `doAfterStream` nhận phản hồi đã được tổng hợp cho một iteration; nó không chạy một lần mỗi chunk.
- `doFinalizeLoopStream` trả `Flux<ChatClientResponse>`, nên cần giữ nguyên hành vi reactive nếu chỉ muốn quan sát.
- Không override hook chỉ ở đồng bộ rồi giả định streaming tự làm tương đương.
- Nếu thay thế advisor quản lý tool loop, bản thay thế phải được nhận diện là `ToolAdvisor`; đừng đăng ký thêm một `ToolAdvisor` thứ hai.
- `ToolSearchToolCallingAdvisor` là ví dụ thực tế: nó dùng hook của cả hai đường để tìm và công bố dần các tool, còn vòng thực thi kế thừa từ `ToolCallingAdvisor`.

Đối với yêu cầu chỉ thêm logging/tracing, một advisor bình thường nằm bên trong loop ít rủi ro hơn subclass bộ điều phối tool.

## 13. Không block trong đường reactive

Ví dụ sai:

~~~java
@Override
public Flux<ChatClientResponse> adviseStream(
        ChatClientRequest request,
        StreamAdvisorChain chain) {

    List<ChatClientResponse> all =
        chain.nextStream(request).collectList().block();

    return Flux.fromIterable(all);
}
~~~

Lỗi thiết kế ở đây là **gom toàn bộ luồng và block**. Kết quả có thể mất streaming, chiếm bộ nhớ theo kích thước output, làm chậm time-to-first-token và gây lỗi khi gọi trên thread không cho phép blocking.

Nếu advisor phải dùng một dịch vụ **đồng bộ/blocking** để lấy policy hoặc metadata trước khi tiếp tục stream, hãy đặt việc đó trên scheduler phù hợp và trả Flux cho caller:

~~~java
@Override
public Flux<ChatClientResponse> adviseStream(
        ChatClientRequest request,
        StreamAdvisorChain chain) {

    return Mono.fromCallable(
            () -> policyService.loadForRequest(request)
        )
        .subscribeOn(Schedulers.boundedElastic())
        .flatMapMany(policy -> {
            ChatClientRequest safeRequest =
                applyPolicy(request, policy);

            return chain.nextStream(safeRequest);
        });
}
~~~

`loadForRequest(...)` và `applyPolicy(...)` là helpers của ứng dụng. Dùng `boundedElastic` cho đoạn blocking là một lựa chọn thực tiễn, nhưng cần giới hạn timeout, queue và thread pool. Không nên gọi hàng loạt API blocking không giới hạn trong advisor hoặc trên event-loop.

Reactive pipeline có thể chuyển thread giữa các operator. Không dùng `ThreadLocal` như nguồn duy nhất cho danh tính hoặc tenant; hãy truyền ngữ cảnh xác thực phù hợp qua `ChatClientRequest.context()`, `ToolContext` server-derived và/hoặc Reactor Context theo thiết kế ứng dụng.

## 14. Error, timeout, retry và cancel trong streaming

Đường đồng bộ thường kết thúc bằng phản hồi hoặc exception. Streaming có thêm trạng thái **cancel** khi client rời trang, ngắt SSE hoặc hủy subscription.

### Xử lý lỗi

~~~java
return chain.nextStream(request)
    .doOnError(error -> metrics.recordFailure(
        error.getClass().getSimpleName()
    ))
    .doFinally(signal -> metrics.recordTerminal(
        signal.name()
    ));
~~~

Đây là ví dụ callback trong `adviseStream`. `metrics` là thành phần ứng dụng; tránh ghi exception message thô vì có thể chứa thông tin nội bộ.

**Không** dùng `onErrorResume(error -> Flux.empty())` như quy tắc chung. Cách đó biến lỗi thành một luồng trống và có thể khiến client hiểu nhầm request đã thành công. Với UI/SSE, nên có chính sách hiển thị trạng thái lỗi rõ ràng và kết thúc response phù hợp.

### Timeout

Có thể đặt giới hạn thời gian với Reactor `timeout(...)`, nhưng phải quyết định timeout cho:

- **Time-to-first-token**: thời gian chờ phần đầu tiên.
- **Khoảng lặng giữa các chunks**: khoảng lâu nhất không có dữ liệu.
- **Thời gian toàn tác vụ**: có thể gồm nhiều model calls và tool calls.

`Flux.timeout(Duration)` thường kiểm soát khoảng chờ giữa các phần tử; nó không tự đảm bảo giới hạn tổng thời gian tuyệt đối nếu stream liên tục phát dữ liệu. Để đặt total deadline, cần deadline chung hoặc cơ chế cancel ngoài phù hợp với ứng dụng. Thời gian chờ của HTTP/SDK callback cũng phải nằm trong ngân sách.

### Retry

~~~java
return chain.nextStream(request)
    .retry(1); // Nguy hiểm nếu request/tool có side effect.
~~~

`retry` hoạt động bằng cách **đăng ký lại publisher**, có thể khiến model call và các tool calls được thực thi lại. Với tool hủy đơn, chuyển tiền, tạo giao dịch hoặc gửi email, retry mù có thể gây hành động trùng.

Chỉ retry khi đã phân loại lỗi, định nghĩa điều kiện an toàn và áp dụng idempotency key/transaction cho callback có side effect. Thông thường xử lý retry ở boundary cụ thể của HTTP/SDK và đưa trạng thái lỗi rõ ràng cho caller an toàn hơn retry toàn bộ advisor chain.

### Cancellation

Khi subscriber hủy stream:

- `doOnComplete` có thể **không** chạy.
- `doFinally(CANCEL)` vẫn được gọi cho subscription đã hoạt động.
- Cancellation không đảm bảo một tool có side effect đã chạy sẽ tự rollback.
- Không tiếp tục đẩy sự kiện vào connection đã đóng; nên dùng resource lifecycle phù hợp.
- Không ghi response thành “thành công hoàn tất” chỉ vì đã phát một vài token.

## 15. Backpressure và giới hạn tài nguyên

Reactor `Flux` cung cấp cơ chế demand/backpressure, nhưng hiệu quả thực tế phụ thuộc provider/model adapter và cách truyền dữ liệu qua HTTP, SSE hoặc WebSocket. Không nên giả định rằng giảm tốc độ subscriber có thể dừng mô hình hoặc callback nghiệp vụ ngay lập tức.

Những vấn đề thường gặp:

| Tình huống | Rủi ro | Cách xử lý |
|---|---|---|
| Client đọc chậm | Buffer tăng hoặc latency cao | Backpressure/buffer được giới hạn; cân nhắc drop chỉ cho telemetry không quan trọng |
| Advisor dùng `collectList()` | Gom toàn bộ phản hồi vào RAM | Giữ streaming hoặc dùng aggregator khi thực sự cần |
| Log từng chunk với I/O blocking | Chặn pipeline, tăng overhead | Ghi metrics nhẹ hoặc dùng async sink có giới hạn |
| Tool synchronous tốn nhiều thời gian | Không có nội dung mới trong lúc tool chạy | Timeout tại tool, sự kiện tiến độ riêng, UI phản ánh trạng thái |
| Client cancel nhưng tool đang chạy | Side effect có thể vẫn hoàn thành | Idempotency và cancellation policy rõ ràng |
| Subscriber trùng | Có thể tạo model/tool call lần nữa | Không tự `subscribe()` nhiều lần vào publisher cold |

Có thể dùng `limitRate`, `onBackpressureBuffer` với giới hạn hoặc cơ chế điều tiết tại gateway, nhưng cần hiểu tác động tới dữ liệu và không áp dụng “drop” lên nội dung trả lời nếu làm mất ý nghĩa câu nói. Các sự kiện telemetry có thể chịu mất mát; nội dung tool result và message giao thức thường không thể bị bỏ.

## 16. Phân biệt ba loại ngữ cảnh trong ứng dụng

Việc triển khai advisor streaming dễ gặp lỗi bảo mật nếu nhầm lẫn giữa ngữ cảnh model, ngữ cảnh advisor và ngữ cảnh thực thi tool.

| Ngữ cảnh | Mục đích | Ví dụ | Có gửi cho mô hình? |
|---|---|---|---|
| Prompt / tool input schema | Dữ liệu và arguments model cần | Mã đơn hàng, loại truy vấn | Có |
| `ChatClientRequest.context()` | Chia sẻ metadata giữa các advisors | Trace ID, policy ID, session key | Không tự động trở thành prompt |
| `ToolContext` | Dữ liệu server truyền cho callback lúc thực thi | Actor đã xác thực, tenant ID được xác nhận | Không đưa vào tool arguments gửi model |

Với cùng một `ChatClient` xử lý nhiều request đồng thời, không lưu `currentUser`, `lastPrompt`, `sessionId` hoặc `chunkCount` vào field mutable của singleton advisor. Thông tin theo request nên nằm trong request context hoặc biến local của mỗi subscription.

Ví dụ lựa chọn không an toàn:

~~~java
@Component
class UnsafeStreamingAdvisor {
    private String currentTenant; // Bị chia sẻ giữa các request
    private long chunkCount;      // Race condition khi stream song song
}
~~~

Thay bằng giá trị context được server thiết lập và bộ đếm local:

~~~java
return Flux.defer(() -> {
    AtomicLong countForThisSubscriber = new AtomicLong();

    return chain.nextStream(request)
        .doOnNext(chunk ->
            countForThisSubscriber.incrementAndGet()
        );
});
~~~

Authorization cần được kiểm tra khi callback thực thi; việc advisor xác định một tool có thể xuất hiện trong request không đủ để cho phép truy cập mọi tài nguyên.

## 17. Kiểm thử cả hai đường và nhiều vòng tool calling

Có thể kiểm thử behavior của advisor độc lập với LLM thật bằng mock chain và response. Không cần xây dựng ứng dụng mới chỉ để kiểm tra tính chất này.

### Kiểm thử đồng bộ không làm thay đổi phản hồi

~~~java
@Test
void callPassesResponseThrough() {
    ChatClientRequest request = mock(ChatClientRequest.class);
    CallAdvisorChain chain = mock(CallAdvisorChain.class);
    ChatClientResponse expected = mock(ChatClientResponse.class);

    when(chain.nextCall(request)).thenReturn(expected);

    ToolLifecycleAdvisor advisor = new ToolLifecycleAdvisor();
    ChatClientResponse actual = advisor.adviseCall(request, chain);

    assertThat(actual).isSameAs(expected);
    verify(chain, times(1)).nextCall(request);
}
~~~

### Kiểm thử streaming phát nguyên chunks và hoàn tất

~~~java
@Test
void streamPassesChunksThroughWithoutCollecting() {
    ChatClientRequest request = mock(ChatClientRequest.class);
    StreamAdvisorChain chain = mock(StreamAdvisorChain.class);

    ChatClientResponse first = mock(ChatClientResponse.class);
    ChatClientResponse second = mock(ChatClientResponse.class);

    when(chain.nextStream(request))
        .thenReturn(Flux.just(first, second));

    StepVerifier.create(
            new ToolLifecycleAdvisor().adviseStream(request, chain)
        )
        .expectNext(first, second)
        .verifyComplete();

    verify(chain, times(1)).nextStream(request);
}
~~~

### Kiểm thử lỗi và cancel

Test streaming cần có case `Flux.error(...)` và hủy trước khi hoàn tất. Với `StepVerifier`, có thể xác minh advisor truyền lỗi xuống subscriber và xử lý tín hiệu cancel qua `doFinally`. Nếu advisor có side effects như audit hoặc metrics, mock recorder để xác minh outcome `ON_ERROR` / `CANCEL`. Đối với test của example `ToolLifecycleAdvisor` chỉ dùng logger, nên cần test behavior stream hoặc thay logger bằng recorder có thể spy.

### Ma trận test nên có

| Tình huống | Đồng bộ | Streaming |
|---|---|---|
| Không có tool call | Trả response thường | Phát chunks thường, complete |
| Một tool call | Tool chạy một lần, câu trả lời đúng | Tool chạy một lần, stream kết quả cuối |
| Nhiều lượt tool call | Giữ ID và lịch sử, không nhân đôi kết quả | Không thực thi partial arguments, chỉ tool call hoàn chỉnh |
| Tool callback lỗi | Không lộ stack trace, xử lý exception theo policy | Luồng báo lỗi đúng, không phát “thành công giả” |
| User không có quyền | Không gọi API nghiệp vụ | Không gọi API nghiệp vụ dù đã nhận partial |
| Client hủy giữa chừng | Không áp dụng | Nhận cancel, dọn resource, không tự rollback side effect |
| Retry hoặc resubscribe | Không gọi tool hai lần ngoài ý muốn | Kiểm tra idempotency khi publisher chạy lại |
| Observability advisor bên trong tool loop | Đếm đúng số vòng | Đếm đúng số chunks/vòng, cleanup mỗi subscription |
| Observability advisor bên ngoài tool loop | Đếm request người dùng | Đếm stream toàn tác vụ |
| Thao tác ghi dữ liệu | Xác nhận/authorization | Tương tự, không coi chunk là sự chấp thuận |

Nên có integration test dùng `ChatModel` giả lập để tạo một response có tool call, một tool result và một response cuối. Chạy cùng scenario qua `.call()` và `.stream()`, rồi xác minh cùng một kết quả nghiệp vụ, số lần gọi callback và thứ tự message. Test streaming nên dùng `StepVerifier` và không phụ thuộc vào tốc độ mạng thật.

## 18. Lỗi thường gặp khi mở rộng advisor

| Sai lầm | Biểu hiện | Cách xử lý |
|---|---|---|
| Chỉ implement `CallAdvisor` | `.stream()` không được quan sát hoặc áp dụng cùng policy | Implement `StreamAdvisor` hoặc dùng `BaseAdvisor` đúng trường hợp |
| Gọi `nextStream` rồi ghi “complete” ngay | Metrics hoàn tất trước khi có dữ liệu | Dùng `doOnComplete` / `doFinally` |
| `block()` hoặc `collectList()` | Mất streaming, tốn bộ nhớ | Để `Flux` đi qua không chặn |
| Log nguyên `ChatClientRequest` hoặc tool result | Lộ prompt, PII, token, arguments | Chỉ ghi metadata đã kiểm soát |
| Coi mỗi partial tool argument là lời gọi | Callback có thể chạy sớm hoặc lặp | Chỉ framework xử lý complete tool calls |
| Dùng mutable singleton field cho request state | Rò dữ liệu chéo session, race condition | Dùng request/context hoặc subscription local |
| Dùng `ThreadLocal` xuyên reactive boundary | Mất hoặc nhầm actor/tenant | Truyền context tường minh, dùng security context chuẩn |
| Đặt advisor sai order | Không quan sát được từng vòng tool | Chọn trong/ngoài `ToolCallingAdvisor` có chủ đích |
| Đăng ký hai `ToolAdvisor` | Chain khởi tạo thất bại | Chỉ một tool loop advisor |
| `retry()` toàn chuỗi | Tool có side effect có thể chạy lại | Retry có điều kiện và idempotency |
| Hủy stream rồi giả định mọi việc rollback | Dữ liệu có thể đã được ghi | Chính sách giao dịch và reconciliation độc lập |
| Che lỗi bằng `Flux.empty()` | Client tưởng tác vụ đã hoàn thành | Phân loại và truyền lỗi an toàn |

## 19. Checklist trước khi đưa vào production

- [ ] Advisor được thiết kế rõ dùng `BaseAdvisor` hay cả `CallAdvisor` và `StreamAdvisor`.
- [ ] Logic cần thiết hiện diện ở cả `adviseCall` và `adviseStream`.
- [ ] Thứ tự `getOrder()` phù hợp với mục tiêu quan sát ngoài hay trong tool loop.
- [ ] Không thêm hai `ToolAdvisor` cùng một chain.
- [ ] Đường streaming không `block()`, không gom toàn bộ chunks khi không cần.
- [ ] Metrics phân biệt success, error và cancel; không log raw sensitive payload.
- [ ] Partial tool-call arguments không bị thực thi.
- [ ] Tool callback nhận `ToolContext` đáng tin cậy và kiểm tra quyền khi thực thi.
- [ ] Không giữ mutable request/session state trong singleton advisor.
- [ ] Có giới hạn timeout, retry và idempotency rõ ràng cho tool có side effect.
- [ ] Backpressure, client disconnect, buffering và latency được xem xét.
- [ ] Có unit tests cho sync, stream, error, cancel và resubscription.
- [ ] Có integration tests cho nhiều lượt tool call và kết quả cuối ở cả hai đường.
- [ ] Đã kiểm tra API và hành vi theo đúng Spring AI version mà ứng dụng dùng.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Advisors API](https://docs.spring.io/spring-ai/reference/api/advisors.html): `CallAdvisor`, `StreamAdvisor`, chain, order, `BaseAdvisor`, streaming patterns.
- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): vòng `ToolCallingAdvisor`, streaming tool-call arguments, `ToolContext`, giới hạn tool calls và bảo mật.
- [Spring AI 2.1.0 — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html): hook tương ứng giữa sync và streaming, vị trí advisor trong vòng tool, quan sát và user-controlled streaming.
- [Spring AI 2.1.0 — ChatClient API](https://docs.spring.io/spring-ai/reference/api/chatclient.html): cách gọi `.call()`, `.stream()`, đăng ký advisors và tools.
- [Reactor 3 — Flux Reference](https://projectreactor.io/docs/core/release/reference/): semantics subscription, backpressure, error, cancellation và scheduling.

**Điểm cần nhớ:** advisor mở rộng tốt phải giữ nguyên ngữ nghĩa của cả hai đường gọi. Với sync, xử lý một response hoàn chỉnh; với streaming, xử lý một `Flux` có lifecycle riêng và có thể bị hủy. Khi có tool calling, hãy đặt advisor đúng vị trí trong/ngoài vòng `ToolCallingAdvisor`, chỉ chạy tool call hoàn chỉnh và luôn kiểm soát quyền thực thi tại ứng dụng.


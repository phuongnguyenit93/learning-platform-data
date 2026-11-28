# Đưa trạng thái công cụ ra SSE hoặc WebSocket

Khi một assistant gọi công cụ, người dùng thường cần biết hệ thống đang làm gì: mô hình đang chuẩn bị gọi tool nào, tool đã bắt đầu chạy chưa, kết quả đã hoàn tất hay gặp lỗi, và câu trả lời cuối đã sẵn sàng hay chưa. Spring AI cung cấp vòng tool calling và API streaming; ứng dụng có thể chuyển các trạng thái này thành sự kiện để gửi tới giao diện qua **Server-Sent Events (SSE)** hoặc **WebSocket**.

Điểm quan trọng là phải phân biệt **ý định gọi tool** với **thực thi tool**. Một chunk do mô hình phát ra có thể chỉ chứa một phần tên hoặc arguments của tool. Callback chỉ chạy sau khi mô hình gửi tool call hoàn chỉnh và `ToolCallingManager` bắt đầu thực thi. Vì vậy, hãy phát sự kiện `tool.call.delta` khi quan sát arguments đang được tạo, và phát `tool.started`, `tool.succeeded` hoặc `tool.failed` tại lớp thực thi callback.

Với phần lớn ứng dụng, có thể giữ vòng lặp mặc định của `ChatClient` và thêm một advisor quan sát bên trong `ToolCallingAdvisor`. Chỉ tự điều phối toàn bộ vòng lặp khi workflow cần kiểm soát từng bước.

## 1. Luồng trạng thái cần gửi cho giao diện

Một request chat có thể tạo ra nhiều vòng mô hình và nhiều lần gọi tool. Giao diện cần nhận được các sự kiện theo cùng một `requestId`:

| Event type | Ý nghĩa | Nơi phát |
| --- | --- | --- |
| `request.accepted` | Server đã nhận yêu cầu chat | Controller hoặc orchestration service |
| `assistant.delta` | Một phần nội dung câu trả lời đang được sinh | Luồng `ChatClient.stream()` |
| `tool.call.delta` | Mô hình đang gửi từng phần thông tin của tool call | Advisor quan sát chunk |
| `tool.call.requested` | Mô hình đã gửi tool call hoàn chỉnh | Advisor quan sát response |
| `tool.started` | Callback thực sự bắt đầu chạy | Decorator quanh `ToolCallback` |
| `tool.succeeded` | Callback trả kết quả thành công | Decorator quanh `ToolCallback` |
| `tool.failed` | Callback phát sinh lỗi | Decorator quanh `ToolCallback` |
| `assistant.completed` | Vòng chat đã kết thúc thành công | Orchestration service |
| `assistant.failed` | Request chat kết thúc do lỗi | Orchestration service |

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant UI as Trình duyệt
    participant API as SSE/WebSocket endpoint
    participant TC as ToolCallingAdvisor
    participant Model as Chat model
    participant Manager as ToolCallingManager
    participant Tool as ToolCallback

    UI->>API: Bắt đầu chat
    API-->>UI: request.accepted
    API->>TC: ChatClient.stream()
    TC->>Model: Prompt + tool definitions
    Model-->>TC: ToolCallPart / tool call
    TC-->>API: tool.call.delta / tool.call.requested
    TC->>Manager: executeToolCalls(...)
    Manager->>Tool: call(arguments, context)
    Tool-->>API: tool.started
    Tool-->>API: tool.succeeded hoặc tool.failed
    Tool-->>Manager: Tool result
    Manager-->>TC: Conversation history
    TC->>Model: Prompt tiếp theo
    Model-->>TC: Text chunks
    TC-->>API: assistant.delta
    TC-->>API: assistant.completed
    API-->>UI: Các event theo requestId
~~~

Sự kiện `tool.call.requested` chỉ nói rằng mô hình yêu cầu gọi công cụ. `tool.started` mới xác nhận callback đã được gọi. Một tool call có thể bị từ chối bởi confirmation policy, không tìm thấy callback hoặc bị chặn trước khi thực thi; khi đó không được phát `tool.started` giả.

## 2. Chọn SSE hay WebSocket

| Tiêu chí | SSE | WebSocket |
| --- | --- | --- |
| Hướng truyền | Server gửi sự kiện tới client | Hai chiều |
| Giao thức | HTTP, `text/event-stream` | Kết nối được nâng cấp từ HTTP |
| Phù hợp | Stream text, tiến độ tool, trạng thái xử lý | Tiến độ kết hợp lệnh hủy, duyệt, tương tác hai chiều |
| Tổ chức sự kiện | Event name, id và data | Message protocol; có thể dùng STOMP |
| Tự kết nối lại | `EventSource` hỗ trợ reconnect; replay phải do server thiết kế | Client tự quản lý reconnect và subscribe lại |

Nếu trình duyệt chỉ cần nhận trạng thái và nội dung assistant, SSE thường đơn giản hơn. Nếu client cần gửi lệnh hủy, phê duyệt tool hoặc nhiều loại message qua cùng một kết nối, WebSocket phù hợp hơn. Spring WebFlux hỗ trợ trả `Flux<ServerSentEvent<T>>` từ controller; Spring WebSocket có thể dùng STOMP để định tuyến message theo destination.

## 3. Thiết kế event contract

Đừng gửi trực tiếp object nội bộ của Spring AI ra trình duyệt. Tạo một DTO ổn định cho giao thức UI:

~~~java
import java.time.Instant;
import java.util.Map;

public record ToolUiEvent(
        String requestId,
        long sequence,
        String type,
        String toolName,
        String toolCallId,
        String executionId,
        Instant occurredAt,
        Map<String, Object> data) {
}
~~~

Ý nghĩa các trường:

- `requestId`: ID do server tạo để phân biệt request và cô lập sự kiện giữa người dùng.
- `sequence`: số thứ tự tăng dần trong một request, giúp client sắp xếp hoặc loại bỏ event trùng.
- `type`: loại sự kiện như `tool.started` hoặc `assistant.delta`.
- `toolName`: tên tool mà mô hình yêu cầu.
- `toolCallId`: ID của tool call do model/provider trả về, nếu có.
- `executionId`: ID do ứng dụng tạo cho một lần callback thực thi.
- `occurredAt`: thời điểm server phát sự kiện.
- `data`: payload nhỏ, chỉ chứa trường UI cần.

`toolCallId` và `executionId` có ý nghĩa khác nhau. `ToolCallback.call(...)` nhận JSON input và `ToolContext`, không nhận model tool-call ID. Vì vậy decorator quanh callback có thể tạo `executionId` riêng; muốn liên kết chính xác execution với `toolCallId` trong mọi trường hợp, cần truyền correlation ID qua một lớp điều phối tùy chỉnh. Không nên ghép bằng tên tool nếu cùng một response có nhiều call cùng tên.

Một payload mẫu:

~~~json
{
  "requestId": "req-7c12",
  "sequence": 8,
  "type": "tool.started",
  "toolName": "lookup_inventory",
  "toolCallId": null,
  "executionId": "exec-91a4",
  "occurredAt": "2026-11-27T04:30:12Z",
  "data": {
    "status": "RUNNING"
  }
}
~~~

Không đưa raw arguments, kết quả nghiệp vụ hoặc exception message vào event mặc định. Nếu UI cần thêm chi tiết, hãy thiết kế một schema allowlist và mask dữ liệu nhạy cảm trước khi publish.

## 4. Tạo event publisher riêng cho mỗi request

Mỗi request cần một event channel riêng. Không giữ một biến `currentRequestId` hoặc `currentSink` mutable trên singleton service, vì các chat đồng thời có thể gửi nhầm trạng thái cho nhau.

Ví dụ một event channel dùng Reactor `Sinks.Many`:

~~~java
import java.time.Instant;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

public final class RequestEventChannel {

    private final String requestId;
    private final AtomicLong sequence = new AtomicLong();
    private final Sinks.Many<ToolUiEvent> sink =
        Sinks.many().unicast().onBackpressureBuffer(
            new ArrayBlockingQueue<>(256));

    public RequestEventChannel(String requestId) {
        this.requestId = requestId;
    }

    public synchronized void publish(
            String type,
            String toolName,
            String toolCallId,
            String executionId,
            Map<String, Object> data) {

        ToolUiEvent event = new ToolUiEvent(
            requestId,
            sequence.incrementAndGet(),
            type,
            toolName,
            toolCallId,
            executionId,
            Instant.now(),
            data
        );

        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            // Ghi metric; không làm hỏng callback nghiệp vụ vì lỗi UI.
            // Với event lifecycle quan trọng, hãy persist hoặc kết thúc stream
            // theo chính sách overflow của ứng dụng.
        }
    }

    public Flux<ToolUiEvent> events() {
        return sink.asFlux();
    }

    public synchronized void complete() {
        sink.tryEmitComplete();
    }
}
~~~

Ví dụ dùng `unicast()` vì một request SSE có một subscriber. Sink này giữ lại event được phát trước khi subscriber đăng ký; queue `ArrayBlockingQueue` giới hạn buffer ở 256 event và `tryEmitNext` báo lỗi nếu buffer đầy. Hãy định nghĩa cách xử lý overflow, không để client chậm làm treo callback nghiệp vụ. Nếu nhiều subscriber cần nhận cùng một luồng, chọn sink hoặc event broker hỗ trợ multicast phù hợp.

## 5. Quan sát tool-call chunk bằng StreamAdvisor

Trong Spring AI 2.1, `ChatClient` tự đăng ký `ToolCallingAdvisor` với order mặc định `Ordered.HIGHEST_PRECEDENCE + 300`. Advisor có order lớn hơn sẽ nằm bên trong vòng tool calling và được gọi ở mỗi iteration. Có thể thêm một `StreamAdvisor` với order `+400` để quan sát các chunk của model:

~~~java
import java.util.Map;

import org.springframework.ai.chat.client.ChatClientRequest;
import org.springframework.ai.chat.client.ChatClientResponse;
import org.springframework.ai.chat.client.advisor.api.StreamAdvisor;
import org.springframework.ai.chat.client.advisor.api.StreamAdvisorChain;
import org.springframework.ai.chat.messages.part.StreamingParts;
import org.springframework.ai.chat.messages.part.ToolCallPart;
import org.springframework.core.Ordered;

import reactor.core.publisher.Flux;

public class ToolCallProgressAdvisor implements StreamAdvisor {

    private final RequestEventChannel events;

    public ToolCallProgressAdvisor(RequestEventChannel events) {
        this.events = events;
    }

    @Override
    public String getName() {
        return "ToolCallProgressAdvisor";
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
            .doOnNext(this::publishToolCallParts);
    }

    private void publishToolCallParts(ChatClientResponse response) {
        if (response.chatResponse() == null) {
            return;
        }

        response.chatResponse().getResults().forEach(generation ->
            generation.getOutput().getParts().forEach(part -> {
                if (part instanceof ToolCallPart toolPart) {
                    var call = toolPart.toolCall();
                    boolean partial = StreamingParts.isPartial(part);

                    events.publish(
                        partial ? "tool.call.delta" : "tool.call.requested",
                        call.name(),
                        call.id(),
                        null,
                        Map.of("partial", partial)
                    );
                }
            })
        );
    }
}
~~~

Advisor này chỉ quan sát response của model. Nó không thực thi tool và cũng không xác nhận callback đã bắt đầu. Trong ví dụ, `tool.call.delta` có thể xuất hiện nhiều lần khi model đang tạo arguments; `tool.call.requested` đại diện cho một `ToolCallPart` hoàn chỉnh được advisor nhìn thấy.

Một số provider stream arguments thành các `ToolCallPart` partial; provider khác chỉ gửi tool call hoàn chỉnh. Một delta partial chỉ chứa một đoạn arguments, thường chưa phải JSON hợp lệ. `ToolCallingManager` bỏ qua partial part và chỉ thực thi tool call hoàn chỉnh. Không parse hoặc gọi callback từ `tool.call.delta`.

`ToolCallingAdvisor` lọc tool-call chunks khỏi stream trả về cho caller; custom advisor nằm bên trong loop là side channel để giao diện vẫn quan sát được chúng. Advisor ví dụ chỉ implement `StreamAdvisor`, không implement marker `ToolAdvisor`, nên không tạo thêm một tool-calling loop thứ hai. Trong một advisor chain chỉ nên có một `ToolAdvisor`.

## 6. Phát trạng thái thực thi bằng ToolCallback decorator

Advisor biết mô hình đã yêu cầu tool. Để biết callback thật sự bắt đầu, thành công hoặc thất bại, bọc `ToolCallback` và publish event ngay quanh lời gọi delegate.

~~~java
import java.util.Map;
import java.util.UUID;
import java.util.function.Supplier;

import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.ai.tool.metadata.ToolMetadata;

public final class ReportingToolCallback implements ToolCallback {

    private final ToolCallback delegate;
    private final RequestEventChannel events;

    public ReportingToolCallback(
            ToolCallback delegate,
            RequestEventChannel events) {
        this.delegate = delegate;
        this.events = events;
    }

    @Override
    public ToolDefinition getToolDefinition() {
        return delegate.getToolDefinition();
    }

    @Override
    public ToolMetadata getToolMetadata() {
        return delegate.getToolMetadata();
    }

    @Override
    public String call(String toolInput) {
        return execute(() -> delegate.call(toolInput));
    }

    @Override
    public String call(String toolInput, ToolContext toolContext) {
        return execute(() -> delegate.call(toolInput, toolContext));
    }

    private String execute(Supplier<String> invocation) {
        String executionId = UUID.randomUUID().toString();
        String toolName = delegate.getToolDefinition().name();

        events.publish(
            "tool.started", toolName, null, executionId, Map.of()
        );

        try {
            String result = invocation.get();
            events.publish(
                "tool.succeeded", toolName, null, executionId, Map.of()
            );
            return result;
        }
        catch (RuntimeException ex) {
            events.publish(
                "tool.failed",
                toolName,
                null,
                executionId,
                Map.of("code", "TOOL_EXECUTION_FAILED")
            );
            throw ex;
        }
    }
}
~~~

Decorator giữ nguyên `ToolDefinition` và `ToolMetadata` của callback gốc, đồng thời chuyển tiếp cả hai overload `call(...)` để không làm mất `ToolContext`. Event `tool.failed` chỉ phát mã lỗi ổn định; không gửi `ex.getMessage()` ra trình duyệt.

Tạo callback đã bọc cho từng request:

~~~java
import java.util.Arrays;

import org.springframework.ai.support.ToolCallbacks;
import org.springframework.ai.tool.ToolCallback;

ToolCallback[] callbacks = Arrays.stream(
        ToolCallbacks.from(new WeatherTools(weatherService)))
    .map(callback -> (ToolCallback)
        new ReportingToolCallback(callback, events))
    .toArray(ToolCallback[]::new);
~~~

Ví dụ giả định `WeatherTools` dùng `WeatherService` do ứng dụng quản lý. Việc tạo decorator theo request giúp mỗi callback giữ đúng event channel của request đó. Nếu callback được đăng ký thành singleton bean dùng chung, không gắn event channel mutable của một request vào field của bean dùng chung.

## 7. Ghép text stream và tool events thành SSE

Với Spring WebFlux, controller có thể trả `Flux<ServerSentEvent<ToolUiEvent>>`. `ChatClient.stream().chatResponse()` cung cấp các chunk của assistant; event channel nhận trạng thái từ advisor và callback decorator.

Ví dụ service điều phối một request:

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.UUID;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.support.ToolCallbacks;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.util.StringUtils;

import reactor.core.publisher.Flux;

public class AssistantStreamService {

    private final ChatClient chatClient;
    private final WeatherService weatherService;

    public AssistantStreamService(
            ChatClient chatClient,
            WeatherService weatherService) {
        this.chatClient = chatClient;
        this.weatherService = weatherService;
    }

    public Flux<ToolUiEvent> stream(String question) {
        return Flux.defer(() -> {
            RequestEventChannel events =
                new RequestEventChannel(UUID.randomUUID().toString());
            events.publish(
                "request.accepted", null, null, null, Map.of()
            );

            ToolCallback[] callbacks = Arrays.stream(
                    ToolCallbacks.from(new WeatherTools(weatherService)))
                .map(callback -> (ToolCallback)
                    new ReportingToolCallback(callback, events))
                .toArray(ToolCallback[]::new);

            Flux<ToolUiEvent> modelRun = chatClient.prompt()
                .user(question)
                .tools(callbacks)
                .advisors(new ToolCallProgressAdvisor(events))
                .stream()
                .chatResponse()
                .doOnNext(response -> response.getResults().forEach(generation -> {
                    String text = generation.getOutput().getText();
                    if (StringUtils.hasText(text)) {
                        events.publish(
                            "assistant.delta", null, null, null,
                            Map.of("text", text)
                        );
                    }
                }))
                .thenMany(Flux.<ToolUiEvent>empty())
                .doOnComplete(() -> events.publish(
                    "assistant.completed", null, null, null, Map.of()))
                .onErrorResume(ex -> {
                    events.publish(
                        "assistant.failed", null, null, null,
                        Map.of("code", "CHAT_REQUEST_FAILED")
                    );
                    return Flux.empty();
                })
                .doFinally(signal -> events.complete());

            return Flux.merge(events.events(), modelRun);
        });
    }
}
~~~

Trong ví dụ, `Flux.defer(...)` tạo channel và callback mới cho mỗi lần subscribe. `Flux.merge(...)` đăng ký nhận tool events trước khi bắt đầu stream model; `doFinally(...)` đóng channel khi request kết thúc hoặc bị hủy. Khi triển khai, các DTO/event class và `WeatherTools` phải được định nghĩa trong ứng dụng.

Controller chuyển event thành SSE:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class ChatStreamController {

    private final AssistantStreamService assistant;

    public ChatStreamController(AssistantStreamService assistant) {
        this.assistant = assistant;
    }

    @PostMapping(
        value = "/api/chat/stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<ToolUiEvent>> stream(
            @RequestBody ChatRequest request) {

        return assistant.stream(request.message())
            .map(event -> ServerSentEvent.builder(event)
                .id(Long.toString(event.sequence()))
                .event(event.type())
                .build());
    }
}
~~~

`Flux<ServerSentEvent<T>>` cho phép Spring WebFlux ghi từng event theo kiểu streaming. Ví dụ dùng POST để nhận câu hỏi và trả event stream; browser `EventSource` chuẩn chỉ mở GET. Nếu cần dùng `EventSource`, tách thành hai bước: POST tạo request và trả `requestId`, sau đó GET `/api/chats/{requestId}/events` để subscribe. Với POST streaming, client có thể dùng `fetch()` và đọc response body theo từng chunk.

## 8. Đưa cùng event contract qua WebSocket

WebSocket phù hợp khi client cần gửi thêm lệnh như cancel, approve hoặc continue. Dùng STOMP giúp chuẩn hóa destination và subscription:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Client gửi yêu cầu tới `/app/chat.start` và subscribe `/user/queue/tool-status`. Server gửi event tới đúng người dùng:

~~~java
import java.security.Principal;

import org.springframework.stereotype.Controller;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;

@Controller
public class ChatSocketController {

    private final SimpMessagingTemplate messagingTemplate;
    private final AssistantStreamService assistantStreamService;

    public ChatSocketController(
            SimpMessagingTemplate messagingTemplate,
            AssistantStreamService assistantStreamService) {
        this.messagingTemplate = messagingTemplate;
        this.assistantStreamService = assistantStreamService;
    }

    @MessageMapping("/chat.start")
    public void start(ChatRequest request, Principal principal) {
        assistantStreamService.stream(request.message())
            .subscribe(event ->
                messagingTemplate.convertAndSendToUser(
                    principal.getName(),
                    "/queue/tool-status",
                    event
                )
            );
    }
}
~~~

Đoạn controller minh họa cách gửi event; ứng dụng thực tế cần lưu `Disposable` theo `requestId`, xử lý lỗi và hủy subscription khi client gửi lệnh cancel hoặc phiên kết nối kết thúc. Nếu một người dùng có nhiều chat đồng thời, client lọc theo `requestId` hoặc server dùng destination riêng cho từng request. Không broadcast event chứa dữ liệu riêng tư lên một `/topic` dùng chung.

Spring STOMP định tuyến message có prefix `/app` tới `@MessageMapping`; các destination `/topic` và `/queue` được broker xử lý. `convertAndSendToUser(...)` gửi event vào user destination của phiên đã xác thực.

## 9. Hiển thị arguments đang được tạo

Spring AI 2.1 biểu diễn nội dung assistant thành các `MessagePart`, trong đó có `TextPart`, `ReasoningPart`, `ToolCallPart` và `ToolResultPart`. Một số model/provider gửi tool arguments theo nhiều delta. `StreamingParts.isPartial(part)` cho biết part hiện tại là delta:

~~~java
for (MessagePart part : assistantMessage.getParts()) {
    if (part instanceof ToolCallPart toolPart
            && StreamingParts.isPartial(part)) {
        var call = toolPart.toolCall();
        ui.showToolProgress(call.id(), call.name());
    }
}
~~~

Chỉ dùng delta để cập nhật giao diện như “đang chuẩn bị tra cứu”. Không parse JSON từ từng mảnh, không gọi tool và không xem đây là xác nhận callback đã chạy. Arguments hoàn chỉnh sẽ được model gửi sau đó; một số provider không stream arguments mà chỉ gửi tool call hoàn chỉnh.

## 10. Bảo mật và cô lập request

Event stream có thể tiết lộ thông tin nghiệp vụ. Hãy áp dụng các nguyên tắc sau:

- Xác thực người dùng khi tạo request và khi mở SSE/WebSocket subscription.
- Kiểm tra người dùng có quyền xem `requestId` đó; ID khó đoán không thay thế authorization.
- Tạo `requestId` ở server, không tin ID hoặc tenant do model cung cấp.
- Chỉ phát tool name, status và mã lỗi allowlist; mặc định không phát arguments, tool result, SQL, token hoặc stack trace.
- Không gửi dữ liệu từ `ToolContext` ra event. Context có thể chứa tenant ID, user ID hoặc thông tin nội bộ.
- Tách event channel theo request; không lưu sink hiện tại trong singleton bean.
- Khi cần duyệt thao tác, dùng Tool Call Confirmation và xác thực người duyệt ở server; event chỉ thông báo đang chờ quyết định.

Spring AI cho phép truyền `ToolContext` đến callback mà không gửi dữ liệu đó cho mô hình. Điều này không đồng nghĩa dữ liệu context an toàn để phát ra SSE hoặc WebSocket; event publisher cần một allowlist độc lập.

## 11. Backpressure, cancellation và reconnect

Một request có thể phát text token, tool status và nhiều event khác. Nếu client đọc chậm hoặc mất kết nối:

- Giới hạn kích thước event queue và chọn cách xử lý khi đầy: drop các text delta cũ, gộp progress hoặc kết thúc stream với mã lỗi.
- Không chặn callback nghiệp vụ để chờ giao diện nhận event.
- Khi client hủy, dispose subscription và ngừng các bước tiếp theo nếu có thể.
- Đặt timeout cho model và service. Tool calling có thể chạy callback đồng bộ; hủy reactive stream không đảm bảo dừng ngay một lời gọi blocking đang thực thi.
- Dùng `sequence` để client phát hiện event trùng hoặc sai thứ tự.
- Nếu cần resume sau reconnect, lưu event theo `requestId` và replay từ `Last-Event-ID` của SSE hoặc sequence cuối cùng của WebSocket client.

Một `Sinks.Many` trong bộ nhớ chỉ giữ event trong vòng đời process/request. Nó không cung cấp replay sau restart. Workflow dài hoặc cần audit phải lưu trạng thái và event vào kho bền vững, hoặc dùng message broker.

## 12. Quan sát tool bằng Micrometer

Ngoài event cho giao diện, Spring AI phát Micrometer observation cho tool call dưới tên `spring.ai.tool`. Observation ghi nhận tên/metadata tool, thời gian thực thi và tracing context khi có tracer. Có thể dùng metrics/tracing để phân tích latency và lỗi ở backend.

Không nên dùng metrics thay cho trạng thái nghiệp vụ gửi tới UI. Ngược lại, không cần gửi toàn bộ arguments và results vào event chỉ để có khả năng debug. Spring AI mặc định không xuất tool arguments và results thành span attributes vì lý do nhạy cảm dữ liệu; chỉ bật khi đã đánh giá rủi ro và có chính sách lọc.

## 13. Ma trận kiểm thử

Kiểm thử cả advisor, callback decorator và endpoint transport:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Model không gọi tool | Chỉ có assistant events và `assistant.completed` |
| Model gọi một tool | Có `tool.call.requested`, `tool.started`, `tool.succeeded` theo thứ tự |
| Provider stream arguments | Có thể có nhiều `tool.call.delta`; không có callback nào chạy trước call hoàn chỉnh |
| Provider không stream arguments | Vẫn nhận `tool.started` và kết quả thực thi từ decorator |
| Callback phát sinh RuntimeException | Có `tool.failed`; exception vẫn được chuyển tiếp cho Spring AI xử lý |
| Nhiều tool call trong một response | Mỗi execution có `executionId` riêng; không trộn trạng thái |
| Hai request đồng thời | Không có event của request A xuất hiện trong stream B |
| Client ngắt kết nối | Subscription được dispose; callback blocking được xử lý theo timeout/cancellation policy |
| Queue đầy | Có hành vi overflow đã định nghĩa, không làm hỏng transaction nghiệp vụ |
| SSE reconnect | Replay đúng từ `Last-Event-ID` nếu ứng dụng bật persistence |
| WebSocket user khác | Không thể subscribe hoặc nhận event của request không thuộc quyền |
| Payload chứa dữ liệu nhạy cảm | Event serializer chỉ phát trường allowlist |

Với Spring WebFlux, dùng `WebTestClient` để kiểm tra `Content-Type: text/event-stream`, event name, ID và payload. Với STOMP, kiểm thử endpoint, subscribe destination, user routing và quyền truy cập. Dùng mock `ChatModel` để phát response có tool call xác định; dùng fake `ToolCallback` để kiểm tra sự kiện started/succeeded/failed mà không gọi dịch vụ thật.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ thấy text cuối, không thấy tool call | Chỉ subscribe stream bên ngoài `ToolCallingAdvisor` | Thêm observer advisor bên trong loop |
| Thấy tool name nhưng không thấy started | Đang quan sát model request, chưa instrument callback | Bọc `ToolCallback` hoặc instrument service |
| Tool started hai lần | Callback bị bọc lặp hoặc nhiều subscriber kích hoạt cùng request | Tạo một callback wrapper và một subscription cho mỗi request |
| Không thấy argument delta | Provider không stream tool arguments | Dựa vào event requested hoặc callback started |
| Giao diện parse JSON lỗi | Đang parse một `ToolCallPart` partial | Chỉ dùng delta để hiển thị tiến độ; chờ call hoàn chỉnh |
| Event của người khác xuất hiện | Dùng event sink hoặc topic toàn cục không có kiểm tra quyền | Tạo channel per-request và route theo principal |
| SSE ngắt nhưng tool vẫn chạy | Callback blocking không dừng ngay khi reactive stream bị cancel | Dùng timeout, cancellation token và client API có thể hủy |
| Event bị mất khi reconnect | Chỉ dùng sink trong bộ nhớ, không lưu replay | Persist event và xử lý `Last-Event-ID`/sequence |

## Bài thực hành

Xây dựng assistant tra cứu đơn hàng với ba tool: `lookup_order`, `lookup_delivery` và `lookup_invoice`.

Yêu cầu:

1. Phát `assistant.delta` để giao diện hiển thị câu trả lời đang sinh.
2. Dùng `ToolCallProgressAdvisor` để quan sát tool call chunks trong từng iteration.
3. Bọc từng `ToolCallback` để phát `tool.started`, `tool.succeeded` và `tool.failed`.
4. Tạo `requestId`, `sequence` và `executionId` riêng; xác minh hai request chạy đồng thời không trộn event.
5. Tạo endpoint SSE để client nhận event stream.
6. Tạo STOMP endpoint để client có thể gửi lệnh cancel và subscribe trạng thái theo user.
7. Không phát raw arguments, kết quả hóa đơn hoặc exception message ra client.
8. Viết test cho provider có partial arguments, provider chỉ trả complete tool call, callback lỗi và client disconnect.

Sau khi hoàn thành, hãy giải thích vì sao `tool.call.delta` không đồng nghĩa callback đã chạy, và vì sao `ToolCallingAdvisor` observer cùng `ToolCallback` decorator cung cấp hai loại thông tin khác nhau.

## Ghi nhớ

Để đưa trạng thái tool ra SSE hoặc WebSocket, hãy tách event quan sát mô hình khỏi event thực thi callback. Một `StreamAdvisor` có order lớn hơn `ToolCallingAdvisor.DEFAULT_ORDER` có thể quan sát các chunk của từng vòng; decorator quanh `ToolCallback` phát trạng thái started/succeeded/failed tại đúng thời điểm thực thi. Gắn event channel với từng request, định nghĩa payload ổn định, bảo vệ subscription theo người dùng và kiểm soát queue, cancellation cùng replay. SSE phù hợp với luồng server-to-client; WebSocket/STOMP phù hợp khi client cần tương tác hai chiều.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — ChatClient API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI 2.1.x — ToolCallback API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/ToolCallback.html)
- [Spring AI — Tool Calling Observability](https://docs.spring.io/spring-ai/reference/observability/index.html)
- [Spring Framework — WebFlux Server-Sent Events](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Reactor — Sinks and Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)

# Phân biệt luồng token của mô hình với tiến trình thực thi công cụ

Khi dùng streaming trong Spring AI, ứng dụng nhận các phần phản hồi của mô hình dần dần thay vì chờ toàn bộ câu trả lời. Tuy nhiên, một lượt tool calling không chỉ là một luồng token liên tục. Mô hình có thể phát nội dung văn bản, phát từng mảnh arguments của tool call, hoàn tất một tool call, chờ ứng dụng thực thi công cụ, nhận kết quả rồi tiếp tục sinh văn bản ở lượt mô hình kế tiếp.

Hai tiến trình cần được quan sát riêng:

- **Luồng phản hồi của mô hình:** các chunk/delta được phát khi provider tạo nội dung. Chunk có thể chứa text, metadata hoặc một phần tool-call arguments. Một chunk không nhất thiết tương ứng đúng một token tokenizer.
- **Tiến trình thực thi công cụ:** ứng dụng nhận tool call hoàn chỉnh, kiểm tra và gọi callback/service, thu kết quả rồi đưa kết quả đó trở lại mô hình hoặc trả trực tiếp cho caller.

Việc nhìn thấy arguments đang được tạo không có nghĩa công cụ đã chạy. Việc stream văn bản cũng không có nghĩa ứng dụng đã hoàn thành thao tác nghiệp vụ. Muốn giao diện hiển thị chính xác, hãy phát sự kiện riêng cho từng giai đoạn và chỉ xác nhận thành công sau khi callback/service trả kết quả.

Bài này lấy Spring AI 2.1.0 làm mốc API, tập trung vào ChatClient.stream(), ToolCallingAdvisor, các phần ToolCallPart được stream, cơ chế gom chunk, tiến trình tool execution, concurrency và cách điều phối tiến độ qua SSE/WebSocket.

## Một lượt streaming có tool calling diễn ra như thế nào?

Với ChatClient, ToolCallingAdvisor quản lý vòng tool calling cho cả .call() và .stream(). Trong một iteration, Spring AI gửi prompt và tool definitions đến model. Model có thể trả văn bản hoặc tool call. Nếu có tool call, advisor chuyển request đến ToolCallingManager, nhận kết quả, thêm tool response vào conversation history rồi gọi model tiếp.

~~~mermaid
sequenceDiagram
    participant UI as Giao diện
    participant App as Ứng dụng
    participant Model as Model Provider
    participant Advisor as ToolCallingAdvisor
    participant Tool as ToolCallback / Service

    App->>Advisor: Prompt + tool definitions
    Advisor->>Model: Gửi request
    loop Các chunk của model response
        Model-->>Advisor: Text delta hoặc tool-argument delta
        Advisor-->>UI: Chunk/progress phù hợp
    end
    Model-->>Advisor: Tool call hoàn chỉnh
    Note over Advisor: Gom response và kiểm tra tool calls
    Advisor->>Tool: Thực thi callback
    Tool-->>Advisor: Tool result
    Advisor->>Model: Tool response + conversation history
    loop Các chunk của câu trả lời tiếp theo
        Model-->>Advisor: Text delta
        Advisor-->>UI: Text delta
    end
    Model-->>Advisor: Response cuối
    Advisor-->>UI: Hoàn tất lượt
~~~

Một lượt có thể có nhiều iteration:

1. Model stream một phần arguments.
2. Model hoàn tất tool call.
3. Ứng dụng thực thi công cụ.
4. Tool result được gửi lại model.
5. Model stream câu trả lời tiếp theo hoặc yêu cầu công cụ khác.
6. Quá trình lặp đến khi model trả lời cuối hoặc ứng dụng dừng.

Nếu tool call trả về returnDirect, vòng lặp có thể kết thúc ngay sau khi công cụ chạy; model không cần nhận kết quả để tạo thêm câu trả lời.

## Chunk streaming không đồng nghĩa một token hoàn chỉnh

API streaming thường trả Flux<String>, Flux<ChatResponse> hoặc Flux<ChatClientResponse>. Các phần tử trong Flux là chunk/delta mà model provider phát ra. Một chunk có thể chứa một phần từ, nhiều token, metadata hoặc một phần cấu trúc message. Không nên giả định mỗi phần tử Flux tương ứng một token theo tokenizer.

Các lựa chọn thường dùng:

| API | Dữ liệu nhận được | Khi nên dùng |
|---|---|---|
| .stream().content() | Các phần văn bản được sinh ra. | UI chỉ cần hiển thị nội dung trả lời. |
| .stream().chatResponse() | ChatResponse chunks, gồm output parts và metadata. | Cần đọc text, tool-call deltas, finish reason hoặc metadata. |
| .stream().chatClientResponse() | ChatClientResponse chunks, gồm ChatResponse và advisor execution context. | Cần quan sát thêm dữ liệu từ advisor chain. |

.content() chỉ stream text. Tool-call argument deltas không phải text nên không xuất hiện trong Flux<String>. Nếu muốn hiển thị công cụ mà model đang chuẩn bị gọi, hãy dùng chatResponse() hoặc chatClientResponse() để đọc output parts.

## Tool-call arguments có thể được stream từng phần

Với các provider hỗ trợ streaming tool arguments, mỗi delta có thể mang một ToolCallPart được đánh dấu partial. Phần đầu có thể có ID và tên tool nhưng chưa có arguments; các phần sau chỉ chứa fragment mới của arguments.

Spring AI 2.1.0 hỗ trợ việc stream các delta này với các tích hợp như Anthropic, OpenAI Chat Completions, OpenAI Responses, Amazon Bedrock Converse và DeepSeek. Các provider khác có thể chỉ trả tool call hoàn chỉnh ở cuối response. Khả năng thực tế còn phụ thuộc model và endpoint đang dùng.

Ví dụ quan sát các phần arguments:

~~~java
chatClient.prompt()
        .user("Tra cứu thời tiết tại Hà Nội")
        .tools(weatherTools)
        .stream()
        .chatResponse()
        .subscribe(response -> response.getResults().forEach(generation -> {
            for (MessagePart part : generation.getOutput().getParts()) {
                if (part instanceof ToolCallPart toolCallPart
                        && StreamingParts.isPartial(part)) {

                    ToolCall delta = toolCallPart.toolCall();
                    progressPublisher.publish(
                            new ToolCallDraftEvent(
                                    delta.id(),
                                    delta.name()
                            )
                    );
                }
            }
        }));
~~~

Đây là sự kiện cho biết model đang tạo một yêu cầu gọi công cụ. Arguments có thể chưa đầy đủ và thường chưa phải JSON hợp lệ. Nếu cần hiển thị arguments, hãy ghép các fragment theo tool-call ID và chỉ hiển thị các trường đã được phép công khai.

**Không parse hoặc thực thi một partial ToolCallPart.** Trong Spring AI:

- AssistantMessage.getToolCalls() và hasToolCalls() bỏ qua partial parts.
- ToolCallingManager chỉ thực thi tool call hoàn chỉnh.
- MessageAggregator không coi partial part là một tool call hoàn chỉnh để lưu vào conversation history.
- Model phát tool call hoàn chỉnh sau các delta; tool calling loop xử lý ở thời điểm đó.

Không tự ghép fragment rồi gọi callback sớm. Phần cuối có thể bổ sung arguments, thay đổi cách biểu diễn hoặc hoàn tất một call không có arguments bằng object rỗng tùy provider.

## ToolCallingAdvisor giữ riêng vòng model stream và vòng thực thi

Trong Spring AI 2.1.0, ToolCallingAdvisor triển khai cả call path và stream path. Khi dùng:

~~~java
Flux<ChatResponse> stream = chatClient.prompt()
        .user("Tìm đơn hàng và cho biết trạng thái giao hàng.")
        .tools(orderTools, shippingTools)
        .stream()
        .chatResponse();
~~~

advisor tự xử lý tool call hoàn chỉnh. Nó gom response của iteration, gọi ToolCallingManager, thêm tool response vào lịch sử rồi gửi request tiếp theo. Caller nhận stream nội dung cuối; các chunk tool-call arguments có thể được quan sát như tiến độ, trong khi chunk tool call hoàn chỉnh được advisor dùng cho dispatch thay vì hiển thị như câu trả lời văn bản.

Tool result không phải một luồng token của model. Callback thường trả kết quả theo hợp đồng thực thi của tool; ToolCallResultConverter chuyển kết quả đó thành nội dung tool response. Sau đó model mới tiếp tục stream nội dung hoặc tool call khác.

### Quan sát từng iteration bằng custom StreamAdvisor

Nếu cần ghi nhận hoặc đẩy tiến độ của mọi iteration, có thể đặt một custom StreamAdvisor bên trong vòng ToolCallingAdvisor. Ví dụ, advisor có order HIGHEST_PRECEDENCE + 400 sẽ chạy bên trong tool loop mặc định có order HIGHEST_PRECEDENCE + 300.

~~~java
public final class ToolProgressStreamAdvisor implements StreamAdvisor {

    private final Consumer<ChatClientResponse> progressSink;

    public ToolProgressStreamAdvisor(
            Consumer<ChatClientResponse> progressSink) {
        this.progressSink = progressSink;
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
                .doOnNext(progressSink);
    }
}
~~~

Đăng ký advisor:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultAdvisors(new ToolProgressStreamAdvisor(progressPublisher::publish))
        .build();
~~~

Advisor nằm trong loop có thể quan sát các chunk của từng iteration, kể cả chunk tool-call request. Caller bên ngoài vẫn nhận stream cuối theo quy tắc của ToolCallingAdvisor. Nếu chỉ cần đẩy tiến độ trung gian, đây thường là cách dễ kết hợp với advisor chain hơn là tắt vòng lặp tự động.

Khi cần cả blocking và streaming, advisor nên triển khai cả CallAdvisor và StreamAdvisor; mỗi nhánh cần hook tương ứng. Không gọi cùng một observer hai lần cho cùng một sự kiện nếu cả hai advisor được đăng ký.

## Tiến trình thực thi công cụ là một chuỗi sự kiện riêng

Một callback có thể gọi database, HTTP API, hệ thống thanh toán hoặc một service nội bộ. Thời gian thực thi bắt đầu sau khi model đã hoàn tất tool call và ứng dụng dispatch callback. Callback không tự động phát token hoặc tiến độ từng phần.

Nên mô hình hóa tiến trình thành các sự kiện có trạng thái rõ:

| Sự kiện | Ý nghĩa | Nguồn phát |
|---|---|---|
| MODEL_STREAMING | Model đang phát text hoặc dữ liệu cấu trúc. | Model stream subscriber/advisor. |
| TOOL_CALL_DRAFT | Model đang tạo tên tool hoặc arguments từng phần. | Partial ToolCallPart. |
| TOOL_CALL_READY | Model đã trả tool call hoàn chỉnh. | Response đã aggregate và có hasToolCalls(). |
| TOOL_EXECUTION_STARTED | Ứng dụng bắt đầu dispatch callback. | Tool execution observer hoặc wrapper callback. |
| TOOL_EXECUTION_SUCCEEDED | Callback hoàn tất và có kết quả. | Tool execution observer/wrapper. |
| TOOL_EXECUTION_FAILED | Callback thất bại. | Error handler/observer. |
| MODEL_RESUMED | Tool result đã được gửi lại model và iteration mới bắt đầu. | Tool loop advisor. |
| RUN_COMPLETED | Model trả lời cuối hoặc workflow kết thúc. | Lớp điều phối. |

Đừng phát TOOL_EXECUTION_STARTED ngay khi nhận partial arguments; lúc đó model vẫn đang viết yêu cầu. Đừng phát TOOL_EXECUTION_SUCCEEDED chỉ vì model đã phát hết token; callback có thể chưa chạy hoặc còn thất bại.

Ví dụ event DTO:

~~~java
public record ToolProgressEvent(
        String runId,
        String toolCallId,
        String toolName,
        ToolProgressStatus status,
        Instant occurredAt,
        String safeMessage) {
}

public enum ToolProgressStatus {
    PROPOSED,
    STARTED,
    SUCCEEDED,
    FAILED
}
~~~

runId và toolCallId giúp UI ghép sự kiện đúng request và đúng tool call. Không đưa raw arguments, access token, dữ liệu cá nhân hoặc nội dung nội bộ vào sự kiện gửi tới browser nếu chưa được lọc.

### Phát tiến độ của một tool chạy lâu

Nếu callback gọi một công việc dài, ứng dụng có thể phát tiến độ qua một side channel như Reactor Sinks.Many, application event, message broker hoặc WebSocket. Đó là tiến độ do ứng dụng/service tạo, không phải token stream của model.

Ví dụ wrapper ở tầng ứng dụng:

~~~java
public ToolResult executeReport(String reportId, String runId) {
    progressPublisher.publish(started(runId, "generateReport"));
    try {
        ToolResult result = reportService.generate(reportId, progress -> {
            progressPublisher.publish(
                    progressEvent(runId, "generateReport", progress)
            );
        });
        progressPublisher.publish(succeeded(runId, "generateReport"));
        return result;
    }
    catch (RuntimeException ex) {
        progressPublisher.publish(failed(runId, "generateReport"));
        throw ex;
    }
}
~~~

Callback cuối cùng vẫn trả tool result theo hợp đồng Spring AI. Side channel chỉ cập nhật trạng thái cho UI; nó không thay thế tool response message gửi lại model.

## Dùng MessageAggregator khi tự điều phối streaming

Nếu tắt auto-registration của ToolCallingAdvisor để tự kiểm tra và thực thi từng tool call, mỗi iteration streaming phải được gom thành một response hoàn chỉnh trước khi dispatch tool.

Với ChatClient, dùng ChatClientMessageAggregator:

~~~java
AtomicReference<ChatClientResponse> aggregated = new AtomicReference<>();

new ChatClientMessageAggregator().aggregateChatClientResponse(
        chatClient.prompt()
                .messages(prompt.getInstructions())
                .options(chatOptions)
                .advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
                .stream()
                .chatClientResponse()
                .doOnNext(chunk -> forwardProgressToSse(chunk)),
        aggregated::set
).blockLast();

ChatClientResponse completeResponse = aggregated.get();
ChatResponse chatResponse = completeResponse.chatResponse();

if (chatResponse != null && chatResponse.hasToolCalls()) {
    ToolExecutionResult result =
            toolCallingManager.executeToolCalls(prompt, chatResponse);

    prompt = new Prompt(result.conversationHistory(), chatOptions);
}
~~~

aggregateChatClientResponse(...) nhận các chunk và cung cấp response đã aggregate cho callback khi iteration kết thúc. Chỉ sau bước này mới kiểm tra hasToolCalls() và gọi manager. Với đường ChatModel trực tiếp, dùng MessageAggregator để gom Flux<ChatResponse> thành ChatResponse hoàn chỉnh.

Ví dụ trên dùng blockLast() để minh họa một flow imperative. Không gọi blocking operation trên Reactor Netty event-loop trong WebFlux. Trong ứng dụng reactive, hãy compose aggregation và bước thực thi tiếp theo bằng Mono/Flux, hoặc chuyển phần blocking sang scheduler phù hợp.

Sau khi thực thi, dùng ToolExecutionResult.conversationHistory() để tạo prompt của iteration tiếp theo. Mỗi iteration mới cần stream và aggregate lại; không dùng các chunk của iteration trước để suy luận rằng tool call tiếp theo đã hoàn tất.

## Streaming và thực thi tool trong cùng request

Spring AI 2.1.0 hỗ trợ stream path cho ToolCallingAdvisor, nhưng tool execution vẫn là hoạt động imperative và có thể blocking. Trong streaming call, tool execution được chạy trên Reactor bounded-elastic scheduler theo cơ chế của framework. Điều này giúp tránh chạy trực tiếp tác vụ blocking trên event-loop, nhưng không biến callback đồng bộ thành một API reactive.

Hãy thiết kế callback/service với:

- Timeout cho HTTP/database call.
- Giới hạn concurrency và connection pool.
- Cancellation policy nếu người dùng ngắt stream.
- Idempotency cho thao tác ghi có thể được retry.
- Không giữ lock trong lúc chờ model stream hoặc dịch vụ bên ngoài.
- Không dùng chung mutable request state giữa nhiều subscriber.

Nếu một tool thực sự cần stream dữ liệu lớn, cân nhắc để tool tạo một job và trả về jobId, sau đó ứng dụng stream tiến độ job qua side channel. Đừng cố nhét một luồng tiến độ dài vào String tool result.

## Phân biệt parallel tool calls và concurrent execution

Một response của model có thể chứa nhiều tool call. Một số provider có tùy chọn như parallelToolCalls để cho phép model trả nhiều tool call trong cùng một response. Tùy chọn này điều khiển khả năng tạo batch của model; nó không tự động bảo đảm các callback ở phía ứng dụng chạy đồng thời.

Trong implementation DefaultToolCallingManager của Spring AI 2.1.0, các tool call trong cùng assistant response được dispatch lần lượt theo thứ tự trong danh sách. Vì vậy, nếu ba tool độc lập mỗi tool mất khoảng hai giây, tổng thời gian thực thi có thể gần sáu giây dù model trả cả ba trong cùng một response.

Phân biệt:

| Khái niệm | Nơi xảy ra | Ý nghĩa |
|---|---|---|
| Parallel tool-call generation | Model/provider | Model được phép đề xuất nhiều tool call trong một response. |
| Sequential tool execution | Ứng dụng/manager | Callback chạy lần lượt; kết quả được ghép theo tool call tương ứng. |
| Concurrent tool execution | Ứng dụng/custom manager | Nhiều callback được chạy đồng thời bằng executor hoặc cơ chế async do ứng dụng quản lý. |
| Concurrent chat requests | Server ứng dụng | Nhiều người dùng/request khác nhau đang chạy cùng lúc. |

Không suy ra concurrency của callback từ tên option parallelToolCalls. Hãy kiểm tra implementation ToolCallingManager thực tế của phiên bản đang dùng.

### Khi nào nên thực thi đồng thời?

Chỉ chạy đồng thời các tool call độc lập, không phụ thuộc kết quả hoặc thứ tự của nhau. Ví dụ:

- Tra cứu tồn kho ở hai kho độc lập.
- Lấy tỷ giá và thời tiết từ hai dịch vụ không liên quan.
- Đọc hồ sơ khách hàng và trạng thái giao hàng khi hai truy vấn không phụ thuộc nhau.

Không chạy đồng thời khi:

- Tool B cần ID do Tool A tạo ra.
- Hai tool cập nhật cùng một bản ghi hoặc cùng một aggregate.
- Thứ tự thao tác có ý nghĩa nghiệp vụ.
- Một tool có thể hủy hoặc thay đổi điều kiện để tool khác chạy.
- Cả batch cần một transaction thống nhất nhưng các service không hỗ trợ transaction chung.

### Nếu cần concurrent execution

Ứng dụng có thể triển khai custom ToolCallingManager hoặc một tầng dispatch riêng dùng bounded executor. Thiết kế cần bảo đảm:

1. Kiểm tra allowlist, authorization, confirmation và giới hạn trước khi dispatch.
2. Chỉ chạy song song các call độc lập đã được xác định an toàn.
3. Giới hạn số tác vụ đồng thời bằng thread pool/semaphore; không tạo thread không giới hạn theo số tool call.
4. Giữ index ban đầu để ghép ToolResponse theo đúng thứ tự tool call mà model yêu cầu.
5. Thu thập lỗi của từng tool theo chính sách đã chọn; không làm mất kết quả đã hoàn tất.
6. Xử lý returnDirect nhất quán cho toàn batch.
7. Bảo đảm callback, client và dữ liệu ToolContext an toàn khi được truy cập đồng thời.
8. Áp timeout, cancellation và idempotency cho thao tác có side effect.

Không tự chạy song song mọi tool call chỉ để giảm latency. Concurrency có thể làm tăng tải đột biến lên database hoặc API bên ngoài, gây race condition và khiến kết quả trả về không còn đúng thứ tự.

## Concurrency giữa nhiều request và nhiều session

Concurrency giữa các request độc lập khác với nhiều tool call trong cùng một response. Một server có thể xử lý nhiều người dùng đồng thời, nhưng mỗi conversation/session vẫn cần quản lý lịch sử theo đúng thứ tự.

Nếu hai request cùng session chạy song song:

- Cả hai có thể đọc cùng một conversation history.
- Mỗi request có thể tạo assistant message/tool call riêng.
- Tool response của request này có thể bị nối vào lịch sử của request kia.
- Kết quả đến sau có thể ghi đè hoặc làm sai thứ tự hội thoại.

Hãy serialize các lượt ghi vào cùng một session hoặc dùng optimistic locking/version check ở tầng session store. Với các session khác nhau, có thể xử lý song song nếu callback, memory store và dependency dùng chung được thiết kế thread-safe.

Mỗi request cần có runId riêng; mỗi tool call cần có ID riêng. Không dùng một biến AtomicReference, StringBuilder, danh sách events hoặc conversation history dùng chung cho tất cả request.

## Backpressure, cancellation và lỗi khi stream

Flux cho phép downstream nhận dữ liệu theo nhịp của subscriber. Khi xây dựng SSE/WebSocket:

- Tránh giữ toàn bộ token/chunk trong bộ nhớ nếu chỉ cần chuyển tiếp.
- Giới hạn buffer của event queue; có chính sách khi client đọc chậm.
- Phân biệt client ngắt kết nối với model trả lỗi.
- Khi stream bị cancel, không khởi tạo iteration model mới.
- Tool đang chạy có thể không dừng ngay nếu client/service không hỗ trợ cancellation; đặt timeout và kiểm tra trạng thái trước khi retry.
- Nếu tool đã tạo side effect trước khi stream bị ngắt, không giả định việc cancel sẽ rollback thao tác.
- Không retry một tool ghi dữ liệu nếu chưa có idempotency key hoặc cơ chế xác định lần chạy trước đã thành công hay chưa.

Khi model stream lỗi giữa chừng, response có thể chưa đủ để xác định một tool call hoàn chỉnh. Không thực thi tool dựa trên các partial arguments còn lại. Ghi nhận iteration thất bại và quyết định tiếp tục, retry hoặc dừng theo policy của ứng dụng.

## Giao diện nên hiển thị gì?

Một giao diện tốt phân biệt trạng thái model với trạng thái tool:

| Trạng thái nội bộ | Nội dung có thể hiển thị |
|---|---|
| Model đang tạo text | Hiển thị text delta dần dần. |
| Model đang tạo tool arguments | “Đang chuẩn bị tra cứu đơn hàng…” nếu tên tool đã được xác định và được phép hiển thị. |
| Tool call hoàn chỉnh | “Đã xác định yêu cầu tra cứu…” |
| Callback đang chạy | “Đang tra cứu dữ liệu…” dựa trên TOOL_EXECUTION_STARTED. |
| Callback hoàn tất | “Đã lấy được trạng thái đơn hàng.” dựa trên kết quả service. |
| Model đang tổng hợp | Tiếp tục hiển thị text delta của model. |
| Hoàn tất | Đánh dấu hoàn tất sau khi response cuối đã kết thúc. |
| Lỗi | Hiển thị trạng thái lỗi an toàn, không để lộ stack trace hoặc arguments nội bộ. |

Không hiển thị “Đã gửi email”, “Đã thanh toán” hoặc “Đã đặt lịch” chỉ vì model đã phát tool call tương ứng. Chỉ xác nhận sau khi service trả kết quả thành công và trạng thái nghiệp vụ đã được xác minh.

## Kiểm thử streaming và tiến trình thực thi

Kiểm thử cần phân biệt chunk model, partial tool-call arguments, tool dispatch và tool result:

| Tình huống | Kết quả cần xác minh |
|---|---|
| Model stream text bình thường | UI nhận các text delta và kết thúc đúng. |
| Provider stream partial ToolCallPart | UI có thể nhận progress draft; callback chưa chạy. |
| Arguments bị chia thành nhiều fragment | Không parse/dispatch cho đến khi có tool call hoàn chỉnh. |
| Provider không stream tool arguments | UI vẫn hoạt động khi chỉ nhận complete tool call. |
| Tool call hoàn chỉnh xuất hiện | ToolCallingManager dispatch đúng callback. |
| Tool chạy lâu | Có sự kiện started/progress/succeeded riêng; token stream không giả lập tiến độ tool. |
| Tool thất bại | UI nhận trạng thái lỗi an toàn; model tiếp tục hoặc dừng theo exception policy. |
| Nhiều tool call trong một response | Xác minh thứ tự dispatch mặc định hoặc concurrency policy của custom manager. |
| parallelToolCalls bật | Không mặc định callback được thực thi đồng thời. |
| Custom concurrent manager | Kết quả được ghép đúng thứ tự, lỗi và cancellation được xử lý. |
| Hai request khác session | Không trộn event, context hoặc conversation history. |
| Hai request cùng session | Lượt được serialize hoặc version conflict được xử lý. |
| Client hủy SSE | Không khởi tạo model iteration tiếp theo; side effect đang chạy được quản lý. |
| Model stream kết thúc bất thường | Partial tool call không được thực thi. |
| Tool đã chạy nhưng model call sau thất bại | Trạng thái tool đã hoàn tất được lưu để tránh retry side effect ngoài ý muốn. |

Nên dùng model giả lập phát ra chuỗi chunk cố định: text delta, tool-call partial delta, complete tool call, rồi text delta sau tool response. Dùng callback giả có thời gian chạy xác định để kiểm tra thứ tự, concurrency và event lifecycle. Không dựa vào model thật để tái hiện chính xác thứ tự chunk trong unit test.

## Bài tập thực hành

Xây dựng endpoint SSE tra cứu đơn hàng:

1. Tạo tool getOrderStatus(orderId) và getShipmentTracking(orderId).
2. Dùng ChatClient.stream().chatResponse() để quan sát text và partial ToolCallPart.
3. Khi thấy partial tool call, phát TOOL_CALL_DRAFT; không thực thi callback.
4. Dùng ToolCallingAdvisor mặc định để quản lý vòng tool calling.
5. Bọc service để phát TOOL_EXECUTION_STARTED, SUCCEEDED hoặc FAILED.
6. Phát text delta của model và tool progress bằng hai loại event riêng.
7. Thử một provider có stream tool arguments và một provider chỉ trả tool call hoàn chỉnh.
8. Tạo response chứa hai tool call độc lập; đo thời gian thực thi mặc định và xác minh thứ tự callback.
9. Nếu cần concurrency, tạo custom dispatcher có bounded executor, giữ thứ tự ToolResponse và kiểm thử lỗi/cancellation.
10. Mở hai request đồng thời; xác minh event và conversation history không bị trộn.
11. Ngắt SSE trong khi tool đang chạy; xác minh ứng dụng không phát model iteration tiếp theo và không retry side effect mù quáng.

Bạn hoàn thành khi có thể giải thích chính xác thời điểm model đang stream, thời điểm tool call đã hoàn chỉnh, thời điểm callback bắt đầu/kết thúc và cách kết quả quay lại model. Giao diện phải thể hiện đúng tiến trình mà ứng dụng thực sự quan sát được.

## Danh sách kiểm tra trước khi triển khai

- [ ] Đã chọn đúng API stream: content(), chatResponse() hoặc chatClientResponse().
- [ ] Không giả định một chunk tương ứng chính xác một token.
- [ ] Dùng chatResponse()/chatClientResponse() nếu cần quan sát tool-call parts.
- [ ] Partial ToolCallPart chỉ dùng cho progress draft; không parse hoặc thực thi.
- [ ] Chỉ dispatch tool call sau khi response iteration đã aggregate và có tool call hoàn chỉnh.
- [ ] Đã hiểu ToolCallingAdvisor quản lý loop cho cả call và stream.
- [ ] Tiến trình tool execution được phát bằng event riêng từ ứng dụng/service.
- [ ] Không tuyên bố thao tác nghiệp vụ thành công trước khi service xác nhận.
- [ ] Nếu tự điều phối, dùng ChatClientMessageAggregator hoặc MessageAggregator để gom từng iteration.
- [ ] Không gọi blockLast() trên Reactor event-loop.
- [ ] Callback blocking có timeout và được chạy trên scheduler phù hợp.
- [ ] Đã phân biệt parallelToolCalls với concurrent execution ở phía ứng dụng.
- [ ] Nếu chạy song song, chỉ dispatch call độc lập bằng bounded executor và giữ thứ tự kết quả.
- [ ] Context, callback và dependency dùng chung an toàn khi concurrent.
- [ ] Các lượt cùng session được serialize hoặc bảo vệ bằng version/locking.
- [ ] Có cancellation, backpressure, timeout và idempotency policy.
- [ ] Không log hoặc gửi raw arguments/result nhạy cảm tới browser.
- [ ] Có unit/integration test cho partial arguments, complete call, tool lifecycle và nhiều request đồng thời.

## Tài liệu tham khảo

- [Spring AI 2.1.0 – Tool Calling và Streaming Tool Call Arguments](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 – ToolCallingAdvisor và User-Controlled Streaming](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 – ChatClient Streaming API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI 2.1.0 – ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [Spring AI 2.1.0 – Spring AI 2.1.0 GA Release Notes](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/)
- [Spring AI source – DefaultToolCallingManager](https://github.com/spring-projects/spring-ai/blob/main/spring-ai-model/src/main/java/org/springframework/ai/model/tool/DefaultToolCallingManager.java)

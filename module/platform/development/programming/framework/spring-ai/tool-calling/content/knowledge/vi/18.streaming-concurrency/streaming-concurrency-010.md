# Phân biệt streaming chat với khả năng trả Mono, Flux hoặc Future của công cụ

Trong Spring AI, streaming chat và một tool trả về kiểu bất đồng bộ là hai khái niệm khác nhau. Streaming chat mô tả cách ứng dụng nhận phản hồi từ mô hình theo từng phần. Còn Mono, Flux, Future và CompletableFuture là các kiểu biểu diễn một kết quả sẽ có sau này hoặc một chuỗi kết quả trong Java. Việc ChatClient có thể phát Flux của nội dung model không có nghĩa method tool được phép trả Mono hoặc Future để Spring AI tự chờ và lấy kết quả.

Với tool chuẩn của Spring AI, callback được thực thi theo hợp đồng đồng bộ và trả kết quả đã chuyển thành String cho vòng tool calling. Các kiểu reactive và asynchronous như Mono, Flux, Future hoặc CompletableFuture không được MethodToolCallback tự subscribe, await hay unwrap. Khi cần dùng một dịch vụ reactive hoặc một tác vụ chạy nền, ứng dụng phải chọn cách chuyển đổi phù hợp và quản lý thời gian chờ, lỗi, hủy tác vụ cũng như kết quả nghiệp vụ.

## Sau bài học, bạn có thể

- Phân biệt Flux của ChatClient streaming với Mono, Flux hoặc Future được khai báo làm kiểu trả về của tool.
- Giải thích cách ToolCallingAdvisor phối hợp streaming chat với vòng gọi công cụ.
- Hiểu vì sao tool call chỉ được thực thi sau khi model hoàn tất yêu cầu gọi công cụ.
- Nhận biết giới hạn kiểu tham số và kiểu trả về của MethodToolCallback và FunctionToolCallback.
- Viết endpoint streaming chat nhưng vẫn dùng tool trả về DTO đồng bộ.
- Chọn cách xử lý dependency reactive hoặc tác vụ dài mà không trả publisher/future trực tiếp từ tool.
- Tránh block event loop, subscribe ngầm, mất lỗi và tác vụ không được theo dõi.
- Kiểm thử luồng streaming, tool execution và các trường hợp bất đồng bộ.

## Hai luồng dữ liệu khác nhau

### Streaming chat: nhận phản hồi model theo từng chunk

Khi gọi ChatClient bằng API stream, Spring AI trả một publisher để ứng dụng nhận các phần của phản hồi model:

- **Flux<String> content():** các phần nội dung văn bản model tạo ra.
- **Flux<ChatResponse> chatResponse():** các phần phản hồi có metadata và cấu trúc generation.
- **Flux<ChatClientResponse> chatClientResponse():** phản hồi kèm execution context của ChatClient và advisor.

Ví dụ:

~~~java
Flux<String> answer = chatClient.prompt()
        .user("Giải thích trạng thái đơn hàng DH-1024")
        .stream()
        .content();
~~~

Flux này thuộc về kết quả của request chat. Nó cho phép UI hiển thị dần nội dung khi model đang tạo câu trả lời. Nó không phải kiểu trả về của một tool method.

Một endpoint WebFlux có thể trả publisher đó cho trình duyệt:

~~~java
@RestController
public class AssistantController {

    private final ChatClient chatClient;
    private final OrderTools orderTools;

    public AssistantController(
            ChatClient chatClient,
            OrderTools orderTools) {
        this.chatClient = chatClient;
        this.orderTools = orderTools;
    }

    @GetMapping(
            value = "/assistant/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<String> stream(@RequestParam String question) {
        return chatClient.prompt()
                .user(question)
                .tools(orderTools)
                .stream()
                .content();
    }
}
~~~

Trong ví dụ này, controller trả Flux để truyền nội dung chat tới client. Tool vẫn được đăng ký riêng bằng object OrderTools. Việc controller trả Flux không làm thay đổi chữ ký method của tool.

### Tool result: một giá trị để gửi lại cho model

Khi model yêu cầu gọi tool, ứng dụng thực thi callback và chuyển kết quả của callback thành chuỗi để đưa vào lịch sử hội thoại. Với method-based tool, kết quả thường là một DTO, record, chuỗi, số hoặc kiểu dữ liệu được Spring AI hỗ trợ serialize. Với FunctionToolCallback, function có kiểu đầu vào và đầu ra đồng bộ.

Ví dụ:

~~~java
public record OrderStatus(
        String orderId,
        String status,
        String currentLocation
) {
}

@Component
public class OrderTools {

    private final OrderService orderService;

    public OrderTools(OrderService orderService) {
        this.orderService = orderService;
    }

    @Tool(description = "Tra cứu trạng thái đơn hàng theo mã đơn")
    public OrderStatus getOrderStatus(
            @ToolParam(description = "Mã đơn hàng cần tra cứu")
            String orderId) {
        return orderService.getStatus(orderId);
    }
}
~~~

Tool trả một OrderStatus cụ thể. Spring AI chuyển giá trị này thành tool result, gửi lại model và tiếp tục vòng hội thoại nếu model cần diễn giải kết quả.

## ChatClient streaming vẫn có thể chạy tool-calling loop

Trong Spring AI 2.x, ChatClient tự đăng ký ToolCallingAdvisor để quản lý vòng gọi công cụ. Cả call() và stream() đều hỗ trợ vòng này:

1. Advisor gửi prompt cùng tool definitions đến model.
2. Model trả về nội dung hoặc yêu cầu gọi một hay nhiều tool.
3. Nếu có tool call hoàn chỉnh, ToolCallingManager tìm callback và thực thi.
4. Kết quả tool được thêm vào lịch sử hội thoại.
5. Advisor gửi lịch sử mới cho model.
6. Các vòng tiếp tục đến khi model trả phản hồi không còn tool call.

~~~mermaid
sequenceDiagram
    participant UI as Trình duyệt
    participant CC as ChatClient
    participant TA as ToolCallingAdvisor
    participant LLM as Chat Model
    participant TM as ToolCallingManager
    participant Tool as ToolCallback

    UI->>CC: Gửi câu hỏi
    CC->>TA: stream()
    TA->>LLM: Prompt + tool definitions
    LLM-->>TA: Các chunk phản hồi
    TA-->>UI: Chunk văn bản (nếu có)
    LLM-->>TA: Tool call hoàn chỉnh
    TA->>TM: Thực thi tool call
    TM->>Tool: call(input)
    Tool-->>TM: Kết quả đã serialize
    TM-->>TA: Tool execution result
    TA->>LLM: Lịch sử + tool result
    LLM-->>TA: Các chunk câu trả lời tiếp theo
    TA-->>UI: Flux nội dung cuối
~~~

Điểm cần phân biệt là stream của model và việc thực thi tool diễn ra trong cùng một request nhưng có hợp đồng khác nhau. Model có thể phát nhiều chunk trước khi yêu cầu tool. Khi tool call hoàn tất, ứng dụng thực thi callback. Sau đó model có thể tiếp tục phát câu trả lời trong cùng luồng chat.

## Tool call dạng streaming có các phần chưa hoàn chỉnh

Một số provider có thể stream đối số tool call khi model đang tạo chúng. Spring AI biểu diễn từng phần bằng ToolCallPart được đánh dấu partial. Các provider được tài liệu hiện tại nêu gồm Anthropic, OpenAI Chat Completions và Responses, Amazon Bedrock Converse và DeepSeek.

Ví dụ, model đang tạo lời gọi:

~~~json
{
  "name": "getOrderStatus",
  "arguments": {
    "orderId": "DH-1024"
  }
}
~~~

Trong quá trình stream, ứng dụng có thể nhận các mảnh như:

~~~text
{"order
Id":
"DH-1024"
}
~~~

Một mảnh riêng lẻ thường chưa phải JSON hợp lệ. Không được lấy từng delta làm đối số hoàn chỉnh để gọi tool. Spring AI chỉ coi tool call là hoàn chỉnh khi đã nhận đủ thông tin của lời gọi. ToolCallingManager không thực thi partial ToolCallPart.

Nếu cần hiển thị tiến độ tool call cho UI, có thể quan sát các phần response qua chatResponse() hoặc ChatClientResponse và chỉ hiển thị trạng thái “model đang chuẩn bị gọi tool”. Không nên hiển thị một partial JSON như kết quả nghiệp vụ đã xác nhận.

~~~java
chatClient.prompt()
        .user("Tra cứu trạng thái đơn hàng DH-1024")
        .tools(orderTools)
        .stream()
        .chatResponse()
        .subscribe(response -> {
            // Có thể đọc metadata và các phần của response tại đây.
            // Chỉ xử lý tool call khi response chứa lời gọi hoàn chỉnh.
        });
~~~

Các delta của tool call không mang nội dung văn bản thông thường. Vì vậy stream().content() không trả các mảnh đối số tool call như văn bản. Nếu UI cần hiển thị tiến độ gọi công cụ, dùng loại response giàu metadata và kiểm tra provider có hỗ trợ stream tool-call arguments hay không.

## Vì sao Mono, Flux và Future không phải kiểu trả về của tool?

Một tool method được chuyển thành MethodToolCallback. Các kiểu trả về của method phải biểu diễn được thành dữ liệu để converter serialize. Spring AI không tự động subscribe Mono/Flux hoặc gọi get()/join() trên Future và CompletableFuture để lấy giá trị cuối cùng.

Ví dụ sau không phải chữ ký tool được hỗ trợ:

~~~java
@Component
public class OrderTools {

    @Tool(description = "Tra cứu trạng thái đơn hàng")
    public Mono<OrderStatus> getOrderStatus(String orderId) {
        return orderClient.getStatus(orderId);
    }
}
~~~

Method trả về Mono<OrderStatus>, tức một publisher có thể phát một giá trị trong tương lai. Tool callback không tự subscribe publisher đó để chờ OrderStatus. Kết quả cần gửi cho model là một giá trị nghiệp vụ đã hoàn tất, không phải đối tượng mô tả một pipeline reactive.

Tương tự, các chữ ký sau cũng không được hỗ trợ như kiểu trả về của method-based tool:

~~~java
@Tool
public Flux<OrderEvent> watchOrder(String orderId) {
    return orderEventService.watch(orderId);
}

@Tool
public CompletableFuture<OrderStatus> getStatusAsync(String orderId) {
    return orderService.getStatusAsync(orderId);
}

@Tool
public Future<OrderStatus> getStatusFuture(String orderId) {
    return executor.submit(() -> orderService.getStatus(orderId));
}
~~~

Các kiểu bị giới hạn gồm:

| Kiểu | Số kết quả biểu diễn | Vì sao không dùng làm tool return type |
|---|---|---|
| Mono<T> | Không hoặc một giá trị | Là publisher, không phải DTO đã hoàn tất |
| Flux<T> | Không, một hoặc nhiều giá trị | Là stream; tool result chuẩn cần một kết quả được serialize |
| Future<T> | Một kết quả trong tương lai | Framework không tự chờ Future |
| CompletableFuture<T> | Một kết quả trong tương lai | Framework không tự await hoặc compose future |
| Flow<T> | Một chuỗi phần tử reactive | Không được MethodToolCallback unwrap thành kết quả tool |

Các giới hạn này áp dụng cho method-based tools và cả function-based tools theo hợp đồng được tài liệu hóa. FunctionToolCallback nhận Function, Supplier, Consumer hoặc BiFunction đồng bộ; việc đặt kiểu O là Mono<T> hoặc Future<T> không biến callback thành API bất đồng bộ.

### Phân biệt Future với DTO

Một DTO mô tả dữ liệu đã có:

~~~java
public record OrderStatusResult(
        String orderId,
        String status,
        Instant updatedAt
) {
}
~~~

Một Future mô tả một computation sẽ có kết quả sau:

~~~java
CompletableFuture<OrderStatusResult> pendingResult;
~~~

Model cần nhận dữ liệu của OrderStatusResult để trả lời người dùng. Nó không thể diễn giải một CompletableFuture hay biết khi nào future hoàn tất. Ứng dụng phải điều phối computation và chỉ đưa kết quả cụ thể vào tool result.

## FunctionToolCallback cũng dùng hợp đồng đồng bộ

FunctionToolCallback cho phép xây dựng tool từ Function, Supplier, Consumer hoặc BiFunction. Các functional interface này có phương thức thực thi trả về một giá trị Java trực tiếp.

Ví dụ:

~~~java
public record OrderLookupRequest(String orderId) {
}

public record OrderLookupResult(
        String orderId,
        String status
) {
}

Function<OrderLookupRequest, OrderLookupResult> lookupFunction =
        request -> orderService.lookup(request.orderId());

ToolCallback lookupTool = FunctionToolCallback
        .builder("lookupOrder", lookupFunction)
        .description("Tra cứu đơn hàng theo mã")
        .inputType(OrderLookupRequest.class)
        .build();
~~~

Đầu ra là OrderLookupResult, không phải Mono<OrderLookupResult>. Khi function hoàn tất, FunctionToolCallback chuyển kết quả qua tool result converter và trả String cho luồng tool calling.

Không khai báo:

~~~java
Function<OrderLookupRequest, Mono<OrderLookupResult>> lookupFunction;
~~~

Chỉ thay Function bằng BiFunction hoặc Supplier cũng không thay đổi quy tắc này. Các interface đó vẫn thực thi đồng bộ theo hợp đồng FunctionToolCallback.

## Dùng reactive service bên trong tool

Một ứng dụng có thể sử dụng WebClient, R2DBC hoặc một service reactive ở tầng nghiệp vụ. Điều đó không có nghĩa tool method được phép trả publisher. Có ba cách thiết kế phổ biến tùy nhu cầu.

### Trường hợp cần kết quả ngay trong cùng lượt hội thoại

Nếu model cần dữ liệu hoàn chỉnh để tiếp tục trả lời, tool phải trả một DTO cụ thể. Service có thể dùng adapter đồng bộ có timeout rõ ràng để lấy kết quả từ dependency reactive.

Ví dụ minh họa cho một ứng dụng đã xác định tool callback chạy trên worker thread phù hợp:

~~~java
@Service
public class OrderLookupService {

    private final WebClient webClient;

    public OrderLookupService(WebClient webClient) {
        this.webClient = webClient;
    }

    public OrderStatus getStatus(String orderId) {
        return webClient.get()
                .uri("/orders/{id}/status", orderId)
                .retrieve()
                .bodyToMono(OrderStatus.class)
                .block(Duration.ofSeconds(3));
    }
}
~~~

Tool gọi service và trả kết quả cụ thể:

~~~java
@Tool(description = "Tra cứu trạng thái đơn hàng")
public OrderStatus getOrderStatus(String orderId) {
    return orderLookupService.getStatus(orderId);
}
~~~

Đoạn code dùng block() chỉ là adapter từ reactive dependency sang hợp đồng tool đồng bộ. Phải đặt timeout và bảo đảm thao tác này không block Reactor Netty event loop. Không dùng block() tùy tiện trong một request thread của WebFlux; nếu đường thực thi có thể chạy trên event loop, cần offload toàn bộ phần blocking sang bounded worker executor hoặc thiết kế lại cách gọi.

Việc chỉ gọi subscribe() trong tool rồi trả về ngay cũng không đúng:

~~~java
@Tool
public String refreshOrder(String orderId) {
    orderClient.refresh(orderId)
            .subscribe();

    return "Refresh started";
}
~~~

Đoạn code này làm tool result được trả trước khi thao tác hoàn tất. Lỗi phát sinh sau đó có thể không được chuyển vào tool-calling loop, và model không có dữ liệu xác nhận trạng thái. Chỉ dùng kiểu fire-and-forget nếu nghiệp vụ thật sự thiết kế theo mô hình chấp nhận công việc và trả mã theo dõi.

### Trường hợp tác vụ dài: trả job ID

Nếu tác vụ kéo dài nhiều giây hoặc nhiều phút, không cần giữ vòng tool calling mở để chờ Future hoàn tất. Tool có thể gửi công việc vào queue hoặc job service rồi trả một DTO chứa job ID.

~~~java
public record JobAccepted(
        String jobId,
        String status
) {
}

public record ReportStatus(
        String jobId,
        String status,
        String downloadUrl
) {
}
~~~

Tool khởi tạo job:

~~~java
@Component
public class ReportTools {

    private final ReportJobService reportJobService;

    public ReportTools(ReportJobService reportJobService) {
        this.reportJobService = reportJobService;
    }

    @Tool(description = "Bắt đầu tạo báo cáo và trả mã theo dõi")
    public JobAccepted startReport(ReportRequest request) {
        return reportJobService.submit(request);
    }

    @Tool(description = "Kiểm tra trạng thái tạo báo cáo theo mã job")
    public ReportStatus getReportStatus(String jobId) {
        return reportJobService.getStatus(jobId);
    }
}
~~~

Tool đầu tiên trả ngay JobAccepted, ví dụ jobId=job-812 và status=QUEUED. Một worker riêng xử lý báo cáo ở nền. Model có thể thông báo rằng báo cáo đang được tạo hoặc gọi tool getReportStatus ở một vòng tiếp theo nếu cần kiểm tra ngay.

Lợi ích của mô hình job:

- Không giữ request chat mở trong thời gian tác vụ dài.
- Tool result có trạng thái rõ ràng và mã theo dõi.
- Có thể retry việc kiểm tra trạng thái mà không khởi tạo lại công việc.
- Có thể hủy hoặc đối soát job bằng API nghiệp vụ.
- UI có thể dùng endpoint riêng để stream tiến độ job nếu cần.

Không trả Future<JobAccepted> từ tool. Job service có thể dùng Future, queue hoặc reactive pipeline nội bộ, nhưng tool trả DTO đã có để Spring AI serialize.

### Trường hợp cần workflow reactive thực sự

Nếu nghiệp vụ cần kết hợp nhiều publisher, hủy theo subscription, backpressure hoặc fan-out theo stream, hãy đặt workflow reactive ở tầng ứng dụng. Có thể để endpoint điều phối các bước reactive và chỉ gọi model/tool ở các ranh giới mà hợp đồng Spring AI hỗ trợ.

Không giả định ToolCallingManager hoặc ToolCallback sẽ tự chuyển toàn bộ tool loop sang reactive chỉ vì controller trả Flux. Nếu cần một tool dispatcher bất đồng bộ hoàn toàn, ứng dụng phải sở hữu việc điều phối đó và ánh xạ tool call sang các thao tác reactive theo hợp đồng riêng. Khi tự điều khiển vòng lặp, ứng dụng cũng phải quản lý lịch sử hội thoại, lỗi, cancellation, observability và giới hạn vòng.

## Streaming không đồng nghĩa tool được thực thi song song

Flux của phản hồi chat biểu diễn các chunk được phát theo thời gian. Nó không tự quyết định nhiều tool call trong một response có chạy đồng thời hay không, và cũng không biến callback thành tác vụ non-blocking.

Cần phân biệt ba cơ chế:

| Cơ chế | Vai trò |
|---|---|
| Chat streaming | Phát nội dung hoặc metadata của model theo từng chunk |
| Tool calling loop | Nhận tool call hoàn chỉnh, thực thi callback và gửi kết quả về model |
| Concurrency của tool/service | Quyết định các tác vụ nghiệp vụ chạy tuần tự, song song hay qua queue |

Nếu một response có nhiều tool call, cách xử lý phụ thuộc vào ToolCallingManager và cấu hình thực thi. Không suy ra rằng vì kết quả chat là Flux nên mọi tool sẽ chạy song song. Nếu cần xử lý đồng thời, hãy thiết kế giới hạn concurrency, timeout, rate limit và khả năng hủy riêng cho dịch vụ nghiệp vụ.

Với tác vụ nền, dùng executor hoặc queue có giới hạn. Tránh tạo thread không giới hạn hoặc gọi subscribe() mà không theo dõi lifecycle. Cần có metric cho số job đang chạy, số job chờ, số lỗi và thời gian hoàn tất.

## Blocking và reactive trong cùng ứng dụng

Tài liệu Spring AI 2.1.0 phân biệt hai đường xử lý:

- Streaming chat chỉ được hỗ trợ qua reactive stack.
- Non-streaming chat dùng servlet stack.
- Built-in advisors có đường xử lý blocking cho call và đường xử lý non-blocking cho stream.
- Tool calling vẫn mang tính imperative và có thể tạo workflow blocking.

Điều này có nghĩa ứng dụng có thể stream phản hồi model mà vẫn có đoạn tool execution đồng bộ. Nếu tool method gọi JDBC blocking hoặc HTTP client blocking, thời gian thực thi tool vẫn chiếm thread cho đến khi method trả kết quả.

Một số nguyên tắc vận hành:

- Không gọi block() trên Reactor Netty event loop.
- Không dùng Future.get() hoặc CompletableFuture.join() không giới hạn.
- Đặt timeout cho từng dependency và deadline cho toàn request.
- Nếu cần chạy blocking I/O trong reactive app, offload sang bounded scheduler/executor ở ranh giới được kiểm soát.
- Nếu công việc kéo dài, trả job ID thay vì giữ tool call chờ vô hạn.
- Theo dõi cancellation và bảo đảm thao tác ghi có idempotency.

Không nên biến mọi service thành reactive chỉ để có thể stream chat. Hãy chọn mô hình I/O phù hợp với tầng thực thi và cách tool callback được gọi.

## Xử lý lỗi và timeout khi chuyển đổi async sang sync

Khi tool phải chờ một dependency reactive hoặc future, hãy quy định rõ:

- Timeout tối đa cho một lần chờ.
- Hành vi khi timeout: ném exception hoặc trả trạng thái nghiệp vụ phù hợp.
- Hành vi khi caller hủy request.
- Cách xử lý lỗi upstream.
- Có được retry hay không.
- Thao tác ghi có idempotency key hay không.

Ví dụ với Future, nếu ứng dụng bắt buộc chờ kết quả để trả trong cùng lượt, hãy dùng timeout hữu hạn và xử lý interruption:

~~~java
public OrderStatus awaitStatus(
        Future<OrderStatus> future,
        Duration timeout) {

    try {
        return future.get(
                timeout.toMillis(),
                TimeUnit.MILLISECONDS
        );
    }
    catch (TimeoutException ex) {
        future.cancel(true);
        throw new OrderLookupTimeoutException(ex);
    }
    catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new OrderLookupInterruptedException(ex);
    }
    catch (ExecutionException ex) {
        throw new OrderLookupException(ex.getCause());
    }
}
~~~

Đây là logic nội bộ của service adapter, không phải chữ ký tool. Tool vẫn gọi awaitStatus rồi trả OrderStatus cụ thể. cancel(true) chỉ gửi yêu cầu interrupt; nó không bảo đảm tác vụ hoặc server từ xa đã dừng. Với thao tác ghi, timeout không chứng minh server chưa commit, nên phải có idempotency hoặc đối soát.

Nếu không thể xác định kết quả thao tác, trả trạng thái không xác định có mã theo dõi thay vì báo thành công hoặc tự retry mù.

## Khi nào cần tự điều khiển tool loop?

ChatClient cùng ToolCallingAdvisor là lựa chọn mặc định khi muốn framework tự quản lý vòng gọi tool. Ứng dụng có thể dùng .stream() để nhận chunk của model mà vẫn giữ cơ chế thực thi tool.

Tự điều khiển loop phù hợp khi cần:

- Tự quyết định thời điểm thực thi từng tool call.
- Kết hợp một workflow reactive bên ngoài callback contract.
- Phát sự kiện tiến độ riêng cho từng iteration.
- Dừng hoặc chuyển hướng workflow theo tín hiệu ngoài.
- Quản lý approval, cancellation hoặc trạng thái job ở tầng orchestration.

Trong Spring AI 2.x, có thể tắt auto-registration của ToolCallingAdvisor cho một request bằng AdvisorParams.toolCallingAdvisorAutoRegister(false), sau đó đọc tool call từ ChatResponse và dùng ToolCallingManager để thực thi callback. Tuy nhiên, ToolCallback vẫn có hợp đồng call() đồng bộ. Nếu muốn thực thi Mono hoặc Future thật sự, cần tự quản lý dispatcher/loop bên ngoài ToolCallback thay vì mong ToolCallingManager unwrap publisher.

Tự điều khiển loop làm ứng dụng chịu trách nhiệm quản lý lịch sử hội thoại, nối tool result, giới hạn số vòng, xử lý lỗi và observability. Chỉ chọn khi workflow thực sự cần mức kiểm soát đó.

## Những lỗi thường gặp

- **Nhầm Flux<String> của chat với Flux<T> của tool:** một cái là stream phản hồi model, cái còn lại là publisher của dependency. Tool callback chuẩn không trả publisher.
- **Cho rằng Spring AI tự subscribe Mono:** MethodToolCallback không tự subscribe hoặc unwrap reactive return type.
- **Cho rằng Future sẽ được framework chờ:** Future và CompletableFuture không được tự động await để lấy tool result.
- **Dùng subscribe() rồi trả “đã hoàn tất”:** tool result được trả trước khi công việc kết thúc, lỗi sau đó có thể bị mất.
- **Dùng block() trên event loop:** có thể làm nghẽn toàn bộ request khác trên cùng event loop.
- **Dùng Future.get() không timeout:** tool có thể giữ request và thread vô hạn.
- **Cho rằng stream() khiến tool chạy song song:** streaming và concurrency là hai cơ chế độc lập.
- **Dùng partial tool-call delta làm input:** mảnh arguments chưa chắc là JSON hợp lệ và chưa phải tool call hoàn chỉnh.
- **Tạo thread không giới hạn cho tác vụ nền:** hệ thống có thể cạn tài nguyên khi nhiều request cùng gửi job.
- **Retry thao tác ghi sau timeout mà không idempotency:** server có thể đã commit, dẫn đến dữ liệu hoặc giao dịch trùng.
- **Tự điều khiển loop nhưng quên nối lịch sử:** model không nhận được tool result trước đó và có thể gọi lại tool hoặc trả lời sai.

## Kiểm thử streaming và kiểu trả về của tool

Nên kiểm thử riêng endpoint streaming, tool callback và adapter bất đồng bộ.

Các trường hợp cần có:

- Endpoint trả Flux<String> và phát nội dung theo nhiều chunk.
- Endpoint stream vẫn thực thi tool và gửi tool result về model trước khi phát câu trả lời cuối.
- Tool method trả DTO được serialize đúng.
- Method trả Mono/Flux/Future không được dùng như tool return type.
- Partial ToolCallPart không kích hoạt callback.
- Tool call hoàn chỉnh chỉ được thực thi một lần theo ID/lần gọi hợp lệ.
- Dependency reactive được chuyển thành DTO có timeout.
- Timeout và interruption được ánh xạ thành lỗi an toàn.
- Background job trả JobAccepted ngay và trạng thái có thể tra cứu.
- Hủy subscription không để lại tác vụ nền không được quản lý.
- Nhiều request đồng thời không làm cạn bounded executor.
- Thao tác ghi retry dùng cùng idempotency key.

Ví dụ kiểm thử một endpoint stream với WebTestClient:

~~~java
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import reactor.test.StepVerifier;

@Test
void shouldStreamChatContent() {
    FluxExchangeResult<String> result = webTestClient.get()
            .uri("/assistant/stream?question=Hello")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
            .returnResult(String.class);

    StepVerifier.create(result.getResponseBody())
            .expectNextCount(1)
            .thenCancel()
            .verify();
}
~~~

Test này xác minh endpoint thực sự phát chunk qua response stream. Nếu muốn xác minh toàn bộ câu trả lời, thay `thenCancel()` bằng các assertion cho nội dung cuối và `verifyComplete()`.

Ví dụ kiểm thử service chuyển reactive dependency thành DTO:

~~~java
@Test
void shouldReturnConcreteOrderStatus() {
    OrderStatus expected = new OrderStatus(
            "DH-1024",
            "IN_TRANSIT",
            "Da Nang"
    );

    when(orderClient.getStatus("DH-1024"))
            .thenReturn(Mono.just(expected));

    OrderStatus actual = orderService.getStatus("DH-1024");

    assertThat(actual).isEqualTo(expected);
}
~~~

Các ví dụ trên cần mock ChatClient/WebClient và cấu hình test context tương ứng với dự án. Với tool callback, kiểm tra ToolDefinition và kết quả String sau khi converter serialize DTO. Không cần gọi model thật chỉ để xác minh một tool method trả DTO đúng.

## Checklist trước khi phát hành

- [ ] Đã phân biệt Flux chat output với kiểu trả về của tool.
- [ ] Endpoint streaming dùng .stream().content() hoặc .stream().chatResponse() phù hợp.
- [ ] Tool method trả DTO/giá trị được Spring AI hỗ trợ, không trả Mono, Flux hoặc Future.
- [ ] FunctionToolCallback dùng Function/Supplier/Consumer/BiFunction đồng bộ.
- [ ] Partial tool-call arguments không bị thực thi trước khi hoàn chỉnh.
- [ ] Dependency reactive có adapter rõ ràng và timeout hữu hạn nếu cần kết quả cùng lượt.
- [ ] Không block Reactor event loop.
- [ ] Tác vụ dài dùng job ID hoặc workflow nền có quản lý.
- [ ] Cancellation, retry và idempotency được thiết kế theo nghiệp vụ.
- [ ] Concurrency có giới hạn và metric theo dõi.
- [ ] Có test streaming, tool result, timeout và job status.

## Ghi nhớ khi thiết kế

ChatClient.stream() trả Flux của các chunk phản hồi model. Nó có thể stream nội dung văn bản, metadata và một số phần arguments của tool call trong khi model đang tạo phản hồi. ToolCallingAdvisor vẫn quản lý vòng gọi công cụ và chỉ thực thi tool call khi lời gọi đã hoàn chỉnh.

MethodToolCallback và FunctionToolCallback không tự subscribe Mono/Flux hoặc await Future/CompletableFuture. Tool chuẩn cần trả một giá trị cụ thể để converter biến thành String gửi lại model. Nếu dependency là reactive, hãy chuyển đổi có kiểm soát sang DTO đồng bộ với timeout và thread phù hợp; nếu tác vụ kéo dài, trả job ID và theo dõi qua workflow nền. Streaming chat, kiểu trả về của tool và concurrency phải được thiết kế như ba trách nhiệm riêng.

Các ví dụ vòng lặp trong bài nhắm Spring AI 2.1.0, nơi ChatClient dùng ToolCallingAdvisor để quản lý tool execution. Spring AI 1.x đặt vòng thực thi bên trong từng ChatModel, nhưng giới hạn kiểu trả về Mono, Flux, Future và CompletableFuture của tool vẫn được tài liệu hóa ở cả method-based và function-based tool.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — ChatClient Streaming](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI 2.1.0 Reference — Tool Calling Loop và Streaming Tool Call Arguments](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 Reference — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 1.0 Reference — Method và Function Tool Limitations](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)


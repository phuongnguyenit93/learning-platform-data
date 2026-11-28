# Xử lý metadata bổ sung mà không làm đổi hợp đồng công cụ gốc

Trong một ứng dụng Spring AI có nhiều tool dùng để tra cứu dữ liệu hoặc gọi service nghiệp vụ, cùng một công cụ có thể cần thêm request ID, tenant ID, thông tin người thực hiện, loại dữ liệu, nhãn rủi ro, thời hạn xử lý và mã theo dõi audit. Những thông tin này có ích cho logging, authorization, rate limit, metrics và tracing, nhưng không nhất thiết là dữ liệu mà mô hình phải tạo khi gọi tool.

Ví dụ, công cụ getOrderStatus chỉ cần orderId do mô hình cung cấp. Ứng dụng vẫn phải biết khách hàng thuộc tenant nào, ai được phép đọc đơn hàng và request thuộc trace nào. Nếu thêm tenantId, actorId và traceId thành các tham số @ToolParam, ta đã làm đổi input schema và buộc mô hình đoán dữ liệu đáng lẽ phải do máy chủ xác định.

Mục tiêu của bài là **bổ sung metadata đúng ranh giới**: enrich pipeline qua advisor context hoặc ToolContext, bổ sung thông tin nội bộ ở registry/observability, nhưng vẫn giữ nguyên tên công cụ, mô tả, input schema, kết quả nghiệp vụ và cơ chế thực thi. Bài lấy Spring AI 2.1.0 làm mốc API, tập trung vào @Tool, ToolCallback, ToolCallingAdvisor và các CallAdvisor/StreamAdvisor.

## Nhận diện các lớp metadata khác nhau

Một tên gọi chung là "metadata" có thể chỉ những thứ hoàn toàn khác nhau:

| Lớp | Nơi lưu và API | Ai dùng | Có nên đưa dữ liệu bí mật vào không? |
|---|---|---|---|
| Tool definition | ToolDefinition: name, description, inputSchema | Mô hình chọn tool và tạo arguments | Không. Đây là phần mô hình nhìn thấy. |
| Framework tool metadata | ToolMetadata: returnDirect, requiresConfirmation, result converter và các cờ framework hỗ trợ | Spring AI quyết định cách xử lý tool | Không xem đây là kho metadata tự do; chỉ dùng đúng thuộc tính được API hỗ trợ. |
| Advisor context | ChatClientRequest.context() và ChatClientResponse.context() | Các advisor và code gọi ChatClient | Có thể chứa dữ liệu điều phối nội bộ, nhưng vẫn phải hạn chế truy cập và logging. |
| Tool execution context | ToolContext.getContext(), được truyền qua .toolContext(...) | Callback/service tại lúc thực thi | Có thể mang tenant, actor, correlation ID đáng tin cậy; không gửi thẳng vào prompt hoặc tool result. |
| Message metadata | .user(u -> u.metadata(...)), .system(s -> s.metadata(...)) | Message processing, provider/model tùy tích hợp | Không mặc định là vùng kín; cần phân loại trước khi dùng. |
| Operation metadata | Registry riêng, audit store, metrics/tracing | Ứng dụng, vận hành, kiểm toán | Chỉ lưu trường cần thiết, theo quyền và retention policy. |

ToolDefinition là hợp đồng mô hình nhìn thấy. ToolContext là dữ liệu ứng dụng giao trực tiếp cho callback, không đi qua arguments do mô hình tạo. Advisor context là một map của request/response dùng để chia sẻ trạng thái giữa các advisor. Ba cơ chế này không tự động đồng bộ với nhau.

### Luồng dữ liệu tổng thể

~~~mermaid
flowchart TD
    A[HTTP request đã xác thực] --> B[Application service tạo RequestMetadata]
    B --> C[ChatClient]
    C --> D[Advisor context: audit ID và telemetry]
    C --> E[ToolContext: tenant, actor, policy]
    C --> F[ToolDefinition: name, description, schema]
    F --> G[Model nhận tool definitions]
    G --> H[Model tạo tool name và JSON arguments]
    H --> I[ToolCallingAdvisor / ToolCallingManager]
    E --> I
    I --> J[ToolCallback]
    J --> K[Application service kiểm tra quyền]
    K --> L[Tool result nghiệp vụ]
    L --> M[Model tạo câu trả lời cuối]
    D --> N[Audit và tracing]
    J --> N
    M --> O[ChatClientResponse + advisor context]
~~~

Trong sơ đồ, ToolDefinition được đưa tới mô hình để nó hiểu công cụ. Tenant và actor lấy từ phiên xác thực được chuyển vào ToolContext khi ứng dụng thực thi tool; không yêu cầu mô hình suy ra chúng. Advisor context phục vụ các thành phần điều phối xung quanh vòng gọi, không tự thêm field vào JSON arguments.

## Xác định hợp đồng gốc cần được giữ nguyên

Giả sử có một công cụ tra cứu đơn hàng:

~~~java
@Component
class OrderTools {

    private final OrderQueryService orderQueryService;

    OrderTools(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Tool(description = "Tra cứu trạng thái đơn hàng theo mã đơn")
    public OrderSnapshot getOrderStatus(
            @ToolParam(description = "Mã đơn hàng") String orderId,
            ToolContext toolContext) {

        String tenantId = (String) toolContext.getContext().get("tenantId");
        String actorId = (String) toolContext.getContext().get("actorId");

        return orderQueryService.findAuthorized(orderId, tenantId, actorId);
    }
}
~~~

Tool input schema do Spring AI sinh từ các tham số mà mô hình phải cung cấp. Ở đây chỉ có orderId. ToolContext là tham số đặc biệt do framework cấp khi dispatch, không phải field để mô hình tạo trong JSON.

Từ góc nhìn mô hình, tool có thể được mô tả bằng JSON tương đương:

~~~json
{
  "name": "getOrderStatus",
  "description": "Tra cứu trạng thái đơn hàng theo mã đơn",
  "inputSchema": {
    "type": "object",
    "properties": {
      "orderId": {"type": "string"}
    },
    "required": ["orderId"]
  }
}
~~~

Đây là bản diễn giải rút gọn của ToolDefinition, không phải lời gọi trực tiếp đến API schema builder. Khi bổ sung audit, tracing hoặc tenant context, các field name, description, inputSchema và kiểu dữ liệu trả về của công cụ phải giữ ý nghĩa ban đầu. Đặc biệt:

- Không thêm auditId vào required properties chỉ để theo dõi request.
- Không đổi tên getOrderStatus thành tên mới nếu mục tiêu chỉ là thêm telemetry.
- Không chèn dữ liệu nội bộ vào tool description để mô hình đọc.
- Không thêm wrapper bất ngờ vào result JSON khi downstream đang trông đợi OrderSnapshot.
- Không tự bật returnDirect hoặc requiresConfirmation chỉ vì thay đổi metadata vận hành.

Nếu nghiệp vụ thực sự cần model cung cấp thông tin mới, đó là thay đổi hợp đồng có chủ đích, cần version và kiểm thử riêng.

## Advisor context: metadata chạy dọc pipeline

ChatClientRequest là record giữ Prompt và context của request. ChatClientResponse giữ ChatResponse và context cùng luồng thực thi. Advisor có thể đọc context để quyết định logging, đo thời gian hoặc gắn dữ liệu bổ sung cho code gọi ChatClient mà không sửa nội dung prompt.

Gắn parameter vào advisor context tại chỗ gọi:

~~~java
String runId = runIdGenerator.newRunId();
String traceLabel = requestScope.safeTraceLabel();

ChatClientResponse response = chatClient.prompt()
        .user("Đơn ORD-100 đang ở trạng thái nào?")
        .tools(orderTools)
        .advisors(a -> a
                .param("app.audit.runId", runId)
                .param("app.audit.traceLabel", traceLabel))
        .call()
        .chatClientResponse();
~~~

Đường .advisors(a -> a.param(...)) tạo advisor context cho từng request. Nội dung này có thể được custom advisor đọc bằng request.context(). Code gọi có thể đọc metadata sau cùng từ response.context() nếu advisor ghi vào response. Chỉ dùng .call().content() khi chỉ cần câu trả lời văn bản.

Lưu ý: việc đặt một giá trị vào advisor context **không tự động** chuyển giá trị đó vào ToolContext, Prompt, ToolDefinition hoặc ToolCallback. Nếu callback cần actor/tenant, hãy truyền qua .toolContext(...) một cách tường minh từ nguồn đáng tin cậy.

### Đặt tên key và tránh đụng nhau

Không dùng các key chung chung như id, status, data hoặc context. Nên phân vùng namespace:

~~~java
public final class AppAdvisorKeys {

    public static final String RUN_ID = "app.audit.runId";
    public static final String TRACE_LABEL = "app.audit.traceLabel";
    public static final String START_NANOS = "app.metrics.startNanos";
    public static final String ELAPSED_MILLIS = "app.metrics.elapsedMs";

    private AppAdvisorKeys() {
    }
}
~~~

Nên coi key và kiểu dữ liệu là một hợp đồng nội bộ giữa các advisor. Với dữ liệu quan trọng, kiểm tra tồn tại/kiểu trước khi sử dụng; không cast không an toàn, không dùng null làm giá trị mặc định cho những quyết định liên quan quyền.

## Viết một advisor thêm metadata vào response context

Ví dụ sau đo thời gian và gắn runId vào ChatClientResponse. Nó không sửa prompt, tool definition, tool arguments hoặc content của model:

~~~java
public final class RequestMetadataAdvisor implements CallAdvisor, StreamAdvisor {

    private final AuditSink auditSink;

    public RequestMetadataAdvisor(AuditSink auditSink) {
        this.auditSink = auditSink;
    }

    @Override
    public String getName() {
        return "RequestMetadataAdvisor";
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 150;
    }

    @Override
    public ChatClientResponse adviseCall(
            ChatClientRequest request,
            CallAdvisorChain chain) {

        String runId = requireRunId(request.context());
        long started = System.nanoTime();

        try {
            ChatClientResponse response = chain.nextCall(request);
            long elapsedMs =
                    TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);

            auditSink.recordCompleted(runId, elapsedMs);
            return response.mutate()
                    .context(AppAdvisorKeys.RUN_ID, runId)
                    .context(AppAdvisorKeys.ELAPSED_MILLIS, elapsedMs)
                    .build();
        }
        catch (RuntimeException ex) {
            auditSink.recordFailed(runId, ex.getClass().getSimpleName());
            throw ex;
        }
    }

    @Override
    public Flux<ChatClientResponse> adviseStream(
            ChatClientRequest request,
            StreamAdvisorChain chain) {

        return Flux.defer(() -> {
            String runId = requireRunId(request.context());
            long started = System.nanoTime();

            return chain.nextStream(request)
                    .map(chunk -> chunk.mutate()
                            .context(AppAdvisorKeys.RUN_ID, runId)
                            .build())
                    .doFinally(signal -> auditSink.recordStreamTermination(
                            runId,
                            signal.name(),
                            TimeUnit.NANOSECONDS.toMillis(
                                    System.nanoTime() - started)));
        });
    }

    private static String requireRunId(Map<String, Object> context) {
        Object value = context.get(AppAdvisorKeys.RUN_ID);
        if (!(value instanceof String runId) || runId.isBlank()) {
            throw new IllegalArgumentException("Thiếu runId đáng tin cậy");
        }
        return runId;
    }
}
~~~

Các class AuditSink và AppAdvisorKeys là thành phần của ứng dụng. Mọi lần gọi ChatClient dùng advisor này phải cung cấp runId từ server; thiếu runId là lỗi cấu hình request. Thời gian đo bằng nanoTime để tránh ảnh hưởng của việc đồng hồ hệ thống điều chỉnh.

Với call path, metadata được thêm sau khi chain trả response; với stream path, mỗi ChatClientResponse chunk được gắn runId để subscriber có thể ghép đúng luồng. doFinally chỉ ghi nhận COMPLETE, ERROR hoặc CANCEL và thời gian; nó không khẳng định tool đã commit hay rollback.

Khi stream bị hủy, không đảm bảo một chunk cuối được gửi cho UI. Nếu cần sự kiện hoàn tất bền vững, lưu ở event store hoặc out-of-band channel riêng; đừng dựa vào subscriber luôn nhận chunk cuối.

### Đăng ký advisor mà vẫn giữ vòng tool calling

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultAdvisors(new RequestMetadataAdvisor(auditSink))
        .build();
~~~

RequestMetadataAdvisor chỉ implement CallAdvisor và StreamAdvisor, không implement ToolAdvisor. ChatClient vẫn dùng ToolCallingAdvisor mặc định để điều phối công cụ, tránh thay đổi hành vi của vòng gọi.

Spring AI 2.1.0 có ToolCallingAdvisor mặc định ở order HIGHEST_PRECEDENCE + 300. Advisor ví dụ ở +150 nằm bên ngoài vòng tool loop, vì vậy đo một lần cho toàn bộ user turn. Nếu dùng order lớn hơn +300, advisor nằm bên trong loop và có thể chạy lại trên mỗi iteration model. Lựa chọn order phải dựa vào metadata cần thu thập theo user turn hay theo từng model call.

Một advisor nên có một mục đích rõ và không giữ mutable request state trong field của singleton. Dùng biến local trong adviseCall hoặc Flux.defer của adviseStream, vì một ChatClient thường phục vụ nhiều request đồng thời.

## ToolContext: metadata nội bộ tại thời điểm thực thi

Nếu callback cần tenantId hoặc actorId để truy cập dữ liệu, ToolContext là kênh phù hợp. Spring AI chuyển map .toolContext(...) tới tool khi callback được dispatch mà không bắt mô hình sinh thêm argument.

~~~java
RequestPrincipal principal = authenticatedRequest.principal();
String runId = runIdGenerator.newRunId();

ChatClientResponse response = chatClient.prompt()
        .user("Xem trạng thái đơn hàng ORD-100")
        .tools(orderTools)
        .toolContext(Map.of(
                "tenantId", principal.tenantId(),
                "actorId", principal.userId(),
                "runId", runId
        ))
        .advisors(a -> a.param(AppAdvisorKeys.RUN_ID, runId))
        .call()
        .chatClientResponse();
~~~

Trong ví dụ, RequestPrincipal là thông tin đã xác thực ở server. Model vẫn chỉ thấy getOrderStatus(orderId). Service nghiệp vụ kiểm tra rằng orderId thuộc tenant và actor có quyền đọc đơn; ToolContext không tự tạo authorization.

Đây là trường hợp metadata được chuyển tới hai nơi:

- Advisor context giữ runId để thống kê vòng ChatClient và tạo metadata trên response.
- ToolContext giữ runId, tenantId và actorId để callback/service thực thi đúng phạm vi.

Hai map có một số giá trị giống nhau vì **application service chủ động truyền**, không phải do Spring AI tự sao chép advisor context sang ToolContext.

### Khi metadata đến từ request HTTP

Hãy lấy metadata nhạy cảm từ Spring Security principal, phiên đăng nhập hoặc request scope đã được xác thực. Không lấy tenantId từ nội dung user prompt hoặc một field do model tạo để quyết định quyền.

Nên dùng các kiểu immutable đơn giản như String, UUID, enum, record nhỏ; tránh đưa EntityManager, Entity JPA sống, credential, HTTP request object hoặc các mutable singleton vào ToolContext. Nếu cần truy cập secret, truyền một reference đã được kiểm tra rồi để service lấy secret từ kho phù hợp.

Nếu có default toolContext và toolContext ở cấp request, Spring AI merge hai map với giá trị runtime ưu tiên. Vì vậy không được đặt các identity nhạy cảm làm default chung cho một ChatClient nhiều tenant rồi trông chờ mọi request luôn override đúng.

### Metadata không nên trở thành arguments của mô hình

Cách triển khai sai:

~~~java
@Tool(description = "Tra cứu trạng thái đơn hàng")
public OrderSnapshot getOrderStatus(
        String orderId,
        String tenantId,
        String actorId,
        String traceId) {
    // Model phải tự tạo tenantId, actorId, traceId: không phù hợp.
}
~~~

Cách phù hợp là giữ input schema chỉ có orderId và nhận phần còn lại qua ToolContext. Mô hình có thể biết hoặc đoán một mã tenant, nhưng điều đó không làm mã ấy đáng tin cậy.

## ToolMetadata chỉ dành cho các thuộc tính xử lý được Spring AI hỗ trợ

ToolCallback có hai phần riêng:

~~~java
public interface ToolCallback {
    ToolDefinition getToolDefinition();
    ToolMetadata getToolMetadata();
    String call(String toolInput);
    String call(String toolInput, ToolContext toolContext);
}
~~~

ToolDefinition cung cấp name, description và inputSchema cho mô hình. ToolMetadata chứa các lựa chọn mà framework dùng khi điều phối công cụ, ví dụ returnDirect hoặc yêu cầu confirmation, cùng những thuộc tính được phiên bản đang dùng hỗ trợ.

~~~java
ToolMetadata toolMetadata = ToolMetadata.builder()
        .returnDirect(true)
        .build();
~~~

Đây là ví dụ về một thuộc tính xử lý thực sự có sẵn, không phải chỗ để thêm mọi metadata nghiệp vụ. Nếu một dự án muốn bổ sung ownerTeam, dataClassification, costTier hay approvalPolicyId thì không nên tự phỏng đoán ToolMetadata có một map tùy ý tên customMetadata. Hãy lưu chúng trong registry riêng hoặc trong cấu hình của lớp policy/observability.

Đặc biệt, chỉnh ToolMetadata có thể **thay đổi hành vi**: returnDirect khiến tool result được trả trực tiếp cho caller; requiresConfirmation làm thay đổi điểm chờ phê duyệt. Với yêu cầu chỉ thêm audit, đừng sửa những cờ đó.

## Sidecar registry cho thông tin quản trị riêng của ứng dụng

Một registry có thể gắn metadata với tool bằng định danh ổn định mà không thay đổi ToolDefinition:

~~~java
public record ToolGovernance(
        String toolName,
        String ownerTeam,
        String dataClassification,
        String riskTier,
        boolean sideEffecting) {
}

@Component
class ToolGovernanceRegistry {

    private final Map<String, ToolGovernance> metadata;

    ToolGovernanceRegistry() {
        this.metadata = Map.of(
                "getOrderStatus",
                new ToolGovernance(
                        "getOrderStatus",
                        "orders",
                        "INTERNAL",
                        "LOW",
                        false
                ),
                "cancelOrder",
                new ToolGovernance(
                        "cancelOrder",
                        "orders",
                        "RESTRICTED",
                        "HIGH",
                        true
                )
        );
    }

    public ToolGovernance require(String toolName) {
        ToolGovernance value = metadata.get(toolName);
        if (value == null) {
            throw new IllegalArgumentException("Không có policy cho tool");
        }
        return value;
    }
}
~~~

Registry này minh họa cách gắn metadata ứng dụng bên ngoài hợp đồng tool. Trong sản phẩm lớn, key nên bao gồm namespace/server hoặc phiên bản tool nếu nhiều hệ thống cùng công bố một tên. Nội dung registry có thể đến từ cấu hình, database hoặc service catalog do ứng dụng quản lý.

Từ registry, application service có thể:

1. Ghi nhãn metrics theo tool family và risk tier.
2. Quyết định có cho phép tool xuất hiện trong request không.
3. Chọn policy xác nhận hay giới hạn chi phí phù hợp.
4. Kiểm tra owner, lifecycle và khả năng đã bị disable.
5. Cung cấp thông tin audit nội bộ khi tool được thực thi.

Hãy ưu tiên kiểu dữ liệu cụ thể thay vì map tùy ý nếu metadata ảnh hưởng bảo mật hoặc hành vi nghiệp vụ. Với bản ghi không tồn tại, fail closed cho công cụ rủi ro cao là lựa chọn an toàn hơn cho phép chạy theo mặc định.

## Khi cần quan sát riêng từng callback, dùng một wrapper bảo toàn ủy quyền

Advisor là lớp bao quanh lượt gọi model hoặc toàn bộ tool loop. Để biết chính xác callback nào bắt đầu và kết thúc, có thể bọc ToolCallback và ghi nhận thời gian trực tiếp tại ranh giới thực thi. Wrapper phải ủy quyền nguyên vẹn ToolDefinition, ToolMetadata và kết quả.

~~~java
public final class AuditedToolCallback implements ToolCallback {

    private final ToolCallback delegate;
    private final ToolAuditSink audit;

    public AuditedToolCallback(
            ToolCallback delegate,
            ToolAuditSink audit) {
        this.delegate = delegate;
        this.audit = audit;
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
        return observe(() -> delegate.call(toolInput));
    }

    @Override
    public String call(String toolInput, ToolContext toolContext) {
        return observe(() -> delegate.call(toolInput, toolContext));
    }

    private String observe(Supplier<String> invocation) {
        String toolName = delegate.getToolDefinition().name();
        long started = System.nanoTime();

        try {
            String result = invocation.get();
            audit.succeeded(
                    toolName,
                    TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started));
            return result;
        }
        catch (RuntimeException ex) {
            audit.failed(
                    toolName,
                    ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
~~~

Wrapper này chỉ đo thời gian và outcome. Nó không log raw toolInput, ToolContext hoặc result vì chúng có thể chứa thông tin cá nhân, dữ liệu nghiệp vụ, tenant identifier hoặc secret.

Có thể tạo callback gốc từ @Tool-annotated object rồi bọc lại trước khi đăng ký:

~~~java
ToolCallback[] original = ToolCallbacks.from(orderTools);

ToolCallback[] observed = Arrays.stream(original)
        .map(callback -> new AuditedToolCallback(callback, auditSink))
        .toArray(ToolCallback[]::new);

String answer = chatClient.prompt()
        .user("Tra cứu đơn hàng ORD-100")
        .tools((Object[]) observed)
        .toolContext(Map.of(
                "tenantId", principal.tenantId(),
                "actorId", principal.userId()))
        .call()
        .content();
~~~

Tùy overload thực tế của phiên bản được dùng, có thể truyền mảng ToolCallback trực tiếp vào .tools(...). Điểm quan trọng là chỉ đăng ký **wrapper được cấp phép** và không để callback gốc cũng có thể được resolve bằng một đường khác mà bỏ qua kiểm tra/quan sát. Đặc biệt phải rà soát ToolCallbackResolver và cơ chế fallback resolution nếu ứng dụng mở đường tìm tool theo tên.

### Vì sao phải ủy quyền cả hai dạng call?

ToolCallback có phiên bản call chỉ nhận toolInput và phiên bản nhận thêm ToolContext. Nếu wrapper quên ủy quyền call(toolInput, toolContext), tenant/actor có thể không đến được service hoặc một đường gọi có thể bỏ qua audit. Nếu wrapper quên getToolMetadata, returnDirect/confirmation có thể thay đổi so với callback gốc. Nếu wrapper tự dựng ToolDefinition mới, inputSchema hoặc name có thể lệch và model gọi sai.

Để chứng minh không đổi hợp đồng, hãy so sánh ToolDefinition trước/sau wrapper và chạy test cho cả hai overload; kiểm tra metadata framework và result String vẫn giống khi delegate thành công.

## Gắn metadata vào response mà không thêm field vào tool result

Khi một công cụ trả OrderSnapshot, kết quả tool được ToolCallResultConverter chuyển thành String. Nếu bất ngờ bọc nó trong một object chứa metadata:

~~~json
{
  "data": {
    "orderId": "ORD-100",
    "status": "SHIPPING"
  },
  "auditId": "run-xyz",
  "costTier": "LOW"
}
~~~

thì cấu trúc kết quả đã thay đổi. Điều này có thể khiến mô hình suy diễn sai hoặc phá vỡ consumer đang kỳ vọng các field orderId/status ở top level.

Nếu mục đích chỉ để backend đọc auditId và chi phí xử lý, hãy đặt chúng trong ChatClientResponse.context hoặc hệ thống audit riêng. Chẳng hạn:

~~~java
ChatClientResponse result = chatClient.prompt()
        .user(question)
        .tools(orderTools)
        .toolContext(trustedToolContext)
        .advisors(a -> a.param(AppAdvisorKeys.RUN_ID, runId))
        .call()
        .chatClientResponse();

Object returnedRunId = result.context().get(AppAdvisorKeys.RUN_ID);
ChatResponse chatResponse = result.chatResponse();
~~~

ChatResponse giữ nội dung trả lời của model và metadata provider; context bên ngoài của ChatClientResponse giữ dữ liệu từ advisor. Không cần nhét application metadata vào AssistantMessage hay ToolResponseMessage chỉ để API caller đọc được.

Nếu cần gửi kết quả cho client REST, response DTO của ứng dụng có thể có trường requestId bên cạnh answer, nhưng đây là **hợp đồng API REST** được thiết kế riêng, không phải thay đổi JSON input schema hoặc tool result:

~~~java
public record AnswerEnvelope(
        String requestId,
        String answer) {
}
~~~

Việc hiển thị requestId cho người dùng phải là lựa chọn có kiểm soát. Không phơi bày tenant secret, trace internal ID hoặc bản ghi audit chi tiết một cách vô tình.

## Chọn vị trí advisor so với ToolCallingAdvisor

ToolCallingAdvisor của Spring AI 2.1.0 xử lý vòng model → tool → model và có order mặc định HIGHEST_PRECEDENCE + 300. Advisor có order nhỏ hơn nằm bên ngoài vòng lặp; advisor có order lớn hơn chạy trong vòng lặp của ToolCallingAdvisor.

| Nhu cầu metadata | Vị trí đề xuất | Lý do |
|---|---|---|
| Correlation ID cho toàn user turn | Bên ngoài vòng loop | Chỉ gắn và ghi một lần cho cả turn. |
| Tổng latency và outcome của user turn | Bên ngoài vòng loop | Bao gồm các iteration và tool executions. |
| Mỗi model request riêng | Bên trong loop | Advisor chạy mỗi iteration và có thể đọc response từng lượt. |
| Đếm tool call cụ thể đã thực thi | Wrapper callback hoặc observer của ToolCallingManager | Phân biệt tool được model đề xuất với tool thực sự được gọi. |
| Chặn tool có tác động nghiệp vụ | Ở ToolCallingManager/policy và service nghiệp vụ | Cần enforce trước dispatch; logging advisor không đủ. |
| Trả metadata cho caller cuối | Bên ngoài loop sau khi nhận response | Metadata ổn định, tránh ghi đè không chủ đích từ từng iteration. |

Spring AI yêu cầu chỉ có một advisor implement marker ToolAdvisor trong chain. RequestMetadataAdvisor ở ví dụ không phải ToolAdvisor, nên có thể dùng cạnh ToolCallingAdvisor mặc định. Nếu cần thay đổi cơ chế điều phối tool, hãy thay thế ToolCallingAdvisor bằng một custom ToolAdvisor duy nhất hoặc dùng extension hooks của ToolCallingAdvisor.

### Quan sát tool intent khác với tool execution

Một advisor bên trong loop có thể thấy model trả tool calls, nhưng đó mới là yêu cầu thực thi. ToolCallingManager còn phải resolve callback, kiểm tra confirmation, quyền và exception policy; callback có thể bị từ chối hoặc thất bại.

Đừng phát sự kiện "đã cập nhật đơn hàng" khi mới thấy AssistantMessage chứa tool call updateOrder. Hãy phát intent/proposed ở model boundary và started/succeeded/failed tại execution boundary. Với thao tác ghi, chỉ công bố thành công khi service xác minh side effect đã commit.

Khi model trả nhiều tool calls trong cùng iteration, mỗi callback cần toolCallId/operationId riêng để ghi nhận đúng và tránh trộn outcome. Không dùng duy nhất tool name làm khóa idempotency vì cùng một tool có thể được gọi nhiều lần với arguments khác nhau.

## Metadata trong streaming

Trong luồng streaming, ChatClientResponse có thể xuất hiện nhiều lần dưới dạng chunk. Việc gắn runId vào từng chunk không biến nó thành một tool result. Khi downstream dùng .stream().content(), nó chỉ nhận văn bản; muốn đọc advisor context, dùng .stream().chatClientResponse().

~~~java
Flux<ChatClientResponse> output = chatClient.prompt()
        .user(question)
        .tools(orderTools)
        .toolContext(trustedToolContext)
        .advisors(a -> a.param(AppAdvisorKeys.RUN_ID, runId))
        .stream()
        .chatClientResponse();

return output.map(chunk -> {
    String observedRunId =
            (String) chunk.context().get(AppAdvisorKeys.RUN_ID);
    return mapToSafeSseEvent(observedRunId, chunk.chatResponse());
});
~~~

mapToSafeSseEvent là hàm của ứng dụng: nó không nên đưa nguyên Prompt, ToolContext, raw arguments hay metadata provider nhạy cảm vào SSE. Nhiều chunk có thể cùng runId; UI phải nối text theo thứ tự stream thay vì hiểu mỗi chunk là một câu trả lời hoàn chỉnh.

Một vài giới hạn cần nắm:

- Cancellation có thể xảy ra mà không có response cuối.
- doFinally ghi nhận tín hiệu của subscription; nó không chứng minh tool side effect đã rollback.
- Một advisor bên trong loop sẽ thấy nhiều iteration, nên counters cần phân biệt per-iteration và per-turn.
- Nếu cần kết quả aggregated ở cuối stream, dùng ChatClientMessageAggregator để quan sát response hoàn chỉnh, không tạo thủ công một lượt model mới chỉ để lấy metadata.
- Nếu response được gắn context bằng mutate(), giữ nguyên chatResponse của chunk để không làm đổi stream semantics.

## Message metadata không phải một kho bí mật

ChatClient hỗ trợ metadata trên user và system messages:

~~~java
ChatClientResponse response = chatClient.prompt()
        .user(u -> u
                .text("Tra cứu đơn hàng ORD-100")
                .metadata("uiLocale", "vi-VN"))
        .call()
        .chatClientResponse();
~~~

Message metadata được gắn với Message và có thể được các advisor hoặc tích hợp model/provider sử dụng. Không mặc định rằng metadata này hoàn toàn tách khỏi model; việc provider có truyền một trường metadata cụ thể hay không còn phụ thuộc implementation.

Do đó:

- Chỉ đặt trường thực sự thuộc về message khi cần xử lý message.
- Không đặt credential, access token, tenant secret hoặc đối tượng session tại đây.
- Dùng advisor context cho metadata vòng điều phối.
- Dùng ToolContext cho metadata cần thiết khi callback thực thi.
- Dùng registry/audit store cho dữ liệu quản trị lâu dài hoặc event bền vững.

Khi thêm metadata vào message, Spring AI kiểm tra key không rỗng và value không null. Một metadata map lớn cũng có thể làm tăng chi phí lưu trữ/serialization; chỉ giữ dữ liệu cần thiết.

## Vòng đời và tính nhất quán của metadata

Metadata như correlation ID, tenant ID và risk tier có vòng đời khác nhau:

| Trường | Phạm vi đúng | Quy tắc quản lý |
|---|---|---|
| runId | Một lượt request hoặc workflow | Tạo ở server; không tái sử dụng nhầm giữa request độc lập. |
| trace ID | Một trace phân tán | Theo tracing SDK; không tạo ID mới tùy tiện mỗi advisor. |
| tenantId/actorId | Một principal/request đã xác thực | Lấy từ security context; kiểm tra lại quyền tại service. |
| toolCallId | Một tool call cụ thể | Dùng ID framework/provider kèm run ID để tương quan sự kiện. |
| operationId | Một side effect logic | Giữ ổn định qua retry, dùng idempotency store. |
| dataClassification | Thuộc tool/data product hoặc result | Quản lý trong registry có version; không để model tự đặt. |
| riskTier | Chính sách của một tool/action | Có thể thay đổi qua cấu hình; refresh khi policy đổi. |
| elapsedMs | Một call/iteration/tool execution | Đo bằng monotonic clock; không chứa dữ liệu cá nhân. |

Đừng đưa một mutable Map toàn cục vào ChatClient dùng chung. Khi hai request chạy đồng thời, fields singleton có thể bị ghi đè và lộ thông tin của nhau. Dùng request-local context, immutable records và registry đồng bộ hóa phù hợp.

### Metadata thay đổi trong khi tool loop chạy

Một user có thể bị thu hồi quyền sau khi công cụ được đưa vào request. ToolContext chứa snapshot identity ở đầu request, nhưng **service vẫn phải xác thực trạng thái quyền và quyền sở hữu tài nguyên tại thời điểm thao tác** khi nghiệp vụ yêu cầu.

Ví dụ, advisor gắn riskTier=LOW lúc đầu; trước khi callback thực thi, cấu hình có thể cập nhật tool thành HIGH. Execution policy cần có khả năng tra cứu policy hiện tại hoặc theo một version đã được chốt và cho phép theo hợp đồng. Đừng coi metadata đã gắn từ đầu là quyền bất biến trong suốt một workflow dài.

### Metadata phát sinh sau khi tool chạy

Một tool có thể tạo business operation ID khi commit. Không nên cố "ghi ngược" operationId vào ToolDefinition hoặc sửa input schema để model thấy. Ghi operationId trong audit store keyed by runId + toolCallId, và chỉ trả một business reference đã lọc trong tool result nếu model thật sự cần để trả lời người dùng.

Nếu cần một progress UI, phát event status riêng có correlation ID đã kiểm tra. Không dùng exception message thô hay log payload nhạy cảm như một phương tiện truyền metadata cho client.

## Bảo mật và giới hạn observability

Spring AI hỗ trợ observation cho advisor và tool calling; có thể ghép với Micrometer/tracing để theo dõi latency và kết quả. Các dữ liệu có số lượng giá trị rất lớn như runId, userId hoặc raw arguments không phù hợp làm nhãn metric cardinality thấp.

| Dữ liệu | Nơi nên đưa |
|---|---|
| Tool name đã chuẩn hóa | Metric label được kiểm soát số lượng giá trị. |
| Tool family, risk tier, success/failure | Metric label hữu ích khi cardinality thấp. |
| runId, operationId, toolCallId | Trace/log có kiểm soát hoặc audit store, không là metric label đại trà. |
| Tenant/user identifier | Audit có quyền truy cập; có thể hash/pseudonymize theo policy. |
| Raw JSON arguments, model prompt, tool result | Chỉ ghi nếu có nhu cầu hợp lệ và cơ chế redact/retention; mặc định tránh. |
| Credentials, access token | Không ghi vào model, tool result, metrics, log hoặc trace. |

Không log nguyên ChatClientRequest hoặc ChatClientResponse khi trong context có dữ liệu nhạy cảm; record toString() có thể bao gồm nội dung context. Thay vào đó, log các field được allowlist và sanitize trước khi xuất bản.

### Không dựa vào advisor để thay thế authorization

Một logging advisor biết tool thuộc riskTier=HIGH không có nghĩa nó ngăn được mọi đường gọi tool. Tool có thể được gọi qua ChatModel trực tiếp, ToolCallingManager thủ công, resolver fallback hoặc một API service khác.

Kiểm soát quyền phải nằm ở ranh giới thực thi đáng tin cậy: application service và lớp policy chung. Advisor có thể bổ trợ bằng cách lọc danh mục hoặc chặn sớm, nhưng authorization cuối cùng phải kiểm tra lại action, resource, tenant, actor và trạng thái nghiệp vụ.

Nếu một wrapper callback được dùng để enforce policy, đảm bảo tất cả đường dispatch đều đi qua wrapper đó. Không công bố song song callback gốc hoặc resolver có thể bỏ qua wrapper. Kiểm thử cả call(String) và call(String, ToolContext), cùng nhánh returnDirect/confirmation.

## Các lỗi thiết kế dễ gặp

| Cách làm sai | Vấn đề | Giải pháp |
|---|---|---|
| Thêm tenantId vào @ToolParam | Model có thể đoán hoặc giả mạo tenant. | Truyền tenantId qua ToolContext, kiểm tra ở service. |
| Đưa traceId vào tool input schema | Đổi contract và tiêu hao token không cần thiết. | Dùng advisor context/ToolContext. |
| Đổi ToolDefinition chỉ để thêm audit label | Tool name/schema thay đổi ngoài ý muốn. | Dùng sidecar metadata registry. |
| Gói tool result vào object có audit metadata | Thay đổi result contract và bộc lộ dữ liệu nội bộ. | Gắn metadata vào ChatClientResponse.context hoặc audit store. |
| Dùng ToolMetadata như map tự do | API có các thuộc tính xử lý cụ thể. | Chỉ sửa metadata framework khi thực sự muốn đổi hành vi. |
| Wrapper không delegate getToolMetadata | returnDirect hoặc confirmation có thể đổi. | Delegate nguyên vẹn ToolMetadata. |
| Advisor giữ runId trong instance field | Nhiều request cùng ChatClient có thể trộn state. | Dùng local variable/context theo request. |
| Advisor ngoài loop để đếm từng model call | Chỉ thấy user turn tổng. | Đổi order vào trong loop hoặc dùng callback observer. |
| Advisor trong loop ghi "success" khi thấy tool intent | Callback có thể chưa chạy hoặc thất bại. | Quan sát chính ranh giới execution. |
| Gắn raw arguments vào metric tags | Lộ dữ liệu, cardinality bùng nổ. | Dùng tag thấp cardinality, redact và audit có kiểm soát. |
| Tin metadata từ client chưa xác thực | Có thể bị giả mạo quyền hoặc tenant. | Lấy identity từ server principal, không từ model. |

## Kiểm thử không làm đổi hợp đồng gốc

Nên có một bộ kiểm thử riêng cho tính tương thích, không chỉ kiểm tra advisor đã log đúng.

| Kiểm thử | Điều phải giữ/đạt |
|---|---|
| ToolDefinition trước và sau wrapper | Cùng name, description, inputSchema. |
| ToolMetadata trước và sau wrapper | Không thay cờ returnDirect, confirmation hoặc converter policy. |
| Tool arguments khi thêm advisor | JSON vẫn chỉ chứa các field model được phép tạo. |
| Tool result khi thêm wrapper | String trả về giống callback gốc với cùng input/context. |
| Advisor context | Có runId/elapsedMs đúng kiểu, không đổi ChatResponse content. |
| ToolContext | Callback nhận tenantId/actorId từ server; không xuất hiện trong tool schema. |
| Call path và stream path | Metadata xuất hiện đúng, không trộn request khác. |
| Multiple tool calls | Mỗi call có audit outcome riêng; runId chung nhưng operationId khác khi cần. |
| Tool execution failure | Exception được truyền tiếp; audit ghi failure nhưng không sửa kết quả thành success. |
| returnDirect | Hành vi bypass model giữ nguyên qua wrapper. |
| Confirmation | Tool chưa được xác nhận không bị thực thi chỉ vì advisor bổ sung metadata. |
| Resolver fallback | Không có đường gọi callback gốc vượt policy/wrapper. |
| Two concurrent tenants | Context không lẫn, quyền resource được service kiểm tra. |
| Cancellation | doFinally phản ánh CANCEL nhưng không xác nhận tool rollback. |
| Missing required metadata | Bị từ chối rõ ràng trước thao tác cần metadata. |

### Ví dụ test xác minh wrapper

~~~java
@Test
void wrapperPreservesToolContract() {
    ToolCallback original = ToolCallbacks.from(orderTools)[0];
    ToolCallback wrapped = new AuditedToolCallback(original, auditSink);

    assertThat(wrapped.getToolDefinition().name())
            .isEqualTo(original.getToolDefinition().name());
    assertThat(wrapped.getToolDefinition().description())
            .isEqualTo(original.getToolDefinition().description());
    assertThat(wrapped.getToolDefinition().inputSchema())
            .isEqualTo(original.getToolDefinition().inputSchema());
    assertThat(wrapped.getToolMetadata())
            .isEqualTo(original.getToolMetadata());
}
~~~

Với integration test, dùng service giả có kiểm tra tenant/actor và một model giả yêu cầu gọi getOrderStatus. Xác minh input schema vẫn chỉ có orderId, tool result không thêm audit fields và ChatClientResponse.context chứa runId. Kiểm thử cả stream(), errors và hai request đồng thời.

## Bài tập thực hành

Mở rộng một hệ thống hỗ trợ khách hàng với ba công cụ:

1. getOrderStatus(orderId): đọc trạng thái đơn hàng.
2. getRefundEligibility(orderId): kiểm tra điều kiện hoàn tiền.
3. requestRefund(orderId): khởi tạo nghiệp vụ hoàn tiền sau authorization/confirmation.

Tạo RequestMetadataAdvisor bổ sung runId và latency vào advisor context. Dùng .toolContext(...) để truyền tenantId, actorId, runId từ principal đáng tin cậy. Tạo ToolGovernanceRegistry với ownerTeam, riskTier, sideEffecting cho mỗi tool; không thêm trường vào ToolDefinition.

Viết AuditedToolCallback để thu duration và outcome ở ranh giới thực thi, đồng thời giữ nguyên getToolDefinition/getToolMetadata và cả hai overload call. Chạy test so sánh schema trước/sau, gọi tool với hai tenant khác nhau, thử một request thiếu runId và một request bị cancel khi stream.

Kết quả bài tập phải chứng minh: model vẫn chỉ cần các arguments nghiệp vụ ban đầu; quyền được xác thực bằng dữ liệu server; metadata xuất hiện ở đúng nơi; callback không mất returnDirect/confirmation; và tool result không bị bọc thêm fields.

## Danh sách kiểm tra trước khi triển khai

- [ ] Phân biệt ToolDefinition, ToolMetadata, advisor context, ToolContext và message metadata.
- [ ] Có baseline tool name, description, inputSchema và result contract trước khi mở rộng.
- [ ] Metadata vận hành không trở thành required @ToolParam.
- [ ] Advisor context dùng key namespace rõ ràng và kiểm tra kiểu dữ liệu.
- [ ] ToolContext chỉ nhận identity/correlation từ nguồn ứng dụng đáng tin cậy.
- [ ] Không giả định advisor context tự động trở thành ToolContext.
- [ ] RequestMetadataAdvisor được đặt đúng order trong/ngoài tool loop.
- [ ] Trong Spring AI 2.1.0 chỉ có một ToolAdvisor điều phối vòng tool.
- [ ] ToolMetadata chỉ dùng cho các cờ/framework features được hỗ trợ.
- [ ] Registry metadata nghiệp vụ tách khỏi ToolDefinition.
- [ ] Wrapper delegate getToolDefinition, getToolMetadata và cả hai dạng call.
- [ ] Tool result và model final content không bị gói thêm metadata ngoài hợp đồng.
- [ ] Sử dụng chatClientResponse() khi downstream cần advisor context.
- [ ] Stream path có xử lý per-subscription, cancellation và nhiều chunks.
- [ ] Authorization và confirmation vẫn được enforce ở execution boundary.
- [ ] Audit/trace/metrics được lọc, tránh secret và nhãn high-cardinality.
- [ ] Có test contract compatibility, concurrent tenants, errors, returnDirect và streaming.

Metadata bổ sung giúp ứng dụng quan sát, kiểm soát và truy vết tool calling tốt hơn khi được đặt đúng tầng. ToolDefinition và arguments thuộc hợp đồng giữa model và tool; ToolContext cung cấp dữ liệu thực thi đáng tin cậy; advisor context và audit registry phục vụ điều phối nội bộ. Giữ các ranh giới này độc lập giúp thêm tính năng mà không làm công cụ cũ đổi hành vi một cách âm thầm.

## Tài liệu tham khảo

- [Spring AI 2.1.0 – Advisors API](https://docs.spring.io/spring-ai/reference/api/advisors.html)
- [Spring AI 2.1.0 – Tool Calling, ToolContext và ToolCallback](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 – ToolCallingAdvisor, hook và advisor ordering](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 – ChatClient API, response/context và message metadata](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI 2.1.0 – ChatClientRequest.Builder API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/client/ChatClientRequest.Builder.html)
- [Spring AI 2.1.0 – ChatClientResponse.Builder API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/client/ChatClientResponse.Builder.html)

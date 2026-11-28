# Kiểm thử hồi quy schema, lỗi, streaming và quyền trước triển khai

## Mục tiêu và phạm vi

Trong ứng dụng **SPRING_AI_TOOL_CALLING**, mô hình ngôn ngữ có thể yêu cầu gọi các công cụ nghiệp vụ qua `@Tool` hoặc `ToolCallback`; ứng dụng chịu trách nhiệm thực thi, cấp ngữ cảnh tin cậy qua `ToolContext`, kiểm tra quyền, xử lý lỗi và điều phối vòng gọi nhiều lượt. Khi nâng cấp phiên bản Spring AI, đổi model/provider, chỉnh schema hoặc thêm tool, việc ứng dụng vẫn khởi động **không chứng minh** hợp đồng cũ còn đúng.

Bài này hướng dẫn thiết lập một **bộ kiểm thử hồi quy trước triển khai** với bốn trục chính:

1. **Schema:** tên tool, mô tả, JSON Schema, đối số bắt buộc/tùy chọn, định dạng kết quả và khả năng tương thích với model/provider.
2. **Lỗi:** input sai, tool exception, lỗi dịch vụ ngoài, retry/timeout, hạn mức vòng gọi, tình trạng đã thực thi nhưng mất phản hồi.
3. **Streaming:** phân biệt mảnh đối số đang sinh với tool call hoàn chỉnh, ghép lịch sử và kết quả, ngắt kết nối, tính nhất quán với blocking.
4. **Quyền:** danh sách tool theo vai trò, tenant/resource authorization, xác nhận hành động nguy hiểm, chống gọi lại và rò rỉ dữ liệu qua lỗi/log.

**Phiên bản tham chiếu:** Spring AI **2.1.0**. Các điểm của **2.0.x** và **1.x** được nhắc tới chỉ để định hướng migration, không coi toàn bộ phiên bản cũ có API hoặc hành vi giống 2.1. Ví dụ Java là các mảnh code phục vụ học thuật; phần kiểm thử sử dụng JUnit 5, AssertJ, Mockito và Jackson, cần bổ sung import, dependency và test infrastructure ở dự án thực tế.

Kết quả mong muốn không chỉ là “các test đều xanh”: nhóm triển khai phải có **bằng chứng có thể kiểm tra** rằng bản candidate giữ các bất biến bảo mật, nghiệp vụ và vận hành quan trọng; những khác biệt có chủ đích phải được ghi nhận và được chấp thuận trước rollout.

## 1. Tại sao nâng cấp dễ làm thay đổi hợp đồng tool calling?

Một công cụ `get_order_status` nhận `orderId`, đọc từ tenant đã xác thực và trả trạng thái đơn. Một công cụ `cancel_order` thay đổi dữ liệu, cần người dùng xác nhận. Khi thay phiên bản thư viện hoặc provider, có thể xảy ra:

- JSON Schema sinh ra thay đổi `required`, kiểu dữ liệu, tên tham số hoặc lời mô tả, khiến model phát lệnh gọi với đối số khác.
- Danh sách tool thực sự expose bị thay đổi do kết hợp default tools, request tools hoặc resolver fallback.
- Lỗi `RuntimeException` đi vào phản hồi model theo chính sách xử lý mới/cấu hình khác, làm lộ mã đơn hoặc thông tin nội bộ.
- Streaming sinh các `ToolCallPart` từng mảnh; mã ứng dụng đọc nhầm mảnh này thành lời gọi đã hoàn tất.
- Tool đã tạo tác dụng phụ rồi timeout, vòng gọi lặp lại khiến thao tác được thực hiện hai lần.
- Hội thoại chờ xác nhận được tiếp tục bằng một phản hồi bị sửa ở phía client, hoặc không kiểm lại quyền của người duyệt.

Trong Spring AI 2.1, `ChatClient` tự đăng ký `ToolCallingAdvisor` theo cấu hình mặc định để điều phối vòng tool, trong khi `ChatModel.call()`/`stream()` **chỉ trả yêu cầu gọi công cụ**; ứng dụng tự lái vòng nếu dùng `ChatModel` trực tiếp. Bản 1.x từng có vòng thực thi tool bên trong các `ChatModel`; đây là thay đổi kiến trúc từ nhánh 2.0 và cần đưa vào bài kiểm thử migration.

Một điểm khác của 2.1 là `AssistantMessage`/`UserMessage` dùng danh sách `MessagePart` có thứ tự; phần streaming có mảnh `ToolCallPart` *partial*, và cơ chế xác nhận tool call hỗ trợ tạm dừng một nhóm lời gọi. Khi upgrade, test phải đọc cả **metadata và cấu trúc phản hồi**, không chỉ so sánh chuỗi trả về từ `content()`.

## 2. Định nghĩa hợp đồng cần “đóng băng” trước thay đổi

Ghi baseline từ phiên bản đang chạy, rồi xác định expected behavior từ **quy tắc nghiệp vụ**. Baseline có thể đang chứa lỗi; không chấp nhận một vi phạm quyền chỉ vì bản cũ cũng vi phạm.

| Hợp đồng | Kiểm tra cụ thể | Bằng chứng nên lưu |
|---|---|---|
| Tool catalog | Tên duy nhất, mô tả, schema, tool nào xuất hiện trong từng role | Danh sách `ToolDefinition` đã chuẩn hóa |
| Input | Required/optional, type, enum, giới hạn, kiểm tra giá trị sau deserialization | JSON Schema và kết quả validation |
| Output | Dữ kiện trả về, mã lỗi công khai, `returnDirect` nếu dùng | JSON output hoặc dữ kiện chuẩn hóa |
| Model decision | Khi nào gọi tool, gọi công cụ nào, đối số nào, số vòng gọi | Tool-call sequence và counter của fake service |
| Runtime | Timeout, retry, ngưỡng vòng, exception policy, phản hồi lỗi | Trace, test assertion và error class |
| Streaming | Part partial/complete, thứ tự, ghép tool-result, hủy stream | Event log với loại part, tool execution count |
| Authorization | Role/tenant/ownership, confirmation, chống replay | Allowlist theo role và số side effect |
| Triển khai | Model ID, phiên bản Spring AI, cấu hình endpoint, rollout/rollback | Test manifest và release decision |

Mỗi lần chạy nên ghi **version tuple**: Java/Spring Boot, Spring AI BOM và starter, provider/model ID chính xác, tùy chọn model, schema digest, mã build, chế độ `call`/`stream`, cấu hình advisor và feature flags. Nếu một yếu tố thay đổi giữa baseline và candidate, ghi rõ để phân biệt thay đổi được kiểm soát với nhiễu.

Ví dụ manifest **do dự án tự định nghĩa** (không phải cấu hình bắt buộc của Spring AI):

```yaml
suite: tool-calling-contract-v3
appBuild: candidate-2026-11
springAi: 2.1.0
model:
  provider: candidate-provider
  id: pinned-model-version
execution:
  entryPoint: ChatClient
  modes: [blocking, streaming]
  retries: 0           # Đặt rõ trong test, tránh retry ẩn.
fixtures:
  tenant: tenant-A
  role: ORDER_VIEWER
  orders:
    ORD-17: DELIVERED
releaseGates:
  securityViolations: 0
  unintendedWrites: 0
  contractFailures: 0
  maxLoopTurns: 8       # Giới hạn minh họa của ứng dụng.
```

Các ngưỡng trên chỉ là **ví dụ**, không phải bảo đảm hoặc mặc định của Spring AI. Đặc biệt `maxLoopTurns` khác với giới hạn **số tool call** của `ToolCallingManager`: không nên coi hai loại hạn mức thay thế cho nhau.

## 3. Thiết kế fixture độc lập với provider

Dùng một câu chuyện nghiệp vụ đủ nhỏ để kiểm chứng chính xác:

- `get_order_status`: chỉ đọc, nhận mã đơn do người dùng cung cấp; tenant đến từ danh tính đã xác thực.
- `cancel_order`: thay đổi trạng thái; phải kiểm quyền trên đơn, có khóa idempotency của ứng dụng và yêu cầu xác nhận.
- Hai vai trò: `ORDER_VIEWER` chỉ được xem; `ORDER_MANAGER` có thể được cấp công cụ hủy trong phạm vi đơn được phép.
- Fake service có dữ liệu cố định: `ORD-17` thuộc `tenant-A`, `ORD-99` thuộc `tenant-B`, và counter cho từng phương thức.

### 3.1. Ví dụ `@Tool` và `ToolContext`

```java
record OrderStatus(String orderId, String state) {}

interface OrderService {
    OrderStatus findForTenant(String tenantId, String orderId);
}

final class OrderTools {
    private final OrderService orderService;

    OrderTools(OrderService orderService) {
        this.orderService = orderService;
    }

    @Tool(
        name = "get_order_status",
        description = "Đọc trạng thái một đơn hàng khi đã biết mã; không sửa dữ liệu"
    )
    public OrderStatus getStatus(
            @ToolParam(description = "Mã đơn hàng do người dùng cung cấp") String orderId,
            ToolContext context) {

        String tenantId = (String) context.getContext().get("tenantId");

        if (tenantId == null || tenantId.isBlank()) {
            throw new SecurityException("UNAUTHORIZED");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("INVALID_ORDER_ID");
        }

        // Service phải kiểm tra quyền đọc đối với chính orderId.
        return orderService.findForTenant(tenantId, orderId);
    }
}
```

`ToolContext` không được gửi tới model; ứng dụng điền `tenantId` từ request đã xác thực. Đây là ranh giới tin cậy của backend. **Không lấy tenant/role từ lời nhắc hoặc đối số model** và cũng không mặc nhiên coi `ToolContext` thay cho kiểm quyền trên tài nguyên ở service.

Tool ghi có thể được khai báo theo cấu trúc sau:

```java
final class OrderWriteTools {
    private final CancellationService service;

    OrderWriteTools(CancellationService service) {
        this.service = service;
    }

    @Tool(
        name = "cancel_order",
        description = "Yêu cầu hủy một đơn thuộc quyền người dùng",
        requiresConfirmation = true
    )
    public String cancel(
            @ToolParam(description = "Mã đơn cần hủy") String orderId,
            ToolContext context) {

        String tenantId = (String) context.getContext().get("tenantId");
        String operationId = (String) context.getContext().get("operationId");

        // Service phải kiểm role, tenant, ownership và idempotency.
        return service.cancelOnce(tenantId, orderId, operationId);
    }
}
```

`CancellationService` là interface nghiệp vụ giả định; yêu cầu xác nhận của framework **không thay thế** kiểm quyền và chống thực thi lặp. Nếu ứng dụng dùng lớp riêng để cấp `operationId`, hãy đảm bảo ID ràng buộc với **một hành động** cụ thể và không tái sử dụng nhầm giữa các lần gọi tool khác nhau.

### 3.2. Chuẩn hóa kết quả để so sánh

Không so sánh câu trả lời tự nhiên từng ký tự. Với lời gọi đọc, đối chiếu:

- Tool đã được gọi hay chưa; tên tool và đối số `orderId`.
- Counter của fake service và tenant được truyền qua.
- Trạng thái `DELIVERED` thật xuất hiện trong kết quả có căn cứ; không bịa dữ liệu của đơn khác.
- Không có tác dụng phụ và không gọi tool bị cấm.

Với lời gọi ghi, chuẩn hóa theo `operationId`, `orderId`, **số giao dịch thực tế** và trạng thái xác nhận. Lời nói “đã hủy” không chứng minh giao dịch đã thành công; phải đọc lại state của service.

## 4. Nhóm kiểm thử A — Hồi quy JSON Schema và công cụ được expose

### 4.1. Kiểm tra contract tĩnh không gọi model

`ToolCallback.getToolDefinition()` trả về `name()`, `description()` và `inputSchema()`. Kiểm tra chính các giá trị sau khi Spring AI sinh schema, không chỉ đọc annotation bằng reflection.

```java
@Test
void getOrderStatusSchemaIsStable() throws Exception {
    OrderService service = mock(OrderService.class);
    ToolCallback callback = ToolCallbacks.from(new OrderTools(service))[0];

    assertThat(callback.getToolDefinition().name())
        .isEqualTo("get_order_status");
    assertThat(callback.getToolDefinition().description())
        .contains("Đọc trạng thái");

    JsonNode schema = new ObjectMapper()
        .readTree(callback.getToolDefinition().inputSchema());

    assertThat(schema.path("type").asText()).isEqualTo("object");
    assertThat(schema.path("properties").path("orderId")
        .path("type").asText()).isEqualTo("string");

    boolean required = StreamSupport
        .stream(schema.path("required").spliterator(), false)
        .anyMatch(node -> "orderId".equals(node.asText()));
    assertThat(required).isTrue();
}
```

Đối với schema có cấu trúc phức tạp, hãy parse rồi **canonicalize** trước khi so sánh: sắp xếp khóa object, giữ nguyên thứ tự nơi có ngữ nghĩa như `enum`/`required` nếu chính sách yêu cầu, bỏ các field nhiễu không ảnh hưởng hợp đồng chỉ khi đã kiểm chứng. Snapshot toàn bộ chuỗi JSON sẽ gây lỗi giả khi chỉ thay thứ tự khóa.

`@ToolParam(required = false)` hoặc `@Nullable` khiến một tham số tùy chọn; tham số method mặc định là bắt buộc. Kiểm thử không chỉ dừng ở dấu `required`: callback vẫn phải **từ chối giá trị không hợp lệ** tại ứng dụng, vì JSON Schema gửi cho model không phải ranh giới bảo mật.

### 4.2. Bộ dữ liệu âm tính

| Input | Kỳ vọng |
|---|---|
| `{"orderId":"ORD-17"}` | Parse thành công và đọc tenant hợp lệ |
| `{}` | Không tự đoán mã; request được từ chối hoặc hỏi lại |
| `{"orderId":null}` | Validation từ chối nếu nghiệp vụ bắt buộc mã |
| `{"orderId":42}` | Không chấp nhận sai kiểu theo contract |
| `{"orderId":""}` | Validation nghiệp vụ từ chối mã trống |
| `{"orderId":"ORD-99"}` với tenant A | Service kiểm quyền và từ chối nếu đơn thuộc tenant B |
| `{"orderId":"ORD-17","tenantId":"tenant-B"}` | Không dùng `tenantId` do model tự gửi; phát hiện/loại trường dư theo policy |
| Chuỗi dài, ký tự điều khiển, JSON hỏng | Chặn theo giới hạn input, không ghi log payload nguyên vẹn |

Lưu ý: kết quả deserialization với kiểu sai hoặc field dư tùy Jackson/configuration, nên test phải nói rõ **validation layer được cấu hình**; không khẳng định Spring AI tự bảo đảm strict schema validation cho mọi provider.

### 4.3. Hồi quy catalog khi nâng cấp

Trong Spring AI 2.1:

- Với `ChatClient`, `defaultTools(…)` trên builder và `.tools(…)` theo request được **gộp**. Thêm tool theo request không tự loại tool mặc định.
- Với `ChatModel` sử dụng `ToolCallingChatOptions`, tool list trong request **thay thế** list ở default options của model khi cả hai được đặt.
- `ChatClient` kiểm tra trùng tên trong tập tool kết hợp; nếu ứng dụng dùng `ChatModel` trực tiếp hoặc loop riêng, cần tự kiểm tập danh sách.
- Resolver fallback để thực thi tool chỉ được biết qua bean nhưng không attach vào request được **tắt mặc định** trong bản 2.1; có thể cấu hình `spring.ai.tools.resolution.fallback.enabled=true`. Mở fallback làm tăng phạm vi công cụ có thể được thực thi, nên phải có test quyền riêng.

Tạo test chụp **effective tool catalog** cho từng role, xác nhận chỉ có tool dự kiến. Không đặt `cancel_order` vào `defaultTools` của mọi request và hy vọng model sẽ không chọn nó khi người dùng chỉ có quyền xem. Chỉ cấp tool đúng vai trò và vẫn kiểm quyền trong service.

## 5. Nhóm kiểm thử B — Lỗi, retry, giới hạn và tác dụng phụ

### 5.1. Định nghĩa lỗi có thể kiểm thử

| Sự cố được bơm | Kỳ vọng hệ thống | Retry? |
|---|---|---|
| Thiếu mã, sai kiểu, input vượt giới hạn | Lỗi validation an toàn hoặc xin bổ sung thông tin; không gọi backend | Không |
| 401/403 hoặc quyền sở hữu sai | Chặn callback/service, không tiết lộ sự tồn tại tài nguyên ngoài quyền | Không |
| 404 từ nghiệp vụ | Nói không có kết quả hợp lệ, không bịa trạng thái | Thường không |
| 429/503 từ API ngoài | Backoff/jitter, giới hạn số lần và thời gian | Có điều kiện |
| Timeout **trước** khi tool gửi lệnh ghi | Có thể thử lại theo policy khi biết chắc chưa ghi | Có điều kiện |
| Timeout **sau** khi lệnh ghi có thể đã chạy | Trạng thái `UNKNOWN`; tra cứu bằng idempotency key trước khi retry | Không retry mù |
| Tool trả kết quả khác schema mong đợi | Đánh dấu contract regression; không trình bày dữ kiện sai là đúng | Không tự động |
| Model yêu cầu gọi lặp vô hạn | Chặn khi chạm ngưỡng, ghi mã lỗi và stop reason | Không tiếp tục vô hạn |

Spring AI bao bọc exception lúc thực thi tool thành `ToolExecutionException` và chuyển đến `ToolExecutionExceptionProcessor`. Trong cấu hình mặc định 2.1, thông điệp của `RuntimeException` có thể được trả lại model; checked exception và `Error` được ném tiếp. Muốn mọi lỗi tool được đẩy cho caller xử lý, dùng:

```yaml
spring:
  ai:
    tools:
      throw-exception-on-error: true
```

Không biến thuộc tính này thành chính sách duy nhất: một số lỗi nghiệp vụ cần kết quả có mã an toàn cho model, còn lỗi quyền nhạy cảm phải bị xử lý tại ranh giới phù hợp. Test cả **đường trả lỗi cho model** và **đường ném ngoại lệ cho caller** theo cấu hình thực tế, bảo đảm thông điệp không chứa token, SQL, stack trace hoặc dữ liệu khách hàng.

### 5.2. Ví dụ test callback khi thiếu tenant

```java
@Test
void missingTrustedTenantNeverReachesService() {
    OrderService service = mock(OrderService.class);
    ToolCallback tool = ToolCallbacks.from(new OrderTools(service))[0];

    assertThatThrownBy(() -> tool.call(
        "{\"orderId\":\"ORD-17\"}",
        new ToolContext(Map.of())
    )).isInstanceOf(RuntimeException.class);

    verifyNoInteractions(service);
}
```

`MethodToolCallback` có thể bọc lỗi phương thức. Bài kiểm thử trên chỉ khẳng định **không có call service** và lỗi ở ranh giới callback; test tích hợp với manager và `ToolExecutionExceptionProcessor` mới xác nhận loại kết quả cuối được gửi cho model hay caller. Nếu ứng dụng tự chọn cách trả `DENIED` theo cấu trúc, assertion phải kiểm tra **mã lỗi chuẩn hóa**.

### 5.3. Hạn mức và điều kiện dừng

Spring AI 2.1 có các cấu hình tại `ToolCallingManager`:

```java
ToolCallingManager manager = ToolCallingManager.builder()
    .maxCallsPerTool(8)
    .maxTotalToolCalls(20)
    .onLimitExceeded(ToolCallLimitBehavior.THROW)
    .build();
```

`8` và `20` là hạn mức minh họa cho suite; trong tài liệu Spring AI 2.1, mặc định manager là **40 call/tool** và **150 call/turn**. Test cần kiểm tra các ca:

- Một tool được model gọi quá số lần cho phép.
- Tổng call vượt ngưỡng dù từng tool chưa vượt.
- Nhiều tool call trong cùng phản hồi, có tool đã chạy trước khi hạn mức bị vi phạm.
- Xử lý `ToolCallLimitExceededException`, finish reason và metadata của các kết quả một phần.
- Nếu chọn `RETURN_ERROR_RESPONSE` thay `THROW`, model nhận lỗi tổng hợp và có thể tiếp tục; ứng dụng vẫn cần ngân sách vòng/chi phí phía ngoài để không kéo dài vô hạn.

Hạn mức đếm trên **turn hiện tại**; test nhớ truyền đầy đủ lịch sử vòng khi dùng loop thủ công, vì manager tính lại từ `Prompt`. Các hạn mức này không thay cho timeout HTTP, số lần retry của SDK hay giới hạn tiền/giây của ứng dụng.

### 5.4. Chống thực thi lặp

Với `cancel_order`, giả lập API đã thực hiện hủy nhưng trả timeout. Test phải kiểm tra:

1. `operationId` được server sinh từ yêu cầu nghiệp vụ, không từ tool args do model tạo.
2. Reconcile theo `operationId` trước khi quyết định có gửi lại lệnh.
3. Nếu backend đã `SUCCEEDED`, gửi lại **kết quả** cho workflow mà không tạo giao dịch mới.
4. Nếu backend chưa thực thi và còn quyền, retry chỉ trong ngân sách, dùng cùng idempotency key.
5. Một callback lỗi không được làm xóa checkpoint hoặc biến `UNKNOWN` thành “thất bại chắc chắn”.

Không dùng số lần gọi model làm bằng chứng side effect chỉ xảy ra một lần; đo transaction/log tại **dịch vụ nghiệp vụ**.

## 6. Nhóm kiểm thử C — Streaming và lịch sử nhiều vòng

### 6.1. Khác biệt giữa nội dung đang stream và tool call có thể chạy

Với những model/endpoint hỗ trợ, Spring AI 2.1 đưa từng đoạn đối số tool qua `ToolCallPart` được đánh dấu partial. Mảnh này thường **chưa phải JSON hoàn chỉnh**; `AssistantMessage.getToolCalls()`/`hasToolCalls()` bỏ qua nó. `ToolCallingManager` chỉ thực thi tool call hoàn chỉnh.

Một UI có thể hiển thị “model đang chuẩn bị gọi công cụ” mà không biến tín hiệu hiển thị thành lệnh gọi backend. Sau đó model gửi complete tool call, `ToolCallingAdvisor` mới điều phối thực thi.

Ví dụ quan sát stream mà không tự thực thi các mảnh:

```java
chatClient.prompt()
    .user("Tra cứu đơn ORD-17")
    .tools(new OrderTools(orderService))
    .toolContext(Map.of("tenantId", "tenant-A"))
    .stream()
    .chatResponse()
    .subscribe(chunk -> {
        for (Generation generation : chunk.getResults()) {
            for (MessagePart part : generation.getOutput().getParts()) {
                if (part instanceof ToolCallPart toolPart
                        && StreamingParts.isPartial(part)) {
                    // Chỉ hiển thị tiến độ hoặc ghi event redacted.
                    // KHÔNG gọi ToolCallback ở đây.
                    showProgress(toolPart.toolCall().name());
                }
            }
        }
    });
```

Phương thức `showProgress` là callback UI do ứng dụng định nghĩa. Với test blocking/streaming, giả lập các fragment như `{"order` và `Id":"ORD-17"}` rồi xác nhận chưa có lệnh nghiệp vụ ở thời điểm chỉ nhận fragment. **Không yêu cầu mọi provider phải phát fragment**: có provider chỉ trả complete tool call. Điều cần bất biến là *không thực thi fragment* và *thực thi tool call hoàn chỉnh đúng theo chính sách*.

### 6.2. Các ca cần đưa vào stream suite

| Ca streaming | Kỳ vọng |
|---|---|
| Text chunk trước tool call | Giao diện vẫn stream đúng; không suy luận callback đã chạy |
| Nhiều mảnh args một call | Thứ tự mảnh được giữ nếu ứng dụng tự hiển thị; chỉ complete call được dispatch |
| Hai tool call trong một phản hồi | Ghép đúng ID/chỉ số và đối số; không lẫn kết quả |
| Provider chỉ phát complete call | Hoạt động hợp lệ dù không có progress delta |
| Ngắt SSE trước khi complete call | Không thực thi tool từ partial; dừng/đối soát workflow |
| Ngắt SSE sau khi tool đã thực thi | Không tự retry side effect do client kết nối lại |
| Blocking và streaming cùng fixture | Cùng quyền, input, dữ kiện và side effect; cách chia chunk có thể khác |
| Đang stream thì có confirmation | Metadata tạm dừng ở chunk cuối; caller phát hiện và lưu pause |
| Một turn có nhiều vòng tool | Lịch sử có các cặp tool call/tool result hợp lệ; không trùng khi replay |

Trong `ChatClient`, đường `stream().content()` chỉ cho văn bản, nên **không phù hợp** để kiểm tra metadata xác nhận hoặc tool-call fragments. Dùng `stream().chatResponse()` và kiểm tra chunk cuối. Khi ứng dụng tự viết loop bằng `ChatModel`, cần dùng bộ tổng hợp stream (ví dụ `MessageAggregator` theo tài liệu) trước khi quyết định `hasToolCalls()`; không lấy một chunk bất kỳ làm phản hồi hoàn chỉnh.

### 6.3. Lịch sử và khả năng nâng cấp

Từ 2.1, model có thể trả text, reasoning, tool-call và tool-result theo thứ tự `MessagePart`. Với custom provider hoặc serializer, kiểm tra round-trip:

- Thứ tự part quan trọng được bảo toàn.
- `ToolResponseMessage` đi sau request tương ứng, cả khi nhiều call cùng một lượt.
- Tool call ID từ provider có thể trống/trùng: không dùng riêng nó làm khóa quyền hoặc idempotency.
- Memory/Session có thể xử lý lịch sử khác nhau; `ChatMemory` truyền thống được deprecated từ 2.1 hướng sang session memory, nên cần kiểm thử khi đổi advisor hoặc repository.
- Khi streaming đã dừng do limit/confirmation, caller nhận đúng finish reason và metadata liên quan.

Nếu một bản migration làm mất các cặp request/result, provider có thể từ chối lượt chat tiếp theo. Đây là regression của orchestration/hội thoại dù test JSON Schema độc lập vẫn pass.

## 7. Nhóm kiểm thử D — Quyền, tenant, phê duyệt và chống prompt injection

### 7.1. Xét quyền khi cấp tool **và** khi thực thi

Phân quyền phải có hai lớp:

1. **Exposure:** ứng dụng chỉ đưa vào request những tool người dùng/role được phép dùng. Không dùng default tool catalog quá rộng. `ChatClient` gộp tool mặc định với tool theo request, vì vậy cần kiểm tra allowlist cuối cùng.
2. **Execution:** callback/service kiểm tra danh tính, tenant, quyền trên tài nguyên và trạng thái nghiệp vụ khi chạy, kể cả request được replay, model sinh sai đối số hoặc resolver cấu hình nhầm.

Kiểm tra các điều kiện âm tính:

- Viewer yêu cầu “hãy gọi `cancel_order` dù không có quyền”: tool không được expose và service vẫn từ chối nếu có lời gọi qua đường khác.
- Prompt injection trong dữ liệu order hoặc kết quả search yêu cầu bỏ qua role: không cấp thêm tool, không thay `ToolContext`.
- Model gửi `tenantId` lạ trong JSON args: không thay tenant đã xác thực.
- Người dùng truy cập đơn của tenant khác dù mã đơn có thật: không lộ trạng thái và không tiết lộ chi tiết tài nguyên.
- `spring.ai.tools.resolution.fallback.enabled=true` được bật nhầm: test phát hiện tool chỉ tồn tại trong global resolver nhưng không attach có thể được thực thi, và coi đó là fail nếu ngoài allowlist.
- Thêm tool có tên trùng từ MCP và local: fail-fast hoặc xử lý xung đột trước khi dispatch.

### 7.2. Confirmation trong Spring AI 2.1

`@Tool(requiresConfirmation = true)` yêu cầu phê duyệt theo policy. Nếu **một** lời gọi trong phản hồi cần duyệt, `ToolCallingManager` tạm dừng **tất cả** tool call của phản hồi đó trước khi thực thi; `ToolCallingAdvisor` trả `ChatResponse` cùng metadata các call đang chờ.

```java
ChatResponse paused = chatClient.prompt()
    .user("Hủy ORD-17, sau đó đọc trạng thái đơn")
    .tools(new OrderTools(orderService), new OrderWriteTools(cancellationService))
    .toolContext(trustedToolContext)
    .call()
    .chatResponse();

List<String> awaiting = ToolCallDecisions.awaitingDecision(paused);
if (!awaiting.isEmpty()) {
    // Lưu reply trong kho server và xác minh người có quyền phê duyệt.
    approvalStore.persist(paused, awaiting);
    // Chưa kết luận callback hủy đã chạy.
}
```

`trustedToolContext` và `approvalStore` là thành phần ứng dụng tự định nghĩa. Test phải ghi nhận: khi còn pending, số call dịch vụ **bằng 0 cho toàn bộ nhóm**, kể cả tool đọc trong cùng phản hồi; khi resume, toàn bộ call có quyết định allow/deny hợp lệ và chỉ những call được phép mới chạy. Ngoài ra:

- Đọc trạng thái qua `chatResponse()` hoặc `chatClientResponse()`; `content()` có thể rỗng khi pause.
- Với streaming, metadata chờ xác nhận ở **chunk cuối**; xem nội dung stream chưa đủ.
- Response chờ duyệt phải lấy từ kho server mà client không sửa được; xác minh lại approver và quyền tại thời điểm thực thi.
- Spring AI không tự chặn replay quyết định: ứng dụng lưu dấu đã xử lý và bảo vệ bằng idempotency key.
- Nếu người dùng chuyển sang turn khác mà không duyệt, hòa giải pause cũ để lịch sử model không chứa tool call thiếu tool result. Sau khi nhận turn mới, không resume pause cũ.
- Không để provider-supplied tool call ID trống/trùng trở thành khóa duy nhất; `ToolCallDecisions.toolCallKeys(…)` có thể dùng chỉ số như `#0`, `#1` khi cần.

### 7.3. Bằng chứng khi có sự cố quyền

Không đủ để thấy câu trả lời “Tôi không thể hủy”. Hãy khẳng định cùng lúc:

- Tool cấp cho model có đúng allowlist theo role.
- `CancellationService` ghi nhận **0 side effect** khi không có quyền/duyệt.
- Audit chứa mã từ chối, tenant và request ID ở kênh được bảo vệ, không ghi token hoặc nội dung khách hàng nguyên vẹn.
- Có test API direct/callback direct để chứng minh ranh giới quyền vẫn đúng nếu model bị bỏ qua.
- Có test replay/phê duyệt hết hạn/quyết định từ người dùng không được phép.

## 8. Ma trận hồi quy bắt buộc trước deploy

Mã và mức độ trong bảng là mẫu để điều chỉnh cho ứng dụng; `BLOCKER` nghĩa là release không được đi tiếp nếu ca thất bại.

| ID | Nhóm | Tình huống | Điều kiện PASS | Mức |
|---|---|---|---|---|
| RG-01 | Schema | Tên/mô tả/tool input JSON Schema sau nâng cấp | Khớp contract đã duyệt | BLOCKER |
| RG-02 | Schema | Required/optional, enum, kiểu dữ liệu | Đúng schema và validation nghiệp vụ | BLOCKER |
| RG-03 | Schema | Đối số sai kiểu/thiếu/ngoài giới hạn | Bị từ chối an toàn; không gọi service | BLOCKER |
| RG-04 | Catalog | Default tools + request tools | Effective catalog đúng allowlist | BLOCKER |
| RG-05 | Catalog | Local/MCP tool trùng tên | Phát hiện trước dispatch | BLOCKER |
| RG-06 | Lỗi | Tool ném RuntimeException có dữ liệu nhạy cảm | Không lộ nội dung nhạy cảm ra model/log công khai | BLOCKER |
| RG-07 | Lỗi | 401/403/404/429/503/timeout | Error mapping và retry theo chính sách | BLOCKER |
| RG-08 | Lỗi | Timeout sau tool ghi đã thành công | Đối soát, đúng một side effect | BLOCKER |
| RG-09 | Vòng gọi | Model liên tục yêu cầu cùng tool | Bị giới hạn, có stop reason | BLOCKER |
| RG-10 | Vòng gọi | Hai tool call, một call lỗi hoặc quá limit | Không mất kết quả một phần, không báo thành công giả | BLOCKER |
| RG-11 | Streaming | Partial args trước complete tool call | Không thực thi từ mảnh partial | BLOCKER |
| RG-12 | Streaming | Provider trả complete tool call, không có delta | Thực thi đúng, không phụ thuộc có fragment | BLOCKER |
| RG-13 | Streaming | Ngắt kết nối/reconnect sau callback | Không tạo tác dụng phụ lặp | BLOCKER |
| RG-14 | Streaming | Nhiều tool/round và replay lịch sử | Ghép đúng call/result, turn sau hợp lệ | BLOCKER |
| RG-15 | Quyền | Role chỉ đọc yêu cầu tool ghi | Tool không expose và callback/service từ chối | BLOCKER |
| RG-16 | Quyền | Mã đơn của tenant khác | Không rò rỉ và không đọc/ghi ngoài quyền | BLOCKER |
| RG-17 | Quyền | Prompt injection yêu cầu đổi tenant/role | Backend giữ tenant/role tin cậy | BLOCKER |
| RG-18 | Quyền | Pending confirmation và nhóm nhiều tool | Chưa call nào chạy trước quyết định | BLOCKER |
| RG-19 | Quyền | Resume trái phép, trùng hoặc quá hạn | Không thực hiện side effect | BLOCKER |
| RG-20 | Compatibility | `ChatClient` và `ChatModel` theo đường đang dùng | Loop/đầu ra phù hợp contract từng entry point | BLOCKER |
| RG-21 | Quality | Model candidate chọn tool đúng trên corpus | Đạt ngưỡng đã chốt với số lần lặp được ghi | GATE |
| RG-22 | Operation | Latency, số round-trip, token/chi phí, lỗi | Nằm trong ngân sách/SLO | GATE |

Nếu hệ thống không có tool ghi hoặc không dùng MCP, hãy ghi `NOT_APPLICABLE` kèm lý do cho những ca tương ứng; không biến thành `PASS`. Các bất biến phân quyền và side effect phải **100%** qua những ca áp dụng. Các ngưỡng chất lượng xác suất như tỷ lệ chọn tool nên được xác định từ yêu cầu nghiệp vụ, tập đại diện và rủi ro, không lấy con số bất kỳ làm chuẩn của Spring AI.

## 9. Tổ chức suite thành ba vòng để giảm nhiễu

### Vòng 1 — Contract offline, chạy trên mỗi PR

Chỉ cần Java test, JSON fixture, fake service, không cần gọi provider:

- Chụp/so sánh `ToolDefinition` và policy allowlist.
- Kiểm đối số âm tính và quyền callback/service.
- Giả lập timeout, 429, 403, idempotency/reconcile.
- Test vòng gọi dùng fake `ChatModel` hoặc fake response cho tool manager, kiểm hạn mức, kết quả nhiều call và stop reason.
- Test stream aggregator với chuỗi fragment giả có cả partial và complete; bảo đảm chỉ complete call được dispatch.
- Test session/approval lưu trên server và replay an toàn.

Vòng này ổn định, rẻ và là điều kiện tối thiểu để một PR có thể merge.

### Vòng 2 — Tích hợp với provider/model thật, chạy trước release

Khóa model ID, endpoint và options. Chạy cùng corpus trên baseline và candidate (ít nhất có ca tiếng Việt, yêu cầu thiếu thông tin, nhiều tool, input gần giống nhau và prompt injection). Đo **hành vi thực tế** qua fake service với counter và event log; phân biệt model không gọi tool, gọi sai tên, sinh args sai, loop lỗi và tạo đáp án không có căn cứ.

Ví dụ cấu trúc một integration test (mã minh họa):

```java
@Test
void realCandidateUsesOrderToolWithTrustedTenant() {
    OrderService service = mock(OrderService.class);
    when(service.findForTenant("tenant-A", "ORD-17"))
        .thenReturn(new OrderStatus("ORD-17", "DELIVERED"));

    ChatClient client = ChatClient.create(candidateChatModel);

    String answer = client.prompt()
        .user("Tra cứu trạng thái đơn ORD-17.")
        .tools(new OrderTools(service))
        .toolContext(Map.of("tenantId", "tenant-A"))
        .call()
        .content();

    verify(service, times(1)).findForTenant("tenant-A", "ORD-17");
    assertThat(answer).isNotBlank();

    // Kiểm dữ kiện DELIVERED bằng evaluator/structured output riêng,
    // không so khớp từng từ trong câu tự nhiên.
}
```

`candidateChatModel` được tạo bằng cấu hình test thật. Một lần pass chưa đủ cho model có tính xác suất; chạy lặp trên tập cố định, báo số lần chạy và tỷ lệ, đồng thời giữ chính xác **0 vi phạm** quyền/side effect. Không đánh giá độ an toàn chỉ qua lời hứa từ model.

### Vòng 3 — Staging/canary theo hành vi vận hành

Sau vòng 1–2:

1. Deploy ở staging với tracing an toàn, giới hạn tốc độ và dịch vụ nghiệp vụ giả.
2. Diễn tập timeout sau side effect, ngắt SSE, resume confirmation, credential expired, rollback cấu hình và cleanup dữ liệu thử.
3. Canary một phần lưu lượng thực theo feature flag nếu chính sách cho phép; đo lỗi schema, phân quyền, tỷ lệ thực thi tool, loop limit và độ trễ.
4. Có **kill switch** cho tool ghi, lựa chọn rollback Spring AI/model/provider và trạng thái hội thoại tương thích.
5. Không mở rộng rollout khi có regression mới ở các ca BLOCKER, dù latency hoặc chất lượng câu trả lời cải thiện.

Chỉ chạy test bên ngoài môi trường production với dữ liệu mô phỏng khi có khả năng tác động dữ liệu thật; canary phải hạn chế mức độ rủi ro và tuân theo quy trình vận hành đã được phê duyệt.

## 10. Đọc kết quả và ra quyết định phát hành

Một bản báo cáo tốt tách **cái model yêu cầu** khỏi **cái ứng dụng thực thi**.

```json
{
  "suite": "tool-calling-contract-v3",
  "variant": "candidate",
  "springAi": "2.1.0",
  "caseId": "RG-16",
  "modelId": "pinned-model-version",
  "mode": "streaming",
  "expectedTools": ["get_order_status"],
  "actualTools": ["get_order_status"],
  "normalizedArgs": {"orderId": "ORD-99"},
  "trustedTenant": "tenant-A",
  "serviceCalls": 1,
  "unauthorizedReads": 0,
  "unauthorizedWrites": 0,
  "decision": "PASS"
}
```

JSON trên **chỉ là ví dụ định dạng báo cáo**, không phải một test đã chạy. Với trường hợp tenant khác, service có thể được gọi một lần để kiểm tra quyền rồi trả từ chối; cần kiểm thêm **không có dữ liệu của tenant B được trả ra**. Nên gắn trace ID, response finish reason, số lần retry, latency và chi phí trong kho kết quả kiểm thử đã bảo vệ. Không đưa tenant hoặc order ID chi tiết vào metric label có cardinality lớn.

| Trạng thái | Cách hiểu | Quyết định |
|---|---|---|
| `PASS` | Bất biến được kiểm và đạt | Có thể tiếp tục cổng sau |
| `FAIL` | Hành vi khác expected, tái hiện được | Chặn release nếu thuộc BLOCKER |
| `UNSUPPORTED` | Model/provider không hỗ trợ khả năng bắt buộc | Chặn hoặc thay thiết kế được phê duyệt |
| `FLAKY` | Kết quả phụ thuộc thời điểm/xác suất, chưa đủ bằng chứng | Chạy lại có kiểm soát, điều tra |
| `NOT_APPLICABLE` | Không có chức năng tương ứng trong hệ thống | Ghi lý do, không tính như PASS |
| `NOT_RUN` | Thiếu môi trường/credential hoặc test chưa chạy | Không tuyên bố đã kiểm chứng |

Đặt tiêu chí release trước khi nhìn kết quả; không sửa ngưỡng sau khi candidate fail nếu không có căn cứ thay đổi yêu cầu. Ngoài tỷ lệ pass, cần đọc cụ thể call sequence, output schema, lỗi cuối, side effect và dấu hiệu retry ẩn.

### Ví dụ quyết định

- **Có thể triển khai:** tất cả BLOCKER pass; suite tích hợp đáp ứng ngưỡng đã chốt; các chức năng streaming/confirmation áp dụng đã được kiểm thử; quan sát staging phù hợp SLO; rollback sẵn sàng.
- **Chưa triển khai:** xảy ra bất kỳ truy cập sai tenant, tool ghi chạy khi thiếu phê duyệt, data leak qua runtime exception, callback thực thi từ partial stream, hoặc side effect lặp.
- **Cần đánh giá thêm:** model chọn tool không ổn định, provider thiếu progress delta nhưng vẫn có complete call, hoặc một ca test phụ thuộc hạ tầng chưa có kết quả. Không tự xếp nhóm này thành PASS.

## 11. Các lỗi tư duy thường gặp

1. **“Schema của `@Tool` đúng nên input luôn hợp lệ.”** Schema là phần giao tiếp với model; validation giá trị, tenant và quyền vẫn phải được thực thi ở backend.
2. **“Một API `ChatModel` chung đảm bảo mọi provider giống nhau.”** Có sự khác biệt khả năng tool calling, parallel call, streaming, JSON schema và stop reason; phải kiểm model ID/endpoint thật.
3. **“`content()` có chuỗi là workflow đã xong.”** Lời gọi chờ xác nhận hoặc lỗi hạn mức có thể cần đọc `ChatResponse`/metadata.
4. **“Đối số partial trong stream là một tool call.”** Chỉ complete call mới có thể được thực thi.
5. **“Nếu model không nhìn thấy tool ghi thì không thể ghi sai.”** Phải kiểm quyền ở callback/service, kiểm resolver fallback và bảo vệ đường gọi khác.
6. **“Retry sau timeout chắc chắn an toàn.”** Tool có side effect có thể đã thành công; phải đối soát theo operation ID.
7. **“Test mock model pass nghĩa là có thể đổi provider.”** Mock chứng minh cơ chế nội bộ; provider thật quyết định tool nào được gọi.
8. **“Có thể nâng version rồi kiểm ở production.”** Các bất biến quyền, schema và streaming cần được chặn ở PR/staging, rồi mới canary theo chính sách.

## 12. Câu hỏi thực hành

1. Nếu sau upgrade `inputSchema()` biến `orderId` từ required thành optional, bạn sẽ viết assertion nào và giải thích rủi ro ra sao?
2. Bản mới làm `RuntimeException` của tool chứa email xuất hiện trong final answer. Điểm kiểm thử nào phát hiện và lớp nào nên sửa?
3. Vì sao test streaming phải có ca fragment JSON chưa đầy đủ và ca provider chỉ gửi complete call?
4. Khi `ORDER_VIEWER` không thấy `cancel_order` trong tool catalog nhưng service vẫn cho gọi qua API riêng, release có đạt yêu cầu phân quyền không?
5. Một response có cả `get_order_status` và `cancel_order`, trong đó `cancel_order` cần confirmation. Trước khi người dùng quyết định, expected service call count là bao nhiêu?
6. Bạn sẽ chứng minh tác dụng phụ chỉ xảy ra một lần khi timeout xuất hiện ngay sau lệnh ghi bằng công cụ nào?
7. Nếu từ 1.x chuyển sang 2.1, điểm khác biệt nào giữa `ChatModel` và `ChatClient` phải nằm trong regression suite?
8. Trước khi bật canary, bạn sẽ yêu cầu những trường nào trong báo cáo và bằng chứng nào giúp rollback nhanh?

## Tài liệu tham khảo

- [Spring AI 2.1 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): khai báo `@Tool`/`ToolCallback`, JSON Schema, `ToolContext`, exception policy, tool limits và streaming.
- [Spring AI 2.1 — ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html): vòng gọi thủ công, khác biệt default/request options và `ToolCallingManager`.
- [Spring AI 2.1 — Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html): metadata pause, quyết định, an toàn khi resume và streaming.
- [Spring AI 2.1 — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html): vòng điều phối tự động, return-direct, streaming, registration.
- [Spring AI — Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): `MessagePart` 2.1, thay đổi `ChatModel`/advisor từ 1.x sang 2.0, resolver fallback.

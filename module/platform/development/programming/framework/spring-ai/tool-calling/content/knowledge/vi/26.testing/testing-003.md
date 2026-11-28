# Kiểm thử ToolCallback và ToolContext trực tiếp

Khi phát triển tool calling bằng Spring AI, không nên bắt đầu mọi ca kiểm thử bằng một ChatClient kết nối đến mô hình thật. Nếu mục tiêu là xác minh công cụ được tạo đúng schema, parse arguments đúng, chuyển kết quả thành String, nhận tenant/actor từ ToolContext và gọi đúng service nghiệp vụ, ta có thể kiểm thử trực tiếp ToolCallback ngay trong JVM.

Trong Spring AI 2.1.0, ToolCallbacks.from(...) chuyển object chứa phương thức @Tool thành các ToolCallback. Mỗi callback có getToolDefinition(), getToolMetadata() và hai phương thức call(String) / call(String, ToolContext). Bởi vậy, một unit test có thể chủ động đưa JSON arguments vào callback, tự tạo ToolContext, chặn service bằng Mockito và kiểm tra response String bằng Jackson. Không cần API key, model provider, prompt hay vòng lặp advisor.

Điểm cần phân biệt: **test trực tiếp chứng minh callback hoạt động đúng với input đã cho, không chứng minh mô hình sẽ chọn đúng callback đó**. Mô hình, ToolCallingAdvisor, ToolCallingManager và cơ chế gọi nhiều lượt là những ranh giới kiểm thử khác.

## Mục tiêu và phạm vi của bài

Sau bài học, bạn cần tự viết được những nhóm test:

- Kiểm tra ToolDefinition: tên, description, JSON input schema, field required/optional.
- Gọi ToolCallback.call(json, context) và kiểm tra tham số thực sự đến service.
- Xác minh ToolContext được truyền riêng, không xuất hiện trong model-generated arguments.
- Kiểm tra output serialization, kết quả nghiệp vụ và không lộ metadata nhạy cảm.
- Kiểm thử thiếu context, sai tenant, không đủ quyền, arguments thiếu/sai kiểu và exception.
- Tách lỗi bên trong callback khỏi cách ToolCallingManager xử lý lỗi cho mô hình.
- Kiểm thử callback tạo thủ công hoặc FunctionToolCallback khi cần.
- Giữ test nhanh, xác định được nguyên nhân thất bại và không gây side effect thật.

Bài dùng JUnit Jupiter 5, AssertJ, Mockito và Jackson với các API Spring AI 2.1.0. Các đoạn ví dụ là mẫu test kiến trúc; khi đưa vào dự án hãy điều chỉnh package, dependency và kiểu dữ liệu theo code thực tế.

## Phân tách các tầng kiểm thử

~~~mermaid
flowchart TD
    A[Golden JSON arguments] --> B[ToolCallback.call]
    C[ToolContext của test] --> B
    B --> D[Parse và bind vào tham số Java]
    D --> E[Method @Tool hoặc Function callback]
    E --> F[Mockito fake / application service]
    F --> G[DTO kết quả]
    G --> H[ToolCallResultConverter]
    H --> I[String tool result]
    I --> J[AssertJ và Jackson assertions]
    K[ToolDefinition và ToolMetadata] --> L[Contract assertions]
~~~

| Loại test | Đối tượng thực sự được chạy | Điều chứng minh |
|---|---|---|
| Unit test của service | Java service và dependency fake | Quy tắc nghiệp vụ, validation, authorization, mapping |
| Direct ToolCallback test | Callback thật + method/functional tool + mocked service | JSON binding, ToolContext, converter, schema và lỗi callback |
| ToolCallingManager test | Manager + callbacks + ChatResponse có tool calls | Dispatch theo tên, tool response messages, processor lỗi và returnDirect |
| ChatClient/Advisor integration test | Advisor loop và fake/stub ChatModel | Tool được điều phối qua nhiều vòng, history và final answer |
| Provider contract/e2e test | Model/provider thật cùng dịch vụ sandbox | Model có chọn công cụ, tạo arguments, trả lời cuối đáng tin không |

Đây là kim tự tháp kiểm thử: direct callback test chạy nhiều nhất vì nhanh và ổn định; integration/e2e test ít hơn để kiểm tra những ranh giới không nằm trong callback.

## API tối thiểu cần nắm

~~~java
public interface ToolCallback {
    ToolDefinition getToolDefinition();

    ToolMetadata getToolMetadata();

    String call(String toolInput);

    String call(String toolInput, ToolContext toolContext);
}
~~~

ToolDefinition là hợp đồng mô hình nhìn thấy: tên, mô tả và inputSchema (JSON Schema được biểu diễn thành String). ToolMetadata chứa các cờ điều phối như returnDirect và yêu cầu confirmation. call(String, ToolContext) thực thi callback bằng JSON input cùng context nội bộ.

Tạo callback từ object có @Tool:

~~~java
ToolCallback[] callbacks = ToolCallbacks.from(orderTools);
ToolCallback callback = callbacks[0];

String result = callback.call(
        "{\"orderId\":\"ORD-100\"}",
        new ToolContext(Map.of(
                "tenantId", "tenant-a",
                "actorId", "user-7"
        ))
);
~~~

ToolContext thuộc package org.springframework.ai.chat.model. Constructor nhận Map<String, Object> và cung cấp getContext() như một view không cho sửa. Điều này không biến các object mutable nằm trong map thành immutable; hãy dùng giá trị đơn giản, immutable trong test và production.

**Không gọi ChatModel.call() trong direct callback test.** Với Spring AI 2.x, ChatModel trực tiếp chỉ sinh tool call request; nó không tự thực thi callback. ChatClient với ToolCallingAdvisor mới quản lý vòng lặp model/tool. Direct test bỏ qua cả hai và kiểm tra đúng callback contract.

## Chuẩn bị fixture nghiệp vụ có phân quyền

Xét use case tra cứu trạng thái đơn hàng. Mô hình chỉ cung cấp orderId; tenant và actor phải đến từ ứng dụng qua ToolContext.

~~~java
public record OrderSnapshot(
        String orderId,
        String status,
        String trackingCode) {
}

public interface OrderQueryService {
    OrderSnapshot findAuthorized(
            String orderId,
            String tenantId,
            String actorId);
}

public final class OrderTools {

    private final OrderQueryService orderQueryService;

    public OrderTools(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Tool(description = "Đọc trạng thái đơn hàng theo mã đơn, không cập nhật dữ liệu")
    public OrderSnapshot getOrderStatus(
            @ToolParam(description = "Mã đơn hàng") String orderId,
            ToolContext toolContext) {

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Thiếu mã đơn hàng");
        }

        if (toolContext == null) {
            throw new IllegalArgumentException("Thiếu tool context");
        }

        Object tenantId = toolContext.getContext().get("tenantId");
        Object actorId = toolContext.getContext().get("actorId");
        if (!(tenantId instanceof String tenant) || tenant.isBlank()
                || !(actorId instanceof String actor) || actor.isBlank()) {
            throw new IllegalArgumentException("Thiếu danh tính đáng tin cậy");
        }

        return orderQueryService.findAuthorized(orderId, tenant, actor);
    }
}
~~~

Các public top-level types trong ví dụ nên tách ra những file Java tương ứng; test class ở những đoạn dưới được đặt trong một file test riêng. Tool method gọi service thay vì tự truy vấn database. findAuthorized là nơi kiểm tra đối tượng thật có thuộc tenant và actor được phép đọc đơn hay không; kiểm tra context có giá trị chỉ là bước đầu, chưa thay thế authorization.

Từ góc nhìn của mô hình, JSON arguments chỉ nên có:

~~~json
{"orderId":"ORD-100"}
~~~

Không thêm tenantId, actorId, traceId vào JSON input do model tạo. Những giá trị đó là dữ liệu điều phối tin cậy do server cung cấp.

## Test 1: tạo callback và gọi trực tiếp với context

Một test JUnit Jupiter sử dụng Mockito để kiểm tra toàn bộ đường từ JSON input đến lời gọi service:

~~~java
class OrderToolCallbackTest {

    private final ObjectMapper mapper = new ObjectMapper();

    private OrderQueryService orderQueryService;
    private ToolCallback callback;

    @BeforeEach
    void setUp() {
        orderQueryService = Mockito.mock(OrderQueryService.class);
        OrderTools tools = new OrderTools(orderQueryService);
        callback = ToolCallbacks.from(tools)[0];
    }

    @Test
    void executesToolWithTrustedContext() throws Exception {
        when(orderQueryService.findAuthorized(
                "ORD-100", "tenant-a", "user-7"))
                .thenReturn(new OrderSnapshot(
                        "ORD-100", "SHIPPING", "TRK-91"));

        ToolContext context = new ToolContext(Map.of(
                "tenantId", "tenant-a",
                "actorId", "user-7"
        ));

        String json = callback.call(
                "{\"orderId\":\"ORD-100\"}",
                context
        );

        JsonNode result = mapper.readTree(json);
        assertThat(result.path("orderId").asText()).isEqualTo("ORD-100");
        assertThat(result.path("status").asText()).isEqualTo("SHIPPING");
        assertThat(result.path("trackingCode").asText()).isEqualTo("TRK-91");

        verify(orderQueryService).findAuthorized(
                "ORD-100", "tenant-a", "user-7");
        verifyNoMoreInteractions(orderQueryService);
    }
}
~~~

Trong file test, cần các static import thông thường: org.assertj.core.api.Assertions.assertThat, org.mockito.Mockito.*, và các annotation org.junit.jupiter.api.BeforeEach / Test. ObjectMapper / JsonNode thuộc com.fasterxml.jackson.databind. Những test tiếp theo là các method bổ sung vào cùng test class ở trên.

Test này chứng minh:

1. Factory đọc được annotation @Tool và tạo callback.
2. Callback parse orderId từ JSON.
3. ToolContext truyền tenant/actor tới phương thức Java.
4. Service được gọi với chính xác ba tham số mong muốn.
5. Record kết quả được converter mặc định serialize thành JSON parse được.
6. Không có lời gọi service dư thừa.

Kết quả tool là String do callback converter tạo; không cần dùng ChatClient.entity() hoặc nhờ mô hình parse lại mới kiểm tra được. Dùng ObjectMapper.readTree tránh phụ thuộc vào thứ tự field trong JSON.

## Test 2: kiểm tra ToolDefinition và input schema

Test trực tiếp không chỉ gọi method; nó còn xác minh model được quảng bá công cụ nào và schema đầu vào có đúng không:

~~~java
@Test
void advertisesOnlyModelSuppliedArguments() throws Exception {
    ToolDefinition definition = callback.getToolDefinition();

    assertThat(definition.name()).isEqualTo("getOrderStatus");
    assertThat(definition.description())
            .contains("trạng thái đơn hàng");

    JsonNode schema = mapper.readTree(definition.inputSchema());

    assertThat(schema.path("type").asText()).isEqualTo("object");
    assertThat(schema.path("properties").has("orderId")).isTrue();
    assertThat(schema.path("required").toString()).contains("orderId");

    assertThat(schema.path("properties").has("tenantId")).isFalse();
    assertThat(schema.path("properties").has("actorId")).isFalse();
    assertThat(schema.path("properties").has("toolContext")).isFalse();
}
~~~

Trong test production, nên so sánh schema bằng cây JSON hoặc schema snapshot đã chuẩn hóa thay vì so sánh String chứa whitespace/thứ tự properties. Khi sửa tên tool, mô tả, kiểu tham số, @ToolParam(required = false) hoặc annotation schema khác, test phải cảnh báo để tránh breaking change im lặng.

Một schema đúng hỗ trợ model tạo arguments, nhưng **không tự chứng minh service đã validate business rules**. Các trường hợp như mã đơn không tồn tại hoặc không thuộc tenant vẫn cần test ở service/callback.

### Assert metadata điều phối riêng

~~~java
@Test
void keepsFrameworkMetadataExplicit() {
    ToolMetadata metadata = callback.getToolMetadata();
    assertThat(metadata).isNotNull();
    assertThat(metadata.returnDirect()).isFalse();
}
~~~

Nếu tool được gắn @Tool(returnDirect = true), hãy kiểm tra cờ đó khi cần. Tuy nhiên, callback.call(...) trực tiếp chỉ trả về String; nó không tự tạo vòng model để minh họa returnDirect. Hành vi bỏ qua model call tiếp theo cần kiểm thử ở ToolCallingManager/Advisor.

## Test 3: thiếu ToolContext phải bị từ chối

Không được để tool mặc định đọc tenant toàn hệ thống hoặc tự chọn tenant đầu tiên nếu context bị thiếu. Fixture đã kiểm tra lỗi trước khi chạm repository.

~~~java
@Test
void rejectsMissingContextBeforeCallingService() {
    assertThatThrownBy(() -> callback.call(
            "{\"orderId\":\"ORD-100\"}",
            new ToolContext(Map.of())
    ))
            .isInstanceOf(ToolExecutionException.class)
            .hasCauseInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(orderQueryService);
}
~~~

Đối với MethodToolCallback dựa trên method Java, exception được method ném ra thường được bọc vào ToolExecutionException (cause giữ lỗi gốc). Đây là hành vi ở callback boundary; **test trực tiếp không cần ToolExecutionExceptionProcessor**.

Khi dùng callback.call(String) cho một phương thức yêu cầu ToolContext, code cũng phải thất bại có kiểm soát. Nếu tự triển khai ToolCallback, chú ý overload nhận ToolContext là default method ở interface và có thể chỉ chuyển sang overload không có context; phải override rõ khi cần xử lý context.

### Context được truyền nhưng thiếu một trường bắt buộc

~~~java
@Test
void rejectsContextWithoutActor() {
    ToolContext context = new ToolContext(
            Map.of("tenantId", "tenant-a")
    );

    assertThatThrownBy(() -> callback.call(
            "{\"orderId\":\"ORD-100\"}",
            context
    ))
            .isInstanceOf(ToolExecutionException.class)
            .hasCauseInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(orderQueryService);
}
~~~

Kiểm tra cả trường rỗng, sai kiểu hoặc null tùy policy. Không đặt default tenant/actor đáng tin cậy trong object ToolCallback dùng chung giữa mọi request.

## Test 4: xác thực tenant và quyền tại service

Một người dùng có thể biết mã đơn của tenant khác. Test cần chứng minh callback không biến mã đơn đó thành quyền đọc dữ liệu.

~~~java
@Test
void rejectsCrossTenantAccess() {
    when(orderQueryService.findAuthorized(
            "ORD-OTHER", "tenant-a", "user-7"))
            .thenThrow(new SecurityException("Không có quyền đọc đơn"));

    ToolContext context = new ToolContext(Map.of(
            "tenantId", "tenant-a",
            "actorId", "user-7"
    ));

    assertThatThrownBy(() -> callback.call(
            "{\"orderId\":\"ORD-OTHER\"}", context))
            .isInstanceOf(ToolExecutionException.class)
            .hasCauseInstanceOf(SecurityException.class);

    verify(orderQueryService).findAuthorized(
            "ORD-OTHER", "tenant-a", "user-7");
}
~~~

Test ở đây xác minh **callback truyền đúng identity và lan truyền lỗi quyền**. Vì service đang mock, nó không chứng minh query thật đã lọc tenant_id đúng. Phải có thêm integration test riêng cho implementation của OrderQueryService với dữ liệu thuộc hai tenant.

Không trả stack trace, nội dung query SQL hoặc thông tin đơn của tenant khác trong tool result. Nếu ứng dụng muốn model có thông báo lỗi an toàn, xử lý thông điệp sau khi policy đã chặn; không để callback tự che một lỗi quyền thành kết quả thành công.

## Test 5: ngữ cảnh của hai lần gọi không bị trộn

Một ToolCallback có thể được dùng trong nhiều request khác nhau. Nó không nên giữ tenantId hoặc actorId dưới dạng mutable field cập nhật sau mỗi request, vì đó là nguồn lỗi rò rỉ cross-tenant khi có concurrency.

~~~java
@Test
void usesContextOfEachInvocationIndependently() {
    when(orderQueryService.findAuthorized(
            "ORD-A", "tenant-a", "user-a"))
            .thenReturn(new OrderSnapshot(
                    "ORD-A", "PENDING", "TRK-A"));

    when(orderQueryService.findAuthorized(
            "ORD-B", "tenant-b", "user-b"))
            .thenReturn(new OrderSnapshot(
                    "ORD-B", "SHIPPING", "TRK-B"));

    String first = callback.call(
            "{\"orderId\":\"ORD-A\"}",
            new ToolContext(Map.of(
                    "tenantId", "tenant-a",
                    "actorId", "user-a"))
    );

    String second = callback.call(
            "{\"orderId\":\"ORD-B\"}",
            new ToolContext(Map.of(
                    "tenantId", "tenant-b",
                    "actorId", "user-b"))
    );

    assertThat(first).contains("ORD-A");
    assertThat(second).contains("ORD-B");
    verify(orderQueryService).findAuthorized(
            "ORD-A", "tenant-a", "user-a");
    verify(orderQueryService).findAuthorized(
            "ORD-B", "tenant-b", "user-b");
}
~~~

Test tuần tự này bắt được lỗi callback lưu một context cố định từ lần đầu. Nó chưa đủ để chứng minh thread safety. Với component giữ state hoặc service dùng chung, thêm test đồng thời bằng ExecutorService với barrier để buộc hai call chồng thời gian, rồi kiểm tra từng operation không bị lẫn tenant/actor.

### ToolContext bảo vệ map khỏi thao tác ghi

~~~java
@Test
void exposesReadOnlyContextMap() {
    ToolContext context = new ToolContext(Map.of(
            "tenantId", "tenant-a"
    ));

    assertThatThrownBy(() ->
            context.getContext().put("tenantId", "tenant-b"))
            .isInstanceOf(UnsupportedOperationException.class);

    assertThat(context.getContext().get("tenantId"))
            .isEqualTo("tenant-a");
}
~~~

Đây là kiểm thử tính bất biến của map view, không phải một test authorization. Việc truyền tenant-a từ test vẫn cần được service tin tưởng vì test tạo nó theo chủ đích; trong production, identity phải đến từ principal/session đã được xác thực ở server.

## Test 6: arguments không hợp lệ và ranh giới JSON Schema

Một test cần phân biệt hai nhóm lỗi:

1. **Sai định dạng/kiểu dữ liệu:** JSON sai cú pháp, enum không có giá trị, số không parse được, field không tương thích với Java type.
2. **Sai nghiệp vụ:** orderId rỗng, order không thuộc tenant, trạng thái không cho phép, quota vượt giới hạn.

Không suy ra input schema là cơ chế bảo vệ quyền hoặc xác thực mọi invariant nghiệp vụ. JSON Schema được gửi cho mô hình để hướng dẫn arguments; cách callback phản ứng với JSON cụ thể phụ thuộc converter, phiên bản Spring AI và kiểu phương thức.

| Input thử nghiệm | Kỳ vọng của bài test |
|---|---|
| JSON đúng, có orderId | Service được gọi với orderId đúng. |
| JSON malformed | Callback báo lỗi, không được thực thi side effect. |
| Thiếu orderId | Không chấp nhận thao tác ghi; nếu framework bind null, service phải từ chối. |
| orderId là object/array thay vì string | Ghi nhận rõ lỗi parse/bind hoặc validation theo kiểu đầu vào. |
| orderId là chuỗi rỗng | Service phải kiểm tra quy tắc nghiệp vụ. |
| Có field tenantId trong JSON nhưng ToolContext tenant khác | Không dùng field do mô hình cung cấp để quyết định quyền. |
| Enum không hợp lệ | Có lỗi rõ, không âm thầm chọn giá trị mặc định nguy hiểm. |
| Kích thước input rất lớn | Validation giới hạn độ dài/truy cập tài nguyên bảo vệ callback/service. |

### Thử JSON malformed

~~~java
@Test
void doesNotCallBusinessServiceForMalformedJson() {
    assertThatThrownBy(() -> callback.call(
            "{\"orderId\":",
            new ToolContext(Map.of(
                    "tenantId", "tenant-a",
                    "actorId", "user-7"))
    )).isInstanceOf(RuntimeException.class);

    verifyNoInteractions(orderQueryService);
}
~~~

Không nên cố định mọi lỗi parse thành ToolExecutionException trong test khi chưa kiểm tra implementation và phiên bản cụ thể. Một số lỗi argument có thể bị ném dưới dạng runtime exception khác trước khi logic tool chạy. Kết luận quan trọng ở đây là input không hợp lệ không được tạo side effect, không phải một thông điệp lỗi mặc định luôn có chữ cố định.

### Thử arguments có trường mạo danh tenant

~~~java
@Test
void ignoresModelSuppliedTenantForAuthorization() {
    when(orderQueryService.findAuthorized(
            "ORD-100", "tenant-a", "user-7"))
            .thenReturn(new OrderSnapshot(
                    "ORD-100", "SHIPPING", "TRK-91"));

    callback.call(
            """
            {
              "orderId": "ORD-100",
              "tenantId": "tenant-evil",
              "actorId": "admin"
            }
            """,
            new ToolContext(Map.of(
                    "tenantId", "tenant-a",
                    "actorId", "user-7"))
    );

    verify(orderQueryService).findAuthorized(
            "ORD-100", "tenant-a", "user-7");
}
~~~

Test này chỉ có giá trị nếu callback hiện tại chấp nhận extra JSON fields; một số cấu hình có thể từ chối input ngay vì unknown fields. Khi đó, hành vi fail closed cũng an toàn: test nên chấp nhận lỗi được kiểm soát và xác minh service không chạy, thay vì ép parser phải bỏ qua mọi trường thừa.

**Không để assertions về cách parser xử lý field thừa trở thành yêu cầu bảo mật.** Dù framework có bỏ qua field thừa, application service chỉ tin ToolContext đã xác thực; nếu framework từ chối, callback cũng không tạo side effect.

## Cần test riêng trường hợp thiếu tham số kiểu primitive

Với những method có tham số optional kiểu primitive như int, long, boolean, việc mô hình bỏ qua field có thể dẫn đến phản ứng khác nhau giữa các phiên bản Spring AI. Nếu argument bị bind thành null rồi reflection cố truyền vào primitive, lỗi có thể xuất hiện trước khi code tool được gọi.

Ưu tiên các wrapper type Integer, Long, Boolean cho field có thể vắng mặt, kèm validation rõ ràng. Có thể thêm test:

~~~java
@Test
void rejectsMissingRequiredArgumentsBeforeAnyWrite() {
    assertThatThrownBy(() -> callback.call(
            "{}",
            new ToolContext(Map.of(
                    "tenantId", "tenant-a",
                    "actorId", "user-7"))
    )).isInstanceOf(RuntimeException.class);

    verifyNoInteractions(orderQueryService);
}
~~~

**Lưu ý về fixture:** Nếu method demo dùng String và không chủ động validate orderId, JSON thiếu field có thể được bind thành null rồi truyền vào mock, khiến test trên thất bại. Fixture đầu bài đã chủ động có validation này:

~~~java
if (orderId == null || orderId.isBlank()) {
    throw new IllegalArgumentException("Thiếu mã đơn hàng");
}
~~~

Validation phải chạy trước findAuthorized. Test trực tiếp giúp lộ lỗ hổng validation thay vì coi schema mô hình là đủ.

## Test 7: FunctionToolCallback với input DTO và context

Không phải công cụ nào cũng khai báo bằng @Tool. Spring AI cũng hỗ trợ FunctionToolCallback cho Function, Supplier, Consumer và BiFunction. Với công cụ cần ToolContext, BiFunction giúp nhận cả input DTO và context:

~~~java
public record OrderLookupRequest(String orderId) {
}

BiFunction<OrderLookupRequest, ToolContext, OrderSnapshot> action =
        (request, context) -> {
            String tenantId =
                    (String) context.getContext().get("tenantId");
            String actorId =
                    (String) context.getContext().get("actorId");
            if (tenantId == null || actorId == null) {
                throw new IllegalArgumentException("Thiếu danh tính");
            }
            return orderQueryService.findAuthorized(
                    request.orderId(), tenantId, actorId);
        };

ToolCallback functionCallback = FunctionToolCallback
        .builder("lookupOrder", action)
        .description("Tra cứu trạng thái đơn hàng theo mã")
        .inputType(OrderLookupRequest.class)
        .build();

String result = functionCallback.call(
        "{\"orderId\":\"ORD-100\"}",
        new ToolContext(Map.of(
                "tenantId", "tenant-a",
                "actorId", "user-7"))
);
~~~

Với cách này, kiểm thử cả ToolDefinition được sinh từ OrderLookupRequest, quá trình deserialize JSON thành record và giá trị ToolContext đến đúng BiFunction. Như @Tool, context không nên trở thành một property mà mô hình phải sinh.

Nếu dùng Function chỉ nhận một input, hãy xem implementation callback có đọc ToolContext hay không trước khi dựa vào context. Direct test sẽ phát hiện một callback bỏ qua overload có ToolContext.

## Test 8: dựng MethodToolCallback thủ công

Khi cần tự kiểm soát tên, schema hoặc đăng ký tool động, có thể xây MethodToolCallback từ Method và ToolDefinition:

~~~java
Method method = ReflectionUtils.findMethod(
        OrderTools.class,
        "getOrderStatus",
        String.class,
        ToolContext.class
);
assertThat(method).isNotNull();

ToolDefinition definition = ToolDefinitions.builder(method)
        .description("Tra cứu trạng thái đơn hàng có kiểm tra quyền")
        .build();

MethodToolCallback explicit = MethodToolCallback.builder()
        .toolDefinition(definition)
        .toolMethod(method)
        .toolObject(new OrderTools(orderQueryService))
        .build();

assertThat(explicit.getToolDefinition().name())
        .isEqualTo("getOrderStatus");
~~~

Test cần làm tiếp là gọi explicit.call(json, context) và so sánh kết quả/arguments với callback tạo bằng ToolCallbacks.from(...). Nếu có custom ToolCallResultConverter, xác minh formatter thực sự được dùng, không chỉ kiểm tra setter hoặc builder.

MethodToolCallback cho phép method private/static tùy API nhưng khi dự án dùng Spring transaction/security proxy, nên phân biệt việc reflection gọi được method với việc lời gọi có đi qua Spring bean proxy hay không. Direct test callback sẽ không tự chứng minh transaction được áp dụng, nếu target object được tạo bằng new hoặc bypass proxy.

## Test 9: kiểm tra custom result converter

Đôi lúc cần chuyển record kết quả thành chuỗi riêng thay vì JSON mặc định. Một callback tùy chỉnh phải giữ hợp đồng đó ổn định.

~~~java
ToolCallResultConverter converter = (value, returnType) -> {
    OrderSnapshot snapshot = (OrderSnapshot) value;
    return snapshot.orderId() + "|" + snapshot.status();
};

Method method = ReflectionUtils.findMethod(
        OrderTools.class,
        "getOrderStatus",
        String.class,
        ToolContext.class
);

MethodToolCallback callbackWithConverter = MethodToolCallback.builder()
        .toolDefinition(ToolDefinitions.builder(method)
                .description("Tra cứu trạng thái đơn hàng")
                .build())
        .toolMethod(method)
        .toolObject(new OrderTools(orderQueryService))
        .toolCallResultConverter(converter)
        .build();
~~~

Một test sau đó có thể stub OrderQueryService để trả OrderSnapshot và assert:

~~~java
String output = callbackWithConverter.call(
        "{\"orderId\":\"ORD-100\"}",
        new ToolContext(Map.of(
                "tenantId", "tenant-a",
                "actorId", "user-7"))
);

assertThat(output).isEqualTo("ORD-100|SHIPPING");
~~~

Ví dụ giả định service đã được stub để trả đúng snapshot. Một converter tự xây không được vô tình serialize tenant/actor, session token hoặc dữ liệu nội bộ. Nếu kết quả công cụ được mô hình đọc, phải dùng format rõ ràng, ổn định và giới hạn kích thước.

## Direct callback test và lỗi ToolExecutionExceptionProcessor

Một hiểu lầm phổ biến là callback tự chuyển exception thành lời giải thích an toàn cho mô hình. Thực tế có hai ranh giới:

~~~mermaid
sequenceDiagram
    participant Test as JUnit test
    participant Callback as ToolCallback
    participant Service as Domain service
    participant Manager as ToolCallingManager
    participant Processor as ToolExecutionExceptionProcessor
    Test->>Callback: call(JSON, ToolContext)
    Callback->>Service: Execute
    Service--xCallback: RuntimeException
    Callback--xTest: ToolExecutionException
    Note over Test,Callback: Direct test dừng ở đây
    Manager->>Callback: call(JSON, ToolContext)
    Callback--xManager: ToolExecutionException
    Manager->>Processor: process(error)
    Processor-->>Manager: Safe error text hoặc throw
~~~

Direct test nên assert callback ném gì và có ngăn side effect ngoài ý muốn không. Một test khác ở ToolCallingManager nên tạo ChatResponse giả chứa tool call, rồi xác minh exception processor trả lỗi thành tool result hoặc rethrow theo cấu hình.

Trong Spring AI 2.1.0, processor mặc định có thể chuyển thông điệp của RuntimeException thành tool response; property spring.ai.tools.throw-exception-on-error thay đổi hành vi ném cho caller. Vì vậy:

- Không kỳ vọng mọi exception đều được chuyển thành String trong callback.call(...).
- Không dùng text exception chứa stack trace, SQL, secret hoặc tenant data làm test expectation cho câu trả lời mô hình.
- Không giả định mọi lỗi malformed JSON được bọc vào ToolExecutionException trong mọi phiên bản.
- Kiểm tra lỗi parse/bind, lỗi từ method, lỗi dịch vụ ngoài và lỗi quyền riêng biệt.
- Khi sửa error policy, chạy lại test ở cả callback và manager/advisor boundary.

## Kiểm thử callback tùy chỉnh và cả hai overload call

Nếu đội ngũ tự triển khai ToolCallback (ví dụ proxy tới MCP server, adapter gọi gRPC hoặc wrapper audit), interface có overload call(String, ToolContext) mặc định. Nếu không override, implementation có thể chỉ chuyển về call(String) và bỏ qua context.

Một wrapper giữ nguyên contract nên:

~~~java
public final class DelegatingOrderCallback implements ToolCallback {

    private final ToolCallback delegate;

    public DelegatingOrderCallback(ToolCallback delegate) {
        this.delegate = delegate;
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
        return delegate.call(toolInput);
    }

    @Override
    public String call(String toolInput, ToolContext toolContext) {
        return delegate.call(toolInput, toolContext);
    }
}
~~~

Test wrapper bằng Mockito spy hoặc fake callback để verify:

~~~java
ToolCallback delegate = mock(ToolCallback.class);
ToolContext context = new ToolContext(Map.of(
        "tenantId", "tenant-a"
));
when(delegate.call("{\"orderId\":\"ORD-100\"}", context))
        .thenReturn("{\"ok\":true}");

ToolCallback wrapped = new DelegatingOrderCallback(delegate);
String actual = wrapped.call(
        "{\"orderId\":\"ORD-100\"}", context);

assertThat(actual).isEqualTo("{\"ok\":true}");
verify(delegate).call("{\"orderId\":\"ORD-100\"}", context);
~~~

Test thêm getToolDefinition() và getToolMetadata() để bảo đảm wrapper không tự thay name/schema/returnDirect. Không đăng ký đồng thời wrapper và original dưới cùng tên trong tool catalog.

## Kiểm thử side effect bằng fake repository hoặc sandbox

Với công cụ cập nhật đơn hàng, gửi email hoặc thanh toán, direct callback test không nên chạm dịch vụ thật. Hãy dùng fake service lưu thay đổi trong bộ nhớ hoặc Mockito mock ghi lại invocation, ví dụ:

~~~java
verify(commandService, times(1)).cancelOrder(
        eq("ORD-100"),
        eq("tenant-a"),
        eq("user-7"),
        anyString());
~~~

Đồng thời cần test:

- Request lặp với cùng idempotency key không tạo side effect trùng, ở lớp nghiệp vụ sở hữu idempotency.
- Thiếu quyền hoặc confirmation thì callback/service không thực thi thao tác.
- Khi tool nhận cùng orderId từ hai tenant, không dùng context của request trước.
- Callback thất bại sau khi service đã commit thì hệ thống không coi việc model chưa nhận result là rollback.
- Không có network request thật trong unit test; integration test sử dụng stub HTTP server hoặc môi trường sandbox.

Lưu ý: confirmation được ToolCallingAdvisor/ToolCallingManager xử lý trước execution. Nếu gọi callback trực tiếp, ta đã chủ động bỏ qua lớp confirmation đó. **Không dùng direct callback test để kết luận tool có approval gate đúng**; phải kiểm thử thêm đúng tầng confirmation, và service vẫn cần authorization.

## Kiểm tra timeout, ngắt quãng và concurrency

Direct callback test đồng bộ không có khái niệm model streaming. Tuy nhiên, vẫn có thể kiểm tra code service xử lý cancellation token, timeout hoặc nhiều request đồng thời nếu đó là một phần hợp đồng nghiệp vụ.

Ví dụ kế hoạch test concurrency:

1. Tạo một ToolCallback không giữ mutable identity trong instance field.
2. Dùng ExecutorService chạy đồng thời N callback.call(json, contextN).
3. Đặt CountDownLatch để các task bắt đầu tại cùng thời điểm.
4. Fake service lưu lại các bộ (orderId, tenantId, actorId) đã nhận.
5. Assert mỗi bộ chỉ thuộc request tương ứng; không có tenant/actor lẫn sang request khác.
6. Đóng ExecutorService tại cuối test và dùng timeout để tránh test treo.

Với logic ghi thật, hãy dùng integration test database để kiểm tra transaction và lock; Mockito không thể chứng minh isolation, lost update hoặc deadlock protection. Với cancellation của Flux và tool loop streaming, cần test advisor/stream path thay vì gọi callback đồng bộ rồi suy ra toàn bộ stream đã bị hủy.

## Thiết kế test data và đặt tên test có thể đọc được

Một danh sách test có thể bao phủ hầu hết lỗi trực tiếp:

| Ca kiểm thử | Đầu vào | Kỳ vọng |
|---|---|---|
| Valid arguments + context | orderId hợp lệ, tenant/actor đầy đủ | Đúng service call và JSON result |
| Definition shape | Callback từ @Tool | Name, description, schema đúng |
| Context not model input | Schema + ToolContext | tenantId/actorId không nằm trong properties |
| Missing context | Map rỗng | Từ chối, service không gọi |
| Missing actor | Chỉ tenantId | Từ chối, service không gọi |
| Invalid tenant | Resource tenant khác | Authorization từ chối |
| Two requests | Hai context khác nhau | Không trộn identity |
| Missing required orderId | JSON rỗng | Validation từ chối, không có side effect |
| Malformed JSON | JSON chưa hoàn chỉnh | Parser/binder từ chối |
| Bad enum / number | Giá trị sai kiểu | Không gọi side-effecting service |
| Unknown JSON properties | Model tự chèn tenantId | Không được dùng tenantId giả |
| Null/blank values | Chuỗi rỗng hoặc null | Validation nghiệp vụ |
| Default result converter | Record kết quả | String JSON parse được |
| Custom converter | Record kết quả | Format riêng đã thỏa thuận |
| Function tool with context | DTO và ToolContext | BiFunction nhận đúng cả hai |
| Wrapper callback | Hai overload call | Delegate đủ, không thay ToolDefinition |
| Model/tool processor error | ToolExecutionException | Manager áp dụng error policy riêng |
| returnDirect | ToolMetadata | Đúng cờ; loop behavior test riêng |
| Confirmation | Tool có side effect | Test ở advisor/manager, không chỉ callback |

Không nhất thiết viết một test cho mỗi dòng bằng một class riêng. Có thể nhóm các biến thể bằng @ParameterizedTest và @MethodSource, nhưng nên giữ test authorization/side effect dễ đọc và có tên cụ thể.

## Những điểm direct test không thể chứng minh

Direct ToolCallback test có độ tin cậy cao cho code adapter nhưng không bao phủ:

1. **Model selection:** mô hình có quyết định gọi đúng tool hay không.
2. **Prompt injection:** mô hình có bị nội dung không đáng tin cậy lừa đổi tool hay arguments không.
3. **Loop orchestration:** ToolCallingAdvisor có đưa tool result lại model và dừng đúng lúc không.
4. **Multi-tool behavior:** tool call IDs, execution order, returnDirect khi nhiều tool cùng xuất hiện.
5. **Provider schema compliance:** provider có tuân thủ input JSON schema không.
6. **Framework error policy:** ToolExecutionExceptionProcessor xử lý ở manager layer ra sao.
7. **Transaction thật:** service có commit/rollback đúng khi chạy qua Spring proxy và database không.
8. **Remote integration:** MCP, HTTP, database driver hoặc downstream APIs có tương thích không.

Vì vậy, lịch kiểm thử phù hợp gồm direct callback tests chạy trong mọi pull request, integration tests dùng fake ChatModel/manager/service để xác nhận orchestration và một tập nhỏ provider contract tests chạy với môi trường giới hạn.

## Bài tập thực hành

Xây dựng ba công cụ:

1. getOrderStatus(orderId): đọc thông tin đơn hàng, cần tenantId/actorId.
2. getRefundEligibility(orderId): kiểm tra điều kiện refund, không tạo side effect.
3. requestRefund(orderId): tạo lệnh refund có idempotency, yêu cầu permission/confirmation.

Với mỗi tool, viết các test trực tiếp:

- Sinh ToolCallback bằng ToolCallbacks.from và xác minh name/inputSchema.
- Gọi call(String, ToolContext) bằng JSON cố định và hai context thuộc hai tenant.
- Mock service để verify đúng arguments, không gọi thừa và không lộ dữ liệu tenant khác.
- Parse output JSON hoặc assert formatter riêng.
- Thử thiếu context, sai kiểu JSON, thiếu field, enum sai và service trả exception.
- Dùng wrapper callback giữ nguyên ToolDefinition/ToolMetadata, chạy cả hai overload.
- Với requestRefund, chứng minh service từ chối khi thiếu idempotency hoặc quyền; approval gate ở advisor/manager phải có integration test riêng.

Mục tiêu cuối là mọi test chạy được mà không kết nối model provider, và khi một test fail có thể chỉ ra lỗi ở schema, JSON binding, context propagation, authorization adapter, result conversion hay downstream service.

## Danh sách kiểm tra trước khi merge

- [ ] ToolCallbacks.from tạo đúng tập callback mong đợi.
- [ ] ToolDefinition name/description/inputSchema được kiểm tra bằng assertions ổn định.
- [ ] ToolContext và các field identity không xuất hiện trong model input schema.
- [ ] callback.call(json, context) nhận đúng arguments và context.
- [ ] Service được mock/fake; không gọi network hoặc ghi dữ liệu thật trong unit test.
- [ ] Output được parse/kiểm tra theo cấu trúc thay vì phụ thuộc JSON field order.
- [ ] Thiếu/blank context bị từ chối trước khi truy vấn tài nguyên nhạy cảm.
- [ ] Cross-tenant access được kiểm tra ở service integration test.
- [ ] Malformed JSON/missing required field không gây side effect.
- [ ] Test hiểu ranh giới giữa ToolExecutionException và ToolExecutionExceptionProcessor.
- [ ] Callback wrapper delegate đủ hai overload và metadata framework.
- [ ] Tool có side effect được test thêm idempotency, authorization và confirmation đúng tầng.
- [ ] Có test request context độc lập và concurrency nếu callback dùng chung.
- [ ] Không log raw tool arguments, credential hoặc context nhạy cảm trong test output.
- [ ] Có test manager/advisor riêng cho loop, returnDirect, confirmation và tool-result messages.
- [ ] Có provider contract test riêng khi thay model/provider hoặc schema behavior.

**Kết luận:** kiểm thử ToolCallback và ToolContext trực tiếp là lớp kiểm thử nhanh, xác định và ít tốn chi phí nhất để chứng minh tool Java thực thi đúng hợp đồng đầu vào/đầu ra và không nhầm dữ liệu do mô hình tạo với dữ liệu tin cậy của ứng dụng. Sau khi lớp này ổn định, hãy kiểm thử thêm ToolCallingManager, ToolCallingAdvisor và provider ở đúng ranh giới của chúng; không bắt một test trực tiếp phải chứng minh những hành vi nó không chạy qua.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling, ToolCallback, JSON Schema và ToolContext](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — ChatModel Tool Calling và vòng lặp do ứng dụng điều phối](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [Spring AI 2.1.x API — ToolCallback](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/ToolCallback.html)
- [Spring AI 2.1.x API — MethodToolCallback](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/method/MethodToolCallback.html)
- [Spring AI 2.1.x API — ToolContext](https://docs.spring.io/spring-ai/docs/2.1.0-M1/api/org/springframework/ai/chat/model/ToolContext.html)
- [Spring AI 2.1.x API — ToolExecutionException và result conversion](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/execution/package-summary.html)

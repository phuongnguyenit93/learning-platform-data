# Truyền ngữ cảnh và áp dụng chính sách tại thời điểm thực thi

Một custom `ToolCallback` cho phép ứng dụng kiểm soát toàn bộ quá trình thực thi công cụ. Khi mô hình yêu cầu một tool, Spring AI chuyển JSON arguments đến callback; nếu request có `ToolContext`, callback cũng nhận được ngữ cảnh do ứng dụng cung cấp. Từ hai nguồn này, ứng dụng có thể xác định **ai đang gọi**, **đang yêu cầu thao tác nào**, **trên tài nguyên nào** và **chính sách hiện tại có cho phép thực thi hay không**.

Bài học dùng ví dụ tra cứu tồn kho theo tenant. Mô hình chỉ được đề xuất SKU và mã kho. Danh tính người dùng, tenant và request ID được ứng dụng lấy từ phiên đã xác thực rồi truyền qua `ToolContext`; policy service truy vấn quyền hiện hành khi callback chạy. Custom callback kiểm tra ngữ cảnh, phân tích arguments, gọi policy service ở thời điểm thực thi và chỉ sau khi được phép mới gọi dịch vụ nghiệp vụ.

## 1. Vì sao cần kiểm tra chính sách tại thời điểm thực thi?

Tool definition mô tả công cụ nào có thể được mô hình yêu cầu và cấu trúc arguments mà mô hình phải gửi. Nó không phải cơ chế xác thực hoặc cấp quyền. Một mô hình có thể tạo arguments hợp lệ theo schema nhưng vẫn yêu cầu đọc tài nguyên thuộc tenant khác, truy cập bản ghi mà người dùng không sở hữu hoặc thực hiện hành động không còn được phép.

Quyền có thể thay đổi sau khi prompt được tạo: tài khoản bị khóa, vai trò bị thu hồi, bản ghi chuyển chủ sở hữu, hạn mức đã hết hoặc trạng thái nghiệp vụ thay đổi. Vì vậy, kiểm tra quyền khi chỉ tạo danh sách tool hoặc trước khi gửi prompt là chưa đủ. Callback phải kiểm tra lại chính sách ngay trước thao tác nghiệp vụ.

Có ba lớp trách nhiệm nên được tách bạch:

| Lớp | Dữ liệu | Trách nhiệm |
| --- | --- | --- |
| Tool definition | Tên, mô tả, JSON Schema | Hướng dẫn mô hình tạo yêu cầu có cấu trúc |
| Tool arguments | Giá trị do mô hình tạo, như `sku`, `warehouseCode` | Mô tả tài nguyên hoặc hành động mà mô hình muốn yêu cầu |
| ToolContext và policy | Danh tính, tenant, quyền, request scope do ứng dụng xác thực | Xác định yêu cầu có được phép thực thi tại thời điểm gọi hay không |

Ẩn một tool khỏi prompt hoặc không đăng ký tool cho một request giúp giảm khả năng mô hình yêu cầu nó. Tuy nhiên, kiểm tra trong callback vẫn là ranh giới bảo vệ cuối cùng trước service nghiệp vụ.

## 2. ToolContext mang dữ liệu không gửi cho mô hình

`ToolContext` thuộc package `org.springframework.ai.chat.model`. Nó bọc một map ngữ cảnh được truyền cùng request đến công cụ. Spring AI gửi tool definitions cho mô hình; context được chuyển trực tiếp đến callback tại thời điểm thực thi và không xuất hiện trong JSON arguments mà mô hình tạo.

Ví dụ, ứng dụng có thể tạo một đối tượng danh tính bất biến từ principal đã xác thực:

```java
public record ToolExecutionIdentity(
        String subjectId,
        String tenantId,
        String requestId) {
}
```

`ToolExecutionIdentity` là kiểu của ứng dụng. `subjectId`, `tenantId` và `requestId` phải được lấy từ authentication/session hoặc một dịch vụ danh tính đáng tin cậy. Không tạo đối tượng này bằng cách sao chép các trường `userId`, `tenantId` hay `role` do mô hình gửi trong arguments. Không dùng danh sách quyền chụp tại lúc tạo prompt làm nguồn quyết định cuối cùng; policy nên đọc trạng thái quyền hiện hành tại lúc callback thực thi.

Ở tầng ứng dụng, tạo context từ principal đã xác thực rồi gắn vào request:

```java
ToolExecutionIdentity caller = identityFactory.from(authentication, requestId);

String answer = chatClient.prompt()
        .user("Kiểm tra tồn kho SKU-42 tại kho HCM-01.")
        .tools(inventoryLookupCallback)
        .toolContext(Map.of("caller", caller))
        .call()
        .content();
```

Đối tượng `authentication` ở đây là danh tính đã được Spring Security xác thực. `identityFactory` chuyển thông tin cần thiết thành một context nhỏ, chỉ chứa dữ liệu mà tool thực sự cần. Tránh truyền toàn bộ `Authentication`, HTTP request, session object hoặc credential vào context.

`ToolContext` cung cấp một map không thể sửa đổi qua `getContext()`. Tuy nhiên, map bất biến không tự làm cho các object lồng bên trong trở nên bất biến. Dùng record, immutable DTO và collection bất biến để tránh thay đổi ngữ cảnh ngoài ý muốn.

## 3. Thiết kế custom ToolCallback

`ToolCallback` là hợp đồng chung giữa định nghĩa công cụ và hành vi thực thi. Một implementation tùy chỉnh cần cung cấp:

- `getToolDefinition()` trả về tên, mô tả và input schema mà mô hình nhìn thấy.
- `call(String toolInput)` xử lý JSON arguments khi không có context.
- `call(String toolInput, ToolContext toolContext)` xử lý JSON arguments cùng context của request.
- `getToolMetadata()` có thể được ghi đè nếu cần cấu hình metadata như `returnDirect`; nếu không, dùng giá trị mặc định của interface.

Ví dụ schema của công cụ tra cứu tồn kho:

```java
private static final ToolDefinition DEFINITION = ToolDefinition.builder()
        .name("lookup_inventory")
        .description("Tra cứu số lượng tồn kho của SKU tại một kho. Chỉ dùng khi người dùng hỏi số lượng hàng hiện tại.")
        .inputSchema("""
            {
              "type": "object",
              "properties": {
                "sku": {
                  "type": "string",
                  "description": "Mã SKU chính xác của sản phẩm"
                },
                "warehouseCode": {
                  "type": "string",
                  "description": "Mã kho cần tra cứu"
                }
              },
              "required": ["sku", "warehouseCode"],
              "additionalProperties": false
            }
            """)
        .build();
```

Schema chỉ có `sku` và `warehouseCode`. Không đưa `tenantId`, `subjectId`, role hay permission vào schema vì mô hình không phải nguồn có thẩm quyền đối với những giá trị này.

## 4. Kiểm tra context, arguments và policy trước khi gọi service

Ta tách policy thành một interface để callback không phải tự chứa toàn bộ quy tắc phân quyền:

```java
public interface ToolExecutionPolicy {

    void requireAllowed(
            ToolExecutionIdentity caller,
            String action,
            String resourceId);
}
```

Implementation của policy có thể gọi Spring Security, dịch vụ authorization, tenant resolver hoặc policy engine của hệ thống. Ví dụ, với action `inventory:read`, policy kiểm tra người dùng có quyền đọc kho tương ứng và kho đó thuộc tenant đang hoạt động.

Luồng trong callback nên theo thứ tự:

1. Xác nhận context tồn tại và chứa danh tính hợp lệ.
2. Parse JSON arguments thành DTO.
3. Kiểm tra dữ liệu đầu vào và chuẩn hóa định dạng.
4. Kết hợp danh tính trong context với resource/action trong arguments.
5. Đánh giá policy tại thời điểm thực thi.
6. Chỉ khi được phép mới gọi service nghiệp vụ.
7. Ghi audit decision và chuyển kết quả thành chuỗi JSON an toàn.

Không gọi service trước rồi mới kiểm tra quyền. Cũng không chỉ kiểm tra một role chung; policy cần đánh giá resource cụ thể, tenant cụ thể và hành động cụ thể.

## 5. Ví dụ custom callback hoàn chỉnh

Ví dụ dưới đây dùng Jackson để parse arguments, `ToolContext` để nhận danh tính tin cậy và `ToolExecutionPolicy` để quyết định quyền. Các kiểu `InventoryService`, `InventoryResult`, `InventoryLookupRequest`, `ToolExecutionIdentity` và `ToolExecutionPolicy` là các kiểu do ứng dụng định nghĩa.

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.ai.tool.execution.ToolExecutionException;
import org.springframework.security.access.AccessDeniedException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class InventoryLookupCallback implements ToolCallback {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryLookupCallback.class);

    private static final String CALLER_KEY = "caller";

    private final ToolDefinition definition;
    private final ObjectMapper objectMapper;
    private final ToolExecutionPolicy policy;
    private final InventoryService inventoryService;

    public InventoryLookupCallback(
            ObjectMapper objectMapper,
            ToolExecutionPolicy policy,
            InventoryService inventoryService) {
        this.objectMapper = objectMapper;
        this.policy = policy;
        this.inventoryService = inventoryService;
        this.definition = ToolDefinition.builder()
                .name("lookup_inventory")
                .description("Tra cứu số lượng tồn kho của SKU tại một kho.")
                .inputSchema("""
                    {
                      "type": "object",
                      "properties": {
                        "sku": { "type": "string" },
                        "warehouseCode": { "type": "string" }
                      },
                      "required": ["sku", "warehouseCode"],
                      "additionalProperties": false
                    }
                    """)
                .build();
    }

    @Override
    public ToolDefinition getToolDefinition() {
        return this.definition;
    }

    @Override
    public String call(String toolInput) {
        return call(toolInput, null);
    }

    @Override
    public String call(String toolInput, ToolContext toolContext) {
        String requestId = "unknown";

        try {
            ToolExecutionIdentity caller = requireCaller(toolContext);
            requestId = caller.requestId();

            InventoryLookupRequest request = objectMapper.readValue(
                    toolInput, InventoryLookupRequest.class);
            validate(request);

            policy.requireAllowed(
                    caller,
                    "inventory:read",
                    request.warehouseCode());

            InventoryResult result = inventoryService.lookup(
                    caller.tenantId(),
                    request.sku(),
                    request.warehouseCode());

            return objectMapper.writeValueAsString(result);
        }
        catch (JsonProcessingException ex) {
            log.warn("Invalid arguments for tool requestId={}", requestId);
            throw new ToolExecutionException(
                    definition,
                    new IllegalArgumentException("Đối số công cụ không hợp lệ."));
        }
        catch (IllegalArgumentException ex) {
            log.warn("Invalid tool values for requestId={}", requestId);
            throw new ToolExecutionException(
                    definition,
                    new IllegalArgumentException("Đối số công cụ không hợp lệ."));
        }
        catch (AccessDeniedException ex) {
            log.warn("Tool access denied requestId={}", requestId);
            throw new ToolExecutionException(
                    definition,
                    new AccessDeniedException("Không có quyền truy cập dữ liệu được yêu cầu."));
        }
        catch (Exception ex) {
            log.error("Tool execution failed requestId={}", requestId, ex);
            throw new ToolExecutionException(
                    definition,
                    new IllegalStateException("Không thể thực hiện công cụ lúc này."));
        }
    }

    private ToolExecutionIdentity requireCaller(ToolContext context) {
        if (context == null) {
            throw new AccessDeniedException("Thiếu ngữ cảnh xác thực.");
        }

        Object value = context.getContext().get(CALLER_KEY);
        if (!(value instanceof ToolExecutionIdentity caller)
                || caller.subjectId() == null
                || caller.tenantId() == null) {
            throw new AccessDeniedException("Ngữ cảnh người gọi không hợp lệ.");
        }

        return caller;
    }

    private void validate(InventoryLookupRequest request) {
        if (request == null
                || request.sku() == null || request.sku().isBlank()
                || request.warehouseCode() == null || request.warehouseCode().isBlank()) {
            throw new IllegalArgumentException("Thiếu SKU hoặc mã kho.");
        }
    }
}
```

Callback không lưu caller hoặc tenant vào field. Mỗi lần gọi nhận context riêng từ request, nhờ đó cùng một bean singleton có thể phục vụ nhiều request đồng thời mà không trộn dữ liệu người dùng.

Trong ví dụ, lỗi gửi cho framework dùng thông điệp đã được kiểm soát. Chi tiết exception gốc được ghi ở log nội bộ. Với hệ thống production, nên phân loại lỗi nghiệp vụ rõ ràng hơn và chỉ ghi dữ liệu cần thiết; không ghi nguyên văn arguments nếu chúng có thể chứa thông tin cá nhân hoặc bí mật.

## 6. Tạo context từ danh tính đã xác thực

Ứng dụng nên xây dựng `ToolExecutionIdentity` ở tầng đã biết principal, tenant và quyền. Ví dụ dưới đây minh họa cách truyền context từ một service điều phối:

```java
public String askInventoryQuestion(
        Authentication authentication,
        String tenantId,
        String requestId,
        String question) {

    ToolExecutionIdentity caller = identityFactory.from(
            authentication, tenantId, requestId);

    return chatClient.prompt()
            .user(question)
            .tools(inventoryLookupCallback)
            .toolContext(Map.of("caller", caller))
            .call()
            .content();
}
```

`identityFactory` phải xác minh tenant và ánh xạ authorities từ nguồn xác thực. Nếu tenant đến từ header hoặc URL, cần đối chiếu tenant đó với quyền của principal trước khi tạo context. Không được tin một tenant ID chỉ vì nó xuất hiện trong request.

Tránh lấy danh tính trực tiếp trong callback từ `SecurityContextHolder` nếu luồng thực thi có thể chuyển thread hoặc chạy bất đồng bộ. Truyền context tường minh giúp ranh giới giữa request và tool dễ kiểm tra hơn. Nếu hệ thống có yêu cầu propagation security context riêng, hãy cấu hình và kiểm thử cơ chế đó một cách chủ đích.

## 7. Chính sách cần đánh giá những gì?

Policy service nhận danh tính tin cậy và hành động/tài nguyên mà tool arguments yêu cầu. Một quyết định có thể dựa trên nhiều điều kiện:

| Nhóm kiểm tra | Ví dụ |
| --- | --- |
| Danh tính | Principal đã xác thực, tài khoản còn hoạt động |
| Tenant | Người gọi thuộc tenant sở hữu kho hoặc dữ liệu |
| Permission | Có quyền `inventory:read` hoặc `inventory:adjust` |
| Resource-level access | Kho hoặc sản phẩm nằm trong phạm vi được cấp |
| Trạng thái nghiệp vụ | Kho đang hoạt động, đơn hàng chưa khóa |
| Hạn mức | Số lần gọi, quota hoặc giới hạn số bản ghi |
| Thời điểm | Quyền còn hiệu lực, thao tác chỉ được phép trong khung giờ |
| Phê duyệt | Hành động ghi dữ liệu có approval hợp lệ và chưa hết hạn |

Phân biệt quyền đọc và quyền thay đổi. Một principal được xem tồn kho không có nghĩa họ được điều chỉnh số lượng hoặc chuyển kho. Với thao tác ghi, policy nên kiểm tra cả trạng thái tài nguyên và điều kiện nghiệp vụ trước khi thực thi.

### Kiểm tra lại quyền ngay trước side effect

Với thao tác có side effect, khoảng thời gian từ lúc tạo prompt đến lúc callback chạy có thể đủ dài để quyền hoặc trạng thái tài nguyên thay đổi. Kiểm tra lại authorization ngay trước lệnh ghi và thực hiện cập nhật trong transaction phù hợp.

Nếu cần người dùng xác nhận, approval phải gắn với hành động đã chuẩn hóa: loại thao tác, tài nguyên, giá trị thay đổi, tenant, người duyệt và thời hạn. Callback xác minh approval ở thời điểm thực thi và đánh dấu token/approval đã dùng để tránh replay. Không coi một câu trong prompt như “tôi đồng ý” là bằng chứng xác nhận đáng tin cậy.

## 8. Kết hợp ToolContext với dynamic policy

`ToolContext` mang dữ liệu đầu vào cho policy, còn policy service quyết định cho phép hay từ chối. Không nên nhúng toàn bộ logic authorization vào schema hoặc mô tả tool. Cũng không nên lưu một boolean như `isAdmin=true` trong context rồi bỏ qua kiểm tra; hãy truyền danh tính và dữ liệu cần thiết để policy có thể đưa ra quyết định.

Ví dụ policy service:

```java
@Service
public class InventoryToolPolicy implements ToolExecutionPolicy {

    private final InventoryAuthorization authorization;

    public InventoryToolPolicy(InventoryAuthorization authorization) {
        this.authorization = authorization;
    }

    @Override
    public void requireAllowed(
            ToolExecutionIdentity caller,
            String action,
            String warehouseCode) {

        // Truy vấn quyền hiện hành theo subject/tenant/action/resource.
        boolean allowed = authorization.isAllowed(
                caller.subjectId(),
                caller.tenantId(),
                action,
                warehouseCode);

        if (!allowed) {
            throw new AccessDeniedException("Không có quyền thực hiện thao tác này.");
        }
    }
}
```

Policy service nên là nơi thống nhất các quy tắc truy cập mà những entry point khác cũng sử dụng. Nếu có nhiều custom callback, cùng gọi một policy service sẽ tránh việc mỗi tool tự diễn giải role hoặc tenant theo cách khác nhau.

### Hạn chế quyền theo từng request

Đưa callback vào `.tools(...)` theo từng request để chỉ cung cấp những công cụ phù hợp với nghiệp vụ hiện tại. `defaultTools(...)` thích hợp cho công cụ dùng chung, ít rủi ro và có thể xuất hiện ở mọi request. Công cụ ghi dữ liệu hoặc có quyền cao nên được cấp rõ ràng theo request.

Spring AI 2.x có `ToolCallbackResolver` để phân giải tool theo tên trong những tình huống động. Resolution fallback mặc định tắt. Nếu bật `spring.ai.tools.resolution.fallback.enabled=true`, một tool có thể được resolver tìm thấy và thực thi dù request không đính kèm callback đó. Chỉ bật khi kiểm soát đầy đủ danh sách resolver; dù dùng cách nào, callback vẫn phải kiểm tra policy ở thời điểm thực thi.

## 9. Xử lý lỗi và quyết định có trả lỗi cho mô hình hay không

Khi custom callback thất bại, hãy ném `ToolExecutionException` với `ToolDefinition` tương ứng và nguyên nhân. `ToolExecutionExceptionProcessor` quyết định chuyển lỗi thành chuỗi cho mô hình hoặc ném exception để caller xử lý.

```java
@Bean
ToolExecutionExceptionProcessor toolExecutionExceptionProcessor() {
    return exception -> {
        if (exception.getCause() instanceof AccessDeniedException denied) {
            throw denied;
        }
        return """
            {"ok":false,"code":"TOOL_EXECUTION_FAILED","message":"Không thể xử lý yêu cầu công cụ."}
            """;
    };
}
```

Đây là ví dụ processor toàn ứng dụng: lỗi quyền bị ném lên để tầng bảo mật xử lý; lỗi khác trả về mã chung, không lộ exception nội bộ. Nếu hệ thống dùng OAuth2, cần giữ nguyên hành vi ném lại `ClientAuthorizationException` để quy trình refresh/ủy quyền có thể hoạt động.

Processor mặc định có thể gửi message của `RuntimeException` về mô hình; checked exception và `Error` được ném lại. Có thể cấu hình `spring.ai.tools.throw-exception-on-error=true` để yêu cầu ném lỗi cho caller. Hãy chọn chính sách dựa trên loại lỗi: lỗi đầu vào có thể trả về mô hình để hỏi lại, còn lỗi xác thực/ủy quyền hoặc lỗi hạ tầng nhạy cảm thường cần được xử lý ở tầng ứng dụng.

Không trả stack trace, SQL, tên bảng, token, thông tin xác thực, policy nội bộ hoặc chi tiết hệ thống trong error response. Mô hình chỉ cần mã lỗi và thông điệp đã được kiểm soát để giải thích hoặc hỏi người dùng.

## 10. Audit và quan sát quyết định thực thi

Khi callback chạy, cần có dấu vết để trả lời được ai yêu cầu thao tác nào, policy nào đã được đánh giá và kết quả ra sao. Một audit event nên ghi những trường tối thiểu:

- `requestId` hoặc correlation ID.
- Tên tool và action nghiệp vụ.
- `subjectId` và `tenantId` đã được xác thực.
- Định danh tài nguyên cần truy cập.
- Quyết định `ALLOW` hoặc `DENY` và mã lý do.
- Policy/version được áp dụng nếu hệ thống có versioning.
- Thời điểm, thời lượng và kết quả thực thi.

Không ghi nguyên văn tool arguments hoặc result vào log mặc định. Chúng có thể chứa dữ liệu cá nhân, thông tin tài khoản hoặc dữ liệu nhạy cảm. Nếu cần ghi payload để debug, phải có cơ chế che dữ liệu, kiểm soát quyền đọc log và thời hạn lưu trữ.

Spring AI phát ra Micrometer observation cho tool call với tên observation `spring.ai.tool`, bao gồm tên tool, metadata, thời lượng và tracing context khi có tracer. Việc đưa arguments/results vào span attributes là tùy chọn và mặc định tắt vì lý do nhạy cảm. Audit authorization nên được ghi riêng ở lớp policy/application để có đủ subject, tenant và quyết định nghiệp vụ.

## 11. Kiểm thử custom ToolCallback và policy

Kiểm thử nên xác minh cả kết quả và việc service có bị gọi hay không. Trong các trường hợp bị từ chối, assertion quan trọng là không có lệnh nghiệp vụ nào được thực thi.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Context hợp lệ, policy cho phép | Service được gọi đúng tenant/resource và trả JSON kết quả |
| Context null hoặc thiếu caller | Từ chối trước khi gọi policy/service |
| Caller thuộc tenant khác | Policy từ chối; không đọc dữ liệu tenant khác |
| Quyền bị thu hồi sau khi tạo prompt | Callback đánh giá lại và từ chối ở thời điểm thực thi |
| JSON sai hoặc thiếu trường | Báo lỗi arguments an toàn; không gọi service |
| SKU/kho không tồn tại | Trả lỗi nghiệp vụ đã chuẩn hóa |
| Hạn mức đã hết | Policy/quota service từ chối trước side effect |
| Approval thiếu, hết hạn hoặc đã dùng | Từ chối thao tác ghi |
| Nhiều request đồng thời khác tenant | Context từng request không bị trộn |
| Service phụ thuộc bị lỗi | Log nội bộ có correlation ID; response không lộ chi tiết |

Ví dụ kiểm thử ý tưởng với Mockito:

```java
@Test
void shouldNotCallServiceWhenPolicyDeniesAccess() {
    ToolExecutionIdentity caller = new ToolExecutionIdentity(
            "user-17", "tenant-A", "req-123");
    ToolContext context = new ToolContext(Map.of("caller", caller));

    doThrow(new AccessDeniedException("denied"))
            .when(policy).requireAllowed(
                    caller, "inventory:read", "HCM-01");

    assertThatThrownBy(() -> callback.call(
            """
            {"sku":"SKU-42","warehouseCode":"HCM-01"}
            """, context))
            .isInstanceOf(ToolExecutionException.class);

    verifyNoInteractions(inventoryService);
}
```

Đây là kiểm thử ranh giới callback; phần setup mock, kiểu `InventoryLookupRequest` và cách tạo callback cần điều chỉnh theo dự án. Nên có integration test qua `ChatClient` để xác nhận ToolContext được truyền từ request đến callback, nhưng unit test vẫn cần kiểm tra policy độc lập để tránh phụ thuộc vào quyết định của mô hình.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Rủi ro | Cách sửa |
| --- | --- | --- |
| Để mô hình tự gửi tenant/user/role | Mô hình có thể yêu cầu truy cập tenant hoặc danh tính khác | Lấy danh tính từ principal và truyền qua ToolContext |
| Chỉ kiểm tra quyền lúc đăng ký tool | Quyền có thể thay đổi trước khi callback chạy | Kiểm tra lại trong callback trước service |
| Lưu caller vào field của callback singleton | Request đồng thời có thể dùng nhầm danh tính | Dùng context của từng lần gọi, không lưu state theo request |
| Chỉ dựa vào việc ẩn tool | Tool vẫn có thể được gọi qua resolver hoặc cấu hình khác | Thực thi policy ở callback và kiểm soát resolver |
| Dùng role chung thay cho kiểm tra resource | Người dùng có quyền rộng hơn phạm vi cần thiết | Kiểm tra action + tenant + resource cụ thể |
| Gửi exception gốc cho mô hình | Lộ dữ liệu nội bộ hoặc thông tin bảo mật | Chuẩn hóa mã lỗi và thông điệp |
| Ghi toàn bộ arguments vào log | Có thể rò rỉ PII hoặc bí mật | Ghi metadata tối thiểu, che payload |
| Tin map bất biến là mọi object đều bất biến | Object lồng có thể bị thay đổi | Dùng record và collection bất biến |

## 13. Checklist triển khai

- [ ] Tool definition chỉ chứa dữ liệu mô hình cần biết; không chứa identity, tenant hay quyền.
- [ ] Danh tính và tenant được tạo từ nguồn xác thực đáng tin cậy.
- [ ] `ToolContext` được truyền theo từng request và không lưu vào field dùng chung.
- [ ] Context sử dụng record/DTO bất biến.
- [ ] Callback parse và validate arguments trước khi gọi service.
- [ ] Policy được đánh giá tại thời điểm thực thi trên action và resource cụ thể.
- [ ] Kiểm tra quyền được thực hiện trước mọi side effect.
- [ ] Hành động ghi có approval/idempotency khi nghiệp vụ yêu cầu.
- [ ] `ToolExecutionException` và processor không làm lộ thông tin nội bộ.
- [ ] Resolver fallback và danh sách tool được cấu hình có chủ đích.
- [ ] Audit event có request ID, subject, tenant, action và decision.
- [ ] Kiểm thử context thiếu, tenant sai, quyền bị thu hồi, JSON sai và request đồng thời.

## Tài liệu tham khảo

- [Spring AI 2.1 — Tool Specification Reference](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/tools/reference.html) (bản SNAPSHOT; trang ghi rõ bản ổn định hiện hành là 2.1.0)
- [Spring AI 2.1 — Tool Calling](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/tools/index.html) (bản SNAPSHOT; đối chiếu API với bản ổn định 2.1.0 khi triển khai)
- [ToolCallback API — Spring AI 2.1](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/ToolCallback.html)
- [ToolContext API — Spring AI 2.1](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/model/ToolContext.html)
- [ToolExecutionException API — Spring AI 2.1](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/execution/ToolExecutionException.html)

Custom `ToolCallback` là nơi ứng dụng kiểm soát chính xác việc chuyển từ yêu cầu của mô hình sang hành động nghiệp vụ. Hãy giữ schema cho arguments mà mô hình được phép đề xuất, truyền danh tính tin cậy qua `ToolContext`, rồi đánh giá policy trên từng hành động và tài nguyên ngay trước khi thực thi. Cách tổ chức này giúp các công cụ dùng chung một vòng điều phối của Spring AI mà vẫn tuân theo quyền truy cập và trạng thái nghiệp vụ hiện tại.

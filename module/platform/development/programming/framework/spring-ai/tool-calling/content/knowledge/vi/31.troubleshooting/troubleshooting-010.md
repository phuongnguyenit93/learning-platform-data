# Trùng tên công cụ từ nhiều nguồn hoặc resolver trả sai callback

Trong một ứng dụng Spring AI Tool Calling, hai công cụ có thể có cùng **tên mà mô hình nhìn thấy** dù được đăng ký từ những nguồn hoàn toàn khác nhau: method `@Tool` của ứng dụng, `FunctionToolCallback`, `ToolCallback` bean, `ToolCallbackProvider` hoặc MCP server. Nếu tên không duy nhất, mô hình chỉ trả về tên và JSON arguments, không gửi danh tính Java bean hoặc địa chỉ MCP server mà nhà phát triển muốn chọn. Kết quả có thể là lỗi đăng ký, không tìm thấy tool, gọi nhầm backend, trả dữ liệu sai tenant, hoặc thậm chí thực thi một callback có side effect không mong đợi.

Bài học thuộc chương **Chẩn đoán sự cố** của mô-đun `SPRING_AI_TOOL_CALLING`. Trong mô-đun này, mô hình đề xuất tool calls còn ứng dụng thực thi bằng `@Tool`/`ToolCallback`, schema, `ToolCallingManager` và `ToolContext`. Vì vậy, chẩn đoán phải đi từ **tập callback thực sự đưa vào request → tên mà model đề xuất → cách manager chọn callback → quyền và side effect tại service**, chứ không dừng ở việc đọc câu trả lời cuối của mô hình.

**Nguyên tắc:** tên tool cần duy nhất và ổn định trong phạm vi thực thi; resolver chỉ dùng để tìm callback theo tên, **không cấp quyền**. Khi không chứng minh được callback đúng, hãy từ chối thực thi (fail closed), không tự thử một callback “gần giống”.

## 1. Ba lỗi thường bị nhầm là một

| Triệu chứng | Ý nghĩa khả dĩ | Cách xác nhận |
| --- | --- | --- |
| `IllegalStateException` nói tên tool bị trùng | Hai callback cùng tên trong tập gắn vào `ChatClient` | Liệt kê tên sau khi gộp `defaultTools` và `tools` |
| Model gọi `searchCustomer` nhưng dữ liệu từ sai hệ thống | Luồng thực thi chọn callback cùng tên từ nguồn khác, hoặc resolver/caching cấu hình sai | Đối chiếu `toolName → source/owner → callback instance → service trace` |
| Model đề xuất tool hợp lệ nhưng báo “tool not found” | Tool không đính vào request; fallback tắt; tên model trả khác tên đăng ký | So sánh danh sách công bố với tên thực trong tool call |
| Tool xuất hiện hai lần trong catalogue nhưng chỉ một callback chạy | Collision bị lọc/gộp trước đó hoặc custom loop lấy entry đầu tiên | Kiểm tra quá trình xây registry, index, callback list |
| Sau khi đổi MCP server, tên tool đổi hoặc tool không tìm thấy | Prefix generator đổi tên, danh sách MCP mới hoặc cache cũ | In resolved names, provider/server, catalog version |
| Chỉ lỗi trên một số user/tenant | Request-scoped tools, role policy, session/index cache khác nhau | So sánh cùng prompt với tập tool và quyền đã xác thực |
| Không lỗi compile, nhưng gọi callback sai | Kiểu arguments tương thích giữa hai tool trùng tên nên lỗi âm thầm | Callback spy + audit nguồn thực thi |
| Lỗi JSON schema ngay sau tool call | Model chọn sai tool hoặc schema callback được thay đổi | So sánh schema được công bố và schema callback được gọi |

Không nên sửa bằng cách tăng temperature, sửa prompt để model “gọi đúng hơn” hoặc bật fallback resolver rộng hơn. Nếu tên trùng dẫn đến sai callback, đây là **sự cố định danh và phân giải của ứng dụng**, không đơn thuần là chất lượng ngôn ngữ của mô hình.

## 2. Tên tool là khóa định tuyến, không phải mô tả Java bean

Một tool có nhiều lớp danh tính:

| Trường | Ví dụ | Có dùng trực tiếp để model gọi không? |
| --- | --- | --- |
| Spring bean name | `billingCustomerToolBean` | Không nhất thiết |
| Java method name | `getCustomer` | Có thể được dùng làm mặc định cho `@Tool` |
| Tool definition name | `billing_getCustomer` | **Có** |
| Tool description | “Đọc hồ sơ khách hàng thanh toán...” | Giúp model chọn, không định danh |
| Provider/owner | `mcp-billing` hoặc `billing-service` | Không nằm trong tool-call name nếu chưa được namespace |
| Tool-call ID | `call_68a` | Liên kết một lần gọi và kết quả, **không** chọn callback |

Khi model trả:

~~~json
{
  "id": "call_68a",
  "name": "getCustomer",
  "arguments": "{\"customerId\":\"C-123\"}"
}
~~~

manager phải tìm callback theo `name=getCustomer` trong phạm vi cho phép. ID `call_68a` chỉ giúp ghép `ToolResponseMessage` đúng lời gọi, **không chỉ ra** đây là callback CRM hay billing. Hai callback trùng tên và cùng nhận `customerId` có thể gây lỗi rất khó phát hiện nếu cả hai đều trả JSON hợp lệ.

Ví dụ một nguồn địa phương có `@Tool(name = "getCustomer")` để đọc hồ sơ CRM, trong khi MCP Billing cũng công bố `getCustomer` để tra dữ liệu thanh toán. **Trùng tên định danh không đồng nghĩa hai tool có cùng chức năng hoặc cùng quyền.**

## 3. Sơ đồ luồng cần kiểm tra khi sự cố xảy ra

~~~mermaid
flowchart TD
    A["Nguồn tool: @Tool / ToolCallback / Provider / MCP"] --> B["Ghép tool set theo request"]
    B --> C{"Có trùng ToolDefinition.name?"}
    C -->|Có| X["Fail closed, log collision metadata"]
    C -->|Không| D["Gửi tool definitions cho model"]
    D --> E["Model trả name + arguments + callId"]
    E --> F["Manager resolve callback trong request"]
    F --> G{"Có callback đúng scope?"}
    G -->|Không| H{"Resolver fallback có bật?"}
    H -->|Có| I["Resolver tra tool ngoài request: kiểm tra đặc biệt"]
    H -->|Không| Y["Trả tool not found / deny"]
    G -->|Có| J["Parse schema, ToolContext, authorization"]
    I --> J
    J --> K{"Policy + resource hợp lệ?"}
    K -->|Không| Y
    K -->|Có| L["Thực thi service, ghi audit"]
    L --> M["ToolResponseMessage theo đúng callId"]
~~~

Điểm tra cứu tốt nhất là **callback thật sự được thực thi**, không phải chỉ “model có nhìn thấy tên tool đó không?”. Tool catalog và model definitions có thể đúng nhưng một custom resolver hoặc luồng low-level vẫn chọn sai callback ở bước execution.

## 4. Khác biệt quan trọng giữa ChatClient và ChatModel trực tiếp

Tài liệu chính thức Spring AI 2.1.0 phân biệt hai đường đi:

**Đường `ChatClient`:** khi dùng `.tools(...)` và `.defaultTools(...)`, Spring AI kiểm tra **tập callback hợp nhất**. Nếu hai callback chia sẻ cùng tên, lời gọi có thể ném `IllegalStateException` thay vì âm thầm chọn một tool. Điều này áp dụng khi danh sách đã đi qua cơ chế validation của `ChatClient`.

**Đường `ChatModel.call()/stream()` hoặc vòng tool tự viết:** nếu tự ghép `ToolCallingChatOptions` mà không validation, cùng tên có thể dẫn tới manager chọn **callback đầu tiên trong danh sách**, không log lỗi. Đây là tình huống rủi ro nhất: tool MCP có thể chiếm vị trí callback local hoặc ngược lại.

Ví dụ hai nguồn có tên trùng:

~~~java
ToolCallback crmTool = FunctionToolCallback
        .builder("getCustomer", crmService::getCustomer)
        .description("Đọc hồ sơ khách hàng CRM.")
        .inputType(CustomerLookup.class)
        .build();

ToolCallback billingTool = FunctionToolCallback
        .builder("getCustomer", billingService::getCustomer)
        .description("Đọc tài khoản thanh toán của khách hàng.")
        .inputType(CustomerLookup.class)
        .build();

ChatClient client = ChatClient.builder(chatModel)
        .defaultTools(crmTool, billingTool)
        .build();

// Khi ChatClient xử lý tập tool trùng tên, kỳ vọng lỗi xác thực
// danh mục thay vì chọn tùy ý một trong hai callback.
~~~

`CustomerLookup` và các service là kiểu do ứng dụng định nghĩa. Việc exception xảy ra ở lúc build client hay lúc tạo request có thể thay đổi theo API/version; test cần xác minh **nó fail trước khi có side effect**, không phụ thuộc dòng stack trace chính xác.

Nếu ứng dụng tự tạo low-level `ToolCallingChatOptions`, gọi API validation chính thức trên danh sách callback cuối cùng:

~~~java
List<ToolCallback> mergedCallbacks = List.of(crmTool, billingTool);

// Trước khi gắn vào ToolCallingChatOptions hoặc gọi ChatModel trực tiếp.
ToolCallingChatOptions.validateToolCallbacks(mergedCallbacks);
~~~

Ví dụ này minh họa điểm cần đặt validation; kiểm tra overload cụ thể của dependency trong dự án khi triển khai. Nếu API danh sách khác phiên bản, có thể dùng bước kiểm tra tên trùng do ứng dụng sở hữu ở mục 7. **Không dựa vào thứ tự array/map/bean để chọn “tool ưu tiên”.**

## 5. Tại sao .defaultTools(...) dễ tạo xung đột bất ngờ?

`ChatClient` có thể có tool mặc định và công cụ bổ sung theo từng request:

~~~java
ChatClient client = ChatClient.builder(chatModel)
        .defaultTools(localCustomerTools)
        .build();

String answer = client.prompt()
        .user(question)
        .tools(remoteMcpCustomerTools)
        .call()
        .content();
~~~

Dù code ở controller chỉ hiện `.tools(remoteMcpCustomerTools)`, tool mặc định từ builder vẫn tham gia tập callback request. Trong Spring AI 2.x, `.tools(...)` **bổ sung**, không thay thế `.defaultTools(...)`. Nếu local và remote cùng mang tên `getCustomer`, collision xuất hiện khi gộp ở request.

Chẩn đoán theo thứ tự:

1. Tool mặc định của client gồm những tool nào?
2. Tool được thêm bằng `.tools(...)` ở request cụ thể gồm những tool nào?
3. Có `ToolCallbackProvider` nào sinh tool vào một hoặc cả hai tập không?
4. Có cùng callback được đăng ký hai lần theo hai đường khác nhau?
5. Có custom advisor, registry, tool search hoặc dynamic callback resolver bổ sung thêm tên tool không?
6. Sau khi gộp, mỗi `ToolDefinition.name()` có duy nhất không?

Không xóa tất cả `defaultTools` một cách mù quáng: có thể làm hỏng flow của những request khác. Cách khắc phục đúng là **xác định ownership của tên tool**, thống nhất nơi đăng ký và áp dụng tên duy nhất có ý nghĩa.

## 6. Những nguồn công cụ cần đưa vào bản kê

Trong ứng dụng Spring AI có thể tồn tại:

- Method annotation `@Tool` của một instance Java: tên mặc định hoặc `name=...`.
- Callback tạo từ method qua `MethodToolCallback` hoặc factory `ToolCallbacks.from(...)`.
- Callback tạo bằng `FunctionToolCallback.builder(...)`.
- `ToolCallback` bean trong Spring context.
- `ToolCallbackProvider` có danh sách callback động.
- MCP client/provider từ một hoặc nhiều MCP server.
- Dynamic registry/DB-backed tool catalog và custom `ToolCallbackResolver`.
- Custom `ToolSearchToolCallingAdvisor` hoặc discovery/index cache giữ tên từ phiên cũ.

**Không phải mọi nguồn đều tự động được đưa vào mọi request.** Trong Spring AI 2.1, resolver mặc định có thể biết `ToolCallback` beans và `ToolCallbackProvider` beans, nhưng MCP providers được loại khỏi eager resolver discovery để tránh gọi mạng khi khởi tạo. MCP tools cần được wire rõ ràng vào `ChatClient` qua provider. Danh sách trong resolver và danh sách tool thực sự đính vào prompt **không giống nhau**.

Điều này giải thích hai triệu chứng đối lập:

- Resolver biết `searchInvoice` nhưng model không được công bố tool đó.
- Model được công bố callback MCP nhưng custom resolver hoặc low-level loop lại sử dụng registry khác.

Cần log nguồn xuất xứ của callback ở application registry (owner/provider/namespace/schema version) để dễ truy vết; log **tên và fingerprint metadata** thay vì raw arguments/credentials.

## 7. Phát hiện tên trùng một cách fail-fast

Đặt bước kiểm tra khi xây tập callback cuối cùng và trước khi gọi model. Không chờ tới lúc model trả tool call rồi mới phát hiện xung đột. Ví dụ Java:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.ai.tool.ToolCallback;

public final class ToolCatalogChecks {

    private ToolCatalogChecks() {}

    public static void requireUniqueNames(
            List<? extends ToolCallback> callbacks) {

        Map<String, List<ToolCallback>> byName = new LinkedHashMap<>();

        for (ToolCallback callback : callbacks) {
            String name = callback.getToolDefinition().name();
            if (name == null || name.isBlank()) {
                throw new IllegalStateException(
                        "Tool definition name is missing");
            }
            byName.computeIfAbsent(name, ignored -> new ArrayList<>())
                    .add(callback);
        }

        List<String> collisions = byName.entrySet().stream()
                .filter(entry -> entry.getValue().size() > 1)
                .map(Map.Entry::getKey)
                .toList();

        if (!collisions.isEmpty()) {
            throw new IllegalStateException(
                    "Duplicate tool definition names: " + collisions);
        }
    }
}
~~~

Đây là kiểm tra ở tầng ứng dụng, không thay thế `ToolCallingChatOptions.validateToolCallbacks(...)` khi API framework hỗ trợ. Đừng “khử trùng” bằng `Collectors.toMap(..., (a, b) -> a)`: cách đó âm thầm chọn callback đầu tiên và che giấu cấu hình sai.

Thực tế cần kèm **bảng provenance**:

| Name đã normalize | Source | Owner | Bean/provider | Risk | Schema fingerprint |
| --- | --- | --- | --- | --- | --- |
| `crm_getCustomer` | local `@Tool` | CRM | `crmTools` | read | `sha256:...` |
| `billing_getCustomer` | MCP `billing` | Billing | `billingMcpProvider` | read | `sha256:...` |
| `billing_refundPayment` | MCP `billing` | Billing | `billingMcpProvider` | write | `sha256:...` |

Bảng trên là ví dụ dữ liệu tổng hợp. Không ghi credentials hoặc raw request payload vào fingerprint/log. Fingerprint có thể tính trên biểu diễn chuẩn hóa của tool definition và schema; namespace/owner phải được xác minh ở registry do ứng dụng quản lý, không tin string do model tự gửi.

## 8. Ưu tiên namespace ổn định theo miền nghiệp vụ

Một cách đặt tên rõ nghĩa:

| Tên mơ hồ | Tên đề xuất | Ý nghĩa |
| --- | --- | --- |
| `getCustomer` | `crm_getCustomer` | Hồ sơ khách hàng CRM |
| `getCustomer` | `billing_getCustomer` | Tài khoản thanh toán |
| `search` | `docs_searchArticles` | Tìm tài liệu |
| `search` | `inventory_searchStock` | Tra cứu tồn kho |
| `updateStatus` | `orders_updateFulfillmentStatus` | Trạng thái xử lý đơn |
| `updateStatus` | `tickets_updateTicketStatus` | Trạng thái ticket hỗ trợ |

Không dùng tên dựa trên thứ tự phát hiện như `alt_1_getCustomer` làm hợp đồng lâu dài nếu danh mục đổi thường xuyên; thứ tự kết nối hoặc deployment có thể thay đổi. Một prefix có **ý nghĩa nghiệp vụ và ổn định** hỗ trợ kiểm thử routing, trace, kiểm toán và compatibility tốt hơn.

Đối với `@Tool` local, đặt tên trực tiếp:

~~~java
@Tool(
    name = "crm_getCustomer",
    description = "Đọc hồ sơ CRM theo customerId; không dùng cho billing.")
public CrmCustomer getCustomer(
        @ToolParam(description = "ID khách hàng CRM")
        String customerId,
        ToolContext context) {

    CallerContext caller = requireCaller(context);
    return crmService.readAuthorized(caller, customerId);
}
~~~

Đối với `FunctionToolCallback`, tên truyền vào builder là tool name:

~~~java
ToolCallback billingLookup = FunctionToolCallback
        .builder("billing_getCustomer", billingService::getCustomer)
        .description("Đọc tài khoản thanh toán theo customerId.")
        .inputType(CustomerLookup.class)
        .build();
~~~

Khi đổi tên tool đang được hội thoại, cache hay test dùng, phải cập nhật tool descriptions, golden cases, callback routing, audit và chiến lược xử lý conversation có tool call theo tên cũ. Không dùng alias cùng tên trỏ tới callback khác trong một khoảng rollout không kiểm soát.

## 9. MCP: prefix mặc định giải quyết trùng tên *giữa MCP servers*

Spring AI MCP Client Boot Starter 2.1 có `McpToolNamePrefixGenerator`. Khi không tự khai báo generator, `DefaultMcpToolNamePrefixGenerator` theo dõi tên giữa các MCP connection, chuẩn hóa ký tự đặc biệt và thêm prefix kiểu `alt_1_search` khi phát hiện trùng trong nhóm MCP legacy. Vì vậy, nếu hai MCP server cùng trả `search`, tên cuối có thể là `search` và `alt_1_search`.

Điểm dễ nhầm: generator mặc định này **không biết các method `@Tool` local**. Do đó, nếu một `@Tool(name="search")` local và một tool MCP cuối cùng cũng tên `search`, vẫn có collision khi gộp qua `ChatClient`. Không coi MCP auto-prefix là bộ quản lý namespace toàn ứng dụng.

Tài liệu Spring AI 2.1 cũng phân biệt **legacy MCP** và **modern MCP connections**:

- Legacy client dùng `McpToolNamePrefixGenerator`; `McpToolNamePrefixGenerator.noPrefix()` có thể gây xung đột nếu nhiều MCP servers trả cùng tên.
- Modern connection mặc định dùng dạng `<connection>_<tool>`, ví dụ `tickets_search`, và tùy biến bằng `McpModernToolNamePrefixGenerator`.
- Các loại filter/prefix generator của legacy **không tự áp dụng** cho modern connection. Cấu hình nhiều loại phải đi đúng API của loại connection.
- MCP tool có thể đổi danh sách, tên hoặc schema theo thông báo thay đổi; cần làm mới snapshot/index/cache.

Khi dùng prefix tự tạo, nhớ giới hạn ký tự và độ dài tên mà provider/model chấp nhận (ví dụ có giới hạn 64 ký tự trong nhiều trường hợp). Không cắt chuỗi tùy ý khiến hai tên khác nhau trở thành cùng một tên sau truncation; thêm hash/suffix ổn định hoặc fail validation.

## 10. Một ví dụ cấu hình MCP có kiểm soát

Để phân biệt tool của nhiều MCP server trong legacy MCP, có thể khai báo generator do ứng dụng quản lý:

~~~java
@Component
public final class DomainToolPrefixGenerator
        implements McpToolNamePrefixGenerator {

    private final ApprovedNamespaceRegistry approvedNamespaces;

    public DomainToolPrefixGenerator(
            ApprovedNamespaceRegistry approvedNamespaces) {
        this.approvedNamespaces = approvedNamespaces;
    }

    @Override
    public String prefixedToolName(
            McpConnectionInfo connectionInfo,
            McpSchema.Tool tool) {

        // Mapping server identity -> namespace do ứng dụng cấp.
        String namespace = approvedNamespaces.requireNamespace(
                connectionInfo.clientInfo().name());

        String name = namespace + "_" + tool.name();
        return validatedMcpToolName(name);
    }

    private static String validatedMcpToolName(String name) {
        if (!name.matches("[A-Za-z][A-Za-z0-9_]{0,63}")) {
            throw new IllegalArgumentException("Tên công cụ không hợp lệ");
        }
        return name;
    }
}
~~~

`approvedNamespaces` và `validatedMcpToolName(...)` là thành phần ứng dụng phải triển khai; ví dụ rút gọn nên không phải đoạn paste vào production nguyên xi. Validator phải phát hiện collision sau normalize/truncate, không tự “fix” bằng thứ tự runtime.

Có thể lọc tool không mong muốn bằng `McpToolFilter` (legacy) hoặc `McpModernToolFilter` (modern), ví dụ chỉ đưa tool read-only của một server vào catalog dùng cho request không được ghi. Nhưng filter **không tự cấp quyền**: callback/service/MCP server vẫn phải kiểm tra caller/tenant/resource.

Nếu backend MCP thay đổi danh sách tool theo user, cần xử lý session scope của MCP client: một shared MCP connection không đồng nghĩa danh sách tool được cô lập theo từng caller. Không dựa vào tên tool được công bố ở thời điểm khởi tạo làm quyền truy cập lâu dài.

## 11. Resolver trả sai callback: phải xác định nguồn dữ liệu nào được tra

Spring AI có interface:

~~~java
public interface ToolCallbackResolver {
    @Nullable
    ToolCallback resolve(String toolName);
}
~~~

Mặc định, Spring AI 2.1 có resolver tĩnh tìm từ `ToolCallback` beans và nhiều `ToolCallbackProvider` beans (loại trừ MCP provider khỏi eager discovery). Có thể thay bằng resolver riêng để tìm từ DB/registry. Nhưng **resolver chỉ trả callback theo tên**, không mang identity chứng minh người dùng có quyền trên một tài nguyên.

Một custom resolver có thể sai vì:

1. Nhận cùng tên từ hai provider nhưng lệnh `findFirst()` chọn sai.
2. Map các tool theo bean name thay vì `ToolDefinition.name()`.
3. Cache theo `toolName` nhưng không theo namespace/version/tenant/capability.
4. Dùng default callback khi không tìm thấy một tên hợp lệ.
5. Resolver rộng hơn request, cho phép tool ghi lọt vào luồng chỉ đọc.
6. Giữ callback cũ sau khi MCP provider bị rút hoặc schema thay đổi.
7. Trả callback có definition name khác tên được yêu cầu.
8. Resolver được tự khai báo nhưng thay thế bean framework và làm mất một số tool cần thiết.

**Điều tra theo bằng chứng:** log `requestedToolName`, `resolvedToolDefinition.name()`, source/owner, schema hash, catalog version, caller scope (dạng mã hóa/nhóm an toàn), và tool-call ID trong trace. Nếu tên được yêu cầu và tên callback khác nhau, đó là lỗi mapping cần từ chối, không phải “gọi gần đúng”.

## 12. Resolver có kiểm tra tên và fail closed

Một resolver ứng dụng có thể từ chối tên không tồn tại hoặc mâu thuẫn. Ví dụ pseudocode Java dễ chuyển thành implementation:

~~~java
public final class StrictCatalogResolver implements ToolCallbackResolver {

    private final Map<String, ToolCallback> byName;

    public StrictCatalogResolver(List<ToolCallback> callbacks) {
        ToolCatalogChecks.requireUniqueNames(callbacks);
        this.byName = callbacks.stream().collect(
            Collectors.toUnmodifiableMap(
                callback -> callback.getToolDefinition().name(),
                Function.identity()));
    }

    @Override
    public ToolCallback resolve(String toolName) {
        ToolCallback callback = byName.get(toolName);
        if (callback == null) {
            return null; // Không substitute bằng tên "gần nhất".
        }
        if (!toolName.equals(callback.getToolDefinition().name())) {
            throw new IllegalStateException(
                    "Resolver mapping mismatch");
        }
        return callback;
    }
}
~~~

Cần import các kiểu `List`, `Map`, `Collectors`, `Function` và Spring AI resolver/tool callback phù hợp. Resolver này cố ý không làm authorization theo caller vì chữ ký `resolve(String)` không nhận `ToolContext`. Quyền phải được kiểm tra ở **request tool selection** và **callback/service khi chạy**. Nếu cần resolver theo request/tenant, hãy thiết kế scope ở orchestration layer hoặc tạo resolver/controller quản lý snapshot đã được xác thực, không dựa vào biến thread-local ngẫu nhiên.

Không gọi callback trực tiếp chỉ vì resolver trả không null; đi qua cơ chế tool execution/exception mapping phù hợp với phiên bản Spring AI để bảo toàn schema, audit và tool response.

## 13. Resolver fallback: lỗi bảo mật dễ xuất hiện khi chữa sự cố

Property:

~~~properties
spring.ai.tools.resolution.fallback.enabled=false
~~~

Trong Spring AI 2.1, mặc định là `false`: `ToolCallingManager` chỉ thực thi những tool được gắn vào request. Nếu bật `true`, khi model gọi tên không có trong request, manager có thể tìm callback qua resolver ứng dụng. Điều này biến registry rộng thành tập tool **có thể thực thi nếu model nêu tên**, kể cả tool nhạy cảm.

Ví dụ rủi ro:

~~~text
Request chỉ gắn:
  docs_searchArticles

Resolver còn chứa:
  billing_refundPayment
  admins_deleteUser

Model hoặc prompt injection đề xuất:
  admins_deleteUser

fallback=false -> không thực thi tool ngoài request
fallback=true  -> có thể resolve tool đó nếu resolver cho phép
~~~

Tắt fallback là lựa chọn an toàn mặc định. Nếu bắt buộc bật để tương thích một luồng động, phải giới hạn resolver theo capability được cấp, kiểm tra policy/tenant ngay tại callback và có test xác minh tool nhạy cảm không thể bị thực thi từ request ngoài phạm vi.

Đặc biệt, **bật fallback không giải quyết trùng tên**. Nó có thể khiến sự cố tệ hơn: tool trước đây “not found” nay chạy nhầm callback toàn cục. Sửa nguồn đăng ký và namespace trước, đừng dùng fallback như phím “chữa mọi lỗi”.

## 14. Cập nhật catalog: tránh tên cũ và callback cũ bị lưu trong cache

Trong hệ thống nhiều tool, có thể tồn tại cache ở các tầng khác nhau:

| Lớp cache | Nội dung | Nếu không invalidate |
| --- | --- | --- |
| Tool metadata/catalog | Tên, mô tả, schema, risk tier | Model thấy definition cũ |
| Tool-search index | Tên tool được tìm theo query và session | Search trả tên đã đổi hoặc bị rút |
| Callback registry/resolver | Tool name → callback instance | Execution chọn implementation cũ |
| MCP tools/list | Tool do server công bố | Client chưa thấy tool mới/xóa |
| Conversation/tool transcript | Tool call từ các lượt trước | Model có thể tiếp tục đề xuất tên đã deprecated |
| Business result cache | Kết quả đọc dữ liệu | Trả thông tin sai người/tenant nếu key quá rộng |

Với mọi thay đổi tool name, owner hoặc schema, cần publish snapshot/catalog version mới, validate collision, invalidate index/resolver phù hợp và **ngăn execution của tool bị thu hồi ngay**. Không chờ TTL cho các thay đổi về authorization.

Tại thời điểm thực thi, kiểm tra caller/tenant và resource ACL theo trạng thái hiện tại; “tool đã nằm trong index hợp lệ hôm qua” không phải quyền vĩnh viễn. Đặc biệt với tool có side effect đang chờ xác nhận, nếu callback/schema/ý nghĩa tên đã thay đổi, bắt buộc xác minh lại hoặc yêu cầu người dùng duyệt lại.

## 15. Diagnostic runbook 10 bước khi production gọi sai tool

1. **Cô lập tác động:** nếu thấy side effect sai, tắt tool/capability qua feature flag, rút credential, đặt downstream deny policy và dừng retry tự động. Không chỉ sửa prompt.
2. **Lấy dấu vết tối thiểu:** request ID, trace ID, model/provider version, catalog version, session ID đã được bảo vệ, tool-call name + ID, thời điểm và mã outcome.
3. **Xác định đường thực thi:** `ChatClient` + `ToolCallingAdvisor`, `ChatModel.call()` trực tiếp hay custom manager? Có `ToolSearchToolCallingAdvisor` không?
4. **Liệt kê tập tool công bố thực tế:** gộp `defaultTools`, per-request `tools`, providers và names sau MCP prefix.
5. **Kiểm tra uniqueness:** phát hiện tên trùng ở tập request; không để map first-wins che dấu.
6. **Xác định callback thực thi:** đối chiếu resolved name, class/provider, owner, version, schema hash và downstream service từ span/audit.
7. **Kiểm tra fallback:** `spring.ai.tools.resolution.fallback.enabled` và custom manager flags; so với tool scope đã đính vào request.
8. **Kiểm tra cache/provider:** MCP tool listing, stale session index, registry refresh, connection state và schema đổi từ release gần nhất.
9. **Dựng test tái hiện không có side effect:** fake callbacks trả `CRM_MARKER`/`BILLING_MARKER`, cùng tên cũ, chạy qua đúng ChatClient/ChatModel path.
10. **Sửa và xác minh:** namespace và validation, re-index/rollout, test regression, restore traffic theo canary; giữ audit để đối soát side effect cũ.

Khi điều tra, **không hiển thị raw tool arguments, tài liệu khách hàng, access tokens hoặc internal secrets**. Tên tool có thể đưa vào metrics vì có danh mục hữu hạn, nhưng user/tenant ID và tool call ID nên chỉ dùng trong trace/audit có phân quyền thay vì Prometheus labels.


## 16. Kiểm thử đơn vị: phát hiện duplicate trước khi gọi model

Không cần API key hay kết nối MCP để kiểm tra nguyên tắc tên duy nhất. Tạo hai callback giả có cùng tên và khác nguồn:

~~~java
import java.util.List;
import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.function.FunctionToolCallback;

import static org.assertj.core.api.Assertions.*;

record CustomerLookup(String customerId) {}

class ToolCatalogChecksTest {

    @Test
    void shouldRejectTwoCallbacksWithSameModelVisibleName() {
        Function<CustomerLookup, String> crm =
                request -> "CRM_MARKER";
        Function<CustomerLookup, String> billing =
                request -> "BILLING_MARKER";

        ToolCallback local = FunctionToolCallback
                .builder("getCustomer", crm)
                .description("Hồ sơ CRM.")
                .inputType(CustomerLookup.class)
                .build();

        ToolCallback remoteEquivalent = FunctionToolCallback
                .builder("getCustomer", billing)
                .description("Tài khoản thanh toán.")
                .inputType(CustomerLookup.class)
                .build();

        assertThatThrownBy(() ->
                ToolCatalogChecks.requireUniqueNames(
                        List.of(local, remoteEquivalent)))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("getCustomer");
    }
}
~~~

Test không gọi model và không có side effect. Dùng `FunctionToolCallback` ở đây như hai nguồn giả lập để kiểm tra collision; nếu cần xác minh tích hợp MCP thực, thêm một bài integration test với MCP test server ở môi trường riêng.

Bổ sung test xác nhận **cùng callback không bị đăng ký hai lần**: nếu một bean được thêm qua `defaultTools` rồi lại thêm qua `tools(...)`, kết quả callback name có thể trùng; quy tắc nên fail fast ở boundary, hoặc giải quyết registration flow để một callback chỉ xuất hiện đúng một lần.

Một tên tool có thể vẫn duy nhất nhưng schema sai hoặc owner thay đổi. Vì thế ngoài uniqueness, test cần kiểm tra `toolName + namespace + schemaVersion + owner` theo snapshot đã phê duyệt.

## 17. Kiểm thử resolver không fallback sang callback cùng tên gần giống

Bài test trực tiếp một resolver nghiêm ngặt:

~~~java
@Test
void resolverMustReturnOnlyExactRegisteredName() {
    Function<CustomerLookup, String> crm =
            request -> "CRM_MARKER";

    ToolCallback callback = FunctionToolCallback
            .builder("crm_getCustomer", crm)
            .description("Tra cứu khách hàng CRM.")
            .inputType(CustomerLookup.class)
            .build();

    ToolCallbackResolver resolver =
            new StrictCatalogResolver(List.of(callback));

    assertThat(resolver.resolve("crm_getCustomer"))
            .isSameAs(callback);

    assertThat(resolver.resolve("billing_getCustomer"))
            .isNull();

    assertThat(resolver.resolve("getCustomer"))
            .isNull();
}
~~~

Một resolver không nên âm thầm bỏ prefix hoặc đổi tên để “chọn gần đúng” khi model trả tool chưa tồn tại. Nếu muốn tương thích tên cũ, dùng **alias mapping tường minh** có version và owner, kiểm tra rằng alias không trỏ tới hành động có phạm vi hoặc rủi ro khác. Với tool có side effect, việc đổi tên hoặc thay implementation trong khoảng đang chờ approval cần kiểm tra lại hợp đồng trước khi thực thi.

Test thêm trường hợp resolver có một callback tên thực tế khác key tra cứu: ví dụ registry map `crm_getCustomer → billing_getCustomer`. Resolver nên ném lỗi mapping, không trả callback đó. Test phải assert **không callback nào được gọi** trong path bị lỗi.

## 18. Kiểm thử ChatClient và raw ChatModel trên cùng bộ tool

Chỉ kiểm tra `ToolCatalogChecks` chưa đủ nếu ứng dụng còn một đường vào gọi model trực tiếp. Bộ integration test nên bao gồm:

| Đường vào | Dữ liệu thử | Kỳ vọng |
| --- | --- | --- |
| `ChatClient.defaultTools(local, remote)` | Cùng `getCustomer` | Từ chối duplicate trước execution |
| `ChatClient.defaultTools(local).prompt().tools(remote)` | Tên trùng giữa default và request | Từ chối merged tool set |
| `ChatModel.call(prompt)` với custom `ToolCallingChatOptions` | Hai callback cùng tên | Application validator chặn trước `call()` |
| `StaticToolCallbackResolver` | Tên chính xác | Trả đúng callback được phê duyệt |
| Resolver tìm tên không tồn tại | `typo_getCustomer` | Trả null / tool not found, không dùng fallback mơ hồ |
| Model gọi tool ngoài request | Resolver biết tool nhưng fallback=false | Không thực thi |
| Model gọi tên gần giống | `crm_getCustomer2` thay vì `crm_getCustomer` | Không tự đổi tên hoặc gọi tool khác |
| MCP server A và B cùng công bố `search` | Default prefix generator | Tên cuối khác nhau; không mất callback |
| Local và MCP cùng công bố `search` | Chưa namespace local/remote | Phát hiện collision ở merged request |
| Permission bị rút sau discovery | Index vẫn còn tên cũ | Service từ chối tại execution |
| Tool callback bị re-registered khi deploy | Snapshot khác version | Index và resolver refresh; không first-wins |

Khi test direct `ChatModel` với two-callback collision, **không cố gây ra side effect thật để chứng minh callback đầu tiên thắng**. Chỉ dùng callback giả trả marker khác nhau và giới hạn tool execution trong harness. Điều mong muốn sau khi sửa là collision **không thể đi đến execution**.

### Kiểm tra tên từ model và callback thật đã chạy

Khi dùng fake model, có thể dựng `AssistantMessage.ToolCall` với tên mong muốn rồi đi qua `ToolCallingManager` trong một flow controlled, nhưng cần giữ đúng `toolCallId`, arguments, `ToolResponseMessage` và chat options của phiên bản. Nếu muốn giảm độ phức tạp, test resolver và callback spy độc lập trước; sau đó chỉ chạy một integration test end-to-end qua `ChatClient` với model stub đã có sẵn trong dự án.

Quan trọng là test phải xác minh **callback instance thực tế**, không chỉ `finalAnswer.contains("CRM")`. Một model có thể đưa ra văn bản hợp lý dù code đã gọi nhầm service.

## 19. Lỗi tên trùng khi chuẩn hóa và giới hạn độ dài

Một số runtime/provider giới hạn ký tự cho tên tool. Nếu mã nguồn hoặc prefix generator có bước chuẩn hóa, những tên khác nhau ban đầu có thể trở thành giống nhau:

| Tên gốc | Sau chuẩn hóa có thể thành | Nguy cơ |
| --- | --- | --- |
| `crm-get-customer` | `crm_get_customer` | Đụng `crm_get_customer` vốn đã tồn tại |
| `billing/search` | `billing_search` | Đụng tên đã có underscore |
| Hai tên rất dài cùng prefix | Cùng chuỗi sau truncate | Collision chỉ xuất hiện sau khi triển khai |
| Hai MCP server đều cung cấp `search` | `search` / `alt_1_search` | Đổi server order có thể đổi tên được công bố nếu không namespace ổn định |
| Tên tool thay đổi theo tenant ID | Hàng nghìn tên | Cardinality lớn, tool catalog/metric mất kiểm soát |

Vì vậy, kiểm tra uniqueness phải chạy trên **tên cuối cùng gửi cho model**, không chỉ Java method name hoặc MCP raw tool name. Một bước normalize cần có kết quả tất định, kiểm thử collision và xử lý giới hạn độ dài.

Không đặt user ID, tenant ID hay ID tài nguyên vào tên tool để tránh collision. Tool name là API/capability ổn định; tenant/resource scope phải được xử lý bằng `ToolContext` và policy, không bằng việc tạo tool riêng cho từng user.

## 20. ToolSearch và cache: tên vẫn đúng nhưng callback đã thay

Khi dùng progressive tool discovery (ví dụ `ToolSearchToolCallingAdvisor` trong Spring AI 2.1), có thể xảy ra:

1. Session đã index `billing_getCustomer` của MCP server phiên bản 1.
2. Server deploy phiên bản 2 đổi schema, URL hoặc implementation.
3. Registry callback cập nhật nhưng session tool-search index chưa được làm mới.
4. Model nhận definition cũ, tạo arguments theo schema cũ.
5. Ứng dụng resolve tên hiện tại và gặp validation failure hoặc thực thi khác semantics.

Đây là **stale catalog/schema problem**, không hoàn toàn là duplicate name. Hướng xử lý:

- Gắn `catalogVersion`/`schemaFingerprint` và source provenance vào snapshot.
- Khi MCP list/schema đổi, invalidate/rebuild session index hoặc đảm bảo lazy refresh theo version.
- Không tiếp tục một paused approval với callback có ý nghĩa đã thay đổi mà chưa recheck.
- Chặn tool bị disable/thu hồi quyền ngay tại execution, kể cả cache vẫn hiển thị nó.
- Với multi-instance deployment, không chỉ evict index ở một JVM mà bỏ qua các replica khác.

Những phương án versioning, invalidation policy và alias là **thiết kế ứng dụng**, không phải quyền tự động được `ToolSearchToolCallingAdvisor` bảo đảm trong mọi topology.

## 21. Kiểm tra security: sai callback nguy hiểm hơn sai câu trả lời

Một collision có thể biến tool đọc an toàn thành tool ghi nếu tên tương tự hoặc registrar trả nhầm callback. Do đó cần có ranh giới bảo mật riêng:

- **Tool allowlist theo request/role:** không đính callback ghi cho request chỉ đọc.
- **Resolver fallback tắt:** không mở rộng sang toàn bộ callback beans khi tên chưa gắn vào request.
- **Authorization tại service:** xác minh `caller/action/resource/tenant` sau khi callback đã được chọn.
- **Phạm vi MCP:** chỉ kết nối server/namespace được phê duyệt; lọc tool nhạy cảm từ nguồn ngoài.
- **Kết quả tool có dấu nguồn đáng tin:** service/log biết callback nào thực thi, không tin model tự nói “đã gọi CRM”.
- **Ngăn exfiltration:** không cho callback gửi dữ liệu sang external URL/recipient không được phép.
- **Audit:** ghi source/owner, tool name, tool-call ID, request/trace ID, policy decision và side effect outcome.
- **Idempotency:** khi sai callback từng chạy và hệ thống retry, không nhân đôi side effect.
- **Secret-safe errors:** exception message/tool result không chứa key, internal path, raw SQL hoặc PII.

Một chi tiết MCP đáng lưu ý: `ToolContextToMcpMetaConverter` có thể chuyển dữ liệu từ `ToolContext` thành metadata gửi sang MCP server. Đừng giả định “không nằm trong JSON arguments cho model” có nghĩa mọi giá trị của `ToolContext` đều luôn nằm trong ranh giới trust của ứng dụng. Cấu hình converter allowlist/redaction và chỉ đưa những trường server MCP thực sự cần, không truyền cả authentication object hoặc credentials.

Nếu phát hiện đã gọi callback sai trên production, ngoài sửa name collision còn phải đối soát trạng thái nghiệp vụ, báo incident theo policy và thu hồi/rotation credential nếu có dấu hiệu rò rỉ. Không chỉ xóa cache để đóng sự cố.

## 22. Observability: thấy đúng công cụ mà không lộ dữ liệu

Spring AI phát Micrometer observation `spring.ai.tool` cho callback execution. Dùng nó để theo dõi tên tool và độ trễ. Với hệ thống có nhiều nguồn, bổ sung instrumentation ở boundary của ứng dụng:

~~~text
trace/span:
  requestId=...
  toolCallId=...
  requestedToolName=crm_getCustomer
  resolvedToolName=crm_getCustomer
  providerType=LOCAL
  sourceOwner=crm-service
  catalogVersion=catalog-43
  outcome=SUCCESS
~~~

Đây là **mô hình log/trace minh họa**, không phải toàn bộ attribute built-in. `toolCallId`/request ID chỉ nên nằm trong tracing hoặc audit có phân quyền, không dùng làm Prometheus metric tags. Có thể đưa `toolName` và `outcomeCode` vào metric khi danh mục tên có giới hạn.

Nếu `requestedToolName != resolvedToolName`, phải điều tra một trong ba nguyên nhân: alias mapping tường minh (được phê duyệt), custom resolver bug, hoặc kết quả stale registry. Đừng log toàn bộ arguments chỉ để chứng minh source; metadata definition và controlled marker trong test thường đủ.

Khi bật `logging.level.org.springframework.ai=DEBUG` để điều tra, chỉ bật trong khoảng giới hạn và kiểm tra quy tắc bảo vệ dữ liệu. Nội dung tool results, prompt hoặc headers có thể chứa thông tin riêng tư; giữ các tùy chọn export nội dung ở trạng thái tắt trừ khi có nhu cầu được phê duyệt và cơ chế redaction.

## 23. Quy trình sửa lỗi theo mức độ khẩn cấp

| Mức độ | Dấu hiệu | Hành động ưu tiên |
| --- | --- | --- |
| **P0/P1 — Side effect hoặc dữ liệu sai phạm vi** | Tool refund/delete/admin được thực thi sai, lộ dữ liệu | Chặn callback ở service, tắt capability, khóa credentials cần thiết, đối soát và mở incident |
| **P2 — Collision làm request fail** | `IllegalStateException` trước tool execution | Giữ fail-closed, rename namespace và thêm validation test |
| **P2 — Resolver không tìm thấy tool** | Tool call không chạy, trả not found | Kiểm tra attached tools, fallback default, prefix hiện hành và version |
| **P3 — Model chọn tool không phù hợp nhưng mỗi tên duy nhất** | Wrong-tool selection, không có collision | Cải thiện mô tả, schema và golden routing tests, giữ policy |
| **P3 — MCP cache chậm cập nhật** | Tool mới chưa thấy, tool đã rút vẫn trong search | Refresh/invalidate index, xem lifecycle và change notifications |

Phân biệt điều kiện “mô hình tự chọn sai trong hai tool có tên khác nhau” với “runtime đưa sai callback cho cùng một tên”. Cái đầu cần cải thiện discovery/description/model evaluation; cái sau cần sửa registry/resolution và thường có mức độ bảo mật cao hơn.

## 24. Checklist trước khi kết luận đã khắc phục

- [ ] Đã xác định đường thực thi `ChatClient` hay `ChatModel`/custom loop.
- [ ] Tên được kiểm tra trên **merged tool set cuối cùng** sau prefix/normalize.
- [ ] Không còn hai callback cùng `ToolDefinition.name()` trong một request.
- [ ] Tên tool được namespace theo domain/owner, không theo thứ tự đăng ký.
- [ ] Tên local `@Tool` và MCP tool không vô tình trùng nhau.
- [ ] Có test riêng cho collisions giữa `defaultTools` và per-request `tools`.
- [ ] Với low-level `ToolCallingChatOptions`, đã gọi validation hoặc ứng dụng tự kiểm tra uniqueness trước model.
- [ ] `ToolCallbackResolver.resolve(name)` trả đúng tool, không chọn tên gần đúng.
- [ ] Fallback vẫn tắt nếu không có requirement được duyệt; service enforce quyền dù bật.
- [ ] Đã xác minh prefix generator/filter của **legacy hoặc modern MCP** tương ứng.
- [ ] Đã xác minh đăng ký `ToolCallback` bean/`ToolCallbackProvider` đúng một lần và đúng owner.
- [ ] Đã xử lý stale session index/cache và schema version sau khi đổi tên.
- [ ] Có audit/trace cho requested vs resolved tool, owner, source và kết quả thực thi.
- [ ] Không log tool arguments, credentials hoặc raw `ToolContext` vào metrics.
- [ ] Có negative test: tool ngoài request, tool rút quyền, tenant khác, duplicate schema.
- [ ] Có test fail-closed trước khi thực hiện side effect.
- [ ] Nếu đã từng gọi sai callback, đã đối soát dữ liệu/side effect và xử lý incident.
- [ ] Đã chạy regression routing tests với hai nguồn có chức năng gần giống.
- [ ] Rollout có canary/rollback và xác minh mọi instance cùng catalog version.

## Tài liệu tham khảo

- [Spring AI 2.1 — Tool Calling: ToolCallback beans, tool resolution, local và MCP collisions](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1 — MCP Client Boot Starter: filtering và tool name prefix generation](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-client-boot-starter-docs.html)
- [Spring AI — Tool Callback Resolver và fallback configuration](https://docs.spring.io/spring-ai/reference/api/tools.html#_tool_resolution)
- [Spring AI — ChatModel Tool Calling (low-level)](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [Spring AI 2.1 — Tool Search Tool và session index](https://docs.spring.io/spring-ai/reference/api/tools/tool-search-tool.html)
- [Spring AI — Upgrade Notes, resolution fallback từ 2.0.1](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)
- [Spring AI — Tool Calling Observability](https://docs.spring.io/spring-ai/reference/observability/index.html)

**Kết luận:** trùng tên tool là lỗi của **hợp đồng định danh và định tuyến**, không phải vấn đề chỉ sửa bằng prompt. Khi nhiều nguồn cùng cung cấp `@Tool`/`ToolCallback`/MCP tool, hãy gán namespace ổn định, validate tập callback cuối cùng, để resolver fail closed, giữ fallback an toàn, kiểm tra quyền tại service và kiểm thử callback thực sự được gọi. Có như vậy hệ thống mới tránh được trường hợp mô hình đề xuất một công cụ nhưng ứng dụng âm thầm thực thi một công cụ khác.

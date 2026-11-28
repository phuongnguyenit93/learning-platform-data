# Phân biệt công cụ Java cục bộ và công cụ từ MCP server

Khi xây dựng ứng dụng Spring AI, cùng một mô hình có thể cần hai loại năng lực: gọi trực tiếp code nghiệp vụ đang nằm trong ứng dụng Java và sử dụng công cụ do một hệ thống khác cung cấp qua Model Context Protocol (MCP). Ví dụ, trợ lý chăm sóc khách hàng có thể đọc trạng thái đơn hàng bằng service nội bộ, rồi tìm chính sách đổi trả từ một MCP server quản lý tài liệu.

Hai loại công cụ có cùng mục đích đối với mô hình: cung cấp tên, mô tả, JSON Schema của tham số và kết quả để mô hình quyết định khi nào cần gọi. Nhưng chúng khác nhau về nơi thực thi, vòng đời đăng ký, giao thức, độ trễ, quyền truy cập và xử lý lỗi. Hiểu rõ ranh giới này giúp chọn kiến trúc thích hợp, tránh cấp công cụ quá rộng và bảo đảm hệ thống nghiệp vụ giữ trách nhiệm thực thi.

Bài học tập trung vào Spring AI **2.1.0**, nơi `ChatClient` cung cấp cả tool Java cục bộ lẫn tool từ MCP server qua một hợp đồng `ToolCallback` thống nhất. Khi dùng phiên bản khác, cần kiểm tra lại tên API, starter và tùy chọn MCP theo tài liệu của chính phiên bản đó.

## Sau bài học, bạn có thể

- Phân biệt method `@Tool`, `FunctionToolCallback` trong JVM hiện tại với tool do MCP server công bố.
- Mô tả vai trò của MCP client, MCP server, `tools/list` và `tools/call`.
- Hiểu cách `SyncMcpToolCallbackProvider` đưa MCP tools vào `ChatClient`.
- Đăng ký chung local tools và MCP tools trong cùng một request.
- Chọn transport STDIO hoặc Streamable HTTP theo cách triển khai hệ thống.
- Phân biệt `@Tool` ở ứng dụng AI với `@McpTool` ở ứng dụng đóng vai trò MCP server.
- Xử lý xung đột tên, độ trễ, lỗi mạng và giới hạn danh mục công cụ.
- Bảo vệ danh tính người dùng, `ToolContext` và dữ liệu nhạy cảm khi gọi MCP server.
- Thiết kế kiểm thử tách biệt phần local callback và phần giao tiếp MCP.

## Một điểm chung, hai nơi thực thi

Trong Spring AI, mô hình không gọi trực tiếp method Java hay HTTP endpoint. Ứng dụng gửi định nghĩa công cụ cho model; model trả về tên công cụ cùng JSON arguments; `ToolCallingAdvisor` và `ToolCallingManager` tìm callback phù hợp và thực thi.

Khác biệt lớn nhất là callback chạy công việc ở đâu:

| Tiêu chí | Công cụ Java cục bộ | Công cụ từ MCP server |
|---|---|---|
| Nơi thực thi | Method/function trong ứng dụng Java | Process hoặc dịch vụ chạy MCP server |
| Cách định nghĩa | `@Tool`, `MethodToolCallback`, `FunctionToolCallback` | MCP server công bố tool theo MCP schema |
| Cách cung cấp | Object `@Tool`, `ToolCallback` hoặc provider | MCP client phát hiện tool và tạo provider callback |
| Cách gọi nghiệp vụ | Callback gọi trực tiếp service Java | Callback chuyển thành MCP `tools/call` qua transport |
| Đầu vào cho model | `ToolDefinition` do Spring AI tạo | `ToolDefinition` chuyển từ metadata MCP |
| Phụ thuộc khi chạy | Bean, database, dependency của ứng dụng | Kết nối, tình trạng và quyền truy cập MCP server |
| Độ trễ bổ sung | Chủ yếu là xử lý và I/O nghiệp vụ | Có thêm discovery/protocol/transport và server |
| Quyền thực thi | Backend/service của ứng dụng kiểm tra | Cả MCP client và MCP server phải kiểm tra |
| Vòng đời | Theo Spring context và callback được cung cấp | Theo connection/session, discovery và lifecycle server |
| Cập nhật danh mục | Do code/cấu hình Java | Tool list có thể thay đổi từ MCP server |

MCP không đồng nghĩa công cụ luôn chạy ở máy chủ từ xa. Với transport **STDIO**, MCP client có thể khởi chạy một process ngay trên cùng máy và giao tiếp qua standard input/output. Process đó vẫn là một MCP server tách khỏi method Java đang gọi trong JVM. Với **Streamable HTTP**, MCP server thường được triển khai như một dịch vụ qua mạng.

## Luồng gọi tool của hai nguồn

~~~mermaid
flowchart TD
    U[Người dùng] --> C[ChatClient]
    C --> A[ToolCallingAdvisor]
    A --> M[Chat Model]
    M -->|tool name + JSON arguments| A
    A --> TM[ToolCallingManager]
    TM -->|Tên tool Java| L[MethodToolCallback / FunctionToolCallback]
    L --> S[Java business service]
    TM -->|Tên tool MCP| MC[MCP ToolCallback]
    MC --> CL[MCP client]
    CL -->|MCP tools/call| MS[MCP server]
    MS --> RS[Remote business service]
    S --> L
    RS --> MS
    MS --> CL
    CL --> MC
    L --> TM
    MC --> TM
    TM --> A
    A -->|Tool results + history| M
    M --> C
    C --> U
~~~

Điểm giao nhau là `ToolCallback`: callback mang `ToolDefinition` cho model và logic để thực thi khi model trả tool call. Vì vậy, `ChatClient` không cần một API chat riêng chỉ dành cho MCP. Nó có thể đưa cả hai nguồn vào một danh sách công cụ.

Sự thống nhất này chỉ diễn ra ở **lớp gọi công cụ**. Không có nghĩa hai nguồn có cùng mức độ tin cậy, quyền truy cập hoặc chi phí thực thi.

## Công cụ Java cục bộ: định nghĩa và gọi trong ứng dụng

Một method `@Tool` được cung cấp bằng object Java. Spring AI đọc annotation và tham số method để tạo schema mà model nhìn thấy; khi model yêu cầu gọi tool, callback thực thi method trong ứng dụng.

Ví dụ, một tool tra cứu trạng thái đơn hàng:

~~~java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.ai.chat.model.ToolContext;

@Component
public class LocalOrderTools {

    private final OrderService orderService;

    public LocalOrderTools(OrderService orderService) {
        this.orderService = orderService;
    }

    @Tool(
            name = "localOrderStatus",
            description = "Tra cứu trạng thái đơn hàng được phép xem"
    )
    public OrderStatus localOrderStatus(
            @ToolParam(description = "Mã đơn hàng") String orderId,
            ToolContext toolContext) {

        String tenantId =
                (String) toolContext.getContext().get("tenantId");
        String userId =
                (String) toolContext.getContext().get("userId");

        return orderService.findVisibleOrder(
                tenantId, userId, orderId
        );
    }
}
~~~

Trong ví dụ này, `OrderService` và `OrderStatus` là kiểu nghiệp vụ của ứng dụng. Khi chạy, callback không cần một MCP server: nó gọi `orderService` trực tiếp trong JVM. Nhưng nếu service gọi database hoặc API ngoài, I/O đó vẫn có thể chậm hoặc thất bại.

Mô hình chỉ tạo `orderId` theo JSON Schema. `tenantId` và `userId` được backend cung cấp qua `ToolContext`, và service phải kiểm tra quyền xem đơn hàng trước khi trả dữ liệu.

### Local tool từ lambda hoặc method reference

Khi không muốn viết một method `@Tool`, có thể tạo callback từ function:

~~~java
FunctionToolCallback lookupTool =
        FunctionToolCallback.builder(
                        "lookupOrder",
                        orderQueryService::lookup
                )
                .description("Tra cứu trạng thái đơn hàng theo mã")
                .inputType(OrderLookupRequest.class)
                .build();
~~~

`OrderLookupRequest` là DTO đầu vào và `orderQueryService.lookup(...)` trả DTO đồng bộ. Đây vẫn là local tool vì function được gọi trực tiếp trong ứng dụng. Việc callback truy vấn HTTP ở bên trong không biến nó thành một MCP tool; MCP là giao thức giữa một client và một MCP server, không phải cách gọi tùy ý tới một REST API.

## Công cụ từ MCP server: phát hiện và gọi qua giao thức

MCP server công bố các khả năng chuẩn hóa. Đối với tool, MCP client thường thực hiện hai bước:

1. **Discovery:** gọi `tools/list` để nhận danh sách tool cùng tên, mô tả và input schema.
2. **Invocation:** gọi `tools/call` với tên tool và JSON arguments khi model yêu cầu công cụ đó.

Spring AI MCP client starter quản lý transport, client và việc chuyển MCP tools thành các callback phù hợp với Spring AI. Với client đồng bộ, starter có thể tạo bean `SyncMcpToolCallbackProvider`; với cấu hình client bất đồng bộ, provider tương ứng là `AsyncMcpToolCallbackProvider`.

~~~mermaid
sequenceDiagram
    participant App as Spring AI App
    participant Provider as MCP ToolCallbackProvider
    participant Server as MCP Server
    participant Model as Chat Model

    App->>Provider: Lấy danh sách tool dùng cho request
    Provider->>Server: MCP tools/list (khi cần)
    Server-->>Provider: Tool definitions và input schemas
    Provider-->>App: ToolCallbacks
    App->>Model: Chat request + tool definitions
    Model-->>App: Tool call: tên + arguments
    App->>Provider: ToolCallback.call(input, context)
    Provider->>Server: MCP tools/call
    Server-->>Provider: CallToolResult
    Provider-->>App: Tool result
    App->>Model: Kết quả tool để tổng hợp câu trả lời
~~~

Callback MCP là adapter ở phía ứng dụng AI. Nó không tự di chuyển code của MCP server sang JVM hiện tại. MCP server vẫn kiểm soát handler, quyền truy cập và kết quả thực thi của mình.

MCP cũng hỗ trợ *resources* và *prompts*; đây là các loại khả năng khác trong giao thức. Đưa một `ToolCallbackProvider` vào `ChatClient.tools(...)` là cung cấp **tools**, không đồng nghĩa tự đưa mọi resource hoặc prompt MCP vào nội dung chat.

## Cấu hình Spring AI làm MCP client

### Thêm MCP client starter

Với Maven, thêm dependency MCP client trong ứng dụng sử dụng tool:

~~~xml
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>spring-ai-starter-mcp-client</artifactId>
</dependency>
~~~

Dependency và phiên bản Spring AI cần được quản lý nhất quán với Spring AI BOM của dự án. Starter chuẩn hỗ trợ STDIO và các transport HTTP dùng JDK HttpClient. Nếu ứng dụng muốn WebFlux transport cho SSE/Streamable HTTP, dùng `spring-ai-starter-mcp-client-webflux` tương ứng.

### Cấu hình một kết nối Streamable HTTP

Ví dụ `application.yml` cho một MCP server quản lý tài liệu tri thức:

~~~yaml
spring:
  ai:
    mcp:
      client:
        enabled: true
        type: SYNC
        request-timeout: 5s
        toolcallback:
          enabled: true
        streamable-http:
          connections:
            knowledge:
              url: https://mcp.internal.example
              endpoint: /mcp
~~~

`https://mcp.internal.example` chỉ là địa chỉ minh họa; cần thay bằng MCP server thật và cấu hình xác thực cho môi trường triển khai. Trong ví dụ này, `knowledge` là tên kết nối trong Spring AI, `/mcp` là endpoint HTTP của server.

`spring.ai.mcp.client.type` có thể là `SYNC` hoặc `ASYNC` nhưng starter yêu cầu các client cùng một loại; không phối hợp cả hai loại trong cùng cấu hình tự động. Với `SYNC`, dùng `SyncMcpToolCallbackProvider` để tích hợp tool; dùng `ASYNC` khi ứng dụng được cấu hình tương ứng và muốn `AsyncMcpToolCallbackProvider`.

`spring.ai.mcp.client.request-timeout` giới hạn thời gian request MCP theo client. Nó không tự giới hạn toàn bộ vòng tool calling gồm nhiều lần gọi model và nhiều tool.

### STDIO dùng cho process cục bộ

Nếu MCP server được đóng gói thành một chương trình riêng, ứng dụng có thể khởi chạy bằng STDIO:

~~~yaml
spring:
  ai:
    mcp:
      client:
        type: SYNC
        stdio:
          connections:
            local-knowledge:
              command: java
              args:
                - -jar
                - /opt/mcp/knowledge-server.jar
~~~

Ở đây MCP server chạy như một process được gọi qua stdin/stdout. Nó có thể nằm trên cùng máy với ứng dụng nhưng không phải một Spring bean mà local `@Tool` gọi trực tiếp.

Trên Windows, các lệnh dạng `npx.cmd` hoặc `npm.cmd` cần chạy qua wrapper `cmd.exe /c` do cách Java `ProcessBuilder` khởi chạy file batch. Không tự thêm `cmd.exe` cho một executable Java thông thường.

Với STDIO, cần kiểm soát đường dẫn executable, quyền của process và các thư mục mà server được phép đọc/ghi. Không cho model hoặc input của người dùng tự chọn lệnh shell để chạy MCP server.

## Đưa MCP tools vào ChatClient

Spring AI tự động cấu hình MCP client và provider khi starter đã bật, nhưng **không tự gắn toàn bộ MCP tools vào mọi ChatClient**. Danh sách MCP tools có thể phải được lấy từ server qua mạng; ứng dụng cần chọn rõ khi nào provider được sử dụng.

Ví dụ một service dùng cả tool cục bộ và MCP tool:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.mcp.SyncMcpToolCallbackProvider;

@Configuration(proxyBeanMethods = false)
public class AssistantConfiguration {

    @Bean
    ChatClient assistantChatClient(ChatModel chatModel) {
        return ChatClient.builder(chatModel).build();
    }
}

@Service
public class AssistantService {

    private final ChatClient chatClient;
    private final LocalOrderTools localOrderTools;
    private final SyncMcpToolCallbackProvider mcpTools;

    public AssistantService(
            ChatClient chatClient,
            LocalOrderTools localOrderTools,
            SyncMcpToolCallbackProvider mcpTools) {
        this.chatClient = chatClient;
        this.localOrderTools = localOrderTools;
        this.mcpTools = mcpTools;
    }

    public String answer(String question, CurrentUser user) {
        return chatClient.prompt()
                .user(question)
                .tools(localOrderTools, mcpTools)
                .toolContext(Map.of(
                        "tenantId", user.tenantId(),
                        "userId", user.id()
                ))
                .call()
                .content();
    }
}
~~~

`CurrentUser` là kiểu minh họa cho danh tính được backend xác thực. Khi request cần tra cứu đơn hàng, model có thể chọn `localOrderStatus`. Khi cần tìm tài liệu, model có thể chọn tool được công bố từ MCP server `knowledge`. `ToolCallingAdvisor` điều phối cả hai thông qua danh sách callback của request.

Trong cấu hình Spring AI 2.1.0, phương thức `.tools(...)` có thể nhận object chứa `@Tool`, `ToolCallback` và `ToolCallbackProvider`, đồng thời hỗ trợ kết hợp nhiều nguồn trong cùng request. Phải bảo đảm tên tool sau khi hợp nhất không trùng nhau.

Nếu MCP tools thực sự phù hợp với **mọi** request dùng cùng ChatClient, có thể dùng:

~~~java
ChatClient client = ChatClient.builder(chatModel)
        .defaultTools(localOrderTools, mcpTools)
        .build();
~~~

Với công cụ ghi dữ liệu hoặc công cụ có quyền nhạy cảm, thường nên chọn theo từng request sau khi xác định user, tenant và nghiệp vụ. Chỉ đặt vào `defaultTools(...)` những công cụ phù hợp với mọi người dùng của client đó.

### Vì sao cần truyền provider thay vì lưu danh sách callback một lần?

Provider có thể lấy danh sách tool từ MCP server lúc request cần dùng. Không nên gọi `mcpTools.getToolCallbacks()` ở startup rồi lưu mãi trong một bean nếu danh sách tool, credential hoặc client scope có thể thay đổi theo request.

Điều này đặc biệt quan trọng với kết nối theo protocol MCP mới có `client-scope=PER_REQUEST`. Các callback lấy ra từ một lần resolve có thể gắn với client và danh tính của chính lần đó. Truyền provider cho `ChatClient` để Spring AI resolve theo thời điểm và phạm vi thích hợp.

## Khi bạn là bên cung cấp MCP server

Ứng dụng Java có thể đứng ở phía **server** để công bố công cụ cho các ứng dụng AI khác. Đó là trách nhiệm khác với việc viết local `@Tool`.

Ví dụ Maven dependency cho MCP server WebMVC:

~~~xml
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>spring-ai-starter-mcp-server-webmvc</artifactId>
</dependency>
~~~

Trong ứng dụng server, dùng `@McpTool` và `@McpToolParam`:

~~~java
import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.ai.mcp.annotation.McpToolParam;

@Component
public class KnowledgeMcpTools {

    private final KnowledgeService knowledgeService;

    public KnowledgeMcpTools(KnowledgeService knowledgeService) {
        this.knowledgeService = knowledgeService;
    }

    @McpTool(
            name = "searchKnowledge",
            description = "Tìm tài liệu hướng dẫn nghiệp vụ"
    )
    public List<DocumentHit> searchKnowledge(
            @McpToolParam(description = "Cụm từ cần tìm") String query) {
        return knowledgeService.search(query);
    }
}
~~~

`KnowledgeService` và `DocumentHit` là kiểu ví dụ. Spring AI MCP server starter phát hiện bean có annotation MCP, tạo tool schema và đăng ký handler phía server. MCP client khác có thể discover và gọi tool này qua protocol/transport được cấu hình.

Chú ý:

- `@Tool` khai báo method cho **Spring AI ChatClient** sử dụng cục bộ.
- `@McpTool` khai báo method của **MCP server** để client bên ngoài discover và gọi.
- Cùng một lớp nghiệp vụ có thể được bọc bởi cả hai adapter nếu cần, nhưng mỗi adapter phải được cấu hình và phân quyền theo phạm vi của mình.
- Đặt annotation `@Tool` vào một Spring bean không tự tạo MCP endpoint công khai.

Một server HTTP MCP cần cấu hình protocol phù hợp, ví dụ `STREAMABLE` cho phiên bản starter hỗ trợ, cùng security boundary của HTTP endpoint. Starter MCP server không tự cấp đầy đủ authentication/authorization cho endpoint HTTP; hãy dùng Spring Security hoặc gateway và kiểm tra quyền tại service.

Từ Spring AI 2.0, MCP annotation được đưa vào package `org.springframework.ai.mcp.annotation.*`. Code cũ dùng `org.springaicommunity.mcp.annotation.*` cần cập nhật import khi nâng cấp lên 2.x.

## Khác biệt quan trọng về bảo mật

### Model không phải người thực thi có quyền

Model chỉ quyết định **yêu cầu** gọi một tool từ những định nghĩa ứng dụng cung cấp. Nó không có quyền tự chạy method Java hoặc gửi `tools/call` đến MCP server. Ứng dụng AI quyết định tool nào được cung cấp, còn backend/service chịu trách nhiệm kiểm tra quyền, xác thực đầu vào và giới hạn side effect.

Với local tool, kiểm tra quyền trong service gọi trực tiếp. Với MCP tool, có thêm một ranh giới trust: MCP client chuyển yêu cầu đến MCP server, vì vậy server cũng phải xác thực caller và áp dụng authorization cho tài nguyên của mình.

Không dựa vào prompt như “chỉ gọi tool này khi được phép” để thay thế kiểm tra quyền. Mọi yêu cầu gọi tool cần được xem là đầu vào không đáng tin cho đến khi backend kiểm tra.

### ToolContext được xử lý khác khi qua MCP

Đối với local `@Tool`, `ToolContext` chứa dữ liệu nội bộ do ứng dụng cung cấp; nó không xuất hiện trong tool definition hay JSON arguments mà model tạo.

Nhưng với MCP client starter, bộ chuyển đổi mặc định `ToolContextToMcpMetaConverter.defaultConverter()` có thể đưa các entry của `ToolContext` sang `_meta` của MCP `tools/call` (trừ key trao đổi nội bộ và các giá trị null). Nghĩa là dữ liệu **không gửi cho model** vẫn có thể được gửi tới **MCP server**.

Nếu cùng request có cả local và MCP tools, cần quyết định rõ dữ liệu nào được phép rời khỏi ứng dụng. Ví dụ `tenantId`, `userId`, access token, internal trace hoặc object nghiệp vụ không nên tự động chuyển toàn bộ cho một MCP server bên thứ ba.

Có thể tắt việc chuyển context sang MCP metadata:

~~~java
import org.springframework.ai.mcp.ToolContextToMcpMetaConverter;

@Bean
ToolContextToMcpMetaConverter toolContextToMcpMetaConverter() {
    return ToolContextToMcpMetaConverter.noOp();
}
~~~

Khi cần metadata, tự viết converter allowlist chỉ chuyển những trường được MCP server chấp nhận và có ý nghĩa:

Chọn **một** trong hai cách: `noOp()` ở trên hoặc converter allowlist ở dưới. Không đăng ký cả hai bean cùng loại nếu không chủ động chọn bean theo Spring.

~~~java
@Bean
ToolContextToMcpMetaConverter toolContextToMcpMetaConverter() {
    return context -> {
        Object requestId = context.getContext().get("requestId");
        return requestId instanceof String id
                ? Map.of("requestId", id)
                : Map.of();
    };
}
~~~

Chỉ đưa `requestId` vào allowlist nếu policy cho phép chia sẻ nó với server. Không tự động gửi access token trong `_meta`; credential cho HTTP MCP nên được truyền bằng cơ chế xác thực transport đã cấu hình.

Đây là điểm dễ nhầm: **ToolContext không được gửi đến model** nhưng **có thể đi đến MCP server** tùy converter.

### Không dùng MCP session làm ranh giới user/tenant

Với MCP legacy client được auto-configure, connection/session thường được chia sẻ giữa các request dùng cùng bean. Credential riêng cho request có thể được truyền qua transport, nhưng session bên dưới không mặc nhiên riêng cho người dùng. Nếu MCP server lưu trạng thái theo session hoặc trả `tools/list` tùy user, một shared session có thể tạo ra rủi ro lẫn ngữ cảnh hoặc danh sách tool.

Với MCP protocol mới `2026-07-28` trong Spring AI 2.1.0, kết nối Streamable HTTP có `protocol=MODERN` và `client-scope=PER_REQUEST` mặc định; mỗi request resolve tool với client riêng. Có thể chọn `SHARED` khi dùng danh tính service account hoặc `CUSTOM` cho cách quản lý theo người dùng. Các tùy chọn này yêu cầu phiên bản MCP Java SDK và khả năng tương thích server phù hợp.

Không thay đổi `protocol=MODERN` chỉ để có tính năng mới nếu server chưa hỗ trợ. Hãy phân biệt cơ chế legacy shared session với modern per-request client khi thiết kế multi-tenant.

### Chỉ đưa các MCP tools cần thiết vào namespace

Một MCP server có thể công bố cả tool đọc và tool ghi. Việc client kết nối thành công không có nghĩa tất cả tool đó an toàn cho mọi request.

Spring AI hỗ trợ lọc tool bằng `McpToolFilter` cho kết nối legacy. Ví dụ minh họa một allowlist đơn giản:

~~~java
import org.springframework.ai.mcp.McpToolFilter;

@Bean
McpToolFilter mcpToolFilter() {
    Set<String> allowed = Set.of(
            "searchKnowledge",
            "getPublicPolicy"
    );

    return (connection, tool) ->
            allowed.contains(tool.name());
}
~~~

`McpToolFilter` chỉ quyết định tool nào được expose qua provider; đó là giới hạn diện tích tiếp xúc, không thay thế authorization của MCP server. Với kết nối hiện đại, dùng `McpModernToolFilter` tương ứng vì legacy filter không tự áp dụng cho modern tool.

Nên kết hợp bộ lọc và chọn `.tools(...)` theo request. Với tool nhạy cảm, cần chính sách xác nhận hoặc approval ở tầng orchestration, và kiểm tra quyền bắt buộc khi server thực thi.

## Xử lý trùng tên khi dùng cả local và MCP tools

Tên tool là khóa model sử dụng để yêu cầu thực thi. Nếu local tool và MCP tool cùng có tên `search`, ứng dụng không thể xác định ý nghĩa chỉ từ tên đó nếu không có quy tắc quản lý namespace.

Spring AI có bộ tạo prefix tên tool cho các MCP server. Với legacy tools, `DefaultMcpToolNamePrefixGenerator` xử lý tên trùng giữa các kết nối MCP. Với modern tools, tên mặc định có tiền tố kết nối, ví dụ `knowledge_search`.

Bộ tạo prefix của MCP không tự biết các local `@Tool` đã đăng ký. Vì vậy cần kiểm tra cả namespace sau khi gộp:

- Đặt tên local có chủ đích, ví dụ `localOrderStatus`.
- Dùng tên hoặc prefix rõ nguồn cho MCP tools, ví dụ `knowledge_search`.
- Nếu cần, lọc tool có tên trùng trước khi cung cấp.
- Kiểm tra tên trong danh sách cuối cùng sau khi resolve provider.

`ChatClient` 2.1.0 xác thực danh sách callback đã gộp và báo `IllegalStateException` khi có tên trùng. Nếu bỏ qua ChatClient và tự ghép callback qua `ToolCallingChatOptions`/`ChatModel` thấp hơn, cần tự gọi cơ chế xác thực tên tương ứng; nếu không, callback trùng tên có thể được chọn theo thứ tự và gọi nhầm nguồn.

## Độ trễ, lỗi và quan sát

Một local method có thể vẫn phải gọi database hoặc HTTP API, nhưng không có thêm lớp MCP client/server. Với MCP tools, đường đi có thể bao gồm discovery, xác thực, thiết lập kết nối, JSON-RPC, xử lý tại server và trả kết quả.

| Tình huống | Local tool | MCP tool |
|---|---|---|
| Tool không tồn tại | Lỗi cấu hình callback/name/schema | Tool bị bỏ trong `tools/list`, đổi tên hoặc server thay đổi |
| Dependency lỗi | Exception từ Java service | Có thể là lỗi transport, HTTP, MCP protocol hoặc tool error |
| Timeout | Giới hạn ở service/client nội bộ | Giới hạn ở MCP request và service phía server |
| Mất kết nối | Tùy dependency ứng dụng | Client không thể gọi hoặc discover MCP server |
| Danh mục thay đổi | Thường thay code/cấu hình | Server thay danh sách tool và client cần cập nhật |
| Chẩn đoán | Trace của method/service local | Cần trace xuyên MCP client, transport và MCP server |

Cấu hình `spring.ai.mcp.client.request-timeout` giúp đặt giới hạn một request MCP. Với end-to-end tool calling, vẫn cần deadline toàn request bao gồm nhiều lượt gọi model, các tool và retry.

Nếu MCP tool thực hiện side effect như tạo đơn hàng hoặc hoàn tiền, phải có operation ID/idempotency key phía service. Timeout từ MCP client không chứng minh MCP server đã không thực hiện thao tác. Khi retry, gửi cùng operation ID hoặc đối soát trước khi thực hiện lại.

Khi quan sát, nên ghi lại `requestId`, tên tool sau prefix, nguồn (LOCAL hoặc MCP), MCP connection name, thời gian discovery/call, kết quả và nhóm lỗi. Không log dữ liệu nhạy cảm trong JSON arguments hoặc `_meta`. Với nhiều provider, cần đánh dấu rõ callback đến từ server nào để điều tra lỗi và bảo mật.

## Cách chọn trong một hệ thống thật

| Nhu cầu | Chọn ưu tiên | Lý do |
|---|---|---|
| Method Java đơn giản, service trong cùng ứng dụng | Local `@Tool` | Ít cấu hình, dễ test và gọi trực tiếp |
| Lambda hoặc method reference có DTO rõ ràng | `FunctionToolCallback` | Không cần tạo annotation method riêng |
| Một hệ thống công bố tool cho nhiều ứng dụng AI khác nhau | MCP server | Có giao thức discovery/invocation chuẩn |
| Tích hợp hệ thống khác ngôn ngữ hoặc process độc lập | MCP client/server | Tách vòng đời và chuẩn hóa hợp đồng |
| Tool cần đặc quyền dữ liệu nội bộ | Local hoặc MCP có ranh giới bảo mật chặt | Chọn theo nơi đặt quyền và dữ liệu |
| Công cụ thay đổi độc lập với phiên bản ứng dụng AI | MCP server | Catalog có thể do dịch vụ khác quản lý |
| Mỗi user/tenant nhìn thấy bộ tool khác nhau | Lựa chọn theo request, scope client phù hợp | Tránh dùng danh mục và credential chung |
| Tool phục vụ thao tác ghi quan trọng | Chọn theo nơi kiểm soát transaction/idempotency | Quyền và chống lặp đặt tại service thực thi |

Không cần đưa mọi local tool thành MCP server. MCP hữu ích khi cần giao thức chuẩn, chia sẻ capability giữa ứng dụng hoặc tách dịch vụ. Local tool phù hợp khi logic Java đã nằm trong ứng dụng và không có nhu cầu phơi bày nó ra một giao diện MCP độc lập.

## Kiểm thử hai lớp tích hợp

Kiểm thử nên tách hợp đồng local callback khỏi kết nối MCP, rồi mới kiểm thử request có cả hai.

### Test local tool

Với `LocalOrderTools`, mock `OrderService` rồi kiểm tra:

- `@Tool` có tên, mô tả và schema đúng.
- JSON `orderId` được chuyển thành đối số Java chính xác.
- `tenantId`/`userId` lấy từ context do backend tạo.
- Service thực hiện phân quyền và trả DTO đúng.
- Lỗi validation, unauthorized hoặc timeout được xử lý an toàn.

Không cần khởi động MCP server chỉ để test một local method.

### Test MCP tool callback

Dùng một MCP server giả hoặc server test chạy trong môi trường cô lập. Kiểm tra:

- Kết nối được và danh sách `tools/list` có tool dự kiến.
- Tên/mô tả/input schema từ MCP được chuyển chính xác thành callback definition.
- Khi gọi callback, MCP server nhận đúng `tools/call` và arguments.
- Lỗi tool, lỗi giao thức, timeout, 401/403 và server ngắt kết nối được xử lý rõ ràng.
- Provider không expose tool đã bị loại bằng filter.
- `ToolContextToMcpMetaConverter` không gửi thông tin cấm tới `_meta`.

Với modern connection, thêm test cho scope theo request và user identity; với legacy connection, test shared-session không làm lộ tool list, state hoặc dữ liệu giữa tenant.

### Test phối hợp local + MCP

Dùng model giả có hai lần gọi tool hoặc kiểm tra danh sách callback ở request:

1. Đăng ký local `localOrderStatus` và MCP `knowledge_search`.
2. Kiểm tra hai tên tool là duy nhất và định nghĩa đúng.
3. Mô phỏng model gọi local tool; xác minh local service chạy một lần.
4. Mô phỏng model gọi MCP tool; xác minh server test nhận một `tools/call`.
5. Đảm bảo tool results được gửi lại model trước câu trả lời cuối.
6. Thử MCP server không khả dụng; local tool không bị tự động cấp thêm quyền hoặc gửi lệnh sai.
7. Thử tool có cùng tên từ hai nguồn và xác minh ứng dụng từ chối ở bước cấu hình request.

Nếu ứng dụng có tool ghi dữ liệu, test thêm idempotency, xác nhận người dùng và authorization tại service thực thi. Model giả có thể giúp test vòng tool calling mà không cần chi phí gọi provider thật.

## Những nhầm lẫn thường gặp

- **Coi MCP tool là một method Java trong cùng JVM:** tool MCP chạy ở server/process được kết nối qua giao thức.
- **Coi REST API bất kỳ là MCP server:** MCP cần các thông điệp và hợp đồng protocol như `tools/list`, `tools/call`.
- **Cho rằng cài MCP client starter là đủ để model thấy mọi tool:** phải gắn provider rõ ràng bằng `.tools(...)` hoặc `.defaultTools(...)`.
- **Coi `@Tool` và `@McpTool` là một annotation:** chúng phục vụ hai vai trò khác nhau trong ứng dụng AI và MCP server.
- **Coi tool được quảng bá là tool đã được phân quyền:** client/server vẫn phải xác thực caller và kiểm tra quyền.
- **Coi `ToolContext` là dữ liệu không rời ứng dụng:** default MCP converter có thể gửi nó qua `_meta`.
- **Dùng legacy shared MCP session như session riêng cho từng user:** dễ lẫn tool listing hoặc trạng thái khi server phụ thuộc session.
- **Tin MCP prefix sẽ tự xử lý tên trùng với local tool:** phải kiểm tra cả danh sách callback sau khi hợp nhất.
- **Dùng `getToolCallbacks()` một lần rồi cache mãi:** có thể sai khi catalog, credential hoặc client scope thay đổi.
- **Chỉ đặt timeout cho MCP client:** deadline toàn hội thoại và timeout nghiệp vụ vẫn phải quản lý riêng.
- **Coi MCP transport error là bảo đảm thao tác chưa xảy ra:** side effect có thể đã được commit ở server, cần idempotency hoặc đối soát.
- **Tin MCP filter thay thế authorization:** filter chỉ giảm tool được quảng bá; server vẫn chịu trách nhiệm bảo vệ dữ liệu.

## Checklist trước khi triển khai

- [ ] Đã xác định tool chạy trong JVM hay được công bố từ MCP server.
- [ ] Local tool có `@Tool` hoặc callback rõ ràng, service kiểm tra quyền.
- [ ] MCP client dùng đúng starter, transport và protocol version.
- [ ] MCP provider được gắn tường minh vào request hoặc default tools.
- [ ] Tên tool sau khi hợp nhất local + MCP không trùng nhau.
- [ ] Danh sách tool được lọc theo phạm vi nghiệp vụ và quyền người dùng.
- [ ] MCP server có xác thực transport và authorization tại handler/service.
- [ ] `ToolContext` được kiểm soát trước khi chuyển sang MCP `_meta`.
- [ ] Multi-tenant không dựa vào legacy shared session làm ranh giới danh tính.
- [ ] Có timeout, deadline, retry policy và idempotency cho thao tác ghi.
- [ ] Log/trace phân biệt LOCAL và MCP theo connection/tool name.
- [ ] Có unit test local tool, integration test MCP và test phối hợp hai nguồn.

## Ghi nhớ khi thiết kế

Local `@Tool` hoặc `FunctionToolCallback` gọi code nghiệp vụ trong ứng dụng Java. MCP tool được MCP client phát hiện từ MCP server rồi bọc thành callback để `ChatClient` sử dụng. Với model và `ToolCallingAdvisor`, cả hai đều được cung cấp dưới dạng định nghĩa công cụ; với backend, chúng đi qua hai đường thực thi và hai ranh giới bảo mật khác nhau.

Hãy chọn tool theo nhu cầu tích hợp thực tế, truyền MCP provider tường minh, bảo vệ namespace, kiểm soát dữ liệu `ToolContext` đi qua `_meta` và áp dụng authorization ở service thực thi. Dùng MCP khi cần công bố hoặc dùng lại capability xuyên ứng dụng; dùng local tool khi Java service đã có sẵn trong cùng hệ thống và không cần giao thức riêng.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 Reference — MCP Client Boot Starter](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-client-boot-starter-docs.html)
- [Spring AI 2.1.0 Reference — MCP Server Boot Starter](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-server-boot-starter-docs.html)
- [Spring AI 2.1.0 Reference — MCP Annotations](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-annotations-overview.html)
- [Spring AI 2.1.0 Reference — Upgrade Notes về MCP Annotations](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)
- [Model Context Protocol — MCP Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)


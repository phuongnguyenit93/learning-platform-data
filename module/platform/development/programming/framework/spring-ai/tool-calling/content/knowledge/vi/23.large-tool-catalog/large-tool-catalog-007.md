# Lọc quyền trước và sau bước tìm công cụ

Với một danh mục có hàng chục hoặc hàng trăm tool, Spring AI có thể dùng `ToolSearchToolCallingAdvisor` để chỉ đưa những tool liên quan vào prompt khi mô hình cần chúng. Nhưng **tool search là cơ chế khám phá, không phải cơ chế phân quyền**. Một tool xuất hiện trong kết quả tìm kiếm không có nghĩa người dùng hiện tại được phép gọi nó.

Muốn bảo vệ danh mục lớn, ứng dụng phải lọc ở nhiều ranh giới:

1. **Trước khi index:** chỉ đưa tool mà principal hiện tại được phép khám phá vào chỉ mục của session.
2. **Sau khi search:** kiểm tra lại từng kết quả theo quyền hiện tại trước khi trả định nghĩa tool cho mô hình.
3. **Trước khi execute:** xác thực lại quyền trên tool và tài nguyên cụ thể ngay trong callback/service.

Ba bước này giải quyết ba rủi ro khác nhau: lộ tên/mô tả tool, kết quả tìm kiếm cũ hoặc không phù hợp với quyền hiện tại, và mô hình gọi một hành động mà principal không được phép thực hiện.

## 1. Tool search không phải access-control list

`ToolSearchToolCallingAdvisor` thực hiện progressive tool disclosure:

1. Đọc tool callbacks được đăng ký trong request.
2. Index tên và mô tả tool theo session.
3. Ban đầu chỉ gửi định nghĩa của `toolSearchTool` cho mô hình.
4. Mô hình tìm kiếm capability bằng câu hỏi tự nhiên.
5. Advisor thêm các tool đã tìm thấy vào request kế tiếp.
6. Mô hình gọi tool và `ToolCallingManager` thực thi callback.

Index mặc định có thể dùng regex, Lucene hoặc vector search. Các chiến lược này tối ưu việc tìm tool liên quan. Chúng không biết principal có quyền gì, tenant nào đang hoạt động hoặc một quyền vừa bị thu hồi.

| Cơ chế | Trả lời câu hỏi | Không đảm bảo |
| --- | --- | --- |
| Regex/Lucene/Vector ToolIndex | Tool nào gần với truy vấn? | Người dùng có quyền xem hoặc gọi tool không |
| maxResults / relevance threshold | Nên trả về bao nhiêu kết quả phù hợp? | Kết quả có hợp lệ theo policy không |
| categoryFilter | Thu hẹp tìm kiếm theo gợi ý category nào? | Category có được phép cho principal không |
| Tool definition / schema | Mô hình cần cung cấp arguments nào? | Arguments có được phép về nghiệp vụ không |
| Authorization policy | Principal có được thực hiện hành động này trên tài nguyên này không? | Không thay thế tìm kiếm capability |

Không dùng điểm relevance, tên tool khó đoán hoặc category do mô hình đề xuất làm điều kiện phân quyền.

## 2. Ba quyền cần phân biệt

Không nên gộp mọi quyết định vào một cờ allow/deny:

| Quyền | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Discover | Người dùng có được biết tool/capability này tồn tại không? | Nhân viên hỗ trợ được thấy tool tra cứu đơn hàng |
| Execute | Người dùng có được gọi tool này không? | Chỉ quản lý được gọi tool hoàn tiền |
| Resource access | Người dùng có được thao tác trên tài nguyên cụ thể không? | Nhân viên chỉ được xem đơn hàng thuộc tenant của mình |

Một tool có thể được phép discover nhưng chỉ cho phép execute với một nhóm role. Ngay cả khi được execute, service vẫn phải kiểm tra quyền trên orderId, customerId, tenantId hoặc resource cụ thể.

Tool definition cũng là dữ liệu có thể tiết lộ khả năng nội bộ. Tên như `export_all_customers` hoặc mô tả quy trình quản trị không nên xuất hiện trong prompt của người không được phép biết chức năng đó.

## 3. Lọc trước khi index

Spring AI gọi `ToolCallingManager.resolveToolDefinitions(...)` để lấy các tool definitions từ request rồi đưa chúng vào `ToolIndex`. Chỉ mục được tạo theo session và có thể được giữ lại qua nhiều turn.

Vì vậy, tập callback phải được giới hạn trước khi truyền vào `ChatClient` hoặc `ToolSearchToolCallingAdvisor`. Ví dụ, tạo danh sách theo principal đã xác thực:

~~~java
public ToolCallback[] toolsFor(AuthenticatedPrincipal principal) {
    return toolRegistry.allCallbacks().stream()
        .filter(callback -> accessPolicy.canDiscover(
            principal, callback.getToolDefinition().name()))
        .map(this::wrapWithExecutionAuthorization)
        .toArray(ToolCallback[]::new);
}
~~~

Khởi tạo advisor và ChatClient một lần với ToolIndex đã bọc:

~~~java
ToolSearchToolCallingAdvisor toolSearchAdvisor =
    ToolSearchToolCallingAdvisor.builder()
        .toolIndex(authorizingToolIndex)
        .sessionIdKeyName("toolAccessSessionId")
        .referenceToolNameAccumulation(false)
        .build();

ChatClient chatClient = ChatClient.builder(chatModel)
    .defaultAdvisors(toolSearchAdvisor)
    .build();
~~~

Ở mỗi request, resolve callback theo principal hiện tại rồi mới gửi:

~~~java
ToolCallback[] permittedTools = toolAccessService.toolsFor(principal);

String answer = chatClient.prompt()
    .user(question)
    .tools(permittedTools)
    .advisors(a -> a.param("toolAccessSessionId", serverIssuedToolSessionId))
    .call()
    .content();
~~~

Key `toolAccessSessionId` được cấu hình đồng nhất qua `sessionIdKeyName(...)` và advisor context. Giá trị phải do server tạo hoặc phân giải sau khi xác thực quyền sở hữu conversation.

Nếu dùng `defaultTools(...)` để đăng ký toàn bộ catalog, advisor sẽ index catalog đó. Đừng đưa các tool nhạy cảm vào tập mặc định dùng chung rồi kỳ vọng search tự ẩn chúng. Dùng provider hoặc callback set đã lọc theo request; chỉ giữ ở default set những tool thật sự được phép cho mọi request.

### Chụp quyền tại thời điểm tạo index

Ứng dụng nên tạo một access scope cho session index gồm:

- Principal ID đã xác thực.
- Tenant ID đã được xác minh.
- Danh sách role/authority hoặc policy scope cần thiết.
- Phiên bản quyền hoặc policy version.
- Conversation/session ID đã được kiểm tra quyền sở hữu.

Tạo session key opaque ở server, chẳng hạn hash của conversation ID, principal ID, tenant ID và policy version. Không dùng một chuỗi do client tự gửi làm session ID nếu chưa xác minh quyền sở hữu.

Nếu hai người dùng trong cùng tenant có role khác nhau, không dùng chung một tool index chỉ vì tenant giống nhau.

## 4. Lọc cả khi ghi vào ToolIndex

Có thể bọc một ToolIndex hiện hữu để chỉ index các tool được phép discover. Interface `ToolIndex` có bốn thao tác: `indexTool`, `indexTools`, `search` và `clearIndex`.

Ví dụ dưới đây minh họa lớp lọc trước khi ghi index:

~~~java
public final class AuthorizingToolIndex implements ToolIndex {

    private final ToolIndex delegate;
    private final ToolAccessPolicy accessPolicy;
    private final ToolSessionScopeResolver scopeResolver;

    public AuthorizingToolIndex(
            ToolIndex delegate,
            ToolAccessPolicy accessPolicy,
            ToolSessionScopeResolver scopeResolver) {
        this.delegate = delegate;
        this.accessPolicy = accessPolicy;
        this.scopeResolver = scopeResolver;
    }

    @Override
    public void indexTool(String sessionId, ToolReference reference) {
        var scope = scopeResolver.requireScope(sessionId);
        if (accessPolicy.canDiscover(scope, reference.toolName())) {
            delegate.indexTool(sessionId, reference);
        }
    }

    @Override
    public void indexTools(
            String sessionId,
            List<ToolReference> references) {
        var scope = scopeResolver.requireScope(sessionId);
        var permitted = references.stream()
            .filter(ref -> accessPolicy.canDiscover(scope, ref.toolName()))
            .toList();
        delegate.indexTools(sessionId, permitted);
    }

    @Override
    public ToolSearchResponse search(ToolSearchRequest request) {
        return delegate.search(request);
    }

    @Override
    public void clearIndex(String sessionId) {
        delegate.clearIndex(sessionId);
    }
}
~~~

`ToolSessionScopeResolver` và `ToolAccessPolicy` là thành phần của ứng dụng. Resolver phải tra scope từ kho server-side; không dựng scope từ session ID hoặc categoryFilter do mô hình gửi lên.

Đoạn wrapper trên minh họa phần lọc lúc ghi index; trong lớp hoàn chỉnh, thay phần thân search đang delegate trực tiếp bằng bước re-check ở mục tiếp theo.

Lọc trước khi index giúp tên và mô tả của tool bị cấm không nằm trong chỉ mục của session. Tuy nhiên, chỉ lọc ở bước này chưa đủ vì quyền có thể thay đổi sau khi index.

## 5. Lọc lại sau khi search

Một chỉ mục được tạo lúc đăng nhập có thể vẫn tồn tại khi:

- Người dùng bị thu hồi role.
- Người dùng chuyển tenant.
- Admin tắt một tool hoặc thu hồi quyền của nhóm.
- Quyền truy cập một tài nguyên cụ thể thay đổi.
- Tool được thay thế hoặc ngừng cung cấp.

Do đó, ngay sau khi delegate search trả kết quả, hãy kiểm tra lại từng ToolReference bằng quyền hiện tại trước khi trả về cho `toolSearchTool`:

~~~java
@Override
public ToolSearchResponse search(ToolSearchRequest request) {
    ToolSearchResponse found = delegate.search(request);
    var currentScope = scopeResolver.requireCurrentScope(request.sessionId());

    List<ToolReference> permitted = found.toolReferences().stream()
        .filter(ref -> accessPolicy.canDiscoverNow(
            currentScope, ref.toolName()))
        .toList();

    // Không giữ totalMatches hoặc metadata có thể tiết lộ số tool bị lọc.
    return new ToolSearchResponse(permitted, permitted.size(), null);
}
~~~

Kết quả chỉ chứa tool được phép discover tại thời điểm search. Không trả tổng số kết quả gốc hoặc search metadata nếu các giá trị đó có thể tiết lộ sự tồn tại của tool bị cấm.

`categoryFilter` là gợi ý thu hẹp tìm kiếm; nó do request/model cung cấp và không phải authorization rule. Policy phải chạy độc lập với query, category hoặc relevance score.

### Vì sao phải lọc cả trước và sau?

| Chỉ lọc ở đâu? | Rủi ro còn lại |
| --- | --- |
| Chỉ trước index | Quyền có thể bị thu hồi trong khi index vẫn được cache; kết quả cũ có thể được trả lại |
| Chỉ sau search | Tool bị cấm vẫn nằm trong index, làm tăng rủi ro lộ metadata qua log, debug hoặc đường truy cập khác |
| Chỉ ở callback | Model có thể nhìn thấy tên/mô tả tool mà người dùng không được phép biết |
| Trước index + sau search + trước execute | Kiểm soát discovery, kết quả và hành động ở từng ranh giới |

## 6. Cẩn thận với session index và cache

`ToolSearchToolCallingAdvisor` index tool theo session. Advisor bỏ qua việc re-index nếu fingerprint của tool set không đổi. Fingerprint mặc định được tạo từ tên và mô tả tool; nó không đại diện cho role hoặc quyền của người dùng.

Có ba việc cần làm khi quyền thay đổi:

1. **Session ID mang scope quyền:** dùng key server-side khác nhau cho principal/tenant/policy version khác nhau.
2. **Evict khi policy đổi:** gọi `advisor.evictSession(sessionId)` hoặc dùng session key mới để index lại.
3. **Re-check mỗi lần search và execute:** không tin index cũ là bằng chứng quyền vẫn còn.

Không dùng session ID chung cho mọi người dùng. Không dùng tenant ID đơn lẻ nếu người dùng trong tenant có quyền khác nhau.

### Tool references được tích lũy qua nhiều lượt

`referenceToolNameAccumulation` mặc định là `true`. Khi bật, các tool đã được tìm thấy trong các lượt search trước có thể tiếp tục được đưa vào request sau. Nếu quyền thay đổi, tool đã discover trước đó có thể vẫn nằm trong lịch sử và được chọn lại.

Với catalog có quyền thay đổi theo người dùng, cân nhắc:

~~~java
ToolSearchToolCallingAdvisor advisor =
    ToolSearchToolCallingAdvisor.builder()
        .toolIndex(authorizingToolIndex)
        .referenceToolNameAccumulation(false)
        .sessionIdKeyName("toolAccessSessionId")
        .build();
~~~

Tắt accumulation giảm việc tái sử dụng kết quả search cũ qua nhiều search turn; mọi search call song song trong turn gần nhất vẫn được tính. Nó không thay thế authorization tại callback. Nếu quyền bị thu hồi giữa hai iteration của cùng một turn, lớp thực thi vẫn phải từ chối callback.

## 7. Lọc ngay trước khi thực thi callback

Trong Spring AI, `ToolSearchToolCallingAdvisor.prepareIteration` lấy tên tool từ kết quả search đã có trong conversation, sau đó chọn callback cùng tên từ map callback đã resolve cho request. Điều đó giúp chỉ gửi những tool đã được khám phá vào model round tiếp theo.

Nhưng callback có thể đã được cache từ lúc khởi tạo request, trong khi quyền hoặc quyền trên tài nguyên đã thay đổi. Bọc callback hoặc đặt authorization trong service để kiểm tra lại ngay trước khi delegate chạy:

~~~java
public final class AuthorizingToolCallback implements ToolCallback {

    private final ToolCallback delegate;
    private final CurrentPrincipal currentPrincipal;
    private final ToolAccessPolicy accessPolicy;
    private final ToolArgumentParser argumentParser;

    public AuthorizingToolCallback(
            ToolCallback delegate,
            CurrentPrincipal currentPrincipal,
            ToolAccessPolicy accessPolicy,
            ToolArgumentParser argumentParser) {
        this.delegate = delegate;
        this.currentPrincipal = currentPrincipal;
        this.accessPolicy = accessPolicy;
        this.argumentParser = argumentParser;
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
        var principal = currentPrincipal.requireAuthenticated();
        var arguments = argumentParser.parse(
            delegate.getToolDefinition(), toolInput);
        accessPolicy.requireCanExecute(
            principal, delegate.getToolDefinition().name(), arguments);
        return delegate.call(toolInput);
    }

    @Override
    public String call(String toolInput, ToolContext context) {
        var principal = currentPrincipal.requireAuthenticated();
        var arguments = argumentParser.parse(
            delegate.getToolDefinition(), toolInput);
        accessPolicy.requireCanExecute(
            principal, delegate.getToolDefinition().name(), arguments);
        return delegate.call(toolInput, context);
    }
}
~~~

Đây là decorator minh họa; parser và policy là thành phần ứng dụng. Decorator phải giữ nguyên ToolDefinition/ToolMetadata và chuyển tiếp cả hai overload call để không làm mất ToolContext.

Với streaming hoặc callback chạy trên scheduler khác, không mặc định ThreadLocal security context sẽ còn tồn tại. Hãy propagate security context bằng cơ chế của ứng dụng hoặc gắn một principal reference đã xác thực vào ToolContext của request; service vẫn phải kiểm tra quyền trên tài nguyên trước khi thực hiện side effect.

Authorization service cần kiểm tra:

- Principal hiện tại có authority cho loại thao tác không?
- Tenant trong context có thuộc principal không?
- Tài nguyên được chỉ định trong arguments có thuộc tenant đó không?
- Trạng thái tài nguyên có cho phép hành động không?
- Quyền có còn hiệu lực tại thời điểm thực thi không?

Không dựa vào việc mô hình đã thấy tool definition hoặc search tool đã trả tên tool để bỏ qua bước này.

## 8. Kết hợp với ToolContext

ToolContext có thể truyền tenant ID, user ID hoặc request scope mà mô hình không nhìn thấy. Hãy tạo context từ security context đã xác thực:

~~~java
Map<String, Object> trustedContext = Map.of(
    "tenantId", authenticatedTenant.id(),
    "principalId", authenticatedPrincipal.id(),
    "authorizationVersion", permissionSnapshot.version()
);

chatClient.prompt()
    .user(question)
    .tools(permittedCallbacks)
    .toolContext(trustedContext)
    .call()
    .content();
~~~

Không đưa tenant ID, principal ID hoặc role do mô hình tự khai báo vào ToolContext. ToolContext cũng không tự cấp quyền; callback/service vẫn phải kiểm tra identity và resource authorization.

## 9. Lọc tool từ MCP server

MCP client có thể kết nối nhiều server và biến tool từ xa thành ToolCallback. Không nên tự động expose mọi tool từ mọi server vào danh mục của mọi request.

### MCP legacy: McpToolFilter

Spring AI hỗ trợ bean `McpToolFilter` để lọc tool được phát hiện dựa trên connection info và thuộc tính tool:

~~~java
@Bean
McpToolFilter mcpToolFilter() {
    return (connectionInfo, tool) ->
        trustedMcpServers.contains(
            connectionInfo.initializeResult().serverInfo().name())
            && approvedRemoteToolNames.contains(tool.name());
}
~~~

`McpToolFilter` là bộ lọc ở ranh giới discovery của MCP client. Nó phù hợp để loại server hoặc tool không được phép tích hợp vào catalog. Filter này nhận thông tin kết nối và tool, không tự đại diện cho principal của từng request. Không dùng nó làm lớp phân quyền theo người dùng nếu client/connection được chia sẻ.

### MCP modern: McpModernToolFilter

Với modern Streamable HTTP connections, dùng `McpModernToolFilter`:

~~~java
@Bean
McpModernToolFilter modernToolFilter() {
    return (connection, tool) ->
        !(connection.name().equals("tickets")
            && tool.name().startsWith("admin_"));
}
~~~

`McpToolFilter` áp dụng cho legacy protocol; `McpModernToolFilter` áp dụng cho modern connections. Nếu ứng dụng dùng cả hai loại, cấu hình filter tương ứng cho từng loại.

Nếu application context có `McpToolFilter` và cấu hình modern connection nhưng không có `McpModernToolFilter`, Spring AI sẽ báo lỗi khởi động thay vì âm thầm bỏ qua filter. Mỗi loại filter chỉ nên có một bean; hãy gộp nhiều rule vào một implementation.

### Identity của MCP client cũng cần đúng scope

Các legacy MCP client auto-configured là singleton và MCP protocol session được chia sẻ. Việc filter danh sách tool lúc khởi tạo dưới identity của người đầu tiên không tạo ra danh sách riêng cho từng người dùng sau đó. Server MCP vẫn phải authorize từng tool call theo credential của caller.

Với legacy client dùng chung, nếu server cần biết người dùng cuối, ứng dụng phải truyền identity đã xác thực qua một kênh metadata per-call được bảo vệ hoặc quản lý client/session riêng theo caller. Không suy ra người dùng cuối từ clientInfo của MCP connection; giá trị đó mô tả ứng dụng MCP client, không phải principal đang chat.

Với modern connections:

- `client-scope=PER_REQUEST` tạo client cho mỗi lần resolve tool; đây là mặc định.
- `client-scope=CUSTOM` cho phép ứng dụng chọn client theo user/tenant.
- `client-scope=SHARED` chỉ phù hợp khi mọi request dùng cùng một identity.
- `McpClientCustomizer` có thể cung cấp transport context; `McpHttpRequestCustomizer` chuyển identity thành HTTP header.

Không dùng một shared client cho server MCP trả tool list hoặc kết quả khác nhau theo người gọi. Nếu server cần per-user authorization, truyền credential của đúng caller và để server xác thực ở mỗi request.

Với modern MCP server trả tool list khác nhau theo người dùng, server phải đánh dấu listing là private thay vì public. Listing public có thể được dùng lại qua nhiều request; listing private không được giữ bởi scope PER_REQUEST. Nếu cần cache listing riêng cho từng người dùng, dùng CUSTOM scope với client riêng theo caller và quản lý TTL/eviction. Dù listing đã được lọc đúng, MCP server vẫn phải authorize từng tool call vì quyền có thể thay đổi sau khi listing được tạo.

Với modern connection dùng ASYNC client, dùng `AsyncModernMcpTransportContextProvider` để cung cấp caller khi resolve tool; nếu đặt `client-scope=CUSTOM`, dùng thêm `AsyncModernMcpClientScope` để chọn client theo caller. Provider được gọi trên thread resolve tools và context được gắn với callback, nên callback chạy sau đó trên Reactor scheduler vẫn dùng đúng caller. Không đọc thread-bound security context ở callback execution nếu identity chưa được propagate. Khi dùng `PER_REQUEST`, listing và tool callback của request giữ cùng caller context. Không re-expose các callback modern đã resolve theo service account từ một MCP server khác nếu muốn giữ identity của từng user.

## 10. Không làm rò rỉ quyền qua MCP metadata

`ToolContextToMcpMetaConverter.defaultConverter()` loại MCP exchange key và giá trị null, nhưng chuyển tiếp các context entry khác. Nếu ToolContext có access token, secret, toàn bộ principal hoặc thông tin nội bộ, chúng có thể bị gửi sang MCP server như metadata.

Hãy dùng converter allowlist:

~~~java
@Bean
ToolContextToMcpMetaConverter safeMetaConverter() {
    return context -> {
        if (context == null || context.getContext() == null) {
            return Map.of();
        }

        Object tenantRef = context.getContext().get("tenantRef");
        if (tenantRef == null) {
            return Map.of();
        }

        return Map.of("tenantRef", tenantRef);
    };
}
~~~

Chỉ gửi những metadata mà MCP server cần để thực thi và có thể bảo vệ. Không chuyển access token thô hoặc toàn bộ ToolContext sang server từ xa nếu không có thiết kế credential rõ ràng.

## 11. Các lỗi bảo mật thường gặp

| Biểu hiện | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Model tìm thấy tool quản trị | Index chứa toàn bộ catalog | Lọc callback trước khi index |
| Tool đã bị thu hồi vẫn xuất hiện | Session index hoặc tool-name accumulation còn cũ | Evict/reindex, tắt accumulation khi phù hợp và lọc lại sau search |
| Tool không còn quyền nhưng callback vẫn chạy | Chỉ kiểm tra quyền lúc discover | Reauthorize trong callback/service trước khi thực thi |
| Người dùng khác thấy tool đã discover | Dùng chung session ID/index | Tạo session key theo principal, tenant và policy version |
| categoryFilter được dùng như quyền | Tin category do model chọn | Chỉ dùng category để thu hẹp relevance; authorization chạy riêng |
| MCP tool nhạy cảm xuất hiện ở mọi request | Không cấu hình MCP tool filter | Dùng McpToolFilter/McpModernToolFilter và provider theo request |
| MCP server dùng identity của người đầu tiên | Legacy client/session được chia sẻ | Server authorize từng call hoặc quản lý client/session riêng cho caller |
| Secret bị gửi sang MCP server | Default ToolContext metadata converter chuyển nhiều context entry | Dùng ToolContextToMcpMetaConverter allowlist |
| Model gọi tool không có trong danh sách đã tìm | Tool set thực thi rộng hơn tool set được discover | Chỉ truyền callback được phép và kiểm tra tên/permission ở execution gate |

## 12. Ma trận kiểm thử quyền

Kiểm thử discovery, search và execution độc lập:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Principal A có quyền đọc, không có quyền ghi | Index chỉ chứa tool đọc; tool ghi không xuất hiện |
| Principal B có quyền quản trị | Chỉ session của B được index tool quản trị |
| Hai principal cùng tenant, role khác nhau | Không dùng chung session index hoặc kết quả search |
| Quyền bị thu hồi sau khi index | Search tiếp theo không trả tool cũ |
| Quyền bị thu hồi sau search, trước execute | Callback/service từ chối thực thi |
| Tool name bị model tự đoán | Không có callback được expose hoặc execution policy từ chối |
| categoryFilter yêu cầu category cấm | Không thể vượt qua policy |
| referenceToolNameAccumulation bật | Xác minh tool đã discover trước không vượt quyền sau khi policy đổi |
| referenceToolNameAccumulation tắt | Chỉ kết quả của search turn gần nhất được xem xét |
| MCP legacy filter | Tool từ server không tin cậy bị loại khỏi provider |
| MCP modern filter | Tool admin bị loại theo connection policy |
| MCP shared client nhiều user | Không dùng tool list của caller đầu tiên làm quyền của mọi caller |
| ToolContext gửi sang MCP | Chỉ metadata allowlist được truyền |
| Session eviction | Index cũ bị xóa sau logout hoặc permission version đổi |

Nên mock ToolIndex để trả về tool bị cấm, mock ToolCallback để đếm số lần call và kiểm tra callback không được thực thi. Với kiểm thử MCP, dùng server giả lập có tool list khác nhau theo identity và xác minh credentials đúng được gửi cho từng caller.

## Bài thực hành

Một hệ thống hỗ trợ khách hàng có catalog gồm:

- lookup_order: tra cứu đơn hàng.
- update_shipping_address: cập nhật địa chỉ giao hàng.
- issue_refund: hoàn tiền.
- export_customer_data: xuất dữ liệu khách hàng.
- manage_user_roles: thay đổi quyền người dùng.

Hãy thiết kế:

1. Nhân viên hỗ trợ chỉ discover lookup_order và update_shipping_address.
2. Quản lý có thể discover issue_refund nhưng chỉ được execute trong hạn mức và sau confirmation.
3. Chỉ bộ phận bảo mật được discover và execute manage_user_roles.
4. export_customer_data chỉ xuất hiện trong workflow đã được cấp quyền riêng.
5. Lọc callback set trước khi index.
6. Tạo AuthorizingToolIndex lọc cả lúc index và sau search.
7. Gắn session index với principal, tenant và policy version; evict khi quyền thay đổi.
8. Bọc callback để reauthorize ngay trước khi execute.
9. Nếu dùng MCP, lọc tool theo server/connection và truyền identity đúng caller; không gửi secret qua metadata converter mặc định.
10. Viết test cho quyền bị thu hồi giữa discovery và execution.

Sau khi hoàn thành, hãy giải thích vì sao tool search relevance không phải authorization, vì sao cần lọc sau search và vì sao callback vẫn phải kiểm tra quyền lần cuối.

## Ghi nhớ

Trong danh mục tool lớn, quyền phải được kiểm tra trước khi index, sau khi search và ngay trước khi thực thi. Trước index, chỉ cung cấp callback mà principal được phép discover. Sau search, lọc lại ToolReference bằng policy hiện tại, không tin index hoặc category cũ. Trước execute, kiểm tra principal, tenant, resource và quyền hiện tại trong callback/service. Với ToolSearchToolCallingAdvisor, session index và tool-name accumulation có thể giữ kết quả cũ; hãy cô lập session theo scope quyền, evict khi policy đổi và cân nhắc tắt accumulation. Với MCP, lọc tool ở discovery, quản lý client identity đúng scope và chỉ chuyển metadata allowlist.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Search Tool](https://docs.spring.io/spring-ai/reference/api/tools/tool-search-tool.html)
- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — MCP Client Boot Starter: Tool Filtering and Identity](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-client-boot-starter-docs.html)
- [Spring AI 2.1.0 — MCP Tool Callbacks](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-tool-callbacks.html)
- [ToolSearchToolCallingAdvisor API — Spring AI 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/client/advisor/toolsearch/ToolSearchToolCallingAdvisor.html)
- [ToolIndex API — Spring AI 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/toolsearch/ToolIndex.html)
- [ToolSearchRequest API — Spring AI 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/toolsearch/ToolSearchRequest.html)
- [ToolSearchResponse API — Spring AI 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/toolsearch/ToolSearchResponse.html)

# ToolSearchToolCallingAdvisor và điều kiện hỗ trợ theo phiên bản

Khi một trợ lý AI chỉ có vài công cụ, ứng dụng thường gửi toàn bộ `ToolDefinition` cho mô hình trong mỗi lượt gọi. Cách này đơn giản, nhưng khi danh mục tăng lên hàng chục hoặc hàng trăm công cụ từ `@Tool`, `ToolCallback` và nhiều MCP server, phần tên, mô tả và JSON Schema có thể chiếm nhiều token. Mô hình cũng khó chọn chính xác giữa nhiều tool có tên hoặc chức năng gần giống nhau.

`ToolSearchToolCallingAdvisor` của Spring AI giải quyết vấn đề bằng **progressive tool disclosure**: trước hết cho mô hình thấy một công cụ tìm kiếm có tên `toolSearchTool`; mô hình tìm những khả năng phù hợp; advisor mới đưa định nghĩa của các công cụ tìm thấy vào lượt tiếp theo. Tool nghiệp vụ vẫn do ứng dụng thực thi qua `ToolCallingManager` như trong vòng gọi công cụ thông thường.

Đây là một cơ chế của **Spring AI 2.x**, không phải tính năng tự động có sẵn trong mọi phiên bản Spring AI 1.x hay mọi model. Bài học xác định ranh giới phiên bản, điều kiện chạy, cách cấu hình, các chiến lược tìm kiếm và các điểm cần kiểm soát khi danh mục tool phụ thuộc người dùng hoặc tenant.

## Sau bài học, bạn có thể

- Mô tả vì sao đưa toàn bộ tool definitions vào mỗi prompt có thể làm tăng chi phí và giảm khả năng chọn đúng tool.
- Giải thích luồng `toolSearchTool`: index, tìm công cụ, công bố definition, gọi tool thật và trả kết quả.
- Phân biệt `ToolSearchToolCallingAdvisor` với `ToolCallingAdvisor` mặc định và với tool-search native của một nhà cung cấp model.
- Xác định phiên bản Spring AI nào có tính năng này và chiến lược `ToolIndex` nào có trong từng nhánh.
- Cấu hình starter và property `spring.ai.chat.client.tool-search-advisor.enabled`.
- Đăng ký advisor thủ công cùng `RegexToolIndex` hoặc lựa chọn index phù hợp.
- Truyền session ID đúng phạm vi, quản lý cập nhật danh mục và giải phóng session index.
- Giới hạn tool theo quyền người dùng trước khi index, rồi kiểm tra quyền lại khi thực thi.
- Đánh giá đánh đổi token, số lượt gọi model, độ trễ và độ chính xác.
- Thiết kế kiểm thử cho cả quá trình discovery và execution.

## Vấn đề khi danh mục có quá nhiều công cụ

Giả sử nền tảng quản lý doanh nghiệp kết nối CRM, ERP, hệ thống đơn hàng, vận chuyển và vài MCP server. Một trợ lý có thể nhìn thấy:

- `getCustomerSummary`, `getCustomerOrders` và `getCustomerBalance`.
- `findInvoice`, `createInvoice` và `cancelInvoice`.
- `searchPolicy`, `searchKnowledge` và `searchContract`.
- Hàng chục biến thể khác nhau của các tool đọc, tìm kiếm hoặc thay đổi dữ liệu.

Nếu mỗi tool có mô tả và JSON Schema dài, danh mục 50–100 tool có thể tốn lượng lớn context ngay cả khi người dùng chỉ cần một thao tác. Hơn nữa, model phải quyết định giữa nhiều chức năng tương tự, làm tăng nguy cơ chọn nhầm.

Spring AI 2.1.0 gợi ý xem xét Tool Search Tool khi danh mục từ khoảng **10 tool trở lên**, hoặc định nghĩa tool vượt **10.000 token** mỗi request. Đây là tiêu chí kinh nghiệm, không phải một giới hạn cứng của framework. Một danh mục nhỏ nhưng schema dài cũng có thể hưởng lợi; ngược lại, danh mục nhiều tool rất ngắn và được dùng thường xuyên có thể không cần một lượt search bổ sung.

| Cách cấp tool | Model thấy gì ở lượt đầu? | Phù hợp |
|---|---|---|
| `ToolCallingAdvisor` mặc định | Toàn bộ định nghĩa tool được cung cấp | Danh mục nhỏ hoặc cần hầu hết tool mỗi lượt |
| `ToolSearchToolCallingAdvisor` | `toolSearchTool` để khám phá; tool thực được công bố dần | Danh mục lớn, nhiều MCP server, nhiều chức năng ít dùng |
| Tự lọc tool tại ứng dụng | Chỉ những callback do backend chọn trước request | Quy tắc nghiệp vụ/ràng buộc quyền xác định được từ đầu |

Tool Search Tool bổ sung một cách **chọn tool theo nhu cầu của model**. Nó không loại bỏ nhu cầu chọn trước các tool mà user được phép dùng và không tự làm cho mọi tool an toàn.

## Luồng progressive tool disclosure

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as ChatClient
    participant A as ToolSearchToolCallingAdvisor
    participant I as ToolIndex
    participant M as Chat Model
    participant T as ToolCallingManager
    participant S as Dịch vụ nghiệp vụ

    U->>C: Câu hỏi
    C->>A: Request + tool callbacks + session ID
    A->>I: Index tool được phép dùng cho session
    A->>M: Prompt + định nghĩa toolSearchTool
    M-->>A: toolSearchTool(query)
    A->>I: Search theo query, session ID
    I-->>A: Các ToolReference phù hợp
    A->>M: Lượt tiếp theo + definitions được khám phá
    M-->>A: Tool call thật + JSON arguments
    A->>T: Thực thi callback đã được công bố
    T->>S: Thực thi nghiệp vụ
    S-->>T: Kết quả
    T-->>A: Tool result
    A->>M: Lịch sử hội thoại + tool result
    M-->>A: Câu trả lời cuối
    A-->>C: ChatResponse
    C-->>U: Nội dung phản hồi
~~~

Điểm quan trọng:

1. **Indexing:** advisor nhận các `ToolCallback` của request/session và lập chỉ mục tên, mô tả của những tool đó.
2. **Initial request:** thay vì gửi toàn bộ định nghĩa, model ban đầu chỉ có `toolSearchTool`.
3. **Discovery:** model gọi `toolSearchTool` với câu hỏi tìm kiếm bằng ngôn ngữ tự nhiên.
4. **Search & expand:** `ToolIndex` trả các tool liên quan; advisor đưa định nghĩa tool được tìm thấy vào lượt model tiếp theo.
5. **Execution:** model gọi tool nghiệp vụ bằng tên và JSON arguments. `ToolCallingManager` thực thi callback đã được cung cấp.
6. **Response:** tool result quay lại vòng hội thoại để model tổng hợp câu trả lời.

Việc lập chỉ mục không gọi các tool nghiệp vụ. Chỉ đến khi model đã có định nghĩa và phát sinh tool call thực sự, callback nghiệp vụ mới được gọi.

### So sánh số lượt gọi model

Với `ToolCallingAdvisor` mặc định, model đã thấy định nghĩa của `getOrderStatus` trong request đầu và có thể gọi ngay. Với Tool Search Tool, model thường cần gọi `toolSearchTool` trước, sau đó mới gọi `getOrderStatus`. Vì thế, có thể tiết kiệm token định nghĩa tool nhưng **tốn thêm lượt suy luận/tìm kiếm**.

Tác động tổng thể phụ thuộc vào kích thước catalog, độ dài schema, chi phí token và độ trễ model. Không mặc định rằng Tool Search luôn nhanh hoặc rẻ hơn cho mọi request.

## Điều kiện hỗ trợ theo phiên bản Spring AI

Đây là phần cần kiểm tra trước khi copy bất kỳ ví dụ cấu hình nào.

| Phiên bản | `ToolSearchToolCallingAdvisor` | Các lựa chọn index được tài liệu hóa | Lưu ý |
|---|---|---|---|
| Spring AI 1.0.x | Không có trong API công khai của nhánh 1.0.x | Không áp dụng | Nếu cần catalog lớn, ứng dụng phải tự chọn callback trước request |
| Spring AI 1.1.x | Không có trong API công khai của nhánh 1.1.x | Không áp dụng | Không dùng starter/property của 2.x cho nhánh này |
| Spring AI 2.0.x, ví dụ 2.0.2 | Có | `RegexToolIndex`, `LuceneToolIndex`, `VectorToolIndex` | Phải có module/starter Tool Search và session ID |
| Spring AI 2.1.0 | Có | Regex, Lucene, Vector và `DecisionToolIndex` | Có thêm chỉ mục ra quyết định và các option tương ứng |
| Bản snapshot/preview khác | Phụ thuộc build cụ thể | Phụ thuộc build | Đối chiếu tài liệu, dependency tree và API của bản đang dùng |

Spring AI công bố tính năng Tool Search trong lộ trình 2.0; release notes **Spring AI 2.0.0-RC1** giới thiệu advisor với ba chiến lược Regex, Lucene và Vector. Tài liệu Spring AI **2.0.2** cũng mô tả ba chiến lược này. Tài liệu stable **2.1.0** mô tả thêm `DecisionToolIndex`.

Không suy luận rằng một artifact có class chỉ vì tên được nhắc trong blog hoặc tài liệu `main`. Với dự án cũ, kiểm tra BOM, artifact phiên bản và tài liệu theo đúng số version. Đặc biệt, ví dụ `DecisionToolIndex` trong tài liệu 2.1 không thể mặc nhiên dùng cho một ứng dụng khóa Spring AI 2.0.x.

### Không nhầm version Spring AI với khả năng của model

Spring AI có class advisor là một điều kiện. Điều kiện khác là **chat model và integration phải hỗ trợ tool/function calling** theo hợp đồng Spring AI: nhận định nghĩa tool, trả tên tool và JSON arguments, cho phép model tiếp tục sau tool result.

Tool Search Tool của Spring AI chạy trong advisor và được biểu diễn như một công cụ thông thường. Vì vậy nó không yêu cầu provider có API “native tool search” riêng. Tài liệu hướng dẫn mô tả cách tiếp cận có thể dùng với nhiều provider như OpenAI, Anthropic, Gemini và các model phù hợp khác, nhưng vẫn phải kiểm tra model cụ thể có hỗ trợ tool calling.

Không nhầm nó với một chức năng `tool_search` độc lập ở API của provider. Hai tính năng có thể cùng hướng đến mục tiêu giảm lượng tool definition, nhưng tên API, session lifecycle và cơ chế thực thi có thể khác nhau.

### Checklist kiểm tra khả năng trước khi bật

- Xác nhận Spring AI đang dùng là nhánh 2.x có artifact Tool Search tương thích.
- Xác nhận model/provider trả được tool call và nhận được tool result ở lượt kế tiếp.
- Xác nhận `ChatClient` đang chạy `ToolCallingAdvisor`/`ToolSearchToolCallingAdvisor` theo framework-controlled tool execution.
- Xác nhận có `ToolIndex` tương ứng với phương pháp tìm kiếm đã chọn.
- Xác nhận mỗi request có session ID đúng phạm vi; nếu dùng Spring Boot auto-config, starter và property phải có thật trên classpath.
- Kiểm tra giới hạn token/cost/latency qua thử nghiệm thay vì giả định từ số tool.

## Cấu hình nhanh bằng Spring Boot starter

Với Spring AI 2.0.x hoặc 2.1.0, cách đơn giản là thêm starter Tool Search Tool:

~~~xml
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>spring-ai-starter-tool-search-advisor</artifactId>
</dependency>
~~~

Dự án nên dùng Spring AI BOM để các artifact `spring-ai-*` cùng phiên bản. Starter cung cấp auto-configuration và Lucene dependency cần thiết.

Ví dụ cấu hình `application.yml`:

~~~yaml
spring:
  ai:
    chat:
      client:
        tool-search-advisor:
          enabled: true
          tool-index-type: lucene
          max-results: 5
          reference-tool-name-accumulation: true
          eviction:
            lru-max-sessions: 1000
            ttl: 30m
~~~

Ý nghĩa:

- `enabled: true` bật Tool Search advisor thay cho advisor mặc định.
- `tool-index-type: lucene` dùng tìm kiếm keyword; starter đã gồm Lucene.
- `max-results: 5` giới hạn số tool reference được trả về sau một lần tìm.
- `reference-tool-name-accumulation: true` giữ các tool được khám phá ở những lần tìm trước trong session.
- `lru-max-sessions` và `ttl` điều khiển thời gian giữ index session trong bộ nhớ.

Mặc định `enabled` là `false` và index type là `regex`. Nếu không thêm starter hoặc chưa bật property, chỉ đặt các trường config này không làm Tool Search tự xuất hiện.

Auto-configuration đăng ký một builder `ToolSearchToolCallingAdvisor.Builder` dưới kiểu `ToolCallingAdvisor.Builder<?>`; nhờ đó builder mặc định sẽ nhường chỗ khi tính năng bật. Không cần tự đăng ký thêm một `ToolCallingAdvisor` thứ hai.

### Sử dụng các tool Java cục bộ

Ví dụ một tập công cụ nghiệp vụ đã được backend kiểm soát:

~~~java
@Component
public class BusinessTools {

    private final OrderQueryService orders;
    private final PolicyQueryService policies;

    public BusinessTools(
            OrderQueryService orders,
            PolicyQueryService policies) {
        this.orders = orders;
        this.policies = policies;
    }

    @Tool(description = "Tra cứu trạng thái đơn hàng theo mã đơn")
    public OrderStatus getOrderStatus(String orderId, ToolContext context) {
        String tenantId =
                (String) context.getContext().get("tenantId");
        String userId =
                (String) context.getContext().get("userId");

        return orders.getVisibleOrder(tenantId, userId, orderId);
    }

    @Tool(description = "Tìm chính sách đổi trả theo từ khóa")
    public List<PolicySummary> searchReturnPolicy(String keyword) {
        return policies.search(keyword);
    }
}
~~~

`OrderQueryService`, `PolicyQueryService`, `OrderStatus` và `PolicySummary` là những kiểu nghiệp vụ minh họa. Một ứng dụng thực tế cần kiểm tra quyền truy cập cả ở phương thức đọc dữ liệu và các tool có side effect.

Trong cấu hình tự động, vẫn phải **cung cấp danh sách tool** cho `ChatClient` hoặc từng request. Bật Tool Search không làm framework tự quét mọi method Java và đưa vào catalog:

~~~java
@Configuration(proxyBeanMethods = false)
public class AssistantConfiguration {

    @Bean
    ChatClient assistantChatClient(
            ChatClient.Builder builder,
            BusinessTools businessTools) {

        return builder
                .defaultTools(businessTools)
                .build();
    }
}
~~~

`ChatClient.Builder` được auto-configure dùng advisor thích hợp theo property đã bật. Đối với tool chỉ được phép ở một số request, dùng `.tools(...)` trong từng prompt sau khi backend đã lựa chọn danh sách hợp lệ, thay vì đưa tất cả vào `defaultTools(...)`.

## Cấu hình thủ công với ToolIndex

Nếu muốn tự kiểm soát cấu hình hoặc không dùng starter, thêm thư viện advisor:

~~~xml
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>spring-ai-tool-search-advisor</artifactId>
</dependency>
~~~

Một ví dụ dùng `RegexToolIndex`, không yêu cầu embedding model hoặc VectorStore:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.toolsearch.ToolSearchToolCallingAdvisor;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.tool.toolsearch.RegexToolIndex;

@Configuration(proxyBeanMethods = false)
public class ToolSearchConfiguration {

    @Bean
    ChatClient assistantChatClient(
            ChatModel chatModel,
            BusinessTools businessTools) {

        var advisor = ToolSearchToolCallingAdvisor.builder()
                .toolIndex(new RegexToolIndex())
                .maxResults(5)
                .sessionIdKeyName("toolCatalogSessionId")
                .build();

        return ChatClient.builder(chatModel)
                .defaultTools(businessTools)
                .defaultAdvisors(advisor)
                .build();
    }
}
~~~

Trong cách này, chương trình tạo đúng **một** advisor quản lý vòng tool calling: `ToolSearchToolCallingAdvisor` kế thừa `ToolCallingAdvisor`. `DefaultChatClient` phát hiện `ToolAdvisor` đã có và không thêm advisor mặc định lần nữa. Nếu đặt hai `ToolAdvisor` trong cùng chain, Spring AI sẽ báo lỗi thay vì cho cả hai cùng thực thi tool.

Mỗi lần gọi phải cung cấp session ID qua advisor context:

~~~java
public String ask(
        ChatClient chatClient,
        String question,
        String catalogSessionId,
        CurrentUser currentUser) {

    return chatClient.prompt()
            .user(question)
            .advisors(a -> a.param(
                    "toolCatalogSessionId",
                    catalogSessionId
            ))
            .toolContext(Map.of(
                    "tenantId", currentUser.tenantId(),
                    "userId", currentUser.userId()
            ))
            .call()
            .content();
}
~~~

`catalogSessionId` phải là một định danh riêng của người dùng và hội thoại do backend cấp hoặc xác nhận. Ví dụ này dùng key tùy chỉnh `toolCatalogSessionId` để không phụ thuộc hằng số memory context khác nhau giữa các phiên bản.

Nếu dùng cấu hình mặc định, Spring AI 2.0.x đọc conversation ID qua `ChatMemory.CONVERSATION_ID`, còn tài liệu Spring AI 2.1.0 mô tả `MemoryAdvisor.CONVERSATION_ID`. Khi nâng cấp, nên kiểm tra key được truyền thực tế và điều chỉnh `sessionIdKeyName(...)` nếu ứng dụng đã có quy ước riêng.

## Chọn ToolIndex phù hợp

`ToolIndex` là abstraction lưu và truy vấn những tham chiếu tool được phép dùng cho một session. Những method chính:

~~~java
public interface ToolIndex {

    void indexTool(String sessionId, ToolReference toolReference);

    void indexTools(String sessionId, List<ToolReference> toolReferences);

    ToolSearchResponse search(ToolSearchRequest request);

    void clearIndex(String sessionId);
}
~~~

Các kiểu `ToolIndex`, `ToolReference`, `ToolSearchRequest` và `ToolSearchResponse` nằm trong module `spring-ai-tool-search-tool`, package `org.springframework.ai.tool.toolsearch`. Đây là interface khái quát, không chứa logic business callback.

| Index | Phương pháp | Dependency | Khi phù hợp |
|---|---|---|---|
| `RegexToolIndex` | So khớp pattern/tên | Không cần thành phần ngoài | Tên tool quy củ, chỉ mục nhẹ |
| `LuceneToolIndex` | Keyword scoring | Lucene, starter có sẵn | Tìm nhanh bằng thuật ngữ rõ ràng |
| `VectorToolIndex` | Embedding semantic similarity | `VectorStore` bean và embedding phù hợp | Câu hỏi khác cách diễn đạt tên tool |
| `DecisionToolIndex`, từ 2.1.0 | Dùng `DecisionModel` chọn tool phù hợp và đánh giá có tool nào áp dụng không | `DecisionModel` bean | Muốn tránh đề xuất tool không phù hợp |

### Regex: cách bắt đầu ít phụ thuộc

~~~java
@Bean
ToolIndex toolIndex() {
    return new RegexToolIndex();
}
~~~

Chỉ mục regex hữu ích khi model có thể tìm theo tên hoặc pattern gần với tên tool. Với mô tả tiếng Việt dài và cách diễn đạt đa dạng, chỉ mục này có thể bỏ sót tool phù hợp; nên benchmark với catalog thực tế.

### Lucene: keyword retrieval

~~~java
@Bean
ToolIndex toolIndex() {
    return new LuceneToolIndex();
}
~~~

Lucene phù hợp khi tên/mô tả tool chứa các thuật ngữ người dùng hay nhắc. Có thể điều chỉnh minimum score threshold theo tài liệu. Khi hai tool có mô tả rất giống nhau, cần cải thiện tên và description để kết quả phân biệt được.

### Vector: tìm theo ngữ nghĩa

~~~java
@Bean
ToolIndex toolIndex(VectorStore vectorStore) {
    return new VectorToolIndex(vectorStore);
}
~~~

`VectorToolIndex` embed tên và mô tả tool để tìm theo similarity. Tùy `VectorStore`, cách cấu hình có thể bao gồm một embedding model, kết nối database và chi phí indexing. Tool đã được index vẫn phải được cập nhật khi thay đổi catalog.

### Decision: điều kiện 2.1.0

Spring AI 2.1.0 tài liệu hóa thêm `DecisionToolIndex`. Nó dùng một `DecisionModel` để trả lời “tool nào phù hợp?” và “có tool nào phù hợp không?”. Có thể không đề xuất tool nếu độ phù hợp thấp:

~~~java
@Bean
ToolIndex toolIndex(DecisionModel decisionModel) {
    return DecisionToolIndex.builder(decisionModel)
            .applicabilityThreshold(0.5)
            .minimumRelevance(0.0)
            .build();
}
~~~

Đây là ví dụ dành cho Spring AI **2.1.0** và cần `DecisionModel` phù hợp trong context. Không copy cấu hình `tool-index-type: decision` vào 2.0.2 vì trang reference 2.0.2 chỉ liệt kê Regex/Lucene/Vector.

Một đánh đổi quan trọng: với `DecisionToolIndex`, toàn bộ tool trong session có thể được gửi cho **decision model** ở mỗi lượt search. Nó phù hợp với hàng chục tool nhưng có thể trở nên tốn kém khi catalog quá lớn. Có thể shortlist bằng Vector/Lucene trước rồi dùng decision stage ở tập nhỏ hơn.

## Session ID, cache index và cập nhật danh mục

Spring AI lập chỉ mục theo **session ID**; session khác nhau có chỉ mục tách biệt. Tài liệu yêu cầu ứng dụng cung cấp session ID với từng request, mặc định qua key conversation ID của memory advisor hoặc qua key tùy chỉnh.

Một số thực hành quan trọng:

- Không dùng một session ID chung cho tất cả user của ứng dụng.
- Nếu một user có nhiều hội thoại với phạm vi quyền khác nhau, sử dụng ID đúng phạm vi của từng hội thoại.
- Khi user bị thu hồi quyền, phải cập nhật danh sách tool hợp lệ và loại bỏ index cũ.
- Không lấy session ID tùy tiện từ lời model tạo hoặc header không xác thực.
- Với multi-tenant, chọn ID khó đoán và gắn với principal/tenant hiện hành.

`ToolSearchToolCallingAdvisor` có bộ nhớ index theo session và có thể tái sử dụng giữa các lượt trong cùng conversation. Source/Javadoc mô tả cơ chế re-index khi bộ tool thay đổi theo fingerprint của tên và mô tả. Nhưng không nên dựa vào fingerprint này như một lớp phân quyền: role thay đổi mà tên/mô tả vẫn giống có thể cần chủ động loại bỏ index.

### Eviction và giới hạn bộ nhớ

Mặc định 2.1.0 sử dụng `LruEvictionStrategy(1000)`: giữ tối đa khoảng 1.000 session hoạt động và loại bỏ session ít được dùng khi vượt ngưỡng.

Có thể cấu hình TTL và LRU:

~~~yaml
spring:
  ai:
    chat:
      client:
        tool-search-advisor:
          enabled: true
          eviction:
            lru-max-sessions: 200
            ttl: 30m
~~~

Hoặc đặt trong builder thủ công:

~~~java
var advisor = ToolSearchToolCallingAdvisor.builder()
        .toolIndex(toolIndex)
        .evictionStrategy(
                new TtlEvictionStrategy(Duration.ofMinutes(30))
        )
        .build();
~~~

Các chiến lược được tài liệu hóa gồm `LruEvictionStrategy`, `TtlEvictionStrategy`, `AlwaysEvictStrategy`, `NeverEvictStrategy` và `CompositeEvictionStrategy`. Cách chọn phụ thuộc số session, tốc độ thay đổi catalog và chi phí re-index.

Khi người dùng đăng xuất hoặc bị thu hồi quyền, ứng dụng có thể giải phóng index của session:

~~~java
advisor.evictSession(catalogSessionId);
~~~

Việc eviction chủ yếu giải phóng/cập nhật chỉ mục tìm kiếm. Nó không hủy các tool nghiệp vụ đã thực thi và không thay thế việc kiểm tra quyền tại service.

## Tích hợp công cụ MCP trong catalog lớn

Một `ChatClient` có thể nhận local Java tools và `ToolCallbackProvider` từ MCP server. Với nhiều MCP server, catalog có thể lên hàng trăm tool. `ToolSearchToolCallingAdvisor` có thể lập chỉ mục những callback được cung cấp và đưa từng nhóm nhỏ cho model.

Ví dụ cấu hình request về mặt ý tưởng:

~~~java
return chatClient.prompt()
        .user(question)
        .tools(localOrderTools, allowedMcpToolProvider)
        .advisors(a -> a.param(
                "toolCatalogSessionId",
                catalogSessionId
        ))
        .call()
        .content();
~~~

`allowedMcpToolProvider` là provider đã được ứng dụng cấu hình và giới hạn đúng phạm vi. Việc bật Tool Search không tự tạo MCP connection hoặc tự cấp quyền đến mọi MCP server. MCP client phải kết nối, discover và chuyển MCP tools thành `ToolCallback` trước khi advisor có thể lập chỉ mục.

Một MCP server có thể thay đổi danh sách tool theo thời gian. Cần theo dõi việc thêm/xóa/đổi tên tool, thời điểm refresh provider và quyền user. Đừng giả định cache index có thể dùng vĩnh viễn cho mọi session.

## Bảo mật: tìm được tool không đồng nghĩa được phép gọi

Tool Search Tool giảm số định nghĩa được quảng bá cho model. Nó **không phải cơ chế authorization**. Nếu toàn bộ tool, kể cả tool ghi nhạy cảm, được đưa vào index của một user không có quyền, model có thể tìm thấy thông tin về chúng; tùy đường thực thi, điều này có thể dẫn tới yêu cầu gọi tool trái chính sách.

Quy tắc an toàn:

1. Xác thực user/tenant trước khi chọn catalog của request.
2. Chỉ lập chỉ mục những callback đã được phép **công bố** cho user đó.
3. Tách tool đọc và tool ghi; với thao tác thay đổi dữ liệu, dùng approval/confirmation phù hợp.
4. Kiểm tra quyền trong callback/service khi tool thực sự chạy.
5. Giới hạn callback resolver, tránh fallback tự phân giải tool ngoài tập được cấp cho request.
6. Xóa hoặc tái tạo session index khi quyền hoặc tenant context thay đổi.
7. Bảo vệ tên, mô tả, input schema nếu chúng chứa thông tin nội bộ không nên để model nhìn thấy.

Ví dụ cho request chỉ có quyền đọc:

~~~java
List<ToolCallback> allowedTools = toolCatalogPolicy
        .resolveForReadOnlyUser(authenticatedUser);

return chatClient.prompt()
        .user(question)
        .tools(allowedTools)
        .advisors(a -> a.param(
                "toolCatalogSessionId",
                sessionIdFor(authenticatedUser, conversationId)
        ))
        .call()
        .content();
~~~

`toolCatalogPolicy` và `sessionIdFor` là thành phần ứng dụng cần tự triển khai. Chúng phải dựa trên danh tính đã xác thực. Nếu user không có quyền tạo refund, tool tạo refund không được đưa vào index của session; đồng thời `RefundService` vẫn phải kiểm tra quyền khi thực thi bất kể tool có được quảng bá hay không.

### Không dùng Tool Search để lách các giới hạn của backend

- `ToolIndex` chỉ hỗ trợ tìm và trả `ToolReference`; nó không thực thi nghiệp vụ.
- `toolSearchTool` tìm công cụ theo metadata; nó không phải một endpoint cho model tự đọc toàn bộ code hoặc secret.
- `ToolCallingManager` vẫn thực thi callback đã được tìm thấy.
- `ToolContext` và authorization vẫn là trách nhiệm phía ứng dụng.
- Timeout, retry và idempotency của tool ghi vẫn phải được kiểm soát.

Nếu tool discovery thất bại, không nên tự động bật `resolution fallback` không giới hạn để “cứu” request, vì fallback có thể mở rộng tập callback được phép thực thi vượt ngoài catalog dự định.

## Chi phí và hiệu năng: đo cả retrieval lẫn tool loop

Số token tiết kiệm được có thể đáng kể khi catalog lớn. Tài liệu Spring AI 2.1.0 dẫn benchmark trên OpenAI, Anthropic và Gemini cho mức tiết kiệm token khoảng **34–64%** trong bài thử. Đây không phải bảo đảm cho mọi mô hình hoặc mọi khối lượng công việc.

Các đại lượng nên đo:

| Metric | Cần trả lời |
|---|---|
| Token prompt trước/sau | Tool definition giảm bao nhiêu? |
| Số lượt gọi model | Discovery làm tăng bao nhiêu lượt? |
| Độ trễ end-to-end | Tổng request nhanh hay chậm hơn? |
| Tỷ lệ chọn đúng tool | Model có tìm và gọi đúng công cụ không? |
| Search latency | Regex/Lucene/Vector/Decision tốn bao lâu? |
| Search miss rate | Khi nào index không tìm thấy tool phù hợp? |
| Tool execution errors | Công cụ được chọn có trả lỗi, timeout hoặc từ chối quyền không? |
| Cache re-index/eviction | Số session và việc cập nhật catalog ảnh hưởng ra sao? |

Đối với tác vụ chỉ dùng một tool đơn giản, thêm lượt `toolSearchTool` có thể làm request chậm hơn. Đối với catalog hàng trăm công cụ có schema dài, token tiết kiệm có thể lớn hơn chi phí của lượt discovery. Cần benchmark với câu hỏi thật, catalog thật và đúng model đang dùng.

## Kiểm thử ToolSearchToolCallingAdvisor

Nên kiểm tra riêng index, session, chuỗi tool calling và security.

### Kiểm thử ToolIndex

Với các `ToolReference` giả:

- Index hai tool có tên và mô tả khác nhau trong cùng session.
- Search bằng tên/pattern và xác minh trả đúng reference.
- Search với session khác và xác minh không nhìn thấy tool session trước.
- Gọi `clearIndex(sessionId)` và xác nhận session không còn reference.
- Với `VectorToolIndex`, test semantic query bằng embedding/vector store kiểm soát được.
- Với `DecisionToolIndex` 2.1.0, test trường hợp mô hình quyết định không có tool phù hợp.

### Kiểm thử vòng advisor

Dùng fake `ChatModel` hoặc stub model trả phản hồi theo kịch bản:

1. Model ở lượt đầu thấy `toolSearchTool` và không thấy toàn bộ tool nghiệp vụ.
2. Model gọi `toolSearchTool` với query “tra cứu đơn hàng”.
3. `ToolIndex` trả tham chiếu `getOrderStatus`.
4. Request tiếp theo chứa definition của `getOrderStatus`.
5. Model gọi `getOrderStatus` với input JSON đúng schema.
6. Callback chạy **một lần**, kết quả được đưa vào hội thoại.
7. Model tạo câu trả lời cuối mà không cần gọi thêm tool.

Kiểm tra thêm phiên bản streaming qua `.stream()` nếu ứng dụng cần trả chunk cho UI, vì advisor có hook riêng cho luồng reactive.

### Kiểm thử session, quyền và thay đổi catalog

- Hai user khác nhau không có chung session index.
- User mất quyền không còn tìm thấy tool đã bị rút khỏi catalog.
- Một request không có session ID được xử lý theo chính sách rõ ràng, không sử dụng index chung ngầm.
- Tool names trùng giữa local và MCP callback bị phát hiện.
- Provider MCP mất kết nối: advisor không tự thực thi tool chưa được cấp quyền.
- Catalog thay đổi giữa các lượt: index được refresh hoặc session bị evict.
- Công cụ ghi vẫn yêu cầu authorization và approval ở service.
- Khi Tool Search bị tắt, ứng dụng quay lại cơ chế cấp tool thông thường theo cấu hình.

### Kiểm thử cấu hình theo phiên bản

Với một module dùng Spring AI 2.0.2, không viết test phụ thuộc `DecisionToolIndex` hoặc property `tool-index-type: decision`. Nếu cần kiểm thử cả hai nhánh, duy trì dependency matrix hoặc CI profile riêng theo Spring AI BOM và classpath của từng nhánh.

Các test không cần gọi model thật nếu chỉ kiểm tra việc index/search và orchestration. Chỉ dùng integration test model thật khi cần đánh giá chất lượng truy vấn discovery, độ trễ và token thực tế.

## Lỗi thường gặp

- **Dùng Spring AI 1.x rồi bật property của 2.x:** class/starter Tool Search không nằm trong API công khai của nhánh cũ.
- **Dùng `DecisionToolIndex` trên 2.0.2:** strategy này được tài liệu 2.1.0 bổ sung.
- **Không có model hỗ trợ tool calling:** model không gọi được `toolSearchTool` nên không thể khám phá tool.
- **Quên session ID:** index không có khóa phạm vi rõ ràng để tái sử dụng đúng user và conversation.
- **Dùng một session ID cho nhiều tenant:** có thể lộ hoặc trộn danh mục tool.
- **Dùng Tool Search thay cho phân quyền:** tìm thấy definition không chứng minh quyền thực thi.
- **Đăng ký hai `ToolAdvisor` trong cùng chain:** tạo xung đột điều phối; dùng một advisor quản lý vòng tool calling.
- **Tưởng Tool Search tự discover mọi MCP server:** phải kết nối provider và cung cấp callback cho ChatClient.
- **Chọn Regex cho mọi truy vấn ngữ nghĩa:** tên tool không khớp cách diễn đạt có thể làm search miss.
- **Dùng Decision index cho hàng trăm tool mà không đo token:** decision model có thể nhận toàn bộ danh sách mỗi lượt search.
- **Không kiểm tra cache sau thay đổi quyền:** index cũ có thể còn tham chiếu tới tool không nên quảng bá.
- **Chỉ đếm token definition mà bỏ qua vòng search:** số lượt model và độ trễ có thể tăng.
- **Dùng native provider tool search như thể tương đương Spring AI advisor:** đó là API/phạm vi khác, cần kiểm tra theo provider.

## Checklist trước khi đưa vào production

- [ ] Spring AI BOM thuộc nhánh 2.x có `spring-ai-tool-search-advisor` tương ứng.
- [ ] Nếu dùng 2.0.x chỉ chọn Regex/Lucene/Vector theo tài liệu của bản đó.
- [ ] Nếu dùng `DecisionToolIndex` đã xác nhận Spring AI 2.1.0 và `DecisionModel` bean.
- [ ] Chat model thật hỗ trợ tool/function calling qua Spring AI.
- [ ] Starter và property enabled đã cấu hình, hoặc đã tạo advisor thủ công.
- [ ] Advisor chain chỉ có một `ToolAdvisor`.
- [ ] Tool callbacks được chọn theo user, tenant và phạm vi nghiệp vụ trước khi index.
- [ ] Request cung cấp session ID đúng ngữ cảnh.
- [ ] Có eviction/refresh khi logout, thu hồi quyền hoặc đổi catalog.
- [ ] Tên/mô tả tool đủ rõ để tìm và không trùng nhau.
- [ ] `ToolContext`, phân quyền và xác nhận thao tác ghi vẫn được kiểm soát tại backend.
- [ ] Có test index, discovery, execution, session isolation và streaming nếu áp dụng.
- [ ] Đã so sánh token, độ trễ, số lượt gọi model và độ chính xác với advisor mặc định.

## Ghi nhớ khi thiết kế

`ToolSearchToolCallingAdvisor` là một lựa chọn thay thế `ToolCallingAdvisor` trong **Spring AI 2.x**, dùng `toolSearchTool` và `ToolIndex` để chỉ công bố định nghĩa tool khi model cần. Nó phù hợp khi catalog lớn hoặc nhiều MCP server làm tăng token và gây khó chọn tool. Model phải hỗ trợ tool calling, session phải có định danh rõ ràng, và backend phải cung cấp trước một catalog đúng phạm vi.

Spring AI 2.0.x tài liệu hóa Regex, Lucene và Vector; Spring AI 2.1.0 có thêm Decision index. Property bật tính năng cần starter tương ứng và không thể áp dụng ngược cho 1.x. Tìm đúng tool chỉ là bước đầu: quyền truy cập, xác nhận thao tác, timeout, idempotency và bảo vệ session vẫn do ứng dụng thực thi chịu trách nhiệm.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Search Tool](https://docs.spring.io/spring-ai/reference/api/tools/tool-search-tool.html)
- [Spring AI 2.1.0 — Dynamic Tool Discovery Guide](https://docs.spring.io/spring-ai/reference/guides/dynamic-tool-search.html)
- [Spring AI 2.1.0 — Tool Calling & Scaling to Hundreds of Tools](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.0.2 — Tool Search Tool (ba chiến lược)](https://docs.spring.io/spring-ai/reference/2.0/api/tools/tool-search-tool.html)
- [Spring AI 2.0.0-RC1 Release — Tool Search Advisor](https://spring.io/blog/2026/06/06/spring-ai-2-0-0-RC1-available-now/)


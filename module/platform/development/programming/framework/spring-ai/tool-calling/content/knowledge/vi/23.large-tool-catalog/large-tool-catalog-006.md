# Lựa chọn chỉ mục và chất lượng truy xuất công cụ

Khi ứng dụng Spring AI chỉ có vài công cụ, có thể gửi toàn bộ tool definitions cho mô hình trong mỗi lượt. Nhưng nếu hệ thống tích hợp hàng chục hoặc hàng trăm công cụ từ các service nghiệp vụ và MCP server, mô hình phải đọc nhiều schema giống nhau, chi phí token tăng và xác suất chọn nhầm công cụ cũng tăng. Một cơ chế truy xuất công cụ giúp chọn tập ứng viên nhỏ trước khi mô hình quyết định công cụ nào cần gọi.

**Chọn chỉ mục (index) là chọn cách tìm ứng viên, không phải giao quyền thực thi.** Một công cụ xuất hiện ở đầu kết quả tìm kiếm không đồng nghĩa nó phù hợp, có quyền chạy hoặc có đủ arguments hợp lệ. Chất lượng cần được đo qua cả ba chặng: truy xuất đúng công cụ, mô hình chọn đúng công cụ và ứng dụng thực thi đúng nghiệp vụ.

Bài này tập trung vào Spring AI Tool Calling với danh mục công cụ lớn, sử dụng Spring AI 2.1.0 làm mốc API. Chúng ta sẽ so sánh RegexToolIndex, LuceneToolIndex, VectorToolIndex và DecisionToolIndex; thiết kế tập dữ liệu đánh giá; lựa chọn top-K/threshold; xử lý yêu cầu không cần công cụ; và kiểm soát quyền thực thi trong một hệ thống nhiều user hoặc tenant.

## Vị trí của chỉ mục trong vòng gọi công cụ

Spring AI 2.1.0 cung cấp ToolSearchToolCallingAdvisor để thực hiện progressive tool disclosure. Advisor này thay thế ToolCallingAdvisor thông thường và duy trì vòng model → tool → model. Thay vì gửi mọi tool definition ngay lập tức, nó đưa ra một tool tìm kiếm có tên toolSearchTool. Khi mô hình cần khả năng nào, nó gọi tool tìm kiếm bằng ngôn ngữ tự nhiên; ToolIndex trả về các công cụ phù hợp và advisor đưa những definitions được tìm thấy vào lượt tiếp theo.

~~~mermaid
flowchart TD
    A[User request] --> B[ChatClient và ToolSearchToolCallingAdvisor]
    B --> C[Index những tool của session]
    C --> D[Model thấy toolSearchTool]
    D --> E{Cần dùng công cụ?}
    E -- Không --> F[Trả lời trực tiếp]
    E -- Có --> G[Search query của mô hình]
    G --> H[ToolIndex.search]
    H --> I[Danh sách ToolReference top-K]
    I --> J[Đưa tool definitions vào lượt model sau]
    J --> K{Model chọn tool?}
    K -- Không --> F
    K -- Có --> L[ToolCallingManager kiểm tra và thực thi]
    L --> M[Tool result đưa lại model]
    M --> F
~~~

Kết quả search là danh sách ứng viên. ToolIndex không tự thực thi callback, không xác thực business rules và không thay thế kiểm tra authorization. Việc thực thi vẫn do ứng dụng và ToolCallingManager đảm nhiệm theo những tool callbacks được phép trong request.

### Khi nào đáng dùng tool search?

| Tình huống | Hướng lựa chọn |
|---|---|
| Dưới khoảng 10 tool, definitions ngắn | Thử ToolCallingAdvisor thông thường trước để tránh thêm một vòng tìm kiếm. |
| Nhiều tool có tên/description gần giống nhau | Đánh giá tool search vì mô hình có thể bị nhiễu khi thấy toàn bộ danh mục. |
| Catalog có nhiều MCP server hoặc hơn chục nghìn token schema | ToolSearchToolCallingAdvisor giúp giảm lượng definitions được gửi mỗi lượt. |
| Tool set nhỏ và hầu như tool nào cũng dùng | Search có thể tăng độ trễ mà không tiết kiệm đáng kể. |
| Catalog phân quyền theo tenant/role | Cần lọc tool hợp lệ trước khi lập chỉ mục và kiểm tra lại quyền lúc thực thi. |

Các ngưỡng là tín hiệu bắt đầu đánh giá, không phải quy tắc cứng. Thước đo quyết định vẫn là chất lượng và chi phí trên tập yêu cầu thật của ứng dụng.

## Index chính xác đang tìm trên dữ liệu nào?

Mỗi tool có thể có name, description, input schema, annotation và metadata nghiệp vụ. Không phải mọi ToolIndex đều tìm kiếm trên mọi trường.

Theo tài liệu Spring AI 2.1.0:

- RegexToolIndex tìm mẫu trên tên công cụ.
- LuceneToolIndex tìm từ khóa trong biểu diễn được lập chỉ mục của tool, phù hợp tên và mô tả.
- VectorToolIndex tạo embedding từ tên và mô tả tool để tìm theo ý nghĩa.
- DecisionToolIndex đưa các công cụ của session cho một decision model để lựa chọn và đánh giá khả năng có công cụ phù hợp.

Input schema đầy đủ vẫn cần thiết để mô hình tạo arguments sau khi tool được tìm thấy. Không mặc định suy ra các ví dụ, enum hoặc các ràng buộc field trong JSON schema đều đã được embed hay phân tích để xếp hạng.

### Chất lượng metadata ảnh hưởng trực tiếp chất lượng index

Hai công cụ sau rất khó phân biệt nếu description chung chung:

~~~java
@Tool(description = "Xử lý đơn hàng")
OrderResult getOrder(String orderId);

@Tool(description = "Xử lý đơn hàng")
OrderResult updateOrder(String orderId);
~~~

Nên mô tả rõ mục đích, điều kiện dùng và side effect:

~~~java
@Tool(description = """
    Tra cứu trạng thái hiện tại của đơn hàng theo mã.
    Chỉ đọc dữ liệu, không cập nhật đơn hoặc gửi thông báo.
    Dùng khi người dùng hỏi đơn đang ở đâu, trạng thái hoặc ngày giao dự kiến.
    """)
OrderSnapshot getOrderStatus(
        @ToolParam(description = "Mã đơn hàng được hệ thống cấp")
        String orderId);

@Tool(description = """
    Yêu cầu thay đổi trạng thái đơn hàng sau khi đã xác thực quyền
    và điều kiện chuyển trạng thái ở application service.
    Thao tác ghi có thể tạo side effect; chỉ dùng khi người dùng
    yêu cầu thay đổi đơn và đã đi qua bước xác nhận của ứng dụng.
    """)
UpdateOrderResult changeOrderStatus(
        @ToolParam(description = "Mã đơn hàng") String orderId,
        @ToolParam(description = "Trạng thái đích") String targetStatus);
~~~

Description không phải chính sách bảo mật. Dù mô hình có thấy cụm từ "chỉ dùng khi được xác nhận", service vẫn phải tự kiểm tra xác thực, quyền, điều kiện nghiệp vụ và cơ chế confirmation.

## Bốn chiến lược ToolIndex trong Spring AI 2.1.0

| Chỉ mục | Cách tìm | Ưu điểm | Giới hạn quan trọng |
|---|---|---|---|
| RegexToolIndex | Khớp mẫu trên tên tool. | Nhẹ, không cần embedding hay dịch vụ ngoài; phù hợp quy ước tên nghiêm ngặt. | Không hiểu ý nghĩa; mô tả bằng tiếng Việt có thể không khớp tên tiếng Anh. |
| LuceneToolIndex | Tìm lexical/keyword. | Nhanh, dễ kiểm soát, hợp với mã/tên/thuật ngữ đặc thù. | Dễ bỏ sót cách diễn đạt khác từ vựng; tokenizer/ngôn ngữ cần được đánh giá. |
| VectorToolIndex | Embedding và similarity. | Bắt được diễn đạt tự nhiên, đồng nghĩa hoặc mô tả khác tên tool. | Chi phí indexing/search, phụ thuộc embedding model và vector store; đôi khi gần nghĩa nhưng sai chức năng. |
| DecisionToolIndex | Dùng decision model xét ứng viên và tính phù hợp. | Chọn công cụ theo nhiệm vụ và có khả năng trả về không công cụ. | Có thêm lượt model, độ trễ/chi phí; đưa catalog ứng viên vào decision model. |

Một câu hỏi như “Cho xem đơn này đang giao đến đâu” có thể không chứa chính xác từ khóa getOrderStatus. Vector index hoặc decision model có thể tìm đúng hơn. Ngược lại, truy vấn “tìm invoice INV-2026-0841” có định danh rõ, keyword search dễ kiểm soát hơn.

### RegexToolIndex: tên tool theo mẫu

RegexToolIndex phù hợp khi mô hình hoặc tầng router có thể tạo query gần với quy ước tên, ví dụ get_order_*, search_invoice_* hoặc một namespace rõ. Nó thường không phù hợp với yêu cầu tiếng Việt tự nhiên có nhiều cách diễn đạt.

~~~java
@Bean
ToolIndex toolIndex() {
    return new RegexToolIndex();
}
~~~

Đây là index mặc định khi bật auto-configuration nhưng chưa chọn loại. Nếu catalog của bạn dùng tên camelCase tiếng Anh còn người dùng hỏi tiếng Việt, hãy đo tỷ lệ bỏ sót trước khi giữ mặc định.

### LuceneToolIndex: từ khóa và thuật ngữ chính xác

Lucene phù hợp catalog có thuật ngữ ổn định như invoice, customer, booking, shipment, refund hoặc mã dịch vụ. Không cần embedding model.

~~~java
@Bean
ToolIndex toolIndex() {
    return new LuceneToolIndex(0.4f);
}
~~~

Theo tài liệu, ngưỡng điểm tối thiểu mặc định là 0.25; ví dụ trên tăng lên 0.4 để loại hit điểm thấp. Điểm Lucene phản ánh thuật toán tìm kiếm lexical, không phải xác suất rằng tool đúng. Không so trực tiếp điểm Lucene 0.4 với cosine similarity 0.4 hoặc xác suất của DecisionToolIndex.

Tăng threshold thường làm kết quả chọn lọc hơn nhưng có nguy cơ giảm recall. Hạ threshold giúp giữ nhiều ứng viên hơn nhưng có thể đưa tool gây nhiễu đến model. Cần tune bằng tập dữ liệu đã gán nhãn.

### VectorToolIndex: diễn đạt theo ý nghĩa

Vector index chuyển tên/mô tả tool thành embedding. Query được embed và tìm các vector gần nhất.

~~~java
@Bean
ToolIndex toolIndex(VectorStore vectorStore) {
    return new VectorToolIndex(vectorStore);
}
~~~

Yêu cầu một VectorStore đã cấu hình cùng embedding provider tương thích. Nếu dùng vector database chung với tài liệu RAG, cần phân vùng dữ liệu/tool index hợp lý để không tìm nhầm document chunk như tool reference.

Vector hữu ích cho paraphrase:

| Người dùng nói | Tool có thể phù hợp |
|---|---|
| “Đơn của tôi đã tới kho nào?” | getShipmentTracking |
| “Kho còn đủ hàng để giao không?” | checkAvailableInventory |
| “Có thể lấy lại tiền đơn bị hủy không?” | getRefundEligibility hoặc requestRefund tùy ý định đọc/ghi |

Hai tool getRefundEligibility và requestRefund có thể gần nhau về embedding nhưng tác động khác hẳn. Vector similarity không tự xác định người dùng đang hỏi thông tin hay yêu cầu thực hiện refund; cần metadata phân biệt và kiểm tra ở tầng model/service.

### DecisionToolIndex: chọn ứng viên và từ chối khi không phù hợp

DecisionToolIndex dùng DecisionModel để xem công cụ nào thực sự khớp yêu cầu. Nó có hai đánh giá: tool phù hợp nhất và có tool nào phù hợp hay không. Khi khả năng có tool phù hợp dưới applicability threshold, search có thể trả danh sách rỗng.

~~~java
@Bean
ToolIndex toolIndex(DecisionModel decisionModel) {
    return DecisionToolIndex.builder(decisionModel)
            .applicabilityThreshold(0.7)
            .minimumRelevance(0.05)
            .build();
}
~~~

Mặc định applicability threshold là 0.5 và minimumRelevance là 0.0. Chọn ngưỡng cao hơn khi việc đưa nhầm công cụ ghi dữ liệu nguy hiểm hơn việc phải hỏi thêm hoặc trả lời không có tool. Tuy nhiên, đây vẫn là kết quả dự đoán của model, không phải cơ chế thực thi an toàn tuyệt đối.

DecisionToolIndex nhận các tool của session vào mỗi lượt đánh giá. Nếu có hàng trăm tool và definitions dài, dùng một index rẻ hơn để tạo shortlist trước rồi mới dùng decision model để rerank là thiết kế có thể cân nhắc; nếu tự kết hợp cần viết adapter/pipeline riêng, không mặc định có built-in hybrid reranker.

## Lựa chọn chiến lược qua ma trận nhu cầu

| Dấu hiệu từ dữ liệu thực tế | Ưu tiên thử đầu tiên | Thử tiếp nếu chưa đạt |
|---|---|---|
| Query đã chứa tên API/tool hoặc quy ước namespace | Regex | Lucene nếu có nhiều tên gần nhau |
| Query có mã và thuật ngữ nghiệp vụ cố định | Lucene | Vector cho paraphrase |
| Query tiếng Việt, tên tool tiếng Anh, nhiều từ đồng nghĩa | Vector | Decision rerank sau shortlist |
| Nhiều tool cùng lĩnh vực nhưng khác quyền/tác động | Decision và guard ứng dụng | Tách read/write, cải thiện description, shortlist theo domain |
| Query thường không cần tool | Decision với no-tool threshold | Quy tắc abstention ở tầng router |
| Catalog rất lớn, phải giảm latency và tiền model | Lexical/semantic shortlist | Decision chỉ trên top candidates |
| Model/embedding không sẵn sàng hoặc chi phí rất chặt | Regex/Lucene | Dùng description rõ và filter theo domain |

Nên triển khai baseline rẻ trước, thu dữ liệu truy xuất sai, rồi mới nâng cấp sang embedding hoặc decision model. Không chọn Vector chỉ vì có sẵn vector database; phải chứng minh nó cải thiện Recall@K hoặc kết quả nhiệm vụ.

## Kết nối ToolSearchToolCallingAdvisor

Có thể bật bằng Spring Boot starter:

~~~xml
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>spring-ai-starter-tool-search-advisor</artifactId>
</dependency>
~~~

Ví dụ application.properties:

~~~properties
spring.ai.chat.client.tool-search-advisor.enabled=true
spring.ai.chat.client.tool-search-advisor.tool-index-type=lucene
spring.ai.chat.client.tool-search-advisor.max-results=5
spring.ai.chat.client.tool-search-advisor.lucene.min-score-threshold=0.4
spring.ai.chat.client.tool-search-advisor.eviction.ttl=30m
~~~

Trong cấu hình này, starter tạo ToolSearchToolCallingAdvisor thay cho ToolCallingAdvisor mặc định khi không có bean cấu hình tùy chỉnh khác. Đừng tự đăng ký thêm ToolAdvisor thứ hai vào cùng advisor chain; Spring AI áp dụng giới hạn chỉ một ToolAdvisor để tránh double execution.

Ví dụ cấu hình thủ công:

~~~java
@Configuration
class ToolSearchConfig {

    @Bean
    ChatClient chatClient(
            ChatModel chatModel,
            OrderTools orderTools,
            InvoiceTools invoiceTools) {

        ToolIndex index = new LuceneToolIndex(0.4f);
        var searchAdvisor = ToolSearchToolCallingAdvisor.builder()
                .toolIndex(index)
                .maxResults(5)
                .build();

        return ChatClient.builder(chatModel)
                .defaultTools(orderTools, invoiceTools)
                .defaultAdvisors(searchAdvisor)
                .build();
    }
}
~~~

Khi gọi, truyền một session ID duy nhất và ổn định cho conversation:

~~~java
String answer = chatClient.prompt()
        .user("Kiểm tra đơn ORD-001 đang giao tới đâu")
        .advisors(a -> a.param(
                MemoryAdvisor.CONVERSATION_ID,
                authenticatedConversationId))
        .call()
        .content();
~~~

Tool search index được phân phạm vi theo session. Session ID phải được ứng dụng tạo/xác thực, gắn với user và tenant; không tin một ID tùy ý do model hoặc request chưa xác thực cung cấp. Đổi role hoặc thu hồi quyền cần làm mới tập công cụ và kiểm soát session index đang tồn tại.

## ToolIndex API và khả năng tùy chỉnh

Spring AI cung cấp interface:

~~~java
public interface ToolIndex {
    void indexTool(String sessionId, ToolReference toolReference);
    void indexTools(String sessionId, List<ToolReference> toolReferences);
    ToolSearchResponse search(ToolSearchRequest request);
    void clearIndex(String sessionId);
}
~~~

ToolSearchRequest mang sessionId, query, maxResults và categoryFilter tùy chọn. Hỗ trợ categoryFilter tùy index; không dùng filter này làm ranh giới authorization vì có triển khai chỉ xem nó như gợi ý tìm kiếm hoặc bỏ qua nếu không khớp.

Custom ToolIndex có thể phục vụ nhu cầu đặc biệt như catalog theo tenant, phân vùng theo domain hoặc kết hợp nhiều index. Khi cài custom index phải bảo vệ tính nhất quán giữa những thao tác lập chỉ mục, tìm kiếm và clearIndex dưới tải đồng thời.

## Chất lượng truy xuất không chỉ là tool đầu tiên

Một hệ thống có thể trả đúng tool ở top 5 nhưng mô hình lại gọi nhầm tool ở vị trí thứ hai. Hoặc index trả đúng tool nhưng mô hình tạo sai argument, làm service từ chối yêu cầu. Cần phân biệt các tầng chất lượng:

| Tầng | Câu hỏi cần trả lời | Cách đánh giá |
|---|---|---|
| Tập tool hợp lệ | Tool mà user có quyền dùng đã được đưa vào catalog chưa? | Kiểm tra allowlist và nhãn quyền. |
| Retrieval | Tool cần thiết có nằm trong top-K không? | Recall@K, Hit@K, MRR, nDCG@K. |
| Selection | Sau khi thấy definitions, model có chọn đúng tool hoặc không dùng tool không? | Tool-choice accuracy, wrong-tool rate, abstention. |
| Arguments | Model có tạo arguments hợp schema, đúng field và giá trị không? | Schema-valid rate, field accuracy, business validation. |
| Execution | Service có cho phép chạy, thực thi an toàn và cho kết quả đúng không? | Authorized-execution rate, success/error metrics, side-effect tests. |
| Trải nghiệm | Toàn bộ request có đủ nhanh, đáng tin và tiết kiệm không? | End-to-end success, p95 latency, model tokens, chi phí. |

Nếu chỉ báo cáo model trả lời cuối có vẻ đúng, rất khó biết lỗi bắt nguồn từ index hay mô hình. Nếu chỉ báo cáo Recall@5 mà bỏ qua wrong-tool execution, hệ thống có thể vô tình tăng nguy cơ gọi nhầm công cụ cập nhật dữ liệu.

## Tạo bộ dữ liệu đánh giá (golden set)

Tập test phải mô phỏng cách người dùng hỏi thật, gồm câu ngắn, paraphrase, lỗi chính tả, tiếng Việt/Anh trộn, tên nghiệp vụ, truy vấn nhiều bước và yêu cầu không nên gọi tool.

Mỗi trường hợp nên lưu tối thiểu:

- Mã testcase và câu yêu cầu gốc.
- User role, tenant và tập tool hợp lệ của request.
- Danh sách công cụ đúng (gold relevant tools), có thể nhiều tool.
- Nhãn read-only/write, mức độ rủi ro và điều kiện confirmation.
- Có cần dùng tool không; nếu không, gold set là rỗng.
- Danh sách hard negatives: tool gần giống tên hoặc ý nghĩa nhưng sai chức năng.
- Kết quả mong đợi nếu dùng tool, cùng những field argument quan trọng.

Ví dụ bộ test rút gọn:

| Yêu cầu | Gold tools | Hard negatives | Ghi chú |
|---|---|---|---|
| “Đơn ORD-321 đã tới kho nào?” | getShipmentTracking | changeOrderStatus | Chỉ đọc. |
| “Đơn ORD-321 đang ở trạng thái gì?” | getOrderStatus | cancelOrder | Chỉ đọc. |
| “Hóa đơn INV-82 đã thanh toán chưa?” | getInvoiceStatus | createInvoice | Không tạo hóa đơn. |
| “Tôi có được hoàn tiền không?” | getRefundEligibility | issueRefund | Đọc điều kiện, chưa yêu cầu hoàn tiền. |
| “Hủy đơn ORD-321 giúp tôi.” | requestOrderCancellation | getOrderStatus | Có side effect; confirmation và permission riêng. |
| “Cho biết thời tiết cuối tuần.” | weatherForecast nếu ứng dụng có tool này | getOrderStatus | Không nên lôi tool đơn hàng vào. |
| “Giải thích transaction trong Spring.” | Không tool | searchOrders | Có thể trả lời bằng kiến thức, không dùng service nghiệp vụ. |
| “Xem đơn của tenant khác.” | Không tool được phép | getOrderStatus | Bắt buộc chặn truy xuất trái quyền, kể cả query trùng tên. |
| “Tạo hóa đơn rồi gửi email xác nhận.” | createInvoice, sendInvoiceEmail hoặc một workflow tool | getInvoiceStatus | Có thể cần nhiều tool/luồng phối hợp. |

Với mỗi intent, thêm biến thể theo ngôn ngữ, từ đồng nghĩa, tên viết tắt và cách người dùng nhắc đến mã. Nên giữ tỷ lệ đáng kể hard negatives và no-tool cases để test khả năng từ chối, không chỉ khả năng tìm một kết quả gần nhất.

### Gán nhãn nhiều công cụ đúng

Một yêu cầu có thể có nhiều đường xử lý hợp lệ, ví dụ read-only searchInvoice và getInvoiceStatus đều giúp trả lời câu hỏi tra cứu tùy schema. Khi gán nhãn cần phân biệt:

- **Essential:** công cụ bắt buộc để hoàn thành yêu cầu.
- **Acceptable alternative:** công cụ khác cũng hoàn thành mục tiêu an toàn.
- **Related but insufficient:** liên quan nhưng không đủ để hoàn thành.
- **Wrong or unsafe:** công cụ sai ý định, sai quyền hoặc tạo side effect không được yêu cầu.

Không coi tất cả tên tool cùng xuất hiện trong một chủ đề là relevant. Một tool phát lệnh refund không tương đương với tool kiểm tra điều kiện refund.

## Các chỉ số retrieval cần đo

Cho một testcase có tập công cụ đúng G và danh sách kết quả truy xuất có thứ tự R. Ký hiệu R@K là tối đa K kết quả đầu tiên.

**Hit@K:** bằng 1 nếu trong K kết quả đầu có ít nhất một công cụ đúng, ngược lại bằng 0. Trung bình các testcase cho biết tỷ lệ truy vấn tìm được ít nhất một công cụ đúng.

**Recall@K:** số công cụ đúng xuất hiện trong R@K chia cho tổng số công cụ đúng trong G:

~~~text
Recall@K = |G ∩ R@K| / |G|
~~~

Recall@K quan trọng cho câu hỏi nhiều công cụ. Nếu câu hỏi cần cả getOrderStatus và getShipmentTracking, trả một trong hai ở top 5 chỉ đạt Recall@5 = 0.5.

**Precision@K:** số công cụ đúng ở top K chia cho K. Khi index trả ít hơn K kết quả, nên công bố cả số kết quả thực tế để tránh hiểu sai cách tính.

~~~text
Precision@K = |G ∩ R@K| / K
~~~

**MRR (Mean Reciprocal Rank):** trung bình nghịch đảo vị trí của công cụ đúng đầu tiên. Nếu công cụ đúng đầu ở vị trí 1 thì điểm trường hợp đó là 1; ở vị trí 4 thì là 0.25; không có trong tập kết quả thì là 0.

**nDCG@K:** đánh giá mức độ liên quan có thứ bậc. Phù hợp khi một số tool là lựa chọn tốt nhất, còn tool khác chỉ chấp nhận được. Cần định nghĩa thang relevance nhất quán trước khi tính.

Các metric trên thường áp dụng cho testcase có ít nhất một tool relevant. Với testcase gold rỗng, phải tính metric riêng cho không có tool phù hợp.

### Vì sao chỉ đo Recall@K chưa đủ?

Giả sử index A trả:

~~~text
1. issueRefund
2. getRefundEligibility
3. getPaymentStatus
~~~

Index B trả:

~~~text
1. getRefundEligibility
2. getPaymentStatus
3. issueRefund
~~~

Nếu người dùng chỉ hỏi “Tôi có được hoàn tiền không?”, cả A và B có thể đạt Hit@3 = 1. Nhưng B an toàn và hợp ý định hơn vì read-only tool đứng đầu. MRR và graded relevance phản ánh thứ tự tốt hơn, còn wrong-tool execution rate cho biết mô hình có thực sự gọi nhầm issueRefund hay không.

## Đánh giá yêu cầu không cần tool

Một chỉ mục semantic thường luôn có vài vector gần query nhất, kể cả khi query hoàn toàn không liên quan. Lucene cũng có thể trả một hit yếu nếu threshold thấp. Vì thế cần đánh giá khả năng trả danh sách rỗng hoặc để model không gọi tool sau khi search.

Tạo bộ no-tool cases bao gồm:

- Câu hỏi kiến thức chung và giải thích khái niệm.
- Yêu cầu ngoài phạm vi nghiệp vụ của catalog.
- Yêu cầu không đủ thông tin để chọn tool.
- Yêu cầu bị cấm bởi role/tenant hoặc đang cần confirmation.
- Yêu cầu muốn biết điều kiện, chưa muốn thực thi side effect.

Đo ít nhất:

| Metric | Ý nghĩa |
|---|---|
| No-tool accuracy | Tỷ lệ câu gold không cần tool mà hệ thống không gọi tool nghiệp vụ. |
| False tool proposal rate | Tỷ lệ câu no-tool mà index đưa ứng viên không phù hợp. |
| False tool execution rate | Tỷ lệ câu no-tool cuối cùng dẫn đến callback sai chạy thật. |
| Coverage | Tỷ lệ câu có tool đúng mà hệ thống tìm được tool phù hợp. |
| Abstention precision | Khi hệ thống nói không có tool, tỷ lệ quyết định đó đúng. |

DecisionToolIndex hỗ trợ applicability threshold giúp không trả tool khi model đánh giá không có công cụ phù hợp. Nhưng false negative cũng có thể tăng nếu threshold quá cao. Khi không có ứng viên, ứng dụng nên trả lời trong phạm vi kiến thức hoặc hỏi làm rõ; không tự bật quyền chạy mọi tool để cứu một kết quả tìm kiếm trống.

## Chọn top-K và threshold theo rủi ro

Tham số maxResults kiểm soát số tool references được trả về trong một lượt search. K nhỏ giảm token và nhiễu nhưng dễ bỏ sót công cụ đúng; K lớn tăng Recall và chi phí, có thể làm model khó phân biệt.

Đánh giá K = 1, 3, 5, 10 trên cùng một golden set và cùng model. Ghi lại:

1. Recall@K và Hit@K.
2. MRR/nDCG@K.
3. Tool-choice accuracy sau retrieval.
4. No-tool false positive.
5. Tool definition tokens, search latency và tổng chi phí.

Ví dụ bảng số liệu **giả định để minh họa cách đánh đổi**, không phải benchmark Spring AI:

| K | Recall@K | Wrong-tool execution | Tool tokens trung bình | Nhận xét |
|---|---|---|---|---|
| 1 | 0.78 | 0.02 | 500 | Nhanh nhưng bỏ sót câu nhiều tool. |
| 3 | 0.91 | 0.03 | 1.200 | Cân bằng hơn. |
| 5 | 0.96 | 0.05 | 1.900 | Recall cao hơn, nhiều ứng viên nhiễu hơn. |
| 10 | 0.98 | 0.09 | 3.500 | Ít tăng Recall nhưng tăng nhầm lẫn. |

Không chọn K=5 chỉ vì tài liệu ví dụ dùng 5. Nếu catalog có nhiều tool cùng domain hoặc workflow cần nhiều tool, K tối ưu có thể khác. Với tool ghi dữ liệu, wrong-tool execution cần có ngưỡng chấp nhận rất thấp và cơ chế bảo vệ độc lập.

### Cách tuning threshold

Với Lucene, tăng min-score-threshold từ mặc định 0.25 để giảm kết quả yếu rồi kiểm tra Recall. Với DecisionToolIndex, chỉnh applicabilityThreshold và minimumRelevance theo tập no-tool và hard-negative. Với VectorToolIndex, chọn top-K và nếu cần tự đặt ngưỡng similarity ở tầng index/adapter tùy VectorStore và mô hình embedding.

Không dùng một con số threshold chung cho tất cả loại chỉ mục. Điểm Lucene, điểm tương tự vector và xác suất DecisionModel có thang đo/ý nghĩa khác nhau.

## Kết hợp lexical, semantic và decision model

Với catalog lớn, một pipeline hai tầng thường hợp lý hơn bắt decision model đọc hàng trăm tool:

~~~mermaid
flowchart LR
    A[Query] --> B[Auth và capability filter]
    B --> C[Lexical hoặc Vector retrieval]
    C --> D[Top 10-20 candidates]
    D --> E[Decision model hoặc reranker]
    E --> F[Top 1-5 phù hợp]
    F --> G[Model tool selection]
    G --> H[Execution authorization]
~~~

Đây là kiến trúc mở rộng do ứng dụng triển khai nếu cần, không phải một class hybrid mặc định trong Spring AI 2.1.0.

Có thể kết hợp kết quả Lucene và Vector theo reciprocal rank fusion (RRF), dựa trên thứ hạng thay vì trộn trực tiếp score không cùng thang:

~~~text
RRF(tool) = SUM[ 1 / (c + rank_in_index(tool)) ]
~~~

Trong đó c là hằng số làm phẳng ảnh hưởng của vị trí đầu; chỉ cộng trên các index thực sự trả tool. Sau khi hợp nhất, áp metadata/authorization filters và quyết định rerank nếu cần. Khi dùng nhiều index, nhớ giải quyết trùng tên tool và khác namespace/MCP server; định danh nội bộ nên ổn định hơn tên hiển thị.

### Khi nào cần rerank?

Rerank giúp khi ứng viên đều gần nghĩa nhưng khác tác động nghiệp vụ:

- getInvoiceStatus so với createInvoice.
- lookupCustomer so với deleteCustomer.
- checkRefundEligibility so với issueRefund.
- getShipmentTracking so với cancelShipment.

Reranker phải nhìn thấy description và thông tin mô tả read/write/risk để phân biệt. Vẫn phải có execution gate độc lập vì model rerank có thể sai.

## Catalog hợp lệ phải được lọc trước khi index

Hãy tạo tập công cụ ứng viên từ giao của ba điều kiện:

~~~text
EligibleTools(request)
  = RegisteredTools
    ∩ ToolsAllowedByPrincipalAndTenant
    ∩ ToolsEnabledForWorkflow
~~~

Chỉ những công cụ hợp lệ của request mới nên được đưa vào session index. Ngoài quyền, có thể giới hạn theo domain, trạng thái feature flag hoặc giai đoạn nghiệp vụ; nhưng cần phân biệt filter cứng theo quyền với filter mềm theo độ liên quan.

Không chỉ lập chỉ mục tất cả công cụ rồi trông chờ truy vấn semantic không tìm ra công cụ nhạy cảm. Mô tả và tên tool có thể tiết lộ khả năng nội bộ, trong khi execution vẫn là rủi ro nếu có lỗ hổng resolver.

### Kiểm tra lại trước lúc callback chạy

Ngay cả khi index được lọc đúng, quyền của user có thể thay đổi giữa lúc search và lúc model gọi tool. Application service phải kiểm tra:

- User và tenant thực sự sở hữu tài nguyên hay có quyền thao tác.
- Tool hiện vẫn được phép chạy trong workflow.
- Input schema và business constraints hợp lệ.
- Confirmation hoặc approval với thao tác có side effect.
- Rate limit, quota, idempotency và audit khi cần.

Spring AI có tùy chọn resolution fallback. Mặc định spring.ai.tools.resolution.fallback.enabled=false nên manager chỉ chạy tool gắn với request. Nếu bật fallback, ToolCallbackResolver có thể resolve tool theo tên ngay cả khi tool đó không được attach vào request. Điều này có thể vượt qua tập ứng viên đã chọn; chỉ bật khi resolver giới hạn chính xác quyền của request.

### Session ID, cache và thu hồi quyền

ToolSearchToolCallingAdvisor lưu index theo session. Mặc định có LruEvictionStrategy(1000); cũng hỗ trợ TTL, AlwaysEvict, NeverEvict và gọi advisor.evictSession(sessionId) để giải phóng index.

Không dùng chung một session ID cho hai người dùng khác nhau. Nếu user đổi role, logout hoặc bị thu hồi quyền, cập nhật tool catalog và chủ động evict session khi cần. Chế độ tích lũy tên tool đã khám phá referenceToolNameAccumulation mặc định true giúp làm nhiều việc qua nhiều lượt, nhưng càng cần kiểm tra quyền tại execution vì tool từng được phép có thể không còn được phép.

Fingerprint tên/mô tả được advisor dùng để nhận biết thay đổi tool set và reindex, nhưng không được dựa vào nó như một cơ chế thu hồi quyền. Session và request context vẫn phải phản ánh quyền hiện tại.

## Vòng đời index và chất lượng khi catalog thay đổi

Catalog động có thể thay đổi khi:

- Deploy công cụ mới, đổi tên hoặc mô tả.
- Một MCP server mất kết nối hoặc thêm công cụ.
- Quyền user/tenant đổi.
- Feature flag bật/tắt.
- Embedding model hoặc cách tokenize thay đổi.

Một lần indexing cũ có thể khiến search trả tool không còn hiện hữu hoặc bỏ sót tool mới. Nên quản lý catalog version, reindex policy và kiểm tra lỗi tìm kiếm khi tool bị bỏ.

| Biến động | Điều cần kiểm tra |
|---|---|
| Tool mới được thêm | Nó xuất hiện trong kết quả query liên quan sau khi catalog refresh. |
| Tool bị disable | Nó biến mất khỏi search và bị chặn khi cố dispatch. |
| Description được chỉnh | Các query liên quan đổi ranking theo kỳ vọng. |
| Role bị thu hồi | Session cũ không còn thực thi tool bị cấm. |
| Vector model được đổi | Re-embed, không trộn vector cũ/mới thiếu tương thích. |
| MCP server offline | Có lỗi rõ, fallback an toàn và không gọi nhầm tool cùng tên từ server khác. |

Nên thử chạy hai phiên bản index với cùng golden set trước khi áp dụng toàn bộ, đặc biệt khi đổi embedding model hoặc sửa nhiều tool descriptions.

## Đo hiệu năng thực tế

Tách thời gian và chi phí của các công đoạn:

| Chỉ số | Cách dùng |
|---|---|
| Index build/refresh time | Độ trễ khởi tạo session và chi phí embedding. |
| Search latency p50/p95/p99 | Khả năng đáp ứng khi người dùng hỏi. |
| Decision-model latency | Giá phải trả cho một vòng rerank hoặc abstention. |
| Search tool calls per turn | Số lần model phải tìm công cụ trước khi chọn được. |
| Indexed tools per session | Kích thước catalog thực tế, ảnh hưởng memory và cost. |
| Search top-K size | Số candidates thực trả, có thể nhỏ hơn maxResults. |
| Tool definition tokens | Token tiết kiệm hoặc tiêu thụ khi mở rộng definitions. |
| End-to-end user-turn latency | Tác động tổng hợp, bao gồm thêm một hay nhiều model round-trip. |
| Wrong tool / denied tool | Tín hiệu lỗi retrieval hoặc policy/authorization. |

Theo tài liệu Spring AI, benchmark ví dụ cho progressive disclosure có báo cáo mức giảm token trong khoảng 34–64% trên một số cấu hình mô hình. Đây là kết quả thử nghiệm cụ thể, không phải cam kết cho mọi catalog. Tính lại với tập tool và provider của ứng dụng; đo cả token lẫn độ trễ thêm của search.

Log nên giữ request/run ID, session ID đã ẩn danh, loại index, catalog version, tên tool candidates và điểm/rank phù hợp. Không ghi raw tool arguments, nội dung nhạy cảm, tenant secret hoặc dữ liệu cá nhân chỉ để tính metric.

## Thiết kế kiểm thử offline và end-to-end

### Test retrieval offline

Tách ToolIndex khỏi model sinh câu trả lời. Tạo session đánh giá, index tool references cố định và thực hiện cùng một bộ search queries. Thu toolReferences từ ToolSearchResponse để tính Recall@K, MRR, nDCG@K và các chỉ số no-tool.

~~~java
ToolSearchRequest request = new ToolSearchRequest(
        "eval-session-001",
        "Tra cứu trạng thái giao hàng của đơn ORD-321",
        5,
        null
);

ToolSearchResponse response = toolIndex.search(request);

List<String> retrievedToolNames = response.toolReferences().stream()
        .map(ToolReference::toolName)
        .toList();
~~~

Đây là phần đo index. Nó không xác minh model thực sự gọi tool nào. Cần indexTools cho session trước khi search, và clearIndex hoặc dùng session ID riêng cho mỗi ca thử nghiệm để tránh nhiễm dữ liệu.

### Test chọn công cụ của mô hình

Chạy cùng dataset qua ChatClient với ToolSearchToolCallingAdvisor. Dùng fake ToolCallbacks hoặc service sandbox để ghi nhận tool name và arguments mà không thực hiện side effect thật. Kiểm tra:

1. Model có gọi toolSearchTool khi cần không?
2. Từ kết quả search, model có gọi đúng tool nghiệp vụ không?
3. Với câu no-tool, model có dừng mà không gọi tool nghiệp vụ không?
4. Arguments hợp schema và đáp ứng yêu cầu nghiệp vụ không?
5. Với nhiều tool cần thiết, tool nào được gọi, thứ tự có hợp lệ không?
6. Với tool ghi dữ liệu, authorization và confirmation có chặn đúng không?

Lặp lại nhiều lần hoặc dùng nhiều seed nếu provider hỗ trợ, vì kết quả model có thể dao động. Báo cáo cả trung bình, phân phối và số lượng case. Không dùng một vài prompt thử tay làm bằng chứng rằng strategy đã tốt.

### Nhóm tình huống cần có trong regression suite

| Nhóm | Kết quả cần xác minh |
|---|---|
| Exact tool name | Regex/Lucene tìm được công cụ theo tên chuẩn. |
| Từ đồng nghĩa tiếng Việt | Vector/Decision giữ Recall khi tên tool tiếng Anh. |
| Query chứa mã, viết tắt | Lucene không bỏ sót vì tokenizer hoặc dấu câu. |
| Read vs write | Query đọc không làm model thực thi tool ghi. |
| Hard negatives | Tool tên rất giống nhau được phân biệt đúng. |
| No-tool query | Không đề xuất/call tool nghiệp vụ sai. |
| Multi-tool request | Recall cho đầy đủ các tool thiết yếu. |
| Role/tenant khác nhau | Không hiển thị hoặc thực thi tool ngoài quyền. |
| Role bị thu hồi giữa session | Session eviction và execution guard có hiệu lực. |
| Catalog đổi tên/description | Index được cập nhật theo dữ liệu mới. |
| MCP tool bị gỡ hoặc offline | Không còn gọi tool cũ; lỗi rõ và an toàn. |
| Search trả zero results | Có câu trả lời/hỏi làm rõ, không tự bypass allowlist. |
| VectorStore lỗi | Có fallback search an toàn hoặc thông báo tạm thời không có kết quả. |
| Nhiều session đồng thời | Không trộn ứng viên và dữ liệu giữa các user. |
| Top-K/threshold khác nhau | Metric đo chính xác, báo cáo phiên bản cấu hình. |

## Quy trình chọn chỉ mục cho dự án thực tế

Có thể áp dụng theo thứ tự:

1. **Lập danh mục tool rõ nghĩa:** name/description phải phân biệt chức năng, điều kiện sử dụng và tác động đọc/ghi.
2. **Lọc theo quyền và workflow:** xác định tập eligible tools theo từng request, không dựa vào semantic score để kiểm soát quyền.
3. **Xây golden set:** gồm positive queries, paraphrases, hard negatives và no-tool cases có nhãn.
4. **Đo baseline:** chạy Regex và Lucene trước, ghi Recall@K, wrong-tool rate, no-tool accuracy, latency/token.
5. **Thử Vector và Decision:** so sánh trên cùng dataset, kể cả độ trễ embedding/decision-model.
6. **Tune top-K và threshold:** chọn cấu hình theo metric và mức rủi ro nghiệp vụ.
7. **Thử end-to-end:** dùng fake callbacks để kiểm tra selection, arguments, permission và mô hình trả lời.
8. **Đưa vào shadow/canary:** thu metric thật đã lọc dữ liệu nhạy cảm; có rollback khi chất lượng giảm.
9. **Giám sát drift:** theo dõi catalog changes, câu hỏi mới, tool nhầm nhiều và hiệu năng theo thời gian.

### Bài tập thực hành

Tạo catalog gồm ít nhất 20 công cụ cho quản lý đơn hàng, hóa đơn, tồn kho, hoàn tiền và vận chuyển. Đảm bảo mỗi nhóm có cặp tool dễ nhầm như getRefundEligibility/issueRefund và getInvoiceStatus/createInvoice.

Xây bộ 60 testcase gồm câu chính xác, câu diễn đạt khác, câu không cần tool, câu thiếu quyền và câu cần nhiều tool. Chạy lần lượt RegexToolIndex, LuceneToolIndex, VectorToolIndex và DecisionToolIndex với cùng các giá trị K = 1, 3, 5. Tính Hit@K, Recall@K, MRR, no-tool accuracy, wrong-tool execution rate và p95 latency.

Thử chỉnh description của hai tool dễ nhầm, chạy lại cùng dataset và so sánh kết quả. Sau đó thay đổi role một session đang dùng, evict index và xác minh tool đã mất quyền không còn được trả về hoặc thực thi. Cuối cùng, kiểm thử một yêu cầu hoàn tiền chỉ hỏi điều kiện để chứng minh hệ thống không tự gọi side-effecting tool.

Hoàn thành bài tập khi có thể giải thích vì sao một index được chọn bằng dữ liệu đo, chứ không chỉ bằng ấn tượng rằng nó "thông minh hơn".

## Danh sách kiểm tra trước khi triển khai

- [ ] Đã cân nhắc liệu catalog đủ lớn để cần ToolSearchToolCallingAdvisor hay chưa.
- [ ] Nắm rõ flow toolSearchTool → ToolIndex.search → disclose definitions → model tool call.
- [ ] Chọn Regex/Lucene/Vector/Decision theo đặc điểm query và catalog.
- [ ] Không mặc định các điểm score giữa index khác nhau có cùng thang đo.
- [ ] Description phân biệt rõ read/write, điều kiện và tác động của tool.
- [ ] Có golden set gồm positive, hard negatives, no-tool và multi-tool queries.
- [ ] Đo Hit@K, Recall@K, MRR hoặc nDCG@K, cùng no-tool accuracy.
- [ ] Đo tool-choice accuracy sau retrieval và argument validity.
- [ ] Tune K/threshold bằng cùng dataset; ghi nhận token/latency trade-off.
- [ ] Tool index chỉ chứa công cụ hợp lệ theo user/tenant/workflow.
- [ ] Authorization, confirmation và business validation vẫn nằm ở execution.
- [ ] Không bật resolver fallback quá rộng làm vượt tập tool được phép.
- [ ] Session ID không bị dùng chung giữa users; role changes được xử lý.
- [ ] Có catalog version/reindex/eviction policy khi tool set thay đổi.
- [ ] Với hybrid/reranking tự xây, không coi đó là built-in Spring AI API.
- [ ] Có regression tests cho drift, stale tools, MCP errors và concurrent sessions.
- [ ] Không ghi dữ liệu nhạy cảm vào index logs hoặc traces.

Điểm mấu chốt là một index tốt phải đưa đúng công cụ vào đúng ngữ cảnh, để mô hình dễ lựa chọn, trong khi ứng dụng vẫn giữ quyền quyết định có thực thi hay không. Hãy đo cả chất lượng truy xuất và kết quả cuối, đặc biệt với công cụ có side effect. Khi catalog phát triển, cách chọn chỉ mục cần được đánh giá và điều chỉnh bằng dữ liệu thực tế.

## Tài liệu tham khảo

- [Spring AI 2.1.0 – Tool Search Tool: chiến lược, API và cấu hình](https://docs.spring.io/spring-ai/reference/api/tools/tool-search-tool.html)
- [Spring AI 2.1.0 – Dynamic Tool Discovery guide](https://docs.spring.io/spring-ai/reference/guides/dynamic-tool-search.html)
- [Spring AI 2.1.0 – Tool Calling, ToolCallbackResolver và resolution fallback](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 – ToolCallingAdvisor và single-ToolAdvisor invariant](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI ToolIndex API – JavaDoc](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/toolsearch/ToolIndex.html)
- [Spring AI ToolSearchResponse API – JavaDoc](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/toolsearch/ToolSearchResponse.html)

# Ảnh hưởng của số lượng công cụ và độ dài schema đến lựa chọn

Khi xây dựng một trợ lý bằng Spring AI, ứng dụng có thể cung cấp cho mô hình những công cụ như tra cứu đơn hàng, đọc tồn kho, tạo yêu cầu hỗ trợ, lấy dữ liệu kế toán hoặc gọi API nội bộ. Với vài công cụ có chức năng khác nhau, mô hình thường phân biệt được khi nào nên gọi tool và cần điền những arguments nào. Khi danh mục tăng lên hàng chục hoặc hàng trăm tool, đặc biệt khi các tool có tên giống nhau và JSON Schema dài, việc chọn đúng tool trở thành một bài toán thiết kế riêng.

**Số lượng tool và độ dài schema là hai biến độc lập.** Mười tool có schema phức tạp có thể tiêu tốn nhiều token hơn năm mươi tool rất gọn; ngược lại, năm mươi tool trùng lặp về ý nghĩa có thể khó lựa chọn hơn mười tool khác biệt dù tổng token tương đương. Vì vậy, tối ưu danh mục không chỉ là giảm số hàm: cần quan tâm đến chất lượng tên và mô tả, kích thước của definitions, mức độ phân biệt nghiệp vụ, độ chính xác của bộ tìm tool, và giới hạn quyền thực thi.

Trong Spring AI 2.1.0, `ToolDefinition` gồm `name`, `description` và `inputSchema`. `ChatClient` có thể gửi các definitions đã đăng ký đến mô hình qua `ToolCallingAdvisor`. Với catalog lớn, `ToolSearchToolCallingAdvisor` hỗ trợ công bố công cụ tăng dần: trước tiên đưa một tool tìm kiếm vào request; chỉ khi tìm thấy công cụ phù hợp mới đưa schema của chúng cho mô hình. Bài này giải thích lúc nào hai chiến lược phù hợp, cách đo hiệu quả và cách tránh để tối ưu token làm suy yếu validation hoặc authorization.

## 1. Mô hình nhìn thấy gì khi ứng dụng đăng ký tool?

Giả sử ứng dụng có các tool:

- `get_order_status`: kiểm tra đơn hàng đang xử lý hay đã giao.
- `get_shipment_tracking`: tra cứu mã vận đơn và các mốc vận chuyển.
- `get_order_invoice`: lấy chứng từ hóa đơn.
- `cancel_order`: hủy đơn hàng theo chính sách.

Mỗi tool bao gồm một tên, mô tả cách sử dụng và JSON Schema arguments. Ví dụ:

~~~json
{
  "name": "get_shipment_tracking",
  "description": "Lấy mã vận đơn và các mốc vận chuyển của đơn hàng. Dùng khi người dùng hỏi gói hàng đang ở đâu hoặc giao đến đâu. Không dùng để xem hóa đơn hoặc hủy đơn.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "orderNumber": {
        "type": "string",
        "description": "Mã đơn hàng, ví dụ ORD-8F31A2"
      }
    },
    "required": ["orderNumber"],
    "additionalProperties": false
  }
}
~~~

Đây là biểu diễn khái niệm của một `ToolDefinition`. Các nhà cung cấp mô hình có thể truyền tool dưới dạng cấu trúc request khác nhau, nhưng ba phần tên, mô tả và input schema vẫn là dữ liệu chủ yếu để mô hình chọn và tạo arguments.

Mô hình có thể:

1. Không gọi tool nào nếu yêu cầu chỉ cần câu trả lời từ hội thoại.
2. Chọn một tool phù hợp.
3. Đề xuất nhiều tool calls nếu câu hỏi cần nhiều dữ liệu hoặc thao tác.
4. Chọn sai tool, đưa arguments sai hoặc không gọi tool dù cần.

**Mô hình đề xuất lời gọi; ứng dụng mới là bên thực thi.** Một tool được tìm thấy và đưa vào prompt không tự động cấp quyền gọi API phía sau. Ứng dụng vẫn kiểm tra quyền và validate arguments ở thời điểm thực thi.

## 2. Hai trục làm catalog khó dùng: số lượng và kích thước

Hai yếu tố thường bị gộp làm một:

| Yếu tố | Câu hỏi cần đo | Hệ quả chính |
|---|---|---|
| **Số lượng tool** | Có bao nhiêu hành động mà mô hình phải cân nhắc? | Nhiều ứng viên, tên và mô tả dễ chồng lấn, chọn nhầm hoặc gọi dư |
| **Độ dài schema** | Tool definitions chiếm bao nhiêu token? | Tăng context, chi phí input, thời gian xử lý và khả năng bị loãng thông tin |
| **Độ giống nhau về ngữ nghĩa** | Có bao nhiêu tool xử lý yêu cầu gần giống nhau? | Mô hình khó phân biệt ranh giới sử dụng |
| **Độ phức tạp của arguments** | Mỗi tool có bao nhiêu field, enum, nested object và required field? | Dễ tạo JSON sai, đoán field thiếu hoặc chọn nhầm loại tham số |
| **Tỷ lệ tool thực sự cần** | Một request thường cần mấy tool trong toàn catalog? | Nếu ít, gửi toàn bộ catalog tạo nhiều nhiễu và lãng phí |

Ví dụ về bốn danh mục khác nhau:

| Danh mục | Số tool | Đặc điểm schema | Rủi ro chủ yếu |
|---|---:|---|---|
| A | 6 | Gọn, mỗi tool một nghiệp vụ riêng | Thường dễ quản lý |
| B | 6 | Mỗi tool có nhiều object lồng nhau | Context tốn token, arguments phức tạp |
| C | 60 | Gọn nhưng nhiều tên gần nhau | Nhầm chọn tool |
| D | 60 | Dài, nhiều field tùy chọn và mô tả trùng lặp | Cả context, độ nhiễu và lỗi arguments |

Không có một con số cố định áp dụng cho mọi model. Tài liệu Spring AI 2.1.0 gợi ý xem xét Tool Search khi có từ khoảng 10 tool hoặc definitions vượt khoảng 10.000 token mỗi request; đó là **tín hiệu để đo và cân nhắc**, không phải ngưỡng chính xác phổ quát. Một catalog chỉ có tám tool nhưng schema dài vẫn có thể cần tối ưu.

## 3. Vì sao số lượng công cụ ảnh hưởng đến lựa chọn?

### 3.1. Nhiều ứng viên cạnh tranh cho cùng một ý định

Câu hỏi: “Đơn ORD-8F31A2 đi đến đâu rồi?”

- `get_order_status` có thể trả trạng thái tổng quát `PROCESSING`, `SHIPPED` hoặc `DELIVERED`.
- `get_shipment_tracking` trả các sự kiện vận chuyển chi tiết và vị trí cập nhật.
- `get_order_details` trả toàn bộ thông tin đơn.
- `search_orders` tìm nhiều đơn theo bộ lọc.

Cả bốn đều có từ “order”. Nếu description chỉ nói “lấy thông tin đơn hàng”, mô hình không có đủ tín hiệu để chọn đúng. Vấn đề tồn tại ngay cả khi schema của mỗi tool chỉ có một trường.

Với tập công cụ nhỏ, mô hình có ít lựa chọn dễ lẫn hơn. Khi catalog tăng, đặc biệt từ nhiều hệ thống MCP khác nhau, nhiều tool có thể đại diện cho cùng một thao tác ở các phiên bản hoặc dịch vụ khác nhau.

### 3.2. Mô hình có thể chọn tool tổng quát thay vì tool chuyên dụng

Nếu đồng thời công bố `call_any_api`, `search_everything` và `get_shipment_tracking`, một lời mô tả quá rộng như “dùng cho mọi yêu cầu” sẽ cạnh tranh với tool được thiết kế riêng. Một tool tổng quát có schema `url`, `operation` và `payload` không những khiến lựa chọn mơ hồ mà còn mở rộng rủi ro nếu ứng dụng không kiểm soát chặt đầu vào.

Ưu tiên tool mang hành động nghiệp vụ rõ ràng. Tool tổng quát chỉ phù hợp khi có lớp policy kiểm tra endpoint, operation và phạm vi dữ liệu ở server.

### 3.3. Nhiều tool không đồng nghĩa mô hình gọi tất cả

Số lượng tool tăng làm tăng tập ứng viên mà mô hình phải xét. Nó không có nghĩa mô hình sẽ luôn gọi nhiều tool. Kết quả phụ thuộc vào mô hình, cách mô tả, câu hỏi, cấu hình tool choice và ngữ cảnh.

Cần đo riêng:

- **Wrong tool:** chọn công cụ sai.
- **Unnecessary tool call:** gọi công cụ dù không cần.
- **Missed tool:** trả lời mà không gọi công cụ cần thiết.
- **Missing/invalid arguments:** chọn đúng tool nhưng tạo arguments sai.
- **Over-calling:** gọi thêm công cụ không giúp hoàn thành yêu cầu.

Đây là các lỗi khác nhau. Giảm số tool có thể giúp chọn đúng hơn nhưng nếu loại bỏ tool cần thiết thì tỷ lệ `missed tool` sẽ tăng.

## 4. Vì sao schema dài ảnh hưởng đến token và chất lượng?

JSON Schema dài vì nhiều lý do: description quá dài, quá nhiều field, object lồng nhau, danh sách enum lớn, các field chồng lấn hoặc lặp lại quy tắc nghiệp vụ.

Một định nghĩa lớn có thể chứa:

~~~text
tool name
+ tool description
+ schema top-level
+ từng property: tên, kiểu, mô tả, required/optional
+ enum, pattern, minimum, maximum, nested object
+ cấu trúc bao ngoài do provider dùng để gửi tool
~~~

Các thành phần này thường được tính vào input của model. Với `ToolCallingAdvisor` mặc định, các tool đã đăng ký cho request được gửi tới mô hình ở mỗi lần gọi trong vòng tool calling. Điều này có thể chiếm một phần đáng kể context, đặc biệt khi assistant cần nhiều vòng để gọi và nhận kết quả tool.

### Công thức ước tính ngân sách

Gọi:

- `N` là số tool được gửi.
- `tᵢ` là số token của định nghĩa tool thứ `i`, bao gồm tên, mô tả và schema.
- `W` là phần token của cấu trúc bao ngoài/tool wrappers.
- `R` là số lần gọi model trong cùng tác vụ.

Khi đó, số token definitions ở một request có thể ước tính:

~~~text
T_tools ≈ Σ(tᵢ) + W
           i=1..N
~~~

Nếu danh sách tool không đổi qua các vòng, tổng token definitions được gửi trong `R` model calls xấp xỉ:

~~~text
T_tools_total ≈ R × T_tools
~~~

Ví dụ giả định, **không phải số liệu benchmark**:

| Kịch bản | Số tool | Trung bình token/definition | Token tool mỗi model call |
|---|---:|---:|---:|
| Nhỏ, gọn | 8 | 180 | 1.440 |
| Ít nhưng schema dài | 8 | 1.250 | 10.000 |
| Nhiều, gọn | 60 | 180 | 10.800 |
| Nhiều và dài | 60 | 1.250 | 75.000 |

Bảng bỏ qua wrapper và overhead của provider để dễ nhìn xu hướng. Token thật phải đo bằng tokenizer hoặc usage của model được sử dụng; cùng một schema có thể được token hóa khác nhau giữa các model và provider.

Nếu một lượt cần ba model calls, kịch bản 60 tool × 180 token có thể gửi khoảng `3 × 10.800 = 32.400` token cho phần tool definitions, chưa tính hệ thống, lịch sử chat, nội dung người dùng và kết quả tool. Một số provider có cơ chế cache prefix làm thay đổi tiền billed; cache không loại bỏ việc model phải nhận và xử lý các định nghĩa trong ngữ cảnh.

### Schema quá ngắn cũng có thể gây lỗi

Không nên tối ưu bằng cách xóa hết mô tả. Ví dụ:

~~~json
{
  "name": "search",
  "description": "Search things",
  "inputSchema": {
    "type": "object",
    "properties": {
      "q": {"type": "string"}
    }
  }
}
~~~

Mô hình khó biết tìm loại dữ liệu gì, miền dữ liệu nào hoặc các giới hạn nghiệp vụ. Một schema ngắn nhưng mơ hồ có thể gây nhiều tool calls sai, khiến tổng chi phí và latency còn cao hơn.

Mục tiêu là **schema đủ thông tin để ra quyết định**, không phải schema ngắn nhất bằng mọi giá.

## 5. Tách phần giúp chọn tool và phần cần để gọi tool

Mô hình cần hai loại thông tin:

1. **Chọn tool:** tool dùng cho mục đích gì, không dùng khi nào, khác công cụ gần giống ra sao?
2. **Điền arguments:** bắt buộc field nào, định dạng nào, giá trị hợp lệ ra sao?

Hai loại thông tin này có liên hệ nhưng không đồng nhất. Với catalog lớn, phần tìm kiếm tool thường chỉ cần tên và mô tả ngắn, đủ phân biệt. Khi đã chọn được tool, mô hình mới cần JSON Schema đầy đủ.

Ví dụ các tool có ranh giới rõ:

| Tool | Description dùng để phân biệt |
|---|---|
| `get_order_status` | Trả trạng thái xử lý/giao nhận tổng quát của một đơn; không trả vị trí xe giao |
| `get_shipment_tracking` | Trả mã vận đơn, các mốc vận chuyển, vị trí cập nhật; dùng cho câu hỏi “hàng đến đâu” |
| `get_order_invoice` | Trả thông tin hóa đơn theo quyền người dùng; không đổi trạng thái đơn |
| `cancel_order` | Yêu cầu hủy đơn, có side effect và cần phê duyệt phù hợp |

Các mô tả này ngắn nhưng có ranh giới nghiệp vụ. Khi trả schema của `get_shipment_tracking` cho mô hình, tham số `orderNumber` mới cần description, pattern hoặc required status cụ thể.

Nếu danh mục có nhiều phiên bản cho cùng chức năng như `get_order_status_v1` và `get_order_status_v2`, cần quyết định ở application layer phiên bản nào được phép công bố. Không nên bắt mô hình tự giải quyết chính sách phiên bản hoặc quyền truy cập.

## 6. Cải thiện tên, mô tả và schema trước khi mở rộng catalog

Một số quy tắc thực tế:

**Tên tool**

- Thể hiện hành động và đối tượng: `get_inventory_balance`, `search_customer_orders`, `create_support_ticket`.
- Giữ nhất quán động từ: `get` cho một tài nguyên, `search` cho danh sách, `create`/`update`/`cancel` cho thay đổi.
- Tránh tên gần giống chỉ khác vài ký tự hoặc hậu tố khó hiểu.
- Với nhiều nhà cung cấp, cân nhắc namespace rõ ràng, ví dụ `crm_search_contact` và `erp_search_supplier`.
- Đảm bảo tên duy nhất trong danh sách tool của request.

**Mô tả**

- Nêu kết quả trả về, tình huống nên dùng và trường hợp không nên dùng.
- Dùng ví dụ cụ thể nếu một câu ngắn không đủ phân biệt.
- Tránh lời quảng cáo, văn bản lặp lại, policy chung dài hàng trang.
- Không chèn hướng dẫn yêu cầu mô hình bỏ qua bảo mật hoặc xác thực.
- Đối với tool có side effect, mô tả rõ hành động sẽ làm thay đổi dữ liệu.

**Input Schema**

- Dùng kiểu Java cụ thể để Spring AI sinh schema; tránh payload tùy ý khi có thể dùng DTO.
- Chỉ bắt buộc trường người dùng hoặc ngữ cảnh có thể cung cấp đáng tin cậy.
- Không đưa `tenantId`, token, role vào schema để model tự điền; truyền các giá trị server-derived qua `ToolContext`.
- Giới hạn enum và field theo trường hợp sử dụng; chia quá nhiều biến thể thành tool chuyên dụng nếu có ranh giới nghiệp vụ tự nhiên.
- Không để model chọn URL, tên bảng database, HTTP method hoặc mã thực thi tự do.
- Giữ validation thật ở application service: schema chỉ hướng dẫn model tạo input, không thay thế kiểm tra phía server.

Ví dụ Spring AI với tool nhỏ, rõ mục đích:

~~~java
public class OrderReadTools {

    private final OrderService orderService;

    public OrderReadTools(OrderService orderService) {
        this.orderService = orderService;
    }

    @Tool(
        name = "get_order_status",
        description = """
            Lấy trạng thái xử lý/giao nhận tổng quát của một đơn hàng
            mà người dùng được phép xem. Không trả hóa đơn hoặc
            vị trí chi tiết của gói hàng.
            """
    )
    public OrderStatusResult getOrderStatus(
            @ToolParam(description = "Mã đơn, ví dụ ORD-8F31A2")
            String orderNumber,
            ToolContext context) {
        Actor actor = requireServerActor(context);
        return orderService.getStatus(actor, orderNumber);
    }
}
~~~

`OrderService`, `OrderStatusResult` và `requireServerActor(...)` là thành phần của ứng dụng. Hàm thực thi cần xác thực quyền đối với từng đơn; `ToolContext` không tự làm authorization.

## 7. Cách 1: chỉ gửi các tool phù hợp với mỗi request

Với catalog vừa hoặc phân nhóm được theo quyền và loại nghiệp vụ, cách đơn giản nhất là chỉ gắn tool cần thiết cho từng request.

Ví dụ chỉ mở tool đọc tồn kho cho một tác vụ tra cứu:

~~~java
ChatClient client = ChatClient.builder(chatModel).build();

String answer = client.prompt()
    .user("Tồn kho SKU-100 tại kho Hà Nội còn bao nhiêu?")
    .tools(inventoryReadTools)
    .call()
    .content();
~~~

Khi xử lý yêu cầu hỗ trợ khách hàng:

~~~java
String answer = client.prompt()
    .user("Tôi muốn biết trạng thái ticket SUP-1024")
    .tools(supportReadTools)
    .call()
    .content();
~~~

Cách này giảm số định nghĩa gửi tới mô hình và giảm công cụ ngoài phạm vi có thể được đề xuất. Tập tool cần được quyết định từ **chính sách server, quyền người dùng và ngữ cảnh nghiệp vụ đáng tin cậy**; không chỉ dùng text do model tự tạo để cấp quyền.

### Điểm dễ nhầm của `defaultTools`

Trong Spring AI 2.1.0, tool gắn bằng `.tools(...)` cho từng request **được cộng thêm** vào tools đã cấu hình bằng `.defaultTools(...)`. Nó không thay thế mặc định.

~~~java
ChatClient client = ChatClient.builder(chatModel)
    .defaultTools(commonReadTools)
    .build();

// Request sau có commonReadTools + inventoryReadTools.
String answer = client.prompt()
    .user(question)
    .tools(inventoryReadTools)
    .call()
    .content();
~~~

Vì vậy, để giảm catalog theo request thật sự, không đăng ký toàn bộ tool vào `defaultTools` rồi tưởng rằng `.tools(...)` đã lọc bớt danh sách. Chỉ đặt công cụ thường trực, an toàn và dùng rộng vào defaults; công cụ nhạy cảm nên được cấp theo chính sách từng request.

Nếu ứng dụng có nhiều `ChatClient` riêng theo workflow, có thể duy trì các bộ default tools khác nhau. Với người dùng nhiều vai trò, tránh lưu trạng thái phân quyền trong singleton có thể chia sẻ giữa các session.

## 8. Cách 2: công bố tăng dần bằng Tool Search Tool

Từ Spring AI 2.1.0, `ToolSearchToolCallingAdvisor` hỗ trợ **progressive tool disclosure**: chỉ gửi một tool tìm kiếm ở request ban đầu, rồi thêm các định nghĩa phù hợp sau khi mô hình tìm kiếm.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as ChatClient
    participant S as ToolSearchToolCallingAdvisor
    participant M as Mô hình
    participant I as ToolIndex
    participant T as ToolCallback

    U->>C: Hỏi trạng thái vận chuyển
    C->>S: Request + full catalog trong ứng dụng
    S->>I: Lập chỉ mục catalog theo session
    S->>M: Chỉ gửi định nghĩa toolSearchTool
    M-->>S: toolSearchTool("theo dõi vận đơn")
    S->>I: Tìm tool phù hợp
    I-->>S: get_shipment_tracking
    S->>M: Gửi schema get_shipment_tracking
    M-->>S: Gọi get_shipment_tracking(arguments)
    S->>T: Kiểm tra điều kiện và thực thi
    T-->>S: Kết quả có cấu trúc
    S->>M: Tool result
    M-->>C: Câu trả lời cuối
    C-->>U: Trình bày kết quả
~~~

Điểm then chốt là **toàn bộ catalog vẫn tồn tại trong ứng dụng**, nhưng mô hình chỉ thấy subset ở một thời điểm. Spring AI dùng `ToolIndex` để tìm các tool phù hợp; `ToolCallingManager` vẫn thực thi callback như trong vòng tool calling thông thường.

### 8.1. Kích hoạt bằng Spring Boot starter

Thêm dependency cho Spring AI 2.1.0:

~~~groovy
dependencies {
    implementation 'org.springframework.ai:spring-ai-starter-tool-search-advisor'
}
~~~

Bật auto-configuration và chọn index:

~~~properties
spring.ai.chat.client.tool-search-advisor.enabled=true
spring.ai.chat.client.tool-search-advisor.tool-index-type=lucene
spring.ai.chat.client.tool-search-advisor.max-results=5
~~~

Theo tài liệu Spring AI 2.1.0, starter tự cấu hình `ToolSearchToolCallingAdvisor` thay `ToolCallingAdvisor` mặc định khi property được bật. `lucene` dùng tìm kiếm từ khóa và có dependency đi kèm starter. Giá trị `5` chỉ là ví dụ để bắt đầu đo recall; không nên coi đó là K tối ưu cho mọi bộ công cụ.

**Chú ý:** loại index mặc định của starter là `regex`. Nó hữu ích khi người dùng/model tìm tên tool theo pattern, nhưng có thể bỏ sót yêu cầu diễn đạt tự nhiên như “hàng của tôi đến đâu rồi”. Hãy chọn index và ngưỡng tìm kiếm theo từ vựng thực tế của ứng dụng.

### 8.2. Truyền session ID cho Tool Search

Tool index được quản lý theo session, nên mỗi request phải có session ID phù hợp. Mặc định advisor lấy từ khóa `MemoryAdvisor.CONVERSATION_ID` trong advisor context:

~~~java
String sessionId = sessionService.requireAuthorizedSessionId(
    authenticatedUser,
    conversationId
);

String answer = chatClient.prompt()
    .user(userQuestion)
    .advisors(a -> a.param(MemoryAdvisor.CONVERSATION_ID, sessionId))
    .call()
    .content();
~~~

`sessionService` và `authenticatedUser` là thành phần của ứng dụng. Session ID cần được tạo/kiểm tra ở phía server, không dùng nguyên giá trị tùy ý người dùng đưa vào để truy cập session của người khác. Khi đăng xuất hoặc thay đổi quyền, cần cân nhắc xóa hoặc tạo mới index session bằng `advisor.evictSession(sessionId)` để tránh tập tool cũ còn trong session.

### 8.3. Điều phối thủ công bằng builder

Nếu ứng dụng không dùng auto-configuration, có thể tạo advisor theo tài liệu:

~~~java
@Bean
ToolIndex toolIndex() {
    return new LuceneToolIndex();
}

@Bean
ToolSearchToolCallingAdvisor toolSearchAdvisor(ToolIndex toolIndex) {
    return ToolSearchToolCallingAdvisor.builder()
        .toolIndex(toolIndex)
        .maxResults(5)
        .build();
}
~~~

Khi tích hợp với `ChatClient` thủ công, cần sử dụng advisor này như **tool advisor** của client, tránh đồng thời cài thêm một `ToolCallingAdvisor` khác. `DefaultChatClient` chỉ cho một tool advisor trong chain. Với ứng dụng Spring Boot đã bật starter, ưu tiên để auto-configuration tạo advisor và `ChatClient.Builder` thay vì trộn cả hai cách cấu hình.

## 9. Chọn chiến lược ToolIndex theo dữ liệu

`ToolSearchToolCallingAdvisor` dựa vào một `ToolIndex`. Spring AI 2.1.0 hỗ trợ một số triển khai:

| Chiến lược | Class | Phù hợp | Giới hạn cần đo |
|---|---|---|---|
| Pattern | `RegexToolIndex` | Tìm tool theo tên quy ước/pattern | Khó khớp câu hỏi tự nhiên nếu tên khác từ ngữ |
| Từ khóa | `LuceneToolIndex` | Tên/description có thuật ngữ ổn định | Khó với diễn đạt đồng nghĩa hoặc khác ngôn ngữ |
| Ngữ nghĩa | `VectorToolIndex` | Truy vấn tự nhiên, biến thể cách diễn đạt | Cần embeddings/`VectorStore`, có thể trả tool gần nghĩa nhưng sai nghiệp vụ |
| Mô hình quyết định | `DecisionToolIndex` | Muốn quyết định có tool phù hợp hay không | Tăng chi phí inference; model phải xét tập ứng viên được cung cấp |

Ví dụ với người dùng hỏi bằng tiếng Việt nhưng công cụ mô tả tiếng Anh, vector search có thể tìm được tool liên quan ngay cả khi không khớp từ chính xác, tùy embedding model. Ngược lại, keyword index có thể hiệu quả nếu tên và description được chuẩn hóa cùng thuật ngữ nghiệp vụ.

`DecisionToolIndex` có lợi thế là có thể trả về không tool nào khi không có công cụ phù hợp. Tài liệu Spring AI lưu ý việc dùng decision model để xét hàng trăm tools có thể tốn prompt lớn; nên shortlist bằng index rẻ hơn rồi mới áp dụng bước quyết định nếu cần.

Không xem `VectorToolIndex` là tự động chính xác hơn `LuceneToolIndex`. Chất lượng phụ thuộc vào mô tả tool, embedding, phân phối ngôn ngữ và bộ câu hỏi thật.

## 10. Trade-off của K và việc tích lũy công cụ đã tìm thấy

Khi dùng tìm kiếm, `K` là số tool tối đa đưa ra sau một truy vấn discovery. Đây là một điểm cân bằng:

- K quá nhỏ: tool đúng có thể không xuất hiện trong kết quả tìm kiếm; model không thể chọn tool nó chưa được công bố.
- K quá lớn: gần như quay lại vấn đề catalog quá nhiều tool.
- K vừa đủ: tăng khả năng có tool đúng nhưng vẫn giảm token và nhiễu.

Ví dụ giả định với catalog 100 tools:

| K | Lợi ích | Rủi ro |
|---:|---|---|
| 1 | Rất ít schema trong context | Dễ bỏ sót nếu top-1 sai |
| 3 | Giảm nhiễu, có vài lựa chọn | Có thể thiếu tool ở bài toán đa bước |
| 5 | Có thêm ứng viên cho câu hỏi phức tạp | Token cao hơn K=3 |
| 20 | Recall có thể cao hơn | Nhiều ứng viên gần nghĩa, tăng context |

Bảng là phân tích xu hướng, không phải benchmark về một model cụ thể. Cần đánh giá K trên tập câu hỏi có ground truth thay vì chọn theo cảm giác.

Spring AI có `referenceToolNameAccumulation`, mặc định `true`: các công cụ tìm thấy ở những lượt search trước được tích lũy trong session. Điều này giúp công việc nhiều bước giữ lại những tool đã khám phá, nhưng về lâu dài subset cũng có thể phình to. Có thể cân nhắc `reference-tool-name-accumulation=false` để chỉ giữ các tool tìm thấy trong lượt search gần nhất, nếu quy trình không cần giữ công cụ của bước trước.

Ví dụ cấu hình:

~~~properties
spring.ai.chat.client.tool-search-advisor.max-results=5
spring.ai.chat.client.tool-search-advisor.reference-tool-name-accumulation=false
~~~

Cần kiểm thử các tác vụ nhiều bước trước khi tắt tích lũy. Mục tiêu không phải làm context nhỏ bằng mọi giá, mà là giữ đủ công cụ để hoàn thành nhiệm vụ đúng.

## 11. Tool Search tiết kiệm token nhưng thêm một vòng tìm kiếm

Công bố tăng dần có chi phí riêng:

- Tool tìm kiếm chiếm một phần prompt.
- Mô hình cần thêm một lượt gọi `toolSearchTool` để tìm công cụ.
- Indexing/search tiêu tốn CPU, bộ nhớ hoặc phí embedding tùy chiến lược.
- Nếu tìm sai tool, mô hình có thể phải tìm lại, làm tăng latency.
- Tool đã khám phá có thể được đưa vào các lượt model kế tiếp.

Với catalog nhỏ và tất cả công cụ được dùng thường xuyên, gửi toàn bộ definitions có thể đơn giản và nhanh hơn vì tránh discovery round-trip. Với catalog lớn nhưng mỗi request chỉ cần vài tool, chi phí một lần tìm kiếm thường đáng để thử nghiệm.

### So sánh ngân sách bằng ví dụ giả định

Giả sử 60 definitions, trung bình 250 token mỗi tool:

~~~text
Full catalog mỗi model call: 60 × 250 ≈ 15.000 token
Sau discovery tìm được 5 tool: 5 × 250 ≈ 1.250 token
~~~

Con số 1.250 không phải toàn bộ input của cách Tool Search: còn schema của `toolSearchTool`, truy vấn search, message lịch sử và các lượt gọi bổ sung. Dù vậy, chênh lệch cho thấy tại sao chiến lược chỉ công bố subset có thể hữu ích.

Tài liệu Spring AI 2.1.0 công bố kết quả thử nghiệm sơ bộ với 28 tools, tiết kiệm khoảng 34–64% input token tùy model. Đây là kết quả trên cấu hình thử nghiệm cụ thể, không bảo đảm ứng dụng của bạn đạt cùng mức tiết kiệm. Hãy so sánh cả chi phí, độ chính xác và thời gian hoàn thành tác vụ trước khi đổi kiến trúc.

## 12. An toàn thực thi không được phụ thuộc vào chất lượng tìm kiếm

Một tool được truy xuất từ `ToolIndex` chưa đồng nghĩa người dùng được quyền sử dụng nó. Bộ tìm kiếm có thể sai; LLM có thể yêu cầu tool có side effect; remote MCP server có thể thay đổi mô tả tool.

Các nguyên tắc bắt buộc:

1. **Lọc quyền trước khi đưa tool vào catalog của request/session** khi kiến trúc cho phép, để model không thấy công cụ vốn không được dùng.
2. **Kiểm tra quyền lại tại execution boundary.** Tool callback hoặc application service phải xác thực principal, tenant và quyền trên tài nguyên.
3. **ToolContext lấy từ server.** Không yêu cầu model cung cấp token, tenant ID, vai trò hay “đã được phê duyệt”.
4. **Phân biệt read và write.** Tool xóa, tạo giao dịch, hoàn tiền, gửi tin cần kiểm soát side effect, idempotency và xác nhận người dùng khi cần.
5. **Không bật resolution fallback chỉ để sửa vấn đề tìm tool.** Resolver fallback có thể làm các tool vốn không được gắn vào request trở nên thực thi được theo tên.
6. **Kiểm soát xung đột tên.** Trong hệ thống trộn local và MCP tool, dùng namespace hoặc cơ chế kiểm tra tên duy nhất.

Trong Spring AI 2.1.0, `spring.ai.tools.resolution.fallback.enabled` mặc định là `false`. Giữ mặc định này cho mô hình quyền hạn theo từng request. Bật fallback khiến `ToolCallingManager` có thể tìm callback theo tên trong `ToolCallbackResolver` kể cả khi tool không được gắn cho request; điều đó cần được xem xét kỹ với catalog có tool nhạy cảm.

### Cẩn thận với catalog đa tenant

Nếu Tool Search sử dụng index theo session, session phải gắn với danh tính và phạm vi truy cập đã xác thực. Khi đổi tenant, role hoặc policy:

- Tạo session scope mới hoặc loại bỏ index cũ.
- Đảm bảo tool discovery không dùng cache chia sẻ giữa người dùng sai phạm vi.
- Xác minh mỗi tool vẫn thực thi authorization độc lập.
- Dùng `evictSession(sessionId)` khi phù hợp với chính sách vòng đời.

Chất lượng tìm tool và quyền thực thi là hai bài toán riêng. Tối ưu recall không được vượt qua lớp bảo mật.

## 13. Đo hiệu quả bằng bộ câu hỏi đại diện

Không thể kết luận một catalog “tốt” chỉ bằng việc số tool giảm từ 80 xuống 20. Cần đánh giá cả việc tìm được đúng tool, chạy đúng và trả lời đúng.

### 13.1. Tạo dataset có nhãn

Mỗi case nên có:

| Trường | Ý nghĩa |
|---|---|
| `query` | Câu hỏi thực tế, gồm cả câu mơ hồ và tiếng Việt tự nhiên |
| `userRole`, `tenantScope` | Ngữ cảnh quyền cho phép test |
| `expectedTools` | Một hoặc nhiều tool cần thiết; có thể là tập rỗng |
| `expectedArguments` | Giá trị và kiểu arguments hợp lệ |
| `allowedToExecute` | Tool có được phép thực thi trong context này không |
| `expectedOutcome` | Kết quả nghiệp vụ hoặc thông tin cuối cùng cần đạt |

Ví dụ:

~~~json
[
  {
    "query": "Đơn ORD-8F31A2 của tôi đang giao đến đâu?",
    "expectedTools": ["get_shipment_tracking"],
    "expectedArguments": {"orderNumber": "ORD-8F31A2"},
    "allowedToExecute": true
  },
  {
    "query": "Giải thích khái niệm tool calling trong Spring AI",
    "expectedTools": [],
    "allowedToExecute": false
  },
  {
    "query": "Hủy đơn hàng thuộc tenant khác",
    "expectedTools": [],
    "allowedToExecute": false
  }
]
~~~

Case cuối nhấn mạnh hệ thống phải từ chối thực thi trái quyền. Tùy sản phẩm, mô hình vẫn có thể đề xuất tool rồi service từ chối; khi đánh giá an toàn, thước đo quan trọng là **không có thao tác trái quyền được thực thi**, không chỉ dựa vào danh sách tool được mô hình đề xuất.

### 13.2. Phân tách hai giai đoạn tìm và gọi

Với Tool Search, cần đo riêng:

**Discovery quality**

- `Recall@K`: tỷ lệ case mà tool đúng nằm trong tối đa K công cụ tìm thấy.
- `Precision@K`: tỷ lệ công cụ tìm thấy thực sự phù hợp; cần xác định nhãn relevance rõ ràng.
- `No-match accuracy`: tỷ lệ không đề xuất công cụ khi đúng là không có tool phù hợp.
- Tỷ lệ tìm lại (re-search) vì lần đầu bỏ sót.

**Tool invocation quality**

- `Tool selection accuracy`: chọn đúng tên tool từ subset.
- `Argument validity`: JSON hợp schema và vượt qua validation phía ứng dụng.
- `Task completion rate`: hoàn thành đúng yêu cầu nghiệp vụ.
- `Unauthorized execution rate`: mục tiêu bằng 0.
- `Unnecessary call rate`: gọi thêm tool không cần.

**Chi phí và hiệu năng**

- Input token và output token thực tế trên từng model call.
- Tổng số model calls và search calls trên mỗi tác vụ.
- Tổng chi phí tiền theo model/provider, bao gồm embeddings/index nếu có.
- End-to-end latency, trung vị và p95.
- Kích thước `ToolIndex`, thời gian index, tỷ lệ cache hit và số session tồn đọng.

### 13.3. Công thức đo đơn giản

~~~text
Recall@K = số case có tool đúng trong top-K / số case cần tool

WrongToolRate = số case chọn tool sai / số case có tool được chọn

TokenPerTask = tổng token từ mọi model call của một tác vụ

TaskSuccessRate = số tác vụ hoàn thành đúng / tổng tác vụ
~~~

Với yêu cầu cần nhiều tools, hãy quyết định trước cách đánh giá: `Recall@K` có nghĩa “tìm được ít nhất một tool đúng” hay “tìm đủ tất cả tool bắt buộc”. Nên báo cáo cả hai, vì tìm được một trong ba tool vẫn có thể khiến quy trình thất bại.

Dùng cùng một bộ case và môi trường để so sánh các chiến lược: full catalog, shortlist theo domain, Lucene Tool Search, Vector Tool Search và hybrid. Cố định model, thông số inference, dữ liệu dịch vụ và quyền test; chạy nhiều lần vì lựa chọn mô hình có thể dao động.

## 14. Quy trình thực nghiệm tối ưu catalog

Một thứ tự thực tế:

1. **Đo baseline.** Ghi số tool, token definitions, tổng input token, tool calls, lỗi arguments, latency và tỷ lệ thành công.
2. **Kiểm tra chất lượng hợp đồng.** Sửa tool name trùng, description mơ hồ, field required sai, schema quá tổng quát và dữ liệu nhạy cảm bị lộ.
3. **Phân nhóm theo nghiệp vụ/quyền.** Ví dụ đọc đơn hàng, vận chuyển, tài chính, hỗ trợ; quyết định rõ tool nào có thể xuất hiện trong mỗi workflow.
4. **Thử shortlist theo request.** Đây là cách có độ phức tạp thấp nếu ứng dụng biết domain của request từ nguồn đáng tin cậy.
5. **Thử Tool Search.** Bắt đầu với `lucene` hoặc chiến lược phù hợp ngôn ngữ dữ liệu, rồi thử K khác nhau.
6. **Kiểm tra case không nên gọi tool.** Không chỉ tối ưu các câu hỏi chắc chắn cần tool.
7. **Đánh giá tác vụ nhiều bước.** Khi cần chuỗi tool A → B → C, kiểm tra discovery có tìm đủ công cụ sau mỗi vòng.
8. **Kiểm tra đa tenant và side effect.** Không để một tool bị lọt qua tầng lọc hoặc session cache.
9. **So sánh hiệu quả tổng thể.** Chỉ áp dụng giải pháp mới nếu task success và an toàn giữ được hoặc cải thiện, đồng thời token/cost/latency đạt mục tiêu.

Ví dụ kết quả đo (số giả định để minh họa cách đọc):

| Chiến lược | Tool definition token mỗi lần gửi | Task success | p95 latency | Nhận xét |
|---|---:|---:|---:|---|
| Gửi 60 tool | 15.000 | 88% | 5,4 s | Baseline |
| Shortlist 8 tool | 2.000 | 94% | 4,6 s | Tốt nếu có routing đáng tin cậy |
| Tool Search top-5 | Thay đổi theo vòng | 93% | 6,1 s | Token có thể giảm, thêm bước discovery |
| Tool Search top-1 | Thay đổi theo vòng | 79% | 5,0 s | Recall quá thấp |

Không dùng các con số trên làm mục tiêu kỹ thuật cho mọi dự án. Chúng chỉ minh họa rằng chiến lược có token thấp nhất không nhất thiết đạt task success cao nhất và Tool Search có thể tăng latency dù giảm input token.

## 15. Kịch bản quyết định kiến trúc

| Tình huống | Lựa chọn nên thử trước | Lý do |
|---|---|---|
| Dưới 10 tool, schema gọn, mục đích khác biệt | `ToolCallingAdvisor` mặc định | Ít chi phí discovery và đơn giản |
| Nhiều domain nhưng request biết sẵn domain đáng tin cậy | Shortlist theo request | Giảm tool gửi mà không cần model tìm |
| 30+ tool và mỗi câu hỏi chỉ dùng vài tool | `ToolSearchToolCallingAdvisor` | Progressive disclosure có khả năng giảm context bloat |
| Nhiều tool trùng tên/ý nghĩa | Sửa tên, mô tả và chính sách version trước | Search tốt cũng khó cứu description mơ hồ |
| Tool có nhiều arguments lồng nhau | Thiết kế lại DTO/schema | Chọn đúng tool chưa đủ nếu arguments luôn sai |
| Multi-server MCP catalog | Lọc nguồn, namespace và Tool Search | Kiểm soát xung đột tên, quyền và kích thước catalog |
| Tool catalog thay đổi thường xuyên | Index lifecycle và refresh policy rõ ràng | Tránh session giữ tool cũ |
| Nhiệm vụ nhiều bước có tool phụ thuộc | Test recall nhiều vòng, K và accumulation | Cần đủ tool ở từng giai đoạn |
| Tác vụ có rủi ro ghi dữ liệu | Tool allowlist, authorization và confirmation | Quyền thực thi phải ở server |

Không bắt buộc phải chọn một cơ chế cho toàn ứng dụng. Một hệ thống có thể dùng `ChatClient` mặc định cho nhóm 5 công cụ đọc và một client khác dùng Tool Search cho catalog 100 công cụ. Quan trọng là định nghĩa chính sách công cụ nhất quán và đo được.

## 16. Những sai lầm thường gặp

| Sai lầm | Vì sao gây vấn đề | Cách sửa |
|---|---|---|
| Đăng ký mọi tool vào `defaultTools` rồi thêm `.tools(...)` | Request nhận cả hai nhóm tool | Chỉ để common tools trong defaults |
| Dùng số tool như chỉ số duy nhất | Bỏ qua schema length, overlap và số field | Đo token definitions và semantic overlap |
| Cắt hết description để giảm token | Tool mất ranh giới sử dụng | Viết ngắn nhưng nêu mục đích và giới hạn |
| Để nhiều tool làm cùng việc nhưng khác version | Model không biết nên chọn version nào | Chọn version hợp lệ ở server |
| Đặt quá nhiều field required | Model bịa dữ liệu không có | Chỉ bắt buộc input biết được; đưa internal context qua `ToolContext` |
| Giảm K thật thấp để tiết kiệm token | Retrieval bỏ sót tool đúng | Đo `Recall@K` trên case thật |
| Dùng index regex mặc định cho câu hỏi tự nhiên | Khó tìm theo diễn đạt khác tên tool | Chọn Lucene/vector/decision theo dữ liệu |
| Chỉ xem token mỗi model call | Bỏ qua vòng discovery và repeat calls | Đo token và latency trên cả tác vụ |
| Cho rằng tool được tìm thấy là đã có quyền | Tool trái quyền có thể bị thực thi | Authorization lại trong application service |
| Bật resolver fallback để tool nào cũng gọi được | Bỏ qua giới hạn per-request tools | Giữ fallback tắt hoặc tự giới hạn resolver theo policy |
| Không kiểm thử câu hỏi không cần tool | Tăng unnecessary calls | Thêm case `expectedTools=[]` |
| Không quản lý session index | Tool cũ hoặc scope sai tồn tại | Session ID tin cậy, eviction và refresh policy |

## 17. Checklist trước khi đưa catalog lớn vào production

- [ ] Tool names duy nhất, rõ đối tượng và hành động.
- [ ] Description phân biệt được các tool dễ bị nhầm.
- [ ] JSON Schema không chứa field thừa, có required/optional và kiểu đúng.
- [ ] Đã đo token definitions theo model/provider thực tế.
- [ ] Đã đo chất lượng tool selection với câu hỏi nhiều domain.
- [ ] Có case không cần tool và case yêu cầu nhiều tool.
- [ ] Tool catalog được lọc theo quyền, tenant và workflow phù hợp.
- [ ] Tool có side effect vẫn cần authorization, idempotency và confirmation phù hợp.
- [ ] Không bật tên-based resolver fallback ngoài ý muốn.
- [ ] Nếu dùng Tool Search, đã chọn index phù hợp và đo `Recall@K`.
- [ ] Có session ID tin cậy, eviction/refresh cho tool index.
- [ ] Có số liệu input token, tổng model calls, p50/p95 latency và task success.
- [ ] Có regression dataset khi thêm, sửa tên hoặc xóa tool.
- [ ] Đã đo cả latency và chi phí discovery thay vì chỉ nhìn giảm token.
- [ ] Có quan sát lỗi wrong-tool, invalid-arguments và unauthorized execution.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): `ToolDefinition`, `ToolCallback`, cách truyền `.tools(...)`/`.defaultTools(...)`, vòng `ToolCallingAdvisor`, dynamic resolution và mở rộng catalog.
- [Spring AI 2.1.0 — Tool Search Tool](https://docs.spring.io/spring-ai/reference/api/tools/tool-search-tool.html): `ToolSearchToolCallingAdvisor`, `ToolIndex`, auto-configuration, index strategies, session scoping, accumulation và eviction.
- [Spring AI 2.1.0 — Dynamic Tool Discovery Guide](https://docs.spring.io/spring-ai/reference/guides/dynamic-tool-search.html): ví dụ progressive tool disclosure và kết quả benchmark sơ bộ.
- [Spring AI 2.1.0 — Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html): xác nhận trước khi thực thi tool có tác động nghiệp vụ.
- [Spring AI 2.1.0 — Tool Calling Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): quan sát hoạt động tool calling và chi phí/hiệu năng theo hệ thống.
- [Spring AI Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): khác biệt phiên bản, trong đó Spring AI 2.x không còn `toolNames(...)` theo cách Spring AI 1.x.

**Điểm cần nhớ:** không có quy luật “càng ít tool càng tốt” hoặc “schema càng ngắn càng chính xác”. Một catalog tốt chứa đủ công cụ cần thiết, mô tả phân biệt rõ, arguments hợp lệ, được lọc theo quyền và chỉ công bố phần cần thiết ở mỗi thời điểm. Hãy dùng dữ liệu từ thử nghiệm để lựa chọn giữa gửi toàn bộ, shortlist theo request và Tool Search, rồi giữ mọi quyết định an toàn tại ứng dụng Spring AI.


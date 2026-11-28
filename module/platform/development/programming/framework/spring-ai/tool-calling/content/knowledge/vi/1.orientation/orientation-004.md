# Phân biệt tool calling, function calling, structured output và agent

Khi tích hợp mô hình ngôn ngữ lớn (LLM) vào một ứng dụng Spring, có bốn khái niệm thường xuất hiện cùng nhau: **tool calling**, **function calling**, **structured output** và **agent**. Chúng liên quan đến cách mô hình trao đổi dữ liệu với ứng dụng, nhưng giải quyết những vấn đề khác nhau.

- **Structured output** giúp ứng dụng nhận câu trả lời theo một cấu trúc dữ liệu đã định.
- **Tool calling** cho phép mô hình đề xuất một thao tác mà ứng dụng có thể thực thi.
- **Function calling** là tên gọi lịch sử của một cơ chế gọi hàm, đồng thời cũng là tên của một cách tạo tool cụ thể trong Spring AI.
- **Agent** là cách tổ chức một vòng làm việc có mục tiêu: nhận yêu cầu, chọn bước tiếp theo, dùng công cụ, quan sát kết quả và tiếp tục cho đến khi đạt điều kiện dừng.

Điểm cần giữ rõ trong mọi thiết kế là: **mô hình đề xuất lời gọi; ứng dụng chịu trách nhiệm xác thực, thực thi và kiểm soát tác động của lời gọi đó**. Việc mô hình trả về một tool call không có nghĩa là nó đã truy cập cơ sở dữ liệu hay thực hiện một giao dịch.

Bài viết sử dụng Spring AI làm ví dụ, tập trung vào `@Tool`, `ToolCallback`, schema đầu vào và `ToolContext`, cùng trách nhiệm của ứng dụng trong điều phối nhiều lượt gọi, phân quyền, xử lý lỗi và kiểm thử.

## 1. Một tình huống để phân biệt các khái niệm

Giả sử người dùng hỏi:

> Kiểm tra tồn kho của SKU A-100 tại kho Hà Nội. Nếu còn hàng, cho tôi biết có thể đáp ứng đơn 20 sản phẩm không.

Ứng dụng có dịch vụ nghiệp vụ để tra cứu tồn kho. LLM có thể tham gia theo nhiều cách:

1. **Structured output:** mô hình phân loại yêu cầu thành dữ liệu như hành động `CHECK_STOCK`, mã SKU `A-100`, kho `Hà Nội` và số lượng `20`. Ứng dụng nhận một đối tượng Java có kiểu rõ ràng.
2. **Tool calling:** mô hình gửi yêu cầu gọi tool `lookupInventory` với các đối số SKU và kho. Spring AI chuyển yêu cầu đến callback tương ứng; callback gọi dịch vụ tồn kho và trả kết quả.
3. **Function calling:** nếu đang nói về cơ chế API đời đầu của một nhà cung cấp, đây có thể là tên gọi cho việc mô hình yêu cầu gọi một hàm. Trong Spring AI, `FunctionToolCallback` là một cách bọc `Function`, `Supplier`, `Consumer` hoặc `BiFunction` thành tool.
4. **Agent:** nếu yêu cầu mở rộng thành kiểm tra tồn kho, tạo đề xuất thay thế, chờ người dùng xác nhận rồi mới tạo đơn, một agent có thể điều phối nhiều bước và quyết định bước tiếp theo dựa trên kết quả đã nhận.

Cùng một ứng dụng có thể dùng cả bốn khái niệm. Chúng không phải bốn lựa chọn loại trừ nhau.

## 2. Tool calling: mô hình yêu cầu ứng dụng thực hiện một thao tác

Tool calling là cơ chế để LLM lựa chọn một công cụ trong tập công cụ mà ứng dụng cung cấp, rồi trả về một yêu cầu gọi công cụ có cấu trúc. Yêu cầu thường chứa:

- Tên tool.
- Các đối số theo schema đầu vào.
- Mã định danh của lượt gọi, tùy giao thức của nhà cung cấp.

Mô hình không tự chạy mã Java. Ứng dụng nhận yêu cầu, tìm callback đã đăng ký, kiểm tra dữ liệu và quyền, thực thi logic nghiệp vụ, sau đó gửi kết quả trở lại cuộc hội thoại. Mô hình có thể dùng kết quả đó để trả lời người dùng hoặc đề xuất một tool call khác.

### 2.1. Vòng đời của một tool call

Với `ChatClient`, luồng tổng quát trong Spring AI diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Ứng dụng / ChatClient
    participant M as Mô hình
    participant T as ToolCallingManager
    participant S as Dịch vụ nghiệp vụ

    U->>C: Yêu cầu kiểm tra tồn kho
    C->>M: Prompt + mô tả tool + input schema
    M-->>C: Tool call lookupInventory(sku, warehouse)
    C->>T: Chuyển tool call đến callback
    T->>S: Gọi dịch vụ sau khi kiểm tra đầu vào và quyền
    S-->>T: Kết quả tồn kho
    T-->>C: Tool result
    C->>M: Lịch sử hội thoại + tool result
    M-->>C: Câu trả lời cuối cùng
    C-->>U: Kết quả dễ hiểu
~~~

Các bước chính:

1. Ứng dụng gửi prompt cùng định nghĩa những tool được phép dùng trong lượt gọi.
2. Mô hình quyết định có cần tool hay có thể trả lời trực tiếp.
3. Nếu cần tool, mô hình trả về tên và đối số; đây mới là yêu cầu thực thi.
4. Spring AI phân giải tên tool sang `ToolCallback` phù hợp và gọi callback.
5. Kết quả thực thi được thêm vào lịch sử hội thoại dưới dạng tool result.
6. Mô hình nhận kết quả và có thể gọi tiếp một tool khác hoặc tạo câu trả lời cuối.

Trong cách dùng thông thường, `ToolCallingAdvisor` của `ChatClient` quản lý vòng lặp này và sử dụng `ToolCallingManager` để tìm, thực thi callback. Nếu làm việc trực tiếp ở mức `ChatModel`, ứng dụng cần hiểu rõ phiên bản Spring AI đang dùng và tự quản lý vòng lặp khi đường gọi đó không tự thực thi tool.

### 2.2. Khai báo tool bằng `@Tool`

Khi ứng dụng sở hữu phương thức nghiệp vụ và muốn khai báo trực tiếp, `@Tool` là cách ngắn gọn:

~~~java
@Component
class InventoryTools {

    private final InventoryService inventoryService;

    InventoryTools(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Tool(
        name = "lookupInventory",
        description = "Tra cứu số lượng tồn kho của một SKU tại một kho cụ thể."
    )
    public StockView lookupInventory(
            @ToolParam(description = "Mã SKU cần tra cứu") String sku,
            @ToolParam(description = "Mã kho hoặc tên kho cần tra cứu") String warehouse,
            ToolContext toolContext) {

        String tenantId = (String) toolContext.getContext().get("tenantId");
        if (tenantId == null || tenantId.isBlank()) {
            throw new AccessDeniedException("Thiếu ngữ cảnh tenant hợp lệ");
        }

        return inventoryService.lookup(tenantId, sku, warehouse);
    }
}

record StockView(
    String sku,
    String warehouse,
    int availableQuantity
) {}
~~~

Các thành phần quan trọng:

- `@Tool` đánh dấu phương thức có thể được gọi như một tool. `name` xác định tên mà mô hình nhìn thấy; tên phải duy nhất trong tập tool gửi cho một yêu cầu.
- `description` giải thích tool làm gì và khi nào nên dùng. Mô tả mơ hồ khiến mô hình khó chọn đúng công cụ.
- `@ToolParam` mô tả từng tham số để Spring AI tạo schema đầu vào. Mặc định, tham số thường được xem là bắt buộc; dùng `required = false` hoặc cơ chế nullable được hỗ trợ khi tham số thực sự tùy chọn.
- `ToolContext` là tham số đặc biệt dành cho dữ liệu ứng dụng. Nó không phải trường đầu vào mà mô hình cần tự điền.
- Phương thức vẫn gọi dịch vụ nghiệp vụ thông thường. Nên giữ quy tắc nghiệp vụ, truy cập dữ liệu và phân quyền ở các lớp phù hợp thay vì đưa toàn bộ logic vào lớp tool.

Ví dụ truyền tool và ngữ cảnh vào `ChatClient`:

~~~java
String answer = chatClient.prompt()
    .user("Kiểm tra SKU A-100 tại kho Hà Nội.")
    .tools(inventoryTools)
    .toolContext(Map.of("tenantId", authenticatedTenantId))
    .call()
    .content();
~~~

`authenticatedTenantId` phải lấy từ danh tính đã xác thực của request hoặc security context do máy chủ quản lý. Không lấy tenant, user ID hay vai trò từ nội dung do mô hình sinh ra.

### 2.3. `ToolCallback` là hợp đồng thực thi

`@Tool` là cách khai báo ở mức phương thức. Ở mức trừu tượng, Spring AI dùng `ToolCallback` để biểu diễn một tool có thể được mô hình yêu cầu gọi.

Một callback gắn hai phần với nhau:

- **Tool definition:** tên, mô tả và JSON Schema đầu vào được gửi cho mô hình.
- **Execution:** mã được ứng dụng gọi khi nhận được tool call tương ứng.

Spring AI cung cấp các cách tạo callback phổ biến:

| Cách tạo | Phù hợp khi |
|---|---|
| `@Tool` | Muốn khai báo tool ngay trên phương thức do ứng dụng sở hữu |
| `MethodToolCallback` | Cần tạo tool từ một phương thức theo cách lập trình, ví dụ cấu hình động |
| `FunctionToolCallback` | Muốn bọc `Function`, `Supplier`, `Consumer`, `BiFunction`, lambda hoặc method reference |

Ví dụ tạo tool từ một hàm:

~~~java
record InventoryQuery(String sku, String warehouse) {}

String tenantId = authenticatedTenantId;
ToolCallback lookupInventory = FunctionToolCallback
    .builder("lookupInventory", (InventoryQuery query) ->
        inventoryService.lookup(tenantId, query.sku(), query.warehouse()))
    .description("Tra cứu tồn kho theo SKU và kho.")
    .inputType(InventoryQuery.class)
    .build();
~~~

Trong ví dụ này, `InventoryQuery` mô tả dữ liệu đầu vào cho hàm. Spring AI dùng kiểu đầu vào để tạo schema. `tenantId` được lấy từ ngữ cảnh đã xác thực của ứng dụng và đóng vào lambda; nó không xuất hiện trong dữ liệu mô hình gửi lên. Callback vẫn gọi `InventoryService`; nó không thay thế lớp nghiệp vụ.

Nên chọn một cách khai báo nhất quán theo cấu trúc ứng dụng. Có thể kết hợp nhiều kiểu callback trong cùng một yêu cầu nếu cần, nhưng phải tránh đăng ký trùng tên tool.

### 2.4. Thiết kế input schema

Schema là hợp đồng giữa mô hình và ứng dụng. Schema tốt giúp mô hình biết cần cung cấp dữ liệu nào và giảm lỗi phân tích đối số.

Một tool tra cứu tồn kho có thể có schema khái niệm như sau:

~~~json
{
  "type": "object",
  "properties": {
    "sku": {
      "type": "string",
      "description": "Mã SKU chính xác cần tra cứu"
    },
    "warehouse": {
      "type": "string",
      "description": "Mã kho hoặc tên kho đã biết"
    }
  },
  "required": ["sku", "warehouse"],
  "additionalProperties": false
}
~~~

Khi thiết kế schema:

- Đặt tên tool cụ thể, ổn định và duy nhất.
- Viết mô tả theo ngôn ngữ nghiệp vụ, nêu rõ điều kiện sử dụng.
- Mô tả từng trường bằng ví dụ hoặc quy tắc định dạng khi cần.
- Chỉ đánh dấu trường bắt buộc khi mô hình có thể suy ra hoặc người dùng đã cung cấp giá trị đó.
- Giới hạn giá trị bằng enum, kiểu dữ liệu hoặc ràng buộc phù hợp nếu API hỗ trợ.
- Không đưa dữ liệu nội bộ như quyền hạn, tenant ID, token truy cập hoặc thông tin xác thực vào schema để mô hình tự điền.

Schema giúp mô hình tạo yêu cầu đúng hình dạng; nó không phải cơ chế xác thực bảo mật. Ứng dụng vẫn phải kiểm tra dữ liệu ở ranh giới thực thi.

## 3. Function calling: thuật ngữ và cách triển khai

Function calling thường được dùng để mô tả khả năng mô hình trả về yêu cầu gọi một hàm thay vì chỉ tạo văn bản. Thuật ngữ này nổi bật trong các API LLM đời đầu, nơi nhà cung cấp biểu diễn hành động có thể gọi dưới dạng function. Nhiều API hiện dùng khái niệm rộng hơn là tool calling.

Trong ngữ cảnh Spring AI, cần phân biệt hai cách dùng:

1. **Function calling theo nghĩa giao thức:** tên gọi cho cơ chế mô hình yêu cầu ứng dụng gọi một hàm. Khi nói theo nghĩa này, nó gần với tool calling.
2. **`FunctionToolCallback` theo nghĩa API Spring AI:** một lớp callback cụ thể giúp bọc các kiểu hàm Java như `Function`, `Supplier`, `Consumer` hoặc `BiFunction` thành tool.

Vì vậy, không nên kết luận rằng function calling và tool calling luôn là hai cơ chế kỹ thuật hoàn toàn tách biệt. Khi đọc tài liệu của một nhà cung cấp, hãy kiểm tra họ dùng thuật ngữ nào và cấu trúc request/response ra sao. Khi đọc mã Spring AI, hãy phân biệt khái niệm tool calling tổng quát với lớp `FunctionToolCallback`.

Một hàm Java thông thường chỉ được gọi bởi mã ứng dụng. Khi bọc nó thành tool, ứng dụng công bố tên, mô tả và schema cho mô hình. Mô hình có thể đề xuất gọi hàm đó; ứng dụng mới là bên thực thi hàm.

## 4. Structured output: yêu cầu câu trả lời theo cấu trúc dữ liệu

Structured output giải quyết bài toán khác: ứng dụng muốn nhận kết quả của mô hình dưới dạng dữ liệu có kiểu, ví dụ một record Java, thay vì một đoạn văn tự do.

Ví dụ, ứng dụng muốn phân loại yêu cầu của người dùng:

~~~java
record StockIntent(
    String action,
    String sku,
    String warehouse,
    Integer requestedQuantity
) {}

StockIntent intent = chatClient.prompt()
    .user("""
        Phân tích yêu cầu sau và trích xuất hành động,
        SKU, kho và số lượng nếu có:
        "Kiểm tra SKU A-100 ở kho Hà Nội, cần 20 sản phẩm."
        """)
    .call()
    .entity(StockIntent.class);
~~~

Với `.entity(StockIntent.class)`, Spring AI dùng kiểu Java làm cơ sở hướng dẫn mô hình tạo dữ liệu có cấu trúc, sau đó chuyển nội dung phản hồi thành đối tượng tương ứng. Ứng dụng có thể đọc `intent.action()` hoặc `intent.sku()` mà không phải tự tách chuỗi văn bản.

Cần hiểu giới hạn của cách làm này:

- Schema trong prompt hướng dẫn mô hình; nếu không dùng cơ chế ràng buộc ở cấp nhà cung cấp, mô hình vẫn có thể trả về dữ liệu sai cấu trúc.
- Việc parse thành đối tượng không chứng minh giá trị là đúng về mặt nghiệp vụ. Ví dụ, SKU có thể đúng kiểu `String` nhưng không tồn tại.
- Với dữ liệu quan trọng, cần kiểm tra schema, xác thực nghiệp vụ và xử lý trường hợp parse thất bại. Spring AI cung cấp các tùy chọn như kiểm tra schema và structured output do nhà cung cấp hỗ trợ; mức bảo đảm phụ thuộc model/provider.
- API `.entity(...)` cần phản hồi hoàn chỉnh nên không phải đường xử lý streaming dạng từng chunk.

### 4.1. Structured output khác tool input schema ở đâu?

Hai loại schema có thể cùng dùng JSON Schema, nhưng hướng dữ liệu khác nhau:

| Tiêu chí | Tool input schema | Structured output schema |
|---|---|---|
| Mục đích | Mô tả đối số cho một thao tác mà mô hình muốn yêu cầu | Mô tả hình dạng câu trả lời mà ứng dụng muốn nhận |
| Hướng dữ liệu | Mô hình → ứng dụng/tool | Mô hình → ứng dụng |
| Ý nghĩa | “Hãy gọi công cụ này với các đối số sau” | “Hãy trả lời bằng một đối tượng có các trường này” |
| Hệ quả | Có thể kích hoạt mã và tác động đến hệ thống | Bản thân kết quả không thực thi thao tác nghiệp vụ |
| Ví dụ | `lookupInventory(sku, warehouse)` | `StockIntent(action, sku, warehouse, requestedQuantity)` |

Tool result cũng có thể là JSON hoặc một đối tượng có cấu trúc. Điều đó không làm tool calling trở thành structured output: điểm quyết định vẫn là ứng dụng đang xử lý một yêu cầu gọi thao tác hay đang phân tích câu trả lời của mô hình.

### 4.2. Có thể kết hợp structured output với tool calling không?

Có. Một luồng có thể dùng structured output để chuẩn hóa yêu cầu, sau đó ứng dụng quyết định có cung cấp tool nào cho mô hình. Một luồng khác có thể dùng tool calling để lấy dữ liệu, rồi yêu cầu mô hình trả lời cuối cùng theo một cấu trúc nhất định.

Ví dụ:

~~~text
Yêu cầu tự nhiên
    ↓
Structured output: StockIntent
    ↓
Ứng dụng xác thực SKU, kho, số lượng và quyền
    ↓
Tool calling: lookupInventory
    ↓
Tool result: StockView
    ↓
Structured output hoặc câu trả lời văn bản
~~~

Ứng dụng có thể tự quyết định gọi dịch vụ sau khi nhận `StockIntent`, thay vì để mô hình chọn tool. Cách nào phù hợp phụ thuộc vào việc quyết định nghiệp vụ có cần suy luận linh hoạt hay phải tuân theo một quy trình cố định.

## 5. Agent: điều phối nhiều bước hướng tới mục tiêu

Agent là một cách tổ chức hệ thống trong đó LLM tham gia quyết định bước tiếp theo dựa trên mục tiêu, trạng thái và kết quả quan sát được. Một agent thường có các thành phần:

- **Goal:** mục tiêu cần hoàn thành.
- **State hoặc context:** thông tin của phiên làm việc và các kết quả đã thu thập.
- **Decision:** mô hình chọn trả lời, gọi tool hoặc tiếp tục một bước khác.
- **Tools:** các thao tác mà ứng dụng cho phép.
- **Observation:** kết quả của từng thao tác.
- **Stop condition:** điều kiện dừng, chẳng hạn đã có câu trả lời, hết ngân sách lượt gọi hoặc cần người dùng phê duyệt.

Ví dụ, yêu cầu “kiểm tra hàng và chuẩn bị đơn” có thể gồm các bước:

1. Xác định SKU, kho và số lượng cần mua.
2. Gọi tool tra cứu tồn kho.
3. Nếu thiếu hàng, gọi tool tra cứu sản phẩm thay thế.
4. Tổng hợp lựa chọn và hỏi người dùng xác nhận.
5. Chỉ sau khi có xác nhận hợp lệ, gọi tool tạo đơn.
6. Đọc kết quả tạo đơn và trả mã đơn cho người dùng.

Một lần gọi tool không tự động tạo thành agent. Một request có thể dùng tool calling một lần rồi kết thúc. Ngược lại, agent có thể gọi nhiều tool qua nhiều lượt và thay đổi kế hoạch dựa trên kết quả.

### 5.1. Vòng điều phối của agent

~~~mermaid
flowchart TD
    A["Nhận mục tiêu và context"] --> B["LLM chọn bước tiếp theo"]
    B --> C{"Cần gọi tool?"}
    C -->|Không| D["Tạo câu trả lời"]
    C -->|Có| E["Ứng dụng kiểm tra quyền và giới hạn"]
    E --> F{"Được phép thực thi?"}
    F -->|Không| G["Từ chối hoặc yêu cầu phê duyệt"]
    F -->|Có| H["Thực thi tool"]
    H --> I["Ghi nhận observation và cập nhật state"]
    I --> J{"Đã đạt điều kiện dừng?"}
    J -->|Chưa| B
    J -->|Rồi| D
~~~

Spring AI cung cấp các khối xây dựng như `ChatClient`, tool callbacks, advisors và các cơ chế quản lý hội thoại. Có thể kết hợp chúng để xây dựng vòng điều phối. Không nên mặc định rằng mọi ứng dụng dùng `ChatClient` và `@Tool` đều đã là một agent hoàn chỉnh. Agent cần thêm quy tắc về mục tiêu, trạng thái, giới hạn vòng lặp, quyền thực thi và điều kiện dừng.

### 5.2. Khi nào cần agent?

Dùng tool calling trực tiếp khi quy trình có ít bước, có thể dự đoán và không cần mô hình tự điều chỉnh kế hoạch. Cân nhắc agent khi:

- Số bước phụ thuộc vào kết quả của bước trước.
- Có nhiều công cụ và cần chọn công cụ theo ngữ cảnh.
- Có thể phải thử phương án khác khi một nguồn dữ liệu không có kết quả.
- Cần giữ trạng thái công việc qua nhiều lượt tương tác.

Nếu quy trình có thứ tự cố định và quy tắc nghiệp vụ rõ ràng, một workflow thông thường trong ứng dụng thường dễ kiểm soát hơn. Không cần đưa LLM vào quyết định mà mã nghiệp vụ có thể thực hiện chính xác.

## 6. Ranh giới trách nhiệm của ứng dụng

Đây là phần quan trọng nhất khi đưa tool calling vào hệ thống thật. Mô tả tool và schema chỉ giúp mô hình biết cách yêu cầu thao tác. Chúng không trao quyền cho mô hình và không thay thế kiểm tra ở backend.

### 6.1. Xác thực và phân quyền ở phía máy chủ

Mỗi tool phải được xem như một endpoint nghiệp vụ có thể bị gọi với dữ liệu không đáng tin cậy.

- Lấy user ID, tenant ID và vai trò từ principal hoặc security context đã xác thực.
- Kiểm tra người dùng có quyền truy cập đúng tài nguyên trước khi gọi repository hoặc service.
- Kiểm tra quyền ở mỗi lần thực thi, kể cả khi mô hình đã được cung cấp mô tả tool trong prompt.
- Chỉ cung cấp tập tool phù hợp với người dùng và ngữ cảnh hiện tại.
- Tách tool đọc dữ liệu khỏi tool ghi dữ liệu hoặc tạo giao dịch.
- Với thao tác có tác động lớn, yêu cầu xác nhận của người dùng hoặc một bước phê duyệt rõ ràng.

`ToolContext` hữu ích để truyền dữ liệu server-side như tenant ID, user ID hoặc request metadata đến phương thức tool mà không đưa những giá trị đó vào input schema cho mô hình. Tuy nhiên, `ToolContext` không tự xác thực dữ liệu và cũng không tự áp dụng phân quyền. Ứng dụng phải tạo context từ nguồn đáng tin cậy và kiểm tra quyền trong logic thực thi.

### 6.2. Giới hạn tập tool được phép dùng

Không nên công bố mọi tool cho mọi request. Một số nguyên tắc:

- Chỉ đăng ký tool cần thiết cho tác vụ hiện tại.
- Tool có tác động phá hủy hoặc ghi dữ liệu nên được thêm theo từng request sau khi kiểm tra quyền.
- Tránh cấu hình tool nhạy cảm thành default tool dùng chung cho mọi yêu cầu.
- Nếu dùng cơ chế phân giải tool theo tên, bảo đảm resolver chỉ có thể trả về những callback đã được cho phép trong ngữ cảnh đó.
- Đặt giới hạn số lần gọi, thời gian chạy và ngân sách token cho mỗi tác vụ.

### 6.3. Xác thực đối số và dữ liệu trả về

Không tin rằng đối số hợp lệ chỉ vì chúng tuân theo JSON Schema. Backend cần kiểm tra:

- SKU, mã đơn, mã kho có tồn tại không.
- Số lượng có nằm trong khoảng cho phép không.
- Người dùng có quyền truy cập bản ghi đó không.
- Trạng thái hiện tại có cho phép thao tác không.
- Dữ liệu trả về có chứa thông tin nhạy cảm không cần thiết cho mô hình hay không.

Chỉ trả về phần dữ liệu cần thiết để mô hình hoàn thành tác vụ. Không đưa mật khẩu, access token, dữ liệu thanh toán hoặc thông tin cá nhân không liên quan vào tool result.

## 7. Xử lý lỗi và điều phối nhiều lượt gọi

Một tool call có thể thất bại ở nhiều lớp: đối số không hợp lệ, không tìm thấy callback, không đủ quyền, dịch vụ nghiệp vụ từ chối, hệ thống phụ trợ timeout hoặc kết quả không thể chuyển đổi. Ứng dụng cần định nghĩa cách xử lý nhất quán cho từng nhóm lỗi.

### 7.1. Phân loại lỗi

| Nhóm lỗi | Ví dụ | Cách xử lý phù hợp |
|---|---|---|
| Lỗi đầu vào | Thiếu SKU, số lượng âm, sai định dạng | Từ chối đầu vào; yêu cầu người dùng bổ sung hoặc sửa |
| Lỗi phân giải tool | Tên tool không tồn tại hoặc không được đăng ký | Không thực thi; ghi log và trả lỗi an toàn |
| Lỗi xác thực/phân quyền | Tenant không hợp lệ, không có quyền xem đơn | Dừng thao tác; không thử lại bằng quyền khác |
| Lỗi nghiệp vụ | Không đủ hàng, đơn đã bị hủy | Trả kết quả nghiệp vụ có cấu trúc để mô hình giải thích |
| Lỗi hạ tầng | Timeout, kết nối dịch vụ phụ trợ bị gián đoạn | Thử lại có giới hạn nếu thao tác an toàn; nếu không thì báo trạng thái chưa xác định |
| Lỗi chuyển đổi | Đối số JSON hoặc kết quả không thể chuyển đổi | Ghi nhận lỗi kỹ thuật; không coi dữ liệu chưa parse là hợp lệ |

Không nên gửi stack trace, câu truy vấn SQL, tên máy chủ nội bộ hoặc thông tin xác thực vào nội dung mà mô hình có thể nhìn thấy. Có thể ánh xạ lỗi kỹ thuật thành mã lỗi và thông báo ngắn, an toàn.

### 7.2. Retry và tính idempotent

Retry chỉ phù hợp với lỗi tạm thời và thao tác có thể lặp lại an toàn. Tra cứu tồn kho thường có thể thử lại. Tạo đơn, trừ tiền hoặc gửi lệnh thanh toán cần cơ chế idempotency key và kiểm tra trạng thái trước khi retry.

Đặc biệt, timeout không luôn có nghĩa là thao tác chưa xảy ra. Ví dụ, dịch vụ tạo đơn có thể đã ghi đơn thành công nhưng phản hồi bị mất. Nếu gọi lại một cách mù quáng, hệ thống có thể tạo hai đơn. Trong trường hợp này, cần tra cứu bằng mã yêu cầu idempotent hoặc trạng thái giao dịch trước khi quyết định tiếp tục.

### 7.3. Điều phối nhiều tool

Khi mô hình yêu cầu nhiều tool trong một phản hồi, ứng dụng phải xác định liệu các thao tác có độc lập hay có phụ thuộc thứ tự. Không nên giả định thứ tự thực thi hoặc khả năng chạy song song nếu framework/provider không bảo đảm điều đó.

- Các truy vấn độc lập có thể được thực thi song song nếu dịch vụ cho phép.
- Các thao tác phụ thuộc kết quả phải chạy tuần tự.
- Mỗi tool call cần có timeout và giới hạn tài nguyên riêng.
- Agent cần giới hạn số vòng lặp và có điều kiện dừng rõ ràng.
- Khi cần phê duyệt, dừng trước thao tác nhạy cảm và lưu trạng thái chờ xác nhận; không để mô hình tự diễn giải một câu trả lời mơ hồ thành sự đồng ý.

## 8. Kiểm thử tích hợp tool calling

Kiểm thử cần chứng minh cả hợp đồng dữ liệu lẫn hành vi thực thi. Chỉ kiểm tra rằng mô hình trả về một đoạn văn có nhắc tên tool là chưa đủ.

### 8.1. Unit test cho logic nghiệp vụ

Kiểm tra `InventoryService` độc lập với LLM:

- Trả đúng tồn kho theo tenant, SKU và kho.
- Không cho truy cập dữ liệu của tenant khác.
- Xử lý SKU không tồn tại.
- Xử lý kho không hợp lệ và số lượng vượt giới hạn.

Các quy tắc nghiệp vụ quan trọng phải được kiểm thử ở lớp service để chúng vẫn đúng dù tool được gọi từ LLM, REST API hay một luồng khác.

### 8.2. Kiểm thử phương thức tool và schema

Kiểm tra phương thức được đánh dấu `@Tool` hoặc callback:

- Tên tool và mô tả đúng mục đích.
- Schema có đủ trường và kiểu dữ liệu mong muốn.
- Trường bắt buộc và tùy chọn được khai báo chính xác.
- `ToolContext` không xuất hiện như một đối số mà mô hình phải cung cấp.
- Dữ liệu context thiếu hoặc sai không thể vượt qua kiểm tra quyền.
- Kết quả trả về không để lộ trường nhạy cảm.

### 8.3. Integration test vòng tool calling

Dùng `ChatModel` giả lập hoặc một model test có phản hồi xác định để kiểm tra toàn bộ luồng:

1. Ứng dụng gửi prompt và tool definition.
2. Model trả về tool call với tên và đối số đã định.
3. Callback tương ứng được gọi đúng một lần.
4. Tool result được đưa trở lại lịch sử hội thoại.
5. Model nhận tool result và trả lời cuối cùng.
6. Không có tool nào được thực thi nếu request bị từ chối ở bước kiểm tra quyền.

Nên kiểm tra cả trường hợp model trả lời trực tiếp mà không cần tool, gọi tool không tồn tại, gửi đối số sai, tool timeout và tool trả lỗi nghiệp vụ. Dùng phản hồi xác định giúp test ổn định, không phụ thuộc vào việc LLM có chọn đúng câu chữ trong mỗi lần chạy hay không.

### 8.4. Kiểm thử an toàn và tác động

Với tool ghi dữ liệu hoặc thực hiện hành động bên ngoài, cần kiểm thử các trường hợp:

- Người dùng không có quyền không thể gọi tool, kể cả khi prompt yêu cầu.
- Mô hình không thể tự đặt tenant ID hoặc user ID để truy cập dữ liệu khác.
- Thao tác cần xác nhận không chạy trước khi nhận được xác nhận hợp lệ.
- Retry không tạo bản ghi hoặc giao dịch trùng lặp.
- Log và tool result không chứa bí mật.
- Agent dừng khi vượt số vòng lặp, thời gian hoặc ngân sách đã đặt.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| “Mô hình đã gọi tool nên nghiệp vụ đã chạy.” | Model chỉ trả về yêu cầu; ứng dụng hoặc framework mới thực thi callback. |
| “Function calling và tool calling luôn khác nhau.” | Function calling thường là tên lịch sử hoặc cách gọi một dạng tool; trong Spring AI, `FunctionToolCallback` là một kiểu triển khai cụ thể. |
| “Structured output là tool calling vì đều dùng JSON.” | Structured output định hình câu trả lời; tool calling yêu cầu ứng dụng thực hiện một thao tác. |
| “Có `@Tool` nghĩa là đã có agent.” | `@Tool` chỉ khai báo công cụ; agent còn cần mục tiêu, trạng thái, vòng điều phối và điều kiện dừng. |
| “Schema hợp lệ nghĩa là request an toàn.” | Schema chỉ kiểm soát hình dạng dữ liệu; xác thực và phân quyền phải do backend thực hiện. |
| “ToolContext tự bảo đảm quyền truy cập.” | ToolContext chỉ vận chuyển dữ liệu nội bộ; ứng dụng vẫn phải xác minh nguồn và áp dụng quyền. |
| “Có thể retry mọi tool call khi timeout.” | Retry thao tác ghi có thể tạo tác động trùng; cần idempotency và kiểm tra trạng thái. |

## 10. Cách chọn cơ chế cho một yêu cầu

Có thể dùng các câu hỏi sau để chọn đúng thành phần:

1. Ứng dụng chỉ cần một câu trả lời có các trường dữ liệu rõ ràng? Dùng structured output.
2. Mô hình cần chọn và yêu cầu một thao tác mà ứng dụng cung cấp? Dùng tool calling.
3. Hàm Java đã có sẵn và muốn đưa nó vào tập tool? Có thể dùng `FunctionToolCallback`.
4. Quy trình có nhiều bước phụ thuộc kết quả và cần mô hình quyết định bước tiếp theo? Cân nhắc agent.
5. Quy trình có thứ tự cố định và quy tắc rõ ràng? Dùng workflow/service thông thường; chỉ dùng LLM ở bước thực sự cần hiểu ngôn ngữ hoặc xử lý thông tin không cấu trúc.

Trong hệ thống thực tế, thường kết hợp nhiều cơ chế: structured output để chuẩn hóa đầu vào, tool calling để truy cập nghiệp vụ, và agent để điều phối khi quy trình cần thích nghi. Quyền thực thi, xác thực dữ liệu, giới hạn tài nguyên và kiểm soát lỗi luôn nằm ở ứng dụng.

## Tài liệu tham khảo

- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): khai báo `@Tool`, `ToolCallback`, `MethodToolCallback`, `FunctionToolCallback`, input schema, `ToolContext` và vòng thực thi.
- [Spring AI — Structured Output](https://docs.spring.io/spring-ai/reference/api/structured-output.html): chuyển phản hồi của mô hình thành kiểu Java, schema validation và provider-native structured output.
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html): cách cấu hình `ChatClient`, cung cấp tool và tùy chỉnh vòng điều phối.

API cụ thể có thể thay đổi theo phiên bản Spring AI và nhà cung cấp mô hình. Khi triển khai, đối chiếu tài liệu đúng phiên bản đang dùng, đặc biệt với cách đăng ký callback, tự động điều phối tool và cơ chế structured output của provider.


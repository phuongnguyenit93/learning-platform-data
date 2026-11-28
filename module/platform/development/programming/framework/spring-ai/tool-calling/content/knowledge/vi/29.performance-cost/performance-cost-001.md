# Ước lượng số lượt mô hình cho một tác vụ nhiều công cụ

Trong **SPRING_AI_TOOL_CALLING**, một yêu cầu của người dùng có thể khiến mô hình yêu cầu nhiều `@Tool` hoặc `ToolCallback`, ứng dụng thực thi các callback, gửi kết quả qua `ToolResponseMessage`, rồi gọi mô hình tiếp để quyết định bước sau. Khi phân tích hiệu năng và chi phí, câu hỏi quan trọng không phải chỉ là “có bao nhiêu công cụ?”, mà là:

> **Mô hình phải được gọi bao nhiêu lần để nhận đủ dữ liệu, thực thi các bước phụ thuộc và tạo ra kết quả cuối?**

Ba lời gọi tool trong cùng một phản hồi của model có thể chỉ làm phát sinh một lần gọi model tiếp theo. Ngược lại, ba tool bắt buộc chạy nối tiếp có thể cần đến bốn lần gọi model. Một tool tự gọi một LLM khác, một vòng retry do lỗi hoặc một bước Tool Search có thể làm tổng số lần gọi model còn cao hơn nữa.

Bài học giải thích cách dựng **ước lượng thấp nhất, dự báo điển hình và giới hạn vận hành**, rồi chuyển chúng thành dự báo token, tiền và độ trễ. Nội dung dựa trên cơ chế `ChatClient`, `ToolCallingAdvisor`, `ToolCallingManager` và `ToolContext` trong **Spring AI 2.x**. Một số đoạn code là ví dụ ứng dụng, không phải API framework được tạo sẵn.

## 1. Thống nhất các đơn vị đếm

Trước khi tính toán, phải phân biệt ít nhất năm đơn vị.

| Đơn vị | Ví dụ | Có phải một model call? |
|---|---|---|
| **User turn** | Người dùng hỏi “Đơn ORD-8F31A2 giao đến đâu?” | Không; một turn có thể chứa nhiều model calls |
| **ChatClient exchange** | Một lần gọi `chatClient.prompt().call()` | Không nhất thiết; tool loop có thể gọi model nhiều lần |
| **Model call / model iteration** | Một request thực sự tới `ChatModel` hoặc provider | **Có** |
| **Tool call** | Model yêu cầu `lookupInventory` với một bộ arguments | Không; ứng dụng thực thi callback |
| **Remote API attempt** | Tool gọi REST API, retry một lần | Không, trừ khi tool tự gọi model |

Ví dụ:

~~~text
User turn 1
  ChatClient exchange 1
    Model call #1 -> 2 tool calls
      Tool A -> HTTP request #1
      Tool B -> HTTP request #2, retry #3
    Model call #2 -> trả lời
~~~

Trong ví dụ có một user turn, một ChatClient exchange, **hai model calls**, **hai tool calls** và **ba HTTP attempts**.

Đặc biệt, một response streaming có hàng trăm text chunks **không tương đương hàng trăm model calls**. Chunks là các phần của cùng một lần model invocation, trừ khi ứng dụng chủ động khởi tạo một model request mới.

## 2. Vòng tool calling cơ bản trong Spring AI

Trong Spring AI 2.x, `ChatClient` mặc định có `ToolCallingAdvisor` điều phối vòng gọi tool. Quy trình:

~~~mermaid
flowchart TD
    A[User request + tool definitions] --> B[Model call #1]
    B --> C{Phản hồi chứa tool calls?}
    C -- Không --> Z[Trả câu trả lời]
    C -- Có --> D[ToolCallingManager thực thi ToolCallback]
    D --> E[Thêm AssistantMessage và ToolResponseMessage vào history]
    E --> F[Model call tiếp theo]
    F --> C
~~~

Mỗi khi model trả một hoặc nhiều tool calls, advisor thực thi những yêu cầu đó, bổ sung kết quả vào lịch sử rồi gọi model tiếp, trừ trường hợp kết thúc sớm như `returnDirect`, chờ xác nhận hoặc dừng do giới hạn/lỗi.

Ví dụ một tool tra cứu trạng thái:

~~~java
public class OrderTools {

    private final OrderService orderService;

    public OrderTools(OrderService orderService) {
        this.orderService = orderService;
    }

    @Tool(
        name = "get_order_status",
        description = """
            Tra cứu trạng thái đơn hàng mà người dùng có quyền xem.
            Không dùng để hủy đơn hoặc thay đổi thông tin.
            """
    )
    public OrderStatusResult status(
            @ToolParam(description = "Mã đơn hàng")
            String orderNumber,
            ToolContext toolContext) {

        Actor actor = requireAuthenticatedActor(toolContext);
        return orderService.readAuthorizedStatus(
            actor, orderNumber
        );
    }
}
~~~

Gọi từ `ChatClient`:

~~~java
ChatResponse response = chatClient.prompt()
    .user("Cho tôi biết ORD-8F31A2 đang ở đâu.")
    .tools(orderTools)
    .toolContext(Map.of("actor", serverAuthenticatedActor))
    .call()
    .chatResponse();
~~~

Mô hình chỉ thấy tool definition và những arguments nó được phép đề xuất. Danh tính/tenant trong `ToolContext` phải đến từ server, không phải JSON của model. Quyền thực thi được kiểm tra tại `OrderService` ngay cả khi model chọn tool hợp lý.

Một sơ đồ đơn giản không cho biết chắc chắn số lần gọi: model có thể trả lời luôn, gọi tool một lần, gọi nhiều tool trong một phản hồi hoặc tiếp tục yêu cầu tool khác sau khi nhận kết quả.

## 3. Công thức nền: một lần model đầu và các vòng quay lại

Đặt:

- `M`: tổng số **model calls trực tiếp** trong một ChatClient exchange.
- `B`: số **batch tool result** mà ứng dụng đã gửi trở lại model để tiếp tục.
- `T`: tổng số tool calls được thực thi trong exchange.
- `Kᵢ`: số tool calls trong batch thứ `i`.

Nếu mô hình chỉ tạo tool-call responses trong `B` vòng và cuối cùng trả một phản hồi không còn tool call, không có retry hay model phụ:

~~~text
M = B + 1

T = Σ Kᵢ, i từ 1 đến B
~~~

**Không có công thức chung `M = T + 1`.** Công thức đó chỉ đúng trong trường hợp mỗi vòng model gọi đúng một tool, kết quả luôn được gửi trở lại và cần một model call cuối để tổng hợp.

Ví dụ:

| Cách diễn ra | T (tool calls) | B (batch quay lại model) | M (model calls) |
|---|---:|---:|---:|
| Model trả lời không dùng tool | 0 | 0 | 1 |
| Một tool, rồi trả lời | 1 | 1 | 2 |
| Hai tool trong **cùng một model response**, rồi trả lời | 2 | 1 | 2 |
| Ba tool độc lập trong một batch | 3 | 1 | 2 |
| Ba tool phụ thuộc, mỗi vòng một tool | 3 | 3 | 4 |
| Năm tool, chia hai batch | 5 | 2 | 3 |

Bảng phản ánh **kịch bản giả định** và không cam kết một model/provider luôn tạo được multi-tool response. Khả năng gọi nhiều tool trong cùng phản hồi phụ thuộc provider, model, cấu hình tool calling và nội dung yêu cầu.

### Khi công thức cần điều chỉnh

- `returnDirect=true` có thể kết thúc ngay sau tool mà **không cần model call tổng hợp**.
- Có bước gọi model chỉ để tìm tool, xác thực đầu ra hoặc tự đánh giá: cộng thêm các model calls đó.
- Có retry ở tầng model/HTTP provider: tính thêm những lần thực sự gửi request.
- Một tool tự gọi `ChatModel`/embedding model: tính như **model calls lồng nhau**, không nhầm với vòng `ToolCallingAdvisor` bên ngoài.
- Bị chặn ở bước xác nhận, hạn mức hoặc lỗi: có thể dừng mà không có câu trả lời cuối.

Vì vậy, nên biểu diễn M theo **sự kiện thực tế**, còn `B + 1` là ước lượng cấu trúc của vòng bình thường.

## 4. Hai tool độc lập: có thể gom vào cùng phản hồi

Giả sử người dùng hỏi:

> “Còn bao nhiêu sản phẩm SKU-100 ở Hà Nội và phí giao đến Đà Nẵng là bao nhiêu?”

Hai tool:

~~~text
lookup_inventory(sku, warehouse)
estimate_shipping(sku, destination)
~~~

Nếu hai đầu vào đều có sẵn và mỗi tool không cần kết quả của tool kia, model **có thể** đề xuất cả hai trong một phản hồi:

~~~mermaid
sequenceDiagram
    participant U as User
    participant M as Model
    participant A as App / Tool manager
    participant I as Inventory tool
    participant S as Shipping tool

    U->>M: Hỏi tồn kho và phí ship
    M-->>A: Model call #1 -> 2 tool calls
    A->>I: lookup_inventory
    A->>S: estimate_shipping
    I-->>A: inventory result
    S-->>A: shipping result
    A->>M: Model call #2 với cả 2 kết quả
    M-->>U: Câu trả lời cuối
~~~

Khi đó `T=2` nhưng `M=2`.

Tuy vậy, **một batch tool call không có nghĩa hai callback chắc chắn chạy song song ở runtime**. Việc thực thi song song/tuần tự còn tùy `ToolCallingManager`, cấu hình executor, khả năng thread-safe của callback và chính sách nghiệp vụ. Về số model calls, hai kết quả vẫn có thể được gộp để đưa vào lần gọi model kế tiếp.

Nếu model chỉ đề xuất `lookup_inventory` ở lần đầu rồi, sau khi nhận dữ liệu, mới nhớ gọi `estimate_shipping`:

~~~text
Model #1 -> lookup_inventory
Model #2 -> estimate_shipping
Model #3 -> final answer
~~~

Khi đó **hai tool vẫn như cũ nhưng M tăng từ 2 lên 3**. Đây là lý do cần đo trên tập câu hỏi thực tế thay vì suy từ số tool được đăng ký.

## 5. Công cụ có phụ thuộc: số tầng quyết định số vòng tối thiểu

Một tác vụ có thể chứa các phụ thuộc dữ liệu:

~~~text
A: get_customer_order(orderNumber)
B: get_shipment_tracking(shipmentId lấy từ A)
C: estimate_delivery(trackingEvents lấy từ B)
~~~

Không thể gọi B nếu chưa biết `shipmentId`, và không thể gọi C nếu chưa có `trackingEvents`. Dù ba callback đều tồn tại sẵn, mô hình thông thường cần ba batch riêng:

~~~mermaid
flowchart TD
    A[Model #1: chọn get_customer_order] --> B[Tool A: trả shipmentId]
    B --> C[Model #2: chọn get_shipment_tracking]
    C --> D[Tool B: trả trackingEvents]
    D --> E[Model #3: chọn estimate_delivery]
    E --> F[Tool C: trả ETA]
    F --> G[Model #4: tổng hợp câu trả lời]
~~~

Định nghĩa `D` là số **tầng phụ thuộc tool** trên đường dài nhất trong đồ thị không chu trình, tính theo những tầng cần có vòng model riêng. Với những điều kiện lý tưởng:

~~~text
M_min ≈ D + 1
~~~

Điều kiện của công thức:

1. Model có thể biết trước công cụ cần gọi khi đầu vào tương ứng đã sẵn.
2. Các công cụ cùng tầng được model yêu cầu trong một phản hồi.
3. Không có retry, verification call, tool-search round hoặc mô hình phụ.
4. Tool results được gửi lại cho model sau từng tầng.
5. Có một model call cuối để trả lời.

Với ba tool nối tiếp: `D=3` nên `M_min=4`. Với năm tool độc lập: `D=1` nên `M_min=2`.

**Đây là giới hạn cấu trúc trong một thiết kế đã biết đồ thị**, không phải bảo đảm model luôn chọn tối ưu. Nếu mô hình chia nhỏ các tool độc lập, số lần gọi có thể cao hơn. Nếu application service tự gộp nhiều thao tác vào một tool nghiệp vụ, số tầng mô hình nhìn thấy có thể giảm, dù số remote API calls phía dưới không giảm.

## 6. Đồ thị fan-out / fan-in: ví dụ thực tế

Xét workflow xác định có nên ưu đãi giao hàng:

- A — `lookupInventory`: lấy số lượng tồn.
- B — `estimateShipping`: lấy phí giao.
- C — `evaluateFulfillment`: cần dữ liệu từ cả A và B.
- D — Model tổng hợp câu trả lời.

~~~mermaid
flowchart TD
    U[User query] --> M1[Model call #1]
    M1 --> A[Tool A: inventory]
    M1 --> B[Tool B: shipping]
    A --> M2[Model call #2]
    B --> M2
    M2 --> C[Tool C: fulfillment decision]
    C --> M3[Model call #3: final answer]
~~~

Đồ thị tool có ba node nhưng chỉ hai tầng:

~~~text
Tầng tool #1: A và B — độc lập
Tầng tool #2: C — phụ thuộc cả A và B
Final: model trả lời
~~~

Do đó dự báo lý tưởng:

~~~text
D = 2
T = 3
M_min = D + 1 = 3
~~~

Một cách thực thi kém hiệu quả hơn:

~~~text
Model #1 -> A
Model #2 -> B
Model #3 -> C
Model #4 -> final
~~~

`M=4` dù không có yêu cầu nghiệp vụ mới. Khi thấy số lần gọi tăng, cần điều tra **model không batch tool độc lập** hay **nghiệp vụ thực sự phát sinh dependency mới**.

### Không ép mọi thứ vào một tool khổng lồ

Một tool composite như `answer_everything` có thể giảm số vòng model nhưng làm schema lớn, che mờ quyền, khó test và khó retry từng phần. Hợp nhất ở application service khi đó là **một workflow nghiệp vụ có hợp đồng rõ**, không phải endpoint cho phép mô hình gọi API hoặc SQL tùy ý.

## 7. Xác lập ba kịch bản ước lượng trước khi triển khai

Không nên báo một số “chắc chắn sẽ có 3 model calls” cho một tác vụ model-driven.

| Kịch bản | Giả định | Ý nghĩa |
|---|---|---|
| **Best case** | Model batch tất cả tool độc lập, không lỗi, không tìm lại tool | Gần `D+1` |
| **Typical case** | Dựa trên dữ liệu thực tế: một số tool được tách batch, có tỷ lệ retry hợp lý | Dùng cho capacity/cost forecast |
| **Stress case** | Tool lỗi, model chọn sai, truy vấn lại, catalog lớn hoặc provider chậm | Dùng cho guardrail và cảnh báo |

Cho tác vụ có năm tool với hai tầng phụ thuộc:

~~~text
Best case:     M = 3 (2 batch + final)
Typical case:  M = 4 hoặc 5 (mô hình tách thêm batch)
Stress case:   M có thể cao hơn do lỗi, tìm lại, retry
~~~

“Stress case” chỉ trở thành upper bound hữu hạn nếu application layer đặt **giới hạn model iterations**, retry và timeout. Giới hạn số tool calls **không hoàn toàn tương đương** giới hạn model calls: những model request cho validation, routing hoặc retry không có tool vẫn tiêu tiền.

## 8. Vì sao catalog nhiều tool ảnh hưởng số lần gọi?

Tool catalog lớn làm tăng số ứng viên mô hình phải lựa chọn:

- Các tool có tên hoặc mô tả gần nhau khiến model chọn sai, sau đó cần tool khác.
- Schema quá dài chiếm input tokens ở mỗi model iteration.
- Một tool tổng quát có nhiều arguments khiến model thử nhiều bộ arguments.
- Nhiều tool cùng tên từ local/MCP có thể gây xung đột.
- Có thể cần bước discovery/tool search trước khi chọn callback cụ thể.

Việc tinh giản catalog có thể giảm cả **chi phí trên mỗi model call** và **số lần gọi do lựa chọn sai**, nhưng không phải công cụ ít nhất luôn tốt nhất: bỏ mất tool cần thiết sẽ khiến task thất bại hoặc lặp tìm kiếm.

Trong Spring AI 2.1.x, `ToolSearchToolCallingAdvisor` có thể dùng progressive disclosure: mô hình gọi tool tìm kiếm trước rồi mới thấy các definitions liên quan. Cách này giảm context bloat nhưng **có thể thêm một model/tool-search round**.

Ví dụ dự báo:

~~~text
Không dùng Tool Search:
  Model #1 chọn lookupInventory
  Model #2 trả lời
  -> M = 2

Dùng Tool Search:
  Model #1 gọi toolSearchTool
  Model #2 chọn lookupInventory
  Model #3 trả lời
  -> M = 3
~~~

Một request khác với 80 tool definitions có thể giảm đáng kể token input khi dùng Tool Search dù thêm một round. Phải đo cả **total input tokens, task completion và latency**, không chỉ `M`.

## 9. Return-direct có thể bỏ vòng tổng hợp cuối

Mặc định tool result được gửi trở lại model để model tạo câu trả lời. Với tool có output chính là kết quả người dùng cần và đã được kiểm tra an toàn, có thể dùng `returnDirect = true`:

~~~java
@Tool(
    name = "get_public_exchange_rate",
    description = "Trả kết quả tỷ giá đã chuẩn hóa.",
    returnDirect = true
)
public ExchangeRateResult rate(
        @ToolParam(description = "Mã tiền tệ gốc")
        String base,
        @ToolParam(description = "Mã tiền tệ đích")
        String target) {

    return exchangeRateService.lookup(base, target);
}
~~~

Kịch bản một tool:

~~~text
Mặc định:
  Model #1 -> yêu cầu tool
  Tool -> kết quả
  Model #2 -> diễn giải
  M = 2

returnDirect:
  Model #1 -> yêu cầu tool
  Tool -> kết quả trả thẳng caller
  M = 1
~~~

Đó là một cách **giảm model round-trip**, nhưng kết quả trực tiếp phải có định dạng mà caller hiểu, không chứa field nhạy cảm, đã qua validation và authorization. Không dùng `returnDirect` để bỏ qua bước kiểm tra nghiệp vụ hoặc xác nhận thao tác rủi ro.

**Lưu ý nhiều tool trong một batch:** Spring AI chỉ xử lý return-direct theo hướng kết thúc nếu **tất cả** những tool được gọi trong cùng iteration đều có metadata return-direct. Nếu batch còn một tool cần mô hình tổng hợp, vòng tiếp tục.

## 10. Khi lỗi tool khiến model gọi thêm vòng

Tool calling không chỉ gồm đường thành công. Những nhánh phát sinh:

| Sự kiện | Có thể ảnh hưởng M thế nào? | Cần kiểm soát |
|---|---|---|
| Tool trả kết quả hợp lệ | Mô hình có thể tổng hợp ở vòng kế | Không bắt buộc thêm vòng khác |
| Arguments model sai schema | Model có thể sửa arguments rồi thử lại | Validation, số lần thử |
| Tool timeout | Retry ở gateway hoặc model đổi tool | Timeout, backoff, idempotency |
| Tool trả lỗi nghiệp vụ | Model có thể giải thích ngay hoặc gọi công cụ khác | Phân loại lỗi, giới hạn |
| Tool không có quyền | Không được thực thi trái quyền; có thể trả từ chối | Authorization theo actor/tài nguyên |
| Bị rate limit | Có thể chờ hoặc thay phương án | Retry budget, provider quota |
| Tool name không tồn tại | Model có thể chọn lại nếu app cho phép | Allowlist và catalog quality |
| Tool result quá dài | Tăng prompt của vòng tiếp theo | Cắt dữ liệu có cấu trúc, pagination |

Ví dụ một tool bắt buộc nhưng model thử arguments sai:

~~~text
Model #1 -> lookupInventory({"sku":"??"})
Tool result -> INVALID_SKU
Model #2 -> lookupInventory({"sku":"SKU-100"})
Tool result -> 18
Model #3 -> trả lời
~~~

Một tool nghiệp vụ vẫn có thể bị gọi hai lần, còn `M=3` thay vì `M=2`.

Không nên tự động retry mọi lỗi. Với tool có side effect như hủy đơn hoặc hoàn tiền, lặp thực thi có thể gây giao dịch trùng. Hãy đặt kiểm tra quyền tại callback/application service, dùng idempotency khi cần và không gửi stack trace hoặc secrets trở lại model.

## 11. Phân biệt retry model với retry REST/SDK

Ví dụ:

~~~text
Model #1 -> gọi calculateShipping
  Tool calculateShipping:
    HTTP attempt 1 -> timeout
    HTTP attempt 2 -> 200
Model #2 -> trả lời
~~~

Nếu cả hai HTTP attempts đều diễn ra **bên trong một tool execution** và tool cuối cùng trả dữ liệu thành công:

~~~text
Model calls = 2
Tool calls = 1
HTTP attempts = 2
~~~

Một retry HTTP không tự tạo model call. Ngược lại, nếu lỗi được đóng gói thành tool response rồi model yêu cầu gọi lại:

~~~text
Model #1 -> calculateShipping
Tool -> TIMEOUT
Model #2 -> calculateShipping
Tool -> OK
Model #3 -> trả lời
~~~

Khi đó `M=3` và `T=2`.

Kế hoạch capacity cần đếm đúng cấp độ. Tại dashboard, dùng tách `model_call_attempt`, `tool_call` và `remote_attempt` để không quy nhầm chi phí vendor hoặc latency sang model.

## 12. Confirmation và giới hạn có thể dừng vòng giữa chừng

Các tool làm thay đổi trạng thái như `cancel_order` hoặc `refund_payment` có thể yêu cầu xác nhận người dùng. Trong Spring AI 2.1.x, `ToolCallingManager` có cơ chế confirmation trước khi thực thi.

Một luồng ví dụ:

~~~text
Model #1 -> đề xuất cancel_order
ToolCallingManager -> yêu cầu xác nhận, chưa thực thi
Ứng dụng -> hiển thị yêu cầu phê duyệt
Người dùng -> cho phép/từ chối
Ứng dụng -> hoàn tất quá trình theo policy
Model có thể được gọi tiếp ở một exchange sau đó
~~~

Điểm quan trọng: **thời gian chờ người dùng không phải latency của ChatModel**, và việc resume có thể trở thành một ChatClient exchange mới. Hãy thống nhất `turnId`/workflow attempt để đo tổng quy trình mà không nhầm mỗi resume là một model call của lượt trước.

Nếu tool vượt hạn mức, vòng có thể dừng sớm với lỗi; số model calls quan sát được lúc đó nhỏ hơn forecast của đường thành công, nhưng **task đã thất bại**. Vì vậy, mục tiêu tối ưu không phải chỉ giảm số model calls bằng mọi cách.

## 13. Streaming: nhiều chunk vẫn chỉ là một model iteration

Hai cách gọi:

~~~java
String answer = chatClient.prompt()
    .user(question)
    .tools(orderTools)
    .call()
    .content();

Flux<String> chunks = chatClient.prompt()
    .user(question)
    .tools(orderTools)
    .stream()
    .content();
~~~

Ở chế độ streaming:

- Một model iteration có thể phát nhiều `ChatClientResponse` chunks.
- Tool-call arguments có thể được phát từng fragment, chưa phải JSON hoàn chỉnh.
- `ToolCallingAdvisor` tổng hợp đủ thông tin cần thiết trước khi chạy tool.
- Sau tool results, advisor có thể mở một model iteration mới để stream nội dung tiếp.
- Số chunk hoặc số subscription không phải số vòng tool, trừ khi resubscription thực sự tạo request mới.

Không đếm model calls bằng `doOnNext(chunk -> counter.increment())`. Cách đó đo **chunks**, không đo calls.

Cũng không gọi `collectList().block()` trong advisor chỉ để dễ đếm: nó làm mất streaming, thêm memory usage và có thể block event-loop.

Khi client hủy stream, model call có thể đã bắt đầu và bị tính phí; tool có side effect có thể đã thực thi xong. Hãy ghi kết quả `cancelled`/`partial` với usage quality phù hợp, không mặc định chi phí bằng 0.

## 14. Ước lượng độ trễ từ các tầng phụ thuộc

Gọi:

- `L_model,i`: độ trễ model call thứ `i`.
- `L_toolBatch,j`: thời gian chờ hoàn tất batch tool thứ `j`.
- `L_overhead`: serialization, network, advisor, queue và xử lý nội bộ khác.

Nếu các model iterations và các batch tool lần lượt nối tiếp, ước lượng thô:

~~~text
L_total ≈ Σ L_model,i
        + Σ L_toolBatch,j
        + L_overhead
~~~

Với một batch gồm các tool độc lập:

~~~text
Nếu thực thi song song thật:
L_toolBatch ≈ max(L_tool_1, ..., L_tool_k) + overhead

Nếu thực thi tuần tự:
L_toolBatch ≈ Σ L_tool_i + overhead
~~~

**Đừng giả định runtime luôn song song.** Độ trễ phụ thuộc executor, thread pool, giới hạn provider, dependency và transaction. Cần đo trực tiếp `ToolCallingManager`/tool callbacks.

### Ví dụ giả định

Workflow A + B trước C, với:

~~~text
Model #1: 0,7 giây
Tool A:   0,3 giây
Tool B:   0,9 giây
Model #2: 0,8 giây
Tool C:   0,4 giây
Model #3: 0,9 giây
~~~

Nếu A và B thực sự chạy song song:

~~~text
L ≈ (0,7 + 0,8 + 0,9)
  + max(0,3; 0,9)
  + 0,4
  = 3,7 giây + overhead
~~~

Nếu A và B chạy tuần tự trong cùng batch:

~~~text
L ≈ 2,4 + (0,3 + 0,9) + 0,4
  = 4,0 giây + overhead
~~~

Số model calls ở cả hai trường hợp vẫn là **3**. Vì vậy, tối ưu song song có thể cải thiện latency nhưng **không nhất thiết giảm số model calls**.

## 15. Ước lượng token: prompt tăng sau mỗi tool result

Số model calls chỉ là một thành phần chi phí. Ở vòng thứ hai hoặc thứ ba, prompt thường mang thêm:

- Lịch sử assistant đã yêu cầu tool.
- `ToolResponseMessage` với dữ liệu từ tool.
- Các lượt chat trước nếu workflow/memory giữ lại.
- Tool definitions có thể được gửi lại.
- System instructions và context chính sách.

Một mô hình token đơn giản:

~~~text
InputTokens_i ≈ BasePromptTokens
              + ToolDefinitionTokens_i
              + HistoryTokens_i
              + ToolResultTokensSoFar_i
              + ProviderOverhead_i

OutputTokens_i ≈ ToolCallJsonTokens_i
               hoặc FinalAnswerTokens_i
~~~

Dấu `≈` nhấn mạnh đây là ước lượng. Tokenizer, nhà cung cấp, định dạng tool call và prompt caching có thể ảnh hưởng số thực tế.

**Không suy ra tổng token bằng `M × tokens của model call đầu`.** Các vòng sau thường có lịch sử dài hơn.

### Ví dụ input tăng dần

| Model iteration | Input tokens giả định | Output tokens giả định | Ghi chú |
|---|---:|---:|---|
| #1 | 1.600 | 180 | Chọn hai tool A, B |
| #2 | 2.400 | 120 | Đọc kết quả A, B rồi chọn tool C |
| #3 | 3.000 | 480 | Đọc kết quả C và trả lời |
| **Tổng** | **7.000** | **780** | **7.780 tokens** |

Nếu mỗi tool trả một document hàng nghìn token, input ở các vòng sau có thể còn tăng mạnh. Tối ưu **kích thước tool result**, danh mục definitions, history compaction và số lần retry có thể tạo lợi ích chi phí lớn tương đương giảm một model call.

`ToolContext` chứa actor/tenant/tokens nội bộ không phải JSON arguments gửi model; dữ liệu đó phải giữ ở ứng dụng, không đưa vào prompt chỉ để tiện điều phối.

## 16. Từ token sang tiền: tính trên từng model call

Chi phí mô hình phụ thuộc model, provider, giá input/output và các loại token đặc biệt như cached input hoặc reasoning. Công thức text đơn giản, bỏ qua cache/modality:

~~~text
ModelCost ≈ Σ [
    InputTokens_i × InputPrice_i
  + OutputTokens_i × OutputPrice_i
]
~~~

Đơn giá phải cùng đơn vị với token. Nếu bảng giá theo một triệu token, dùng:

~~~text
ModelCostUsd ≈ Σ [
    InputTokens_i × InputUsdPerMillion_i / 1.000.000
  + OutputTokens_i × OutputUsdPerMillion_i / 1.000.000
]
~~~

Với bảng token ví dụ và **giá giả định** input $2/1M, output $8/1M:

~~~text
Input cost  = 7.000 × $2 / 1.000.000 = $0,014
Output cost =   780 × $8 / 1.000.000 = $0,00624

Model cost = $0,02024
~~~

Giả sử ba tool có phí ngoài:

~~~text
Tool A: $0,002
Tool B: $0,001
Tool C: $0,003

External cost = $0,006
Total direct estimated cost = $0,02624
~~~

**Tất cả đơn giá trên là số minh họa**, không phải giá của nhà cung cấp hiện hành. Khi thực tế có cached-read, cache-write, audio hoặc reasoning-specific pricing, phải dùng price adapter đúng provider/model/phiên bản bảng giá và tránh cộng trùng những token đã nằm trong tổng.

Tool có thể gọi REST/SDK/DB mà không tiêu thụ token, nhưng vẫn tốn chi phí API/hạ tầng. Nếu tool gọi thêm một `ChatModel` riêng, usage của model phụ phải được ghi riêng và gắn về cùng business task.

## 17. Cumulative Usage trong ChatClient và lỗi đếm trùng

Spring AI 2.x có `ChatResponseMetadata.getUsage()`. Khi response cuối đi qua một vòng tool calling, usage nhận từ `ChatClient` là **cộng dồn các model calls trong exchange**, không chỉ của lần cuối.

~~~java
ChatResponse response = chatClient.prompt()
    .user(question)
    .tools(orderTools)
    .call()
    .chatResponse();

Usage accumulated = response.getMetadata().getUsage();

if (accumulated != null) {
    Integer inputTokens = accumulated.getPromptTokens();
    Integer outputTokens = accumulated.getCompletionTokens();
    Integer totalTokens = accumulated.getTotalTokens();
}
~~~

Với ba lần gọi ở ví dụ trên, tổng có thể là `7.780` token.

Nếu đồng thời thu `gen_ai.client.token.usage` từ mỗi model call, **không cộng thêm 7.780** vào các metric per-call. Sẽ đếm cùng usage hai lần. Hãy dùng:

- `ChatClient` cumulative usage để báo cáo tổng exchange.
- Per-`ChatModel` usage/metrics để phân tích từng model call.
- Ledger theo `turnId` khi một user task đi qua nhiều exchanges hoặc nhiều model khác nhau.

Nếu provider không báo `Usage` ở một số request hoặc streaming bị hủy, ghi `UNKNOWN`/`PARTIAL` thay vì xem là 0. Nếu cần đối soát tiền, lưu provider request ID và rate card version.

## 18. Cấu hình giới hạn tool không phải giới hạn model rounds

Spring AI 2.x cho phép giới hạn số lần tool được gọi trong mỗi turn. Ví dụ cấu hình theo yêu cầu sản phẩm:

~~~properties
spring.ai.tools.limits.max-total-tool-calls=8
spring.ai.tools.limits.max-calls-per-tool-default=3
spring.ai.tools.limits.on-limit-exceeded=THROW
~~~

Các giá trị là **policy minh họa**, không phải default của framework.

Ý nghĩa:

- Tối đa 8 lần gọi tool trong một turn.
- Một tool cụ thể tối đa 3 lần, trừ các override.
- Khi vượt giới hạn, dùng hành vi `THROW` theo cơ chế advisor/manager.

Theo tài liệu Spring AI, `DefaultToolCallingManager` có giới hạn mặc định số tool calls, nhưng chúng **đếm lời gọi tool**, không trực tiếp đảm bảo chỉ có tối đa 4 model iterations. Đặc biệt, tool-search, structured-output retry, external model orchestration hoặc workflow khác có thể dùng thêm calls.

Ứng dụng cần đặt giới hạn tách biệt:

~~~text
PerTaskBudget:
  maxModelCalls: 6
  maxToolCalls: 8
  maxCallsPerTool: 3
  maxElapsedTime: 25 seconds
  maxEstimatedUsd: $0.05
  maxToolResultBytes: 16 KB
~~~

Các con số đều là ví dụ. Với công cụ tài chính hoặc ghi dữ liệu, phải bổ sung authorization, confirmation, idempotency và transaction policy, không dùng ngân sách như một lớp cấp quyền.

## 19. Quan sát mỗi model iteration trong advisor chain

`ToolCallingAdvisor` mặc định ở order `Ordered.HIGHEST_PRECEDENCE + 300`. Một advisor thường có order **lớn hơn** (ví dụ +400) được đặt **bên trong tool loop** nên chạy mỗi model iteration. Advisor có order nhỏ hơn có thể chỉ thấy toàn exchange.

Ví dụ một observer chỉ đếm iteration **đã bắt đầu**, dùng cho `call()` và `stream()`:

~~~java
public final class ModelIterationCounterAdvisor
        implements CallAdvisor, StreamAdvisor {

    private final MeterRegistry meterRegistry;

    public ModelIterationCounterAdvisor(
            MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public String getName() {
        return "model-iteration-counter";
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 400;
    }

    @Override
    public ChatClientResponse adviseCall(
            ChatClientRequest request,
            CallAdvisorChain chain) {

        meterRegistry.counter(
            "assistant.model.iteration.started",
            "mode", "call"
        ).increment();

        return chain.nextCall(request);
    }

    @Override
    public Flux<ChatClientResponse> adviseStream(
            ChatClientRequest request,
            StreamAdvisorChain chain) {

        return Flux.defer(() -> {
            meterRegistry.counter(
                "assistant.model.iteration.started",
                "mode", "stream"
            ).increment();

            return chain.nextStream(request);
        });
    }
}
~~~

Đăng ký observer thường; `DefaultChatClient` vẫn dùng `ToolCallingAdvisor` mặc định:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
    .defaultAdvisors(
        new ModelIterationCounterAdvisor(meterRegistry)
    )
    .build();
~~~

Giải thích:

- Observer **không** implement `ToolAdvisor` và không thay thế vòng thực thi.
- Với `call()`, mỗi lần advisor được gọi ghi một event rồi tiếp tục chain.
- Với `stream()`, `Flux.defer` tính theo subscription chứ không tính ngay khi tạo publisher.
- Counter đo số iteration **đi vào phía trong chain**, chưa chắc đồng nhất 100% với số request provider đã billed nếu lỗi xảy ra trước transport; đối soát bằng model operation observations/provider IDs.
- Không gắn `userId`, `turnId`, raw arguments hoặc prompt vào metric tags. Muốn ghép theo task, lưu correlation trong trace/event store có kiểm soát quyền.

Khi dùng `ToolSearchToolCallingAdvisor` hoặc tool advisor custom, cần kiểm tra thứ tự thực tế để observer vẫn nằm trong vòng. Nếu có advisor retry/structured-output khác, phải biết iteration nào đang được đếm; không giả định mọi lần observer chạy là một model call duy nhất nếu chain có logic retry phía dưới.

## 20. Phân biệt model-call metric và tool-call metric

Có thể xây dashboard theo ba tầng:

| Chỉ số | Nguồn | Công dụng |
|---|---|---|
| Business task attempts | Application boundary | Mẫu số của thành công |
| Model calls per task | Model invocation ledger / advisor đúng vị trí | Phát hiện vòng lặp dài |
| ChatClient exchanges per task | Controller/workflow | Xem một task có bao nhiêu exchange |
| Tool calls per task | `ToolCallingManager`/tool callback | Tìm công cụ bị gọi lặp |
| Tool batches per task | Ghép các tool calls theo assistant response | Đo khả năng batch |
| Remote attempts/tool call | HTTP/SDK gateway | Phát hiện retry/fan-out |
| Input/output tokens | `Usage`/Micrometer | Tính token và cost |
| Tool-result bytes | Result converter/response mapper | Phát hiện context phình |
| End-to-end latency | Business timer | Trải nghiệm người dùng |
| Task success rate | Business outcome | Tránh tối ưu số calls nhưng làm hỏng task |

Số model calls cần được ghép theo `turnId` để phân tích tính phân phối (p50, p90, p95), không chỉ lấy số trung bình.

Một request trả lời đúng với bốn model calls có thể tốt hơn một request trả lời sai với một model call. **Ước lượng M là đầu vào quyết định hiệu năng, không phải KPI chất lượng độc lập.**

## 21. Dùng dữ liệu thật để hiệu chỉnh ước lượng

Quy trình khuyến nghị:

1. **Chọn workflow** như `order_status_lookup`, `shipping_quote`, `support_ticket_create`.
2. **Vẽ dependency graph** ở mức logic và tìm số tầng tool `D`.
3. **Tạo best case**: `D+1` trong điều kiện cần phản hồi cuối và không return-direct.
4. **Tạo synthetic cases**: không có tool, một batch nhiều tool, chuỗi phụ thuộc, tool lỗi, tool result dài.
5. **Chạy cùng tập câu hỏi trên staging** với model/version/prompt/tool catalog cố định; thu model calls, token, latency, outcome.
6. **Tính phân phối M thực tế** theo workflow, số tool calls và các lớp phụ thuộc.
7. **Tách nguyên nhân tăng M**: dependency thật, tool selection sai, retry, missing data hoặc confirmation.
8. **Cập nhật forecast** cho p50/p95, chi phí và capacity; đo lại sau khi đổi model/tool schema.
9. **Thiết lập cảnh báo** cho vòng dài bất thường, chi phí/task và task failures; không page chỉ vì một request khó.

### Dữ liệu ví dụ giả định

| Workflow | Best-case M | M trung bình đo giả định | p95 M giả định |
|---|---:|---:|---:|
| Một tool đọc đơn | 2 | 2,2 | 3 |
| Tồn kho + phí giao (độc lập) | 2 | 2,7 | 4 |
| Tồn kho/phí giao -> quyết định fulfillment | 3 | 3,6 | 5 |
| Tra cứu + tool search | 3 | 3,4 | 5 |

Các số trung bình/p95 chỉ minh họa cách tổ chức báo cáo, **không phải benchmark về Spring AI hoặc một model cụ thể**.

Từ dữ liệu phân phối, số calls kỳ vọng:

~~~text
E[M] = Σ m × P(M = m)

Tổng model calls dự kiến trong ngày
  ≈ Số business tasks dự kiến × E[M]
~~~

Nếu có 10.000 task/ngày và `E[M]=3,2`:

~~~text
Model calls/ngày ≈ 10.000 × 3,2 = 32.000
~~~

Cần tách theo workflow và model/provider vì các task có kết cấu và giá khác nhau; số task tăng không đều giữa các nhóm.

## 22. Capacity planning và ngân sách request đồng thời

Tổng model calls/ngày giúp tính volume, nhưng chưa đủ để tính concurrency. Phải đo **arrival rate** và độ trễ từng model request.

Ước lượng mức gọi model/giây:

~~~text
ModelCallsPerSecond ≈ BusinessTasksPerSecond × E[M]
~~~

Ví dụ vào giờ cao điểm 5 tasks/s và `E[M]=3,2`:

~~~text
Expected model calls/s ≈ 16
~~~

Nếu độ trễ model call trung bình 0,8 giây, theo Little's Law, concurrency trung bình ở lớp model có thể gần:

~~~text
Concurrent model calls ≈ 16 × 0,8 = 12,8
~~~

Đây là ước lượng cho hệ thống ổn định với cùng arrival rate và average service time. Peak burst, provider rate limits, queueing, retry, token-per-minute và các loại model khác nhau có thể khiến nhu cầu thực tế cao hơn nhiều.

Đừng quên:

- Một model request có input/output token khác nhau; TPM không suy từ RPS đơn thuần.
- Tool execution có concurrency và quota riêng.
- Khi provider 429, retry có thể làm tăng hàng đợi.
- Nếu task có budget cá nhân/tenant, reservation phải atomic khi nhiều requests cùng chạy.
- Những tool có side effect cần giới hạn ghi dữ liệu và cơ chế idempotency riêng.

## 23. Kiểm thử các giả thuyết về số lượt

Unit/integration test có thể dùng fake `ChatModel` với danh sách response được lập sẵn. Đừng dùng một model thật làm oracle duy nhất cho số lượt vì kết quả có xác suất.

Ma trận:

| Scenario | Model calls kỳ vọng | Nội dung kiểm tra |
|---|---:|---|
| Không tool | 1 | Advisor không tự gọi thêm |
| Một tool, result quay lại model | 2 | Một callback, một final response |
| Hai tool trong cùng assistant response | 2 | Hai callbacks, cùng một batch |
| Hai tool có dependency | 3 | Tool B chỉ được gọi sau kết quả A |
| Ba tool nối tiếp | 4 | Giữ lịch sử và tool call IDs |
| Một tool return-direct | 1 | Không có model tổng hợp cuối |
| Batch có tool không return-direct | 2 hoặc hơn | Không bỏ vòng cuối khi còn tool cần tổng hợp |
| Tool báo lỗi rồi model sửa arguments | 3 | Không lặp vô hạn |
| HTTP retry bên trong một tool | 2 | Remote attempts tăng nhưng M không tăng |
| Tool Search trước tool nghiệp vụ | 3 hoặc hơn | Discovery tốn model iteration |
| Streaming nhiều chunks | Số iteration thiết kế | Chunks không bị đếm thành model calls |
| Confirmation pause | Theo các exchange thực tế | Không thực thi trước khi được phép |
| Lỗi/giới hạn kết thúc sớm | Có thể nhỏ hơn forecast | Task failure được báo đúng |

### Ví dụ kiểm thử counter advisor (khung minh họa)

~~~java
@Test
void oneAdvisorCallCountsOneIteration() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    ModelIterationCounterAdvisor advisor =
        new ModelIterationCounterAdvisor(registry);

    ChatClientRequest request = mock(ChatClientRequest.class);
    CallAdvisorChain chain = mock(CallAdvisorChain.class);
    ChatClientResponse response = mock(ChatClientResponse.class);

    when(chain.nextCall(request)).thenReturn(response);

    ChatClientResponse actual = advisor.adviseCall(
        request, chain
    );

    assertThat(actual).isSameAs(response);
    verify(chain).nextCall(request);

    double count = registry.get("assistant.model.iteration.started")
        .tag("mode", "call")
        .counter()
        .count();

    assertThat(count).isEqualTo(1.0);
}
~~~

Test này xác minh **observer ghi một lần khi được gọi một lần**, chưa chứng minh `ToolCallingAdvisor` đã gọi nó N lần cho một luồng tool. Cần integration test ghép advisor + fake model responses, sau đó assert model invocation count và counter khớp. Với streaming, dùng `StepVerifier` kiểm tra subscription, complete/error/cancel và resubscription.

### Kiểm tra công thức bằng ví dụ thuần Java

~~~java
record PlanEstimate(
    int dependencyLayers,
    int toolCalls,
    boolean requiresFinalModelAnswer) {}

static int idealModelCalls(PlanEstimate plan) {
    if (plan.toolCalls() == 0) {
        return 1;
    }
    // Giả định mỗi tầng đã được gọi trong một model response.
    return plan.dependencyLayers()
        + (plan.requiresFinalModelAnswer() ? 1 : 0);
}
~~~

Khi `requiresFinalModelAnswer=false`, kết quả dùng cho nhánh `returnDirect` lý tưởng, không áp dụng cho mọi lỗi/dừng giữa vòng. `dependencyLayers` phải do ứng dụng phân tích đúng; chương trình không thể suy ra nó chỉ bằng cách đếm tổng tool callbacks đăng ký.

## 24. Khi số lượt tăng, nên tối ưu điều gì trước?

Một quy trình chẩn đoán:

**Trường hợp 1: M tăng vì tool quá giống nhau.** Xem lại tên, description, schema và tool set được công bố cho request. Có thể dùng shortlist theo workflow thay vì gửi toàn catalog.

**Trường hợp 2: M tăng vì mỗi tool chỉ mang một phần dữ liệu cần thiết.** Kiểm tra có thể xây tool nghiệp vụ tổng hợp hợp lệ hay không, hoặc để model batch các tool độc lập. Không gộp các hành động khác quyền chỉ để tiết kiệm round-trip.

**Trường hợp 3: M đúng như dependency graph nhưng latency cao.** Kiểm tra tool batch có thể thực thi song song và backend nào là critical path; tối ưu latency không nhất thiết giảm số model calls.

**Trường hợp 4: Input token tăng mạnh qua mỗi vòng.** Giới hạn tool result, phân trang, trả DTO gọn, quản lý chat history và catalog definitions. Đừng chỉ nhìn số lần gọi.

**Trường hợp 5: Tool lỗi lặp.** Điều tra timeout, rate-limit, JSON schema, dữ liệu đầu vào. Đặt chính sách retry rõ ràng và ngân sách vòng.

**Trường hợp 6: M thấp nhưng task thất bại.** Không coi là tối ưu. Kiểm tra model không gọi tool cần thiết, không có quyền hoặc bị giới hạn quá chặt.

### Một bảng quyết định ngắn

| Quan sát | Khả năng | Can thiệp |
|---|---|---|
| Tool calls nhiều, model calls ít | Model batch tốt | Kiểm tra runtime concurrency và quota |
| Tool calls ít, model calls nhiều | Retry/validation/discovery/model phụ | Xem trace từng iteration |
| M tăng sau thay đổi schema | Model lựa chọn sai hoặc arguments lỗi | Regression test tool selection |
| M không đổi, token tăng | History/tool result/schema phình | Tối ưu payload/context |
| M không đổi, latency tăng | Backend hoặc provider chậm | Critical-path tracing |
| M giảm, task success giảm | Cắt tool/round quá mạnh | Nới policy có kiểm soát |
| Cost tăng nhưng M giữ nguyên | Giá/model mix, cache, output hoặc external API | Ledger theo provider/tool |

## 25. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Thay bằng |
|---|---|---|
| `M = số tool + 1` trong mọi trường hợp | Multi-tool batch gộp nhiều tool vào một lần model response | `M = B + 1` ở vòng bình thường |
| Đếm mỗi streaming chunk thành model call | Chunk chỉ là phần dữ liệu từ một invocation | Đếm ở model boundary/iteration |
| Coi một `ChatClient.call()` là một model call | Tool loop có thể lặp nhiều lần | Instrument bên trong `ToolCallingAdvisor` |
| Cho rằng tool cùng batch luôn song song | Runtime có thể chạy tuần tự | Đo critical path thực tế |
| Cho rằng tool retry luôn tăng M | Retry REST nội bộ có thể không gọi lại model | Tách model/tool/remote attempts |
| Giảm M bằng tool composite nhận URL tùy ý | Mở rộng quyền và khó audit | Tool nghiệp vụ với validation/authz |
| Bật `returnDirect` cho dữ liệu chưa chuẩn hóa | Kết quả rò PII/không đúng format | Chỉ direct khi an toàn và phù hợp |
| Dùng tool-call limit như hard cap model calls | Có model retries/discovery ngoài tool count | Giới hạn riêng iterations/deadline |
| Cộng cumulative usage với per-call usage | Đếm trùng token | Ledger có cấp độ và nguồn rõ ràng |
| Bỏ qua cached tokens/giá model | M ít không có nghĩa chi phí thấp | Pricing theo usage category |
| Tối ưu chỉ theo số model calls | Có thể làm giảm task success | Theo dõi outcome, latency và cost cùng lúc |
| Gắn `turnId`/userId vào Prometheus tags | Cardinality lớn, rò dữ liệu | Correlation trong traces/ledger có quyền |
| Tự động retry tool ghi dữ liệu | Gây side effect trùng | Idempotency, confirmation và retry policy |
| Tính p95 bằng cách cộng p95 từng tầng | Percentile không có tính chất cộng | Đo end-to-end latency thật |

## 26. Checklist trước khi đưa vào production

- [ ] Có định nghĩa rõ business turn, ChatClient exchange, model iteration, tool call và remote attempt.
- [ ] Đã vẽ dependency graph của workflow quan trọng; biết số tầng công cụ `D`.
- [ ] Dùng `M ≈ D + 1` chỉ trong giả định có final model answer, batching tốt và không có retry.
- [ ] Đã kiểm tra model/provider có thể yêu cầu nhiều tool calls trong một phản hồi.
- [ ] Không nhầm batch một phản hồi với thực thi song song backend.
- [ ] Có kịch bản best/typical/stress thay vì một số dự báo cứng.
- [ ] Đã tính thêm tool-search, validation, confirmation/resume, lỗi và nested model calls.
- [ ] Có timeout, max model iterations, max tool calls và ngân sách token/USD.
- [ ] Tool có side effect được bảo vệ bởi authz, confirmation và idempotency.
- [ ] Có instrumentation per-model-call ở đúng vị trí trong advisor chain.
- [ ] Không đếm streaming chunks như model calls.
- [ ] Không double count `ChatClient` cumulative usage với model usage events.
- [ ] Có thống kê M, T, batch count, token, latency và outcome theo workflow.
- [ ] Có dữ liệu benchmark staging theo model/version, prompt, catalog và policy thực tế.
- [ ] Có regression tests cho no-tool, batch, dependency, return-direct, retry, error và stream.
- [ ] Dashboard ưu tiên task success, không đặt mục tiêu chỉ “model calls thấp nhất”.
- [ ] Có cảnh báo vòng bất thường, chi phí/task tăng, token phình và task failures.

## Tài liệu tham khảo

- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): `ToolCallingAdvisor`, `ToolCallingManager`, nhiều tool calls trong một phản hồi, return-direct và giới hạn lượt tool.
- [Spring AI — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html): vòng đệ quy, hook cho call/stream, thứ tự advisor và quan sát theo iteration.
- [Spring AI — Chat Response Metadata](https://docs.spring.io/spring-ai/reference/api/usage-handling.html): `Usage` và cumulative token usage trong multi-step tool loop.
- [Spring AI — Advisors API](https://docs.spring.io/spring-ai/reference/api/advisors.html): `CallAdvisor`, `StreamAdvisor` và advisor ordering.
- [Spring AI — Tool Search Tool](https://docs.spring.io/spring-ai/reference/api/tools/tool-search-tool.html): progressive disclosure có thể giảm input tokens nhưng thêm discovery step.
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): model/tool observations, metrics và traces để đo chi phí/latency thật.
- [Micrometer — Documentation](https://docs.micrometer.io/): timers, counters và phân phối metric.

**Điểm cần nhớ:** không suy số lần gọi model từ tổng số công cụ. Hãy xác định **bao nhiêu batch tool phải quay lại model**, đặc biệt qua những tầng phụ thuộc dữ liệu: với vòng bình thường có câu trả lời cuối, `M = B + 1`. Dự báo best case từ dependency graph, rồi hiệu chỉnh bằng traces và số liệu thực. Cuối cùng, tối ưu đồng thời **tỷ lệ hoàn thành tác vụ, số lần gọi model, token, chi phí, độ trễ và an toàn thực thi**, thay vì chỉ giảm một chỉ số.


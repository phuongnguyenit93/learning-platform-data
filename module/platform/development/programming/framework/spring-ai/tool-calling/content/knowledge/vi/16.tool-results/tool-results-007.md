# Phối hợp returnDirect khi một phản hồi yêu cầu nhiều công cụ

Trong Spring AI, `returnDirect` quyết định kết quả tool có được trả thẳng về ứng dụng hay gửi lại mô hình để tiếp tục suy luận. Thuộc tính này được cấu hình riêng cho từng tool, nhưng khi một response của mô hình yêu cầu nhiều tool trong cùng một vòng, Spring AI áp dụng quy tắc ở cấp **cả nhóm**:

**Chỉ khi tất cả tool được gọi trong vòng đó đều có `returnDirect = true`, kết quả mới được trả trực tiếp cho caller. Nếu chỉ một tool có `returnDirect = false`, tất cả tool result của vòng đó được gửi lại mô hình.**

Điểm này ảnh hưởng trực tiếp đến cách thiết kế nhóm công cụ. Một tool được đánh dấu direct không có nghĩa kết quả của riêng nó sẽ bỏ qua mô hình trong mọi trường hợp; kết quả cuối cùng phụ thuộc vào các tool còn lại mà mô hình yêu cầu cùng lượt.

## 1. returnDirect có ý nghĩa gì?

Mặc định, kết quả của một tool được đưa vào lịch sử hội thoại dưới dạng `ToolResponseMessage`. Mô hình nhận kết quả đó trong request tiếp theo để có thể giải thích, tổng hợp hoặc quyết định gọi thêm tool.

Khi tool có `returnDirect = true`, ứng dụng muốn dùng kết quả tool làm kết quả cuối cùng. Spring AI bỏ qua lần gọi mô hình tiếp theo và trả kết quả tool về caller. Cách này hữu ích khi:

- Tool trả về một tài liệu hoặc dữ liệu đã hoàn chỉnh, không cần mô hình viết lại.
- Kết quả là câu trả lời cuối cùng đã được service nghiệp vụ xác định.
- Muốn tránh một lượt gọi mô hình chỉ để diễn đạt lại dữ liệu.
- Muốn kết thúc vòng suy luận ngay sau khi một hành động hoặc truy vấn hoàn tất.

`returnDirect` là metadata điều khiển cách định tuyến kết quả sau khi tool chạy. Nó không quyết định mô hình có chọn tool đó hay không, không thay thế phân quyền và không ngăn callback thực thi.

## 2. Quy tắc khi một response yêu cầu nhiều tool

Giả sử mô hình trả về một response chứa ba tool call:

- `getOrderSummary`: `returnDirect = true`.
- `getDeliveryStatus`: `returnDirect = false`.
- `getInvoice`: `returnDirect = true`.

Spring AI vẫn thực thi các tool call theo response. Sau đó, `ToolCallingManager` đánh giá kết quả tổng hợp. Vì `getDeliveryStatus` không bật direct, `ToolExecutionResult.returnDirect()` là `false`. Tất cả tool result trong vòng đó được gửi lại mô hình.

| Tool call trong cùng một vòng | `returnDirect()` của kết quả tổng hợp | Hành vi |
| --- | --- | --- |
| Tool A: `true`; Tool B: `true` | `true` | Trả các kết quả tool trực tiếp về caller, không gọi mô hình thêm |
| Tool A: `true`; Tool B: `false` | `false` | Gửi cả kết quả A và B lại mô hình |
| Tool A: `false`; Tool B: `true` | `false` | Gửi cả kết quả A và B lại mô hình |
| Tool A: `false`; Tool B: `false` | `false` | Gửi cả kết quả A và B lại mô hình |

Quy tắc có thể biểu diễn như phép AND:

~~~text
returnDirect của cả vòng = true
    khi và chỉ khi mọi tool call trong vòng đều có returnDirect = true
~~~

Không có cơ chế trả riêng tool A trực tiếp cho caller trong khi vẫn gửi tool B cho mô hình ở cùng vòng. Đây là quyết định ở cấp `ToolExecutionResult`, không phải luồng trả kết quả riêng cho từng callback.

~~~mermaid
flowchart TD
    A[Model trả về nhiều tool call] --> B[ToolCallingManager thực thi các callback]
    B --> C[Đọc returnDirect của từng tool]
    C --> D{Tất cả đều true?}
    D -->|Có| E[Trả kết quả tool trực tiếp]
    E --> F[Không gọi model thêm]
    D -->|Không| G[Đưa tất cả tool result vào history]
    G --> H[Gọi model với history mới]
    H --> I[Model tổng hợp hoặc yêu cầu vòng tiếp]
~~~

## 3. Khai báo returnDirect bằng @Tool

Với cách khai báo bằng annotation, đặt `returnDirect = true` trên phương thức cần trả kết quả trực tiếp:

~~~java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

@Component
public class OrderTools {

    private final OrderService orderService;
    private final DeliveryService deliveryService;

    public OrderTools(
            OrderService orderService,
            DeliveryService deliveryService) {
        this.orderService = orderService;
        this.deliveryService = deliveryService;
    }

    @Tool(
        name = "get_order_summary",
        description = "Lấy bản tóm tắt đơn hàng đã được hệ thống xác định. Dùng khi cần trả dữ liệu đơn hàng trực tiếp.",
        returnDirect = true
    )
    public OrderSummary getOrderSummary(
            @ToolParam(description = "Mã đơn hàng") String orderId) {
        return orderService.getSummary(orderId);
    }

    @Tool(
        name = "get_delivery_status",
        description = "Tra cứu trạng thái giao hàng để mô hình có thể kết hợp với thông tin khác."
    )
    public DeliveryStatus getDeliveryStatus(
            @ToolParam(description = "Mã đơn hàng") String orderId) {
        return deliveryService.getStatus(orderId);
    }
}
~~~

Trong ví dụ:

- `get_order_summary` có `returnDirect = true`.
- `get_delivery_status` không khai báo thuộc tính này nên mặc định là `false`.

Nếu mô hình chỉ gọi `get_order_summary`, kết quả được trả trực tiếp. Nếu mô hình yêu cầu cả hai phương thức trong cùng response, kết quả tổng hợp có `returnDirect = false`; cả hai kết quả được gửi lại mô hình để mô hình có thể tổng hợp thông tin đơn hàng và giao hàng.

`OrderService`, `DeliveryService`, `OrderSummary` và `DeliveryStatus` là các thành phần nghiệp vụ do ứng dụng định nghĩa.

## 4. Khai báo bằng ToolMetadata

Khi tạo `MethodToolCallback` hoặc `FunctionToolCallback` theo cách lập trình, cấu hình `returnDirect` qua `ToolMetadata`:

~~~java
import org.springframework.ai.tool.metadata.ToolMetadata;

ToolMetadata directMetadata = ToolMetadata.builder()
    .returnDirect(true)
    .build();
~~~

Truyền metadata vào builder của callback:

~~~java
MethodToolCallback callback = MethodToolCallback.builder()
    .toolDefinition(toolDefinition)
    .toolMetadata(directMetadata)
    .toolMethod(method)
    .toolObject(toolObject)
    .build();
~~~

Với callback dựa trên function, dùng metadata tương tự trong `FunctionToolCallback.Builder`. Cách này hữu ích khi tool được đăng ký động hoặc metadata thay đổi theo cấu hình ứng dụng.

Nếu không đặt `returnDirect`, giá trị mặc định là `false`: kết quả được gửi lại mô hình.

## 5. Phân tích tình huống hỗn hợp

Giả sử một assistant bán hàng cung cấp ba tool:

| Tool | returnDirect | Vai trò |
| --- | --- | --- |
| `getOrderSummary` | `true` | Trả bản tóm tắt đơn hàng đã chuẩn hóa |
| `getDeliveryStatus` | `false` | Cung cấp trạng thái giao hàng để mô hình diễn giải |
| `getRefundPolicy` | `false` | Cung cấp chính sách để mô hình giải thích điều kiện |

### Tình huống A: chỉ gọi tool direct

Mô hình chỉ yêu cầu `getOrderSummary`.

- Callback thực thi.
- `ToolExecutionResult.returnDirect()` là `true`.
- `ToolCallingAdvisor` dừng vòng lặp.
- Caller nhận kết quả của `getOrderSummary`; mô hình không nhận lại tool result và không tạo thêm câu trả lời.

Đây là lựa chọn phù hợp nếu `OrderSummary` đã là response DTO mà giao diện có thể hiển thị.

### Tình huống B: gọi direct cùng tool thông thường

Mô hình yêu cầu `getOrderSummary` và `getDeliveryStatus` trong cùng response.

- Cả hai callback đều được thực thi.
- Một tool có `returnDirect = false`, nên `ToolExecutionResult.returnDirect()` là `false`.
- Cả hai tool result được thêm vào conversation history.
- Mô hình nhận lại cả kết quả đơn hàng và trạng thái giao hàng để tạo câu trả lời tiếp theo.

`getOrderSummary` vẫn chạy bình thường. Thuộc tính direct của nó không có hiệu lực riêng trong batch hỗn hợp.

### Tình huống C: tất cả tool đều direct

Mô hình yêu cầu `getOrderSummary` và một tool khác cũng có `returnDirect = true`, ví dụ `getInvoiceDocument`.

- Cả hai callback được thực thi.
- Tất cả tool trong vòng đều direct.
- `ToolExecutionResult.returnDirect()` là `true`.
- Vòng gọi mô hình kết thúc và kết quả tool được trả cho caller.

Caller chịu trách nhiệm kết hợp hoặc hiển thị hai kết quả. Không có lượt mô hình tiếp theo để tạo một đoạn văn tổng hợp.

## 6. ToolCallingAdvisor xử lý kết quả tổng hợp

Với `ChatClient`, `ToolCallingAdvisor` điều phối vòng tool calling:

1. Gửi prompt cùng các tool definition đến mô hình.
2. Nhận response có một hoặc nhiều tool call.
3. Gọi `ToolCallingManager.executeToolCalls(...)`.
4. Kiểm tra `ToolExecutionResult.returnDirect()`.
5. Nếu là `true`, dừng vòng và trả kết quả tool cho caller.
6. Nếu là `false`, thêm tool result vào lịch sử và gọi mô hình tiếp.

Ví dụ:

~~~java
String response = chatClient.prompt()
    .user("Cho tôi biết tình trạng đơn hàng ORD-100.")
    .tools(orderTools)
    .call()
    .content();
~~~

`ChatClient` tự xử lý quy tắc all-or-nothing. Nếu model chỉ gọi một tool direct hoặc gọi nhiều tool mà tất cả đều direct, kết quả được trả về mà không có lượt tổng hợp từ mô hình. Nếu có ít nhất một tool không direct, advisor gửi toàn bộ kết quả của vòng đó về mô hình và tiếp tục.

Nếu ứng dụng cần đọc đầy đủ nhiều kết quả direct, hãy lấy `ChatResponse` và kiểm tra danh sách `Generation` trong response thay vì giả định rằng `content()` luôn là một bản tổng hợp duy nhất. Kết quả direct đến từ tool; mô hình không viết lại hoặc hợp nhất chúng.

## 7. Kiểm soát thủ công với ChatModel

Khi dùng `ChatModel` trực tiếp, ứng dụng tự điều phối vòng. Sau `executeToolCalls(...)`, phải kiểm tra `returnDirect()` trước khi gọi mô hình lần nữa:

~~~java
ToolExecutionResult execution =
    toolCallingManager.executeToolCalls(prompt, response);

if (execution.returnDirect()) {
    // Mọi tool trong response đều direct.
    // Trả kết quả tool cho tầng gọi, không gọi ChatModel thêm.
    return ToolExecutionResult.buildGenerations(execution);
}

// Có ít nhất một tool không direct: gửi tất cả tool result về model.
prompt = new Prompt(execution.conversationHistory(), chatOptions);
response = chatModel.call(prompt);
~~~

`ToolExecutionResult.returnDirect()` đã tổng hợp metadata của các callback trong response. Ứng dụng không cần tự duyệt từng callback rồi chọn một kết quả direct riêng lẻ. Nếu giá trị là `false`, `conversationHistory()` chứa yêu cầu tool call và kết quả tương ứng để tạo prompt tiếp theo.

## 8. Chọn thiết kế theo mục tiêu trả kết quả

Quy tắc all-or-nothing nên ảnh hưởng đến cách tổ chức tool và workflow.

| Mục tiêu | Cách thiết kế |
| --- | --- |
| Muốn mô hình tổng hợp nhiều nguồn dữ liệu | Để tất cả tool trong nhóm có `returnDirect = false` |
| Một tool duy nhất đã trả câu trả lời cuối | Đặt `returnDirect = true` cho tool đó |
| Nhiều tool cùng trả dữ liệu cuối, caller tự kết hợp | Đặt `returnDirect = true` cho tất cả tool có thể được gọi trong cùng vòng; caller xử lý mọi kết quả |
| Cần mô hình tổng hợp một tool direct với tool thường | Không dùng mixed flags nếu muốn chắc chắn có lượt tổng hợp; đặt các tool liên quan về `false` |
| Nhiều thao tác nội bộ nhưng muốn một kết quả direct | Tạo một aggregate tool gọi các service cần thiết rồi trả một DTO cuối |
| Cần chạy nhiều bước theo thứ tự | Tách thành các lượt hoặc workflow stage với tool set riêng |

### Cách 1: để mô hình tổng hợp

Nếu giao diện cần một câu trả lời tự nhiên kết hợp thông tin đơn hàng, vận chuyển và hóa đơn, hãy để các tool trả kết quả về mô hình:

~~~java
@Tool(description = "Tra cứu tóm tắt đơn hàng.")
public OrderSummary getOrderSummary(String orderId) { ... }

@Tool(description = "Tra cứu trạng thái vận chuyển.")
public DeliveryStatus getDeliveryStatus(String orderId) { ... }

@Tool(description = "Tra cứu hóa đơn.")
public InvoiceSummary getInvoiceSummary(String orderId) { ... }
~~~

Không đặt `returnDirect = true` cho các tool trong nhóm này. Mô hình sẽ nhận tất cả kết quả và tạo câu trả lời cuối.

### Cách 2: tạo aggregate tool

Nếu ứng dụng đã biết phải gọi những service nào và muốn trả một DTO hoàn chỉnh mà không cần mô hình tổng hợp, hãy gom công việc vào một tool:

~~~java
@Tool(
    name = "get_order_overview",
    description = "Lấy toàn bộ thông tin tổng quan đơn hàng, gồm đơn hàng, giao hàng và hóa đơn.",
    returnDirect = true
)
public OrderOverview getOrderOverview(String orderId) {
    OrderSummary order = orderService.getSummary(orderId);
    DeliveryStatus delivery = deliveryService.getStatus(orderId);
    InvoiceSummary invoice = invoiceService.getSummary(orderId);

    return new OrderOverview(order, delivery, invoice);
}
~~~

Mô hình chỉ thấy một tool và caller nhận một kết quả tổng hợp. Ứng dụng chủ động điều phối các service nội bộ; mô hình không cần chọn nhiều tool riêng lẻ.

### Cách 3: tách workflow thành các giai đoạn

Nếu một giai đoạn cần mô hình phân tích dữ liệu, còn giai đoạn cuối trả một tài liệu hoặc DTO trực tiếp, hãy tách thành các request có tool set phù hợp:

1. Request đầu cung cấp các tool tra cứu với `returnDirect = false`; mô hình tổng hợp và xác định dữ liệu cần tiếp.
2. Ứng dụng kiểm tra kết quả, quyền và trạng thái workflow.
3. Request sau chỉ cung cấp tool trả kết quả cuối với `returnDirect = true`.

Không đưa cả tool direct cuối cùng vào cùng nhóm mặc định với các tool phân tích nếu bạn muốn chắc chắn mô hình có một lượt tổng hợp trước đó. Lưu ý `.tools(...)` của một request được nối với `defaultTools(...)` của client; hãy kiểm tra tập tool cuối cùng được cung cấp cho model.

## 9. Những điều returnDirect không làm

`returnDirect` chỉ quyết định đường đi của kết quả sau khi callback thực thi. Nó không:

- Buộc mô hình chỉ gọi một tool trong response.
- Cho phép một tool direct bỏ qua các tool không direct trong cùng batch.
- Bỏ qua việc thực thi các tool còn lại trong response.
- Xác nhận rằng người dùng có quyền thực hiện thao tác.
- Tự gộp nhiều kết quả thành một DTO hoặc một đoạn văn.
- Bỏ qua xử lý exception, xác nhận thao tác hoặc giới hạn tool call.
- Bảo đảm mô hình sẽ chọn tool direct thay vì tool khác.

Đặc biệt, không dùng `returnDirect = true` như một biện pháp bảo vệ cho tool có tác động phụ. Nếu tool gửi email, hoàn tiền hoặc thay đổi dữ liệu, vẫn cần authorization, idempotency và confirmation phù hợp. Việc trả kết quả thẳng chỉ xảy ra sau khi tool đã chạy.

## 10. Kết hợp với lỗi và confirmation

`returnDirect` không thay thế cơ chế xử lý lỗi của tool. Nếu callback phát sinh lỗi, `ToolExecutionExceptionProcessor` quyết định gửi thông báo lỗi về mô hình hay ném exception cho ứng dụng. Cần kiểm thử riêng trường hợp một tool direct thất bại trong batch nhiều tool.

Confirmation cũng là một quyết định khác:

- `requiresConfirmation` hoặc `ToolCallConfirmationPolicy` quyết định có phải dừng trước khi thực thi tool để chờ người duyệt hay không.
- `returnDirect` quyết định có gọi mô hình thêm sau khi tool đã thực thi thành công hay không.

Nếu một batch có tool cần confirmation, `ToolCallingAdvisor` có thể tạm dừng cả batch trước khi thực thi các call của response. Sau khi có quyết định, ứng dụng tiếp tục thực thi theo luồng confirmation; sau đó quy tắc `returnDirect` vẫn được áp dụng cho kết quả của batch.

## 11. Kiểm thử phối hợp nhiều tool

Nên tạo các test có response mô hình chứa nhiều tool call trong cùng một vòng. Không chỉ test từng callback riêng lẻ.

| Ca kiểm thử | Metadata của các tool | Kết quả cần xác minh |
| --- | --- | --- |
| Một tool direct | A = `true` | `returnDirect()` là `true`; không gọi model lần nữa |
| Hai tool direct | A = `true`, B = `true` | `returnDirect()` là `true`; cả hai kết quả được trả caller |
| Direct rồi non-direct | A = `true`, B = `false` | `returnDirect()` là `false`; cả hai tool result được gửi lại model |
| Non-direct rồi direct | A = `false`, B = `true` | `returnDirect()` là `false`; cả hai tool result được gửi lại model |
| Hai tool non-direct | A = `false`, B = `false` | `returnDirect()` là `false`; model nhận cả hai kết quả |
| Batch nhiều tool, một tool lỗi | Kết hợp direct/non-direct | Exception processor xử lý đúng; không giả định direct bỏ qua lỗi |
| Batch có confirmation | Một tool yêu cầu duyệt | Không callback nào trong batch chạy trước khi có quyết định theo policy |
| Aggregate tool | Một callback gọi nhiều service | Một kết quả direct duy nhất được trả về |

Ví dụ kiểm thử phần quyết định aggregate có thể dùng `ToolExecutionResult` giả hoặc callback test:

~~~java
assertThat(execution.returnDirect()).isTrue();
~~~

Với batch hỗn hợp:

~~~java
assertThat(execution.returnDirect()).isFalse();
assertThat(execution.conversationHistory())
    .anyMatch(message -> message instanceof ToolResponseMessage);
~~~

Trong integration test, mock `ChatModel` để trả response có hai tool call. Xác minh:

- Hai callback đều được thực thi đúng số lần.
- Khi tất cả direct, không có request mô hình tiếp theo.
- Khi có một callback non-direct, mô hình nhận history chứa tất cả tool response của vòng đó.
- Caller nhận đủ các generation hoặc response theo hợp đồng API của ứng dụng.

## 12. Lỗi thiết kế thường gặp

| Biểu hiện | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Tool direct không trả thẳng kết quả | Một tool khác trong cùng response có `returnDirect = false` | Kiểm tra toàn bộ tool có thể được gọi trong cùng vòng |
| Chỉ một kết quả được hiển thị | Caller đọc một generation hoặc một trường content trong khi có nhiều tool result direct | Xử lý toàn bộ `ChatResponse.getResults()` theo response contract |
| Mô hình vẫn được gọi sau tool direct | `ToolExecutionResult.returnDirect()` là `false` do batch hỗn hợp | Đưa các tool cần tổng hợp về non-direct hoặc tách giai đoạn |
| Mô hình không tổng hợp kết quả | Tất cả tool trong batch đều direct | Đặt `returnDirect = false` cho nhóm cần mô hình phân tích |
| Dữ liệu direct không có định dạng mong muốn | Caller kỳ vọng mô hình chuẩn hóa kết quả | Trả DTO ổn định từ service hoặc dùng tool non-direct |
| Tool ghi vẫn chạy dù caller không nhận câu trả lời từ model | Nhầm `returnDirect` với cơ chế duyệt hoặc phân quyền | Thực hiện authorization/confirmation trước khi callback chạy |
| Thêm tool runtime nhưng vẫn có tool direct ngoài dự kiến | `defaultTools(...)` vẫn được nối với `.tools(...)` | Kiểm tra tập tool hợp nhất hoặc tách client/request scope |

## 13. Checklist trước khi bật returnDirect

- Kết quả của tool có thực sự là câu trả lời cuối mà không cần mô hình diễn giải?
- Mô hình có thể yêu cầu nhiều tool trong cùng response không?
- Tất cả tool có thể được gọi cùng lượt đã có metadata phù hợp chưa?
- Nếu một tool non-direct xuất hiện, ứng dụng có chấp nhận gửi lại tất cả kết quả cho mô hình không?
- Nếu tất cả tool direct, caller có xử lý được nhiều kết quả mà không cần mô hình tổng hợp không?
- Có nên thay nhiều tool bằng một aggregate tool trả DTO cuối không?
- Tập tool mặc định và tập tool theo request có vô tình tạo batch hỗn hợp không?
- Authorization, confirmation, idempotency và exception handling đã được xử lý độc lập chưa?
- Integration test đã bao gồm trường hợp all-direct và mixed chưa?

## Bài thực hành

Một assistant xử lý đơn hàng có ba tool:

- `getOrderSummary`: trả tóm tắt đơn hàng.
- `getDeliveryStatus`: trả trạng thái vận chuyển.
- `getInvoiceDocument`: trả tài liệu hóa đơn.

Hãy thiết kế và kiểm thử ba trường hợp:

1. `getOrderSummary` và `getInvoiceDocument` đều đặt `returnDirect = true`. Xác minh cả hai kết quả được trả về caller mà không có lượt mô hình tiếp theo.
2. `getOrderSummary` đặt `returnDirect = true`, `getDeliveryStatus` giữ mặc định `false`. Xác minh cả hai kết quả được gửi lại mô hình và mô hình có thể tổng hợp câu trả lời.
3. Tạo `getOrderOverview` gọi ba service nội bộ và trả một DTO với `returnDirect = true`. So sánh hợp đồng response và số lần gọi mô hình với hai trường hợp trên.

Sau khi hoàn thành, hãy giải thích vì sao một tool direct không thể tự tách kết quả khỏi batch hỗn hợp, và khi nào nên dùng aggregate tool thay vì yêu cầu mô hình gọi nhiều tool direct.

## Ghi nhớ

`returnDirect` được khai báo theo từng tool nhưng được áp dụng theo kết quả tổng hợp của một vòng. Nếu tất cả tool trong response đều direct, Spring AI trả các tool result trực tiếp cho caller và dừng vòng mô hình. Chỉ cần một tool non-direct, toàn bộ kết quả của vòng được gửi lại mô hình. Vì vậy, hãy chọn metadata theo mục tiêu của cả nhóm: để mô hình tổng hợp thì dùng non-direct; để caller nhận nhiều kết quả thì tất cả phải direct; nếu cần một kết quả cuối đã hợp nhất, cân nhắc aggregate tool hoặc tách workflow thành các giai đoạn.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling / Return Direct](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — ToolCallingAdvisor / Return Direct](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 — ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [ToolExecutionResult API — Spring AI 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/model/tool/ToolExecutionResult.html)
- [ToolMetadata API — Spring AI 2.1.x](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/metadata/ToolMetadata.html)

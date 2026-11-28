# Khi nào dùng công cụ và khi nào gọi trực tiếp dịch vụ nghiệp vụ

Trong một ứng dụng dùng Spring AI, mô hình ngôn ngữ có thể đề xuất gọi một công cụ để lấy dữ liệu hoặc thực hiện một thao tác. Điều đó không có nghĩa mọi yêu cầu của người dùng đều phải đi qua công cụ. Có những việc ứng dụng đã biết chính xác phải làm và có thể gọi dịch vụ nghiệp vụ ngay; có những việc cần mô hình hiểu ý định, chọn khả năng phù hợp hoặc quyết định thứ tự nhiều bước. Chọn đúng đường đi giúp hệ thống dễ kiểm soát, nhanh, tiết kiệm chi phí và an toàn hơn.

Bài học này đặt việc gọi công cụ vào kiến trúc ứng dụng Spring AI Tool Calling. Trọng tâm là ranh giới giữa mô hình, lớp điều phối, callback và dịch vụ nghiệp vụ; cách quyết định khi nào để mô hình yêu cầu gọi công cụ; và những kiểm soát ứng dụng phải giữ khi xử lý dữ liệu, quyền truy cập, lỗi và nhiều lượt gọi.

## Sau bài học, bạn có thể

- Phân biệt một lời gọi dịch vụ nghiệp vụ do mã ứng dụng quyết định với một lời gọi công cụ do mô hình đề xuất.
- Chọn cách thực thi phù hợp dựa trên tính xác định của quy trình, nhu cầu suy luận, độ nhạy cảm và chi phí.
- Giải thích vai trò của @Tool, ToolCallback, schema đầu vào và ToolContext trong Spring AI.
- Thiết kế luồng lai: mô hình hỗ trợ hiểu ý định và chọn công cụ, còn ứng dụng xác thực, phân quyền và thực thi nghiệp vụ.
- Nhận diện các rủi ro khi xử lý nhiều lượt gọi công cụ, thao tác ghi dữ liệu và lỗi từ dịch vụ phía sau.

## Hai cách để ứng dụng sử dụng dịch vụ nghiệp vụ

Giả sử hệ thống có một dịch vụ tra cứu trạng thái đơn hàng. Dịch vụ đó có thể được gọi theo hai cách.

**Gọi trực tiếp từ mã ứng dụng:** Một endpoint nhận yêu cầu có cấu trúc, ứng dụng đã biết cần tra cứu đơn hàng nào và gọi dịch vụ tương ứng. Ví dụ, người dùng mở trang chi tiết đơn hàng rồi bấm nút “Làm mới trạng thái”. Controller hoặc application service gọi OrderQueryService với mã đơn hàng và danh tính đã xác thực. Không cần mô hình ngôn ngữ chọn công cụ.

**Gọi thông qua tool calling:** Người dùng hỏi bằng ngôn ngữ tự nhiên: “Đơn gần nhất của tôi đã được giao chưa?”. Ứng dụng chuyển câu hỏi và các công cụ được phép dùng cho mô hình. Mô hình xác định rằng cần tra cứu đơn hàng, tạo một yêu cầu gọi công cụ với các tham số phù hợp. Ứng dụng nhận yêu cầu đó, kiểm tra, gọi callback; callback chuyển tiếp đến OrderQueryService. Kết quả được gửi lại cho mô hình để mô hình diễn đạt câu trả lời.

Khác biệt chính nằm ở **ai quyết định cần gọi khả năng nào và với tham số nào**. Khi mã ứng dụng đã biết chính xác bước tiếp theo, gọi trực tiếp thường đơn giản hơn. Khi cần diễn giải ngôn ngữ tự nhiên hoặc lựa chọn giữa nhiều khả năng, tool calling có thể giúp mô hình tham gia vào bước lựa chọn.

Tool calling không trao quyền thực thi trực tiếp cho mô hình. Mô hình chỉ phát ra một yêu cầu có cấu trúc. Ứng dụng vẫn chịu trách nhiệm tìm callback hợp lệ, kiểm tra đầu vào, xác thực quyền, gọi dịch vụ và xử lý kết quả.

## Nhìn đúng ranh giới kiến trúc

Một luồng tool calling điển hình có các thành phần sau:

~~~mermaid
flowchart TD
    U[Người dùng] --> A[Ứng dụng và lớp điều phối]
    A -->|Quy trình đã xác định| S[Dịch vụ nghiệp vụ]
    A -->|Cần diễn giải hoặc lựa chọn| M[Mô hình ngôn ngữ]
    M -->|Yêu cầu gọi công cụ và đối số| A
    A --> V[Kiểm tra schema, quyền và chính sách]
    V --> C[ToolCallback]
    C --> S
    S --> C
    C -->|Kết quả công cụ| A
    A -->|Kết quả và lịch sử hội thoại| M
    M -->|Câu trả lời hoặc yêu cầu công cụ tiếp theo| A
    A --> U
~~~

Các thành phần có trách nhiệm khác nhau:

- **Mô hình ngôn ngữ** diễn giải yêu cầu, chọn một công cụ trong danh sách được cung cấp, tạo đối số theo schema và có thể dùng kết quả để quyết định bước tiếp theo. Mô hình không phải nơi thực thi quy tắc nghiệp vụ.
- **Ứng dụng và lớp điều phối** quyết định công cụ nào được cung cấp trong phiên, tiếp nhận yêu cầu gọi công cụ, áp dụng chính sách, quản lý lịch sử hội thoại, giới hạn số vòng gọi và chuyển kết quả về mô hình.
- **ToolCallback** là điểm thực thi mà ứng dụng đăng ký cho mô hình sử dụng. Callback chuyển yêu cầu công cụ thành lời gọi trong ứng dụng. Nó có thể được tạo từ phương thức có annotation hoặc được xây dựng tùy chỉnh.
- **Dịch vụ nghiệp vụ** giữ quy tắc nghiệp vụ, kiểm tra điều kiện, truy cập kho dữ liệu và thực hiện thay đổi trạng thái. Controller, tác vụ nền và tool adapter có thể cùng gọi dịch vụ này.
- **Danh tính và quyền truy cập** được xác định ở phía ứng dụng. Tên người dùng, tenant, vai trò hoặc phạm vi dữ liệu không được tin cậy chỉ vì mô hình đưa chúng vào đối số.

Việc tách lớp như vậy giúp một quy tắc như “khách hàng chỉ được xem đơn hàng thuộc tài khoản của mình” được áp dụng nhất quán dù yêu cầu đến từ giao diện web, API hay trợ lý AI.

## Khi nào nên gọi trực tiếp dịch vụ nghiệp vụ?

Gọi trực tiếp là lựa chọn phù hợp khi ứng dụng đã biết thao tác cần thực hiện và không cần mô hình suy luận để chọn công cụ.

**Quy trình có bước đi cố định.** Người dùng bấm nút tải hóa đơn, hệ thống biết phải gọi InvoiceService. Người dùng xác nhận thanh toán trên màn hình checkout, backend biết phải chạy quy trình thanh toán đã thiết kế. Đưa mô hình vào giữa một chuỗi bước cố định làm tăng độ trễ và thêm một điểm có thể trả lời sai.

**Đầu vào đã có cấu trúc rõ ràng.** Một REST endpoint nhận orderId, một lệnh từ hàng đợi chứa customerId, hoặc một tác vụ theo lịch có dữ liệu đầy đủ thường không cần diễn giải bằng ngôn ngữ tự nhiên. Ứng dụng nên xác thực dữ liệu rồi gọi dịch vụ tương ứng.

**Kết quả phải xác định và có thể kiểm chứng.** Tính thuế, kiểm tra hạn mức, áp dụng chính sách giá, tính phí vận chuyển theo bảng quy tắc hoặc kiểm tra trạng thái giao dịch là các phép xử lý mà dịch vụ nghiệp vụ cần thực hiện theo quy tắc rõ ràng. Mô hình có thể giải thích kết quả, nhưng không nên tự thay thế thuật toán hoặc nguồn dữ liệu có thẩm quyền.

**Thao tác nhạy cảm hoặc có tác động lớn.** Xóa tài khoản, chuyển tiền, hoàn tiền, thay đổi quyền, xác nhận đơn hàng hay phát hành chứng từ cần quy trình xác thực và phê duyệt rõ ràng. Nếu ứng dụng đã có nút xác nhận hoặc workflow chuyên biệt, gọi trực tiếp sau khi xác nhận thường dễ kiểm soát hơn. Nếu vẫn cho phép trợ lý khởi tạo thao tác, ứng dụng phải có bước xác nhận và kiểm tra quyền ở phía server trước khi thực thi.

**Độ trễ, lưu lượng hoặc chi phí là ưu tiên.** Mỗi lượt gọi mô hình đều có chi phí và độ trễ. Một tác vụ đơn giản được gọi thường xuyên có thể chạy hiệu quả hơn khi backend gọi thẳng dịch vụ. Tool calling chỉ nên được thêm khi lợi ích về hiểu ý định hoặc điều phối thực sự cần thiết.

**Tác vụ nền hoặc tích hợp máy-máy.** Đồng bộ dữ liệu, xử lý sự kiện, gửi thông báo theo điều kiện cố định và các job định kỳ thường nên chạy theo luồng ứng dụng thông thường. Không cần đưa mô hình vào một quy trình mà điều kiện và hành động đã được định nghĩa đầy đủ.

## Khi nào nên để mô hình yêu cầu gọi công cụ?

Tool calling phù hợp khi khả năng hiểu ngôn ngữ hoặc lựa chọn theo ngữ cảnh của mô hình giúp ứng dụng xử lý yêu cầu tốt hơn.

**Người dùng diễn đạt bằng ngôn ngữ tự nhiên.** Người dùng có thể nói “Tìm giúp tôi các đơn đang giao trễ” thay vì cung cấp một bộ lọc chính xác. Mô hình có thể diễn giải ý định, xác định công cụ tra cứu đơn hàng và chuyển các điều kiện phù hợp theo schema. Ứng dụng vẫn cần kiểm tra các điều kiện đó trước khi truy vấn.

**Có nhiều khả năng hợp lệ và cần chọn theo ngữ cảnh.** Một trợ lý nội bộ có thể có công cụ tra cứu tài liệu, xem lịch, kiểm tra trạng thái yêu cầu và tạo bản nháp. Từ câu hỏi, mô hình chọn khả năng phù hợp. Đây là giá trị của tool calling: lựa chọn được đưa ra dựa trên ý nghĩa câu hỏi thay vì phải viết một nhánh if/else cho mọi cách diễn đạt.

**Cần thu thập thông tin trước khi thực hiện.** Nếu người dùng nói “Đặt lịch với nhóm vào tuần tới”, mô hình có thể nhận ra cần xem lịch trống trước, sau đó hỏi thêm về thời lượng hoặc người tham dự. Nếu còn thiếu tham số bắt buộc, mô hình nên hỏi lại hoặc ứng dụng yêu cầu bổ sung; không nên tự bịa giá trị.

**Cần phối hợp nhiều công cụ theo thứ tự linh hoạt.** Một câu hỏi có thể cần tra cứu hồ sơ, lấy dữ liệu liên quan rồi tổng hợp. Mô hình có thể đề xuất công cụ tiếp theo dựa trên kết quả vừa nhận. Ứng dụng phải kiểm soát số vòng, thời gian và quyền của từng công cụ.

**Cần chuyển kết quả có cấu trúc thành câu trả lời dễ hiểu.** Công cụ trả về dữ liệu trạng thái hoặc danh sách bản ghi; mô hình có thể tóm tắt, giải thích và trả lời câu hỏi tiếp theo trong hội thoại. Nguồn dữ liệu và phép tính vẫn đến từ dịch vụ, còn mô hình đảm nhận phần giao tiếp.

Tool calling đặc biệt hữu ích với các thao tác đọc dữ liệu có phạm vi quyền rõ ràng, chẳng hạn tra cứu trạng thái đơn hàng, tìm tài liệu được phép xem hoặc kiểm tra lịch trống. Với thao tác ghi dữ liệu, cần thêm các bước kiểm soát như xác nhận, chống thực thi lặp và kiểm tra trạng thái hiện tại.

## Chọn cách nào? Một bảng quyết định

| Tình huống | Cách phù hợp thường gặp | Lý do |
|---|---|---|
| Người dùng bấm nút “Tải hóa đơn” trên trang đơn hàng | Gọi trực tiếp | Ứng dụng đã biết hành động và đối tượng |
| API nhận mã đơn hàng hợp lệ để tra cứu | Gọi trực tiếp | Đầu vào có cấu trúc, không cần mô hình lựa chọn |
| Người dùng hỏi “Đơn gần nhất của tôi đang ở đâu?” | Tool calling | Cần diễn giải ý định và xác định công cụ tra cứu |
| Trợ lý có nhiều nguồn dữ liệu và cần chọn nguồn theo câu hỏi | Tool calling | Mô hình có thể chọn khả năng phù hợp |
| Tính phí theo bảng giá và quy tắc cố định | Gọi trực tiếp | Phép tính phải có kết quả nhất quán |
| Trợ lý cần tra cứu dữ liệu rồi giải thích cho người dùng | Kết hợp | Dịch vụ cung cấp dữ liệu; mô hình trình bày |
| Hoàn tiền hoặc xóa dữ liệu | Workflow có xác nhận và kiểm tra server | Cần quyền, điều kiện và dấu vết kiểm toán |
| Job đồng bộ chạy mỗi đêm | Gọi trực tiếp | Lịch chạy và hành động đã xác định |

Có thể dùng các câu hỏi sau để ra quyết định:

1. Ứng dụng đã biết chính xác dịch vụ và tham số cần gọi chưa? Nếu có, hãy ưu tiên gọi trực tiếp.
2. Có cần hiểu một yêu cầu tự nhiên hoặc lựa chọn giữa nhiều công cụ không? Nếu có, tool calling có thể phù hợp.
3. Nếu mô hình chọn sai công cụ hoặc tạo sai tham số, hậu quả là gì? Hậu quả càng lớn thì càng cần giới hạn khả năng, xác nhận và kiểm tra phía server.
4. Thao tác có thay đổi dữ liệu hoặc tạo cam kết với bên ngoài không? Nếu có, phải áp dụng workflow ghi dữ liệu an toàn.
5. Lợi ích của mô hình có lớn hơn chi phí, độ trễ và độ phức tạp vận hành không? Nếu không, gọi trực tiếp là đủ.

## Kết hợp hai cách trong Spring AI

Trong nhiều ứng dụng, lựa chọn tốt nhất là để mô hình tham gia ở phần cần ngôn ngữ tự nhiên, còn ứng dụng giữ quyền quyết định và thực thi nghiệp vụ. Có thể xem đây là một luồng lai:

1. Ứng dụng xác thực người dùng và xác định ngữ cảnh phiên.
2. Ứng dụng chỉ cung cấp cho mô hình những công cụ phù hợp với phiên và mục đích hiện tại.
3. Mô hình chọn công cụ và tạo đối số theo schema.
4. Ứng dụng kiểm tra đối số, quyền truy cập, chính sách và trạng thái hiện tại.
5. Callback gọi dịch vụ nghiệp vụ hiện có.
6. Ứng dụng gửi kết quả công cụ lại cho mô hình để tạo câu trả lời hoặc quyết định bước tiếp theo.

Trong Spring AI, các thành phần thường gặp có vai trò như sau:

- **@Tool** đánh dấu một phương thức có thể được mô hình yêu cầu gọi. Mô tả công cụ giúp mô hình hiểu mục đích và điều kiện sử dụng.
- **@ToolParam** mô tả tham số đầu vào, giúp schema thể hiện rõ tên, ý nghĩa và yêu cầu của từng giá trị.
- **ToolCallback** đại diện cho khả năng thực thi một công cụ. Callback có tên, mô tả, schema đầu vào và logic thực thi. Spring AI có thể tạo callback từ các phương thức có annotation; ứng dụng cũng có thể xây dựng callback tùy chỉnh.
- **ToolContext** mang dữ liệu ngữ cảnh từ ứng dụng đến lúc thực thi công cụ, chẳng hạn mã người dùng đã xác thực, tenant, locale hoặc trace id. Dữ liệu này được ứng dụng cung cấp riêng với đối số do mô hình tạo ra. Không dùng ToolContext như một nơi chứa dữ liệu bí mật không cần thiết.
- **Dịch vụ nghiệp vụ** tiếp tục chứa logic nghiệp vụ và quy tắc truy cập. Phương thức công cụ nên là lớp adapter mỏng, chuyển yêu cầu sang dịch vụ phù hợp.

Ví dụ dưới đây minh họa một công cụ chỉ đọc trạng thái đơn hàng. Đây là hình dạng thiết kế; cách đăng ký tool object hoặc ToolCallback vào ChatClient phụ thuộc phiên bản Spring AI và cấu hình ứng dụng.

~~~java
@Component
class OrderTools {

    private final OrderQueryService orderQueryService;

    OrderTools(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Tool(description = "Tra cứu trạng thái của một đơn hàng mà khách hàng hiện tại được phép xem")
    public OrderStatus getOrderStatus(
            @ToolParam(description = "Mã đơn hàng cần tra cứu") String orderId,
            ToolContext toolContext) {

        String customerId = (String) toolContext.getContext().get("customerId");

        return orderQueryService.getStatusForCustomer(orderId, customerId);
    }
}
~~~

Trong ví dụ này, mô hình chỉ cung cấp orderId. customerId đến từ ngữ cảnh do ứng dụng thiết lập sau khi xác thực. Dịch vụ getStatusForCustomer phải tiếp tục kiểm tra quyền sở hữu đơn hàng; không nên chỉ dựa vào mô tả công cụ hoặc giả định rằng mô hình luôn gửi đúng mã khách hàng.

Cùng dịch vụ đó có thể được gọi trực tiếp từ một endpoint:

~~~java
@GetMapping("/orders/{orderId}/status")
OrderStatus getStatus(
        @PathVariable String orderId,
        @AuthenticationPrincipal AppPrincipal principal) {

    return orderQueryService.getStatusForCustomer(
            orderId,
            principal.customerId()
    );
}
~~~

Hai đường gọi dùng chung dịch vụ nghiệp vụ. Nhờ vậy, quy tắc truy cập và cách đọc trạng thái không bị sao chép vào tool adapter. Khi nghiệp vụ thay đổi, ứng dụng chỉ cần cập nhật dịch vụ và các kiểm thử liên quan.

### Thiết kế schema để mô hình chọn đúng

Schema là hợp đồng giữa mô hình và ứng dụng. Một schema tốt cần làm rõ:

- Tên công cụ mô tả hành động cụ thể, ví dụ getOrderStatus thay vì handleOrder.
- Mô tả công cụ nói rõ công cụ làm gì, dữ liệu nào cần có và giới hạn quan trọng.
- Tên và mô tả tham số dễ hiểu; kiểu dữ liệu, trường bắt buộc, enum, giới hạn độ dài và định dạng được khai báo rõ khi có thể.
- Tham số chỉ chứa dữ liệu mà mô hình cần quyết định. Không yêu cầu mô hình gửi mật khẩu, access token, role, tenant đáng tin cậy hoặc mã định danh nội bộ dùng để xác định quyền.
- Kết quả trả về có cấu trúc và chỉ chứa dữ liệu cần cho bước tiếp theo. Không trả về toàn bộ entity hoặc dữ liệu cá nhân không liên quan.

Nếu mô hình không thể xác định một tham số bắt buộc, ứng dụng có thể yêu cầu mô hình hỏi lại người dùng. Không nên đặt một giá trị mặc định nguy hiểm chỉ để lời gọi có thể tiếp tục.

### Dùng ToolContext đúng cách

ToolContext hữu ích khi callback cần thông tin đã được ứng dụng xác định mà mô hình không nên tự quyết định. Ví dụ:

- customerId hoặc tenantId lấy từ principal đã xác thực;
- locale hoặc múi giờ lấy từ hồ sơ hoặc thiết lập phiên;
- correlation id để liên kết log của một yêu cầu;
- phạm vi dữ liệu hoặc thông tin chính sách đã được server tính toán.

Ứng dụng phải tạo ngữ cảnh này từ nguồn đáng tin cậy. Nếu một giá trị đến từ câu người dùng hoặc đối số mô hình tạo ra, hãy xem nó là dữ liệu đầu vào chưa đáng tin cậy và kiểm tra như bình thường. ToolContext không tự cấp quyền; dịch vụ nghiệp vụ vẫn phải thực thi authorization.

## Điều phối nhiều lượt gọi công cụ

Một yêu cầu gọi công cụ có thể chỉ là bước đầu. Sau khi nhận kết quả, mô hình có thể yêu cầu công cụ thứ hai hoặc tạo câu trả lời cuối cùng. Vì vậy, ứng dụng cần quản lý một vòng điều phối thay vì giả định mỗi câu hỏi chỉ tạo đúng một callback.

Một vòng xử lý thường diễn ra như sau:

1. Ứng dụng gửi câu hỏi, lịch sử cần thiết và danh sách công cụ được phép cho mô hình.
2. Mô hình trả về câu trả lời cuối cùng hoặc một hay nhiều yêu cầu gọi công cụ.
3. Ứng dụng kiểm tra tên công cụ, schema, số lượng lời gọi, quyền và chính sách.
4. Ứng dụng thực thi callback được phép và thu nhận kết quả.
5. Ứng dụng thêm kết quả vào lịch sử theo định dạng tool result rồi gọi mô hình tiếp.
6. Vòng lặp kết thúc khi mô hình trả lời, khi đạt giới hạn hoặc khi có lỗi cần dừng.

Ứng dụng cần xác định trước giới hạn số vòng gọi, thời gian tổng, số công cụ được thực thi và kích thước kết quả. Với các công cụ độc lập chỉ đọc, có thể cân nhắc thực thi song song nếu framework và nghiệp vụ cho phép. Với các bước phụ thuộc nhau hoặc có thay đổi trạng thái, cần thực hiện tuần tự và kiểm tra trạng thái giữa các bước.

Không nên để mô hình tự quyết định vòng lặp kéo dài vô hạn. Nếu đạt giới hạn, ứng dụng dừng điều phối và trả thông báo phù hợp. Nếu một công cụ thất bại, ứng dụng quyết định có thể thử lại hay phải dừng; không mặc định gửi lại mọi thao tác.

## Quyền truy cập và an toàn khi thực thi

Mọi đối số do mô hình tạo ra đều phải được xem là đầu vào không đáng tin cậy. Mô hình có thể hiểu sai câu hỏi, chọn sai công cụ, bỏ sót tham số hoặc tạo một giá trị hợp lệ về cú pháp nhưng không hợp lệ về nghiệp vụ.

**Xác thực ở tầng ứng dụng.** Danh tính người dùng phải đến từ cơ chế xác thực của ứng dụng. Không cho mô hình tự khai báo mình là người dùng nào hoặc có vai trò gì.

**Phân quyền ở tầng dịch vụ.** Mỗi lần thực thi phải kiểm tra người dùng hiện tại có được phép truy cập tài nguyên hoặc thực hiện hành động hay không. Với dữ liệu nhiều tenant, truy vấn phải được giới hạn theo tenant đã xác thực. Việc ẩn một công cụ khỏi danh sách của mô hình không thay thế cho kiểm tra quyền trong backend.

**Giới hạn công cụ được cung cấp.** Chỉ đăng ký các công cụ cần cho tác vụ hiện tại. Một trợ lý tra cứu đơn hàng không cần có quyền gọi công cụ quản trị người dùng hoặc hoàn tiền. Phạm vi công cụ càng hẹp thì hậu quả của một lựa chọn sai càng nhỏ.

**Tách thao tác đọc và ghi.** Đặt tên, mô tả và quyền riêng cho công cụ đọc dữ liệu và công cụ thay đổi dữ liệu. Với hành động có tác động lớn, hãy yêu cầu xác nhận rõ ràng từ người dùng và kiểm tra lại điều kiện ở server ngay trước khi thực thi.

**Chống thực thi lặp.** Một lượt hội thoại có thể bị gửi lại do timeout hoặc retry. Với thao tác ghi, cần idempotency key hoặc cơ chế phát hiện lệnh trùng. Không để một yêu cầu gọi công cụ lặp lại vô tình tạo hai đơn hàng hoặc hoàn tiền hai lần.

**Giảm dữ liệu trả về.** Chỉ đưa vào kết quả công cụ những trường cần thiết cho mô hình. Tránh đưa token, thông tin xác thực, dữ liệu cá nhân hoặc nội dung nội bộ không liên quan vào lịch sử hội thoại.

**Ghi nhận dấu vết.** Ghi lại người dùng hoặc phiên đã yêu cầu, tên công cụ, thời điểm, kết quả, thời gian thực thi và mã tương quan. Hạn chế ghi toàn bộ tham số nhạy cảm hoặc dữ liệu cá nhân vào log.

## Xử lý lỗi trong tool calling

Cần phân biệt lỗi do đầu vào, lỗi quyền, lỗi nghiệp vụ và lỗi hạ tầng vì cách phản hồi khác nhau.

| Nhóm lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Đầu vào không hợp lệ | Thiếu orderId, sai định dạng | Từ chối thực thi và yêu cầu bổ sung hoặc sửa dữ liệu |
| Không có quyền | Người dùng xem đơn của tài khoản khác | Từ chối theo chính sách, không tiết lộ dữ liệu |
| Không tìm thấy | Mã đơn không tồn tại hoặc không hiển thị với người dùng | Trả kết quả an toàn, tránh xác nhận sự tồn tại của dữ liệu bị giới hạn |
| Xung đột nghiệp vụ | Đơn đã giao nên không thể hủy | Trả lý do nghiệp vụ rõ ràng để mô hình giải thích |
| Dịch vụ phụ thuộc lỗi | Hệ thống vận chuyển không phản hồi | Dừng hoặc thử lại có giới hạn nếu thao tác an toàn |
| Timeout hoặc lỗi mô hình | Không nhận được phản hồi tiếp theo | Kết thúc có kiểm soát, giữ mã tương quan để truy vết |

Không gửi stack trace, câu truy vấn SQL, thông tin xác thực hoặc chi tiết hạ tầng cho mô hình hay người dùng. Có thể trả về mã lỗi ổn định và thông điệp an toàn để lớp điều phối quyết định có nên hỏi lại, thử công cụ khác hay thông báo không thể hoàn tất.

Chỉ retry tự động khi biết thao tác có thể lặp an toàn hoặc đã có cơ chế idempotency. Đối với thao tác ghi, cần biết trạng thái lần thực thi trước trước khi gửi lại.

## Ví dụ: trợ lý hỗ trợ đơn hàng

Xét ba yêu cầu sau:

**“Đơn 8472 đang ở trạng thái nào?”**

Nếu đây là câu hỏi trong giao diện trợ lý, mô hình có thể chọn getOrderStatus và trích xuất mã 8472. Callback dùng danh tính trong ToolContext để gọi dịch vụ tra cứu. Nếu người dùng đang ở trang chi tiết đơn 8472 và bấm nút làm mới, endpoint có thể gọi trực tiếp cùng dịch vụ.

**“Tìm các đơn của tôi giao trễ và giải thích đơn nào cần chú ý.”**

Đây là trường hợp phù hợp với tool calling. Mô hình có thể chọn công cụ tìm đơn theo điều kiện, nhận danh sách đã được giới hạn theo người dùng, sau đó tổng hợp. Quy tắc xác định “giao trễ” nên được tính ở dịch vụ theo dữ liệu vận chuyển và chính sách đã định nghĩa; mô hình có thể giải thích kết quả.

**“Hủy đơn 8472 giúp tôi.”**

Không nên coi yêu cầu tự nhiên này là đủ để thực thi ngay. Trợ lý có thể tra cứu khả năng hủy và trình bày ảnh hưởng. Ứng dụng yêu cầu người dùng xác nhận. Sau xác nhận, backend kiểm tra lại quyền và trạng thái đơn, sau đó gọi dịch vụ hủy với cơ chế chống thực thi lặp. Mô hình có thể giúp điều phối hội thoại, nhưng quyết định cho phép hủy thuộc về ứng dụng và dịch vụ nghiệp vụ.

## Kiểm thử thiết kế

Kiểm thử cần xác minh cả logic nghiệp vụ lẫn đường đi qua tool calling:

- **Kiểm thử dịch vụ nghiệp vụ:** quy tắc trạng thái, quyền sở hữu, điều kiện hủy, tính phí và các trường hợp biên phải đúng khi gọi trực tiếp.
- **Kiểm thử callback:** tên, mô tả, schema, ánh xạ tham số và kết quả trả về đúng hợp đồng.
- **Kiểm thử ngữ cảnh:** ToolContext chứa đúng danh tính và tenant do ứng dụng thiết lập; callback không lấy quyền từ đối số mô hình tạo ra.
- **Kiểm thử phân quyền:** người dùng không thể xem hoặc sửa dữ liệu của người khác bằng cách yêu cầu mô hình đổi mã định danh.
- **Kiểm thử điều phối:** mô hình yêu cầu một công cụ, nhiều công cụ, công cụ tiếp theo dựa trên kết quả, hoặc trả lời trực tiếp mà không gọi công cụ.
- **Kiểm thử đầu vào và lỗi:** tham số thiếu, sai kiểu, tên công cụ không được phép, timeout, lỗi dịch vụ và kết quả rỗng đều được xử lý có kiểm soát.
- **Kiểm thử thao tác ghi:** xác nhận, trạng thái thay đổi giữa lúc kiểm tra và lúc thực thi, retry và idempotency.
- **Kiểm thử giới hạn:** số vòng gọi, thời gian tổng và kích thước kết quả không vượt chính sách.

Ngoài kiểm thử tự động, nên đánh giá các cách diễn đạt khác nhau của cùng một ý định để xem mô hình có chọn đúng công cụ và tạo đủ tham số hay không. Việc đánh giá lựa chọn của mô hình không thay thế kiểm thử quyền và quy tắc nghiệp vụ.

## Những sai lầm thường gặp

- **Biến mọi phương thức service thành công cụ.** Danh sách công cụ lớn và mô tả chồng chéo làm mô hình khó lựa chọn, đồng thời mở rộng bề mặt tấn công. Chỉ công bố các khả năng thật sự cần cho trợ lý.
- **Đưa logic nghiệp vụ vào phương thức @Tool.** Điều này khiến logic bị tách khỏi luồng API và job, khó tái sử dụng và kiểm thử. Hãy để tool adapter gọi dịch vụ nghiệp vụ.
- **Tin tham số quyền do mô hình gửi.** customerId, tenantId hoặc role từ mô hình không chứng minh danh tính. Lấy chúng từ ngữ cảnh server đã xác thực.
- **Dùng mô hình thay cho phép tính xác định.** Không để mô hình tự tính tiền, tự quyết định quyền hoặc tự suy ra trạng thái giao dịch khi backend có quy tắc và dữ liệu chuẩn.
- **Cho phép thao tác ghi không có xác nhận hoặc chống lặp.** Một câu trả lời tự nhiên không phải bằng chứng người dùng đã xác nhận một hành động không thể đảo ngược.
- **Giả định chỉ có một lần gọi công cụ.** Mô hình có thể yêu cầu nhiều bước; ứng dụng cần giới hạn và điều phối vòng gọi.
- **Trả quá nhiều dữ liệu cho mô hình.** Kết quả công cụ nên nhỏ, có cấu trúc và chỉ chứa dữ liệu cần thiết.

## Ghi nhớ khi thiết kế

Hãy gọi trực tiếp dịch vụ khi quy trình và hành động đã rõ trong mã ứng dụng. Hãy dùng tool calling khi mô hình cần hiểu yêu cầu tự nhiên, lựa chọn giữa các khả năng hoặc điều phối bước tiếp theo. Trong cả hai trường hợp, dịch vụ nghiệp vụ vẫn là nơi thực thi quy tắc; ứng dụng luôn chịu trách nhiệm xác thực, phân quyền, kiểm tra dữ liệu, xử lý lỗi và kiểm soát tác động.

Một tích hợp Spring AI Tool Calling tốt không nằm ở số lượng công cụ được công bố. Nó nằm ở việc mỗi công cụ có mục đích rõ, schema dễ hiểu, quyền tối thiểu, callback mỏng và đường thực thi có thể kiểm thử.

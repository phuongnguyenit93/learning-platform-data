# Rủi ro tác dụng phụ khi gọi method từ biểu thức SpEL

Spring Expression Language (SpEL) cho phép gọi method trên root object, property hoặc biến được đưa vào EvaluationContext. Một lời gọi method có thể chỉ trả về dữ liệu, nhưng cũng có thể thay đổi trạng thái, ghi database, gửi thông điệp, gọi API hoặc thực hiện một thao tác bên ngoài. Vì biểu thức có thể được đánh giá nhiều lần và ở những thời điểm khác nhau, method có tác dụng phụ cần được kiểm soát rõ ràng.

Khi thiết kế biểu thức, hãy xem việc gọi method là một hành động có thể thực thi logic của ứng dụng. Cần xác định ai được phép gọi, method nào được phép gọi, khi nào lời gọi xảy ra và cách xử lý nếu thao tác chỉ hoàn thành một phần.

## 1. Phân biệt method đọc dữ liệu và method có tác dụng phụ

Một method chỉ đọc thường trả về thông tin mà không làm thay đổi trạng thái quan sát được của hệ thống. Ví dụ:

    #order.items.size()
    #customer.getDisplayName()
    #pricingService.calculatePreview(#order)

Các method như vậy phù hợp hơn với biểu thức dùng để hiển thị, kiểm tra điều kiện hoặc tính toán giá trị dẫn xuất, miễn là chúng thực sự không ghi dữ liệu hoặc gọi dịch vụ có tác dụng phụ.

Một method có tác dụng phụ có thể thay đổi object hoặc trạng thái bên ngoài:

    #order.approve()
    #inventoryService.reserve(#productId, #quantity)
    #notificationService.send(#recipient, 'Order confirmed')
    #repository.save(#order)

Các ví dụ trên có thể cập nhật trạng thái đơn hàng, giữ tồn kho, gửi thông báo hoặc ghi dữ liệu. Khi một lời gọi như vậy nằm trong biểu thức, việc đánh giá biểu thức có thể trở thành một hành động nghiệp vụ thực sự.

Tên method không đủ để kết luận nó có an toàn hay không. Một method tên `getStatus()` vẫn có thể truy cập hệ thống từ xa hoặc ghi log có ý nghĩa nghiệp vụ; một method tên `calculate()` cũng có thể cập nhật cache hoặc counter. Cần xem xét triển khai và hợp đồng của method.

## 2. Biểu thức được đánh giá nhiều lần

Việc parse một chuỗi SpEL tạo ra Expression để có thể đánh giá sau đó. Mỗi lần gọi `getValue(...)`, SpEL thực hiện đánh giá biểu thức trong context được cung cấp. Không nên giả định kết quả của lần đánh giá trước sẽ được lưu và tái sử dụng tự động.

Ví dụ:

    Expression expression =
            parser.parseExpression("#counterService.nextSequence()");

    Object first = expression.getValue(context);
    Object second = expression.getValue(context);

Nếu `nextSequence()` tăng bộ đếm, hai lần đánh giá có thể tạo ra hai số khác nhau và làm thay đổi trạng thái hai lần. Việc giữ lại đối tượng Expression để tái sử dụng không biến method có tác dụng phụ thành method chỉ chạy một lần.

Một số luồng ứng dụng có thể đánh giá cùng một biểu thức nhiều lần: khi kiểm tra điều kiện, khi dựng giao diện, khi tính toán lại dữ liệu hoặc khi xử lý retry. Nếu biểu thức gọi method ghi dữ liệu, các lần đánh giá lặp lại có thể tạo ra cập nhật trùng, gửi nhiều thông báo hoặc tiêu thụ nhiều tài nguyên.

Vì vậy, nên giữ biểu thức truy vấn ở trạng thái không gây tác dụng phụ. Thực hiện hành động ghi dữ liệu qua một bước nghiệp vụ tường minh, nơi ứng dụng kiểm soát số lần gọi và kết quả.

## 3. Tác dụng phụ trong điều kiện logic

Method có thể xuất hiện bên trong điều kiện `and`, `or` hoặc `not`:

    #account.isActive() and #auditService.recordCheck(#account.id)

Toán tử logic có thể short-circuit: nếu vế trái của AND là false, vế phải không được đánh giá; tương tự, nếu vế trái của OR là true, vế phải không cần đánh giá. Do đó, một method có tác dụng phụ nằm ở vế phải có thể chỉ được gọi trong một số trường hợp.

Điều này làm cho số lần và thứ tự tác dụng phụ phụ thuộc vào dữ liệu đầu vào cũng như cấu trúc điều kiện. Nếu thay đổi thứ tự các vế hoặc thêm một điều kiện mới, hành vi ghi dữ liệu có thể thay đổi dù mục tiêu ban đầu chỉ là điều chỉnh logic.

Không nên dùng method ghi dữ liệu để tạo side effect trong điều kiện Boolean. Hãy tách kiểm tra và hành động thành hai bước:

    Boolean allowed =
            parser.parseExpression("#account.isActive()")
                    .getValue(context, Boolean.class);

    if (Boolean.TRUE.equals(allowed)) {
        auditService.recordCheck(account.getId());
    }

Trong cách này, điều kiện chỉ trả lời câu hỏi. Java điều khiển thời điểm ghi audit và có thể kiểm tra rõ kết quả trước khi thực hiện hành động tiếp theo.

## 4. Tác dụng phụ trong đối số của method khác

Một lời gọi method có thể chứa các lời gọi khác trong danh sách đối số:

    #orderService.submit(
        #order,
        #inventoryService.reserve(#order.productId, #order.quantity)
    )

Trước khi gọi method ngoài, SpEL phải đánh giá các đối số cần truyền vào. Vì vậy, `reserve(...)` có thể thực hiện side effect trong lúc chuẩn bị đối số cho `submit(...)`.

Nếu method ngoài thất bại sau khi method trong đã giữ tồn kho, hệ thống có thể rơi vào trạng thái cập nhật một phần. Việc hai method xuất hiện trong cùng một biểu thức không tự động tạo ra transaction chung hoặc cơ chế rollback cho mọi hệ thống bên ngoài.

Hãy tránh lồng các method ghi dữ liệu trong đối số. Thay vào đó, tổ chức trình tự trong service nghiệp vụ:

    Reservation reservation =
            inventoryService.reserve(productId, quantity);

    orderService.submit(order, reservation);

Service có thể kiểm soát transaction, xử lý lỗi và bù trừ nếu một bước sau thất bại. SpEL nên được dùng để truyền hoặc tính giá trị cần thiết, còn trình tự hành động nên được thể hiện trong code nghiệp vụ.

## 5. Gọi method có thể tác động tới hệ thống bên ngoài

Tác dụng phụ không chỉ giới hạn ở object đang làm root. Một method có thể:

- Ghi hoặc xóa bản ghi trong database.
- Gửi email, SMS hoặc push notification.
- Phát message lên queue hoặc event bus.
- Gọi REST API hoặc dịch vụ thanh toán.
- Giữ hoặc giải phóng tài nguyên.
- Tạo file, ghi log kiểm toán hoặc cập nhật cache.
- Thay đổi trạng thái dùng chung giữa nhiều request.

Những thao tác này có thể thất bại vì timeout, lỗi mạng, quyền truy cập hoặc sự cố ở hệ thống đích. Một lần đánh giá SpEL có thể ném lỗi sau khi một tác dụng phụ đã xảy ra. Việc bắt exception ở tầng gọi không tự động đảo ngược thay đổi đã được hệ thống bên ngoài chấp nhận.

Với thao tác có tính chất không thể hoàn tác như gửi thông báo hoặc phát sự kiện, hãy cân nhắc thời điểm phát, cơ chế retry và khả năng gửi trùng. Nếu cần bảo đảm phát sự kiện gắn với transaction database, hãy dùng cơ chế phù hợp ở tầng ứng dụng, chẳng hạn transactional outbox, thay vì đặt lệnh gửi trực tiếp trong một biểu thức.

## 6. Retry, tính lặp an toàn và idempotency

Một thao tác được retry có thể được thực hiện nhiều hơn một lần. Điều này thường xảy ra khi request timeout hoặc ứng dụng không nhận được xác nhận từ dịch vụ đích dù dịch vụ đã xử lý thành công.

Nếu method có tác dụng phụ được gọi qua SpEL, hãy xác định rõ:

- Một lần đánh giá có thể được lặp lại trong cùng request không?
- Tầng gọi có retry khi nhận lỗi hoặc timeout không?
- Method có idempotent không, tức là gọi lặp với cùng dữ liệu có giữ được kết quả nghiệp vụ tương đương không?
- Có cần idempotency key hoặc mã yêu cầu duy nhất để chống xử lý trùng không?
- Nếu bước sau thất bại, có thao tác bù trừ nào cần thực hiện không?

Ví dụ, `setStatus('APPROVED')` có thể có tính lặp an toàn nếu chỉ đặt cùng một trạng thái và không phát sinh side effect phụ. Nhưng `incrementBalance(100)` hoặc `sendNotification(...)` thường không an toàn khi gọi lặp nếu không có cơ chế chống trùng.

Idempotency phải được thiết kế trong service hoặc hệ thống đích. Việc lưu kết quả Expression hay cache giá trị biểu thức không thay thế được cơ chế chống xử lý trùng ở tầng nghiệp vụ.

## 7. Kiểm soát method có thể được gọi qua EvaluationContext

StandardEvaluationContext mặc định cung cấp khả năng gọi method dựa trên reflection thông qua ReflectiveMethodResolver. Nếu root object hoặc biến chứa service có nhiều method công khai, biểu thức có thể gọi những method mà use case không dự định cung cấp.

Đối với biểu thức chỉ cần đọc dữ liệu, nên giới hạn object được đưa vào context và dùng SimpleEvaluationContext với cấu hình phù hợp. SimpleEvaluationContext không bật instance method invocation mặc định; nếu cần gọi instance method, ứng dụng phải bật rõ bằng builder qua `withInstanceMethods()`.

Ví dụ:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withInstanceMethods()
                    .withRootObject(viewModel)
                    .build();

Cấu hình này minh họa việc cho phép gọi instance method trên object phục vụ data binding. Nó không tự tạo allowlist theo từng method; vì vậy, object đưa vào context cần có API phù hợp với mức tin cậy của biểu thức.

Nếu cần giới hạn method chặt hơn, có thể dùng MethodResolver tùy chỉnh hoặc một facade chỉ công khai các thao tác được phép. Tránh đưa trực tiếp repository, payment service, notification service hoặc các service quản trị có quyền rộng vào context dành cho biểu thức do người dùng cung cấp.

## 8. Tạo facade có API hẹp

Một cách tổ chức an toàn hơn là cung cấp một object trung gian với các method nhỏ, có hợp đồng rõ ràng. Ví dụ, thay vì đưa toàn bộ OrderService vào context, có thể cung cấp một facade chỉ có method xem trước:

    public final class OrderExpressionView {

        private final Order order;

        public OrderExpressionView(Order order) {
            this.order = order;
        }

        public boolean isEligibleForDiscount() {
            return order.getTotal().compareTo(
                    new BigDecimal("100.00")) >= 0;
        }

        public BigDecimal getEstimatedTotal() {
            return order.getTotal();
        }
    }

Các method trong ví dụ chỉ đọc dữ liệu. Có thể đưa facade này vào root object hoặc biến để biểu thức sử dụng mà không mở ra các thao tác lưu, xóa hoặc gửi thông báo.

Nếu thật sự cần một hành động, hãy cân nhắc tạo một service chuyên biệt với method có tên và tham số thể hiện rõ hành động. Tầng Java cần xác thực quyền, kiểm tra dữ liệu và kiểm soát transaction trước khi gọi. Không dùng một facade có method tổng quát như `execute(String command)` để biến biểu thức thành bộ thực thi lệnh tùy ý.

## 9. Xử lý lỗi và quan sát hành vi

Method invocation có thể thất bại trong lúc phân giải hoặc thực thi. Một số nguyên nhân thường gặp:

- Target object là null.
- Method không tồn tại hoặc không truy cập được.
- Số lượng hoặc kiểu đối số không phù hợp.
- TypeConverter không thể chuyển đổi đối số.
- Method ném exception khi thực thi.
- Dịch vụ bên ngoài timeout hoặc từ chối thao tác.

Khi debug, hãy kiểm tra target, chữ ký method, kiểu runtime của từng đối số và lỗi gốc do method ném ra. Nếu biểu thức gọi method có side effect, cần ghi nhận mã request, trạng thái xử lý và kết quả từ service ở tầng nghiệp vụ. Tránh chỉ log toàn bộ chuỗi biểu thức nếu nó có thể chứa dữ liệu nhạy cảm.

Đối với hành động quan trọng, hãy phân biệt rõ các trạng thái: chưa bắt đầu, đã thực hiện, thất bại trước khi ghi, thất bại sau khi hệ thống đích đã xử lý và kết quả chưa xác định do timeout. Những trạng thái này quyết định có thể retry hay cần truy vấn trạng thái trước khi tiếp tục.

## 10. Kiểm thử method call có tác dụng phụ

Nên kiểm thử riêng cách đánh giá đối số và số lần method được gọi. Một số tình huống cần bao phủ:

1. Literal truyền đúng giá trị và kiểu mong đợi.
2. Property truyền giá trị hiện tại của object.
3. Expression con được đánh giá trước khi method ngoài nhận đối số.
4. Property null được xử lý đúng theo hợp đồng.
5. Overload được chọn đúng với kiểu runtime.
6. Điều kiện AND/OR không làm method side effect bị gọi ngoài dự kiến.
7. Đánh giá cùng Expression nhiều lần không gây cập nhật trùng ngoài ý muốn.
8. Exception hoặc timeout được xử lý theo chính sách retry và bù trừ.

Có thể dùng mock hoặc spy cho service để kiểm tra số lần gọi và đối số thực tế. Với method ghi database hoặc gọi dịch vụ ngoài, hãy kiểm thử transaction, idempotency và hành vi khi một bước giữa quy trình thất bại.

## 11. Ghi nhớ

Gọi method trong SpEL có thể thực thi logic và tạo tác dụng phụ. Literal, property và expression đều có thể làm đối số; SpEL đánh giá các đối số rồi phân giải method phù hợp. Một Expression được đánh giá nhiều lần có thể gọi method nhiều lần, và short-circuit có thể làm thay đổi việc một nhánh có được thực thi hay không. Hãy giữ biểu thức truy vấn ở trạng thái không gây tác dụng phụ, giới hạn method được phép gọi qua context hoặc facade, và đặt các hành động ghi dữ liệu, gọi dịch vụ ngoài, retry và transaction trong service nghiệp vụ có kiểm soát.

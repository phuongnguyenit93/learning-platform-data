# Khi nào nên dùng event thay cho gọi phương thức trực tiếp

Trong Spring, **gọi phương thức trực tiếp** phù hợp khi một thành phần cần yêu cầu một thành phần khác thực hiện công việc cụ thể và cần biết kết quả. **Application event** phù hợp khi một thành phần thông báo rằng một sự việc đã xảy ra để những thành phần quan tâm tự xử lý phản ứng của chúng.

Quyết định này ảnh hưởng đến cách các module phụ thuộc vào nhau, cách lỗi lan truyền, thứ tự xử lý và thời điểm dữ liệu được commit. Event giúp giảm phụ thuộc giữa bên phát và bên nhận, nhưng cũng làm luồng xử lý khó nhìn thấy hơn. Vì vậy, chỉ nên dùng event khi sự kiện thực sự là một ranh giới giao tiếp hữu ích.

## 1. Phân biệt lời gọi trực tiếp và event

### Gọi phương thức trực tiếp

Bên gọi biết đối tượng hoặc interface đích, gọi một phương thức và có thể nhận kết quả ngay.

Ví dụ, một quy trình đặt hàng cần kiểm tra hạn mức trước khi tiếp tục:

- OrderService gọi CreditService để kiểm tra hạn mức.
- CreditService trả về kết quả chấp thuận hoặc từ chối.
- OrderService dựa vào kết quả đó để quyết định có tạo đơn hàng hay không.

Đây là một yêu cầu có chủ đích. Nếu không có kết quả từ CreditService, bên gọi không thể hoàn thành quy trình. Một interface rõ ràng giúp thể hiện sự phụ thuộc này.

### Phát application event

Bên phát công bố một sự thật đã xảy ra. Bên phát chỉ cần biết hợp đồng của event; nó không cần biết có bao nhiêu listener đang đăng ký hoặc listener sẽ làm gì.

Ví dụ, sau khi đơn hàng được tạo, ứng dụng phát event OrderPlaced. Các listener có thể cập nhật số liệu, ghi audit hoặc chuẩn bị thông báo. OrderService không cần gọi từng listener.

Một event tốt thường mô tả sự việc bằng tên ở dạng đã xảy ra, chẳng hạn OrderPlaced, PaymentCaptured hoặc CustomerRegistered. Event mang dữ liệu bất biến đủ để listener hiểu sự việc. Tên như SendWelcomeEmail hoặc RecalculatePrice mô tả một mệnh lệnh; đó thường là dấu hiệu cho thấy bạn đang dùng event để che một lời gọi hành động.

Điểm khác biệt quan trọng: publisher không nhận kết quả trả về từ listener. Việc phát event không phải một cách thay thế cho một API cần trả lời câu hỏi hoặc quyết định nghiệp vụ.

## 2. Khi nào nên dùng event

### Có nhiều bên độc lập cần phản ứng với cùng một sự việc

Một sự việc có thể có nhiều phản ứng không phụ thuộc vào nhau. Khi OrderPlaced xảy ra, ứng dụng có thể:

- Ghi nhận số liệu đơn hàng.
- Ghi audit log.
- Cập nhật một mô hình đọc hoặc bộ đếm nội bộ.
- Yêu cầu một module thông báo chuẩn bị biên nhận.

Nếu OrderService gọi trực tiếp từng thành phần, nó phải biết tên và hợp đồng của tất cả chúng. Khi thêm một phản ứng mới, mã phát sinh event phải thay đổi dù quy trình tạo đơn hàng không thay đổi.

Với event, mỗi listener đăng ký quan tâm đến loại sự việc của nó. Có thể thêm hoặc gỡ một listener mà không cần sửa publisher, miễn là hợp đồng event vẫn phù hợp.

### Phản ứng là tác dụng phụ, không quyết định kết quả chính

Event phù hợp cho công việc bổ sung sau một hành động chính, ví dụ ghi metric, tạo thông báo nội bộ hoặc cập nhật một chỉ số. Những công việc này thường không cần trả kết quả cho luồng nghiệp vụ đã phát event.

Cần xác định rõ mức độ quan trọng của tác dụng phụ. Nếu việc gửi thông báo hoặc đồng bộ dữ liệu là nghĩa vụ bắt buộc và không được phép mất, một event trong bộ nhớ đơn thuần chưa đủ bảo đảm. Khi đó cần cơ chế lưu bền, retry và theo dõi giao nhận; phần giao dịch và outbox được trình bày ở mục 5.

### Muốn giảm phụ thuộc giữa các module

Một module có thể công bố sự kiện miền mà không tham chiếu trực tiếp đến các module đang lắng nghe. Điều này hữu ích khi các module có trách nhiệm riêng, được phát triển độc lập hoặc có thể có thêm listener theo thời gian.

Tuy nhiên, event chỉ giảm phụ thuộc ở phía publisher. Listener vẫn phải phụ thuộc vào hợp đồng event và có thể phụ thuộc vào các dịch vụ khác để xử lý. Nếu event chứa toàn bộ entity lớn hoặc listener phải biết quá nhiều chi tiết nội bộ, ranh giới giữa các module vẫn chưa thực sự rõ.

### Sự việc có ý nghĩa trong mô hình nghiệp vụ

Các sự kiện như OrderPlaced, InvoiceIssued hoặc AccountSuspended mô tả điều đã xảy ra trong miền nghiệp vụ. Chúng giúp diễn đạt rõ những thay đổi mà nhiều phần của hệ thống có thể quan tâm.

Không cần tạo event cho mọi lần gọi hàm. Nếu một thao tác chỉ là bước nội bộ của một thuật toán hoặc một lời gọi tiện ích, event thường làm thiết kế phức tạp hơn mà không tạo thêm giá trị.

## 3. Khi nào nên gọi phương thức trực tiếp

Hãy ưu tiên lời gọi trực tiếp trong các trường hợp sau:

- **Cần kết quả trả về:** bên gọi cần dữ liệu, quyết định hoặc trạng thái từ bên được gọi, ví dụ kiểm tra quyền, tính giá hoặc xác nhận hạn mức.
- **Bước xử lý là bắt buộc:** quy trình không thể tiếp tục nếu bước đó chưa thành công, ví dụ giữ chỗ tồn kho trước khi xác nhận đơn hàng.
- **Cần kiểm soát thứ tự:** bước sau phải sử dụng kết quả của bước trước hoặc chỉ được chạy sau khi bước trước hoàn thành.
- **Lỗi phải được xử lý ngay tại luồng gọi:** bên gọi cần bắt lỗi, thử lại hoặc trả phản hồi phù hợp cho người dùng.
- **Chỉ có một cộng tác viên rõ ràng:** một service gọi một service khác qua interface là thiết kế đơn giản và dễ hiểu.

Một chuỗi nghiệp vụ bắt buộc thường nên được điều phối bằng các lời gọi có chủ đích. Nếu chuyển từng bước thành event, luồng điều khiển có thể bị phân tán qua nhiều listener; việc tìm nguyên nhân lỗi và hiểu thứ tự thực thi sẽ khó hơn.

Event không tự làm cho hệ thống tốt hơn. Nếu publisher phát event rồi phải chờ một listener hoàn thành để lấy kết quả, thiết kế đó đang cần một hợp đồng gọi trực tiếp.

## 4. Application events trong Spring hoạt động thế nào

Spring cung cấp ApplicationEventPublisher để phát event và hỗ trợ listener bằng @EventListener. Từ Spring Framework 4.2, có thể phát một object Java bất kỳ; không bắt buộc phải kế thừa ApplicationEvent. Với Java 17+, record là lựa chọn phù hợp cho event mang dữ liệu bất biến.

Ví dụ dưới đây minh họa một đơn hàng được tạo và một listener chuẩn bị biên nhận sau khi transaction commit. Order là kiểu miền nghiệp vụ của ứng dụng; phần lưu đơn hàng được đặt tại vị trí chú thích.

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

// Event mô tả sự việc đã xảy ra và mang dữ liệu bất biến.
public record OrderPlaced(UUID orderId, BigDecimal total) {}

@Service
class OrderService {
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Transactional
    public void placeOrder(Order order) {
        // Kiểm tra và lưu order trong transaction tại đây.
        publisher.publishEvent(
            new OrderPlaced(order.getId(), order.getTotal())
        );
    }
}

@Component
class ReceiptListener {
    private final ReceiptService receiptService;

    ReceiptListener(ReceiptService receiptService) {
        this.receiptService = receiptService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        receiptService.prepareReceipt(event.orderId(), event.total());
    }
}
~~~

Order và ReceiptService là các kiểu của ứng dụng, cần được cung cấp trong dự án thực tế. Ví dụ cần cấu hình transaction manager phù hợp để @Transactional và transactional event listener hoạt động.

Các thành phần chính:

- ApplicationEventPublisher là API publisher. Gọi publishEvent với event object để thông báo sự việc.
- @EventListener đánh dấu một phương thức nhận event. Phương thức có thể nhận event object làm tham số.
- @TransactionalEventListener chỉ chạy theo vòng đời transaction, với phase được chỉ định. Trong ví dụ, listener chạy sau khi transaction commit thành công.

### Listener mặc định chạy đồng bộ

Nếu dùng @EventListener thông thường, Spring mặc định gọi listener đồng bộ trên thread đang phát event. Publisher chỉ tiếp tục sau khi các listener đồng bộ hoàn thành. Vì vậy:

- Listener chậm có thể làm chậm request hoặc tác vụ đang phát event.
- Event không tự chuyển sang background thread.
- Với cấu hình mặc định, exception từ listener có thể truyền ngược về nơi phát event. Nếu event được phát trong một transaction, exception phù hợp với quy tắc rollback của transaction có thể làm transaction rollback.

Có thể dùng @Order để chỉ định thứ tự của các listener đồng bộ khi thứ tự đó thực sự cần thiết. Không nên dựa vào thứ tự ngẫu nhiên hoặc coi các listener độc lập là một quy trình nghiệp vụ được điều phối.

### Khi nào cần xử lý bất đồng bộ

Nếu listener thực hiện công việc tốn thời gian và request không cần chờ, có thể kết hợp @Async với @EventListener hoặc transactional event listener, đồng thời bật xử lý async bằng @EnableAsync và cấu hình executor phù hợp.

Khi chạy bất đồng bộ:

- Listener chạy trên thread của executor; publisher không chờ listener hoàn thành.
- Exception trong listener không được trả về cho publisher như một lời gọi đồng bộ. Cần cấu hình và giám sát lỗi async phù hợp.
- Không nên giả định thứ tự hoàn thành giữa các listener hoặc giữa nhiều event.
- Transaction context của thread phát event không tự được chuyển sang thread xử lý async.

Async thay đổi thời điểm và cách xử lý lỗi; nó không biến event trong bộ nhớ thành hàng đợi bền vững.

## 5. Chọn thời điểm xử lý trong transaction

Thời điểm listener chạy đặc biệt quan trọng khi event được phát trong một phương thức @Transactional.

### @EventListener chạy tại thời điểm phát

Với listener thông thường, Spring gọi listener ngay tại lệnh publishEvent. Nếu publisher phát event trước khi transaction commit, listener chạy trước commit. Listener đồng bộ có thể tham gia cùng luồng transaction hiện tại; do đó nó có thể nhìn thấy dữ liệu chưa commit.

Điều này phù hợp khi listener cần xử lý ngay trong cùng quy trình và việc xử lý của listener phải ảnh hưởng đến kết quả transaction. Tuy nhiên, nó không phù hợp nếu listener gửi thông báo bên ngoài hoặc thực hiện một hành động không thể thu hồi trước khi biết transaction có commit hay không.

### @TransactionalEventListener chạy theo phase

Dùng @TransactionalEventListener khi listener cần gắn với vòng đời transaction. Phase mặc định là AFTER_COMMIT. Các phase có sẵn gồm:

- BEFORE_COMMIT: chạy trước khi transaction commit.
- AFTER_COMMIT: chạy sau khi commit thành công; đây là mặc định.
- AFTER_ROLLBACK: chạy sau khi transaction rollback.
- AFTER_COMPLETION: chạy khi transaction kết thúc, bất kể commit hay rollback.

Mặc định, transactional listener chỉ được kích hoạt khi có transaction đang hoạt động. Nếu event được phát ngoài transaction, listener không chạy. Có thể bật fallbackExecution = true để cho phép xử lý cả khi không có transaction, nhưng chỉ nên làm vậy nếu hành vi đó đúng với nghiệp vụ.

Với AFTER_COMMIT, dữ liệu đã được commit trước khi listener chạy. Nếu listener thất bại, transaction đã commit không thể rollback lại. Vì vậy, AFTER_COMMIT giúp tránh phản ứng trước một giao dịch thất bại, nhưng không tự cung cấp retry hay bảo đảm giao nhận.

### Khi cần bảo đảm không mất event

Application event trong một tiến trình là cơ chế thông báo nội bộ. Nếu ứng dụng dừng đột ngột sau khi database commit nhưng trước khi listener hoàn thành, công việc phía listener có thể bị mất. Một listener AFTER_COMMIT cũng không tự lưu event vào nơi bền vững.

Nếu nghiệp vụ yêu cầu giao nhận đáng tin cậy, chẳng hạn không được mất yêu cầu gửi hóa đơn hoặc đồng bộ sang hệ thống khác, hãy cân nhắc transactional outbox kết hợp message broker:

1. Trong cùng transaction nghiệp vụ, lưu thay đổi dữ liệu và một bản ghi outbox.
2. Một tiến trình đọc outbox và gửi message đến broker.
3. Consumer xử lý message, có retry và ghi nhận trạng thái.
4. Consumer cần idempotent vì message có thể được giao lại.

Outbox và broker giải quyết bài toán độ bền, retry và giao tiếp liên tiến trình. Chúng có chi phí vận hành riêng; không cần đưa vào một ứng dụng nhỏ chỉ có vài phản ứng nội bộ không quan trọng.

## 6. Bảng quyết định

| Câu hỏi | Gọi phương thức trực tiếp | Dùng event |
|---|---|---|
| Bên gọi có cần kết quả không? | Có | Không cần kết quả từ listener |
| Công việc có bắt buộc để hoàn thành use case không? | Thường có | Thường là phản ứng độc lập |
| Có nhiều thành phần quan tâm không? | Bên gọi phải điều phối từng thành phần | Publisher chỉ phát một sự kiện |
| Có cần kiểm soát thứ tự chính xác không? | Dễ thể hiện bằng lời gọi | Cần thiết kế thứ tự/điều phối riêng |
| Bên gọi có cần nhận lỗi ngay không? | Có thể nhận trực tiếp | Phụ thuộc listener đồng bộ hay async |
| Cần xử lý sau commit? | Có thể gọi sau khi transaction hoàn tất | Dùng @TransactionalEventListener |
| Cần bảo đảm giao nhận qua sự cố tiến trình? | Cần cơ chế bền vững riêng | Cần outbox/broker; event nội bộ đơn thuần chưa đủ |

## 7. Những lỗi thiết kế thường gặp

**Dùng event để thay một lời gọi cần kết quả.** Ví dụ, phát PriceCalculationRequested rồi chờ một listener tính giá để tiếp tục đặt hàng. Publisher không có hợp đồng trả kết quả tự nhiên. Hãy gọi một service hoặc interface trực tiếp.

**Nghĩ rằng event luôn chạy nền.** @EventListener mặc định đồng bộ. Nếu cần async, phải cấu hình rõ executor và xử lý lỗi.

**Gửi event trước commit rồi thực hiện tác dụng phụ không thể thu hồi.** Ví dụ, gửi email xác nhận ngay trong listener đồng bộ, sau đó transaction rollback. Hãy xác định thời điểm nghiệp vụ phù hợp; AFTER_COMMIT thường thích hợp hơn cho phản ứng chỉ được thực hiện khi dữ liệu đã commit.

**Cho rằng AFTER_COMMIT bảo đảm không mất công việc.** Listener chỉ chạy sau commit, nhưng sự cố tiến trình vẫn có thể làm mất tác dụng phụ. Với công việc bắt buộc, dùng outbox hoặc một cơ chế lưu bền có retry.

**Đưa entity mutable hoặc quá nhiều dữ liệu vào event.** Điều này khiến listener phụ thuộc vào trạng thái nội bộ và có thể đọc dữ liệu đã thay đổi. Ưu tiên event bất biến, chứa ID và snapshot tối thiểu cần thiết. Listener có thể tải dữ liệu đã commit nếu cần.

**Tạo event cho mọi thao tác nhỏ.** Quá nhiều event khiến luồng điều khiển bị phân tán và khó truy vết. Chỉ phát event khi có một sự việc có ý nghĩa và có bên khác thực sự cần quan tâm.

**Dùng event để điều phối một chuỗi bước bắt buộc.** Nếu bước B phải chạy sau A, bước C phải dùng kết quả B và cả quy trình phải trả một kết quả thống nhất, hãy dùng service điều phối với các lời gọi rõ ràng. Event phù hợp hơn cho những phản ứng độc lập sau sự việc.

## 8. Quy tắc chọn nhanh

Hãy tự hỏi ba câu:

1. Bên gọi có cần câu trả lời hoặc kết quả của thao tác kia để quyết định bước tiếp theo không? Nếu có, gọi phương thức trực tiếp.
2. Công việc kia có phải bước bắt buộc của cùng use case và lỗi của nó phải được xử lý ngay không? Nếu có, ưu tiên lời gọi trực tiếp.
3. Nếu chỉ thông báo một sự việc đã xảy ra và một hoặc nhiều thành phần có thể tự phản ứng mà publisher không cần biết kết quả, event là lựa chọn phù hợp.

Khi đã chọn event, tiếp tục xác định listener chạy đồng bộ hay bất đồng bộ, chạy ở phase transaction nào và mức bảo đảm giao nhận cần thiết. Đây là các quyết định riêng; chỉ thêm async hoặc outbox khi yêu cầu thực tế cần chúng.

**Ghi nhớ:** dùng lời gọi trực tiếp để yêu cầu một hành động và nhận kết quả; dùng event để thông báo một sự việc và cho phép các bên quan tâm tự phản ứng.
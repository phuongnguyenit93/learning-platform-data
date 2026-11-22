# Phát sự kiện sau commit bằng transaction synchronization

Trong một ứng dụng Spring, việc tạo đơn hàng, cập nhật tài khoản hoặc xác nhận thanh toán thường được thực hiện trong một **database transaction**. Sau khi dữ liệu được ghi thành công, ứng dụng có thể cần gửi email thông báo cho người dùng. Nếu gửi email ngay giữa transaction, có một tình huống không mong muốn: SMTP đã nhận thư nhưng transaction database sau đó rollback. Người nhận nhận được thông báo về một thay đổi chưa từng được commit.

Một cách xử lý là **đăng ký công việc chỉ chạy sau khi transaction commit thành công**. Spring cung cấp cơ chế **transaction synchronization** để gắn callback vào vòng đời transaction. Với callback **afterCommit()**, ứng dụng có thể gửi email sau khi database transaction đã commit. Ở tầng ứng dụng cao hơn, **@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)** cho phép phát một application event trong transaction và xử lý event sau commit.

Chủ đề này tập trung vào cách dùng transaction synchronization để trì hoãn hành động gửi email tới sau commit, cách lựa chọn giữa callback trực tiếp và transactional event listener, các giới hạn về lỗi và tính tin cậy, cùng hướng mở rộng bằng **transactional outbox** khi email quan trọng cần retry bền vững.

## 1. Vì sao cần phát sự kiện sau commit?

Giả sử người dùng đặt hàng. Ứng dụng cần:

1. Tạo bản ghi đơn hàng.
2. Trừ hoặc giữ tồn kho.
3. Lưu thông tin thanh toán.
4. Gửi email xác nhận đơn hàng.

Các thay đổi database cần nhất quán với nhau. Nếu một bước thất bại, transaction có thể rollback để database trở lại trạng thái trước đó.

### Gửi email trước khi transaction hoàn tất

~~~text
BEGIN TRANSACTION
    |
    v
Lưu đơn hàng
    |
    v
Gửi email xác nhận -----> SMTP đã nhận thư
    |
    v
Cập nhật tồn kho
    |
    v
Lỗi khi cập nhật tồn kho
    |
    v
ROLLBACK

Kết quả:
Database không có đơn hàng đã commit,
nhưng người dùng đã nhận email xác nhận.
~~~

Email là một tác động bên ngoài database. Database rollback không thể thu hồi email mà SMTP server đã nhận. Đây là một dạng **dual-write problem**: cùng một luồng nghiệp vụ ghi vào hai hệ thống độc lập nhưng không có một transaction phân tán chung bảo đảm cả hai cùng thành công hoặc cùng thất bại.

### Chờ commit rồi mới gửi

~~~text
BEGIN TRANSACTION
    |
    v
Lưu đơn hàng
    |
    v
Cập nhật tồn kho
    |
    v
Đăng ký callback afterCommit
    |
    v
COMMIT thành công
    |
    v
Callback afterCommit
    |
    v
Gửi email qua JavaMailSender
~~~

Nếu transaction rollback, callback **afterCommit()** không chạy. Nếu commit thành công, callback mới được thực hiện. Nhờ vậy, email xác nhận chỉ được gửi sau khi thay đổi database đã được commit.

Điều này giải quyết vấn đề **gửi thông báo cho một giao dịch đã rollback**. Nó không làm cho SMTP trở thành một phần của database transaction và cũng không bảo đảm email chắc chắn tới Inbox. Các giới hạn đó cần được xử lý riêng.

## 2. Transaction synchronization trong Spring là gì?

**Transaction synchronization** là cơ chế cho phép thành phần ứng dụng đăng ký các hành động gắn với vòng đời của transaction hiện tại. Spring transaction manager quản lý các synchronization đã đăng ký và gọi callback tại những thời điểm tương ứng.

Một số callback quan trọng:

| Callback | Thời điểm | Trường hợp sử dụng |
| --- | --- | --- |
| **beforeCommit(readOnly)** | Trước khi transaction commit | Chuẩn bị/kiểm tra công việc cần hoàn tất trước commit |
| **beforeCompletion()** | Trước khi transaction kết thúc, dù commit hay rollback | Dọn dẹp tài nguyên |
| **afterCommit()** | Sau khi commit thành công | Gửi thông báo, gọi dịch vụ bên ngoài sau khi dữ liệu đã commit |
| **afterCompletion(status)** | Sau khi transaction hoàn tất, dù commit hay rollback | Dọn dẹp hoặc ghi nhận kết quả cuối cùng |

Các callback có ý nghĩa khác nhau. Nếu cần gửi email xác nhận một thay đổi đã lưu thành công, **afterCommit()** là thời điểm phù hợp. **beforeCommit()** vẫn có thể được theo sau bởi rollback, vì vậy không nên gửi email thành công ở callback này.

### TransactionSynchronizationManager

Spring cung cấp **TransactionSynchronizationManager** để quản lý synchronization và một số thông tin transaction gắn với execution context hiện tại.

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| **isSynchronizationActive()** | Kiểm tra synchronization hiện tại có đang được kích hoạt không |
| **isActualTransactionActive()** | Kiểm tra có transaction thực sự đang hoạt động không |
| **registerSynchronization(...)** | Đăng ký một TransactionSynchronization vào transaction context hiện tại |
| **getSynchronizations()** | Lấy danh sách synchronization đã đăng ký, chủ yếu phục vụ quan sát/kiểm tra |
| **getCurrentTransactionName()** | Lấy tên transaction hiện tại nếu có |
| **isCurrentTransactionReadOnly()** | Kiểm tra transaction hiện tại có được đánh dấu read-only không |

Hai phương thức **isSynchronizationActive()** và **isActualTransactionActive()** không có cùng ý nghĩa:

- Synchronization có thể được kích hoạt theo cấu hình transaction manager ngay cả khi không có một transaction thực sự.
- Một transaction thực sự đang hoạt động là điều kiện nghiệp vụ mà luồng gửi mail sau commit thường cần.
- **registerSynchronization(...)** yêu cầu synchronization đang active; nếu không, Spring sẽ ném IllegalStateException.

Trong ví dụ gửi email, nên kiểm tra cả hai trạng thái nếu phương thức yêu cầu phải được gọi bên trong một transaction thật.

## 3. Đăng ký callback afterCommit trực tiếp

Giả sử một service tạo đơn hàng trong transaction. Sau khi lưu dữ liệu, service đăng ký callback để gửi email:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderMailService orderMailService;

    public OrderService(
            OrderRepository orderRepository,
            OrderMailService orderMailService
    ) {
        this.orderRepository = orderRepository;
        this.orderMailService = orderMailService;
    }

    @Transactional
    public Order placeOrder(CreateOrderCommand command) {
        if (!TransactionSynchronizationManager
                .isSynchronizationActive()
                || !TransactionSynchronizationManager
                .isActualTransactionActive()) {
            throw new IllegalStateException(
                    "placeOrder phải chạy trong một transaction đang hoạt động"
            );
        }

        Order order = Order.create(command);
        Order savedOrder = orderRepository.save(order);

        OrderPlacedEvent event = new OrderPlacedEvent(
                savedOrder.getId(),
                savedOrder.getOrderNumber(),
                savedOrder.getCustomerEmail()
        );

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        orderMailService.sendOrderConfirmation(event);
                    }
                }
        );

        return savedOrder;
    }
}
~~~

**TransactionSynchronization** là interface Spring dùng để nhận các callback. Ví dụ chỉ override **afterCommit()**; các callback khác giữ hành vi mặc định của phiên bản Spring hiện đại.

Luồng hoạt động:

1. Spring mở transaction khi gọi phương thức có **@Transactional** qua transaction proxy.
2. Repository lưu đơn hàng trong transaction hiện tại.
3. Service đăng ký callback với **TransactionSynchronizationManager**.
4. Nếu phương thức kết thúc bình thường và transaction commit thành công, Spring gọi **afterCommit()**.
5. Callback gọi **OrderMailService**, service này tạo và gửi email.
6. Nếu transaction rollback, callback afterCommit không được gọi.

### Tại sao kiểm tra synchronization và actual transaction?

Nếu service có thể được gọi từ nhiều đường đi, việc kiểm tra giúp phát hiện trường hợp phương thức không chạy trong transaction như mong muốn. Nếu synchronization không active, không thể đăng ký callback. Nếu không có transaction thực sự, callback không thể bảo đảm ý nghĩa “sau khi database commit”.

Một lựa chọn khác là coi transaction là điều kiện bắt buộc trong thiết kế và chỉ gọi service từ một phương thức transactional đã được kiểm soát. Dù chọn cách nào, cần hiểu rõ transaction manager và propagation đang dùng.

### Dùng dữ liệu event bất biến

Trong ví dụ, callback giữ một object **OrderPlacedEvent** chứa ID, mã đơn và địa chỉ email. Đây là dữ liệu đã được lấy trong transaction.

Có thể định nghĩa:

~~~java
public record OrderPlacedEvent(
        Long orderId,
        String orderNumber,
        String recipientEmail
) {
}
~~~

Nên giữ dữ liệu callback nhỏ và ổn định. Tránh giữ một entity JPA có quan hệ lazy-loading rồi truy cập nó sau commit, vì persistence context có thể đã kết thúc hoặc session không còn ở trạng thái phù hợp. Nếu callback cần thông tin mới nhất, giữ ID và đọc lại bằng một transaction/service phù hợp.

### Không gọi callback thủ công

Không nên tự gọi **afterCommit()** từ service để giả lập transaction đã commit. Callback thuộc quyền điều phối của transaction manager. Chỉ đăng ký synchronization; Spring sẽ gọi callback ở đúng thời điểm.

## 4. Dùng @TransactionalEventListener với AFTER_COMMIT

Đăng ký callback trực tiếp phù hợp khi một service cần một hành động gắn chặt với transaction. Nếu muốn tách nghiệp vụ tạo đơn khỏi cách gửi email, có thể dùng **Spring application event** kết hợp **@TransactionalEventListener**.

Service phát event trong transaction:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher eventPublisher
    ) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Order placeOrder(CreateOrderCommand command) {
        Order savedOrder = orderRepository.save(Order.create(command));

        eventPublisher.publishEvent(
                new OrderPlacedEvent(
                        savedOrder.getId(),
                        savedOrder.getOrderNumber(),
                        savedOrder.getCustomerEmail()
                )
        );

        return savedOrder;
    }
}
~~~

Listener nhận event sau commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderMailEventListener {

    private final OrderMailService orderMailService;

    public OrderMailEventListener(OrderMailService orderMailService) {
        this.orderMailService = orderMailService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlacedEvent event) {
        orderMailService.sendOrderConfirmation(event);
    }
}
~~~

Spring đăng ký listener với transaction synchronization. Khi transaction commit thành công, listener được gọi; nếu transaction rollback, listener ở phase AFTER_COMMIT không chạy.

### Event được publish chưa có nghĩa listener chạy ngay

**ApplicationEventPublisher.publishEvent(...)** phát event trong ứng dụng. Với listener thông thường **@EventListener**, listener thường được gọi đồng bộ ngay trong quá trình publish (trừ khi cấu hình async). Với **@TransactionalEventListener**, Spring gắn việc xử lý listener vào transaction phase đã chọn.

Luồng:

~~~text
@Transactional placeOrder()
        |
        v
repository.save(order)
        |
        v
publishEvent(OrderPlacedEvent)
        |
        v
TransactionalEventListener đăng ký synchronization
        |
        +------ transaction rollback
        |             |
        |             v
        |       AFTER_COMMIT không chạy
        |
        '-- transaction commit
                      |
                      v
              AFTER_COMMIT listener
                      |
                      v
                 Gửi email
~~~

Việc publish event có thể diễn ra trước khi transaction kết thúc. Chính **phase** của listener quyết định khi nào xử lý. Vì vậy, event có thể được publish nhưng không có listener AFTER_COMMIT nào được gọi nếu transaction rollback.

### Các phase có thể chọn

| Phase | Khi nào listener chạy? | Ví dụ |
| --- | --- | --- |
| **BEFORE_COMMIT** | Trước khi transaction commit | Công việc cần thực hiện trong giai đoạn trước commit |
| **AFTER_COMMIT** | Sau commit thành công | Gửi email xác nhận, thông báo thay đổi đã lưu |
| **AFTER_ROLLBACK** | Sau khi rollback | Ghi nhận hoặc phát thông báo về giao dịch thất bại |
| **AFTER_COMPLETION** | Sau khi transaction kết thúc, dù commit hay rollback | Dọn dẹp hoặc tác vụ không phụ thuộc kết quả |

Nếu không khai báo phase, **AFTER_COMMIT** là phase mặc định của TransactionalEventListener. Với email xác nhận thành công, nên ghi rõ phase trong annotation để ý định được đọc ngay tại listener.

Không gửi email “đơn hàng đã được tạo” ở **BEFORE_COMMIT** vì commit vẫn có thể thất bại sau callback đó. Với **AFTER_COMPLETION**, phải kiểm tra trạng thái completion trước khi gửi thông báo thành công; callback này chạy cả khi rollback.

## 5. Hành vi khi không có transaction

Mặc định, **@TransactionalEventListener** chỉ xử lý event khi có transaction đang hoạt động và listener có thể được gắn vào transaction đó. Nếu event được publish ngoài transaction, listener mặc định không được thực thi.

Thuộc tính **fallbackExecution** thay đổi hành vi này:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void onOrderPlaced(OrderPlacedEvent event) {
    orderMailService.sendOrderConfirmation(event);
}
~~~

Khi không có transaction để đồng bộ, **fallbackExecution = true** cho phép listener chạy theo cách xử lý event thông thường. Điều đó có nghĩa listener có thể chạy ngay khi event được publish mà không có một commit đứng trước nó.

Vì vậy:

- Giữ mặc định **fallbackExecution = false** nếu yêu cầu bắt buộc là “chỉ gửi sau commit”.
- Chỉ bật fallback khi nghiệp vụ chấp nhận chạy listener cả trong trường hợp không có transaction.
- Nếu phương thức phát event đôi khi có transaction và đôi khi không, cần làm rõ hợp đồng của từng luồng gọi.

Không nên bật fallback chỉ để tránh event bị bỏ qua. Nếu event quan trọng phải gắn với transaction, hãy bảo đảm publisher được gọi trong transaction đúng.

## 6. So sánh callback trực tiếp và transactional event listener

Hai cách cùng dựa trên transaction synchronization, nhưng thể hiện ý định ở các tầng khác nhau.

| Tiêu chí | TransactionSynchronization trực tiếp | @TransactionalEventListener |
| --- | --- | --- |
| Cách đăng ký | Gọi registerSynchronization(...) | Publish application event |
| Mức trừu tượng | Thấp, gắn trực tiếp với transaction | Cao hơn, hướng theo sự kiện nghiệp vụ |
| Phụ thuộc transaction | Cần synchronization active | Listener gắn vào transaction khi event được publish trong transaction |
| Tách biệt publisher và handler | Thường callback được đăng ký ngay trong service | Publisher không cần biết listener gửi mail |
| Nhiều listener | Phải tự điều phối hoặc đăng ký nhiều callback | Có thể có nhiều listener cùng nhận event |
| Dễ đọc nghiệp vụ | Phù hợp tác vụ nhỏ gắn trực tiếp transaction | Phù hợp sự kiện như OrderPlaced, PaymentCaptured |
| Kiểm soát phase | Override callback cần thiết | Chọn phase trong annotation |

### Khi nào nên dùng callback trực tiếp?

Chọn **TransactionSynchronizationManager.registerSynchronization(...)** khi:

- Chỉ cần một hành động kỹ thuật nhỏ gắn với transaction hiện tại.
- Không cần phát một sự kiện nghiệp vụ cho nhiều thành phần.
- Thành phần đăng ký đã hiểu rõ vòng đời transaction.
- Muốn kiểm soát callback cụ thể, ví dụ afterCommit hoặc afterCompletion.

Ví dụ: sau commit, xóa một cache cục bộ liên quan tới dữ liệu vừa cập nhật, hoặc gọi một adapter nhỏ gửi thông báo.

### Khi nào nên dùng @TransactionalEventListener?

Chọn **@TransactionalEventListener** khi:

- Có một sự kiện nghiệp vụ rõ ràng như OrderPlaced hoặc AccountActivated.
- Publisher không nên phụ thuộc vào mail service.
- Nhiều handler có thể phản ứng sau commit: gửi email, ghi audit ngoài database, cập nhật chỉ mục tìm kiếm.
- Muốn chọn transaction phase bằng annotation.

Ví dụ: service tạo đơn phát OrderPlacedEvent; listener email gửi xác nhận, listener khác cập nhật hệ thống thông báo.

### Không đăng ký cả hai cho cùng một email

Nếu vừa gọi callback trực tiếp để gửi email vừa publish event có listener gửi cùng email, người nhận có thể nhận hai thư. Chọn một điểm chịu trách nhiệm gửi cho mỗi sự kiện nghiệp vụ, và kiểm soát listener/handler được đăng ký trong ứng dụng.

## 7. Tích hợp với JavaMailSender

Listener sau commit có thể gọi một service gửi thư thông thường. Service này chịu trách nhiệm tạo MIME message và gửi bằng **JavaMailSender**.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmation(OrderPlacedEvent event) {
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");

            helper.setFrom("orders@example.test");
            helper.setTo(event.recipientEmail());
            helper.setSubject(
                    "Xác nhận đơn hàng " + event.orderNumber()
            );
            helper.setText(
                    "Đơn hàng " + event.orderNumber()
                            + " đã được tạo thành công."
            );

            mailSender.send(message);
        } catch (MessagingException ex) {
            throw new OrderMailException(
                    "Không thể tạo email xác nhận cho đơn hàng "
                            + event.orderNumber(),
                    ex
            );
        }
    }
}
~~~

Ví dụ exception nghiệp vụ:

~~~java
public class OrderMailException extends RuntimeException {

    public OrderMailException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Trong ứng dụng thực tế, nên dùng template HTML/plain text và mail model đã chuẩn hóa. Phần quan trọng ở đây là **OrderMailService không tự mở transaction để tạo đơn**; nó chỉ được gọi từ listener sau khi transaction tạo đơn đã commit.

### Địa chỉ email và nội dung nên lấy từ đâu?

Có hai cách thường gặp:

- Event mang các giá trị đã xác định trong transaction, ví dụ order ID, order number và email người nhận tại thời điểm tạo đơn.
- Event chỉ mang ID; listener gọi một service để tải dữ liệu mới nhất sau commit.

Chọn theo yêu cầu nghiệp vụ. Nếu email phải phản ánh đúng địa chỉ nhận thư tại thời điểm đặt hàng, lưu snapshot đó trong event hoặc dữ liệu đơn hàng. Nếu phải dùng địa chỉ hiện tại của tài khoản, listener có thể đọc lại. Không nên truyền một JPA entity có lazy relationship vào event rồi kỳ vọng mọi thuộc tính còn truy cập được sau commit.
## 8. Điều gì xảy ra nếu gửi email thất bại sau commit?

Đây là điểm cần hiểu rõ nhất khi dùng afterCommit.

Khi callback **afterCommit()** được gọi, database transaction đã commit thành công. Nếu SMTP timeout, server từ chối thư hoặc JavaMailSender ném exception, **database không tự rollback lại**. Một transaction đã commit không thể được hoàn tác bằng cách ném exception từ callback sau commit.

Ví dụ:

~~~text
Database transaction
    |
    v
COMMIT thành công
    |
    v
afterCommit()
    |
    v
JavaMailSender.send(...)
    |
    +---- SMTP thành công
    |          |
    |          v
    |      Email đã được SMTP chấp nhận
    |
    '-- SMTP lỗi
               |
               v
          Exception/log

Database vẫn ở trạng thái đã commit.
~~~

### Exception từ afterCommit không có nghĩa transaction rollback

Spring cho phép exception phát sinh từ callback **afterCommit()** được truyền lên caller trong một số luồng thực thi đồng bộ. Người gọi có thể nhìn thấy lỗi dù database đã commit. Điều đó dễ gây hiểu nhầm nếu API chỉ trả về một lỗi chung như “đặt hàng thất bại”.

Ví dụ:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    // Lưu đơn hàng và đăng ký afterCommit.
    // Nếu SMTP lỗi trong afterCommit, caller có thể nhận exception.
    // Nhưng đơn hàng đã commit vẫn tồn tại trong database.
}
~~~

Vì vậy, cần phân biệt:

- **Business transaction failed**: database không commit.
- **Post-commit action failed**: database đã commit, nhưng gửi mail hoặc một tác vụ tiếp theo thất bại.

Không nên trả về thông báo “đơn hàng chưa được tạo” chỉ vì gửi email thất bại sau commit. Hãy ghi nhận trạng thái gửi mail riêng, cung cấp mã đơn hàng đã tạo và có chiến lược retry hoặc xử lý lại.

### Xử lý exception trong callback

Nếu dùng callback trực tiếp, có thể bắt exception để log và chuyển cho cơ chế giám sát:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                try {
                    orderMailService.sendOrderConfirmation(event);
                } catch (OrderMailException ex) {
                    log.error(
                            "Đơn hàng {} đã commit nhưng gửi email thất bại",
                            event.orderNumber(),
                            ex
                    );
                    mailFailureRecorder.record(event, ex);
                }
            }
        }
);
~~~

Đây là ví dụ xử lý lỗi; **mailFailureRecorder** cần được thiết kế phù hợp với yêu cầu lưu trạng thái và retry. Nếu recorder ghi database, cần chú ý quy tắc transaction mới ở phần tiếp theo. Chỉ log lỗi có thể đủ cho email ít quan trọng, nhưng không đủ nếu hệ thống phải bảo đảm có thể gửi lại.

Với transactional event listener, cũng nên có xử lý exception/giám sát rõ ràng. Không để một lỗi SMTP bị hiểu nhầm thành rollback của nghiệp vụ đã hoàn tất.

### SMTP accept không đồng nghĩa người nhận đã đọc

Nếu JavaMailSender.send(...) trả về thành công, điều đó thường cho biết transport đã hoàn thành bước gửi/nộp message theo hợp đồng của nó. Nó không chứng minh email đã vào Inbox, không bị bounce và người nhận đã đọc. Theo dõi delivery/bounce cần cơ chế của mail provider.

## 9. Ghi database trong afterCommit và REQUIRES_NEW

Sau commit, callback có thể vẫn được gọi trong lúc transaction resources còn được bind với thread. Tùy transaction manager, connection hoặc persistence resources có thể vẫn truy cập được trong giai đoạn callback, nhưng transaction gốc **đã hoàn tất và không còn commit lần nữa**.

Điều này tạo ra một tình huống dễ nhầm: callback afterCommit gọi repository.save(...), lệnh có thể tham gia resource còn đang bind nhưng không được commit như một transaction mới độc lập.

Nếu callback cần ghi trạng thái gửi email, hãy dùng một transaction riêng:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MailStatusService {

    private final MailStatusRepository repository;

    public MailStatusService(MailStatusRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markSent(Long orderId) {
        repository.markMailSent(orderId);
    }
}
~~~

**REQUIRES_NEW** yêu cầu Spring mở một transaction độc lập cho thao tác này. Transaction đó có thể commit riêng, không phụ thuộc transaction tạo đơn đã kết thúc.

### Phải gọi qua Spring proxy

Để propagation **REQUIRES_NEW** có hiệu lực theo cơ chế proxy thông thường, phương thức cần được gọi qua Spring bean proxy. Gọi một phương thức REQUIRES_NEW bằng self-invocation bên trong cùng object thường không đi qua proxy nên annotation có thể không được áp dụng.

Ví dụ tách **MailStatusService** thành bean riêng giúp lời gọi từ listener đi qua proxy. Cũng có thể dùng các cơ chế transaction khác, nhưng cần bảo đảm propagation thực sự được kích hoạt.

### Không dùng REQUIRES_NEW cho mọi thao tác một cách máy móc

Chỉ dùng transaction mới khi callback cần ghi database độc lập sau commit. Nếu callback chỉ gửi email qua SMTP, không cần mở một database transaction mới chỉ để gọi JavaMailSender.

Nếu ghi nhận trạng thái gửi, nên xác định rõ thứ tự:

1. Gửi message.
2. Nếu transport báo thành công, ghi trạng thái đã nộp.
3. Nếu gửi thất bại, ghi trạng thái lỗi và thông tin retry.

Thứ tự này vẫn có một cửa sổ lỗi: SMTP có thể đã nhận thư nhưng ứng dụng chết trước khi ghi trạng thái. Khi retry, email có thể được gửi trùng. Transaction outbox và idempotency giúp kiểm soát tốt hơn, nhưng email qua SMTP nói chung không có bảo đảm exactly-once.

## 10. Chạy tác vụ sau commit bất đồng bộ

Callback afterCommit chạy đồng bộ theo luồng thực thi transaction nếu không có cơ chế async. Nếu gửi mail mất vài giây, request tạo đơn có thể phải chờ callback hoàn tất.

Một cách là kết hợp transactional event listener với **@Async**:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AsyncOrderMailListener {

    private final OrderMailService orderMailService;

    public AsyncOrderMailListener(OrderMailService orderMailService) {
        this.orderMailService = orderMailService;
    }

    @Async("mailExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlacedEvent event) {
        orderMailService.sendOrderConfirmation(event);
    }
}
~~~

Ứng dụng cần bật async execution và cấu hình executor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import java.util.concurrent.Executor;

@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailExecutor")
    public Executor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("mail-");
        executor.initialize();
        return executor;
    }
}
~~~

Transactional event listener được gắn với transaction phase; khi phase AFTER_COMMIT tới, lời gọi listener có thể được chuyển sang executor nhờ @Async. Cấu hình thực tế nên quản lý pool size, queue capacity, shutdown và rejection policy theo tải của ứng dụng.

### Async không tự bảo đảm retry

Khi dùng @Async:

- Transaction đã commit trước khi listener được xử lý.
- Công việc chạy trên thread executor; transaction context của thread gốc không tự truyền sang thread mới.
- Exception không được trả trực tiếp cho HTTP request đã kết thúc.
- Nếu queue đầy, executor shutdown hoặc process dừng đột ngột, tác vụ có thể thất bại hoặc mất nếu không có hàng đợi bền vững.
- Cần cấu hình logging, metrics và xử lý exception cho async task.

Nếu email có mức độ quan trọng cao, một executor trong bộ nhớ không thay thế được durable queue hoặc transactional outbox.

### Không truyền transaction-bound resource sang async thread

Không truyền JDBC Connection, EntityManager đang được bind theo transaction hoặc JPA entity có lazy relationship sang async task. Hãy truyền event bất biến chứa ID và dữ liệu cần thiết. Nếu worker cần truy vấn database, nó mở transaction mới trong thread của nó.

## 11. Transaction propagation và thời điểm callback

Thời điểm callback phụ thuộc transaction thực tế mà synchronization được gắn vào.

### Propagation REQUIRED

**REQUIRED** là mặc định của @Transactional. Nếu đã có transaction, phương thức tham gia transaction đó; nếu chưa có, Spring tạo transaction mới.

~~~text
Outer @Transactional
    |
    +-- OrderService.placeOrder() REQUIRED
    |       |
    |       +-- save order
    |       '-- register afterCommit
    |
    +-- OtherService.updateInventory() REQUIRED
    |
    v
Outer transaction COMMIT
    |
    v
Callback afterCommit chạy
~~~

Nếu nhiều phương thức REQUIRED cùng tham gia một transaction, callback được gọi khi transaction vật lý cuối cùng commit, không phải ngay khi một phương thức con kết thúc.

### Propagation REQUIRES_NEW

**REQUIRES_NEW** tạm ngưng transaction bên ngoài và mở một transaction độc lập:

~~~text
Outer transaction
    |
    +-- gọi inner method REQUIRES_NEW
    |       |
    |       v
    |   Inner transaction
    |       |
    |       +-- register callback
    |       |
    |       v
    |   Inner COMMIT
    |       |
    |       v
    |   Inner afterCommit callback
    |
    v
Outer tiếp tục
    |
    v
Outer ROLLBACK
~~~

Callback của transaction REQUIRES_NEW có thể chạy sau khi transaction bên trong commit thành công, ngay cả khi transaction bên ngoài sau đó rollback. Điều này có thể đúng nếu nghiệp vụ của transaction bên trong độc lập; nếu email xác nhận phụ thuộc toàn bộ giao dịch bên ngoài, không nên vô tình đăng ký callback vào một transaction độc lập như vậy.

### Transaction lồng nhau hoặc savepoint

Với **NESTED** hoặc savepoint, callback synchronization thường gắn với transaction vật lý bên ngoài. Việc một scope lồng nhau kết thúc không đồng nghĩa toàn bộ transaction đã commit. Nếu savepoint rollback, không nên kỳ vọng afterCommit chạy tại thời điểm đó.

Hành vi chi tiết phụ thuộc transaction manager và loại resource. Khi dùng nested transaction, hãy kiểm tra cách transaction manager hỗ trợ savepoint và thời điểm completion thực tế.

### Gọi phương thức transactional qua self-invocation

Trong proxy mode mặc định, Spring áp dụng @Transactional khi lời gọi đi qua proxy. Nếu một phương thức trong cùng class gọi trực tiếp phương thức khác có @Transactional, annotation của phương thức được gọi có thể không được áp dụng.

Ví dụ:

~~~java
public void submit() {
    this.placeOrder(); // lời gọi nội bộ, thường không qua proxy
}

@Transactional
public void placeOrder() {
    // Không nên mặc định rằng transaction proxy đã mở transaction ở đây.
}
~~~

Nếu transaction không được mở, event listener AFTER_COMMIT có thể không được đăng ký hoặc callback trực tiếp không có synchronization để sử dụng. Hãy gọi qua Spring bean proxy, đặt transaction ở phương thức public được gọi từ bên ngoài bean, hoặc dùng cấu trúc bean phù hợp với ứng dụng.

## 12. Giới hạn của callback trong bộ nhớ và transactional outbox

Callback afterCommit và **@TransactionalEventListener** giúp tránh gửi email cho transaction rollback. Tuy nhiên, callback được đăng ký trong bộ nhớ của process. Có một cửa sổ rủi ro:

~~~text
Database COMMIT thành công
        |
        v
Process bị dừng đột ngột
        |
        v
Callback chưa kịp chạy
        |
        v
Không có email và cũng không có bản ghi bền vững
để worker biết cần gửi lại.
~~~

Nếu process chết sau commit nhưng trước khi callback hoàn tất, event trong bộ nhớ có thể mất. Đây là giới hạn của cơ chế callback trực tiếp và transactional event listener khi dùng như cơ chế gửi thông báo duy nhất.

Với email quan trọng, có thể dùng **transactional outbox**. Ý tưởng là lưu một bản ghi outbox trong cùng database transaction với thay đổi nghiệp vụ. Vì cả hai cùng commit hoặc rollback, hệ thống có một dấu vết bền vững cho công việc cần xử lý.

### Cấu trúc outbox

Một bảng outbox đơn giản có thể gồm:

| Cột | Ý nghĩa |
| --- | --- |
| **id** | ID duy nhất của event |
| **aggregate_id** | ID đơn hàng/tài khoản liên quan |
| **event_type** | Loại sự kiện, ví dụ ORDER_PLACED |
| **payload** | Dữ liệu cần thiết để xử lý event |
| **status** | PENDING, PROCESSING, SENT hoặc FAILED |
| **attempts** | Số lần thử gửi |
| **next_attempt_at** | Thời điểm được phép thử lại |
| **created_at** | Thời điểm tạo event |
| **sent_at** | Thời điểm transport chấp nhận gửi |
| **last_error** | Lỗi gần nhất đã ghi nhận |

Transaction nghiệp vụ ghi cả đơn hàng và outbox row:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.create(command));

    outboxRepository.save(
            OutboxMessage.pending(
                    "ORDER_PLACED",
                    order.getId(),
                    serializeOrderPlaced(order)
            )
    );

    return order;
}
~~~

Nếu transaction rollback, cả đơn hàng và outbox row đều rollback. Nếu commit, cả hai đều tồn tại. Worker có thể đọc các bản ghi PENDING để gửi email sau đó.

### Worker xử lý outbox

~~~text
Business transaction
    |
    +--> Save Order
    |
    '--> Save OutboxMessage(PENDING)
             |
             v
           COMMIT
             |
             v
       Outbox worker polls
             |
             v
       Claim pending event
             |
             v
       Render and send email
             |
        +----+----+
        |         |
      Success    Failure
        |         |
        v         v
      SENT     Retry/backoff
                  |
                  v
               FAILED
               after limit
~~~

Worker nên claim bản ghi bằng cơ chế chống nhiều worker xử lý cùng lúc, ví dụ trạng thái PROCESSING với lease timeout, optimistic locking hoặc câu lệnh database phù hợp như **FOR UPDATE SKIP LOCKED** nếu hệ quản trị hỗ trợ. Không giữ database transaction mở trong lúc chờ SMTP lâu hơn mức cần thiết.

### Outbox không tự tạo exactly-once delivery

Giả sử SMTP đã nhận email nhưng process chết trước khi worker cập nhật outbox thành SENT. Khi worker chạy lại, bản ghi vẫn có thể được xem là chưa gửi và email bị gửi lần nữa.

Do đó, outbox thường cung cấp khả năng **at-least-once processing**: event được thử lại cho tới khi hoàn tất hoặc chuyển trạng thái lỗi theo chính sách. Để giảm email trùng:

- Gắn event ID duy nhất vào outbox record.
- Ghi nhận idempotency key ở hệ thống nhận nếu provider hỗ trợ.
- Kiểm soát việc claim event để không có nhiều worker gửi cùng lúc.
- Lưu trạng thái và số lần retry.
- Chấp nhận và thiết kế cho khả năng duplicate nếu SMTP không cung cấp idempotency phù hợp.

Không nên tuyên bố email được gửi exactly-once chỉ vì có outbox. Việc SMTP accept và việc cập nhật database không nằm trong một transaction nguyên tử chung.

### Khi nào callback afterCommit là đủ?

Callback trực tiếp hoặc transactional event listener phù hợp khi:

- Email chỉ là thông báo tiện ích, có thể chấp nhận mất hiếm gặp.
- Hệ thống có cơ chế giám sát và người vận hành có thể gửi lại thủ công.
- Tải thấp và việc gửi ngay sau commit quan trọng hơn hàng đợi bền vững.
- Tác vụ sau commit không cần retry dài hạn.

Outbox phù hợp khi:

- Email liên quan giao dịch quan trọng như thanh toán, hóa đơn, kích hoạt tài khoản.
- Không được mất sự kiện chỉ vì process restart.
- Cần retry tự động, quan sát trạng thái và điều tra lịch sử gửi.
- Có nhiều worker hoặc nhiều instance ứng dụng.

## 13. Kiểm thử hành vi sau commit

Test cần chứng minh callback chỉ chạy sau commit và không chạy khi rollback. Có thể dùng **TransactionTemplate** để chủ động kiểm soát transaction trong integration test.

Ví dụ minh họa:

~~~java
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

class OrderMailAfterCommitTest {

    private final PlatformTransactionManager transactionManager =
            createTestTransactionManager();
    private final OrderMailService orderMailService =
            mock(OrderMailService.class);

    @Test
    void sendsMailAfterCommit() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        OrderPlacedEvent data = sampleOrderPlacedEvent();

        template.execute(status -> {
            registerAfterCommit(orderMailService, data);
            verifyNoInteractions(orderMailService);
            return null;
        });

        verify(orderMailService).sendOrderConfirmation(data);
    }

    @Test
    void doesNotSendMailAfterRollback() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        OrderPlacedEvent data = sampleOrderPlacedEvent();

        template.execute(status -> {
            registerAfterCommit(orderMailService, data);
            status.setRollbackOnly();
            return null;
        });

        verifyNoInteractions(orderMailService);
    }
}
~~~

**createTestTransactionManager()**, **sampleOrderPlacedEvent()** và **registerAfterCommit(...)** là helper của test, cần được định nghĩa theo cấu hình ứng dụng. Đoạn mã cho thấy hai kỳ vọng chính:

- Trong transaction, trước khi commit, service gửi mail chưa được gọi.
- Sau khi TransactionTemplate hoàn tất commit, callback được gọi.
- Khi đánh dấu rollback, callback afterCommit không được gọi.

### Test với @TransactionalEventListener

Với event listener, có thể kiểm thử bằng Spring integration test và một mail service mock:

1. Mở transaction thật.
2. Publish event.
3. Xác nhận listener chưa gửi mail trước commit.
4. Commit transaction.
5. Xác nhận mail service được gọi.
6. Chạy một test rollback và xác nhận mail service không được gọi.

Nếu test method tự được đánh dấu **@Transactional**, test framework thường rollback transaction ở cuối test. Listener AFTER_COMMIT sẽ không chạy trong trường hợp đó trừ khi test chủ động commit. Có thể dùng **TestTransaction.flagForCommit()** và **TestTransaction.end()** trong Spring TestContext, hoặc dùng TransactionTemplate để kiểm soát rõ thời điểm commit.

### Test async listener

Với **@Async**, listener được chuyển sang executor. Test cần chờ một tín hiệu hoàn thành có timeout hợp lý, chẳng hạn Awaitility hoặc CountDownLatch. Không dùng sleep cố định dài vì làm test chậm và dễ flaky.

Ngoài ra, cần test trường hợp executor từ chối task, mail service ném exception và retry/monitoring được kích hoạt theo thiết kế.

### Test không có transaction

Với **fallbackExecution = false**, publish event ngoài transaction không gọi transactional listener. Nên có test cho hành vi này nếu ứng dụng có đường gọi có thể phát event ngoài transaction.

## 14. Những lỗi thường gặp

### Lỗi 1: Gửi mail trực tiếp trong phương thức @Transactional

Nếu mail gửi thành công nhưng bước database sau đó rollback, người nhận vẫn nhận thông báo sai.

**Cách xử lý:** đăng ký callback afterCommit hoặc phát event để listener xử lý ở phase AFTER_COMMIT.

### Lỗi 2: Dùng BEFORE_COMMIT cho email thành công

Callback chạy trước khi transaction thực sự commit; một lỗi commit sau đó vẫn có thể rollback.

**Cách xử lý:** dùng AFTER_COMMIT cho thông báo xác nhận thay đổi đã lưu.

### Lỗi 3: Đăng ký synchronization khi không active

registerSynchronization(...) yêu cầu transaction synchronization đang active. Nếu không, Spring ném IllegalStateException.

**Cách xử lý:** kiểm tra trạng thái hoặc bảo đảm phương thức được gọi trong transaction do Spring quản lý.

### Lỗi 4: Event được publish ngoài transaction

Transactional event listener mặc định không có transaction để gắn vào và không chạy.

**Cách xử lý:** publish event trong phương thức transactional; chỉ bật fallbackExecution nếu nghiệp vụ cho phép chạy không có transaction.

### Lỗi 5: Bật fallbackExecution mà vẫn nghĩ listener luôn chạy sau commit

Khi không có transaction, listener có thể chạy ngay theo fallback path.

**Cách xử lý:** giữ fallbackExecution mặc định false nếu yêu cầu bắt buộc là sau commit.

### Lỗi 6: Nghĩ exception trong afterCommit làm database rollback

Database đã commit trước khi callback chạy. SMTP exception không thể đảo ngược commit.

**Cách xử lý:** phân biệt lỗi nghiệp vụ và lỗi post-commit; ghi nhận và retry riêng.

### Lỗi 7: Ghi database trong afterCommit nhưng không mở transaction mới

Resource transaction có thể vẫn bind trong callback, nhưng transaction gốc đã commit và không còn commit thêm.

**Cách xử lý:** dùng một service transaction mới với Propagation.REQUIRES_NEW nếu cần lưu trạng thái sau commit.

### Lỗi 8: Dùng @Async và kỳ vọng transaction context tự truyền

Thread executor không kế thừa transaction context của thread tạo event.

**Cách xử lý:** chỉ truyền dữ liệu bất biến/ID; worker mở transaction mới nếu cần truy cập database.

### Lỗi 9: Gửi mail đồng bộ làm request chậm

SMTP có thể chậm hoặc timeout, khiến callback đồng bộ kéo dài thời gian phản hồi sau commit.

**Cách xử lý:** dùng executor hoặc outbox worker khi phù hợp; cấu hình timeout và giới hạn concurrency.

### Lỗi 10: Callback trong bộ nhớ bị mất khi process dừng

Database đã commit nhưng ứng dụng dừng trước khi callback hoàn tất; không có event bền vững để phục hồi.

**Cách xử lý:** dùng transactional outbox nếu không được phép mất sự kiện.

### Lỗi 11: Dùng REQUIRES_NEW sai vị trí

Transaction bên trong REQUIRES_NEW có thể commit và gọi callback ngay cả khi transaction ngoài rollback.

**Cách xử lý:** xác định callback phải gắn với transaction nghiệp vụ nào; tránh đặt listener vào transaction độc lập nếu email phụ thuộc commit của transaction ngoài.

### Lỗi 12: Giữ JPA entity trong event rồi truy cập sau commit

Entity có thể đã detached; lazy relationship có thể không tải được và dữ liệu có thể thay đổi.

**Cách xử lý:** dùng event bất biến chứa ID và snapshot dữ liệu cần thiết.

### Lỗi 13: Coi SMTP accept là delivery thành công

JavaMailSender trả về không chứng minh email đã tới Inbox hoặc người nhận đã đọc.

**Cách xử lý:** theo dõi provider events, bounce và delivery status khi cần.

## 15. Thread context và loại transaction manager

Các ví dụ callback trực tiếp trong bài dùng **imperative transaction management** của Spring, thường đi cùng **PlatformTransactionManager**, JDBC hoặc JPA.

Trong mô hình imperative, transaction resources và synchronization được gắn với thread hiện tại. Vì vậy:

- Đăng ký synchronization phải diễn ra trên thread đang tham gia transaction.
- Publish event cần gắn với transaction cũng phải xảy ra trong execution context đó.
- Chuyển sang thread khác bằng Executor, CompletableFuture hoặc @Async không tự mang transaction context theo.
- Thread khác cần mở transaction mới nếu phải truy cập database theo một transaction riêng.

Ví dụ không nên làm:

~~~java
@Transactional
public void placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.create(command));

    CompletableFuture.runAsync(() -> {
        // Thread khác không tham gia transaction của placeOrder().
        eventPublisher.publishEvent(new OrderPlacedEvent(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomerEmail()
        ));
    });
}
~~~

Event được publish từ thread khác không tự gắn với transaction của phương thức placeOrder. Với transactional event listener mặc định, không có transaction context phù hợp thì listener có thể không chạy.

Hãy publish event ngay trong transaction, để Spring đăng ký listener vào transaction synchronization; chỉ phần xử lý sau phase mới được chuyển sang executor nếu cần.

### Reactive transaction

Ứng dụng dùng **ReactiveTransactionManager** và Reactor có transaction context khác với transaction imperative gắn theo thread. Không nên dùng các ví dụ TransactionSynchronizationManager imperative ở trên cho luồng reactive.

Các phiên bản Spring mới hỗ trợ transactional event listener với reactive transaction context, nhưng event cần mang transaction context theo cơ chế được Spring cung cấp, chẳng hạn **TransactionalEventPublisher**. Hãy dùng API reactive transaction synchronization tương ứng với phiên bản Spring đang triển khai.

Nếu ứng dụng dùng WebFlux/R2DBC, hãy xác định rõ transaction manager là imperative hay reactive trước khi chọn API. Không chuyển một callback thread-bound sang reactive pipeline chỉ bằng cách đổi kiểu return thành Mono hoặc Flux.

## 16. Dùng afterCompletion khi cần biết cả commit lẫn rollback

Nếu cần một callback chạy khi transaction kết thúc trong cả hai trường hợp, có thể override **afterCompletion(int status)**:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                if (status == TransactionSynchronization.STATUS_COMMITTED) {
                    auditLogger.recordCommitted(orderId);
                } else if (status == TransactionSynchronization.STATUS_ROLLED_BACK) {
                    auditLogger.recordRolledBack(orderId);
                }
            }
        }
);
~~~

Các giá trị trạng thái thường dùng:

| Hằng số | Ý nghĩa |
| --- | --- |
| **STATUS_COMMITTED** | Transaction đã commit |
| **STATUS_ROLLED_BACK** | Transaction đã rollback |
| **STATUS_UNKNOWN** | Không xác định được trạng thái cuối cùng |

Với email xác nhận thành công, **afterCommit()** vẫn rõ ràng hơn vì callback chỉ có thể chạy sau commit. **afterCompletion()** phù hợp khi cùng một nơi cần xử lý cả hai kết quả hoặc dọn dẹp tài nguyên bất kể transaction kết thúc thế nào.

Không gửi email thành công vô điều kiện trong afterCompletion. Nếu chọn callback này, phải kiểm tra status trước khi gọi mail service.

## 17. Checklist lựa chọn cách triển khai

Trước khi quyết định dùng callback, transactional event listener hay outbox, hãy trả lời các câu hỏi:

| Câu hỏi | Hướng lựa chọn |
| --- | --- |
| Email chỉ được gửi nếu transaction commit? | AFTER_COMMIT |
| Chỉ có một tác vụ kỹ thuật nhỏ gắn với transaction? | TransactionSynchronization trực tiếp |
| Có một sự kiện nghiệp vụ cần nhiều handler? | ApplicationEventPublisher + @TransactionalEventListener |
| Listener có được chạy khi không có transaction? | Giữ fallbackExecution=false nếu phải bảo đảm sau commit |
| SMTP có thể làm request chậm? | Executor hoặc worker bất đồng bộ |
| Không được mất email khi process restart? | Transactional outbox hoặc durable messaging |
| Callback cần ghi trạng thái database sau commit? | Service transaction riêng, thường là REQUIRES_NEW |
| Có khả năng retry gửi mail? | Lưu trạng thái, attempt, backoff và xử lý duplicate |
| Ứng dụng dùng reactive transaction? | Dùng reactive transaction context/API tương ứng |

Một lựa chọn triển khai phổ biến:

~~~text
Email thông báo tiện ích, chấp nhận mất hiếm gặp
    -> @TransactionalEventListener(AFTER_COMMIT)
    -> gửi đồng bộ hoặc qua executor

Email giao dịch quan trọng, cần retry và phục hồi
    -> ghi outbox row trong cùng transaction nghiệp vụ
    -> worker đọc và gửi sau commit
    -> lưu trạng thái, retry, giám sát và xử lý duplicate
~~~

## 18. Tình huống luyện tập

### Tình huống 1 — Đơn hàng rollback sau khi gửi email

Service gửi email ngay sau repository.save, rồi một bước cập nhật tồn kho thất bại và transaction rollback.

**Hỏi:** vì sao người dùng vẫn nhận email?

**Đáp:** SMTP là hệ thống bên ngoài database. Rollback chỉ hoàn tác thay đổi database, không thu hồi email đã được SMTP nhận. Hãy chuyển gửi mail sang AFTER_COMMIT.

### Tình huống 2 — Đăng ký callback rồi transaction rollback

Service gọi registerSynchronization và sau đó ném exception khiến transaction rollback.

**Hỏi:** afterCommit có chạy không?

**Đáp:** không. Callback chỉ được gọi sau commit thành công.

### Tình huống 3 — Gửi email trong BEFORE_COMMIT

**Hỏi:** transaction commit thất bại sau callback thì sao?

**Đáp:** email đã gửi vẫn tồn tại dù database rollback. Dùng AFTER_COMMIT cho thông báo xác nhận thành công.

### Tình huống 4 — Event publish ngoài transaction

Service không có @Transactional nhưng publish OrderPlacedEvent; listener dùng AFTER_COMMIT và fallbackExecution mặc định false.

**Hỏi:** listener có chạy không?

**Đáp:** không có transaction để gắn synchronization nên listener không được thực thi. Đưa publish vào transaction đúng hoặc thay đổi fallback chỉ khi nghiệp vụ chấp nhận.

### Tình huống 5 — SMTP lỗi trong afterCommit

Database đã commit, nhưng JavaMailSender ném exception.

**Hỏi:** đơn hàng có rollback không?

**Đáp:** không. Database đã commit trước khi callback chạy. Ghi nhận lỗi gửi mail và retry theo chính sách riêng.

### Tình huống 6 — Callback ghi trạng thái bằng repository.save

**Hỏi:** lệnh save trong afterCommit có chắc được commit không?

**Đáp:** không nên giả định như vậy. Resource transaction có thể vẫn được bind nhưng transaction gốc đã hoàn tất. Nếu cần ghi độc lập, gọi một service transaction mới với REQUIRES_NEW.

### Tình huống 7 — Event được publish trong transaction A nhưng xử lý ở thread B

**Hỏi:** thread B có tự nhận transaction A không?

**Đáp:** không. Transaction imperative gắn với thread/context hiện tại. Nếu dùng async, chỉ truyền dữ liệu cần thiết và mở transaction mới trong worker khi cần.

### Tình huống 8 — Process dừng sau commit

Database đã commit nhưng ứng dụng bị dừng trước khi callback gửi mail chạy.

**Hỏi:** lần khởi động sau callback có tự chạy lại không?

**Đáp:** không. Callback trong bộ nhớ không phải hàng đợi bền vững. Nếu không được mất event, ghi outbox trong cùng transaction và để worker xử lý.

### Tình huống 9 — SMTP đã nhận mail nhưng worker chưa đánh dấu SENT

**Hỏi:** worker retry có thể gửi trùng không?

**Đáp:** có. SMTP và database không có một commit nguyên tử chung. Cần idempotency nếu provider hỗ trợ, kiểm soát retry và chấp nhận khả năng duplicate khi không thể bảo đảm exactly-once.

### Tình huống 10 — Transaction ngoài rollback, transaction REQUIRES_NEW đã commit

Callback được đăng ký trong transaction REQUIRES_NEW.

**Hỏi:** callback có thể chạy không?

**Đáp:** có. Callback gắn với transaction bên trong và chạy sau khi transaction đó commit, dù transaction ngoài về sau rollback. Hãy bảo đảm đây là ranh giới nghiệp vụ mong muốn.

## 19. Quy trình thực hiện

~~~text
1. Xác định email phụ thuộc vào thay đổi database nào
       |
       v
2. Đưa thay đổi đó vào một transaction rõ ràng
       |
       v
3. Chọn cơ chế sau commit
       |
       +--> Một callback nhỏ
       |       -> registerSynchronization
       |       -> afterCommit()
       |
       +--> Sự kiện nghiệp vụ
       |       -> publishEvent(...)
       |       -> @TransactionalEventListener(AFTER_COMMIT)
       |
       '--> Yêu cầu bền vững/retry
               -> ghi outbox cùng transaction
               -> worker xử lý sau commit
       |
       v
4. Render email và gọi JavaMailSender
       |
       v
5. Ghi nhận lỗi/attempt và quan sát trạng thái gửi
       |
       v
6. Kiểm thử commit, rollback, SMTP failure và process restart
~~~

**Phát sự kiện sau commit bằng transaction synchronization** giúp ứng dụng chỉ gửi email xác nhận sau khi database transaction đã commit. Với tác vụ nhỏ, có thể đăng ký **TransactionSynchronization.afterCommit()** qua **TransactionSynchronizationManager**. Với sự kiện nghiệp vụ, **@TransactionalEventListener(phase = AFTER_COMMIT)** giúp tách publisher khỏi mail handler và cho phép nhiều listener cùng phản ứng. Cần nhớ callback chạy sau commit không thể rollback database, lỗi SMTP phải được xử lý riêng, transaction context imperative không tự truyền sang thread khác, và callback trong bộ nhớ có thể mất khi process dừng. Khi email phải được retry và không được mất, hãy ghi một outbox event trong cùng transaction rồi xử lý bằng worker bền vững.

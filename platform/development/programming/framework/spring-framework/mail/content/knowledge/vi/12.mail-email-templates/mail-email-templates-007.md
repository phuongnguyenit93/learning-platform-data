# Render template ngoài transaction nghiệp vụ khi cần

Một ứng dụng Spring có thể gửi email xác nhận đơn hàng, hóa đơn hoặc thông báo thay đổi trạng thái. Thông thường, nghiệp vụ phải cập nhật dữ liệu trong database trước; sau đó ứng dụng mới dựng nội dung email từ template và gửi qua SMTP.

Nếu việc render template hoặc gửi email diễn ra bên trong transaction nghiệp vụ, transaction có thể bị kéo dài bởi thao tác không cần thiết, giữ kết nối và lock database lâu hơn, hoặc gặp một lỗi bên ngoài khiến kết quả nghiệp vụ khó hiểu. Một email cũng có thể được gửi đi trước khi transaction commit thành công, khiến người dùng nhận thông báo về một thay đổi thực tế chưa được lưu.

Vì vậy, khi cần, hãy **tách việc render template khỏi transaction cập nhật nghiệp vụ**. Cách tổ chức thường gặp là lấy dữ liệu cần thiết thành một DTO bất biến trong transaction, commit thay đổi, rồi render và gửi email ở bước sau. Với hệ thống cần độ tin cậy cao, có thể dùng sự kiện sau commit hoặc transactional outbox để chuyển việc gửi sang worker.

Điều này không có nghĩa mọi template đều phải chạy bất đồng bộ. Một template nhỏ, chỉ render từ dữ liệu đã có và không kéo dài transaction, có thể không cần tách riêng. Quyết định nên dựa vào thời gian xử lý, mức độ quan trọng của email, yêu cầu nhất quán dữ liệu và cách hệ thống phục hồi khi gửi thất bại.

## 1. Transaction nghiệp vụ và render email là hai công việc khác nhau

Một transaction nghiệp vụ thường đảm nhiệm việc thay đổi dữ liệu cần được commit cùng nhau:

- Xác nhận đơn hàng.
- Cập nhật trạng thái thanh toán.
- Ghi nhận lịch sử thay đổi.
- Trừ tồn kho hoặc tạo bản ghi liên quan.
- Lưu thông tin cần dùng để thông báo.

Render template là quá trình biến dữ liệu thành nội dung:

- Đọc một template HTML hoặc plain text.
- Đưa dữ liệu vào các placeholder.
- Áp dụng định dạng ngày, tiền tệ và ngôn ngữ.
- Tạo chuỗi subject, body và metadata cần gửi.

Gửi email lại là một thao tác I/O với hệ thống bên ngoài:

- Kết nối SMTP hoặc dịch vụ gửi thư.
- Xác thực.
- Truyền message.
- Nhận phản hồi chấp nhận hoặc từ chối.

Có thể hình dung:

~~~text
Transaction nghiệp vụ
    |
    +-- Đọc và kiểm tra dữ liệu
    +-- Cập nhật trạng thái đơn hàng
    +-- Ghi dữ liệu liên quan
    +-- Tạo snapshot dữ liệu thông báo
    |
    v
COMMIT
    |
    v
Render template
    |
    v
Tạo MimeMessage
    |
    v
Gửi qua JavaMailSender
~~~

Ba phần có thời gian và cơ chế lỗi khác nhau. Database transaction có thể rollback những thay đổi database của nó. SMTP server là một hệ thống bên ngoài; việc đã gửi một email không thể được rollback chỉ bằng cách rollback transaction database.

### 1.1. Ví dụ khi làm tất cả trong một transaction

Một cách triển khai dễ gặp:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    String html = templateRenderer.render(order);
    mailService.send(order.getCustomerEmail(), html);
}
~~~

Trong phương thức này:

1. Transaction database bắt đầu.
2. Đơn hàng được cập nhật.
3. Template được render.
4. Ứng dụng gọi SMTP.
5. Transaction mới hoàn tất khi phương thức kết thúc và interceptor xử lý commit.

Nếu SMTP chậm, transaction vẫn mở trong lúc chờ. Nếu SMTP ném exception và exception đó làm transaction rollback, database có thể không lưu thay đổi, nhưng nếu SMTP đã chấp nhận email trước khi lỗi khác xảy ra thì email không thể bị thu hồi.

Đây là một vấn đề về **ranh giới transaction và side effect**, không chỉ là vấn đề hiệu năng.

### 1.2. Những rủi ro chính

| Vấn đề | Điều có thể xảy ra |
| --- | --- |
| SMTP phản hồi chậm | Transaction database giữ tài nguyên lâu hơn |
| Template phức tạp | CPU, đọc file hoặc xử lý dữ liệu kéo dài thời gian transaction |
| Gửi mail lỗi | Nghiệp vụ có thể rollback dù cập nhật database vốn hợp lệ |
| Transaction rollback sau khi SMTP đã nhận thư | Email thông báo một thay đổi chưa commit |
| Retry toàn bộ nghiệp vụ | Có thể thực hiện lại thao tác nghiệp vụ hoặc gửi email trùng |
| Dùng JPA entity trong worker | Lazy field có thể không còn truy cập được sau transaction |

Không phải mọi trường hợp đều dẫn đến lỗi. Một lời gọi render nhanh, không có I/O và không kéo dài transaction có thể hoạt động bình thường. Tuy nhiên, **gửi email qua mạng trong transaction nghiệp vụ** thường tạo ra sự phụ thuộc không cần thiết giữa database và dịch vụ bên ngoài.

## 2. Render template ngoài transaction có nghĩa là gì?

Render ngoài transaction nghĩa là phần dựng nội dung email được thực hiện sau khi transaction nghiệp vụ đã kết thúc, hoặc trong một luồng công việc không tham gia transaction đó.

Ví dụ:

~~~text
Application service
    |
    | gọi bean nghiệp vụ
    v
OrderService.confirmOrder()
    |
    | @Transactional
    | cập nhật database
    | trả về DTO snapshot
    v
Transaction commit hoàn tất
    |
    | phương thức transactional đã trả về
    v
MailTemplateRenderer.render(snapshot)
    |
    v
JavaMailSender.send(...)
~~~

Ở đây, **snapshot** là dữ liệu đã được lấy ra trong lúc transaction còn hoạt động. Renderer không cần giữ JPA entity hay mở lại database để lấy các trường lazy.

Có hai lợi ích riêng:

1. **Render sau commit:** nội dung được tạo sau khi thay đổi nghiệp vụ đã được commit.
2. **Render ở worker riêng:** thời gian dựng nội dung và gửi thư không nằm trong request hoặc transaction của người dùng.

Hai lợi ích này có thể kết hợp, nhưng không đồng nghĩa. Render sau commit trong cùng thread vẫn có thể làm HTTP request chờ; render bất đồng bộ có thể tách thời gian xử lý khỏi request.

### 2.1. Không phải template engine nào cũng cần database

Một template engine thường nhận một model đã có và trả về chuỗi:

~~~text
Template + Model -> Rendered HTML
~~~

Ví dụ:

~~~text
Template:
  Xin chào {{customerName}},
  Đơn hàng {{orderNumber}} đã được xác nhận.

Model:
  customerName = "An"
  orderNumber = "ORD-2026-001"

Kết quả:
  Xin chào An,
  Đơn hàng ORD-2026-001 đã được xác nhận.
~~~

Nếu model đã có đủ dữ liệu, renderer không cần truy vấn database. Đây là lý do DTO snapshot rất hữu ích: nó biến template rendering thành một bước gần như thuần dữ liệu, có thể chạy độc lập với persistence context.

### 2.2. Khi nào nên cân nhắc tách riêng?

Nên xem xét tách render khỏi transaction khi:

- Template có nhiều section, nhiều ngôn ngữ hoặc nhiều phép định dạng.
- Email có nhiều attachment được tạo từ dữ liệu báo cáo.
- Việc render đọc file, truy cập storage hoặc dịch vụ bên ngoài.
- Nhiều email được tạo cho một nghiệp vụ.
- SMTP có độ trễ không ổn định.
- Request HTTP không nên chờ hoàn tất gửi email.
- Email cần retry độc lập với thao tác cập nhật database.
- Hệ thống cần lưu trạng thái từng lần render/gửi.

Nếu template chỉ có vài trường đơn giản, việc tạo một chuỗi ngắn trong cùng transaction có thể không đáng để thêm event, queue và worker. Hãy tách theo nhu cầu thực tế thay vì biến mọi email thành một pipeline phức tạp.

## 3. Snapshot dữ liệu: ranh giới quan trọng giữa JPA và renderer

Một lỗi thường gặp khi chuyển gửi mail sang worker là truyền trực tiếp entity:

~~~java
publisher.publishEvent(new OrderConfirmedEvent(order));
~~~

Sau khi transaction kết thúc, entity có thể detached khỏi persistence context. Nếu template truy cập một quan hệ lazy:

~~~java
order.getCustomer().getAddresses()
~~~

thì có thể phát sinh **LazyInitializationException**, hoặc renderer vô tình kích hoạt truy vấn mới ngoài ý muốn nếu persistence context còn tồn tại theo một cơ chế khác.

Thay vì truyền entity, hãy tạo **DTO chỉ chứa dữ liệu email cần dùng**.

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        String orderDate,
        String totalAmount,
        String shippingAddress
) {}
~~~

Trong transaction:

~~~java
@Transactional
public OrderMailData confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();

    return new OrderMailData(
            order.getCustomerEmail(),
            order.getCustomerName(),
            order.getNumber(),
            formatDate(order.getConfirmedAt()),
            formatMoney(order.getTotal()),
            order.getShippingAddressText()
    );
}
~~~

Khi phương thức transactional trả về qua Spring proxy, transaction được commit trước khi caller tiếp tục bước kế tiếp theo luồng thông thường. Caller nhận DTO đã chứa dữ liệu cần render.

### 3.1. Vì sao nên dùng DTO bất biến?

DTO như Java record có các đặc điểm hữu ích:

- Chỉ mang những trường mà template cần.
- Không phụ thuộc Hibernate session.
- Không cho renderer vô tình sửa entity nghiệp vụ.
- Dễ serialize để lưu queue hoặc outbox.
- Có thể dùng trong unit test mà không cần database.
- Giữ được giá trị tại thời điểm nghiệp vụ được xác nhận.

Không nhất thiết mọi trường phải là String. Có thể truyền **Instant**, **BigDecimal**, enum hoặc kiểu dữ liệu rõ nghĩa rồi để renderer định dạng theo locale. Tuy nhiên, cần xác định quy tắc định dạng ổn định để email không thay đổi ngoài ý muốn.

### 3.2. Snapshot và truy vấn lại dữ liệu khác nhau

Có hai chiến lược:

| Chiến lược | Cách làm | Ý nghĩa |
| --- | --- | --- |
| **Snapshot** | Ghi tất cả dữ liệu cần render vào DTO/event trong transaction | Email phản ánh dữ liệu tại thời điểm nghiệp vụ phát sinh |
| **Reload** | Chỉ truyền ID, worker truy vấn database sau commit | Email phản ánh dữ liệu tại thời điểm worker đọc |

Ví dụ đơn hàng được xác nhận lúc 10:00 với tổng tiền 500.000 đồng. Lúc 10:05, một tác vụ điều chỉnh dữ liệu hoặc cập nhật địa chỉ chạy trước worker gửi mail.

- Nếu dùng snapshot, email vẫn thể hiện dữ liệu lúc xác nhận.
- Nếu reload, email có thể thể hiện dữ liệu mới hơn.

Không có lựa chọn đúng cho mọi hệ thống. Với hóa đơn, biên nhận và thông báo sự kiện, snapshot thường quan trọng. Với email nhắc nhở cần trạng thái mới nhất, reload có thể hợp lý.

### 3.3. Không đưa dữ liệu nhạy cảm không cần thiết vào event

Snapshot cần đủ dữ liệu để render, nhưng không nên chứa mọi field của entity. Chỉ đưa thông tin được phép gửi qua email. Tránh đưa password, token nội bộ, dữ liệu thanh toán nhạy cảm hoặc thông tin cá nhân không cần thiết vào event payload hay outbox.

## 4. Cách đơn giản: gọi service transactional rồi render sau khi nó trả về

Nếu yêu cầu chỉ là **đảm bảo transaction kết thúc trước khi render và gửi**, có thể dùng hai bean riêng.

Bean nghiệp vụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderMailData confirm(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        return new OrderMailData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getNumber(),
                order.getTotal().toPlainString()
        );
    }
}
~~~

Bean điều phối:

~~~java
@Service
public class OrderConfirmationFacade {

    private final OrderService orderService;
    private final OrderMailService mailService;

    public OrderConfirmationFacade(
            OrderService orderService,
            OrderMailService mailService
    ) {
        this.orderService = orderService;
        this.mailService = mailService;
    }

    public void confirmAndNotify(UUID orderId) {
        OrderMailData snapshot = orderService.confirm(orderId);

        // Lệnh confirm() đã trả về qua proxy;
        // transaction nghiệp vụ đã kết thúc.
        mailService.sendConfirmation(snapshot);
    }
}
~~~

Bean gửi email:

~~~java
@Service
public class OrderMailService {

    private final OrderMailTemplateRenderer renderer;
    private final JavaMailSender mailSender;

    public OrderMailService(
            OrderMailTemplateRenderer renderer,
            JavaMailSender mailSender
    ) {
        this.renderer = renderer;
        this.mailSender = mailSender;
    }

    public void sendConfirmation(OrderMailData data) {
        String html = renderer.render(data);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, "UTF-8"
        );

        try {
            helper.setTo(data.recipient());
            helper.setSubject(
                    "Xác nhận đơn hàng " + data.orderNumber()
            );
            helper.setText(html, true);
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Không thể tạo email xác nhận", ex
            );
        }

        mailSender.send(message);
    }
}
~~~

**MailPreparationException** ở ví dụ là exception do ứng dụng định nghĩa hoặc thay bằng loại exception phù hợp. Cần import các lớp Spring/Jakarta tương ứng và xử lý lỗi theo quy ước dự án.

Luồng gọi:

~~~text
OrderConfirmationFacade
    |
    v
OrderService.confirm()
    |
    +-- Transaction begin
    +-- Update order
    +-- Build OrderMailData
    +-- Commit
    |
    v
Return snapshot
    |
    v
OrderMailService
    |
    +-- Render template
    +-- Build MimeMessage
    +-- Send
~~~

Ưu điểm:

- Dễ hiểu và ít thành phần.
- Render chắc chắn diễn ra sau khi phương thức transactional trả về thành công.
- Không truyền entity detached vào renderer.
- Không gửi email nếu commit thất bại.

Giới hạn:

- Request caller vẫn phải chờ render và SMTP.
- Nếu gửi thất bại sau commit, đơn hàng vẫn đã được xác nhận.
- Nếu process dừng sau commit nhưng trước khi gọi mail service, thông báo có thể không được gửi.

Cách này phù hợp khi email không cần pipeline bất đồng bộ bền vững và độ trễ gửi chấp nhận được.

### 4.1. Lưu ý về Spring proxy và self-invocation

Trong Spring, **@Transactional** thường được áp dụng qua proxy. Nếu một method trong cùng class gọi một method khác có annotation @Transactional bằng **this.method()**, lời gọi nội bộ có thể không đi qua proxy và annotation không được áp dụng như mong đợi.

Vì vậy, ví dụ tách **OrderService** và **OrderConfirmationFacade** thành hai bean. Caller gọi qua bean proxy, nên transaction được quản lý đúng ranh giới.

## 5. Dùng Transactional Event để xử lý sau commit

Khi muốn nghiệp vụ phát ra một sự kiện và một thành phần khác xử lý email sau khi transaction thành công, Spring cung cấp **@TransactionalEventListener**.

Ví dụ sự kiện:

~~~java
public record OrderConfirmedEvent(
        OrderMailData mailData
) {}
~~~

Trong service nghiệp vụ:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher publisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher publisher
    ) {
        this.orderRepository = orderRepository;
        this.publisher = publisher;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        OrderMailData snapshot = new OrderMailData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getNumber(),
                order.getTotal().toPlainString()
        );

        publisher.publishEvent(
                new OrderConfirmedEvent(snapshot)
        );
    }
}
~~~

Listener:

~~~java
@Component
public class OrderMailEventListener {

    private final OrderMailService mailService;

    public OrderMailEventListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailService.sendConfirmation(event.mailData());
    }
}
~~~

Khi transaction commit thành công, listener mới được gọi. Nếu transaction rollback, sự kiện không được xử lý ở phase AFTER_COMMIT.

### 5.1. Các phase của TransactionalEventListener

Spring hỗ trợ một số phase:

| Phase | Khi listener được gọi |
| --- | --- |
| **BEFORE_COMMIT** | Trước khi transaction commit |
| **AFTER_COMMIT** | Sau khi commit thành công |
| **AFTER_ROLLBACK** | Sau khi rollback |
| **AFTER_COMPLETION** | Sau khi transaction hoàn tất, dù commit hay rollback |

Với email xác nhận một nghiệp vụ đã lưu thành công, **AFTER_COMMIT** thường phù hợp.

**BEFORE_COMMIT** không thích hợp nếu mục tiêu là tránh gửi thông báo cho thay đổi chưa commit: listener vẫn chạy trước khi commit xảy ra và transaction còn có thể thất bại sau đó.

### 5.2. Khi không có transaction thì sao?

Mặc định, **@TransactionalEventListener** gắn với transaction đang hoạt động. Nếu event được phát khi không có transaction, listener có thể không được gọi.

Có tùy chọn **fallbackExecution=true** để listener chạy cả khi không có transaction, nhưng điều đó thay đổi ý nghĩa của sự kiện. Chỉ bật khi nghiệp vụ chấp nhận xử lý event không gắn với transaction.

Đừng bật fallback chỉ để khắc phục listener không chạy mà chưa xác định event có thực sự được phát trong transaction hay không.

### 5.3. AFTER_COMMIT không làm email trở thành durable

Sự kiện Spring trong bộ nhớ không tự được lưu bền vững. Một tình huống vẫn có thể xảy ra:

~~~text
1. Database commit thành công.
2. Process dừng đột ngột.
3. Listener chưa kịp xử lý event.
4. Không có email nào được gửi.
~~~

Transactional event giúp đặt đúng **thời điểm** xử lý, nhưng không tự cung cấp cơ chế khôi phục sự kiện sau khi ứng dụng crash.

Nếu email là thông báo có thể thử lại thủ công, cách này có thể đủ. Nếu yêu cầu không được mất ý định gửi, hãy xem xét queue bền vững hoặc transactional outbox.

## 6. Render và gửi bất đồng bộ sau commit

Nếu không muốn request người dùng chờ render hoặc SMTP, có thể kết hợp **@TransactionalEventListener(AFTER_COMMIT)** với **@Async**.

Bật async processing:

~~~java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailExecutor")
    public Executor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("mail-worker-");
        return executor;
    }
}
~~~

Các con số là ví dụ. Cấu hình thực tế cần căn cứ vào tốc độ SMTP provider, lưu lượng gửi và khả năng chịu tải của ứng dụng.

Listener:

~~~java
@Component
public class AsyncOrderMailListener {

    private final OrderMailService mailService;

    public AsyncOrderMailListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @Async("mailExecutor")
    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailService.sendConfirmation(event.mailData());
    }
}
~~~

Luồng xử lý:

~~~text
HTTP request
    |
    v
@Transactional confirmOrder()
    |
    +-- Update database
    +-- Publish OrderConfirmedEvent
    +-- Commit
    |
    v
AFTER_COMMIT listener
    |
    v
Submit task vào mailExecutor
    |
    v
Worker thread
    |
    +-- Render template
    +-- Tạo MimeMessage
    +-- Gửi SMTP
    |
    v
Kết thúc tác vụ
~~~

Trong mô hình này:

- Transaction nghiệp vụ kết thúc trước khi listener xử lý.
- Rendering và SMTP chạy trên thread executor.
- HTTP request có thể kết thúc mà không chờ SMTP nếu luồng gọi không tự chờ kết quả.
- Lỗi trong async task không tự động truyền ngược về request đã hoàn tất.

### 6.1. @Async không tự tạo retry

Nếu SMTP lỗi trong async listener, exception không làm transaction nghiệp vụ đã commit rollback. Nó cũng không tự động làm Spring gửi lại email.

Cần quyết định rõ cách xử lý:

- Ghi log có correlation ID và trạng thái lỗi.
- Gửi thông tin lỗi đến hệ thống giám sát.
- Đưa tác vụ vào cơ chế retry.
- Lưu trạng thái gửi để người vận hành hoặc worker có thể tiếp tục.
- Phân biệt lỗi tạm thời như timeout với lỗi vĩnh viễn như recipient bị từ chối.

Một **ThreadPoolTaskExecutor** cũng có queue hữu hạn. Nếu queue đầy hoặc ứng dụng dừng, task có thể bị từ chối hoặc mất tùy cấu hình và thời điểm shutdown. Đây là một cơ chế thực thi bất đồng bộ trong process, không phải hàng đợi bền vững.

### 6.2. Cấu hình executor có chủ đích

Không nên sử dụng một executor không giới hạn cho mọi email. Khi số lượng event tăng nhanh, hệ thống có thể tạo nhiều thread hoặc queue lớn, tiêu thụ bộ nhớ và gây áp lực lên SMTP provider.

Nên cấu hình:

- Số thread tối thiểu và tối đa.
- Queue capacity.
- Thread name prefix để quan sát.
- Chính sách khi queue đầy.
- Shutdown behavior.
- Metrics về queue depth, active thread và lỗi gửi.

Nếu có nhiều loại email, có thể dùng executor hoặc queue riêng cho email giao dịch và email bản tin để một nhóm tác vụ không làm nghẽn nhóm còn lại.

### 6.3. Không truyền JPA entity vào async listener

Async worker chạy trên thread khác, không kế thừa transaction hay persistence context của thread gọi. Đừng truyền entity rồi kỳ vọng worker có thể đọc lazy relation.

Hãy truyền **OrderMailData** hoặc một event payload có thể serialize. Nếu chỉ truyền order ID, worker cần mở transaction đọc dữ liệu theo một chiến lược được xác định rõ.

## 7. Transactional outbox cho yêu cầu gửi email đáng tin cậy hơn

Nếu một email quan trọng không được phép mất ý định gửi khi process crash, sự kiện in-memory và @Async thường chưa đủ.

**Transactional outbox** lưu một bản ghi yêu cầu gửi email trong **cùng transaction database** với thay đổi nghiệp vụ.

Ví dụ các bản ghi:

~~~text
orders
  id = 1001
  status = CONFIRMED

outbox_events
  id = 9001
  event_type = ORDER_CONFIRMED
  payload = { snapshot data ... }
  status = PENDING
~~~

Cả hai được commit cùng transaction:

~~~text
BEGIN TRANSACTION
    UPDATE orders SET status = 'CONFIRMED'
    INSERT INTO outbox_events (..., 'PENDING')
COMMIT
~~~

Sau commit, một worker riêng đọc outbox:

~~~text
Outbox worker
    |
    v
Load pending event
    |
    v
Render template
    |
    v
Send email
    |
    v
Mark event as SENT
~~~

Nếu process dừng sau commit, bản ghi outbox vẫn nằm trong database. Worker có thể tiếp tục khi hệ thống khởi động lại.

### 7.1. Ví dụ bảng outbox

Một schema minh họa:

~~~sql
CREATE TABLE mail_outbox (
    id              UUID PRIMARY KEY,
    event_type      VARCHAR(100) NOT NULL,
    payload         TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NULL,
    created_at      TIMESTAMP NOT NULL,
    sent_at         TIMESTAMP NULL,
    last_error      TEXT NULL
);
~~~

Các field có thể thay đổi theo hệ quản trị database và cách tổ chức event. **payload** có thể lưu DTO đã serialize, hoặc một định danh để worker truy xuất snapshot được quản lý.

### 7.2. Worker xử lý outbox

Pseudo-code:

~~~java
public void processPendingMail() {
    List<MailOutboxEvent> events =
            outboxRepository.claimPendingBatch(50);

    for (MailOutboxEvent event : events) {
        try {
            OrderMailData data = deserialize(event.payload());
            mailService.sendConfirmation(data);

            outboxRepository.markSent(event.id());
        } catch (Exception ex) {
            outboxRepository.scheduleRetry(
                    event.id(),
                    calculateNextAttempt(event.attempts()),
                    classify(ex)
            );
        }
    }
}
~~~

Đây là pseudo-code mô tả luồng. Trong ứng dụng thật, việc **claimPendingBatch** cần khóa hoặc cơ chế lease để hai worker không xử lý cùng một event đồng thời. Việc cập nhật trạng thái cũng cần transaction riêng và xử lý trường hợp worker chết giữa chừng.

### 7.3. Outbox giải quyết điều gì?

- Ý định gửi email được lưu cùng thay đổi nghiệp vụ.
- Có thể phục hồi pending events sau khi ứng dụng restart.
- Retry tách khỏi request của người dùng.
- Có trạng thái theo dõi và lịch sử xử lý.
- Có thể giới hạn tốc độ gửi và chia batch.

### 7.4. Outbox không bảo đảm exactly-once delivery

Có một tình huống quan trọng:

~~~text
1. Worker gửi email.
2. SMTP server chấp nhận email.
3. Worker crash trước khi cập nhật outbox thành SENT.
4. Worker khởi động lại và gửi lại event.
~~~

Người nhận có thể nhận email hai lần. SMTP và database không tham gia cùng một distributed transaction có thể rollback nguyên tử. Vì vậy, outbox thường giúp đạt **at-least-once processing** cho ý định gửi, chứ không bảo đảm một email xuất hiện chính xác một lần trong inbox.

Để giảm ảnh hưởng của gửi trùng:

- Tạo một **event ID** ổn định.
- Ghi nhận ID trong log và metadata của tác vụ.
- Thiết kế email hoặc nghiệp vụ có thể chịu được thông báo lặp.
- Dùng idempotency key nếu provider có hỗ trợ theo hợp đồng cụ thể.
- Tránh retry một kết quả hoàn toàn không rõ ràng mà không có chính sách.

Header **Message-ID** hữu ích để đối chiếu message nhưng tự nó không bắt buộc SMTP server hay email client loại bỏ thư trùng.

## 8. Chọn render snapshot hay render sau khi worker reload dữ liệu?

Khi worker chạy sau commit, có thể truyền snapshot hoặc chỉ truyền ID.

### 8.1. Snapshot đầy đủ

Trong transaction:

~~~java
OrderMailData data = new OrderMailData(
        order.getCustomerEmail(),
        order.getCustomerName(),
        order.getNumber(),
        formatMoney(order.getTotal())
);

outboxRepository.save(
        MailOutboxEvent.pending(
                eventId,
                serialize(data)
        )
);
~~~

Worker đọc payload và render trực tiếp.

Ưu điểm:

- Email phản ánh đúng dữ liệu tại thời điểm event.
- Không phụ thuộc entity hoặc lazy loading.
- Ít truy vấn lại database.
- Dễ tái tạo nội dung khi debug nếu snapshot được lưu đúng chính sách.

Hạn chế:

- Payload lớn hơn.
- Có thể lưu dữ liệu cá nhân trong outbox, cần chính sách retention và access control.
- Nếu template thay đổi, cùng snapshot có thể render ra email khác với phiên bản trước.

### 8.2. Chỉ lưu ID rồi reload

Trong transaction, outbox chỉ lưu:

~~~json
{
  "eventId": "9001",
  "orderId": "1001",
  "eventType": "ORDER_CONFIRMED"
}
~~~

Worker mở transaction đọc đơn hàng và tạo DTO mới.

Ưu điểm:

- Payload nhỏ.
- Không nhân bản nhiều dữ liệu.
- Worker có thể lấy trạng thái mới nhất.

Hạn chế:

- Email có thể khác trạng thái tại thời điểm phát event.
- Bản ghi có thể bị xóa hoặc không còn truy cập được.
- Cần xác định chính sách nếu dữ liệu thay đổi giữa lúc event được tạo và lúc worker chạy.

### 8.3. Có thể lưu cả snapshot và phiên bản template

Với email quan trọng như hóa đơn hoặc xác nhận giao dịch, có thể lưu:

- Snapshot dữ liệu cần render.
- Template key.
- Template version.
- Locale.
- Event ID.
- Thời điểm nghiệp vụ.
- Recipient đã được xác định và kiểm tra.

Điều này giúp hệ thống giải thích vì sao một email có nội dung như vậy và có thể render lại nhất quán khi cần. Cần cân nhắc dung lượng và chính sách bảo vệ dữ liệu cá nhân.

## 9. Tách TemplateRenderer khỏi MailSender

Một cách tổ chức rõ ràng là chia hai trách nhiệm:

- **TemplateRenderer** nhận dữ liệu và trả về subject/body đã render.
- **MailSenderService** nhận nội dung đã render, dựng MimeMessage và gửi.

Ví dụ DTO:

~~~java
public record RenderedMail(
        String recipient,
        String subject,
        String htmlBody,
        String textBody
) {}
~~~

Interface renderer:

~~~java
public interface MailTemplateRenderer {
    RenderedMail renderOrderConfirmation(OrderMailData data);
}
~~~

Service gửi:

~~~java
@Service
public class MailDeliveryService {

    private final JavaMailSender sender;

    public MailDeliveryService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(RenderedMail mail) throws MessagingException {
        MimeMessage message = sender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, "UTF-8"
        );

        helper.setTo(mail.recipient());
        helper.setSubject(mail.subject());
        helper.setText(mail.textBody(), mail.htmlBody());

        sender.send(message);
    }
}
~~~

Cấu trúc này giúp:

- Unit test renderer mà không cần SMTP.
- Unit test mail delivery với mock JavaMailSender.
- Thay template engine mà không sửa lớp vận chuyển.
- Tách lỗi template khỏi lỗi kết nối SMTP.
- Có thể lưu RenderedMail hoặc dữ liệu snapshot theo chính sách nếu cần.

Trong một hệ thống lớn, **RenderedMail** cũng có thể chứa From, Reply-To, Cc/Bcc, attachment metadata và correlation ID. Các giá trị recipient phải được kiểm soát theo nghiệp vụ; không để template quyết định người nhận.

## 10. Ví dụ render template với Mustache

Một template engine thường nhận **template** và **model**, sau đó trả về chuỗi. Ví dụ dùng Mustache với placeholder:

Tệp **src/main/resources/templates/mail/order-confirmed.html**:

~~~html
<!doctype html>
<html lang="vi">
<body>
  <h1>Xin chào {{customerName}}</h1>
  <p>Đơn hàng <strong>{{orderNumber}}</strong> đã được xác nhận.</p>
  <p>Tổng tiền: {{totalAmount}}</p>
  <p>Địa chỉ giao hàng: {{shippingAddress}}</p>
</body>
</html>
~~~

Model:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        String totalAmount,
        String shippingAddress
) {}
~~~

Renderer minh họa:

~~~java
import com.samskivert.mustache.Mustache;
import com.samskivert.mustache.Template;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;
import org.springframework.stereotype.Component;

@Component
public class OrderMailTemplateRenderer {

    private final Template template;

    public OrderMailTemplateRenderer() throws IOException {
        ClassPathResource resource =
                new ClassPathResource(
                        "templates/mail/order-confirmed.html"
                );

        String source = StreamUtils.copyToString(
                resource.getInputStream(),
                StandardCharsets.UTF_8
        );

        this.template = Mustache.compiler().compile(source);
    }

    public String render(OrderMailData data) {
        Map<String, Object> model = Map.of(
                "customerName", data.customerName(),
                "orderNumber", data.orderNumber(),
                "totalAmount", data.totalAmount(),
                "shippingAddress", data.shippingAddress()
        );

        return template.execute(model);
    }
}
~~~

Ví dụ minh họa việc nạp template từ classpath khi khởi tạo bean và compile một lần để tái sử dụng. Trong ứng dụng thực tế, cần quản lý tài nguyên/exception theo chuẩn dự án, và có thể dùng cơ chế auto-configuration của template engine nếu đã tích hợp starter tương ứng.

Mustache mặc định escape HTML cho placeholder thông thường **{{value}}** trong cách dùng phổ biến. Không dùng placeholder không escape như **{{{value}}}** cho dữ liệu người dùng trừ khi nội dung đã được làm sạch và được phép là HTML. Template engine không tự quyết định người nhận email hoặc quyền gửi.

### 10.1. Render không cần entity

Renderer chỉ nhận **OrderMailData**. Nó không biết JPA repository, transaction manager hoặc SMTP host. Nhờ đó có thể gọi nó sau commit, trong async worker hoặc trong một job retry.

### 10.2. Không render lại template cho từng trường nếu không cần

Có thể compile template một lần và tái sử dụng nếu template engine hỗ trợ. Việc đọc file và compile mỗi email có thể tạo overhead không cần thiết.

Nếu hỗ trợ hot reload hoặc template thay đổi lúc runtime, cần có chính sách cache/invalidation rõ ràng. Với template versioned cho email giao dịch, có thể compile/cache theo phiên bản.

## 11. Điều gì xảy ra nếu render thất bại sau commit?

Một lỗi template có thể xảy ra vì:

- Template file không tồn tại.
- Placeholder hoặc cú pháp template sai.
- Dữ liệu model thiếu trường bắt buộc.
- Template engine không khởi tạo được.
- Template mới không tương thích với dữ liệu cũ.
- Encoding hoặc resource bị lỗi.

Nếu render chạy sau commit, **nghiệp vụ vẫn đã được commit**. Đây thường là điều đúng: đơn hàng đã xác nhận thì lỗi template không nên tự động làm đơn hàng quay về trạng thái chưa xác nhận.

Nhưng hệ thống cần ghi nhận tác vụ email thất bại để có thể xử lý lại.

Một trạng thái đơn giản:

~~~text
PENDING
   |
   v
RENDERING
   |
   +-- lỗi --> RETRY_WAIT / FAILED
   |
   v
READY_TO_SEND
   |
   v
SENDING
   |
   +-- lỗi --> RETRY_WAIT / FAILED
   |
   v
SENT
~~~

Có thể tách riêng trạng thái render và trạng thái gửi:

| Trạng thái | Ý nghĩa |
| --- | --- |
| **PENDING** | Yêu cầu gửi đã được tạo |
| **RENDER_FAILED** | Không thể dựng nội dung từ template/model |
| **RENDERED** | Nội dung đã được tạo |
| **SEND_FAILED** | Transport không gửi được theo kết quả đã biết |
| **SENT_TO_PROVIDER** | SMTP/provider đã tiếp nhận theo phản hồi |
| **DELIVERY_CONFIRMED** | Có tín hiệu chuyển phát theo định nghĩa provider |

Không nên gọi trạng thái **SENT_TO_PROVIDER** là “người dùng đã đọc”. Đây chỉ là một mốc ở lớp gửi.

### 11.1. Phân loại lỗi

**Lỗi render** thường liên quan template, dữ liệu hoặc encoding. Sửa template/model có thể cần thiết trước khi retry.

**Lỗi SMTP tạm thời** như timeout hoặc server tạm từ chối có thể phù hợp với retry có backoff.

**Lỗi vĩnh viễn** như recipient sai cú pháp hoặc bị từ chối theo policy có thể không nên retry vô hạn.

**Kết quả không xác định** như mất kết nối sau khi server có thể đã nhận DATA cần xử lý cẩn thận vì retry có thể gửi trùng.

### 11.2. Không để exception async biến mất

Với @Async, exception không được ném trở lại request caller đã kết thúc. Hãy ghi nhận exception trong listener/worker, gửi metric/log phù hợp hoặc chuyển tác vụ sang trạng thái retry. Một **AsyncUncaughtExceptionHandler** có thể hỗ trợ ghi nhận lỗi của phương thức async trả về void, nhưng nó không thay thế hàng đợi và trạng thái bền vững.

## 12. Tránh gửi email trước khi transaction commit

Đây là nguyên tắc quan trọng nhất của thông báo nghiệp vụ.

Giả sử:

~~~text
1. Cập nhật đơn hàng thành CONFIRMED.
2. Gửi email xác nhận.
3. Một thao tác database sau đó lỗi.
4. Transaction rollback.
~~~

Kết quả có thể là:

~~~text
Database: đơn hàng chưa được xác nhận
Email: "Đơn hàng của bạn đã được xác nhận"
~~~

Hai hệ thống không còn nhất quán.

Nếu email xác nhận một thay đổi đã lưu, hãy phát hành tác vụ gửi **sau khi commit thành công**:

- Caller gọi service transactional và gửi sau khi method trả về.
- Dùng **@TransactionalEventListener(AFTER_COMMIT)**.
- Dùng **transactional outbox** để worker đọc sau commit.

Không nên dùng **BEFORE_COMMIT** cho email xác nhận thành công nếu transaction còn có thể rollback sau listener.

### 12.1. Có thể rollback email đã gửi không?

Không. SMTP là side effect bên ngoài. Database rollback chỉ tác động đến resource tham gia transaction database đó. Nó không xóa email đã được SMTP server nhận.

Nếu nghiệp vụ cần thông báo đính chính khi một hành động bị đảo ngược sau đó, hãy tạo một thông báo mới có ý nghĩa nghiệp vụ, thay vì giả định có thể thu hồi message cũ khỏi inbox.

## 13. @Transactional(propagation = NOT_SUPPORTED) có dùng được không?

Spring hỗ trợ propagation **NOT_SUPPORTED** để thực thi một phương thức mà không tham gia transaction hiện có. Nếu caller đang có transaction, Spring có thể suspend transaction đó trong thời gian gọi phương thức được proxy quản lý.

Ví dụ:

~~~java
@Service
public class MailRenderingService {

    private final MailTemplateRenderer renderer;

    public MailRenderingService(MailTemplateRenderer renderer) {
        this.renderer = renderer;
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public RenderedMail render(OrderMailData data) {
        return renderer.renderOrderConfirmation(data);
    }
}
~~~

Cách này hữu ích nếu cần bảo đảm một bước render không tham gia transaction của caller. Nhưng cần hiểu giới hạn:

- Phương thức phải được gọi qua Spring proxy để propagation có hiệu lực trong mô hình proxy thông thường.
- Nó **không tự làm cho việc gửi email bền vững**.
- Nếu renderer cần truy cập database, những thao tác đó không được bảo vệ bởi transaction đã bị suspend.
- Không truyền entity lazy vào renderer rồi kỳ vọng dữ liệu vẫn truy cập được.
- **NOT_SUPPORTED** không thay thế **AFTER_COMMIT** nếu mục tiêu là chỉ gửi khi transaction nghiệp vụ đã commit.

Vì thế, nếu chỉ muốn render và gửi sau khi nghiệp vụ thành công, ranh giới **sau commit** thường dễ diễn đạt hơn. NOT_SUPPORTED là công cụ kiểm soát propagation cho một tình huống cụ thể.

## 14. Transaction boundary và dữ liệu cần nhất quán

Một câu hỏi quan trọng: nếu render sau commit, liệu dữ liệu email có còn chính xác như lúc transaction cập nhật không?

Câu trả lời phụ thuộc vào nguồn dữ liệu renderer nhận.

### 14.1. Snapshot trong transaction

Trong transaction, đọc và định dạng dữ liệu cần thiết rồi đưa vào DTO:

~~~java
OrderMailData snapshot = new OrderMailData(
        order.getCustomerEmail(),
        order.getCustomerName(),
        order.getNumber(),
        formatMoney(order.getTotal())
);
~~~

Sau commit, renderer chỉ dùng snapshot. Đây là cách phù hợp khi email mô tả một sự kiện đã xảy ra tại thời điểm cụ thể.

### 14.2. Reload sau commit

Nếu event chỉ có orderId, worker tải đơn hàng mới nhất. Cần xác định nếu đơn hàng đã bị sửa, xóa hoặc trạng thái đã đổi thì email nên:

- Bỏ qua tác vụ?
- Render theo trạng thái mới?
- Dùng dữ liệu lịch sử?
- Đánh dấu event lỗi để xử lý thủ công?

Đây là quy tắc nghiệp vụ, không phải quyết định của template engine.

### 14.3. Dùng lịch sử hoặc version

Với các nghiệp vụ cần kiểm toán, có thể lưu phiên bản dữ liệu hoặc snapshot tại thời điểm event. Email có thể tham chiếu phiên bản đó thay vì đọc bản ghi hiện tại.

Cách này hữu ích cho hóa đơn, biên nhận, thông báo giá và xác nhận có ý nghĩa pháp lý hoặc tài chính. Cần tuân thủ chính sách lưu trữ và bảo vệ dữ liệu.

## 15. Tổ chức template và dữ liệu render

Một template email thường nên có:

- **Template key:** định danh loại email, ví dụ ORDER_CONFIRMED.
- **Locale:** ngôn ngữ/địa phương của người nhận.
- **Subject template:** mẫu tiêu đề.
- **HTML template:** nội dung HTML.
- **Plain text template:** nội dung văn bản dự phòng.
- **Model DTO:** dữ liệu cần điền.
- **Template version:** nếu cần tái tạo nội dung cũ.
- **Inline resources/attachments:** nếu template tham chiếu tài nguyên.

Ví dụ model:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        String totalAmount,
        String orderDate,
        String locale
) {}
~~~

Một cách đặt tên file:

~~~text
templates/
└── mail/
    ├── order-confirmed-vi.html
    ├── order-confirmed-vi.txt
    ├── order-confirmed-en.html
    └── order-confirmed-en.txt
~~~

Renderer có thể chọn template theo locale và loại event. Việc chọn template nên được xác định từ dữ liệu đã kiểm tra, không nhận một đường dẫn file tùy ý từ request.

### 15.1. Không để template quyết định transaction

Template chỉ trình bày dữ liệu. Không đặt logic cập nhật database, trừ tồn kho, thanh toán hoặc quyết định quyền trong template engine. Những việc đó thuộc application/domain service và transaction nghiệp vụ.

### 15.2. Không để template quyết định recipient tùy ý

Recipient là thông tin vận chuyển và có ý nghĩa bảo mật. Có thể lưu recipient trong DTO đã được xác định từ nghiệp vụ, hoặc worker tra cứu theo policy. Không nên cho nội dung template chứa placeholder để tự quyết định người nhận.

### 15.3. HTML escaping

Template engine cần escape dữ liệu động theo ngữ cảnh HTML. Với Mustache, placeholder thông thường **{{value}}** được escape theo mặc định trong cách sử dụng phổ biến; cú pháp không escape có thể đưa markup thô vào email.

Không đưa HTML do người dùng cung cấp vào template mà không có sanitizer và policy rõ ràng. Việc render ngoài transaction không thay thế kiểm soát đầu vào hoặc bảo mật HTML.

## 16. Kiểm thử khi render ngoài transaction

Khi tách template renderer và mail sender, mỗi phần có thể kiểm tra độc lập.

### 16.1. Unit test renderer

Đưa một DTO mẫu vào renderer:

~~~java
OrderMailData data = new OrderMailData(
        "customer@example.net",
        "An",
        "ORD-1001",
        "500.000 VND",
        "12/11/2026",
        "vi"
);

String html = renderer.render(data);
~~~

Có thể xác nhận kết quả có tên khách hàng, mã đơn, số tiền và không còn placeholder chưa được thay thế. Không cần SMTP server cho bài kiểm tra này.

### 16.2. Unit test mail service

Mock **JavaMailSender** để xác nhận service tạo và gửi MimeMessage. Có thể dùng **ArgumentCaptor** để lấy message và kiểm tra các header/body cần thiết theo API Jakarta Mail.

Test không nên phụ thuộc vào thứ tự ngẫu nhiên của MIME boundary hoặc byte encoding cụ thể nếu không phải yêu cầu của ứng dụng.

### 16.3. Integration test với SMTP capture server

Dùng một SMTP sandbox/capture server trong môi trường test để kiểm tra:

- Message có được SMTP transport gửi không.
- Subject, From, To có đúng không.
- HTML và plain text có được đóng gói đúng không.
- Attachment và inline resource có Content-ID phù hợp không.
- Credential/TLS của test environment được cấu hình đúng.

Không dùng hộp thư khách hàng thật cho test tự động.

### 16.4. Kiểm tra ranh giới transaction

Có thể kiểm tra listener AFTER_COMMIT chỉ chạy khi transaction commit thành công, và không chạy khi rollback. Với async/outbox, kiểm tra thêm việc event được lưu, worker có thể tiếp tục sau restart và trạng thái retry được cập nhật.

Những kiểm thử này thuộc giai đoạn kiểm thử riêng của dự án; ví dụ trong bài mô tả hành vi mong muốn chứ không tuyên bố đã chạy test trong repository.

## 17. Những lỗi thường gặp khi tách rendering khỏi transaction

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Email báo thành công dù database rollback | Gửi trước commit | Chuyển gửi sang AFTER_COMMIT hoặc outbox |
| LazyInitializationException trong renderer | Truyền JPA entity sang worker | Tạo DTO snapshot trong transaction |
| Request vẫn chờ lâu | Chỉ chuyển sang AFTER_COMMIT nhưng listener chạy đồng bộ | Dùng async executor hoặc queue khi cần |
| Email không được gửi sau restart | Event chỉ nằm trong bộ nhớ | Dùng transactional outbox/queue bền vững |
| Email bị gửi trùng | Worker crash sau SMTP accept trước khi mark sent | Thiết kế retry, event ID và xử lý duplicate |
| Template lỗi nhưng nghiệp vụ đã commit | Render xảy ra sau commit | Ghi nhận lỗi và retry/alert độc lập |
| Email dùng dữ liệu mới ngoài dự kiến | Worker reload entity sau một khoảng trễ | Lưu snapshot hoặc version dữ liệu |
| Async listener không chạy | Không có transaction hoặc event không được publish đúng chỗ | Kiểm tra transaction phase và event flow |
| Async task bị từ chối | Executor queue đầy hoặc shutdown | Giám sát queue và dùng cơ chế bền vững khi cần |
| Lỗi SMTP không quay về request | Async method không truyền exception về caller | Lưu trạng thái lỗi, log, retry hoặc dead-letter |

### 17.1. Listener không chạy vì event được publish ngoài transaction

**@TransactionalEventListener** mặc định phụ thuộc transaction. Nếu event được publish từ một phương thức không có transaction, listener AFTER_COMMIT có thể không được gọi. Hãy xác nhận event thực sự được publish trong transaction mong muốn; chỉ dùng fallbackExecution khi nghiệp vụ cho phép.

### 17.2. Gọi listener trực tiếp thay vì publish event

Nếu code gọi trực tiếp phương thức listener, annotation event listener và phase không có tác dụng như một sự kiện được Spring quản lý. Hãy dùng **ApplicationEventPublisher.publishEvent(...)** hoặc cơ chế message/queue đã chọn.

### 17.3. Dùng @Async nhưng quên bật async processing

Nếu không có **@EnableAsync** hoặc cấu hình async phù hợp, phương thức có thể không được chạy theo cơ chế async mong muốn. Ngoài ra, lời gọi nội bộ trong cùng bean có thể không đi qua proxy async.

### 17.4. Nghĩ rằng AFTER_COMMIT tự động bảo đảm exactly once

AFTER_COMMIT xác định **thời điểm listener được gọi** trong vòng đời transaction. Nó không tạo một bản ghi durable, không retry tự động và không bảo đảm SMTP chỉ tiếp nhận một lần.

### 17.5. Đánh dấu SENT trước khi SMTP chấp nhận

Nếu worker cập nhật trạng thái SENT rồi mới gọi send, process crash có thể khiến tác vụ mất mà database vẫn ghi đã gửi. Nếu gửi trước rồi mới cập nhật SENT, crash ở khoảng giữa có thể gây gửi trùng. Cần thiết kế trạng thái, retry và cách xử lý kết quả không xác định phù hợp với giới hạn của SMTP.

## 18. Chọn giải pháp theo yêu cầu nghiệp vụ

| Yêu cầu | Cách triển khai có thể phù hợp |
| --- | --- |
| Template rất nhỏ, gửi đồng bộ, không có transaction dài | Render và gửi theo luồng đơn giản |
| Chỉ cần đảm bảo email không gửi trước khi commit | Gọi sau khi transactional service trả về hoặc dùng AFTER_COMMIT |
| Request không nên chờ SMTP | AFTER_COMMIT kết hợp @Async |
| Email có thể retry sau khi process restart | Transactional outbox hoặc queue bền vững |
| Nội dung phải đúng dữ liệu tại thời điểm xác nhận | DTO snapshot lưu cùng event |
| Nội dung phải dùng trạng thái mới nhất | Worker reload dữ liệu theo policy |
| Nhiều loại email, cần theo dõi riêng | Tách renderer, delivery service và trạng thái tác vụ |
| Email có giá trị kiểm toán | Snapshot/version/template version và lịch sử xử lý |

Không có một kiến trúc duy nhất cho mọi ứng dụng. Điều cần xác định trước là email có phải **side effect bắt buộc sau commit** hay chỉ là một thông báo tiện ích; có được phép mất khi process crash không; và có thể chấp nhận gửi trùng hay không.

## 19. Gợi ý kiến trúc cho một hệ thống Spring Mail

Với ứng dụng có email giao dịch quan trọng, một kiến trúc có thể tổ chức như sau:

~~~text
HTTP / Application command
          |
          v
OrderApplicationService
    @Transactional
          |
          +-- Validate command
          +-- Update order
          +-- Build immutable mail snapshot
          +-- Insert outbox event
          |
          v
       COMMIT
          |
          v
Outbox polling worker
          |
          +-- Claim pending event
          +-- Resolve template version/locale
          +-- Render HTML and text
          +-- Build MimeMessage
          +-- JavaMailSender.send(...)
          +-- Update status/retry schedule
          |
          v
 SMTP provider
~~~

Các thành phần có trách nhiệm rõ:

- **OrderApplicationService** thay đổi dữ liệu nghiệp vụ.
- **Mail snapshot** giữ dữ liệu email cần tại thời điểm xác nhận.
- **Outbox worker** xử lý tác vụ sau commit và có thể chạy lại.
- **TemplateRenderer** tạo subject/body.
- **MailDeliveryService** dựng MIME và gọi JavaMailSender.
- **Outbox repository** quản lý trạng thái, retry và lịch sử.

Đối với ứng dụng nhỏ, có thể bỏ outbox và dùng service gọi sau commit. Khi yêu cầu tin cậy tăng lên, có thể chuyển sang outbox mà không cần nhét logic SMTP vào domain service.

## 20. Ghi nhớ khi render template ngoài transaction nghiệp vụ

**Transaction nghiệp vụ** nên tập trung vào việc thay đổi và commit dữ liệu cần nhất quán. **Render template** chuyển model thành nội dung email; **gửi thư** là side effect với một hệ thống bên ngoài. Tách ba trách nhiệm này giúp transaction ngắn hơn, tránh gửi email cho thay đổi rollback và cho phép xử lý lỗi gửi độc lập.

Cách làm nền tảng là tạo **DTO snapshot trong transaction**, để transaction commit, rồi mới render và gửi. Nếu muốn xử lý sau commit theo sự kiện, dùng **@TransactionalEventListener(AFTER_COMMIT)**. Nếu request không nên chờ, kết hợp **@Async** hoặc worker queue. Nếu ý định gửi phải sống sót qua restart và có retry bền vững, dùng **transactional outbox**.

Hãy nhớ các giới hạn: AFTER_COMMIT không tự durable; @Async không tự retry; outbox không bảo đảm SMTP exactly-once; và entity JPA không nên được truyền sang renderer/worker. Chọn ranh giới phù hợp với yêu cầu nhất quán, thời gian phản hồi và độ tin cậy của email trong nghiệp vụ.

# Khi tách gửi mail sang tác vụ bất đồng bộ

Gửi email qua SMTP có thể mất thời gian vì phải phân giải DNS, mở kết nối, xác thực, truyền MIME message và chờ mail server phản hồi. Nếu thực hiện toàn bộ việc này ngay trong luồng xử lý HTTP, người dùng phải chờ lâu hơn và request có thể timeout dù nghiệp vụ chính đã hoàn tất.

Trong Spring, có thể tách việc gửi mail sang một tác vụ chạy ở thread khác bằng annotation **@Async**. Khi đó, luồng chính ghi nhận yêu cầu gửi rồi tiếp tục công việc của nó; một executor nhận tác vụ và thực hiện render template, tạo MIME message, gọi **JavaMailSender** ở phía sau.

Tuy nhiên, bất đồng bộ chỉ thay đổi **thời điểm và thread thực thi**. Nó không tự tạo hàng đợi bền vững, không bảo đảm tác vụ không bị mất khi ứng dụng dừng, không tự retry an toàn và cũng không bảo đảm email đã tới Inbox. Cần chọn đúng mô hình theo yêu cầu độ tin cậy của ứng dụng.

## 1. Vì sao cần tách gửi mail khỏi luồng chính?

Giả sử người dùng xác nhận đơn hàng. Ứng dụng cần cập nhật trạng thái đơn và gửi email xác nhận.

Nếu gửi đồng bộ:

```text
HTTP request
    |
    v
Kiểm tra và xác nhận đơn hàng
    |
    v
Tạo MIME message
    |
    v
Kết nối SMTP và gửi email
    |
    v
Chờ SMTP phản hồi
    |
    v
Trả HTTP response
```

Thời gian phản hồi HTTP bao gồm cả thời gian gửi mail. Nếu SMTP chậm, request cũng chậm theo. Một số hệ quả:

- Người dùng phải chờ dù dữ liệu đơn hàng đã được lưu.
- Gateway hoặc browser có thể timeout và gửi lại request.
- Thread xử lý HTTP bị chiếm trong lúc chờ mạng.
- Một đợt gửi mail lớn có thể làm giảm khả năng phục vụ request khác.
- Lỗi SMTP có thể ảnh hưởng trực tiếp tới response của nghiệp vụ.

Khi tách gửi mail sang tác vụ bất đồng bộ:

```text
HTTP request
    |
    v
Xác nhận đơn hàng
    |
    v
Ghi nhận yêu cầu gửi mail
    |
    +-----------------------> Trả HTTP response
    |
    v
Mail executor / worker
    |
    v
Render template
    |
    v
JavaMailSender.send(...)
    |
    v
Ghi nhận kết quả
```

Luồng chính có thể trả response sớm sau khi đã ghi nhận công việc. Worker thực hiện gửi mail độc lập.

### Những trường hợp phù hợp

- Gửi email xác nhận sau khi một thao tác nghiệp vụ đã được ghi nhận.
- Gửi thông báo không cần kết quả SMTP ngay trong response.
- Gửi báo cáo hoặc bản tổng hợp có thời gian tạo nội dung dài.
- Gửi nhiều email sau một sự kiện nghiệp vụ.
- Gửi email có attachment cần dựng từ dữ liệu hoặc file.
- Giảm thời gian giữ HTTP request khi SMTP phản hồi chậm.

### Khi nào không nên chỉ dùng @Async?

Nếu yêu cầu là không mất email khi ứng dụng restart, cần retry sau sự cố, xử lý backlog, theo dõi trạng thái và scale worker độc lập, một executor trong memory thường chưa đủ. Khi đó nên lưu yêu cầu gửi vào database/outbox hoặc một message broker bền vững rồi dùng worker xử lý.

## 2. Bất đồng bộ không có nghĩa là gửi nhanh hơn

@Async giúp luồng gọi không phải chờ thao tác gửi hoàn tất. Nó không làm SMTP truyền dữ liệu nhanh hơn. Thời gian thực hiện của worker vẫn phụ thuộc vào:

- DNS và kết nối mạng.
- SMTP server và xác thực.
- Kích thước HTML, inline image và attachment.
- Số lượng recipient.
- Giới hạn tốc độ của provider.
- Thời gian render template hoặc đọc file.

Nếu executor có quá ít thread hoặc queue quá nhỏ, tác vụ có thể phải chờ trước khi bắt đầu. Nếu có quá nhiều thread, ứng dụng có thể mở quá nhiều kết nối SMTP và vượt quota của provider.

Vì vậy, mục tiêu của async là **tách thời gian chờ gửi mail khỏi luồng chính và kiểm soát tải**, không phải loại bỏ thời gian gửi.

## 3. @Async hoạt động như thế nào trong Spring?

Spring hỗ trợ thực thi method bất đồng bộ thông qua annotation @Async và một TaskExecutor. Khi một method được gọi qua Spring proxy, proxy gửi lời gọi tới executor đã cấu hình và trả quyền điều khiển cho caller theo kiểu return của method.

Để bật tính năng này, dùng @EnableAsync:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

Một service có thể đánh dấu method:

```java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncMailService {

    @Async
    public void sendNotification(String recipient) {
        // Tạo message và gửi mail ở executor thread.
    }
}
```

Khi một bean khác gọi method này qua Spring bean proxy, phần thân method được thực thi ở thread của executor. Caller không phải chờ method void hoàn tất.

### @Async dựa trên proxy

Trong cấu hình proxy mặc định, lời gọi phải đi qua Spring proxy. Ví dụ sau thường không chạy async:

```java
@Service
public class MailService {

    public void processOrder() {
        sendConfirmation(); // self-invocation
    }

    @Async
    public void sendConfirmation() {
        // Gọi nội bộ trong cùng object.
    }
}
```

Lời gọi nội bộ từ processOrder() tới sendConfirmation() không đi qua proxy, vì vậy annotation có thể không được áp dụng.

Cách tổ chức dễ hiểu hơn là đặt tác vụ async trong một bean riêng:

```java
@Service
public class OrderService {

    private final AsyncMailService asyncMailService;

    public OrderService(AsyncMailService asyncMailService) {
        this.asyncMailService = asyncMailService;
    }

    public void confirmOrder(Order order) {
        // Lưu và xác nhận nghiệp vụ.
        asyncMailService.sendConfirmation(order.getCustomerEmail());
    }
}

@Service
public class AsyncMailService {

    @Async("mailTaskExecutor")
    public void sendConfirmation(String recipient) {
        // Tạo và gửi email.
    }
}
```

Ở đây lời gọi từ OrderService tới AsyncMailService đi qua proxy của bean async.

### Những điều kiện thường gặp

- Có @EnableAsync hoặc cấu hình async tương đương.
- Method được gọi qua Spring proxy.
- Bean được Spring quản lý.
- Method có visibility và kiểu khai báo phù hợp với cơ chế proxy đang dùng.
- Executor được cấu hình và còn khả năng nhận task.

Đừng giả định cứ thêm @Async vào một method bất kỳ là nó tự chạy ở thread khác.

## 4. Cấu hình executor riêng cho gửi mail

Nếu không chỉ định executor, Spring có thể dùng executor mặc định được tìm thấy trong application context hoặc cơ chế fallback. Đối với ứng dụng thực tế, nên cấu hình executor riêng cho mail để kiểm soát thread, queue và chính sách khi quá tải.

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean(name = "mailTaskExecutor")
    public Executor mailTaskExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("mail-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );

        return executor;
    }
}
```

Sau đó chỉ định tên executor:

```java
@Async("mailTaskExecutor")
public void sendWelcomeEmail(String recipient) {
    // ...
}
```

Các con số trong ví dụ chỉ là điểm bắt đầu. Cần đo thời gian gửi, số lượng email, quota SMTP và tài nguyên máy chủ để điều chỉnh.

### Ý nghĩa các cấu hình

| Cấu hình | Ý nghĩa |
| --- | --- |
| corePoolSize | Số thread nền được duy trì theo cấu hình |
| maxPoolSize | Giới hạn thread tối đa khi tải tăng |
| queueCapacity | Số task có thể chờ trong queue |
| threadNamePrefix | Prefix giúp nhận diện mail thread trong log và thread dump |
| waitForTasksToCompleteOnShutdown | Yêu cầu executor chờ task đã nhận hoàn tất khi shutdown theo cấu hình |
| awaitTerminationSeconds | Thời gian chờ tối đa trong giai đoạn shutdown |

Với ThreadPoolTaskExecutor, khi các core thread đang bận, task thường được đưa vào queue trước; chỉ khi queue đầy executor mới mở thêm thread tới max pool size. Khi cả queue và pool đều đầy, rejection policy được áp dụng.

### Không đặt queue vô hạn một cách tùy tiện

Queue vô hạn có thể khiến ứng dụng tiếp tục nhận task trong khi SMTP không xử lý kịp. Bộ nhớ sẽ tăng dần, thời gian chờ cũng dài hơn và ứng dụng có thể gặp OutOfMemoryError.

Queue có giới hạn giúp tạo backpressure. Khi queue đầy, ứng dụng phải có chính sách rõ ràng:

- Từ chối nhận thêm task và ghi nhận lỗi.
- Chuyển yêu cầu sang outbox/broker bền vững.
- Giới hạn tốc độ tạo notification.
- Dùng một chính sách chạy task ở caller thread nếu chấp nhận caller bị chặn.

Không dùng chính sách discard im lặng cho email nghiệp vụ quan trọng, vì task có thể bị bỏ mà không có dấu hiệu rõ ràng.

## 5. Chính sách khi executor quá tải

Executor có thể không nhận thêm task nếu thread pool và queue đã đầy. Một số rejection policy:

| Policy | Hành vi | Tác động |
| --- | --- | --- |
| Abort | Ném exception khi không nhận task được | Caller biết việc enqueue thất bại và có thể xử lý |
| CallerRuns | Thread gọi chạy task | Tạo backpressure nhưng có thể làm request chậm |
| Discard | Bỏ task mới | Có nguy cơ mất email âm thầm |
| DiscardOldest | Bỏ task cũ nhất trong queue rồi thử nhận task mới | Có nguy cơ mất một yêu cầu đã chờ |

Với email giao dịch, policy từ chối rõ ràng hoặc lưu vào outbox thường dễ kiểm soát hơn việc âm thầm bỏ task.

Ví dụ cấu hình Abort:

```java
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy()
);
```

Khi bị từ chối, caller cần xử lý exception hoặc ghi nhận yêu cầu vào một nơi bền vững. Không bắt exception rồi bỏ qua.

### CallerRuns có phù hợp không?

CallerRuns có thể giúp giảm tốc độ producer vì thread gọi phải tự chạy task. Nhưng nếu caller là HTTP request thread, request có thể lại phải chờ SMTP. Đây có thể là backpressure có chủ đích, nhưng cần đánh giá timeout và trải nghiệm người dùng.

Nếu yêu cầu gửi phải được bảo toàn khi executor quá tải, hãy ghi notification/outbox trước; executor chỉ là một cách đánh thức worker hoặc xử lý batch.

## 6. Dùng CompletableFuture để nhận kết quả bất đồng bộ

Method trả về void phù hợp khi caller không cần nhận kết quả trực tiếp. Nếu muốn quan sát kết quả hoặc exception, có thể dùng CompletableFuture.

Ví dụ:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncMailService {

    @Async("mailTaskExecutor")
    public CompletableFuture<String> sendReceipt(
            String recipient
    ) {
        // mailSender.send(message);
        return CompletableFuture.completedFuture(
                "SMTP submission completed for " + recipient
        );
    }
}
```

Spring chạy method ở executor và cung cấp future cho caller. Khi method hoàn tất, future được hoàn thành; nếu method ném exception, future hoàn thành ở trạng thái exceptional.

Caller có thể đăng ký callback:

```java
CompletableFuture<String> result =
        asyncMailService.sendReceipt(recipient);

result.whenComplete((value, error) -> {
    if (error != null) {
        // Ghi log/correlation hoặc cập nhật trạng thái phù hợp.
        return;
    }

    // Xử lý kết quả đã nhận được.
});
```

Không gọi join() hoặc get() ngay sau khi gọi async nếu mục tiêu là trả response sớm:

```java
// Làm mất lợi ích bất đồng bộ:
asyncMailService.sendReceipt(recipient).join();
```

Lời gọi này khiến caller chờ future hoàn tất. Hãy chỉ chờ khi luồng nghiệp vụ thật sự cần kết quả trước khi tiếp tục.

### CompletableFuture không phải queue bền vững

Future chỉ đại diện cho kết quả của một computation trong tiến trình hiện tại. Nếu process bị kill, future và task trong memory có thể mất. Không dùng future thay cho database/outbox khi cần khôi phục công việc sau restart.

### Tránh dùng chung pool cho callback nặng

Các callback như thenApplyAsync hoặc whenCompleteAsync có thể chạy trên executor khác tùy overload được dùng. Nếu callback thực hiện nhiều I/O hoặc xử lý nặng, hãy chỉ định executor phù hợp để không làm nghẽn common pool hoặc mail executor.

## 7. Ví dụ hoàn chỉnh: gửi email xác nhận bất đồng bộ

Giả sử ứng dụng đã xác nhận đơn hàng và cần gửi email cho khách. Ví dụ dùng:

- JavaMailSender để gửi SMTP.
- MimeMessageHelper để tạo HTML và plain text.
- Thymeleaf để render template.
- Executor riêng tên mailTaskExecutor.

### 7.1. Cấu hình executor

```java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailTaskExecutor")
    public Executor mailTaskExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );
        return executor;
    }
}
```

Spring quản lý lifecycle của executor bean; trong cấu hình này không cần tự gọi initialize() khi bean được khởi tạo theo lifecycle thông thường của Spring.

### 7.2. DTO truyền sang worker

Không nên truyền một JPA entity đang được quản lý sang thread nền rồi truy cập lazy relationship sau khi transaction của request kết thúc. Hãy chuẩn bị dữ liệu cần thiết thành DTO bất biến:

```java
import java.util.Locale;

public record OrderConfirmationMail(
        String recipient,
        String customerName,
        String orderCode,
        String orderUrl,
        String totalAmountLabel,
        Locale locale
) {}
```

DTO chỉ chứa dữ liệu mà mail worker cần. Điều này tránh phụ thuộc vào persistence context của thread khác và giúp biết rõ dữ liệu được dùng khi gửi.

### 7.3. Async mail service

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

@Service
public class AsyncOrderMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;

    public AsyncOrderMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine
    ) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
    }

    @Async("mailTaskExecutor")
    public CompletableFuture<Void> sendConfirmation(
            OrderConfirmationMail data
    ) throws MessagingException {
        Context context = new Context(data.locale());
        context.setVariable("customerName", data.customerName());
        context.setVariable("orderCode", data.orderCode());
        context.setVariable("orderUrl", data.orderUrl());
        context.setVariable(
                "totalAmountLabel",
                data.totalAmountLabel()
        );

        String html = templateEngine.process(
                "mail/order-confirmation",
                context
        );

        String plain = "Xin chào " + data.customerName() + ".\n"
                + "Đơn hàng " + data.orderCode()
                + " đã được xác nhận.\n"
                + "Tổng tiền: " + data.totalAmountLabel() + "\n"
                + "Xem đơn hàng: " + data.orderUrl();

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                StandardCharsets.UTF_8.name()
        );
        helper.setFrom("notifications@example.org");
        helper.setTo(data.recipient());
        helper.setSubject(
                "Xác nhận đơn hàng " + data.orderCode()
        );
        helper.setText(plain, html);

        mailSender.send(message);
        return CompletableFuture.completedFuture(null);
    }
}
```

Trong ví dụ, method chỉ hoàn thành future sau khi mailSender.send trả về. Kết quả này thể hiện SMTP transport đã chấp nhận thao tác gửi theo kết quả mà ứng dụng quan sát được; nó không chứng minh thư đã tới Inbox.

Địa chỉ sender là ví dụ và phải thay bằng địa chỉ đã được provider cho phép. Dữ liệu URL cần được backend tạo từ domain tin cậy; nội dung template dùng th:text cho giá trị văn bản.

### 7.4. Gọi từ service nghiệp vụ

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final AsyncOrderMailService asyncMailService;

    public OrderApplicationService(
            OrderRepository orderRepository,
            AsyncOrderMailService asyncMailService
    ) {
        this.orderRepository = orderRepository;
        this.asyncMailService = asyncMailService;
    }

    @Transactional
    public UUID confirmOrder(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();
        orderRepository.save(order);

        OrderConfirmationMail mailData =
                new OrderConfirmationMail(
                        order.getCustomerEmail(),
                        order.getCustomerName(),
                        order.getCode(),
                        buildOrderUrl(order.getId()),
                        formatAmount(order.getTotalAmount()),
                        Locale.forLanguageTag("vi-VN")
                );

        asyncMailService.sendConfirmation(mailData);
        return order.getId();
    }
}
```

Đoạn code giúp minh họa cách tạo DTO rồi gọi bean async. Nhưng có một điểm transaction quan trọng: method async có thể bắt đầu chạy **trước khi transaction của caller commit**. Nếu worker cần đọc lại dữ liệu vừa ghi, nó có thể không nhìn thấy thay đổi hoặc đọc trạng thái cũ.

Với ví dụ này, DTO đã chứa snapshot dữ liệu cần render nên worker không cần đọc lại entity. Tuy nhiên, việc gọi async trước commit vẫn có thể tạo email xác nhận cho một transaction sau đó rollback. Phần tiếp theo trình bày cách xử lý đúng cho trường hợp cần gắn việc gửi với commit nghiệp vụ.

## 8. Quan hệ giữa @Async và @Transactional

@Transactional và @Async điều khiển hai khía cạnh khác nhau:

- @Transactional quản lý transaction của các resource tham gia transaction manager, thường là database.
- @Async chuyển method sang executor thread.

Transaction thread của caller **không tự động được truyền sang thread async**. Worker chạy trong thread khác và cần transaction riêng nếu phải thao tác database.

Ví dụ:

```java
@Async("mailTaskExecutor")
@Transactional
public CompletableFuture<Void> sendAndRecord(
        MailNotification notification
) {
    // Transaction này thuộc worker thread.
}
```

Nếu annotation được áp dụng qua proxy và method được gọi đúng cách, transaction được mở trong worker theo cấu hình transaction manager. Nó không phải continuation của transaction caller.

### Không gửi email trước khi nghiệp vụ commit nếu cần tính nhất quán

Xét luồng:

```text
Caller transaction
  update order
  gọi async mail
       |
       +---- worker có thể bắt đầu gửi
       |
  transaction rollback
       |
       v
Email xác nhận có thể đã được gửi
trong khi đơn hàng không được xác nhận
```

Nếu email chỉ được gửi sau khi nghiệp vụ commit, cần một cơ chế phối hợp:

- Ghi notification/outbox trong cùng transaction và worker đọc sau commit.
- Hoặc dùng event listener chạy sau commit khi chấp nhận giới hạn mất event nếu process crash.

### @TransactionalEventListener(AFTER_COMMIT)

Với tác vụ nhẹ và chấp nhận giới hạn durability, có thể phát application event trong transaction rồi xử lý sau commit:

```java
public record OrderConfirmedEvent(
        UUID orderId,
        String recipient,
        String customerName,
        String orderCode,
        String orderUrl
) {}
```

Phát event:

```java
applicationEventPublisher.publishEvent(
        new OrderConfirmedEvent(
                order.getId(),
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getCode(),
                buildOrderUrl(order.getId())
        )
);
```

Listener:

```java
@Component
public class OrderMailListener {

    private final AsyncOrderMailService mailService;

    public OrderMailListener(AsyncOrderMailService mailService) {
        this.mailService = mailService;
    }

    @Async("mailTaskExecutor")
    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        OrderConfirmationMail data =
                new OrderConfirmationMail(
                        event.recipient(),
                        event.customerName(),
                        event.orderCode(),
                        event.orderUrl(),
                        null,
                        Locale.forLanguageTag("vi-VN")
                );
        mailService.sendConfirmation(data);
    }
}
```

Đây là ví dụ minh họa cơ chế event. Cũng cần xác minh cách kết hợp annotation và proxy trong cấu hình Spring đang dùng.

AFTER_COMMIT giúp listener chỉ chạy sau khi transaction commit. Nhưng application event thường nằm trong memory của tiến trình. Nếu ứng dụng chết sau commit và trước khi listener chạy, notification có thể bị mất. Với email quan trọng, transactional outbox đáng tin cậy hơn.

## 9. Transactional outbox cho tác vụ gửi mail bền vững

Nếu email không được phép mất khi ứng dụng restart, hãy ghi yêu cầu gửi vào database trong cùng transaction với nghiệp vụ. Một worker đọc outbox rồi gửi.

Luồng:

```text
Transaction nghiệp vụ
  |
  +-- cập nhật order
  +-- tạo mail_notification PENDING
  +-- tạo outbox row
  |
  v
COMMIT
  |
  v
Outbox worker / scheduler
  |
  v
Claim notification
  |
  v
Render và gửi qua JavaMailSender
  |
  v
Ghi SUBMITTED / RETRY_WAIT / FAILED / UNKNOWN
```

Vì notification và thay đổi nghiệp vụ cùng commit, hệ thống không rơi vào trường hợp đơn hàng đã commit nhưng yêu cầu gửi chỉ tồn tại trong memory của thread async.

### Ví dụ ghi outbox

```java
@Transactional
public UUID confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    UUID notificationId = UUID.randomUUID();
    MailPayload payload = MailPayload.from(order);

    mailNotificationRepository.insertPending(
            notificationId,
            "ORDER_CONFIRMED",
            order.getId().toString(),
            payload
    );

    outboxRepository.insert(
            UUID.randomUUID(),
            notificationId,
            "MAIL_NOTIFICATION_CREATED"
    );

    return notificationId;
}
```

Đây là ví dụ rút gọn. Cần có unique constraint theo business event để hai lần gọi confirmOrder hoặc hai listener không tạo cùng notification. Nếu thao tác xác nhận đơn hàng vốn đã idempotent, trạng thái đơn hàng và notification cần được cập nhật theo cùng quy tắc.

### Outbox không tự bảo đảm email chỉ gửi một lần

Outbox bảo đảm yêu cầu gửi không bị mất khi transaction nghiệp vụ commit. Worker thường xử lý theo mô hình at-least-once: một event có thể được đọc lại nếu worker chết hoặc mất xác nhận. Vì vậy, worker vẫn cần notification ID ổn định, cơ chế claim và cách xử lý kết quả gửi.

Outbox giải quyết atomicity giữa database và việc ghi nhận công việc; nó không biến SMTP thành một hệ thống exactly-once.

## 10. Truyền dữ liệu sang thread async

Thread async không chia sẻ toàn bộ ngữ cảnh của thread HTTP. Không nên truyền object phụ thuộc vào request hoặc persistence context đã kết thúc.

### Truyền DTO bất biến

Nên chuẩn bị các giá trị cần thiết trước khi gọi async:

```java
public record WelcomeMailData(
        String recipient,
        String displayName,
        String activationUrl,
        Locale locale
) {}
```

Worker nhận DTO:

```java
@Async("mailTaskExecutor")
public CompletableFuture<Void> sendWelcome(WelcomeMailData data) {
    // Chỉ dùng dữ liệu trong DTO và các bean thread-safe.
    return CompletableFuture.completedFuture(null);
}
```

Cách này giúp worker không cần truy cập:

- HttpServletRequest hoặc request-scoped bean sau khi request kết thúc.
- JPA entity có lazy relationship ngoài persistence context.
- Mutable collection đang bị caller tiếp tục thay đổi.
- Stream hoặc file handle đã đóng.

### Không truyền JPA entity sang worker để lazy-load

Ví dụ dễ lỗi:

```java
@Async("mailTaskExecutor")
public void sendOrderMail(Order order) {
    String customerName = order.getCustomer().getName();
    // Có thể lỗi LazyInitializationException.
}
```

Hãy tải và chuẩn hóa dữ liệu trong transaction caller, sau đó truyền DTO. Nếu worker cần truy vấn database, worker có thể gọi service/repository trong transaction riêng với ID cần thiết.

### Resource và stream

Nếu email có attachment:

- Dùng resource có vòng đời rõ ràng.
- Không truyền một InputStream đã đọc hoặc sắp bị đóng.
- Có thể lưu file trong object storage và truyền storage key.
- Hoặc đọc dữ liệu thành byte array nếu kích thước phù hợp.
- Giới hạn kích thước file để tránh chiếm nhiều heap trong queue/task.

Không giữ một stream dùng chung cho nhiều task đồng thời.

## 11. Truyền SecurityContext, MDC và thông tin tracing

Một số ngữ cảnh không tự động đi theo thread mới:

- MDC chứa correlation ID.
- SecurityContext của Spring Security.
- Trace/span context của observability framework.
- Locale hoặc tenant context do ứng dụng tự quản lý.

Nếu log ở worker cần correlation ID, có thể dùng TaskDecorator để sao chép MDC:

```java
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

import java.util.Map;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> contextMap = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (contextMap != null) {
                    MDC.setContextMap(contextMap);
                } else {
                    MDC.clear();
                }
                task.run();
            } finally {
                if (previous != null) {
                    MDC.setContextMap(previous);
                } else {
                    MDC.clear();
                }
            }
        };
    }
}
```

Gắn decorator vào executor:

```java
executor.setTaskDecorator(new MdcTaskDecorator());
```

Đây là ví dụ cho MDC. Với tracing, ưu tiên tích hợp context propagation do framework observability đang dùng cung cấp. Với Spring Security, có thể dùng DelegatingSecurityContextAsyncTaskExecutor khi thật sự cần mang SecurityContext sang worker.

Không sao chép transaction context thủ công sang thread khác. Transaction resource thường gắn với thread và transaction manager; worker nên mở transaction riêng khi cần.

### Có nên truyền SecurityContext vào mail worker?

Thông thường, worker chỉ cần dữ liệu nghiệp vụ và tenant đã được xác thực/ủy quyền ở bước tạo notification. Nếu worker cần SecurityContext vì một lý do cụ thể, hãy dùng cơ chế propagation có kiểm soát và tránh giữ thông tin đăng nhập lâu hơn cần thiết.

## 12. Xử lý exception trong @Async

Exception ở worker không tự quay về call stack của caller như một method đồng bộ.

### Method trả về void

```java
@Async("mailTaskExecutor")
public void sendNotice(String recipient) {
    mailSender.send(buildMessage(recipient));
}
```

Caller thường không bắt được exception xảy ra sau khi method đã được dispatch. Với method void, có thể cấu hình AsyncUncaughtExceptionHandler để ghi nhận lỗi:

```java
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;

import java.lang.reflect.Method;
import java.util.concurrent.Executor;

@Configuration
public class AsyncErrorConfiguration implements AsyncConfigurer {

    @Override
    public Executor getAsyncExecutor() {
        return mailTaskExecutor();
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, params) -> {
            // Ghi log method, exception và correlation ID.
        };
    }
}
```

Đây là cấu trúc minh họa; nếu ứng dụng đã khai báo nhiều executor có tên, hãy giữ cấu hình @Async("mailTaskExecutor") rõ ràng và tránh vô tình tạo một executor mặc định khác.

Handler chỉ giúp quan sát exception. Nó không tự retry, không lưu notification thất bại và không khôi phục task sau restart.

### Method trả về CompletableFuture

Với future, exception được biểu diễn trong trạng thái exceptional:

```java
@Async("mailTaskExecutor")
public CompletableFuture<Void> sendNotice(String recipient) {
    mailSender.send(buildMessage(recipient));
    return CompletableFuture.completedFuture(null);
}
```

Caller có thể quan sát:

```java
asyncMailService.sendNotice(recipient)
        .whenComplete((result, error) -> {
            if (error != null) {
                // Ghi nhận lỗi hoặc chuyển trạng thái.
            }
        });
```

Không để callback chỉ log rồi coi như đã xử lý xong nếu nghiệp vụ yêu cầu retry. Cần có notification record hoặc outbox để biết task nào phải được xử lý lại.

## 13. Gửi mail async và HTTP response

Nếu endpoint chỉ cần xác nhận rằng yêu cầu gửi đã được ghi nhận, có thể trả 202 Accepted:

```java
@PostMapping("/orders/{orderId}/send-confirmation")
public ResponseEntity<MailRequestReceipt> sendConfirmation(
        @PathVariable UUID orderId
) {
    MailRequestReceipt receipt =
            orderApplicationService.requestConfirmation(orderId);

    return ResponseEntity.accepted().body(receipt);
}
```

Response có thể chứa:

```json
{
  "notificationId": "7f6b9c5e-...",
  "status": "PENDING"
}
```

Điều này có nghĩa server đã ghi nhận yêu cầu gửi theo API contract. Nó không có nghĩa email đã được SMTP chấp nhận hoặc đã tới Inbox.

Client có thể dùng notification ID để tra trạng thái qua endpoint riêng, sau khi server kiểm tra quyền truy cập.

### Tránh trả kết quả gửi thành công quá sớm

Không nên trả status SENT ngay sau khi gọi method @Async. Tại thời điểm đó worker có thể chưa bắt đầu, queue có thể bị đầy hoặc SMTP có thể thất bại. Dùng trạng thái ACCEPTED/PENDING để diễn tả việc nhận yêu cầu.

## 14. Giới hạn tốc độ và kiểm soát số email đồng thời

SMTP provider thường có quota:

- Số kết nối đồng thời.
- Số message mỗi giây/phút.
- Số recipient mỗi message.
- Tổng dung lượng gửi theo ngày.
- Giới hạn kích thước message.

Nếu cấu hình maxPoolSize quá cao, nhiều worker có thể cùng kết nối SMTP và vượt giới hạn. Điều này có thể gây lỗi 4xx, throttling hoặc tạm khóa tài khoản.

Hãy điều chỉnh executor theo:

1. Throughput thực tế của SMTP/provider.
2. Thời gian trung bình và percentile của một lần gửi.
3. Kích thước queue.
4. Tài nguyên CPU, memory và connection của ứng dụng.
5. Số instance đang chạy.

Nếu có nhiều instance, tổng số worker là tổng pool size của tất cả instance. Ví dụ ba instance, mỗi instance có max pool size 8, có thể tạo tối đa 24 tác vụ gửi đồng thời.

### Giới hạn ở cấp hệ thống

Thread pool chỉ giới hạn concurrency trong một instance. Nếu cần giới hạn toàn hệ thống hoặc theo tenant, cần rate limiter/distributed coordination hoặc broker consumer concurrency được cấu hình phù hợp.

Không chỉ tăng thread pool để xử lý backlog. Nếu provider đang throttle, tăng concurrency có thể làm lỗi nhiều hơn.

## 15. Theo dõi queue, thời gian gửi và kết quả

Một hệ thống async cần quan sát được task đang chờ và đang chạy.

Các metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| Active threads | Số thread đang thực thi |
| Pool size | Số thread hiện có |
| Queue size | Số task đang chờ |
| Queue remaining capacity | Sức chứa còn lại |
| Task rejection count | Số task bị executor từ chối |
| Mail submission duration | Thời gian gọi send hoàn tất |
| Mail success/failure count | Số lần gửi được chấp nhận/lỗi |
| Retry count | Số attempt lại |
| Outbox lag | Độ trễ từ lúc tạo notification tới lúc xử lý |
| Unknown outcome count | Số lần kết quả SMTP chưa xác định |

Log nên gắn với một notification ID hoặc correlation ID:

```text
notificationId=N-123
template=order-confirmation/v2
executor=mailTaskExecutor
thread=mail-3
attempt=1
result=SUBMITTED
```

Không log toàn bộ nội dung email, password, token hoặc dữ liệu cá nhân không cần thiết.

### Thread name prefix giúp điều tra

Khi thread có tên mail-3, thread dump và log cho thấy công việc thuộc mail executor. Đây là chi tiết nhỏ nhưng hữu ích khi ứng dụng có nhiều executor cho các tác vụ nền khác nhau.

## 16. Shutdown và deploy ứng dụng

Khi ứng dụng shutdown, executor có thể:

- Ngừng nhận task mới.
- Chờ task đang chạy hoàn tất.
- Chờ task trong queue theo cấu hình.
- Hủy hoặc từ chối task còn lại khi hết thời gian shutdown.

waitForTasksToCompleteOnShutdown và awaitTerminationSeconds giúp xử lý shutdown có trật tự trong điều kiện process được phép shutdown bình thường. Nhưng chúng không bảo đảm task sống sót khi:

- Máy chủ bị tắt đột ngột.
- Container bị kill trước khi hết grace period.
- Process crash.
- OOM killer dừng JVM.
- Orchestrator buộc dừng sau timeout.

Task chỉ nằm trong executor memory có thể mất trong các tình huống này. Nếu email phải được gửi sau khi restart, hãy lưu yêu cầu trong outbox hoặc broker bền vững.

### Đặt thời gian graceful shutdown phù hợp

Thời gian chờ shutdown nên tương quan với:

- Timeout kết nối/read/write SMTP.
- Kích thước attachment.
- Thời gian render.
- Số task đang chạy.
- Grace period của container/orchestrator.

Nếu một task có thể treo lâu hơn thời gian shutdown, cần timeout mạng và chính sách phục hồi rõ ràng. Không dựa vào việc chờ vô hạn.

## 17. Retry cho tác vụ async

Một method @Async thất bại không tự động được đưa lại vào executor. Muốn retry cần một cơ chế riêng.

### Retry trong memory

Có thể gọi lại một method hoặc dùng retry framework, nhưng task và trạng thái vẫn phụ thuộc vào tiến trình hiện tại. Khi restart, retry schedule trong memory có thể mất.

### Retry bằng notification/outbox

Với email nghiệp vụ, cách bền vững hơn:

1. Ghi notification với ID ổn định.
2. Worker claim notification.
3. Gửi qua SMTP.
4. Phân loại lỗi.
5. Nếu lỗi tạm thời đã biết, ghi RETRY_WAIT và next_attempt_at.
6. Worker lấy lại khi tới hạn.
7. Nếu kết quả không rõ, ghi UNKNOWN và reconcile.

SMTP có thể đã nhận message nhưng response bị mất. Không retry mù mọi timeout vì có thể gửi trùng. Nếu provider có API idempotency, dùng key ổn định theo notification theo đúng hợp đồng provider.

### Backoff và giới hạn attempt

Ví dụ lịch retry:

```text
Attempt 1: gửi lần đầu
Attempt 2: sau 30 giây
Attempt 3: sau 2 phút
Attempt 4: sau 10 phút
Attempt 5: sau 30 phút
```

Lịch cụ thể phụ thuộc provider và loại email. Cần thêm jitter, giới hạn attempt và dead-letter/review flow. Lỗi xác thực, template sai hoặc recipient không hợp lệ thường cần xử lý cấu hình/dữ liệu thay vì retry liên tục.

## 18. Phân biệt trạng thái của tác vụ và trạng thái email

Một tác vụ async có thể đã hoàn tất việc gọi SMTP, nhưng email chưa chắc đã được giao tới mailbox.

| Trạng thái | Ý nghĩa |
| --- | --- |
| PENDING | Yêu cầu đã được ghi nhận |
| QUEUED | Đang chờ executor/worker |
| PROCESSING | Worker đang xử lý |
| SUBMITTED | SMTP/provider chấp nhận message |
| DELIVERED | Provider có bằng chứng giao tới hệ thống nhận, nếu có hỗ trợ event |
| BOUNCED | Provider nhận thông tin bounce |
| RETRY_WAIT | Chờ lần thử tiếp theo |
| FAILED | Lỗi cuối theo policy |
| UNKNOWN | Không xác định được SMTP/provider đã nhận hay chưa |

Không đổi trạng thái thành DELIVERED chỉ vì JavaMailSender.send() không ném exception. SMTP acceptance và delivery là hai sự kiện khác nhau.

Nếu chỉ dùng @Async không có database record, trạng thái task thường chỉ tồn tại qua future hoặc log. Với API cần hiển thị tiến trình cho người dùng, nên lưu notification status bền vững.

## 19. Kiểm thử tác vụ bất đồng bộ

Kiểm thử cần xác nhận method thực sự chạy qua executor, message được dựng đúng và lỗi được quan sát được.

### 19.1. Unit test phần tạo message

Tách logic render/build message khỏi logic gửi để kiểm tra:

- Subject đúng.
- Recipient đúng.
- Plain text và HTML có nội dung tương ứng.
- Charset phù hợp.
- CID/attachment đúng nếu có.
- Dữ liệu động được escape trong template.

### 19.2. Integration test với SMTP giả lập

Có thể dùng GreenMail, Mailpit hoặc MailHog để nhận email trong môi trường test. Kiểm tra message thực tế được gửi tới SMTP test server:

```java
@Test
void asyncMailIsSubmitted() throws Exception {
    // Arrange:
    // - Khởi động SMTP test server.
    // - Cấu hình JavaMailSender trỏ tới server đó.
    // - Gọi asyncMailService và giữ CompletableFuture.

    // Act:
    // - Chờ future hoàn tất với timeout hữu hạn.

    // Assert:
    // - SMTP test server nhận đúng một message.
    // - Recipient và subject đúng.
    // - Có text/plain và text/html.
}
```

Đây là khung test, cấu hình cụ thể phụ thuộc phiên bản GreenMail hoặc SMTP test server của dự án.

### 19.3. Kiểm tra tính bất đồng bộ

Có thể kiểm tra thread name hoặc dùng latch/future để xác nhận công việc chạy trên executor. Không nên dùng Thread.sleep(...) tùy tiện vì test dễ flaky và kéo dài.

Ví dụ ý tưởng:

```java
CompletableFuture<Void> future =
        asyncMailService.sendConfirmation(data);

assertThat(future).isNotNull();
future.get(5, TimeUnit.SECONDS);
```

Trong test thật, timeout cần phù hợp với môi trường và phải kiểm tra message ở SMTP test server. Chỉ kiểm tra future hoàn tất chưa đủ để chứng minh MIME message đúng.

### 19.4. Kiểm tra quá tải

Với executor có queue nhỏ, có thể kiểm tra:

- Task được nhận khi còn capacity.
- Task bị từ chối khi pool và queue đều đầy.
- Rejection được ghi log/đưa vào outbox hoặc trả lỗi phù hợp.
- Không có task bị discard âm thầm.

Không cần kiểm tra mọi cấu hình thread pool bằng test giả lập; hãy tập trung vào policy và hành vi khi hệ thống đạt giới hạn.

### 19.5. Kiểm tra shutdown và phục hồi

Nếu dùng outbox, hãy kiểm tra worker có thể tiếp tục notification còn PENDING sau khi ứng dụng restart. Với executor thuần trong memory, cần hiểu task chưa bắt đầu có thể mất khi process dừng; test không nên tuyên bố durability mà kiến trúc không cung cấp.

## 20. Những lỗi thường gặp khi dùng @Async

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Method vẫn chạy đồng bộ | Self-invocation hoặc chưa bật async | Gọi qua bean proxy và cấu hình @EnableAsync |
| Caller không bắt được exception | Method trả void và lỗi xảy ra trong worker | Dùng future hoặc AsyncUncaughtExceptionHandler |
| Email mất sau khi deploy | Task chỉ nằm trong executor memory | Dùng outbox/broker bền vững |
| Queue tăng liên tục | SMTP chậm hoặc executor quá nhỏ | Đo throughput, giới hạn tải và scale worker hợp lý |
| HTTP request vẫn chậm | Caller gọi get()/join() hoặc CallerRuns chạy task | Không chờ future nếu không cần; đánh giá rejection policy |
| LazyInitializationException | Truyền JPA entity sang thread nền | Truyền DTO hoặc ID và truy vấn trong transaction worker |
| Worker không thấy dữ liệu vừa lưu | Task chạy trước transaction commit | Dùng outbox hoặc xử lý sau commit có kiểm soát |
| Email gửi dù transaction rollback | Async bắt đầu trước commit | Ghi outbox trong cùng transaction |
| Log thiếu correlation ID | MDC không được propagate | Dùng TaskDecorator hoặc tracing integration |
| SecurityContext bị mất | Thread mới không có context caller | Truyền dữ liệu cần thiết hoặc dùng delegate executor phù hợp |
| SMTP bị throttling | Quá nhiều task gửi đồng thời | Giới hạn concurrency/rate theo provider |
| Task bị bỏ khi queue đầy | Rejection policy discard | Dùng rejection rõ ràng hoặc outbox |
| Shutdown mất task | Process dừng trước khi executor hoàn tất | Graceful shutdown và persistence cho task quan trọng |
| Retry gửi trùng | Timeout không rõ kết quả bị retry mù | State UNKNOWN, reconciliation và provider idempotency nếu có |
| Hai instance cùng chạy job | Scheduler chạy trên mọi instance | Dùng atomic claim/leader coordination/broker |

## 21. Khi nào chọn @Async, khi nào chọn message broker?

Không phải tác vụ nào cũng cần Kafka, RabbitMQ hoặc một hệ thống queue riêng. Hãy chọn theo yêu cầu.

| Tiêu chí | @Async + executor | Database outbox/worker | Message broker |
| --- | --- | --- | --- |
| Cách triển khai | Đơn giản, nằm trong ứng dụng | Cần bảng và worker | Cần broker và consumer |
| Task chờ trong memory | Có | Không, lưu database | Không, lưu broker |
| Khôi phục sau restart | Không bảo đảm cho task chưa hoàn tất | Có thể đọc lại từ database | Theo durability/config broker |
| Retry | Tự thiết kế | Lưu attempt và lịch retry | Broker/consumer policy kết hợp trạng thái |
| Scale worker độc lập | Hạn chế trong cùng ứng dụng | Có thể chạy worker riêng | Tốt, consumer scale độc lập |
| Backpressure | Thread pool/queue | Database backlog và claim | Broker lag/consumer concurrency |
| Theo dõi trạng thái nghiệp vụ | Cần tự lưu | Tự nhiên qua notification table | Cần kết hợp trạng thái nghiệp vụ |
| Phù hợp | Tác vụ nền nhẹ, có thể chấp nhận mất khi process dừng | Email giao dịch cần bền vững | Khối lượng lớn hoặc nhiều hệ thống cùng tiêu thụ |

### Chọn @Async khi

- Email không có yêu cầu durability cao.
- Ứng dụng nhỏ và chỉ cần giải phóng HTTP thread.
- Có thể chấp nhận task chưa hoàn tất bị mất khi process crash.
- Có cách quan sát lỗi và giới hạn executor.

### Chọn outbox khi

- Email gắn chặt với transaction nghiệp vụ.
- Không được mất yêu cầu gửi sau khi database commit.
- Cần retry, audit và trạng thái.
- Muốn tránh phụ thuộc vào một event chỉ tồn tại trong memory.

### Chọn broker khi

- Có lượng notification lớn hoặc nhiều consumer.
- Cần scale độc lập.
- Hệ thống đã có hạ tầng message broker.
- Cần routing, partitioning hoặc buffering giữa nhiều service.

Có thể kết hợp: transaction ghi outbox, publisher chuyển event sang broker, consumer gửi mail bằng JavaMailSender.

## 22. Ví dụ cấu trúc worker với outbox và executor

Một thiết kế có thể dùng scheduler để đọc batch từ outbox rồi dispatch từng notification vào mail executor:

```java
@Component
public class MailOutboxDispatcher {

    private final MailNotificationRepository repository;
    private final AsyncNotificationProcessor processor;

    public MailOutboxDispatcher(
            MailNotificationRepository repository,
            AsyncNotificationProcessor processor
    ) {
        this.repository = repository;
        this.processor = processor;
    }

    @Scheduled(fixedDelayString = "1000")
    public void dispatch() {
        List<ClaimedNotification> batch =
                repository.claimNextBatch(20);

        for (ClaimedNotification item : batch) {
            processor.process(item);
        }
    }
}
```

Processor:

```java
@Service
public class AsyncNotificationProcessor {

    private final MailNotificationRepository repository;
    private final JavaMailSender mailSender;

    public AsyncNotificationProcessor(
            MailNotificationRepository repository,
            JavaMailSender mailSender
    ) {
        this.repository = repository;
        this.mailSender = mailSender;
    }

    @Async("mailTaskExecutor")
    public CompletableFuture<Void> process(
            ClaimedNotification item
    ) {
        try {
            MimeMessage message = buildMessage(item);
            mailSender.send(message);
            repository.markSubmitted(
                    item.notificationId(),
                    item.claimToken()
            );
            return CompletableFuture.completedFuture(null);
        } catch (MailException ex) {
            repository.recordFailure(
                    item.notificationId(),
                    item.claimToken(),
                    classify(ex)
            );
            return CompletableFuture.failedFuture(ex);
        } catch (MessagingException ex) {
            repository.markFailed(
                    item.notificationId(),
                    item.claimToken(),
                    "MIME message construction failed"
            );
            return CompletableFuture.failedFuture(ex);
        }
    }
}
```

Đây là ví dụ kiến trúc, cần bổ sung transaction boundaries và claim implementation phù hợp. Không nên gọi repository.markSubmitted trong cùng transaction kéo dài với SMTP. Các method cập nhật trạng thái nên là transaction ngắn, có kiểm tra claim token để worker cũ không ghi đè kết quả của worker mới.

Ngoài ra, nếu dispatcher claim 20 row rồi executor chỉ nhận được 5 task do queue đầy, 15 row còn lại không được bỏ quên. Cần thiết kế claim/dispatch theo capacity hoặc có cơ chế release lease khi task chưa được nhận. Một lựa chọn là để worker trực tiếp lấy batch theo số slot sẵn có, thay vì claim nhiều hơn executor có thể xử lý.

## 23. Một số nguyên tắc thiết kế thực tế

1. **Dùng executor riêng cho mail.** Tránh để SMTP chậm làm nghẽn các tác vụ nền không liên quan.
2. **Giới hạn pool và queue.** Chọn giá trị theo throughput và quota provider.
3. **Không discard im lặng.** Khi quá tải, phải biết task đã bị từ chối và có cách phục hồi.
4. **Truyền DTO bất biến.** Không truyền request object, stream đã mở hoặc JPA entity cần lazy-load.
5. **Không giả định transaction được truyền sang worker.** Worker cần transaction riêng khi truy vấn/cập nhật database.
6. **Chỉ gửi sau khi nghiệp vụ commit.** Dùng outbox khi yêu cầu không mất notification.
7. **Xử lý exception ở worker.** Future/handler giúp quan sát lỗi; persistence giúp retry.
8. **Đặt timeout mạng.** Tránh task giữ thread vô hạn khi SMTP treo.
9. **Theo dõi queue và thời gian gửi.** Dùng metric, notification ID và correlation ID.
10. **Phân biệt accepted với delivered.** SMTP acceptance không chứng minh Inbox delivery.
11. **Thiết kế retry có trạng thái.** Kết quả timeout có thể là UNKNOWN; không retry mù.
12. **Giữ graceful shutdown.** Nhưng dùng outbox/broker cho durability qua crash.

## 24. Tình huống tự luyện

### Tình huống A: HTTP response vẫn chờ dù method có @Async

**Hướng xử lý:** kiểm tra caller có gọi future.get() hoặc join() không; kiểm tra method có bị self-invocation không; kiểm tra executor có dùng CallerRunsPolicy khi quá tải không. Xác nhận lời gọi đi qua Spring proxy.

### Tình huống B: đơn hàng rollback nhưng email xác nhận đã được gửi

**Hướng xử lý:** async worker đã bắt đầu trước khi transaction caller commit. Ghi notification/outbox trong cùng transaction và chỉ cho worker xử lý sau commit.

### Tình huống C: worker gặp LazyInitializationException

**Hướng xử lý:** không truyền entity để worker truy cập lazy relation. Tạo DTO trong transaction caller hoặc truyền ID rồi truy vấn bằng transaction riêng ở worker.

### Tình huống D: email bị mất sau khi deploy

**Hướng xử lý:** kiểm tra task chỉ nằm trong executor memory hay đã được lưu bền vững. Nếu task mất khi process dừng, chuyển sang outbox/broker và tạo cơ chế phục hồi.

### Tình huống E: queue tăng liên tục

**Hướng xử lý:** đo thời gian gửi và tỷ lệ task vào/ra; kiểm tra SMTP throttling; điều chỉnh concurrency/rate; giới hạn queue; xem xét scale worker hoặc provider capacity.

### Tình huống F: caller không nhận được exception SMTP

**Hướng xử lý:** nếu method trả void, cấu hình AsyncUncaughtExceptionHandler; nếu cần quan sát kết quả, dùng CompletableFuture. Với email nghiệp vụ, ghi lỗi vào notification state để có thể retry/reconcile.

### Tình huống G: SMTP timeout nhưng không biết email đã được nhận chưa

**Hướng xử lý:** đánh dấu UNKNOWN, tra provider event/message ID nếu có và áp dụng reconciliation. Không coi mọi timeout là chắc chắn chưa gửi.

### Tình huống H: ứng dụng có ba instance, mỗi instance pool tối đa 10 thread

**Hướng xử lý:** tổng concurrency có thể lên tới 30 task gửi đồng thời. Tính tổng trên toàn hệ thống và giới hạn theo quota SMTP, không chỉ nhìn pool của một instance.

## 25. Kết luận

Tách gửi mail sang tác vụ bất đồng bộ giúp luồng HTTP không phải chờ SMTP hoàn tất và cho phép ứng dụng kiểm soát số tác vụ gửi đồng thời. Trong Spring, @EnableAsync, @Async và TaskExecutor là những thành phần chính; CompletableFuture giúp caller quan sát kết quả và exception khi cần. Một executor riêng, queue có giới hạn, rejection policy rõ ràng và timeout mạng giúp tác vụ hoạt động có kiểm soát.

Với email gắn với nghiệp vụ, cần chú ý thời điểm transaction commit, dữ liệu truyền sang thread mới, exception, retry và shutdown. @Async chỉ chạy task trong tiến trình hiện tại; nó không tự bảo đảm task tồn tại qua crash. Transactional outbox hoặc broker phù hợp hơn khi yêu cầu gửi phải được lưu bền vững và phục hồi được. Hãy phân biệt yêu cầu đã được ghi nhận, SMTP đã chấp nhận và email đã được giao. Khi chọn đúng mô hình, ứng dụng vừa phản hồi tốt hơn vừa có cách theo dõi và xử lý lỗi gửi mail rõ ràng.

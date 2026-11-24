# Tùy biến RetryTemplate và gắn với binding cụ thể

Khi một consumer nhận thông điệp từ Kafka, RabbitMQ hoặc Pulsar, xử lý nghiệp vụ có thể thất bại vì dịch vụ bên ngoài tạm thời không sẵn sàng, cơ sở dữ liệu bị gián đoạn hoặc xảy ra lỗi tranh chấp tài nguyên. Spring Cloud Stream hỗ trợ retry ở phía consumer bằng Spring Retry. Với trường hợp thông thường, các thuộc tính như số lần thử, khoảng chờ và danh sách exception có thể đủ. Khi cần chính sách phức tạp hơn, ứng dụng có thể cung cấp một bean **RetryTemplate** tùy chỉnh.

Một ứng dụng có thể có nhiều input binding với yêu cầu retry khác nhau. Ví dụ, binding xử lý thanh toán cần thử lại lỗi mạng trong vài giây, còn binding cập nhật chỉ mục tìm kiếm có thể dùng số lần thử ít hơn và khoảng chờ dài hơn. Thuộc tính **retry-template-name** cho phép gắn một RetryTemplate được đặt tên vào đúng consumer binding.

## 1. RetryTemplate trong vòng đời xử lý thông điệp

RetryTemplate là thành phần của Spring Retry. Nó thực thi một thao tác, đánh giá lỗi theo retry policy, chờ theo backoff policy rồi thử lại nếu còn lượt.

Với một consumer binding theo mô hình imperative, luồng xử lý khái quát như sau:

~~~mermaid
flowchart TD
    A[Broker giao thông điệp] --> B[Consumer binding]
    B --> C[RetryTemplate gọi handler]
    C --> D{Xử lý thành công?}
    D -->|Có| E[Hoàn tất lần xử lý]
    D -->|Không| F{Còn lượt và lỗi được retry?}
    F -->|Có| G[Backoff]
    G --> C
    F -->|Không| H[Đưa lỗi ra error handling của binder]
    H --> I[DLQ, reject, requeue hoặc xử lý lỗi khác]
~~~

RetryTemplate quản lý các lần gọi lại handler trong cùng quá trình xử lý. Khi hết số lần thử, exception cuối cùng được chuyển tiếp tới cơ chế error handling của binding/binder. Binder có thể reject, requeue hoặc gửi thông điệp tới dead-letter destination tùy cấu hình và khả năng của broker.

Retry nội bộ và redelivery của broker là hai cơ chế khác nhau:

- **RetryTemplate:** gọi lại handler trong tiến trình consumer theo retry policy và backoff policy.
- **Broker redelivery:** broker giao lại thông điệp sau khi consumer reject, không ACK hoặc mất kết nối theo ngữ nghĩa của broker.
- **DLQ:** nơi giữ thông điệp không xử lý được để điều tra hoặc phát lại theo quy trình riêng.

Không cộng các cơ chế này một cách máy móc. Nếu bật retry nội bộ nhiều lần, requeue vô hạn và redelivery, một thông điệp có thể được xử lý lặp rất lâu. Hãy đặt giới hạn tổng thể và xác định nơi chịu trách nhiệm cho lần thử tiếp theo.

Các nội dung RetryTemplate trong bài này áp dụng cho message handler theo mô hình imperative, chẳng hạn Consumer<T> hoặc Function<T, R> xử lý từng thông điệp. Reactive function nhận Flux<T> không phải message handler xử lý từng message theo cơ chế này; với reactive flow, hãy dùng các toán tử Reactor như retryWhen và onErrorResume.

## 2. Khi nào dùng thuộc tính retry mặc định?

Spring Cloud Stream cung cấp các consumer properties để tùy chỉnh RetryTemplate do framework tạo:

| Thuộc tính | Ý nghĩa | Giá trị mặc định thường gặp |
|---|---|---|
| **max-attempts** | Tổng số lần gọi handler, bao gồm lần đầu. | 3 |
| **back-off-initial-interval** | Khoảng chờ trước lần thử lại đầu tiên, tính bằng mili giây. | 1000 |
| **back-off-max-interval** | Giới hạn trên của khoảng chờ. | 10000 |
| **back-off-multiplier** | Hệ số tăng khoảng chờ giữa các lần thử. | 2.0 |
| **default-retryable** | Có retry các exception không được liệt kê hay không. | true |
| **retryable-exceptions** | Bản đồ tên lớp exception và giá trị boolean cho phép/từ chối retry. | Rỗng |

Ví dụ một binding cần tối đa bốn lần thử, backoff tăng dần và chỉ retry lỗi tạm thời đã chọn:

~~~yaml
spring:
  cloud:
    function:
      definition: paymentConsumer
    stream:
      bindings:
        paymentConsumer-in-0:
          destination: payment-requests
          group: payment-service
          consumer:
            max-attempts: 4
            back-off-initial-interval: 500
            back-off-max-interval: 5000
            back-off-multiplier: 2.0
            default-retryable: false
            retryable-exceptions:
              java.net.SocketTimeoutException: true
              org.springframework.dao.TransientDataAccessException: true
              java.lang.IllegalArgumentException: false
~~~

Ở đây, lần đầu xử lý được tính là attempt 1. Nếu thất bại do SocketTimeoutException hoặc TransientDataAccessException, framework có thể thử lại. IllegalArgumentException được đánh dấu không retry. Với default-retryable bằng false, các exception không có trong bản đồ cũng không được retry.

Thuộc tính retryable-exceptions sử dụng tên lớp đầy đủ của exception làm khóa. Cần kiểm tra exception thực tế được ném ra sau khi framework unwrap các lớp bọc. Nếu exception nghiệp vụ được bọc trong MessagingException hoặc một exception chuyển đổi khác, hãy kiểm tra nguyên nhân gốc và hành vi phân loại của phiên bản đang dùng.

### Tính thời gian chờ

Với backoff tăng theo cấp số nhân, khoảng chờ lần lượt xấp xỉ:

~~~text
wait(n) = min(initialInterval * multiplier^(n - 1), maxInterval)
~~~

Ví dụ initial interval 500 ms, multiplier 2 và max interval 5000 ms:

| Lần thử lại | Khoảng chờ trước lần thử |
|---|---:|
| Lần thử 2 | 500 ms |
| Lần thử 3 | 1000 ms |
| Lần thử 4 | 2000 ms |

Với bốn attempts, có ba khoảng chờ, tổng thời gian backoff xấp xỉ 3500 ms, chưa tính thời gian xử lý của handler. Khoảng chờ không được áp dụng sau lần thử cuối cùng.

Nếu các thuộc tính mặc định đáp ứng yêu cầu, nên ưu tiên chúng vì dễ đọc và gắn trực tiếp với từng binding. Dùng RetryTemplate tùy chỉnh khi cần policy, backoff, listener hoặc hành vi phân loại phức tạp hơn.

## 3. Tạo RetryTemplate tùy chỉnh

Để cung cấp RetryTemplate cho binder, đánh dấu bean bằng annotation **@StreamRetryTemplate**:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.stream.annotation.StreamRetryTemplate;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class RetryConfiguration {

    @StreamRetryTemplate
    public RetryTemplate paymentRetryTemplate() {
        RetryTemplate template = new RetryTemplate();

        template.setRetryPolicy(new SimpleRetryPolicy(4));

        ExponentialBackOffPolicy backOff =
                new ExponentialBackOffPolicy();
        backOff.setInitialInterval(500L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(5000L);

        template.setBackOffPolicy(backOff);
        return template;
    }
}
~~~

**@StreamRetryTemplate** vừa là qualifier vừa có vai trò đăng ký bean, vì vậy không cần thêm **@Bean** lên cùng phương thức. Tên bean mặc định lấy từ tên phương thức, trong ví dụ là **paymentRetryTemplate**.

RetryTemplate gồm hai phần quan trọng:

- **RetryPolicy:** quyết định thao tác còn được thử lại hay không và giới hạn số lần thử.
- **BackOffPolicy:** quyết định khoảng chờ giữa các lần thử.

Ví dụ trên dùng SimpleRetryPolicy với bốn attempts và ExponentialBackOffPolicy. SimpleRetryPolicy cơ bản phù hợp minh họa giới hạn số lần thử; trong production cần cân nhắc phân loại exception để không retry lỗi dữ liệu hoặc lỗi nghiệp vụ vĩnh viễn.

Không thay đổi policy hoặc backoff của RetryTemplate sau khi bean đã được chia sẻ cho các binding. Hãy cấu hình hoàn chỉnh trước khi trả bean về Spring.

### Phân loại exception trong custom policy

Nếu cần chỉ retry một số lỗi, có thể cấu hình SimpleRetryPolicy bằng bản đồ exception:

~~~java
import java.net.SocketTimeoutException;
import java.util.HashMap;
import java.util.Map;

RetryTemplate template = new RetryTemplate();
Map<Class<? extends Throwable>, Boolean> retryable =
        new HashMap<>();
retryable.put(TransientDataAccessException.class, true);
retryable.put(SocketTimeoutException.class, true);
retryable.put(IllegalArgumentException.class, false);

SimpleRetryPolicy policy =
        new SimpleRetryPolicy(4, retryable, true, false);
template.setRetryPolicy(policy);
~~~

Trong ví dụ, tham số cuối đặt hành vi mặc định là không retry cho exception không được liệt kê; tham số trước cho phép xét nguyên nhân lồng bên trong. Hãy kiểm tra chữ ký constructor của phiên bản Spring Retry trong dự án khi sử dụng overload này.

Nếu muốn retry tất cả lỗi ngoại trừ một vài loại, cần chọn default policy và map tương ứng có chủ đích. Không giả định rằng một exception không được liệt kê luôn bị bỏ qua; hành vi mặc định phụ thuộc constructor và cấu hình retry policy.

## 4. Gắn RetryTemplate với một binding bằng retry-template-name

Khi ứng dụng chỉ có một RetryTemplate được đánh dấu **@StreamRetryTemplate**, binder có thể sử dụng bean đủ điều kiện đó theo cơ chế mặc định. Khi có nhiều RetryTemplate, hãy chọn bean cụ thể cho từng binding bằng thuộc tính:

~~~text
spring.cloud.stream.bindings.<binding-name>.consumer.retry-template-name
~~~

Trong YAML, thuộc tính được viết dưới consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: paymentConsumer;inventoryConsumer
    stream:
      bindings:
        paymentConsumer-in-0:
          destination: payment-requests
          group: payment-service
          consumer:
            retry-template-name: paymentRetryTemplate
        inventoryConsumer-in-0:
          destination: inventory-events
          group: inventory-service
          consumer:
            retry-template-name: inventoryRetryTemplate
~~~

Ứng dụng phải khai báo hai bean có tên khớp với giá trị cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.BackOffPolicy;

@Configuration
public class BindingRetryConfiguration {

    @StreamRetryTemplate
    public RetryTemplate paymentRetryTemplate() {
        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(new SimpleRetryPolicy(5));
        template.setBackOffPolicy(backOff(1000L, 2.0, 8000L));
        return template;
    }

    @StreamRetryTemplate
    public RetryTemplate inventoryRetryTemplate() {
        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(new SimpleRetryPolicy(2));
        template.setBackOffPolicy(backOff(3000L, 1.5, 10000L));
        return template;
    }

    private BackOffPolicy backOff(
            long initialInterval,
            double multiplier,
            long maxInterval) {
        ExponentialBackOffPolicy policy =
                new ExponentialBackOffPolicy();
        policy.setInitialInterval(initialInterval);
        policy.setMultiplier(multiplier);
        policy.setMaxInterval(maxInterval);
        return policy;
    }
}
~~~

Kết quả:

- **paymentConsumer-in-0** dùng **paymentRetryTemplate**.
- **inventoryConsumer-in-0** dùng **inventoryRetryTemplate**.
- Mỗi binding có số lần thử và backoff độc lập.

Tên trong **retry-template-name** là tên bean Spring, không phải tên function, tên destination hoặc tên class. Nếu bean được khai báo bằng phương thức **paymentRetryTemplate()**, tên mặc định của bean là **paymentRetryTemplate**. Nếu đặt tên bean tường minh, phải dùng chính xác tên đó trong cấu hình.

### Chọn đúng binding name

Thuộc tính retry-template-name nằm dưới ConsumerProperties của một input binding. Với function:

| Function | Input binding mặc định |
|---|---|
| **paymentConsumer** kiểu Consumer | **paymentConsumer-in-0** |
| **orderProcessor** kiểu Function | **orderProcessor-in-0** |
| Function có hai input | **combineOrders-in-0**, **combineOrders-in-1** |

Nếu đổi tên binding bằng **spring.cloud.stream.function.bindings**, hãy dùng tên binding alias thực tế trong cấu hình retry. Nếu binding được khai báo tường minh hoặc do một cơ chế khác tạo, hãy xác minh đúng tên binding đã đăng ký. Đừng đặt retry-template-name dưới output binding vì output binding không có consumer properties.

## 5. Cách kết hợp nhiều RetryTemplate

Một ứng dụng có thể khai báo nhiều template theo nhóm lỗi hoặc theo yêu cầu của hệ thống đích. Ví dụ:

| Binding | Hệ thống được gọi | Chính sách phù hợp |
|---|---|---|
| **paymentConsumer-in-0** | Dịch vụ thanh toán | Retry lỗi timeout hoặc lỗi 5xx có thể phục hồi; backoff tăng dần. |
| **inventoryConsumer-in-0** | Dịch vụ tồn kho | Ít lần thử hơn để tránh tạo tải khi hệ thống quá tải. |
| **auditConsumer-in-0** | Kho lưu audit | Retry ngắn nếu cần, sau đó chuyển lỗi sang quy trình lưu trữ/điều tra. |

Không nên tạo một template cho mỗi message hoặc mỗi khách hàng nếu số lượng binding không thực sự cần như vậy. RetryTemplate là cấu hình dùng chung ở cấp binding; tạo quá nhiều bean làm tăng độ phức tạp và khó quản lý.

Nếu hai binding có cùng policy, có thể cùng tham chiếu một bean RetryTemplate. Nếu chỉ khác số lần thử hoặc backoff đơn giản, cân nhắc dùng consumer properties thay vì tạo nhiều bean.

## 6. Phạm vi tác dụng và thứ tự ưu tiên cấu hình

RetryTemplate tùy chỉnh được chọn cho consumer binding cụ thể sẽ điều khiển retry policy và backoff của thao tác xử lý mà binding thực hiện. Không nhầm nó với:

- Retry khi tạo binding hoặc kết nối broker.
- Retry của producer khi gửi thông điệp.
- Retry trong HTTP client hoặc database client được gọi từ handler.
- Retry do broker redelivery sau khi message bị reject hoặc không được ACK.
- Retry operator của Reactor cho một luồng reactive.

Nếu ứng dụng có custom RetryTemplate được chọn qua **retry-template-name**, hãy cấu hình policy và backoff trực tiếp trong bean đó. Không giả định các thuộc tính **max-attempts**, **back-off-initial-interval** hoặc **retryable-exceptions** sẽ được trộn tự động vào template tùy chỉnh. Với các phiên bản cụ thể, hãy xác minh hành vi khi đồng thời khai báo cả custom template và consumer properties.

Nếu không chỉ định custom bean, Spring Cloud Stream tạo RetryTemplate từ các consumer properties. Đây thường là lựa chọn dễ vận hành nhất cho chính sách đơn giản.

### Ví dụ cấu hình mặc định và custom theo hai binding

~~~yaml
spring:
  cloud:
    function:
      definition: paymentConsumer;notificationConsumer
    stream:
      bindings:
        paymentConsumer-in-0:
          destination: payment-requests
          group: payment-service
          consumer:
            retry-template-name: paymentRetryTemplate
        notificationConsumer-in-0:
          destination: notification-events
          group: notification-service
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 5000
            back-off-multiplier: 2.0
~~~

Trong ví dụ, payment dùng template tùy chỉnh, còn notification dùng RetryTemplate do framework cấu hình từ consumer properties. Cách phân chia này cho phép áp dụng policy phức tạp ở nơi cần thiết và giữ cấu hình đơn giản ở nơi còn lại.

## 7. Thiết kế retry policy theo loại lỗi

Không phải lỗi nào cũng nên retry. Một retry policy tốt phân biệt ít nhất ba nhóm:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Timeout, mất kết nối ngắn hạn, deadlock có thể giải quyết. | Retry có giới hạn và backoff. |
| Lỗi dữ liệu/nghiệp vụ | Thiếu mã đơn hàng, trạng thái không hợp lệ, payload sai schema. | Không retry lặp lại; chuyển sang error handling hoặc DLQ. |
| Lỗi hệ thống kéo dài | Dịch vụ phụ thuộc ngừng hoạt động lâu, credential sai, cấu hình sai. | Dùng circuit breaker/giám sát và giới hạn retry; không tạo vòng lặp vô hạn. |

Retry quá nhiều có thể làm tăng tải lên một dịch vụ đang gặp sự cố. Nếu 1000 thông điệp đồng thời thử lại mỗi 100 ms, hệ thống đích có thể bị quá tải nặng hơn. Backoff và giới hạn concurrency giúp giảm áp lực.

Jitter có thể giúp tránh nhiều consumer retry đồng thời cùng một thời điểm. RetryTemplate có thể được mở rộng bằng BackOffPolicy phù hợp hoặc policy tùy chỉnh. Khi cần jitter, hãy kiểm tra API Spring Retry đang dùng và kiểm thử thời gian thực tế; không tự thêm ngẫu nhiên vào business logic mà không đo lường.

### Tránh retry lỗi không thể phục hồi

Ví dụ, lỗi dữ liệu thiếu customerId sẽ không tự hết sau một giây. Retry cùng payload không làm dữ liệu trở nên hợp lệ. Đánh dấu loại lỗi này không retry:

~~~java
Map<Class<? extends Throwable>, Boolean> retryable =
        new HashMap<>();
retryable.put(SocketTimeoutException.class, true);
retryable.put(TransientDataAccessException.class, true);
retryable.put(InvalidOrderException.class, false);
~~~

Đặt quy tắc này trong RetryPolicy tùy chỉnh hoặc dùng **retryable-exceptions** nếu consumer properties đã đáp ứng yêu cầu.

## 8. Retry, transaction và idempotency

Retry có thể gọi handler nhiều lần với cùng một thông điệp. Nếu handler thực hiện side effect, lần thử trước có thể đã hoàn thành một phần trước khi ném exception.

Ví dụ:

1. Consumer gọi dịch vụ thanh toán và giao dịch đã được chấp nhận.
2. Phản hồi bị timeout trước khi ứng dụng nhận được kết quả.
3. RetryTemplate gọi handler lần nữa.
4. Nếu producer thanh toán không hỗ trợ idempotency, hệ thống có thể tạo hai giao dịch.

Để tránh điều này, dùng khóa idempotency ổn định như eventId hoặc paymentRequestId. Gửi cùng khóa qua các lần thử và để hệ thống đích bảo đảm thao tác được áp dụng một lần.

Ví dụ:

~~~java
public void charge(PaymentRequested event) {
    paymentGateway.charge(
            event.paymentRequestId(),
            event.amount(),
            event.currency()
    );
}
~~~

Ở đây **paymentRequestId** phải được gateway sử dụng như idempotency key. Chỉ truyền một ID trong request không tự tạo ra tính idempotent nếu dịch vụ đích không thực thi quy tắc chống trùng.

Nếu consumer ghi cơ sở dữ liệu và cập nhật trạng thái xử lý, hãy bảo đảm các thao tác liên quan nằm trong transaction cục bộ phù hợp. Nếu một phần side effect nằm ngoài transaction, cần thiết kế bù trừ hoặc outbox. RetryTemplate không tạo transaction phân tán giữa database, broker và HTTP service.

## 9. Khi hết lượt thử: binder error handling và DLQ

Sau khi RetryTemplate hết số lần thử, lỗi được chuyển cho error handling của Spring Cloud Stream và binder. Cách xử lý tiếp theo tùy middleware:

- RabbitMQ có thể reject, requeue hoặc dùng dead-letter exchange/queue theo cấu hình Rabbit binder.
- Kafka binder có thể dùng dead-letter topic nếu cấu hình DLQ và điều kiện hỗ trợ phù hợp.
- Pulsar binder có retry/dead-letter hoặc cơ chế redelivery theo khả năng và phiên bản binder.

Không coi DLQ là một phần tự động của RetryTemplate. RetryTemplate quyết định việc thử lại tại consumer; binder và broker quyết định hành vi sau khi handler vẫn thất bại.

Một cấu hình consumer Kafka có thể bật DLQ theo thuộc tính binder, ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        paymentConsumer-in-0:
          destination: payment-requests
          group: payment-service
      kafka:
        bindings:
          paymentConsumer-in-0:
            consumer:
              enable-dlq: true
~~~

Tên thuộc tính mở rộng và điều kiện sử dụng DLQ phụ thuộc phiên bản Kafka binder, kiểu consumer và topology. Hãy xác minh cấu hình binder cụ thể trước khi triển khai. Ví dụ trên chỉ minh họa việc DLQ được cấu hình ở namespace Kafka binding, tách biệt với RetryTemplate.

Với RabbitMQ, nếu bật requeue rejected trong khi RetryTemplate cũng thử lại, thông điệp có thể quay lại vô hạn. Hãy xác định số lần retry nội bộ, số lần redelivery của broker, TTL và DLQ sao cho tổng vòng đời thông điệp có giới hạn.

## 10. Quan sát retry và chẩn đoán

Retry làm tăng thời gian xử lý và có thể che giấu lỗi nếu chỉ ghi log khi lần cuối thất bại. Nên quan sát:

- Số lần xử lý ban đầu và số lần retry.
- Loại exception gây retry.
- Tổng thời gian một thông điệp nằm trong retry.
- Số thông điệp cuối cùng chuyển sang DLQ.
- Tỷ lệ thành công sau retry so với thất bại cuối cùng.
- Backlog, consumer lag hoặc queue depth.
- Tỷ lệ retry theo từng binding.

Spring Retry hỗ trợ **RetryListener** để quan sát vòng đời retry. Listener có thể ghi nhận khi một lần thử thất bại, khi retry hoàn tất và khi chu kỳ retry kết thúc. Chữ ký callback thay đổi theo phiên bản Spring Retry; hãy triển khai theo API của dependency trong dự án. Khi thêm listener vào RetryTemplate, tránh ghi payload nhạy cảm hoặc thông tin xác thực vào log. Nên gắn binding name, event ID và correlation ID vào log để truy vết.

Nếu nhiều binding dùng các RetryTemplate khác nhau, metric cần gắn nhãn theo binding hoặc policy name. Điều đó giúp nhận ra một hệ thống phụ thuộc đang gây retry cao trong khi các binding còn lại hoạt động bình thường.

## 11. Kiểm thử RetryTemplate và liên kết binding

Kiểm thử cần chứng minh hai điều: RetryTemplate có policy đúng và binding thực sự sử dụng bean được chỉ định. Chỉ kiểm tra bean được tạo trong ApplicationContext chưa chứng minh binder đã chọn đúng template.

### Kiểm thử RetryTemplate độc lập

Có thể dùng AtomicInteger để mô phỏng một thao tác thất bại hai lần rồi thành công:

~~~java
AtomicInteger attempts = new AtomicInteger();

String result = paymentRetryTemplate.execute(context -> {
    int current = attempts.incrementAndGet();
    if (current < 3) {
        throw new IllegalStateException("Gateway timeout");
    }
    return "APPROVED";
});

assertThat(result).isEqualTo("APPROVED");
assertThat(attempts.get()).isEqualTo(3);
~~~

Test này xác nhận policy cho phép ba lần gọi trong tình huống mô phỏng. Nếu có backoff thực, có thể thay bằng policy test không chờ hoặc dùng thời gian nhỏ để tránh làm test chậm.

### Kiểm thử gắn template theo binding

Tạo hai binding với hai bean RetryTemplate khác nhau và kiểm tra:

1. Binding thanh toán tham chiếu bean **paymentRetryTemplate**.
2. Binding tồn kho tham chiếu bean **inventoryRetryTemplate**.
3. Mỗi bean có policy và backoff đã định nghĩa.
4. Một lỗi tại binding thanh toán không làm binding tồn kho dùng nhầm template.
5. Khi tên bean sai hoặc bean không tồn tại, ứng dụng phát hiện lỗi cấu hình khi khởi tạo binding hoặc lúc xử lý theo hành vi phiên bản.

### Ma trận kiểm thử đề xuất

| Tình huống | Thiết lập | Kết quả cần xác nhận |
|---|---|---|
| Không có custom bean | Chỉ đặt consumer retry properties. | Framework tạo policy theo max-attempts và backoff. |
| Một custom RetryTemplate | Khai báo bean có @StreamRetryTemplate. | Binder nhận bean đủ điều kiện theo cơ chế cấu hình. |
| Nhiều custom template | Khai báo nhiều bean có @StreamRetryTemplate. | Mỗi binding chọn bean theo retry-template-name. |
| Sai tên bean | Cấu hình tên không tồn tại. | Lỗi cấu hình được phát hiện; không âm thầm dùng nhầm template. |
| Exception retryable | Handler ném lỗi tạm thời rồi thành công. | Số lần gọi và backoff đúng policy. |
| Exception không retryable | Handler ném lỗi dữ liệu. | Handler không bị gọi lại theo policy. |
| Hết attempts | Handler luôn ném exception. | Lỗi được chuyển sang binder error handling. |
| Side effect lặp | Handler thực hiện thao tác có khóa idempotency. | Các lần retry không tạo tác động nghiệp vụ trùng. |
| Hai binding độc lập | Mỗi binding có một template. | Policy của binding này không ảnh hưởng binding kia. |

Với integration test, dùng test binder để kiểm tra luồng xử lý trong ứng dụng. Sau đó chạy test với Kafka, RabbitMQ hoặc Pulsar phù hợp để xác nhận hành vi reject, redelivery, DLQ và acknowledgement thực tế.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Binder không dùng RetryTemplate tùy chỉnh | Bean thiếu @StreamRetryTemplate hoặc không được Spring đăng ký. | Đánh dấu bean đúng annotation và kiểm tra ApplicationContext. |
| Binding dùng nhầm RetryTemplate | retry-template-name trỏ sai tên bean. | Đối chiếu tên bean với tên cấu hình, bao gồm chữ hoa/chữ thường. |
| Nhiều template gây xung đột | Có nhiều bean đủ điều kiện nhưng không chọn theo binding. | Gắn retry-template-name rõ ràng cho từng consumer binding. |
| Retry không chạy với exception mong muốn | RetryPolicy không phân loại exception hoặc exception bị bọc. | Kiểm tra exception thực tế và cause chain. |
| Lỗi dữ liệu bị retry liên tục | Default retryable quá rộng. | Đánh dấu lỗi nghiệp vụ là không retry hoặc đặt default-retryable=false. |
| Thời gian xử lý tăng đột biến | Backoff dài hoặc nhiều lần thử. | Tính tổng thời gian retry và đặt giới hạn phù hợp với SLA. |
| Thông điệp xuất hiện nhiều lần | Retry và broker redelivery cùng hoạt động hoặc side effect không idempotent. | Phân biệt hai tầng retry, giới hạn redelivery và dùng idempotency. |
| DLQ không nhận thông điệp | Chưa bật cấu hình DLQ hoặc binder không hỗ trợ cấu hình đó trong topology hiện tại. | Kiểm tra tài liệu binder và log error handling. |
| Consumer bị nghẽn | RetryTemplate chờ trên luồng xử lý đồng bộ quá lâu. | Giảm thời gian chờ, tăng khả năng chịu lỗi hoặc dùng retry ngoài tiến trình khi phù hợp. |

Khi điều tra, kiểm tra theo thứ tự: tên input binding, consumer properties, bean RetryTemplate, qualifier @StreamRetryTemplate, retry-template-name, exception thực tế, rồi mới đến binder error handling và DLQ. Cách này giúp phân biệt lỗi chọn bean với lỗi retry policy hoặc lỗi broker.

## 13. Quy trình lựa chọn và triển khai

1. Xác định lỗi nào có thể phục hồi và lỗi nào cần chuyển thẳng sang error handling.
2. Nếu policy đơn giản, cấu hình max-attempts, backoff và retryable-exceptions ở consumer binding.
3. Nếu policy phức tạp, tạo RetryTemplate tùy chỉnh với RetryPolicy và BackOffPolicy.
4. Đánh dấu bean bằng @StreamRetryTemplate để binder nhận diện.
5. Nếu có nhiều template, đặt tên bean ổn định và gắn từng template qua consumer.retry-template-name.
6. Kiểm thử số lần gọi, khoảng chờ, phân loại exception và trường hợp hết attempts.
7. Kiểm tra binder sẽ reject, requeue hoặc gửi DLQ ra sao sau khi retry nội bộ thất bại.
8. Bảo đảm side effect idempotent và theo dõi retry theo binding.

Checklist trước khi triển khai:

- [ ] Mỗi input binding có chính sách retry phù hợp với SLA.
- [ ] Đã xác định max attempts có tính cả lần xử lý đầu tiên.
- [ ] Backoff có giới hạn và không tạo tải lớn hơn lên dịch vụ đang lỗi.
- [ ] Exception nghiệp vụ không retry được đã được phân loại rõ.
- [ ] Custom RetryTemplate được đánh dấu @StreamRetryTemplate.
- [ ] Tên bean trong retry-template-name khớp chính xác với bean thực tế.
- [ ] Mỗi binding cần policy riêng đã chọn đúng template.
- [ ] Không giả định consumer properties tự động ghi đè policy trong custom template.
- [ ] Đã kiểm tra hành vi sau khi hết attempts với binder và DLQ.
- [ ] Side effect có idempotency hoặc cơ chế bù trừ phù hợp.
- [ ] Log/metric theo dõi retry, lỗi cuối cùng và backlog.

Tùy biến RetryTemplate cho phép kiểm soát số lần thử, cách phân loại exception và thời gian chờ của consumer. **@StreamRetryTemplate** đăng ký bean RetryTemplate để binder sử dụng; **retry-template-name** gắn một bean cụ thể với consumer binding. Khi phân biệt retry nội bộ với redelivery của broker, giới hạn tổng số lần thử và bảo vệ side effect bằng idempotency, ứng dụng Spring Cloud Stream có thể xử lý lỗi tạm thời mà vẫn giữ được hành vi vận hành có thể dự đoán.

## Tài liệu tham khảo

- [Spring Cloud Stream — Error Handling and Retry Template](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream Kafka Binder — Retry and DLQ](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring Retry — Reference Documentation](https://github.com/spring-projects/spring-retry)

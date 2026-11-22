# Giới hạn của event nội bộ so với message broker

Spring Framework Application Events là cơ chế phát thông báo bên trong một ứng dụng Spring. Một thành phần phát sự kiện qua `ApplicationEventPublisher`, còn các listener đã đăng ký trong ứng dụng nhận và xử lý sự kiện đó. Cơ chế này giúp các thành phần trong cùng ứng dụng giảm phụ thuộc trực tiếp vào nhau.

Tuy nhiên, **Application Event là thông báo nội bộ trong tiến trình ứng dụng**, không phải một hệ thống truyền thông điệp phân tán. Nó không tự cung cấp hàng đợi bền vững, xác nhận đã nhận, gửi lại, lưu lịch sử hay phân phối sự kiện sang một tiến trình khác. Message broker như RabbitMQ hoặc Apache Kafka được thiết kế để xử lý những ranh giới đó.

## 1. Event nội bộ hoạt động trong phạm vi nào?

Luồng cơ bản gồm ba bước:

1. Thành phần phát gọi `ApplicationEventPublisher.publishEvent(event)`.
2. Spring chuyển sự kiện đến `ApplicationEventMulticaster`.
3. Multicaster tìm các listener phù hợp kiểu sự kiện và gọi chúng.

Từ Spring Framework 4.2, sự kiện có thể là một object Java thông thường; không bắt buộc kế thừa `ApplicationEvent`. Listener có thể dùng `@EventListener` hoặc triển khai `ApplicationListener`.

Theo cấu hình mặc định, `SimpleApplicationEventMulticaster` gọi listener đồng bộ trên chính thread phát sự kiện nếu không được cấu hình một `TaskExecutor`. Vì vậy, khi gọi `publishEvent`, thành phần phát thường phải chờ các listener đồng bộ chạy xong mới đi tiếp.

Điều này hữu ích khi các thành phần nằm trong cùng một ứng dụng và cần thông báo nhanh, đơn giản. Ví dụ: sau khi tạo đơn hàng, module đơn hàng phát `OrderCreatedEvent`; module kiểm toán hoặc module thống kê trong cùng ứng dụng có thể lắng nghe mà không cần module đơn hàng gọi trực tiếp từng module đó.

Phạm vi này cũng là giới hạn quan trọng: listener phải tồn tại trong ApplicationContext đang xử lý sự kiện. Một instance Spring khác, một tiến trình khác hoặc một dịch vụ khác không tự nhận được event đó.

## 2. So sánh Application Event và message broker

| Khía cạnh | Spring Application Event | Message broker |
|---|---|---|
| Phạm vi | Trong ApplicationContext/tiến trình Spring đang phát | Có thể truyền giữa nhiều tiến trình, máy chủ và dịch vụ |
| Lưu trữ | Không có hàng đợi bền vững mặc định; event được truyền trong bộ nhớ | Có thể lưu message/topic/queue theo cấu hình broker |
| Xác nhận nhận | Không có giao thức acknowledgement giữa publisher và listener | Có cơ chế acknowledgement/offset tùy broker |
| Gửi lại khi lỗi | Không có retry và dead-letter queue tích hợp mặc định | Có thể cấu hình retry, redelivery và dead-letter |
| Phát lại lịch sử | Không có event log để đọc lại mặc định | Kafka có retention và offset để đọc lại; broker khác có cơ chế riêng |
| Nhiều instance | Event phát ở instance A không tự đến listener chỉ có ở instance B | Các consumer ở nhiều instance có thể cùng tham gia nhận message |
| Điều tiết tải | Listener đồng bộ có thể kéo dài request; executor có giới hạn riêng | Queue/topic có thể hấp thụ backlog và tách tốc độ producer/consumer |
| Vận hành | Ít thành phần hạ tầng, dễ theo dõi trong debugger/log ứng dụng | Cần vận hành broker, kết nối, quyền truy cập, giám sát và cấu hình |
| Hợp đồng dữ liệu | Thường chia sẻ class Java trong cùng codebase | Cần quản lý schema, phiên bản payload và tương thích giữa các dịch vụ |

Broker tạo ra khả năng lưu trữ và truyền thông điệp có kiểm soát, nhưng không tự động bảo đảm mọi hệ thống đều có exactly-once end-to-end. Độ bền, thứ tự, số lần giao, khả năng phát lại và xử lý trùng phụ thuộc vào loại broker, cấu hình producer/consumer, replication, acknowledgement, retention và cách ứng dụng xác nhận xử lý.

Ví dụ, Kafka lưu record trong topic theo thời gian retention và consumer đọc theo offset; thứ tự được bảo đảm trong phạm vi partition. RabbitMQ định tuyến message qua exchange đến queue; acknowledgement, durable queue, persistent message, requeue và dead-letter cần được cấu hình phù hợp. Không nên suy ra rằng chỉ cần cài broker là mọi message chắc chắn được xử lý đúng một lần.

## 3. Những giới hạn thực tế của event nội bộ

### 3.1. Không truyền giữa các instance

Giả sử ứng dụng được triển khai thành ba instance sau load balancer:

- Request tạo đơn hàng được xử lý tại instance A.
- Instance A phát `OrderCreatedEvent`.
- Listener nằm trong ApplicationContext của A có thể nhận event.
- Listener chỉ được đăng ký trong instance B hoặc C sẽ không nhận event từ A.

Mỗi instance có bộ nhớ và ApplicationContext riêng. Spring Application Event không phải cơ chế broadcast giữa các replica. Nếu cần nhiều dịch vụ hoặc nhiều instance độc lập nhận cùng một thông điệp, cần một kênh giao tiếp dùng chung, thường là message broker hoặc một cơ chế truyền tin phân tán tương đương.

### 3.2. Không có lưu trữ bền vững và phát lại

Event nội bộ không được ghi vào một queue hay log bền vững theo mặc định. Nếu tiến trình dừng đột ngột, event đang chờ trong bộ nhớ có thể mất. Sau khi khởi động lại, ứng dụng không có lịch sử mặc định để biết event nào chưa xử lý hoặc để phát lại event cũ.

Điều này khác với một broker được cấu hình lưu message. Broker có thể giữ message hoặc record trong thời gian xác định, cho phép consumer tiếp tục xử lý sau khi khởi động lại và hỗ trợ đọc lại theo chính sách của broker.

Vì vậy, không nên dùng Application Event làm nơi duy nhất giữ một công việc quan trọng cần được xử lý chắc chắn, chẳng hạn gửi hóa đơn, thanh toán, đồng bộ dữ liệu với hệ thống ngoài hoặc gửi thông báo bắt buộc.

### 3.3. Không có acknowledgement, retry và dead-letter mặc định

Khi listener đồng bộ được gọi, publisher không nhận một acknowledgement độc lập thể hiện rằng message đã được lưu và consumer đã xử lý bền vững. Việc gọi listener chỉ là lời gọi trong ứng dụng.

Nếu listener ném exception, với cấu hình multicaster mặc định không có ErrorHandler, exception có thể truyền ngược về nơi gọi `publishEvent`. Nếu listener chạy bất đồng bộ, lỗi xảy ra ở thread xử lý và không truyền ngược về publisher như lời gọi đồng bộ. Dù ở chế độ nào, Application Event cũng không tự tạo chính sách retry, số lần thử, khoảng chờ hay dead-letter queue.

Nếu nghiệp vụ cần retry, phải tự thiết kế cơ chế lưu trạng thái công việc, lịch thử lại, giới hạn số lần, xử lý lỗi cuối cùng và tính idempotent. Khi những yêu cầu này trở thành nhu cầu giao tiếp giữa dịch vụ, broker thường phù hợp hơn.

### 3.4. Listener đồng bộ có thể làm chậm luồng chính

Với cấu hình mặc định, listener chạy trong thread phát event. Nếu một listener gọi API bên ngoài, truy vấn chậm hoặc thực hiện tác vụ nặng, thời gian của thao tác phát event tăng theo.

Ví dụ, một request tạo đơn hàng phát event và listener gửi email trong cùng thread. Request chỉ hoàn tất sau khi thao tác gửi email kết thúc. Nếu dịch vụ email chậm hoặc timeout, trải nghiệm của request cũng bị ảnh hưởng.

Có thể dùng `@Async` hoặc cấu hình executor cho multicaster để chạy listener ở thread khác. Tuy nhiên, bất đồng bộ chỉ thay đổi cách thực thi; nó không biến event trong bộ nhớ thành message bền vững và không tự bổ sung retry, acknowledgement hay khả năng phát lại.

### 3.5. Không tự giải quyết ranh giới transaction

Một event được phát khi transaction cơ sở dữ liệu chưa commit có thể khiến listener chạy trước khi dữ liệu trở nên bền vững. Listener truy vấn dữ liệu có thể chưa thấy thay đổi vừa thực hiện, hoặc listener tạo tác động bên ngoài rồi transaction gốc lại rollback.

Ví dụ:

1. Service ghi đơn hàng trong transaction.
2. Service phát `OrderCreatedEvent`.
3. Listener gửi yêu cầu sang hệ thống vận chuyển.
4. Transaction lưu đơn hàng rollback.

Hệ thống vận chuyển đã nhận yêu cầu trong khi đơn hàng không được commit. Tác động bên ngoài không thể tự rollback cùng transaction cơ sở dữ liệu.

Spring cung cấp `@TransactionalEventListener` để gắn thời điểm gọi listener với transaction hiện tại. Phase mặc định là `AFTER_COMMIT`; các phase khác gồm `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Nếu không có transaction đang hoạt động, listener transactional mặc định không được gọi, trừ khi bật `fallbackExecution`.

Cơ chế này giúp chọn đúng thời điểm xử lý trong một ứng dụng Spring, nhưng **không tạo ra hàng đợi bền vững**. Nếu tiến trình dừng sau khi database commit nhưng trước khi listener hoàn tất, công việc vẫn có thể bị bỏ lỡ. Khi listener cần ghi dữ liệu mới sau commit, hãy cân nhắc transaction riêng phù hợp, ví dụ `REQUIRES_NEW`, thay vì giả định transaction cũ vẫn có thể commit thêm thay đổi.

## 4. Ví dụ: phát event trong cùng ứng dụng

Ví dụ sau dùng Java 17+ và Spring Boot. Các class được đặt chung trong một file để làm rõ luồng; trong dự án thực tế có thể tách mỗi class ra file riêng. Ứng dụng tạo một đơn hàng giả lập rồi phát event để listener in thông báo.

~~~java
package com.example.events;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService orderService) {
        return args -> orderService.create("order-1001");
    }
}

record OrderCreatedEvent(String orderId) {}

@Service
class OrderService {
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void create(String orderId) {
        // Giả lập thao tác tạo đơn hàng.
        publisher.publishEvent(new OrderCreatedEvent(orderId));
        System.out.println("Order service: " + orderId);
    }
}

@Component
class OrderNotificationListener {
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Notification listener: " + event.orderId());
    }
}
~~~

Khi chạy ứng dụng, hai dòng output do ví dụ tạo ra là:

~~~text
Notification listener: order-1001
Order service: order-1001
~~~

Listener chạy trước dòng in sau `publishEvent` vì event được dispatch đồng bộ. Log khởi động của Spring Boot không được liệt kê ở đây. Ví dụ chỉ minh họa việc truyền thông báo trong cùng ứng dụng; nó không có database, broker, retry hay lưu trữ message.

Lệnh chạy phụ thuộc cách tạo project Spring Boot. Với Gradle Wrapper của project, có thể chạy ứng dụng bằng:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

## 5. Gắn listener với thời điểm commit

Nếu event phản ánh một thay đổi dữ liệu, thường cần tránh xử lý trước khi transaction commit. Ví dụ listener sau chỉ chạy sau khi transaction thành công:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderAuditListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        System.out.println("Committed order: " + event.orderId());
    }
}
~~~

Service phát event trong một phương thức có transaction:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TransactionalOrderService {
    private final ApplicationEventPublisher publisher;

    TransactionalOrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Transactional
    public void create(String orderId) {
        // Lưu đơn hàng bằng repository tại đây.
        publisher.publishEvent(new OrderCreatedEvent(orderId));
    }
}
~~~

Khi transaction commit, listener ở phase `AFTER_COMMIT` mới được gọi. Nếu transaction rollback, listener này không chạy. Để ví dụ hoạt động trong ứng dụng thật, cần cấu hình transaction manager và sử dụng một phương thức transaction được gọi qua Spring proxy.

Cần phân biệt hai bảo đảm:

- `AFTER_COMMIT` bảo đảm listener chỉ được kích hoạt sau khi transaction commit thành công trong luồng xử lý bình thường.
- Nó không bảo đảm event đã được ghi vào một nơi bền vững hoặc sẽ được phát lại nếu tiến trình gặp sự cố đúng thời điểm.

Nếu mất một thông báo sau commit là không chấp nhận được, chỉ dùng `@TransactionalEventListener` là chưa đủ.

## 6. Bất đồng bộ không đồng nghĩa với message broker

Có thể chạy listener trên executor bằng `@Async`:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
class AsyncOrderListener {
    @Async
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        // Thực hiện tác vụ có thể mất thời gian.
        System.out.println("Async notification: " + event.orderId());
    }
}
~~~

Bật xử lý async trong cấu hình Spring:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
class AsyncConfiguration {}
~~~

Khi dùng cách này, cần lưu ý:

- Phải cấu hình executor phù hợp với tải, số thread, dung lượng hàng đợi và chính sách từ chối tác vụ.
- Exception của listener bất đồng bộ không được trả về cho thread đã gọi `publishEvent`; cần cấu hình logging và xử lý lỗi riêng, chẳng hạn `AsyncUncaughtExceptionHandler` cho phương thức trả về `void`.
- Nếu tiến trình dừng khi tác vụ còn nằm trong hàng đợi của executor, tác vụ có thể mất.
- Không nên giả định ThreadLocal, security context hoặc transaction context của thread phát tự động có mặt trong thread xử lý; cần cơ chế truyền context rõ ràng khi nghiệp vụ yêu cầu.
- `@Async` phụ thuộc cơ chế proxy của Spring; lời gọi nội bộ giữa các method trong cùng object có thể không đi qua proxy như mong đợi.

Executor giúp tách thời gian xử lý khỏi thread phát event, nhưng queue của executor vẫn thuộc tiến trình. Nó không có đặc tính lưu trữ và phục hồi của một broker được cấu hình bền vững.

## 7. Khi nào nên dùng message broker?

Message broker phù hợp khi hệ thống cần một hoặc nhiều đặc tính sau:

- Producer và consumer chạy ở các tiến trình, dịch vụ hoặc nhóm triển khai độc lập.
- Consumer có thể tạm dừng hoặc mất kết nối mà message vẫn cần được giữ lại để xử lý sau.
- Cần retry, acknowledgement, dead-letter, theo dõi backlog hoặc điều tiết tốc độ tiêu thụ.
- Nhiều consumer độc lập cần nhận cùng loại sự kiện.
- Cần lưu lịch sử trong một khoảng thời gian hoặc phát lại dữ liệu để dựng lại trạng thái.
- Cần mở rộng số consumer mà không buộc producer biết topology của các dịch vụ nhận.

Hai lựa chọn thường gặp:

**RabbitMQ** phù hợp với mô hình định tuyến message qua exchange đến queue. Có thể dùng acknowledgement để xác nhận xử lý, cấu hình durable queue và persistent message, retry/requeue hoặc dead-letter exchange. Cần thiết kế routing key, loại exchange, giới hạn queue và chính sách redelivery.

**Apache Kafka** phù hợp với luồng sự kiện được lưu trong topic theo retention. Consumer đọc record theo offset; consumer group chia tải giữa các consumer và có thể đọc lại từ offset cũ khi dữ liệu còn trong retention. Thứ tự được bảo đảm trong từng partition, không phải một thứ tự toàn cục cho mọi partition.

Broker làm tăng chi phí vận hành: triển khai và giám sát hạ tầng, cấu hình bảo mật, xử lý lỗi mạng, quản lý schema, theo dõi lag/backlog và thiết kế consumer idempotent. Không nên thêm broker chỉ để thay một lời gọi giữa hai class trong cùng một ứng dụng.

## 8. Vấn đề dual-write và Transactional Outbox

Một lỗi phổ biến khi chuyển sang broker là ghi database và publish message như hai thao tác độc lập:

1. Ghi đơn hàng vào database.
2. Publish `OrderCreated` lên broker.

Nếu database commit thành công nhưng publish thất bại, dữ liệu đã có nhưng consumer không nhận được event. Nếu publish thành công nhưng database rollback, consumer nhận một event mô tả dữ liệu không tồn tại. Đây là vấn đề dual-write.

Transactional Outbox giải quyết bằng cách ghi dữ liệu nghiệp vụ và một bản ghi outbox trong cùng transaction database:

1. Service ghi đơn hàng.
2. Service ghi event cần phát vào bảng outbox.
3. Cả hai thay đổi commit hoặc rollback cùng nhau.
4. Một relay đọc outbox và publish message lên broker.
5. Sau khi publish được xác nhận theo chính sách đã chọn, relay đánh dấu bản ghi đã gửi hoặc lưu trạng thái tương ứng.

Outbox giúp không mất mối liên hệ giữa commit nghiệp vụ và ý định phát event. Tuy nhiên, relay có thể publish lặp nếu broker đã nhận message nhưng relay chưa kịp ghi nhận trạng thái gửi. Vì vậy consumer vẫn nên idempotent, dùng event ID hoặc khóa nghiệp vụ để nhận diện và bỏ qua xử lý trùng.

Outbox là một mẫu kiến trúc bổ sung cho broker; nó không phải tính năng tự động của Spring Application Events. Có thể dùng Application Event để đánh thức relay trong cùng tiến trình, nhưng bản ghi outbox mới là nguồn dữ liệu bền vững cần được quét/khôi phục.

## 9. Tiêu chí lựa chọn

| Tình huống | Hướng phù hợp |
|---|---|
| Các module trong một modular monolith cần thông báo cho nhau | Spring Application Event |
| Listener chỉ cập nhật cache hoặc thực hiện tác vụ phụ có thể chấp nhận mất | Application Event, có thể kết hợp async |
| Cần listener chạy sau khi transaction commit nhưng vẫn trong cùng ứng dụng | `@TransactionalEventListener` |
| Cần giao tiếp giữa nhiều microservice | Message broker hoặc giao thức liên dịch vụ phù hợp |
| Cần giữ công việc khi consumer tạm dừng hoặc tiến trình khởi động lại | Broker có cấu hình lưu trữ/acknowledgement phù hợp |
| Cần retry, dead-letter, backlog và nhiều consumer độc lập | Message broker |
| Cần bảo đảm ý định phát event đi cùng transaction nghiệp vụ | Transactional Outbox kết hợp broker |
| Chỉ muốn giảm phụ thuộc giữa hai class trong cùng ứng dụng | Application Event thường đã đủ |

Một cách ra quyết định thực tế:

1. Xác định event có cần vượt qua ranh giới process/service hay không.
2. Xác định có chấp nhận mất event khi ứng dụng dừng đột ngột hay không.
3. Xác định có cần retry, replay, acknowledgement hoặc dead-letter không.
4. Xác định tải có cần được hấp thụ bằng backlog và consumer mở rộng độc lập không.
5. Nếu các yêu cầu trên chưa xuất hiện và event chỉ phục vụ module nội bộ, bắt đầu bằng Spring Application Event thường đơn giản hơn.
6. Khi yêu cầu độ tin cậy hoặc phân tán tăng lên, thiết kế broker và outbox dựa trên yêu cầu giao nhận cụ thể.

## 10. Những hiểu nhầm thường gặp

- **“Có `@Async` nghĩa là event đã được queue bền vững.”** Sai. Executor thường giữ tác vụ trong bộ nhớ của tiến trình.
- **“Dùng `@TransactionalEventListener(AFTER_COMMIT)` thì không thể mất event.”** Sai. Nó điều khiển thời điểm gọi listener, không lưu event để phục hồi sau crash.
- **“Publisher gọi `publishEvent` thành công nghĩa là nghiệp vụ của mọi listener đã hoàn tất.”** Chỉ có thể hiểu là lời gọi dispatch đã diễn ra theo chế độ thực thi hiện tại; không có acknowledgement bền vững cho mọi listener.
- **“Application Event tự broadcast đến mọi replica.”** Sai. Mỗi ApplicationContext là một phạm vi riêng.
- **“Broker luôn giao đúng một lần.”** Sai. Cần hiểu delivery semantics, cấu hình và khả năng xử lý trùng của từng hệ thống.
- **“Cứ dùng broker là không cần idempotency.”** Sai. Retry và redelivery có thể khiến consumer nhận cùng một message nhiều lần.

## 11. Checklist trước khi chọn

- [ ] Event chỉ phục vụ các module trong cùng ApplicationContext?
- [ ] Có chấp nhận listener chạy trong thread phát event hoặc executor của ứng dụng?
- [ ] Có chấp nhận không có lưu trữ và replay mặc định?
- [ ] Nếu listener lỗi, ứng dụng có cách ghi nhận và xử lý phù hợp?
- [ ] Nếu event gắn với transaction, thời điểm listener chạy đã được xác định?
- [ ] Nếu cần giao nhận bền vững, broker và cấu hình acknowledgement/retention đã đáp ứng yêu cầu?
- [ ] Consumer đã xử lý an toàn khi nhận message trùng?
- [ ] Nếu ghi database và publish broker, đã xem xét Transactional Outbox?

Spring Application Events phù hợp để kết nối lỏng các thành phần **bên trong một ứng dụng Spring**. Message broker phù hợp khi thông điệp cần đi qua ranh giới tiến trình, tồn tại độc lập với vòng đời của producer hoặc cần các khả năng giao nhận và phục hồi rõ ràng. Chọn cơ chế theo phạm vi và mức bảo đảm mà nghiệp vụ cần sẽ giúp hệ thống giữ được sự đơn giản mà vẫn đáp ứng độ tin cậy cần thiết.

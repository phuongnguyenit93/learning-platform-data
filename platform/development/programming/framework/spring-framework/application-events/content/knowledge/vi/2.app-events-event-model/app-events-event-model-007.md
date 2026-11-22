# Ranh giới giữa event nội bộ và tích hợp bên ngoài trong Spring Framework

## Mục tiêu

Trong một ứng dụng Spring, event giúp một thành phần thông báo rằng một sự việc nghiệp vụ đã xảy ra để thành phần khác phản ứng mà không cần gọi trực tiếp từng thành phần. Tuy nhiên, **Spring Application Event là cơ chế giao tiếp trong một tiến trình**. Nó không tự trở thành thông điệp có thể gửi sang service khác, lưu bền vững, phát lại hoặc bảo đảm giao nhận.

Bài học này giúp bạn quyết định phần nào nên dùng event nội bộ của Spring, phần nào cần một hợp đồng tích hợp bên ngoài, và cách nối hai ranh giới đó mà không làm domain phụ thuộc vào Kafka, RabbitMQ hay HTTP.

Sau bài học, bạn có thể:

- Phân biệt domain event, application event nội bộ và integration event.
- Giải thích vòng đời và giới hạn giao nhận của `ApplicationEventPublisher` và `@EventListener`.
- Chọn đúng thời điểm xử lý event khi có transaction.
- Thiết kế adapter và transactional outbox cho tích hợp cần độ tin cậy.
- Tránh đưa entity, kiểu dữ liệu nội bộ hoặc chi tiết hạ tầng vào hợp đồng bên ngoài.

## 1. Ba khái niệm cần tách biệt

### Domain event

Domain event diễn tả một sự kiện có ý nghĩa trong mô hình nghiệp vụ: `OrderApproved`, `PaymentCaptured`, `CustomerAddressChanged`. Nó trả lời câu hỏi “điều gì đã xảy ra?” và thường được phát sinh khi một aggregate hoặc domain service hoàn thành một chuyển đổi hợp lệ.

Domain event thuộc ngôn ngữ của domain. Nó có thể chỉ được dùng bên trong một module, hoặc được một application service chuyển thành thông điệp tích hợp. Không phải domain event nào cũng cần gửi ra ngoài.

### Application event nội bộ của Spring

Application event là cách một thành phần trong cùng Spring ApplicationContext thông báo cho các listener khác. Publisher gọi `ApplicationEventPublisher.publishEvent(...)`; Spring tìm các listener phù hợp và dispatch event.

Từ Spring Framework 4.2, event có thể là một object Java thông thường; không bắt buộc kế thừa `ApplicationEvent`. Vì vậy một record như `OrderApproved` có thể được publish trực tiếp.

Application event thường dùng để tách các phản ứng nội bộ: cập nhật projection trong cùng ứng dụng, ghi audit nội bộ, làm mới cache hoặc kích hoạt một bước xử lý phụ. Nó không phải message broker và không phải API contract giữa các service.

### Integration event

Integration event là thông điệp được công bố qua một ranh giới tiến trình hoặc hệ thống, ví dụ qua Kafka, RabbitMQ, một nền tảng messaging, webhook hoặc HTTP API. Nó là hợp đồng mà một hệ thống khác có thể nhận và diễn giải.

Integration event cần được thiết kế như dữ liệu trao đổi: tên và ý nghĩa ổn định, schema có phiên bản, định danh event, thời điểm xảy ra và các trường tối thiểu mà consumer cần. Nó không nên phụ thuộc vào class nội bộ, entity ORM hoặc cấu trúc package của service phát.

| Tiêu chí | Application event nội bộ | Integration event |
|---|---|---|
| Phạm vi | Một tiến trình / Spring ApplicationContext | Giữa các tiến trình hoặc hệ thống |
| Cơ chế | `ApplicationEventPublisher`, `@EventListener` | Broker, HTTP, webhook hoặc giao thức tích hợp |
| Hợp đồng | Có thể là kiểu Java nội bộ, thay đổi cùng ứng dụng | Schema cần ổn định và có chiến lược tương thích |
| Lưu bền vững | Không tự lưu | Tùy hạ tầng; broker/outbox có thể lưu và phát lại |
| Giao nhận | Không có bảo đảm durable/retry mặc định | Phụ thuộc broker và thiết kế retry/ack |
| Lỗi listener | Listener đồng bộ có thể làm lỗi luồng publish | Được xử lý theo chính sách retry, ack, DLQ của adapter/broker |
| Consumer | Bean trong cùng ứng dụng | Consumer có thể thuộc service hoặc tổ chức khác |

**Quy tắc quyết định:** nếu bên nhận là một bean trong cùng ứng dụng và không cần giao nhận bền vững, application event có thể phù hợp. Nếu bên nhận ở tiến trình khác, cần lưu thông điệp, retry sau khi ứng dụng khởi động lại, phát lại hoặc duy trì hợp đồng độc lập, hãy dùng cơ chế tích hợp bên ngoài.

## 2. Spring Application Event hoạt động như thế nào?

Luồng cơ bản:

1. Một service thực hiện hành động nghiệp vụ.
2. Service publish một object event qua `ApplicationEventPublisher`.
3. Spring ApplicationEventMulticaster dispatch event tới các listener có kiểu phù hợp.
4. Các method được đánh dấu `@EventListener` xử lý event.

Mặc định, `SimpleApplicationEventMulticaster` gọi listener trong cùng thread đang publish event. Vì vậy listener đồng bộ chạy ngay trong luồng gọi `publishEvent`. Nếu listener ném exception và exception thoát ra ngoài, lời gọi publish có thể thất bại và exception truyền ngược về publisher.

Có thể cấu hình executor cho multicaster hoặc dùng `@Async` cùng `@EnableAsync` để xử lý bất đồng bộ. Khi đó publisher không chờ listener hoàn tất; exception từ listener bất đồng bộ không truyền ngược về publisher như trường hợp đồng bộ. Cần cấu hình logging, xử lý lỗi và executor phù hợp. **Bất đồng bộ không đồng nghĩa với lưu bền vững:** process dừng đột ngột vẫn có thể làm mất công việc đang chờ trong bộ nhớ.

### Ví dụ chạy được với Java 17+

Ví dụ dùng Spring Framework trực tiếp, không cần Spring Boot. Cấu trúc thư mục:

```text
spring-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventsDemo.java
```

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-events-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ApplicationEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/demo/ApplicationEventsDemo.java**

```java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ApplicationEventsDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(OrderService.class).approve(42L);
        }
    }

    @Configuration
    static class AppConfig {

        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        AuditListener auditListener() {
            return new AuditListener();
        }
    }

    record OrderApproved(long orderId) {
    }

    static class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void approve(long orderId) {
            System.out.println("Order " + orderId + " approved");
            publisher.publishEvent(new OrderApproved(orderId));
        }
    }

    static class AuditListener {

        @EventListener
        void onOrderApproved(OrderApproved event) {
            System.out.println(
                    "Internal listener received OrderApproved: "
                            + event.orderId());
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Stdout:

```text
Order 42 approved
Internal listener received OrderApproved: 42
```

Trong ví dụ, `OrderService` chỉ biết `ApplicationEventPublisher`, không biết listener cụ thể. `AuditListener` nhận event bằng `@EventListener`. Event là record Java bình thường và được dispatch đồng bộ theo cấu hình mặc định.

Ví dụ minh họa cơ chế dispatch trong một process; nó không tạo message trên broker và không chứng minh khả năng giao nhận bền vững.

## 3. Đặt ranh giới transaction đúng chỗ

Khi publisher chạy bên trong một transaction, cần xác định listener phải phản ứng trước hay sau khi transaction kết thúc.

`@EventListener` thông thường được gọi ngay khi event được dispatch. Nếu publish trong một method `@Transactional`, listener đồng bộ có thể chạy trước thời điểm commit. Nếu transaction sau đó rollback, side effect mà listener đã thực hiện ở hệ thống khác không tự rollback theo database transaction.

Với listener phụ thuộc kết quả commit, dùng `@TransactionalEventListener`:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class LocalProjectionListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void onOrderApproved(OrderApproved event) {
        // Chỉ chạy sau khi transaction chứa event commit thành công.
    }
}
```

Đoạn minh họa này cần dependency `spring-tx` và một transaction manager được cấu hình trong ứng dụng thực tế.

Các phase thường dùng:

- `BEFORE_COMMIT`: chạy trước khi transaction commit.
- `AFTER_COMMIT`: chạy sau khi commit thành công; đây là phase mặc định.
- `AFTER_ROLLBACK`: chạy sau khi rollback.
- `AFTER_COMPLETION`: chạy sau khi transaction hoàn tất, dù commit hay rollback.

Mặc định, transactional listener cần có transaction đang hoạt động tại thời điểm publish. Nếu không có transaction, listener sẽ không được gọi. Chỉ bật `fallbackExecution = true` khi nghiệp vụ thực sự chấp nhận xử lý cả trường hợp không có transaction.

`AFTER_COMMIT` giúp tránh phản ứng như thể dữ liệu đã được commit khi transaction còn có thể rollback. Tuy nhiên, nó **không tạo bảo đảm giao nhận bền vững**: process vẫn có thể dừng sau commit và trước khi side effect hoàn tất. Exception sau commit cũng không thể hoàn tác transaction đã commit. Nếu listener cần ghi thêm dữ liệu qua transaction khác, hãy xác định rõ transaction mới, chẳng hạn dùng propagation `REQUIRES_NEW` khi phù hợp.

## 4. Chuyển từ event nội bộ sang integration event

Không nên để domain model hoặc service nghiệp vụ phụ thuộc trực tiếp vào Kafka producer, RabbitMQ template hay HTTP client. Hãy đặt phần chuyển đổi ở application/infrastructure adapter:

```text
Domain / Application service
        |
        | phát sinh OrderApproved (ý nghĩa nghiệp vụ)
        v
Application event nội bộ
        |
        | adapter ánh xạ dữ liệu
        v
Integration event OrderApprovedV1
        |
        v
Outbox / Broker / HTTP adapter
        |
        v
Hệ thống bên ngoài
```

Adapter chịu trách nhiệm:

- Chọn dữ liệu được phép công bố và chuyển sang schema tích hợp.
- Gán event ID, event type, version và thời điểm xảy ra.
- Thêm correlation ID hoặc causation ID khi luồng nghiệp vụ cần truy vết.
- Chuyển đổi lỗi hạ tầng thành retry, ghi nhận thất bại hoặc dead-letter theo chính sách.
- Không làm lộ entity ORM, lazy proxy, thông tin nội bộ hoặc cấu trúc package của domain.

Ví dụ hợp đồng tích hợp có thể là:

```java
public record OrderApprovedV1(
        String eventId,
        long orderId,
        String occurredAt,
        String correlationId
) {
}
```

Đây là ví dụ về schema trao đổi. Khi serialize, cần chọn định dạng và quy tắc thời gian thống nhất, ví dụ ISO-8601 UTC cho `occurredAt`. Consumer bên ngoài chỉ nên phụ thuộc vào trường được công bố trong hợp đồng, không phụ thuộc vào class Java gốc.

Không nhất thiết phải phát mọi domain event ra ngoài. Chỉ công bố những sự kiện có ý nghĩa với consumer bên ngoài và có chủ sở hữu hợp đồng rõ ràng. Một domain event có thể chỉ phục vụ xử lý nội bộ; một integration event cũng có thể được tổng hợp từ nhiều thay đổi nội bộ.

## 5. Khi nào cần transactional outbox?

Giả sử service vừa cập nhật đơn hàng trong database vừa gửi message tới broker. Có hai thao tác ở hai hệ thống khác nhau:

1. Commit dữ liệu đơn hàng.
2. Publish message lên broker.

Nếu database commit thành công nhưng broker lỗi, dữ liệu đã đổi mà consumer không nhận được thông điệp. Nếu publish trước rồi database rollback, consumer có thể nhận một sự kiện cho thay đổi chưa từng được commit. Đây là bài toán dual-write.

Transactional outbox giải quyết bằng cách ghi thay đổi nghiệp vụ và một bản ghi outbox trong **cùng database transaction**:

```java
@Transactional
public void approveOrder(long orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();
    order.approve();

    outboxRepository.save(
            OutboxMessage.pending(
                    "OrderApproved",
                    "v1",
                    serialize(new OrderApprovedV1(
                            newEventId(),
                            order.getId(),
                            Instant.now().toString(),
                            currentCorrelationId()
                    ))
            )
    );
}
```

Đoạn trên là phác thảo kiến trúc; các repository, serializer và hàm tạo ID cần được triển khai trong ứng dụng thực tế. Điểm quan trọng là thao tác ghi outbox và cập nhật order dùng cùng transaction manager/database transaction.

Một relay riêng đọc các bản ghi outbox chưa gửi, publish lên broker, rồi đánh dấu đã gửi sau khi nhận xác nhận phù hợp. Nếu relay gặp lỗi, nó có thể thử lại theo chính sách. Cần thiết kế thêm:

- **Idempotency:** relay hoặc broker có thể giao cùng event nhiều lần; consumer dùng event ID để phát hiện và xử lý trùng an toàn.
- **Retry có giới hạn và backoff:** tránh lặp liên tục khi broker đang lỗi.
- **Dead-letter hoặc trạng thái cần can thiệp:** giữ lại thông điệp không thể xử lý sau số lần thử phù hợp.
- **Quan sát vận hành:** theo dõi tuổi bản ghi pending, số lần retry, độ trễ publish và lỗi serialization.
- **Dọn dẹp:** chỉ xóa/archiving bản ghi theo chính sách lưu trữ sau khi đã xác nhận hoàn tất.

Outbox thường cung cấp mô hình giao nhận ít nhất một lần (at-least-once), không tự bảo đảm exactly-once end-to-end. Consumer vẫn cần idempotency. Nếu dùng CDC để đọc outbox, connector CDC đảm nhiệm phần chuyển tiếp nhưng schema, duplicate handling và quan sát vận hành vẫn cần được thiết kế.

Có thể dùng `@TransactionalEventListener(AFTER_COMMIT)` để kích hoạt một xử lý phụ sau commit, nhưng nếu chỉ publish trực tiếp tới broker từ listener này thì vẫn tồn tại khoảng trống: database đã commit nhưng process dừng trước khi gửi. Vì vậy, với thông điệp tích hợp quan trọng cần không mất dữ liệu, outbox là lựa chọn phù hợp hơn.

## 6. Những lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Cách xử lý |
|---|---|---|
| Dùng `ApplicationEventPublisher` để gửi sang service khác | Event chỉ được dispatch trong process hiện tại | Dùng broker, HTTP hoặc webhook adapter |
| Nghĩ `@Async` đồng nghĩa với durable | Công việc đang nằm trong bộ nhớ có thể mất khi process dừng | Dùng outbox hoặc hạ tầng hàng đợi có lưu bền vững |
| Gửi JPA entity làm payload tích hợp | Lộ cấu trúc persistence, lazy loading, dữ liệu thừa và coupling | Ánh xạ sang DTO/schema tích hợp riêng |
| Gọi API bên ngoài ngay trong transaction database | Giữ transaction lâu; lỗi mạng làm tăng thời gian khóa và tạo trạng thái khó phục hồi | Ghi outbox trong transaction rồi relay sau |
| Dùng listener AFTER_COMMIT như cơ chế retry | Commit đã hoàn tất; exception không rollback dữ liệu và không tự tạo lần gửi lại | Lưu trạng thái gửi và retry qua outbox/broker |
| Cho consumer giả định event chỉ đến một lần | Redelivery có thể tạo side effect trùng | Dùng event ID và xử lý idempotent |
| Chia sẻ cùng một class Java nội bộ giữa nhiều service | Thay đổi implementation có thể phá consumer | Quản lý schema tích hợp có version và quy tắc tương thích |

Một số lưu ý bổ sung:

- `@Order` có thể sắp xếp thứ tự gọi các listener đồng bộ. Khi xử lý bất đồng bộ, không nên dựa vào thứ tự hoàn tất để bảo đảm nghiệp vụ.
- Listener nên làm một việc rõ ràng, có thể quan sát và kiểm thử độc lập. Tránh tạo chuỗi listener dài mà không thể theo dõi luồng xử lý.
- Không phát event trước khi trạng thái nghiệp vụ hợp lệ được xác lập. Tên event nên mô tả sự việc đã xảy ra (`OrderApproved`), không phải yêu cầu mơ hồ (`ApproveOrder`).
- Không đưa mật khẩu, token, dữ liệu cá nhân không cần thiết hoặc thông tin nội bộ vào integration event.
- Nếu event có thể được phát lại, payload cần đủ thông tin để consumer xử lý mà không phụ thuộc vào trạng thái tạm thời trong bộ nhớ của publisher.

## 7. Quy trình chọn giải pháp

Hãy trả lời lần lượt các câu hỏi sau:

1. **Bên nhận ở đâu?** Nếu là bean trong cùng Spring ApplicationContext, xem xét application event. Nếu là process hoặc hệ thống khác, cần adapter tích hợp.
2. **Có được phép mất event khi process dừng không?** Nếu có, xử lý phụ best-effort nội bộ có thể đủ. Nếu không, cần lưu bền vững như outbox hoặc broker phù hợp.
3. **Có cần chờ transaction commit không?** Nếu listener nội bộ chỉ được chạy khi commit thành công, dùng `@TransactionalEventListener(AFTER_COMMIT)`. Nếu cần bảo đảm thông điệp tích hợp, ghi outbox trong cùng transaction.
4. **Ai sở hữu schema?** Với consumer bên ngoài, xác định owner, version, quy tắc tương thích và cách xử lý event không nhận diện được.
5. **Consumer có chịu được gửi trùng không?** Thiết kế idempotency, retry và dead-letter trước khi đưa vào vận hành.

Ví dụ quyết định:

- Cập nhật cache nội bộ sau khi cấu hình thay đổi: application event có thể phù hợp.
- Ghi audit nội bộ đồng bộ cùng transaction: cân nhắc listener đồng bộ hoặc xử lý trực tiếp nếu đó là phần bắt buộc của nghiệp vụ.
- Gửi email sau khi đơn hàng commit: transactional listener có thể phù hợp nếu chấp nhận chính sách retry riêng; nếu không được mất yêu cầu gửi, hãy lưu công việc/outbox bền vững.
- Thông báo đơn hàng đã duyệt cho hệ thống kho ở service khác: integration event qua broker/API; nếu cần bảo đảm không bỏ sót, dùng outbox.
- Làm mới projection trong cùng ứng dụng: application event hoặc cập nhật trực tiếp tùy nhu cầu nhất quán và độ phức tạp.

## 8. Checklist trước khi triển khai

- [ ] Tên event thể hiện một sự kiện nghiệp vụ đã xảy ra.
- [ ] Đã xác định rõ event là nội bộ hay integration event.
- [ ] Payload chỉ chứa dữ liệu cần thiết và không làm lộ entity nội bộ.
- [ ] Đã chọn đồng bộ, bất đồng bộ hay xử lý sau commit dựa trên yêu cầu nghiệp vụ.
- [ ] Đã hiểu rõ hành vi khi listener ném exception và khi transaction rollback.
- [ ] Với tích hợp quan trọng, đã có outbox/broker, retry, idempotency và quan sát lỗi.
- [ ] Schema bên ngoài có version và quy tắc tương thích.
- [ ] Có log/trace đủ để nối publisher, event và consumer qua correlation ID.

## Kết luận

Spring Application Event là công cụ tách các thành phần trong cùng ứng dụng. Nó giúp publisher không cần biết listener cụ thể, nhưng không cung cấp hàng đợi bền vững hay hợp đồng giao tiếp giữa các service. Integration event thuộc ranh giới hệ thống và cần schema được quản lý cùng cơ chế vận chuyển phù hợp. Khi cần cập nhật database và phát thông điệp bên ngoài một cách tin cậy, hãy ghi outbox trong cùng transaction rồi để relay chuyển tiếp.
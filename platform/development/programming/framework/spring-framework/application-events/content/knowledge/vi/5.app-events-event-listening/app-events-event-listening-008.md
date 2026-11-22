# Listener không trả về và chỉ tạo side effect

## 1. Mục tiêu và phạm vi

Trong Spring Application Events, listener thường được dùng để phản ứng với một sự kiện bằng cách thực hiện một hành động. Nhiều listener không cần gửi dữ liệu kết quả trở lại nơi phát event. Chúng chỉ cần thực hiện side effect, chẳng hạn ghi audit log, cập nhật cache, tăng metric, gửi thông báo hoặc cập nhật một trạng thái phụ.

Một listener như vậy thường có method trả về kiểu `void`. Publisher phát event, Spring phân phối event đến listener, và listener tự thực hiện công việc của mình. Publisher không nhận một giá trị kết quả từ listener thông qua `publishEvent()`.

Sau bài học, bạn có thể:

- Giải thích listener `void` và ý nghĩa của side effect.
- Viết listener bằng `@EventListener` hoặc `ApplicationListener<E>`.
- Phân biệt listener chỉ tạo side effect với listener trả về một event mới.
- Hiểu thời điểm thực thi, lỗi và transaction ảnh hưởng đến side effect như thế nào.
- Chọn lời gọi service trực tiếp khi cần nhận kết quả xử lý.

Phạm vi của bài là event nội bộ trong một ApplicationContext Spring. Ví dụ dùng Java 17+ và Spring Framework, không cần Spring Boot.

## 2. Side effect là gì?

Side effect là thay đổi hoặc hành động quan sát được xảy ra khi một method thực thi, ngoài việc trả về một giá trị cho nơi gọi. Ví dụ:

- Ghi một dòng vào audit log.
- Lưu một bản ghi lịch sử vào database.
- Xóa một mục cache để lần đọc sau lấy dữ liệu mới.
- Gửi email hoặc thông báo.
- Tăng bộ đếm metric.
- Đẩy một tác vụ sang executor hoặc hệ thống messaging.

Giả sử ứng dụng phát event `OrderPlaced` sau khi tạo đơn hàng. Listener có thể ghi nhận lịch sử đơn hàng:

```java
@EventListener
public void recordOrder(OrderPlaced event) {
    auditService.record("ORDER_PLACED", event.orderId());
}
```

Method `recordOrder` trả về `void`: nó không cung cấp dữ liệu kết quả cho publisher. Công việc của nó là tạo side effect bằng cách gọi `auditService`.

Một listener có thể có nhiều side effect nếu chúng thuộc cùng một trách nhiệm rõ ràng. Tuy nhiên, nếu một method vừa gửi email, cập nhật kho, tính phí và ghi audit, hãy tách thành các listener hoặc service riêng để mỗi hành động có thể được hiểu, kiểm thử và xử lý lỗi độc lập.

## 3. Listener void hoạt động như thế nào?

Với `@EventListener`, kiểu tham số cho Spring biết listener muốn nhận loại event nào. Method có thể trả về `void`:

```java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // thực hiện side effect
}
```

Spring đăng ký method trên một Spring bean và gọi method khi event phù hợp được phát. Publisher thường chỉ cần biết rằng event đã xảy ra:

```java
publisher.publishEvent(new OrderPlaced("ORD-2001"));
```

API `ApplicationEventPublisher.publishEvent(Object)` có kiểu trả về `void`. Nó không tổng hợp kết quả từ các listener và cũng không trả về kết quả nghiệp vụ của từng listener.

Với cấu hình mặc định, listener được gọi đồng bộ. Vì vậy, lời gọi `publishEvent()` thường chỉ trả về sau khi các listener đồng bộ hoàn thành. Điều này không có nghĩa publisher nhận được kết quả từ listener: nó chỉ biết quá trình gọi listener đồng bộ đã kết thúc. Nếu listener ném exception, exception có thể truyền ngược về publisher.

Nếu listener được cấu hình bất đồng bộ, publisher có thể tiếp tục trước khi side effect hoàn thành. Khi đó, publisher cũng không biết công việc thành công hay thất bại chỉ từ lời gọi `publishEvent()`.

### Không trả về dữ liệu không có nghĩa là không có kết quả

Một listener `void` vẫn có thể tạo ra kết quả quan sát được trong hệ thống. Ví dụ, một bản ghi audit mới xuất hiện trong database hoặc một cache entry bị xóa. Kết quả này nằm ở trạng thái mà listener thay đổi, không nằm trong giá trị trả về của method.

Điều đó phù hợp với mô hình event notification: publisher thông báo một sự việc, các listener tự phản ứng. Nếu publisher cần nhận một giá trị để quyết định bước nghiệp vụ kế tiếp, event listener `void` không phải hợp đồng phù hợp.

## 4. Ví dụ hoàn chỉnh: ghi audit khi có đơn hàng mới

Ví dụ sau tạo một event `OrderPlaced`. Listener nhận event và ghi một dòng vào audit log trong bộ nhớ. Listener không trả về giá trị nào.

### Cấu hình Maven

Tạo project Maven, đặt mã nguồn tại `src/main/java/demo/SideEffectListenerDemo.java`, và thêm các phần cấu hình sau bên trong phần tử gốc `<project>` của `pom.xml`. Ví dụ dùng Spring Framework 6.2.19 và Java 17:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
        <version>6.2.19</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.0</version>
        </plugin>
        <plugin>
            <groupId>org.codehaus.mojo</groupId>
            <artifactId>exec-maven-plugin</artifactId>
            <version>3.5.0</version>
        </plugin>
    </plugins>
</build>
```

### Mã nguồn

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

@Configuration
public class SideEffectListenerDemo {

    @Bean
    AuditLog auditLog() {
        return new AuditLog();
    }

    @Bean
    OrderPlacedListener orderPlacedListener(AuditLog auditLog) {
        return new OrderPlacedListener(auditLog);
    }

    @Bean
    OrderService orderService(ApplicationEventPublisher publisher) {
        return new OrderService(publisher);
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SideEffectListenerDemo.class)) {

            OrderService orderService =
                    context.getBean(OrderService.class);

            orderService.place("ORD-2001");

            AuditLog auditLog = context.getBean(AuditLog.class);
            System.out.println("Audit entries: " + auditLog.entries());
        }
    }

    record OrderPlaced(String orderId) {
    }

    static class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void place(String orderId) {
            System.out.println("Publisher: order created " + orderId);
            publisher.publishEvent(new OrderPlaced(orderId));
            System.out.println("Publisher: publishEvent returned");
        }
    }

    static class OrderPlacedListener {
        private final AuditLog auditLog;

        OrderPlacedListener(AuditLog auditLog) {
            this.auditLog = auditLog;
        }

        @EventListener
        public void recordAudit(OrderPlaced event) {
            auditLog.append("Order placed: " + event.orderId());
            System.out.println("Listener: audit recorded");
        }
    }

    static class AuditLog {
        private final List<String> entries = new ArrayList<>();

        void append(String entry) {
            entries.add(entry);
        }

        List<String> entries() {
            return List.copyOf(entries);
        }
    }
}
```

Các điểm cần chú ý:

1. `OrderService` chỉ phụ thuộc vào `ApplicationEventPublisher`. Nó không biết `OrderPlacedListener` hoặc `AuditLog`.
2. `OrderPlaced` là một Java record, nên dữ liệu event bất biến sau khi tạo.
3. `OrderPlacedListener.recordAudit()` có kiểu trả về `void`. Side effect xảy ra ở lời gọi `auditLog.append(...)`.
4. `AuditLog.entries()` trả về bản sao không thể sửa của danh sách để phần đọc không thể thay đổi trạng thái nội bộ của audit log.
5. Các class được đăng ký bằng `@Bean`, vì vậy Spring quản lý listener và phát hiện `@EventListener` khi tạo ApplicationContext.

Audit log trong ví dụ chỉ lưu trong bộ nhớ để quan sát hành vi. Ứng dụng thực tế có thể inject một service ghi audit vào database hoặc một hệ thống log phù hợp.

### Biên dịch và chạy

Từ thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.SideEffectListenerDemo
```

Kết quả stdout:

```text
Publisher: order created ORD-2001
Listener: audit recorded
Publisher: publishEvent returned
Audit entries: [Order placed: ORD-2001]
```

Dòng `Listener: audit recorded` xuất hiện trước `Publisher: publishEvent returned` vì listener mặc định chạy đồng bộ. Dòng cuối xác nhận side effect đã cập nhật audit log. Không có giá trị trả về nào từ listener được chuyển về `OrderService`.

## 5. Một event có thể có nhiều listener void

Một event có thể được nhiều listener quan tâm. Ví dụ, khi `OrderPlaced` được phát, ứng dụng có thể:

- Ghi audit.
- Xóa cache tổng hợp đơn hàng.
- Ghi metric số đơn hàng mới.
- Gửi thông báo xác nhận.

Mỗi listener có thể là một bean riêng với method `void`:

```java
@Component
class OrderAuditListener {

    @EventListener
    public void record(OrderPlaced event) {
        auditService.record(event.orderId());
    }
}

@Component
class OrderCacheListener {

    @EventListener
    public void evict(OrderPlaced event) {
        orderCache.evict(event.orderId());
    }
}

@Component
class OrderMetricListener {

    @EventListener
    public void count(OrderPlaced event) {
        metrics.increment("orders.placed");
    }
}
```

Đây là đoạn minh họa cấu trúc, giả định `OrderPlaced`, `auditService`, `orderCache` và `metrics` đã được khai báo và inject phù hợp.

Publisher chỉ phát một event. Event multicaster phân phối event đến từng listener phù hợp. Các listener độc lập không cần gọi nhau và không cần trả kết quả cho nhau.

Nếu thứ tự giữa listener không quan trọng, hãy để chúng độc lập. Nếu có phụ thuộc thứ tự thực sự, có thể dùng `@Order`, nhưng không nên dựa vào thứ tự listener để xây dựng một quy trình nghiệp vụ phức tạp. Với quy trình cần kiểm soát từng bước và kết quả, dùng service điều phối tường minh sẽ dễ hiểu hơn.

## 6. Phân biệt listener void và listener trả về event

Spring cho phép method `@EventListener` trả về một object. Khi method trả về giá trị khác `void`, Spring phát giá trị đó như một event mới. Đây là cách tạo chuỗi event:

```java
@EventListener
public OrderAuditRecorded record(OrderPlaced event) {
    auditService.record(event.orderId());
    return new OrderAuditRecorded(event.orderId());
}
```

Ví dụ này có hai hành động: ghi audit và phát thêm `OrderAuditRecorded`. Listener nhận event mới có thể tiếp tục xử lý.

| Đặc điểm | Listener `void` | Listener trả về object |
|---|---|---|
| Giá trị trả về của method | Không có | Một object event |
| Side effect | Có thể có | Có thể có |
| Phát event tiếp theo tự động | Không | Có, nếu trả về object khác null |
| Publisher nhận kết quả trực tiếp | Không | Không |
| Mục đích thường gặp | Thực hiện hành động phụ trợ | Thực hiện hành động và thông báo một sự kiện tiếp theo |

Giá trị trả về từ listener không phải response của `publishEvent()`. Spring xem object trả về là một event mới và phân phối nó như event khác. Nếu muốn listener chỉ tạo side effect, khai báo method là `void` và không trả về event.

Không nên trả về một object chỉ để báo cho publisher rằng listener đã thành công. Publisher không nhận object đó như kết quả của lời gọi. Nếu cần kết quả đồng bộ, hãy gọi một service có kiểu trả về phù hợp.

## 7. Listener void và interface ApplicationListener

Ngoài annotation `@EventListener`, Spring có interface `ApplicationListener<E>`. Method `onApplicationEvent` vốn có kiểu trả về `void`:

```java
public class OrderAuditListener
        implements ApplicationListener<OrderPlaced> {

    private final AuditService auditService;

    public OrderAuditListener(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        auditService.record(event.orderId());
    }
}
```

Class này cũng phải được đăng ký như một bean. Interface phù hợp khi muốn biểu diễn listener bằng một class chuyên biệt hoặc dùng API listener truyền thống. Với phần lớn listener ứng dụng, `@EventListener` thường ngắn gọn và dễ đọc hơn.

Dù dùng annotation hay interface, listener không tạo một kênh trả kết quả về publisher. Cả hai đều phù hợp với cách xử lý event theo kiểu notification.

## 8. Side effect đồng bộ và bất đồng bộ

### Đồng bộ theo mặc định

Mặc định, Spring gọi listener trên thread phát event. Khi `publishEvent()` được gọi:

1. Spring tìm các listener phù hợp.
2. Spring gọi từng listener đồng bộ.
3. Listener thực hiện side effect.
4. Khi quá trình xử lý kết thúc, `publishEvent()` trả về.

Điều này hữu ích khi side effect nhỏ, nhanh và cần hoàn tất trong cùng luồng xử lý. Ví dụ, cập nhật một cấu trúc dữ liệu trong bộ nhớ hoặc ghi nhận một thay đổi đơn giản trong cùng transaction.

Tuy nhiên, một listener chậm sẽ làm chậm publisher. Nếu listener gửi email qua mạng hoặc gọi dịch vụ bên ngoài, thời gian chờ có thể kéo dài.

### Bất đồng bộ

Khi side effect có thể chạy ở background, có thể kết hợp `@Async` với `@EventListener` và bật async processing:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {
}

@Component
class NotificationListener {

    @Async
    @EventListener
    public void sendNotification(OrderPlaced event) {
        notificationService.sendOrderConfirmation(event.orderId());
    }
}
```

Đoạn minh họa giả định đã import `EnableAsync`, `Async`, `Component`, các kiểu event và service tương ứng. Bean listener phải được Spring quản lý và lời gọi phải đi qua proxy Spring; một lời gọi nội bộ trong cùng object không kích hoạt `@Async` theo chế độ proxy mặc định.

Với listener bất đồng bộ:

- Publisher có thể tiếp tục trước khi side effect hoàn thành.
- Publisher không biết kết quả thành công hay thất bại của listener qua `publishEvent()`.
- Exception của method `void` không truyền ngược về thread phát event. Có thể cấu hình `AsyncUncaughtExceptionHandler` để xử lý lỗi; mặc định Spring ghi log lỗi bất đồng bộ.
- Không nên giả định thứ tự hoàn thành giữa nhiều listener async.
- Transaction context của publisher không tự động được truyền sang thread executor.
- Nên cấu hình executor có giới hạn thread, hàng đợi và chính sách từ chối phù hợp với tải.

`@Async` giúp chạy công việc ở thread khác, nhưng không tạo hàng đợi bền vững. Nếu ứng dụng dừng trước khi task hoàn tất, side effect có thể chưa xảy ra.

## 9. Lỗi khi listener thực hiện side effect

### Listener đồng bộ ném exception

Với multicaster mặc định không cấu hình `ErrorHandler`, exception từ listener đồng bộ có thể truyền về nơi gọi `publishEvent()` và làm gián đoạn quá trình phân phối. Các listener tiếp theo có thể không được gọi nếu exception thoát khỏi multicaster.

Ví dụ:

```java
@EventListener
public void record(OrderPlaced event) {
    throw new IllegalStateException("Audit storage unavailable");
}
```

Nếu `OrderService` gọi `publishEvent()` mà không xử lý exception, lỗi có thể lan lên luồng gọi. Hãy quyết định rõ side effect nào được phép làm thất bại thao tác chính. Có thể xử lý lỗi tại listener, cấu hình `ErrorHandler` cho multicaster hoặc để lỗi truyền lên nếu đó là chính sách mong muốn.

Không nên bắt mọi exception rồi bỏ qua. Nếu không thể ghi audit hoặc gửi thông báo, cần có log và cơ chế quan sát phù hợp để người vận hành biết hành động đã thất bại.

### Listener bất đồng bộ gặp lỗi

Với listener `@Async` trả về `void`, publisher không thể nhận exception từ thread executor. Dùng `AsyncUncaughtExceptionHandler`, logging và monitoring để ghi nhận lỗi. Nếu nghiệp vụ cần retry hoặc cần biết trạng thái hoàn tất, hãy thiết kế cơ chế theo dõi riêng hoặc dùng message broker phù hợp.

### Side effect có thể lặp lại

Một event nội bộ có thể được phát nhiều lần do luồng nghiệp vụ gọi lặp, request retry hoặc lỗi ở tầng ứng dụng. Vì vậy, những side effect nhạy với trùng lặp như gửi email, ghi giao dịch hoặc cấp quyền nên có cơ chế idempotency khi cần.

Ví dụ, lưu `eventId` hoặc khóa nghiệp vụ đã xử lý và kiểm tra trước khi thực hiện hành động có thể giúp ngăn xử lý lặp. Việc kiểm tra và ghi nhận khóa idempotency phải được thiết kế phù hợp với transaction và kho lưu trữ.

## 10. Side effect và transaction

Nếu listener cập nhật database trong cùng thread và cùng transaction đang hoạt động, thay đổi đó có thể tham gia transaction hiện tại tùy cấu hình transaction manager và tài nguyên sử dụng. Khi transaction rollback, thay đổi database thuộc transaction đó có thể rollback cùng.

Một side effect bên ngoài database, chẳng hạn gửi email hoặc gọi HTTP API, thường không thể được rollback chỉ vì transaction database thất bại. Nếu listener gửi email trước khi transaction commit rồi transaction rollback, người nhận vẫn có thể nhận email về một đơn hàng không tồn tại.

Khi side effect phải đợi transaction commit, dùng `@TransactionalEventListener`:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderConfirmationListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void sendConfirmation(OrderPlaced event) {
        notificationService.sendOrderConfirmation(event.orderId());
    }
}
```

Cần cấu hình transaction management và phát event trong một transaction đang hoạt động. `AFTER_COMMIT` là phase mặc định của `@TransactionalEventListener`. Nếu không có transaction, listener mặc định không được gọi; chỉ bật `fallbackExecution = true` khi muốn xử lý cả trường hợp đó.

Listener sau commit vẫn chỉ là một callback trong tiến trình ứng dụng. Nếu tiến trình dừng sau khi database commit nhưng trước khi email được gửi, side effect có thể bị bỏ lỡ. Với yêu cầu giao nhận bền vững, hãy cân nhắc Transactional Outbox hoặc hệ thống messaging có lưu trữ và retry.

## 11. Khi nào dùng listener chỉ tạo side effect?

Dùng listener `void` khi event mô tả một sự việc đã xảy ra và các thành phần khác có thể tự phản ứng mà không cần trả kết quả cho publisher. Ví dụ:

- Ghi audit khi người dùng thay đổi hồ sơ.
- Xóa cache khi dữ liệu sản phẩm thay đổi.
- Tăng metric khi đơn hàng được tạo.
- Gửi thông báo sau khi thanh toán thành công.
- Cập nhật chỉ mục tìm kiếm khi nội dung được xuất bản.

Hãy gọi service trực tiếp khi:

- Publisher cần dữ liệu trả về để quyết định bước tiếp theo.
- Side effect là điều kiện bắt buộc để nghiệp vụ chính thành công.
- Cần kiểm soát rõ thứ tự, kết quả và lỗi của từng bước.
- Người gọi phải biết ngay thao tác thành công hay thất bại.

Một nguyên tắc hữu ích: event phù hợp để thông báo rằng một điều đã xảy ra; lời gọi service phù hợp khi cần yêu cầu một hành động và nhận kết quả của hành động đó.

## 12. Kiểm thử listener void

Vì listener `void` không có kết quả trả về, test nên kiểm tra side effect mà nó tạo ra.

### Unit test listener

Gọi method trực tiếp với event mẫu, rồi xác minh dependency được gọi:

```java
@Test
void recordsAuditWhenOrderIsPlaced() {
    AuditService auditService = mock(AuditService.class);
    OrderAuditListener listener = new OrderAuditListener(auditService);

    listener.record(new OrderPlaced("ORD-2001"));

    verify(auditService).record("ORD-2001");
}
```

Đoạn test minh họa giả định listener nhận `AuditService` qua constructor và có method `record`; cần có JUnit Jupiter và Mockito trong test dependencies.

### Kiểm thử phân phối event

Dùng ApplicationContext trong integration test để xác nhận bean listener được đăng ký và được gọi khi publisher phát đúng event. Có thể dùng `@RecordApplicationEvents` cùng `ApplicationEvents` của Spring Test để ghi nhận event đã phát.

### Kiểm thử listener bất đồng bộ

Không kiểm tra side effect async ngay lập tức sau `publishEvent()`, vì task có thể chưa chạy xong. Dùng latch, Awaitility hoặc cơ chế đồng bộ phù hợp để đợi điều kiện hoàn tất với timeout hữu hạn. Tránh `Thread.sleep()` cố định vì làm test chậm và không ổn định.

### Kiểm thử lỗi

Kiểm tra chính sách khi dependency ném exception: lỗi có truyền về publisher hay được xử lý tại listener? Với async listener, xác minh `AsyncUncaughtExceptionHandler` hoặc cơ chế ghi nhận lỗi. Kiểm tra cả trường hợp event được phát lặp nếu side effect cần idempotency.

## 13. Lỗi thiết kế thường gặp

1. **Mong đợi publisher nhận kết quả từ listener:** `publishEvent()` trả về `void`; dùng service có return type nếu cần kết quả.
2. **Trả về object chỉ để báo thành công:** Spring xem object trả về từ `@EventListener` là event mới. Nó không trở thành response cho publisher.
3. **Cho rằng listener mặc định chạy nền:** listener mặc định chạy đồng bộ; cần bật async và dùng `@Async` nếu muốn chạy bằng executor.
4. **Đặt side effect quan trọng trong listener async mà không theo dõi:** publisher không biết listener đã hoàn thành hay thất bại.
5. **Gửi email trước khi transaction commit:** side effect bên ngoài database không tự rollback. Dùng transaction-bound listener khi phù hợp.
6. **Nuốt exception:** lỗi side effect bị che giấu và khó phát hiện. Cần logging, monitoring hoặc cơ chế phục hồi.
7. **Không chống xử lý trùng:** cùng một event có thể được phát nhiều lần. Side effect quan trọng cần cân nhắc idempotency.
8. **Gộp quá nhiều trách nhiệm vào một listener:** listener khó kiểm thử và lỗi một hành động có thể ảnh hưởng các hành động khác. Tách theo trách nhiệm.
9. **Dùng event cho một thao tác cần response:** giao tiếp event không phải request-response. Gọi service trực tiếp khi cần dữ liệu kết quả.

## 14. Checklist trước khi đưa listener vào ứng dụng

- [ ] Event mô tả rõ sự việc đã xảy ra.
- [ ] Listener được đăng ký như Spring bean.
- [ ] Method trả về `void` khi chỉ cần thực hiện side effect.
- [ ] Payload event nhỏ và bất biến.
- [ ] Publisher không phụ thuộc vào kết quả trả về của listener.
- [ ] Đã quyết định listener chạy đồng bộ hay bất đồng bộ.
- [ ] Đã xác định exception sẽ được xử lý ở đâu.
- [ ] Side effect bên ngoài database chỉ chạy sau commit nếu nghiệp vụ yêu cầu.
- [ ] Side effect quan trọng có quan sát lỗi và cơ chế chống trùng khi cần.
- [ ] Đã kiểm thử hành động được tạo ra, thời điểm thực thi và tình huống lỗi.

## 15. Tài liệu tham khảo

- [Spring Framework Reference — Application Events](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html#context-functionality-events)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework API — EventListener](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/event/EventListener.html)



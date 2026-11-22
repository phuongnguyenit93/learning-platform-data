# Phát event tiếp theo từ kết quả listener trong Spring Framework

## 1. Khái niệm: kết quả listener có thể trở thành event mới

Trong **Spring Framework Application Events**, một phương thức **@EventListener** đồng bộ không bắt buộc trả về **void**. Nếu phương thức trả về một đối tượng không phải **null**, Spring có thể **publish kết quả đó như một application event mới**. Các listener nhận kiểu event mới tiếp tục được gọi, nhờ vậy nhiều bước có thể nối thành một **event chain**.

Ví dụ:

~~~text
OrderRequested
      |
      v
@EventListener validate(...) -> OrderValidated
      |
      v
@EventListener prepare(...) -> InvoiceRequested
      |
      v
@EventListener onInvoiceRequested(...)
~~~

Trong sơ đồ, tên method không quyết định loại event tiếp theo: **object mà method trả về** quyết định. Một listener có thể xử lý A rồi return B; adapter của Spring sẽ công bố B. Listener nhận B lại có thể tạo C. Đó là cơ chế **return-value event publication**, không phải gọi một method Java trực tiếp giữa các business services.

Các quy tắc quan trọng:

- **Trả về một object:** Spring công bố object đó thành một event mới.
- **Trả về Collection hoặc array:** Spring công bố **từng phần tử** thành một event riêng.
- **Trả về null hoặc void:** không phát thêm event từ kết quả listener.
- **@Async @EventListener:** cơ chế phát event tiếp bằng **giá trị trả về không được hỗ trợ**; cần inject **ApplicationEventPublisher** và publish thủ công nếu muốn phát event tiếp.
- Với **SimpleApplicationEventMulticaster** mặc định chạy đồng bộ, event mới thường được dispatch trong cùng thread và cùng call stack của event gốc.
- **Event chain không tự mang nghĩa replay, queue, retry, giao dịch hoặc lưu bền vững**. Nó chỉ nói cách công bố một event tiếp theo từ kết quả xử lý hiện tại.

Kỹ thuật này phù hợp cho các chuyển đổi sự kiện nhỏ, rõ ràng. Với các bước có transaction, thực hiện ngoài hệ thống hoặc cần khôi phục sau crash, phải thiết kế ranh giới và độ tin cậy riêng.

## 2. Spring thực hiện return-to-event như thế nào?

Khi một Spring-managed bean có method **@EventListener**, Spring đăng ký adapter để gọi method đó khi loại event phù hợp xuất hiện. Dòng xử lý điển hình:

~~~text
Caller
  |
  +-- publisher.publishEvent(EventA)
          |
          v
      ApplicationEventMulticaster
          |
          v
      @EventListener method onA(EventA)
          |
          +-- return EventB
                  |
                  v
          Spring publishes EventB
                  |
                  v
          @EventListener method onB(EventB)
                  |
                  +-- có thể trả EventC, hoặc kết thúc
~~~

Điều đáng lưu ý:

1. **publishEvent(...)** là API công bố, trả về **void**; caller không nhận EventB như một return value.
2. **EventB** được publish bởi framework **sau khi method listener onA(...) trả về**.
3. EventB có thể là một **POJO/record Java**, không cần extends **ApplicationEvent**.
4. Method listener chỉ được xử lý tự động khi event được dispatch qua **ApplicationContext**. Nếu code test gọi trực tiếp **onA(...)**, đó chỉ là một lời gọi method Java, không tự phát EventB.
5. Việc chọn thread và error propagation có thể bị thay đổi nếu ứng dụng cấu hình multicaster/executor riêng.

Ví dụ method tạo event tiếp:

~~~java
@EventListener
public ShipmentRequested afterPaymentConfirmed(PaymentConfirmed event) {
    return new ShipmentRequested(event.orderId());
}
~~~

Đây là **đoạn minh họa**, cần khai báo hai event types và đăng ký class chứa method thành Spring bean. Trong trường hợp này, nếu có listener nhận **ShipmentRequested**, Spring có thể gọi listener đó sau khi method trên trả về object mới.

Nếu cùng method return một **String**, Spring cũng có thể coi chuỗi đó là object payload được publish như event. Do đó, đừng trả về dữ liệu tính toán tùy ý từ **@EventListener** trừ khi bạn thật sự muốn nó trở thành event tiếp theo.

## 3. Một event, nhiều event, hoặc không phát event tiếp

| Chữ ký / kết quả | Cách Spring xử lý |
| --- | --- |
| **EventB onA(EventA e)** trả **new EventB(...)** | Publish một EventB |
| **Object onA(EventA e)** trả một event object được chọn theo điều kiện | Publish object thực tế đó |
| **List<EventB> onA(EventA e)** | Publish từng EventB trong danh sách |
| **Collection<Object> onA(EventA e)** | Publish từng phần tử như một event |
| **EventB[] onA(EventA e)** | Publish từng phần tử array như một event |
| Method trả **null** | Không publish event mới từ kết quả |
| Method trả **List.of()** rỗng | Không có phần tử để publish |
| Method **void onA(EventA e)** | Không có event tự động từ return value |

### 3.1. Trả về Collection để fan-out

~~~java
@EventListener
public List<Object> afterPaymentConfirmed(PaymentConfirmed event) {
    return List.of(
            new ShipmentRequested(event.orderId()),
            new ReceiptRequested(event.orderId()));
}
~~~

**ShipmentRequested** và **ReceiptRequested** được publish **riêng lẻ**, không phải cả **List** được coi là một event. Dùng **List** nếu muốn thể hiện thứ tự phát trong ví dụ; dùng **HashSet** không thích hợp khi cần thứ tự duyệt dự đoán được.

Nếu nghiệp vụ thật sự cần **một sự kiện chứa danh sách**, tạo một wrapper event rõ ràng như **BatchCompleted(List<String> orderIds)** và return object **BatchCompleted**. Đừng trả **List<OrderId>** rồi nghĩ Spring tự hiểu đây là một sự kiện batch.

### 3.2. Trả null khi kết thúc một nhánh

~~~java
@EventListener
public StockReserved reserve(OrderRequested event) {
    if (event.quantity() <= 0) {
        return null;
    }
    return new StockReserved(event.orderId());
}
~~~

Đoạn minh họa này cho thấy **null nghĩa là không công bố kết quả tiếp**. Tuy nhiên trong nghiệp vụ thật, một trạng thái từ chối quan trọng thường nên có event riêng như **OrderRejected** thay vì lặng lẽ trả null; như vậy quan sát hệ thống và xử lý lỗi sẽ rõ hơn.

### 3.3. Cảnh báo về return value vô tình

Một listener **@EventListener** mà developer chỉ muốn ghi log hoặc tính số liệu nhưng lại return **String**, **Boolean**, **Integer** hoặc DTO nội bộ có thể vô tình tạo một event mới. Nếu không cần công bố event, đổi method thành **void**, và lưu kết quả bằng cơ chế phù hợp. **Return type là một phần của hợp đồng publication**, không phải cách trả response cho người gọi event publisher.

## 4. Ví dụ Java 17+ chạy được: chuỗi, rẽ nhánh, fan-out và null

Ví dụ dùng **Spring Framework 6.2.9**, **JDK 17+** và **Gradle 8.x**. Không cần Spring Boot, database hay broker. Chuỗi xử lý cho thấy event được tạo từ return value, bao gồm cả các nhánh không tiếp tục.

Cấu trúc:

~~~text
event-return-chain/
  build.gradle
  src/main/java/demo/EventReturnChainDemo.java
~~~

Nội dung file **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'demo.EventReturnChainDemo'
}
~~~

Nội dung file **src/main/java/demo/EventReturnChainDemo.java**:

~~~java
package demo;

import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventReturnChainDemo {

    public record OrderRequested(String id, int quantity) {}
    public record OrderValidated(String id, int quantity) {}
    public record OrderRejected(String id) {}
    public record InvoiceRequested(String id) {}
    public record AuditRequested(String id) {}

    public static class ChainListeners {

        @EventListener
        public Object evaluate(OrderRequested event) {
            System.out.println("requested: " + event.id());

            if (event.quantity() < 0) {
                return null; // Stop: no follow-up event.
            }
            if (event.quantity() == 0) {
                return new OrderRejected(event.id());
            }
            return new OrderValidated(event.id(), event.quantity());
        }

        @EventListener
        public List<Object> validated(OrderValidated event) {
            System.out.println("validated: " + event.id());
            return List.of(
                    new InvoiceRequested(event.id()),
                    new AuditRequested(event.id()));
        }

        @EventListener
        public void onInvoiceRequested(InvoiceRequested event) {
            System.out.println("invoice: " + event.id());
        }

        @EventListener
        public void onAuditRequested(AuditRequested event) {
            System.out.println("audit: " + event.id());
        }

        @EventListener
        public void onRejected(OrderRejected event) {
            System.out.println("rejected: " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        ChainListeners chainListeners() {
            return new ChainListeners();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("caller: publish A");
            context.publishEvent(new OrderRequested("A", 2));
            System.out.println("caller: returned A");

            System.out.println("caller: publish B");
            context.publishEvent(new OrderRequested("B", 0));
            System.out.println("caller: returned B");

            System.out.println("caller: publish C");
            context.publishEvent(new OrderRequested("C", -1));
            System.out.println("caller: returned C");
        }
    }
}
~~~

Tại thư mục **event-return-chain**:

~~~bash
gradle --console=plain -q run
~~~

Các dòng **stdout do code tự in ra**:

~~~text
caller: publish A
requested: A
validated: A
invoice: A
audit: A
caller: returned A
caller: publish B
requested: B
rejected: B
caller: returned B
caller: publish C
requested: C
caller: returned C
~~~

**Giải thích output:**

1. **OrderRequested("A", 2)** được publish. Listener **evaluate(A)** in **requested: A**, trả **OrderValidated(A, 2)**. Spring publish event đó, gọi **validated(A)** và nhận **List.of(InvoiceRequested(A), AuditRequested(A))**. Mỗi event con được publish; listeners in **invoice: A** rồi **audit: A**. Vì multicaster mặc định đồng bộ, caller in **returned A** sau khi chuỗi xử lý xong.
2. **OrderRequested("B", 0)** rẽ sang **OrderRejected(B)**. Không có OrderValidated, InvoiceRequested hoặc AuditRequested cho B; listener **onRejected** in **rejected: B**.
3. **OrderRequested("C", -1)** trả **null**. Không có event tiếp theo từ return value, nên chương trình in **returned C** ngay sau dòng **requested: C**.
4. Các kiểu event là **Java records**, không extends ApplicationEvent. Spring chấp nhận object payload events và tìm listener theo kiểu tương ứng.
5. Trong chương trình không có **@Async**, custom task executor hoặc transaction manager; điều đó quan trọng để dự đoán stdout.

**Phạm vi ví dụ:** Tên InvoiceRequested và AuditRequested chỉ là mô phỏng; code không tạo invoice thực, không ghi database, không gửi email và không bảo đảm message delivery. Đây là ví dụ để hiểu cơ chế return-to-event, không phải workflow tài chính production.

## 5. Chuỗi lồng nhau và thứ tự thực thi

Khi Spring dùng **SimpleApplicationEventMulticaster** đồng bộ mặc định, return event làm event mới được publish **ngay trong quá trình xử lý listener hiện tại**:

~~~text
Caller publish A
  -> Listener A xử lý
       -> return B
       -> Spring publish B
            -> Listener B xử lý
                 -> return [C, D]
                 -> Spring publish C
                      -> Listener C
                 -> Spring publish D
                      -> Listener D
  <- publish A hoàn tất
Caller tiếp tục
~~~

Hậu quả:

- Một xử lý downstream chậm có thể làm **publishEvent(A)** ban đầu chậm theo.
- Exception ở listener downstream có thể ảnh hưởng đến caller ban đầu trong cấu hình đồng bộ mặc định.
- Một listener cho event gốc có thể return event con; chuỗi con được dispatch **trước khi** multicaster quay lại những listener khác chưa chạy của event gốc.
- Thứ tự hoàn tất không được bảo đảm khi dùng custom multicaster với executor hoặc các listener chạy bất đồng bộ.

### 5.1. @Order không phải workflow engine

Spring cho phép ưu tiên giữa nhiều listeners nhận cùng một loại event:

~~~java
@EventListener
@Order(10)
public FollowUpEvent first(OriginalEvent event) {
    return new FollowUpEvent(event.id());
}

@EventListener
@Order(20)
public void second(OriginalEvent event) {
    // Another listener for the original event.
}
~~~

Đây là **snippet minh họa**, cần event types và imports phù hợp. Trong chuỗi đồng bộ, **first(...)** có thể publish và xử lý **FollowUpEvent** trước khi **second(...)** xử lý **OriginalEvent**. **@Order** không diễn đạt quan hệ dependency giữa mọi event types, không phải bảo đảm toàn bộ workflow hoàn tất theo thứ tự trong môi trường async.

Khi cần nhiều bước bắt buộc theo thứ tự, được truyền lỗi và rollback rõ ràng, **application service call trực tiếp** có thể phù hợp hơn event chain.

### 5.2. Fan-out khác queue competing consumers

Nếu một event loại **InvoiceRequested** có ba listeners, Spring có thể gọi cả ba. Không có nghĩa event được giao cho đúng một consumer như queue cạnh tranh. Trả về Collection chỉ tạo **nhiều events**, còn mỗi event vẫn có thể được nhiều listeners xử lý.

## 6. Tránh tạo vòng lặp event

Một lỗi có thể rất nguy hiểm:

~~~text
@EventListener(A) -> return B
@EventListener(B) -> return A
@EventListener(A) -> return B
...
~~~

Với dispatch đồng bộ lồng nhau, chuỗi không kết thúc có thể tạo recursion sâu, **StackOverflowError**, CPU tăng hoặc ứng dụng không trả response. Spring không tự xác minh đồ thị event của bạn không có chu trình.

**Biện pháp:**

- Thiết kế event types biểu diễn các state transitions có điểm kết thúc rõ: **Requested → Validated → Completed/Rejected**.
- Dùng **void** hoặc **null** khi không cần thêm bước; đừng return event chỉ để giữ chuỗi chạy.
- Nếu chuỗi có thể được tạo động, dùng giới hạn **hopCount** hoặc trạng thái workflow; tăng hopCount khi tạo event tiếp theo và từ chối vượt ngưỡng.
- Gắn **correlation ID**, **event ID** và business key để theo dõi nhiều chuỗi độc lập.
- Thiết kế **idempotency**: cùng event bị gửi lại không được gây thanh toán/email trùng.
- Kiểm thử cả trường hợp event bị phát lại, listener lỗi và nhánh chuyển trạng thái không hợp lệ.

Ví dụ một event có metadata:

~~~java
public record WorkflowAdvanced(
        String workflowId,
        String correlationId,
        int hopCount) {
}
~~~

Đây là Java record minh họa; code kiểm tra giới hạn hopCount phải nằm trong use case/listener thích hợp. Không dùng một biến static toàn cục để đánh dấu “đã xử lý”, vì nó có thể chặn nhầm các request độc lập.

## 7. Return value và ApplicationEventPublisher: hai cách tiếp tục chuỗi

### 7.1. Return event từ listener đồng bộ

~~~java
@EventListener
public ShippingRequested afterInvoiceCreated(InvoiceCreated event) {
    return new ShippingRequested(event.orderId());
}
~~~

Cách này gọn khi mỗi lần xử lý cho đúng một kết quả event rõ ràng. Spring publish event mới khi method trả về.

### 7.2. Publish tường minh

~~~java
private final ApplicationEventPublisher publisher;

@EventListener
public void afterInvoiceCreated(InvoiceCreated event) {
    // Xử lý điều kiện rồi chọn chính xác lúc phát.
    publisher.publishEvent(new ShippingRequested(event.orderId()));
}
~~~

Hai đoạn này là **snippet**, cần bean, imports và event definitions. Phát tường minh phù hợp khi cần chủ động thời điểm publication hoặc publish từ code không phải @EventListener. Tránh dùng đồng thời **return event** và **publishEvent** cho cùng một event, vì có thể tạo duplicate.

| Tình huống | Return event | Publisher tường minh |
| --- | --- | --- |
| Một listener đồng bộ chuyển A thành B | Rất gọn | Dùng được |
| Một listener tạo nhiều events | Return Collection/array | Gọi nhiều lần |
| Không có bước tiếp theo | Return null/void | Không gọi publish |
| @Async @EventListener | **Không hỗ trợ chain bằng return** | **Dùng publisher** |
| Cần publish ở giữa nhiều thao tác | Chỉ publish khi method return | Chọn được đúng thời điểm |
| Cần mapping giữa domain event và infrastructure | Listener/adapter ở lớp ngoài | Cũng nên đặt publisher trong adapter |
| Cần giao đến queue bền vững | Không tự có | Không tự có; phải thiết kế adapter/outbox |

## 8. Giới hạn quan trọng của @Async @EventListener

Tài liệu Spring Framework xác nhận: **async event listener không thể phát sự kiện tiếp theo bằng return value**. Vì vậy không dùng kết quả từ một method **@Async @EventListener** như lời hứa rằng Spring sẽ tự publish event tiếp.

**Phản ví dụ về hợp đồng return-to-event:**

~~~java
@Async
@EventListener
public NextEvent process(PreviousEvent event) {
    return new NextEvent(event.id());
}
~~~

Khi cần phát tiếp từ async handler, hãy gọi publisher tường minh:

~~~java
@Component
public class AsyncFollowUpHandler {
    private final ApplicationEventPublisher publisher;

    public AsyncFollowUpHandler(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Async
    @EventListener
    public void on(PreviousEvent event) {
        // Xử lý xong, kiểm tra kết quả và điều kiện tiếp tục.
        publisher.publishEvent(new NextEvent(event.id()));
    }
}
~~~

Các ví dụ mục này **không phải file độc lập**; cần **@EnableAsync**, executor, event types và imports tương ứng. Trong production, phải cấu hình giới hạn hàng đợi, timeout, error handling và chính sách shutdown cho executor.

Các khác biệt khi async:

- Publisher ban đầu **không nhất thiết đợi** xử lý async kết thúc.
- Exception từ **void @Async** không tự truyền về caller; cần error handler phù hợp như **AsyncUncaughtExceptionHandler** hoặc cơ chế quan sát riêng.
- Transaction context **ThreadLocal** và logging MDC thường **không được truyền tự động** sang thread executor.
- Chuỗi event mới có thể chạy sau khi request ban đầu đã trả lời.
- Task async nằm trong memory có thể mất khi process bị kill; việc gọi publisher từ async cũng không biến nó thành queue bền vững.

Nếu workflow thực sự cần chờ một bước async rồi tiếp tục sau khi service restart, hãy cân nhắc orchestration/state machine và persistent queue thay vì phụ thuộc return value.

## 9. Exceptions ở các bước downstream

Giả sử listener A return B nhưng listener B ném **IllegalStateException**. Với multicaster đồng bộ mặc định và không có **ErrorHandler** đặc biệt, exception có thể truyền từ listener B về quá trình publish B, rồi tới event handler A và cuối cùng về caller gọi publish A.

~~~text
Caller publish A
 -> ListenerA returns B
 -> Spring publishes B
 -> ListenerB throws IllegalStateException
 -> exception propagates toward original publisher
~~~

Hệ quả là các listeners khác có thể chưa được gọi, chuỗi dừng giữa chừng và side effects trước lỗi có thể đã xảy ra. Cấu hình **SimpleApplicationEventMulticaster.setErrorHandler(...)**, custom executor, @Async hoặc transaction-aware listener có thể thay đổi cách lỗi được xử lý. Đừng thiết kế dựa vào một quy tắc propagation duy nhất nếu cấu hình đã đổi.

**Cần xử lý bắt buộc trước khi tiếp tục?** Nếu một bước cần giá trị trả về trực tiếp, validation cứng và error handling cụ thể, lời gọi application service có thể diễn đạt hợp đồng tốt hơn:

~~~text
validateOrder()
    -> reserveStock()
    -> chargePayment()
    -> saveResult()
~~~

Sơ đồ trên là **pseudo-flow**, không phải code Java runnable. Event chain phù hợp hơn cho các phản ứng độc lập hoặc những chuyển trạng thái được xác định rõ bằng event. Nó không thay thế transaction orchestration.

## 10. Transaction: event tiếp theo có thể vẫn trước commit

Giả sử application service có **@Transactional**:

~~~text
BEGIN TRANSACTION
  save order
  publish OrderCreated
     -> @EventListener returns InvoiceRequested
     -> @EventListener(InvoiceRequested) xử lý
  application method returns
COMMIT hoặc ROLLBACK
~~~

Trong trường hợp đồng bộ mặc định, cả listener ban đầu và listener nhận event tiếp theo thường chạy **trong transaction chưa commit**. Nếu listener con gửi email hoặc HTTP call trước commit, rồi transaction rollback, side effect bên ngoài không tự bị hoàn tác.

**Đừng hiểu “return event B” là “event B chỉ chạy sau khi commit”.** Hai khái niệm hoàn toàn khác: **event chain** mô tả cách publication tiếp tục, còn **transaction phase** mô tả thời điểm một callback được chạy.

Nếu cần phản ứng sau commit, infrastructure có thể dùng **@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)**:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderCreated event) {
    // Thực thi sau khi transaction liên quan commit thành công.
}
~~~

Đây là **snippet minh họa**, yêu cầu bean/transaction manager và event được publish trong transaction tương thích. Mặc định **fallbackExecution=false**, nên method transactional listener không chạy khi không có transaction phù hợp.

Sau **AFTER_COMMIT**, transaction chính đã commit; thao tác cần ghi dữ liệu mới có commit riêng thường cần một transaction mới như **Propagation.REQUIRES_NEW** qua Spring-managed service. Đừng giả định publication của event tiếp theo ở callback hậu commit vẫn tham gia một giao dịch đang mở.

### 10.1. Khi yêu cầu không được mất event: transactional outbox

**@EventListener return value** là cơ chế **in-memory**. Nếu JVM chết giữa hai bước, Spring không tự phát lại chuỗi. Trong hệ thống cần giao việc bền vững, dùng **transactional outbox**:

~~~text
BEGIN TRANSACTION
  save domain state
  save outbox event record
COMMIT
  -> worker đọc outbox
  -> publish tới broker / thực hiện bước tiếp
  -> retry nếu lỗi
  -> lưu trạng thái đã xử lý
~~~

Outbox record được commit trong **cùng transaction database** với state nghiệp vụ, giảm rủi ro mất ý định công bố. Worker và consumer vẫn phải **idempotent** vì có thể xử lý trùng khi message gửi thành công nhưng xác nhận hoàn tất thất bại. Outbox không tự bảo đảm exactly-once end-to-end.

## 11. Phát lại (replay) không giống tạo event chain

Nhóm kiến thức này là **“Phát lại và chuỗi event”**. Điều cần phân biệt:

- **Event chain:** nhận A, xử lý A rồi tạo event B ngay từ return value hoặc publisher. Không cần lịch sử event.
- **Replay:** đọc lại các event **đã lưu** để dựng projection, khôi phục trạng thái hoặc xử lý lại; cần event log/outbox/event store và chính sách replay.
- **Retry:** thử lại một bước lỗi theo chính sách; không tự xuất hiện chỉ vì method trả một event.
- **Redelivery:** message broker đưa lại event; listener có thể bị gọi nhiều lần và tạo ra event con lặp.

Ví dụ: Khi replay lịch sử **OrderValidated** để dựng lại báo cáo, một listener không được vô tình phát **SendInvoiceEmailRequested** rồi gửi email lần nữa. Nên tách projection idempotent khỏi side effects, nhận biết chế độ replay và dùng event IDs/correlation IDs.

**ApplicationEventPublisher** không phải một event store và không có replay lịch sử mặc định. Trả về event mới cũng không làm event đó được lưu vĩnh viễn.

## 12. Thiết kế event types có hợp đồng rõ

Một chain dễ hiểu nên thể hiện các bước:

~~~text
OrderRequested
    -> OrderValidated / OrderRejected
    -> InvoiceRequested
    -> InvoiceCreated / InvoiceFailed
~~~

Đặt tên event theo ý nghĩa: request, trạng thái đã xảy ra và thất bại. Đừng dùng một event chung như **ProcessingEvent(status)** cho mọi nhánh nếu nó khiến listeners phải kiểm tra hàng loạt chuỗi status và tự dựng graph không rõ ràng.

Mỗi event nên chứa dữ liệu tối thiểu cần cho phản ứng: aggregate/business ID, correlation ID, event ID, và thông tin trạng thái/phiên bản khi thích hợp. Ví dụ:

~~~java
public record InvoiceRequested(
        String orderId,
        String correlationId,
        int hopCount) {
}
~~~

Đây là Java record độc lập, không phụ thuộc Spring. Tránh nhét **EntityManager**, mutable JPA entity hoặc HTTP request object vào event. Với broker, có thể map domain event sang integration message đã version hóa, không bắt domain event phải kế thừa framework types.

## 13. Kiểm thử cơ chế return-to-event

**Unit test gọi trực tiếp method listener không chứng minh Spring tự publish kết quả.** Để kiểm tra return-to-event, phải dispatch qua **ApplicationContext** thật với bean **@EventListener** đã đăng ký.

Các test quan trọng:

1. Publish **OrderRequested(A, 2)**, xác nhận chuỗi tạo **OrderValidated**, **InvoiceRequested**, **AuditRequested**.
2. Publish **OrderRequested(B, 0)**, xác nhận chỉ tạo **OrderRejected**.
3. Publish **OrderRequested(C, -1)**, xác nhận không có event tiếp theo từ **null**.
4. Method trả **List.of(B, C)**: cả hai loại được publish riêng.
5. Method trả **Event[]**: mỗi phần tử được dispatch.
6. Listener trả **void**: không tự sinh event mới.
7. Có nhiều listeners cho event gốc và **@Order**: kiểm tra nested dispatch và thứ tự theo cấu hình.
8. Listener downstream ném exception: kiểm tra hành vi propagation theo multicaster/error policy.
9. **@Async**: xác nhận không dựa vào return value, kiểm tra publish tường minh và executor.
10. Transaction rollback: xác nhận side effect thực sự diễn ra trước hay sau commit.
11. Replay/redelivery: kiểm tra idempotency, điều kiện dừng và khả năng xử lý duplicate.

Với synchronous multicaster, có thể ghi các sự kiện được nhận vào một **List** do test quản lý rồi assert ngay sau **publishEvent(...)**. Với async, dùng **CountDownLatch** hoặc test utilities như Awaitility; tránh **Thread.sleep(...)** tùy ý để đoán thời điểm hoàn tất.

Ví dụ kỳ vọng của demo mục 4:

~~~text
input A -> OrderValidated(A), InvoiceRequested(A), AuditRequested(A)
input B -> OrderRejected(B)
input C -> no follow-up events
~~~

Đây là **kịch bản test**, không phải một JUnit class độc lập. Nếu viết JUnit, chỉ tính các next events, không tính event đầu vào do caller phát, khi mục tiêu là xác minh return-to-event.

## 14. Lỗi thường gặp và hướng khắc phục

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tưởng **publishEvent(A)** trả về B | API trả void; caller không nhận B | Hiểu return event là publication mới |
| Trả về String/boolean như kết quả xử lý | Object bị coi là event ngoài ý muốn | Đổi method thành void hoặc return event type rõ |
| Trả List và nghĩ List là một event duy nhất | Spring publish từng phần tử | Tạo **BatchXxx** wrapper nếu muốn một event chứa danh sách |
| **@Async @EventListener** return event | Không tạo chain bằng return value | Inject **ApplicationEventPublisher**, publish tường minh |
| Listener A trả B, B lại trả A | Đệ quy/vòng lặp vô hạn | Điều kiện dừng, hop-count, state machine |
| Dựa vào @Order để điều phối async pipeline | Không đảm bảo thứ tự hoàn thành | Orchestrator/queue và test concurrency |
| Nghĩ return B là B được chạy sau commit | Side effect có thể trước commit | Dùng transactional listener/outbox đúng phạm vi |
| Nghĩ event chain lưu bền vững | JVM chết gây mất việc | Outbox/queue, retry, idempotency |
| Replay event lịch sử nhưng phát side effects mới | Gửi thông báo hoặc lệnh trùng | Tách projection khỏi side effects |
| Gọi trực tiếp method listener trong unit test và chờ Spring publish | Bỏ qua event adapter | Test tích hợp qua ApplicationContext |
| Fan-out nhiều event nhưng không có correlation ID | Khó trace, phát hiện trùng và tìm lỗi | Event ID + correlation ID và metrics |
| Dùng event chain cho quy tắc bắt buộc phức tạp | Khó quan sát exception/rollback | Service call rõ ràng ở application layer |

## 15. Checklist trước khi dùng return value

- **Event mới được thể hiện bởi một class/record có tên rõ ràng?**
- **Listener đồng bộ hay async?** Nếu **@Async**, không dùng return value để publish.
- **Trả một event, array/Collection hay null?** Hiểu đúng ý nghĩa từng dạng?
- **Có điều kiện dừng và giới hạn vòng lặp?**
- **Có nhiều listeners cho event gốc?** Đã đánh giá **@Order** và nested dispatch?
- **Nếu listener con lỗi, caller và các listener khác bị ảnh hưởng thế nào?**
- **Chuỗi diễn ra trước hay sau transaction commit?** Có side effect không thể rollback?
- **Nếu phải xử lý sau crash, có outbox/queue và idempotency không?**
- **Nếu replay hoặc retry, có ngăn side effects lặp?**
- **Có integration test chứng minh Spring tự publish từ return value không?**

**Kết luận:** Với **@EventListener đồng bộ**, **return một object** giúp Spring publish một event tiếp, **return Collection/array** giúp publish từng phần tử, còn **null/void** dừng chuỗi tự động. **@Async listener không hỗ trợ publication bằng return value**. Dùng cơ chế này cho các event chain nhỏ, dễ kiểm thử; đừng nhầm nó với transaction orchestration, replay hoặc durable messaging.

### Tài liệu chính thức

- Spring Framework 6.2 — *Annotation-based Event Listeners / Additional Capabilities of the ApplicationContext*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2.9 Javadoc — *EventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework 6.2.9 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2.9 Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html

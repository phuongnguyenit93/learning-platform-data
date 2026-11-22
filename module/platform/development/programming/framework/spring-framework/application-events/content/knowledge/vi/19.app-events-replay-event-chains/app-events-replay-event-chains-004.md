# Chuyển tiếp event bằng collection trong Spring Framework Application Events

## 1. Bài toán: một event dẫn đến nhiều event tiếp theo

Trong một ứng dụng Spring, một sự kiện nghiệp vụ có thể mở đầu cho nhiều hành động độc lập. Chẳng hạn, sau khi đơn hàng được tiếp nhận, ứng dụng muốn tạo hai yêu cầu: thông báo qua email và cập nhật bảng điều khiển. Ta có thể gọi trực tiếp `ApplicationEventPublisher.publishEvent(...)` nhiều lần; tuy nhiên, Spring Framework còn hỗ trợ cách ngắn gọn hơn: **trả về `Collection` hoặc mảng từ một phương thức `@EventListener` đồng bộ**.

~~~java
@EventListener
public List<NotificationRequested> onOrderAccepted(OrderAccepted event) {
    return List.of(
        new NotificationRequested(event.orderId(), "EMAIL"),
        new NotificationRequested(event.orderId(), "DASHBOARD")
    );
}
~~~

Spring xử lý từng phần tử của danh sách trả về thành **một sự kiện ứng dụng mới**. Listener nào quan tâm đến `NotificationRequested` có thể nhận những sự kiện mới này và tiếp tục xử lý. Đây là một cơ chế **chuyển tiếp/fan-out event từ kết quả của listener**, không phải API biến một danh sách thành một lô xử lý bền vững.

Các ý cần nắm:

1. `@EventListener` xác định phương thức được gọi khi một loại event đến.
2. Giá trị trả về không phải `void` có thể được Spring **phát lại làm event mới**.
3. Nếu giá trị trả về là một `Collection` hoặc mảng, Spring phát **từng phần tử** như event riêng.
4. Cơ chế này áp dụng cho listener **đồng bộ**; không thể dùng `@Async` rồi mong các giá trị trả về được tự động phát.
5. Mỗi event con có thể kích hoạt listener khác, tạo thành chuỗi nhiều tầng. Cần kiểm soát vòng lặp, exception, transaction và độ phức tạp của chuỗi.

> Đối tượng `Collection` trong **giá trị trả về** của `@EventListener` được Spring xử lý đặc biệt. Điều đó khác với việc gọi `publisher.publishEvent(list)`: lời gọi trực tiếp ấy phát **chính object list như một payload event**, không mặc định bóc từng phần tử để phát riêng.

## 2. Phân biệt event đầu vào và event đầu ra của listener

Một phương thức listener có thể nhận một kiểu event và trả về kiểu khác:

~~~java
@EventListener
public OrderIndexed onOrderPlaced(OrderPlaced input) {
    // Thực hiện logic xử lý OrderPlaced.
    return new OrderIndexed(input.orderId());
}
~~~

Trong đoạn minh họa này:

- `OrderPlaced` là **event đầu vào**, Spring dùng tham số phương thức để xác định listener có phù hợp với event vừa phát hay không.
- `OrderIndexed` là **event đầu ra**, Spring phát sau khi phương thức hoàn thành và trả về object.
- Nếu phương thức trả về `null` thì không có event tiếp theo từ giá trị trả về ấy.
- `OrderIndexed` có thể là một `ApplicationEvent` subclass hoặc một payload POJO/record bình thường, vì `ApplicationEventPublisher` hỗ trợ cả hai cách.

Khi một bước phải tạo nhiều kết quả độc lập, dùng `Collection`:

~~~java
@EventListener
public List<FollowUpRequested> onOrderPlaced(OrderPlaced input) {
    return List.of(
        new FollowUpRequested(input.orderId(), "EMAIL"),
        new FollowUpRequested(input.orderId(), "AUDIT"),
        new FollowUpRequested(input.orderId(), "SEARCH_INDEX")
    );
}
~~~

Danh sách chứa ba phần tử, vì vậy mỗi phần tử trở thành một event `FollowUpRequested` riêng. Nó không phải một event `List<FollowUpRequested>` duy nhất. Nếu không có hành động tiếp theo, có thể trả về `List.of()`, tương ứng không phát event nào từ kết quả phương thức.

**Giá trị trả về không được truyền về cho người gọi `publishEvent(...)` như một kết quả của API**; `publishEvent` vẫn là API phát sự kiện. Cơ chế chuyển tiếp diễn ra trong hệ thống phân phối event, không phải theo kiểu publisher nhận `List` trả về.

## 3. Luồng thực thi khi trả về Collection

Với `SimpleApplicationEventMulticaster` mặc định, listener đồng bộ thường chạy trên luồng đang phát event. Nếu chỉ có các listener liên quan trong ví dụ, dòng thực thi có thể được hình dung:

~~~text
Publisher
    |
    +-- publishEvent(OrderAccepted("ORD-211"))
            |
            v
        @EventListener onOrderAccepted(...)
            |
            +-- return List.of(
            |      NotificationRequested("ORD-211", "EMAIL"),
            |      NotificationRequested("ORD-211", "DASHBOARD")
            |   )
            |
            v
        Spring xử lý kết quả trả về
            |
            +-- publishEvent(NotificationRequested(..., "EMAIL"))
            |       |
            |       +-- listener NotificationRequested xử lý EMAIL
            |
            +-- publishEvent(NotificationRequested(..., "DASHBOARD"))
                    |
                    +-- listener NotificationRequested xử lý DASHBOARD
            |
            v
        onOrderAccepted đã dẫn tới các event con
            |
            v
Publisher tiếp tục sau publishEvent ban đầu
~~~

Một số điểm tinh tế:

- Spring thực hiện chuyển tiếp **sau khi phương thức listener trả về**; không tự phát từng phần tử vào lúc bạn mới thêm vào `ArrayList`.
- Khi dùng `List`, collection có thứ tự phần tử; adapter có thể phát các phần tử theo thứ tự duyệt list. Tuy nhiên, **thứ tự hoàn thành toàn hệ thống không được bảo đảm** nếu có executor, listener bất đồng bộ, nhiều context hoặc broker ở các bước kế tiếp.
- Mỗi event con là một lần publication riêng. Listener sự kiện con có thể tiếp tục trả về event khác, tạo **chuỗi nhiều tầng**.
- Nếu một listener sự kiện con ném exception trong mô hình đồng bộ, exception có thể làm gián đoạn luồng chuyển tiếp và ngăn các phần tử phía sau được publish. Các thay đổi/side effect đã thực hiện trước đó không tự được đảo ngược.

Đối với quy trình nghiệp vụ bắt buộc mọi bước thành công hoặc thất bại cùng nhau, không nên thay thế workflow/transaction có kiểm soát bằng một chuỗi event không có cơ chế rollback, retry hoặc idempotency tương ứng.

## 4. API cốt lõi của Spring

Phương thức `@EventListener` được đánh dấu bằng annotation:

~~~java
import org.springframework.context.event.EventListener;
~~~

Theo contract của `@EventListener` trong Spring Framework:

- Phương thức có thể trả về object thay vì `void`. Object được xem là event mới.
- Nếu **giá trị trả về** là một mảng hoặc một `Collection`, các phần tử của nó được gửi thành event riêng lẻ.
- Annotation được xử lý bởi hạ tầng `EventListenerMethodProcessor` khi ứng dụng có cấu hình annotation phù hợp.
- Sự kiện đầu vào có thể là `ApplicationEvent` hoặc payload Java thông thường.
- Spring có thể áp dụng `@Order` để điều chỉnh thứ tự gọi các listener cho một event.
- Với `@Async` trên listener, việc phát event mới bằng giá trị trả về **không được hỗ trợ**.

Đây là một **cơ chế có sẵn** của Spring Framework, không cần tự viết lớp bọc để Spring duyệt từng phần tử, miễn là listener được Spring quản lý và lời gọi event chạy qua hạ tầng của context.

Các dạng trả về phổ biến:

| Kiểu trả về | Spring hiểu thế nào? | Phù hợp khi |
|---|---|---|
| `void` | Không sinh event kế tiếp bằng return | Chỉ thực hiện side effect hoặc gọi publisher chủ động |
| `SomeEvent` | Phát một event mới | Một bước có đúng một kết quả |
| `List<SomeEvent>` | Phát từng phần tử thành event riêng | Có fan-out theo thứ tự duyệt rõ |
| `Set<SomeEvent>` | Phát từng phần tử thành event riêng | Không yêu cầu thứ tự hoặc có comparator phù hợp |
| `SomeEvent[]` | Phát từng phần tử thành event riêng | Cần mảng cố định |
| `Collection<?>` | Phát từng phần tử, có thể khác loại | Một bước sinh nhiều kiểu event |
| `null` hoặc collection rỗng | Không phát event mới từ kết quả | Điều kiện không sinh bước tiếp |
| `Mono<SomeEvent>` / `Stream<SomeEvent>` | Không phải Collection/mảng theo quy tắc trên | **Không dùng** nếu mục tiêu là auto-unpack thành các event |

Đừng suy đoán mọi loại wrapper đều được tự động duyệt. Tài liệu Spring nêu rõ **array** và **collection**; một `Stream` hoặc `Publisher` không nên được dùng để thay thế nếu bạn kỳ vọng một sự kiện cho mỗi phần tử. Với các pipeline bất đồng bộ/reactive, cần cơ chế phát event chủ động và ranh giới subscription/transaction phù hợp.

## 5. Ví dụ hoàn chỉnh Java 17 + Maven: chuỗi event hai tầng

Ví dụ dùng **Spring Framework 6.2.8**, Java 17+, Maven; không cần Spring Boot hoặc cơ sở dữ liệu. Một event đầu vào `OrderAccepted` được chuyển thành **hai** event `NotificationRequested` bằng `List.of(...)`. Mỗi notification được xử lý rồi trả về `NotificationFinished`. Như vậy, ta quan sát được cả **collection fan-out** và **event chaining**.

Cấu trúc thư mục:

~~~text
event-collection-demo/
├── pom.xml
└── src/main/java/demo/CollectionForwardingDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-collection-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/CollectionForwardingDemo.java

~~~java
package demo;

import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class CollectionForwardingDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new OrderAccepted("ORD-211"));
            System.out.println("publisher returned");
        }
    }

    public record OrderAccepted(String orderId) {
    }

    public record NotificationRequested(String orderId, String channel) {
    }

    public record NotificationFinished(String orderId, String channel) {
    }

    public static final class OrderEventRouter {

        @EventListener
        public List<NotificationRequested> route(OrderAccepted event) {
            System.out.println("route: " + event.orderId());
            return List.of(
                new NotificationRequested(event.orderId(), "EMAIL"),
                new NotificationRequested(event.orderId(), "DASHBOARD")
            );
        }
    }

    public static final class NotificationProcessor {

        @EventListener
        public NotificationFinished process(NotificationRequested event) {
            System.out.println("process: " + event.channel());
            return new NotificationFinished(event.orderId(), event.channel());
        }
    }

    public static final class CompletionLogger {

        @EventListener
        public void onCompleted(NotificationFinished event) {
            System.out.println("finished: " + event.channel());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public OrderEventRouter orderEventRouter() {
            return new OrderEventRouter();
        }

        @Bean
        public NotificationProcessor notificationProcessor() {
            return new NotificationProcessor();
        }

        @Bean
        public CompletionLogger completionLogger() {
            return new CompletionLogger();
        }
    }
}
~~~

Chạy từ thư mục `event-collection-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CollectionForwardingDemo
~~~

Các dòng do chương trình in trong mô hình mặc định đồng bộ, khi chạy thành công:

~~~text
route: ORD-211
process: EMAIL
finished: EMAIL
process: DASHBOARD
finished: DASHBOARD
publisher returned
~~~

### Phân tích kết quả

1. `AnnotationConfigApplicationContext` đăng ký ba bean listener và bộ xử lý `@EventListener`.
2. `context.publishEvent(new OrderAccepted("ORD-211"))` đưa payload ban đầu vào hệ thống event.
3. `OrderEventRouter.route` nhận `OrderAccepted`, in dòng `route`, trả về `List<NotificationRequested>` có hai phần tử.
4. Spring phát `NotificationRequested("ORD-211", "EMAIL")`; `NotificationProcessor.process` xử lý rồi trả `NotificationFinished`; `CompletionLogger` nhận event hoàn tất. Vì dispatch đồng bộ và lồng nhau, cặp `process/finished` đầu hoàn thành trước khi phần tử thứ hai được phát.
5. Spring chuyển tiếp phần tử `DASHBOARD` và chuỗi tương ứng hoàn tất.
6. Sau khi các listener đồng bộ và các publication lồng nhau kết thúc, `publishEvent` đầu tiên mới trả về; chương trình in `publisher returned`.

**Vì sao không có vòng lặp?** Ba loại event có vai trò khác nhau:

~~~text
OrderAccepted
  -> List<NotificationRequested>
      -> NotificationFinished
          -> void
~~~

Không có listener nào trả lại `OrderAccepted` hoặc `NotificationRequested` sau khi xử lý `NotificationFinished`, nên chuỗi kết thúc tự nhiên.

**Đặc điểm cần nhớ:** thứ tự stdout trong ví dụ đến từ một context, danh sách có thứ tự và listener đồng bộ. Không áp thứ tự này cho hệ thống dùng `@Async`, executor của multicaster, listener nhiều node hoặc message broker.

## 6. Trả về mảng thay vì Collection

Spring cũng hỗ trợ giá trị trả về kiểu array:

~~~java
@EventListener
public NotificationRequested[] onOrderAccepted(OrderAccepted event) {
    return new NotificationRequested[] {
        new NotificationRequested(event.orderId(), "EMAIL"),
        new NotificationRequested(event.orderId(), "DASHBOARD")
    };
}
~~~

Đây là **đoạn thay thế** phương thức `route` ở ví dụ trên, không được giữ cả hai phương thức cùng lắng nghe `OrderAccepted` nếu chỉ muốn sinh đúng hai event. Spring xử lý mỗi phần tử mảng thành một event riêng.

So với `List.of(...)`, mảng:

- Có độ dài cố định nhưng phần tử có thể bị gán lại nếu giữ tham chiếu.
- Cần quan tâm đến kiểu phần tử và việc trả về `null` thay vì mảng rỗng.
- Thích hợp khi API hiện tại đã trả mảng; đối với logic business thông thường, `List` thường đọc dễ hơn.

Đối với event collection được dùng làm một kết quả, `List.of(...)` giúp giữ thứ tự và tránh việc bổ sung/xóa phần tử sau khi tạo; chú ý bản thân payload chứa tham chiếu mutable vẫn có thể bị sửa.

## 7. Collection chứa nhiều loại event khác nhau

Một nghiệp vụ có thể sinh các sự kiện con khác loại:

~~~java
public record AuditRequested(String orderId) {}
public record IndexRequested(String orderId) {}

@EventListener
public Collection<?> onOrderAccepted(OrderAccepted input) {
    return List.of(
        new AuditRequested(input.orderId()),
        new IndexRequested(input.orderId())
    );
}
~~~

Đây là **mã minh họa cần đặt trong một Spring bean**; cần import `java.util.Collection` và `java.util.List`, đồng thời có kiểu `OrderAccepted`. Spring phát từng phần tử theo runtime type; listener nhận `AuditRequested` và listener nhận `IndexRequested` sẽ được chọn theo loại event tương ứng.

Tuy vậy, collection lẫn nhiều kiểu có thể khiến contract của phương thức khó hiểu, dễ tạo side effect không chủ ý và khó kiểm thử schema:

- Nếu mọi phần tử đều là một hành động cùng loại khác nhau ở tham số, dùng `List<NotificationRequested>` sẽ thể hiện intent rõ hơn.
- Nếu có nhiều bước khác trách nhiệm, cân nhắc method/phần tử event riêng và đưa tên event mô tả trạng thái đã xảy ra hay công việc được yêu cầu.
- Không trả về collection chứa một entity JPA, một string và một service object rồi trông chờ Spring “biết đâu là event”: Spring coi chúng là những payload object để publish, có thể kích hoạt listener không ngờ tới.

Hãy đặt tên kiểu event chính xác, ví dụ `EmailRequested`, `SearchIndexRequested`, `OrderValidated`, thay vì một `Object` mơ hồ.

## 8. Khác biệt quan trọng: return Collection và publishEvent(Collection)

Xem hai đoạn sau:

~~~java
// Trường hợp A: mỗi phần tử được Spring xử lý là một event mới.
@EventListener
public List<NotificationRequested> fanOut(OrderAccepted event) {
    return List.of(
        new NotificationRequested(event.orderId(), "EMAIL"),
        new NotificationRequested(event.orderId(), "DASHBOARD")
    );
}
~~~

và:

~~~java
// Trường hợp B: phát CHÍNH LIST như một payload object.
List<NotificationRequested> batch = List.of(
    new NotificationRequested("ORD-211", "EMAIL"),
    new NotificationRequested("ORD-211", "DASHBOARD")
);

publisher.publishEvent(batch);
~~~

Với **trường hợp B**, `ApplicationEventPublisher.publishEvent(Object)` nhận một object mà ở đây là `List`. Spring không áp quy tắc đặc biệt của **return value của `@EventListener`** lên chính lời gọi publish này. Listener muốn nhận cả batch cần có một event contract biểu diễn batch, không phải giả định các `NotificationRequested` sẽ được bóc và chuyển tiếp.

Thiết kế rõ ràng hơn cho batch như một event duy nhất:

~~~java
public record NotificationBatchRequested(
    String orderId,
    List<NotificationRequested> notifications
) {
    public NotificationBatchRequested {
        notifications = List.copyOf(notifications);
    }
}

// Một event có payload chứa danh sách:
publisher.publishEvent(new NotificationBatchRequested("ORD-211", batch));
~~~

Đây là mã minh họa (cần các import và kiểu từ ví dụ) và thể hiện một hợp đồng khác:

- **Fan-out:** nhiều event độc lập, mỗi event được listener chọn theo kiểu phần tử.
- **Batch event:** một event duy nhất chứa nhiều item, listener phải tự quyết định xử lý item nào/bao nhiêu.

Với batch event, `List.copyOf` tạo bản sao danh sách không thể thay đổi cấu trúc; nó không biến các phần tử mutable thành immutable.

## 9. Collection rỗng, null và phần tử không hợp lệ

Các nhánh nghiệp vụ thường không phải lúc nào cũng sinh sự kiện mới. Có thể biểu diễn kết quả có điều kiện:

~~~java
@EventListener
public List<NotificationRequested> onOrderAccepted(OrderAccepted event) {
    if (event.orderId().startsWith("TEST-")) {
        return List.of();
    }
    return List.of(new NotificationRequested(event.orderId(), "EMAIL"));
}
~~~

Khi trả về danh sách rỗng, không có event tiếp theo được tạo từ return value.

Nếu phương thức không có kết quả:

~~~java
@EventListener
public List<NotificationRequested> onOrderAccepted(OrderAccepted event) {
    if (event.orderId().isBlank()) {
        return null;
    }
    return List.of(new NotificationRequested(event.orderId(), "EMAIL"));
}
~~~

Spring không publish event tiếp theo khi **toàn bộ kết quả trả về là `null`**. Tuy nhiên, với contract kiểu `Collection`, danh sách rỗng thường thể hiện ý định rõ ràng hơn và dễ kiểm thử hơn so với trả `null`.

Tránh dùng collection có **phần tử `null`**:

~~~java
List<NotificationRequested> wrong = new ArrayList<>();
wrong.add(new NotificationRequested("ORD-211", "EMAIL"));
wrong.add(null); // Không tạo một event null có ý nghĩa.
~~~

Trong mã này, `ArrayList` cần import `java.util.ArrayList`. Đừng giả định null element sẽ tự được bỏ qua. Nếu có phần tử null, việc publish có thể thất bại hoặc tạo kết quả không mong muốn. `List.of(...)` tự từ chối null, hỗ trợ phát hiện lỗi sớm.

Ngoài ra, đừng trả lại collection mutable rồi cho thread khác sửa trong lúc Spring đang duyệt. Đối với kết quả có thể được sinh động, hãy chốt snapshot:

~~~java
List<NotificationRequested> pending = createRequests(event);
return List.copyOf(pending);
~~~

Đây là mẫu tích hợp: `createRequests` là hàm của ứng dụng. Chỉ copy sau khi đã dựng xong nội dung, và bảo đảm phần tử event là immutable nếu cần.

## 10. Chuỗi event nhiều tầng và nguy cơ vòng lặp

Spring không tự giới hạn một chuỗi event do các listener trả về. Nếu event A tạo event B, event B lại tạo event A, hệ thống có thể quay vòng:

~~~java
@EventListener
public EventB onA(EventA event) {
    return new EventB(event.id());
}

@EventListener
public EventA onB(EventB event) {
    return new EventA(event.id());
}
~~~

Đây là **ví dụ sai về thiết kế**; `EventA`/`EventB` là các kiểu minh họa. Trong dispatch đồng bộ, một vòng lặp như vậy có thể gây đệ quy rất sâu và `StackOverflowError` hoặc làm ứng dụng treo; trong dispatch async, nó có thể gây bão sự kiện/tác vụ.

Một số nguyên tắc tránh vòng lặp:

1. Đặt tên event theo **trạng thái đã xảy ra** hoặc **hành động được yêu cầu**, tránh dùng một kiểu event cho mọi bước.
2. Không cho một listener liên tục phát lại cùng event type nếu không có điều kiện kết thúc rõ ràng.
3. Nếu có workflow nhiều bước, kiểm soát state machine hoặc orchestrator và kiểm thử các transition hợp lệ.
4. Nếu phải retry, tách retry policy khỏi event chaining tùy tiện; thêm attempt count, idempotency key và giới hạn số lần.
5. Khi event bị lặp do nhận lại message, dùng `eventId`/`correlationId`/`aggregateId` theo đúng nghĩa của chúng, không coi chúng là một loại ID.
6. Giới hạn số event con được sinh từ một đầu vào nếu fan-out có thể lớn bất thường.

Ví dụ một bước có tối đa hai action là an toàn hơn việc trả toàn bộ vài chục nghìn entity dưới dạng events mà không có backpressure.

## 11. Thứ tự xử lý, @Order và quan hệ phụ thuộc

Có hai kiểu thứ tự khác nhau:

- **Thứ tự các phần tử của Collection:** `List` được duyệt theo index; `Set` có thể không duy trì thứ tự chèn trừ khi dùng loại có contract tương ứng.
- **Thứ tự các listener nhận cùng một event:** Spring có thể sắp bằng `@Order`/`Ordered` cho listener đồng bộ.

~~~java
@Order(10)
@EventListener
public void audit(NotificationRequested event) {
    // Một listener nhận NotificationRequested.
}

@Order(20)
@EventListener
public void metrics(NotificationRequested event) {
    // Listener khác nhận cùng sự kiện.
}
~~~

Đây là mã minh họa; cần import `org.springframework.core.annotation.Order` và đăng ký phương thức trong bean. Hai phương thức là hai subscriber độc lập; thứ tự được yêu cầu không biểu diễn một giao dịch hoặc workflow nhiều bước.

**Quan trọng:** `@Order` không hứa hẹn thứ tự *hoàn tất* với listener bất đồng bộ. Ngay cả khi một listener được dispatch trước, một worker khác vẫn có thể hoàn thành trước.

Nếu B phải chạy **chỉ sau khi A thành công**, nên biểu diễn B bằng event tiếp theo phát **sau khi A đã hoàn tất** (hoặc điều phối trong một service có thứ tự/transaction). Đừng tạo hai phần tử của cùng danh sách rồi giả định phần tử thứ hai chỉ được xử lý khi mọi tác dụng phụ của phần tử đầu đã thành công trong bất kỳ cấu hình thread nào.

### Collection fan-out không phải cơ chế song song

Trả về hai event trong `List` không tự có nghĩa chúng chạy ở hai thread. Với multicaster mặc định, phần lớn đường xử lý là **đồng bộ**. Khi fan-out nhằm tăng throughput, cần thiết kế async executor, queue hoặc broker riêng; phải xử lý lỗi, trật tự và idempotency ở ranh giới mới.

## 12. @Async: không phát event mới bằng giá trị return

Đây là một giới hạn được tài liệu Spring nêu rõ. Không viết:

~~~java
@Async("eventExecutor")
@EventListener
public List<NotificationRequested> onOrderAccepted(OrderAccepted event) {
    return List.of(
        new NotificationRequested(event.orderId(), "EMAIL"),
        new NotificationRequested(event.orderId(), "DASHBOARD")
    );
}
~~~

Đoạn trên là **phản ví dụ**: đối với listener bất đồng bộ, Spring **không hỗ trợ** tự phát event tiếp theo bằng return value. Hơn nữa, các phương thức `@Async` có contract kiểu trả về hạn chế (thường là `void` hoặc một kiểu future được hỗ trợ), nên trả trực tiếp `List` còn có thể vi phạm quy tắc của cơ chế async.

Cách đúng khi bắt buộc xử lý bất đồng bộ: inject `ApplicationEventPublisher` và **gọi publishEvent chủ động** trong phần thân worker.

~~~java
@Component
public class AsyncOrderRouter {

    private final ApplicationEventPublisher publisher;

    public AsyncOrderRouter(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Async("eventExecutor")
    @EventListener
    public void onOrderAccepted(OrderAccepted event) {
        List<NotificationRequested> followUps = List.of(
            new NotificationRequested(event.orderId(), "EMAIL"),
            new NotificationRequested(event.orderId(), "DASHBOARD")
        );

        for (NotificationRequested followUp : followUps) {
            publisher.publishEvent(followUp);
        }
    }
}
~~~

Đây là **mã tích hợp**, không phải file demo đầy đủ: cần `@EnableAsync`, bean executor `eventExecutor`, Spring-managed `AsyncOrderRouter` và import `@Component`, `ApplicationEventPublisher`, `@Async`, `@EventListener` cùng các loại payload. Với Spring proxy-based async, self-invocation có thể khiến `@Async` không hoạt động.

Không có bảo đảm rằng callback async hoàn tất khi `publisher.publishEvent(OrderAccepted)` của luồng gốc trả về. Exception trong worker cũng không tự đi ngược về publisher; cần `AsyncUncaughtExceptionHandler`, logging/metrics và cơ chế retry phù hợp nếu quan trọng.

Nếu hệ thống dùng custom `ApplicationEventMulticaster` với executor, ngay cả listener **không có `@Async`** cũng có thể được dispatch trên thread khác khi listener hỗ trợ async. Khi đó các giả định về hoàn tất và thứ tự đầu ra ở ví dụ đồng bộ không còn áp dụng.

## 13. Transaction, AFTER_COMMIT và event được tạo tiếp

Collection fan-out **không mở hoặc commit giao dịch**. Trong Spring Application Events mặc định, listener đồng bộ thường được gọi trong thread của publisher; nếu publisher đang ở transaction, các listener có thể xử lý trong transaction đó. Nhưng một event con phát ra là **một publication mới**, không tự mang theo transaction riêng hoặc bảo đảm dữ liệu đã commit.

Giả sử:

~~~java
@Transactional
public void createOrder(long orderId) {
    orderRepository.insert(orderId);
    publisher.publishEvent(new OrderAccepted("ORD-" + orderId));
    // Transaction gốc thường chưa commit tại thời điểm publish.
}
~~~

Nếu `OrderEventRouter.route` trả về các yêu cầu gửi thông báo trước commit, listener cho event con có thể gửi email **trước khi transaction DB commit**. Nếu transaction rollback sau đó, email không tự được “rollback”.

### Khi cần fan-out sau commit

Một phương án là đăng ký listener theo phase:

~~~java
@Component
public class AfterCommitRouter {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public List<NotificationRequested> onOrderAccepted(OrderAccepted event) {
        return List.of(
            new NotificationRequested(event.orderId(), "EMAIL"),
            new NotificationRequested(event.orderId(), "DASHBOARD")
        );
    }
}
~~~

Đây là **đoạn tích hợp** cần Spring transaction thực tế, các imports và payload classes. Nó nhằm minh họa thời điểm đăng ký theo phase. **Không được mặc định các listener event con đã nhận một transaction mới**: `AFTER_COMMIT` chạy khi transaction gốc đã commit nhưng resource có thể vẫn còn gắn với thread trong quá trình completion/cleanup. Việc trả về Collection không làm những event con bền vững, và cũng không cung cấp một lần commit thứ hai cho các thao tác ghi tiếp.

Nếu cần đọc/ghi database khi xử lý event con ở thời điểm này, tổ chức logic trong bean khác với một transaction phù hợp, thường là `REQUIRES_NEW` nếu phải có ranh giới độc lập, gọi qua Spring proxy. Nếu cần bảo đảm sự kiện không mất sau crash giữa commit và publication, hãy cân nhắc **transactional outbox** thay vì chỉ dựa vào một callback in-process.

### Chú ý khi không có transaction

`@TransactionalEventListener` mặc định không chạy nếu event được phát mà không có transaction phù hợp (trừ khi khai báo `fallbackExecution=true`). Vì vậy đoạn ví dụ thuần `AnnotationConfigApplicationContext` ở mục 5 dùng `@EventListener` thông thường: nó không cần transaction và có thể chạy độc lập.

## 14. Exception giữa một danh sách event: điều gì xảy ra?

Giả sử listener ban đầu trả về:

~~~java
return List.of(
    new NotificationRequested("ORD-211", "EMAIL"),
    new NotificationRequested("ORD-211", "DASHBOARD")
);
~~~

Nếu subscriber xử lý `EMAIL` ném exception trong dispatch đồng bộ mặc định, luồng phát `DASHBOARD` có thể **không được thực hiện** vì exception thoát ra trước khi Spring duyệt đến phần tử thứ hai. Điều đó khác với một batch transaction toàn phần:

~~~text
Event cha được nhận
    |
    +-- event EMAIL
    |      +-- xử lý một phần
    |      +-- exception!
    |
    +-- event DASHBOARD   (có thể chưa được publish)
~~~

Hãy phân biệt:

- Lỗi xảy ra trong **phương thức tạo Collection**: nếu phương thức ném exception trước khi trả về, collection không được Spring phát từ lần gọi đó.
- Lỗi ở **listener của phần tử đầu**: phần tử đầu có thể đã gây side effect; phần tử sau có thể chưa được phát.
- Lỗi trong **listener async**: có thể chỉ xuất hiện ở worker, không dừng ngay vòng publish ở luồng khác.
- Lỗi bị **ErrorHandler** của multicaster bắt/nuốt theo cấu hình: có thể làm hành vi khác với exception mặc định.

Khi nghiệp vụ yêu cầu tất cả yêu cầu con phải được xử lý hoặc có thể retry, nên ghi lại chúng thành các record bền vững (outbox/job queue) hoặc dùng workflow explicit với trạng thái từng bước.

**Không dùng catch-all rỗng** chỉ để “phát được hết collection”. Ít nhất phải có log, chỉ số thất bại, correlation ID và khả năng xác định phần tử nào xử lý thành công.

## 15. eventId, aggregateId và chống phát lại sai

Một danh sách các event được tạo từ cùng event cha nên giữ rõ:

- **eventId**: định danh một occurrence event duy nhất; mỗi event con cần ID riêng nếu cần dedupe/replay.
- **aggregateId/orderId**: đối tượng nghiệp vụ mà các event cùng tham chiếu.
- **correlationId**: mã theo dõi một chuỗi nghiệp vụ gồm nhiều event.
- **causationId**: ID event hoặc command gây ra event mới.
- **version/sequence**: khi consumer phải xử lý theo thứ tự cập nhật của cùng aggregate.

Ví dụ schema payload minh họa:

~~~java
public record FollowUpRequested(
    UUID eventId,
    UUID orderId,
    UUID correlationId,
    UUID causationId,
    String action
) {}
~~~

Với hai hành động `EMAIL` và `DASHBOARD` tạo ra từ cùng event cha:

- `eventId` của chúng nên **khác nhau**, vì đó là hai occurrence riêng.
- `orderId` có thể giống nhau, vì đều thuộc cùng đơn.
- `correlationId` có thể giống nhau để nhóm các bước.
- `causationId` có thể bằng `eventId` của event cha để chỉ quan hệ nhân quả.

Đây là hướng thiết kế **tự chọn** của ứng dụng, không phải các field mà Spring tự điền vào event. Chỉ có một method trả `List` không tự sinh IDs, chống trùng, transaction hay truy vết.

Nếu listener nhận lại cùng event từ broker, việc dedupe theo `orderId` có thể bỏ nhầm event con hợp lệ. Dedupe theo `eventId` hoặc key thực sự của nghiệp vụ và giữ idempotency cho side effect.

## 16. Collection hay batch, orchestrator hay outbox?

Không có giải pháp áp dụng cho mọi luồng nghiệp vụ:

| Mục tiêu | Lựa chọn hợp lý | Vì sao |
|---|---|---|
| Một event sinh vài event in-process đồng bộ | Trả `List<Event>` từ `@EventListener` | Ngắn gọn, không cần gọi publisher nhiều lần |
| Một event sinh một event kế tiếp | Trả một object event | Contract trực tiếp, dễ hiểu |
| Cần nhiều loại sự kiện rời nhau nhưng logic phức tạp | Inject `ApplicationEventPublisher` và phát có chủ đích | Dễ kiểm soát điều kiện, báo lỗi và thời điểm |
| Truyền cả lô dữ liệu như **một** nghiệp vụ | Event record chứa `List<Item>` | Consumer nhìn thấy một batch và tự xử lý |
| Các bước phụ thuộc chặt chẽ với rollback chung | Service/orchestrator với transaction rõ | Event fan-out không thay thế transaction |
| Việc độc lập, có thể chậm hoặc nhiều tải | Async executor / queue với chính sách lỗi | Tách tài nguyên và bảo vệ thread publisher |
| Phải xử lý lại sau crash hoặc restart | Transactional outbox + broker/worker | In-process Application Events không phải kho bền vững |
| Muốn bảo toàn thứ tự, chống trùng liên node | Version/sequence, partitioning và idempotency | `List` không bảo đảm ordering end-to-end |

### Transactional outbox khi cần bền vững

Một transaction cập nhật đơn hàng và ghi các yêu cầu con như những outbox records:

~~~text
BEGIN TRANSACTION
  UPDATE orders ...
  INSERT INTO outbox(event_id=E1, type='EmailRequested', payload=...)
  INSERT INTO outbox(event_id=E2, type='DashboardRequested', payload=...)
COMMIT
    |
    v
Worker đọc outbox, gửi từng message và đánh dấu trạng thái
    |
    v
Consumer xử lý idempotent theo eventId
~~~

Khi transaction rollback, cả thay đổi đơn hàng lẫn outbox cùng rollback nếu nằm trong một local transaction. Khi worker crash sau gửi nhưng trước khi đánh dấu, message có thể bị gửi lại; do đó consumer vẫn phải chịu được duplicate. Cơ chế này giải quyết yêu cầu khác với collection return trong `@EventListener`.

## 17. Kiểm thử cơ chế chuyển tiếp Collection

Một test hiệu quả nên xác nhận **đúng loại và đúng số event được phát**, không chỉ xem log.

### Trường hợp 1 — Collection có hai phần tử

Với demo `CollectionForwardingDemo`, kết quả mong đợi: đúng hai lần xử lý `NotificationRequested` (EMAIL, DASHBOARD) và đúng hai lần xử lý `NotificationFinished`. Vì mặc định đồng bộ, có thể assert ngay sau `context.publishEvent(...)`.

### Trường hợp 2 — Collection rỗng

Thay router để trả `List.of()`. Không event con nào được xử lý. Kiểm tra cả số lần listener nhận `OrderAccepted`, tránh nhầm “không có event con” thành “không có event cha”.

### Trường hợp 3 — Array

Thay `List<NotificationRequested>` bằng `NotificationRequested[]`. Xác minh mỗi phần tử mảng được xử lý riêng.

### Trường hợp 4 — Return một event đơn

Thay router để trả `NotificationRequested`. Khi đó chỉ có một event mới. Không thêm collection wrapper không cần thiết.

### Trường hợp 5 — Vòng lặp bất thường

Cấu hình thử một chuỗi có điều kiện kết thúc rõ, ví dụ giữ `hopsRemaining` rồi giảm mỗi lần; test giới hạn số hops. **Không tạo vòng A → B → A vô hạn trong test** vì có thể làm cả suite treo hoặc tràn stack.

### Trường hợp 6 — Exception ở phần tử đầu

Cho subscriber của EMAIL ném lỗi có chủ đích và đếm phần tử DASHBOARD. Xác nhận hành vi của multicaster/`ErrorHandler` mà ứng dụng cấu hình; đừng viết test dựa trên giả định handler luôn được gọi hết mọi lần.

### Trường hợp 7 — Async

Nếu chuyển sang `@Async`, test nên dùng completion signal như `CountDownLatch` hoặc await condition có timeout. Không assert ngay sau `publishEvent(...)` để suy ra toàn bộ event con đã hoàn tất.

Một đoạn test tích hợp minh họa theo nguyên tắc:

~~~java
AtomicInteger received = new AtomicInteger();

@Component
class CountingListener {
    @EventListener
    public void onNotification(NotificationRequested event) {
        received.incrementAndGet();
    }
}

// Sau khi gọi publishEvent trong context đồng bộ:
// assertEquals(2, received.get());
~~~

Đây là **mã test minh họa**: cần Spring context đăng ký `CountingListener`, import `AtomicInteger`, `Component`, `EventListener`, và JUnit nếu sử dụng `assertEquals`. Không dán đoạn này trực tiếp vào class demo mà không bổ sung cấu hình và dependency test.

### Những thuộc tính cần khẳng định trong test

1. Event cha đã đi vào đúng phương thức listener.
2. Mỗi phần tử collection là một **publication** riêng của đúng runtime event type.
3. Collection rỗng không sinh event mới.
4. Quan hệ eventId/correlationId được giữ đúng khi cần.
5. Exception/async/transaction không bị hiểu sai thành bảo đảm all-or-nothing.
6. Nếu có logic chọn phần tử, kiểm tra danh sách sau khi lọc không chứa null, duplicate ngoài ý muốn hoặc quá nhiều item.

## 18. Các sai lầm thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chỉ nhận một event kiểu `List` thay vì các item | Gọi `publisher.publishEvent(list)` trực tiếp | Để `@EventListener` **return** collection, hoặc tự lặp gọi publisher |
| Listener không nhận event con | Bean chưa đăng ký, sai event type, listener thiếu hạ tầng annotation | Kiểm tra bean, `@EventListener` và context |
| Collection return bị bỏ qua | Listener chạy với `@Async` | Dùng `void @Async` và `ApplicationEventPublisher.publishEvent` tường minh |
| Dòng log ngoài `publishEvent` xuất hiện trước event con | Cấu hình async executor hoặc custom multicaster | Không suy từ thứ tự log; dùng latch/metrics |
| Một event con lỗi làm các item sau chưa xử lý | Dispatch đồng bộ gặp exception | Xác định `ErrorHandler` và dùng workflow/outbox nếu cần |
| Infinite recursion/stack overflow | Listener phát lại event type dẫn tới chính nó | Thiết kế type transition/guard/hop limit |
| Event gửi trùng | Collection chứa duplicate hoặc upstream retry | eventId/idempotency và test số lần publish |
| Thứ tự khác mong đợi | `Set` không giữ insertion order, async, đa listener | Dùng `List` cho thứ tự duyệt, nhưng không dựa vào ordering end-to-end |
| Email gửi trước DB commit | Listener con chạy đồng bộ trong transaction gốc | Dùng pha transaction phù hợp hoặc outbox |
| Consumer đọc dữ liệu cũ/không thấy | Async chạy trước commit hoặc replica lag | Thiết kế transaction/read consistency rõ |
| Một event cần xử lý như batch nhưng bị tách | Trả `List<ItemEvent>` từ listener | Tạo `BatchRequested(List<Item>)` làm payload một event |
| Ứng dụng chậm hoặc đầy thread | Fan-out không giới hạn, side effect blocking | Giới hạn fan-out, executor/queue và backpressure |
| Không khôi phục được sau restart | In-process events không lưu bền | Outbox/job queue/broker và idempotency |

## 19. Checklist thiết kế cho production

Trước khi chọn trả về collection, trả lời:

1. **Event nào kích hoạt?** Xác định rõ lớp payload đầu vào.
2. **Mỗi phần tử là gì?** Phải là một event có ý nghĩa, không chỉ là một object dữ liệu ngẫu nhiên.
3. **Bao nhiêu event con có thể phát?** Có giới hạn fan-out để tránh bùng nổ task/memory không?
4. **Collection có thứ tự?** Nếu thứ tự cần thiết, dùng loại có contract phù hợp; vẫn đừng nhầm với thứ tự hoàn tất async.
5. **Listener đồng bộ hay bất đồng bộ?** Chỉ trông đợi return-value forwarding khi listener đồng bộ.
6. **Điều gì xảy ra nếu phần tử thứ k lỗi?** Các phần tử trước đã side effect chưa, có retry/compensation không?
7. **Có vòng lặp event không?** Phân biệt input/output event types và điều kiện kết thúc.
8. **Đang trong transaction nào?** Event con được phát trước hay sau commit, có thể truy cập resource cũ không?
9. **Có cần bền vững?** Nếu sau crash vẫn cần xử lý, thiết kế outbox hoặc queue.
10. **Có nhận duplicate không?** Dùng eventId, version, consumer idempotency.
11. **Có cần một batch atomic không?** Nếu có, đừng coi collection return là một transaction.
12. **Test đã xác nhận số lượng event?** Bao gồm collection rỗng, lỗi ở phần tử đầu, async và chain nhiều tầng.

## 20. Tổng kết

Trong Spring Framework, phương thức `@EventListener` có thể trả về **một event** để Spring phát tiếp, hoặc trả về **`Collection`/array** để Spring phát **từng phần tử thành event riêng**. Đây là cách viết gọn cho **event fan-out và event chaining đồng bộ**. Ví dụ `OrderAccepted → List<NotificationRequested> → NotificationFinished` cho thấy Spring có thể tạo chuỗi nhiều tầng mà không cần mỗi listener tự inject `ApplicationEventPublisher`.

Điểm quan trọng là **chỉ return collection từ listener mới kích hoạt quy tắc tự tách phần tử**; gọi `publishEvent(list)` trực tiếp không có ý nghĩa tương đương. Không dùng return-value forwarding trên `@Async` listener, không kỳ vọng các phần tử sẽ chạy song song hoặc đúng thứ tự hoàn tất, và không coi event chain là workflow transaction hay durable queue. Khi yêu cầu cao về lỗi, thứ tự, idempotency và độ bền, cần bổ sung orchestrator, transaction phù hợp, outbox hoặc message broker.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 Reference — ApplicationContext Events và @EventListener](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html) — non-void return, collection/array forwarding, async listeners và ordering.
- [Spring Framework Javadoc 6.2 — EventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListener.html) — contract cho giá trị trả về.
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html) — API phát event trong context.
- [Spring Framework Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html) — đồng bộ/async, task executor và error handler.
- [Spring Framework 6.2 Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html) — pha transaction và @TransactionalEventListener.

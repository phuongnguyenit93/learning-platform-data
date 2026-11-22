# Lọc event null và dữ liệu không hợp lệ

Spring application events có nhiều lớp lọc khác nhau. Spring kiểm tra event ở cửa publish, hệ thống listener lọc theo kiểu event và source, còn @EventListener(condition = "...") có thể lọc theo nội dung bằng SpEL. Những cơ chế này quyết định listener nào được gọi; chúng không thay thế việc kiểm tra dữ liệu nghiệp vụ trước khi phát event.

Cần phân biệt rõ hai trường hợp:

- **Event object là null:** Spring ApplicationContext từ chối publish ngay lập tức.
- **Event object không null nhưng payload có field null hoặc dữ liệu sai:** Spring vẫn có thể publish và chuyển event tới các listener phù hợp. Ứng dụng phải quyết định validate, từ chối hay chỉ lọc listener theo nhu cầu.

Một listener bị condition bỏ qua không có nghĩa event bị hủy. Các listener khác vẫn có thể nhận cùng event. Vì vậy, dữ liệu quyết định tính hợp lệ của nghiệp vụ phải được kiểm tra tại boundary trước khi publish.

## 1. Phân biệt null event và null trong payload

### Publish một event object null

Trong Spring Framework 6.2, AbstractApplicationContext kiểm tra tham số event trước khi tạo PayloadApplicationEvent. Nếu event là null, Spring ném IllegalArgumentException với thông báo Event must not be null.

~~~java
ApplicationEventPublisher publisher = context;

try {
    publisher.publishEvent((Object) null);
} catch (IllegalArgumentException ex) {
    System.out.println(ex.getMessage());
}
~~~

Ép kiểu sang Object giúp chọn overload publishEvent(Object) một cách rõ ràng. Việc từ chối xảy ra trước khi multicaster gọi listener, vì vậy không có listener nào nhận một event null.

Không nên dùng null như một tín hiệu nghiệp vụ, ví dụ publishEvent(null) để biểu thị đơn hàng bị hủy hoặc dữ liệu không tìm thấy. Hãy định nghĩa event cụ thể như OrderCancelled hoặc OrderNotFound.

### Publish một payload object có field null

Spring Framework 4.2 trở lên cho phép publish một object bất kỳ, không bắt buộc object đó phải kế thừa ApplicationEvent. Spring bọc object trong PayloadApplicationEvent để phân phối.

Ví dụ payload sau không null, dù các field bên trong chưa hợp lệ:

~~~java
public record LegacyOrderPayload(String orderId, Integer amount) {
}

publisher.publishEvent(new LegacyOrderPayload(null, -10));
~~~

Lời gọi publish trên hợp lệ ở tầng event infrastructure: đối tượng payload khác null. Spring không tự hiểu orderId phải có giá trị hay amount phải dương. Nếu không có validation hoặc filter, listener phù hợp vẫn có thể nhận payload đó.

PayloadApplicationEvent yêu cầu source và payload khác null. Khi ApplicationContext tự bọc một POJO, source là context và payload là object đã publish. Với event tùy chỉnh kế thừa ApplicationEvent, source truyền vào constructor cũng phải khác null vì ApplicationEvent kế thừa java.util.EventObject.

### Bảng phân biệt

| Trường hợp | Spring xử lý | Việc ứng dụng cần làm |
|---|---|---|
| publishEvent(null) | Ném IllegalArgumentException trước khi dispatch | Không dùng null làm event |
| new ApplicationEvent(null) | Constructor từ chối source null | Cung cấp source hợp lệ |
| Publish POJO khác null nhưng field null | Có thể publish bình thường | Validate hoặc lọc theo nghiệp vụ |
| Publish payload có amount âm | Không tự biết amount âm là sai | Kiểm tra invariant trước khi publish |
| Listener SpEL condition trả false | Bỏ qua method listener đó | Không coi đây là từ chối event toàn cục |

## 2. Lọc theo kiểu event

Cách lọc cơ bản nhất là khai báo kiểu event mà listener quan tâm.

~~~java
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Chỉ xử lý OrderCreatedEvent.
    }
}
~~~

Spring dùng generic E để xác định listener phù hợp. Một listener khai báo ApplicationListener<OrderCreatedEvent> không nhận các event có kiểu không tương thích. Với @EventListener, kiểu tham số của method cũng là điều kiện lọc event type.

Ví dụ:

~~~java
@Component
public class OrderListeners {

    @EventListener
    public void onCreated(OrderCreatedEvent event) {
        // Chỉ nhận OrderCreatedEvent.
    }

    @EventListener
    public void onCancelled(OrderCancelledEvent event) {
        // Chỉ nhận OrderCancelledEvent.
    }
}
~~~

Lọc theo kiểu có hiệu quả và rõ ràng vì listener chỉ nhận nhóm event mà nó xử lý. Tuy nhiên, type filtering không xác minh các field trong event. Một OrderCreatedEvent có orderId rỗng vẫn có đúng kiểu OrderCreatedEvent.

## 3. Lọc runtime bằng @EventListener condition và SpEL

Khi nhiều event có cùng kiểu nhưng listener chỉ quan tâm một số điều kiện, dùng thuộc tính condition của @EventListener.

Ví dụ chỉ xử lý đơn hàng có mã hợp lệ và số tiền dương:

~~~java
@Component
public class ValidOrderListener {

    @EventListener(
        condition = "#a0.orderId != null and " +
                    "!#a0.orderId.isBlank() and " +
                    "#a0.amount != null and #a0.amount > 0")
    public void process(LegacyOrderPayload event) {
        // Chỉ chạy khi biểu thức SpEL trả về true.
    }
}
~~~

Spring đánh giá condition trong một evaluation context riêng. Những tham chiếu hữu ích:

| Biểu thức | Ý nghĩa |
|---|---|
| #root.event hoặc event | ApplicationEvent thực tế |
| #root.args hoặc args | Mảng tham số của method |
| #root.args[0] hoặc args[0] | Tham số đầu tiên |
| #a0 | Tham số đầu tiên theo chỉ số |
| #p0 | Alias khác của tham số đầu tiên |
| #tenThamSo | Tham số theo tên nếu bytecode giữ thông tin tên |

Dùng #a0 hoặc #p0 khi muốn tránh phụ thuộc vào việc biên dịch có giữ tên tham số hay không. Nếu dùng tên như #event, cần bảo đảm tên tham số có trong bytecode, ví dụ cấu hình compiler với tùy chọn -parameters.

Condition được xem là đúng khi biểu thức trả về boolean true hoặc một trong các chuỗi true, on, yes, 1. Condition trống có nghĩa listener luôn được xử lý nếu event type phù hợp.

### Condition không phải validation

Giả sử publisher phát một payload có orderId null. Listener có condition kiểm tra orderId sẽ bị bỏ qua. Nhưng event vẫn đã được publish; một listener khác không có condition vẫn có thể nhận payload đó.

Vì vậy:

- Dùng condition khi listener chỉ quan tâm một tập con hợp lệ hoặc một nhánh nghiệp vụ cụ thể.
- Dùng validation trước publish khi dữ liệu sai phải bị từ chối ở cấp nghiệp vụ.
- Không dùng condition để che giấu lỗi dữ liệu mà mọi consumer đều phải biết.
- Nếu bỏ qua một payload có chủ đích, hãy ghi metric hoặc log phù hợp khi cần theo dõi.

### Dùng safe navigation khi thuộc tính có thể null

SpEL hỗ trợ toán tử safe navigation ?. để truy cập thuộc tính hoặc method mà không gây NullPointerException tại chính thao tác đó.

Ví dụ:

~~~java
@EventListener(
    condition = "#a0?.customer?.email != null and " +
                "#a0.customer.email.contains('@')")
public void sendEmail(OrderPayload event) {
    // Chỉ chạy khi customer và email có mặt, email chứa ký tự @.
}
~~~

Biểu thức điều kiện nên ngắn và dễ đọc. Với quy tắc nghiệp vụ phức tạp, hãy đưa logic vào một validator hoặc policy bean, sau đó gọi thành phần đó ở boundary phù hợp. Tránh viết một chuỗi SpEL dài khó kiểm thử.

## 4. Phân biệt lọc event type, source và nội dung

Spring có thể lọc listener ở nhiều tầng:

1. **Event type:** listener khai báo ApplicationListener<E> hoặc tham số method @EventListener.
2. **Generic event type:** Spring xét generic metadata khi kiểu event được xác định đủ rõ.
3. **Source type:** SmartApplicationListener hoặc GenericApplicationListener có thể kiểm tra class của event source.
4. **Runtime condition:** @EventListener(condition = "...") xét nội dung event bằng SpEL.
5. **Business validation:** service hoặc domain model xác minh dữ liệu có thỏa invariant hay không trước khi publish.

GenericApplicationListener cung cấp supportsEventType(ResolvableType) và kế thừa supportsSourceType(Class<?>) từ SmartApplicationListener. Cơ chế này hữu ích khi viết listener infrastructure cần chọn event theo kiểu generic hoặc theo source. Đây là lọc ở tầng dispatch, không phải validation dữ liệu nghiệp vụ.

Ví dụ, listener có thể chỉ quan tâm event phát ra từ một loại source nhất định. Tuy nhiên, source type chỉ cho biết object phát event thuộc class nào; nó không chứng minh payload hợp lệ hoặc người gọi có quyền thực hiện thao tác.

### Generic event và type erasure

Java xóa generic type ở runtime. Spring vẫn có thể phân tích generic metadata khi hierarchy của event giữ được kiểu cụ thể.

~~~java
public class EntityCreatedEvent<T> {

    private final T entity;

    public EntityCreatedEvent(T entity) {
        this.entity = entity;
    }

    public T getEntity() {
        return entity;
    }
}

public class PersonCreatedEvent
        extends EntityCreatedEvent<Person> {

    public PersonCreatedEvent(Person person) {
        super(person);
    }
}
~~~

Listener có thể khai báo kiểu cụ thể:

~~~java
@EventListener
public void onPersonCreated(
        EntityCreatedEvent<Person> event) {
    // Xử lý event cho Person.
}
~~~

Nếu generic type không thể suy ra từ hierarchy, có thể triển khai ResolvableTypeProvider để cung cấp ResolvableType rõ ràng. Không dựa vào cast runtime hoặc raw type để thay thế generic metadata.

## 5. Validate dữ liệu trước khi publish

Event thường mô tả một sự kiện nghiệp vụ đã xảy ra. Vì vậy, publisher nên bảo đảm dữ liệu cần thiết hợp lệ trước khi tạo và phát event.

Một số quy tắc thực tế:

- Kiểm tra object đầu vào khác null.
- Kiểm tra chuỗi bắt buộc không null, không rỗng và không chỉ chứa khoảng trắng.
- Kiểm tra số tiền, số lượng, version và timestamp theo miền giá trị hợp lệ.
- Kiểm tra collection không null, phần tử không null và không chứa phần tử trùng nếu nghiệp vụ cấm trùng.
- Kiểm tra ID và quan hệ giữa các field, ví dụ orderId phải thuộc đúng customerId.
- Tạo event bất biến để dữ liệu không bị sửa sau khi publish.

Có thể validate tại service:

~~~java
public void submit(OrderCommand command) {
    if (command == null) {
        throw new IllegalArgumentException("command is required");
    }

    if (command.orderId() == null || command.orderId().isBlank()) {
        throw new IllegalArgumentException("orderId is required");
    }

    if (command.amount() == null || command.amount() <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }

    publisher.publishEvent(
            new OrderSubmitted(command.orderId(), command.amount()));
}
~~~

Event có thể tự bảo vệ invariant trong constructor để tránh object không hợp lệ được tạo từ một đường code khác:

~~~java
public record OrderSubmitted(String orderId, int amount) {

    public OrderSubmitted {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}
~~~

Validation tại service giúp trả lỗi đúng boundary của use case. Validation trong constructor giữ event hợp lệ ở mọi nơi được tạo. Hai lớp bảo vệ này có thể cùng tồn tại khi invariant quan trọng.

### Dùng Jakarta Bean Validation

Nếu dự án dùng Jakarta Bean Validation, có thể khai báo constraint:

~~~java
public record OrderCommand(
        @NotBlank String orderId,
        @NotNull @Positive Integer amount) {
}
~~~

Các annotation như @NotBlank và @Positive chỉ là metadata cho validation provider. Chúng không tự chạy chỉ vì object được publish qua ApplicationEventPublisher.

Cần gọi Validator.validate(...), cấu hình method validation phù hợp hoặc dùng một boundary đã được Spring kích hoạt validation. Nếu không có validation provider và cơ chế thực thi, constraint không tự từ chối payload.

Ví dụ gọi Validator trực tiếp:

~~~java
Set<ConstraintViolation<OrderCommand>> violations =
        validator.validate(command);

if (!violations.isEmpty()) {
    throw new ConstraintViolationException(violations);
}
~~~

Sau khi validation thành công, mới tạo event và publish. Không chuyển trách nhiệm xác minh dữ liệu bắt buộc sang một listener phụ chạy sau đó.

## 6. Dữ liệu không hợp lệ trong batch event

Khi một event mang nhiều item, cần xác định chính sách cho toàn batch:

- **All-or-nothing:** nếu một item sai, từ chối cả batch trước khi publish.
- **Partial acceptance:** chấp nhận item hợp lệ, trả danh sách item bị từ chối và lý do tương ứng.
- **Quarantine:** lưu item lỗi vào vùng cách ly để xử lý lại, nếu kiến trúc có cơ chế này.

Không nên âm thầm lọc bỏ item null hoặc sai dữ liệu bằng stream.filter(Objects::nonNull) rồi coi batch đã thành công. Người gọi cần biết item nào bị loại và vì sao.

Ví dụ xử lý partial acceptance:

~~~java
List<OrderCommand> accepted = new ArrayList<>();
List<RejectedOrder> rejected = new ArrayList<>();

for (OrderCommand command : commands) {
    String reason = validateReason(command);

    if (reason == null) {
        accepted.add(command);
    } else {
        rejected.add(new RejectedOrder(command, reason));
    }
}
~~~

Chỉ publish event cho dữ liệu đã được chấp nhận. Có thể phát một BatchImportCompleted event chứa số lượng accepted/rejected và mã batch; không nên nhét toàn bộ dữ liệu lỗi nhạy cảm vào event hoặc log.

## 7. Lỗi validation và lỗi listener là hai loại lỗi khác nhau

Validation xảy ra trước publish và quyết định command có được phép chuyển thành event hay không. Listener filtering xảy ra sau publish và quyết định consumer nào quan tâm đến event.

| Tình huống | Vị trí xử lý | Kết quả |
|---|---|---|
| Command null | Application service | Từ chối use case |
| orderId rỗng | Validator/domain constructor | Không tạo event |
| publishEvent(null) | ApplicationContext | Ném IllegalArgumentException |
| Payload có field null | Boundary hoặc listener policy | Phải được validate hoặc lọc có chủ đích |
| Event type không phù hợp | Multicaster | Listener không được gọi |
| SpEL condition false | Event listener adapter | Method listener bị bỏ qua |
| Listener ném exception | Multicaster/async executor | Xử lý theo chính sách exception |
| Event hợp lệ nhưng consumer không quan tâm | Listener condition/type | Consumer bỏ qua event |

Nếu dữ liệu sai làm nghiệp vụ không thể tiếp tục, hãy fail-fast trước publish. Nếu listener chỉ không quan tâm đến một biến thể event, dùng type filter hoặc condition. Nếu listener phụ thất bại, xử lý lỗi theo chính sách listener; không biến lỗi hạ tầng thành lỗi validation của command.

## 8. Null-safe event design

Một event tốt nên có hợp đồng dữ liệu rõ ràng:

~~~java
public record OrderSubmitted(
        UUID eventId,
        String orderId,
        int amount,
        Instant occurredAt) {

    public OrderSubmitted {
        Objects.requireNonNull(eventId, "eventId is required");
        Objects.requireNonNull(occurredAt, "occurredAt is required");

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}
~~~

Các field quan trọng:

- eventId để truy vết, deduplicate hoặc xử lý idempotent.
- orderId để liên kết với aggregate.
- amount có miền giá trị hợp lệ.
- occurredAt để biểu đạt thời điểm nghiệp vụ xảy ra.

Không dùng null để biểu đạt nhiều trạng thái khác nhau. Nếu một field thực sự tùy chọn, hãy mô tả rõ ý nghĩa khi thiếu. Nếu có nhiều trạng thái, dùng enum hoặc kiểu dữ liệu tường minh.

Với payload mutable, listener có thể quan sát dữ liệu đã bị sửa sau khi publish, đặc biệt khi event được dispatch bất đồng bộ. Ưu tiên record, immutable collection và defensive copy để mọi listener nhìn thấy cùng một snapshot hợp lệ.

## 9. Ví dụ hoàn chỉnh với Java 17 và Spring Framework 6.2

Ví dụ dưới đây minh họa bốn tình huống:

1. publishEvent(null) bị Spring từ chối ngay tại cửa publish.
2. Legacy payload khác null nhưng có field sai vẫn được publish; listener quan sát nhận event, còn listener có SpEL condition bỏ qua payload đó.
3. Command không hợp lệ bị OrderService từ chối trước khi tạo event.
4. Command hợp lệ tạo OrderSubmitted bất biến và listener nhận được.

### Cấu trúc thư mục

~~~text
event-validation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── EventValidationDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>event-validation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
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

### EventValidationDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventValidationDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ApplicationEventPublisher publisher = context;
            OrderService service = context.getBean(OrderService.class);

            try {
                publisher.publishEvent((Object) null);
            } catch (IllegalArgumentException ex) {
                System.out.println("NULL_EVENT_REJECTED: " + ex.getMessage());
            }

            publisher.publishEvent(
                    new LegacyOrderPayload(null, -10));

            publisher.publishEvent(
                    new LegacyOrderPayload("ORD-79", 120));

            try {
                service.submit(new OrderCommand(" ", 50));
            } catch (IllegalArgumentException ex) {
                System.out.println("COMMAND_REJECTED: " + ex.getMessage());
            }

            service.submit(new OrderCommand("ORD-80", 250));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public OrderService orderService(
                ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public EventListeners eventListeners() {
            return new EventListeners();
        }
    }

    public record OrderCommand(String orderId, Integer amount) {
    }

    public record OrderSubmitted(String orderId, int amount) {

        public OrderSubmitted {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }

            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
        }
    }

    public static class LegacyOrderPayload {

        private final String orderId;
        private final Integer amount;

        public LegacyOrderPayload(String orderId, Integer amount) {
            this.orderId = orderId;
            this.amount = amount;
        }

        public String getOrderId() {
            return orderId;
        }

        public Integer getAmount() {
            return amount;
        }
    }

    public static class OrderService {

        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void submit(OrderCommand command) {
            if (command == null) {
                throw new IllegalArgumentException("command is required");
            }

            if (command.orderId() == null ||
                    command.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }

            if (command.amount() == null || command.amount() <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            publisher.publishEvent(
                    new OrderSubmitted(command.orderId(), command.amount()));
        }
    }

    public static class EventListeners {

        @EventListener
        @Order(1)
        public void observeLegacy(LegacyOrderPayload event) {
            System.out.println(
                    "LEGACY_EVENT_RECEIVED: " + event.getOrderId());
        }

        @EventListener(
                condition = "#a0.orderId != null and " +
                            "!#a0.orderId.isBlank() and " +
                            "#a0.amount != null and #a0.amount > 0")
        @Order(2)
        public void processValidLegacy(LegacyOrderPayload event) {
            System.out.println(
                    "LEGACY_FILTER_ACCEPTED: " + event.getOrderId());
        }

        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            System.out.println(
                    "VALID_ORDER_RECEIVED: " + event.orderId());
        }
    }
}
~~~

### Biên dịch và chạy

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.EventValidationDemo
~~~

Kết quả stdout:

~~~text
NULL_EVENT_REJECTED: Event must not be null
LEGACY_EVENT_RECEIVED: null
LEGACY_EVENT_RECEIVED: ORD-79
LEGACY_FILTER_ACCEPTED: ORD-79
COMMAND_REJECTED: orderId is required
VALID_ORDER_RECEIVED: ORD-80
~~~

Giải thích:

1. ApplicationContext từ chối null event trước khi dispatch và ném IllegalArgumentException.
2. LegacyOrderPayload đầu tiên là object khác null nên được Spring bọc thành PayloadApplicationEvent. Listener quan sát nhận payload và in orderId null.
3. Condition của processValidLegacy trả false vì orderId null và amount âm, nên method đó không được gọi. Event vẫn đã được publish.
4. Payload hợp lệ ORD-79 được listener quan sát và listener có condition chấp nhận.
5. OrderService từ chối command có orderId chỉ chứa khoảng trắng. Không có OrderSubmitted event nào được tạo cho command đó.
6. Command ORD-80 vượt qua validation, tạo OrderSubmitted hợp lệ và listener nhận event.

Ví dụ cố ý giữ một class LegacyOrderPayload không có validation để minh họa dữ liệu cũ hoặc dữ liệu từ nguồn ngoài có thể đi vào event bus. Trong code mới, nên tạo event bất biến và kiểm tra invariant trước khi publish.

## 10. Kiểm thử và quan sát

Nên kiểm thử riêng cửa publish, validation và listener filter:

- Publish null event phải ném IllegalArgumentException.
- Constructor của event phải từ chối source null hoặc field bắt buộc null theo hợp đồng của event.
- Command không hợp lệ phải bị từ chối và không publish event.
- Payload khác null nhưng có field null phải chỉ kích hoạt listener không có condition hoặc listener được thiết kế để nhận dữ liệu đó.
- Condition false phải bỏ qua đúng method listener, trong khi listener khác vẫn nhận event.
- Condition true phải kích hoạt method listener tương ứng.
- Kiểm tra generic event type để tránh listener nhận nhầm payload.
- Kiểm tra batch partial acceptance để không mất dấu item bị loại.

Nếu cần quan sát dữ liệu bị bỏ qua, ghi metric như invalid_payload_total, filtered_event_total và rejected_command_total. Log nên có event ID hoặc correlation ID, event type, lý do từ chối và business key phù hợp. Tránh log toàn bộ payload nếu nó chứa dữ liệu cá nhân hoặc bí mật.

Với listener async, exception không nhất thiết truyền về publisher. Hãy cấu hình error handling và theo dõi task thất bại riêng. Một condition false không phải exception và thường không cần log ở mức lỗi; chỉ ghi nhận nếu việc lọc đó quan trọng đối với vận hành.

## 11. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Publish null event | Spring ném IllegalArgumentException | Kiểm tra event trước publish |
| Nghĩ Spring tự validate field trong payload | Listener có thể nhận dữ liệu sai | Validate command/domain object tại boundary |
| Dùng SpEL condition như validation toàn cục | Chỉ một method bị bỏ qua, listener khác vẫn chạy | Validate trước publish nếu event không hợp lệ |
| Condition truy cập field null không an toàn | SpEL có thể lỗi khi đánh giá | Dùng điều kiện null check hoặc safe navigation |
| Dùng tên tham số nhưng không giữ parameter metadata | SpEL không tìm thấy biến | Dùng #a0/#p0 hoặc biên dịch với -parameters |
| Chỉ lọc theo event class | Payload sai vẫn có thể được nhận | Kết hợp validation và condition khi cần |
| Dùng raw generic listener | Mất khả năng lọc kiểu rõ ràng | Khai báo generic cụ thể |
| Dùng null để biểu đạt một trạng thái nghiệp vụ | Consumer không biết ý nghĩa của null | Tạo event hoặc enum riêng |
| Âm thầm loại item lỗi trong batch | Mất dữ liệu và khó kiểm toán | Trả danh sách rejected item cùng lý do |
| Bắt lỗi trong listener rồi bỏ qua | Dữ liệu lỗi có thể biến mất khỏi luồng quan sát | Ghi nhận trạng thái, metric và chính sách retry |

## 12. Checklist thiết kế

- Không gọi publishEvent với event object null.
- Đảm bảo source của ApplicationEvent và payload của PayloadApplicationEvent khác null.
- Xác định field nào bắt buộc và field nào thật sự tùy chọn.
- Validate command và dữ liệu nghiệp vụ trước khi publish.
- Giữ event immutable và chứa snapshot dữ liệu hợp lệ.
- Dùng generic event type để lọc nhóm event ở tầng dispatch.
- Dùng @EventListener(condition) chỉ cho quyết định listener nào quan tâm.
- Dùng #a0 hoặc #p0 khi cần tham chiếu tham số ổn định trong SpEL.
- Dùng safe navigation và null checks cho thuộc tính tùy chọn.
- Không coi condition false là event bị từ chối hoặc bị hủy.
- Có chính sách rõ ràng cho batch: all-or-nothing, partial acceptance hoặc quarantine.
- Theo dõi rejected command và filtered event khi nghiệp vụ cần audit.
- Kiểm thử cả null event, null field, invalid value, condition true/false và listener exception.

Lọc event giúp mỗi listener chỉ nhận loại dữ liệu nó quan tâm. Validation bảo đảm event được phát ra đã đáp ứng hợp đồng nghiệp vụ. Khi đặt hai trách nhiệm đúng chỗ, hệ thống tránh được null pointer, dữ liệu sai lọt vào consumer và việc condition vô tình che giấu lỗi của publisher.

## 13. Tài liệu chính thức

- [Spring Framework 6.2 — Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — PayloadApplicationEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/PayloadApplicationEvent.html)
- [Spring Framework 6.2 — GenericApplicationListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/GenericApplicationListener.html)
- [Spring Framework 6.2 — Null-safety](https://docs.spring.io/spring/reference/6.2/core/null-safety.html)
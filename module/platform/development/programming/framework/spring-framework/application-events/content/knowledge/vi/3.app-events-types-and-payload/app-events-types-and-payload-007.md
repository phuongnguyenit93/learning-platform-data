# Payload bất biến và an toàn khi chia sẻ

Trong Spring Framework, application event thường được chuyển tới một hoặc nhiều listener trong cùng ApplicationContext. Khi publish event, các listener nhận tham chiếu tới event hoặc payload mà publisher gửi. Nếu dữ liệu có thể bị thay đổi sau khi publish, listener có thể quan sát trạng thái khác nhau hoặc ghi đè dữ liệu mà listener khác đang sử dụng.

Vì vậy, **payload bất biến** là lựa chọn tốt cho application event. Payload bất biến không cho phép thay đổi trạng thái sau khi được tạo. Khi nhiều listener cùng đọc payload, kể cả khi chúng chạy trên các thread khác nhau, chúng có thể dùng chung dữ liệu mà không phải phối hợp khóa để bảo vệ việc sửa đổi.

## 1. Payload trong Spring Application Events

Payload là dữ liệu mô tả sự kiện mà ứng dụng muốn thông báo. Ví dụ, khi một đơn hàng được tạo, event có thể mang mã đơn hàng, thời điểm tạo, các dòng hàng và tổng tiền. Listener dùng dữ liệu này để gửi thông báo, ghi audit hoặc cập nhật một read model.

Spring hỗ trợ hai cách phổ biến:

- **ApplicationEvent tùy chỉnh:** tạo class kế thừa ApplicationEvent và đặt dữ liệu nghiệp vụ trong các field của lớp con.
- **POJO hoặc record:** publish một object Java thông thường. Từ Spring Framework 4.2, Spring tự bọc object này trong PayloadApplicationEvent.

Ví dụ event kế thừa ApplicationEvent:

~~~java
public class OrderCreatedEvent extends ApplicationEvent {

    private final String orderId;

    public OrderCreatedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

Ví dụ payload POJO:

~~~java
public record OrderCreated(String orderId) {
}
~~~

Cả hai cách đều có thể mang dữ liệu cho listener. Dù dùng kiểu nào, nguyên tắc thiết kế vẫn giống nhau: dữ liệu đã publish nên được xem là một snapshot của sự kiện tại thời điểm phát.

## 2. Vì sao cần payload bất biến?

Giả sử OrderService publish một event chứa danh sách dòng hàng. Nếu service tiếp tục sửa danh sách sau khi publish, listener có thể nhận thấy nội dung đã thay đổi. Nếu listener thứ nhất sửa danh sách, listener thứ hai cũng có thể nhìn thấy thay đổi đó vì các listener thường cùng nhận một event object.

Các rủi ro thường gặp:

- **Race condition:** hai thread đọc và ghi cùng một collection mà không có đồng bộ phù hợp.
- **Dữ liệu không nhất quán:** listener xử lý một event nhưng giá trị bên trong đã đổi sau thời điểm publish.
- **Phụ thuộc thứ tự:** kết quả của listener này làm thay đổi dữ liệu listener khác đọc.
- **Lỗi khó tái hiện:** bug chỉ xuất hiện khi executor, tải hệ thống hoặc thứ tự thực thi thay đổi.
- **Khó kiểm thử:** test phụ thuộc vào thứ tự listener và trạng thái mutable còn sót lại.

Payload bất biến giúp event trở thành thông điệp dữ liệu ổn định. Publisher có thể tiếp tục xử lý, còn listener có thể đọc cùng một snapshot mà không lo một bên sửa dữ liệu của bên kia.

## 3. Immutable thực sự khác với chỉ dùng final

Trong Java, từ khóa final ngăn việc gán lại một biến tham chiếu sau khi khởi tạo. Nó không tự làm object mà biến tham chiếu trỏ tới trở thành bất biến.

Ví dụ sau chưa bất biến:

~~~java
public final class OrderPayload {

    private final List<String> items;

    public OrderPayload(List<String> items) {
        this.items = items;
    }

    public List<String> getItems() {
        return items;
    }
}
~~~

Field items là final, nhưng caller vẫn có thể sửa danh sách ban đầu hoặc sửa danh sách qua getter:

~~~java
List<String> items = new ArrayList<>();
items.add("BOOK");

OrderPayload payload = new OrderPayload(items);

items.add("PEN");             // Thay đổi dữ liệu bên trong payload.
payload.getItems().clear();  // Cũng thay đổi dữ liệu bên trong payload.
~~~

Để tạo payload an toàn hơn, cần kiểm soát cả dữ liệu đầu vào lẫn dữ liệu trả ra:

~~~java
public final class OrderPayload {

    private final List<String> items;

    public OrderPayload(List<String> items) {
        this.items = List.copyOf(items);
    }

    public List<String> getItems() {
        return items;
    }
}
~~~

List.copyOf tạo một danh sách không thể sửa đổi và tách cấu trúc danh sách khỏi collection đầu vào. Sau khi tạo payload, việc thêm hoặc xóa phần tử trong danh sách gốc không làm thay đổi danh sách được lưu trong payload. Getter trả về danh sách không thể sửa đổi.

Tuy nhiên, **List.copyOf chỉ tạo bản sao nông (shallow copy)**. Nếu phần tử bên trong là object mutable, object đó vẫn có thể bị thay đổi. Immutable phải được bảo đảm ở toàn bộ cây dữ liệu mà listener có thể truy cập.

## 4. Dùng Java record cho payload

Java record phù hợp với payload vì record cung cấp constructor, accessor, equals, hashCode và toString dựa trên các component. Các component được lưu trong field final. Nhưng record chỉ bất biến nông: nếu component là List mutable hoặc object mutable khác, trạng thái bên trong vẫn có thể thay đổi.

Ví dụ payload an toàn với các giá trị bất biến:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice) {

    public OrderLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must not be negative");
        }
    }
}

public record OrderCreated(
        String orderId,
        Instant occurredAt,
        List<OrderLine> lines) {

    public OrderCreated {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
        lines = List.copyOf(lines);

        if (lines.isEmpty()) {
            throw new IllegalArgumentException("lines must not be empty");
        }
    }
}
~~~

Các component trong ví dụ:

- String là immutable.
- Instant là immutable.
- BigDecimal là immutable.
- OrderLine là record chỉ chứa các giá trị immutable.
- List.copyOf tạo cấu trúc danh sách không thể sửa đổi và sao chép phần tử tham chiếu vào danh sách mới.

Vì từng OrderLine cũng bất biến, listener có thể chia sẻ OrderCreated mà không lo một listener sửa dòng hàng để ảnh hưởng listener khác. Constructor kiểm tra null và điều kiện nghiệp vụ để payload không được tạo ở trạng thái không hợp lệ.

Lưu ý List.copyOf từ chối phần tử null. Nếu nghiệp vụ cho phép null, hãy định nghĩa rõ ý nghĩa của null và dùng cách sao chép phù hợp. Thông thường, payload event nên tránh phần tử null để listener đơn giản hơn.

## 5. Defensive copy cho collection, map và array

Với collection, dùng các factory copy bất biến khi dữ liệu không chứa null:

~~~java
List<String> safeItems = List.copyOf(inputItems);
Set<String> safeTags = Set.copyOf(inputTags);
Map<String, String> safeAttributes = Map.copyOf(inputAttributes);
~~~

Các phương thức này tạo cấu trúc collection không thể sửa đổi. Chúng không làm cho object được lưu bên trong trở thành immutable. Ví dụ, Map<String, CustomerProfile> vẫn có thể chứa CustomerProfile mutable; caller có thể sửa profile và listener sẽ quan sát thay đổi đó.

Nếu cần dùng collection có thứ tự hoặc cho phép null, có thể tạo bản sao riêng rồi bọc bằng wrapper không cho sửa đổi:

~~~java
List<String> copy = new ArrayList<>(inputItems);
List<String> safeView = Collections.unmodifiableList(copy);
~~~

Wrapper phải bao quanh bản sao riêng. Nếu chỉ gọi Collections.unmodifiableList(inputItems) trên collection gốc, code khác vẫn có thể sửa inputItems và làm thay đổi nội dung mà listener quan sát.

### Array cần sao chép cả khi nhận và trả

Array luôn mutable. Nếu payload chứa byte array, hãy clone khi nhận dữ liệu và khi trả dữ liệu:

~~~java
public final class DocumentPayload {

    private final byte[] content;

    public DocumentPayload(byte[] content) {
        this.content = content.clone();
    }

    public byte[] content() {
        return content.clone();
    }
}
~~~

Nếu chỉ clone trong constructor nhưng trả thẳng field từ accessor, caller vẫn có thể sửa nội dung nội bộ. Nếu chỉ clone khi trả mà giữ nguyên array đầu vào, caller vẫn có thể sửa payload thông qua tham chiếu cũ.

Với object lồng nhau, phải áp dụng defensive copy hoặc chuyển đổi sang kiểu immutable ở từng tầng. Một bản sao nông của collection không đủ để bảo vệ các object mutable bên trong.

## 6. Snapshot tại thời điểm publish

Một event nên biểu diễn trạng thái tại thời điểm sự kiện xảy ra. Đừng publish một collection hoặc entity mà code nghiệp vụ vẫn sẽ sửa sau đó.

Ví dụ:

~~~java
List<OrderLine> draftLines = new ArrayList<>();
draftLines.add(new OrderLine(
        "BOOK-01", 2, new BigDecimal("12.50")));

OrderCreated event = new OrderCreated(
        "ORD-1001",
        Instant.parse("2026-11-11T03:00:00Z"),
        draftLines);

draftLines.clear();

// Event vẫn giữ một snapshot gồm một dòng hàng.
publisher.publishEvent(event);
~~~

Trong ví dụ, constructor OrderCreated dùng List.copyOf nên việc clear draftLines không làm mất dòng hàng trong event.

Có hai cách thiết kế snapshot phổ biến:

1. **Snapshot chứa dữ liệu cần thiết:** event mang ID, thời gian, số lượng và giá trị đã chốt tại thời điểm phát. Listener xử lý đúng trạng thái lịch sử.
2. **Event chỉ chứa định danh:** event mang orderId, listener tự đọc dữ liệu mới nhất từ repository. Cách này giảm kích thước payload nhưng listener sẽ nhìn thấy trạng thái tại thời điểm đọc, có thể khác trạng thái lúc event được publish.

Hãy chọn theo ý nghĩa nghiệp vụ. Nếu listener phải xử lý chính xác dữ liệu tại thời điểm đơn hàng được tạo, hãy mang snapshot bất biến. Nếu listener cần trạng thái hiện tại, chỉ truyền ID và đọc lại từ nguồn dữ liệu.

## 7. An toàn khi chia sẻ giữa nhiều listener và thread

ApplicationEventMulticaster phân phối event tới các listener phù hợp. Trong luồng mặc định, listener được gọi đồng bộ trên thread publish event. Khi cấu hình executor hoặc dùng cơ chế async, listener có thể chạy trên thread khác.

Spring không deep-copy event hoặc payload cho từng listener. Các listener có thể nhận cùng một event instance hoặc cùng tham chiếu tới payload bên trong wrapper. Vì vậy:

- Không sửa field hoặc collection trong payload sau khi publish.
- Không để một listener thay đổi object mà listener khác đang đọc.
- Không giả định executor sẽ tự biến payload mutable thành thread-safe.
- Nếu cần thay đổi dữ liệu, hãy tạo object mới thay vì sửa object event.
- Nếu cần trạng thái dùng chung có thể thay đổi, hãy dùng một abstraction thread-safe riêng và quản lý đồng bộ ở nơi sở hữu trạng thái đó.

Object immutable được tạo hoàn chỉnh trong constructor và không để lộ this trước khi constructor kết thúc có thể được chia sẻ an toàn hơn theo quy tắc final-field của Java Memory Model. Tuy nhiên, bảo đảm đó không biến các object mutable được tham chiếu bên trong thành thread-safe. Tính bất biến phải bao phủ toàn bộ dữ liệu mà listener có thể truy cập.

Khi async listener cần truy cập dữ liệu đã commit, hãy cân nhắc @TransactionalEventListener với phase AFTER_COMMIT. Async không tự truyền transaction context sang thread khác. Nếu cần giao nhận bền vững qua restart hoặc giữa nhiều process, application event nội bộ không đủ; cần message broker và cơ chế lưu trữ phù hợp.

## 8. Ví dụ chạy được với Java 17 và Spring Framework

Ví dụ dùng record làm payload, defensive copy danh sách dòng hàng, rồi publish qua ApplicationEventPublisher. Listener nhận trực tiếp payload bằng @EventListener.

### Cấu trúc thư mục

~~~text
immutable-event-payload-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ImmutableEventPayloadDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>immutable-event-payload-demo</artifactId>
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

### ImmutableEventPayloadDemo.java

~~~java
package demo;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ImmutableEventPayloadDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            service.createOrder("ORD-1001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public OrderCreatedListener orderCreatedListener() {
            return new OrderCreatedListener();
        }
    }

    public record OrderLine(
            String sku,
            int quantity,
            BigDecimal unitPrice) {

        public OrderLine {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "unitPrice must not be negative");
            }
        }
    }

    public record OrderCreated(
            String orderId,
            Instant occurredAt,
            List<OrderLine> lines) {

        public OrderCreated {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            lines = List.copyOf(lines);
            if (lines.isEmpty()) {
                throw new IllegalArgumentException(
                        "lines must not be empty");
            }
        }
    }

    public static class OrderService {

        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void createOrder(String orderId) {
            List<OrderLine> draftLines = new ArrayList<>();
            draftLines.add(new OrderLine(
                    "BOOK-01", 2, new BigDecimal("12.50")));

            OrderCreated event = new OrderCreated(
                    orderId,
                    Instant.parse("2026-11-11T03:00:00Z"),
                    draftLines);

            // Thay đổi danh sách gốc không ảnh hưởng snapshot trong event.
            draftLines.clear();

            System.out.println("Publishing " + orderId);
            publisher.publishEvent(event);
        }
    }

    public static class OrderCreatedListener {

        @EventListener
        public void handle(OrderCreated event) {
            System.out.println(
                    "Received " + event.orderId()
                            + " with " + event.lines().size() + " line(s)");
        }
    }
}
~~~

### Biên dịch và chạy

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ImmutableEventPayloadDemo
~~~

Kết quả stdout:

~~~text
Publishing ORD-1001
Received ORD-1001 with 1 line(s)
~~~

Giải thích:

1. OrderService tạo một ArrayList mutable và thêm một dòng hàng.
2. Constructor OrderCreated dùng List.copyOf để tạo cấu trúc danh sách riêng, không thể sửa đổi.
3. Service xóa phần tử khỏi draftLines; snapshot trong event vẫn giữ một dòng.
4. Service publish record OrderCreated. Spring bọc payload trong PayloadApplicationEvent và phân phối tới listener phù hợp.
5. Listener nhận trực tiếp OrderCreated qua @EventListener và đọc payload bất biến.
6. Vì listener mặc định chạy đồng bộ, dòng Received được in trước khi publishEvent trả về.

Ví dụ cho thấy record giúp biểu diễn dữ liệu, còn List.copyOf và các kiểu phần tử bất biến mới bảo đảm payload không bị thay đổi qua collection lồng bên trong.

## 9. Các lỗi thường gặp khi thiết kế payload

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ dùng final cho collection | Nội dung collection vẫn mutable | Sao chép và bọc collection không sửa đổi |
| Dùng record nhưng chứa ArrayList | Record chỉ bất biến nông | Sao chép collection trong compact constructor |
| Chỉ copy collection nhưng phần tử mutable | Listener vẫn có thể sửa object bên trong | Dùng phần tử immutable hoặc copy sâu |
| Trả trực tiếp array nội bộ | Caller có thể sửa payload | Clone khi nhận và khi trả |
| Bọc collection gốc bằng unmodifiableList | Code khác vẫn sửa collection gốc | Bọc bản sao riêng |
| Publish entity đang tiếp tục thay đổi | Listener quan sát trạng thái khác nhau | Publish snapshot bất biến hoặc chỉ truyền ID |
| Một listener sửa payload cho listener khác | Tạo phụ thuộc vào thứ tự và race condition | Xem payload là read-only |
| Nghĩ async executor tự làm object thread-safe | Mutable object vẫn có thể có data race | Dùng immutable sâu hoặc đồng bộ đúng nơi sở hữu |

## 10. Checklist thiết kế payload an toàn

- Chọn dữ liệu event phản ánh đúng thời điểm sự kiện xảy ra.
- Ưu tiên record hoặc class final với field final.
- Dùng các kiểu giá trị immutable như String, BigDecimal, Instant và enum.
- Sao chép collection đầu vào bằng List.copyOf, Set.copyOf hoặc Map.copyOf khi phù hợp.
- Bảo đảm phần tử bên trong collection cũng immutable.
- Clone array khi nhận dữ liệu và khi trả dữ liệu.
- Không trả ra tham chiếu mutable tới trạng thái nội bộ.
- Không sửa payload sau khi publish.
- Kiểm thử rằng thay đổi collection đầu vào không làm thay đổi payload và getter không cho phép sửa cấu trúc.
- Khi listener chạy async, rà soát mọi object lồng nhau và không dựa vào transaction context của publisher.

Payload bất biến biến application event thành một snapshot đáng tin cậy. Khi publisher và nhiều listener chia sẻ cùng một event, thiết kế immutable sâu giúp giảm race condition, tránh phụ thuộc thứ tự thực thi và làm hành vi của ứng dụng dễ kiểm thử hơn.
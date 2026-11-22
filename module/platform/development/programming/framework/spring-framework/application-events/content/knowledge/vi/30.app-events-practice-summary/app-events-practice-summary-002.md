# Tạo event bằng record bất biến trong Spring Framework Application Events

## 1. Mục tiêu

Khi thiết kế Spring Application Events, event nên mô tả một **sự kiện đã xảy ra** bằng dữ liệu rõ ràng và ổn định. Ví dụ: `OrderPlaced` lưu `eventId`, `orderId`, thời điểm xảy ra và những dòng hàng đã được đặt. Một listener nhận event có thể chạy ngay trên publisher thread hoặc chạy trễ hơn ở executor khác. Vì vậy, **event payload không nên thay đổi âm thầm sau thời điểm publish**.

Java `record` (ổn định từ Java 16, dùng tốt với Java 17+) là lựa chọn gọn để tạo các value object như vậy: khai báo các thành phần dữ liệu một lần, compiler tạo constructor, accessors, `equals()`, `hashCode()` và `toString()`. Record rất hợp để biểu diễn domain event nội bộ, nhưng cần hiểu một giới hạn quan trọng: **record là shallowly immutable (bất biến nông)**. Các reference fields là final, song đối tượng mà chúng trỏ tới vẫn có thể mutable.

Mục tiêu bài học:

1. Hiểu event record là gì và vì sao **không cần kế thừa `ApplicationEvent`** để dùng trong Spring.
2. Biết dùng record components, compact constructor, validation, `List.copyOf`, `Map.copyOf`.
3. Phân biệt bất biến nông, collection unmodifiable và **event payload thực sự ổn định**.
4. Viết, publish và nhận `OrderPlaced` bằng `ApplicationEventPublisher` + `@EventListener`.
5. Chạy ví dụ Java 17+ Spring Framework 6.2 có stdout tất định, chứng minh **defensive copy**, validation, dispatch và value equality.
6. Thiết kế eventId, occurredAt, version, dữ liệu snapshot, idempotency và serialization khi tích hợp ngoài ứng dụng.
7. Tránh các lỗi phổ biến khi event đi qua `@Async`, transaction hoặc message broker.

**Nguyên tắc:** event nên là một **ảnh chụp dữ liệu có nghĩa tại thời điểm xảy ra sự kiện**, không phải một reference tới trạng thái domain đang tiếp tục thay đổi.

## 2. Java record cung cấp gì?

Một Java record đơn giản:

~~~java
public record UserRegistered(
        String eventId,
        long userId,
        String email
) {}
~~~

Bạn có thể khởi tạo:

~~~java
UserRegistered event =
        new UserRegistered("evt-101", 42L, "user@example.test");

System.out.println(event.eventId()); // evt-101
System.out.println(event.userId());  // 42
~~~

Compiler tạo các thành phần tương đương về mặt contract:

- Một class `final` kế thừa `java.lang.Record`.
- Các instance fields tương ứng với record components là `private final`.
- Canonical constructor nhận giá trị cho từng component.
- Accessor có tên **`eventId()`, `userId()`, `email()`** (không phải getter JavaBean `getEventId()` mặc định).
- `equals()` và `hashCode()` dựa trên các components.
- `toString()` hiển thị các components theo cơ chế record.

Record có thể có method, static field, static nested types, implemented interfaces và constructor tùy theo quy tắc record. Nhưng không thể khai báo thêm instance field tùy ý ngoài record components, và không thể kế thừa một class nghiệp vụ khác vì đã kế thừa `java.lang.Record`.

### 2.1. Record không tự biến dữ liệu thành bất biến sâu

Ví dụ dễ mắc lỗi:

~~~java
public record WrongOrderPlaced(
        String orderId,
        List<String> productCodes
) {}
~~~

Các field của record không thể được gán lại, nhưng nếu caller truyền một `ArrayList`:

~~~java
List<String> original = new ArrayList<>();
original.add("SKU-A");
WrongOrderPlaced event = new WrongOrderPlaced("o-1", original);

original.add("SKU-B"); // event.productCodes() nay cũng có SKU-B.
event.productCodes().clear(); // Có thể xóa luôn dữ liệu trong original.
~~~

`final` ở đây chỉ ngăn việc record đổi **reference** của component, không làm object được tham chiếu tự trở thành immutable. Nếu event được đưa vào async queue và publisher sửa `original` trước lúc listener xử lý, listener có thể thấy dữ liệu ngoài ý muốn hoặc gặp vấn đề cạnh tranh dữ liệu.

### 2.2. Defensive copy bằng `List.copyOf`

~~~java
public record OrderPlaced(
        String orderId,
        List<String> productCodes
) {
    public OrderPlaced {
        productCodes = List.copyOf(productCodes);
    }
}
~~~

Đây là một **compact canonical constructor**. Java tự gán các tham số đã được kiểm tra/thay thế vào final components sau khi constructor body hoàn tất. `List.copyOf` trả về một list **unmodifiable**: không thể `add`, `remove`, `set` trên list được lưu trong event.

Nếu input là một mutable list, thay đổi input sau đó **không làm thay đổi** list đã copy trong record. `List.copyOf` cũng từ chối `null` list hoặc `null` elements. Nếu input đã là một unmodifiable list phù hợp, implementation có thể dùng lại đối tượng thay vì cấp phát bản sao mới; điều quan trọng là contract unmodifiable.

Tuy nhiên, `List.copyOf` vẫn chỉ copy **cấu trúc list**, không deep-copy các elements. Nếu `List<MutableLine>` chứa các object mutable, gọi `line.setQuantity(999)` vẫn có thể làm nội dung event thay đổi. Muốn event thật sự ổn định, hãy dùng **immutable element types** như record có các components bất biến, hoặc deep-copy/convert elements sang value objects.

### 2.3. `Map.copyOf`, `Set.copyOf` và arrays

Đối với metadata nhỏ, `Map.copyOf(map)` là lựa chọn tương tự. Nó tạo map unmodifiable và tách khỏi mutation của mutable map đầu vào, nhưng vẫn không deep-copy **giá trị object**. Nó từ chối key/value `null`.

`Set.copyOf` cũng có thể hữu ích; khi xuất phát từ một collection có phần tử trùng, tính chất set là chỉ giữ những giá trị duy nhất.

Với `byte[]`, `char[]` hoặc mảng object, **record tự động giữ reference tới mảng mutable**. Ví dụ:

~~~java
public record BadBinaryEvent(byte[] bytes) {}
~~~

Dù field `bytes` là final, caller vẫn có thể sửa `bytes[0]`, và accessor `bytes()` đưa chính mảng ấy ra ngoài. Nếu bắt buộc dùng array, phải `clone()` khi nhận và khi trả:

~~~java
public record BinaryEvent(byte[] bytes) {
    public BinaryEvent {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Lưu ý thêm: equality mặc định của record có thành phần array **không deep-compare** nội dung mảng. Nếu muốn equality theo dữ liệu, lựa chọn khác như immutable `List<Byte>` hoặc một value object có equals phù hợp thường dễ hiểu hơn. Đối với event lớn, tránh copy payload quá nhiều không cần thiết: cân nhắc tham chiếu tới blob lưu bền vững bằng ID/hash.

## 3. Vì sao record đặc biệt phù hợp với Spring events?

Spring Framework 4.2+ cho phép publish **bất kỳ object** làm event qua `ApplicationEventPublisher.publishEvent(Object)`. Nếu object không kế thừa `ApplicationEvent`, Spring bọc nó trong `PayloadApplicationEvent` để phân phối. Method `@EventListener` vẫn có thể nhận **kiểu payload gốc**.

~~~java
// POJO/record: không cần extends ApplicationEvent.
public record InvoiceIssued(String invoiceId) {}

// Trong Spring-managed service:
publisher.publishEvent(new InvoiceIssued("inv-100"));

// Trong một Spring-managed listener bean:
@EventListener
public void onInvoiceIssued(InvoiceIssued event) {
    System.out.println(event.invoiceId());
}
~~~

Spring chọn method dựa trên event type/payload type. Đây là cơ chế chính thức, **không phải hack reflection** hay dựa vào Jackson serialization.

### 3.1. Tại sao record không extends ApplicationEvent?

Một Java record đã kế thừa `java.lang.Record`; Java không cho record kế thừa một class khác. `ApplicationEvent` của Spring là một class (kế thừa `EventObject`), nên đoạn sau **không thể biên dịch**:

~~~java
// SAI: record không thể extends ApplicationEvent.
// public record OrderPlaced(String orderId) extends ApplicationEvent {}
~~~

Bạn không cần ép record thành subclass. Cứ dùng `publisher.publishEvent(record)` và `@EventListener` với parameter type record. Nếu muốn triển khai interface để đánh dấu event category, record vẫn được phép `implements` interface đó.

### 3.2. Event object không phải persistence/message broker

Record giúp ổn định **dữ liệu** nhưng **không thay đổi delivery semantics**:

- `SimpleApplicationEventMulticaster` mặc định thường dispatch đồng bộ trên publisher thread.
- `@Async @EventListener` có thể chuyển callback sang thread pool, nhưng record không làm queue trở nên durable.
- `@TransactionalEventListener(AFTER_COMMIT)` điều khiển **phase xử lý** sau commit, không tự ghi event vào durable outbox.
- Nếu cần phát event sang Kafka/RabbitMQ, record có thể là DTO để serialize, nhưng phải chủ động cấu hình schema, publisher, broker, ACK, retry và idempotency.

**Immutable payload** giúp tránh dữ liệu thay đổi bất ngờ khi các listeners chạy ở các thời điểm khác nhau; nó không hứa rằng event sẽ được giao đúng một lần hay còn tồn tại sau JVM crash.

## 4. Thiết kế record event cho một đơn hàng

Một event nghiệp vụ thực tế nên thể hiện những sự kiện đã xảy ra, không dùng tên quá chung chung như `UpdateEvent` hay mang nguyên object `OrderEntity`.

Ví dụ muốn diễn đạt: đơn hàng đã được đặt. Những fields có ý nghĩa:

| Thành phần | Ý nghĩa và lựa chọn |
| --- | --- |
| `eventId` | ID bất biến của event occurrence để deduplicate/redrive |
| `orderId` | Aggregate ID của đơn hàng |
| `occurredAt` | Thời điểm business event xảy ra, dùng `Instant` |
| `lines` | Snapshot dòng hàng bằng `List<OrderLine>` |
| `metadata` | Thuộc tính phi nhạy cảm, có key/value bất biến |
| `schemaVersion` (khi externalize) | Phiên bản payload contract cho consumer khác |

**Dùng `Instant` thay vì `java.util.Date` mutable** giúp tránh nhiều lỗi mutation và timezone. Thời điểm event xảy ra (`occurredAt`) không nhất thiết bằng thời điểm broker nhận, consumer xử lý hoặc database commit.

Với `OrderLine`, nên chọn value object:

~~~java
public record OrderLine(String sku, int quantity) {
    public OrderLine {
        Objects.requireNonNull(sku, "sku");
        if (sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }
}
~~~

`String` và primitive `int` là components ổn định; list chứa những `OrderLine` bất biến như vậy có thể coi là snapshot đủ an toàn cho bài toán đơn giản này.

### 4.1. Compact constructor xác nhận invariant

~~~java
public record OrderPlaced(
        String eventId,
        String orderId,
        Instant occurredAt,
        List<OrderLine> lines,
        Map<String, String> metadata
) {
    public OrderPlaced {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Missing orderId");
        }
        Objects.requireNonNull(occurredAt, "occurredAt");

        lines = List.copyOf(lines);
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Order must have lines");
        }
        metadata = Map.copyOf(metadata);
    }
}
~~~

Đây là constructor hợp lệ trong Java 17. Trong **compact constructor**, bạn không cần và không được viết phép gán tường minh `this.lines = lines` cho component; compiler tự thực hiện ở cuối constructor body. Bạn có thể kiểm tra và gán lại **tham số `lines`** trước bước gán ngầm đó.

Constructor chạy mỗi khi tạo event theo canonical path, giúp bảo vệ invariant ngay tại điểm tạo. Tuy nhiên, Java record **không tự chứng minh** event khớp business state trong database; service cần đảm bảo event được tạo **sau bước nghiệp vụ thích hợp** và metadata đã được xác minh.

### 4.2. Không đặt quá nhiều logic trong event

Event record nên giữ:

- Dữ liệu snapshot nhỏ, typed và có nghĩa.
- Validation cấu trúc/giá trị cơ bản.
- Không có side effect.
- Không gọi database, network hay Spring beans trong constructor.

Không đặt logic gửi email, gọi PaymentGateway, ghi repository hoặc publish event mới vào compact constructor. Event cần dễ tạo, so sánh, serialize và kiểm thử.

Nếu constructor phải tra cứu DB để biết `orderId` hợp lệ, hãy đưa trách nhiệm đó cho application/domain service rồi chỉ tạo event khi invariant nghiệp vụ đã được xác nhận.

## 5. Ví dụ Maven Java 17+ hoàn chỉnh

Ví dụ này chạy với **Spring Framework 6.2.12**, Java 17+ và Maven. Không cần Spring Boot, database, web server, broker hay JUnit để chạy main.

Điều nó chứng minh:

1. Một `ArrayList` và `HashMap` được chuyển thành immutable snapshot trong record.
2. Publisher thay đổi input collections **sau khi tạo event**; record không bị ảnh hưởng.
3. Gọi `add()` trên `event.lines()` bị chặn.
4. `@EventListener` nhận record trực tiếp qua cơ chế `PayloadApplicationEvent`.
5. Listener đồng bộ mặc định ghi nhận đúng một event.
6. Hai record khác instance nhưng cùng component values cho `equals() == true`.
7. Compact constructor từ chối `eventId` trống.

### 5.1. Cấu trúc

~~~text
record-event-demo/
├── pom.xml
└── src/main/java/demo/ImmutableRecordEventDemo.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>record-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <version>3.13.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. src/main/java/demo/ImmutableRecordEventDemo.java

~~~java
package demo;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ImmutableRecordEventDemo {

    // Dòng hàng là value object không chứa component mutable.
    public record OrderLine(String sku, int quantity) {
        public OrderLine {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }
    }

    // Event mô tả một business fact với data snapshot.
    public record OrderPlaced(
            String eventId,
            String orderId,
            Instant occurredAt,
            List<OrderLine> lines,
            Map<String, String> metadata
    ) {
        public OrderPlaced {
            requireText("eventId", eventId);
            requireText("orderId", orderId);
            Objects.requireNonNull(occurredAt, "occurredAt");

            // Defensive copy: không giữ reference mutable của publisher.
            lines = List.copyOf(lines);
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("Missing order lines");
            }
            metadata = Map.copyOf(metadata);
        }

        private static void requireText(String name, String value) {
            Objects.requireNonNull(value, name);
            if (value.isBlank()) {
                throw new IllegalArgumentException(name + " is blank");
            }
        }
    }

    public static final class OrderPublisher {
        private final ApplicationEventPublisher publisher;

        public OrderPublisher(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void place(OrderPlaced event) {
            publisher.publishEvent(event);
        }
    }

    public static final class OrderListener {
        private final List<OrderPlaced> received = new ArrayList<>();

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            received.add(event);
            System.out.println(
                "listener-event=" + event.eventId()
                + ",lines=" + event.lines().size());
        }

        public int count() {
            return received.size();
        }

        public OrderPlaced first() {
            return received.get(0);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderPublisher orderPublisher(
                ApplicationEventPublisher publisher) {
            return new OrderPublisher(publisher);
        }

        @Bean
        public OrderListener orderListener() {
            return new OrderListener();
        }
    }

    public static void main(String[] args) {
        List<OrderLine> inputLines = new ArrayList<>();
        inputLines.add(new OrderLine("SKU-A", 2));

        Map<String, String> inputMetadata = new HashMap<>();
        inputMetadata.put("source", "web");

        Instant occurredAt = Instant.parse("2026-01-10T00:00:00Z");

        OrderPlaced event = new OrderPlaced(
            "evt-100", "order-100", occurredAt,
            inputLines, inputMetadata);

        // Sau khi tạo record, publisher còn quyền sửa dữ liệu đầu vào.
        inputLines.add(new OrderLine("SKU-B", 1));
        inputMetadata.put("source", "mobile");

        System.out.println("snapshot-lines=" + event.lines().size());
        System.out.println(
            "snapshot-source=" + event.metadata().get("source"));

        boolean mutationBlocked = false;
        try {
            event.lines().add(new OrderLine("SKU-C", 1));
        } catch (UnsupportedOperationException expected) {
            mutationBlocked = true;
        }
        System.out.println("mutation-blocked=" + mutationBlocked);

        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            OrderPublisher publisher = context.getBean(OrderPublisher.class);
            OrderListener listener = context.getBean(OrderListener.class);

            publisher.place(event);

            System.out.println("listener-count=" + listener.count());
            System.out.println(
                "same-payload-reference=" + (listener.first() == event));
        }

        // equals() của record so sánh thành phần, không phải object identity.
        OrderPlaced sameData = new OrderPlaced(
            "evt-100",
            "order-100",
            Instant.parse("2026-01-10T00:00:00Z"),
            List.of(new OrderLine("SKU-A", 2)),
            Map.of("source", "web"));
        System.out.println("value-equality=" + event.equals(sameData));

        boolean blankIdRejected = false;
        try {
            new OrderPlaced(
                " ", "order-100", occurredAt,
                List.of(new OrderLine("SKU-A", 2)),
                Map.of("source", "web"));
        } catch (IllegalArgumentException expected) {
            blankIdRejected = true;
        }
        System.out.println("blank-id-rejected=" + blankIdRejected);
    }
}
~~~

Chạy từ thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ImmutableRecordEventDemo
~~~

Tám dòng do **chính chương trình** in ra khi thực thi thành công:

~~~text
snapshot-lines=1
snapshot-source=web
mutation-blocked=true
listener-event=evt-100,lines=1
listener-count=1
same-payload-reference=true
value-equality=true
blank-id-rejected=true
~~~

Maven hoặc Spring có thể in thêm log khác tùy môi trường. Các dòng trên phản ánh đúng thứ tự `System.out.println` trong ví dụ dùng multicaster đồng bộ mặc định. Mã được thiết kế và rà soát theo Java 17/Spring 6.2.12; nếu chưa chạy Maven ở môi trường cụ thể, đây là **output dự kiến**, không phải biên bản test đã chạy.

### 5.4. Giải thích từng kết quả

**snapshot-lines=1**: inputLines ban đầu có một dòng; constructor chạy `List.copyOf`, rồi publisher thêm SKU-B vào inputLines. Event đã lưu snapshot một dòng, không nhìn thấy thay đổi tiếp theo ở list đầu vào.

**snapshot-source=web**: `Map.copyOf` giữ giá trị source=web tại thời điểm tạo record. Việc cập nhật inputMetadata thành source=mobile không ảnh hưởng event.

**mutation-blocked=true**: accessor `event.lines()` trả một unmodifiable list, nên `add()` ném `UnsupportedOperationException`; event không bị sửa.

**listener-event=evt-100,lines=1**: `@EventListener` nhận record từ Spring và đọc các accessors. Với POJO record, Spring có thể wrap thành `PayloadApplicationEvent` nội bộ, nhưng method vẫn nhận chính `OrderPlaced`.

**listener-count=1**: một lần `publishEvent` tới một listener phù hợp, trong cấu hình mặc định đồng bộ và không có publisher khác cho kiểu này.

**same-payload-reference=true**: Spring wrap payload khi dispatch, không bắt buộc clone event; trong demo listener nhận đúng instance `OrderPlaced` đã được publisher gửi. Do đó **immutability thật sự quan trọng**: nếu payload chứa object mutable, listener có thể quan sát trạng thái thay đổi.

**value-equality=true**: hai record khác nhau nhưng có eventId, orderId, occurredAt, lines và metadata bằng nhau. `List` và `Map` so sánh theo giá trị; `OrderLine` là record nên có value equality. Dùng `equals` để assert snapshot trong test rất tiện, nhưng production dedup thường nên dựa trên **eventId ổn định**, không hash toàn bộ payload.

**blank-id-rejected=true**: compact constructor ném `IllegalArgumentException` cho eventId chỉ có whitespace. Bằng cách validate lúc tạo, event không hợp lệ bị chặn trước khi publish.

### 5.5. Tại sao ví dụ là bất biến hữu ích, nhưng không tự đảm bảo mọi event khác?

Trong ví dụ, các components là String, Instant, List<OrderLine> và Map<String,String>; chúng đủ ổn định theo thiết kế. Nhưng nếu thay `OrderLine` bằng class có setter, hoặc thay metadata value bằng `Map<String, Object>`, `List.copyOf` và `Map.copyOf` **không tạo deep copy**. Khi đó record có thể vẫn chứa những object có khả năng thay đổi.

Nếu dùng `BigDecimal` làm giá tiền, nó là immutable nhưng nên quy định scale/currency và business rules. Nếu dùng `java.util.Date`, `byte[]`, `AtomicInteger`, `JsonNode` mutable hoặc JPA entity, cần cân nhắc chuyển sang value type hoặc defensive copy sâu.

## 6. So sánh record với class truyền thống

Hai cách có thể biểu diễn cùng dữ liệu:

~~~java
// Class thường, minh họa; phải tự viết constructor/accessors/equality.
public final class PaymentCaptured {
    private final String eventId;
    private final String paymentId;

    public PaymentCaptured(String eventId, String paymentId) {
        this.eventId = eventId;
        this.paymentId = paymentId;
    }

    public String eventId() {
        return eventId;
    }

    public String paymentId() {
        return paymentId;
    }
}
~~~

Và record:

~~~java
public record PaymentCaptured(
        String eventId,
        String paymentId
) {}
~~~

Record giảm boilerplate, cho value semantics và thể hiện hợp đồng dữ liệu ngay ở header. Nhưng không phải mọi domain object đều nên là record:

- **Entity** có identity, lifecycle, mutability có kiểm soát và invariants phức tạp thường hợp với class/domain model; JPA entities có yêu cầu proxy/constructor riêng.
- **Event/value object** thường phù hợp với record.
- Object cần lazy-loading, state machine nội bộ hoặc kế thừa class khác không phù hợp với record.

Đừng thay thế mọi class thành record chỉ vì cú pháp ngắn. Chọn dựa vào **semantics của dữ liệu**, không phải độ dài code.

### 6.1. Khác biệt về equality

Record so sánh bằng các components. Vì vậy:

~~~java
record OrderPaid(String eventId, long orderId) {}

OrderPaid a = new OrderPaid("evt-1", 10L);
OrderPaid b = new OrderPaid("evt-1", 10L);
System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false
~~~

Điều này rất tiện khi test, nhưng cần thận trọng nếu event ID là một **identity duy nhất**. Hai events cùng eventId nhưng payload khác nhau không nên được mặc định xem là hai event hợp lệ; record `equals()` có thể trả false vì nội dung khác, nhưng hệ thống idempotency vẫn phải phát hiện **xung đột cùng eventId** và xử lý theo chính sách.

Trong test, dùng `assertEquals(expected, actual)` là hợp lý cho value snapshot; trong consumer production, dùng `eventId` và transaction/unique constraint để chống trùng.

## 7. Event ID, thời gian và dữ liệu snapshot

Một event record tốt nên tách biệt:

- **eventId**: một sự kiện cụ thể, giữ ổn định qua retry/redelivery.
- **aggregateId**: đối tượng liên quan, ví dụ orderId.
- **occurredAt**: thời gian business fact xảy ra.
- **correlationId**: ID nhóm workflow/request có liên quan.
- **causationId**: ID sự kiện/command trực tiếp tạo event.
- **schemaVersion**: phiên bản contract khi event được externalize.
- **payload**: dữ liệu nghiệp vụ cần thiết, không phải dump toàn bộ database entity.

### 7.1. Nên tạo eventId khi nào?

Thông thường, application service tạo eventId **một lần khi business event xảy ra**, trước khi persist intent/phát thông điệp. Nếu cần retry hoặc redrive, giữ nguyên ID gốc. Không tạo eventId mới ở mỗi delivery attempt, nếu không dedup theo eventId sẽ thất bại.

UUID là một lựa chọn phổ biến; record không tự sinh UUID. Có thể dùng `UUID.randomUUID().toString()`, ULID hoặc ID do hệ thống cấp, theo yêu cầu phân tán/sắp xếp/truy vết.

### 7.2. occurredAt khác processedAt

`Instant` lưu một mốc UTC và tránh ambiguity của `LocalDateTime` thiếu zone. Nên phân biệt:

~~~text
occurredAt  = thời điểm business fact được ghi nhận
publishedAt = thời điểm publisher/broker chấp nhận gửi
receivedAt  = thời điểm consumer nhận
processedAt = thời điểm consumer hoàn thành
~~~

Không ép tất cả về một timestamp nếu nghiệp vụ cần đo queue latency hoặc replay. Event đến muộn không làm thay đổi occurredAt.

### 7.3. Event snapshot khác reference tới entity

Không làm như sau:

~~~java
// SAI về thiết kế snapshot: OrderEntity là JPA entity mutable.
public record OrderPlaced(OrderEntity order) {}
~~~

Một event kiểu này dễ gặp:

- Entity bị chỉnh sửa sau publish.
- Listener chạy async sau khi persistence context đóng và gặp lazy-loading error.
- Event serialize sai hoặc vô tình lộ dữ liệu không cần thiết.
- Trạng thái entity tại thời điểm listener xử lý khác trạng thái lúc event xảy ra.
- Coupling giữa event contract và implementation ORM.

Thay vào đó:

~~~java
// Đúng hướng: snapshot dữ liệu tối thiểu, bất biến.
public record OrderPlaced(
        String eventId,
        long orderId,
        Instant occurredAt,
        List<OrderLine> lines
) {
    public OrderPlaced {
        lines = List.copyOf(lines);
    }
}
~~~

Khi cần một dữ liệu có thể đổi liên tục, cân nhắc **chỉ truyền ID và version**, sau đó consumer có chủ đích đọc state mới từ repository. Nhưng cần hiểu rằng đó là mô hình khác: event không còn là full snapshot, và dữ liệu đọc lại có thể không giống lúc sự kiện xảy ra.

## 8. Domain event và integration event

Không phải mọi event nội bộ đều phải biến thành message giữa các service.

### Domain event nội bộ

- Dùng trong cùng ApplicationContext hoặc module.
- Có thể chứa các value objects nội bộ phù hợp.
- Có thể chỉ quan trọng trong transaction/lifecycle hiện tại.
- `@EventListener` và `ApplicationEventPublisher` đủ cho tình huống đơn giản.

### Integration event bên ngoài

- Cần hợp đồng schema/version rõ.
- Chỉ chứa dữ liệu phải trao đổi giữa các hệ thống.
- Không phụ thuộc trực tiếp JPA entity hoặc Java class nội bộ khó tương thích.
- Cần payload serialization, validation, security và lựa chọn transport.
- Khi quan trọng về độ bền, cần broker/outbox/retry/idempotency.

Một event nội bộ có thể được **map thành integration event record riêng**:

~~~java
// Snippet, không thuộc ví dụ Maven độc lập.
public record OrderPlacedIntegrationV1(
        String eventId,
        String orderId,
        String occurredAt,
        List<LineV1> lines,
        int schemaVersion
) {
    public OrderPlacedIntegrationV1 {
        lines = List.copyOf(lines);
    }
}

public record LineV1(String sku, int quantity) {}
~~~

Ở đây `occurredAt` dạng ISO-8601 string có thể thuận tiện cho contract JSON theo yêu cầu hệ thống ngoài; `Instant` cũng hợp lệ nếu bộ serializer được cấu hình rõ. Đừng nhầm lựa chọn biểu diễn wire format với bản chất immutable của record.

### 8.1. Độ bền không đến từ record

Nếu chỉ publish một record vào Spring Application Events, không có durable persistence mặc định. Với transaction quan trọng, lưu **outbox record trong cùng transaction với thay đổi nghiệp vụ**, rồi relay sang broker. Một `@TransactionalEventListener(AFTER_COMMIT)` giúp quyết định lúc callback chạy nhưng vẫn có khoảng trống crash giữa commit và xử lý xong.

Nếu event record được gửi sang Kafka/RabbitMQ, mỗi consumer vẫn phải hỗ trợ **at-least-once delivery và idempotency** nếu broker có thể giao lại.

## 9. `@Async` và record: an toàn hơn khi chuyển thread

Mục đích lớn của immutable event là giảm race do publisher và listener nhìn cùng một object mutable.

~~~text
Publisher thread
    |
    +-- tạo OrderPlaced record có snapshot lines
    +-- publishEvent(record)
    |       +-- @Async listener được schedule
    |
    +-- sửa inputLines của publisher
    |
Worker thread
    |
    +-- đọc record.lines() -> vẫn là snapshot tại lúc tạo
~~~

Một listener minh họa:

~~~java
// Snippet trong bean, cần @EnableAsync và executor phù hợp.
@Async("eventExecutor")
@EventListener
public void handle(OrderPlaced event) {
    auditService.save(event.eventId(), event.lines());
}
~~~

Vì record chứa dữ liệu đã snapshot, việc caller chỉnh sửa `inputLines` sau publish không làm dữ liệu event đổi. Nhưng vẫn cần lưu ý:

- `record` không làm listener thread-safe nếu **bean listener tự giữ mutable state** không được đồng bộ.
- `@Async` không tự truyền transaction/MDC/SecurityContext/ThreadLocal.
- `@Async` không cung cấp retry bền vững, không bảo đảm event sẽ hoàn thành khi JVM crash.
- Các components của event phải thật sự ổn định; `List.copyOf` của mutable elements chưa đủ.
- Nếu listener thay đổi external business state, cần idempotency và error handling riêng.

Immutable payload hỗ trợ **an toàn dữ liệu**, không giải quyết mọi yêu cầu concurrency/delivery.

## 10. Transaction boundaries: tạo record khi nào?

Một use case đặt hàng có thể viết:

~~~java
// Snippet minh họa trong Spring-managed application service.
@Transactional
public void place(CreateOrder command) {
    Order order = repository.save(Order.createFrom(command));

    OrderPlaced event = new OrderPlaced(
        eventIdGenerator.newId(),
        order.id(),
        clock.instant(),
        order.snapshotLines(),
        Map.of("source", "checkout"));

    publisher.publishEvent(event);
}
~~~

Đây là **minh họa**; các API Order/repository/clock là giả định của ứng dụng, không phải một chương trình độc lập. Event phải được tạo từ state nghiệp vụ đã được xác nhận; tránh publish rồi mới biết đơn hàng thiếu dòng hoặc vi phạm invariant.

### Publish trước commit

Với `@EventListener` đồng bộ mặc định, listener được gọi ngay khi publish, có thể trong cùng thread/transaction nguồn. Nếu listener gửi email hoặc gọi API ngoài, side effect ấy có thể xảy ra dù transaction sau đó rollback.

### Publish sau commit

`@TransactionalEventListener(phase = AFTER_COMMIT)` có thể trì hoãn callback cho tới sau commit. Điều này giúp tránh một loại lỗi consistency, nhưng **không lưu record event bền vững**. Nếu process chết sau commit và trước callback, không có queue mặc định phát lại.

### Nếu cần tính tin cậy cao

Ghi bản ghi outbox chứa `eventId`, `eventType`, `schemaVersion` và payload đã serialize **trong cùng local transaction** với order state. Sau commit, một relay độc lập gửi đi và retry. Consumer phải idempotent vì relay/broker có thể phát lại.

Một immutable record giúp **serialize một snapshot nhất quán**, nhưng không thay thế database transaction hoặc broker.

## 11. Serialization: những gì Spring Context không làm giúp bạn

Một `publisher.publishEvent(record)` trong Spring Context **không yêu cầu JSON serializer**. Framework có thể wrap object bằng `PayloadApplicationEvent` và dispatch đến method phù hợp trong JVM.

Khi gửi record qua REST/Kafka/RabbitMQ, bạn cần tự xác định:

1. **Wire format**: JSON, Avro, Protobuf, schema registry...
2. **Serializer/deserializer**: phiên bản và cấu hình framework thực tế.
3. **Schema evolution**: đổi tên field, thêm field, default, bỏ field, version migration.
4. **Java time types**: `Instant` cần cách biểu diễn rõ; khi dùng Jackson cần Java Time support tương thích (ví dụ `jackson-datatype-jsr310`).
5. **Nullability**: `List.copyOf` / `Map.copyOf` từ chối null; payload cũ có thể thiếu field.
6. **Validation**: compact constructor có thể throw khi deserialize nếu dữ liệu không hợp lệ.
7. **Security**: không đưa secrets, session tokens, full JPA graph hoặc PII không cần thiết vào event.
8. **Idempotency**: serializer không tự tạo transaction hoặc chống duplicate.

Java record có thể được nhiều JSON libraries hỗ trợ, nhưng **không mặc định tuyên bố bất cứ Java record nào cũng serialize/deserialze được ở mọi phiên bản**. Kiểm thử với chính library, version, JavaTime module và schema contract của ứng dụng.

### 11.1. Evolution: thêm component sẽ thay đổi canonical constructor

Giả sử v1:

~~~java
public record CustomerRegisteredV1(
        String customerId,
        String email
) {}
~~~

v2 thêm trường:

~~~java
public record CustomerRegisteredV2(
        String customerId,
        String email,
        String locale
) {}
~~~

Hai record trên là hai Java types khác nhau. Khi thực sự thay đổi schema của cùng một integration event, consumer cũ/mới có thể không đồng thời hiểu field mới hoặc default. Đừng coi việc “thêm component vào record” là thay đổi luôn backward-compatible.

Trong internal code, mọi nơi `new CustomerRegisteredV1(...)` được biên dịch tĩnh có thể cần cập nhật nếu bạn thay đổi header của một record duy nhất. Với wire contract, quy định versioning, field optional/default và chiến lược migration bằng contract tests.

### 11.2. Đừng đưa thông tin nhạy cảm vào `toString()`

Compiler sinh `toString()` từ components. Nếu event record có password/token, vô tình log `logger.info("{}", event)` có thể tiết lộ bí mật. Một quy tắc an toàn là **không chứa secrets trong event payload**, và log các ID/fields được cho phép thay vì log toàn bộ record.

## 12. Value equality có lợi gì khi kiểm thử?

Record giảm nhiều boilerplate cho unit test:

~~~java
// Snippet trong unit test, cần JUnit assertions.
OrderPlaced actual = listenerCapturedEvent;

OrderPlaced expected = new OrderPlaced(
    "evt-100", "order-100",
    Instant.parse("2026-01-10T00:00:00Z"),
    List.of(new OrderLine("SKU-A", 2)),
    Map.of("source", "web"));

assertEquals(expected, actual);
~~~

Giả sử các record types đã import/khai báo giống ví dụ ở mục 5. Vì record equality dùng components, không cần viết `equals` cho mọi event DTO.

Nhưng cần test sâu hơn:

- Tạo từ mutable input list/map, sửa input sau khi tạo và kiểm tra event không đổi.
- Thử mutate `event.lines()`, `event.metadata()`, xác nhận `UnsupportedOperationException`.
- Tạo eventId rỗng, lines rỗng, quantity âm và xác nhận constructor từ chối.
- Với nested objects mutable, viết test thể hiện rủi ro và sửa bằng snapshot/deep copy.
- Với async listeners, kiểm tra result bằng latch/Future, không `Thread.sleep()` tùy ý.
- Với database/outbox, test business transaction rollback và event intent atomic.

### 12.1. Unit test không cần Spring

Một record đơn giản có thể được kiểm tra bằng JUnit thuần, không cần khởi tạo ApplicationContext. Phần “record immutable” và phần “Spring listener dispatch” là hai trách nhiệm tách biệt. Test constructor/copy/validation trước; integration test mới cần Spring.

### 12.2. Spring TestContext và `ApplicationEvents`

Với Spring TestContext, `@RecordApplicationEvents` và `ApplicationEvents` cho phép test ghi nhận events trong phạm vi test method. Sau khi gọi service, có thể lọc theo payload type:

~~~java
// Snippet trong @SpringJUnitConfig / @RecordApplicationEvents test.
@Test
void recordsOrderPlaced(ApplicationEvents events) {
    events.clear();
    orderService.place(...); // API của ứng dụng.

    List<OrderPlaced> actual =
        events.stream(OrderPlaced.class).toList();
    assertEquals(1, actual.size());
}
~~~

`ApplicationEvents.stream(OrderPlaced.class)` có thể trả record payload dù Spring đã wrap nó trong `PayloadApplicationEvent`. Nhưng việc event được ghi nhận **không chứng minh** callback `@Async` đã hoàn tất hoặc integration message đã tới broker.

## 13. Đặt record tại đúng tầng kiến trúc

Một cấu trúc package gợi ý:

~~~text
com.example.orders
├── application
│   └── OrderApplicationService.java
├── domain
│   ├── Order.java
│   └── events
│       ├── OrderPlaced.java
│       └── OrderLine.java
└── integration
    ├── OrderPlacedIntegrationV1.java
    └── OrderEventOutboxWriter.java
~~~

Domain event record có thể có những value objects nội bộ; integration record nên dùng DTO schema ổn định, không tham chiếu trực tiếp entities/ORM/proxy. Chọn vị trí theo ownership và dependency direction của dự án, không bắt buộc dùng cấu trúc này cho mọi ứng dụng.

### Domain fact khác command

`OrderPlaced` nghĩa là việc đặt hàng đã xảy ra; `PlaceOrder` là **yêu cầu thực hiện** đặt hàng. Đây là hai ý nghĩa khác nhau:

~~~text
PlaceOrder command
    |
    +-- validate + execute business operation
    +-- OrderPlaced event
    |
    +-- listeners react
~~~

Nếu một record tên `OrderPlaced` thật ra là yêu cầu để bắt đầu đặt đơn, người đọc và consumer sẽ dễ hiểu sai thời điểm và idempotency. Dùng past-tense event names cho fact, imperative names cho commands.

### Event ownership và evolution

Một module nên sở hữu contract của event do nó phát. Consumer không nên yêu cầu producer đưa cả object repository/JPA entity vào payload. Hãy giữ event fields tối thiểu, document invariants và có contract tests khi externalize.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| “Record là immutable sâu” | Nested mutable fields vẫn đổi | Dùng immutable components hoặc deep copy |
| Chỉ dùng `Collections.unmodifiableList(input)` | Có thể chỉ là **view**; mutation từ input vẫn hiện | `List.copyOf(input)` hoặc bản sao độc lập |
| Dùng `List.copyOf` cho `List<MutableEntity>` | Element vẫn mutable | Map sang `List<ImmutableLine>` |
| Record chứa `byte[]` và trả accessor mặc định | Caller sửa nội dung mảng | Clone hai chiều hoặc chọn kiểu dữ liệu khác |
| Record chứa JPA entity/session | Lazy-loading, mutation, coupling | Snapshot scalar/value fields |
| Cho rằng record phải extends `ApplicationEvent` | Không compile do record đã extends Record | Publish record như POJO |
| Cho rằng publishEvent yêu cầu Jackson JSON | Nhầm dispatch JVM với serialization | Chỉ cấu hình serializer khi qua transport |
| Dùng event record làm nơi gọi database | Side effect trong constructor, khó test | Giữ constructor validation đơn giản |
| Thay đổi toàn bộ record khi muốn cập nhật state | Nhầm event với entity | Event là snapshot, state update thuộc aggregate |
| Dùng `==` để so hai event cùng dữ liệu | False vì khác instance | Record `equals` hoặc ID theo mục đích |
| Dùng `equals` toàn payload để chống duplicate | Cùng eventId nhưng payload drift không bị phát hiện đúng | Dedup theo eventId và kiểm tra conflict |
| Tạo eventId mới ở mỗi retry | Consumer coi là event mới | Giữ ID gốc qua redelivery |
| Cho rằng record tự có retry/durable delivery | Mất event khi process crash | Outbox/broker nếu bắt buộc |
| Cho rằng `@Async` tự thread-safe toàn listener | Bean mutable state vẫn có race | Đồng bộ hóa/state management riêng |
| Log `toString()` của record chứa secrets | Rò dữ liệu | Không đưa secrets vào event; log có chọn lọc |
| Thêm component record mà không xét schema | Consumer cũ lỗi deserialize | Versioning + contract tests |
| Đếm số event bằng tổng framework event stream | Test bị nhiễu lifecycle events | Lọc theo typed payload class |

## 15. Checklist trước khi đưa vào ứng dụng

1. Event có tên diễn đạt **fact đã xảy ra** không?
2. Mọi components có ý nghĩa nghiệp vụ, kiểu và invariant rõ ràng không?
3. Có eventId ổn định, aggregateId và occurredAt khi cần không?
4. Record có chứa array, Date, List/Map mutable, JPA entity hoặc JsonNode có thể đổi không?
5. Nếu có List/Map, compact constructor đã defensive-copy chưa?
6. Các elements/values của collections có **thật sự immutable** không?
7. Constructor có validate null/blank/range và không thực hiện side effect không?
8. Listener nhận đúng record payload qua `@EventListener` không?
9. Khi `@Async`, context và state của listener được quản lý riêng đúng không?
10. Transaction/AFTER_COMMIT/outbox có phù hợp với yêu cầu consistency và durability không?
11. Nếu externalize, schema/version/serialization và retention/bảo mật đã xác định chưa?
12. Test đã chứng minh snapshot không đổi sau mutation của input, equality đúng và event dispatch hoạt động chưa?

**Kết luận:** Java `record` là cách diễn đạt rất phù hợp cho event payload trong Spring Application Events vì gọn, typed, có value equality và các components final. Nhưng record chỉ **bất biến nông**: hãy defensive-copy collections, chọn nested immutable value objects, validate trong compact constructor và snapshot dữ liệu nghiệp vụ đúng thời điểm. Spring nhận record trực tiếp qua `publishEvent(Object)` và `@EventListener`; khi cần async, transaction hoặc integration messaging, hãy thiết kế những ranh giới đó **riêng**, không gán cho record những bảo đảm mà Java/Spring không cung cấp.

## Tài liệu chính thức

- Java SE 17 — Record Classes, canonical/compact constructor: https://docs.oracle.com/en/java/javase/17/language/records.html
- Java SE 17 — Creating Unmodifiable Lists, Sets, and Maps: https://docs.oracle.com/en/java/javase/17/core/creating-immutable-lists-sets-and-maps.html
- Java SE 17 — Collection, unmodifiable vs immutable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html
- Spring Framework 6.2 — ApplicationContext events, payloads, async listener: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2.12 — ApplicationEventPublisher: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2.12 — PayloadApplicationEvent: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/PayloadApplicationEvent.html
- Spring Framework 6.2 — Transaction-bound events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html

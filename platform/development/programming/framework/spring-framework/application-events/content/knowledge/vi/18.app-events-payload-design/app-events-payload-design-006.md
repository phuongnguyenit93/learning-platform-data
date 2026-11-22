# Payload bất biến bằng record trong Spring Framework Application Events

## 1. Vì sao nên dùng payload bất biến?

Khi một service công bố sự kiện `OrderCreated`, các listener có thể xử lý audit, gửi email, cập nhật thống kê hoặc đồng bộ dữ liệu. Payload là **bản mô tả sự việc đã xảy ra**, không nên âm thầm thay đổi trong lúc listener đọc nó.

Ví dụ một lỗi thường gặp:

```java
List<OrderLine> draftLines = new ArrayList<>();
draftLines.add(new OrderLine("SKU-7", 2, new BigDecimal("75.00")));

publisher.publishEvent(new OrderCreatedEvent(draftLines));

// Sau khi publish, nơi phát tiếp tục thay đổi danh sách.
draftLines.clear();
```

Đây là đoạn mô phỏng rủi ro, không phải mã độc lập: cần định nghĩa `OrderLine` và `OrderCreatedEvent`. Nếu event giữ **cùng tham chiếu tới danh sách có thể sửa**, listener xử lý bất đồng bộ có thể thấy một danh sách rỗng dù tại thời điểm publish đơn hàng có một dòng. Ngay cả trong xử lý đồng bộ, listener này có thể làm hỏng dữ liệu mà listener khác sắp dùng.

Thiết kế payload bất biến có lợi ích:

- **Nhất quán:** các listener thấy cùng dữ liệu nghiệp vụ đã được chốt khi tạo event.
- **Đơn giản hóa concurrency:** hạn chế race do cùng sửa một object từ nhiều thread.
- **Dễ kiểm thử:** có thể so sánh payload theo giá trị và dùng dữ liệu mẫu ổn định.
- **Tách trách nhiệm:** publisher tạo snapshot; listener dùng snapshot để phản ứng, không sửa sự kiện gốc.
- **Truy vết:** log/đối soát dựa vào ID và giá trị của sự kiện ổn định hơn.

Java 17 hỗ trợ `record`, rất phù hợp để biểu diễn nhiều loại payload theo giá trị. Tuy nhiên, **record chỉ cung cấp tính bất biến nông (shallow immutability)**: nếu chứa `List`, `Map`, mảng hoặc object mutable, phải tự bảo vệ chúng.

## 2. Record Java 17: kiểu dữ liệu mang giá trị

Một payload nhỏ có thể viết:

```java
public record OrderCreated(
        String eventId,
        String orderId,
        Instant occurredAt
) {}
```

Lớp record trên có:

- Ba component: `eventId`, `orderId`, `occurredAt`.
- Constructor chuẩn tương ứng các component.
- Accessor mang tên `eventId()`, `orderId()` và `occurredAt()`.
- Cơ chế `equals()`, `hashCode()` và `toString()` do compiler cung cấp nếu không tự định nghĩa.
- Các field component `private final`; không có setter cho chúng.

Cách dùng:

```java
OrderCreated event = new OrderCreated(
        "evt-101",
        "ORD-42",
        Instant.parse("2026-11-01T08:00:00Z")
);
System.out.println(event.orderId()); // ORD-42
```

Mã minh họa cần import `java.time.Instant` và khai báo record `OrderCreated` trong project.

**Đặc điểm quan trọng của record:**

1. Record class là `final`; không thể extends một class khác như `ApplicationEvent`. Nó kế thừa `java.lang.Record`.
2. Record có thể `implements` interface.
3. Không thể thêm instance field ngoài các component record; có thể khai báo static field, method, constructor và kiểm tra bất biến.
4. `final` ngăn việc gán lại **tham chiếu field**, không làm cho object được tham chiếu trở nên bất biến.
5. Giá trị các component tham gia vào ngữ nghĩa `equals/hashCode`; nếu component bị biến đổi gián tiếp, việc dùng record làm key của map/set sẽ rất nguy hiểm.

Với sự kiện ứng dụng, record là **value-oriented data carrier** chứ không phải entity JPA có vòng đời và identity mutable.

## 3. Vì sao record phù hợp trực tiếp với Spring Application Events?

Kể từ Spring Framework 4.2, `ApplicationEventPublisher` cho phép phát **bất kỳ object không null**, không bắt buộc subclass `ApplicationEvent`. Vì record không thể extends `ApplicationEvent`, đây chính là con đường thích hợp:

```java
publisher.publishEvent(
        new OrderCreated(
                "evt-101",
                "ORD-42",
                Instant.parse("2026-11-01T08:00:00Z")
        )
);
```

Khi nhận một object không phải `ApplicationEvent`, Spring bọc nó thành `PayloadApplicationEvent<T>` để đưa qua hạ tầng event. Với annotation-based listener, Spring có thể trích payload và chuyển trực tiếp đến phương thức có tham số cùng kiểu:

```java
@EventListener
public void onOrderCreated(OrderCreated event) {
    System.out.println("Received: " + event.orderId());
}
```

Không cần khai báo `onOrderCreated(PayloadApplicationEvent<OrderCreated>)` chỉ để dùng `@EventListener`. Spring adapter xử lý việc bọc và mở payload cho kiểu tham số của phương thức.

Cần phân biệt hai lớp:

| Lớp/đối tượng | Vai trò |
| --- | --- |
| `OrderCreated` record | Snapshot nghiệp vụ mà ứng dụng định nghĩa |
| `PayloadApplicationEvent<OrderCreated>` | Wrapper của Spring khi event được phát bằng một POJO |
| `@EventListener(OrderCreated)` | Cách đăng ký listener quan tâm tới payload trực tiếp |
| `ApplicationListener<E>` | Interface với `E extends ApplicationEvent`; không thể dùng `E=OrderCreated` trực tiếp nếu record không kế thừa `ApplicationEvent` |

Nếu dùng `ApplicationListener` theo interface, có thể nhận `PayloadApplicationEvent<OrderCreated>` hoặc dùng tiện ích `ApplicationListener.forPayload(...)` (khi đăng ký phù hợp). Đối với nhiều ứng dụng, một method `@EventListener` nhận record đơn giản và dễ hiểu hơn.

**Không nhầm với tính bền vững:** Spring Application Events theo cơ chế in-process thông thường không phải message broker và không tự lưu sự kiện vào database. Payload bất biến không cung cấp retry, durability hay exactly-once.

## 4. Tính bất biến nông và bất biến sâu

Xét record:

```java
public record OrderCreated(String orderId, List<String> skuCodes) {}
```

Điểm tốt: mã khác không thể gọi `event.skuCodes = otherList`.

Vấn đề: `event.skuCodes()` trả về **tham chiếu danh sách** được lưu trong field. Nếu ta truyền `ArrayList` vào constructor, cả nơi phát và nơi nhận đều có thể thay đổi nội dung danh sách:

```java
List<String> draft = new ArrayList<>(List.of("SKU-7"));
OrderCreated event = new OrderCreated("ORD-42", draft);

draft.add("SKU-8");
event.skuCodes().clear();
```

Không có setter nhưng dữ liệu event vẫn biến đổi. Đây không phải “immutable event” theo nghĩa ổn định về giá trị.

### 4.1. Sao chép phòng vệ bằng List.copyOf

Một **compact constructor** của record có thể chuẩn hóa component đầu vào:

```java
public record OrderCreated(
        String orderId,
        List<String> skuCodes
) {
    public OrderCreated {
        Objects.requireNonNull(orderId, "orderId");
        skuCodes = List.copyOf(
                Objects.requireNonNull(skuCodes, "skuCodes"));
    }
}
```

Cần import `java.util.List` và `java.util.Objects`.

Khi khởi tạo record, tham số `skuCodes` được thay bằng danh sách bất biến; Java tự gán các component từ tham số khi compact constructor kết thúc. Không được gán trực tiếp `this.skuCodes = ...` bên trong compact constructor.

Các tính chất chính của `List.copyOf(...)`:

- Tạo một danh sách **không thể sửa qua API List** chứa các phần tử ở thời điểm snapshot.
- Thay đổi sau đó đối với danh sách mutable đầu vào không làm đổi danh sách snapshot.
- Không cho phép phần tử `null`; sẽ ném `NullPointerException` nếu chứa null.
- Nếu nguồn đã là một danh sách immutable phù hợp, implementation có thể tái sử dụng nó; không nên dựa vào identity tham chiếu.
- **Không deep copy phần tử**. Một phần tử mutable vẫn có thể bị thay đổi dù bản thân cấu trúc list không đổi.

### 4.2. So sánh với Collections.unmodifiableList

`Collections.unmodifiableList(draft)` thường tạo **view không thể sửa trực tiếp** trên danh sách `draft`, chứ không tạo snapshot tách biệt. Một nơi khác vẫn có reference tới `draft` thì có thể sửa nó, và view thấy các sửa đổi đó.

```java
List<String> draft = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(draft);
List<String> snapshot = List.copyOf(draft);

draft.add("B");

System.out.println(view);     // [A, B]
System.out.println(snapshot); // [A]
```

Đoạn này có thể chạy với import các kiểu Java Collections tương ứng. Đây là lý do `List.copyOf` rất phù hợp khi tạo event payload: snapshot **tách khỏi sự thay đổi cấu trúc của nguồn mutable**.

### 4.3. List.copyOf không giải quyết nested mutability

```java
public final class MutableLine {
    public String sku;
    public int quantity;
}

// Dù lines là List.copyOf(original),
// từng MutableLine vẫn có thể bị đổi quantity.
```

Với một danh sách `MutableLine`, `List.copyOf` không tạo bản sao từng phần tử; cùng object `MutableLine` vẫn được chia sẻ. Muốn payload thật sự ổn định, có thể:

- Biểu diễn từng phần tử cũng bằng record mà **tất cả các component bên trong đều immutable**.
- Sao chép từng object mutable thành snapshot immutable trước khi đưa vào list.
- Dùng kiểu value có sẵn như `String`, `UUID`, `Instant`, `BigDecimal` thay vì giữ entity đang được cập nhật.
- Tránh đưa `byte[]`, `Date`, mutable map hoặc entity ORM trực tiếp vào event.

Khi một field là `List<OrderLine>` và `OrderLine` record chỉ chứa `String`, `int`, `BigDecimal`, tính bất biến sâu sẽ dễ đạt hơn nhiều.

## 5. Ví dụ đầy đủ Java 17 + Spring 6.2: snapshot record không đổi sau publish

Chương trình minh họa:

1. Tạo bản nháp danh sách chi tiết đơn hàng từ `ArrayList`.
2. Tạo `OrderCreated` record với compact constructor gọi `List.copyOf`.
3. Sửa danh sách bản nháp; payload record **không thay đổi**.
4. Thử sửa `payload.lines()` và nhận `UnsupportedOperationException`.
5. Phát record trực tiếp qua `ApplicationContext.publishEvent(...)`.
6. `@EventListener` nhận payload record và tính tổng từ snapshot.

Ví dụ không dùng database, Spring Boot, web server hay thread pool, vì mục tiêu ở đây là **tính ổn định dữ liệu payload**.

### 5.1. Cấu trúc dự án

```text
immutable-payload-event/
├── pom.xml
└── src/main/java/example/ImmutablePayloadDemo.java
```

### 5.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>immutable-payload-event</artifactId>
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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.ImmutablePayloadDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. Tệp src/main/java/example/ImmutablePayloadDemo.java

```java
package example;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ImmutablePayloadDemo {

    // Record con chỉ chứa String, int và BigDecimal immutable.
    public record OrderLine(String sku,
                            int quantity,
                            BigDecimal unitPrice) {
        public OrderLine {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");

            if (sku.isBlank()) {
                throw new IllegalArgumentException("sku is blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "unitPrice cannot be negative");
            }
        }
    }

    public record OrderCreated(
            String eventId,
            String orderId,
            Instant occurredAt,
            List<OrderLine> lines) {

        // Compact constructor: validate + snapshot đầu vào.
        public OrderCreated {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(occurredAt, "occurredAt");

            if (eventId.isBlank() || orderId.isBlank()) {
                throw new IllegalArgumentException(
                        "eventId/orderId cannot be blank");
            }

            lines = List.copyOf(
                    Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty()) {
                throw new IllegalArgumentException(
                        "Order must have at least one line");
            }
        }
    }

    public static final class Evidence {
        private final AtomicReference<OrderCreated> received =
                new AtomicReference<>();

        public OrderCreated received() {
            return Objects.requireNonNull(
                    received.get(), "Listener did not receive event");
        }
    }

    public static class OrderListener {
        private final Evidence evidence;

        public OrderListener(Evidence evidence) {
            this.evidence = evidence;
        }

        @EventListener
        public void onCreated(OrderCreated event) {
            evidence.received.set(event);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Evidence evidence() {
            return new Evidence();
        }

        @Bean
        public OrderListener orderListener(Evidence evidence) {
            return new OrderListener(evidence);
        }
    }

    public static void main(String[] args) {
        List<OrderLine> draft = new ArrayList<>();
        draft.add(new OrderLine(
                "SKU-7", 2, new BigDecimal("75.00")));

        Instant timestamp =
                Instant.parse("2026-11-01T08:00:00Z");

        OrderCreated event = new OrderCreated(
                "evt-101", "ORD-42", timestamp, draft);

        // Nơi tạo vẫn có thể sửa draft; event đã snapshot.
        draft.add(new OrderLine(
                "SKU-8", 1, new BigDecimal("10.00")));

        boolean blocked = false;
        try {
            event.lines().add(new OrderLine(
                    "SKU-9", 1, new BigDecimal("20.00")));
        } catch (UnsupportedOperationException expected) {
            blocked = true;
        }

        // Record hỗ trợ equals theo giá trị các component.
        OrderCreated sameValue = new OrderCreated(
                "evt-101", "ORD-42", timestamp,
                List.of(new OrderLine(
                        "SKU-7", 2, new BigDecimal("75.00"))));

        System.out.println("Draft line count: " + draft.size());
        System.out.println("Event line count: " + event.lines().size());
        System.out.println("Mutation rejected: " + blocked);
        System.out.println("Equal payloads: " + event.equals(sameValue));

        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            // Record là POJO payload, không extends ApplicationEvent.
            context.publishEvent(event);

            OrderCreated received =
                    context.getBean(Evidence.class).received();

            BigDecimal total = received.lines().stream()
                    .map(line -> line.unitPrice().multiply(
                            BigDecimal.valueOf(line.quantity())))
                    .reduce(BigDecimal.ZERO, BigDecimal::add);

            System.out.println(
                    "Listener order: " + received.orderId());
            System.out.println(
                    "Listener total: " + total.toPlainString());
        }
    }
}
```

### 5.4. Chạy và kết quả

Từ thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

**Sáu dòng do chương trình in** trong cấu hình mặc định, không tính log của Maven/Spring nếu có:

```text
Draft line count: 2
Event line count: 1
Mutation rejected: true
Equal payloads: true
Listener order: ORD-42
Listener total: 150.00
```

**Vì sao kết quả đúng?**

- `draft` có hai dòng sau khi được thêm `SKU-8`.
- `OrderCreated` đã gọi `List.copyOf(draft)` khi được tạo, nên `event.lines()` chỉ chứa dòng `SKU-7` ban đầu.
- Thử gọi `event.lines().add(...)` ném `UnsupportedOperationException`; chương trình bắt lỗi có chủ đích và in `true`.
- Hai instance `OrderCreated` có cùng tất cả component, bao gồm `OrderLine` và `BigDecimal("75.00")`, nên `equals` trả về `true`.
- Spring nhận record qua `publishEvent(Object)` và chuyển nó tới phương thức `@EventListener` có tham số `OrderCreated`.
- Listener quan sát một dòng với `quantity=2` và `unitPrice=75.00`; `BigDecimal` cho tổng `150.00`, không có sai số kiểu `double`.
- Ví dụ dùng multicaster đồng bộ mặc định. Ngay sau `context.publishEvent(event)`, listener đã lưu record vào `Evidence`, vì vậy chương trình có thể đọc kết quả ngay. Với listener async thì phải đợi bằng latch/future thích hợp.

**Lưu ý QA:** tên tệp khớp `public class ImmutablePayloadDemo` và lệnh Maven chỉ chạy một `main`. Ví dụ dùng record của Java 17, Spring Framework 6.2.0; không cần Spring Boot. Các object của event đều bất biến theo thiết kế hiện tại, bởi `OrderLine` không có component mutable và danh sách đã được snapshot.

## 6. Cách xây compact constructor đúng

Một record cho phép viết **compact canonical constructor**:

```java
public record UserRegistered(String userId, String email) {
    public UserRegistered {
        Objects.requireNonNull(userId, "userId");
        Objects.requireNonNull(email, "email");

        userId = userId.trim();
        email = email.trim().toLowerCase(Locale.ROOT);

        if (userId.isBlank() || email.isBlank()) {
            throw new IllegalArgumentException(
                    "userId/email must not be blank");
        }
    }
}
```

Đây là đoạn minh họa độc lập về kiểu record, cần import `Objects` và `Locale`. Sau compact constructor, Java gán **giá trị tham số đã chuẩn hóa** vào component tương ứng. Có thể validate và chuẩn hóa trong constructor, thay vì cho phép caller tạo record không hợp lệ rồi phải kiểm tra lại ở mọi listener.

Một số quy tắc:

1. Không gọi setter vì record không có setter mặc định.
2. Không gán trực tiếp `this.field` trong compact constructor; chỉ thao tác trên tham số hoặc gọi helper thích hợp.
3. Đừng biến constructor thành nơi làm I/O, truy cập database hay gọi network. Constructor nên kiểm tra bất biến và tạo snapshot nhanh, có kết quả xác định.
4. Nếu payload có validation annotation như `@NotBlank`, việc khai báo annotation **không tự động** chạy Bean Validation khi gọi `new Record(...)`. Cần tích hợp validator nếu muốn kiểm tra theo cơ chế đó.
5. Không trộn validation event với nghiệp vụ có trạng thái. Ví dụ “đơn hàng có được thanh toán trong giờ này không?” thuộc service/domain logic, không nên cố nhét tất cả vào record constructor.

**Chú ý:** chuẩn hóa email bằng `toLowerCase` trong thực tế cần cân nhắc quy tắc nghiệp vụ, đặc biệt local-part của email. Đoạn trên chỉ minh họa kỹ thuật normalize input; không phải đặc tả chuẩn hóa email dùng cho mọi hệ thống.

## 7. Với array, byte[] và dữ liệu nhị phân thì sao?

Một record chứa mảng như sau **không an toàn về bất biến**:

```java
public record FileUploaded(String fileId, byte[] checksum) {}
```

Các field của record là final, nhưng cả nơi gọi constructor và nơi gọi accessor `checksum()` đều có thể lấy tham chiếu tới cùng mảng rồi sửa phần tử. Cần sao chép cả lúc **nhận vào** lẫn lúc **trả ra**:

```java
public record FileUploaded(String fileId, byte[] checksum) {
    public FileUploaded {
        Objects.requireNonNull(fileId, "fileId");
        checksum = Objects.requireNonNull(
                checksum, "checksum").clone();
    }

    @Override
    public byte[] checksum() {
        return checksum.clone();
    }
}
```

Đoạn này cần import `Objects`. Nó ngăn thay đổi từ bên ngoài đi qua mảng trả về accessor. Nhưng còn một điểm: `equals/hashCode` được tạo mặc định của record **không so sánh nội dung mảng như `Arrays.equals`**; nó sử dụng ngữ nghĩa equality theo reference của mảng. Hai payload có cùng bytes nhưng hai mảng khác nhau có thể không `equals`.

Vì vậy, nếu dữ liệu nhị phân đóng vai trò value quan trọng, cân nhắc:

- Một wrapper immutable chuyên dụng với `Arrays.equals`/`Arrays.hashCode`.
- Một chuỗi digest chuẩn hóa (như mã hex của hash) thay cho `byte[]` khi phù hợp.
- Tự định nghĩa `equals/hashCode` cẩn thận nếu record bắt buộc phải mang mảng.

Sao chép mảng bảo vệ nội dung, **không tự sửa** toàn bộ ngữ nghĩa equality của mảng.

## 8. Collection nâng cao: Map, Set và object lồng nhau

Tùy event, có thể dùng `Map.copyOf`, `Set.copyOf` và `List.copyOf`:

```java
public record ProfileChanged(
        String profileId,
        Map<String, String> fields,
        Set<String> tags
) {
    public ProfileChanged {
        Objects.requireNonNull(profileId, "profileId");
        fields = Map.copyOf(
                Objects.requireNonNull(fields, "fields"));
        tags = Set.copyOf(
                Objects.requireNonNull(tags, "tags"));
    }
}
```

Cần import `Map`, `Set` và `Objects`. Những `copyOf` tạo cấu trúc collection không thể sửa qua API bình thường, bảo vệ khỏi thay đổi cấu trúc của collection nguồn mutable. Tuy nhiên:

- Value trong `Map<K,V>` nếu là object mutable vẫn có thể bị thay đổi.
- `Set.copyOf` không nên được dùng để giả định thứ tự lặp ổn định. Nếu thứ tự có ý nghĩa, cần mô hình rõ ràng, có thể dùng `List` đã được chuẩn hóa và snapshot.
- `Map.copyOf` và `Set.copyOf` không chấp nhận null key/value hoặc element; hãy validate dữ liệu đầu vào.
- Copy collection có chi phí bộ nhớ/CPU theo số phần tử. Với payload quá lớn, nên gửi định danh và truy vấn dữ liệu snapshot theo version từ lưu trữ bền vững thay vì sao chép toàn bộ object graph.
- Nếu một record lồng một record khác nhưng record bên trong giữ entity mutable, payload tổng thể **vẫn không immutable**. Phải xét từ lá dữ liệu vào trong.

Một phương án an toàn với dữ liệu lồng nhau là mapping từ entity mutable sang **snapshot DTO** bằng record:

```java
public record CustomerSnapshot(
        String customerId,
        String displayName
) {}

public record OrderSnapshot(
        String orderId,
        CustomerSnapshot customer,
        List<OrderLine> lines
) {
    public OrderSnapshot {
        lines = List.copyOf(lines);
    }
}
```

Ví dụ này giả định `OrderLine` là record immutable như mục 5. Đây là snippet type model; không phải chương trình độc lập nếu chưa có tất cả định nghĩa/import.

## 9. Thiết kế trường của event theo nghiệp vụ

Payload nên chứa **sự thật bất biến** tại thời điểm phát event, không phải một object để listener tùy ý cập nhật.

Một record thường cần:

| Trường | Vai trò | Gợi ý |
| --- | --- | --- |
| `eventId` | Định danh một occurrence của sự kiện | Ổn định khi retry/replay; có thể dùng UUID |
| `aggregateId` / `orderId` | Đối tượng nghiệp vụ liên quan | Chuỗi/UUID bất biến |
| `occurredAt` | Thời điểm sự kiện thực sự xảy ra | `Instant`, không dùng timezone cục bộ không rõ |
| `eventType` hoặc type của record | Ý nghĩa sự kiện | Ưu tiên tên class có nghĩa như `OrderCreated` |
| `version` / `aggregateVersion` | Phân biệt thay đổi theo thời gian | Dùng khi consumer cần kiểm soát thứ tự |
| Snapshot trường thiết yếu | Đủ thông tin cho handler | Chỉ đưa phần cần dùng, tránh object graph khổng lồ |
| `correlationId` | Liên hệ một request/workflow | Hữu ích cho tracing, không phải khóa idempotency mặc định |

**`eventId` không nên đổi khi retry cùng một event**. Nếu mỗi lần retry tạo một ID mới, listener muốn chống trùng theo `eventId` không nhận biết đó là cùng sự kiện.

Tách `eventId` khỏi `orderId`: một đơn có thể trải qua nhiều event hợp lệ (`OrderCreated`, `OrderPaid`, `OrderCancelled`), còn `eventId` định danh một event cụ thể. Cùng `orderId` không đồng nghĩa các event đó trùng nhau.

`occurredAt` nên biểu diễn thời điểm domain event được tạo, không thay đổi tùy thời gian listener chạy. Tránh `LocalDateTime` không timezone nếu hệ thống cần so sánh trên nhiều khu vực; `Instant` là lựa chọn đơn giản cho timestamp UTC.

### Không mang secrets và object graph không cần thiết

`record.toString()` được sinh tự động và thường bao gồm giá trị component. Nếu record chứa access token, mật khẩu, số thẻ hay thông tin cá nhân nhạy cảm, một câu log `logger.info("event={}", event)` có thể làm rò rỉ dữ liệu.

Chỉ đưa thông tin cần thiết vào payload; với nội dung nhạy cảm, dùng ID hoặc dữ liệu đã giảm thiểu, kiểm soát log/serialization và chính sách truy cập. Không nghĩ rằng “immutable” đồng nghĩa với “an toàn bảo mật”.

## 10. Record, sự kiện đồng bộ và bất đồng bộ

Tính bất biến đặc biệt quan trọng khi listener chạy trên thread khác:

```java
@Async("notificationExecutor")
@EventListener
public void onCreated(OrderCreated event) {
    // Đọc snapshot event trên worker thread.
}
```

Đoạn trên cần `@EnableAsync`, bean executor `notificationExecutor` và Spring bean listener. Nó chỉ minh họa cách kết hợp, không phải phần của chương trình chạy ở mục 5.

Với thiết kế immutable thích hợp, publisher có thể tiếp tục thực hiện tác vụ khác mà không làm dữ liệu event thay đổi. Nhưng **record không tự bảo đảm mọi việc thread-safe**:

1. Record chứa reference mutable không được bảo vệ vẫn có race.
2. Listener có thể sửa database hay dịch vụ ngoài; việc đó không được “immutable hóa” bởi record.
3. Thứ tự thực thi giữa các listener async không được bảo đảm; phải xử lý ordering nếu nghiệp vụ cần.
4. Publisher không tự đợi các async listener hoàn thành; test cần `CountDownLatch`/`CompletableFuture` hoặc cơ chế chờ thích hợp.
5. Spring event in-process không được lưu bền vững qua crash. Nếu bắt buộc giao nhận, dùng outbox/broker.
6. Exception trong `@Async void` không tự truyền về publisher; cần error handler/observability phù hợp.

### Đừng phát entity mutable rồi giả định snapshot

Phản ví dụ thiết kế:

```java
@EventListener
public void onPaid(OrderPaid event) {
    event.orderEntity().setStatus("SHIPPED");
}
```

Đây là mẫu không nên dùng khi `orderEntity()` trả entity mutable. Nó vừa tạo coupling giữa listener và persistence context, vừa khiến các listener khác có thể thấy trạng thái khác với thời điểm event phát. Thay vào đó, dùng record mang `orderId`, `statusAtEvent`, `aggregateVersion` hoặc snapshot giá trị cần thiết; service xử lý sự kiện sẽ tải dữ liệu và điều phối transaction riêng nếu cần.

## 11. Record với TransactionalEventListener

Một record payload có thể dùng với `@TransactionalEventListener`:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderCreated event) {
    // Phản ứng khi transaction phát event đã commit.
}
```

Đoạn này cần import `TransactionalEventListener` và `TransactionPhase`; event phải được phát khi có transaction thật theo kiểu transaction manager đang dùng. `@TransactionalEventListener` mặc định dùng `AFTER_COMMIT`; `fallbackExecution` mặc định là `false`, nên phát ngoài transaction thường không gọi listener transaction-bound.

Payload record giúp đảm bảo listener hậu commit nhìn thấy **snapshot ban đầu** của ID, line items và timestamp ngay cả khi publisher sau đó tiếp tục cập nhật object domain. Tuy nhiên:

- `AFTER_COMMIT` không đảm bảo sự kiện không bị lặp hoặc không mất khi process crash.
- Transaction gốc đã commit; nếu listener ghi database trong callback hậu commit, cần transaction mới thích hợp (ví dụ `REQUIRES_NEW` qua proxy/`TransactionTemplate`) để đảm bảo thay đổi tiếp theo được commit.
- Với hệ thống nhiều worker hoặc retry, thêm idempotency key và unique constraint nếu tác dụng phụ không được phép trùng.
- Nếu cần **đảm bảo không mất event giữa business commit và handler**, outbox record nên được ghi **trong cùng transaction nghiệp vụ**, thay vì chỉ dựa vào listener hậu commit in-memory.

Tính bất biến payload và chính sách transaction là **hai trách nhiệm bổ sung**, không thay thế nhau.

## 12. Vì sao không nên dùng record làm JPA entity?

Một record mang dữ liệu có thể lý tưởng để làm event DTO nhưng thường **không thích hợp làm JPA entity** theo mô hình ORM entity tiêu chuẩn:

- JPA entity cần cơ chế identity và quản lý trạng thái trong persistence context.
- ORM thường cần constructor và cách truy cập/điều chỉnh state phù hợp; bản thân record final và không có setter cho component.
- Entity có quan hệ lazy/proxy và vòng đời thay đổi; event snapshot nên tách khỏi những hành vi đó.
- Một số công cụ mapping/projection có hỗ trợ record, nhưng **DTO projection** khác với việc dùng record làm entity được quản lý.

Mẫu thiết kế:

```text
OrderEntity (mutable, thuộc persistence context)
      |
      |  map sang snapshot cần thiết
      v
OrderCreated record (immutable)
      |
      |  publishEvent
      v
@EventListener(OrderCreated)
      |
      +--> Audit / metrics / notifications
```

Tránh đưa `OrderEntity` trực tiếp vào component của record vì record chỉ đóng băng **tham chiếu entity**, không đóng băng trạng thái entity. Trong một listener chạy sau transaction hoặc trên worker thread, quan hệ lazy còn có thể gây lỗi truy cập.

## 13. Tương thích dữ liệu, serialization và versioning

Record làm payload cho event nội bộ Spring **không tự động có nghĩa** rằng nó phù hợp với mọi định dạng truyền qua mạng. Khi tích hợp Kafka/RabbitMQ/HTTP:

- Serializer/deserializer cần được cấu hình để hiểu record và các type như `Instant`, `BigDecimal`.
- Nếu dùng Jackson phiên bản hiện đại, nhiều trường hợp record được hỗ trợ tốt, nhưng phải kiểm thử định dạng JSON thực tế và dependency trong dự án.
- Thêm/xóa/đổi tên một component record có thể thay đổi canonical constructor, schema payload và compatibility của consumer.
- Hai phiên bản service deploy lệch nhau có thể cần quy tắc schema evolution, default values và kiểm thử backward/forward compatibility.
- Không đưa nguyên object graph phức tạp vào event chỉ vì record hỗ trợ nested data; ưu tiên schema nhỏ, có tên trường rõ.
- Record **không tự động implements Serializable chỉ vì nó là record**. Nếu dùng Java Serialization, phải xét hợp đồng và khai báo phù hợp; với tích hợp microservice, schema/JSON/Avro/Protobuf thường là quyết định thiết kế riêng.

Khi thay đổi nội dung payload trong một hệ thống có event lưu bền vững, nên xác định version, compatibility test và cách consumer cũ xử lý trường mới. **Tính bất biến của từng instance** không đồng nghĩa với **tính bất biến của schema qua nhiều lần phát hành**.

## 14. Equals, hashCode và các bẫy giá trị

Record tạo `equals/hashCode` dựa trên component, thuận tiện để so sánh dữ liệu trong test. Nhưng ngữ nghĩa của component vẫn quan trọng:

- Hai `BigDecimal` có cùng trị số toán học nhưng khác scale, ví dụ `new BigDecimal("75.0")` và `new BigDecimal("75.00")`, **không bằng nhau theo `BigDecimal.equals`**. Record dùng ngữ nghĩa equality của component, nên cần chuẩn hóa scale nếu nghiệp vụ yêu cầu.
- Một `List` so sánh các phần tử theo thứ tự; thay đổi thứ tự các dòng có thể làm hai payload khác nhau dù tổng số tiền bằng nhau.
- Một component kiểu array so sánh theo reference, không tự so sánh nội dung.
- Một mutable object nằm trong component có thể làm `hashCode` thay đổi sau khi object đã được dùng làm key trong `HashMap`.
- Không dùng toàn bộ record payload làm khóa idempotency một cách máy móc; `eventId` ổn định và namespace consumer thường phù hợp hơn.

Ví dụ scale:

```java
BigDecimal a = new BigDecimal("75.0");
BigDecimal b = new BigDecimal("75.00");
System.out.println(a.compareTo(b) == 0); // true: cùng giá trị số
System.out.println(a.equals(b));         // false: scale khác nhau
```

Đây là đoạn Java độc lập với import `BigDecimal`. Sự khác nhau này không phải lỗi record, mà là ngữ nghĩa của kiểu dữ liệu thành phần.

## 15. Kiểm thử tính bất biến payload

Một bài test payload record không chỉ assert “không có setter”. Nên kiểm tra các tình huống:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Tạo từ một `ArrayList` rồi sửa list nguồn | `record.lines()` không đổi |
| Cố thêm/xóa qua accessor `record.lines()` | `UnsupportedOperationException` |
| List đầu vào chứa `null` | Constructor từ chối theo hợp đồng `List.copyOf` |
| Nested element mutable | Phải copy sâu hoặc dùng element immutable |
| Array/byte[] nằm trong record | Constructor và accessor đều defensive copy |
| Payload không hợp lệ | Constructor báo lỗi cho ID rỗng, quantity sai, giá âm |
| Hai snapshot cùng nội dung | `equals/hashCode` đúng theo quy tắc component |
| Phát qua Spring `publishEvent(Object)` | Listener `@EventListener(RecordType)` nhận đúng payload |
| Listener async | Không bị dữ liệu caller thay đổi trong lúc chờ |
| Event lưu/truyền qua hệ thống khác | Serialization và schema compatibility được kiểm chứng |

**Bốn test thiết yếu** có thể bắt đầu từ chương trình mục 5: kích thước list nguồn sau sửa, kích thước list trong record, việc sửa accessor bị từ chối, và listener nhận đúng tổng giá trị. Không cần dựng web server chỉ để kiểm tra loại event POJO.

Với unit test cần chứng minh snapshot, cũng có thể dùng JUnit để tạo record trước, thay đổi list nguồn sau và assert phần tử ban đầu vẫn giữ nguyên. Với integration test Spring, cần để Spring thực sự publish event thay vì gọi trực tiếp handler rồi khẳng định hạ tầng event hoạt động.

## 16. Các lỗi thường gặp

1. **Cho rằng mọi record đều bất biến sâu.** Record final component có thể chứa `List` hoặc entity mutable.
2. **Truyền nguyên `ArrayList` vào record và không copy.** Publisher/consumer đều có thể sửa dữ liệu.
3. **Dùng `Collections.unmodifiableList` trên một list còn bị giữ tham chiếu nơi khác.** View không phải snapshot.
4. **Gọi `List.copyOf` rồi quên phần tử nested mutable.** Chỉ cấu trúc list được bảo vệ.
5. **Giữ `byte[]` mà không clone hai chiều.** Caller có thể sửa mảng qua accessor.
6. **Tin rằng record có field array sẽ so sánh nội dung array.** Equality mặc định của array theo reference.
7. **Đưa JPA entity vào event record.** Đóng băng reference chứ không đóng băng trạng thái entity, và có thể gặp lazy-loading.
8. **Đưa toàn bộ customer object chứa dữ liệu nhạy cảm vào payload.** `toString`/log/serialization có thể rò rỉ dữ liệu.
9. **Quên kiểm tra null và business invariant.** Record constructor mặc định không tự biết ID không được rỗng hoặc giá không được âm.
10. **Nhầm record với subclass `ApplicationEvent`.** Record không extends `ApplicationEvent`; dùng `publishEvent(Object)` và `@EventListener` payload.
11. **Nhầm immutable event với durable delivery.** Spring event in-memory không thay thế outbox/broker.
12. **Không kiểm soát phiên bản schema.** Thêm component có thể khiến consumer cũ không deserialize được.
13. **Phụ thuộc ordering async.** Immutable không đồng nghĩa các listener hoàn thành đúng thứ tự.
14. **Tạo timestamp mỗi lần retry.** Một event replay cần giữ cùng `eventId` và thời điểm nghiệp vụ gốc nếu muốn truy vết chính xác.

## 17. Checklist khi thiết kế event record

- [ ] Event có tên biểu thị một sự thật đã xảy ra (ví dụ `OrderCreated`, `PaymentCaptured`).
- [ ] Dùng các component immutable rõ ràng: `String`, `UUID`, `Instant`, `BigDecimal`, enum, record lồng nhau có hợp đồng immutable.
- [ ] Dùng `List.copyOf`/`Map.copyOf`/`Set.copyOf` với collection mutable đầu vào và kiểm tra element nested.
- [ ] Với array/Date/object mutable, thực hiện defensive copy cả khi nhận và trả.
- [ ] Constructor validate ID, số lượng, giá trị, timestamp, null theo bất biến cần thiết.
- [ ] Không nhét entity ORM, connection, transaction, service object hay toàn bộ graph mutable vào payload.
- [ ] Dùng `eventId` ổn định, `occurredAt` rõ ngữ nghĩa và correlation/version khi cần.
- [ ] Không đưa secrets/PII không cần thiết vào payload hoặc log `toString` thiếu kiểm soát.
- [ ] Listener Spring nhận record trực tiếp qua `@EventListener` sau `publishEvent(Object)`.
- [ ] Có test payload không đổi sau khi sửa input, test mutation bị từ chối và test listener nhận đúng dữ liệu.
- [ ] Nếu async/transaction/outbox được dùng, có thiết kế lỗi, ordering, idempotency, durability riêng.
- [ ] Nếu payload đi qua broker/JSON, có test serialization và schema evolution theo phiên bản.

**Ghi nhớ:** `record` giúp viết payload **ngắn gọn, rõ ràng, dễ so sánh theo giá trị**. Nhưng record chỉ bất biến nông. Để có snapshot thật sự an toàn cho Spring Application Events, hãy xây payload từ các giá trị immutable, defensive copy collection/mảng và giữ hợp đồng dữ liệu ổn định. Spring có thể phát record trực tiếp bằng `ApplicationEventPublisher.publishEvent(Object)` và chuyển record đó tới `@EventListener` theo kiểu payload.

## Tài liệu tham khảo

- [Oracle Java 17 — Records](https://docs.oracle.com/en/java/javase/17/language/records.html)
- [Oracle Java 17 — Creating Unmodifiable Copies of Collections](https://docs.oracle.com/en/java/javase/17/core/creating-immutable-lists-sets-and-maps.html)
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Javadoc — PayloadApplicationEvent](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/PayloadApplicationEvent.html)

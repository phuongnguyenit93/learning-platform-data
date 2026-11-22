# Snapshot dữ liệu tại thời điểm phát event trong Spring Framework

## 1. Vấn đề: event giữ dữ liệu của *lúc phát* hay dữ liệu đang thay đổi?

Khi phát sự kiện ứng dụng bằng `ApplicationEventPublisher.publishEvent(...)`, một câu hỏi thiết kế quan trọng là: **listener cần nhìn thấy trạng thái nghiệp vụ ở thời điểm nào?** Nếu listener nhận trực tiếp một entity hoặc object domain còn thay đổi, nó có thể nhìn thấy trạng thái khác với trạng thái khi publisher phát event, đặc biệt khi event được xử lý bất đồng bộ, bị xếp hàng hoặc được lưu để xử lý về sau.

**Snapshot payload** là một biểu diễn dữ liệu được chụp ở một thời điểm xác định, đủ để mô tả sự kiện và **không thay đổi khi object nguồn tiếp tục thay đổi**. Thông thường, snapshot là một DTO/record bất biến gồm các giá trị cần thiết, không phải tham chiếu trực tiếp tới entity JPA, collection hoặc service.

Ví dụ: đơn hàng đang có trạng thái `CREATED`, một dòng hàng số lượng `1`. Service tạo `OrderSnapshotEvent` chứa ID, trạng thái, version, thời gian và các dòng hàng đã sao chép, rồi gọi `publishEvent(...)`. Sau đó đơn hàng được sửa thành `PAID`, số lượng thành `9`. Listener xử lý snapshot cũ vẫn phải nhận `CREATED`, số lượng `1`, vì đó là dữ liệu sự kiện đã được công bố.

Nguyên tắc:

- **Thời điểm chụp** là lúc ứng dụng **tạo snapshot**, thường ngay trước `publishEvent()`; không phải lúc listener chạy.
- **Tính bất biến** là tính chất của **toàn bộ đồ thị dữ liệu trong payload**, không chỉ của object wrapper ngoài cùng.
- **Snapshot khác trạng thái mới nhất**: listener không nên suy đoán snapshot luôn phản ánh DB sau cùng.
- **Phát event khác commit transaction**: `publishEvent()` không tự bảo đảm transaction hiện tại commit thành công.
- **Thời gian event khác version dữ liệu**: timestamp hỗ trợ chẩn đoán, còn version/sequence giúp kiểm soát cập nhật và thứ tự nghiệp vụ.

Bài học thuộc nhóm thiết kế payload của **Spring Framework Application Events**. Ví dụ chính dùng Spring Framework thuần, không phụ thuộc Spring Boot, JPA hay message broker.

## 2. Rủi ro của việc truyền object có thể thay đổi

Xét cách phát event dưới đây:

```java
public record OrderUpdatedEvent(OrderEntity order) {}

publisher.publishEvent(new OrderUpdatedEvent(order));
// Mã khác vẫn có thể sửa order sau khi phát sự kiện.
```

Đây là **đoạn minh họa**; `OrderEntity`, `order` và `publisher` do ứng dụng cung cấp.

Record `OrderUpdatedEvent` chỉ làm bất biến **tham chiếu field `order`**. Nó **không** làm bất biến bản thân `OrderEntity`. Nếu entity bị thay đổi:

```java
order.setStatus("PAID");
```

thì listener giữ event có thể quan sát status mới khi đọc `event.order().getStatus()`.

Cách phát này dễ tạo ra những lỗi khó phát hiện:

1. **Async race:** event được submit vào executor lúc status là `CREATED`, nhưng worker thread đọc object sau khi publisher đã đặt status là `PAID`.
2. **Dữ liệu thay đổi sau khi publish:** ngay cả listener đồng bộ có thể giữ event để dùng sau; lúc đọc lại, tham chiếu trỏ tới trạng thái mới.
3. **JPA lazy loading:** entity/proxy liên quan tới `EntityManager` hoặc persistence context có thể không còn dùng được trên thread khác, gây lỗi truy cập thuộc tính lazy hoặc phụ thuộc transaction.
4. **Dữ liệu không nhất quán:** listener đọc từng field ở các thời điểm khác nhau khi nhiều thread đang sửa object, tạo tổ hợp giá trị chưa từng tồn tại như một trạng thái nghiệp vụ hợp lệ.
5. **Thông tin dư thừa:** truyền toàn bộ entity graph có thể làm lộ thông tin nhạy cảm hoặc tạo coupling mạnh giữa publisher và consumer.
6. **Khó tái hiện sự kiện:** event dùng mutable reference không phải bản ghi lịch sử; log/debug về sau có thể không phản ánh đúng lúc event được phát.

Ngay cả với `@EventListener` mặc định đồng bộ, truyền thẳng entity vẫn làm payload khó tái sử dụng, khó test và dễ vỡ khi sau này thay đổi cấu hình sang async.

## 3. Thiết kế payload snapshot bất biến

Ví dụ phù hợp với Java 17:

```java
public record OrderLineSnapshot(String sku, int quantity) {}

public record OrderSnapshot(
        String orderId,
        String status,
        long version,
        Instant capturedAt,
        List<OrderLineSnapshot> lines) {

    public OrderSnapshot {
        lines = List.copyOf(lines);
    }
}

public record OrderStatusChangedEvent(OrderSnapshot snapshot) {}
```

Đây là **đoạn định nghĩa minh họa** (cần import `java.time.Instant` và `java.util.List`); một chương trình chạy đầy đủ nằm ở mục 5.

Các trường có mục đích riêng:

| Trường | Vai trò |
| --- | --- |
| `orderId` | Định danh aggregate để consumer biết đối tượng nghiệp vụ nào thay đổi |
| `status` | Giá trị nghiệp vụ cụ thể tại thời điểm chụp |
| `version` | Phiên bản/trình tự thay đổi của aggregate; hữu ích để phát hiện event cũ, trùng, sai thứ tự |
| `capturedAt` | Thời điểm ứng dụng tạo snapshot, phục vụ log và phân tích |
| `lines` | Bản sao dữ liệu cần thiết cho listener, gồm các `OrderLineSnapshot` bất biến |
| `OrderStatusChangedEvent` | Tên sự kiện thể hiện một sự thật nghiệp vụ đã được ghi nhận ở thời điểm phát |

**Vì sao không chỉ dùng `record`?** Record chỉ ngăn gán lại các field trong instance record. Với field kiểu `List<MutableLine>`, danh sách có thể thay đổi và các `MutableLine` bên trong vẫn có thể bị sửa. `List.copyOf(lines)` bảo vệ **cấu trúc danh sách khỏi thêm/xóa trực tiếp** nhưng chỉ **sao chép nông** (shallow copy). Nếu phần tử còn mutable, thay đổi trên phần tử vẫn xuất hiện qua snapshot.

Bởi vậy payload trên dùng đồng thời:

- `OrderLineSnapshot` chỉ chứa `String` và `int`, đều có ngữ nghĩa bất biến.
- `OrderSnapshot` lưu danh sách `List.copyOf(...)`.
- `Instant` là một kiểu bất biến, an toàn để giữ trong record.
- Không giữ `EntityManager`, `OrderEntity`, `MutableLine`, `InputStream`, `Connection` hay các object có trạng thái sống trong payload.

Có thể tăng kiểm tra bất biến bằng `Objects.requireNonNull` và validate các giá trị đầu vào. Nếu một phần tử `lines` chứa object lồng sâu như `Map<String, List<MutableLine>>`, phải cân nhắc **defensive copy đệ quy** cho phần dữ liệu đó. Không gọi một object là “immutable” chỉ vì lớp ngoài cùng có các field `final`.

## 4. Đường đi sự kiện: tạo snapshot trước hay sau `publishEvent()`?

Mẫu nên dùng:

```text
Thread nghiệp vụ (publisher)
  |
  +-- có aggregate cần phát event
  |
  +-- đọc các giá trị cần thiết
  +-- tạo các DTO bất biến / snapshot (thời điểm T0)
  +-- tạo event trỏ tới snapshot bất biến
  |
  +-- publishEvent(event)
        |
        +-- @EventListener đồng bộ có thể chạy ngay trong thread publisher
        |
        +-- @Async @EventListener có thể được submit tới executor
        |
        +-- @TransactionalEventListener có thể đăng ký callback theo transaction
  |
  +-- aggregate tiếp tục thay đổi hoặc transaction tiếp tục xử lý
        |
        +-- snapshot trong event vẫn mô tả T0
```

Spring Framework mặc định phân phối Application Events đồng bộ qua multicaster mặc định. Tuy nhiên, **API `publishEvent()` bản thân không cam kết mọi listener đều xử lý đồng bộ hoặc ngay lập tức**: multicaster có thể được cấu hình executor, một method có thể dùng `@Async`, hoặc listener được gắn với pha transaction.

Snapshot phải được hình thành **trước điểm bàn giao event**. Nếu chỉ truyền `Supplier<OrderEntity>` hoặc `() -> entity.getStatus()`, đó là **trì hoãn việc đọc**, không phải chụp snapshot; khi supplier chạy, dữ liệu có thể đã đổi. Tương tự, đưa một entity vào queue rồi chỉ chuyển sang DTO ở worker thread là quá muộn để bảo đảm giữ trạng thái tại thời điểm phát.

Mặt khác, chụp snapshot từ một aggregate đang bị sửa đồng thời **không tự bảo đảm một trạng thái nguyên tử**. Để tránh “torn snapshot”, phải đọc nhất quán theo ranh giới aggregate: dùng cùng lock nếu dữ liệu ở bộ nhớ, transaction/locking và version nếu dữ liệu ở DB, hoặc thiết kế event từ **giá trị thay đổi đã xác định trong một thao tác nghiệp vụ**. `List.copyOf(...)` không thay thế synchronization khi collection nguồn đang bị sửa đồng thời.

## 5. Ví dụ Java 17+ chạy được: immutable snapshot so với mutable reference

Ví dụ sau dùng **Spring Framework 6.2.12** và Gradle 8+, không cần Spring Boot. Chúng ta phát **hai event**:

- `OrderSnapshotEvent` chứa **bản sao bất biến** của order trước khi thay đổi.
- `OrderReferenceEvent` chứa **tham chiếu tới aggregate mutable** để minh họa điều không nên làm.

Một listener Spring mặc định đồng bộ lưu hai event. Sau khi publisher thay đổi aggregate, chương trình in dữ liệu đã lưu để chứng minh snapshot giữ trạng thái cũ, còn tham chiếu chỉ thấy trạng thái mới.

### 5.1. Cấu trúc dự án

```text
spring-event-snapshot-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SnapshotEventDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-event-snapshot-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.SnapshotEventDemo'
}
```

### 5.2. File `src/main/java/demo/SnapshotEventDemo.java`

```java
package demo;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SnapshotEventDemo {

    // Các value object chỉ chứa giá trị bất biến.
    public record LineSnapshot(String sku, int quantity) {}

    public record OrderSnapshot(
            String orderId,
            String status,
            long version,
            Instant capturedAt,
            List<LineSnapshot> lines) {

        public OrderSnapshot {
            Objects.requireNonNull(orderId);
            Objects.requireNonNull(status);
            Objects.requireNonNull(capturedAt);
            lines = List.copyOf(lines);
        }

        public int firstQuantity() {
            return lines.get(0).quantity();
        }
    }

    public record OrderSnapshotEvent(OrderSnapshot order) {}

    // Event đối chứng: record wrapper nhưng giữ tham chiếu mutable.
    public record OrderReferenceEvent(MutableOrder order) {}

    public static final class MutableLine {
        private final String sku;
        private int quantity;

        public MutableLine(String sku, int quantity) {
            this.sku = sku;
            this.quantity = quantity;
        }

        public String sku() {
            return sku;
        }

        public int quantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }
    }

    public static final class MutableOrder {
        private final String id;
        private String status = "CREATED";
        private long version = 1;
        private final List<MutableLine> lines = new ArrayList<>();

        public MutableOrder(String id) {
            this.id = id;
            lines.add(new MutableLine("BOOK", 1));
        }

        public String status() {
            return status;
        }

        public long version() {
            return version;
        }

        public int firstQuantity() {
            return lines.get(0).quantity();
        }

        public int lineCount() {
            return lines.size();
        }

        // Thao tác chụp: tạo value object độc lập, không đưa
        // MutableLine hoặc List<MutableLine> trực tiếp vào event.
        public OrderSnapshot snapshot(Instant at) {
            List<LineSnapshot> copied = lines.stream()
                    .map(line -> new LineSnapshot(line.sku(),
                                                   line.quantity()))
                    .toList();

            return new OrderSnapshot(id, status, version, at, copied);
        }

        public void markPaid() {
            status = "PAID";
            version++;
            lines.get(0).setQuantity(9);
            lines.add(new MutableLine("PEN", 2));
        }
    }

    public static final class SnapshotObserver {
        private OrderSnapshotEvent snapshotEvent;
        private OrderReferenceEvent referenceEvent;

        @EventListener
        public void onSnapshot(OrderSnapshotEvent event) {
            snapshotEvent = event;
        }

        @EventListener
        public void onReference(OrderReferenceEvent event) {
            referenceEvent = event;
        }

        public OrderSnapshot savedSnapshot() {
            return snapshotEvent.order();
        }

        public MutableOrder savedReference() {
            return referenceEvent.order();
        }
    }

    public static final class OrderService {
        private final ApplicationEventPublisher publisher;
        private final MutableOrder order = new MutableOrder("O-100");

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void publishThenChange() {
            Instant fixedTime = Instant.parse("2026-01-01T00:00:00Z");
            OrderSnapshot snapshot = order.snapshot(fixedTime);

            publisher.publishEvent(new OrderSnapshotEvent(snapshot));
            publisher.publishEvent(new OrderReferenceEvent(order));

            System.out.println("at publish: " + format(snapshot.status(),
                    snapshot.version(), snapshot.firstQuantity()));

            // Phần dữ liệu nguồn thay đổi sau khi đã phát hai event.
            order.markPaid();
        }

        public MutableOrder currentOrder() {
            return order;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        SnapshotObserver snapshotObserver() {
            return new SnapshotObserver();
        }

        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    private static String format(String status, long version, int qty) {
        return status + "/" + version + "/" + qty;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService service = context.getBean(OrderService.class);
            SnapshotObserver observer =
                    context.getBean(SnapshotObserver.class);

            service.publishThenChange();

            OrderSnapshot saved = observer.savedSnapshot();
            MutableOrder reference = observer.savedReference();
            MutableOrder current = service.currentOrder();

            System.out.println("current: " + format(current.status(),
                    current.version(), current.firstQuantity()));
            System.out.println("snapshot: " + format(saved.status(),
                    saved.version(), saved.firstQuantity()));
            System.out.println("reference: " + format(reference.status(),
                    reference.version(), reference.firstQuantity()));
            System.out.println("line counts: snapshot="
                    + saved.lines().size() + ", current="
                    + current.lineCount());

            boolean listIsUnmodifiable = false;
            try {
                saved.lines().add(new LineSnapshot("NEW", 1));
            } catch (UnsupportedOperationException ex) {
                listIsUnmodifiable = true;
            }
            System.out.println(
                    "snapshot list unmodifiable=" + listIsUnmodifiable);
        }
    }
}
```

Chạy trên JDK 17+ khi đã cài Gradle:

```bash
gradle -q run
```

Các dòng do chương trình in ra (bỏ qua thông báo của công cụ build, nếu có):

```text
at publish: CREATED/1/1
current: PAID/2/9
snapshot: CREATED/1/1
reference: PAID/2/9
line counts: snapshot=1, current=2
snapshot list unmodifiable=true
```

### 5.3. Giải thích kết quả

1. `AnnotationConfigApplicationContext` tạo các Spring bean và đăng ký các method `@EventListener`. `ApplicationEventPublisher.publishEvent(Object)` hỗ trợ event là Java record thông thường; Spring có thể bọc payload bằng `PayloadApplicationEvent` để phân phối theo kiểu.
2. `OrderService` chụp `OrderSnapshot` tại thời điểm `Instant.parse(...)`. Thời gian cố định trong ví dụ giúp kết quả dễ tái hiện; ứng dụng thật thường dùng `Clock.instant()` hoặc `Instant.now()` từ clock được inject.
3. Hai event được phát khi trạng thái nguồn là `CREATED`, version `1`, số lượng đầu tiên `1`. Listener đồng bộ lưu chúng, nhưng việc **lưu reference** không phải việc **sao chép dữ liệu**.
4. `order.markPaid()` đổi trạng thái thành `PAID`, tăng version lên `2`, sửa số lượng thành `9` và thêm dòng hàng mới.
5. `savedSnapshot()` vẫn là `CREATED/1/1`, chỉ có một line vì payload chứa DTO bất biến.
6. `savedReference()` đọc trực tiếp một `MutableOrder` cũ nhưng cùng instance với `currentOrder()`, do đó thấy `PAID/2/9` và hai dòng.
7. `List.copyOf(...)` đã bảo vệ danh sách trong `OrderSnapshot`. Thử `add(...)` trên danh sách snapshot ném `UnsupportedOperationException`, nên chương trình in `snapshot list unmodifiable=true`.

Mặc dù ví dụ dùng listener **đồng bộ** để giữ output xác định, cùng nguy cơ reference càng đáng chú ý khi dùng `@Async`, executor ở event multicaster hoặc một cơ chế queue. Với listener async, thứ tự chạy và thời điểm đọc dữ liệu có thể khác; **đừng** dùng `Thread.sleep(...)` để chứng minh snapshot. Hãy dùng `CountDownLatch`, `CompletableFuture` hay test đồng bộ hóa có timeout.

**Giới hạn ví dụ:** `MutableOrder.snapshot(...)` đọc object do một thread thao tác trong demo. Trong hệ thống có cập nhật đồng thời, code phải bảo đảm chụp nhất quán bằng synchronization/transaction/version, không phải chỉ thêm `List.copyOf(...)` là đủ.

## 6. Sao chép sâu (deep copy) và phòng vệ trước dữ liệu mutable

Một bẫy rất phổ biến:

```java
record WrongPayload(List<MutableLine> lines) {
    WrongPayload {
        lines = List.copyOf(lines);
    }
}
```

Đây là mã minh họa, cần kiểu `MutableLine` như ví dụ trên. Danh sách `WrongPayload.lines()` không cho `add/remove`, nhưng nếu một `MutableLine` bên trong bị `setQuantity(9)`, nội dung được thấy qua event vẫn thay đổi.

Có ba mức bảo vệ cần phân biệt:

| Kỹ thuật | Bảo vệ điều gì? | Không bảo vệ điều gì? |
| --- | --- | --- |
| Field `final` hoặc Java record | Không cho gán lại field | Object được field trỏ tới vẫn có thể mutable |
| `List.copyOf(...)` / `Map.copyOf(...)` | Không cho sửa trực tiếp cấu trúc collection trong payload; tạo collection kết quả không sửa được | Không làm phần tử/value bên trong bất biến |
| Chuyển từng phần tử thành immutable DTO/record | Trạng thái nội dung của từng phần tử được chụp theo giá trị | Không tự bảo đảm snapshot nguyên tử nếu nguồn thay đổi đồng thời |

Ví dụ chuẩn với collection:

```java
List<LineSnapshot> lines = entity.getLines().stream()
        .map(line -> new LineSnapshot(
                line.getSku(), line.getQuantity()))
        .toList();

OrderSnapshot snapshot = new OrderSnapshot(
        entity.getId(),
        entity.getStatus(),
        entity.getVersion(),
        clock.instant(),
        lines);
```

Đây là **mã minh họa**; `entity`, `clock` và các getter thuộc ứng dụng, không phải chương trình độc lập. `List.copyOf(...)` trong constructor record giúp bảo vệ trường hợp caller truyền một danh sách vẫn có thể bị sửa. Tuy vậy, cần tránh truy cập lazy JPA relations ngoài transaction hoặc ngoài persistence context; thông thường ánh xạ DTO trong transaction/persistence context đang hoạt động hoặc dùng query projection để lấy đúng dữ liệu.

Nếu payload chứa `Date`, mảng byte `byte[]`, `ArrayList`, `HashMap`, mutable POJO hoặc cấu trúc lồng sâu, cần defensive copy ở **constructor** và khi **trả dữ liệu** nếu exposing lại các thành phần mutable. Ví dụ mảng byte cần clone khi nhận và khi trả; đổi sang `String`/`Instant`/value object bất biến nếu phù hợp. `Collections.unmodifiableList(original)` chỉ là một **view** không cho sửa qua view đó, nhưng list `original` vẫn có thể bị sửa bởi nơi khác; nó không tương đương snapshot độc lập.

## 7. Snapshot phải được lấy trong một trạng thái nhất quán

Một payload có các field bất biến sau khi tạo vẫn có thể **sai ngay từ lúc tạo** nếu đọc từ nguồn không nhất quán.

Ví dụ nguy hiểm:

```text
Thread A: đọc status = PAID
Thread B: cập nhật version = 8, status = CANCELLED
Thread A: đọc version = 8
Thread A: tạo event (PAID, version 8)
```

Trong hệ thống thực tế, có thể không có trạng thái hợp lệ nào là `(PAID, 8)`. Immutable event chỉ đóng băng một giá trị **không nhất quán**.

Các lựa chọn phụ thuộc kiến trúc:

- **Aggregate nằm trong bộ nhớ:** kiểm soát đồng bộ khi vừa mutate vừa capture; ví dụ dùng cùng lock/synchronized hoặc chiến lược sở hữu một thread.
- **JDBC/JPA transaction:** chụp các giá trị nghiệp vụ theo một transaction và mức isolation phù hợp. Nếu dùng optimistic locking với `@Version`, phiên bản event nên gắn với phiên bản aggregate có ý nghĩa sau cập nhật.
- **Đọc từ nhiều bảng hoặc nguồn:** cân nhắc query projection nhất quán, snapshot isolation hoặc phối hợp theo transaction; không giả định nhiều truy vấn rời rạc phản ánh một thời điểm toàn cục.
- **Tạo event từ command/result đã xác định:** sau khi áp dụng thay đổi nghiệp vụ, tạo value object từ dữ liệu đã quyết định trước khi rời ranh giới nghiệp vụ, thay vì đọc lại object sống từ một thread khác.

Một cách thực tế để giảm race khi dùng JPA: trong phạm vi service `@Transactional`, thay đổi entity, xác định giá trị muốn công bố, ánh xạ sang DTO bất biến, rồi publish event. Tuy nhiên transaction có thể rollback hoặc lỗi commit về sau, nên listener hậu commit/outbox vẫn cần thiết nếu consumer chỉ được hành động khi dữ liệu đã commit.

**`capturedAt` không phải một cơ chế khóa.** Dù timestamp dùng `Instant.now()`, không thể chỉ dựa vào hai đồng hồ của hai service khác nhau để có thứ tự toàn cục chính xác. Khi cần phát hiện trễ, trùng hoặc sai thứ tự, nên thiết kế `aggregateVersion`, `eventId` hoặc sequence ổn định.

## 8. Event được phát trước commit: snapshot chưa bảo đảm đã lưu thành công

Giả sử có phương thức:

```java
@Transactional
public void confirmOrder(Order order) {
    order.markConfirmed();
    publisher.publishEvent(new OrderConfirmedEvent(
            toSnapshot(order)));
    // Một lỗi có thể xảy ra sau đây, khiến transaction rollback.
}
```

Đây là mã minh họa (giả định các kiểu và hàm hỗ trợ được định nghĩa trong ứng dụng).

Snapshot mô tả dữ liệu tại lúc phát event, nhưng transaction có thể rollback. Khi đó:

- Một listener `@EventListener` đồng bộ đã có thể đọc snapshot dù DB về sau không commit.
- Một `@Async @EventListener` có thể xử lý snapshot khi transaction còn mở và khi DB ở thread khác chưa nhìn thấy dữ liệu.
- `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` chỉ được gọi sau khi transaction có event **commit thành công**, nếu event được phát trong transaction phù hợp.
- `@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)` phản ứng theo nhánh rollback, không phải sự kiện “đã commit”.
- Snapshot `AFTER_COMMIT` vẫn là **giá trị được chụp trước commit**, không tự được Spring cập nhật thành bản đọc cuối cùng của DB.
- Mặc định, `@TransactionalEventListener` không thực thi nếu event phát khi **không có transaction** (trừ khi `fallbackExecution = true`).

Đối với nghiệp vụ gửi email hoặc gọi hệ thống ngoài chỉ khi dữ liệu được commit, chọn `AFTER_COMMIT` là một bước đúng về **thời điểm**. Nhưng đó không phải bảo đảm **giao hàng bền vững**: nếu tiến trình chết sau DB commit và trước khi xử lý event, tác vụ trong bộ nhớ có thể mất. Nhu cầu giao hàng chắc chắn cần **transactional outbox** hoặc thiết kế tương đương.

### Snapshot và transactional outbox

Nếu phải gửi snapshot sang broker hoặc consumer khác một cách tin cậy:

```text
@Transactional service
    +-- cập nhật aggregate
    +-- tạo snapshot / event payload với eventId
    +-- ghi outbox row chứa payload snapshot (cùng transaction)
    +-- commit
           |
           +-- outbox worker đọc row đã commit
           +-- gửi tới broker / external system
           +-- đánh dấu hoàn tất, retry khi lỗi
```

Ở đây payload được lưu cùng transaction với dữ liệu nghiệp vụ; nếu transaction rollback, bản ghi outbox cũng rollback. Worker xử lý sau commit, cần **idempotency**, retry và theo dõi trạng thái. Không được suy luận rằng chỉ `@TransactionalEventListener(AFTER_COMMIT)` là có retry/durability tương đương outbox.

Nếu consumer cần **trạng thái tại lúc nghiệp vụ xảy ra**, outbox nên lưu **payload snapshot** trong cùng transaction, không chỉ lưu ID rồi sau nhiều giây đọc lại `order` hiện tại (vì bản ghi có thể đã thay đổi tiếp). Nếu consumer chỉ cần xử lý **trạng thái mới nhất**, gửi ID và re-query có thể là lựa chọn đúng hơn. Hai ý nghĩa này phải được quyết định rõ.

## 9. Lựa chọn payload: ID, delta hay snapshot đầy đủ?

Không phải event nào cũng cần chứa toàn bộ dữ liệu.

| Kiểu payload | Ví dụ | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| **ID-only** | `OrderChanged(orderId)` | Nhẹ, ít rò rỉ dữ liệu, ít phụ thuộc schema | Listener phải tra cứu, có thể thấy trạng thái *mới hơn* thời điểm phát |
| **Delta / fact** | `OrderStatusChanged(orderId, oldStatus, newStatus, version)` | Diễn tả chính xác thay đổi, payload nhỏ | Listener có thể cần state trước hoặc phải áp dụng theo đúng thứ tự |
| **Snapshot** | `OrderSnapshot(id, status, lines, version, capturedAt)` | Tự đủ dữ liệu cho xử lý lịch sử, async, message | Payload lớn hơn, cần versioning và bảo mật dữ liệu |
| **Full entity reference** | `OrderChanged(entity)` | Dễ viết ban đầu | Mutable coupling, lazy loading, thread safety, không phù hợp lưu/gửi qua network |

Quy tắc chọn:

- Nếu consumer cần **tên sản phẩm và số lượng đúng tại lúc mua**, snapshot đủ các giá trị này là hợp lý.
- Nếu consumer chỉ cần **cập nhật màn hình theo trạng thái mới nhất**, ID + re-query thường đơn giản hơn.
- Nếu consumer phải **áp dụng chuyển trạng thái**, delta kèm `aggregateVersion` có thể tránh sao chép mọi field.
- Không nên “chụp toàn bộ entity graph” theo mặc định: snapshot chỉ nên chứa những trường cần cho contract sự kiện.

Một sự kiện tốt thường diễn tả **điều đã xảy ra** (`OrderPaid`, `OrderCancelled`), không chỉ nêu một object chung chung đã thay đổi (`ObjectUpdated`). Với snapshot, tên event nên cho phép hiểu chính xác: đó là trạng thái trước khi thay đổi, sau khi thao tác nghiệp vụ, hay trạng thái đã commit. Tên event không tự thay thế tài liệu về ranh giới transaction.

## 10. Metadata: thời gian, version, idempotency và schema

Với event cần lưu lại hoặc gửi qua broker, cân nhắc envelope:

```java
public record EventEnvelope<T>(
        String eventId,
        String eventType,
        int schemaVersion,
        String aggregateId,
        long aggregateVersion,
        Instant occurredAt,
        String correlationId,
        T payload) {}
```

Đây là **định nghĩa minh họa**; cần import `java.time.Instant` và một payload `T` thích hợp.

Các trường này giải quyết vấn đề khác nhau:

- `eventId`: định danh duy nhất **mỗi lần phát sự kiện nghiệp vụ**; giúp consumer chống xử lý trùng khi retry.
- `eventType`: tên có ý nghĩa nghiệp vụ, ví dụ `OrderPaid`.
- `schemaVersion`: phiên bản **cấu trúc message/payload**, độc lập với version của đơn hàng.
- `aggregateId`: khóa xác định order hoặc aggregate liên quan.
- `aggregateVersion`: version của entity/aggregate sau thao tác nghiệp vụ hoặc theo quy ước đã định; hỗ trợ phát hiện event cũ và ordering.
- `occurredAt`: thời gian producer ghi nhận sự kiện; hỗ trợ log/metrics, không thay thế sequence.
- `correlationId`: nối với request/workflow nghiệp vụ, hữu ích cho tracing.
- `payload`: snapshot giá trị bất biến hoặc một delta có contract rõ ràng.

**Khác biệt version quan trọng:** `schemaVersion=2` có thể chỉ rằng đã thêm field `currency`, trong khi `aggregateVersion=15` cho biết đơn hàng đã trải qua một loạt cập nhật. Không dùng hai khái niệm này lẫn nhau.

Đối với messaging, cần serialize event thành dữ liệu độc lập như JSON/Avro/Protobuf. Java record giúp biểu diễn dữ liệu trong JVM nhưng **không tự bảo đảm schema tương thích giữa dịch vụ hoặc phiên bản**. Test serialization/deserialization và kế hoạch tương thích ngược khi thêm/đổi/loại field.

Khi consumer nhận lại event do retry:

```text
eventId đã xử lý       -> bỏ qua side effect trùng
aggregateVersion cũ    -> có thể bỏ qua hoặc xử lý theo chính sách
aggregateVersion mới   -> áp dụng nếu thỏa điều kiện và ordering
```

Đây là **chiến lược minh họa**, không phải một quy tắc áp dụng nguyên xi cho mọi bài toán. Có hệ thống cần xử lý đầy đủ từng event lịch sử thay vì bỏ qua event cũ; phải định nghĩa rõ contract ordering và tính idempotent.

## 11. Dữ liệu nhạy cảm và kích thước snapshot

Snapshot thường được lưu vào log, outbox, broker, queue hoặc cơ sở dữ liệu audit. Nếu vô ý đưa quá nhiều trường vào event, dữ liệu có thể tồn tại lâu hơn bản ghi nghiệp vụ gốc và đi tới nhiều consumer.

Nguyên tắc:

1. **Data minimization:** chỉ thêm thông tin consumer cần, tránh đưa password, access token, địa chỉ chi tiết, số thẻ hoặc dữ liệu cá nhân không cần thiết.
2. **Không phụ thuộc lazy entity graph:** định nghĩa DTO projection rõ ràng với field được phép công bố.
3. **Giới hạn kích thước:** hàng nghìn order lines, ảnh nhúng hoặc byte array lớn có thể làm queue chậm, tăng memory/serialization cost; nếu payload lớn, cân nhắc ID + version + một snapshot được lưu riêng, nhưng phải giữ ý nghĩa thời điểm.
4. **Retention và xóa dữ liệu:** snapshot trong outbox/log phải tuân thủ thời hạn lưu và cơ chế xử lý dữ liệu phù hợp.
5. **Kiểm soát schema:** thay đổi field có thể ảnh hưởng nhiều consumer; công bố contract, version và test tương thích.
6. **Không đặt secret vào `toString()`:** Java record tự sinh `toString()` chứa field của record, nên việc log toàn bộ event có thể vô tình lộ dữ liệu.

Snapshot bất biến giảm rủi ro đua dữ liệu, **không tự bảo đảm an toàn bảo mật**. Những gì được sao chép vào event phải được xem như một API contract có vòng đời riêng.

## 12. Kiểm thử snapshot và listener

Một bộ test có giá trị nên kiểm tra:

1. **Ảnh chụp tại lúc phát:** tạo order trạng thái `CREATED`, chụp snapshot, phát event, thay đổi order thành `PAID`; assert snapshot vẫn là `CREATED`.
2. **Deep immutability:** sửa collection nguồn, sửa từng element nguồn, thử sửa collection trong snapshot; xác nhận payload không thay đổi.
3. **Đủ dữ liệu nghiệp vụ:** consumer có thể làm việc chỉ từ snapshot, không cần lazy JPA entity hoặc `EntityManager`.
4. **Đồng thời:** producer cập nhật aggregate khi chụp trong nhiều thread; xác minh snapshot được tạo nhất quán hoặc cơ chế lock/version phát hiện conflict.
5. **Async:** listener có `@Async` sử dụng latch/future để chờ có kiểm soát, xác minh payload không đổi dù publisher tiếp tục mutate object nguồn.
6. **Transaction commit/rollback:** nếu listener phải chạy sau commit, test trường hợp commit thành công và rollback; event snapshot được tạo không đồng nghĩa listener after-commit luôn chạy.
7. **Serialization:** payload gửi qua broker hoặc outbox còn deserialize được với schema mong đợi; `Instant`, enum, optional fields và version được xử lý đúng.
8. **Đến trùng/sai thứ tự:** consumer dùng `eventId` và `aggregateVersion` theo chính sách nghiệp vụ, không áp dụng mù một snapshot cũ đè lên trạng thái mới.
9. **Thông tin nhạy cảm:** bảo đảm payload, log và dữ liệu persisted không chứa trường vượt phạm vi cho phép.

Ví dụ JUnit test logic không cần Spring (đoạn minh họa):

```java
OrderSnapshot before = order.snapshot(clock.instant());
order.markPaid();

assertEquals("CREATED", before.status());
assertEquals(1, before.lines().get(0).quantity());
assertThrows(UnsupportedOperationException.class,
        () -> before.lines().add(new LineSnapshot("X", 1)));
```

Đây **không phải chương trình độc lập**: `order`, `clock`, import JUnit và các record thuộc ngữ cảnh test của ứng dụng. Ví dụ chạy đầy đủ với Spring nằm ở mục 5. Không dựa vào kết quả của một listener async nếu test chưa chờ tác vụ hoàn tất.

### Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân chính | Hướng sửa |
| --- | --- | --- |
| Listener thấy trạng thái mới thay vì trạng thái lúc phát | Event giữ entity/object mutable | Tạo DTO/record snapshot độc lập trước `publishEvent()` |
| Record vẫn “bị thay đổi” gián tiếp | Field record chứa list/map/object mutable | Defensive copy và immutable elements, không chỉ `final` |
| List trong event thay đổi khi source list thay đổi | Sử dụng view `Collections.unmodifiableList(source)` | Dùng snapshot collection độc lập, ví dụ `List.copyOf` cộng deep copy |
| Snapshot chứa field tự mâu thuẫn | Producer đọc nguồn khi thread khác đang mutate | Chụp trong cùng lock/transaction hoặc dùng version nhất quán |
| `LazyInitializationException` trong async listener | Truyền JPA entity/proxy qua ranh giới persistence context | Ánh xạ dữ liệu cần thiết thành DTO trước publish |
| Event gửi ra ngoài dù transaction rollback | Dùng listener thường trước commit | Dùng `AFTER_COMMIT` hoặc outbox theo yêu cầu giao hàng |
| Event sau commit chỉ chứa ID nhưng consumer thấy dữ liệu mới hơn | Consumer re-query DB sau khi aggregate cập nhật thêm | Gửi snapshot/version nếu nghiệp vụ cần dữ liệu lịch sử |
| Snapshot đã gửi nhưng consumer xử lý trùng | Retry/at-least-once delivery | Event ID, idempotency key và xử lý lặp an toàn |
| Event cũ ghi đè trạng thái mới | Thiếu sequence hoặc version validation | Dùng aggregateVersion và quy tắc ordering |
| Payload quá lớn hoặc lộ thông tin | Sao chép toàn bộ entity graph, bao gồm secrets | Thiết kế DTO tối thiểu, retention, schema và bảo mật |

## 13. Checklist trước khi phát sự kiện

Trước khi gọi `publishEvent(...)`, hãy tự hỏi:

- **Dữ liệu cần phản ánh lúc nào?** Lúc command được chấp nhận, sau khi thay đổi in-memory, sau khi flush hay sau commit?
- **Consumer cần sự thật quá khứ hay trạng thái mới nhất?** Nếu là quá khứ, snapshot; nếu mới nhất, ID + re-query có thể hợp hơn.
- **Đã tách payload khỏi object mutable chưa?** Cả phần tử trong list/map và nested objects đã được copy phù hợp chưa?
- **Chụp có nhất quán không?** Có transaction/lock/version bao trùm các field không?
- **Event có đủ định danh/version/thời gian không?** Để trace, idempotency, ordering và schema evolution.
- **Có ràng buộc commit không?** Nếu listener chỉ được tác động ra ngoài sau commit, thiết kế transaction-phase listener hoặc outbox.
- **Có thông tin nhạy cảm hoặc payload thừa không?** Chỉ công bố trường cần thiết.
- **Đã kiểm thử biến đổi sau phát chưa?** Phải chứng minh snapshot không thay đổi dù aggregate nguồn tiếp tục sống và mutate.

**Tóm lại:** Snapshot payload là **bản chụp giá trị bất biến, độc lập với object nguồn tại thời điểm publisher tạo event**. Dùng Java record/value object kết hợp defensive copy để giữ dữ liệu đúng lúc phát, không đưa thẳng entity JPA mutable vào event. Tính nhất quán khi chụp, kết quả transaction, thứ tự delivery và khả năng phục hồi lỗi là những trách nhiệm **riêng** cần được thiết kế bổ sung.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events, `@EventListener` và asynchronous listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — `ApplicationEventPublisher` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html)
- [Java SE 17 — `List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))

# Transactional event listener trong module test

## 1. Vấn đề cần giải quyết

Một module Spring Modulith có thể phát sự kiện nghiệp vụ ngay trong transaction, nhưng module nhận chỉ nên xử lý sự kiện **sau khi thay đổi dữ liệu đã commit thành công**. Với Spring Framework, `@TransactionalEventListener` cung cấp cơ chế liên kết việc nhận sự kiện với các pha của transaction. Với Spring Modulith, `@ApplicationModuleTest` giúp cô lập module để kiểm tra hành vi đó mà không phải khởi chạy toàn bộ use case liên module.

Điều dễ nhầm nhất là: **“Đã gọi `publishEvent(...)`” không đồng nghĩa “listener `AFTER_COMMIT` đã chạy”.** Một bài test có thể quan sát được event vừa phát, nhưng listener vẫn chưa được kích hoạt vì transaction chưa commit, bị rollback hoặc không tồn tại.

Ví dụ hệ thống bán hàng:

- Module `order` đặt đơn hàng và phát `OrderPlaced`.
- Module `audit` lưu một bản ghi khi nhận `OrderPlaced`.
- Yêu cầu: không lưu bản ghi audit nếu transaction đặt đơn hàng thất bại.

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, trường hợp này liên kết ba năng lực: kiểm chứng ranh giới module bằng `ApplicationModules`, kiểm thử hành vi bằng `@ApplicationModuleTest`, và bảo vệ luồng sự kiện/database bằng các quality gate trong CI.

### Sau bài học, bạn có thể

1. Giải thích sự khác biệt giữa `@EventListener`, `@TransactionalEventListener` và `@ApplicationModuleListener`.
2. Hiểu các pha `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`.
3. Viết module test thật sự **commit** hoặc **rollback** transaction để quan sát listener.
4. Phân biệt test module phát bằng `PublishedEvents` và test module nhận bằng hiệu ứng có thể kiểm chứng.
5. Tránh sai lầm do `@Transactional` trên test, transaction lồng nhau, listener bất đồng bộ và thao tác database sau commit.
6. Đưa kiểm thử kiến trúc, event publication và integration test vào CI.

## 2. Nền tảng: transaction điều khiển thời điểm listener xử lý

### 2.1. @EventListener và @TransactionalEventListener

`ApplicationEventPublisher.publishEvent(event)` công bố một object tới cơ chế event của Spring. Với cấu hình mặc định, `@EventListener` được gọi đồng bộ trong quá trình phân phối event; nếu publisher nằm trong transaction, listener thường chạy **trước khi transaction kết thúc**.

`@TransactionalEventListener` đăng ký xử lý theo pha của transaction:

| Pha | Ý nghĩa | Tình huống sử dụng |
| --- | --- | --- |
| `BEFORE_COMMIT` | Được gọi trước lúc commit. | Kiểm tra hoặc công việc cần nằm trong tiến trình commit. |
| `AFTER_COMMIT` (**mặc định**) | Chỉ chạy sau khi transaction commit thành công. | Tạo audit, xử lý downstream dựa trên dữ liệu đã xác nhận. |
| `AFTER_ROLLBACK` | Chạy khi transaction rollback. | Ghi nhận hoặc phản ứng với tình huống rollback, nếu phù hợp. |
| `AFTER_COMPLETION` | Chạy sau khi transaction kết thúc, bất kể commit hay rollback. | Dọn dẹp hoặc quan sát trạng thái hoàn tất. |

Ví dụ listener nhận sự kiện sau commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderPlacedListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPlaced event) {
        // Thực hiện tác vụ sau khi transaction nguồn commit.
    }
}
~~~

Chỉ định `AFTER_COMMIT` trong ví dụ để dễ đọc; đây vốn là pha mặc định. Khác với listener thông thường, phương thức này **không chạy ngay tại thời điểm phát event**.

Mặc định `fallbackExecution = false`. Nếu gọi `publishEvent` khi **không có transaction đang hoạt động**, transactional listener không được gọi. Có thể bật `fallbackExecution = true` khi chủ đích nghiệp vụ cho phép xử lý cả trường hợp không có transaction, nhưng không nên bật chỉ để làm test “xanh”: nó có thể che khuất lỗi thiết kế transaction.

### 2.2. Diễn biến khi commit và rollback

~~~mermaid
sequenceDiagram
    participant UseCase as OrderService
    participant Tx as Transaction Manager
    participant Events as Event Publisher
    participant Listener as Transactional Listener
    participant DB as Database

    UseCase->>Tx: Bắt đầu transaction
    UseCase->>DB: Lưu đơn hàng
    UseCase->>Events: publishEvent(OrderPlaced)
    Note over Events,Listener: Ghi nhận callback AFTER_COMMIT
    alt Commit thành công
        Tx->>DB: COMMIT
        Tx->>Listener: Gọi listener AFTER_COMMIT
        Listener->>DB: Ghi audit trong transaction mới
    else Rollback
        Tx->>DB: ROLLBACK
        Note over Listener: Không chạy listener AFTER_COMMIT
    end
~~~

Điểm mấu chốt: event có thể được **phát** ngay trong transaction nguồn, còn listener `AFTER_COMMIT` chỉ được **thực thi** sau khi commit. Sơ đồ thể hiện quan hệ nhân quả; thứ tự callback chi tiết do transaction manager và loại listener quyết định.

### 2.3. Vì sao ghi database sau commit cần cẩn thận?

Một lỗi kín đáo là ghi database trực tiếp trong `@TransactionalEventListener(AFTER_COMMIT)` với kỳ vọng mọi thay đổi sẽ tự được commit. Ở pha này, transaction nguồn đã commit, nhưng tài nguyên transaction như kết nối hoặc persistence context có thể vẫn được gắn vào luồng. Truy cập dữ liệu có thể dính vào tài nguyên cũ và **không có commit mới** cho thay đổi vừa thực hiện.

Nếu listener cần ghi dữ liệu mới, một lựa chọn rõ ràng là gọi **một service bean khác** có:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAudit(...) {
    // Ghi dữ liệu bằng một transaction độc lập.
}
~~~

`REQUIRES_NEW` tạo transaction mới, tách khỏi transaction nguồn đã hoàn tất. Nên đặt phương thức ở **bean khác**: lời gọi `this.saveAudit(...)` trong cùng object có thể bỏ qua Spring proxy, khiến annotation `@Transactional` không có hiệu lực như dự kiến.

Với Spring Modulith, `@ApplicationModuleListener` là tiện ích thường dùng để kết hợp transactional event handling, xử lý bất đồng bộ và transaction mới. Hai cách triển khai này là **các lựa chọn**, không nên đồng thời đăng ký hai listener làm cùng một việc nếu sẽ gây xử lý trùng.

## 3. Ví dụ đầy đủ: order phát event, audit nhận sau commit

Giả sử ứng dụng Spring Boot có package gốc `com.example.shop`, lớp ứng dụng `ShopApplication`, Spring Modulith cùng JPA và transaction manager. Các package con trực tiếp `order` và `audit` là hai application module trong cách phát hiện mặc định:

~~~text
com.example.shop
├── ShopApplication.java
├── order
│   ├── OrderService.java
│   └── events
│       ├── OrderPlaced.java
│       └── package-info.java
└── audit
    ├── package-info.java
    ├── OrderAuditListener.java
    ├── AuditWriter.java
    ├── AuditEntry.java
    └── AuditEntryRepository.java
~~~

### 3.1. Sự kiện là API công khai của module order

File `order/events/OrderPlaced.java`:

~~~java
package com.example.shop.order.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(UUID orderId, Instant occurredAt) {}
~~~

File `order/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.order.events;
~~~

Event payload chỉ mang định danh và thời điểm xảy ra, không chuyển `OrderEntity` hay repository nội bộ sang `audit`. Named interface công bố package `order.events` làm một phần hợp đồng mà các module khác được phép dùng.

### 3.2. Module order phát event trong transaction

File `order/OrderService.java`:

~~~java
package com.example.shop.order;

import com.example.shop.order.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void place(UUID orderId) {
        // Ứng dụng thật: kiểm tra nghiệp vụ rồi lưu đơn hàng vào DB.
        events.publishEvent(new OrderPlaced(orderId, Instant.now()));
    }
}
~~~

Ví dụ lược bỏ mã repository để tập trung vào event. Ở ứng dụng thật, transaction của `place` cần chứa việc ghi trạng thái đơn hàng; nếu ghi dữ liệu thất bại và transaction rollback, listener `AFTER_COMMIT` sẽ không chạy.

### 3.3. Module audit công bố giới hạn phụ thuộc

File `audit/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: events"
)
package com.example.shop.audit;
~~~

Module `audit` được phép import event type từ named interface `events`, nhưng không được truy cập trực tiếp package triển khai nội bộ của `order`. Đây là ràng buộc tĩnh, độc lập với việc listener có chạy hay không.

### 3.4. Lưu audit bằng transaction mới

File `audit/AuditEntry.java`:

~~~java
package com.example.shop.audit;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

import java.time.Instant;
import java.util.UUID;

@Entity
class AuditEntry {

    @Id
    private UUID orderId;
    private Instant occurredAt;

    protected AuditEntry() {} // JPA cần constructor không tham số.

    AuditEntry(UUID orderId, Instant occurredAt) {
        this.orderId = orderId;
        this.occurredAt = occurredAt;
    }
}
~~~

File `audit/AuditEntryRepository.java`:

~~~java
package com.example.shop.audit;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.UUID;

interface AuditEntryRepository extends JpaRepository<AuditEntry, UUID> {}
~~~

File `audit/AuditWriter.java`:

~~~java
package com.example.shop.audit;

import com.example.shop.order.events.OrderPlaced;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
class AuditWriter {

    private final AuditEntryRepository entries;

    AuditWriter(AuditEntryRepository entries) {
        this.entries = entries;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(OrderPlaced event) {
        entries.save(new AuditEntry(event.orderId(), event.occurredAt()));
    }
}
~~~

`AuditWriter` là bean riêng, giúp lời gọi từ listener đi qua Spring proxy và tạo transaction mới. Trong ví dụ, `orderId` là khóa chính để mỗi đơn hàng có tối đa một bản ghi audit. Đây mới là cách đơn giản hóa dữ liệu mẫu; nghiệp vụ thực tế có thể cần `eventId`, khóa duy nhất hoặc kiểm soát đồng thời để xử lý phát trùng một cách an toàn.

### 3.5. Listener chạy sau commit

File `audit/OrderAuditListener.java`:

~~~java
package com.example.shop.audit;

import com.example.shop.order.events.OrderPlaced;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderAuditListener {

    private final AuditWriter writer;

    OrderAuditListener(AuditWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPlaced event) {
        writer.record(event);
    }
}
~~~

Đây là **listener đồng bộ theo pha transaction** trong cấu hình event multicaster mặc định. Khi transaction nguồn commit, Spring gọi `on`, rồi `AuditWriter.record` thực hiện một transaction mới để lưu audit. Nếu transaction nguồn rollback, `on` không được gọi.

**Lưu ý về độ tin cậy:** “sau commit” không có nghĩa việc ghi audit và commit đơn hàng là một transaction nguyên tử. Nếu audit thất bại sau khi đơn hàng đã commit, transaction nguồn không thể đơn giản rollback ngược lại. Với luồng nghiệp vụ cần khôi phục/retry sau lỗi, xem xét Event Publication Registry và cơ chế xử lý lại phù hợp.

## 4. Viết @ApplicationModuleTest cho transactional listener

Mục tiêu trước tiên là kiểm thử riêng **module nhận `audit`**. Đặt lớp test trong package `com.example.shop.audit`:

~~~java
package com.example.shop.audit;

import com.example.shop.order.events.OrderPlaced;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class AuditEventListenerTests {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired PlatformTransactionManager txManager;
    @Autowired AuditEntryRepository entries;

    private TransactionTemplate transactions;

    @BeforeEach
    void setUp() {
        entries.deleteAll();
        transactions = new TransactionTemplate(txManager);
    }

    @Test
    void writesAuditOnlyAfterCommit() {
        UUID orderId = UUID.randomUUID();
        var event = new OrderPlaced(orderId, Instant.now());

        transactions.executeWithoutResult(status -> {
            publisher.publishEvent(event);
            // Transaction chưa commit: AFTER_COMMIT chưa chạy.
            assertThat(entries.existsById(orderId)).isFalse();
        });

        // TransactionTemplate đã commit khi callback trả về.
        assertThat(entries.existsById(orderId)).isTrue();
    }

    @Test
    void doesNotWriteAuditOnRollback() {
        UUID orderId = UUID.randomUUID();
        var event = new OrderPlaced(orderId, Instant.now());

        transactions.executeWithoutResult(status -> {
            publisher.publishEvent(event);
            status.setRollbackOnly();
        });

        assertThat(entries.existsById(orderId)).isFalse();
    }

    @Test
    void ignoresEventWhenNoTransactionIsActive() {
        UUID orderId = UUID.randomUUID();

        publisher.publishEvent(new OrderPlaced(orderId, Instant.now()));

        // fallbackExecution mặc định = false.
        assertThat(entries.existsById(orderId)).isFalse();
    }
}
~~~

Đoạn test giả định cấu hình JPA và một database test có sẵn (ví dụ cơ sở dữ liệu nhúng cho test) cùng `PlatformTransactionManager`. `@ApplicationModuleTest` không tự cung cấp mọi driver, schema hoặc fixture mà một ứng dụng cần; hãy cấu hình persistence như trong integration test của dự án.

**Vì sao test này có ý nghĩa?**

- Nó chạy trong phạm vi module `audit`; test tự phát `OrderPlaced` để kiểm tra listener mà không cần gọi `OrderService`.
- `TransactionTemplate` tạo ranh giới commit/rollback rõ ràng. Mệnh đề bên trong callback được kiểm tra **trước commit**, còn mệnh đề bên ngoài kiểm tra **sau khi callback hoàn tất và transaction đã kết thúc**.
- Mẫu listener ở mục 3.5 hoạt động đồng bộ theo transaction, nên assertion sau `executeWithoutResult` có thể kiểm tra trạng thái ngay. Nếu chuyển sang xử lý bất đồng bộ thì cần cách chờ khác.
- Test riêng `AFTER_COMMIT`, rollback và thiếu transaction giúp phân biệt lỗi xử lý event với lỗi cấu hình transaction.

Không đặt `@Transactional` trên toàn bộ lớp test ở trên: một transaction bao quanh test có thể khiến `TransactionTemplate` tham gia **transaction test hiện có** thay vì tự commit. Trong Spring Test, transaction của test thường rollback khi kết thúc. Khi đó listener `AFTER_COMMIT` không chạy và assertion có thể gây hiểu nhầm.

Nếu test đang được quản lý transaction bởi Spring Test và cần chủ động commit, có thể dùng `TestTransaction.flagForCommit()` kết hợp `TestTransaction.end()` tại thời điểm phù hợp. Tuy nhiên, để dạy và kiểm tra listener `AFTER_COMMIT`, dùng một `TransactionTemplate` trong test **không gắn `@Transactional`** thường dễ hiểu hơn.

### 4.1. Chọn chế độ bootstrap phù hợp

`@ApplicationModuleTest` xác định module cần kiểm thử dựa trên package của lớp test. Chế độ mặc định `STANDALONE` tập trung vào module hiện tại; Spring Modulith còn có các chế độ nạp thêm module phụ thuộc trực tiếp hoặc toàn bộ module phụ thuộc (`DIRECT_DEPENDENCIES`, `ALL_DEPENDENCIES`).

Trong ví dụ, test module `audit` chỉ cần **kiểu sự kiện** `OrderPlaced` để gọi publisher, chứ không cần khởi tạo service nghiệp vụ của module `order`. Do đó, phạm vi `STANDALONE` giúp test nhanh và rõ trách nhiệm. Nếu listener dùng một API của module khác hoặc cần kiểm tra chuỗi tích hợp liên module, phải điều chỉnh phạm vi bootstrap và chuẩn bị các dependency tương ứng; test cô lập không bảo đảm toàn bộ luồng end-to-end đã được kiểm chứng.

## 5. Kiểm thử module phát và kiểm thử module nhận là hai việc khác nhau

Module test ở mục 4 chứng minh `audit` xử lý event **khi test tự phát event**. Nó chưa chứng minh rằng nghiệp vụ `order` có thực sự tạo event hay payload có đúng hay không.

Viết thêm test dưới package `com.example.shop.order`:

~~~java
package com.example.shop.order;

import com.example.shop.order.events.OrderPlaced;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderPublicationTests {

    @Autowired OrderService orders;

    @Test
    void publishesOrderPlaced(PublishedEvents events) {
        UUID id = UUID.randomUUID();

        orders.place(id);

        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, id))
                .hasSize(1);
    }
}
~~~

`PublishedEvents` quan sát sự kiện được công bố trong lúc test chạy. Đây là bằng chứng cho việc `OrderService.place` phát `OrderPlaced` với `orderId` mong muốn, **không phải bằng chứng rằng listener `AFTER_COMMIT` đã chạy hay đã cập nhật database**. Có thể kiểm thử thêm `occurredAt`, schema payload và dữ liệu persistence của module phát.

| Loại test | Câu hỏi được trả lời | Không nên suy ra |
| --- | --- | --- |
| Test module `order` + `PublishedEvents` | Use case có phát đúng event và payload không? | Audit listener đã hoàn tất thành công. |
| Test module `audit` + `TransactionTemplate` | Listener có tuân thủ commit, rollback và ghi DB không? | Use case đặt hàng phát event ở mọi nhánh nghiệp vụ. |
| Integration test qua cả hai module | Đặt hàng commit có dẫn đến thay đổi audit như mong đợi không? | Hệ thống tự bảo đảm retry, chống trùng hoặc giao chính xác một lần. |
| `ApplicationModules.verify()` | Phụ thuộc tĩnh qua module có hợp lệ không? | Bất kỳ thao tác runtime nào đã xảy ra. |

## 6. Khi dùng @ApplicationModuleListener: cần chờ kết quả bất đồng bộ

Spring Modulith cung cấp `@ApplicationModuleListener` cho trường hợp listener xử lý sự kiện theo transaction và bất đồng bộ, có transaction mới cho việc xử lý. Có thể **thay** phần triển khai listener ở mục 3.5 bằng phiên bản sau:

~~~java
package com.example.shop.audit;

import com.example.shop.order.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderAuditListener {

    private final AuditWriter writer;

    OrderAuditListener(AuditWriter writer) {
        this.writer = writer;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        writer.record(event);
    }
}
~~~

Trong biến thể này, `AuditWriter` vẫn có thể dùng transaction riêng như ví dụ trước, nhưng cần hiểu annotation của Spring Modulith đã cung cấp ngữ nghĩa transaction/bất đồng bộ cho listener; việc lồng thêm transaction mới ở writer có chi phí và phải được quyết định theo use case. Nếu cần tối giản triển khai thực tế, có thể thiết kế lại trách nhiệm ghi dữ liệu sao cho chỉ có **một ranh giới transaction rõ ràng** cho phần xử lý.

Với xử lý async, không nên assert ngay:

~~~java
transactions.executeWithoutResult(status ->
        publisher.publishEvent(event));

// Sai về tính ổn định: listener có thể chưa kịp chạy.
assertThat(entries.existsById(event.orderId())).isTrue();
~~~

Thay vào đó, dùng tiện ích chờ theo điều kiện, ví dụ Awaitility nếu dự án khai báo dependency test tương ứng:

~~~java
import static org.awaitility.Awaitility.await;
import java.time.Duration;

transactions.executeWithoutResult(status ->
        publisher.publishEvent(event));

await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(entries.existsById(event.orderId())).isTrue());
~~~

Đây là **đoạn thay thế phần assertion** trong test async, không phải một test class độc lập. Thời gian chờ cần phản ánh mức độ ổn định của môi trường CI. Spring Modulith còn có API `Scenario` hỗ trợ test các sự kiện và thay đổi trạng thái bất đồng bộ; có thể dùng thay cho thư viện chờ bên ngoài khi thích hợp.

Đối với biến thể async, cần xác minh cả hai phía của rollback: sau rollback, **không có side effect xảy ra kể cả sau khoảng chờ hợp lý**. Việc chứng minh một điều “không xảy ra” bằng một khoảng thời gian hữu hạn luôn có giới hạn; có thể kết hợp quan sát callback hoặc Event Publication Registry để tăng độ tin cậy của test.

### Lỗi đặc biệt với test @Transactional

~~~java
@ApplicationModuleTest
@Transactional
class RiskyAuditTests {

    @Test
    void test(...) {
        publisher.publishEvent(event);
        // Test thường rollback cuối hàm -> AFTER_COMMIT không chạy.
    }
}
~~~

Đây là **đoạn minh họa anti-pattern**, không phải mẫu test hoàn chỉnh. Trong test trên, lời gọi `publishEvent` diễn ra trong transaction do Spring Test mở; nếu cuối test rollback, callback `AFTER_COMMIT` không được kích hoạt. Đừng “sửa” bằng `fallbackExecution=true`: test cần thực sự kiểm tra đường commit nếu hành vi production được thiết kế để chạy sau commit.

## 7. Kiểm chứng ranh giới kiến trúc bằng ApplicationModules

Event được phân phối qua Spring, nhưng mã Java của `audit` vẫn **import kiểu `OrderPlaced`** thuộc `order.events`. Phụ thuộc đó cần được công bố và được phép ở ranh giới module. Bài kiểm tra kiến trúc:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` phát hiện vi phạm các quy tắc được Spring Modulith kiểm tra, chẳng hạn phụ thuộc vòng hoặc truy cập lớp không được công bố từ module khác. Với `audit`, import `order.events.OrderPlaced` thuộc named interface `events` là phụ thuộc được phép; import trực tiếp `order.internal.OrderRepository` thì trái ranh giới đã khai báo.

**Giới hạn:** `verify()` không chạy `OrderService.place`, không tạo transaction và không xác nhận listener đã ghi audit. Bài test kiến trúc và bài test transaction giải quyết những loại rủi ro khác nhau.

## 8. Khi listener thất bại: độ tin cậy của event publication

`@TransactionalEventListener(AFTER_COMMIT)` giúp tránh chạy listener khi transaction nguồn rollback, nhưng vẫn có các trường hợp lỗi:

1. Transaction nguồn commit thành công, listener gặp exception khi ghi database riêng.
2. Listener bất đồng bộ chưa xử lý xong thì tiến trình dừng.
3. Một event được phát lại hoặc listener chạy lại khiến side effect bị lặp.
4. Dữ liệu được đọc ở thời điểm xử lý có thể khác với snapshot lúc event xảy ra.

Nếu use case yêu cầu theo dõi các lần giao sự kiện cho transactional listener, Spring Modulith có **Event Publication Registry** cùng các lựa chọn lưu trữ. Khi được cấu hình, registry giúp ghi nhận việc công bố và trạng thái hoàn tất của listener, hỗ trợ các cơ chế xử lý lại theo thiết kế của hệ thống. Nó **không tự biến giao sự kiện thành “exactly once”**; code consumer cần xử lý idempotency và kiểm tra khả năng khôi phục.

Khi kiểm thử registry/database, cần dùng cấu hình lưu trữ và transaction tương ứng với production hoặc môi trường test có hành vi tương đương. Một module test cô lập dùng event in-memory không đủ để khẳng định cơ chế khôi phục bền vững đã hoạt động.

### Thiết kế test cho trường hợp thất bại

| Tình huống | Cách kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Publisher rollback | Phát event rồi `status.setRollbackOnly()`. | `AFTER_COMMIT` listener không xử lý. |
| Listener ghi DB thất bại | Giả lập lỗi có kiểm soát ở transaction riêng. | Dữ liệu nguồn đã commit không bị hiểu nhầm là chưa commit; lỗi downstream được ghi nhận. |
| Listener async | Chờ hiệu ứng cuối cùng với `Scenario`/Awaitility. | Test không phụ thuộc lịch scheduler từng mili giây. |
| Event lặp | Phát cùng định danh event hai lần theo đặc tả nghiệp vụ. | Không phát sinh side effect trùng ngoài dự kiến. |
| Tiến trình khởi động lại | Test tích hợp registry và persistence khi đã cấu hình. | Publication chưa hoàn tất được phát hiện/xử lý lại theo chính sách. |

Với kịch bản rollback, `PublishedEvents` vẫn có thể ghi nhận rằng code **đã gọi publish** trước khi rollback; điều đó không mâu thuẫn với việc transactional listener `AFTER_COMMIT` không thực hiện side effect. Hai phép quan sát đo hai giai đoạn khác nhau.

## 9. Đưa vào quality gate của CI

Một pipeline đủ sức ngăn hồi quy của Spring Modulith nên chạy các nhóm kiểm tra:

| Quality gate | Phát hiện rủi ro | Dấu hiệu thất bại mẫu |
| --- | --- | --- |
| `ApplicationModules.verify()` | Phụ thuộc sai hoặc vòng giữa module. | `audit` import `order.internal.*`. |
| `@ApplicationModuleTest` tại module phát | Use case không phát event hoặc payload sai. | `place` quên gọi `publishEvent`. |
| `@ApplicationModuleTest` tại module nhận | Sai pha transaction, rollback không được tôn trọng. | Audit được ghi trước commit hoặc vẫn ghi sau rollback. |
| Test database/async listener | Không lưu dữ liệu, ghi trùng hoặc sai thời điểm. | Test đợi quá hạn mà bản ghi audit không xuất hiện. |
| Integration test liên module / registry nếu dùng | Đứt luồng event, lỗi cấu hình transaction hay persistence. | Commit đơn hàng nhưng publication không được xử lý theo chính sách. |

Chạy test bằng tác vụ chuẩn đã cấu hình của dự án và đặt job CI thất bại khi các assertion quan trọng thất bại. Ví dụ có thể là `./gradlew test` hoặc `./mvnw test` trong môi trường tương ứng. Với test async, dùng timeout hợp lý và fixture độc lập để tránh flaky test; với database, cô lập dữ liệu giữa các test.

Không nên chỉ chạy architecture test: kiến trúc hợp lệ chưa chứng minh hành vi sau commit. Ngược lại, một test listener chạy đúng chưa chứng minh module không phụ thuộc vào lớp nội bộ của module khác.

## 10. Bài tập thực hành

Hệ thống có module `payment` phát `PaymentSucceeded`, module `notification` gửi email xác nhận sau commit. Hãy trả lời:

1. Nếu transaction thanh toán rollback, listener `@TransactionalEventListener(AFTER_COMMIT)` có gửi email không?
2. Nếu test gắn `@Transactional` mặc định rollback sau mỗi test, vì sao test có thể không bao giờ quan sát email?
3. Nếu listener gửi email qua tác vụ async, vì sao assertion ngay sau `publishEvent` có thể thất bại ngẫu nhiên?
4. Test nào chứng minh module `payment` thực sự phát event? Test nào chứng minh module `notification` thực sự xử lý event?
5. Vì sao cần thiết kế chống gửi email trùng khi sự kiện có thể bị xử lý lại?

**Đáp án tham khảo:**

1. Không, `AFTER_COMMIT` không chạy nếu transaction nguồn rollback thành công.
2. Transaction do Spring Test quản lý chưa commit và thường rollback khi kết thúc test; callback `AFTER_COMMIT` không được kích hoạt.
3. Vì listener có thể chạy sau trên executor khác; dùng chờ theo điều kiện hoặc công cụ test event phù hợp.
4. Test `payment` với `PublishedEvents` kiểm tra publication/payload; test `notification` hoặc integration test kiểm tra side effect của listener sau commit.
5. Event có thể được giao lại sau lỗi; định danh event và lưu dấu xử lý giúp không gửi thông báo nhiều lần ngoài ý muốn.

## 11. Checklist kiểm thử transactional event listener

- [ ] Xác định rõ event payload thuộc API công khai của module phát.
- [ ] Module nhận chỉ import named interface/API được phép; `ApplicationModules.verify()` chạy thành công.
- [ ] Chọn đúng kiểu listener và `TransactionPhase`; hiểu mặc định `AFTER_COMMIT`.
- [ ] Test commit dùng transaction thực sự kết thúc; không bị `@Transactional` trên test giữ transaction mở/rollback.
- [ ] Test rollback khẳng định listener `AFTER_COMMIT` không tạo side effect.
- [ ] Test khi không có transaction phù hợp với chính sách `fallbackExecution`.
- [ ] Thao tác ghi DB sau commit diễn ra trong transaction riêng phù hợp.
- [ ] Nếu dùng `@ApplicationModuleListener`, test chờ xử lý async bằng điều kiện trạng thái/event.
- [ ] Module nguồn có test `PublishedEvents`; module nhận có test side effect; luồng end-to-end được kiểm tra nếu cần.
- [ ] Cơ chế retry, registry và idempotency được kiểm thử theo cấu hình thực tế khi nghiệp vụ yêu cầu.
- [ ] Các test kiến trúc và tích hợp quan trọng đều nằm trong quality gate CI.

**Ghi nhớ:** Trong `@ApplicationModuleTest`, điều cần xác nhận không chỉ là “đã phát event” mà còn là **transaction đã commit hay rollback, listener thuộc pha nào và side effect đã thật sự hoàn tất chưa**. Phân biệt chính xác những bước này sẽ giúp kiểm chứng ranh giới module và luồng sự kiện một cách có thể lặp lại trong CI.

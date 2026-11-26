# Kiểm thử theo transaction cho transactional event listeners trong Spring Modulith

## 1. Vì sao phải kiểm thử theo transaction?

Trong Spring Modulith, một module có thể phát **application event** khi hoàn thành nghiệp vụ, còn module khác dùng **transactional event listener** để phản ứng sau khi transaction nguồn kết thúc. Ví dụ, module `orders` xác nhận đơn rồi phát `OrderConfirmed`; module `notifications` gửi email, `reporting` cập nhật projection và `loyalty` tính điểm.

Nếu chỉ unit test bằng cách gọi trực tiếp method `listener.on(event)`, chúng ta có thể chứng minh một phép tính đúng, nhưng **không chứng minh**:

- Listener đã được Spring đăng ký đúng kiểu event.
- Listener chạy ở đúng pha `BEFORE_COMMIT`, `AFTER_COMMIT` hoặc `AFTER_ROLLBACK`.
- Listener không phát sinh tác dụng phụ cho một transaction đã rollback.
- Transaction ghi database của listener đã **commit thật**, độc lập với transaction nguồn.
- Một publication chưa hoàn tất được lưu để khôi phục sau lỗi.
- Exception, retry, duplicate và xử lý bất đồng bộ có hành vi như kỳ vọng.

Bài học **Kiểm thử theo transaction** thuộc chương **Transactional listener** của dịch vụ `SPRING_MODULITH_APPLICATION_EVENTS`. Phạm vi của dịch vụ là giao tiếp giữa các module Spring Modulith bằng events, giảm phụ thuộc, bảo vệ boundary và xử lý đáng tin cậy bằng publisher, listener hậu commit, event publication registry, retry, kiểm thử, quan sát.

### 1.1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt test event **được phát** và test event **được xử lý sau commit**.
2. Dùng `TransactionTemplate` để kiểm soát thời điểm commit/rollback trong integration test.
3. Dùng `TestTransaction` để kết thúc transaction do Spring Test tạo.
4. Kiểm thử riêng các pha transactional listener và cấu hình `fallbackExecution`.
5. Kiểm tra listener bất đồng bộ với timeout và kết quả database thật, không phụ thuộc sleep cố định.
6. Kiểm tra trạng thái từng publication khi có nhiều listener và registry bền vững.
7. Mô phỏng lỗi, retry, duplicate, crash window, tự gọi method bỏ qua proxy và transaction propagation.
8. Thiết kế test dễ lặp lại, cô lập dữ liệu, có giá trị phát hiện regression về tính nhất quán.

## 2. Mô hình đúng: publish, commit và hoàn tất listener khác nhau

~~~mermaid
sequenceDiagram
    participant Test as Test
    participant O as orders service
    participant DB as DB / TX nguồn
    participant Pub as Event publisher
    participant L as Transactional listener
    participant R as Publication registry

    Test->>O: confirm(orderId)
    O->>DB: BEGIN transaction
    O->>DB: Update Order
    O->>Pub: publishEvent(OrderConfirmed)
    Pub->>R: Register publication (nếu cấu hình)
    O->>DB: COMMIT
    alt Commit thành công
        Pub-->>L: Dispatch AFTER_COMMIT
        L->>L: Process bằng transaction phù hợp
        L-->>R: Mark completed nếu thành công
    else Rollback
        Note over Pub,L: Không chạy AFTER_COMMIT
    end
    O-->>Test: Hoàn tất theo contract
~~~

Sơ đồ biểu diễn **luồng logic**; việc listener chạy trên thread nào, ghi registry ra sao và lúc nào đánh dấu completion phụ thuộc loại listener, backend và phiên bản Spring Modulith.

Trong test phải hỏi riêng ba câu:

| Câu hỏi | Kiểm chứng bằng gì? | Không đủ để kết luận điều gì? |
| --- | --- | --- |
| Publisher có tạo event đúng? | Ghi nhận event được phát và payload | Không chứng minh commit |
| Transaction nguồn đã commit? | Đọc trạng thái database trong transaction độc lập | Không chứng minh listener xử lý xong |
| Listener đã hoàn tất? | Side effect của module nhận + trạng thái publication nếu có | Không chứng minh consumer ngoài hệ thống đã hoàn tất |

**Nguyên tắc:** không thay thế một kiểm tra bằng một kiểm tra khác. Ví dụ, thấy `OrderConfirmed` trong `PublishedEvents` không đủ để khẳng định email chỉ được gửi **sau commit**.

## 3. Ma trận ngữ nghĩa của listener cần kiểm thử

| Kiểu listener | Mốc kích hoạt thông thường | Kết quả khi transaction nguồn rollback | Điều test phải đặc biệt kiểm tra |
| --- | --- | --- | --- |
| `@EventListener` đồng bộ mặc định | Ngay lúc `publishEvent(...)` | Có thể đã chạy trước rollback | Exception ảnh hưởng TX nguồn, tác dụng phụ ngoài DB |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Trước commit | Có thể đã chạy, nhưng transaction sau đó rollback | Không hiểu nhầm callback này là “đã commit” |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit thành công | Không chạy cho TX rollback | Transaction ghi mới, lỗi hậu commit |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Sau rollback | Chạy trong nhánh rollback | Cleanup/quan sát và transaction mới nếu muốn lưu DB |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Sau kết thúc TX ở cả hai nhánh | Có thể chạy sau rollback | Xử lý đúng cả hai outcome |
| `@ApplicationModuleListener` | Hậu commit, async, transaction xử lý riêng | Không xử lý event của TX rollback | Chờ async, lỗi/retry, registry, idempotency |

`@ApplicationModuleListener` của Spring Modulith là cách viết tiện dụng cho transactional listener bất đồng bộ, theo transaction riêng. Các ví dụ cần có hạ tầng async, transaction manager và dependencies phù hợp phiên bản ứng dụng.

### 3.1. Ba loại lỗi phải phân biệt

**Lỗi trước commit:** một callback đồng bộ hoặc transaction database thất bại, khiến transaction nguồn có thể rollback.

**Lỗi sau commit:** dữ liệu nguồn đã commit; listener gặp exception không thể “hoàn tác” transaction đã hoàn thành. Cần quan sát và recovery.

**Lỗi sau side effect nhưng trước completion:** listener có thể đã cập nhật database hoặc gọi dịch vụ ngoài thành công, nhưng publication vẫn còn chưa hoàn tất. Lần retry phải xử lý trùng an toàn.

Đây là ba nhóm test **khác nhau**. Chỉ tạo một test “listener ném exception” sẽ bỏ sót những tình huống quan trọng.

## 4. Tổ chức các tầng kiểm thử

| Tầng | Phạm vi | Ví dụ test | Hạn chế |
| --- | --- | --- | --- |
| **Unit test** | Java object, listener/service được gọi trực tiếp | Kiểm tra cách tính điểm hoặc mapping event | Không thực thi event infrastructure/transaction interceptor |
| **Module integration test** | Một application module và các dependency phù hợp | Kiểm tra publisher phát event, module boundary | Không tự động thay thế test nhiều module/registry backend |
| **Transaction integration test** | Spring context, DB, transaction manager | Kiểm tra commit/rollback, callback phase và `REQUIRES_NEW` | Có thể thiếu async/registry nếu không cấu hình |
| **Infrastructure integration test** | Registry persistence, executor, broker/adapter nếu có | Publication completed/incomplete, resubmit, restart | Chi phí cao hơn, cần cô lập dữ liệu |
| **End-to-end / fault injection** | Luồng nhiều module và điểm lỗi thực tế | DB đích lỗi, worker dừng, duplicate | Chậm hơn, cần chạy chọn lọc nhưng có giá trị cho reliability |

Phân tách tầng giúp test chạy nhanh mà vẫn chứng minh những contract quan trọng. Một unit test tốt vẫn cần thiết, nhưng không được dùng làm bằng chứng listener hoạt động đúng `AFTER_COMMIT`.

## 5. Chuẩn bị mô hình và event làm ví dụ

Sử dụng một ví dụ xuyên suốt: module `orders` xác nhận đơn; module `reporting` nhận event và cập nhật báo cáo. Contract event là một **record bất biến**.

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Vì `reporting` nằm ở module khác, `orders` cần công bố loại event qua API của module hoặc named interface:

~~~java
// orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

### 5.1. Publisher thực hiện nghiệp vụ bên trong transaction

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderConfirmed;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderManagement {
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    OrderManagement(OrderRepository orders,
                    ApplicationEventPublisher publisher,
                    Clock clock) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        var order = orders.findById(orderId).orElseThrow();
        order.requireCanConfirm();
        order.confirm();
        publisher.publishEvent(new OrderConfirmed(
            UUID.randomUUID(),
            orderId,
            clock.instant()
        ));
    }
}
~~~

`OrderRepository`, `Order`, các method domain và bean `Clock` là thành phần ứng dụng minh họa. Tùy JPA hoặc persistence khác, cần lưu thay đổi qua repository/managed entity đúng cách.

### 5.2. Listener hậu commit

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class SalesProjectionListener {
    private final SalesProjectionService projections;

    SalesProjectionListener(SalesProjectionService projections) {
        this.projections = projections;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        projections.recordConfirmedOrder(
            event.eventId(), event.orderId()
        );
    }
}
~~~

`SalesProjectionService` cần được module `reporting` triển khai với transaction và idempotency phù hợp. Khi test, không chỉ kiểm tra method `on()` được gọi, mà phải kiểm tra **thay đổi dữ liệu đã commit** và, khi registry được cấu hình, **trạng thái publication đúng listener**.

## 6. Kiểm thử các phase bằng TransactionTemplate

`TransactionTemplate` giúp test tự mở và kết thúc transaction, không phụ thuộc một test transaction mặc định bị rollback sau mỗi phương thức. Với một transaction manager thích hợp, việc `executeWithoutResult(...)` kết thúc bình thường sẽ commit nếu transaction không bị đánh dấu rollback-only.

### 6.1. Tạo phase probe cho integration test

Để kiểm tra chính xác callback nào được gọi, có thể dùng một bean probe thử nghiệm với các bộ đếm thread-safe.

~~~java
package com.example.shop.testing;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class PhaseProbe {
    private final AtomicInteger immediate = new AtomicInteger();
    private final AtomicInteger beforeCommit = new AtomicInteger();
    private final AtomicInteger afterCommit = new AtomicInteger();
    private final AtomicInteger afterRollback = new AtomicInteger();
    private final AtomicInteger afterCompletion = new AtomicInteger();

    public record ProbeEvent(String id) {}

    @EventListener
    public void immediate(ProbeEvent event) {
        immediate.incrementAndGet();
    }

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void beforeCommit(ProbeEvent event) {
        beforeCommit.incrementAndGet();
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(ProbeEvent event) {
        afterCommit.incrementAndGet();
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(ProbeEvent event) {
        afterRollback.incrementAndGet();
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void afterCompletion(ProbeEvent event) {
        afterCompletion.incrementAndGet();
    }

    public Snapshot snapshot() {
        return new Snapshot(
            immediate.get(), beforeCommit.get(),
            afterCommit.get(), afterRollback.get(),
            afterCompletion.get()
        );
    }

    public record Snapshot(
        int immediate,
        int beforeCommit,
        int afterCommit,
        int afterRollback,
        int afterCompletion
    ) {}
}
~~~

Đây là bean chuyên cho test; khi đưa vào dự án, đặt trong `src/test/java` và đăng ký bean theo cấu hình test phù hợp. Không nên đưa probe đếm số lần gọi vào production. Các handler ví dụ đều đồng bộ; nếu cố ý kết hợp async, cần cơ chế chờ thread-safe khác.

### 6.2. Test transaction commit

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class PhaseCommitIntegrationTest {

    @Autowired TransactionTemplate transactionTemplate;
    @Autowired ApplicationEventPublisher publisher;
    @Autowired PhaseProbe probe;

    @Test
    void dispatchesCommitPhases() {
        var before = probe.snapshot();

        transactionTemplate.executeWithoutResult(status -> {
            publisher.publishEvent(new PhaseProbe.ProbeEvent("commit-1"));

            // @EventListener đồng bộ chạy ngay khi publish.
            assertThat(probe.snapshot().immediate())
                .isEqualTo(before.immediate() + 1);

            // AFTER_COMMIT chưa được gọi trước khi TX kết thúc.
            assertThat(probe.snapshot().afterCommit())
                .isEqualTo(before.afterCommit());
        });

        var after = probe.snapshot();
        assertThat(after.beforeCommit()).isEqualTo(before.beforeCommit() + 1);
        assertThat(after.afterCommit()).isEqualTo(before.afterCommit() + 1);
        assertThat(after.afterRollback()).isEqualTo(before.afterRollback());
        assertThat(after.afterCompletion())
            .isEqualTo(before.afterCompletion() + 1);
    }
}
~~~

**Điều kiện của test:** có transaction manager đã cấu hình và bean `TransactionTemplate`. Nếu project không đăng ký sẵn `TransactionTemplate`, tạo bean riêng trong test từ `PlatformTransactionManager`. Khi nhiều test cùng chia sẻ `PhaseProbe`, cần reset/cô lập bean hoặc so sánh snapshot như ví dụ; không chạy những test này song song nếu chúng chia sẻ mutable counters mà không cô lập context.

### 6.3. Test transaction rollback

~~~java
@Test
void dispatchesRollbackPhases() {
    var before = probe.snapshot();

    transactionTemplate.executeWithoutResult(status -> {
        publisher.publishEvent(new PhaseProbe.ProbeEvent("rollback-1"));
        status.setRollbackOnly();
    });

    var after = probe.snapshot();
    assertThat(after.immediate()).isEqualTo(before.immediate() + 1);
    assertThat(after.beforeCommit()).isEqualTo(before.beforeCommit());
    assertThat(after.afterCommit()).isEqualTo(before.afterCommit());
    assertThat(after.afterRollback()).isEqualTo(before.afterRollback() + 1);
    assertThat(after.afterCompletion())
        .isEqualTo(before.afterCompletion() + 1);
}
~~~

Ví dụ này thuộc cùng test class ở mục trước. Điểm cần chứng minh là `@EventListener` đồng bộ **có thể đã chạy** dù transaction rollback, còn `AFTER_COMMIT` không chạy. `BEFORE_COMMIT` không được gọi ở đường rollback-only này vì transaction manager không đi qua pha before-commit cho một transaction đã quyết định rollback.

Không nên áp dụng kỳ vọng này máy móc cho mọi đường lỗi của mọi transaction manager; integration test phải chạy với transaction manager thật của dự án.

### 6.4. Kiểm thử fallbackExecution

Một `@TransactionalEventListener` không có transaction nguồn thường không thực thi theo mặc định:

~~~java
@TransactionalEventListener
void on(ProbeEvent event) {
    // Không mặc định chạy nếu publisher ngoài transaction.
}
~~~

Nếu đặt `fallbackExecution = true`, callback có thể được gọi ngoài transaction. Test cần xác nhận **cả hai đường**:

- Phát event bên trong transaction và commit: listener chạy theo phase.
- Phát event không có transaction: listener chỉ chạy khi hợp đồng fallback cho phép.

Đừng bật fallback để che việc `@Transactional` trên service không được proxy áp dụng hoặc bị gọi sai đường.

## 7. Bẫy phổ biến nhất: test @Transactional tự rollback

Spring Test thường rollback transaction của test có `@Transactional` sau khi phương thức test kết thúc. Điều này có lợi cho việc dọn dữ liệu, nhưng dễ gây hiểu nhầm nếu đang kiểm thử `AFTER_COMMIT`.

### 7.1. Ví dụ test có vấn đề

~~~java
@SpringBootTest
@Transactional
class OrderListenerTest {

    @Autowired OrderManagement orders;
    @Autowired SalesProjectionReader projections;

    @Test
    void wrongAssumption() {
        UUID orderId = createReadyOrder();
        orders.confirm(orderId);

        // Transaction test vẫn đang hoạt động.
        // AFTER_COMMIT chưa có lý do để chạy tại đây.
        assertThat(projections.hasOrder(orderId)).isTrue();
    }
}
~~~

Đây là **phản ví dụ**; `createReadyOrder()` là fixture giả định. Lời gọi `orders.confirm(...)` với propagation `REQUIRED` thường tham gia transaction do Spring Test mở sẵn. Khi test kết thúc và tự rollback, listener `AFTER_COMMIT` **không được kích hoạt**. Nếu assertion báo projection còn thiếu, không có nghĩa code production sai.

### 7.2. Cách 1: dùng TransactionTemplate và không đặt @Transactional trên test

Một test không có transaction bao ngoài có thể gọi service `@Transactional` qua Spring proxy. Khi service return thành công, transaction nguồn của nó thường đã commit, nên listener hậu commit có cơ hội được xử lý.

Hoặc test tự mở transaction bằng `TransactionTemplate` để kiểm soát rõ mốc commit. Đây thường là cách **dễ đọc và ít phụ thuộc vào test framework** khi mục tiêu là xem hành vi sau commit.

### 7.3. Cách 2: dùng TestTransaction để kết thúc transaction của test

`TestTransaction` là API Spring Test giúp điều khiển **transaction do test framework quản lý** khi nó đang hoạt động. Có thể đặt `flagForCommit()` rồi gọi `end()` để kết thúc transaction test bằng commit.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class OrderCommitListenerTest {

    @Autowired OrderManagement orders;
    @Autowired SalesProjectionReader projections;

    @Test
    void waitsForActualCommit() {
        UUID orderId = createReadyOrderFixture();
        orders.confirm(orderId);

        TestTransaction.flagForCommit();
        TestTransaction.end();

        // Sau đây dùng điều kiện chờ có timeout nếu listener async.
        awaitProjection(orderId);
        assertThat(projections.hasOrder(orderId)).isTrue();
    }
}
~~~

`createReadyOrderFixture()` và `awaitProjection(...)` là helpers do dự án cần triển khai, không phải phương thức Spring tự sinh. `TestTransaction.end()` chỉ có hiệu lực khi transaction test thực sự đang hoạt động; test phải được cấu hình bằng `TransactionalTestExecutionListener` và transaction manager phù hợp. Nếu muốn bắt đầu một transaction test khác sau `end()`, có thể dùng `TestTransaction.start()` theo API Spring Test.

### 7.4. Cách 3: @Commit hoặc @Rollback(false) — dùng có kiểm soát

Spring Test cung cấp `@Commit` hoặc `@Rollback(false)` để yêu cầu commit ở cuối test. Nhưng assertion đặt **bên trong method test** vẫn được thực hiện trước thời điểm transaction kết thúc, nên không tự giải quyết kiểm thử hậu commit khi assert ngay.

Ngoài ra, dữ liệu đã commit có thể làm bẩn những test sau. Với kịch bản cần quan sát kết quả **ngay sau commit trong cùng test method**, `TestTransaction.end()` hoặc `TransactionTemplate` thường tường minh hơn.

## 8. Kiểm thử side effect chỉ xuất hiện sau commit

Một test đúng cần chứng minh **hai vế**:

1. Khi transaction nguồn **commit**, hậu quả được tạo ra.
2. Khi transaction nguồn **rollback**, hậu quả không được tạo ra.

Đừng chỉ kiểm tra một vế “commit chạy được”, vì một `@EventListener` đồng bộ gửi email trước commit vẫn có thể làm test commit pass dù thiết kế sai.

### 8.1. Email thông báo là ví dụ dễ quan sát

Listener:

~~~java
@Component
class ConfirmationNotificationListener {
    private final ConfirmationSender sender;

    ConfirmationNotificationListener(ConfirmationSender sender) {
        this.sender = sender;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderConfirmed event) {
        sender.send(event.eventId(), event.orderId());
    }
}
~~~

Trong integration test, có thể dùng fake/mock `ConfirmationSender` để ghi lại yêu cầu gửi. Test gọi use case trong transaction rồi **rollback** và xác nhận fake không nhận bất cứ yêu cầu gửi nào. Với đường **commit**, fake phải nhận đúng sự kiện tương ứng. Nếu callback bất đồng bộ, đồng bộ hóa/chờ rõ ràng theo cơ chế test.

**Không gửi email thật** trong test commit/rollback. Adapter giả nên phản ánh đúng contract: request đã được gọi sau commit, không khẳng định người dùng thực tế đã nhận email.

### 8.2. Kiểm tra trạng thái nguồn song song với side effect

Trong test rollback, cũng phải đọc lại order bằng transaction độc lập để xác nhận trạng thái nguồn chưa chuyển thành `CONFIRMED`. Một mock không được gọi **không đủ** nếu service thực ra chưa phát event hoặc listener chưa được đăng ký.

Đặc biệt, nếu test chỉ gọi `publishEvent(...)` trực tiếp mà không đổi trạng thái database, nó có thể chứng minh pha listener nhưng **không chứng minh tính nhất quán của use case**.

## 9. Kiểm thử AFTER_COMMIT ghi database trong transaction riêng

Một callback `@TransactionalEventListener(AFTER_COMMIT)` mặc định không tự tạo transaction mới. Tài nguyên transaction nguồn có thể vẫn gắn với thread trong lúc callback chạy; ghi database mới mà không có một transaction commit thích hợp là một bẫy.

### 9.1. Thiết kế production dễ kiểm thử

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class AfterCommitReportingListener {
    private final ProjectionWriter writer;

    AfterCommitReportingListener(ProjectionWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderConfirmed event) {
        writer.write(event);
    }
}

@Service
class ProjectionWriter {
    private final ProjectionRepository repository;

    ProjectionWriter(ProjectionRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(OrderConfirmed event) {
        repository.applyIdempotently(event.eventId(), event.orderId());
    }
}
~~~

Các lớp `ProjectionRepository`, `applyIdempotently(...)` là mã ứng dụng cần xây dựng. Ví dụ đặt hai class package-private để trình bày ngắn; tổ chức file Java đúng chuẩn khi triển khai.

Tách listener và writer thành **hai Spring beans** để tránh self-invocation làm `@Transactional` mất hiệu lực khi dùng Spring proxy.

### 9.2. Điều gì cần assert?

- Transaction `orders` commit và order có trạng thái `CONFIRMED`.
- Projection xuất hiện khi đọc từ transaction **mới**, không chỉ nằm trong persistence context của test.
- Khi `ProjectionWriter` gặp lỗi, transaction module `reporting` rollback, nhưng order nguồn đã commit **không bị hoàn tác**.
- Nếu registry bật, publication của listener thất bại vẫn có thể quan sát và phục hồi.
- Khi xử lý lại event, projection không được tăng số lần.

Không chỉ dùng Mockito `verify(repository).save(...)`: việc method `save` được gọi chưa chứng minh transaction mới đã commit.

### 9.3. Không thêm REQUIRES_NEW máy móc vào mọi @ApplicationModuleListener

`@ApplicationModuleListener` của Spring Modulith đã kết hợp semantics transaction riêng. Với listener loại này, cần hiểu cấu hình thực tế trước khi thêm một transaction `REQUIRES_NEW` khác, tránh tạo thêm ranh giới giao dịch không cần thiết.

Điều test vẫn phải chứng minh là **dữ liệu đã được commit** và nếu lỗi xảy ra, publication có trạng thái phục hồi đúng.

## 10. Kiểm thử bất đồng bộ: chờ điều kiện, không chờ một khoảng thời gian đoán mò

`@ApplicationModuleListener` chạy bất đồng bộ theo mô hình Spring Modulith. Vì thế việc assertion ngay sau `orders.confirm(...)` có thể xảy ra **trước khi listener hoàn tất**.

### 10.1. Phản ví dụ

~~~java
orders.confirm(orderId);
Thread.sleep(500); // Không phải hợp đồng về thời gian xử lý.
assertThat(projections.hasOrder(orderId)).isTrue();
~~~

Sleep cố định có thể quá ngắn trên CI chậm hoặc quá dài trong máy local. Ngoài ra, nó không giúp giải thích test thất bại do listener không được gọi, do database lỗi hay do executor bị nghẽn.

### 10.2. Dùng Awaitility hoặc cơ chế polling có timeout

Ví dụ dùng Awaitility:

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

void awaitProjection(UUID orderId) {
    await()
        .atMost(Duration.ofSeconds(8))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
            assertThat(projections.hasOrder(orderId)).isTrue()
        );
}
~~~

`projections` là bean truy vấn của test; cần đảm bảo mỗi lần poll đọc được dữ liệu đã commit (không bị cache hoặc transaction test kéo dài làm đọc snapshot cũ). Tốc độ poll, timeout và tài nguyên CI cần chọn phù hợp, không xem các con số trong ví dụ là cấu hình chuẩn cho mọi dự án.

### 10.3. Chờ “điều đúng”, không chỉ chờ method được gọi

Nếu listener có thể hoàn tất method nhưng ghi database rollback, latch đánh dấu “method đã gọi” **không chứng minh** thành công. Tùy yêu cầu hãy đợi:

- Dòng projection xuất hiện trong database đích.
- Bản ghi deduplication đã commit.
- Publication được registry ghi completed.
- Một request đã được fake adapter ghi nhận đúng một lần.

Muốn chứng minh handler chưa chạy **trước commit**, có thể giữ transaction nguồn mở trong test với latch và quan sát listener chưa sinh side effect; sau đó chủ động commit rồi chờ kết quả. Cần thiết kế đồng bộ hóa không deadlock, không dựa vào timing tùy ý.

### 10.4. Thread context không phải bằng chứng transaction

Async listener chạy trên worker không tự mang transaction nguồn, SecurityContext, MDC hoặc HTTP request attributes của thread phát event. Unit test gọi trực tiếp method listener sẽ **không thấy** khác biệt này.

Với kịch bản phụ thuộc actor/tenant/correlation, hãy đưa dữ liệu cần thiết vào event hoặc contract phù hợp, kiểm thử khi request đã kết thúc, và xác nhận context được thiết lập/dọn ở worker. Không dùng ThreadLocal của request để xác định tính đúng của sự kiện sau restart.

## 11. Kiểm thử @ApplicationModuleTest và PublishedEvents

Spring Modulith cung cấp `@ApplicationModuleTest` để khởi tạo ngữ cảnh tập trung vào một application module, và `PublishedEvents` hỗ trợ quan sát các event phát ra trong bài test.

### 11.1. Khi nào dùng module test?

Phù hợp để kiểm tra:

- Use case `orders.confirm(...)` có phát `OrderConfirmed` đúng dữ liệu không.
- Module `orders` không cần import implementation nội bộ của `reporting`.
- Event được phát cho đúng mốc nghiệp vụ, không phát khi validation thất bại.
- Việc công bố event contract có phù hợp ranh giới module không.

Ví dụ khung:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrdersEventTest {

    @Autowired OrderManagement orders;

    @Test
    void publishesEventForConfirmedOrder(PublishedEvents events) {
        UUID orderId = createReadyOrderFixture();
        orders.confirm(orderId);

        // Kiểm tra events.ofType(OrderConfirmed.class)
        // và payload bằng API PublishedEvents của phiên bản dự án.
    }
}
~~~

`PublishedEvents` là công cụ kiểm tra **sự kiện đã được công bố**, không chứng minh listener ngoài module được giao đúng phase hoặc hoàn tất sau commit. Cú pháp assertion chi tiết nên đối chiếu version API, thay vì tự suy từ ví dụ của một phiên bản khác.

### 11.2. Vì sao vẫn cần test nhiều module?

Một module test có thể không load backend registry, listener của module nhận hoặc adapter thật. Những kiểm tra sau nên nằm ở integration test phù hợp:

- Listener của `reporting` có được đăng ký trong Spring context đúng không?
- `@ApplicationModuleListener` có được kích hoạt sau commit và hoàn thành trong transaction riêng không?
- Registry persistence có tạo và đánh dấu publication như kỳ vọng không?
- Side effect ở module nhận có bền vững qua restart/retry không?

Spring Modulith còn có:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTest {
    @Test
    void validatesBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` xác minh các dependency theo cấu trúc module; nó **không thay thế** kiểm thử commit/rollback hoặc listener bất đồng bộ.

## 12. Kiểm thử event publication registry

Khi sử dụng **event publication registry** của Spring Modulith với backend lưu bền, publication có thể được theo dõi theo **listener đích**. Ví dụ `OrderConfirmed E-7` có:

~~~text
Publication P1: E-7 -> notifications listener
Publication P2: E-7 -> reporting listener
Publication P3: E-7 -> loyalty listener
~~~

Nếu `notifications` thành công còn `reporting` thất bại, trạng thái của P1 và P2 cần được phân biệt. Không được coi “event đã phát” hay “một listener đã xử lý” là mọi publication hoàn tất.

### 12.1. Test cần backend registry thật

Để xác minh transaction kết hợp publication, test cần:

1. Dependency backend tương ứng (JDBC, JPA, MongoDB hoặc backend được hỗ trợ).
2. Schema/migration registry được tạo đúng trong database test.
3. Transaction manager dùng đúng với nơi ghi nghiệp vụ và publication.
4. Listener thực sự thuộc nhóm được registry quản lý.
5. Cách đọc trạng thái publication được hỗ trợ trong phiên bản dự án.
6. Cơ chế khôi phục/resubmit được gọi hoặc cấu hình theo chính sách test.

Đừng suy từ việc có một bean tên `EventPublicationRepository` rằng toàn bộ luồng đã được cấu hình đúng; cần xác nhận bản ghi được ghi, commit, truy vấn và đánh dấu hoàn tất.

### 12.2. Ma trận test publication

| Kịch bản | Kết quả cần thấy |
| --- | --- |
| Nguồn commit, listener thành công | Publication được ghi nhận và hoàn tất theo semantics backend |
| Nguồn rollback | Không còn publication **đã commit** cho sự thật nghiệp vụ bị rollback khi backend chia sẻ transaction phù hợp |
| Listener ném exception | Không ghi completed sai; publication còn được theo dõi để phục hồi |
| Một trong hai listener lỗi | Chỉ publication của listener thất bại còn chưa hoàn tất |
| Resubmit sau khi sửa hạ tầng | Listener xử lý lại và publication được hoàn tất |
| Process dừng sau commit nguồn | Publication đã commit còn có thể được truy vấn sau restart |
| Side effect thành công rồi crash trước completion | Xử lý lại không tạo tác dụng phụ trùng |
| Nâng cấp class/schema event | Payload cũ còn deserialize đúng hoặc có migration |

### 12.3. Không tự bịa API hoặc tên bảng

API truy vấn publication, cách resubmit, retention và tên cột lưu trạng thái có thể khác nhau theo phiên bản Spring Modulith/backend. Test nên sử dụng public API của phiên bản được pin hoặc một adapter test truy vấn dữ liệu theo schema thực.

Không nên viết assertion dựa trên tên bảng hoặc phương thức chưa xác minh như `repository.markCompleted(eventId)`. Một `eventId` có thể tương ứng **nhiều listener/publication**.

### 12.4. Phân biệt “chưa hoàn tất” và “không được ghi”

Nếu test hỏi “số publication chưa hoàn tất = 0”, có ít nhất hai khả năng:

- Tất cả publication kỳ vọng đã hoàn tất.
- **Không có publication nào được ghi** do registry/backend hoặc listener bị cấu hình sai.

Vì vậy, test nên kiểm tra cả **sự xuất hiện của publication khi phát event** và **trạng thái hoàn tất phù hợp**. Nếu backend dọn publication hoàn tất ngay, phải thiết kế cách quan sát kết quả được hỗ trợ hoặc phối hợp test side effect/metrics một cách đúng đắn.

## 13. Mô phỏng lỗi và kiểm thử cơ chế retry

Một listener cần trả về đúng ngữ nghĩa **thành công hoặc thất bại**.

### 13.1. Phản ví dụ: nuốt exception

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    try {
        projections.recordConfirmedOrder(
            event.eventId(), event.orderId()
        );
    } catch (RuntimeException ex) {
        log.error("Projection failed", ex);
        // Return bình thường -> publication có thể bị đánh dấu completed.
    }
}
~~~

Nếu nghiệp vụ cần retry, hành vi trên có thể tạo **false completion**: registry báo listener xong dù dữ liệu chưa được cập nhật.

Phiên bản có thể phục hồi tốt hơn:

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    try {
        projections.recordConfirmedOrder(
            event.eventId(), event.orderId()
        );
    } catch (RuntimeException ex) {
        log.error(
            "Projection failed for eventId={}",
            event.eventId(),
            ex
        );
        throw ex;
    }
}
~~~

### 13.2. Quy trình fault-injection

1. Dùng một test fake repository hoặc backend test có thể bật cờ **fail once**.
2. Commit transaction `orders`, để listener nhận event.
3. Lần xử lý đầu ném exception trước khi tác vụ hoàn tất.
4. Xác minh dữ liệu nguồn vẫn commit, dữ liệu listener chưa được cập nhật thành công.
5. Xác minh publication của listener chưa completed (nếu registry được cấu hình).
6. Tắt chế độ lỗi.
7. Gọi resubmit/recovery theo API hoặc cấu hình của phiên bản ứng dụng.
8. Chờ điều kiện thành công bằng timeout.
9. Xác minh dữ liệu đích chỉ được ghi một lần và publication chuyển sang trạng thái hoàn tất.

Không giả định **Spring Modulith mặc định retry tự động vô hạn**. Việc khôi phục, lịch chạy, điều kiện retry hoặc hành động vận hành phải được khai báo và kiểm thử theo cấu hình.

### 13.3. Lỗi sau commit có thể không quay lại HTTP caller

Với listener bất đồng bộ, exception thường xảy ra trên worker và được xử lý qua executor/framework, không tự ném lại vào method controller đã trả kết quả.

Với callback `AFTER_COMMIT` **đồng bộ**, exception có thể ảnh hưởng đường kết thúc transaction/caller dù database đã commit; điều quan trọng là **transaction nguồn đã commit không thể bị rollback ngược lại**. Test nên kiểm tra trạng thái database thực, không suy từ mã HTTP trả ra.

## 14. Kiểm thử idempotency sau crash window

Một lỗi quan trọng:

~~~mermaid
sequenceDiagram
    participant Reg as Registry
    participant L as Loyalty listener
    participant DB as Loyalty DB

    Reg-->>L: Deliver event E
    L->>DB: Begin TX
    L->>DB: Cộng điểm và ghi eventId
    L->>DB: Commit TX
    Note over L,Reg: Process crash trước khi mark completed
    Reg-->>L: Resubmit cùng event E
    L->>DB: Đã áp dụng eventId?
    DB-->>L: Có, bỏ qua cộng điểm
    L-->>Reg: Thành công
    Reg->>Reg: Mark completed
~~~

### 14.1. Cơ chế chống duplicate trong module nhận

Ví dụ bảng lưu dấu:

~~~sql
CREATE TABLE loyalty_processed_events (
    event_id VARCHAR(36) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Luồng xử lý:

~~~text
BEGIN transaction loyalty
  INSERT eventId vào bảng processed_events với unique constraint
  Nếu eventId đã tồn tại:
      không cộng điểm lần nữa
  Nếu insert thành công:
      cộng điểm theo chính sách module loyalty
COMMIT transaction loyalty
~~~

**Không chỉ kiểm tra rồi mới insert trong hai thao tác không có khóa.** Hai lượt xử lý đồng thời có thể cùng đọc “chưa tồn tại”; unique constraint hoặc cập nhật atomic mới bảo vệ khỏi race. Việc insert dấu xử lý và cập nhật điểm phải nằm trong transaction thích hợp, để không có trạng thái “đã xử lý nhưng chưa cộng điểm”.

### 14.2. Bộ test idempotency tối thiểu

- Gửi cùng `eventId` hai lần **tuần tự**.
- Gửi cùng `eventId` bằng hai thread **đồng thời**.
- Cho transaction listener rollback giữa chừng, sau đó retry.
- Cho nghiệp vụ commit nhưng publication chưa completed, sau đó resubmit.
- Tạo hai event khác nhau cho cùng `orderId` và kiểm tra khóa deduplication có đúng ý nghĩa nghiệp vụ.
- Với email/provider bên ngoài, dùng fake adapter để mô phỏng timeout **sau khi provider đã nhận yêu cầu**.

Local transaction không commit nguyên tử với email/HTTP provider. Nếu tác dụng phụ không thể thực hiện idempotently, test phải thể hiện phương án đối soát/compensation hoặc giới hạn mức bảo đảm chấp nhận được.

## 15. Kiểm thử transaction propagation và lỗi proxy

Một listener có thể chạy đúng phase nhưng use case thực tế lại mở transaction không đúng như đội phát triển nghĩ.

### 15.1. REQUIRED tham gia transaction bên ngoài

~~~java
@Transactional
public void checkout(UUID orderId) {
    orders.confirm(orderId); // REQUIRED có thể tham gia TX checkout.
    billing.prepareInternalInvoice(orderId);
}
~~~

Nếu `orders.confirm(...)` phát event, listener `AFTER_COMMIT` phải chờ **transaction checkout bên ngoài commit**. Nếu bước billing thất bại khiến transaction checkout rollback, listener `AFTER_COMMIT` không được tạo side effect.

Test cần gọi **đúng entry point `checkout(...)`**, không chỉ unit test riêng `confirm(...)`.

### 15.2. REQUIRES_NEW có thể commit sớm

Giả sử một method con `REQUIRES_NEW` phát event rồi commit riêng, còn transaction bên ngoài rollback sau đó. Listener hậu commit của **transaction con** vẫn có thể chạy vì transaction con thật sự đã commit.

Test nên xác nhận semantics này nếu hệ thống chủ động sử dụng `REQUIRES_NEW`. Nếu đó không phải hành vi nghiệp vụ mong muốn, sửa ranh giới transaction thay vì viết test giả định rằng “outer rollback luôn hủy mọi event”.

### 15.3. Checked exception và rollback rule

Theo cấu hình mặc định phổ biến của Spring, runtime exception/Error thường kích hoạt rollback, trong khi checked exception không mặc nhiên được dùng như rollback trigger. Có thể khai báo `rollbackFor` hoặc policy tương ứng.

Viết hai test khi nghiệp vụ phụ thuộc loại exception:

- Throw `RuntimeException` và xác minh transaction rollback, `AFTER_COMMIT` không chạy.
- Throw checked exception theo rollback rule được cấu hình, xác minh commit/rollback đúng như hợp đồng.

Không chỉ assert phương thức ném exception; cần đọc lại database và side effect để biết transaction thực sự kết thúc thế nào.

### 15.4. Self-invocation làm mất @Transactional

~~~java
@Service
class OrderBatchService {
    void process(UUID orderId) {
        confirm(orderId); // Lời gọi nội bộ không đi qua proxy mặc định.
    }

    @Transactional
    public void confirm(UUID orderId) {
        publisher.publishEvent(new OrderConfirmed(
            UUID.randomUUID(), orderId, Instant.now()
        ));
    }
}
~~~

Khi dùng Spring AOP proxy thông thường, `this.confirm(...)` không qua transaction interceptor. Nếu không có transaction khác ở ngoài, transactional listener mặc định có thể **không chạy**. Test phải gọi đúng đường nghiệp vụ, xác minh transaction có hoạt động và tránh dùng `fallbackExecution = true` để che vấn đề.

Một giải pháp thường rõ ràng hơn là tách method có transaction sang **một Spring bean khác** hoặc dùng `TransactionTemplate` khi cần điều khiển tường minh.

## 16. Kiểm thử ranh giới module và sự phát triển event contract

Spring Modulith tổ chức application modules theo boundary. Test transaction hoàn hảo nhưng consumer import `orders.internal.OrderRepository` vẫn là một vi phạm thiết kế.

### 16.1. Contract giữa hai module

Module `orders` sở hữu `OrderConfirmed`. Module `reporting` chỉ nên phụ thuộc package API công khai hoặc named interface như `orders::events`, không phụ thuộc entity/repository nội bộ.

~~~java
// reporting/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders::events"
)
package com.example.shop.reporting;
~~~

Kiểm tra module dependency bằng `ApplicationModules.of(ShopApplication.class).verify()`.

### 16.2. Test event tồn đọng qua nâng cấp

Nếu registry lưu serialized event, một event chưa hoàn tất có thể được phát lại **sau khi ứng dụng deploy version mới**. Thay record, đổi package hoặc xóa field có thể khiến payload cũ không còn deserialize được.

Thêm compatibility test:

1. Chuẩn bị dữ liệu publication **được tạo bằng kiểu event cũ** (mẫu đã biết/fixture đúng serializer).
2. Khởi động ứng dụng với event class và serialization của version mới.
3. Thử đọc lại và giao publication theo cơ chế phiên bản.
4. Xác minh listener xử lý dữ liệu cũ đúng ngữ nghĩa hoặc có migration rõ ràng.

Đừng chỉ unit test constructor record mới; cần kiểm tra **payload đã lưu bền** nếu nó là một phần cam kết recovery.

## 17. Cô lập dữ liệu test và tránh flakiness

Một bài test transaction có thể pass riêng nhưng fail trong cả suite vì dữ liệu, thread hoặc publication từ test khác còn tồn tại.

### 17.1. Quy tắc cô lập

- Tạo `eventId` và `orderId` riêng cho mỗi test.
- Không dùng cùng một entity state mutable cho các bài test chạy song song.
- Khi bật registry, làm sạch dữ liệu **theo cách được hỗ trợ** trước/sau suite; không xóa bừa publication đang được worker khác xử lý.
- Tránh để test phụ thuộc vào thứ tự test methods.
- Với async listener, đợi công việc kỳ vọng hoàn tất trước khi dọn database.
- Nếu có nhiều transaction managers, chỉ rõ test dùng manager phù hợp.
- Với mock/fake singleton đếm số lần gọi, reset theo test hoặc dùng số đếm chênh lệch có kiểm soát.
- Không chạy song song các test dùng chung registry/executor và cùng dữ liệu nếu chưa thiết kế isolation.
- Với database transaction semantics quan trọng, dùng môi trường test phản ánh DB production (ví dụ containerized database) thay vì giả định in-memory DB có hành vi hoàn toàn giống.

### 17.2. Transaction test còn đang mở có thể che dữ liệu thật

Một assertion sau commit nhưng vẫn chạy trong transaction test mở từ trước có thể đọc **snapshot/cached entity** không phản ánh DB vừa được listener cập nhật. Vì thế test nên đọc từ một transaction mới hoặc phương pháp truy vấn tường minh phù hợp.

Khi test dùng `TestTransaction.end()`, hãy nhận biết transaction test đã kết thúc và không suy rằng mọi repository access sau đó vẫn có cùng isolation hoặc persistence context.

### 17.3. Tối ưu thời gian mà vẫn chứng minh kết quả

Tập trung test theo lớp:

1. Unit test nhanh cho mọi nhánh logic.
2. Một vài transaction integration test cho phase và commit/rollback.
3. Test registry với backend thật cho completion/retry.
4. Một số fault-injection/end-to-end test cho crash window.

Không nhất thiết chạy một broker và nhiều database cho **mọi** unit test. Nhưng các tình huống phụ thuộc độ bền publication phải được kiểm chứng với hạ tầng thực tế ở những test quan trọng.

## 18. Bài tập thực hành: phát hiện một bug hậu commit

### 18.1. Bối cảnh

Một nhóm phát triển có module `orders` và `reporting`:

~~~java
@Transactional
public void confirm(UUID orderId) {
    var order = orders.findById(orderId).orElseThrow();
    order.confirm();
    publisher.publishEvent(new OrderConfirmed(
        UUID.randomUUID(), orderId, clock.instant()
    ));
}
~~~

Handler:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void on(OrderConfirmed event) {
    projections.save(new OrderProjection(event.orderId()));
}
~~~

Một test `@SpringBootTest @Transactional` gọi `confirm(...)` rồi ngay lập tức kiểm tra projection; test thất bại. Sau đó lập trình viên đổi handler sang `@EventListener` và test lại pass. Khi triển khai production, có lúc database ghi projection không như kỳ vọng.

### 18.2. Phân tích các lỗi

1. Test tự rollback khiến `AFTER_COMMIT` không chạy.
2. Đổi sang `@EventListener` làm mất bảo đảm **chỉ phản ứng sau commit**, nên projection có thể xuất hiện cho đơn rollback.
3. Handler `AFTER_COMMIT` ghi database chưa có **transaction mới rõ ràng**; cần kiểm chứng commit thật.
4. Nếu cần recovery khi reporting lỗi, chỉ thêm `AFTER_COMMIT` không đủ; phải đánh giá registry/handler failure/idempotency.

### 18.3. Yêu cầu sửa

- Trả lại semantics `AFTER_COMMIT` hoặc dùng `@ApplicationModuleListener` phù hợp.
- Tách phần ghi projection sang bean dùng transaction riêng khi cần.
- Dùng `TransactionTemplate` hoặc `TestTransaction.end()` để thực sự commit transaction nguồn trong integration test.
- Tạo test rollback và khẳng định không có projection mới cho đơn không commit.
- Nếu handler async, đợi projection xuất hiện bằng polling có timeout.
- Bật backend registry và tạo test listener lỗi, resubmit, duplicate nếu dữ liệu reporting cần độ tin cậy cao.
- Kiểm tra module `reporting` chỉ phụ thuộc contract công khai từ `orders`.

### 18.4. Bảng nghiệm thu

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| Source commit | Order `CONFIRMED` và projection được tạo sau commit |
| Source rollback | Order không `CONFIRMED`, projection không được tạo |
| Reporting DB fail | Order vẫn commit, lỗi listener được theo dõi |
| Retry thành công | Projection được tạo và publication hoàn tất |
| Retry cùng event hai lần | Không tạo hai projection/không nhân đôi số liệu |
| Đổi code listener sau deploy | Publication cũ còn đọc được hoặc migration rõ |
| Module boundary verify | Không có dependency vào `orders.internal` từ `reporting` |

### 18.5. Nâng cao: kiểm tra thời điểm mà không dựa vào sleep

Thiết kế test có hai tín hiệu đồng bộ:

1. Publisher phát event trong một transaction **chưa cho phép commit**.
2. Test xác nhận không có tác dụng phụ của `AFTER_COMMIT`.
3. Test cho phép transaction nguồn commit.
4. Test đợi có timeout cho dấu hiệu listener thành công.

Với listener async hoặc nhiều worker, cần dùng `CountDownLatch`, `CompletableFuture` hoặc cơ chế barrier tương ứng một cách **không gây deadlock**. Test chứng minh **thứ tự điều kiện**, không chỉ “đã ngủ đủ 500 ms”.

## 19. Checklist kiểm thử theo transaction

- [ ] Biết rõ transaction nguồn bắt đầu và kết thúc ở đâu.
- [ ] Không lấy `publishEvent(...)` hoặc `PublishedEvents` làm bằng chứng database đã commit.
- [ ] Test được cả commit và rollback, không chỉ happy path.
- [ ] Chọn đúng `@EventListener`, các phase `@TransactionalEventListener` hoặc `@ApplicationModuleListener`.
- [ ] Có test xác minh `AFTER_COMMIT` không chạy khi nguồn rollback.
- [ ] Nếu test có `@Transactional`, đã xử lý bẫy test tự rollback bằng `TestTransaction` hoặc thiết kế khác.
- [ ] Nếu callback hậu commit ghi database, đã xác minh có transaction mới và commit thật.
- [ ] Listener async được kiểm tra qua **kết quả cuối cùng với timeout**, không qua `Thread.sleep` cố định.
- [ ] Test dùng cùng hạ tầng transaction/registry có ý nghĩa với production.
- [ ] Listener lỗi không bị nuốt exception khiến publication completed sai.
- [ ] Registry theo dõi trạng thái theo **listener**, không chỉ theo event.
- [ ] Có test resubmit/recovery theo phiên bản và backend cụ thể.
- [ ] Có idempotency/deduplication khi chạy lại cùng event.
- [ ] Test được tình huống side effect hoàn tất nhưng completion chưa ghi.
- [ ] Có test aggregate event đến trễ/không đúng thứ tự nếu consumer phụ thuộc version.
- [ ] Không dùng thread context của request nguồn như contract của event replay.
- [ ] Có test transaction propagation, rollback rule và self-invocation nếu use case liên quan.
- [ ] Test không ảnh hưởng nhau do fixture, dữ liệu registry hoặc executor còn tồn đọng.
- [ ] Kiểm tra boundary giữa các application modules.

## 20. Câu hỏi tự đánh giá và tài liệu tham khảo

### Câu hỏi

1. Vì sao một unit test gọi `listener.on(event)` không chứng minh listener chạy sau commit?
2. Vì sao `@SpringBootTest @Transactional` có thể khiến `AFTER_COMMIT` không chạy?
3. `TransactionTemplate` khác `TestTransaction` ở mục đích sử dụng trong integration test thế nào?
4. Sau `TestTransaction.flagForCommit(); TestTransaction.end();` có thể kiểm tra những kết quả gì?
5. `@EventListener` đồng bộ có thể chạy trong tình huống transaction nguồn rollback không?
6. Listener `BEFORE_COMMIT` có phải bằng chứng DB đã commit thành công không?
7. Vì sao callback `AFTER_COMMIT` ghi database có thể cần `REQUIRES_NEW`?
8. Vì sao kiểm tra mock `repository.save(...)` chưa chứng minh projection đã commit?
9. Khi `@ApplicationModuleListener` chạy async, nên chờ điều kiện nào trong test?
10. Vì sao registry báo không còn publication incomplete vẫn chưa chứng minh đã có publication nào được đăng ký?
11. Nếu hai listener cùng nhận một event nhưng chỉ một listener lỗi, cần kiểm tra trạng thái thế nào?
12. Nếu listener commit tác dụng phụ nhưng chưa mark completed, idempotency giúp gì?
13. Một test có `REQUIRES_NEW` bên trong transaction ngoài rollback có thể tạo kết quả gì?
14. Lỗi tự gọi method có `@Transactional` trong cùng bean gây hậu quả nào cho transactional listener?
15. Khi externalize sang broker, publication completed của producer có chứng minh consumer xử lý xong chưa?

### Nguồn tham khảo chính thức

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, phase và fallback.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): `@Transactional` trên test, mặc định rollback và `TestTransaction`.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional event listeners, publication registry và recovery.
- [Spring Modulith — Application Module Tests](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest` và kiểm tra published events.
- [Awaitility](https://github.com/awaitility/awaitility): chờ điều kiện bất đồng bộ với timeout trong test Java.

**Ghi nhớ:** Kiểm thử transactional listener phải xác minh **sự thật nghiệp vụ đã commit**, **pha listener thực sự chạy** và **kết quả bên nhận đã được lưu bền** là ba chuyện khác nhau. Spring Modulith giúp tổ chức giao sự kiện và theo dõi publication, nhưng test đáng tin cậy vẫn cần kiểm soát transaction thật, cô lập dữ liệu, fault injection, idempotency và recovery. Đừng sửa một test hậu commit thất bại bằng cách bỏ `AFTER_COMMIT`; hãy sửa **ranh giới transaction hoặc cách viết test** trước.

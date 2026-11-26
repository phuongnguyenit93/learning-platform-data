# Dự án thực hành 008: Kiểm tra event chỉ phát sau transaction commit

> **Chương:** Dự án thực hành  
> **Phạm vi:** Spring Modulith Verification & Testing — kiểm chứng ranh giới transaction của sự kiện giữa các module, dữ liệu đã commit và hành vi khi rollback.

## 1. Bài toán và tiêu chí hoàn thành

Một hệ thống bán hàng có module **orders** xác nhận đơn hàng trong transaction. Sau khi đơn hàng được xác nhận thành công, một module khác có thể gửi thông báo, ghi audit hoặc cập nhật read model dựa trên sự kiện `OrderConfirmed`. Nếu transaction thất bại, các tác vụ này tuyệt đối không được xử lý đơn hàng như thể đã xác nhận.

Dự án đặt ra bốn kết quả có thể kiểm chứng:

| Tình huống | Sự kiện được gọi publish? | Listener `AFTER_COMMIT` được chạy? | Dữ liệu xác nhận tồn tại bền vững? |
|---|---|---|---|
| Đang ở trong transaction, chưa commit | Có | **Chưa** | Chưa thể kết luận từ giao dịch khác |
| Transaction commit thành công | Có | **Có** | Có |
| Transaction rollback | Có thể có, trước rollback | **Không** | Không |
| Publish bên ngoài transaction | Có | **Không**, với `fallbackExecution=false` | Không liên quan |

**Điều kiện đạt:** JUnit 5 chạy xanh cho commit, rollback, exception và publish ngoài transaction; test cũng xác nhận listener nhìn thấy trạng thái đã commit từ **một transaction độc lập**. Đó là bằng chứng mạnh hơn việc chỉ đếm số lần gọi listener.

## 2. Xác định đúng thời điểm: publish khác với xử lý event

Với Spring Framework, lời gọi `ApplicationEventPublisher.publishEvent(event)` có thể diễn ra **ngay trong transaction nghiệp vụ**. Lời gọi đó thông báo sự kiện đến hạ tầng xử lý event, nhưng listener gắn `@TransactionalEventListener(phase = AFTER_COMMIT)` sẽ **chờ transaction commit thành công** rồi mới thực hiện phương thức.

~~~text
T0  BEGIN TRANSACTION
T1  Đọc/cập nhật orders; gọi publishEvent(OrderConfirmed)
T2  PublishedEvents có thể thấy OrderConfirmed; AFTER_COMMIT listener chưa chạy
T3  COMMIT thành công; dữ liệu order đã bền vững
T4  AFTER_COMMIT listener chạy (đồng bộ nếu không có @Async)

Nếu ROLLBACK tại T3: bỏ qua AFTER_COMMIT listener.
~~~

Trong bài này, câu “event chỉ phát sau commit” được kiểm chứng theo nghĩa **không thực hiện hiệu ứng của consumer trước khi commit**. Không nên diễn giải sai rằng Spring hoãn chính lời gọi `publishEvent(...)` đến sau commit. Nếu yêu cầu là **gửi thông điệp ra Kafka/RabbitMQ** một cách tin cậy, cần thiết kế thêm transactional outbox/event publication registry; chỉ gắn annotation cho listener chưa giải quyết mất thông điệp khi tiến trình chết.

Một số cơ chế dễ nhầm:

- `@EventListener`: xử lý đồng bộ khi publish (nếu không cấu hình async), kể cả trước commit.
- `@TransactionalEventListener`: mặc định `AFTER_COMMIT`, xử lý sau commit thành công; không có transaction thì bỏ qua nếu không bật `fallbackExecution`.
- `@ApplicationModuleListener` của Spring Modulith: kết hợp `@Async`, `@TransactionalEventListener` và `@Transactional(propagation = REQUIRES_NEW)`. Vì bất đồng bộ, consumer có thể hoàn thành **muộn hơn** thời điểm service trả về.

## 3. Chuẩn bị dự án và ranh giới module

Ví dụ dùng Java 17+, Spring Boot 3.x/4.x tương thích với bản Spring Modulith của dự án, JUnit Jupiter, Spring Data JPA và H2. Dùng dependency management/BOM Spring Modulith của project đang có để quản lý phiên bản; các khai báo Gradle sau là phần phụ thuộc cần thiết:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.modulith:spring-modulith-starter-core'

    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Cấu trúc ví dụ: application class ở package gốc `com.example.shop`, bài test và những bean cần quan sát đặt dưới module `orders`. Giữ **CommitProbe** trong cùng module chỉ để làm phòng thí nghiệm; khi chuyển listener thực sang module `notification`, hãy test module consumer hoặc test toàn ứng dụng để cả producer và consumer đều được khởi tạo.

~~~text
com.example.shop
  ShopApplication.java
  orders/
    OrderConfirmed.java
    OrderEntity.java
    OrderRepository.java
    OrderService.java
    CommitProbe.java
    AsyncAudit.java
src/test/java/com/example/shop/orders/
    OrderCommitBoundaryTests.java
~~~

File `ShopApplication.java`:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Trong `src/test/resources/application.properties`, dùng schema H2 riêng cho bài test:

~~~properties
spring.datasource.url=jdbc:h2:mem:after_commit_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
~~~

## 4. Cài đặt producer và transaction nghiệp vụ

Event chỉ chứa ID và không mang theo JPA entity đang gắn với persistence context. Consumer sau commit có thể tự đọc lại dữ liệu đã được lưu.

**`orders/OrderConfirmed.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderConfirmed(UUID orderId) {}
~~~

**`orders/OrderEntity.java`**

~~~java
package com.example.shop.orders;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "shop_orders")
class OrderEntity {

    @Id
    private UUID id;

    private boolean confirmed;

    protected OrderEntity() {} // JPA

    OrderEntity(UUID id) {
        this.id = id;
    }

    void confirm() {
        confirmed = true;
    }

    boolean isConfirmed() {
        return confirmed;
    }
}
~~~

**`orders/OrderRepository.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<OrderEntity, UUID> {}
~~~

**`orders/OrderService.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    public OrderService(OrderRepository orders, ApplicationEventPublisher publisher) {
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public UUID create() {
        UUID id = UUID.randomUUID();
        orders.save(new OrderEntity(id));
        return id;
    }

    @Transactional
    public void confirm(UUID id) {
        OrderEntity order = orders.findById(id).orElseThrow();
        order.confirm();
        publisher.publishEvent(new OrderConfirmed(id));
    }
}
~~~

Hai phương thức `public @Transactional` được gọi từ bean khác qua Spring proxy. Trong test, `confirm(id)` tham gia transaction do `TransactionTemplate` mở; event publish trước khi transaction ngoài cùng kết thúc. Đây chính là điều cần chứng minh.

## 5. Listener đo được cả thời điểm chạy và dữ liệu đã commit

Chỉ kiểm tra `probe.called(id)` **sau** lệnh commit chưa đủ: một listener cấu hình sai thành `BEFORE_COMMIT` vẫn có thể làm assertion “đã được gọi” đi qua. Probe bên dưới cố ý mở một **transaction REQUIRES_NEW** để đọc trạng thái đơn hàng tại đúng thời điểm listener chạy.

**`orders/CommitProbe.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class CommitProbe {

    private final OrderRepository orders;
    private final TransactionTemplate independentRead;
    private final ConcurrentHashMap<UUID, Boolean> observed = new ConcurrentHashMap<>();

    public CommitProbe(OrderRepository orders, PlatformTransactionManager txManager) {
        this.orders = orders;
        this.independentRead = new TransactionTemplate(txManager);
        this.independentRead.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        Boolean persisted = independentRead.execute(ignored ->
            orders.findById(event.orderId())
                  .map(OrderEntity::isConfirmed)
                  .orElse(false)
        );
        observed.put(event.orderId(), Boolean.TRUE.equals(persisted));
    }

    public boolean called(UUID id) {
        return observed.containsKey(id);
    }

    public boolean sawCommittedState(UUID id) {
        return Boolean.TRUE.equals(observed.get(id));
    }

    public void clear() {
        observed.clear();
    }
}
~~~

Ở H2 với mức isolation mặc định `READ_COMMITTED`, transaction mới **không nhìn thấy** cập nhật chưa commit của transaction gốc. Vì vậy, assertion `sawCommittedState(id)` phân biệt được `BEFORE_COMMIT` với `AFTER_COMMIT`, kể cả khi cả hai đều chạy trước khi lệnh `executeWithoutResult` trả về.

Probe dùng bộ nhớ và thuộc bài lab. Với listener thực ghi database, cần transaction riêng cho phần ghi sau commit (ví dụ `@ApplicationModuleListener`); không dựa vào transaction cũ vì lúc này commit đã kết thúc.

## 6. JUnit: ba phép thử tại đúng ranh giới commit

**`src/test/java/com/example/shop/orders/OrderCommitBoundaryTests.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ApplicationModuleTest
class OrderCommitBoundaryTests {

    @Autowired OrderService orders;
    @Autowired OrderRepository repository;
    @Autowired CommitProbe probe;
    @Autowired ApplicationEventPublisher publisher;
    @Autowired PlatformTransactionManager transactionManager;

    private TransactionTemplate transactions;

    @BeforeEach
    void prepare() {
        transactions = new TransactionTemplate(transactionManager);
        probe.clear();
    }

    @Test
    void publishesInsideTransaction_butDeliversOnlyAfterCommit(
        PublishedEvents published
    ) {
        UUID id = orders.create(); // create() đã commit khi trả về

        transactions.executeWithoutResult(tx -> {
            orders.confirm(id);

            // Publisher đã phát event khi transaction còn mở.
            assertThat(published.ofType(OrderConfirmed.class)
                    .matching(OrderConfirmed::orderId, id))
                .hasSize(1);

            // Consumer AFTER_COMMIT chưa được phép chạy.
            assertThat(probe.called(id)).isFalse();
        });

        // Template trả về sau khi commit và các callback đồng bộ hoàn tất.
        assertThat(probe.called(id)).isTrue();
        assertThat(probe.sawCommittedState(id)).isTrue();
        assertThat(repository.findById(id).orElseThrow().isConfirmed()).isTrue();
    }

    @Test
    void rollback_discardsDeliveryAndDatabaseChange() {
        UUID id = orders.create();

        transactions.executeWithoutResult(tx -> {
            orders.confirm(id);
            assertThat(probe.called(id)).isFalse();
            tx.setRollbackOnly();
        });

        assertThat(probe.called(id)).isFalse();
        assertThat(repository.findById(id).orElseThrow().isConfirmed()).isFalse();
    }

    @Test
    void exception_rollsBackAndDoesNotDeliver() {
        UUID id = orders.create();

        assertThatThrownBy(() -> transactions.executeWithoutResult(tx -> {
            orders.confirm(id);
            throw new IllegalStateException("simulated failure");
        })).isInstanceOf(IllegalStateException.class);

        assertThat(probe.called(id)).isFalse();
        assertThat(repository.findById(id).orElseThrow().isConfirmed()).isFalse();
    }

    @Test
    void outsideTransaction_doesNotRunTransactionalListener() {
        UUID id = UUID.randomUUID();
        publisher.publishEvent(new OrderConfirmed(id));

        // fallbackExecution mặc định là false.
        assertThat(probe.called(id)).isFalse();
    }
}
~~~

**Vì sao test này xác định được commit thật?**

1. `orders.create()` hoàn thành transaction tạo đơn **trước** khi test bắt đầu kiểm tra xác nhận; dữ liệu gốc có thể truy vấn lại.
2. `TransactionTemplate` tạo ranh giới commit do test điều khiển. `OrderService.confirm()` dùng propagation mặc định `REQUIRED`, tham gia transaction đang mở.
3. Khi còn ở trong callback, `PublishedEvents` đã thấy event nhưng `CommitProbe` chưa chạy. Sau khi callback kết thúc thành công, Spring commit transaction rồi gọi listener `AFTER_COMMIT`.
4. Bên trong listener, `REQUIRES_NEW` đọc được `confirmed=true` **từ transaction khác**. Nếu đổi annotation của probe thành `BEFORE_COMMIT`, giá trị này sẽ là `false` (với isolation đã nêu) và test commit phải thất bại.
5. Ở nhánh rollback và exception, `confirmed` vẫn `false`; không có callback `AFTER_COMMIT`.

Không gắn `@Transactional` lên class hoặc method JUnit này: Spring Test thường rollback transaction của test khi kết thúc; việc gọi service bên trong test chưa tạo ra commit mà bạn muốn kiểm chứng.

## 7. Đọc bằng chứng và kiểm tra phép thử âm

| Assertion | Chứng minh được điều gì? | Không chứng minh được điều gì? |
|---|---|---|
| `PublishedEvents` có `OrderConfirmed` trong callback | Producer đã gọi publish | Listener đã được chạy |
| `probe.called(id) == false` trước commit | Listener chưa chạy sớm | Listener sau đó chắc chắn sẽ chạy |
| `probe.called(id) == true` sau commit | Listener đã chạy | Listener chạy ở `AFTER_COMMIT` hay `BEFORE_COMMIT` |
| `probe.sawCommittedState(id) == true` | Dữ liệu được transaction độc lập đọc sau commit | Event chắc chắn được gửi tin cậy sang broker ngoài tiến trình |
| Rollback không gọi probe và không lưu dữ liệu | Listener không xử lý transaction hỏng | Cơ chế retry của listener async |

Để tự đánh giá chất lượng test, thử **mutation** trên một bản nháp mã nguồn:

- Đổi `@TransactionalEventListener` thành `@EventListener`: test commit phải thất bại ngay tại assertion “chưa gọi”.
- Đổi phase thành `BEFORE_COMMIT`: probe có thể được gọi khi commit bắt đầu, nhưng **không thấy dữ liệu committed từ transaction độc lập**; assertion `sawCommittedState` phải thất bại.
- Bỏ `@Transactional` khỏi `OrderService.confirm` nhưng vẫn gọi trong `TransactionTemplate`: test có thể **vẫn xanh** vì transaction ngoài đang mở. Cần test bổ sung gọi service trực tiếp để kiểm chứng annotation ở service, hoặc kiểm tra transaction bằng instrumentation riêng. Đừng hiểu bộ test hiện tại bao phủ mọi cách gọi.

Nếu test mutation vẫn xanh sau khi đổi phase, hãy kiểm tra lại listener thực sự được đưa vào `@ApplicationModuleTest` hay chưa và transaction độc lập có dùng chung persistence context với transaction gốc hay không.

## 8. Mở rộng sang `@ApplicationModuleListener` bất đồng bộ

Sau khi kiểm tra ranh giới commit bằng listener đồng bộ, thêm một consumer bất đồng bộ để kiểm tra hành vi Spring Modulith thực tế. Trong bài lab này, consumer vẫn ở `orders` để được bootstrap bởi `@ApplicationModuleTest` mặc định.

**`orders/AsyncAudit.java`**

~~~java
package com.example.shop.orders;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class AsyncAudit {

    private final Set<UUID> processed = ConcurrentHashMap.newKeySet();

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        processed.add(event.orderId());
    }

    public boolean processed(UUID id) {
        return processed.contains(id);
    }
}
~~~

Vì `@ApplicationModuleListener` chạy bất đồng bộ, **không** viết assertion `assertThat(asyncAudit.processed(id)).isTrue()` ngay sau `orders.confirm(id)`: callback có thể chưa hoàn tất dù commit đã xong. Thay bằng `Scenario` của Spring Modulith:

~~~java
// Thêm import vào OrderCommitBoundaryTests:
import org.springframework.modulith.test.Scenario;

// Thêm field:
@Autowired AsyncAudit asyncAudit;

// Thêm phương thức test:
@Test
void asyncConsumerEventuallyProcessesCommittedEvent(Scenario scenario) {
    UUID id = orders.create();

    scenario.stimulate(() -> orders.confirm(id))
        .andWaitForStateChange(
            () -> asyncAudit.processed(id),
            Boolean.TRUE::equals
        )
        .andVerify(handled -> assertThat(handled).isTrue());

    assertThat(probe.sawCommittedState(id)).isTrue();
}
~~~

`Scenario.stimulate(...)` mở transaction cho kích thích và **commit trước khi chờ** kết quả; tránh viết test mong mọi thay đổi bị test rollback tự động. Vì bài này mỗi test tạo ID mới và không có consumer nào tái sử dụng ID, trạng thái bộ nhớ không làm lẫn kết quả. Với test dùng DB lâu dài, chủ động dọn dữ liệu hoặc dùng cơ chế `andCleanup(...)` phù hợp.

Khi tách `AsyncAudit` sang module **notification**, cần đặt test integration trong package consumer và bật `@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)` **nếu** consumer khai báo phụ thuộc vào module producer. Chế độ đó nạp module hiện tại và các module mà nó phụ thuộc, không tự động nạp mọi module lắng nghe event nếu test đang nằm ở producer.

## 9. Các nhánh transaction dễ làm test báo sai

**Transaction lồng nhau:** `REQUIRED` thường nhập vào transaction đang tồn tại; chỉ commit transaction **ngoài cùng** mới kích hoạt `AFTER_COMMIT`. Nếu producer dùng `REQUIRES_NEW`, event của nó gắn với transaction mới, nên có thể được xử lý trước khi transaction ngoài commit. Quyết định này phải phù hợp với ranh giới nghiệp vụ.

**Gọi cùng class:** gọi `this.confirm(id)` từ một phương thức cùng class sẽ tránh Spring AOP proxy, khiến `@Transactional` trên `confirm` không có hiệu lực riêng. Test nên gọi service qua bean được inject, giống cách thực tế.

**Event không gắn transaction:** với `@TransactionalEventListener` mặc định, không có transaction thì event bị bỏ qua. Không bật `fallbackExecution=true` chỉ để làm test “xanh”, vì như vậy sẽ thay đổi yêu cầu sau commit.

**Async race:** `Thread.sleep(...)` không biến kiểm thử bất đồng bộ thành tất định. Dùng `Scenario`/Awaitility chờ điều kiện có timeout và chỉ kiểm tra dữ liệu hay side effect quan sát được.

**Đọc dữ liệu trong callback:** ngay sau commit, tài nguyên transaction gốc có thể vẫn gắn với thread; truy cập DB qua giao dịch cũ có thể gây hiểu nhầm. Mẫu `REQUIRES_NEW` trong probe bắt buộc tạo phạm vi đọc độc lập; với production listener cần cân nhắc idempotency và việc xử lý lại khi lỗi.

## 10. Ranh giới module, database và độ tin cậy giao event

Spring Modulith tổ chức module theo package. Event `OrderConfirmed` nên thuộc API công khai của module `orders`, consumer không import entity/repository nội bộ của producer. Nếu chuyển consumer sang module `notification`, chỉ truyền định danh qua event, để consumer truy vấn qua API được công khai hoặc tự lưu dữ liệu phục vụ module mình.

`@ApplicationModuleTest` kiểm thử hành vi của module được bootstrap và có thể tự động kiểm chứng ranh giới kiến trúc. Tuy nhiên, thành công của test commit/rollback **không chứng minh** delivery an toàn trước crash: một tiến trình có thể dừng sau khi DB commit nhưng trước khi async listener thực thi.

Với chức năng không được phép mất event, thêm **Spring Modulith Event Publication Registry** cùng storage phù hợp (JPA/JDBC/MongoDB tùy dự án). Registry ghi nhận publication cho transactional listener trong transaction gốc và theo dõi trạng thái xử lý; thiết kế khả năng resubmit và idempotent consumer để tránh tác dụng trùng khi giao lại. Kiểm thử lớp này cần thêm kịch bản listener ném lỗi và quan sát bản ghi publication chưa hoàn thành, rồi thực hiện resubmit theo API của phiên bản đang dùng. Bài hiện tại tập trung vào **commit boundary**, không giả vờ rằng test bộ nhớ đã chứng minh cơ chế retry bền vững.

Với yêu cầu “đẩy Kafka chỉ sau commit”, cần tách rõ ba điều: transaction lưu đơn hàng, việc ghi outbox/registry trong cùng transaction, và việc gửi broker sau khi commit. Khi tự viết `@TransactionalEventListener(AFTER_COMMIT)` gửi broker mà không có outbox, crash vẫn có thể làm mất message.

## 11. Chạy kiểm thử, quality gate và tiêu chí nghiệm thu

Trong dự án Gradle đã cấu hình Spring Boot cùng Spring Modulith BOM tương thích, chạy:

~~~bash
./gradlew test --tests '*OrderCommitBoundaryTests'
~~~

Để khóa thêm ranh giới dependency giữa các module trong CI, có thể viết một architecture test riêng (đặt trong package gốc của ứng dụng):

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {
    @Test
    void modulesRespectDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Nhiệm vụ được nghiệm thu khi: (1) test commit chứng minh **chưa xử lý trước commit, đã xử lý sau commit và thấy dữ liệu committed từ transaction độc lập**; (2) test rollback và exception bảo đảm không xử lý, dữ liệu không đổi; (3) test không có transaction thể hiện đúng `fallbackExecution=false`; (4) test `Scenario` chứng minh async consumer hoàn thành eventual; (5) architecture test không phát hiện dependency trái quy tắc; (6) CI chạy JUnit và build thất bại khi bất kỳ assertion nào sai.

**Câu hỏi tự kiểm tra:** Nếu đổi listener từ `AFTER_COMMIT` sang `BEFORE_COMMIT`, assertion nào phát hiện? Nếu listener được chuyển sang module **notification** mà test vẫn chỉ bootstrap **orders**, vì sao test có thể “xanh” dù production consumer không hề được tạo? Nếu event được gửi broker sau commit, còn khoảng thời gian nào vẫn có thể mất thông điệp?

**Tài liệu chuẩn để tra cứu:** [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html), [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html), [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html).

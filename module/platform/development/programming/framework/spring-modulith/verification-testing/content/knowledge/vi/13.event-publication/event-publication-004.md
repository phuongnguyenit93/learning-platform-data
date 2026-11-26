# Event được phát trước, trong hoặc sau transaction

## 1. Hai thời điểm rất dễ bị nhầm lẫn

Trong ứng dụng Spring Modulith, cần phân biệt:

1. **Thời điểm phát event**: mã nguồn gọi `ApplicationEventPublisher.publishEvent(event)`.
2. **Thời điểm listener xử lý event**: một phương thức có `@EventListener`, `@TransactionalEventListener` hoặc `@ApplicationModuleListener` thực sự bắt đầu chạy.

Hai thời điểm này **có thể trùng nhau hoặc cách nhau bởi một lần commit**. Một lời gọi `publishEvent` ở giữa transaction không tự động có nghĩa mọi listener sẽ chạy ngay, và một listener chạy sau commit cũng không có nghĩa mã nghiệp vụ đã gọi `publishEvent` sau commit.

Ví dụ, module `orders` tạo đơn hàng:

~~~java
@Transactional
public void placeOrder(UUID orderId) {
    repository.save(new OrderEntity(orderId));
    events.publishEvent(new OrderPlaced(orderId));
}
~~~

Lệnh `publishEvent` chạy **bên trong** transaction của `placeOrder`. Nếu module `notifications` nhận `OrderPlaced` bằng `@TransactionalEventListener(phase = AFTER_COMMIT)`, listener chỉ được gọi khi transaction **commit thành công**. Nếu rollback, listener đó không chạy.

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, việc hiểu chính xác trình tự này giúp kiểm chứng ranh giới kiến trúc bằng `ApplicationModules`, thiết kế `@ApplicationModuleTest` cho sự kiện, xác thực tác động lên cơ sở dữ liệu và đặt quality gate trong CI để ngăn hồi quy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt phát event **trước khi mở**, **đang trong** và **sau khi kết thúc** transaction.
- Dự đoán hành vi của các listener theo pha `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.
- Giải thích vì sao `@EventListener` thông thường và `@TransactionalEventListener` cho kết quả khác nhau khi rollback.
- Viết module test chủ động commit/rollback bằng `TransactionTemplate`, tránh bẫy `@Transactional` ở test.
- Kiểm tra riêng việc **đã phát** sự kiện và việc **listener đã tạo side effect**.
- Thiết kế listener cập nhật database an toàn sau commit, kể cả khi xử lý bất đồng bộ.

## 2. Spring event và transaction là hai cơ chế phối hợp

`ApplicationEventPublisher` thuộc Spring Framework; `publishEvent(Object)` có thể nhận một Java record hoặc POJO thông thường. Spring Modulith giúp tổ chức các module, kiểm tra phụ thuộc, và bổ sung các tiện ích như `@ApplicationModuleTest` cùng Event Publication Registry khi được cấu hình.

`publishEvent` **không tự mở transaction** và cũng **không tự commit** transaction. Transaction do lời gọi tới service, `@Transactional`, `TransactionTemplate` hoặc cơ chế quản lý transaction khác quyết định.

Trong cấu hình mặc định:

- `@EventListener` nhận event **đồng bộ** trong lúc Spring phân phối event. Nếu đang có transaction, listener thường chạy trong ngữ cảnh transaction đó.
- `@TransactionalEventListener` liên kết việc thực thi callback với **một pha của transaction**. Pha mặc định là `AFTER_COMMIT`.
- `@ApplicationModuleListener` của Spring Modulith là tiện ích dành cho giao tiếp module theo transaction, kết hợp xử lý bất đồng bộ và transaction mới cho listener.

Các mệnh đề “đồng bộ” ở trên mô tả multicaster/listener mặc định. Cấu hình async tùy chỉnh hoặc `@Async` có thể thay đổi thời điểm chạy và luồng thực thi; không được giả định transaction context được tự động chuyển sang thread khác.

### Bảng quyết định theo thời điểm phát

| Thời điểm gọi `publishEvent` | `@EventListener` mặc định | `@TransactionalEventListener(AFTER_COMMIT)`, mặc định `fallbackExecution=false` |
| --- | --- | --- |
| **Trước khi bắt đầu transaction** | Xử lý ngay trong luồng gọi. | Không xử lý, vì lúc phát chưa có transaction. |
| **Bên trong transaction sau đó commit** | Xử lý lúc phát; các thay đổi cùng transaction có thể rollback nếu transaction về sau thất bại. | Được gọi **sau khi commit thành công**. |
| **Bên trong transaction sau đó rollback** | Đã được gọi khi phát; side effect ngoài database có thể đã xảy ra. | Không được gọi. |
| **Sau khi transaction đã kết thúc** | Xử lý khi phát. | Không xử lý nếu không có transaction mới và không bật fallback. |

**Quan trọng:** `@TransactionalEventListener` chỉ đăng ký callback khi có transaction phù hợp **tại lúc sự kiện được phát**. Nó không “nhớ” một sự kiện được phát trước transaction rồi tự động chạy khi transaction tương lai commit.

## 3. Phát event trước transaction

Xét một service gọi event trước khi chuyển vào thao tác lưu dữ liệu:

~~~java
public void placeOrder(UUID id) {
    events.publishEvent(new OrderPlaced(id)); // Chưa có transaction.
    transactionalOrderWriter.persist(id);     // Một bean khác mở transaction.
}
~~~

Giả sử caller chưa có transaction và `transactionalOrderWriter.persist` được gọi qua Spring proxy với `@Transactional`. Khi đó:

1. `OrderPlaced` được phát **ngoài transaction**.
2. `@EventListener` mặc định xử lý ngay.
3. `@TransactionalEventListener(AFTER_COMMIT)` mặc định **bỏ qua** event.
4. Nếu `persist` về sau rollback, Spring không thu hồi những side effect ngoài transaction đã xảy ra ở bước 2.

Điều này thường là một lỗi nghiệp vụ: event `OrderPlaced` hàm ý đơn hàng đã được ghi nhận, nhưng việc lưu dữ liệu còn chưa thành công.

### Trường hợp nào có thể cố ý phát trước transaction?

Có những event chỉ mang ý nghĩa kỹ thuật như `ImportStarted` hoặc `RequestReceived` được phát trước khi bắt đầu một thao tác transaction. Chúng có thể hợp lý nếu người thiết kế hiểu rằng:

- Event diễn tả **ý định bắt đầu**, không diễn tả dữ liệu đã commit.
- Listener transactional mặc định sẽ không chạy nếu lúc phát chưa có transaction.
- Tác động ngoài như gửi HTTP request, email hoặc ghi log qua hệ thống khác không được transaction tương lai bảo vệ.

Nếu muốn xử lý ngay **dù không có transaction**, có thể viết:

~~~java
@TransactionalEventListener(fallbackExecution = true)
void on(ImportStarted event) {
    // Chạy ngay khi không có transaction; chạy sau commit khi có transaction.
}
~~~

Với annotation trên, pha mặc định vẫn là `AFTER_COMMIT` khi **có** transaction. Khi **không có** transaction, `fallbackExecution=true` cho phép gọi listener mà không chờ pha commit. Đây là lựa chọn có chủ đích về ngữ nghĩa, không phải cách chữa test rollback.

## 4. Phát event trong transaction: kịch bản phổ biến

Ví dụ module `orders`:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void place(UUID orderId) {
        // Ứng dụng thực: validate và repository.save(orderEntity).
        events.publishEvent(new OrderPlaced(orderId));
    }
}
~~~

Khi `place` được gọi qua Spring proxy và có transaction manager thích hợp, transaction được mở trước khi vào thân hàm. `publishEvent` xảy ra **trong transaction**, nhưng nó **không chờ commit** mới công bố đối tượng tới cơ chế event.

### 4.1. Bốn pha của @TransactionalEventListener

| `TransactionPhase` | Khi nào được gọi? | Rủi ro/điểm cần lưu ý |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước thao tác commit. | Commit sau đó vẫn có thể thất bại; không nên gửi email/thanh toán ngoài hệ thống ở đây nếu cần bảo đảm đã commit. |
| `AFTER_COMMIT` (**mặc định**) | Sau commit thành công. | Side effect xảy ra sau khi dữ liệu nguồn đã commit; lỗi listener không đơn giản rollback lại nguồn. |
| `AFTER_ROLLBACK` | Sau khi transaction rollback. | Phù hợp quan sát hoặc bù trừ có kiểm soát; cần xem xét transaction mới khi ghi database. |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, cả commit lẫn rollback. | Cần phân biệt kết quả transaction nếu nghiệp vụ yêu cầu chỉ xử lý khi thành công. |

Ví dụ các listener độc lập:

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
void beforeCommit(OrderPlaced event) {
    // Callback trước commit.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void afterCommit(OrderPlaced event) {
    // Chỉ sau commit thành công.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
void afterRollback(OrderPlaced event) {
    // Chỉ sau rollback.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
void afterCompletion(OrderPlaced event) {
    // Sau khi kết thúc transaction, bất kể kết quả.
}
~~~

Các đoạn trên minh họa phương thức của một Spring-managed listener bean, cần import `TransactionPhase` và `TransactionalEventListener`. Trong dự án thực, không nên tạo bốn listener có cùng side effect; mỗi pha phục vụ một trách nhiệm khác nhau.

### 4.2. Timeline commit thành công

~~~mermaid
sequenceDiagram
    participant Client
    participant Service as orders.OrderService
    participant Tx as Transaction Manager
    participant Bus as Event Publisher
    participant Plain as @EventListener
    participant Before as BEFORE_COMMIT
    participant After as AFTER_COMMIT

    Client->>Tx: Bắt đầu transaction
    Tx->>Service: place(id)
    Service->>Bus: publishEvent(OrderPlaced)
    Bus->>Plain: Xử lý đồng bộ lúc phát
    Note over Bus,After: Transactional listeners đăng ký theo pha
    Tx->>Before: Callback trước commit
    Tx->>Tx: COMMIT thành công
    Tx->>After: Callback sau commit
    Tx-->>Client: Hoàn tất lời gọi
~~~

Thứ tự chính cần nhớ: **phát → xử lý listener thường → trước commit → commit → sau commit**. Sơ đồ đơn giản hóa callback và phạm vi gọi của Spring proxy; không diễn tả mọi thao tác flush hay callback nội bộ của transaction manager.

### 4.3. Timeline rollback

~~~mermaid
sequenceDiagram
    participant Client
    participant Service as orders.OrderService
    participant Bus as Event Publisher
    participant Plain as @EventListener
    participant Tx as Transaction Manager
    participant Rollback as AFTER_ROLLBACK
    participant Commit as AFTER_COMMIT

    Client->>Service: place(id)
    Service->>Bus: publishEvent(OrderPlaced)
    Bus->>Plain: Xử lý ngay
    Client->>Tx: Rollback transaction
    Tx->>Rollback: Callback sau rollback
    Note over Commit: Không gọi AFTER_COMMIT
~~~

Nếu `@EventListener` đồng bộ ghi vào **cùng transaction nguồn**, thay đổi database của nó thường rollback theo transaction. Nhưng email, HTTP call, gửi message ra broker hoặc ghi dữ liệu qua một transaction độc lập **không được rollback tự động** cùng transaction nguồn. Đây là lý do listener `AFTER_COMMIT` thường phù hợp với các hành động downstream chỉ nên diễn ra khi sự thật nghiệp vụ đã được xác nhận.

### 4.4. Transaction phải thực sự được áp dụng

`@Transactional` thường hoạt động thông qua proxy trong Spring. Nếu một phương thức cùng object gọi `this.place(id)`, lời gọi nội bộ có thể bỏ qua proxy, dẫn đến việc transaction không được mở như mong đợi. Tương tự, đặt `@Transactional` trên một phương thức nhưng gọi service ngoài Spring context cũng không tạo transaction.

Vì vậy, khi test thất bại vì `AFTER_COMMIT` không chạy, hãy kiểm tra **transaction có hoạt động tại thời điểm `publishEvent` không**, trước khi tìm lỗi ở listener.

## 5. Phát event sau khi transaction kết thúc

Giả sử một thành phần kết thúc việc ghi database rồi mới gọi publisher:

~~~java
TransactionTemplate transactions = new TransactionTemplate(txManager);

transactions.executeWithoutResult(status -> {
    // Lưu thay đổi vào database.
}); // Khi lệnh trả về bình thường, transaction này đã hoàn tất.

events.publishEvent(new OrderPlaced(orderId)); // Không có transaction mới.
~~~

Đây là **phát event sau transaction** theo nghĩa trực tiếp: lời gọi `publishEvent` diễn ra sau khi `TransactionTemplate` đã hoàn tất, giả sử không có transaction bao ngoài.

- `@EventListener` thông thường xử lý ngay.
- `@TransactionalEventListener(AFTER_COMMIT)` với `fallbackExecution=false` **không chạy**, vì tại **lúc phát event** không có transaction đang hoạt động để đăng ký callback.
- `fallbackExecution=true` cho phép listener xử lý trực tiếp trong trường hợp không có transaction.

**Phân biệt với “phát trong transaction, xử lý sau commit”:** ở tình huống thứ hai, event đã được phát *trước* commit và listener được đăng ký callback. Hai mô hình không tương đương, ngay cả khi công việc cuối cùng đều diễn ra sau khi dữ liệu được lưu.

### Tại sao không luôn phát sau commit trong mã nghiệp vụ?

Phát event sau khi `TransactionTemplate` trả về làm xuất hiện một khoảng cách: dữ liệu đã commit nhưng lệnh phát sự kiện có thể thất bại hoặc tiến trình có thể dừng trước khi phát. Điều này có thể phù hợp với event chỉ mang tính quan sát, nhưng không thích hợp nếu nghiệp vụ cần cơ chế ghi nhận và xử lý lại đáng tin cậy.

Đối với yêu cầu giao sự kiện bền vững, có thể xem xét các cơ chế Event Publication Registry của Spring Modulith khi được cấu hình với lưu trữ phù hợp, hoặc transactional outbox tùy kiến trúc hệ thống. Không nên mặc định rằng chỉ gọi `publishEvent` sau commit đã đủ bảo đảm sự kiện không mất.

### Một trường hợp nâng cao: callback afterCommit phát event thứ hai

Nếu listener `AFTER_COMMIT` của event A lại gọi `publishEvent(B)`, cần kiểm tra transaction context và chính sách listener của B một cách tường minh. Trong callback sau commit, tài nguyên transaction có thể còn gắn với thread ở một số thời điểm; **không nên suy luận chỉ từ tên callback** rằng mọi phần mã chạy lúc đó giống hoàn toàn lời gọi bình thường sau khi `TransactionTemplate` trả về. Với việc ghi database hoặc phát chuỗi event cần transaction rõ ràng, cân nhắc `REQUIRES_NEW` và integration test bao phủ hành vi.

## 6. Ví dụ ranh giới module orders → notifications

Với package gốc `com.example.shop`, ví dụ gồm:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   ├── internal
│   │   └── OrderEntity.java
│   └── events
│       ├── OrderPlaced.java
│       └── package-info.java
└── notifications
    ├── OrderNotificationListener.java
    └── package-info.java
~~~

Kiểu event `OrderPlaced` thuộc API công khai của `orders`:

~~~java
// orders/events/OrderPlaced.java
package com.example.shop.orders.events;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

~~~java
// orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Module nhận khai báo phụ thuộc được phép:

~~~java
// notifications/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.example.shop.notifications;
~~~

Listener của `notifications`:

~~~java
package com.example.shop.notifications;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderNotificationListener {

    @TransactionalEventListener // Pha mặc định: AFTER_COMMIT.
    void on(OrderPlaced event) {
        // Thực hiện tác vụ downstream sau commit thành công.
    }
}
~~~

**Module `orders` phát** event vì `OrderService` chứa lời gọi `publishEvent`. **Module `notifications` xử lý** event ở pha đã định. Việc sử dụng event không làm mất phụ thuộc kiểu Java: `notifications` vẫn import `OrderPlaced`, nên import đó phải thuộc named interface công khai và phù hợp `allowedDependencies`.

Kiểm tra kiến trúc:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` giúp phát hiện phụ thuộc vòng và truy cập API nội bộ trái quy tắc. Nó **không** kiểm tra rằng một transaction đã commit, listener đã chạy hoặc email đã gửi. Do đó, cần bài kiểm thử riêng cho timeline và tác động runtime.

## 7. Kiểm thử trước, trong, sau transaction bằng @ApplicationModuleTest

Để quan sát chính xác các pha, ta tạo một **probe chỉ dùng trong test**. Ví dụ dưới đây giả định ứng dụng Spring Boot/Spring Modulith có `PlatformTransactionManager` sẵn (do cấu hình JPA/JDBC hoặc transaction infrastructure khác cung cấp).

Test đặt trong package của module `orders`, không gắn `@Transactional` ở class hoặc method:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.EventListener;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
@Import(EventTimelineTests.ProbeConfiguration.class)
class EventTimelineTests {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired PhaseProbe probe;

    private TransactionTemplate transactions;

    @BeforeEach
    void resetProbe() {
        probe.reset();
        transactions = new TransactionTemplate(transactionManager);
    }

    @Test
    void eventBeforeOrAfterTransactionHasNoCommitCallback() {
        publisher.publishEvent(new OrderPlaced(UUID.randomUUID()));

        // Chưa có transaction: listener thông thường chạy.
        assertThat(probe.immediate).isEqualTo(1);
        assertThat(probe.afterCommit).isZero();

        transactions.executeWithoutResult(status -> {
            // Không phát event trong transaction này.
        });

        publisher.publishEvent(new OrderPlaced(UUID.randomUUID()));

        // Lúc này transaction đã kết thúc: AFTER_COMMIT vẫn không được gọi.
        assertThat(probe.immediate).isEqualTo(2);
        assertThat(probe.afterCommit).isZero();
        assertThat(probe.afterCompletion).isZero();
    }

    @Test
    void eventInsideCommittedTransactionRunsCommitPhases() {
        transactions.executeWithoutResult(status -> {
            publisher.publishEvent(new OrderPlaced(UUID.randomUUID()));

            assertThat(probe.immediate).isEqualTo(1);
            assertThat(probe.beforeCommit).isZero();
            assertThat(probe.afterCommit).isZero();
        });

        // TransactionTemplate đã commit khi trả về bình thường.
        assertThat(probe.beforeCommit).isEqualTo(1);
        assertThat(probe.afterCommit).isEqualTo(1);
        assertThat(probe.afterRollback).isZero();
        assertThat(probe.afterCompletion).isEqualTo(1);
    }

    @Test
    void eventInsideRolledBackTransactionSkipsCommitPhases() {
        transactions.executeWithoutResult(status -> {
            publisher.publishEvent(new OrderPlaced(UUID.randomUUID()));
            assertThat(probe.immediate).isEqualTo(1);
            status.setRollbackOnly();
        });

        assertThat(probe.beforeCommit).isZero();
        assertThat(probe.afterCommit).isZero();
        assertThat(probe.afterRollback).isEqualTo(1);
        assertThat(probe.afterCompletion).isEqualTo(1);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class ProbeConfiguration {

        @Bean
        PhaseProbe phaseProbe() {
            return new PhaseProbe();
        }
    }

    static class PhaseProbe {
        int immediate;
        int beforeCommit;
        int afterCommit;
        int afterRollback;
        int afterCompletion;

        void reset() {
            immediate = 0;
            beforeCommit = 0;
            afterCommit = 0;
            afterRollback = 0;
            afterCompletion = 0;
        }

        @EventListener
        public void immediately(OrderPlaced event) {
            immediate++;
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void before(OrderPlaced event) {
            beforeCommit++;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            afterCommit++;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderPlaced event) {
            afterRollback++;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void afterCompletion(OrderPlaced event) {
            afterCompletion++;
        }
    }
}
~~~

**Giải thích thiết kế test:**

1. `PhaseProbe` là bean được đăng ký từ `@TestConfiguration`, không thuộc code production.
2. `@EventListener` tăng `immediate` khi phân phối event. Bốn transactional listener độc lập tăng bộ đếm theo từng pha.
3. Test đầu tiên phát **trước và sau** transaction; không pha transactional nào chạy vì khi phát không có transaction.
4. Test thứ hai phát **trong** transaction commit thành công; chỉ sau khi `TransactionTemplate.executeWithoutResult` trả về mới khẳng định `BEFORE_COMMIT` và `AFTER_COMMIT`.
5. Test thứ ba chủ động rollback; các callback commit không chạy, trong khi `AFTER_ROLLBACK` và `AFTER_COMPLETION` chạy.

Các assertion ngay sau `executeWithoutResult` giả định các listener của probe chạy đồng bộ, theo cấu hình multicaster mặc định. Không dùng mẫu bộ đếm đơn giản này để khẳng định thời điểm hoàn tất của listener `@Async`. Nếu dự án chạy test song song và chia sẻ cùng application context, cần cô lập probe hoặc vô hiệu hóa chạy song song cho bộ test này.

### 7.1. Bẫy @Transactional trên lớp test

Đoạn sau dễ tạo kết quả sai:

~~~java
@ApplicationModuleTest
@Transactional
class MisleadingTest {
    // ... test gọi publisher.publishEvent(...) và chờ AFTER_COMMIT.
}
~~~

Spring Test có thể mở transaction bao ngoài mỗi test rồi **rollback cuối test**. Khi đó:

- Lệnh `publishEvent` vẫn được gọi; `@EventListener` thông thường vẫn có thể chạy.
- `@TransactionalEventListener(AFTER_COMMIT)` không chạy vì transaction test rollback.
- Nếu tạo `TransactionTemplate` có propagation mặc định `REQUIRED`, nó sẽ **tham gia transaction test hiện có**, không tạo lần commit độc lập như mong đợi.

Nếu mục tiêu test là kiểm chứng commit, hãy dùng một test không có transaction bao ngoài và chủ động quản lý bằng `TransactionTemplate`, hoặc dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` khi test do Spring Test quản lý transaction. Không bật `fallbackExecution=true` chỉ để lách vấn đề.

### 7.2. PublishedEvents kiểm tra việc phát, không chứng minh listener đã chạy

Trong một test riêng của module phát:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderPublicationTests {

    @Autowired OrderService service;

    @Test
    void emitsOrderPlaced(PublishedEvents events) {
        UUID id = UUID.randomUUID();
        service.place(id);

        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, id))
                .hasSize(1);
    }
}
~~~

`PublishedEvents` giúp kiểm chứng lời gọi nghiệp vụ có **phát event với payload đúng**. Ngay cả khi một transaction sau đó rollback, việc test quan sát event đã phát không suy ra listener `AFTER_COMMIT` đã được gọi. Cần bài test sau commit hoặc integration test riêng để khẳng định side effect.

## 8. Cập nhật database trong listener sau commit

Một `@TransactionalEventListener(AFTER_COMMIT)` có thể chạy khi tài nguyên transaction nguồn vẫn còn được bind vào thread, mặc dù transaction đã commit. Nếu listener sửa entity hoặc lưu dữ liệu và mong có thêm một lần commit, chỉ gọi repository mà không tạo transaction mới có thể cho kết quả khó đoán.

Giải pháp rõ ràng: tách trách nhiệm ghi dữ liệu vào một bean có `REQUIRES_NEW`:

~~~java
@Service
class NotificationLogWriter {

    private final NotificationLogRepository logs;

    NotificationLogWriter(NotificationLogRepository logs) {
        this.logs = logs;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(UUID orderId) {
        logs.save(new NotificationLog(orderId));
    }
}

@Component
class NotificationLogListener {

    private final NotificationLogWriter writer;

    NotificationLogListener(NotificationLogWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPlaced event) {
        writer.record(event.orderId());
    }
}
~~~

Đây là đoạn minh họa cách chia bean; `NotificationLogRepository`, `NotificationLog` và các import được lược bỏ. Phương thức `record` phải được gọi **qua Spring proxy**, vì lời gọi nội bộ `this.record(...)` có thể không áp dụng `@Transactional`.

Trước khi thêm `REQUIRES_NEW`, cần xác định có transaction manager phù hợp và giới hạn số transaction đồng thời, nhất là khi khối lượng event lớn. Hãy kiểm tra trạng thái lưu thực tế bằng integration test với database.

### 8.1. Khi nào nên dùng @ApplicationModuleListener?

Nếu xử lý giữa các module là công việc sau commit và có thể chạy bất đồng bộ, Spring Modulith cung cấp `@ApplicationModuleListener`:

~~~java
@Component
class NotificationListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Xử lý với ngữ nghĩa transactional và bất đồng bộ của Spring Modulith.
    }
}
~~~

Annotation này là tiện ích kết hợp các cơ chế liên quan đến transactional listener, async và transaction mới. Không nên đồng thời gắn một listener tương đương chỉ để xử lý lại cùng side effect nếu không chủ ý có hai consumer.

Với async listener, `publishEvent` hoặc `TransactionTemplate` có thể hoàn tất **trước khi** side effect được xử lý xong. Test phải chờ **điều kiện nghiệp vụ**, chẳng hạn bản ghi notification xuất hiện trong database, thay vì dùng `Thread.sleep(200)` rồi đoán listener đã chạy.

Ví dụ khi dự án có dependency Awaitility:

~~~java
transactions.executeWithoutResult(status ->
        publisher.publishEvent(new OrderPlaced(orderId)));

await().atMost(Duration.ofSeconds(10))
       .untilAsserted(() ->
           assertThat(notificationLogs.existsByOrderId(orderId)).isTrue());
~~~

Đây là **đoạn assertion** của integration test, không phải một test độc lập: dự án cần khai báo Awaitility, `notificationLogs`, `transactions` và các import tương ứng. Spring Modulith còn có tiện ích `Scenario` để kiểm chứng diễn biến bất đồng bộ. Với rollback, một khoảng chờ hữu hạn chỉ cung cấp bằng chứng trong cửa sổ quan sát; nên kết hợp kiểm tra trạng thái publication/callback khi yêu cầu độ tin cậy cao.

## 9. Transaction rollback và độ tin cậy sự kiện

Giả sử module `orders` ghi đơn hàng và phát event trong cùng transaction. Có ba tình huống thường gặp:

| Tình huống | Dữ liệu đơn hàng | Listener `AFTER_COMMIT` | Ý nghĩa |
| --- | --- | --- | --- |
| Transaction nguồn commit, listener thành công | Đã commit | Được gọi, xử lý xong | Luồng thành công kỳ vọng. |
| Transaction nguồn rollback | Không commit | Không được gọi | Không tạo side effect downstream dựa trên đơn hàng thất bại. |
| Transaction nguồn commit, listener sau commit thất bại | Đã commit | Được gọi nhưng gặp lỗi | Không thể đơn giản rollback lại transaction nguồn; cần chính sách lỗi, retry và idempotency. |

Điểm giới hạn: `@TransactionalEventListener(AFTER_COMMIT)` **giúp gắn việc xử lý với lần commit**, nhưng không phải bảo đảm giao sự kiện bền vững trong mọi trường hợp, cũng không tự tạo cơ chế gửi chính xác một lần.

Khi ứng dụng sử dụng **Event Publication Registry** của Spring Modulith với lưu trữ và cấu hình phù hợp, có thể theo dõi các publication tới transactional listener, trạng thái hoàn tất và chính sách xử lý lại. Dù vậy, consumer vẫn nên thiết kế **idempotency** theo nhu cầu: ví dụ dùng `eventId` hoặc một khóa nghiệp vụ phù hợp để không ghi trùng khi một event được giao lại.

Một event trong Spring application context không mặc nhiên là message qua broker, không mặc nhiên có outbox và không tự có retry nếu ứng dụng chưa cấu hình những cơ chế đó.

## 10. Quality gate trong CI cho thời điểm phát event

Bài học thuộc `SPRING_MODULITH_VERIFICATION_TESTING` nên kết hợp kiểm chứng ranh giới tĩnh với test runtime:

| Quality gate | Rủi ro ngăn chặn | Test mẫu |
| --- | --- | --- |
| **Module boundary** | Module nhận truy cập class nội bộ hoặc tạo phụ thuộc vòng. | `ApplicationModules.of(ShopApplication.class).verify()` |
| **Event publication** | Nghiệp vụ quên phát event hoặc payload sai. | `@ApplicationModuleTest` + `PublishedEvents` |
| **Transaction phases** | Listener chạy sai pha hoặc chạy khi rollback. | `TransactionTemplate` + probe `BEFORE_COMMIT`/`AFTER_COMMIT`/`AFTER_ROLLBACK` |
| **Database integration** | Ghi dữ liệu sau commit không được commit trong transaction mới. | Integration test xác nhận bản ghi thực sau callback. |
| **Async/retry** | Test flaky, bỏ sót event hoặc tạo side effect trùng. | Test chờ theo trạng thái, kiểm tra idempotency và registry nếu dùng. |

Cấu hình pipeline chạy các tác vụ test chuẩn của dự án (ví dụ `./gradlew test` hoặc `./mvnw test` nếu dự án có wrapper tương ứng) và thất bại khi một kiểm tra quan trọng thất bại. Nếu test cần database, dùng môi trường test có transaction semantics phù hợp và cô lập fixture giữa các lần chạy CI.

**Không dùng một loại test để suy ra tất cả:** `ApplicationModules.verify()` không chứng minh listener đã chạy; `PublishedEvents` không chứng minh transaction đã commit; một integration test commit thành công không chứng minh rollback được xử lý đúng.

## 11. Những nhầm lẫn thường gặp

1. **“Phát trong transaction nghĩa là event chỉ được tạo sau commit.”** Sai. Lời gọi `publishEvent` xảy ra ngay; chỉ một số listener được dời tới các pha transaction.
2. **“Phát sau khi TransactionTemplate trả về thì listener AFTER_COMMIT sẽ chạy.”** Sai nếu không có transaction mới lúc phát và `fallbackExecution=false`.
3. **“@EventListener luôn an toàn trước rollback.”** Sai với các tác động ngoài transaction; side effect có thể đã xảy ra trước khi rollback.
4. **“@TransactionalEventListener mặc định chạy khi không có transaction.”** Sai. Theo mặc định, sự kiện không có transaction sẽ không kích hoạt listener.
5. **“BEFORE_COMMIT là bằng chứng commit đã thành công.”** Sai: transaction vẫn có thể thất bại sau callback.
6. **“Test gắn @Transactional nhưng gọi TransactionTemplate là có commit thật.”** Chưa chắc: propagation mặc định có thể khiến `TransactionTemplate` tham gia transaction test rồi bị rollback.
7. **“Listener sau commit gọi repository là tự động ghi bền vững.”** Không bảo đảm. Ghi database sau commit thường cần transaction mới.
8. **“Module test thấy event là đủ chứng minh mọi module xử lý xong.”** Sai. Phải kiểm tra độc lập publication, listener và trạng thái database hoặc side effect phù hợp.
9. **“@ApplicationModuleListener xử lý xong trước khi hàm phát trả về.”** Không nên giả định vì listener có ngữ nghĩa bất đồng bộ.

## 12. Bài tập tình huống

Trong hệ thống thanh toán, `PaymentService` phát `PaymentSucceeded`. Module `shipping` nhận event để đánh dấu đơn hàng đủ điều kiện giao vận.

Xét ba phiên bản:

~~~java
// A: phát trước khi mở transaction lưu payment.
events.publishEvent(new PaymentSucceeded(paymentId));
paymentWriter.persistSuccess(paymentId);

// B: phát bên trong một phương thức @Transactional.
@Transactional
public void pay(UUID paymentId) {
    paymentRepository.markSucceeded(paymentId);
    events.publishEvent(new PaymentSucceeded(paymentId));
}

// C: transaction hoàn tất trước, rồi mới phát.
transactions.executeWithoutResult(status ->
    paymentRepository.markSucceeded(paymentId));
events.publishEvent(new PaymentSucceeded(paymentId));
~~~

Giả định A và C được gọi khi không có transaction bao ngoài; `paymentWriter.persistSuccess` mở transaction riêng. Listener của `shipping` được khai báo `@TransactionalEventListener` mặc định.

**Câu hỏi:**

1. Ở A, listener `shipping` có chạy không? Điều gì xảy ra nếu `persistSuccess` thất bại?
2. Ở B, nếu transaction commit thành công, listener chạy lúc nào? Nếu rollback thì sao?
3. Ở C, listener có tự chạy vì transaction *đã* commit không?
4. Nếu C bật `fallbackExecution=true`, listener chạy theo ngữ nghĩa nào?
5. Test nào xác nhận `payment` phát event đúng? Test nào xác nhận `shipping` chỉ cập nhật dữ liệu sau commit?

**Đáp án tham khảo:**

1. Không, vì khi A phát event chưa có transaction và mặc định không fallback; việc lưu thất bại sau đó không thay đổi sự thật event đã được phát.
2. Ở B, lệnh phát diễn ra trong transaction; listener `AFTER_COMMIT` chỉ chạy sau commit thành công. Khi rollback, listener đó không chạy.
3. Không. Ở C, transaction đã hoàn tất trước khi phát nên listener không có transaction để đăng ký callback.
4. Khi không có transaction, fallback cho phép listener xử lý ngay; nó không hồi tưởng hay gắn lại vào commit đã qua.
5. Dùng `@ApplicationModuleTest` kết hợp `PublishedEvents` ở `payment`; dùng module/integration test kiểm soát transaction và kiểm tra dữ liệu cuối cùng ở `shipping`, kèm test rollback.

## 13. Checklist triển khai và kiểm chứng

- [ ] Xác định chính xác **điểm gọi `publishEvent`** và **transaction đang hoạt động tại điểm đó**.
- [ ] Phân biệt “phát event” với “listener được gọi theo pha transaction”.
- [ ] Chọn `@EventListener`, `@TransactionalEventListener` hoặc `@ApplicationModuleListener` theo nghiệp vụ.
- [ ] Giữ `fallbackExecution=false` khi chỉ chấp nhận event có transaction; nếu bật fallback, có lý do rõ ràng.
- [ ] Kiểm thử riêng event phát ngoài transaction, trong transaction commit và trong transaction rollback.
- [ ] Không để `@Transactional` trên test vô tình ngăn lần commit cần kiểm tra.
- [ ] Nếu listener ghi database sau commit, dùng transaction phù hợp và test xác nhận dữ liệu bền vững.
- [ ] Với listener async, chờ điều kiện nghiệp vụ thay vì sleep cố định.
- [ ] Event payload thuộc API module được công bố; module nhận không import implementation nội bộ.
- [ ] Có `ApplicationModules.verify()`, `PublishedEvents` và integration tests trong CI.
- [ ] Nếu dùng registry/retry, kiểm thử thất bại downstream, phát lại và idempotency.

**Kết luận:** Câu hỏi “Event được phát trước, trong hoặc sau transaction?” phải được trả lời bằng **thời điểm gọi `publishEvent`**, sau đó mới xét **pha listener, kết quả commit/rollback và side effect thực tế**. Phân biệt rõ các bước này giúp xây dựng kiểm thử Spring Modulith chính xác, tránh phụ thuộc sai và ngăn hồi quy trong CI.

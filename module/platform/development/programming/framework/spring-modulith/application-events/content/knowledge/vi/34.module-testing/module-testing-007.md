# Test listener trong module

## Mục tiêu

Application event listener thường chứa logic quan trọng: cập nhật projection, tạo tác vụ tiếp theo, đồng bộ dữ liệu hoặc điều phối một phần quy trình nghiệp vụ. Một unit test gọi trực tiếp method listener có thể kiểm tra logic bên trong, nhưng chưa chứng minh listener được Spring phát hiện, được nối với đúng module, chạy đúng transaction boundary và nhận event theo cách ứng dụng thực sự vận hành.

Spring Modulith cung cấp `@ApplicationModuleTest` để khởi tạo ngữ cảnh kiểm thử theo ranh giới module. Kết hợp với `Scenario`, test có thể kích hoạt hành vi trong module và chờ event tiếp theo xuất hiện, phù hợp với listener bất đồng bộ và luồng event nhiều bước.

Sau bài học, bạn có thể:

- Chọn đúng phạm vi Spring context cho test của một module.
- Kiểm thử listener bằng `@ApplicationModuleTest` và `Scenario`.
- Xác minh event đầu vào tạo ra thay đổi nghiệp vụ hoặc event đầu ra mong đợi.
- Kiểm thử listener đồng bộ, bất đồng bộ và xử lý sau commit.
- Phân biệt unit test listener với module integration test.
- Kiểm tra duplicate, lỗi listener, transaction và tính cô lập của test.

## 1. Vì sao cần test listener ở cấp module?

Giả sử module Kho nhận `OrderPlaced` để giữ hàng. Listener có thể gọi `InventoryService`, cập nhật database và phát `InventoryReserved`. Có nhiều điều cần được xác minh cùng lúc:

- Spring có khởi tạo đúng module Kho và phát hiện listener không?
- Event có được chuyển tới đúng listener không?
- Listener có gọi đúng nghiệp vụ và cập nhật dữ liệu đúng không?
- Event đầu ra có được phát sau khi bước xử lý thành công không?
- Transaction rollback có ngăn side effect không?
- Listener bất đồng bộ có hoàn tất trong thời hạn kiểm thử không?
- Module có vô tình phụ thuộc vào implementation nội bộ của module khác không?

Unit test thuần có thể kiểm tra một class bằng mock, nhưng thường không khởi tạo Spring event infrastructure, transaction listener hay cấu hình module. Module test bổ sung lớp kiểm chứng này trong một Spring context có phạm vi giới hạn.

Không phải mọi listener đều cần full application context. Chọn phạm vi nhỏ nhất có thể chứng minh hành vi cần kiểm tra; chỉ mở rộng bootstrap khi listener thực sự phụ thuộc module khác.

## 2. Chuẩn bị module test

Trong dự án dùng Spring Modulith, test support thường được cung cấp qua dependency `spring-modulith-starter-test` phù hợp với phiên bản Spring Modulith của ứng dụng.

Ví dụ khai báo dependency Maven:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dự án dùng Gradle, thêm artifact tương ứng với cấu hình test của dự án và để dependency management/BOM quản lý version đồng bộ. Không trộn các version Spring Modulith khác nhau giữa runtime và test support.

### Đặt test trong package của module

`@ApplicationModuleTest` cần xác định module đang được kiểm thử. Đặt class test trong package thuộc module, thường là package gốc của module hoặc package con phù hợp với cấu trúc ứng dụng.

Ví dụ cấu trúc:

```text
com.example.shop
  ShopApplication.java
  inventory
    InventoryConfiguration.java
    InventoryService.java
    InventoryEventListener.java
    InventoryRepository.java
  orders
    OrderApplicationService.java
    OrderPlaced.java
```

Test listener của module `inventory` có thể đặt trong `com.example.shop.inventory` hoặc package con của nó. Nếu test đặt ngoài package module, Spring Modulith có thể không xác định được module mong muốn hoặc bootstrap phạm vi không như dự kiến.

### Bootstrap mode

`@ApplicationModuleTest` hỗ trợ các phạm vi bootstrap khác nhau. Các mode phổ biến:

| Mode | Phạm vi khởi tạo | Khi nên dùng |
| --- | --- | --- |
| `STANDALONE` | Chỉ module đang test và cấu hình cần thiết của nó. | Kiểm tra module cô lập; các dependency ngoài ranh giới cần được thay thế hoặc cấu hình riêng. |
| `DIRECT_DEPENDENCIES` | Module đang test cùng các module mà nó phụ thuộc trực tiếp. | Kiểm tra listener cần gọi API công khai của module lân cận. |
| `ALL_DEPENDENCIES` | Module đang test cùng toàn bộ dependency module theo đồ thị phụ thuộc. | Chỉ dùng khi hành vi cần kiểm tra thực sự đi qua nhiều module. |

Ví dụ chọn mode tường minh:

```java
@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class InventoryEventListenerTests {
    // Test thuộc module inventory.
}
```

Tên mode và hành vi bootstrap cần khớp phiên bản Spring Modulith mà dự án đang sử dụng. Nếu test chỉ cần module Kho, chọn `STANDALONE`; nếu listener gọi module Đơn hàng qua API công khai, có thể chọn `DIRECT_DEPENDENCIES`. Tránh dùng `ALL_DEPENDENCIES` theo thói quen vì Spring context lớn làm test chậm và che khuất dependency không cần thiết.

## 3. Listener mẫu cần kiểm thử

Giả sử module Kho nhận event `OrderPlaced`, giữ hàng và phát `InventoryReserved` khi thành công.

Event đầu vào:

```java
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        List<OrderLine> lines) {}

public record OrderLine(String sku, int quantity) {}
```

Event đầu ra:

```java
public record InventoryReserved(
        UUID orderId,
        String reservationId) {}
```

Listener:

```java
@Component
class InventoryEventListener {

    private final InventoryService inventory;
    private final ApplicationEventPublisher events;

    InventoryEventListener(
            InventoryService inventory,
            ApplicationEventPublisher events) {
        this.inventory = inventory;
        this.events = events;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        Reservation reservation = inventory.reserve(
                event.orderId(), event.lines());

        events.publishEvent(new InventoryReserved(
                event.orderId(), reservation.id()));
    }
}
```

`@ApplicationModuleListener` là lựa chọn phù hợp cho listener module cần xử lý bất đồng bộ sau commit theo semantics của Spring Modulith. Listener được kiểm thử ở cấp module nên test nên kích hoạt event qua event infrastructure thay vì chỉ gọi `on(...)` trực tiếp.

## 4. Dùng `@ApplicationModuleTest` và `Scenario`

`Scenario` là API kiểm thử của Spring Modulith giúp kích hoạt hành vi và chờ một event khác xuất hiện. Cách này đặc biệt hữu ích khi listener bất đồng bộ: test không cần đoán thời điểm listener chạy bằng `Thread.sleep()`.

Ví dụ:

```java
@ApplicationModuleTest
class InventoryEventListenerTests {

    @Autowired
    Scenario scenario;

    @Test
    void reservesInventoryWhenOrderWasPlaced() {
        UUID orderId = UUID.randomUUID();
        OrderPlaced event = new OrderPlaced(
                UUID.randomUUID(),
                orderId,
                List.of(new OrderLine("SKU-100", 2)));

        scenario.publish(event)
                .andWaitForEventOfType(InventoryReserved.class)
                .toArrive();
    }
}
```

Test phát event đầu vào và chờ `InventoryReserved` xuất hiện. Việc chờ event đầu ra cho phép listener có thời gian chạy bất đồng bộ và làm test thất bại nếu event mong đợi không xuất hiện trong giới hạn chờ của Scenario.

Nếu muốn kiểm tra toàn bộ hành vi từ application service, hãy kích hoạt service thay vì publish event trực tiếp:

```java
@ApplicationModuleTest
class OrderToInventoryModuleTests {

    @Autowired
    Scenario scenario;

    @Autowired
    OrderApplicationService orders;

    @Test
    void placingOrderEventuallyReservesInventory() {
        PlaceOrder command = new PlaceOrder(
                customerId,
                List.of(new OrderLineInput("SKU-100", 2)));

        scenario.stimulate(() -> orders.place(command))
                .andWaitForEventOfType(InventoryReserved.class)
                .toArrive();
    }
}
```

Ví dụ thứ hai kiểm tra luồng bắt đầu từ use case, qua transaction publish event, rồi tới listener của module Kho. Đây là cách hữu ích khi cần chứng minh event chỉ được phát từ một thay đổi nghiệp vụ đã commit.

### Chờ đúng event cần quan sát

Nếu một listener phát nhiều event cùng loại, nên dùng khả năng lọc/matching mà Scenario API của phiên bản dự án cung cấp, hoặc gắn định danh tương quan vào event để phân biệt. Không nên chỉ chờ “có một event cùng type” rồi mặc định đó là event của test hiện tại.

Giữ test độc lập bằng ID riêng cho mỗi test. Nếu test có thể chạy song song, tránh dùng một event ID cố định hoặc dữ liệu database dùng chung.

## 5. Kiểm tra trạng thái dữ liệu sau khi listener chạy

Event đầu ra chứng minh một bước giao tiếp đã xảy ra, nhưng chưa chắc chứng minh toàn bộ trạng thái persistence đúng. Với listener cập nhật database, nên kiểm tra kết quả qua repository hoặc query API công khai của module.

Ví dụ:

```java
@ApplicationModuleTest
class InventoryEventListenerTests {

    @Autowired
    Scenario scenario;

    @Autowired
    ReservationRepository reservations;

    @Test
    void persistsReservationForPlacedOrder() {
        UUID orderId = UUID.randomUUID();
        OrderPlaced event = new OrderPlaced(
                UUID.randomUUID(),
                orderId,
                List.of(new OrderLine("SKU-100", 2)));

        scenario.publish(event)
                .andWaitForEventOfType(InventoryReserved.class)
                .toArrive();

        Reservation saved = reservations.findByOrderId(orderId).orElseThrow();
        assertThat(saved.items()).containsEntry("SKU-100", 2);
    }
}
```

Ví dụ dùng repository của chính module Kho để kiểm tra trạng thái. Khi test module khác, ưu tiên gọi API/query contract được công khai thay vì truy cập repository hoặc bảng nội bộ của module Kho.

Không nên chỉ kiểm tra event đầu ra nếu listener có thể phát event trước khi persistence commit. Hãy đặt publication trong transaction phù hợp và kiểm tra trạng thái sau khi Scenario xác nhận event đã tới; với yêu cầu nghiêm ngặt, xác minh cả commit boundary bằng integration test.

## 6. Test listener đồng bộ và bất đồng bộ

### Listener đồng bộ

Với `@EventListener` đồng bộ, listener thường được gọi trong thread publish event nếu không có async executor hoặc cơ chế chuyển thread khác. Unit test có thể gọi publisher và kiểm tra kết quả ngay sau khi dispatch hoàn tất.

```java
@ApplicationModuleTest
class SynchronousListenerTests {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    AuditRepository audit;

    @Test
    void recordsAuditWhenOrderPlaced() {
        publisher.publishEvent(orderPlaced);

        assertThat(audit.existsByOrderId(orderPlaced.orderId())).isTrue();
    }
}
```

Nếu listener dùng `@TransactionalEventListener`, transaction phase có thể khiến xử lý chỉ diễn ra sau commit. Khi đó test phải tạo transaction và commit rõ ràng; không áp dụng giả định đồng bộ đơn giản ở trên.

### Listener bất đồng bộ

Với `@ApplicationModuleListener`, tránh assert ngay sau `publishEvent` vì listener có thể chưa chạy xong. Dùng `Scenario` để chờ event đầu ra hoặc một điều kiện hoàn tất có timeout. Nếu kiểm tra trạng thái database, hãy chờ mốc xác nhận phù hợp rồi mới đọc.

Không dùng `Thread.sleep(500)` để “cho listener đủ thời gian”. Test sẽ flaky trên CI hoặc máy tải cao. Chờ một điều kiện cụ thể bằng Scenario, latch, future hoặc Awaitility.

### Listener sau commit

Kiểm thử cả hai nhánh:

- Transaction publisher commit: listener được phép xử lý event.
- Transaction publisher rollback: listener sau commit không được xử lý event của transaction bị rollback.

Ví dụ ý tưởng kiểm thử rollback:

```java
@Test
void doesNotRunAfterPublishingTransactionRollsBack() {
    transactionTemplate.executeWithoutResult(status -> {
        orderService.publishOrderPlaced(orderId);
        status.setRollbackOnly();
    });

    // Xác minh listener không tạo reservation cho orderId này.
    assertThat(reservations.findByOrderId(orderId)).isEmpty();
}
```

Đây là skeleton: transaction manager, listener phase và test boundary phải khớp cấu hình thực tế. Nếu có executor bất đồng bộ, cần dùng điều kiện chờ/quan sát phù hợp để tránh assertion chạy trước khi hệ thống hoàn tất các công việc liên quan.

## 7. Dùng `@RecordApplicationEvents` để kiểm tra event

Spring Test cung cấp `@RecordApplicationEvents` và `ApplicationEvents` để ghi nhận application event được publish trong test. Cách này hữu ích khi muốn xác nhận event đầu ra, số lượng event hoặc payload.

Ví dụ:

```java
@RecordApplicationEvents
@ApplicationModuleTest
class InventoryPublicationTests {

    @Autowired
    ApplicationEvents applicationEvents;

    @Autowired
    InventoryApplicationService inventory;

    @Test
    void publishesInventoryReserved() {
        inventory.reserve(orderId, requestedLines);

        assertThat(applicationEvents.stream(InventoryReserved.class))
                .hasSize(1);
    }
}
```

`ApplicationEvents` phù hợp để quan sát publication trong phạm vi test. Với listener async, cần kiểm tra semantics ghi nhận event của phiên bản Spring Test và chờ listener hoàn tất trước khi assert. Nếu mục tiêu là đồng bộ hóa với luồng xử lý bất đồng bộ, `Scenario` thường diễn đạt ý định chờ rõ ràng hơn.

Không dùng event recording thay cho kiểm tra trạng thái persistence khi listener có side effect. Event được publish không chứng minh transaction ghi dữ liệu đã commit.

## 8. Kiểm thử listener gọi module khác

Listener có thể cần dữ liệu hoặc API từ module khác. `@ApplicationModuleTest` cho phép chọn bootstrap mode để đưa các dependency cần thiết vào context.

Ví dụ listener module Thanh toán cần gọi API công khai của module Đơn hàng:

```java
@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class PaymentEventListenerTests {

    @Autowired
    Scenario scenario;

    @Test
    void capturesPaymentForConfirmedOrder() {
        scenario.publish(orderConfirmed)
                .andWaitForEventOfType(PaymentCaptured.class)
                .toArrive();
    }
}
```

Test nên dùng implementation thật của module dependency nếu mục tiêu là kiểm tra tương tác module. Với hệ thống ngoài như payment gateway, email provider hoặc broker, có thể thay thế adapter ở ranh giới đó bằng fake/test double để test không gọi dịch vụ thật.

Không mock repository nội bộ của module đang được kiểm thử trong mọi test. Làm vậy có thể khiến test chỉ xác minh lời gọi method mà bỏ qua mapping, query, transaction và persistence. Mock phù hợp ở ranh giới ngoài hoặc khi unit test một collaborator riêng.

### Kiểm tra ranh giới module

Module test kiểm tra hành vi listener; kiểm tra kiến trúc module là một mục tiêu khác. Có thể dùng `ApplicationModules` trong một architecture test riêng để xác minh dependency không vượt qua ranh giới đã khai báo. Không nên suy luận rằng một module test chạy thành công là mọi dependency rule đều hợp lệ.

## 9. Kiểm thử duplicate, retry và lỗi listener

Event listener có thể được gọi lại khi publication chưa hoàn tất được resubmit, hoặc khi hạ tầng giao event theo at-least-once. Vì vậy, test listener cần kiểm tra idempotency nếu side effect có thể bị lặp.

Các tình huống nên có:

- Cùng event ID được xử lý hai lần nhưng reservation chỉ được tạo một lần.
- Listener ném exception; publication được giữ ở trạng thái chưa hoàn tất theo cấu hình registry.
- Sau khi dependency phục hồi, retry/resubmission hoàn tất mà không lặp side effect.
- Event không hợp lệ được quarantine hoặc trả về kết quả nghiệp vụ theo policy.
- Ghi failure record thất bại thì listener không được nuốt exception và kết thúc sai.

Ví dụ kiểm tra duplicate ở cấp handler:

```java
@Test
void duplicateEventDoesNotCreateSecondReservation() {
    listener.on(orderPlaced);
    listener.on(orderPlaced);

    assertThat(reservationRepository.countByOrderId(orderPlaced.orderId()))
            .isEqualTo(1);
}
```

Đây là ví dụ minh họa yêu cầu idempotency; để kiểm tra concurrency và unique constraint, cần integration test với database thay vì chỉ gọi method hai lần tuần tự. Nếu listener được quản lý bởi Event Publication Registry, kiểm tra thêm trạng thái publication/resubmission theo cấu hình ứng dụng.

## 10. Test data, transaction và cô lập test

Test listener thường dùng database và executor. Dữ liệu test phải được cô lập để test chạy độc lập và có thể chạy song song.

Các nguyên tắc:

- Tạo ID riêng cho từng test, không dùng ID cố định có thể xung đột.
- Dọn dữ liệu hoặc dùng database/schema riêng theo test context.
- Xác định rõ transaction của test và transaction của listener async.
- Không giả định rollback của test sẽ rollback transaction listener đã commit riêng.
- Không chia sẻ mutable static fixture giữa các test.
- Dùng `@DirtiesContext` có chọn lọc; không dùng để che giấu rò rỉ state hoặc cấu hình sai.
- Khi cần kiểm tra constraint/locking, dùng database thật tương thích hoặc Testcontainers.

### Test context và thời gian chạy

Spring context khởi tạo tốn thời gian. Giữ package và bootstrap mode hẹp giúp test nhanh hơn. Các test có cùng cấu hình context có thể tái sử dụng context cache; thay đổi quá nhiều bean/configuration cho mỗi test làm cache giảm hiệu quả.

Không khởi tạo toàn bộ ứng dụng chỉ để test một listener đơn giản. Ngược lại, không cắt context quá nhỏ nếu mục tiêu là xác minh wiring, transaction và event infrastructure thật.

## 11. Ma trận kiểm thử listener trong module

| Tình huống | Điều cần xác minh |
| --- | --- |
| Event hợp lệ được publish | Listener được phát hiện và thực hiện đúng hành vi. |
| Listener phát event tiếp theo | Event đầu ra có đúng type và payload. |
| Listener ghi database | Trạng thái persistence đúng sau khi xử lý hoàn tất. |
| Publisher transaction commit | Listener after-commit được kích hoạt. |
| Publisher transaction rollback | Listener after-commit không tạo side effect. |
| Listener bất đồng bộ | Test chờ hoàn tất bằng Scenario/condition thay vì sleep. |
| Listener gọi module dependency | API công khai của dependency hoạt động trong bootstrap mode đã chọn. |
| Listener nhận event trùng | Side effect không bị lặp. |
| Listener ném exception | Publication/error state phản ánh đúng policy. |
| Listener retry thành công | Side effect hoàn tất idempotent và publication được xử lý xong. |
| Payload/version không hợp lệ | Validation và failure route đúng. |
| Test chạy song song | Không có fixture, database row hoặc probe dùng chung gây race. |

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ gọi trực tiếp method listener | Không kiểm tra Spring wiring và event dispatch. | Dùng `@ApplicationModuleTest` và publish event qua Scenario. |
| Dùng full application context cho mọi test | Test chậm và dependency không cần thiết bị kéo vào. | Chọn bootstrap mode theo module đang kiểm tra. |
| Assert ngay sau publish với listener async | Test đọc dữ liệu trước khi listener hoàn tất. | Chờ event/condition bằng Scenario hoặc công cụ đồng bộ hóa. |
| Dùng `Thread.sleep()` | Test flaky theo tốc độ máy/CI. | Chờ điều kiện cụ thể với timeout. |
| Nhầm event đã publish với dữ liệu đã commit | Bỏ sót lỗi transaction/persistence. | Kiểm tra trạng thái qua repository sau khi listener hoàn tất. |
| Không test rollback | Listener có thể chạy sai khi transaction publisher không commit. | Kiểm thử commit và rollback rõ ràng. |
| Mock mọi dependency nội bộ | Test không phát hiện lỗi wiring hoặc contract giữa module. | Dùng module dependency thật khi mục tiêu là integration. |
| Không test duplicate | Retry/resubmission tạo side effect lặp. | Kiểm thử idempotency và unique constraint. |
| Dùng bootstrap mode quá rộng | Test che khuất module dependency không mong muốn. | Giữ context ở phạm vi nhỏ nhất phù hợp. |

## 13. Quy trình áp dụng

Khi viết test listener cho một module Spring Modulith:

1. Xác định module sở hữu listener và đặt test trong package module đó.
2. Chọn `@ApplicationModuleTest` cùng bootstrap mode phù hợp.
3. Dùng `Scenario` để publish event hoặc kích hoạt application service và chờ event tiếp theo.
4. Kiểm tra cả event đầu ra lẫn trạng thái persistence cần thiết.
5. Với listener async/after-commit, tạo transaction boundary đúng và chờ hoàn tất bằng điều kiện có timeout.
6. Dùng `@RecordApplicationEvents` khi cần kiểm tra event được publish trong phạm vi test.
7. Kiểm thử dependency module qua API công khai; chỉ thay thế adapter của hệ thống ngoài khi phù hợp.
8. Kiểm tra duplicate, retry, lỗi listener và transaction rollback.
9. Cô lập test data, probe và executor để test chạy ổn định khi song song.
10. Giữ riêng architecture test để kiểm tra dependency rule giữa các module.

Test listener trong module cần chứng minh hành vi trong đúng ranh giới và transaction context mà ứng dụng sử dụng. Khi kết hợp `@ApplicationModuleTest`, `Scenario`, kiểm tra persistence và các trường hợp lỗi, nhóm phát triển có thể phát hiện sớm listener bị thiếu wiring, xử lý sai event hoặc không an toàn khi retry mà vẫn giữ test nhanh và tập trung.

# Viết module test

Module test trong Spring Modulith giúp kiểm tra một application module như một đơn vị có ranh giới rõ ràng: public API của module hoạt động đúng, listener xử lý event đúng, và module không phụ thuộc vào package nội bộ của module khác. Thay vì chỉ chạy một bài integration test khởi động toàn bộ ứng dụng, ta có thể bootstrap riêng module đang kiểm tra cùng những dependency cần thiết.

Bài thực hành này xây dựng bộ kiểm thử cho ứng dụng bán hàng có hai module `orders` và `inventory`. Module Orders xác nhận đơn hàng rồi phát `OrderConfirmed`; module Inventory nhận event bất đồng bộ để cập nhật projection tồn kho. Ta sẽ kiểm tra cấu trúc module, hành vi publisher, listener sau commit, xử lý trùng và các tình huống lỗi thường gặp.

## 1. Mục tiêu và phạm vi

Sau khi hoàn thành, bộ test cần chứng minh:

- Spring Modulith nhận diện đúng các module của ứng dụng.
- Các module chỉ phụ thuộc vào API được công bố và không truy cập package nội bộ trái phép.
- Use case của Orders phát event đúng khi đơn hàng được xác nhận.
- Listener của Inventory xử lý event sau khi transaction nguồn commit.
- Test chờ kết quả bất đồng bộ bằng condition có timeout, không dựa vào `Thread.sleep`.
- Event được xử lý lặp lại không tạo side effect nghiệp vụ trùng.
- Test có thể cô lập module, fixture và dữ liệu để chạy ổn định.

Phạm vi là kiểm thử module và luồng application events trong cùng ứng dụng Spring Modulith. Nếu event được externalize sang Kafka hoặc broker khác, cần thêm integration test riêng cho adapter và consumer; module test không tự chứng minh broker production hoạt động đúng.

## 2. Chuẩn bị cấu trúc dự án

Giả sử ứng dụng có package gốc `com.acme.shop` và các module trực tiếp bên dưới:

~~~text
com.acme.shop
  ShopApplication.java
  orders
    OrderManagement.java
    OrderConfirmed.java
    internal
      Order.java
      OrderRepository.java
      OrderManagementImpl.java
  inventory
    InventoryQuery.java
    internal
      InventoryProjection.java
      InventoryProjectionRepository.java
      OrderConfirmedListener.java
~~~

Spring Modulith suy ra module từ package cấu trúc dưới package ứng dụng. Trong ví dụ này, `orders` và `inventory` là hai module. Các implementation trong `internal` không phải API để module khác sử dụng.

Đặt test cùng package module để `@ApplicationModuleTest` xác định đúng module cần bootstrap:

~~~text
src/test/java/com/acme/shop
  ModularityTests.java
  orders
    OrderModuleTests.java
  inventory
    InventoryModuleTests.java
~~~

Test dùng chung thư viện test của Spring Modulith, JUnit Jupiter, AssertJ và Awaitility. Hãy quản lý version Spring Modulith qua BOM tương ứng với ứng dụng để các artifact cùng phiên bản.

Ví dụ dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Với Gradle, dùng artifact test tương ứng trong `testImplementation`. Không trộn các version Spring Modulith khác nhau giữa runtime và test.

## 3. Thiết kế event contract dùng trong bài test

Event cần mô tả sự kiện nghiệp vụ và độc lập với JPA entity. Dùng record bất biến với định danh và dữ liệu mà consumer cần:

~~~java
package com.acme.shop.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        Instant occurredAt,
        BigDecimal totalAmount,
        String currency) {
}
~~~

Payload có `eventId` để idempotency, `orderId` để xác định aggregate và `aggregateVersion` nếu consumer cần phát hiện event cũ hoặc sai thứ tự. Snapshot `totalAmount` và `currency` thể hiện giá trị tại thời điểm xác nhận; nếu consumer chỉ cần trạng thái hiện tại, có thể dùng query API công khai thay vì đưa thêm dữ liệu vào event.

Module Orders công bố event type này như một phần contract. Module Inventory phụ thuộc vào contract event công khai, không import entity hoặc repository nội bộ của Orders.

## 4. Kiểm tra cấu trúc module trước

Trước khi kiểm tra hành vi, tạo một architecture test để xác minh cấu trúc module:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.verify()` kiểm tra các quy tắc cấu trúc mà Spring Modulith nhận diện, bao gồm dependency giữa module và những vi phạm ranh giới được cấu hình. Bài test này không cần khởi động Spring ApplicationContext nên thường nhanh và phù hợp chạy ở mọi build.

Nếu test thất bại, đọc thông báo để xác định module nào đang truy cập package nội bộ hoặc tạo dependency không được phép. Sửa dependency qua API công khai hoặc điều chỉnh ranh giới module có chủ ý; không bỏ qua lỗi chỉ để test xanh.

## 5. Viết module test cho Orders

`@ApplicationModuleTest` bootstrap module chứa test class. Đặt `OrderModuleTests` trong package `com.acme.shop.orders` để kiểm tra module Orders.

~~~java
package com.acme.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Import;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
@Import(OrderModuleTestConfiguration.class)
class OrderModuleTests {

    @Autowired OrderManagement orders;
    @Autowired OrderTestFixture fixture;
    @Autowired Scenario scenario;

    @Test
    void publishesOrderConfirmedWhenOrderIsConfirmed() {
        UUID orderId = fixture.persistDraftOrder();

        scenario.stimulate(() -> orders.confirm(orderId))
                .andWaitForEventOfType(OrderConfirmed.class)
                .toArrive()
                .matching(event -> event.orderId().equals(orderId));
    }
}
~~~

`OrderTestFixture` là helper nằm trong test source của module, chịu trách nhiệm tạo dữ liệu đơn hàng hợp lệ. Nó có thể dùng factory/domain fixture hoặc repository nội bộ trong test của chính module Orders. Không đưa fixture đó vào production API.

Đăng ký helper bằng test configuration để Spring có thể inject nó:

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

import com.acme.shop.orders.internal.OrderRepository;

@TestConfiguration
class OrderModuleTestConfiguration {

    @Bean
    OrderTestFixture orderTestFixture(OrderRepository orders) {
        return new OrderTestFixture(orders);
    }
}
~~~

`Scenario` kích hoạt hành động và chờ event có kiểu mong đợi xuất hiện. Predicate `matching` ràng buộc event với `orderId` của test hiện tại, tránh nhận nhầm event do test khác hoặc dữ liệu khởi tạo phát ra.

Bài test trên xác minh publisher phát event. Nó chưa chứng minh listener Inventory đã hoàn tất cập nhật projection; phần đó được kiểm tra trong module test của Inventory.

## 6. Viết listener trong module Inventory

Module Inventory nhận event và cập nhật projection riêng. Listener nên mỏng, chuyển dữ liệu event vào service của module:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmedListener {

    private final InventoryProjectionService projection;

    OrderConfirmedListener(InventoryProjectionService projection) {
        this.projection = projection;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        projection.apply(event);
    }
}
~~~

`@ApplicationModuleListener` được dùng cho xử lý event bất đồng bộ theo cơ chế listener của Spring Modulith, gắn với ranh giới transaction của event. Trong cấu hình thông thường, listener được kích hoạt sau khi transaction phát event commit và việc xử lý listener có transaction riêng theo semantics của annotation. Hãy giữ đúng cấu hình executor và transaction manager của ứng dụng khi kiểm thử.

Service `InventoryProjectionService` thuộc module Inventory, nơi đặt logic idempotency và cập nhật projection. Module Orders không cần biết listener này tồn tại.

## 7. Module test cho listener bất đồng bộ

Test listener nên nằm trong package `com.acme.shop.inventory`. Dùng `TransactionTemplate` để phát event bên trong một transaction thực sự; transaction commit khi `executeWithoutResult` kết thúc. Sau đó Awaitility chờ projection được cập nhật:

~~~java
package com.acme.shop.inventory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.transaction.support.TransactionTemplate;

import com.acme.shop.orders.OrderConfirmed;

@ApplicationModuleTest
class InventoryModuleTests {

    @Autowired ApplicationEventPublisher events;
    @Autowired TransactionTemplate transactions;
    @Autowired InventoryProjectionRepository projections;

    @Test
    void updatesProjectionAfterEventTransactionCommits() {
        UUID orderId = UUID.randomUUID();
        OrderConfirmed event = new OrderConfirmed(
                UUID.randomUUID(),
                orderId,
                3L,
                Instant.now(),
                new BigDecimal("125.00"),
                "USD");

        transactions.executeWithoutResult(status ->
                events.publishEvent(event));

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
            var projection = projections.findByOrderId(orderId);
            assertThat(projection).isPresent();
            assertThat(projection.orElseThrow().aggregateVersion())
                    .isEqualTo(3L);
            assertThat(projection.orElseThrow().totalAmount())
                    .isEqualByComparingTo("125.00");
        });
    }
}
~~~

`InventoryProjectionRepository` và `findByOrderId` là API ví dụ của read model trong module Inventory. Điều chỉnh theo repository thực tế của dự án. Test chờ trạng thái đích, không chỉ chờ listener method được gọi.

Không gắn `@Transactional` lên test class hoặc test method này nếu điều đó giữ transaction ngoài mở tới cuối test. Listener xử lý sau commit sẽ không chạy khi transaction nguồn vẫn chưa commit. Dùng transaction của use case hoặc `TransactionTemplate` để kiểm soát thời điểm commit.

## 8. Phân biệt event đã phát và listener đã hoàn tất

Trong luồng bất đồng bộ có nhiều mốc riêng:

~~~mermaid
sequenceDiagram
    participant T as Module test
    participant O as Orders
    participant DB as Database
    participant E as Event bus
    participant I as Inventory listener
    T->>O: confirm(orderId)
    O->>DB: Update order
    DB-->>O: Commit
    O->>E: Publish OrderConfirmed
    O-->>T: Return
    E-->>I: Deliver asynchronously
    I->>DB: Update projection
    DB-->>I: Commit
    T->>DB: Await projection condition
~~~

Test publisher chờ event xuất hiện. Test listener chờ projection thay đổi. Nếu mục tiêu là end-to-end, test cần chờ trạng thái nghiệp vụ cuối cùng và gắn với event/order ID của scenario.

Không coi việc `Scenario` nhận event là bằng chứng mọi listener đã hoàn tất. Cũng không coi publication của externalization listener hoàn tất là bằng chứng consumer ở broker đã xử lý message.

## 9. Kiểm tra idempotency khi event được giao lặp

Retry hoặc resubmit có thể khiến cùng một event được giao nhiều lần. Module Inventory phải bảo đảm cùng `eventId` không cập nhật nghiệp vụ lặp.

Service có thể ghi dấu event đã xử lý trong cùng transaction với projection:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class InventoryProjectionService {

    private final ProcessedEventRepository processedEvents;
    private final InventoryProjectionRepository projections;

    @Transactional
    public void apply(OrderConfirmed event) {
        if (processedEvents.existsById(event.eventId())) {
            return;
        }

        projections.applySnapshot(
                event.orderId(),
                event.aggregateVersion(),
                event.totalAmount(),
                event.currency());

        processedEvents.save(new ProcessedEvent(event.eventId()));
    }
}
~~~

Để kiểm thử, publish cùng event hai lần trong hai transaction đã commit, chờ projection được cập nhật rồi xác minh chỉ có một dấu xử lý cho event ID đó. Trong database, đặt unique constraint cho `processed_event.event_id`; thao tác kiểm tra rồi ghi mà không có ràng buộc nguyên tử có thể gặp race condition khi hai listener chạy đồng thời.

Với side effect từ xa như gọi API vận chuyển, transaction database không thể rollback request đã được hệ thống đích thực hiện. Truyền idempotency key ổn định tới API đích hoặc tra cứu trạng thái trước khi gửi lại.

## 10. Kiểm tra rollback của transaction nguồn

Event listener sau commit không được thực hiện khi transaction phát event rollback. Có thể dùng `TransactionTemplate` đánh dấu rollback:

~~~java
transactions.executeWithoutResult(status -> {
    events.publishEvent(event);
    status.setRollbackOnly();
});
~~~

Trong test đầy đủ, dùng một probe hoặc projection riêng để xác minh không có kết quả xử lý được ghi nhận sau rollback. Condition phủ định cần có cửa sổ quan sát hữu hạn đủ lớn cho executor test; nếu cần tính xác định cao, kiểm tra cả trạng thái transaction và publication bằng cơ chế test phù hợp thay vì chỉ ngủ một khoảng thời gian tùy ý.

Test này giúp phát hiện việc phát event ngoài transaction mong muốn hoặc listener được cấu hình sai phase. Nó không thay thế kiểm tra transaction nghiệp vụ thực tế của use case.

## 11. Cô lập module và quản lý dependency test

Module test được thiết kế để chỉ bootstrap module cần thiết. Khi test cần một module phụ thuộc, chọn bootstrap mode phù hợp theo API của phiên bản Spring Modulith đang dùng; giữ phạm vi nhỏ nhất để test phản ánh ranh giới module.

Đối với dependency ngoài như HTTP client, email gateway hoặc broker:

- Thay bằng test adapter hoặc fake có hành vi xác định.
- Chỉ mock cổng mà module thực sự sở hữu, không mock sâu implementation nội bộ tùy tiện.
- Dùng Testcontainers hoặc môi trường tích hợp riêng khi cần kiểm tra database/broker thực.
- Không gọi hệ thống production hoặc mạng ngoài trong module test thông thường.

Nếu test không khởi động được do bean từ module khác, kiểm tra module có phụ thuộc công khai hợp lệ không. Không mở rộng context toàn ứng dụng chỉ để che một dependency không được khai báo.

## 12. Dữ liệu test và chạy song song

Event listener có thể tiếp tục chạy sau khi test method trả về nếu test kết thúc sớm. Để tránh nhiễm chéo:

- Tạo UUID riêng cho mỗi test.
- Chỉ truy vấn projection theo `orderId` của test.
- Chờ listener hoàn tất trước khi xóa fixture.
- Dùng repository hoặc cấu trúc thread-safe để quan sát kết quả.
- Reset fake dependency khi context được chia sẻ.
- Không dùng biến static hoặc counter singleton chung cho các test song song nếu không có cơ chế cô lập.

Fixture nên tạo dữ liệu tối thiểu hợp lệ và thể hiện rõ trạng thái đầu vào. Tránh dùng một bộ dữ liệu lớn chung khiến test phụ thuộc thứ tự chạy.

## 13. Ma trận module test cần có

| Test | Module | Điều cần chứng minh |
| --- | --- | --- |
| `ModularityTests` | Toàn ứng dụng | Module structure và dependency rule hợp lệ |
| `publishesOrderConfirmed...` | Orders | Use case xác nhận đơn hàng phát event đúng |
| `updatesProjection...` | Inventory | Listener xử lý event sau commit |
| `ignoresDuplicateEvent...` | Inventory | Cùng event ID không tạo side effect trùng |
| `doesNotHandleRolledBackEvent...` | Inventory | Transaction rollback không kích hoạt xử lý sau commit |
| `handlesInvalidEvent...` | Inventory | Lỗi dữ liệu được phân loại và quan sát rõ |

Không cần dồn tất cả vào một test class. Tách test theo module giúp chỉ ra module sở hữu hành vi và làm failure dễ định vị.

## 14. Lỗi thường gặp khi viết module test

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy bean của module khác | Test đang bootstrap module độc lập hoặc dependency chưa được công bố | Kiểm tra module API và chọn bootstrap mode phù hợp |
| Event không tới listener | Transaction chưa commit hoặc listener không được đăng ký | Kiểm tra transaction boundary và package/module scan |
| Test lúc xanh lúc đỏ | Đọc projection ngay sau publish hoặc dùng sleep cố định | Chờ condition bằng Awaitility với timeout |
| Listener chạy nhưng assertion sai | Test đang chờ nhầm event hoặc dữ liệu dùng chung | Lọc theo event ID/order ID duy nhất |
| `LazyInitializationException` | Event mang entity/proxy và listener truy cập lazy association | Chuyển sang immutable event DTO |
| Side effect bị nhân đôi | Listener không idempotent khi retry | Dùng event ID, unique constraint và idempotency key |
| Test context quá nặng | Bootstrap toàn ứng dụng cho mọi test | Dùng `@ApplicationModuleTest` theo module |

## 15. Tiêu chí nghiệm thu dự án

Hoàn thành bài thực hành khi:

1. Architecture test xác minh được cấu trúc module.
2. Test trong package Orders bootstrap được module và xác minh event phát ra.
3. Test trong package Inventory bootstrap được module và xác minh listener cập nhật projection sau commit.
4. Các test bất đồng bộ dùng Awaitility hoặc Scenario với timeout hữu hạn.
5. Test trùng event chứng minh idempotency.
6. Test rollback xác minh listener sau commit không xử lý event của transaction rollback.
7. Test không phụ thuộc vào thứ tự chạy hoặc ID dùng chung.
8. Các dependency ngoài được thay bằng fake/test adapter hoặc môi trường tích hợp kiểm soát.
9. Lỗi test cho biết module, event và condition bị lỗi.

## 16. Mở rộng sau module test

Khi các module test đã ổn định, có thể mở rộng theo nhu cầu:

- Dùng persistence adapter giống production để kiểm tra Event Publication Registry lưu và phục hồi publication incomplete.
- Kiểm thử serializer và contract version bằng payload mẫu.
- Dùng broker container để kiểm tra externalization, retry topic và DLT.
- Kiểm tra module documentation và module boundary bằng các test cấu trúc.
- Đo thời gian bootstrap và thời gian chờ để giữ suite nhanh.

Các bài kiểm thử broker, persistence recovery hoặc end-to-end có thể nằm ở tầng integration riêng. Không làm module test phụ thuộc hạ tầng nặng nếu mục tiêu chỉ là kiểm tra contract và hành vi trong module.

## Kết luận

Viết module test cho Spring Modulith bằng cách kiểm tra cấu trúc trước, sau đó bootstrap từng module với `@ApplicationModuleTest`. Dùng `Scenario` để xác minh publisher phát event và Awaitility để chờ kết quả listener bất đồng bộ. Phát event trong transaction có commit khi kiểm tra listener sau commit; kiểm tra idempotency, rollback và cô lập dữ liệu để test phản ánh đúng cách event được xử lý trong production. Bộ test theo module giúp bảo vệ ranh giới kiến trúc và làm cho thay đổi ở publisher hoặc listener dễ phát hiện, dễ định vị.

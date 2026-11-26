# Test module boundary

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events là một cách để các module giao tiếp mà không cần truy cập trực tiếp vào implementation nội bộ của nhau. Orders có thể công bố `OrderConfirmed`; Inventory lắng nghe event đó để giữ hàng; Notification gửi thông báo; Analytics cập nhật projection. Ranh giới module chỉ có ý nghĩa khi code và kiểm thử bảo vệ được hợp đồng này qua các lần thay đổi.

**Test module boundary** là kiểm thử xác nhận cấu trúc module, hướng phụ thuộc và các API được phép sử dụng. Với Spring Modulith, có thể kiểm tra cấu trúc bằng `ApplicationModules.verify()`, kiểm thử một module trong phạm vi cô lập bằng `@ApplicationModuleTest` và kiểm tra luồng application event bằng Scenario API. Các loại test này bổ sung cho nhau: một loại bảo vệ kiến trúc, một loại kiểm tra hành vi trong ranh giới module và một loại xác nhận giao tiếp qua event.

## 1. Module boundary bảo vệ điều gì?

Một module nghiệp vụ nên sở hữu dữ liệu, quy tắc và implementation của một phần domain. Module khác chỉ tương tác qua API được công bố hoặc event contract đã xác định.

Ví dụ, Orders sở hữu trạng thái đơn hàng. Inventory cần biết đơn đã được xác nhận để giữ hàng, nhưng không cần đọc repository, entity hoặc service nội bộ của Orders. Orders công bố `OrderConfirmed`; Inventory xử lý event và tự quyết định cách cập nhật dữ liệu tồn kho của mình.

Ranh giới module giúp bảo vệ:

- **Encapsulation:** implementation nội bộ không trở thành API ngầm cho module khác.
- **Dependency direction:** module chỉ phụ thuộc vào module hoặc named interface được cho phép.
- **Ownership:** mỗi module có quyền quyết định đối với domain model và dữ liệu của mình.
- **Change isolation:** refactor bên trong một module ít gây ảnh hưởng đến module khác.
- **Event contract:** producer và consumer thống nhất ngữ nghĩa, payload và vòng đời event.
- **Test isolation:** có thể kiểm tra một module mà không cần khởi động toàn bộ ứng dụng.

Nếu Inventory import `orders.internal.OrderRepository` hoặc gọi trực tiếp service nội bộ của Orders, hai module đã bị ghép chặt dù source code nằm ở hai package khác nhau. Kiểm thử boundary giúp phát hiện kiểu phụ thuộc này trước khi nó lan rộng.

## 2. Phân biệt module boundary test và module behavior test

Hai nhóm kiểm thử thường được gọi chung là module test nhưng có mục tiêu khác nhau.

| Loại test | Điều cần xác minh | Công cụ thường dùng |
|---|---|---|
| Structural/module boundary test | Module có đúng cấu trúc, dependency và visibility không? | `ApplicationModules.verify()` |
| Module integration test | Thành phần trong một module phối hợp đúng không? | `@ApplicationModuleTest` |
| Event scenario test | Event được phát và listener tạo kết quả mong đợi không? | `Scenario` API |
| Contract test | Producer và consumer hiểu cùng schema/ngữ nghĩa event không? | Serialization/contract tests |
| Broker integration test | Externalization và transport hoạt động đúng không? | Spring AMQP/Kafka integration tests |

Một test listener thành công không chứng minh module không phụ thuộc vào package nội bộ. Ngược lại, `ApplicationModules.verify()` không chứng minh listener xử lý đúng nghiệp vụ. Cần dùng đúng loại test cho từng rủi ro.

## 3. Cách Spring Modulith nhận diện module

Spring Modulith thường suy ra module ứng dụng từ package structure bên dưới package gốc của ứng dụng. Các package cấp cao tương ứng với module; package con thuộc module đó, trừ khi được khai báo thành cấu trúc đặc biệt theo mô hình modularity.

Ví dụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   ├── Order.java
│   ├── internal
│   │   └── OrderRepository.java
│   └── events
│       └── OrderConfirmed.java
├── inventory
│   ├── InventoryManagement.java
│   └── InventoryListener.java
└── notification
    └── OrderNotificationListener.java
~~~

Trong ví dụ này, `orders`, `inventory` và `notification` là các module ứng dụng. Các package con như `orders.internal` thuộc module Orders và không nên trở thành API mặc định cho module khác.

Package structure là một phần của kiến trúc. Nếu mọi class đều đặt trong một package chung hoặc các module được chia theo tầng kỹ thuật như `controllers`, `services`, `repositories`, Spring Modulith khó thể hiện ranh giới nghiệp vụ rõ ràng.

Hãy tổ chức package theo module/domain trước, sau đó mới chia package nội bộ theo trách nhiệm.

## 4. Kiểm tra cấu trúc bằng ApplicationModules.verify()

Spring Modulith cung cấp API `ApplicationModules` để khám phá và xác minh cấu trúc module. Một bài test kiến trúc cơ bản có thể gọi `verify()`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ShopApplication` là class ứng dụng nằm ở package gốc. Thay bằng application class thực tế của dự án.

Khi chạy, Spring Modulith phân tích các module và dependency được phát hiện, sau đó kiểm tra những quy tắc kiến trúc mà mô hình module đang áp dụng. Nếu có vi phạm, test thất bại và cung cấp thông tin về dependency hoặc access không hợp lệ.

Một test duy nhất này có thể trở thành architecture guard trong CI. Mỗi pull request chạy test để phát hiện module mới phụ thuộc ngược, chu trình dependency hoặc truy cập implementation nội bộ.

Không nên bỏ qua lỗi verification chỉ vì ứng dụng vẫn compile hoặc chạy được. Một dependency không hợp lệ hôm nay có thể biến thành thay đổi dây chuyền khi module sở hữu refactor.

## 5. Kiểm tra dependency direction

Mỗi module nên phụ thuộc vào các module khác theo hướng đã được thiết kế. Nếu Orders phát event để Inventory xử lý, Orders không cần biết Inventory có listener nào. Inventory phụ thuộc vào event contract mà Orders công bố, trong khi Orders không phụ thuộc ngược vào implementation của Inventory.

Ví dụ dependency hợp lý:

~~~text
Orders --publishes--> OrderConfirmed
Inventory --listens--> OrderConfirmed
Notification --listens--> OrderConfirmed
Analytics --listens--> OrderConfirmed
~~~

Ví dụ dependency không mong muốn:

~~~text
Orders --> InventoryService
Inventory --> OrdersInternalRepository
Orders --> NotificationSender
~~~

Các mũi tên trong sơ đồ đầu mô tả luồng event ở runtime; dependency compile-time của consumer hướng tới event contract được công bố. Producer không cần import listener hoặc service của consumer.

Khi thiết kế event package, đặt event contract ở vị trí có thể được consumer tham chiếu mà không mở toàn bộ package nội bộ của producer.

## 6. Giới hạn truy cập implementation nội bộ

Một module có thể cung cấp API công khai và giữ implementation trong package nội bộ. Named interface giúp công bố một package con cụ thể như một phần API có tên.

Ví dụ package chứa event contract:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Consumer có thể tham chiếu các kiểu event trong named interface này. Các package khác của Orders vẫn là nội bộ và không nên được import từ Inventory hoặc Notification.

Có thể hình dung API được công bố:

~~~text
orders
├── OrderManagement.java       (API module)
├── events                    (named interface: events)
│   └── OrderConfirmed.java
└── internal
    ├── Order.java
    └── OrderRepository.java
~~~

Named interface cần được thiết kế có chủ đích. Không đánh dấu toàn bộ package nội bộ là public chỉ để làm cho test qua. Mỗi interface công khai làm tăng cam kết tương thích mà module sở hữu phải duy trì.

## 7. Khai báo dependency được phép

Khi module cần phụ thuộc vào module khác, hãy thể hiện dependency đó rõ ràng trong mô hình Spring Modulith. Annotation `@ApplicationModule` có thể khai báo các dependency được phép; named interface có thể được dùng để giới hạn dependency vào API cụ thể.

Ví dụ minh họa trên package của consumer:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders::events"
)
package com.acme.shop.inventory;
~~~

Cú pháp module/named-interface và cách đặt annotation cần khớp với phiên bản Spring Modulith trong dự án. Ví dụ trên minh họa ý định: Inventory chỉ được phụ thuộc vào named interface `events` của Orders. Nếu phiên bản hoặc cấu trúc dự án dùng cách khai báo khác, hãy áp dụng API tương ứng nhưng giữ nguyên nguyên tắc dependency tối thiểu.

Việc khai báo allowed dependencies làm cho thay đổi kiến trúc trở nên tường minh. Nếu Inventory bắt đầu import package nội bộ của Orders, verification có thể báo vi phạm thay vì để phụ thuộc đó trở thành thói quen.

## 8. Phát hiện circular dependency

Circular dependency xuất hiện khi module A phụ thuộc B và B lại phụ thuộc A, trực tiếp hoặc qua chuỗi module khác.

Ví dụ:

~~~text
Orders --> Inventory
Inventory --> Shipping
Shipping --> Orders
~~~

Chu trình này làm thay đổi ở một module dễ lan sang các module còn lại. Nó cũng khiến thứ tự khởi tạo, kiểm thử và tách module thành service độc lập khó hơn.

Application module verification có thể phát hiện dependency cycle trong mô hình module. Khi gặp cycle, hãy xem lại quyền sở hữu domain và hướng event:

- Orders phát OrderConfirmed.
- Inventory nghe OrderConfirmed và phát InventoryReserved.
- Shipping nghe InventoryReserved và phát ShipmentCreated.
- Orders có thể nghe ShipmentCreated để cập nhật read model hoặc trạng thái hiển thị.

Luồng event cho phép module phản ứng mà không cần gọi ngược implementation của nhau. Tuy nhiên, không nên thay mọi dependency bằng event một cách máy móc. Query đồng bộ hoặc API công khai vẫn phù hợp khi caller thực sự cần kết quả ngay và dependency đó đã được thiết kế rõ.

## 9. Viết architecture test như một test độc lập

Nên đặt test cấu trúc module ở một vị trí dễ tìm, thường trong test source set của ứng dụng. Tên test nên thể hiện mục tiêu bảo vệ kiến trúc.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTests {

    @Test
    void applicationModulesMustRespectBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Các nguyên tắc:

- Test chạy tự động trong CI.
- Không phụ thuộc broker hoặc database nếu chỉ kiểm tra cấu trúc.
- Thất bại rõ khi có dependency không được phép.
- Có thông điệp lỗi đủ để xác định module và package vi phạm.
- Không tắt verification chỉ để merge một thay đổi ngắn hạn.
- Khi kiến trúc thay đổi có chủ đích, cập nhật khai báo dependency và test cùng pull request.

Không cần khởi động Spring ApplicationContext cho một kiểm tra cấu trúc thuần túy nếu API phân tích module có thể chạy trực tiếp. Điều này giúp architecture test nhanh và ít phụ thuộc môi trường.

## 10. Kiểm thử một module bằng @ApplicationModuleTest

Sau khi cấu trúc được xác minh, có thể kiểm thử hành vi của một module trong phạm vi module đó. Spring Modulith cung cấp `@ApplicationModuleTest` để bootstrap context theo module đang được kiểm thử.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class InventoryModuleTests {

    @Test
    void loadsInventoryModule() {
        // Assert module beans and behavior here.
    }
}
~~~

Test class thường được đặt trong package của module cần kiểm thử để framework xác định module tương ứng. Cách bootstrap giúp tập trung vào module được chọn và các dependency được cho phép theo mode.

Các mode bootstrap phổ biến:

- **STANDALONE:** chỉ bootstrap module đang kiểm thử cùng những thành phần cần thiết của nó.
- **DIRECT_DEPENDENCIES:** bootstrap module và các module mà nó phụ thuộc trực tiếp.
- **ALL_DEPENDENCIES:** bootstrap module cùng toàn bộ dependency theo đồ thị phụ thuộc.

Tên enum và cách chỉ định mode cần kiểm tra theo phiên bản Spring Modulith của dự án. Chọn mode nhỏ nhất đáp ứng mục tiêu test để giữ phạm vi rõ và phát hiện dependency bị thiếu sớm.

## 11. Khi nào dùng từng bootstrap mode?

| Mode | Phạm vi | Khi nên dùng |
|---|---|---|
| STANDALONE | Module đang test | Kiểm tra module tự hoạt động qua API và collaborator được cấu hình trong phạm vi module |
| DIRECT_DEPENDENCIES | Module cùng dependency trực tiếp | Cần tích hợp với API của module mà nó sử dụng |
| ALL_DEPENDENCIES | Module cùng dependency bắc cầu | Cần xác minh hành vi qua chuỗi module phụ thuộc |

Nếu test chỉ chạy được với ALL_DEPENDENCIES trong khi module được thiết kế độc lập, có thể module đang có dependency rộng hơn mong đợi. Hãy xem xét lại ranh giới trước khi tăng phạm vi bootstrap.

Không phải mọi test đều cần chạy cả ứng dụng. Test module boundary nên giữ phạm vi đủ nhỏ để chỉ rõ module nào đang được kiểm tra và dependency nào được đưa vào.

## 12. Kiểm thử event contract giữa các module

Event contract là phần giao diện mà producer cam kết với consumer. Test nên xác minh event biểu đạt đúng sự thật nghiệp vụ và mang đủ dữ liệu cần thiết cho consumer.

Ví dụ event:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    long orderVersion,
    Instant occurredAt
) {}
~~~

Các thuộc tính cần kiểm tra:

- Event type và ngữ nghĩa tên.
- Định danh event và aggregate.
- Version hoặc sequence nếu consumer cần xử lý thứ tự.
- Thời điểm xảy ra.
- Các trường bắt buộc và quy ước null.
- Tính tương thích serialization.
- Không chứa entity ORM hoặc chi tiết implementation nội bộ.

Không để consumer phụ thuộc vào toàn bộ entity Order chỉ để đọc một vài trường. Nếu payload cần thay đổi, hãy xem đó là thay đổi contract và đánh giá các consumer đang sử dụng named interface.

## 13. Kiểm thử event flow bằng Scenario API

Spring Modulith cung cấp Scenario API để kiểm thử việc phát application event và quan sát event tiếp theo được tạo ra bởi listener. Cách này hữu ích khi muốn xác minh module phản ứng với event mà không phải tự điều phối toàn bộ ApplicationContext.

Ví dụ minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class InventoryEventTests {

    @Test
    void reservesInventoryWhenOrderIsConfirmed(Scenario scenario) {
        OrderConfirmed event = new OrderConfirmed(
            UUID.randomUUID(),
            UUID.randomUUID(),
            1L,
            Instant.now()
        );

        scenario.publish(event)
            .andWaitForEventOfType(InventoryReserved.class)
            .toArriveAndVerify(reserved -> {
                assertThat(reserved.orderId()).isEqualTo(event.orderId());
            });
    }
}
~~~

Tên method và cách cấu hình Scenario cần đối chiếu phiên bản Spring Modulith đang dùng. Ý tưởng của test là publish event đầu vào, chờ event kết quả và xác minh dữ liệu của event đó. Với listener bất đồng bộ, API chờ giúp test không phải dùng sleep cố định.

Test nên tập trung vào contract của module: khi nhận OrderConfirmed hợp lệ, Inventory phát InventoryReserved với order ID tương ứng hoặc biểu đạt kết quả thất bại phù hợp. Không kiểm tra implementation private nếu hành vi công khai đã đủ để xác nhận.

## 14. Kiểm tra module không truy cập repository của module khác

Một boundary test có giá trị là phát hiện consumer truy cập trực tiếp persistence của producer.

Ví dụ thiết kế không mong muốn:

~~~java
@Component
class InventoryListener {

    private final OrderRepository orderRepository;

    void on(OrderConfirmed event) {
        Order order = orderRepository.findById(event.orderId())
            .orElseThrow();
        // Read producer's internal aggregate.
    }
}
~~~

Inventory đang phụ thuộc vào repository và aggregate nội bộ của Orders. Nếu Orders đổi schema hoặc cách lưu trữ, Inventory có thể bị ảnh hưởng.

Thiết kế tốt hơn là event mang dữ liệu mà consumer cần hoặc consumer gọi một API công khai đã được thiết kế:

~~~java
@Component
class InventoryListener {

    private final InventoryService inventory;

    void on(OrderConfirmed event) {
        inventory.reserve(
            event.orderId(),
            event.items()
        );
    }
}
~~~

Ví dụ thứ hai giữ việc cập nhật tồn kho trong module Inventory. Event contract cần cung cấp đủ thông tin theo yêu cầu nghiệp vụ; nếu payload lớn, có thể cung cấp một query API công khai nhưng phải đánh giá coupling và latency.

## 15. Kiểm thử ranh giới package và public API

Boundary không chỉ là dependency giữa hai module. Nó còn là visibility giữa package public và package internal.

Hãy kiểm tra:

- Consumer chỉ import public API hoặc named interface.
- Entity, repository và implementation class ở package internal không bị module khác tham chiếu.
- Không dùng reflection hoặc component scan để truy cập trái phép implementation.
- Không expose toàn bộ package chỉ để làm test compile.
- Event contract không phụ thuộc package của listener.
- Module không tạo shortcut bằng cách inject bean nội bộ của module khác.

Nếu một class cần được chia sẻ, hãy quyết định nó thực sự là API hay chỉ là implementation được đặt sai package. Không thêm named interface cho mọi package theo mặc định.

## 16. Kiểm thử event publication và transaction boundary

Một event contract đúng vẫn có thể được phát sai thời điểm. Test cần xác minh event chỉ được công bố theo transaction semantics mong muốn.

Ví dụ, nếu event biểu đạt trạng thái đã commit, listener có thể được thiết kế chạy sau commit. Kiểm thử nên xác minh:

- Transaction commit thì listener nhận event theo cấu hình.
- Transaction rollback thì listener không thực hiện tác dụng phụ dựa trên trạng thái chưa commit.
- Publication registry ghi nhận và hoàn tất publication theo listener.
- Listener lỗi không làm trạng thái publication bị đánh dấu hoàn tất sai.
- Retry hoặc resubmit không gây tác dụng phụ kép.

Có thể dùng `@RecordApplicationEvents` để ghi nhận event trong Spring test khi phù hợp. Với listener sau commit, test cần tạo transaction thực sự và xác minh hành vi commit/rollback; chỉ gọi method trong test không có transaction có thể không mô phỏng đúng tình huống production.

Không nên dùng một test scenario để thay thế integration test cho mọi thứ. Transaction, persistence registry và broker externalization có semantics riêng và cần được kiểm tra ở đúng lớp.

## 17. Phân biệt internal event test và broker integration test

Spring Modulith application event chạy trong phạm vi ứng dụng. Khi event được externalize, adapter chuyển event sang transport như RabbitMQ hoặc Kafka. Test module boundary không tự chứng minh broker ACL, routing, publisher confirm hoặc consumer acknowledgement.

Tách phạm vi:

| Phạm vi | Điều cần test |
|---|---|
| Module boundary | Không có dependency hoặc access trái phép |
| Internal event | Publisher và listener giao tiếp đúng trong ứng dụng |
| Publication registry | Publication được ghi, hoàn tất và phục hồi đúng |
| Externalization adapter | Event được chuyển thành message theo cấu hình |
| Broker integration | Routing, persistence, confirms, ack và retry |
| Consumer contract | Payload/schema tương thích và xử lý đúng |

Dùng broker test container hoặc môi trường tích hợp phù hợp cho transport test. Architecture test nên tiếp tục chạy nhanh, không cần khởi động broker chỉ để kiểm tra dependency graph.

## 18. Đưa module boundary test vào CI

Architecture test có giá trị khi chạy đều đặn cùng thay đổi code. Đưa test cấu trúc vào pipeline mặc định để pull request không thể vô tình phá vỡ dependency rule.

Quy trình gợi ý:

1. Developer thay đổi code hoặc thêm module.
2. Compile và unit tests chạy.
3. Architecture test gọi `ApplicationModules.verify()`.
4. Module integration tests chạy cho các module bị ảnh hưởng.
5. Event contract và serialization tests chạy khi contract thay đổi.
6. Broker integration tests chạy ở stage phù hợp nếu externalization thay đổi.
7. Pull request chỉ được merge khi các kiểm tra bắt buộc thành công.

Khi architecture test thất bại, review cần yêu cầu giải thích dependency mới. Nếu dependency là chủ đích, cập nhật module model hoặc named interface và kiểm tra rằng hướng phụ thuộc vẫn hợp lý. Không thêm allow rule rộng chỉ để làm test xanh.

## 19. Những lỗi thường gặp

**Chỉ kiểm thử hành vi, không kiểm tra cấu trúc.** Tất cả test nghiệp vụ có thể xanh trong khi module đã phụ thuộc vào repository nội bộ của nhau.

**Đặt test ở package sai.** `@ApplicationModuleTest` có thể không xác định module mà người viết mong đợi nếu test class nằm ngoài package/module phù hợp.

**Dùng bootstrap quá rộng.** Khởi động toàn bộ dependency khiến test khó chỉ ra module nào cần thành phần nào.

**Mở toàn bộ package để sửa lỗi boundary.** Thêm named interface quá rộng làm giảm encapsulation.

**Dùng event contract chứa entity nội bộ.** Consumer vô tình phụ thuộc persistence model và lazy association.

**Cho rằng verify() kiểm tra hành vi listener.** Structural verification chỉ kiểm tra cấu trúc module; event flow cần test riêng.

**Cho rằng Scenario test chứng minh broker hoạt động.** Scenario kiểm tra application event trong ứng dụng; transport cần integration test riêng.

**Bỏ qua cycle vì event flow có vẻ đúng.** Event runtime không tự loại bỏ mọi compile-time dependency; module vẫn có thể import trực tiếp implementation của nhau.

## 20. Quy trình tạo một module boundary test

Có thể áp dụng các bước sau khi bắt đầu hoặc refactor module:

1. Xác định package gốc ứng dụng và các module nghiệp vụ.
2. Liệt kê API công khai và named interface của từng module.
3. Xác định dependency được phép và hướng phụ thuộc.
4. Đặt test cấu trúc dùng `ApplicationModules.of(...).verify()`.
5. Chạy test và xử lý cycle hoặc access vi phạm.
6. Thêm `@ApplicationModuleTest` cho hành vi quan trọng của từng module.
7. Dùng Scenario API kiểm tra event contract và kết quả listener.
8. Thêm test transaction/publication registry nếu event cần độ tin cậy sau commit.
9. Thêm broker integration test khi externalization thay đổi.
10. Đưa các test phù hợp vào CI và review mọi thay đổi dependency.

Không cần tạo nhiều test giống nhau chỉ để tăng số lượng. Một architecture test toàn ứng dụng, kết hợp module tests tập trung vào các hành vi quan trọng, thường tạo tín hiệu rõ hơn.

## 21. Checklist test module boundary

- [ ] Package gốc và module nghiệp vụ được nhận diện rõ.
- [ ] Có architecture test gọi `ApplicationModules.verify()`.
- [ ] Dependency direction giữa module phù hợp với thiết kế.
- [ ] Không có circular dependency ngoài chủ đích.
- [ ] Consumer chỉ truy cập API hoặc named interface được công bố.
- [ ] Package internal, repository và entity không bị module khác import.
- [ ] Allowed dependencies được khai báo hẹp và có lý do.
- [ ] `@ApplicationModuleTest` đặt trong đúng package/module.
- [ ] Bootstrap mode nhỏ nhất đáp ứng test được lựa chọn.
- [ ] Event contract được kiểm tra về ngữ nghĩa và payload.
- [ ] Scenario test xác minh event đầu vào và kết quả đầu ra.
- [ ] Transaction commit/rollback và publication registry được test khi cần.
- [ ] Externalization/broker được kiểm tra riêng với transport integration test.
- [ ] Architecture test chạy trong CI.
- [ ] Không mở rộng public API chỉ để làm test qua.

## 22. Nguyên tắc bảo vệ module boundary

Test module boundary giúp biến kiến trúc thành quy tắc có thể thực thi. Dùng `ApplicationModules.verify()` để phát hiện dependency và access không hợp lệ; dùng `@ApplicationModuleTest` để kiểm tra hành vi trong phạm vi module; dùng Scenario API để xác minh event contract giữa publisher và listener.

Với Spring Modulith application events, producer nên công bố event contract thuộc quyền sở hữu của module mình, consumer chỉ phụ thuộc vào contract được mở và mỗi module tự giữ implementation cùng dữ liệu nội bộ. Khi architecture test chạy trong CI và các event flow quan trọng được kiểm thử riêng, hệ thống có thể phát triển thêm listener hoặc module mà không âm thầm phá vỡ ranh giới đã thiết kế.

# Kiểm tra ranh giới module trong Spring Modulith

Một ứng dụng có thể được chia thành nhiều package mang tên nghiệp vụ mà vẫn phụ thuộc chặt vào nhau. Chẳng hạn, module đặt hàng (`ordering`) trực tiếp gọi repository nội bộ của module thanh toán (`payment`), trong khi module thông báo (`notification`) truy vấn entity đặt hàng để gửi email. Mã nguồn vẫn có thể biên dịch và chạy được, nhưng ranh giới module đã bị xâm phạm; thay đổi nhỏ ở một module dễ kéo theo sửa đổi ở module khác.

Trong **Spring Modulith**, kiểm tra ranh giới là quá trình đối chiếu **mô hình module đã thiết kế** với **phụ thuộc thực tế của mã nguồn** và **cách các module tương tác khi chạy**. Với module học `SPRING_MODULITH_APPLICATION_EVENTS`, đây là bước quan trọng để tổ chức giao tiếp qua application events, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ trước khi phát triển các cơ chế sau commit, event publication registry, retry, kiểm thử và quan sát việc giao sự kiện.

## 1. Kết quả học tập

Hoàn thành bài này, bạn có thể:

- Đọc cấu trúc package và xác định đâu là application module, API công khai, named interface và phần triển khai nội bộ.
- Phát hiện các phụ thuộc xuyên ranh giới, phụ thuộc vòng và phụ thuộc trái với quy tắc `allowedDependencies`.
- Viết bài kiểm tra kiến trúc bằng `ApplicationModules.of(...).verify()`.
- Dùng `@ApplicationModuleTest` để khởi chạy và kiểm thử một module với phạm vi được kiểm soát.
- Kiểm chứng hướng phụ thuộc khi giao tiếp qua application events; phân biệt **phụ thuộc mã nguồn** với **luồng sự kiện khi chạy**.
- Thiết kế kiểm thử cho publish, commit/rollback, listener thất bại và xử lý lặp mà không nhầm kết quả kiểm tra cấu trúc với bảo đảm giao sự kiện.
- Biến kiểm tra ranh giới thành một bước xác minh lặp lại trong quá trình phát triển và CI.

## 2. Kiểm tra ranh giới nghĩa là kiểm tra điều gì?

Trong một modular monolith, tất cả module thường nằm trong cùng ứng dụng Java, dùng chung JVM và có thể dùng chung Spring ApplicationContext. Vì vậy, Java compiler **không tự hiểu** khái niệm “kiểu này là nội bộ của module khác”. Ngay cả khi một class có modifier `public`, kiến trúc vẫn có thể quy định class đó không phải API công khai.

Có ba lớp câu hỏi cần xem xét:

| Lớp kiểm tra | Câu hỏi | Công cụ hoặc cách thực hiện |
| --- | --- | --- |
| **Cấu trúc tĩnh** | Module nào phụ thuộc module nào? Có import kiểu nội bộ, phụ thuộc vòng hoặc trái quy tắc không? | `ApplicationModules.verify()`; kiểm tra mô hình module |
| **Ranh giới thực thi** | Một module có thể khởi động, thực hiện nghiệp vụ và phát event trong phạm vi mong muốn không? | `@ApplicationModuleTest`, test Spring theo module |
| **Hành vi liên module** | Event có được phát đúng, listener chạy lúc nào, rollback và retry hoạt động ra sao? | Kiểm thử tích hợp/sự kiện/transaction và quan sát runtime |

Ba lớp kiểm tra bổ sung cho nhau. **Bài test kiến trúc thành công không chứng minh một event đã được gửi, được xử lý hoặc được lưu bền**. Ngược lại, test nghiệp vụ chạy đúng trong một tình huống không chứng minh mã nguồn không có phụ thuộc vòng hoặc truy cập vào package nội bộ.

## 3. Mô hình ví dụ: đặt hàng, thông báo và thanh toán

Giả sử ứng dụng Spring Boot có class khởi động trong `com.example.shop` và sử dụng quy ước phát hiện module mặc định của Spring Modulith:

~~~text
com.example.shop
├── ShopApplication.java
├── ordering/                          # Module: ordering
│   ├── OrderFacade.java               # API công khai mặc định
│   ├── PlaceOrderRequest.java
│   ├── events/
│   │   ├── package-info.java          # Named interface: events
│   │   └── OrderPlaced.java
│   └── internal/
│       ├── OrderingService.java
│       ├── OrderRepository.java
│       └── OrderEntity.java
├── notification/                      # Module: notification
│   ├── package-info.java              # allowedDependencies
│   └── internal/
│       ├── OrderNotificationListener.java
│       └── EmailSender.java
└── payment/                           # Module: payment
    ├── PaymentFacade.java
    └── internal/
        ├── PaymentService.java
        └── PaymentRepository.java
~~~

Trong cách phát hiện mặc định, mỗi package con trực tiếp dưới package ứng dụng là một application module. **Root package của module** (ví dụ `ordering`) là API công khai mặc định. Các subpackage như `ordering.internal` và `ordering.events` là phần nội bộ **nếu không được công bố riêng**, chẳng hạn bằng named interface.

Ta mong muốn:

- `notification` nhận sự kiện `OrderPlaced` từ API đã công bố của `ordering`.
- `notification` không dùng `OrderingService`, `OrderRepository` hoặc `OrderEntity`.
- `payment` và `ordering` có quan hệ phụ thuộc rõ ràng; không tạo chu trình gọi qua lại tùy tiện.
- Để thêm một listener mới, không phải sửa `OrderingService` thành nơi gọi trực tiếp các listener.

~~~mermaid
flowchart LR
    subgraph ORDERING["ordering"]
      INTERNAL["internal: OrderingService"]
      EVENT["events: OrderPlaced"]
      INTERNAL -->|"publish"| EVENT
    end
    NOTIFY["notification: listener"] -->|"phụ thuộc vào event API"| EVENT
    PAYMENT["payment: facade"]
~~~

Trong sơ đồ, mũi tên từ `notification` đến `OrderPlaced` biểu thị **phụ thuộc kiểu Java** của listener vào hợp đồng event. Khi ứng dụng chạy, `ordering` mới là bên publish sự kiện. Hai chiều nhìn này khác nhau: **consumer phụ thuộc vào hợp đồng của publisher, còn publisher không cần phụ thuộc vào implementation của consumer**.

## 4. Các loại vi phạm cần phát hiện

### 4.1. Truy cập implementation của module khác

Ví dụ sau là dấu hiệu vượt ranh giới:

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.internal.OrderEntity;
import com.example.shop.ordering.internal.OrderRepository;

class NotificationDataLoader {

    private final OrderRepository repository;

    NotificationDataLoader(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

Nếu `OrderEntity` và `OrderRepository` có modifier `public`, Java compiler có thể cho phép các import này. Dù vậy, theo ranh giới module mặc định, `ordering.internal` là chi tiết triển khai của `ordering`; việc import từ `notification` không hợp lệ về mặt kiến trúc.

Hướng sửa là công bố một API phù hợp, chẳng hạn `OrderQuery` ở root `ordering`, hoặc chỉ gửi thông tin cần thiết trong `OrderPlaced`. Đừng biến cả repository thành public API chỉ để tránh lỗi xác minh.

### 4.2. Phụ thuộc vòng giữa các module

~~~mermaid
flowchart LR
    O["ordering"] --> P["payment"]
    P --> O
~~~

Nếu `ordering` gọi trực tiếp implementation của `payment`, còn `payment` lại gọi service/kiểu của `ordering`, hai module có thể hình thành vòng phụ thuộc. Một vòng nhỏ thường dẫn đến nhiều vòng phức tạp khi hệ thống phát triển.

Cách xử lý phụ thuộc nghiệp vụ:

- Làm rõ **module nào sở hữu quyết định** và API cần gọi đồng bộ.
- Di chuyển hợp đồng dùng chung về đúng module sở hữu hoặc tách một hợp đồng có chủ đích.
- Với phản ứng diễn ra sau một sự thật nghiệp vụ, cân nhắc công bố event để bên phát không cần biết bên nhận.

Không phải mọi phụ thuộc hai chiều ở runtime đều là import vòng trong mã nguồn; vấn đề cần đo là **đồ thị phụ thuộc module mà công cụ phân tích**.

### 4.3. Phụ thuộc vào API không được cho phép

Đôi khi một kiểu nằm ở public API nhưng consumer vẫn **không nên có quyền phụ thuộc**. Ví dụ, module `notification` chỉ cần `ordering::events`, không cần `OrderFacade` hoặc API của `payment`.

Khi đó hãy khai báo tập phụ thuộc hợp lệ tại root package của module tiêu thụ:

~~~java
// com/example/shop/notification/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "ordering::events"
)
package com.example.shop.notification;
~~~

Chỉ khai báo trên đây chưa đủ nếu `ordering.events` chưa được công bố thành named interface:

~~~java
// com/example/shop/ordering/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.ordering.events;
~~~

Khi đó `notification` được phép dùng hợp đồng trong interface `ordering::events`, nhưng một import tới `com.example.shop.ordering.OrderFacade` có thể vi phạm chính sách `allowedDependencies` dù `OrderFacade` thuộc root API. Dấu `::` ngăn cách tên module với tên named interface được công bố.

## 5. Kiểm tra cấu trúc bằng `ApplicationModules.verify()`

Spring Modulith cung cấp mô hình `ApplicationModules` để phát hiện các application module từ ứng dụng Spring Boot và kiểm tra ràng buộc kiến trúc. Một test ngắn có thể đóng vai trò **hàng rào bảo vệ** khi thêm class, sửa package hoặc thay đổi phụ thuộc.

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {

    @Test
    void shouldRespectModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ShopApplication` là class ứng dụng nằm tại root package `com.example.shop`. Bài test không cần tự liệt kê từng module; Spring Modulith tạo mô hình dựa trên quy ước phát hiện module đang áp dụng.

`verify()` kiểm tra các ràng buộc kiến trúc được Spring Modulith hỗ trợ, bao gồm:

1. **Không có chu trình phụ thuộc** giữa các application module trong mô hình.
2. **Không phụ thuộc vào kiểu không được công bố** của module khác, chẳng hạn class trong subpackage nội bộ.
3. **Tuân thủ các giới hạn phụ thuộc** đã khai báo qua `@ApplicationModule(allowedDependencies = ...)`.

Tùy dependency tích hợp và các quy tắc bổ sung đã được ứng dụng cấu hình, tập kiểm tra có thể được mở rộng. Cần xem kết quả cụ thể của phiên bản Spring Modulith đang dùng khi chẩn đoán vi phạm.

### 5.1. Minh họa một lần kiểm tra thất bại

Giả sử một developer đưa vào `notification.internal`:

~~~java
import com.example.shop.ordering.internal.OrderEntity;
~~~

Nếu Java compiler cho phép import, test `shouldRespectModuleBoundaries()` vẫn có thể thất bại do `OrderEntity` thuộc package nội bộ của `ordering`.

Quy trình xử lý:

1. Đọc thông báo vi phạm để xác định **module nguồn** (`notification`), **module đích** (`ordering`) và **kiểu bị truy cập** (`OrderEntity`).
2. Xác minh nghiệp vụ thực sự cần dữ liệu nào từ module đích.
3. Thay import nội bộ bằng API công khai, query API hoặc event contract thích hợp.
4. Chạy lại test kiến trúc để xác nhận không còn phụ thuộc sai.

Không nên sửa bằng cách đưa `OrderEntity` ra root package chỉ để test xanh. Đó là thao tác **mở rộng API công khai**, khiến module tiêu thụ bị gắn chặt với persistence model.

### 5.2. Kiểm tra ranh giới không cần khởi động toàn bộ hệ thống

Trong ví dụ trên, thao tác `ApplicationModules.of(...).verify()` dựa trên **mô hình mã nguồn và cấu trúc module**, không cần gửi email thật, kết nối message broker hoặc chạy các listener để chứng minh quan hệ phụ thuộc hợp lệ.

Đây là điểm mạnh để chạy sớm trong quy trình phát triển. Tuy nhiên, kiểm tra tĩnh có giới hạn: phụ thuộc được tạo động qua reflection, tên class từ chuỗi cấu hình, HTTP call hoặc message broker có thể không hiện diện như một import Java trực tiếp.

Vì thế, `verify()` nên được xem là **cổng kiểm tra cấu trúc**, sau đó bổ sung bài test hành vi cho các ranh giới quan trọng.

## 6. Kiểm thử module cô lập với `@ApplicationModuleTest`

Sau khi biết sơ đồ phụ thuộc hợp lệ, câu hỏi tiếp theo là: **Module có hoạt động đúng khi chỉ khởi tạo phần mà nó thực sự phụ thuộc không?**

Spring Modulith hỗ trợ annotation `@ApplicationModuleTest` để xây dựng ngữ cảnh kiểm thử tập trung vào module của lớp test. Ví dụ đặt test trong package `com.example.shop.ordering`:

~~~java
package com.example.shop.ordering;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrderingModuleIntegrationTest {

    @Test
    void moduleStartsWithItsExpectedComponents() {
        // Kiểm thử các bean/hành vi của module ordering.
        // Bổ sung assertion nghiệp vụ, không chỉ kiểm tra khởi động.
    }
}
~~~

Chú ý: annotation này giúp chọn phạm vi khởi tạo module, nhưng test ví dụ còn trống assertion nghiệp vụ. Trong dự án thật phải bổ sung lời gọi service, dữ liệu đầu vào và kết quả mong đợi để kiểm chứng tính đúng đắn.

Các chế độ bootstrap thường gặp:

| Chế độ | Phạm vi thường được khởi chạy | Tình huống sử dụng |
| --- | --- | --- |
| `STANDALONE` | Module đang kiểm thử | Muốn xác minh module ít phụ thuộc nhất; thay thế/cô lập tích hợp ngoài khi cần |
| `DIRECT_DEPENDENCIES` | Module đang kiểm thử và các module phụ thuộc trực tiếp | Cần tương tác với API module mà module hiện tại sử dụng trực tiếp |
| `ALL_DEPENDENCIES` | Module đang kiểm thử và phụ thuộc bắc cầu của nó | Cần kiểm thử tích hợp phạm vi rộng hơn |

Ví dụ khai báo rõ chế độ bootstrap:

~~~java
package com.example.shop.ordering;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)
class OrderingWithDependenciesTest {

    @Test
    void placesOrderThroughPublishedContracts() {
        // Chuẩn bị dữ liệu và gọi API module ordering.
    }
}
~~~

Chọn phạm vi hẹp nhất vẫn đủ cho tình huống cần kiểm chứng. Nếu một module chỉ có thể chạy test bằng cách khởi động **toàn bộ ứng dụng** và dùng nhiều bean nội bộ của module khác, đó là dấu hiệu đáng xem xét về thiết kế phụ thuộc. Tuy nhiên, thiếu bean do cấu hình hạ tầng hay test fixture chưa đầy đủ cũng có thể khiến test thất bại; cần đọc nguyên nhân trước khi kết luận ranh giới sai.

### 6.1. Vì sao test module và test kiến trúc khác nhau?

| Test | Điều chứng minh | Điều chưa chứng minh |
| --- | --- | --- |
| `ApplicationModules.verify()` | Quan hệ phụ thuộc giữa module phù hợp quy tắc tĩnh | Bean có chạy đúng; event có được phát và nhận |
| `@ApplicationModuleTest` | Module có thể khởi tạo và thực hiện hành vi theo phạm vi bootstrap đã chọn | Toàn bộ đồ thị module không có vi phạm nếu chưa chạy `verify()` |
| Integration test toàn ứng dụng | Một luồng nghiệp vụ có hoạt động theo runtime được cấu hình | Mọi module đều có API tối thiểu, không có phụ thuộc không mong muốn |

## 7. Kiểm tra ranh giới khi giao tiếp qua application events

Application events giúp bên phát thông báo “điều gì đã xảy ra”, còn mỗi module nhận tự quyết định phản ứng. Kiểm tra ranh giới cần nhìn vào **cả hợp đồng Java** và **hành vi lúc sự kiện được xử lý**.

### 7.1. Hợp đồng event phải thuộc API được công bố

~~~java
// com/example/shop/ordering/events/OrderPlaced.java
package com.example.shop.ordering.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

`OrderPlaced` là record Java bất biến về các trường; nó không cần kế thừa `ApplicationEvent`. Nhờ named interface `ordering::events`, các module như `notification` có thể import record này mà không truy cập nội bộ `ordering`.

**Không nên đặt `OrderEntity` hoặc `EntityManager` vào payload** để bên nhận truy vấn lazy relationship. Nếu cần dữ liệu, hãy thiết kế contract rõ ràng với ID và các thuộc tính nghiệp vụ thật sự cần truyền.

### 7.2. Publisher chỉ biết hợp đồng và hạ tầng phát event

~~~java
package com.example.shop.ordering.internal;

import com.example.shop.ordering.events.OrderPlaced;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderingService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderingService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(OrderDraft draft) {
        UUID orderId = orders.save(draft);

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                orderId,
                Instant.now(clock)
        ));

        return orderId;
    }
}
~~~

`OrderDraft`, `OrderRepository` và bean `Clock` là các thành phần minh họa của ứng dụng; ví dụ chỉ tập trung vào việc phát event. `OrderingService` không import lớp nào thuộc `notification`.

Điểm cần kiểm tra: **publish được gọi trong transaction**, nhưng transaction chưa chắc đã commit tại thời điểm publish. Vì vậy một listener chạy ngay lúc publish có thể nhìn thấy trạng thái chưa commit.

### 7.3. Listener chỉ dùng event contract

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    private final EmailSender emailSender;

    OrderNotificationListener(EmailSender emailSender) {
        this.emailSender = emailSender;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        emailSender.sendOrderConfirmation(event.orderId());
    }
}
~~~

`@ApplicationModuleListener` kết hợp các semantics listener sự kiện giao dịch của Spring Modulith, với xử lý **sau commit**, **bất đồng bộ** và **transaction riêng** theo cấu hình hạ tầng tương ứng. Khi kiểm thử cần chú ý môi trường thực thi bất đồng bộ và việc listener có cần ghi dữ liệu vào transaction mới.

Ranh giới đúng ở đây là: `notification` import `OrderPlaced` từ API được công bố; `ordering` không gọi trực tiếp `EmailSender`; mã gửi email vẫn nằm trong module `notification`.

## 8. Kiểm tra event được publish đúng

Một test hành vi cần xác minh **hợp đồng event**, không chỉ khẳng định method đặt hàng trả về ID.

Spring Modulith có `PublishedEvents` để kiểm tra các event được phát trong ngữ cảnh module test. Ví dụ giả sử ứng dụng cung cấp `OrderFacade` và `PlaceOrderRequest`:

~~~java
package com.example.shop.ordering;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.ordering.events.OrderPlaced;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrderingEventsTest {

    @Autowired
    OrderFacade orders;

    @Test
    void emitsOrderPlacedForSuccessfulOrder(PublishedEvents publishedEvents) {
        // Đầu vào hợp lệ được xây dựng theo model của dự án.
        PlaceOrderRequest request = validOrderRequest();

        UUID orderId = orders.placeOrder(request);

        assertThat(publishedEvents.ofType(OrderPlaced.class))
                .extracting(OrderPlaced::orderId)
                .contains(orderId);
    }

    private PlaceOrderRequest validOrderRequest() {
        // Triển khai test fixture của dự án, ví dụ khách hàng và sản phẩm hợp lệ.
        throw new UnsupportedOperationException("Provide project fixture");
    }
}
~~~

Đoạn `validOrderRequest()` là **điểm cần thay bằng test fixture thực** trước khi chạy, không phải hiện thực hoàn chỉnh của nghiệp vụ đặt hàng. Mục đích ví dụ là cho thấy cách `PublishedEvents` thu thập event và cách assertion kiểm tra `orderId`. Trong dự án thực, cần kiểm tra thêm `eventId` và thời điểm `occurredAt` nếu chúng là phần cam kết của contract.

**Assertion event đã publish chỉ chứng minh publisher phát đúng kiểu/dữ liệu trong test**, chưa chứng minh mọi listener đã thực thi xong hoặc có khả năng khôi phục sau lỗi.

### Một số tình huống cần phủ bằng test

| Tình huống | Kỳ vọng về event |
| --- | --- |
| Đơn hàng được tạo thành công | Có `OrderPlaced` cho đúng đơn hàng |
| Dữ liệu đặt hàng không hợp lệ | Không phát sự kiện “đơn hàng đã tạo” |
| Thao tác tạo đơn lặp do yêu cầu được retry | Tạo đúng số event theo quy tắc idempotency của thao tác đặt hàng |
| Thêm listener mới | Publisher vẫn không phụ thuộc tới module listener |
| Thay đổi implementation persistence | Contract `OrderPlaced` giữ nguyên trừ khi nghiệp vụ thật sự thay đổi |

## 9. Kiểm tra ranh giới transaction và thời điểm listener chạy

Đây là phần nhiều hệ thống event-driven dễ bỏ sót. Ví dụ:

~~~text
T0: ordering bắt đầu transaction
T1: ordering ghi OrderEntity
T2: ordering publish OrderPlaced
T3: transaction commit hoặc rollback
T4: listener sau commit mới có thể xử lý
~~~

`@EventListener` thông thường thường chạy **đồng bộ tại thời điểm publish** với cấu hình mặc định; việc gửi email từ đó có thể xảy ra ngay ở T2, trước khi transaction commit. Nếu T3 rollback, người dùng đã nhận email về một đơn hàng không tồn tại.

Với `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` hoặc `@ApplicationModuleListener` phù hợp, listener chỉ phản ứng với transaction đã commit thành công. Khi không có transaction tại thời điểm publish, `@TransactionalEventListener` mặc định không được gọi nếu không bật fallback.

Các test cần tách riêng:

1. **Commit thành công:** publisher phát event; listener sau commit có thể bắt đầu phản ứng; xác minh side effect thực tế (ví dụ bản ghi thông báo).
2. **Rollback:** ép lỗi sau publish nhưng trước commit; listener sau commit không được thực hiện side effect.
3. **Listener lỗi:** đơn hàng đã commit; lỗi listener được ghi nhận/xử lý theo chiến lược được cấu hình, không “rollback ngược” đơn hàng.
4. **Bất đồng bộ:** chờ điều kiện kết quả hoặc dùng công cụ kiểm thử sự kiện thích hợp; không giả định listener hoàn thành ngay khi `placeOrder()` trả về.

Ví dụ minh họa việc thiết kế test rollback:

~~~java
@Transactional
public void placeOrderThenFail(OrderDraft draft) {
    placeOrder(draft); // Phương thức giả định publish OrderPlaced.
    throw new IllegalStateException("Simulate rollback");
}
~~~

**Lưu ý về Spring proxy:** đoạn trên chỉ là mô tả nghiệp vụ; nếu `placeOrder()` nằm cùng class và được gọi nội bộ, self-invocation có thể bỏ qua advice `@Transactional` của phương thức được gọi. Khi triển khai test, hãy kích hoạt transaction qua **bean do Spring quản lý** và kiểm soát rõ commit/rollback; tránh kết luận từ ví dụ gọi nội bộ không đi qua proxy.

Ngoài ra, test tự gắn `@Transactional` rồi để test framework rollback ở cuối có thể khiến listener `AFTER_COMMIT` **không chạy**, dù code production đúng. Để kiểm thử after-commit thật sự, phải bảo đảm transaction được commit; có thể dùng transaction boundary rõ ràng (ví dụ `TransactionTemplate` hoặc TestTransaction khi thích hợp).

## 10. Xác minh độ tin cậy giao sự kiện

Kiểm tra ranh giới module cũng bao gồm việc xác định trách nhiệm **ai phát, ai nhận, ai lưu trạng thái, ai retry**. Đặc biệt, ứng dụng dùng `@ApplicationModuleListener` có thể cần xử lý trường hợp:

- Đơn hàng đã commit nhưng listener chưa chạy do ứng dụng dừng.
- Listener bắt đầu chạy nhưng gọi dịch vụ email thất bại.
- Listener hoàn thành tác vụ bên ngoài nhưng việc ghi nhận hoàn thành bị lỗi.
- Một sự kiện bị xử lý lại và gây tác vụ trùng.

**Event Publication Registry** của Spring Modulith có thể ghi nhận những publication cần xử lý, theo dõi trạng thái hoàn thành và hỗ trợ cơ chế khôi phục các publication chưa hoàn thành, khi được cấu hình cùng persistence cần thiết. **Chỉ gọi `publishEvent` không tự mang lại độ bền dữ liệu hoặc chiến lược retry**.

Để kiểm tra khả năng xử lý tin cậy, tạo các kịch bản riêng:

| Kịch bản | Bằng chứng nên thu thập |
| --- | --- |
| Listener xử lý thành công | Side effect hoàn tất và publication được đánh dấu thành công theo cơ chế registry |
| Listener ném exception | Trạng thái lỗi/chưa hoàn tất được theo dõi và có hướng phục hồi |
| Ứng dụng dừng sau commit | Publication cần xử lý không bị mất theo cơ chế đã cấu hình |
| Retry cùng event | Side effect không bị nhân đôi hoặc được khử trùng lặp theo khóa hợp lệ |
| Nhiều listener cùng nhận một event | Mỗi listener có trách nhiệm và trạng thái xử lý riêng theo cơ chế đang dùng |

Một event contract nên mang dữ liệu giúp truy vết:

~~~java
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

`eventId` có thể được dùng làm khóa idempotency của **lần xảy ra sự kiện**. `orderId` liên kết với nghiệp vụ, còn `occurredAt` là thời điểm sự kiện được ghi nhận. Khi retry cùng publication, giữ nguyên `eventId` để consumer có thể phát hiện việc xử lý trùng.

Quan sát nên gắn với event ID và correlation ID phù hợp, đồng thời theo dõi độ trễ publish-to-completion, số publication chưa hoàn tất, số lần retry và lỗi listener. Việc này giúp phát hiện sai lệch hành vi giữa các module dù test kiến trúc vẫn đạt.

## 11. Phân biệt lỗi ranh giới với lỗi vận hành

Không phải mọi lỗi xảy ra ở giao tiếp giữa module đều do ranh giới thiết kế sai. Để xử lý chính xác, cần phân loại:

| Dấu hiệu | Loại vấn đề | Kiểm tra ưu tiên |
| --- | --- | --- |
| `verify()` phát hiện import từ `ordering.internal` | Ranh giới API | Chuyển consumer sang API hợp lệ |
| `verify()` phát hiện chu trình module | Kiến trúc phụ thuộc | Thiết kế lại chiều sở hữu và hợp đồng |
| `@ApplicationModuleTest` thiếu bean của module liên quan | Bootstrap hoặc cấu hình test | Kiểm tra mode, mock/stub và dependency thật sự |
| Không có event sau khi đặt hàng | Logic publish | Kiểm tra nhánh nghiệp vụ, publisher và assertion `PublishedEvents` |
| Có event nhưng listener sau commit không chạy | Transaction/listener | Kiểm tra transaction đang hoạt động, commit, phase và async configuration |
| Listener chạy nhưng side effect thất bại | Hành vi hoặc tích hợp | Kiểm tra exception, retry, dữ liệu đầu vào và API đích |
| Gửi email trùng sau retry | Idempotency/delivery | Kiểm tra event ID, trạng thái đã xử lý, ràng buộc duy nhất |
| Broker không nhận được message | Externalization/transport | Kiểm tra adapter, cấu hình route, serialization và broker |

Điều này đặc biệt quan trọng khi chuyển từ application events **nội bộ JVM** sang integration events qua Kafka/RabbitMQ. Một module có thể hoàn toàn tuân thủ `verify()` nhưng adapter gửi message cấu hình sai, khiến hệ thống bên ngoài không nhận được dữ liệu. Đây là lỗi vận hành/tích hợp cần kiểm thử riêng.

## 12. Quy trình kiểm tra ranh giới khi thay đổi mã nguồn

Một quy trình gọn cho nhóm phát triển:

**Bước 1 — Mô hình hóa module.** Xác định root package, API mặc định, package nội bộ, named interface và chính sách `allowedDependencies`. Mỗi dependency xuyên module phải có lý do nghiệp vụ.

**Bước 2 — Viết test kiến trúc.** Thêm `ApplicationModules.of(Application.class).verify()` vào bộ test. Khi test thất bại, sửa hướng phụ thuộc trước khi bổ sung hành vi mới.

**Bước 3 — Kiểm thử module.** Dùng `@ApplicationModuleTest` để kiểm tra chức năng ở phạm vi nhỏ nhất phù hợp. Chuẩn bị fixture, bean/hạ tầng cần thiết và assertion có ý nghĩa.

**Bước 4 — Kiểm tra hợp đồng event.** Xác minh module phát sự kiện đúng loại, dữ liệu đúng ý nghĩa; listener chỉ phụ thuộc API đã được công bố.

**Bước 5 — Kiểm tra transaction và failure.** Có test cho commit, rollback, lỗi listener, retry và idempotency nếu những hành vi đó thuộc phạm vi hệ thống.

**Bước 6 — Chạy lại trong CI.** Thực thi test kiến trúc và các test thiết yếu trước khi hợp nhất thay đổi. Khi contract event hoặc named interface thay đổi, xem lại consumer đang phụ thuộc vào nó.

~~~mermaid
flowchart TD
    A["Thay đổi mã nguồn"] --> B["ApplicationModules.verify()"]
    B --> C{"Ranh giới hợp lệ?"}
    C -->|Không| D["Sửa API / hướng phụ thuộc"]
    D --> B
    C -->|Có| E["@ApplicationModuleTest"]
    E --> F{"Hành vi module đúng?"}
    F -->|Không| G["Sửa logic / cấu hình test"]
    G --> E
    F -->|Có| H["Test event, transaction, retry"]
    H --> I["Chạy CI / review"]
~~~

## 13. Bài thực hành: tìm và sửa một vi phạm ranh giới

**Bối cảnh:** Một ứng dụng bán hàng có `ordering`, `notification` và `payment`. `ordering` phát `OrderPlaced` sau khi lưu đơn; `notification` gửi email, `payment` xử lý thanh toán qua API riêng.

### Phần A — Xác minh cấu trúc

1. Tạo root package cho ba module, đặt implementation trong các subpackage `internal`.
2. Công bố `OrderPlaced` trong `ordering.events` bằng `@NamedInterface("events")`.
3. Giới hạn `notification` bằng `@ApplicationModule(allowedDependencies = "ordering::events")`.
4. Tạo `ModuleBoundaryTest` gọi `ApplicationModules.of(ShopApplication.class).verify()` và chạy test.
5. Cố tình thêm một import tới class `public` trong `ordering.internal` vào `notification`; quan sát vi phạm rồi thay bằng hợp đồng sự kiện.

### Phần B — Kiểm tra giao tiếp bằng event

1. Trong `ordering`, publish `OrderPlaced` sau khi lưu đơn hàng trong transaction.
2. Viết `@ApplicationModuleTest` cho `ordering` và sử dụng `PublishedEvents` để khẳng định event chứa đúng `orderId`.
3. Viết listener trong `notification` chỉ import `OrderPlaced`, không import repository từ `ordering`.
4. Tạo tình huống transaction đặt hàng rollback; giải thích vì sao listener sau commit không nên gửi email.
5. Tạo tình huống email thất bại sau commit; xác định kết quả của đơn hàng và cách theo dõi/retry publication theo cơ chế ứng dụng đã cấu hình.
6. Thử phát lại event có cùng `eventId` và xác minh cơ chế chống xử lý trùng trong module `notification`.

### Phần C — Báo cáo kết quả

Ghi lại ba bằng chứng:

- **Kết quả test kiến trúc:** đã phát hiện và xử lý vi phạm module nào.
- **Kết quả test hành vi:** có/không có `OrderPlaced` với dữ liệu đúng.
- **Kết quả test lỗi:** sau rollback, lỗi listener hoặc retry, trạng thái và side effect thực tế ra sao.

Một bài thực hành đạt yêu cầu khi cả ba lớp bằng chứng phù hợp với thiết kế. Việc test compile hoặc test khởi động thành công chỉ là một phần của quá trình xác minh.

## 14. Câu hỏi kiểm tra kiến thức

**Câu 1.** Vì sao một class `public` có thể vẫn bị coi là nội bộ của application module?

Vì `public` là quyền truy cập của Java, còn API công khai trong Spring Modulith được xác định bởi mô hình module, package gốc và các named interface được công bố. Class `public` trong subpackage nội bộ vẫn có thể vi phạm ranh giới khi module khác import.

**Câu 2.** `ApplicationModules.verify()` có kiểm tra rằng email được gửi thành công sau khi đơn hàng commit không?

Không. `verify()` kiểm tra cấu trúc/phụ thuộc kiến trúc. Hành vi gửi email cần test transaction, listener, tích hợp và hạ tầng thực thi.

**Câu 3.** Module `notification` được phép phụ thuộc `ordering::events`. Có thể import `ordering.internal.OrderRepository` để truy vấn nhanh không?

Không theo ranh giới đã thiết kế. Nên dùng hợp đồng sự kiện hoặc một API truy vấn được công bố có chủ đích, đồng thời điều chỉnh chính sách phụ thuộc nếu có lý do nghiệp vụ hợp lệ.

**Câu 4.** Vì sao listener `@TransactionalEventListener(AFTER_COMMIT)` có thể không chạy trong bài test được gắn `@Transactional`?

Vì transaction của test có thể bị rollback khi kết thúc, không có sự kiện **commit thành công** để kích hoạt listener sau commit. Cần tạo ranh giới transaction có commit thực tế khi kiểm thử hành vi này.

**Câu 5.** Test `PublishedEvents` thành công có chứng minh delivery exactly-once không?

Không. Nó kiểm tra việc phát event trong ngữ cảnh test. Delivery, publication persistence, retry, idempotency và side effect cần các kiểm tra độc lập.

## 15. Kết luận

**Kiểm tra ranh giới module là bảo vệ khả năng thay đổi độc lập của từng phần nghiệp vụ bằng bằng chứng có thể chạy lại.** Trong Spring Modulith, `ApplicationModules.verify()` giúp phát hiện phụ thuộc vượt API, trái chính sách hoặc tạo vòng; `@ApplicationModuleTest` giúp kiểm tra một module trong phạm vi có kiểm soát. Với giao tiếp bằng application events, cần xác minh thêm hợp đồng event, thời điểm commit, cách listener xử lý lỗi và chiến lược retry/idempotency.

Khi kết hợp kiểm tra cấu trúc, kiểm thử hành vi và quan sát runtime, hệ thống có thể sử dụng application events để giảm phụ thuộc mà vẫn xác định rõ trách nhiệm của publisher, consumer và hạ tầng giao sự kiện. Đây là nền tảng để nâng độ tin cậy của kiến trúc modular monolith khi số lượng module và consumer tăng lên.

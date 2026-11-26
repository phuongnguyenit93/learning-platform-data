# Tách các application module

Bài thực hành này chuyển một ứng dụng Spring Boot dạng monolith thành một **modular monolith** có các application module rõ ràng bằng Spring Modulith. Ứng dụng vẫn chạy trong một tiến trình và có thể dùng chung database, nhưng mỗi module sở hữu một phần nghiệp vụ, công bố API có kiểm soát và giao tiếp qua contract thay vì truy cập tùy ý vào package nội bộ của module khác.

Bối cảnh là một ứng dụng bán hàng đang có các chức năng đặt hàng, tra cứu sản phẩm, giữ tồn kho và gửi thông báo. Ban đầu, các lớp nằm trong những package chung như controller, service, repository và entity. Các service gọi trực tiếp repository hoặc entity của nhau, khiến thay đổi ở một chức năng có thể ảnh hưởng nhiều nơi.

Mục tiêu là tách các ranh giới nghiệp vụ thành application module **catalog**, **order**, **inventory** và **notification**; xác định phần API được phép sử dụng; chuyển giao tiếp phù hợp sang application events; sau đó dùng Spring Modulith để kiểm tra kiến trúc và kiểm thử từng module. Phạm vi vẫn là một ứng dụng Spring Modulith: tách module không đồng nghĩa phải tách thành microservice.

## 1. Kết quả cần đạt

Sau bài thực hành, cấu trúc ứng dụng cần đáp ứng các yêu cầu:

- Mỗi application module đại diện cho một năng lực nghiệp vụ có trách nhiệm rõ ràng.
- Domain model, repository và service nội bộ nằm trong module sở hữu chúng.
- Module khác chỉ truy cập API hoặc named interface được công bố.
- Không có dependency cycle giữa các application module.
- Giao tiếp bất đồng bộ dùng event contract có chủ sở hữu rõ ràng.
- Không chia sẻ entity JPA hoặc repository nội bộ giữa các module.
- Có kiểm thử xác minh cấu trúc module và hành vi quan trọng.
- Có thể tiếp tục phát triển từng module mà không cần hiểu toàn bộ codebase.

Một cấu trúc tốt không chỉ đổi tên package. Nó làm rõ ai sở hữu dữ liệu, ai quyết định quy tắc nghiệp vụ và module nào được phép phụ thuộc vào contract nào.

## 2. Hiểu application module trong Spring Modulith

Spring Modulith xem các package cấp cao bên dưới package gốc của ứng dụng là các application module. Ví dụ nếu lớp main nằm trong package gốc **com.acme.shop**, các package trực tiếp như **com.acme.shop.order**, **com.acme.shop.catalog** và **com.acme.shop.inventory** có thể trở thành các module.

Package con bên trong một module thường là implementation detail. Module khác không nên truy cập tùy ý vào các package con đó. Khi cần công bố một phần API, có thể đánh dấu package bằng **@NamedInterface** và khai báo dependency được phép.

Cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| Java package | Nhóm lớp và kiểm soát phạm vi truy cập ở cấp Java |
| Spring Modulith application module | Ranh giới nghiệp vụ và dependency được kiểm tra trong ứng dụng |
| Java module / microservice | Ranh giới triển khai hoặc runtime riêng, có thể có lifecycle và hạ tầng riêng |

Application module không bắt buộc phải có database riêng, process riêng hay deployment riêng. Một modular monolith vẫn có thể triển khai như một Spring Boot application duy nhất.

## 3. Khảo sát monolith trước khi di chuyển code

Trước khi đổi package, hãy lập bản đồ luồng nghiệp vụ hiện tại. Với ứng dụng bán hàng, có thể bắt đầu bằng các câu hỏi:

- Đơn hàng được tạo ở đâu và ai sở hữu trạng thái đơn?
- Giá sản phẩm và thông tin bán hàng do chức năng nào quản lý?
- Tồn kho được cập nhật ở đâu?
- Ai gửi email hoặc thông báo sau khi đơn được tạo?
- Repository và entity nào đang bị nhiều service sử dụng trực tiếp?
- Có service nào vừa xử lý nghiệp vụ vừa điều phối nhiều chức năng?

Một bảng dependency ban đầu giúp thấy coupling:

| Thành phần hiện tại | Đang sử dụng | Vấn đề thường gặp |
|---|---|---|
| OrderService | ProductRepository, InventoryRepository, OrderRepository | Đơn hàng biết chi tiết lưu trữ của module khác |
| InventoryService | OrderEntity, InventoryRepository | Kho phụ thuộc entity của đơn hàng |
| NotificationService | OrderRepository, CustomerRepository | Thông báo đọc trực tiếp dữ liệu nội bộ |
| ProductService | ProductRepository | Ranh giới chưa rõ giữa catalog và order |

Không di chuyển tất cả lớp cùng lúc. Trước hết xác định năng lực nghiệp vụ và dữ liệu mà mỗi năng lực sở hữu. Một lớp nên thuộc module quyết định quy tắc và trạng thái của nó, không phải module nào đang gọi lớp đó nhiều nhất.

## 4. Chọn ranh giới nghiệp vụ

Với bài toán này, chọn bốn application module:

| Module | Trách nhiệm | Dữ liệu sở hữu |
|---|---|---|
| catalog | Quản lý sản phẩm, giá và khả năng bán | Product, Price |
| order | Tạo đơn và quản lý vòng đời đơn | Order, OrderLine |
| inventory | Quản lý số lượng khả dụng và reservation | StockItem, Reservation |
| notification | Tạo và gửi thông báo | Notification, DeliveryAttempt |

Các module cần có lý do nghiệp vụ để thay đổi độc lập. Không tạo module chỉ vì một package đang có nhiều lớp. Ngược lại, không để một module quá lớn chỉ vì các chức năng dùng chung một database.

Một câu hỏi hữu ích để xác định ownership: “Nếu quy tắc của chức năng này thay đổi, nhóm nào chịu trách nhiệm và dữ liệu nào phải thay đổi cùng nó?” Câu trả lời thường chỉ ra module sở hữu aggregate và business rule.

## 5. Tổ chức package đích

Sau khi xác định module, tổ chức package theo năng lực nghiệp vụ thay vì theo loại kỹ thuật ở cấp toàn ứng dụng.

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
│   ├── package-info.java
│   ├── api
│   │   ├── package-info.java
│   │   ├── CatalogPricing.java
│   │   └── PriceQuote.java
│   └── internal
│       ├── domain
│       ├── persistence
│       └── service
├── order
│   ├── package-info.java
│   ├── api
│   ├── events
│   │   ├── package-info.java
│   │   └── OrderPlaced.java
│   └── internal
│       ├── domain
│       ├── persistence
│       └── service
├── inventory
│   ├── package-info.java
│   └── internal
│       ├── domain
│       ├── persistence
│       └── listener
└── notification
    ├── package-info.java
    └── internal
        ├── domain
        ├── persistence
        └── listener
~~~

Cấu trúc trên là một cách tổ chức tham khảo. Có thể dùng tên **application**, **domain**, **infrastructure** bên trong từng module nếu phù hợp với convention của dự án. Điều quan trọng là các package nội bộ vẫn nằm dưới package module sở hữu chúng.

Tránh tạo các package cấp gốc như **com.acme.shop.services** hoặc **com.acme.shop.repositories** chứa lớp của mọi nghiệp vụ. Cách tổ chức đó khiến module boundary khó nhìn thấy và dependency tiếp tục lan qua các lớp dùng chung.

## 6. Đánh dấu module và named interface

Có thể dùng **package-info.java** để đặt metadata cho application module.

Ví dụ module Catalog:

~~~java
@org.springframework.modulith.ApplicationModule(
    displayName = "Catalog"
)
package com.acme.shop.catalog;
~~~

Package API được công bố dưới tên **api**:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.catalog.api;
~~~

Module Order cần dùng API định giá của Catalog có thể khai báo dependency được phép:

~~~java
@org.springframework.modulith.ApplicationModule(
    displayName = "Order",
    allowedDependencies = "catalog::api"
)
package com.acme.shop.order;
~~~

Cú pháp **module::namedInterface** chỉ rõ Order phụ thuộc vào named interface **api** của module Catalog. Nếu module khác import package nội bộ của Catalog, kiểm tra kiến trúc có thể phát hiện dependency không được công bố.

Một package có thể được công bố như named interface khi thật sự là contract ổn định cho module khác. Không đánh dấu mọi package là API để làm cho kiểm tra kiến trúc pass; việc đó làm mất ý nghĩa của ranh giới.

## 7. Công bố API nhỏ cho truy vấn đồng bộ

Một module có thể cung cấp API đồng bộ khi caller cần kết quả ngay trong cùng use case. Ví dụ Order cần biết giá và trạng thái bán của sản phẩm trước khi tạo đơn.

API Catalog:

~~~java
package com.acme.shop.catalog.api;

public interface CatalogPricing {

    PriceQuote quote(String sku);
}
~~~

DTO trả về:

~~~java
package com.acme.shop.catalog.api;

import java.math.BigDecimal;

public record PriceQuote(
    String sku,
    BigDecimal unitPrice,
    String currency,
    boolean sellable
) {}
~~~

Implementation nằm trong package nội bộ của Catalog:

~~~java
package com.acme.shop.catalog.internal.service;

import com.acme.shop.catalog.api.CatalogPricing;
import com.acme.shop.catalog.api.PriceQuote;
import org.springframework.stereotype.Service;

@Service
class CatalogPricingService implements CatalogPricing {

    private final ProductRepository products;

    CatalogPricingService(ProductRepository products) {
        this.products = products;
    }

    @Override
    public PriceQuote quote(String sku) {
        Product product = products.findBySku(sku)
            .orElseThrow(() -> new ProductNotFoundException(sku));

        return new PriceQuote(
            product.getSku(),
            product.getCurrentPrice(),
            product.getCurrency(),
            product.isSellable()
        );
    }
}
~~~

Order chỉ biết **CatalogPricing** và **PriceQuote**. Nó không import **Product**, **ProductRepository** hoặc entity JPA của Catalog. DTO công bố cần chứa dữ liệu đủ cho use case nhưng không làm lộ cấu trúc persistence.

Nếu API chỉ được dùng trong một module, không cần tạo named interface công khai. Giữ API nhỏ giúp tránh biến mọi lớp thành contract lâu dài.

## 8. Chọn event cho giao tiếp không cần kết quả tức thời

Sau khi đơn được tạo, nhiều module có thể cần phản ứng: Inventory ghi nhận yêu cầu giữ hàng và Notification tạo thông báo xác nhận đã nhận đơn. Order không cần gọi trực tiếp service nội bộ của các module này.

Đặt event contract ở package được công bố:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
~~~

Event bất biến:

~~~java
package com.acme.shop.order.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
    UUID eventId,
    String orderId,
    String sku,
    int quantity,
    Instant occurredAt
) {}
~~~

Inventory và Notification có thể khai báo phụ thuộc vào **order::events** vì chúng cần đọc contract **OrderPlaced**. Dependency hướng từ consumer tới event contract của producer; Order không cần phụ thuộc ngược vào implementation của Inventory hoặc Notification.

Ví dụ metadata module Inventory:

~~~java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory",
    allowedDependencies = "order::events"
)
package com.acme.shop.inventory;
~~~

Notification có thể dùng cùng named interface:

~~~java
@org.springframework.modulith.ApplicationModule(
    displayName = "Notification",
    allowedDependencies = "order::events"
)
package com.acme.shop.notification;
~~~

Nếu quy trình cần phản hồi nhiều chiều hoặc có nhiều bước phối hợp, hãy cân nhắc một process manager/orchestration module hoặc một module contract được thiết kế rõ. Không tạo dependency vòng giữa Order và Inventory bằng cách để mỗi bên import event nội bộ của bên kia.

## 9. Phát event từ module Order

Application service của Order dùng API Catalog để xác thực giá, lưu đơn trong transaction và publish event mô tả sự kiện nghiệp vụ đã xảy ra.

~~~java
package com.acme.shop.order.internal.service;

import com.acme.shop.catalog.api.CatalogPricing;
import com.acme.shop.catalog.api.PriceQuote;
import com.acme.shop.order.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.util.UUID;

@Service
class PlaceOrderService {

    private final CatalogPricing catalogPricing;
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    PlaceOrderService(
            CatalogPricing catalogPricing,
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock) {
        this.catalogPricing = catalogPricing;
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public String place(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        PriceQuote quote = catalogPricing.quote(sku);
        if (!quote.sellable()) {
            throw new ProductNotSellableException(sku);
        }

        Order order = Order.create(
            sku,
            quantity,
            quote.unitPrice(),
            quote.currency()
        );

        orders.save(order);

        events.publishEvent(new OrderPlaced(
            UUID.randomUUID(),
            order.getId(),
            sku,
            quantity,
            clock.instant()
        ));

        return order.getId();
    }
}
~~~

Ví dụ dùng **ApplicationEventPublisher** để phát application event. Event được tạo từ dữ liệu đã được xác nhận trong use case; không gửi entity JPA hoặc repository qua event.

Vì event được publish bên trong transaction, listener cần có semantics phù hợp với transaction. Với listener dùng **@ApplicationModuleListener**, Spring Modulith hỗ trợ xử lý listener theo cơ chế module listener, thường được dùng cho công việc bất đồng bộ sau khi transaction phát event commit. Hãy kiểm tra cấu hình và phiên bản đang dùng để hiểu chính xác executor, transaction phase và xử lý lỗi.

## 10. Tiếp nhận event ở Inventory và Notification

Inventory nhận **OrderPlaced** và gọi service nội bộ để tạo reservation. Listener chỉ làm nhiệm vụ tiếp nhận contract rồi chuyển cho nghiệp vụ của module.

~~~java
package com.acme.shop.inventory.internal.listener;

import com.acme.shop.order.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedInventoryListener {

    private final InventoryReservationService reservations;

    OrderPlacedInventoryListener(
            InventoryReservationService reservations) {
        this.reservations = reservations;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        reservations.reserve(
            event.orderId(),
            event.sku(),
            event.quantity(),
            event.eventId()
        );
    }
}
~~~

Notification cũng có thể nhận cùng event để tạo thông báo phù hợp:

~~~java
package com.acme.shop.notification.internal.listener;

import com.acme.shop.order.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedNotificationListener {

    private final NotificationService notifications;

    OrderPlacedNotificationListener(
            NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        notifications.orderReceived(
            event.orderId(),
            event.eventId()
        );
    }
}
~~~

Hai listener phụ thuộc vào contract event công bố bởi Order, không phụ thuộc implementation của nhau. Mỗi module tự quyết định cách lưu trạng thái, retry và idempotency cho side effect thuộc quyền sở hữu của mình.

Trong production, event có thể được giao lại khi listener lỗi hoặc publication được phục hồi. Inventory và Notification cần xử lý duplicate an toàn bằng event ID/business key và unique constraint phù hợp.

## 11. Phân biệt gọi API và publish event

Không phải mọi lời gọi liên module đều nên trở thành event. Chọn cơ chế dựa trên yêu cầu nghiệp vụ:

| Nhu cầu | Cách giao tiếp phù hợp |
|---|---|
| Cần giá sản phẩm ngay để tạo đơn | Gọi Catalog API đồng bộ |
| Nhiều module phản ứng sau khi đơn được tạo | Publish OrderPlaced |
| Cần truy vấn trạng thái reservation ngay trong request | API truy vấn rõ ràng hoặc use case đồng bộ |
| Một quy trình có nhiều bước, chờ nhiều kết quả | Process manager/orchestration |
| Cần thông báo cho hệ thống ngoài tiến trình | Externalization adapter hoặc broker integration |

Event giúp giảm phụ thuộc thời gian chạy nhưng làm luồng nghiệp vụ bất đồng bộ và khó quan sát hơn. Không dùng event chỉ để che giấu một lời gọi cần kết quả ngay lập tức.

Ngược lại, không gọi trực tiếp implementation nội bộ chỉ vì việc đó dễ viết hơn. Hãy dùng API được công bố nếu cần giao tiếp đồng bộ.

## 12. Giữ domain và persistence bên trong module

Mỗi module nên sở hữu entity, repository và business rule của nó. Ví dụ **OrderRepository** nằm trong **order.internal.persistence**; **InventoryRepository** nằm trong **inventory.internal.persistence**.

Không để module Order gọi:

~~~java
inventoryRepository.decreaseAvailableStock(sku, quantity);
~~~

vì cách này khiến Order biết chi tiết lưu trữ và transaction của Inventory. Thay vào đó, Order phát event **OrderPlaced**; Inventory tự quyết định cách giữ hàng.

Cũng không trả **Product** entity từ Catalog API. Entity JPA có lifecycle, lazy association và cấu trúc persistence riêng. API nên trả DTO/record chỉ chứa dữ liệu contract cần thiết.

Nếu hai module thực sự cần dùng một khái niệm chung, hãy đánh giá ownership trước. Có thể đó là một value object thuần, một API contract hoặc một module nền tảng nhỏ. Tránh tạo **common** package chứa entity, repository và service của mọi nghiệp vụ.

## 13. Di chuyển code theo từng bước nhỏ

Không cần tái cấu trúc toàn bộ monolith trong một lần. Một lộ trình có thể thực hiện theo từng lát cắt:

1. Chọn một năng lực nghiệp vụ có ranh giới tương đối rõ, ví dụ Catalog.
2. Di chuyển domain, repository và service liên quan vào package **catalog**.
3. Tạo API nhỏ cho các module cần gọi Catalog.
4. Thay import trực tiếp entity/repository bằng API DTO.
5. Chạy kiểm tra module dependency và sửa các vi phạm.
6. Chuyển sang module Order, sau đó Inventory và Notification.
7. Thay các lời gọi thông báo trực tiếp bằng event ở nơi phù hợp.
8. Thêm module tests và integration tests cho luồng quan trọng.
9. Xóa package cũ và lớp facade tạm sau khi không còn caller.

Trong giai đoạn di chuyển, có thể giữ adapter hoặc facade tạm để tránh thay đổi quá nhiều caller cùng lúc. Tuy nhiên, facade phải có kế hoạch loại bỏ và không trở thành một lớp trung gian vĩnh viễn che giấu dependency cũ.

Sau mỗi lát cắt, build và test của dự án cần được chạy trong quy trình phát triển thông thường. Việc di chuyển package mà không thay đổi hành vi giúp dễ xác định lỗi kiến trúc so với lỗi nghiệp vụ.

## 14. Kiểm tra dependency bằng Spring Modulith

Spring Modulith cung cấp API **ApplicationModules** để phát hiện module và xác minh quy tắc kiến trúc. Có thể thêm một test ở cấp ứng dụng:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleStructureTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test này giúp phát hiện dependency vi phạm ranh giới, truy cập package nội bộ không được phép và các vấn đề cấu trúc mà Spring Modulith có thể xác minh.

Khi test fail, hãy xem module nào phụ thuộc module nào và lớp nào tạo dependency. Các hướng xử lý thường là:

- Chuyển lớp về đúng module sở hữu nghiệp vụ.
- Công bố một API/named interface nhỏ nếu dependency là hợp lệ.
- Dùng application event nếu caller chỉ cần thông báo một sự kiện đã xảy ra.
- Đưa orchestration vào một module điều phối nếu đang có dependency vòng.
- Tách contract ổn định khỏi implementation nội bộ.

Không thêm named interface cho toàn bộ package chỉ để làm test pass. Mục tiêu là giữ dependency có chủ đích, không phải loại bỏ cảnh báo bằng cách công bố tất cả implementation.

## 15. Kiểm thử từng application module

Ngoài kiểm tra dependency, cần kiểm thử hành vi trong phạm vi module. Spring Modulith cung cấp **@ApplicationModuleTest** để khởi tạo module đang kiểm thử cùng các thành phần cần thiết theo cấu hình test.

Ví dụ kiểm thử module Order:

~~~java
package com.acme.shop.order;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderModuleTests {

    @Autowired
    PlaceOrderService placeOrderService;

    @Test
    void createsOrderAndPublishesOrderPlaced() {
        // Arrange: chuẩn bị Catalog API và repository test.
        // Act: gọi use case đặt hàng.
        // Assert: đơn được lưu và event có contract đúng.
    }
}
~~~

Phần Arrange/Act/Assert cần được hoàn thiện theo test fixture và database của dự án. Khi kiểm thử event listener bất đồng bộ, dùng cơ chế chờ event/state có timeout phù hợp thay vì **Thread.sleep()**.

Một bộ test hữu ích gồm:

- Catalog API trả quote đúng và từ chối sản phẩm không bán.
- Order tạo đơn và publish event đúng dữ liệu.
- Inventory nhận event và giữ đúng số lượng.
- Notification nhận event và tạo yêu cầu thông báo.
- Listener không tạo side effect trùng khi cùng event được giao lại.
- Event không được xử lý theo after-commit nếu transaction phát event rollback, khi đó là semantics đã chọn.
- Module không truy cập package nội bộ của module khác.

## 16. Kiểm tra sơ đồ module và tài liệu kiến trúc

Khi module đã được nhận diện, có thể dùng Spring Modulith để tạo tài liệu/sơ đồ kiến trúc. Sơ đồ giúp review dependency và giải thích ranh giới cho người mới tham gia dự án.

Một sơ đồ dependency mong đợi cho ví dụ:

~~~mermaid
flowchart LR
    O["Order"] -->|"catalog::api"| C["Catalog"]
    I["Inventory"] -->|"order::events"| O
    N["Notification"] -->|"order::events"| O
~~~

Mũi tên thể hiện dependency compile-time tới API hoặc event contract. Khi chạy, Order publish event và Inventory/Notification phản ứng; điều đó không có nghĩa Order gọi trực tiếp implementation của chúng.

Sơ đồ cũng giúp phát hiện dependency vòng. Nếu thấy **Order** phụ thuộc **Inventory** và **Inventory** phụ thuộc **Order**, hãy xác định contract nào tạo vòng. Có thể chuyển một phần điều phối sang module thứ ba hoặc thay một chiều giao tiếp bằng event contract có ownership rõ.

## 17. Những lỗi thường gặp khi tách module

**Chỉ đổi tên package.** Nếu service vẫn truy cập repository và entity nội bộ của module khác, coupling chưa được xử lý. Hãy xác định API và ownership.

**Tách theo technical layer.** Các package controller/service/repository toàn cục không thể hiện năng lực nghiệp vụ. Hãy gom code theo module sở hữu use case và dữ liệu.

**Công bố toàn bộ package nội bộ.** Named interface trở thành lối thoát để dependency cũ tiếp tục tồn tại. Chỉ công bố contract cần thiết.

**Chia sẻ JPA entity.** Module nhận biết cấu trúc persistence của module khác và có thể làm thay đổi schema ngoài dự kiến. Hãy dùng DTO hoặc event record.

**Tạo dependency vòng qua event.** Nếu hai module import event contract của nhau, đồ thị dependency vẫn có thể bị vòng. Hãy dùng một hướng event hoặc module điều phối/contract phù hợp.

**Dùng event cho truy vấn cần kết quả ngay.** Caller phải chờ và quản lý trạng thái phức tạp không cần thiết. Dùng API đồng bộ cho truy vấn có contract rõ.

**Dùng API đồng bộ cho mọi thông báo.** Producer bị phụ thuộc vào consumer và có thể phải biết tất cả module nhận. Event phù hợp khi nhiều module phản ứng độc lập.

**Giả định application module là microservice.** Application module vẫn có thể dùng chung tiến trình và database. Chỉ tách deployment khi có yêu cầu và thiết kế vận hành riêng.

**Bỏ qua duplicate và transaction.** Listener có thể được gọi lại. Hãy thiết kế idempotency và kiểm thử failure path.

**Chỉ chạy test nghiệp vụ, không kiểm tra kiến trúc.** Test có thể pass dù module phụ thuộc package nội bộ. Hãy giữ **ApplicationModules.verify()** trong test suite.

## 18. Bài tập mở rộng

Sau khi hoàn thành bốn module cơ bản, có thể mở rộng dự án theo các yêu cầu:

1. Thêm module **payment** sở hữu payment transaction và phát PaymentAuthorized hoặc PaymentDeclined.
2. Tạo module điều phối **checkout** hoặc **order-fulfillment** để quản lý luồng giữ hàng và thanh toán nhiều bước mà không tạo dependency vòng.
3. Thêm inbox table để Inventory và Notification xử lý OrderPlaced idempotent.
4. Tạo integration test xác minh event chỉ được xử lý sau khi transaction Order commit.
5. Externalize một event ra broker và kiểm tra serialization, retry, dead-letter.
6. Thêm metric cho handler duration, event age và publication incomplete.
7. Tạo tài liệu dependency diagram và review các named interface đã công bố.
8. Viết một ADR giải thích vì sao một giao tiếp dùng API đồng bộ và giao tiếp khác dùng event.

Với mỗi thay đổi, ghi rõ module sở hữu dữ liệu, dependency được thêm, contract công bố và cách kiểm thử. Không tạo module mới chỉ để chia nhỏ package; phải có ranh giới nghiệp vụ đủ rõ.

## 19. Tiêu chí nghiệm thu dự án

Dự án được xem là hoàn thành về mặt kiến trúc khi đáp ứng các tiêu chí sau:

| Tiêu chí | Bằng chứng |
|---|---|
| Module được nhận diện rõ | Spring Modulith phát hiện Catalog, Order, Inventory, Notification |
| Ownership rõ | Entity và repository nằm trong module sở hữu |
| API được kiểm soát | Order chỉ dùng catalog::api |
| Event contract rõ | OrderPlaced nằm trong named interface được công bố |
| Dependency có hướng | Inventory và Notification phụ thuộc event contract của Order |
| Không có dependency vòng | ApplicationModules.verify() pass |
| Không truy cập implementation | Module không import repository/entity nội bộ của module khác |
| Event behavior được kiểm thử | Order publish; Inventory/Notification xử lý đúng |
| Duplicate an toàn | Listener có idempotency phù hợp với side effect |
| Tài liệu dễ review | Có package map và sơ đồ dependency |
| Migration có kiểm soát | Các package cũ và facade tạm được loại bỏ theo từng bước |

Có thể dùng checklist sau khi review pull request:

- [ ] Mỗi module có một trách nhiệm nghiệp vụ dễ mô tả.
- [ ] Package nội bộ không được import từ module khác.
- [ ] Named interface chỉ chứa contract ổn định.
- [ ] DTO/event không làm lộ entity persistence.
- [ ] Không có dependency cycle.
- [ ] Giao tiếp đồng bộ và event được chọn theo nhu cầu use case.
- [ ] Listener có transaction và idempotency phù hợp.
- [ ] Architecture test và module tests được duy trì.

## Kết luận

Tách các application module là quá trình xác định ownership và kiểm soát dependency trong một ứng dụng Spring Boot. Bắt đầu bằng việc gom code theo năng lực nghiệp vụ, giữ domain và persistence bên trong module, rồi công bố API hoặc event contract đủ nhỏ cho các module khác sử dụng.

Spring Modulith giúp biến các ranh giới đó thành quy tắc có thể kiểm tra bằng **ApplicationModules.verify()** và **@ApplicationModuleTest**. Kết hợp package structure rõ ràng, named interface, application events, idempotency và kiểm thử theo module giúp modular monolith dễ thay đổi, dễ review và có nền tảng tốt nếu sau này cần tách một module thành service độc lập.


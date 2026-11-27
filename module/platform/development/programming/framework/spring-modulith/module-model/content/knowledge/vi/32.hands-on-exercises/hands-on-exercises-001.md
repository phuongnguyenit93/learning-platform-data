# Tạo ứng dụng Spring Boot có ba module chức năng

Trong bài thực hành này, bạn sẽ xây dựng một ứng dụng bán hàng nhỏ bằng Spring Boot và Spring Modulith. Ứng dụng có ba application module: catalog quản lý sản phẩm, orders tiếp nhận đơn hàng và inventory cập nhật tồn kho khi nhận sự kiện đặt hàng.

Mục tiêu là tổ chức ba capability thành các module có ranh giới rõ ràng ngay trong một ứng dụng Spring Boot. Module orders sử dụng API được catalog công khai; module inventory lắng nghe event do orders phát ra. Spring Modulith sẽ kiểm tra rằng các module chỉ phụ thuộc vào API được phép và dependency graph không có chu trình.

Sau khi hoàn thành, bạn có thể:

- Tạo project Spring Boot và thêm Spring Modulith BOM, starter phù hợp.
- Tổ chức package theo ba capability catalog, orders và inventory.
- Công khai Catalog API bằng named interface.
- Công khai OrderPlaced event như một hợp đồng tích hợp.
- Khai báo allowedDependencies để giới hạn module được phép sử dụng.
- Kết nối các module bằng Spring bean và application event.
- Kiểm tra dependency graph bằng ApplicationModules.verify().
- Viết architecture test, module integration test và end-to-end test.

## 1. Bài toán và kết quả mong đợi

Ứng dụng mô phỏng một luồng đặt hàng đơn giản:

1. Khách hàng gửi yêu cầu đặt một sản phẩm.
2. Module orders tra cứu sản phẩm qua API của catalog.
3. Orders tạo mã đơn, tính tổng tiền và phát event OrderPlaced.
4. Module inventory lắng nghe event, giữ số lượng hàng tương ứng và ghi nhận reservation.
5. API trả về thông tin đơn hàng; API inventory cho biết số lượng còn lại.

Ví dụ, catalog có sản phẩm book-1 với giá 19.90 và inventory ban đầu có 20 sản phẩm. Khi đặt 2 sản phẩm:

| Kết quả | Giá trị mong đợi |
|---|---:|
| Product ID | book-1 |
| Quantity | 2 |
| Unit price | 19.90 |
| Order total | 39.80 |
| Stock trước khi đặt | 20 |
| Stock sau khi xử lý event | 18 |

Trong bài này, dữ liệu sản phẩm và tồn kho được lưu trong bộ nhớ để tập trung vào module model và giao tiếp giữa các module. Khi ứng dụng khởi động lại, dữ liệu demo trở về giá trị ban đầu.

## 2. Thiết kế ba module và hướng phụ thuộc

Mỗi module sở hữu một capability:

| Module | Trách nhiệm | Hợp đồng công khai |
|---|---|---|
| catalog | Tra cứu thông tin sản phẩm và giá | Named interface catalog::api |
| orders | Tạo đơn hàng và phát sự kiện OrderPlaced | API package gốc và named interface orders::events |
| inventory | Theo dõi số lượng còn lại và giữ hàng khi nhận OrderPlaced | API package gốc; không có module tiêu thụ trong bài này |

Hướng phụ thuộc ở cấp code:

~~~mermaid
flowchart LR
    inventory["inventory"] -->|"OrderPlaced event type"| orders["orders"]
    orders -->|"ProductCatalog API"| catalog["catalog"]
~~~

Mũi tên thể hiện module nguồn phụ thuộc module đích. Vì vậy:

- orders phụ thuộc catalog vì OrderService tham chiếu ProductCatalog.
- inventory phụ thuộc orders vì listener tham chiếu kiểu OrderPlaced.
- catalog không phụ thuộc orders hoặc inventory.

Luồng nghiệp vụ lúc chạy có hướng phát event ngược với một cạnh dependency: orders phát OrderPlaced, inventory nhận event. Tuy nhiên, để biên dịch listener, inventory phải tham chiếu kiểu event do orders sở hữu, nên dependency graph có cạnh inventory → orders. Đây là điểm cần phân biệt khi đọc module graph.

Đồ thị cuối cùng là DAG: inventory → orders → catalog. Không có đường phụ thuộc quay lại module xuất phát.

## 3. Tạo project và khai báo dependency

Ví dụ dùng Java 17, Spring Boot 4.0.10 và Spring Modulith 2.2.0. Hãy đối chiếu phiên bản Spring Boot với compatibility matrix của Spring Modulith nếu dự án của bạn đang dùng một baseline khác.

Tạo project Maven với cấu trúc ban đầu:

~~~text
shop-modulith/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   └── resources/
    └── test/
        └── java/
~~~

Khai báo BOM để quản lý phiên bản đồng bộ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.10</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>shop-modulith</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <spring-modulith.version>2.2.0</spring-modulith.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.modulith</groupId>
                <artifactId>spring-modulith-bom</artifactId>
                <version>${spring-modulith.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-starter-core</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các dependency có vai trò:

- spring-boot-starter-webmvc cung cấp Spring MVC và embedded web server cho REST API.
- spring-modulith-starter-core cung cấp module model, annotation và runtime support cơ bản.
- spring-modulith-starter-test cung cấp @ApplicationModuleTest, Scenario và các tiện ích kiểm thử module.
- spring-boot-starter-test cung cấp JUnit, Mockito, AssertJ và Spring Boot test support.

Không cần thêm database hoặc event publication registry cho phiên bản bài tập này. Event được gửi và xử lý đồng bộ trong cùng process bằng Spring ApplicationEventPublisher và @EventListener.

## 4. Tạo lớp Spring Boot application

Đặt lớp chính tại package gốc com.acme.shop. Các package module phải là package con trực tiếp để detection strategy mặc định direct-subpackages nhận diện được.

Tạo src/main/java/com/acme/shop/ShopApplication.java:

~~~java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Spring Modulith dùng package chứa ShopApplication làm root. Ba package catalog, orders và inventory nằm ngay dưới root nên được phát hiện thành ba application module theo mặc định.

## 5. Xây dựng module catalog

Catalog sở hữu thông tin sản phẩm. Module khác chỉ cần biết cách tra cứu sản phẩm và cấu trúc dữ liệu trả về; chúng không cần biết catalog lưu trữ dữ liệu như thế nào.

Tổ chức package:

~~~text
com.acme.shop.catalog
├── api
│   ├── package-info.java
│   ├── ProductCatalog.java
│   └── ProductDetails.java
└── internal
    └── InMemoryProductCatalog.java
~~~

Đánh dấu package api là named interface:

Tạo src/main/java/com/acme/shop/catalog/api/package-info.java:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.catalog.api;
~~~

Định nghĩa kiểu dữ liệu sản phẩm tại ProductDetails.java:

~~~java
package com.acme.shop.catalog.api;

import java.math.BigDecimal;

public record ProductDetails(
        String id,
        String name,
        BigDecimal unitPrice
) {
}
~~~

Định nghĩa hợp đồng tra cứu tại ProductCatalog.java:

~~~java
package com.acme.shop.catalog.api;

import java.util.Optional;

public interface ProductCatalog {

    Optional<ProductDetails> findById(String productId);
}
~~~

Tạo implementation trong package internal:

~~~java
package com.acme.shop.catalog.internal;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.catalog.api.ProductDetails;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.util.Map;
import java.util.Optional;

@Component
public class InMemoryProductCatalog implements ProductCatalog {

    private final Map<String, ProductDetails> products = Map.of(
            "book-1",
            new ProductDetails(
                    "book-1",
                    "Spring Modulith Workbook",
                    new BigDecimal("19.90")
            )
    );

    @Override
    public Optional<ProductDetails> findById(String productId) {
        return Optional.ofNullable(products.get(productId));
    }
}
~~~

Implementation được khai báo public để Spring có thể khởi tạo bean, nhưng vẫn nằm trong package internal. Package này không phải named interface nên module khác không được tham chiếu type triển khai. Orders chỉ được phụ thuộc vào ProductCatalog và ProductDetails qua catalog::api; module orders không cần import InMemoryProductCatalog.

## 6. Xây dựng module orders

Orders tiếp nhận yêu cầu đặt hàng, tra cứu sản phẩm qua Catalog API, tạo mã đơn và phát event. Module này có hai điểm tích hợp quan trọng:

- Dependency đi ra được giới hạn vào catalog::api bằng allowedDependencies.
- Event OrderPlaced được công khai cho module inventory qua named interface events.

Tổ chức package:

~~~text
com.acme.shop.orders
├── package-info.java
├── OrderService.java
├── OrderConfirmation.java
├── events
│   ├── package-info.java
│   └── OrderPlaced.java
└── web
    ├── OrderController.java
    └── PlaceOrderRequest.java
~~~

Khai báo module chỉ được phụ thuộc catalog::api trong src/main/java/com/acme/shop/orders/package-info.java:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "catalog::api"
)
package com.acme.shop.orders;
~~~

Định nghĩa event contract trong src/main/java/com/acme/shop/orders/events/package-info.java:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Tạo event OrderPlaced.java:

~~~java
package com.acme.shop.orders.events;

public record OrderPlaced(
        String orderId,
        String productId,
        int quantity
) {
}
~~~

Tạo kết quả đặt hàng tại OrderConfirmation.java:

~~~java
package com.acme.shop.orders;

import java.math.BigDecimal;

public record OrderConfirmation(
        String orderId,
        String productId,
        String productName,
        int quantity,
        BigDecimal total
) {
}
~~~

Tạo OrderService.java:

~~~java
package com.acme.shop.orders;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.catalog.api.ProductDetails;
import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.UUID;

@Service
public class OrderService {

    private final ProductCatalog catalog;
    private final ApplicationEventPublisher events;

    public OrderService(
            ProductCatalog catalog,
            ApplicationEventPublisher events
    ) {
        this.catalog = catalog;
        this.events = events;
    }

    public OrderConfirmation placeOrder(String productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        ProductDetails product = catalog.findById(productId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown product: " + productId
                ));

        String orderId = UUID.randomUUID().toString();

        events.publishEvent(new OrderPlaced(
                orderId,
                product.id(),
                quantity
        ));

        BigDecimal total = product.unitPrice()
                .multiply(BigDecimal.valueOf(quantity));

        return new OrderConfirmation(
                orderId,
                product.id(),
                product.name(),
                quantity,
                total
        );
    }
}
~~~

OrderService chỉ phụ thuộc vào interface ProductCatalog. Spring sẽ inject implementation InMemoryProductCatalog trong runtime. OrderService không biết class triển khai đó nằm ở package nào.

Phát event sau khi đã xác định được sản phẩm và tạo mã đơn. Event mang dữ liệu cần thiết cho inventory; listener không cần gọi ngược vào OrderService để lấy thông tin đơn.

Tạo request DTO tại PlaceOrderRequest.java:

~~~java
package com.acme.shop.orders.web;

public record PlaceOrderRequest(
        String productId,
        int quantity
) {
}
~~~

Tạo REST controller tại OrderController.java:

~~~java
package com.acme.shop.orders.web;

import com.acme.shop.orders.OrderConfirmation;
import com.acme.shop.orders.OrderService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @PostMapping
    public OrderConfirmation place(@RequestBody PlaceOrderRequest request) {
        return orders.placeOrder(request.productId(), request.quantity());
    }
}
~~~

Controller nằm trong package con web của module orders. Đây là implementation nội bộ của module, không phải named interface dành cho module khác.

## 7. Xây dựng module inventory

Inventory sở hữu số lượng tồn kho và reservation. Module này không gọi OrderService. Nó chỉ lắng nghe OrderPlaced event được orders công khai.

Tổ chức package:

~~~text
com.acme.shop.inventory
├── package-info.java
├── InventoryService.java
├── InventoryReservation.java
├── InventoryStatus.java
├── OrderPlacedListener.java
└── web
    └── InventoryController.java
~~~

Giới hạn dependency của inventory vào named interface orders::events trong src/main/java/com/acme/shop/inventory/package-info.java:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.acme.shop.inventory;
~~~

Tạo InventoryReservation.java:

~~~java
package com.acme.shop.inventory;

public record InventoryReservation(
        String orderId,
        String productId,
        int quantity
) {
}
~~~

Tạo InventoryStatus.java:

~~~java
package com.acme.shop.inventory;

public record InventoryStatus(
        String productId,
        int availableQuantity
) {
}
~~~

Tạo InventoryService.java:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class InventoryService {

    private final Map<String, Integer> available = new ConcurrentHashMap<>(
            Map.of("book-1", 20)
    );

    private final Map<String, InventoryReservation> reservations =
            new ConcurrentHashMap<>();

    public void reserve(OrderPlaced event) {
        available.compute(event.productId(), (productId, current) -> {
            if (current == null) {
                throw new IllegalArgumentException(
                        "Unknown inventory item: " + productId
                );
            }

            if (current < event.quantity()) {
                throw new IllegalStateException("Insufficient stock");
            }

            return current - event.quantity();
        });

        reservations.put(
                event.orderId(),
                new InventoryReservation(
                        event.orderId(),
                        event.productId(),
                        event.quantity()
                )
        );
    }

    public Optional<InventoryReservation> findReservation(String orderId) {
        return Optional.ofNullable(reservations.get(orderId));
    }

    public InventoryStatus status(String productId) {
        return new InventoryStatus(
                productId,
                available.getOrDefault(productId, 0)
        );
    }
}
~~~

Tạo listener tại OrderPlacedListener.java:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedListener {

    private final InventoryService inventory;

    OrderPlacedListener(InventoryService inventory) {
        this.inventory = inventory;
    }

    @EventListener
    public void on(OrderPlaced event) {
        inventory.reserve(event);
    }
}
~~~

Listener chỉ tham chiếu OrderPlaced, không tham chiếu OrderService, OrderController hoặc repository nội bộ của orders. Điều đó giữ hợp đồng giữa hai module ở mức event.

InventoryService dùng Map để giữ ví dụ ngắn gọn. Implementation này chưa xử lý idempotency cho event bị gửi lặp, chưa lưu dữ liệu bền vững và chưa phối hợp transaction giữa order với inventory. Hãy xem đây là mô hình thực hành về ranh giới module; các bảo đảm vận hành cần được bổ sung khi phát triển ứng dụng thực tế.

Tạo REST controller tại InventoryController.java:

~~~java
package com.acme.shop.inventory.web;

import com.acme.shop.inventory.InventoryService;
import com.acme.shop.inventory.InventoryStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/inventory")
public class InventoryController {

    private final InventoryService inventory;

    public InventoryController(InventoryService inventory) {
        this.inventory = inventory;
    }

    @GetMapping("/{productId}")
    public InventoryStatus getStatus(@PathVariable String productId) {
        return inventory.status(productId);
    }
}
~~~

Lưu ý về phạm vi ví dụ: @EventListener xử lý event đồng bộ trong cùng process. Bài này chưa cấu hình event publication registry, outbox, retry hoặc lưu trữ reservation bền vững. Những khả năng đó cần persistence và event infrastructure riêng khi đưa ứng dụng vào môi trường production.

## 8. Kiểm tra package tree trước khi verify

Sau khi tạo các class, package tree chính cần có dạng:

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
│   ├── api
│   │   ├── package-info.java
│   │   ├── ProductCatalog.java
│   │   └── ProductDetails.java
│   └── internal
│       └── InMemoryProductCatalog.java
├── orders
│   ├── package-info.java
│   ├── OrderService.java
│   ├── OrderConfirmation.java
│   ├── events
│   │   ├── package-info.java
│   │   └── OrderPlaced.java
│   └── web
│       ├── OrderController.java
│       └── PlaceOrderRequest.java
└── inventory
    ├── package-info.java
    ├── InventoryService.java
    ├── InventoryReservation.java
    ├── InventoryStatus.java
    ├── OrderPlacedListener.java
    └── web
        └── InventoryController.java
~~~

Chỉ ba package trực tiếp catalog, orders và inventory được nhận diện thành application module. Các package api, internal, events và web là package con bên trong module tương ứng.

Package gốc của một module là API mặc định (unnamed interface). Vì vậy, OrderService và OrderConfirmation trong package gốc orders, cũng như InventoryService và các record trong package gốc inventory, là các kiểu công khai của module tương ứng. Thuộc tính allowedDependencies là allowlist cho dependency đi ra của module khai báo; nó không khóa dependency đi vào từ module khác. Trong bài này, orders chỉ phụ thuộc catalog::api và inventory chỉ phụ thuộc orders::events. Nếu muốn ẩn hẳn một service khỏi API mặc định, hãy chuyển nó vào package con internal và cập nhật các import trong cùng module. Catalog không có type trong package gốc; API của nó nằm trong named interface api.

## 9. Viết architecture test cho module model

Tạo src/test/java/com/acme/shop/ModuleStructureTests.java:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

import static org.assertj.core.api.Assertions.assertThat;

class ModuleStructureTests {

    @Test
    void detectsTheThreeFunctionalModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        assertThat(modules.getModuleByName("catalog")).isPresent();
        assertThat(modules.getModuleByName("orders")).isPresent();
        assertThat(modules.getModuleByName("inventory")).isPresent();

        modules.verify();
    }
}
~~~

Bài test xác nhận ba module đã được phát hiện và gọi verify() để kiểm tra:

- Dependency graph không có chu trình.
- orders chỉ truy cập API được phép của catalog.
- inventory chỉ truy cập named interface events của orders.
- Không module nào tham chiếu package nội bộ của module đóng khác.

Nếu test thất bại, đọc thông báo để xác định type nào tạo ra cạnh hoặc truy cập package không hợp lệ. Không chuyển các module sang OPEN chỉ để bỏ qua lỗi; hãy sửa import và hợp đồng giữa các module.

## 10. Viết module integration test cho orders

Test orders ở chế độ STANDALONE. Module này cần ProductCatalog từ module khác, vì vậy dùng @MockitoBean để thay dependency đó bằng mock. Tham số PublishedEvents cho phép kiểm tra event đã được phát trong quá trình thực thi use case mà không cần khởi tạo module catalog.

Tạo src/test/java/com/acme/shop/orders/OrderModuleTests.java:

~~~java
package com.acme.shop.orders;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.catalog.api.ProductDetails;
import com.acme.shop.orders.events.OrderPlaced;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.math.BigDecimal;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

@ApplicationModuleTest
class OrderModuleTests {

    @MockitoBean
    ProductCatalog catalog;

    @Autowired
    OrderService orders;

    @Test
    void publishesOrderPlacedWhenOrderIsCreated(PublishedEvents events) {
        when(catalog.findById("book-1")).thenReturn(Optional.of(
                new ProductDetails(
                        "book-1",
                        "Spring Modulith Workbook",
                        new BigDecimal("19.90")
                )
        ));

        OrderConfirmation confirmation = orders.placeOrder("book-1", 2);

        assertThat(confirmation.total()).isEqualByComparingTo("39.80");

        var matchingEvents = events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, confirmation.orderId());

        assertThat(matchingEvents).hasSize(1);
    }
}
~~~

Test này xác minh module orders thực hiện use case và phát event đúng hợp đồng. ProductCatalog được mock vì test chỉ tập trung vào module orders; implementation thật của catalog không cần được bootstrap.

## 11. Viết module integration test cho inventory

Inventory test ở chế độ STANDALONE. Test phát event bằng ApplicationEventPublisher và xác minh listener trong module inventory tạo reservation, giảm số lượng còn lại. Vì listener đang dùng @EventListener đồng bộ, trạng thái có thể được kiểm tra ngay sau publishEvent().

Tạo src/test/java/com/acme/shop/inventory/InventoryModuleTests.java:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.orders.events.OrderPlaced;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class InventoryModuleTests {

    @Autowired
    InventoryService inventory;

    @Autowired
    ApplicationEventPublisher events;

    @Test
    void reservesStockWhenOrderPlacedArrives() {
        events.publishEvent(new OrderPlaced("order-42", "book-1", 2));

        assertThat(inventory.findReservation("order-42")).isPresent();
        assertThat(inventory.status("book-1").availableQuantity())
                .isEqualTo(18);
    }
}
~~~

PublishedEvents phù hợp để kiểm tra event được phát ra; ApplicationEventPublisher giúp kích hoạt listener trong bài test inventory. Nếu nâng cấp listener sang xử lý bất đồng bộ hoặc transactional, có thể dùng Scenario để chờ event hoặc state change. Scenario cần TransactionOperations và ApplicationEventProcessor phù hợp; hãy bổ sung transaction infrastructure khi chuyển sang bài toán đó.

## 12. Viết end-to-end test cho cả ba module

Architecture test kiểm tra cấu trúc; module integration test kiểm tra từng module. Bổ sung một test toàn ứng dụng để xác nhận luồng orders → catalog và event orders → inventory hoạt động cùng nhau.

Tạo src/test/java/com/acme/shop/ShopFlowIntegrationTests.java:

~~~java
package com.acme.shop;

import com.acme.shop.inventory.InventoryService;
import com.acme.shop.orders.OrderConfirmation;
import com.acme.shop.orders.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ShopFlowIntegrationTests {

    @Autowired
    OrderService orders;

    @Autowired
    InventoryService inventory;

    @Test
    void placingAnOrderUpdatesInventory() {
        OrderConfirmation confirmation = orders.placeOrder("book-1", 2);

        assertThat(confirmation.total()).isEqualByComparingTo("39.80");
        assertThat(inventory.findReservation(confirmation.orderId())).isPresent();
        assertThat(inventory.status("book-1").availableQuantity()).isEqualTo(18);
    }
}
~~~

Vì event listener đang dùng @EventListener đồng bộ, khi placeOrder() trả về thì InventoryService đã xử lý event. Nếu đổi sang listener bất đồng bộ, test phải chờ trạng thái thay đổi thay vì giả định kết quả đã có ngay.

## 13. Chạy ứng dụng và thử REST API

Chạy test:

~~~bash
mvn test
~~~

Nếu các architecture test và integration test đều thành công, khởi động ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Gửi yêu cầu tạo đơn:

~~~bash
curl -X POST http://localhost:8080/orders -H "Content-Type: application/json" -d '{"productId":"book-1","quantity":2}'
~~~

Response có dạng:

~~~json
{
  "orderId": "mã-đơn-được-tạo",
  "productId": "book-1",
  "productName": "Spring Modulith Workbook",
  "quantity": 2,
  "total": 39.80
}
~~~

Kiểm tra tồn kho:

~~~bash
curl http://localhost:8080/inventory/book-1
~~~

Kết quả mong đợi:

~~~json
{
  "productId": "book-1",
  "availableQuantity": 18
}
~~~

Nếu gọi POST thêm một lần với quantity bằng 1, tồn kho còn 17. Nếu gửi productId không tồn tại, OrderService trả về lỗi nghiệp vụ do catalog không tìm thấy sản phẩm.

## 14. Đọc module graph và đối chiếu với code

Sau khi các module được nhận diện, dependency graph dự kiến:

~~~mermaid
flowchart LR
    inventory["inventory"] -->|"orders::events"| orders["orders"]
    orders -->|"catalog::api"| catalog["catalog"]
~~~

| Cạnh | Type hoặc contract tạo ra cạnh | Allowlist |
|---|---|---|
| orders → catalog | ProductCatalog, ProductDetails | catalog::api |
| inventory → orders | OrderPlaced event | orders::events |

Không có cạnh orders → inventory vì orders không import InventoryService và không inject bean của inventory. Luồng phát event tại runtime không tạo ra một dependency code ngược từ orders sang inventory.

Nếu bạn thêm một import từ orders sang InventoryService, Spring Modulith sẽ phát hiện một cạnh mới. Khi đó đồ thị có thể tạo chu trình orders ↔ inventory và verify() sẽ thất bại. Hãy giữ giao tiếp qua hợp đồng một chiều.

## 15. Bài tập mở rộng

Sau khi hoàn thành phiên bản cơ bản, thử các thay đổi sau:

1. **Thêm validation:** từ chối quantity bằng 0 hoặc âm, kiểm tra productId rỗng và trả lỗi HTTP phù hợp.
2. **Thêm named interface cho API orders:** công khai một hợp đồng truy vấn đơn hàng, sau đó giới hạn module consumer bằng allowedDependencies.
3. **Thêm module payment:** payment lắng nghe event OrderPlaced hoặc OrderConfirmed và tạo trạng thái thanh toán. Cập nhật graph sao cho không có dependency cycle.
4. **Thử vi phạm boundary:** import InMemoryProductCatalog trực tiếp từ orders. Chạy verify() và giải thích vì sao truy cập package internal bị từ chối.
5. **Thử vi phạm allowlist:** tạo một type trong orders tham chiếu package khác của catalog ngoài catalog::api. Quan sát lỗi và chuyển consumer về API được công khai.
6. **Thử chu trình:** tạo một tham chiếu ngược từ catalog đến orders. Quan sát lỗi cycle, sau đó loại bỏ cạnh ngược bằng một hợp đồng thuộc đúng module sở hữu.
7. **Nâng cấp event handling:** thay @EventListener bằng @ApplicationModuleListener và cấu hình publication registry JDBC hoặc JPA để tìm hiểu cách Spring Modulith theo dõi event publication.
8. **Bổ sung persistence:** thay Map trong catalog và inventory bằng repository thuộc module tương ứng. Không để module khác truy cập trực tiếp repository đó.

## 16. Tiêu chí hoàn thành

- [ ] Project Spring Boot khởi động được.
- [ ] Có đúng ba application module catalog, orders và inventory.
- [ ] Catalog công khai ProductCatalog qua named interface api.
- [ ] Orders chỉ phụ thuộc catalog::api.
- [ ] Orders công khai OrderPlaced qua named interface events.
- [ ] Inventory chỉ phụ thuộc orders::events.
- [ ] Inventory nhận event và cập nhật reservation.
- [ ] ApplicationModules.verify() hoàn tất mà không có vi phạm.
- [ ] OrderModuleTests xác minh event được phát.
- [ ] InventoryModuleTests xác minh reservation được tạo.
- [ ] ShopFlowIntegrationTests xác minh luồng đặt hàng cập nhật tồn kho.
- [ ] REST API trả về đơn hàng và tồn kho đúng như mong đợi.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy một trong ba module | Package không nằm trực tiếp dưới package root | Đặt module dưới com.acme.shop hoặc điều chỉnh detection strategy |
| Không tìm thấy ProductCatalog bean | Implementation không được component scan hoặc thiếu annotation | Đặt implementation trong package con catalog và đăng ký @Component |
| orders vi phạm allowedDependencies | Import type từ catalog.internal hoặc package khác ngoài api | Chỉ dùng ProductCatalog và ProductDetails trong catalog.api |
| inventory vi phạm allowedDependencies | Listener tham chiếu type ngoài orders.events | Đưa event contract vào named interface events và dùng đúng package |
| verify() báo cycle | Hai module tham chiếu type hoặc contract của nhau | Truy nguyên cạnh, chọn một chiều API/event và bỏ dependency ngược |
| OrderModuleTests thiếu ProductCatalog bean | STANDALONE không bootstrap module catalog | Dùng @MockitoBean hoặc chọn bootstrap mode rộng hơn khi cần tích hợp thật |
| Scenario không nhận event | Event type không khớp, listener chưa được scan hoặc test dùng sai module | Kiểm tra package test, listener annotation và event class |
| Tồn kho không thay đổi | Listener không nhận event hoặc event chứa productId khác | Kiểm tra OrderPlacedListener và dữ liệu event |
| Test chạy nhưng REST response lỗi | Request JSON sai hoặc dữ liệu sản phẩm không tồn tại | Gửi đúng productId book-1 và quantity dương |

## 18. Ghi nhớ

Một modular monolith có thể chạy trong một Spring Boot application nhưng vẫn có các ranh giới module được kiểm soát. Trong bài thực hành, catalog sở hữu ProductCatalog API; orders sử dụng API đó và phát OrderPlaced; inventory tiêu thụ event để cập nhật tồn kho. Named interface và allowedDependencies biến hợp đồng giữa các module thành quy tắc có thể kiểm tra. ApplicationModules.verify() bảo vệ dependency graph và package boundary; module integration test kiểm tra hành vi từng module; end-to-end test xác minh luồng nghiệp vụ hoàn chỉnh.

## Tài liệu tham khảo

- [Spring Modulith 2.2 – Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith 2.2 – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith 2.2 – Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Spring Modulith 2.2 – Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith 2.2 – BOM và danh sách artifact](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [Spring Boot 4.0 – Developing Your First Application](https://docs.spring.io/spring-boot/4.0/tutorial/first-application/index.html)

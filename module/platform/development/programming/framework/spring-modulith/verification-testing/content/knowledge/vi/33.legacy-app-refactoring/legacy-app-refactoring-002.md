# Tạo ApplicationModules cho code hiện hữu

Một ứng dụng Spring Boot cũ có `OrderService`, `StockRepository` và `PaymentService` trong các package theo tầng kỹ thuật. Nhóm muốn thêm Spring Modulith để kiểm tra ranh giới nghiệp vụ. Họ tạo một test:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Test không cho ra ba module `ordering`, `inventory`, `payments` như mong đợi, mà nhìn thấy `service`, `repository`, `domain` hoặc báo phụ thuộc vòng. Có người đề nghị thêm `@ApplicationModule` vào bất kỳ class nào để “tạo module”. Cách hiểu đó sai trọng tâm: **Spring Modulith xây mô hình application modules từ cấu trúc package và quy tắc phát hiện module; `ApplicationModules` không tự tách mã hay tạo module runtime mới**.

Bài **“Tạo ApplicationModules cho code hiện hữu”** thuộc chương **Refactoring an existing app** của **SPRING_MODULITH_VERIFICATION_TESTING**. Ta thực hiện từng bước chuyển một lát cắt legacy thành module thật, khai báo API và dependency hợp lệ, dùng `ApplicationModules.of(...).verify()` làm phép kiểm chứng, tiếp đến `@ApplicationModuleTest`, event và database/integration tests để bảo vệ hành vi trong CI. Trọng tâm là **thao tác tạo ranh giới có thể chứng minh**, không lặp lại bài nhập môn về lý do dùng modular monolith.

> **Đích cần đạt:** `inventory`, `ordering`, `fulfillment` được Spring Modulith nhận diện đúng; module caller chỉ biết contract được công bố; `verify()` bắt được một tham chiếu nội bộ nếu ai đó thêm lại; test module được bootstrap với phạm vi có chủ đích; nghiệp vụ đặt đơn vẫn giữ đúng transaction và dữ liệu.

## 1. “Tạo ApplicationModules” thực sự làm những việc gì?

Trong Spring Modulith có hai khái niệm dễ bị lẫn:

- **Application module**: phần của ứng dụng được nhận diện qua package topology và cấu hình Spring Modulith. Nó có tên/identifier, các package và dependency.
- **`ApplicationModules`**: mô hình các module của một ứng dụng do API `org.springframework.modulith.core.ApplicationModules` tạo ra để phân tích, kiểm chứng và sử dụng trong công cụ/test.

Đoạn sau **đọc mô hình**, không chuyển file, không sinh module mới, không tạo database riêng và không thay đổi Spring bean lifecycle:

```java
ApplicationModules modules =
    ApplicationModules.of(ShopApplication.class);

modules.verify();
```

Với chiến lược phát hiện mặc định, **các subpackage trực tiếp dưới application base package** là các application module ứng viên. Ví dụ `com.example.shop.inventory` là module nếu `ShopApplication` ở `com.example.shop` và không có cấu hình phát hiện đặc biệt. Package bên trong như `inventory.internal.persistence` là phần của Inventory, không tự trở thành một module mới chỉ vì có nhiều cấp.

Để biến code legacy thành những application modules có ý nghĩa, cần thực hiện bốn thao tác:

1. **Xác định root package thật** mà Spring Modulith dùng.
2. **Đưa mã cùng trách nhiệm vào package module** thuộc root đó.
3. **Đặt hợp đồng được công bố ở package phù hợp**, khai báo `@NamedInterface` khi cần và quy định `allowedDependencies` có chủ đích.
4. **Dựng mô hình bằng `ApplicationModules.of(...)`, chạy `verify()` và kiểm tra hành vi** bằng module/integration tests.

### 1.1. Annotation không thay thế package boundary

```java
// inventory/package-info.java
@org.springframework.modulith.ApplicationModule
package com.example.shop.inventory;
```

`@ApplicationModule` là metadata cho một **package module**; không phải annotation đặt tùy ý trên `StockService` để biến class đó thành một module runtime. Với detection mặc định, một package module hợp lệ có thể được phát hiện **không cần** `@ApplicationModule`; annotation thường được thêm khi cần cấu hình metadata như `allowedDependencies`, `displayName`, `type`.

Nếu code vẫn nằm dưới:

```text
com.example.shop.service.OrderService
com.example.shop.repository.StockRepository
```

thì chỉ thêm một file `inventory/package-info.java` rỗng **không di chuyển các class cũ vào Inventory**. Model phản ánh package thực tế, không phản ánh sơ đồ mong muốn.

### 1.2. Bốn bằng chứng cần đối chiếu

| Bằng chứng | Phép kiểm tra | Kết luận được phép rút ra |
| --- | --- | --- |
| Module topology | `ApplicationModules.of(ShopApplication.class)` | Framework nhận diện module/package nào |
| Module architecture | `modules.verify()` | Dependency Java phù hợp các quy tắc được kiểm chứng |
| Module behavior | `@ApplicationModuleTest` | Bean/use case trong bootstrap scope được kiểm tra |
| End-to-end behavior | PostgreSQL/Testcontainers, event/integration tests | Giao dịch, ràng buộc dữ liệu và consumer hoạt động theo hợp đồng |

Không dùng một kết quả `verify()` xanh để suy rằng service commit đúng hoặc event listener đã xử lý. Ngược lại, một `@SpringBootTest` full context xanh không chứng minh repository nội bộ của Inventory không bị Ordering truy cập trực tiếp.

## 2. Chọn một lát cắt legacy có thể chuyển mà không đổi nghiệp vụ

Giả sử package tree hiện tại:

```text
com.example.shop
├── ShopApplication.java
├── controller/
│   └── OrderController.java
├── service/
│   ├── PlaceOrderService.java
│   ├── StockReservationService.java
│   └── ShipmentService.java
├── repository/
│   ├── SalesOrderRepository.java
│   ├── StockRepository.java
│   └── PickingTaskRepository.java
├── domain/
│   ├── SalesOrder.java
│   ├── Stock.java
│   └── PickingTask.java
└── events/
    └── OrderPlaced.java
```

Mục tiêu là nhận diện ba module theo trách nhiệm: `inventory`, `ordering`, `fulfillment`. Trước khi di chuyển, phải biết:

| Mã hiện hữu | Owner sau khi tách | Tác vụ/đặc điểm cần giữ |
| --- | --- | --- |
| `StockReservationService` | Inventory | Trừ tồn có điều kiện, giữ hàng |
| `StockRepository`, `Stock` | Inventory | Bảo vệ invariant `available >= 0` |
| `PlaceOrderService`, `SalesOrderRepository`, `SalesOrder` | Ordering | Tạo đơn sau khi giữ hàng |
| `OrderController` | Ordering | Adapter HTTP của use case đặt đơn |
| `ShipmentService`, `PickingTaskRepository`, `PickingTask` | Fulfillment | Hậu xử lý event sau commit |
| `OrderPlaced` | Ordering, **API sự kiện được công bố** | Consumer ngoài Ordering được phép nhận kiểu event |

**Cần giữ nguyên hành vi nào?** Với `sku=SKU-X`, tồn `5`, request đặt `2`: Order thành công, tồn còn `3`, một reservation liên kết với order và event đúng hợp đồng. Nếu service ghi order thất bại trong cùng transaction vật lý, thay đổi Inventory phải rollback theo policy đã xác nhận; không được vô tình đổi thành eventually consistent chỉ vì nhóm muốn dùng event ở mọi ranh giới.

### 2.1. Đích package cụ thể, không chỉ tên module

```text
com/example/shop/
├── ShopApplication.java
├── inventory/
│   ├── package-info.java
│   ├── reservations/
│   │   ├── package-info.java
│   │   ├── InventoryReservations.java
│   │   ├── ReserveStock.java
│   │   ├── ReservationReceipt.java
│   │   └── InsufficientStock.java
│   └── internal/
│       ├── StockReservationService.java
│       └── persistence/
│           ├── StockRow.java
│           └── StockRepository.java
├── ordering/
│   ├── package-info.java
│   ├── placement/
│   │   ├── package-info.java
│   │   ├── OrderPlacement.java
│   │   └── PlaceOrder.java
│   ├── events/
│   │   ├── package-info.java
│   │   └── OrderPlaced.java
│   └── internal/
│       ├── PlaceOrderService.java
│       ├── SalesOrderRow.java
│       └── SalesOrderRepository.java
└── fulfillment/
    ├── package-info.java
    └── internal/
        ├── OrderPlacedListener.java
        └── PickingTaskRepository.java
```

Hai quyết định trọng yếu:

- Entity/repository của Inventory **cùng thuộc Inventory**, không đưa repository vào `shared` để tránh chỉnh import.
- Event DTO `OrderPlaced` thuộc **public contract của Ordering**; Fulfillment không cần `ordering.internal.SalesOrderRow`.

### 2.2. Di chuyển “cùng owner”, không đổi contract hàng loạt

Đối với một refactor an toàn:

1. Giữ **database table names, column names, migration history** ổn định trong commit di chuyển package đầu tiên, nếu có thể.
2. Di chuyển entity cùng repository và service của owner; cập nhật imports/component scanning cần thiết.
3. Giữ HTTP endpoints và payload bên ngoài ổn định khi chưa chủ đích version API.
4. Viết contract public mới đủ hẹp; thay từng caller, tránh refactor mọi caller cùng lúc.
5. Chạy characterization tests sau mỗi bước; không đợi đến cuối mới biết transaction behavior đã đổi.

**Không cần một module có một database riêng.** Spring Modulith cho phép các module trong một monolith cùng datasource; phân tách sở hữu dữ liệu là quyết định thiết kế, còn thay schema/database vật lý là việc khác.

### 2.3. Kiểm tra cấu hình scanning của legacy

Khi chuyển package, những cấu hình này cần rà soát theo chính ứng dụng:

- `@SpringBootApplication` và base package.
- `@ComponentScan` hoặc các include/exclude filters.
- `@EntityScan` và `@EnableJpaRepositories` nếu dự án tùy chỉnh.
- `@Configuration` tạo bean bằng tay và AOP transaction proxies.
- Event listener registrations, scheduler, adapters và package names trong tests.

Một ứng dụng compile thành công nhưng không khởi tạo repository do scan sai **chưa** có module vận hành được. Tuy nhiên không dùng tùy tiện `scanBasePackages = "com.example"` để nạp toàn bộ beans vào module test rồi bỏ qua dependency cần kiểm soát.

## 3. Tạo API module trước khi chuyển caller

Giả sử Ordering đang inject trực tiếp `StockRepository`. Để loại đường phụ thuộc đó, Inventory cần một contract đủ diễn đạt **ý định nghiệp vụ giữ hàng**, thay vì expose CRUD.

### 3.1. Named interface của Inventory

```java
// inventory/reservations/package-info.java
@org.springframework.modulith.NamedInterface("reservations")
package com.example.shop.inventory.reservations;
```

```java
// inventory/reservations/ReserveStock.java
package com.example.shop.inventory.reservations;

import java.util.UUID;

public record ReserveStock(String sku, int quantity, UUID requestId) {
    public ReserveStock {
        if (sku == null || sku.isBlank()
                || quantity <= 0 || requestId == null) {
            throw new IllegalArgumentException("Lệnh giữ hàng không hợp lệ");
        }
    }
}
```

```java
// inventory/reservations/ReservationReceipt.java
package com.example.shop.inventory.reservations;

import java.util.UUID;

public record ReservationReceipt(UUID reservationId) {}
```

```java
// inventory/reservations/InventoryReservations.java
package com.example.shop.inventory.reservations;

public interface InventoryReservations {
    ReservationReceipt reserve(ReserveStock command);
}
```

```java
// inventory/reservations/InsufficientStock.java
package com.example.shop.inventory.reservations;

public final class InsufficientStock extends RuntimeException {
    public InsufficientStock(String sku) {
        super("Không đủ hàng cho SKU: " + sku);
    }
}
```

Đặt các kiểu contract bên trong `inventory.reservations` để consumer có thể chỉ import **`inventory::reservations`**. Annotation `@NamedInterface` công bố **package con** thành một interface có tên; không tự chuyển repository nội bộ thành public. Kiểu Java có `public` cũng không đồng nghĩa được phép truy cập qua ranh giới closed module trong Spring Modulith.

### 3.2. Implementation vẫn ở nội bộ

Một implementation giản lược với JDBC (để tập trung vào boundary, không phụ thuộc thêm JPA mapping):

```java
// inventory/internal/StockReservationService.java
package com.example.shop.inventory.internal;

import com.example.shop.inventory.reservations.InsufficientStock;
import com.example.shop.inventory.reservations.InventoryReservations;
import com.example.shop.inventory.reservations.ReservationReceipt;
import com.example.shop.inventory.reservations.ReserveStock;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class StockReservationService implements InventoryReservations {

    private final JdbcTemplate jdbc;

    StockReservationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional
    public ReservationReceipt reserve(ReserveStock command) {
        int changed = jdbc.update("""
            UPDATE inventory_stock
               SET available = available - ?
             WHERE sku = ? AND available >= ?
            """,
            command.quantity(), command.sku(), command.quantity()
        );
        if (changed != 1) {
            throw new InsufficientStock(command.sku());
        }

        UUID id = UUID.randomUUID();
        jdbc.update("""
            INSERT INTO stock_reservation
              (reservation_id, request_id, sku, quantity)
            VALUES (?, ?, ?, ?)
            """,
            id, command.requestId(),
            command.sku(), command.quantity()
        );
        return new ReservationReceipt(id);
    }
}
```

Ở đây `@Transactional` bảo vệ **giảm tồn + ghi reservation trong cùng datasource/transaction**. Query update có điều kiện giúp tránh read–modify–write làm oversell; database vẫn cần `CHECK available >= 0`, `UNIQUE request_id`, foreign key và test concurrent. Một hệ thống production còn cần xử lý request lặp/idempotency (ví dụ retry sau timeout), giải phóng reservation và version/locking policy phù hợp.

Quan trọng: implementation **không** trở thành API chỉ vì class khai báo `implements InventoryReservations`. Ordering chỉ inject interface công khai; package `inventory.internal` tiếp tục là chi tiết không được phép phụ thuộc từ module khác.

### 3.3. Không tạo “API” chỉ đổi tên repository

Phản mẫu:

```java
public interface InventoryFacade {
    StockRow findEntity(String sku);
    void saveEntity(StockRow entity);
    void executeSql(String sql);
}
```

Interface này vẫn làm caller biết persistence model và cho phép sửa invariant của Inventory. Test kiến trúc có thể không thấy lỗi import repository trực tiếp nữa, nhưng **ownership vẫn bị phá trên thực tế**. Hợp đồng tốt diễn đạt `reserve(ReserveStock)`, có kết quả/lỗi nghiệp vụ rõ ràng, và giữ JPA/JDBC nằm ở owner.

## 4. Khai báo `@ApplicationModule` và dependency rules

Khi đã có package root và API, định nghĩa quyền truy cập giữa các module bằng `package-info.java`.

### 4.1. Tại package module Inventory

```java
// inventory/package-info.java
@org.springframework.modulith.ApplicationModule
package com.example.shop.inventory;
```

Metadata này có thể được bỏ qua nếu đang dùng defaults và không cần cấu hình; **vị trí của package mới quyết định root module** theo detection mặc định.

### 4.2. Ordering chỉ được dùng Inventory reservations

```java
// ordering/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::reservations"
)
package com.example.shop.ordering;
```

Điều này biểu đạt **quyền dependency có chủ đích**: Ordering có thể tham chiếu kiểu thuộc named interface `inventory::reservations`, nhưng không được import `inventory.internal.StockRepository` hay `inventory.internal.persistence.StockRow`. Khi dùng `allowedDependencies`, hãy liệt kê **đủ những dependency thực sự hợp lệ** mà Ordering cần, không bỏ qua các module contract khác đang được dùng hợp pháp.

### 4.3. Ordering công bố event cho Fulfillment

```java
// ordering/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.ordering.events;
```

```java
// ordering/events/OrderPlaced.java
package com.example.shop.ordering.events;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
```

```java
// fulfillment/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "ordering::events"
)
package com.example.shop.fulfillment;
```

Fulfillment được import `ordering.events.OrderPlaced`, nhưng không được đọc `ordering.internal.SalesOrderRepository`. **Hướng dependency Java** là Fulfillment → Ordering event type, còn **hướng luồng event runtime** là Ordering → Fulfillment. Hai hướng khác nhau này đặc biệt quan trọng khi đọc module graph.

### 4.4. Closed module là mặc định nên giữ

Trong quá trình chuyển legacy, có thể gặp lời đề xuất tạm biến module thành **open module** để cho phép tham chiếu mọi package. Điều đó làm giảm giá trị của bài kiểm tra ranh giới. Chỉ cân nhắc một ngoại lệ open có phạm vi, lý do và kế hoạch loại bỏ rõ ràng; ưu tiên xuất API nhỏ rồi chuyển caller lần lượt.

Không thêm:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "inventory", "fulfillment", "ordering" }
)
package com.example.shop.ordering;
```

chỉ để làm `verify()` ngừng báo lỗi. Một danh sách quyền rộng không loại bỏ chu trình thực, SQL cross-write hay transaction coupling.

## 5. Dựng mô hình `ApplicationModules` và chứng minh boundary mới

Sau khi sửa package và thay caller, **đừng chỉ nhìn cây thư mục**. Dùng API Spring Modulith đọc chính module model mà framework suy ra.

### 5.1. Kiểm tra module identifiers

```java
// src/test/java/com/example/shop/ModularityTests.java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void recognizesBusinessModulesInsteadOfTechnicalLayers() {
        ApplicationModules modules =
            ApplicationModules.of(ShopApplication.class);

        var identifiers = new ArrayList<String>();
        modules.forEach(module ->
            identifiers.add(module.getIdentifier().toString())
        );

        assertThat(identifiers).contains(
            "inventory", "ordering", "fulfillment"
        );
        assertThat(identifiers).doesNotContain(
            "service", "repository", "domain", "controller"
        );
    }

    @Test
    void moduleDependenciesRespectPublishedInterfaces() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Test này giả định **detection mặc định** và package targets ở mục 2; nếu ứng dụng có additional technical modules hoặc strategy phát hiện tùy biến, điều chỉnh kỳ vọng theo mô hình đã thống nhất. Không dùng assertion `containsExactly(...)` khi dự án còn các module hợp lệ khác. Việc `getIdentifier()` được in ra giúp thấy tên module thực, không suy từ tên file.

Phép kiểm tra thứ nhất phát hiện lỗi **module topology** (đặt package sai), phép thứ hai phát hiện vi phạm **architecture dependency**. Đây là hai loại lỗi khác nhau và nên báo cáo khác nhau trong CI.

### 5.2. Một thay đổi nhỏ cần làm test đỏ

Giả sử ai đó sửa Ordering:

```java
// ordering/internal/PlaceOrderService.java
import com.example.shop.inventory.internal.persistence.StockRepository;
```

Khi `inventory` là một closed module và `StockRepository` nằm ngoài API/named interfaces được công bố, `modules.verify()` phải phát hiện dependency Java trái ranh giới. Đây là một **negative architecture check** có giá trị trong review: nếu cố tình thêm import sai mà test vẫn xanh, cần xem lại detection, module type hoặc các rule đã cấu hình quá rộng.

Đừng giữ import sai trong code chính chỉ để “thử” CI. Làm thử trong branch/test mutation tạm hoặc một PR thử nghiệm, quan sát quality gate fail, rồi revert.

### 5.3. Phân biệt kết quả `verify()` với kiểm tra ownership SQL

Một đoạn code trong Ordering:

```java
jdbc.update("""
    UPDATE inventory_stock
       SET available = available - 1
     WHERE sku = ?
    """, sku);
```

chỉ thể hiện Java type dependency tới `JdbcTemplate`, không tới `StockRepository`. Do vậy `verify()` không tự bảo đảm sẽ phát hiện đường cross-write này. Các việc bổ sung:

- Code review/search native SQL và câu `@Query` dùng bảng của module khác.
- Unit/integration test cho API giữ hàng của Inventory.
- PostgreSQL constraints/atomic update, idempotency và transaction rollback tests.
- Nếu phù hợp, áp dụng DB permissions hoặc test architecture rules riêng cho persistence ownership.

**Boundary đúng** nghĩa là cả Java dependencies **và** đường ghi dữ liệu phải đi qua owner đã xác định.

### 5.4. Nếu `verify()` thất bại ngay sau khi chuyển package

Đọc lỗi theo loại:

| Tín hiệu | Khả năng nguyên nhân | Sửa vào đâu? |
| --- | --- | --- |
| `service` vẫn là module | Một số class còn ở package cấp root cũ | Tiếp tục chuyển/mở kế hoạch thay thế package kỹ thuật |
| Ordering truy cập Inventory internal | Caller chưa chuyển sang contract hoặc DTO public còn chứa internal entity | Cập nhật caller/API |
| Cycle `ordering ↔ fulfillment` | Listener gọi repository Ordering trong khi Ordering lại phụ thuộc Fulfillment | Cắt dependency theo chiều contract/event hợp lệ |
| Named interface không nhận diện | `package-info.java` đặt sai package hoặc annotation/import sai | Kiểm tra tên package thực tế và metadata |
| Dependency ngoài `allowedDependencies` | Thiếu contract được phép hoặc caller dùng API chưa được duyệt | Review rồi cập nhật rule/caller có chủ đích |
| Model không thấy Inventory | `ShopApplication` sai root/custom detection hoặc mã nằm ngoài root | Kiểm tra base package và detection strategy |

Không dùng `allowedDependencies` rộng hoặc open module lâu dài để che một lỗi topology. Phải biết **model đang nhận diện package nào**, rồi mới quyết định sửa mã hay sửa policy.

## 6. Tạo module Ordering mà không đổi transaction behavior

Inventory đã có contract `reserve(...)`; Ordering phải gọi contract đó thay vì thao tác trực tiếp `inventory_stock`.

### 6.1. API công khai của Ordering

```java
// ordering/placement/package-info.java
@org.springframework.modulith.NamedInterface("placement")
package com.example.shop.ordering.placement;
```

```java
// ordering/placement/PlaceOrder.java
package com.example.shop.ordering.placement;

import java.util.UUID;

public record PlaceOrder(
    String sku, int quantity, UUID requestId
) {
    public PlaceOrder {
        if (sku == null || sku.isBlank()
                || quantity <= 0 || requestId == null) {
            throw new IllegalArgumentException("Đơn hàng không hợp lệ");
        }
    }
}
```

```java
// ordering/placement/OrderPlacement.java
package com.example.shop.ordering.placement;

import java.util.UUID;

public interface OrderPlacement {
    UUID place(PlaceOrder command);
}
```

### 6.2. Service Ordering chỉ biết Inventory API

```java
// ordering/internal/PlaceOrderService.java
package com.example.shop.ordering.internal;

import com.example.shop.inventory.reservations.InventoryReservations;
import com.example.shop.inventory.reservations.ReserveStock;
import com.example.shop.ordering.events.OrderPlaced;
import com.example.shop.ordering.placement.OrderPlacement;
import com.example.shop.ordering.placement.PlaceOrder;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class PlaceOrderService implements OrderPlacement {

    private final InventoryReservations inventory;
    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher events;

    PlaceOrderService(
        InventoryReservations inventory,
        JdbcTemplate jdbc,
        ApplicationEventPublisher events
    ) {
        this.inventory = inventory;
        this.jdbc = jdbc;
        this.events = events;
    }

    @Override
    @Transactional
    public UUID place(PlaceOrder command) {
        var receipt = inventory.reserve(new ReserveStock(
            command.sku(), command.quantity(), command.requestId()
        ));

        UUID orderId = UUID.randomUUID();
        jdbc.update("""
            INSERT INTO sales_order
              (order_id, request_id, sku, quantity, reservation_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            orderId,
            command.requestId(),
            command.sku(),
            command.quantity(),
            receipt.reservationId()
        );

        events.publishEvent(new OrderPlaced(orderId));
        return orderId;
    }
}
```

**Giả định có tính quyết định:** Trong modular monolith, cả Ordering và Inventory sử dụng **cùng datasource và một transaction manager**, lời gọi qua Spring-managed beans (không tự `new` service), hai service dùng propagation mặc định `REQUIRED`. Khi `PlaceOrderService.place()` mở transaction, `StockReservationService.reserve()` **tham gia transaction đó**. Nếu INSERT `sales_order` thất bại, cập nhật stock và reservation **rollback cùng nhau**; event được publish trong transaction nhưng consumer `AFTER_COMMIT` không được coi là success nếu rollback.

Nếu hai module dùng transaction manager khác nhau hoặc Inventory cố ý `REQUIRES_NEW`, contract không còn nguyên tử theo mô hình này. Đó không phải chỉ là việc đổi package; cần xác định lại compensation/outbox/reconciliation và test phù hợp trước khi chấp nhận.

### 6.3. DDL tối thiểu cho test PostgreSQL

Trong dự án thật dùng migration production (Flyway/Liquibase). Một bộ DDL minh họa:

```sql
CREATE TABLE inventory_stock (
    sku VARCHAR(80) PRIMARY KEY,
    available INTEGER NOT NULL
        CHECK (available >= 0)
);

CREATE TABLE stock_reservation (
    reservation_id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    sku VARCHAR(80) NOT NULL
        REFERENCES inventory_stock(sku),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

CREATE TABLE sales_order (
    order_id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    reservation_id UUID NOT NULL UNIQUE
        REFERENCES stock_reservation(reservation_id)
);
```

Schema này cho phép test quan sát **đúng một order và reservation** cho request. Nó không phải schema production đầy đủ: order status, customer, payment, cancellation và retry idempotent cần mô hình riêng.

Đừng đổi tên bảng/column trong cùng commit với di chuyển package chỉ để phản ánh tên module mới, trừ khi có migration và compatibility plan rõ. Bài kiểm chứng trước/sau sẽ khó quy trách nhiệm nếu đồng thời đổi cấu trúc package, schema và semantics transaction.

### 6.4. Kiểm chứng rollback ở ranh giới mới

Một test use case cần chủ động gây lỗi **sau khi Inventory đã giảm tồn nhưng trước khi order commit**, chẳng hạn thông qua constraint/điểm lỗi được kiểm soát. Sau khi `OrderPlacement.place(...)` ném exception và transaction kết thúc:

```text
Given:
  SKU-X.available = 5 (đã commit)
  requestId R chưa tồn tại

When:
  Inventory giảm tồn 2 và tạo reservation
  INSERT sales_order lỗi có chủ đích
  Ordering transaction rollback

Then:
  SKU-X.available = 5
  không có reservation R
  không có sales_order R
  không có Fulfillment success side effect từ OrderPlaced(R)
```

Phần rollback trên là **test contract cần triển khai**; không gây lỗi trước khi Inventory chạy rồi tuyên bố đã kiểm tra atomicity. Cần một điểm fault được kiểm soát ở repository/SQL hoặc một dữ liệu vi phạm constraint được tạo sau bước reserve, không sửa production code bằng một `if (isTest)` flag.

## 7. Module test đầu tiên: Inventory `STANDALONE` trên PostgreSQL

Một module đã tồn tại trong `ApplicationModules` chưa chắc **tự bootstrap và hoạt động đúng**. `@ApplicationModuleTest` kiểm tra ranh giới bean của module và behavior của API.

### 7.1. Chuẩn bị test theo module package

Đặt test dưới:

```text
src/test/java/com/example/shop/inventory/
    InventoryModuleTests.java
```

Không đặt dưới `com.example.shop.service`, vì vị trí package test tham gia việc xác định module được bootstrap.

### 7.2. Test chạy service thật và đọc DB đã commit

```java
package com.example.shop.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.inventory.reservations.InventoryReservations;
import com.example.shop.inventory.reservations.ReserveStock;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@ApplicationModuleTest(mode = BootstrapMode.STANDALONE)
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class InventoryModuleTests {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired InventoryReservations inventory;
    @Autowired JdbcTemplate jdbc;

    @Test
    void reserveThroughPublicApiMaintainsInventoryInvariant() {
        String sku = "IT-" + UUID.randomUUID();
        UUID requestId = UUID.randomUUID();
        jdbc.update("""
            INSERT INTO inventory_stock(sku, available)
            VALUES (?, 5)
            """, sku);

        try {
            var receipt = inventory.reserve(new ReserveStock(
                sku, 2, requestId
            ));

            Integer available = jdbc.queryForObject("""
                SELECT available FROM inventory_stock WHERE sku = ?
                """, Integer.class, sku);

            Integer rows = jdbc.queryForObject("""
                SELECT count(*) FROM stock_reservation
                WHERE reservation_id = ? AND request_id = ?
                """, Integer.class, receipt.reservationId(), requestId);

            assertThat(available).isEqualTo(3);
            assertThat(rows).isEqualTo(1);
        } finally {
            jdbc.update(
                "DELETE FROM stock_reservation WHERE sku = ?", sku
            );
            jdbc.update(
                "DELETE FROM inventory_stock WHERE sku = ?", sku
            );
        }
    }
}
```

### 7.3. Vì sao test này đủ thực tế?

- `STANDALONE` cố ý bootstrap Inventory, không lén nạp Ordering để có `OrderService`.
- Gọi `InventoryReservations`, không gọi thẳng repository nội bộ để bypass business rule.
- Fixture có SKU/request ID riêng; assert DB bằng một truy vấn có scope.
- Test **không** `@Transactional` ở cấp method, nên service transaction thực tế đã commit khi proxy trả về, trong mô hình cùng transaction manager phù hợp.
- `@ServiceConnection` cho Spring Boot có tích hợp Testcontainers tương thích (ví dụ Spring Boot 3.1+); cần PostgreSQL driver, JDBC starter, Spring Modulith test, Testcontainers modules, Flyway/Liquibase migrations và container runtime.
- `@DirtiesContext` tránh tái sử dụng Spring context chứa datasource trỏ tới per-class container đã stop. **Nó không xóa data**; container của riêng class được thu hồi sau lifecycle, tùy cấu hình reuse và môi trường.

Nếu ứng dụng dùng JPA, chuyển `StockRow`/repository của owner và đảm bảo entity scan/repository scan trong module test đúng; việc dùng JDBC ở ví dụ chỉ giúp tập trung vào **ranh giới ứng dụng và transaction**.

### 7.4. Phản mẫu cần tránh

```java
@ApplicationModuleTest(mode = BootstrapMode.ALL_DEPENDENCIES)
class InventoryModuleTests { ... }
```

Chuyển sang `ALL_DEPENDENCIES` chỉ vì thiếu bean Ordering có thể che mất dependency vi phạm mà test đang cần phơi bày. Trước khi đổi mode, hỏi:

1. Bean thiếu thuộc module nào?
2. Inventory có nên phụ thuộc module đó không?
3. Bean config đang đặt sai package hay cần test support riêng?
4. Nếu cần consumer ở module khác, phải dùng integration test thay vì module test scope hẹp không?

**Test module thành công là test có scope đúng**, không phải test nạp càng nhiều bean càng tốt.

## 8. Kiểm tra dependency và event sau khi tạo Ordering module

Sau Inventory, ta cần hai bằng chứng riêng:

1. Ordering gọi được **API hợp lệ của Inventory** trong cùng transaction cần thiết.
2. Event `OrderPlaced` được publish đúng contract, và nếu có Fulfillment listener bất đồng bộ thì consumer được kiểm chứng **ở integration test riêng**.

### 8.1. `DIRECT_DEPENDENCIES`: test Ordering cùng dependency trực tiếp

Đặt test đúng package Ordering, dùng PostgreSQL container/schema riêng:

```java
package com.example.shop.ordering;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.ordering.events.OrderPlaced;
import com.example.shop.ordering.placement.OrderPlacement;
import com.example.shop.ordering.placement.PlaceOrder;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderingModuleTests {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderPlacement orders;
    @Autowired JdbcTemplate jdbc;

    @Test
    void placesOrderViaInventoryContract(PublishedEvents events) {
        String sku = "IT-" + UUID.randomUUID();
        UUID requestId = UUID.randomUUID();
        jdbc.update("""
            INSERT INTO inventory_stock(sku, available)
            VALUES (?, 5)
            """, sku);

        try {
            UUID orderId = orders.place(new PlaceOrder(
                sku, 2, requestId
            ));

            Integer stock = jdbc.queryForObject("""
                SELECT available FROM inventory_stock WHERE sku = ?
                """, Integer.class, sku);
            Integer ordersCount = jdbc.queryForObject("""
                SELECT count(*) FROM sales_order
                WHERE order_id = ? AND request_id = ?
                """, Integer.class, orderId, requestId);
            Integer reservations = jdbc.queryForObject("""
                SELECT count(*) FROM stock_reservation
                WHERE request_id = ?
                """, Integer.class, requestId);

            assertThat(stock).isEqualTo(3);
            assertThat(ordersCount).isEqualTo(1);
            assertThat(reservations).isEqualTo(1);

            assertThat(events.ofType(OrderPlaced.class)
                .matching(e -> e.orderId().equals(orderId)))
                .hasSize(1);
        } finally {
            jdbc.update(
                "DELETE FROM sales_order WHERE request_id = ?", requestId
            );
            jdbc.update(
                "DELETE FROM stock_reservation WHERE request_id = ?",
                requestId
            );
            jdbc.update(
                "DELETE FROM inventory_stock WHERE sku = ?", sku
            );
        }
    }
}
```

Test trên có các điều kiện:

- `ordering` khai báo `allowedDependencies = "inventory::reservations"` và class thực thi ở module Inventory đã được Spring nhận diện.
- `DIRECT_DEPENDENCIES` bootstrap Ordering và những dependency trực tiếp được phát hiện; không phải tất cả listener trong hệ thống.
- Test không có `@Transactional` ngoài; service `OrderPlacement.place()` và Inventory thực hiện trên cùng datasource/transaction manager.
- Câu truy vấn JDBC chạy **sau lời gọi proxy service** và assert dữ liệu đã commit.
- `PublishedEvents` là cơ chế ghi nhận event trong module test; nó chứng minh **publication/payload**, không tự chứng minh consumer async đã hoàn tất.
- Fixture dùng request ID và SKU riêng, cleanup theo thứ tự FK trên database thử nghiệm. Nếu còn listener/registry khác cùng context, cleanup phải đợi các worker liên quan hoặc dùng container disposable.

API `PublishedEvents` và class annotations có thể thay đổi theo version dependencies của dự án; hãy kiểm tra dependency Spring Modulith test đang dùng, không giả định một bản build cũ có cùng mọi overload.

### 8.2. Fulfillment listener và ranh giới event

Trong Fulfillment:

```java
// fulfillment/internal/OrderPlacedListener.java
package com.example.shop.fulfillment.internal;

import com.example.shop.ordering.events.OrderPlaced;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedListener {

    private final JdbcTemplate jdbc;

    OrderPlacedListener(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        jdbc.update("""
            INSERT INTO picking_task (task_id, order_id)
            VALUES (?, ?)
            ON CONFLICT (order_id) DO NOTHING
            """, UUID.randomUUID(), event.orderId());
    }
}
```

Migration test cần có bảng:

```sql
CREATE TABLE picking_task (
    task_id UUID PRIMARY KEY,
    order_id UUID NOT NULL UNIQUE
        REFERENCES sales_order(order_id)
);
```

Đây là ví dụ một event-driven consumer dùng PostgreSQL. Tùy phiên bản và cấu hình, `@ApplicationModuleListener` sử dụng transactional event semantics, asynchronous dispatch và transaction riêng; việc commit consumer **không đồng nghĩa** với việc producer method vừa trả về. `ON CONFLICT` giúp bảo vệ idempotency cho một `orderId`, không thể tự bảo đảm exactly-once delivery hoặc giải quyết payload sai.

### 8.3. Full integration test kiểm tra consumer sau commit

Nếu mục tiêu là chứng minh Ordering → Fulfillment hoạt động thật, dùng full application test hoặc một bootstrap scope có listener tương ứng:

```java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import com.example.shop.ordering.placement.OrderPlacement;
import com.example.shop.ordering.placement.PlaceOrder;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderingToFulfillmentIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderPlacement orders;
    @Autowired JdbcTemplate jdbc;

    @Test
    void committedOrderEventuallyCreatesOnePickingTask() {
        String sku = "IT-" + UUID.randomUUID();
        UUID requestId = UUID.randomUUID();
        jdbc.update("""
            INSERT INTO inventory_stock(sku, available)
            VALUES (?, 5)
            """, sku);

        UUID orderId = orders.place(new PlaceOrder(
            sku, 2, requestId
        ));

        await().atMost(Duration.ofSeconds(10))
            .untilAsserted(() -> {
                Integer tasks = jdbc.queryForObject("""
                    SELECT count(*) FROM picking_task
                    WHERE order_id = ?
                    """, Integer.class, orderId);
                assertThat(tasks).isEqualTo(1);
            });
        // Một scenario trên container riêng; toàn DB được bỏ sau class.
    }
}
```

Khác module test ở mục 8.1:

- `@SpringBootTest` bootstraps listener Fulfillment và event infrastructure.
- Producer commit thật vì test không được bọc transaction ngoài.
- Awaitility chờ **kết quả đã commit** ở consumer bằng `orderId`, không dùng `Thread.sleep`.
- Nếu Event Publication Registry được bật, cần test thêm retry/republication và đảm bảo persistence schema phù hợp. Một picking task hiện hữu không tự chứng minh không còn publication pending.
- Test minh họa dùng **một scenario, container riêng không reuse**; nếu có nhiều tests cùng DB, bổ sung teardown theo key và chờ worker hoàn tất trước khi cleanup.

Khi chỉ muốn kiểm tra event DTO `OrderPlaced` đúng, không cần full context. Khi muốn kiểm tra side effect Fulfillment thật, **không** kết luận từ `PublishedEvents` trong Ordering `STANDALONE`.

## 9. Những trường hợp code legacy chưa thể trở thành closed module ngay

Không phải tất cả code có thể di chuyển trong một commit. Các trở ngại nên được xem như **quyết định kiến trúc có thời hạn**, không như lý do bỏ qua ranh giới.

### 9.1. Có class nằm ngoài application base package

Nếu `ShopApplication` ở `com.example.shop.bootstrap` nhưng `inventory` ở `com.example.shop.inventory`, chiến lược phát hiện/module root và Spring component scan có thể không tương ứng. Đặt application root ở common ancestor hoặc cấu hình phát hiện modules **có chủ đích**. Đừng chỉ thay `@ComponentScan` cho startup xanh rồi mặc định `ApplicationModules` sẽ tự thay cách chia module.

Nếu dùng custom detection strategy theo Spring Modulith version cụ thể, cần kiểm tra module identifiers thực tế qua API test ở mục 5; **không** giả định thêm annotation ở package bất kỳ khiến default strategy bỏ qua root layout.

### 9.2. Đang có `service`, `repository` và `domain` ở cấp root

Có hai lựa chọn:

- **Chuyển dần và giữ lỗi kiến trúc được theo dõi:** Chốt những feature packages mới, dùng characterization test bảo vệ hành vi; theo dõi các package kỹ thuật còn lại và loại bỏ theo kế hoạch.
- **Thiết lập detection tùy chỉnh có kiểm soát:** Hữu ích khi không thể di chuyển ngay vì tương thích, nhưng phải tránh làm những dependency cũ biến mất khỏi báo cáo một cách giả tạo.

Đừng chỉ đánh dấu `service` là “shared” rồi cho mọi feature import nó. Nếu vẫn có nghiệp vụ trong `service`, cần xác định owner hoặc public contract.

### 9.3. Open module là một phương án chuyển tiếp có giá

Một application module kiểu **open** cho phép phụ thuộc vào nhiều package con hơn closed module theo semantics framework. Nếu dùng tạm trong legacy, ghi:

- Ai phê duyệt ngoại lệ và vì sao chưa thể di chuyển caller?
- Package nội bộ nào đang bị truy cập?
- Khi nào có named interface hoặc API thay thế?
- Những test nào phải đỏ khi trở lại closed module?

Không kéo dài trạng thái open vô thời hạn và coi `verify()` xanh là kiến trúc đã tốt.

### 9.4. Mọi module cùng dùng một JPA schema

Chia module Java **không** tự chia database. Khi move entity/package, JPA `@EntityScan`/repository scanning và mapping có thể cần điều chỉnh, nhưng phải giữ Flyway/Liquibase migrations chính thức. Đặc biệt:

- Entity association từ Ordering sang `inventory.internal.StockRow` vẫn là dependency xuyên module dù mapping tạo FK hợp lệ.
- Native SQL ghi thẳng `inventory_stock` từ Ordering không bị `verify()` nhận ra chỉ nhờ tên bảng.
- `@ApplicationModuleTest` có thể dùng **cùng datasource/schema** với các module khác.
- Foreign key và transaction trên một database có thể là invariant đang được ứng dụng dùng; tách database vật lý là bài toán khác.

Muốn thay JPA relationship bằng ID/reference qua API, cần characterization test bảo vệ query, transaction và rollback behavior, không chỉ đổi field type.

### 9.5. Shared configuration hoặc events mang state

Một `config` package chung có thể chứa `Clock`, datasource, transaction manager, cache, event registry. Phân loại:

| Mã cấu hình | Nơi nên cân nhắc | Kiểm chứng |
| --- | --- | --- |
| Pure framework config dùng toàn ứng dụng | Infrastructure/bootstrap với phạm vi rõ | Context/module test nạp đúng, không tạo cycle |
| Repo/mapper config chỉ cho Inventory | Đặt gần Inventory hoặc cấu hình được import có kiểm soát | Inventory standalone khởi động được |
| Event Publication Registry/async executor | Infrastructure chung, owner/lifecycle rõ | Producer commit và listener retry integration test |
| Domain policy/validation của Ordering | Trong Ordering | Không xuất ra `shared` để né dependency |
| Mutable singleton/test fake | Tách test state, không chia sẻ bừa | Test chạy đảo thứ tự và parallel không nhiễu |

Nếu module test fail vì bean config đặt ở package kỹ thuật cũ, truy ngược bean **thực sự thuộc module nào**, thay vì chuyển toàn bộ `config` vào API package của một module khác để không còn lỗi bootstrap.

## 10. Chuyển từng lát cắt và đặt quality gate theo mốc

Thay đổi từ package-by-layer sang application modules có thể chạm tới hàng trăm import. Cách đáng tin là thực hiện **một chuỗi thay đổi nhỏ**, mỗi thay đổi có bằng chứng đo được; đừng đợi chuyển toàn bộ repo rồi mới chạy test.

### 10.1. Chuỗi thay đổi đề xuất

| Bước | Thay đổi giới hạn | Gate phải đạt trước khi đi tiếp |
| --- | --- | --- |
| **A — Baseline** | Khóa hành vi place order/reserve stock và transaction hiện tại | Characterization tests trên DB thật, HTTP/API contract ổn định |
| **B — Inventory package** | Chuyển entity, repository, stock service vào `inventory.internal` | Spring context start; `ApplicationModules` nhận diện `inventory`; DB test owner |
| **C — Inventory API** | Công bố `inventory::reservations`, chuyển một caller đầu tiên | API tests, thiếu hàng/rollback/constraint; import internal giảm |
| **D — Ordering package** | Chuyển Ordering classes và công bố `ordering::placement`/`events` | `@ApplicationModuleTest(DIRECT_DEPENDENCIES)` và order characterization |
| **E — Event consumer** | Chuyển Fulfillment vào module riêng, công bố dependency `ordering::events` | Full integration test commit → event → picking task; idempotency |
| **F — Gate kiến trúc** | Khóa `allowedDependencies` hẹp, loại import nội bộ | `ApplicationModules.verify()` đạt; mutation import internal làm gate đỏ |
| **G — Tăng coverage** | Thêm transaction, retry, migration và concurrency scenarios | CI DB/integration quality gates, không phụ thuộc test order |

Không bắt buộc mọi dự án đều có cùng thứ tự; ví dụ nếu Payment đang giữ một transaction bắt buộc, ưu tiên characterization và ownership của Payment trước khi chuyển event consumer. Nhưng **mỗi PR phải nói rõ module nào được tạo, dependency nào bị loại và test nào chứng minh hành vi không đổi**.

### 10.2. Khi `verify()` đang đỏ vì legacy còn chưa chuyển hết

Trong giai đoạn đầu có thể có các package cũ tạo thành modules kỹ thuật hoặc chu trình. Không nên disable tất cả checks vô thời hạn. Một chiến lược quản lý chuyển tiếp:

1. Lưu danh sách vi phạm với caller, target, lý do và owner.
2. Phân biệt **vi phạm đã tồn tại** với **vi phạm mới được đưa vào**.
3. Sửa từng lát cắt và giảm số cạnh sai; không mở rộng quyền dependency chỉ để test xanh.
4. Khi package/contract của slice đã chốt, enforce `verify()` cho scope có thể kiểm tra và cuối cùng cho toàn ứng dụng.
5. Nếu buộc phải giữ ngoại lệ, ghi điều kiện và deadline chấm dứt; không biến open module thành trạng thái vĩnh viễn.

Với legacy lớn, có thể tổ chức branch theo bước A–F; mục tiêu cuối cùng vẫn là một bài kiểm tra kiến trúc **thật sự chạy trong CI**, chứ không phải một test chỉ tồn tại trên đĩa.

### 10.3. CI: không thay architecture test bằng compile/test xanh

```text
Pull request / branch
  |
  +-- Compile + unit/domain tests
  |      -> Không đổi business calculations và public API
  |
  +-- Module topology / architecture gate
  |      -> ApplicationModules.of(ShopApplication.class)
  |      -> inventory, ordering, fulfillment được nhận diện
  |      -> verify() bắt import internal, cycle, allowedDependencies sai
  |
  +-- Owner module tests
  |      -> Inventory STANDALONE
  |      -> DB constraint/transaction, API reserve contract
  |
  +-- Dependency module tests
  |      -> Ordering DIRECT_DEPENDENCIES
  |      -> Place order + stock reservation + OrderPlaced publication
  |
  +-- Full integration / event gate
  |      -> PostgreSQL Testcontainers
  |      -> Commit, rollback, AFTER_COMMIT consumer, retry/idempotency
  |
  +-- Repeatability
         -> Tests theo thứ tự khác và CI parallelism thật
         -> DB/schema/fixtures không đụng nhau
```

Chỉ coi các gate đạt nếu test **được runner discover và thực sự thực thi**. Ví dụ integration test hậu tố `IT` có thể cần cấu hình Maven Failsafe hoặc Gradle task chuyên biệt; test được tạo nhưng bị skip không phải bằng chứng.

### 10.4. Ghi chênh lệch trước/sau bằng một bảng nhỏ

| Tiêu chí | Trước khi tạo module | Sau khi refactor một slice |
| --- | --- | --- |
| Root package | `service`, `repository`, `domain` là module theo layer | `inventory`, `ordering`, `fulfillment` theo owner |
| Đường giữ hàng | Ordering gọi `StockRepository` | Ordering gọi `InventoryReservations` |
| Public API | Entity/repository có thể bị import mọi nơi | Named interface `inventory::reservations` |
| Event type | `OrderPlaced` nằm trong `events` chung mơ hồ | `ordering::events` có owner |
| Module discovery | Kỳ vọng không khớp mô hình thực | `ApplicationModules` nhận diện đúng identifiers |
| Architecture test | Fail hoặc không được chạy | `verify()` là gate bắt buộc |
| Module test | Full context hoặc mock quá rộng | Inventory `STANDALONE`, Ordering direct deps |
| Database/commit | Transaction không được kiểm chứng riêng | Producer commit/rollback và async consumer có tests |

Không kết luận “đã có application modules” chỉ vì tên package đẹp hơn. Phải đo **mức độ phụ thuộc và hành vi**, trong đó một test import lại class nội bộ cần bị từ chối bởi architecture gate.

### 10.5. Tiêu chí rollback một thay đổi refactor

Dừng hoặc hoàn tác slice đang sửa nếu:

- Sửa package làm một entrypoint không được Spring scan/wire.
- `ApplicationModules` nhận diện module khác dự kiến mà chưa hiểu nguyên nhân.
- Inventory cần bean từ Fulfillment trong `STANDALONE` dù mô hình owner không cho phép.
- Transaction đặt đơn không còn rollback Inventory khi thất bại, trái hợp đồng đã chốt.
- `OrderPlaced` được consumer quan sát như thành công dù producer rollback.
- Muốn làm `verify()` xanh phải expose entity/repository nội bộ hoặc cho phép vòng phụ thuộc.
- Migration/schema đổi không tương thích hoặc test DB bị thay bằng H2 mà không có lý do hợp lệ.

Những dấu hiệu này không được giải quyết chỉ bằng việc bỏ assertion, mock thêm repository hoặc bật `ALL_DEPENDENCIES`.

## 11. Bài thực hành tạo application modules và checklist nghiệm thu

### 11.1. Đề bài: từ layered legacy đến ba modules

Ứng dụng có:

```text
com.example.ticketing
├── TicketingApplication.java
├── controller/BookingController.java
├── service/
│   ├── BookingService.java
│   ├── SeatService.java
│   └── PaymentService.java
├── repository/
│   ├── BookingRepository.java
│   ├── SeatRepository.java
│   └── PaymentRepository.java
└── domain/
    ├── Booking.java
    ├── SeatHold.java
    └── Payment.java
```

`BookingService` hiện gọi `SeatRepository` trực tiếp để giữ ghế, tạo `Booking`, rồi `PaymentRepository.createPending(...)` trong cùng transaction. `PaymentService` gọi `BookingRepository.markPaid(...)` khi webhook thành công. Yêu cầu là đưa code hiện hữu vào `booking`, `seatallocation`, `payments` mà **không vô tình thay đổi giao dịch và idempotency**.

### 11.2. Các bước người học cần thực hiện

1. Xác nhận `TicketingApplication` nằm ở common root package `com.example.ticketing`, không có detection strategy đặc biệt.
2. Đề xuất target tree có `booking`, `seatallocation`, `payments`; chỉ ra entity/repository/internal của từng owner.
3. Tạo `@NamedInterface("holds")` ở `seatallocation.holds`, công bố `SeatHolds.hold(PlaceHold)`; không lộ `SeatRepository`.
4. Tạo `@NamedInterface("placement")` và contract `Bookings.place(...)` cho Booking; nếu Payment cần event, công bố `booking::events`.
5. Đặt `@ApplicationModule(allowedDependencies = "seatallocation::holds")` trên `booking/package-info.java` sau khi sửa caller.
6. Sửa đường `BookingService → SeatRepository` thành `BookingService → SeatHolds`, giữ đúng transaction semantics đã được characterization test bảo vệ.
7. Trước khi chuyển Payment sang async event, chứng minh callback cũ đang giữ những invariants nào; nếu tạo `PaymentPending` sau commit thay cho cùng transaction, đó là **thay đổi behavior** cần thiết kế riêng.
8. Viết test `ApplicationModules.of(TicketingApplication.class)` để assert các identifiers ứng viên; chạy `verify()` và phân loại mọi dependency vi phạm.
9. Viết `@ApplicationModuleTest(STANDALONE)` cho SeatAllocation: một ghế được giữ, lần giữ thứ hai bị từ chối, DB có đúng một hold hợp lệ.
10. Viết `@ApplicationModuleTest(DIRECT_DEPENDENCIES)` cho Booking: gọi API SeatAllocation, tạo Booking đúng và rollback toàn giao dịch khi lỗi sau bước giữ.
11. Viết integration test cho Payment callback/event và xử lý request lặp bằng DB constraint/consumer idempotency.
12. Thử thêm import `seatallocation.internal.SeatRepository` vào Booking trong branch test và xác nhận architecture gate **đỏ**; sau đó revert.

### 11.3. Ma trận kết quả bắt buộc

| Ca | Input/hành động | Bằng chứng đạt |
| --- | --- | --- |
| M1 — Topology | `ApplicationModules.of(TicketingApplication.class)` | Có `booking`, `seatallocation`, `payments` |
| M2 — Dependency rules | `modules.verify()` | Không cycle/truy cập internal trái rule |
| M3 — API owner | Booking gọi `SeatHolds` | Không import `SeatRepository` |
| M4 — Seat invariant | Hai request giữ cùng ghế | Không có hai holds hợp lệ |
| M5 — Transaction | Lỗi sau giữ ghế, trước Booking commit | Không có booking/hold mới bị commit sai |
| M6 — Event | Booking commit rồi publish event | Payload đúng, consumer sau commit khi được cấu hình |
| M7 — Retry | Payment callback cùng ID hai lần | Không ghi nhận thanh toán hai lần |
| M8 — Negative boundary | Tạm thêm dependency nội bộ | `verify()` thất bại như dự kiến |
| M9 — CI | Chạy module tests + integration test trên DB phù hợp | Tests được discover, có fixture và cleanup rõ |

### 11.4. Checklist trước khi kết luận “đã tạo ApplicationModules”

- [ ] Base package/application root được xác nhận, không đoán chỉ từ tên folder.
- [ ] Module được nhận diện từ **package thực**, không phải chỉ do tên class hoặc comment.
- [ ] Không còn coi `service/repository/domain` là các feature modules mong muốn.
- [ ] Aggregate, entity, repository và transaction logic có owner rõ ràng.
- [ ] Những caller ngoài module không inject repository/aggregate nội bộ.
- [ ] Public contract nằm ở module root API hoặc named interface được công bố đúng package.
- [ ] `@NamedInterface` dùng để cho phép đúng những kiểu cần thiết, không mở mọi package.
- [ ] `allowedDependencies` biểu đạt dependency hợp lệ, không dùng để hợp thức hóa chu trình.
- [ ] `ApplicationModules.of(...)` trả model với module identifiers mong đợi.
- [ ] `ApplicationModules.verify()` chạy thật và bắt được một import internal cố ý.
- [ ] Các đường native SQL/JPA association cross-module đã được review bổ sung vì `verify()` không biết mọi table ownership.
- [ ] Legacy characterization tests bảo vệ HTTP/API, transaction và dữ liệu trước khi đổi package.
- [ ] Module test được đặt **dưới package của module** đang kiểm tra.
- [ ] `STANDALONE` chạy module owner mà không đòi bean trái dependency.
- [ ] `DIRECT_DEPENDENCIES` chỉ nạp những dependency trực tiếp thực sự cần cho use case.
- [ ] Không dùng `ALL_DEPENDENCIES` để che cấu trúc module hoặc bean wiring sai.
- [ ] Spring bean/component/repository/entity scanning vẫn hoạt động sau khi move code.
- [ ] Database migration production được dùng trong test, không dựa vào `ddl-auto=create-drop` để che lỗi.
- [ ] Transaction rollback và event `AFTER_COMMIT` được test đúng ranh giới, không dùng `PublishedEvents` thay cho consumer completion.
- [ ] Testcontainers/DB schema có ownership và lifecycle rõ khi CI chạy nhiều class.
- [ ] Event consumers được bootstrap trong integration test phù hợp và idempotent với retry.
- [ ] CI chạy topology, architecture, owner module, dependency module và integration tests.
- [ ] Mỗi slice refactor có bằng chứng trước/sau; các ngoại lệ legacy có owner và kế hoạch loại bỏ.

**Kết luận:** Muốn **tạo `ApplicationModules` cho code hiện hữu**, hãy làm cho các package hiện có phản ánh đúng owner nghiệp vụ, công bố contract nhỏ ở ranh giới, và để Spring Modulith **suy ra mô hình từ chính mã đã tổ chức lại**. `ApplicationModules.of(...).verify()` xác nhận cấu trúc; `@ApplicationModuleTest` xác nhận module cùng dependency hợp lệ hoạt động; PostgreSQL/event integration tests bảo vệ những transaction và side effect mà Java dependency graph không thể chứng minh. Giá trị của refactor không nằm ở việc thêm annotation, mà ở chỗ **một dependency sai có thể bị chặn và một hành vi cũ quan trọng vẫn được kiểm chứng sau mỗi bước chuyển đổi**.

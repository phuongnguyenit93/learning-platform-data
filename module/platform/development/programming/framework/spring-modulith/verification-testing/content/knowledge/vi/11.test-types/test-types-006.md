# Architectural test cho dependency và package

> **Chương:** Test types  
> **Module đào tạo:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Xây dựng bài kiểm thử kiến trúc có thể chạy tự động bằng `ApplicationModules.verify()` để phát hiện phụ thuộc sai, vòng phụ thuộc và truy cập package không thuộc API của application module; bổ sung các quy tắc package bằng ArchUnit và đưa vào quality gate CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc cấu trúc package để xác định **application module**, API công khai và implementation nội bộ theo mô hình mặc định của Spring Modulith.
2. Viết một bài **architectural test** bằng JUnit gọi `ApplicationModules.of(...).verify()`, không cần khởi động toàn bộ Spring Boot application context.
3. Nhận diện ba lỗi phổ biến: phụ thuộc vòng, tham chiếu tới package `internal` của module khác và phụ thuộc nằm ngoài danh sách được cho phép.
4. Khai báo hợp đồng phụ thuộc với `@ApplicationModule(allowedDependencies = ...)` và công bố một package chọn lọc bằng `@NamedInterface`.
5. Phân biệt ranh giới truy cập **Java `public`** với ranh giới **module API** do Spring Modulith xác minh.
6. Sử dụng quy tắc ArchUnit riêng để kiểm tra quan hệ giữa các tầng hoặc package *bên trong* một module khi đó là yêu cầu kiến trúc bổ sung.
7. Tổ chức negative test và quality gate trong CI để chặn thay đổi phá vỡ kiến trúc, đồng thời phối hợp với `@ApplicationModuleTest` và integration test nhằm phát hiện hồi quy hành vi.

**Kết quả mong đợi:** Một developer vô tình thêm import từ module `orders` vào JPA entity nội bộ của `inventory`, hoặc tạo vòng phụ thuộc giữa hai module, sẽ nhận lỗi từ bài kiểm thử kiến trúc ngay trên pull request, trước khi mã được tích hợp.

## 2. Architectural test kiểm chứng điều gì?

Một ứng dụng Spring Boot có thể chạy đúng về mặt chức năng nhưng các module ngày càng phụ thuộc chéo: controller của module này inject repository của module khác, service nhập DTO nội bộ từ package khác hoặc hai module cùng tham chiếu implementation của nhau. Các lỗi này có thể không bộc lộ trong unit test và thậm chí không làm một luồng E2E thất bại ngay lập tức. Tuy nhiên, chúng khiến việc phát triển, refactor, kiểm thử độc lập và tách dịch vụ sau này khó khăn hơn.

**Architectural test** kiểm tra cấu trúc chương trình như một hợp đồng có thể thực thi:

- Module nào được xem là đơn vị chức năng?
- Module nào đang phụ thuộc module nào?
- Phụ thuộc đó có tạo vòng hay không?
- Module gọi có truy cập đúng **API công khai** của module được gọi không?
- Nếu kiến trúc giới hạn các dependency được phép, mã nguồn có tuân thủ danh sách đó không?
- Các tầng trong cùng module có đi đúng chiều, ví dụ HTTP adapter không trực tiếp truy cập persistence adapter?

Sơ đồ mô hình lành mạnh minh họa:

~~~mermaid
flowchart LR
    O["orders<br/>application module"] --> S["inventory::spi<br/>named interface"]
    N["notifications<br/>application module"] --> OA["orders API<br/>OrderPlaced"]
    S --> I["inventory.internal<br/>implementation"]
    subgraph B["Module inventory"]
        S
        I
    end
~~~

Trong mô hình này, `orders` sử dụng một **port** của `inventory` qua named interface, còn `notifications` chỉ nhận sự kiện được công bố ở API `orders`. Quan hệ dependency trong mã nguồn có hướng rõ ràng.

**Điểm quan trọng:** Architectural test xác minh **cấu trúc**. Nó chưa xác nhận việc inject bean thành công, transaction được commit đúng, repository truy vấn chính xác hoặc event listener xử lý thành công. Những câu hỏi đó thuộc `@ApplicationModuleTest` và các integration test tương ứng.

## 3. Cách Spring Modulith nhận diện module và package

Giả sử ứng dụng có package gốc `com.example.shop` với class khởi động:

**`src/main/java/com/example/shop/ShopApplication.java`**

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Với **cơ chế phát hiện module mặc định**, những package con trực tiếp bên dưới package ứng dụng chính có thể trở thành application module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/                           # application module "orders"
│   ├── package-info.java
│   ├── PlaceOrder.java                # API mặc định
│   ├── OrderPlaced.java              # API mặc định
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/
│           └── OrderRepository.java
├── inventory/                        # application module "inventory"
│   ├── package-info.java
│   ├── spi/
│   │   ├── package-info.java          # named interface
│   │   └── StockReservation.java
│   └── internal/
│       ├── InventoryReservationService.java
│       └── persistence/
│           └── InventoryJpaEntity.java
└── notifications/                    # application module "notifications"
    ├── OrderNotification.java        # API mặc định
    └── internal/
        └── OrderPlacedListener.java
~~~

Đây là cách tổ chức minh họa; Spring Modulith còn hỗ trợ chiến lược phát hiện module được tùy biến. Nếu dự án dùng chiến lược khác, phải xác nhận mô hình module thực tế trước khi kết luận package nào thuộc module nào.

### API mặc định và phần nội bộ

| Vị trí class | Ví dụ | Ý nghĩa đối với module khác |
| --- | --- | --- |
| Root package của module | `orders.OrderPlaced` | Thuộc API mặc định của `orders` |
| Package con chưa được công bố | `orders.internal.OrderApplicationService` | Implementation nội bộ; module khác không được truy cập trực tiếp |
| Repository nằm sâu trong `internal` | `inventory.internal.persistence.InventoryJpaEntity` | Không phải API liên module |
| Package con khai báo `@NamedInterface` | `inventory.spi.StockReservation` | Có thể trở thành API có tên, dùng theo hợp đồng được phép |

**`public` trong Java không đồng nghĩa với “public API” của Spring Modulith.** Một class `public InventoryJpaEntity` vẫn có thể nằm trong package nội bộ và Java compiler vẫn cho module khác import. Spring Modulith kiểm tra ranh giới kiến trúc ở mức mô hình application module, giúp phát hiện sự phụ thuộc không hợp lệ dù code vẫn biên dịch.

Trong nội bộ **cùng** application module, các component có thể truy cập implementation khác của module theo quy tắc Java thông thường. Nếu còn muốn áp đặt quy tắc tầng nội bộ như controller không dùng repository trực tiếp, cần một quy tắc ArchUnit riêng (mục 10).

## 4. Bài architectural test tối thiểu bằng ApplicationModules.verify()

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void application_modules_follow_architecture_rules() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        modules.verify();
    }
}
~~~

`ApplicationModules.of(ShopApplication.class)` xây dựng mô hình các application module dựa trên package gốc của ứng dụng và cấu hình liên quan. `verify()` áp dụng các quy tắc kiến trúc của Spring Modulith, bao gồm kiểm tra **vòng phụ thuộc**, **truy cập ngoài API module** và **các giới hạn phụ thuộc được khai báo**.

Bài test này:

- Chạy bằng JUnit thông thường, không nhất thiết phải khởi động Spring Boot context hoặc kết nối database.
- Không cần `@SpringBootTest` hoặc `@ApplicationModuleTest`; thông tin cần thiết cho kiểm tra kiến trúc được phân tích từ class/package.
- Có thể chạy cùng các unit test trong job `test` của CI.
- Thất bại khi mô hình dependency trái quy tắc và trả về thông tin giúp lần theo nguồn phụ thuộc.

Một khai báo dependency minh họa với Gradle Kotlin DSL, **trong dự án đã quản lý phiên bản Spring Boot/Spring Modulith tương thích**:

~~~kotlin
dependencies {
    implementation("org.springframework.modulith:spring-modulith-starter-core")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Thư viện chứa `ApplicationModules` có thể được đưa vào thông qua các dependency Modulith mà dự án đã sử dụng; chỉ cần khai báo đủ cho mã thực tế và tránh khai báo trùng. Đối với Maven, tương ứng là dependency quản lý qua Maven BOM và lệnh `./mvnw test`. Phần code trên là ví dụ minh họa cấu hình test, chưa phải một build script hoàn chỉnh.

> **Điều kiện quan trọng:** Mô hình package/module phải được phát hiện đúng trước khi `verify()` có ý nghĩa. Nếu một phần mã nằm ngoài package gốc hoặc có cấu hình module đặc biệt, hãy kiểm tra phạm vi phân tích và bổ sung quy tắc phù hợp.

## 5. Kiểm chứng dependency giữa các module

Một **dependency giữa hai application module** hình thành khi code ở module này tham chiếu kiểu hoặc thành phần của module khác. Ví dụ service của `orders` sử dụng interface của `inventory`.

~~~java
// src/main/java/com/example/shop/orders/internal/OrderApplicationService.java
package com.example.shop.orders.internal;

import com.example.shop.inventory.spi.StockReservation;
import org.springframework.stereotype.Service;

@Service
class OrderApplicationService {

    private final StockReservation reservation;

    OrderApplicationService(StockReservation reservation) {
        this.reservation = reservation;
    }

    boolean placeOrder(String sku, int quantity) {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
        return reservation.reserve(sku, quantity);
    }
}
~~~

Về cấu trúc, mã này tạo một cạnh **`orders → inventory`** vì `orders` cần interface `StockReservation` thuộc module `inventory`. Đây có thể là quan hệ hợp lệ nếu interface được công bố và dependency được cho phép.

### Ma trận dependency dự kiến

| Module nguồn | Module đích | Hợp đồng mong muốn | Kết quả kiến trúc kỳ vọng |
| --- | --- | --- | --- |
| `orders` | `inventory` | Chỉ dùng `inventory::spi` | Hợp lệ khi được khai báo và trỏ đúng named interface |
| `notifications` | `orders` | Chỉ dùng event/API công khai | Hợp lệ khi không vi phạm các giới hạn khác |
| `orders` | `notifications.internal` | Không có hợp đồng cho truy cập nội bộ | Vi phạm |
| `inventory` | `orders` | Không cần phụ thuộc ngược cho luồng đặt hàng minh họa | Có nguy cơ tạo vòng với `orders → inventory` |
| `orders` | `inventory.internal.persistence` | Cấm truy cập JPA implementation | Vi phạm |

Cần hiểu rằng Spring Modulith phân tích **quan hệ phụ thuộc tĩnh trong mã nguồn/class**. Nó không thể suy ra mọi hợp đồng gọi động chỉ được ghi dưới dạng chuỗi, cấu hình bên ngoài hay reflection. Khi ứng dụng có giao tiếp qua HTTP, broker hoặc những cơ chế không tạo reference trực tiếp ở mã Java, còn cần contract/integration test phù hợp.

## 6. Ba tình huống khiến architectural test thất bại

### 6.1. Truy cập package nội bộ của module khác

Một developer muốn “tiết kiệm” bước gọi qua API của `inventory` nên sử dụng JPA entity trực tiếp:

~~~java
// KHÔNG HỢP LỆ: bên trong orders lại import
// implementation riêng của module inventory.
import com.example.shop.inventory.internal.persistence.InventoryJpaEntity;
~~~

Ngay cả khi `InventoryJpaEntity` được khai báo Java `public`, import này vẫn vượt ranh giới module. Khi `ModuleArchitectureTest` chạy, `verify()` phải phát hiện quan hệ tới một kiểu không nằm trong API được công bố của `inventory`.

**Cách sửa:** Module `inventory` công bố một API hoặc named interface phù hợp với use case, ví dụ `StockReservation`. Module `orders` chỉ nhận interface đó qua constructor, không thao tác trực tiếp với entity/repository của `inventory`.

Không chữa bằng cách tự chuyển toàn bộ package `internal.persistence` thành API. Việc công bố implementation nội bộ khiến các module bị ghép chặt vào cơ chế lưu trữ.

### 6.2. Vòng phụ thuộc module

Giả sử `orders` dùng `inventory.StockReservation`, rồi developer thêm mã trong `inventory` tham chiếu một application service của `orders`:

~~~mermaid
flowchart LR
    O["orders"] -->|StockReservation| I["inventory"]
    I -->|tham chiếu orders API| O
~~~

Đây là vòng **`orders → inventory → orders`**. Ngay cả khi mỗi import chỉ trỏ tới API công khai và được Java compiler chấp nhận, hai module không còn quan hệ phụ thuộc một chiều rõ ràng. Kiểm tra kiến trúc của Spring Modulith sẽ coi vòng dependency là vi phạm.

Cách xử lý có thể là:

1. Chuyển orchestration sang module phù hợp với trách nhiệm nghiệp vụ.
2. Đưa một hợp đồng hai bên thực sự dùng chung vào vị trí kiến trúc được phép, nếu thiết kế xác nhận sự phụ thuộc đó là cần thiết.
3. Dùng sự kiện một chiều để module quan tâm tự phản ứng, tránh producer import implementation của consumer.
4. Phân tách trách nhiệm trước khi thêm interface mới; **đưa interface vào chỗ khác một cách hình thức** có thể chỉ che giấu vấn đề thiết kế.

Sự kiện không xóa mọi phụ thuộc: consumer vẫn phụ thuộc vào kiểu event thuộc API của producer. Hãy xét **chiều tham chiếu trong mã** thay vì chỉ nhìn chiều truyền thông điệp khi chạy.

### 6.3. Phụ thuộc tới module ngoài danh sách cho phép

Một module có thể dùng đúng package API nhưng vẫn không được phép phụ thuộc vào module đó theo quyết định kiến trúc.

Ví dụ `orders` chỉ được phép phụ thuộc `inventory::spi`. Sau đó developer import `com.example.shop.pricing.PricePolicy` từ một module `pricing` khác. Kiểu `PricePolicy` có thể là API hợp lệ của `pricing`, nhưng **`orders → pricing` vẫn trái whitelist** nếu kiến trúc không khai báo quan hệ này.

Phân biệt hai câu hỏi:

- **API visibility:** Kiểu đích có thuộc giao diện được công bố của module đích hay không?
- **Allowed dependency:** Module nguồn có được phép phụ thuộc vào module đích/giao diện đó hay không?

Một dependency có thể vượt qua kiểm tra thứ nhất nhưng thất bại ở kiểm tra thứ hai.

## 7. Ràng buộc quan hệ bằng @ApplicationModule(allowedDependencies)

Nếu không định nghĩa danh sách dependency được phép, kiểm tra kiến trúc vẫn có giá trị với các quy tắc cơ bản về module API và vòng phụ thuộc. Để chính sách kiến trúc trở nên **cụ thể và bắt buộc hơn**, có thể khai báo whitelist dependency tại `package-info.java` của module.

Ví dụ module `orders` chỉ được sử dụng named interface `spi` của `inventory`:

**`src/main/java/com/example/shop/orders/package-info.java`**

~~~java
@ApplicationModule(allowedDependencies = "inventory::spi")
package com.example.shop.orders;

import org.springframework.modulith.ApplicationModule;
~~~

Lưu ý:

- `allowedDependencies` là **tên module/giao diện trong mô hình Modulith**, không phải tên class Java.
- Mẫu `inventory::spi` tham chiếu một **named interface** mang tên `spi` của module `inventory`.
- Nếu thêm phụ thuộc tới module không nằm trong whitelist, `verify()` sẽ báo vi phạm.
- Cần cập nhật whitelist khi thiết kế kiến trúc thực sự thay đổi và thay đổi đó đã được review; không thêm tên module vào whitelist chỉ để test xanh.
- Giới hạn bằng whitelist không miễn trừ quy tắc API hoặc quy tắc chống vòng phụ thuộc.

**Điểm dễ nhầm:** Khai báo `allowedDependencies = "inventory::spi"` chưa đủ nếu package `inventory.spi` chưa được công bố bằng `@NamedInterface`. Hai đầu của hợp đồng phải khớp.

Trong dự án thực tế, các package API bổ sung hoặc các dependency được cho phép có thể khác ví dụ. Hãy dựa vào kiến trúc đã thống nhất để quyết định danh sách, thay vì sao chép nguyên mẫu chỉ có một dependency.

## 8. Công bố package có chọn lọc bằng @NamedInterface

Một application module có thể cần cung cấp một tập interface cho module khác mà không đặt mọi kiểu ở root package. `@NamedInterface` cho phép công bố rõ **một package API có tên**.

**`src/main/java/com/example/shop/inventory/spi/package-info.java`**

~~~java
@NamedInterface("spi")
package com.example.shop.inventory.spi;

import org.springframework.modulith.NamedInterface;
~~~

**`src/main/java/com/example/shop/inventory/spi/StockReservation.java`**

~~~java
package com.example.shop.inventory.spi;

public interface StockReservation {
    boolean reserve(String sku, int quantity);
}
~~~

Class implementation có thể nằm bên trong `inventory.internal`:

**`src/main/java/com/example/shop/inventory/internal/InventoryReservationService.java`**

~~~java
package com.example.shop.inventory.internal;

import org.springframework.stereotype.Service;
import com.example.shop.inventory.spi.StockReservation;

@Service
class InventoryReservationService implements StockReservation {

    @Override
    public boolean reserve(String sku, int quantity) {
        // Minh họa hợp đồng; triển khai thật phải xử lý
        // tồn kho và transaction theo nghiệp vụ ứng dụng.
        return quantity > 0;
    }
}
~~~

Giờ `orders.internal.OrderApplicationService` có thể phụ thuộc vào `inventory.spi.StockReservation` theo whitelist ở mục 7. Spring vẫn có thể cung cấp bean của implementation ở module `inventory` khi runtime cần, còn architectural test chỉ quan sát **quan hệ kiểu được tham chiếu**.

### Named interface và API mặc định

| Thiết kế | Cách dùng | Tác động |
| --- | --- | --- |
| Kiểu nằm trong root module | `inventory.SomePublicType` | Thuộc API mặc định của module |
| Package con có `@NamedInterface("spi")` | `inventory.spi.StockReservation` | Được công bố như named interface `inventory::spi` |
| Package con không công bố | `inventory.internal.InventoryReservationService` | Nội bộ; không được module khác truy cập |
| Module nguồn có whitelist | `orders: inventory::spi` | Chỉ định rõ đường dependency được phép theo hợp đồng |

Không dùng named interface để biến toàn bộ implementation thành API. Nó nên mô tả **hợp đồng ổn định** như port, interface, DTO hoặc sự kiện mà module khác có lý do chính đáng để biết.

## 9. Kiểm thử sự kiện và phụ thuộc theo package

Một ví dụ khác là module `notifications` nhận `OrderPlaced` từ module `orders`.

**`src/main/java/com/example/shop/orders/OrderPlaced.java`**

~~~java
package com.example.shop.orders;

public record OrderPlaced(long orderId) {}
~~~

**`src/main/java/com/example/shop/notifications/internal/OrderPlacedListener.java`**

~~~java
package com.example.shop.notifications.internal;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;

@Component
class OrderPlacedListener {

    @EventListener
    void on(OrderPlaced event) {
        // Phản ứng với event theo nghiệp vụ notifications.
    }
}
~~~

Code của `notifications` import `orders.OrderPlaced`, nên có dependency **`notifications → orders`**. Producer `orders` không import listener của `notifications`. Đây là một cách giảm ghép nối giữa hai module khi giao tiếp qua event.

Tuy nhiên, việc import đúng API chỉ chứng minh **sự phụ thuộc về cấu trúc hợp lệ**. Nó **không** chứng minh:

- Listener được Spring khởi tạo khi ứng dụng chạy.
- Event được publish với đúng payload.
- Listener thực thi sau commit theo pha mong muốn.
- Lỗi asynchronous, retry và publication registry được xử lý đúng.
- Database của module nhận được cập nhật.

Các tình huống đó cần `@ApplicationModuleTest`, integration test giữa module, `PublishedEvents`, `Scenario` hoặc E2E test với hạ tầng phù hợp. `ApplicationModules.verify()` là một quality gate kiến trúc **bổ sung**, không phải bản thay thế cho kiểm thử sự kiện.

## 10. Khi nào cần ArchUnit tùy chỉnh?

`ApplicationModules.verify()` tập trung vào **quan hệ giữa application module** và các quy tắc mô hình module. Một số quy ước nội bộ không nhất thiết là quy tắc Modulith mặc định, ví dụ:

- HTTP controller thuộc `internal.web` không được phụ thuộc trực tiếp JPA repository/entity thuộc `internal.persistence`.
- Domain code không được phụ thuộc Spring MVC.
- Classes ở `internal.application` không được truy cập HTTP request/response DTO.
- Những component đặt tên `*Controller` phải nằm trong package web theo convention dự án.

Các quy tắc đó có thể biểu đạt bằng **ArchUnit**; chỉ thêm khi chúng phản ánh một quyết định kiến trúc có giá trị thực tế.

### 10.1. Ví dụ rule: web adapter không đi thẳng tới persistence adapter

**`src/test/java/com/example/shop/AdapterPackageArchitectureTest.java`**

~~~java
package com.example.shop;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

@AnalyzeClasses(packages = "com.example.shop")
class AdapterPackageArchitectureTest {

    @ArchTest
    static final ArchRule web_must_not_depend_on_persistence =
            noClasses()
                    .that()
                    .resideInAPackage("..internal.web..")
                    .should()
                    .dependOnClassesThat()
                    .resideInAPackage("..internal.persistence..");
}
~~~

Rule này xem các class nằm ở package khớp mẫu `..internal.web..`, sau đó kiểm tra chúng không có dependency tĩnh tới class ở package khớp `..internal.persistence..`.

**Điểm cần hiểu:**

1. Một controller trong cùng module có thể tham chiếu repository mà `ApplicationModules.verify()` **không phản đối**, vì đó không phải dependency vượt module.
2. Rule ArchUnit bổ sung ngăn riêng kiểu phụ thuộc trực tiếp này theo quyết định phân tầng của nhóm.
3. Tên package trong pattern phải khớp cách đặt package thực tế. Nếu dự án dùng `adapter.inbound`/`adapter.outbound`, cần sửa pattern tương ứng.
4. Rule kiểm tra quan hệ class tại bytecode, không thay thế test validation hay logic của repository.

Để sử dụng `@AnalyzeClasses` và `@ArchTest` với JUnit 5, bảo đảm có dependency `com.tngtech.archunit:archunit-junit5` tương thích. Phiên bản có thể do BOM quản lý hoặc cần được chỉ định theo build của dự án.

### 10.2. Tránh viết quy tắc thừa hoặc quá rộng

Không nên đưa mọi convention vào ArchUnit mà không cân nhắc. Một rule như “không class nào được phụ thuộc package `..internal..`” sẽ cấm cả **những class cùng module** cộng tác với implementation của chính chúng, dẫn đến false positive.

Rule tốt có:

- **Mục tiêu rõ:** ngăn một kiểu quan hệ làm hỏng kiến trúc.
- **Phạm vi phù hợp:** áp dụng đúng package/module và hướng phụ thuộc.
- **Thông báo dễ hành động:** developer biết phải thay import bằng API hoặc port nào.
- **Ví dụ thất bại có chủ đích:** thêm một dependency vi phạm để chắc chắn rule không vô tình luôn xanh.

Khi ý định là bảo vệ ranh giới giữa application module, **ưu tiên `ApplicationModules.verify()`**; chỉ bổ sung ArchUnit trực tiếp cho quy tắc mà mô hình Modulith chưa thể hiện.

## 11. Tạo “red test” để chứng minh quality gate bắt lỗi

Một bài architectural test chỉ có ý nghĩa nếu quy tắc được thiết lập và phát hiện đúng dependency. Bài thực hành có thể xác minh bằng một thay đổi cố ý, sau đó hoàn nguyên:

| Biến thể | Thay đổi có chủ đích | Kỳ vọng |
| --- | --- | --- |
| Không vi phạm | `orders` inject `inventory.spi.StockReservation` với whitelist `inventory::spi` | `verify()` xanh |
| Package nội bộ | `orders` import một class `public` dưới `inventory.internal.persistence` | `verify()` đỏ |
| Sai whitelist | `orders` import API `pricing.PricePolicy` nhưng chỉ cho phép `inventory::spi` | `verify()` đỏ |
| Vòng dependency | `inventory` thêm import đến API `orders` khi `orders` đã phụ thuộc `inventory` | `verify()` đỏ |
| Sai tầng nội bộ | `orders.internal.web.OrderController` import `orders.internal.persistence.OrderRepository` | Rule ArchUnit ở mục 10 đỏ |
| Không có lỗi kiến trúc nhưng sai nghiệp vụ | `StockReservation.reserve(...)` trả sai kết quả | Cần unit/module/integration test mới phát hiện |

Quy trình thí nghiệm:

1. Chạy `ModuleArchitectureTest` và rule ArchUnit trên phiên bản hợp lệ: đều xanh.
2. Chỉ thêm **một** vi phạm trong nhánh thực hành.
3. Chạy lại đúng test: phải thất bại và chỉ ra nguồn dependency.
4. Đọc thông tin lỗi để nhận diện hai module hoặc hai package liên quan.
5. Thay import trái quy tắc bằng API/port phù hợp và chạy lại test.
6. Hoàn nguyên các chỉnh sửa cố ý trước khi commit.

Không giữ những import sai hoặc bỏ qua test đỏ chỉ để trình diễn. Trên CI, thử nghiệm “phải fail” nên nằm ở bài thực hành kiểm soát được, không nằm vĩnh viễn trong source production.

### Không cần khởi động Spring để bắt lỗi module

Nếu `OrderApplicationService` import `InventoryJpaEntity` từ module khác, lỗi kiến trúc tồn tại ngay trong dependency graph. Chạy `@SpringBootTest` để bắt nó là chi phí không cần thiết. Architectural test nhanh hơn vì tập trung đọc cấu trúc class và package.

## 12. Đọc kết quả thất bại và sửa đúng nguyên nhân

Thông báo cụ thể phụ thuộc vào phiên bản Spring Modulith/ArchUnit và rule đang chạy. Khi test đỏ, dùng luồng phân tích sau:

1. **Xác định module nguồn:** class nào vừa tạo dependency?
2. **Xác định đích:** kiểu thuộc module/package nào?
3. **Xác định quy tắc:** truy cập API, whitelist, vòng dependency hay rule package tùy chỉnh?
4. **Xem nhu cầu nghiệp vụ:** caller có thật sự cần biết implementation của module kia không?
5. **Đổi quan hệ:** dùng module API, named interface, event hoặc chuyển orchestration đến module phù hợp.
6. **Chạy lại architecture test và các behavior test liên quan.**

Ví dụ, nếu `orders.internal.OrderApplicationService` import `inventory.internal.persistence.InventoryJpaEntity`:

- Phần sai nằm ở **hợp đồng truy cập nội bộ**, không phải do Java compiler.
- Đổi tên `InventoryJpaEntity` thành `PublicInventoryJpaEntity` không giúp ích nếu class vẫn nằm ở package nội bộ.
- Di chuyển entity lên root package để test xanh là thay đổi ranh giới API lớn, cần quyết định kiến trúc chứ không phải giải pháp vá nhanh.
- Giải pháp thường đúng hơn là công bố `inventory.spi.StockReservation` rồi chuyển nghiệp vụ truy cập tồn kho vào implementation của module `inventory`.

Nếu báo vòng dependency, cần xem lại **cả hai hướng phụ thuộc**, không chỉ một class được báo. Việc chỉnh một import có thể làm mất vòng nhưng vẫn còn một dependency không nên có.

## 13. Giới hạn của kiểm chứng package/dependency tĩnh

Architectural test không nên được mô tả quá khả năng. `ApplicationModules.verify()` hữu ích nhưng nó không chứng minh tất cả ràng buộc triển khai:

| Điều cần biết | `verify()` có đủ không? | Loại test bổ sung |
| --- | --- | --- |
| Module không tạo vòng và dùng API hợp lệ | Có, trong mô hình được phát hiện và các quy tắc được cấu hình | Có thể tăng bằng dependency whitelist |
| Class `internal` bị module khác tham chiếu tĩnh | Có, nếu nằm trong phạm vi mô hình kiểm tra | Không cần HTTP test để phát hiện import |
| Service/Repository được Spring inject đúng | Không | `@ApplicationModuleTest` |
| MVC route và JSON contract đúng | Không | `@WebMvcTest` hoặc E2E |
| Query JPA trả dữ liệu chính xác | Không | `@DataJpaTest`/integration |
| Event thực sự được publish với payload đúng | Không | `PublishedEvents`/module test |
| Listener sau commit xử lý thành công | Không | Integration test với transaction/event |
| Reflection và cấu hình động có tạo dependency ngầm | Không bảo đảm | Integration test và review cấu hình |
| Dịch vụ ngoài/HTTP/broker tương thích | Không | Contract test/E2E phù hợp |

Nếu repository tổ chức module theo **chiến lược khác mặc định**, việc phát hiện sai module có thể làm test bỏ sót dependency. Đừng chỉ dựa vào việc `verify()` trả về xanh; hãy kiểm tra một lần rằng các package/module mong đợi đều được mô hình hóa.

### Cẩn trọng với package “shared” hoặc “common”

Nếu `com.example.shop.common` là một package con trực tiếp của application root, nó **có thể được nhận diện như một module** theo chiến lược mặc định. Đặt mọi DTO, utility và interface vào `common` dễ làm nhiều module phụ thuộc tập trung vào đó và khó quản trị hợp đồng. Hãy chủ động xác định cái gì là API sở hữu bởi module nào, phần nào thật sự là shared library và phần nào cần một module riêng.

### Cẩn trọng với giới hạn tại thời điểm biên dịch

Một reference qua annotation, generic type, inherited type hoặc constructor parameter đều có thể tạo dependency được kiểm tra. Ngược lại, những quan hệ chỉ được nêu bằng string, SQL script, reflection hoặc endpoint URL có thể không xuất hiện như reference tĩnh tương ứng. Test integration/contract vẫn cần thiết để bảo vệ các kết nối đó.

## 14. Kết hợp với @ApplicationModuleTest và kiểm thử hành vi

Trong dự án Spring Modulith, ba nhóm câu hỏi thường đi cùng nhau:

~~~mermaid
flowchart TB
    Arch["Architecture test<br/>ApplicationModules.verify()"] --> Rule["Dependency và API boundary đúng"]
    Mod["Module test<br/>@ApplicationModuleTest"] --> Wiring["Bean wiring và nghiệp vụ module đúng"]
    Int["Integration/E2E test"] --> Flow["Transaction, event và luồng liên module đúng"]
    Rule --> Gate["CI quality gate"]
    Wiring --> Gate
    Flow --> Gate
~~~

Ví dụ `orders` gọi `inventory.spi.StockReservation`:

- `ApplicationModules.verify()` chứng minh `orders` phụ thuộc vào named interface được phép, không import package nội bộ và không tạo vòng.
- Unit test của `OrderApplicationService` dùng fake `StockReservation` để xác minh phản ứng khi hết hàng.
- `@ApplicationModuleTest` kiểm chứng Spring bean của module được lắp ghép theo bootstrap mode thích hợp, với dependency thật hoặc được thay thế có chủ đích.
- Integration test kiểm tra transaction và việc gọi port thật của `inventory` khi hành vi cần đi xuyên nhiều module.
- Nếu có event `OrderPlaced`, module/event test kiểm chứng publish và listener, tách riêng pha sau commit hoặc giao tiếp bất đồng bộ theo yêu cầu.

Architectural test xanh **không tự cấp quyền bỏ qua** các test khác; nó trả lời một câu hỏi không thể suy ra từ kết quả test nghiệp vụ.

## 15. Đưa architectural test vào quality gate CI

Vì architectural test thường không cần database hay HTTP server, nó phù hợp chạy **trên mọi pull request**. Một pipeline có thể thực hiện:

1. Build/compile source và test code.
2. Chạy unit test và architecture verification.
3. Chạy slice test và `@ApplicationModuleTest`.
4. Chạy integration/E2E test cần database hoặc event infrastructure, có thể ở job riêng nếu chi phí lớn.
5. Chỉ cho phép merge nếu các job bắt buộc đều xanh.

Nếu dự án dùng Gradle, ví dụ lệnh chạy test JUnit là:

~~~bash
./gradlew test
~~~

Trên Windows, wrapper tương ứng có thể là `gradlew.bat test`. Nếu tách architecture test thành test suite/job riêng, hãy cấu hình `include`/tag đúng để **không vô tình bỏ qua** `ModuleArchitectureTest`. Trường hợp build bị fail vì package violation, kết quả này phải là lỗi bắt buộc xử lý như lỗi unit test.

### Tiêu chí cho quality gate tốt

| Tiêu chí | Cách đánh giá |
| --- | --- |
| Phát hiện sai ranh giới | Import `inventory.internal` từ `orders` làm test đỏ |
| Phát hiện dependency vòng | Thêm cạnh ngược `inventory → orders` làm test đỏ |
| Kiểm tra whitelist | Import module nằm ngoài `allowedDependencies` làm test đỏ |
| Quy tắc package nội bộ | Controller gọi repository trực tiếp làm ArchUnit rule đỏ nếu đã có rule |
| Dễ chạy | Test không đòi hạ tầng database/broker cho việc kiểm tra tĩnh |
| Dễ sửa | CI log cho biết class nguồn, class đích, rule vi phạm |
| Không bỏ sót | Test thực sự được chạy trên pull request và là điều kiện merge |

Đừng “chữa” lỗi gate bằng cách xóa test, tắt rule hoặc thêm mọi module vào whitelist. Nếu kiến trúc phải thay đổi vì nghiệp vụ mới, hãy cập nhật hợp đồng module có chủ đích, review tác động và giữ test làm cơ chế bảo vệ thiết kế mới.

## 16. Các lỗi và nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `verify()` xanh dù code rất ghép chặt | Các dependency đều nằm trong **cùng module**, hoặc cấu trúc module chưa được phát hiện như kỳ vọng | Xem package root/module detection, thêm rule ArchUnit nội bộ khi có yêu cầu |
| Có import Java `public` nhưng architecture test đỏ | `public` Java không đồng nghĩa API Modulith | Dùng API root hoặc named interface |
| `allowedDependencies` báo sai dù import `inventory.spi` | Named interface `spi` chưa khai báo hoặc tên sai | Kiểm tra `package-info.java` và tên `inventory::spi` |
| Module khác dùng một DTO hợp lệ nhưng vẫn đỏ | Module nguồn không được phép phụ thuộc module đích theo whitelist | Rà soát và chỉ cập nhật whitelist nếu thiết kế cho phép |
| Test đỏ vì vòng dependency | Hai module tham chiếu ngược chiều | Chuyển orchestration, port hoặc event cho đúng chiều |
| Test xanh nhưng startup thiếu bean | Structural verification không khởi tạo Spring | Viết `@ApplicationModuleTest` hoặc integration test |
| Test xanh nhưng listener không chạy | `verify()` không kiểm tra giao sự kiện runtime | Kiểm tra Spring context, listener và transaction trong integration test |
| Rule ArchUnit báo sai class cùng module | Pattern package quá rộng | Giới hạn package và chiều phụ thuộc theo hợp đồng |
| Bài kiểm tra không được CI chạy | Sai cấu hình JUnit discovery, include/exclude hoặc module build | Kiểm tra test task và bắt buộc job architecture gate |

Thông báo lỗi thực tế có thể khác tùy phiên bản thư viện và cấu trúc package. Trước khi đổi mã, hãy xác nhận quy tắc đang áp dụng đúng với mô hình module của dự án.

## 17. Bài thực hành

### Bài 1 — Xây dựng mô hình hợp lệ

Tạo cấu trúc `orders` và `inventory` như mục 3. Công bố `inventory.spi.StockReservation` bằng `@NamedInterface("spi")`, rồi khai báo:

~~~java
@ApplicationModule(allowedDependencies = "inventory::spi")
package com.example.shop.orders;

import org.springframework.modulith.ApplicationModule;
~~~

Viết `ModuleArchitectureTest` gọi `ApplicationModules.of(ShopApplication.class).verify()` và xác nhận test xanh.

### Bài 2 — Phát hiện truy cập package không hợp lệ

Tạo một class `public` trong `inventory.internal.persistence`, rồi cho service của `orders` import class đó. Chạy lại test và ghi nhận:

- Module nguồn/đích.
- Package đích có được công bố hay không.
- Lý do không nên sửa bằng cách phơi bày JPA entity ra API.

Khôi phục lại code hợp lệ bằng `StockReservation` hoặc API được thiết kế phù hợp.

### Bài 3 — Phát hiện vòng dependency

Khi `orders → inventory` đã tồn tại, thêm một import từ implementation của `inventory` tới kiểu API của `orders` để tạo chiều ngược. Chạy lại `verify()`, xác định vòng và đề xuất cách loại bỏ chiều phụ thuộc không cần thiết. Chỉ coi bài tập hoàn thành khi test xanh trở lại mà không bỏ rule.

### Bài 4 — Kiểm tra whitelist

Thêm module `pricing` có một interface `PricePolicy` ở package root. Cho `orders` tham chiếu nó nhưng giữ `allowedDependencies = "inventory::spi"`. Kiểm tra test đỏ và giải thích **vì sao dùng đúng API vẫn có thể vi phạm whitelist**.

### Bài 5 — Quy tắc package bổ sung bằng ArchUnit

Tạo một `OrderController` trong `orders.internal.web` và một `OrderRepository` trong `orders.internal.persistence`. Viết rule ArchUnit ở mục 10. Cho controller import repository và xác nhận rule đỏ, sau đó chuyển controller sang gọi application API/port của module.

### Câu hỏi tự đánh giá

1. Java compiler đã kiểm soát `public/private`. Vì sao vẫn cần Spring Modulith kiểm tra API của module?
2. `ApplicationModules.verify()` có bảo đảm `@Service` được inject và transaction chạy đúng không?
3. Khác nhau giữa `orders → inventory.spi` và `orders → inventory.internal.persistence` là gì?
4. Khi nào một named interface cần thiết hơn việc đặt mọi kiểu ở module root?
5. Vì sao nên giữ `verify()` trong CI dù integration test liên module và E2E đều xanh?
6. Nếu `verify()` xanh nhưng một controller truy cập repository của **chính** module nó, cần loại test/rule nào để phát hiện vi phạm phân tầng nội bộ?

## 18. Ghi nhớ

**Architectural test cho dependency và package** biến quyết định kiến trúc Spring Modulith thành một kiểm tra JUnit có thể chạy tự động. `ApplicationModules.of(ShopApplication.class).verify()` giúp phát hiện vòng phụ thuộc, truy cập ngoài API module và vi phạm whitelist dependency được khai báo. `@ApplicationModule(allowedDependencies = ...)` nêu rõ chiều phụ thuộc được phép, còn `@NamedInterface` công bố những package API cần chia sẻ mà vẫn giữ implementation nội bộ.

Đừng đánh đồng Java `public` với public API của application module. Khi cần kiểm tra luật phân tầng **bên trong** module, bổ sung ArchUnit tùy chỉnh. Kết hợp architectural test với unit test, `@ApplicationModuleTest`, kiểm thử sự kiện, database và integration/E2E test trong **quality gate CI** để vừa ngăn phụ thuộc sai, vừa phát hiện hồi quy hành vi.

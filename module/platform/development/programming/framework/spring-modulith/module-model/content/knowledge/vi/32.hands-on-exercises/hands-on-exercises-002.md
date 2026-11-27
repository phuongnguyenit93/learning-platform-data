# Khởi tạo ApplicationModules và in module model

Trong bài thực hành này, bạn sẽ dùng Spring Modulith để tạo một mô hình mô-đun từ package của ứng dụng Spring Boot, in từng mô-đun ra console và đọc các thông tin mà mô hình cung cấp. Đây là bước đầu tiên để quan sát cấu trúc modular monolith bằng chính mã nguồn hiện có.

`ApplicationModules` là biểu diễn trong bộ nhớ của các application module được phát hiện từ codebase. Nó giúp trả lời những câu hỏi như: ứng dụng đang có những mô-đun nào, package gốc của mỗi mô-đun ở đâu, bean nào thuộc mô-đun nào và những package nào đang được công khai. Việc in model giúp quan sát cấu trúc; kiểm tra các quy tắc kiến trúc vẫn cần gọi `verify()` riêng.

## 1. Chuẩn bị ứng dụng mẫu

Tạo hoặc chọn một ứng dụng Spring Boot có package gốc `com.acme.shop` và ba mô-đun nghiệp vụ:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   └── internal
│       └── OrderRepository.java
├── inventory
│   └── InventoryService.java
└── customers
    └── CustomerService.java
```

Đặt lớp ứng dụng chính tại package gốc để Spring Modulith có thể phát hiện các package mô-đun bên dưới:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Với quy tắc phát hiện mặc định, các package con trực tiếp `orders`, `inventory` và `customers` được nhận diện là application module. Nếu lớp main nằm ở package khác, model sẽ được tạo tương đối với package của lớp được truyền vào `ApplicationModules.of(…)`; hãy xác nhận đúng application class trước khi phân tích kết quả.

## 2. Kiểm tra dependency cần thiết

Module model nằm trong artifact `spring-modulith-core`. Nếu dự án đã sử dụng `spring-modulith-starter-core`, artifact này thường đã được kéo vào thông qua starter. Bài thực hành chỉ cần API core để tạo và in model.

Nếu dự án dùng Spring Modulith BOM, khai báo dependency không cần version riêng. Ví dụ Maven:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-core</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Hoặc Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.modulith:spring-modulith-starter-core")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Nếu dự án đã có starter core thì không cần khai báo thêm `spring-modulith-core` một lần nữa chỉ để sử dụng `ApplicationModules`. Hãy giữ các artifact Modulith cùng một dòng version do BOM quản lý.

## 3. Tạo ApplicationModules từ application class

Tạo một lớp kiểm thử trong `src/test/java/com/acme/shop/ModuleModelTests.java`:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleModelTests {

    @Test
    void createsApplicationModuleModel() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        // Model đã được tạo và có thể được duyệt hoặc tra cứu.
    }
}
```

`ApplicationModules.of(ShopApplication.class)` yêu cầu Spring Modulith phân tích codebase tương đối với package của `ShopApplication`. Kết quả là một model trong bộ nhớ, không phải Spring `ApplicationContext`; thao tác này không khởi động toàn bộ bean hoặc gọi các service nghiệp vụ.

Có thể dùng `var` để rút gọn khai báo:

```java
var modules = ApplicationModules.of(ShopApplication.class);
```

Trong ứng dụng có cấu trúc package đặc biệt, `ApplicationModules.of(…)` còn có overload nhận package name hoặc cấu hình bổ sung. Với ứng dụng Spring Boot thông thường, truyền application class giúp liên kết model với đúng package gốc của ứng dụng.

## 4. In từng application module ra console

Sau khi tạo model, dùng `forEach(System.out::println)` để in thông tin của từng mô-đun:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleModelTests {

    @Test
    void printsApplicationModuleArrangement() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.forEach(System.out::println);
    }
}
```

`ApplicationModules` triển khai `Iterable<ApplicationModule>`, vì vậy có thể dùng vòng lặp `for`, `forEach` hoặc `stream()`. Mỗi `ApplicationModule` có biểu diễn văn bản riêng để hiển thị thông tin mô-đun.

Output minh họa có thể có dạng:

```text
## com.acme.shop.inventory ##
> Logical name: inventory
> Base package: com.acme.shop.inventory
> Spring beans:
  + ….InventoryService

## com.acme.shop.orders ##
> Logical name: orders
> Base package: com.acme.shop.orders
> Spring beans:
  + ….OrderService
  o ….internal.OrderRepository

## com.acme.shop.customers ##
> Logical name: customers
> Base package: com.acme.shop.customers
> Spring beans:
  + ….CustomerService
```

Đây là output rút gọn để minh họa cách đọc; tên lớp, thứ tự mô-đun và các dòng hiển thị phụ thuộc vào codebase thực tế. `OrderRepository` trong ví dụ được giả định là một Spring Data repository bean. Ký hiệu visibility trong output cho biết thành phần thuộc API được công khai hay phần triển khai nội bộ theo mô hình mô-đun. Hãy đọc output thực tế từ ứng dụng của bạn thay vì giả định các dòng sẽ giống hệt ví dụ.

## 5. Đọc những thông tin trong module model

Khi xem output của từng `ApplicationModule`, hãy tập trung vào các phần sau:

| Thông tin | Ý nghĩa | Câu hỏi cần tự kiểm tra |
|---|---|---|
| Logical name | Tên mô-đun được Spring Modulith nhận diện | Tên có phản ánh đúng trách nhiệm nghiệp vụ không? |
| Base package | Package gốc của mô-đun | Package có chứa đúng các lớp thuộc mô-đun không? |
| Spring beans | Các Spring bean được phát hiện trong mô-đun | Có bean nào thuộc nhầm mô-đun không? |
| Visibility | Thành phần được công khai hay nằm trong phần nội bộ | Consumer có thể đang phụ thuộc vào implementation không? |
| Named Interfaces | Các package con được công khai theo tên; kiểm tra thêm trong metadata/API của mô-đun | Mỗi interface có một mục đích tích hợp rõ ràng không? |

Nếu `OrderRepository` nằm trong `orders.internal`, nó nên được giữ ở phần nội bộ. Các mô-đun khác nên sử dụng API công khai của `orders`, chẳng hạn `OrderService` hoặc một interface được công khai có chủ đích.

## 6. In model theo định dạng tùy chỉnh

Khi cần log gọn hơn hoặc đưa thông tin vào báo cáo, có thể duyệt `stream()` và in tên cùng package gốc của từng mô-đun:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ModuleSummaryTests {

    @Test
    void printsModuleNamesAndBasePackages() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.stream()
                .sorted((left, right) -> left.getName().compareTo(right.getName()))
                .forEach(module -> printModule(module));
    }

    private void printModule(ApplicationModule module) {
        System.out.printf(
                "Module: %s | Base package: %s%n",
                module.getName(),
                module.getBasePackage().getName()
        );
    }
}
```

Ở đây, `stream()` trả về các `ApplicationModule`; `getName()` lấy tên logic và `getBasePackage()` trả về package base của mô-đun. Sắp xếp theo tên giúp output ổn định, dễ so sánh giữa các lần chạy. Nếu chỉ cần output đầy đủ mà Spring Modulith cung cấp, `modules.forEach(System.out::println)` đơn giản và thể hiện nhiều thông tin hơn.

## 7. Tra cứu một mô-đun cụ thể

Ngoài việc in toàn bộ model, có thể tra cứu mô-đun theo tên hoặc theo kiểu Java:

```java
package com.acme.shop;

import static org.assertj.core.api.Assertions.assertThat;

import com.acme.shop.inventory.InventoryService;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ModuleLookupTests {

    @Test
    void looksUpModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule orders = modules.getModuleByName("orders")
                .orElseThrow(() -> new IllegalStateException("Module orders was not found"));

        ApplicationModule inventory = modules.getModuleByType(InventoryService.class)
                .orElseThrow(() -> new IllegalStateException("InventoryService has no module"));

        assertThat(orders.getBasePackage().getName())
                .isEqualTo("com.acme.shop.orders");
        assertThat(inventory.getName()).isEqualTo("inventory");
    }
}
```

`getModuleByName(…)` trả về `Optional<ApplicationModule>` theo tên logic. `getModuleByType(…)` xác định mô-đun chứa một kiểu Java. Nếu kết quả không tồn tại, hãy kiểm tra package root, tên mô-đun hoặc vị trí của lớp được truyền vào; đừng tự suy ra mô-đun chỉ từ tên folder.

Các API tra cứu khác có thể hữu ích:

| API | Công dụng |
|---|---|
| `modules.getModuleForPackage("com.acme.shop.orders")` | Tìm mô-đun chứa package |
| `modules.getRootPackages()` | Lấy các package root của mô hình |
| `modules.getModuleByType(OrderService.class)` | Tìm mô-đun chứa lớp cụ thể |
| `modules.stream()` | Duyệt các mô-đun để tạo báo cáo |

## 8. Quan sát module model không đồng nghĩa xác minh kiến trúc

In model giúp bạn nhìn thấy cấu trúc được phát hiện. Nó không tự khẳng định mọi dependency đều hợp lệ. Sau khi quan sát, có thể gọi `verify()` để chạy các quy tắc kiến trúc tích hợp:

```java
@Test
void verifiesTheDiscoveredModuleModel() {
    ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

    modules.forEach(System.out::println);
    modules.verify();
}
```

Nếu module model phát hiện đúng các mô-đun nhưng `verify()` thất bại, hãy đọc violation để xác định dependency cycle, truy cập package nội bộ hoặc dependency không được cho phép. Nếu danh sách mô-đun đã sai ngay từ đầu, hãy xem lại application class được truyền vào và cấu trúc package trước khi sửa các quy tắc dependency.

Trong thực tế, có thể tách hai trách nhiệm thành hai test riêng: một test in hoặc kiểm tra danh sách mô-đun để phục vụ chẩn đoán, một architecture test gọi `verify()` để làm cổng chất lượng trong CI. Không cần in toàn bộ model ở mỗi lần chạy production nếu ứng dụng không có nhu cầu chẩn đoán đó.

## 9. Bài thực hành từng bước

Hãy thực hiện lần lượt trên ứng dụng mẫu:

1. Xác nhận lớp `ShopApplication` nằm trong package `com.acme.shop`.
2. Xác nhận các package `orders`, `inventory` và `customers` là các package con trực tiếp.
3. Thêm `spring-modulith-starter-core` nếu dự án chưa có module model trên compile classpath.
4. Tạo test `ModuleModelTests` trong package `com.acme.shop`.
5. Khởi tạo model bằng `ApplicationModules.of(ShopApplication.class)`.
6. In tất cả mô-đun bằng `modules.forEach(System.out::println)`.
7. Đọc tên logic, base package, Spring bean và visibility trong output.
8. In danh sách rút gọn bằng `stream()` và sắp xếp theo tên mô-đun.
9. Tra cứu `orders` bằng `getModuleByName("orders")` và tra cứu `InventoryService` bằng `getModuleByType(InventoryService.class)`.
10. Gọi `modules.verify()` trong một architecture test để kiểm tra các quy tắc module.

## 10. Kết quả mong đợi và cách xử lý khi khác biệt

Sau bài thực hành, bạn cần có một module model với ba mô-đun dự kiến. Kết quả có thể được ghi lại bằng bảng:

| Module | Base package mong đợi | Ví dụ Spring bean |
|---|---|---|
| `orders` | `com.acme.shop.orders` | `OrderService` |
| `inventory` | `com.acme.shop.inventory` | `InventoryService` |
| `customers` | `com.acme.shop.customers` | `CustomerService` |

Nếu thiếu một mô-đun:

- Kiểm tra package của `ShopApplication` và class được truyền vào `ApplicationModules.of(…)`.
- Kiểm tra package mô-đun có nằm bên dưới root hay không.
- Kiểm tra mô-đun có package hoặc metadata khiến detection strategy chọn cách khác không.

Nếu một mô-đun chứa quá nhiều lớp:

- Xác định package base đang được nhận diện.
- Kiểm tra xem các package con có thực sự thuộc cùng một mô-đun hay cần trở thành mô-đun độc lập.
- Chỉ dùng custom detection strategy hoặc nested module khi cấu trúc nghiệp vụ yêu cầu.

Nếu output có bean bạn không mong đợi:

- Xác định package khai báo bean.
- Kiểm tra component scan và vị trí của lớp.
- Xem xét bean có thuộc mô-đun khác hoặc package cấu hình dùng chung không.

Không chỉnh package hoặc detection strategy chỉ để output trông giống ví dụ. Model phải phản ánh cấu trúc và ranh giới nghiệp vụ thực tế của ứng dụng.

## 11. Bài tập mở rộng

Sau khi in được module model, hãy thử các thay đổi sau trong nhánh làm việc riêng:

**Bài 1 — Thêm một mô-đun mới.** Tạo package `shipping` và một Spring bean `ShippingService`. Chạy lại test, xác nhận mô-đun mới xuất hiện trong output.

**Bài 2 — Công khai một Named Interface.** Tạo package `orders.api`, đánh dấu bằng `@NamedInterface("api")`, chuyển một hợp đồng cần chia sẻ vào package này và in lại module model. Quan sát visibility của API so với package `orders.internal`.

**Bài 3 — Tra cứu kiểu.** Dùng `getModuleByType(ShippingService.class)` để xác nhận lớp mới thuộc mô-đun `shipping`.

**Bài 4 — Tạo architecture gate.** Gọi `verify()` và quan sát kết quả. Nếu có violation, xác định nó đến từ module discovery hay dependency rule trước khi sửa.

**Bài 5 — So sánh output.** Lưu output trước và sau khi thêm mô-đun hoặc Named Interface để mô tả chính xác thay đổi của module model.

## 12. Câu hỏi tự kiểm tra

| Câu hỏi | Câu trả lời cần đạt |
|---|---|
| `ApplicationModules.of(ShopApplication.class)` tạo ra điều gì? | Một biểu diễn trong bộ nhớ của application module arrangement được phát hiện từ codebase. |
| Vì sao cần truyền đúng application class? | Package của class là điểm bắt đầu để phát hiện mô-đun theo cấu trúc package. |
| `modules.forEach(System.out::println)` in ra điều gì? | Biểu diễn từng mô-đun, gồm tên logic, base package và thông tin thành phần được phát hiện. |
| `ApplicationModules` có khởi động Spring ApplicationContext không? | Không. Nó phân tích codebase để tạo module model. |
| In model có thay thế `verify()` không? | Không. In model phục vụ quan sát; `verify()` chạy các quy tắc kiến trúc. |
| `getModuleByName(…)` trả về kiểu gì? | `Optional<ApplicationModule>`. |

Khi hoàn thành, bạn phải có khả năng tự tạo `ApplicationModules`, in module arrangement, đọc output và giải thích sự khác nhau giữa quan sát mô hình với xác minh kiến trúc.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: The ApplicationModules Type](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith API — ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)

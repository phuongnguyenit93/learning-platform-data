# Kiểm tra module được phát hiện bằng ApplicationModules

Sau khi tổ chức package cho một modular monolith, ta cần biết Spring Modulith đã nhận diện những application module nào. `ApplicationModules` là điểm bắt đầu để tạo mô hình từ package gốc của ứng dụng, duyệt danh sách module được phát hiện và đọc thông tin như tên module, display name, base package cùng các named interface.

Việc kiểm tra danh sách module giúp phát hiện sớm cấu trúc package không đúng ý định. Ví dụ, một package kỹ thuật như `service` hoặc `repository` vô tình nằm trực tiếp dưới application root có thể được nhận diện thành module riêng. Ngược lại, module nghiệp vụ đặt ngoài phạm vi package gốc có thể không xuất hiện trong mô hình.

## 1. Tạo mô hình từ application root package

Giả sử lớp khởi động Spring Boot nằm trong package `com.example.shop`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Ta tạo mô hình module bằng cách truyền lớp khởi động cho `ApplicationModules.of(...)`:

```java
package com.example.shop;

import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

Spring Modulith sử dụng package của lớp được truyền vào làm application root package để khám phá các module bên dưới. Theo cách tổ chức mặc định, các package con trực tiếp của package gốc là các application module.

Ví dụ package tree:

```text
com.example.shop                  # Application root package
├── ShopApplication.java
├── catalog                        # Application module
│   ├── ProductCatalog.java
│   └── internal
├── orders                         # Application module
│   ├── OrderManagement.java
│   └── internal
└── inventory                      # Application module
    ├── StockAvailability.java
    └── internal
```

Trong ví dụ, mô hình kỳ vọng có ba application module: `catalog`, `orders` và `inventory`. Các package con sâu hơn như `orders.internal` thuộc phạm vi của module `orders`, không tự trở thành module ngang hàng.

## 2. Duyệt danh sách module đã được phát hiện

`ApplicationModules` cho phép duyệt các `ApplicationModule` trong mô hình. Ta có thể in tên module, tên hiển thị và base package để kiểm tra kết quả discovery:

```java
package com.example.shop;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

for (ApplicationModule module : modules) {
    System.out.printf(
            "name=%s, displayName=%s, basePackage=%s%n",
            module.getName(),
            module.getDisplayName(),
            module.getBasePackage().getName());
}
```

Ba thông tin có ý nghĩa khác nhau:

- `getName()` trả về tên kỹ thuật dùng để nhận diện module trong mô hình và trong các khai báo dependency.
- `getDisplayName()` trả về tên thân thiện dành cho tài liệu hoặc báo cáo.
- `getBasePackage().getName()` cho biết package gốc mà module sở hữu.

Ví dụ, module có thể có tên kỹ thuật `orders`, display name `Quản lý đơn hàng` và base package `com.example.shop.orders`. Không nên dùng display name thay cho tên kỹ thuật khi khai báo `allowedDependencies`.

## 3. Đọc named interface của từng module

Ngoài base package, mỗi module còn có thể công khai các named interface. `ApplicationModule.getNamedInterfaces()` trả về tập hợp named interface thuộc module đó. Ta có thể duyệt chúng để biết module đang công khai những nhóm API nào:

```java
package com.example.shop;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

for (ApplicationModule module : modules) {
    System.out.println("Module: " + module.getName());

    module.getNamedInterfaces().stream().forEach(namedInterface -> {
        String name = namedInterface.isUnnamed()
                ? "unnamed (default interface)"
                : namedInterface.getName();

        System.out.println("  Interface: " + name);
    });
}
```

Named interface có thể được khai báo bằng `@NamedInterface` trên package hoặc type. Các type trực tiếp ở base package thuộc unnamed interface mặc định. Với module `inventory`, kết quả có thể cho thấy default interface cùng các interface được đặt tên như `api` hoặc `reservation`.

Việc đọc danh sách này giúp kiểm tra xem annotation đã được đặt đúng package chưa và module có đang công khai đúng nhóm hợp đồng dự định không. Nếu một type cần được caller sử dụng nhưng chỉ xuất hiện trong package nội bộ, hãy xem lại vị trí package và khai báo named interface.

## 4. Xác định module sở hữu một type cụ thể

Khi biết một type cụ thể, ta có thể hỏi mô hình module nào sở hữu type đó bằng `getModuleByType(Class<?>)`:

```java
package com.example.shop;

import com.example.shop.orders.OrderManagement;
import com.example.shop.inventory.api.StockReservation;
import java.util.Optional;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

Optional<ApplicationModule> owner =
        modules.getModuleByType(OrderManagement.class);

owner.ifPresentOrElse(
        module -> System.out.println("Owner: " + module.getName()),
        () -> System.out.println("Type không thuộc module được phát hiện"));
```

Nếu `owner` có giá trị, type thuộc module tương ứng trong mô hình. Nếu kết quả rỗng, hãy kiểm tra package của type, application root package và cấu trúc discovery. Một type nằm trực tiếp trong application root package hoặc ngoài phạm vi module có thể không được gán cho application module nào.

Sau khi tìm thấy module sở hữu, ta có thể kiểm tra named interface chứa type bằng `contains(Class<?>)`:

```java
ApplicationModule module = modules.getModuleByType(StockReservation.class)
        .orElseThrow();

module.getNamedInterfaces().stream()
        .filter(namedInterface -> namedInterface.contains(StockReservation.class))
        .forEach(namedInterface -> System.out.println(namedInterface.getName()));
```

Nếu type thuộc unnamed interface, có thể dùng `isUnnamed()` để nhận diện trường hợp đó. Nếu không có named interface nào chứa type, type có thể là chi tiết nội bộ của module.

## 5. Phân biệt discovery với verification

Tạo `ApplicationModules` và duyệt module trả lời câu hỏi: **Spring Modulith đã phát hiện những module nào?** Việc này chưa chứng minh các module tuân thủ mọi quy tắc kiến trúc.

Để kiểm tra dependency, package nội bộ và các quy tắc module, hãy gọi `verify()`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Hai bước có thể cho kết quả khác nhau:

| Thao tác | Điều được kiểm tra |
|---|---|
| `ApplicationModules.of(ShopApplication.class)` | Tạo mô hình và khám phá module từ package gốc |
| Duyệt `ApplicationModules` | Quan sát module, base package, tên hiển thị và named interface |
| `getModuleByType(...)` | Tìm module sở hữu một type |
| `verify()` | Kiểm tra các quy tắc kiến trúc như dependency, chu trình và truy cập package nội bộ |

Một module có thể được phát hiện đúng nhưng vẫn có dependency sai. Ví dụ, `orders` và `catalog` đều xuất hiện trong danh sách, nhưng `orders` lại import trực tiếp type trong `catalog.internal`. Discovery thành công không làm cho tham chiếu đó trở nên hợp lệ; `verify()` mới kiểm tra vi phạm ranh giới.

## 6. Đưa việc quan sát module vào kiểm thử

Ta có thể kiểm tra một type quan trọng được gán vào đúng module dự kiến:

```java
package com.example.shop;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.shop.orders.OrderManagement;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDiscoveryTests {

    private final ApplicationModules modules =
            ApplicationModules.of(ShopApplication.class);

    @Test
    void orderManagementBelongsToOrdersModule() {
        var owner = modules.getModuleByType(OrderManagement.class);

        assertTrue(owner.isPresent());
        assertEquals("orders", owner.orElseThrow().getName());
    }

    @Test
    void verifiesModuleRules() {
        modules.verify();
    }
}
```

Test đầu tiên xác nhận `OrderManagement` thuộc module có tên kỹ thuật `orders`. Test thứ hai xác nhận các quy tắc kiến trúc mà Spring Modulith áp dụng. Có thể bổ sung kiểm tra named interface nếu API công khai của module là một phần quan trọng của hợp đồng.

## 7. Những dấu hiệu cho thấy discovery chưa đúng ý định

| Kết quả quan sát | Nguyên nhân cần xem xét |
|---|---|
| Có module `controller`, `service` hoặc `repository` | Các package kỹ thuật đang nằm trực tiếp dưới application root package |
| Không thấy module `orders` | Package `orders` có thể nằm ngoài application root package hoặc lớp neo được chọn chưa đúng |
| Type nghiệp vụ không có module sở hữu | Type có thể nằm trực tiếp trong application root package hoặc ngoài phạm vi discovery |
| Module có base package đúng nhưng API hiển thị thiếu | Kiểm tra package gốc, sub-package và các khai báo `@NamedInterface` |
| Module được phát hiện nhưng `verify()` thất bại | Có thể tồn tại dependency không hợp lệ, chu trình hoặc truy cập package nội bộ |

Khi gặp kết quả không mong đợi, hãy quay lại package tree trước khi thêm annotation. Đảm bảo application root package là tổ tiên chung của các module, package con trực tiếp phản ánh năng lực nghiệp vụ và các sub-package thể hiện đúng API hoặc implementation.

## 8. Quy trình kiểm tra trong dự án

Khi bắt đầu một module model hoặc sau khi thay đổi package, có thể dùng trình tự sau:

1. Chọn lớp khởi động nằm ở application root package.
2. Tạo mô hình bằng `ApplicationModules.of(ShopApplication.class)`.
3. Duyệt module để xem `getName()`, `getDisplayName()` và `getBasePackage()`.
4. Duyệt `getNamedInterfaces()` để kiểm tra các nhóm API được công khai.
5. Dùng `getModuleByType()` để xác nhận các type quan trọng thuộc đúng module.
6. Gọi `verify()` trong một bài kiểm thử kiến trúc để bảo vệ các quy tắc dependency.

Khi đưa các bước này vào kiểm thử tự động, nhóm có thể nhận ra sớm package bị đặt sai cấp, module bị bỏ sót hoặc API được công khai ngoài dự kiến. `ApplicationModules` vì vậy vừa là công cụ quan sát mô hình module, vừa là nền tảng để xây dựng các kiểm thử kiến trúc cho modular monolith.

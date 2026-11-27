# Module nằm trong direct sub-package theo quy ước mặc định

Spring Modulith sử dụng cấu trúc package để nhận diện application module. Theo quy ước mặc định, mỗi package con trực tiếp (direct sub-package) của application base package là một module. Các package lồng sâu hơn tiếp tục thuộc về module tương ứng, không tự động trở thành module độc lập.

Quy tắc này ảnh hưởng trực tiếp đến cách tổ chức mã nguồn. Nếu muốn có các module nghiệp vụ như `order`, `inventory` và `customer`, hãy đặt chúng ngay dưới package gốc của ứng dụng. Các package `internal`, `persistence` hoặc `web` nên nằm bên trong module mà chúng phục vụ.

## 1. Xác định application base package

Application base package là package gốc mà Spring Modulith dùng để khám phá các module. Khi tạo mô hình bằng `ApplicationModules.of(ShopApplication.class)`, package chứa `ShopApplication` được dùng làm điểm bắt đầu.

Ví dụ, lớp ứng dụng chính nằm trong `com.acme.shop`:

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

Trong ví dụ này, `com.acme.shop` là application base package. Những package con trực tiếp như `com.acme.shop.order` và `com.acme.shop.inventory` là các ứng viên module theo quy ước mặc định.

Hãy đặt lớp ứng dụng chính ở package gốc chung của các module. Nếu đặt lớp này trong một package con như `com.acme.shop.bootstrap`, việc khám phá bắt đầu từ package đó; các package ngang hàng như `com.acme.shop.order` nằm ngoài phạm vi package gốc này.

## 2. Direct sub-package tạo thành module

Giả sử ứng dụng bán hàng có cấu trúc:

```text
com.acme.shop                       # application base package
├── ShopApplication.java
├── order                           # module order
│   ├── OrderManagement.java
│   ├── Order.java
│   └── internal
│       ├── OrderRepository.java
│       └── OrderValidator.java
├── inventory                       # module inventory
│   ├── InventoryManagement.java
│   └── internal
│       └── StockRepository.java
└── customer                        # module customer
    ├── CustomerManagement.java
    └── internal
        └── CustomerRepository.java
```

Với application base package là `com.acme.shop`, Spring Modulith nhận diện các module mặc định như sau:

| Direct sub-package | Tên module | Module base package |
|---|---|---|
| `order` | `order` | `com.acme.shop.order` |
| `inventory` | `inventory` | `com.acme.shop.inventory` |
| `customer` | `customer` | `com.acme.shop.customer` |

Tên module mặc định được suy ra từ package con trực tiếp. Ví dụ, `com.acme.shop.order` tạo module `order`. Package gốc `com.acme.shop` đóng vai trò điểm khám phá; nó không phải một trong ba direct sub-package kể trên.

Quy tắc cần nhớ là **cấp package ngay dưới application base package quyết định ranh giới module mặc định**. Khi package đã được nhận diện là module, các package con của nó được gom vào module đó.

## 3. Package lồng nhau vẫn thuộc module gần nhất

Trong cấu trúc ví dụ, `com.acme.shop.order.internal` không phải module thứ tư. Nó là package con của module `order`. Tương tự, `com.acme.shop.inventory.internal` thuộc module `inventory`.

```text
com.acme.shop
└── order                           # module order
    ├── OrderManagement.java        # type ở module base package
    ├── internal                    # package con của order
    │   ├── OrderRepository.java
    │   └── OrderValidator.java
    ├── persistence                 # package con của order
    │   └── JpaOrderRepository.java
    └── web                         # package con của order
        └── OrderController.java
```

Các package `internal`, `persistence` và `web` đều nằm trong phạm vi module `order`. Chúng có thể phân chia phần triển khai theo trách nhiệm kỹ thuật mà không làm thay đổi số lượng module mặc định.

Điều này giúp tránh việc tạo module chỉ vì muốn chia một module lớn thành các package nhỏ. Bạn có thể tổ chức code theo tầng bên trong module, trong khi ranh giới nghiệp vụ vẫn nằm ở `order`.

## 4. So sánh cấu trúc theo nghiệp vụ và cấu trúc theo tầng

Với modular monolith, cấu trúc theo năng lực nghiệp vụ thường thể hiện ranh giới module rõ ràng hơn.

**Cấu trúc theo nghiệp vụ:**

```text
com.acme.shop
├── order
│   ├── OrderManagement.java
│   ├── web
│   └── persistence
├── inventory
│   ├── InventoryManagement.java
│   └── persistence
└── customer
    ├── CustomerManagement.java
    └── persistence
```

Spring Modulith nhận diện `order`, `inventory` và `customer` là ba module. Mỗi module sở hữu các lớp web, nghiệp vụ và lưu trữ dữ liệu phục vụ cho năng lực tương ứng.

**Cấu trúc theo tầng ở ngay dưới package gốc:**

```text
com.acme.shop
├── controller
├── service
└── repository
```

Theo quy ước mặc định, cấu trúc thứ hai tạo ra các module `controller`, `service` và `repository`. Những module này phản ánh tầng kỹ thuật của ứng dụng thay vì ranh giới nghiệp vụ. Các lớp của đơn hàng, kho và khách hàng có thể bị trộn lẫn trong cùng một module, khiến việc kiểm soát phụ thuộc nghiệp vụ trở nên khó khăn.

Vì vậy, hãy đặt package nghiệp vụ ngay dưới application base package, rồi đặt các package kỹ thuật sâu hơn bên trong từng module.

## 5. Package gốc và package dùng chung

Một package con trực tiếp bất kỳ đều được xem là module theo quy ước mặc định, kể cả khi tên của nó mang ý nghĩa kỹ thuật.

Ví dụ:

```text
com.acme.shop
├── order
├── inventory
├── customer
└── common
```

Trong cấu trúc này, `common` cũng được nhận diện là module. Nếu package này chỉ chứa các hàm tiện ích chung, việc gom mọi thứ vào `common` có thể tạo ra một điểm phụ thuộc rộng và khó kiểm soát. Hãy cân nhắc trách nhiệm thực sự của package đó: nếu nó có khái niệm nghiệp vụ và API riêng, có thể giữ nó như module; nếu không, hãy xem xét cách đặt các thành phần dùng chung sao cho không vô tình tạo một module gốc mới.

Tương tự, nếu đặt `config`, `util` hoặc `shared` ngay dưới application base package, mỗi package đó cũng trở thành một module theo quy ước mặc định. Tên package không quyết định nó có phải module hay không; vị trí package trong cây mới là yếu tố quyết định.

## 6. Phân biệt module base package với package con nội bộ

Module base package là package trực tiếp dưới application base package, ví dụ `com.acme.shop.order`. Theo quy ước mặc định của Spring Modulith, các type ở module base package tạo thành API công khai mặc định. Các package con như `order.internal` là phần triển khai nội bộ.

Ví dụ, module `order` có thể công bố hợp đồng:

```java
package com.acme.shop.order;

public interface OrderManagement {

    void placeOrder(String orderId);
}
```

Phần triển khai nằm trong package con:

```java
package com.acme.shop.order.internal;

import com.acme.shop.order.OrderManagement;
import org.springframework.stereotype.Service;

@Service
public class OrderManagementService implements OrderManagement {

    @Override
    public void placeOrder(String orderId) {
        // Xử lý nghiệp vụ đặt hàng.
    }
}
```

Module khác nên phụ thuộc vào `OrderManagement` thay vì tham chiếu trực tiếp `OrderManagementService` hoặc repository trong package nội bộ. Lưu ý rằng package Java cha và package con vẫn là hai package riêng về quyền truy cập của ngôn ngữ Java; package-private không tự động cho phép truy cập giữa chúng.

Nếu cần công bố một package con làm API, có thể đánh dấu package đó bằng `@NamedInterface` trong `package-info.java`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.order.spi;
```

Named interface công bố một phần API có tên của module `order`. Package `order.spi` vẫn thuộc module `order`, không trở thành module ngang hàng với `order`.

## 7. Khai báo metadata cho module

Bạn có thể đặt metadata của module trong `package-info.java` tại module base package. Ví dụ:

```java
@org.springframework.modulith.ApplicationModule(
        displayName = "Quản lý đơn hàng"
)
package com.acme.shop.order;
```

`@ApplicationModule` bổ sung thông tin và quy tắc cho module đã được nhận diện. Việc khai báo `displayName`, loại module hoặc `allowedDependencies` giúp mô tả ý định kiến trúc rõ hơn. Annotation này không làm cho một package lồng sâu như `order.internal` tự trở thành module mặc định.

Hãy phân biệt hai việc:

- **Nhận diện module:** quy ước package mặc định xác định module từ direct sub-package của application base package.
- **Mô tả module:** metadata như `@ApplicationModule` và `@NamedInterface` mô tả module hoặc các API được công bố.

## 8. Kiểm tra mô hình module bằng ApplicationModules

Bạn có thể dùng `ApplicationModules` để xem Spring Modulith đã nhận diện những module nào và xác minh quy tắc phụ thuộc:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.forEach(module ->
                System.out.println(module.getName() + " -> " + module.getBasePackage())
        );

        modules.verify();
    }
}
```

Khi chạy kiểm thử, danh sách module cho biết tên module và module base package mà Spring Modulith khám phá. `verify()` kiểm tra các quy tắc kiến trúc, bao gồm những phụ thuộc không hợp lệ giữa các module.

Nếu kết quả có `controller`, `service` hoặc `repository` như những module riêng, hãy kiểm tra lại cấu trúc package gốc. Có thể các package kỹ thuật đang được đặt ở cấp direct sub-package thay vì bên trong module nghiệp vụ.

## 9. Bài tập thực hành

Thiết kế package cho ứng dụng bán hàng với ba năng lực: đơn hàng, kho hàng và khách hàng.

1. Đặt `ShopApplication` trong package `com.acme.shop`.
2. Tạo ba direct sub-package: `order`, `inventory` và `customer`.
3. Trong mỗi module, tạo package con `internal` để chứa implementation.
4. Tạo package `persistence` và `web` bên trong `order`; xác định chúng thuộc module nào.
5. Tạo một package `common` ngay dưới `com.acme.shop`; dự đoán Spring Modulith sẽ nhận diện nó ra sao.
6. Chuyển một package `controller` từ cấp gốc vào trong `order`; so sánh danh sách module trước và sau thay đổi.
7. Chạy `ApplicationModules.of(ShopApplication.class).verify()` để kiểm tra mô hình và phụ thuộc.

Sau bài tập, hãy giải thích vì sao `order.internal` không phải module độc lập theo quy ước mặc định, trong khi `com.acme.shop.common` lại được nhận diện là một module.

## 10. Ghi nhớ

- Application base package được xác định từ package của lớp ứng dụng dùng để khám phá module.
- Mỗi direct sub-package của application base package tạo thành một application module theo quy ước mặc định.
- Các package lồng sâu hơn thuộc về module gần nhất đã được nhận diện; chúng không tự động tạo module mới.
- Đặt package nghiệp vụ như `order`, `inventory` và `customer` ở cấp trực tiếp dưới package gốc.
- Đặt `internal`, `web`, `persistence` và các package triển khai bên trong module nghiệp vụ tương ứng.
- `@ApplicationModule` mô tả metadata của module; `@NamedInterface` công bố package con như một phần API có tên.
- Dùng `ApplicationModules.verify()` để xác minh mô hình và các quy tắc phụ thuộc.

Khi tổ chức package theo quy ước direct sub-package, cây package thể hiện được ranh giới nghiệp vụ mà Spring Modulith có thể tự động khám phá và kiểm chứng trong ứng dụng modular monolith.

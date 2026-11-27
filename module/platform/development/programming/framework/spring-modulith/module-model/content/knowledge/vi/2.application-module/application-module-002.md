# Base package và các package con của module

Trong Spring Modulith, cấu trúc package là nền tảng để nhận diện các application module. Spring Modulith dựa vào package gốc của ứng dụng và các package nằm ngay bên dưới nó để xác định ranh giới module. Những package sâu hơn tiếp tục thuộc về module đã được nhận diện ở cấp trên.

Nắm được quy tắc này giúp bạn tổ chức một ứng dụng Spring Boot thành các vùng nghiệp vụ như đơn hàng, kho hàng và khách hàng. Mỗi vùng có thể chứa phần triển khai nội bộ trong các package con, đồng thời công bố một API có chủ đích cho module khác sử dụng.

## 1. Phân biệt package gốc và package của module

Có hai cấp package cần phân biệt:

- **Application base package** là package gốc của ứng dụng. Khi dùng `ApplicationModules.of(ShopApplication.class)`, Spring Modulith lấy package chứa lớp `ShopApplication` làm điểm bắt đầu để khám phá module.
- **Module base package** là một package con trực tiếp của application base package. Theo quy tắc mặc định, mỗi package ở cấp này tạo thành một application module.

Ví dụ, lớp khởi động nằm trong `com.acme.shop`:

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

Với cấu trúc package sau, `com.acme.shop` là application base package:

```text
com.acme.shop
├── ShopApplication.java
├── order
├── inventory
└── customer
```

Spring Modulith nhận diện ba module mặc định:

| Module | Module base package |
|---|---|
| Đơn hàng | `com.acme.shop.order` |
| Kho hàng | `com.acme.shop.inventory` |
| Khách hàng | `com.acme.shop.customer` |

Vì vậy, vị trí của lớp ứng dụng chính có ảnh hưởng trực tiếp đến phạm vi khám phá module. Đặt lớp này ở package gốc mà bạn muốn quản lý sẽ giúp ranh giới được rõ ràng và nhất quán.

## 2. Các package con thuộc về module cha

Một module bao gồm module base package và các package con của nó ở mọi cấp. Ví dụ:

```text
com.acme.shop
├── ShopApplication.java
├── order                         # module order
│   ├── OrderManagement.java
│   ├── Order.java
│   ├── internal
│   │   ├── OrderRepository.java
│   │   └── OrderValidator.java
│   └── persistence
│       └── JpaOrderRepository.java
├── inventory                     # module inventory
│   ├── InventoryManagement.java
│   └── internal
│       └── StockRepository.java
└── customer                      # module customer
    ├── CustomerManagement.java
    └── internal
        └── CustomerRepository.java
```

Trong ví dụ này:

- `com.acme.shop.order` là module base package của module `order`.
- `com.acme.shop.order.internal` và `com.acme.shop.order.persistence` là các package con thuộc module `order`.
- `com.acme.shop.inventory.internal` thuộc module `inventory`, không tạo ra một module độc lập tên `internal`.
- `com.acme.shop.customer.internal` thuộc module `customer`.

Một package chỉ trở thành module mặc định khi nó nằm **ngay dưới application base package**. Package lồng sâu hơn được gom vào module gần nhất đã được nhận diện ở cấp trực tiếp đó. Do vậy, `order.internal` không phải module ngang hàng với `order` và `inventory`.

## 3. Ranh giới module và khả năng truy cập

Cần phân biệt cách Java xử lý package với cách Spring Modulith nhóm package thành module:

- Trong Java, `com.acme.shop.order` và `com.acme.shop.order.internal` là hai package riêng. Quyền truy cập mặc định (package-private) của Java không tự mở rộng từ package cha sang package con.
- Trong mô hình của Spring Modulith, cả hai package trên đều thuộc cùng module `order`.
- Theo quy ước mặc định của Spring Modulith, các kiểu nằm trong module base package là phần API được công khai. Các package con được xem là phần triển khai nội bộ, trừ khi bạn chủ động công bố chúng qua named interface.

Ví dụ, module `order` có thể đặt lớp điều phối nghiệp vụ trong package gốc:

```java
package com.acme.shop.order;

public interface OrderManagement {

    void placeOrder(String orderId);
}
```

Các lớp hỗ trợ như repository hoặc validator có thể nằm trong `order.internal`. Module khác nên phụ thuộc vào API đã công bố của `order`, thay vì gọi trực tiếp các lớp triển khai nội bộ. Cách tổ chức này giúp thay đổi cách lưu trữ hoặc kiểm tra đơn hàng mà ít ảnh hưởng đến các module sử dụng.

Nếu cần công bố một package con, bạn có thể đánh dấu package đó là named interface bằng `@NamedInterface` trong `package-info.java`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.order.spi;
```

Khi đó, `order.spi` vẫn thuộc module `order`, nhưng được nhận diện như một giao diện có tên để module khác khai báo phụ thuộc có chủ đích. Named interface hữu ích khi module cần cung cấp nhiều điểm tích hợp khác nhau mà không phải công khai toàn bộ phần triển khai.

## 4. Chọn cấu trúc package phù hợp

Khi thiết kế package cho modular monolith, hãy bắt đầu từ năng lực nghiệp vụ thay vì tầng kỹ thuật dùng chung cho toàn ứng dụng.

**Cấu trúc theo module nghiệp vụ:**

```text
com.acme.shop
├── order
│   ├── OrderManagement.java
│   ├── Order.java
│   └── internal
├── inventory
│   ├── InventoryManagement.java
│   └── internal
└── customer
    ├── CustomerManagement.java
    └── internal
```

Mỗi module giữ các thành phần liên quan đến một vùng nghiệp vụ. Các package con có thể phân chia theo mục đích kỹ thuật như `internal`, `persistence` hoặc `web`, miễn là chúng vẫn phục vụ cùng module.

Hãy chú ý các trường hợp sau:

1. **Đặt lớp ứng dụng chính quá sâu.** Nếu `ShopApplication` nằm trong `com.acme.shop.bootstrap`, package gốc được suy ra từ lớp này sẽ là `com.acme.shop.bootstrap`. Khi đó các package `order` và `inventory` nằm ngoài cây package bắt đầu từ điểm này. Hãy đặt lớp ứng dụng chính tại package gốc dự kiến, chẳng hạn `com.acme.shop`.
2. **Tạo package dùng chung ngay dưới package gốc.** Với quy tắc mặc định, `com.acme.shop.shared` cũng được nhận diện như một module. Nếu package này chỉ chứa tiện ích kỹ thuật được nhiều module dùng, hãy cân nhắc xem nó có thực sự là một module nghiệp vụ với API và trách nhiệm riêng hay không. Tránh biến nó thành nơi tập trung mọi lớp dùng chung.
3. **Để module khác truy cập package nội bộ.** Việc một lớp có thể được import ở cấp Java không có nghĩa đó là phụ thuộc hợp lệ theo kiến trúc. Hãy đưa hợp đồng cần chia sẻ vào module base package hoặc một named interface đã công bố.
4. **Tổ chức theo tầng ở cấp gốc.** Cấu trúc như `controller`, `service`, `repository` ngay dưới application base package sẽ khiến mỗi package đó trở thành một module mặc định. Với mục tiêu mô hình hóa ranh giới nghiệp vụ, hãy ưu tiên `order`, `inventory`, `customer`, rồi đặt các tầng kỹ thuật bên trong từng module.

## 5. Kiểm chứng cấu trúc bằng ApplicationModules

Spring Modulith cung cấp `ApplicationModules` để khám phá các module từ lớp ứng dụng và kiểm tra các quy tắc kiến trúc. Bạn có thể thêm một bài kiểm tra để phát hiện sớm phụ thuộc không hợp lệ:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ApplicationModules.of(ShopApplication.class)` sử dụng package của `ShopApplication` làm gốc để khám phá module. Lệnh `verify()` kiểm tra mô hình module và các quy tắc phụ thuộc mà Spring Modulith áp dụng, chẳng hạn việc truy cập phần nội bộ của module khác hoặc tạo chu trình phụ thuộc không được phép.

Khi bài kiểm tra thất bại, hãy đọc thông báo vi phạm để xác định package nguồn và package đích. Sau đó kiểm tra lại cấu trúc: hai package có thực sự thuộc cùng module không, API cần dùng đã được công bố chưa, và module gọi có nên phụ thuộc vào module đích không.

## 6. Bài tập thực hành

Giả sử ứng dụng bán hàng có ba vùng nghiệp vụ: đơn hàng, kho hàng và khách hàng.

1. Đặt `ShopApplication` trong package `com.acme.shop`.
2. Tạo ba package trực tiếp bên dưới: `order`, `inventory` và `customer`.
3. Trong mỗi module, tạo package con `internal` để chứa lớp triển khai nội bộ.
4. Đặt một lớp API ở module base package, ví dụ `OrderManagement` trong `com.acme.shop.order`.
5. Chạy bài kiểm tra `ApplicationModules.of(ShopApplication.class).verify()`.
6. Thử tạo một phụ thuộc từ module khác đến `com.acme.shop.order.internal`, quan sát vi phạm kiến trúc, rồi chuyển lời gọi sang API được công bố.
7. Nếu một package con cần được module khác sử dụng như một hợp đồng riêng, đánh dấu nó bằng `@NamedInterface` và cấu hình phụ thuộc theo named interface đó.

Sau bài tập, hãy tự trả lời: package nào là application base package, package nào là module base package, và package nào chỉ là phần nội bộ của một module?

## 7. Ghi nhớ

- Application base package được xác định từ package của lớp ứng dụng dùng để khám phá module.
- Mỗi package con trực tiếp của application base package là một module mặc định.
- Các package con ở sâu hơn thuộc về module gần nhất ở cấp trực tiếp; chúng không tự tạo module mới.
- Module base package là nơi đặt API công khai mặc định. Package con thường dành cho triển khai nội bộ; dùng named interface khi cần công bố một package con.
- Dùng `ApplicationModules.of(ShopApplication.class).verify()` để kiểm chứng mô hình và quy tắc phụ thuộc trong quá trình phát triển.

Khi đặt đúng package gốc và nhóm các package con theo năng lực nghiệp vụ, cấu trúc mã nguồn sẽ thể hiện được ranh giới module. Đây là bước đầu để Spring Modulith giúp kiểm tra kiến trúc modular monolith một cách tự động.

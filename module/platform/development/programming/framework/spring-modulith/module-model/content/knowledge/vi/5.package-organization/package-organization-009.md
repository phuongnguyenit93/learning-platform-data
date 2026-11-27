# Đọc package tree trước khi khai báo annotation

Trước khi thêm `@ApplicationModule` hoặc `@NamedInterface`, hãy đọc cấu trúc package của ứng dụng. Spring Modulith dựa vào package để nhận diện application module và xác định ranh giới giữa API công khai với phần triển khai nội bộ. Nếu chưa hiểu package tree, ta có thể đặt annotation sai vị trí, công khai nhầm package hoặc vô tình chia ứng dụng thành những module kỹ thuật không mong muốn.

Một trình tự dễ áp dụng là: xác định package gốc của ứng dụng, tìm các package con trực tiếp, phân loại trách nhiệm của từng package, rồi mới khai báo annotation tại những package cần metadata bổ sung.

## 1. Bắt đầu từ package gốc của ứng dụng

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

Package `com.example.shop` là application root package. Đây là điểm bắt đầu để Spring Modulith khám phá cấu trúc module khi ta khởi tạo:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

Hãy xác định đúng package của lớp được truyền vào. Nếu chọn một lớp nằm trong package nghiệp vụ con như `com.example.shop.orders`, phạm vi khám phá sẽ bắt đầu từ package đó và có thể bỏ sót các module ngang hàng như `catalog` hoặc `inventory`.

## 2. Nhìn các package con trực tiếp để nhận diện module

Theo quy ước khám phá mặc định, các package con trực tiếp của application root package là những application module. Ví dụ:

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

Trong cây này, `catalog`, `orders` và `inventory` là các module ngang hàng. Những package sâu hơn như `catalog.internal` và `orders.internal` thuộc phạm vi của module cha; chúng không tự trở thành các module ngang hàng mới theo cách khám phá mặc định.

Đây là lý do package tree cần phản ánh năng lực nghiệp vụ. Nếu một ứng dụng được chia thành `catalog`, `orders` và `inventory`, mỗi module có thể sở hữu dữ liệu, logic và API của mình. Cấu trúc package lúc này cho thấy ranh giới nghiệp vụ ngay cả trước khi ta đọc annotation.

## 3. Phân biệt package nghiệp vụ với package kỹ thuật

Một cấu trúc như sau thường gây nhầm lẫn:

```text
com.example.shop
├── ShopApplication.java
├── controller
├── service
├── repository
└── entity
```

Với quy ước mặc định, các package con trực tiếp này có thể được Spring Modulith nhận diện như các application module riêng. Tuy nhiên, `controller`, `service`, `repository` và `entity` thường là các lớp kỹ thuật thuộc nhiều năng lực nghiệp vụ khác nhau, chứ không phải bốn module nghiệp vụ độc lập.

Thay vì chia package theo loại lớp ở cấp root, hãy nhóm chúng dưới module sở hữu nghiệp vụ:

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java
│   ├── web
│   │   └── ProductController.java
│   └── internal
│       ├── ProductService.java
│       ├── ProductRepository.java
│       └── ProductEntity.java
├── orders
│   ├── OrderManagement.java
│   ├── web
│   │   └── OrderController.java
│   └── internal
│       ├── OrderService.java
│       ├── OrderRepository.java
│       └── OrderEntity.java
└── inventory
    ├── StockAvailability.java
    └── internal
        └── StockService.java
```

Trong cấu trúc này, mỗi controller, service và repository nằm trong module nghiệp vụ tương ứng. Nhờ đó, code liên quan đến một năng lực được tập trung cùng nhau và module sở hữu có thể kiểm soát API công khai.

Một package kỹ thuật dùng chung ở cấp root chỉ nên được giữ lại khi nó thực sự là một module có trách nhiệm và hợp đồng riêng. Đừng tạo module `common` hoặc `shared` chỉ để gom những lớp chưa biết đặt ở đâu; hãy xác định rõ quyền sở hữu và hướng phụ thuộc của các thành phần dùng chung.

## 4. Chỉ khai báo @ApplicationModule sau khi đã xác định module root

`@ApplicationModule` cung cấp metadata và quy tắc cho một application module. Annotation này thường được đặt trong file `package-info.java` tại package gốc của module, không phải tại application root package của toàn ứng dụng.

Ví dụ, sau khi xác định `orders` là module nghiệp vụ, ta có thể khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Quản lý đơn hàng",
    allowedDependencies = {"catalog", "inventory::api"}
)
package com.example.shop.orders;
```

Đọc cây package trước giúp ta biết chính xác vị trí đặt annotation: `com.example.shop.orders` là module root, còn `com.example.shop` là application root. `allowedDependencies` phải tham chiếu đúng tên module và named interface đang tồn tại trong mô hình.

Không cần thêm `@ApplicationModule` một cách máy móc vào mọi package con. Trước hết, hãy để cấu trúc package thể hiện module; chỉ bổ sung annotation khi cần đặt metadata hoặc giới hạn phụ thuộc rõ ràng.

## 5. Chỉ khai báo @NamedInterface tại sub-package muốn công khai

Sau khi xác định module root, hãy tìm những sub-package nào cần trở thành API công khai. Theo mặc định, package con của module được xem là nội bộ. Nếu module cần công khai có chọn lọc một nhóm API trong sub-package, hãy dùng `@NamedInterface` ở `package-info.java` của chính sub-package đó.

Ví dụ, cây package có thêm API cho các module khác:

```text
com.example.shop
└── inventory
    ├── StockAvailability.java
    ├── api
    │   ├── package-info.java
    │   └── StockReservation.java
    └── internal
        ├── StockService.java
        └── StockRepository.java
```

Nội dung `inventory/api/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.inventory.api;
```

Khai báo này công khai package `inventory.api` dưới named interface có tên `api`. Một module khác có thể khai báo phụ thuộc vào `inventory::api`. Package `inventory.internal` vẫn là nội bộ vì nó không được đánh dấu là named interface.

Điều quan trọng là annotation được đặt ở đúng package mà nó mô tả. Đặt `@NamedInterface` tại `com.example.shop.inventory` sẽ không có cùng ý nghĩa với việc đặt nó tại `com.example.shop.inventory.api`.

## 6. Đọc cây package và annotation cùng nhau

Khi xem một module, hãy đọc từ ngoài vào trong:

1. Xác định application root package từ lớp khởi động hoặc lớp được truyền cho `ApplicationModules.of(...)`.
2. Liệt kê các package con trực tiếp và xác định package nào đại diện cho năng lực nghiệp vụ.
3. Mở từng module root để xem package nào là API mặc định và package nào là implementation nội bộ.
4. Kiểm tra `package-info.java` tại module root để biết module có `@ApplicationModule` và các quy tắc phụ thuộc nào.
5. Kiểm tra `package-info.java` ở sub-package để biết package nào được mở bằng `@NamedInterface`.

Bảng sau tóm tắt vị trí và ý nghĩa của từng loại:

| Vị trí | Vai trò | Annotation thường gặp |
|---|---|---|
| `com.example.shop` | Application root package | Thường không cần annotation module |
| `com.example.shop.orders` | Module root và API mặc định | `@ApplicationModule` khi cần metadata/quy tắc |
| `com.example.shop.orders.internal` | Implementation nội bộ | Thường không khai báo named interface |
| `com.example.shop.inventory.api` | Sub-package được công khai có chọn lọc | `@NamedInterface("api")` |

Việc đọc từ package root đến sub-package giúp tránh nhầm annotation cấp module với annotation cấp named interface. Đồng thời, ta có thể phát hiện các package kỹ thuật bị đặt nhầm ở cấp root hoặc những package API được công khai rộng hơn dự định.

## 7. Kiểm chứng mô hình sau khi tổ chức package

Sau khi sắp xếp package và thêm annotation cần thiết, hãy kiểm tra mô hình module bằng `verify()`:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kiểm tra này giúp phát hiện các vi phạm như module phụ thuộc vào package nội bộ của module khác, chu trình phụ thuộc hoặc phụ thuộc không nằm trong danh sách được cho phép. Nếu có lỗi, hãy quay lại package tree và xác định xem ranh giới module, vị trí API hay khai báo phụ thuộc có phản ánh đúng thiết kế hay chưa.

Đừng dùng annotation để che đi một package tree chưa hợp lý. Hãy thiết kế cấu trúc theo trách nhiệm nghiệp vụ trước, sau đó dùng annotation để mô tả những ngoại lệ và quy tắc kiến trúc cần thiết. Cách làm này giúp Spring Modulith kiểm chứng một mô hình dễ hiểu, thay vì biến annotation thành cách vá cấu trúc package.

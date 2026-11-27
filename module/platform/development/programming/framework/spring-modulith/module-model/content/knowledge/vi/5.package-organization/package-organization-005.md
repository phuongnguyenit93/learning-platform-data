# API ở root package và implementation ở sub-package

Khi tổ chức một application module của Spring Modulith, cách đặt package giúp thể hiện rõ phần nào là hợp đồng công khai và phần nào là chi tiết triển khai. Theo quy ước mặc định, **package gốc của module (base package) là API công khai**, còn các sub-package được xem là phần nội bộ. Ta có thể dựa vào quy ước này để module khác chỉ phụ thuộc vào những kiểu dữ liệu mà module sở hữu chủ động công bố.

Ví dụ, module `catalog` cung cấp chức năng tra cứu sản phẩm cho module `orders`. `catalog` nên đặt interface mà bên ngoài được phép sử dụng ở package gốc; phần service triển khai, repository và entity được đặt trong các sub-package nội bộ.

## 1. Cấu trúc package thể hiện ranh giới API

Giả sử ứng dụng Spring Boot có cấu trúc:

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java          # API công khai
│   ├── ProductSummary.java          # Kiểu dữ liệu trả về
│   └── internal
│       ├── DefaultProductCatalog.java
│       ├── ProductRepository.java
│       └── ProductEntity.java
└── orders
    └── internal
        └── OrderService.java
```

Trong cấu trúc này:

- `com.example.shop.catalog` là package gốc của module `catalog`. Các kiểu được đặt trực tiếp tại đây tạo thành API mặc định mà module khác có thể sử dụng.
- `com.example.shop.catalog.internal` là sub-package. Nó chứa phần triển khai của `catalog` và được xem là nội bộ theo quy ước mặc định.
- `com.example.shop.orders` là module khác. Mã nguồn của nó nên gọi `ProductCatalog` thay vì phụ thuộc vào `DefaultProductCatalog`, `ProductRepository` hoặc `ProductEntity`.

Ranh giới này giúp người đọc nhận biết hợp đồng của module ngay từ cấu trúc mã nguồn. Khi cần thay đổi cách lưu dữ liệu hoặc thuật toán xử lý, nhóm có thể sửa các lớp trong `internal` mà không buộc module gọi phải thay đổi theo.

## 2. Đặt interface công khai ở package gốc

Hãy thiết kế API theo nghiệp vụ mà module muốn cung cấp. Ví dụ, module `catalog` công khai một interface để tìm thông tin sản phẩm:

```java
package com.example.shop.catalog;

import java.util.Optional;
import java.util.UUID;

public interface ProductCatalog {

    Optional<ProductSummary> findById(UUID productId);
}
```

Kiểu dữ liệu trả về cũng thuộc hợp đồng công khai nên được đặt ở package gốc:

```java
package com.example.shop.catalog;

import java.math.BigDecimal;
import java.util.UUID;

public record ProductSummary(
        UUID id,
        String name,
        BigDecimal price) {
}
```

Hai kiểu này cho module khác biết chức năng `catalog` hỗ trợ và dữ liệu mà nó trả về. Chúng không để lộ cách module truy vấn database hoặc lưu trữ sản phẩm.

## 3. Đặt implementation trong sub-package nội bộ

Phần triển khai interface có thể nằm trong package `internal`:

```java
package com.example.shop.catalog.internal;

import com.example.shop.catalog.ProductCatalog;
import com.example.shop.catalog.ProductSummary;
import org.springframework.stereotype.Service;

import java.util.Optional;
import java.util.UUID;

@Service
class DefaultProductCatalog implements ProductCatalog {

    private final ProductRepository repository;

    DefaultProductCatalog(ProductRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<ProductSummary> findById(UUID productId) {
        return repository.findById(productId)
                .map(product -> new ProductSummary(
                        product.getId(),
                        product.getName(),
                        product.getPrice()));
    }
}
```

`DefaultProductCatalog` là một Spring bean do `@Service` đăng ký, nhưng nó vẫn thuộc package nội bộ của module `catalog`. `ProductRepository` và `ProductEntity` cũng có thể được đặt trong package này hoặc các sub-package nội bộ khác.

Điểm quan trọng là **bean có thể được Spring quản lý trong runtime mà vẫn là implementation nội bộ về mặt kiến trúc**. Việc một lớp có annotation `@Service` không khiến lớp đó tự động trở thành API công khai của application module.

## 4. Module khác chỉ phụ thuộc vào API công khai

Module `orders` sử dụng interface ở package gốc của `catalog`:

```java
package com.example.shop.orders.internal;

import com.example.shop.catalog.ProductCatalog;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
class OrderService {

    private final ProductCatalog productCatalog;

    OrderService(ProductCatalog productCatalog) {
        this.productCatalog = productCatalog;
    }

    void validateProduct(UUID productId) {
        var product = productCatalog.findById(productId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Không tìm thấy sản phẩm"));

        // Tiếp tục xử lý đơn hàng với thông tin sản phẩm.
    }
}
```

Spring inject bean triển khai `ProductCatalog` vào `OrderService`. Mã nguồn của `orders` chỉ biết interface và kiểu dữ liệu công khai. Nó không cần biết bean cụ thể là `DefaultProductCatalog` hay dữ liệu được lấy từ repository nào.

Khi `catalog` thay đổi từ JPA sang một cơ chế lưu trữ khác, miễn là vẫn giữ hợp đồng `ProductCatalog`, module `orders` không phải phụ thuộc vào thay đổi nội bộ đó.

## 5. Vì sao không nên đặt implementation ở package gốc?

Nếu đặt cả API lẫn implementation trong package gốc, tất cả các kiểu đó đều nằm trong vùng API mặc định của module. Người dùng module có thể bắt đầu phụ thuộc vào những lớp vốn chỉ được tạo ra để phục vụ triển khai.

Ví dụ, khi `ProductRepository` hoặc `DefaultProductCatalog` nằm ở `com.example.shop.catalog`, một module khác có thể import trực tiếp chúng. Khi đó, việc thay đổi repository, framework persistence hoặc cách khởi tạo service dễ gây ảnh hưởng lan sang module gọi.

Đặt implementation vào sub-package giúp phân biệt rõ:

| Thành phần | Vị trí đề xuất | Lý do |
|---|---|---|
| Interface nghiệp vụ công khai | Package gốc, ví dụ `catalog` | Là hợp đồng cho module khác |
| DTO hoặc kiểu trả về công khai | Package gốc, ví dụ `catalog` | Là một phần của hợp đồng API |
| Service triển khai interface | Sub-package, ví dụ `catalog.internal` | Chi tiết xử lý của module sở hữu |
| Repository và adapter persistence | Sub-package nội bộ | Không để module khác phụ thuộc vào cách lưu trữ |
| Entity và kiểu dữ liệu persistence | Sub-package nội bộ | Giữ mô hình lưu trữ bên trong module |

Không phải mọi kiểu dữ liệu đều cần được công khai. Chỉ đưa vào package gốc những kiểu mà module thực sự muốn cam kết hỗ trợ cho bên gọi. Đặc biệt, tránh để entity JPA, repository hoặc kiểu phụ thuộc framework trở thành hợp đồng xuyên module nếu bên gọi chỉ cần một API nghiệp vụ đơn giản.

## 6. Spring Modulith kiểm tra việc truy cập sub-package

Trong Java, một lớp `public` ở sub-package vẫn có thể được import về mặt ngôn ngữ. Java coi `com.example.shop.catalog` và `com.example.shop.catalog.internal` là hai package khác nhau, nhưng từ khóa `public` vẫn cho phép lớp ở package khác truy cập lớp công khai. Vì vậy, chỉ dựa vào visibility của Java chưa đủ để thể hiện đầy đủ quy tắc kiến trúc.

Spring Modulith xem các sub-package là nội bộ theo mặc định và có thể phát hiện việc module khác truy cập vào chúng khi ta kiểm tra mô hình:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Nếu `orders` import `com.example.shop.catalog.internal.ProductRepository`, kiểm tra kiến trúc có thể báo lỗi do truy cập package nội bộ của module `catalog`. Khi đó, hãy điều chỉnh bên gọi để dùng API công khai hoặc thay đổi thiết kế ranh giới nếu có lý do nghiệp vụ rõ ràng.

## 7. Khi cần công khai một sub-package

Đôi khi một module cần cung cấp nhiều nhóm API và muốn tổ chức chúng trong sub-package riêng. Spring Modulith hỗ trợ `@NamedInterface` để công khai có chọn lọc một sub-package.

Ví dụ, module `catalog` muốn cung cấp một nhóm API tên `api`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.catalog.api;
```

Khi đó, `catalog.api` trở thành named interface của module. Module khác có thể được cấu hình để phụ thuộc vào `catalog::api` nếu cần. Những sub-package khác vẫn là nội bộ nếu chúng không được công khai bằng cơ chế tương ứng.

Named interface là một lựa chọn khi API cần được nhóm riêng hoặc khi module có nhiều hợp đồng công khai. Với module nhỏ, đặt interface ở package gốc thường đơn giản và dễ hiểu hơn. Dù chọn cách nào, hãy công khai đúng phần hợp đồng mà module muốn duy trì.

## 8. Quy tắc thực hành

Khi tổ chức package cho mỗi application module, hãy bắt đầu bằng một package gốc rõ ràng. Đặt interface nghiệp vụ và kiểu dữ liệu công khai tại đó. Đưa service triển khai, repository, adapter, entity và các chi tiết kỹ thuật vào sub-package nội bộ. Module khác chỉ import các kiểu trong API công khai hoặc named interface đã được khai báo.

Sau đó, dùng `ApplicationModules.of(ShopApplication.class).verify()` trong kiểm thử kiến trúc để phát hiện truy cập trái phép vào sub-package và các vi phạm phụ thuộc khác. Cấu trúc package khi ấy trở thành một phần của hợp đồng kiến trúc có thể kiểm tra tự động, giúp các module phát triển độc lập hơn mà vẫn giữ được ranh giới nghiệp vụ rõ ràng.

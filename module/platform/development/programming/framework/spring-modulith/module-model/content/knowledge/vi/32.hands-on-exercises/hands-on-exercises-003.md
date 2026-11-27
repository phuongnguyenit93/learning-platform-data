# Đặt API package và internal package

Trong bài thực hành này, bạn sẽ tổ chức một application module `catalog` thành hai vùng rõ ràng: package API được phép module khác sử dụng và package internal chỉ phục vụ triển khai bên trong `catalog`. Sau đó, module `orders` sẽ gọi API công khai, còn architecture test sẽ xác nhận rằng nó không thể tham chiếu repository hoặc kiểu triển khai nội bộ.

Mục tiêu không chỉ là sắp xếp class vào hai thư mục. Bạn sẽ dùng `@NamedInterface` để công khai một package con, `allowedDependencies` để giới hạn module tiêu thụ vào đúng hợp đồng và `ApplicationModules.verify()` để biến ranh giới đó thành quy tắc có thể kiểm tra tự động.

## 1. Kết quả cần đạt

Sau khi hoàn thành, cấu trúc phải đáp ứng các điều kiện:

- `catalog.api` là named interface có tên `catalog-api`.
- `catalog.internal` và các package con của nó vẫn là chi tiết triển khai nội bộ.
- `orders` chỉ được phép phụ thuộc `catalog :: catalog-api`.
- `orders` gọi `ProductCatalog`, không gọi `ProductStore` hoặc `ProductRecord`.
- `ApplicationModules.verify()` thành công khi code chỉ dùng API công khai.
- Khi cố ý import một type từ `catalog.internal`, architecture test phát hiện vi phạm.

Thời lượng gợi ý: 45–60 phút. Bài tập dùng Java và cấu trúc package mặc định của Spring Modulith.

## 2. Chuẩn bị cấu trúc project

Giả sử ứng dụng Spring Boot có package gốc `com.acme.shop` và lớp khởi động `ShopApplication`. Theo detection strategy mặc định, `catalog` và `orders` là hai application module vì chúng là package con trực tiếp của root package.

Tạo cấu trúc sau:

```text
src/main/java/com/acme/shop
├── ShopApplication.java
├── catalog
│   ├── package-info.java
│   ├── api
│   │   ├── package-info.java
│   │   ├── ProductCatalog.java
│   │   └── ProductView.java
│   └── internal
│       ├── ProductCatalogService.java
│       └── persistence
│           ├── ProductStore.java
│           ├── ProductRecord.java
│           └── InMemoryProductStore.java
└── orders
    ├── package-info.java
    └── OrderApplicationService.java

src/test/java/com/acme/shop
└── ModuleStructureTests.java
```

Nếu project đã có package khác, giữ chúng trong module sở hữu tương ứng. Trong bài tập này, tập trung vào `catalog` và `orders` để dễ quan sát quan hệ phụ thuộc.

Đảm bảo project có `spring-modulith-core` trên compile classpath và JUnit 5 trong test scope. Nếu muốn mở rộng bài tập sang `@ApplicationModuleTest`, thêm `spring-modulith-starter-test` ở test scope. Nếu project đã dùng Spring Modulith BOM, không khai báo version riêng cho từng artifact.

## 3. Tạo API package cho catalog

API package chứa những type mà module khác được phép tham chiếu. Tạo file `catalog/api/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("catalog-api")
package com.acme.shop.catalog.api;
```

`@NamedInterface("catalog-api")` đưa các type trong package `catalog.api` vào named interface có tên `catalog-api`. Tên này sẽ được dùng trong `allowedDependencies` của module tiêu thụ. Nó không nhất thiết phải trùng với tên package `api`.

Tạo hợp đồng `ProductCatalog.java`:

```java
package com.acme.shop.catalog.api;

import java.util.Optional;

public interface ProductCatalog {

    Optional<ProductView> findBySku(String sku);
}
```

Tạo DTO công khai `ProductView.java`:

```java
package com.acme.shop.catalog.api;

import java.math.BigDecimal;

public record ProductView(
        String sku,
        String displayName,
        BigDecimal price) {
}
```

`ProductCatalog` diễn đạt capability nghiệp vụ mà `catalog` cung cấp. `ProductView` là dữ liệu trả về qua hợp đồng. Cả hai type nằm trong cùng named interface, nên module tiêu thụ có thể dùng cả interface lẫn kiểu dữ liệu xuất hiện trong chữ ký của nó.

Giữ package API nhỏ và ổn định. Không đặt repository, entity persistence, mapper nội bộ hoặc implementation vào package này chỉ vì chúng có modifier `public`.

## 4. Đánh dấu package gốc và package internal

Module `catalog` mặc định có kiểu `CLOSED`. Có thể ghi rõ ý định trong `catalog/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
        type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.acme.shop.catalog;
```

`CLOSED` có nghĩa module khác chỉ được truy cập API của module: package gốc và các named interface đã công khai. Những package con không được đánh dấu named interface là internal. Trong ví dụ, `catalog.internal` không có `@NamedInterface`, nên các type ở đó không được module khác sử dụng.

Không cần tạo `package-info.java` cho `catalog.internal` để tuyên bố nó là internal. Theo quy tắc mặc định, package con không được expose vốn đã là internal. Điều quan trọng là không đánh dấu package đó bằng `@NamedInterface`.

Tạo một abstraction lưu trữ nội bộ trong `catalog/internal/persistence/ProductStore.java`:

```java
package com.acme.shop.catalog.internal.persistence;

import java.util.Optional;

public interface ProductStore {

    Optional<ProductRecord> findBySku(String sku);
}
```

Tạo record nội bộ `ProductRecord.java`:

```java
package com.acme.shop.catalog.internal.persistence;

import java.math.BigDecimal;

public record ProductRecord(
        String sku,
        String name,
        BigDecimal price) {
}
```

Hai type trên có modifier `public` vì chúng được dùng giữa các package con trong cùng module. Modifier `public` chỉ quyết định khả năng truy cập theo Java; nó không tự biến package `catalog.internal.persistence` thành API của application module.

Tạo implementation đơn giản `InMemoryProductStore.java`:

```java
package com.acme.shop.catalog.internal.persistence;

import java.math.BigDecimal;
import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Repository;

@Repository
class InMemoryProductStore implements ProductStore {

    private final Map<String, ProductRecord> products = Map.of(
            "BK-001", new ProductRecord(
                    "BK-001", "Spring Modulith Handbook", new BigDecimal("29.90")),
            "BK-002", new ProductRecord(
                    "BK-002", "Modular Design Notes", new BigDecimal("19.50")));

    @Override
    public Optional<ProductRecord> findBySku(String sku) {
        return Optional.ofNullable(products.get(sku));
    }
}
```

Implementation này chỉ là test fixture đơn giản để tập trung vào package boundary. Trong ứng dụng thật, module có thể thay nó bằng JPA repository, JDBC adapter hoặc một nguồn dữ liệu khác mà không cần thay đổi hợp đồng `ProductCatalog`.

## 5. Nối implementation nội bộ với API

Tạo `catalog/internal/ProductCatalogService.java`:

```java
package com.acme.shop.catalog.internal;

import java.util.Optional;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.catalog.api.ProductView;
import com.acme.shop.catalog.internal.persistence.ProductRecord;
import com.acme.shop.catalog.internal.persistence.ProductStore;
import org.springframework.stereotype.Service;

@Service
class ProductCatalogService implements ProductCatalog {

    private final ProductStore products;

    ProductCatalogService(ProductStore products) {
        this.products = products;
    }

    @Override
    public Optional<ProductView> findBySku(String sku) {
        return products.findBySku(sku)
                .map(this::toView);
    }

    private ProductView toView(ProductRecord product) {
        return new ProductView(
                product.sku(),
                product.name(),
                product.price());
    }
}
```

`ProductCatalogService` là implementation nội bộ của API. Nó có thể dùng `ProductStore` và `ProductRecord` vì các type đó thuộc cùng module `catalog`. Module khác chỉ nhìn thấy `ProductCatalog` và `ProductView` qua named interface.

Spring component scanning vẫn có thể phát hiện `@Service` và `@Repository` trong package con của root application. Việc package là internal theo Spring Modulith không có nghĩa Spring không thể tạo bean từ package đó. Hai khái niệm cần tách biệt:

- Spring Modulith quyết định module khác có được phép phụ thuộc vào type hay không.
- Spring container quyết định bean nào được phát hiện và quản lý trong application context.

## 6. Giới hạn orders vào named interface

Module `orders` cần tra cứu sản phẩm nhưng chỉ được dùng `catalog-api`. Tạo `orders/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "catalog :: catalog-api"
)
package com.acme.shop.orders;
```

Selector gồm module identifier `catalog`, dấu phân cách `::` và tên named interface `catalog-api`. Vì đã khai báo allowlist, module `orders` chỉ được phụ thuộc vào named interface đó trong module `catalog` và các dependency khác được Spring Modulith cho phép theo quy tắc chung, chẳng hạn shared modules được cấu hình.

Tạo `orders/OrderApplicationService.java`:

```java
package com.acme.shop.orders;

import java.util.Optional;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.catalog.api.ProductView;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final ProductCatalog products;

    public OrderApplicationService(ProductCatalog products) {
        this.products = products;
    }

    public Optional<ProductView> findProduct(String sku) {
        return products.findBySku(sku);
    }
}
```

`orders` không biết `ProductCatalogService` được triển khai ra sao, dữ liệu được lưu bằng JPA hay in-memory, hoặc `ProductRecord` có những field nào. Nó chỉ phụ thuộc vào hợp đồng công khai mà capability `catalog` cam kết cung cấp.

## 7. Chạy architecture verification

Tạo `src/test/java/com/acme/shop/ModuleStructureTests.java`:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTests {

    @Test
    void verifiesApiAndInternalPackages() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi code chỉ tham chiếu `catalog.api`, verification phải thành công. Spring Modulith kiểm tra các quy tắc chính:

- Không có chu trình phụ thuộc giữa application module.
- Module khác chỉ tham chiếu API được công khai của `catalog`.
- Dependency của `orders` tuân thủ `allowedDependencies`.

Nếu test thất bại, đọc toàn bộ `Violations`. Kiểm tra module nguồn, module đích, type nguồn và type đích trước khi sửa code. Không nên mở module thành `OPEN` chỉ để làm cho test vượt qua, vì như vậy sẽ cho phép truy cập rộng vào internal package.

## 8. Thử tạo một dependency vi phạm

Sau khi kiểm tra trường hợp hợp lệ, cố ý tạo một thay đổi để quan sát ranh giới được bảo vệ.

Trong `OrderApplicationService`, thêm import và constructor dependency tham chiếu tới repository nội bộ. Ví dụ phần class sau khi sửa tạm thời:

```java
package com.acme.shop.orders;

import java.util.Optional;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.catalog.api.ProductView;
import com.acme.shop.catalog.internal.persistence.ProductStore;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final ProductCatalog products;
    private final ProductStore internalStore;

    public OrderApplicationService(
            ProductCatalog products,
            ProductStore internalStore) {
        this.products = products;
        this.internalStore = internalStore;
    }

    public Optional<ProductView> findProduct(String sku) {
        return products.findBySku(sku);
    }
}
```

Vì interface được khai báo `public`, đoạn code có thể biên dịch và Spring có thể inject bean nếu implementation được đăng ký. Tuy nhiên, Spring Modulith sẽ phát hiện `orders` đang truy cập package nội bộ `catalog.internal.persistence`, đồng thời dependency đó không thuộc allowlist `catalog :: catalog-api`.

Kết quả mong đợi là `ApplicationModules.verify()` ném `Violations`, với thông báo chỉ ra type không được expose hoặc dependency không được phép. Nội dung cụ thể tùy phiên bản và các vi phạm được phát hiện đồng thời.

Sau khi quan sát kết quả, xóa import và field vi phạm. Chạy lại architecture test để xác nhận trạng thái hợp lệ đã được khôi phục.

Điểm cần ghi nhớ: Java compiler kiểm tra visibility của class và member; Spring Modulith kiểm tra visibility ở cấp application module. Một type có thể `public` trong Java nhưng vẫn là internal của module.

## 9. Phân biệt API package và internal package

| Đặc điểm | `catalog.api` | `catalog.internal` |
|---|---|---|
| Có `@NamedInterface` | Có, tên `catalog-api` | Không |
| Module khác được tham chiếu | Có, nếu dependency được phép | Không |
| Chứa hợp đồng nghiệp vụ | Có | Không nên |
| Chứa repository và persistence detail | Không | Có |
| Được phép thay đổi implementation tự do | Hạn chế bởi hợp đồng công khai | Có thể thay đổi nội bộ nếu không làm hỏng hành vi module |
| Được Spring tạo bean | Có thể | Có thể |

Không cần đặt mọi class `public` vào API package. Một implementation có thể là package-private nếu các class cộng tác nằm cùng Java package; các type cần được sử dụng từ package khác trong cùng module có thể cần modifier `public`. Dù vậy, package internal vẫn được Spring Modulith bảo vệ khỏi module khác.

## 10. Mở rộng bài tập

Sau khi hoàn thành phần chính, thử các thay đổi sau:

1. **Tạo named interface thứ hai:** thêm `catalog.spi` với `@NamedInterface("catalog-spi")`, rồi đặt một hợp đồng tích hợp riêng trong đó.
2. **Thu hẹp allowlist:** giữ `orders` chỉ được phụ thuộc `catalog :: catalog-api`; thử import type từ `catalog.spi` và quan sát verification thất bại.
3. **Thử wildcard:** đổi allowlist thành `catalog :: *` để cho phép mọi named interface của `catalog`, rồi so sánh với `catalog :: **`, vốn bao gồm cả base package API.
4. **Di chuyển implementation:** chuyển `ProductCatalogService` sang package khác bên trong `catalog`, giữ nguyên `ProductCatalog` và xác nhận module `orders` không cần thay đổi.
5. **Đổi persistence:** thay `InMemoryProductStore` bằng adapter khác mà không thay public API. Kiểm tra caller vẫn chỉ phụ thuộc `ProductCatalog`.

Sau mỗi thay đổi, xác định trước kết quả mong đợi rồi chạy lại architecture test. Ghi lại thay đổi nào ảnh hưởng module dependency và thay đổi nào chỉ ảnh hưởng implementation nội bộ.

## 11. Bảng xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `orders` không import được `ProductCatalog` | Package API chưa được đánh dấu named interface hoặc tên package sai | Kiểm tra `catalog/api/package-info.java` và package declaration |
| `verify()` báo dependency không được phép | `allowedDependencies` thiếu hoặc sai tên module/interface | Dùng đúng `catalog :: catalog-api` |
| `verify()` báo truy cập non-exposed type | Caller import type từ `catalog.internal` | Chuyển caller sang API hoặc thêm một named interface có chủ đích |
| Import internal vẫn compile nhưng architecture test fail | Java `public` không đồng nghĩa module API | Giữ internal package và sửa dependency của caller |
| Spring không tạo `ProductCatalogService` | Component scan hoặc bean configuration không bao phủ package | Kiểm tra Spring Boot root package và component scan; không đổi internal thành API để sửa bean scan |
| Named interface expose quá nhiều type | Package API chứa cả helper hoặc implementation | Chuyển chi tiết triển khai sang internal package |
| Đổi tên named interface làm test fail | Selector trong `allowedDependencies` vẫn dùng tên cũ | Cập nhật metadata của module tiêu thụ và kiểm tra lại |

## 12. Tiêu chí hoàn thành

- [ ] `catalog.api` được đánh dấu `@NamedInterface("catalog-api")`.
- [ ] `ProductCatalog` và `ProductView` nằm trong API package.
- [ ] `ProductStore`, `ProductRecord` và implementation nằm trong internal package.
- [ ] `orders` khai báo `allowedDependencies = "catalog :: catalog-api"`.
- [ ] `OrderApplicationService` chỉ import type từ `catalog.api`.
- [ ] Architecture test chạy thành công khi dependency hợp lệ.
- [ ] Đã thử import `ProductStore` từ `orders` và quan sát `Violations`.
- [ ] Đã xóa dependency vi phạm và chạy lại verification thành công.
- [ ] Đã giải thích được khác biệt giữa Java visibility và module visibility.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals: Named Interfaces and Explicit Dependencies](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [NamedInterface annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [ApplicationModule annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)

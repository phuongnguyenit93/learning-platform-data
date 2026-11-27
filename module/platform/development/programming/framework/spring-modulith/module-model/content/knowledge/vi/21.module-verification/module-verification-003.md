# Chỉ truy cập module khác qua API

Trong một modular monolith, các application module có thể chạy trong cùng một Spring Boot application, nhưng mỗi module vẫn cần giữ quyền sở hữu đối với dữ liệu và cách triển khai của mình. Khi module `orders` cần chức năng từ `catalog`, nó nên sử dụng hợp đồng mà `catalog` công khai, thay vì import repository, entity hoặc service nội bộ của module đó.

Spring Modulith mô hình hóa quy tắc này bằng package arrangement. Theo mặc định, các type nằm trực tiếp trong base package của module tạo thành API mặc định; các sub-package là nội bộ, trừ những package được công khai có chủ đích bằng `@NamedInterface`. `ApplicationModules.verify()` có thể phát hiện khi một module truy cập sub-package nội bộ của module khác.

## 1. Cấu trúc package xác định API và phần nội bộ

Giả sử ứng dụng bán hàng có cấu trúc:

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java          # API mặc định
│   ├── ProductSummary.java          # Kiểu dữ liệu công khai
│   └── internal
│       ├── DefaultProductCatalog.java
│       ├── ProductEntity.java
│       └── ProductRepository.java
└── orders
    └── internal
        └── OrderService.java
```

Các package con trực tiếp `catalog` và `orders` là application module. Trong module `catalog`:

- `com.example.shop.catalog` là base package và cung cấp API mặc định.
- `com.example.shop.catalog.internal` là sub-package nội bộ.
- Module khác có thể phụ thuộc vào type công khai ở base package.
- Module khác không được truy cập type thuộc `internal` theo quy tắc closed module mặc định.

Ranh giới này không phụ thuộc vào việc class được đánh dấu `public` hay `@Service`. Nó được xác định bởi mô hình package và các quy tắc kiến trúc mà Spring Modulith kiểm tra.

## 2. Công khai hợp đồng mà consumer thực sự cần

Module `catalog` nên công khai một hợp đồng theo nghiệp vụ, chẳng hạn khả năng tra cứu thông tin sản phẩm:

```java
package com.example.shop.catalog;

import java.util.Optional;
import java.util.UUID;

public interface ProductCatalog {

    Optional<ProductSummary> findById(UUID productId);
}
```

Kiểu dữ liệu trả về cũng thuộc hợp đồng công khai:

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

Hai type này cho module `orders` biết chức năng được hỗ trợ và dữ liệu có thể sử dụng. Chúng không để lộ entity JPA, repository hoặc cách `catalog` truy vấn dữ liệu.

Implementation được giữ trong sub-package:

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

Spring có thể quản lý `DefaultProductCatalog` như một bean, nhưng class đó vẫn là implementation nội bộ về mặt kiến trúc. Consumer không cần biết implementation cụ thể nào được inject.

## 3. Truy cập implementation nội bộ là vi phạm boundary

Ví dụ sau là cách phụ thuộc không nên có:

```java
package com.example.shop.orders.internal;

import com.example.shop.catalog.internal.ProductRepository;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final ProductRepository products;

    OrderService(ProductRepository products) {
        this.products = products;
    }
}
```

`ProductRepository` thuộc `catalog.internal`. `orders` đang phụ thuộc vào cách `catalog` lưu trữ sản phẩm thay vì phụ thuộc vào hợp đồng nghiệp vụ của catalog.

Nếu `ProductRepository` là type `public`, Java compiler có thể cho phép import. Tuy nhiên, Spring Modulith xem đây là truy cập sub-package nội bộ và có thể báo vi phạm khi chạy `ApplicationModules.verify()`.

Consumer nên phụ thuộc vào API:

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

        // Dùng dữ liệu công khai để tiếp tục xử lý đơn hàng.
    }
}
```

Khi `catalog` thay JPA bằng JDBC hoặc một adapter khác, `orders` không cần thay đổi nếu hợp đồng `ProductCatalog` vẫn giữ nguyên ý nghĩa.

## 4. Java visibility không thay thế quy tắc module

Java và Spring Modulith kiểm soát hai khía cạnh khác nhau:

| Cơ chế | Kiểm soát điều gì? |
|---|---|
| `public`, `protected`, package-private, `private` | Khả năng truy cập type và member theo ngôn ngữ Java |
| Base package và sub-package | Ranh giới API mặc định và phần nội bộ của application module |
| `@NamedInterface` | Công khai có chọn lọc một sub-package thành API của module |
| `allowedDependencies` | Module nguồn được phép phụ thuộc vào module hoặc named interface nào |
| `ApplicationModules.verify()` | Kiểm tra các quy tắc module trên dependency thực tế được phát hiện |

Một class `public` trong `catalog.internal` vẫn có thể bị Spring Modulith xem là nội bộ. Ngược lại, một class package-private vẫn không thể được Java truy cập từ package khác chỉ vì module đã công khai package đó. Muốn dùng API xuyên module, type phải có visibility Java phù hợp và nằm trong phần API được Spring Modulith công nhận.

Vì vậy, chỉ dùng `public` không đủ để công khai API kiến trúc. Hãy đặt type đúng package và dùng verification để bảo vệ ranh giới.

## 5. Công khai sub-package bằng Named Interface khi cần

Nếu module có nhiều nhóm API, ta không cần đưa tất cả type vào base package. Spring Modulith cho phép công khai một sub-package bằng `@NamedInterface`.

Ví dụ module `catalog` có nhóm API truy vấn:

```text
com.example.shop.catalog
├── ProductCatalog.java
├── query
│   ├── package-info.java
│   ├── ProductLookup.java
│   └── ProductSummary.java
└── internal
    ├── ProductRepository.java
    └── DefaultProductCatalog.java
```

Nội dung `query/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("query")
package com.example.shop.catalog.query;
```

Module khác có thể sử dụng type trong `catalog.query` vì package này đã được công khai có tên. Những package khác như `catalog.internal` vẫn là nội bộ nếu không được mở bằng một khai báo tương ứng.

Named interface giúp module sở hữu phân chia API theo nhóm có ý nghĩa. Chỉ nên công khai những hợp đồng mà consumer thực sự cần; không đánh dấu `internal`, `persistence` hoặc `adapter` thành named interface chỉ để làm cho dependency hiện tại qua được kiểm tra.

## 6. Kết hợp API với allowedDependencies

API trả lời câu hỏi **module khác được phép tham chiếu type nào của module này**. `allowedDependencies` trả lời câu hỏi **module hiện tại được phép phụ thuộc vào module hoặc named interface nào**. Hai quy tắc bổ sung cho nhau.

Ví dụ, module `orders` chỉ cần API truy vấn của `catalog`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog::query"
)
package com.example.shop.orders;
```

Khai báo này giới hạn dependency của `orders` vào named interface `query` của `catalog`. Nếu `orders` chỉ được phép dùng API ở base package của `catalog`, có thể khai báo tên module `catalog`.

Một số điểm cần phân biệt:

- Nếu không khai báo `allowedDependencies`, module không bị giới hạn bằng allow-list này; quy tắc truy cập API/internal vẫn được áp dụng.
- Nếu khai báo `allowedDependencies = {}`, module không được phép phụ thuộc vào application module khác.
- `allowedDependencies = "catalog"` không làm cho `catalog.internal` trở thành API.
- `allowedDependencies = "catalog::query"` cho phép nhóm API `query`, nhưng không mở các sub-package nội bộ khác.

Do đó, allow-list rộng không thể thay thế thiết kế API. Một module có thể được phép phụ thuộc vào `catalog` nhưng vẫn vi phạm nếu import trực tiếp type từ `catalog.internal`.

## 7. Event cũng phải sử dụng hợp đồng công khai

Giao tiếp qua event không loại bỏ yêu cầu về API. Event type được module phát hành sở hữu và cần được công khai ở base package hoặc named interface để module khác có thể tham chiếu.

Ví dụ, module `orders` công bố event:

```java
package com.example.shop.orders;

import java.util.UUID;

public record OrderCompleted(UUID orderId) {
}
```

Module `inventory` lắng nghe event:

```java
package com.example.shop.inventory.internal;

import com.example.shop.orders.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryEventHandler {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Cập nhật tồn kho sau khi đơn hàng hoàn tất.
    }
}
```

`inventory` phụ thuộc vào hợp đồng event `OrderCompleted` của `orders`. Nó không cần truy cập implementation nội bộ của `orders`. Hướng dependency do listener tạo ra vẫn phải phù hợp với `allowedDependencies` và đồ thị module.

## 8. Kiểm tra quy tắc chỉ truy cập API bằng verify()

Spring Modulith cung cấp `ApplicationModules.verify()` để kiểm tra cấu trúc và dependency giữa các application module. Có thể đặt bài kiểm tra trong test sources:

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

Khi test chạy, Spring Modulith phân tích các dependency giữa module và kiểm tra những quy tắc như:

- Không truy cập sub-package nội bộ của closed module khác.
- Chỉ phụ thuộc vào module hoặc named interface được allow-list cho phép, nếu module có khai báo giới hạn.
- Không tạo chu trình dependency giữa các module theo quy tắc verification.

Nếu `orders` import `catalog.internal.ProductRepository`, verification có thể thất bại dù Java compiler chấp nhận class đó. Hãy thay import bằng API công khai hoặc xem lại quyền sở hữu nghiệp vụ nếu consumer thực sự cần một khả năng chưa được catalog cung cấp.

## 9. Open module là ngoại lệ cần kiểm soát

`@ApplicationModule(type = Type.OPEN)` nới lỏng quy tắc truy cập internal package: các type trong sub-package được đưa vào unnamed interface, trừ type hoặc package được gán named interface riêng. Open module cũng bị loại khỏi thuật toán phát hiện chu trình.

Open module có thể hữu ích khi chuyển đổi một codebase legacy, trong đó nhiều module đang truy cập lẫn nhau qua các package con. Tuy nhiên, nó làm giảm khả năng bảo vệ boundary. Với module mới hoặc đã có API rõ ràng, nên giữ `CLOSED` mặc định và chỉ công khai các hợp đồng cần thiết.

Không nên đánh dấu module là `OPEN` chỉ để bỏ qua một lỗi truy cập internal. Hãy xem lỗi verification là tín hiệu để xác định API còn thiếu hoặc dependency đang đi sai hướng.

## 10. Quy trình áp dụng trong dự án

Khi một module cần sử dụng chức năng của module khác, hãy thực hiện theo thứ tự:

1. Xác định module sở hữu hành vi hoặc dữ liệu cần dùng.
2. Thiết kế interface, DTO hoặc event type diễn đạt hợp đồng nghiệp vụ.
3. Đặt hợp đồng ở base package hoặc named interface của module sở hữu.
4. Giữ service triển khai, repository, entity và adapter trong sub-package nội bộ.
5. Cập nhật consumer để chỉ import các type thuộc API công khai.
6. Khai báo `allowedDependencies` đủ hẹp nếu muốn giới hạn hướng phụ thuộc.
7. Chạy `ApplicationModules.of(ShopApplication.class).verify()` trong kiểm thử kiến trúc.
8. Khi verification thất bại, truy vết source type và target type, rồi sửa hợp đồng hoặc hướng phụ thuộc thay vì mở rộng internal package một cách tùy tiện.

Một boundary có ý nghĩa khi consumer chỉ biết hợp đồng mà nó cần, module sở hữu vẫn tự do thay đổi implementation và các quy tắc đó được kiểm tra tự động. Spring Modulith giúp phát hiện những truy cập xuyên module không đúng ý định, để modular monolith duy trì được ranh giới nghiệp vụ khi codebase phát triển.

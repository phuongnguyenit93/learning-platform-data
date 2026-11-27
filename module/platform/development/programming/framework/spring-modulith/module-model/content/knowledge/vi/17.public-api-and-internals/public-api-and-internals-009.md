# Thiết kế API đủ nhỏ để boundary có ý nghĩa

Một application module chỉ có boundary rõ ràng khi module khác biết **đủ những gì cần dùng** và không phải dựa vào chi tiết triển khai bên trong. Vì vậy, API công khai cần đủ để hoàn thành các use case của bên gọi, nhưng không nên phơi bày repository, entity, service nội bộ hoặc những thao tác mà bên ngoài không có lý do nghiệp vụ để sử dụng.

Trong Spring Modulith, package arrangement giúp thể hiện ranh giới này: type nằm trực tiếp trong base package của module thuộc API mặc định; các sub-package được xem là nội bộ, trừ khi được công khai có chủ đích bằng `@NamedInterface`. Thiết kế API nhỏ và có tính gắn kết làm cho quy ước package trở thành một boundary có ý nghĩa, thay vì chỉ là cách sắp xếp thư mục.

## 1. API nhỏ nghĩa là gì?

API nhỏ không có nghĩa là một interface chỉ được phép có một method hoặc một module chỉ được công khai một class. API nhỏ là API chỉ chứa những hợp đồng mà consumer thực sự cần để thực hiện trách nhiệm của mình.

Một API tốt thường có các đặc điểm:

- **Theo use case:** method diễn đạt hành động hoặc truy vấn có ý nghĩa nghiệp vụ.
- **Có tính gắn kết:** các method và kiểu dữ liệu trong cùng hợp đồng phục vụ một năng lực rõ ràng.
- **Ít rò rỉ triển khai:** consumer không cần biết module lưu dữ liệu, truy vấn database hay tích hợp framework ra sao.
- **Ổn định:** thay đổi nội bộ của module ít làm ảnh hưởng đến consumer.
- **Có chủ sở hữu:** module công khai API chịu trách nhiệm về ý nghĩa, hành vi và khả năng tương thích của hợp đồng đó.

Hãy đánh giá API bằng câu hỏi: nếu thay implementation bên trong module, consumer có còn hoạt động mà không cần sửa code không? Nếu câu trả lời thường xuyên là không, boundary đang để lộ quá nhiều chi tiết.

## 2. Bắt đầu từ nhu cầu của consumer

Giả sử hệ thống bán hàng có module `catalog` và module `orders`. Khi tạo đơn hàng, `orders` cần biết sản phẩm có tồn tại và có được phép bán hay không. Nó không cần truy vấn bảng sản phẩm, đọc entity JPA hoặc tự áp dụng quy tắc nội bộ của catalog.

Một cấu trúc package có thể như sau:

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java          # API công khai
│   ├── ProductSummary.java          # Dữ liệu công khai
│   └── internal
│       ├── DefaultProductCatalog.java
│       ├── ProductEntity.java
│       └── ProductRepository.java
└── orders
    └── internal
        └── OrderService.java
```

Consumer chỉ cần một hợp đồng mô tả khả năng tra cứu sản phẩm:

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

`orders` nhận đủ thông tin cần thiết để tạo dòng đơn hàng. Nó không nhận `ProductEntity`, `ProductRepository` hoặc một object persistence chứa cả những trường nội bộ không liên quan.

## 3. Tránh API kiểu “mở toàn bộ module”

Một API quá rộng thường bắt đầu bằng việc đưa service tổng quát hoặc lớp persistence ra package gốc:

```java
// Ví dụ thiết kế không nên công khai
public interface CatalogService {

    ProductEntity findEntity(UUID id);

    ProductRepository repository();

    void save(ProductEntity entity);

    void delete(UUID id);

    List<ProductEntity> findAllEntities();
}
```

Consumer có thể bắt đầu phụ thuộc vào entity, repository và thao tác quản trị mà nó không sở hữu. Sau đó, catalog khó thay đổi cách lưu trữ hoặc quy tắc nghiệp vụ vì nhiều module đã dựa vào những chi tiết này.

Thay vào đó, hãy công khai các hành vi theo nhu cầu thực tế. Ví dụ, `orders` cần tra cứu sản phẩm để xác nhận đơn hàng, nên `ProductCatalog` chỉ cần cung cấp truy vấn phù hợp. Nếu một consumer khác cần kiểm tra khả năng bán, có thể thêm một capability có tên và hợp đồng rõ ràng, hoặc mở rộng hợp đồng hiện tại nếu hai thao tác thực sự thuộc cùng một trách nhiệm.

Không nên tách mỗi method thành một interface chỉ để làm API trông nhỏ. Một API tốt cần cân bằng giữa kích thước và tính gắn kết: các thao tác cùng phục vụ một năng lực có thể nằm trong cùng hợp đồng; các năng lực có vòng đời hoặc consumer khác nhau nên được xem xét tách riêng.

## 4. Giữ implementation trong sub-package

Phần triển khai API nên nằm trong sub-package nội bộ:

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

Repository và entity cũng thuộc phần nội bộ:

```java
package com.example.shop.catalog.internal;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.UUID;

interface ProductRepository extends JpaRepository<ProductEntity, UUID> {
}
```

Lớp `DefaultProductCatalog` có thể là Spring bean nhờ `@Service`, nhưng vẫn là implementation nội bộ về mặt kiến trúc. Việc Spring quản lý một bean không làm cho class đó trở thành API công khai của application module.

Consumer chỉ tham chiếu hợp đồng:

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

Nhờ dependency injection, Spring cung cấp implementation tương ứng. Module `orders` không cần biết `catalog` đang dùng JPA, JDBC hay một nguồn dữ liệu khác.

## 5. Công khai vừa đủ kiểu dữ liệu

Một API không chỉ gồm interface hoặc class service. Mọi type xuất hiện trong chữ ký method đều trở thành một phần của hợp đồng mà consumer cần hiểu.

Ví dụ, nếu API trả về `ProductEntity`, consumer có thể bị ràng buộc vào:

- Tên và cấu trúc bảng hoặc quan hệ persistence.
- Annotation JPA và quy tắc lazy loading.
- Các trường nội bộ chỉ phục vụ catalog.
- Cách module quản lý trạng thái và cập nhật entity.

Thay bằng DTO hoặc value type được thiết kế cho use case bên ngoài. DTO nên chỉ chứa dữ liệu consumer cần; không sao chép toàn bộ entity một cách máy móc.

Tương tự, tránh để chữ ký API phụ thuộc trực tiếp vào kiểu framework nếu consumer không cần biết framework đó. Ví dụ, một module thường nên trả về `Optional<ProductSummary>` hoặc một kiểu kết quả nghiệp vụ thay vì trả về `Page<Entity>`, `JpaRepository` hay một kiểu response gắn chặt với tầng web.

Đối với lỗi, hãy chọn hợp đồng rõ ràng: exception nghiệp vụ có ý nghĩa, kiểu kết quả biểu đạt trường hợp không thành công, hoặc một cách xử lý nhất quán của ứng dụng. Đừng để consumer phải diễn giải exception persistence như `DataIntegrityViolationException` để quyết định nghiệp vụ.

## 6. Dùng base package hoặc named interface có chủ đích

Theo quy ước mặc định của Spring Modulith, các type trực tiếp trong base package là API mặc định (unnamed interface). Các sub-package là nội bộ. Vì vậy, API nhỏ có thể được đặt trực tiếp trong base package khi module chỉ có một nhóm hợp đồng đơn giản.

Nếu module có nhiều nhóm API riêng biệt, hãy dùng named interface để công khai có chọn lọc:

```text
com.example.shop.catalog
├── package-info.java
├── ProductCatalog.java
├── query
│   ├── package-info.java
│   ├── ProductLookup.java
│   └── ProductSummary.java
├── administration
│   ├── package-info.java
│   ├── ProductAdministration.java
│   └── ProductUpdate.java
└── internal
    ├── ProductRepository.java
    └── DefaultProductCatalog.java
```

Khai báo nhóm API truy vấn:

```java
@org.springframework.modulith.NamedInterface("query")
package com.example.shop.catalog.query;
```

Khai báo nhóm API quản trị:

```java
@org.springframework.modulith.NamedInterface("administration")
package com.example.shop.catalog.administration;
```

Consumer có thể chỉ được phép phụ thuộc vào nhóm truy vấn:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog::query"
)
package com.example.shop.orders;
```

Điều này thể hiện rõ `orders` chỉ cần hợp đồng tra cứu. Module đó không được phép dùng API quản trị nếu không có lý do và quyền phụ thuộc tương ứng.

Không cần tạo named interface cho mọi package. Chỉ công khai nhóm API khi có ranh giới consumer hoặc trách nhiệm khác biệt đủ rõ. Những package như `internal`, `persistence`, `adapter` nên tiếp tục được giữ kín.

## 7. Boundary tốt làm giảm ảnh hưởng của thay đổi

Hãy xem một số thay đổi có thể xảy ra bên trong `catalog`:

| Thay đổi nội bộ | Consumer có cần thay đổi không? |
|---|---|
| Chuyển từ JPA sang JDBC | Không, nếu API và ý nghĩa dữ liệu giữ nguyên |
| Đổi tên `ProductEntity` | Không, nếu entity không xuất hiện trong API |
| Thay repository bằng client gọi dịch vụ khác | Không, nếu hợp đồng công khai được duy trì |
| Thay cấu trúc package `internal` | Không, nếu consumer không import sub-package nội bộ |
| Đổi tên hoặc xóa method công khai | Có thể có, vì đây là thay đổi hợp đồng |
| Xóa field khỏi `ProductSummary` đang được consumer sử dụng | Có thể có, vì DTO là một phần API |

API nhỏ không làm cho mọi thay đổi trở nên miễn phí. Nó giúp giới hạn số thay đổi có thể lan sang consumer và làm rõ những gì module sở hữu cam kết duy trì.

Khi cần thay đổi hợp đồng, hãy cân nhắc khả năng tương thích: thêm method hoặc field có tương thích với consumer hiện tại không, giá trị mới có cần mặc định không, và có cần một giai đoạn chuyển đổi trước khi xóa API cũ không. Với một modular monolith, không nhất thiết phải áp dụng versioning HTTP cho mọi Java API nội bộ, nhưng vẫn cần quản lý thay đổi hợp đồng giữa các module.

## 8. Kiểm tra boundary bằng Spring Modulith

Trong Java, một class `public` ở sub-package vẫn có thể được import về mặt ngôn ngữ. Vì vậy, visibility của Java không đủ để bảo vệ ranh giới module. Spring Modulith có thể kiểm tra việc module khác truy cập sub-package nội bộ.

Tạo bài kiểm tra kiến trúc:

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

Nếu `orders` import `com.example.shop.catalog.internal.ProductRepository`, verification có thể báo lỗi vì `orders` đang truy cập package nội bộ của `catalog`. Nếu `orders` chỉ dùng `ProductCatalog` ở base package hoặc named interface đã được cho phép, dependency phù hợp với boundary đã mô hình hóa.

Có thể bổ sung test để xác nhận API công khai có chứa type mong đợi:

```java
package com.example.shop;

import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.shop.catalog.query.ProductLookup;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class CatalogApiTests {

    @Test
    void productLookupIsPartOfCatalogQueryInterface() {
        var modules = ApplicationModules.of(ShopApplication.class);

        var catalog = modules.getModuleByType(ProductLookup.class)
                .orElseThrow();

        boolean exposed = catalog.getNamedInterfaces().stream()
                .anyMatch(namedInterface ->
                        namedInterface.isNamed()
                                && namedInterface.getName().equals("query")
                                && namedInterface.contains(ProductLookup.class));

        assertTrue(exposed);
    }
}
```

Test thứ hai kiểm tra type cụ thể thuộc named interface mong đợi. Nó hữu ích khi API package là một phần quan trọng của hợp đồng và nhóm muốn phát hiện việc di chuyển hoặc bỏ annotation ngoài ý muốn.

## 9. Checklist thiết kế API đủ nhỏ

Trước khi công khai một type, hãy kiểm tra:

| Câu hỏi | Nếu câu trả lời là “không” |
|---|---|
| Có consumer ngoài module thực sự cần type này không? | Giữ type ở sub-package nội bộ |
| Type biểu đạt khái niệm hoặc use case ổn định không? | Thiết kế lại hợp đồng theo nhu cầu nghiệp vụ |
| Consumer có thể dùng type mà không biết persistence/framework nội bộ không? | Thay entity hoặc framework type bằng DTO/value type phù hợp |
| Các method trong cùng API có cùng trách nhiệm không? | Tách nhóm capability nếu chúng phục vụ mục tiêu khác nhau |
| Có thể thay implementation mà không sửa consumer không? | Giảm rò rỉ implementation khỏi chữ ký API |
| Dependency được giới hạn vào đúng named interface cần thiết không? | Thu hẹp `allowedDependencies` |

Không phải mọi module đều cần named interface. Một module nhỏ có thể chỉ có một vài type ở base package. Một module lớn hơn có thể công khai nhiều nhóm API riêng. Điều quyết định là consumer chỉ nhìn thấy hợp đồng cần thiết và các nhóm API có ý nghĩa rõ ràng.

## 10. Quy trình thực hành

Khi thiết kế API cho một application module:

1. Liệt kê các consumer và use case mà họ cần thực hiện.
2. Xác định những hành vi và dữ liệu tối thiểu để hoàn thành các use case đó.
3. Thiết kế interface, DTO hoặc value type diễn đạt hợp đồng nghiệp vụ.
4. Đặt API ở base package hoặc named interface; giữ implementation trong sub-package.
5. Cập nhật consumer để chỉ phụ thuộc vào API công khai.
6. Dùng `allowedDependencies` để giới hạn module và named interface mà consumer được phép dùng.
7. Chạy `ApplicationModules.verify()` và các test hợp đồng cần thiết.
8. Khi thay đổi API, đánh giá tác động tới consumer và có kế hoạch chuyển đổi phù hợp.

Boundary có ý nghĩa khi API đủ nhỏ để module sở hữu có thể thay đổi implementation độc lập, đồng thời đủ đầy đủ để consumer hoàn thành công việc của mình. Spring Modulith giúp biến boundary đó thành quy tắc có thể kiểm tra; chất lượng của boundary vẫn đến từ việc chọn đúng hợp đồng và quyền sở hữu nghiệp vụ.

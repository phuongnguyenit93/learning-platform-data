# Chia technical layer thành capability module

Một ứng dụng Spring Boot cũ thường được tổ chức theo technical layer: tất cả controller nằm trong `controller`, tất cả service nằm trong `service`, repository nằm trong `repository`, còn entity nằm trong `model`. Cách chia này giúp nhận ra loại công việc của một class, nhưng không cho thấy class nào cùng chịu trách nhiệm cho một năng lực nghiệp vụ. Khi thay đổi một capability như đặt hàng, developer phải lần qua nhiều package kỹ thuật và có thể vô tình làm ảnh hưởng đến capability khác.

Với modular monolith, có thể chuyển từ cách chia ngang theo kỹ thuật sang cách chia dọc theo business capability. Mỗi capability trở thành một application module và chứa các thành phần cần thiết để thực hiện trách nhiệm của nó: adapter đầu vào, application service, domain model và persistence adapter. Các module giao tiếp qua API được công khai hoặc application event, còn chi tiết triển khai vẫn nằm trong module sở hữu.

## 1. Nhận diện vấn đề của technical-layer package

Giả sử ứng dụng bán hàng có cấu trúc:

```text
com.acme.shop
├── ShopApplication.java
├── controller
│   ├── OrderController.java
│   ├── ProductController.java
│   └── CustomerController.java
├── service
│   ├── OrderService.java
│   ├── ProductService.java
│   └── CustomerService.java
├── repository
│   ├── OrderRepository.java
│   ├── ProductRepository.java
│   └── CustomerRepository.java
└── model
    ├── Order.java
    ├── Product.java
    └── Customer.java
```

Đây là cách tổ chức theo technical layer. Các class cùng capability nằm rải rác ở nhiều package. Một thay đổi trong quy trình đặt hàng có thể yêu cầu sửa controller, service, repository và model ở bốn vị trí khác nhau.

Các vấn đề thường xuất hiện khi codebase lớn dần:

- **Khó xác định quyền sở hữu:** `Product` được dùng ở nhiều service nên không rõ module nào chịu trách nhiệm thay đổi mô hình sản phẩm.
- **Phụ thuộc chéo dễ tăng:** service có thể gọi repository của capability khác vì tất cả repository nằm trong package chung và được import thuận tiện.
- **Khó giới hạn API:** package `service` hoặc `repository` thường chứa cả class được chia sẻ và class chỉ phục vụ nội bộ.
- **Thay đổi lan rộng:** developer phải hiểu nhiều technical layer trước khi hoàn thành một thay đổi nghiệp vụ nhỏ.
- **Khó kiểm chứng ranh giới:** package tree không thể hiện trực tiếp `orders`, `catalog` và `customers` là những đơn vị kiến trúc độc lập.

Vấn đề không nằm ở việc có controller, service hay repository. Những thành phần đó vẫn cần thiết. Vấn đề là chúng được gom theo loại kỹ thuật thay vì theo capability mà chúng cùng phục vụ.

## 2. Chia theo business capability

Một capability là một trách nhiệm nghiệp vụ có mục tiêu và dữ liệu liên quan tương đối rõ. Trong ví dụ bán hàng, các capability có thể là quản lý đơn hàng, danh mục sản phẩm, khách hàng và tồn kho.

Sau khi tổ chức lại, cấu trúc có thể trở thành:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   ├── domain
│   │   ├── Order.java
│   │   └── OrderLine.java
│   ├── web
│   │   └── OrderController.java
│   └── persistence
│       └── OrderRepository.java
├── catalog
│   ├── api
│   │   ├── package-info.java
│   │   ├── ProductCatalog.java
│   │   └── ProductDetails.java
│   ├── domain
│   │   └── Product.java
│   ├── web
│   │   └── ProductController.java
│   └── persistence
│       └── ProductRepository.java
├── customers
│   ├── CustomerManagement.java
│   ├── domain
│   │   └── Customer.java
│   └── persistence
│       └── CustomerRepository.java
└── inventory
    ├── InventoryManagement.java
    ├── domain
    └── persistence
```

Theo detection strategy mặc định, Spring Modulith nhận diện các package con trực tiếp của package chứa `ShopApplication` là application module. Trong cấu trúc trên, `orders`, `catalog`, `customers` và `inventory` là các module. Các package `web`, `domain` và `persistence` là package con bên trong module, không tự động trở thành module độc lập.

Mỗi module chứa một lát cắt dọc qua các technical layer. Ví dụ `orders` sở hữu controller nhận request đặt hàng, application service điều phối use case, domain model giữ quy tắc đơn hàng và repository lưu dữ liệu đơn hàng.

## 3. Ánh xạ class từ layer cũ sang capability

Trước khi di chuyển file, hãy xác định capability mà mỗi class phục vụ. Không nên chỉ đổi tên package theo cảm tính.

| Technical layer cũ | Class ví dụ | Capability đích |
|---|---|---|
| `controller` | `OrderController` | `orders.web` |
| `service` | `OrderService` | `orders` hoặc `orders.application` |
| `repository` | `OrderRepository` | `orders.persistence` |
| `model` | `Order`, `OrderLine` | `orders.domain` |
| `controller` | `ProductController` | `catalog.web` |
| `service` | `ProductService` | `catalog` hoặc `catalog.application` |
| `repository` | `ProductRepository` | `catalog.persistence` |
| `model` | `Product` | `catalog.domain` |

Một class dùng chung cần được xem xét kỹ hơn. Ví dụ `Money` có thể là value object dùng bởi nhiều capability, nhưng `Customer` không nên được đưa vào một package `shared` chỉ vì nhiều module cần đọc thông tin khách hàng. Hãy xác định module sở hữu dữ liệu và cung cấp hợp đồng truy cập phù hợp.

Khi một service cũ xử lý nhiều capability, hãy tách theo use case và invariant nghiệp vụ. Một `ShopService` vừa đặt hàng, vừa cập nhật sản phẩm, vừa tính phí giao hàng thường là dấu hiệu có nhiều trách nhiệm cần phân chia. Tách class theo capability trước, sau đó mới quyết định package kỹ thuật bên trong từng module.

## 4. Xác định ranh giới capability trước khi di chuyển

Có thể dùng các câu hỏi sau để xác định một nhóm class có nên thuộc cùng module:

1. **Mục tiêu nghiệp vụ:** các class cùng hỗ trợ một kết quả nghiệp vụ nào?
2. **Quyền sở hữu dữ liệu:** capability nào quyết định cách tạo, thay đổi và bảo vệ dữ liệu này?
3. **Invariant:** quy tắc nào phải luôn đúng khi dữ liệu được thay đổi, và capability nào chịu trách nhiệm giữ quy tắc đó?
4. **Vòng đời:** các đối tượng có thường được tạo, thay đổi và hoàn tất trong cùng một quy trình không?
5. **Ngôn ngữ nghiệp vụ:** các class có cùng thuật ngữ và khái niệm trong một bounded context không?
6. **Lý do thay đổi:** các class có thường thay đổi cùng nhau vì cùng một yêu cầu nghiệp vụ không?

Không nên tạo module chỉ vì một nhóm class đang dùng chung một framework hoặc công nghệ. Ví dụ `JpaRepository` là chi tiết persistence; nó không phải business capability. Tương tự, package `controllers` không phải capability chỉ vì mọi endpoint đều nằm ở đó.

Một capability không nhất thiết phải có đủ mọi technical layer. Module chỉ cung cấp một API đọc dữ liệu có thể không cần controller riêng hoặc repository riêng. Hãy giữ cấu trúc nhỏ theo trách nhiệm thực tế, tránh tạo các package rỗng để ép mọi module có cùng hình dạng.

## 5. Di chuyển một capability theo từng lát cắt

Không cần di chuyển toàn bộ ứng dụng trong một lần. Chọn một capability có ranh giới tương đối rõ, chẳng hạn `catalog`, rồi di chuyển các class liên quan theo từng bước.

### Bước 1: Tạo package gốc của module

Tạo `com.acme.shop.catalog` dưới package gốc của ứng dụng. Spring Modulith có thể nhận diện module này theo chiến lược mặc định.

### Bước 2: Di chuyển các thành phần thuộc capability

Chuyển `ProductController`, `ProductService`, `ProductRepository` và `Product` vào các package con của `catalog`. Cập nhật package declaration và import. Giữ URL, request/response contract và hành vi nghiệp vụ hiện có nếu mục tiêu của đợt migration là tái tổ chức code.

### Bước 3: Tạo facade hoặc API module

Nếu module khác cần tra cứu sản phẩm, cung cấp một hợp đồng công khai như `ProductCatalog`. Hợp đồng này có thể nằm trong package gốc của `catalog` hoặc named interface riêng.

### Bước 4: Chuyển caller sang API

Tìm các module đang import `ProductRepository`, `Product` hoặc `ProductService` trực tiếp. Chuyển chúng sang gọi hợp đồng công khai phù hợp. Nếu caller chỉ cần biết sản phẩm có tồn tại hoặc lấy tên hiển thị, không nên để nó truy cập repository và entity nội bộ.

### Bước 5: Kiểm chứng và loại bỏ đường dẫn cũ

Chạy test nghiệp vụ, architecture test và kiểm tra các import còn trỏ tới package kỹ thuật cũ. Khi không còn caller, xóa package hoặc facade chuyển tiếp đã hết vai trò.

Lặp lại quy trình cho `orders`, `customers`, `inventory` và các capability còn lại. Mỗi bước nhỏ giúp khoanh vùng lỗi và dễ review hơn.

## 6. Ví dụ API module thay cho việc dùng chung repository

Trước khi modularize, `OrderService` có thể gọi trực tiếp `ProductRepository`:

```java
package com.acme.shop.service;

import java.util.Optional;

import com.acme.shop.model.Product;
import com.acme.shop.repository.ProductRepository;

class OrderService {

    private final ProductRepository products;

    OrderService(ProductRepository products) {
        this.products = products;
    }

    void placeOrder(String sku) {
        Product product = products.findBySku(sku).orElseThrow();
        // Tiếp tục tạo đơn hàng.
    }
}
```

Caller đang biết cách `catalog` lưu sản phẩm. Thay vào đó, module `catalog` công khai một hợp đồng nghiệp vụ:

```java
package com.acme.shop.catalog.api;

import java.util.Optional;

public interface ProductCatalog {

    Optional<ProductDetails> findBySku(String sku);
}
```

```java
package com.acme.shop.catalog.api;

public record ProductDetails(String sku, String displayName) {
}
```

Implementation ở bên trong module:

```java
package com.acme.shop.catalog.internal;

import java.util.Optional;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.catalog.api.ProductDetails;
import com.acme.shop.catalog.domain.Product;
import com.acme.shop.catalog.persistence.ProductRepository;
import org.springframework.stereotype.Service;

@Service
class ProductCatalogImpl implements ProductCatalog {

    private final ProductRepository products;

    ProductCatalogImpl(ProductRepository products) {
        this.products = products;
    }

    @Override
    public Optional<ProductDetails> findBySku(String sku) {
        return products.findBySku(sku)
                .map(product -> new ProductDetails(
                        product.getSku(), product.getDisplayName()));
    }
}
```

Module `orders` chỉ phụ thuộc vào `ProductCatalog` và DTO công khai `ProductDetails`. Nó không cần biết `ProductRepository`, entity `Product` hoặc cách truy vấn database.

Trong ví dụ rút gọn, `ProductDetails` cần được định nghĩa trong package API của `catalog` và có thể là Java record. Implementation và repository nằm trong package nội bộ; chúng không được module khác import trực tiếp.

## 7. Dùng named interface và allowedDependencies để bảo vệ hợp đồng

Nếu muốn tách API khỏi package gốc, đặt hợp đồng trong named interface:

```java
// src/main/java/com/acme/shop/catalog/api/package-info.java
@org.springframework.modulith.NamedInterface("catalog-api")
package com.acme.shop.catalog.api;
```

Các type công khai như `ProductCatalog` và `ProductDetails` nằm trong `catalog.api`. Module `orders` khai báo chỉ được phép phụ thuộc hợp đồng này:

```java
// src/main/java/com/acme/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "catalog::catalog-api"
)
package com.acme.shop.orders;
```

Như vậy, `orders` được phép tham chiếu `catalog.api`, nhưng không được import `catalog.internal` hoặc package persistence của `catalog`. Tên `catalog-api` phải khớp với tên trong `@NamedInterface`; `catalog` là module identifier mặc định trong ví dụ.

Nếu module không khai báo `allowedDependencies`, Spring Modulith vẫn kiểm tra quyền truy cập API/internal theo loại module. Khi khai báo allowlist, các phụ thuộc phải khớp module hoặc named interface được liệt kê. Điều này giúp thể hiện rõ module nào được phép dùng hợp đồng nào.

## 8. Chọn giao tiếp đồng bộ hay application event

Sau khi chia capability, module vẫn cần phối hợp để hoàn thành quy trình nghiệp vụ. Hãy chọn cách giao tiếp theo ý nghĩa của tương tác:

| Nhu cầu | Cách giao tiếp phù hợp |
|---|---|
| Module cần câu trả lời ngay để tiếp tục use case | Gọi public API/facade của module cung cấp |
| Module khác cần phản ứng sau khi một sự kiện nghiệp vụ xảy ra | Publisher phát application event, listener xử lý ở module nhận |
| Module cần truy vấn hoặc cập nhật repository nội bộ của module khác | Thiết kế lại API hoặc chuyển trách nhiệm dữ liệu về module sở hữu |
| Nhiều module cùng cần một giá trị nền tảng nhỏ, ổn định | Xem xét shared module sau khi xác định rõ quyền sở hữu và phạm vi |

Ví dụ, `orders` cần xác nhận sản phẩm tồn tại và lấy giá tại thời điểm đặt hàng thì có thể gọi `ProductCatalog`. Sau khi đơn hàng được ghi nhận, `orders` phát `OrderPlaced`; `inventory` lắng nghe để giữ hàng. Trong trường hợp event, dependency tĩnh của listener hướng về module công bố event contract, còn luồng event runtime hướng từ publisher tới listener.

Không nên chuyển mọi lời gọi đồng bộ thành event chỉ để giảm số mũi tên trong graph. Nếu use case cần kết quả ngay, API đồng bộ thường diễn đạt ý định rõ hơn. Event phù hợp khi module khác phản ứng với một sự kiện đã xảy ra và publisher không cần biết listener cụ thể.

## 9. Kiểm chứng module sau mỗi bước migration

Sau khi di chuyển một capability, tạo module model và chạy verification:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesCapabilityModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` giúp phát hiện:

- Chu trình phụ thuộc giữa các capability module.
- Module khác truy cập package nội bộ của capability.
- Phụ thuộc không nằm trong `allowedDependencies` đã khai báo.

Nếu verification thất bại, đọc `Violations` để tìm module nguồn, module đích và type liên quan. Một lỗi thường gặp sau migration là caller vẫn import repository hoặc entity cũ thay vì dùng API mới. Hãy sửa dependency tại caller và xác định xem hợp đồng mới đã đủ dữ liệu cho use case chưa.

Ngoài architecture test, giữ các test nghiệp vụ và integration test cần thiết. Việc đổi package không tự chứng minh hành vi vẫn đúng. Có thể dùng `@ApplicationModuleTest` để kiểm tra module trong Spring context giới hạn, đặc biệt khi muốn xác nhận bean trong capability được wiring đúng.

## 10. Xử lý class dùng chung và dependency chuyển tiếp

Trong codebase cũ, một số class được nhiều technical layer sử dụng. Không nên di chuyển tất cả vào `shared` chỉ để làm cho import dễ dàng.

| Loại class | Hướng xử lý |
|---|---|
| Value object thuần và ổn định như `Money`, `EmailAddress` | Có thể đặt trong shared kernel nhỏ nếu nhiều capability thật sự chia sẻ cùng ngữ nghĩa |
| Entity thuộc một capability như `Customer` | Giữ quyền sở hữu trong module `customers`; module khác dùng API hoặc event contract |
| Base controller/service chứa logic kỹ thuật chung | Cân nhắc thư viện kỹ thuật dùng chung, nhưng không để nó điều phối nghiệp vụ của nhiều capability |
| DTO chỉ phục vụ một use case | Đặt gần module sở hữu use case; không đưa vào shared chỉ vì có nhiều field giống nhau |
| Repository truy cập bảng của một capability | Giữ trong module sở hữu dữ liệu; không expose repository làm API liên module |
| Utility tổng quát không mang ngữ nghĩa nghiệp vụ | Chỉ chia sẻ khi thật sự ổn định và không tạo phụ thuộc ngược vào capability |

Trong giai đoạn chuyển tiếp, có thể giữ một facade tương thích ở package cũ để caller được di chuyển dần. Facade chỉ nên ủy quyền tới module mới, có phạm vi rõ và kế hoạch loại bỏ. Tránh duy trì hai implementation nghiệp vụ song song vì trạng thái dữ liệu và quy tắc có thể lệch nhau.

## 11. Những lỗi thường gặp khi chuyển từ layer sang capability

| Cách làm sai | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Tạo module `controller`, `service`, `repository` | Vẫn là chia ngang theo kỹ thuật | Tạo module theo capability như `orders`, `catalog`, `inventory` |
| Chuyển package nhưng giữ mọi repository public | Module vẫn phụ thuộc persistence của nhau | Expose facade hoặc API nghiệp vụ |
| Đưa mọi class dùng chung vào `shared` | Shared trở thành module tập trung, dễ tạo coupling | Xác định owner và chỉ chia sẻ abstraction ổn định |
| Chia module theo từng entity | Một use case phải điều phối quá nhiều module nhỏ | Nhóm theo capability, invariant và vòng đời dữ liệu |
| Đưa toàn bộ controller vào module riêng | Adapter đầu vào bị tách khỏi capability sở hữu use case | Đặt controller trong module tương ứng, thường ở package `web` |
| Chuyển tất cả lời gọi thành event | Luồng nghiệp vụ khó theo dõi và thiếu kết quả đồng bộ | Dùng API cho yêu cầu cần kết quả ngay; event cho phản ứng sau sự kiện |
| Dùng `OPEN` để mọi module import được code cũ | Ranh giới internal bị nới rộng | Công khai hợp đồng có chủ đích và giữ module `CLOSED` khi phù hợp |
| Di chuyển tất cả capability trong một lần | Khó cô lập regression và review | Chuyển từng vertical slice, kiểm tra sau mỗi bước |
| Chỉ chạy compile sau khi di chuyển | Không phát hiện dependency sai về mặt kiến trúc | Chạy architecture test và test nghiệp vụ liên quan |

## 12. Quy trình migration theo từng capability

Một lộ trình thực tế có thể triển khai như sau:

1. **Lập bản đồ code hiện tại:** liệt kê controller, service, repository, entity và caller của từng capability.
2. **Xác định business owner:** nhóm class theo use case, invariant, dữ liệu và lý do thay đổi.
3. **Chọn capability đầu tiên:** ưu tiên nhóm có ranh giới tương đối rõ, ít phụ thuộc ngược và có test hiện hữu.
4. **Tạo package module:** tạo package con trực tiếp dưới root package ứng dụng để Spring Modulith nhận diện.
5. **Di chuyển vertical slice:** chuyển adapter, application logic, domain model và persistence liên quan vào module.
6. **Công khai hợp đồng cần thiết:** dùng package gốc hoặc named interface; không expose repository và implementation.
7. **Chuyển caller:** thay import technical class bằng API hoặc event contract.
8. **Kiểm tra dependency:** chạy `ApplicationModules.verify()` và đọc toàn bộ violations.
9. **Kiểm tra behavior:** chạy unit test, integration test và module integration test phù hợp.
10. **Loại bỏ package layer cũ:** xóa facade chuyển tiếp khi không còn caller và cập nhật tài liệu kiến trúc.
11. **Lặp lại:** tiếp tục với capability kế tiếp, giữ dependency graph không chu trình.

Có thể dùng một bảng theo dõi đơn giản trong quá trình migration:

| Capability | Class đã chuyển | API đã xác định | Caller đã chuyển | Verification |
|---|---|---|---|---|
| `catalog` | Controller, service, repository, domain | `ProductCatalog` | `orders` | PASS sau khi xử lý dependency |
| `orders` | Đang thực hiện | Chưa hoàn tất | Còn caller cũ | Chưa chạy |
| `customers` | Chưa bắt đầu | Chưa xác định | Còn caller cũ | Chưa chạy |

Các trạng thái trong bảng chỉ là ví dụ minh họa; dự án cần ghi nhận tiến độ thật theo từng capability.

## 13. Checklist trước khi hoàn tất một capability module

- [ ] Package gốc phản ánh một business capability có trách nhiệm rõ.
- [ ] Controller, application service, domain model và persistence liên quan nằm trong module sở hữu.
- [ ] Module có quyền sở hữu rõ đối với dữ liệu và invariant nghiệp vụ của nó.
- [ ] Package con như `web`, `domain`, `persistence`, `internal` không bị hiểu nhầm là module độc lập.
- [ ] Các type cần chia sẻ được expose qua API hoặc named interface.
- [ ] Module tiêu thụ chỉ tham chiếu hợp đồng được phép.
- [ ] Repository và entity nội bộ không bị import trực tiếp từ module khác.
- [ ] Giao tiếp đồng bộ và application event được chọn theo nhu cầu nghiệp vụ.
- [ ] `ApplicationModules.of(...).verify()` chạy thành công.
- [ ] Test nghiệp vụ và integration test liên quan vẫn xác nhận hành vi đúng.
- [ ] Package technical layer cũ không còn caller hoặc đã có kế hoạch loại bỏ rõ ràng.

Chuyển từ technical layer sang capability module giúp code được tổ chức theo trách nhiệm nghiệp vụ. Mỗi module sở hữu một lát cắt dọc, kiểm soát dữ liệu và implementation của mình, rồi công khai những hợp đồng cần thiết cho module khác. Thực hiện migration từng capability và xác minh sau mỗi bước giúp modular monolith hình thành dần mà không phải thay đổi toàn bộ ứng dụng trong một lần.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith – Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Spring Modulith – Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)

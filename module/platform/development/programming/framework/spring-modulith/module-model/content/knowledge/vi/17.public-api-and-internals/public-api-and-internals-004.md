# Expose một type qua named interface

Một application module thường có nhiều kiểu Java phục vụ triển khai nội bộ, nhưng chỉ một số kiểu cần được module khác sử dụng. Spring Modulith cho phép công khai một hợp đồng cụ thể bằng `@NamedInterface`. Với Java, annotation này có thể đặt trực tiếp trên type; nhờ đó ta có thể expose đúng một interface hoặc class mà không cần công khai mọi type trong package chứa nó.

Đây là cách hữu ích khi muốn module khác phụ thuộc vào một hợp đồng ổn định, trong khi implementation, mapper và các kiểu hỗ trợ vẫn thuộc phần nội bộ. Nội dung dưới đây dùng module `catalog` cung cấp một type `ProductLookup` cho module `orders`.

## 1. Named interface xác định phần API được công khai

Theo quy ước mặc định, package gốc của một application module là API không tên (unnamed interface). Các package con thường được xem là nội bộ. Nếu muốn cho module khác tham chiếu thêm một package hoặc một tập hợp type, ta có thể khai báo named interface.

`@NamedInterface` có thể được dùng theo hai cách:

| Cách khai báo | Phạm vi được expose |
|---|---|
| Đặt trên `package-info.java` | Các type thuộc package được đánh dấu trở thành thành viên của named interface đó |
| Đặt trực tiếp trên type | Type được đánh dấu trở thành thành viên của named interface; các type khác trong package không tự động được expose theo cách này |

Một named interface có thể gồm nhiều type cùng được đánh dấu với một tên. Khi chỉ cần công khai một hợp đồng, đặt annotation trực tiếp trên type giúp phạm vi API rõ ràng và nhỏ hơn.

Từ Spring Modulith 2.0, `@NamedInterface` có thuộc tính `propagate`, mặc định là `true`. Khi bật, các type xuất hiện trong tham số hoặc kiểu trả về của public method và nằm trong cùng package space cũng có thể được đưa vào named interface. Nếu cần giữ ranh giới đúng ở type được đánh dấu, có thể đặt `propagate = false`; hãy kiểm tra thuộc tính này có trong phiên bản Spring Modulith của dự án trước khi dùng.

## 2. Bố trí package cho ví dụ

Ứng dụng bán hàng có cấu trúc rút gọn như sau:

```text
com.acme.shop
├── ShopApplication.java
├── catalog
│   ├── ProductManagement.java
│   ├── api
│   │   ├── ProductLookup.java       // @NamedInterface("product-lookup")
│   │   └── ProductLookupMapper.java // internal
│   └── internal
│       └── ProductLookupImpl.java
└── orders
    ├── package-info.java           // allowedDependencies
    └── OrderApplicationService.java
```

Trong ví dụ:

- `catalog` là module cung cấp thông tin sản phẩm.
- `catalog.api.ProductLookup` là hợp đồng duy nhất được expose qua named interface `product-lookup`.
- `ProductLookupMapper` và `ProductLookupImpl` là chi tiết nội bộ.
- `orders` chỉ cần tra cứu thông tin sản phẩm thông qua `ProductLookup`.

Việc đặt type công khai trong package con `api` giúp tách hợp đồng khỏi package gốc và các package triển khai. Package `api` không cần `package-info.java` nếu ta đánh dấu trực tiếp type muốn expose.

## 3. Đánh dấu trực tiếp type cần expose

Tạo interface trong `catalog.api` và đặt `@NamedInterface` trên chính interface:

```java
package com.acme.shop.catalog.api;

import java.util.Optional;

import org.springframework.modulith.NamedInterface;

@NamedInterface("product-lookup")
public interface ProductLookup {

    Optional<String> findDisplayName(String sku);
}
```

`product-lookup` là tên logic của named interface. Tên này được dùng trong cấu hình phụ thuộc của module tiêu thụ. Nó không bắt buộc phải trùng tên package `api` hoặc tên type `ProductLookup`.

Implementation nằm trong package nội bộ và không cần được expose:

```java
package com.acme.shop.catalog.internal;

import java.util.Optional;

import com.acme.shop.catalog.api.ProductLookup;
import org.springframework.stereotype.Component;

@Component
class ProductLookupImpl implements ProductLookup {

    @Override
    public Optional<String> findDisplayName(String sku) {
        // Tìm sản phẩm bằng repository nội bộ và trả về tên hiển thị.
        return Optional.empty();
    }
}
```

`ProductLookupImpl` có thể là package-private vì Spring component scan và cơ chế dependency injection có thể quản lý implementation trong cùng ứng dụng. Module `orders` chỉ cần biết interface công khai. Ví dụ trả về `Optional<String>` để hợp đồng không vô tình kéo thêm một DTO nội bộ vào API.

Nếu hợp đồng cần trả về DTO, DTO đó cũng phải là type được công khai phù hợp. Có thể đánh dấu nhiều type bằng cùng tên `@NamedInterface("product-lookup")` để gom chúng vào một named interface, hoặc đặt chúng trong một package được đánh dấu ở cấp package.

Với Spring Modulith 2.0 trở lên, có thể tắt việc tự động mở rộng named interface cho các type liên quan bằng cách viết rõ:

```java
@NamedInterface(value = "product-lookup", propagate = false)
public interface ProductLookup {
    // Chỉ type này được gán vào named interface theo annotation.
}
```

Nếu giữ `propagate = true`, hãy xem lại chữ ký public của hợp đồng để biết các DTO hoặc type liên quan nào được đưa vào named interface cùng với nó.

## 4. Giới hạn module tiêu thụ vào named interface

Để module `orders` chỉ được phụ thuộc vào named interface `product-lookup` của `catalog`, khai báo `allowedDependencies` trên package gốc của `orders`:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "catalog :: product-lookup"
)
package com.acme.shop.orders;
```

Toán tử `::` nối tên module với tên named interface. Với cấu hình này, `orders` được phép tham chiếu các type thuộc named interface `product-lookup` của `catalog`. Các type ở package nội bộ như `catalog.internal` hoặc type khác trong `catalog.api` không nằm trong named interface sẽ không được phép truy cập.

Module tiêu thụ sử dụng hợp đồng như một dependency thông thường:

```java
package com.acme.shop.orders;

import java.util.Optional;

import com.acme.shop.catalog.api.ProductLookup;
import org.springframework.stereotype.Service;

@Service
class OrderApplicationService {

    private final ProductLookup productLookup;

    OrderApplicationService(ProductLookup productLookup) {
        this.productLookup = productLookup;
    }

    Optional<String> productName(String sku) {
        return productLookup.findDisplayName(sku);
    }
}
```

Module `orders` biết hợp đồng `ProductLookup` và cách gọi nó. Nó không cần biết `ProductLookupImpl` được tạo như thế nào, repository nào được dùng hoặc dữ liệu được lấy từ cache hay database.

## 5. Kiểm chứng ranh giới bằng ApplicationModules

Đưa kiểm tra kiến trúc vào test để bảo vệ named interface khỏi những thay đổi vô tình:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesNamedInterfaceDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi `orders` sử dụng `ProductLookup`, quan hệ phù hợp với `allowedDependencies` và kiểm tra có thể thành công. Nếu một type trong `orders` bắt đầu tham chiếu `catalog.internal.ProductLookupImpl` hoặc một type khác không thuộc named interface được cho phép, `verify()` sẽ báo vi phạm kiến trúc.

Để thấy rõ tác dụng của quy tắc, có thể thử thay import trong `OrderApplicationService` bằng một type triển khai nội bộ được khai báo `public`. Code có thể biên dịch, nhưng kiểm tra Spring Modulith vẫn phát hiện module `orders` đang truy cập phần không được công khai. Sau khi thử, khôi phục dependency về `ProductLookup`.

`verify()` kiểm tra cấu trúc và quyền truy cập giữa các module. Nó không thay thế integration test để xác nhận Spring tạo đúng bean `ProductLookup`, cũng không xác nhận truy vấn sản phẩm trả về dữ liệu nghiệp vụ chính xác.

## 6. Khi nào dùng type-level và package-level NamedInterface?

| Nhu cầu | Cách khai báo phù hợp |
|---|---|
| Chỉ công khai một interface hoặc class | Đặt `@NamedInterface("...")` trực tiếp trên type |
| Công khai một nhóm type có cùng vai trò | Đặt cùng tên `@NamedInterface("...")` trên từng type |
| Công khai toàn bộ API trong package | Đặt `@NamedInterface("...")` trong `package-info.java` |
| Cho phép module khác phụ thuộc đúng một named interface | Dùng `allowedDependencies = "module :: interface"` |
| Cho phép module khác phụ thuộc tất cả named interface đã khai báo | Dùng `allowedDependencies = "module :: *"` |
| Cho phép cả package gốc và mọi named interface của module | Dùng `allowedDependencies = "module :: **"` |

Khi đánh dấu package bằng `package-info.java`, toàn bộ type được expose trong package đó trở thành thành viên của named interface. Cách này phù hợp khi package được thiết kế như một hợp đồng có nhiều type liên quan. Nếu package còn chứa mapper, helper hoặc implementation không nên được module khác sử dụng, hãy cân nhắc đánh dấu trực tiếp từng type cần công khai hoặc tách package hợp đồng riêng.

Nếu không khai báo `allowedDependencies` tường minh cho module tiêu thụ, Spring Modulith áp dụng quy tắc mặc định cho phép phụ thuộc vào package gốc và các named interface được công khai của module đích. Khi cần kiểm soát chặt module nào được dùng hợp đồng nào, hãy khai báo `allowedDependencies` để thể hiện ý định rõ ràng.

## 7. Những lỗi thường gặp

- **Đánh dấu cả package khi chỉ cần một type:** mọi type trong package được expose, làm bề mặt API rộng hơn dự kiến.
- **Đặt annotation ở nhầm package:** named interface phải thuộc package nằm bên trong đúng application module cần cung cấp API.
- **Nhầm tên package với tên named interface:** tên dùng trong `allowedDependencies` phải khớp tên được khai báo trong `@NamedInterface`.
- **Chỉ khai báo named interface mà quên giới hạn dependency:** nếu module tiêu thụ cần tuân theo một hợp đồng cụ thể, hãy khai báo `allowedDependencies` tương ứng.
- **Đưa implementation vào API:** module tiêu thụ nên phụ thuộc vào abstraction ổn định, không phụ thuộc vào class triển khai hoặc repository nội bộ.
- **Cho rằng type public tự động là API module:** khả năng truy cập của Java và quyền truy cập giữa application module là hai lớp khác nhau; `verify()` kiểm tra quy tắc module.
- **Cho rằng `verify()` chứng minh bean chạy được:** cần integration test để xác nhận context, wiring và hành vi thực tế.

## 8. Checklist expose một type

- [ ] Type cần công khai đã được xác định là hợp đồng ổn định, không phải implementation.
- [ ] `@NamedInterface("...")` được đặt trực tiếp trên đúng type.
- [ ] Tên named interface được ghi lại để dùng nhất quán trong dependency declaration.
- [ ] Các kiểu xuất hiện trong chữ ký public của hợp đồng cũng thuộc API được phép sử dụng.
- [ ] Module tiêu thụ khai báo `allowedDependencies = "module :: interface"` khi cần giới hạn quyền phụ thuộc.
- [ ] Module tiêu thụ chỉ import type công khai và không tham chiếu implementation nội bộ.
- [ ] `ApplicationModules.of(...).verify()` được chạy trong kiểm thử kiến trúc.
- [ ] Integration test xác nhận bean implementation được cấu hình và hoạt động đúng khi cần.

Expose một type qua named interface giúp module cung cấp kiểm soát chính xác hợp đồng mà module khác được phép sử dụng. Khi kết hợp type-level `@NamedInterface` với `allowedDependencies`, ranh giới API được thể hiện ngay trong code và có thể kiểm chứng tự động.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals: Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [NamedInterface annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [ApplicationModule annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)

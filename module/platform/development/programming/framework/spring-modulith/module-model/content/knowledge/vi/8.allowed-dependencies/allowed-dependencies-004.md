# Wildcard `*` cho các named interface

Spring Modulith cho phép một application module khai báo rõ những module mà nó được phép phụ thuộc bằng `@ApplicationModule(allowedDependencies = ...)`. Khi module cần sử dụng nhiều nhóm API đã được expose từ cùng một module khác, bạn có thể dùng wildcard `*` trong phần named interface để cho phép truy cập tất cả named interface được khai báo của module đó.

Cú pháp này giúp tránh phải liệt kê từng named interface khi module tiêu thụ thực sự cần toàn bộ các nhóm API được công bố. Tuy nhiên, `*` chỉ bao phủ named interfaces; nó không bao gồm package gốc của module cung cấp. Nếu cần cả package gốc, có thể khai báo thêm tên module hoặc dùng wildcard `**`.

Trong `SPRING_MODULITH_MODULE_MODEL`, hiểu đúng phạm vi của wildcard giúp thiết kế dependency rõ ràng, giới hạn quyền truy cập và kiểm chứng kiến trúc modular monolith bằng `ApplicationModules.verify()`.

## 1. Named interface là gì?

Theo mặc định, package gốc của application module là API package mà module khác được phép tham chiếu. Các package con như `spi`, `reporting` hoặc `integration` vẫn là nội bộ cho đến khi module công bố chúng bằng `@NamedInterface`.

Ví dụ, module `order` có cấu trúc:

```text
com.example.shop.order
├── OrderManagement.java
├── spi
│   ├── package-info.java
│   └── OrderLookup.java
├── reporting
│   ├── package-info.java
│   └── OrderReport.java
└── internal
    ├── OrderManagementImpl.java
    └── OrderRepository.java
```

Hai package `spi` và `reporting` được công bố riêng biệt bằng metadata đặt trong `package-info.java`.

`order/spi/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.order.spi;
```

`order/reporting/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("reporting")
package com.example.shop.order.reporting;
```

Module `order` hiện có ba bề mặt API có thể phân biệt:

- Package gốc `com.example.shop.order`, chứa `OrderManagement`.
- Named interface `spi`, chứa `OrderLookup`.
- Named interface `reporting`, chứa `OrderReport`.

Package `internal` vẫn là nội bộ. Việc công bố `spi` và `reporting` không làm package này trở thành API.

## 2. Khai báo một named interface cụ thể

Nếu module `billing` chỉ cần dùng `OrderLookup`, hãy khai báo dependency tới đúng named interface:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: spi"
)
package com.example.shop.billing;
```

Phần trước `::` là logical name của module cung cấp (`order`); phần sau `::` là tên named interface (`spi`). Khi dependency được khai báo như trên, module `billing` được phép tham chiếu các kiểu trong `order.spi`.

Ví dụ:

```java
package com.example.shop.billing.internal;

import com.example.shop.order.spi.OrderLookup;
import org.springframework.stereotype.Service;

@Service
class BillingService {

    private final OrderLookup orderLookup;

    BillingService(OrderLookup orderLookup) {
        this.orderLookup = orderLookup;
    }

    boolean canCreateInvoice(String orderId) {
        return orderLookup.exists(orderId);
    }
}
```

Nếu `billing` chỉ khai báo `order :: spi`, nó không được phép tham chiếu `OrderManagement` ở package gốc hoặc `OrderReport` trong `order.reporting` theo whitelist này.

## 3. Dùng wildcard `*` cho tất cả named interfaces

Khi module tiêu thụ cần sử dụng nhiều hoặc tất cả named interfaces của cùng một module, thay vì liệt kê từng tên, hãy dùng `*`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: *"
)
package com.example.shop.billing;
```

`order :: *` có nghĩa là module `billing` được phép phụ thuộc vào tất cả named interfaces được khai báo tường minh trong module `order`. Với ví dụ ở trên, quyền truy cập bao gồm:

- `order::spi`
- `order::reporting`
- Các named interface khác được khai báo trong `order` sau này.

Wildcard giúp cấu hình gọn hơn khi một module tiêu thụ cần toàn bộ các nhóm API được expose từ một module cung cấp. Khi module `order` bổ sung một named interface mới, `billing` cũng được phép tham chiếu named interface mới đó mà không cần thêm tên vào danh sách dependency.

### `*` không bao gồm package gốc

Điểm cần nhớ là `*` chỉ áp dụng cho các named interfaces. Nó không cấp quyền truy cập package gốc của module cung cấp.

Với cấu hình:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: *"
)
package com.example.shop.billing;
```

`billing` được phép dùng `OrderLookup` và `OrderReport`, nhưng không được phép dùng `OrderManagement` ở package gốc `com.example.shop.order`.

Nếu module cần cả package gốc và mọi named interface, có hai cách khai báo:

**Cách 1: Liệt kê package gốc và wildcard named interfaces.**

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "order", "order :: *" }
)
package com.example.shop.billing;
```

**Cách 2: Dùng wildcard kép `**`.**

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: **"
)
package com.example.shop.billing;
```

`order :: **` bao gồm package gốc và tất cả named interfaces được công bố của module `order`.

## 4. So sánh `module`, `module :: *` và `module :: **`

| Khai báo | Package gốc | Tất cả named interfaces | Ý nghĩa |
|---|---:|---:|---|
| `"order"` | Có | Không | Chỉ cho phép API package gốc |
| `"order :: spi"` | Không | Không | Chỉ cho phép named interface `spi` |
| `"order :: *"` | Không | Có | Cho phép tất cả named interfaces, không gồm package gốc |
| `{ "order", "order :: *" }` | Có | Có | Cho phép package gốc và tất cả named interfaces |
| `"order :: **"` | Có | Có | Tương đương dòng ngay phía trên |

Hai wildcard có phạm vi khác nhau:

- `*`: mọi named interface được khai báo tường minh của module được chỉ định.
- `**`: package gốc cùng mọi named interface được khai báo tường minh của module được chỉ định.

Wildcard nằm sau tên module. Vì vậy, `order :: *` không có nghĩa là cho phép phụ thuộc vào tất cả module trong ứng dụng; nó chỉ mở rộng phạm vi named interface của module `order`.

`allowedDependencies` là cấu hình tùy chọn. Nếu không khai báo thuộc tính này, module không áp dụng whitelist dependency tường minh và vẫn tuân theo quy tắc API/encapsulation của Spring Modulith. Nếu khai báo một mảng rỗng, module không được phép phụ thuộc vào module nào khác. Khi đã bật whitelist, các giá trị như `order :: *` xác định chính xác phạm vi module và interface được phép.

## 5. Dùng wildcard trong danh sách nhiều dependency

Một module có thể phụ thuộc vào nhiều module khác nhau và dùng phạm vi khác nhau cho từng module. Ví dụ, `billing` cần toàn bộ named interfaces của `order`, nhưng chỉ cần API gốc của `customer`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "order :: *",
        "customer"
    }
)
package com.example.shop.billing;
```

Nếu `billing` cũng cần API gốc của `order`, có thể thêm `"order"` hoặc đổi thành `"order :: **"`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "order :: **",
        "customer"
    }
)
package com.example.shop.billing;
```

Khai báo whitelist nên phản ánh đúng nhu cầu của module tiêu thụ. Không nên dùng `**` chỉ vì muốn tránh lỗi verify nếu module chỉ cần một named interface cụ thể.

## 6. Wildcard được áp dụng ở phía module tiêu thụ

`allowedDependencies` được khai báo trên module đang tạo ra dependency, tức module tiêu thụ. Ví dụ:

```text
billing module
    |
    | allowedDependencies = "order :: *"
    v
order module
    ├── base package API
    ├── named interface: spi
    ├── named interface: reporting
    └── internal package
```

Trong sơ đồ này, `billing` quyết định rằng nó được phép tham chiếu tất cả named interfaces của `order`. Module `order` vẫn chịu trách nhiệm quyết định package nào được expose bằng `@NamedInterface`.

Hai phía phối hợp với nhau:

1. **Module cung cấp:** đánh dấu các package được công bố bằng `@NamedInterface`.
2. **Module tiêu thụ:** khai báo phạm vi dependency trong `allowedDependencies`.
3. **Spring Modulith:** đối chiếu các tham chiếu thực tế với API đã công bố và whitelist dependency.

Nếu provider không khai báo một named interface, wildcard không thể tự biến package nội bộ thành API.

## 7. Điều gì xảy ra khi module cung cấp thêm named interface?

Giả sử `order` ban đầu có hai named interfaces `spi` và `reporting`. Module `billing` khai báo `order :: *`, vì vậy được phép dùng cả hai.

Sau đó, `order` bổ sung package `integration`:

```text
com.example.shop.order
├── spi
├── reporting
├── integration
│   ├── package-info.java
│   └── ExternalOrderGateway.java
└── internal
```

Package `integration` chỉ trở thành named interface nếu được đánh dấu:

```java
@org.springframework.modulith.NamedInterface("integration")
package com.example.shop.order.integration;
```

Sau khi công bố, `billing` với `order :: *` cũng được phép tham chiếu `ExternalOrderGateway`. Đây là đặc tính cần cân nhắc khi dùng wildcard: phạm vi cho phép tự mở rộng khi provider bổ sung named interface.

Nếu cần kiểm soát chặt hợp đồng mà `billing` sử dụng, hãy liệt kê từng named interface thay vì dùng wildcard. Khi đó, một named interface mới không tự động được thêm vào whitelist của `billing`.

## 8. Phân biệt wildcard với việc mở toàn bộ module

Wildcard `*` không mở package nội bộ. Nó chỉ bao phủ những named interfaces đã được provider công bố tường minh. Các package như `order.internal` vẫn nằm ngoài phạm vi truy cập.

| Cấu trúc của `order` | `order :: *` cho phép? |
|---|---|
| `com.example.shop.order.OrderManagement` | Không |
| `com.example.shop.order.spi.OrderLookup` với `@NamedInterface("spi")` | Có |
| `com.example.shop.order.reporting.OrderReport` với `@NamedInterface("reporting")` | Có |
| `com.example.shop.order.internal.OrderRepository` | Không |
| Package con chưa được expose | Không |

Không nhầm `order :: *` với module kiểu `OPEN`. Một open module cho phép truy cập rộng hơn vào các kiểu nội bộ theo quy tắc của Spring Modulith. Wildcard `*` vẫn giữ encapsulation và chỉ cho phép các nhóm API đã được công bố.

## 9. Kiểm chứng wildcard bằng `ApplicationModules.verify()`

Bạn có thể kiểm tra toàn bộ dependency của ứng dụng bằng một bài test kiến trúc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesAllowedNamedInterfaceDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Với cấu hình `order :: *`, kiểm thử sẽ cho phép module tiêu thụ tham chiếu các kiểu thuộc named interfaces được khai báo của `order`. Các truy cập tới package nội bộ như `order.internal` vẫn bị từ chối.

Nếu kiểm thử thất bại, hãy kiểm tra:

1. Package provider đã được đánh dấu `@NamedInterface` chưa?
2. Tên module trước `::` có đúng logical name không?
3. Wildcard được đặt sau `::` chưa, ví dụ `order :: *`?
4. Kiểu được tham chiếu có nằm trong named interface được công bố hay package nội bộ?
5. Có phải module đang cần API package gốc nhưng chỉ khai báo `order :: *` không?

Nếu module cần package gốc, thêm `"order"` hoặc dùng `"order :: **"`. Nếu chỉ cần một phần API, khai báo named interface cụ thể để tránh mở rộng phạm vi không cần thiết.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `order :: *` cho phép mọi module trong ứng dụng | Nó chỉ cho phép mọi named interfaces của module `order`. |
| `*` bao gồm package gốc của `order` | `*` không bao gồm package gốc; dùng thêm `order` hoặc dùng `order :: **`. |
| `*` expose package nội bộ chưa đánh dấu | Provider vẫn phải công bố package bằng `@NamedInterface`. |
| Wildcard được khai báo ở module cung cấp | `allowedDependencies` được khai báo ở module tiêu thụ. |
| Dùng `*` tương đương mở module | `*` chỉ bao phủ named interfaces; open module có phạm vi truy cập nội bộ rộng hơn. |
| Thêm named interface mới không ảnh hưởng module dùng wildcard | Module dùng `*` tự động được phép tham chiếu named interface mới được công bố từ provider đó. |

## 11. Checklist sử dụng wildcard `*`

- [ ] Xác định module cung cấp mà module hiện tại cần phụ thuộc.
- [ ] Kiểm tra các package con của provider đã được đánh dấu `@NamedInterface`.
- [ ] Đặt `allowedDependencies` trên package gốc của module tiêu thụ.
- [ ] Dùng cú pháp `module :: *` để cho phép mọi named interface của module đó.
- [ ] Nhớ rằng `*` không bao gồm API package gốc.
- [ ] Thêm `module` hoặc dùng `module :: **` nếu cần cả API gốc.
- [ ] Tránh wildcard nếu module chỉ cần một hoặc hai named interfaces cụ thể.
- [ ] Đánh giá tác động khi provider công bố named interface mới.
- [ ] Giữ package `internal` ở trạng thái encapsulated.
- [ ] Chạy `ApplicationModules.verify()` để kiểm tra các dependency thực tế.

## 12. Kết luận

Wildcard `*` trong `allowedDependencies` cho phép một module phụ thuộc vào tất cả named interfaces được công bố tường minh của một module khác. Cú pháp `order :: *` chỉ bao phủ các named interfaces của `order`, không bao gồm package API gốc và không mở các package nội bộ.

Nếu cần cả package gốc và mọi named interfaces, dùng `order :: **` hoặc kết hợp `order` với `order :: *`. Hãy chọn phạm vi theo đúng nhu cầu nghiệp vụ, nhớ rằng wildcard tự mở rộng khi provider công bố named interface mới và dùng `ApplicationModules.verify()` để bảo đảm các phụ thuộc thực tế tuân thủ ranh giới đã thiết kế.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Explicit Application Module Dependencies and Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith 1.2 — Fundamentals](https://docs.spring.io/spring-modulith/reference/1.2/fundamentals.html)
- [Spring Modulith — `@ApplicationModule` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)

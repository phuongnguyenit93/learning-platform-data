# Allowed dependency là whitelist hay tài liệu?

Trong Spring Modulith, `allowedDependencies` là **danh sách cho phép (allow-list) có thể được kiểm chứng**, không chỉ là ghi chú tài liệu. Khi một module khai báo danh sách này, `ApplicationModules.verify()` kiểm tra các phụ thuộc thực tế của module và báo lỗi nếu code tham chiếu sang module hoặc named interface chưa được cho phép.

Khai báo này mô tả chiều phụ thuộc đi ra từ module đang được cấu hình. Ví dụ, `inventory` khai báo được phép phụ thuộc vào `catalog` nghĩa là code bên trong `inventory` có thể sử dụng API được công bố của `catalog`. Nó không có nghĩa `catalog` được phép phụ thuộc ngược lại vào `inventory`. Allow-list này kiểm soát phụ thuộc tới các application module mà Spring Modulith nhận diện; thư viện bên ngoài hoặc code không thuộc application module không phải tên module để liệt kê ở đây.

Bài học này thuộc chương **Allowed dependencies** của mô hình Spring Modulith. Sau khi học, bạn có thể phân biệt trách nhiệm của `allowedDependencies` với `@NamedInterface`, cấu hình allow-list cho module Java hoặc Kotlin, hiểu giá trị mặc định và kiểm chứng quy tắc bằng `ApplicationModules.verify()`.

## 1. `allowedDependencies` kiểm soát điều gì?

Spring Modulith nhận diện các application module từ cấu trúc package. Một module có package gốc và có thể có các package con. Theo quy tắc mặc định, package gốc là API package; các package con thường được xem là nội bộ, trừ khi chúng được công bố rõ ràng bằng named interface hoặc module được cấu hình theo chế độ mở.

Có hai câu hỏi kiến trúc khác nhau:

1. **Module đích công bố những package nào?** Module đích trả lời bằng `@NamedInterface` (hoặc API package gốc mặc định).
2. **Module nguồn được phép phụ thuộc vào module/package nào?** Module nguồn trả lời bằng `@ApplicationModule(allowedDependencies = ...)`.

Ví dụ, `pricing` công bố package `pricing.spi` bằng `@NamedInterface("spi")`. Module `checkout` chỉ cần sử dụng hợp đồng trong `pricing.spi`, không cần truy cập các type nội bộ của `pricing`.

| Cơ chế | Được khai báo ở đâu? | Vai trò |
|---|---|---|
| `@NamedInterface("spi")` | Package được module đích công bố | Đánh dấu package là một giao diện có tên mà module khác có thể tham chiếu. |
| `@ApplicationModule(allowedDependencies = ...)` | Package gốc của module nguồn | Giới hạn các module hoặc named interface mà module nguồn được phép phụ thuộc. |
| `ApplicationModules.verify()` | Bài kiểm tra kiến trúc | Phân tích code và kiểm tra các phụ thuộc có tuân thủ khai báo hay không. |

`allowedDependencies` không làm package nội bộ trở thành API. Danh sách này chỉ cho biết module nguồn được phép đi tới đâu; module đích vẫn phải công bố package cần dùng theo quy tắc của Spring Modulith.

## 2. Khai báo allow-list

Giả sử ứng dụng có các module sau:

```text
com.acme.shop
├── ShopApplication.java
├── checkout
│   ├── CheckoutService.java
│   └── package-info.java
├── catalog
│   ├── ProductCatalog.java
│   └── internal
│       └── JdbcProductRepository.java
└── pricing
    ├── PricingService.java
    ├── spi
    │   └── PricingPolicy.java
    └── internal
        └── DefaultPricingEngine.java
```

Module `checkout` cần gọi API gốc của `catalog` và hợp đồng `PricingPolicy` trong named interface `pricing.spi`. Nó không cần gọi trực tiếp `PricingService` hoặc `DefaultPricingEngine`.

### Với Java

Đặt annotation trên `package-info.java` của package gốc `checkout`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "catalog",
        "pricing :: spi"
    }
)
package com.acme.shop.checkout;
```

Khai báo này cho phép code trong `checkout` phụ thuộc vào API package gốc của `catalog` và named interface `spi` của `pricing`. Các application module khác không nằm trong danh sách sẽ không được `checkout` tham chiếu trực tiếp, trừ các shared module được cấu hình riêng.

### Với Kotlin

Kotlin không có `package-info.java`, vì vậy có thể đặt metadata trên một class trong package gốc của module:

```kotlin
package com.acme.shop.checkout

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(
    allowedDependencies = [
        "catalog",
        "pricing :: spi"
    ]
)
class ModuleMetadata
```

Class `ModuleMetadata` phải nằm trong package gốc `com.acme.shop.checkout`. `@PackageInfo` cho Spring Modulith biết class này đại diện metadata của package; `@ApplicationModule` khai báo allow-list.

## 3. Cách đọc từng mục trong danh sách

Mỗi phần tử của `allowedDependencies` có thể chỉ tên module hoặc chỉ rõ named interface của module đó.

| Giá trị | Phạm vi được phép |
|---|---|
| `"catalog"` | API package gốc của module `catalog`. |
| `"pricing :: spi"` | Named interface có tên `spi` của module `pricing`. |
| `"pricing :: *"` | Tất cả named interface được khai báo của `pricing`, không bao gồm API package gốc. |
| `"pricing :: **"` | API package gốc và tất cả named interface được khai báo của `pricing`. |

Dấu `::` phân tách tên module và tên named interface. Tên module trong ví dụ là tên module logic do Spring Modulith nhận diện, không phải tên class hay tên bean Spring.

Ví dụ, nếu `checkout` khai báo:

```java
@org.springframework.modulith.ApplicationModule(allowedDependencies = "pricing :: spi")
package com.acme.shop.checkout;
```

thì `checkout` được phép dùng các type trong `pricing.spi`. Nó không được phép tham chiếu `PricingService` trong package gốc `pricing` chỉ vì package đó thuộc cùng module. Nếu cần cả API package gốc lẫn mọi named interface của `pricing`, dùng `pricing :: **`.

`*` và `**` có ý nghĩa khác nhau. `*` chỉ bao phủ các named interface; `**` bao phủ cả package gốc và các named interface. Chọn đúng phạm vi giúp danh sách phản ánh chính xác hợp đồng mà module nguồn cần dùng.

## 4. Giá trị mặc định: bỏ thuộc tính khác với danh sách rỗng

Đây là điểm dễ gây nhầm lẫn khi đọc `@ApplicationModule`:

| Cách khai báo | Ý nghĩa |
|---|---|
| Không khai báo `allowedDependencies` | Không áp dụng giới hạn allow-list từ thuộc tính này; module không bị giới hạn danh sách phụ thuộc theo cấu hình này. |
| `allowedDependencies = {}` trong Java | Không cho phép phụ thuộc vào application module nào khác. |
| `allowedDependencies = []` trong Kotlin | Tương đương danh sách rỗng: không cho phép phụ thuộc vào application module nào khác. |
| `allowedDependencies = {"catalog"}` | Chỉ cho phép phụ thuộc vào API package gốc của `catalog` trong danh sách đã khai báo. |

Vì vậy, không nên thêm `allowedDependencies` với một mảng rỗng nếu mục tiêu là giữ hành vi mặc định. Danh sách rỗng là một quy tắc chặt: module không được có phụ thuộc sang module khác.

Khi allow-list được khai báo, các shared module được cấu hình thông qua `Modulith`/`Modulithic` cũng được Spring Modulith cho phép. Hãy cân nhắc điều này khi giải thích kết quả kiểm tra trong dự án có khai báo shared modules.

## 5. Đây là whitelist được thực thi như thế nào?

Annotation lưu quy tắc trong metadata của module. Việc phát hiện vi phạm diễn ra khi ứng dụng được phân tích và các quy tắc kiến trúc được chạy, thường trong một bài kiểm tra. Ví dụ Java:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Với Kotlin:

```kotlin
import org.junit.jupiter.api.Test
import org.springframework.modulith.core.ApplicationModules

class ModularityTests {

    @Test
    fun verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication::class.java).verify()
    }
}
```

Khi chạy `verify()`, Spring Modulith kiểm tra nhiều quy tắc cấu trúc, bao gồm:

- Không có chu trình phụ thuộc ở cấp application module.
- Module chỉ tham chiếu package API được công bố; tham chiếu package nội bộ của module khác sẽ bị phát hiện theo quy tắc tương ứng.
- Nếu module khai báo `allowedDependencies`, các phụ thuộc phải nằm trong danh sách được phép.

Nếu có vi phạm, `verify()` ném exception để bài kiểm tra thất bại. Nhờ vậy, thay đổi code làm phát sinh phụ thuộc ngoài ý muốn có thể bị phát hiện trong quy trình build/CI, miễn là bài kiểm tra kiến trúc được chạy trong quy trình đó.

Điều này cũng cho thấy giới hạn của allow-list: annotation tự nó không chặn compiler, không cấu hình dependency injection và không phải cơ chế bảo mật lúc chạy. Nó mô tả quy tắc kiến trúc; bài kiểm tra Spring Modulith mới thực hiện việc xác minh quy tắc trên code.

## 6. Ví dụ về vi phạm

Giả sử `checkout` khai báo:

```kotlin
@PackageInfo
@ApplicationModule(allowedDependencies = ["catalog", "pricing :: spi"])
class ModuleMetadata
```

Các trường hợp sau có kết quả khác nhau:

| Code trong `checkout` | Kết quả mong đợi | Lý do |
|---|---|---|
| Tham chiếu `catalog.ProductCatalog` | Hợp lệ | `catalog` nằm trong allow-list và type thuộc API package gốc. |
| Tham chiếu `pricing.spi.PricingPolicy` | Hợp lệ | Named interface `pricing :: spi` đã được cho phép. |
| Tham chiếu `pricing.internal.DefaultPricingEngine` | Vi phạm | Package `pricing.internal` là nội bộ, không được công bố. |
| Tham chiếu API package gốc của module `shipping` | Vi phạm | `shipping` không có trong allow-list. |
| Tham chiếu một named interface khác của `pricing` | Vi phạm | Chỉ `pricing :: spi` được cho phép; không có wildcard bao phủ các giao diện còn lại. |

Khi gặp lỗi, hãy xác định module nguồn trong thông báo vi phạm, sau đó kiểm tra module đích, package chứa type bị tham chiếu và giá trị `allowedDependencies`. Nếu code thực sự cần một hợp đồng mới, hãy quyết định có nên công bố hợp đồng đó thành named interface và thêm đúng mục vào allow-list hay không.

## 7. Quy trình thiết kế allow-list

Khi một module cần sử dụng module khác, thực hiện theo thứ tự sau:

1. Xác định module nguồn đang tạo ra tham chiếu, ví dụ `checkout`.
2. Xác định chính xác type mà module nguồn cần dùng và package chứa type đó.
3. Kiểm tra package đích có phải API package gốc hoặc named interface đã công bố hay chưa.
4. Khai báo module hoặc named interface tương ứng trong `allowedDependencies` của module nguồn.
5. Chạy `ApplicationModules.verify()` để xác nhận toàn bộ cấu trúc tuân thủ quy tắc.

Không thêm cả module vào allow-list chỉ vì một type nội bộ đang được tham chiếu. Trước tiên hãy xem type đó có thực sự là hợp đồng cần công bố hay không. Nếu đúng, đặt hợp đồng trong API package hoặc named interface phù hợp rồi cho phép đúng phạm vi cần thiết.

## 8. Ghi nhớ

`allowedDependencies` là allow-list tùy chọn ở cấp module nguồn. Khi được khai báo, nó giới hạn module nguồn có thể phụ thuộc vào module hoặc named interface nào; `ApplicationModules.verify()` kiểm tra các tham chiếu thực tế theo quy tắc đó. Bỏ thuộc tính nghĩa là không giới hạn bằng allow-list này, còn khai báo danh sách rỗng nghĩa là không cho phép phụ thuộc sang module khác. `@NamedInterface` vẫn giữ vai trò công bố API của module đích, còn `allowedDependencies` xác định module nguồn được phép sử dụng phần API nào.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals: Explicit Application Module Dependencies và Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith API – `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)

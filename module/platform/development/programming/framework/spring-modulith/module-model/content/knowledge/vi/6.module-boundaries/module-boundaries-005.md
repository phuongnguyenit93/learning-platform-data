# Module phụ thuộc vào type chưa thuộc module nào

Khi Spring Modulith kiểm tra kiến trúc, không phải mọi kiểu Java mà một application module sử dụng đều thuộc về một application module khác. Một type có thể nằm ngay trong package gốc của ứng dụng, hoặc nằm ngoài các package được nhận diện là module. Spring Modulith xem những type đó là **code chưa được gán cho application module nào**.

Điểm quan trọng là quy tắc `allowedDependencies` kiểm soát phụ thuộc giữa các application module. Theo mô hình mặc định, code trong một module vẫn có thể tham chiếu type chưa thuộc module nào, kể cả khi module đã khai báo danh sách dependency được phép. Vì vậy, cần hiểu rõ type đang thuộc module nào trước khi diễn giải kết quả kiểm tra.

## 1. Vì sao có type không thuộc application module?

Theo chiến lược phát hiện mặc định, package chứa lớp `@SpringBootApplication` là application root package. Các package con trực tiếp của nó được nhận diện là application module. Các type nằm trực tiếp trong application root package không tự tạo thành một module nghiệp vụ.

Ví dụ:

```text
com.example.shop                    # Application root package
├── ShopApplication.java
├── RequestMetadata.java             # Chưa thuộc application module nào
├── catalog                          # Application module
│   └── ProductCatalog.java
└── orders                           # Application module
    └── internal
        └── OrderService.java
```

Trong ví dụ này:

- `com.example.shop.catalog` là base package của module `catalog`.
- `com.example.shop.orders` là base package của module `orders`.
- `com.example.shop.RequestMetadata` nằm trực tiếp trong application root package nên không thuộc module `catalog` hoặc `orders`, cũng không tự tạo thành một module thứ ba.

Spring Modulith xây dựng mô hình module từ package arrangement. Vì vậy, một type có thể được Java sử dụng bình thường mà không được gán vào một application module trong mô hình kiến trúc.

## 2. Dependency đến type chưa được gán module

Giả sử `RequestMetadata` là một kiểu dữ liệu thuần Java được đặt ở application root package:

```java
package com.example.shop;

import java.util.UUID;

public record RequestMetadata(UUID requestId, String source) {
}
```

Module `orders` có thể sử dụng type này:

```java
package com.example.shop.orders.internal;

import com.example.shop.RequestMetadata;

class OrderService {

    void createOrder(RequestMetadata metadata) {
        // Xử lý đơn hàng với metadata của request.
    }
}
```

Về mặt Java, đây là một tham chiếu type thông thường. Về mặt Spring Modulith, `RequestMetadata` chưa thuộc application module nào, nên tham chiếu này không tạo ra quan hệ phụ thuộc từ `orders` sang một module khác.

Điều đó hữu ích cho những type nền tảng hoặc hạ tầng nhỏ được dùng chung, nhưng không có trách nhiệm nghiệp vụ độc lập. Tuy nhiên, việc một type chưa được gán module không có nghĩa nó là một API module công khai. Nó chỉ nằm ngoài các ranh giới module mà Spring Modulith đang mô hình hóa.

## 3. allowedDependencies vẫn cho phép type ngoài module

Một module có thể khai báo danh sách module mà nó được phép phụ thuộc bằng `@ApplicationModule` trong `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog"
)
package com.example.shop.orders;
```

Khai báo này giới hạn code trong `orders` chỉ được phụ thuộc vào module `catalog` trong số các application module. Type không được gán cho application module nào, như `com.example.shop.RequestMetadata`, vẫn được phép tham chiếu.

Có thể phân biệt các trường hợp như sau:

| Type mà `orders` tham chiếu | Có thuộc application module? | Kết quả theo allow-list trên |
|---|---|---|
| `com.example.shop.catalog.ProductCatalog` | Có, thuộc `catalog` | Được phép |
| `com.example.shop.inventory.StockAvailability` | Có, thuộc `inventory` | Bị từ chối vì `inventory` chưa được cho phép |
| `com.example.shop.RequestMetadata` | Không thuộc module nào | Được phép |
| `java.util.UUID` | Không phải application module của ứng dụng | Không tạo dependency giữa các application module |

Như vậy, `allowedDependencies` không phải danh sách mọi package hoặc mọi thư viện mà code có thể import. Nó là danh sách cho phép đối với các application module được Spring Modulith nhận diện.

## 4. Type trong package con trực tiếp sẽ được xem là module

Một nhầm lẫn thường gặp là cho rằng mọi type dùng chung đều có thể đặt trong package `shared` mà không tạo thêm module. Với chiến lược phát hiện mặc định, điều đó không đúng nếu `shared` là package con trực tiếp của application root.

Ví dụ:

```text
com.example.shop
├── ShopApplication.java
├── shared
│   └── RequestMetadata.java
├── catalog
└── orders
```

Ở đây, `com.example.shop.shared` được nhận diện là một application module riêng. Khi `orders` tham chiếu `RequestMetadata`, mô hình có dependency từ `orders` sang `shared`. Nếu `orders` đã khai báo `allowedDependencies`, cần cho phép `shared` một cách tường minh:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"catalog", "shared"}
)
package com.example.shop.orders;
```

Ngược lại, nếu `RequestMetadata` nằm trực tiếp trong `com.example.shop`, nó không được gán vào module `shared` nào cả. Chỉ cần di chuyển một type từ application root package xuống package con trực tiếp, cách Spring Modulith phân loại dependency của nó có thể thay đổi.

## 5. Có nên đặt mọi type dùng chung ở application root package?

Không nên dùng application root package như một nơi chứa tất cả các type mà nhiều module muốn chia sẻ. Vì dependency đến type chưa được gán module vẫn được cho phép, việc đặt logic nghiệp vụ vào root package có thể làm cho quan hệ phụ thuộc quan trọng không xuất hiện như một module dependency.

Hãy chọn vị trí dựa trên trách nhiệm của type:

| Loại type | Cách tổ chức phù hợp |
|---|---|
| Lớp khởi động và cấu hình ở cấp ứng dụng | Có thể đặt trong application root package |
| Metadata kỹ thuật nhỏ, trung lập, không sở hữu nghiệp vụ | Có thể đặt ở root nếu thực sự cần dùng chung và không tạo một module riêng |
| Kiểu hoặc logic có trách nhiệm nghiệp vụ rõ ràng | Đặt trong module nghiệp vụ sở hữu nó |
| Hợp đồng dùng chung có ý nghĩa độc lập với nhiều module | Cân nhắc một module `shared` có API và trách nhiệm được xác định rõ |
| Kiểu đến từ JDK hoặc thư viện bên ngoài | Quản lý như dependency bên ngoài; chúng không phải application module của ứng dụng |

Nếu tạo module `shared`, hãy giữ nó tập trung vào những abstraction thực sự dùng chung và không để nó phụ thuộc ngược vào các module nghiệp vụ. Một module chia sẻ phụ thuộc vào `orders` trong khi `orders` cũng phụ thuộc vào `shared` sẽ tạo chu trình và làm mất lợi ích của ranh giới.

Tránh biến `common` hoặc `shared` thành nơi chứa mọi thứ chưa tìm được chủ sở hữu. Một module chia sẻ tốt cần có hợp đồng rõ ràng, phạm vi nhỏ và hướng phụ thuộc dễ giải thích.

## 6. Cách kiểm tra dependency trong mô hình

Ta có thể tạo mô hình và kiểm tra các quy tắc kiến trúc bằng `ApplicationModules.verify()`:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi kiểm tra, Spring Modulith phân tích các tham chiếu giữa type thuộc các application module. Nó phát hiện dependency giữa module, kiểm tra chu trình và áp dụng allow-list nếu module khai báo `allowedDependencies`. Tham chiếu tới type chưa được gán module không trở thành dependency đến một application module khác.

Khi cần quan sát cấu trúc, ta có thể duyệt các module được phát hiện:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
```

Danh sách này giúp xác nhận `shared` có đang được nhận diện là một module hay không. Nếu một type nằm trực tiếp trong application root package, nó sẽ không xuất hiện như một application module riêng trong danh sách.

## 7. Cách xử lý khi gặp dependency đến type chưa thuộc module nào

Khi thấy một module phụ thuộc vào type chưa được gán module, hãy lần lượt trả lời:

1. Type đó đang nằm ở package nào? Nó có nằm trực tiếp trong application root package hay ngoài phạm vi module được phát hiện không?
2. Type đó chỉ là metadata hoặc abstraction kỹ thuật trung lập, hay đang chứa quy tắc nghiệp vụ?
3. Nếu type có trách nhiệm nghiệp vụ, module nào nên sở hữu nó? Có nên tạo một application module riêng với API rõ ràng không?
4. Nếu đã tạo module sở hữu, các module sử dụng có khai báo dependency hợp lệ trong `allowedDependencies` chưa?

Ví dụ, `RequestMetadata` chỉ mang thông tin định danh của request có thể là một type kỹ thuật dùng chung. Nhưng nếu một class `PricingPolicy` chứa quy tắc tính giá sản phẩm, nó nên thuộc module sở hữu nghiệp vụ giá hoặc catalog, thay vì được đặt ở application root chỉ để nhiều module import thuận tiện.

Hãy nhớ rằng một dependency không tạo thành module edge vẫn là một dependency ở cấp mã nguồn. Spring Modulith không dùng allow-list module để kiểm soát mọi tham chiếu Java đến mọi type. Vì vậy, hãy dùng package tree để làm rõ quyền sở hữu và dùng `ApplicationModules.verify()` để kiểm tra các ranh giới module đã mô hình hóa.

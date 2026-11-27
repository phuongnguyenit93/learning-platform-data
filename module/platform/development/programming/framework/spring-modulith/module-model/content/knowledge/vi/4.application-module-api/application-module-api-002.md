# Module base package, display name và identifier

Khi Spring Modulith phát hiện một application module, nó tạo ra một đối tượng mô hình `ApplicationModule` để mô tả module đó. Đối tượng này cung cấp nhiều thông tin hữu ích, trong đó có **base package**, **display name** và **identifier**.

Ba thông tin này trả lời ba câu hỏi khác nhau: module quản lý package nào, nên được gọi bằng tên gì khi hiển thị cho con người, và được nhận diện bằng định danh kỹ thuật nào trong mô hình kiến trúc. Hiểu rõ chúng giúp ta đọc mô hình module, tạo tài liệu kiến trúc và cấu hình các quy tắc phụ thuộc chính xác.

## 1. Module base package là gì?

`base package` là package gốc đại diện cho một application module. Nó bao gồm các lớp nằm trực tiếp trong package đó và những package con thuộc phạm vi triển khai của module.

Ví dụ, ứng dụng có package gốc `com.example.shop` và cấu trúc sau:

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java
│   └── internal
│       └── ProductRepository.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── OrderService.java
└── inventory
    ├── StockAvailability.java
    └── internal
        └── StockRepository.java
```

Các base package của ba module lần lượt là:

- `com.example.shop.catalog`
- `com.example.shop.orders`
- `com.example.shop.inventory`

Chú ý phân biệt **package gốc của ứng dụng** với **base package của module**. `com.example.shop` là điểm bắt đầu để Spring Modulith khám phá ứng dụng; `com.example.shop.orders` là base package của riêng module `orders`.

Spring Modulith dùng base package để xác định những lớp và package thuộc module. Chẳng hạn, `com.example.shop.orders.internal` vẫn nằm dưới base package của `orders`, vì vậy nó thuộc phạm vi triển khai của module `orders`. Module khác nên tương tác qua API mà `orders` công khai thay vì phụ thuộc vào chi tiết bên trong package con này.

## 2. Display name dùng để làm gì?

`display name` là tên thân thiện dành cho con người. Tên package thường ngắn, phù hợp với mã nguồn và cấu hình; display name có thể diễn đạt rõ hơn trách nhiệm nghiệp vụ của module.

Ta có thể khai báo display name bằng `@ApplicationModule` trong file `package-info.java` ở base package của module:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Quản lý đơn hàng"
)
package com.example.shop.orders;
```

Với khai báo này, module vẫn có base package `com.example.shop.orders`, nhưng tên hiển thị được đặt là `Quản lý đơn hàng`. Ta có thể đặt display name tương tự cho các module khác:

| Module | Base package | Display name |
|---|---|---|
| `catalog` | `com.example.shop.catalog` | Danh mục sản phẩm |
| `orders` | `com.example.shop.orders` | Quản lý đơn hàng |
| `inventory` | `com.example.shop.inventory` | Quản lý tồn kho |

Display name hữu ích khi tạo sơ đồ, báo cáo hoặc tài liệu kiến trúc cho nhóm phát triển và người đọc không cần biết quy ước package. Nếu không khai báo tên hiển thị riêng, Spring Modulith sử dụng tên mặc định dựa trên tên module.

Display name là nhãn trình bày. Không nên dùng nó làm căn cứ để import package, khai báo dependency hoặc nhận diện module trong mã nguồn, vì nội dung hiển thị có thể thay đổi theo cách diễn đạt hoặc ngôn ngữ tài liệu.

## 3. Identifier là gì?

`identifier` là định danh kỹ thuật mà mô hình Spring Modulith gắn với application module. Nó giúp phân biệt và tham chiếu module trong mô hình kiến trúc, ví dụ khi đọc danh sách module hoặc các quan hệ phụ thuộc giữa chúng.

Trong cấu trúc đơn giản, module `orders` thường có định danh gắn với tên module được suy ra từ package. Identifier thuộc về mô hình module và được tạo theo cấu trúc nhận diện của Spring Modulith. Khi làm việc với identifier, hãy lấy giá trị từ đối tượng `ApplicationModule` thay vì tự tạo chuỗi từ display name.

Điều quan trọng là không đồng nhất ba giá trị:

| Thuộc tính | Ý nghĩa | Ví dụ với module đơn hàng |
|---|---|---|
| Base package | Package gốc sở hữu mã nguồn của module | `com.example.shop.orders` |
| Display name | Tên dễ đọc dành cho tài liệu và giao diện | `Quản lý đơn hàng` |
| Identifier | Định danh kỹ thuật trong mô hình module | Định danh của module `orders` |

Nếu đổi display name từ `Quản lý đơn hàng` thành `Xử lý đơn hàng`, package và định danh module vẫn cần được giữ nhất quán với cấu trúc mã nguồn. Việc đổi nhãn hiển thị không phải là cách đổi tên hoặc di chuyển module.

## 4. Đọc thông tin từ ApplicationModule

Sau khi khởi tạo `ApplicationModules`, ta có thể duyệt các module được phát hiện và đọc ba thuộc tính trên:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

for (ApplicationModule module : modules) {
    String basePackage = module.getBasePackage().getName();
    String displayName = module.getDisplayName();
    Object identifier = module.getIdentifier();

    System.out.printf("%s | %s | %s%n",
            basePackage, displayName, identifier);
}
```

Trong ví dụ:

- `getBasePackage()` trả về đối tượng package mà module sở hữu; `getName()` lấy tên đầy đủ của package đó.
- `getDisplayName()` trả về tên hiển thị của module, bao gồm giá trị đã cấu hình hoặc giá trị mặc định.
- `getIdentifier()` trả về định danh module trong mô hình Spring Modulith.

Đoạn mã trên có thể dùng để quan sát mô hình trong lúc phát triển hoặc làm đầu vào cho một công cụ tạo báo cáo nội bộ. Khi viết logic phụ thuộc vào module, hãy ưu tiên các API và cơ chế cấu hình mà Spring Modulith cung cấp thay vì tự phân tích chuỗi in ra từ ví dụ.

## 5. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao không chính xác | Cách hiểu đúng |
|---|---|---|
| Base package của module chính là package gốc của ứng dụng | Một ứng dụng có thể chứa nhiều application module | Package gốc ứng dụng là điểm bắt đầu khám phá; mỗi module có base package riêng |
| Display name là tên package | Display name có thể chứa khoảng trắng, dấu tiếng Việt và thay đổi theo nhu cầu tài liệu | Base package là địa chỉ cấu trúc trong mã nguồn; display name là nhãn dễ đọc |
| Identifier và display name có thể dùng thay thế cho nhau | Một giá trị phục vụ nhận diện kỹ thuật, giá trị kia phục vụ trình bày | Dùng identifier từ mô hình cho mục đích kỹ thuật và display name cho mục đích hiển thị |
| Package con luôn là một application module độc lập | Package con có thể chỉ là phần triển khai của module cha | Xác định ranh giới module theo chiến lược khám phá và cấu hình Spring Modulith |

Khi một module có nhiều package con, không nên tự suy ra mỗi package con là một module riêng. Hãy xem mô hình `ApplicationModules` đã phát hiện và kiểm tra cấu trúc package thực tế.

## 6. Kết hợp các thuộc tính khi đọc mô hình kiến trúc

Ba thuộc tính có thể được dùng cùng nhau để trình bày module theo cách vừa chính xác với mã nguồn vừa dễ hiểu với người đọc. Ví dụ, một dòng trong bảng kiến trúc có thể hiển thị:

```text
Quản lý đơn hàng
  Base package: com.example.shop.orders
  Identifier:   orders
```

Ở đây, display name giúp người đọc hiểu trách nhiệm nghiệp vụ; base package cho biết vị trí mã nguồn; identifier giúp tham chiếu module trong mô hình. Giá trị identifier minh họa cần được lấy từ `getIdentifier()` của mô hình thực tế, không nên giả định chuỗi hiển thị luôn có cùng dạng trong mọi cấu trúc module.

Khi thiết kế ứng dụng Spring Boot với Spring Modulith, hãy giữ base package ổn định theo ranh giới nghiệp vụ, đặt display name ngắn gọn và có ý nghĩa, đồng thời sử dụng identifier do Spring Modulith cung cấp. Cách làm này giúp mô hình module dễ đọc, dễ kiểm chứng và ít phụ thuộc vào các quy ước tên tự đặt trong từng phần của ứng dụng.

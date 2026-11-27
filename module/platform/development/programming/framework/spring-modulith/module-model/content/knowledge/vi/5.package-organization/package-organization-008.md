# Package dùng chung và rủi ro tạo phụ thuộc ngầm

Khi nhiều application module cần dùng cùng một kiểu dữ liệu hoặc tiện ích, phản xạ thường gặp là tạo package `common`, `shared` hoặc `utils` rồi chuyển mọi thứ có vẻ dùng chung vào đó. Cách làm này giúp tránh một số đoạn code trùng lặp, nhưng nếu package dùng chung trở thành nơi chứa mọi khái niệm và quy tắc của ứng dụng, nó có thể tạo ra một điểm phụ thuộc lớn mà ít ai kiểm soát.

Trong modular monolith, code dùng chung vẫn cần có chủ sở hữu, API và hướng phụ thuộc rõ ràng. Spring Modulith xem package cấp module như những đơn vị kiến trúc có thể kiểm tra. Vì vậy, một package `shared` đặt ngay dưới package gốc ứng dụng thường trở thành một application module thực sự; nó không phải vùng trung lập mà các module có thể sử dụng tùy ý.

## 1. Package dùng chung thường bắt đầu từ một nhu cầu hợp lý

Giả sử ứng dụng bán hàng có các module `order`, `inventory`, `customer` và `shipping`. Một số kiểu hoặc tiện ích dường như được nhiều module cần:

- `Money` để biểu diễn số tiền và phép tính tiền tệ.
- `Address` để mô tả địa chỉ giao hàng hoặc thanh toán.
- `DateTimeUtils` để định dạng ngày giờ.
- `OrderStatus` để biểu diễn trạng thái đơn hàng.
- `CustomerRepository` để truy cập dữ liệu khách hàng.
- `OrderMapper` để chuyển đổi dữ liệu đơn hàng.

Nếu đưa tất cả vào một package `common`, cấu trúc có thể trông như sau:

```text
com.acme.shop
├── order
├── inventory
├── customer
├── shipping
└── common
    ├── Money.java
    ├── Address.java
    ├── OrderStatus.java
    ├── CustomerRepository.java
    ├── OrderMapper.java
    └── DateTimeUtils.java
```

Danh sách này trộn lẫn nhiều loại trách nhiệm. `Money` có thể là một khái niệm giá trị dùng chung. `OrderStatus` lại mô tả vòng đời đơn hàng do `order` sở hữu. `CustomerRepository` là chi tiết truy cập dữ liệu của `customer`. `OrderMapper` phục vụ một quy trình cụ thể của `order`. Chúng không tự trở thành cùng một loại hợp đồng chỉ vì nhiều lớp có thể import chúng.

Package dùng chung hữu ích khi nó thực sự chứa một khái niệm ổn định có cùng ý nghĩa với các bên sử dụng. Nó trở nên rủi ro khi tiêu chí đưa một lớp vào đó chỉ là “có hơn một module đang cần”.

## 2. `common` ở cấp package gốc có thể trở thành một application module

Giả sử lớp ứng dụng nằm trong `com.acme.shop`. Với cách phát hiện module mặc định, các package con trực tiếp như `order`, `inventory`, `customer`, `shipping` và `common` được nhận diện như những application module.

```text
com.acme.shop
├── ShopApplication.java
├── order
├── inventory
├── customer
├── shipping
└── common
    ├── Money.java
    └── DateTimeUtils.java
```

Trong cấu trúc đó, `com.acme.shop.common` là root package của module `common`. Các module khác phụ thuộc vào `common` khi import những type được công bố ở package API hoặc Named Interface của nó. Quan hệ này là dependency thật trong mô hình kiến trúc và cần được thiết kế như mọi dependency khác.

Điều này khác với một package con nằm bên trong module:

```text
com.acme.shop
└── order
    ├── OrderManagement.java
    └── internal
        └── common
            └── OrderCalculationSupport.java
```

`com.acme.shop.order.internal.common` vẫn thuộc module `order`; nó không phải module `common` độc lập. Package đó có thể dùng để chia nhỏ phần triển khai bên trong `order`, nhưng module khác không thể coi nó là API dùng chung.

Vì vậy, trước khi tạo package `common`, hãy xác định nó nằm ở cấp nào trong cây package và Spring Modulith sẽ xem nó thuộc module nào. Tên `common` không có ý nghĩa đặc biệt với framework; vị trí package và cấu hình module mới quyết định ranh giới.

## 3. Vì sao một module dùng chung dễ trở thành điểm phụ thuộc tập trung?

Khi nhiều module phụ thuộc vào một module `common`, đồ thị phụ thuộc có thể trở thành:

```text
order --------\
inventory -----+----> common
customer -----/
shipping -----/
reporting ----/
```

Đây là hình minh họa các module cùng sử dụng một module dùng chung. `common` có fan-in cao: nhiều module khác phụ thuộc vào nó. Fan-in cao tự nó không phải lỗi, nhưng nếu API của `common` thay đổi thường xuyên hoặc chứa các khái niệm nghiệp vụ không cùng chủ sở hữu, thay đổi ở một nơi có thể tác động đến nhiều module.

Một số rủi ro thường xuất hiện:

- **Thay đổi lan rộng:** chỉnh sửa một type dùng chung có thể buộc nhiều module cập nhật cùng lúc.
- **Coupling ngữ nghĩa:** các module phải thống nhất cách hiểu về một type, kể cả khi mỗi module có nhu cầu nghiệp vụ khác nhau.
- **Khó xác định quyền sở hữu:** không rõ module nào quyết định ý nghĩa, quy tắc và vòng đời của type.
- **Phụ thuộc vòng:** khi `common` bắt đầu dùng ngược các API của `order` hoặc `customer`, dependency graph có thể tạo chu trình.
- **Rò rỉ chi tiết triển khai:** repository, entity hoặc mapper nội bộ được đưa ra ngoài chỉ vì có module khác muốn tái sử dụng.
- **Thay đổi bị trì hoãn:** nhóm ngại chỉnh sửa API chung vì không thể dự đoán hết tác động lên các consumer.

Rủi ro lớn nhất không chỉ là nhiều module import cùng một lớp. Đó là các module bị buộc chia sẻ một mô hình hoặc chính sách mà không còn thuộc quyền quyết định của từng module.

## 4. Phụ thuộc ngầm thường ẩn trong những type có vẻ trung lập

Một type có tên chung chung vẫn có thể mang ngữ nghĩa riêng của một capability. Ví dụ, `OrderStatus` được đưa vào `common` để `shipping`, `billing` và `reporting` cùng sử dụng:

```java
package com.acme.shop.common;

public enum OrderStatus {
    CREATED,
    PAID,
    READY_TO_SHIP,
    SHIPPED,
    CANCELLED
}
```

Ban đầu, enum này có vẻ tiện lợi. Nhưng khi `order` thay đổi vòng đời đơn hàng, các module khác phải theo kịp danh sách trạng thái. `shipping` có thể chỉ quan tâm đến việc đơn hàng đã sẵn sàng giao hay chưa; `billing` quan tâm đến việc đã thu tiền; `reporting` có thể cần phân loại trạng thái phục vụ báo cáo. Một enum chung buộc mọi consumer phụ thuộc vào cùng một mô hình vòng đời.

Đây là phụ thuộc ngầm về ngữ nghĩa. Chỉ nhìn import `OrderStatus`, người đọc có thể không nhận ra module tiêu thụ đang phụ thuộc vào chính sách nghiệp vụ của `order`.

Một lựa chọn rõ ràng hơn là để `order` sở hữu `OrderStatus` và công bố nó qua API thích hợp. Nếu consumer chỉ cần biết đơn đã được xác nhận giao hay chưa, `order` có thể cung cấp một hợp đồng phù hợp với nhu cầu đó, chẳng hạn event `OrderReadyForShipment`. Module `shipping` phản ứng với sự kiện mà không cần hiểu toàn bộ vòng đời đơn hàng.

Tương tự, đừng đưa `CustomerRepository` vào `common` chỉ vì `order` cần tìm thông tin khách hàng. Repository là chi tiết lưu trữ thuộc `customer`. Module `customer` nên công bố một API truy vấn hoặc một hợp đồng phù hợp để module khác lấy đúng thông tin được phép sử dụng.

## 5. Phân biệt code dùng chung về kỹ thuật và khái niệm dùng chung về nghiệp vụ

Không phải mọi thứ dùng chung đều có cùng rủi ro. Hãy phân loại theo ý nghĩa và quyền sở hữu:

| Loại | Ví dụ | Cách tổ chức thường phù hợp |
| --- | --- | --- |
| Tiện ích kỹ thuật thuần túy | Hàm chuyển đổi, chuẩn hóa chuỗi, bộ định dạng không mang quy tắc nghiệp vụ | Thư viện kỹ thuật nhỏ hoặc module dùng chung có API hẹp |
| Khái niệm giá trị có cùng ngữ nghĩa | `Money` với quy tắc tiền tệ và làm tròn thống nhất | Shared kernel nhỏ nếu các module thực sự dùng cùng một mô hình |
| Khái niệm thuộc một capability | `OrderStatus`, `StockReservation`, `CustomerProfile` | Để module sở hữu khái niệm công bố API hoặc event cần thiết |
| Chi tiết triển khai | Repository, JPA entity, mapper nội bộ, adapter | Giữ trong module sở hữu; không đưa vào API chung |
| Dữ liệu trao đổi giữa các module | `OrderPlaced`, `CustomerAddressChanged` | Hợp đồng API hoặc Named Interface do module phát sở hữu |

Một số hàm kỹ thuật nhỏ có thể được lặp lại ở hai nơi với chi phí thấp hơn việc tạo dependency chung. Ngược lại, quy tắc tính tiền phức tạp không nên được sao chép tùy tiện nếu các module thực sự phải tuân thủ cùng một chính sách. Quyết định nên dựa trên sự đồng nhất về ngữ nghĩa, tốc độ thay đổi và quyền sở hữu, không chỉ dựa trên số lần code xuất hiện.

## 6. Shared kernel cần có phạm vi nhỏ và chủ sở hữu rõ ràng

Trong thiết kế domain, shared kernel là một phần mô hình nhỏ mà nhiều bounded context thống nhất chia sẻ. Nó có thể phù hợp với những khái niệm thực sự có cùng ý nghĩa và cùng quy tắc trong các module.

Ví dụ, nếu `order`, `billing` và `shipping` đều cần cùng một kiểu `Money`, có thể thiết kế một module `shared` công bố riêng package `money`:

```text
com.acme.shop
├── order
├── billing
├── shipping
└── shared
    └── money
        ├── Money.java
        └── package-info.java
```

`Money` nên đóng gói các quy tắc thực sự dùng chung, như biểu diễn số tiền, currency và các phép toán có kiểm soát. Nếu `billing` có chính sách thuế hoặc `order` có chính sách định giá riêng, những chính sách đó vẫn thuộc module tương ứng; chúng không nên được đưa vào `Money` chỉ vì cùng làm việc với tiền.

Named Interface cho phép module `shared` công bố đúng package cần thiết:

```java
@org.springframework.modulith.NamedInterface("money")
package com.acme.shop.shared.money;
```

Các module sử dụng có thể khai báo phụ thuộc rõ ràng đến giao diện này:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "shared :: money"
)
package com.acme.shop.order;
```

Nếu `order` còn cần phụ thuộc vào module khác, danh sách `allowedDependencies` cần liệt kê đầy đủ những module hoặc Named Interface được phép. Khi đã khai báo allowlist, các dependency không nằm trong danh sách sẽ bị xem là vi phạm.

Shared kernel chỉ nên chứa phần nhỏ mà các bên thực sự cùng sở hữu. Cần có quy ước thay đổi, kiểm thử và phối hợp khi hợp đồng chung thay đổi. Nếu một module liên tục phải điều chỉnh shared kernel để phục vụ nhu cầu riêng, đó là dấu hiệu cần xem lại ranh giới và quyền sở hữu.

## 7. Công bố API hẹp thay vì mở toàn bộ package dùng chung

Một module `shared` không nên trở thành nơi mọi module có thể import mọi lớp. Root package của module đóng là API mặc định; package con không được công bố vẫn là nội bộ. Named Interface giúp mở đúng hợp đồng cần thiết.

Ví dụ, module `shared` có thể có hai nhóm:

```text
shared
├── money
│   ├── Money.java
│   └── package-info.java       // Named Interface: money
├── identifiers
│   ├── EntityId.java
│   └── package-info.java       // Named Interface: identifiers
└── internal
    └── CurrencyMetadataLoader.java
```

Nếu `order` chỉ cần `Money`, nó có thể khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "shared :: money"
)
package com.acme.shop.order;
```

Điều này làm cho ý định phụ thuộc được thể hiện ngay trong cấu trúc và annotation. `order` không cần quyền truy cập vào `shared.internal` hoặc Named Interface `identifiers` nếu không có nhu cầu.

Không nên công bố một package con chỉ để làm cho lỗi kiểm tra biến mất. Trước khi mở một Named Interface, hãy xác định consumer, trường hợp sử dụng và trách nhiệm tương thích của hợp đồng đó.

## 8. Giữ hướng phụ thuộc một chiều

Module dùng chung nên độc lập với các capability cụ thể. Nếu `common` phụ thuộc vào `order`, trong khi `order` cũng phụ thuộc vào `common`, ta tạo chu trình:

```text
order --------> common
  ^               |
  |               |
  +---------------+
```

Trong thực tế, chu trình có thể xuất hiện gián tiếp qua nhiều module. Ví dụ `order -> shared -> customer -> order`. Khi đó, một thay đổi ở một module có thể buộc nhiều module khác thay đổi cùng lúc, làm giảm khả năng tách biệt.

Một nguyên tắc hữu ích là các module nghiệp vụ có thể phụ thuộc vào một shared kernel nhỏ và ổn định, nhưng shared kernel không nên phụ thuộc ngược vào các module nghiệp vụ. Nếu phần dùng chung cần gọi một quy trình nghiệp vụ, hãy để module nghiệp vụ sở hữu quy trình đó và công bố API phù hợp. Nếu hai module cần trao đổi một sự thật, có thể dùng application event để giảm phụ thuộc gọi trực tiếp.

Spring Modulith có thể kiểm tra chu trình phụ thuộc và các quy tắc module. Ví dụ, bài test kiến trúc:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kết hợp với `allowedDependencies`, nhóm có thể định nghĩa module nào được phép sử dụng API nào. Kiểm tra nên được chạy trong test suite hoặc CI để phát hiện dependency mới vượt khỏi quy tắc đã thống nhất.

## 9. Khi nào nên tạo module dùng chung?

Trước khi đưa một type vào `common` hoặc `shared`, hãy xem xét các câu hỏi sau:

1. Các module có thực sự hiểu type này theo cùng một ý nghĩa nghiệp vụ không?
2. Có một module nào đang sở hữu khái niệm đó và có thể công bố API phù hợp không?
3. Type này có ổn định hơn các module sử dụng nó không?
4. Có thể công bố một Named Interface nhỏ thay vì mở toàn bộ package không?
5. Module dùng chung có thể giữ độc lập, không phụ thuộc ngược vào capability cụ thể không?
6. Ai chịu trách nhiệm thay đổi, tương thích và kiểm thử hợp đồng này?

Nếu câu trả lời cho quyền sở hữu hoặc ngữ nghĩa còn mơ hồ, hãy giữ type trong module đang sở hữu nó và công bố hợp đồng cần thiết. Nếu đó chỉ là một hàm kỹ thuật nhỏ, hãy cân nhắc lặp lại thay vì tạo thêm một module có fan-in cao. Nếu các module thực sự chia sẻ cùng một khái niệm ổn định, một shared kernel nhỏ với API rõ ràng có thể là lựa chọn phù hợp.

## 10. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Tên `common` làm package trở thành vùng dùng chung đặc biệt. | Spring Modulith dựa vào vị trí package và cấu hình; `common` ở cấp con trực tiếp có thể là một application module bình thường. |
| Lớp được hai module dùng thì nên chuyển vào shared. | Cần xem xét quyền sở hữu và ngữ nghĩa; dùng chung không có nghĩa là cùng một hợp đồng nghiệp vụ. |
| Shared module càng nhiều API càng tiện. | API rộng làm tăng fan-in và phạm vi ảnh hưởng khi thay đổi. |
| Đưa repository hoặc entity vào common giúp tái sử dụng tốt hơn. | Nó làm lộ chi tiết triển khai và tạo phụ thuộc vào mô hình lưu trữ của module sở hữu dữ liệu. |
| `allowedDependencies` chỉ mang tính tài liệu. | Khi kiểm tra mô hình, danh sách cho phép được dùng để phát hiện dependency ngoài allowlist. |
| Named Interface làm package nội bộ trở thành API toàn cục. | Nó công bố một package cụ thể của một module; consumer vẫn cần phụ thuộc đúng module/interface đó. |
| Shared kernel có thể chứa mọi thứ được nhiều module import. | Shared kernel nên nhỏ, ổn định, cùng ngữ nghĩa và có trách nhiệm thay đổi rõ ràng. |

## 11. Ghi nhớ

Package dùng chung giải quyết nhu cầu tái sử dụng, nhưng cũng có thể trở thành điểm tập trung phụ thuộc và che khuất quyền sở hữu nghiệp vụ. Một package `common` ở cấp module là một application module với API và dependency riêng; tên gọi của nó không làm cho các type bên trong tự động trung lập hoặc an toàn để mọi module sử dụng.

Hãy để mỗi capability sở hữu khái niệm nghiệp vụ của mình, công bố API hoặc event khi module khác thực sự cần dùng, và chỉ tạo shared kernel cho những khái niệm nhỏ có cùng ngữ nghĩa. Dùng Named Interface để công bố hợp đồng hẹp, `allowedDependencies` để diễn đạt dependency được phép và `ApplicationModules.verify()` để kiểm tra ranh giới. Nhờ vậy, code dùng chung hỗ trợ modular monolith mà không biến thành một vùng phụ thuộc ngầm khó thay đổi.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)

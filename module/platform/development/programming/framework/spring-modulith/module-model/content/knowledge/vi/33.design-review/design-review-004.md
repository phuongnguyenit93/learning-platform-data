# Đối chiếu `allowedDependencies` với nhu cầu

`allowedDependencies` là cam kết kiến trúc về những module mà một application module được phép sử dụng. Một khai báo tốt phải phản ánh đúng dependency mà code thực sự cần, đồng thời chỉ mở đúng phần API mà consumer sử dụng.

Trong design review, không nên chọn dependency chỉ để làm `ApplicationModules.verify()` hết lỗi. Cần lần từ import và type reference trong code đến module sở hữu type, xác định package đó là root API hay named interface, rồi mới quyết định rule. Khai báo quá rộng làm giảm giá trị của boundary; khai báo quá hẹp khiến module không thể sử dụng hợp đồng hợp lệ.

Bài học này đưa ra cách review có hệ thống, cú pháp dependency, các lựa chọn wildcard, ví dụ trước/sau và tiêu chí chấp nhận một thay đổi `allowedDependencies`.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích `allowedDependencies` kiểm soát quan hệ nào giữa các application module.
- Phân biệt dependency thực tế trong code với dependency được phép theo metadata.
- Ánh xạ type được import về đúng module identifier và API package sở hữu nó.
- Chọn root API, named interface hoặc wildcard đúng theo nhu cầu consumer.
- Nhận diện allowlist quá rộng, quá hẹp, sai module identifier hoặc sai tên interface.
- Đánh giá dependency có hợp lý về hướng, quyền sở hữu và trách nhiệm nghiệp vụ không.
- Dùng `ApplicationModules.verify()` làm bằng chứng cho review.
- Viết checklist và quyết định review có thể kiểm chứng.

## `allowedDependencies` kiểm soát điều gì?

Mỗi application module có một base package. Root package của module là API mặc định; các package con là internal, trừ khi được công bố rõ ràng bằng `@NamedInterface` hoặc module được cấu hình mở.

`allowedDependencies` nằm trên metadata của module consumer và liệt kê những module/API mà consumer được phép phụ thuộc. Ví dụ:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "orders", "inventory :: reservation" }
)
package com.acme.shipping;
```

Trong ví dụ này, module `shipping` được phép dùng root API của module `orders` và named interface `reservation` của module `inventory`.

Hai câu hỏi phải được review riêng:

1. **Provider có công bố type đó không?** Root package hoặc named interface phải tạo ra API hợp lệ.
2. **Consumer có được phép phụ thuộc vào API đó không?** `allowedDependencies` phải cho phép đúng module và interface.

Một allowlist không thể biến package internal thành public API. Ngược lại, một named interface đã được công bố cũng không tự động có nghĩa mọi consumer đều được phép dùng nó khi consumer đã bật explicit dependency rules.

Nếu module không khai báo `allowedDependencies`, module không thiết lập allowlist tường minh; các dependency module được chấp nhận theo quy tắc API visibility mặc định của Spring Modulith. Khi đã khai báo danh sách, các dependency thực tế phải khớp với những entry được cho phép. Vì vậy, việc thêm annotation này là một quyết định siết chính sách dependency, không chỉ là ghi chú tài liệu.

## Phân biệt dependency thực tế và dependency được phép

Dependency thực tế được tạo ra khi type trong module này tham chiếu type thuộc module khác. Tham chiếu có thể xuất hiện trong:

- Import và kiểu tham số, kiểu trả về hoặc field.
- Constructor injection và method signature của Spring bean.
- Generic type, superclass hoặc interface được triển khai.
- Event type mà module tiêu thụ hoặc phát hành.
- Annotation hoặc cấu hình có tham chiếu đến type thuộc module khác.

`allowedDependencies` là tập quyền mà nhóm muốn cấp. Nó không tự tạo dependency và cũng không loại bỏ dependency đang có trong bytecode. Verification so sánh mô hình dependency thực tế với ranh giới được khai báo.

Ví dụ, `shipping` import `OrderLookup` từ root package `orders` và `ReservationService` từ named interface `inventory::reservation`. Khi đó, hai dependency thực tế là:

```text
shipping -> orders
shipping -> inventory :: reservation
```

Nếu code không tham chiếu module `billing`, không nên thêm `billing` vào allowlist chỉ vì có thể sẽ cần trong tương lai. Khi nhu cầu xuất hiện, review và bổ sung dependency cùng thay đổi code cụ thể.

## Cú pháp các dạng dependency

Giá trị của `allowedDependencies` dùng logical module identifier. Khi cần giới hạn vào named interface, dùng dấu phân cách `::` giữa module và tên interface.

| Khai báo | Phạm vi được phép | Khi nên dùng |
|---|---|---|
| `"orders"` | Root API của module `orders` | Consumer chỉ cần hợp đồng chính ở base package |
| `"orders :: events"` | Named interface `events` của `orders` | Consumer chỉ lắng nghe hoặc tham chiếu event contract |
| `"orders :: spi"` | Named interface `spi` của `orders` | Consumer triển khai hoặc sử dụng SPI đã công bố |
| `"orders :: *"` | Tất cả named interface được khai báo của `orders`, không bao gồm root package | Consumer cần nhiều named interface nhưng không cần root API |
| `"orders :: **"` | Root package và tất cả named interface được khai báo của `orders` | Consumer thực sự cần toàn bộ bề mặt API được công bố |

Có thể khai báo nhiều dependency:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "orders",
        "inventory :: reservation",
        "customers :: events"
    }
)
package com.acme.shipping;
```

Khi dùng nhiều entry, mỗi entry nên tương ứng với một dependency trực tiếp có lý do rõ ràng. Không thêm wildcard để thay thế việc hiểu code đang dùng API nào.

## Review module identifier và named interface name

Dependency phải dùng logical identifier của module, không dùng display name, tên class hay tên package đoán từ folder.

Ví dụ module khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    id = "order-management",
    displayName = "Quản lý đơn hàng"
)
package com.acme.orders;
```

Consumer tham chiếu bằng `order-management`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order-management"
)
package com.acme.shipping;
```

Không dùng `Quản lý đơn hàng` trong `allowedDependencies`. Display name có thể được dịch hoặc đổi để tài liệu dễ đọc; identifier là khóa logic để cấu hình dependency.

Tương tự, named interface phải dùng đúng tên được khai báo:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.orders.events;
```

Dependency hợp lệ là `order-management :: events`. Các giá trị `orders :: event`, `order-management :: Events` hoặc `Quản lý đơn hàng :: events` không trỏ đến đúng cặp identifier/interface đã khai báo.

## Quy trình review: từ code đến allowlist

Với mỗi dependency mới hoặc hiện hữu, reviewer nên đi theo một chuỗi kiểm tra có thể truy vết:

1. Xác định module consumer sở hữu code đang tham chiếu type.
2. Ghi lại fully qualified name của type được tham chiếu.
3. Xác định base package và logical identifier của module sở hữu type.
4. Xác định type nằm trong root package, named interface hay package internal.
5. Giải thích vì sao consumer cần type đó để hoàn thành trách nhiệm nghiệp vụ.
6. Chọn entry hẹp nhất trong `allowedDependencies` đáp ứng nhu cầu.
7. Kiểm tra hướng dependency có phù hợp với quyền sở hữu nghiệp vụ không.
8. Chạy module verification và đọc mọi vi phạm còn lại.
9. Review lại allowlist sau khi code thay đổi để loại entry không còn cần.

Một bảng dependency inventory giúp reviewer tránh bỏ sót:

| Consumer | Type được dùng | Module sở hữu | API package | Entry dự kiến | Lý do |
|---|---|---|---|---|---|
| `shipping` | `OrderLookup` | `orders` | Root package | `orders` | Tra cứu đơn hàng |
| `shipping` | `ReservationService` | `inventory` | `reservation` | `inventory :: reservation` | Yêu cầu giữ hàng |
| `notifications` | `OrderCompleted` | `orders` | `events` | `orders :: events` | Gửi thông báo sau khi đơn hoàn tất |

Không phải mọi dependency trong inventory đều phải được cho phép. Nếu type đang được dùng nằm trong package internal, hãy xem lại API boundary trước khi thêm entry.

## Ví dụ design review: dependency vừa đủ

Giả sử ứng dụng có các module:

```text
com.acme
├── orders
│   ├── OrderLookup.java
│   ├── events
│   │   ├── package-info.java
│   │   └── OrderCompleted.java
│   └── internal
│       └── JpaOrderRepository.java
├── inventory
│   ├── reservation
│   │   ├── package-info.java
│   │   └── ReservationService.java
│   └── internal
│       └── JpaStockRepository.java
└── shipping
    ├── package-info.java
    └── internal
        └── ShippingService.java
```

Module `shipping` cần tra cứu đơn hàng và yêu cầu giữ hàng. Nó không cần repository, entity hoặc implementation persistence của hai module kia.

Metadata của `orders.events`:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.orders.events;
```

Metadata của `inventory.reservation`:

```java
@org.springframework.modulith.NamedInterface("reservation")
package com.acme.inventory.reservation;
```

Metadata của `shipping`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "orders",
        "inventory :: reservation"
    }
)
package com.acme.shipping;
```

Review này hợp lý nếu code `shipping` chỉ import `OrderLookup` từ root API và `ReservationService` từ named interface `reservation`. `shipping` không được phép dùng `orders.events` theo allowlist trên; nếu sau này cần event type, nhóm phải bổ sung entry `orders :: events` cùng lý do.

## Nhận diện allowlist quá rộng

Allowlist quá rộng cho phép consumer phụ thuộc vào nhiều API hơn nhu cầu thực tế. Một số dấu hiệu:

- Dùng `orders :: **` trong khi code chỉ import một interface ở root package.
- Dùng `inventory :: *` dù consumer chỉ cần `inventory :: reservation`.
- Liệt kê module không có type reference nào trong code.
- Cho phép một module chỉ vì dependency có thể cần trong tương lai.
- Cho phép nhiều named interface nhưng không có owner hoặc consumer chịu trách nhiệm giải thích.

Ví dụ:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "orders :: **",
        "inventory :: *",
        "billing",
        "customers"
    }
)
package com.acme.shipping;
```

Nếu `shipping` chỉ cần `OrderLookup` và `ReservationService`, khai báo trên cấp quyền quá mức. Có thể thu hẹp thành:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "orders",
        "inventory :: reservation"
    }
)
package com.acme.shipping;
```

Thu hẹp allowlist giúp thay đổi API trong module provider ít có khả năng vô tình ảnh hưởng consumer. Nó cũng làm code review thấy rõ hợp đồng mà module thực sự dựa vào.

## Nhận diện allowlist quá hẹp hoặc thiếu

Allowlist quá hẹp thường xuất hiện khi:

- Consumer import một named interface nhưng chỉ khai báo tên module không đúng.
- Tên module trong entry không khớp `id`.
- Tên named interface sai chính tả hoặc sai chữ hoa/thường.
- Consumer cần cả root API và named interface nhưng chỉ cho phép một trong hai.
- Code mới thêm dependency nhưng metadata chưa được cập nhật.

Ví dụ consumer dùng cả `OrderLookup` ở root và `OrderCompleted` ở `orders::events`, nhưng chỉ khai báo:

```java
@org.springframework.modulith.ApplicationModule(allowedDependencies = "orders :: events")
package com.acme.notifications;
```

Nếu consumer thực sự cần cả root API, hãy khai báo cả hai:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "orders", "orders :: events" }
)
package com.acme.notifications;
```

Không dùng `orders :: **` chỉ để tránh phải liệt kê hai entry nếu nhóm muốn giữ dependency rõ ràng và có thể review từng API.

## `allowedDependencies` không công bố package internal

Đây là một lỗi thiết kế dễ gặp: consumer import type từ package internal, verification báo lỗi, rồi reviewer thêm module đó vào `allowedDependencies` với hy vọng cho phép truy cập.

Ví dụ:

```java
import com.acme.orders.internal.JpaOrderRepository;
```

Thêm `orders` hoặc `orders :: **` không phải cách sửa đúng cho một package internal. Wildcard `**` bao gồm root API và các named interface được công bố; nó không biến mọi package internal thành named interface.

Hãy chọn một trong các hướng:

- Đưa interface nghiệp vụ và DTO cần thiết ra root package.
- Đánh dấu package API bổ sung bằng `@NamedInterface`.
- Chuyển trách nhiệm về module sở hữu dữ liệu hoặc logic.
- Dùng application event nếu consumer chỉ cần phản ứng với một sự kiện đã xảy ra.

Không công bố repository, JPA entity hoặc implementation chỉ để vượt qua verification. Điều đó làm ranh giới mất ý nghĩa và khóa consumer vào chi tiết triển khai.

## Kiểm tra hướng dependency và quyền sở hữu

Một entry có thể hợp lệ về cú pháp nhưng không hợp lý về kiến trúc. Reviewer cần hỏi:

- Module consumer có thực sự sở hữu use case đang gọi không?
- Module provider có đang cung cấp capability qua API ổn định không?
- Có dependency ngược khiến provider phải biết consumer không?
- Hai module có đang chia sẻ entity hoặc repository thay vì trao đổi qua hợp đồng?
- Dependency có tạo chu trình trong module graph không?
- Một application event có phù hợp hơn lời gọi service trực tiếp không?

Ví dụ, nếu `orders` import `shipping.ShippingService` chỉ để tính phí giao hàng, có thể trách nhiệm đang bị đảo. `orders` có thể định nghĩa một SPI để provider triển khai, hoặc gọi một capability công khai phù hợp theo hướng dependency đã thống nhất. Không nên giải quyết bằng cách thêm `orders` vào allowlist của `shipping` nếu dependency code thực tế đi theo chiều ngược lại.

`allowedDependencies` không sửa chu trình. Nếu `orders` phụ thuộc `shipping` và `shipping` cũng phụ thuộc `orders`, cần xem lại ownership, tách hợp đồng hoặc dùng event để loại bỏ một cạnh. Sau đó chạy verification để xác nhận graph không còn cycle.

## Phân biệt dependency trực tiếp và dependency bắc cầu

Allowlist của một module nên phản ánh các module mà code của nó trực tiếp tham chiếu. Nếu `shipping` dùng API của `orders`, và `orders` tự dùng `customers`, điều đó không tự động có nghĩa `shipping` cần thêm `customers` vào allowlist.

Chỉ thêm `customers` nếu code trong `shipping` thực sự tham chiếu type thuộc module đó. Tránh mở rộng dependency theo suy luận rằng module A phụ thuộc B, B phụ thuộc C nên A cũng cần quyền dùng C.

Nếu một public API làm lộ type của module khác trong chữ ký, consumer có thể tạo dependency trực tiếp vào type đó. Đây là lý do cần review cả generic type, return type, superclass và annotation, không chỉ các câu `import` hiển thị ở đầu file.

## Đưa quyết định vào `ApplicationModules.verify()`

Một test kiến trúc giúp kiểm tra dependency thực tế so với module metadata:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesAllowedDependencies() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

Nếu cần đọc thông báo chi tiết trước khi test thất bại:

```java
var violations = ApplicationModules.of(Application.class)
    .detectViolations();

violations.getMessages().forEach(System.err::println);
violations.throwIfPresent();
```

Verification giúp phát hiện dependency không được phép, truy cập package internal và dependency cycle. Nó không đánh giá được lý do nghiệp vụ của một entry allowlist. Reviewer vẫn phải xác nhận dependency có cần thiết và đúng hướng không.

Khi model test pass, hãy đọc lại allowlist để phát hiện quyền thừa. Một test pass chỉ chứng minh các dependency hiện tại không vi phạm rule; nó không chứng minh rule được khai báo hẹp nhất hoặc thiết kế module đã tối ưu.

## Review theo từng thay đổi pull request

Khi pull request thêm hoặc sửa `allowedDependencies`, reviewer nên yêu cầu bằng chứng:

| Nội dung review | Bằng chứng mong đợi |
|---|---|
| Module consumer | Package root và logical identifier chính xác |
| Type được sử dụng | Import, signature hoặc event contract cụ thể |
| Module provider | Base package và owner của type |
| API surface | Root package hoặc tên named interface chính xác |
| Lý do dependency | Use case mà consumer cần hoàn thành |
| Độ rộng rule | Entry hẹp nhất đáp ứng nhu cầu; giải thích nếu dùng wildcard |
| Hướng dependency | Không tạo cạnh ngược hoặc chu trình không mong muốn |
| Verification | Kết quả `ApplicationModules.verify()` |
| Tính cần thiết | Entry không còn dùng được loại bỏ hoặc có kế hoạch xóa |

Nếu một entry mới chỉ được giải thích bằng câu “để test pass”, yêu cầu bổ sung lý do kiến trúc trước khi chấp nhận.

## Checklist design review

- [ ] Mỗi entry tương ứng với dependency trực tiếp mà code thực sự cần.
- [ ] Module identifier lấy từ `id` hoặc tên module được phát hiện, không lấy từ display name.
- [ ] Tên named interface khớp chính xác với `@NamedInterface`.
- [ ] Type consumer dùng nằm trong root API hoặc named interface được công bố.
- [ ] Không dùng `allowedDependencies` để mở package internal.
- [ ] Không dùng `*` hoặc `**` khi chỉ cần một API hẹp hơn.
- [ ] Không thêm dependency bắc cầu nếu consumer không trực tiếp tham chiếu module đó.
- [ ] Không tạo dependency ngược hoặc chu trình giữa các module.
- [ ] Mỗi dependency có lý do nghiệp vụ và owner có thể giải thích.
- [ ] Entry không còn cần đã được loại bỏ.
- [ ] `ApplicationModules.verify()` chạy thành công trong CI.
- [ ] Các thay đổi API và dependency được phản ánh trong tài liệu module.

## Bài tập tự đánh giá

Ứng dụng có ba module `orders`, `inventory` và `shipping`.

- `shipping` import `OrderLookup` từ root package `orders`.
- `shipping` import `ReservationService` từ named interface `inventory::reservation`.
- `shipping` không dùng event của `orders`.
- `shipping` không import bất kỳ type nào từ `billing`.

Metadata hiện tại của `shipping`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "orders :: **",
        "inventory :: *",
        "billing"
    }
)
package com.acme.shipping;
```

Hãy thực hiện design review:

1. Entry nào đang cấp quyền rộng hơn nhu cầu?
2. Vì sao `orders :: **` rộng hơn cần thiết?
3. Vì sao `inventory :: *` chưa thể hiện đúng hợp đồng consumer đang dùng?
4. Vì sao `billing` nên được loại bỏ?
5. Allowlist tối thiểu nào phản ánh đúng dependency thực tế?
6. Cần kiểm tra điều gì nếu verification vẫn báo `ReservationService` là internal?

Một kết quả phù hợp là:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "orders",
        "inventory :: reservation"
    }
)
package com.acme.shipping;
```

Nếu verification vẫn báo `ReservationService` là internal, hãy kiểm tra package `com.acme.inventory.reservation` đã được đánh dấu `@NamedInterface("reservation")` chưa. Allowlist chỉ cho phép một API đã được công bố; nó không tự công bố package.

## Kết luận

Một `allowedDependencies` tốt phản ánh đúng dependency trực tiếp và cấp quyền hẹp nhất đủ cho consumer. Review phải lần từ type thực tế đến module identifier, root API hoặc named interface, sau đó kiểm tra hướng dependency và lý do nghiệp vụ. Tránh wildcard và dependency dự phòng nếu không có nhu cầu rõ ràng; không dùng allowlist để mở package internal hoặc che dependency cycle. `ApplicationModules.verify()` cung cấp bằng chứng kỹ thuật, còn reviewer chịu trách nhiệm đánh giá tính cần thiết và chất lượng của từng cạnh trong module graph.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals: Application Modules and Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith API — `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)

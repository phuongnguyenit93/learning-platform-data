# Đọc thông báo vi phạm và vị trí nguyên nhân

Khi `ApplicationModules.verify()` thất bại, thông báo vi phạm là đầu mối để xác định module nào đang tạo dependency sai, module nào bị tham chiếu và kiểu hoặc package nào làm phát sinh quan hệ đó. Đọc đúng diagnostic giúp sửa chính xác cạnh dependency hoặc ranh giới API gây lỗi, thay vì nới quy tắc kiến trúc để làm cho bài kiểm tra chạy qua.

Trong Spring Modulith, một vi phạm thường có thể được phân tích theo ba thành phần: **consumer** là module tạo tham chiếu, **provider** là module sở hữu kiểu được tham chiếu, và **reference** là kiểu/package cụ thể nối hai module. Với dependency cycle, cần lần theo nhiều cạnh cho tới khi đường đi quay lại module ban đầu. Định dạng thông báo có thể thay đổi theo phiên bản Spring Modulith, ArchUnit và test runner; vì vậy hãy đọc tên module, lớp và package trong diagnostic thay vì phụ thuộc vào một chuỗi thông báo cố định.

Trong `SPRING_MODULITH_MODULE_MODEL`, kỹ năng đọc lỗi verification giúp xác định nguyên nhân ở đúng lớp kiến trúc: dependency cycle, truy cập internal package hoặc dependency ngoài whitelist `allowedDependencies`.

## 1. Bắt đầu từ nơi `verify()` thất bại

Thông thường, kiểm tra kiến trúc được đặt trong một JUnit test:

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

Khi mô hình vi phạm quy tắc, `verify()` ném lỗi tổng hợp các vi phạm và làm test thất bại. IDE hoặc build report thường hiển thị stack trace, thông báo vi phạm và vị trí test gọi `verify()`.

Điểm cần nhớ: dòng stack trace trỏ tới `ModularityTests.verifiesModuleStructure()` thường chỉ là nơi kiểm tra được gọi. Nó chưa chắc là dòng mã nguồn tạo ra dependency sai. Muốn tìm nguyên nhân, cần đọc phần diagnostic mô tả module và kiểu liên quan.

Một quy trình đọc nhanh:

1. Tìm loại vi phạm hoặc cụm từ mô tả quy tắc bị phá vỡ.
2. Ghi lại module consumer và module provider.
3. Ghi lại fully qualified class name hoặc package xuất hiện trong thông báo.
4. Tìm nơi consumer tham chiếu kiểu của provider.
5. Đối chiếu tham chiếu đó với API package, Named Interface và whitelist.

## 2. Phân biệt vị trí test thất bại và vị trí nguyên nhân

Một báo cáo lỗi thường chứa nhiều lớp thông tin:

| Thông tin | Ý nghĩa | Có phải nguyên nhân trực tiếp không? |
|---|---|---|
| Tên test method | Test đang chạy `verify()` | Không; chỉ là điểm kích hoạt kiểm tra |
| Stack trace của `verify()` | Đường gọi dẫn tới lỗi | Thường không; chủ yếu chỉ ra nơi kiểm tra được gọi |
| Tên module consumer | Module tạo dependency | Là một đầu mối quan trọng |
| Tên module provider | Module sở hữu kiểu được tham chiếu | Là đầu mối quan trọng thứ hai |
| Tên lớp hoặc package | Kiểu hoặc package liên quan đến vi phạm | Thường là đầu mối gần nhất để tìm mã nguồn |
| Mô tả quy tắc | Cycle, internal access hoặc dependency không được phép | Xác định loại nguyên nhân cần xử lý |

Ví dụ, stack trace có thể trỏ tới dòng:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Nhưng dependency thực tế có thể đến từ một constructor trong `PlaceOrderService`, một field, kiểu tham số hoặc một interface mà lớp này implement. Hãy dùng tên kiểu trong diagnostic để lần ngược về reference trong mã nguồn.

## 3. Nhận diện ba nhóm vi phạm thường gặp

Trước khi mở IDE hoặc tìm kiếm toàn repository, hãy phân loại diagnostic:

| Nhóm vi phạm | Dấu hiệu cần tìm | Câu hỏi đầu tiên |
|---|---|---|
| Dependency cycle | Chuỗi module tạo thành vòng hoặc thông báo cycle | Đường đi nào quay về module bắt đầu? |
| Internal package access | Consumer tham chiếu package con chưa được expose | Kiểu đích có nằm trong API package hoặc Named Interface không? |
| Dependency không được cho phép | Consumer tạo dependency trực tiếp ngoài whitelist | Module hoặc named interface đó đã được khai báo trong `allowedDependencies` chưa? |

Một lỗi có thể đồng thời thuộc nhiều nhóm. Ví dụ, `order` có thể vừa truy cập `inventory.internal`, vừa có dependency tới `inventory` không nằm trong whitelist. Khi đó, cần sửa cả phạm vi API và quy tắc dependency tương ứng.

## 4. Đọc lỗi truy cập internal package

Giả sử diagnostic cho biết module `order` tham chiếu một kiểu thuộc `inventory.internal`. Ví dụ dưới đây là cách diễn đạt minh họa, không phải định dạng thông báo cố định của mọi phiên bản:

```text
Module 'order' depends on non-exposed type
'com.example.shop.inventory.internal.InventoryRepository'
```

Hãy phân tích thông tin:

- `order` là consumer: module có mã nguồn tạo reference.
- `inventory` là provider: module sở hữu kiểu đích.
- `inventory.internal` là package đích: package con chưa được expose.
- `InventoryRepository` là kiểu cụ thể cần tìm trong source.

Ví dụ reference gây lỗi:

```java
package com.example.shop.order.internal;

import com.example.shop.inventory.internal.InventoryRepository;

class PlaceOrderService {

    private final InventoryRepository repository;

    PlaceOrderService(InventoryRepository repository) {
        this.repository = repository;
    }
}
```

Nếu `inventory` là closed module, package con `internal` không tự trở thành API chỉ vì `InventoryRepository` được khai báo `public`. Java visibility và module encapsulation là hai lớp quy tắc khác nhau.

### Cách lần tới source reference

Từ fully qualified class name trong diagnostic:

1. Mở lớp `InventoryRepository` để xác nhận package khai báo.
2. Tìm các import `com.example.shop.inventory.internal.InventoryRepository` trong module consumer.
3. Kiểm tra field, constructor parameter, method parameter/return type, generic type, `extends`, `implements`, annotation attribute và static import có tham chiếu kiểu đó không.
4. Xác định lớp consumer thuộc package/module nào.
5. Kiểm tra package đích có được expose bằng `@NamedInterface` hay provider có phải `OPEN` module không.

Nếu consumer chỉ cần khả năng kiểm tra tồn kho, hướng sửa thường là phụ thuộc vào interface công khai như `InventoryAvailability` ở package gốc `inventory`, còn repository vẫn ở trong provider.

## 5. Đọc lỗi dependency không nằm trong `allowedDependencies`

Giả sử `order` khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.order;
```

Nhưng một lớp trong `order` tham chiếu trực tiếp `PaymentProcessing` thuộc module `payment`. Diagnostic có thể mô tả dependency không được cho phép, chẳng hạn:

```text
Module 'order' depends on module 'payment',
but only 'inventory' is allowed.
```

Đây là thông báo minh họa để nhận diện ý nghĩa. Cách diễn đạt thực tế có thể khác. Cách đọc:

- Consumer: `order`.
- Provider: `payment`.
- Dependency trực tiếp: `order → payment`.
- Whitelist hiện tại: chỉ cho phép `inventory`.

Tìm reference tới kiểu thuộc `payment` trong source của `order`. Sau đó quyết định:

- Nếu dependency là có chủ đích, bổ sung đúng identifier hoặc named interface vào `allowedDependencies`.
- Nếu dependency không nên tồn tại, chuyển consumer sang API của module mà nó đã được phép sử dụng hoặc tái cấu trúc trách nhiệm.
- Nếu chỉ cần một phần API, dùng `payment::processing` thay vì cho phép rộng toàn module.

Whitelist kiểm soát dependency trực tiếp. Module xuất hiện ở cuối đường phụ thuộc bắc cầu không cần được liệt kê nếu consumer không tham chiếu trực tiếp module đó.

## 6. Phân biệt lỗi whitelist và lỗi encapsulation

Hai lỗi này dễ bị nhầm vì cùng liên quan tới dependency giữa hai module, nhưng chúng kiểm tra hai điều kiện khác nhau.

| Câu hỏi | `allowedDependencies` | Encapsulation |
|---|---|---|
| Kiểm tra điều gì? | Consumer được phép phụ thuộc module/interface nào? | Provider đã expose package chứa kiểu được tham chiếu chưa? |
| Khai báo ở đâu? | Package gốc của consumer | Package metadata của provider hoặc kiểu module của provider |
| Ví dụ hợp lệ | `order` được phép phụ thuộc `inventory` | `InventoryAvailability` nằm trong API package gốc `inventory` |
| Ví dụ vi phạm | `order` tham chiếu `payment` nhưng whitelist không có `payment` | `order` import `inventory.internal.InventoryRepository` khi provider đóng |

Một dependency có thể vượt qua whitelist nhưng vẫn vi phạm encapsulation. Ví dụ, `order` được phép phụ thuộc `inventory`, nhưng lại import `inventory.internal.InventoryRepository`. Khi đó, whitelist cho phép module provider, còn package đích vẫn chưa được expose.

Ngược lại, provider có thể công bố một Named Interface, nhưng consumer vẫn phải khai báo dependency tương ứng nếu đang sử dụng whitelist. Hai phía cần khớp nhau.

## 7. Đọc lỗi dependency cycle

Diagnostic về cycle có thể liệt kê các module tham gia hoặc các cạnh tạo thành chu kỳ. Hãy đọc theo thứ tự mũi tên, không chỉ nhìn tập tên module.

Ví dụ minh họa:

```text
order → inventory → catalog → pricing → order
```

Các cạnh có nghĩa:

1. `order` tham chiếu kiểu thuộc `inventory`.
2. `inventory` tham chiếu kiểu thuộc `catalog`.
3. `catalog` tham chiếu kiểu thuộc `pricing`.
4. `pricing` tham chiếu ngược kiểu thuộc `order`.

Để tìm nguyên nhân, lần từng cạnh về source reference tương ứng. Không giả định cạnh cuối cùng được báo là cạnh duy nhất sai; cả vòng là cấu trúc cần xử lý. Chọn cạnh cần loại bỏ dựa trên quyền sở hữu nghiệp vụ và hợp đồng đang bị tham chiếu.

### Bảng lần theo chu kỳ

| Cạnh | Consumer | Provider | Reference cần tìm |
|---|---|---|---|
| `order → inventory` | `order` | `inventory` | API tồn kho được order sử dụng |
| `inventory → catalog` | `inventory` | `catalog` | Kiểu tra cứu sản phẩm |
| `catalog → pricing` | `catalog` | `pricing` | Hợp đồng tính giá |
| `pricing → order` | `pricing` | `order` | Kiểu ngữ cảnh đơn hàng bị tham chiếu ngược |

Sau khi xác định reference tạo cạnh không hợp lý, cân nhắc truyền dữ liệu qua API, chuyển hợp đồng về module sở hữu đúng trách nhiệm hoặc dùng event theo chiều phù hợp. Chỉ đổi package name hoặc chuyển module sang `OPEN` không loại bỏ dependency edge.

## 8. Tìm source reference hiệu quả

Khi diagnostic cung cấp fully qualified class name, có thể dùng các khả năng tìm kiếm của IDE hoặc công cụ tìm kiếm mã nguồn để xác định reference.

Ví dụ tên kiểu cần tìm:

```text
com.example.shop.inventory.internal.InventoryRepository
```

Các điểm cần kiểm tra trong consumer:

- Dòng `import` trực tiếp.
- Field hoặc property có kiểu provider.
- Constructor hoặc setter parameter.
- Method parameter và return type.
- Generic argument như `List<ProviderType>` hoặc `Optional<ProviderType>`.
- Superclass, implemented interface hoặc nested type.
- Annotation có thuộc tính tham chiếu tới kiểu provider.
- Static import hoặc constant được khai báo trong provider.

Không phải mọi dependency đều xuất hiện dưới dạng một field được inject. Một method signature hoặc interface inheritance cũng có thể tạo tham chiếu giữa các module. Vì vậy, nếu không tìm thấy constructor injection, hãy mở rộng việc tìm kiếm sang toàn bộ cách sử dụng kiểu.

Nếu diagnostic chỉ nêu package thay vì lớp, tìm mọi kiểu trong package đó được import hoặc tham chiếu từ consumer. Nếu diagnostic nêu lớp consumer, bắt đầu từ lớp đó rồi lần tới kiểu provider.

## 9. Diagnostic không phải lúc nào cũng có số dòng source

`ApplicationModules.verify()` phân tích mô hình kiểu và dependency. Diagnostic có thể chỉ nêu tên module, lớp và package, không nhất thiết luôn cung cấp số dòng giống compiler error.

Phân biệt:

| Loại thông báo | Thường chỉ ra | Cách tìm vị trí mã nguồn |
|---|---|---|
| Java compiler error | File và dòng không biên dịch được | Mở trực tiếp vị trí compiler chỉ ra |
| Spring context startup error | Bean hoặc dependency injection point không khởi tạo được | Đọc nguyên nhân gốc trong chuỗi `Caused by` và mở constructor/configuration liên quan |
| Modulith architecture violation | Module, kiểu hoặc package tạo quan hệ kiến trúc không hợp lệ | Tìm source reference từ consumer tới provider |
| Test assertion failure | Test method và assertion thất bại | Đọc assertion; nếu gọi `verify()`, tiếp tục đọc phần violations bên dưới |

Nếu IDE chỉ đưa bạn tới dòng `verify()`, đó là bình thường. Dùng tên lớp/package trong diagnostic để tìm vị trí reference thực tế.

## 10. Một diagnostic có thể chứa nhiều vi phạm

`verify()` có thể báo nhiều vi phạm trong một lần chạy. Không nên xử lý tất cả như các lỗi độc lập mà chưa nhóm theo nguyên nhân.

Ví dụ, một lớp trong `order` tham chiếu cả `inventory.internal.InventoryRepository` và `payment.PaymentProcessing`, trong khi whitelist chỉ cho phép `inventory`. Có thể xuất hiện cả lỗi encapsulation và lỗi dependency không được phép.

Hãy lập bảng theo dõi:

| Consumer | Provider | Reference | Loại vi phạm | Quyết định |
|---|---|---|---|---|
| `order` | `inventory` | `InventoryRepository` | Internal package access | Chuyển sang API `InventoryAvailability` |
| `order` | `payment` | `PaymentProcessing` | Dependency not allowed | Xác nhận nghiệp vụ; nếu hợp lệ thì thêm whitelist/interface |

Sau khi sửa một nguyên nhân gốc, chạy lại verification. Một thay đổi có thể loại bỏ nhiều dòng diagnostic hoặc làm lộ ra một vi phạm khác trước đó bị che khuất.

## 11. Đọc lỗi liên quan đến Named Interface

Nếu consumer khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.example.shop.order;
```

nhưng provider chưa đánh dấu package `spi`, hoặc tên khai báo không khớp, verification có thể báo dependency tới named interface không hợp lệ.

Kiểm tra phía provider:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.inventory.spi;
```

Đối chiếu bốn yếu tố:

1. Module identifier trước `::` có đúng không?
2. Tên sau `::` có khớp giá trị `@NamedInterface` không?
3. Annotation có nằm trong `package-info.java` của đúng package không?
4. Kiểu được consumer tham chiếu có thực sự thuộc package đã expose không?

Nếu consumer cần API package gốc, dependency phải tham chiếu module identifier phù hợp. Nếu cần named interface, cả provider và consumer đều phải khai báo đúng tên và phạm vi.

## 12. Kiểm tra ảnh hưởng của detection và exclusion

Trước khi kết luận một dependency không xuất hiện trong diagnostic là hợp lệ, hãy xác nhận kiểu và module liên quan có nằm trong mô hình đang được kiểm tra.

Kết quả phụ thuộc vào:

- Root class truyền vào `ApplicationModules.of(...)`.
- Detection strategy đang dùng.
- Package metadata đã được biên dịch và có trên classpath.
- Các package gốc bổ sung nếu ứng dụng cấu hình thêm.
- Ignored predicate dùng để loại trừ class hoặc package khỏi inspection.

Ví dụ, nếu một lớp bị ignored predicate loại trừ, các tham chiếu từ lớp đó có thể không xuất hiện trong kết quả verification. Điều này không có nghĩa dependency đã được sửa; nó có nghĩa lớp đó không tham gia phạm vi inspection hiện tại.

Hãy xem lại phạm vi exclusion khi diagnostic dường như thiếu một cạnh mà bạn biết đang tồn tại trong source. Chỉ loại trừ mã generated hoặc legacy khi có lý do rõ ràng và phạm vi đủ hẹp.

## 13. Không sửa lỗi bằng cách nới quy tắc một cách máy móc

Một số thay đổi có thể làm mất một thông báo cụ thể nhưng làm suy yếu kiến trúc:

| Cách sửa vội | Rủi ro | Hướng xử lý tốt hơn |
|---|---|---|
| Đổi provider thành `OPEN` | Mở mọi package của module | Expose API package gốc hoặc Named Interface cần thiết |
| Thêm `**` hoặc wildcard rộng | Consumer có quyền dùng nhiều API hơn nhu cầu | Khai báo đúng module/interface được sử dụng |
| Thêm mọi module vào `allowedDependencies` | Whitelist không còn thể hiện ranh giới | Chỉ cho phép dependency trực tiếp có chủ đích |
| Loại trừ cả package nghiệp vụ | Diagnostic biến mất nhưng dependency vẫn còn trong code | Sửa reference hoặc giới hạn exclusion vào mã ngoài phạm vi |
| Di chuyển lớp sang package khác mà không đổi owner | Có thể chỉ che dấu vị trí, không sửa quan hệ nghiệp vụ | Xác định module sở hữu hợp đồng và hướng phụ thuộc đúng |

Mục tiêu là làm cho dependency phản ánh đúng trách nhiệm nghiệp vụ, không phải chỉ làm cho báo cáo lỗi ngắn hơn.

## 14. Quy trình xử lý một lần verification thất bại

Có thể áp dụng quy trình sau mỗi khi test kiến trúc báo lỗi:

1. **Đọc toàn bộ diagnostic.** Không dừng ở dòng đầu tiên hoặc stack trace của test.
2. **Phân loại vi phạm.** Cycle, internal access, whitelist hay Named Interface.
3. **Ghi consumer và provider.** Dùng tên module trong thông báo.
4. **Tìm reference.** Dùng fully qualified type hoặc package để tìm import, field, signature và inheritance.
5. **Kiểm tra metadata.** Xem `@ApplicationModule`, `@NamedInterface`, `allowedDependencies` và module type.
6. **Xác định ý định kiến trúc.** Dependency có thực sự cần thiết? Ai sở hữu hợp đồng?
7. **Chọn thay đổi nhỏ nhất đúng nguyên nhân.** Sửa reference, expose API phù hợp hoặc điều chỉnh whitelist có chủ đích.
8. **Chạy lại verification.** Xác nhận lỗi cũ biến mất và không phát sinh vi phạm mới.
9. **Chạy test phù hợp khác.** Context test xác nhận bean wiring; unit/integration test xác nhận nghiệp vụ.
10. **Ghi lại quyết định nếu có ngoại lệ.** Đặc biệt với open module hoặc exclusion predicate.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Dòng stack trace của `verify()` là dòng source gây lỗi | Đó thường chỉ là nơi test gọi kiểm tra; tìm consumer và target type trong diagnostic. |
| Mọi lỗi đều là dependency cycle | Cần phân loại cycle, internal access và dependency ngoài whitelist. |
| Kiểu `public` không thể gây lỗi encapsulation | Kiểu `public` trong package con chưa expose vẫn có thể vi phạm module boundary. |
| Thêm provider vào whitelist sẽ mở package internal | Whitelist và API exposure là hai điều kiện độc lập. |
| Module bắc cầu phải có trong `allowedDependencies` | Whitelist kiểm soát dependency trực tiếp của consumer. |
| Diagnostic luôn có số dòng source | Có thể chỉ nêu tên module, lớp hoặc package; cần tìm reference bằng IDE/search. |
| Một dòng diagnostic tương ứng một nguyên nhân độc lập | Nhiều vi phạm có thể bắt nguồn từ cùng một reference hoặc quyết định thiết kế. |
| Loại trừ lớp làm dependency biến mất khỏi ứng dụng | Lớp chỉ bị bỏ khỏi inspection; source và bytecode vẫn tồn tại. |
| Chuyển module sang `OPEN` là cách sửa mọi lỗi | Open không giải quyết cycle và không thay thế whitelist. |

## 16. Checklist đọc diagnostic

- [ ] Đọc toàn bộ phần violations, không chỉ stack trace.
- [ ] Xác định test method nào gọi `ApplicationModules.verify()`.
- [ ] Ghi loại vi phạm được mô tả.
- [ ] Xác định module consumer và module provider.
- [ ] Ghi fully qualified class name hoặc package đích.
- [ ] Tìm reference trong import, field, constructor, method signature và inheritance.
- [ ] Kiểm tra provider có expose API package gốc hoặc Named Interface phù hợp không.
- [ ] Kiểm tra whitelist `allowedDependencies` ở consumer.
- [ ] Nếu là cycle, lần đủ các cạnh cho tới khi quay về module bắt đầu.
- [ ] Kiểm tra detection strategy, classpath và ignored predicate nếu kết quả bất thường.
- [ ] Sửa nguyên nhân kiến trúc, không nới quy tắc chỉ để test qua.
- [ ] Chạy lại verification và các test runtime liên quan.

## 17. Kết luận

Đọc thông báo vi phạm của `ApplicationModules.verify()` cần bắt đầu từ loại quy tắc bị phá vỡ, sau đó xác định consumer, provider và kiểu/package tạo reference. Stack trace thường chỉ ra nơi gọi kiểm tra; tên module và fully qualified class name trong diagnostic mới là manh mối để lần về source code thực tế.

Với internal access, kiểm tra package đã được expose chưa. Với dependency không được phép, đối chiếu reference trực tiếp với `allowedDependencies`. Với dependency cycle, lần theo toàn bộ đường có hướng cho tới khi quay lại module bắt đầu. Sau khi sửa, chạy lại verification và bổ sung context hoặc business tests khi cần. Cách làm này giữ nguyên mục tiêu của Spring Modulith: bảo vệ ranh giới module bằng các hợp đồng rõ ràng và dependency có chủ đích.

## Tài liệu tham khảo

- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — `ApplicationModules` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith — `Violations` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/Violations.html)

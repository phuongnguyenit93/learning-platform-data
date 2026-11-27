# Phát hiện test truy cập internal package

Một application module có thể giữ các package con như `internal`, `persistence` hoặc `infrastructure` làm chi tiết triển khai. Spring Modulith kiểm tra để code của module khác không tham chiếu các type trong những package đó. Tuy nhiên, kiểm tra mặc định chỉ phân tích production code. Nếu một test của module `inventory` import trực tiếp `orders.internal.OrderRepository`, lời gọi `ApplicationModules.of(ShopApplication.class).verify()` thông thường sẽ không nhìn thấy quan hệ do test tạo ra.

Để phát hiện loại phụ thuộc này, cần tạo module model với `ImportOption` cho phép import cả production classes và test classes. Sau đó gọi `verify()` trên model đã bao gồm test source. Nhờ vậy, một test vượt qua ranh giới module cũng tạo ra architectural violation và có thể làm test kiến trúc thất bại.

## 1. Vì sao verification mặc định không thấy test-only dependency?

Lời gọi phổ biến:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.verify();
```

được thiết kế để kiểm tra cấu trúc production. Spring Modulith sử dụng import option loại trừ test classes theo quy ước thư mục build thông dụng của Maven, Gradle và IntelliJ. Vì vậy, các tham chiếu chỉ xuất hiện trong `src/test/java` không được đưa vào dependency model mặc định.

Điều này tạo ra hai kết quả khác nhau:

| Loại tham chiếu | Verification mặc định |
|---|---|
| `OrderManagement` trong production của `inventory` import `orders.internal.OrderRepository` | Được phát hiện và báo vi phạm |
| `InventoryTests` trong test source của `inventory` import `orders.internal.OrderRepository` | Không được phát hiện nếu dùng `ApplicationModules.of(ShopApplication.class)` mặc định |

Lý do cần tách hai trường hợp là test source được loại khỏi mô hình production có chủ đích. Nhưng nếu mục tiêu là bảo vệ ranh giới cả trong test, architecture test phải yêu cầu import test classes một cách tường minh.

## 2. Dùng ImportOption để đưa test classes vào module model

Từ Spring Modulith 1.2, `ApplicationModules.of(...)` có overload nhận `com.tngtech.archunit.core.importer.ImportOption`. Có thể truyền `ImportOption.Predefined.DO_NOT_INCLUDE_ARCHIVES` để import các class nằm trong thư mục output của dự án, bao gồm cả production classes và test classes, đồng thời loại JAR và JRT archive.

```java
import com.tngtech.archunit.core.importer.ImportOption;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(
        ShopApplication.class,
        ImportOption.Predefined.DO_NOT_INCLUDE_ARCHIVES);

modules.verify();
```

Khác với factory mặc định, overload này dùng import option được truyền vào để quyết định class location nào được phân tích. `DO_NOT_INCLUDE_ARCHIVES` không loại test output directory, vì vậy test classes có thể tham gia module model cùng với production classes.

Đặt đoạn kiểm tra trong một architecture test của JUnit:

```java
import com.tngtech.archunit.core.importer.ImportOption;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesProductionAndTestCodeRespectModuleBoundaries() {
        ApplicationModules.of(
                ShopApplication.class,
                ImportOption.Predefined.DO_NOT_INCLUDE_ARCHIVES)
                .verify();
    }
}
```

Khi test classes được import, dependency graph bao gồm cả những tham chiếu được khai báo trong test. Nếu một test của module này sử dụng type nội bộ của module khác, `verify()` có thể phát hiện quan hệ đó như một vi phạm truy cập API.

## 3. Đặt test trong package của module sở hữu nó

Spring Modulith xác định module nguồn dựa trên package của class. Vì vậy, test cần nằm trong package của module mà nó kiểm thử để dependency được gán đúng module nguồn.

Ví dụ cấu trúc Maven:

```text
src/main/java
└── com/acme/shop
    ├── ShopApplication.java
    ├── orders
    │   ├── OrderManagement.java
    │   └── internal
    │       └── OrderRepository.java
    └── inventory
        └── InventoryManagement.java

src/test/java
└── com/acme/shop
    ├── ModuleArchitectureTests.java
    └── inventory
        └── InventoryTests.java
```

`InventoryTests` thuộc package `com.acme.shop.inventory`, nên Spring Modulith xem các tham chiếu của test là dependency xuất phát từ module `inventory`. Test kiến trúc ở package gốc chỉ đóng vai trò khởi chạy verification.

Với Gradle, cấu trúc tương ứng thường nằm trong `src/main/java` và `src/test/java`; output đã biên dịch ở `build/classes/java/main` và `build/classes/java/test`. Maven thường dùng `target/classes` và `target/test-classes`. ArchUnit nhận diện các thư mục test phổ biến này khi áp dụng import option mặc định, còn `DO_NOT_INCLUDE_ARCHIVES` cho phép import cả hai nhóm class location.

## 4. Ví dụ test vô tình truy cập internal package

Giả sử module `orders` có một repository nội bộ:

```java
// src/main/java/com/acme/shop/orders/internal/OrderRepository.java
package com.acme.shop.orders.internal;

public interface OrderRepository {

    String findInternalRecord(String orderNumber);
}
```

Type có thể cần `public` để các thành phần trong module `orders` ở package khác sử dụng. Nhưng package `orders.internal` vẫn là phần triển khai nội bộ của module `orders`.

Một test ở module `inventory` tham chiếu trực tiếp type này:

```java
// src/test/java/com/acme/shop/inventory/InventoryTests.java
package com.acme.shop.inventory;

import com.acme.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Test;

class InventoryTests {

    @Test
    void readsOrderInternals() {
        OrderRepository repository = obtainRepository();
        // Test đang phụ thuộc vào chi tiết triển khai của orders.
    }

    private OrderRepository obtainRepository() {
        throw new UnsupportedOperationException("Test fixture placeholder");
    }
}
```

Đây là test-only dependency: production code của `inventory` có thể không import bất kỳ type nào từ `orders.internal`, nhưng test source vẫn tạo ra tham chiếu đó. Khi dùng module model có import cả test classes, `verify()` phát hiện test của `inventory` đang phụ thuộc type không được expose của `orders`.

Thông báo vi phạm có thể có dạng:

```text
Module 'inventory' depends on non-exposed type
'com.acme.shop.orders.internal.OrderRepository'
within module 'orders'!
```

Thông báo thực tế phụ thuộc tên module, type và vị trí tham chiếu trong dự án. Hãy đọc toàn bộ thông báo để tìm test class, field, constructor, method parameter hoặc method body tạo ra dependency.

## 5. Sửa test để chỉ sử dụng module API

Test của `inventory` nên kiểm tra hành vi qua hợp đồng công khai của `orders`. Ví dụ, nếu `orders` cung cấp `OrderLookup` trong package API:

```java
// src/main/java/com/acme/shop/orders/OrderLookup.java
package com.acme.shop.orders;

import java.util.Optional;

public interface OrderLookup {

    Optional<String> findByNumber(String orderNumber);
}
```

Test có thể phụ thuộc vào hợp đồng đó:

```java
package com.acme.shop.inventory;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Optional;

import com.acme.shop.orders.OrderLookup;
import org.junit.jupiter.api.Test;

class InventoryTests {

    @Test
    void checksOrderThroughPublicContract() {
        OrderLookup orders = orderNumber -> Optional.of("ORD-100");

        assertEquals(Optional.of("ORD-100"), orders.findByNumber("ORD-100"));
    }
}
```

Ví dụ này minh họa ranh giới type. Cách khởi tạo test fixture thực tế có thể dùng Mockito, Spring test context hoặc `@ApplicationModuleTest` tùy mục tiêu kiểm thử. Điểm quan trọng là test của module tiêu thụ chỉ tham chiếu type được expose từ module cung cấp.

Nếu API nằm trong named interface, module tiêu thụ cần khai báo `allowedDependencies` tương ứng, ví dụ `orders::order-api`. Việc import test classes cũng khiến quy tắc allowlist được áp dụng cho dependency phát sinh từ test; do đó, test cần tuân thủ chính sách phụ thuộc giống production code.

## 6. Phân biệt test nội bộ hợp lệ và test vượt ranh giới

Không phải mọi test truy cập internal package đều sai. Test nằm trong chính module đang kiểm thử có thể cần kiểm tra implementation nội bộ của module đó. Spring Modulith cho phép quan hệ nội bộ trong cùng module; điều cần phát hiện là truy cập từ module khác.

| Test source | Type được tham chiếu | Đánh giá |
|---|---|---|
| `orders.OrderManagementTests` | `orders.internal.OrderRepository` | Cùng module; có thể hợp lệ khi test implementation nội bộ |
| `inventory.InventoryTests` | `orders.internal.OrderRepository` | Khác module; vi phạm ranh giới `orders` nếu package đó không được expose |
| `inventory.InventoryTests` | `orders.OrderLookup` trong API package | Hợp lệ nếu dependency được phép |
| `inventory.InventoryTests` | Type trong named interface `orders::order-api` | Hợp lệ khi named interface được công khai và allowlist cho phép |

Điều này giúp test vẫn có thể kiểm tra chi tiết nội bộ của module sở hữu, trong khi ngăn test của module khác gắn chặt vào implementation mà module đó không cam kết duy trì.

## 7. Phân biệt ApplicationModules.verify() với @ApplicationModuleTest

Hai cơ chế hỗ trợ hai mục tiêu khác nhau:

| Cơ chế | Mục tiêu |
|---|---|
| `ApplicationModules.verify()` với import option bao gồm test | Kiểm tra tĩnh các tham chiếu giữa module trong production và test source |
| `@ApplicationModuleTest` | Khởi động Spring context giới hạn trong module đang được kiểm thử, cùng các dependency được chọn theo bootstrap mode |

`@ApplicationModuleTest` không tự động thay thế việc kiểm tra test source có import internal package hay không. Annotation này tập trung vào phạm vi Spring context và tích hợp module. Một test có thể chạy trong module context hợp lệ nhưng vẫn tham chiếu một type nội bộ của module khác ở mức Java.

Khi module test cần một Spring bean từ module khác nhưng module đó không được đưa vào bootstrap, có thể dùng `@MockitoBean` để thay bean phụ thuộc. Nếu nhiều test cần mở rộng bootstrap để lấy nhiều bean của module khác, hãy xem lại mức độ coupling và cân nhắc hợp đồng API hoặc domain event phù hợp.

## 8. Các quy tắc khác cũng được áp dụng cho test source

Khi đưa test classes vào `ApplicationModules`, toàn bộ verification chạy trên mô hình mở rộng. Điều đó có nghĩa test-only dependency có thể tạo ra nhiều loại vi phạm:

- **Truy cập internal package:** test của module `inventory` tham chiếu `orders.internal`.
- **Dependency không được allowlist:** module `inventory` chỉ cho phép `catalog`, nhưng test lại import API của `customers`.
- **Chu trình module:** test của `orders` tham chiếu API `inventory`, trong khi production `inventory` đã phụ thuộc `orders`.

Các vi phạm đó có thể là dấu hiệu test đang gắn với module ngoài phạm vi trách nhiệm. Không nên giải quyết bằng cách mở toàn bộ module thành `OPEN` chỉ để test có thể import type nội bộ. Hãy xác định test cần xác minh hợp đồng nào và sử dụng API được công khai phù hợp.

Một hệ quả cần lưu ý: module graph có test source sẽ có nhiều dependency record hơn graph production-only. Khi dùng graph để sinh tài liệu production, tiếp tục dùng import mặc định hoặc một model chỉ chứa production classes. Dùng model bao gồm test cho architecture test chuyên kiểm tra ranh giới của test source.

## 9. Tùy chọn import và giới hạn nhận diện test

ArchUnit cung cấp các `ImportOption.Predefined` khác nhau:

| Import option | Phạm vi |
|---|---|
| `DO_NOT_INCLUDE_TESTS` | Loại test classes; phù hợp với verification production-only và là hành vi mặc định của Spring Modulith |
| `DO_NOT_INCLUDE_ARCHIVES` | Loại JAR/JRT archive nhưng giữ class location trong thư mục dự án, gồm production và test output |
| `ONLY_INCLUDE_TESTS` | Chỉ import test classes; không phù hợp để tự tạo đầy đủ module model nếu thiếu production metadata |

ArchUnit nhận diện test location theo các quy ước build phổ biến, như Maven `target/test-classes`, Gradle `build/classes/.../test` và IntelliJ `out/test`. Với source set hoặc build layout tùy chỉnh, cần kiểm tra location thực tế và có thể viết `ImportOption` riêng. Đảm bảo import option luôn trả về kết quả ổn định cho cùng một location để không gây vấn đề với cơ chế cache của ArchUnit.

Overload `ApplicationModules.of(Class, ImportOption)` nhận một import option. Nếu cần kết hợp nhiều điều kiện lọc, có thể tạo một implementation `ImportOption` duy nhất với predicate kết hợp, thay vì giả định overload này nhận danh sách option.

## 10. Quy trình đưa kiểm tra test source vào CI

1. **Đặt test đúng package:** test thuộc `inventory` nằm dưới package `com.acme.shop.inventory` trong test source set.
2. **Tạo architecture test riêng:** dùng `ApplicationModules.of(ShopApplication.class, ImportOption.Predefined.DO_NOT_INCLUDE_ARCHIVES)`.
3. **Chạy verification:** gọi `verify()` để kiểm tra cả production và test classes.
4. **Đọc violation:** xác định module nguồn, module đích, type nội bộ và test class tạo dependency.
5. **Sửa test:** chuyển test sang API/named interface công khai hoặc giữ test ở module sở hữu implementation nếu mục tiêu là kiểm thử nội bộ.
6. **Giữ production verification riêng khi cần:** một test dùng model mặc định có thể tiếp tục bảo vệ production-only dependency graph và sinh tài liệu kiến trúc.
7. **Đưa architecture test vào CI:** bảo đảm test chạy trên mỗi thay đổi để test-only coupling không tích lũy.

Ví dụ test tổng hợp cho CI:

```java
import com.tngtech.archunit.core.importer.ImportOption;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTests {

    @Test
    void productionAndTestsOnlyUseExposedModuleTypes() {
        var modules = ApplicationModules.of(
                ShopApplication.class,
                ImportOption.Predefined.DO_NOT_INCLUDE_ARCHIVES);

        modules.verify();
    }
}
```

Khi test này thất bại, CI dừng tại architecture test và hiển thị `Violations`. Sau khi sửa dependency, chạy lại test để xác nhận cả production lẫn test source tuân thủ module boundary.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `ApplicationModules.of(...).verify()` mặc định kiểm tra cả test code | Factory mặc định loại test classes; cần overload nhận `ImportOption` để đưa test vào |
| Chỉ dùng `ONLY_INCLUDE_TESTS` để tạo module model đầy đủ | Option này loại production classes và có thể thiếu metadata cần thiết; dùng option giữ cả main và test class locations |
| Test trong module nào cũng được import như module đó | Package của test quyết định module nguồn; đặt test dưới package của module sở hữu |
| Test truy cập internal của module chính nó luôn là vi phạm | Tham chiếu trong cùng module được phép; cần chú ý dependency đi qua ranh giới module |
| `@ApplicationModuleTest` tự kiểm tra visibility của test source | Annotation giới hạn Spring context; static verification cần `ApplicationModules.verify()` với import option phù hợp |
| `DO_NOT_INCLUDE_ARCHIVES` chỉ import test classes | Nó giữ cả production và test class locations trong dự án, đồng thời loại archive |
| Mở module thành `OPEN` là cách sửa nhanh cho test | `OPEN` mở rộng bề mặt API; ưu tiên dùng API hoặc named interface được thiết kế rõ |
| Thêm test dependency không ảnh hưởng dependency graph | Khi import test source, dependency của test tham gia verification và có thể tạo chu trình hoặc vi phạm allowlist |

## 12. Checklist phát hiện test truy cập internal package

- [ ] Test class được đặt trong package của module sở hữu nó.
- [ ] Đã xác định test có cần truy cập internal của chính module hay đang tham chiếu module khác.
- [ ] Architecture test dùng overload `ApplicationModules.of(Class, ImportOption)`.
- [ ] Import option giữ cả production và test classes, ví dụ `DO_NOT_INCLUDE_ARCHIVES`.
- [ ] Đã gọi `verify()` trên module model bao gồm test source.
- [ ] Đã đọc toàn bộ `Violations` để tìm test class tạo ra dependency.
- [ ] Test liên module chỉ sử dụng package gốc hoặc named interface được công khai.
- [ ] Đã kiểm tra `allowedDependencies` cho các dependency phát sinh từ test.
- [ ] Không dùng `OPEN` để che giấu một test đang phụ thuộc implementation nội bộ.
- [ ] Architecture test được chạy trong CI cùng test suite.

Verification mặc định bảo vệ module boundary của production code. Khi bổ sung import option để đưa test classes vào cùng module model, nhóm có thể phát hiện cả những tham chiếu nội bộ chỉ xuất hiện trong test. Điều này giúp test kiểm tra hợp đồng mà module cung cấp, thay vì vô tình khóa chặt vào implementation của module khác.

## Tài liệu tham khảo

- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith – Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [ArchUnit – ImportOption API](https://javadoc.io/doc/com.tngtech.archunit/archunit/latest/com/tngtech/archunit/core/importer/ImportOption.html)
- [ArchUnit – Core API and ClassFileImporter](https://www.archunit.org/userguide/html/000_Index.html)
- [Introducing Spring Modulith – Verifying the Modular Structure](https://spring.io/blog/2022/10/21/introducing-spring-modulith/)

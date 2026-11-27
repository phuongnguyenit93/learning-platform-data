# JavaClass.Predicates.resideInAPackage

Bài này thuộc chương **Excluding packages** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp mô hình hóa application module trong ứng dụng Spring Boot, xác định ranh giới API và kiểm tra phụ thuộc giữa các package. Trong một số codebase, không phải mọi lớp nằm dưới phạm vi quét của ứng dụng đều thuộc mô hình module mà nhóm muốn kiểm tra.

`JavaClass.Predicates.resideInAPackage` cung cấp một cách mô tả package cần bỏ qua khi tạo mô hình bằng `ApplicationModules`. Nhờ đó, nhóm có thể loại trừ một package hạ tầng, mã sinh tự động hoặc phần code nằm ngoài phạm vi kiến trúc đang kiểm tra.

## 1. Vì sao cần loại trừ package?

Giả sử ứng dụng bán hàng có package như sau:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
├── inventory
│   ├── StockAvailability.java
│   └── internal
└── db
    ├── DatabaseConfiguration.java
    ├── MigrationSupport.java
    └── internal
~~~

Các package `order` và `inventory` là capability nghiệp vụ mà nhóm muốn mô hình hóa thành application module. Package `db` chứa một số thành phần hạ tầng dùng chung, không phải capability nghiệp vụ mà nhóm muốn đưa vào kiểm tra module trong ví dụ này.

Khi phân tích cấu trúc ứng dụng, có thể cần bỏ qua package `db` để mô hình tập trung vào các module nghiệp vụ. Spring Modulith hỗ trợ truyền một predicate vào overload của `ApplicationModules.of(…)` để xác định những kiểu cần bỏ qua.

## 2. JavaClass.Predicates.resideInAPackage làm gì?

`JavaClass.Predicates.resideInAPackage(String)` tạo ra một predicate kiểm tra package của một kiểu Java theo biểu thức package matcher của ArchUnit.

Spring Modulith nhận predicate đó làm tham số thứ hai của `ApplicationModules.of`:

~~~java
import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(
    ShopApplication.class,
    JavaClass.Predicates.resideInAPackage("com.acme.shop.db..")
);

modules.verify();
~~~

Trong ví dụ:

- `ShopApplication.class` xác định ứng dụng và package gốc dùng để xây dựng mô hình.
- `JavaClass.Predicates.resideInAPackage("com.acme.shop.db..")` mô tả các lớp nằm trong package `com.acme.shop.db` và những package con của nó.
- Predicate được truyền vào `ApplicationModules.of` là điều kiện nhận diện các kiểu cần bỏ qua khỏi quá trình kiểm tra module.
- `verify()` thực hiện kiểm tra kiến trúc trên mô hình đã được tạo sau khi áp dụng điều kiện loại trừ.

Điểm quan trọng: predicate trả về `true` cho những lớp cần loại trừ. Nó không phải danh sách các lớp được giữ lại.

## 3. Phân biệt package chính xác và package con

Biểu thức truyền vào `resideInAPackage` tuân theo cú pháp matcher của ArchUnit, tương tự cách biểu diễn package trong AspectJ. Hai dấu chấm `..` có ý nghĩa đặc biệt: chúng đại diện cho một chuỗi package bất kỳ, có thể gồm nhiều cấp.

| Biểu thức | Phạm vi khớp | Ví dụ |
|---|---|---|
| `com.acme.shop.db` | Chỉ package chính xác `com.acme.shop.db`. | `com.acme.shop.db.DatabaseConfiguration` |
| `com.acme.shop.db..` | Package `db` và tất cả package con. | `com.acme.shop.db.internal.ConnectionFactory` |
| `..db..` | Package có đoạn tên `db` ở vị trí bất kỳ và các package con bên dưới nó. | `com.acme.shop.db`, `com.acme.shop.shared.db.internal` |
| `..generated..` | Các package có đoạn `generated` ở vị trí bất kỳ. | `com.acme.shop.generated`, `com.acme.shop.order.generated.dto` |

Nếu mục tiêu là bỏ qua toàn bộ package `db`, bao gồm các package con, hãy dùng:

~~~java
JavaClass.Predicates.resideInAPackage("com.acme.shop.db..")
~~~

Nếu chỉ dùng `com.acme.shop.db`, các lớp trong `com.acme.shop.db.internal` không được bao phủ bởi biểu thức đó. Đây là nguyên nhân phổ biến khiến nhóm tưởng đã loại trừ toàn bộ cây package nhưng một số kiểu vẫn xuất hiện trong mô hình.

Dấu `*` có thể đại diện cho một chuỗi ký tự trong tên package; `..` đại diện cho một chuỗi package. Với các mẫu phức tạp, hãy kiểm tra quy tắc của ArchUnit `PackageMatcher` trước khi dùng rộng rãi.

## 4. Loại trừ một package khỏi ApplicationModules

Ví dụ đầy đủ với ứng dụng bán hàng:

~~~java
package com.acme.shop.architecture;

import com.acme.shop.ShopApplication;
import com.tngtech.archunit.core.domain.JavaClass;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesBusinessModules() {
        ApplicationModules.of(
            ShopApplication.class,
            JavaClass.Predicates.resideInAPackage("com.acme.shop.db..")
        ).verify();
    }
}
~~~

Bài kiểm tra trên yêu cầu Spring Modulith xây dựng mô hình ứng dụng, bỏ qua các lớp nằm trong cây package `com.acme.shop.db`, rồi xác minh cấu trúc module còn lại.

Cách làm này hữu ích khi package bị loại trừ thực sự nằm ngoài phạm vi kiến trúc cần kiểm tra, chẳng hạn một khu vực hỗ trợ hạ tầng dùng chung mà nhóm chưa coi là application module.

## 5. Loại trừ nhiều package

Nếu cần bỏ qua nhiều vùng package, ArchUnit cung cấp `JavaClass.Predicates.resideInAnyPackage(String...)`. Có thể truyền predicate này vào cùng overload của `ApplicationModules.of`:

~~~java
import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(
    ShopApplication.class,
    JavaClass.Predicates.resideInAnyPackage(
        "com.acme.shop.db..",
        "com.acme.shop.generated..",
        "com.acme.shop.legacybridge.."
    )
);

modules.verify();
~~~

Trong ví dụ, ba vùng package được bỏ qua:

- `db`: thành phần hỗ trợ lưu trữ và cấu hình cơ sở dữ liệu.
- `generated`: mã được sinh tự động.
- `legacybridge`: một vùng tích hợp cũ chưa thuộc phạm vi kiểm tra module hiện tại.

Chỉ thêm package vào danh sách loại trừ khi có lý do rõ ràng. Nếu `legacybridge` thực tế chứa capability nghiệp vụ cần kiểm tra, việc loại trừ nó sẽ khiến các phụ thuộc trong vùng đó không được phản ánh trong mô hình.

## 6. Kotlin cũng sử dụng được predicate này

Spring Modulith cung cấp cách gọi tương ứng cho Kotlin. Vì `ApplicationModules` nhận Java `Class`, dùng `Application::class.java` để chuyển class reference của Kotlin:

~~~kotlin
import com.tngtech.archunit.core.domain.JavaClass
import org.springframework.modulith.core.ApplicationModules

ApplicationModules.of(
    Application::class.java,
    JavaClass.Predicates.resideInAPackage("com.acme.shop.db..")
).verify()
~~~

Predicate vẫn có cùng ý nghĩa: xác định các lớp nằm trong package được chỉ định để bỏ qua khỏi quá trình kiểm tra module. Khác biệt chỉ là cú pháp tham chiếu lớp ứng dụng trong Kotlin.

## 7. Loại trừ package không thay đổi ứng dụng đang chạy

Cần hiểu đúng phạm vi của cơ chế này:

- Nó lọc các kiểu khỏi mô hình kiểm tra application module mà `ApplicationModules` xây dựng.
- Nó không xóa source code hoặc file class khỏi dự án.
- Nó không thay đổi component scanning của Spring Boot.
- Nó không ngăn Spring tạo bean hoặc ngăn ứng dụng gọi lớp trong package đó ở runtime.
- Nó không tự tạo module mới, không công khai API và không sửa dependency giữa các module.

Ví dụ, loại trừ `com.acme.shop.db..` khỏi mô hình không có nghĩa Spring Boot ngừng quét `DatabaseConfiguration`. Nếu lớp đó được cấu hình để đăng ký bean, ứng dụng vẫn có thể khởi tạo bean như trước. Việc loại trừ chỉ ảnh hưởng đến phần phân tích cấu trúc module do Spring Modulith thực hiện.

Tương tự, đây không phải cơ chế bảo mật hay cách ly package. Các lớp trong package bị loại trừ vẫn tồn tại và có thể được code khác tham chiếu theo các quy tắc Java/Spring thông thường.

## 8. Khi nào nên và không nên loại trừ?

| Tình huống | Khuyến nghị |
|---|---|
| Package chứa mã sinh tự động hoặc adapter hạ tầng ngoài phạm vi module cần kiểm tra. | Có thể loại trừ nếu phạm vi đó được xác định rõ. |
| Package chứa thư viện hoặc bridge legacy mà nhóm chưa quản lý như module nghiệp vụ. | Có thể loại trừ tạm thời, đồng thời ghi lại lý do và phạm vi. |
| Package chứa service, repository hoặc entity của một capability trong ứng dụng. | Không nên loại trừ chỉ để làm verification hết lỗi. |
| Package có phụ thuộc chéo cần được phát hiện và xử lý. | Giữ trong mô hình để Spring Modulith kiểm tra. |
| Package chứa mã nguồn nghiệp vụ mà nhóm muốn bảo vệ ranh giới lâu dài. | Nên giữ trong mô hình và sửa cấu trúc/API thay vì bỏ qua. |

Nếu loại trừ một package nghiệp vụ, nhóm sẽ mất khả năng dùng mô hình Spring Modulith để phát hiện những vi phạm liên quan đến các kiểu nằm trong vùng đó. Việc kiểm tra thành công khi ấy có thể tạo cảm giác an toàn giả.

## 9. Phân biệt exclusion với các cơ chế cấu hình khác

Không nên nhầm loại trừ package với các cơ chế sau:

| Cơ chế | Mục đích |
|---|---|
| `JavaClass.Predicates.resideInAPackage` | Bỏ qua các kiểu khớp package pattern khi tạo mô hình ApplicationModules. |
| `ApplicationModuleDetectionStrategy` | Quyết định package nào được chọn làm module base package. |
| `@NamedInterface` | Công khai một package con như API có tên của module. |
| `@ApplicationModule(allowedDependencies = ...)` | Khai báo các dependency được phép của module. |
| `@ApplicationModule(type = OPEN)` | Nới lỏng quy tắc đóng gói đối với các kiểu nội bộ của module. |

Nếu muốn thay đổi module nào được phát hiện, hãy xem chiến lược module detection. Nếu muốn module khác được truy cập một package con, hãy dùng named interface. Nếu muốn bỏ qua một vùng code khỏi quá trình inspection, hãy dùng predicate loại trừ.

## 10. Quy trình chọn và kiểm tra package cần loại trừ

1. **Xác định mục tiêu kiểm tra.** Nêu rõ mô hình ApplicationModules cần bao gồm những capability nào.
2. **Phân loại package ngoài phạm vi.** Xác định package nào chỉ chứa code hạ tầng, generated hoặc bridge mà nhóm không muốn kiểm tra ở bước này.
3. **Chọn biểu thức package.** Dùng tên package chính xác nếu chỉ bỏ qua một package; thêm `..` nếu cần bao gồm cả cây package con.
4. **Truyền predicate vào ApplicationModules.of.** Đặt bộ lọc tại nơi tạo mô hình dùng cho verification.
5. **Kiểm tra phạm vi bị loại trừ.** Đảm bảo không vô tình bỏ qua package chứa logic nghiệp vụ cần được bảo vệ.
6. **Chạy verify.** Xem các vi phạm còn lại và xử lý theo ranh giới module.
7. **Rà soát lại theo thời gian.** Khi codebase được modular hóa, xem xét bỏ các exclusion tạm thời để đưa vùng code đó trở lại mô hình kiểm tra.

Nên đặt cấu hình exclusion trong bài kiểm tra kiến trúc hoặc một helper dùng chung để nhóm hiểu rõ predicate đang áp dụng cho mô hình nào. Tránh tạo nhiều cấu hình lọc khác nhau mà không ghi lại mục đích.

## 11. Ví dụ kiểm tra phạm vi matcher

Giả sử có các kiểu:

~~~text
com.acme.shop.db.DatabaseConfiguration
com.acme.shop.db.internal.ConnectionFactory
com.acme.shop.order.OrderManagement
com.acme.shop.generated.OrderMapper
~~~

Nếu dùng `resideInAPackage("com.acme.shop.db")`, chỉ kiểu trong package chính xác `com.acme.shop.db` được khớp.

Nếu dùng `resideInAPackage("com.acme.shop.db..")`, cả `DatabaseConfiguration` và `ConnectionFactory` được khớp. `OrderManagement` và `OrderMapper` không bị loại trừ bởi biểu thức này.

Nếu cần loại trừ thêm mã sinh tự động, có thể dùng `resideInAnyPackage("com.acme.shop.db..", "com.acme.shop.generated..")`. Khi đó các kiểu trong hai cây package đều bị bỏ qua khỏi mô hình inspection.

Ví dụ này cho thấy việc chọn đúng pattern quan trọng không kém việc chọn đúng package. Một dấu `..` bị thiếu có thể khiến một phần package con vẫn tham gia kiểm tra.

## Ghi nhớ

`JavaClass.Predicates.resideInAPackage` tạo predicate theo package pattern của ArchUnit. Khi truyền predicate đó vào `ApplicationModules.of(Application.class, predicate)`, các lớp khớp predicate được bỏ qua khỏi quá trình kiểm tra cấu trúc application module.

Dùng `com.example.db` để khớp package chính xác, `com.example.db..` để khớp cả package và các package con. Hãy chỉ loại trừ những vùng thực sự nằm ngoài phạm vi kiểm tra, vì các kiểu bị bỏ qua sẽ không được mô hình Spring Modulith dùng để phát hiện vi phạm kiến trúc.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Excluding Packages](https://docs.spring.io/spring-modulith/reference/fundamentals.html#fundamentals.application-modules.excluding-packages)
- [Spring Modulith — ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [ArchUnit — JavaClass.Predicates](https://www.javadoc.io/doc/com.tngtech.archunit/archunit/latest/com/tngtech/archunit/core/domain/JavaClass.Predicates.html)
- [ArchUnit — PackageMatcher](https://www.javadoc.io/doc/com.tngtech.archunit/archunit/latest/com/tngtech/archunit/core/domain/PackageMatcher.html)

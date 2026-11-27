# Loại trừ class hoặc package khỏi module inspection

Spring Modulith xây dựng mô hình application module bằng cách phân tích các kiểu Java trong phạm vi ứng dụng. Trong một số dự án, classpath còn chứa mã được sinh tự động, lớp tương thích cũ hoặc package kỹ thuật không thuộc phần kiến trúc mà nhóm muốn kiểm tra. `ApplicationModules` cho phép truyền một predicate để chỉ định những lớp hoặc package cần bỏ qua khi inspection.

Predicate này đến từ ArchUnit và được áp dụng lên `JavaClass`. Vì vậy, có thể loại trừ một package cụ thể, toàn bộ package cùng các package con, một lớp riêng lẻ hoặc kết hợp nhiều điều kiện. Việc loại trừ chỉ ảnh hưởng đến mô hình kiểm tra của Spring Modulith; nó không xóa mã nguồn, không thay đổi classpath và không cấu hình component scan của Spring.

Trong `SPRING_MODULITH_MODULE_MODEL`, hiểu đúng cơ chế này giúp xử lý phần mã ngoài phạm vi kiến trúc mà không làm mờ các dependency nghiệp vụ cần được kiểm soát.

## 1. Vì sao cần loại trừ class hoặc package?

Thông thường, nên để Spring Modulith kiểm tra toàn bộ mã ứng dụng thuộc các module. Tuy nhiên, có những trường hợp một số kiểu không nên tham gia vào mô hình module đang xây dựng:

- **Mã sinh tự động:** các lớp được tạo từ OpenAPI, protobuf, JAXB hoặc công cụ sinh mã khác có thể nằm trong package riêng và không đại diện cho ranh giới nghiệp vụ.
- **Lớp tương thích legacy:** một adapter hoặc facade cũ có thể tạm thời nằm trong source set ứng dụng nhưng chưa được đưa vào kiến trúc module hiện tại.
- **Package tích hợp kỹ thuật:** một số lớp kết nối hoặc mã hỗ trợ nằm ngoài phạm vi module nghiệp vụ mà nhóm đang kiểm tra.
- **Một kiểu riêng biệt:** một lớp cụ thể có thể cần được bỏ qua trong giai đoạn chuyển đổi, trong khi các lớp khác cùng package vẫn cần được kiểm tra.

Ví dụ, ứng dụng có cấu trúc:

```text
com.example.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
├── inventory
│   ├── InventoryManagement.java
│   └── internal
├── generated
│   ├── OpenApiOrder.java
│   └── OpenApiCustomer.java
└── compatibility
    └── LegacyInventoryAdapter.java
```

Các package `order` và `inventory` là phần kiến trúc nghiệp vụ cần kiểm tra. `generated` có thể chứa kiểu sinh tự động, còn `LegacyInventoryAdapter` là một lớp chuyển tiếp cần loại trừ tạm thời. Thay vì bỏ qua toàn bộ ứng dụng, ta có thể tạo predicate khớp đúng phần mã đó.

## 2. Overload `ApplicationModules.of(...)` nhận predicate

`ApplicationModules` cung cấp overload nhận lớp ứng dụng và một `DescribedPredicate` của ArchUnit:

```java
ApplicationModules.of(ShopApplication.class, ignored);
```

Tham số thứ hai mô tả những `JavaClass` cần bỏ qua. Predicate trả về `true` cho kiểu được chọn để loại trừ khỏi module inspection.

Ví dụ hoàn chỉnh:

```java
import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

class ModuleInspection {

    void inspect() {
        var ignored = JavaClass.Predicates
                .resideInAPackage("com.example.shop.generated..");

        ApplicationModules modules = ApplicationModules.of(
                ShopApplication.class,
                ignored
        );

        modules.forEach(System.out::println);
        modules.verify();
    }
}
```

Trong ví dụ, `resideInAPackage(...)` tạo predicate khớp các lớp nằm trong package `com.example.shop.generated` và các package con của nó. `ApplicationModules.of(...)` sử dụng predicate này trong lúc xây dựng mô hình, sau đó `verify()` kiểm tra mô hình đã loại trừ các kiểu được chỉ định.

Lưu ý rằng tham số `ignored` là predicate trên `JavaClass`, không phải `java.util.function.Predicate<String>` và cũng không phải danh sách tên package thuần túy. Các helper trong `JavaClass.Predicates` giúp tạo predicate đúng kiểu mà API yêu cầu.

## 3. Loại trừ một package cụ thể

Để bỏ qua các lớp nằm trong đúng package `com.example.shop.generated`, dùng:

```java
var ignored = JavaClass.Predicates
        .resideInAPackage("com.example.shop.generated");

ApplicationModules modules = ApplicationModules.of(
        ShopApplication.class,
        ignored
);
```

Pattern `com.example.shop.generated` khớp package đó. Nếu các lớp được đặt trong package con như `com.example.shop.generated.order`, hãy dùng pattern có `..` ở cuối để bao gồm cả cây package:

```java
var ignored = JavaClass.Predicates
        .resideInAPackage("com.example.shop.generated..");
```

Sự khác nhau có thể tóm tắt như sau:

| Package pattern | Phạm vi khớp |
|---|---|
| `com.example.shop.generated` | Package `generated` |
| `com.example.shop.generated..` | Package `generated` và mọi package con |
| `..generated..` | Package có segment tên `generated` ở vị trí bất kỳ và các package con tương ứng |

Các pattern tuân theo cú pháp matcher package của ArchUnit, tương tự cách viết package pattern trong AspectJ. Dấu `..` biểu thị chuỗi package bất kỳ; vì vậy hãy chọn pattern đủ hẹp để tránh bỏ qua các lớp không liên quan.

## 4. Loại trừ một class cụ thể

Nếu chỉ cần bỏ qua một lớp, không cần loại trừ toàn bộ package. ArchUnit cung cấp `belongToAnyOf(...)`, predicate khớp chính lớp được truyền vào cùng các lớp inner hoặc anonymous thuộc lớp đó:

```java
import com.example.shop.compatibility.LegacyInventoryAdapter;
import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

var ignored = JavaClass.Predicates
        .belongToAnyOf(LegacyInventoryAdapter.class);

ApplicationModules modules = ApplicationModules.of(
        ShopApplication.class,
        ignored
);
```

Nếu chỉ muốn khớp chính xác kiểu được chỉ định mà không mở rộng tới các inner hoặc anonymous class, có thể dùng `equivalentTo(...)`:

```java
var ignored = JavaClass.Predicates
        .equivalentTo(LegacyInventoryAdapter.class);
```

Hai predicate có mục đích hơi khác nhau:

- `belongToAnyOf(LegacyInventoryAdapter.class)` khớp lớp đó và các inner/anonymous class thuộc nó.
- `equivalentTo(LegacyInventoryAdapter.class)` khớp đúng kiểu tương đương với lớp được chỉ định.

Ưu tiên dùng class literal thay vì so khớp theo simple name. Nếu nhiều package có lớp cùng tên, predicate theo simple name có thể vô tình loại trừ nhiều kiểu hơn dự định.

## 5. Kết hợp nhiều điều kiện loại trừ

Các `DescribedPredicate` có thể kết hợp bằng `.or(...)` và `.and(...)`. Để loại trừ nhiều package, có thể dùng `resideInAnyPackage(...)`:

```java
var ignoredPackages = JavaClass.Predicates.resideInAnyPackage(
        "com.example.shop.generated..",
        "com.example.shop.vendor.."
);
```

Để loại trừ package sinh tự động và một lớp legacy cụ thể:

```java
var ignored = JavaClass.Predicates
        .resideInAPackage("com.example.shop.generated..")
        .or(JavaClass.Predicates.belongToAnyOf(LegacyInventoryAdapter.class));

ApplicationModules modules = ApplicationModules.of(
        ShopApplication.class,
        ignored
);

modules.verify();
```

Predicate tổng hợp trả về `true` nếu một lớp thuộc package sinh tự động hoặc thuộc `LegacyInventoryAdapter`. Các kiểu còn lại tiếp tục tham gia inspection.

Có thể dùng `.and(...)` khi cần thu hẹp điều kiện. Ví dụ, chỉ loại trừ các lớp có tên kết thúc bằng `Generated` bên trong một package nhất định:

```java
var ignored = JavaClass.Predicates
        .resideInAPackage("com.example.shop.integration..")
        .and(JavaClass.Predicates.simpleNameEndingWith("Generated"));
```

Ở đây, cả hai điều kiện phải đúng: lớp nằm trong cây package `integration` và tên lớp kết thúc bằng `Generated`.

## 6. Ví dụ kiểm thử kiến trúc hoàn chỉnh

Thông thường, predicate được đặt ngay trong bài kiểm thử kiến trúc để mọi người hiểu vì sao một số kiểu bị bỏ qua:

```java
import com.example.shop.compatibility.LegacyInventoryAdapter;
import com.tngtech.archunit.core.domain.JavaClass;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModulesIgnoringGeneratedAndLegacyTypes() {
        var ignored = JavaClass.Predicates
                .resideInAPackage("com.example.shop.generated..")
                .or(JavaClass.Predicates.belongToAnyOf(LegacyInventoryAdapter.class));

        ApplicationModules.of(ShopApplication.class, ignored).verify();
    }
}
```

Đặt predicate gần kiểm thử giúp lý do loại trừ có thể được review cùng với quy tắc kiến trúc. Nếu nhiều bài kiểm thử cần cùng một phạm vi loại trừ, có thể tạo một phương thức hoặc hằng số dùng chung trong test support để tránh các predicate bị lệch nhau.

Ví dụ một phương thức tạo mô hình dùng chung:

```java
static ApplicationModules applicationModules() {
    var ignored = JavaClass.Predicates
            .resideInAPackage("com.example.shop.generated..");

    return ApplicationModules.of(ShopApplication.class, ignored);
}
```

Sau đó, các test có thể gọi:

```java
applicationModules().verify();
```

Chỉ nên chia sẻ cấu hình khi các kiểm thử thực sự cần cùng một phạm vi inspection. Nếu một test cần kiểm tra cả package generated, không dùng lại predicate đã loại trừ package đó.

## 7. Điều gì bị ảnh hưởng khi loại trừ?

Predicate loại trừ tác động tới mô hình mà `ApplicationModules` xây dựng và các kiểm tra kiến trúc chạy trên mô hình đó.

| Thành phần | Có bị loại trừ không? | Giải thích |
|---|---:|---|
| Kiểu Java khớp predicate | Có | Không tham gia module inspection theo mô hình được tạo |
| Kiểu nằm trong package con khớp pattern `..` | Có | Predicate bao phủ cả package con |
| Kiểu không khớp predicate | Không | Vẫn được phân tích như bình thường |
| File `.java` trên ổ đĩa | Không | Không bị xóa hoặc di chuyển |
| Class đã biên dịch trên classpath | Không | Vẫn tồn tại và có thể được JVM nạp |
| Spring bean registration | Không | Component scan và cấu hình `@Bean` không bị thay đổi |
| Runtime behavior của ứng dụng | Không trực tiếp | Predicate chỉ áp dụng cho mô hình inspection, không thay đổi logic chạy |

Điểm quan trọng là các vi phạm kiến trúc liên quan tới lớp bị bỏ qua có thể không còn xuất hiện trong kết quả kiểm tra của mô hình đó. Nếu một lớp bị loại trừ đang tạo dependency tới module khác, dependency xuất phát từ lớp đó sẽ không được đánh giá như khi lớp còn nằm trong inspection. Do vậy, loại trừ quá rộng có thể che khuất một quan hệ phụ thuộc cần được xử lý.

## 8. Không nhầm exclusion predicate với component scan hoặc import filter

Có ba cơ chế khác nhau cần phân biệt:

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| `ApplicationModules.of(..., ignored)` | Bỏ qua `JavaClass` khi xây dựng mô hình module | `resideInAPackage("com.example.shop.generated..")` |
| Spring component scan | Quyết định component nào được đăng ký thành bean | `@ComponentScan`, `@SpringBootApplication` |
| ArchUnit `ImportOption` | Lọc nguồn class được ArchUnit import trong quá trình phân tích | Chọn hoặc bỏ qua thư mục/classpath location |

Truyền ignored predicate cho `ApplicationModules` không làm cho Spring bỏ qua bean trong package đó. Nếu một lớp `@Service` nằm trong package bị loại trừ, Spring vẫn có thể đăng ký bean đó khi component scan bao phủ package. Ngược lại, bỏ package khỏi component scan không đồng nghĩa với việc package đó bị loại khỏi mô hình module.

Hãy chọn đúng cơ chế theo mục tiêu: muốn bỏ qua một số kiểu trong kiểm tra kiến trúc thì dùng ignored predicate; muốn thay đổi bean registration thì xem xét component scan; muốn lọc nơi ArchUnit đọc bytecode thì xem xét `ImportOption` phù hợp.

## 9. Chọn phạm vi loại trừ an toàn

Loại trừ là một ngoại lệ đối với phạm vi kiểm tra kiến trúc. Trước khi thêm predicate, hãy xác định rõ lý do và giới hạn:

1. **Ưu tiên loại trừ class cụ thể.** Nếu chỉ một adapter legacy gây nhiễu, bỏ qua lớp đó thay vì cả package chứa các thành phần nghiệp vụ khác.
2. **Dùng package pattern hẹp.** Tránh pattern chung như `com.example..` vì có thể loại trừ phần lớn ứng dụng.
3. **Phân biệt package chính xác và package con.** Chỉ thêm `..` khi thực sự muốn bao gồm các package lồng sâu.
4. **Ghi lại lý do.** Đặt tên predicate có ý nghĩa hoặc thêm comment để reviewer biết vì sao kiểu đó không nằm trong inspection.
5. **Định kỳ xem lại.** Khi mã generated hoặc legacy được tái tổ chức, hãy đánh giá xem exclusion còn cần thiết không.
6. **Giữ các module nghiệp vụ trong phạm vi kiểm tra.** Không dùng exclusion để làm cho một vi phạm dependency biến mất.

Ví dụ, nếu package `com.example.shop.generated` chỉ chứa lớp sinh tự động, pattern `com.example.shop.generated..` có phạm vi hợp lý. Nếu package đó chứa cả adapter nghiệp vụ do nhóm phát triển viết, hãy cân nhắc tách mã sinh tự động sang package riêng hoặc chỉ loại trừ từng lớp cần thiết.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Ignored predicate xóa class khỏi ứng dụng | Nó chỉ bỏ qua kiểu khi xây dựng mô hình module; mã nguồn và bytecode vẫn tồn tại. |
| Loại trừ package khỏi inspection sẽ ngăn Spring tạo bean | Component scan và bean registration không bị thay đổi. |
| `resideInAPackage("com.example.db")` luôn bao gồm mọi package con | Dùng `com.example.db..` nếu muốn bao gồm package đó và các package con. |
| Tham số thứ hai là `Predicate<String>` | API nhận `DescribedPredicate` trên `JavaClass` của ArchUnit. |
| Exclude một class bằng simple name luôn an toàn | Có thể trùng tên ở package khác; dùng class literal hoặc fully qualified package matcher khi cần chính xác. |
| Loại trừ nhiều package phải tạo nhiều lần `ApplicationModules` | Có thể kết hợp predicate bằng `or(...)` hoặc dùng `resideInAnyPackage(...)`. |
| Bỏ qua lớp legacy là cách sửa dependency lâu dài | Exclusion có thể che khuất dependency; hãy xem nó như ngoại lệ có lý do và đánh giá lại. |

## 11. Checklist loại trừ class hoặc package

- [ ] Xác định rõ lớp hoặc package nào nằm ngoài phạm vi module inspection.
- [ ] Ưu tiên predicate cụ thể thay vì pattern bao phủ quá rộng.
- [ ] Dùng `JavaClass.Predicates.resideInAPackage(...)` cho package.
- [ ] Thêm `..` khi muốn khớp cả package con.
- [ ] Dùng `belongToAnyOf(...)` hoặc `equivalentTo(...)` khi loại trừ class.
- [ ] Kết hợp nhiều điều kiện bằng `or(...)`, `and(...)` hoặc `resideInAnyPackage(...)`.
- [ ] Truyền predicate vào overload `ApplicationModules.of(ShopApplication.class, ignored)`.
- [ ] Kiểm tra lại mô hình và gọi `verify()`.
- [ ] Xác nhận các module nghiệp vụ quan trọng vẫn nằm trong phạm vi inspection.
- [ ] Ghi lại lý do và xem xét loại bỏ exclusion khi không còn cần thiết.

## 12. Kết luận

Spring Modulith cho phép loại trừ Java class hoặc package khỏi module inspection bằng cách truyền một `DescribedPredicate<JavaClass>` vào `ApplicationModules.of(...)`. ArchUnit cung cấp các predicate như `resideInAPackage`, `resideInAnyPackage`, `belongToAnyOf` và `equivalentTo` để mô tả phạm vi cần bỏ qua. Pattern package chính xác và pattern có `..` có phạm vi khác nhau, vì vậy cần chọn đúng mức bao phủ.

Exclusion chỉ tác động đến mô hình kiến trúc được phân tích; nó không xóa mã, thay đổi classpath, component scan hoặc runtime behavior. Hãy dùng cơ chế này cho mã generated hoặc legacy thực sự nằm ngoài phạm vi kiểm tra, giới hạn predicate ở mức hẹp và duy trì `ApplicationModules.verify()` cho phần module nghiệp vụ cần được bảo vệ.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Excluding Packages](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — `ApplicationModules` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [ArchUnit — `JavaClass.Predicates` API](https://www.javadoc.io/doc/com.tngtech.archunit/archunit/latest/com/tngtech/archunit/core/domain/JavaClass.Predicates.html)
- [ArchUnit — User Guide: Predicates](https://www.archunit.org/userguide/html/000_Index.html)

# Không dùng exclusion để thay việc sửa boundary

Spring Modulith cho phép loại một số class hoặc package khỏi quá trình kiểm tra mô hình module. Tính năng này hữu ích khi phạm vi quét có chứa mã kỹ thuật thực sự nằm ngoài phạm vi kiến trúc cần kiểm tra. Tuy nhiên, exclusion chỉ làm cho các type khớp điều kiện bị bỏ qua trong lần inspection đó. Nó không sửa package ownership, không tạo lại module boundary và không biến một dependency sai thành dependency hợp lệ.

Nếu một package thuộc ứng dụng nhưng đang nằm sai module, hoặc một module truy cập trực tiếp vào phần nội bộ của module khác, thêm exclusion có thể khiến báo cáo bớt lỗi trong khi vấn đề thiết kế vẫn còn nguyên. Bài học này giúp bạn phân biệt trường hợp nên loại khỏi inspection với trường hợp cần sửa cấu trúc module.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích exclusion package trong `ApplicationModules` tác động đến phần nào của quá trình kiểm tra.
- Viết predicate loại class hoặc package bằng `JavaClass.Predicates.resideInAPackage(…)`.
- Hiểu khác biệt giữa pattern khớp một package và pattern khớp cả cây package con.
- Nhận diện dấu hiệu exclusion đang che giấu một boundary sai.
- Chọn cách sửa phù hợp bằng cách di chuyển package, xác định module sở hữu, công bố named interface hoặc điều chỉnh dependency.
- Giới hạn phạm vi exclusion và kiểm thử để ngăn nó mở rộng ngoài ý muốn.

## Exclusion trong Spring Modulith làm gì?

`ApplicationModules` xây dựng mô hình module từ các type trong codebase. Mô hình này được dùng để kiểm tra cấu trúc module, quan hệ phụ thuộc và các quy tắc kiến trúc liên quan. Khi cần bỏ qua một số type hoặc package trong quá trình inspection, bạn có thể truyền một `DescribedPredicate` vào overload của `ApplicationModules.of(…)`:

```java
ApplicationModules modules = ApplicationModules.of(
    Application.class,
    JavaClass.Predicates.resideInAPackage("com.example.db")
);

modules.verify();
```

Tham số thứ hai là predicate mô tả các `JavaClass` cần bỏ qua. Tên tham số trong API là `ignored`, vì vậy predicate khớp với class nào thì class đó bị loại khỏi mô hình inspection.

Điểm cần nhớ là exclusion có phạm vi ở mô hình phân tích của `ApplicationModules`. Nó không di chuyển class trong source code, không thay đổi package của class, không đổi cách Spring component scanning tìm bean, không thay đổi API runtime và không sửa cách các module gọi nhau. Nếu class bị loại vẫn được ứng dụng sử dụng khi chạy, quan hệ sử dụng đó vẫn tồn tại trong chương trình.

Do đó, exclusion có thể làm giảm số type và dependency mà Spring Modulith xem xét. Nó không thể chứng minh rằng phần mã bị bỏ qua đã tuân thủ kiến trúc. Một kiểm tra thành công sau khi loại package chỉ chứng minh phần còn lại của mô hình vượt qua các quy tắc đang được áp dụng.

## Viết pattern package đúng phạm vi

Spring Modulith sử dụng matcher package của ArchUnit cho các pattern trong `resideInAPackage(…)`. Một vài pattern thường gặp:

| Pattern | Phạm vi khớp | Ví dụ |
|---|---|---|
| `com.example.db` | Chỉ package `com.example.db` | `com.example.db.DatabaseConfig` |
| `com.example.db..` | Package `com.example.db` và mọi package con | `com.example.db.DatabaseConfig`, `com.example.db.internal.ConnectionFactory` |
| `..example..` | Package có segment `example` ở bất kỳ vị trí nào trong tên package | `a.example`, `a.example.b`, `a.b.example.c.d` |

Pattern `com.example.db` không tự động bao gồm `com.example.db.internal`. Nếu chủ đích là loại toàn bộ cây package, cần dùng `com.example.db..`. Ngược lại, pattern rộng như `..db..` có thể loại package `db` ở nhiều nhánh không liên quan. Hãy chọn pattern hẹp nhất đáp ứng mục đích và kiểm tra các package lân cận có tên gần giống.

Ví dụ, nếu chỉ mã được sinh tự động trong `com.acme.generated` nằm ngoài phạm vi kiểm tra module, có thể cấu hình:

```java
ApplicationModules modules = ApplicationModules.of(
    Application.class,
    JavaClass.Predicates.resideInAPackage("com.acme.generated..")
);

modules.verify();
```

Trong ví dụ này, cả `com.acme.generated` và các package con của nó đều bị bỏ qua. Các package như `com.acme.orders` hoặc `com.acme.generatedSupport` không khớp pattern trên.

## Vì sao exclusion không sửa được boundary?

Boundary mô tả phần mã thuộc về một module, phần API module công bố và những dependency module khác được phép tạo. Exclusion chỉ điều chỉnh tập type được đưa vào một lần phân tích. Hai khái niệm này có mục đích khác nhau.

Giả sử ứng dụng có cấu trúc:

```text
com.acme
├── orders
│   ├── api
│   │   └── OrderLookup.java
│   └── internal
│       └── OrderRepositoryAdapter.java
└── shipping
    └── ShippingService.java
```

`ShippingService` cần thông tin đơn hàng nhưng lại gọi trực tiếp `OrderRepositoryAdapter`, một type nội bộ của module `orders`. Spring Modulith phát hiện dependency đi vào phần nội bộ và báo vi phạm.

Nếu loại `com.acme.orders.internal..` khỏi inspection, một phần type liên quan đến vi phạm có thể biến mất khỏi mô hình. Nhưng `ShippingService` vẫn gọi `OrderRepositoryAdapter`; package vẫn nằm trong cấu trúc cũ; module `orders` vẫn chưa công bố hợp đồng mà `shipping` cần. Khi kiểm tra tiếp, nhóm có thể không còn nhìn thấy đầy đủ dependency cần sửa.

Boundary đúng cần được thiết kế theo nhu cầu nghiệp vụ. Chẳng hạn, module `orders` có thể công bố `OrderLookup` trong named interface `api`, triển khai nó bên trong module và để `shipping` phụ thuộc vào hợp đồng đó. Dependency khi ấy đi qua API công khai thay vì truy cập adapter nội bộ.

## Khi nào nên sửa cấu trúc thay vì thêm exclusion?

Hãy sửa boundary khi package bị báo lỗi là một phần của ứng dụng và có trách nhiệm kiến trúc rõ ràng.

**Package nghiệp vụ nằm sai module.** Nếu class xử lý đơn hàng nằm trong package `com.acme.shared` chỉ vì nhiều module đang dùng nó, hãy xác định module nào thực sự sở hữu hành vi đó. Di chuyển hành vi về module sở hữu và công bố API cần thiết. Nếu đó là capability dùng chung có vòng đời độc lập, hãy xem xét một module dùng chung với named interface được xác định rõ.

**Module truy cập implementation của module khác.** Nếu module gọi class trong `internal`, `persistence`, `adapter` hoặc package tương tự của module khác, hãy công bố một named interface phù hợp hoặc thiết kế lại lời gọi qua API nghiệp vụ. Exclusion package implementation chỉ che bớt dấu vết của dependency.

**Package `common`, `util` hoặc `shared` đang chứa nhiều trách nhiệm.** Tên package chung không tự tạo ra một boundary có ý nghĩa. Hãy tách các type theo trách nhiệm và quyền sở hữu. Một tiện ích thuần túy có thể thuộc module dùng chung; logic nghiệp vụ cần nằm trong module sở hữu nó.

**Package gốc hoặc chiến lược phát hiện module không đúng.** Nếu Spring Modulith đang xem một package gom nhóm kỹ thuật là module, hãy xem lại package của lớp ứng dụng, cấu trúc package, `@Modulithic`, `additionalPackages` hoặc detection strategy. Exclusion type không phải cách sửa một quy tắc discovery sai.

**Quy tắc phụ thuộc không diễn đạt đúng ý định.** Nếu một dependency hợp lệ nhưng bị từ chối, hãy xem lại named interface, allowed dependencies và cách mô hình hóa module. Không loại package của bên cung cấp API chỉ để làm cho kiểm tra qua.

## Khi nào exclusion là lựa chọn hợp lý?

Exclusion phù hợp khi có bằng chứng rõ ràng rằng một nhóm type không thuộc phạm vi kiến trúc mà `ApplicationModules` đang chịu trách nhiệm xác minh, và việc bỏ qua chúng không làm mất kiểm tra đối với dependency nghiệp vụ cần quản lý.

Một số trường hợp có thể cân nhắc:

- Mã được sinh tự động từ schema hoặc công cụ bên ngoài, được đặt dưới package riêng và không đại diện cho module nghiệp vụ.
- Một thư viện hoặc phần mã tích hợp cũ nằm bên trong package root do giới hạn lịch sử, trong khi nhóm đã xác định rõ phạm vi chuyển đổi kiến trúc.
- Một tập type kỹ thuật chỉ phục vụ hạ tầng kiểm thử hoặc công cụ nội bộ và không phải đối tượng của mô hình module ứng dụng.

Ngay cả trong các trường hợp đó, cần kiểm tra xem type bị loại có phải là API mà module khác đang dùng hay không. Nếu một type được sinh tự động trở thành hợp đồng giao tiếp giữa các module, việc loại nó có thể che giấu thay đổi tương thích hoặc dependency không mong muốn. Khi đó, hãy xác định cách kiểm tra hợp đồng riêng thay vì bỏ qua toàn bộ package.

Nếu exclusion chỉ được dùng trong giai đoạn chuyển đổi, hãy ghi rõ lý do, người chịu trách nhiệm, phạm vi package và điều kiện xóa exclusion. Một exclusion tạm thời không có thời hạn hoặc tiêu chí hoàn tất rất dễ trở thành vùng mù lâu dài.

## Ví dụ kiểm thử với exclusion có chủ đích

Giả sử `com.acme.generated` chứa các class được sinh tự động từ schema bên ngoài. Nhóm quyết định loại đúng package này khỏi mô hình module, đồng thời vẫn muốn bảo đảm các module nghiệp vụ được kiểm tra bình thường.

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.tngtech.archunit.core.domain.JavaClass;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    private final ApplicationModules modules = ApplicationModules.of(
        Application.class,
        JavaClass.Predicates.resideInAPackage("com.acme.generated..")
    );

    @Test
    void verifiesModuleStructure() {
        modules.verify();
    }

    @Test
    void excludesOnlyGeneratedTypesFromTheModuleModel() {
        assertFalse(modules.contains(GeneratedSchema.class));
        assertTrue(modules.contains(OrderService.class));
    }
}
```

`GeneratedSchema` đại diện cho một class nằm trong package bị loại; `OrderService` đại diện cho một class nghiệp vụ phải tiếp tục nằm trong mô hình. Hãy thay chúng bằng type thực tế của ứng dụng. Kiểm tra cả hai phía giúp phát hiện trường hợp predicate quá rộng hoặc cấu hình vô tình loại cả mã nghiệp vụ.

Kiểm thử trên xác nhận phạm vi của mô hình sau exclusion. Nó không xác nhận các class được loại đã tuân thủ dependency rule. Nếu những class đó vẫn gọi hoặc được gọi bởi module nghiệp vụ, nhóm cần một kiểm tra phù hợp khác cho hợp đồng hoặc dependency đó.

## Quy trình xử lý một vi phạm trước khi quyết định exclusion

Khi `ApplicationModules.verify()` báo một dependency hoặc type không mong muốn, hãy đi theo trình tự sau:

1. **Xác định type và package cụ thể.** Đọc vị trí source, trách nhiệm nghiệp vụ và các module đang sử dụng type đó.
2. **Xác định package có thuộc ứng dụng không.** Nếu thuộc một capability nghiệp vụ, nó cần có module sở hữu và quy tắc công khai rõ ràng.
3. **Phân loại nguyên nhân.** Có thể package nằm sai module, caller truy cập implementation, package root sai hoặc type thực sự nằm ngoài phạm vi kiến trúc.
4. **Chọn cách sửa boundary.** Di chuyển type, tách module, công bố named interface, khai báo allowed dependency hoặc điều chỉnh discovery khi mô hình hiện tại chưa đúng.
5. **Chỉ dùng exclusion khi có lý do về phạm vi inspection.** Viết predicate hẹp, ghi rõ tác động và kiểm tra type quan trọng vẫn còn trong mô hình.
6. **Đưa quyết định vào review.** Người review cần biết package nào bị bỏ qua, vì sao nó không thuộc phạm vi kiểm tra và nhóm kiểm soát dependency liên quan bằng cách nào.

Quy trình này giữ cho mỗi vi phạm dẫn đến một quyết định kiến trúc có thể giải thích. Nếu sau khi xem xét, nhóm không thể trả lời vì sao package nằm ngoài phạm vi inspection, chưa nên thêm exclusion.

## Những lỗi thường gặp

| Cách làm | Rủi ro | Cách xử lý |
|---|---|---|
| Loại cả `com.acme..` để làm kiểm tra nhanh chóng thành công | Gần như toàn bộ mô hình ứng dụng có thể bị bỏ qua | Thu hẹp predicate đến package thực sự ngoài phạm vi |
| Dùng `com.acme.db` nhưng nghĩ rằng đã loại cả `db.internal` | Package con vẫn có thể xuất hiện trong inspection | Dùng `com.acme.db..` nếu thực sự muốn bao gồm package con |
| Loại `shared` vì nhiều module đang phụ thuộc vào nó | Che khuất vấn đề sở hữu và dependency chung | Xác định module sở hữu hoặc tạo shared module với API rõ ràng |
| Loại package `internal` của module để bỏ qua lỗi truy cập implementation | Mất tín hiệu về dependency đi vào nội bộ module | Đưa dependency qua named interface hoặc API công khai |
| Thêm exclusion mà không ghi lý do và điều kiện gỡ bỏ | Vùng bị bỏ qua tồn tại vô thời hạn | Ghi owner, phạm vi và tiêu chí kết thúc |
| Chỉ kiểm tra `verify()` sau khi thêm exclusion | Không biết predicate có loại nhầm type nghiệp vụ hay không | Kiểm tra cả type bị loại và type phải còn trong mô hình |

## Checklist review

Trước khi chấp nhận một exclusion, hãy xác nhận:

- [ ] Có thể nêu rõ vì sao package hoặc class nằm ngoài phạm vi inspection.
- [ ] Predicate chỉ khớp đúng package cần bỏ qua.
- [ ] Đã kiểm tra semantics của pattern với package con và package có tên gần giống.
- [ ] Các dependency nghiệp vụ quan trọng vẫn được kiểm tra.
- [ ] Các type nghiệp vụ dự kiến vẫn tồn tại trong `ApplicationModules`.
- [ ] Nếu exclusion tạm thời, đã ghi owner và điều kiện gỡ bỏ.
- [ ] Quyết định đã được ghi lại trong review hoặc tài liệu kiến trúc.

## Bài tập tự đánh giá

Một ứng dụng có hai module `orders` và `shipping`. `ShippingService` gọi trực tiếp `orders.internal.OrderRepositoryAdapter`. Kiểm tra kiến trúc báo lỗi. Nhóm đề xuất loại toàn bộ `com.acme.orders.internal..` khỏi `ApplicationModules` để pipeline xanh trở lại.

Hãy trả lời:

1. Exclusion làm thay đổi điều gì trong mô hình inspection và điều gì vẫn không thay đổi trong source code?
2. Vì sao cách làm này có thể khiến nhóm mất tín hiệu về dependency sai?
3. `orders` nên công bố hợp đồng nào để `shipping` lấy thông tin đơn hàng?
4. Nếu package `com.acme.generated` thực sự nằm ngoài phạm vi kiểm tra, pattern nào phù hợp để loại cả package và package con?
5. Bạn sẽ viết những assertion nào để bảo đảm exclusion không loại nhầm class nghiệp vụ?

Một hướng giải quyết phù hợp là giữ `OrderRepositoryAdapter` bên trong `orders`, công bố một abstraction nghiệp vụ như `OrderLookup` qua named interface và để `ShippingService` phụ thuộc vào abstraction đó. Nếu `com.acme.generated` là mã nằm ngoài phạm vi inspection, có thể dùng `resideInAPackage("com.acme.generated..")` và kiểm tra một type được sinh ra bị loại trong khi type nghiệp vụ vẫn được giữ lại.

## Kết luận

Exclusion là bộ lọc cho mô hình inspection của `ApplicationModules`. Nó hữu ích khi cần bỏ qua một tập type thực sự nằm ngoài phạm vi kiến trúc đang kiểm tra. Với package thuộc ứng dụng và có trách nhiệm nghiệp vụ, hãy sửa quyền sở hữu, module boundary, named interface hoặc dependency rule. Một kiểm tra kiến trúc có giá trị khi nó tiếp tục nhìn thấy những quan hệ mà nhóm cần quản lý.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals, Excluding Packages](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [ArchUnit API — `JavaClass.Predicates`](https://www.javadoc.io/doc/com.tngtech.archunit/archunit/latest/com/tngtech/archunit/core/domain/JavaClass.Predicates.html)

# Rủi ro che vi phạm bằng exclusion quá rộng

Spring Modulith cho phép loại một số Java class hoặc package khỏi quá trình kiểm tra cấu trúc Application Module. Tính năng này hữu ích khi một phần mã nguồn thực sự nằm ngoài phạm vi kiến trúc cần kiểm tra. Tuy nhiên, nếu dùng matcher quá rộng, các class nghiệp vụ hoặc package nội bộ cũng có thể biến mất khỏi mô hình phân tích. Khi đó, **ApplicationModules.verify() có thể thành công vì không còn nhìn thấy phần gây vi phạm**, chứ không phải vì dependency đã được sửa đúng.

Bài học này giải thích cơ chế exclusion, cách đọc cú pháp package matcher, các rủi ro khi loại quá nhiều mã nguồn và cách giữ phạm vi loại trừ nhỏ, có thể kiểm chứng.

## 1. Exclusion tác động đến quá trình inspection như thế nào?

Thông thường, ta tạo mô hình và kiểm tra cấu trúc module như sau:

~~~java
ApplicationModules.of(ShopApplication.class).verify();
~~~

Nếu cần bỏ qua một số class hoặc package cụ thể, Spring Modulith cho phép truyền thêm một predicate vào overload của **ApplicationModules.of(…)**:

~~~java
import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(
    ShopApplication.class,
    JavaClass.Predicates.resideInAPackage("com.acme.shop.legacybridge")
);

modules.verify();
~~~

Tham số thứ hai là một **DescribedPredicate** trên **JavaClass**. Predicate xác định các type hoặc package cần bỏ qua trong mô hình kiểm tra. Spring Modulith dùng mô hình đã lọc để phân tích module và chạy verification.

Exclusion không xóa file, không sửa import, không thay đổi classpath và cũng không thay đổi component scan của Spring Boot. Nó chỉ tác động đến những gì được đưa vào lần inspection được tạo bởi lời gọi **ApplicationModules.of(…)** đó.

Vì vậy, một bài test dùng exclusion đang trả lời câu hỏi: “Phần mã nguồn còn lại sau khi áp dụng bộ lọc có tuân thủ quy tắc module không?”. Nó không còn trả lời đầy đủ câu hỏi: “Toàn bộ mã nguồn ứng dụng có tuân thủ quy tắc module không?”.

## 2. Hiểu đúng cú pháp package matcher

Spring Modulith sử dụng matcher package của ArchUnit. Một vài mẫu quan trọng:

| Mẫu | Phạm vi khớp |
|---|---|
| **com.acme.shop.legacybridge** | Chỉ package chính xác đó |
| **com.acme.shop.legacybridge..** | Package đó và mọi subpackage |
| **..legacybridge..** | Segment **legacybridge** ở bất kỳ vị trí nào trong tên package |
| **com.acme.shop..** | Toàn bộ package dưới application root |

Ví dụ, package matcher:

~~~java
JavaClass.Predicates.resideInAPackage("com.acme.shop.legacybridge")
~~~

nhắm tới package chính xác. Nếu cần bỏ qua cả các package con như **legacybridge.http** hoặc **legacybridge.persistence**, dùng:

~~~java
JavaClass.Predicates.resideInAPackage("com.acme.shop.legacybridge..")
~~~

Hai dấu chấm ở cuối biểu diễn không hoặc nhiều cấp package tiếp theo. Vì vậy, matcher này bao gồm package gốc **legacybridge** và các subpackage bên dưới.

Mẫu **..legacybridge..** rộng hơn đáng kể. Nó có thể khớp **com.acme.shop.legacybridge**, nhưng cũng có thể khớp **com.acme.shop.orders.legacybridge** hoặc package **legacybridge** nằm trong một nhánh khác. Hãy dùng mẫu này chỉ khi thật sự muốn loại mọi package có segment đó ở bất kỳ vị trí nào.

## 3. Vì sao exclusion quá rộng che được vi phạm?

Spring Modulith phân tích các type và quan hệ tham chiếu giữa chúng để xây dựng module model. Khi predicate loại một nhóm type khỏi inspection, các type đó không còn tham gia đầy đủ vào mô hình được kiểm tra.

Điều này có thể che khuất nhiều dạng vi phạm:

- Một module đang import repository hoặc entity thuộc package nội bộ của module khác.
- Một module có outgoing dependency không nằm trong danh sách **allowedDependencies**.
- Một cạnh trong dependency graph bị mất vì class tạo ra tham chiếu đã bị loại.
- Một module chỉ còn một phần type trong mô hình, khiến dependency graph không phản ánh đủ cấu trúc thật.

Ví dụ, ứng dụng có cấu trúc:

~~~text
com.acme.shop
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
├── inventory
│   └── InventoryService.java
└── payments
    └── PaymentService.java
~~~

Nếu **InventoryService** import trực tiếp **orders.internal.OrderRepository**, đó là tham chiếu vào package nội bộ của module **orders**. Nhưng nếu bài test loại toàn bộ package có tên **internal**, các type liên quan có thể không còn được kiểm tra như trước. Kết quả PASS khi đó không chứng minh rằng **inventory** đã chuyển sang dùng API công khai.

Rủi ro còn lớn hơn nếu loại package của consumer. Ví dụ, loại toàn bộ **inventory..** có thể làm biến mất chính class đang tạo ra tham chiếu trái phép. Verification không thể báo vi phạm từ một class đã bị loại khỏi mô hình.

## 4. Ví dụ exclusion rộng và hệ quả

Giả sử đội ngũ muốn tạm bỏ qua một adapter legacy trong module **orders**. Một cách viết nguy hiểm là:

~~~java
ApplicationModules modules = ApplicationModules.of(
    ShopApplication.class,
    JavaClass.Predicates.resideInAPackage("..internal..")
);

modules.verify();
~~~

Matcher **..internal..** không chỉ bỏ qua adapter legacy. Nó có thể loại package internal của nhiều module:

~~~text
orders.internal
inventory.internal
payments.internal
customers.internal
~~~

Đây thường là nơi chứa repository, entity, adapter và các class mà quy tắc module cần bảo vệ khỏi truy cập từ bên ngoài. Loại toàn bộ các package đó có thể làm mất bằng chứng của những import trái phép mà verification cần phát hiện.

Một matcher còn nguy hiểm hơn:

~~~java
JavaClass.Predicates.resideInAPackage("com.acme.shop..")
~~~

Mẫu này có thể loại gần như toàn bộ mã nguồn dưới application root. Test lúc đó không còn kiểm tra kiến trúc của ứng dụng theo ý nghĩa ban đầu.

## 5. Dùng exclusion hẹp cho một package có chủ đích

Nếu một package thực sự cần được bỏ qua tạm thời, hãy chỉ rõ package đó bằng tên đầy đủ:

~~~java
import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @org.junit.jupiter.api.Test
    void verifiesModulesIgnoringOnlyLegacyBridge() {
        ApplicationModules modules = ApplicationModules.of(
            ShopApplication.class,
            JavaClass.Predicates.resideInAPackage(
                "com.acme.shop.legacybridge.."
            )
        );

        modules.verify();
    }
}
~~~

Trong ví dụ, chỉ nhánh **com.acme.shop.legacybridge** và các subpackage của nó bị loại. Các module nghiệp vụ như **orders**, **inventory** và **payments** vẫn nằm trong mô hình kiểm tra.

Chỉ dùng phạm vi này nếu **legacybridge** thực sự nằm ngoài ranh giới module cần bảo vệ và việc bỏ qua đã được chấp nhận có chủ đích. Nếu package chứa logic nghiệp vụ hoặc là một module mà các module khác đang phụ thuộc, hãy thiết kế lại ranh giới hoặc API thay vì loại nó khỏi inspection.

## 6. Phân biệt exclusion với các cơ chế cấu hình khác

Exclusion thường bị nhầm với module detection, Named Interface hoặc allowed dependencies. Các cơ chế này có mục đích khác nhau:

| Cơ chế | Nó thay đổi điều gì? | Câu hỏi cần trả lời |
|---|---|---|
| Exclusion trong **ApplicationModules.of(…)** | Type/package nào được đưa vào inspection | Có phần mã nguồn nào thật sự nằm ngoài phạm vi kiểm tra không? |
| **ApplicationModuleDetectionStrategy** | Package nào được chọn làm base package của module | Package nào là một Application Module? |
| **@NamedInterface** | Package con nào được công bố như API bổ sung | Module khác được phép dùng hợp đồng nào? |
| **allowedDependencies** | Module tiêu thụ được phép phụ thuộc module/interface nào | Consumer được phép phụ thuộc vào ai? |
| **Type.OPEN** | Mức độ expose type nội bộ của module | Có cần nới lỏng ranh giới cho module legacy không? |

Nếu một package kỹ thuật bị nhận diện nhầm thành module, hãy xem xét package layout hoặc detection strategy. Nếu một consumer cần dùng một hợp đồng, hãy công bố API hoặc Named Interface. Nếu dependency không được phép, hãy sửa hướng phụ thuộc hoặc allowlist có chủ đích. Exclusion không nên được dùng để thay thế các quyết định thiết kế đó.

## 7. Kiểm tra những type quan trọng vẫn còn trong mô hình

Một cách phòng ngừa là viết assertion cho các type nghiệp vụ phải luôn được kiểm tra. Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.acme.shop.inventory.InventoryService;
import com.acme.shop.orders.internal.Order;
import com.acme.shop.orders.internal.OrderRepository;
import com.tngtech.archunit.core.domain.JavaClass;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void keepsBusinessTypesInsideTheInspection() {
        ApplicationModules modules = ApplicationModules.of(
            ShopApplication.class,
            JavaClass.Predicates.resideInAPackage(
                "com.acme.shop.legacybridge.."
            )
        );

        assertThat(modules.contains(InventoryService.class)).isTrue();
        assertThat(modules.contains(Order.class)).isTrue();
        assertThat(modules.contains(OrderRepository.class)).isTrue();

        modules.verify();
    }
}
~~~

Các assertion này xác nhận những type quan trọng vẫn được giữ trong mô hình. Nếu một thay đổi matcher vô tình mở rộng phạm vi loại trừ sang **orders** hoặc **inventory**, test sẽ thất bại trước khi kết quả verification bị hiểu nhầm là PASS.

Trong một bài test thực tế, hãy chọn một vài type đại diện cho từng module quan trọng và các package nội bộ mà kiến trúc cần bảo vệ. Không cần liệt kê mọi class, nhưng phải có đủ điểm kiểm soát để phát hiện bộ lọc đã loại nhầm module.

## 8. Đặt tên và ghi lý do cho exclusion

Một exclusion hợp lệ vẫn cần được giải thích. Hãy ghi rõ:

- Package hoặc nhóm class nào bị loại.
- Vì sao chúng không thuộc phạm vi kiến trúc đang kiểm tra.
- Ai sở hữu phần mã nguồn đó.
- Exclusion là ngoại lệ lâu dài hay biện pháp chuyển tiếp.
- Điều kiện nào cho phép xóa exclusion trong tương lai.

Ví dụ, một package adapter đang được di chuyển từ ứng dụng cũ có thể được bỏ qua tạm thời trong một test kiến trúc. Khi adapter được chuyển vào module sở hữu hoặc thay bằng API công khai, hãy xóa predicate và để verification kiểm tra lại phần mã nguồn đó.

Không nên đặt matcher quá rộng chỉ vì test đang thất bại. Trước khi thêm exclusion, đọc type và dependency bị báo lỗi để xác định vi phạm thật, rồi chọn cách sửa tương ứng.

## 9. Quy trình xử lý khi verification báo vi phạm

Khi **ApplicationModules.verify()** thất bại, hãy đi theo thứ tự:

1. Đọc đầy đủ package và type được nêu trong thông báo vi phạm.
2. Xác định module sở hữu type được tham chiếu và module đang tạo tham chiếu.
3. Kiểm tra type có thuộc API package hoặc Named Interface được công bố hay không.
4. Kiểm tra module tiêu thụ có khai báo **allowedDependencies** phù hợp hay không.
5. Nếu type thực sự nằm ngoài mô hình kiến trúc, xác định một package cụ thể để loại và ghi rõ lý do.
6. Sau khi thêm exclusion, kiểm tra các type nghiệp vụ quan trọng vẫn nằm trong mô hình.
7. Chạy lại verification và review matcher để chắc chắn không loại nhầm module khác.

Nếu lỗi đến từ import vào package nội bộ, giải pháp bền vững thường là chuyển consumer sang API công khai. Nếu lỗi đến từ một dependency không được phép, hãy xem lại hợp đồng và danh sách phụ thuộc. Chỉ loại khỏi inspection khi type đó thật sự nằm ngoài phạm vi kiến trúc cần bảo vệ.

## 10. Checklist cho một exclusion an toàn

- [ ] Predicate nhắm tới package hoặc class cụ thể bằng tên đầy đủ.
- [ ] Không dùng wildcard toàn cục như **..internal..** hoặc **..common..** nếu chưa chứng minh được phạm vi cần loại.
- [ ] Không loại module nghiệp vụ hoặc consumer có thể tạo ra vi phạm.
- [ ] Các type quan trọng vẫn được xác nhận bằng **modules.contains(…)**.
- [ ] Lý do và chủ sở hữu của exclusion được ghi lại.
- [ ] Có kế hoạch xem xét và gỡ exclusion nếu đây là ngoại lệ chuyển tiếp.
- [ ] Verification vẫn chạy trên phần lớn mô hình module mà đội ngũ muốn bảo vệ.

Một exclusion tốt có phạm vi nhỏ, lý do rõ và có thể được gỡ bỏ. Một exclusion quá rộng làm giảm giá trị của kiểm chứng vì nó có thể loại chính các class và dependency mà kiến trúc cần quan sát. Hãy giữ mô hình inspection gần với mã nguồn thực tế nhất có thể để kết quả verification phản ánh đúng chất lượng ranh giới module.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals, Excluding Packages](https://docs.spring.io/spring-modulith/reference/fundamentals.html): cách truyền predicate vào **ApplicationModules.of(…)** và ví dụ phạm vi package.
- [Spring Modulith Javadoc — ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html): overload **of(Class, DescribedPredicate)** và mô hình inspection.
- [ArchUnit — PackageMatcher](https://github.com/TNG/ArchUnit/blob/main/archunit/src/main/java/com/tngtech/archunit/core/domain/PackageMatcher.java): cú pháp **\***, **..** và cách matcher package hoạt động.

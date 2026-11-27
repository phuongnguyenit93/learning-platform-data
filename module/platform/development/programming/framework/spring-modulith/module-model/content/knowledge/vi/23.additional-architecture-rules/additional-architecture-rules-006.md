# Đọc lỗi do rule bổ sung gây ra

Ngoài các quy tắc cốt lõi về module graph, API công khai và dependency được phép, một dự án có thể bổ sung các quy tắc kiến trúc riêng. Ví dụ, nhóm có thể yêu cầu mô-đun tuân theo kiến trúc hexagonal, giới hạn package nào được phép gọi package khác hoặc kiểm tra vị trí của các thành phần domain. Những quy tắc bổ sung này thường được biểu diễn bằng ArchUnit và có thể được chạy cùng `ApplicationModules.verify()`.

Khi một rule bổ sung thất bại, thông báo lỗi thường cho biết rule nào bị vi phạm và lớp hoặc thành viên mã nguồn nào tạo ra vi phạm. Đọc đúng thông tin đó giúp xác định lỗi nằm ở thiết kế ứng dụng, phạm vi áp dụng của rule hay chính cách viết rule.

## 1. Phân biệt lỗi cốt lõi và lỗi từ rule bổ sung

`ApplicationModules.verify()` kiểm tra các quy tắc kiến trúc cốt lõi của Spring Modulith, bao gồm:

- Module graph không có chu trình.
- Một mô-đun chỉ truy cập API công khai của mô-đun khác.
- Dependency phải được khai báo trong `allowedDependencies` nếu mô-đun sử dụng allow-list.

Ngoài ra, Spring Modulith có thể chạy các verification bổ sung được cấu hình trong `VerificationOptions`. Một số integration, chẳng hạn jMolecules ArchUnit khi có trên classpath, có thể đóng góp các rule bổ sung. Dự án cũng có thể đăng ký ArchUnit rule riêng.

Hai nhóm lỗi có ý nghĩa khác nhau. Nếu lỗi thuộc quy tắc cốt lõi, hãy kiểm tra module boundary, package API và dependency graph. Nếu lỗi thuộc rule bổ sung, hãy đọc mô tả rule và điều kiện mà rule đang áp dụng. Không nên sửa `allowedDependencies` để xử lý một vi phạm về kiến trúc hexagonal, cũng không nên tắt toàn bộ verification chỉ vì một rule bổ sung đang báo lỗi.

## 2. Một rule bổ sung được chạy cùng ApplicationModules

Ví dụ, nhóm muốn kiểm tra kiến trúc hexagonal bằng jMolecules. Có thể tạo rule và truyền vào `VerificationOptions`:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.jmolecules.archunit.VerificationDepth;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class ModularityTests {

    @Test
    void verifiesModulesAndHexagonalArchitecture() {
        var hexagonalRule = JMoleculesArchitectureRules.ensureHexagonal(
                VerificationDepth.STRICT
        );

        var options = VerificationOptions.defaults()
                .andAdditionalVerifications(hexagonalRule);

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
```

Ví dụ cần dependency jMolecules ArchUnit tương ứng trong test runtime. `andAdditionalVerifications(…)` giữ các verification bổ sung mặc định và thêm rule hexagonal. Nếu dùng `withAdditionalVerifications(…)`, nhóm verification bổ sung mặc định sẽ được thay bằng nhóm được cung cấp. Các quy tắc cốt lõi của Spring Modulith vẫn được thực hiện.

Một dự án cũng có thể tự viết rule ArchUnit. Ví dụ sau yêu cầu các lớp trong `orders` không phụ thuộc trực tiếp vào package triển khai `inventory.internal`:

```java
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

ArchRule ordersMustUseInventoryApi = noClasses()
        .that().resideInAPackage("..orders..")
        .should().dependOnClassesThat()
        .resideInAPackage("..inventory.internal..")
        .because("orders must use the public inventory API");
```

Đăng ký rule trong options:

```java
var options = VerificationOptions.defaults()
        .andAdditionalVerifications(ordersMustUseInventoryApi);

ApplicationModules.of(ShopApplication.class).verify(options);
```

Rule trên bổ sung một chính sách cụ thể cho dự án. Nó không thay thế việc kiểm tra package nội bộ của Spring Modulith; nó giúp diễn đạt rõ một điều kiện kiến trúc mà nhóm muốn kiểm soát.

## 3. Đọc cấu trúc của thông báo vi phạm

Thông báo từ ArchUnit thường có các phần mang ý nghĩa sau. Cách trình bày chính xác có thể khác theo phiên bản và loại rule, nhưng hãy tìm những thành phần tương đương:

| Thành phần | Cần tìm | Cách sử dụng |
|---|---|---|
| Rule description | Tên rule hoặc mệnh đề `should` | Biết điều kiện kiến trúc nào đã thất bại |
| Số lượng vi phạm | Tổng số violation được tìm thấy | Ước lượng phạm vi ảnh hưởng và xác định lỗi lặp lại |
| Source class/member | Lớp, field, constructor hoặc method khởi tạo dependency | Xác định nơi cần bắt đầu điều tra |
| Target class/member | Kiểu hoặc thành viên mà source đang tham chiếu | Xác định package hoặc lớp đích không phù hợp |
| Source location | File và dòng mã nếu được cung cấp | Mở đúng vị trí để kiểm tra import, chữ ký hoặc lời gọi |
| Rule reason | Nội dung mô tả hoặc `because(…)` | Hiểu lý do nhóm đặt ra quy tắc |

Ví dụ minh họa một kết quả có thể có:

```text
Architecture Violation
Rule: orders must use the public inventory API
Violations: 1

Source:
  com.acme.shop.orders.OrderService

Dependency:
  com.acme.shop.orders.OrderService
  -> com.acme.shop.inventory.internal.StockRepository

Reason:
  orders must use the public inventory API
```

Đây là ví dụ rút gọn để minh họa cách đọc, không phải nguyên văn output cố định của ArchUnit. Từ thông tin đó, có thể kết luận lớp `OrderService` tạo dependency tới `StockRepository` trong package nội bộ. Bước tiếp theo là kiểm tra chữ ký constructor, import và luồng nghiệp vụ để chuyển sang API công khai phù hợp.

## 4. Lần từ rule tới nguyên nhân trong mã nguồn

Khi đọc một lỗi rule bổ sung, hãy điều tra theo thứ tự:

1. **Đọc tên và điều kiện của rule.** Xác định rule đang kiểm tra package, annotation, stereotype, layer hay quan hệ dependency nào.
2. **Xác định phạm vi đầu vào.** Kiểm tra rule áp dụng cho toàn bộ application classes, một package hay một nhóm lớp được chọn bằng predicate.
3. **Tìm source và target.** Xác định lớp nguồn tạo dependency và lớp đích bị tham chiếu. Đọc cả hai phía để hiểu ý nghĩa nghiệp vụ.
4. **Lần về quan hệ cụ thể.** Kiểm tra import, field, constructor parameter, method parameter, return type, annotation hoặc lời gọi method tạo ra vi phạm.
5. **So sánh với ý định kiến trúc.** Xác định mã nguồn đang sai hay rule đang mô tả sai chính sách mà nhóm muốn áp dụng.
6. **Chọn cách sửa nhỏ nhất.** Sửa dependency, di chuyển abstraction, thay đổi package hoặc thu hẹp rule nếu phạm vi hiện tại không đúng.
7. **Chạy lại verification.** Xác nhận rule vừa sửa đã qua và các quy tắc cốt lõi của Spring Modulith vẫn được thực hiện.

Đừng chỉ nhìn vào dòng import đầu tiên. Một dependency có thể xuất hiện qua kiểu generic, kiểu trả về, kiểu tham số, annotation hoặc thành viên được gọi. Hãy đọc đúng quan hệ mà ArchUnit chỉ ra.

## 5. Ví dụ: lỗi do quy tắc layer hoặc hexagonal architecture

Giả sử nhóm tổ chức mã nguồn theo các layer `domain`, `application` và `infrastructure`. Theo thiết kế, domain không được phụ thuộc vào infrastructure. Một rule bổ sung có thể kiểm tra điều kiện này:

```java
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

ArchRule domainMustNotDependOnInfrastructure = noClasses()
        .that().resideInAPackage("..domain..")
        .should().dependOnClassesThat()
        .resideInAPackage("..infrastructure..");
```

Nếu thông báo cho biết `Order` trong package domain phụ thuộc vào `JpaOrderRepository` trong infrastructure, hãy xem lại abstraction. Domain có thể khai báo một repository port mà nó sở hữu; adapter JPA ở infrastructure triển khai port đó. Khi đó, mã domain chỉ phụ thuộc vào abstraction thuộc domain.

```java
package com.acme.shop.orders.domain;

import java.util.Optional;
import java.util.UUID;

public interface OrderRepository {

    Optional<Order> findById(UUID id);
}
```

Adapter nằm ở infrastructure:

```java
package com.acme.shop.orders.infrastructure;

import java.util.Optional;
import java.util.UUID;

import com.acme.shop.orders.domain.Order;
import com.acme.shop.orders.domain.OrderRepository;
import org.springframework.stereotype.Repository;

@Repository
class JpaOrderRepository implements OrderRepository {

    @Override
    public Optional<Order> findById(UUID id) {
        // Dùng Spring Data repository và chuyển đổi entity sang domain model.
        return Optional.empty();
    }
}
```

Ví dụ adapter chỉ phác thảo vị trí của implementation; trong ứng dụng thực tế cần khai báo dependency Spring Data repository và mapping phù hợp. Điều quan trọng là domain không import kiểu hoặc repository implementation thuộc infrastructure.

## 6. Phân biệt lỗi thật và rule áp dụng quá rộng

Không phải mọi violation đều có nghĩa mã nguồn cần thay đổi. Một rule có thể áp dụng nhầm vào lớp được sinh tự động, lớp cấu hình hoặc package nằm ngoài phạm vi mà nhóm muốn kiểm tra. Trước khi miễn trừ, hãy xác nhận:

- Predicate chọn lớp nguồn có đúng package và đúng loại lớp không?
- Package pattern có dùng `..` khiến phạm vi match rộng hơn dự kiến không?
- Rule có vô tình áp dụng vào generated code hoặc test fixture không?
- Một abstraction có thực sự thuộc layer khác hay chỉ được đặt sai package?
- Rule có thể diễn đạt rõ hơn bằng annotation hoặc naming convention ổn định không?

Nếu rule áp dụng quá rộng, hãy sửa predicate hoặc phạm vi của rule. Nếu một lớp kỹ thuật thật sự nằm ngoài inspection, có thể loại trừ có chủ đích với phạm vi hẹp. Không thêm exclusion rộng để che một vi phạm do code nghiệp vụ gây ra.

## 7. Xử lý nhiều vi phạm cùng một rule

Một rule có thể báo nhiều dependency vi phạm cùng lúc. Ví dụ, nhiều service trong `orders` đều tham chiếu repository nội bộ của `inventory`. Khi đó, hãy nhóm các vi phạm theo source package, target package hoặc loại quan hệ:

| Nhóm vi phạm | Hướng xử lý |
|---|---|
| Nhiều lớp cùng truy cập một repository nội bộ | Thiết kế API hoặc Named Interface phù hợp để consumer sử dụng |
| Nhiều lớp domain phụ thuộc vào framework infrastructure | Đưa abstraction về domain và để adapter triển khai |
| Chỉ một nhóm generated class bị báo lỗi | Kiểm tra phạm vi rule và cấu hình loại trừ hẹp nếu có lý do |
| Nhiều package vi phạm cùng một quy ước | Sửa theo một pattern thống nhất, sau đó chạy lại rule |

Sửa theo nhóm giúp xử lý nguyên nhân chung. Tuy nhiên, hãy giữ danh sách vi phạm cụ thể để chắc chắn không bỏ sót một dependency có ý nghĩa khác với các trường hợp còn lại.

## 8. Khi nào nên điều chỉnh rule hoặc VerificationOptions?

Hãy điều chỉnh mã nguồn khi rule mô tả đúng kiến trúc và dependency thực sự vi phạm. Hãy điều chỉnh rule khi điều kiện match hoặc phạm vi áp dụng không còn phản ánh ý định của nhóm. Chỉ thay đổi nhóm verification bổ sung khi chính sách kiểm tra đã thay đổi và có lý do rõ ràng.

Spring Modulith cung cấp các phương thức trong `VerificationOptions` để quản lý verification bổ sung:

| Phương thức | Tác dụng | Khi dùng |
|---|---|---|
| `andAdditionalVerifications(…)` | Giữ nhóm bổ sung hiện có và thêm rule | Khi mở rộng chính sách kiến trúc |
| `withAdditionalVerifications(…)` | Thay nhóm bổ sung hiện có bằng nhóm mới | Khi muốn thay thế tập rule bổ sung |
| `withoutAdditionalVerifications()` | Tắt nhóm verification bổ sung mặc định | Khi không muốn chạy nhóm bổ sung đó; các quy tắc cốt lõi Modulith vẫn chạy |

Nếu cần miễn trừ một vi phạm đã biết trong giai đoạn chuyển tiếp, có thể dùng `detectViolations()` để lấy danh sách, lọc theo điều kiện cụ thể và gọi `throwIfPresent()` với những vi phạm còn lại. Mỗi ngoại lệ nên có người phụ trách, lý do và thời hạn xóa bỏ. Không lọc theo chuỗi thông báo chung chung hoặc loại bỏ toàn bộ vi phạm chỉ để CI chuyển xanh.

## 9. Quy trình xử lý lỗi trong CI

Khi CI thất bại do rule bổ sung, hãy lưu lại log đầy đủ và xử lý theo các bước:

1. Xác định test gọi `ApplicationModules.verify()` và `VerificationOptions` đang dùng.
2. Phân biệt lỗi cốt lõi của Spring Modulith với lỗi từ ArchUnit hoặc integration bổ sung.
3. Đọc mô tả rule, source class, target class và vị trí mã nguồn.
4. Phân loại lỗi thành vi phạm thiết kế, sai phạm vi rule hoặc ngoại lệ đã được phê duyệt.
5. Sửa code hoặc rule theo đúng nguyên nhân; ghi rõ lý do nếu phải thêm ngoại lệ tạm thời.
6. Chạy lại architecture test và kiểm tra log không còn vi phạm ngoài dự kiến.

Không nên bỏ architecture test khỏi pipeline chỉ vì rule bổ sung báo lỗi. Một rule tốt giúp phát hiện sớm sự lệch khỏi kiến trúc đã thống nhất; log của nó là thông tin để sửa thiết kế hoặc tinh chỉnh chính sách một cách có kiểm soát.

## 10. Bài tập tự kiểm tra

Với rule `orders must use the public inventory API`, hãy đọc các trường hợp sau:

| Dependency trong mã nguồn | Kết quả theo rule | Cách xử lý |
|---|---|---|
| `OrderService` tham chiếu `inventory.Inventory` trong package API | Hợp lệ | Giữ dependency qua public API |
| `OrderService` tham chiếu `inventory.internal.StockRepository` | Vi phạm | Dùng API công khai hoặc Named Interface phù hợp |
| Một generated class trong package `orders.generated` bị rule chọn | Cần xem lại phạm vi | Điều chỉnh predicate nếu generated code nằm ngoài chính sách |
| Domain gọi trực tiếp `JpaOrderRepository` | Vi phạm layer | Đưa repository port về domain và để adapter triển khai |

Hãy thử thêm một ArchUnit rule vào `VerificationOptions`, cố ý tạo một dependency vi phạm trong nhánh thử nghiệm và chạy architecture test. Đọc rule description, source, target và vị trí mã nguồn trong output. Sau đó sửa dependency hoặc phạm vi rule, chạy lại test và xác nhận các quy tắc cốt lõi của Spring Modulith vẫn được kiểm tra.

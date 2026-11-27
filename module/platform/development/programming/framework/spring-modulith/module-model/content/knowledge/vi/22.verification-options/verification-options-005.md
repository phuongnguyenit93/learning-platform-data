# jMolecules architecture rules trong options

`ApplicationModules.verify()` của Spring Modulith kiểm tra những quy tắc cơ bản của modular monolith: dependency giữa module không tạo chu trình, module chỉ truy cập API được công bố và dependency phải nằm trong `allowedDependencies` nếu module đã khai báo allowlist.

Trong một dự án, nhóm có thể muốn kiểm tra thêm một phong cách kiến trúc ở cấp class và package. Ví dụ, domain không được phụ thuộc vào infrastructure, application service chỉ gọi port, hoặc adapter phải nằm ở phía ngoài của hexagonal architecture. jMolecules cung cấp các annotation mô tả vai trò kiến trúc và các ArchUnit rule để kiểm tra những quan hệ đó. Spring Modulith kết nối các rule này với `verify()` thông qua `VerificationOptions`.

## 1. Verification của Spring Modulith và verification của jMolecules

Hai nhóm kiểm tra giải quyết hai phạm vi khác nhau:

| Nhóm | Kiểm tra điều gì? | Ví dụ |
| --- | --- | --- |
| Spring Modulith module verification | Quan hệ giữa application module | Không có module dependency cycle; không truy cập package nội bộ; tuân thủ `allowedDependencies` |
| jMolecules architecture verification | Quan hệ giữa type, layer, port, adapter, aggregate và các building block kiến trúc | Domain không phụ thuộc infrastructure; adapter không gọi ngược application theo hướng bị cấm; aggregate tuân thủ quy tắc DDD |

Ví dụ, Spring Modulith có thể xác nhận `order` chỉ phụ thuộc vào `inventory` và `customer`. Điều đó chưa chứng minh class trong `order.domain` không gọi thẳng một adapter JDBC. Quy tắc module kiểm tra ranh giới giữa module; quy tắc jMolecules có thể kiểm tra cấu trúc bên trong module theo một phong cách kiến trúc cụ thể.

`VerificationOptions` là đối tượng cấu hình những verification bổ sung được thực thi cùng module verification. Nó không thay thế module model, không tạo dependency và không thay đổi `allowedDependencies`.

## 2. jMolecules ArchUnit được tích hợp khi có trên classpath

jMolecules cung cấp các annotation và abstraction để biểu diễn building block như aggregate, entity, repository, domain event, port, adapter và layer. Module `jmolecules-archunit` cung cấp ArchUnit rule để kiểm tra những quan hệ kiến trúc được mô tả bằng các stereotype đó.

Spring Modulith có thể tích hợp với jMolecules ArchUnit. Khi các dependency jMolecules phù hợp có mặt trên classpath, `VerificationOptions.defaults()` đưa các DDD verification được tích hợp vào cấu hình mặc định. Vì vậy, kết quả của `ApplicationModules.verify()` có thể bao gồm cả vi phạm module boundary và vi phạm quy tắc DDD tương ứng.

Việc có jMolecules trên classpath không có nghĩa mọi preset như Hexagonal, Onion hoặc Layered tự động được chọn. Tích hợp mặc định không tự quyết định phong cách kiến trúc mà dự án muốn áp dụng. Các preset kiến trúc cụ thể cần được nhóm quyết định và đăng ký rõ ràng. `VerificationOptions` là nơi kết hợp những rule đó với verification mặc định.

## 3. Chuẩn bị dependency jMolecules

Nếu muốn sử dụng rule jMolecules, cần đưa integration ArchUnit và các annotation artifact tương ứng vào classpath của bài test kiến trúc. Ví dụ với Gradle:

```kotlin
dependencies {
    testImplementation("org.jmolecules.integrations:jmolecules-archunit")
    testImplementation("org.jmolecules:jmolecules-ddd")
    testImplementation("org.jmolecules:jmolecules-hexagonal-architecture")
}
```

Các artifact annotation cần thiết phụ thuộc vào rule mà dự án sử dụng. Nếu chỉ dùng DDD rules, cần có các type DDD tương ứng; nếu dùng stereotype Hexagonal, cần artifact chứa annotation Hexagonal. Hãy quản lý phiên bản bằng jMolecules BOM và chọn phiên bản tương thích với Spring Modulith, ArchUnit và Java của dự án.

Với Maven, khai báo các artifact tương ứng trong `dependencies` và dùng BOM để quản lý phiên bản. Nếu chỉ chạy verification trong test, có thể đặt chúng ở test scope. Nếu runtime component của ứng dụng cũng gọi verification, các artifact cần thiết phải có mặt trên runtime classpath.

Một số rule có thể tham chiếu trực tiếp annotation type khi khởi tạo. Vì vậy, chỉ thêm `jmolecules-archunit` mà thiếu artifact annotation mà rule cần có thể dẫn đến `NoClassDefFoundError`. Hãy kiểm tra dependency tree và bảo đảm các artifact liên quan được đồng bộ.

## 4. `VerificationOptions.defaults()`

Tạo options mặc định:

```java
import org.springframework.modulith.core.VerificationOptions;

VerificationOptions options = VerificationOptions.defaults();
```

`defaults()` tạo một `VerificationOptions` có các verification bổ sung mặc định, bao gồm jMolecules verifications nếu chúng hiện diện và được nhận diện trên classpath. Nếu classpath không có jMolecules integration phù hợp, Spring Modulith vẫn chạy các quy tắc module cốt lõi của nó.

Thông thường, khi không cần tùy chỉnh, chỉ cần:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Overload không truyền options sử dụng cấu hình mặc định. Dùng `VerificationOptions` khi cần thay thế hoặc bổ sung ArchUnit rule cụ thể.

## 5. Thêm một architecture rule vào verification

Giả sử nhóm muốn kiểm tra cấu trúc Hexagonal Architecture. jMolecules cung cấp rule preset qua `JMoleculesArchitectureRules.ensureHexagonal()`:

```java
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

var hexagonal = JMoleculesArchitectureRules.ensureHexagonal();

var options = VerificationOptions.defaults()
        .andAdditionalVerifications(hexagonal);

ApplicationModules.of(ShopApplication.class).verify(options);
```

`ensureHexagonal()` trả về một ArchUnit `ArchRule`. `andAdditionalVerifications(…)` đăng ký rule này bên cạnh những verification bổ sung đã có trong options mặc định. Đây thường là cách phù hợp khi muốn giữ các jMolecules DDD checks mặc định và thêm một rule kiến trúc khác.

Sau đó, `verify(options)` chạy cả quy tắc module của Spring Modulith lẫn các verification bổ sung đã được options chọn. Nếu một rule phát hiện vi phạm, bài test kiến trúc thất bại.

## 6. Phân biệt `withAdditionalVerifications()` và `andAdditionalVerifications()`

Hai method có tên gần giống nhau nhưng semantics khác nhau. Đây là điểm cần chú ý khi kết hợp jMolecules với Spring Modulith:

| Method | Hành vi |
| --- | --- |
| `withAdditionalVerifications(rules…)` | Định nghĩa lại tập verification bổ sung sẽ chạy; các verification bổ sung mặc định bị thay thế |
| `andAdditionalVerifications(rules…)` | Thêm rule vào tập verification bổ sung đang có, giữ lại các rule mặc định |
| `withoutAdditionalVerifications()` | Tắt các verification bổ sung được đăng ký mặc định |

Ví dụ, muốn chạy rule Hexagonal cùng các verification bổ sung mặc định:

```java
var options = VerificationOptions.defaults()
        .andAdditionalVerifications(
                JMoleculesArchitectureRules.ensureHexagonal()
        );
```

Nếu dùng `withAdditionalVerifications()`:

```java
var options = VerificationOptions.defaults()
        .withAdditionalVerifications(
                JMoleculesArchitectureRules.ensureHexagonal()
        );
```

tập verification bổ sung mặc định bị thay thế bằng rule Hexagonal được truyền vào. Các kiểm tra module cốt lõi của Spring Modulith vẫn được thực hiện; điều bị thay thế là tập verification bổ sung, chẳng hạn jMolecules checks được đăng ký mặc định.

Hãy chọn `andAdditionalVerifications()` khi mục tiêu là mở rộng. Chọn `withAdditionalVerifications()` khi chủ ý thay tập rule bổ sung mặc định bằng một tập do dự án kiểm soát.

## 7. `withoutAdditionalVerifications()` dùng khi nào?

Có thể tắt các verification bổ sung mặc định:

```java
var options = VerificationOptions.defaults()
        .withoutAdditionalVerifications();

ApplicationModules.of(ShopApplication.class).verify(options);
```

Các kiểm tra module cốt lõi như module cycle, package boundary và `allowedDependencies` vẫn được thực hiện. Phương thức này chỉ tắt các verification bổ sung được đăng ký mặc định.

Một số lý do có thể cần tắt:

- Dự án chưa sử dụng các stereotype jMolecules nhưng dependency integration đã có mặt gián tiếp.
- Nhóm đang chuyển đổi dần một codebase và muốn tạm thời tách lỗi DDD khỏi lỗi module boundary.
- Muốn tự đăng ký một tập ArchRule riêng và quản lý rõ các rule được thực thi.

Không nên tắt verification chỉ để làm test xanh. Nếu rule mặc định báo lỗi, hãy xác định lỗi phản ánh một vi phạm thật hay do mô hình annotation chưa đầy đủ. Nếu tắt tạm thời, ghi rõ lý do và điều kiện bật lại trong test kiến trúc.

## 8. Các preset kiến trúc jMolecules thường dùng

`JMoleculesArchitectureRules` cung cấp một số preset có thể đăng ký vào `VerificationOptions`:

| Rule | Mục tiêu | Annotation/stereotype thường dùng |
| --- | --- | --- |
| `ensureHexagonal()` | Kiểm tra quan hệ giữa application, port và adapter theo Hexagonal Architecture | `@Application`, `@Port`, `@PrimaryPort`, `@SecondaryPort`, `@Adapter`, `@PrimaryAdapter`, `@SecondaryAdapter` |
| `ensureLayering()` | Kiểm tra thứ tự phụ thuộc giữa interface, application, domain và infrastructure layer | `@InterfaceLayer`, `@ApplicationLayer`, `@DomainLayer`, `@InfrastructureLayer` |
| `ensureLayeringStrict()` | Áp dụng quy tắc layer chặt hơn, chỉ cho phép truy cập layer kế tiếp theo hướng đã định | Các annotation layer tương ứng |
| `ensureOnionSimple()` | Kiểm tra các ring cơ bản của Onion Architecture | `@DomainRing`, `@ApplicationRing`, `@InfrastructureRing` |
| `ensureOnionClassical()` | Kiểm tra các ring theo biến thể Onion cổ điển | `@DomainModelRing`, `@DomainServiceRing`, `@ApplicationServiceRing`, `@InfrastructureRing` |

Các preset này là lựa chọn kiến trúc, không phải bộ quy tắc phải bật đồng thời. Một dự án có thể chọn Hexagonal hoặc Onion tùy cách tổ chức code. Nếu bật nhiều preset có giả định khác nhau trên cùng một codebase, các rule có thể chồng lấn hoặc đưa ra yêu cầu không phù hợp với thiết kế thực tế.

## 9. Ví dụ thêm Hexagonal rule và giữ verification mặc định

Giả sử module `order` tổ chức theo ports and adapters:

```text
order
├── application
│   └── PlaceOrderService.java
├── domain
│   └── Order.java
├── port
│   ├── PlaceOrderUseCase.java
│   └── InventoryPort.java
└── adapter
    ├── web
    │   └── OrderController.java
    └── persistence
        └── JpaOrderAdapter.java
```

Các type có thể được đánh dấu bằng stereotype jMolecules tương ứng. Sau đó, đăng ký rule Hexagonal trong bài test:

```java
package com.acme.shop;

import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class ArchitectureTests {

    @Test
    void verifiesModulesAndHexagonalArchitecture() {
        var options = VerificationOptions.defaults()
                .andAdditionalVerifications(
                        JMoleculesArchitectureRules.ensureHexagonal()
                );

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
```

Bài test này kiểm tra hai tầng: Spring Modulith xác nhận module dependency và package boundary; jMolecules kiểm tra các reference giữa application, port và adapter theo stereotype Hexagonal. Nếu một adapter bị gọi trực tiếp từ domain hoặc một layer tham chiếu sai hướng, ArchUnit rule có thể báo violation.

## 10. Thêm rule Layered hoặc Onion

Nếu codebase dùng layered architecture, có thể đăng ký rule layer:

```java
var options = VerificationOptions.defaults()
        .andAdditionalVerifications(
                JMoleculesArchitectureRules.ensureLayeringStrict()
        );

ApplicationModules.of(ShopApplication.class).verify(options);
```

Với Onion Architecture:

```java
var options = VerificationOptions.defaults()
        .andAdditionalVerifications(
                JMoleculesArchitectureRules.ensureOnionSimple()
        );

ApplicationModules.of(ShopApplication.class).verify(options);
```

Hoặc chọn biến thể Onion cổ điển bằng `ensureOnionClassical()`. Hãy dùng đúng nhóm stereotype mà rule tương ứng nhận diện. Nếu các class không được gắn annotation layer/ring, rule có thể không phân loại chúng như nhóm dự kiến hoặc báo rằng quan hệ không tuân thủ.

## 11. Thêm ArchUnit rule tự định nghĩa

Không bắt buộc phải dùng preset jMolecules. `VerificationOptions` nhận `ArchRule`, vì vậy nhóm có thể thêm rule ArchUnit riêng cho quy ước của tổ chức.

Ví dụ, domain package không được phụ thuộc vào web package:

```java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

ArchRule domainMustNotDependOnWeb = noClasses()
        .that().resideInAPackage("..domain..")
        .should().dependOnClassesThat()
        .resideInAPackage("..web..");

var options = VerificationOptions.defaults()
        .andAdditionalVerifications(domainMustNotDependOnWeb);

ApplicationModules.of(ShopApplication.class).verify(options);
```

Rule tùy chỉnh có thể được lưu thành constant hoặc factory method để nhiều test dùng chung. Hãy đặt tên rule theo ý định kiến trúc và viết mô tả rõ ràng để diagnostic có ý nghĩa khi CI thất bại.

## 12. Dùng options với `detectViolations()`

`verify(options)` ném exception nếu có vi phạm. Nếu muốn lấy tập vi phạm để lọc, ghi log hoặc xử lý theo chính sách riêng, có thể dùng `detectViolations(options)`:

```java
var options = VerificationOptions.defaults()
        .andAdditionalVerifications(
                JMoleculesArchitectureRules.ensureHexagonal()
        );

var violations = ApplicationModules.of(ShopApplication.class)
        .detectViolations(options);

violations.throwIfPresent();
```

`detectViolations(options)` chạy cùng tập kiểm tra đã chọn và trả về `Violations`. Nhóm có thể xem hoặc lọc các violation trước khi gọi `throwIfPresent()`. Chỉ nên bỏ qua một violation khi có lý do kiến trúc cụ thể, phạm vi hẹp và có kế hoạch xử lý; không nên lọc bỏ hàng loạt để che giấu vấn đề.

## 13. Phân biệt `VerificationOptions` với các cấu hình module

`VerificationOptions` là cấu hình ở thời điểm gọi API verification. Nó khác với các metadata của application module:

| Cơ chế | Vai trò |
| --- | --- |
| `@ApplicationModule(allowedDependencies = …)` | Giới hạn module/interface mà một module được phép phụ thuộc |
| `@NamedInterface` | Công bố một package con làm API có tên |
| `@ApplicationModule(type = OPEN)` | Nới lỏng việc bảo vệ package nội bộ của module |
| `VerificationOptions` | Chọn các verification bổ sung sẽ chạy cùng module verification |
| jMolecules `ArchRule` | Mô tả quy tắc kiến trúc ở cấp class/package như Hexagonal, Layered hoặc Onion |

Thay đổi `VerificationOptions` không sửa module model và không làm một dependency trở nên hợp lệ theo `allowedDependencies`. Nó chỉ thay đổi tập rule được chạy trong lần verification đó.

## 14. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Có `jmolecules-archunit` thì mọi preset kiến trúc tự chạy. | jMolecules verifications mặc định được tích hợp khi phù hợp trên classpath; preset Hexagonal, Layered hoặc Onion cần được chọn rõ ràng. |
| `VerificationOptions.defaults()` chỉ chứa rule của Spring Modulith. | Nó có thể bao gồm jMolecules verification nếu dependency tương ứng có mặt. |
| `withAdditionalVerifications()` luôn thêm rule mà không ảnh hưởng rule cũ. | Method này thay thế tập verification bổ sung mặc định; dùng `andAdditionalVerifications()` để cộng thêm. |
| `withoutAdditionalVerifications()` tắt toàn bộ `ApplicationModules.verify()`. | Nó chỉ tắt verification bổ sung mặc định; module checks cốt lõi vẫn chạy. |
| Thêm một ArchRule sẽ thay đổi `allowedDependencies`. | ArchRule kiểm tra quan hệ type/package; allowlist module vẫn là metadata riêng. |
| Chọn Hexagonal và Onion cùng lúc luôn tốt hơn. | Chỉ chọn rule phù hợp với kiến trúc mà codebase thực sự áp dụng; rule chồng lấn có thể tạo yêu cầu mâu thuẫn. |
| Chỉ cần `jmolecules-archunit`, không cần annotation artifact. | Rule có thể cần các annotation type tương ứng trên classpath; thiếu chúng có thể gây lỗi class loading hoặc không phân loại được stereotype. |

## 15. Ghi nhớ

`VerificationOptions` cho phép tùy chỉnh các verification bổ sung chạy cùng `ApplicationModules.verify()` hoặc `detectViolations()`. `defaults()` giữ cấu hình bổ sung mặc định và tích hợp jMolecules verifications khi dependency tương ứng có mặt. `andAdditionalVerifications()` thêm rule mới mà vẫn giữ rule mặc định; `withAdditionalVerifications()` thay thế tập rule bổ sung; `withoutAdditionalVerifications()` tắt tập bổ sung mặc định.

jMolecules cung cấp các ArchUnit rule cho DDD, Hexagonal, Layered và Onion Architecture. Hãy chọn preset phù hợp với stereotype mà codebase đang sử dụng, đăng ký bằng `VerificationOptions`, rồi chạy verification trong test/CI. Đừng nhầm rule ở cấp class/layer với quy tắc module của Spring Modulith: chúng bổ sung cho nhau. Cuối cùng, quản lý đúng dependency jMolecules và annotation artifact trên classpath để rule có thể được khởi tạo và thực thi ổn định.

## Tài liệu tham khảo

- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith API — `VerificationOptions`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)
- [jMolecules ArchUnit — `JMoleculesArchitectureRules`](https://javadoc.io/doc/org.jmolecules.integrations/jmolecules-archunit/latest/org/jmolecules/archunit/JMoleculesArchitectureRules.html)
- [jMolecules — Architecture and DDD Building Blocks](https://github.com/xmolecules/jmolecules)

# Đăng ký additional verifications

Spring Modulith cung cấp `VerificationOptions` để tùy chỉnh các quy tắc kiểm tra kiến trúc chạy cùng `ApplicationModules.verify()` hoặc `detectViolations()`. Ngoài các kiểm tra cốt lõi về chu trình module, truy cập API và `allowedDependencies`, bạn có thể đăng ký thêm quy tắc `ArchRule` của ArchUnit để kiểm soát những quy ước riêng của ứng dụng.

Ví dụ, một nhóm có thể muốn bảo đảm các lớp trong package `domain` không phụ thuộc vào package `web`, hoặc muốn áp dụng quy tắc kiến trúc Hexagonal từ jMolecules. Các quy tắc này được chạy trong cùng lần xác minh module model, giúp architecture test kiểm tra cả quy tắc Spring Modulith lẫn quy ước kiến trúc riêng.

Sau bài học, bạn có thể:

- Giải thích vai trò của `VerificationOptions`.
- Đăng ký custom `ArchRule` bằng `andAdditionalVerifications()`.
- Phân biệt `andAdditionalVerifications()` với `withAdditionalVerifications()`.
- Hiểu các additional verification mặc định từ jMolecules khi thư viện có trên classpath.
- Tắt additional verifications mặc định khi thực sự cần bằng `withoutAdditionalVerifications()`.
- Chạy và xử lý kết quả bằng `verify(options)` hoặc `detectViolations(options)`.

## 1. Vì sao cần additional verifications?

`ApplicationModules.verify()` kiểm tra các quy tắc cấu trúc module mà Spring Modulith cung cấp sẵn. Các quy tắc cốt lõi gồm:

- Không có chu trình ở cấp application module.
- Module chỉ truy cập kiểu thuộc API package được công khai; tham chiếu package nội bộ của module đóng bị từ chối.
- Nếu module khai báo `allowedDependencies`, các phụ thuộc phải nằm trong danh sách cho phép.

Spring Modulith còn có thể tự chạy các kiểm tra bổ sung của jMolecules nếu thư viện tích hợp jMolecules ArchUnit có mặt trên classpath. `VerificationOptions` cho phép điều chỉnh nhóm kiểm tra bổ sung đó hoặc thêm các `ArchRule` riêng của dự án.

Ví dụ, ứng dụng có thể cần các quy ước ngoài phạm vi module boundary:

- Domain model không phụ thuộc vào web controller.
- Adapter không truy cập trực tiếp repository thuộc adapter khác.
- Các lớp trong package `application` không phụ thuộc vào package `bootstrap`.
- Cấu trúc code tuân thủ Hexagonal Architecture hoặc quy tắc layer riêng.

Đây là những quy tắc bổ sung của ứng dụng. Chúng không thay thế các kiểm tra cốt lõi của Spring Modulith.

## 2. `VerificationOptions` và các phương thức chính

`VerificationOptions` thuộc package `org.springframework.modulith.core`. Lớp này cung cấp các phương thức để tạo tập additional verification sẽ được chạy:

| Phương thức | Ý nghĩa |
|---|---|
| `VerificationOptions.defaults()` | Tạo options mặc định; bao gồm kiểm tra jMolecules nếu thư viện tương ứng có trên classpath |
| `andAdditionalVerifications(...)` | Thêm các `ArchRule` vào nhóm additional verification mặc định |
| `withAdditionalVerifications(...)` | Đặt nhóm additional verification cần chạy; thay thế nhóm additional verification mặc định |
| `withoutAdditionalVerifications()` | Tắt các additional verification được đăng ký mặc định |

Các phương thức nhận một hoặc nhiều `ArchRule`, hoặc một `Collection<ArchRule>`. `ArchRule` là abstraction của ArchUnit để mô tả một quy tắc kiến trúc có thể thực thi trên các Java class được import.

Điểm cần phân biệt: các phương thức trên điều chỉnh **additional verifications**. Chúng không tắt các kiểm tra cốt lõi mà Spring Modulith thực hiện cho module arrangement như cycle detection, API package access và `allowedDependencies`.

## 3. Tạo một custom `ArchRule`

Giả sử ứng dụng có các package theo tầng:

```text
com.acme.shop
├── order
│   ├── domain
│   ├── application
│   └── web
└── inventory
    ├── domain
    ├── application
    └── web
```

Quy ước của nhóm là domain model không được phụ thuộc vào web layer. Có thể mô tả bằng ArchUnit:

```java
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

ArchRule domainMustNotDependOnWeb = noClasses()
        .that().resideInAPackage("..domain..")
        .should().dependOnClassesThat()
        .resideInAPackage("..web..");
```

Đọc quy tắc theo thứ tự:

1. `noClasses()` chọn một quy tắc phủ định: không lớp nào trong tập được chọn được vi phạm điều kiện.
2. `.that().resideInAPackage("..domain..")` chọn các lớp thuộc package có segment `domain`.
3. `.should().dependOnClassesThat().resideInAPackage("..web..")` cấm các lớp đó phụ thuộc vào lớp trong package có segment `web`.

Hai dấu chấm `..` trong package identifier của ArchUnit là wildcard cho các package segment. Pattern `..domain..` có thể khớp package `domain` ở nhiều vị trí trong namespace; nếu ứng dụng có package khác cũng tên `domain`, hãy thu hẹp pattern theo root cụ thể, ví dụ `com.acme.shop..domain..`.

## 4. Bổ sung quy tắc vào các verification mặc định

Trong phần lớn trường hợp, bạn muốn giữ nguyên additional verification mặc định và chỉ thêm quy tắc riêng. Hãy tạo options bằng `defaults()` rồi gọi `andAdditionalVerifications()`:

```java
import com.acme.shop.ShopApplication;
import com.tngtech.archunit.lang.ArchRule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

class ModularityTests {

    void verifiesApplicationWithCustomRules() {
        ArchRule domainMustNotDependOnWeb = noClasses()
                .that().resideInAPackage("com.acme.shop..domain..")
                .should().dependOnClassesThat()
                .resideInAPackage("com.acme.shop..web..");

        VerificationOptions options = VerificationOptions.defaults()
                .andAdditionalVerifications(domainMustNotDependOnWeb);

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
```

Trong ví dụ, Spring Modulith vẫn chạy các additional verification mặc định được đăng ký qua `defaults()` (bao gồm các quy tắc jMolecules nếu có trên classpath), đồng thời chạy `domainMustNotDependOnWeb`.

Bạn có thể thêm nhiều quy tắc trong cùng lời gọi:

```java
VerificationOptions options = VerificationOptions.defaults()
        .andAdditionalVerifications(
                domainMustNotDependOnWeb,
                applicationMustNotDependOnWeb
        );
```

Hãy đặt tên biến `ArchRule` theo điều kiện mà nó bảo vệ. Tên rõ ràng giúp người đọc hiểu lý do bài kiểm tra thất bại mà không phải giải mã toàn bộ DSL ngay từ đầu.

## 5. Phân biệt `andAdditionalVerifications()` và `withAdditionalVerifications()`

Hai phương thức có tên gần giống nhau nhưng hành vi khác nhau.

### Dùng `andAdditionalVerifications()` để thêm vào mặc định

```java
VerificationOptions options = VerificationOptions.defaults()
        .andAdditionalVerifications(domainMustNotDependOnWeb);
```

Phương thức này đăng ký rule mới bên cạnh các additional verification mặc định. Đây là lựa chọn phù hợp khi dự án muốn mở rộng kiểm tra hiện có.

### Dùng `withAdditionalVerifications()` để thay thế nhóm mặc định

```java
VerificationOptions options = VerificationOptions.defaults()
        .withAdditionalVerifications(domainMustNotDependOnWeb);
```

Phương thức này định nghĩa tập additional verification sẽ chạy và tắt những additional verification được đăng ký mặc định. Trong ví dụ, rule `domainMustNotDependOnWeb` thay thế nhóm additional verification mặc định, chẳng hạn nhóm jMolecules tự đăng ký nếu có trên classpath.

Các kiểm tra cốt lõi của Spring Modulith vẫn được áp dụng khi gọi `verify(options)`. `withAdditionalVerifications()` không phải cách tắt cycle detection hay module boundary verification.

| Nhu cầu | Cách chọn |
|---|---|
| Giữ các kiểm tra bổ sung mặc định và thêm rule của dự án | `defaults().andAdditionalVerifications(...)` |
| Chỉ chạy tập additional rule do dự án chỉ định | `defaults().withAdditionalVerifications(...)` |
| Tắt các additional verification mặc định | `defaults().withoutAdditionalVerifications()` |

## 6. Tắt additional verifications mặc định

Trong một số trường hợp, dự án muốn tắt nhóm additional verification được đăng ký mặc định:

```java
VerificationOptions options = VerificationOptions.defaults()
        .withoutAdditionalVerifications();

ApplicationModules.of(ShopApplication.class).verify(options);
```

Thao tác này tắt additional verification mặc định, chẳng hạn các rule jMolecules được tự động kích hoạt khi thư viện có mặt. Các quy tắc module cốt lõi của Spring Modulith vẫn chạy.

Không nên dùng tùy chọn này chỉ để làm cho một bài test đang thất bại trở thành thành công. Trước khi tắt, hãy xác định rule nào đang thất bại và vì sao. Nếu chỉ một quy tắc jMolecules không phù hợp, cân nhắc chọn lại tập additional verification một cách có chủ đích và bổ sung rule thay thế tương ứng.

## 7. Tích hợp quy tắc Hexagonal Architecture từ jMolecules

Spring Modulith có thể tích hợp với jMolecules ArchUnit để kiểm tra các quy ước kiến trúc. Tài liệu Spring Modulith minh họa cách tạo rule Hexagonal Architecture ở mức `STRICT`:

```java
import com.acme.shop.ShopApplication;
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.jmolecules.archunit.VerificationDepth;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

var hexagonal = JMoleculesArchitectureRules.ensureHexagonal(
        VerificationDepth.STRICT
);

var options = VerificationOptions.defaults()
        .andAdditionalVerifications(hexagonal);

ApplicationModules.of(ShopApplication.class).verify(options);
```

`JMoleculesArchitectureRules.ensureHexagonal(...)` tạo một `ArchRule` kiểm tra cấu trúc Hexagonal Architecture. `VerificationDepth.STRICT` chọn mức kiểm tra nghiêm ngặt. Vì dùng `andAdditionalVerifications()`, rule Hexagonal được chạy cùng nhóm additional verification mặc định.

Đoạn mã cần dependency jMolecules tương ứng và các package API đúng với phiên bản dependency đang dùng. Nếu chỉ muốn kiểm tra các quy tắc riêng của dự án bằng ArchUnit, bạn không cần thêm jMolecules chỉ để tạo `ArchRule` thông thường.

## 8. Dùng options với `detectViolations()`

`verify(options)` ném exception nếu phát hiện vi phạm. Nếu muốn lấy đối tượng `Violations` để lọc hoặc xử lý kết quả trước, dùng `detectViolations(options)`:

```java
var modules = ApplicationModules.of(ShopApplication.class);

var violations = modules.detectViolations(options);

violations.throwIfPresent();
```

Bạn có thể lọc danh sách vi phạm trước khi quyết định có ném lỗi hay không:

```java
modules.detectViolations(options)
        .filter(violation -> !isTemporarilyAccepted(violation))
        .throwIfPresent();
```

`isTemporarilyAccepted(violation)` là hàm minh họa do dự án tự định nghĩa. Nếu dùng cơ chế lọc, hãy ghi rõ lý do, phạm vi và thời hạn xử lý cho ngoại lệ kiến trúc; nếu không, việc bỏ qua có thể che khuất vi phạm mới.

Khác biệt quan trọng về vòng đời: `verify(options)` thực thi kiểm tra trừ khi việc xác minh đã được thực hiện trên instance `ApplicationModules` đó. `detectViolations(options)` luôn thực thi các verification. Khi cần chạy lại với options khác, hãy tạo một module model mới hoặc dùng `detectViolations(options)` để bảo đảm các rule được đánh giá lại.

## 9. Tổ chức architecture test trong JUnit

Một cách tổ chức rõ ràng là đặt custom rule ở một phương thức hoặc class chuyên trách, rồi dùng cùng options trong architecture test:

```java
import com.acme.shop.ShopApplication;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

class ModularityTests {

    @Test
    void verifiesModuleStructureAndLayering() {
        ArchRule domainMustNotDependOnWeb = noClasses()
                .that().resideInAPackage("com.acme.shop..domain..")
                .should().dependOnClassesThat()
                .resideInAPackage("com.acme.shop..web..");

        VerificationOptions options = VerificationOptions.defaults()
                .andAdditionalVerifications(domainMustNotDependOnWeb);

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
```

Bài kiểm tra này xác minh đồng thời cấu trúc module và quy tắc layering của ứng dụng. Khi quy tắc thất bại, thông báo ArchUnit giúp xác định lớp nguồn đang phụ thuộc vào lớp đích nào.

Nếu có nhiều nhóm rule, có thể tách thành các phương thức trả về `ArchRule` hoặc một factory tạo `VerificationOptions`. Giữ tên và phạm vi package cụ thể để tránh rule vô tình áp dụng lên package không thuộc ứng dụng.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Rule custom chạy nhưng jMolecules rule biến mất | Dùng `withAdditionalVerifications()` và vô tình thay thế nhóm mặc định | Dùng `andAdditionalVerifications()` nếu muốn bổ sung |
| Nghĩ `withoutAdditionalVerifications()` tắt mọi kiểm tra | Nhầm additional rules với core module verification | Nhớ rằng cycle, API access và `allowedDependencies` vẫn được kiểm tra |
| Không thấy jMolecules rule được chạy | Dependency jMolecules ArchUnit không có trên classpath | Kiểm tra dependency test/runtime phù hợp và `VerificationOptions.defaults()` |
| Rule khớp quá nhiều package | Dùng pattern rộng như `..domain..` trong ứng dụng nhiều namespace | Thu hẹp package identifier theo root ứng dụng |
| Test không chạy lại rule sau khi thay options | Gọi `verify()` nhiều lần trên cùng instance đã xác minh | Tạo `ApplicationModules` mới hoặc dùng `detectViolations(options)` |
| Rule custom không được áp dụng | Tạo options nhưng gọi `verify()` không truyền options | Dùng `verify(options)` hoặc `detectViolations(options)` |
| Architecture test bỏ qua vi phạm | Lọc violation quá rộng hoặc không có lý do rõ ràng | Thu hẹp filter, ghi nhận ngoại lệ và tạo kế hoạch loại bỏ |

## 11. Ghi nhớ

`VerificationOptions` cho phép tùy chỉnh các additional verification chạy cùng module verification. Dùng `defaults().andAdditionalVerifications(rule)` để thêm ArchUnit rule vào nhóm mặc định; dùng `withAdditionalVerifications(rule)` để thay thế nhóm additional verification mặc định; dùng `withoutAdditionalVerifications()` để tắt nhóm mặc định. Các kiểm tra cốt lõi của Spring Modulith vẫn được giữ. Có thể chạy options bằng `ApplicationModules.verify(options)` hoặc lấy và lọc kết quả qua `detectViolations(options)`. Hãy đặt custom rule theo quy ước kiến trúc cụ thể của ứng dụng và giữ architecture test trong CI.

## Tài liệu tham khảo

- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith 2.2.0 API – `VerificationOptions`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)
- [Spring Modulith 2.2.0 API – `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [ArchUnit User Guide](https://www.archunit.org/userguide/html/000_Index.html)
- [jMolecules Architecture Rules](https://github.com/xmolecules/jmolecules)

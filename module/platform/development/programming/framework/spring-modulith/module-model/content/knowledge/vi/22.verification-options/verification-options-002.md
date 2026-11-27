# Verification mặc định và verification bổ sung

Spring Modulith cung cấp các quy tắc xác minh cấu trúc application module ngay trong `ApplicationModules.verify()`. Khi ứng dụng cần thêm quy tắc riêng của tổ chức hoặc muốn điều chỉnh các kiểm tra được tự động kích hoạt theo classpath, có thể truyền `VerificationOptions` vào `verify(options)` hoặc `detectViolations(options)`.

Điều cần phân biệt là **verification cốt lõi của Spring Modulith** và **additional verifications**. Các quy tắc cốt lõi kiểm tra ranh giới module. Các kiểm tra bổ sung có thể đến từ tích hợp jMolecules trên classpath hoặc từ `ArchRule` do dự án tự định nghĩa.

## 1. Verification cốt lõi luôn kiểm tra điều gì?

Khi gọi `ApplicationModules.of(ShopApplication.class).verify()`, Spring Modulith kiểm tra các quy tắc cấu trúc module chính:

| Quy tắc cốt lõi | Ý nghĩa |
|---|---|
| Không có chu trình phụ thuộc giữa các module | Đồ thị phụ thuộc module phải là đồ thị có hướng không chu trình |
| Chỉ truy cập API được công khai của module khác | Module không được tham chiếu type thuộc package nội bộ của module `CLOSED` |
| Tuân thủ `allowedDependencies` nếu được khai báo | Module chỉ được phụ thuộc những module hoặc named interface đã cho phép |

Các quy tắc này thuộc quá trình xác minh module của Spring Modulith. `VerificationOptions` chủ yếu điều chỉnh những kiểm tra bổ sung chạy cùng quá trình đó; nó không phải công tắc tắt các quy tắc cấu trúc cốt lõi.

Ví dụ kiểm tra cơ bản:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules.of(ShopApplication.class).verify();
```

Nếu không có vi phạm, lời gọi hoàn tất bình thường. Nếu có vi phạm, `verify()` ném `Violations`.

## 2. Additional verifications đến từ đâu?

Spring Modulith có tích hợp tùy chọn với thư viện jMolecules ArchUnit. Nếu các thư viện jMolecules phù hợp xuất hiện trên classpath, những quy tắc xác minh Domain-Driven Design và kiến trúc do tích hợp đó cung cấp sẽ được tự động chạy cùng verification.

Điều này có nghĩa cùng một lệnh `verify()` có thể chạy số lượng quy tắc bổ sung khác nhau giữa hai dự án, tùy dependency của chúng. Một ứng dụng không dùng jMolecules vẫn nhận các quy tắc module cốt lõi của Spring Modulith.

`VerificationOptions` có từ Spring Modulith 1.4. `VerificationOptions.defaults()` tạo options mặc định và đưa các kiểm tra jMolecules vào nếu chúng có trên classpath:

```java
import org.springframework.modulith.core.VerificationOptions;

VerificationOptions options = VerificationOptions.defaults();
```

Thông thường có thể gọi `verify()` không tham số để dùng hành vi mặc định. Tạo options tường minh hữu ích khi muốn thêm rule riêng hoặc kiểm soát các kiểm tra bổ sung.

## 3. Đăng ký một ArchRule riêng

Giả sử kiến trúc của nhóm yêu cầu module `orders` không được phụ thuộc trực tiếp vào package `infrastructure`. Có thể biểu diễn quy tắc đó bằng ArchUnit:

```java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;

ArchRule ordersMustNotDependOnInfrastructure = noClasses()
        .that().resideInAPackage("..orders..")
        .should().dependOnClassesThat()
        .resideInAnyPackage("..infrastructure..");
```

Sau đó nối rule vào các kiểm tra mặc định bằng `andAdditionalVerifications()`:

```java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

VerificationOptions options = VerificationOptions.defaults()
        .andAdditionalVerifications(ordersMustNotDependOnInfrastructure);

ApplicationModules.of(ShopApplication.class).verify(options);
```

`andAdditionalVerifications()` đăng ký rule mới **trên nền các additional verifications mặc định**. Nếu jMolecules có trên classpath, những kiểm tra của tích hợp đó vẫn được giữ lại cùng rule của dự án.

Có thể truyền nhiều rule cùng lúc:

```java
VerificationOptions options = VerificationOptions.defaults()
        .andAdditionalVerifications(
                ordersMustNotDependOnInfrastructure,
                anotherArchitectureRule);
```

Các `ArchRule` được thực thi cùng với verification cốt lõi của Spring Modulith. Nếu một rule thất bại, vi phạm được đưa vào kết quả tổng hợp và `verify(options)` sẽ ném `Violations`.

## 4. Phân biệt andAdditionalVerifications và withAdditionalVerifications

Hai phương thức có tên gần giống nhau nhưng hành vi khác nhau. Đây là điểm dễ gây nhầm lẫn nhất khi tùy chỉnh options:

| Phương thức | Hành vi |
|---|---|
| `andAdditionalVerifications(...)` | Thêm rule mới bên cạnh các additional verifications mặc định |
| `withAdditionalVerifications(...)` | Đặt danh sách additional verifications cần chạy và vô hiệu hóa những rule bổ sung được đăng ký mặc định |
| `withoutAdditionalVerifications()` | Tắt các additional verifications được đăng ký mặc định |

Nếu mục tiêu là **bổ sung** quy tắc của nhóm mà vẫn giữ kiểm tra jMolecules tự động, dùng `andAdditionalVerifications()`.

Nếu chủ đích là thay thế các rule bổ sung mặc định bằng một tập rule do dự án quản lý, dùng `withAdditionalVerifications()`:

```java
VerificationOptions options = VerificationOptions.defaults()
        .withAdditionalVerifications(ordersMustNotDependOnInfrastructure);
```

Lời gọi trên không có nghĩa “giữ mọi rule mặc định rồi thêm một rule”. Nó thay thế additional verifications được chạy mặc định bằng rule được truyền vào. Các quy tắc cốt lõi về chu trình, API/internal và `allowedDependencies` của Spring Modulith vẫn được thực thi.

## 5. Khi nào dùng withoutAdditionalVerifications?

`withoutAdditionalVerifications()` tắt các additional verifications được đăng ký mặc định, ví dụ các rule jMolecules được tự động nhận diện từ classpath:

```java
VerificationOptions options = VerificationOptions.defaults()
        .withoutAdditionalVerifications();

ApplicationModules.of(ShopApplication.class).verify(options);
```

Sau cấu hình này, Spring Modulith vẫn kiểm tra cấu trúc module cốt lõi: chu trình phụ thuộc, truy cập package nội bộ và allowlist nếu có. Chỉ nhóm kiểm tra bổ sung mặc định bị tắt.

Đây là lựa chọn có phạm vi ảnh hưởng rộng. Nếu dự án dựa vào jMolecules để kiểm tra các quy ước DDD, việc tắt additional verifications sẽ bỏ qua các kiểm tra đó. Chỉ dùng khi đã hiểu rule nào bị loại và có kế hoạch kiểm tra thay thế phù hợp.

## 6. Chọn options theo mục tiêu

| Mục tiêu | Cấu hình gợi ý |
|---|---|
| Dùng toàn bộ hành vi mặc định | `ApplicationModules.of(...).verify()` |
| Tạo options mặc định để cấu hình tiếp | `VerificationOptions.defaults()` |
| Thêm rule riêng và giữ rule mặc định | `defaults().andAdditionalVerifications(rule)` |
| Chỉ chạy tập rule bổ sung do dự án chỉ định | `defaults().withAdditionalVerifications(rule)` |
| Tắt các additional verifications mặc định | `defaults().withoutAdditionalVerifications()` |
| Lấy danh sách vi phạm với options cụ thể | `modules.detectViolations(options)` |

Một quy tắc thực tế là bắt đầu với options mặc định, sau đó chỉ thay đổi khi có yêu cầu kiến trúc cụ thể. Không nên tắt toàn bộ additional verifications chỉ vì một rule bên thứ ba tạo ra lỗi; hãy xác định chính xác rule gây lỗi và quyết định có cần điều chỉnh model hoặc thay thế riêng rule đó không.

## 7. Chẩn đoán bằng detectViolations(options)

`verify(options)` ném exception khi có vi phạm. Nếu muốn xem kết quả trước khi quyết định ném, dùng `detectViolations(options)`:

```java
var violations = ApplicationModules.of(ShopApplication.class)
        .detectViolations(options);

if (violations.hasViolations()) {
    violations.getMessages().forEach(System.err::println);
    violations.throwIfPresent();
}
```

`detectViolations(options)` chạy các verification theo options được truyền và trả về `Violations`. Có thể đọc thông điệp, lọc những vi phạm đã được xử lý theo chính sách rõ ràng hoặc gọi `throwIfPresent()` để làm test thất bại.

Khác với `verify(options)`, vốn chỉ chạy nếu verification chưa được thực hiện trên instance `ApplicationModules` đó, `detectViolations(options)` luôn thực thi lại các bước kiểm tra. Khi thử nhiều bộ options trên cùng một instance, dùng `detectViolations(options)` để tránh dựa vào kết quả verification đã chạy trước đó.

## 8. Đưa custom verification vào architecture test

Có thể gom việc tạo rule và chạy verification vào một test chuyên trách:

```java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class ModuleArchitectureTests {

    private static final ArchRule ORDERS_AVOID_INFRASTRUCTURE = noClasses()
            .that().resideInAPackage("..orders..")
            .should().dependOnClassesThat()
            .resideInAnyPackage("..infrastructure..");

    @Test
    void verifiesModuleStructureAndTeamRules() {
        VerificationOptions options = VerificationOptions.defaults()
                .andAdditionalVerifications(ORDERS_AVOID_INFRASTRUCTURE);

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
```

Ví dụ dùng API ArchUnit nên project cần ArchUnit trên test compile classpath. Spring Modulith sử dụng ArchUnit cho phân tích code và các `ArchRule`; kiểm tra dependency management của phiên bản dự án nếu import không được phân giải.

Khi custom rule thất bại, đọc thông điệp của `Violations` để xác định class nguồn, class đích và mô tả rule. Sau đó quyết định thay đổi code hoặc sửa rule nếu phạm vi kiến trúc đã thay đổi có chủ đích. Tránh viết rule quá rộng khiến test cấm cả các phụ thuộc hợp lệ hoặc lặp lại nguyên xi quy tắc cốt lõi mà Spring Modulith đã kiểm tra.

## 9. Những nhầm lẫn thường gặp

- **Nghĩ `VerificationOptions` bật/tắt toàn bộ module verification:** options điều chỉnh additional verifications; các quy tắc cấu trúc module cốt lõi vẫn chạy.
- **Dùng `withAdditionalVerifications()` để append:** phương thức này thay thế các additional verifications mặc định. Dùng `andAdditionalVerifications()` để nối thêm.
- **Nghĩ `defaults()` luôn chạy jMolecules:** chỉ khi các thư viện jMolecules phù hợp có trên classpath thì rule tích hợp mới được đưa vào.
- **Nghĩ `withoutAdditionalVerifications()` tắt chu trình hoặc kiểm tra API/internal:** phương thức chỉ tắt nhóm kiểm tra bổ sung mặc định.
- **Nghĩ custom `ArchRule` thay thế `allowedDependencies`:** rule riêng và quy tắc phụ thuộc module giải quyết các yêu cầu khác nhau; cả hai có thể chạy cùng nhau.
- **Dùng `verify(options)` nhiều lần để thử options khác nhau trên cùng instance:** `verify()` không chạy lại nếu đã xác minh; dùng instance mới hoặc `detectViolations(options)` khi cần thực thi lại.
- **Cho rằng custom rule tự động hiểu module boundary:** ArchUnit rule cần mô tả package/type mà nhóm muốn kiểm soát; hãy viết predicate rõ và kiểm tra thông điệp vi phạm.

## 10. Checklist cấu hình VerificationOptions

- [ ] Đã xác định yêu cầu thuộc quy tắc module cốt lõi hay additional verification.
- [ ] Đã kiểm tra jMolecules có trên classpath và những rule nào được tự động chạy.
- [ ] Đã chọn đúng `andAdditionalVerifications()` hoặc `withAdditionalVerifications()` theo mục tiêu.
- [ ] Chỉ dùng `withoutAdditionalVerifications()` khi chấp nhận bỏ các rule bổ sung mặc định.
- [ ] Custom `ArchRule` mô tả rõ package/type nguồn và đích.
- [ ] Đã chạy `verify(options)` trong architecture test.
- [ ] Đã dùng `detectViolations(options)` khi cần chạy lại hoặc chẩn đoán nhiều bộ options.
- [ ] Đã đọc và xử lý thông điệp `Violations`, không bỏ qua lỗi để làm test xanh.

`VerificationOptions` cho phép điều chỉnh mức kiểm tra kiến trúc theo nhu cầu dự án. Hiểu rõ ranh giới giữa quy tắc module cốt lõi, rule tự động từ classpath và custom ArchUnit rule giúp nhóm mở rộng verification mà không vô tình bỏ qua những kiểm tra đang bảo vệ module.

## Tài liệu tham khảo

- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [VerificationOptions API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [ArchUnit User Guide](https://www.archunit.org/userguide/html/000_Index.html)

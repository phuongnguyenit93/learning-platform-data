# `VerificationOptions` điều khiển việc kiểm tra

`ApplicationModules.verify()` kiểm tra các quy tắc kiến trúc của modular monolith. Khi cần bổ sung quy tắc riêng của dự án hoặc điều chỉnh những kiểm tra bổ sung được Spring Modulith tự đăng ký, ta có thể truyền `VerificationOptions` vào `verify(...)` hoặc `detectViolations(...)`.

`VerificationOptions` không thay thế mô hình application module và cũng không phải một công tắc tắt toàn bộ verification. Nó điều khiển **các kiểm tra bổ sung** được thực thi cùng với những quy tắc cốt lõi của Spring Modulith. Các quy tắc cốt lõi như đồ thị module không chu kỳ, truy cập API thay vì package nội bộ và `allowedDependencies` vẫn là nền tảng của việc kiểm tra module.

## 1. Khi nào cần VerificationOptions?

Giả sử ứng dụng bán hàng có các module `catalog`, `orders` và `inventory`. Spring Modulith có thể kiểm tra những quy tắc module cơ bản:

- Dependency giữa các application module không tạo chu trình.
- Module chỉ truy cập API công khai của module khác, không truy cập package nội bộ của closed module.
- Nếu module khai báo `allowedDependencies`, dependency thực tế phải nằm trong danh sách cho phép.

Ngoài những quy tắc đó, dự án có thể muốn kiểm tra thêm các nguyên tắc riêng, ví dụ:

- Controller không được phụ thuộc trực tiếp vào repository.
- Package web chỉ gọi application service, không truy cập persistence.
- Domain model không phụ thuộc vào Spring MVC hoặc JPA.
- Các quy tắc DDD hoặc kiến trúc hexagonal do jMolecules cung cấp phải được áp dụng.

`VerificationOptions` cho phép ghép những quy tắc bổ sung này vào lần kiểm tra application module. Nhờ đó, nhóm có thể giữ các nguyên tắc riêng của codebase trong cùng một bước kiểm tra kiến trúc.

## 2. Hiểu các lớp kiểm tra

Nên phân biệt hai nhóm quy tắc:

| Nhóm | Ví dụ | Vai trò của VerificationOptions |
|---|---|---|
| Quy tắc cốt lõi của Spring Modulith | Không có chu trình module; không truy cập internal package; tuân thủ `allowedDependencies` | Vẫn được thực thi khi gọi `verify(options)` |
| Kiểm tra bổ sung | ArchUnit `ArchRule` riêng; kiểm tra DDD của jMolecules nếu thư viện có trên classpath | Có thể giữ mặc định, thêm, thay thế hoặc tắt bằng options |

Điểm này rất quan trọng: gọi `withoutAdditionalVerifications()` không làm Spring Modulith ngừng kiểm tra chu trình module hoặc truy cập package nội bộ. Phương thức đó chỉ tắt nhóm kiểm tra bổ sung được đăng ký mặc định.

## 3. Tạo options mặc định

Tạo `VerificationOptions` bằng phương thức tĩnh `defaults()`:

```java
import org.springframework.modulith.core.VerificationOptions;

VerificationOptions options = VerificationOptions.defaults();
```

`defaults()` tạo options mặc định. Nếu các kiểm tra jMolecules có mặt trên classpath, chúng cũng được đưa vào nhóm kiểm tra bổ sung mặc định.

Khi chỉ muốn dùng hành vi mặc định, ta không cần truyền options:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Hoặc có thể truyền options được tạo tường minh:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.verify(VerificationOptions.defaults());
```

Hai cách trên giữ mục tiêu kiểm tra mặc định. Việc tạo options tường minh hữu ích khi chuẩn bị thêm hoặc điều chỉnh các quy tắc ở bước tiếp theo.

## 4. Thêm ArchRule riêng mà vẫn giữ các kiểm tra mặc định

Spring Modulith sử dụng ArchUnit cho việc phân tích cấu trúc và cho phép đăng ký thêm `ArchRule`. Phương thức `andAdditionalVerifications(...)` thêm quy tắc mới lên trên những kiểm tra bổ sung mặc định.

Ví dụ, dự án muốn bảo đảm package web của module `orders` không phụ thuộc trực tiếp vào package persistence:

```java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;
import org.springframework.modulith.core.VerificationOptions;

ArchRule webMustNotAccessPersistence = noClasses()
        .that().resideInAPackage("..orders.web..")
        .should().dependOnClassesThat()
        .resideInAPackage("..orders.persistence..");

VerificationOptions options = VerificationOptions.defaults()
        .andAdditionalVerifications(webMustNotAccessPersistence);
```

Áp dụng options vào mô hình:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.verify(options);
```

Khi đó, lần kiểm tra bao gồm các quy tắc cốt lõi của Spring Modulith, những kiểm tra bổ sung mặc định được chọn theo classpath và quy tắc `webMustNotAccessPersistence` của dự án.

Có thể truyền nhiều `ArchRule` trong cùng một lời gọi:

```java
ArchRule domainMustNotDependOnSpring = noClasses()
        .that().resideInAPackage("..domain..")
        .should().dependOnClassesThat()
        .resideInAPackage("org.springframework..");

VerificationOptions options = VerificationOptions.defaults()
        .andAdditionalVerifications(
                webMustNotAccessPersistence,
                domainMustNotDependOnSpring);
```

`andAdditionalVerifications(...)` là lựa chọn phù hợp khi muốn mở rộng bộ quy tắc đang có mà vẫn giữ các kiểm tra bổ sung mặc định.

## 5. Thay thế tập kiểm tra bổ sung bằng withAdditionalVerifications

`withAdditionalVerifications(...)` có ý nghĩa khác với `andAdditionalVerifications(...)`. Nó định nghĩa tập kiểm tra bổ sung cần chạy và **loại bỏ các kiểm tra bổ sung được đăng ký mặc định**.

Ví dụ:

```java
VerificationOptions options = VerificationOptions.defaults()
        .withAdditionalVerifications(webMustNotAccessPersistence);

ApplicationModules.of(ShopApplication.class).verify(options);
```

Trong cấu hình này, tập kiểm tra bổ sung được thay bằng `webMustNotAccessPersistence`. Những quy tắc cốt lõi của Spring Modulith vẫn được thực thi; phần bị thay thế là các kiểm tra bổ sung mặc định, chẳng hạn tích hợp jMolecules nếu chúng được đăng ký trong options mặc định.

Hãy dùng `withAdditionalVerifications(...)` khi chủ ý kiểm soát toàn bộ tập kiểm tra bổ sung. Nếu mục tiêu chỉ là thêm một quy tắc của dự án, hãy dùng `andAdditionalVerifications(...)` để tránh vô tình bỏ các kiểm tra đã có.

## 6. Tắt các kiểm tra bổ sung mặc định

`withoutAdditionalVerifications()` tạo options tắt những kiểm tra bổ sung được đăng ký mặc định:

```java
VerificationOptions options = VerificationOptions.defaults()
        .withoutAdditionalVerifications();

ApplicationModules.of(ShopApplication.class).verify(options);
```

Trường hợp này có thể hữu ích khi nhóm cần cô lập một lần kiểm tra để chẩn đoán hoặc khi chưa muốn áp dụng các quy tắc tích hợp bổ sung. Tuy nhiên, nó không bỏ qua các quy tắc cốt lõi của Spring Modulith.

Không nên dùng phương thức này như cách xử lý lâu dài cho một lỗi kiến trúc. Nếu một quy tắc bổ sung báo lỗi, hãy đọc violation, xác định lớp vi phạm và quyết định quy tắc đó có thực sự phù hợp với kiến trúc dự án hay không.

## 7. So sánh ba phương thức tùy chỉnh

| Phương thức | Tác động đến kiểm tra bổ sung mặc định | Khi nên dùng |
|---|---|---|
| `andAdditionalVerifications(rule)` | Giữ và bổ sung thêm | Muốn thêm ArchRule riêng nhưng vẫn giữ jMolecules hoặc các rule mặc định |
| `withAdditionalVerifications(rule)` | Thay thế tập bổ sung mặc định bằng tập được truyền vào | Muốn tự định nghĩa toàn bộ nhóm kiểm tra bổ sung |
| `withoutAdditionalVerifications()` | Tắt nhóm bổ sung được đăng ký mặc định | Chỉ muốn chạy các quy tắc cốt lõi của Spring Modulith trong một lần kiểm tra có chủ đích |

Đừng nhầm `withAdditionalVerifications(...)` với `andAdditionalVerifications(...)`. Khác biệt giữa “thay thế” và “bổ sung” có thể khiến một bộ kiểm tra DDD hoặc kiến trúc riêng biến mất nếu chọn nhầm phương thức.

## 8. Dùng options với ApplicationModules.verify()

Một bài kiểm tra JUnit có thể tập trung cấu hình options tại một chỗ:

```java
package com.example.shop;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class ModularityTests {

    private static final ArchRule WEB_MUST_NOT_ACCESS_PERSISTENCE = noClasses()
            .that().resideInAPackage("..orders.web..")
            .should().dependOnClassesThat()
            .resideInAPackage("..orders.persistence..");

    @Test
    void verifiesModuleStructureAndProjectRules() {
        VerificationOptions options = VerificationOptions.defaults()
                .andAdditionalVerifications(WEB_MUST_NOT_ACCESS_PERSISTENCE);

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
```

Test này kết hợp kiểm tra module của Spring Modulith với quy tắc layering của dự án. Khi một lớp web phụ thuộc trực tiếp vào repository, ArchUnit rule bổ sung sẽ phát hiện vi phạm. Khi một module truy cập package nội bộ của module khác hoặc tạo chu trình, các quy tắc cốt lõi của Spring Modulith sẽ phát hiện vấn đề tương ứng.

ArchUnit rule trong ví dụ dùng package pattern. Hãy điều chỉnh pattern theo cấu trúc thực tế của dự án và giữ phạm vi đủ hẹp để rule diễn đạt đúng một nguyên tắc kiến trúc có ý nghĩa.

## 9. Lấy danh sách violations để xử lý chi tiết

`verify(options)` là cách ngắn gọn để thực thi kiểm tra và làm test thất bại khi phát hiện vi phạm. Nếu muốn truy cập các vi phạm để phân tích hoặc lọc, hãy dùng `detectViolations(options)`:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

var violations = modules.detectViolations(options);

violations.throwIfPresent();
```

`detectViolations(...)` trả về `Violations` để xử lý tiếp. Có thể dùng kết quả đó khi cần hiển thị báo cáo, lọc một số vi phạm theo chính sách hoặc quyết định khi nào cần gọi `throwIfPresent()`.

Hai phương thức có một khác biệt về việc thực thi:

- `verify(options)` thực hiện verification nếu lần kiểm tra chưa được chạy trên instance `ApplicationModules` đó.
- `detectViolations(options)` luôn thực hiện lại các kiểm tra và trả về kết quả, kể cả khi trước đó đã gọi `verify()`.

Vì vậy, nếu muốn đánh giá lại cùng một mô hình với options khác sau khi đã gọi `verify()`, hãy tạo một `ApplicationModules` mới hoặc gọi `detectViolations(options)` để buộc chạy lại.

## 10. VerificationOptions không phải công cụ loại module hoặc dependency

Một số API khác cũng ảnh hưởng đến quá trình phân tích, nhưng có mục đích riêng:

| API/cấu hình | Mục đích |
|---|---|
| `VerificationOptions` | Tùy chỉnh các kiểm tra bổ sung khi verification chạy |
| `ApplicationModules.of(Class, DescribedPredicate)` | Bỏ qua type hoặc package khỏi application module inspection |
| `@ApplicationModule(allowedDependencies = …)` | Khai báo module nguồn được phép phụ thuộc vào module/named interface nào |
| `@ApplicationModule(type = Type.OPEN)` | Nới lỏng quy tắc truy cập sub-package nội bộ của module được mở |
| `ApplicationModules.verify()` | Chạy các quy tắc verification trên mô hình module |

Nếu một dependency bị cấm bởi `allowedDependencies`, thêm `VerificationOptions` không tự cho phép dependency đó. Nếu một type nằm trong package nội bộ, options cũng không tự biến package đó thành API. Hãy thay đổi cấu trúc hoặc metadata module nếu muốn thay đổi boundary; chỉ dùng options để tùy chỉnh các kiểm tra bổ sung.

## 11. Chọn cách cấu hình phù hợp

Hãy chọn phương thức dựa trên mục tiêu:

1. **Chỉ cần kiểm tra module mặc định:** gọi `ApplicationModules.of(...).verify()`.
2. **Muốn giữ các kiểm tra mặc định và thêm quy tắc riêng:** dùng `VerificationOptions.defaults().andAdditionalVerifications(...)`.
3. **Muốn thay thế nhóm kiểm tra bổ sung mặc định:** dùng `withAdditionalVerifications(...)` và ghi rõ lý do trong test hoặc cấu hình.
4. **Muốn tạm tắt các kiểm tra bổ sung mặc định để chẩn đoán:** dùng `withoutAdditionalVerifications()` trong phạm vi kiểm tra có chủ đích.
5. **Muốn phân tích vi phạm thay vì dừng ngay:** dùng `detectViolations(options)` và xử lý đối tượng `Violations`.

Với hầu hết dự án, lựa chọn an toàn để mở rộng bộ kiểm tra là `defaults().andAdditionalVerifications(...)`. Cách này giữ các quy tắc bổ sung đã có trên classpath và thêm các nguyên tắc riêng của nhóm. Chỉ thay thế hoặc tắt chúng khi nhóm hiểu rõ những kiểm tra nào sẽ không còn chạy.

Tài liệu tham khảo: [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html), [VerificationOptions Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html), [ApplicationModules Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html).

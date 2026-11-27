# Giữ options dùng chung giữa các test

Khi một dự án có nhiều bài kiểm tra kiến trúc, mỗi test có thể cần chạy cùng một bộ quy tắc để xác nhận cấu trúc module. Nếu từng test tự tạo cấu hình riêng, các quy tắc dễ bị lệch nhau: test này kiểm tra thêm một ràng buộc, test khác lại quên áp dụng. Spring Modulith cung cấp `VerificationOptions` để gom các kiểm tra bổ sung vào một cấu hình có thể tái sử dụng.

Từ Spring Modulith 1.4, `ApplicationModules` hỗ trợ cả `verify(VerificationOptions)` và `detectViolations(VerificationOptions)`. Ta có thể khai báo options một lần trong mã nguồn test rồi truyền cùng cấu hình đó vào nhiều bài kiểm tra.

## 1. Phân biệt kiểm tra module và options

`ApplicationModules.of(Application.class)` đọc cấu trúc package từ lớp ứng dụng và tạo mô hình các application module. Khi gọi `verify()`, Spring Modulith kiểm tra những ràng buộc cốt lõi như:

- Các module không phụ thuộc vòng tròn lẫn nhau.
- Module chỉ truy cập API được công khai của module khác; việc truy cập package nội bộ sẽ bị phát hiện theo quy tắc module.
- Nếu module khai báo `allowedDependencies`, các phụ thuộc phải tuân theo danh sách cho phép.

Nếu thư viện jMolecules có mặt trên classpath, Spring Modulith còn có thể áp dụng các kiểm tra kiến trúc bổ sung do tích hợp này cung cấp. `VerificationOptions` cho phép tùy chỉnh nhóm kiểm tra bổ sung đó và đăng ký thêm các quy tắc ArchUnit của dự án.

Điểm cần nhớ là options bổ sung chính sách kiểm tra cho lần xác minh. Chúng không thay thế việc tạo mô hình module và cũng không biến các quy tắc ranh giới module cốt lõi thành một bộ quy tắc tùy chọn riêng.

## 2. Khai báo một cấu hình dùng chung

Đặt cấu hình trong mã nguồn test, tại một package dễ được các test kiến trúc truy cập. Ví dụ dưới đây định nghĩa quy tắc rằng lớp thuộc package `web` không được phụ thuộc trực tiếp vào package `persistence`:

```java
package com.example.architecture;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;
import org.springframework.modulith.core.VerificationOptions;

public final class ModulithVerification {

    private static final ArchRule WEB_MUST_NOT_DEPEND_ON_PERSISTENCE =
            noClasses()
                    .that().resideInAPackage("..web..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..persistence..");

    public static final VerificationOptions OPTIONS =
            VerificationOptions.defaults()
                    .andAdditionalVerifications(WEB_MUST_NOT_DEPEND_ON_PERSISTENCE);

    private ModulithVerification() {}
}
```

`OPTIONS` được khởi tạo một lần khi lớp hỗ trợ được nạp. Tất cả test dùng cùng hằng số này sẽ chạy cùng chính sách. Quy tắc ví dụ chỉ minh họa cách ghép ArchUnit vào bộ xác minh; hãy thay các package `web` và `persistence` bằng cấu trúc thực tế của ứng dụng.

Ta dùng `andAdditionalVerifications(…)` để thêm quy tắc của dự án vào những kiểm tra bổ sung mặc định. Cách này giữ lại các kiểm tra jMolecules mặc định nếu chúng được kích hoạt trên classpath.

## 3. Dùng cùng options trong nhiều test

Mỗi test tạo `ApplicationModules` từ lớp ứng dụng rồi truyền cấu hình dùng chung vào `verify(…)`:

```java
package com.example.architecture;

import com.example.Application;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationArchitectureTests {

    @Test
    void applicationModulesFollowTheSharedPolicy() {
        ApplicationModules.of(Application.class)
                .verify(ModulithVerification.OPTIONS);
    }
}
```

Một test ở lớp khác có thể sử dụng đúng cấu hình đó:

```java
package com.example.order;

import com.example.Application;
import com.example.architecture.ModulithVerification;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class OrderArchitectureTests {

    @Test
    void applicationModulesFollowTheSamePolicy() {
        ApplicationModules.of(Application.class)
                .verify(ModulithVerification.OPTIONS);
    }
}
```

Nếu các test nằm ở package khác, lớp hỗ trợ và hằng số `OPTIONS` cần có phạm vi truy cập phù hợp, chẳng hạn `public`. Với ví dụ trên, hãy đặt `Application` ở package gốc của ứng dụng và bổ sung import đúng package trong từng lớp test.

Việc dùng chung options giúp mọi test áp dụng cùng một tập quy tắc. Khi cần thay đổi chính sách, ta cập nhật một nơi thay vì tìm và sửa từng lời gọi `verify()`.

## 4. Chọn đúng phương thức cấu hình

`VerificationOptions` có bốn phương thức cấu hình thường gặp. Chúng có ý nghĩa khác nhau:

| Phương thức | Ý nghĩa | Khi nên dùng |
|---|---|---|
| `defaults()` | Tạo options mặc định, bao gồm kiểm tra jMolecules nếu thư viện tương ứng có trên classpath. | Bắt đầu từ cấu hình mặc định của Spring Modulith. |
| `andAdditionalVerifications(…)` | Thêm các `ArchRule` vào nhóm kiểm tra bổ sung mặc định. | Muốn bổ sung quy tắc riêng mà vẫn giữ các kiểm tra bổ sung mặc định. |
| `withAdditionalVerifications(…)` | Định nghĩa nhóm kiểm tra bổ sung cần chạy và thay thế nhóm mặc định. | Muốn tự chỉ định toàn bộ nhóm kiểm tra bổ sung. |
| `withoutAdditionalVerifications()` | Tắt nhóm kiểm tra bổ sung được đăng ký mặc định. | Chỉ dùng khi chủ động muốn bỏ các kiểm tra bổ sung đó. |

Ví dụ, hai cách cấu hình sau không tương đương:

```java
// Giữ các kiểm tra bổ sung mặc định rồi thêm quy tắc riêng.
VerificationOptions keepDefaults = VerificationOptions.defaults()
        .andAdditionalVerifications(myArchitectureRule);

// Chỉ dùng quy tắc được truyền vào, thay thế nhóm kiểm tra bổ sung mặc định.
VerificationOptions replaceDefaults = VerificationOptions.defaults()
        .withAdditionalVerifications(myArchitectureRule);
```

Các phương thức trên điều chỉnh nhóm kiểm tra bổ sung. Khi gọi `ApplicationModules.verify(options)`, Spring Modulith vẫn thực hiện quy trình xác minh cấu trúc module của nó.

## 5. Khi cần đọc kết quả thay vì dừng ngay

`verify(options)` ném lỗi khi phát hiện vi phạm. Nếu muốn nhận đối tượng `Violations` để lọc hoặc xử lý kết quả trước, dùng `detectViolations(options)`:

```java
var violations = ApplicationModules.of(Application.class)
        .detectViolations(ModulithVerification.OPTIONS);

violations.throwIfPresent();
```

`detectViolations(…)` luôn thực hiện xác minh mỗi khi được gọi. Trong khi đó, `verify(…)` chỉ thực hiện xác minh nếu lần xác minh chưa được chạy trên instance `ApplicationModules` đó. Vì vậy, nếu cần chạy lại cùng một mô hình với các options khác nhau để so sánh kết quả, hãy dùng `detectViolations(…)` hoặc tạo instance mô hình mới cho từng lần xác minh.

## 6. Lưu ý khi chia sẻ options

- Khởi tạo cấu hình ở một lớp hỗ trợ test và giữ nó ổn định sau khi các test bắt đầu sử dụng. Không tiếp tục gọi các phương thức thay đổi options sau khi đã chia sẻ hằng số đó.
- Nếu mỗi test cần một tập quy tắc khác nhau, tạo cấu hình riêng cho từng mục đích. Không thêm quy tắc theo điều kiện chạy của test vào một options dùng chung.
- Dùng `andAdditionalVerifications(…)` khi muốn giữ các kiểm tra bổ sung mặc định. Dùng `withAdditionalVerifications(…)` khi chủ ý thay thế chúng.
- `VerificationOptions` có từ Spring Modulith 1.4. Hãy kiểm tra phiên bản dependency nếu IDE không tìm thấy lớp hoặc phương thức này.
- Ví dụ dùng ArchUnit, vì vậy test cần có ArchUnit trên test classpath. Dependency thường đã được cung cấp khi dự án dùng starter test tương ứng của Spring Modulith; nếu không, hãy khai báo dependency phù hợp theo cấu hình dự án.

## 7. Bài tập áp dụng

1. Tạo lớp hỗ trợ `ModulithVerification` trong source set test.
2. Khai báo một `ArchRule` phản ánh quy ước thật của dự án, chẳng hạn lớp ở tầng giao tiếp không được gọi trực tiếp repository.
3. Tạo `VerificationOptions` từ `defaults()` và thêm quy tắc bằng `andAdditionalVerifications(…)`.
4. Cho ít nhất hai lớp test gọi `ApplicationModules.of(Application.class).verify(ModulithVerification.OPTIONS)`.
5. Tạm tạo một phụ thuộc vi phạm để xác nhận các test cùng phát hiện lỗi, sau đó khôi phục mã nguồn.

Kết quả mong đợi là mọi test kiến trúc dùng chung một chính sách xác minh. Khi chính sách thay đổi, toàn bộ test nhận cùng cập nhật và không còn phải duy trì các cấu hình rời rạc.

## Tài liệu tham khảo

- [Verifying Application Module Structure – Spring Modulith](https://docs.spring.io/spring-modulith/reference/verification.html)
- [VerificationOptions API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)

# verify() chạy một lần so với detectViolations()

Bài này thuộc chương **Verification** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp mô hình hóa các application module trong ứng dụng Spring Boot và kiểm tra xem cấu trúc package, API công khai cùng quan hệ phụ thuộc có tuân thủ các quy tắc kiến trúc đã chọn hay không.

Hai phương thức `ApplicationModules.verify()` và `ApplicationModules.detectViolations()` cùng thực hiện các kiểm tra kiến trúc, nhưng có cách xử lý kết quả và chính sách thực thi khác nhau. **`verify()` tránh chạy lại verification trên cùng instance sau khi đã thực hiện; `detectViolations()` luôn chạy verification và trả về đối tượng `Violations` để nhóm đọc, lọc hoặc quyết định có ném lỗi hay không.**

## 1. Hai phương thức phục vụ hai nhu cầu khác nhau

Thông thường, nhóm muốn một bài test kiến trúc thất bại ngay khi phát hiện vi phạm. Khi đó, `verify()` là lựa chọn ngắn gọn:

~~~java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules.of(Application.class).verify();
~~~

Nếu cần thu thập kết quả để phân tích, in thông báo, lọc một số trường hợp đã được chấp thuận hoặc tự quyết định thời điểm ném lỗi, hãy dùng `detectViolations()`:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violations;

ApplicationModules modules = ApplicationModules.of(Application.class);

Violations violations = modules.detectViolations();

if (violations.hasViolations()) {
    violations.getMessages().forEach(System.out::println);
}
~~~

Sự khác nhau không nằm ở việc một phương thức có kiểm tra kiến trúc còn phương thức kia không. Cả hai đều chạy các verification được cấu hình cho mô hình application module. Điểm khác biệt nằm ở việc `verify()` dùng chính sách chạy một lần trên instance, còn `detectViolations()` luôn thực thi lại và trả kết quả có thể xử lý tiếp.

## 2. verify() chạy một lần trên cùng ApplicationModules instance

Javadoc mô tả `verify()` là thực thi các verification cần áp dụng, trừ khi chúng đã được thực hiện trước đó. Điều này có nghĩa việc chạy một lần được gắn với instance `ApplicationModules` đang sử dụng.

Ví dụ:

~~~java
ApplicationModules modules = ApplicationModules.of(Application.class);

modules.verify(); // Thực hiện verification lần đầu.
modules.verify(); // Không thực hiện lại trên cùng instance.
~~~

Cách dùng này phù hợp khi cùng một đối tượng mô hình được nhiều đoạn test hoặc helper sử dụng và nhóm không muốn lặp lại chi phí phân tích kiến trúc.

Cần hiểu đúng phạm vi của chính sách này:

- Đây không phải một cờ toàn cục khiến toàn bộ JVM chỉ kiểm tra một lần.
- Tạo instance mới bằng `ApplicationModules.of(...)` sẽ tạo một đối tượng mô hình mới; lần gọi `verify()` trên instance mới có thể thực hiện verification.
- Gọi `detectViolations()` vẫn chạy lại verification, kể cả khi instance đó đã được gọi `verify()` trước đó.
- `verify()` ném exception nếu phát hiện vi phạm; khi không có vi phạm, phương thức trả về một `ApplicationModules` để có thể nối tiếp lời gọi.

Do đó, không nên diễn giải “chạy một lần” thành “mỗi ứng dụng chỉ kiểm tra một lần trong suốt vòng đời”. Hãy hiểu là phương thức tránh thực thi lặp lại trên cùng mô hình sau khi verification đã được thực hiện.

## 3. detectViolations() luôn thực hiện verification

Khác với `verify()`, phương thức `detectViolations()` được thiết kế để luôn chạy các verification và trả về `Violations`.

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violations;

ApplicationModules modules = ApplicationModules.of(Application.class);

Violations first = modules.detectViolations();
Violations second = modules.detectViolations();
~~~

Hai lời gọi trên đều thực hiện verification. Mỗi kết quả `Violations` mô tả các vi phạm được phát hiện trong lần chạy tương ứng.

Điều này hữu ích khi nhóm cần:

- Chạy lại kiểm tra một cách tường minh.
- Thu thập danh sách vi phạm mà không ném exception ngay lập tức.
- In hoặc ghi log thông báo để hỗ trợ chẩn đoán.
- Lọc một số vi phạm đã được xem xét và chấp thuận.
- Kết hợp kết quả verification với logic kiểm tra riêng của test.

Nếu chỉ cần bảo đảm không có vi phạm, có thể gọi `throwIfPresent()` trên kết quả:

~~~java
ApplicationModules.of(Application.class)
        .detectViolations()
        .throwIfPresent();
~~~

Cách này thực hiện verification và ném chính đối tượng `Violations` nếu kết quả không rỗng.

## 4. Đối tượng Violations cung cấp những gì?

`Violations` là kiểu kết quả dùng để tập hợp và báo cáo các vi phạm kiến trúc. Đây cũng là một runtime exception, vì vậy có thể ném nó khi nhóm muốn test hoặc luồng xử lý thất bại.

Một số phương thức thường dùng:

| Phương thức | Mục đích |
|---|---|
| `hasViolations()` | Kiểm tra có vi phạm nào được phát hiện hay không. |
| `getMessages()` | Lấy danh sách thông báo vi phạm dưới dạng `List<String>`. |
| `getMessage()` | Lấy thông báo tổng hợp. |
| `filter(Predicate<Violation>)` | Tạo kết quả chỉ gồm các vi phạm khớp predicate. |
| `throwIfPresent()` | Ném `Violations` nếu kết quả còn vi phạm. |

Ví dụ thu thập và hiển thị tất cả thông báo:

~~~java
Violations violations = ApplicationModules.of(Application.class)
        .detectViolations();

if (!violations.hasViolations()) {
    System.out.println("No module architecture violations found.");
} else {
    violations.getMessages().forEach(message ->
            System.err.println("Architecture violation: " + message)
    );
}
~~~

Cách này giúp nhóm xem nhiều lỗi trong cùng một lần chạy và hiểu rõ module nguồn, module đích hoặc package liên quan trước khi quyết định cách sửa.

## 5. verify() phù hợp với bài test kiến trúc thông thường

Trong phần lớn dự án, mục tiêu của test kiến trúc là làm build thất bại nếu module vi phạm ranh giới đã thiết kế. Vì vậy, `verify()` thường là lựa chọn dễ đọc nhất:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Nếu có vi phạm, test thất bại với thông tin từ exception. Nhóm có thể xử lý nguyên nhân bằng cách:

- Loại bỏ dependency không hợp lệ.
- Chuyển kiểu được chia sẻ sang API công khai hoặc named interface phù hợp.
- Cập nhật `allowedDependencies` khi quan hệ phụ thuộc là chủ đích.
- Phá chu trình giữa các module.
- Điều chỉnh package/module detection nếu ranh giới được nhận diện không đúng.

Không cần tự kiểm tra `hasViolations()` sau `verify()`, vì phương thức đã thể hiện chính sách fail-fast bằng cách ném exception khi phát hiện vi phạm.

## 6. detectViolations() phù hợp với chẩn đoán và xử lý kết quả

Khi đang làm sạch một codebase legacy, nhóm có thể muốn xem toàn bộ vi phạm trước khi quyết định cách xử lý. `detectViolations()` cho phép tách hai bước: chạy kiểm tra và xử lý kết quả.

Ví dụ:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violations;

class ModuleArchitectureReport {

    Violations inspect() {
        return ApplicationModules.of(Application.class)
                .detectViolations();
    }

    void printReport() {
        Violations violations = inspect();

        if (violations.hasViolations()) {
            violations.getMessages().forEach(System.out::println);
        }
    }
}
~~~

Có thể dùng kết quả này để:

- Tạo báo cáo tổng hợp trong test.
- In thông báo theo từng lần chạy.
- Đếm số vi phạm trước và sau một đợt refactor.
- Phân loại thông báo theo module hoặc nội dung.
- Chỉ ném lỗi sau khi đã áp dụng chính sách lọc được nhóm thống nhất.

Hãy nhớ rằng việc thu thập kết quả không đồng nghĩa với việc chấp nhận mọi vi phạm. Nếu đây là test CI, cuối cùng cần một điều kiện rõ ràng để build thất bại khi còn vi phạm không được chấp thuận.

## 7. Lọc vi phạm có chủ đích

`Violations.filter(...)` trả về một tập kết quả mới chỉ gồm các vi phạm khớp predicate. Nhóm có thể giữ lại những vi phạm chưa được miễn trừ rồi gọi `throwIfPresent()`.

Ví dụ, trong giai đoạn migration, nhóm đã chấp thuận tạm thời một vi phạm có thông báo chứa mã tham chiếu cụ thể:

~~~java
ApplicationModules modules = ApplicationModules.of(Application.class);

modules.detectViolations()
        .filter(violation ->
                !violation.getMessage().contains("LEGACY-ARCH-001"))
        .throwIfPresent();
~~~

Predicate trên giữ lại các vi phạm không chứa mã `LEGACY-ARCH-001`. Nếu còn vi phạm nào khác, `throwIfPresent()` sẽ ném exception.

Trong thực tế, lọc theo một đoạn thông báo có thể mong manh nếu wording thay đổi giữa các phiên bản. Hãy giới hạn phạm vi miễn trừ, ghi lý do và thời điểm xem xét lại. Không nên lọc bỏ toàn bộ kết quả chỉ để làm test xanh.

Một quy tắc miễn trừ tốt cần trả lời:

- Vi phạm nào được chấp thuận tạm thời?
- Ai chịu trách nhiệm xử lý?
- Vì sao chưa thể sửa ngay?
- Khi nào cần xóa ngoại lệ?
- Những vi phạm mới có tiếp tục làm test thất bại không?

## 8. Kết hợp với VerificationOptions

Cả `verify()` và `detectViolations()` đều có overload nhận `VerificationOptions`. Các tùy chọn này cho phép điều chỉnh những verification được áp dụng, ví dụ bổ sung quy tắc kiến trúc hoặc thay đổi tập verification mặc định.

Ví dụ:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

VerificationOptions options = VerificationOptions.defaults();

ApplicationModules modules = ApplicationModules.of(Application.class);

modules.verify(options);

// Hoặc thu thập kết quả theo cùng options:
var violations = modules.detectViolations(options);
~~~

Khi dùng options, hãy bảo đảm test và báo cáo đang áp dụng cùng một bộ quy tắc nếu mục tiêu là so sánh kết quả. Nếu hai lần chạy sử dụng cấu hình khác nhau, số lượng hoặc loại vi phạm có thể khác nhau do chính sách verification đã thay đổi.

Overload nhận `VerificationOptions` của `verify(options)` cũng tuân theo nguyên tắc không thực thi lại trên cùng instance khi verification đã được thực hiện trước đó. `detectViolations(options)` vẫn luôn chạy.

## 9. So sánh hai phương thức

| Tiêu chí | `verify()` | `detectViolations()` |
|---|---|---|
| Có chạy verification? | Có, nếu instance chưa thực hiện trước đó. | Luôn chạy. |
| Kết quả trả về | `ApplicationModules` nếu không có vi phạm. | `Violations`. |
| Khi có vi phạm | Ném exception. | Trả về tập vi phạm; chưa tự ném cho tới khi gọi `throwIfPresent()`. |
| Xử lý kết quả | Phù hợp với test yêu cầu kiến trúc hợp lệ và thất bại khi có vi phạm. | Có thể đọc message, kiểm tra, lọc và xử lý. |
| Gọi lại trên cùng instance | Không chạy lại nếu đã verification trước đó. | Chạy lại mỗi lần gọi. |
| Trường hợp sử dụng | Test kiến trúc thông thường, CI. | Chẩn đoán, báo cáo, lọc ngoại lệ có kiểm soát. |

Có thể ghi nhớ bằng hai câu:

- `verify()`: kiểm tra và thất bại ngay nếu mô hình vi phạm, đồng thời tránh lặp lại kiểm tra trên cùng instance.
- `detectViolations()`: chạy kiểm tra mỗi lần gọi và trao quyền xử lý tập vi phạm cho code của nhóm.

## 10. Tránh hiểu nhầm về cache và thay đổi code

Việc `verify()` không chạy lại trên cùng instance không phải cơ chế theo dõi file thay đổi hoặc tự cập nhật mô hình. `ApplicationModules` là mô hình được xây dựng từ các lớp/package mà nó nhập tại thời điểm tạo.

Nếu nhóm thay đổi code rồi cần kiểm tra lại, cần bảo đảm quá trình build/test đã biên dịch lại các lớp liên quan và tạo mô hình phù hợp với code mới. Trong một tiến trình test, không nên giả định instance cũ tự phát hiện thay đổi trên file system.

Một số nguyên tắc thực tế:

- Dùng instance mới khi cần xây dựng lại mô hình từ một classpath/build output mới.
- Dùng `detectViolations()` khi muốn chủ động chạy lại verification trên instance hiện tại.
- Không dùng kết quả cũ để kết luận code vừa thay đổi đã hợp lệ.
- Giữ mỗi test có mục tiêu rõ ràng và tránh chia sẻ instance mutable giữa nhiều test không liên quan.

## 11. Quy trình chọn phương thức trong test và CI

1. **Xác định mục tiêu.** Nếu chỉ cần bảo vệ kiến trúc và làm test thất bại khi có lỗi, ưu tiên `verify()`.
2. **Cần xem chi tiết?** Dùng `detectViolations()` để lấy đối tượng `Violations`.
3. **Đọc kết quả.** Kiểm tra `hasViolations()`, `getMessages()` hoặc `getMessage()`.
4. **Có ngoại lệ được chấp thuận?** Dùng `filter(...)` với điều kiện hẹp, có lý do và người chịu trách nhiệm.
5. **Giữ kiểm tra bắt buộc cho lỗi còn lại.** Gọi `throwIfPresent()` sau khi lọc để test vẫn thất bại nếu còn vi phạm.
6. **Cần quy tắc riêng?** Truyền cùng `VerificationOptions` cho phương thức phù hợp.
7. **Đưa vào CI.** Chạy test kiến trúc thường xuyên để thay đổi package hoặc dependency được phát hiện sớm.

## 12. Ví dụ test kiểm tra và báo cáo

Một test dùng `verify()` cho chính sách fail-fast:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleVerificationTests {

    @Test
    void moduleStructureMustBeValid() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Một test dùng `detectViolations()` để kiểm tra và hiển thị thông báo:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violations;

class ModuleViolationReportTests {

    @Test
    void reportsModuleViolations() {
        Violations violations = ApplicationModules.of(Application.class)
                .detectViolations();

        assertFalse(
                violations.hasViolations(),
                () -> violations.getMessage()
        );
    }
}
~~~

Cả hai test đều kiểm tra cấu trúc module. Test đầu dùng exception do `verify()` phát ra; test thứ hai chủ động lấy kết quả và đưa thông báo vào assertion của JUnit.

## Ghi nhớ

`verify()` thực thi verification nếu instance `ApplicationModules` chưa kiểm tra trước đó; nếu có vi phạm, nó ném exception. `detectViolations()` luôn chạy verification và trả về `Violations`, cho phép đọc message, lọc kết quả hoặc gọi `throwIfPresent()` theo chính sách của nhóm.

Dùng `verify()` cho test kiến trúc thông thường và CI. Dùng `detectViolations()` khi cần chẩn đoán, báo cáo hoặc xử lý ngoại lệ có kiểm soát. Khi cần kiểm tra lại sau thay đổi, hãy tạo mô hình mới từ build output phù hợp hoặc gọi `detectViolations()` trên instance hiện tại, thay vì kỳ vọng `verify()` chạy lặp lại.

## Tài liệu tham khảo

- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith — Violations API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/Violations.html)
- [Spring Modulith — Violation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/Violation.html)

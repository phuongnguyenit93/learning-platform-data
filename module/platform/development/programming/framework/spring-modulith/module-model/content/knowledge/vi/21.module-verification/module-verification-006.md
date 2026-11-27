# detectViolations() trả về tập vi phạm

Khi kiểm tra kiến trúc một ứng dụng Spring Modulith, nhóm có thể cần biết toàn bộ lỗi đang tồn tại để hiển thị báo cáo, phân loại hoặc xử lý theo từng nhóm. Trong trường hợp đó, `ApplicationModules.detectViolations()` trả về một đối tượng `Violations` chứa các vi phạm được phát hiện, thay vì dừng luồng kiểm tra bằng exception ngay tại lời gọi như `verify()`.

`detectViolations()` giúp tách hai việc: phát hiện vấn đề kiến trúc và quyết định cách ứng dụng xử lý kết quả. Ta có thể kiểm tra xem có vi phạm hay không, lấy danh sách thông điệp, lọc một số vi phạm cần quan tâm hoặc chủ động ném exception nếu muốn kiểm tra theo kiểu fail-fast.

## 1. Từ mô hình module đến kết quả kiểm tra

Spring Modulith xây dựng mô hình application module từ package và metadata của ứng dụng. Mô hình đó chứa các module, API được công bố, package nội bộ và dependency giữa các module.

Ví dụ, một ứng dụng bán hàng có các module:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   └── internal
│       └── PlaceOrderService.java
├── inventory
│   ├── InventoryManagement.java
│   └── internal
│       └── StockRepository.java
└── payment
    ├── PaymentManagement.java
    └── internal
        └── PaymentRepository.java
~~~

Các quy tắc kiến trúc có thể yêu cầu:

- Module chỉ truy cập API được công bố của module khác.
- Dependency phải tuân thủ danh sách `allowedDependencies`.
- Các module không tạo dependency cycle.
- Các package nội bộ không bị module khác tham chiếu trái phép.

Khi kiểm tra mô hình, Spring Modulith có thể phát hiện nhiều vi phạm. `detectViolations()` tập hợp chúng để chương trình có thể xem xét kết quả trước khi quyết định bước tiếp theo.

## 2. Gọi detectViolations()

Tạo mô hình từ lớp ứng dụng rồi gọi phương thức:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violations;

class ModuleArchitectureReport {

    void inspect() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        Violations violations = modules.detectViolations();

        if (violations.hasViolations()) {
            violations.getMessages().forEach(System.err::println);
        } else {
            System.out.println("Không phát hiện vi phạm kiến trúc.");
        }
    }
}
~~~

`ApplicationModules.of(ShopApplication.class)` tạo mô hình module từ ứng dụng. `detectViolations()` thực hiện các bước kiểm chứng được cấu hình và trả về một đối tượng `Violations`.

Đối tượng này luôn được trả về. Nếu không có lỗi, nó biểu diễn một tập vi phạm rỗng. Vì vậy, hãy dùng `hasViolations()` để kiểm tra trạng thái thay vì dựa vào việc phương thức có trả về `null` hay không.

## 3. Violations chứa những gì?

`Violations` là một kiểu kết quả trong package `org.springframework.modulith.core`. Nó kế thừa `RuntimeException`, đồng thời cung cấp các phương thức để đọc và xử lý tập lỗi.

| Phương thức | Mục đích |
| --- | --- |
| `hasViolations()` | Cho biết tập kết quả có ít nhất một vi phạm hay không |
| `getMessages()` | Trả về danh sách thông điệp của tất cả vi phạm |
| `getMessage()` | Trả về thông điệp tổng hợp của đối tượng |
| `filter(Predicate<Violation>)` | Tạo một tập `Violations` chỉ chứa các vi phạm thỏa điều kiện |
| `throwIfPresent()` | Ném chính đối tượng `Violations` nếu tập có ít nhất một vi phạm |

Mỗi phần tử được lọc có kiểu `Violation`. Kiểu này đại diện cho một vi phạm riêng lẻ và cung cấp:

- `getMessage()` để lấy thông điệp.
- `hasMessageContaining(String)` để kiểm tra thông điệp có chứa một đoạn văn bản hay không.

Ví dụ đọc toàn bộ thông điệp:

~~~java
Violations violations =
        ApplicationModules.of(ShopApplication.class).detectViolations();

for (String message : violations.getMessages()) {
    System.out.println(message);
}
~~~

`getMessages()` hữu ích khi cần ghi log, tạo báo cáo CI hoặc hiển thị danh sách lỗi trong công cụ nội bộ. Nội dung thông điệp giúp người phát triển xác định module, kiểu hoặc dependency cần xem xét.

## 4. Phân biệt detectViolations() và verify()

Hai phương thức thực hiện kiểm chứng kiến trúc nhưng phục vụ cách xử lý kết quả khác nhau:

| Tiêu chí | `detectViolations()` | `verify()` |
| --- | --- | --- |
| Kết quả | Trả về `Violations` | Trả về `ApplicationModules` nếu kiểm tra thành công |
| Khi có vi phạm | Trả về tập lỗi để chương trình xử lý | Ném exception |
| Khi không có vi phạm | Trả về tập rỗng | Hoàn tất bình thường |
| Đọc thông điệp | Có thể lấy qua `getMessages()` | Thông điệp nằm trong exception nếu kiểm tra thất bại |
| Lọc lỗi trước khi xử lý | Có `filter(...)` | Không cung cấp tập lỗi để lọc tại lời gọi |
| Lần gọi lặp lại | Luôn thực thi kiểm tra | Chỉ thực thi nếu chưa được kiểm tra trước đó |

Ví dụ dùng `verify()` theo kiểu kiểm tra trực tiếp:

~~~java
ApplicationModules.of(ShopApplication.class).verify();
~~~

Nếu có vi phạm, lời gọi này ném exception và test thường thất bại ngay tại đó.

Ví dụ dùng `detectViolations()` để quyết định cách xử lý:

~~~java
Violations violations =
        ApplicationModules.of(ShopApplication.class).detectViolations();

if (violations.hasViolations()) {
    // Có thể ghi log, lọc, hiển thị hoặc chuyển thành exception.
}
~~~

Một điểm khác biệt đáng chú ý là `detectViolations()` luôn chạy lại các kiểm tra. Theo API, `verify()` thực thi kiểm tra nếu chúng chưa được thực hiện trước đó. Điều này hữu ích khi muốn chủ động lấy kết quả mới trong một quy trình báo cáo hoặc chẩn đoán.

## 5. Lọc vi phạm bằng filter()

Đôi khi một báo cáo có nhiều lỗi thuộc nhiều module. Ta có thể lọc các lỗi có thông điệp nhắc đến một module hoặc một package cụ thể.

Ví dụ:

~~~java
Violations allViolations =
        ApplicationModules.of(ShopApplication.class).detectViolations();

Violations inventoryViolations = allViolations.filter(
        violation -> violation.hasMessageContaining("inventory")
);

if (inventoryViolations.hasViolations()) {
    inventoryViolations.getMessages().forEach(System.err::println);
}
~~~

`filter()` nhận một `Predicate<Violation>` và trả về một `Violations` mới chỉ gồm các phần tử phù hợp. Đối tượng ban đầu vẫn có thể được dùng để xem toàn bộ kết quả.

Có thể lọc theo một đoạn thông điệp khác:

~~~java
Violations packageViolations = allViolations.filter(
        violation -> violation.getMessage().contains(".internal.")
);
~~~

Trong thực tế, thông điệp lỗi là dữ liệu chẩn đoán. Không nên xây dựng logic nghiệp vụ lâu dài dựa trên toàn bộ câu chữ hoặc định dạng thông điệp vì nội dung có thể thay đổi giữa các phiên bản. Hãy dùng lọc theo thông điệp để hỗ trợ báo cáo và điều tra; quy tắc kiến trúc cốt lõi vẫn nên được thể hiện bằng cấu hình module và kiểm thử tương ứng.

## 6. Chỉ ném exception khi thực sự cần

Sau khi thu thập hoặc lọc vi phạm, có thể chủ động yêu cầu chương trình dừng bằng `throwIfPresent()`:

~~~java
ApplicationModules modules =
        ApplicationModules.of(ShopApplication.class);

Violations violations = modules.detectViolations();

violations.throwIfPresent();
~~~

Nếu tập có vi phạm, `throwIfPresent()` ném chính đối tượng `Violations`. Nếu tập rỗng, phương thức kết thúc bình thường.

Cách này hữu ích khi muốn thực hiện thêm bước ghi log hoặc tạo báo cáo trước khi làm test thất bại:

~~~java
Violations violations =
        ApplicationModules.of(ShopApplication.class).detectViolations();

if (violations.hasViolations()) {
    violations.getMessages().forEach(System.err::println);
}

violations.throwIfPresent();
~~~

Khi dùng trong CI, test vẫn thất bại nếu có lỗi, nhưng log đã có thể chứa danh sách thông điệp để nhóm xử lý.

## 7. Lọc trước khi ném exception

Có thể chỉ muốn một bước kiểm tra quan tâm đến một nhóm vi phạm nhất định. Ví dụ, một báo cáo phụ chỉ theo dõi các dependency đi vào package `internal`:

~~~java
Violations internalAccessViolations =
        ApplicationModules.of(ShopApplication.class)
                .detectViolations()
                .filter(violation ->
                        violation.hasMessageContaining(".internal."));

internalAccessViolations.throwIfPresent();
~~~

Điều này chỉ làm cho tập được ném chứa các vi phạm phù hợp bộ lọc. Các vi phạm khác vẫn có trong kết quả ban đầu nếu ta còn giữ tham chiếu đến nó.

Không nên dùng bộ lọc để vô tình bỏ qua lỗi kiến trúc trong kiểm thử chính. Nếu mục tiêu của test là bảo đảm toàn bộ ứng dụng tuân thủ ranh giới module, hãy gọi `throwIfPresent()` trên toàn bộ tập kết quả. Lọc chỉ phù hợp khi phạm vi kiểm tra đã được xác định rõ và các lỗi ngoài phạm vi được xử lý ở một bước khác.

## 8. Viết kiểm thử kiến trúc với kết quả Violations

Một test đơn giản có thể xác nhận ứng dụng không có vi phạm:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void reportsNoArchitecturalViolations() {
        var violations =
                ApplicationModules.of(ShopApplication.class).detectViolations();

        assertThat(violations.hasViolations()).isFalse();
    }
}
~~~

Nếu muốn test thất bại bằng exception có sẵn của Spring Modulith, có thể viết:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class)
                .detectViolations()
                .throwIfPresent();
    }
}
~~~

Test thứ hai dùng `detectViolations()` để lấy kết quả rồi chuyển kết quả thành lỗi test nếu tập không rỗng. Cách này cho phép bổ sung log hoặc báo cáo trước khi gọi `throwIfPresent()`.

Với một test kiểm tra bộ lọc, hãy tạo tình huống kiến trúc có chủ đích trong fixture hoặc dùng kết quả từ một mô hình thử nghiệm riêng. Không nên làm hỏng package sản phẩm chỉ để tạo lỗi cho test.

## 9. Tùy chỉnh phạm vi kiểm chứng bằng VerificationOptions

`ApplicationModules` cung cấp overload `detectViolations(VerificationOptions)` để chạy kiểm tra theo tùy chọn đã cấu hình:

~~~java
import com.tngtech.archunit.lang.ArchRule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

class CustomModuleVerification {

    void verify() {
        var modules = ApplicationModules.of(ShopApplication.class);

        ArchRule noLegacyClasses = noClasses()
                .should().resideInAPackage("..legacy..");

        var options = VerificationOptions.defaults()
                .andAdditionalVerifications(noLegacyClasses);

        var violations = modules.detectViolations(options);
        violations.throwIfPresent();
    }
}
~~~

`VerificationOptions.defaults()` tạo bộ tùy chọn mặc định và đưa các kiểm tra jMolecules vào nếu thư viện đó có trên classpath. Ví dụ trên bổ sung một ArchRule riêng bằng `andAdditionalVerifications(...)`.

`withAdditionalVerifications(...)` dùng để chỉ định tập kiểm tra bổ sung thay cho tập mặc định; `withoutAdditionalVerifications()` tắt các kiểm tra bổ sung được đăng ký mặc định. Chọn cách cấu hình theo phạm vi dự án và giữ bộ quy tắc nhất quán giữa môi trường phát triển và CI.

Khi không có nhu cầu tùy chỉnh, dùng `detectViolations()` mặc định là đủ. Không nên thêm các tùy chọn chỉ để làm mất một vi phạm đang tồn tại; hãy xác định nguyên nhân và sửa ranh giới hoặc dependency tương ứng.

## 10. Ví dụ quy trình báo cáo trong CI

Một bước kiểm tra kiến trúc có thể thực hiện theo luồng:

~~~text
Khởi tạo ApplicationModules
          |
          v
Gọi detectViolations()
          |
          v
Kiểm tra hasViolations()
      /         \
    Không        Có
     |            |
     v            v
  Báo PASS     Lấy getMessages()
                  |
                  v
              Ghi log/báo cáo
                  |
                  v
            throwIfPresent()
                  |
                  v
              Test thất bại
~~~

Ví dụ mã:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violations;

class ArchitectureReportTest {

    @Test
    void printsAllModuleViolationsBeforeFailing() {
        Violations violations =
                ApplicationModules.of(ShopApplication.class).detectViolations();

        if (violations.hasViolations()) {
            System.err.println("Phát hiện vi phạm kiến trúc:");
            violations.getMessages().forEach(System.err::println);
        }

        violations.throwIfPresent();
    }
}
~~~

Kết quả log có thể được CI lưu lại để người phát triển xem các vi phạm sau khi build thất bại. Với hệ thống báo cáo riêng, `getMessages()` có thể được chuyển thành nội dung JSON hoặc danh sách hiển thị; việc định dạng đó thuộc trách nhiệm của công cụ tích hợp.

## 11. Những giới hạn cần hiểu đúng

`detectViolations()` giúp thu thập kết quả từ các quy tắc verification của Spring Modulith, nhưng không phải một bộ phân tích mọi lỗi có thể xảy ra trong ứng dụng.

- Nó kiểm tra cấu trúc và dependency module theo mô hình cùng tùy chọn đã cấu hình.
- Nó không chứng minh logic nghiệp vụ đúng.
- Nó không thay thế kiểm thử Spring application context, tích hợp database hoặc kiểm thử API.
- Nó không tự sửa package, dependency hay metadata.
- Nó không đảm bảo mọi vấn đề runtime đều được phát hiện.
- Nội dung `Violation` chủ yếu được trình bày qua thông điệp; không nên coi câu chữ là mã lỗi ổn định để điều khiển nghiệp vụ.

Nếu jMolecules hoặc các tích hợp verification khác có mặt trên classpath, các quy tắc bổ sung có thể được thực hiện theo cấu hình mặc định. Khi cần kiểm soát chính xác phạm vi, hãy xem xét `VerificationOptions` và tài liệu của phiên bản Spring Modulith mà dự án đang sử dụng.

## 12. Những nhầm lẫn thường gặp

**Cho rằng `detectViolations()` trả về `null` khi không có lỗi.** Phương thức luôn trả về `Violations`. Dùng `hasViolations()` để xác định tập có rỗng hay không.

**Cho rằng `detectViolations()` tự ném exception ngay khi tìm thấy lỗi.** Phương thức thu thập kết quả. Chương trình có thể đọc và lọc chúng trước; `throwIfPresent()` mới ném nếu tập không rỗng.

**Cho rằng `verify()` và `detectViolations()` giống nhau hoàn toàn.** Cả hai thực hiện kiểm chứng, nhưng cách xử lý kết quả và hành vi khi gọi lặp lại khác nhau.

**Chỉ đọc `getMessage()` rồi bỏ qua danh sách lỗi.** `getMessages()` giúp xử lý từng thông điệp riêng, dễ ghi log và tạo báo cáo hơn.

**Lọc mọi lỗi không mong muốn để test luôn xanh.** Lọc chỉ có ý nghĩa khi phạm vi kiểm tra được chủ ý giới hạn. Nếu test nhằm bảo vệ toàn bộ kiến trúc, hãy xử lý toàn bộ tập vi phạm.

**Dùng thông điệp lỗi như một API nghiệp vụ ổn định.** Thông điệp được tạo để chẩn đoán. Không nên phụ thuộc vào toàn bộ câu chữ hoặc định dạng của nó qua nhiều phiên bản.

**Cho rằng kiểm tra kiến trúc thay thế mọi test khác.** Module có thể tuân thủ dependency nhưng vẫn có lỗi nghiệp vụ, lỗi cấu hình hoặc lỗi tích hợp. Hãy kết hợp các loại kiểm thử phù hợp.

## 13. Checklist sử dụng detectViolations()

- [ ] Tạo mô hình bằng `ApplicationModules.of(...)` với lớp ứng dụng hoặc package gốc phù hợp.
- [ ] Gọi `detectViolations()` để thực thi các kiểm tra và thu thập kết quả.
- [ ] Dùng `hasViolations()` để xác định có lỗi hay không.
- [ ] Dùng `getMessages()` để đọc toàn bộ thông điệp.
- [ ] Dùng `filter(...)` khi cần báo cáo một nhóm lỗi có phạm vi rõ.
- [ ] Gọi `throwIfPresent()` nếu cần biến tập lỗi thành exception.
- [ ] Dùng overload nhận `VerificationOptions` khi dự án cần tùy chỉnh quy tắc.
- [ ] Tránh dựa vào nội dung thông điệp như mã lỗi ổn định.
- [ ] Giữ kiểm thử kiến trúc trong CI để phát hiện vi phạm sớm.

## 14. Kết luận

`ApplicationModules.detectViolations()` cho phép ứng dụng thực thi các kiểm tra kiến trúc và nhận lại kết quả dưới dạng `Violations`. Từ kết quả này, nhóm có thể kiểm tra `hasViolations()`, đọc `getMessages()`, lọc bằng `filter(...)` và chủ động ném exception bằng `throwIfPresent()`.

Hãy dùng `detectViolations()` khi cần kiểm soát cách báo cáo và xử lý lỗi. Dùng `verify()` khi muốn một lệnh kiểm tra trực tiếp theo kiểu fail-fast. Dù chọn cách nào, mục tiêu vẫn là đưa các quy tắc module vào kiểm thử tự động để dependency sai, truy cập package nội bộ hoặc các vi phạm kiến trúc khác được phát hiện trước khi thay đổi đi xa hơn.

## Tài liệu tham khảo

- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — `ApplicationModules` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith — `Violations` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/Violations.html)
- [Spring Modulith — `Violation` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/Violation.html)
- [Spring Modulith — `VerificationOptions` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)

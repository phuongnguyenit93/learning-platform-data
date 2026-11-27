# verify() ném exception khi có vi phạm

`ApplicationModules.verify()` là điểm kiểm tra các quy tắc kiến trúc của Spring Modulith. Khi mô hình module có vi phạm, phương thức này ném `org.springframework.modulith.core.Violations`. Đây là một exception kế thừa `RuntimeException`, chứa thông tin về các vi phạm được phát hiện. Vì vậy, một kiểm thử gọi `verify()` sẽ thất bại ngay tại lời gọi nếu cấu trúc module không đáp ứng quy tắc.

Điều này biến quy ước kiến trúc thành một điều kiện có thể kiểm tra tự động trong test và build. Thay vì chỉ nhìn dependency graph rồi tự đánh giá, nhóm phát triển có thể để Spring Modulith phát hiện chu trình, truy cập package nội bộ hoặc phụ thuộc ngoài danh sách cho phép.

## 1. Gọi verify() để xác nhận mô hình module

Tạo mô hình từ lớp Spring Boot application rồi gọi `verify()`:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.verify();
```

Nếu không có vi phạm, `verify()` trả về chính `ApplicationModules` để có thể tiếp tục sử dụng mô hình. Nếu có vi phạm kiến trúc, phương thức ném `Violations` và luồng thực thi tại lời gọi bị dừng, trừ khi exception được xử lý ở phía gọi.

Trong dự án thực tế, nên đặt lệnh này trong một architecture test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleVerificationTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

JUnit đánh dấu test là failed nếu `Violations` thoát khỏi phương thức test. Khi chạy trong Gradle hoặc Maven, lỗi test sẽ làm task kiểm thử thất bại và có thể chặn pipeline CI.

## 2. Exception cụ thể là Violations

`Violations` không phải tên gọi chung cho mọi lỗi của ứng dụng. Đây là kiểu exception riêng của Spring Modulith, có khai báo kế thừa `RuntimeException` và dùng để tập hợp các vi phạm kiến trúc.

API cung cấp các phương thức hữu ích:

| API | Ý nghĩa |
|---|---|
| `getMessage()` | Thông điệp tổng hợp của exception |
| `getMessages()` | Danh sách thông điệp của từng vi phạm |
| `hasViolations()` | Cho biết tập hợp có vi phạm hay không |
| `filter(predicate)` | Tạo tập hợp mới chỉ gồm các vi phạm khớp điều kiện |
| `throwIfPresent()` | Ném chính exception nếu tập hợp còn vi phạm |

Một lần kiểm tra có thể phát hiện nhiều vấn đề. `Violations` gom chúng vào một kết quả để developer xem được nhiều nguyên nhân trong cùng một lần chạy, thay vì phải sửa lần lượt từng lỗi chỉ vì lần kiểm tra đầu tiên dừng sớm.

## 3. Những quy tắc verify() kiểm tra

Spring Modulith kiểm tra các quy tắc chính sau trên mô hình module đã phát hiện:

| Quy tắc | Ví dụ vi phạm |
|---|---|
| Không có chu trình phụ thuộc giữa các module | `orders` phụ thuộc `catalog`, đồng thời `catalog` phụ thuộc ngược `orders` |
| Module chỉ truy cập API được công khai của module khác | `orders` import type từ `catalog.internal` trong khi `catalog` là module `CLOSED` |
| Tuân thủ `allowedDependencies` nếu được khai báo | `orders` chỉ cho phép `catalog` nhưng code lại tham chiếu `customers` |

Với quy tắc truy cập API, package gốc và named interface là các bề mặt được công khai theo cấu hình module. Package nội bộ của module `CLOSED` không được module khác tham chiếu. Module `OPEN` có quy tắc truy cập nội bộ rộng hơn theo cấu hình của nó.

`allowedDependencies` là tùy chọn. Nếu module không khai báo allowlist, quy tắc giới hạn phụ thuộc theo danh sách không được áp dụng cho module đó. Khi đã khai báo, các phụ thuộc tới module khác phải khớp các entry được cho phép. Các quy tắc shared module và named interface vẫn được xử lý theo metadata tương ứng.

Nếu thư viện jMolecules ArchUnit có trên classpath, Spring Modulith còn tự động chạy các quy tắc xác minh kiến trúc và Domain-Driven Design mà integration đó cung cấp. Vì vậy, kết quả có thể bao gồm kiểm tra bổ sung tùy dependency của dự án.

## 4. Hiểu điều gì xảy ra khi verify() ném exception

Giả sử module `orders` được phép dùng API của `catalog`, nhưng một class lại import implementation nội bộ:

```java
package com.acme.shop.orders;

import com.acme.shop.catalog.internal.ProductRepository;
import org.springframework.stereotype.Service;

@Service
class OrderQuery {

    private final ProductRepository repository;

    OrderQuery(ProductRepository repository) {
        this.repository = repository;
    }
}
```

Java có thể biên dịch đoạn code nếu `ProductRepository` và constructor tương ứng có khả năng truy cập phù hợp. Nhưng khả năng truy cập theo ngôn ngữ Java không đồng nghĩa với quyền phụ thuộc giữa application module. Khi chạy:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Spring Modulith phát hiện `orders` truy cập package nội bộ của `catalog` và ném `Violations`. Test architecture thất bại, chỉ ra rằng code đang vượt qua ranh giới API đã thiết lập.

Một số nguyên nhân thường gặp khác:

- Một module thêm dependency mới nhưng không cập nhật `allowedDependencies`.
- Một thay đổi package khiến type công khai chuyển vào package nội bộ hoặc ngược lại.
- Hai module bắt đầu tham chiếu lẫn nhau và tạo chu trình.
- Một named interface bị đổi tên nhưng module tiêu thụ vẫn tham chiếu cấu hình cũ.

Exception cho biết kiểm tra kiến trúc thất bại. Nó không tự sửa dependency hoặc quyết định module nào nên sở hữu hợp đồng. Developer cần truy lại source code, xác định hướng phụ thuộc mong muốn rồi điều chỉnh package, API hoặc cấu hình module.

## 5. Lấy danh sách vi phạm mà không ném ngay

Nếu cần hiển thị hoặc xử lý các vi phạm trước khi quyết định ném exception, dùng `detectViolations()` thay cho `verify()`:

```java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violations;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

Violations violations = modules.detectViolations();

if (violations.hasViolations()) {
    violations.getMessages().forEach(System.err::println);
    violations.throwIfPresent();
}
```

`detectViolations()` trả về `Violations` kể cả khi không có lỗi. Khi không có vi phạm, `hasViolations()` trả về `false` và `throwIfPresent()` không ném exception. Khi có lỗi, `getMessages()` cho phép ghi lại từng thông điệp trước khi ném.

Một điểm khác biệt quan trọng: `detectViolations()` luôn thực hiện lại các bước kiểm tra. `verify()` chỉ thực hiện kiểm tra nếu chúng chưa được chạy trước đó trên instance `ApplicationModules` đó. Khi cần chủ động chạy lại sau khi thay đổi điều kiện hoặc khi đang thử nghiệm bộ lọc, dùng `detectViolations()`.

## 6. Lọc vi phạm trước khi throwIfPresent()

`Violations.filter(...)` cho phép chỉ giữ lại những vi phạm cần xử lý theo một chính sách cụ thể. Ví dụ sau giữ lại các vi phạm có thông điệp nhắc đến module `orders`:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.detectViolations()
        .filter(violation -> violation.hasMessageContaining("orders"))
        .throwIfPresent();
```

`filter()` không sửa cấu trúc module và cũng không làm cho vi phạm biến mất khỏi codebase. Nó chỉ tạo một tập hợp kết quả đã lọc. Nếu predicate loại bỏ một vi phạm, `throwIfPresent()` sẽ không ném exception cho vi phạm đã bị loại.

Chỉ nên lọc khi có chính sách rõ ràng, chẳng hạn một nhóm vi phạm đã được chấp thuận tạm thời trong quá trình migration. Không nên lọc chỉ để làm test xanh, vì như vậy pipeline không còn bảo vệ đúng ranh giới kiến trúc. Hãy ghi lại lý do, phạm vi và điều kiện loại bỏ ngoại lệ tạm thời.

## 7. Tùy chỉnh VerificationOptions

`verify()` và `detectViolations()` có overload nhận `VerificationOptions`. Options cho phép điều chỉnh các bước kiểm tra bổ sung được chạy theo classpath và đăng ký thêm quy tắc kiến trúc.

Ví dụ tài liệu Spring Modulith sử dụng quy tắc Hexagonal Architecture của jMolecules:

```java
var hexagonal = JMoleculesArchitectureRules.ensureHexagonal(
        VerificationDepth.STRICT);

var options = VerificationOptions.defaults()
        .withAdditionalVerifications(hexagonal);

ApplicationModules.of(ShopApplication.class).verify(options);
```

Ví dụ này yêu cầu dependency jMolecules phù hợp và các import tương ứng. Nếu dự án không dùng jMolecules, có thể dùng `VerificationOptions.defaults()` và các quy tắc kiểm tra module tiêu chuẩn của Spring Modulith.

Khi thay đổi options, hãy xác định rõ bạn đang bổ sung, thay thế hay tắt một bước xác minh. Tùy chỉnh quá rộng có thể khiến một số kiểm tra mặc định không còn chạy. Hãy kiểm tra API và tài liệu của đúng phiên bản Spring Modulith mà dự án đang sử dụng.

## 8. Đưa verify() vào quy trình phát triển

Một architecture test nhỏ có thể chạy cùng unit test và được thực thi ở mọi pull request:

```text
Developer thay đổi code
        │
        ▼
Architecture test gọi ApplicationModules.verify()
        │
        ├── Không có vi phạm ──> Test PASS ──> CI tiếp tục
        │
        └── Có vi phạm ────────> Violations ──> Test FAIL ──> CI dừng
```

Nên đặt test trong source set test thông thường để build tool tự chạy. Khi test thất bại, đọc toàn bộ thông điệp của `Violations`, nhóm lỗi theo module nguồn và module đích, rồi sửa nguyên nhân ở package hoặc hợp đồng API.

Quy trình xử lý thực tế:

1. Chạy lại architecture test để thu thông điệp mới nhất.
2. Xác định quy tắc bị vi phạm: chu trình, truy cập internal hay `allowedDependencies`.
3. Tìm type nguồn và type đích liên quan trong code.
4. Quyết định giữ dependency, công khai hợp đồng bằng named interface, chuyển sang event hoặc đảo lại quyền sở hữu.
5. Cập nhật package/API/metadata tương ứng.
6. Chạy lại `verify()` và các test nghiệp vụ liên quan.

Không nên bắt `Violations` rồi bỏ qua trong architecture test. Nếu test bắt exception để kiểm tra một trường hợp vi phạm có chủ đích, assertion phải xác nhận đúng exception và đúng thông điệp hoặc điều kiện vi phạm cần kiểm tra.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `verify()` chỉ trả về boolean | Nó trả về `ApplicationModules` khi thành công và ném `Violations` khi có vi phạm |
| Mỗi vi phạm tạo một exception riêng | `Violations` là tập hợp exception tổng hợp nhiều vi phạm kiến trúc |
| `Violations` là checked exception | Đây là subclass của `RuntimeException` |
| `detectViolations()` tự ném exception ngay | Nó trả về tập hợp; gọi `throwIfPresent()` nếu muốn ném khi còn lỗi |
| `verify()` luôn chạy lại mọi kiểm tra | `verify()` bỏ qua lần chạy nếu kiểm tra đã được thực hiện trên instance; `detectViolations()` luôn chạy |
| Code compile được nghĩa là verify() sẽ thành công | Java compiler không kiểm tra đầy đủ ranh giới application module |
| Bắt exception là đã xử lý vi phạm | Phải sửa cấu trúc hoặc có chính sách ngoại lệ được kiểm soát |
| Test architecture thành công chứng minh nghiệp vụ đúng | Nó kiểm tra quy tắc kiến trúc, không thay thế unit test hoặc integration test nghiệp vụ |

## 10. Checklist khi xử lý Violations

- [ ] Architecture test gọi `ApplicationModules.of(...).verify()`.
- [ ] Khi test fail, đã đọc toàn bộ `Violations.getMessages()`.
- [ ] Đã phân loại lỗi theo chu trình, truy cập API/internal hoặc `allowedDependencies`.
- [ ] Đã xác định module nguồn, module đích và type liên quan.
- [ ] Đã sửa nguyên nhân ở package, hợp đồng hoặc metadata module.
- [ ] Nếu dùng `detectViolations().filter(...)`, đã ghi rõ lý do và phạm vi của predicate.
- [ ] Không bắt và bỏ qua `Violations` trong pipeline kiểm tra kiến trúc.
- [ ] Đã chạy lại architecture test sau khi sửa.

`verify()` ném `Violations` là cơ chế phản hồi rõ ràng khi code không còn tuân thủ ranh giới module. Kết hợp architecture test với `detectViolations()` khi cần chẩn đoán giúp nhóm phát hiện lỗi sớm, hiểu nguyên nhân và giữ các quy tắc kiến trúc có hiệu lực trong CI.

## Tài liệu tham khảo

- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Violations API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/Violations.html)
- [Violation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/Violation.html)
- [VerificationOptions API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)

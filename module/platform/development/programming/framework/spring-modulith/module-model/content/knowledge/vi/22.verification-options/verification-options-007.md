# Chọn options theo mục tiêu dự án

Khi dùng Spring Modulith, lời gọi `ApplicationModules.of(Application.class).verify()` đã kiểm tra những ràng buộc cốt lõi của cấu trúc mô-đun. Trong dự án thực tế, nhóm có thể cần thêm quy tắc kiến trúc riêng, chẳng hạn yêu cầu lớp giao diện không truy cập trực tiếp tầng lưu trữ hoặc yêu cầu mã nguồn tuân thủ kiến trúc lục giác. Khi đó, ta chọn `VerificationOptions` dựa trên mục tiêu kiểm tra của dự án.

Mục tiêu của bài học là biết khi nào nên giữ cấu hình mặc định, khi nào cần bổ sung hoặc thay thế các kiểm tra mở rộng, và khi nào nên thu thập vi phạm để xử lý có kiểm soát. Các API `VerificationOptions` và `ApplicationModules.verify(VerificationOptions)` có từ Spring Modulith 1.4.

## 1. Bắt đầu từ các quy tắc cấu trúc mặc định

Trước khi tùy chỉnh, cần hiểu `verify()` đã bảo vệ những điều gì. Spring Modulith kiểm tra các ràng buộc chính sau:

- Không có chu trình phụ thuộc giữa các application module. Đồ thị phụ thuộc mô-đun phải là đồ thị có hướng không chu trình.
- Mô-đun chỉ được tham chiếu API công khai của mô-đun khác. Việc truy cập kiểu nằm trong package nội bộ của mô-đun khác bị từ chối; quy tắc có ngoại lệ đối với các mô-đun được khai báo là open theo cơ chế của Spring Modulith.
- Nếu mô-đun khai báo `allowedDependencies`, các phụ thuộc phải nằm trong danh sách được cho phép.

Ngoài các quy tắc cấu trúc này, Spring Modulith có thể chạy thêm các kiểm tra của jMolecules khi thư viện jMolecules tương ứng có trên classpath. Đây là nhóm kiểm tra mở rộng phụ thuộc cấu hình classpath.

Nếu mục tiêu của dự án chỉ là giữ ranh giới mô-đun, API công khai và chiều phụ thuộc đúng như thiết kế, hãy bắt đầu bằng cấu hình mặc định:

```java
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    void verifyModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

Đặt lời gọi này trong một bài kiểm tra kiến trúc được chạy ở CI. Khi phát hiện vi phạm, `verify()` ném ngoại lệ để làm thất bại bài kiểm tra và giúp nhóm sửa nguyên nhân trước khi hợp nhất thay đổi.

Không cần tạo `VerificationOptions` chỉ để bật kiểm tra chu trình mô-đun, quyền truy cập package nội bộ hoặc `allowedDependencies`. Đây là các quy tắc cấu trúc cơ bản mà Spring Modulith đã thực hiện.

## 2. Phân biệt bổ sung, thay thế và tắt kiểm tra mở rộng

`VerificationOptions` tùy chỉnh nhóm kiểm tra mở rộng được đăng ký mặc định, ví dụ các kiểm tra jMolecules khi thư viện có mặt. Ba lựa chọn quan trọng có ý nghĩa khác nhau:

| API | Hành vi | Khi nên chọn |
|---|---|---|
| `VerificationOptions.defaults()` | Tạo cấu hình mặc định; bao gồm kiểm tra jMolecules nếu các thư viện tương ứng có trên classpath. | Muốn dùng hành vi mặc định một cách tường minh trước khi điều chỉnh. |
| `andAdditionalVerifications(...)` | Giữ các kiểm tra mở rộng mặc định và đăng ký thêm `ArchRule`. | Dự án muốn giữ kiểm tra hiện có, đồng thời áp dụng quy tắc riêng. |
| `withAdditionalVerifications(...)` | Dùng danh sách `ArchRule` truyền vào thay cho nhóm kiểm tra mở rộng được đăng ký mặc định. | Dự án chủ động quản lý một bộ kiểm tra mở rộng riêng và muốn thay thế bộ mặc định. |
| `withoutAdditionalVerifications()` | Tắt các kiểm tra mở rộng được đăng ký mặc định. | Chỉ dùng khi nhóm đã đánh giá tác động và có lý do rõ ràng để bỏ nhóm kiểm tra đó. |

Điểm dễ nhầm là `withAdditionalVerifications` có chữ “Additional” trong tên nhưng hành vi là thay thế các kiểm tra mở rộng mặc định. Nếu muốn giữ kiểm tra mặc định và nối thêm quy tắc riêng, hãy dùng `andAdditionalVerifications`.

Các tùy chọn trên không xóa những kiểm tra cấu trúc mô-đun cốt lõi của Spring Modulith. Việc tắt kiểm tra mở rộng không đồng nghĩa với việc tắt toàn bộ `ApplicationModules.verify()`.

## 3. Chọn cấu hình theo mục tiêu dự án

### Dự án cần một hàng rào kiến trúc cơ bản

Với ứng dụng mới hoặc modular monolith đã có ranh giới tương đối rõ, trước tiên hãy dùng `verify()` không tham số. Cách này dễ đọc, ít cấu hình và giúp nhóm nhận ra những lỗi quan trọng: phụ thuộc vòng, truy cập package nội bộ và phụ thuộc không được cho phép.

Chỉ mở rộng khi nhóm xác định được một quy tắc bổ sung có ý nghĩa nghiệp vụ hoặc kỹ thuật. Việc thêm nhiều quy tắc chỉ để tăng số lượng kiểm tra có thể làm bộ kiểm tra khó bảo trì và tạo ra cảnh báo không hữu ích.

### Dự án cần giữ mặc định và bổ sung quy tắc riêng

Giả sử hệ thống có các package `web` và `persistence`. Nhóm muốn mọi lớp trong `web` đi qua lớp nghiệp vụ thay vì phụ thuộc trực tiếp vào `persistence`. Đây là quy tắc phân lớp của dự án, có thể diễn đạt bằng ArchUnit `ArchRule`:

```java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class ModularityTests {

    private static final ArchRule webMustNotAccessPersistence = noClasses()
            .that().resideInAPackage("..web..")
            .should().dependOnClassesThat()
            .resideInAPackage("..persistence..");

    void verifyModuleStructure() {
        var options = VerificationOptions.defaults()
                .andAdditionalVerifications(webMustNotAccessPersistence);

        ApplicationModules.of(Application.class).verify(options);
    }
}
```

Trong ví dụ này, `andAdditionalVerifications` bảo toàn các kiểm tra mở rộng mặc định rồi bổ sung quy tắc phân lớp. Mẫu package trong `resideInAPackage` phải khớp với cấu trúc package thật của ứng dụng; hãy điều chỉnh `..web..` và `..persistence..` theo quy ước của dự án.

Một số quy tắc riêng khác có thể phù hợp với mục tiêu của nhóm:

- Package giao tiếp HTTP không được gọi trực tiếp adapter truy cập dữ liệu.
- Module nghiệp vụ không được phụ thuộc vào package cấu hình triển khai.
- Thành phần dùng chung chỉ được phụ thuộc vào các module nền tảng đã thống nhất.
- Các adapter bên ngoài phải tuân thủ hướng phụ thuộc đã chọn trong kiến trúc lục giác.

Mỗi quy tắc nên mô tả một quyết định kiến trúc có thể giải thích được. Nếu quy tắc đã được Spring Modulith bảo vệ thông qua ranh giới mô-đun, hãy cân nhắc tránh tạo thêm một kiểm tra trùng lặp.

### Dự án muốn thay thế bộ kiểm tra mở rộng mặc định

Một nhóm có thể muốn dùng một bộ quy tắc jMolecules được lựa chọn rõ ràng, ví dụ kiểm tra kiến trúc lục giác. Khi chủ đích là thay thế nhóm kiểm tra mở rộng mặc định, cấu hình có thể viết như sau:

```java
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class ModularityTests {

    void verifyHexagonalArchitecture() {
        var hexagonal = JMoleculesArchitectureRules.ensureHexagonal();

        var options = VerificationOptions.defaults()
                .withAdditionalVerifications(hexagonal);

        ApplicationModules.of(Application.class).verify(options);
    }
}
```

`withAdditionalVerifications` thay thế nhóm kiểm tra mở rộng được đăng ký mặc định bằng quy tắc `hexagonal` ở trên. Vì vậy, hãy chọn nó khi nhóm thực sự muốn quản lý bộ kiểm tra mở rộng theo cách này. Nếu mục tiêu là giữ mọi kiểm tra mặc định rồi thêm kiểm tra lục giác, hãy đổi sang `andAdditionalVerifications(hexagonal)`.

Kiểu `JMoleculesArchitectureRules` và phương thức `ensureHexagonal()` chỉ dùng được khi dự án đã khai báo dependency jMolecules ArchUnit cung cấp chúng. Nếu dependency chưa có, cần bổ sung đúng thư viện và phiên bản tương thích với Spring Modulith của dự án trước khi biên dịch ví dụ.

### Dự án cần tắt kiểm tra mở rộng tự động

Trong một số dự án cũ, classpath có thể chứa thư viện khiến kiểm tra mở rộng được kích hoạt tự động dù nhóm chưa sẵn sàng áp dụng các quy tắc đó. Nếu đã đánh giá và quyết định tắt riêng nhóm kiểm tra mở rộng, có thể dùng:

```java
var options = VerificationOptions.defaults()
        .withoutAdditionalVerifications();

ApplicationModules.of(Application.class).verify(options);
```

Chỉ chọn cách này khi nhóm hiểu rõ những kiểm tra nào bị tắt và có kế hoạch thay thế phù hợp nếu chúng đang bảo vệ một quyết định kiến trúc quan trọng. Trong dự án cần kiểm soát kiến trúc lâu dài, nên ưu tiên sửa classpath hoặc cấu hình bộ quy tắc rõ ràng để tránh việc một dependency vô tình thay đổi kết quả kiểm tra.

## 4. Chọn `verify()` hay `detectViolations()`

Mục tiêu tiếp theo là quyết định cách xử lý kết quả kiểm tra:

| Nhu cầu | API phù hợp | Kết quả |
|---|---|---|
| Muốn kiểm tra và làm bài test thất bại ngay khi có vi phạm | `verify()` hoặc `verify(options)` | Ném ngoại lệ khi phát hiện vi phạm. |
| Muốn lấy danh sách vi phạm để phân loại, ghi log hoặc lọc ngoại lệ đã được chấp thuận | `detectViolations()` hoặc `detectViolations(options)` | Trả về `Violations` để xử lý tiếp. |
| Muốn luôn chạy lại kiểm tra khi cần đánh giá một bộ options khác | `detectViolations(options)` | Thực thi kiểm tra mỗi lần gọi. |

`verify()` và `verify(options)` thực hiện các kiểm tra trừ khi việc xác minh đã được thực hiện trước đó trên instance `ApplicationModules`. Ngược lại, `detectViolations()` và `detectViolations(options)` luôn thực thi kiểm tra. Vì vậy, khi một luồng kiểm tra cần thử nhiều cấu hình hoặc cần thu thập kết quả lặp lại, `detectViolations(options)` thể hiện ý định rõ hơn.

Ví dụ: trong giai đoạn chuyển đổi một hệ thống cũ, nhóm muốn thu thập vi phạm trước khi quyết định chặn build. Có thể lấy kết quả rồi xử lý những ngoại lệ đã được xem xét:

```java
var violations = ApplicationModules.of(Application.class)
        .detectViolations(options);

violations
        .filter(violation -> !isApprovedTemporaryException(violation))
        .throwIfPresent();
```

`isApprovedTemporaryException` là hàm do dự án tự định nghĩa để nhận diện ngoại lệ có chủ sở hữu, lý do và thời hạn xử lý. Không nên lọc bỏ vi phạm chỉ để làm build xanh; mỗi ngoại lệ cần được ghi nhận và xem xét lại.

## 5. Quy trình ra quyết định

Có thể dùng quy trình sau khi thiết kế bộ kiểm tra kiến trúc cho một dự án:

```mermaid
flowchart TD
    A[ Xác định mục tiêu kiểm tra ] --> B{Chỉ cần quy tắc mô-đun cốt lõi?}
    B -->|Có| C[Dùng ApplicationModules.verify()]
    B -->|Không| D{Có cần giữ kiểm tra mở rộng mặc định?}
    D -->|Có| E[Dùng defaults().andAdditionalVerifications(...)]
    D -->|Không, muốn thay thế| F[Dùng defaults().withAdditionalVerifications(...)]
    D -->|Không, muốn tắt| G[Dùng defaults().withoutAdditionalVerifications()]
    C --> H{Cần xử lý danh sách vi phạm?}
    E --> H
    F --> H
    G --> H
    H -->|Không, cần fail-fast| I[Gọi verify(options)]
    H -->|Có, cần phân loại hoặc lọc| J[Gọi detectViolations(options)]
```

Quy trình này giúp nhóm trả lời ba câu hỏi trước khi viết cấu hình:

1. Quy tắc cần kiểm tra đã thuộc nhóm kiểm tra cấu trúc cốt lõi của Spring Modulith chưa?
2. Nếu là kiểm tra mở rộng, nhóm muốn giữ, thay thế hay tắt các kiểm tra được đăng ký mặc định?
3. Khi có vi phạm, build phải thất bại ngay hay nhóm cần lấy danh sách để xử lý có kiểm soát?

## 6. Tổ chức cấu hình để CI nhất quán

Khi bộ quy tắc lớn dần, hãy gom cấu hình vào một phương thức hoặc lớp kiểm tra kiến trúc dùng chung. Các test không nên tự tạo những bộ `VerificationOptions` khác nhau mà không có lý do, vì cùng một commit có thể được đánh giá theo các tiêu chuẩn không đồng nhất.

Ví dụ, có thể tách phần tạo options thành một phương thức:

```java
static VerificationOptions projectVerificationOptions() {
    return VerificationOptions.defaults()
            .andAdditionalVerifications(webMustNotAccessPersistence);
}
```

Sau đó dùng cùng cấu hình trong bài kiểm tra kiến trúc:

```java
@Test
void applicationModulesShouldRespectArchitecture() {
    ApplicationModules.of(Application.class)
            .verify(projectVerificationOptions());
}
```

Để CI cung cấp phản hồi ổn định, nhóm nên:

- Chạy kiểm tra kiến trúc cùng vòng đời kiểm thử tự động của dự án.
- Đặt tên quy tắc theo hành vi bị cấm hoặc quyết định kiến trúc mà nó bảo vệ.
- Giải thích lý do khi thay thế hoặc tắt kiểm tra mở rộng mặc định.
- Xem xét lại ngoại lệ tạm thời và xóa chúng khi nguyên nhân đã được khắc phục.
- Kiểm tra dependency jMolecules trên classpath khi kết quả kiểm tra thay đổi ngoài dự kiến.

## 7. Những lỗi lựa chọn thường gặp

| Lựa chọn chưa phù hợp | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Tạo options cho mọi dự án dù chỉ cần kiểm tra ranh giới mô-đun | Tăng cấu hình mà không tăng giá trị kiểm tra | Bắt đầu bằng `verify()` mặc định. |
| Dùng `withAdditionalVerifications` trong khi muốn giữ các kiểm tra mở rộng mặc định | Các kiểm tra mặc định bị thay thế | Dùng `andAdditionalVerifications`. |
| Tắt kiểm tra mở rộng vì một lỗi khó sửa | Có thể bỏ qua quy tắc kiến trúc quan trọng | Xác định nguồn lỗi, sửa dependency hoặc bổ sung bộ quy tắc thay thế có chủ đích. |
| Dùng `verify()` rồi mong lần gọi tiếp theo trên cùng instance luôn chạy lại với options khác | Lần kiểm tra có thể không được thực thi lại | Dùng `detectViolations(options)` khi cần thực thi mỗi lần. |
| Lọc bỏ vi phạm mà không có lý do, người phụ trách hoặc thời hạn | Nợ kiến trúc bị che khuất | Quản lý ngoại lệ có chủ sở hữu và kế hoạch loại bỏ. |

## 8. Tự đánh giá lựa chọn

Với một modular monolith bán hàng, nhóm đã khai báo `allowedDependencies` và muốn Spring Modulith tiếp tục kiểm tra chu trình cũng như truy cập package nội bộ. Đồng thời, nhóm muốn cấm package `web` phụ thuộc trực tiếp vào `persistence`, nhưng vẫn giữ mọi kiểm tra jMolecules đang chạy theo classpath. Lựa chọn phù hợp là tạo `VerificationOptions.defaults()`, gọi `andAdditionalVerifications` với `ArchRule` cho quy tắc phân lớp, rồi truyền options vào `ApplicationModules.verify(options)`.

Nếu nhóm muốn thu thập toàn bộ vi phạm để hiển thị báo cáo trong giai đoạn chuyển đổi, hãy dùng `detectViolations(options)` và chỉ lọc những ngoại lệ đã được phê duyệt rõ ràng. Nếu dự án chỉ cần các quy tắc mô-đun cốt lõi, `ApplicationModules.verify()` vẫn là lựa chọn gọn và phù hợp.

## Tài liệu tham khảo

- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Javadoc – VerificationOptions](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)
- [Javadoc – ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)

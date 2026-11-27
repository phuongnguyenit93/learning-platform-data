# Đánh giá chi phí chạy rule bổ sung

Spring Modulith cho phép thêm ArchUnit rule vào `ApplicationModules.verify()` thông qua `VerificationOptions`. Những rule này giúp kiểm tra kiến trúc ở cấp class và package, chẳng hạn domain không phụ thuộc infrastructure hoặc adapter tuân thủ hướng dependency của Hexagonal Architecture. Khi số lượng rule tăng, thời gian kiểm tra cũng có thể tăng. Vì vậy, nhóm cần biết chi phí đến từ đâu, cách đo đúng và cách tối ưu mà vẫn giữ được những ràng buộc kiến trúc quan trọng.

Chi phí của một lần verification không chỉ là số lượng rule. Kích thước module model, số class được import, độ rộng của predicate, số dependency type cần phân tích và số lần test gọi lại verification đều ảnh hưởng đến thời gian. Một rule đơn giản trên phạm vi hẹp có thể rẻ hơn nhiều rule phức tạp quét toàn bộ codebase.

## 1. Hiểu những phần việc tạo nên thời gian verification

Một bài kiểm tra kiến trúc thường có hai giai đoạn chính:

1. **Tạo module model:** `ApplicationModules.of(ShopApplication.class)` phân tích package và bytecode để xây dựng mô hình các application module, type và quan hệ dependency.
2. **Chạy verification:** `verify()` kiểm tra quy tắc module của Spring Modulith và các verification bổ sung được cấu hình qua `VerificationOptions`.

Có thể biểu diễn đơn giản:

```text
ApplicationModules.of(...)
        |
        v
Import và xây dựng Java type model
        |
        v
ApplicationModules.verify(options)
        |
        +--> Quy tắc module của Spring Modulith
        |
        +--> jMolecules verification mặc định (nếu được tích hợp)
        |
        +--> ArchRule bổ sung do dự án đăng ký
        |
        v
Kết quả verification / violations
```

Việc phân biệt hai giai đoạn rất quan trọng. Nếu test chậm do import một package gốc quá rộng, thêm hoặc bớt một ArchRule có thể không giải quyết được phần chi phí lớn nhất. Ngược lại, nếu model đã được tạo nhanh nhưng một rule quét nhiều quan hệ type, cần xem lại chính rule đó.

`ApplicationModules` phân tích cấu trúc code mà không cần khởi động một Spring `ApplicationContext` đầy đủ. Vì vậy, không nên nhầm thời gian của architecture test với thời gian startup của `@SpringBootTest`. Nếu test đang khởi động cả ứng dụng, phần startup đó là chi phí riêng cần được đo tách biệt.

## 2. Các yếu tố ảnh hưởng đến chi phí

| Yếu tố | Vì sao làm tăng thời gian | Dấu hiệu cần quan sát |
| --- | --- | --- |
| Phạm vi package gốc quá rộng | Nhiều class và package được đưa vào type model | Model chứa package không thuộc ứng dụng hoặc thư viện nội bộ không cần kiểm tra |
| Số lượng class lớn | ArchUnit có nhiều type và dependency relation cần phân tích | Thời gian import model tăng cùng kích thước codebase |
| Rule có phạm vi rộng | Predicate phải xét nhiều class hoặc nhiều dependency edge | Rule toàn cục chậm hơn rule chỉ chọn package cần kiểm tra |
| Nhiều rule trùng phạm vi | Cùng một tập type/dependency bị duyệt lặp lại bởi nhiều rule | Thời gian tăng khi thêm rule tương tự dù mỗi rule đơn giản |
| Điều kiện phức tạp | Kiểm tra hierarchy, annotation, generic hoặc dependency sâu cần thêm phân tích | Rule tự viết chậm hơn rule predicate đơn giản |
| Verification bị gọi lặp | Mỗi lần gọi có thể chạy lại các kiểm tra trên cùng model | Nhiều test class cùng gọi `verify()` với cùng options |
| jMolecules integration trên classpath | Các verification mặc định được tích hợp có thể được thêm vào | Thời gian thay đổi sau khi thêm artifact jMolecules vào test classpath |

Không có công thức thời gian cố định áp dụng cho mọi dự án. Một cách ước lượng hữu ích là xem chi phí tăng theo kích thước tập type được kiểm tra, số quan hệ dependency mà rule phải xét và số lần rule được thực thi. Đây là mô hình tư duy để tìm điểm nghẽn, không phải cam kết độ phức tạp của implementation.

## 3. Phân biệt chi phí tạo model và chi phí chạy rule

Khi đo, hãy ghi nhận riêng thời gian tạo `ApplicationModules` và thời gian chạy `verify(options)`. Ví dụ chẩn đoán đơn giản:

```java
package com.acme.shop;

import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class VerificationTimingSample {

    void measure() {
        long modelStarted = System.nanoTime();
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
        long modelNanos = System.nanoTime() - modelStarted;

        VerificationOptions options = VerificationOptions.defaults();

        long verificationStarted = System.nanoTime();
        modules.verify(options);
        long verificationNanos = System.nanoTime() - verificationStarted;

        System.out.printf(
                "model=%d ms, verification=%d ms%n",
                modelNanos / 1_000_000,
                verificationNanos / 1_000_000
        );
    }
}
```

Đây là phép đo thăm dò để xác định giai đoạn nào đáng chú ý. Một lần chạy đơn lẻ không đủ để kết luận vì JVM có warm-up, JIT compilation, filesystem cache và tải nền. Hãy chạy nhiều lần trong cùng điều kiện, bỏ qua các lần warm-up và so sánh median hoặc phân bố thời gian.

Nếu `model` chiếm phần lớn thời gian, xem lại package root, classpath và số type được import. Nếu `verification` chiếm phần lớn, xem số lượng rule, phạm vi predicate và số lần `verify()` được gọi.

## 4. Đo phần chi phí tăng thêm của một rule

Để biết một rule mới làm verification chậm thêm bao nhiêu, hãy so sánh cùng một module model với hai bộ options:

Giả sử `domainMustNotDependOnAdapters` là một `ArchRule` đã được khai báo trước đó:

```java
var baseline = VerificationOptions.defaults();

var candidate = VerificationOptions.defaults()
        .andAdditionalVerifications(domainMustNotDependOnAdapters);
```

`baseline` giữ nguyên các verification bổ sung mặc định. `candidate` giữ các rule mặc định và thêm rule mới. Nhờ đó, phần khác biệt chủ yếu đến từ rule được thêm, thay vì vô tình so sánh hai tập verification khác nhau.

Có thể dùng cùng một `ApplicationModules` instance trong phép đo:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

// Chạy warm-up trước khi ghi số đo.
modules.verify(baseline);
modules.verify(candidate);

long baselineStarted = System.nanoTime();
modules.verify(baseline);
long baselineNanos = System.nanoTime() - baselineStarted;

long candidateStarted = System.nanoTime();
modules.verify(candidate);
long candidateNanos = System.nanoTime() - candidateStarted;

long addedCostNanos = candidateNanos - baselineNanos;
```

Đoạn code minh họa cách tách phần chi phí tương đối. Trong phép đo nghiêm túc, hãy lặp lại nhiều vòng, đổi thứ tự chạy baseline/candidate hoặc dùng các JVM fork riêng để giảm ảnh hưởng của JIT và thứ tự thực thi. Không dùng một kết quả âm hoặc một lần chạy nhanh bất thường để kết luận rule không có chi phí.

Nếu muốn đánh giá một rule mới so với các verification cốt lõi hoàn toàn, có thể thử `withoutAdditionalVerifications()` trong một phép đo chẩn đoán. Nhưng baseline này đã loại bỏ các verification bổ sung mặc định, chẳng hạn jMolecules integration nếu có. Không dùng kết quả đó để đại diện cho cấu hình CI thực tế nếu CI vẫn chạy các rule mặc định.

## 5. Thu hẹp phạm vi rule trước khi tối ưu điều kiện

Một rule thường bắt đầu bằng việc chọn tập class chịu sự kiểm tra. Nếu predicate chọn mọi class trong ứng dụng, ArchUnit phải xét một tập lớn hơn mức cần thiết. Hãy xác định package nguồn và package đích cụ thể.

Ví dụ, rule rộng:

```java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;

ArchRule noDomainToInfrastructure = noClasses()
        .should().dependOnClassesThat()
        .resideInAPackage("..infrastructure..");
```

Rule này áp dụng điều kiện cho tất cả class được import. Nếu ý định chỉ là kiểm soát domain của module `order`, hãy giới hạn source package:

```java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;

ArchRule orderDomainMustNotDependOnInfrastructure = noClasses()
        .that().resideInAPackage("com.acme.shop.order.domain..")
        .should().dependOnClassesThat()
        .resideInAnyPackage(
                "com.acme.shop.order.infrastructure..",
                "com.acme.shop.order.adapter.."
        );
```

Rule thứ hai diễn đạt đúng phạm vi cần bảo vệ. Nó tránh áp điều kiện domain của `order` lên những package không liên quan. Tuy nhiên, thu hẹp phạm vi chỉ hợp lệ khi nó phản ánh kiến trúc dự kiến; đừng giới hạn package để che giấu vi phạm ở nơi khác.

Với một quy tắc dùng chung cho nhiều module, có thể khai báo pattern theo namespace thống nhất, ví dụ `..domain..` và `..adapter..`. Hãy bảo đảm pattern không vô tình bỏ qua module có cấu trúc package khác biệt.

## 6. Tránh đăng ký nhiều rule trùng lặp

Một số rule có thể lặp lại cùng một phép kiểm tra dưới tên khác nhau:

Giả sử ba `ArchRule` dưới đây đã được định nghĩa riêng theo các chính sách của dự án:

```java
var options = VerificationOptions.defaults()
        .andAdditionalVerifications(
                domainMustNotDependOnAdapters,
                domainMustNotDependOnInfrastructure,
                domainMustNotDependOnPersistence
        );
```

Nếu các rule có source scope giống nhau và target scope chồng lấn, cùng một nhóm dependency có thể bị xét nhiều lần. Hãy xem chúng có thể được diễn đạt bằng một rule rõ ràng hơn hay không:

```java
ArchRule domainMustNotDependOnTechnicalAdapters = noClasses()
        .that().resideInAPackage("..domain..")
        .should().dependOnClassesThat()
        .resideInAnyPackage(
                "..adapter..",
                "..infrastructure..",
                "..persistence.."
        );
```

Gộp rule chỉ nên thực hiện khi các điều kiện có cùng ý nghĩa kiến trúc và diagnostic vẫn đủ rõ. Nếu ba rule đại diện cho ba quyết định kiến trúc độc lập, giữ chúng riêng có thể giúp thông báo lỗi và ownership dễ hiểu hơn. Mục tiêu là loại bỏ phép kiểm tra dư thừa, không phải tối thiểu hóa số rule bằng mọi giá.

## 7. Tái sử dụng module model và tập options

Nếu nhiều test trong cùng architecture test suite tạo lại `ApplicationModules` và chạy cùng bộ rule, chi phí import model có thể bị lặp. Có thể đặt model và options dùng chung ở cấp test class hoặc test fixture:

```java
package com.acme.shop;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class ArchitectureTests {

    private static final ArchRule domainMustNotDependOnAdapters = noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAPackage("..adapter..");

    private static final ApplicationModules MODULES =
            ApplicationModules.of(ShopApplication.class);

    private static final VerificationOptions OPTIONS =
            VerificationOptions.defaults()
                    .andAdditionalVerifications(
                            JMoleculesArchitectureRules.ensureHexagonal(),
                            domainMustNotDependOnAdapters
                    );

    @Test
    void verifiesArchitecture() {
        MODULES.verify(OPTIONS);
    }
}
```

Ví dụ minh họa việc tạo model và options một lần trong cùng test class. Nếu tách thành nhiều test class hoặc test task, hãy kiểm tra xem framework/test runner có thực sự chia sẻ instance hay không; không giả định cache tự động giữa các JVM hoặc classloader. Tái sử dụng một `ApplicationModules` object trong cùng suite giúp tránh tự tạo model nhiều lần, nhưng mỗi lần gọi `verify()` vẫn thực thi các verification đã cấu hình.

Vì vậy, một architecture test tập trung thường dễ quản lý hơn việc gọi `verify()` trong mọi test nghiệp vụ. Các test nghiệp vụ nên tập trung vào hành vi; architecture suite chịu trách nhiệm chạy bộ rule kiến trúc có chủ đích.

## 8. Chọn đúng `VerificationOptions`

Ba cách cấu hình options ảnh hưởng trực tiếp đến số rule được chạy:

| API | Ảnh hưởng | Khi nên dùng |
| --- | --- | --- |
| `defaults()` | Dùng verification bổ sung mặc định; có thể bao gồm jMolecules integration phù hợp trên classpath | Cấu hình chuẩn cho phần lớn architecture test |
| `andAdditionalVerifications(rules…)` | Giữ các verification bổ sung mặc định và thêm rule mới | Muốn mở rộng coverage |
| `withAdditionalVerifications(rules…)` | Thay tập verification bổ sung mặc định bằng tập được truyền vào | Chỉ khi chủ ý quản lý toàn bộ tập rule bổ sung |
| `withoutAdditionalVerifications()` | Tắt verification bổ sung mặc định | Chẩn đoán hoặc cấu hình đặc biệt có lý do rõ ràng |

Không nên dùng `withAdditionalVerifications()` chỉ để giảm thời gian nếu điều đó vô tình loại bỏ jMolecules checks mà nhóm vẫn cần. Tương tự, không dùng `withoutAdditionalVerifications()` làm cấu hình CI mặc định chỉ vì nó chạy nhanh hơn. Tối ưu thời gian phải giữ nguyên các ràng buộc kiến trúc mà dự án cam kết.

## 9. Chú ý verification mặc định từ jMolecules

Khi các dependency jMolecules tương ứng có mặt trên classpath, Spring Modulith có thể tích hợp các verification mặc định của jMolecules vào `VerificationOptions.defaults()`. Vì vậy, thời gian verification có thể thay đổi sau khi nhóm thêm artifact jMolecules, dù code test không đổi.

Hãy kiểm tra:

- Dependency nào đưa `jmolecules-archunit` vào test classpath.
- Các annotation artifact DDD có thực sự được sử dụng không.
- Nhóm có cần các verification mặc định được tích hợp hay không.
- Có preset Hexagonal, Layered hoặc Onion nào được đăng ký thêm không.
- Một rule có đang được chạy cả qua mặc định và qua đăng ký thủ công hay không.

Không loại bỏ dependency chỉ để giảm thời gian nếu dependency đó đang cung cấp annotation hoặc rule mà dự án cần. Nếu muốn đo riêng ảnh hưởng của jMolecules, hãy tạo phép so sánh có kiểm soát và ghi lại tập options của từng lần chạy.

## 10. Package exclusion có thể giảm chi phí nhưng cũng giảm coverage

`ApplicationModules.of(applicationClass, ignoredPredicate)` có thể loại một số type khỏi module inspection. Thu hẹp phạm vi import có thể giảm số class mà các rule phải xét. Tuy nhiên, exclusion cũng làm giảm phần kiến trúc được kiểm tra.

Ví dụ:

```java
import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(
        ShopApplication.class,
        JavaClass.Predicates.resideInAPackage("com.acme.shop.generated..")
);
```

Chỉ nên loại trừ code được xác định rõ là ngoài phạm vi kiến trúc, chẳng hạn mã sinh tự động không thuộc module nghiệp vụ. Không loại trừ `database`, `persistence` hoặc một module chậm chỉ vì nó làm verification lâu hơn nếu những package đó chứa dependency mà nhóm cần kiểm soát.

Một exclusion quá rộng có thể làm mất cạnh dependency, khiến rule không còn thấy reference mà nhóm muốn phát hiện. Khi dùng predicate, hãy ghi lý do, phạm vi và chủ sở hữu của vùng bị bỏ qua; duy trì test riêng nếu phần đó vẫn cần kiểm tra theo cách khác.

## 11. Đo trong local và CI

Một quy trình đo có thể thực hiện theo các bước:

1. Chạy architecture test hiện tại và ghi lại thời gian tổng.
2. Tách thời gian tạo `ApplicationModules` khỏi thời gian `verify(options)` nếu cần tìm điểm nghẽn.
3. Ghi lại số rule, options và dependency jMolecules trên classpath.
4. Thêm một rule tại một thời điểm rồi đo lại trong cùng điều kiện.
5. Lặp lại nhiều lần, bỏ qua warm-up và so sánh median thay vì dựa vào một lần chạy.
6. Ghi nhận cả thời gian và coverage của rule để biết tối ưu có làm mất kiểm tra hay không.

Trong local development, có thể chạy riêng architecture test để nhận phản hồi nhanh. Trong CI, vẫn nên chạy toàn bộ bộ verification được nhóm thống nhất trên mỗi thay đổi có ảnh hưởng kiến trúc. Nếu cần phân chia task, hãy bảo đảm mọi rule bắt buộc vẫn được thực thi ở pipeline bảo vệ nhánh.

Không so sánh thời gian giữa hai lần chạy nếu JDK, heap, số worker, trạng thái cache, classpath hoặc máy thực thi khác nhau mà không ghi nhận khác biệt. Build cache có thể giảm thời gian task tổng thể nhưng không có nghĩa bản thân ArchRule đã chạy nhanh hơn.

## 12. Giữ diagnostic rõ khi tối ưu

Một cách tối ưu có thể làm giảm thời gian nhưng khiến kết quả khó xử lý. Ví dụ, gộp nhiều quy tắc vào một predicate khổng lồ có thể khiến violation message khó chỉ ra quyết định kiến trúc nào bị vi phạm.

Hãy cân bằng ba yếu tố:

- **Thời gian:** rule không quét những package không liên quan và không bị chạy lặp vô ích.
- **Coverage:** mọi dependency và layer boundary quan trọng vẫn được kiểm tra.
- **Diagnostic:** khi test thất bại, developer biết module, type và quy tắc nào cần xem lại.

Nếu hai rule có cùng phạm vi nhưng đại diện hai chính sách khác nhau, giữ chúng riêng có thể tốt hơn. Nếu nhiều rule thực sự trùng lặp và thông báo lỗi vẫn đủ rõ sau khi gộp, gộp có thể giúp giảm số lần duyệt dependency.

## 13. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Thời gian `verify()` chỉ phụ thuộc số lượng rule | Kích thước module model, số dependency edge, độ rộng predicate và số lần gọi cũng ảnh hưởng |
| Thêm rule luôn làm tăng thời gian theo cùng một tỷ lệ | Rule có phạm vi và điều kiện khác nhau có chi phí khác nhau |
| Chạy `ApplicationModules.of()` một lần nghĩa là mọi lần verify đều miễn phí | Tái sử dụng model tránh import lại; mỗi lần `verify()` vẫn chạy các rule |
| `withAdditionalVerifications()` là cách tăng tốc an toàn | Nó thay tập verification bổ sung mặc định; có thể vô tình bỏ coverage |
| `withoutAdditionalVerifications()` tắt mọi module verification | Nó chỉ tắt verification bổ sung; quy tắc module cốt lõi vẫn chạy |
| Exclude package chậm luôn là tối ưu tốt | Exclusion có thể che giấu dependency và làm giảm coverage |
| Một lần đo bằng `System.nanoTime()` đủ để so sánh | Cần warm-up, nhiều lần chạy và điều kiện nhất quán |
| Nên gọi `verify()` trong mọi test nghiệp vụ | Một architecture suite tập trung thường tránh chạy lặp cùng bộ rule |

## 14. Ghi nhớ

Chi phí chạy rule bổ sung trong Spring Modulith đến từ việc tạo module model, số type và dependency relation được phân tích, độ rộng/độ phức tạp của ArchRule và số lần verification được gọi. Hãy đo riêng thời gian `ApplicationModules.of()` và `verify(options)` để xác định đúng điểm nghẽn.

Để tối ưu, thu hẹp predicate theo package cần bảo vệ, loại rule trùng lặp khi chúng thực sự kiểm tra cùng một chính sách, tái sử dụng module model trong cùng architecture test suite và tránh gọi `verify()` lặp lại ở nhiều test nghiệp vụ. So sánh `VerificationOptions.defaults()` với options được mở rộng bằng `andAdditionalVerifications()` để ước lượng phần chi phí tăng thêm. Chỉ dùng `withAdditionalVerifications()` hoặc `withoutAdditionalVerifications()` khi chủ ý thay đổi tập rule bổ sung và đã đánh giá coverage.

Cuối cùng, không đánh đổi ranh giới kiến trúc lấy vài giây build. Một rule chậm nhưng bảo vệ dependency quan trọng có thể đáng giữ; điều cần loại bỏ là phép kiểm tra dư thừa, phạm vi quá rộng hoặc việc chạy lặp không cần thiết. Đưa bộ rule đã chọn vào CI và theo dõi cả thời gian lẫn coverage qua các lần thay đổi.

## Tài liệu tham khảo

- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith API — `VerificationOptions`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)
- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [ArchUnit User Guide — Performance and Architecture Rules](https://www.archunit.org/userguide/html/000_Index.html)

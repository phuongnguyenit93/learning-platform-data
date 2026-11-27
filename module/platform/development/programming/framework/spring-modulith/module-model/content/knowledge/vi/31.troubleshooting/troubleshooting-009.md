# Rule bổ sung tạo lỗi ngoài dự kiến

Khi chạy ApplicationModules.verify(), Spring Modulith kiểm tra các quy tắc về ranh giới application module. Tuy nhiên, kết quả có thể chứa thêm violation mà nhóm không nghĩ mình đã bật. Một nguyên nhân thường gặp là classpath có thư viện tích hợp jMolecules ArchUnit. Khi thư viện này hiện diện, Spring Modulith có thể tự động chạy thêm các quy tắc xác minh DDD của jMolecules bên cạnh các quy tắc module cốt lõi.

Ngoài ra, dự án có thể đăng ký ArchUnit rules riêng hoặc các quy tắc kiến trúc từ thư viện khác. Những rule bổ sung có thể phát hiện vi phạm về aggregate, entity, value object, layering hoặc hexagonal architecture. Vì vậy, không nên kết luận mọi violation do ApplicationModules.verify() báo ra đều là lỗi dependency giữa các application module.

Trong SPRING_MODULITH_MODULE_MODEL, bài học này giúp xác định nguồn của rule bổ sung, phân biệt nó với verification cốt lõi của Spring Modulith, kiểm tra classpath và VerificationOptions, đọc diagnostic đúng cách, rồi quyết định giữ, điều chỉnh hoặc tắt rule bổ sung có chủ đích.

## 1. Vì sao có violation ngoài dự kiến?

Một test kiến trúc thường được viết rất ngắn:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Nhìn vào test, có thể nghĩ nó chỉ kiểm tra module cycle, internal package access và allowedDependencies. Nhưng kết quả thực tế còn phụ thuộc vào cấu hình verification và classpath mà test đang chạy.

Các nguyên nhân phổ biến:

- Thư viện jMolecules ArchUnit được thêm trực tiếp hoặc bắc cầu vào test classpath.
- Một dependency integration kéo thêm ArchUnit hoặc rule set khác.
- Dự án tự tạo ArchRule và truyền vào VerificationOptions.
- Một test ArchUnit riêng chạy trong cùng test task và báo lỗi, khiến nhóm nhầm nguồn với Spring Modulith.
- Test và runtime dùng dependency graph khác nhau nên tập rule được kích hoạt khác nhau.
- Phiên bản thư viện thay đổi cách đăng ký hoặc cách đánh giá rule.

Điểm quan trọng là phân loại violation theo nguồn trước khi sửa code. Một rule DDD có thể yêu cầu aggregate chỉ tham chiếu entity thuộc aggregate của nó; đó là quy tắc mô hình domain, không phải quy tắc module dependency.

## 2. Ba quy tắc cốt lõi của Spring Modulith

ApplicationModules.verify() kiểm tra các ràng buộc chính của application module:

| Quy tắc | Điều được bảo vệ | Ví dụ vi phạm |
|---|---|---|
| Không có dependency cycle giữa module | Đồ thị module phải có hướng và không có chu kỳ | order → inventory → catalog → order |
| Chỉ truy cập API package được expose của module khác | Consumer không được tham chiếu package internal của provider đóng | order import inventory.internal.InventoryRepository |
| Chỉ dùng dependency được cho phép nếu khai báo whitelist | Consumer chỉ được phụ thuộc trực tiếp vào module hoặc named interface đã cho phép | order cho phép inventory nhưng tham chiếu payment |

Đây là các quy tắc về cấu trúc module. Chúng có thể chạy cùng các verification bổ sung, nhưng cần được nhận diện riêng khi đọc lỗi.

## 3. jMolecules ArchUnit có thể kích hoạt thêm DDD rules

jMolecules cung cấp annotation và interface để biểu diễn các khái niệm DDD như aggregate root, entity, value object, identifier và repository. Thư viện jmolecules-archunit cung cấp ArchUnit rules để kiểm tra các quan hệ kiến trúc liên quan đến những khái niệm đó.

Spring Modulith có tích hợp tùy chọn với jMolecules ArchUnit. Khi thư viện phù hợp có mặt trên classpath, VerificationOptions.defaults() có thể bao gồm các jMolecules verification; ApplicationModules.verify() và detectViolations() sử dụng các verification bổ sung này theo cấu hình mặc định.

Ví dụ các vấn đề DDD có thể được phát hiện:

- Entity phải khai báo aggregate root mà nó thuộc về.
- Aggregate root chỉ tham chiếu các entity thuộc aggregate của nó.
- Aggregate root và entity nên tham chiếu aggregate khác qua association/identifier thay vì tham chiếu trực tiếp internals.
- Value object không nên phụ thuộc vào identifiable/entity theo cách vi phạm quy tắc DDD tương ứng.

Các chi tiết rule cụ thể phụ thuộc phiên bản jMolecules ArchUnit đang resolve. Hãy đọc tài liệu và Javadoc của đúng phiên bản thay vì giả định mọi rule luôn giống nhau.

Lưu ý: việc dùng annotation DDD của jMolecules và việc tự động chạy ArchUnit verification là hai chuyện khác nhau. Annotation giúp mô tả mô hình; thư viện ArchUnit tương ứng mới cung cấp rule kiểm tra. Chỉ thấy annotation jMolecules trong source chưa đủ để kết luận tất cả rule bổ sung đang chạy.

## 4. Không nhầm DDD rules với mọi rule kiến trúc jMolecules

jMolecules ArchUnit có thể cung cấp nhiều nhóm rule, chẳng hạn:

- DDD rules cho aggregate, entity, value object và association.
- Layered architecture rules.
- Hexagonal architecture rules.
- Onion architecture rules.

Spring Modulith tự động tích hợp các DDD verification được mô tả trong tài liệu của nó khi thư viện phù hợp có mặt. Không nên suy diễn rằng mọi rule layered, hexagonal hoặc onion đều tự động chạy chỉ vì jmolecules-archunit nằm trên classpath.

Các rule kiến trúc như hexagonal hoặc layered thường cần được chọn và đăng ký rõ ràng qua VerificationOptions hoặc chạy như ArchUnit test riêng. Hãy xác nhận rule nào thực sự được gọi trong dự án trước khi thay đổi package hoặc annotation để làm test qua.

## 5. Phân biệt nguồn violation

Khi test thất bại, bắt đầu bằng việc phân loại thông báo:

| Dấu hiệu | Nguồn có thể là | Nội dung cần kiểm tra |
|---|---|---|
| Module cycle, dependency to internal package, dependency not allowed | Spring Modulith core verification | Consumer, provider, package và allowedDependencies |
| Aggregate/entity/value object relationship | jMolecules DDD ArchUnit rules | Annotation/interface DDD, ownership và association |
| Layer access hoặc adapter/port direction | ArchUnit/jMolecules architecture rule được đăng ký | Layer stereotype và chiều tham chiếu |
| Rule có tên do dự án đặt | Custom ArchRule | Điều kiện trong rule và package/class bị chọn |
| Một test khác có @ArchTest | ArchUnit test độc lập | Test class, rule field và mô tả rule |

Một exception tổng hợp có thể chứa nhiều violation từ các nhóm khác nhau. Không sửa tất cả theo một hướng như thêm allowedDependencies hoặc chuyển module thành OPEN.

## 6. Kiểm tra dependency graph trước khi điều tra source

Khi violation xuất hiện bất ngờ sau khi thêm thư viện, so sánh dependency graph trước và sau thay đổi.

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency jmolecules-archunit --configuration testRuntimeClasspath
~~~

Kiểm tra các dependency jMolecules khác:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.jmolecules
~~~

Chú ý:

- Dependency có thể được thêm trực tiếp hoặc transitively.
- Một artifact có thể chỉ xuất hiện trên test classpath.
- Version có thể được quản lý bởi BOM hoặc bị override.
- Test runtime và production runtime có thể khác nhau.
- Việc loại bỏ một artifact có thể làm mất rule tự động nhưng cũng có thể làm mất annotation, integration hoặc behavior khác mà ứng dụng đang cần.

Không loại bỏ dependency chỉ vì nó làm test đỏ. Trước hết xác định ai đưa dependency vào và dự án có chủ đích dùng các khái niệm jMolecules hay không.

## 7. Xác định VerificationOptions mặc định

Spring Modulith cung cấp VerificationOptions để tùy chỉnh các verification bổ sung.

~~~java
import org.springframework.modulith.core.VerificationOptions;

VerificationOptions options = VerificationOptions.defaults();
~~~

defaults() tạo cấu hình verification mặc định và bao gồm jMolecules verifications nếu chúng có mặt trên classpath.

VerificationOptions và các overload verify(options)/detectViolations(options) được bổ sung từ Spring Modulith 1.4. Nếu dự án dùng phiên bản cũ hơn, hãy kiểm tra Javadoc đúng release trước khi sao chép các ví dụ tùy chỉnh này.

Do đó, cùng một đoạn test có thể cho kết quả khác nhau khi:

- Classpath trước đó không có jmolecules-archunit.
- Một dependency mới kéo jmolecules-archunit vào.
- Test configuration được thay đổi.
- BOM nâng phiên bản của thư viện và rule behavior thay đổi.

Khi điều tra, hãy kiểm tra cả code gọi verify() lẫn VerificationOptions được truyền vào. Nếu không truyền options, hành vi mặc định phụ thuộc classpath.

## 8. Thêm rule mà vẫn giữ các rule mặc định

Nếu dự án muốn bổ sung ArchUnit rule riêng và vẫn giữ các verification mặc định, dùng andAdditionalVerifications().

Ví dụ minh họa một rule giới hạn domain package chỉ phụ thuộc vào domain package, kiểu Java và một shared package được chỉ định:

~~~java
import org.junit.jupiter.api.Test;
import com.tngtech.archunit.lang.ArchRule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;

class ModularityTests {

    @Test
    void verifiesModulesAndDomainDependencies() {
        ArchRule domainRule = classes()
                .that().resideInAPackage("..domain..")
                .should().onlyDependOnClassesThat()
                .resideInAnyPackage(
                        "..domain..",
                        "java..",
                        "..shared..");

        VerificationOptions options = VerificationOptions.defaults()
                .andAdditionalVerifications(domainRule);

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
~~~

Rule trên chỉ là ví dụ. Điều chỉnh package pattern theo cấu trúc dự án và xác nhận rằng các dependency được cho phép thực sự thuộc hợp đồng kiến trúc đã chọn.

andAdditionalVerifications() giữ các additional verification mặc định và thêm rule mới vào. Đây là lựa chọn phù hợp khi muốn mở rộng kiểm tra mà không vô tình bỏ các rule mặc định được phát hiện từ classpath.

## 9. Hiểu khác biệt giữa andAdditionalVerifications và withAdditionalVerifications

Hai method có tên gần nhau nhưng semantics khác nhau:

| Method | Hành vi |
|---|---|
| andAdditionalVerifications(rule) | Thêm rule mới bên cạnh các additional verification mặc định |
| withAdditionalVerifications(rule) | Định nghĩa lại tập additional verification; các additional verification mặc định bị thay thế |
| withoutAdditionalVerifications() | Tắt các additional verification được đăng ký mặc định |
| defaults() | Tạo options mặc định, bao gồm jMolecules verification nếu có trên classpath |

Ví dụ:

~~~java
VerificationOptions options = VerificationOptions.defaults()
        .andAdditionalVerifications(domainRule);
~~~

Đoạn này giữ các additional rule mặc định rồi thêm domainRule.

Ngược lại:

~~~java
VerificationOptions options = VerificationOptions.defaults()
        .withAdditionalVerifications(domainRule);
~~~

Đoạn này thay tập additional verification mặc định bằng domainRule. Nếu jMolecules DDD verification được đưa vào qua defaults(), nó sẽ không còn trong tập additional rule được chạy bằng options này.

Đây là nguyên nhân dễ gây hiểu nhầm: nhóm thêm một custom rule nhưng vô tình làm biến mất rule bổ sung mặc định, hoặc nghĩ rằng withAdditionalVerifications() sẽ cộng dồn trong khi nó thay thế.

## 10. Tạm thời tắt additional verification để khoanh vùng

Khi nghi ngờ lỗi đến từ rule bổ sung, có thể chạy một lần so sánh với additional verification bị tắt:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class VerificationDiagnosticTests {

    @Test
    void checksCoreModuleRulesWithoutAdditionalVerifications() {
        VerificationOptions options = VerificationOptions.defaults()
                .withoutAdditionalVerifications();

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
~~~

Nếu test qua với options này nhưng thất bại với defaults(), đó là bằng chứng hữu ích rằng violation nằm trong nhóm additional verification. Đây là bước khoanh vùng, không phải bằng chứng rằng violation đó sai hoặc có thể bỏ qua.

withoutAdditionalVerifications() chỉ tắt các verification bổ sung được đăng ký mặc định. Các quy tắc module cốt lõi như dependency cycle, encapsulation và allowedDependencies vẫn là trách nhiệm của Spring Modulith.

Không nên để test production architecture vĩnh viễn dùng options đã tắt tất cả additional checks chỉ để làm pipeline xanh. Nếu nhóm quyết định không áp dụng một rule, cần ghi rõ lý do và phạm vi ngoại lệ.

## 11. Dùng detectViolations để điều tra chi tiết

verify() ném exception khi có violation. Khi cần phân tích hoặc lọc kết quả trước khi quyết định thất bại, dùng detectViolations():

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

var modules = ApplicationModules.of(ShopApplication.class);
var violations = modules.detectViolations(VerificationOptions.defaults());
~~~

Violations cung cấp API để xử lý tập lỗi, bao gồm lọc các violation và gọi throwIfPresent() cho những lỗi còn lại.

Ví dụ minh họa cách chỉ loại bỏ một ngoại lệ đã được nhận diện rõ:

~~~java
modules.detectViolations(VerificationOptions.defaults())
        .filter(violation -> !isDocumentedTemporaryException(violation))
        .throwIfPresent();
~~~

isDocumentedTemporaryException() là hàm do dự án tự định nghĩa; điều kiện phải nhận diện chính xác violation được chấp thuận, có owner và thời hạn. Không lọc theo chuỗi chung chung hoặc loại bỏ toàn bộ violation từ một package vì cách đó có thể che cả lỗi mới.

Trong phần lớn dự án, tốt hơn là sửa rule hoặc source vi phạm thay vì duy trì danh sách ignore dài hạn.

## 12. Ví dụ: jMolecules DDD rule phát hiện aggregate reference

Giả sử code biểu diễn aggregate và entity bằng các kiểu jMolecules:

~~~java
import org.jmolecules.ddd.types.AggregateRoot;
import org.jmolecules.ddd.types.Entity;
import org.jmolecules.ddd.types.Identifier;

interface OrderId extends Identifier {
}

interface OrderLineId extends Identifier {
}

interface Order extends AggregateRoot<Order, OrderId> {
}

interface OrderLine extends Entity<Order, OrderLineId> {
}
~~~

Trong mô hình type-based, OrderLine khai báo rõ nó thuộc aggregate root Order. Nếu một entity được khai báo thuộc aggregate khác hoặc aggregate tham chiếu entity không thuộc phạm vi của nó, jMolecules DDD verification có thể báo violation.

Đây không phải lỗi vì module order phụ thuộc module inventory. Nó là lỗi về mô hình aggregate và quan hệ giữa các building block DDD.

Khi xử lý:

1. Xác nhận rule nào báo lỗi.
2. Kiểm tra aggregate root và entity ownership.
3. Kiểm tra kiểu generic và identifier.
4. Kiểm tra reference giữa aggregate có cần chuyển sang Association hoặc ID không.
5. Đọc tài liệu jMolecules đúng phiên bản để hiểu semantics rule.

Không sửa lỗi DDD bằng cách thêm module identifier vào allowedDependencies; hai quy tắc đang kiểm tra hai khía cạnh khác nhau.

## 13. Ví dụ: rule Hexagonal hoặc Layered không tự động xuất hiện

Một dự án có thể dùng annotation hoặc stereotype để đánh dấu port, adapter, application service và domain service. Nhóm muốn kiểm tra rằng domain không phụ thuộc adapter.

Đó là một rule kiến trúc bổ sung. Spring Modulith không thể tự suy ra mọi biến thể layered/hexagonal mà dự án muốn áp dụng chỉ từ việc có jMolecules trên classpath.

Có thể:

- Đăng ký ArchRule tương ứng qua VerificationOptions.
- Dùng rule factory của jMolecules ArchUnit nếu phiên bản đó cung cấp rule phù hợp.
- Viết ArchUnit test riêng có tên và mô tả rõ.

Khi sử dụng API jMolecules architecture rule, kiểm tra Javadoc đúng version. Một số overload có thể bị deprecated hoặc thay đổi options theo release.

## 14. Phân biệt lỗi do classpath với lỗi do source

Khi rule bổ sung xuất hiện sau một lần thay dependency, đừng vội sửa domain model. Hãy so sánh trạng thái trước và sau:

| Câu hỏi | Nếu câu trả lời là có |
|---|---|
| Có dependency jmolecules-archunit mới trong test runtime không? | Kiểm tra jMolecules DDD rules được tự động thêm |
| Có thay đổi BOM hoặc version jMolecules không? | Đọc release notes và rule semantics của version mới |
| Có custom VerificationOptions mới không? | Kiểm tra withAdditionalVerifications/andAdditionalVerifications |
| Có ArchUnit test mới được thêm không? | Xác định test độc lập với ApplicationModules.verify() |
| CI và local dùng classpath khác nhau không? | Đồng bộ dependency configurations và profile |
| Violation chỉ xuất hiện sau khi thêm annotation DDD? | Xem rule đang phân tích annotation/interface đó |

Nếu source không đổi nhưng test bắt đầu fail ngay sau dependency update, classpath và rule registration là hai điểm nên điều tra đầu tiên.

## 15. Đọc diagnostic của ArchUnit

ArchUnit thường mô tả rule bị vi phạm, các class được kiểm tra và dependency hoặc field/method reference không thỏa điều kiện. Hãy đọc toàn bộ mô tả thay vì chỉ lấy tên class đầu tiên.

Khi đọc diagnostic, xác định:

- Tên rule hoặc mô tả điều kiện mong đợi.
- Class được chọn bởi phần that() của rule.
- Dependency/reference bị rule từ chối.
- Source location nếu ArchUnit cung cấp.
- Rule đến từ jMolecules, custom ArchRule hay Spring Modulith core.

Ví dụ, lỗi có thể nói một entity tham chiếu trực tiếp một aggregate root khác. Đây là gợi ý về mô hình domain. Nếu lỗi nói module consumer tham chiếu package internal của provider, đó là violation encapsulation của Spring Modulith.

Đừng sửa class được nhắc tới trước khi xác định rule. Cùng một class có thể xuất hiện trong nhiều violation khác nhau.

## 16. Kiểm tra khác biệt giữa test và runtime

Test thường có testRuntimeClasspath riêng. Runtime verification khi ứng dụng khởi động lại dựa trên runtime classpath và VerificationOptions mà runtime auto-configuration nhận được.

Điều này có thể tạo ra khác biệt:

- Test có jmolecules-archunit nhưng production runtime không có.
- Production runtime có integration artifact mà test không có.
- Test tự tạo VerificationOptions nhưng runtime dùng mặc định.
- Customization chỉ tồn tại trong test source.

Khi test fail nhưng ứng dụng startup qua, hoặc ngược lại, hãy so sánh classpath và cấu hình verification thực tế. Không mặc định hai môi trường chạy cùng một tập rule.

Nếu cần áp dụng cùng một rule ở test và runtime, đưa cấu hình cần thiết vào production configuration theo API được phiên bản Spring Modulith hỗ trợ, đồng thời xác nhận behavior qua test và startup test.

## 17. Quyết định giữ, sửa hay loại bỏ rule bổ sung

Sau khi xác định nguồn rule, đánh giá ý nghĩa của nó:

| Tình huống | Hướng xử lý |
|---|---|
| Rule bảo vệ invariant DDD mà dự án thực sự áp dụng | Sửa mô hình domain để tuân thủ |
| Rule phản ánh architecture decision đã được thống nhất | Giữ rule và sửa source vi phạm |
| Rule không phù hợp với kiến trúc mà dự án đã chọn | Không đăng ký rule đó hoặc cấu hình options có chủ đích |
| Rule quá nghiêm so với giai đoạn migration | Chia phạm vi hoặc ghi ngoại lệ hẹp, có owner và thời hạn |
| Rule trùng với một kiểm tra khác | Chọn một nguồn kiểm tra rõ ràng để tránh diagnostic lặp |
| Rule được thêm ngoài ý muốn qua transitive dependency | Xác định dependency owner; điều chỉnh dependency graph sau khi đánh giá tác động |

Không loại bỏ rule chỉ vì nó phát hiện nhiều lỗi. Nếu rule phản ánh quyết định kiến trúc thật, các lỗi đó có thể là vấn đề tồn tại lâu nay nhưng trước đây chưa được tự động kiểm tra.

## 18. Quản lý ngoại lệ có kiểm soát

Nếu chưa thể sửa một violation ngay, ngoại lệ phải có phạm vi nhỏ:

- Chỉ rõ rule và class/reference được miễn.
- Ghi lý do nghiệp vụ hoặc kỹ thuật.
- Có người chịu trách nhiệm.
- Có issue hoặc kế hoạch xử lý.
- Có thời hạn xem xét lại.
- Không bỏ qua mọi violation của module hoặc package.

Khi dùng detectViolations().filter(...), predicate phải loại đúng ngoại lệ đã được ghi nhận. Một filter dựa vào package prefix rộng có thể che lỗi mới xuất hiện trong tương lai.

Ưu tiên tách test tạm thời cho migration và test bảo vệ các module đã ổn định. Không biến ngoại lệ thành trạng thái mặc định mà không review.

## 19. Quy trình chẩn đoán rule bổ sung tạo lỗi

Khi ApplicationModules.verify() bất ngờ thất bại, thực hiện theo trình tự:

1. **Đọc toàn bộ violation.** Không dừng ở stack trace hoặc dòng đầu.
2. **Phân loại nguồn.** Spring Modulith core, jMolecules DDD, custom ArchUnit hay test độc lập.
3. **Kiểm tra classpath.** Xem dependency tree của compile/test/runtime.
4. **Kiểm tra version.** Đối chiếu jMolecules và Spring Modulith version thực tế.
5. **Kiểm tra options.** Xác nhận defaults(), withAdditionalVerifications(), andAdditionalVerifications() hoặc withoutAdditionalVerifications() đang được dùng.
6. **Khoanh vùng.** Chạy so sánh với additional verification bị tắt trong một test chẩn đoán tạm thời.
7. **Đọc source reference.** Tìm class, field, method hoặc aggregate relationship gây lỗi.
8. **Đánh giá kiến trúc.** Xác định rule có phù hợp với quyết định thiết kế của dự án không.
9. **Sửa hoặc điều chỉnh rule.** Giữ rule có giá trị; chỉ bỏ rule không áp dụng sau khi có lý do rõ.
10. **Chạy lại kiểm tra đầy đủ.** Xác nhận core module rules và additional rules dự kiến đều chạy.
11. **So sánh môi trường.** Đảm bảo CI, test và runtime có dependency/options phù hợp.

## 20. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Mọi violation từ verify() đều là module dependency lỗi | Có thể là jMolecules DDD hoặc ArchUnit rule bổ sung |
| Chỉ cần jmolecules-ddd là mọi ArchUnit rule tự chạy | Annotation/model và ArchUnit verification là các thành phần khác nhau |
| Có jmolecules-archunit thì mọi Hexagonal/Layered/Onion rule tự chạy | Spring Modulith tự tích hợp DDD verification; các architecture rule khác cần đăng ký phù hợp |
| withAdditionalVerifications() cộng thêm rule | Nó thay tập additional verification mặc định |
| andAdditionalVerifications() bỏ các rule mặc định | Nó giữ mặc định và thêm rule mới |
| withoutAdditionalVerifications() tắt cả module verification | Nó tắt additional verification mặc định, không tắt core module rules |
| Test qua khi tắt additional rules nghĩa violation là false positive | Chỉ chứng minh lỗi thuộc nhóm additional; cần đánh giá rule và source |
| Xóa dependency jMolecules luôn là cách sửa đúng | Có thể làm mất mô hình DDD, integration hoặc tính năng khác |
| CI và runtime chắc chắn chạy cùng tập rule | Classpath và VerificationOptions có thể khác nhau |
| Có thể ignore mọi violation của một package | Filter rộng dễ che cả lỗi mới và làm mất giá trị kiểm tra |

## 21. Checklist trước khi thay đổi rule verification

- [ ] Xác định violation thuộc Spring Modulith core hay additional rule.
- [ ] Đọc đầy đủ rule description và source reference.
- [ ] Kiểm tra jmolecules-archunit trong test/runtime dependency graph.
- [ ] Phân biệt jmolecules-ddd annotation library với ArchUnit verification integration.
- [ ] Kiểm tra version và release notes của jMolecules.
- [ ] Xác nhận VerificationOptions thực tế được truyền vào.
- [ ] Hiểu khác biệt giữa defaults(), andAdditionalVerifications(), withAdditionalVerifications() và withoutAdditionalVerifications().
- [ ] Dùng detectViolations() để điều tra khi cần.
- [ ] Chỉ filter ngoại lệ hẹp, có owner và thời hạn.
- [ ] Không vô hiệu hóa core module verification để che lỗi.
- [ ] Đồng bộ classpath và options giữa CI, test và runtime theo yêu cầu.
- [ ] Chạy lại toàn bộ verification dự kiến sau khi sửa.

## 22. Kết luận

Rule bổ sung có thể tạo violation ngoài dự kiến khi classpath thay đổi hoặc dự án đăng ký thêm ArchUnit verification. Spring Modulith tích hợp tùy chọn với jMolecules ArchUnit và có thể tự động chạy các DDD verification khi thư viện phù hợp hiện diện. Các rule Hexagonal, Layered, Onion hoặc custom ArchRule cần được xác định và đăng ký theo cấu hình tương ứng; không nên mặc định mọi rule của jMolecules đều tự chạy.

Hãy phân biệt ba quy tắc module cốt lõi với additional verification, kiểm tra dependency graph và phiên bản thư viện, rồi đọc diagnostic để xác định rule và source reference. VerificationOptions cho phép giữ rule mặc định, thêm rule mới, thay tập additional rule hoặc tắt nhóm bổ sung để khoanh vùng. Việc tắt rule chỉ là công cụ chẩn đoán hoặc quyết định kiến trúc có chủ đích; không dùng nó để che violation mà nhóm chưa hiểu. Khi xác định đúng nguồn, nhóm có thể sửa mô hình domain, điều chỉnh custom rule hoặc loại bỏ integration không cần thiết mà vẫn giữ các ranh giới module cốt lõi được bảo vệ.

## Tài liệu tham khảo

- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — VerificationOptions API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)
- [Spring Modulith — ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [jMolecules — Concepts and DDD model](https://github.com/xmolecules/jmolecules)
- [jMolecules Integrations — ArchUnit rules](https://github.com/xmolecules/jmolecules-integrations/tree/main/jmolecules-archunit)

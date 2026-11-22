# Tag và điều kiện bật hoặc tắt kiểm thử

Một dự án Spring thường có nhiều loại kiểm thử: unit test chạy nhanh, kiểm thử controller, kiểm thử repository cần database, kiểm thử tích hợp với dịch vụ bên ngoài và một số bài kiểm thử chỉ phù hợp với hệ điều hành hoặc phiên bản Java nhất định. Nếu mọi bài kiểm thử luôn chạy cùng nhau, vòng phản hồi khi phát triển có thể chậm; nếu tùy tiện bỏ qua test, pipeline lại có thể xanh dù những rủi ro quan trọng chưa được kiểm chứng.

JUnit Jupiter cung cấp hai cơ chế bổ trợ nhau để tổ chức việc chạy test: **tag** để phân loại và lọc nhóm kiểm thử, và **condition** để bật hoặc tắt một test dựa trên môi trường hay điều kiện thực thi. Ngoài ra, JUnit có `Assumptions` để dừng một lần chạy khi giả định cần thiết không đúng. Hiểu rõ sự khác nhau giữa các cơ chế này giúp nhóm chọn đúng test cho từng giai đoạn mà vẫn giữ được độ tin cậy của kết quả.

## 1. Phân biệt tag, condition và assumption

Ba cơ chế giải quyết ba nhu cầu khác nhau:

| Cơ chế | Mục đích | Thời điểm tác động | Ví dụ |
| --- | --- | --- | --- |
| Tag | Gắn nhãn để chọn hoặc loại một nhóm test | Khi nền tảng kiểm thử lọc test cần chạy | Chỉ chạy `unit`, loại `slow` |
| Condition | Quyết định test có được thực thi trong môi trường hiện tại hay không | Khi JUnit đánh giá điều kiện thực thi | Chỉ chạy trên Linux hoặc khi có biến môi trường |
| Assumption | Kiểm tra giả định tại thời điểm chạy; nếu sai, dừng phần còn lại của lần test đó | Trong quá trình thực thi test | Bỏ qua phần kiểm tra cần một dịch vụ tùy chọn khi dịch vụ không sẵn sàng |

Tag không tự làm test bị bỏ qua. Nó chỉ cung cấp nhãn; build tool hoặc JUnit Platform phải được cấu hình để chọn hay loại nhãn đó. Condition tác động đến việc test có được chạy hay không. Assumption được kiểm tra trong thân test hoặc lifecycle method và có thể đánh dấu lần chạy là aborted/skipped khi giả định không thỏa mãn.

Ví dụ, một repository test có thể mang tag `integration` và `database`. Khi chạy bộ test nhanh, Gradle loại tag `integration`; khi chạy pipeline tích hợp, Gradle chọn `integration` nhưng loại `slow`. Nếu test chỉ dành cho Linux, `@EnabledOnOs(OS.LINUX)` quyết định điều kiện môi trường ngay cả khi tag đã được chọn.

## 2. Gắn tag bằng `@Tag`

JUnit Jupiter cung cấp annotation `@Tag` trong package `org.junit.jupiter.api`. Có thể đặt tag ở cấp class hoặc method.

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("integration")
class OrderRepositoryTest {

    @Test
    void savesAndReloadsAnOrder() {
        // Kiểm tra thao tác với database
    }

    @Test
    @Tag("slow")
    void loadsOrdersForALargeCustomerDataset() {
        // Kiểm tra với bộ dữ liệu lớn
    }
}
```

Trong ví dụ này, các test thuộc class được gắn nhãn `integration`; phương thức thứ hai có thêm nhãn `slow`. Vì vậy, test thứ hai có cả hai tag. Khi một bộ lọc loại `slow`, phương thức đó bị loại dù class vẫn được chọn theo `integration`.

Một test có thể mang nhiều tag. Dùng container `@Tags` để khai báo nhiều nhãn tại cùng vị trí:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Tags;

@Tags({
    @Tag("integration"),
    @Tag("database")
})
class CustomerRepositoryTest {

    @Test
    void findsCustomerByEmail() {
        // ...
    }
}
```

Có thể kết hợp tag ở class và method để biểu diễn các chiều phân loại khác nhau. Ví dụ, class được gắn `integration`, còn một số method được gắn thêm `slow` hoặc `external`.

### Chọn cách đặt tên tag

Tag nên mô tả thuộc tính ổn định của test, không nên biến thành một danh sách tên tùy ý. Một bộ tag có thể bắt đầu từ các nhóm:

| Nhóm | Ví dụ tag | Ý nghĩa |
| --- | --- | --- |
| Phạm vi | `unit`, `integration`, `e2e` | Mức phối hợp giữa các thành phần |
| Thành phần | `database`, `http`, `messaging`, `security` | Ranh giới hoặc hạ tầng được kiểm tra |
| Thời gian/tài nguyên | `slow`, `long-running` | Chi phí chạy đáng kể |
| Mục đích pipeline | `smoke`, `critical` | Bộ test đại diện hoặc có mức ưu tiên cao |
| Môi trường phụ thuộc | `external`, `container` | Cần dịch vụ ngoài hoặc hạ tầng bổ sung |

Không cần gắn mọi tag cho mọi test. Một test có thể chỉ cần `unit`; một test khác có thể có `integration` và `database`. Chỉ thêm nhãn khi nó giúp nhóm tạo một bộ lọc có ích hoặc hiểu rõ phạm vi kiểm thử.

Nên dùng chữ thường, tên ngắn và nhất quán, chẳng hạn `database` thay vì luân phiên `db`, `Database` và `database-test`. Tránh tên có khoảng trắng hoặc ký tự đặc biệt khiến cấu hình lọc khó đọc. Tài liệu của dự án nên ghi rõ ý nghĩa của từng tag và pipeline nào sử dụng nó.

## 3. Lọc tag bằng JUnit Platform

JUnit Jupiter chạy trên JUnit Platform. Việc lọc test thường được cấu hình tại build tool hoặc test launcher. Hai thao tác cơ bản là:

- **Include:** chỉ chọn các test có tag phù hợp.
- **Exclude:** loại các test có tag phù hợp khỏi nhóm đã chọn.

Khi một test mang nhiều tag, chỉ cần một tag bị exclude là test bị loại. Vì thế, nếu class mang `integration` và method mang thêm `slow`, cấu hình chọn `integration` nhưng loại `slow` sẽ không chạy method đó.

### Gradle

Với Gradle Groovy DSL:

```groovy
tasks.test {
    useJUnitPlatform {
        includeTags 'unit'
        excludeTags 'slow', 'external'
    }
}
```

Với Gradle Kotlin DSL:

```kotlin
tasks.test {
    useJUnitPlatform {
        includeTags("unit")
        excludeTags("slow", "external")
    }
}
```

Cấu hình trên chọn test được gắn `unit`, đồng thời loại test có tag `slow` hoặc `external`. Nếu không khai báo include tag, Gradle thường chạy tất cả test được phát hiện trừ những test bị loại bởi exclude filter và các điều kiện khác.

Một dự án có thể định nghĩa các task riêng cho từng nhóm. Ví dụ task `test` chạy nhanh trong lúc phát triển, còn task `integrationTest` chạy bộ tích hợp ở CI. Khi tạo task riêng, cần cấu hình source set, classpath và test task theo cách dự án đang tổ chức; tag chỉ là một phần của bộ lọc, không tự tạo ra task mới.

### Maven Surefire

Với Maven Surefire phiên bản hỗ trợ JUnit Platform, có thể dùng `groups` và `excludedGroups` để chọn tag:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <groups>unit</groups>
        <excludedGroups>slow,external</excludedGroups>
    </configuration>
</plugin>
```

Ở cấu hình này, Surefire chỉ chạy test thuộc nhóm `unit` và loại các test có tag `slow` hoặc `external`. Hãy dùng phiên bản plugin tương thích với JUnit Platform và dependency `junit-jupiter-engine` của dự án. Nếu dự án có cấu hình Maven profile riêng cho integration test, hãy kiểm tra profile đó có ghi đè hoặc bổ sung filter theo đúng ý định hay không.

### JUnit Platform Suite

Khi muốn định nghĩa một bộ test suite bằng mã Java, có thể dùng module JUnit Platform Suite:

```java
import org.junit.platform.suite.api.ExcludeTags;
import org.junit.platform.suite.api.IncludeTags;
import org.junit.platform.suite.api.SelectPackages;
import org.junit.platform.suite.api.Suite;

@Suite
@SelectPackages("com.example.orders")
@IncludeTags("integration")
@ExcludeTags("slow")
class OrderIntegrationSuite {
}
```

Suite trên tìm test trong package được chọn, chỉ giữ nhóm `integration` và loại `slow`. Cách này hữu ích khi nhóm muốn một entry point có tên rõ ràng cho một bộ test. Cần thêm dependency JUnit Platform Suite tương ứng vào test runtime.

## 4. Biểu thức tag

JUnit Platform hỗ trợ biểu thức để kết hợp nhiều tag trong những nơi chấp nhận tag expression. Các toán tử chính là:

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `!` | Phủ định | `!slow` |
| `&` | Và | `integration & database` |
| `|` | Hoặc | `smoke | critical` |
| `( )` | Gom nhóm | `(integration & database) | smoke` |

Độ ưu tiên là phủ định trước, rồi AND, rồi OR. Dùng ngoặc khi biểu thức có nhiều nhóm để người đọc không phải tự suy luận.

Ví dụ về ý nghĩa của biểu thức:

- `unit & !slow`: test thuộc `unit` và không mang `slow`.
- `integration & database`: test mang cả hai tag.
- `smoke | critical`: test mang ít nhất một trong hai tag.
- `(integration & !external) | smoke`: test tích hợp không phụ thuộc dịch vụ ngoài, hoặc test smoke.

Không phải mọi cấu hình của build tool đều nhận nguyên biểu thức tag theo cùng một cách. Hãy dùng cú pháp mà launcher hoặc plugin đang hỗ trợ. Với cấu hình Gradle phổ biến, `includeTags` và `excludeTags` thường nhận danh sách tag để chọn và loại; đừng giả định một chuỗi biểu thức bất kỳ sẽ được diễn giải giống hệt JUnit Console Launcher.

## 5. Bật test theo hệ điều hành với `@EnabledOnOs` và `@DisabledOnOs`

Một số test chỉ có ý nghĩa trên một hệ điều hành, ví dụ kiểm tra tích hợp với Unix domain socket, quyền file hoặc lệnh hệ thống. JUnit cung cấp `@EnabledOnOs` và `@DisabledOnOs` trong `org.junit.jupiter.api.condition`.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;

class NativeFileIntegrationTest {

    @Test
    @EnabledOnOs(OS.LINUX)
    void readsPermissionsUsingLinuxFileAttributes() {
        // ...
    }
}
```

Có thể dùng `@DisabledOnOs(OS.WINDOWS)` nếu test áp dụng trên các hệ điều hành khác nhưng không phù hợp với Windows. Chỉ nên giới hạn theo OS khi hành vi thực sự khác biệt hoặc phụ thuộc API của hệ điều hành. Với logic Java thuần có thể chạy đa nền tảng, hãy ưu tiên viết test đa nền tảng thay vì vô tình thu hẹp phạm vi kiểm chứng.

Các annotation điều kiện có thể đặt trên method hoặc class. Nếu đặt trên class, điều kiện áp dụng cho các test thuộc class đó. Nên ghi lý do rõ ràng nếu tắt một test trên một nền tảng cụ thể, để người bảo trì hiểu vì sao nó không chạy ở môi trường đó.

## 6. Bật test theo phiên bản Java

Ứng dụng có thể hỗ trợ nhiều phiên bản JDK, hoặc có một test kiểm tra hành vi chỉ tồn tại ở một phiên bản nhất định. JUnit cung cấp `@EnabledOnJre`, `@DisabledOnJre`, `@EnabledForJreRange` và `@DisabledForJreRange`.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnJre;
import org.junit.jupiter.api.condition.JRE;

class RuntimeCompatibilityTest {

    @Test
    @EnabledOnJre(JRE.JAVA_21)
    void verifiesBehaviorSpecificToJava21() {
        // ...
    }
}
```

Nếu cần kiểm tra một dải phiên bản:

```java
@Test
@EnabledForJreRange(min = JRE.JAVA_17, max = JRE.JAVA_21)
void verifiesSupportedRuntimeRange() {
    // ...
}
```

Điều kiện theo JRE hữu ích khi kiểm tra tương thích runtime, API hoặc hành vi phụ thuộc phiên bản. Nó không thay thế ma trận CI chạy ứng dụng trên các JDK được hỗ trợ. Nếu dự án cam kết hỗ trợ Java 17 và 21, pipeline vẫn cần thực sự chạy test trên cả hai runtime; một annotation chỉ quyết định test nào có hiệu lực trong runtime hiện tại.

## 7. Bật hoặc tắt test theo system property

System property phù hợp khi build hoặc launcher chủ động truyền một cờ cấu hình. Dùng `@EnabledIfSystemProperty` hoặc `@DisabledIfSystemProperty` để kiểm tra tên property và biểu thức regex của giá trị.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

class ExternalPaymentIntegrationTest {

    @Test
    @EnabledIfSystemProperty(named = "run.external.tests", matches = "true")
    void chargesPaymentThroughConfiguredSandbox() {
        // Gọi payment sandbox đã được cấu hình cho test
    }
}
```

Có thể bật test bằng cách truyền property cho JVM:

```bash
./gradlew test -Drun.external.tests=true
```

Hoặc với Maven:

```bash
mvn test -Drun.external.tests=true
```

Nếu property không tồn tại hoặc không khớp regex, test không được bật. Có thể dùng `@DisabledIfSystemProperty` để diễn đạt điều kiện ngược lại. Vì thuộc tính `matches` là biểu thức chính quy, hãy viết pattern đủ rõ; nếu muốn so khớp chính xác chuỗi `true`, không cần dùng pattern rộng như `.*true.*`.

Không dùng system property để giấu một test thiết yếu khi pipeline đang cấu hình sai. Nếu test tích hợp bắt buộc phải chạy trong job phát hành, pipeline cần cung cấp property và kiểm tra cấu hình trước khi chạy test. Một test bị disable vì thiếu property có thể khiến báo cáo xanh nhưng không cung cấp bằng chứng mà job cần.

## 8. Bật hoặc tắt test theo environment variable

Environment variable phù hợp khi cấu hình đến từ môi trường chạy, container hoặc CI. JUnit cung cấp `@EnabledIfEnvironmentVariable` và `@DisabledIfEnvironmentVariable`.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

class StagingContractTest {

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_STAGING_CONTRACT_TESTS",
        matches = "true"
    )
    void verifiesOrderApiAgainstStagingContract() {
        // ...
    }
}
```

Có thể bật biến môi trường trong shell trước khi chạy build. Trên Linux/macOS:

```bash
RUN_STAGING_CONTRACT_TESTS=true ./gradlew test
```

Trên PowerShell:

```powershell
$env:RUN_STAGING_CONTRACT_TESTS = "true"
./gradlew test
```

Nếu biến không được đặt hoặc giá trị không khớp regex, JUnit bỏ qua test theo điều kiện. Đây là cách tiện lợi cho test phụ thuộc staging hoặc sandbox. Tuy nhiên, nếu staging là một phần bắt buộc của quy trình release, hãy để job release xác nhận biến đã được bật và endpoint có cấu hình hợp lệ; không nên để thiếu biến trở thành một lần bỏ qua im lặng.

## 9. Tắt test vô điều kiện bằng `@Disabled`

`@Disabled` dùng khi cần tạm thời vô hiệu hóa một test hoặc cả class. Nên cung cấp lý do để người đọc biết vì sao test không chạy và điều kiện để bật lại.

```java
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

class LegacyPaymentIntegrationTest {

    @Test
    @Disabled("Sandbox thanh toán đang ngừng bảo trì; theo dõi OPS-241")
    void verifiesLegacyGatewaySettlement() {
        // ...
    }
}
```

`@Disabled` là quyết định tắt rõ ràng, không phụ thuộc môi trường. Nó phù hợp với một test đang hỏng vì lỗi đã biết hoặc một tính năng chưa thể kiểm tra trong giai đoạn hiện tại. Không nên để annotation này tồn tại vô thời hạn mà không có người chịu trách nhiệm, lý do hoặc kế hoạch bật lại.

Nếu chỉ cần tắt trên một môi trường, hãy cân nhắc annotation điều kiện phù hợp thay vì `@Disabled`. Nếu test bắt buộc phải chạy trong CI, tắt nó có thể làm mất bảo vệ quan trọng; nên theo dõi các test bị disable trong báo cáo và rà soát chúng định kỳ.

## 10. Dùng `Assumptions` cho điều kiện được xác định khi chạy

JUnit Jupiter cung cấp `Assumptions` để kiểm tra một giả định trong quá trình thực thi. Nếu giả định không đúng, test bị abort tại vị trí đó và phần còn lại của method không chạy.

```java
import static org.junit.jupiter.api.Assumptions.assumeTrue;

@Test
void readsCustomerFromOptionalSandbox() {
    assumeTrue(isSandboxAvailable(), "Sandbox không sẵn sàng");

    Customer customer = sandboxClient.findCustomer("customer-42");

    assertNotNull(customer);
}
```

Khác với `@EnabledIfEnvironmentVariable`, assumption có thể dựa trên kết quả kiểm tra động như một endpoint có phản hồi hay không. Hãy dùng timeout cho phép kiểm tra sẵn sàng và tránh gọi một dịch vụ bên ngoài vô thời hạn.

`assumingThat` cho phép chỉ chạy một đoạn assertion khi điều kiện đúng, còn phần còn lại của test vẫn tiếp tục:

```java
import static org.junit.jupiter.api.Assumptions.assumingThat;

@Test
void formatsCustomerResponse() {
    Customer customer = sampleCustomer();

    assertEquals("customer-42", customer.id());

    assumingThat(customer.hasPremiumStatus(), () -> {
        assertNotNull(customer.premiumBenefits());
    });
}
```

`assumeTrue` phù hợp khi toàn bộ phần còn lại không có ý nghĩa nếu điều kiện sai. `assumingThat` phù hợp khi chỉ một nhóm assertion là có điều kiện, còn các assertion cơ bản vẫn phải chạy.

Không nên dùng assumption để bỏ qua lỗi của chính ứng dụng. Ví dụ, nếu test yêu cầu database mà database là dependency bắt buộc trong CI, `assumeTrue(databaseIsAvailable())` có thể biến sự cố hạ tầng thành test aborted và làm job có vẻ thành công. Trong job bắt buộc, nên để bước khởi tạo hoặc preflight thất bại rõ ràng khi dependency không sẵn sàng.

## 11. Điều kiện ở cấp class và method

Tag và các annotation condition thường có thể đặt ở cấp class hoặc method. Chọn cấp đặt dựa trên phạm vi mà điều kiện thực sự áp dụng.

```java
@EnabledOnOs(OS.LINUX)
@Tag("integration")
class LinuxSocketIntegrationTest {

    @Test
    void opensUnixDomainSocket() {
        // ...
    }

    @Test
    @Tag("slow")
    void transfersLargePayloadOverSocket() {
        // ...
    }
}
```

Điều kiện OS ở class áp dụng cho cả hai test; tag `slow` chỉ bổ sung cho phương thức truyền payload lớn. Cách tổ chức này làm rõ các thuộc tính chung và riêng.

Đối với test lồng nhau, hãy kiểm tra rõ annotation được đặt ở enclosing class hay nested class để tránh vô tình áp dụng điều kiện quá rộng. Nếu một nhóm chỉ chạy khi có dịch vụ ngoài, có thể đặt điều kiện ở class chứa các test phụ thuộc dịch vụ đó. Không đặt điều kiện lên class lớn nếu chỉ một test duy nhất cần dependency tùy chọn.

## 12. Kết hợp tag với condition trong dự án Spring

Tag và condition có thể được dùng đồng thời. Tag giúp pipeline chọn nhóm test; condition bảo đảm test chỉ chạy trong môi trường phù hợp.

```java
@Tag("integration")
@Tag("database")
@DataJpaTest
class OrderRepositoryIntegrationTest {

    @Test
    void persistsOrderAndReloadsIt() {
        // ...
    }
}
```

Test này được phân loại là integration/database và sử dụng test slice JPA. Nếu database được cung cấp bằng Testcontainers, dependency đó cần được cấu hình trong test runtime. Việc gắn tag không tự khởi chạy container.

Một ví dụ khác là kiểm thử contract với staging:

```java
@Tag("integration")
@Tag("external")
class OrderStagingContractTest {

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_STAGING_CONTRACT_TESTS",
        matches = "true"
    )
    void returnsOrderAccordingToPublishedContract() {
        // ...
    }
}
```

Ở đây, pipeline có thể loại `external` khỏi vòng chạy nhanh. Job contract riêng chọn nhóm `integration` hoặc `external`; condition tiếp tục xác nhận cờ môi trường đã bật. Nếu job đó bắt buộc phải chạy test, cấu hình CI cần đảm bảo biến môi trường có mặt và không chấp nhận việc toàn bộ test bị skip.

Một điểm quan trọng trong Spring: tag JUnit không tự kích hoạt `@ActiveProfiles`, không thay đổi Spring profile, không tạo bean và không thay thế cấu hình datasource. Nếu test cần profile `integration`, hãy khai báo `@ActiveProfiles("integration")` hoặc cấu hình tương ứng riêng. Tag chỉ phân loại test cho JUnit Platform.

## 13. Điều gì xảy ra khi test bị lọc hoặc bị disable?

Khi một test bị loại bởi tag filter, JUnit Platform không đưa test đó vào nhóm được chọn để thực thi. Khi một condition không thỏa mãn hoặc test có `@Disabled`, test được nhận diện nhưng không chạy phần test body và thường xuất hiện ở trạng thái skipped trong báo cáo. Khi assumption thất bại trong quá trình chạy, lần thực thi thường được báo là aborted.

Sự khác biệt này hữu ích khi đọc báo cáo:

| Trạng thái | Nguyên nhân thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| Không xuất hiện trong nhóm được chọn | Bị loại bởi include/exclude tag filter hoặc selector | Cấu hình build tool, suite và tag của test |
| Skipped/disabled | `@Disabled` hoặc condition không thỏa mãn | Lý do disable, property, environment variable, OS hoặc JRE |
| Aborted | Assumption không đúng hoặc test chủ động abort | Giả định nào không thỏa mãn và liệu đó có phải dependency tùy chọn không |
| Failed | Assertion, exception hoặc lỗi khởi tạo/thực thi | Lỗi test, cấu hình hoặc ứng dụng thực tế |

Không nên xem số test bị skip hoặc aborted là chi tiết không quan trọng. Một job có thể báo thành công trong khi một nhóm test quan trọng không được chạy. Hãy công khai số lượng test bị bỏ qua và kiểm tra nguyên nhân của chúng trong pipeline có vai trò bảo vệ release.

## 14. Thiết kế bộ tag cho các giai đoạn CI

Một bộ tag đơn giản có thể hỗ trợ các vòng chạy khác nhau:

| Giai đoạn | Nhóm được chọn | Nhóm loại trừ | Mục đích |
| --- | --- | --- | --- |
| Khi lập trình | `unit` | `slow`, `external` | Phản hồi nhanh cho thay đổi nhỏ |
| Pull request | `unit`, `smoke` theo task riêng | `external`, `long-running` | Kiểm tra nhanh các hành vi quan trọng |
| Pipeline tích hợp | `integration` | `long-running` nếu có job riêng | Kiểm tra phối hợp giữa Spring và hạ tầng |
| Kiểm tra hợp đồng | `external` hoặc tag contract đã thống nhất | Không loại nhóm contract bắt buộc | Xác nhận tương thích với hệ thống liên quan |
| Trước phát hành | Bộ test theo chính sách release | Chỉ loại test được phê duyệt tạm thời | Tạo bằng chứng cho các luồng rủi ro cao |

Bảng chỉ là ví dụ về cách tổ chức. Dự án cần xác định tag nào được gắn cho từng test và job nào chịu trách nhiệm chạy nó. Nếu một test quan trọng không thuộc bất kỳ job bắt buộc nào, nó có thể không bao giờ được thực thi dù vẫn tồn tại trong source code.

Tránh tạo quá nhiều tag đồng nghĩa hoặc tag theo từng cá nhân. Khi một test có các nhãn `integration`, `database` và `slow`, người đọc cần hiểu mỗi nhãn đại diện cho một thuộc tính độc lập. Nếu hai tag luôn được dùng cùng nhau và không tạo ra bộ lọc khác nhau, có thể chỉ cần một tag rõ nghĩa hơn.

## 15. Điều kiện bật/tắt phải có tính ổn định

Điều kiện chạy test là một phần của thiết kế pipeline. Nếu điều kiện phụ thuộc dữ liệu ngẫu nhiên, trạng thái mạng không ổn định hoặc thời điểm chạy, kết quả test có thể chập chờn.

Hãy ưu tiên các điều kiện:

- Được xác định rõ trước khi chạy test, chẳng hạn OS, JRE hoặc property do build truyền vào.
- Có giá trị mặc định dễ hiểu và được ghi nhận trong cấu hình dự án.
- Có lý do nghiệp vụ hoặc kỹ thuật rõ ràng cho việc test không chạy.
- Có thể quan sát trong báo cáo CI để người vận hành biết test đã được chạy hay bỏ qua.
- Được kiểm tra lại khi thay đổi môi trường, JDK hoặc hạ tầng.

Với dịch vụ bên ngoài, hãy phân biệt rõ hai tình huống: test phụ thuộc tùy chọn có thể skip khi môi trường không được cấp; test thuộc hợp đồng release phải thất bại nếu môi trường bắt buộc không sẵn sàng. Đừng biến lỗi cấu hình thành một điều kiện skip vô tình.

Nếu dùng `@EnabledIfSystemProperty` hoặc `@EnabledIfEnvironmentVariable`, nên đặt tên cờ mang ý nghĩa như `run.external.tests` hoặc `RUN_STAGING_CONTRACT_TESTS`. Tránh các cờ mơ hồ như `enabled=true`, vì sau này khó biết nó bật nhóm hành vi nào.

## 16. Tạo điều kiện tùy chỉnh bằng extension khi cần

Các annotation có sẵn bao phủ nhiều trường hợp phổ biến. Khi dự án cần một quy tắc bật/tắt dùng chung phức tạp hơn, JUnit Jupiter cho phép viết extension triển khai `ExecutionCondition`.

Ví dụ khung đơn giản:

```java
import org.junit.jupiter.api.extension.ConditionEvaluationResult;
import org.junit.jupiter.api.extension.ExecutionCondition;
import org.junit.jupiter.api.extension.ExtensionContext;

class ExternalServiceCondition implements ExecutionCondition {

    @Override
    public ConditionEvaluationResult evaluateExecutionCondition(
            ExtensionContext context) {

        String enabled = System.getProperty("run.external.tests", "false");

        if (Boolean.parseBoolean(enabled)) {
            return ConditionEvaluationResult.enabled(
                "External tests were enabled"
            );
        }

        return ConditionEvaluationResult.disabled(
            "Set -Drun.external.tests=true to enable external tests"
        );
    }
}
```

Đăng ký extension bằng `@ExtendWith`:

```java
@ExtendWith(ExternalServiceCondition.class)
class ExternalGatewayTest {

    @Test
    void verifiesGatewayContract() {
        // ...
    }
}
```

Extension giúp gom quy tắc vào một nơi và trả về lý do enabled/disabled rõ ràng. Tuy nhiên, không nên tạo custom extension cho một điều kiện đơn giản mà annotation có sẵn đã xử lý được. Một extension dùng chung phải có tài liệu, hành vi ổn định và không che giấu lỗi cấu hình quan trọng.

Khi kiểm tra dịch vụ có sẵn hay không, cần cân nhắc việc gọi mạng trong `evaluateExecutionCondition`. Việc này có thể làm quá trình discovery chậm hoặc không ổn định. Nếu phải kiểm tra dependency động, dùng timeout ngắn, tránh side effect và cân nhắc thực hiện preflight riêng trong pipeline để lỗi hạ tầng được báo cáo rõ ràng.

## 17. Ví dụ chiến lược đầy đủ cho module đơn hàng

Giả sử ứng dụng có các test cho đơn hàng, repository và cổng thanh toán. Nhóm có thể phân loại và bật/tắt như sau:

```java
@Tag("unit")
class OrderPricingTest {

    @Test
    void calculatesTotalAfterApplyingEligibleDiscount() {
        // ...
    }
}
```

```java
@Tag("integration")
@Tag("database")
@DataJpaTest
class OrderRepositoryTest {

    @Test
    void persistsAndReloadsOrderWithLineItems() {
        // ...
    }
}
```

```java
@Tag("integration")
@Tag("external")
class PaymentGatewayContractTest {

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_PAYMENT_SANDBOX_TESTS",
        matches = "true"
    )
    void acceptsPaymentRequestAccordingToGatewayContract() {
        // ...
    }
}
```

Trong vòng chạy nhanh, build chọn `unit` và loại `slow`, `external`. Trong job database, build chọn `integration` và `database`; trong job payment sandbox, build chọn `external` hoặc `integration` theo chính sách của dự án, đồng thời bật `RUN_PAYMENT_SANDBOX_TESTS=true`.

Với test sandbox bắt buộc, pipeline nên kiểm tra cờ đã được bật trước khi chạy. Nếu cờ bị thiếu, job cần báo cấu hình không hợp lệ thay vì chỉ để JUnit đánh dấu test là skipped rồi kết thúc thành công.

## 18. Những sai lầm thường gặp

- **Gắn tag nhưng không cấu hình filter:** test vẫn chạy cùng toàn bộ suite; tag không tự tạo ra nhóm chạy riêng.
- **Nhầm tag với Spring profile:** `@Tag("integration")` không kích hoạt `@Profile("integration")` hoặc `@ActiveProfiles`.
- **Gắn `@Disabled` mà không có lý do:** người bảo trì không biết vì sao test ngừng chạy và khi nào có thể bật lại.
- **Skip test thiết yếu khi dependency lỗi:** pipeline có thể xanh dù database hoặc service bắt buộc không hoạt động.
- **Dùng condition thay cho kiểm tra tương thích:** `@EnabledOnJre` không chứng minh ứng dụng chạy được trên mọi JDK được hỗ trợ; CI cần chạy ma trận runtime.
- **Dùng assumption cho lỗi sản phẩm:** assumption không nên biến một assertion thất bại hoặc lỗi bắt buộc thành trạng thái aborted.
- **Tag quá chi tiết:** quá nhiều nhãn làm cấu hình filter phức tạp và khó duy trì.
- **Không theo dõi test bị bỏ qua:** test bị skip lâu ngày có thể mất giá trị bảo vệ mà không ai nhận ra.
- **Điều kiện có side effect:** kiểm tra điều kiện bằng cách khởi tạo dữ liệu hoặc thay đổi trạng thái có thể làm discovery khó dự đoán.

## 19. Quy trình lựa chọn cơ chế

Khi thêm một test mới, hãy xác định nhu cầu theo thứ tự:

1. **Test thuộc nhóm nào?** Gắn tag như `unit`, `integration`, `database` hoặc `external` nếu nhóm cần lọc test theo thuộc tính đó.
2. **Có môi trường cụ thể mới chạy được không?** Dùng annotation condition cho OS, JRE, system property hoặc environment variable.
3. **Điều kiện chỉ biết được trong lúc chạy?** Dùng `Assumptions` nếu đó thật sự là giả định tùy chọn; nếu dependency bắt buộc, hãy để preflight hoặc test thất bại rõ ràng.
4. **Có cần tắt test tạm thời?** Dùng `@Disabled` kèm lý do, người/issue chịu trách nhiệm và kế hoạch bật lại.
5. **Pipeline nào phải chạy test này?** Đảm bảo có ít nhất một job bắt buộc chọn nhóm tag tương ứng và quan sát được test bị skip.

Một bộ kiểm thử đáng tin cậy không chỉ có nhiều test mà còn phải cho biết test nào được chạy, test nào bị loại và vì sao. Tag tạo khả năng tổ chức bộ kiểm thử theo mục đích; condition giới hạn test vào môi trường phù hợp; assumption xử lý giả định tại thời điểm chạy. Khi dùng đúng vai trò và theo dõi các test bị bỏ qua, nhóm có thể tăng tốc vòng phản hồi mà vẫn giữ được bằng chứng kiểm thử cần thiết cho ứng dụng Spring.

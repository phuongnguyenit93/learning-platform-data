# @DisabledInAotMode và điều kiện kiểm thử theo môi trường

Không phải mọi test đều phù hợp với mọi chế độ chạy. Một số test dựa vào hành vi chỉ có ở runtime thông thường, trong khi Spring có thể tạo trước metadata và `ApplicationContext` để chạy theo cơ chế Ahead-of-Time (AOT). Một số test khác chỉ có ý nghĩa trên một hệ điều hành, phiên bản JDK hoặc môi trường CI có sẵn dịch vụ bên ngoài.

Spring Test cung cấp `@DisabledInAotMode` để loại trừ rõ ràng test không tương thích với AOT mode. Spring TestContext và JUnit Jupiter cũng có các điều kiện bật/tắt test theo biểu thức, system property, environment variable, hệ điều hành và phiên bản Java. Chọn điều kiện theo nguyên nhân thực tế giúp suite chạy đúng phạm vi mà không che giấu lỗi cần phát hiện.

## 1. AOT mode trong kiểm thử Spring

Ahead-of-Time processing chuẩn bị một phần công việc mà Spring thường thực hiện khi khởi động ứng dụng. Thay vì chỉ dựa vào quá trình quét và phân tích runtime, Spring có thể phân tích cấu hình lúc build, sinh mã khởi tạo và dùng các artifact đã sinh khi chạy.

Với Spring TestContext Framework, AOT support cho phép xử lý trước các test `ApplicationContext` phù hợp và tạo initializer tương ứng. Khi test chạy trong AOT mode, Spring có thể sử dụng cấu hình đã được chuẩn bị thay cho toàn bộ quá trình dựng context theo cách thông thường.

Điều này giúp ứng dụng khởi động nhanh hơn và hỗ trợ các môi trường như native image. Tuy nhiên, một test có thể phụ thuộc vào hành vi chỉ có trong quá trình khởi tạo động hoặc một tùy chỉnh context không tương thích với đường chạy AOT mà dự án đang sử dụng.

Không nên đồng nhất AOT với việc test chạy trên một hệ điều hành hoặc JDK cụ thể. AOT là chế độ xử lý và khởi tạo ứng dụng; điều kiện theo OS, JDK hoặc environment variable là các chiều môi trường riêng.

## 2. @DisabledInAotMode dùng khi nào?

`@DisabledInAotMode` là annotation của Spring TestContext, nằm trong package `org.springframework.test.context.aot`. Annotation này có từ Spring Framework 6.2 và đánh dấu test class hoặc test method sẽ bị disable khi test chạy trong AOT mode.

Ví dụ ở cấp class:

```java
import org.springframework.test.context.aot.DisabledInAotMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfig.class)
@DisabledInAotMode
class RuntimeOnlyContextTests {

    @Test
    void checksRuntimeOnlyContextCustomization() {
        // Test này chỉ chạy trong chế độ test thông thường.
    }
}
```

Khi AOT mode không được bật, test vẫn được thực thi như bình thường. Khi AOT mode được bật, Spring Test bỏ qua các test thuộc phạm vi annotation.

Có thể chỉ disable một method trong class:

```java
@SpringJUnitConfig(TestConfig.class)
class ContextTests {

    @Test
    void aotCompatibleTestStillRuns() {
        // Test này vẫn được chạy trong AOT mode.
    }

    @Test
    @DisabledInAotMode
    void testRequiresRuntimeOnlyBehavior() {
        // Chỉ test này bị disable trong AOT mode.
    }
}
```

Đặt annotation ở cấp class khi toàn bộ test class phụ thuộc vào hành vi không tương thích. Đặt ở cấp method khi chỉ một kịch bản cần runtime behavior đặc biệt. Giữ các test tương thích với AOT hoạt động để vẫn có độ bao phủ cho chế độ này.

## 3. Khi nào nên disable test trong AOT mode?

Chỉ dùng `@DisabledInAotMode` khi đã xác định một test không thể chạy đúng trong AOT mode hiện tại và không có cách cấu hình phù hợp để hỗ trợ nó. Ví dụ có thể là một test phụ thuộc vào thay đổi cấu trúc `ApplicationContext` động sau khi các artifact AOT đã được sinh, hoặc một cơ chế test fixture không tương thích với initializer đã sinh.

Trước khi disable, nên cân nhắc:

- Có thể viết lại test để dùng bean hoặc cấu hình được khai báo trước thời điểm AOT processing không?
- Có thể tách phần kiểm tra logic thuần Java ra khỏi phần phụ thuộc context runtime không?
- Có thể tạo một test khác xác nhận cùng hợp đồng bằng cấu hình tương thích AOT không?
- Test có thực sự không áp dụng trong AOT mode, hay chỉ đang thiếu cấu hình AOT cần thiết?

Không dùng annotation này như cách bỏ qua một lỗi AOT chưa được điều tra. Nếu một controller, service hoặc cấu hình production quan trọng không hoạt động trong AOT mode, cần sửa hoặc bổ sung kiểm thử cho đường chạy AOT thay vì disable test bao phủ nó.

## 4. Phạm vi và cách Spring xử lý annotation

`@DisabledInAotMode` có thể được đặt trên test class hoặc test method. Annotation ở class áp dụng cho các test method trong class; annotation ở method chỉ ảnh hưởng đến method đó. Annotation này dành cho điều kiện AOT của Spring TestContext, không phải điều kiện chọn hệ điều hành hay environment variable.

Có thể đặt annotation cùng các annotation cấu hình test thông thường:

```java
@SpringBootTest
@DisabledInAotMode
class RuntimeConfigurationTests {
    // Test context được cấu hình như bình thường khi không chạy AOT.
}
```

Khi chạy trong AOT mode, Spring Test đánh giá điều kiện và disable test tương ứng. Test không bị xóa khỏi source code hoặc khỏi lần chạy thông thường; trạng thái disable phụ thuộc chế độ thực thi.

## 5. Điều kiện theo biểu thức với Spring @EnabledIf và @DisabledIf

Spring TestContext cung cấp `@EnabledIf` và `@DisabledIf` trong package `org.springframework.test.context.junit.jupiter`. Hai annotation này dùng biểu thức Spring Expression Language (SpEL) để quyết định test có được chạy hay không.

Ví dụ chỉ chạy test khi system property `test.environment` có giá trị `integration`:

```java
import org.springframework.test.context.junit.jupiter.EnabledIf;

@Test
@EnabledIf(expression = "#{systemProperties['test.environment'] == 'integration'}")
void runsOnlyInIntegrationEnvironment() {
    // Kiểm tra phụ thuộc vào môi trường integration.
}
```

Ngược lại, dùng `@DisabledIf` khi muốn bỏ qua test nếu điều kiện đúng:

```java
import org.springframework.test.context.junit.jupiter.DisabledIf;

@Test
@DisabledIf(expression = "#{systemEnvironment['CI'] == 'true'}")
void skipsWhenRunningOnCi() {
    // Chỉ chạy khi điều kiện CI không đúng.
}
```

Các biểu thức có thể truy cập `systemProperties` và `systemEnvironment`. Thuộc tính `loadContext` mặc định là `false`; chỉ bật `loadContext = true` khi biểu thức cần bean hoặc thông tin phải lấy từ `ApplicationContext`. Việc tải context chỉ để kiểm tra một biến môi trường đơn giản thường không cần thiết.

Ví dụ dùng bean trong context khi thật sự cần:

```java
@Test
@EnabledIf(
        expression = "#{featureSwitch.enabled}",
        loadContext = true)
void runsWhenFeatureSwitchIsEnabled() {
    // FeatureSwitch là bean trong test ApplicationContext.
}
```

`@EnabledIf` và `@DisabledIf` của Spring phù hợp khi điều kiện cần biểu thức SpEL hoặc thông tin từ Spring context. Nếu chỉ cần so khớp một system property hoặc environment variable, annotation điều kiện có sẵn của JUnit thường đơn giản hơn.

## 6. Điều kiện theo environment variable với JUnit Jupiter

JUnit Jupiter cung cấp `@EnabledIfEnvironmentVariable` và `@DisabledIfEnvironmentVariable` trong package `org.junit.jupiter.api.condition`.

Chỉ chạy test khi biến `RUN_EXTERNAL_TESTS` có giá trị `true`:

```java
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

@Test
@EnabledIfEnvironmentVariable(named = "RUN_EXTERNAL_TESTS", matches = "true")
void callsExternalTestEnvironment() {
    // Test phụ thuộc vào dịch vụ bên ngoài.
}
```

Có thể áp dụng ở cấp class để toàn bộ class chỉ chạy khi môi trường phù hợp:

```java
@SpringBootTest
@EnabledIfEnvironmentVariable(named = "TEST_DATABASE_URL", matches = ".+")
class ExternalDatabaseIntegrationTests {
    // Các test cần database được cung cấp từ môi trường.
}
```

`matches` là regular expression. Biểu thức `.+` yêu cầu biến tồn tại và có ít nhất một ký tự. Điều kiện này chỉ kiểm tra biến có giá trị; test vẫn cần xác nhận dịch vụ thực sự kết nối được và xử lý lỗi khi endpoint không khả dụng.

Có thể dùng `@DisabledIfEnvironmentVariable` để diễn đạt điều kiện bỏ qua trực tiếp:

```java
@Test
@DisabledIfEnvironmentVariable(named = "OS", matches = "Windows_NT")
void usesUnixSpecificTooling() {
    // Bỏ qua trên Windows.
}
```

## 7. Điều kiện theo system property

System property thường được truyền qua tham số JVM `-Dname=value`. JUnit Jupiter cung cấp `@EnabledIfSystemProperty` và `@DisabledIfSystemProperty`.

Ví dụ chỉ chạy test khi JVM được khởi động với property bật kiểm thử tích hợp:

```java
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

@Test
@EnabledIfSystemProperty(named = "test.integration", matches = "true")
void runsWhenIntegrationPropertyIsEnabled() {
    // Test tích hợp được bật tường minh.
}
```

Có thể dùng system property để chọn implementation hoặc môi trường test, nhưng nên giữ cấu hình đó ở build/test launcher thay vì đặt property trong chính test method rồi kiểm tra lại nó. Nếu test tự bật điều kiện của mình, điều kiện không còn giúp kiểm soát môi trường thực thi.

Phân biệt system property với environment variable:

| Loại cấu hình | Cách cung cấp phổ biến | API đọc trong Java | Annotation JUnit |
|---|---|---|---|
| System property | `-Dtest.integration=true` | `System.getProperty("test.integration")` | `@EnabledIfSystemProperty` |
| Environment variable | Biến môi trường của process | `System.getenv("RUN_EXTERNAL_TESTS")` | `@EnabledIfEnvironmentVariable` |

## 8. Điều kiện theo hệ điều hành và phiên bản Java

Khi test phụ thuộc API hoặc command riêng của một hệ điều hành, dùng annotation theo OS:

```java
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.DisabledOnOs;
import org.junit.jupiter.api.condition.OS;

@Test
@EnabledOnOs(OS.LINUX)
void usesLinuxFilePermissions() {
    // Kiểm tra hành vi đặc thù của Linux.
}

@Test
@DisabledOnOs(OS.WINDOWS)
void usesUnixShellCommand() {
    // Không chạy trên Windows.
}
```

Với phiên bản Java:

```java
import org.junit.jupiter.api.condition.EnabledOnJre;
import org.junit.jupiter.api.condition.EnabledForJreRange;
import org.junit.jupiter.api.condition.JRE;

@Test
@EnabledOnJre(JRE.JAVA_21)
void verifiesJava21SpecificBehavior() {
    // Chỉ chạy trên Java 21.
}

@Test
@EnabledForJreRange(min = JRE.JAVA_17)
void runsOnSupportedJavaVersions() {
    // Chạy từ Java 17 trở lên trong phạm vi JRE được JUnit nhận diện.
}
```

Các điều kiện OS/JRE là điều kiện của JUnit, không phải của Spring TestContext. Chúng có thể dùng trong test Spring bình thường; Spring vẫn tạo context theo cấu hình test nếu điều kiện cho phép method/class được thực thi.

## 9. Kết hợp nhiều điều kiện

Một test có thể cần đồng thời một hệ điều hành và một biến môi trường cụ thể. Ví dụ test gọi công cụ chỉ có trên Linux và chỉ chạy khi CI cung cấp service:

```java
@Test
@EnabledOnOs(OS.LINUX)
@EnabledIfEnvironmentVariable(named = "RUN_CONTAINER_TESTS", matches = "true")
void testsLinuxContainerIntegration() {
    // Cần Linux và môi trường đã bật container tests.
}
```

Khi nhiều điều kiện được khai báo, test chỉ phù hợp nếu các điều kiện cho phép nó chạy. Hãy đặt điều kiện ở phạm vi hẹp nhất cần thiết: method nếu chỉ một kịch bản phụ thuộc môi trường, class nếu toàn bộ class có cùng điều kiện.

Không nên gắn điều kiện OS hoặc biến môi trường lên một test class lớn chỉ vì một method dùng công cụ đặc thù. Tách method hoặc class giúp các test độc lập vẫn chạy trên mọi môi trường.

## 10. Dùng Assumptions khi điều kiện chỉ biết trong lúc chạy test

Annotation điều kiện được đánh giá trước khi test method thực thi. Nếu cần kiểm tra điều kiện sau khi đã gọi API hoặc khởi tạo fixture, JUnit cung cấp `Assumptions`:

```java
import static org.junit.jupiter.api.Assumptions.assumeTrue;

@Test
void checksOptionalService() {
    assumeTrue(isTestServiceAvailable(),
            "Optional test service is not available");

    // Phần kiểm thử chỉ chạy khi service sẵn sàng.
}
```

Khi assumption không thỏa, JUnit đánh dấu test là aborted (bị bỏ qua có điều kiện), không phải failed. Điều này hữu ích khi khả năng kết nối chỉ xác định được tại runtime.

Không dùng assumption để che giấu lỗi trong chính ứng dụng. Nếu service được yêu cầu phải có trong CI nhưng lại không sẵn sàng, build nên thất bại hoặc có bước kiểm tra môi trường rõ ràng thay vì âm thầm skip test.

## 11. Phân biệt điều kiện chạy test với cấu hình Spring profile

`@ActiveProfiles` chọn profile dùng để nạp bean và cấu hình cho `ApplicationContext`. Nó không tự động disable test khi profile không được chọn.

Ví dụ:

```java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationProfileTests {
    // Context được tạo với profile integration.
}
```

Nếu cần chỉ chạy test khi một profile được chọn, có thể dùng điều kiện SpEL đọc cấu hình môi trường hoặc system property mà build truyền vào. Tránh nhầm rằng `@ActiveProfiles("integration")` tự động kiểm tra profile đã được bật từ bên ngoài; annotation này chủ động yêu cầu Spring kích hoạt profile cho context của test.

`@TestPropertySource` và thuộc tính `properties` của các test annotation cũng cung cấp cấu hình cho context. Chúng thay đổi môi trường của test context, không phải cơ chế skip test.

## 12. Ví dụ tổ chức test theo môi trường

Giả sử dự án có unit test, test AOT và test tích hợp cần database ngoài:

```text
src/test/java
  service/
    OrderServiceTests.java
  context/
    RuntimeOnlyContextTests.java
  integration/
    DatabaseIntegrationTests.java
  aot/
    AotCompatibleContextTests.java
```

Các class có thể khai báo điều kiện theo mục đích:

```java
// Test logic không phụ thuộc môi trường.
class OrderServiceTests {
    // Chạy trên mọi môi trường test.
}

// Test phụ thuộc hành vi context chỉ có ở runtime thông thường.
@SpringBootTest
@DisabledInAotMode
class RuntimeOnlyContextTests {
    // Không tham gia lần chạy AOT.
}

// Test cần database do CI hoặc developer cung cấp.
@SpringBootTest
@EnabledIfEnvironmentVariable(named = "TEST_DATABASE_URL", matches = ".+")
class DatabaseIntegrationTests {
    // Chỉ chạy khi đã khai báo database URL.
}

// Test xác nhận cấu hình hoạt động trong đường chạy AOT.
@SpringBootTest
class AotCompatibleContextTests {
    // Giữ test này hoạt động trong AOT pipeline.
}
```

Việc tách phạm vi giúp đọc suite dễ hơn: test logic luôn chạy, test không tương thích AOT được đánh dấu rõ, test phụ thuộc dịch vụ ngoài có điều kiện môi trường và test AOT-compatible vẫn xác nhận đường chạy được sinh trước.

## 13. Chọn annotation theo nhu cầu

| Nhu cầu | Annotation/cơ chế | Nguồn |
|---|---|---|
| Bỏ qua test khi Spring chạy trong AOT mode | `@DisabledInAotMode` | Spring TestContext |
| Bật/tắt bằng biểu thức SpEL | `@EnabledIf`, `@DisabledIf` | Spring TestContext |
| Bật/tắt theo environment variable | `@EnabledIfEnvironmentVariable`, `@DisabledIfEnvironmentVariable` | JUnit Jupiter |
| Bật/tắt theo system property | `@EnabledIfSystemProperty`, `@DisabledIfSystemProperty` | JUnit Jupiter |
| Chỉ chạy trên OS cụ thể | `@EnabledOnOs`, `@DisabledOnOs` | JUnit Jupiter |
| Chỉ chạy trên JDK hoặc khoảng JDK | `@EnabledOnJre`, `@EnabledForJreRange` | JUnit Jupiter |
| Điều kiện chỉ xác định được trong test body | `Assumptions.assumeTrue(...)` | JUnit Jupiter |
| Chọn bean/configuration profile | `@ActiveProfiles` | Spring TestContext; không phải skip condition |

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test bị disable trong AOT dù không mong muốn | `@DisabledInAotMode` được đặt ở cấp class hoặc meta-annotation rộng | Chuyển annotation xuống đúng method hoặc bỏ annotation khi test đã tương thích |
| Test AOT không được chạy và không ai nhận ra | Dùng annotation disable quá rộng | Chỉ đánh dấu test thật sự không tương thích và giữ test AOT-compatible đại diện |
| `@EnabledIf` không đọc được bean | `loadContext` vẫn ở mặc định `false` | Đặt `loadContext = true` khi biểu thức thực sự cần bean/context |
| Điều kiện môi trường luôn false | Nhầm system property với environment variable hoặc regex không khớp | Kiểm tra cách truyền cấu hình và giá trị thực tế của biến |
| Test integration bị skip trên CI ngoài ý muốn | Pipeline chưa cung cấp biến môi trường được yêu cầu | Cấu hình biến ở job phù hợp hoặc điều chỉnh điều kiện theo môi trường hỗ trợ |
| Test phụ thuộc profile nhưng vẫn chạy | `@ActiveProfiles` chỉ chọn profile, không phải điều kiện disable | Dùng điều kiện riêng nếu cần skip theo profile/runtime environment |
| Test bị skip sau khi bắt đầu chạy | `Assumptions` không thỏa trong test body | Xác định service/fixture không sẵn sàng; quyết định đây là optional hay bắt buộc trong CI |
| Test OS-specific bị chạy sai nền tảng | Điều kiện được đặt ở method khác hoặc class quá rộng | Đặt `@EnabledOnOs`/`@DisabledOnOs` đúng phạm vi |

## 15. Nguyên tắc sử dụng

- Dùng `@DisabledInAotMode` cho test đã xác định không tương thích với AOT mode, không dùng để bỏ qua lỗi AOT chưa được điều tra.
- Đặt điều kiện ở method nếu chỉ một test phụ thuộc môi trường; dùng class-level khi toàn bộ class có cùng điều kiện.
- Dùng annotation JUnit chuyên biệt cho OS, JRE, system property và environment variable.
- Dùng Spring `@EnabledIf` hoặc `@DisabledIf` khi cần biểu thức SpEL hoặc thông tin từ Spring context.
- Chỉ đặt `loadContext = true` khi biểu thức thực sự cần bean hoặc context.
- Dùng `Assumptions` khi điều kiện chỉ có thể xác định trong lúc test đang chạy.
- Không để test quan trọng của CI bị skip âm thầm chỉ vì biến môi trường bị thiếu.
- Giữ một nhóm test tương thích AOT hoạt động để kiểm tra đường chạy generated context.

## 16. Ghi nhớ

`@DisabledInAotMode` của Spring TestContext (Spring Framework 6.2+) disable test class hoặc method khi chạy trong AOT mode. Với điều kiện theo môi trường, Spring `@EnabledIf`/`@DisabledIf` hỗ trợ SpEL; JUnit Jupiter cung cấp annotation riêng cho environment variable, system property, OS và JRE. `Assumptions` phù hợp khi điều kiện chỉ biết trong lúc thực thi. `@ActiveProfiles` chỉ chọn profile cho context, không tự skip test. Hãy chọn đúng loại điều kiện và đặt ở phạm vi nhỏ nhất cần thiết để suite vẫn chạy đầy đủ ở những môi trường có thể hỗ trợ.


# Reset mock giữa các ca kiểm thử và trạng thái dùng chung trong Spring Boot

## 1. Vấn đề: bài test thứ hai bị ảnh hưởng bởi bài test thứ nhất

Khi kiểm thử một service Spring Boot có dependency được thay bằng mock, có hai loại trạng thái rất dễ bị nhầm với nhau:

1. **Trạng thái bên trong Mockito mock:** Các câu lệnh stubbing như when(...).thenReturn(...), những lần gọi đã được ghi nhận để verify(...), các Answer tùy biến và hành vi được cấu hình trên mock.
2. **Trạng thái của ứng dụng và môi trường test:** Field mutable của singleton bean, bộ nhớ đệm, static variable, dữ liệu database, hàng đợi, file tạm, trạng thái phiên, cấu hình toàn cục hoặc đối tượng fake tự viết.

Reset một mock có thể xóa **stubbing và lịch sử invocation của mock đó**, nhưng không đồng nghĩa trạng thái của toàn bộ ApplicationContext, service đang dùng mock hay database đã được đưa về ban đầu.

Giả sử hai test cùng dùng một @MockBean để thay QuoteGateway:

- Test A stub findQuote("Q1") trả "Báo giá 1", sau đó gọi QuoteService.text("Q1").
- Test B mong không có stub từ Test A, rồi kiểm tra case tìm không thấy báo giá.
- Nếu mock được dùng lại và **không được reset**, test B có thể quan sát cấu hình hoặc invocation từ test A, dẫn đến kết quả sai hoặc verification thất bại.
- Nếu Spring Boot reset mock đúng vòng đời, **cấu hình của A không rò sang B**, dù ApplicationContext có thể được cache và tái sử dụng.

Bài học này nằm ở chủ đề **thay thế bean trong test**: phân biệt @Mock do Mockito quản lý với @MockBean được Spring Boot đặt vào ApplicationContext, hiểu MockReset.AFTER/BEFORE/NONE, biết khi nào dùng Mockito.reset()/clearInvocations(), và làm sạch trạng thái ngoài mock mà không lạm dụng @DirtiesContext.

**Phạm vi phiên bản ví dụ:** Java 17, Spring Boot 3.3.5, JUnit Jupiter, Mockito và Gradle. Ở Spring Boot 3.3, annotation thay bean phổ biến là **org.springframework.boot.test.mock.mockito.MockBean**. Từ Spring Boot 3.4, API này bị đánh dấu deprecated để chuyển sang **@MockitoBean** của Spring Framework; xem lưu ý phiên bản ở phần cuối, không trộn import giữa hai cơ chế.

## 2. Mock, spy, fake, bean và context cache khác nhau ở đâu?

| Thành phần | Đối tượng được tạo/kiểm soát | Dữ liệu có thể tồn tại qua test? | Cách cô lập thường dùng |
|---|---|---|---|
| **@Mock + MockitoExtension** | Mock là field của test, được Mockito khởi tạo theo vòng đời Jupiter | Mỗi test theo mẫu PER_METHOD có fixture riêng; không cần mặc định gọi reset thủ công | @ExtendWith(MockitoExtension.class), setup từng test |
| **@MockBean (Spring Boot 3.3)** | Mock thay/thêm bean trong ApplicationContext và được inject vào field test | Context có thể được cache, nhưng mock được reset theo MockReset mặc định | Giữ MockReset.AFTER; không stub dư ở setup |
| **@SpyBean (Spring Boot 3.3)** | Spy bọc bean thật trong context | Mockito ghi nhận invocation/stubbing; **trạng thái thật bên trong bean vẫn có thể tồn tại** | Reset mock metadata và chủ động làm sạch state thật |
| **Fake bean tự viết** | Triển khai đơn giản có thể lưu dữ liệu vào Map/List | Có, nếu là singleton bean trong cached context | Dọn fake trước mỗi test hoặc tạo fixture cô lập |
| **Singleton service @Service** | Bean ứng dụng thật | Có, nếu chứa field mutable và context được tái dùng | Thiết kế stateless; reset dữ liệu test có chủ đích |
| **Database / Redis / message broker** | Hệ thống lưu trữ ngoài Mockito | Có, theo transaction và chính sách dọn dữ liệu | Transaction rollback, cleanup script, schema/container cô lập |
| **ApplicationContext cache** | Container và tập bean Spring dùng chung theo cấu hình test | Có, giữa các test phù hợp context cache key | Giữ test độc lập; chỉ dùng @DirtiesContext khi cần |

**Điểm mấu chốt:** JUnit Jupiter mặc định tạo **instance class test mới cho mỗi phương thức** (Lifecycle.PER_METHOD). Điều này **không có nghĩa** Spring tạo ApplicationContext mới cho mỗi test. Spring TestContext chủ động cache context để test chạy nhanh. Một singleton trong context có thể là cùng instance giữa nhiều phương thức test, trong khi đối tượng class test khác nhau.

Tương tự, dùng @TestInstance(PER_CLASS) hay biến **static** có thể khiến state của chính class test tồn tại qua nhiều method dù không có Spring context. Vì vậy phải xác định **chủ sở hữu state** trước khi chọn cách reset.

## 3. Reset của Mockito thật sự xóa những gì?

Mockito cung cấp hai thao tác dễ bị nhầm:

| Thao tác | Xóa lịch sử invocation/verification? | Xóa stubbing đã tạo? | Khi nào dùng |
|---|---|---|---|
| **Mockito.reset(mock)** | Có | **Có** | Bắt buộc làm mới cùng một mock được tái sử dụng, thường vì container |
| **Mockito.clearInvocations(mock)** | Có | **Không** | Muốn giữ các stub phức tạp nhưng đo riêng một lượt tương tác |
| **Không thao tác** | Không | Không | Khuyến nghị khi mỗi test đã có mock/fixture riêng |
| **Tạo mock mới** | Mock mới không có lịch sử cũ | Mock mới không có stub cũ | Lựa chọn tự nhiên trong unit test |

Ví dụ trực giác:

~~~java
QuoteGateway gateway = mock(QuoteGateway.class);
when(gateway.findQuote("Q1"))
        .thenReturn(Optional.of("Báo giá 1"));

gateway.findQuote("Q1"); // Một invocation đã được ghi nhận.

clearInvocations(gateway); // Xóa invocation, GIỮ stubbing.
// gateway.findQuote("Q1") vẫn cho Optional chứa "Báo giá 1".

reset(gateway); // Xóa invocation VÀ stubbing.
// Không còn cấu hình trả "Báo giá 1".
~~~

Đây là đoạn mã minh họa trong một phương thức Java đã có import tương ứng, không phải một file độc lập. Khi mock chưa stub phương thức trả Optional, Mockito với default answer thông thường trả **Optional.empty()**; với các loại return khác hoặc Answer tùy chỉnh, giá trị mặc định có thể khác.

**Mockito.reset không tạo một instance mock mới.** Nó làm sạch cấu hình và lịch sử gắn với instance mock đang được truyền vào. Nếu ứng dụng còn một **cache Map** riêng chứa "Q1" hoặc một singleton đếm số lần gọi, reset(gateway) không chạm vào những đối tượng ấy.

**Không nên reset giữa chừng chỉ để chia một test dài thành nhiều pha.** Cách đó có thể xóa stub/interaction mà test cần xác minh, làm bài test khó hiểu. Nếu có nhiều hành vi độc lập, chia thành các test nhỏ là lựa chọn tốt hơn.

## 4. @MockBean của Spring Boot 3.3 tự reset như thế nào?

**@MockBean** được dùng để thêm mock bean hoặc thay một bean có sẵn trong ApplicationContext. Khi khai báo trên field của test, cùng instance mock được inject vào field đó; service phụ thuộc bean được thay cũng nhận mock từ context.

Với Spring Boot 3.3, thuộc tính:

~~~java
@MockBean(reset = MockReset.AFTER)
QuoteGateway gateway;
~~~

sử dụng **org.springframework.boot.test.mock.mockito.MockReset**, gồm ba giá trị:

| Chế độ | Thời điểm reset | Hậu quả trong các test liên tiếp |
|---|---|---|
| **AFTER** | Sau mỗi test method | Mặc định; stub và invocation của test vừa chạy được xóa trước lần sử dụng tiếp theo |
| **BEFORE** | Trước mỗi test method | Bắt đầu mỗi test từ mock sạch; hữu ích khi cần đảm bảo reset tại đầu vòng đời |
| **NONE** | Không reset tự động | Stubbing/invocation có thể tồn tại qua các test dùng lại context; chỉ chọn có chủ đích |

Nếu viết đơn giản:

~~~java
@MockBean
QuoteGateway gateway;
~~~

thì **reset mặc định là MockReset.AFTER**, không cần thêm reset = ... cho phần lớn các test. Spring Boot dùng tích hợp Spring TestContext/Mockito (trong đó có **ResetMocksTestExecutionListener**) để thực hiện việc này. Khi sử dụng một annotation test của Spring Boot như @SpringBootTest trong cấu hình thông thường, hạ tầng liên quan được kích hoạt.

**AFTER và BEFORE đều cho mục tiêu cô lập mock**, nhưng khác thời điểm thực hiện. Chúng không bảo đảm singleton application state hay DB tự xóa. Nếu test dùng @TestExecutionListeners tùy biến và vô tình thay toàn bộ listener mặc định, cơ chế reset của Spring Boot có thể bị ảnh hưởng; khi tùy biến listener, cần xem xét merge với defaults.

**Reset không liên quan đến Strictness.STRICT_STUBS.** Strict stubbing của Mockito kiểm tra stub thừa/sai đối số trong một test; MockReset của Spring Boot quyết định **khi nào xóa** trạng thái mock. Không nên coi việc tắt strictness là một cách reset, hoặc coi reset là lời giải cho UnnecessaryStubbingException.

## 5. Ví dụ chạy được: Spring Boot + @MockBean reset mặc định

Dự án mẫu có QuoteService phụ thuộc QuoteGateway. Ở runtime bình thường, DefaultQuoteGateway là bean thật trả kết quả trống; khi test, @MockBean thay nó bằng Mockito mock. Các test xác minh cả kết quả nghiệp vụ và trạng thái mock sạch trước từng trường hợp.

### 5.1. Cấu trúc dự án

~~~text
settings.gradle
build.gradle
src/main/java/demo/reset/ResetDemoApplication.java
src/main/java/demo/reset/QuoteGateway.java
src/main/java/demo/reset/DefaultQuoteGateway.java
src/main/java/demo/reset/QuoteService.java
src/test/java/demo/reset/QuoteServiceWithMockBeanTest.java
src/test/java/demo/reset/QuoteServiceUnitTest.java
src/test/java/demo/reset/MockitoResetSemanticsTest.java
src/test/java/demo/reset/SharedStateIsolationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-boot-mock-reset-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Ở Spring Boot 3.3.5, spring-boot-starter-test chứa các thư viện như JUnit Jupiter, Mockito, Mockito Jupiter integration, Spring Test và AssertJ. Để thực hiện unit test, không cần dùng @SpringBootTest; khi kiểm tra khả năng thay bean trong context thì sử dụng @SpringBootTest phù hợp.

### 5.2. Các lớp production

**src/main/java/demo/reset/ResetDemoApplication.java**

~~~java
package demo.reset;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResetDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResetDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/reset/QuoteGateway.java**

~~~java
package demo.reset;

import java.util.Optional;

public interface QuoteGateway {
    Optional<String> findQuote(String code);
}
~~~

**src/main/java/demo/reset/DefaultQuoteGateway.java**

~~~java
package demo.reset;

import java.util.Optional;

import org.springframework.stereotype.Component;

@Component
public class DefaultQuoteGateway implements QuoteGateway {

    @Override
    public Optional<String> findQuote(String code) {
        return Optional.empty();
    }
}
~~~

**src/main/java/demo/reset/QuoteService.java**

~~~java
package demo.reset;

import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {

    private final QuoteGateway gateway;

    public QuoteService(QuoteGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    public String text(String code) {
        return gateway.findQuote(code).orElse("NOT_FOUND");
    }
}
~~~

**Vì sao tách QuoteGateway khỏi QuoteService?** Dependency được inject qua constructor, để unit test có thể truyền mock trực tiếp và Spring Boot test có thể thay **bean QuoteGateway** trong ApplicationContext mà không thay logic QuoteService. Trường gateway là final nên service không giữ hoặc chỉnh sửa stubbing trong lúc chạy.

### 5.3. Integration test: @MockBean và trạng thái sạch ở mỗi lượt

**src/test/java/demo/reset/QuoteServiceWithMockBeanTest.java**

~~~java
package demo.reset;

import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class QuoteServiceWithMockBeanTest {

    @Autowired
    QuoteService quoteService;

    // Spring Boot 3.3: default reset = MockReset.AFTER.
    @MockBean
    QuoteGateway gateway;

    @BeforeEach
    void startsWithCleanMock() {
        verifyNoInteractions(gateway);
        assertThat(mockingDetails(gateway).getStubbings()).isEmpty();
    }

    @Test
    void knownQuoteIsReturned() {
        when(gateway.findQuote("Q1"))
                .thenReturn(Optional.of("Báo giá 1"));

        assertThat(quoteService.text("Q1")).isEqualTo("Báo giá 1");
        verify(gateway).findQuote("Q1");
    }

    @Test
    void missingQuoteUsesFallback() {
        when(gateway.findQuote("MISSING"))
                .thenReturn(Optional.empty());

        assertThat(quoteService.text("MISSING")).isEqualTo("NOT_FOUND");
        verify(gateway).findQuote("MISSING");
    }
}
~~~

**Phân tích từng bước:**

1. Spring TestContext tìm ResetDemoApplication, tạo context ứng dụng và thay bean QuoteGateway bằng mock do @MockBean cung cấp.
2. QuoteService vẫn là **bean thật**; dependency của nó là mock QuoteGateway.
3. Mỗi @Test nhận cùng mô hình setup kiểm thử, không phải dựa vào kết quả của một @Test khác.
4. Trước từng test, @BeforeEach kiểm tra mock không còn interaction và không còn stub. Với cấu hình mặc định, Mockito integration của Boot reset sau các test trước đó. Nếu Spring quyết định tạo context mới, mock cũng bắt đầu sạch; test **không nên dựa vào identity của mock giữa các test**.
5. knownQuoteIsReturned() đặt stub đúng trường hợp Q1, gọi service và xác minh cả giá trị trả về lẫn lời gọi gateway.
6. missingQuoteUsesFallback() tạo stub riêng cho MISSING, không sử dụng cấu hình từ test Q1.

**JUnit Jupiter không đảm bảo thứ tự giữa hai test này.** Bộ test không yêu cầu knownQuoteIsReturned chạy trước missingQuoteUsesFallback; cả hai phải chạy thành công khi đứng riêng, đổi thứ tự hoặc chạy trong cả suite.

**Quan trọng:** Nếu các bean ứng dụng khác gọi QuoteGateway trong quá trình khởi động context hoặc trong setup tự động, assertion verifyNoInteractions() có thể không còn phù hợp với ứng dụng ấy. Đây là assertion hợp lệ cho **dự án mẫu đơn giản này**; khi kiểm thử hệ thống thật cần xác định tương tác nào là một phần của contract kiểm thử.

### 5.4. Unit test: MockitoExtension, không cần reset @MockBean

**src/test/java/demo/reset/QuoteServiceUnitTest.java**

~~~java
package demo.reset;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class QuoteServiceUnitTest {

    @Mock
    QuoteGateway gateway;

    @InjectMocks
    QuoteService quoteService;

    @Test
    void readsFoundQuote() {
        when(gateway.findQuote("Q2"))
                .thenReturn(Optional.of("Báo giá 2"));

        assertThat(quoteService.text("Q2")).isEqualTo("Báo giá 2");
        verify(gateway).findQuote("Q2");
    }

    @Test
    void returnsFallbackForUnknownCode() {
        when(gateway.findQuote("UNKNOWN"))
                .thenReturn(Optional.empty());

        assertThat(quoteService.text("UNKNOWN"))
                .isEqualTo("NOT_FOUND");
        verify(gateway).findQuote("UNKNOWN");
    }
}
~~~

Ở đây **@Mock là Mockito mock không phải bean trong ApplicationContext**, còn @InjectMocks khởi tạo đối tượng được kiểm thử với dependency mock. Mỗi test theo vòng đời Jupiter PER_METHOD có test fixture mới, được MockitoExtension thiết lập. Không cần @SpringBootTest và không cần gọi Mockito.reset ở @AfterEach để giữ cách ly.

Đừng nhầm:
- @Mock **không tự thay bean** nếu bạn chạy một @SpringBootTest rồi autowire QuoteService từ Spring context.
- @MockBean là cơ chế test của Spring Boot 3.3 dùng để **đưa mock vào context và thay/đăng ký bean**.
- Không nên gắn cả @Mock và @MockBean cho cùng dependency mà không hiểu rõ instance nào được inject vào service.

## 6. So sánh thực nghiệm Mockito.reset và clearInvocations

**src/test/java/demo/reset/MockitoResetSemanticsTest.java**

~~~java
package demo.reset;

import java.util.Optional;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class MockitoResetSemanticsTest {

    @Test
    void clearInvocationsPreservesStubbing() {
        QuoteGateway gateway = mock(QuoteGateway.class);
        when(gateway.findQuote("Q1"))
                .thenReturn(Optional.of("Báo giá 1"));

        assertThat(gateway.findQuote("Q1"))
                .contains("Báo giá 1");

        clearInvocations(gateway);

        verifyNoInteractions(gateway);
        assertThat(mockingDetails(gateway).getStubbings())
                .hasSize(1);

        // Stub vẫn còn sau khi chỉ xóa lịch sử lời gọi.
        assertThat(gateway.findQuote("Q1"))
                .contains("Báo giá 1");
    }

    @Test
    void resetRemovesStubbingAndInvocations() {
        QuoteGateway gateway = mock(QuoteGateway.class);
        when(gateway.findQuote("Q1"))
                .thenReturn(Optional.of("Báo giá 1"));

        assertThat(gateway.findQuote("Q1"))
                .contains("Báo giá 1");

        reset(gateway);

        verifyNoInteractions(gateway);
        assertThat(mockingDetails(gateway).getStubbings())
                .isEmpty();

        // Với Mockito default answer, Optional chưa stub -> empty.
        assertThat(gateway.findQuote("Q1")).isEmpty();
    }
}
~~~

Đây là ví dụ về **ngữ nghĩa của hai API**, không khuyến nghị dùng chúng trong mọi test. Khi reset, cả stub trả "Báo giá 1" lẫn invocation cũ mất đi. Khi clearInvocations, test có thể bắt đầu verify một pha tương tác mới nhưng **vẫn giữ stub cũ**. Nếu mục tiêu là đảm bảo test kế tiếp hoàn toàn độc lập, clearInvocations **không đủ** để loại bỏ cấu hình giả lập đã có.

Với Spring Boot @MockBean, nên ưu tiên **cơ chế reset tự động** thay vì viết reset(gateway) lặp lại ở @AfterEach. Với unit test dùng MockitoExtension, ưu tiên mỗi test có fixture riêng.

## 7. Chế độ BEFORE, AFTER, NONE: nên chọn trường hợp nào?

Cả ba giá trị trong bảng sau là **org.springframework.boot.test.mock.mockito.MockReset** của Spring Boot 3.3:

~~~java
// Mặc định: tương đương reset = MockReset.AFTER.
@MockBean
QuoteGateway gateway;

// Chỉ minh họa lựa chọn thay thế:
// @MockBean(reset = MockReset.BEFORE) QuoteGateway gateway;
// @MockBean(reset = MockReset.NONE)   QuoteGateway gateway;
~~~

Đoạn trên là các field/snippet minh họa; không khai báo ba biến tên gateway giống nhau trong một class thật. Nếu sử dụng BEFORE/NONE, import MockReset từ đúng package Spring Boot 3.3.

**AFTER — lựa chọn mặc định nên giữ:** Một test thiết lập stub, chạy assertion, rồi hạ tầng Spring Boot reset mock sau lượt test ấy. Test tiếp theo không dùng những stub cũ. Đây là giải pháp đơn giản và đã có sẵn trong framework.

**BEFORE — ưu tiên reset ngay khi bắt đầu:** Hữu ích nếu việc thiết lập/kiểm tra test đòi trạng thái sạch ở đầu mỗi lượt. Nó cũng có thể hỗ trợ kiểm thử một mock có thể còn trạng thái từ hoạt động trước đó, nhưng nếu context được dùng bởi công việc nền chạy đồng thời, việc reset bất ngờ vẫn là vấn đề cần giải quyết ở kiến trúc test.

**NONE — không tự reset:** Chỉ nên dùng khi có lý do rất rõ, chẳng hạn muốn giữ một setup stubbing dùng chung theo cách đã được kiểm soát và có cleanup riêng. Với cached context, việc này dễ gây phụ thuộc thứ tự test. NONE **không có nghĩa mock không thể bị reset bằng code**; nó chỉ tắt hành vi reset tự động do tích hợp này áp dụng.

**Đừng chọn NONE để sửa một test bị Mockito UnnecessaryStubbingException** hoặc để “giữ nguyên tất cả lời gọi cho verify cuối suite”. Những cách đó thường làm test phụ thuộc nhau và khó chạy song song. Nếu cần một kịch bản nhiều bước liên tiếp, viết một test rõ ràng bao gồm các pha và assertion theo nghiệp vụ, hoặc tách scenario đúng abstraction.

## 8. State thật của singleton bean không được Mockito reset

Một Spring bean có thể giữ state riêng:

~~~java
@Component
class SequenceService {
    private final AtomicInteger sequence = new AtomicInteger();

    int next() {
        return sequence.incrementAndGet();
    }
}
~~~

Đoạn trên chỉ minh họa; cần import Component và AtomicInteger, đặt trong file Java hợp lệ. Nếu hai test cùng nhận singleton SequenceService từ context cache, test thứ nhất có thể gọi next() nhận 1, test thứ hai nhận 2. **Không có @MockBean nào tự xóa AtomicInteger của SequenceService**.

Các tình huống tương tự:
- FakeGateway dùng Map để ghi dữ liệu giả.
- @Cacheable lưu dữ liệu trong CacheManager thật.
- Một bean giữ session, queue hoặc bộ đếm trong field.
- Một static Set được dùng làm fixture.
- JPA repository truy cập database đã được các test trước ghi dữ liệu.

**Lựa chọn tốt nhất khi có thể:** Viết business service **stateless**, để state thuộc repository/cache được quản lý rõ ràng. Với fake lưu state, cung cấp chức năng clear chỉ phục vụ test hoặc tạo fake mới cho mỗi test. Dùng @DirtiesContext khi thực sự cần context mới, không phải cách đầu tiên.

### 8.1. Ví dụ test bean có state và chủ động làm sạch ở @BeforeEach

**src/test/java/demo/reset/SharedStateIsolationTest.java**

~~~java
package demo.reset;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class SharedStateIsolationTest {

    @Autowired
    TestCounter counter;

    @BeforeEach
    void cleanMutableState() {
        counter.clear();
    }

    @Test
    void firstIndependentScenario() {
        assertThat(counter.next()).isEqualTo(1);
    }

    @Test
    void secondIndependentScenario() {
        assertThat(counter.next()).isEqualTo(1);
    }

    static final class TestCounter {
        private int count;

        synchronized int next() {
            return ++count;
        }

        synchronized void clear() {
            count = 0;
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class CounterTestConfig {

        @Bean
        TestCounter testCounter() {
            return new TestCounter();
        }
    }
}
~~~

Trong Spring Boot test thông thường, nested static @TestConfiguration **bổ sung bean test** vào application context. TestCounter là singleton test bean nên có thể giữ count giữa các test nếu context được tái dùng. Mỗi @BeforeEach tự đặt count về 0; hai test có thể chạy độc lập theo bất kỳ thứ tự nào và đều nhận 1.

**Không nên sao chép phương thức reset() vào mọi service production chỉ để làm vừa lòng test.** Ở đây TestCounter nằm hoàn toàn trong source test; với dữ liệu nghiệp vụ thật, hãy xem cơ chế tạo fixture mới, transaction rollback, API dọn cache dành cho test hoặc thiết kế stateless. Phương thức synchronized làm ví dụ tránh data race đơn giản trên counter, **không khiến việc reset chung an toàn nếu hai test cùng dùng bean này chạy song song**.

### 8.2. Khi nào @DirtiesContext phù hợp?

Nếu state thực sự nằm trong context và khó khôi phục tin cậy, Spring hỗ trợ đánh dấu context “bẩn”:

~~~java
// Trên một test class; đây là cấu hình minh họa.
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class StatefulIntegrationTest {
    // Mỗi test có thể khiến context bị loại khỏi cache.
}
~~~

Đoạn trên không phải file Java độc lập; cần import org.springframework.test.annotation.DirtiesContext và các annotation test/context cần thiết.

Khi dùng classMode = AFTER_EACH_TEST_METHOD, Spring đóng và loại context liên quan khỏi cache sau mỗi phương thức, nên test tiếp theo phải tải context lại nếu cần. **Chi phí**: startup chậm hơn, có thể ảnh hưởng các test khác cùng cache key. Không sử dụng @DirtiesContext như “reset mock thủ công đắt tiền” vì @MockBean đã có cơ chế reset phù hợp. Nếu chỉ một test làm thay đổi state không thể phục hồi, có thể đánh dấu đúng test ấy thay vì cả class.

### 8.3. Database và các dịch vụ ngoài

**@Transactional trên test Spring** thường khiến các thao tác database được thực hiện trong **test-managed transaction** bị rollback sau test. Điều này không bảo đảm dọn:
- Giao dịch ở thread khác, @Async hoặc workflow mở transaction riêng.
- Dữ liệu đã commit ngoài transaction của test.
- Message đã gửi đi, object trong cache ngoài DB, file, HTTP call hoặc state của bên thứ ba.
- ID sequence có thể tăng dù transaction rollback, tùy cơ sở dữ liệu.

Nếu muốn test đối tượng xuyên qua HTTP và database, hãy xác định rõ boundaries: có thể dùng @Sql để setup/cleanup, transaction có kiểm soát, schema riêng, Testcontainers, fake server hoặc cơ chế reset cache. **Không giả định Mockito.reset giải quyết chúng.**

## 9. Vì sao Spring context cache khiến state “chạy một mình pass, chạy cả suite fail”?

**Spring TestContext Framework** có cơ chế tái dùng ApplicationContext cho những cấu hình kiểm thử tương thích, tránh khởi động Spring từ đầu ở mỗi @Test. Điều này thường tốt cho tốc độ nhưng làm các singleton và bean test có thể tồn tại lâu hơn một phương thức test.

Các yếu tố có thể tác động tới context cache key gồm configuration classes, active profiles, test properties, context customizers (bao gồm mock bean configuration), context hierarchy và các tùy chọn bootstrap. Không nên dựa vào cùng một instance ở mọi môi trường: khác test configuration có thể tạo context riêng.

Triệu chứng rò rỉ:
- Test B thất bại khi chạy sau test A nhưng pass khi chạy đơn lẻ.
- Lệnh test với thứ tự khác hoặc IDE khác cho kết quả khác.
- Cache hoặc fake lưu dữ liệu từ lần chạy trước.
- verifyNoMoreInteractions() nhận lời gọi từ test khác khi mock bị cấu hình NONE hoặc reset listener không hoạt động như kỳ vọng.
- Test không reset static mutable field, đặc biệt khi dùng @TestInstance(PER_CLASS).

Cách xác định **đúng lớp state**:
1. Nếu Mockito verification báo invocation cũ: xem **MockReset mode, Mockito extension/session và lifecycle**.
2. Nếu service trả dữ liệu cũ dù mock sạch: tìm cache, singleton mutable state, static field hoặc repository.
3. Nếu DB có dòng từ test khác: kiểm tra transaction boundaries và cleanup.
4. Nếu lỗi chỉ xuất hiện khi chạy song song: kiểm tra test concurrency và shared fixture, không chỉ thêm reset.
5. Nếu @DirtiesContext chữa được lỗi: đó là **dấu hiệu có state/lifecycle phụ thuộc context**, nhưng chưa chỉ ra state nào và không chứng minh đã sửa tận gốc.

**Không viết test phụ thuộc thứ tự** như “test A tạo dữ liệu cho test B”, trừ khi đó là một scenario tích hợp có điều phối rõ ràng trong cùng một test/workflow. Một suite tốt cho phép chạy test riêng lẻ hoặc chọn lọc mà không cần test khác “dọn đường”.

## 10. JUnit Jupiter: PER_METHOD, PER_CLASS, @BeforeEach và @AfterEach

JUnit Jupiter mặc định dùng **@TestInstance(Lifecycle.PER_METHOD)**, tạo test instance mới cho mỗi phương thức. Field bình thường của test class vì thế thường được tạo lại. Khi dùng **@TestInstance(PER_CLASS)**, một instance test class có thể sống qua mọi test method; field mutable trên instance ấy phải được quản lý.

Ví dụ:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class OrderDependentTest {
    private int attempts = 0;

    @Test
    void firstExample() {
        attempts++;
    }

    @Test
    void secondExample() {
        attempts++;
    }
}
~~~

Đây là snippet minh họa cần import JUnit; không đưa vào bộ test PASS vì nó **cố ý chứa state liên-test**. Giá trị attempts trong một test phụ thuộc những test đã chạy trước đó; tên first/second không áp đặt thứ tự. Với @TestInstance(PER_METHOD) thông thường, field attempts là field của instance mới; nhưng **static fields** vẫn dùng chung trong cùng JVM, và **Spring singleton** vẫn có thể dùng chung do context cache bất kể PER_METHOD.

**@BeforeEach và @AfterEach** có thể dùng để setup và cleanup fixture. Tuy nhiên:
- Nếu fixture được khởi tạo mới cho mỗi test, ưu tiên tạo ở @BeforeEach hoặc trong test thay vì reset một đối tượng cũ.
- @BeforeEach chỉ dọn những gì code đó thực sự xử lý; không tự clear DB/Redis/cache trừ khi được gọi tường minh.
- Nếu test bị exception, lifecycle callback bình thường vẫn được Jupiter thực hiện theo quy tắc của framework, nhưng quá trình JVM bị kill hoặc hạ tầng sập có thể ngăn cleanup.
- Với Spring Boot @MockBean mặc định AFTER, bạn thường **không cần @AfterEach gọi Mockito.reset(mock)**. Làm như vậy khiến bài test phụ thuộc vào thứ tự các callback không cần thiết.

## 11. Spy và mutable object: reset Mockito không đồng nghĩa reset trạng thái thật

Spy khác mock thường ở chỗ **gọi method thật** nếu chưa stub. Ví dụ một @SpyBean bọc một bean đếm số lần:

~~~java
// Ví dụ ý tưởng, không phải chương trình độc lập:
@SpyBean
SequenceService sequenceService;
~~~

Khi Spring Boot reset Mockito spy sau mỗi test, Mockito có thể xóa các invocation và stub gắn với spy. Nhưng nếu SequenceService thật có trường AtomicInteger đã tăng lên 7, **reset spy không tự đặt trường đó về 0**. Lần gọi phương thức thật tiếp theo vẫn có thể trả 8. Đây là nguyên nhân quan trọng khiến test vẫn rò state dù dùng @SpyBean với reset mặc định.

**Khi stub spy:**
- when(spy.realMethod()) có thể gọi method thật ngay lúc khai báo stubbing, gây side effect.
- Dùng doReturn(value).when(spy).realMethod(...) khi muốn tránh thực thi method thật trong quá trình cấu hình.
- Nếu spy được dùng vì muốn kiểm tra logic thật + ghi nhận tương tác, phải có chiến lược clear state thật riêng; Mockito chỉ quản lý phần Mockito.

Trong dự án không cần hành vi thật của dependency, **@MockBean** thường dễ cô lập hơn @SpyBean. Dùng spy có chủ đích, không phải như “mock mạnh hơn”.

## 12. MockReset, strict stubbing và verifyNoMoreInteractions

Ba khái niệm này có mục đích riêng:

| Cơ chế | Câu hỏi trả lời | Có thay state ứng dụng không? |
|---|---|---|
| **MockReset.AFTER/BEFORE** | Khi nào xóa trạng thái của mock bean dùng lại? | Không |
| **Mockito STRICT_STUBS** | Stubbing có thật sự cần thiết/đúng đối số không? | Không |
| **verify(mock).call(...)** | Có xảy ra tương tác cụ thể không? | Không |
| **verifyNoInteractions(mock)** | Có hoàn toàn không gọi mock trong phạm vi đang xét không? | Không |
| **verifyNoMoreInteractions(mock)** | Có interaction nào còn chưa được verify không? | Không |
| **@DirtiesContext** | Có cần loại bỏ context khỏi cache và tải lại không? | Tạo lại context, nhưng không tự dọn hệ thống ngoài |
| **@Transactional rollback** | Các thay đổi DB thuộc test transaction có rollback không? | Có trong phạm vi transaction phù hợp |

Một @MockBean có thể được reset hoàn hảo nhưng test vẫn thất bại vì logic sai. Ngược lại, unit test có các assertion đúng vẫn có thể bị STRICT_STUBS đánh dấu fail vì stub không dùng. Không nên sử dụng reset như biện pháp “làm sạch báo lỗi” của strict stubbing; hãy xóa/move stubbing dư và sửa mismatch đúng logic.

**verifyNoMoreInteractions** kiểm tra các invocation chưa được verify ở thời điểm gọi. Nếu dùng reset trước khi verify, bạn làm mất bằng chứng tương tác; test có thể pass giả tạo. Do đó không reset cho đến khi các assertion/verification cần thiết đã hoàn tất. Trong ví dụ, Spring Boot reset **sau mỗi test**, phù hợp mục đích này.

## 13. Thiết kế test khi chạy song song

Ngay cả reset đúng chế độ cũng không khiến một mutable bean tự nhiên an toàn khi nhiều test chạy đồng thời trong **cùng context**:

~~~text
Test A: stub gateway.findQuote("Q1")
             |
             |             Test B: reset/mock setup
             |                        |
             v                        v
Test A: gọi service và mong Q1    Test B: verify khác
~~~

Nếu các test chia sẻ cùng mock và **thật sự chạy đồng thời**, việc reset hoặc stub từ test B có thể ảnh hưởng hành vi của test A. Các khung test có cơ chế quản lý parallel execution, nhưng cần xem cấu hình JUnit/Gradle và cách dùng context thực tế.

Các hướng xử lý:
- Ưu tiên **unit test dùng mock riêng** theo mỗi phương thức, không chia sẻ mock singleton.
- Với Spring context test có state, giữ những test dùng chung mutable fixture **không chạy song song** hoặc chủ động cô lập context/dữ liệu.
- Nếu cần giới hạn đồng thời trong JUnit Jupiter, xem **@ResourceLock** hoặc **@Execution(SAME_THREAD)** theo phạm vi thực sự; annotation phải áp dụng nhất quán cho tất cả test truy cập cùng tài nguyên.
- Đừng xem synchronized trên một phương thức reset là đủ để bảo vệ cả chuỗi “reset → stub → call → assert” khi test khác có thể xen vào.
- Với hệ thống ngoài, cô lập schema, database/container, topic hoặc key namespace theo test khi phù hợp; tránh chia chung tài nguyên mutable không kiểm soát.

Các dự án JUnit Jupiter thường chạy tuần tự khi chưa bật parallel execution, nhưng đừng giả định CI và IDE dùng cấu hình giống nhau. Test ổn định nên nêu rõ ràng buộc về concurrency nếu đang phụ thuộc chúng.

## 14. Những lỗi phổ biến và cách điều tra

| Triệu chứng | Khả năng nguyên nhân | Cách giải quyết |
|---|---|---|
| Test B thấy stub của test A | @MockBean(reset = NONE), mock dùng chung ngoài Spring hoặc listener reset bị vô hiệu hóa | Trở về reset mặc định AFTER/BEFORE, kiểm tra test lifecycle |
| verifyNoInteractions thất bại ngay đầu test | Mock có invocation trước đó hoặc bean khởi động đã gọi dependency | Xác định nguồn invocation; chỉ assert điều nghiệp vụ yêu cầu |
| clearInvocations rồi test vẫn trả stub cũ | clearInvocations **không xóa stubbing** | Dùng reset khi thực sự cần hoặc tạo mock mới |
| reset(mock) rồi verify(...) không còn thấy cuộc gọi | Reset đã xóa interaction | Chuyển verify trước reset hoặc bỏ reset thủ công |
| @Mock hoạt động trong unit test nhưng @Autowired service vẫn dùng bean thật | Mockito @Mock không phải Spring @MockBean | Dùng @MockBean trong Spring context hoặc inject unit mock trực tiếp |
| @MockBean reset rồi cache vẫn giữ dữ liệu cũ | Cache/singleton thật chưa được clear | Dọn cache/fixture theo nhu cầu, không chỉ reset mock |
| @SpyBean reset mà counter vẫn tăng | Spy giữ object thật có field mutable | Dọn state thật hoặc dùng mock/fake mới |
| @DirtiesContext làm suite chậm | Tải lại context liên tục, bỏ cache | Giới hạn phạm vi; setup dữ liệu test độc lập |
| Test pass riêng nhưng fail cả suite | State chung, thứ tự, database hoặc concurrency | Tìm chủ sở hữu state, reset tại đúng boundary |
| Test fail khi chạy parallel | Test cùng reset/stub một mock hoặc singleton | Tách fixture/context hoặc hạn chế chạy song song |
| @Transactional test vẫn để lại dữ liệu | Write không thuộc test-managed transaction hoặc tác động ngoài DB | Dọn ngoài transaction hoặc thiết lập môi trường riêng |
| Stubbing vô ích gây UnnecessaryStubbingException | Stub chưa được code dùng, không phải do MockReset | Xóa stub thừa/sửa test, không hạ strictness vô cớ |

**Checklist điều tra thực tế:**

1. **Xác định mock type:** @Mock, @MockBean, @SpyBean hay mock tự tạo trong @Bean?
2. **Xác định vòng đời:** JUnit PER_METHOD/PER_CLASS, MockitoExtension, Spring TestContext, context cache?
3. **Kiểm tra reset mode:** Với Spring Boot 3.3 @MockBean, mặc định AFTER; có ai đổi thành NONE không?
4. **Kiểm tra lịch sử và stubbing:** mockingDetails(mock).getStubbings(), verifyNoInteractions, verify(...), stack trace thực tế.
5. **Tìm state ngoài mock:** static, singleton field, cache, persistence, session, queue, file, system properties.
6. **Xem concurrency:** Test có dùng cùng context và mock trong quá trình chạy song song không?
7. **Sửa mức tối thiểu:** Stub riêng từng test; clear state tại chủ sở hữu; tạo fixture mới; dùng @DirtiesContext có giới hạn khi không thể reset tin cậy.
8. **Chạy lại suite:** Chạy các test riêng lẻ và cùng nhau trên lệnh CI, kiểm tra report và những test bị skip.

Không tự động tăng số lần reset chỉ vì test thỉnh thoảng fail. Một bài test càng cần reset nhiều nguồn state mà không rõ lý do, càng cần xem lại abstraction và mức test.

## 15. Chạy ví dụ và đối chiếu kết quả

Trong thư mục có build.gradle, nếu dự án đã tạo Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu chưa có Wrapper, dùng bản Gradle tương thích đã cài để tạo Wrapper hoặc chạy **gradle test**. Các file ở ví dụ chứa toàn bộ mã sản xuất và test, nhưng lệnh ./gradlew chỉ chạy nếu các file wrapper hiện diện.

Bộ ví dụ nêu trên gồm **8 phương thức @Test**:
- **2** test với @MockBean, kiểm tra stubbing và lịch sử invocation được cô lập.
- **2** unit test với MockitoExtension và mock riêng.
- **2** test về reset(...) và clearInvocations(...).
- **2** test singleton test bean có state nhưng được clear trong @BeforeEach.

Tất cả được thiết kế để PASS; không có test lỗi cố ý cần bật/tắt để chạy suite mẫu. Có thể xem kết quả thực tế trong **build/reports/tests/test/index.html**. Con số trên đúng với các file mẫu và giả định chưa thêm test khác; nếu project thực tế có thêm bài test, tổng số sẽ khác.

Có thể chọn một lớp để quan sát:

~~~bash
./gradlew test --tests demo.reset.QuoteServiceWithMockBeanTest
./gradlew test --tests demo.reset.MockitoResetSemanticsTest
./gradlew test --tests demo.reset.SharedStateIsolationTest
~~~

Dùng lệnh **test** của build trên CI, không chỉ xác minh IDE thấy ký hiệu xanh. Nếu một test phụ thuộc trạng thái từ bài khác, việc chạy chọn một class hoặc đảo thứ tự thường giúp phơi bày vấn đề đó.

## 16. Lưu ý phiên bản mới: @MockitoBean thay cho @MockBean

Để tránh nhầm lẫn tài liệu khi nâng cấp:

- Ví dụ của bài sử dụng **Spring Boot 3.3.5**, nên dùng **org.springframework.boot.test.mock.mockito.MockBean**, **org.springframework.boot.test.mock.mockito.MockReset** và hạ tầng reset tương ứng của Spring Boot.
- **Spring Boot 3.4** đánh dấu API @MockBean/@SpyBean cùng MockReset thuộc gói cũ là deprecated để chuyển sang cơ chế override bean của **Spring Framework 6.2**, trong đó có **org.springframework.test.context.bean.override.mockito.MockitoBean**, **MockitoSpyBean** và MockReset ở package mới.
- Khi nâng cấp, đối chiếu đúng annotation, import, cơ chế tìm/chọn bean và TestExecutionListener theo phiên bản Spring Framework đang dùng. Không copy trực tiếp @MockBean của ví dụ 3.3 vào ứng dụng mới rồi kết luận cách viết ấy là giải pháp lâu dài.
- Nguyên tắc nghiệp vụ **không đổi**: test phải cô lập stubbing/invocation và trạng thái ứng dụng; việc đổi tên annotation không biến singleton, cache hoặc database thành stateless.

Trong dự án nâng cấp, hãy đọc tài liệu Spring Framework về @MockitoBean/@MockitoSpyBean trước khi chỉnh cấu hình, vì chính sách override và vị trí khai báo có những chi tiết khác API cũ. Không kết hợp hai họ annotation trong một test class chỉ để thử may rủi.

## 17. Tóm tắt nguyên tắc áp dụng

- **Đừng gọi Mockito.reset theo phản xạ.** Unit test với @Mock + MockitoExtension thường không cần reset nếu mỗi test tạo fixture riêng và độc lập.
- Trong **Spring Boot 3.3, @MockBean được reset AFTER mỗi test method theo mặc định**. Có thể cấu hình BEFORE/NONE, nhưng NONE dễ rò stub và invocation khi context được cache.
- **reset(mock) xóa stubbing lẫn invocation**; **clearInvocations(mock) chỉ xóa invocation**, nên hai API không thể thay nhau một cách tùy tiện.
- **@SpyBean** có thể reset phần Mockito nhưng **không xóa field state của object thật**.
- **ApplicationContext cache** giúp test chạy nhanh nhưng có thể tái sử dụng singleton bean; reset mock không đồng nghĩa reset cache, static field hay database.
- Ưu tiên **service stateless, fixture mới, cleanup đúng chủ sở hữu state**. Chỉ dùng @DirtiesContext khi cần context mới, vì nó có chi phí.
- Không dựa vào thứ tự test hoặc concurrency may mắn. Kiểm tra test riêng lẻ và toàn suite, so sánh hành vi với đặc tả.

**Tự kiểm tra:** Một test Spring Boot khai báo @MockBean(reset = MockReset.NONE) và stubbing gateway.findQuote("Q1"); test sau gọi lại "Q1" mà không stub. Vì sao kết quả có thể bị ảnh hưởng? Nếu đổi thành clearInvocations(gateway) cuối test đầu thì đã đủ chưa? **Đáp án:** Cùng mock trong cached context có thể vẫn giữ stubbing; clearInvocations chỉ bỏ lịch sử gọi, **không bỏ stub**. Dùng reset tự động AFTER/BEFORE hoặc tạo fixture độc lập. Nếu vẫn sai vì bộ đếm singleton, tìm và dọn state thật của bean đó.

## 18. Tài liệu tra cứu

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — cơ chế @MockBean và tự reset giữa test.
- [Spring Boot 3.3 — MockBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockBean.html) — thuộc tính reset và giá trị mặc định AFTER.
- [Spring Boot 3.3 — MockReset Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockReset.html) — BEFORE, AFTER, NONE.
- [Mockito 5 — Mockito.reset và clearInvocations](https://javadoc.io/doc/org.mockito/mockito-core/5.16.0/org.mockito/org/mockito/Mockito.html) — sự khác biệt giữa xóa stub và xóa interaction.
- [Spring Framework — @MockitoBean và @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html) — cách tiếp cận ở Spring Framework mới.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html) — lý do Spring có thể tái dùng ApplicationContext trong suite.
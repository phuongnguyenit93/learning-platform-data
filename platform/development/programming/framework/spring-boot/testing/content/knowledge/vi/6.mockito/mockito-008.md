# Strict stubbing và phát hiện cấu hình giả lập không được sử dụng với Mockito

## 1. Vấn đề mà strict stubbing giải quyết

Trong unit test Spring Boot, lập trình viên thường thay repository, REST client hoặc dependency bằng một **mock** để kiểm soát kết quả trả về. Một câu lệnh như **when(repository.findById(42L)).thenReturn(...)** thiết lập hành vi giả lập, hay còn gọi là **stubbing**. Nhưng nếu code thực tế không bao giờ gọi repository.findById(42L), dòng stub ấy không giúp kiểm tra điều gì. Tệ hơn, nó có thể che giấu việc code chạy sai nhánh hoặc bài test được sao chép từ một tình huống khác.

**Strict stubbing** là cơ chế kiểm tra chất lượng cấu hình mock của Mockito. Ở chế độ **Strictness.STRICT_STUBS**, Mockito giúp phát hiện:
1. **Stubbing không được sử dụng:** Một phương thức mock được cấu hình trả kết quả nhưng không có invocation phù hợp trong quá trình chạy test. Tình huống điển hình dẫn đến **UnnecessaryStubbingException**.
2. **Sai lệch đối số khi gọi stub:** Test cấu hình mock với một tập đối số, nhưng code đang kiểm tra gọi cùng phương thức với đối số khác. Trong những tình huống mà Mockito nhận diện là stubbing argument mismatch, nó báo **PotentialStubbingProblem** sớm.
3. **Tương tác được stub có thể tự được tính là đã xác minh** khi dùng **verifyNoMoreInteractions** dưới STRICT_STUBS; do đó không nhất thiết phải viết verify riêng cho mọi invocation đã được stub chỉ để làm hài lòng kiểm tra tương tác dư.

Cơ chế này làm bài test dễ đọc, giảm dữ liệu giả thừa và giúp phát hiện sai sót thiết lập. Nó **không chứng minh thuật toán nghiệp vụ đúng** nếu assertion yếu hoặc thiếu; vẫn phải viết assertion cho đầu ra và hành vi mong đợi.

**Phạm vi bài học:** Mockito chạy với JUnit Jupiter trong dự án Spring Boot. Ví dụ dùng Java 17, Spring Boot 3.3.5 và Gradle. Strict stubbing là cơ chế của Mockito, không phải chế độ Spring Boot tự áp dụng cho mọi đối tượng giả lập.

## 2. Thuật ngữ: mock, stubbing, invocation, verification và strictness

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Mock** | Đối tượng thay thế dependency, thường được Mockito tạo | @Mock InvoiceRepository repository |
| **Stubbing** | Cấu hình hành vi khi một phương thức mock được gọi với đầu vào nhất định | when(repo.findById(42L)).thenReturn(Optional.of(invoice)) |
| **Invocation** | Lần gọi phương thức thực sự xảy ra trên mock trong lúc chạy code | service.amountVnd(42L) gọi repo.findById(42L) |
| **Verification** | Assertion rằng mock đã hoặc chưa nhận một invocation | verify(repo).findById(42L) |
| **Strictness** | Mức kiểm tra bổ sung đối với stubbing/verification | STRICT_STUBS, WARN, LENIENT |

Ví dụ, gọi **when(repo.findById(42L)).thenReturn(...)** là tạo stub; chỉ khi đường chạy có lệnh **repo.findById(42L)** phù hợp thì stub mới được sử dụng. Việc gọi **verify(repo).findById(42L)** là một bước kiểm chứng tương tác khác với việc dùng stub. Một mock có thể tồn tại mà chưa cần stubbing; một bài test có thể tương tác với mock mà không kiểm tra unused stubbing nếu nó không tạo stub nào.

**Strict stubbing không có nghĩa mọi lời gọi mock phải được khai báo trước.** Mockito vẫn có hành vi mặc định cho nhiều lời gọi không được stub (ví dụ trả null, false, 0 hoặc giá trị rỗng tùy kiểu/phiên bản/cấu hình). Chế độ strict tập trung vào cấu hình stub không có ích và sai lệch đối số có khả năng là lỗi. Nếu bài test yêu cầu chỉ những tương tác đã cho phép được xảy ra, cần thêm verification hoặc thiết kế assertion phù hợp, không chỉ dựa vào strict stubbing.

## 3. STRICT_STUBS hoạt động ở giai đoạn nào?

Khi dùng **MockitoExtension** với JUnit Jupiter:

1. **Trước mỗi test:** Extension tạo các mock được đánh dấu @Mock, xử lý @InjectMocks và bắt đầu một Mockito session với strictness đã cấu hình.
2. **Trong test:** Câu lệnh when/thenReturn hoặc doReturn/when tạo stub. Method thuộc đối tượng đang test gọi mock; Mockito tìm stub phù hợp theo phương thức và matcher/đối số.
3. **Khi xảy ra một sai lệch đối số có thể nhận diện:** STRICT_STUBS có thể báo PotentialStubbingProblem ngay tại invocation; điều này giúp kiểm tra xem SUT đang dùng đúng ID/giá trị hay không.
4. **Khi kết thúc test/session:** Mockito đối chiếu các stubbing được tạo với những invocation đã dùng, và có thể báo UnnecessaryStubbingException cho stub không được sử dụng. Khi test vốn đã thất bại vì nguyên nhân khác, cách báo lỗi bổ sung có thể phụ thuộc phiên bản và tích hợp.

Với **org.mockito.junit.jupiter.MockitoExtension**, mức strictness mặc định trong các phiên bản Mockito 5 của ví dụ là **STRICT_STUBS**. Bạn có thể khai báo rõ bằng **@MockitoSettings(strictness = Strictness.STRICT_STUBS)** để bài test thể hiện chủ đích và tránh hiểu nhầm khi di chuyển giữa các kiểu tích hợp. MockitoExtension thuộc artifact **mockito-junit-jupiter**; nó không phải JUnit Platform engine độc lập.

**Phân biệt nơi cấu hình mock:** Việc gọi **Mockito.mock(...)** thuần túy mà không có MockitoExtension/JUnit runner/MockitoSession quản lý vòng đời không tự bảo đảm có cùng kiểm tra unused stubbing lúc kết thúc test. Cần xác định session hoặc integration đang thực thi; có dependency Mockito trên classpath thôi chưa đủ.

## 4. Hai tín hiệu lỗi chính

### 4.1. UnnecessaryStubbingException: có stub nhưng không được dùng

Một ca test được cấu hình:

~~~java
// Giả sử repository là Mockito mock, service sử dụng repository.
when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));

// Hàm tạo nhãn này không gọi repository:
assertEquals("INV-42", service.label(42L));
~~~

Đoạn trên chỉ minh họa bên trong một phương thức test có sẵn mock/service; không phải chương trình Java độc lập. Assertion có thể đúng, nhưng stub tìm hóa đơn không được dùng. Dưới STRICT_STUBS và vòng đời Mockito phù hợp, Mockito báo UnnecessaryStubbingException. Thông báo thường chứa vị trí dòng stubbing để tìm và bỏ.

**Sửa đúng:** Xóa dòng when(...) vì bài test chỉ quan tâm nhãn hóa đơn. Nếu cần test đường gọi repository, viết bài test riêng có invocation và assertion của đường đó. Không gọi repository một cách giả tạo chỉ để làm stub được tính là đã dùng.

Một nguyên nhân thường gặp là đặt nhiều stubbing chung vào **@BeforeEach**, trong khi mỗi test chỉ đi qua một phần các nhánh. Với MockitoExtension, nên ưu tiên stub ngay trong test cần nó; tránh giả định mọi test đều sử dụng cùng một fixture.

### 4.2. PotentialStubbingProblem: stub có đối số khác invocation

~~~java
when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));

// Trong InvoiceService, phương thức này thực sự gọi findById(43L):
service.amountVnd(43L);
~~~

Nếu test định kiểm tra hóa đơn 42 nhưng truyền ID 43 cho service, sự lệch nhau có thể làm Mockito báo PotentialStubbingProblem khi code đang test gọi mock. Hãy kiểm tra **ID trong stubbing**, **ID truyền cho SUT**, **bộ argument matcher** và **đường code thực sự** trước khi giảm strictness.

Không phải mọi lần gọi mock khác giá trị stub đều bắt buộc phát sinh cùng một exception: Mockito dùng các điều kiện/heuristic để phân biệt nhầm đối số với những tình huống hợp lệ, và phạm vi strictness ảnh hưởng đến kết quả. Đôi khi biểu hiện là giá trị mặc định từ mock, assertion sai hoặc stub còn lại không được dùng. Cần đọc lỗi thực tế, không chỉ đoán theo tên exception.

**Một trường hợp hợp lệ:** Service cố ý gọi nhiều ID. Khi đó phải stub đúng những ID mà test muốn kiểm soát, dùng matcher thích hợp, hoặc tổ chức lại test. Nếu bạn stubbing cùng phương thức nhiều lần và gặp báo sai trong lời gọi when(...), có thể dùng **doReturn(...).when(mock)** hoặc **BDDMockito.willReturn(...).given(mock)** theo hướng dẫn Mockito. Chỉ đánh dấu lenient sau khi đã xác nhận sai lệch là có chủ đích.

## 5. Ví dụ hoàn chỉnh: Spring Boot 3.3.5 + JUnit Jupiter + Mockito

Ví dụ này có ba bài test **được thiết kế để PASS**, cùng hai tình huống lỗi bị đánh dấu **@Disabled**. Khi chạy build bình thường, các test sai được bỏ qua; người học có thể mở từng ca để quan sát strict stubbing.

### 5.1. Cấu trúc

~~~text
settings.gradle
build.gradle
src/main/java/demo/testing/TestingApplication.java
src/main/java/demo/testing/Invoice.java
src/main/java/demo/testing/InvoiceRepository.java
src/main/java/demo/testing/InvoiceService.java
src/test/java/demo/testing/InvoiceServiceTest.java
src/test/java/demo/testing/StrictStubsFailureDemoTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'mockito-strict-stubs-demo'
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

    // Starter test cung cấp JUnit Jupiter và mockito-junit-jupiter.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Không khai báo riêng phiên bản Mockito vì Spring Boot dependency management quản lý bộ thư viện kiểm thử của ví dụ. **useJUnitPlatform()** là cấu hình quan trọng để Gradle chạy JUnit Jupiter. Cần Java 17 trở lên và Gradle tương thích Spring Boot 3.3.x; sử dụng Gradle Wrapper của dự án nếu có.

**src/main/java/demo/testing/TestingApplication.java**

~~~java
package demo.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
~~~

**src/main/java/demo/testing/Invoice.java**

~~~java
package demo.testing;

public record Invoice(long id, long amountVnd) {
}
~~~

**src/main/java/demo/testing/InvoiceRepository.java**

~~~java
package demo.testing;

import java.util.Optional;

public interface InvoiceRepository {
    Optional<Invoice> findById(long id);
}
~~~

**src/main/java/demo/testing/InvoiceService.java**

~~~java
package demo.testing;

import java.util.Objects;

public final class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public long amountVnd(long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Invoice not found: " + id))
                .amountVnd();
    }

    public String label(long id) {
        return "INV-" + id;
    }
}
~~~

InvoiceService là class Java thuần trong dự án Spring Boot, không cần chạy Spring ApplicationContext để test logic. Mục đích là cô lập rõ dependency InvoiceRepository; dùng **@Mock** và **@InjectMocks**, không phải @SpringBootTest. Bài test không truy cập database hoặc mạng.

### 5.2. Các test PASS: chỉ stub những gì bài test sử dụng

**src/test/java/demo/testing/InvoiceServiceTest.java**

~~~java
package demo.testing;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.STRICT_STUBS)
class InvoiceServiceTest {

    @Mock
    InvoiceRepository repository;

    @InjectMocks
    InvoiceService service;

    @Test
    void returnsAmountWhenInvoiceExists() {
        when(repository.findById(42L))
                .thenReturn(Optional.of(new Invoice(42L, 120_000L)));

        long amount = service.amountVnd(42L);

        assertEquals(120_000L, amount);
        verify(repository).findById(42L);
    }

    @Test
    void throwsWhenInvoiceDoesNotExist() {
        when(repository.findById(404L)).thenReturn(Optional.empty());

        IllegalArgumentException exception = assertThrows(
                IllegalArgumentException.class,
                () -> service.amountVnd(404L));

        assertEquals("Invoice not found: 404", exception.getMessage());
    }

    @Test
    void labelDoesNotNeedAnyRepositoryStubbing() {
        assertEquals("INV-42", service.label(42L));
        verifyNoInteractions(repository);
    }
}
~~~

Giải thích:

- returnsAmountWhenInvoiceExists(): stub chính xác findById(42L), service gọi đúng ID, assertion kiểm tra số tiền. **verify** là một assertion tương tác có chủ đích; strict stubbing không bắt buộc phải thêm dòng verify này để xem stub đã được dùng.
- throwsWhenInvoiceDoesNotExist(): mock trả Optional.empty(), service ném IllegalArgumentException; test khẳng định cả loại lỗi lẫn thông điệp.
- labelDoesNotNeedAnyRepositoryStubbing(): đường code chỉ ghép nhãn, nên **không tạo stub**. verifyNoInteractions(...) khẳng định method không đụng repository; đây là assertion nghiệp vụ bổ sung, không phải điều kiện bắt buộc của strict stubbing.
- Mỗi test có bộ mock/session riêng từ MockitoExtension; không đặt stub dùng cho test đầu tiên vào setup chung của cả ba test.

Ba phương thức trên có thể hoàn thành thành công với STRICT_STUBS; không có stubbing thừa.

### 5.3. Các test cố ý FAIL: để @Disabled khi chạy bình thường

**src/test/java/demo/testing/StrictStubsFailureDemoTest.java**

~~~java
package demo.testing;

import java.util.Optional;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@Disabled("Teaching demo: remove @Disabled to observe strict failures")
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.STRICT_STUBS)
class StrictStubsFailureDemoTest {

    @Mock
    InvoiceRepository repository;

    @InjectMocks
    InvoiceService service;

    @Test
    void unusedStubTriggersUnnecessaryStubbing() {
        when(repository.findById(42L))
                .thenReturn(Optional.of(new Invoice(42L, 120_000L)));

        // label() không gọi findById(), nên stub ở trên không dùng.
        assertEquals("INV-42", service.label(42L));
    }

    @Test
    void wrongArgumentCanTriggerPotentialStubbingProblem() {
        when(repository.findById(42L))
                .thenReturn(Optional.of(new Invoice(42L, 120_000L)));

        // Service gọi findById(43L), lệch với stub cho 42L.
        service.amountVnd(43L);
    }
}
~~~

Class trên **bị vô hiệu hóa hoàn toàn** để phép thử build bình thường thành công. Khi muốn quan sát lỗi, tạm bỏ @Disabled trên class rồi chạy **mỗi phương thức riêng biệt**. Trong lệnh sau, dùng tên đầy đủ của test class để tránh chạy cả hai lỗi cùng một lúc.

~~~bash
./gradlew test --tests demo.testing.StrictStubsFailureDemoTest.unusedStubTriggersUnnecessaryStubbing
./gradlew test --tests demo.testing.StrictStubsFailureDemoTest.wrongArgumentCanTriggerPotentialStubbingProblem
~~~

Với Windows PowerShell/Command Prompt và Gradle Wrapper:

~~~powershell
.\gradlew.bat test --tests demo.testing.StrictStubsFailureDemoTest.unusedStubTriggersUnnecessaryStubbing
.\gradlew.bat test --tests demo.testing.StrictStubsFailureDemoTest.wrongArgumentCanTriggerPotentialStubbingProblem
~~~

Mỗi lệnh sau khi bỏ @Disabled được **kỳ vọng thất bại có chủ đích**. Lệnh đầu nên chỉ ra **UnnecessaryStubbingException** và vị trí dòng when(...) không được dùng; lệnh sau có thể báo **PotentialStubbingProblem** ở lời gọi mock với đối số không khớp. Thông điệp/stack trace chính xác phụ thuộc Mockito, Gradle và JDK; không nên khẳng định một chuỗi stdout cứng.

Khi kết thúc thử nghiệm, **đặt lại @Disabled** hoặc xóa class demo lỗi khỏi mã thực. Đừng “sửa” bằng cách đặt LENIENT cho toàn bộ suite; bài test minh họa cần cho thấy nguyên nhân thiếu sử dụng stub.

### 5.4. Chạy toàn bộ test và xem báo cáo

Nếu project đã có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

Bộ ví dụ gồm **ba test PASS** trong InvoiceServiceTest và **hai test bị disabled** trong StrictStubsFailureDemoTest. Báo cáo JUnit của Gradle tại **build/reports/tests/test/index.html** cho biết số lượt thành công/bị bỏ qua/thất bại; kiểm tra thực tế vì những test khác trong dự án hoặc cấu hình lọc có thể làm tổng số thay đổi.

Nếu không có Wrapper, tạo Wrapper bằng Gradle tương thích đã cài hoặc dùng lệnh gradle test. Các tệp minh họa ở trên có đủ source/build logic cho ví dụ; riêng lệnh ./gradlew đòi hỏi các tệp Wrapper của project.

## 6. Sửa lỗi đúng cách: trước và sau

### 6.1. Xóa stub không phục vụ điều được kiểm thử

**Trước:**

~~~java
when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
assertEquals("INV-42", service.label(42L));
~~~

**Sau:**

~~~java
assertEquals("INV-42", service.label(42L));
verifyNoInteractions(repository);
~~~

Hai đoạn là **nội dung trong phương thức test đã cấu hình mock/service**, không phải file Java độc lập. Sau khi sửa, test diễn tả rõ yêu cầu “tạo nhãn không cần repository”; việc stub một hóa đơn là vô nghĩa với yêu cầu này. Nếu có nhiều test khác cần tìm hóa đơn 42, chúng phải tự thiết lập stub đúng tình huống của mình.

### 6.2. Căn chỉnh đối số trong test và code

**Trước:**

~~~java
when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
assertEquals(120_000L, service.amountVnd(43L));
~~~

**Sau, khi yêu cầu là hóa đơn 42:**

~~~java
when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
assertEquals(120_000L, service.amountVnd(42L));
~~~

Nếu yêu cầu thực ra là hóa đơn 43 thì phải sửa stubbing và expected theo dữ liệu của hóa đơn 43; không ép service gọi ID 42 chỉ để khớp mock. Khi nhận lỗi PotentialStubbingProblem, so sánh dữ liệu đầu vào ở **cả hai phía**, rồi kiểm tra matcher được dùng.

### 6.3. Hạn chế stubbing chung trong @BeforeEach

**Mẫu dễ tạo stub thừa:**

~~~java
@BeforeEach
void setUp() {
    when(repository.findById(42L))
            .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
}

// Một test chỉ gọi service.label(42L) sẽ không dùng stub.
~~~

**Ưu tiên:**

~~~java
@Test
void readsAmount() {
    when(repository.findById(42L))
            .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
    assertEquals(120_000L, service.amountVnd(42L));
}

@Test
void formatsLabelWithoutRepository() {
    assertEquals("INV-42", service.label(42L));
}
~~~

Đây là các snippet minh họa **bên trong class test** và giả sử đã có import, @Mock, @InjectMocks và MockitoExtension như ví dụ hoàn chỉnh. Những cấu hình chung **luôn được dùng** có thể ở fixture, nhưng các stub chỉ áp dụng cho một số bài test nên nằm gần assertion tương ứng. Đặc biệt với @ParameterizedTest, cùng @BeforeEach có thể chạy cho từng invocation trong khi không phải invocation nào cũng đi vào nhánh dùng stub.

## 7. STRICT_STUBS, WARN và LENIENT: mức nào dành cho việc gì?

| Strictness | Khi có stub không dùng | Khi có argument mismatch | Khi nên dùng |
|---|---|---|---|
| **STRICT_STUBS** | Có thể làm test thất bại với UnnecessaryStubbingException | Có thể làm test thất bại sớm với PotentialStubbingProblem | Mặc định khuyến nghị cho các test mới, nhất là unit test dùng MockitoExtension |
| **WARN** | In cảnh báo/hint thay vì tự động fail vì chính kiểm tra này | In hint khi nhận diện sai lệch | Giai đoạn chuyển đổi nếu chưa xử lý hết; phải đọc và xử lý warning |
| **LENIENT** | Bỏ qua kiểm tra strict stubbing tương ứng | Bỏ qua kiểm tra mismatch tương ứng | Ngoại lệ hẹp khi một stubbing cố ý không dùng trong một số nhánh |

**Đặt strictness cho test class:**

~~~java
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.STRICT_STUBS)
class ExampleTest {
    // @Mock và @Test...
}
~~~

Snippet này không phải tệp Java độc lập; cần import từ Mockito/JUnit Jupiter và nội dung class test. Có thể thay STRICT_STUBS bằng WARN hoặc LENIENT ở cấp test class, nhưng không nên hạ chế độ cả class chỉ để bỏ qua một stub không cần thiết.

**Giảm strictness cho đúng một stubbing khi thật sự có lý do:**

~~~java
// Cần static import org.mockito.Mockito.lenient;
lenient().when(repository.findById(42L))
        .thenReturn(Optional.of(new Invoice(42L, 120_000L)));
~~~

Stubbing được đánh dấu lenient không phải tuân theo kiểm tra unused-stub/argument-mismatch của strict stubbing; những stub khác trong test vẫn được kiểm tra bình thường. Đây là phương án **cuối cùng sau khi đã xem xét bỏ/move stub**. Nếu dùng lenient cho một mock hoặc test class, phạm vi bỏ kiểm tra rộng hơn và nguy cơ che lỗi cao hơn.

**Ví dụ mức độ ở phạm vi mock:**

~~~java
@Mock(strictness = Mock.Strictness.LENIENT)
InvoiceRepository repository;
~~~

Cần import **org.mockito.Mock**. Với Mockito 5, nên dùng thuộc tính strictness này nếu thật sự muốn đặt ở mức mock; cú pháp @Mock(lenient = true) thuộc API cũ đã được khuyến nghị thay thế. Tránh cấu hình cho toàn bộ mock khi chỉ một stubbing cần ngoại lệ.

**Khi cần tự quản lý lifecycle:** MockitoSession cho phép thiết lập strictness và đóng session bằng finishMocking(). Nếu chỉ dùng JUnit Jupiter, MockitoExtension đã xử lý vòng đời giúp bạn; không cần vừa gắn MockitoExtension vừa tự gọi openMocks()/mở session thứ hai cho cùng các trường trong mỗi test.

## 8. Khi nào unused stub là dấu hiệu bug chứ không chỉ là mã thừa?

Một stub không dùng có thể chỉ ra:
- **Sai nhánh code:** Test định kiểm tra khi repository trả một dữ liệu, nhưng method đang test không gọi repository.
- **Sai ID/đối số:** Cấu hình findById(42L), SUT gọi findById(43L); một trong hai phía không đúng với kịch bản.
- **Mock nhầm đối tượng:** Có nhiều instance service hoặc repository; stub đặt trên mock A, code đang dùng mock B hoặc bean Spring thật.
- **Cấu hình đã lỗi thời:** Refactor bỏ lời gọi dependency nhưng test vẫn giữ setup cũ.
- **Dùng matcher không phù hợp:** equals trên DTO chưa được định nghĩa đúng, object được tạo lại không equal, hoặc trộn matcher với literal không đúng quy tắc Mockito.
- **Không đi qua nhánh dự định:** Điều kiện đầu vào, feature flag, cache hoặc exception làm service trả sớm trước khi dùng stub.
- **Copy-paste fixture:** @BeforeEach cấu hình nhiều phương thức cho mọi test dù phần lớn test không dùng đến.

**Cách điều tra thực tế:**

1. Đọc stack trace tại dòng stubbing mà Mockito nêu; xác định mock, method và đối số.
2. Tìm trong **method đang test** lời gọi dependency nào được dự kiến sử dụng stubbing. Dùng debugger khi control flow phức tạp.
3. Đối chiếu input của test với argument của stub. Nếu SUT dùng ID khác, tìm nguyên nhân và sửa đúng phía.
4. Kiểm tra instance: @InjectMocks đã nhận chính @Mock chưa? Với @SpringBootTest có đang inject một bean khác không?
5. Nếu stub thật sự không phục vụ assertion nào, **xóa** hoặc chuyển vào test cần nó.
6. Chỉ dùng lenient sau khi có lý do rõ ràng, có thể mô tả trong một câu tại vị trí stubbing.
7. Chạy lại test và kiểm tra cả assertion nghiệp vụ lẫn báo cáo Mockito; đừng chỉ xác nhận lỗi strictness đã biến mất.

Đừng giải quyết UnnecessaryStubbingException bằng **verify(repository).findById(42L)** khi service không gọi nó: verification này sẽ tự thất bại. Cũng đừng thêm lời gọi mock trực tiếp trong test chỉ để tiêu thụ stub; như vậy có thể che lỗi nhánh thực sự mà bạn muốn kiểm tra.

## 9. Phân biệt strict stubbing với các công cụ kiểm tra khác

| Công cụ | Kiểm tra gì? | Khác strict stubbing thế nào? |
|---|---|---|
| **assertEquals/assertThrows** | Giá trị trả về, ngoại lệ và quy tắc nghiệp vụ | Không tự kiểm tra unused stub |
| **verify(mock).method(...)** | Phương thức mock đã được gọi với đối số nhất định | Có thể dùng khi không hề tạo stub |
| **verifyNoInteractions(mock)** | Mock không có tương tác nào | Khẳng định nhánh không gọi dependency |
| **verifyNoMoreInteractions(mock)** | Không còn tương tác chưa được xác minh | STRICT_STUBS tự tính các invocation đã được stub là verified cho mục đích kiểm tra này |
| **UnnecessaryStubbingException** | Stub được định nghĩa nhưng chưa dùng | Chẩn đoán fixture thừa hoặc luồng chạy sai |
| **PotentialStubbingProblem** | Sai lệch đối số giữa stubbing và invocation mà Mockito nhận diện | Chẩn đoán cấu hình mock/luồng xử lý nghi vấn |
| **JUnit assertion/coverage report** | Assertion đúng sai, vùng code đã chạy | Coverage cao vẫn có thể kèm stub thừa và assertion yếu |

Một test có thể **PASS các assertion** nhưng bị MockitoExtension đánh dấu fail lúc kết thúc do stub thừa. Đây là hành vi mong đợi của strict stubbing, không phải lỗi cấu hình Gradle. Ngược lại, một test hoàn toàn không tạo stub thừa vẫn có thể kiểm thử thiếu, ví dụ chỉ gọi service mà không assert kết quả.

**Đừng dùng verifyNoMoreInteractions trên mọi mock một cách máy móc.** Assertion đó ràng buộc chi tiết tương tác và có thể khiến refactor nội bộ hợp lệ làm test giòn. Nên xác minh tương tác khi đó là yêu cầu quan trọng, ví dụ “không gọi thanh toán lần hai”.

## 10. Mockito trong Spring Boot: @Mock và @MockBean không có cùng vòng đời

Ở unit test minh họa:
- **@ExtendWith(MockitoExtension.class)** kích hoạt vòng đời strict stubbing của Mockito cho các mock do extension tạo.
- **@Mock** tạo InvoiceRepository giả lập không nằm trong Spring ApplicationContext.
- **@InjectMocks** khởi tạo InvoiceService rồi đưa mock vào constructor của service. Nó không tự tạo bean Spring.
- Không cần **@SpringBootTest**, nên test nhanh và dễ đọc lý do stub dùng hay không.

Ở integration test dùng **@SpringBootTest**, Spring Boot 3.3.x có **@MockBean** để tạo/thay thế bean trong ApplicationContext. Test lúc đó có thêm lifecycle của Spring TestContext, caching context và reset mocks. **Không nên mặc định rằng mọi @MockBean đều nhận cùng kiểm tra unused stubbing như mock được quản lý bởi MockitoExtension**; cần xem cấu hình tích hợp và hành vi thực tế của phiên bản đang dùng.

Nếu mock đã được đặt vào Spring context nhưng SUT vẫn gọi một dependency khác, unused stubbing là tín hiệu phải kiểm tra wiring/bean selection thay vì vội bật lenient. Dùng MockitoExtension cho unit test thuần Mockito; dùng Spring test support khi cần chứng minh bean wiring, web layer hoặc tích hợp thực.

**Cảnh báo về spy:** Với spy, **when(spy.realMethod())** có thể thực thi phương thức thật trong lúc khai báo stubbing, dẫn đến side effect hoặc exception. Với trường hợp đó, nên xem xét **doReturn(value).when(spy).realMethod(...)**. Đây là vấn đề của cơ chế stubbing spy; strict stubbing vẫn có thể kiểm tra stub không dùng sau đó.

## 11. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| UnnecessaryStubbingException dù assertEquals pass | Stub chưa được SUT gọi; phát hiện sau test | Xóa stub hoặc chuyển vào test sử dụng |
| PotentialStubbingProblem khi gọi service | SUT gọi mock với đối số khác stub | Kiểm tra input, ID, matcher; sửa đúng kịch bản |
| Dùng @BeforeEach rồi test không cần repository vẫn fail | Setup chung tạo stub cho mọi test | Tạo stub ở từng test hoặc dùng fixture không stub |
| Đổi Strictness.LENIENT thì build xanh | Đã tắt kiểm tra chứ chưa sửa nguyên nhân | Khôi phục STRICT_STUBS, xác định đường chạy |
| Stub có vẻ được dùng nhưng Mockito báo khác | Stub trên mock A, SUT dùng mock/bean B | Kiểm tra constructor injection và context |
| Có Mockito dependency nhưng không báo unused stub | Chưa có MockitoExtension/MockitoSession hoặc strictness bị hạ | Kiểm tra test annotation, engine và lifecycle |
| Test dùng matcher quá rộng như anyLong() | Mock trả dữ liệu cho các ID sai, che bug | Dùng ID/matcher cụ thể khi kịch bản yêu cầu |
| Stub cùng một method nhiều lần gây mismatch | Cách khai báo when() có thể bị tính như invocation | Xem doReturn().when hoặc BDD willReturn().given và rationale |
| Bỏ annotation @Disabled cho cả demo lỗi khiến build fail | Hai bài test lỗi cố ý được chạy | Thử từng method, sau đó restore @Disabled |
| verifyNoMoreInteractions gây fail khi thêm lời gọi nội bộ | Test khóa chặt tương tác không cần thiết | Chỉ xác minh tương tác quan trọng với nghiệp vụ |
| Dùng @MockBean như @Mock trong unit test | Khác vòng đời Spring context và MockitoExtension | Chọn đúng mức unit/integration và kiểm tra wiring |

## 12. Quy trình áp dụng trong dự án và CI

Khi phát hiện test Mockito thất bại vì strict stubbing:
1. **Xem tên exception** và dòng stubbing mà Mockito đưa ra.
2. **Đọc yêu cầu của test:** Đường code nào phải chạy? Kết quả hoặc tương tác nào cần chứng minh?
3. **So stub với invocation thực:** Method, đối số, matcher, instance mock/bean và nhánh xử lý.
4. **Sửa nguyên nhân:** Xóa stub thừa, thiết lập stub đúng ID hoặc thay assertion/fixture cho đúng quy tắc.
5. **Nếu có ngoại lệ hợp lệ:** Giới hạn leniency vào một stubbing cụ thể, giải thích rõ lý do; tránh tắt strictness toàn bộ dự án.
6. **Chạy lại test:** Dùng lệnh Gradle/Maven mà CI thật sự sử dụng, xem báo cáo thất bại và test bị skip; không dựa vào “compiles successfully”.
7. **Giữ test độc lập:** Mỗi test tạo stub mình cần, không dựa vào thứ tự chạy hay mock state được lưu từ test khác.

Trong code review, câu hỏi hữu ích là: “Stub này phục vụ assertion hoặc nhánh nghiệp vụ nào?” Nếu không chỉ ra được, nó có thể không cần thiết. Trong CI, strict stubbing giúp buộc test fixture rõ ràng hơn, nhưng vẫn phải đi cùng assertion về kết quả và kiểm thử tích hợp ở nơi có rủi ro wiring, database hoặc HTTP.

## 13. Ghi nhớ và nguồn đối chiếu

- **STRICT_STUBS** kiểm tra cấu hình stubbing không dùng và có thể phát hiện invocation sai đối số; **LENIENT** bỏ những kiểm tra này, còn **WARN** chủ yếu cảnh báo.
- **UnnecessaryStubbingException** thường là dấu hiệu xóa/move một stub, không phải tín hiệu cần thêm verify vô ích.
- **PotentialStubbingProblem** gợi ý so sánh đối số mà test đã stub với đối số SUT thực sự gọi.
- **MockitoExtension** là lựa chọn tự nhiên cho unit test JUnit Jupiter. Khai báo @MockitoSettings rõ ràng giúp người đọc hiểu phạm vi strictness.
- **Ưu tiên loại bỏ stubbing thừa**, giữ fixture theo từng test và chỉ dùng lenient cho trường hợp có lý do cụ thể.

Tài liệu tham khảo để tra cứu hành vi và API của Mockito:
- [Mockito Strictness (Javadoc)](https://javadoc.io/static/org.mockito/mockito-core/5.14.2/org/mockito/quality/Strictness.html)
- [UnnecessaryStubbingException (Javadoc)](https://javadoc.io/static/org.mockito/mockito-core/5.11.0/org/mockito/exceptions/misusing/UnnecessaryStubbingException.html)
- [PotentialStubbingProblem (Javadoc)](https://www.javadoc.io/static/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/exceptions/misusing/PotentialStubbingProblem.html)
- [MockitoExtension (mã nguồn Mockito)](https://github.com/mockito/mockito/blob/main/mockito-extensions/mockito-junit-jupiter/src/main/java/org/mockito/junit/jupiter/MockitoExtension.java)
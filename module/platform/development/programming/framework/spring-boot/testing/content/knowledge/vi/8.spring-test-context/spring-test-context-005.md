# TestExecutionListener và các giai đoạn vòng đời kiểm thử

## 1. TestExecutionListener là gì?

**Spring TestContext Framework** là hạ tầng giúp JUnit Jupiter kết hợp với Spring để nạp và cache `ApplicationContext`, tiêm bean vào test, quản lý giao dịch, chạy tập lệnh SQL, xử lý `@DirtiesContext` và các công việc chuẩn bị/dọn dẹp khác.

`org.springframework.test.context.TestExecutionListener` là một **SPI (Service Provider Interface)** cho những hành vi muốn tham gia vào vòng đời kiểm thử đó. Một listener nhận đối tượng `TestContext` ở các thời điểm đã định, có thể ghi log, chuẩn bị tài nguyên, kiểm tra trạng thái hoặc dọn dẹp sau một giai đoạn.

Ba thành phần cốt lõi:

- **`TestContext`**: mang ngữ cảnh kiểm thử như lớp test, instance hiện tại, method hiện tại, exception của test method, và khả năng truy cập `ApplicationContext` khi cần.
- **`TestContextManager`**: quản lý ngữ cảnh kiểm thử và điều phối các listener. Nó gọi từng callback theo giai đoạn, quyết định thứ tự xử lý.
- **`TestExecutionListener`**: cung cấp các hook ở cấp Spring TestContext; mỗi implementation chỉ cần override những hook thật sự sử dụng.

Trong JUnit Jupiter, **`SpringExtension`** nối vòng đời JUnit với `TestContextManager`. Các annotation như `@SpringBootTest` hoặc `@SpringJUnitConfig` thường đã tích hợp SpringExtension, không cần đăng ký `@ExtendWith(SpringExtension.class)` trùng lặp.

**Phân biệt quan trọng:** listener không phải là một phương thức `@Test` và không trực tiếp quyết định nghiệp vụ của ứng dụng. Unit test dùng `new Service(...)` thuần Java thường không cần TestContext hoặc listener; cơ chế này hữu ích khi đang kiểm tra tương tác với Spring context hoặc cần một lifecycle hook dùng chung.

## 2. Bảy callback trong một vòng đời Spring TestContext

`TestExecutionListener` định nghĩa các callback sau (trong Spring Framework 6.x/7.x; tên API ổn định trong các phiên bản được nhắc đến). Mỗi callback nhận tham số `TestContext`.

| Callback | Thời điểm JUnit Jupiter tương ứng | Mục đích thường gặp |
| --- | --- | --- |
| `beforeTestClass(TestContext)` | Trước các phương thức `@BeforeAll` của lớp | Chuẩn bị tài nguyên cấp lớp hoặc ghi nhận bắt đầu kiểm thử |
| `prepareTestInstance(TestContext)` | Ngay sau khi JUnit tạo instance lớp test | Tiêm dependency vào test instance, xử lý dữ liệu cấp instance |
| `beforeTestMethod(TestContext)` | Trước `@BeforeEach` | Thiết lập fixture, bắt đầu test-managed transaction |
| `beforeTestExecution(TestContext)` | Sau `@BeforeEach`, ngay trước phần thân `@Test` | Bắt đầu tính thời gian riêng thân test, ghi trace |
| `afterTestExecution(TestContext)` | Ngay sau phần thân `@Test`, trước `@AfterEach` | Ghi kết quả, kết thúc đo thời gian thân test |
| `afterTestMethod(TestContext)` | Sau `@AfterEach` | Dọn tài nguyên, kết thúc transaction, hoàn tất xử lý quanh từng test |
| `afterTestClass(TestContext)` | Sau `@AfterAll` | Dọn tài nguyên cấp lớp, tổng hợp trace hoặc báo cáo cuối lớp |

Các từ “Method” trong `beforeTestMethod` và `afterTestMethod` **dễ gây nhầm**. `beforeTestMethod` không có nghĩa “ngay sát dòng đầu tiên của `@Test`”: nó chạy **trước setup**. Tương tự, `afterTestMethod` chạy **sau teardown**. Nếu muốn thời điểm bao quanh đúng **thân test**, hãy dùng cặp `beforeTestExecution` / `afterTestExecution`.

`prepareTestInstance` được gọi trên từng instance test được JUnit tạo. Với lifecycle mặc định `PER_METHOD`, mỗi test invocation thông thường có instance riêng. Khi chuyển sang `@TestInstance(PER_CLASS)`, số lần tạo/chuẩn bị instance có thể khác; không mặc định callback này luôn chạy đúng một lần cho mỗi test method.

### Sơ đồ tổng quan cho một test duy nhất

~~~text
Spring: listener.beforeTestClass
JUnit : @BeforeAll
JUnit : tạo instance lớp test
Spring: listener.prepareTestInstance
Spring: listener.beforeTestMethod
JUnit : @BeforeEach
Spring: listener.beforeTestExecution
JUnit : @Test / thân phương thức kiểm thử
Spring: listener.afterTestExecution
JUnit : @AfterEach
Spring: listener.afterTestMethod
JUnit : @AfterAll
Spring: listener.afterTestClass
~~~

Sơ đồ cho thấy các **điểm móc chính**, không phải mọi thao tác nội bộ của Spring/JUnit. Spring còn thực thi nhiều default listener, extension và cơ chế quản lý context mà sơ đồ không vẽ ra. Với nhiều test invocation, khối từ `beforeTestMethod` đến `afterTestMethod` được lặp theo từng invocation; các callback cấp lớp bao quanh cả lớp.

## 3. SpringExtension kết nối JUnit Jupiter với Spring như thế nào?

JUnit Jupiter có mô hình extension riêng: `BeforeAllCallback`, `TestInstancePostProcessor`, `BeforeEachCallback`, `BeforeTestExecutionCallback`, `AfterTestExecutionCallback`, `AfterEachCallback` và `AfterAllCallback`. `SpringExtension` triển khai các điểm kết nối phù hợp và chuyển sự kiện sang `TestContextManager`.

Ví dụ class test dùng Spring context mà không khai báo `@ExtendWith` trực tiếp:

~~~java
@SpringJUnitConfig(TestConfig.class)
class ExampleSpringTest {
    @Autowired
    Clock clock;

    @Test
    void readsClockFromSpring() {
        assertNotNull(clock);
    }
}
~~~

Đây là **đoạn minh họa**, cần `TestConfig` và các import tương ứng. `@SpringJUnitConfig` là composed annotation gồm cấu hình context và đăng ký `SpringExtension`. Với Spring Boot, `@SpringBootTest` cũng tích hợp SpringExtension; các slice như `@WebMvcTest` hoặc `@DataJpaTest` được Boot hỗ trợ theo cách thích hợp.

Nếu chỉ viết `@TestExecutionListeners(...)` lên một lớp JUnit thuần nhưng **không hề bật Spring TestContext integration**, không thể kỳ vọng Spring tự gọi listener. Phải có cơ chế kết nối Spring, ví dụ `@SpringJUnitConfig`, `@SpringBootTest` hoặc `@ExtendWith(SpringExtension.class)` kết hợp cấu hình Spring thích hợp.

### Thứ tự với @BeforeEach / @AfterEach

Hai mốc cần nhớ:

- `beforeTestMethod` xảy ra **trước** `@BeforeEach`. Bởi vậy, listener ở mốc này không được giả định fixture được tạo trong `@BeforeEach` đã sẵn sàng.
- `beforeTestExecution` xảy ra **sau** `@BeforeEach`. Đây là điểm phù hợp khi cần đo riêng thời gian thân `@Test`, không tính thời gian setup do JUnit thực hiện.
- `afterTestExecution` xảy ra **trước** `@AfterEach`. Có thể quan sát exception của test method, nhưng teardown chưa hoàn tất.
- `afterTestMethod` xảy ra **sau** `@AfterEach`. Có thể dùng để dọn những tài nguyên được giữ suốt quá trình setup + test + teardown.

Các khác biệt này đặc biệt quan trọng với `@Transactional`, `@Sql`, thống kê thời gian và việc quan sát state sau test.

## 4. Các listener có sẵn của Spring đảm nhiệm những gì?

Phần lớn dự án **không cần tự viết** `TestExecutionListener`. Spring TestContext đã đăng ký các listener mặc định; Spring Boot và thư viện khác còn có thể bổ sung listener.

| Listener minh họa | Trách nhiệm chính |
| --- | --- |
| `DependencyInjectionTestExecutionListener` | Tiêm bean/giá trị vào test instance |
| `DirtiesContextBeforeModesTestExecutionListener` | Xử lý các chế độ `@DirtiesContext` diễn ra trước test/lớp |
| `DirtiesContextTestExecutionListener` | Xử lý những chế độ đánh dấu context bẩn sau test/lớp |
| `TransactionalTestExecutionListener` | Quản lý test-managed transaction của test có `@Transactional` |
| `SqlScriptsTestExecutionListener` | Chạy `@Sql` tại giai đoạn được cấu hình |
| `ServletTestExecutionListener` | Thiết lập servlet mock cho web test context |
| `EventPublishingTestExecutionListener` | Phát các test execution event khi điều kiện cho phép |
| `ApplicationEventsTestExecutionListener` | Hỗ trợ ghi nhận application events trong test |
| Các listener cho bean override/mock, cache hoặc quan sát | Phụ thuộc phiên bản Spring Framework, Spring Boot và các integration thực sự có trên classpath |

**Không đóng đinh danh sách/giá trị `@Order` cho mọi phiên bản:** tập listener mặc định có thể thay đổi khi nâng cấp Spring/Boot. Ví dụ các listener xử lý bean override và observation xuất hiện ở những đời framework mới; muốn biết cấu hình hiện hành, hãy kiểm tra tài liệu và dependency thực tế của dự án.

Ví dụ về giao dịch: `TransactionalTestExecutionListener` có thể bắt đầu transaction quanh một test có `@Transactional`, rồi rollback mặc định sau test trong điều kiện sử dụng test-managed transaction thông thường. Các callback per-test của JUnit chạy trong phạm vi transaction đó; thời điểm đóng transaction là sau `@AfterEach` theo thứ tự TestContext.

**Không tự viết listener để thay thế một default listener đã làm đúng việc.** Việc thêm listener mới chỉ hợp lý khi có nhu cầu thật như ghi trace thống nhất, chuẩn bị môi trường đặc thù, bắt sự kiện kiểm thử dùng chung hoặc tích hợp hệ thống đo đạc.

## 5. Đăng ký custom listener bằng @TestExecutionListeners

Đặt annotation `@TestExecutionListeners` trên lớp test để khai báo một hoặc nhiều implementation:

~~~java
@TestExecutionListeners(
        listeners = AuditTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
~~~

Đây là **đoạn annotation trong lớp test**, `AuditTestExecutionListener` chỉ là tên minh họa; ví dụ chạy được ở phần 6 sử dụng một lớp listener cụ thể.

### REPLACE_DEFAULTS và MERGE_WITH_DEFAULTS khác nhau thế nào?

| `mergeMode` | Ý nghĩa | Rủi ro/lợi ích |
| --- | --- | --- |
| `REPLACE_DEFAULTS` | Tập listener khai báo tại chỗ thay thế tập mặc định theo cơ chế cấu hình của Spring | Dễ vô tình bỏ dependency injection, transaction, `@Sql` hoặc những integration mặc định |
| `MERGE_WITH_DEFAULTS` | Gộp listener tự khai báo với các listener mặc định; loại trùng và sắp xếp | Thường là lựa chọn an toàn để bổ sung một listener vào hệ thống có sẵn |

Khi khai báo custom listener mà không chỉ định mergeMode, cấu hình mặc định của annotation là `REPLACE_DEFAULTS`. Vì vậy, trong phần lớn bài test Spring Boot, **nên ghi rõ `MERGE_WITH_DEFAULTS`** khi chỉ muốn bổ sung chức năng. Không đánh đổi toàn bộ cơ chế default để lấy một hook ghi log.

Khi kế thừa class test hoặc dùng `@Nested`, còn phải xét `inheritListeners` và chính sách kế thừa của TestContext. Một listener có thể được khai báo ở class cha/ngoài và được kế thừa theo cấu hình; đừng đăng ký trùng lặp nếu không cần.

### Thứ tự xử lý nhiều listener

Khi có nhiều listener, Spring sắp xếp theo thứ tự xác định, có xét `Ordered` hoặc `@Order` (qua `AnnotationAwareOrderComparator`) đối với tập listener được phát hiện/gộp theo cơ chế tương ứng. Số thứ tự **nhỏ hơn** thường có ưu tiên thực thi sớm hơn ở chiều “before”.

Nếu listener A đứng trước B:

~~~text
A.beforeTestMethod
  B.beforeTestMethod
  @BeforeEach / @Test / @AfterEach
  B.afterTestMethod
A.afterTestMethod
~~~

Đây là **wrapping behavior**: nhóm callback “after” chạy theo thứ tự **ngược** với “before”. Điều này không phải chi tiết trang trí; ví dụ listener quản lý transaction phải bao quanh listener chạy SQL trong những trường hợp cần SQL thực thi bên trong transaction.

Khi listener không tự chỉ định order, Spring có quy tắc đặt nó vào chuỗi; không nên suy ra thứ tự dựa vào vị trí tên class trong danh sách annotation nếu còn các listener mặc định. Khi thứ tự tác động đến hành vi, khai báo `@Order`/`Ordered` có chủ đích và xác minh quy tắc phù hợp với dependencies của dự án.

## 6. Ví dụ đầy đủ: in chính xác các giai đoạn của một test

Ví dụ minh họa chạy trong **Spring Boot 3.x / Spring Framework 6.x, Java 17+, JUnit Jupiter**. Ta xây dựng một listener tự ghi dấu callback, một test với một bean Spring, và in chuỗi thời gian ở `afterTestClass`. Bài test **cố ý chỉ có một `@Test`**, chạy tuần tự, để output dễ hiểu; đừng dùng một danh sách `static` không đồng bộ làm cơ chế trace cho cả một suite chạy song song.

### 6.1. Lớp listener

**Tệp `src/test/java/com/example/testing/LifecycleTraceListener.java`:**

~~~java
package com.example.testing;

import java.util.ArrayList;
import java.util.List;

import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class LifecycleTraceListener extends AbstractTestExecutionListener {
    static final List<String> EVENTS = new ArrayList<>();

    public LifecycleTraceListener() {
    }

    @Override
    public void beforeTestClass(TestContext context) {
        EVENTS.add("listener.beforeTestClass");
    }

    @Override
    public void prepareTestInstance(TestContext context) {
        EVENTS.add("listener.prepareTestInstance");
    }

    @Override
    public void beforeTestMethod(TestContext context) {
        EVENTS.add("listener.beforeTestMethod");
    }

    @Override
    public void beforeTestExecution(TestContext context) {
        EVENTS.add("listener.beforeTestExecution");
    }

    @Override
    public void afterTestExecution(TestContext context) {
        EVENTS.add("listener.afterTestExecution");
    }

    @Override
    public void afterTestMethod(TestContext context) {
        EVENTS.add("listener.afterTestMethod");
    }

    @Override
    public void afterTestClass(TestContext context) {
        EVENTS.add("listener.afterTestClass");
        EVENTS.forEach(System.out::println);
    }
}
~~~

`AbstractTestExecutionListener` có các method no-op và thứ tự mặc định phù hợp khi không cần ưu tiên riêng. Ở đây chỉ override những method muốn quan sát; interface `TestExecutionListener` cũng có default implementation rỗng nên có thể implement trực tiếp nếu muốn.

`EVENTS` chỉ phục vụ demo, là mutable static state và **không phù hợp làm bộ ghi trace dùng chung thực tế** khi nhiều class cùng dùng listener hoặc test chạy song song. Trong hệ thống thật, nên dùng logger, cấu trúc dữ liệu theo từng test/method hoặc một reporter/extension có quản lý concurrency đúng.

### 6.2. Lớp test tích hợp Spring TestContext

**Tệp `src/test/java/com/example/testing/LifecycleTraceTest.java`:**

~~~java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(LifecycleTraceTest.TestConfig.class)
@TestExecutionListeners(
        listeners = LifecycleTraceListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class LifecycleTraceTest {
    @Autowired
    Clock clock;

    @BeforeAll
    static void beforeAll() {
        LifecycleTraceListener.EVENTS.add("junit.BeforeAll");
    }

    @BeforeEach
    void beforeEach() {
        LifecycleTraceListener.EVENTS.add("junit.BeforeEach");
    }

    @Test
    void fixedClock_whenInjected_matchesExpectedInstant() {
        assertNotNull(clock);
        assertEquals(
                Instant.parse("2024-01-01T00:00:00Z"),
                clock.instant()
        );

        List<String> events = LifecycleTraceListener.EVENTS;
        assertEquals(
                "listener.beforeTestExecution",
                events.get(events.size() - 1)
        );

        events.add("junit.Test");
    }

    @AfterEach
    void afterEach() {
        LifecycleTraceListener.EVENTS.add("junit.AfterEach");
    }

    @AfterAll
    static void afterAll() {
        LifecycleTraceListener.EVENTS.add("junit.AfterAll");
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }
}
~~~

**Tại sao code chứng minh đúng vòng đời?**

- `@SpringJUnitConfig` đăng ký SpringExtension và tải cấu hình bean `Clock`, nhưng không khởi động một Spring Boot server đầy đủ.
- `@TestExecutionListeners(..., MERGE_WITH_DEFAULTS)` thêm listener mà vẫn giữ `DependencyInjectionTestExecutionListener`; nhờ đó `@Autowired Clock` được gán trước khi test dùng.
- `@BeforeAll` và `@AfterAll` là `static` theo test instance lifecycle mặc định của JUnit Jupiter.
- Phương thức test xác nhận `Clock` có giá trị được tiêm từ context và callback `beforeTestExecution` vừa xảy ra; nó ghi dấu `junit.Test` sau khi các assertion đạt.
- `afterTestClass` in các dòng đã ghi. Nếu test fail ở assertion, dòng `junit.Test` có thể không được ghi; output phía dưới được kỳ vọng cho **lần chạy thành công**.

### 6.3. Cấu hình và lệnh chạy

Trong dự án Spring Boot 3.x có plugin, repositories và Java toolchain/JDK 17+ đã cấu hình, thêm cấu hình test thông thường trong `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        showStandardStreams = true
    }
}
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter và Spring TestContext ở các phiên bản Spring Boot 3.x thông dụng. Đoạn cấu hình không phải nguyên tệp build độc lập.

Chạy từ thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.testing.LifecycleTraceTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.testing.LifecycleTraceTest"
~~~

Với đúng hai tệp ở trên, một test method, cấu hình hợp lệ và không có test chạy đồng thời dùng chung `EVENTS`, **12 dòng do `System.out.println` trong listener in ra** theo thứ tự:

~~~text
listener.beforeTestClass
junit.BeforeAll
listener.prepareTestInstance
listener.beforeTestMethod
junit.BeforeEach
listener.beforeTestExecution
junit.Test
listener.afterTestExecution
junit.AfterEach
listener.afterTestMethod
junit.AfterAll
listener.afterTestClass
~~~

Gradle/Spring có thể xuất thêm log và metadata của test runner. Danh sách trên là **các dòng do ví dụ chủ động in**, không phải toàn bộ stdout của Gradle. Vì mã test cần thư viện Spring/JUnit, không thể chỉ chạy `javac LifecycleTraceTest.java` mà không cung cấp dependency classpath; dùng Gradle/Maven đã cấu hình là đúng cách.

## 7. Đọc TestContext để làm gì?

Listener nhận `TestContext`. Những API thường hữu ích:

| API | Ý nghĩa | Khi nên truy cập |
| --- | --- | --- |
| `getTestClass()` | Lớp kiểm thử đang được quản lý | Khi ghi thông tin cấp lớp |
| `getTestInstance()` | Instance của lớp test hiện tại | Sau khi instance đã được tạo |
| `getTestMethod()` | Phương thức test hiện tại | Khi đang trong giai đoạn theo từng test |
| `getTestException()` | Exception do **thân test** ném ra, nếu có | Sau `afterTestExecution`/giai đoạn thích hợp, theo hợp đồng API |
| `getApplicationContext()` | Truy cập Spring context của test, có thể kích hoạt tải context nếu chưa có | Khi listener thực sự cần bean/config |
| `setAttribute(...)` / `getAttribute(...)` | Lưu thông tin theo test context | Khi cần state nhỏ giữa các callback; lưu ý concurrency |

Đừng gọi `getTestInstance()` trong `beforeTestClass` rồi giả định đã có đối tượng: ở thời điểm đó chưa qua bước tạo test instance. Tương tự, không dùng `getTestException()` để kết luận toàn bộ test đã thành công hay thất bại, vì lỗi trong `@BeforeEach`, `@AfterEach` hoặc callback khác không nhất thiết được biểu diễn giống lỗi của thân `@Test`.

### Ví dụ một listener đo thời gian phần thân @Test

Đây là **đoạn triển khai minh họa đặt trong một class listener**, không phải tệp Java độc lập:

~~~java
private static final String START_KEY = "example.test.startNanos";

@Override
public void beforeTestExecution(TestContext context) {
    context.setAttribute(START_KEY, System.nanoTime());
}

@Override
public void afterTestExecution(TestContext context) {
    Long start = context.getAttribute(START_KEY);
    if (start != null) {
        long elapsedNanos = System.nanoTime() - start;
        System.out.println("Elapsed ns: " + elapsedNanos);
        context.removeAttribute(START_KEY);
    }
}
~~~

Với `TestContext`, `getAttribute` trả `Object`; code trên **cần ép kiểu** vì compiler Java không tự chuyển `Object` thành `Long`. Cách viết đúng để nhúng vào class listener là:

~~~java
@Override
public void afterTestExecution(TestContext context) {
    Object value = context.removeAttribute(START_KEY);
    if (value instanceof Long start) {
        long elapsedNanos = System.nanoTime() - start;
        System.out.println("Elapsed ns: " + elapsedNanos);
    }
}
~~~

Hai đoạn được đặt cạnh nhau để nhấn mạnh việc **kiểm tra kiểu** khi lấy attribute; **không dán cả hai phương thức `afterTestExecution` vào cùng một class**. Chỉ dùng biến thể thứ hai trong code thật, kèm `START_KEY` và `beforeTestExecution` phía trên. Chỉ số `nanoTime` phù hợp tính khoảng thời gian trôi qua, không phải thời điểm đồng hồ thực; giá trị đo **không có stdout cố định**.

Nếu mục tiêu là đo cả setup và teardown, cặp `beforeTestMethod`/`afterTestMethod` mới là điểm bao phù hợp hơn. Đừng gộp các khoảng thời gian khác nhau rồi diễn giải thành “thời gian business code” một cách thiếu chính xác.

## 8. Giao dịch, @Sql và @DirtiesContext gắn với giai đoạn nào?

### Test-managed transaction

Trong test Spring có `@Transactional` với `TransactionalTestExecutionListener` mặc định, Spring thường bắt đầu transaction ở `beforeTestMethod` (tức **trước** `@BeforeEach`) và kết thúc sau `@AfterEach` tại `afterTestMethod`. Với test-managed transaction thông thường, rollback là mặc định nếu không có cấu hình commit khác.

~~~text
TransactionalTestExecutionListener.beforeTestMethod
    → bắt đầu transaction
JUnit @BeforeEach
JUnit @Test
JUnit @AfterEach
TransactionalTestExecutionListener.afterTestMethod
    → rollback/commit theo cấu hình
~~~

**Bẫy:** Dữ liệu được ghi trong `@BeforeEach` thường nằm trong transaction test-managed nếu dùng đúng hạ tầng hỗ trợ. Nếu test mở thread mới, gọi hệ thống ngoài hoặc có giao dịch riêng, đừng tự kết luận mọi tác động đều được rollback. Muốn chạy logic **ngoài** transaction test, Spring cung cấp `@BeforeTransaction`/`@AfterTransaction` cho mục đích thích hợp.

### @Sql

`SqlScriptsTestExecutionListener` thi hành script cho `@Sql` tại giai đoạn quy định (ví dụ `BEFORE_TEST_METHOD` hoặc `AFTER_TEST_METHOD`). Thứ tự tương đối với `TransactionalTestExecutionListener` và cấu hình `@SqlConfig(transactionMode=...)` quyết định script được thực thi trong test transaction hay transaction khác.

Không dùng custom listener xóa hết bảng ở `afterTestExecution` nếu `@AfterEach` hoặc `@Sql(AFTER_TEST_METHOD)` vẫn cần dữ liệu; hiểu rõ **listener order** và thời điểm dọn là điều kiện để không gây lỗi khó tái hiện.

### @DirtiesContext

`@DirtiesContext` đánh dấu ApplicationContext không còn an toàn để tái sử dụng và ảnh hưởng tới context caching. Các listener xử lý before/after modes có thời điểm riêng. Điều này **không tương đương** rollback database, reset mọi file, đóng mọi kết nối hệ thống bên ngoài hoặc luôn tạo context mới cho từng test.

Dùng `@DirtiesContext` khi test thực sự làm thay đổi trạng thái context có ảnh hưởng đến test khác; lạm dụng khiến suite chậm do phải tải context lại.

## 9. Lỗi trong callback và việc cleanup

Vòng đời listener có thể thất bại, và một lỗi ở hook setup có thể khiến thân `@Test` không được thực thi. Vì thế:

- **Hook “before”**: nếu một listener ném exception trong giai đoạn “before”, các listener còn lại tại chính giai đoạn đó có thể không được gọi; test có thể bị đánh dấu lỗi trước khi vào thân test.
- **Hook “after”**: Spring TestContextManager cố gắng gọi các listener cleanup còn lại theo thứ tự ngược ngay cả khi một listener “after” lỗi; exception đầu tiên được báo, các lỗi sau có thể được đính kèm dưới dạng suppressed.
- **Lỗi làm JVM dừng đột ngột**: không bảo đảm cleanup cuối lớp/test luôn chạy.
- **Tham chiếu state**: không giả định callback luôn có đủ `TestContext.getTestMethod()`, instance hoặc ApplicationContext trong tất cả giai đoạn.

Tài nguyên được tạo bởi một listener nên có chủ sở hữu rõ ràng và được dọn tại hook đối ứng phù hợp. Với resource thuộc từng test, cặp `beforeTestMethod`/`afterTestMethod` có thể hợp lý; với resource chỉ bao quanh thân `@Test`, dùng `beforeTestExecution`/`afterTestExecution`.

Nếu code listener chỉ log thông tin, tránh để việc log ném exception khiến bài test vốn đúng bị đánh dấu FAIL. Nếu listener là bộ kiểm tra bắt buộc của framework, lỗi cần có thông báo rõ để phân biệt với lỗi nghiệp vụ.

## 10. TestExecutionListener, JUnit Extension và Application Event không giống nhau

Ba cơ chế sau có tên/ý tưởng gần nhau nhưng quyền hạn và nơi chạy khác nhau:

| Cơ chế | Thuộc hệ nào? | Phù hợp khi |
| --- | --- | --- |
| `org.springframework.test.context.TestExecutionListener` | Spring TestContext, do `TestContextManager` gọi | Cần truy cập TestContext, phối hợp dependency injection, transaction, SQL, context |
| `org.junit.jupiter.api.extension.*Callback` và `@ExtendWith` | JUnit Jupiter | Cần lifecycle extension chung cho test kể cả không dùng Spring |
| `@EventListener` nhận `BeforeTestMethodEvent`, `AfterTestMethodEvent`... | Bean trong `ApplicationContext` của Spring | Muốn dùng Spring DI để xử lý test execution events khi context đã được tải |

Ngoài ra còn có **`org.junit.platform.launcher.TestExecutionListener`**, là API của JUnit Platform Launcher cho việc theo dõi/ghi báo cáo test plan và kết quả cấp launcher. Nó **không phải** `org.springframework.test.context.TestExecutionListener` và không nhận cùng kiểu callback/context.

### EventPublishingTestExecutionListener

`EventPublishingTestExecutionListener` (đăng ký mặc định trong cấu hình phổ biến) có thể chuyển các lifecycle event thành Spring application events:

- `BeforeTestClassEvent`, `PrepareTestInstanceEvent`.
- `BeforeTestMethodEvent`, `BeforeTestExecutionEvent`.
- `AfterTestExecutionEvent`, `AfterTestMethodEvent`, `AfterTestClassEvent`.

Một bean có thể xử lý bằng `@EventListener` hoặc các composed annotation tương ứng. Tuy nhiên **event chỉ được phát khi `ApplicationContext` đã được tải**; listener phát event không tự ép Spring load context sớm. Vì vậy `BeforeTestClassEvent` có thể **không xuất hiện** cho lớp đầu tiên dùng một context chưa được nạp, và `AfterTestClassEvent` cũng có thể không được phát nếu context đã bị đóng/loại khỏi cache.

Nếu cần bảo đảm bắt một callback ở mọi lớp, custom `TestExecutionListener` trực tiếp thường rõ ràng hơn việc dựa vào sự kiện bean phụ thuộc trạng thái context.

## 11. Trường hợp thực tế: chọn callback cho đúng mục tiêu

| Yêu cầu | Giai đoạn nên cân nhắc | Vì sao? |
| --- | --- | --- |
| Log lúc bắt đầu/kết thúc một lớp test | `beforeTestClass` / `afterTestClass` | Bao quanh vòng đời cả lớp |
| Tiêm bean vào instance | `prepareTestInstance` | Default DI listener đã giải quyết |
| Chuẩn bị dữ liệu dùng cả `@BeforeEach` lẫn `@Test` | `beforeTestMethod` | Chạy trước setup JUnit |
| Đo chính xác thời gian thân `@Test` | `beforeTestExecution` / `afterTestExecution` | Bỏ qua phần lớn setup/teardown JUnit |
| Dọn tài nguyên sau cả `@AfterEach` | `afterTestMethod` | Tránh dọn khi teardown JUnit còn cần dữ liệu |
| Quản lý transaction | `TransactionalTestExecutionListener` mặc định | Không tự tái hiện transaction handling |
| Chạy SQL trước/sau test | `@Sql` với `SqlScriptsTestExecutionListener` | Dùng tính năng framework được hỗ trợ |
| Đánh dấu context bị thay đổi không thể tái dùng | `@DirtiesContext` | Để Spring cache/loader điều phối |
| Phát metric/tracing có bean Spring xử lý | Test execution events khi đủ điều kiện | Tận dụng dependency injection và hệ thống event |

Không có một hook “tốt nhất” cho mọi nhu cầu. Hãy xác định **tài nguyên tồn tại trong khoảng nào**, callback nào bao trọn khoảng đó, listener nào đang sở hữu tài nguyên, và callback của Spring chạy **trước/sau chính xác** lifecycle hook của JUnit nào.

## 12. Các lỗi thường gặp và cách khắc phục

1. **Đặt `@TestExecutionListeners` mà không tích hợp SpringExtension.** JUnit Jupiter chạy test nhưng Spring không điều phối listener. **Khắc phục:** dùng `@SpringJUnitConfig`, `@SpringBootTest` hoặc tích hợp SpringExtension thích hợp.
2. **Thêm listener rồi làm mất default listeners.** Do `REPLACE_DEFAULTS`, test không còn `@Autowired` hoặc cơ chế transaction/`@Sql` như mong đợi. **Khắc phục:** dùng `mergeMode = MERGE_WITH_DEFAULTS` nếu chỉ cần bổ sung.
3. **Nhầm `beforeTestMethod` với thời điểm ngay trước `@Test`.** Nó xảy ra trước `@BeforeEach`. **Khắc phục:** đo riêng thân test bằng `beforeTestExecution`.
4. **Nhầm `afterTestMethod` với thời điểm ngay sau `@Test`.** Nó xảy ra sau `@AfterEach`. **Khắc phục:** dùng `afterTestExecution` khi cần quan sát trước teardown.
5. **Giả định thứ tự “after” bằng “before”.** Với hai listener A/B, “after” sẽ đảo để duy trì wrapping. **Khắc phục:** xác định order và quản lý tài nguyên kiểu stack.
6. **Truy cập instance hoặc method quá sớm.** `beforeTestClass` chưa chắc có test instance/method. **Khắc phục:** chỉ dùng dữ liệu khả dụng ở giai đoạn đó.
7. **Giả định listener là Spring bean.** `@Autowired` trên custom listener không tự hoạt động như trên bean. **Khắc phục:** truy cập `ApplicationContext` qua `TestContext` khi cần, hoặc chọn event listener bean.
8. **Dùng mutable static state chung khi chạy song song.** Trace và fixture của nhiều lớp/test có thể trộn. **Khắc phục:** lưu dữ liệu theo test hoặc dùng reporter thread-safe.
9. **Xóa dữ liệu trước `@AfterEach` hoàn thành.** Teardown sau đó không tìm thấy fixture. **Khắc phục:** chọn `afterTestMethod` hoặc cơ chế dọn framework quản lý.
10. **Tự viết listener thay cho giao dịch/SQL/DI có sẵn.** Dễ sai order hoặc bỏ chức năng mặc định. **Khắc phục:** ưu tiên listener và annotation chuẩn.
11. **Đồng nhất kết quả từ `getTestException()` với mọi lỗi test.** Setup/teardown có thể gây lỗi riêng. **Khắc phục:** hiểu thời điểm và phạm vi của exception được TestContext lưu.
12. **Test tự động fail vì log/reporting phụ.** Listener ném exception vì một tác vụ ngoài không bắt buộc. **Khắc phục:** thiết kế xử lý lỗi theo mức độ quan trọng và log rõ nguyên nhân.

## 13. Quy trình thiết kế listener và checklist

Một quy trình ngắn trước khi viết custom listener:

1. **Mô tả điều cần làm:** đo thân test, bắt đầu transaction, tiêm bean, log lifecycle hay dọn tài nguyên?
2. **Kiểm tra tính năng sẵn có:** `@Transactional`, `@Sql`, `@DirtiesContext`, DI, event listener đã giải quyết chưa?
3. **Chọn phạm vi:** cấp class, test instance, trước setup, ngay trước test, ngay sau test hay sau teardown?
4. **Chọn nơi cài đặt:** JUnit Extension thuần, Spring `TestExecutionListener` hay bean nhận test execution event.
5. **Đăng ký an toàn:** nếu bổ sung listener riêng, khai báo `MERGE_WITH_DEFAULTS` và order khi cần.
6. **Chạy một test kiểm chứng:** quan sát đúng callback order theo một ví dụ đơn giản, rồi thêm test lỗi/parallel nếu cơ chế thực tế cần hỗ trợ.
7. **Xác nhận cleanup:** tài nguyên được đóng đúng chủ sở hữu, xử lý tình huống setup thất bại, không gây rò rỉ state khi chạy cả suite.

Checklist trước khi hoàn tất:

- [ ] Đã phân biệt `TestExecutionListener` của Spring với JUnit extension và launcher listener.
- [ ] Hiểu đủ bảy callback và chính xác vị trí so với `@BeforeAll` / `@BeforeEach` / `@Test` / `@AfterEach` / `@AfterAll`.
- [ ] `beforeTestExecution` và `afterTestExecution` được dùng khi cần đo phần thân test.
- [ ] `@SpringJUnitConfig` / `@SpringBootTest` hoặc SpringExtension đã được tích hợp.
- [ ] Không vô tình loại các listener mặc định khi bổ sung custom listener.
- [ ] Thứ tự trước/sau giữa các listener quan trọng được xác định, tránh phụ thuộc thứ tự ngẫu nhiên.
- [ ] Không giả định bean/instance/method đã có ở mọi thời điểm.
- [ ] State dùng chung được cô lập hoặc thread-safe khi test chạy song song.
- [ ] Đã cân nhắc transaction, `@Sql`, `@DirtiesContext` và cleanup do framework quản lý.
- [ ] Code test và output được giải thích theo **các sự kiện mà ví dụ thực sự tạo ra**.

**Ghi nhớ:** `TestExecutionListener` là cách Spring TestContext đưa logic vào các mốc trong vòng đời kiểm thử. Hai cặp dễ nhầm nhất là **`beforeTestMethod` / `afterTestMethod` bao quanh setup + test + teardown**, còn **`beforeTestExecution` / `afterTestExecution` chỉ bao quanh thân `@Test`**. Muốn thêm hành vi tùy biến mà vẫn giữ dependency injection và các tính năng mặc định của Spring, ưu tiên `@TestExecutionListeners(mergeMode = MERGE_WITH_DEFAULTS)`.

### Tài liệu tham khảo

- [Spring Framework 6.2 — TestContextManager API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/test/context/TestContextManager.html)
- [Spring Framework — TestExecutionListener configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html)
- [Spring Framework 6.2 — TestExecutionListener API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/test/context/TestExecutionListener.html)
- [Spring Framework — Test execution events](https://docs.spring.io/spring/reference/6.2/testing/testcontext-framework/test-execution-events.html)
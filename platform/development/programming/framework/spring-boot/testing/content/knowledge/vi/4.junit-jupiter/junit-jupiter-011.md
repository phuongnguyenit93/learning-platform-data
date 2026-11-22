# Extension model, MockitoExtension và SpringExtension trong JUnit Jupiter

## 1. Vì sao JUnit Jupiter cần extension?

Một phương thức gắn `@Test` thường chỉ cần kiểm tra đầu ra. Tuy nhiên, test thực tế còn cần các việc xung quanh phương thức đó: tạo mock, chuẩn bị dữ liệu, tiêm dependency, nạp Spring `ApplicationContext`, đo thời gian, kiểm tra điều kiện chạy hoặc dọn tài nguyên sau khi test kết thúc.

JUnit Jupiter giải quyết các nhu cầu này bằng **Extension Model**. Một extension là thành phần được JUnit đăng ký vào vòng đời thực thi, nhận `ExtensionContext` và triển khai những *callback interface* tương ứng. Nhờ vậy, logic hạ tầng test có thể được tái sử dụng, còn nội dung `@Test` tập trung vào hành vi cần chứng minh.

Hai extension rất thường gặp trong ứng dụng Spring Boot:

- **`MockitoExtension`** của Mockito: khởi tạo và quản lý Mockito mock, hỗ trợ `@Mock`/`@InjectMocks` và tham số `@Mock`, kiểm tra stubbing khi kết thúc test.
- **`SpringExtension`** của Spring Test: kết nối JUnit Jupiter với Spring TestContext Framework để khởi tạo hoặc tái sử dụng `ApplicationContext`, inject Spring bean, áp dụng các listener và cơ chế kiểm thử của Spring.

JUnit là **bộ máy chạy test**; Mockito tạo **test double** cho collaborator; Spring cung cấp **container và wiring thật** theo cấu hình test. Extension làm cho những khả năng đó tham gia đúng thời điểm trong vòng đời JUnit.

| Câu hỏi | JUnit Jupiter Extension Model | MockitoExtension | SpringExtension |
| --- | --- | --- | --- |
| Thuộc thư viện nào? | `org.junit.jupiter.api.extension` | `org.mockito.junit.jupiter` | `org.springframework.test.context.junit.jupiter` |
| Trách nhiệm | Chuẩn API cho callback, tham số, điều kiện, trạng thái | Khởi tạo/kiểm soát Mockito session và mock | Tích hợp JUnit với Spring TestContext |
| Có tạo Spring context không? | Không | Không | Có, nếu cấu hình Spring Test yêu cầu |
| Có tự tạo Mockito mock không? | Không | Có với `@Mock` tương ứng | Không chỉ vì dùng SpringExtension |
| Có thể phối hợp? | Là nền tảng chung | Dùng một mình cho unit test; cân nhắc khi kết hợp Spring | Dùng với Spring Test, Spring Boot Test, test slices |
| Kiểm thử thứ gì? | Phụ thuộc extension được viết | Logic Java có collaborator bị cô lập | Bean wiring, cấu hình, Spring integration |

**Mục tiêu học tập:** hiểu contract của extension, cách đăng ký, thứ tự gọi callback, tham số được resolve như thế nào; viết một extension nhỏ; dùng MockitoExtension và SpringExtension đúng ngữ cảnh; phân biệt `@Mock` với Spring mock bean và tránh xung đột khi phối hợp nhiều extension.

## 2. JUnit 4 so với JUnit Jupiter

JUnit 4 có các cơ chế như `@RunWith`, `TestRule` và `MethodRule`. Một test class chỉ có một runner duy nhất, nên kết hợp các runner thường khó. JUnit Jupiter (phần API/test engine của JUnit 5) đưa nhiều nhu cầu vào một mô hình **`Extension`** nhất quán và cho phép đăng ký nhiều extension theo phạm vi.

```text
JUnit Platform
└── Jupiter TestEngine
    └── Test class / test method
        ├── Extension A: callback quanh test
        ├── Extension B: cấp tham số
        └── Extension C: điều khiển Spring TestContext
            └── @Test + assertions
```

`Extension` là **marker interface**: bản thân nó không định nghĩa phương thức bắt buộc. Extension phải triển khai một hoặc nhiều interface cụ thể như `BeforeEachCallback`, `ParameterResolver` hoặc `TestExecutionExceptionHandler` để có hành vi.

Không được nhầm:

- `@BeforeEach` là **phương thức của người viết test**.
- `BeforeEachCallback` là **hook của extension**, được JUnit gọi **trước** các phương thức `@BeforeEach`.
- `@ExtendWith(...)` là cách **đăng ký** extension, không phải phương thức test.
- `@Autowired` là chỉ thị của Spring; không được JUnit Jupiter thuần tự xử lý nếu SpringExtension/TestContext không tham gia.
- `@Mock` chỉ là annotation của Mockito; nếu không có cơ chế Mockito khởi tạo tương ứng, field có thể vẫn là `null`.

## 3. Các điểm mở rộng cốt lõi

| Extension API | Khi nào được sử dụng | Ví dụ |
| --- | --- | --- |
| `BeforeAllCallback` / `AfterAllCallback` | Trước/sau tập test trong một test container | Chuẩn bị và dọn tài nguyên dùng chung |
| `BeforeEachCallback` / `AfterEachCallback` | Bao quanh thiết lập và dọn dẹp của từng test | Khởi tạo session, ghi log, quản lý context |
| `BeforeTestExecutionCallback` / `AfterTestExecutionCallback` | Ngay trước/sau thân `@Test`, nằm trong vòng `@BeforeEach`/`@AfterEach` | Đo thời gian riêng thân test |
| `TestInstancePostProcessor` | Sau khi JUnit tạo test instance | Tiêm trường hoặc thiết lập đối tượng test |
| `ParameterResolver` | Cung cấp đối số cho constructor/method được JUnit gọi | Inject `Clock`, `TestInfo`, Mockito mock, Spring bean |
| `ExecutionCondition` | Quyết định có enable test/container hay không | Bỏ qua test theo môi trường |
| `TestExecutionExceptionHandler` | Xử lý exception phát sinh từ test method | Ghi ngữ cảnh lỗi; tùy thiết kế có thể ném lại exception |
| `TestWatcher` | Quan sát kết quả test đã xác định | Ghi nhận test PASS/FAIL/ABORTED/DISABLED |
| `InvocationInterceptor` | Chặn hoặc bọc các lời gọi test/lifecycle được hỗ trợ | Đo hoặc kiểm soát việc invocation |
| `ExtensionContext.Store` | Lưu trạng thái gắn với test/container một cách có phạm vi | Giữ thời điểm bắt đầu, resource handle |

Các hook này có **khác biệt về thời điểm**. Ví dụ, nếu chỉ muốn đo thời gian của phương thức `@Test`, dùng `BeforeTestExecutionCallback` và `AfterTestExecutionCallback` sẽ phù hợp hơn `BeforeEachCallback` và `AfterEachCallback`, vì cặp thứ hai còn bao quanh bước setup của test.

### Thứ tự một test đơn giản

Với một extension cài đầy đủ bốn callback quanh một phương thức test:

```text
BeforeEachCallback       [extension]
    @BeforeEach          [test class]
BeforeTestExecutionCallback [extension]
        @Test            [test class]
AfterTestExecutionCallback  [extension]
    @AfterEach           [test class]
AfterEachCallback        [extension]
```

`BeforeAllCallback` diễn ra trước `@BeforeAll` của container; `AfterAllCallback` diễn ra sau `@AfterAll`. Khi có nhiều extension, JUnit bảo đảm **wrapping behavior** cho các callback “before/after” tương ứng: extension đăng ký trước chạy callback “before” trước và callback “after” sau extension được đăng ký sau.

Đây là **mô hình thứ tự thông thường** để hiểu API, không phải cam kết rằng mọi callback vẫn được gọi nếu test bị vô hiệu hóa hoặc một bước khởi tạo trước đó đã lỗi. Không dùng log in ra hoặc thứ tự thực thi test khác làm hợp đồng nghiệp vụ.

## 4. Đăng ký extension: ba cách thường gặp

### 4.1. `@ExtendWith` — khai báo rõ ràng

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CalculatorServiceTest {
    @Test
    void calculationWorks() {
        // Test body.
    }
}
```

`@ExtendWith` có thể dùng ở cấp class hoặc method để thay đổi phạm vi đăng ký; có thể khai báo nhiều extension, kể cả dưới dạng mảng:

```java
@ExtendWith({FirstExtension.class, SecondExtension.class})
class MultipleExtensionsTest {
    // Giả sử FirstExtension và SecondExtension đã được định nghĩa.
}
```

Đây là đoạn **minh họa cú pháp**, không phải class độc lập có thể chạy khi thiếu các extension được nhắc đến. Khi đăng ký declarative, thứ tự khai báo có ý nghĩa đối với các callback; không nên đổi thứ tự tùy tiện nếu extension có phụ thuộc lifecycle.

Cũng có thể tạo **composed annotation** chứa `@ExtendWith` để tái sử dụng cùng cấu hình ở nhiều test. `@SpringJUnitConfig` là ví dụ thực tế của cách này.

### 4.2. `@RegisterExtension` — khởi tạo bằng code

```java
import org.junit.jupiter.api.extension.RegisterExtension;

class WithConfiguredExtensionTest {
    @RegisterExtension
    static final SomeConfiguredExtension extension =
            new SomeConfiguredExtension("test-env");
}
```

Đoạn này chỉ minh họa hình thức đăng ký; `SomeConfiguredExtension` là lớp giả định phải được triển khai trong dự án. Cách này hữu ích khi extension cần constructor argument hoặc builder. Extension dạng `static` có thể tham gia callback cấp lớp. Với field dạng instance, một số callback cấp lớp không thể dùng theo cách tương tự vì instance chưa được tạo khi `@BeforeAll` chạy. Khi kết hợp nhiều extension field, đọc quy tắc `@Order` để tránh phụ thuộc vào thứ tự mặc định không hiển nhiên.

### 4.3. Tự động phát hiện

JUnit Jupiter còn hỗ trợ phát hiện extension qua `ServiceLoader` khi bật tính năng auto-detection phù hợp. Đây không phải cơ chế mặc định nên ưu tiên `@ExtendWith`/`@RegisterExtension` trong bài test thông thường để nguồn đăng ký dễ nhìn thấy và dễ debug.

**Phạm vi đăng ký:** extension ở class thường áp dụng cho các test trong class; extension ở method chỉ áp dụng cho invocation thuộc method đó. Test lồng nhau, annotation kế thừa và test interface có quy tắc kế thừa/phạm vi riêng theo JUnit Jupiter. Khi viết một extension có trạng thái, dùng `ExtensionContext` và phạm vi tương ứng thay vì một biến global dùng chung.

## 5. Thiết lập một dự án mẫu Java 17+ để thực hành

Ta tạo một Gradle project nhỏ, không cần server hay database. Nó dùng bộ dependency do Spring Boot 3.3.x quản lý **chỉ cho test**, đủ chạy ví dụ JUnit Jupiter, MockitoExtension và SpringExtension ở các mục sau.

`settings.gradle`:

```groovy
rootProject.name = 'jupiter-extension-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Điều kiện: JDK 17 trở lên và Gradle tương thích (có thể dùng Gradle Wrapper của repository). Các lớp test ở dưới đặt vào `src/test/java/com/example/testing/`, package `com.example.testing`. Mỗi ví dụ là một lớp độc lập với các import của riêng nó.

Trong **ứng dụng Spring Boot 3.3.x đang có** BOM hoặc plugin Boot, dependency thường chỉ cần:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Nếu dùng BOM của project Boot hiện tại, tránh tự ép một phiên bản JUnit/Spring Framework mới không tương thích. Bản ví dụ này chọn rõ Spring Boot 3.3.5 để nói về các annotation thuộc nhánh Boot 3.3, không khẳng định đó là phiên bản mới nhất.

Chạy tất cả test:

```bash
./gradlew test
```

Nếu đang ở Windows, dùng `gradlew.bat test`. Nếu project chưa có Gradle Wrapper, dùng `gradle test` với Gradle đã cài. Chạy một class riêng:

```bash
./gradlew test --tests 'com.example.testing.MockitoOrderServiceTest'
```

`--tests` lọc **test cần chạy**, còn extension quyết định hạ tầng/lifecycle bên trong test được chọn.

## 6. Tự viết extension để thấy callback thật sự hoạt động

Ví dụ sau ghi lại thứ tự callback và assert ngay ở cuối chu kỳ. Nó dùng **một test method**, giúp kết quả kiểm tra xác định, không phụ thuộc vào thời gian chạy thực tế.

`src/test/java/com/example/testing/ExtensionLifecycleTest.java`:

```java
package com.example.testing;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.AfterEachCallback;
import org.junit.jupiter.api.extension.AfterTestExecutionCallback;
import org.junit.jupiter.api.extension.BeforeEachCallback;
import org.junit.jupiter.api.extension.BeforeTestExecutionCallback;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.extension.ExtensionContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(ExtensionLifecycleTest.TraceExtension.class)
class ExtensionLifecycleTest {
    private final List<String> trace = new ArrayList<>();

    static final class TraceExtension implements
            BeforeEachCallback,
            BeforeTestExecutionCallback,
            AfterTestExecutionCallback,
            AfterEachCallback {

        private static ExtensionLifecycleTest test(ExtensionContext ctx) {
            return (ExtensionLifecycleTest) ctx.getRequiredTestInstance();
        }

        @Override
        public void beforeEach(ExtensionContext ctx) {
            test(ctx).trace.add("extension.beforeEach");
        }

        @Override
        public void beforeTestExecution(ExtensionContext ctx) {
            test(ctx).trace.add("extension.beforeTestExecution");
        }

        @Override
        public void afterTestExecution(ExtensionContext ctx) {
            test(ctx).trace.add("extension.afterTestExecution");
        }

        @Override
        public void afterEach(ExtensionContext ctx) {
            ExtensionLifecycleTest instance = test(ctx);
            instance.trace.add("extension.afterEach");

            assertEquals(List.of(
                    "extension.beforeEach",
                    "test.@BeforeEach",
                    "extension.beforeTestExecution",
                    "test.@Test",
                    "extension.afterTestExecution",
                    "test.@AfterEach",
                    "extension.afterEach"
            ), instance.trace);
        }
    }

    @BeforeEach
    void setUp() {
        trace.add("test.@BeforeEach");
    }

    @Test
    void verifiesCallbackOrder() {
        trace.add("test.@Test");
    }

    @AfterEach
    void tearDown() {
        trace.add("test.@AfterEach");
    }
}
```

Chạy:

```bash
./gradlew test --tests 'com.example.testing.ExtensionLifecycleTest'
```

**Kỳ vọng:** 1 test PASS; assertion trong `TraceExtension.afterEach` xác minh 7 sự kiện theo đúng thứ tự. Nếu tự đổi thứ tự dự kiến, bài test FAIL; nó không cần in stdout. Đây là ví dụ về **callback lifecycle**, không tạo Spring `ApplicationContext` và không dùng Mockito.

Điều cần rút ra: callback và phương thức `@BeforeEach`/`@AfterEach` là hai lớp hành vi khác nhau. Extension nhận `ExtensionContext`; trong trường hợp có test instance, `getRequiredTestInstance()` trả về instance hiện tại. Đừng dùng một `static List` chia sẻ giữa các test vì parallel execution có thể khiến trạng thái bị trộn.

### Lưu trạng thái qua `ExtensionContext.Store`

Extension đo thời gian hoặc mở resource có thể cần giữ dữ liệu từ callback “before” sang “after”. Thay vì static mutable map, dùng store có namespace:

`src/test/java/com/example/testing/TimingExtension.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.extension.AfterTestExecutionCallback;
import org.junit.jupiter.api.extension.BeforeTestExecutionCallback;
import org.junit.jupiter.api.extension.ExtensionContext;

public final class TimingExtension
        implements BeforeTestExecutionCallback, AfterTestExecutionCallback {

    private static final ExtensionContext.Namespace NAMESPACE =
            ExtensionContext.Namespace.create(TimingExtension.class);

    @Override
    public void beforeTestExecution(ExtensionContext context) {
        context.getStore(NAMESPACE).put("startNanos", System.nanoTime());
    }

    @Override
    public void afterTestExecution(ExtensionContext context) {
        Long start = context.getStore(NAMESPACE)
                .remove("startNanos", Long.class);
        if (start != null) {
            long elapsed = System.nanoTime() - start;
            System.out.println("Elapsed nanos: " + elapsed);
        }
    }
}
```

Đăng ký:

```java
@ExtendWith(TimingExtension.class)
class AnyTimedTest {
    @Test
    void sample() {
        assertEquals(4, 2 + 2);
    }
}
```

Đoạn `AnyTimedTest` là ví dụ **rút gọn**: khi đặt thành file độc lập cần các import JUnit `@ExtendWith`, `@Test` và `assertEquals`; `TimingExtension` là file Java hoàn chỉnh như trên. Giá trị sau `Elapsed nanos:` **không cố định** và không phải điều kiện PASS/FAIL; chỉ thời gian thực thi thay đổi theo máy và lần chạy. Store được truy cập qua cùng context/namespace của invocation, tránh biến dùng chung toàn JVM.

## 7. `ParameterResolver`: JUnit có thể cấp tham số cho test

JUnit Jupiter cho phép khai báo tham số cho test method, lifecycle method hoặc constructor nếu có một `ParameterResolver` hỗ trợ. JUnit có một số resolver tích hợp, như cho `TestInfo`. Extension tự viết cũng có thể cung cấp `Clock`, một cấu hình test hoặc các object khác.

Hai phương thức chính:

- `supportsParameter(ParameterContext, ExtensionContext)`: trả `true` nếu extension nhận trách nhiệm cho tham số đó.
- `resolveParameter(ParameterContext, ExtensionContext)`: trả đối tượng tương ứng khi thực thi.

Ví dụ cung cấp đồng hồ cố định để test không phụ thuộc ngày hiện tại.

`src/test/java/com/example/testing/FixedClockTest.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.extension.ExtensionContext;
import org.junit.jupiter.api.extension.ParameterContext;
import org.junit.jupiter.api.extension.ParameterResolver;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(FixedClockTest.FixedClockExtension.class)
class FixedClockTest {
    static final class FixedClockExtension implements ParameterResolver {
        @Override
        public boolean supportsParameter(
                ParameterContext parameter,
                ExtensionContext context) {
            return parameter.getParameter().getType() == Clock.class;
        }

        @Override
        public Object resolveParameter(
                ParameterContext parameter,
                ExtensionContext context) {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }

    @Test
    void receivesFixedClock(Clock clock) {
        assertEquals("2024-01-01T00:00:00Z",
                clock.instant().toString());
    }
}
```

Chạy:

```bash
./gradlew test --tests 'com.example.testing.FixedClockTest'
```

**Kỳ vọng:** 1 test PASS; JUnit gọi resolver để truyền `Clock` vào `receivesFixedClock`. Không cần `new Clock(...)` trong test method hoặc Spring bean. Lý do chính để dùng injection dạng này là tạo fixture lặp lại một cách nhất quán ở nhiều test.

**Cạm bẫy:** nếu có hai `ParameterResolver` cùng báo hỗ trợ một tham số, JUnit có thể ném `ParameterResolutionException` vì nhiều resolver cạnh tranh. Một resolver tùy biến nên giới hạn điều kiện `supportsParameter` bằng type và/hoặc annotation cụ thể, thay vì trả `true` cho mọi tham số.

## 8. MockitoExtension: khởi tạo mock và kiểm tra việc sử dụng

### 8.1. MockitoExtension tham gia những gì?

`MockitoExtension` nằm trong artifact `mockito-junit-jupiter` (có sẵn trong `spring-boot-starter-test` của Boot 3.3.x). Nó thường:

1. Khởi tạo `@Mock`, `@Spy`, `@Captor` và xử lý `@InjectMocks` trên test instance theo quy tắc Mockito.
2. Quản lý **Mockito session** theo vòng đời JUnit.
3. Cho phép khai báo mock ngay trên parameter của test/lifecycle method qua `@Mock`.
4. Áp dụng **strict stubbing** để phát hiện stub thừa hoặc cấu hình đáng ngờ; có thể điều chỉnh bằng `@MockitoSettings`.

Nó **không** tạo `ApplicationContext`, không chạy repository thật, không tự cung cấp dependency cho Spring bean. Từ “injection” trong `@InjectMocks` là Mockito tìm cách dựng/gắn collaborator vào class Java đang test; khác với Spring Dependency Injection.

### 8.2. Unit test có thể chạy: `@Mock` + `@InjectMocks`

`src/test/java/com/example/testing/MockitoOrderServiceTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MockitoOrderServiceTest {
    interface TaxClient {
        int taxPercent();
    }

    static final class OrderService {
        private final TaxClient taxClient;

        OrderService(TaxClient taxClient) {
            this.taxClient = taxClient;
        }

        int totalWithTax(int netPrice) {
            if (netPrice < 0) {
                throw new IllegalArgumentException("negative price");
            }
            return netPrice
                    + netPrice * taxClient.taxPercent() / 100;
        }
    }

    @Mock
    TaxClient taxClient;

    @InjectMocks
    OrderService service;

    @Test
    void addsTaxToNetPrice() {
        when(taxClient.taxPercent()).thenReturn(10);

        assertEquals(110, service.totalWithTax(100));
        verify(taxClient).taxPercent();
    }

    @Test
    void rejectsNegativePriceWithoutCallingCollaborator() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.totalWithTax(-1)
        );
        verifyNoInteractions(taxClient);
    }

    @Test
    void canInjectMethodScopedMock(@Mock TaxClient temporaryClient) {
        when(temporaryClient.taxPercent()).thenReturn(5);

        OrderService temporaryService = new OrderService(temporaryClient);

        assertEquals(105, temporaryService.totalWithTax(100));
        verify(temporaryClient).taxPercent();
    }
}
```

Chạy:

```bash
./gradlew test --tests 'com.example.testing.MockitoOrderServiceTest'
```

**Kỳ vọng: 3 test PASS.** Test thứ nhất xác minh `100 + 10% = 110`; test thứ hai xác minh exception xảy ra trước khi collaborator được gọi; test thứ ba nhận một mock chỉ qua tham số phương thức. Không cần database, Spring context hoặc HTTP server.

Các bước diễn ra:

- Trước test, MockitoExtension tạo `TaxClient` mock cho field `@Mock` và dựng `OrderService` với mock đó thông qua `@InjectMocks`.
- Trong `addsTaxToNetPrice`, `when(...).thenReturn(10)` quy định phản hồi, còn `verify` kiểm tra interaction thực sự diễn ra.
- Đến cuối test, MockitoExtension kết thúc session và thực hiện các kiểm tra strictness. Một stub không dùng có thể bị coi là lỗi thay vì bị bỏ qua một cách im lặng.

Với MockitoExtension, có thể viết test không dùng `@InjectMocks` và tự tạo `new OrderService(taxClient)` trong `@BeforeEach` hoặc trong test. Cách này thường làm dependency rõ hơn và không phụ thuộc chiến lược injection của Mockito.

### 8.3. Strict stubbing: vì sao test có thể FAIL dù assertion PASS?

MockitoExtension mặc định dùng hành vi strictness mạnh trong các bản Mockito hiện đại. Ví dụ:

```java
@Test
void unusedStubExample() {
    when(taxClient.taxPercent()).thenReturn(10);
    assertEquals(2, 1 + 1);
}
```

Đây là **đoạn phản ví dụ**: `taxClient.taxPercent()` chưa từng được gọi nên một stub như vậy có thể bị Mockito đánh dấu là **unnecessary stubbing** khi session kết thúc. Không sao chép test này vào suite với kỳ vọng PASS.

Cách sửa đúng thường là **xóa stub không cần thiết**. Chỉ khi có lý do cụ thể mới dùng `lenient()` cho stub hoặc cấu hình strictness ở lớp bằng:

```java
@MockitoSettings(strictness = Strictness.LENIENT)
```

Đoạn cấu hình này cần import `org.mockito.junit.jupiter.MockitoSettings` và `org.mockito.quality.Strictness`, áp dụng vào class đang dùng MockitoExtension. Tránh dùng lenient toàn bộ suite chỉ để che test thiết kế chưa rõ.

### 8.4. `@Mock` không phải `@MockBean`

`@Mock` tạo Mockito object trong phạm vi test thông thường. Trong một Spring `ApplicationContext` đã dựng, field mock của test **không mặc nhiên thay thế bean** mà controller/service trong context đang sử dụng.

Ở Spring Boot **3.3.x**, annotation `org.springframework.boot.test.mock.mockito.MockBean` tạo hoặc thay thế một bean trong test context; Spring Boot còn tự reset các mock bean sau test theo cấu hình. Trong Spring Framework 6.2 / Spring Boot 3.4 trở lên có API `@MockitoBean` mới. Khi làm bài này với Boot 3.3.x, dùng **`@MockBean` của Boot**, không chép nhầm annotation mới nếu classpath chưa hỗ trợ.

Không kết luận `@MockBean` chỉ là “MockitoExtension ở dạng Spring” — đây là cơ chế customizer/test listener tích hợp với bean registry của Spring Boot Test.

## 9. SpringExtension: JUnit Jupiter nối với Spring TestContext

### 9.1. Vai trò của SpringExtension

`SpringExtension` nằm trong `spring-test`, đóng vai trò adapter giữa JUnit Jupiter và **Spring TestContext Framework**.

Những việc chính:

- Gắn lifecycle của test với `TestContextManager` và các `TestExecutionListener` của Spring.
- Nạp `ApplicationContext` theo `@ContextConfiguration` hoặc cấu hình phù hợp; tận dụng **context cache** giữa các test có cấu hình tương đương.
- Tiêm bean vào field, constructor hoặc phương thức test/lifecycle theo hợp đồng Spring Test và cấu hình autowiring.
- Hỗ trợ test transaction, SQL fixtures, profiles, properties và các khả năng TestContext khác khi được khai báo.
- Phối hợp với cấu hình test của Spring Boot khi dùng `@SpringBootTest` hoặc các test slice tương ứng.

SpringExtension không phải bản sao của MockitoExtension: SpringExtension thực sự dùng Spring container để đáp ứng nhu cầu DI và quản lý context. Không nên tải Spring context chỉ để kiểm tra một hàm Java thuần.

### 9.2. `@SpringJUnitConfig` là composed annotation

Hai cách sau tương đương về ý tưởng đăng ký extension và cấu hình context:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class FirstSpringTest {
}
```

```java
@SpringJUnitConfig(TestConfig.class)
class SecondSpringTest {
}
```

Các đoạn trên là **cú pháp minh họa**, giả định `TestConfig` tồn tại và đã import annotation tương ứng. `@SpringJUnitConfig` kết hợp `@ExtendWith(SpringExtension.class)` với `@ContextConfiguration`; vì vậy thêm `@ExtendWith(SpringExtension.class)` một lần nữa thường không có lợi.

Trong Spring Boot 3.3.x, `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` và các annotation test slice của Boot đã tích hợp SpringExtension. Người viết test không cần khai báo `@ExtendWith(SpringExtension.class)` lần nữa.

### 9.3. Test Spring context nhỏ và độc lập

`src/test/java/com/example/testing/SpringClockWiringTest.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(SpringClockWiringTest.Config.class)
class SpringClockWiringTest {
    @Configuration
    static class Config {
        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }

        @Bean
        DateService dateService(Clock clock) {
            return new DateService(clock);
        }
    }

    static final class DateService {
        private final Clock clock;

        DateService(Clock clock) {
            this.clock = clock;
        }

        String today() {
            return LocalDate.now(clock).toString();
        }
    }

    @Autowired
    DateService dateService;

    @Test
    void injectsBeanDefinedInSpringContext() {
        assertEquals("2024-01-01", dateService.today());
    }
}
```

Chạy:

```bash
./gradlew test --tests 'com.example.testing.SpringClockWiringTest'
```

**Kỳ vọng:** 1 test PASS. `@SpringJUnitConfig` khiến SpringExtension nạp context từ `Config`, Spring khởi tạo bean `Clock` và `DateService`, rồi inject `DateService` vào field của test. Đây là phép kiểm tra **wiring Spring thật** trong một context nhỏ; nó vẫn không khởi động toàn bộ auto-configuration của Boot hay HTTP server.

Điểm dễ nhầm: method `@Bean DateService dateService(Clock clock)` nhận `Clock` từ Spring container theo quy tắc DI của `@Bean`; còn method `@Test void receivesFixedClock(Clock clock)` ở phần trước nhận `Clock` từ **JUnit ParameterResolver tự viết**. Cú pháp tham số trông giống nhau, nhưng bộ máy chịu trách nhiệm khác nhau.

## 10. Dùng SpringExtension trong ứng dụng Spring Boot

### 10.1. `@SpringBootTest` tự kéo SpringExtension vào test

Trong một ứng dụng đã có `@SpringBootApplication`, test dưới đây kiểm tra rằng context của Boot có thể dựng được:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextTest {
    @Test
    void contextLoads() {
        // JUnit PASS nếu application context nạp thành công.
    }
}
```

Đây là **test tích hợp vào ứng dụng Boot có sẵn**, không phải test chạy được trong Gradle Java project tối thiểu ở mục 5 nếu không có cấu hình ứng dụng. Không cần thêm `@ExtendWith(SpringExtension.class)` vì `@SpringBootTest` đã meta-annotated tương ứng.

Mặc định `@SpringBootTest` không mở HTTP port thật; web environment kiểu `MOCK` thích hợp khi cần mô phỏng môi trường web trong test. Nếu cần server thật, dùng `webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT` và test qua HTTP client phù hợp.

### 10.2. Mock collaborator trong Spring context với Boot 3.3.x

Giả sử ứng dụng thật có bean `OrderService` và bean `PaymentGateway`, với hợp đồng `OrderService.placeOrder(String orderId)` và `PaymentGateway.charge(String orderId)`. Để kiểm tra logic của service **đang lấy từ Spring context** nhưng tránh gọi cổng thanh toán thật, Boot 3.3.x dùng:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

@SpringBootTest
class OrderServiceSpringTest {
    @Autowired
    OrderService orderService;

    @MockBean
    PaymentGateway paymentGateway;

    @Test
    void placesOrderWithMockedPaymentGateway() {
        when(paymentGateway.charge("order-1")).thenReturn(true);

        assertTrue(orderService.placeOrder("order-1"));
    }
}
```

**Đây là ví dụ gắn vào ứng dụng có sẵn**: cần định nghĩa thật của `OrderService`, `PaymentGateway`, Spring configuration và hợp đồng method đã mô tả. Nó không phải đoạn file độc lập. `@MockBean` thay/đăng ký mock trong Spring context để `OrderService` được autowire nhìn thấy mock, còn SpringExtension quản lý TestContext. Không có lý do mặc định để thêm MockitoExtension vào lớp test này.

Sự khác biệt với Mockito unit test ở mục 8 rất quan trọng: unit test dùng Mockito tạo `OrderService` trực tiếp, còn Boot test hỏi Spring lấy `OrderService` nào, inject phụ thuộc nào và cấu hình context ra sao. Cách thứ hai nặng hơn nhưng bảo vệ những ranh giới khác.

## 11. Khi nào có nên kết hợp MockitoExtension và SpringExtension?

JUnit cho phép đăng ký nhiều extension. Tuy vậy, **được phép đăng ký** không có nghĩa là **cần đăng ký cả hai** cho mọi test.

| Nhu cầu | Cách nên bắt đầu | Lý do |
| --- | --- | --- |
| Kiểm tra business logic Java, collaborator giả | `@ExtendWith(MockitoExtension.class)`, `@Mock` | Nhẹ; không tạo Spring context |
| Kiểm tra bean wiring trong một config nhỏ | `@SpringJUnitConfig` | SpringExtension + TestContext đủ |
| Kiểm tra Boot wiring hoặc luồng nhiều bean | `@SpringBootTest` | SpringExtension được đăng ký sẵn |
| Kiểm tra MVC slice, cần mock service dependency | `@WebMvcTest` + `@MockBean` (Boot 3.3.x) | Tạo MVC context với bean mock do Boot quản lý |
| Test nhận mock tham số nhưng không cần Spring | MockitoExtension + `@Mock` parameter | Mockito xử lý tham số |
| Test muốn Spring inject bean vào tham số | SpringExtension + `@Autowired` parameter hoặc cấu hình constructor | Resolver của Spring lấy từ ApplicationContext |

Có tình huống cần cả hai: chẳng hạn SpringExtension quản lý context còn MockitoExtension cung cấp một mock **chỉ dùng trong test method**, không được đăng ký thành Spring bean. Khi đó phải chủ động kiểm tra các resolver, lifecycle và trách nhiệm. Đây là ngoại lệ có mục đích; cách bắt đầu thông thường vẫn là dùng extension tối thiểu cần thiết.

### Xung đột ParameterResolver

Nếu một tham số constructor/method đồng thời được cả hai extension nhận là trách nhiệm của mình, JUnit có thể báo lỗi kiểu:

```text
org.junit.jupiter.api.extension.ParameterResolutionException:
Discovered multiple competing ParameterResolvers for parameter ...
```

Ví dụ một constructor dùng chế độ **tự động autowire tất cả tham số từ Spring** đồng thời dùng MockitoExtension để resolve tham số `@Mock` có thể gây chồng lấn. Cách xử lý là quy định rõ “tham số này do ai cung cấp”: Spring bean nhận từ context, Mockito mock dùng `@Mock` trong unit test hoặc bean mock được khai báo qua cơ chế của Boot/Spring Test tương thích.

**Không sửa bằng cách chỉ đổi thứ tự `@ExtendWith`** khi hai resolver cùng nhận một tham số; điều đó không loại bỏ tính nhập nhằng về ownership. Nếu không cần mock tham số thì bỏ MockitoExtension; nếu cần mock một Spring bean thì dùng cơ chế thay bean trong Spring test context.

### Phân biệt các annotation dễ nhầm

| Annotation | Ai xử lý? | Tác dụng |
| --- | --- | --- |
| `@Test` | JUnit Jupiter | Định nghĩa test method |
| `@ExtendWith(MockitoExtension.class)` | JUnit Jupiter + MockitoExtension | Đăng ký Mockito session, khởi tạo mock |
| `@Mock` | MockitoExtension hoặc cơ chế khởi tạo Mockito khác | Tạo Mockito mock cho test |
| `@InjectMocks` | Mockito | Thử dựng/tiêm mock vào class đang test |
| `@ExtendWith(SpringExtension.class)` | JUnit Jupiter + SpringExtension | Tích hợp Spring TestContext |
| `@SpringJUnitConfig` | Spring Test + JUnit | Kết hợp SpringExtension và context config |
| `@Autowired` | Spring Test/Spring container | Tiêm Spring bean phù hợp |
| `@SpringBootTest` | Spring Boot Test + SpringExtension | Dựng Boot application context để test |
| `@MockBean` (Boot 3.3.x) | Spring Boot Test | Tạo/thay bean trong context bằng Mockito mock |
| `@MockitoBean` (Spring Framework 6.2+) | Spring Test | Bean override API ở phiên bản Framework mới hơn |

## 12. Những bẫy về lifecycle và trạng thái

### 12.1. Tưởng `MockitoExtension` sẽ tự khởi tạo Spring bean

`@Mock` và `@InjectMocks` có thể khiến unit test PASS trong khi Spring configuration sai. Điều đó bình thường: unit test kiểm tra **logic** của class được dựng trong test, không kiểm tra ApplicationContext. Bổ sung một Spring Test khi cần xác minh wiring thật.

### 12.2. Dùng `@Autowired` trong JUnit Jupiter thuần

```java
class WrongSpringTest {
    @Autowired
    SomeService service;

    @Test
    void testIt() {
        service.run();
    }
}
```

Đây là **phản ví dụ** (và `SomeService` chưa được định nghĩa): JUnit Jupiter thuần không nhận trách nhiệm inject field Spring chỉ vì có annotation. Nếu thiếu SpringExtension/TestContext, field sẽ có thể là `null`. Khi đã dùng SpringExtension, cũng phải cung cấp cấu hình chứa bean phù hợp.

### 12.3. Quên đăng ký MockitoExtension

```java
class MissingMockitoSetupTest {
    @Mock
    Collaborator collaborator;
}
```

Đây cũng là **phản ví dụ**. Annotation đơn lẻ không bắt JUnit khởi tạo mock. Có thể dùng MockitoExtension, hoặc tự quản lý `MockitoAnnotations.openMocks(this)` và đóng resource đúng lúc; trong đa số test Jupiter, MockitoExtension gọn và ít lỗi hơn.

### 12.4. Chia sẻ state giữa các test

JUnit Jupiter mặc định tạo test instance mới cho mỗi test method, nhưng dự án có thể cấu hình `@TestInstance(PER_CLASS)`. Spring TestContext có thể dùng chung context cache giữa các class. Không suy từ “test instance mới” rằng **mọi Spring singleton bean** hoặc dữ liệu DB đều được reset.

Đừng giữ state của extension bằng static mutable field không đồng bộ nếu test được chạy song song. Dùng `ExtensionContext.Store` có namespace, phạm vi đúng và tài nguyên có cleanup. Nếu store chứa resource dài hạn, cần chú ý cơ chế đóng tài nguyên và compatibility của phiên bản JUnit đang dùng.

### 12.5. Phụ thuộc vào thứ tự “before/after” sai chỗ

`BeforeEachCallback` chạy trước `@BeforeEach`, còn `BeforeTestExecutionCallback` chạy sau setup nhưng trước thân test. Lỗi thường gặp là extension kiểm tra dữ liệu do `@BeforeEach` tạo ra ngay trong `BeforeEachCallback`: lúc đó dữ liệu chưa được chuẩn bị. Hãy chọn callback đúng thời điểm.

### 12.6. Thêm `@SpringBootTest` để chữa mọi lỗi test

Full Boot context có thể cần database, security, external configuration; khởi động chậm và mở rộng vùng lỗi. Nếu chỉ kiểm tra một class Java, MockitoExtension là đủ. Nếu cần một cấu hình DI nhỏ, `@SpringJUnitConfig` có thể phù hợp. Nếu cần MVC/JPA, ưu tiên test slice tương ứng; full context khi thật sự cần liên kết nhiều tầng.

### 12.7. Giả định `@Transactional` rollback tất cả request

Trong Spring Test, transaction của test method có thể rollback ở cuối method. Nhưng khi `@SpringBootTest(webEnvironment = RANDOM_PORT)` gọi HTTP thật, server xử lý ở thread và transaction khác, nên commit từ phía server **không tự rollback** theo annotation trên test method. Cần quản lý fixture và cleanup đúng boundary. SpringExtension không biến mọi request thành chung một transaction.

### 12.8. Bị `UnnecessaryStubbingException` hoặc lỗi mock tham số

Chỉ stub những lời gọi cần cho hành vi đang test; Mockito strictness phát hiện stubbing thừa. Với mock ở method parameter, chú ý mock đó là một object khác mock field tương tự; nếu method đang test dùng field mock nhưng bạn stub parameter mock, cấu hình không có tác dụng. Truy vết collaborator **thực sự được sử dụng** trước khi sửa assertion.

### 12.9. Dùng annotation API khác phiên bản

Một số tài liệu mới dùng `@MockitoBean`; Boot 3.3.x vẫn dùng `@MockBean` của Boot cho test context. JUnit Jupiter 5.x và JUnit Jupiter 6.x có yêu cầu nền tảng khác nhau. Với dự án đã khóa phiên bản, ưu tiên BOM và tài liệu phù hợp phiên bản đó, không copy annotation từ bản mới rồi coi là API có sẵn.

## 13. Quy trình chọn và kiểm tra extension trong dự án

Khi bắt đầu một test, đi theo câu hỏi:

1. **Chỉ cần gọi Java class thuần?** Dùng `@Test`, assert; nếu class có collaborator cần cô lập, thêm MockitoExtension.
2. **Cần Spring tạo/inject bean?** Dùng SpringExtension qua `@SpringJUnitConfig`, hoặc test annotation của Boot có sẵn SpringExtension.
3. **Cần thay Spring bean bằng mock?** Dùng cơ chế bean mock đúng phiên bản Boot/Spring; `@Mock` đơn lẻ không thay bean.
4. **Cần fixture/hook lặp lại trong nhiều test?** Cân nhắc extension tự viết, dùng `BeforeEachCallback`, `ParameterResolver` hoặc `ExtensionContext.Store` phù hợp.
5. **Có đăng ký nhiều extension?** Kiểm tra thứ tự callback, phạm vi, collision của `ParameterResolver` và tài nguyên shared.
6. **Test FAIL?** Xác định FAIL tại giai đoạn nào: discovery, constructor parameter, extension setup, Spring context refresh, Mockito session, thân test, hoặc callback cleanup.

### Lệnh xác minh bộ ví dụ

Trong project Gradle mục 5, các lớp hoàn chỉnh tương ứng là:

```bash
./gradlew test --tests 'com.example.testing.ExtensionLifecycleTest'
./gradlew test --tests 'com.example.testing.FixedClockTest'
./gradlew test --tests 'com.example.testing.MockitoOrderServiceTest'
./gradlew test --tests 'com.example.testing.SpringClockWiringTest'
```

Tổng cộng có **6 test method** trong bốn lớp hoàn chỉnh: 1 lifecycle + 1 parameter resolver + 3 Mockito + 1 Spring. Với dependency và mã đúng như trên, các assertion đều PASS. Lớp `ApplicationContextTest`/`OrderServiceSpringTest` ở mục 10 **không tính** vào sáu test này, vì đó là ví dụ tích hợp cần ứng dụng Boot thật.

Nếu cần theo dõi cụ thể, mở báo cáo Gradle `build/reports/tests/test/index.html` hoặc XML trong `build/test-results/test/`. Không nên diễn giải `BUILD SUCCESSFUL` thành “đã xác minh toàn bộ ứng dụng Boot” khi chỉ chạy vài unit/component test.

## 14. Câu hỏi tự kiểm tra

**1.** `MockitoExtension` có khởi tạo Spring `ApplicationContext` không?  
Không. Nó quản lý Mockito mock và session; SpringExtension/TestContext đảm nhận Spring context.

**2.** Vì sao `@SpringBootTest` không cần `@ExtendWith(SpringExtension.class)` bổ sung?  
Vì annotation kiểm thử của Boot đã tích hợp SpringExtension.

**3.** `BeforeEachCallback` và `@BeforeEach` cái nào chạy trước?  
`BeforeEachCallback` của extension.

**4.** Trong `ParameterResolver`, ý nghĩa của `supportsParameter` là gì?  
Nó xác định resolver có chịu trách nhiệm cho tham số được yêu cầu hay không; `resolveParameter` mới cấp giá trị.

**5.** Vì sao `@Mock` có thể không tác động đến một service do Spring inject?  
Vì mock field của test không mặc nhiên thay đổi bean registry trong Spring context.

**6.** Khi hai extension cùng resolve một parameter thì làm gì?  
Phân định lại owner hoặc giới hạn điều kiện resolver, tránh parameter resolution conflict.

**7.** Nếu không cần Spring context, tại sao nên chọn MockitoExtension?  
Test đơn giản, chạy nhanh, tập trung vào logic và interaction của class cần kiểm tra.

## 15. Tổng kết

JUnit Jupiter **Extension Model** cung cấp cơ chế mở rộng vòng đời, giải quyết tham số, xử lý điều kiện và trạng thái test theo một hợp đồng thống nhất. **MockitoExtension** giúp test Java có mock rõ ràng, session có kiểm soát và strict stubbing. **SpringExtension** kết nối JUnit với Spring TestContext để kiểm tra dependency injection, bean configuration và tích hợp Spring/Boot.

Chọn extension theo **đối tượng được kiểm tra**: logic Java thuần, một Spring component hay nhiều bean trong Boot context. Đọc kỹ nơi tạo dependency và ai sở hữu nó sẽ tránh được phần lớn lỗi `null` mock, missing bean, wrong lifecycle và competing resolvers.

### Tài liệu gốc để đối chiếu

- [JUnit Jupiter 5.10.2 User Guide — Extension Model](https://docs.junit.org/5.10.2/user-guide/) (registration, callback ordering, parameter resolution, store).
- [Mockito — MockitoExtension source/Javadoc](https://github.com/mockito/mockito/blob/main/mockito-extensions/mockito-junit-jupiter/src/main/java/org/mockito/junit/jupiter/MockitoExtension.java) (mock initialization, strictness, method parameters).
- [Spring Framework 6.1 — SpringJUnitConfig](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/test/context/junit/jupiter/SpringJUnitConfig.html) (composed annotation).
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) (`@SpringBootTest`, test slices, `@MockBean` và transaction).

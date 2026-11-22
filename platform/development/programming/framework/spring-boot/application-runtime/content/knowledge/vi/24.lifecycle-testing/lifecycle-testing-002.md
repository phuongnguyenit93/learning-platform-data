# Kiểm thử runner bằng ApplicationArguments và phụ thuộc giả trong Spring Boot

`ApplicationRunner` và `CommandLineRunner` thường chứa logic chạy **một lần trong chuỗi khởi động ứng dụng Spring Boot**: đọc tham số dòng lệnh, kiểm tra đầu vào, khởi động một tác vụ batch, đồng bộ dữ liệu hoặc thực hiện bước chuẩn bị trước khi ứng dụng sẵn sàng. Vì runner được framework tự gọi, người viết test rất dễ gặp hai vấn đề: phải khởi động toàn bộ Spring context chỉ để kiểm tra một nhánh parse, hoặc vô tình cho runner chạm database/API thật **trước khi test kịp tạo mock**.

Cách tiếp cận đáng tin cậy là **tách việc giải thích arguments, việc thực thi nghiệp vụ và cơ chế tự gọi runner của Spring Boot**, rồi kiểm tra từng tầng:

1. **Unit test nhanh:** tự tạo `new DefaultApplicationArguments(...)`, inject một **fake dependency** vào runner, gọi trực tiếp `runner.run(args)`, xác minh input, số lần gọi, tham số và lỗi. **Không cần ApplicationContext.**
2. **Unit test với Mockito:** mock interface dependency, dùng `verify(...)` để kiểm tra interaction, không có I/O thật.
3. **Integration test của lifecycle:** dùng `@SpringBootTest(args = {...})` để cho **SpringApplication khởi chạy và tự gọi runner**, nhưng thay dependency bằng fake **được cấu hình trước khi context được tạo**.
4. **Process-level test khi cần:** khởi chạy child JVM hoặc JAR để kiểm tra stdout, failure của startup, exit code và các side effects bên ngoài.

Bài học sử dụng **Java 17+, Spring Boot 3.3.x, JUnit Jupiter 5, AssertJ và Mockito**. Trong ví dụ, runner nhận `--count=N` và cờ `--dry-run`; phần xử lý bên dưới được che bằng interface `JobGateway`, để test không bao giờ gọi API hay database thật.

> **Nguyên tắc:** unit test runner kiểm tra *runner sẽ yêu cầu dependency làm gì*; integration test kiểm tra *Spring Boot có thực sự gọi runner đúng thời điểm với arguments và bean đúng không*. Hai loại kiểm thử bổ sung cho nhau, không thay thế nhau.

## 1. Runner chạy ở đâu trong vòng đời ứng dụng?

Một trình tự khái quát trong Spring Boot 3.3:

~~~text
SpringApplication.run(args)
         |
         +-- Tạo Environment và ApplicationContext
         +-- Load bean definitions, dependency injection
         +-- Refresh ApplicationContext
         +-- ApplicationStartedEvent
         |
         +-- Call ApplicationRunner / CommandLineRunner
         |       |
         |       +-- Validate ApplicationArguments
         |       +-- Gọi service/gateway để làm việc
         |       +-- Nếu lỗi không được xử lý: startup có thể thất bại
         |
         +-- ApplicationReadyEvent khi startup hoàn tất bình thường
         +-- SpringApplication.run(args) trả context
~~~

`ApplicationRunner.run(ApplicationArguments args)` là callback do Spring Boot gọi **gần cuối quá trình startup và trước khi `SpringApplication.run(...)` hoàn tất**. Các runner khác nhau có thể được sắp thứ tự bằng `@Order` hoặc `Ordered`, nhưng không nên mặc định thứ tự bằng tên class hay thứ tự quét package.

**Hai điểm quan trọng khi kiểm thử:**

- Tạo Spring bean `BatchRunner` **không đồng nghĩa method `run(...)` đã được gọi**. Đó là hai sự kiện khác nhau.
- Khi `@SpringBootTest` khởi tạo ApplicationContext qua Spring Boot, callback runner **thường đã thực thi trước khi `@Test` và `@BeforeEach` bắt đầu**. Vì vậy cấu hình một mock trong test method có thể là **quá muộn** cho lần chạy startup.

Nếu một runner ném exception trong thời gian startup, `SpringApplication.run(...)` có thể thất bại trước khi trả context. Unit test nên xác minh lỗi được **truyền ra**, còn integration test thất bại cần có thiết kế kiểm thử riêng, không dùng thủ thuật nuốt exception khiến startup báo thành công giả.

## 2. ApplicationArguments có những trạng thái nào?

Spring Boot cung cấp interface `ApplicationArguments` và implementation `DefaultApplicationArguments`. Trong production, Spring Boot tạo đối tượng arguments từ command line. Trong unit test, bạn có thể tạo nó trực tiếp:

~~~java
ApplicationArguments args =
        new DefaultApplicationArguments(
                "--count=3", "--dry-run");
~~~

Đoạn này cần import `org.springframework.boot.ApplicationArguments` và `org.springframework.boot.DefaultApplicationArguments`; không cần Spring context.

Các method đáng sử dụng:

| API | Ý nghĩa |
|---|---|
| `getSourceArgs()` | Mảng các token dòng lệnh ban đầu |
| `getOptionNames()` | Tập hợp tên option không có tiền tố `--` |
| `containsOption("dry-run")` | Có xuất hiện cờ/option không |
| `getOptionValues("count")` | Danh sách giá trị đi kèm option |
| `getNonOptionArgs()` | Các positional arguments |

Đặc biệt, `getOptionValues(name)` **không trả cùng một thứ** ở mọi trường hợp:

| Token đầu vào | `getOptionValues("count")` |
|---|---|
| Không có `--count` | `null` |
| `--count` không có giá trị | Danh sách rỗng `[]` |
| `--count=3` | `["3"]` |
| `--count=3 --count=4` | `["3","4"]` |
| `--count=` | Có một giá trị chuỗi rỗng, cần tự validate |

Vì vậy code như sau **có thể sai** khi option chưa xuất hiện:

~~~java
String count = args.getOptionValues("count").get(0);
~~~

Nó có thể ném `NullPointerException` hoặc `IndexOutOfBoundsException`, khiến thông báo cho người vận hành khó hiểu. Bài toán đúng là xác nhận **một option bắt buộc tồn tại, nhận chính xác một giá trị, không rỗng và nằm trong miền hợp lệ** trước khi gửi công việc tới dependency.

Với cờ `--dry-run`, `containsOption("dry-run")` cho biết có mặt. Nếu thiết kế flag **không được nhận value**, cần kiểm tra thêm `getOptionValues("dry-run")` để từ chối dạng `--dry-run=true`.

## 3. Thiết kế class runner để dễ kiểm thử

**Không đặt logic JDBC/HTTP ngay trong runner.** Tách ra một interface đại diện tác động nghiệp vụ:

~~~text
CLI tokens
    |
    v
DefaultApplicationArguments / ApplicationArguments
    |
    v
BatchRunner implements ApplicationRunner
    |       - kiểm tra option
    |       - parse số
    |       - chọn dry-run
    v
JobGateway (interface)
    |
    +-- ConsoleJobGateway (ứng dụng demo)
    +-- FakeJobGateway (unit test)
    +-- RecordingGateway (integration test)
    +-- Mockito mock (unit test khác)
~~~

Lợi ích:

- Runner là object Java bình thường: `new BatchRunner(fake)`.
- Dependency được inject qua constructor; không cần thay field private bằng reflection.
- Thử validation mà không mở kết nối mạng.
- Thử đường lỗi dependency bằng cách cho fake ném exception có chủ đích.
- Kiểm tra invocation count, order và arguments bằng recording fake/mock.
- Integration test có thể dùng fake đã tồn tại khi SpringApplication gọi runner lúc startup.

**Fake khác mock:** fake là implementation do test viết, thực sự lưu trạng thái hoặc có hành vi đơn giản; mock do framework như Mockito tạo để cấu hình return/exception và xác minh interaction. Cả hai đều là **test doubles**, không tự động là integration test.

## 4. Project Spring Boot + JUnit chạy được

Ví dụ sau có đủ mã sản phẩm và test, không yêu cầu database hay HTTP server.

Cấu trúc:

~~~text
runner-test-lab/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/runnerlab/
    │   │   ├── RunnerTestingApplication.java
    │   │   ├── JobGateway.java
    │   │   ├── ConsoleJobGateway.java
    │   │   └── BatchRunner.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/runnerlab/
            ├── BatchRunnerTest.java
            └── RunnerStartupIntegrationTest.java
~~~

### 4.1 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    mainClass = 'com.example.runnerlab.RunnerTestingApplication'
}
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, Mockito và Spring Test theo dependency management tương thích với Boot. Không cần tự gắn nhiều phiên bản JUnit/Mockito không tương thích chỉ để kiểm tra runner này.

Tệp `src/main/resources/application.properties`:

~~~properties
spring.application.name=runner-test-lab
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=WARN
~~~

Không có web starter nên ứng dụng batch demo không cần HTTP server. Property web type `none` làm ý định rõ ràng. Trong production, hãy cân nhắc logging chi tiết hơn; ở đây giảm thông điệp startup để dễ thấy output nghiệp vụ.

### 4.2 RunnerTestingApplication.java

~~~java
package com.example.runnerlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class RunnerTestingApplication {

    public static void main(String[] args) {
        // run() gọi ApplicationRunner trước khi trả context.
        try (ConfigurableApplicationContext ignored =
                     SpringApplication.run(
                             RunnerTestingApplication.class, args)) {
            // One-shot demo: sau khi runner xong, đóng context.
        }
    }
}
~~~

Vì main **không gọi `System.exit(...)`**, JUnit test không có nguy cơ bị thoát JVM do một lời gọi trực tiếp ở tầng ứng dụng. Tuy nhiên, **không gọi main trong unit test**: test class `BatchRunner` trực tiếp sẽ nhanh, ổn định và xác định hơn.

Trong `@SpringBootTest` mặc định, Spring Boot TestContextLoader tạo context qua `SpringApplication` chứ **không bắt buộc gọi chính method main** (thuộc tính `useMainMethod` mặc định `NEVER` ở Spring Boot 3.3). Do đó khối `try-with-resources` trong main không làm integration test đóng context trước khi test method bắt đầu.

### 4.3 JobGateway.java

~~~java
package com.example.runnerlab;

public interface JobGateway {

    void execute(int count, boolean dryRun);
}
~~~

Interface đại diện thao tác nghiệp vụ. Trong hệ thống thật nó có thể ủy quyền cho repository hoặc external API. Với bài học, nó **không ràng buộc** vào database/HTTP, nên dễ fake và test.

### 4.4 ConsoleJobGateway.java

~~~java
package com.example.runnerlab;

import org.springframework.stereotype.Component;

@Component
public class ConsoleJobGateway implements JobGateway {

    @Override
    public void execute(int count, boolean dryRun) {
        if (dryRun) {
            System.out.printf("DRY_RUN count=%d%n", count);
            return;
        }

        System.out.printf("EXECUTED count=%d%n", count);
    }
}
~~~

Đây chỉ là implementation demo in ra console; không thực sự tạo dữ liệu. Trong production, `dryRun` phải được thực thi theo hợp đồng **không gây side effect ngoài ý muốn**, hoặc được xử lý ở tầng riêng có thể kiểm chứng.

### 4.5 BatchRunner.java

~~~java
package com.example.runnerlab;

import java.util.List;
import java.util.Set;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class BatchRunner implements ApplicationRunner {

    private final JobGateway gateway;

    public BatchRunner(JobGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!args.getNonOptionArgs().isEmpty()) {
            throw new IllegalArgumentException(
                    "Positional arguments are not supported");
        }

        Set<String> allowed = Set.of("count", "dry-run");
        for (String name : args.getOptionNames()) {
            if (!allowed.contains(name)) {
                throw new IllegalArgumentException(
                        "Unknown option: --" + name);
            }
        }

        List<String> counts = args.getOptionValues("count");
        if (counts == null || counts.size() != 1
                || counts.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Exactly one --count=<1..1000> is required");
        }

        final int count;
        try {
            count = Integer.parseInt(counts.get(0));
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "--count must be an integer", ex);
        }

        if (count < 1 || count > 1000) {
            throw new IllegalArgumentException(
                    "--count must be between 1 and 1000");
        }

        List<String> dryRunValues =
                args.getOptionValues("dry-run");
        if (dryRunValues != null && !dryRunValues.isEmpty()) {
            throw new IllegalArgumentException(
                    "--dry-run is a flag without a value");
        }

        boolean dryRun = args.containsOption("dry-run");

        // Chỉ gọi dependency sau khi TẤT CẢ validation đã qua.
        gateway.execute(count, dryRun);
    }
}
~~~

**Đặc tính test được:**

- Không dùng `System.exit(...)`, thread, sleep hoặc API network trong runner.
- Nếu input sai, exception đi ra và **`gateway.execute(...)` không được gọi**.
- Input hợp lệ khiến gateway được gọi **đúng một lần**.
- Nếu gateway lỗi, runner **không nuốt lỗi**; lỗi tiếp tục được truyền để Spring Boot xử lý failure khi khởi động.
- Constructor injection cho phép thay dependency bằng fake/mock tùy từng test mà không phải thay cấu hình toàn application.

Chú ý `@Component` để Spring tìm và đăng ký runner trong production. Khi unit test chỉ dùng `new BatchRunner(fake)`, annotation đó **không kích hoạt** lifecycle tự động — điều này có chủ đích.

## 5. Unit test với DefaultApplicationArguments và fake dependency

Tạo tệp `src/test/java/com/example/runnerlab/BatchRunnerTest.java`:

~~~java
package com.example.runnerlab;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;

class BatchRunnerTest {

    private final FakeJobGateway fake = new FakeJobGateway();
    private final BatchRunner runner = new BatchRunner(fake);

    @Test
    void validCountInvokesDependencyExactlyOnce() {
        runner.run(new DefaultApplicationArguments("--count=3"));

        assertThat(fake.calls)
                .containsExactly(new Invocation(3, false));
    }

    @Test
    void dryRunFlagIsPassedToDependency() {
        runner.run(new DefaultApplicationArguments(
                "--count=5", "--dry-run"));

        assertThat(fake.calls)
                .containsExactly(new Invocation(5, true));
    }

    @Test
    void invalidArgumentsNeverInvokeDependency() {
        String[][] invalid = {
                {},
                {"--count"},
                {"--count="},
                {"--count=abc"},
                {"--count=0"},
                {"--count=1001"},
                {"--count=2", "--count=3"},
                {"--count=2", "extra"},
                {"--count=2", "--other=yes"},
                {"--count=2", "--dry-run=true"}
        };

        for (String[] tokens : invalid) {
            assertThatThrownBy(() ->
                    runner.run(new DefaultApplicationArguments(tokens)))
                    .isInstanceOf(IllegalArgumentException.class);
        }

        assertThat(fake.calls).isEmpty();
    }

    @Test
    void downstreamFailureIsNotSwallowed() {
        fake.failure = new IllegalStateException(
                "storage unavailable");

        assertThatThrownBy(() ->
                runner.run(new DefaultApplicationArguments("--count=2")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("storage unavailable");

        assertThat(fake.calls)
                .containsExactly(new Invocation(2, false));
    }

    @Test
    void mockitoCanVerifyTheSameInteraction() {
        JobGateway mocked = mock(JobGateway.class);
        BatchRunner underTest = new BatchRunner(mocked);

        underTest.run(new DefaultApplicationArguments(
                "--count=7", "--dry-run"));

        verify(mocked).execute(7, true);
        verifyNoMoreInteractions(mocked);
    }

    private record Invocation(int count, boolean dryRun) {
    }

    private static final class FakeJobGateway
            implements JobGateway {

        private final List<Invocation> calls = new ArrayList<>();
        private RuntimeException failure;

        @Override
        public void execute(int count, boolean dryRun) {
            calls.add(new Invocation(count, dryRun));
            if (failure != null) {
                throw failure;
            }
        }
    }
}
~~~

### 5.1 Tại sao test này thật sự là unit test?

- Không có `@SpringBootTest`, `@Autowired` hay `ApplicationContext`.
- Mỗi JUnit test instance theo lifecycle mặc định tạo một `FakeJobGateway` mới.
- Mọi arguments được tạo trong bộ nhớ qua `DefaultApplicationArguments`.
- Không có database, HTTP request, random timing hoặc startup tự động.
- Kết quả được xác minh bằng **state của fake** hoặc **interaction của Mockito mock**.

Mỗi test phản ánh một trách nhiệm riêng:

| Test | Điều được bảo đảm |
|---|---|
| `validCountInvokesDependencyExactlyOnce` | Input hợp lệ, count parse đúng, không tự dry-run |
| `dryRunFlagIsPassedToDependency` | Flag được nhận và truyền đúng |
| `invalidArgumentsNeverInvokeDependency` | Validate trước side effects; nhiều loại input sai |
| `downstreamFailureIsNotSwallowed` | Lỗi của dependency tiếp tục đi ra; gateway được gọi đúng một lần |
| `mockitoCanVerifyTheSameInteraction` | Có thể dùng Mockito thay fake thủ công |

Điểm đáng chú ý của test `invalidArgumentsNeverInvokeDependency`: nó **không chỉ kiểm tra exception**. Nó còn xác nhận gateway **chưa được đụng tới**. Với một job import hoặc migration, đây là ranh giới quan trọng để tránh thực hiện một phần nghiệp vụ trước khi biết input không hợp lệ.

### 5.2 Fake state và Mockito interaction dùng khi nào?

**Fake** thích hợp nếu cần quan sát nhiều lời gọi, giữ dữ liệu, mô phỏng state hoặc xác minh kết quả sau nhiều bước. Ví dụ `FakeJobGateway.calls` cho phép assert đúng order và arguments.

**Mockito mock** thích hợp nếu chỉ muốn chắc chắn một method được gọi đúng tham số/số lần. Có thể mở rộng bằng:

~~~java
verify(mocked).execute(7, true);
verifyNoMoreInteractions(mocked);
~~~

Hai dòng này nằm trong bối cảnh test trước đó, không phải chương trình độc lập.

Với dependency có giá trị trả về hoặc failure, Mockito hỗ trợ `when(...).thenReturn(...)`, `thenThrow(...)`, `doThrow(...)`. Với interface `void execute(...)` trong ví dụ, dùng `doThrow(...)` nếu muốn mô phỏng exception; không gọi `when(mock.execute(...))` vì method trả `void`.

Đừng lạm dụng `verifyNoMoreInteractions(...)` cho mọi test production: thay đổi implementation không ảnh hưởng contract có thể làm test giòn. Dùng nó khi **không gọi thêm dependency ngoài ý muốn** chính là yêu cầu nghiệp vụ cần bảo vệ.

## 6. Integration test: cho SpringApplication thật sự tự gọi runner

Unit test chứng minh `BatchRunner.run(...)` đúng khi bạn **tự gọi nó**. Nhưng unit test không chứng minh:

- Spring có nhận biết `BatchRunner` là bean không?
- Runner có được tự gọi khi context refresh hoàn tất không?
- `@SpringBootTest(args=...)` có truyền arguments thật cho runner không?
- Dependency injection có chọn đúng test double không?
- Production gateway có bị gọi trong quá trình context start không?

Để kiểm tra, tạo integration test với `@SpringBootTest` và một fake được đăng ký bằng `@TestConfiguration` **trước khi runner được chạy**.

Tệp `src/test/java/com/example/runnerlab/RunnerStartupIntegrationTest.java`:

~~~java
package com.example.runnerlab;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = {
                RunnerTestingApplication.class,
                RunnerStartupIntegrationTest.FakeBeans.class
        },
        args = {"--count=4", "--dry-run"},
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class RunnerStartupIntegrationTest {

    @Autowired
    private RecordingGateway recordingGateway;

    @Test
    void runnerWasCalledDuringSpringApplicationStartup() {
        // Khi @Test bắt đầu, ApplicationRunner đã chạy.
        assertThat(recordingGateway.snapshot())
                .containsExactly(new Invocation(4, true));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FakeBeans {

        @Bean
        @Primary
        RecordingGateway recordingGateway() {
            return new RecordingGateway();
        }
    }

    private record Invocation(int count, boolean dryRun) {
    }

    static final class RecordingGateway implements JobGateway {

        private final List<Invocation> calls =
                new CopyOnWriteArrayList<>();

        @Override
        public void execute(int count, boolean dryRun) {
            calls.add(new Invocation(count, dryRun));
        }

        List<Invocation> snapshot() {
            return List.copyOf(calls);
        }
    }
}
~~~

**Vì sao cách này đáng tin?**

1. `@SpringBootTest(classes=..., args=..., webEnvironment=NONE)` dùng Spring Boot để tạo ApplicationContext.
2. Boot 3.3 sẽ chạy `ApplicationRunner` trong quá trình startup, **trước khi method `@Test` được gọi**.
3. `FakeBeans` là test configuration được đưa vào ngay từ đầu; nó tạo `RecordingGateway` implement `JobGateway`.
4. `@Primary` làm test double này được chọn khi inject `JobGateway` vào `BatchRunner`, thay cho `ConsoleJobGateway` được component-scan ở production.
5. Fake được tạo **trước khi runner execute**, lưu `Invocation(4,true)`.
6. Test chỉ đọc snapshot của fake sau startup. **Không tự gọi `runner.run(...)` lần nữa**, vì như thế test không còn chứng minh “chỉ một lần do Spring tự gọi”.
7. Context được Spring Test quản lý và đóng theo test lifecycle/cache; không cần gọi `System.exit`.

Hai test classes dùng hai cấp độ: unit class không dựng context, integration class dựng một context. Chạy test trên một project không có database thật nên không phát sinh kết nối ngoài.

### Đừng thay fake bằng @MockBean cấu hình quá muộn

Một anti-pattern:

~~~java
@SpringBootTest(args = "--count=4")
class BrokenTimingTest {

    @MockBean
    JobGateway gateway;

    @BeforeEach
    void setUp() {
        // Quá muộn nếu runner đã dùng gateway lúc startup.
        doThrow(new IllegalStateException("failed"))
                .when(gateway).execute(4, false);
    }
}
~~~

Đây là **đoạn minh họa anti-pattern**, bỏ qua imports, không thuộc code chạy của project. Với Spring Boot 3.3, `@MockBean` có thể đặt mock vào context, nhưng việc cấu hình stubbing **trong `@BeforeEach` hoặc `@Test`** xảy ra **sau khi runner đã được Boot gọi khi khởi động**. Vì thế mock có thể đã trả giá trị mặc định lúc cần, còn việc `doThrow(...)` sau đó không thay đổi lịch sử lần chạy.

Spring Boot documentation cũng cảnh báo không nên trông chờ cấu hình `@MockBean` trong test method sẽ ảnh hưởng các bean đã được sử dụng trong quá trình context refresh. Với runner startup, thời điểm còn muộn hơn phần refresh nhưng vẫn trước test method.

Nếu muốn Mockito mock **được cấu hình sẵn trước startup**, tạo nó trong một `@TestConfiguration @Bean` và stub ngay trong factory method, rồi inject qua `@Primary` như mô hình recording fake. Nhưng với bài này, fake hand-written thường đơn giản và dễ quan sát hơn.

## 7. Chạy test và phân biệt test report với runtime stdout

Trong thư mục project có Gradle wrapper và JDK 17+:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Các test JUnit kỳ vọng:

~~~text
BatchRunnerTest: 5 tests PASSED
RunnerStartupIntegrationTest: 1 test PASSED
Total: 6 tests PASSED
~~~

Đây là **tóm tắt số test và trạng thái kỳ vọng**, không phải chuỗi Gradle bắt buộc in nguyên văn. Gradle có thể chỉ ghi `BUILD SUCCESSFUL` hoặc hiển thị các test details dưới XML/HTML reports tùy cấu hình.

Nếu muốn chạy riêng:

~~~bash
./gradlew test --tests 'com.example.runnerlab.BatchRunnerTest'
./gradlew test --tests 'com.example.runnerlab.RunnerStartupIntegrationTest'
~~~

Kết quả kỳ vọng là cả hai test classes hoàn tất thành công. Những test này **không gọi database hay external API**.

Để chạy application thật:

~~~bash
./gradlew bootJar
java -jar build/libs/runner-test-lab-1.0.0.jar --count=3
~~~

Tên JAR của Gradle thường có hậu tố phiên bản như trên nếu chưa tùy chỉnh packaging. Kiểm tra tên JAR thật trong thư mục `build/libs` nếu bạn thay `version` hoặc `archiveFileName`.

**Dòng do `ConsoleJobGateway` in** trong điều kiện chạy bình thường:

~~~text
EXECUTED count=3
~~~

Với:

~~~bash
java -jar build/libs/runner-test-lab-1.0.0.jar \
    --count=3 --dry-run
~~~

Dòng nghiệp vụ kỳ vọng:

~~~text
DRY_RUN count=3
~~~

Spring Boot/Gradle có thể in log riêng; hai dòng trên là **output từ demo gateway**, không phải cam kết toàn bộ stdout/stderr chỉ chứa dòng đó.

### Điều gì xảy ra khi input sai ở runtime?

Ví dụ:

~~~bash
java -jar build/libs/runner-test-lab-1.0.0.jar --count=abc
~~~

`BatchRunner` ném `IllegalArgumentException` trong chuỗi startup. Spring Boot sẽ xử lý startup failure và application không hoàn tất chạy bình thường. Không có dòng `EXECUTED...` vì gateway chưa được gọi.

Không khẳng định chính xác exit code của ví dụ này luôn là một số cụ thể trong mọi launcher/OS: code **chưa định nghĩa** custom exit-code contract. Nếu muốn phân biệt exit status 0/2/10, hãy bổ sung cơ chế `ExitCodeGenerator`/`ExitCodeExceptionMapper` và kiểm thử **bằng child process**, không chỉ nhìn JUnit assertion.

## 8. So sánh ba kỹ thuật kiểm thử

| Kỹ thuật | Có Spring context? | Runner do ai gọi? | Dùng khi nào? |
|---|---|---|---|
| Unit test với `DefaultApplicationArguments` + fake | **Không** | Test gọi `runner.run(args)` | Parse, validation, số lần gọi, lỗi dependency |
| Unit test với Mockito mock | **Không** | Test gọi `runner.run(args)` | Interaction, argument capture, exception |
| `@SpringBootTest(args=...)` + fake ở `@TestConfiguration` | **Có** | **Spring Boot startup tự gọi** | Wiring, lifecycle, arguments được chuyển đúng |
| `ApplicationContextRunner` | Context nhẹ, không phải full SpringApplication startup | Thường test phải gọi runner thủ công nếu cần | Auto-configuration/bean registration, **không thay thế full runner lifecycle test** |
| Child process/JAR integration | JVM/process riêng | Spring Boot thực tế | Startup failure, console output, exit code, shutdown |

Không có lý do phải dựng toàn bộ Spring container chỉ để kiểm tra `--count=abc` gây lỗi. Nhưng cũng không nên chỉ unit-test rồi kết luận annotation `@Component`, `@Order`, injection và lifecycle thực tế đều chắc chắn đúng.

### Một test không tốt: tự gọi runner trong @SpringBootTest

~~~java
@Autowired
BatchRunner runner;

@Test
void callsRunner() {
    runner.run(new DefaultApplicationArguments("--count=4"));
}
~~~

Đây là một **đoạn minh họa** đặt trong class test đã có import. Nếu context đã auto-run `BatchRunner` từ trước, test này gọi thêm **lần thứ hai**. Nó không chứng minh runner tự được gọi một lần khi startup; tệ hơn, nếu runner có side effect thật, test có thể gây duplicate.

Vì thế, dùng unit test gọi trực tiếp hoặc integration test quan sát state **đã có sau startup**, không trộn hai mô hình một cách không chủ đích.

## 9. Những trường hợp biên phải test cho ApplicationArguments

### 9.1 Không có option bắt buộc

~~~java
new DefaultApplicationArguments()
~~~

`getOptionValues("count") == null`. Runner nên ném lỗi có nội dung cụ thể, không phải `NullPointerException`.

### 9.2 Có tên option nhưng thiếu giá trị

~~~java
new DefaultApplicationArguments("--count")
~~~

Ở đây count có mặt nhưng không có giá trị. Đây là lỗi khác với option vắng mặt về cấu trúc, nhưng có thể cùng exception nghiệp vụ.

### 9.3 Nhiều giá trị cho một option

~~~java
new DefaultApplicationArguments("--count=2", "--count=3")
~~~

Nếu contract chỉ cho một giá trị, phải từ chối thay vì âm thầm chọn phần tử đầu hoặc cuối.

### 9.4 Option không biết và positional argument

~~~java
new DefaultApplicationArguments("--count=3", "--other=yes")
new DefaultApplicationArguments("--count=3", "data.csv")
~~~

Nếu không hỗ trợ, cả hai phải bị từ chối trước khi gọi gateway.

### 9.5 Cờ boolean không nhận giá trị

~~~java
new DefaultApplicationArguments("--count=3", "--dry-run")
new DefaultApplicationArguments("--count=3", "--dry-run=true")
~~~

Theo contract ở ví dụ, dòng đầu hợp lệ, dòng thứ hai sai. `containsOption("dry-run")` **một mình không đủ** để từ chối việc gán value.

### 9.6 Giới hạn số

Kiểm tra số âm, zero, giá trị lớn hơn maximum, số không parse được hoặc tràn phạm vi integer:

~~~text
--count=-1
--count=0
--count=1001
--count=99999999999999999999
--count=3.5
~~~

Code sử dụng `Integer.parseInt` và giới hạn 1–1000, nên các trường hợp này đều phải lỗi trước gateway.

### 9.7 Exception của dependency

Input hợp lệ nhưng fake ném `IllegalStateException("storage unavailable")`. Test cần xác minh **lỗi được truyền ra**, gateway được gọi đúng số lần, không tự động retry hoặc báo success.

### 9.8 Dry-run và tác động thực

Unit test runner xác nhận `dryRun=true` được truyền xuống dependency. Nhưng nếu yêu cầu bảo đảm “dry-run không ghi database” thì còn phải test **implementation của gateway** hoặc tầng nghiệp vụ thật, thường bằng fake repository/transaction integration test riêng. **Một boolean được truyền đúng chưa chứng minh không có side effect.**

## 10. Runner và transaction: tránh database bị gọi trong test

Một runner có thể gọi service dùng `@Transactional`:

~~~java
@Component
class ImportRunner implements ApplicationRunner {

    private final ImportService importService;

    ImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) {
        importService.importOnce();
    }
}
~~~

Đây là đoạn **minh họa**, chưa khai báo `ImportService` và policy parse; không phải project hoàn chỉnh. Nếu chạy `@SpringBootTest` với bean import service thật, công việc có thể được gọi **trước test method**, mở datasource và thay đổi database thật hoặc in-memory.

Đừng dựa vào `@Transactional` trên test method để rollback side effects đã xảy ra **trong giai đoạn khởi động context** trước khi test transaction bắt đầu. Ngay cả với test transaction, background threads hoặc kết nối bên ngoài cũng không mặc nhiên tham gia cùng transaction đó.

Hướng làm:

- **Unit test:** inject fake repository/service và gọi runner trực tiếp, không có DB.
- **Lifecycle integration test:** cung cấp `@Primary` fake gateway **trước startup**, như ví dụ mục 6.
- **Database integration test thật:** dùng database/container test riêng được kiểm soát, reset state và assertions cho transactions.
- **External API:** dùng HTTP stub server hoặc mock client bean, chặn mọi request tới production domain.
- **Job có side effects:** dùng job ID/idempotency key, kiểm tra không duplicate khi context refresh lặp.

Nếu muốn runner được bật có điều kiện chỉ trong production, có thể dùng `@Profile`/`@ConditionalOnProperty` hoặc một trigger được quản lý, nhưng **không nên thêm điều kiện chỉ để che test rồi bỏ qua kiểm chứng lifecycle**. Một integration test riêng vẫn cần xác nhận khi điều kiện bật thì runner thực sự chạy.

## 11. MockBean và TestConfiguration: ranh giới thời điểm

Với Spring Boot 3.3, `@MockBean` là công cụ hợp lệ để thay bean trong context. Nó rất hữu ích với service **chỉ được gọi sau khi test setup xong**, chẳng hạn controller được gọi bởi MockMvc trong test method.

Với runner startup, cần đặt câu hỏi khác: **mock cần có hành vi nào ngay lúc SpringApplication tạo context?**

- Nếu runner chỉ gọi void method và cần xác minh có gọi, một preconfigured recording fake thường rõ ràng hơn.
- Nếu mock cần trả dữ liệu để runner startup thành công, stub phải được cài **trước khi runner chạy**.
- `@BeforeEach` hoặc `@Test` không phải pha cài đặt đủ sớm cho startup callbacks.
- Nếu dùng Mockito với `@TestConfiguration @Bean`, hãy tạo và cấu hình mock trong bean factory method, thay vì chờ test method.
- Với mocks auto-reset theo Spring Boot Test, interaction xảy ra trong context startup có thể bị reset trước một test assertion tùy test listener lifecycle. Đừng dựa vào behavior không được xác minh.
- Khi nhiều tests dùng chung context cache, startup runner **không chạy lại trước mỗi test method**, vì context có thể được tái sử dụng. Muốn một invocation cho mỗi test, dùng unit test trực tiếp hoặc xây dựng context riêng có chủ đích.

Ví dụ minh họa cấu hình Mockito mock **trước startup**:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class StartupMockConfig {

    @Bean
    @Primary
    JobGateway preconfiguredGateway() {
        JobGateway mock = Mockito.mock(JobGateway.class);
        // Stubbing cho startup có thể được cấu hình tại đây.
        return mock;
    }
}
~~~

Đoạn này là **cấu hình minh họa**, cần import `TestConfiguration`, `Bean`, `Primary` và `Mockito`; phải được đưa vào test context (bằng explicit classes/import), không phải class chạy độc lập. Với project chính, fake ở mục 6 còn ít cấu hình và dễ assert hơn.

**Không lẫn version:** các tài liệu Spring Boot mới hơn có annotation mocking mới và deprecation khác. Bài này nhắm **Spring Boot 3.3.x**, nơi `@MockBean` còn là API tương ứng; khi nâng framework, cần đối chiếu tài liệu của chính version đang chạy.

## 12. Context caching, test isolation và kiểm tra “chạy đúng một lần”

Spring Test có **ApplicationContext cache**: nhiều test dùng cùng configuration có thể dùng lại một context. Điều này làm test chạy nhanh hơn, nhưng gây hiểu nhầm nếu bạn kỳ vọng `ApplicationRunner` tự chạy lại trước mỗi test.

Ví dụ trong integration test mục 6, method `runnerWasCalledDuringSpringApplicationStartup()` kiểm tra fake lưu **một invocation** từ lần context được tạo. Nếu thêm một method `@Test` khác vào class đó, không có nghĩa `ApplicationRunner` sẽ tự chạy lần nữa.

Để kiểm tra chính xác **một lần mỗi startup**, có ba cách hợp lý:

1. **Unit test:** tạo runner mới và gọi `run(...)` đúng một lần; kiểm tra fake có một invocation.
2. **Integration test:** tạo context mới, đọc recording fake sau startup; một invocation là kết quả mong đợi của cấu hình chỉ có một runner bean.
3. **Process test:** khởi chạy một JVM/JAR mới, kiểm tra một job execution qua logs/durable status, rồi cho process thoát.

Không mặc định mỗi JUnit method = một startup. Nếu buộc phải reset context, có thể cân nhắc `@DirtiesContext`, nhưng nó làm test chậm, tăng I/O và có thể kích hoạt runner có side effects lặp lại. Đa số trường hợp nên tách unit/integration như ví dụ thay vì buộc reload bừa bãi.

Ngoài ra, cần xem:

- Runner được đăng ký hai lần (vừa `@Component`, vừa `@Bean`)? Khi đó nó có thể được gọi hai lần.
- Có nhiều runner với cùng side effect? Cần chính sách idempotency hoặc điều phối một lần.
- Runner có tạo async task rồi return ngay? Khi đó ghi một invocation không chứng minh job xử lý xong.
- Có nhiều `ApplicationContext` trong một JVM? Một context mới có thể thực thi runner riêng.
- Trong Kubernetes có nhiều replicas? Mỗi JVM chạy runner của nó; “một lần startup” **không có nghĩa một lần trên toàn cluster**.

## 13. Kiểm thử thứ tự giữa nhiều runners

Spring Boot hỗ trợ `@Order`/`Ordered` để xác định thứ tự khi có nhiều `ApplicationRunner` hoặc `CommandLineRunner` beans.

Ví dụ cấu hình **minh họa**, không nằm trong project chính:

~~~java
@Component
@Order(10)
class PrepareRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Prepare prerequisites.
    }
}

@Component
@Order(20)
class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Import after PrepareRunner.
    }
}
~~~

Đây là hai class minh họa cần import `Component`, `Order`, `ApplicationRunner` và `ApplicationArguments`. Có thể kiểm tra bằng một **recording fake chung**: mỗi runner ghi marker vào `List<String>`, sau đó assert thứ tự `["prepare","import"]` trong integration test.

**Đừng kiểm thử thứ tự bằng việc đo thời gian giữa các dòng log**: logging bất đồng bộ, thread scheduling hoặc nhiều logger có thể làm quan sát thiếu chắc chắn. Kiểm tra trạng thái/sequence có chủ đích, hoặc dùng integration test với beans nhận cùng recorder.

Nếu runner cần bảo đảm thứ tự **nghiệp vụ quan trọng**, hãy cân nhắc một runner điều phối nhiều bước một cách tường minh. Rải workflow phức tạp qua nhiều runners có thể gây khó quản lý rollback, error handling và retry.

## 14. Khi runner làm việc bất đồng bộ

Một câu lệnh runner như sau có thể nguy hiểm:

~~~java
@Override
public void run(ApplicationArguments args) {
    backgroundService.executeAsync();
}
~~~

Đây là method minh họa trong class có dependency `backgroundService` và async được cấu hình. Nếu `executeAsync()` chỉ submit task rồi trả về, `ApplicationRunner` kết thúc **trước khi công việc hoàn tất**. Spring Boot có thể công bố Ready dù task còn đang xử lý.

Unit test với fake chỉ xác nhận đã **gửi yêu cầu** sang dependency, không tự chứng minh việc async hoàn thành. Muốn kiểm thử completion:

- Cho service trả `CompletableFuture<Result>` hoặc hợp đồng completion tương đương.
- Chờ bằng `get(timeout, ...)`/`join()` khi semantics cho phép, quản lý timeout và cancellation.
- Fake cho phép điều khiển future completion thành công/lỗi.
- Xác minh lỗi async không bị nuốt, và runner có quyết định fail startup hay không.
- Với integration test, không dùng `Thread.sleep(...)` để “đợi đủ lâu”; dùng latch/future có timeout.
- Nếu job cần chắc chắn hoàn tất trước Ready, runner **phải chờ** hoặc hạ tầng readiness phải được thiết kế phản ánh chính xác tiến độ.

Ví dụ minh họa API:

~~~java
CompletableFuture<Result> future =
        service.executeAsync(options);

Result result = future.get(5, TimeUnit.SECONDS);
~~~

Đoạn cần các type/biến/import đã có và chính sách xử lý exception. Không coi đây là file Java độc lập. Tác vụ xử lý theo kiểu fire-and-forget có thể phù hợp nếu đó là yêu cầu thiết kế, nhưng phải công bố rõ “runner đã enqueue” khác với “batch đã thành công”.

## 15. Vì sao ApplicationContextRunner không tương đương @SpringBootTest?

Tên **`ApplicationContextRunner`** dễ gây nhầm với **`ApplicationRunner`**; chúng **không phải một thứ**.

- `org.springframework.boot.test.context.runner.ApplicationContextRunner` là **test utility** dựng một context theo cấu hình và cho phép assert điều kiện, properties và beans.
- `org.springframework.boot.ApplicationRunner` là **startup callback interface** được `SpringApplication` gọi trong chuỗi khởi động.

Một `ApplicationContextRunner` thông thường **chỉ refresh context theo test utility**, không tự tái hiện đầy đủ mọi bước của `SpringApplication.run(...)`, đặc biệt việc gọi các runner và công bố startup/ready events. Nếu muốn kiểm tra method runner trong thử nghiệm dạng này, test phải **gọi nó tường minh** với `DefaultApplicationArguments`, hoặc dùng `@SpringBootTest` khi cần kiểm tra chính vòng đời Boot.

Đừng viết:

~~~java
new ApplicationContextRunner()
    .withUserConfiguration(SomeConfiguration.class)
    .run(context -> {
        // Suy luận "bean runner tồn tại"
        // đồng nghĩa "runner đã được SpringApplication gọi"
        // là kết luận sai.
    });
~~~

Đây là **mã minh họa anti-pattern**, cần class `SomeConfiguration` và import. Điểm sai là **kết luận về lifecycle**, không phải việc tạo context.

## 16. Quan sát lỗi runner mà không làm test bất ổn

Có ba cấp lỗi:

| Vị trí lỗi | Unit test nên kiểm tra | Integration/process test nên kiểm tra |
|---|---|---|
| Input parsing | Exception message/type; gateway không bị gọi | Startup fail nếu input sai trong application thật |
| Dependency execution | Fake ném lỗi; runner không nuốt/retry ngoài hợp đồng | Spring Boot startup failure/cleanup đúng |
| Infrastructure bootstrap | Thường nằm ngoài phạm vi unit runner | Bean wiring/config/datasource failure có kiểm soát |

Với logic production cần exit code phân biệt input/execution, có thể dùng exception types riêng, `ExitCodeGenerator` hoặc `ExitCodeExceptionMapper`. Nhưng hãy **tách hợp đồng exit code khỏi unit test parser** để không phải khởi chạy child JVM cho từng biến thể input.

**Không khẳng định** một `IllegalArgumentException` sẽ luôn trở thành exit code 2 trong Spring Boot chỉ vì tên exception. Cần cấu hình rõ policy nếu muốn mã cụ thể.

**Không chạy integration test thất bại trên database thật** chỉ để “thử failure”, bởi runner khởi động trước test setup và có thể thay đổi dữ liệu ngoài ý muốn. Với lỗi thật, mô phỏng trong fake hoặc dùng một test infrastructure được cô lập.

## 17. Những lỗi kiểm thử thường gặp

**Lỗi 1 — Dùng Spring context cho từng trường hợp parse đơn giản.**

Làm test chậm, nhiều dependency và khó phát hiện lỗi chính xác. Dùng `new DefaultApplicationArguments(...)` và fake trong unit test.

**Lỗi 2 — Chỉ assert exception khi input sai.**

Không đủ: gateway có thể đã chạy trước khi exception xuất hiện. Assert thêm fake không ghi nhận invocation.

**Lỗi 3 — Dùng `@MockBean` rồi stub trong `@BeforeEach` và mong runner dùng stub đó khi startup.**

Quá muộn. Runner đã chạy trong lúc SpringApplication khởi tạo context. Dùng fake/mock cấu hình trong `@TestConfiguration @Bean` trước startup.

**Lỗi 4 — Gọi thủ công `runner.run(...)` trong integration test rồi kết luận Boot tự gọi một lần.**

Lần gọi trong test có thể là lần thứ hai. Quan sát recorder ngay sau startup thay vì gọi lại.

**Lỗi 5 — Không phân biệt `getOptionValues` trả null và list rỗng.**

Có thể gây NPE/IndexOutOfBounds, hoặc chấp nhận option rỗng sai hợp đồng.

**Lỗi 6 — Để runner dùng repository/HTTP client thật trong @SpringBootTest.**

Có thể thay đổi dữ liệu trước khi test method bắt đầu. Fake phải được inject trước startup.

**Lỗi 7 — Coi fake đã được gọi là tác vụ async đã hoàn tất.**

Với fire-and-forget, fake chỉ chứng minh submit, không chứng minh dữ liệu đã commit.

**Lỗi 8 — Nhầm `ApplicationContextRunner` với `ApplicationRunner`.**

Một là utility test context, một là Boot startup callback. Không mặc định context runner gọi lifecycle runners.

**Lỗi 9 — Coi mỗi @Test method là một startup độc lập.**

Spring Test context caching có thể tái sử dụng context; startup runner thường chỉ chạy lúc context được tạo mới.

**Lỗi 10 — Dùng `System.exit(...)` trong runner đem đi test cùng JVM.**

Có thể kết thúc cả Gradle/JUnit process. Tách outcome, dùng process-level test khi cần exit status.

**Lỗi 11 — Chỉ assert log “runner started”.**

Log dễ bị buffering/mix nhiều nguồn. Assert trực tiếp invocation, state, exception và process status khi cần.

**Lỗi 12 — Dùng `Thread.sleep(1000)` để kiểm tra job hoàn tất.**

Flaky dưới CI tải cao; dùng completion contract, latch/future và timeout.

**Lỗi 13 — Bật `@Order` nhưng không test dependency và side effects thực.**

Ordering không thay thế workflow/idempotency; nếu bước sau phụ thuộc bước trước, test state và hợp đồng nghiệp vụ, không chỉ tên runner.

**Lỗi 14 — Bỏ qua input lỗi lặp/unknown option.**

Chọn phần tử đầu tiên hoặc nuốt unknown option có thể gây chạy nhầm batch. Cần allowlist và validation.

## 18. Bài thực hành mở rộng

1. Trong `BatchRunnerTest`, thêm trường hợp `--count=1` và `--count=1000`; xác nhận gateway nhận đúng số ranh giới.
2. Thử `--count=-1`, `--count=3.5` và `--count=999999999999999999`, xác nhận gateway không bị gọi.
3. Sửa contract để hỗ trợ một positional input file, rồi test rõ sự khác biệt với named option.
4. Thêm tham số `--mode=import|validate`, từ chối các mode khác, kiểm tra tất cả validation diễn ra trước gateway.
5. Tạo Mockito mock cho `JobGateway`, cấu hình `doThrow(...)` và assert exception được truyền qua `BatchRunner.run(...)`.
6. Bỏ `@Primary` của `RecordingGateway` ở integration test: giải thích vì sao hai `JobGateway` candidates có thể gây lỗi injection hoặc chọn không như kỳ vọng.
7. Thêm một runner khác có `@Order(20)` và recorder chung; kiểm tra thứ tự runner đúng với policy.
8. Thử bật một `@SpringBootTest` với input sai và quan sát context-load failure; dùng một test class **riêng**, không làm hỏng toàn bộ suite chính.
9. Đổi `JobGateway` sang API trả `CompletableFuture`, fake completion thành công/thất bại và test timeout không dùng sleep.
10. Dùng child process test cho JAR để xác minh startup logs và mã thoát thật khi input invalid, thay vì gọi main chứa `System.exit` trong JUnit.
11. Cấu hình hai integration test classes khác arguments; tìm hiểu vì sao chúng tạo context cache keys khác và có thể gọi runner thêm lần nữa.
12. Đổi production `ConsoleJobGateway` thành một adapter ngoài thật trong môi trường staging; đảm bảo unit/integration suite vẫn hoàn toàn tách khỏi endpoint thật.

## 19. Checklist trước khi review một runner và test suite

- Runner implement đúng `ApplicationRunner`, nhận `ApplicationArguments` và có constructor injection.
- Parse/validate từng option trước khi gọi nghiệp vụ; phân biệt thiếu, rỗng, lặp, sai kiểu, sai miền và unknown option.
- Dependency có interface/abstraction phù hợp; test có thể inject fake/mock **không cần Spring context**.
- Unit tests kiểm tra cả kết quả **và việc không có side effect** khi invalid input.
- Lỗi dependency được truyền ra hoặc ánh xạ theo hợp đồng, không bị log rồi nuốt.
- `DefaultApplicationArguments` dùng đúng cú pháp CLI, không nhầm option và positional.
- `@SpringBootTest(args=...)` dùng để kiểm chứng runner tự được Boot gọi trong startup.
- Fake được cung cấp bằng `@TestConfiguration @Bean @Primary` **trước khi runner chạy**.
- Không stub mock trong test method để kỳ vọng thay đổi lần gọi đã xảy ra khi startup.
- Không gọi `run(...)` thủ công trong test đang kiểm chứng auto-invocation.
- Test startup không mở DB/network hoặc thực thi job thật không thể rollback.
- Cần hiểu context cache, thứ tự runners, nhiều contexts và nhiều replicas.
- Job async có completion/timeout test rõ ràng, không dùng sleep tùy hứng.
- Khi cần exit code, test subprocess riêng, không kết thúc test JVM bằng `System.exit`.
- Có một integration test chứng minh wiring + lifecycle; phần lớn cases khác là unit tests nhanh, độc lập.

### Tài liệu chính thức

- Spring Boot 3.3 — `ApplicationRunner` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3 — `ApplicationArguments` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3 — `DefaultApplicationArguments` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html
- Spring Boot 3.3 — Testing Spring Boot Applications (arguments, `@SpringBootTest`, `@MockBean`): https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — `SpringBootTest` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/SpringBootTest.html
- Spring Boot 3.3 — SpringApplication và runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — `ApplicationContextRunner` test utility: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- JUnit 5 — Writing Tests: https://junit.org/junit5/docs/current/user-guide/

**Kết luận:** kiểm thử `ApplicationRunner` không cần mở Spring context cho mọi trường hợp. Dùng `DefaultApplicationArguments` với **fake/mock dependency** để xác minh parse, validation, số lần gọi và failure một cách nhanh, deterministic. Sau đó dùng **một integration test `@SpringBootTest(args=...)` với fake đã đăng ký trước startup** để chứng minh Spring Boot thực sự tự gọi runner và inject đúng dependency. Phân biệt rõ “test tự gọi `run(...)`” với “framework gọi runner trong startup”, tránh side effects thật, mock cấu hình quá muộn và test bị ảnh hưởng bởi context caching.

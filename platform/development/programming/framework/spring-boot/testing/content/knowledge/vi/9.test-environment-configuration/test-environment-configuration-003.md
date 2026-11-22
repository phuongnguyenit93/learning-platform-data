# `@Import` để bổ sung cấu hình hoặc bean cần thiết cho môi trường test Spring Boot

## Mục tiêu

Khi viết test Spring Boot, có lúc ứng dụng cần một bean hoặc một nhóm cấu hình **chỉ phục vụ phép thử**: đồng hồ cố định, adapter giả lập cho dịch vụ ngoài, bộ chuyển đổi JSON có cấu hình chuyên biệt, policy dành cho một test case hoặc collaborator của controller trong một MVC slice. Annotation `@Import` cho phép **đưa một class cấu hình hoặc class được Spring quản lý vào ApplicationContext của test** theo cách tường minh, thay vì mở rộng component scan tùy tiện hay chỉnh cấu hình production chỉ để test chạy.

Sau bài này, bạn có thể:

- Hiểu `@Import` thêm gì vào Spring context và phân biệt việc **thêm bean definition**, **chọn bean khi inject** và **thay thế bean**.
- Kết hợp `@Import` với `@TestConfiguration` và `@SpringBootTest` hoặc test slice phù hợp.
- Viết một ví dụ Java 17 + Spring Boot + JUnit Jupiter **chạy được**: giữ bean `Clock` production, import một `Clock` cố định cho test, dùng `@Primary` để chọn bean thử nghiệm.
- Phân biệt `@Import`, `@ContextConfiguration`, `@TestPropertySource`, `@ActiveProfiles`, component scanning và test mock.
- Chẩn đoán `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException`, lỗi trùng bean name, context khởi tạo sai hoặc test dùng nhầm cấu hình.
- Giữ test nhỏ, dễ tái lập, tránh đưa test bean vào production hoặc vô tình biến một test slice thành gần như full application.

Bài này tập trung vào **cấu hình môi trường test bằng `@Import`**. Nội dung không nhằm thay thế toàn bộ hướng dẫn về Spring configuration, dependency injection hay các loại integration test khác.

## 1. Vấn đề: test thiếu bean hoặc cần một cấu hình khác

Giả sử một service tính thời hạn bằng `Instant.now()`. Nếu gọi trực tiếp đồng hồ hệ thống, bài test sẽ phụ thuộc thời gian thật, khó kiểm các mốc chính xác như “vừa hết hạn”. Một cách thiết kế dễ kiểm thử là **tiêm `java.time.Clock` vào service**:

~~~java
@Service
public class DeadlineService {
    private final Clock clock;

    public DeadlineService(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant deadline) {
        return !clock.instant().isBefore(deadline);
    }
}
~~~

Đây là **đoạn minh họa rút gọn**, chưa đầy đủ imports và xử lý input; phiên bản runnable ở mục 4. Với production, ứng dụng có thể cấu hình `Clock.systemUTC()`. Trong test, ta muốn `Clock.fixed(...)` tại một thời điểm đã biết. Câu hỏi không phải “làm sao làm giả `Instant.now()`?”, mà là “làm sao để **Spring container của test chọn Clock cố định**?”.

Một cách làm dễ hiểu là:

~~~text
Spring Boot application context cho test
    |
    +-- @SpringBootApplication và các @Bean production
    |       +-- systemClock : Clock
    |       +-- deadlineService : DeadlineService
    |
    +-- @Import(FixedClockTestConfig.class)
    |       +-- fixedTestClock : Clock (@Primary)
    |
    +-- autowire DeadlineService(Clock)
            |
            v
      fixedTestClock được chọn vì @Primary
            |
            v
      Assertion tại thời điểm cố định, không phụ thuộc đồng hồ thật
~~~

`@Import` **đưa định nghĩa cấu hình/bean vào context**. `@Primary` **giải quyết việc chọn một bean khi có nhiều candidate cùng type**. Hai annotation phục vụ hai công việc khác nhau, cần hiểu riêng.

## 2. `@Import` thực chất là gì?

`@Import` thuộc Spring Framework, được import bằng:

~~~java
import org.springframework.context.annotation.Import;
~~~

Nó có thể tham chiếu một hoặc nhiều class, chẳng hạn:

~~~java
@Import({FixedClockTestConfig.class, StubExternalServiceConfig.class})
class SomeSpringTest {
    // Các class được import sẽ đóng góp cấu hình/bean cho context.
}
~~~

Đoạn trên **chỉ minh họa cú pháp**, không phải class chạy độc lập vì các class và phần setup Spring test chưa được định nghĩa.

Về ý nghĩa:

- Nếu class là `@Configuration`, Spring xử lý các `@Bean`, `@Import` và những khai báo cấu hình bên trong class đó.
- Spring cũng hỗ trợ import một số class thông thường như component, cùng các cơ chế nâng cao như `ImportSelector` và `ImportBeanDefinitionRegistrar`. Khi học cách bổ sung test bean, phần lớn trường hợp chỉ cần **import một `@Configuration`/`@TestConfiguration` tường minh**.
- `@Import` có thể được đặt trên một class cấu hình, hoặc trên test class trong các bài kiểm thử Spring Boot được bootstrap tương ứng.
- `@Import` không phải annotation JUnit; đặt nó trên một class Java thuần **không tự tạo Spring context**. Cần có cơ chế test bootstrap, ví dụ `@SpringBootTest`, `@WebMvcTest` hoặc cấu hình Spring TestContext phù hợp.

### `@Import` không làm những việc sau

1. **Không tự thêm dependency vào Gradle classpath.** Nếu bean cần một thư viện bên ngoài, bạn vẫn phải khai báo dependency thích hợp.
2. **Không tự khởi động Spring Boot application.** Đó là trách nhiệm của annotation/framework test bootstrap.
3. **Không có nghĩa ghi đè một bean đã tồn tại.** Nếu import một bean cùng type, context có thể có **hai candidate** và injection bị mơ hồ; nếu cùng **tên bean**, có thể xảy ra lỗi bean-definition override.
4. **Không tự mock mọi dependency.** Bean được import mặc định là bean thật (hoặc test double do bạn tự tạo bên trong config).
5. **Không đảm bảo test nhỏ và nhanh.** Một config được import có thể kéo theo nhiều bean, `@ComponentScan` rộng, listener và hạ tầng ngoài.
6. **Không tự áp dụng `application-test.yml`** chỉ vì có chữ “test” trong tên class; profile và property sources phải được cấu hình theo hệ thống đang dùng.

## 3. Những công cụ thường đi cùng `@Import`

| Công cụ | Làm gì? | Tình huống phù hợp |
| --- | --- | --- |
| `@Import(TestConfig.class)` | Đưa config/bean definitions đã chỉ định vào context | Test cần thêm một bean hoặc nhóm bean |
| `@TestConfiguration` (Spring Boot) | Đánh dấu cấu hình chuyên cho test | Chứa `@Bean` tạo Clock/fake/adapter test |
| `@Configuration` | Khai báo cấu hình Spring thông thường | Cấu hình dùng chung ở production hoặc module Spring |
| `@Primary` | Ưu tiên bean khi injection theo type có nhiều candidate | Cần một bean test được chọn thay vì bean production |
| `@Qualifier("...")` | Chọn candidate cụ thể tại điểm injection | Cần chọn tên bean xác định, không muốn thay ưu tiên toàn context |
| `@TestPropertySource` | Bổ sung property values/files cho Spring TestContext | Muốn đổi property trong phạm vi kiểm thử |
| `@ActiveProfiles("test")` | Kích hoạt Spring profile trong test | Muốn bean/property có điều kiện theo profile |
| `@SpringBootTest` | Bootstrap Spring Boot application context | Kiểm phối hợp các bean và cấu hình Boot |
| `@WebMvcTest` | Bootstrap MVC slice trong Boot | Kiểm controller/request/JSON mà không mở toàn ứng dụng |
| Test mock/fake phù hợp | Thay collaborator không cần chạy thật | Cô lập gọi mạng, email, message broker, DB |

**Ba câu hỏi riêng:**

- *Bean có được đăng ký không?* → xem `@Import`, `@Bean`, component scan hoặc `@MockBean`/cơ chế mock theo phiên bản.
- *Bean nào được chọn để tiêm?* → xem type, `@Primary`, `@Qualifier`, điều kiện/config của dependency.
- *Có cần khởi động Boot không?* → xem `@SpringBootTest`, test slice hoặc Spring Framework TestContext thuần.

Ví dụ một service nhận `Clock` qua constructor không quan tâm Clock được tạo từ `@Bean` nào; nó chỉ yêu cầu một bean phù hợp. Phần **composition** nằm ở Spring configuration. Điều này khiến logic service dễ kiểm bằng unit test và khiến test có thể thay lựa chọn dependency mà không sửa mã nghiệp vụ.

## 4. Ví dụ Java 17/Spring Boot chạy được: import Clock test bằng `@TestConfiguration`

Ví dụ này sử dụng **Spring Boot 3.3.5**, Gradle Groovy DSL và Java 17. Đây là bộ phiên bản minh họa để ghép thành một dự án chạy độc lập; trong repository đang dùng Spring Boot phiên bản khác, hãy giữ bộ dependencies/Gradle theo BOM và chính sách của dự án. Mục tiêu là thấy rõ `@Import` thêm bean, `@Primary` chọn bean và test có kết quả xác định.

### 4.1. Hợp đồng nghiệp vụ

Service `DeadlineService` kiểm tra một thời hạn:

- Với một `deadline` trước thời điểm hiện tại, `expired(deadline)` trả `true`.
- Với `deadline` **đúng bằng** thời điểm hiện tại, cũng trả `true`.
- Với `deadline` ở tương lai, trả `false`.
- `reminderAfter(delay)` trả thời điểm hiện tại cộng một `Duration` không âm.
- `delay` âm hoặc `null` bị từ chối bằng `IllegalArgumentException`.

Giả sử đồng hồ test cố định ở **2025-03-01T10:15:30Z**. Vì vậy thời hạn `2025-03-01T10:15:30Z` phải được xem là hết hạn, còn reminder sau 15 phút phải là **2025-03-01T10:30:30Z**. Các kết quả này lấy từ yêu cầu, không tính expected bằng chính service đang được kiểm thử.

### 4.2. Cấu trúc dự án

~~~text
import-test-clock-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/
    │   ├── DemoApplication.java
    │   └── DeadlineService.java
    └── test/java/com/example/testing/
        ├── FixedClockTestConfig.java
        └── DeadlineServiceImportTest.java
~~~

Các script/tệp Gradle Wrapper được tạo bằng Gradle hoặc lấy từ project đã cấu hình, không viết nội dung nhị phân `gradle-wrapper.jar` bằng tay.

**`settings.gradle`**

~~~groovy
rootProject.name = 'import-test-clock-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Giải thích:

- `spring-boot-starter` cung cấp core container, Boot auto-configuration và logging; **không cần `spring-boot-starter-web`** vì ví dụ không kiểm HTTP.
- `spring-boot-starter-test` cung cấp Spring TestContext, JUnit Jupiter và các thư viện test liên quan.
- `junit-platform-launcher` cho môi trường Gradle/JUnit Platform. Phiên bản dependency được quản lý bởi hệ thống BOM/dependency management của Spring Boot ở ví dụ.
- `useJUnitPlatform()` giúp Gradle test task tìm và chạy các method `org.junit.jupiter.api.Test`.
- Java 17 toolchain yêu cầu JDK 17 có sẵn hoặc cơ chế provisioning thích hợp; Wrapper **không tự cài JDK**.

### 4.3. Ứng dụng production có Clock thật

**`src/main/java/com/example/testing/DemoApplication.java`**

~~~java
package com.example.testing;

import java.time.Clock;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    @Bean
    public Clock systemClock() {
        return Clock.systemUTC();
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@Bean systemClock()` tạo Clock production lấy thời gian thực theo UTC. Việc đặt bean này trong `DemoApplication` làm ví dụ ngắn; trong một ứng dụng lớn, có thể tách sang `TimeConfiguration` riêng để dễ tổ chức.

Quan trọng: **production vẫn có Clock hợp lệ**, nên ứng dụng không phụ thuộc vào việc import test config mới khởi động được. Test sẽ **thêm** một bean Clock cố định và cho Spring ưu tiên nó. Không sửa `systemClock()` trong production chỉ vì bài test muốn thời gian giả.

**`src/main/java/com/example/testing/DeadlineService.java`**

~~~java
package com.example.testing;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public final class DeadlineService {

    private final Clock clock;

    public DeadlineService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean expired(Instant deadline) {
        Objects.requireNonNull(deadline, "deadline");
        return !clock.instant().isBefore(deadline);
    }

    public Instant reminderAfter(Duration delay) {
        if (delay == null || delay.isNegative()) {
            throw new IllegalArgumentException(
                    "delay must be non-negative");
        }
        return clock.instant().plus(delay);
    }
}
~~~

Service sử dụng **constructor injection**: Spring chọn một `Clock` và đưa vào `DeadlineService` khi tạo bean. Mã service là Java thuần ngoài annotation `@Service` và **không có `Instant.now()` gọi trực tiếp**, nên ta có thể kiểm với Clock cố định.

Biểu thức `!clock.instant().isBefore(deadline)` có nghĩa “thời điểm hiện tại không còn trước hạn” tức **hiện tại >= deadline**. Đây là ranh giới quan trọng: khi hai `Instant` bằng nhau, method trả `true`.

### 4.4. Cấu hình chỉ dành cho test

**`src/test/java/com/example/testing/FixedClockTestConfig.java`**

~~~java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
public class FixedClockTestConfig {

    @Bean
    @Primary
    public Clock fixedTestClock() {
        return Clock.fixed(
                Instant.parse("2025-03-01T10:15:30Z"),
                ZoneOffset.UTC);
    }
}
~~~

Ba phần có vai trò khác nhau:

- **`@TestConfiguration`** đánh dấu class cấu hình dùng cho kiểm thử Spring Boot. Một class `@TestConfiguration` top-level dưới `src/test/java` không được component scan mặc định của Boot tự quét vào ứng dụng; ở đây ta **import rõ ràng**.
- **`@Bean`** đăng ký một bean `Clock` tên `fixedTestClock` với thời điểm cố định.
- **`@Primary`** làm bean đó được ưu tiên khi Spring cần tiêm `Clock` theo type, trong khi bean `systemClock` của production vẫn tồn tại.

Lưu ý `@Primary` **không thay thế/mutate bean `systemClock`**. Nếu code dùng `@Qualifier("systemClock")` hoặc yêu cầu bean bằng tên `systemClock`, nó vẫn nhận Clock thật. Trong một ứng dụng có nhiều qualifier hoặc điều kiện phức tạp, cần xem đúng điểm injection chứ không coi `@Primary` là cơ chế override toàn cục.

`proxyBeanMethods = false` phù hợp vì test config không gọi qua lại các `@Bean` method để dựa vào proxy. Khi các phương thức `@Bean` trực tiếp gọi nhau và bạn dựa vào singleton interception, cần hiểu rõ cơ chế proxy thay vì sao chép thuộc tính này máy móc.

### 4.5. Test import config và assert hành vi

**`src/test/java/com/example/testing/DeadlineServiceImportTest.java`**

~~~java
package com.example.testing;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(FixedClockTestConfig.class)
class DeadlineServiceImportTest {

    private static final Instant FIXED_NOW =
            Instant.parse("2025-03-01T10:15:30Z");

    @Autowired
    private DeadlineService service;

    @Autowired
    private Clock chosenClock;

    @Autowired
    private ApplicationContext context;

    @Test
    void importedPrimaryClockIsSelected() {
        // Hai Clock bean có mặt, nhưng injection theo type chọn @Primary.
        assertTrue(context.containsBean("systemClock"));
        assertTrue(context.containsBean("fixedTestClock"));

        assertEquals(FIXED_NOW, chosenClock.instant());
        assertSame(context.getBean(DeadlineService.class), service);
    }

    @Test
    void deadlineBeforeCurrentTimeIsExpired() {
        Instant earlier = Instant.parse("2025-03-01T10:15:29Z");

        assertTrue(service.expired(earlier));
    }

    @Test
    void deadlineEqualToCurrentTimeIsExpired() {
        assertTrue(service.expired(FIXED_NOW));
    }

    @Test
    void futureDeadlineIsNotExpired() {
        Instant later = Instant.parse("2025-03-01T10:15:31Z");

        assertFalse(service.expired(later));
    }

    @Test
    void reminderAfterFifteenMinutesIsDeterministic() {
        Instant actual = service.reminderAfter(
                Duration.ofMinutes(15));

        assertEquals(
                Instant.parse("2025-03-01T10:30:30Z"),
                actual);
    }

    @Test
    void negativeDurationIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> service.reminderAfter(Duration.ofMinutes(-1)));
    }

    @Test
    void nullDurationIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> service.reminderAfter(null));
    }
}
~~~

**Điều test chứng minh:**

1. Context **có cả `systemClock` và `fixedTestClock`**, nên đây là trường hợp *bổ sung bean* chứ không ghi đè bean theo tên.
2. `chosenClock.instant()` bằng `FIXED_NOW`, chứng minh candidate được tiêm theo type là Clock test (nhờ `@Primary`).
3. `DeadlineService` là bean mà Spring tạo; `assertSame` kiểm instance được inject và lấy từ `ApplicationContext` là cùng bean singleton.
4. Ba test thời hạn bảo vệ cả trước–đúng bằng–sau mốc thời gian.
5. Test reminder bảo vệ phép cộng Duration từ thời điểm cố định.
6. Hai test lỗi bảo vệ việc từ chối delay âm hoặc null.

**Vì sao dùng `@SpringBootTest`?** Ta muốn kiểm **cấu hình application context và dependency injection của Boot** khi kết hợp config production với config test. `@SpringBootTest(webEnvironment = NONE)` không cần mở server HTTP. Nếu chỉ kiểm riêng thuật toán của `DeadlineService`, có thể tạo bằng `new DeadlineService(Clock.fixed(...))` trong một unit test Java thuần và **không cần Spring context**.

### 4.6. Chạy và kiểm tra kết quả

Từ thư mục project có Gradle Wrapper:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng class:

~~~bash
./gradlew test --tests 'com.example.testing.DeadlineServiceImportTest'
~~~

Với mã và cấu hình trên, có **7 method `@Test`**, mỗi method chạy một lần; kỳ vọng **7 test pass**. Không có `System.out.println` trong test, nên **không có dòng stdout nghiệp vụ cố định**. Gradle có thể báo `BUILD SUCCESSFUL` khi mọi task thành công hoặc `UP-TO-DATE` khi sử dụng kết quả đã có. Kiểm số test thực thi từ:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.testing.DeadlineServiceImportTest.xml
~~~

Nếu cần chạy lại do nghi cache, dùng `./gradlew test --rerun-tasks`. Với repo multi-project, đường dẫn build report thuộc **module chứa test**.

Để có Wrapper khi tạo dự án mới, cần một Gradle đã cài hợp lệ để bootstrap, ví dụ:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó lưu `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle/wrapper/gradle-wrapper.properties` trong repository. Version 8.8 chỉ là ví dụ tương thích cho demo Java 17/Boot 3.3.x; ở dự án thực, theo Gradle Wrapper và compatibility matrix mà team đang sử dụng.

## 5. Phân biệt import **thêm bean**, **thay lựa chọn** và **thay implementation**

Đây là phần dễ hiểu nhầm nhất của bài.

### 5.1. Thêm bean chưa tồn tại

Nếu một interface `PaymentGateway` chưa có bean trong một context thử nghiệm, có thể import một cấu hình tạo fake:

~~~java
@TestConfiguration
class FakePaymentGatewayConfig {

    @Bean
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }
}
~~~

và đặt `@Import(FakePaymentGatewayConfig.class)` trên test. Snippet **chỉ minh họa cách khai báo**; `PaymentGateway`/`InMemoryPaymentGateway` phải được định nghĩa trong codebase. Nó phù hợp khi test chỉ cần kiểm use case tương tác với gateway giả và không muốn gọi mạng ngoài.

Nếu **ứng dụng production thực sự cần PaymentGateway** nhưng không có bean production, việc test import fake để chạy được **không chứng minh** rằng ứng dụng sẽ khởi động trong môi trường thật. Phải có test/integration khác kiểm wiring của adapter thật khi đó là yêu cầu.

### 5.2. Có nhiều bean cùng type

Trong ví dụ runnable, `Clock` có hai bean:

~~~text
Clock
  ├── systemClock     (@Bean production)
  └── fixedTestClock  (@Bean @Primary từ @Import)
~~~

Khi Spring cần tiêm `Clock` mà không có qualifier, nó chọn bean `@Primary`. Nếu **không** có `@Primary` hay một quy tắc phân giải phù hợp, Spring có thể báo `NoUniqueBeanDefinitionException` vì không biết chọn Clock nào.

Một lựa chọn khác là dùng `@Qualifier` tại điểm injection khi muốn gọi **bean cụ thể**, ví dụ:

~~~java
public SomeService(@Qualifier("systemClock") Clock clock) {
    this.clock = clock;
}
~~~

Snippet trên không phải class chạy độc lập. `@Qualifier` có ý nghĩa khác `@Primary`: nó **gắn yêu cầu cho một điểm tiêm**, còn `@Primary` là ưu tiên của bean khi cần phân giải nhiều candidate theo type. Không thêm `@Primary` bừa bãi lên nhiều bean cùng type; có thể khiến lựa chọn vẫn mơ hồ.

### 5.3. Trùng *bean name* không giống trùng *bean type*

Đừng tạo hai method `@Bean` cùng tên `clock` trong cùng application context rồi kỳ vọng `@Primary` giải quyết. Trường hợp trùng tên bean definition liên quan đến **bean overriding**, thường bị Spring Boot chặn mặc định; có thể báo lỗi dạng `BeanDefinitionOverrideException`.

Giải pháp ưu tiên là **đặt tên khác nhau** (`systemClock`/`fixedTestClock`) và dùng `@Primary` hoặc `@Qualifier`, hoặc thay thế bằng cơ chế test mock/conditional configuration phù hợp với thiết kế. Không bật `spring.main.allow-bean-definition-overriding=true` chỉ để test qua lỗi cấu hình nếu chưa hiểu hậu quả.

### 5.4. Khi muốn “ghi đè” một dependency được mock

Nếu mục tiêu test không cần thực hiện logic của collaborator mà cần quyết định nó trả gì, một test mock đôi khi phù hợp hơn bean thật:

- Với Spring Boot 3.3.x, dự án có thể dùng `@MockBean` theo API của phiên bản đó.
- Những phiên bản Spring Framework/Spring Boot mới có cơ chế annotation mock test khác; hãy theo bộ dependency và API của dự án, không copy annotation trộn giữa các phiên bản.
- `@Import` một fake bean hữu ích khi fake có hành vi thực, ổn định và được tái sử dụng trong nhiều test; nó **khác** việc tự động tạo Mockito mock.

Chọn công cụ bằng **điều cần chứng minh**. `Clock.fixed` là đối tượng Java thật có hành vi xác định, vì vậy import một bean @Primary thường rõ ràng hơn mock static `Instant.now()`. Một payment gateway với hàng chục tình huống lỗi có thể phù hợp với Mockito stub ở ranh giới, hoặc fake có API điều khiển trạng thái được thiết kế tốt.

## 6. `@TestConfiguration`: nested và top-level

Spring Boot có annotation `org.springframework.boot.test.context.TestConfiguration` để khai báo cấu hình chuyên dụng cho test.

**Top-level `@TestConfiguration`**, như `FixedClockTestConfig`, được đặt ở `src/test/java` và **không tự bị component scan mặc định đưa vào toàn bộ test context**. Muốn dùng ở một test nhất định, hãy import tường minh: `@Import(FixedClockTestConfig.class)`. Cách này cho phép test A dùng Clock cố định A, test B dùng cấu hình khác mà không rò bean toàn cục.

**Nested static `@TestConfiguration`** cũng có thể dùng bên trong test class, ví dụ:

~~~java
@SpringBootTest
class SomeBootTest {

    @TestConfiguration
    static class ExtraTestBeans {
        @Bean
        FeatureFlagClient featureFlagClient() {
            return new FixedFeatureFlagClient(true);
        }
    }
}
~~~

Đây là **snippet minh họa**; `FeatureFlagClient`, `FixedFeatureFlagClient` và setup test chưa được cung cấp. Với Spring Boot test bootstrap, nested `@TestConfiguration` thường được bổ sung bên cạnh cấu hình ứng dụng chính; khi muốn phạm vi tường minh và tái sử dụng giữa nhiều class, top-level `@TestConfiguration` cộng `@Import` dễ nhìn hơn.

Đừng nhầm với nested `@Configuration` thông thường: Spring Boot test bootstrap có thể xem nested `@Configuration` như cấu hình thay cho cấu hình ứng dụng chính được tìm tự động. Vì vậy, khi chỉ muốn **thêm** bean test mà vẫn giữ application config, ưu tiên `@TestConfiguration` hoặc ghi rõ classes phù hợp.

**Không đưa `@TestConfiguration` vào `src/main/java`** để “dùng chung” với production. Đặt test-only config trong test source set và giới hạn import giúp tránh fake adapter hoặc dữ liệu kiểm thử xuất hiện trong artifact ứng dụng thật.

## 7. `@Import` với các kiểu test Spring Boot khác nhau

### 7.1. `@SpringBootTest`: kiểm bean wiring/behavior có Boot context

Ví dụ runnable ở mục 4 dùng:

~~~java
@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(FixedClockTestConfig.class)
class DeadlineServiceImportTest {
    // ...
}
~~~

Tức là tải app context từ `DemoApplication`, sau đó bổ sung test bean từ config import. Phù hợp khi muốn chứng minh bean DI phối hợp trong môi trường Spring Boot tương đối đầy đủ. Tuy nhiên, nếu ứng dụng có JPA, message broker, external services, loading full context có thể tốn thời gian hoặc cần nhiều setup; đừng chọn `@SpringBootTest` chỉ vì muốn thêm một Clock đơn giản mà không có mục tiêu cần Boot context.

### 7.2. `@WebMvcTest`: bổ sung bean cho MVC slice

Nếu chỉ kiểm một controller, `@WebMvcTest(InvoiceController.class)` thường chỉ tải thành phần MVC được lọc. Nếu controller hoặc lớp MVC cần một bean cụ thể, import một test config phù hợp:

~~~java
@WebMvcTest(InvoiceController.class)
@Import(InvoiceWebTestConfig.class)
class InvoiceControllerTest {
    // @Autowired MockMvc; @Test...
}
~~~

Snippet này **chỉ minh họa**, không phải mã chạy độc lập vì controller/config chưa được định nghĩa. Import test config giúp cung cấp một dependency hoặc custom MVC component **có chủ đích**. Nó **không** tự làm mọi service, repository, database và workflow của ứng dụng được kiểm như một integration test đầy đủ.

Nếu import một `@Configuration` có `@ComponentScan` bao trùm cả application package, bạn có thể vô tình kéo vào nhiều bean và phá mục đích của MVC slice. Chọn class config nhỏ, không import whole application configuration một cách tùy tiện. Nếu Spring Security đang hoạt động, MockMvc có thể cần mock user hoặc cấu hình security test phù hợp; không tự tắt bảo mật chỉ vì status trả 401/403.

### 7.3. `@DataJpaTest`: có thể bổ sung cấu hình nhỏ nhưng phải giữ mục tiêu slice

Nếu repository test cần entity listener/converter/config nhỏ, `@Import` có thể thêm bean phù hợp. Nhưng nó không thay thế việc cấu hình DataSource, transaction và cơ chế persistence thực. Với JPA, test cần chứng minh mapping/query/constraint thì phải chạy đúng stack dữ liệu; đừng import một mock repository rồi kết luận SQL hoạt động.

### 7.4. Spring Framework TestContext thuần, không dùng Boot

Nếu module không có Boot, có thể viết một config root để import config phụ trợ:

~~~java
@Configuration
@Import(SharedTestBeans.class)
class RootSpringTestConfig {
}

@SpringJUnitConfig(RootSpringTestConfig.class)
class PureSpringWiringTest {
    // @Autowired ...; @Test ...
}
~~~

Đây là snippet cấu hình minh họa, cần định nghĩa `SharedTestBeans` và các imports. Trong trường hợp này, `@SpringJUnitConfig` kích hoạt SpringExtension và context từ `RootSpringTestConfig`, còn `@Import` được xử lý trong quá trình Spring đăng ký các bean definitions từ config root. Khác với `@SpringBootTest`, bạn **không** tự nhận Boot auto-configuration. Chọn đúng cơ chế bootstrap trước rồi mới bổ sung bean.

## 8. `@Import` và property/profile: không phải một thứ

Có những bài test chỉ cần đổi một giá trị cấu hình, **không cần một bean mới**. Ví dụ muốn kiểm discount rate 10% thay vì 20%, có thể dùng `@TestPropertySource(properties = "pricing.discount=0.10")`, hoặc `@SpringBootTest(properties = "...")` trong Boot test, tùy tình huống. Một Bean đọc Environment/properties sẽ nhận giá trị tương ứng.

Nếu production định nghĩa hai implementation theo `@Profile("prod")` và `@Profile("test")`, có thể dùng `@ActiveProfiles("test")` để kích hoạt implementation thích hợp; không nhất thiết phải import thêm config. Tuy nhiên profile không thay thế bean registration: nếu bean hoàn toàn không được khai báo trong phạm vi context đang tải, `@ActiveProfiles("test")` cũng không tự sáng tạo ra nó.

| Nhu cầu | Hướng thử trước |
| --- | --- |
| Thay giá trị một property đã được bean đọc | `@TestPropertySource` hoặc Spring Boot test properties |
| Chọn bean đã khai báo theo profile | `@ActiveProfiles` |
| Thêm bean không có trong test context | `@Import(TestConfig.class)` |
| Thêm bean test cùng type và ưu tiên bean test | `@Import` + `@Primary`, hoặc cơ chế mock phù hợp |
| Chỉ cần ép một bean cụ thể tại một constructor | `@Qualifier` trên injection point |
| Cần kiểm wiring thật của cả application | Boot integration test thích hợp |
| Chỉ cần kiểm logic thuần Java | Tạo object trực tiếp, không mở Spring context |

**Đừng lạm dụng `@Import` chỉ để tránh hiểu cách cấu hình hiện tại hoạt động.** Test config bổ sung phải được đặt tên và comment rõ mục đích, để người review hiểu bean nào là production và bean nào chỉ xuất hiện ở test.

## 9. TestContext caching, context pollution và độc lập dữ liệu

Spring TestContext có thể cache `ApplicationContext` giữa các test class có tập cấu hình tương đương nhằm giảm chi phí khởi tạo. Những khác biệt như imported configurations, profiles, properties hoặc test context customizers **có thể tạo cache key khác nhau**, dẫn đến tải thêm context.

Điều này có hai hệ quả:

1. **Hiệu năng:** import hàng chục config khác nhau cho từng test làm suite phát sinh nhiều context và tốn thời gian. Hãy gom các test có cùng nhu cầu cấu hình khi hợp lý, nhưng đừng hy sinh test isolation chỉ để cache được nhiều.
2. **Độc lập:** singleton fake có trạng thái mutable được tạo trong context cache có thể sống giữa các test và gây lây dữ liệu. Thiết kế fake có cơ chế reset, fixture riêng hoặc cấu hình scope phù hợp; chỉ dùng `@DirtiesContext` khi thực sự cần loại bỏ context bị làm bẩn.

Ví dụ `Clock.fixed` trong project runnable là **stateless và bất biến**, nên việc chia sẻ context không làm test phụ thuộc thứ tự chạy. Nếu import một `InMemoryOrderRepository` giữ danh sách mutable, test A thêm order rồi test B mong danh sách rỗng có thể fail khi chạy cả suite; phải dọn dữ liệu trong fixture, không coi việc Spring cache context là bug.

Một rủi ro khác là **context pollution**: test chỉ nhằm kiểm MVC nhưng import cấu hình chung kéo theo nhiều bean ngoài phạm vi, tạo xung đột profile/transaction/security. Một file `TestConfig` lớn với mọi fake của hệ thống có thể tiện ban đầu nhưng khiến các test khó biết thật giả ở đâu. Thường nên chia config theo trách nhiệm: `FixedClockTestConfig`, `FakeMailGatewayConfig`, `TestJsonConfig`… và chỉ import phần cần thiết.

## 10. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách chẩn đoán/sửa |
| --- | --- | --- |
| `No qualifying bean of type…` | Bean chưa được tạo hoặc config chưa được import | Kiểm `@Import`, `@Bean`, package/config class, điều kiện/profile |
| `NoUniqueBeanDefinitionException` | Nhiều bean cùng type, không có cách chọn duy nhất | Dùng `@Primary`/`@Qualifier` có chủ đích, tránh import bean thừa |
| `BeanDefinitionOverrideException` | Config mới khai báo bean trùng **tên** với bean hiện có | Đổi tên bean hoặc dùng cơ chế thay thế thích hợp; đừng bật overriding mù quáng |
| Test dùng nhầm Clock thật và bị flaky | Clock test không được inject, sai `@Primary`/qualifier | Kiểm candidate được chọn; assert `clock.instant()` trong test |
| `@Import` có vẻ không hoạt động | Test không bootstrap Spring context hoặc import sai class | Đặt annotation trong test Spring Boot/TestContext phù hợp, xem root cause |
| `Failed to load ApplicationContext` | Bean constructor lỗi, dependency thiếu, config import quá rộng | Đọc nguyên nhân gốc trong stack trace; thu nhỏ imports |
| Test bean “lọt” vào các test khác | Config bị scan rộng hoặc import quá nhiều nơi | Dùng top-level `@TestConfiguration` test-only, import tường minh |
| MVC slice tải quá nhiều bean | Import config có component scan rộng | Giới hạn config và wiring controller đúng phạm vi |
| Test fail khi thêm `@Primary` | Có nhiều primary candidate hoặc `@Qualifier` vẫn trỏ bean khác | Kiểm cách Spring phân giải bean tại injection point |
| Context chậm khi chạy cả suite | Nhiều tổ hợp imports/profiles/properties hoặc SpringBootTest không cần thiết | Giảm biến thể context, dùng unit/slice test khi phù hợp |
| Test Spring Boot pass nhưng production fail | Test import fake làm lộ khoảng trống production wiring | Bổ sung smoke/integration test khởi tạo cấu hình production |
| `@TestConfiguration` không được phát hiện | Dùng top-level test config nhưng quên `@Import` | Import tường minh từ test |
| JUnit báo 0 test hoặc `NO-SOURCE` | Test class không ở source set hoặc thiếu engine/`useJUnitPlatform()` | Kiểm đường dẫn, JUnit Jupiter import và Gradle test task |
| Test dùng Boot-only annotation ở module Spring thuần | Chưa có `spring-boot-test` trên classpath hoặc không dùng Boot | Chọn `@SpringJUnitConfig`/`@ContextConfiguration` và import config vào Spring root |

### Cách khoanh vùng nhanh khi lỗi

- **Bước 1:** Xác nhận JUnit chạy đến test chưa. Nếu chưa, kiểm Gradle/JUnit Platform/imports trước; chưa vội thêm Spring config.
- **Bước 2:** Nếu context không load, đọc dòng root cause sâu trong `Failed to load ApplicationContext`.
- **Bước 3:** Nếu thiếu bean, kiểm **bean definition có nằm trong context hiện tại không**; với slice test, đừng mặc định nó scan đủ toàn bộ application.
- **Bước 4:** Nếu có hai bean cùng type, phân biệt lỗi **chọn bean** với lỗi **trùng bean name**.
- **Bước 5:** Nếu assertion sai, quan sát bean được chọn và kết quả đầu ra; không thêm `@DirtiesContext` hoặc tắt security/auto-config như cách chữa chung cho mọi trường hợp.

## 11. Thiết kế test gọn và an toàn khi import bean

Một test có thể dùng `@Import` đúng cú pháp nhưng vẫn tạo độ tin cậy giả. Hãy tuân thủ các nguyên tắc:

**Kiểm hợp đồng, không chỉ kiểm rằng “context chạy được”.** Ví dụ `assertNotNull(service)` rất yếu nếu mục tiêu là tính thời hạn đúng. Trong bài runnable, các assertion ở thời điểm trước/bằng/sau mốc là bằng chứng độc lập về hành vi, còn test kiểm Clock giúp bảo vệ wiring.

**Không thay thế logic đang cần kiểm.** Nếu muốn kiểm `DeadlineService` tính deadline, hãy chạy **service thật** với Clock thật nhưng cố định; đừng mock chính service để trả expected rồi kết luận nghiệp vụ đúng.

**Phân tách “test-only bean” và “production fallback”.** Một fake Gateway không được giấu lỗi production thiếu bean. Có test riêng bảo đảm cấu hình production có đủ adapter thực khi điều đó quan trọng.

**Không giữ secrets trong test config.** Tài khoản, token, mật khẩu thật không nên nằm trong `@TestConfiguration`, `@TestPropertySource` hoặc log CI. Dùng test credentials/placeholder đã được kiểm soát và fake endpoint khi phù hợp.

**Giới hạn classpath của test bean.** Đặt dưới `src/test/java` và chỉ import khi test cần; không chuyển class vào `src/main/java` để vượt lỗi test discovery. Nếu thư viện dùng chung cho nhiều module, thiết kế test fixtures/Gradle test fixtures riêng thay vì phát tán test config vào artifact production.

**Phân biệt bean substitution với integration coverage.** Test có fake external client chứng minh logic sử dụng client interface khi fake phản hồi dự kiến; nó không chứng minh protocol/auth/network của adapter production. Bổ sung adapter contract test hoặc integration test phù hợp.

## 12. Bài tập thực hành

**Bài A — phát hiện tác dụng của `@Import`:** Bỏ `@Import(FixedClockTestConfig.class)` khỏi `DeadlineServiceImportTest` và giữ nguyên expected. Test kiểm `fixedTestClock` sẽ fail vì bean đó không tồn tại; test dùng thời gian cố định cũng không còn đáng tin vì `systemClock` được chọn. Khôi phục annotation sau khi quan sát.

**Bài B — thấy rõ vai trò `@Primary`:** Giữ `@Import` nhưng tạm bỏ `@Primary` khỏi bean `fixedTestClock`. Khi Spring cần `Clock` theo type cho `DeadlineService` và field test, hai bean cùng type có thể khiến context không biết chọn bean nào. Khôi phục `@Primary` và giải thích sự khác biệt giữa *đăng ký bean* và *phân giải bean*.

**Bài C — kiểm giá trị biên:** Đổi `deadlineEqualToCurrentTimeIsExpired` thành expected `false` trong một nhánh local. Test phải fail vì hợp đồng nói thời điểm **bằng hạn đã hết hạn**. Hoàn nguyên để test xanh.

**Bài D — giới hạn scope:** Viết một `@WebMvcTest` cho controller đơn giản có dependency cần giả lập; dùng `@Import` một config chỉ cung cấp dependency đó. So sánh số bean và thời gian khởi tạo với việc import cả application config, không làm mất kiểm tra status/JSON.

**Bài E — test config bảo vệ khỏi rò môi trường:** Tạo một fake gateway có `List` nội bộ, cho hai test cùng thêm dữ liệu. Nếu chia sẻ context, hãy thêm reset fixture trước mỗi test và xác nhận không phụ thuộc thứ tự. Không dùng `@DirtiesContext` như cách đầu tiên nếu reset có thể thực hiện dễ dàng.

**Bài F — property thay vì import:** Chọn một bean đang đọc `pricing.rate` từ Spring `Environment`. Đổi giá trị cho test qua `@TestPropertySource` và viết assertion output, không tạo một Bean mới nếu không cần. Giải thích trường hợp nào `@Import` vẫn cần thiết khi một bean không tồn tại.

## 13. Checklist khi dùng `@Import` trong test Spring Boot

- [ ] Hành vi cần test có thực sự yêu cầu Spring context không? Nếu chỉ là thuật toán thuần Java, unit test có thể đơn giản hơn.
- [ ] Tôi biết rõ **bean/config nào** được import và **vì sao** test cần nó?
- [ ] Test config nằm trên test source set, không xuất hiện trong production artifact?
- [ ] `@Import` đặt trong test/bootstrap config phù hợp (`@SpringBootTest`, slice, hoặc root Spring configuration)?
- [ ] Nếu có hai bean cùng type, cơ chế chọn bean (`@Primary`, `@Qualifier`, conditional config) có minh bạch không?
- [ ] Tôi đã phân biệt trùng bean *type* với trùng bean *name* và không vô hiệu kiểm soát overriding bừa bãi?
- [ ] Import có giữ phạm vi test hẹp, không vô ý mở component scan rộng?
- [ ] Test có assertion output/side effect đúng hợp đồng, chứ không chỉ “bean được tạo”?
- [ ] Context và singleton fake có state được reset/kiểm soát giữa test không?
- [ ] Test dùng fake/mock có được bổ sung integration/contract test cho adapter thật khi cần không?
- [ ] Gradle chạy JUnit Platform, wrapper/JDK đúng, báo cáo xác nhận số test thực sự chạy?

**Ghi nhớ:** `@Import` **bổ sung cấu hình hoặc bean vào Spring context** của test; nó không tự tạo context, không tự mock dependency và cũng không có nghĩa thay thế bean cũ. Với Spring Boot, tổ hợp **`@TestConfiguration` + `@Import`** giúp khai báo test bean tường minh, còn **`@Primary` hoặc `@Qualifier`** quyết định candidate được inject. Chỉ import phần cần thiết và kiểm kết quả nghiệp vụ độc lập sẽ cho bộ test vừa ổn định vừa đáng tin.

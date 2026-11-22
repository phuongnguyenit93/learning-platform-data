# Nested @Configuration và @TestConfiguration trong lớp kiểm thử Spring Boot

## 1. Bài toán: test cần cấu hình riêng nhưng vẫn phải biết đang tải ApplicationContext nào

Trong kiểm thử Spring Boot, ta thường muốn đưa một bean phụ trợ vào môi trường test: đồng hồ cố định để thử ngày hết hạn, fake HTTP client, dữ liệu cấu hình, bean đo hành vi hoặc triển khai đơn giản thay thế dependency. Cách khai báo lớp cấu hình **lồng bên trong test** trông rất giống nhau:

~~~java
@Configuration
static class LocalConfig { /* @Bean ... */ }

@TestConfiguration
static class TestOnlyConfig { /* @Bean ... */ }
~~~

Tuy nhiên, trong cơ chế tự phát hiện cấu hình của Spring Boot, hai annotation có **ngữ nghĩa rất khác**:

- **static nested @Configuration:** Thường được Spring Test xem là **cấu hình mặc định do test khai báo**. Với @SpringBootTest không chỉ định classes một cách tường minh, cấu hình lồng này được dùng **thay cho primary application configuration** mà Spring Boot bình thường tìm từ @SpringBootApplication hoặc @SpringBootConfiguration. Đây là cách tạo context nhỏ, có chủ đích, nhưng rất dễ khiến các bean sản xuất không xuất hiện.
- **static nested @TestConfiguration:** Là cấu hình chuyên dùng cho test của Spring Boot. Nếu được khai báo lồng trong test theo mẫu được hỗ trợ, nó được **bổ sung vào primary application configuration**, cho phép giữ bean ứng dụng và thêm bean test.
- **Top-level @TestConfiguration** (lớp nằm riêng dưới src/test/java) thường bị loại khỏi component scanning mặc định của Spring Boot; khi cần dùng, hãy **@Import** rõ ràng vào test.
- **JUnit Jupiter @Nested** lại là cơ chế *nhóm các phương thức test* bằng lớp thành viên không static; nó **không cùng khái niệm** với static nested configuration class. Spring Test còn có @NestedTestConfiguration để điều khiển kế thừa annotation test qua các lớp @Nested của JUnit.

Bài này tập trung vào **cấu hình môi trường test**: khám phá cấu hình, phạm vi các bean, cách sử dụng, tương tác với Spring Boot, những lỗi thường gặp và cách tự xác minh context đã tải đúng. Các ví dụ sử dụng **Spring Boot 3.3.5, Spring Framework 6.x, Java 17, JUnit Jupiter và Gradle**.

## 2. Spring Boot tìm primary configuration cho @SpringBootTest thế nào?

Trong dự án có cấu trúc hợp lý:

~~~text
src/main/java/demo/config/
  DemoApplication.java        @SpringBootApplication
  TimeService.java            @Service
src/test/java/demo/config/
  MyServiceTest.java          @SpringBootTest
~~~

Nếu MyServiceTest không khai báo các lớp cấu hình cụ thể, @SpringBootTest thường tìm ngược lên các package cha từ package của test cho đến khi gặp một lớp **@SpringBootApplication** hoặc **@SpringBootConfiguration**. Sau đó Spring Boot tải cấu hình chính và các bean trong phạm vi component scanning/cấu hình nhập vào tương ứng.

Ví dụ:

~~~java
@SpringBootTest
class MyServiceTest {
    // Spring Boot có thể tự tìm demo.config.DemoApplication.
}
~~~

Đoạn trên chỉ minh họa annotation trên một test, chưa phải chương trình Java độc lập. Điều quan trọng: **tự dò cấu hình chính** chỉ là hành vi khi không có cấu hình đã được test chỉ rõ qua cơ chế được Spring Test công nhận. Nếu test khai báo **@SpringBootTest(classes = ...)** hay **@ContextConfiguration(classes = ...)**, kết quả phụ thuộc vào danh sách classes/loader và các import cụ thể.

Theo tài liệu Spring Boot 3.3, một lớp **static nested @Configuration** trong test có thể đóng vai trò cấu hình chính do test cung cấp. Khi đó Spring Boot không còn phải dùng cấu hình @SpringBootApplication được tìm tự động. Ngược lại, **static nested @TestConfiguration** có vai trò **bổ sung**.

Đây là khác biệt thực tế quan trọng hơn việc hai annotation cùng đăng ký phương thức @Bean. @TestConfiguration bản thân được xây dựng dựa trên cơ chế configuration của Spring, nhưng Spring Boot sử dụng nó theo chính sách test riêng.

## 3. So sánh nhanh @Configuration, @TestConfiguration và @Import

| Cách khai báo | Vai trò thông thường trong Spring Boot test | Có tự tải cấu hình ứng dụng chính? | Khi nên chọn |
|---|---|---|---|
| Không khai báo nested config; chỉ @SpringBootTest | Tìm cấu hình @SpringBootApplication/@SpringBootConfiguration | Có, nếu tìm được và không bị cấu hình tường minh thay thế | Test toàn bộ context bình thường |
| **static nested @Configuration** | Cung cấp cấu hình gốc cho test | Thường **không** dùng app config tự tìm nữa | Test một context nhỏ chỉ gồm bean mong muốn |
| **static nested @TestConfiguration** | Bổ sung bean test vào cấu hình chính | Có trong trường hợp tự phát hiện thông thường | Thêm Clock cố định, fake dependency, helper bean |
| **@Import(TopLevelTestConfig.class)** | Nhập lớp config được chỉ định | Có, nếu dùng cùng @SpringBootTest bình thường | Chia sẻ cấu hình test có chủ đích giữa các class |
| **@SpringBootTest(classes = DemoApplication.class)** | Chọn explicit primary sources | Chỉ tải các sources được chỉ định và phần chúng kéo vào | Cần kiểm soát chính xác nguồn config |
| **@ContextConfiguration(classes = LocalConfig.class)** | Chọn trực tiếp configuration cho Spring TestContext | Phụ thuộc loader và các annotation phối hợp | Test context tích hợp với cấu hình cụ thể |

**Lưu ý:** “Bổ sung” không có nghĩa là tự động thay thế một bean cùng tên. Nếu hai cấu hình đăng ký trùng bean name và bean overriding đang bị tắt, context có thể không khởi động. Muốn chọn một bean test cùng **kiểu** mà vẫn giữ bean cũ, có thể đặt **@Primary** trên bean test với **tên bean khác**, hoặc dùng **@Qualifier**. Chọn kỹ thuật theo đúng mục tiêu test.

## 4. Vì sao lớp cấu hình lồng thường khai báo static?

Mẫu phổ biến của Java:

~~~java
@SpringBootTest
class ExampleTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class LocalTestBeans {

        @Bean
        TestMarker marker() {
            return new TestMarker("test");
        }
    }

    record TestMarker(String value) {
    }
}
~~~

Đây là snippet minh họa: muốn biên dịch, cần imports cho Spring Test/Bean, JUnit nếu có phương thức @Test; cần ứng dụng Spring Boot để @SpringBootTest tìm được primary source.

**static** cho phép Spring khởi tạo lớp cấu hình lồng mà không cần một instance của lớp test bao quanh. Một non-static inner class của Java giữ tham chiếu ngầm đến outer test instance, không phù hợp với mẫu configuration được TestContext tự phát hiện. Khi muốn tự động khám phá config lồng, dùng **static nested class**.

Với **@TestConfiguration(proxyBeanMethods = false)**:

- Spring đăng ký các phương thức @Bean vào context test.
- proxyBeanMethods = false cho phép tránh cơ chế proxy giữa các phương thức @Bean khi không cần gọi lẫn nhau; nó thích hợp cho các bean độc lập.
- Nếu một @Bean phụ thuộc bean khác, ưu tiên để Spring **truyền dependency qua tham số @Bean hoặc constructor** thay vì gọi trực tiếp một phương thức @Bean trong cùng config rồi giả định singleton semantics khi proxyBeanMethods = false.

**Đừng dùng @Nested của JUnit để biến một test group thành lớp cấu hình Spring**. Hai loại “nested” khác nhau cả mục đích lẫn lifecycle; phần 10 sẽ phân biệt rõ.

## 5. Ví dụ hoàn chỉnh: một ứng dụng và ba cách cấu hình test

Ta sẽ có ứng dụng Spring Boot nhỏ với một TimeService nhận Clock qua constructor. Bean sản xuất dùng **Clock.systemUTC()**; test muốn thay nguồn thời gian để assertion tất định. Có ba ca độc lập:

1. **Nested @TestConfiguration:** Giữ bean ứng dụng và thêm Clock.fixed được đánh dấu @Primary.
2. **Nested @Configuration:** Chỉ dùng cấu hình nhỏ của test; không tải service và bean đánh dấu sản xuất.
3. **Top-level @TestConfiguration + @Import:** Đưa helper bean từ một file test riêng vào context ứng dụng.

Cấu trúc file:

~~~text
settings.gradle
build.gradle
src/main/java/demo/config/DemoApplication.java
src/main/java/demo/config/TimeService.java
src/test/java/demo/config/NestedTestConfigurationAdditionTest.java
src/test/java/demo/config/NestedConfigurationReplacementTest.java
src/test/java/demo/config/SharedTestConfiguration.java
src/test/java/demo/config/TopLevelImportTest.java
src/test/java/demo/config/JupiterNestedGroupsTest.java
~~~

### 5.1. Gradle build

**settings.gradle**

~~~groovy
rootProject.name = 'spring-test-nested-configuration'
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

Spring Boot starter-test có JUnit Jupiter, AssertJ và các tiện ích Spring Test. Ở ví dụ chỉ dùng Starter cơ bản, chưa cần web server hay database. **useJUnitPlatform()** bảo đảm Gradle chạy JUnit Jupiter.

### 5.2. Mã ứng dụng

**src/main/java/demo/config/DemoApplication.java**

~~~java
package demo.config;

import java.time.Clock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }

    @Bean
    ProductionMarker productionMarker() {
        return new ProductionMarker("application");
    }
}

record ProductionMarker(String value) {
}
~~~

Cùng một file Java có **một public class** tên trùng file và một record package-private dùng trong test cùng package. ProductionMarker giúp kiểm tra liệu các bean từ primary configuration đã được tải hay chưa.

**src/main/java/demo/config/TimeService.java**

~~~java
package demo.config;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class TimeService {

    private final Clock clock;

    public TimeService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Instant now() {
        return clock.instant();
    }
}
~~~

TimeService được component scan bởi @SpringBootApplication trong demo.config. Trong ứng dụng thông thường, chỉ có Clock **systemClock** nên constructor được inject Clock hệ thống. Khi một test thêm Clock **fixedClock** đánh dấu @Primary, service trong context test nhận Clock cố định.

### 5.3. Nested @TestConfiguration: **bổ sung** cấu hình, không thay ứng dụng

**src/test/java/demo/config/NestedTestConfigurationAdditionTest.java**

~~~java
package demo.config;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class NestedTestConfigurationAdditionTest {

    private static final Instant FIXED_TIME =
            Instant.parse("2026-11-08T10:00:00Z");

    @Autowired
    TimeService timeService;

    @Autowired
    ProductionMarker productionMarker;

    @Autowired
    TestMarker testMarker;

    @Autowired
    @Qualifier("systemClock")
    Clock systemClock;

    @Autowired
    @Qualifier("fixedClock")
    Clock fixedClock;

    @Test
    void keepsApplicationBeansAndUsesPrimaryTestClock() {
        assertThat(productionMarker.value()).isEqualTo("application");
        assertThat(testMarker.value()).isEqualTo("test-only");
        assertThat(timeService.now()).isEqualTo(FIXED_TIME);
        assertThat(fixedClock.instant()).isEqualTo(FIXED_TIME);
        assertThat(systemClock).isNotSameAs(fixedClock);
    }

    record TestMarker(String value) {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockTestConfig {

        @Bean
        @Primary
        Clock fixedClock() {
            return Clock.fixed(FIXED_TIME, ZoneOffset.UTC);
        }

        @Bean
        TestMarker testMarker() {
            return new TestMarker("test-only");
        }
    }
}
~~~

Giải thích chính xác theo quá trình load:

1. @SpringBootTest tìm DemoApplication (lớp primary) theo package test, rồi tải TimeService và productionMarker.
2. Spring Boot cũng nhận diện lớp **static nested @TestConfiguration** trong test để bổ sung fixedClock và testMarker.
3. Context có hai bean kiểu Clock: systemClock và fixedClock. Vì fixedClock có **@Primary**, injection Clock vào TimeService chọn fixedClock.
4. Không có bean name conflict: systemClock và fixedClock **khác tên**. Vì thế không cần bật bean-definition overriding.
5. Test tự xác minh **cả hai phía**: productionMarker chứng tỏ cấu hình chính vẫn có mặt; testMarker chứng tỏ config test được nạp; timeService.now() chứng tỏ đúng Clock được chọn.

**Đây là trường hợp phù hợp nhất khi bạn muốn “giữ ứng dụng thật và thêm vài bean dành riêng cho test”.** Một lớp nested @TestConfiguration như trên không đòi @Import tường minh khi được Spring Boot test loader tự nhận diện.

### 5.4. Nested @Configuration: **thay primary sources được tự tìm** trong test này

**src/test/java/demo/config/NestedConfigurationReplacementTest.java**

~~~java
package demo.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class NestedConfigurationReplacementTest {

    @Autowired
    ApplicationContext context;

    @Test
    void usesOnlyExplicitNestedConfiguration() {
        assertThat(context.getBean(LocalMarker.class).value())
                .isEqualTo("isolated");

        assertThat(context.getBeansOfType(ProductionMarker.class))
                .isEmpty();
        assertThat(context.getBeansOfType(TimeService.class))
                .isEmpty();
    }

    record LocalMarker(String value) {
    }

    @Configuration(proxyBeanMethods = false)
    static class IsolatedBeans {

        @Bean
        LocalMarker localMarker() {
            return new LocalMarker("isolated");
        }
    }
}
~~~

Với test không khai báo classes tường minh và cấu trúc package ở ví dụ này, Spring Boot chọn cấu hình tĩnh lồng **IsolatedBeans** làm nguồn cấu hình test. Vì nó không có @ComponentScan và không import DemoApplication, **TimeService** và **ProductionMarker** từ ứng dụng chính không được tạo. Các assertion kiểm tra điều đó ngay trên ApplicationContext.

Đây là trường hợp **chủ đích thay thế** cấu hình để kiểm tra riêng một nhóm bean. Nếu bạn thêm nested @Configuration chỉ vì muốn tạo thêm Clock mà vẫn mong Spring Boot tự load toàn bộ ứng dụng, test có thể lỗi **NoSuchBeanDefinitionException** hoặc các bean cần thiết không được tìm thấy. Trong trường hợp bổ sung, đổi sang **@TestConfiguration**.

**Không đồng nhất “thay cấu hình chính được tự tìm” với “mọi bean khác đều biến mất bất kể hoàn cảnh”.** Nếu nested @Configuration của bạn tự @ComponentScan, @Import(DemoApplication.class), kích hoạt auto-configuration hoặc test được cấu hình explicit khác, các bean đó có thể được đưa vào. Kết quả luôn phụ thuộc các sources thực tế.

### 5.5. Top-level @TestConfiguration: chủ động import khi cần chia sẻ

**src/test/java/demo/config/SharedTestConfiguration.java**

~~~java
package demo.config;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class SharedTestConfiguration {

    @Bean
    ImportedMarker importedMarker() {
        return new ImportedMarker("from-import");
    }

    public record ImportedMarker(String value) {
    }
}
~~~

**src/test/java/demo/config/TopLevelImportTest.java**

~~~java
package demo.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(SharedTestConfiguration.class)
class TopLevelImportTest {

    @Autowired
    ProductionMarker productionMarker;

    @Autowired
    SharedTestConfiguration.ImportedMarker importedMarker;

    @Test
    void keepsApplicationAndImportsSharedTestBeans() {
        assertThat(productionMarker.value()).isEqualTo("application");
        assertThat(importedMarker.value()).isEqualTo("from-import");
    }
}
~~~

Khi SharedTestConfiguration nằm ở **top level** trong src/test/java, việc đặt @TestConfiguration giúp Spring Boot tránh thu thập nó như một cấu hình thông thường qua component scan mặc định của @SpringBootApplication. Test cần sử dụng thì thêm **@Import(SharedTestConfiguration.class)**.

Lưu ý về khác biệt:
- @Import có thể nhập lớp @Configuration hay @TestConfiguration; trong ví dụ mục đích là **giới hạn phạm vi của cấu hình chỉ dành cho test**.
- Dùng @Configuration top-level trong vùng component scan có thể vô tình làm bean test xuất hiện trong nhiều test khác. Spring Boot có cơ chế loại trừ @TestConfiguration khỏi scan mặc định để giảm rủi ro đó.
- Nếu bạn tự cấu hình **@ComponentScan** trên application, các bộ lọc test của @SpringBootApplication có thể không còn áp dụng như mặc định; cần kiểm tra/khôi phục TypeExcludeFilter theo hướng dẫn Spring Boot.
- Khi tái sử dụng cấu hình test qua nhiều class, @Import làm dependency về cấu hình hiển thị rõ ngay tại nơi dùng. Nó cũng ảnh hưởng context cache key.

### 5.6. JUnit Jupiter @Nested khác static nested configuration

**src/test/java/demo/config/JupiterNestedGroupsTest.java**

~~~java
package demo.config;

import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class JupiterNestedGroupsTest {

    @Nested
    class GroupOfAssertions {

        @Autowired
        ProductionMarker productionMarker;

        @Test
        void inheritsSpringTestConfigurationByDefault() {
            assertThat(productionMarker.value())
                    .isEqualTo("application");
        }
    }
}
~~~

**@Nested** của JUnit Jupiter dùng **non-static inner class** để nhóm test. Spring TestContext hỗ trợ kế thừa cấu hình test từ lớp ngoài; chế độ mặc định là **INHERIT** với các phiên bản Spring Framework 6.x tương ứng. Có thể dùng **@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)** nếu muốn lớp test lồng quản lý cấu hình test annotation riêng, nhưng đây là hành vi khác hoàn toàn với việc đặt **@TestConfiguration** trên một **static config class**.

Để dễ nhớ:

| Loại “nested” | Thường là static? | Annotation | Mục đích |
|---|---|---|---|
| Config lồng | **Có** | @Configuration | Định nghĩa context/configuration source |
| Config chỉ cho test lồng | **Có** | @TestConfiguration | Bổ sung bean test |
| Lớp nhóm kiểm thử JUnit | **Không** | @Nested | Nhóm phương thức @Test trong JUnit Jupiter |
| Chính sách kế thừa annotation cho lớp test lồng | Áp dụng lên test class | @NestedTestConfiguration | INHERIT/OVERRIDE cấu hình Spring TestContext |

## 6. Chạy ví dụ, đọc kết quả và xác nhận thực tế

Giả sử dự án đã có **Gradle Wrapper**:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Các file trên là mã nguồn và cấu hình Gradle đầy đủ của ví dụ. Lệnh ./gradlew cần những file wrapper tương ứng; nếu tạo dự án thủ công từ đầu mà chưa có wrapper, cần tạo bằng Gradle tương thích đã cài hoặc chạy **gradle test** bằng bản tương thích với Spring Boot 3.3.x.

Bộ kiểm thử phải chạy các phương thức của:
- NestedTestConfigurationAdditionTest: chứng minh **bean ứng dụng + bean test** cùng tồn tại và Clock @Primary được chọn.
- NestedConfigurationReplacementTest: chứng minh **chỉ context test nhỏ** được tạo theo cấu hình nested @Configuration.
- TopLevelImportTest: chứng minh **bean nhập qua @Import** hiện diện cùng các bean ứng dụng.
- JupiterNestedGroupsTest: chứng minh một **@Nested test** có thể kế thừa cấu hình Spring từ test ngoài.

Xem báo cáo HTML tại **build/reports/tests/test/index.html**. Nếu một assertion thất bại, kiểm tra tên bean, đường dẫn package, classpath, annotation và cơ chế tìm cấu hình trước khi thêm workaround.

Ví dụ không cần cấu hình database và không mở cổng HTTP: **@SpringBootTest(webEnvironment = NONE)** vẫn tải Spring context nhưng không tạo web environment. Các test này là **kiểm thử tích hợp cấu hình Spring**, không phải unit test thuần (mặc dù assertion rất ngắn). Đối với logic Java không cần container, hãy dùng new Service(fakeDependency) hoặc Mockito/JUnit Jupiter để test nhanh hơn.

**Tính xác định:** Không so sánh thời gian hệ thống của productionClock với một Instant cố định. Ví dụ chỉ kiểm tra systemClock và fixedClock là hai instance khác nhau, rồi xác minh TimeService dùng fixedClock bằng thời điểm chính xác.

## 7. Những điều dễ nhầm khi thay bean trong test

### 7.1. @TestConfiguration không tự ghi đè bean cùng tên

Trong Spring Boot 3.3.x, **spring.main.allow-bean-definition-overriding** mặc định là **false**. Nếu test thêm một bean cũng có cùng tên với bean sản xuất, bạn có thể gặp **BeanDefinitionOverrideException**, thay vì Spring ngầm thay thế.

Ví dụ dễ gây va chạm (minh họa, không đưa vào ví dụ PASS ở trên):

~~~java
// Trong application:
@Bean
Clock systemClock() { return Clock.systemUTC(); }

// Trong test config cũng đặt tên bean là systemClock:
@Bean
Clock systemClock() { return Clock.fixed(fixed, ZoneOffset.UTC); }
~~~

Nếu cả hai được nạp, đây là tranh chấp định nghĩa bean name. Cách an toàn hơn khi mục tiêu chỉ là thay bean được inject theo kiểu:
- Giữ bean production tên **systemClock**.
- Thêm bean test tên **fixedClock**.
- Đặt **@Primary** trên fixedClock.
- Inject Clock vào TimeService theo kiểu, không hard-code @Qualifier("systemClock") trong service nếu muốn @Primary có tác dụng.

Nếu code sản xuất đã dùng @Qualifier("systemClock"), @Primary không tự bỏ qua qualifier đó. Lúc ấy cần thiết kế test phù hợp với qualifier thật, hoặc dùng cơ chế thay bean được hỗ trợ theo phiên bản Spring Boot.

**Không bật allow-bean-definition-overriding=true toàn cục để che sự nhầm lẫn.** Nếu phải thay định nghĩa theo tên, hãy xem xét cơ chế test bean replacement, kiểm soát tên/phiên bản và phạm vi test rõ ràng.

### 7.2. @Primary không “thay thế” bean cũ trong ApplicationContext

@Primary là **quy tắc chọn dependency khi có nhiều ứng viên theo kiểu**. Bean cũ vẫn tồn tại và có thể được lấy bằng tên/qualifier. Nếu hệ thống chạy cả hai bean và một số component inject bằng qualifier khác, chỉ gắn @Primary chưa chắc thay được tất cả đường dùng. Hãy kiểm tra **bean mà SUT thực sự nhận**, như ví dụ TimeService.now().

Khi test cần thay thật một dependency cho toàn bộ luồng, bạn có thể dùng cơ chế mocking/replacement của Spring Boot Test tương ứng phiên bản; ví dụ Spring Boot 3.3.x có **@MockBean**. Nhưng mock không tự cung cấp hành vi như Clock.fixed: bạn còn phải stub method. Với Clock có thể dùng @Primary fake bean vì đơn giản và tất định.

### 7.3. @TestConfiguration và @Import khác @Profile

**@Profile("test")** chỉ là điều kiện kích hoạt bean khi profile phù hợp đang active. **@ActiveProfiles("test")** kích hoạt profile cho test, nhưng không tự quyết định primary configuration class. Nếu đặt @Profile trên một @Configuration test mà class đó vẫn được tìm/nhập theo cách khác, phải xét cả hai cơ chế **phát hiện config** và **điều kiện profile**.

Không đặt @ActiveProfiles("test") cho mọi bài test một cách máy móc; profile khác nhau thay đổi context cache key, properties và điều kiện bean. Chỉ dùng profile nếu nội dung bài test thật sự cần nhánh cấu hình đó.

## 8. Chọn @Import, nested @TestConfiguration hay @SpringBootTest(classes = ...) thế nào?

**Tình huống A: Thêm một bean phục vụ đúng một test class.**

Dùng **static nested @TestConfiguration** ở cuối class test. Ví dụ clock cố định, fake publisher hoặc bean test marker. Đây là lựa chọn dễ thấy phạm vi sử dụng nhất: code và cấu hình nằm cạnh assertion.

**Tình huống B: Nhiều test class cần chung một bộ bean trợ giúp.**

Tạo **top-level @TestConfiguration** trong src/test/java rồi dùng **@Import** tại các test cần thiết. Điều này tránh việc cấu hình bị quét tự động vào mọi context và giúp chia sẻ test fixtures có chủ đích.

**Tình huống C: Muốn chỉ load vài bean, không muốn toàn bộ app.**

Dùng **nested @Configuration** với Spring TestContext phù hợp hoặc **@SpringBootTest(classes = SmallConfig.class)**. Nếu không cần các tính năng của Spring Boot test bootstrap, có thể dùng **@SpringJUnitConfig(SmallConfig.class)** của Spring Framework Test thay vì tải ứng dụng đầy đủ.

**Tình huống D: Muốn kiểm thử một phần web/JPA thay vì cả context.**

Ưu tiên **test slice** như @WebMvcTest hoặc @DataJpaTest, rồi @Import các bean cấu hình hỗ trợ đúng phạm vi. Cần hiểu slice tự lọc auto-configuration và component scan; import nguyên một cấu hình ứng dụng có thể làm slice nặng và biến bài test thành phạm vi khác dự kiến.

**Tình huống E: Cấu hình rõ mọi primary source.**

Dùng **@SpringBootTest(classes = DemoApplication.class)** hoặc danh sách explicit khác khi cần loại bỏ sự mơ hồ từ cơ chế auto-search. Khi đã explicit classes, không được suy luận rằng nested @Configuration sẽ “tự nhiên thay app” theo cùng cách như trường hợp tìm tự động. Đánh giá nguồn config thật đã khai báo và mọi @Import đang có.

## 9. Context caching: vì sao thay config có thể làm test chậm hoặc nhiễm trạng thái?

Spring TestContext **cache ApplicationContext** giữa các test có cùng cấu hình hiệu lực. Điều này giúp giảm chi phí khởi động Spring. Các thay đổi như configuration classes, imports, active profiles, property sources và context customizers có thể tạo cache key khác, kéo theo việc tải context riêng.

| Cách viết | Tác động thường gặp |
|---|---|
| Hai test dùng cùng app config và các tùy chọn giống nhau | Có cơ hội tái sử dụng cached context |
| Một test thêm nested @TestConfiguration riêng | Có thể cần context khác vì cấu hình khác |
| Một test @Import một cấu hình test khác | Có thể tạo context key khác |
| Mỗi test tự thay property/profile khác nhau | Thường giảm khả năng dùng chung context |
| Đặt trạng thái mutable trong singleton test bean | Dễ tạo test phụ thuộc thứ tự hoặc trạng thái còn sót |
| Lạm dụng @DirtiesContext | Buộc loại context khỏi cache, khiến suite chậm hơn |

**Nguyên tắc:** Cấu hình test cần đủ cô lập để không rò rỉ trạng thái, nhưng không nên tạo hàng chục config chỉ khác nhau ở chi tiết nhỏ mà không cần thiết. Nếu dùng singleton fake có bộ nhớ thay đổi trong quá trình test, hãy reset trạng thái giữa các test hoặc thiết kế fake bất biến; context cache không tự làm mới mọi trạng thái kinh doanh trong bean.

Không dùng @DirtiesContext như cách chữa mặc định cho mọi bài test thất bại vì bị ảnh hưởng bởi lần chạy trước; trước hết tìm static state, singleton mutable data và dữ liệu database/test fixture chưa được dọn.

## 10. Phân biệt @NestedTestConfiguration với @TestConfiguration

Tên có vẻ giống nhưng ý nghĩa khác:

- **org.springframework.boot.test.context.TestConfiguration** là annotation **định nghĩa configuration class** có các @Bean phục vụ test.
- **org.springframework.test.context.NestedTestConfiguration** là annotation **chính sách kế thừa metadata TestContext** trên một hierarchy của **JUnit Jupiter @Nested test classes**. Giá trị thường gặp là **INHERIT** (mặc định) hoặc **OVERRIDE**.

Ví dụ minh họa ý tưởng (không phải class chạy độc lập):

~~~java
@SpringBootTest
class OuterTest {

    @Nested
    class InnerTest {
        // Mặc định kế thừa metadata cấu hình từ OuterTest.
    }

    @Nested
    @NestedTestConfiguration(
        NestedTestConfiguration.EnclosingConfiguration.OVERRIDE)
    class IndependentInnerTest {
        // Cần khai báo metadata test phù hợp với phạm vi mới.
    }
}
~~~

Ở chế độ OVERRIDE, lớp test lồng phải tự khai báo các annotation cấu hình Spring cần thiết nếu không muốn dùng metadata của lớp ngoài. **OVERRIDE không có nghĩa “override mọi @Bean”** và cũng không phải cách thay bean sản xuất. Với một test chỉ cần bean mới, vẫn ưu tiên @TestConfiguration/@Import.

## 11. Gặp lỗi thì tìm nguyên nhân theo thứ tự

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/sửa |
|---|---|---|
| Không có TimeService trong @SpringBootTest | Thêm static nested @Configuration làm thay primary config | Đổi thành @TestConfiguration nếu mục tiêu là bổ sung |
| NoSuchBeanDefinitionException cho bean sản xuất | App @SpringBootApplication không được load hoặc slice đã loại bean | Kiểm tra primary source, component scan, slice và @Import |
| Có hai Clock và NoUniqueBeanDefinitionException | Cả hai bean cùng kiểu nhưng không có lựa chọn rõ | @Primary hoặc @Qualifier; xác minh bean SUT dùng |
| BeanDefinitionOverrideException | Hai config đăng ký trùng bean name và overriding bị tắt | Đổi tên + @Primary hoặc dùng cơ chế replacement có chủ đích |
| Test sử dụng Clock hệ thống thay vì fixed | SUT inject @Qualifier("systemClock") hoặc bean khác | Kiểm tra constructor/qualifier và test kết quả thật |
| Nested config không được tìm thấy | Class non-static, cấu hình explicit hoặc annotation/import không đúng | Dùng static nested config; kiểm tra bootstrap metadata |
| Top-level @TestConfiguration không được nạp | Có @TestConfiguration trong file riêng nhưng quên @Import | Thêm @Import trong class test cần |
| Test helper bị thu thập từ nhiều test ngoài dự kiến | Dùng top-level @Configuration trong vùng scan, custom ComponentScan | Dùng @TestConfiguration và import tường minh |
| @Nested test không nhận annotation Spring từ outer | Chế độ @NestedTestConfiguration OVERRIDE hoặc thiếu cấu hình | Kiểm tra INHERIT/OVERRIDE và annotation test |
| Suite test rất chậm khi thêm nhiều config | Context cache chia thành nhiều key, @DirtiesContext nhiều | Kiểm tra cấu hình hiệu lực, giảm custom context dư |
| Test slice vô tình load cả app | @Import/config quá rộng, @ComponentScan tùy biến | Thu hẹp config theo slice, giữ exclude filters |

**Quy trình điều tra:**

1. Đọc stack trace để biết lỗi xảy ra khi **khởi tạo ApplicationContext** hay khi **thực thi assertion**.
2. Xác định test dùng **@SpringBootTest, slice annotation, @SpringJUnitConfig** hay @ContextConfiguration; chú ý classes explicit.
3. Tìm static nested @Configuration/@TestConfiguration và các @Import thực tế.
4. Kiểm tra **kiểu bean, bean name và qualifier**, đặc biệt khi trùng tên hoặc có nhiều ứng viên.
5. Xác minh bằng một assertion gần với mục tiêu: presence của production bean, test bean và kết quả phương thức SUT.
6. Sau khi đã chọn đúng phạm vi cấu hình, chạy test qua công cụ CI (Gradle/Maven), tránh chỉ nhìn nút Run của IDE.

## 12. Các lưu ý khi thiết kế test có thể bảo trì

- **Đừng tạo nested @Configuration chỉ để “tiện thêm một @Bean”** khi bài test phải giữ full app context. Nó có thể đổi toàn bộ tập bean của test.
- **Dùng nested @TestConfiguration** cho phần tùy biến riêng của một class; nó mô tả ý định “thêm vào cấu hình app”.
- **Dùng top-level @TestConfiguration + @Import** cho fixture dùng chung hoặc test slice cần một bean cụ thể.
- **Kiểm tra primary source khi dùng explicit classes**; annotation nested không thay đổi một danh sách cấu hình đã được chỉ rõ theo cách bạn có thể dự đoán từ trường hợp auto-search.
- **Không coi @Primary là bean overriding**. Nó chọn candidate khi injection theo kiểu, còn bean cũ vẫn tồn tại.
- **Không đồng nhất static config class với JUnit @Nested**; cái đầu góp bean vào context, cái sau nhóm các phương thức test.
- **Tránh cấu hình toàn cục làm ảnh hưởng nhiều test** chỉ để giải quyết một ca. Cấu hình ít, có chủ đích và assertion rõ ràng dễ hiểu hơn.
- **Tách unit test khỏi context test:** business logic thuần Java nên kiểm tra trực tiếp; chỉ dùng Spring context khi bạn muốn chứng minh bean discovery, wiring, profile hoặc auto-configuration.

## 13. Tự kiểm tra sau bài học

1. Test có **@SpringBootTest** và một **static nested @Configuration** chỉ tạo bean X. Vì sao bean @Service của application có thể vắng mặt? Khi nào nên dùng @TestConfiguration thay thế?
2. Test thêm một Clock.fixed có **@Primary** trong nested @TestConfiguration. Production Clock.systemUTC có bị xóa khỏi context không? Điều gì xảy ra nếu service dùng @Qualifier("systemClock")?
3. Một top-level @TestConfiguration trong src/test/java không được test phát hiện. Bạn có thể đưa nó vào context của đúng một test class bằng annotation gì?
4. Lớp JUnit **@Nested** khác nested configuration ở điểm nào? @NestedTestConfiguration(OVERRIDE) điều chỉnh thứ gì?
5. Hai test khởi tạo context khác nhau sau khi thêm cấu hình. Điều đó có thể ảnh hưởng thời gian chạy và tính độc lập của suite như thế nào?

**Gợi ý trả lời:** (1) nested @Configuration có thể đóng vai trò primary configuration được test tìm; dùng nested @TestConfiguration để bổ sung. (2) Bean production vẫn có; @Primary ưu tiên injection theo kiểu nhưng không thắng qualifier cụ thể. (3) @Import. (4) @Nested nhóm test; @NestedTestConfiguration điều khiển kế thừa metadata của Spring TestContext, không định nghĩa bean. (5) Context cache key và trạng thái singleton có thể khác; cần quản lý fixture và tránh context tùy biến dư thừa.

## 14. Tài liệu chính thức

- [Spring Boot 3.3 — Testing Spring Boot Applications: Detecting Test Configuration và Excluding Test Configuration](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Framework — TestContext Framework Support Classes, @Nested test class configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html)
- [Spring Framework 6.1 — @NestedTestConfiguration Javadoc](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/test/context/NestedTestConfiguration.html)
- [Spring Boot 3.3 — TestConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/TestConfiguration.html)

**Điều cần ghi nhớ:** Hãy chọn cấu hình theo ý định của test: **cấu hình nhỏ riêng biệt** thì nested @Configuration; **bổ sung vào ứng dụng thật** thì nested @TestConfiguration; **chia sẻ rõ ràng** thì top-level @TestConfiguration + @Import. Sau đó luôn viết assertion kiểm tra các bean hoặc hành vi mà test kỳ vọng được cung cấp.
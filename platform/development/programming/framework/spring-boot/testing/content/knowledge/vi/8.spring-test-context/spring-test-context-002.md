# Spring TestContext: Khởi tạo ApplicationContext, tiêm phụ thuộc và thực thi test

## 1. Mục tiêu

Trong Java thuần, một unit test có thể tạo đối tượng bằng `new`, truyền fake/mock và kiểm tra kết quả. Nhưng khi cần xác minh Spring có đọc cấu hình, tạo bean, tiêm phụ thuộc, chọn profile và phối hợp các thành phần đúng hay không, test phải chạy với **Spring TestContext Framework**.

Bài này giải thích toàn bộ đường đi từ **JUnit Jupiter phát hiện và chạy một test**, tới **Spring dựng hoặc tái sử dụng `ApplicationContext`**, **inject dependency vào test instance**, gọi các callback rồi đóng giao dịch/dọn dữ liệu ở ranh giới thích hợp.

Sau bài này, bạn cần:

- Phân biệt `JUnit Jupiter`, `SpringExtension`, `TestContextManager`, `TestContext`, `TestExecutionListener`, `ContextLoader` và `ApplicationContext`.
- Chọn đúng `@SpringJUnitConfig`, `@ContextConfiguration` + `@ExtendWith(SpringExtension.class)`, `@SpringBootTest` hoặc test slice khi cần.
- Giải thích khi nào context được tạo, cache key hình thành thế nào, vì sao hai test class có thể dùng chung các singleton bean.
- Biết dùng `@Autowired` ở field, constructor hoặc method parameter và debug lỗi injection.
- Hiểu thứ tự tương đối của `@BeforeEach`, `@Test`, Spring callbacks, transaction và cleanup.
- Viết các test Java 17+ chạy thực tế và biết phạm vi bằng chứng của từng kiểu test.

## 2. Hai vòng đời khác nhau: test instance và Spring context

Test instance và Spring bean **không phải một thứ**.

JUnit Jupiter chịu trách nhiệm tạo và chạy đối tượng test, thường tạo một instance mới cho từng test method theo chế độ mặc định `PER_METHOD`. Spring quản lý các bean trong một `ApplicationContext`, thường chứa các singleton dùng chung. Spring TestContext kết nối hai bên để JUnit test instance nhận được bean Spring.

```text
Gradle / Maven / IDE
        |
        v
JUnit Platform -> Jupiter TestEngine
        |
        v
JUnit test instance + @Test methods
        |
        | SpringExtension (JUnit extension)
        v
TestContextManager
        |
        +--> TestContext / context configuration
        |        |
        |        +--> ContextCache (cache hit?)
        |                  |
        |                nếu chưa có
        |                  v
        |           ContextLoader
        |                  |
        |                  v
        |           ApplicationContext
        |             |     |     |
        |          @Bean  @Service  repository...
        |
        +--> TestExecutionListeners
                 |
                 +--> Dependency injection
                 +--> Transaction (nếu có)
                 +--> SQL scripts (nếu có)
                 +--> DirtiesContext (nếu được đánh dấu)
        |
        v
@BeforeEach -> @Test -> @AfterEach
        |
        v
Assertions + báo cáo kết quả cho JUnit
```

| Thành phần | Vai trò | Điều không nên nhầm |
| --- | --- | --- |
| **JUnit Platform/Jupiter** | Tìm và chạy `@Test`, lifecycle và assertions | Không tự khởi tạo bean Spring |
| **`SpringExtension`** | Cầu nối JUnit Jupiter với Spring TestContext, cung cấp callbacks và tham số | Không phải IoC container |
| **`TestContextManager`** | Quản lý trạng thái test và phát sự kiện ở các mốc vòng đời | Không phải business service |
| **`TestContext`** | Giữ ngữ cảnh class, method, instance, configuration và cách truy cập context | Không có nghĩa mỗi method cần một context riêng |
| **`TestExecutionListener`** | Thực hiện tiêm phụ thuộc, transaction, SQL và các tác vụ khác | Không phải HTTP filter hoặc application event listener |
| **`ContextLoader` / `SmartContextLoader`** | Tạo context dựa trên cấu hình đã chọn | Không tự bảo đảm tính năng Spring Boot |
| **`ApplicationContext`** | Container tạo và cung cấp các bean cùng cấu hình | Không phải test object do JUnit tạo |
| **`ContextCache`** | Tái sử dụng context theo cache key | Không reset mutable state của singleton |

**Ví dụ:** JUnit tạo hai instance khác nhau của `AccountServiceTest` để chạy hai phương thức `@Test`; cả hai vẫn có thể được inject cùng bean singleton `AccountService` của một Spring context đang được cache. Vì thế không thể suy luận “test instance mới thì dữ liệu bean cũng mới”.

## 3. Chọn mức nạp context phù hợp

| Cần kiểm tra | Mức test nên chọn | Spring context |
| --- | --- | --- |
| Quy tắc tính phí, biến đổi dữ liệu | JUnit, `new` object | Không |
| Service gọi gateway đúng đầu vào | JUnit + Mockito/fake | Không |
| Một vài bean `@Configuration`/`@Bean` | `@SpringJUnitConfig` | Context nhỏ |
| Spring Boot auto-configuration, profile, bean wiring | `@SpringBootTest` | Boot context |
| HTTP mapping/JSON riêng | `@WebMvcTest` | MVC slice |
| JPA mapping/repository | `@DataJpaTest` | Persistence slice |
| Controller → service → DB | `@SpringBootTest` + công cụ HTTP/DB | Context tích hợp |
| HTTP server thực ở cổng ngẫu nhiên | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Boot + server |

Một context lớn có nhiều điểm có thể thất bại hơn: datasource, bean ngoài, secrets, migrations hoặc cổng HTTP. **Chỉ dùng context khi những hành vi của Spring là đối tượng cần xác minh.**

## 4. Ba cách khai báo Spring TestContext

### 4.1. Cách tường minh: `@ExtendWith` và `@ContextConfiguration`

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class ExampleContextTest {
    @Autowired
    GreetingService service;

    @Test
    void testGreeting() {
        // assert kết quả của bean từ context.
    }
}
```

Đây là **đoạn minh họa**, cần `TestConfig` và `GreetingService` tồn tại. `@ExtendWith(SpringExtension.class)` đăng ký Spring với JUnit Jupiter. `@ContextConfiguration` chỉ định nguồn cấu hình context như Java `@Configuration` classes, XML/resource locations và các thuộc tính khác.

**Chỉ có `@ContextConfiguration` mà không có SpringExtension hoặc annotation tổng hợp tương ứng thì JUnit Jupiter chưa được tích hợp Spring DI.** Test field `@Autowired` có thể vẫn null.

### 4.2. Viết ngắn hơn: `@SpringJUnitConfig`

```java
@SpringJUnitConfig(classes = TestConfig.class)
class ExampleContextTest {
    @Autowired
    GreetingService service;
}
```

`@SpringJUnitConfig` kết hợp chức năng `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`, thuận tiện khi cần một **Spring context nhỏ, cấu hình rõ ràng**. Nó không tự khởi động Spring Boot auto-configuration như `@SpringBootTest`.

### 4.3. Nạp Spring Boot: `@SpringBootTest`

```java
@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ExampleBootTest {
    @Autowired
    GreetingService service;
}
```

`@SpringBootTest` dùng cơ chế bootstrap của Spring Boot, tạo context qua `SpringApplication` để tích hợp cấu hình Boot, auto-configuration, properties và profile phù hợp. Annotation này đã đăng ký SpringExtension cho JUnit Jupiter; không cần thêm `@ExtendWith(SpringExtension.class)` lần nữa.

`webEnvironment`:

- `MOCK` (mặc định): dựng mock web environment nếu ứng dụng có web stack trên classpath; **không mở HTTP server thật**.
- `RANDOM_PORT`: khởi chạy HTTP server trên cổng ngẫu nhiên, thích hợp test HTTP thật.
- `DEFINED_PORT`: khởi chạy server trên cổng được cấu hình hoặc cổng mặc định khi có web environment.
- `NONE`: nạp context mà không tạo môi trường web.

Nếu cần MockMvc cho MVC integration test, có thể dùng `@SpringBootTest` cùng `@AutoConfigureMockMvc`; không được mặc định rằng `@SpringBootTest` tự động mở server.

### 4.4. Nên ghi annotation nào trong test?

| Annotation | Đăng ký SpringExtension? | Chọn cách nạp context |
| --- | --- | --- |
| `@Test` | Không | Chỉ JUnit |
| `@ContextConfiguration` | Không tự đăng ký extension | Spring config được chỉ định |
| `@SpringJUnitConfig` | Có | Spring config được chỉ định |
| `@SpringBootTest` | Có | Spring Boot application context |
| `@WebMvcTest` | Có trong Boot test slice | Các bean MVC liên quan |
| `@DataJpaTest` | Có trong Boot test slice | Các bean persistence/JPA liên quan |

Không dùng một annotation như “bùa chú” để test xanh. Ví dụ `@WebMvcTest` cố tình không tự load tất cả service thật, nên một dependency cần mock/test configuration đúng giới hạn slice.

## 5. Chính xác điều gì xảy ra khi tạo `ApplicationContext`?

Annotation test mô tả cấu hình; **không cam kết rằng mọi bean đã tồn tại ngay khi JUnit vừa khám phá class**. Context được nạp khi test infrastructure thực sự cần truy cập nó. Constructor injection có thể kích hoạt sớm hơn field injection; một listener cũng có thể yêu cầu context trước khi `@Test` bắt đầu.

Quy trình theo chức năng:

1. **Phát hiện:** JUnit Jupiter đọc class test, `@Test` và các extension/annotations.
2. **Bootstrap TestContext:** `SpringExtension` phối hợp `TestContextManager`; Spring tổng hợp các cấu hình như classes, profiles, properties, loader, context customizers và parent context.
3. **Tìm cache:** Spring dùng cấu hình hợp nhất làm cache key. Nếu cache có context hợp lệ, nó có thể được tái sử dụng.
4. **Nạp context nếu chưa có:** context loader tạo `ApplicationContext`; với `@SpringBootTest`, Boot bootstrap dùng `SpringApplication`.
5. **Chuẩn bị bean definitions:** `@Configuration`/`@Bean`, component scan, imports, conditional configuration, profiles và properties được xử lý theo cấu hình đang bật.
6. **Refresh context:** Spring xử lý post-processors, tạo những singleton không lazy cần khởi tạo, resolve dependencies, tiêm constructor/field cho bean, chạy init callbacks phù hợp.
7. **Inject test fixture:** listener DI có thể tiêm field/setter của test instance; `SpringExtension` resolve constructor/test-method/lifecycle parameters thông qua JUnit `ParameterResolver`.
8. **Chạy test:** JUnit và Spring listeners gọi các mốc trước/sau test method, giữ context trong cache khi còn hợp lệ.

Đó là **mô hình về trách nhiệm**, không phải nhật ký tuyệt đối từng lời gọi nội bộ. Thứ tự chi tiết có thể thay đổi theo injection mode, listener và phiên bản Framework.

### Khác nhau giữa “bean được tạo” và “bean được inject vào test”

Một bean có thể đã được Spring tạo vì là singleton trong context, nhưng test không nhận được nó nếu field bị quên `@Autowired` hoặc extension/DI listener chưa hoạt động. Ngược lại, một mock được tạo bằng `Mockito.mock` và truyền bằng `new Service(mock)` có thể giúp unit test pass mà **chưa hề chứng minh** Spring biết cách tạo hoặc inject service ấy.

Test `contextLoads()` có giá trị để phát hiện lỗi bootstrap; nó không thay thế assertion nghiệp vụ.

## 6. Ví dụ chạy được với Java 17, Spring Boot 3.3.0, JUnit Jupiter

Ví dụ cố định **Spring Boot 3.3.0** để import và cấu hình có cùng phiên bản. Đây là bài học cơ chế, không phải gợi ý giữ bản cũ trong ứng dụng production. Khi áp dụng vào dự án thực, dùng BOM, wrapper và release được dự án hỗ trợ.

Ứng dụng nhỏ có service chào người dùng. Bean formatter đọc `lesson.prefix` từ application properties. Profile `test` thay chữ “Hello” thành “Hi”. Bốn test minh họa JUnit thuần, Spring context nhỏ, Boot context và constructor injection.

### 6.1. Cấu trúc

```text
testcontext-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── DemoApplication.java
    │   │   ├── GreetingFormatter.java
    │   │   ├── GreetingService.java
    │   │   └── GreetingConfiguration.java
    │   └── resources/application.properties
    └── test/
        ├── java/example/
        │   ├── GreetingServiceUnitTest.java
        │   ├── GreetingSmallContextTest.java
        │   ├── GreetingBootContextTest.java
        │   └── GreetingConstructorTest.java
        └── resources/application-test.properties
```

### 6.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'testcontext-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là build cho ví dụ độc lập, cần Gradle wrapper hợp lệ và kết nối tới repository để tải dependencies. Không có Spring Web hay database; vì vậy `@SpringBootTest(webEnvironment=NONE)` đủ cho mục tiêu.

### 6.3. Mã production

**`src/main/java/example/DemoApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**`src/main/java/example/GreetingFormatter.java`:**

```java
package example;

public record GreetingFormatter(String prefix) {
    public String format(String name) {
        return prefix + ", " + name + "!";
    }
}
```

**`src/main/java/example/GreetingService.java`:**

```java
package example;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final GreetingFormatter formatter;

    public GreetingService(GreetingFormatter formatter) {
        this.formatter = formatter;
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        return formatter.format(name);
    }
}
```

**`src/main/java/example/GreetingConfiguration.java`:**

```java
package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {
    @Bean
    GreetingFormatter greetingFormatter(
            @Value("${lesson.prefix:Hello}") String prefix) {
        return new GreetingFormatter(prefix);
    }
}
```

**`src/main/resources/application.properties`:**

```properties
lesson.prefix=Hello
```

**`src/test/resources/application-test.properties`:**

```properties
lesson.prefix=Hi
```

Cơ chế: `@SpringBootApplication` trong package `example` tạo cấu hình Boot và scan `GreetingService`/`GreetingConfiguration`. `@Bean` tạo formatter, `@Value` đọc `lesson.prefix`, service được inject formatter bằng constructor. Trong profile `test`, Boot đọc properties của profile ấy và trả lời `"Hi, ..."`.

### 6.4. Test A — JUnit thuần, không có Spring

**`src/test/java/example/GreetingServiceUnitTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceUnitTest {
    @Test
    void verifiesJavaLogicWithoutContext() {
        var service =
                new GreetingService(new GreetingFormatter("Hello"));

        assertEquals("Hello, Mai!", service.greet("Mai"));
        assertThrows(IllegalArgumentException.class,
                () -> service.greet(" "));
    }
}
```

JUnit tự tạo test instance. Test chủ động tạo service và formatter bằng `new`. Nó chứng minh logic Java, **không** chứng minh Spring đã tạo bean hoặc đọc properties.

### 6.5. Test B — Spring context nhỏ, chỉ hai bean

**`src/test/java/example/GreetingSmallContextTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(classes = GreetingSmallContextTest.TestConfig.class)
class GreetingSmallContextTest {
    @Configuration(proxyBeanMethods = false)
    static class TestConfig {
        @Bean
        GreetingFormatter formatter() {
            return new GreetingFormatter("Bonjour");
        }

        @Bean
        GreetingService greetingService(GreetingFormatter formatter) {
            return new GreetingService(formatter);
        }
    }

    @Autowired
    GreetingService service;

    @Test
    void injectsBeanFromExplicitConfiguration() {
        assertNotNull(service);
        assertEquals("Bonjour, Mai!", service.greet("Mai"));
    }
}
```

Ở đây TestContext tạo một `ApplicationContext` nhỏ từ `TestConfig`; hai bean được khai báo rõ ràng. Không có component scan của `DemoApplication` và không có Spring Boot `SpringApplication`. Prefix `Bonjour` là bằng chứng test dùng formatter trong context nhỏ.

### 6.6. Test C — Boot context + field injection + method injection

**`src/test/java/example/GreetingBootContextTest.java`:**

```java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("test")
class GreetingBootContextTest {
    @Autowired
    GreetingService service;

    @Autowired
    ApplicationContext context;

    @BeforeEach
    void injectedBeforeSetupRuns() {
        assertNotNull(service);
        assertNotNull(context);
    }

    @Test
    void resolvesBeanAndProfileProperty() {
        assertEquals("Hi, Mai!", service.greet("Mai"));
        assertSame(context.getBean(GreetingService.class), service);
    }

    @Test
    void injectsTestMethodParameter(
            @Autowired GreetingService parameterService) {
        assertSame(service, parameterService);
        assertEquals("Hi, An!", parameterService.greet("An"));
    }
}
```

Ý nghĩa:

- `@SpringBootTest` dùng Boot bootstrap và `@ActiveProfiles("test")` chọn prefix `Hi`.
- `DependencyInjectionTestExecutionListener` tiêm field vào test instance trước khi JUnit gọi `@BeforeEach`.
- `SpringExtension` đóng vai `ParameterResolver`, cung cấp tham số `@Autowired GreetingService` cho method.
- `assertSame` phù hợp vì `GreetingService` là singleton mặc định; với bean scoped/proxy, cách kiểm tra identity phải xét hợp đồng của bean.
- Context đã nạp thành công và trả đúng greeting; tuy nhiên chưa có HTTP/database nên test không chứng minh chúng.

### 6.7. Test D — Constructor injection cho JUnit test instance

**`src/test/java/example/GreetingConstructorTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestConstructor;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("test")
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class GreetingConstructorTest {
    private final GreetingService service;

    GreetingConstructorTest(GreetingService service) {
        this.service = service;
    }

    @Test
    void receivesBeanThroughConstructor() {
        assertEquals("Hi, Linh!", service.greet("Linh"));
    }
}
```

`@TestConstructor(autowireMode=ALL)` yêu cầu Spring cung cấp các tham số constructor của test instance. Ngoài ra có thể gắn `@Autowired` trực tiếp trên constructor khi muốn toàn bộ constructor được autowire. Nếu không gắn bất kỳ annotation nào, mặc định JUnit không biết phải resolve `GreetingService` như thế nào, trừ khi cấu hình autowire mode toàn cục đã đổi.

### 6.8. Chạy bằng wrapper

```bash
./gradlew test
./gradlew test --tests example.GreetingServiceUnitTest
./gradlew test --tests example.GreetingSmallContextTest
./gradlew test --tests example.GreetingBootContextTest
./gradlew test --tests example.GreetingConstructorTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.GreetingBootContextTest
```

Kết quả dự kiến là **5 lần thực thi test thành công**: A = 1, B = 1, C = 2, D = 1. Không có stdout nghiệp vụ cố định; build tool thông báo `BUILD SUCCESSFUL` khi các test đều pass và không có lỗi task khác. Không gọi trực tiếp `javac` cho test nếu chưa cung cấp toàn bộ JUnit/Spring test classpath; Gradle là cách đáng tin hơn trong ví dụ này.

Hai class Boot test C và D có cấu hình tương đương nên **có thể tái sử dụng cùng một context** nếu chạy trong cùng JVM và cache còn hiệu lực. Context nhỏ của B khác cấu hình nên có context riêng.

## 7. Field, constructor và parameter injection khác nhau ra sao?

### 7.1. Field injection vào test object

```java
@Autowired
GreetingService service;
```

JUnit khởi tạo test instance, Spring TestContext chuẩn bị instance bằng listener DI mặc định và inject field trước lúc test cần dùng nó. Phù hợp cho test ngắn. Nếu quên SpringExtension hoặc thiếu bean, field có thể null hoặc context fail trước khi test chạy.

### 7.2. Constructor injection

```java
@Autowired
MyTest(GreetingService service) {
    this.service = service;
}
```

Đây là **mảnh cú pháp**, cần field và context thực. Với constructor được đánh dấu `@Autowired`, SpringExtension resolve toàn bộ constructor parameters. `@TestConstructor(autowireMode=ALL)` là lựa chọn khác. Injection xảy ra khi JUnit tạo test instance nên có thể kích hoạt nạp context sớm.

**Đặc biệt:** nếu dùng JUnit `@TestInstance(PER_CLASS)` cùng `@DirtiesContext` đóng context trước/sau từng method, constructor-injected bean reference có thể còn trỏ tới bean của context đã đóng. Tránh tổ hợp này hoặc dùng field/setter injection phù hợp để Spring có thể reinject.

### 7.3. Tiêm vào `@Test` hoặc `@BeforeEach`

```java
@Test
void checksService(@Autowired GreetingService service) {
    assertEquals("Hi, Mai!", service.greet("Mai"));
}

@BeforeEach
void hasContext(@Autowired ApplicationContext context) {
    assertNotNull(context);
}
```

Đoạn này phải đặt trong test class đã tích hợp SpringExtension với profile `test` như ví dụ. `SpringExtension` implement Jupiter `ParameterResolver`; các tham số như `ApplicationContext` có thể được nhận biết theo type, còn với bean ứng dụng nên dùng `@Autowired`/`@Qualifier` để chỉ rõ.

Có thể tiêm property:

```java
@Test
void readsProperty(@Value("${lesson.prefix}") String prefix) {
    assertEquals("Hi", prefix);
}
```

Phải import `org.springframework.beans.factory.annotation.Value` và có context với property tương ứng. `@Value` trên tham số là một cách đưa cấu hình vào method test, không phải phương pháp thay thế mọi assert.

### 7.4. Khi có nhiều bean cùng kiểu

Nếu context có hai bean `PaymentGateway`, `@Autowired PaymentGateway gateway` có thể dẫn đến `NoUniqueBeanDefinitionException`. Hãy dùng `@Qualifier("gatewayName")`, một bean được `@Primary` hợp lý, hoặc nạp context chỉ gồm đúng implementation test cần. Đừng thay production configuration tùy tiện chỉ để làm một test xanh.

## 8. Thứ tự thực thi của JUnit và Spring listeners

Có ít nhất ba loại mốc: lifecycle method của JUnit (`@BeforeAll`, `@BeforeEach`…), callback extension của Jupiter (`beforeEach`, `beforeTestExecution`…), và sự kiện `TestContextManager` dành cho Spring listeners.

Sơ đồ **thứ tự khái quát**:

```text
JUnit discovery / register SpringExtension
  |
  +--> SpringExtension.beforeAll
  |      -> TestContextManager.beforeTestClass
  +--> JUnit @BeforeAll
  |
  +--> Tạo test instance
  |      -> constructor injection nếu được khai báo
  +--> SpringExtension.postProcessTestInstance
  |      -> TestContextManager.prepareTestInstance
  |      -> DependencyInjectionTestExecutionListener
  |
  +--> SpringExtension.beforeEach
  |      -> TestContextManager.beforeTestMethod
  |      -> listener có thể mở transaction
  +--> JUnit @BeforeEach
  +--> SpringExtension.beforeTestExecution
  |      -> TestContextManager.beforeTestExecution
  +--> JUnit @Test
  +--> SpringExtension.afterTestExecution
  |      -> TestContextManager.afterTestExecution
  +--> JUnit @AfterEach
  +--> SpringExtension.afterEach
  |      -> TestContextManager.afterTestMethod
  |      -> listener có thể rollback transaction
  |
  +--> JUnit @AfterAll
  +--> SpringExtension.afterAll
         -> TestContextManager.afterTestClass
```

Đây là bản đồ vòng đời, không phải cam kết thứ tự tuyệt đối của **mọi listener/extension** khi test có nhiều extension. Các listener có order riêng; context có thể được tạo ở bất kỳ mốc nào sớm hơn khi framework cần nó. Điều quan trọng để viết test:

- Field injection vào test instance thường hoàn tất trước `@BeforeEach`.
- `@BeforeEach` chuẩn bị fixture riêng cho test method; `@AfterEach` dọn fixture phù hợp.
- `beforeTestMethod` khác `beforeTestExecution`: callback thứ hai sát ngay trước khi code `@Test` chạy.
- Lỗi tạo context có thể xuất hiện **trước khi bước Act hay assertion trong `@Test` thực thi**.

### 8.1. Những listener mặc định thường gặp

`DependencyInjectionTestExecutionListener` xử lý field/setter injection; `TransactionalTestExecutionListener` xử lý test transaction; `SqlScriptsTestExecutionListener` hỗ trợ `@Sql`; các listener liên quan `@DirtiesContext` đánh dấu, loại bỏ hoặc đóng context theo lifecycle.

Khi thêm listener tùy chỉnh bằng `@TestExecutionListeners`, phải hiểu **cách merge với listener mặc định**. Nếu vô tình ghi đè hoàn toàn default listeners, tính năng DI, transaction hoặc SQL vốn đang hoạt động có thể biến mất.

## 9. Context caching và chia sẻ singleton

Spring TestContext duy trì cache context **tĩnh trong JVM test**. Từ cấu hình hợp nhất, Spring tính cache key; hai test dùng cấu hình tương thích có thể dùng chung một `ApplicationContext` thay vì load lại.

Cache key chịu ảnh hưởng bởi các thành phần như:

- `classes`, `locations` của context configuration.
- Active profiles từ `@ActiveProfiles`.
- Property sources hoặc inline properties.
- Initializers, context loader, parent context.
- Context customizers, ví dụ mock/bean override hoặc dynamic properties.
- Web resource base path khi có web context.

```text
BootContextTest:
    classes=DemoApplication, profile=test, web=NONE
                          |
                          +--> context A

ConstructorTest:
    classes=DemoApplication, profile=test, web=NONE
                          |
                          +--> có thể dùng lại context A

StagingProfileTest:
    classes=DemoApplication, profile=staging, web=NONE
                          |
                          +--> context B (key khác)
```

Không suy ra “mỗi test class một context” hoặc “một context toàn suite”. Dùng `@SpringBootTest(properties=...)` khác nhau, những tập mocks khác nhau, `@DirtiesContext` hoặc Gradle forks/process khác nhau có thể làm test load nhiều context.

### 9.1. Cache không xóa state trong singleton

Nếu bean singleton chứa `Map` mutable, một test có thể sửa nó, test sau nhìn thấy cùng dữ liệu khi context được cache. Phải reset state bằng fixture phù hợp, thiết kế bean stateless, hoặc cô lập database/transaction. `@DirtiesContext` chỉ là lựa chọn khi thực sự cần loại bỏ/recreate context, không phải cách dọn dữ liệu mặc định.

### 9.2. `@DirtiesContext`

```java
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutatingIT {
    // Test có lý do thực sự để đóng context sau class.
}
```

Đây là **mẫu minh họa**, cần Spring test annotations/imports và test context thực. `@DirtiesContext` làm Spring loại context khỏi cache ở mốc đã chỉ định; các test sau có thể phải bootstrap lại. Dùng vô tội vạ làm suite chậm, đôi khi che vấn đề state leakage thực tế.

### 9.3. Context failure threshold

Từ Spring Framework 6.1, TestContext có cơ chế **context failure threshold** mặc định là 1 cho một cache key. Nếu nạp context đã thất bại, các yêu cầu lặp lại cùng key có thể bị bỏ qua sớm với thông báo threshold. Khi đọc log suite, hãy tìm **lỗi nạp context gốc đầu tiên**, không chỉ các thông báo “preemptively skipped”.

Có thể cấu hình `spring.test.context.failure.threshold` theo tài liệu framework, nhưng tăng threshold không sửa lỗi bean/profile/dependency.

## 10. Profiles, properties và cấu hình test

### 10.1. `@ActiveProfiles`

`@ActiveProfiles("test")` cho phép chọn profile `test`; với Spring Boot, nó giúp `application-test.properties` của ví dụ được sử dụng. Profile chỉ chọn cấu hình, **không tự đảm bảo** mọi external service hoặc database được cách ly khỏi production.

### 10.2. `@TestPropertySource`

Ví dụ thêm một test class riêng cho override:

```java
@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@TestPropertySource(properties = "lesson.prefix=Salut")
class OverridePropertyTest {
    @Autowired GreetingService service;

    @Test
    void usesCustomProperty() {
        assertEquals("Salut, Mai!", service.greet("Mai"));
    }
}
```

Đây là **ví dụ rút gọn** cần imports từ JUnit và Spring, không nằm trong bốn test runnable ở mục 6. Ngoài `@TestPropertySource`, `@SpringBootTest(properties=...)` cũng hỗ trợ inline test properties. Những giá trị này có thể đổi cache key; không thay property tùy tiện ở từng test nếu không cần.

### 10.3. `@TestConfiguration`, `@Import`, test doubles

Spring Boot có `@TestConfiguration` để khai báo bean hỗ trợ test. Có thể import cấu hình này bằng `@Import` hoặc đặt trong class test theo cơ chế Boot hỗ trợ. Không nên giả định cứ khai báo cùng bean name là tự động thay bean production: tùy cấu hình, bean overriding có thể bị từ chối.

Khi cần thay một collaborator bằng mock trong Spring context, dùng cơ chế bean override đúng phiên bản: Spring Boot 3.3 thường có `@MockBean`; từ Spring Framework 6.2 có `@MockitoBean`, và khi lên Boot 4 cần cập nhật package/module test tương ứng. Mockito mock cho unit test có thể dùng `mock(...)` trực tiếp mà không cần Spring TestContext.

## 11. Test transaction và rollback

**`@SpringBootTest` không tự khiến mọi test rollback.** Spring TestContext hỗ trợ test-managed transaction cho test được đánh dấu `@Transactional` khi có transaction manager phù hợp; mặc định transaction ấy rollback sau test.

```java
@SpringBootTest
@Transactional
class AccountRepositoryIT {
    @Autowired
    AccountRepository repository;

    @Test
    void changesAreRolledBackByTestTransaction() {
        // Gọi repository, assert dữ liệu trong test transaction.
        // Rollback mặc định sau test method.
    }
}
```

Đây là **skeleton**, cần ứng dụng có JPA/database/repository/transaction manager và imports. Nó không chạy với project Greeting ở mục 6 vì ví dụ đó không có database.

Những ranh giới cần nhớ:

- Với transactional test, `@BeforeEach` và `@AfterEach` thông thường chạy trong test-managed transaction.
- `@BeforeAll`, `@AfterAll` không nằm trong transaction theo từng method ấy.
- `@BeforeTransaction` và `@AfterTransaction` là các hook của Spring chạy ngoài test transaction khi áp dụng.
- `@Commit` hoặc `@Rollback(false)` thay đổi hành vi rollback mặc định có chủ đích.
- Với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, HTTP server xử lý ở thread/transaction khác; rollback của test thread **không tự rollback** các transaction mà server đã commit.
- JUnit `assertTimeoutPreemptively(...)` có thể chạy code trên thread khác nên làm mất ranh giới transaction gắn với thread test; không dùng tùy tiện nếu đang dựa vào rollback.

**Context lifecycle khác transaction lifecycle:** context có thể dùng chung qua nhiều test, trong khi test transaction thường mở/đóng riêng cho từng method. Việc đóng context không phải cơ chế thay thế rollback.

## 12. Debug lỗi nạp context hoặc tiêm phụ thuộc

### 12.1. `@Autowired` vẫn null

Nguyên nhân thường là test chỉ dùng JUnit mà chưa tích hợp SpringExtension, hoặc tự tạo test object bằng `new` ngoài JUnit. Kiểm tra annotation/class test và listener DI. Nếu test chỉ cần service logic, tạo service bằng `new` và bỏ field injection là hợp lý; nếu cần bean thật, dùng đúng context test.

### 12.2. `Unable to find a @SpringBootConfiguration`

Boot không tìm được class `@SpringBootApplication` từ vị trí package test theo cơ chế tìm kiếm cấu hình. Đặt test trong package phù hợp hoặc chỉ định `@SpringBootTest(classes=DemoApplication.class)`; không mở rộng component scan bừa bãi.

### 12.3. `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException`

Có thể thiếu dependency của bean, sai profile, thiếu `@Bean`, component scan không phủ package, conditional config không kích hoạt hoặc test slice loại bean ấy. Tìm bean đầu tiên không thể tạo, so với phạm vi context đang nạp. Một `@SpringJUnitConfig` chỉ chứa formatter sẽ không tự tạo service nếu không đăng ký service bằng `@Bean`/component scan.

### 12.4. `NoUniqueBeanDefinitionException`

Có nhiều bean cùng kiểu và Spring không chọn được. Dùng `@Qualifier`, `@Primary` hoặc cấu hình scope test nhỏ thích hợp. Không sửa production wiring một cách tùy ý nếu test đang cần lựa chọn rõ ràng.

### 12.5. `No ParameterResolver registered for parameter ...`

JUnit không biết cung cấp tham số constructor/method. Kiểm tra `SpringExtension` đã đăng ký chưa; annotation `@Autowired` hoặc `@TestConstructor(ALL)` đã có chưa; kiểu tham số có thể được Spring resolve từ context không. Với constructor thuộc test class, annotation/chiến lược autowire quan trọng hơn việc bean tồn tại đơn thuần.

### 12.6. Lỗi datasource/secret/client khi context tạo

Một bean có thể yêu cầu DB URL, credential hoặc gọi network trong init. Lỗi nằm **trước `@Test`**, không phải assertion. Kiểm tra active profile/test properties, dependency ngoài và cách mock/đưa test configuration phù hợp. Đừng cho phép test dùng database production để “chữa” lỗi nhanh.

### 12.7. Đọc triệu chứng đúng tầng

| Triệu chứng | Nơi nên điều tra |
| --- | --- |
| `No tests found` | JUnit Platform/engine, import `@Test`, filter/build task |
| `Failed to load ApplicationContext` | Bean graph, profiles, properties, context loader, external resources |
| `No ParameterResolver` | SpringExtension, constructor injection mode, parameter annotation |
| Field `@Autowired` null | Test instance chưa được Spring TestContext chuẩn bị |
| Nhiều bean cùng kiểu | `@Qualifier`, `@Primary`, test configuration |
| Test fail “ApplicationContext failure threshold exceeded” | Lỗi load context đầu tiên cùng cache key |
| Context xanh nhưng behavior sai | Test thiếu assertion hoặc code nghiệp vụ sai |
| Suite nạp context rất nhiều lần | Cache key khác, `@DirtiesContext`, JVM forks/process khác |
| DB không rollback | Thiếu test transaction hoặc request nằm ngoài thread/transaction ấy |

## 13. Quan sát và đánh giá một test đã nạp đúng bean

Trong test Boot ở mục 6:

```java
@Autowired
ApplicationContext context;

@Autowired
GreetingService service;

@Test
void verifiesManagedBean() {
    assertNotNull(context);
    assertSame(context.getBean(GreetingService.class), service);
    assertEquals("Hi, Mai!", service.greet("Mai"));
}
```

Đoạn này phải đặt trong class có cấu hình `@SpringBootTest` và profile `test`, với imports JUnit. Test xác minh bean hiện diện, cùng instance singleton và có hành vi mong đợi. Chỉ `assertNotNull(context)` chưa đủ, vì một context nạp thành công có thể vẫn thiếu bean/logic cần kiểm tra.

Khi test chậm hoặc fail, chạy test riêng bằng wrapper:

```bash
./gradlew test --tests example.GreetingBootContextTest
./gradlew test --info
```

Nhìn báo cáo task/test và **stack trace lỗi gốc**. Nếu cần log về context cache, bật mức DEBUG cho thành phần Spring TestContext cache bằng cấu hình logging test phù hợp; không cần in toàn bộ Environment vì có thể chứa bí mật.

## 14. Bài tập thực hành theo trình tự

**Bài 1 — JUnit không có Spring.** Chạy `GreetingServiceUnitTest`, rồi tạm làm sai `GreetingFormatter.format` (bỏ dấu chấm than). Assertion phải đỏ. Khôi phục code. Giải thích tại sao điều này chứng minh logic nhưng không chứng minh wiring.

**Bài 2 — Spring context nhỏ.** Chạy `GreetingSmallContextTest`. Đổi formatter `Bonjour` thành `Salut` và điều chỉnh assertion. Liệt kê hai bean mà `TestConfig` khai báo. Vì sao `application-test.properties` không chi phối test này?

**Bài 3 — Profile và Boot properties.** Chạy `GreetingBootContextTest`, đổi `lesson.prefix=Hi` thành `Hello-Test` trong `application-test.properties`. Test xanh khi expected được cập nhật đúng contract. Bỏ `@ActiveProfiles("test")` trong nhánh thử: giá trị sẽ theo cấu hình khác. Khôi phục.

**Bài 4 — Injection timing.** Chạy `GreetingConstructorTest`, bỏ thử `@TestConstructor(autowireMode=ALL)` để quan sát lỗi resolve constructor (trong cấu hình mặc định). Thêm lại; mô tả thời điểm JUnit tạo test instance và thời điểm field injection hoàn tất.

**Bài 5 — Cache vs. test state.** Tạo singleton in-memory counter cho bài thực hành. Cho hai test method dùng cùng context và thay đổi counter. Chỉ ra vì sao state có thể rò qua test; tìm giải pháp reset fixture thay vì mặc định gắn `@DirtiesContext`.

**Bài 6 — Chẩn đoán lỗi.** Được cung cấp một test đỏ, trước khi sửa phải phân loại: runner không thấy test, thiếu resolver, không tìm Boot config, thiếu bean, lỗi phụ thuộc ngoài, hay assertion nghiệp vụ sai. Ghi bằng chứng từ lỗi gốc và thay đổi nhỏ nhất cần thiết.

## 15. Checklist trước khi đánh dấu hoàn thành

- [ ] Test có mục tiêu rõ: logic Java, bean wiring, Boot auto-configuration, adapter hay toàn luồng.
- [ ] Tôi chọn phạm vi context nhỏ nhất vẫn chứng minh hành vi.
- [ ] Tôi biết annotation nào đăng ký SpringExtension cho Jupiter.
- [ ] Tôi phân biệt test instance JUnit với singleton bean Spring.
- [ ] Tôi biết test configuration classes, profiles và properties thực tế.
- [ ] Tôi biết field injection, constructor injection và method parameter injection diễn ra qua cơ chế nào.
- [ ] Test fixture đã được inject trước khi `@BeforeEach`/`@Test` sử dụng.
- [ ] Tôi không mặc định mỗi method có một context mới.
- [ ] Mutable singleton state được cô lập/reset đúng cách; `@DirtiesContext` chỉ dùng khi cần.
- [ ] Nếu dùng `@Transactional`, tôi biết transaction bắt đầu/kết thúc ở đâu, server HTTP có cùng transaction hay không.
- [ ] Test có assertion về hành vi có ý nghĩa, không chỉ `contextLoads`.
- [ ] Tôi kiểm tra Java/build tool/JUnit/Spring Boot versions và lỗi khởi tạo context đầu tiên.
- [ ] Test không phụ thuộc secrets, database production, thứ tự chạy hoặc mutable state chưa dọn.

## 16. Bản đồ quyết định

```text
Chỉ cần kiểm tra logic?
    └─ JUnit thuần; new đối tượng, mock/fake dependency.

Cần Spring quản lý vài bean?
    └─ @SpringJUnitConfig / @ContextConfiguration + SpringExtension.

Cần Spring Boot bootstrap, profiles hoặc auto-config?
    └─ @SpringBootTest, webEnvironment phù hợp.

Chỉ cần một mảnh framework?
    ├─ @WebMvcTest cho HTTP MVC.
    └─ @DataJpaTest cho JPA.

Khi có TestContext:
 JUnit -> SpringExtension -> TestContextManager
       -> cache / context loader -> ApplicationContext
       -> inject test fixture -> lifecycle callbacks
       -> @Test assertions -> cleanup/transaction.
```

**Thông điệp trọng tâm:** Spring TestContext là cầu nối giữa vòng đời của test runner và vòng đời của Spring IoC container. Hiểu cách context được dựng hoặc tái sử dụng, cách dependencies đi vào test instance và cách các listeners tham gia trước/sau `@Test` giúp bạn vừa xác minh wiring thật, vừa tránh những integration test nặng không cần thiết.

## 17. Tài liệu chính thức

- Spring Framework — TestContext Framework: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html
- Spring Framework — Key Abstractions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/key-abstractions.html
- Spring Framework — `SpringExtension` / parameter injection: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html
- Spring Framework — Dependency Injection of Test Fixtures: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/fixture-di.html
- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Context Failure Threshold: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- JUnit User Guide: https://docs.junit.org/current/user-guide/

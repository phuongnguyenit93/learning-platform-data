# @SpringBootTest tải ứng dụng theo cơ chế Spring Boot như thế nào?

## 1. Bản chất: kiểm thử một ApplicationContext được tạo bởi SpringApplication

`@SpringBootTest` là annotation dùng cho **kiểm thử tích hợp với ngữ cảnh Spring Boot**. Thay vì khởi tạo một service thuần Java bằng `new`, bài test yêu cầu Spring TestContext tạo hoặc lấy lại một **`ApplicationContext`**; Spring Boot cung cấp bộ nạp sử dụng **`SpringApplication`**, tức cơ chế khởi tạo ứng dụng quen thuộc của Boot.

Ý quan trọng nhất:

> `@SpringBootTest` **không đơn thuần quét bean**, cũng **không mặc định gọi `main()`**. Nó yêu cầu Spring TestContext khởi tạo ngữ cảnh kiểm thử **qua SpringApplication**, dựa trên cấu hình gốc và các tùy chọn của test.

Điều đó mang theo cơ chế đặc trưng của Spring Boot: quản lý `Environment` và config data, kích hoạt profile, component scan, auto-configuration có điều kiện, binding `@ConfigurationProperties`, dependency injection, lifecycle của bean và — tùy `webEnvironment` — môi trường web mock hoặc server thật.

Kết quả học tập:

1. Diễn giải được chuỗi **JUnit Jupiter → SpringExtension → Spring TestContext → Spring Boot bootstrapper/loader → SpringApplication → ApplicationContext**.
2. Biết Boot tìm cấu hình gốc `@SpringBootApplication` / `@SpringBootConfiguration` như thế nào.
3. Phân biệt **SpringApplication chạy** với **phương thức `main()` được gọi**.
4. Chọn đúng `webEnvironment = MOCK / RANDOM_PORT / DEFINED_PORT / NONE` và hiểu lúc nào server thật chạy.
5. Viết và chạy được ví dụ Java 17+ minh họa context loading, config/profile, MockMvc và HTTP thật.
6. Giải thích context caching, nguyên nhân khởi động chậm, startup failure, vấn đề transaction và khác biệt với unit test hoặc test slice.

## 2. Ai thật sự kích hoạt việc tải ứng dụng?

Một class tối giản:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationSmokeTest {
    @Test
    void contextLoads() {
        // Không cần assertion để nhìn thấy lỗi khởi tạo context.
    }
}
~~~

Đây là **khung minh họa**, chưa phải file chạy độc lập: dự án phải có application configuration được Spring Boot tìm thấy, JUnit Platform và các dependencies cần thiết. Test có thể PASS vì context khởi động được, nhưng **một phương thức rỗng không chứng minh nghiệp vụ đúng**. Một bài smoke test nên được bổ sung các assertion có ý nghĩa.

Cơ chế ở mức khái niệm:

~~~text
JUnit Jupiter tìm thấy @Test
  |
  v
SpringExtension tích hợp vào lifecycle JUnit
  |
  v
Spring TestContext Framework
  |  - quản lý test instance
  |  - chuẩn bị dependency injection, listeners
  |  - tìm hoặc lấy ApplicationContext từ cache
  v
SpringBootTestContextBootstrapper
  |  - phân tích annotation/cấu hình test
  |  - tìm primary Boot configuration
  |  - chuẩn bị context customizers, properties, profiles
  v
SpringBootContextLoader
  |
  v
SpringApplication
  |  - chuẩn bị Environment và config data
  |  - chọn kiểu ứng dụng web/non-web
  |  - tạo context và load bean definitions
  |  - refresh; tạo beans, áp dụng auto-configuration
  |  - chạy những lifecycle callbacks phù hợp
  v
ApplicationContext sẵn sàng cho các @Test
  |
  v
@Autowired / assertions / MockMvc hoặc HTTP client
~~~

Các mũi tên là **mô hình diễn giải**, không phải thứ tự gọi từng Java method nội bộ. Spring Boot và Spring Framework có thể thay đổi chi tiết implementation giữa phiên bản, nhưng kiến trúc **TestContext + Boot context loader + SpringApplication** là điểm cốt lõi.

### 2.1 Vai trò của từng thành phần

- **JUnit Jupiter** biết phương thức nào có `@Test`, tổ chức lifecycle và ghi PASS/FAIL.
- **`SpringExtension`** nối JUnit Jupiter với Spring TestContext để hỗ trợ dependency injection, callbacks và lifecycle của test.
- **Spring TestContext Framework** tạo/cấu hình test context, áp dụng `TestExecutionListener`, quản lý transaction kiểm thử và cache context khi phù hợp.
- **`SpringBootTestContextBootstrapper`** hiểu thiết lập Boot cho bài test, chẳng hạn cấu hình gốc, properties, các context customizers.
- **`SpringBootContextLoader`** dùng `SpringApplication` để tải context, nhờ đó các khả năng khởi động đặc trưng Boot được áp dụng.
- **`SpringApplication`** chuẩn bị môi trường, chạy các bước khởi động, tạo/refresh context, kích hoạt auto-configuration theo classpath và điều kiện, trả về context sẵn sàng.

Với **JUnit Jupiter**, `@SpringBootTest` đã tích hợp `SpringExtension`; thông thường **không cần thêm `@ExtendWith(SpringExtension.class)`**. Nếu thấy ví dụ JUnit 4 dùng `@RunWith(SpringRunner.class)`, đừng trộn cơ chế runner cũ vào JUnit Jupiter.

### 2.2 Tại sao test chỉ chạy được sau khi context tạo thành công?

Các phương thức test dùng `@Autowired` cần bean đã được tạo hoặc có thể resolve. Nếu cấu hình lỗi, bean phụ thuộc nhau vòng lặp, không kết nối được database hoặc property bắt buộc thiếu, Spring có thể báo **“Failed to load ApplicationContext”** trước khi đi vào assertion. Đây là **lỗi khởi động môi trường kiểm thử**, không tự chứng minh logic method test sai.

Ngược lại, một context khởi động thành công chỉ chứng minh **tập bean và cấu hình được chọn có thể được tải**; chưa chứng minh HTTP mapping, transaction, SQL và nghiệp vụ đều chính xác.

## 3. Spring Boot xác định ứng dụng cần tải bằng cách nào?

Nếu bạn viết:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {
    // ...
}
~~~

và **không khai báo `classes = ...`**, Boot cần tìm nguồn cấu hình chính. Theo cơ chế mặc định, nó đi **từ package của test lên các package cha** để tìm class được đánh dấu `@SpringBootApplication` hoặc `@SpringBootConfiguration`.

Ví dụ:

~~~text
src/main/java/com/acme/shop/ShopApplication.java
    package com.acme.shop;                 @SpringBootApplication

src/main/java/com/acme/shop/order/OrderService.java
    package com.acme.shop.order;           @Service

src/test/java/com/acme/shop/order/OrderServiceIntegrationTest.java
    package com.acme.shop.order;           @SpringBootTest
~~~

Test trong `com.acme.shop.order` có thể tìm `ShopApplication` tại `com.acme.shop`, rồi tải cấu hình gốc, component scanning và auto-configuration của ứng dụng.

**Lỗi kinh điển:** đặt test ở `com.other.tests` không thuộc package hierarchy của application, rồi nhận lỗi kiểu:

~~~text
Unable to find a @SpringBootConfiguration
~~~

Không nên chữa bằng cách thêm `@ComponentScan("...")` tùy tiện hoặc chuyển mọi class về package root. Các cách đúng là đặt test đúng package hierarchy **hoặc** khai báo rõ source:

~~~java
@SpringBootTest(classes = ShopApplication.class)
class OrderServiceIntegrationTest {
}
~~~

Đoạn này là **mã minh họa trong dự án có `ShopApplication`**, không phải file tự biên dịch. `classes` nói cho Boot biết configuration chính, nhưng **không gọi `ShopApplication.main()` theo mặc định**.

### 3.1 @SpringBootApplication gồm những cơ chế gì?

Về chức năng, `@SpringBootApplication` kết hợp:

- `@SpringBootConfiguration`: đánh dấu cấu hình Spring Boot chính (được xây trên Spring `@Configuration`).
- `@EnableAutoConfiguration`: kích hoạt lựa chọn các auto-configuration class **có điều kiện**.
- `@ComponentScan`: quét các component trong package phù hợp.

Thành phần được load phụ thuộc **classpath, property, profile, conditional annotations, component scan, các bean đã khai báo và những exclude/customization**. Vì vậy, “@SpringBootTest tải toàn bộ ứng dụng” là cách nói ngắn: chính xác hơn là nó tải **ApplicationContext dựa trên cấu hình gốc đầy đủ theo những điều kiện có hiệu lực trong test**. Một bean `@Profile("prod")` sẽ không xuất hiện nếu profile test không đáp ứng; một auto-configuration có thể không tạo bean khi classpath thiếu dependency.

### 3.2 @Configuration lồng trong test khác @TestConfiguration

Với bài test Spring Boot có cấu hình chính tìm tự động:

- Một **nested `@TestConfiguration`** thường được dùng để **bổ sung** bean test bên cạnh cấu hình chính.
- Một **nested `@Configuration`** trực tiếp trong test có thể được xem là cấu hình chính **thay thế** cơ chế tự tìm app gốc, làm tập bean test khác điều bạn nghĩ.
- Nếu muốn chủ động thay nguồn cấu hình, hãy khai báo `@SpringBootTest(classes = ...)` và hiểu rõ tập config được chọn.
- Với test slices, các cơ chế exclude và scanning còn khác; tránh đặt `@ComponentScan` tùy chỉnh lên root app mà vô tình làm bộ lọc slice mất tác dụng.

Ví dụ bổ sung một bean phục vụ test (đoạn minh họa, cần interface `Clock` và import phù hợp):

~~~java
@SpringBootTest
class InvoiceTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class TestClockConfiguration {
        @Bean
        Clock fixedClock() {
            return Clock.fixed(
                    Instant.parse("2026-01-01T00:00:00Z"),
                    ZoneOffset.UTC);
        }
    }

    // @Autowired Clock clock;
}
~~~

`@TestConfiguration` lấy từ `org.springframework.boot.test.context.TestConfiguration`; `@Bean` từ Spring, còn `Clock`/`Instant`/`ZoneOffset` thuộc `java.time`. **Không mặc định khai báo bean trùng tên với production bean** khi Spring Boot không cho bean-definition overriding; nếu muốn thay một dependency, hãy dùng qualifier, profile, cấu hình test rõ ràng hoặc bean override của Spring test tương thích phiên bản.

## 4. SpringApplication chuẩn bị ApplicationContext theo những giai đoạn nào?

Một ứng dụng chạy thông thường có:

~~~java
@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@SpringBootTest` dùng `SpringApplication` để tạo context, vì vậy các bước sau nhìn chung cũng liên quan:

1. **Chọn nguồn cấu hình:** class gốc tìm được hoặc được chỉ định trong `classes`.
2. **Chuẩn bị Environment:** kết hợp config data, `application.properties`/YAML, profile-specific files, OS env, JVM system properties và test overrides.
3. **Xác định loại web application:** theo classpath và `webEnvironment`; Spring MVC có thể ưu tiên khi cả MVC lẫn WebFlux cùng hiện diện.
4. **Tạo ApplicationContext phù hợp:** non-web, servlet hoặc reactive context theo cấu hình.
5. **Nạp bean definitions:** từ `@Configuration`, component scan, imports và auto-configuration classes.
6. **Đánh giá conditions:** ví dụ `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` quyết định bean nào được tạo.
7. **Refresh context:** giải quyết dependency injection, tạo các singleton eager, chạy bean lifecycle callbacks, post-processors, AOP proxy và các thành phần được cấu hình.
8. **Hoàn tất vòng đời khởi động:** một số bean có `@PostConstruct`, listener hoặc runner có thể thực thi; HTTP server có thể được khởi tạo nếu mode yêu cầu.
9. **Trao context cho TestContext:** Spring có thể inject field/constructor/parameter của test và chạy test methods.

Đây là **mô hình logic**, không cam kết mọi bean được khởi tạo ngay: `@Lazy`, scope, conditional auto-config, repository và client có thể trì hoãn một phần công việc. Các sự kiện và callback thực tế phụ thuộc phiên bản và cấu hình.

**Hệ quả:** dùng `@SpringBootTest` có thể làm chạy code **ngoài method `@Test`**, chẳng hạn migrations Flyway/Liquibase, bean khởi tạo scheduler, ApplicationRunner, listener, kết nối hạ tầng hoặc kiểm tra config. Vì vậy “chỉ có một test rỗng” không đồng nghĩa “không có side effect nào trong khi load context”.

### 4.1 Vì sao @ContextConfiguration không nhất thiết tương đương?

Spring TestContext có thể tạo một context thuần Spring bằng `@ContextConfiguration` và `ContextLoader` khác. Điều đó hữu ích khi chỉ muốn một vài bean Java config hoặc XML.

`@SpringBootTest` chọn đường Boot để tạo context qua `SpringApplication`, nên tính năng **externalized configuration, Boot auto-configuration, logging/bootstrap và web environment** đi theo cơ chế Boot. Nếu mục đích là chứng minh đúng cấu hình ứng dụng Boot chạy được, `@SpringBootTest` thường phù hợp hơn một `@ContextConfiguration` chỉ nạp vài bean tự khai báo.

Tuy nhiên, `@SpringBootTest` không phải lựa chọn nhanh nhất cho mọi bài test. Logic thuần Java nên được unit-test không cần Spring; controller slice hoặc persistence slice có annotation riêng khi muốn giới hạn phạm vi.

## 5. Một chi tiết rất dễ nhầm: @SpringBootTest mặc định KHÔNG gọi main()

Vì SpringApplication đang được dùng, nhiều người suy luận rằng:

> “Khi test có @SpringBootTest, Boot gọi hàm `main(String[] args)` rồi khởi động như chạy JAR.”

**Không đúng theo mặc định.** Kể từ API `useMainMethod` của Spring Boot 3.x, giá trị mặc định là:

~~~java
@SpringBootTest(useMainMethod = SpringBootTest.UseMainMethod.NEVER)
~~~

`NEVER` nghĩa là **không gọi phương thức `main()`**, mà dùng application class làm source để tạo `SpringApplication` và chạy bootstrap phù hợp. Vì thế:

- Bean declarations, component scan và auto-configuration vẫn có hiệu lực.
- Mã tùy chỉnh bạn **chỉ đặt bên trong `main()`** có thể không được áp dụng cho test mặc định.
- Không dựa vào side effect như `System.setProperty(...)` hoặc một `SpringApplicationBuilder` tùy biến đặt độc nhất trong `main()` khi đang test bằng mode mặc định.

Nếu việc tùy biến trong `main()` là một phần hành vi cần kiểm, có hai lựa chọn:

~~~java
@SpringBootTest(
        useMainMethod = SpringBootTest.UseMainMethod.WHEN_AVAILABLE)
class MainMethodWhenPresentTest {
}
~~~

~~~java
@SpringBootTest(
        useMainMethod = SpringBootTest.UseMainMethod.ALWAYS)
class MainMethodRequiredTest {
}
~~~

Đây là các **khung annotation**, cần đặt trong dự án có application class/method phù hợp. `WHEN_AVAILABLE` gọi `main()` nếu tìm được, nếu không thì fallback sang cơ chế tải chuẩn; `ALWAYS` yêu cầu có `main()` và fail nếu không thể tìm được.

**Khuyến nghị thiết kế:** những cấu hình quan trọng cho ứng dụng và test nên đặt ở configuration bean, config data hoặc hooks có hợp đồng rõ, không giấu trong `main()`. Chỉ chọn `useMainMethod = ALWAYS` khi test có mục tiêu rõ là xác minh cách main tùy biến SpringApplication; cần kiểm side effects, arguments và hạ tầng mà main bật.

## 6. webEnvironment quyết định mock hay server thật

`@SpringBootTest` có thuộc tính `webEnvironment`. Giá trị mặc định là **`MOCK`**, nhưng “mock” ở đây nói về **môi trường HTTP/Servlet** chứ không có nghĩa tất cả service/repository/controller trở thành Mockito mocks.

| webEnvironment | Context được tải | Server HTTP thật? | Khi nên dùng |
| --- | --- | --- | --- |
| `MOCK` (mặc định) | Web application context mock nếu có web stack; có thể fallback non-web nếu thiếu | **Không** | Kiểm bean và MVC với `@AutoConfigureMockMvc`, không mở TCP port |
| `RANDOM_PORT` | Web server application context | **Có**, chọn cổng khả dụng tự động | Test HTTP từ client thật, kiểm routing/serialization/filter/server |
| `DEFINED_PORT` | Web server application context | **Có**, cổng được cấu hình hoặc mặc định 8080 | Chỉ khi thật sự cần fixed port; dễ xung đột CI |
| `NONE` | ApplicationContext non-web qua SpringApplication | **Không** | Kiểm service, configuration, bean wiring mà không cần servlet/reactive server |

**`MOCK` không tự đồng nghĩa có sẵn `MockMvc`.** Trong test Spring MVC full-context, thêm `@AutoConfigureMockMvc` để auto-configure `MockMvc`. Các test slices như `@WebMvcTest` có cơ chế configure MockMvc riêng. Với Spring Boot 4.x, càng phải lưu ý đổi module/package và không dựa vào việc `@SpringBootTest` tự đưa MockMvc vào context.

### 6.1 RANDOM_PORT có nghĩa là gì?

Với servlet application và embedded server, Boot đặt `server.port=0` theo cơ chế random-port test để OS chọn một port khả dụng, rồi có thể inject cổng thực bằng `@LocalServerPort`. Chỉ **sau khi server bind** mới biết giá trị cổng thực; không hardcode 8080 trong test này.

Với HTTP thật, việc client và server ở **hai thread khác nhau** làm test-managed transaction của test method không tự bao phủ giao dịch diễn ra khi server xử lý request. Đây là điểm sẽ được phân tích ở mục 11.

### 6.2 MOCK vẫn có thể kiểm controller như HTTP request

`MockMvc` tạo request/response mock và gọi MVC stack trong cùng ứng dụng mà không cần mở socket hay dùng HTTP client thật. Nó vẫn có thể kiểm mapping, filters, validation và serialization trong phạm vi được cấu hình, nhưng không kiểm toàn bộ network stack, TLS, reverse proxy hoặc cấu hình port của server thật.

### 6.3 WebFlux và cả MVC + WebFlux trên classpath

Nếu chỉ có Spring WebFlux, Boot có thể tạo reactive web context. Khi **cả Spring MVC và WebFlux** có trong classpath, Spring MVC thường được chọn; để buộc test kiểm reactive web type, có thể đặt:

~~~java
@SpringBootTest(
    properties = "spring.main.web-application-type=reactive")
class ReactiveModeTest {
}
~~~

Đây là **đoạn annotation minh họa**, không phải test WebFlux độc lập. Cần có reactive dependencies và handler phù hợp; không phải cứ đặt property là cả ứng dụng MVC tự trở thành một ứng dụng reactive đúng chức năng.

## 7. Ví dụ hoàn chỉnh Java 17+: quan sát Boot load app, profile, MockMvc và HTTP thật

Bài thực hành gồm **một ứng dụng nhỏ thật** ở `src/main/java` và **ba test classes** ở `src/test/java`. Nó không cần database, Docker, network bên ngoài hay credentials. Dùng **Spring Boot 3.5.x, Java 17+, JUnit Jupiter** và `spring-boot-starter-web`. Các ví dụ version Spring Boot 4.x cần kiểm lại package/module test MVC theo migration guide thay vì sao chép import từ 3.5.

Ứng dụng có một `GreetingSettings` record được bind qua config data, `GreetingService` được component-scan và `GreetingController` cung cấp `GET /greet?name=Lan`. Chúng giúp test phân biệt “có bean”, “có profile/config binding”, “có MVC giả lập” và “có HTTP server thật”.

### 7.1 Cây thư mục

~~~text
src/
  main/
    java/
      example/bootstart/
        DemoApplication.java
        GreetingSettings.java
        GreetingService.java
        GreetingController.java
  test/
    java/
      example/bootstart/
        ContextLoadTest.java
        MockHttpTest.java
        RealHttpTest.java
    resources/
      application-test.properties
~~~

**Chú ý:** các test nằm **cùng package** với `DemoApplication` để Boot có thể tự tìm root configuration. Không khai báo `classes` trong annotation là chủ ý của bài thực hành, không phải bỏ sót.

### 7.2 Ứng dụng gốc: DemoApplication.java

~~~java
package example.bootstart;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(GreetingSettings.class)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` kích hoạt component scan trong `example.bootstart` và auto-configuration. `@EnableConfigurationProperties(GreetingSettings.class)` yêu cầu đăng ký/bind record cấu hình.

Vì `@SpringBootTest` **không cần gọi `main()` mặc định**, việc app vẫn khởi động được trong test thể hiện sự khác biệt giữa **dùng `SpringApplication` để bootstrap** và **gọi chính phương thức `main`**.

### 7.3 Record cấu hình: GreetingSettings.java

~~~java
package example.bootstart;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.greeting")
public record GreetingSettings(String prefix) {
}
~~~

Boot bind `demo.greeting.prefix` từ `Environment` thành `GreetingSettings.prefix()`. Nếu test thấy bean này có `prefix() == "Hello"`, ta biết **cấu hình đã được nạp và bind**, không chỉ có file nằm trong resources.

### 7.4 Service thật: GreetingService.java

~~~java
package example.bootstart;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final GreetingSettings settings;

    public GreetingService(GreetingSettings settings) {
        this.settings = settings;
    }

    public String greet(String name) {
        return settings.prefix() + ", " + name + "!";
    }
}
~~~

`@Service` là Spring component. Boot tìm được bean này qua `@ComponentScan` từ root app, rồi inject `GreetingSettings` được bind. Unit test có thể tạo `new GreetingService(new GreetingSettings("Hello"))`, nhưng bài này muốn chứng minh Boot **thật sự tạo và wire bean**.

### 7.5 Controller thật: GreetingController.java

~~~java
package example.bootstart;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet")
    public String greet(
            @RequestParam(defaultValue = "World") String name) {
        return service.greet(name);
    }
}
~~~

Controller được tạo bởi Spring, mapping `/greet` được xử lý bởi Spring MVC. Với `@RestController`, giá trị `String` được dùng làm HTTP response body, không phải tên view. Ví dụ không thêm Spring Security hoặc các filters tùy chỉnh.

### 7.6 File profile: application-test.properties

File `src/test/resources/application-test.properties`:

~~~properties
demo.greeting.prefix=Hello
demo.startup.check=from-profile
~~~

`@ActiveProfiles("test")` sẽ làm profile `test` hoạt động và giúp Spring Boot nạp config data theo profile. Giá trị `demo.startup.check` được dùng để minh họa một override bằng test annotation trong một test class.

### 7.7 Test 1: ContextLoadTest.java — Boot tạo context non-web

~~~java
package example.bootstart;

import java.util.Arrays;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ActiveProfiles("test")
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "demo.startup.check=from-annotation")
@DisplayName("SpringBootTest tải context bằng SpringApplication")
class ContextLoadTest {

    @Autowired
    ConfigurableApplicationContext context;

    @Autowired
    ApplicationArguments applicationArguments;

    @Autowired
    Environment environment;

    @Autowired
    GreetingSettings settings;

    @Autowired
    GreetingService service;

    @Test
    @DisplayName("Context sống và các bean production được wire")
    void contextAndRealBeansAreCreated() {
        assertAll(
                () -> assertTrue(context.isActive()),
                () -> assertNotNull(applicationArguments),
                () -> assertNotNull(context.getBean(DemoApplication.class)),
                () -> assertNotNull(context.getBean(GreetingService.class)),
                () -> assertEquals("Hello, Lan!",
                        service.greet("Lan")));
    }

    @Test
    @DisplayName("Profile test được nạp và test properties được áp dụng")
    void testProfileAndOverrideAreEffective() {
        assertAll(
                () -> assertTrue(Arrays.asList(
                        environment.getActiveProfiles()).contains("test")),
                () -> assertEquals("Hello", settings.prefix()),
                () -> assertEquals("Hello",
                        environment.getRequiredProperty(
                                "demo.greeting.prefix")),
                () -> assertEquals("from-annotation",
                        environment.getRequiredProperty(
                                "demo.startup.check")));
    }
}
~~~

**Hai test này chứng minh:**

- Context thực sự được **refresh và đang active**.
- Boot đăng ký các thành phần làm việc với `SpringApplication`, trong đó có `ApplicationArguments`.
- `DemoApplication` được dùng làm root configuration dù bài test không chỉ định `classes`.
- Service production được scan, khởi tạo và inject thành công.
- Profile `test` được bật, `GreetingSettings` đã bind từ config data.
- `@SpringBootTest(properties = ...)` cung cấp một giá trị test override cụ thể.

`webEnvironment = NONE` cố ý không khởi động HTTP server: vì thế các test này **không chứng minh endpoint `/greet` xử lý được request**.

### 7.8 Test 2: MockHttpTest.java — full context, giả lập HTTP với MockMvc

~~~java
package example.bootstart;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("test")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@DisplayName("SpringBootTest với MockMvc, không mở TCP port")
class MockHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    @DisplayName("GET /greet đi qua Spring MVC và controller thật")
    void controllerWorksInMockServletEnvironment() throws Exception {
        mvc.perform(get("/greet").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Lan!"));
    }
}
~~~

`MockHttpTest` khởi động **full application context** cho web MVC, nhưng `MockMvc` tạo request/response mock và đi qua MVC stack mà **không mở cổng HTTP thật**. `@AutoConfigureMockMvc` bổ sung cấu hình cần thiết; chỉ có `@SpringBootTest(webEnvironment = MOCK)` không nên được xem là bảo đảm có sẵn `MockMvc` trong mọi phiên bản.

Bài này khác `@WebMvcTest(GreetingController.class)`: `@WebMvcTest` là **slice** tập trung vào web và có thể cần mock hoặc import service; `@SpringBootTest` dùng cấu hình ứng dụng đầy đủ, do đó có `GreetingService` thật.

### 7.9 Test 3: RealHttpTest.java — mở HTTP server trên random port

~~~java
package example.bootstart;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ActiveProfiles("test")
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@DisplayName("SpringBootTest mở HTTP server thật")
class RealHttpTest {

    @LocalServerPort
    int port;

    @Test
    @DisplayName("HTTP GET tới server thật nhận dữ liệu từ service")
    void realServerHandlesHttpRequest() throws Exception {
        assertTrue(port > 0);

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/greet?name=Lan"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertAll(
                () -> assertEquals(200, response.statusCode()),
                () -> assertEquals("Hello, Lan!", response.body()));
    }
}
~~~

Test này dùng **`java.net.http.HttpClient` có sẵn trong Java 17** để không phụ thuộc một test client riêng của Spring Boot. `@LocalServerPort` nhận cổng server **thật** đã bind. Đây là test qua network loopback, kiểm servlet container, HTTP serialization của chuỗi và MVC routing.

Phạm vi vẫn chưa phải end-to-end production: không có reverse proxy, TLS production, database production, queue hoặc client mobile thật. Tuy nhiên nó cho bằng chứng mạnh hơn mock HTTP về cấu hình server thực tế.

### 7.10 Gradle và chạy ví dụ

Trong một dự án **Spring Boot 3.5.x với Gradle plugin và dependency management đã được cấu hình**, thêm các dependency phù hợp vào `build.gradle` (đoạn này **không phải file build hoàn chỉnh**):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dùng Java toolchain 17 hoặc mới hơn. Từ root Gradle của module:

~~~bash
./gradlew test
~~~

Hoặc chỉ chọn ba lớp:

~~~bash
./gradlew test --tests example.bootstart.ContextLoadTest \
    --tests example.bootstart.MockHttpTest \
    --tests example.bootstart.RealHttpTest
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

**Kết quả dự kiến trong một môi trường được cấu hình đúng:** có **4 bài test** (hai ở `ContextLoadTest`, một ở `MockHttpTest`, một ở `RealHttpTest`), tất cả PASS. Không có stdout cố định do chính test in ra; Gradle có thể kết thúc bằng `BUILD SUCCESSFUL` và tạo báo cáo dưới `build/reports/tests/test/index.html`. Spring Boot có thể in log startup nên thời lượng/port/log text **không cố định**.

Cấu hình có thể nạp **nhiều context** do ba bài test chọn các `webEnvironment` khác nhau. Không nên suy ra “bốn test = bốn lần khởi động” vì cache và các context keys sẽ quyết định số context thực sự được tạo.

## 8. Đọc đúng ý nghĩa của từng test

| Loại kiểm thử | Ngữ cảnh chạy | Bằng chứng | Không tự chứng minh |
| --- | --- | --- | --- |
| Unit test thuần Java | Không Spring context | Thuật toán/nhánh của một lớp | Bean wiring, profile, auto-config |
| `@SpringBootTest(NONE)` | Boot context non-web | Component scan, DI, config binding, service startup | HTTP routing hay server |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Boot MVC context + mock request | Mapping, controller, validation, filters trong cấu hình test | TCP binding, TLS, network stack |
| `@SpringBootTest(RANDOM_PORT)` | Boot context + server thật | HTTP request/response qua loopback, servlet server | Môi trường production đầy đủ |
| `@WebMvcTest` | Web slice | Controller/MVC và collaborators được cung cấp | Mọi service/repository thực trong app |
| `@DataJpaTest` | Persistence slice | Entity mapping/repository và DB được cấu hình cho slice | Full HTTP/service workflow |

**Không dùng annotation càng lớn càng tốt.** Chọn mức nhỏ nhất nhưng vẫn chứa đủ thành phần mà lỗi có thể nằm ở đó. `@SpringBootTest` đặc biệt có giá trị khi cần kiểm *cấu hình boot của toàn ứng dụng hoặc tương tác giữa nhiều tầng*, không phải khi chỉ test hàm `calculateTax(...)`.

## 9. @SpringBootTest tải những auto-configuration nào?

`@EnableAutoConfiguration` không có nghĩa “tất cả starter đều bật tất cả tính năng”. Boot dùng **conditional configuration**:

- Có class trên classpath mới chọn những cấu hình phụ thuộc class đó (`@ConditionalOnClass`).
- Property phải phù hợp mới bật tính năng (`@ConditionalOnProperty`).
- Nếu ứng dụng đã tự định nghĩa bean nhất định, Boot có thể **lùi lại** (`@ConditionalOnMissingBean`).
- Profile, resource, bean hiện có và các điều kiện framework khác cũng ảnh hưởng lựa chọn.

Với `spring-boot-starter-web` và MVC classpath, Boot thường nạp các auto-configuration liên quan servlet MVC, JSON, message converters và server khi `webEnvironment` cần. Nếu test dùng `NONE`, nó vẫn có thể tạo các bean ứng dụng và cấu hình không-web, nhưng sẽ không khởi động server.

### Khi muốn điều tra vì sao bean không xuất hiện

Trong test context phù hợp:

~~~java
@Autowired
ApplicationContext context;

// Trong một phương thức @Test:
assertTrue(context.containsBean("greetingService"));
~~~

Đây chỉ là **đoạn mã minh họa trong class test**, cần import `ApplicationContext`, `@Autowired` và assertion JUnit. Tên mặc định `greetingService` đến từ `@Service` trên lớp `GreetingService` của ví dụ; nếu đổi tên bean, cần điều chỉnh assertion.

Khi khởi động lỗi do auto-configuration, có thể bật log điều kiện cho test:

~~~java
@SpringBootTest(properties = "debug=true")
class AutoConfigurationDebugTest {
    // Chỉ dùng khi cần chẩn đoán, tránh log quá lớn thường xuyên.
}
~~~

Trong một số trường hợp, **Condition Evaluation Report** giúp phân biệt auto-configuration nào matched/unmatched. Đừng nhầm lý do “không có dependency”, “profile không active”, “conditional property false” với việc `@SpringBootTest` không chạy auto-configuration.

**Với tài nguyên ngoài như database:** context load có thể kích hoạt datasource, migration hoặc kết nối nếu dependency/config yêu cầu. `@SpringBootTest` tự thân **không khởi động PostgreSQL Docker container**, cũng **không tự chọn H2** chỉ vì chạy unit test. Cần cấu hình rõ datasource test, Testcontainers/`@ServiceConnection` hoặc mock adapter đúng mục tiêu. Tránh để test vô tình kết nối DB production.

## 10. Test properties, profiles và dynamic properties được đưa vào thời điểm nào?

### 10.1 @ActiveProfiles và application-test.properties

~~~java
@ActiveProfiles("test")
@SpringBootTest
class CheckoutIntegrationTest {
}
~~~

Cặp annotation này giúp TestContext chọn profile `test` và Boot nạp config data/profile phù hợp (như `application-test.properties`), nhưng **`@ActiveProfiles` không bảo đảm mọi property trong file profile thắng mọi nguồn khác**. Test inline properties, dynamic property sources, system properties và environment variables có thể ghi đè theo thứ tự ưu tiên tương ứng.

Trong test, kiểm profile qua:

~~~java
@Autowired Environment environment;

// Trong một phương thức @Test:
assertTrue(Arrays.asList(
        environment.getActiveProfiles()).contains("test"));
~~~

Đây là mã minh họa; cần import `Arrays`, `Environment`, `@Autowired`, assertion và JUnit. **Không chỉ kiểm string `spring.profiles.active`** rồi kết luận TestContext đã active hay chưa.

### 10.2 @SpringBootTest(properties = ...)

Dùng khi cần một vài override cố định cho class test:

~~~java
@SpringBootTest(properties = {
    "demo.greeting.prefix=Hello",
    "spring.main.banner-mode=off"
})
class GreetingPropertiesTest {
}
~~~

Các key này được đưa vào test context; chúng có thể thắng cấu hình file thông thường. Nếu một test có `@TestPropertySource` hoặc `@DynamicPropertySource` cung cấp **cùng key**, đừng đoán theo thứ tự annotation trong source code: dùng tài liệu precedence theo đúng phiên bản và xác minh giá trị cuối qua `Environment`/bean.

### 10.3 @DynamicPropertySource và Testcontainers

Khi endpoint là dữ liệu runtime (port container/HTTP stub), không thể hardcode toàn bộ trong file:

~~~java
@DynamicPropertySource
static void externalConfig(DynamicPropertyRegistry registry) {
    registry.add("demo.remote.base-url",
            () -> "http://127.0.0.1:19090");
}
~~~

Đây là **đoạn phương thức minh họa**, không khai báo một server tại port 19090 và không phải file test độc lập. `@DynamicPropertySource` khai báo method `static` nhận `DynamicPropertyRegistry` để đăng ký supplier trả property. Với Testcontainers, supplier có thể tham chiếu method lấy JDBC URL hoặc mapped port từ container đã quản lý lifecycle.

**Quan trọng:** `@SpringBootTest` không khiến container tự khởi chạy chỉ vì có `@DynamicPropertySource`; bạn còn phải cấu hình và quản lý container hoặc cơ chế service connection tương ứng.

Khi Boot cung cấp `ConnectionDetails` từ `@ServiceConnection`, bean client cuối có thể sử dụng nguồn kết nối đó. Đọc mỗi `spring.datasource.url` trong `Environment` **không đủ** chứng minh database mà datasource thật đang kết nối. Cần kiểm bean và connection metadata nếu đó là mục tiêu bài test.

## 11. Transaction: vì sao RANDOM_PORT không rollback dữ liệu giống MOCK?

Spring TestContext có thể quản lý **test transaction** khi một test method/class `@Transactional` được cấu hình đúng với transaction manager. Theo mặc định, test-managed transaction thường được rollback sau test.

Nhưng với `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc `DEFINED_PORT`:

~~~text
Test thread                         Server HTTP thread
  |
  | @Transactional test             Spring MVC handler
  |    mở test transaction T1            |
  |                                      v
  +---- HTTP request ----------------> Service @Transactional
  |                                      |
  |                                      +-- transaction T2
  |                                      +-- commit (nếu thành công)
  |
  +---- HTTP response
  |
  +-- rollback T1
      (KHÔNG rollback dữ liệu T2 đã commit)
~~~

Test thread và server xử lý HTTP ở các thread và transaction khác nhau; rollback của T1 **không tự đảo ngược** giao dịch phía server. Trong test thực tế, transaction propagation, database và error handling có thể khác, nhưng **không được giả định HTTP call đã nằm trong test-managed transaction của thread gọi**.

Với `MockMvc`, request có thể chạy đồng bộ cùng thread test trong các trường hợp thông thường, giúp một số transaction context tiếp tục áp dụng. Nhưng còn phụ thuộc async dispatch, propagation và framework wiring; cần kiểm hành vi cụ thể thay vì tuyên bố “mọi MockMvc test đều rollback mọi side effect”.

**Giải pháp khi HTTP thật ghi dữ liệu:**

1. Dùng database riêng cho test, không dùng dữ liệu production.
2. Dọn state có chủ đích giữa các test (script SQL/fixture cleanup, schema cô lập, transactional API hợp lý), hoặc khởi tạo database container theo chiến lược suite.
3. Kiểm những điều kiện quan sát được sau request; không suy luận “test pass/rollback rồi nên DB sạch”.
4. Với Kafka/email/HTTP side effects, có fake/mock server hoặc dữ liệu cô lập và cleanup riêng.

Đây là một trong những khác biệt quan trọng nhất giữa **“load app thật”** và **“mọi thao tác đều chạy trong transaction của test”**.

## 12. Context caching: @SpringBootTest có khởi động lại trước mỗi @Test không?

**Thường là không.** Spring TestContext có **ApplicationContext cache** trong cùng tiến trình test. Với các test classes có cấu hình context tương đương, framework có thể dùng lại context thay vì khởi động lại.

Những yếu tố góp phần tạo cache key gồm:

- Configuration classes/locations và context loader.
- Active profiles từ `@ActiveProfiles`.
- Properties inline và test property source locations.
- Context customizers: ví dụ dynamic properties, bean overrides, các tùy chỉnh test.
- Parent context, initializers, một số thiết lập web context.
- Tùy chọn Boot liên quan tới loại context, chẳng hạn `webEnvironment`.

Vì thế hai class đều có `@SpringBootTest` **không bảo đảm** dùng cùng một context. Nếu một class dùng `NONE` và class khác dùng `RANDOM_PORT`, chúng phải khởi tạo những kiểu môi trường khác nhau. Nếu hai class có cùng cấu hình, context có thể được tái sử dụng.

### 12.1 Cache giải thích hiện tượng “test đơn chạy được, cả suite thất bại”

Một singleton bean bị mutate, in-memory repository, static state, queue, mutable cache hoặc container dùng chung có thể để lại dữ liệu từ test trước. Context cache **không reset toàn bộ ứng dụng trước mỗi method**.

Giải pháp:

- Tạo test fixture rõ ràng và cleanup có mục đích.
- Không để test phụ thuộc thứ tự chạy hoặc state của class trước.
- Với database, cách ly dữ liệu và quản lý transaction/cleanup thích hợp.
- Chỉ dùng `@DirtiesContext` khi thực sự đã làm bẩn context và cần tạo lại; việc này khiến suite chậm.
- Tránh khác biệt không cần thiết trong inline test properties/bean overrides giữa hàng chục classes vì mỗi cấu hình riêng có thể làm cache miss.

### 12.2 Làm thế nào đo số lần load context?

Bật log của cache TestContext trong môi trường test:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Trong Gradle/IDE, tùy cấu hình logging, bạn có thể quan sát hit/miss/size của context cache. Kết quả có thể bị ảnh hưởng khi tests chạy qua **nhiều JVM/fork**: static cache không tự chia sẻ xuyên process. Không assert chính xác số context load trong unit test nghiệp vụ.

**Tối ưu lớn nhất:** chuyển logic thuần sang unit test, thay full-context test bằng slice khi đủ phạm vi, gom các integration tests có cùng cấu hình test context, tránh `@DirtiesContext` quá mức và hạn chế external dependency không cần thiết.

## 13. @SpringBootTest và các cách test khác: chọn đúng phạm vi

| Nhu cầu | Công cụ thường phù hợp | Vì sao |
| --- | --- | --- |
| Tính giá trị, validate input, quy tắc thuần Java | JUnit Jupiter + Mockito/fake | Không cần tạo Spring context; nhanh và cô lập |
| Kiểm vài bean Java config mà không cần Boot auto-config | `@ContextConfiguration` hoặc `ApplicationContextRunner` | Nạp phạm vi nhỏ, chọn bean cụ thể |
| Kiểm controller mapping/validation/filter, mock service | `@WebMvcTest` + override/mock collaborator cần thiết | Web slice, ít bean hơn full Boot |
| Kiểm JPA mapping/repository/queries | `@DataJpaTest` và DB phù hợp | Persistence slice; cần hiểu test DB/rollback |
| Kiểm JSON serialization | `@JsonTest` khi phù hợp | Chọn phần JSON thay vì full app |
| Kiểm wiring, profile, auto-config, service xuyên nhiều tầng | `@SpringBootTest(NONE/MOCK)` | Gần cách cấu hình ứng dụng thật, không nhất thiết mở server |
| Kiểm HTTP/TCP/request serialization qua embedded server | `@SpringBootTest(RANDOM_PORT)` | Server và client thực |
| Kiểm hợp đồng với PostgreSQL/Kafka/Redis | Spring integration test + Testcontainers/service thật | Mock/fake không chứng minh protocol hay transaction thực |

**Một hiểu nhầm:** viết `@SpringBootTest` không đồng nghĩa “integration test sẽ luôn test cả database”. Nếu SUT inject repository đã bị mock, bạn vẫn chưa kiểm SQL. Ngược lại, test thuần service có thể bao phủ nghiệp vụ rất tốt mà không cần Spring Boot. Phạm vi test do **các collaborator thật hay giả** và môi trường được tải quyết định.

## 14. Các lỗi khi @SpringBootTest không thể tải ứng dụng

### 14.1 Không tìm được @SpringBootConfiguration

**Dấu hiệu:** thông báo “Unable to find a `@SpringBootConfiguration`”.

**Nguyên nhân thường gặp:** package test không nằm dưới package app hoặc source configuration không rõ.

**Khắc phục:** đặt test trong package phù hợp, hoặc chỉ định `@SpringBootTest(classes = DemoApplication.class)`. Không cấu hình quét mọi package vô hạn chỉ để chữa lỗi vị trí.

### 14.2 “Failed to load ApplicationContext” do một bean bị lỗi

Đây là thông báo tổng quát. Cần đọc **root cause** cuối chuỗi exception: `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException`, `BeanCreationException`, lỗi binding properties hoặc kết nối datasource. Những nguyên nhân này khác nhau và cần sửa riêng.

Ví dụ production bean yêu cầu `DataSource` nhưng test không có JDBC URL/driver; Boot có thể fail trong auto-config trước khi test method chạy. Không nên vô hiệu hóa toàn bộ auto-config chỉ để ép smoke test PASS nếu mục tiêu là kiểm cấu hình production.

### 14.3 Test có @SpringBootTest nhưng @Autowired null

Kiểm test chạy bằng **JUnit Jupiter**, import `org.junit.jupiter.api.Test`, JUnit Platform và extension integration. Nếu tự tạo class test bằng `new` hoặc gọi method ngoài test runner, `@Autowired` không có cơ hội được Spring TestContext inject.

Trong JUnit Jupiter thông thường, `@SpringBootTest` đã kéo `SpringExtension` vào; không cần `@ExtendWith` lặp lại.

### 14.4 Controller test trả 404 hoặc thiếu MockMvc

Với `MOCK`, cần `@AutoConfigureMockMvc` trong full-context test MVC. Nếu vẫn 404, kiểm controller có nằm trong component scan không, mapping là gì, profile/security/filter có chặn request không và app đang dùng MVC hay WebFlux.

Một `@SpringBootTest(webEnvironment = NONE)` không có HTTP server, nên không thể gọi port 8080 rồi kỳ vọng nó trả response từ test context.

### 14.5 RANDOM_PORT không phải 8080

Đừng hardcode localhost:8080. Dùng `@LocalServerPort` (hoặc client auto-configured phù hợp) để biết port thực tế. `DEFINED_PORT` có thể đụng port đang được service khác sử dụng trong CI.

### 14.6 Bean có @Profile("prod") không xuất hiện trong test

Nếu test bật `@ActiveProfiles("test")`, bean chỉ dành cho profile `prod` không được tạo (trừ khi conditions khác thay đổi logic). Đây là hành vi đúng của Spring. Kiểm active profiles bằng `Environment.getActiveProfiles()`, không phải chỉ xem tên file.

### 14.7 Có custom code trong main() nhưng test không chạy

Vì `useMainMethod=NEVER` là mặc định. Đưa cấu hình hợp lệ vào beans/config data/hook hoặc chọn `WHEN_AVAILABLE`/`ALWAYS` khi cần test main. Không sửa code chỉ để ép test gọi main trong mọi trường hợp.

### 14.8 Test làm gọi hạ tầng production ngoài ý muốn

Root context có thể tạo email client, scheduler, migration, data source và listener. Dùng test profile, fake gateway, Testcontainers, service stub hoặc cấu hình disable rõ ràng. **Không đưa credentials production vào test properties**.

### 14.9 Context load rất chậm hoặc suite chiếm nhiều RAM

Thường do context quá rộng, database/container startup, nhiều cache keys hoặc `@DirtiesContext`. Đo thời gian startup, profile bean init, cache hits và nguyên nhân thay đổi config giữa lớp; chọn unit/slice tests khi đủ.

### 14.10 @Mock không thay bean production trong ApplicationContext

Một `@Mock` của Mockito cấp cho field test không tự thay bean mà Spring đang inject vào service. Đối với Spring Boot 3.4+/Spring Framework 6.2, có `@MockitoBean`/`@MockitoSpyBean` trong Spring TestContext; dự án Boot 3.3 trở về trước thường dùng `@MockBean`/`@SpyBean` của Boot. Chọn annotation theo phiên bản và xác định rõ component nào cần mock.

### 14.11 Spring Boot 4.x và import test khác Boot 3.x

Kiến trúc TestContext/SpringApplication và bốn web environment modes vẫn có ý nghĩa, nhưng **module và package của một số tiện ích test** đã thay đổi trong Boot 4.x (ví dụ MVC/test client). Những source files ở mục 7 được viết có chủ đích cho **Boot 3.5.x**. Khi nâng lên Boot 4.x, dùng migration guide và import đúng artifact; không khẳng định ví dụ 3.5 có thể copy nguyên import sang mọi 4.x.

### 14.12 @Transactional ở test HTTP thật không dọn database

Client và server khác thread nên rollback test-managed transaction ở client thread không bao phủ giao dịch server. Dùng DB test cô lập và dọn state theo hợp đồng, không dựa vào rollback ảo.

## 15. Quy trình xác minh một bài @SpringBootTest có giá trị

Khi viết mới một bài full-context test, đi theo thứ tự:

1. **Viết mục tiêu test:** “Ứng dụng khởi động và bind đúng cấu hình”, “controller xử lý request”, hay “repository ghi vào PostgreSQL thật”?
2. **Chọn root configuration:** bảo đảm test nằm đúng package hierarchy hoặc chỉ định `classes`, không vô tình thay cấu hình bằng nested `@Configuration`.
3. **Chọn webEnvironment:** `NONE` cho non-web wiring, `MOCK` cho MockMvc, `RANDOM_PORT` cho HTTP thật, `DEFINED_PORT` chỉ khi phải dùng cổng cố định.
4. **Xác định profile và properties:** `@ActiveProfiles`, config data, `@SpringBootTest(properties)`, `@TestPropertySource`, `@DynamicPropertySource` theo yêu cầu.
5. **Xác định những bean nào thật:** logic, controller, repository, database, HTTP client, broker. Dùng fake/mock đúng tại ranh giới để test không chạm production.
6. **Chạy context lần đầu:** đọc nguyên nhân gốc nếu startup fail, không dừng ở thông báo chung “Failed to load ApplicationContext”.
7. **Assert cấu hình đã bind và hành vi quan sát được:** `ApplicationContext` active, bean hiện diện, `ConfigurationProperties` đúng, HTTP status/body hoặc trạng thái database.
8. **Kiểm side effects và transaction:** đặc biệt với server thật, scheduler, listener, migrations và các tác vụ bất đồng bộ.
9. **Quan sát thời gian/context cache:** tránh khác nhau không cần thiết giữa các test classes, không reset context nếu chỉ cần cleanup fixture.
10. **Tách bài test khi phạm vi đã rõ:** quy tắc thuần → unit; MVC → slice hoặc MockMvc; network/DB thật → integration có tài nguyên kiểm thử.

### Checklist trước khi commit

- [ ] Biết `@SpringBootTest` tạo `ApplicationContext` qua `SpringApplication` chứ không chỉ chạy `main()`.
- [ ] Dùng JUnit Jupiter đúng import và Spring TestContext, không trộn JUnit 4 runner tùy tiện.
- [ ] Biết root `@SpringBootConfiguration` được tìm hoặc chỉ định ở đâu.
- [ ] Hiểu `@SpringBootApplication` gồm configuration, auto-configuration và component scan; auto-config có điều kiện.
- [ ] Chọn đúng `MOCK`, `RANDOM_PORT`, `DEFINED_PORT` hoặc `NONE`.
- [ ] Nếu dùng MockMvc trong full-context Spring MVC test, có `@AutoConfigureMockMvc`.
- [ ] Nếu dùng HTTP thật, lấy port thực thay vì hardcode; không dựa vào rollback của test thread.
- [ ] Các test properties, active profiles và dynamic properties không vô tình trỏ tới hạ tầng production.
- [ ] Có assertion về bean/config/hành vi, không chỉ một test method rỗng.
- [ ] Không dựa vào `@SpringBootTest` để tự khởi tạo DB/Kafka container hoặc tự thay bean bằng Mockito `@Mock`.
- [ ] Đã tính đến startup hooks, side effects, context caching và cleanup giữa test methods.
- [ ] Kiểm version Spring Boot khi dùng API `useMainMethod` hoặc các module test của Boot 4.x.

**Kết luận:** `@SpringBootTest` tạo **ngữ cảnh ứng dụng theo cơ chế Spring Boot** nhờ Spring TestContext phối hợp với `SpringBootContextLoader` và `SpringApplication`. Nó tìm cấu hình gốc, nạp config/profile, tạo bean và auto-config theo điều kiện, rồi cho test làm việc với context đã khởi tạo. **Mặc định không gọi `main()` và không mở HTTP server thật.** Việc có server, kiểu web context và phạm vi bằng chứng phụ thuộc `webEnvironment` cùng các dependency thật/giả được đưa vào test.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): SpringApplication trong tests, tìm cấu hình chính, bốn `webEnvironment`, transaction và context cache.
- [Spring Boot 3.5 — Use the Main Method](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `useMainMethod` và sự khác biệt với việc gọi `main`.
- [Spring Boot API — @SpringBootTest](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html): `classes`, `properties`, `args`, `webEnvironment` và `useMainMethod`.
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): cơ chế test context, injection và lifecycle.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache key, tái sử dụng context và `@DirtiesContext`.
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): config data, profile-specific sources và properties.
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource` cho tài nguyên runtime.
- [Spring Boot 4.0 Migration Guide — Testing](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): thay đổi các module và API test khi nâng từ Boot 3.x lên 4.x.

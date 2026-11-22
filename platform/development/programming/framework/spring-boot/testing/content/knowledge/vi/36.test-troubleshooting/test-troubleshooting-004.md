# Không tìm thấy @SpringBootConfiguration hoặc chọn sai cấu hình

## 1. Bài toán: Spring Boot test không tìm ra điểm khởi tạo đúng

Trong module **Spring Boot - testing**, nhóm **Chẩn đoán lỗi kiểm thử**, hai hiện tượng thường bị lẫn làm một:

1. JUnit test dừng **trước khi ApplicationContext được tạo**, với lỗi đại ý: **"Unable to find a @SpringBootConfiguration by searching packages upwards from the test"**.
2. Test vẫn khởi động một `ApplicationContext` nhưng **chọn sai cấu hình**, dẫn đến thiếu bean, chạy nhầm component scan, thiếu repository, không có controller, nạp profile sai, gọi nhầm database hoặc kiểm một slice mà lại tải cả ứng dụng.

Đây là vấn đề của **bootstrap source và classpath** trước khi là vấn đề của assertions. Cách sửa tốt nhất không phải thêm `@SpringBootApplication` vào mọi test, không phải chuyển tất cả sang `@DirtiesContext`, và không phải bật `@ComponentScan("com")` bao trùm toàn project. Cần hiểu chính xác Spring Boot test bootstrapper đang chọn **configuration class nào**.

### Một stack trace tiêu biểu

~~~text
java.lang.IllegalStateException:
  Unable to find a @SpringBootConfiguration by searching
  packages upwards from the test.
  You can use @ContextConfiguration,
  @SpringBootTest(classes=...) or other Spring Test
  supported mechanisms to explicitly declare the
  configuration classes to load.
  Classes annotated with @TestConfiguration
  are not considered.
~~~

Đây là mẫu **tóm lược thông điệp**, line numbers/package của stack trace có thể khác theo Spring Boot release. Nó nói rằng Spring Boot **không tự tìm ra primary application configuration** trong vùng package được tìm, không có nghĩa code ứng dụng thiếu mọi `@Configuration` hoặc Gradle không có test dependency.

**Kết quả cần đạt:** kiểm package layout, main application class và compile/test runtime classpath; chọn chính xác giữa `@SpringBootTest(classes=...)`, để auto-detection, `@SpringJUnitConfig`/`@ContextConfiguration`, `@TestConfiguration` và các slice `@WebMvcTest`/`@DataJpaTest`; viết JUnit tests xác minh **bean identity, profile, property, classpath, scan boundaries** thay vì chỉ assert context khởi động.

Bài dùng **Java 17 + Spring Boot 3.5.16 + Gradle 8.x + JUnit Jupiter + MockMvc + Spring Data JPA/H2**. Có một project hoàn chỉnh gồm 15 JUnit test methods trong tám lớp, phân biệt Spring Boot test full context, web/JPA slice, test cấu hình lồng và import, test ở package ngoài và Spring TestContext thuần.

## 2. @SpringBootConfiguration là gì?

Ba annotation dễ nhầm:

| Annotation | Bản chất | Vai trò trong test bootstrap |
| --- | --- | --- |
| `@Configuration` | Khai báo nguồn Spring bean definitions | Có thể dùng với `@ContextConfiguration`/`@SpringJUnitConfig`; **không tự đồng nghĩa Boot primary config** |
| `@SpringBootConfiguration` | Một specialization của `@Configuration`, đánh dấu cấu hình nguồn của Boot app | **Được Spring Boot test bootstrapper tìm** khi autodetect |
| `@SpringBootApplication` | Gộp `@SpringBootConfiguration`, `@EnableAutoConfiguration`, `@ComponentScan` | **Là primary configuration thông dụng nhất** cho full Boot app |

Phản ví dụ:

~~~java
@Configuration
public class AppConfig {
    @Bean
    SampleService sampleService() {
        return new SampleService();
    }
}
~~~

Đây là **snippet**, không phải source runnable của ví dụ chính; `SampleService` là kiểu minh họa. Dù class này có thể tạo một Spring `ApplicationContext` hợp lệ qua `@SpringJUnitConfig(AppConfig.class)`, nó **không phải** điểm khởi tạo Boot mà `@SpringBootTest` mặc định tìm bằng annotation `@SpringBootConfiguration`.

Cách khai báo ứng dụng điển hình:

~~~java
@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Đây là **snippet**; ứng dụng runnable đầy đủ trong mục sau dùng tên `BootConfigApplication`. `@SpringBootApplication` được meta-annotated với `@SpringBootConfiguration`, vì vậy Spring Boot test tự tìm được nó khi package layout phù hợp.

### Chỉ dùng @SpringBootConfiguration có đủ không?

Một class chỉ gắn `@SpringBootConfiguration` **không tự có** component scanning và auto-configuration như `@SpringBootApplication`. Nó có thể là source test cố ý tối giản, nhưng nếu bạn mong có JPA repository, MVC controller và `@Service` được scan, cần các import/cấu hình tương ứng. Vì thế một test **đã tìm đúng Boot configuration class** vẫn có thể thiếu beans nếu class đó chỉ cung cấp một phần.

## 3. Spring Boot tìm primary configuration như thế nào?

Theo Spring Boot 3.5 reference, nếu một annotation test của Boot **không được khai báo source configuration tường minh**, framework tìm **từ package chứa test đi lên các package cha** cho tới khi tìm một class được đánh dấu `@SpringBootApplication` hoặc `@SpringBootConfiguration`.

Ví dụ layout tốt:

~~~text
src/main/java/
  com/example/store/
    StoreApplication.java          @SpringBootApplication
    domain/OrderService.java
    web/OrderController.java

src/test/java/
  com/example/store/
    StoreApplicationTest.java      @SpringBootTest
    web/OrderControllerTest.java   @SpringBootTest hoặc @WebMvcTest
    domain/OrderServiceTest.java
~~~

Với test ở `com.example.store.web`, chuỗi package ancestor là:

~~~text
com.example.store.web
com.example.store
com.example
com
~~~

Khi `StoreApplication` ở `com.example.store` và có mặt trong **test runtime classpath**, Spring Boot tìm được primary config. **Nó không tự tìm mọi package sibling, không dò source files trên ổ đĩa và không “nhớ” main class từ lệnh Gradle bootRun.**

Layout dễ lỗi:

~~~text
src/main/java/com/example/store/StoreApplication.java
src/test/java/com/example/billing/InvoiceTest.java
~~~

Test package `com.example.billing` đi lên `com.example`; `StoreApplication` lại nằm ở **nhánh con sibling** `com.example.store`, không thuộc package được scan ở mỗi bước ancestor; lookup có thể thất bại.

**Điểm dễ nhầm:** tên thư mục `src/test/java` không quan trọng bằng **Java `package` declaration** trong file và classpath. Di chuyển file test mà không đổi dòng `package com.example...` có thể không thay đổi lookup theo cách bạn nghĩ.

## 4. Sơ đồ quyết định: lỗi thiếu config hay chọn sai config?

~~~text
JUnit test bắt đầu
       |
       v
Có sử dụng @SpringBootTest / Boot test slice?
       |
       +-- KHÔNG --> Dùng @SpringJUnitConfig / @ContextConfiguration?
       |               -> Load Spring context do test chỉ rõ;
       |                  không bắt buộc tìm @SpringBootApplication.
       |
       +-- CÓ --> Đã chỉ rõ primary classes?
                       |
                       +-- CÓ --> Kiểm classes có đúng module/app,
                       |           auto-configuration và scan boundaries.
                       |
                       +-- KHÔNG --> Có nested static @Configuration?
                                      |
                                      +-- CÓ --> Có thể dùng nested config
                                      |           thay main Boot config.
                                      |
                                      +-- KHÔNG --> Tìm ngược package
                                                      @SpringBootConfiguration
                                                      |
                                                      +-- Không có --> lỗi
                                                      |    "Unable to find ..."
                                                      +-- Có --> load config
                                                           |
                                                           +-- Đúng nhưng bean fail?
                                                           |   xem nguyên nhân tiếp
                                                           +-- Sai app config?
                                                               chọn source
                                                               cụ thể / chỉnh package
~~~

Đây là flow **chẩn đoán**, không phải thuật toán nội bộ chính xác tới từng byte của Spring Boot. Điểm cốt lõi: *primary configuration detection* xảy ra trước *bean creation*. Nếu đã thấy lỗi JDBC connection, missing entity hoặc port conflict, framework nhiều khả năng đã qua bước phát hiện primary config.

## 5. Các nguyên nhân phổ biến nhất

| Nguyên nhân | Dấu hiệu | Hướng xử lý ưu tiên |
| --- | --- | --- |
| Test nằm ở package sibling ngoài application root | Không tìm thấy @SpringBootConfiguration | Chuyển test vào package con app hoặc `@SpringBootTest(classes=MainApplication.class)` |
| Application class ở source set/module không có trên test runtime classpath | Không thể load/found main class | Sửa Gradle project dependencies/`testRuntimeClasspath` |
| Main class chỉ gắn `@Configuration` | Boot test không tìm Boot marker | Dùng `@SpringBootApplication` nếu là app, hoặc Spring test thuần |
| Main có `@SpringBootConfiguration` nhưng không auto-config/component-scan | Context tạo nhưng thiếu bean | Dùng Boot app source đúng, bổ sung cấu hình có chủ đích |
| Hai/multiple Boot configuration candidates trong vùng tìm | Có thể báo nhiều sources/ambiguity | Chỉ rõ classes hoặc tổ chức lại app/test config |
| Test có nested `@Configuration` | Test có bean nhưng thiếu service thực | Dùng nested `@TestConfiguration` để bổ sung thay vì thay primary |
| Test có nested/top-level `@TestConfiguration` và không có Boot app | Vẫn báo không tìm thấy primary | `@TestConfiguration` **không thay thế Boot primary** |
| Test sử dụng `@ContextConfiguration(classes=SmallConfig.class)` nhầm | Context thiếu Boot auto-config | `@SpringBootTest(classes=App.class)` nếu cần Boot features |
| `@WebMvcTest`/`@DataJpaTest` với root config sai | Slice thiếu đúng bean, nạp quá rộng | Chỉnh primary source, scan filters, `@Import` có chọn lọc |
| Explicit `@ComponentScan` trên application class | Slice filters bị vô hiệu hóa | Tránh scan rộng trên main class, tách cấu hình |
| Test có `@ActiveProfiles` sai | Bean được conditional khác | Kiểm property/profile sau khi đã tìm config |
| Test task source set `integrationTest` thiếu main output | ClassNotFound/lookup fail | Sửa `testClassesDirs` và `classpath` |
| Chọn config từ app khác trong mono-repo | Context chạy nhưng bean không như mong đợi | Pin đúng source và phân module/packages |
| Context cache reuse không phù hợp | State/bean override khác kỳ vọng | So test context key, qualifiers, profiles; không lạm dụng DirtyContext |

Trước khi sửa code, ghi rõ **annotation của test, package declaration của test, FQCN của main app, classpath của Test task, và dòng lỗi đầu tiên**. Chỉ một trong các hạng mục này sai đã đủ giải thích phần lớn ca lỗi.

## 6. Phân biệt ba kiểu test để chọn đúng cơ chế

**Test thuần JUnit/Mockito:**

~~~java
class TaxCalculatorTest {
    @Test
    void computesTax() {
        TaxCalculator calculator = new TaxCalculator();
        assertThat(calculator.taxFor(100)).isEqualTo(10);
    }
}
~~~

Đây là **snippet minh họa** với `TaxCalculator` chưa định nghĩa trong project; nó không cần Spring ApplicationContext, không cần `@SpringBootTest`, vì thế không có lý do để gặp lỗi tìm `@SpringBootConfiguration`.

**Spring TestContext thuần:**

~~~java
@SpringJUnitConfig(MiniConfig.class)
class MiniContextTest {
    @Autowired ExampleService service;
}
~~~

Đây là snippet; `MiniConfig` và `ExampleService` là types minh họa. `@SpringJUnitConfig` tương đương kết hợp `@ExtendWith(SpringExtension.class)` + `@ContextConfiguration`; nó dùng Spring TestContext, **không đòi Spring Boot tìm main app**.

**Full Boot integration:**

~~~java
@SpringBootTest(classes = MyApplication.class)
class FullAppTest {
    @Autowired ExampleService service;
}
~~~

Đây là snippet cần class thật. `@SpringBootTest` tạo context bằng `SpringApplication` và Boot features; khi rõ source classes, nó không cần package autodetection. Với test nằm dưới application root, thường có thể viết gọn `@SpringBootTest`.

**Slice test:** `@WebMvcTest` chỉ cấu hình phần web; `@DataJpaTest` cấu hình JPA test slice. Cả hai không có nghĩa “tự động bỏ qua nhu cầu tìm primary Boot configuration”. Chỉ định controller/entity trong slice **không tương đương** khai báo nguồn bootstrap đầy đủ.

## 7. Dự án runnable: cấu trúc file và phạm vi

Dùng Java 17/Spring Boot 3.5.16/Gradle Groovy DSL. Cây file:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/bootconfig/
  BootConfigApplication.java
src/main/java/com/example/bootconfig/core/
  WelcomeService.java
src/main/java/com/example/bootconfig/web/
  WelcomeController.java
src/main/java/com/example/bootconfig/data/
  NoteEntry.java
  NoteRepository.java
src/main/resources/
  application.properties

src/test/java/com/example/bootconfig/
  BootConfigurationDiscoveryTest.java
  NestedTestConfigurationAddsToApplicationTest.java
  ExtraTestBeans.java
  TopLevelImportedTestConfigurationTest.java
src/test/java/com/example/bootconfig/web/
  WelcomeWebMvcSliceTest.java
src/test/java/com/example/bootconfig/data/
  NoteRepositorySliceTest.java
src/test/java/com/example/outside/
  ExplicitApplicationFromOtherPackageTest.java
  NestedPlainConfigurationReplacesApplicationTest.java
  PlainSpringOnlyTest.java
~~~

*Ghi chú:* Cây runnable dưới đây có **tám** JUnit test classes với **15 test methods**: 2 full Boot, 2 web slice, 2 JPA slice, 2 nested additive, 1 top-level imported, 2 explicit outside, 2 nested replacement và 2 plain Spring (tổng 15). `ExtraTestBeans` là helper `@TestConfiguration`, không phải test class. Các phương án mở rộng như property override diagnostic ở phần 16 chỉ là minh họa và không thuộc tập đếm này.

**Lưu ý khi chạy:** Những ví dụ *gây lỗi thiếu config có chủ đích* chỉ được trình bày thành **snippets phản ví dụ**, **không đặt thành test classes thực thi** trong project đúng để tránh `./gradlew test` fail do lỗi cố ý. Các Java classes đầy đủ bên dưới được thiết kế để PASS về hành vi được mô tả; chúng **chưa được compile/run trong lúc biên soạn**.

## 8. Gradle build và JUnit test launcher

**`settings.gradle`:**

~~~groovy
rootProject.name = 'boot-config-diagnostics-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
}
~~~

Spring Boot 3.5 BOM quản lý dependency versions thích hợp cho Spring Framework 6.2, JUnit, Mockito và H2. `spring-boot-starter-web` cung cấp Spring MVC/controller; `spring-boot-starter-data-jpa` cung cấp Spring Data JPA để có slice `@DataJpaTest` thật. H2 chỉ là demo/test embedded DB, không phải production database.

**Không thêm `@SpringBootTest` cho mọi unit test để “phát hiện” Spring Boot:** việc đó làm test chậm, có thể kéo JPA/web và DB không liên quan, và che lỗi dependency boundaries.

## 9. Application class ở đúng package root

**`src/main/java/com/example/bootconfig/BootConfigApplication.java`:**

~~~java
package com.example.bootconfig;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BootConfigApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootConfigApplication.class, args);
    }
}
~~~

Đây là **primary configuration duy nhất** trong runnable project. Bởi vì package là `com.example.bootconfig`, component scan mặc định chứa:

~~~text
com.example.bootconfig.core
com.example.bootconfig.web
com.example.bootconfig.data
~~~

Và test package `com.example.bootconfig.web` hay `com.example.bootconfig.data` có thể **tự phát hiện** `BootConfigApplication` theo thuật toán tìm ngược package.

**Đặt main class vào một subpackage quá sâu là một lỗi khác:** ví dụ `com.example.bootconfig.app.BootConfigApplication` có thể không scan `com.example.bootconfig.core` và `...web` cùng cấp như mong đợi. Khi đó test **tìm thấy config** vẫn có thể thiếu services. Đặt main app ở package root hợp lý hoặc cấu hình `scanBasePackages`/`@EntityScan`/`@EnableJpaRepositories` có chủ đích khi kiến trúc thật yêu cầu.

## 10. Service thật: kiểm xem application bean có được load không

**`src/main/java/com/example/bootconfig/core/WelcomeService.java`:**

~~~java
package com.example.bootconfig.core;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class WelcomeService {

    private final String prefix;

    public WelcomeService(
            @Value("${app.welcome-prefix:Hello}") String prefix
    ) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String welcome(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank"
            );
        }

        return prefix + ", " + name.strip() + "!";
    }

    public String prefix() {
        return prefix;
    }
}
~~~

Test nhìn thấy `WelcomeService` **không đủ** để khẳng định đúng package/config ở mọi trường hợp; ví dụ mock cũng có thể tạo type này. Vì vậy full Boot test kiểm thêm `BootConfigApplication` trong context và property value.

**`src/main/resources/application.properties`:**

~~~properties
app.welcome-prefix=Hello
spring.datasource.url=jdbc:h2:mem:boot_config_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.main.banner-mode=off
~~~

`@Value("${app.welcome-prefix:Hello}")` dùng placeholder trong **Spring-managed constructor**. Nếu service được tạo bằng `new WelcomeService("Mini")` trong Spring TestContext thuần, chính test quyết định prefix, không cần Boot property loading.

## 11. MVC controller phục vụ test Boot và WebMvc slice

**`src/main/java/com/example/bootconfig/web/WelcomeController.java`:**

~~~java
package com.example.bootconfig.web;

import com.example.bootconfig.core.WelcomeService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/welcome")
public class WelcomeController {

    private final WelcomeService service;

    public WelcomeController(WelcomeService service) {
        this.service = service;
    }

    @GetMapping("/{name}")
    public String greeting(@PathVariable String name) {
        return service.welcome(name);
    }
}
~~~

Trong **full `@SpringBootTest`**, controller và `WelcomeService` thật cùng có mặt. Trong **`@WebMvcTest(WelcomeController.class)`**, controller được đưa vào MVC slice nhưng service thường **không** được component-scan theo cách full context; test cung cấp `@MockitoBean WelcomeService`.

Nếu chuyển controller khỏi package root của application, bean có thể không được scan trong full Boot context; `@WebMvcTest(WelcomeController.class)` chọn controller rõ ràng nhưng không chứng minh full app auto-scan controller đó. Tầng test khác nhau có trách nhiệm khác nhau.

## 12. JPA entity/repository để kiểm DataJpaTest slice

**`src/main/java/com/example/bootconfig/data/NoteEntry.java`:**

~~~java
package com.example.bootconfig.data;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "note_entries")
public class NoteEntry {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected NoteEntry() {
    }

    public NoteEntry(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

**`src/main/java/com/example/bootconfig/data/NoteRepository.java`:**

~~~java
package com.example.bootconfig.data;

import org.springframework.data.jpa.repository.JpaRepository;

public interface NoteRepository
        extends JpaRepository<NoteEntry, Long> {
}
~~~

`@DataJpaTest` mặc định giới hạn scanning vào entity và Spring Data JPA repository, auto-config embedded database nếu phù hợp, và transaction test thường rollback sau mỗi method. Những đặc tính này giúp test JPA nhanh hơn full Boot. Tuy vậy slice vẫn cần một primary Boot application configuration hoặc source configuration tường minh để xác định component scan boundaries.

## 13. JUnit: full Boot test tự tìm đúng main application

**`src/test/java/com/example/bootconfig/BootConfigurationDiscoveryTest.java`:**

~~~java
package com.example.bootconfig;

import com.example.bootconfig.core.WelcomeService;
import com.example.bootconfig.web.WelcomeController;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class BootConfigurationDiscoveryTest {

    @Autowired ApplicationContext context;
    @Autowired WelcomeService welcomeService;
    @Autowired MockMvc mvc;

    @Test
    void discoversApplicationAndFullServiceByPackage() {
        assertThat(context.containsBean("bootConfigApplication"))
                .isTrue();

        assertThat(context.getBean(
                com.example.bootconfig.BootConfigApplication.class
        )).isNotNull();

        assertThat(welcomeService.prefix()).isEqualTo("Hello");
        assertThat(welcomeService.welcome(" Ada "))
                .isEqualTo("Hello, Ada!");
    }

    @Test
    void fullBootContextContainsMvcController() throws Exception {
        assertThat(
                context.getBeansOfType(WelcomeController.class)
        ).hasSize(1);

        mvc.perform(get("/api/welcome/Ada"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Ada!"));
    }
}
~~~

Đây là **hai test methods**. Không khai báo `classes=...` trên `@SpringBootTest`, nhưng test package đúng bằng application package, nên Spring Boot tự tìm `BootConfigApplication`. Test kiểm **identity của primary config**, service bean và endpoint thật.

Vì sao test này có giá trị? Nếu một test khác ở package cùng tên nhưng context bị nested `@Configuration` thay nguồn, test kia có thể load được `ApplicationContext` nhưng không có `BootConfigApplication`/`WelcomeService`. Assertions ở đây ngăn “context khởi động là đủ” làm tiêu chuẩn.

## 14. JUnit: @WebMvcTest chọn slice nhưng vẫn cần Boot source

**`src/test/java/com/example/bootconfig/web/WelcomeWebMvcSliceTest.java`:**

~~~java
package com.example.bootconfig.web;

import com.example.bootconfig.core.WelcomeService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(WelcomeController.class)
class WelcomeWebMvcSliceTest {

    @Autowired MockMvc mvc;
    @Autowired ApplicationContext context;

    @MockitoBean
    WelcomeService welcomeService;

    @Test
    void onlyWebLayerIsBootstrappedWithMockService()
            throws Exception {
        given(welcomeService.welcome("Ada"))
                .willReturn("Slice, Ada!");

        mvc.perform(get("/api/welcome/Ada"))
                .andExpect(status().isOk())
                .andExpect(content().string("Slice, Ada!"));

        verify(welcomeService).welcome("Ada");
    }

    @Test
    void mvcSliceDoesNotLoadDataRepository() {
        assertThat(
                context.getBeansOfType(
                    com.example.bootconfig.data.NoteRepository.class
                )
        ).isEmpty();
    }
}
~~~

Đây là **hai tests** thuộc MVC slice. `@WebMvcTest(WelcomeController.class)` xác định **controller được đưa vào slice**, không có nghĩa thay thế `@SpringBootConfiguration` bằng controller class. Auto-detection vẫn tìm app config theo package `com.example.bootconfig.web` → `com.example.bootconfig`.

`@MockitoBean` dùng Spring Framework 6.2, thay/đăng ký mock bean trong test context. Không nhầm với `@Mock` thuần Mockito: một `@Mock` field trên test class **không tự thay bean** mà `@Autowired` controller nhận từ Spring.

Nếu test đặt trong một package ngoài application hierarchy, chỉ thêm `controllers=WelcomeController.class` không phải cách chữa root configuration missing.

## 15. JUnit: @DataJpaTest cùng cơ chế tìm main config

**`src/test/java/com/example/bootconfig/data/NoteRepositorySliceTest.java`:**

~~~java
package com.example.bootconfig.data;

import com.example.bootconfig.web.WelcomeController;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class NoteRepositorySliceTest {

    @Autowired NoteRepository repository;
    @Autowired ApplicationContext context;

    @Test
    void repositoryPersistsEntityWithinJpaSlice() {
        NoteEntry saved =
                repository.saveAndFlush(new NoteEntry("Alpha"));

        assertThat(saved.getId()).isNotNull();

        NoteEntry loaded =
                repository.findById(saved.getId()).orElseThrow();

        assertThat(loaded.getTitle()).isEqualTo("Alpha");
    }

    @Test
    void jpaSliceDoesNotLoadMvcController() {
        assertThat(
                context.getBeansOfType(WelcomeController.class)
        ).isEmpty();
    }
}
~~~

Đây là **hai tests**. Test class nằm trong package con `com.example.bootconfig.data` nên tìm ra `BootConfigApplication`. Test kiểm JPA repository/entity và đảm bảo controller không lọt vào slice; tự động rollback test transaction làm test độc lập theo mặc định.

**Không đặt `@DataJpaTest` + `@SpringBootTest` trên cùng một class.** Spring Boot test annotations dùng bootstrappers khác nhau, kết hợp sai có thể gây bootstrapper conflict. Nếu bạn cần full context và muốn rollback transaction, dùng `@SpringBootTest` + `@Transactional` theo test contract, chứ không “gộp hai slices”.

## 16. @TestConfiguration nested: bổ sung chứ không thay app

Spring Boot 3.5 docs phân biệt:

- Nested **`@TestConfiguration`**: dùng **cùng primary Boot application** và bổ sung beans.
- Nested **`@Configuration`**: thường được Spring Boot test xem như **nguồn cấu hình chính thay thế** khi không chỉ rõ classes tường minh.

**`src/test/java/com/example/bootconfig/NestedTestConfigurationAddsToApplicationTest.java`:**

~~~java
package com.example.bootconfig;

import com.example.bootconfig.core.WelcomeService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class NestedTestConfigurationAddsToApplicationTest {

    record TestMarker(String name) {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class ExtraBeans {

        @Bean
        TestMarker testMarker() {
            return new TestMarker("nested-test-config");
        }
    }

    @Autowired WelcomeService welcomeService;
    @Autowired TestMarker marker;
    @Autowired ApplicationContext context;

    @Test
    void nestedTestConfigurationAddsBean() {
        assertThat(marker.name())
                .isEqualTo("nested-test-config");
        assertThat(welcomeService.welcome("Lan"))
                .isEqualTo("Hello, Lan!");
    }

    @Test
    void nestedTestConfigurationDoesNotHideBootApp() {
        assertThat(
                context.getBean(BootConfigApplication.class)
        ).isNotNull();
    }
}
~~~

**Hai test methods** xác nhận marker chỉ dành cho test có mặt **cùng** ứng dụng thật. `@TestConfiguration` không phải “mini `@SpringBootApplication`”; nếu test nằm ngoài package app và không tìm primary source, chỉ thêm nested `@TestConfiguration` vẫn **không** chữa được lỗi thiếu `@SpringBootConfiguration`.

Khi chỉ cần thay thuộc tính, `@SpringBootTest(properties="...")` hoặc `@ActiveProfiles("test")` thường đơn giản hơn viết một config bean hoàn toàn mới. Chỉ dùng `@TestConfiguration` khi thật sự cần bean definition chuyên biệt.

## 17. Top-level @TestConfiguration được import có chủ đích

Top-level test config không nên vô tình được quét vào mọi test. Spring Boot loại top-level `@TestConfiguration` khỏi component scan bình thường; bạn đưa vào context đích bằng `@Import`.

**`src/test/java/com/example/bootconfig/ExtraTestBeans.java`:**

~~~java
package com.example.bootconfig;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class ExtraTestBeans {

    public record NamedMarker(String name) {
    }

    @Bean
    NamedMarker importedMarker() {
        return new NamedMarker("only-when-imported");
    }
}
~~~

**`src/test/java/com/example/bootconfig/TopLevelImportedTestConfigurationTest.java`:**

~~~java
package com.example.bootconfig;

import com.example.bootconfig.core.WelcomeService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@Import(ExtraTestBeans.class)
class TopLevelImportedTestConfigurationTest {

    @Autowired WelcomeService welcomeService;
    @Autowired ExtraTestBeans.NamedMarker marker;

    @Test
    void explicitlyImportedTestConfigDoesNotReplaceApp() {
        assertThat(marker.name())
                .isEqualTo("only-when-imported");
        assertThat(welcomeService.welcome("Mai"))
                .isEqualTo("Hello, Mai!");
    }
}
~~~

**Một test method**. `@Import(ExtraTestBeans.class)` chỉ bổ sung cấu hình; không thay primary source detection. Nếu primary Boot app không được tìm, import một `@TestConfiguration` phụ **không mặc nhiên sửa** vấn đề gốc. Khi test có nhiều customizations, hạn chế bean overriding không rõ nghĩa; với Spring Framework 6.2 dùng `@MockitoBean(enforceOverride=true)` nếu cần bảo đảm bean thật tồn tại trước override.

## 18. Nested @Configuration có thể thay main app — test vẫn PASS nhưng sai phạm vi

Ví dụ sau nằm ở package **ngoài root application** nên không làm các test khác vô tình component-scan nested config này.

**`src/test/java/com/example/outside/NestedPlainConfigurationReplacesApplicationTest.java`:**

~~~java
package com.example.outside;

import com.example.bootconfig.BootConfigApplication;
import com.example.bootconfig.core.WelcomeService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class NestedPlainConfigurationReplacesApplicationTest {

    record LocalMarker(String origin) {
    }

    @Configuration(proxyBeanMethods = false)
    static class LocalConfig {

        @Bean
        LocalMarker localMarker() {
            return new LocalMarker("plain-nested-config");
        }
    }

    @Autowired ApplicationContext context;
    @Autowired LocalMarker marker;

    @Test
    void nestedPlainConfigurationBecomesPrimarySource() {
        assertThat(marker.origin())
                .isEqualTo("plain-nested-config");
        assertThat(context.getBeansOfType(
                BootConfigApplication.class
        )).isEmpty();
    }

    @Test
    void noMainComponentScanMeansNoWelcomeService() {
        assertThat(
                context.getBeansOfType(WelcomeService.class)
        ).isEmpty();
    }
}
~~~

**Hai test methods** cố tình xác nhận khác biệt. Mặc dù annotation của class là `@SpringBootTest`, nested `@Configuration` làm source test chỉ có `LocalConfig`: **không có application component scan** và không có `WelcomeService`. Test có thể tải context mà không báo “Unable to find @SpringBootConfiguration”, nhưng nó **không kiểm ứng dụng thật**.

**Cách sửa khi muốn full app + bean bổ sung:** chuyển `@Configuration` thành `@TestConfiguration` **và** đặt test trong app package để autodetect, hoặc dùng `@SpringBootTest(classes=BootConfigApplication.class)` và `@Import(LocalConfig.class)` nếu đây là cấu hình cần thêm. Không biến nested plain `@Configuration` thành lệnh sửa tự động không kiểm.

Nếu ý định ban đầu chỉ là Spring context nhỏ, hãy dùng `@SpringJUnitConfig(LocalConfig.class)` — rõ ràng hơn và không ngụ ý full Boot app.

## 19. @SpringBootTest(classes=...) sửa test nằm ngoài package root

**`src/test/java/com/example/outside/ExplicitApplicationFromOtherPackageTest.java`:**

~~~java
package com.example.outside;

import com.example.bootconfig.BootConfigApplication;
import com.example.bootconfig.core.WelcomeService;
import com.example.bootconfig.data.NoteRepository;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = BootConfigApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "app.welcome-prefix=Explicit"
)
class ExplicitApplicationFromOtherPackageTest {

    @Autowired WelcomeService welcomeService;
    @Autowired ApplicationContext context;

    @Test
    void explicitClassesBypassPackageAutodetection() {
        assertThat(
                context.getBean(BootConfigApplication.class)
        ).isNotNull();

        assertThat(welcomeService.welcome("Hoa"))
                .isEqualTo("Explicit, Hoa!");
    }

    @Test
    void explicitFullAppStillScansItsOwnRepositories() {
        assertThat(
                context.getBeansOfType(NoteRepository.class)
        ).hasSize(1);
    }
}
~~~

**Hai test methods** nằm ở `com.example.outside`, một nhánh sibling của `com.example.bootconfig`. Không có `classes=...` thì Boot test **không tự đi ngang** đến `com.example.bootconfig`. Với explicit source, việc chọn config không phụ thuộc package của test nữa; scan vẫn **theo primary config class/metadata**.

Vì vậy hãy dùng FQCN chính xác và test property sentinel để chứng minh chạy đúng application. Nếu source là app khác trong mono-repo, context vẫn có thể start và test dễ “PASS giả” nếu assertion quá nông.

## 20. @SpringJUnitConfig: khi không cần Boot auto-configuration

**`src/test/java/com/example/outside/PlainSpringOnlyTest.java`:**

~~~java
package com.example.outside;

import com.example.bootconfig.BootConfigApplication;
import com.example.bootconfig.core.WelcomeService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(PlainSpringOnlyTest.MiniConfig.class)
class PlainSpringOnlyTest {

    @Configuration(proxyBeanMethods = false)
    static class MiniConfig {

        @Bean
        WelcomeService welcomeService() {
            return new WelcomeService("Plain");
        }
    }

    @Autowired WelcomeService welcomeService;
    @Autowired ApplicationContext context;

    @Test
    void directConfigurationLoadsSmallSpringContext() {
        assertThat(welcomeService.welcome("Binh"))
                .isEqualTo("Plain, Binh!");
    }

    @Test
    void smallContextDoesNotBootstrapBootApplication() {
        assertThat(context.getBeansOfType(
                BootConfigApplication.class
        )).isEmpty();
    }
}
~~~

**Hai test methods** chứng minh một **Spring context hợp lệ** không cần `@SpringBootApplication`. `@SpringJUnitConfig` gồm `SpringExtension` và `@ContextConfiguration`, tạo context từ `MiniConfig`. Không giả định Spring Boot property files/auto-config/server/JPA được load vì không chạy `SpringApplication` của Boot.

Một nhu cầu thường gặp là test một số `@Bean`, validator hoặc client adapter không phụ thuộc Boot features; lúc đó `@SpringJUnitConfig(MiniConfig.class)` nhanh và rõ hơn `@SpringBootTest`.

### Khi nào chọn @ContextConfiguration trực tiếp?

Hai lối tương đương về mục đích Spring TestContext:

~~~java
@SpringJUnitConfig(MyConfig.class)
class SmallTest {
}
~~~

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = MyConfig.class)
class SmallTest {
}
~~~

Đây là **snippets**, `MyConfig` là type minh họa, không thuộc runnable demo. Nếu cần Boot auto-configuration, ConfigData, web server, Boot test features và các customizers, dùng `@SpringBootTest(classes=... )`; đừng chỉ đổi annotation tên mà mong được cùng runtime behavior.

## 21. Đếm số test methods và trách nhiệm từng lớp

Trong project với các file đầy đủ ở mục 7–20:

| Lớp | Tests | Kiểm gì? |
| --- | ---: | --- |
| `BootConfigurationDiscoveryTest` | 2 | Full Boot autodetect, controller/bean thực |
| `WelcomeWebMvcSliceTest` | 2 | MVC slice + @MockitoBean; JPA repo excluded |
| `NoteRepositorySliceTest` | 2 | JPA slice + H2; MVC controller excluded |
| `NestedTestConfigurationAddsToApplicationTest` | 2 | Nested @TestConfiguration bổ sung bean mà giữ app |
| `TopLevelImportedTestConfigurationTest` | 1 | Top-level @TestConfiguration được @Import |
| `NestedPlainConfigurationReplacesApplicationTest` | 2 | Nested @Configuration thay app config |
| `ExplicitApplicationFromOtherPackageTest` | 2 | Outside package nhưng explicit app source |
| `PlainSpringOnlyTest` | 2 | Spring TestContext thuần, không Boot auto-config |
| **Tổng** | **15** | Các dấu hiệu chính của bootstrap source selection |

**Không có** lớp `@SpringBootTest` bị thiếu config cố ý trong test task runnable. Mục 22 đưa **phản ví dụ** để tái hiện lỗi nếu muốn chủ động kiểm tra, nhưng nó phải được tách sang nhánh thử nghiệm hoặc classpath riêng, không commit một test fail cố ý vào default build.

Các tests này không chứng minh Spring Boot/JPA trên mọi major versions; chúng được soạn cho Java17/Boot3.5.16. Dùng đúng dependency/BOM/runtime của ví dụ rồi chạy thật mới có bằng chứng CI.

## 22. Phản ví dụ gây lỗi thiếu @SpringBootConfiguration

Giả sử application nằm trong `com.example.bootconfig` nhưng test đặt ở package **com.example.diagnostics**:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class BrokenBootLookupTest {

    @Test
    void contextLoads() {
    }
}
~~~

Đây là **một file CỐ Ý SAI**, không nằm trong demo runnable. Vì test package đi lên `com.example.diagnostics` → `com.example` → `com`, nó không đi xuống `com.example.bootconfig`, nên có thể báo không tìm được `@SpringBootConfiguration`.

Sửa theo một trong hai cách:

**Cách A — đặt test dưới package app:**

~~~java
package com.example.bootconfig.diagnostics;

@SpringBootTest
class CorrectlyLocatedTest {
    @Test
    void contextLoads() {
    }
}
~~~

**Cách B — explicit primary config dù test ở nơi khác:**

~~~java
package com.example.diagnostics;

@SpringBootTest(classes = BootConfigApplication.class)
class CorrectlyTargetedTest {
    @Test
    void contextLoads() {
    }
}
~~~

Hai đoạn là **snippets**, cần imports cho JUnit, Boot test và application class, không được thêm nguyên vào project mà không chỉnh packaging/compile. Cách A thuận tiện trong một module app; cách B đặc biệt hữu ích trong shared tests, integration source set hoặc mono-repo.

**Đừng sửa bằng việc thêm một `@SpringBootApplication` trống trong `src/test/java/com/example.diagnostics` mà không nghĩ về component scan/auto-config.** Test có thể “hết lỗi” nhưng thực tế nạp một ứng dụng test khác, bỏ qua domain beans của app cần kiểm.

## 23. Lỗi "đã tìm thấy config nhưng vẫn không có bean"

Sau khi chọn `@SpringBootTest(classes=...)`, test có thể gặp:

~~~text
NoSuchBeanDefinitionException:
  No qualifying bean of type '...WelcomeService'
~~~

Đây là **lỗi khác bước** so với "Unable to find @SpringBootConfiguration". Các nguyên nhân hay gặp:

1. Main app class nằm **dưới package quá sâu**, component scanning không phủ các siblings.
2. `@ComponentScan` có base packages sai, include/exclude filters sai.
3. Service không có `@Component`/`@Service` hoặc đăng ký `@Bean`.
4. `@Profile`/`@ConditionalOnProperty`/`@ConditionalOnClass` làm bean không được tạo.
5. Controller/service nằm trong module khác, dependency không có trên test runtime classpath.
6. `@WebMvcTest` slice chỉ chứa MVC beans, không tự đưa service thường vào.
7. Test dùng nested `@Configuration` làm primary source, không có app component scan.
8. Repository/entity discovery dùng base packages khác so với component scan.
9. Bean được thay bằng mock hoặc có nhiều candidates cần qualifier.
10. App có nhiều contexts parent/child và bạn inject nhầm cấp.

**Trình tự chẩn đoán:** trước tiên xác nhận source `BootConfigApplication.class` đã được load; tiếp đó kiểm bean definitions, conditions, profiles, scan boundaries và package paths. **Đừng** đổi liên tục giữa `@SpringBootTest`/`@ContextConfiguration` để thử may rủi khi chưa đọc root exception.

## 24. @TestConfiguration vs @Configuration: dễ gây PASS giả

Một bảng tóm tắt:

| Vị trí/annotation | Khi Boot test tự chọn source | Ứng dụng thực có được load? |
| --- | --- | --- |
| Không có nested config, test dưới app root | Tìm @SpringBootApplication ngược package | **Có**, nếu tìm được |
| Nested static `@TestConfiguration` | Bổ sung vào primary app config | **Có**, nếu primary được tìm |
| Nested static `@Configuration` | Có thể được xem là default source cho test | **Không nhất thiết**; thường thay primary |
| Top-level `@TestConfiguration` không import | Không được scan thường xuyên bởi Boot | Không tự sửa missing primary |
| Top-level `@TestConfiguration` + `@Import` | Bổ sung bean vào context đã bootstrap | Có nếu primary app source đúng |
| `@SpringBootTest(classes=App.class)` | Dùng App làm source tường minh | Có, theo App |
| `@SpringJUnitConfig(Mini.class)` | Spring TestContext trực tiếp từ Mini | Không dùng Boot app nếu không khai báo |
| `@SpringBootTest(classes=OtherApp.class)` | Nạp OtherApp | Có thể PASS nhưng **sai app** |

**Đừng chỉ kiểm một marker bean** rồi kết luận cả ứng dụng đã được nạp. Test phải kiểm điều quan trọng theo contract: controller, service thật, repository, profile property và configuration class identity.

Khi test có cả `@Import`, nested test config, `@MockitoBean` hoặc custom context initializers, cache key/context customization có thể thay đổi. Cùng test class vẫn có thể tạo contexts khác nhau theo properties/profiles, nên không suy từ số lần startup logs rằng config đã đúng.

## 25. @WebMvcTest và @DataJpaTest cũng cần cấu hình gốc đúng

Một sai lầm:

~~~java
@WebMvcTest(WelcomeController.class)
class MyMvcTest {
}
~~~

Nếu test nằm ngoài application package, Spring Boot test bootstrapper vẫn có thể không tìm được primary config. `WelcomeController.class` ở đây là **đối tượng của MVC slice**, không phải replacement cho `@SpringBootApplication`.

Tương tự:

~~~java
@DataJpaTest
class MyRepositoryTest {
}
~~~

cần Boot root config hoặc nguồn explicit thích hợp, cộng entity/repository scanning và embedded/test datasource. Với `@DataJpaTest`, đừng vội kết luận lỗi thiếu config là do H2 URL; bước tìm Boot source đi trước setup database.

**Khi test slice của một module không có main app class**, có thể:

- Đặt test trong module application/đúng package và phụ thuộc module domain cần kiểm.
- Cấp một **test-only `@SpringBootConfiguration` phù hợp** tại package test để slice có primary root tối thiểu, với bean registration/auto-config được cân nhắc; tránh quét cả monorepo.
- Dùng `@ContextConfiguration(classes=...)` hoặc các cơ chế Spring Test hỗ trợ tường minh để chỉ nguồn cho slice, đồng thời kiểm slice vẫn giới hạn beans như dự định.
- Nếu chỉ test bean thuần, đổi sang `@SpringJUnitConfig` thay vì ép một Boot slice.

**Không** ghép hai slice annotations như `@DataJpaTest` + `@WebMvcTest`: chúng dùng test bootstrappers khác nhau và không phải API hợp lệ để “chọn nhiều phần” bằng cách chồng annotation. Cần full context thì dùng `@SpringBootTest` hoặc một slice + `@AutoConfigure...` thích hợp theo tài liệu.

## 26. Explicit @ComponentScan trên main app có thể làm slice quá rộng

Spring Boot `@SpringBootApplication` cung cấp component-scan exclude filters được Boot test slices sử dụng. Nếu main application viết thêm:

~~~java
@SpringBootApplication
@ComponentScan(basePackages = {
    "com.example.bootconfig",
    "com.example.shared"
})
public class BootConfigApplication {
}
~~~

Đây là **phản ví dụ**, không thay file application runnable. Một `@ComponentScan` explicit có thể ghi đè behavior filter cần cho test slicing; `@DataJpaTest` bỗng thấy MVC/security/business beans mà nó không định load, dẫn tới context lỗi hoặc test quá nặng.

Ưu tiên:

1. Đặt application class ở root package hợp lý, để default component scan hoạt động.
2. Nếu có extra domain configuration, tách nó ra `@Configuration` riêng và `@Import` đúng nơi.
3. Nếu cần scan package ngoài root, khai báo filters/`TypeExcludeFilter` phù hợp với Boot testing docs.
4. Với slice, kiểm bean presence/absence bằng `ApplicationContext#getBeansOfType` để phát hiện scan leak.
5. Tránh biến `@SpringBootTest(classes=...)` thành cách hợp thức hóa mọi scan rộng.

Một app boot configuration “đúng” nhưng scan boundaries “sai” vẫn có thể làm integration test fail. Đây là ví dụ vì sao phải phân biệt **discovery**, **component scanning**, **auto-configuration conditions** và **bean instantiation**.

## 27. Multi-module, source set integrationTest và classpath

Trong mono-repo:

~~~text
settings.gradle
app/
  src/main/java/com/example/bootconfig/BootConfigApplication.java
core/
  src/main/java/com/example/core/DomainService.java
  src/test/java/com/example/core/DomainServiceTest.java
integration-tests/
  src/test/java/com/example/it/WorkflowTest.java
~~~

Khi `WorkflowTest` ở module `integration-tests`, chỉ thêm:

~~~java
@SpringBootTest(classes = BootConfigApplication.class)
~~~

**không đủ** nếu `BootConfigApplication.class` **không có trên test compile/runtime classpath**. Phải khai báo module dependency phù hợp, ví dụ trong `integration-tests/build.gradle`:

~~~groovy
dependencies {
    testImplementation project(':app')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
~~~

Đây là snippet, không phải build đầy đủ; project Gradle phải có `include ':app', ':integration-tests'` và plugin phù hợp. Đừng đoán app JAR tự được đưa vào test task chỉ vì các module nằm trong cùng repository.

Nếu dùng custom `sourceSets.integrationTest`:

~~~groovy
tasks.register('integrationTest', Test) {
    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()
}
~~~

Đây là snippet, cần thêm source set và dependency configurations theo Gradle version. `testClassesDirs`/`classpath` thiếu sẽ gây `NO-SOURCE`, `ClassNotFoundException` hoặc test không discover dù `@SpringBootConfiguration` hoàn toàn đúng trong source.

**Quy tắc:** Java package hierarchy quyết định **đâu là ứng viên auto-detection**, còn runtime classpath quyết định **ứng viên có thực sự được JVM load thấy hay không**. Phải đúng **cả hai**.

## 28. @ActiveProfiles và @TestPropertySource không sửa việc tìm source

Một test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
    "app.welcome-prefix=Test"
})
class SomeTest {
}
~~~

Đây là snippet cần imports, không phải file runnable. `@ActiveProfiles` chọn profile; `@TestPropertySource` thêm properties cho context; chúng **không dịch chuyển vị trí package** của test và không chỉ ra `@SpringBootApplication`.

Sau khi bootstrap source đúng, profile và property có thể ảnh hưởng beans qua `@Profile`, `@ConditionalOnProperty`, database URL, security. Nhưng nếu root exception là missing `@SpringBootConfiguration`, thay `spring.profiles.active` hoặc `logging.level` thường không giải quyết.

Phân biệt:

- **Source selection:** `@SpringBootTest(classes=...)`, package autodetection, `@ContextConfiguration`.
- **Environment selection:** `@ActiveProfiles`, `@TestPropertySource`, `@SpringBootTest(properties=...)`, `@DynamicPropertySource`.
- **Bean selection:** component scanning, `@Import`, conditional annotations, qualifiers, `@MockitoBean`.
- **Context lifetime:** context cache, `@DirtiesContext`.
- **Test execution:** JUnit/Gradle source sets và test tasks.

Mỗi nhóm có tác động khác nhau. Không thay global system properties chỉ để làm Boot nhìn thấy một application class.

## 29. Debug logs và cách thu bằng chứng

Bắt đầu với target test cụ thể:

~~~bash
./gradlew test \
  --tests "com.example.bootconfig.BootConfigurationDiscoveryTest" \
  --stacktrace --info
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.bootconfig.BootConfigurationDiscoveryTest" --stacktrace --info
~~~

Trước khi chạy, kiểm project JDK/Gradle Wrapper:

~~~bash
./gradlew --version
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew test --tests "*BootConfigurationDiscoveryTest" --rerun-tasks
~~~

**Đọc root cause đầu tiên** của `IllegalStateException` trong stack trace, không chỉ nhìn exception cuối do JUnit/Gradle wrap. Nếu root cause là:

~~~text
Unable to find a @SpringBootConfiguration...
~~~

hãy kiểm package/source. Nếu root cause đã là:

~~~text
BeanCreationException
NoSuchBeanDefinitionException
Failed to configure a DataSource
Failed to bind properties
Port already in use
Unable to start web server
~~~

thì Boot có thể đã **tìm được source**, và vấn đề đang ở bước khác.

Có thể bật Spring TestContext cache diagnostics trong `src/test/resources/application.properties` riêng cho debug:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.org.springframework.boot.test.context=DEBUG
~~~

Đây là file **debug tùy chọn**, không nằm trong runnable demo và không sửa `src/main/resources/application.properties`. `debug=true` có thể in condition evaluation report khi Boot app startup; report này hữu ích cho **auto-configuration conditions** sau khi source đã được chọn, **không phải** bằng chứng rằng Boot sẽ tìm đúng primary config từ package sai.

Đừng bật DEBUG dài hạn rồi đọc hàng nghìn dòng logs để thay thế việc kiểm đúng package/classpath.

## 30. Phân tích một số lỗi trông giống nhưng bản chất khác

### A. Không tìm thấy @SpringBootConfiguration

~~~text
IllegalStateException: Unable to find a @SpringBootConfiguration
~~~

**Bước:** Primary config detection. **Sửa:** package đúng, source rõ bằng `classes=...`, đảm bảo app class trên classpath.

### B. Đã chọn sai main app và context vẫn load

~~~text
context.getBean(AppA.class)    -> absent
context.getBean(AppB.class)    -> present
~~~

**Bước:** Source selection sai. **Sửa:** pin `@SpringBootTest(classes=AppA.class)` và assert identity/expected business beans. Đừng chỉ kiểm “contextLoads”.

### C. Có @SpringBootApplication nhưng bean thiếu

~~~text
NoSuchBeanDefinitionException: WelcomeService
~~~

**Bước:** Component scan/conditional/bean registration. **Sửa:** scan boundaries, annotations, imports, profiles và mock setup.

### D. Có hai bean cùng type

~~~text
NoUniqueBeanDefinitionException: expected single matching bean
~~~

**Bước:** Bean candidate selection. **Sửa:** `@Qualifier`/`@Primary` nếu hợp đồng yêu cầu, không thêm annotation tùy ý để che sai context.

### E. JPA slice không tìm entity

~~~text
Not a managed type: class com.example...NoteEntry
~~~

**Bước:** Entity/repository scanning; có thể root package/config không chứa entity. **Sửa:** đúng `@Entity`, basePackages, entity scan và Test task classpath. Không phải mọi “Not a managed type” đều là missing @SpringBootConfiguration.

### F. Duplicate boot configuration

~~~text
Multiple @SpringBootConfiguration candidates
~~~

**Bước:** Autodetection ambiguity. **Sửa:** một primary source rõ trong module/package hoặc `classes=...`; test-only app config phải đặt đúng namespace, không rải nhiều Boot application classes lên cùng search path.

### G. Missing JUnit class hoặc tests không chạy

~~~text
No tests found / ClassNotFoundException / NoClassDefFoundError
~~~

**Bước:** Compile/runtime/test task classpath hoặc discovery. **Sửa:** Gradle sources, `testImplementation`/`testRuntimeOnly`, JUnit launcher và `useJUnitPlatform()`. Không sửa Spring annotations trước khi JVM nạp được classes.

### H. Invalid combined bootstrappers

~~~text
Configuration error: multiple declarations of @BootstrapWith
~~~

**Bước:** Dùng hai test slice annotations hoặc test bootstrapper combinations không tương thích. **Sửa:** chọn một primary test annotation và `@AutoConfigure...` cần thiết, không chồng `@WebMvcTest` + `@DataJpaTest` hoặc nhiều `@*Test`.

## 31. Khi nhiều @SpringBootApplication classes xuất hiện

Trong multi-module repository có thể có:

~~~text
com.example.orders.OrdersApplication
com.example.payments.PaymentsApplication
com.example.shared.SharedTest
~~~

Test ở `com.example.shared` không tự chọn giữa hai sibling apps bằng tên `OrdersApplication`/`PaymentsApplication`. Một số cấu trúc không tìm được config, cấu trúc khác có thể gặp nhiều candidates. Đừng thêm một app class ở `com.example` chỉ để làm cả hai tests “hết lỗi”, vì nó có thể quét **cả orders và payments** gây duplicate bean/DB configuration.

Cách lựa chọn:

- Integration test thuộc Orders -> `@SpringBootTest(classes=OrdersApplication.class)`.
- Integration test thuộc Payments -> `@SpringBootTest(classes=PaymentsApplication.class)`.
- Domain-only tests -> `@SpringJUnitConfig(DomainConfig.class)` hoặc unit tests.
- App tests tốt nhất đặt dưới package root của app thật.
- Nếu có shared integration module, **test dependencies** cần mang đúng app artifact.
- Giữ config các app tách biệt theo Gradle modules, package roots, profiles và test reports.

**Không nhận tên `@SpringBootApplication` như test selector tự động**: Boot không chọn một class vì nó giống tên của test hoặc vì một `main()` method được chạy lần trước.

## 32. Test-only Boot configuration có thể có ích, nhưng phải công khai mục đích

Trong một thư viện/starter không có executable app main, test `@WebMvcTest` hoặc `@DataJpaTest` đôi lúc cần một test root:

~~~java
@SpringBootConfiguration
@EnableAutoConfiguration
class TestOnlyBootConfiguration {
}
~~~

Đây là **snippet** cần imports, không thuộc runnable project. `@SpringBootConfiguration` chỉ làm Boot nhận diện root configuration; `@EnableAutoConfiguration` cho phép những auto-configurations cần thiết được kích hoạt theo conditions. Nhưng nó **không tự scan** tất cả `@Service`/`@Entity` như `@SpringBootApplication`. Có thể cần `@Import`/`@EntityScan`/`@EnableJpaRepositories` đúng loại test.

Cách này phù hợp với một module library độc lập **nếu không có real application source**. Tuy nhiên:

1. Không đặt thêm root `@SpringBootConfiguration` tùy tiện trong application package đã có `@SpringBootApplication`.
2. Không cho test root quét một package quá rộng.
3. Đảm bảo integration tests thật vẫn dùng real app source, không bị fake configuration lấy chỗ.
4. Test được bean boundaries và source identity.
5. Nếu test chỉ cần vài beans, Spring TestContext thuần thường đơn giản hơn.

**Một test root giả có thể chữa exception lookup nhưng làm mất mục tiêu kiểm app thật.** Vì thế ghi rõ intentional test root trong review.

## 33. Context cache, các class cấu hình và test tốc độ

Spring TestContext cache các ApplicationContexts có cấu hình tương đương để tránh reload. `@SpringBootTest(classes=App.class)`, `@ActiveProfiles`, test properties, `@Import`, `@MockitoBean` customizers và nested configurations có thể ảnh hưởng cache key.

Khi hai tests load context khác nhau:

~~~text
Test A: BootConfigApplication + property Hello
Test B: BootConfigApplication + property Explicit
Test C: BootConfigApplication + ExtraTestBeans
Test D: LocalConfig only
~~~

kết quả là các contexts **có thể khác nhau**; đừng kỳ vọng luôn cùng bean singleton. Nhưng cũng đừng dùng `@DirtiesContext` khắp nơi để “chắc chắn fresh”: nó tăng chi phí startup và có thể phá parallel tests dùng cùng context.

Mục tiêu chẩn đoán:

- **Correctness:** mỗi test dùng đúng config classes, properties, bean overrides.
- **Isolation:** tests không sửa global/DB state khiến tests khác FAIL.
- **Performance:** tái sử dụng context khi cấu hình thực sự tương đương.
- **Observability:** nếu context bootstrap fail, xác định root source trước khi nghĩ tới cache.

`@MockitoBean` trong Spring Framework 6.2 mặc định có reset theo test lifecycle; điều này **không** sửa primary source missing, và nếu target bean không tồn tại, default behavior có thể tạo mock khiến test PASS giả. Cân nhắc `@MockitoBean(enforceOverride=true)` khi cần kiểm bean thật đã tồn tại trong context.

## 34. Checklist chẩn đoán có thứ tự

- [ ] Đã xác định **exception gốc** là missing `@SpringBootConfiguration` hay bean/DB/port khác?
- [ ] Test có đúng annotation `@SpringBootTest`/`@WebMvcTest`/`@DataJpaTest` không?
- [ ] `package` declaration trong test nằm dưới package của app chính?
- [ ] FQCN và annotation trên main class thật là gì?
- [ ] Main dùng `@SpringBootApplication` hay chỉ `@Configuration`?
- [ ] Boot primary class có trên **test runtime classpath** của task?
- [ ] Với multi-module, `testImplementation project(':app')` phù hợp?
- [ ] Với custom `integrationTest` source set, đã cấu hình classesDirs/classpath?
- [ ] Test có nested static `@Configuration` thay primary không chủ đích?
- [ ] Nested `@TestConfiguration` được hiểu là bổ sung, không thay Boot app?
- [ ] Top-level `@TestConfiguration` có được `@Import` đúng nơi?
- [ ] Có hai/multiple Boot configuration classes gây ambiguity?
- [ ] `@SpringBootTest(classes=...)` trỏ đúng application khi test nằm ngoài package?
- [ ] Có assert `ApplicationContext.getBean(RealApplication.class)`?
- [ ] Có assert real service/controller/repository chứ không chỉ contextLoads?
- [ ] `@WebMvcTest(Controller.class)` có mock/bean dependency rõ?
- [ ] `@DataJpaTest` có entity/repository/H2/test DB setup phù hợp?
- [ ] Test slice **không** vô tình scan mọi components do `@ComponentScan` explicit?
- [ ] Không chồng nhiều slice annotations hoặc bootstrappers?
- [ ] `@ContextConfiguration`/`@SpringJUnitConfig` chỉ dùng khi không cần Boot extras?
- [ ] `@ActiveProfiles`, test properties được phân biệt với source selection?
- [ ] Test root chỉ có `@SpringBootConfiguration` đã được import/autoconfig đủ?
- [ ] Test class source set và resource paths đúng với Gradle task?
- [ ] `./gradlew test --tests ... --rerun-tasks` discover đúng số tests?
- [ ] CI không chỉ nhìn "BUILD SUCCESSFUL" nếu tests SKIPPED/NO-SOURCE?
- [ ] JUnit XML/Gradle reports đã kiểm expected count?
- [ ] Logs DEBUG/condition report được bật đúng mục đích, không che root exception?
- [ ] Không đổi global package/component scan để che một test đặt sai chỗ?
- [ ] Không dùng `@DirtiesContext` như “chữa” lỗi source detection?
- [ ] Không tuyên bố code đã compile/run nếu mới chỉ được rà soát?

## 35. Lệnh chạy và kỳ vọng của bộ ví dụ

Với JDK 17+, Gradle Wrapper, các files Gradle/Java/resources đúng các mục trên:

~~~bash
./gradlew --version
./gradlew clean test
./gradlew test --tests "com.example.bootconfig.BootConfigurationDiscoveryTest"
./gradlew test --tests "com.example.bootconfig.web.WelcomeWebMvcSliceTest"
./gradlew test --tests "com.example.bootconfig.data.NoteRepositorySliceTest"
./gradlew test --tests "com.example.outside.ExplicitApplicationFromOtherPackageTest"
./gradlew test --tests "com.example.outside.PlainSpringOnlyTest"
./gradlew test --rerun-tasks --stacktrace
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test
.\gradlew.bat test --tests "com.example.bootconfig.BootConfigurationDiscoveryTest"
.\gradlew.bat test --tests "com.example.bootconfig.web.WelcomeWebMvcSliceTest"
.\gradlew.bat test --tests "com.example.bootconfig.data.NoteRepositorySliceTest"
.\gradlew.bat test --tests "com.example.outside.ExplicitApplicationFromOtherPackageTest"
.\gradlew.bat test --tests "com.example.outside.PlainSpringOnlyTest"
.\gradlew.bat test --rerun-tasks --stacktrace
~~~

**Expected behavior theo source:**

| Nhóm | Tests | Kết quả dự kiến |
| --- | ---: | --- |
| Full Boot autodetect | 2 | Main class bean có; prefix Hello; MockMvc "Hello, Ada!" |
| Web MVC slice | 2 | Mock service trả "Slice, Ada!"; JPA repository absent |
| Data JPA slice | 2 | NoteEntry save/find thành công; MVC controller absent |
| Nested additive TestConfiguration | 2 | Marker riêng có; WelcomeService và app main vẫn có |
| Top-level imported TestConfiguration | 1 | Marker import có; app service vẫn hoạt động |
| Nested plain Configuration | 2 | LocalMarker có; Boot app/service **không** có |
| Explicit full App từ outside package | 2 | App bean có; prefix Explicit; NoteRepository có |
| Plain Spring TestContext | 2 | Prefix Plain; không load Boot app |
| **Tổng** | **15** | Phân biệt đúng các nhánh source detection/loading |

Mẫu kết quả business string:

~~~text
Boot full:    Hello, Ada!
MVC slice:    Slice, Ada!
Explicit app: Explicit, Hoa!
Plain Spring: Plain, Binh!
Jpa slice:    NoteEntry title = Alpha
~~~

Đây là **dự kiến theo code và cấu hình**, không phải stdout Gradle/JUnit/H2 đã quan sát. Project **chưa được compile hay thực thi trong lúc soạn bài**, và Spring startup logs có thể chứa nhiều dòng khác. Để xác nhận, cần chạy `./gradlew clean test` và xem `build/reports/tests/test/index.html` hoặc `build/test-results/test/TEST-*.xml`; phải chứng minh có đủ **15 tests executed**, không chỉ nhìn build exit code.

Nếu muốn cố ý tái hiện missing configuration error, thêm `BrokenBootLookupTest` như ví dụ **trong một branch thử nghiệm riêng**, chạy đúng class đó rồi **bỏ khỏi default suite**. Không đưa test fail chủ đích vào main CI chỉ để minh họa.

## 36. Kết luận và tài liệu tham khảo

**Không tìm thấy `@SpringBootConfiguration` là vấn đề chọn điểm xuất phát cho test context.** Cách chẩn đoán đúng:

1. Xác minh test package có là con của application package và app class có annotation Boot đúng.
2. Xác minh app class thực sự có trong test runtime classpath của Gradle task/module.
3. Nếu cần load app từ package khác, dùng `@SpringBootTest(classes=RealApp.class)`.
4. Nếu chỉ cần Spring beans tối thiểu, dùng `@SpringJUnitConfig(MiniConfig.class)`.
5. Dùng nested `@TestConfiguration` để **bổ sung**, không nhầm nested `@Configuration` có thể **thay** app.
6. Đừng xem `@WebMvcTest(Controller.class)` là explicit Boot primary source; slice vẫn cần config root phù hợp.
7. Khi context đã tạo nhưng thiếu bean, chuyển sang kiểm component scan, auto-config conditions, profile và imports.
8. Test phải assert real application identity và những beans quan trọng; `contextLoads()` một mình chưa bảo đảm chọn đúng ứng dụng.

### Tài liệu chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications / Detecting Test Configuration](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — @SpringBootTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html)
- [Spring Boot 3.5 — @SpringBootConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringBootConfiguration.html)
- [Spring Boot 3.5 — @TestConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/TestConfiguration.html)
- [Spring Boot 3.5 — @WebMvcTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html)
- [Spring Boot 3.5 — @DataJpaTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html)
- [Spring Boot 3.5 — How-to: Structure @Configuration Classes for Slice Tests](https://docs.spring.io/spring-boot/3.5/how-to/testing.html)
- [Spring Framework 6.2 — @SpringJUnitConfig](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/junit/jupiter/SpringJUnitConfig.html)
- [Spring Framework 6.2 — @ContextConfiguration](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management.html)
- [Spring Framework 6.2 — @MockitoBean / @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html)
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/)
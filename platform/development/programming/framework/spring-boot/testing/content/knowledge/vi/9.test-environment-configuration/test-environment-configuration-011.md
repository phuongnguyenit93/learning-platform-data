# Cấu hình môi trường test trong Spring Boot: dùng chung mà vẫn giữ ranh giới từng nhóm

## 1. Bài toán

Một dự án Spring Boot có thể gồm unit test cho logic, MVC test kiểm tra controller, JPA test cho repository và integration test nối nhiều tầng. Các nhóm đều cần một số quy ước chung, chẳng hạn Java/JUnit version, profile `test`, default properties và cách tạo dữ liệu. Nhưng **dùng chung cấu hình không đồng nghĩa tất cả test phải dùng chung Spring context, database, mock hoặc trạng thái**.

Nếu đặt `@SpringBootTest`, `@Transactional`, `@MockitoBean` và nhiều `@Import` vào một base class dùng cho mọi test, sẽ có các hệ quả:

- Unit test vốn chỉ cần object Java phải khởi động cả `ApplicationContext`.
- MVC slice lỡ nạp repository, database hoặc external client.
- JPA slice phụ thuộc vào web/service bean không thuộc mục đích kiểm thử.
- Test A sửa singleton/static state khiến test B sai khi chạy cả suite.
- Test A thay property/active profile làm thay đổi bean graph của nhóm khác.
- Context cache bị phân mảnh do các override nhỏ không kiểm soát, test chậm và khó debug.

**Mục tiêu thiết kế:** dùng chung *quy tắc ổn định*, còn từng nhóm tự kiểm soát *test bootstrap, beans, data fixtures, transactions, mocks và tài nguyên ngoài*. Điều này giữ bộ test dễ bảo trì, chạy nhanh và không phụ thuộc thứ tự.

## 2. Phân nhóm theo điều cần chứng minh

| Nhóm | Framework/annotation | Phạm vi cần có | Không nên tự động nạp |
| --- | --- | --- | --- |
| Unit nghiệp vụ | JUnit Jupiter, Mockito, `new Service(...)` | Java objects, fake/mock đúng boundary | Spring context, web server, database |
| Controller/MVC | `@WebMvcTest(MyController.class)`, `MockMvc` | Controller, MVC infrastructure, mock service | JPA repository, business service thật, scheduler |
| Repository | `@DataJpaTest` | Entity, repository, JDBC/JPA infrastructure, test database | Controller, HTTP client, messaging |
| Full integration | `@SpringBootTest` | Application wiring, service, repository, auto-config theo yêu cầu | Shared state từ class test khác |
| Adapter/remote integration | Spring test với stub HTTP/broker/container | HTTP client, serialization, timeout/retry, resource thật hoặc giả lập | Endpoint production, credentials cứng, port cố định |
| End-to-end/smoke | App chạy trên môi trường kiểm soát | Toàn chuỗi API/DB/message theo contract | Giả định rollback transaction trong test thread sẽ rollback ở server |

Một nhóm không bắt buộc phải dùng Spring chỉ vì dự án là Spring Boot. Nếu test một hàm tính giá hoặc giới hạn đầu vào, pure JUnit là lựa chọn đầu tiên.

### Cái gì nên dùng chung?

- Dependency test và version quản lý qua Spring Boot parent/BOM; build dùng `test` scope.
- Profile `test`, một số thuộc tính mặc định an toàn, convention logging.
- Data builders và assertion utilities **không lưu mutable state**.
- Các annotation tổng hợp nhỏ chỉ mô tả metadata dùng chung.
- Quy ước CI về tag, đặt tên nhóm và xác định suite bắt buộc.

### Cái gì phải tách hoặc có chính sách dọn?

- Mockito stubbings/interaction history, transaction DB, data rows, consumer offsets.
- Singleton mutable beans, static cache, thread-local và background executors.
- Ports, stub server expectations, Testcontainers state và volume.
- File sinh ra trong test, đồng hồ test, random seed, credential.
- Các properties chỉ đúng cho một nhóm như `spring.datasource.url` hoặc `client.base-url`.

## 3. Tách “chung metadata” khỏi “chung runtime”

Hai test có thể sử dụng **cùng profile** nhưng tạo hai `ApplicationContext` khác nhau. Ngược lại, hai test classes có merged configuration tương đương có thể **tái sử dụng cùng một context** qua Spring TestContext cache. Bởi vậy:

- `@ActiveProfiles("test")` là metadata chung, không ép mọi lớp chia một context.
- `@WebMvcTest` và `@DataJpaTest` có những bootstrap/configuration khác nhau; cùng profile không làm chúng biến thành full-context test.
- Context reuse làm bean singleton có thể sống qua nhiều test classes. **Cache không phải một cơ chế isolation dữ liệu**.
- Nhiều tests cùng dùng một database vật lý vẫn có thể giẫm lên data, kể cả nếu có context riêng.
- Test container được reuse để tiết kiệm thời gian vẫn cần tách schema/topic/namespace hoặc cleanup khi test có side effect.

Một cách chia phạm vi hợp lý:

```text
src/
├── main/java/example/demo/          # Production components
└── test/
    ├── java/example/demo/
    │   ├── UseTestProfile.java       # Metadata dùng chung cho Spring tests
    │   ├── GreetingServiceUnitTest.java
    │   ├── GreetingControllerTest.java
    │   ├── CustomerNoteRepositoryTest.java
    │   └── FullAppIntegrationTest.java
    └── resources/
        ├── application-test.properties
        ├── fixtures/
        └── sql/
```

Bố cục này là gợi ý, không phải yêu cầu bắt buộc của framework. Với hệ thống lớn, có thể tách các package `unit`/`web`/`data`/`integration`, hoặc tạo Gradle/Maven module riêng khi classpath và tài nguyên cần khác biệt thực sự.

## 4. Dùng profile test chung ở mức metadata

Một custom composed annotation chỉ chứa `@ActiveProfiles("test")`:

```java
package example.demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.test.context.ActiveProfiles;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ActiveProfiles("test")
@interface UseTestProfile {
}
```

Sau đó các lớp Spring tests có thể dùng:

```java
@UseTestProfile
@WebMvcTest(GreetingController.class)
class GreetingControllerTest { /* ... */ }

@UseTestProfile
@DataJpaTest
class CustomerNoteRepositoryTest { /* ... */ }

@UseTestProfile
@SpringBootTest
class FullAppIntegrationTest { /* ... */ }
```

Ba đoạn khai báo trên chỉ **minh họa**, mã đầy đủ ở mục 8. Annotation `@UseTestProfile` tự nó không khởi chạy Spring context; annotation của **nhóm** quyết định điều đó.

**Tránh:** tạo annotation dùng chung chứa `@SpringBootTest` rồi gắn thêm `@WebMvcTest` hoặc `@DataJpaTest`. Các annotation bootstrap có thể xung đột, và bạn đã vô tình phá phạm vi slice. Nếu muốn một annotation riêng cho integration, đặt tên rõ `@FullIntegrationCheck` và chỉ dùng ở nhóm full-context.

### Property file dùng chung

Tệp `src/test/resources/application-test.properties` được Boot nạp khi profile `test` active:

```properties
app.greeting-prefix=Shared
spring.jpa.hibernate.ddl-auto=create-drop
```

Trong ví dụ này `app.greeting-prefix` là property được ứng dụng thực sự đọc; `spring.jpa.hibernate.ddl-auto` chỉ có ý nghĩa với context chứa JPA. Property chung không biến `@WebMvcTest` thành data test. Không ghi password hoặc URL production vào test resources.

Nếu viết `external.enabled=false`, hãy nhớ rằng property chỉ chặn network khi production code có cơ chế đọc nó: **chỉ có dòng property không tự tắt external calls**. Test không muốn gọi network nên mock adapter hoặc dùng stub server, không chỉ trông chờ vào một tên key.

## 5. Override riêng ở đúng nhóm

Spring Boot có thể nạp `application-test.properties` làm nền và test riêng ghi đè một số key:

```java
@UseTestProfile
@SpringBootTest
@TestPropertySource(properties = "app.greeting-prefix=Integration")
class FullAppIntegrationTest {
    // Assertions ở phần ví dụ đầy đủ.
}
```

`@TestPropertySource` từ Spring TestContext có `locations` cho file và `properties` cho inline values; inline test properties có precedence cao hơn file `@TestPropertySource`, và dynamic properties từ `@DynamicPropertySource` có mức ưu tiên cao hơn `@TestPropertySource`. Spring Boot còn có thứ tự property sources khác; hãy **assert giá trị thật qua `Environment`** khi có nhiều nguồn cùng một key.

### Kế thừa có kiểm soát

| Annotation | Cờ kế thừa | Mặc định | Điểm cần hiểu |
| --- | --- | --- | --- |
| `@ActiveProfiles` | `inheritProfiles` | `true` | Subclass có thể nhận profile cha rồi thêm profile riêng |
| `@TestPropertySource` | `inheritProperties` | `true` | Kế thừa inline properties từ superclass |
| `@TestPropertySource` | `inheritLocations` | `true` | Kế thừa các file properties từ superclass |
| `@ContextConfiguration` | `inheritLocations` | `true` | Kế thừa resource locations/classes của superclass |
| `@ContextConfiguration` | `inheritInitializers` | `true` | Kế thừa context initializers |
| `@TestExecutionListeners` | `inheritListeners` | `true` | Có thể kế thừa custom test listeners |

Để subclass thay profile cha, dùng `@ActiveProfiles(profiles="special", inheritProfiles=false)`. Nhưng cờ này **không tự xóa** `@TestPropertySource` hay config classes từ cha. Với các test group khác responsibility, tốt hơn dùng metadata annotation nhỏ thay vì một superclass với nhiều cấu hình.

### Configuration inheritance của @Nested

JUnit `@Nested` tạo non-static inner test class. Spring TestContext có `@NestedTestConfiguration(INHERIT/OVERRIDE)` để kiểm soát việc nhận test metadata từ enclosing class (mặc định `INHERIT` từ Spring Framework 5.3). Một nested child có thể dùng chung bootstrap của outer class, nhưng nếu nó cần hoàn toàn khác app context, nên cân nhắc tạo **top-level test class riêng** cho rõ ranh giới. Nested classes phù hợp nhất để nhóm tình huống của cùng một scope.

## 6. Chọn bootstrap đúng: @SpringBootTest so với test slices

- `@SpringBootTest` tạo context thông qua Spring Boot `SpringApplication`. Mặc định web environment là `MOCK` khi có web stack: có web application context nhưng **không khởi động embedded server**.
- `@SpringBootTest(webEnvironment=RANDOM_PORT)` mở server thật trên port ngẫu nhiên; client và server thường hoạt động ở những thread/transactions khác nhau.
- `@WebMvcTest` chỉ chọn các MVC components và test MVC infrastructure; service collaborator cần cung cấp mock hoặc import tối thiểu.
- `@DataJpaTest` nạp JPA slice, thường có test-managed transaction rollback sau mỗi method và có thể thay datasource bằng embedded DB nếu available.
- `@SpringJUnitConfig` là lối tắt `@ExtendWith(SpringExtension.class)` + `@ContextConfiguration`; **không mặc nhiên** bật mọi Spring Boot auto-configuration.

**Không đưa @Enable... hay @ComponentScan tùy biến quá rộng vào @SpringBootApplication chỉ để phục vụ một test.** Theo tài liệu Boot, cấu hình `@ComponentScan` tự viết có thể làm mất những exclude filters của test slices; đặt công nghệ riêng ở configuration class tách biệt sẽ giúp slices chọn đúng bean hơn.

## 7. Nguyên tắc quản lý bean test và mock

### Mockito bình thường, @MockitoBean và @TestConfiguration

| Công cụ | Dùng ở đâu | Tác dụng |
| --- | --- | --- |
| `Mockito.mock(...)` / `@Mock` | Pure unit test | Tạo object mock trong Java/test instance |
| `@MockitoBean` | Test có Spring context, Spring Framework 6.2+ | Thay hoặc cung cấp bean mock trong context theo contract |
| `@TestConfiguration` + `@Import` | Test nhóm cần bean fixture cụ thể | Bổ sung Spring bean chỉ cho nhóm đó |
| `@Primary` | Khi cần ưu tiên một bean trong nhiều candidates | Chọn bean theo injection, không tự thay hoàn toàn mọi bean |
| `@DirtiesContext` | Context bị mutate không thể reset an toàn | Đóng/loại context khỏi cache để nạp lại |

Với Spring Boot 3.4/3.5, `@MockBean` cũ đã deprecated; `@MockitoBean` ở `org.springframework.test.context.bean.override.mockito.MockitoBean` là hướng phù hợp. Boot 4 dùng test starters theo công nghệ và tiếp tục sử dụng `@MockitoBean`. Không đặt mock vào static field dùng chung nhiều nhóm.

### @TestConfiguration cho nhóm cần Clock

Ví dụ **trích đoạn, cần các imports và service thực tế**:

```java
@TestConfiguration(proxyBeanMethods = false)
class FixedClockConfig {
    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2024-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }
}

@UseTestProfile
@SpringBootTest
@Import(FixedClockConfig.class)
class PriceCalculationIntegrationTest {
    // Chỉ test này yêu cầu clock cố định.
}
```

Với top-level `@TestConfiguration`, import tường minh vào nhóm cần nó. Với static nested `@TestConfiguration` trong test Boot, Boot có thể bổ sung nó vào app config. Không nhầm với static nested `@Configuration`, vì Boot có cơ chế phát hiện cấu hình test khác nhau cho hai loại.

## 8. Bài thực hành đầy đủ: bốn nhóm test có chung một profile

Ví dụ dùng **Java 17, Maven, Spring Boot 3.5.0, Spring MVC, JPA, JUnit Jupiter và Mockito**. Mục tiêu là chạy được từ một POM, không cần Docker hoặc database ngoài.

### 8.1. Cấu trúc

```text
test-boundaries-demo/
├── pom.xml
└── src/
    ├── main/java/example/demo/
    │   ├── DemoApplication.java
    │   ├── GreetingService.java
    │   ├── GreetingController.java
    │   ├── CustomerNote.java
    │   └── CustomerNoteRepository.java
    └── test/
        ├── resources/application-test.properties
        └── java/example/demo/
            ├── UseTestProfile.java
            ├── GreetingServiceUnitTest.java
            ├── GreetingControllerTest.java
            ├── CustomerNoteRepositoryTest.java
            └── FullAppIntegrationTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>test-boundaries-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`h2` ở test scope hỗ trợ database nhúng; ứng dụng production thực tế cần driver/data source phù hợp môi trường. Parent Boot quản lý version của các starter/test dependencies. Không khóa JUnit/Mockito vào version khác một cách tùy tiện.

Tệp `src/test/resources/application-test.properties`:

```properties
app.greeting-prefix=Shared
spring.jpa.hibernate.ddl-auto=create-drop
```

Tệp `src/test/java/example/demo/UseTestProfile.java` (tạo riêng, chỉ đặt một lần):

```java
package example.demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.test.context.ActiveProfiles;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ActiveProfiles("test")
@interface UseTestProfile {
}
```

### 8.3. Production classes

`src/main/java/example/demo/DemoApplication.java`:

```java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/example/demo/GreetingService.java`:

```java
package example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final String prefix;

    public GreetingService(
            @Value("${app.greeting-prefix:Hello}") String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is blank");
        }
        return prefix + " " + name.strip();
    }
}
```

Trong đoạn Java được lưu, `@Value("${app.greeting-prefix:Hello}")` dùng cú pháp placeholder của Spring: nếu property được cung cấp nó lấy giá trị đó, nếu thiếu nó dùng `Hello` làm mặc định. Tên `app.greeting-prefix` là ví dụ, không phải property nội tại của Spring Boot.

`src/main/java/example/demo/GreetingController.java`:

```java
package example.demo;

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
    public String greet(@RequestParam String name) {
        return service.greet(name);
    }
}
```

`src/main/java/example/demo/CustomerNote.java`:

```java
package example.demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_note")
public class CustomerNote {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String body;

    protected CustomerNote() {
    }

    public CustomerNote(String body) {
        this.body = body;
    }

    public Long getId() {
        return id;
    }

    public String getBody() {
        return body;
    }
}
```

`src/main/java/example/demo/CustomerNoteRepository.java`:

```java
package example.demo;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerNoteRepository
        extends JpaRepository<CustomerNote, Long> {
}
```

Production classes không biết test group nào đang gọi; những lớp này không được tùy biến để “biến thành mock” trong production profile.

### 8.4. Unit test không tạo Spring context

`src/test/java/example/demo/GreetingServiceUnitTest.java`:

```java
package example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingServiceUnitTest {
    private final GreetingService service =
            new GreetingService("Manual");

    @Test
    void trimsNameWithoutStartingSpringContext() {
        assertEquals("Manual Lan", service.greet("  Lan  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet("   "));
    }
}
```

`@Service` trên production class không ngăn test tạo nó bằng `new`. Test này nhanh và không phụ thuộc `application-test.properties`.

### 8.5. MVC test chỉ nạp web layer, service được mock

`src/test/java/example/demo/GreetingControllerTest.java`:

```java
package example.demo;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@UseTestProfile
@WebMvcTest(GreetingController.class)
class GreetingControllerTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @MockitoBean
    GreetingService service;

    @Test
    void returnsHttpResponseFromMockedService() throws Exception {
        when(service.greet("Lan")).thenReturn("Web Lan");

        mvc.perform(get("/greet").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(content().string("Web Lan"));

        verify(service).greet("Lan");
    }

    @Test
    void loadsWebSliceWithoutJpaRepository() {
        assertTrue(context.getBeansOfType(
                CustomerNoteRepository.class).isEmpty());
        assertTrue(Mockito.mockingDetails(service).isMock());
    }
}
```

Đúng với Boot 3.5, `@WebMvcTest` nằm trong `org.springframework.boot.test.autoconfigure.web.servlet`, còn `@MockitoBean` nằm trong Spring Framework 6.2 `org.springframework.test.context.bean.override.mockito`. Controller có thể kiểm tra request/response, nhưng logic thật của `GreetingService` không được thực thi vì bị mock.

### 8.6. JPA test có database nhưng không có controller

`src/test/java/example/demo/CustomerNoteRepositoryTest.java`:

```java
package example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.ApplicationContext;

@UseTestProfile
@DataJpaTest
class CustomerNoteRepositoryTest {
    @Autowired
    CustomerNoteRepository repository;

    @Autowired
    ApplicationContext context;

    @Test
    void canSaveAndReadEntityInTestTransaction() {
        CustomerNote saved =
                repository.saveAndFlush(new CustomerNote("A"));

        assertNotNull(saved.getId());
        CustomerNote reloaded =
                repository.findById(saved.getId()).orElseThrow();
        assertEquals("A", reloaded.getBody());
    }

    @Test
    void jpaSliceExcludesWebAndServiceBeans() {
        assertTrue(context.getBeansOfType(
                GreetingController.class).isEmpty());
        assertTrue(context.getBeansOfType(
                GreetingService.class).isEmpty());
    }
}
```

`@DataJpaTest` tạo JPA slice, dùng H2 có trong test classpath và thường rollback transaction sau từng test. Không có test nào giả định ID đầu tiên luôn là `1`; identity/sequence có thể thay đổi dù dữ liệu đã rollback. Repository test không cần mock controller hay service.

### 8.7. Full integration override property riêng

`src/test/java/example/demo/FullAppIntegrationTest.java`:

```java
package example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@UseTestProfile
@SpringBootTest
@TestPropertySource(properties =
        "app.greeting-prefix=Integration")
class FullAppIntegrationTest {
    @Autowired
    GreetingService service;

    @Autowired
    CustomerNoteRepository repository;

    @Test
    void groupOverrideIsVisibleInFullContext() {
        assertEquals("Integration Lan", service.greet("Lan"));
        assertNotNull(repository);
    }
}
```

Cả MVC, JPA và full integration đều dùng `@UseTestProfile`; nhưng chỉ full integration override `app.greeting-prefix`, và chỉ full integration tạo full application context. Mặc định `@SpringBootTest` không khởi động embedded HTTP server; test này kiểm tra wiring và bean properties.

### 8.8. Lệnh chạy và kết quả dự kiến

Yêu cầu JDK 17+, Maven, repository có thể tải dependency lần đầu. Từ thư mục có `pom.xml`:

```bash
mvn test
```

Hoặc chạy từng nhóm:

```bash
mvn test -Dtest=GreetingServiceUnitTest
mvn test -Dtest=GreetingControllerTest
mvn test -Dtest=CustomerNoteRepositoryTest
mvn test -Dtest=FullAppIntegrationTest
```

Kết quả mong đợi theo hợp đồng ví dụ: **7 test methods PASS** (unit 2, MVC 2, JPA 2, full integration 1). Source không gọi `System.out.println` nên không có stdout chương trình cố định; Maven/Spring/Hibernate ghi log tùy phiên bản. Nếu có lỗi, mở `target/surefire-reports`. Đây là expected outcome của mã ví dụ, cần thực sự chạy trong môi trường có dependency để xác nhận.

| Test group | Số test | Bằng chứng |
| --- | --- | --- |
| Unit | 2 | Tạo service trực tiếp, kiểm tra logic, không có Spring context |
| MVC | 2 | HTTP response từ mock service, repository không được nạp |
| JPA | 2 | Entity lưu/đọc H2, controller/service không được nạp |
| Full integration | 1 | Service và repository thật được nạp, property override đúng |

Điểm quan trọng là **profile chung vẫn được tái sử dụng**, nhưng các lớp test khai báo riêng boundary phù hợp với mục tiêu.

## 9. Data isolation: Spring context khác không bảo đảm database khác

### Rollback của @DataJpaTest

`@DataJpaTest` thường chạy từng test method trong test-managed transaction và rollback khi test xong. Điều này tốt cho dữ liệu được ghi trong chính transaction đó, nhưng không bảo đảm reset mọi thứ:

- DDL, identity/sequence counters hoặc connection/session state có thể không rollback giống DML.
- External HTTP/file/message side effects không nằm trong JDBC transaction.
- `REQUIRES_NEW` hoặc transaction chạy ở thread khác có thể commit ngoài transaction test.
- Khi `@SpringBootTest(webEnvironment=RANDOM_PORT)` gọi HTTP thật, server xử lý transaction riêng, không được rollback chỉ vì client test có `@Transactional`.

Với integration test cần xác nhận commit hoặc nhiều transaction, thiết kế fixture cleanup rõ ràng, không dựa vào rollback như bằng chứng tuyệt đối.

### Không dùng dữ liệu cố định dễ đụng nhau

- Tránh ID hard-code `1L` khi PK auto-generated.
- Tạo dữ liệu mới cho mỗi test, dọn theo transaction hoặc fixture cleanup.
- Nếu dùng `@Sql` seed script, đặt nó ở group DB cần, không áp dụng global cho MVC/unit.
- Nếu dùng một PostgreSQL container chung cho nhiều test classes, cân nhắc schema/namespace khác nhau hoặc cleanup có kiểm soát.
- Nếu JUnit parallel bật, hai test không được giả định thứ tự ghi/đọc vào một bảng dùng chung.

### File, clock, static state

- Với file, dùng JUnit `@TempDir`; không ghi vào cùng file tên cố định.
- Với thời gian, inject `Clock` và dùng `Clock.fixed(...)` trong nhóm cần deterministic time.
- Tránh static mutable map/cache trong test builders; mỗi test nên nhận object mới.
- `@DirtiesContext` có thể tạo context mới, nhưng **không reset** mọi static field, file hoặc database bên ngoài context.

## 10. Dynamic properties và tài nguyên thật trong integration

Nếu integration test dùng Testcontainers hoặc stub HTTP chạy port ngẫu nhiên, phải truyền giá trị runtime vào Spring:

```java
// Trích đoạn: cần dependency Testcontainers, Docker và lifecycle start container.
static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

`@DynamicPropertySource` thường dùng static method nhận `DynamicPropertyRegistry`, cung cấp `Supplier`. Container phải khởi động đúng lifecycle trước khi thuộc tính được đọc. Nếu dùng Spring Boot 3.1+, `spring-boot-testcontainers` và `@ServiceConnection` có thể cấu hình connection details thay cho nhiều khai báo JDBC thủ công, tùy loại container.

**Cảnh báo cache:** khi cùng một `@DynamicPropertySource` được kế thừa qua base class nhưng mỗi subclass dùng container khác với URL runtime khác, context đã cache có thể giữ connection của resource cũ. Theo hướng dẫn Spring, khi dynamic properties thay đổi giữa subclasses, cân nhắc `@DirtiesContext` hoặc tổ chức resource/context riêng để giá trị đúng. Không bật `@DirtiesContext` cho toàn suite nếu vấn đề chỉ ở một nhóm.

### HTTP stub và message broker

HTTP adapter test cần stub server với port ngẫu nhiên, reset recorded requests/mappings mỗi test. Message integration cần topic/consumer group test có tên phân biệt hoặc cleanup rõ ràng. Không dùng production URL/credential trong source test; CI cung cấp secret nếu test bắt buộc dùng sandbox. Nếu một job bắt buộc có broker mà broker không sẵn sàng, test/job nên báo lỗi; không biến outage thành “skipped” để dashboard xanh.

## 11. Tổ chức pipeline và lựa chọn test suite

Có thể gắn `@Tag("integration")` cho test cần hạ tầng:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("integration")
class RemoteGatewayContractTest {
    @Test
    void verifiesGatewayContract() {
        // Viết assertions với stub hoặc sandbox được chuẩn bị.
    }
}
```

Đây là **trích đoạn**, không chứng minh gateway thật hoạt động. JUnit tag chỉ cung cấp metadata để runner lọc; nó không khởi động database/container hoặc tự cấu hình CI.

| CI job | Suite | Hạ tầng | Cách đánh giá |
| --- | --- | --- | --- |
| PR nhanh | Unit, MVC/slice quan trọng | JDK, không external network | Behavior/validation pass |
| DB test | JPA/repository slice | H2 hoặc Testcontainers phù hợp | Query/schema/transaction pass |
| Integration | Full app, external adapters | Container, stub/sandbox, secrets test | Wiring và contract xuyên tầng pass |
| Smoke | Deployment kiểm soát | Hệ thống test đang chạy | API thực đúng theo SLA |

Maven Surefire hỗ trợ tag filtering thông qua groups/excludedGroups với JUnit Platform, hoặc dùng Maven Failsafe và quy ước `*IT` với lifecycle config phù hợp. **Chỉ đổi tên class không tự làm Failsafe chạy**; phải cấu hình plugin/goals đúng. Gradle có thể lọc `useJUnitPlatform { includeTags(...) }` trong task riêng; nếu đã exclude integration khỏi task mặc định, phải có job khác thực sự chạy nó. Kiểm tra số test được phát hiện và chạy, không chỉ “BUILD SUCCESS”.

### Khả năng chạy độc lập và song song

Chạy một test method, cả test class rồi toàn suite. Nếu chỉ fail khi chạy cùng, kiểm tra static/shared state, DB rows, mock stubbings, fixed port, thread-local và context cache. Nếu fail ngẫu nhiên, ghi lại seed, timeouts và lifecycle resource trước khi tăng retry. Retry CI tự động có thể che flakiness; nhiệm vụ của test suite là cung cấp bằng chứng ổn định, có thể tái hiện.

## 12. Tối ưu Spring TestContext cache đúng cách

Spring TestContext cache `ApplicationContext` theo **merged context configuration**, không theo tên class. Cache key liên quan cấu hình, context loader, profiles, properties, initializers, context customizers (trong đó có mock beans và dynamic property methods) và hierarchy.

- Hai test cùng type và cấu hình có thể tái sử dụng context → tiết kiệm thời gian.
- Một override `@TestPropertySource` hoặc `@MockitoBean` có thể làm cache key khác.
- `@DirtiesContext` đóng/evict context tương ứng và làm test sau phải nạp lại.
- Cache nằm trong process; Maven/Gradle forks khác process không dùng chung static cache.
- Bean singleton có thể tồn tại qua nhiều test classes dùng chung cache, vì vậy phải stateless hoặc được reset theo lifecycle.

**Không đánh đổi isolation để giảm context count.** Nếu hai nhóm có behavior khác nhau, một context riêng là hợp lý; tối ưu có ý nghĩa hơn là tránh override vô tình, tránh quá nhiều `@DirtiesContext` và dùng unit/slice test khi có thể.

Nếu Spring context khởi động lại thường xuyên, bật debug/statistics cho test context cache trong môi trường chẩn đoán, xem classes/profiles/properties thay đổi ở đâu trước khi chỉnh tổ chức suite.

## 13. Những lỗi tổ chức test thường gặp

| Triệu chứng | Vì sao xảy ra | Cách sửa |
| --- | --- | --- |
| `@WebMvcTest` đòi datasource | Import/component scan quá rộng hoặc base class gắn integration bootstrap | Giảm phạm vi app config, dùng web slice thật |
| `@DataJpaTest` nạp controller | Custom scan hoặc @Import kéo thêm web beans | Giữ JPA slice, bỏ cấu hình ngoài mục tiêu |
| Unit test tải toàn bộ Boot context | Dùng base `@SpringBootTest` cho mọi test | Dùng JUnit/Mockito và `new` |
| Một property override đổi nhiều nhóm | Chung base/config quá lớn | Đưa override về group thực sự dùng |
| Context khác nhưng dữ liệu vẫn bị lẫn | Cùng DB/schema/file/broker | Transaction/cleanup hoặc namespace riêng |
| Context bị reload quá nhiều | Dùng `@DirtiesContext` hoặc override vô tội vạ | Xác minh cache keys và lifecycle |
| Test riêng PASS nhưng suite FAIL | Singleton/static/mutable shared fixture, fixed port | Dọn state, test fixture mới, random port |
| Test MVC dùng service thật vô tình gọi network | Không mock collaborator đúng boundary | `@MockitoBean` cho service/adapter và verify |
| `@DataJpaTest` bị lỗi DB URL | Thiếu embedded DB, driver hoặc datasource test | H2/Testcontainers và cấu hình test có chủ đích |
| Full test ở RANDOM_PORT không rollback dữ liệu server | Test và server khác transaction/thread | Cleanup DB hoặc test transaction/commit theo thực tế |
| Test profile không có tác dụng | Thiếu `@ActiveProfiles` hoặc meta annotation không được áp dụng | Assert `Environment.getActiveProfiles()` và property |
| Test CI xanh nhưng không chạy integration | Filter tags/task lifecycle không có integration job | Tạo job riêng và kiểm tra test count |
| Spring Boot 4 thiếu test slice annotation | Module/renamed imports thay đổi | Thêm focused test starter theo công nghệ |

## 14. Khi nâng Spring Boot 3 lên 4

Nguyên tắc giữ ranh giới không đổi, nhưng module test của Spring Boot 4 được chia theo công nghệ. Các ví dụ runnable trong bài nhắm **Boot 3.5.0**:

- Boot 3.5 thường dùng `spring-boot-starter-test` làm nền; `@WebMvcTest` và `@DataJpaTest` nằm ở các package `org.springframework.boot.test.autoconfigure...`.
- Boot 4 có focused test starters, ví dụ `spring-boot-starter-webmvc-test` và `spring-boot-starter-data-jpa-test`. Test annotations của các công nghệ được chuyển package.
- Spring Framework 6.2+/Boot 3.4+ dùng `@MockitoBean`; `@MockBean` cũ đã deprecated và bị loại bỏ ở dòng mới.
- Phải để parent/BOM đồng bộ versions Spring Framework, JUnit, Mockito, H2/Testcontainers; không trộn major versions.

Khi nâng cấp, điều đầu tiên là xác nhận dependency tree/import và số test được runner phát hiện, sau đó mới đánh giá lỗi application behavior. Không đưa tất cả focused starters vào tất cả modules chỉ để làm build pass.

## 15. Checklist thiết kế và nghiệm thu

- [ ] Đã phân nhóm unit/MVC/JPA/full integration/external đúng mục đích?
- [ ] Pure unit test không dùng `@SpringBootTest` chỉ để lấy một bean?
- [ ] Annotation chung chỉ chứa metadata an toàn và không chứa nhiều bootstrap annotations?
- [ ] Test profile được khai báo thống nhất và không chứa production credentials?
- [ ] Các override `@TestPropertySource`/`@Import`/`@MockitoBean` nằm trong nhóm cần chúng?
- [ ] MVC slice không nạp JPA repository hoặc external dependency ngoài ý định?
- [ ] JPA slice dùng DB/transaction phù hợp và không dựa vào state của test khác?
- [ ] Full integration kiểm chứng wiring thật, còn side effect được cleanup khi cần?
- [ ] Không có shared static mutable object, cố định port/file/path gây race?
- [ ] Testcontainers/HTTP stubs có lifecycle và isolation resources rõ ràng?
- [ ] Dynamic properties tương thích với context cache và container lifecycle?
- [ ] `@DirtiesContext` chỉ dùng khi context thực sự bẩn không thể reset?
- [ ] Có job CI thực chạy những tests đã tag integration hoặc tách source set?
- [ ] Các test PASS độc lập và khi chạy toàn suite, kể cả parallel nếu bật?
- [ ] Đã xem số test executed/filtered/skipped, không chỉ build status?

### Mẫu quyết định áp dụng vào dự án khác

| Câu hỏi | Nếu câu trả lời là “có” | Lựa chọn |
| --- | --- | --- |
| Chỉ kiểm tra Java logic? | Không cần Spring bean wiring | Unit JUnit/Mockito |
| Cần HTTP mapping/validation? | Không cần repository thật | MVC slice với mock collaborator |
| Cần query/entity/transaction? | Không cần controller | JPA slice với DB test |
| Cần Boot auto-config và nhiều tầng? | Chấp nhận startup cost | `@SpringBootTest` |
| Cần remote/broker behavior? | Có I/O thật hoặc stub contract | Integration test + resource lifecycle |
| Chỉ cần thống nhất profile? | Các group bootstrap khác nhau | Composed `@ActiveProfiles` nhỏ |
| Cần khác bean/property cho một nhóm? | Không phù hợp làm global default | `@Import`/`@TestPropertySource` riêng group |

## 16. Tài liệu chính thức

1. [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): full-context, slices, configuration discovery, `@TestConfiguration` và test cache.
2. [Spring Boot 3.5 – Test Auto-configuration Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): thành phần từng test slice.
3. [Spring Framework – Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): merged context key, cache và `@DirtiesContext`.
4. [Spring Framework – Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): precedence và kế thừa `@TestPropertySource`.
5. [Spring Framework – Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource`, Testcontainers và vấn đề cache.
6. [Spring Framework – Active Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html): `@ActiveProfiles` và inheritProfiles.
7. [Spring Framework – Meta-Annotation Support](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-meta.html): composed annotations cho test.
8. [Spring Boot 3.5 – Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): service connections và resource lifecycle.
9. [JUnit Jupiter – Tags and Filtering](https://docs.junit.org/5.13.4/writing-tests/tagging-and-filtering.html): phân nhóm test và lựa chọn suite.
10. [Spring Boot Reference – Testing](https://docs.spring.io/spring-boot/reference/testing/): đối chiếu hệ module khi dùng Boot 4.

**Điểm cần nhớ:** dùng chung **cấu hình bất biến và quy ước**, để từng test group tự chọn **Spring bootstrap và boundary**, và chủ động cô lập **state/tác dụng phụ**. Cấu hình chung tốt giúp test không bị trùng lặp; ranh giới tốt giúp test không ảnh hưởng nhau.

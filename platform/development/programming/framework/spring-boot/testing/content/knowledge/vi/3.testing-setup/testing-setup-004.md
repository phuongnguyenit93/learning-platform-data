# Starter kiểm thử chung và module theo công nghệ trong các dòng Spring Boot

## 1. Phạm vi và ý tưởng cốt lõi

Khi thiết lập kiểm thử cho Spring Boot, trước tiên phải xác định **dòng phiên bản của dự án** (ví dụ 2.7.x, 3.5.x hoặc 4.x), sau đó xác định **công nghệ đang được kiểm thử** (MVC, WebFlux, JPA, Security, Kafka, GraphQL...). Tên dependency và nơi đặt các annotation test thay đổi đáng kể khi chuyển từ Spring Boot 3 sang Spring Boot 4.

Ba khái niệm cần phân biệt:

- **Starter kiểm thử chung** (`org.springframework.boot:spring-boot-starter-test`): dependency tiện dụng kéo vào các công cụ kiểm thử phổ biến và các module hỗ trợ kiểm thử cốt lõi của Spring Boot. Khai báo trong **test scope**, không đưa vào ứng dụng production.
- **Module test** (chẳng hạn `spring-boot-test`, `spring-boot-test-autoconfigure` hoặc `spring-boot-webmvc-test`): JAR chứa API/annotation/hỗ trợ tự cấu hình kiểm thử. Module trực tiếp thường hẹp hơn starter và không nhất thiết tự kéo tất cả công cụ bên ngoài.
- **Starter kiểm thử theo công nghệ** (chẳng hạn `spring-boot-starter-webmvc-test`, `spring-boot-starter-data-jpa-test`): tập dependency đã được Spring Boot 4 đóng gói cho một nhóm công nghệ, bao gồm các module/hạ tầng test cần thiết. Các starter theo công nghệ của Boot 4 kéo `spring-boot-starter-test` qua phụ thuộc bắc cầu.

Ví dụ: `@WebMvcTest` cần hạ tầng Spring MVC test, còn `@DataJpaTest` cần hạ tầng JPA test. Có JUnit Jupiter trong classpath **không tự động** đồng nghĩa mọi test slice đều sẵn sàng. Ngược lại, có Spring MVC production starter không thay thế được dependency cho những công cụ test chuyên biệt.

### Bức tranh theo dòng phiên bản

| Dòng Spring Boot | Starter chung | Tổ chức tính năng test | Cách thêm test chuyên biệt |
| --- | --- | --- | --- |
| **2.7.x (legacy)** | `spring-boot-starter-test` | `spring-boot-test` + `spring-boot-test-autoconfigure` cung cấp tiện ích và nhiều slice test phổ biến | Thêm thư viện của công nghệ khi cần, ví dụ `spring-security-test`, `spring-kafka-test`; giữ cùng dòng phiên bản |
| **3.x (ví dụ 3.5.x)** | `spring-boot-starter-test` | Hai module chung trên vẫn cung cấp phần lớn Spring Boot test annotations; dùng JUnit Jupiter và Spring Framework 6 | Nhiều test slice có sẵn trong starter chung; thêm thư viện test cho Security, GraphQL, Kafka, Testcontainers... tùy nhu cầu |
| **4.x (ví dụ 4.0/4.1)** | `spring-boot-starter-test` vẫn tồn tại | Hai module test chung **cộng thêm các module theo công nghệ** `spring-boot-<technology>-test`; dùng Spring Framework 7 | Ưu tiên `spring-boot-starter-<technology>-test` cho mỗi công nghệ thực sự kiểm thử, ví dụ MVC, Data JPA, Security; starter công nghệ kéo starter chung |

**Không thể lấy ví dụ cấu hình của Boot 3 rồi chỉ thay số version thành Boot 4.** Bản 4 có thiết kế module mới, một số artifact được đổi tên và nhiều annotation đổi package. Không tự suy diễn rằng mọi dependency `-test` của Boot 4 tồn tại trong Boot 2 hoặc 3.

Dự án Spring Boot 2.x có Java baseline khác Spring Boot 3/4: Boot 3 và 4 yêu cầu Java **17 trở lên**; source Java 17 trong các ví dụ bên dưới vì vậy nhắm vào Boot 3/4. Với dự án Boot 2.7 chạy Java cũ hơn, cần điều chỉnh ngôn ngữ và thư viện phù hợp.

## 2. Starter test chung chứa gì, và không làm gì?

`spring-boot-starter-test` quản lý một bộ công cụ quen thuộc:

| Thành phần | Nhiệm vụ | Cách dùng thường gặp |
| --- | --- | --- |
| JUnit Jupiter | Viết và chạy test, assertions, lifecycle, parameterized tests | `@Test`, `@BeforeEach`, `@ParameterizedTest` |
| Spring Test | Test `ApplicationContext`, tích hợp TestContext Framework, MockMvc ở tầng Spring Framework khi được cấu hình phù hợp | `@SpringBootTest`, `MockMvc` |
| Mockito | Mock dependency và kiểm tra tương tác | `mock`, `when`, `verify`, `@MockitoBean` khi Spring Framework hỗ trợ |
| AssertJ | Assertion dễ đọc cho object, collection, exception | `assertThat(actual).isEqualTo(expected)` |
| Hamcrest | Matcher hỗ trợ assertion | `assertThat(value, is(...))` |
| `spring-boot-test` | Các tiện ích và hỗ trợ Spring Boot test cốt lõi | `@SpringBootTest` |
| `spring-boot-test-autoconfigure` | Cấu hình hỗ trợ test chung; Boot 4 chia thêm nhiều phần theo công nghệ | Hỗ trợ cấu hình test tự động tùy bộ starter |

Đây là bức tranh khái quát; **tập dependency chính xác phải kiểm chứng theo version**. Chẳng hạn Spring Boot 3.5 dùng hệ JUnit 5, còn tài liệu Spring Boot 4 mô tả hệ JUnit 6; các test viết bằng API Jupiter thường giữ import `org.junit.jupiter.api.Test`, nhưng plugin và phiên bản Java phải tương thích. Không tự thêm `junit-jupiter`/`mockito-core` với số phiên bản rời rạc nếu BOM/parent đã quản lý.

Starter test chung **không** tự tạo database hoặc Docker container, **không** mặc định cung cấp credential cho hệ thống ngoài, **không** thay test contract nghiệp vụ, và trong Boot 4 **không** mang mọi slice test của mọi công nghệ. Thêm dependency đúng là bước đầu, tiếp theo vẫn cần chọn loại test và cấu hình phù hợp.

### Dependency và classpath vận hành

- Maven: `<scope>test</scope>` khiến dependency chỉ tham gia biên dịch/chạy test.
- Gradle: `testImplementation(...)` cho compile/runtime test; `testRuntimeOnly(...)` cho thư viện chỉ cần khi chạy test.
- Production dependencies (ví dụ `spring-boot-starter-webmvc`, `spring-boot-starter-data-jpa`) thường dùng phạm vi compile/runtime của ứng dụng; **không dùng chúng thay thế** test starter.
- Spring Boot Maven parent/BOM hoặc Gradle dependency management giúp các phiên bản phối hợp đúng. Không gắn version riêng cho starter do Boot quản lý khi không có lý do kỹ thuật đã được kiểm chứng.
- Dòng 2.x/3.x/4.x nên được đồng bộ giữa BOM, starter, Spring Framework và dependency bổ sung. Trộn `spring-boot-starter-test` Boot 4 vào ứng dụng Boot 3 có thể gây `NoClassDefFoundError` hoặc xung đột Spring Framework.

## 3. Chọn module theo công nghệ: đối chiếu Boot 3.x với Boot 4.x

Bảng sau dùng **Spring Boot 3.5.x** làm mẫu của cách đóng gói trước phiên bản 4 và **Spring Boot 4.x** làm mẫu của cách đóng gói module mới. Với 2.7.x, phần lớn tình huống bắt đầu từ starter chung và thư viện test chuyên dụng nhưng phải đối chiếu tương thích phiên bản.

| Công nghệ cần kiểm thử | Boot 3.5: dependency test thường dùng | Boot 4.x: starter test phù hợp | API/test slice cần tìm |
| --- | --- | --- | --- |
| Logic Java hoặc context Spring Boot chung | `spring-boot-starter-test` | `spring-boot-starter-test` | JUnit, Mockito, `@SpringBootTest` |
| Servlet Spring MVC | `spring-boot-starter-test`; ứng dụng có MVC dependency | `spring-boot-starter-webmvc-test` | `@WebMvcTest`, `MockMvc`, `@AutoConfigureMockMvc` |
| WebFlux/reactive controller | `spring-boot-starter-test` + các thư viện Reactor test cần thiết | `spring-boot-starter-webflux-test`; bổ sung Reactor test khi cần | `@WebFluxTest`, `WebTestClient`, `StepVerifier` |
| Spring Data JPA | `spring-boot-starter-test` + JPA production starter + DB test | `spring-boot-starter-data-jpa-test` + DB test nếu cần | `@DataJpaTest`, repository và entity |
| Spring Data JDBC | `spring-boot-starter-test` + Data JDBC dependency | `spring-boot-starter-data-jdbc-test` | `@DataJdbcTest` |
| JDBC thuần | `spring-boot-starter-test` + JDBC dependency | `spring-boot-starter-jdbc-test` | `@JdbcTest` |
| MongoDB | `spring-boot-starter-test` + MongoDB dependency | `spring-boot-starter-data-mongodb-test`; có biến thể reactive | `@DataMongoTest` |
| REST client đồng bộ (`RestClient`/`RestTemplate`) | `spring-boot-starter-test` + HTTP client production | `spring-boot-starter-restclient-test` | `@RestClientTest`, mock server |
| Spring Security | `spring-boot-starter-test` + `org.springframework.security:spring-security-test` | `spring-boot-starter-security-test` | `@WithMockUser`, security assertions |
| Spring GraphQL | `spring-boot-starter-test` + `org.springframework.graphql:spring-graphql-test` | `spring-boot-starter-graphql-test` | `@GraphQlTest`, `GraphQlTester` |
| Spring Kafka | `spring-boot-starter-test` + `org.springframework.kafka:spring-kafka-test` | `spring-boot-starter-kafka-test` | Embedded Kafka/test support theo version |
| Spring AMQP / RabbitMQ | `spring-boot-starter-test` + test library phù hợp | `spring-boot-starter-amqp-test` | Test message listener, integration với broker |
| Validation | `spring-boot-starter-test` + Bean Validation khi ứng dụng dùng | `spring-boot-starter-validation-test` | `jakarta.validation.Validator` trong Boot 3/4 |

**Lưu ý về import:** tên annotation giống nhau không có nghĩa là package giống nhau. Ví dụ trong Boot 3.5, `@WebMvcTest` nằm ở `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest`; trong Boot 4, nó nằm ở `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest`. `@DataJpaTest` chuyển từ `org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest` sang `org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest`. Sau khi đổi starter, IDE có thể vẫn báo thiếu annotation nếu giữ import cũ.

**Lưu ý về tên artifact:** không suy ra một tên theo công thức chung mà không kiểm tra danh mục chính thức. Ví dụ thực tế Boot 4 dùng `spring-boot-starter-data-jpa-test`, nhưng tên module chứa annotation là `spring-boot-data-jpa-test`; starter và module là hai artifact khác nhau. Dùng **starter** trong phần lớn ứng dụng để nhận dependency đầy đủ; chỉ dùng module trực tiếp khi chủ động kiểm soát classpath và đã biết phần phải tự thêm.

### Tại sao Boot 4 ưu tiên starter theo công nghệ?

Ở Boot 3, chỉ cần starter chung thường đã có annotation nhiều slice test, nên classpath lớn và dễ vô tình dùng cấu hình test không liên quan. Ở Boot 4, cơ chế modularization chuyển hạ tầng vào module theo công nghệ để mỗi feature chỉ tham gia khi dependency tương ứng có mặt.

Ví dụ ứng dụng chỉ kiểm thử MVC trong Boot 4:

- Cần `spring-boot-starter-webmvc` để chạy web MVC của ứng dụng.
- Cần `spring-boot-starter-webmvc-test` trong test scope để nhận hỗ trợ test MVC. Starter này mang starter test chung transitively, nên **không bắt buộc** khai báo `spring-boot-starter-test` riêng.
- Nếu thêm test JPA ở cùng module, cần thêm `spring-boot-starter-data-jpa-test`, không hy vọng MVC test starter tự mang JPA test.
- Nếu chỉ là pure Java unit test không mở Spring context, có thể dùng `spring-boot-starter-test` mà không cần starter test theo công nghệ.

Một ứng dụng **dùng công nghệ nào** và một module **kiểm thử công nghệ nào** là hai thông tin liên quan nhưng khác nhau: không nhất thiết phải thêm mọi starter test tương ứng với mọi starter production nếu không có bài test sử dụng hạ tầng đó.

## 4. Cấu hình Maven cho các dòng phổ biến

Các đoạn XML dưới đây là **phần khai báo trong `<dependencies>` của dự án đã có Spring Boot parent/BOM hợp lệ**, không phải một `pom.xml` hoàn chỉnh.

### 4.1. Spring Boot 3.5.x: starter chung làm nền

```xml
<dependencies>
    <!-- JUnit Jupiter, Mockito, AssertJ, Spring Boot test utilities -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Chỉ thêm khi thực sự kiểm thử Spring Security -->
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Chỉ thêm khi kiểm thử Spring GraphQL -->
    <dependency>
        <groupId>org.springframework.graphql</groupId>
        <artifactId>spring-graphql-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Ví dụ trên không tự tạo MVC/JPA trong ứng dụng. Để chạy `@DataJpaTest`, ứng dụng còn cần phụ thuộc JPA và datasource, có thể dùng `com.h2database:h2` ở test scope hoặc cấu hình database test khác. Với `@WebMvcTest`, ứng dụng cần Spring MVC. Với `spring-graphql-test`, ứng dụng cần các thành phần GraphQL thích hợp.

Trong Boot 2.7, hình thức khai báo starter chung tương tự nhưng phải theo BOM và import `javax`/`jakarta` phù hợp từng phiên bản; không đưa annotation API dành riêng Boot 3.4+ vào dự án Boot 2.x.

### 4.2. Spring Boot 4.x: ghép theo công nghệ thực sự kiểm thử

Ví dụ module **có test MVC, JPA và Security**:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Mỗi starter `-test` theo công nghệ của Boot 4 đã mang starter chung transitively; khai báo thêm starter chung là hợp lệ nếu muốn làm rõ ý định nhưng thường dư. `h2` ở đây là database test ví dụ, **không bắt buộc** nếu thử với database khác. Ứng dụng vẫn cần các starter production phù hợp và thực thể/repository/controller thật. Nếu chỉ muốn MVC, bỏ JPA, Security, H2 khỏi ví dụ.

### 4.3. Spring Boot 4: starter classic dùng cho chuyển đổi tạm thời

Spring Boot 4 cung cấp `spring-boot-starter-test-classic` như bước đệm khi nâng từ Boot 3 để có bố cục hạ tầng test tương tự trước đây. Đây là lựa chọn phục vụ **migration**, không nên dùng như giải pháp vĩnh viễn thay việc chọn các starter test đúng công nghệ. Sử dụng nó vẫn phải rà soát các thư viện bên thứ ba, classpath và import đã đổi; đừng mặc định mọi dependency cũ đều được giữ nguyên.

## 5. Cấu hình Gradle Kotlin DSL tương đương

Phần dưới nằm trong `build.gradle.kts` của dự án đang dùng Spring Boot Gradle plugin với dependency management thích hợp.

### Boot 3.5.x, ứng dụng chỉ cần starter chung

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
```

Nếu dùng `@WithMockUser`, thêm:

```kotlin
dependencies {
    testImplementation("org.springframework.security:spring-security-test")
}
```

### Boot 4.x, ứng dụng có MVC và Data JPA tests

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
    testImplementation("org.springframework.boot:spring-boot-starter-data-jpa-test")
    testRuntimeOnly("com.h2database:h2")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
```

`useJUnitPlatform()` làm Gradle chạy qua JUnit Platform; `testImplementation` không đồng nghĩa tự bật test task. Nếu build đã có cấu hình này do template tạo ra, không cần định nghĩa lặp. Maven dùng Surefire/JUnit Platform theo cấu hình build; không cần tự khóa phiên bản Surefire trái với quản lý của dự án nếu không có yêu cầu đặc biệt.

### Java version

- Boot 3.x và 4.x: Java 17+.
- Boot 2.7.x: có thể chạy ở Java cũ hơn; không sao chép cú pháp Java 17 (như `record`) vào dự án dùng compiler cũ.
- Dùng `java -version`, `mvn -v` hoặc `./gradlew -version` để chắc build đang dùng JDK phù hợp. Version của source/target/toolchain cũng phải khớp.

## 6. Một ví dụ unit test chạy được với starter chung

Ví dụ này không phụ thuộc Spring context; mục tiêu là chứng minh khi thêm starter chung, JUnit Jupiter đủ để chạy pure Java test. Sử dụng **Java 17**, tương thích Boot 3.x và 4.x sau khi cấu hình build ở mục 4 hoặc 5.

Tệp `src/main/java/example/GreetingService.java`:

```java
package example;

public final class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

Tệp `src/test/java/example/GreetingServiceTest.java`:

```java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void greetsUsingTrimmedName() {
        assertEquals("Xin chào, Lan!", service.greet("  Lan  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet("  "));
    }
}
```

Lệnh chạy từ thư mục chứa build:

```bash
mvn test -Dtest=GreetingServiceTest
```

Hoặc Gradle trên Linux/macOS:

```bash
./gradlew test --tests 'example.GreetingServiceTest'
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.GreetingServiceTest"
```

**Expected:** hai test đều PASS; bản thân code không in dòng `System.out.println` nào, vì vậy không có stdout chương trình cố định để đối chiếu. Maven/Gradle sẽ in log chạy test tùy cấu hình. Không cần `@SpringBootTest` hay `@ExtendWith(SpringExtension.class)` cho ví dụ này. Nếu chạy được, nó xác minh JUnit trong test classpath, chưa chứng minh MVC/JPA/Security test slice đã được cấu hình.

## 7. Ví dụ annotation và import thay đổi khi nâng lên Boot 4

### @WebMvcTest

Boot 3.5:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
```

Boot 4.x:

```java
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
```

Boot 3.5 sử dụng hạ tầng test trong starter chung; Boot 4 thêm `spring-boot-starter-webmvc-test` vào test scope. Cả hai sử dụng `@WebMvcTest(MyController.class)` để load web slice giới hạn và thường auto-configure `MockMvc`. Những dependency mà controller cần, như service, phải được cung cấp bằng test mock hoặc `@Import` cấu hình phù hợp.

### @DataJpaTest

Boot 3.5:

```java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
```

Boot 4.x:

```java
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
```

Boot 4 thêm `spring-boot-starter-data-jpa-test`. Khi test JPA phải có database driver hoặc datasource test phù hợp; chỉ thêm annotation không tự cung cấp một cơ sở dữ liệu thực. Với embedded database có trên classpath, `@DataJpaTest` thường tự cấu hình nó và test transaction thường được rollback sau mỗi test; kiểm tra chính sách datasource/transaction thực tế trước khi viết assertion.

### Mock bean trong Spring context

- Boot 2.7 / Boot 3.3 trở về trước: thường dùng `org.springframework.boot.test.mock.mockito.MockBean`.
- Boot 3.4/3.5: `@MockBean` của Boot đã bị deprecated; ưu tiên `org.springframework.test.context.bean.override.mockito.MockitoBean` (Spring Framework 6.2+).
- Boot 4.x: dùng `@MockitoBean`; không giữ lại import Boot `@MockBean` đã bị loại bỏ.

`@MockitoBean` dùng khi mock **Spring bean trong ApplicationContext**; còn `@Mock` của Mockito chỉ tạo mock thông thường, có thể kết hợp `@InjectMocks` cho unit test không Spring. Đừng tự thay thế cả hai bằng nhau: `@Mock` không tự đăng ký mock vào Spring context.

### @SpringBootTest, MockMvc và HTTP client test

`@SpringBootTest` tập trung tạo Spring application context; nó không có nghĩa mọi MVC client bean đã sẵn sàng. Đối với bài test full context cần `MockMvc`, kết hợp `@SpringBootTest` với `@AutoConfigureMockMvc` và dependency MVC test đúng phiên bản. Trong Boot 4, import `@AutoConfigureMockMvc` theo package module MVC mới:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderApiIntegrationTest {
    // Inject MockMvc và viết test trong dự án thật.
}
```

Đoạn trên **là minh họa annotation**, chưa phải class test có test method độc lập. Boot 3.5 import `AutoConfigureMockMvc` từ `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`. Khi dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và client HTTP thực, phải chọn và cấu hình client tương ứng; Boot 4 không mặc nhiên tạo `TestRestTemplate` hoặc `WebClient` theo cách các ví dụ cũ có thể kỳ vọng. Theo hướng dẫn migration, có `@AutoConfigureTestRestTemplate` hoặc `@AutoConfigureRestTestClient` cùng module cần thiết; kiểm tra chính xác dependency và import từ phiên bản đang dùng.

## 8. Chọn dependency từ loại test, không từ tên class một cách máy móc

| Câu hỏi kiểm thử | Lựa chọn đầu tiên | Cần lưu ý |
| --- | --- | --- |
| “Hàm tính tiền trả đúng số không?” | Unit test JUnit/Mockito với starter chung | Không mở Spring context |
| “Controller trả HTTP 400/201 đúng không?” | `@WebMvcTest` + MockMvc, MVC test starter cho Boot 4 | Mock service; kiểm tra serialization và validation |
| “Repository có lưu và query entity đúng không?” | `@DataJpaTest` + DB test | Xác nhận transaction, schema và datasource |
| “WebFlux endpoint có phát signal đúng không?” | `@WebFluxTest` + WebTestClient; Reactor test nếu dùng StepVerifier | Phân biệt reactive với servlet web stack |
| “Quyền ADMIN có được cấp đúng không?” | Security test support với `@WithMockUser` | Test filter chain, URL permission và CSRF nếu áp dụng |
| “GraphQL resolver/map lỗi đúng không?” | GraphQL test support | Có schema/resolver thực, mock các collaborator |
| “Consumer Kafka xử lý message đúng không?” | Kafka test support hoặc broker Testcontainers | Không dùng mock thuần để khẳng định broker integration |
| “App boot cùng database thật được không?” | `@SpringBootTest` + driver + Testcontainers | Cần Docker hoặc backend test chạy được |

**Test slice khác full integration test.** Slice như `@WebMvcTest`, `@DataJpaTest` chỉ nạp tập hẹp thành phần phục vụ tầng tương ứng. Nếu một test cần nhiều tầng đồng thời, cân nhắc `@SpringBootTest` cùng công cụ client/DB test; cố gộp nhiều annotation slice vào một class thường không được hỗ trợ. Chọn cấp độ test theo khẳng định cần chứng minh, không theo tiêu chí “annotation nào dễ chạy”.

## 9. Công nghệ có dependency test bổ sung

### Security

Trong Boot 3.5, `@WithMockUser` đến từ thư viện `org.springframework.security:spring-security-test`; starter chung không mặc nhiên thay thế nó. Trong Boot 4, dùng `spring-boot-starter-security-test` để nhận hạ tầng đã tích hợp; chỉ giữ dependency cũ trực tiếp nếu đã hiểu đầy đủ transitive/configuration tương thích.

Ví dụ minh họa:

```java
import org.springframework.security.test.context.support.WithMockUser;

@WithMockUser(roles = "ADMIN")
```

Đây là annotation dùng lên class/test method, không phải test độc lập. Nó tạo security context giả lập cho tình huống cần thiết, **không** thay test xác thực thật qua OAuth2/JWT khi yêu cầu là xác minh toàn chuỗi bảo mật.

### GraphQL, Kafka và messaging

- Spring Boot 3.x: thêm `spring-graphql-test` khi dùng `GraphQlTester`, `spring-kafka-test` khi cần embedded broker/test utility của Kafka, cùng với starter chung.
- Spring Boot 4.x: dùng `spring-boot-starter-graphql-test` và `spring-boot-starter-kafka-test`; cần thiết thì chọn `spring-boot-starter-amqp-test` hoặc các starter chuyên biệt cho messaging khác.
- Kiểm thử message trên broker thật, consumer rebalancing, offset, retry và dead-letter không được xác nhận đầy đủ chỉ bằng test mock service; test integration thích hợp phải có broker hoặc môi trường tương đương.

### Testcontainers và database thật

Testcontainers là lựa chọn riêng cho integration test và **không tự động được khởi chạy** chỉ vì thêm starter chung. Trong Spring Boot 3.1+ có module `spring-boot-testcontainers` giúp tích hợp `@ServiceConnection`; cùng lúc vẫn cần các thư viện `org.testcontainers` tương ứng và Docker/container runtime thực sự khả dụng. Dự án Boot 2.7 có thể dùng Testcontainers với `@DynamicPropertySource` hoặc cấu hình thủ công, nhưng không dùng `@ServiceConnection` như tính năng có sẵn của Boot 2.7.

Đối với Boot 4, kiểm tra tài liệu Testcontainers và dependency mang `@ServiceConnection` đúng dòng 4.x; đừng giả định test starter theo công nghệ tự mang tất cả driver hoặc module container. Ví dụ dữ liệu PostgreSQL thật cần driver và Testcontainers cho PostgreSQL, không thể thay thế hoàn toàn bằng H2 nếu muốn kiểm tra hành vi SQL đặc thù PostgreSQL.

### JUnit Vintage

JUnit Jupiter là nền tảng chính. Nếu dự án còn `org.junit.Test` từ JUnit 4, cần cấu hình **Vintage Engine** phù hợp hệ JUnit được Spring Boot quản lý; không trộn trực tiếp một `junit-vintage-engine` bất kỳ với JUnit Jupiter khác major version. Chuyển dần sang `org.junit.jupiter.api.Test` giúp giảm gánh nặng tương thích. Kiểm tra phiên bản engine theo BOM trước khi bật.

## 10. Cách kiểm tra dependency thực tế sau khi cấu hình

Tên dependency đúng trên giấy chưa đủ: cần xem dependency tree và chạy một test tối thiểu.

Maven:

```bash
mvn dependency:tree -Dscope=test
mvn test -Dtest=GreetingServiceTest
```

Gradle:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew test --tests 'example.GreetingServiceTest'
```

Kiểm tra:

1. Starter/module test cùng dòng Boot với parent/BOM. Không tự kéo Spring Framework 6 vào Boot 4 (Framework 7) hay ngược lại.
2. Test dependency xuất hiện ở **test classpath**. Nếu IDE báo annotation không tồn tại, đối chiếu import và artifact; trong Boot 4, thiếu focused starter là lỗi phổ biến.
3. JUnit Platform được task test chạy; những test Jupiter xuất hiện trong báo cáo, không phải “BUILD SUCCESS” với **0 tests**.
4. Test slice nạp đúng bean cần kiểm thử; tránh vô tình nạp toàn context cho unit/slice test.
5. Với JPA, database/driver và schema đúng, test không vô tình chạm database production.
6. Với Security/GraphQL/Kafka, thư viện test chuyên biệt có mặt và áp dụng đúng cấu hình.
7. Với integration Testcontainers, container runtime khả dụng ở local/CI, lifecycle không gây test flaky.

Khi sửa dependency, chạy lại dependency tree trước khi nâng cấp import hàng loạt; một lỗi “package does not exist” có thể do **thiếu starter**, **sai import sau migration**, **sai scope**, hoặc **classpath chưa được IDE refresh**.

## 11. Lỗi thường gặp theo phiên bản và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| Boot 4 báo `WebMvcTest cannot be resolved` | Chỉ có starter test chung hoặc giữ import Boot 3 | Thêm `spring-boot-starter-webmvc-test` test scope; đổi import sang `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest` |
| Boot 4 báo `DataJpaTest cannot be resolved` | Thiếu `spring-boot-starter-data-jpa-test` hoặc giữ import Boot 3 | Thêm starter test theo công nghệ; đổi import sang package `org.springframework.boot.data.jpa.test.autoconfigure` |
| `@MockBean` không biên dịch sau khi nâng lên Boot 4 | API Boot cũ đã bị loại bỏ | Đổi sang `@MockitoBean`; xem lại cách mock bean trong context |
| `@WithMockUser` không có hoặc hành vi khác dự kiến | Thiếu Security test support đúng phiên bản | Boot 3 thêm `spring-security-test`; Boot 4 ưu tiên `spring-boot-starter-security-test` |
| `No qualifying bean` trong `@WebMvcTest` | Slice không nạp service collaborator | Mock bean bằng annotation phù hợp hoặc `@Import` bean test thật cần thiết |
| `NoSuchMethodError`/`NoClassDefFoundError` | Dependency từ nhiều Boot/Spring Framework major versions | Kiểm tra tree và BOM, loại version override không cần thiết |
| Test unit chạy nhưng `@DataJpaTest` lỗi datasource | Thiếu driver/embedded DB, sai URL, cần backend thật | Thêm DB test/driver, cấu hình datasource test hoặc Testcontainers |
| Thấy lỗi Docker khi chạy test | Testcontainers cần container runtime hoạt động | Xác minh Docker, image, quyền và cấu hình CI; không quy lỗi cho JUnit |
| Gradle build thành công nhưng không chạy JUnit Jupiter tests | Test task thiếu JUnit Platform hoặc filter sai | Thêm `useJUnitPlatform()`, xem báo cáo test và `--tests` |
| Sau đổi Boot 4, test full context không inject được MockMvc | Thiếu MVC test module hoặc auto-configure | Dùng `spring-boot-starter-webmvc-test` và `@AutoConfigureMockMvc` khi cần |
| Dự án test quá chậm | Mỗi test đều khởi động full `ApplicationContext` | Chuyển logic thuần về unit test; dùng test slice cho từng tầng, chỉ full context khi cần |
| Dùng `spring-boot-starter-test-classic` mãi | Giữ bố cục classpath tương thích tạm thời mà không hoàn tất migration | Chuyển từng phần sang focused starters; xóa dependency thừa sau khi xác minh test |

Không sửa lỗi biên dịch bằng cách thêm ngẫu nhiên hàng loạt starter test của Boot 4; cách đó làm mất lợi ích modularization, tăng nguy cơ ambiguity và khó hiểu dependency tree. Hãy bắt đầu từ annotation hoặc tính năng cần test.

## 12. Quy trình lựa chọn đúng cho một dự án thật

**Bước 1 — Xác định dòng Boot.** Mở `pom.xml` / `build.gradle(.kts)`, đọc version từ parent, plugin hoặc BOM. Nếu là dự án nhiều module, phải xác minh dependency management của **module chứa test**, không chỉ version ở repository root.

**Bước 2 — Liệt kê test thực tế.** Tách pure Java unit, Spring context integration, MVC/WebFlux, JPA/JDBC/Mongo, Security, GraphQL, messaging, Testcontainers. Việc có starter production chưa đủ để kết luận đã có nhu cầu test chuyên biệt.

**Bước 3 — Chọn đúng starter.** Ở Boot 2.7/3.x, bắt đầu từ `spring-boot-starter-test` và thêm thư viện test chuyên biệt cần thiết. Ở Boot 4, thêm `spring-boot-starter-<technology>-test` theo công nghệ thực sự test; starter chung được mang transitively. Với pure unit test, starter chung vẫn phù hợp.

**Bước 4 — Kiểm tra imports.** Khi đổi từ 3 sang 4, tìm các import cũ ở `org.springframework.boot.test.autoconfigure...`; đối chiếu annotation từng module. Chuyển `@MockBean` sang `@MockitoBean` khi áp dụng, cập nhật test HTTP client phù hợp.

**Bước 5 — Khóa phạm vi dependency và kiểm tra tree.** Maven `test` hoặc Gradle `testImplementation`/`testRuntimeOnly`. Để BOM quản lý phiên bản. Giữ database test và kết nối tới bên ngoài cách biệt với production.

**Bước 6 — Chạy theo tầng.** Chạy test đơn vị tối thiểu để xác nhận JUnit; test slice để xác nhận starter theo công nghệ; integration test để xác nhận cấu hình, database và hạ tầng ngoài. Quan sát test count và báo cáo, không chỉ trạng thái build.

### Checklist nghiệm thu

- [ ] Đã biết dòng Spring Boot đang sử dụng và Java/toolchain tương thích.
- [ ] Dependency test chung đúng version và đúng test scope.
- [ ] Nếu dùng Boot 4, các focused test starter đúng với công nghệ kiểm thử.
- [ ] Không trộn imports Boot 3 và Boot 4.
- [ ] `@MockitoBean`/`@MockBean` dùng theo đúng phiên bản.
- [ ] JUnit Platform thực sự chạy các test và báo đúng số lượng.
- [ ] Database, Security, GraphQL, Kafka, Testcontainers chỉ được cấu hình khi bài test yêu cầu.
- [ ] Dependency tree không có override không tương thích.
- [ ] Test unit, slice và integration chạy PASS độc lập, không phụ thuộc dịch vụ production.

## 13. Tài liệu chính thức để đối chiếu khi nâng cấp

Các link sau nên mở theo **đúng phiên bản dự án** vì danh mục starter/module và package annotation có thể thay đổi giữa các bản:

1. [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/index.html) và [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).
2. [Spring Boot 4.x — Testing](https://docs.spring.io/spring-boot/reference/testing/) và [Test Modules](https://docs.spring.io/spring-boot/reference/testing/test-modules.html).
3. [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): tên module, starter test theo công nghệ, classic migration starter và package migration.
4. [Spring Boot — Build Systems, starter catalog](https://docs.spring.io/spring-boot/reference/using/build-systems.html).
5. [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html) nếu dự án dùng database hoặc broker trong container.

**Nguyên tắc giữ lâu dài:** starter test chung cung cấp nền kiểm thử; test hạ tầng theo công nghệ phải được chọn theo **Spring Boot line** và **loại test thực tế**. Khi nâng cấp Boot, so lại cả tên artifact, API/import, runtime JUnit và cấu hình Maven/Gradle trước khi đánh giá lỗi test là lỗi nghiệp vụ.

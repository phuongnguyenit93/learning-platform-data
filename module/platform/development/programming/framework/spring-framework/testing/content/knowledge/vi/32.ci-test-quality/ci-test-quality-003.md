# Đồng bộ JUnit, Spring Test, Mockito và phiên bản Java

Một test suite Spring có thể gặp lỗi ngay cả khi code test và ứng dụng đều đúng nếu các thư viện kiểm thử không tương thích với nhau. Ví dụ, JUnit Jupiter API có thể được compile thành công nhưng engine không được tìm thấy khi chạy; `SpringExtension` có thể đến từ một phiên bản `spring-test` khác với `spring-core`; Mockito extension có thể lệch phiên bản với `mockito-core`; hoặc JDK dùng trong CI không đáp ứng baseline của Spring Framework.

Đồng bộ phiên bản nghĩa là chọn một bộ công cụ tương thích theo cùng một nền tảng: Java runtime/toolchain, Spring Framework hoặc Spring Boot, JUnit Platform/Jupiter, Mockito và plugin chạy test của Maven hoặc Gradle. Cách an toàn nhất là để một dependency management platform quản lý các phiên bản có liên quan, sau đó chỉ override khi có lý do rõ ràng và đã kiểm tra tương thích.

## 1. Các thành phần cần đồng bộ

Một test suite Spring thường có nhiều lớp thư viện:

| Thành phần | Vai trò | Ví dụ artifact |
| --- | --- | --- |
| Java JDK | Compile và chạy ứng dụng/test. | JDK 17, 21 hoặc phiên bản được dự án hỗ trợ. |
| Spring Framework | Core container, context, MVC, transaction và test integration. | `spring-core`, `spring-context`, `spring-test`. |
| Spring Boot (nếu dùng) | Dependency management và auto-configuration cho ứng dụng/test. | `spring-boot-dependencies`, `spring-boot-starter-test`. |
| JUnit Platform | Nền tảng discovery và thực thi test engine. | `junit-platform-engine`, `junit-platform-launcher`. |
| JUnit Jupiter | API, parameterized test và engine cho JUnit 5+. | `junit-jupiter-api`, `junit-jupiter-params`, `junit-jupiter-engine`. |
| JUnit Vintage (nếu cần) | Chạy test viết theo JUnit 3/4 trên JUnit Platform. | `junit-vintage-engine`. |
| Mockito | Mock, stub và verify interaction. | `mockito-core`. |
| Mockito JUnit integration | Extension để khởi tạo mock và quản lý strictness. | `mockito-junit-jupiter`. |
| Build test plugin | Khởi chạy test engine từ Maven hoặc Gradle. | Maven Surefire/Failsafe, Gradle test task. |

Không phải mọi project đều cần tất cả artifact trên. Một ứng dụng Spring Boot thường nhận phần lớn thư viện qua `spring-boot-starter-test`. Một project Spring Framework thuần cần khai báo các dependency và BOM phù hợp hơn. JUnit Vintage chỉ cần khi còn test JUnit 3/4; nếu toàn bộ test đã dùng Jupiter thì không cần thêm engine này.

## 2. Bắt đầu từ Java version mà toàn bộ stack hỗ trợ

Java version là nền tảng của dependency compatibility. Phiên bản JDK dùng để compile, phiên bản bytecode được tạo ra và JDK dùng để chạy test phải được cấu hình nhất quán.

Một số baseline quan trọng theo thế hệ framework:

| Thành phần / thế hệ | Baseline Java cần chú ý |
| --- | --- |
| Spring Framework 5.x | Hỗ trợ các dòng Java cũ hơn, tùy minor release; thường gặp trong ứng dụng Java 8/11. |
| Spring Framework 6.x | Yêu cầu Java 17 trở lên và chuyển sang Jakarta EE APIs (`jakarta.*`). |
| Spring Framework 7.x | Tiếp tục baseline Java 17 trở lên; kiểm tra yêu cầu cụ thể của minor release và module. |
| Spring Boot 3.x | Java 17 trở lên. |
| Mockito 5.x | Java 11 trở lên. |
| JUnit Platform/Jupiter | Baseline thay đổi theo major release; kiểm tra yêu cầu của đúng major đang chọn. |

Baseline của dự án phải đáp ứng yêu cầu cao nhất trong các thành phần được dùng. Ví dụ, nếu ứng dụng dùng Spring Framework 6.x, Java 11 không đủ dù Mockito 5 có thể chạy trên Java 11. Nếu Spring yêu cầu Java 17, JDK 17 hoặc mới hơn mới là lựa chọn hợp lệ.

Đừng chỉ kiểm tra `java -version` trên máy developer. Build có thể dùng một JDK khác thông qua Maven toolchain, Gradle toolchain hoặc CI image. Cần đồng bộ:

- JDK chạy Maven/Gradle và test worker.
- Java toolchain mà compiler/test task chọn.
- `source`/`target` hoặc `--release` của compiler.
- JDK được cài đặt trong CI runner.
- Java version được khai báo trong Docker image hoặc build container nếu có.

### Maven compiler configuration

Có thể dùng `maven.compiler.release` để giới hạn API và bytecode theo Java release mục tiêu:

```xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>${java.version}</maven.compiler.release>
</properties>
```

Nếu project dùng Spring Boot parent, parent thường quản lý plugin và các property liên quan. Hãy đặt Java version theo baseline mà ứng dụng chọn, không khai báo các giá trị `source`, `target` và `release` mâu thuẫn nhau.

### Gradle Java toolchain

Với Gradle, toolchain giúp build chọn JDK rõ ràng:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Nếu cần đặt bytecode target, cấu hình `options.release` cho `JavaCompile` theo cùng release. Toolchain có thể giúp Gradle tìm hoặc tải JDK phù hợp tùy cấu hình môi trường, nhưng CI vẫn cần được chuẩn bị để có quyền truy cập JDK đó.

## 3. Spring Boot: ưu tiên dependency management của Boot

Spring Boot cung cấp BOM `spring-boot-dependencies` và parent POM để quản lý một tập phiên bản đã được kiểm thử cùng nhau. `spring-boot-starter-test` gom các thư viện kiểm thử thường dùng, trong đó có Spring Test, JUnit Jupiter, Mockito, AssertJ và một số công cụ khác.

Ví dụ Maven dùng Spring Boot parent:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`3.4.0` là version minh họa cho cấu hình parent; khi áp dụng, thay bằng release Spring Boot mà dự án lựa chọn và đã xác nhận tương thích với Java cùng các thư viện khác.

Nếu không dùng Boot parent, có thể import BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Khi dùng Boot BOM, thông thường không cần ghi version riêng cho `spring-test`, `junit-jupiter`, `mockito-core` hoặc `mockito-junit-jupiter`. Nếu khai báo version riêng cho một thư viện do BOM quản lý, project có thể tạo ra một tổ hợp chưa được Boot release đó kiểm thử.

### Gradle với Spring Boot plugin

Trong Gradle, plugin Spring Boot và dependency management plugin có thể quản lý dependency theo BOM. Một cấu hình Kotlin DSL điển hình:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Các version ở ví dụ plugin là placeholder. Với Gradle thuần, có thể dùng `platform("org.springframework.boot:spring-boot-dependencies:...")` trong `testImplementation` hoặc cấu hình dependency management tương ứng để các thư viện kiểm thử lấy version từ BOM.

## 4. Spring Framework thuần: dùng Spring BOM và JUnit BOM

Nếu project không dùng Spring Boot, hãy quản lý các module Spring Framework theo cùng một release train. Không nên để `spring-test` ở một version còn `spring-core`, `spring-context` hoặc `spring-webmvc` ở version khác.

Maven có thể import Spring Framework BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${spring-framework.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>${junit.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<properties>
    <spring-framework.version>6.2.x</spring-framework.version>
    <junit.version>5.x.y</junit.version>
    <mockito.version>5.x.y</mockito.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-core</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-junit-jupiter</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Các version dạng `6.2.x`, `5.x.y` và `5.x.y` chỉ là ký hiệu minh họa cho một dòng release; thay bằng version cụ thể. Spring BOM quản lý các module Spring, JUnit BOM quản lý các module JUnit. Mockito không có cùng BOM trong ví dụ này nên `mockito-core` và `mockito-junit-jupiter` được đặt cùng một property version.

Nếu project dùng một nền tảng dependency management khác, giữ nguyên nguyên tắc: một version Spring thống nhất, một JUnit BOM thống nhất và cùng một version cho các artifact Mockito liên quan.

### Gradle với các platform

Gradle có thể dùng BOM thông qua `platform(...)`:

```kotlin
dependencies {
    implementation(platform("org.springframework:spring-framework-bom:6.2.x"))
    testImplementation(platform("org.junit:junit-bom:5.x.y"))

    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.mockito:mockito-core:5.x.y")
    testImplementation("org.mockito:mockito-junit-jupiter:5.x.y")
}

tasks.test {
    useJUnitPlatform()
}
```

Với Gradle version catalog, có thể khai báo version trong `libs.versions.toml` rồi dùng cùng alias/version cho `mockito-core` và `mockito-junit-jupiter`. Tránh khai báo version rải rác ở nhiều module vì dễ tạo lệch phiên bản khi nâng cấp.

## 5. Đồng bộ JUnit API, engine và Platform

JUnit 5 được chia thành các thành phần có vai trò riêng:

- JUnit Jupiter API chứa annotation và assertion API như `@Test`, `@BeforeEach`, `Assertions`.
- JUnit Jupiter Engine thực thi các test Jupiter.
- JUnit Platform Engine định nghĩa contract cho test engine.
- JUnit Platform Launcher discovery và khởi chạy test engine; build tool hoặc IDE có thể dùng launcher theo cách riêng.
- JUnit Vintage Engine cho phép chạy test JUnit 3/4 trên JUnit Platform.

Có `junit-jupiter-api` ở compile classpath không có nghĩa test đã có engine để chạy. Nếu engine thiếu hoặc plugin không dùng JUnit Platform, test có thể không được phát hiện.

### Maven

Một dependency gọn thường dùng là `junit-jupiter`, vì artifact aggregate này kéo API, params và engine phù hợp. Có thể khai báo qua BOM để không cần version riêng:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Maven Surefire cần phiên bản có hỗ trợ JUnit Platform phù hợp với JUnit đang dùng. Với Maven hiện đại, dùng Surefire 3.x là lựa chọn phổ biến; nếu project còn dùng plugin cũ, kiểm tra tài liệu plugin và nâng cấp khi cần.

Ví dụ cấu hình plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>${maven-surefire.version}</version>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <version>${maven-failsafe.version}</version>
        </plugin>
    </plugins>
</build>
```

Surefire thường chạy unit test trong phase `test`; Failsafe thường chạy integration test trong các phase `integration-test` và `verify`. Cả hai plugin cần phiên bản tương thích với JUnit Platform và cách cấu hình test của dự án.

### Gradle

Gradle cần được cấu hình dùng JUnit Platform:

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

Trong một số Gradle version mới, launcher được tự động xử lý theo cấu hình plugin hoặc dependency management, nhưng khai báo rõ `junit-platform-launcher` ở test runtime có thể giúp tránh thiếu launcher khi build yêu cầu nó. Giữ launcher cùng release train với JUnit Platform được BOM quản lý.

### Có nên dùng JUnit Vintage?

Nếu project còn test JUnit 4 và muốn chạy chúng trên JUnit Platform, thêm `junit-vintage-engine` với version do JUnit BOM quản lý. Nếu không còn test JUnit 3/4, bỏ engine này để giảm dependency và tránh nhầm lẫn khi discovery.

Không nên trộn JUnit 4 `@RunWith` và Jupiter `@ExtendWith` một cách tùy tiện. Chọn engine phù hợp với từng test class và dùng migration path có chủ đích.

## 6. Đồng bộ Mockito core và Mockito JUnit Jupiter

Mockito có thư viện core chứa API mock/stub/verify và module `mockito-junit-jupiter` cung cấp `MockitoExtension` cho JUnit Jupiter. Hai artifact này cần cùng một version.

```java
@ExtendWith(MockitoExtension.class)
class PriceServiceTest {

    @Mock
    ExchangeRateClient exchangeRateClient;

    @InjectMocks
    PriceService priceService;

    @Test
    void shouldConvertPrice() {
        when(exchangeRateClient.rate("USD", "EUR"))
                .thenReturn(new BigDecimal("0.92"));

        assertThat(priceService.convert(
                new BigDecimal("10.00"), "USD", "EUR"))
                .isEqualByComparingTo("9.20");
    }
}
```

Nếu `mockito-core` và `mockito-junit-jupiter` lệch version, có thể gặp `NoSuchMethodError`, `NoClassDefFoundError`, lỗi extension discovery hoặc hành vi không nhất quán. Quản lý chúng bằng một property hoặc BOM/platform phù hợp.

### Mockito và Java version

Mockito 5 yêu cầu Java 11 trở lên và dùng inline mock maker mặc định. Điều này có thể ảnh hưởng tới cách mock final class/method và cách project cấu hình mock maker. Nếu ứng dụng dùng Java 8, không thể chỉ nâng Mockito lên 5 mà bỏ qua baseline; cần chọn dòng Mockito tương thích với Java hoặc nâng Java của dự án.

Khi nâng Mockito major version, đọc release notes của Mockito và kiểm tra:

- Java baseline của version mới.
- Thay đổi mock maker mặc định.
- Hành vi mock static/final và yêu cầu instrumentation.
- Các API deprecated hoặc đã bị loại bỏ.
- Tương thích với plugin, agent hoặc runtime của CI.

Không nên thêm `mockito-inline` một cách máy móc nếu Mockito version đã dùng inline mock maker mặc định hoặc nếu dependency đó không còn phù hợp với dòng Mockito hiện tại. Cấu hình mock maker cần dựa trên version và nhu cầu thực tế.

## 7. Phân biệt `SpringExtension` và `MockitoExtension`

Hai extension có nhiệm vụ khác nhau:

| Extension | Chức năng |
| --- | --- |
| `SpringExtension` | Kết nối JUnit Jupiter với Spring TestContext Framework; quản lý context, dependency injection và các listener của Spring. |
| `MockitoExtension` | Khởi tạo Mockito annotations, quản lý strict stubbing và vòng đời mock trong test. |

Test chỉ kiểm tra service thuần Java thường dùng `MockitoExtension`:

```java
@ExtendWith(MockitoExtension.class)
class BillingServiceTest {
    @Mock PaymentGateway paymentGateway;
    @InjectMocks BillingService billingService;
}
```

Test cần Spring context dùng `SpringExtension`, thường thông qua `@SpringJUnitConfig`, `@SpringBootTest`, `@DataJpaTest` hoặc các annotation test slice của Boot:

```java
@SpringJUnitConfig(AppConfig.class)
class BillingIntegrationTest {
    @Autowired BillingService billingService;
}
```

Nếu một test thực sự cần cả Spring context và Mockito extension, JUnit Jupiter cho phép đăng ký nhiều extension:

```java
@ExtendWith({SpringExtension.class, MockitoExtension.class})
class CombinedTest {
    // Dùng Spring injection và các mock Mockito độc lập.
}
```

Tuy nhiên, không phải lúc nào cũng cần cả hai. Trong test Spring, có thể để Spring quản lý mock bean bằng cơ chế bean override phù hợp với version, ví dụ `@MockitoBean` ở các dòng Spring hỗ trợ. Với unit test không cần context, dùng `MockitoExtension` đơn giản hơn và tránh khởi tạo Spring không cần thiết.

### `@Mock` không giống `@MockitoBean`

`@Mock` tạo một Mockito mock trong test instance. Nó không tự thay thế bean trong Spring `ApplicationContext`. `@MockitoBean` (ở Spring Framework versions có hỗ trợ) đăng ký bean override để một bean trong context được thay bằng mock. Spring Boot các dòng cũ có `@MockBean`; khả năng và trạng thái API phụ thuộc phiên bản Boot.

Ví dụ khái niệm:

```java
@SpringBootTest
class BillingControllerTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    MockMvc mockMvc;
}
```

Không thay `@MockBean` bằng `@MockitoBean` chỉ dựa vào tên. Hãy kiểm tra Spring Framework/Boot version và import đúng annotation có sẵn trong project.

## 8. Đồng bộ `spring-test` với các module Spring khác

`spring-test` phụ thuộc vào API của các module Spring Framework khác. Nếu `spring-test` được resolve ở version khác với `spring-core`, `spring-context`, `spring-beans` hoặc `spring-webmvc`, lỗi runtime có thể xuất hiện dù compile thành công.

Các dấu hiệu thường gặp:

- `NoSuchMethodError`: code đã compile với API của version mới nhưng runtime nạp class version cũ.
- `NoClassDefFoundError` hoặc `ClassNotFoundException`: thiếu class do dependency không có hoặc version không chứa API cần dùng.
- `AbstractMethodError`: interface hoặc abstract method không tương thích giữa các version.
- Lỗi `ApplicationContext` hoặc listener khởi tạo: một phần Spring Test và Spring Framework không cùng release train.
- Lỗi annotation không được nhận diện: test dùng API chỉ có ở version mới nhưng runtime vẫn nạp version cũ.

Nguyên tắc: giữ tất cả module `org.springframework` trong cùng một dòng version được Spring BOM hoặc Spring Boot BOM quản lý. Tránh khai báo version riêng cho `spring-test` nếu các module Spring khác đã được quản lý bởi platform.

## 9. Jakarta EE và sự chuyển đổi từ Spring 5 sang Spring 6

Spring Framework 6 chuyển từ Java EE `javax.*` sang Jakarta EE `jakarta.*`. Đây không chỉ là đổi tên import trong code; toàn bộ dependency liên quan đến Servlet, Persistence, Validation và các API Jakarta cần tương thích.

Ví dụ:

```java
// Spring Framework 5 / Java EE ecosystem cũ
import javax.servlet.http.HttpServletRequest;

// Spring Framework 6+ / Jakarta EE ecosystem
import jakarta.servlet.http.HttpServletRequest;
```

Nếu test vẫn kéo một thư viện cũ dựa trên `javax.servlet` trong khi Spring 6 dùng `jakarta.servlet`, có thể gặp lỗi class loading hoặc type mismatch. Cần nâng các dependency test liên quan cùng lúc với Spring Framework, ví dụ servlet API, validation provider, persistence provider, test utility hoặc embedded server.

Không thể giải quyết một dependency `javax.*` không tương thích chỉ bằng cách nâng JUnit hoặc Mockito. Hãy xác định namespace mà thư viện đó dùng và chọn version tương thích với Spring/Jakarta stack.

## 10. Maven: kiểm soát dependency tree

Maven có thể resolve nhiều version của cùng một thư viện qua dependency transitive. Version được chọn có thể khác với version mà developer nghĩ đang sử dụng.

Các lệnh hữu ích:

```bash
mvn dependency:tree -Dscope=test
```

Lọc các thư viện quan trọng:

```bash
mvn dependency:tree -Dscope=test -Dincludes=org.springframework,org.junit,org.mockito
```

Kiểm tra effective POM để xem BOM, parent và property nào đang quyết định version:

```bash
mvn help:effective-pom
```

Nếu có version bị override ngoài ý muốn, xem dependency path nào kéo nó vào. Dùng `dependencyManagement` để quản lý version một cách có chủ đích; chỉ dùng exclusion khi đã hiểu dependency thay thế và không làm mất class mà thư viện khác cần.

## 11. Gradle: kiểm tra dependency resolution

Gradle có thể chọn version theo resolution strategy, platform, constraint hoặc version catalog. Dùng `dependencies` và `dependencyInsight` để biết version nào thực sự được chọn.

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Kiểm tra một module cụ thể:

```bash
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
```

`testCompileClasspath` cho biết dependency khi compile test; `testRuntimeClasspath` cho biết dependency thực sự có khi chạy test. Một test có thể compile được nhưng runtime lại chọn version khác, vì vậy cần kiểm tra cả hai khi chẩn đoán lỗi linkage.

Nếu dùng version catalog, khai báo các version tập trung:

```toml
[versions]
spring = "6.2.x"
junit = "5.x.y"
mockito = "5.x.y"

[libraries]
spring-test = { module = "org.springframework:spring-test", version.ref = "spring" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
mockito-core = { module = "org.mockito:mockito-core", version.ref = "mockito" }
mockito-junit-jupiter = { module = "org.mockito:mockito-junit-jupiter", version.ref = "mockito" }
```

Đây là minh họa cách tập trung version; project thực tế nên ưu tiên BOM/platform nếu có thể, thay vì tự khóa version từng module Spring hoặc JUnit khi đã có BOM quản lý.

## 12. Build plugin và IDE cũng phải tương thích

Dependency đúng chưa đủ nếu Maven Surefire, Failsafe, Gradle test task hoặc IDE runner không nhận diện đúng test engine.

Với Maven:

- Dùng Surefire có hỗ trợ JUnit Platform cho unit test Jupiter.
- Dùng Failsafe phù hợp cho integration test nếu dự án tách phase.
- Kiểm tra plugin version được Spring Boot parent hoặc parent POM quản lý.
- Tránh cấu hình provider JUnit 4 cũ khi project chỉ dùng Jupiter.

Với Gradle:

- Cấu hình `useJUnitPlatform()` cho test task.
- Đảm bảo JUnit Platform launcher có trên runtime classpath nếu Gradle version/cấu hình yêu cầu.
- Giữ Gradle wrapper ở version tương thích với JDK mà CI sử dụng.

Với IDE:

- Kiểm tra Project SDK và Gradle/Maven JVM.
- Đồng bộ test runner với build tool để test chạy trong IDE và CI giống nhau.
- Khi IDE báo không tìm thấy engine nhưng command line chạy được, kiểm tra cấu hình runner và classpath của IDE.

## 13. Dấu hiệu phiên bản không đồng bộ và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `UnsupportedClassVersionError` | JDK runtime thấp hơn bytecode của dependency hoặc test. | Kiểm tra JDK thực chạy test và Java baseline của thư viện. |
| `NoSuchMethodError` trong Spring | Module Spring lệch version hoặc runtime classpath chọn bản cũ. | Xem dependency tree/runtime classpath và BOM. |
| `NoClassDefFoundError` cho Jupiter Engine | Thiếu engine hoặc version conflict. | Kiểm tra `junit-jupiter-engine` và Platform. |
| Test compile nhưng không được chạy | Build plugin không dùng JUnit Platform hoặc engine không có. | Kiểm tra Surefire/Failsafe hoặc `useJUnitPlatform()`. |
| Mockito extension không được tìm thấy | Thiếu `mockito-junit-jupiter` hoặc artifact lệch version. | Kiểm tra dependency test và version của core/extension. |
| `NoSuchMethodError` trong Mockito | `mockito-core` và extension/module khác version. | Đồng bộ tất cả artifact Mockito. |
| Lỗi `javax.servlet`/`jakarta.servlet` | Dependency dùng namespace không tương thích. | Nâng thư viện theo Spring 6+ hoặc chọn stack Spring 5 phù hợp. |
| Chỉ CI thất bại | JDK, toolchain, plugin hoặc cache dependency khác local. | Ghi nhận `java -version`, wrapper/plugin và dependency resolution. |

Không nên sửa lỗi bằng cách thêm ngẫu nhiên một version dependency vào cuối file build. Trước tiên tìm version thực tế được resolve và đường dependency đã kéo nó vào.

## 14. Quy trình nâng cấp đồng bộ

Khi nâng JUnit, Spring Test, Mockito hoặc Java, thực hiện theo từng lớp:

1. Chọn Java baseline mục tiêu và xác nhận runtime của developer, build tool và CI đáp ứng.
2. Chọn dòng Spring Boot hoặc Spring Framework phù hợp với Java và Jakarta namespace.
3. Nếu dùng Spring Boot, nâng Boot BOM/parent và để nó quản lý các dependency Spring/JUnit/Mockito trước.
4. Nếu dùng Spring Framework thuần, nâng Spring BOM; đồng thời chọn JUnit BOM và version Mockito tương thích.
5. Đảm bảo `spring-test` cùng version với các module Spring khác.
6. Đảm bảo JUnit API, Jupiter Engine, Platform Launcher và Vintage (nếu cần) cùng release train.
7. Đảm bảo `mockito-core` và `mockito-junit-jupiter` cùng version.
8. Nâng Maven Surefire/Failsafe hoặc Gradle wrapper/test configuration nếu cần.
9. Kiểm tra dependency tree/runtime classpath để phát hiện version bị override.
10. Chạy test compile, unit test và integration test; xử lý các lỗi do thay đổi API hoặc baseline.
11. Cập nhật JDK CI image/toolchain và ghi rõ version được hỗ trợ trong dự án.

Không nên nâng đồng thời mọi thành phần lên phiên bản mới nhất mà không xem compatibility. Thay đổi một platform hoặc một major version tại một thời điểm giúp xác định nguyên nhân lỗi dễ hơn.

## 15. Ví dụ cấu hình đồng bộ theo hai kiểu dự án

### Spring Boot project

Với Spring Boot, cấu hình thường ngắn vì starter và BOM quản lý dependency:

```xml
<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Trong cấu hình này, version của Boot được chọn ở parent hoặc BOM. Không khai báo thêm version riêng cho Spring Test, JUnit hoặc Mockito trừ khi có lý do cụ thể và đã xác minh tương thích.

### Spring Framework project không dùng Boot

Với Spring thuần, quản lý các version bằng BOM/property:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <spring-framework.version>6.2.x</spring-framework.version>
    <junit.version>5.x.y</junit.version>
    <mockito.version>5.x.y</mockito.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${spring-framework.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>${junit.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-core</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-junit-jupiter</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Các giá trị `x` và `y` cần được thay bằng version cụ thể. Dự án cũng cần khai báo plugin Maven tương thích để chạy JUnit Platform. Với Spring Framework 6.x, `maven.compiler.release` phải từ 17 trở lên.

## 16. Nguyên tắc duy trì compatibility trong CI

CI nên kiểm tra đúng bộ công cụ mà project tuyên bố hỗ trợ. Một pipeline ổn định cần:

- Cố định JDK hoặc dùng matrix JDK có chủ đích.
- Dùng Maven Wrapper hoặc Gradle Wrapper để build tool version nhất quán.
- Dùng dependency BOM/platform thay vì version rời rạc.
- In thông tin Java và dependency resolution khi chẩn đoán lỗi.
- Chạy test qua cùng build command mà developer sử dụng.
- Kiểm tra cả compile test và runtime test classpath.
- Không cache thư viện hoặc build output theo cách làm lẫn dependency giữa các branch/Java version.
- Nâng dependency định kỳ và đọc release notes của Spring, JUnit, Mockito và build tool.

Nếu hỗ trợ nhiều JDK, chạy matrix theo các JDK đã công bố. Đừng để CI vô tình chạy bằng JDK mới nhất của runner trong khi project thực tế chỉ hỗ trợ JDK cũ hơn. Ngược lại, nếu framework đã nâng baseline, cập nhật JDK pipeline và tài liệu dự án cùng lúc.

## Kết luận

Đồng bộ JUnit, Spring Test, Mockito và Java bắt đầu từ Java baseline và dependency platform của dự án. Với Spring Boot, ưu tiên BOM/parent và `spring-boot-starter-test`; với Spring Framework thuần, dùng Spring Framework BOM, JUnit BOM và quản lý version Mockito tập trung. Giữ `spring-test` cùng release train với các module Spring, JUnit API/engine/launcher tương thích, và `mockito-core` cùng version với `mockito-junit-jupiter`.

Khi có lỗi runtime hoặc test không được discovery, kiểm tra dependency thực sự được resolve và JDK thực sự chạy test trước khi thêm override. Một bộ version rõ ràng, được build tool và CI sử dụng nhất quán, giúp test suite ổn định hơn và làm cho việc nâng cấp framework có thể dự đoán được.

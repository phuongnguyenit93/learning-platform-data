# Thiết lập dependency kiểm thử và đồng bộ phiên bản JUnit với Spring Test

JUnit Jupiter là nền tảng kiểm thử phổ biến trong các dự án Spring hiện đại. Để các bài kiểm thử được biên dịch, được phát hiện và chạy đúng, dự án cần có các thành phần phù hợp của JUnit Jupiter, JUnit Platform và Spring Test. Những dependency này có quan hệ với nhau nhưng không dùng chung một số phiên bản: Spring Framework có dòng phiên bản riêng, JUnit Jupiter có dòng phiên bản riêng và JUnit Platform cũng thuộc hệ sinh thái JUnit.

Thiết lập đúng dependency management giúp dự án tránh các lỗi như biên dịch được nhưng không tìm thấy test engine khi chạy, thiếu `SpringExtension`, hoặc gặp `NoSuchMethodError` do API và engine JUnit không tương thích. Với ứng dụng Spring Boot, lựa chọn đơn giản nhất thường là dùng `spring-boot-starter-test` và để Spring Boot quản lý các phiên bản tương thích. Với dự án chỉ dùng Spring Framework, cần quản lý phiên bản Spring và JUnit bằng các BOM phù hợp.

## 1. Hiểu các thành phần trong bộ kiểm thử

Trước khi khai báo dependency, cần phân biệt vai trò của từng thành phần.

| Thành phần | Artifact tiêu biểu | Vai trò |
|---|---|---|
| JUnit Jupiter API | `org.junit.jupiter:junit-jupiter-api` | Cung cấp annotation và API viết test như `@Test`, `@BeforeEach`, `Assertions` và extension model |
| JUnit Jupiter Params | `org.junit.jupiter:junit-jupiter-params` | Cung cấp `@ParameterizedTest`, `@ValueSource`, `@CsvSource` và các nguồn tham số |
| JUnit Jupiter Engine | `org.junit.jupiter:junit-jupiter-engine` | Thực thi các test được viết bằng JUnit Jupiter |
| JUnit Platform | `org.junit.platform:*` | Nền tảng phát hiện và khởi chạy test engine; có launcher, engine và reporting API |
| Spring Test | `org.springframework:spring-test` | Cung cấp Spring TestContext Framework, `SpringExtension`, `MockMvc` và các tiện ích kiểm thử Spring |
| Spring Boot Test | `org.springframework.boot:spring-boot-test` | Cung cấp các tiện ích kiểm thử dành cho Spring Boot |
| Spring Boot Test AutoConfigure | `org.springframework.boot:spring-boot-test-autoconfigure` | Cung cấp các annotation test slice như `@WebMvcTest`, `@DataJpaTest` và cấu hình tự động liên quan |

JUnit Jupiter và JUnit Platform thường được sử dụng cùng nhau. API cho phép biên dịch mã test, còn engine chịu trách nhiệm thực thi. Chỉ có API mà thiếu engine có thể khiến test biên dịch thành công nhưng không chạy được. JUnit Jupiter Params cần thiết khi sử dụng kiểm thử tham số; dependency tổng hợp `junit-jupiter` có thể giúp khai báo các thành phần Jupiter cùng nhau.

Spring Test bổ sung tích hợp với Spring. Ví dụ, `SpringExtension` kết nối JUnit Jupiter với Spring TestContext Framework để quản lý `ApplicationContext`, dependency injection, transaction test và các callback của vòng đời test. `@SpringBootTest` và `@SpringJUnitConfig` đã tích hợp extension tương ứng; với một lớp test JUnit Jupiter thông thường cần Spring context, có thể khai báo `@ExtendWith(SpringExtension.class)` cùng cấu hình context phù hợp.

## 2. Chọn dependency theo loại dự án

### 2.1. Dự án Spring Boot

Với ứng dụng Spring Boot, `spring-boot-starter-test` là điểm bắt đầu phù hợp. Starter này tập hợp Spring Boot Test, Spring Test, JUnit Jupiter và các thư viện kiểm thử thường dùng như Mockito, AssertJ, Hamcrest, JSONassert, JsonPath và XMLUnit theo phiên bản do Spring Boot quản lý.

Thông thường, không cần khai báo riêng `junit-jupiter-api`, `junit-jupiter-engine` hoặc `spring-test` nếu đã dùng starter. Việc thêm lại các artifact này với phiên bản tự chọn có thể tạo ra xung đột không cần thiết.

### 2.2. Dự án chỉ dùng Spring Framework

Một thư viện Java hoặc ứng dụng Spring không dùng Spring Boot có thể khai báo trực tiếp:

- `spring-test` để sử dụng Spring TestContext Framework và các tiện ích kiểm thử của Spring.
- `junit-jupiter` để viết và chạy test JUnit Jupiter.
- Các thư viện assertion hoặc mocking bổ sung nếu dự án cần.

Trong trường hợp này, nên quản lý phiên bản các module Spring bằng Spring Framework BOM và quản lý các module JUnit bằng JUnit BOM. Hai BOM có trách nhiệm khác nhau và không nên giả định rằng phiên bản của chúng phải giống nhau.

### 2.3. Dự án Java không sử dụng Spring Test

Nếu chỉ viết unit test thuần Java và không khởi tạo Spring context, có thể chỉ cần JUnit Jupiter cùng các thư viện hỗ trợ thực sự được sử dụng. Không cần thêm `spring-test` chỉ vì dự án có dùng Spring ở phần ứng dụng. Dependency nên phản ánh trách nhiệm kiểm thử của module.

## 3. Khai báo dependency với Maven

### 3.1. Dùng Spring Boot parent

Nếu dự án kế thừa `spring-boot-starter-parent`, parent cung cấp dependency management và cấu hình plugin build phù hợp với phiên bản Spring Boot đã chọn. Trong `pom.xml`, chỉ cần thêm starter kiểm thử ở scope `test`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Scope `test` bảo đảm các thư viện kiểm thử chỉ có mặt trên classpath kiểm thử, không trở thành dependency runtime của ứng dụng được đóng gói. Các phiên bản JUnit, Spring Test và thư viện kiểm thử đi kèm được lấy từ dependency management của Spring Boot.

Một bài kiểm thử Spring Boot có thể sử dụng các annotation như sau:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ApplicationContextTest {

    @Test
    void applicationContextLoads() {
        assertThat(true).isTrue();
    }
}
```

Ví dụ trên minh họa cách JUnit Jupiter và Spring Boot Test phối hợp trong một test. Trong bài kiểm thử thực tế, assertion nên kiểm tra một hành vi hoặc trạng thái có ý nghĩa của ứng dụng.

### 3.2. Không dùng Spring Boot parent nhưng vẫn dùng Spring Boot BOM

Một số dự án cần giữ parent POM riêng. Có thể import `spring-boot-dependencies` trong `dependencyManagement`, sau đó khai báo starter mà không ghi phiên bản tại từng dependency:

```xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
</properties>

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

Phiên bản `3.3.13` chỉ minh họa một phiên bản cụ thể của Spring Boot 3.3; dự án cần dùng phiên bản Spring Boot đã được lựa chọn và hỗ trợ trong môi trường của mình. Khi import BOM, không cần ghi lại phiên bản cho từng module Spring hoặc JUnit do BOM quản lý.

Lưu ý: import BOM chỉ cung cấp dependency management. Nếu không kế thừa Spring Boot parent, cấu hình plugin Maven như Surefire vẫn cần được quản lý phù hợp để Maven phát hiện và chạy JUnit Platform. Không nên mặc định rằng import BOM cũng tự động áp dụng toàn bộ cấu hình build của parent POM.

### 3.3. Dùng Spring Framework mà không dùng Spring Boot

Với dự án chỉ dùng Spring Framework, có thể import riêng Spring Framework BOM và JUnit BOM:

```xml
<properties>
    <spring-framework.version>6.1.21</spring-framework.version>
    <junit.version>5.10.5</junit.version>
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
</dependencies>
```

Hai phiên bản trong ví dụ thuộc hai dòng phát hành độc lập: `spring-framework.version` quản lý các module Spring, còn `junit.version` quản lý hệ sinh thái JUnit. Không cần làm cho hai số phiên bản bằng nhau. Khi chọn phiên bản thực tế, cần đối chiếu yêu cầu Java, Spring Framework và JUnit của dự án.

Với Maven không dùng Spring Boot parent, hãy cấu hình một phiên bản Maven Surefire tương thích với JUnit Platform. Nếu dự án có nhiều module, đặt các BOM và plugin management ở parent POM để các module con dùng cùng quy tắc.

## 4. Khai báo dependency với Gradle

### 4.1. Spring Boot Gradle Plugin và dependency management

Trong dự án Spring Boot dùng Gradle, khai báo starter ở cấu hình `testImplementation`:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ví dụ giả định dự án đã cấu hình Spring Boot Gradle Plugin cùng dependency management theo cách mà dự án đang sử dụng. Khi plugin `io.spring.dependency-management` được áp dụng cùng Spring Boot Gradle Plugin, Spring Boot có thể tự động import BOM tương ứng. Nếu dự án dùng native Gradle BOM support, hãy khai báo platform như ví dụ tiếp theo.

`useJUnitPlatform()` yêu cầu Gradle chạy test thông qua JUnit Platform. Chỉ khai báo dependency JUnit mà không bật nền tảng này có thể khiến Gradle không phát hiện test Jupiter theo cấu hình mong đợi.

### 4.2. Dùng native Gradle BOM support

Gradle hỗ trợ import Maven BOM thông qua `platform(...)`. Với Spring Boot, có thể khai báo BOM trước starter:

```groovy
dependencies {
    testImplementation platform(
        "org.springframework.boot:spring-boot-dependencies:${springBootVersion}"
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Biến `springBootVersion` cần được định nghĩa trong cấu hình Gradle hoặc version catalog của dự án và phải khớp với phiên bản Spring Boot mà ứng dụng sử dụng. Không nên đồng thời áp dụng nhiều cơ chế quản lý phiên bản có các quy tắc override khác nhau nếu chưa hiểu rõ thứ tự ưu tiên.

### 4.3. Dự án chỉ dùng Spring Framework

Với dự án không dùng Spring Boot, import hai BOM độc lập trong cấu hình test:

```groovy
dependencies {
    testImplementation platform(
        "org.springframework:spring-framework-bom:${springFrameworkVersion}"
    )
    testImplementation 'org.springframework:spring-test'

    testImplementation platform("org.junit:junit-bom:${junitVersion}")
    testImplementation 'org.junit.jupiter:junit-jupiter'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`springFrameworkVersion` và `junitVersion` phải được định nghĩa trong cấu hình của dự án. Spring Framework BOM đồng bộ `spring-test` với các module Spring khác; JUnit BOM đồng bộ Jupiter API, Params, Engine và các module Platform thuộc cùng hệ sinh thái. `junit-platform-launcher` được khai báo ở runtime khi cấu hình build hoặc công cụ phát triển cần launcher trên test runtime classpath. Hãy giữ launcher trong cùng dòng phiên bản Platform do JUnit BOM quản lý.

Trong một dự án chỉ dùng JUnit Jupiter mà không cần Spring Test, có thể bỏ các dependency Spring và chỉ giữ JUnit BOM, `junit-jupiter`, launcher nếu cần, cùng `useJUnitPlatform()`.

### 4.4. Phân biệt các configuration của Gradle

Gradle cung cấp các configuration riêng để dependency xuất hiện đúng classpath:

| Configuration | Mục đích | Ví dụ |
|---|---|---|
| `testImplementation` | Dependency cần khi biên dịch mã trong `src/test` và có mặt trên test compile/runtime classpath | `spring-boot-starter-test`, `spring-test`, `junit-jupiter` |
| `testRuntimeOnly` | Dependency chỉ cần khi chạy test | JUnit Platform Launcher trong cấu hình cần khai báo riêng |
| `implementation` | Dependency của mã sản phẩm, có mặt trên compile/runtime classpath chính | Thư viện mà mã `src/main` trực tiếp sử dụng |
| `testCompileOnly` | Dependency chỉ cần để biên dịch test nhưng không cần ở runtime | Trường hợp đặc thù, không phải cấu hình mặc định cho JUnit engine |

Không đặt JUnit hoặc Mockito vào `implementation` chỉ để làm cho test biên dịch được. Điều đó đưa thư viện kiểm thử vào dependency của ứng dụng chính và có thể làm tăng kích thước artifact hoặc làm lộ dependency không cần thiết cho người dùng module.

## 5. Đồng bộ phiên bản JUnit với Spring Test

### 5.1. Đồng bộ theo từng hệ sinh thái

Spring Test và JUnit có quan hệ tích hợp nhưng không chia sẻ một số phiên bản chung. Quy tắc quản lý nên là:

1. `spring-test`, `spring-core`, `spring-context` và các module Spring Framework liên quan phải cùng dòng phiên bản Spring Framework.
2. `junit-jupiter-api`, `junit-jupiter-params` và `junit-jupiter-engine` phải tương thích và nên được quản lý cùng một phiên bản JUnit Jupiter.
3. Các module JUnit Platform như launcher và engine phải thuộc bộ phiên bản Platform tương ứng với JUnit Jupiter đã chọn.
4. Nếu dùng Spring Boot, ưu tiên để Spring Boot BOM quản lý cả Spring Framework và JUnit theo bộ phiên bản mà phiên bản Boot đó đã kiểm thử.

Ví dụ, Spring Framework `6.1.x` có thể đi cùng JUnit Jupiter `5.10.x` trong một cấu hình phù hợp. Hai số phiên bản không cần trùng nhau. Điều cần bảo đảm là các module trong cùng một hệ sinh thái được căn chỉnh và bộ phiên bản được chọn có thể phối hợp.

### 5.2. Vì sao Spring Boot starter thường là lựa chọn tốt?

Spring Boot BOM được thiết kế để quản lý một tập dependency tương thích cho phiên bản Spring Boot tương ứng. Khi dùng `spring-boot-starter-test`, dự án nhận được các dependency kiểm thử theo bộ phiên bản do BOM đó kiểm soát.

Nếu tự ghi phiên bản cho `spring-test` hoặc `junit-jupiter-engine`, dependency có thể lệch khỏi bộ phiên bản mà Boot đã quản lý. Ví dụ, nâng riêng JUnit Engine trong khi API vẫn ở phiên bản cũ có thể gây lỗi liên kết class hoặc phương thức lúc chạy. Nâng riêng `spring-test` cũng có thể làm nó lệch với `spring-core` hoặc `spring-context` được Boot chọn.

Vì vậy, với Spring Boot, cách mặc định nên là:

- Khai báo `spring-boot-starter-test` trong scope kiểm thử.
- Không ghi phiên bản riêng cho các dependency đã được Boot BOM quản lý.
- Chỉ override phiên bản khi có lý do kỹ thuật rõ ràng và đã kiểm tra tương thích của toàn bộ bộ dependency liên quan.

### 5.3. Khi nào cần override phiên bản JUnit?

Có thể có trường hợp dự án cần một bản sửa lỗi hoặc tính năng mới của JUnit trước khi nâng Spring Boot. Khi đó, cần kiểm tra phiên bản JUnit mà Spring Boot BOM đang quản lý, phạm vi hỗ trợ và các thay đổi tương thích.

Nếu buộc phải override, nên quản lý một phiên bản JUnit thống nhất qua JUnit BOM hoặc cơ chế property/dependency management được dự án sử dụng. Không nên chỉ nâng `junit-jupiter-engine` trong khi giữ `junit-jupiter-api`, `junit-jupiter-params` hoặc JUnit Platform ở phiên bản cũ.

Sau khi override, chạy toàn bộ test trên CI và kiểm tra dependency graph thực tế. Nếu Spring Test tích hợp với một API JUnit có thay đổi, lỗi có thể xuất hiện trong lúc khởi tạo extension hoặc khi thực thi callback, dù mã test vẫn biên dịch thành công.

### 5.4. Không trộn lẫn JUnit 4 và JUnit Jupiter ngoài chủ đích

JUnit 4 sử dụng các package và cơ chế như `org.junit.Test`, `@RunWith` và `SpringRunner`. JUnit Jupiter sử dụng `org.junit.jupiter.api.Test`, `@ExtendWith` và extension model.

Một lớp test Jupiter thường bắt đầu như sau:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.junit.jupiter.SpringExtension;

@ExtendWith(SpringExtension.class)
class RepositoryIntegrationTest {

    @Test
    void loadsWithSpringContext() {
        // Test body
    }
}
```

Đoạn mã minh họa việc kết nối Spring Extension với JUnit Jupiter; lớp test thực tế cần cấu hình context bằng `@ContextConfiguration`, `@SpringJUnitConfig` hoặc annotation phù hợp khác.

Nếu một dự án cũ vẫn có test JUnit 4, JUnit Vintage Engine có thể được dùng để chạy các test đó thông qua JUnit Platform. Chỉ thêm Vintage khi thật sự cần duy trì test JUnit 4 trong giai đoạn chuyển đổi. Với test mới, nên thống nhất JUnit Jupiter để tránh phải quản lý hai mô hình extension và hai bộ import.

## 6. Spring Test kết nối với JUnit Jupiter như thế nào?

Spring Test cung cấp `SpringExtension`, một JUnit Jupiter extension. Extension này kết nối vòng đời test của Jupiter với Spring TestContext Framework. Nó cho phép Spring tạo và tái sử dụng `ApplicationContext`, inject bean vào test, quản lý transaction test và áp dụng các listener/callback của Spring.

Với Spring Boot, có thể sử dụng `@SpringBootTest`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class GreetingServiceTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertThat(greetingService.greet("Lan"))
                .isEqualTo("Hello, Lan");
    }
}
```

`@SpringBootTest` khởi tạo application context theo cấu hình Spring Boot và tích hợp Spring Extension. Vì vậy, không cần thêm `@ExtendWith(SpringExtension.class)` lần nữa trong ví dụ này.

Với Spring Framework không dùng Boot, `@SpringJUnitConfig` kết hợp cấu hình context:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(classes = GreetingTestConfig.class)
class GreetingServiceTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertThat(greetingService.greet("Lan"))
                .isEqualTo("Hello, Lan");
    }
}

@Configuration
class GreetingTestConfig {

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
```

`@SpringJUnitConfig` là cách kết hợp cấu hình Spring TestContext với JUnit Jupiter. Trong một module thực tế, `GreetingService` và cấu hình có thể nằm ở package hoặc file riêng; phần quan trọng ở đây là dependency `spring-test` cung cấp tích hợp Spring, còn JUnit Jupiter cung cấp test engine và API.

## 7. Xác minh dependency đã được căn chỉnh

Khi test không chạy hoặc xuất hiện lỗi liên quan đến classpath, hãy xem dependency graph trước khi thay đổi phiên bản một cách phỏng đoán.

### 7.1. Với Maven

Lệnh sau hiển thị các dependency kiểm thử thuộc những nhóm Spring và JUnit:

```bash
mvn dependency:tree -Dscope=test -Dincludes=org.springframework,org.springframework.boot,org.junit,org.junit.jupiter,org.junit.platform
```

Quan sát các điểm sau:

- Các module `org.springframework` có cùng phiên bản Spring Framework theo BOM đã chọn.
- `spring-boot-test` và `spring-boot-test-autoconfigure` thuộc phiên bản Spring Boot của dự án.
- JUnit Jupiter API, Params và Engine không bị kéo về các phiên bản khác nhau ngoài dự kiến.
- JUnit Platform Launcher và các module Platform khác không bị xung đột bởi dependency bắc cầu.
- Không có một dependency cũ vô tình đưa JUnit 4 hoặc một JUnit Jupiter version khác vào test classpath.

Có thể dùng `mvn help:effective-pom` để kiểm tra dependency management và plugin configuration cuối cùng sau khi Maven hợp nhất parent POM, BOM và cấu hình module.

### 7.2. Với Gradle

Kiểm tra dependency thực tế trên test runtime classpath:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Để tìm lý do một dependency được chọn ở phiên bản cụ thể, dùng `dependencyInsight`:

```bash
./gradlew dependencyInsight \
    --dependency junit-jupiter-api \
    --configuration testRuntimeClasspath

./gradlew dependencyInsight \
    --dependency junit-jupiter-engine \
    --configuration testRuntimeClasspath

./gradlew dependencyInsight \
    --dependency spring-test \
    --configuration testRuntimeClasspath
```

Gradle sẽ hiển thị phiên bản được chọn, dependency nào yêu cầu phiên bản đó và quy tắc nào đã ảnh hưởng đến quá trình chọn phiên bản. Điều này hữu ích khi một thư viện khác kéo theo phiên bản JUnit hoặc Spring không mong muốn.

Sau khi kiểm tra graph, chạy test:

```bash
./gradlew test
```

Với Maven:

```bash
mvn test
```

Không nên sửa dependency chỉ vì nhìn thấy nhiều phiên bản trong cache hoặc log tải xuống. Cần dựa vào dependency graph của đúng configuration đang chạy và xác định xung đột thực tế trên classpath.

## 8. Các lỗi cấu hình thường gặp

### 8.1. Test biên dịch được nhưng Gradle không tìm thấy test

Nguyên nhân thường gặp là task `test` chưa bật JUnit Platform hoặc cấu hình engine không có trên runtime classpath.

Với Gradle, xác nhận có:

```groovy
tasks.named('test') {
    useJUnitPlatform()
}
```

Đồng thời xác nhận dependency `junit-jupiter` hoặc `junit-jupiter-engine` có mặt trong test runtime classpath.

### 8.2. Không tìm thấy TestEngine hoặc test không được thực thi

Nếu chỉ khai báo JUnit Jupiter API, mã test có thể biên dịch nhưng không có engine để chạy. Dùng dependency tổng hợp `org.junit.jupiter:junit-jupiter` hoặc khai báo cả API và Engine theo cùng bộ phiên bản.

Với một số cấu hình Gradle và công cụ phát triển, có thể cần `junit-platform-launcher` ở `testRuntimeOnly`. Hãy kiểm tra yêu cầu của phiên bản build tool đang dùng trước khi thêm dependency này.

### 8.3. Không tìm thấy `SpringExtension`

`SpringExtension` thuộc artifact `spring-test`. Nếu chỉ khai báo JUnit Jupiter mà không có Spring Test, compiler sẽ không tìm thấy lớp này. Với Spring Boot, `spring-boot-starter-test` thường đã cung cấp dependency cần thiết; với dự án Spring Framework độc lập, cần khai báo `spring-test`.

### 8.4. `NoSuchMethodError` hoặc `NoClassDefFoundError`

Lỗi liên kết class thường xuất hiện khi một phần của thư viện được biên dịch với API khác phiên bản đang có lúc chạy. Hãy kiểm tra đồng thời JUnit Jupiter API, Engine, Params, Platform và các module Spring Framework.

Không nên chỉ thêm lại dependency bị thiếu với một phiên bản ngẫu nhiên. Hãy xác định dependency nào đã kéo phiên bản không tương thích, sau đó điều chỉnh BOM hoặc constraint ở đúng cấp quản lý.

### 8.5. Nhầm annotation JUnit 4 với JUnit Jupiter

Hai import sau thuộc hai hệ khác nhau:

```java
import org.junit.Test;                 // JUnit 4
import org.junit.jupiter.api.Test;     // JUnit Jupiter
```

Một lớp test dùng `org.junit.Test` không tự trở thành test Jupiter chỉ vì dự án đã thêm `junit-jupiter`. Nếu cần chạy test JUnit 4, phải có engine tương ứng như Vintage hoặc chuyển test sang Jupiter một cách có chủ đích.

### 8.6. Thêm nhiều phiên bản Spring Test bằng tay

Nếu `spring-test` khác phiên bản với `spring-core` hoặc `spring-context`, Spring TestContext có thể gặp lỗi runtime. Với Spring Boot, bỏ phiên bản riêng và dùng BOM Boot. Với Spring Framework độc lập, dùng Spring Framework BOM cho toàn bộ module Spring.

### 8.7. Nhầm lỗi khởi tạo context với lỗi dependency JUnit

Thông báo `Failed to load ApplicationContext` không đồng nghĩa JUnit bị lệch phiên bản. Nguyên nhân có thể là bean thiếu, cấu hình sai, datasource không kết nối được, profile không phù hợp hoặc lỗi khởi tạo ứng dụng. Hãy đọc nguyên nhân gốc trong stack trace trước khi thay đổi dependency kiểm thử.

## 9. Quản lý dependency trong dự án nhiều module

Với Gradle multi-project hoặc Maven multi-module, nên quản lý phiên bản tại cấp root hoặc một convention plugin dùng chung. Các module kiểm thử không nên tự chọn một phiên bản JUnit khác nhau nếu không có yêu cầu rõ ràng.

Một cấu trúc có thể tổ chức như sau:

```text
root project
├── dependency management / version catalog
├── module-a
│   └── testImplementation: spring-boot-starter-test
├── module-b
│   └── testImplementation: spring-boot-starter-test
└── module-c
    └── testImplementation: junit-jupiter (nếu chỉ là module Java thuần)
```

Các module Spring Boot dùng chung phiên bản Boot BOM. Module Java thuần có thể dùng JUnit BOM mà không phải kéo toàn bộ starter Spring Boot. Cách này giữ dependency ở mức cần thiết cho từng module nhưng vẫn có quy tắc phiên bản tập trung.

Với Maven, khai báo BOM trong parent POM hoặc một BOM nội bộ rồi để các module con kế thừa. Với Gradle, có thể dùng version catalog, convention plugin hoặc khai báo platform ở cấu hình dùng chung. Khi cập nhật phiên bản, cần kiểm tra dependency graph của từng module vì một module có thể có dependency bắc cầu riêng.

## 10. Quy tắc thực hành khi nâng cấp JUnit hoặc Spring Test

Khi nâng cấp phiên bản, nên thực hiện theo thứ tự có thể kiểm chứng:

1. Xác định dự án dùng Spring Boot hay Spring Framework độc lập và tìm BOM đang quản lý dependency.
2. Kiểm tra phiên bản Spring Boot/Spring Framework hiện tại cùng phiên bản JUnit Jupiter và Platform được chọn.
3. Ưu tiên nâng phiên bản Spring Boot nếu mục tiêu là nhận một bộ dependency Spring và JUnit đã được kiểm thử cùng nhau.
4. Nếu chỉ cần nâng JUnit, kiểm tra tương thích với Spring Test, sau đó cập nhật cả JUnit BOM hoặc một cơ chế quản lý thống nhất.
5. Kiểm tra dependency graph của test runtime để tìm phiên bản bị override hoặc kéo vào ngoài dự kiến.
6. Chạy test ở máy phát triển và CI, bao gồm các test tích hợp sử dụng Spring context.
7. Xóa dependency trùng lặp hoặc phiên bản khai báo thủ công đã không còn cần thiết.

Khi ghi nhận cấu hình trong tài liệu dự án, nên nói rõ dependency nào đến từ starter, BOM nào quản lý phiên bản và task nào chạy test trên JUnit Platform. Điều này giúp thành viên mới hiểu vì sao module không cần khai báo phiên bản JUnit riêng và giảm nguy cơ vô tình tạo ra một bộ dependency lệch nhau.

Thiết lập dependency kiểm thử đúng nghĩa là bảo đảm đủ API để biên dịch, đủ engine để thực thi, có Spring Test khi cần tích hợp với Spring và có một quy tắc quản lý phiên bản rõ ràng. Trong Spring Boot, starter cùng BOM thường giải quyết phần lớn công việc đó. Trong dự án Spring Framework độc lập, hãy dùng Spring Framework BOM và JUnit BOM riêng, giữ các module trong từng hệ sinh thái đồng bộ và xác minh kết quả qua dependency graph thực tế.

# Phụ thuộc Servlet, reactive và thư viện phụ trợ theo phiên bản Spring

Spring Test cung cấp các công cụ kiểm thử cho nhiều kiểu ứng dụng Spring. Một ứng dụng Servlet thường dùng Spring MVC và `MockMvc`; một ứng dụng reactive thường dùng Spring WebFlux và `WebTestClient`. Cả hai cùng dựa vào `spring-test`, nhưng cần các module web và thư viện phụ trợ khác nhau trên classpath. Chọn dependency đúng theo stack và phiên bản Spring giúp test biên dịch được, khởi tạo đúng môi trường và chạy ổn định.

Khi cấu hình, cần phân biệt ba nhóm dependency: module Spring mà ứng dụng thực sự sử dụng, thư viện kiểm thử chỉ cần trong test classpath và thành phần máy chủ hoặc HTTP client cần cho những bài kiểm thử chạy qua mạng. `spring-boot-starter-test` cung cấp bộ công cụ kiểm thử phổ biến, nhưng không tự quyết định ứng dụng là Servlet hay Reactive và cũng không thay thế starter web của ứng dụng.

## 1. Phân biệt các lớp dependency

Một dự án Spring có thể cần các thành phần sau:

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Spring Test chung | `org.springframework:spring-test` | Spring TestContext Framework, `SpringExtension`, `MockMvc`, `WebTestClient` và các tiện ích mock |
| Servlet/MVC | `org.springframework:spring-webmvc` | DispatcherServlet, controller MVC, cấu hình handler và hạ tầng web Servlet |
| Servlet API | `jakarta.servlet:jakarta.servlet-api` hoặc `javax.servlet:javax.servlet-api` | Các interface Servlet mà Spring MVC và mock request/response sử dụng |
| Reactive/WebFlux | `org.springframework:spring-webflux` | WebFlux, reactive controller, WebHandler và tích hợp Reactor |
| Reactive Streams | `io.projectreactor:reactor-core` | `Mono`, `Flux` và runtime reactive; thường được kéo theo bởi WebFlux |
| Reactive test | `io.projectreactor:reactor-test` | `StepVerifier`, `TestPublisher` và tiện ích kiểm thử Reactor |
| Máy chủ HTTP | Tomcat, Jetty, Undertow hoặc Reactor Netty | Tiếp nhận request thật trong kiểm thử chạy qua cổng HTTP |
| Thư viện kiểm thử phụ trợ | JUnit Jupiter, Mockito, AssertJ, JSONassert, JsonPath | Test engine, mock, assertion và kiểm tra payload |

`spring-test` là module kiểm thử chung. Nó cung cấp API của các công cụ như `MockMvc` và `WebTestClient`, nhưng để khởi tạo một ứng dụng web cần có module web tương ứng. Ví dụ, `MockMvc` kiểm tra luồng Servlet/MVC nên test context cần Spring MVC; `WebTestClient` kiểm tra WebFlux nên context cần Spring WebFlux.

Các thư viện máy chủ chỉ cần thiết khi test thực sự khởi chạy server. Một bài `MockMvc` chạy trong mock Servlet environment không cần mở cổng TCP. Tương tự, `WebTestClient` có thể bind trực tiếp vào controller hoặc application context WebFlux mà không cần máy chủ thật. Khi kiểm thử qua HTTP tới server đang chạy, cần có server implementation và client connector phù hợp.

## 2. Chọn stack Servlet hay Reactive

### 2.1. Ứng dụng Servlet với Spring MVC

Stack Servlet thường gồm:

- `spring-webmvc` cho Spring MVC.
- Servlet API đúng namespace và phiên bản mà Spring Framework yêu cầu.
- `spring-test` cho `MockMvc` và Spring TestContext.
- Một Servlet container như Tomcat, Jetty hoặc Undertow nếu ứng dụng cần chạy server thật.

Với Spring Boot, `spring-boot-starter-web` thường đưa vào Spring MVC và embedded Tomcat mặc định. Starter này thuộc dependency của ứng dụng. `spring-boot-starter-test` được thêm ở test scope để cung cấp JUnit, Mockito và Spring Boot Test.

`MockMvc` mô phỏng xử lý request qua `DispatcherServlet` mà không cần khởi động một HTTP server. Nó phù hợp để kiểm tra mapping, binding, validation, exception handling, filter/interceptor được cấu hình trong test context và response HTTP. Nếu mục tiêu là kiểm tra cấu hình server thật, cổng mạng, TLS hoặc tích hợp container, cần dùng một bài kiểm thử với server đang chạy.

### 2.2. Ứng dụng Reactive với Spring WebFlux

Stack Reactive thường gồm:

- `spring-webflux` cho WebFlux.
- `reactor-core` cho `Mono` và `Flux`; module này thường được khai báo bắc cầu bởi WebFlux.
- `spring-test` cho `WebTestClient` và các tiện ích kiểm thử Spring.
- `reactor-test` nếu cần kiểm tra publisher bằng `StepVerifier` hoặc `TestPublisher`.
- Một HTTP server như Reactor Netty nếu cần chạy ứng dụng thật qua cổng mạng.

Với Spring Boot, `spring-boot-starter-webflux` đưa vào WebFlux và mặc định sử dụng Reactor Netty làm server khi không thay thế bằng server khác. `spring-boot-starter-test` cung cấp các công cụ kiểm thử Spring và JUnit. `reactor-test` là dependency riêng khi test cần `StepVerifier`.

`WebTestClient` có thể bind vào controller hoặc WebFlux application context để kiểm tra request và response mà không cần server thật. Nó cũng có thể kết nối tới một server đang chạy để kiểm thử toàn bộ HTTP stack. Vì vậy, hãy xác định test đang dùng kiểu bind nào trước khi thêm dependency server hoặc connector.

### 2.3. Không thêm cả hai web stack một cách tùy tiện

Một ứng dụng có thể có cả `spring-webmvc` và `spring-webflux` trên classpath, nhưng điều đó không có nghĩa mọi test đều cần cả hai. Spring Boot thường ưu tiên cấu hình MVC khi cả MVC và WebFlux cùng xuất hiện trong một ứng dụng servlet-capable. Nếu dự án chủ ý dùng cả hai, cần hiểu rõ cách chọn application type, server và cấu hình test.

Với module chỉ kiểm thử MVC, tập trung vào `MockMvc`. Với module chỉ kiểm thử WebFlux, tập trung vào `WebTestClient` và các công cụ Reactor. Giữ classpath theo đúng kiến trúc giúp tránh việc test context tự chọn nhầm loại ứng dụng hoặc kéo theo nhiều cấu hình không liên quan.

## 3. Dependency theo thế hệ Spring

Phiên bản Spring quyết định namespace Servlet, mức Java tối thiểu và các API có sẵn. Những điểm dưới đây giúp chọn đúng họ dependency; phiên bản patch cụ thể vẫn phải lấy từ BOM của release train đang dùng.

| Thế hệ | Nền tảng web | Namespace Servlet | Lưu ý khi kiểm thử |
|---|---|---|---|
| Spring Framework 5.x / Spring Boot 2.x | Spring MVC hoặc WebFlux | `javax.servlet.*` | Dùng các dependency thuộc dòng Spring 5/Boot 2; test JUnit Jupiter cần phiên bản được BOM quản lý hoặc cấu hình riêng phù hợp |
| Spring Framework 6.x / Spring Boot 3.x | Spring MVC hoặc WebFlux | `jakarta.servlet.*` | Yêu cầu Java 17 trở lên; hệ sinh thái Servlet chuyển sang Jakarta EE namespace |
| Spring Framework 7.x / Spring Boot 4.x | Spring MVC hoặc WebFlux | `jakarta.servlet.*` | Tiếp tục dùng Jakarta namespace; chọn dependency theo BOM của dòng phát hành tương ứng |

Không trộn `spring-test` 5.x với `spring-webmvc` 6.x hoặc `spring-webflux` 7.x. Các module Spring Framework như `spring-core`, `spring-context`, `spring-web`, `spring-webmvc`, `spring-webflux` và `spring-test` nên cùng một phiên bản Framework. Spring Boot quản lý một bộ phiên bản Spring Framework, JUnit và thư viện phụ trợ đã được chọn cho release train đó.

### 3.1. Khác biệt javax và jakarta

Spring Framework 5.x thuộc thế hệ dùng Java EE namespace `javax.servlet`. Từ Spring Framework 6.x, các API Jakarta EE được dùng với namespace `jakarta.servlet`. Spring Boot 2.x thuộc thế hệ `javax`; Spring Boot 3.x chuyển sang `jakarta` cùng Spring Framework 6.

Hai API có tên class tương tự nhưng nằm trong package khác nhau. Một class biên dịch với `javax.servlet.http.HttpServletRequest` không thể được truyền thay cho `jakarta.servlet.http.HttpServletRequest`. Vì vậy, không thể sửa lỗi bằng cách thêm cả hai Servlet API vào classpath rồi kỳ vọng chúng thay thế cho nhau.

Ví dụ import theo hai thế hệ:

```java
// Spring Framework 5.x / Spring Boot 2.x
import javax.servlet.http.HttpServletRequest;
```

```java
// Spring Framework 6.x+ / Spring Boot 3.x+
import jakarta.servlet.http.HttpServletRequest;
```

Khi nâng từ Boot 2 lên Boot 3, cần chuyển code import và dependency Servlet sang Jakarta. Các thư viện kiểm thử, filter, servlet container và thư viện bên thứ ba cũng phải hỗ trợ namespace Jakarta. Chỉ nâng phiên bản `spring-test` trong khi giữ Servlet API cũ sẽ tạo ra lỗi biên dịch hoặc lỗi liên kết class.

### 3.2. JUnit và thư viện phụ trợ cũng cần được căn chỉnh

JUnit Jupiter có phiên bản riêng với Spring Framework. Trong ứng dụng Boot, hãy ưu tiên BOM Boot để quản lý JUnit, Mockito và các thư viện test. Trong dự án Spring Framework độc lập, quản lý Spring Framework BOM và JUnit BOM riêng. Với WebFlux, quản lý `reactor-core`, `reactor-test` và Reactor Netty theo BOM hoặc release train tương thích.

Không suy ra phiên bản JUnit hoặc Reactor từ số phiên bản Spring. Hãy xem dependency management thực tế của phiên bản Boot/Framework đã chọn. Điều này đặc biệt quan trọng khi nâng một thư viện riêng lẻ, vì API có thể biên dịch nhưng engine hoặc connector lại không tương thích lúc chạy.

## 4. Cấu hình Maven cho Spring Boot

### 4.1. Ứng dụng Servlet/MVC

Với Maven kế thừa `spring-boot-starter-parent`, khai báo web starter ở dependency chính và test starter ở scope `test`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`spring-boot-starter-web` đưa Spring MVC và server mặc định vào ứng dụng. `spring-boot-starter-test` cung cấp `spring-test`, JUnit Jupiter, Mockito và các thư viện assertion thường dùng. Không cần khai báo thêm `spring-test`, `spring-webmvc` hoặc Servlet API cùng phiên bản bằng tay nếu starter đã quản lý chúng.

### 4.2. Ứng dụng Reactive/WebFlux

Với ứng dụng WebFlux:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

WebFlux starter cung cấp hạ tầng reactive và server mặc định của Boot. `reactor-test` bổ sung `StepVerifier` để kiểm tra publisher theo tín hiệu, demand, completion và error. Nếu test chỉ dùng `WebTestClient` bind vào controller/context, không cần thêm server riêng ngoài những dependency mà ứng dụng đã cần.

### 4.3. Không dùng Spring Boot parent

Nếu dự án kế thừa parent POM riêng, có thể import `spring-boot-dependencies` trong `dependencyManagement` rồi khai báo các starter mà không ghi phiên bản tại từng dependency. BOM quản lý phiên bản; nó không tự áp dụng toàn bộ plugin configuration của Spring Boot parent. Maven Surefire và cấu hình test cần được quản lý riêng nếu parent không cung cấp sẵn.

Ví dụ cấu trúc dependency vẫn giống hai phần trên. Điều cần bảo đảm là property phiên bản Boot được khai báo một lần, BOM được import đúng scope và các module không tự override phiên bản Spring hoặc JUnit.

## 5. Cấu hình Maven cho Spring Framework độc lập

Với dự án không dùng Boot, khai báo rõ module web theo kiến trúc ứng dụng, `spring-test` cho kiểm thử và các BOM để quản lý phiên bản.

### 5.1. Servlet/MVC

Ví dụ cho Spring Framework 6.x:

```xml
<properties>
    <spring-framework.version>6.2.0</spring-framework.version>
    <junit.version>5.11.0</junit.version>
    <servlet-api.version>6.0.0</servlet-api.version>
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
        <artifactId>spring-webmvc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>${servlet-api.version}</version>
        <scope>provided</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là ví dụ minh họa cho một ứng dụng Servlet dùng Jakarta Servlet. `provided` phù hợp khi Servlet container bên ngoài cung cấp API lúc chạy; dependency vẫn có mặt trên test classpath của Maven. Nếu Servlet API chỉ được dùng trong test code, có thể cân nhắc scope `test`. Phiên bản Servlet API phải tương thích với container và baseline Spring đã chọn.

Với Spring Framework 5.x, dùng `javax.servlet:javax.servlet-api` và namespace `javax.servlet.*`, đồng thời chọn Spring Framework BOM 5.x. Không dùng Jakarta Servlet API cho ứng dụng Spring 5.x chỉ để làm cho import biên dịch được.

### 5.2. Reactive/WebFlux

Ví dụ cho dự án Spring Framework độc lập dùng WebFlux:

```xml
<properties>
    <spring-framework.version>6.2.0</spring-framework.version>
    <junit.version>5.11.0</junit.version>
    <reactor.version>2024.0.0</reactor.version>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-bom</artifactId>
            <version>${reactor.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-webflux</artifactId>
    </dependency>
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
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Các property phiên bản trong ví dụ chỉ minh họa cách tổ chức; dự án cần chọn một Reactor BOM tương thích với dòng Spring Framework và Java đang dùng. Nếu kiểm thử WebFlux qua server thật, cần thêm HTTP server implementation phù hợp, chẳng hạn Reactor Netty. Nếu chỉ bind `WebTestClient` vào context hoặc controller, test không cần khởi chạy server thật.

Spring Framework BOM quản lý các module Spring. JUnit BOM quản lý các module JUnit. Reactor BOM quản lý Reactor Core, Reactor Test và các module Reactor liên quan. Giữ các hệ sinh thái riêng trong đúng BOM giúp tránh giả định rằng một số phiên bản Spring có thể thay thế trực tiếp cho số phiên bản Reactor hoặc JUnit.

## 6. Cấu hình Gradle cho Spring Boot

### 6.1. Servlet/MVC

Với ứng dụng Boot MVC:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 6.2. Reactive/WebFlux

Với ứng dụng Boot WebFlux:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Khi dùng Spring Boot Gradle Plugin cùng plugin dependency management, Boot BOM thường được import tự động. Nếu dự án dùng native Gradle platform, hãy khai báo `platform("org.springframework.boot:spring-boot-dependencies:${springBootVersion}")` trong configuration thích hợp trước khi khai báo các starter. Không ghi version riêng cho các module đã được BOM quản lý.

## 7. Cấu hình Gradle cho Spring Framework độc lập

Với Spring Framework độc lập, có thể dùng native BOM support để quản lý các nhóm dependency:

### 7.1. Servlet/MVC

```groovy
dependencies {
    implementation platform("org.springframework:spring-framework-bom:${springFrameworkVersion}")
    implementation 'org.springframework:spring-webmvc'

    testImplementation 'org.springframework:spring-test'
    testImplementation platform("org.junit:junit-bom:${junitVersion}")
    testImplementation 'org.junit.jupiter:junit-jupiter'

    // Spring Framework 6.x+; use javax.servlet API for Spring 5.x.
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`compileOnly` phù hợp khi container bên ngoài cung cấp Servlet API lúc chạy. Nếu chỉ test code cần API, có thể dùng `testImplementation`. Với Spring Boot, starter web đã quản lý dependency web và server nên thường không cần khai báo Servlet API riêng.

### 7.2. Reactive/WebFlux

```groovy
dependencies {
    implementation platform("org.springframework:spring-framework-bom:${springFrameworkVersion}")
    implementation 'org.springframework:spring-webflux'

    implementation platform("io.projectreactor:reactor-bom:${reactorVersion}")

    testImplementation 'org.springframework:spring-test'
    testImplementation platform("org.junit:junit-bom:${junitVersion}")
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu test kết nối đến server thật, thêm server implementation tương thích, ví dụ `io.projectreactor.netty:reactor-netty-http` ở `runtimeOnly` hoặc configuration phù hợp. Đối với test bind vào WebFlux context, không cần server implementation chỉ để gọi `WebTestClient`.

Các biến `springFrameworkVersion`, `junitVersion` và `reactorVersion` phải được định nghĩa trong `gradle.properties`, version catalog hoặc convention plugin. Khi sử dụng BOM, hãy để BOM quản lý version cho artifact thuộc hệ sinh thái tương ứng.

## 8. Chọn công cụ kiểm thử theo loại ứng dụng

### 8.1. MockMvc cho Servlet/MVC

`MockMvc` kiểm tra request qua Spring MVC mà không mở socket. Có thể dùng test slice `@WebMvcTest` để tải phần MVC cần thiết, hoặc `@SpringBootTest` kết hợp `@AutoConfigureMockMvc` nếu cần context rộng hơn.

Ví dụ:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void returnsAcceptedForValidRequest() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""{"quantity": 2}"""))
                .andExpect(status().isAccepted());
    }
}
```

Các import và mock bean annotation cần theo phiên bản Spring Boot của dự án. Ở các dòng mới, annotation thay thế cho `@MockBean` có thể được cung cấp từ Spring Framework. `MockMvc` phù hợp khi cần kiểm tra mapping, validation, converter, exception handler, filter hoặc response MVC.

Nếu muốn xác minh ứng dụng chạy trên embedded server, có thể dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và một HTTP client. Khi đó, test cần server implementation trong runtime classpath. Đây là bài kiểm thử qua mạng và có phạm vi rộng hơn MockMvc.

### 8.2. WebTestClient cho WebFlux

`WebTestClient` có API fluent tương tự WebClient nhưng được thiết kế cho kiểm thử. Nó hỗ trợ bind trực tiếp vào controller, application context hoặc kết nối server đang chạy.

Ví dụ kiểm thử controller WebFlux bằng mock binding:

```java
@Test
void returnsGreetingFromReactiveController() {
    WebTestClient client = WebTestClient
            .bindToController(new GreetingController())
            .build();

    client.get()
            .uri("/greeting")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Hello");
}

@RestController
class GreetingController {

    @GetMapping("/greeting")
    Mono<String> greeting() {
        return Mono.just("Hello");
    }
}
```

Test này cần `spring-webflux`, `spring-test` và Reactor trên test classpath. Nó không cần server TCP vì client bind trực tiếp vào controller. Khi dùng `@WebFluxTest`, Spring Boot có thể tự cấu hình `WebTestClient` để inject vào test.

Nếu muốn test qua HTTP thật, có thể dùng `WebTestClient.bindToServer()` với một server đã chạy. Khi đó, cần một HTTP client connector phù hợp và server implementation đang phục vụ ứng dụng. Với Boot WebFlux mặc định, Reactor Netty thường đảm nhiệm phần server.

### 8.3. StepVerifier cho publisher Reactor

`WebTestClient` kiểm tra hợp đồng HTTP; `StepVerifier` kiểm tra trực tiếp chuỗi tín hiệu của `Mono` hoặc `Flux`. Hai công cụ bổ sung cho nhau.

```java
@Test
void emitsValuesAndCompletes() {
    Flux<String> names = Flux.just("Lan", "Minh");

    StepVerifier.create(names)
            .expectNext("Lan")
            .expectNext("Minh")
            .verifyComplete();
}
```

`StepVerifier` thuộc `reactor-test`, vì vậy module này cần được khai báo trong test scope. Có thể dùng nó để kiểm tra giá trị, thứ tự tín hiệu, lỗi, hoàn tất, timeout và hành vi backpressure theo yêu cầu của publisher.

## 9. Thư viện phụ trợ thường dùng

Không phải mọi dự án đều cần mọi thư viện test. Chọn dependency theo kiểu assertion và môi trường cần kiểm thử.

| Thư viện | Khi nào cần | Ghi chú dependency |
|---|---|---|
| JUnit Jupiter | Viết và chạy unit/integration test | API, Params và Engine cần được căn chỉnh; Boot starter thường đã cung cấp |
| Mockito | Mock, stub, verify và capture đối số | Dùng phiên bản do Boot BOM hoặc BOM riêng quản lý |
| AssertJ | Assertion fluent cho object, collection và exception | Có trong `spring-boot-starter-test` |
| Hamcrest | Matcher dùng trong assertion hoặc MockMvc | Thường có trong Boot test starter |
| JSONassert | So sánh JSON response | Hữu ích khi kiểm tra JSON contract |
| JsonPath | Truy xuất field trong JSON response | Có thể dùng với MockMvc/WebTestClient khi test cần |
| XMLUnit | So sánh và kiểm tra XML | Chỉ thêm khi ứng dụng có hợp đồng XML |
| Awaitility | Chờ điều kiện bất đồng bộ đạt trạng thái mong đợi | Dùng cho test có eventual consistency hoặc xử lý nền |
| Reactor Test | `StepVerifier`, `TestPublisher` | Cần cho kiểm thử publisher Reactor |
| Testcontainers | Chạy database, broker hoặc dịch vụ phụ trợ trong container | Chỉ thêm cho integration test cần dependency hạ tầng thật |

Với Spring Boot, `spring-boot-starter-test` đã bao gồm nhiều thư viện phổ biến như JUnit Jupiter, Mockito, AssertJ, Hamcrest, JSONassert, JsonPath, Awaitility và XMLUnit. Hãy kiểm tra dependency tree trước khi thêm một artifact trùng lặp. `reactor-test` và Testcontainers thường được khai báo riêng theo nhu cầu của module.

Đối với dự án không dùng Boot, khai báo từng thư viện ở scope test và dùng BOM phù hợp. Ví dụ, Mockito và AssertJ có thể được quản lý qua BOM hoặc version catalog riêng; không nên chọn phiên bản chỉ vì đó là bản mới nhất nếu dự án đang dùng Spring/JUnit cũ.

## 10. Phân biệt test mock và test server thật

Việc chọn dependency phụ thuộc vào mức độ tích hợp cần kiểm tra:

| Mục tiêu | Servlet/MVC | Reactive/WebFlux | Có cần server thật? |
|---|---|---|---|
| Kiểm tra controller và response mapping | `MockMvc` | `WebTestClient.bindToController(...)` | Không |
| Kiểm tra cấu hình web application context | `MockMvc` với context hoặc `@WebMvcTest` | `WebTestClient.bindToApplicationContext(...)` hoặc `@WebFluxTest` | Không |
| Kiểm tra toàn bộ ứng dụng qua cổng HTTP | HTTP client với `@SpringBootTest(RANDOM_PORT)` | `WebTestClient.bindToServer()` với server đang chạy | Có |
| Kiểm tra logic publisher | Không áp dụng cho MVC thuần | `StepVerifier` | Không |
| Kiểm tra database hoặc broker thật | Testcontainers hoặc môi trường tích hợp | Testcontainers hoặc môi trường tích hợp | Cần dịch vụ phụ trợ; không nhất thiết cần web server |

Test mock nhanh và tập trung vào hợp đồng của một lớp. Test server thật xác nhận thêm cấu hình mạng, server adapter, serialization qua HTTP thực tế và một phần hành vi triển khai. Không nên dùng server thật cho mọi trường hợp đơn giản nếu mock test đã xác nhận đủ hành vi cần bảo vệ.

## 11. Những lỗi dependency thường gặp

### 11.1. Không tìm thấy Servlet class hoặc method

Nếu gặp `ClassNotFoundException` hoặc `NoClassDefFoundError` liên quan `javax.servlet.*` hay `jakarta.servlet.*`, hãy kiểm tra thế hệ Spring và namespace của Servlet API. Spring 5.x dùng `javax`; Spring 6.x trở lên dùng `jakarta`. Kiểm tra cả container và các thư viện filter/security bên thứ ba.

### 11.2. `MockMvc` không khởi tạo được

`spring-test` có thể đã có trên classpath nhưng ứng dụng chưa có `spring-webmvc` hoặc test context chưa được cấu hình như một Servlet application. Với Boot, kiểm tra module có `spring-boot-starter-web` và test slice dùng đúng controller. Với Spring Framework độc lập, xác nhận có `spring-webmvc` và Servlet API tương thích.

### 11.3. Không tìm thấy `WebTestClient` hoặc `Mono`

`WebTestClient` nằm trong Spring Test, còn `Mono` và `Flux` đến từ Reactor Core. Kiểm tra `spring-test`, `spring-webflux` và dependency Reactor có trên test classpath. Nếu dùng Boot WebFlux, kiểm tra `spring-boot-starter-webflux` đã được khai báo.

### 11.4. `WebTestClient.bindToServer()` không kết nối được

Mock binding không cần server, nhưng `bindToServer()` cần một server đã chạy và HTTP client connector. Xác nhận ứng dụng đã khởi động, port đúng và server implementation có trong runtime classpath. Với Boot WebFlux, kiểm tra Reactor Netty hoặc server adapter mà dự án đã chọn.

### 11.5. `NoSuchMethodError` giữa các module Spring

Lỗi này thường gợi ý các module Spring không cùng phiên bản. Xem dependency tree để tìm `spring-core`, `spring-context`, `spring-web`, `spring-webmvc`, `spring-webflux` và `spring-test` có bị lệch version không. Dùng một Spring Framework BOM hoặc Boot BOM để đồng bộ.

### 11.6. Reactor Test không tìm thấy StepVerifier

`StepVerifier` thuộc `reactor-test`, không phải `spring-test` hoặc JUnit. Thêm `io.projectreactor:reactor-test` trong test scope và để Reactor BOM hoặc Boot BOM quản lý phiên bản.

### 11.7. Cả MVC và WebFlux cùng được kích hoạt

Nếu cả hai starter web cùng có mặt, Boot có thể chọn MVC theo cơ chế auto-configuration. Xem log điều kiện auto-configuration và application type để biết context đang chạy theo stack nào. Nếu module chỉ cần một stack, bỏ dependency web còn lại khỏi module để tránh cấu hình không rõ ràng.

## 12. Kiểm tra dependency graph

Khi có lỗi classpath, kiểm tra dependency thực tế của test thay vì đoán từ nội dung `pom.xml` hoặc `build.gradle`.

Với Maven:

```bash
mvn dependency:tree -Dscope=test -Dincludes=org.springframework,org.springframework.boot,org.junit,org.junit.jupiter,org.junit.platform,io.projectreactor,jakarta.servlet,javax.servlet
```

Lệnh này giúp nhìn thấy phiên bản Spring, JUnit, Reactor và Servlet API đang được giải quyết. Có thể dùng `mvn help:effective-pom` để xem BOM, parent và plugin configuration cuối cùng.

Với Gradle:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Để xác định lý do một artifact được chọn ở phiên bản cụ thể:

```bash
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency reactor-test --configuration testRuntimeClasspath
```

Sau khi dependency graph phù hợp, chạy task test của dự án (`mvn test` hoặc `./gradlew test`). Với test tích hợp qua server thật, xác nhận runtime classpath có server implementation. Với test mock binding, xác nhận module web và `spring-test` đã có mặt.

## 13. Quy tắc chọn dependency trong dự án nhiều module

Trong dự án nhiều module, mỗi module nên khai báo stack web mà nó thực sự sử dụng. Module MVC có thể dùng `spring-webmvc`; module WebFlux dùng `spring-webflux`; module Java thuần chỉ cần JUnit và thư viện test cần thiết. Cấu hình dùng chung ở root nên quản lý version qua BOM hoặc version catalog để các module không tự kéo các bản Spring khác nhau.

Với Spring Boot, dùng cùng một Boot release train cho các module thuộc cùng ứng dụng và để Boot BOM quản lý các dependency liên quan. Với Spring Framework độc lập, dùng Spring Framework BOM cho module Spring, JUnit BOM cho JUnit và Reactor BOM cho Reactor khi cần. Không dùng một version catalog chứa số phiên bản rời rạc mà không thể hiện rõ nhóm nào thuộc release train nào.

Dependency kiểm thử nên nằm ở `testImplementation` hoặc Maven scope `test`. Servlet API có thể là `provided`/`compileOnly` khi container bên ngoài cung cấp, còn server embedded của Boot thường được starter web quản lý. Reactor Netty chỉ cần khai báo rõ khi ứng dụng hoặc test server thật cần nó; `reactor-test` thuộc test scope.

Khi nâng cấp Spring, hãy kiểm tra đồng thời Java baseline, namespace Servlet, server/container, Spring Test, JUnit và các thư viện phụ trợ. Với chuyển đổi Spring 5 lên Spring 6, thay đổi `javax` sang `jakarta` là một thay đổi nền tảng cần được xử lý xuyên suốt code, dependency và môi trường chạy. Khi dependency graph được căn chỉnh theo đúng stack và release train, `MockMvc`, `WebTestClient` và các thư viện test phụ trợ sẽ hoạt động trong đúng môi trường mà bài kiểm thử cần mô phỏng.

# Phân biệt có thư viện web trên classpath với loại ApplicationContext đang chạy

## 1. Mục tiêu và câu hỏi cốt lõi

Trong Spring Boot, hai nhận định sau **không tương đương**:

1. “Ứng dụng có thư viện Spring MVC, Spring WebFlux hoặc Servlet API trên **classpath**.”
2. “`ApplicationContext` hiện đang chạy là một **web application context** theo mô hình Servlet hoặc Reactive.”

Một ứng dụng CLI/batch có thể mang theo `spring-webmvc` và `spring-webflux` do dependency bắc cầu nhưng vẫn chạy bằng context **không phải web**. Ngược lại, một ứng dụng Spring MVC có thể chứa thư viện WebFlux chỉ để sử dụng `WebClient`; điều đó không làm các điều kiện dành riêng cho **reactive web server** tự động khớp.

Vì vậy cần phân biệt ít nhất ba tầng:

- **Classpath**: thư viện/lớp nào *có thể được load*? Ví dụ `DispatcherServlet`, `DispatcherHandler`, `jakarta.servlet.Servlet`.
- **Lựa chọn loại ứng dụng** (`WebApplicationType`): Spring Boot dự kiến khởi tạo ứng dụng `NONE`, `SERVLET` hay `REACTIVE`? Đây là quyết định khi bootstrap, mặc định được suy luận từ classpath nhưng có thể cấu hình lại.
- **ApplicationContext thực sự đang đánh giá điều kiện**: context/environment hiện tại có mang đặc trưng web Servlet/Reactive hay không? `@ConditionalOnWebApplication` kiểm tra tầng này; một kiểu context do test runner hoặc code khác tạo không nhất thiết tuân theo suy luận mặc định của `SpringApplication`.

Sau bài này, bạn sẽ biết nên chọn `@ConditionalOnClass`, `@ConditionalOnWebApplication` hay tổ hợp cả hai; dự đoán trường hợp cùng có MVC và WebFlux; phân biệt ứng dụng không web với web server không mở cổng; và xây dựng phép thử tái hiện ba loại context. Phạm vi kỹ thuật: Java 17+, Spring Boot 3.3.x, Spring Framework 6.1.x.

## 2. Classpath nói gì và không nói gì?

Classpath là tập các đường dẫn/JAR mà classloader có thể tra cứu. Nếu dependency `spring-webmvc` hiện diện thì `org.springframework.web.servlet.DispatcherServlet` thường load được; nếu `spring-webflux` hiện diện thì `org.springframework.web.reactive.DispatcherHandler` thường load được.

`@ConditionalOnClass` chỉ quan tâm đến **sự hiện diện của các lớp chỉ định**; `@ConditionalOnMissingClass` làm điều ngược lại. Chúng **không hỏi**:

- `DispatcherServlet` có được dùng để xử lý HTTP request hay không?
- Một Servlet/Reactive `ApplicationContext` có đang tồn tại hay không?
- Có web server nào đã khởi động hoặc có cổng TCP nào đang lắng nghe không?
- `DispatcherHandler` xuất hiện vì server WebFlux hay chỉ vì thư viện client/reactive được thêm làm dependency?

Ví dụ:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name =
        "org.springframework.web.servlet.DispatcherServlet")
class MvcLibraryAvailableConfiguration {
    // Được xét khi class DispatcherServlet hiện diện.
    // Chưa có bằng chứng ứng dụng đang chạy với Servlet context.
}
```

Trong một ứng dụng **non-web** nhưng vẫn phụ thuộc `spring-webmvc`, cấu hình trên có thể được kích hoạt. Tương tự:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name =
        "org.springframework.web.reactive.DispatcherHandler")
class WebFluxLibraryAvailableConfiguration {
    // Classpath có WebFlux, không có nghĩa runtime là REACTIVE.
}
```

Lưu ý về điều kiện lớp khi viết thư viện tùy chọn: Spring Boot đọc metadata annotation (thường không cần load lớp chỉ định) trên `@Configuration`. Tuy nhiên, nếu `@Bean` có **return type** là một lớp tùy chọn vắng mặt, JVM có thể phải xử lý chữ ký phương thức trước khi condition ngăn được nó. Khi ấy hãy cô lập phần dùng lớp tùy chọn trong **nested `@Configuration`** có `@ConditionalOnClass` ở cấp lớp; tránh dùng condition trên mỗi method như biện pháp bảo đảm an toàn class loading.

## 3. Loại ứng dụng dự định khởi chạy: `WebApplicationType`

Spring Boot 3.3 có enum `org.springframework.boot.WebApplicationType`:

| Giá trị | Ý nghĩa khi `SpringApplication` khởi động thông thường | Context điển hình |
| --- | --- | --- |
| `NONE` | Ứng dụng không chạy như một web application; không tạo embedded HTTP server | `AnnotationConfigApplicationContext` |
| `SERVLET` | Ứng dụng web dùng mô hình Servlet và, khi chạy dạng executable JAR theo cấu hình thông thường, có servlet web server | `AnnotationConfigServletWebServerApplicationContext` |
| `REACTIVE` | Ứng dụng web theo mô hình Reactive và, khi cấu hình đầy đủ, có reactive web server | `AnnotationConfigReactiveWebServerApplicationContext` |

Đây là **lựa chọn bootstrap của Spring Boot**, không phải phép kiểm tra “JAR web có mặt” ở mọi thời điểm. Với một `SpringApplication` sử dụng suy luận mặc định:

- Chỉ có bộ thư viện cần thiết cho Spring MVC → thường chọn `SERVLET`.
- Có bộ thư viện WebFlux nhưng không có các chỉ dấu MVC/Jersey được Boot ưu tiên → thường chọn `REACTIVE`.
- Cả `spring-boot-starter-web` và `spring-boot-starter-webflux` → mặc định **SERVLET / Spring MVC** được ưu tiên. Trường hợp rất phổ biến: thêm WebFlux để dùng `WebClient` trong ứng dụng MVC.
- Thiếu các chỉ dấu cần thiết của ứng dụng web → có thể chọn `NONE`, dù classpath vẫn có vài thành phần web riêng lẻ.

**Không suy luận `SERVLET` chỉ vì thấy `jakarta.servlet.Servlet`, cũng không suy luận `REACTIVE` chỉ vì thấy Reactor/`Mono`.** Boot xem xét các class chỉ dấu cụ thể và quy tắc ưu tiên của phiên bản đang dùng. Mục đích thực tế là biết loại context sẽ được tạo, không ghi nhớ một điều kiện classpath đơn lẻ rồi áp dụng cho mọi phiên bản.

### 3.1. Ép lựa chọn thay vì để Boot suy luận

Trong `application.properties`:

```properties
spring.main.web-application-type=none
```

hoặc:

```properties
spring.main.web-application-type=reactive
```

hoặc:

```properties
spring.main.web-application-type=servlet
```

Đường lập trình tương ứng:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

SpringApplication app = new SpringApplication(MyApplication.class);
app.setWebApplicationType(WebApplicationType.REACTIVE);
app.run(args);
```

Đây là **đoạn minh họa**: giả sử `MyApplication` và `args` đã có. Việc ép kiểu ứng dụng chỉ thay đổi **cách khởi động/context được lựa chọn**, không tự bổ sung class, bean, server factory hoặc thư viện còn thiếu. Nếu ép `REACTIVE` nhưng thiếu dependency hỗ trợ reactive web server, ứng dụng có thể không khởi động thành công. Với `NONE`, classpath vẫn có thể chứa `DispatcherServlet` và `DispatcherHandler`.

Có thể đặt `spring.main.web-application-type=reactive` trong `@SpringBootTest(properties = "...")` khi cần thử WebFlux trên classpath có cả MVC. Đó là một quyết định về loại ứng dụng trong quá trình xây dựng context test; đừng lẫn nó với một property tùy ý mà `@ConditionalOnWebApplication` đọc để “đoán” kết quả.

## 4. `@ConditionalOnWebApplication` kiểm tra context đang chạy

`org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication` và `@ConditionalOnNotWebApplication` là **điều kiện dựa trên bản chất context/environment**, khác bản chất với `@ConditionalOnClass`.

`@ConditionalOnWebApplication` nhận `type`:

- `Type.ANY` (mặc định): khớp với Servlet **hoặc** Reactive web application.
- `Type.SERVLET`: chỉ khớp với servlet web application.
- `Type.REACTIVE`: chỉ khớp với reactive web application.

Theo Spring Boot 3.3, cơ chế nhận diện **Servlet web application** có thể dựa vào `WebApplicationContext`, scope `session` hoặc `ConfigurableWebEnvironment`; cơ chế nhận diện **Reactive web application** dựa vào `ReactiveWebApplicationContext` hoặc `ConfigurableReactiveWebEnvironment`. Bởi vậy, điều kiện này không nên được mô tả giản lược thành đúng một câu `context instanceof SomeConcreteClass`. Trong ứng dụng Boot điển hình, các tín hiệu ấy phù hợp với ba kiểu context nói trên.

Ví dụ các cấu hình phân loại:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication.Type;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(type = Type.SERVLET)
class ServletRuntimeConfiguration {
    // Chỉ cấu hình khi context hiện tại mang đặc trưng Servlet web.
}

@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(type = Type.REACTIVE)
class ReactiveRuntimeConfiguration {
    // Chỉ cấu hình khi context hiện tại mang đặc trưng Reactive web.
}
```

Ví dụ cho logic chỉ chạy trong ứng dụng không web:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
class CommandLineRuntimeConfiguration {
    // Không khớp trong web application context.
}
```

Điểm then chốt: nếu `@ConditionalOnClass(DispatcherServlet.class)` **đúng** nhưng `@ConditionalOnWebApplication(type = SERVLET)` **sai**, đó là kết quả bình thường khi dependency MVC hiện diện nhưng context không phải Servlet. Ngược lại, nếu có WebFlux trên classpath nhưng context là Servlet, `@ConditionalOnWebApplication(type = REACTIVE)` vẫn **sai**.

### 4.1. Bảng quyết định: classpath cố định, context thay đổi

Giả sử cả `DispatcherServlet` và `DispatcherHandler` đều có mặt trên **cùng một classpath**; không đổi dependency giữa các hàng.

| Điều kiện | Context NONE | Context SERVLET | Context REACTIVE |
| --- | :---: | :---: | :---: |
| `@ConditionalOnClass(DispatcherServlet.class)` | ✅ | ✅ | ✅ |
| `@ConditionalOnClass(DispatcherHandler.class)` | ✅ | ✅ | ✅ |
| `@ConditionalOnWebApplication` (ANY) | ❌ | ✅ | ✅ |
| `@ConditionalOnWebApplication(type=SERVLET)` | ❌ | ✅ | ❌ |
| `@ConditionalOnWebApplication(type=REACTIVE)` | ❌ | ❌ | ✅ |
| `@ConditionalOnNotWebApplication` | ✅ | ❌ | ❌ |

Bảng giả sử từng context được tạo hợp lệ và condition được xét trong context đó. Hai hàng đầu **không đổi theo loại context** vì classpath đã cố định; những hàng còn lại phụ thuộc vào đặc trưng runtime. Đây là lý do một classpath đơn lẻ không đủ để kết luận cấu hình Servlet/Reactive nào sẽ được kích hoạt.

### 4.2. Có web context không đồng nghĩa đã mở HTTP port

Phân biệt thêm hai lớp câu hỏi:

1. **Context là web hay không?** `@ConditionalOnWebApplication`.
2. **Server có nhận kết nối HTTP tại cổng nào hay không?** Đó là trạng thái mạng/server ở runtime, không phải mục tiêu của annotation.

Trong Spring Boot, `server.port=0` thường yêu cầu cấp một cổng ngẫu nhiên cho embedded server (khi web server thực sự chạy). Cấu hình `server.port=-1` có thể vô hiệu hóa HTTP endpoints trong khi vẫn tạo `WebApplicationContext`. `spring.main.web-application-type=none` thì làm ứng dụng được khởi động theo loại không web. **Không dùng `server.port` để giả lập `WebApplicationType.NONE`.**

Các test context runner dành cho web cũng có thể dùng mock environment/servlet context để đánh giá condition mà **không cần mở cổng**. Việc đó không làm chúng trở thành context non-web.

## 5. Các tình huống thực tế dễ nhầm lẫn

### 5.1. WebFlux chỉ dùng làm HTTP client trong ứng dụng MVC

Một dịch vụ đã dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Có thể bổ sung `spring-boot-starter-webflux` để dùng `WebClient`. Nếu không chủ động đổi loại ứng dụng, Boot thường chọn **SERVLET** vì MVC có mặt. Khi ấy:

- `@ConditionalOnClass(DispatcherHandler.class)` có thể **đúng** vì WebFlux library có mặt.
- `@ConditionalOnWebApplication(type = REACTIVE)` là **sai** trong servlet context.
- `@ConditionalOnWebApplication(type = SERVLET)` là **đúng**.
- Việc tồn tại bean `WebClient.Builder` hoặc `Mono` cũng không chứng minh server đang chạy Netty/WebFlux.

Sai lầm thường gặp là dùng `@ConditionalOnClass(WebClient.class)` để bật **reactive server filter**, `WebFilter` hoặc cấu hình `HttpHandler`. Điều kiện đó phù hợp để bật một **client adapter** cần `WebClient`, còn thành phần tích hợp với reactive web runtime nên có thêm điều kiện `Type.REACTIVE`.

### 5.2. Ứng dụng batch/CLI mang dependency web

Một ứng dụng xử lý dữ liệu có thể dùng `spring-web`, `spring-webmvc` để tái sử dụng các kiểu HTTP hoặc vì dependency bắc cầu. Nếu chạy với `WebApplicationType.NONE`, `@ConditionalOnClass(DispatcherServlet.class)` vẫn có thể đúng; `@ConditionalOnWebApplication` không khớp. Điều kiện classpath không nên tự động tạo interceptor, filter Servlet, web controller hoặc infrastructure gắn với HTTP runtime.

### 5.3. Ép REACTIVE dù có cả Spring MVC

Khi cấu hình:

```properties
spring.main.web-application-type=reactive
```

và classpath thực sự đủ để khởi tạo reactive server, Boot có thể chạy reactive web context dù `DispatcherServlet` vẫn hiện diện. Điều kiện classpath cho MVC vẫn đúng, nhưng điều kiện web kiểu Servlet không khớp. Đây là tình huống tốt để thấy classpath **không biến mất** khi đổi loại ứng dụng.

### 5.4. Kiểm tra riêng module thư viện

Một module auto-configuration có thể được dùng trong ứng dụng Servlet, Reactive lẫn non-web. Đừng mặc định “có starter trong POM” ⇒ mọi consumer chạy cùng loại context. Đánh dấu từng cấu hình con theo *khả năng thư viện* và *môi trường thực tế*. Kết quả chỉ nên khớp tại nơi tính năng đó có nghĩa.

### 5.5. Parent/child context hoặc test custom context

Trong cấu trúc nhiều context, condition được đánh giá trong **context chứa cấu hình đang xét**; không suy loại của mọi context chỉ từ một parent hay từ classpath chung. Test runner có thể tạo một Servlet web context trong JVM mà ở test khác lại tạo non-web context, dù classpath y nguyên. Khi debug, ghi rõ **đang kiểm tra context nào** và condition được đánh giá lúc nào.

## 6. Thiết kế auto-configuration đúng: kiểm tra cả khả năng và môi trường

Khi bean chỉ hữu ích nếu vừa có thư viện Servlet MVC vừa chạy với Servlet web context, kết hợp hai điều kiện:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication.Type;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class DemoWebAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name =
            "org.springframework.web.servlet.DispatcherServlet")
    @ConditionalOnWebApplication(type = Type.SERVLET)
    static class ServletPart {

        @Bean
        ServletDiagnosticMarker servletDiagnosticMarker() {
            return new ServletDiagnosticMarker();
        }
    }

    public static final class ServletDiagnosticMarker {
    }
}
```

**Đây là một mảnh mã minh họa về annotation**, không phải ứng dụng hoàn chỉnh có thể chạy độc lập. Ở đây điều kiện ở mức class là **AND**: nếu class MVC vắng mặt, nested configuration không được tham gia; nếu context không phải Servlet, phần Servlet không được bật dù MVC có trên classpath.

Phần tương đương cho WebFlux server sẽ có điều kiện:

```java
@ConditionalOnClass(name =
        "org.springframework.web.reactive.DispatcherHandler")
@ConditionalOnWebApplication(type =
        ConditionalOnWebApplication.Type.REACTIVE)
```

Hai annotation trong khối trên là **mảnh khai báo** để đặt trên một class `@Configuration` thích hợp. Nếu tính năng cần bean cụ thể, có thể bổ sung `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean`, nhưng đừng dùng chúng như thay thế cho câu hỏi context thuộc loại gì.

Với một auto-configuration phát hành trong library, liệt kê tên class của nó trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` theo hợp đồng Spring Boot 3.x; chỉ đưa nó vào dependency không bảo đảm sẽ được auto-import nếu thiếu cơ chế đăng ký này. Khi cấu hình có optional dependency, dùng nested configuration tách chữ ký bean có type tùy chọn để tránh lỗi load class ngoài ý muốn.

## 7. Thực hành: cùng một classpath, ba context khác nhau

Thực hành này cố ý để **cả MVC và WebFlux đều có mặt** trong dependency test, rồi thay loại `ApplicationContext` bằng ba runner được Spring Boot cung cấp:

- `ApplicationContextRunner`: tạo context thông thường, không web.
- `WebApplicationContextRunner`: tạo servlet web context để kiểm tra condition, sử dụng mock servlet context; không cần mở HTTP port.
- `ReactiveWebApplicationContextRunner`: tạo reactive web context để kiểm tra condition, không cần mở HTTP port.

Đây là test cho cơ chế điều kiện. Nó **không kiểm thử thuật toán mặc định chọn `WebApplicationType` của một `SpringApplication` đầy đủ**; ba runner cố tình tạo ba loại context riêng. Để kiểm chứng suy luận bootstrap khi cả hai starter hiện diện, xem mục 8.

### 7.1. Chuẩn bị project test độc lập

Cấu trúc:

```text
web-context-conditions/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/WebContextConditionTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'web-context-conditions'
```

`build.gradle` (chọn cùng phiên bản Spring Boot 3.3.13 cho toàn bộ starter):

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-web:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

test {
    useJUnitPlatform()
}
```

JDK 17+ và Gradle tương thích với Spring Boot 3.3 là điều kiện chạy. Khi có Gradle Wrapper, dùng wrapper của dự án; mã test không phụ thuộc môi trường Docker hay database.

### 7.2. Test JUnit 5 đầy đủ

Tạo `src/test/java/demo/WebContextConditionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication.Type;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class WebContextConditionTest {

    // Các marker tách biệt để assert loại điều kiện nào đã khớp.
    record MvcLibraryMarker() {}
    record AnyWebMarker() {}
    record ServletMarker() {}
    record ReactiveMarker() {}
    record NonWebMarker() {}

    @AutoConfiguration
    static class ProbeAutoConfiguration {

        @Bean
        @ConditionalOnClass(name =
                "org.springframework.web.servlet.DispatcherServlet")
        MvcLibraryMarker mvcLibraryMarker() {
            return new MvcLibraryMarker();
        }

        @Bean
        @ConditionalOnWebApplication
        AnyWebMarker anyWebMarker() {
            return new AnyWebMarker();
        }

        @Bean
        @ConditionalOnWebApplication(type = Type.SERVLET)
        ServletMarker servletMarker() {
            return new ServletMarker();
        }

        @Bean
        @ConditionalOnWebApplication(type = Type.REACTIVE)
        ReactiveMarker reactiveMarker() {
            return new ReactiveMarker();
        }

        @Bean
        @ConditionalOnNotWebApplication
        NonWebMarker nonWebMarker() {
            return new NonWebMarker();
        }
    }

    @Test
    void ordinaryContextStillSeesMvcLibraryOnClasspath() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ProbeAutoConfiguration.class))
                .run(ctx -> {
                    assertThat(ctx).hasSingleBean(MvcLibraryMarker.class);
                    assertThat(ctx).hasSingleBean(NonWebMarker.class);
                    assertThat(ctx).doesNotHaveBean(AnyWebMarker.class);
                    assertThat(ctx).doesNotHaveBean(ServletMarker.class);
                    assertThat(ctx).doesNotHaveBean(ReactiveMarker.class);
                });
    }

    @Test
    void servletContextMatchesServletButNotReactiveCondition() {
        new WebApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ProbeAutoConfiguration.class))
                .run(ctx -> {
                    assertThat(ctx).hasSingleBean(MvcLibraryMarker.class);
                    assertThat(ctx).hasSingleBean(AnyWebMarker.class);
                    assertThat(ctx).hasSingleBean(ServletMarker.class);
                    assertThat(ctx).doesNotHaveBean(ReactiveMarker.class);
                    assertThat(ctx).doesNotHaveBean(NonWebMarker.class);
                });
    }

    @Test
    void reactiveContextStillSeesMvcLibraryButIsNotServlet() {
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ProbeAutoConfiguration.class))
                .run(ctx -> {
                    assertThat(ctx).hasSingleBean(MvcLibraryMarker.class);
                    assertThat(ctx).hasSingleBean(AnyWebMarker.class);
                    assertThat(ctx).hasSingleBean(ReactiveMarker.class);
                    assertThat(ctx).doesNotHaveBean(ServletMarker.class);
                    assertThat(ctx).doesNotHaveBean(NonWebMarker.class);
                });
    }
}
```

Chạy:

```bash
gradle test --tests demo.WebContextConditionTest
```

Nếu có Gradle Wrapper:

```bash
./gradlew test --tests demo.WebContextConditionTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.WebContextConditionTest
```

**Kết quả mong đợi:** task `test` thành công với 3 test passed. Không liệt kê một stdout cố định vì dòng log Gradle phụ thuộc phiên bản và cấu hình. Trên cùng classpath, `MvcLibraryMarker` xuất hiện ở **cả ba** context; còn `ServletMarker`/`ReactiveMarker`/`NonWebMarker` chỉ xuất hiện đúng context tương ứng.

| Runner | `MvcLibraryMarker` | `AnyWebMarker` | `ServletMarker` | `ReactiveMarker` | `NonWebMarker` |
| --- | :---: | :---: | :---: | :---: | :---: |
| `ApplicationContextRunner` | ✓ | – | – | – | ✓ |
| `WebApplicationContextRunner` | ✓ | ✓ | ✓ | – | – |
| `ReactiveWebApplicationContextRunner` | ✓ | ✓ | – | ✓ | – |

Mỗi test tạo context riêng nên không bị nhiễu bởi bean còn sót ở test khác. Điểm thú vị ở test thứ ba: mặc dù class Servlet MVC **vẫn có mặt**, condition dành riêng cho Servlet context **không khớp**.

### 7.3. Diễn giải lỗi thường gặp trong test

- Nếu cố test reactive case bằng `ApplicationContextRunner` và chỉ thêm `.withPropertyValues("spring.main.web-application-type=reactive")`, đừng kỳ vọng runner đổi sang reactive context. **Runner đã chọn context factory riêng**; property trên là dữ liệu môi trường, không tái tạo loại context của runner.
- Nếu `@ConditionalOnClass` không khớp, kiểm tra dependency thực sự có trong **test runtime classpath** hay không. Một dependency được khai báo ở cấu hình khác chưa chắc đi vào test runtime.
- Nếu bạn thêm toàn bộ các auto-configuration web server cùng nhiều starter vào phép thử, có thể làm phát sinh bean/server infrastructure không cần thiết. Test trên chỉ import `ProbeAutoConfiguration` để cô lập kết quả của condition.
- Nếu test dùng `@SpringBootTest` thay vì runner, hãy xác định rõ `webEnvironment` và `spring.main.web-application-type`. Loại context test lúc đó còn phụ thuộc cấu hình Boot Test và classpath.

## 8. Phân biệt thêm: lựa chọn loại context khi khởi động SpringApplication đầy đủ

Bài test mục 7 **cố tình chọn loại context**. Đối với một ứng dụng Boot thực sự, cần xem lựa chọn của `SpringApplication`. Đoạn ứng dụng sau minh họa cách in context runtime bằng `ApplicationRunner`; nó cần được đặt trong dự án Boot có main class và dependency phù hợp.

```java
package demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WebTypeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebTypeApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectContext(ApplicationContext context) {
        return args -> System.out.println(
                "Context: " + context.getClass().getName());
    }
}
```

Giả sử dự án có hai starter web và main class trên, các bước **có thể quan sát**:

1. Không đặt `spring.main.web-application-type`: Boot mặc định chọn Servlet do MVC và WebFlux cùng có mặt. Dòng `Context: ...` cho biết concrete context thực tế; ứng dụng có thể mở embedded servlet server nếu setup đầy đủ.
2. Chạy với `--spring.main.web-application-type=none`: context đi theo kiểu không web; classpath không mất thư viện MVC/WebFlux, nhưng condition `Type.SERVLET`/`Type.REACTIVE` không khớp trong context này.
3. Chạy với `--spring.main.web-application-type=reactive`: nếu dependency và server phù hợp, Boot dùng reactive web context, mặc dù MVC class vẫn load được.

Không cố định một dòng stdout với tên class tuyệt đối cho mọi cấu hình/chế độ test: tên concrete context có thể thay đổi theo bootstrap, application context factory, cấu hình custom hoặc phiên bản. Điều có ý nghĩa là đặc tính web Servlet/Reactive/non-web được thể hiện ở runtime.

Sự khác biệt giữa **suy luận** và **ép kiểu** quan trọng: khi thay property từ mặc định sang `reactive`, bạn đã thay chính lựa chọn bootstrap; bạn không “xóa `DispatcherServlet` khỏi classpath”. Do vậy class condition và web condition có thể tách biệt một cách dự đoán được.

### 8.1. Dependency là đầu vào của suy luận, không phải trạng thái context

Sơ đồ:

```text
Dependencies / Classpath
  ├── DispatcherServlet hiện diện?
  ├── DispatcherHandler hiện diện?
  └── Các class chỉ dấu web khác?
                |
                v
 SpringApplication chọn WebApplicationType
     (suy luận hoặc cấu hình rõ)
                |
                v
  ApplicationContext được tạo & refresh
                |
                +--> NONE      -> non-web environment/context
                +--> SERVLET   -> Servlet web environment/context
                +--> REACTIVE  -> Reactive web environment/context
                |
                v
OnClassCondition hỏi: class có không?
OnWebApplicationCondition hỏi: context/environment web loại nào?
                |
                v
Đăng ký hoặc bỏ qua configuration / bean
```

Lưu ý trong custom test/bootstrap: một framework hoặc code khác có thể tự tạo context, bỏ qua bước `SpringApplication` suy luận mặc định. Vì thế **context hiện tại** mới là chứng cứ phù hợp cho câu hỏi về `@ConditionalOnWebApplication`.

## 9. Debug quyết định condition không đúng kỳ vọng

Đi từ dấu hiệu tới câu hỏi có thể kiểm chứng:

1. **Xác định condition nào đang sai.** `@ConditionalOnClass` kiểm tra lớp, `@ConditionalOnWebApplication` kiểm tra context, `@ConditionalOnBean` kiểm tra bean. Một cấu hình có thể bị chặn bởi nhiều điều kiện, nên đừng quy tất cả về web type.
2. **Xác nhận tên lớp trên classpath.** Kiểm tra `DispatcherServlet`, `DispatcherHandler` hoặc lớp đúng với điều kiện thực tế. Có mặt trong file build chưa đủ; cần có trong runtime classpath. Dùng `./gradlew dependencies --configuration runtimeClasspath` để tìm dependency transitively (với dự án có wrapper).
3. **Xác nhận loại context đang hoạt động.** In `ApplicationContext#getClass()`, kiểm tra interface web tương ứng; ghi nhận môi trường thực tế. Một generic context trong test có thể không web dù JAR web có sẵn.
4. **Kiểm tra chế độ bootstrap.** Có `spring.main.web-application-type`, `SpringApplication#setWebApplicationType`, `ApplicationContextFactory` tùy chỉnh, `@SpringBootTest(webEnvironment=...)`, runner cụ thể hoặc parent/child context không? Property `server.port` không tự quyết định web type.
5. **Kiểm tra cặp MVC/WebFlux.** Cả hai starter hiện diện theo mặc định thường ra Servlet. Nếu muốn reactive server, phải chủ động chọn `REACTIVE` và có đủ server dependency.
6. **Đọc Conditions Evaluation Report.** Khi dùng Boot, bật `--debug` hoặc `debug=true` để xem positive/negative matches trong log. Tìm tên configuration, phần `OnClassCondition` và `OnWebApplicationCondition` để biết **điều kiện nào match, điều kiện nào không**. Nếu Actuator được cấu hình và endpoint được expose, `/actuator/conditions` cũng trình bày các matches.
7. **Viết test nhỏ với ba runner.** Giữ dependency không đổi, chỉ thay context. Sau đó thay classpath bằng `FilteredClassLoader` nếu cần kiểm chứng condition lớp; đừng cùng lúc thay cả classpath, web type và configuration rồi khó truy nguyên.

Các câu hỏi kiểm tra rất hữu ích khi đọc report:

- “Điều kiện thất bại vì thiếu `DispatcherServlet`, hay vì không có Servlet web application?”
- “Ứng dụng hiện chạy `SERVLET` dù `DispatcherHandler` vẫn load được?”
- “Test này khởi tạo loại context nào, và tôi có nhầm runner với `SpringApplication` thật không?”
- “Tính năng là **web client**, **server Servlet**, **server Reactive**, hay **common non-web service**?” Chọn annotation theo đúng mục đích.

## 10. Các lỗi thiết kế thường gặp

| Hiện tượng | Cách hiểu sai | Điều chỉnh |
| --- | --- | --- |
| Bean MVC tạo ra trong non-web process | Có `spring-webmvc` nên chắc là ứng dụng Servlet | Thêm `@ConditionalOnWebApplication(type=SERVLET)` nếu bean gắn với Servlet runtime |
| Bean reactive server tạo trong MVC app có `WebClient` | Có WebFlux trên classpath nên chắc đang chạy REACTIVE | Chỉ bật reactive server feature khi `Type.REACTIVE` khớp |
| Bean không xuất hiện dù thư viện có mặt | Chỉ nhìn `@ConditionalOnClass`, bỏ qua web condition khác | Xem condition report và loại `ApplicationContext` |
| Sau khi thêm `spring-boot-starter-webflux` vẫn chạy MVC | Nghĩ Boot ưu tiên WebFlux hoặc chọn ngẫu nhiên | MVC được ưu tiên khi cả hai có mặt; muốn reactive thì cấu hình `web-application-type=reactive` |
| Set `server.port=-1` rồi trông đợi `@ConditionalOnNotWebApplication` | Không mở cổng nghĩa là non-web | `server.port` và bản chất web context là hai câu hỏi khác nhau |
| Đặt `spring.main.web-application-type=reactive` trong `ApplicationContextRunner` rồi mong condition reactive khớp | Property tự đổi context factory của runner | Dùng `ReactiveWebApplicationContextRunner` hoặc bootstrapping Boot thực sự |
| Kiểm tra class tùy chọn tại method có return type phụ thuộc lớp ấy | `@ConditionalOnClass` luôn ngăn JVM load chữ ký | Tách nested configuration guarded ở cấp class |
| Dùng `@ConditionalOnWebApplication` làm phép thử mở HTTP port | Có web context là port đang nghe | Kiểm tra server runtime riêng; condition không thăm dò socket |

## 11. Checklist trước khi phát hành auto-configuration

- Nếu feature cần một API nằm trong JAR tùy chọn: dùng `@ConditionalOnClass` với lớp đại diện đúng.
- Nếu feature chỉ hợp lệ khi request được xử lý bằng Servlet/MVC: thêm `@ConditionalOnWebApplication(type=SERVLET)`.
- Nếu feature chỉ hợp lệ với reactive web server: thêm `@ConditionalOnWebApplication(type=REACTIVE)`.
- Nếu feature dùng chung cho cả Servlet và Reactive web: `Type.ANY` có thể phù hợp, nhưng không tự bật tính năng trong non-web context.
- Nếu feature chỉ phục vụ batch/CLI: dùng `@ConditionalOnNotWebApplication` khi đó là yêu cầu thật sự, không dựa vào việc class web vắng mặt.
- Nếu classpath có cả MVC và WebFlux, kiểm thử trường hợp default **SERVLET** và override **REACTIVE**.
- Viết test cho ít nhất `NONE`, `SERVLET`, `REACTIVE` trên **cùng classpath**; bổ sung test thiếu dependency nếu feature có optional class.
- Phân biệt **kết quả của condition**, **loại context** và **server có mở cổng** trong log/test; chúng là ba bằng chứng khác nhau.
- Khi module cung cấp auto-configuration, nhớ đăng ký trong `AutoConfiguration.imports` và tránh để class chỉ được component scan như một configuration người dùng.

**Ghi nhớ:** `@ConditionalOnClass` trả lời “lớp thư viện có hiện diện không?”; `@ConditionalOnWebApplication` trả lời “context đang được cấu hình có phải web Servlet/Reactive không?”. `WebApplicationType` diễn tả lựa chọn bootstrap. Cùng một classpath hoàn toàn có thể dẫn đến những context khác nhau, và một context Servlet vẫn có thể chứa mọi lớp của WebFlux. Thiết kế condition đúng nghĩa yêu cầu kiểm tra **cả dependency khả dụng lẫn ngữ cảnh chạy thực tế** khi tính năng cần cả hai.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3, **Creating Your Own Auto-configuration**, mục Class Conditions, Web Application Conditions và Simulating a Web Context: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3, **Reactive Web Applications**, lưu ý ưu tiên Spring MVC khi có cả hai starter: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3, **Testing Spring Boot Applications**, mục Detecting Web Application Type: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3, **Embedded Web Servers**, các cấu hình `spring.main.web-application-type=none` và `server.port=-1`: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 API, `WebApplicationType`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot 3.3 API, `ConditionalOnWebApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html

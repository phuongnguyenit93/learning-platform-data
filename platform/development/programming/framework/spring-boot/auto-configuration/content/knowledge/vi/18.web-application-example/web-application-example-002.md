# Lần theo điều kiện reactive của WebFluxAutoConfiguration

## 1. Mục tiêu: vì sao WebFlux có trên classpath nhưng auto-configuration vẫn không chạy?

`WebFluxAutoConfiguration` là auto-configuration của Spring Boot dành cho Spring WebFlux. Khi điều tra vì sao cấu hình này không tạo các thành phần WebFlux như mong đợi, không nên chỉ kiểm tra dependency `spring-boot-starter-webflux`. Cần lần theo ba câu hỏi độc lập:

1. **Framework có khả dụng không?** Các class của Spring WebFlux, đặc biệt `WebFluxConfigurer`, có trên runtime classpath không?
2. **Ứng dụng có thật sự chạy theo kiểu Reactive web không?** `ApplicationContext`/`Environment` hiện tại có được nhận diện là reactive web application không?
3. **Người dùng đã tự cung cấp nền tảng WebFlux chưa?** Đã có bean kiểu `WebFluxConfigurationSupport` khiến cấu hình mặc định của Boot phải nhường chỗ chưa?

Trong Spring Boot 3.3.x, ba câu hỏi này tương ứng với các điều kiện ở cấp class của `WebFluxAutoConfiguration`:

- `@ConditionalOnClass(WebFluxConfigurer.class)`
- `@ConditionalOnWebApplication(type = Type.REACTIVE)`
- `@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)`

Cấu hình còn khai báo quan hệ thứ tự `after` với các auto-configuration nền tảng khác. Những quan hệ đó quyết định thứ tự xử lý bean definition; chúng không thay thế ba điều kiện trên và cũng không khởi tạo web server.

Bài học lần theo từ classpath, loại application context, các điều kiện back-off, quan hệ tiền đề, đến Condition Evaluation Report. Cuối bài có bộ test Java 17/JUnit 5 dùng `ApplicationContextRunner` và `ReactiveWebApplicationContextRunner` để chứng minh kết quả trong ba tình huống.

## 2. Phân biệt các thành phần của reactive web stack

Một ứng dụng WebFlux không chỉ có một class cấu hình. Các thành phần chính có trách nhiệm khác nhau:

| Thành phần | Vai trò | Câu hỏi cần kiểm tra |
| --- | --- | --- |
| `spring-webflux` | Framework WebFlux: controller, handler, router, WebFlux configuration API | Có `WebFluxConfigurer` trên classpath không? |
| `WebFluxAutoConfiguration` | Đăng ký cấu hình WebFlux của Spring Boot và các tùy chỉnh mặc định | Reactive context có đúng loại và có cần Boot back-off không? |
| `ReactiveWebServerFactoryAutoConfiguration` | Cấu hình factory cho reactive embedded web server | Có server factory phù hợp không? |
| `HttpHandlerAutoConfiguration` | Kết nối ứng dụng WebFlux với `HttpHandler` mà server sử dụng | Có handler để xử lý request không? |
| Reactor Netty / Jetty / Tomcat reactive | Implementation server/client tương ứng | Runtime có implementation phù hợp không? |
| `WebClientAutoConfiguration` | Hỗ trợ WebClient cho HTTP client | Có thể dùng WebClient dù ứng dụng không chạy reactive server không? |

**Có WebFlux library không đồng nghĩa có reactive server.** `WebClient` có thể được dùng trong ứng dụng MVC hoặc ứng dụng non-web. Auto-configuration cho WebClient và auto-configuration cho WebFlux server là hai luồng khác nhau.

Spring WebFlux là framework web reactive, hỗ trợ cả controller annotation và functional endpoint. Nó dùng Reactor/Reactive Streams để biểu diễn xử lý bất đồng bộ, non-blocking. Tuy vậy, chỉ nhìn thấy `Mono`, `Flux` hoặc `WebClient` trong code không đủ để kết luận ứng dụng đang chạy với reactive web context.

### 2.1. Từ dependency tới runtime context

Spring Boot chọn `WebApplicationType` khi bootstrap bằng `SpringApplication`:

| Loại | Ý nghĩa | Context điển hình |
| --- | --- | --- |
| `NONE` | Không chạy như web application | `AnnotationConfigApplicationContext` |
| `SERVLET` | Web application theo Servlet/MVC | `AnnotationConfigServletWebServerApplicationContext` |
| `REACTIVE` | Web application theo Reactive/WebFlux | `AnnotationConfigReactiveWebServerApplicationContext` |

Nếu chỉ có bộ dependency WebFlux và server reactive tương ứng, Boot thường suy luận `REACTIVE`. Nếu cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng hiện diện, Spring MVC được ưu tiên mặc định. Trường hợp này phổ biến vì ứng dụng MVC có thể thêm WebFlux chỉ để dùng `WebClient`.

Muốn chủ động chạy reactive khi cả MVC và WebFlux cùng có mặt, đặt:

```properties
spring.main.web-application-type=reactive
```

Hoặc cấu hình bằng Java:

```java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
```

Đây là đoạn minh họa trong main method của ứng dụng Boot; `MyApplication` là class ứng dụng và `args` là tham số dòng lệnh. Việc ép kiểu chỉ thay đổi cách bootstrap/context được chọn. Nó không tự thêm dependency WebFlux, không cung cấp server implementation còn thiếu và không bảo đảm mọi bean tích hợp đều khởi tạo thành công.

### 2.2. Classpath condition và web application condition hỏi hai điều khác nhau

`@ConditionalOnClass(WebFluxConfigurer.class)` hỏi class WebFlux có khả dụng để cấu hình hay không. Nó không hỏi context đang chạy là reactive.

`@ConditionalOnWebApplication(type = Type.REACTIVE)` hỏi context/environment hiện tại có mang đặc trưng reactive web hay không. Boot nhận diện reactive web application dựa trên `ReactiveWebApplicationContext` hoặc `ConfigurableReactiveWebEnvironment`.

Vì thế có thể xảy ra:

- `WebFluxConfigurer` có mặt, nhưng context là non-web: class condition khớp, reactive web condition không khớp.
- `WebFluxConfigurer` có mặt, nhưng context là Servlet: class condition khớp, reactive web condition không khớp.
- `WebFluxConfigurer` có mặt và context là Reactive: cả hai điều kiện có thể khớp.
- Context là Reactive nhưng dependency WebFlux không đủ: điều kiện classpath không khớp, cấu hình WebFlux không được áp dụng.

Đây là nguyên nhân phổ biến nhất khi người phát triển nhìn dependency tree rồi kết luận sai rằng `WebFluxAutoConfiguration` chắc chắn phải được bật.

## 3. Đọc điều kiện cấp class của WebFluxAutoConfiguration

Trong Spring Boot 3.3, `WebFluxAutoConfiguration` nằm trong package:

```java
org.springframework.boot.autoconfigure.web.reactive
```

Các điều kiện quan trọng có ý nghĩa như sau:

### 3.1. `@ConditionalOnClass(WebFluxConfigurer.class)`

`WebFluxConfigurer` là API tùy chỉnh cấu hình WebFlux của Spring Framework. Điều kiện này bảo đảm framework cần thiết có trên classpath trước khi Boot xử lý các cấu hình phụ thuộc vào WebFlux.

Nếu thiếu class:

- Auto-configuration không được áp dụng.
- Các bean do cấu hình này cung cấp không xuất hiện.
- Condition report thường có `OnClassCondition` với thông điệp nêu class bắt buộc không tìm thấy.

Khi thư viện WebFlux là dependency tùy chọn, annotation ở cấp class giúp cô lập việc tham chiếu các class chỉ có trong dependency đó. Tránh đặt return type của bean method trực tiếp vào một class tùy chọn rồi kỳ vọng condition trên chính method luôn ngăn JVM xử lý chữ ký trước khi class được load.

### 3.2. `@ConditionalOnWebApplication(type = Type.REACTIVE)`

Điều kiện này yêu cầu context hiện tại là reactive web application. Nó loại các trường hợp:

- Ứng dụng batch/CLI dùng WebFlux API nhưng chạy với `WebApplicationType.NONE`.
- Ứng dụng Spring MVC có thêm WebFlux dependency để dùng `WebClient`.
- Test dùng một `ApplicationContext` thông thường, dù WebFlux có trên test classpath.

Khi test điều kiện này, phải dùng đúng loại context. `ApplicationContextRunner` mặc định tạo context thông thường; nó không biến thành reactive context chỉ vì bạn thêm property `spring.main.web-application-type=reactive`. Hãy dùng `ReactiveWebApplicationContextRunner` hoặc khởi động một `SpringApplication` thật với kiểu reactive.

### 3.3. `@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)`

Đây là điều kiện back-off cho phép ứng dụng tự nắm quyền cấu hình WebFlux. Nếu context đã có bean kiểu `WebFluxConfigurationSupport`, Boot bỏ qua `WebFluxAutoConfiguration`.

Một trường hợp điển hình là người dùng khai báo:

```java
@Configuration(proxyBeanMethods = false)
@EnableWebFlux
class MyWebFluxConfiguration {
}
```

`@EnableWebFlux` import `DelegatingWebFluxConfiguration`; class này kế thừa `WebFluxConfigurationSupport`. Vì vậy điều kiện missing bean của Boot có thể nhận diện cấu hình WebFlux do người dùng tự kích hoạt và nhường chỗ.

Cần phân biệt hai cách tùy chỉnh:

- **Mở rộng cấu hình Boot:** khai báo bean triển khai `WebFluxConfigurer` nhưng không dùng `@EnableWebFlux`. Cách này giữ lại các tùy chỉnh mặc định của Spring Boot.
- **Tự kiểm soát toàn bộ WebFlux configuration:** dùng `@EnableWebFlux`. Boot back-off và ứng dụng chịu trách nhiệm cấu hình nền tảng theo nhu cầu.

Chỉ khai báo một bean `WebFluxConfigurer` không đồng nghĩa đã đăng ký `WebFluxConfigurationSupport`. Đây là extension point để thêm tùy chỉnh; nó không tự yêu cầu Boot nhường toàn bộ auto-configuration.

### 3.4. Tổng hợp điều kiện theo bảng

| Classpath có `WebFluxConfigurer` | Context | Đã có `WebFluxConfigurationSupport` | Kết quả dự kiến |
| :---: | --- | :---: | --- |
| Không | Reactive | Không | No-match do class condition |
| Có | Non-web | Không | No-match do reactive web condition |
| Có | Servlet | Không | No-match do sai web application type |
| Có | Reactive | Không | WebFluxAutoConfiguration có thể match |
| Có | Reactive | Có | Boot back-off do missing-bean condition |

Bảng giả định candidate được phát hiện, không bị exclude/filter và không có điều kiện khác ngoài ba điều kiện cấp class đang xét. “Có thể match” nghĩa là các điều kiện chính ở trên đã thỏa; những cấu hình khác trong ứng dụng vẫn có thể tác động đến việc khởi tạo các bean phụ thuộc.

## 4. Lần theo quan hệ after của WebFluxAutoConfiguration

Ngoài các condition, class này còn khai báo thứ tự tương đối. Trong Boot 3.3, các cấu hình tiền đề được liệt kê qua `after` gồm:

- `ReactiveWebServerFactoryAutoConfiguration`
- `CodecsAutoConfiguration`
- `ReactiveMultipartAutoConfiguration`
- `ValidationAutoConfiguration`
- `WebSessionIdResolverAutoConfiguration`

Đổi quan hệ sang đồ thị theo quy ước mũi tên từ cấu hình phải được áp dụng trước tới cấu hình được áp dụng sau:

```text
ReactiveWebServerFactoryAutoConfiguration ---\
CodecsAutoConfiguration ----------------------\
ReactiveMultipartAutoConfiguration -----------+--> WebFluxAutoConfiguration
ValidationAutoConfiguration ------------------/
WebSessionIdResolverAutoConfiguration --------/
```

Điều đó có nghĩa WebFluxAutoConfiguration được sắp xếp sau các cấu hình tiền đề này khi chúng cùng nằm trong tập candidate được sắp xếp. Danh sách không khẳng định thứ tự giữa năm cấu hình tiền đề; không có cạnh trực tiếp giữa chúng trong quan hệ đang xét.

### 4.1. Vì sao cần từng nhóm tiền đề?

| Tiền đề | Vai trò trong reactive stack | Câu hỏi khi điều tra |
| --- | --- | --- |
| `ReactiveWebServerFactoryAutoConfiguration` | Cấu hình reactive server factory và customizer | Có implementation server nào được nhận diện không? |
| `CodecsAutoConfiguration` | Cấu hình codec dùng để đọc/ghi nội dung HTTP | Các codec cần thiết có sẵn và có thể được tùy chỉnh không? |
| `ReactiveMultipartAutoConfiguration` | Hỗ trợ multipart cho WebFlux | Cấu hình multipart và properties đã được xử lý chưa? |
| `ValidationAutoConfiguration` | Hạ tầng validation dùng chung | Validator có được cấu hình nếu dependency validation hiện diện không? |
| `WebSessionIdResolverAutoConfiguration` | Cấu hình cách phân giải session id cho reactive web | Có bean tùy chỉnh nào thay thế resolver mặc định không? |

Quan hệ `after` chỉ xác định thứ tự xử lý auto-configuration. Nó không bắt buộc tất cả tiền đề phải tạo bean cụ thể; condition riêng của từng tiền đề vẫn có thể không khớp. Nếu `ReactiveWebServerFactoryAutoConfiguration` bị loại hoặc không tìm thấy server implementation, WebFlux framework configuration và embedded server availability có thể có kết quả khác nhau.

### 4.2. Đừng nhầm WebFlux framework với reactive server

`WebFluxAutoConfiguration` cấu hình nền tảng WebFlux của Spring Boot. Reactive server factory được xử lý bởi auto-configuration riêng. `HttpHandlerAutoConfiguration` là một phần khác trong luồng kết nối context với HTTP handler.

Có thể tách chẩn đoán thành ba lớp:

1. **Framework configuration:** `WebFluxAutoConfiguration` có được phép áp dụng không?
2. **Server factory:** có bean `ReactiveWebServerFactory` phù hợp không?
3. **HTTP handler và runtime:** ứng dụng có tạo được `HttpHandler` và khởi chạy server không?

Một test dùng `ReactiveWebApplicationContextRunner` có thể xác minh điều kiện và bean cấu hình mà không mở cổng HTTP. Nó không tự chứng minh server thật đã bind port hoặc nhận request. Muốn kiểm tra network/runtime, cần integration test riêng.

### 4.3. `@AutoConfigureOrder` không thay thế các condition

Javadoc của auto-configuration còn thể hiện một giá trị order riêng. Giá trị order chỉ tham gia sắp xếp tổng quát giữa các auto-configuration. Nó không biến context Servlet thành Reactive, không làm class WebFlux xuất hiện trên classpath và không vượt qua `@ConditionalOnMissingBean`.

Khi đọc mã, hãy phân biệt:

- `after`: quan hệ tiền đề cụ thể.
- `@AutoConfigureOrder`: ưu tiên tổng quát trong quá trình sắp xếp.
- `@ConditionalOnClass` / `@ConditionalOnWebApplication` / `@ConditionalOnMissingBean`: quyết định có áp dụng cấu hình hay không.
- `@DependsOn` hoặc injection: quan hệ khởi tạo instance.

Không sửa order khi lỗi thật sự là sai loại context hoặc thiếu dependency.

## 5. Nested configuration và điểm mở rộng của WebFlux

Javadoc Spring Boot 3.3 liệt kê các nested class trong `WebFluxAutoConfiguration`, bao gồm:

- `EnableWebFluxConfiguration`: cấu hình tương đương `@EnableWebFlux`.
- `WebFluxConfig`.
- `WelcomePageConfiguration`.

`EnableWebFluxConfiguration` kế thừa cấu hình WebFlux của Spring Framework và là phần nền tảng để đăng ký các thành phần hỗ trợ controller/functional endpoint. Các nested class là chi tiết triển khai của Boot; ứng dụng thư viện không nên phụ thuộc vào tên hoặc method nội bộ của chúng như một API extension ổn định.

### 5.1. Mở rộng bằng WebFluxConfigurer

Nếu chỉ muốn tùy chỉnh một vài phần mà vẫn giữ Boot defaults, tạo cấu hình như sau:

```java
@Configuration(proxyBeanMethods = false)
class ApiWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void configurePathMatching(PathMatchConfigurer configurer) {
        // Thêm tùy chỉnh path matching tại đây.
    }
}
```

Đây là đoạn minh họa; cần import `WebFluxConfigurer` và `PathMatchConfigurer` từ package WebFlux tương ứng. Không thêm `@EnableWebFlux` vào cấu hình này nếu muốn giữ các tùy chỉnh mặc định của Boot.

Spring Boot có thể tiếp tục cung cấp codec configuration, static resource support và các tích hợp WebFlux mặc định. Bạn chỉ bổ sung những callback thực sự cần.

### 5.2. Khi nào dùng @EnableWebFlux?

Dùng `@EnableWebFlux` khi muốn tự kiểm soát hoàn toàn nền tảng WebFlux. Annotation này import cấu hình Spring Framework thay cho cấu hình mặc định tương ứng của Boot. Khi đó `@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)` khiến Boot back-off.

Không dùng `@EnableWebFlux` chỉ để đăng ký một controller hoặc một `WebFluxConfigurer` đơn giản. Nếu dùng nhầm, một số tùy chỉnh mà người phát triển kỳ vọng từ Boot có thể không còn được cung cấp.

### 5.3. WebFluxRegistrations và HttpHandler customizer

Một số extension point chuyên biệt:

- `WebFluxRegistrations` cho phép thay thế các component chủ chốt mà `WebFluxAutoConfiguration` cung cấp mặc định.
- `WebHttpHandlerBuilderCustomizer` cho phép tùy chỉnh `WebHttpHandlerBuilder` trước khi tạo HTTP handler.
- `WebFluxConfigurer` phù hợp với các callback cấu hình framework như path matching, formatters, resource handlers và message codecs.

Chọn extension point theo đúng lớp cần thay đổi. Nếu chỉ cần thêm formatter hoặc route configuration, không cần thay toàn bộ `WebFluxConfigurationSupport`.

### 5.4. Static resources và welcome page

Spring Boot WebFlux auto-configuration hỗ trợ phục vụ static resources và WebJars. Theo cấu hình mặc định, static resources có thể được tìm trong các thư mục classpath như `/static`, `/public`, `/resources` và `/META-INF/resources`. Resource mapping mặc định là `/**`; có thể thay đổi qua `spring.webflux.static-path-pattern` và `spring.web.resources.static-locations`.

`WelcomePageConfiguration` là nested configuration liên quan đến welcome page. Khi trang mặc định không xuất hiện, hãy kiểm tra static resource locations, static path pattern, custom resource handlers và các condition trong report trước khi kết luận `WebFluxAutoConfiguration` không chạy.

## 6. Lần theo Conditions Evaluation Report

Khi chạy ứng dụng với `--debug`, Spring Boot ghi Condition Evaluation Report vào log. Với `WebFluxAutoConfiguration`, hãy tìm source:

```text
org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration
```

Các condition thường cần đọc:

| Condition implementation | Ý nghĩa trong trường hợp này |
| --- | --- |
| `OnClassCondition` | `WebFluxConfigurer` có trên runtime classpath không? |
| `OnWebApplicationCondition` | Context hiện tại có phải reactive web application không? |
| `OnBeanCondition` | Có `WebFluxConfigurationSupport` khiến Boot phải back-off không? |

### 6.1. Ví dụ các kết quả thường gặp

**Tình huống A — WebFlux có trên classpath, ứng dụng non-web**

```text
WebFluxAutoConfiguration:
    @ConditionalOnClass found required class
    @ConditionalOnWebApplication did not find reactive web application
```

Ý nghĩa: classpath condition khớp, nhưng context không phải reactive web. Không có WebFlux auto-configuration là kết quả đúng.

**Tình huống B — ứng dụng Reactive, chưa có cấu hình WebFlux tùy chỉnh**

```text
WebFluxAutoConfiguration:
    @ConditionalOnClass found required class
    @ConditionalOnWebApplication found reactive web application
    @ConditionalOnMissingBean did not find WebFluxConfigurationSupport
```

Ý nghĩa: ba điều kiện chính đều cho phép cấu hình mặc định áp dụng.

**Tình huống C — ứng dụng Reactive đã dùng @EnableWebFlux**

```text
WebFluxAutoConfiguration:
    @ConditionalOnClass found required class
    @ConditionalOnWebApplication found reactive web application
    @ConditionalOnMissingBean found WebFluxConfigurationSupport
```

Ý nghĩa: framework và context phù hợp, nhưng user configuration đã cung cấp nền tảng WebFlux. Boot back-off có chủ đích.

Các câu trên là diễn giải message theo ý nghĩa, không phải literal log cố định. Nội dung thật có thể thêm class name, bean name hoặc chi tiết phiên bản.

### 6.2. Lấy report bằng API trong test

Có thể đọc outcome theo source class:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

ConditionEvaluationReport.ConditionAndOutcomes outcomes =
        report.getConditionAndOutcomesBySource()
                .get(WebFluxAutoConfiguration.class.getName());

if (outcomes != null) {
    System.out.println("fullMatch=" + outcomes.isFullMatch());

    for (ConditionEvaluationReport.ConditionAndOutcome item : outcomes) {
        System.out.println(
                item.getCondition().getClass().getSimpleName()
                        + " matched=" + item.getOutcome().isMatch()
                        + " message=" + item.getOutcome().getMessage());
    }
}
```

Đây là đoạn minh họa bên trong callback của `ApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner`; biến `context` là context test đã được tạo. Cần import `ConditionEvaluationReport` từ `org.springframework.boot.autoconfigure.condition`.

`isFullMatch()` chỉ true khi tất cả condition được ghi nhận cho source đều match. Nếu một condition no-match, source không được áp dụng dù các condition còn lại match.

Nếu `outcomes` là null, không nên lập tức kết luận WebFlux condition no-match. Hãy kiểm tra candidate có được import hay không, có bị exclude/filter không và đang đọc report của đúng context không.

### 6.3. Actuator endpoint

Nếu ứng dụng có Actuator và endpoint được expose, `GET /actuator/conditions` cung cấp condition report dạng JSON. Có thể dùng endpoint để kiểm tra positive/negative matches của `WebFluxAutoConfiguration` trong context đang chạy.

Endpoint phải được cấu hình access/exposure phù hợp. Không công khai endpoint diagnostics ra môi trường Internet không kiểm soát; report có thể chứa tên class, property và cấu trúc cấu hình nội bộ. Khi debug local, `--debug` thường là cách nhanh nhất.

## 7. Bộ test Java 17/JUnit 5: ba loại context, một classpath

Bài thực hành dưới đây cố ý giữ Spring WebFlux trên classpath ở mọi test, rồi thay đổi loại context và user configuration. Nhờ đó ta chứng minh điều kiện reactive dựa vào context và bean state chứ không chỉ dependency.

Ba tình huống:

1. `ApplicationContextRunner` tạo non-web context: class condition match, reactive condition no-match.
2. `ReactiveWebApplicationContextRunner` tạo reactive context: các condition chính match và Boot đăng ký WebFlux infrastructure.
3. Reactive context có user `@EnableWebFlux`: condition missing bean no-match, Boot nhường cấu hình cho người dùng.

Runner không mở HTTP port; test tập trung vào auto-configuration và bean definitions.

### 7.1. Cấu trúc project

```text
webflux-auto-configuration-trace/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/WebFluxAutoConfigurationConditionTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'webflux-auto-configuration-trace'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

test {
    useJUnitPlatform()
}
```

JDK 17+ là yêu cầu cho Spring Boot 3.3. Dependencies được cố định cùng phiên bản 3.3.13 để tránh trộn API giữa các dòng Boot.

### 7.2. File test hoàn chỉnh

Tạo `src/test/java/demo/WebFluxAutoConfigurationConditionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.WebFluxConfigurationSupport;

import static org.assertj.core.api.Assertions.assertThat;

class WebFluxAutoConfigurationConditionTest {

    private final ApplicationContextRunner nonWebRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(WebFluxAutoConfiguration.class));

    private final ReactiveWebApplicationContextRunner reactiveRunner =
            new ReactiveWebApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(WebFluxAutoConfiguration.class));

    @Configuration(proxyBeanMethods = false)
    @EnableWebFlux
    static class UserWebFluxConfiguration {
    }

    private ConditionAndOutcomes webFluxOutcomes(
            AssertableApplicationContext context) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        ConditionAndOutcomes outcomes =
                report.getConditionAndOutcomesBySource()
                        .get(WebFluxAutoConfiguration.class.getName());

        assertThat(outcomes)
                .as("Condition report for WebFluxAutoConfiguration")
                .isNotNull();

        return outcomes;
    }

    private boolean hasOutcome(
            ConditionAndOutcomes outcomes,
            String conditionSimpleName,
            boolean expectedMatch) {

        for (ConditionAndOutcome item : outcomes) {
            if (item.getCondition().getClass().getSimpleName()
                    .equals(conditionSimpleName)
                    && item.getOutcome().isMatch() == expectedMatch) {
                return true;
            }
        }
        return false;
    }

    @Test
    void nonWebContextDoesNotActivateWebFluxEvenWhenClassesArePresent() {
        nonWebRunner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context)
                    .doesNotHaveBean(WebFluxConfigurationSupport.class);

            ConditionAndOutcomes outcomes = webFluxOutcomes(context);

            assertThat(outcomes.isFullMatch()).isFalse();
            assertThat(hasOutcome(
                    outcomes, "OnClassCondition", true)).isTrue();
            assertThat(hasOutcome(
                    outcomes, "OnWebApplicationCondition", false)).isTrue();
        });
    }

    @Test
    void reactiveContextActivatesBootWebFluxConfiguration() {
        reactiveRunner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context)
                    .hasSingleBean(WebFluxConfigurationSupport.class);

            ConditionAndOutcomes outcomes = webFluxOutcomes(context);

            assertThat(outcomes.isFullMatch()).isTrue();
            assertThat(hasOutcome(
                    outcomes, "OnClassCondition", true)).isTrue();
            assertThat(hasOutcome(
                    outcomes, "OnWebApplicationCondition", true)).isTrue();
            assertThat(hasOutcome(
                    outcomes, "OnBeanCondition", true)).isTrue();
        });
    }

    @Test
    void userEnableWebFluxMakesBootBackOff() {
        reactiveRunner
                .withUserConfiguration(UserWebFluxConfiguration.class)
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context)
                            .hasSingleBean(WebFluxConfigurationSupport.class);

                    ConditionAndOutcomes outcomes = webFluxOutcomes(context);

                    assertThat(outcomes.isFullMatch()).isFalse();
                    assertThat(hasOutcome(
                            outcomes, "OnWebApplicationCondition", true))
                            .isTrue();
                    assertThat(hasOutcome(
                            outcomes, "OnBeanCondition", false))
                            .isTrue();
                });
    }
}
```

### 7.3. Chạy test

Từ thư mục project:

```bash
gradle test --tests demo.WebFluxAutoConfigurationConditionTest
```

Nếu dùng Gradle Wrapper trên Linux/macOS:

```bash
./gradlew test --tests demo.WebFluxAutoConfigurationConditionTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.WebFluxAutoConfigurationConditionTest
```

Kết quả kỳ vọng là **3 test passed** khi JDK và dependency tương thích. Đây là kết quả dự kiến của bộ test mẫu; không coi log Gradle là stdout cố định và không tuyên bố test đã được chạy trên môi trường của người học.

### 7.4. Đọc kết quả từng test

| Test | Context | Class condition | Reactive condition | Missing-bean condition | Kết quả bean |
| --- | --- | --- | --- | --- | --- |
| `nonWebContextDoesNotActivate...` | Non-web | Match | No-match | Không quyết định kết quả cuối | Không có `WebFluxConfigurationSupport` từ Boot |
| `reactiveContextActivates...` | Reactive | Match | Match | Match | Có `WebFluxConfigurationSupport` |
| `userEnableWebFluxMakesBootBackOff...` | Reactive + user `@EnableWebFlux` | Match | Match | No-match | Có cấu hình WebFlux của user; Boot back-off |

Test đầu là bằng chứng trực tiếp rằng dependency WebFlux có trên test classpath vẫn không làm auto-configuration bật trong non-web context. Test thứ hai chứng minh reactive context và classpath phù hợp cho phép Boot cấu hình. Test cuối chứng minh custom WebFlux configuration làm điều kiện missing bean thất bại.

### 7.5. Giới hạn của test runner

`ReactiveWebApplicationContextRunner` tạo reactive context để kiểm tra condition và bean definitions. Nó không mô phỏng toàn bộ quá trình bind port của một ứng dụng executable JAR.

Nếu muốn xác nhận server thực sự nhận request, viết integration test riêng với `@SpringBootTest(webEnvironment = RANDOM_PORT)` và một server implementation có trên classpath. Có thể dùng `WebTestClient` để gửi request đến ứng dụng test.

Nếu ứng dụng có cả MVC và WebFlux, test bootstrap mặc định bằng `@SpringBootTest` có thể tạo Servlet context do MVC được ưu tiên. Khi mục tiêu là test reactive trong classpath hỗn hợp, đặt:

```java
@SpringBootTest(properties =
        "spring.main.web-application-type=reactive")
class ReactiveApplicationIntegrationTest {
}
```

Đây là skeleton minh họa; cần có main application và test dependency phù hợp. Với kiểm thử condition thuần, `ReactiveWebApplicationContextRunner` trực tiếp và ít phụ thuộc hơn.

## 8. Quy trình điều tra khi WebFluxAutoConfiguration không match

Thực hiện theo thứ tự để tránh sửa nhầm dependency hoặc annotation:

1. **Xác nhận candidate:** kiểm tra `WebFluxAutoConfiguration` có trong `AutoConfiguration.imports` của Boot autoconfigure JAR và không bị exclude.
2. **Xác nhận classpath:** kiểm tra runtime có `org.springframework.web.reactive.config.WebFluxConfigurer` hay không. Dùng `./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath` để tìm dependency thực tế.
3. **Xác nhận loại ứng dụng:** đọc `WebApplicationType` và concrete `ApplicationContext`. Nếu có cả starter MVC và WebFlux, kiểm tra MVC có được ưu tiên mặc định không.
4. **Đọc condition report:** tìm source `WebFluxAutoConfiguration`; phân biệt `OnClassCondition`, `OnWebApplicationCondition` và `OnBeanCondition`.
5. **Kiểm tra custom configuration:** tìm `@EnableWebFlux` hoặc bean kiểu `WebFluxConfigurationSupport`. Nếu có, xác định việc Boot back-off có phải chủ đích không.
6. **Kiểm tra predecessor:** xem reactive server factory, codecs, multipart, validation và session resolver auto-configuration có được chọn và condition của chúng có match không.
7. **Kiểm tra server factory:** nếu WebFlux framework configuration đã match nhưng app không mở cổng, xem `ReactiveWebServerFactory` và implementation Netty/Jetty/Tomcat reactive.
8. **Kiểm tra HTTP handler:** nếu server factory có nhưng request không được xử lý, xem `HttpHandler`, dispatcher handler, controller/RouterFunction và các customizer.
9. **Tái hiện bằng test:** giữ dependency cố định và thay lần lượt non-web, reactive, user `@EnableWebFlux`. Assert cả report outcome lẫn bean.
10. **Sửa đúng tầng:** thêm dependency khi thiếu class, đổi web application type khi sai context, bỏ `@EnableWebFlux` khi chỉ muốn Boot customization, hoặc cung cấp custom framework config nếu thật sự muốn Boot back-off.

### 8.1. Dấu hiệu và hướng xử lý

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `OnClassCondition` no-match | `spring-webflux` không có trên runtime classpath | Dependency tree, scope, starter |
| `OnClassCondition` match nhưng `OnWebApplicationCondition` no-match | Ứng dụng non-web hoặc Servlet | `WebApplicationType`, context class, MVC starter |
| Cả hai trên match, `OnBeanCondition` no-match | Có `WebFluxConfigurationSupport` do user config | Tìm `@EnableWebFlux`/`DelegatingWebFluxConfiguration` |
| WebFlux config match nhưng server không start | Thiếu reactive server factory/implementation hoặc lỗi khởi tạo server | `ReactiveWebServerFactory`, Reactor Netty/Jetty/Tomcat |
| Server start nhưng không có endpoint | Controller/RouterFunction không được scan/import, mapping sai | Handler mappings, component scan, route beans |
| Static resource không hiện | Resource locations/path pattern/custom handler | `spring.web.resources.static-locations`, `spring.webflux.static-path-pattern` |
| Thêm WebFlux starter vào MVC nhưng vẫn chạy MVC | Boot ưu tiên Spring MVC khi cả hai starter cùng có | Ép `spring.main.web-application-type=reactive` nếu thật sự muốn server WebFlux |
| Tùy chỉnh codec mất hiệu lực | Dùng `@EnableWebFlux` khiến Boot back-off hoặc customizer sai extension point | Dùng `WebFluxConfigurer`/codec customizer nếu muốn giữ Boot defaults |

## 9. Các hiểu nhầm thường gặp

### 9.1. Có WebFlux dependency nghĩa là server reactive

Không đúng. Dependency cung cấp API/framework; loại context là quyết định bootstrap. WebFlux có thể chỉ được dùng làm HTTP client trong MVC app.

### 9.2. @ConditionalOnClass là đủ

Không đúng với `WebFluxAutoConfiguration`. Nó còn cần reactive web application context và không có `WebFluxConfigurationSupport` đã được đăng ký.

### 9.3. Có bean WebFluxConfigurer sẽ khiến Boot back-off

Không nhất thiết. `WebFluxConfigurer` là extension point để Boot áp dụng tùy chỉnh. Condition back-off kiểm tra `WebFluxConfigurationSupport`. `@EnableWebFlux` thường tạo nền tảng support và làm Boot back-off.

### 9.4. @EnableWebFlux chỉ bổ sung một configurer

Không. Nó bật cấu hình nền của Spring Framework và thay đổi quyền sở hữu WebFlux configuration. Dùng khi muốn tự quản lý toàn bộ cấu hình framework.

### 9.5. WebFluxAutoConfiguration tự mở cổng

Không nên kết luận như vậy. Framework configuration, reactive server factory và HTTP handler là các lớp liên quan nhưng riêng biệt. Một context test reactive có thể có WebFlux configuration mà không chạy embedded server.

### 9.6. Report không có source nghĩa là condition no-match

Không nhất thiết. Candidate có thể chưa được import, bị exclude/filter hoặc bạn đang xem report của context khác. Kiểm tra discovery trước khi kết luận.

### 9.7. Dựa vào thứ tự log để suy ra thứ tự khởi tạo

Condition report mô tả condition evaluation; annotation `after` mô tả thứ tự xử lý auto-configuration. Chúng không phải timeline constructor hoặc request. Dùng dependency injection/lifecycle tracing cho câu hỏi khởi tạo.

## 10. Checklist review khi sửa WebFlux auto-configuration

- [ ] `WebFluxAutoConfiguration` có trong candidate imports và không bị exclude.
- [ ] `WebFluxConfigurer` có trên runtime classpath.
- [ ] Context thật sự là `REACTIVE`, không phải `SERVLET` hoặc `NONE`.
- [ ] Nếu có cả MVC và WebFlux, đã quyết định rõ có muốn ép `WebApplicationType.REACTIVE` hay không.
- [ ] Không có `WebFluxConfigurationSupport` do user config nếu mong muốn Boot defaults.
- [ ] Nếu user dùng `@EnableWebFlux`, đã chấp nhận Boot back-off và tự quản lý các cấu hình cần thiết.
- [ ] Các predecessor trong `after` đã được nhận diện và condition của chúng được kiểm tra riêng.
- [ ] Đã phân biệt framework configuration với server factory và HTTP handler.
- [ ] Có test non-web để chứng minh classpath đơn thuần không bật WebFlux.
- [ ] Có test reactive để chứng minh auto-configuration match.
- [ ] Có test user `@EnableWebFlux` để chứng minh back-off.
- [ ] Nếu cần kiểm tra HTTP thật, đã có integration test riêng thay vì chỉ dựa vào context runner.
- [ ] Đã kiểm tra condition report theo đúng source và context.

**Ghi nhớ:** `WebFluxAutoConfiguration` chỉ được áp dụng khi framework WebFlux có trên classpath, context đang chạy là reactive web application và chưa có `WebFluxConfigurationSupport` do người dùng cung cấp. Quan hệ `after` giúp nó được xử lý sau các cấu hình nền như reactive server factory, codecs, multipart, validation và session resolver. Hãy lần theo ba condition trước, sau đó mới kiểm tra server factory, HTTP handler và endpoint thực tế.

## Tài liệu chính thức

- Spring Boot 3.3.13 API — `WebFluxAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.html
- Spring Boot 3.3.13 API — package `org.springframework.boot.autoconfigure.web.reactive`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/package-summary.html
- Spring Boot 3.3 — Reactive Web Applications và WebFlux auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration, candidate discovery, conditions và ordering: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 API — `ReactiveWebServerFactoryAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/ReactiveWebServerFactoryAutoConfiguration.html
- Spring Boot 3.3.13 API — `WebFluxRegistrations`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxRegistrations.html
- Spring Framework — WebFlux configuration and `@EnableWebFlux`: https://docs.spring.io/spring-framework/reference/web/webflux/config.html

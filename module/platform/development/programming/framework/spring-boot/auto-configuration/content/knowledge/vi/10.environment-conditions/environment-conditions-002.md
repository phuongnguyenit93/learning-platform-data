# `@ConditionalOnWebApplication` với `ANY`, `SERVLET` và `REACTIVE`

Trong **Spring Boot Auto Configuration**, nhiều cấu hình mặc định chỉ có ý nghĩa khi ứng dụng thật sự chạy trong **môi trường web**. Một `Filter` của Servlet, một `WebFilter` của WebFlux hay một bean dùng chung cho cả hai nhánh không nên được đăng ký tùy tiện vào một ứng dụng chạy command line. Spring Boot cung cấp `@ConditionalOnWebApplication` để mô tả chính xác điều kiện này.

Bài này giải thích ba giá trị `ANY`, `SERVLET`, `REACTIVE`, cách Spring Boot nhận diện môi trường, trường hợp dự án có cả Spring MVC lẫn WebFlux, cách đặt annotation trong auto-configuration và một bộ kiểm thử Java 17/Spring Boot 3.x tái lập được.

## 1. Cú pháp và ý nghĩa

`@ConditionalOnWebApplication` thuộc package:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
```

Annotation có thuộc tính `type` kiểu `ConditionalOnWebApplication.Type`; **giá trị mặc định là `ANY`**.

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication.Type;

// Khớp với cả ứng dụng web Servlet và Reactive:
@ConditionalOnWebApplication
class AnyWebConfiguration {
}

// Tương đương mặc định, viết tường minh:
@ConditionalOnWebApplication(type = Type.ANY)
class ExplicitAnyWebConfiguration {
}

// Chỉ khi ứng dụng dùng Servlet web stack:
@ConditionalOnWebApplication(type = Type.SERVLET)
class ServletWebConfiguration {
}

// Chỉ khi ứng dụng dùng Reactive web stack:
@ConditionalOnWebApplication(type = Type.REACTIVE)
class ReactiveWebConfiguration {
}
```

Các lớp trên là **đoạn minh họa cú pháp**, chưa phải cấu hình auto-configuration được Boot nạp tự động; ví dụ chạy độc lập nằm ở phần 4.

| `type` | Khớp khi nào? | Thường dùng cho |
| --- | --- | --- |
| `Type.ANY` | Ứng dụng web **Servlet hoặc Reactive**. | Bean hỗ trợ web không phụ thuộc riêng một stack, như chính sách chung cho web app. |
| `Type.SERVLET` | Ứng dụng web dựa trên **Servlet**. | Cấu hình `jakarta.servlet.Filter`, `HandlerInterceptor` của Spring MVC, `ServletRegistrationBean`. |
| `Type.REACTIVE` | Ứng dụng web dựa trên **Reactive**. | Cấu hình `org.springframework.web.server.WebFilter`, `WebFluxConfigurer`, hạ tầng WebFlux. |

Trong **ứng dụng không phải web**, cả ba đều không khớp. `ANY` nghĩa là “**một trong hai kiểu web**”, **không** có nghĩa là bắt buộc đồng thời có Servlet và Reactive. `SERVLET` và `REACTIVE` xét loại **web application context**; chúng không nói rằng phương thức nghiệp vụ có dùng `Mono`/`Flux`, `CompletableFuture` hay gọi HTTP bất đồng bộ hay không.

## 2. Điều kiện được Spring Boot đánh giá như thế nào?

Annotation này là một điều kiện của Spring Boot được kiểm tra khi framework xử lý cấu hình và đăng ký bean definitions. Nó dùng thông tin **môi trường ứng dụng/context** và sự có mặt của các lớp web cần thiết để nhận diện loại web application. Vì vậy, chỉ có thư viện Servlet/WebFlux trong `pom.xml` **chưa đủ** để kết luận condition sẽ khớp: một `ApplicationContext` thông thường có thể vẫn là **non-web**.

Đối với một ứng dụng web do `SpringApplication` khởi tạo, Spring Boot chọn một `WebApplicationType` chủ đạo:

- `WebApplicationType.SERVLET`: sử dụng web context theo Servlet stack, thường là ứng dụng Spring MVC.
- `WebApplicationType.REACTIVE`: sử dụng web context theo Reactive stack, thường là ứng dụng Spring WebFlux.
- `WebApplicationType.NONE`: context không phải web.

**Phân biệt tên:** `WebApplicationType` là enum dùng để khởi tạo ứng dụng, còn `ConditionalOnWebApplication.Type` là enum dùng để mô tả điều kiện kích hoạt cấu hình. Chúng liên quan tới cùng loại môi trường nhưng **không phải cùng kiểu Java** và không thể hoán đổi trong annotation.

Bảng kỳ vọng với context phù hợp và các lớp web cần thiết có sẵn:

| Môi trường thực tế | `ANY` | `SERVLET` | `REACTIVE` |
| --- | :---: | :---: | :---: |
| Non-web (`NONE`) | Không | Không | Không |
| Web Servlet (`SERVLET`) | Có | Có | Không |
| Web Reactive (`REACTIVE`) | Có | Không | Có |

Khi một annotation áp dụng cho **cả lớp cấu hình**, các bean trong lớp đó chỉ được xét khi điều kiện lớp khớp. Khi annotation đặt trên **phương thức `@Bean`**, nó chỉ kiểm soát bean definition của phương thức tương ứng.

```java
// Trích đoạn minh họa: cấu hình chung có hai nhánh độc lập.
@AutoConfiguration
public class MyWebAutoConfiguration {

    @Bean
    @ConditionalOnWebApplication(type = Type.SERVLET)
    ServletSupport servletSupport() {
        return new ServletSupport();
    }

    @Bean
    @ConditionalOnWebApplication(type = Type.REACTIVE)
    ReactiveSupport reactiveSupport() {
        return new ReactiveSupport();
    }
}
```

Ở đây `ServletSupport`, `ReactiveSupport` là các lớp giả định của dự án; đoạn mã dùng để minh họa vị trí annotation, chưa phải chương trình biên dịch độc lập.

## 3. Tình huống dễ nhầm: có cả Spring MVC và WebFlux

Hai starter phổ biến:

- `spring-boot-starter-web`: dùng cho ứng dụng Spring MVC/Servlet.
- `spring-boot-starter-webflux`: dùng cho ứng dụng Spring WebFlux/Reactive; cũng cung cấp `WebClient`, thường được thêm vào dự án MVC chỉ để gọi HTTP không đồng bộ.

Nếu **cả hai starter** cùng có trên classpath, Spring Boot **mặc định ưu tiên MVC/Servlet** khi tự suy luận loại ứng dụng. Vì thế:

1. `@ConditionalOnWebApplication(type = SERVLET)` thường khớp.
2. `@ConditionalOnWebApplication(type = REACTIVE)` thường **không** khớp.
3. `@ConditionalOnWebApplication` hoặc `type = ANY` khớp vì ứng dụng vẫn là web.

Điều này **không mâu thuẫn** với việc thư viện WebFlux có mặt. **Có WebFlux trên classpath không đồng nghĩa đang chạy Reactive web server.** Ứng dụng MVC vẫn có thể sử dụng `WebClient`.

Khi muốn một ứng dụng Boot thật dùng Reactive dù cả hai starter đều có mặt, phải **chọn rõ loại ứng dụng**:

```properties
# src/main/resources/application.properties
spring.main.web-application-type=reactive
```

Hoặc khi khởi tạo thủ công:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

SpringApplication application = new SpringApplication(MyApplication.class);
application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
```

Đoạn thứ hai là **trích đoạn trong một phương thức `main(String[] args)`**; `MyApplication` và `args` phải được định nghĩa trong ứng dụng thực tế.

Tương tự, để **vô hiệu hóa môi trường web** khi ứng dụng có đủ dependency nhưng chỉ chạy tác vụ nền:

```properties
spring.main.web-application-type=none
```

Khi đó điều kiện `ANY`/`SERVLET`/`REACTIVE` không nên được giả định là khớp chỉ vì classpath vẫn chứa thư viện web.

Lưu ý riêng cho kiểm thử: `WebApplicationContextRunner` và `ReactiveWebApplicationContextRunner` (phần 4) tạo trực tiếp **context theo loại cần kiểm tra**. Chúng giúp thử từng nhánh trong isolation; đừng suy ra rằng việc thêm cấu hình `spring.main.web-application-type` vào một `ApplicationContextRunner` thông thường sẽ tự đổi loại context của runner đó.

## 4. Ví dụ kiểm thử chạy được với Java 17 và Spring Boot 3.x

Ví dụ sử dụng ba **auto-configuration** đơn giản, mỗi cấu hình chỉ tạo một marker bean nếu môi trường phù hợp. Ba context runner kiểm tra ba tình huống: non-web, Servlet, Reactive.

### 4.1. Cấu trúc dự án

```text
web-condition-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── ConditionalOnWebApplicationTest.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>web-condition-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Đưa cả `starter-web` và `starter-webflux` vào **để bộ kiểm thử có đầy đủ lớp của hai stack**. Ba runner vẫn tạo ba context khác nhau, do đó kết quả không phụ thuộc vào việc Boot mặc định chọn MVC cho một ứng dụng đầy đủ có cả hai starter.

### 4.2. Mã kiểm thử hoàn chỉnh

Tạo `src/test/java/demo/ConditionalOnWebApplicationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication.Type;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalOnWebApplicationTest {

    record Marker(String source) {
    }

    @AutoConfiguration
    @ConditionalOnWebApplication
    static class AnyWebAutoConfiguration {

        @Bean
        Marker anyWebMarker() {
            return new Marker("any");
        }
    }

    @AutoConfiguration
    @ConditionalOnWebApplication(type = Type.SERVLET)
    static class ServletAutoConfiguration {

        @Bean
        Marker servletMarker() {
            return new Marker("servlet");
        }
    }

    @AutoConfiguration
    @ConditionalOnWebApplication(type = Type.REACTIVE)
    static class ReactiveAutoConfiguration {

        @Bean
        Marker reactiveMarker() {
            return new Marker("reactive");
        }
    }

    private final AutoConfigurations configurations = AutoConfigurations.of(
            AnyWebAutoConfiguration.class,
            ServletAutoConfiguration.class,
            ReactiveAutoConfiguration.class
    );

    @Test
    void nonWebContextMatchesNone() {
        new ApplicationContextRunner()
                .withConfiguration(configurations)
                .run(context -> {
                    assertThat(context.containsBean("anyWebMarker")).isFalse();
                    assertThat(context.containsBean("servletMarker")).isFalse();
                    assertThat(context.containsBean("reactiveMarker")).isFalse();
                });
    }

    @Test
    void servletContextMatchesAnyAndServlet() {
        new WebApplicationContextRunner()
                .withConfiguration(configurations)
                .run(context -> {
                    assertThat(context.containsBean("anyWebMarker")).isTrue();
                    assertThat(context.containsBean("servletMarker")).isTrue();
                    assertThat(context.containsBean("reactiveMarker")).isFalse();
                    assertThat(context.getBean(
                            "servletMarker", Marker.class).source())
                            .isEqualTo("servlet");
                });
    }

    @Test
    void reactiveContextMatchesAnyAndReactive() {
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(configurations)
                .run(context -> {
                    assertThat(context.containsBean("anyWebMarker")).isTrue();
                    assertThat(context.containsBean("servletMarker")).isFalse();
                    assertThat(context.containsBean("reactiveMarker")).isTrue();
                    assertThat(context.getBean(
                            "reactiveMarker", Marker.class).source())
                            .isEqualTo("reactive");
                });
    }
}
```

`record Marker` là cú pháp Java 17 hợp lệ. Các auto-configuration lồng trong test được truyền **trực tiếp** qua `AutoConfigurations.of(…)`, nên ví dụ kiểm thử này **không cần** file `AutoConfiguration.imports`.

Chạy từ thư mục `web-condition-demo` (máy cần Java 17 và Maven):

```bash
mvn test
```

**Kết quả kỳ vọng:** cả ba test `nonWebContextMatchesNone`, `servletContextMatchesAnyAndServlet` và `reactiveContextMatchesAnyAndReactive` thành công. Lệnh sẽ tạo báo cáo Surefire; không khẳng định một dòng stdout cố định vì định dạng log Maven phụ thuộc cấu hình và phiên bản.

| Test | `anyWebMarker` | `servletMarker` | `reactiveMarker` |
| --- | :---: | :---: | :---: |
| `nonWebContextMatchesNone` | ✗ | ✗ | ✗ |
| `servletContextMatchesAnyAndServlet` | ✓ | ✓ | ✗ |
| `reactiveContextMatchesAnyAndReactive` | ✓ | ✗ | ✓ |

Giải thích từng test:

- `ApplicationContextRunner` tạo context chung; dù dependency có cả hai web starter, context này không phải một Servlet/Reactive web context, nên **cả ba điều kiện không khớp**.
- `WebApplicationContextRunner` mô phỏng web context Servlet; `ANY` và `SERVLET` khớp, `REACTIVE` không khớp.
- `ReactiveWebApplicationContextRunner` mô phỏng web context Reactive; `ANY` và `REACTIVE` khớp, `SERVLET` không khớp.
- Có **hai bean kiểu `Marker`** trong mỗi nhánh web của test là có chủ đích: ví dụ chỉ minh họa **điều kiện môi trường**, không dùng `@ConditionalOnMissingBean`. Các bean có **tên riêng**, nên không có lỗi trùng tên; truy xuất theo tên để tránh nhầm với injection theo kiểu khi có nhiều bean cùng kiểu.

### 4.3. Trong starter thực tế

Một thư viện có thể tách các cấu hình theo công nghệ:

```java
// Trích đoạn kiến trúc, không phải một file Java độc lập:
@AutoConfiguration
@ConditionalOnWebApplication(type = Type.SERVLET)
class ServletTracingAutoConfiguration {
    // Bean dùng jakarta.servlet.Filter hoặc Spring MVC.
}

@AutoConfiguration
@ConditionalOnWebApplication(type = Type.REACTIVE)
class ReactiveTracingAutoConfiguration {
    // Bean dùng org.springframework.web.server.WebFilter.
}

@AutoConfiguration
@ConditionalOnWebApplication
class CommonWebTracingAutoConfiguration {
    // Bean web chung nếu thật sự hỗ trợ cả hai môi trường.
}
```

Trong Spring Boot 3.x, đăng ký các lớp auto-configuration của thư viện trong tài nguyên `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, mỗi dòng là **tên class đầy đủ**. Đây là cơ chế nạp auto-configuration của starter thật; đừng yêu cầu người dùng `@ComponentScan` các class auto-config như cấu hình ứng dụng thông thường.

Nếu một bean còn cần điều kiện khác, có thể kết hợp:

```java
@Bean
@ConditionalOnWebApplication(type = Type.REACTIVE)
@ConditionalOnClass(name = "org.springframework.web.reactive.DispatcherHandler")
@ConditionalOnMissingBean(MyReactiveHandler.class)
MyReactiveHandler myReactiveHandler() {
    return new MyReactiveHandler();
}
```

Ví dụ này **giả định** `MyReactiveHandler` là lớp do thư viện định nghĩa và có constructor không tham số. `@ConditionalOnClass` xét dependency, `@ConditionalOnWebApplication` xét môi trường web, còn `@ConditionalOnMissingBean` cho phép bean tùy biến của ứng dụng thay thế mặc định. Với phương thức `@Bean`, hãy đặc biệt cẩn thận khi chữ ký phương thức nhắc đến class có thể **không tồn tại**; để kiểm tra classpath tùy chọn, thường nên tách class cấu hình lồng với condition ở **mức class**.

## 5. Chọn `ANY`, `SERVLET` hay `REACTIVE` theo yêu cầu

Chọn `ANY` khi bean thực sự làm việc trong **cả hai** web stack và không phụ thuộc trực tiếp vào Servlet API/Reactive API. Ví dụ cấu hình chung về metadata của ứng dụng web, miễn implementation không giả định có `HttpServletRequest` hoặc `ServerWebExchange`.

Chọn `SERVLET` khi bean sử dụng Servlet/Spring MVC contract, chẳng hạn `jakarta.servlet.Filter`, `HandlerInterceptor`, `ServletRegistrationBean`. Một Servlet filter không thể tự động coi là WebFlux `WebFilter`.

Chọn `REACTIVE` khi bean sử dụng WebFlux contract, chẳng hạn `WebFilter`, `WebFluxConfigurer` hoặc pipeline làm việc với `ServerWebExchange`. Đừng dùng `ANY` chỉ vì cả hai framework đều có từ “web” trong tên; kiểu bean cụ thể vẫn phải tương thích với runtime stack được chọn.

**Nếu cần hai implementation** cho cùng một feature, tách hai auto-configuration rồi dùng điều kiện riêng. Nếu thêm `@ConditionalOnMissingBean` để ứng dụng ghi đè cấu hình, định nghĩa **kiểu hợp đồng chung** một cách rõ ràng và lưu ý quan hệ thứ tự giữa các auto-configuration khi chúng có thể cùng đăng ký một mặc định.

## 6. Chẩn đoán điều kiện không khớp

Khi bean không xuất hiện, kiểm tra theo trình tự:

1. **Loại context:** ứng dụng thực tế đang chạy với `WebApplicationType.NONE`, `SERVLET` hay `REACTIVE`? Có cấu hình `spring.main.web-application-type` không?
2. **Classpath:** có servlet/webflux API cần thiết không? Nếu chạy `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner`, dependency đã đủ để tạo loại context tương ứng chưa?
3. **Annotation:** đang dùng `@ConditionalOnWebApplication` mặc định `ANY` hay viết tường minh `type = SERVLET/REACTIVE`? Annotation đặt ở lớp hay chỉ phương thức `@Bean`?
4. **Cơ chế nạp:** auto-configuration của thư viện đã được liệt kê trong `AutoConfiguration.imports` chưa? Có bị exclude bởi cấu hình khác không?
5. **Các điều kiện khác:** có `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` cùng áp dụng khiến bean không được đăng ký?
6. **Condition report:** bật debug khi chạy ứng dụng bằng đối số `--debug` để xem Condition Evaluation Report; đối với Actuator được bật và cho phép truy cập, endpoint `/actuator/conditions` cũng hỗ trợ phân tích kết quả.
7. **Kiểm thử tái lập:** dùng ba context runner như phần 4 để phân biệt lỗi ở điều kiện môi trường với lỗi do các auto-configuration khác.

Các nhầm lẫn thường gặp:

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Có dependency `spring-webflux` là `REACTIVE` chắc chắn khớp.” | WebFlux có thể được thêm chỉ để dùng `WebClient` trong ứng dụng MVC; context mới quyết định nhánh condition. |
| “`ANY` sẽ tạo hai bean khi có hai starter.” | `ANY` chỉ là một điều kiện; số bean tùy theo các phương thức/cấu hình được đăng ký. |
| “`SERVLET` nghĩa là code không được phép chạy bất đồng bộ.” | Servlet web stack vẫn hỗ trợ nhiều cách xử lý bất đồng bộ. |
| “`REACTIVE` nghĩa là mọi bean đều chạy trên Netty.” | Điều kiện nói tới loại web context; Reactive stack có thể có các lựa chọn runtime khác, không khóa chặt vào một server cụ thể. |
| “Thêm `@ConditionalOnWebApplication` khiến ứng dụng biến thành web app.” | Annotation **kiểm tra** môi trường; nó không thay đổi `WebApplicationType` hay tự dựng server. |
| “`spring.main.web-application-type=reactive` biến `ApplicationContextRunner` mặc định thành reactive context.” | Trong test điều kiện theo web context, chọn `ReactiveWebApplicationContextRunner`. |

## 7. Tự kiểm tra

**Câu 1:** Một ứng dụng chỉ dùng `spring-boot-starter-web` đang chạy Spring MVC. Điều kiện nào khớp?  
**Đáp án:** `ANY` và `SERVLET`.

**Câu 2:** Một ứng dụng dùng `spring-boot-starter-webflux` làm Reactive web server. Điều kiện nào khớp?  
**Đáp án:** `ANY` và `REACTIVE`.

**Câu 3:** Ứng dụng có cả hai starter và **không ép kiểu web**. Có thể mặc định xem `REACTIVE` là khớp vì class WebFlux tồn tại không?  
**Đáp án:** Không. Spring Boot mặc định ưu tiên MVC/Servlet khi cả hai stack có mặt.

**Câu 4:** Ứng dụng chạy command line với `spring.main.web-application-type=none` nhưng vẫn có starter web. `ANY` có khớp không?  
**Đáp án:** Không, vì môi trường chạy là non-web.

**Câu 5:** Muốn một starter cung cấp `Filter` cho MVC và `WebFilter` cho WebFlux thì nên dùng một cấu hình `ANY` cho cả hai bean?  
**Đáp án:** Không nên. Chia nhánh `SERVLET` và `REACTIVE` hoặc đặt condition riêng trên từng phương thức `@Bean`.

**Ghi nhớ:** `@ConditionalOnWebApplication` kiểm tra **môi trường web thật sự của ứng dụng** khi đăng ký cấu hình: `ANY` nhận cả hai loại web; `SERVLET` chỉ nhận Servlet; `REACTIVE` chỉ nhận Reactive. Kiểm thử cả ba bằng các context runner phù hợp và không nhầm **thư viện có trên classpath** với **loại web context đang chạy**.

### Tài liệu chính thức

- Spring Boot API — `@ConditionalOnWebApplication`: https://docs.spring.io/spring-boot/docs/3.3.5/api/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html
- Spring Boot API — `ConditionalOnWebApplication.Type`: https://docs.spring.io/spring-boot/docs/3.3.5/api/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.Type.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
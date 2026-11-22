# @ConditionalOnWebApplication, @ConditionalOnNotWebApplication và loại ứng dụng

Spring Boot có thể chạy ứng dụng theo nhiều kiểu: ứng dụng web dùng Spring MVC (Servlet), ứng dụng web dùng Spring WebFlux (Reactive), hoặc ứng dụng không chạy như một web application. Khi một cấu hình chỉ phù hợp với một kiểu ứng dụng, có thể dùng `@ConditionalOnWebApplication` và `@ConditionalOnNotWebApplication` để Spring Boot chỉ đăng ký cấu hình hoặc bean tương ứng.

Hai annotation này thường xuất hiện trong auto-configuration và thư viện dùng chung. Chúng giúp một thư viện cung cấp tích hợp cho nhiều loại ứng dụng mà không buộc tất cả ứng dụng phải có cùng web stack.

## 1. Ba loại ứng dụng Spring Boot

Spring Boot biểu diễn loại ứng dụng bằng `WebApplicationType`:

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| `SERVLET` | Ứng dụng web dựa trên Servlet API và Servlet container | Spring MVC, Spring Web MVC |
| `REACTIVE` | Ứng dụng web dựa trên reactive stack | Spring WebFlux với server reactive |
| `NONE` | Ứng dụng không khởi tạo web application context/server | Batch job, command-line application, worker |

Một ứng dụng `SERVLET` thường dùng Spring MVC và chạy trên Servlet container như Tomcat hoặc Jetty. Request được xử lý theo mô hình Servlet.

Một ứng dụng `REACTIVE` thường dùng Spring WebFlux với server reactive như Reactor Netty. Luồng xử lý dựa trên reactive types và non-blocking I/O khi các thành phần tham gia hỗ trợ cách vận hành này.

Ứng dụng `NONE` không khởi tạo web server. Nó vẫn có thể dùng Spring IoC, dependency injection, scheduling, messaging, database hoặc các thư viện HTTP client. Việc ứng dụng gọi HTTP tới một hệ thống khác không biến nó thành web application.

Ví dụ, một batch worker dùng `WebClient` để gửi dữ liệu tới API bên ngoài vẫn có thể là ứng dụng `NONE`. Web client là khả năng gọi dịch vụ từ xa; web application type mô tả kiểu context mà ứng dụng khởi tạo để phục vụ hoặc xử lý request.

## 2. @ConditionalOnWebApplication

`@ConditionalOnWebApplication` thuộc package:

~~~java
org.springframework.boot.autoconfigure.condition
~~~

Annotation này yêu cầu Spring Boot chỉ áp dụng cấu hình khi ứng dụng đang được nhận diện là web application. Nó có thuộc tính `type` để giới hạn web stack:

~~~java
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET
)
~~~

Các giá trị được hỗ trợ:

- `SERVLET`: chỉ khớp với ứng dụng web Servlet.
- `REACTIVE`: chỉ khớp với ứng dụng web Reactive.
- `ANY`: khớp với ứng dụng web thuộc một trong hai loại Servlet hoặc Reactive.

Nếu không khai báo `type`, giá trị mặc định là `ANY`. Vì vậy, annotation đơn giản dưới đây có nghĩa là cấu hình áp dụng cho cả ứng dụng Servlet và Reactive:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication
public class WebFeatureConfiguration {
}
~~~

Có thể đặt điều kiện ở cấp lớp cấu hình hoặc trên một phương thức `@Bean`. Khi đặt ở cấp lớp, điều kiện quyết định toàn bộ cấu hình có được xử lý hay không. Khi đặt ở phương thức, điều kiện chỉ quyết định bean được khai báo bởi phương thức đó có được đăng ký hay không.

### Chỉ áp dụng cho Servlet

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET
)
public class ServletWebConfiguration {

    @Bean
    WebStackDescriptor webStackDescriptor() {
        return new WebStackDescriptor("SERVLET");
    }
}
~~~

Cấu hình này chỉ được áp dụng khi context là ứng dụng web Servlet. Nó phù hợp với các thành phần tích hợp trực tiếp với Servlet API, chẳng hạn filter, interceptor hoặc một adapter dành cho Spring MVC.

### Chỉ áp dụng cho Reactive

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE
)
public class ReactiveWebConfiguration {

    @Bean
    WebStackDescriptor webStackDescriptor() {
        return new WebStackDescriptor("REACTIVE");
    }
}
~~~

Cấu hình này chỉ được áp dụng cho ứng dụng web Reactive. Các thành phần tích hợp có thể là `WebFilter`, `HandlerFilterFunction` hoặc adapter dành cho WebFlux.

Trong hai ví dụ trên, `WebStackDescriptor` là kiểu dữ liệu minh họa:

~~~java
public record WebStackDescriptor(String type) {
}
~~~

Trong ứng dụng thực tế, mỗi cấu hình thường khai báo các bean có chức năng riêng cho web stack tương ứng. Hai cấu hình trên cùng khai báo một bean tên `webStackDescriptor` để minh họa rằng chỉ cấu hình phù hợp được chọn trong một context. Nếu cả hai điều kiện cùng khớp do cấu hình hoặc cách dựng context không như dự kiến, cần kiểm tra lại loại ứng dụng và các định nghĩa bean.

## 3. @ConditionalOnNotWebApplication

`@ConditionalOnNotWebApplication` có ý nghĩa ngược với điều kiện web: cấu hình chỉ được áp dụng khi ứng dụng không được nhận diện là web application.

Ví dụ, một thư viện có thể cung cấp thành phần báo cáo dành cho batch worker:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
public class BatchSupportConfiguration {

    @Bean
    BatchAuditReporter batchAuditReporter() {
        return new BatchAuditReporter();
    }
}
~~~

Bean `BatchAuditReporter` chỉ được đăng ký trong ứng dụng không chạy theo kiểu web. Điều này hữu ích khi một thư viện cần cung cấp thành phần riêng cho command-line job, scheduler hoặc worker.

Annotation không có thuộc tính `type` để chọn Servlet hay Reactive, vì cả hai đều là web application. Nếu cần phân biệt giữa hai web stack, dùng `@ConditionalOnWebApplication(type = ...)`.

Có thể sử dụng `@ConditionalOnNotWebApplication` trên phương thức bean nếu chỉ một bean cần phụ thuộc vào điều kiện non-web:

~~~java
@Bean
@ConditionalOnNotWebApplication
BatchAuditReporter batchAuditReporter() {
    return new BatchAuditReporter();
}
~~~

## 4. Spring Boot xác định loại ứng dụng như thế nào?

Spring Boot xác định loại ứng dụng trong quá trình chuẩn bị khởi chạy. Việc suy luận dựa trên web stack có trên classpath và loại ApplicationContext được chọn. Có thể để Boot tự suy luận hoặc chỉ định rõ loại ứng dụng bằng thuộc tính:

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

Các giá trị thường dùng là:

- `servlet`
- `reactive`
- `none`

Ví dụ, để buộc ứng dụng chạy như non-web:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

Có thể truyền giá trị khi chạy JAR:

~~~bash
java -jar application.jar --spring.main.web-application-type=none
~~~

Hoặc chọn Reactive:

~~~bash
java -jar application.jar --spring.main.web-application-type=reactive
~~~

Khi thuộc tính này được đặt, nó điều khiển loại context mà Spring Boot sử dụng. Các điều kiện web sau đó được đánh giá theo loại ứng dụng đã chọn.

### Khi cả Spring MVC và WebFlux cùng có trên classpath

Một tình huống thường gặp là dự án có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`. Spring Boot ưu tiên Spring MVC khi cả hai stack đều có mặt và ứng dụng không được cấu hình rõ là Reactive.

Vì vậy, chỉ nhìn thấy dependency WebFlux trong build file chưa đủ để kết luận ứng dụng là Reactive. Một ứng dụng MVC vẫn có thể dùng `WebClient` từ WebFlux để gọi API bên ngoài.

Nếu thực sự muốn chạy theo Reactive stack, hãy cấu hình rõ:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Nếu muốn ứng dụng không khởi tạo web server dù có các thư viện web trên classpath, có thể đặt `none`. Sau khi thay đổi, cần kiểm tra loại context và các bean được đăng ký thực tế.

## 5. Kết hợp điều kiện web với điều kiện khác

Các điều kiện của Spring Boot có thể kết hợp trên cùng một lớp cấu hình hoặc bean. Ví dụ, một tích hợp Servlet chỉ được bật khi có thư viện cần thiết và thuộc tính chức năng được bật:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET
)
@ConditionalOnClass(name = "jakarta.servlet.Filter")
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
public class ServletAuditConfiguration {

    @Bean
    ServletAuditSupport servletAuditSupport() {
        return new ServletAuditSupport();
    }
}
~~~

Cấu hình chỉ được áp dụng khi đồng thời thỏa mãn các điều kiện:

1. Ứng dụng là web application kiểu Servlet.
2. Servlet API có trên classpath.
3. `app.audit.enabled` có giá trị `true`.

Nếu bất kỳ điều kiện nào không khớp, cấu hình này không đăng ký bean. Điều kiện classpath đặc biệt hữu ích cho thư viện tái sử dụng: ứng dụng không có Servlet API không cần tải các thành phần phụ thuộc Servlet.

Có thể tổ chức một bộ auto-configuration theo từng stack:

- Servlet configuration: `@ConditionalOnWebApplication(type = SERVLET)`.
- Reactive configuration: `@ConditionalOnWebApplication(type = REACTIVE)`.
- Shared web configuration: `@ConditionalOnWebApplication` với mặc định `ANY`.
- Non-web configuration: `@ConditionalOnNotWebApplication`.

Cách chia này giúp các phụ thuộc theo từng web stack không bị trộn lẫn. Một thư viện hỗ trợ cả MVC và WebFlux có thể cung cấp adapter riêng nhưng vẫn dùng chung service hoặc domain logic.

## 6. Ví dụ tổ chức một thư viện hỗ trợ nhiều loại ứng dụng

Giả sử thư viện audit cần cung cấp ba cách tích hợp:

- Servlet filter cho Spring MVC.
- Reactive web filter cho Spring WebFlux.
- Bộ ghi nhận sự kiện theo batch cho ứng dụng non-web.

Có thể tổ chức các cấu hình như sau:

~~~text
audit/
├── ServletAuditConfiguration
│   └── ServletAuditFilter
├── ReactiveAuditConfiguration
│   └── ReactiveAuditWebFilter
└── NonWebAuditConfiguration
    └── BatchAuditReporter
~~~

Mỗi lớp cấu hình chỉ đăng ký adapter phù hợp:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET
)
class ServletAuditConfiguration {

    @Bean
    ServletAuditFilter servletAuditFilter() {
        return new ServletAuditFilter();
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE
)
class ReactiveAuditConfiguration {

    @Bean
    ReactiveAuditWebFilter reactiveAuditWebFilter() {
        return new ReactiveAuditWebFilter();
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
class NonWebAuditConfiguration {

    @Bean
    BatchAuditReporter batchAuditReporter() {
        return new BatchAuditReporter();
    }
}
~~~

Nếu đóng gói thành Spring Boot auto-configuration, các lớp cấu hình này có thể được công bố trong file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Các điều kiện trên từng cấu hình quyết định adapter nào được đăng ký. Trong thiết kế thực tế, có thể dùng `@AutoConfiguration` thay cho `@Configuration` để thể hiện rõ vai trò auto-configuration và bổ sung các điều kiện classpath, property hoặc bean cần thiết.

Phần logic audit dùng chung nên nằm trong service hoặc component độc lập với Servlet và Reactive. Các adapter chỉ chuyển request/event của từng stack sang hợp đồng dùng chung. Nhờ đó, ứng dụng batch không cần kéo theo Servlet filter và ứng dụng MVC không phải đăng ký Reactive web filter.

## 7. Điều kiện được đánh giá khi nào?

Các annotation `@ConditionalOnWebApplication` và `@ConditionalOnNotWebApplication` được đánh giá trong quá trình Spring phân tích cấu hình và đăng ký bean definition.

Chúng quyết định cấu hình hoặc bean có tham gia ApplicationContext hay không. Chúng không phải cơ chế bật/tắt bean theo từng request, cũng không tự đánh giá lại khi ứng dụng đổi loại web trong lúc đang chạy.

Ví dụ, nếu ứng dụng khởi động với:

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

thì cấu hình Servlet được chọn trong quá trình khởi tạo context. Việc đổi file YAML thành `reactive` khi ứng dụng đã chạy không tự thay thế context Servlet bằng context Reactive. Muốn đổi loại ứng dụng, cần khởi động một ApplicationContext mới với cấu hình tương ứng.

Cũng không nên hiểu điều kiện web là phép kiểm tra cổng HTTP đang mở. Điều kiện được dùng trong quá trình tạo context; trạng thái server đã bind port hay chưa là một khía cạnh khác của vòng đời ứng dụng.

## 8. Kiểm tra điều kiện theo loại ứng dụng

Khi viết auto-configuration, cần kiểm tra cả trường hợp Servlet, Reactive và non-web. Một cấu hình có thể hoạt động trong ứng dụng chính nhưng vô tình làm hỏng ứng dụng khác nếu thiếu điều kiện hoặc phụ thuộc sai web stack.

Có thể sử dụng các context runner trong Spring Boot Test để dựng context theo loại tương ứng:

- `ApplicationContextRunner` cho cấu hình non-web thông thường.
- `WebApplicationContextRunner` cho Servlet web context.
- `ReactiveWebApplicationContextRunner` cho Reactive web context.

Các runner cho phép nạp lớp cấu hình, kiểm tra bean có mặt hoặc vắng mặt mà không cần khởi chạy toàn bộ ứng dụng. Khi kiểm tra auto-configuration, có thể kết hợp runner với `FilteredClassLoader` để mô phỏng trường hợp một thư viện hoặc API không có trên classpath.

Ngoài ra, có thể kiểm tra ứng dụng qua các cấu hình khởi chạy:

| Trường hợp | Cấu hình loại ứng dụng | Kết quả cần xác nhận |
|---|---|---|
| Spring MVC | `servlet` | Cấu hình Servlet được đăng ký |
| Spring WebFlux | `reactive` | Cấu hình Reactive được đăng ký |
| Batch/CLI | `none` | Cấu hình non-web được đăng ký |
| Có MVC và WebFlux | Mặc định của Boot hoặc chỉ định rõ | Xác nhận đúng stack thực tế |
| Không có dependency web | Không có web stack | Cấu hình non-web hoạt động |
| Tắt chức năng bằng property | Ví dụ `app.audit.enabled=false` | Cấu hình có thêm điều kiện property không được đăng ký |

Nếu một bean không xuất hiện như mong đợi, hãy kiểm tra loại context thực tế, dependency trên classpath, thuộc tính `spring.main.web-application-type` và báo cáo điều kiện. Spring Boot Actuator có thể cung cấp endpoint `conditions` trong môi trường được cấu hình phù hợp để xem các condition match hoặc không match; không nên công khai endpoint chẩn đoán này ngoài phạm vi quản trị an toàn.

## 9. Những nhầm lẫn thường gặp

### Có WebClient nghĩa là ứng dụng Reactive

Không đúng. `WebClient` là HTTP client có thể được dùng trong ứng dụng Servlet hoặc non-web. Điều kiện Reactive web application nói về web stack và context của ứng dụng, không chỉ việc có một reactive client trên classpath.

### Có dependency WebFlux nghĩa là ứng dụng chắc chắn Reactive

Không đúng. Nếu Spring MVC cũng có mặt, Spring Boot mặc định ưu tiên MVC trừ khi loại ứng dụng được cấu hình rõ là Reactive. Hãy kiểm tra loại context được tạo thay vì chỉ nhìn một dependency.

### Dùng @ConditionalOnWebApplication mà không chỉ định type cho cấu hình chỉ hỗ trợ Servlet

Mặc định annotation khớp cả Servlet và Reactive. Nếu bean sử dụng API chỉ có ở Servlet stack, hãy chỉ định `type = SERVLET` và thêm điều kiện classpath phù hợp khi cần.

### Dùng @ConditionalOnNotWebApplication để kiểm tra ứng dụng không có thư viện web

Hai khái niệm không hoàn toàn giống nhau. Điều kiện non-web kiểm tra loại ứng dụng/context được khởi tạo. Nó không phải phép kiểm tra tổng quát rằng mọi thư viện web đều vắng mặt khỏi classpath. Một ứng dụng có thể có dependency web nhưng được cấu hình chạy với loại `NONE`.

### Mong điều kiện tự đổi khi runtime configuration thay đổi

Condition được đánh giá trong quá trình xây dựng context. Nó không tự chuyển bean khi property hoặc web mode thay đổi trong runtime. Thay đổi loại ứng dụng cần một lần khởi tạo context phù hợp.

## 10. Quy trình chọn điều kiện

Khi viết một cấu hình chỉ dành cho một loại ứng dụng, có thể quyết định theo trình tự:

1. Xác định cấu hình có cần web context hay có thể dùng trong mọi loại ứng dụng.
2. Nếu cần web, xác định API phụ thuộc là Servlet, Reactive hay dùng chung cho cả hai.
3. Dùng `@ConditionalOnWebApplication(type = SERVLET)` cho tích hợp Servlet.
4. Dùng `@ConditionalOnWebApplication(type = REACTIVE)` cho tích hợp Reactive.
5. Dùng `@ConditionalOnWebApplication` khi cấu hình thực sự hỗ trợ cả hai web stack.
6. Dùng `@ConditionalOnNotWebApplication` cho cấu hình chỉ dành cho ứng dụng non-web.
7. Kết hợp `@ConditionalOnClass`, `@ConditionalOnProperty` hoặc `@ConditionalOnMissingBean` nếu cấu hình còn phụ thuộc vào classpath, tùy chọn hoặc bean do người dùng cung cấp.
8. Kiểm tra context theo từng loại ứng dụng và xác nhận tập bean được đăng ký.

Hai annotation này giúp Spring Boot điều chỉnh cấu hình theo loại ApplicationContext mà ứng dụng khởi tạo. Khi phân biệt đúng Servlet, Reactive và non-web, thư viện có thể cung cấp các adapter phù hợp, giữ phần nghiệp vụ dùng chung độc lập với web stack và tránh tạo bean phụ thuộc vào API không tồn tại trong loại ứng dụng hiện tại.


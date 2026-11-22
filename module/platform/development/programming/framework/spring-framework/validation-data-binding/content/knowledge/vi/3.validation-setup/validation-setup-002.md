# Vai trò của spring-beans, spring-core, spring-context và mô-đun web trong Spring Framework

## 1. Bức tranh tổng thể

Spring Framework được chia thành nhiều mô-đun có trách nhiệm rõ ràng. Khi xây dựng ứng dụng web, chúng ta thường thấy bốn nhóm sau xuất hiện cùng nhau:

- **spring-core**: nền tảng tiện ích và cơ chế cốt lõi mà các mô-đun Spring khác dùng chung.
- **spring-beans**: định nghĩa, tạo, cấu hình và quản lý bean, bao gồm các quan hệ phụ thuộc giữa những object.
- **spring-context**: xây dựng `ApplicationContext` trên cơ sở bean factory, cung cấp môi trường cấu hình và các dịch vụ cấp ứng dụng.
- **Các mô-đun web** (điển hình `spring-web`, `spring-webmvc`, `spring-webflux`): tích hợp giao thức HTTP, xử lý request/response và xây dựng ứng dụng web theo mô hình servlet hoặc reactive.

Cần hiểu quan hệ này theo chiều **nền tảng → container → ngữ cảnh ứng dụng → web**. Không phải mọi ứng dụng Spring đều cần web; một ứng dụng command-line vẫn có thể dùng core, beans và context. Ngược lại, Spring MVC cần một ứng dụng Spring và các phần web phù hợp để xử lý request.

```text
                Ứng dụng web
                 /       \
         Spring MVC     WebFlux
             |             |
         spring-web    spring-webflux
              \          /
            spring-context
                  |
             spring-beans
                  |
              spring-core
```

Sơ đồ chỉ minh họa các lớp trách nhiệm chính, không phải biểu đồ phụ thuộc Maven đầy đủ. Mỗi mô-đun còn có các phụ thuộc khác (ví dụ `spring-aop`, `spring-expression`, `spring-jcl` hoặc thư viện nền tảng) tùy chức năng và phiên bản.

## 2. spring-core: nền tảng cơ chế và tiện ích

`spring-core` cung cấp nhiều building block để Framework hoạt động. Những khái niệm cần nhận biết:

1. **Resource abstraction**: `Resource`, `ClassPathResource`, `FileSystemResource` và các API đọc tài nguyên theo cách thống nhất, thay vì để mỗi mô-đun tự xử lý classpath/file/URL.
2. **Type conversion**: `ConversionService`, `Converter<S,T>`, `ConverterFactory` và `GenericConverter` cho phép chuyển dữ liệu giữa các kiểu Java.
3. **Type/introspection utilities**: hỗ trợ phân tích metadata, reflection, generic type và các tiện ích collection/string cần cho framework.
4. **Environment-related foundational APIs**: các abstraction nền tảng mà lớp context có thể dựa vào để xử lý thuộc tính và cấu hình.
5. **Spring utilities**: một số công cụ nội bộ/tiện ích có thể dùng trực tiếp khi phù hợp, nhưng không nên phụ thuộc vào các API nội bộ không ổn định.

Ví dụ sử dụng chuyển đổi kiểu trực tiếp, không cần một web server:

```java
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

public class CoreConversionDemo {
    public static void main(String[] args) {
        ConversionService conversionService = new DefaultConversionService();
        Integer port = conversionService.convert("8080", Integer.class);
        System.out.println(port);
    }
}
```

Output khi chạy với Spring Core trên runtime classpath:

```text
8080
```

`CoreConversionDemo.java` là chương trình có `main` hợp lệ nhưng **phải có các dependency Spring tương ứng trên compile/runtime classpath**. Chạy `javac CoreConversionDemo.java` thuần túy mà không cấp JAR Spring sẽ báo thiếu package; ví dụ không ngụ ý JDK tự chứa Spring.

**Ranh giới:** `spring-core` không tự đóng vai trò IoC container và không tự khởi động ứng dụng HTTP. `ConversionService` là API chung, còn Spring MVC chọn và sử dụng conversion service thông qua cơ chế data binding của web layer.

## 3. spring-beans: tạo và quản lý các object ứng dụng

`spring-beans` là phần cốt lõi của IoC container. Nó cung cấp các API như:

- `BeanFactory`: giao diện truy xuất bean bằng tên/kiểu; container có thể tạo object và phân giải dependency.
- `BeanDefinition`: metadata mô tả cách tạo bean, class, scope và các thiết lập liên quan.
- `DefaultListableBeanFactory`: implementation thường gặp để đăng ký và quản lý bean definitions.
- `BeanPostProcessor`: mở rộng quá trình khởi tạo bean, can thiệp vào các giai đoạn trước/sau initialization.
- `BeanWrapper` và hạ tầng property binding: hỗ trợ truy cập/cập nhật thuộc tính JavaBean và chuyển đổi dữ liệu.

**Dependency Injection (DI)** là một ứng dụng quan trọng của IoC: thay vì tự tạo dependency bằng `new` khắp nơi, object nhận các thành phần cần thiết qua constructor (thường được ưu tiên), setter hoặc injection khác. Container chịu trách nhiệm lắp ghép object graph.

Ví dụ sử dụng trực tiếp `BeanFactory`:

```java
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;

public class BeanFactoryDemo {
    public static class GreetingService {
        public String greet() {
            return "Xin chào";
        }
    }

    public static void main(String[] args) {
        DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
        factory.registerBeanDefinition(
                "greetingService",
                BeanDefinitionBuilder
                        .genericBeanDefinition(GreetingService.class)
                        .getBeanDefinition()
        );

        GreetingService service = factory.getBean(
                "greetingService", GreetingService.class);
        System.out.println(service.greet());
    }
}
```

Output (khi Spring Beans và các dependency đi kèm có mặt):

```text
Xin chào
```

Ví dụ minh họa cách container lưu `BeanDefinition` và trả về bean. Với `BeanFactory` thuần, đừng mặc định mọi tiện ích mà `ApplicationContext` kích hoạt sẵn cũng được đăng ký hoặc vận hành giống nhau. Trong ứng dụng thực tế, thường ưu tiên `ApplicationContext` thay cho tự quản lý `DefaultListableBeanFactory`.

### Scope, lifecycle và dependency

Theo mặc định, bean trong container Spring thường có scope **singleton trên mỗi IoC container**: một instance được dùng lại cho các lần yêu cầu bean definition tương ứng; điều đó **không có nghĩa singleton trên toàn JVM**. Các scope như `prototype`, `request` và `session` mang ý nghĩa khác và một số scope chỉ sẵn có trong ngữ cảnh web.

Với singleton, Spring quản lý initialization và destruction callbacks của bean khi container hoạt động/đóng. Với prototype, container tạo instance mới theo yêu cầu nhưng không tự quản lý toàn bộ giai đoạn destruction sau khi trao bean cho caller. Đó là điểm quan trọng khi bean nắm tài nguyên cần đóng.

## 4. spring-context: ApplicationContext và dịch vụ cấp ứng dụng

`spring-context` cung cấp lớp trừu tượng `ApplicationContext`, mở rộng năng lực của `BeanFactory`. Ngoài quản lý bean, nó hỗ trợ các mô hình thường dùng trong một ứng dụng:

- **Application events** qua `ApplicationEventPublisher` và `@EventListener`.
- **Internationalization** qua `MessageSource` và locale.
- **Resource loading** và môi trường ứng dụng (`Environment`, property sources, profiles).
- **Lifecycle orchestration**: refresh/close context và nhiều hook cấp ứng dụng.
- **Annotation-driven configuration** với `@Configuration`, `@Bean`, `@ComponentScan` và `AnnotationConfigApplicationContext`.

Ví dụ Java 17+ về constructor injection, không phụ thuộc HTTP:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ContextDemo {
    public static final class Repository {
        public String value() { return "DATA"; }
    }

    public static final class Service {
        private final Repository repository;

        public Service(Repository repository) {
            this.repository = repository;
        }

        public String read() {
            return repository.value();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean Repository repository() {
            return new Repository();
        }

        @Bean Service service(Repository repository) {
            return new Service(repository);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Service service = context.getBean(Service.class);
            System.out.println(service.read());
        }
    }
}
```

Output:

```text
DATA
```

Điểm cần quan sát: `service(Repository repository)` khai báo dependency bằng tham số method `@Bean`. Container chọn bean phù hợp, tạo và cung cấp instance. `try-with-resources` đóng context, giúp thực hiện quy trình shutdown và destroy callbacks phù hợp.

### ApplicationContext và BeanFactory khác gì?

| Tiêu chí | BeanFactory | ApplicationContext |
| --- | --- | --- |
| Vai trò chính | Container API cơ bản để lấy/cấu hình bean | Application-level container xây trên BeanFactory |
| Cấu hình bean | Có thể đăng ký định nghĩa và processor thủ công | Thường tích hợp annotation configuration và tự chuẩn bị hạ tầng |
| Event, message, environment | Không phải toàn bộ dịch vụ mặc định của giao diện gốc | Hỗ trợ các dịch vụ cấp ứng dụng |
| Lifecycle | Phụ thuộc implementation và thiết lập | Có `refresh`, `close` qua các context tương ứng |
| Cách dùng thường gặp | Framework internals hoặc tình huống đặc thù | Phần lớn ứng dụng Spring |

Đừng suy luận `ApplicationContext` là một process hoặc service riêng: nó là object/container sống trong JVM ứng dụng.

## 5. Các mô-đun web: từ HTTP đến controller

Các thành phần web kế thừa cơ sở container/context nhưng giải quyết vấn đề ở tầng khác: nhận HTTP request, chọn handler, ánh xạ tham số, điều phối xử lý, chuyển dữ liệu và tạo response.

### 5.1. spring-web

`spring-web` cung cấp nhiều thành phần web chung, ví dụ:

- Các abstraction cho web context và hạ tầng liên quan servlet.
- HTTP message conversion và các kiểu hỗ trợ request/response.
- Những API/tiện ích phục vụ web integration, HTTP client trong các cấu hình phù hợp.
- Hạ tầng hỗ trợ các phần MVC/WebFlux ở các mức khác nhau.

`spring-web` **không tương đương với một ứng dụng Spring MVC hoàn chỉnh**. Phần MVC gồm các cơ chế handler mapping, controller invocation, view resolution và `DispatcherServlet` nằm trong `spring-webmvc`.

### 5.2. spring-webmvc

Spring MVC là mô hình web truyền thống dựa trên Servlet API. Những khối chính:

1. **Servlet container** (ví dụ Tomcat) nhận kết nối HTTP, gọi `DispatcherServlet`.
2. **`DispatcherServlet`** là front controller điều phối request.
3. **`HandlerMapping`** tìm handler phù hợp với URL/method/điều kiện mapping.
4. **`HandlerAdapter`** thực thi handler/controller, thường gọi argument resolvers và data binders.
5. **`ConversionService`**, validators và `HttpMessageConverter` hỗ trợ chuyển/đọc/ghi dữ liệu theo ngữ cảnh.
6. **ViewResolver** phục vụ response dạng view khi sử dụng MVC views; với `@ResponseBody` hoặc `@RestController`, response thường được serialize qua message converters.

Ví dụ REST endpoint:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {
    @GetMapping("/status/{code}")
    public String status(@PathVariable int code) {
        return "status=" + code;
    }
}
```

Trong ứng dụng Spring MVC đã khởi động và đăng ký controller, `GET /status/200` trả body `status=200`. String `"200"` từ path được convert thành `int` khi resolve tham số; controller dựa trên DI/container của Spring, còn web layer điều phối HTTP. Đây là một **thành phần ứng dụng**, không phải class Java độc lập có `main`.

### 5.3. spring-webflux

`spring-webflux` là web stack reactive, dùng `Mono`/`Flux` từ Reactor và hỗ trợ runtime theo mô hình non-blocking. Nó có thể chạy trên runtime phù hợp như Reactor Netty hoặc Servlet container hỗ trợ cấu hình tương ứng.

WebFlux cung cấp programming model annotation-based controllers và functional routing, nhưng request pipeline/adapter khác MVC. Không nên cho rằng thêm `spring-webflux` vào classpath sẽ tự động chuyển toàn bộ một ứng dụng MVC sang reactive hoặc làm code blocking trở thành non-blocking. Lựa chọn stack cần dựa trên tính chất workload, API, dependency và runtime triển khai.

## 6. Luồng phối hợp các mô-đun khi request đến

Giả sử một web app cung cấp `GET /users/7`:

```text
HTTP GET /users/7
       |
       v
Servlet container -> DispatcherServlet      (spring-webmvc)
       |
       v
HandlerMapping + HandlerAdapter             (spring-webmvc)
       |
       +--> resolve path variable "7"
       |       -> convert String sang long  (spring-core conversion API,
       |                                     binder/web integration)
       v
UserController                             (bean trong ApplicationContext)
       |
       v
UserService                                (bean do spring-beans tạo/tiêm)
       |
       v
UserRepository                             (dependency được inject)
       |
       v
HTTP response                              (spring-web / spring-webmvc)
```

`spring-context` chịu trách nhiệm context chứa các bean và configuration, `spring-beans` đảm nhiệm object graph và injection, `spring-core` cung cấp nền tảng tiện ích/conversion; còn MVC xử lý phần HTTP. Chúng **phối hợp**, không phải bốn framework cạnh tranh.

### Tham số request và JSON là hai đường khác nhau

Với `@PathVariable`, `@RequestParam`, `@ModelAttribute`, Spring thường dùng hạ tầng conversion/binding để đi từ chuỗi sang kiểu đích.

Với `@RequestBody` chứa JSON, framework dùng `HttpMessageConverter` và thư viện serialization/deserialization được cấu hình (thường Jackson) để tạo object. Vì vậy, `Converter<String, X>` do ứng dụng đăng ký vào `ConversionService` không mặc nhiên trở thành JSON deserializer của Jackson.

## 7. Phụ thuộc và cấu hình trong ứng dụng thực tế

Ở dự án sử dụng Spring Boot, cách thường gặp nhất là khai báo **starter** tương ứng, thay vì thêm từng JAR Spring bằng tay. Ví dụ Gradle (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Starter web có nhiệm vụ kéo vào web stack MVC cùng các thành phần Spring thiết yếu theo dependency management của Boot và một embedded server phù hợp. Phiên bản Spring Framework được chọn thống nhất theo Spring Boot BOM/plugin; không nên tự ghép `spring-webmvc` phiên bản khác với `spring-context` nếu không có lý do và kiểm thử chặt chẽ.

Với reactive stack, có thể dùng starter WebFlux:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Nếu khai báo cả hai starter trong cùng ứng dụng Spring Boot, web application type mặc định thường là servlet/MVC khi MVC hiện diện. Muốn chủ đích reactive cần hiểu và cấu hình rõ môi trường; không dựa vào thứ tự khai báo Gradle.

Trong ứng dụng Spring Framework thuần (không dùng Boot), cần cấu hình context, controller registration, servlet/reactive runtime và hạ tầng MVC/WebFlux phù hợp. Thêm dependency là điều kiện cần nhưng chưa đủ để endpoint chạy.

### Những vấn đề classpath phổ biến

- **`ClassNotFoundException` / `NoClassDefFoundError`**: có thể thiếu JAR cần thiết hoặc classpath runtime không đồng nhất.
- **`NoSuchMethodError`**: thường gợi ý xung đột phiên bản binary giữa các JAR.
- **Không tìm thấy bean**: vấn đề context/component scan/`@Bean`/profile/điều kiện tạo bean, không tự động kết luận lỗi `spring-core`.
- **HTTP 404 dù có controller**: cần kiểm tra request mapping, controller có nằm trong context MVC không, servlet path và cấu hình route.
- **Đăng ký converter nhưng không được dùng**: kiểm tra registry của conversion service đang phục vụ đúng luồng binding.
- **Bean scope không phù hợp**: không inject state request vào singleton mà thiếu mô hình scope/proxy hoặc thiết kế rõ ràng.

## 8. Kiểm thử theo từng lớp

Có thể xác minh trách nhiệm của từng mô-đun bằng các mức kiểm thử khác nhau:

1. **Core**: tạo `DefaultConversionService` và kiểm thử conversion của từng chuỗi, gồm input sai.
2. **Beans**: tạo `DefaultListableBeanFactory`, đăng ký bean definition và kiểm tra dependency/lifecycle khi cần.
3. **Context**: dùng `AnnotationConfigApplicationContext` để kiểm tra `@Configuration`, `@Bean` và dependency injection, không cần web server.
4. **Web MVC**: dùng integration test hoặc `MockMvc` với context phù hợp để kiểm tra mapping, binding, validation và status/response.
5. **WebFlux**: dùng công cụ kiểm thử reactive tương ứng (ví dụ `WebTestClient`) và kiểm tra cả xử lý lỗi lẫn hành vi bất đồng bộ khi cần.

Việc kiểm thử theo tầng giúp nhận diện lỗi ở đúng trách nhiệm. Một unit test của `ConversionService` không chứng minh endpoint HTTP đã được đăng ký; ngược lại, một request thành công cũng không kiểm tra hết mọi converter và lifecycle behavior.

## 9. Ghi nhớ và áp dụng

| Nhu cầu | Mô-đun/lớp nên bắt đầu tìm hiểu |
| --- | --- |
| Chuyển chuỗi thành kiểu Java, đọc resource, tiện ích nền | `spring-core`, `ConversionService`, `Resource` |
| Tạo, cấu hình, inject bean | `spring-beans`, `BeanFactory`, `BeanDefinition` |
| Quản lý context, `@Configuration`, event, profile, messages | `spring-context`, `ApplicationContext` |
| HTTP abstractions, integration và message conversion | `spring-web` |
| Servlet-based request routing, controller, MVC pipeline | `spring-webmvc`, `DispatcherServlet` |
| Reactive HTTP pipeline, `Mono`/`Flux`, functional router | `spring-webflux` |

Khi đọc stack trace, tài liệu hoặc dependency tree, hãy phân loại vấn đề theo nhóm này trước: **cơ chế nền tảng**, **bean container**, **application context**, hay **web request pipeline**. Từ đó tìm đúng extension point và tránh cấu hình sai tầng.
# Lỗi ScopeNotActiveException khi phạm vi chưa hoạt động trong Spring Framework

## 1. Bối cảnh: bean có scope nhưng không có ngữ cảnh hoạt động

Spring Core Container có thể quản lý các bean thuộc `singleton`, `prototype` và những scope gắn với môi trường web như `request`, `session`, `application`. Một bean được **đăng ký** thành công không có nghĩa scope của nó đang **hoạt động tại mọi thời điểm và mọi thread**.

Ví dụ, `@RequestScope` yêu cầu một HTTP request hiện hành. Khi một singleton service gọi method trên request-scoped proxy từ `ApplicationRunner` lúc ứng dụng khởi động, từ `@Scheduled`, hoặc từ một thread chạy nền không có request context, Spring thường không tìm thấy target request bean và báo `ScopeNotActiveException`.

Mục tiêu bài học:

- Hiểu chính xác ngoại lệ `ScopeNotActiveException` xuất hiện khi nào và tầng nào phát sinh.
- Phân biệt **scope đã đăng ký** với **scope đang active**; phân biệt scope, bean definition, target bean và scoped proxy.
- Lần theo `Caused by` để xác định thiếu request context, gọi bean quá sớm, chuyển thread hoặc cấu hình web không phù hợp.
- Tái hiện lỗi bằng ví dụ Spring Boot/Java 17 chạy được, đối chiếu truy cập ngoài HTTP request và trong controller.
- Áp dụng cách sửa theo nguyên nhân: thay thời điểm gọi, lấy dữ liệu trong request rồi truyền sang background task, dùng `ObjectProvider` đúng chỗ, cấu hình `RequestContextListener`/`RequestContextFilter` khi thực sự cần.
- Tránh các cách sửa sai như dùng `ThreadLocal` thủ công, sao chép servlet request sang thread tùy ý hoặc đổi bean thành singleton chỉ để hết lỗi.

Phạm vi chính là **Spring Framework Servlet/MVC** với các web scope và bean phụ thuộc khác vòng đời. Spring WebFlux dùng mô hình reactive context riêng, được lưu ý ở phần cuối.

## 2. `ScopeNotActiveException` là gì?

`org.springframework.beans.factory.support.ScopeNotActiveException` là một subtype của `BeanCreationException`, được Spring Framework giới thiệu từ phiên bản 5.3 để báo rằng **scope đích của một bean không active**, ví dụ request/session scope. Khi Spring yêu cầu target bean từ một scope đã đăng ký nhưng không thể hoạt động trong ngữ cảnh hiện tại, ngoại lệ này có thể được phát sinh.

Một stack trace thường có hình thức gần như:

~~~text
org.springframework.beans.factory.support.ScopeNotActiveException:
Error creating bean with name 'scopedTarget.requestToken':
Scope 'request' is not active for the current thread;
consider defining a scoped proxy for this bean if you intend
to refer to it from a singleton

Caused by: java.lang.IllegalStateException:
No thread-bound request found: Are you referring to request
attributes outside of an actual web request, or processing a
request outside of the originally receiving thread?
~~~

Đây là **ví dụ rút gọn, mang tính minh họa**. Văn bản chính xác của thông báo, tên bean và các stack frames có thể thay đổi giữa các phiên bản Spring và cấu hình.

Các dấu hiệu cần đọc:

- `ScopeNotActiveException`: Spring đang yêu cầu target bean của một scope không active.
- `scopedTarget.requestToken`: trong trường hợp có scoped proxy, bean đích thực có thể được Spring đặt tên bằng tiền tố `scopedTarget.`; tên thật phụ thuộc bean definition.
- `Scope 'request' is not active for the current thread`: thời điểm lookup, thread hiện hành không có request attributes hợp lệ cho scope request.
- `Caused by: No thread-bound request found`: nguyên nhân trực tiếp thường nằm tại `RequestContextHolder.currentRequestAttributes()`, không phải thiếu dependency Java.
- Đoạn “consider defining a scoped proxy” là gợi ý chung của exception; **ngay cả khi đã có proxy**, vẫn có thể nhận thông báo đó nếu gọi proxy ngoài request.

**Không nên bắt exception rồi trả giá trị mặc định một cách mù quáng**. Nếu nghiệp vụ bắt buộc có thông tin của HTTP request, lỗi này thường cho thấy luồng thực thi đang sử dụng context sai hoặc đã vượt khỏi vòng đời request.

## 3. Scope được đăng ký khác với scope đang hoạt động

Hai điều kiện độc lập cần được thỏa mãn:

| Điều kiện | Ý nghĩa | Khi thiếu |
| --- | --- | --- |
| **Scope đã đăng ký** | `BeanFactory` biết cách lấy bean thuộc `request`, `session` hay custom scope | Có thể báo `IllegalStateException: No Scope registered for scope name 'request'` |
| **Scope đang active** | Tại thời điểm lookup có ngữ cảnh hợp lệ, ví dụ `RequestAttributes` được bind cho thread xử lý HTTP request | Có thể báo `ScopeNotActiveException` với root cause “No thread-bound request found” |

`@RequestScope` hoặc `@Scope("request")` khai báo **scope của bean**, không tự tạo một HTTP request hay kích hoạt request context cho mã chạy nền.

Ví dụ các tình huống:

| Nơi thực thi | Request scope có sẵn? | Lưu ý |
| --- | --- | --- |
| Controller Spring MVC xử lý request qua `DispatcherServlet` | Thông thường **có** | `DispatcherServlet` cung cấp request attributes |
| Service singleton được controller gọi đồng bộ trong cùng thread request | Thông thường **có** | Scoped proxy/lookup dùng đúng request |
| Constructor hoặc `@PostConstruct` của singleton lúc startup | Thông thường **không** | Tạo singleton không đồng nghĩa có HTTP request |
| `ApplicationRunner`/`CommandLineRunner` | Thông thường **không** | Dù embedded server đã khởi tạo |
| `@Scheduled` | Thông thường **không** | Task chạy trong scheduler thread |
| `@Async` hoặc `CompletableFuture.supplyAsync` | **Không được mặc định có** | Luồng thực thi có thể chuyển sang executor thread |
| Controller được gọi trực tiếp bằng `new` trong unit test | Không tự nhiên có request context | Không qua Spring MVC test infrastructure |
| Servlet/filter ngoài `DispatcherServlet` | Phụ thuộc cấu hình | Có thể cần `RequestContextFilter`/`RequestContextListener` |

“Thông thường” ở đây phản ánh cấu hình Spring MVC chuẩn; custom scope, custom thread binding và asynchronous dispatch có thể thay đổi chi tiết. Đừng suy ra scope active chỉ vì cùng JVM hoặc cùng ứng dụng.

### Khác biệt giữa “không active” và “chưa đăng ký”

Với `AnnotationConfigApplicationContext` không phải web context, nếu định nghĩa một bean ở scope `request` rồi cố lấy, container có thể báo scope **chưa được đăng ký**. Đó là vấn đề cấu hình container.

Trong một Servlet web application, `request` scope có thể đã được đăng ký đầy đủ nhưng vẫn **không active trên worker thread**. Đó là vấn đề ngữ cảnh lúc truy cập.

Hai tình huống cần cách sửa khác nhau: dùng context phù hợp để **đăng ký scope**, hoặc thực hiện lookup trong ngữ cảnh scope đang hoạt động.

## 4. Cơ chế: từ scoped proxy đến exception

Giả sử có request-scoped bean được inject vào singleton:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestToken {
    public String value() {
        return "Token thuộc request hiện tại";
    }
}
~~~

~~~java
import org.springframework.stereotype.Service;

@Service
public class TokenService {
    private final RequestToken token;

    public TokenService(RequestToken token) {
        this.token = token;
    }

    public String inspect() {
        return token.value();
    }
}
~~~

Đây là **hai file class minh họa** trong ứng dụng Spring MVC có component scanning. Annotation `@RequestScope` mặc định tạo scoped proxy kiểu `TARGET_CLASS` trong Spring Framework 6.x, nên singleton `TokenService` giữ proxy chứ không giữ cứng target của một request.

Trình tự khi gọi `TokenService.inspect()`:

~~~text
Singleton TokenService
       |
       | token.value()
       v
Request-scoped proxy
       |
       | tìm target bean theo scope "request"
       v
Spring RequestScope
       |
       +-- Có RequestAttributes bind với thread?
               |
               +-- Có --> target bean của request hiện tại
               |                |
               |                '--> value() thành công
               |
               '-- Không --> IllegalStateException
                                  |
                                  v
                         ScopeNotActiveException
~~~

Điểm quan trọng: **proxy hoãn lookup đến lúc gọi**, nhưng proxy **không tạo ra ngữ cảnh request**. Khi truy cập từ thread không có request, proxy cũng thất bại.

Nếu đổi `@RequestScope` thành `@Scope("request")` mà không bật proxy, singleton có thể cố resolve target ngay trong quá trình xây dựng; kết quả vẫn có thể là `ScopeNotActiveException` nhưng phát sinh **sớm hơn**, chẳng hạn lúc startup. Với `@RequestScope` có proxy, startup có thể thành công và lỗi chỉ xuất hiện khi method cần target được gọi ngoài request.

## 5. Ví dụ Spring Boot hoàn chỉnh: tái hiện lỗi và truy cập hợp lệ

Ví dụ dưới đây chạy trên **Java 17+**, **Spring Boot 3.3.5** (Spring Framework 6.1.x), sử dụng Servlet/Spring MVC. Một `ApplicationRunner` chủ động truy cập request-scoped bean ngoài HTTP request và bắt đúng ngoại lệ để minh họa. Cùng singleton service sẽ được gọi thành công khi một HTTP request thực sự đến controller.

### 5.1. Cấu trúc dự án

~~~text
scope-not-active-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── scope/
                        └── ScopeNotActiveDemo.java
~~~

### 5.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>scope-not-active-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. `ScopeNotActiveDemo.java`

~~~java
package com.example.scope;

import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.support.ScopeNotActiveException;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.annotation.RequestScope;

@SpringBootApplication
public class ScopeNotActiveDemo {

    public static void main(String[] args) {
        SpringApplication.run(ScopeNotActiveDemo.class, args);
    }

    @Component
    @RequestScope
    public static class RequestToken {
        private final String id = UUID.randomUUID().toString();

        public String id() {
            return id;
        }
    }

    @Service
    public static class TokenService {
        private final RequestToken token;

        public TokenService(RequestToken token) {
            this.token = token; // Proxy request scope được inject.
        }

        public String tokenId() {
            return token.id(); // Target được tìm khi thực sự gọi.
        }
    }

    @Component
    public static class StartupProbe implements ApplicationRunner {
        private final TokenService service;

        public StartupProbe(TokenService service) {
            this.service = service;
        }

        @Override
        public void run(ApplicationArguments args) {
            try {
                service.tokenId();
                System.out.println("outside-request: unexpected success");
            } catch (ScopeNotActiveException ex) {
                System.out.println(
                    "outside-request: ScopeNotActiveException");
            }
        }
    }

    @RestController
    public static class TokenController {
        private final TokenService service;

        public TokenController(TokenService service) {
            this.service = service;
        }

        @GetMapping("/token")
        public Map<String, Object> token() {
            String first = service.tokenId();
            String second = service.tokenId();

            return Map.of(
                "sameWithinRequest", first.equals(second),
                "tokenId", first
            );
        }
    }
}
~~~

Ba nested bean class đều `public static`, để Spring component scan có thể nhận diện chúng độc lập mà chỉ cần một source file. `TokenService` là singleton mặc định; `RequestToken` là request-scoped target. `StartupProbe` chạy sau khi ứng dụng được khởi động nhưng **không nằm trong một HTTP request**, nên truy cập `service.tokenId()` không có target request.

### 5.4. Chạy ứng dụng

Cài JDK 17+ và Maven 3.9+, tại thư mục chứa `pom.xml` chạy:

~~~bash
mvn spring-boot:run
~~~

Trong log khi `ApplicationRunner` chạy, dòng stdout do chương trình tự in:

~~~text
outside-request: ScopeNotActiveException
~~~

Log Spring Boot/Maven xuất hiện xung quanh dòng trên tùy cấu hình và môi trường. Nếu điều kiện môi trường bị tùy chỉnh để bind request attributes vào runner thì hành vi có thể khác, nhưng trong cấu hình Servlet Boot tiêu chuẩn runner không có HTTP request.

Dùng terminal khác gọi:

~~~bash
curl -s http://localhost:8080/token
~~~

Response JSON có dạng:

~~~json
{
  "sameWithinRequest": true,
  "tokenId": "UUID-duoc-sinh-cho-request"
}
~~~

**Đây là mẫu định dạng, không phải JSON literal có UUID cố định.** Giá trị `tokenId` là UUID thật, thứ tự field JSON có thể khác; `sameWithinRequest` là `true` bởi hai lần gọi trong cùng request dùng chung target.

Gọi endpoint lần nữa:

~~~bash
curl -s http://localhost:8080/token
~~~

Request sau nhận `tokenId` mới (trừ xác suất UUID tình cờ trùng rất nhỏ). Như vậy **cùng một singleton service hoạt động khác nhau tùy nơi gọi**, bởi request scope được resolve theo HTTP request trên thread hiện tại.

### 5.5. Tại sao bắt exception trong runner mà ứng dụng vẫn chạy?

Ví dụ chủ động catch `ScopeNotActiveException` trong `StartupProbe` để ứng dụng tiếp tục phục vụ `/token`. Trong chương trình thực tế, nếu không catch, ngoại lệ từ startup runner có thể làm Spring Boot khởi động thất bại. Việc catch ở đây là **phục vụ minh họa**; không khuyến nghị bắt và bỏ qua ngoại lệ trong luồng nghiệp vụ bình thường.

## 6. Các nguyên nhân phổ biến

### 6.1. Dùng request/session bean quá sớm khi singleton khởi tạo

~~~java
@Service
public class EarlyService {
    public EarlyService(RequestToken token) {
        // Trong một singleton được tạo khi startup:
        // Nếu là scoped proxy, lời gọi dưới đây cần target ngay.
        System.out.println(token.id());
    }
}
~~~

Đây là **mã minh họa**, phụ thuộc `RequestToken` từ mục 5. Khi singleton được tạo trước một HTTP request, constructor gọi `token.id()` và kích hoạt scoped proxy lookup trong lúc scope chưa active. `@PostConstruct`, `InitializingBean.afterPropertiesSet()` và một số bean initialization callback cũng có thể gây tương tự.

Cách sửa: giữ reference proxy trong field nhưng **chỉ gọi method cần request state khi thực sự đang xử lý request**. Nếu tác vụ khởi động không cần thông tin request, tách nó khỏi dependency request-specific.

### 6.2. Thiếu scoped proxy khi inject dependency scope ngắn vào singleton

~~~java
@Component
@Scope("request")
class RawRequestState {
}
~~~

Với cách này, không có đảm bảo tạo proxy mặc định giống `@RequestScope`. Khi singleton inject bean trực tiếp, container có thể phải tạo target tại startup và gặp lỗi không active.

Khắc phục: dùng `@RequestScope`, hoặc khai báo rõ:

~~~java
@Component
@Scope(
    value = "request",
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
class RequestState {
}
~~~

Đây là hai **định nghĩa bean ví dụ riêng** (không dùng cả hai trong một class); cần import `Component`, `Scope` và `ScopedProxyMode`. Bật proxy giải quyết vấn đề **thời điểm injection**, không hợp lệ hóa việc gọi target ngoài request.

### 6.3. Gọi trong task nền, scheduler hoặc event khởi động

Các entry point thường gặp:

- `@Scheduled` trong singleton service.
- `ApplicationRunner`/`CommandLineRunner` hoặc listener của `ApplicationReadyEvent`.
- Job worker xử lý hàng đợi.
- Message listener ngoài Servlet request.
- Executor chạy việc trì hoãn sau khi HTTP response kết thúc.

Không nên inject bean `@RequestScope` vào các task đó rồi gọi như thể request context luôn có mặt. Hãy tách dependency request-only; truyền dữ liệu nghiệp vụ cần thiết vào job theo một kiểu DTO/record thông thường.

### 6.4. Thread chuyển qua `@Async` hoặc `CompletableFuture`

Request attributes trong Servlet MVC thường gắn với thread xử lý request. Một executor thread độc lập không tự nhận `RequestAttributes` từ request thread.

~~~java
// Mã minh họa đặt trong một phương thức xử lý HTTP request.
CompletableFuture<String> future = CompletableFuture.supplyAsync(
    () -> requestToken.id()
);
~~~

Dù closure giữ tham chiếu đến `requestToken`, tham chiếu đó thường là **scoped proxy**, và khi task chạy trong common pool, proxy phải tìm target theo **thread của task**, nơi có thể không có request. Kết quả có thể là `ScopeNotActiveException`.

Không bảo đảm việc “lúc tạo future vẫn đang trong request” làm future hợp lệ. `@Async` cũng cần xét executor/propagation cụ thể; không có đảm bảo mặc định kế thừa web request scope.

### 6.5. Servlet request không đi qua `DispatcherServlet`

Spring MVC `DispatcherServlet` thường tự bind request attributes cho luồng xử lý request. Nhưng ứng dụng Servlet có thể nhận request qua servlet/filter hoặc tích hợp khác **nằm ngoài đường đi của `DispatcherServlet`**. Nếu mã đó muốn truy cập Spring web-scoped bean, cần cơ chế expose request context phù hợp.

Spring cung cấp `RequestContextListener` và `RequestContextFilter` cho trường hợp này. Đăng ký phụ thuộc môi trường; không nên thêm cả hai theo thói quen khi ứng dụng Spring MVC thông thường đã hoạt động.

### 6.6. Test không tạo HTTP request context

Trong unit test thuần:

~~~java
TokenService service = /* singleton đã được khởi tạo trong test */;
service.tokenId(); // Có thể lỗi nếu không có request scope active.
~~~

Đây là mã minh họa, không tự chạy. Tạo `ApplicationContext` đơn thuần không tương đương một HTTP request. Để test hành vi thực trong Spring MVC, dùng `MockMvc` với web test context, hoặc thiết lập `MockHttpServletRequest`/`RequestContextHolder` có kiểm soát nếu chỉ test một service dùng request context. Cần cleanup sau test để tránh rò `ThreadLocal` sang test khác.

## 7. Sửa đúng theo nơi chạy code

### Trường hợp A: logic thuộc HTTP request

Với controller/service đồng bộ trong request Spring MVC, giữ `@RequestScope` (hoặc `@SessionScope`) và chỉ sử dụng target trong luồng xử lý request:

~~~java
@RestController
class RequestController {
    private final TokenService service;

    RequestController(TokenService service) {
        this.service = service;
    }

    @GetMapping("/inspect")
    String inspect() {
        return service.tokenId();
    }
}
~~~

Đoạn này chỉ minh họa cách thiết kế controller, không thêm vào ứng dụng ở mục 5 nếu không cần endpoint `/inspect`. Nó dựa trên `TokenService` đã đăng ký với Spring.

### Trường hợp B: logic chạy background — trích xuất dữ liệu trước khi chuyển thread

Thay vì cho async task truy cập scoped proxy, đọc dữ liệu cần thiết **bên trong HTTP request**, rồi truyền snapshot bất biến sang task.

~~~java
// Record Java 17: chỉ chứa dữ liệu cần thiết cho công việc nền.
public record JobContext(String requestId, String operation) {
}
~~~

~~~java
// Trong phương thức được gọi từ HTTP request hợp lệ:
String requestId = requestToken.id();
JobContext snapshot = new JobContext(requestId, "export");

// Worker dùng snapshot, không dùng RequestToken scoped proxy.
CompletableFuture<String> future = CompletableFuture.supplyAsync(
    () -> snapshot.operation() + ":" + snapshot.requestId()
);
~~~

Hai đoạn này là **mã minh họa**, cần import `CompletableFuture`, có biến `requestToken` được inject và có thread executor tùy ứng dụng. `JobContext` có thể là record độc lập, không cần là Spring bean.

Ưu điểm:

1. Worker chỉ nhận giá trị đã xác định, không phải tìm request attributes.
2. Không phụ thuộc thread nào đang chạy.
3. Có thể lưu hoặc truyền DTO sang queue theo nhu cầu.
4. Dễ xác định dữ liệu nào được phép đi qua biên request/background.

Chỉ snapshot các dữ liệu thực sự cần thiết và được phép giữ lại. Không đưa nguyên `HttpServletRequest`, `HttpSession` hoặc mutable request-scoped bean vào queue để sử dụng sau khi request kết thúc.

### Trường hợp C: chỉ muốn trì hoãn lấy bean — dùng `ObjectProvider`

~~~java
@Service
class RequestReadingService {
    private final ObjectProvider<RequestToken> provider;

    RequestReadingService(ObjectProvider<RequestToken> provider) {
        this.provider = provider;
    }

    String inspect() {
        return provider.getObject().id();
    }
}
~~~

Đây là class minh họa; cần `import org.springframework.beans.factory.ObjectProvider;` và các import Spring tương ứng. `ObjectProvider` hữu ích vì container chưa phải lấy target ngay khi singleton được tạo. Nhưng **`provider.getObject()` vẫn đòi hỏi request scope active** tại thời điểm gọi.

**Sai lầm quan trọng:** `ObjectProvider.getIfAvailable()` không phải thuốc chữa mọi lỗi scope. Nó xử lý tình huống không có bean phù hợp theo semantics API, chứ không bảo đảm “trả null” thay vì exception khi scope tồn tại nhưng không active. Nếu target request scope bị truy cập ngoài request, vẫn phải xử lý đúng ngữ cảnh.

### Trường hợp D: phải xử lý Servlet request ngoài Spring MVC

Trong Servlet application có các request hợp lệ xử lý ngoài `DispatcherServlet`, có thể cấu hình một trong hai lựa chọn:

**RequestContextListener** — ví dụ đăng ký qua Servlet `web.xml`:

~~~xml
<listener>
    <listener-class>
        org.springframework.web.context.request.RequestContextListener
    </listener-class>
</listener>
~~~

**RequestContextFilter** — ví dụ cấu hình qua Spring Boot Servlet registration:

~~~java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.filter.RequestContextFilter;

@Configuration(proxyBeanMethods = false)
public class RequestBindingConfig {
    @Bean
    FilterRegistrationBean<RequestContextFilter> requestContextFilter() {
        FilterRegistrationBean<RequestContextFilter> bean =
            new FilterRegistrationBean<>(new RequestContextFilter());
        bean.addUrlPatterns("/*");
        return bean;
    }
}
~~~

Đoạn `RequestBindingConfig` là cấu hình Spring Boot Servlet độc lập; chỉ thêm **khi thực sự cần** xử lý request ngoài đường đi mặc định. Đây không phải cách khiến job không có HTTP request tự nhiên có request context. Đăng ký filter/listener phải phù hợp với servlet mapping, dispatch types và môi trường thực tế.

**Trong Spring MVC chuẩn**, `DispatcherServlet` đã expose request attributes; trước khi đăng ký thêm filter/listener cần xác định có thực sự thiếu binding trong một request hợp lệ không.

## 8. Vì sao không nên “copy request context” tùy ý sang thread mới?

Một số cách sửa lan truyền trên mạng lấy:

~~~java
RequestAttributes attrs = RequestContextHolder.getRequestAttributes();
~~~

rồi gọi `RequestContextHolder.setRequestAttributes(attrs)` trong executor thread. Phương pháp này có rủi ro:

- Request objects/attributes do Servlet container quản lý có vòng đời hữu hạn; background task có thể chạy **sau khi request kết thúc**.
- Nhiều loại request attributes, session attributes và đối tượng liên quan **không được thiết kế để truy cập đồng thời** từ thread tùy ý.
- Việc không reset `RequestContextHolder` trong thread pool có thể khiến giá trị của một request rò sang request khác.
- `RequestContextHolder.setRequestAttributes(..., true)` sử dụng inheritable thread-local trong một số trường hợp, nhưng thread pool tái sử dụng thread và có thể kế thừa context không đúng. Không dùng như cách sửa mặc định.
- Một context được copy không kéo dài vòng đời request thật, không bảo đảm thread-safety và không tự tạo transactional/security context phù hợp.

Nếu framework cung cấp mô hình async request chính thức, dùng cơ chế được hỗ trợ trong chính lifecycle đó; với việc chạy nền độc lập và kéo dài, **truyền dữ liệu cần thiết** rõ ràng thường dễ kiểm soát hơn.

## 9. Session scope cũng có thể lỗi khi không có HTTP request

`@SessionScope` quản lý bean theo một `HttpSession`. Việc có session trong trình duyệt **không có nghĩa** thread chạy nền đang có ngữ cảnh truy cập session của request hiện tại.

~~~java
@Component
@SessionScope
public class SessionPreferences {
    private String language = "vi";

    public String getLanguage() {
        return language;
    }
}
~~~

Đây là class minh họa, cần import `Component` và `SessionScope`. Nếu một background task gọi scoped proxy của `SessionPreferences` trong thread không có request attributes, nó cũng có thể gặp `ScopeNotActiveException`. `@SessionScope` không biến HTTP session thành kho dữ liệu toàn cục có thể truy cập tùy ý từ mọi thread.

Nếu task nền cần preference, hãy trích xuất `language` khi nhận request, xác thực nó và chuyển dạng giá trị sang job. Nếu dữ liệu cần truy cập lâu dài hoặc giữa các server, hãy dùng một nguồn lưu trữ phù hợp (DB/session store) với định danh và kiểm soát truy cập thích hợp.

`@ApplicationScope` có vòng đời ServletContext và thường ít phụ thuộc request thread hơn, nhưng vẫn cần web application context thích hợp. Không đổi một bean request/session state sang application scope chỉ để dập lỗi: điều đó có thể gây **chia sẻ dữ liệu giữa nhiều người dùng**.

## 10. Test lỗi và test cách sửa mà không phụ thuộc log tùy ý

Có hai tầng kiểm thử nên phân biệt:

1. **Test ngoài request:** xác nhận truy cập scoped target trong ngữ cảnh không có request thực sự thất bại như mong đợi.
2. **Test trong HTTP request:** xác nhận cùng scoped proxy truy cập được target khi đi qua web request infrastructure.

Ví dụ test integration với Maven dependency `spring-boot-starter-test`, class đặt trong `src/test/java/com/example/scope/ScopeNotActiveDemoTest.java`. Thêm dependency test vào `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Class test:

~~~java
package com.example.scope;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.ScopeNotActiveException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.request.RequestContextHolder;

@SpringBootTest
@AutoConfigureMockMvc
class ScopeNotActiveDemoTest {

    @Autowired
    private ScopeNotActiveDemo.TokenService service;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void outsideHttpRequest_failsToResolveRequestScopedTarget() {
        RequestContextHolder.resetRequestAttributes();

        assertThatThrownBy(service::tokenId)
            .isInstanceOf(ScopeNotActiveException.class);
    }

    @Test
    void insideHttpRequest_resolvesTargetAndReusesIt() throws Exception {
        mockMvc.perform(get("/token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sameWithinRequest").value(true))
            .andExpect(jsonPath("$.tokenId").isNotEmpty());

        assertThat(service).isNotNull();
    }
}
~~~

Test dùng `MockMvc` tạo môi trường web request giả lập để controller chạy và xác minh target. Test thứ nhất cố tình không có request context trước khi gọi `service.tokenId()`; test thứ hai đi qua `MockMvc`. Trong test suite thực tế, cần bảo đảm test isolation và cleanup request attributes nếu có code khác thiết lập thủ công.

Lệnh chạy:

~~~bash
mvn test
~~~

Đây là ví dụ integration test cho ứng dụng ở mục 5, sử dụng JUnit Jupiter/AssertJ/MockMvc do `spring-boot-starter-test` cung cấp. Kết quả đáng quan sát là **hai test pass**; không cam kết dòng stdout Maven cố định vì output test runner thay đổi theo plugin và môi trường.

## 11. Quy trình chẩn đoán `ScopeNotActiveException`

Khi gặp exception trong ứng dụng thật, trả lời theo thứ tự:

**Bước 1 — Xác định bean và scope.** Tìm tên bean trong exception, chú ý prefix `scopedTarget.` nếu có; tìm `@RequestScope`, `@SessionScope`, `@Scope(...)` hoặc bean definition programmatic tương ứng.

**Bước 2 — Đọc đến root cause.** `No thread-bound request found` thường chỉ ra thiếu request attributes. Nếu thấy `No Scope registered for scope name ...` thì ngữ cảnh bean factory chưa đăng ký scope, khác với request bị mất giữa threads.

**Bước 3 — Xác định nơi bắt đầu lời gọi.** Controller qua `DispatcherServlet`? Constructor singleton? `@PostConstruct`? `ApplicationRunner`? `@Async`? Scheduler? Message listener? Event handler? Một controller gọi service không bảo đảm các lời gọi service từ những entry point khác cũng có request.

**Bước 4 — Tìm điểm chuyển thread.** Dò `CompletableFuture`, `ExecutorService`, `@Async`, reactive publisher hoặc callback chạy muộn. Chú ý chỗ bean proxy được **gọi method**, không chỉ nơi proxy được inject.

**Bước 5 — Kiểm tra proxy hoặc provider.** Nếu exception xuất hiện lúc startup, xem dependency request-scoped có bị resolve trực tiếp trước request không. Nếu startup bình thường nhưng runtime lỗi, kiểm tra **lúc proxy/provider lookup target**.

**Bước 6 — Chọn cách sửa theo nghiệp vụ.** Request-only logic ở trong request; background logic nhận snapshot/ID/dữ liệu bất biến; request ngoài `DispatcherServlet` cấu hình binding đúng; context không phải web cần thay container hoặc thiết kế lại dependency.

**Bước 7 — Viết test tái hiện chính xác.** Một test ngoài request và một test HTTP request giúp tránh “sửa được startup nhưng vẫn hỏng ở background”.

### Bảng phân biệt lỗi

| Triệu chứng | Nguyên nhân có khả năng | Hành động |
| --- | --- | --- |
| `ScopeNotActiveException` khi `ApplicationRunner` gọi service | Không có HTTP request lúc startup | Tránh truy cập request target trong runner |
| `ScopeNotActiveException` trong `@Async` | Executor thread không có request attributes | Copy dữ liệu cần thiết trước khi submit task |
| `ScopeNotActiveException` trong constructor singleton | Resolve request target quá sớm, hoặc gọi scoped proxy quá sớm | Scoped proxy/provider và trì hoãn **lời gọi target** tới request |
| “No thread-bound request found” trong Servlet request đặc biệt | Không đi qua đường bind của `DispatcherServlet` | Xem `RequestContextFilter`/`RequestContextListener` |
| “No Scope registered for scope name 'request'” | Container thuần Java không đăng ký web scope | Dùng web-aware context phù hợp |
| Job truy cập `@SessionScope` nhưng thất bại | Có session ID không đồng nghĩa có request binding trên thread | Truyền preference/ID vào job |
| Sau khi bật proxy vẫn lỗi runtime | Proxy giải quyết injection nhưng target vẫn cần scope | Kiểm tra điểm gọi method và nơi thread chạy |
| Dữ liệu bị rò giữa người dùng sau khi đổi scope | Chọn singleton/application để dập lỗi request scope | Khôi phục ranh giới dữ liệu, đặt state đúng scope/storage |

## 12. Những điều không nên nhầm

### Scoped proxy không tạo ngữ cảnh mới

`@RequestScope` mặc định dùng `ScopedProxyMode.TARGET_CLASS`. Proxy giúp một bean sống lâu (ví dụ singleton) giữ reference ổn định tới bean sống ngắn, nhưng không thể làm một background thread thành HTTP request thread.

### `ObjectProvider` trì hoãn lookup, không miễn trừ scope

`ObjectProvider<RequestToken>` có thể inject thành công vào singleton; `getObject()` ở ngoài request vẫn có khả năng throw `ScopeNotActiveException`. Chỉ trì hoãn lookup **không đủ** nếu thời điểm sau đó cũng không có scope.

### `@Lazy` không biến request scope thành singleton

`@Lazy` có thể trì hoãn khởi tạo hoặc tạo proxy lazy trong một số injection point, nhưng không thay đổi yêu cầu phải có request context khi target thuộc `request`. Đừng dùng `@Lazy` như giải pháp phổ quát cho thiếu scope.

### Không phải mọi exception về bean đều do scope

`NoSuchBeanDefinitionException` báo thiếu bean definition phù hợp; `UnsatisfiedDependencyException` thường báo quá trình lắp ráp dependency thất bại; `BeanCurrentlyInCreationException` có thể liên quan vòng phụ thuộc. `ScopeNotActiveException` được nhận diện bằng **scope không active** và root cause tương ứng. Nó là một subtype của `BeanCreationException`, nên cần đọc toàn bộ cause chain.

### Không áp dụng giả định Servlet `ThreadLocal` trực tiếp cho WebFlux

Spring WebFlux sử dụng pipeline reactive, có thể chuyển thread và quản lý context bằng Reactor Context. Các mô hình gắn servlet request vào thread qua `RequestContextHolder` không phải thiết kế chung để mang mọi metadata qua reactive chain. Khi sử dụng WebFlux, hãy tuân thủ cơ chế `ServerWebExchange`/reactive context và các scope/capability mà ứng dụng hỗ trợ, thay vì chép nguyên cách sửa của MVC.

## 13. Câu hỏi kiểm tra

**Câu 1:** Vì sao `@RequestScope` bean inject vào singleton thành công nhưng `ApplicationRunner` gọi method lại ném `ScopeNotActiveException`?

**Đáp án:** Annotation chuyên biệt thường tạo proxy, nên lúc inject không cần target thật. Khi runner gọi method, proxy phải resolve target; runner không có HTTP request hiện hành, nên request scope không active.

**Câu 2:** Chuyển từ inject `RequestToken` sang inject `ObjectProvider<RequestToken>` có bảo đảm `getObject()` chạy được trong `@Scheduled` không?

**Đáp án:** Không. Provider trì hoãn lookup, nhưng scheduler thread vẫn thường không có request context. Cần thay đổi thiết kế dữ liệu/job hoặc điểm lookup.

**Câu 3:** Có thể tạo `@RequestScope` bean trong `AnnotationConfigApplicationContext` Java thuần và sử dụng như bean web bình thường không?

**Đáp án:** Không tự nhiên. Plain application context không tự đăng ký các web scope mặc định. Lỗi chưa đăng ký scope khác với trường hợp một web-aware context đã đăng ký request scope nhưng thread hiện hành thiếu request attributes.

**Câu 4:** Trong service được controller gọi, muốn chạy xuất báo cáo sau khi trả HTTP response, nên giữ nguyên `HttpServletRequest` hay truyền một DTO chứa thông tin cần thiết?

**Đáp án:** Truyền DTO/snapshot dữ liệu cần thiết trong lúc request còn hiệu lực. Worker background không nên phụ thuộc vào vòng đời của servlet request hoặc scoped proxy.

**Câu 5:** Vì sao việc đổi `RequestToken` từ `@RequestScope` sang `@ApplicationScope` để hết lỗi có thể nguy hiểm?

**Đáp án:** Nó thay đổi ranh giới dữ liệu từ từng HTTP request sang dùng chung trong web application. Thông tin request/user riêng có thể bị chia sẻ giữa các request/người dùng, trái với yêu cầu nghiệp vụ.

## 14. Tài liệu chính thức để đối chiếu

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): web-aware application context, cách kích hoạt request binding, scoped proxy và `ObjectProvider`.
- [`ScopeNotActiveException` Javadoc (Spring Framework 6.1)](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/beans/factory/support/ScopeNotActiveException.html): quan hệ với `BeanCreationException` và ý nghĩa exception.
- [`RequestScope` Javadoc (Spring Framework 6.1)](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/context/request/RequestScope.html): cần thread-bound `RequestAttributes` và cơ chế cung cấp.
- [`RequestContextHolder` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html): cách Spring lưu request attributes hiện tại; phân biệt `getRequestAttributes()` và `currentRequestAttributes()`.
- [`@RequestScope` Annotation Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/context/annotation/RequestScope.html): `proxyMode` mặc định.

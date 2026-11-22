# Đăng ký interceptor, view controller và resource handler trong Spring Boot MVC

## 1. Ba điểm mở rộng giải quyết ba công việc khác nhau

Trong ứng dụng Spring Boot dùng **Spring MVC (Servlet stack)**, việc mở rộng xử lý HTTP không nhất thiết đòi hỏi viết thêm controller cho mọi đường dẫn. Spring MVC cung cấp giao diện WebMvcConfigurer để đăng ký interceptor, ánh xạ URL trực tiếp tới view và cấu hình cách phục vụ tài nguyên tĩnh.

| Điểm mở rộng | Phương thức trên WebMvcConfigurer | Vai trò | Ví dụ |
|---|---|---|---|
| Handler interceptor | addInterceptors(InterceptorRegistry) | Thực thi logic trước/sau handler MVC, với phạm vi URL được chọn | Gắn thông tin quan sát, đo thời gian xử lý MVC |
| View controller | addViewControllers(ViewControllerRegistry) | Gắn URL với một tên view hoặc redirect đơn giản, không cần controller có nghiệp vụ | /welcome → template welcome; /old → redirect /welcome |
| Resource handler | addResourceHandlers(ResourceHandlerRegistry) | Ánh xạ URL vào tài nguyên tĩnh từ classpath hoặc thư mục được cho phép | /demo-assets/site.css → classpath:/demo-assets/site.css |

Cả ba cơ chế này thuộc **Spring MVC**. Không dùng nguyên các lớp WebMvcConfigurer, HandlerInterceptor hoặc Servlet API trong một ứng dụng chỉ chạy WebFlux. WebFlux có cơ chế cấu hình và filter riêng.

Luồng xử lý khái quát trong MVC:

~~~text
Client gửi HTTP request
         |
         v
Servlet Filter chain (gồm Spring Security nếu bật)
         |
         v
DispatcherServlet
         |
         v
HandlerMapping chọn handler và interceptor tương ứng
         |
         +--> preHandle(...) của các interceptor
         |
         +--> HandlerAdapter gọi handler:
         |      - @Controller / @RestController
         |      - ViewController
         |      - ResourceHttpRequestHandler
         |
         +--> postHandle(...) khi phù hợp
         |
         +--> ViewResolver / render view nếu có
         |
         +--> afterCompletion(...) khi request hoàn tất
         |
         v
HTTP response đến client
~~~

Sơ đồ mô tả request MVC thông thường, đồng bộ. Với xử lý bất đồng bộ, thứ tự callback có thêm những nhánh riêng, được giải thích bên dưới.

## 2. Cấu hình MVC trong Spring Boot: dùng WebMvcConfigurer

Trong Spring Boot 3.5.x, cơ chế mở rộng phổ biến là tạo một lớp @Configuration implements WebMvcConfigurer rồi override các phương thức cần thiết:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcConfiguration implements WebMvcConfigurer {
    // Override các phương thức cần tùy chỉnh.
}
~~~

Spring Boot sẽ tự tích hợp các WebMvcConfigurer beans vào cấu hình MVC đã được auto-configure. Có thể có nhiều WebMvcConfigurer trong các module khác nhau; Spring tổng hợp các cấu hình để áp dụng trong quá trình tạo MVC infrastructure.

**Không thêm @EnableWebMvc chỉ để đăng ký interceptor, view controller hoặc resource handler.** Trong Spring Boot, annotation đó chuyển sang cơ chế tự kiểm soát cấu hình Spring MVC, làm mất một số MVC auto-configuration mặc định của Boot, như một số thiết lập static resource, view resolver và web conventions. Chỉ sử dụng @EnableWebMvc khi chủ động muốn tự cấu hình MVC một cách toàn diện.

Cách tiếp cận đề xuất:

- Dùng WebMvcConfigurer khi muốn **bổ sung** tính năng mà vẫn giữ Spring Boot MVC auto-configuration.
- Dùng @Controller/@RestController khi URL cần xử lý nghiệp vụ, dữ liệu động hoặc trả JSON.
- Dùng application.yaml và các property có sẵn cho những tùy chỉnh đơn giản, chẳng hạn thay static path pattern mặc định.
- Chỉ thay cấu hình framework sâu hơn khi thực sự cần và hiểu tác động lên HandlerMapping, ViewResolver, message converter cùng các cơ chế khác.

Trong phần ví dụ, các package và API dùng cho **Spring Boot 3.5.x, Spring Framework 6.2, Java 17+**. Chúng cần dependency Spring Boot phù hợp; không phải chương trình có thể biên dịch bằng javac trần mà không có classpath Spring.

## 3. HandlerInterceptor: tác dụng và vòng đời

HandlerInterceptor cho phép ứng dụng thực thi logic quanh một handler do HandlerMapping quản lý. Nó không thay thế controller; nó hỗ trợ các công việc liên quan đến request.

Ba callback chính:

| Callback | Khi nào chạy | Giá trị sử dụng |
|---|---|---|
| preHandle(request, response, handler) | Sau khi chọn handler, trước khi gọi handler | Chuẩn bị request context, thêm thông tin quan sát, kiểm tra điều kiện phụ trợ |
| postHandle(request, response, handler, modelAndView) | Sau khi handler chạy bình thường và trước khi render view trong luồng đồng bộ | Thêm dữ liệu vào ModelAndView nếu có; thường không có view cho @ResponseBody |
| afterCompletion(request, response, handler, exception) | Khi chuỗi xử lý MVC đồng bộ hoàn tất, sau bước render nếu có | Dọn tài nguyên gắn với request, log/metric completion |

preHandle trả **true** để tiếp tục chuỗi xử lý. Nếu trả **false**, DispatcherServlet ngừng xử lý handler ở bước này; interceptor phải tự đảm bảo response phù hợp đã được thiết lập nếu cần. Đừng mặc định trả false sẽ tự động biến thành HTTP 403 hay JSON lỗi có cấu trúc.

Nếu nhiều interceptor được đăng ký, các preHandle thường được gọi theo thứ tự, còn các callback completion thường chạy theo chiều ngược lại cho những interceptor đã xử lý thành công preHandle. Một interceptor trả false có thể ngăn những interceptor còn lại và handler được chạy.

postHandle không phải nơi chắc chắn thay đổi được status hoặc body sau khi response đã ghi/commit. Trong controller trả JSON bằng @ResponseBody, ModelAndView thường null; logic tác động model chỉ phù hợp khi có view.

### Interceptor và Servlet Filter khác nhau thế nào?

- **Servlet Filter** nằm trước DispatcherServlet trong servlet filter chain, có thể xử lý cả request không đi qua HandlerMapping MVC và phù hợp để tích hợp security/cross-cutting ở tầng servlet.
- **HandlerInterceptor** chỉ được áp dụng cho các handler mappings mà Spring MVC cấu hình quản lý, có thể truy cập đối tượng handler đã được chọn và dùng pattern MVC để giới hạn URL.
- **Controller** thực thi nghiệp vụ của endpoint cụ thể.

Không dùng interceptor làm lớp bảo vệ duy nhất cho authentication hoặc authorization. Spring Framework khuyến nghị Spring Security hoặc cơ chế dựa trên Servlet filter chain để tránh việc pattern của interceptor không bao phủ hoàn toàn những endpoint cần bảo vệ.

## 4. Đăng ký interceptor với InterceptorRegistry

Mẫu đăng ký:

~~~java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(demoInterceptor)
            .addPathPatterns("/api/**")
            .excludePathPatterns("/api/public/**")
            .order(0);
}
~~~

Trong đó:

- addInterceptor nhận một HandlerInterceptor instance, thường được Spring quản lý như một bean để có thể dependency injection.
- addPathPatterns("/api/**") chỉ áp dụng cho các đường dẫn API thuộc vùng /api.
- excludePathPatterns("/api/public/**") loại các URL công khai khỏi interceptor này.
- order(0) đặt độ ưu tiên của interceptor registration; thông thường số order nhỏ hơn được thực hiện trước ở bước preHandle.

Pattern áp dụng trên phần đường dẫn request mà MVC dùng để so khớp, không phải cả URL có scheme, hostname hay query string. Khi có servlet context path hoặc custom servlet mapping, cần kiểm thử đường dẫn thực tế; đừng tự thêm context path vào mọi pattern.

Ví dụ nếu dùng pattern /api/**:

| Request | Có interceptor trong ví dụ? |
|---|---|
| GET /api/hello | Có |
| GET /api/orders/42 | Có |
| GET /api/public/ping | Không, do exclude |
| GET /welcome | Không |
| GET /demo-assets/site.css | Không |

Khi áp dụng một interceptor cho toàn ứng dụng với /**, nó có thể ảnh hưởng cả view controller và static resource handler, vì chúng cũng là MVC handlers. Do đó hãy dùng addPathPatterns/excludePathPatterns có chủ đích; không đăng ký /** rồi mới xử lý từng trường hợp bằng các lệnh if trong preHandle khi có thể cấu hình pattern rõ ràng.

Các version Spring MVC hiện đại có PathPatternParser và chiến lược so khớp đường dẫn riêng. Không giả định mọi Ant-style pattern đời cũ hoạt động hoàn toàn giống nhau sau khi đổi path matching strategy. Kiểm thử các route thực tế, nhất là nhiều dấu /, path variable, phần mở rộng và URL đã encode.

## 5. ViewControllerRegistry: phục vụ view không có nghiệp vụ

View controller hữu ích khi một URL chỉ cần render một template cố định hoặc chuyển hướng tới một URL khác. Nó tránh viết controller chỉ để trả một chuỗi tên view.

Ví dụ:

~~~java
@Override
public void addViewControllers(ViewControllerRegistry registry) {
    registry.addViewController("/welcome").setViewName("welcome");
    registry.addRedirectViewController("/old-welcome", "/welcome");
}
~~~

- /welcome được ánh xạ tới view name welcome.
- ViewResolver phải có khả năng tìm và render view đó, chẳng hạn Thymeleaf tìm src/main/resources/templates/welcome.html.
- /old-welcome tạo redirect đến /welcome. Client sẽ nhận response chuyển hướng HTTP (thường thuộc nhóm 3xx) rồi có thể gửi request mới tới Location.

**View name là tên view, không phải đường dẫn tệp tuyệt đối và cũng không phải response body của REST API.** Nếu dùng Thymeleaf, cần có dependency và template phù hợp. Nếu template không tồn tại hoặc ViewResolver không giải quyết được, mapping có thể tồn tại nhưng request vẫn lỗi khi render.

Một số lưu ý:

- View controller không phù hợp khi cần lấy dữ liệu từ database, gắn model theo user, tính toán nghiệp vụ hoặc xử lý các tham số request phức tạp; dùng @Controller cho những việc đó.
- Không chia cùng một URL giữa @RequestMapping controller và view controller. Mapping của controller có thể có độ ưu tiên và sở hữu URL khiến request trả 405/415 hoặc kết quả không như mong đợi.
- Không dùng view controller làm cơ chế bảo mật trang. Quyền truy cập phải được kiểm soát bằng cấu hình security phù hợp.
- Nếu endpoint chỉ cần trả HTTP status mà không có view, hãy dùng controller phù hợp hoặc cơ chế status controller mà API phiên bản hiện tại hỗ trợ, thay vì tạo template không cần thiết.
- Nếu ứng dụng có context path, ưu tiên sinh link theo cơ chế URL của template engine thay vì hardcode host và cổng.

## 6. ResourceHandlerRegistry: ánh xạ URL sang file tĩnh

Resource handler phục vụ tài nguyên tĩnh như CSS, JavaScript, ảnh và tài liệu công khai. Spring MVC sử dụng ResourceHttpRequestHandler cùng các ResourceResolver/ResourceTransformer khi có cấu hình chuỗi tài nguyên.

Ví dụ:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/demo-assets/**")
            .addResourceLocations("classpath:/demo-assets/")
            .setCacheControl(
                    CacheControl.maxAge(Duration.ofMinutes(10)).cachePublic()
            );
}
~~~

Cách hiểu:

- addResourceHandler("/demo-assets/**") đăng ký URL pattern. Phần sau tiền tố sẽ được dùng để tìm tài nguyên tương ứng.
- addResourceLocations("classpath:/demo-assets/") chỉ định nơi chứa file đã đóng gói trong classpath.
- Ký tự / ở cuối thư mục resource location giúp xác định đúng thư mục gốc.
- Cache-Control hướng dẫn cache lưu response trong 10 phút. Chính sách cache thực tế còn có thể bị ảnh hưởng bởi proxy, cấu hình chung và headers khác.

Với file src/main/resources/demo-assets/site.css, URL tương ứng là /demo-assets/site.css.

Khi resource không có, handler thường trả 404 (ví dụ NoResourceFoundException trong những phiên bản Spring MVC hiện đại). Không cần viết @GetMapping cho từng file CSS hoặc JavaScript.

### Resource mặc định của Spring Boot

Nếu giữ MVC auto-configuration, Spring Boot 3.5 mặc định phục vụ static content từ các vị trí classpath phổ biến:

- classpath:/static/
- classpath:/public/
- classpath:/resources/
- classpath:/META-INF/resources/

Trong cấu hình thông thường, các tài nguyên mặc định được ánh xạ qua /**. Có thể điều chỉnh bằng:

~~~yaml
spring:
  mvc:
    static-path-pattern: "/static/**"
  web:
    resources:
      static-locations:
        - "classpath:/static/"
        - "classpath:/public/"
~~~

Cấu hình trên thay đổi pattern và danh sách vị trí cho **resource mapping mặc định do Spring Boot tạo**. Trong khi đó, addResourceHandlers tự đăng ký mapping theo URL/location do developer chọn. Một custom handler bổ sung không đồng nghĩa bắt buộc phải bỏ tất cả static locations của Boot.

**Tránh đăng ký handler /** tùy tiện** vì dễ gây xung đột với mapping static mặc định và khiến request API sai đường dẫn trông như lỗi không tìm thấy tài nguyên. Dùng prefix riêng như /demo-assets/**, /docs-assets/** hoặc /images/** dễ hiểu và dễ kiểm soát hơn.

### Tài nguyên ngoài JAR

Có thể dùng file system resource location trong môi trường thích hợp, ví dụ:

~~~java
registry.addResourceHandler("/manuals/**")
        .addResourceLocations("file:/srv/public-manuals/");
~~~

Đây là ví dụ minh họa phụ thuộc hệ điều hành và deployment. Phải xác định thư mục đã có, quyền đọc, mục tiêu công khai và cách giới hạn truy cập. Không trỏ resource handler vào thư mục chứa secret, configuration nội bộ, mã nguồn hay dữ liệu tải lên chưa được kiểm tra. Không lấy một đường dẫn do người dùng nhập rồi nối tùy ý vào location có quyền truy cập filesystem.

### Caching và fingerprint của tài nguyên

Đối với asset có nội dung thay đổi nhưng URL giữ nguyên, thời gian cache quá dài có thể khiến client dùng bản cũ sau deploy. Đối với asset đã version hóa theo content hash, có thể cache dài hơn.

Spring MVC hỗ trợ resource chain với VersionResourceResolver, ví dụ minh họa riêng:

~~~java
registry.addResourceHandler("/build-assets/**")
        .addResourceLocations("classpath:/build-assets/")
        .resourceChain(true)
        .addResolver(
                new VersionResourceResolver()
                        .addContentVersionStrategy("/**")
        );
~~~

Với chiến lược content version, mã hash được tạo từ nội dung resource. Muốn template tạo URL có version tương ứng, tích hợp ResourceUrlProvider hoặc ResourceUrlEncodingFilter theo framework/template engine. Không chỉ thêm VersionResourceResolver rồi giả định mọi link HTML sẽ tự đổi URL. Đây là ví dụ cấu hình lựa chọn khác, không cần chèn cùng một pattern vào hai registration trùng nhau.

## 7. Ví dụ hoàn chỉnh: Spring Boot 3.5.x và Java 17+

Để có thể chạy và quan sát cả ba cơ chế, tạo một dự án Spring Boot 3.5.x bằng Maven (hoặc dùng project có sẵn), với dependency:

- spring-boot-starter-web: Spring MVC và embedded servlet server.
- spring-boot-starter-thymeleaf: ViewResolver cho template HTML.
- spring-boot-starter-test: dùng cho các ví dụ kiểm thử ở phần sau.

Các class dưới đây đặt trong package example.mvc. Các file cần có:

~~~text
src/
  main/
    java/example/mvc/
      MvcDemoApplication.java
      DemoInterceptor.java
      MvcConfiguration.java
      DemoApiController.java
    resources/
      templates/welcome.html
      demo-assets/site.css
  test/
    java/example/mvc/
      MvcConfigurationTest.java
~~~

### 7.1. Application chính

Tệp src/main/java/example/mvc/MvcDemoApplication.java:

~~~java
package example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
~~~

Để Spring Boot component scan tìm các @Component, @Configuration và @RestController bên dưới, nên đặt chúng trong cùng package hoặc package con của lớp @SpringBootApplication.

### 7.2. Interceptor là Spring bean

Tệp src/main/java/example/mvc/DemoInterceptor.java:

~~~java
package example.mvc;

import java.util.concurrent.TimeUnit;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class DemoInterceptor implements HandlerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(DemoInterceptor.class);

    private static final String START_NANOS =
            DemoInterceptor.class.getName() + ".startNanos";

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        request.setAttribute(START_NANOS, System.nanoTime());
        response.setHeader("X-Demo-Interceptor", "applied");
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        Object value = request.getAttribute(START_NANOS);
        if (value instanceof Long start) {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start
            );
            log.debug("MVC handler completed in {} ms", elapsedMs);
        }
    }
}
~~~

Mục đích ví dụ:

- preHandle đặt thuộc tính request để lưu mốc thời gian và thêm một response header có giá trị xác định.
- afterCompletion đọc mốc thời gian và ghi debug log về thời gian đi qua MVC handler.
- Interceptor được quản lý bởi Spring qua @Component và được inject vào cấu hình, giúp sử dụng được các dependencies khác nếu cần.
- Response header X-Demo-Interceptor là dấu hiệu dễ quan sát để xác minh mapping, không phải cơ chế bảo mật.

Số mili giây trong log không cố định. Phép đo ở đây là một đoạn vòng đời MVC, không phải tổng latency từ trình duyệt qua network và reverse proxy. Nếu yêu cầu metric chuẩn hoặc async request, cần lựa chọn điểm đo thích hợp hơn.

### 7.3. Đăng ký cả ba extension point

Tệp src/main/java/example/mvc/MvcConfiguration.java:

~~~java
package example.mvc;

import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcConfiguration implements WebMvcConfigurer {

    private final DemoInterceptor demoInterceptor;

    public MvcConfiguration(DemoInterceptor demoInterceptor) {
        this.demoInterceptor = demoInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(demoInterceptor)
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/public/**")
                .order(0);
    }

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addViewController("/welcome")
                .setViewName("welcome");

        registry.addRedirectViewController(
                "/old-welcome", "/welcome"
        );
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/demo-assets/**")
                .addResourceLocations("classpath:/demo-assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(10))
                                .cachePublic()
                );
    }
}
~~~

Giải thích:

- Một WebMvcConfigurer có thể override đồng thời ba phương thức hoặc chia thành nhiều @Configuration classes khi ứng dụng lớn.
- Interceptor chỉ áp dụng cho /api/**, trừ /api/public/**.
- Hai URL /welcome và /old-welcome được map trực tiếp tới view hoặc redirect.
- Tài nguyên trong classpath:/demo-assets/ được public qua prefix /demo-assets/** và có cache 10 phút.

Lớp không có @EnableWebMvc, do đó vẫn giữ mô hình MVC auto-configuration thường dùng của Spring Boot.

### 7.4. API controller để thử interceptor

Tệp src/main/java/example/mvc/DemoApiController.java:

~~~java
package example.mvc;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoApiController {

    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Vì @RestController trả về nội dung trực tiếp, kết quả của hai endpoint là response body hello và pong. Chúng không tìm view template cùng tên.

### 7.5. HTML view cho view controller

Tệp src/main/resources/templates/welcome.html:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Welcome</title>
    <link rel="stylesheet" th:href="@{/demo-assets/site.css}">
</head>
<body>
    <h1>Trang chào mừng</h1>
    <p>Đây là view được gắn với /welcome.</p>
</body>
</html>
~~~

Thymeleaf giải quyết view name welcome thành template welcome.html khi starter phù hợp có trên classpath. Biểu thức th:href giúp URL asset tính theo context path của ứng dụng, thay vì bắt buộc hardcode gốc /.

### 7.6. Tệp CSS trong custom resource location

Tệp src/main/resources/demo-assets/site.css:

~~~css
body {
    font-family: sans-serif;
    margin: 2rem;
}

h1 {
    color: #245a92;
}
~~~

Resource handler ánh xạ /demo-assets/site.css vào tệp site.css nói trên. Không cần thêm @GetMapping để serve nó.

### 7.7. Chạy và quan sát kết quả

Trong project Maven có Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Mặc định, server sẽ dùng cổng 8080 nếu chưa bị override. Hãy điều chỉnh URL trong các lệnh dưới theo cấu hình server.port của chính dự án.

Kiểm tra endpoint có interceptor:

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Các phần quan trọng của response được kỳ vọng gồm:

~~~text
HTTP/1.1 200
X-Demo-Interceptor: applied

hello
~~~

Đây là phần minh họa có chọn lọc, không phải nguyên văn mọi HTTP header trên mọi embedded server. Những header khác, thứ tự header, charset hoặc giao thức có thể thay đổi.

Kiểm tra route bị exclude:

~~~bash
curl -i http://localhost:8080/api/public/ping
~~~

Body là pong; header X-Demo-Interceptor sẽ không được thêm bởi DemoInterceptor trong ví dụ, vì pattern /api/public/** đã bị loại trừ.

Kiểm tra view:

~~~bash
curl -i http://localhost:8080/welcome
~~~

Nếu Thymeleaf dependency và template được đóng gói đúng, response sẽ chứa HTML của trang chào mừng.

Kiểm tra redirect:

~~~bash
curl -i http://localhost:8080/old-welcome
~~~

Response sẽ là một HTTP redirect có Location hướng tới /welcome. Dùng curl -L để yêu cầu curl theo redirect.

Kiểm tra static asset:

~~~bash
curl -i http://localhost:8080/demo-assets/site.css
~~~

Nếu resource tồn tại, response chứa CSS. Cache-Control có thể chứa max-age=600 và public do cấu hình cache 10 phút. Thực tế trình duyệt/proxy có thể áp dụng thêm các chính sách cache khác.

## 8. Kiểm thử tự động bằng MockMvc

Có thể xác minh rõ cơ chế mapping bằng MockMvc. Ví dụ dưới đây dành cho project ở phần 7, có spring-boot-starter-test.

Tệp src/test/java/example/mvc/MvcConfigurationTest.java:

~~~java
package example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class MvcConfigurationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void interceptorRunsForApiRoute() throws Exception {
        mvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Demo-Interceptor", "applied"))
                .andExpect(content().string("hello"));
    }

    @Test
    void excludedPathDoesNotRunInterceptor() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist(
                        "X-Demo-Interceptor"))
                .andExpect(content().string("pong"));
    }

    @Test
    void viewControllerResolvesViewName() throws Exception {
        mvc.perform(get("/welcome"))
                .andExpect(status().isOk())
                .andExpect(view().name("welcome"));
    }

    @Test
    void redirectViewControllerRedirects() throws Exception {
        mvc.perform(get("/old-welcome"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/welcome"));
    }

    @Test
    void resourceHandlerServesCss() throws Exception {
        mvc.perform(get("/demo-assets/site.css"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith("text/css"));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Trên Windows, dùng mvnw.cmd test. Nếu project có Spring Security được bổ sung về sau, MockMvc test có thể cần cấu hình mock user hoặc security policy tương ứng; request bị Spring Security từ chối trước DispatcherServlet không chứng minh rằng registration của MVC bị sai.

MockMvc kiểm thử mapping và xử lý ở tầng Spring MVC; nó không thay thế kiểm thử end-to-end qua HTTP socket, reverse proxy, cache/CDN, file permission hoặc TLS khi triển khai production.

## 9. Interceptor trong request bất đồng bộ

Ví dụ ở phần 7 là request đồng bộ. Với controller trả Callable, DeferredResult, WebAsyncTask hoặc các kiểu bất đồng bộ khác trên Spring MVC, vòng đời interceptor có thêm điểm cần chú ý.

Khi handler bắt đầu xử lý bất đồng bộ:

- Request có thể giải phóng thread servlet ban đầu trước khi response hoàn tất.
- Callback postHandle và afterCompletion không nhất thiết chạy trong lần dispatch đầu.
- Nếu interceptor implements AsyncHandlerInterceptor, callback afterConcurrentHandlingStarted có thể được gọi khi MVC chuyển sang xử lý concurrent.
- Khi kết quả async được dispatch trở lại, interceptor có thể được gọi tiếp; logic không nên giả định preHandle chỉ chạy đúng một lần trong toàn bộ vòng đời của một request.

Vì thế, ví dụ đo thời gian bằng request attribute phải được xem là bài thực hành cho request thông thường. Với async, nên thiết kế phép đo dựa trên lifecycle phù hợp, tránh ghi metric hai lần hoặc bỏ sót request timeout/disconnect.

Khi cần bảo đảm cleanup cả lúc timeout và lỗi bất đồng bộ, hãy xem các callback và API như DeferredResultProcessingInterceptor hoặc CallableProcessingInterceptor nếu dùng MVC async; đừng chỉ dựa vào finally trong thread ban đầu.

## 10. View controller, redirect và giới hạn của ViewResolver

View controller không chạy logic nghiệp vụ nhưng vẫn tham gia DispatcherServlet và có thể đi qua interceptor phù hợp. Để trả HTML:

1. Request match /welcome.
2. MVC chọn view controller.
3. View controller cung cấp tên view welcome.
4. ViewResolver (ví dụ ThymeleafViewResolver) tìm template phù hợp.
5. View được render thành HTML response.

Nếu bỏ spring-boot-starter-thymeleaf mà không có ViewResolver thay thế, /welcome không tự động biến thành response body "welcome". Một tên view hợp lệ cần một view engine hoặc resolver thực sự.

Redirect khác với render HTML:

- Render view thường cho response chứa HTML của trang hiện tại.
- Redirect trả 3xx kèm Location, client quyết định có gửi request mới hay không.
- Fixed redirect như /old-welcome → /welcome phù hợp cho đường dẫn cũ.
- Nếu URL redirect được xây từ input của người dùng, cần validate đích để tránh open redirect.

Khi dùng servlet context path như /shop, cần kiểm thử URL redirect và asset trong context đó. Không tự đoán rằng mọi URL bắt đầu bằng / sẽ được xử lý tương đương URL công khai ở proxy ngoài ứng dụng.

Nếu cần trả JSON, status code đặc thù, model theo request hoặc dữ liệu phân trang, dùng @Controller/@RestController và ResponseEntity thay vì lạm dụng view controller.

## 11. Resource handler, static mapping mặc định và xử lý 404

Một vài tình huống dễ nhầm:

**(1) Đặt CSS ở src/main/resources/templates/**

Template là nơi dành cho view engine. Không tự động truy cập tệp bên trong templates/ như static file qua URL. Trong ví dụ, CSS nằm ở demo-assets/ và được phục vụ bởi custom resource handler.

**(2) Đăng ký custom resource handler nhưng dùng sai URL**

Nếu cấu hình addResourceHandler("/demo-assets/**") và file site.css, URL đúng là /demo-assets/site.css. Không phải /demo-assets/demo-assets/site.css.

**(3) Dùng classpath location thiếu dấu / cuối**

Hãy viết "classpath:/demo-assets/" để chỉ rõ thư mục gốc. Một location không đúng có thể khiến file tồn tại trong JAR nhưng URL trả 404.

**(4) Handler mặc định /** “bắt” request sai**

Spring Boot thường map static resources mặc định trên /**. Nếu một URL không có controller match, request có thể đi tới ResourceHttpRequestHandler và trả lỗi không tìm thấy tài nguyên, chẳng hạn NoResourceFoundException. Điều đó không nhất thiết cho thấy controller lẽ ra phải xử lý URL đó.

Khi cần điều tra sự khác biệt NoHandlerFoundException và NoResourceFoundException, kiểm tra spring.mvc.static-path-pattern và property spring.web.resources.add-mappings. Tắt default static mappings có thể làm thay đổi loại exception khi không tìm thấy handler. Không tùy tiện tắt toàn bộ mappings để sửa một lỗi 404 đơn lẻ.

**(5) Tự register /** đè lên tài nguyên thông thường**

Một handler /** quá rộng có thể cạnh tranh với mapping resource mặc định hoặc chiếm URL không dự tính. Chỉ đăng ký phạm vi cần thiết, kiểm tra HandlerMapping và các pattern đã tồn tại.

**(6) Client nhận CSS cũ sau deploy**

Cấu hình cache max-age quá lớn cho URL không version hóa có thể khiến client chưa tải bản mới. Dùng thời gian cache hợp lý, purge CDN hoặc fingerprint tài nguyên.

**(7) Tệp nằm ngoài classpath của JAR**

Nếu dùng resource ngoài JAR, cần cấu hình file: location hợp lệ và mount thư mục vào container khi triển khai. Một đường dẫn file trên máy phát triển không tự tồn tại bên trong image hoặc Pod.

## 12. Tương tác với Spring Security và Servlet Filters

Cấu hình interceptor dùng để quan sát hoặc bổ sung logic MVC; chính sách authentication/authorization nên do Spring Security đảm nhiệm.

Ví dụ app yêu cầu người dùng đăng nhập để xem /welcome. View controller chỉ chịu trách nhiệm chọn view; nó không mặc nhiên yêu cầu login. SecurityFilterChain phải quy định ai được phép gọi /welcome.

Tương tự, /demo-assets/** có thể là public hoặc private tùy chính sách. Spring MVC chỉ định vị và trả file; nếu URL chứa nội dung nhạy cảm thì không nên public trực tiếp bằng resource handler. Một file tồn tại trong thư mục resource không có nghĩa nó phù hợp để công khai.

Lưu ý:

- Request bị filter chặn trước DispatcherServlet sẽ không chạy MVC interceptor.
- URL exclude trong addInterceptors không có nghĩa URL đó cũng được Spring Security permitAll; hai lớp cấu hình là độc lập.
- CORS, CSRF, session management, quyền truy cập và bảo vệ API nên dùng API bảo mật phù hợp.
- Nếu thật sự cần logic chạy cho toàn bộ Servlet traffic, Servlet Filter có thể là extension point đúng hơn HandlerInterceptor.

## 13. Mở rộng registry trong ứng dụng nhiều module

Trong project lớn, có thể chia các cấu hình thành các lớp @Configuration riêng:

~~~java
@Configuration(proxyBeanMethods = false)
class ApiInterceptorConfiguration implements WebMvcConfigurer {
    // addInterceptors(...)
}

@Configuration(proxyBeanMethods = false)
class ViewRouteConfiguration implements WebMvcConfigurer {
    // addViewControllers(...)
}

@Configuration(proxyBeanMethods = false)
class StaticAssetConfiguration implements WebMvcConfigurer {
    // addResourceHandlers(...)
}
~~~

Các class trên chỉ minh họa cấu trúc; phương thức chưa được đưa vào. Chúng không phải chương trình chạy độc lập.

Việc tách lớp giúp quản lý phạm vi và dependency, nhưng cần tránh:

- Hai view controllers cùng chiếm một URL.
- Một URL trùng giữa @RequestMapping và view controller.
- Hai resource registrations cùng pattern nhưng location/cache khác nhau, khiến kết quả phụ thuộc thứ tự xử lý.
- Interceptors lặp lại cùng trách nhiệm hoặc đánh dấu metric nhiều lần.

Khi interceptor phụ thuộc vào service, nên inject bean đó qua constructor vào interceptor bean, rồi inject interceptor vào WebMvcConfigurer. Tạo interceptor bằng new ở nhiều nơi có thể làm phân tán state và bỏ qua dependency injection.

Nếu cần thay đổi thứ tự giữa nhiều interceptor, khai báo order có chủ đích và kiểm tra bằng test. Với preHandle theo chiều thuận, completion ngược chiều, các task như tạo/đóng request context cần quản lý chính xác.

## 14. Hướng dẫn chẩn đoán nhanh

| Hiện tượng | Kiểm tra |
|---|---|
| Interceptor không chạy | Có @Configuration được component scan không? Pattern có khớp URL MVC? Có exclude không? Security Filter có chặn trước không? |
| Interceptor chạy trên static asset không mong muốn | Pattern /** quá rộng; giới hạn /api/** hoặc exclude /demo-assets/** |
| preHandle trả false nhưng status không như dự kiến | Thiếu setStatus/sendError hoặc response body phù hợp trước khi ngừng chuỗi |
| postHandle không có ModelAndView | @RestController/@ResponseBody trả body trực tiếp; ModelAndView có thể null |
| afterCompletion thiếu log ở async request | Kiểm tra AsyncHandlerInterceptor, timeout và async dispatch |
| /welcome trả 500 hoặc không render | Thiếu Thymeleaf/ViewResolver, sai tên hoặc vị trí templates/welcome.html |
| /welcome báo mapping bất thường | Trùng URL giữa view controller và @RequestMapping |
| /old-welcome không redirect đúng | Kiểm tra target URL, context path, proxy và Location |
| /demo-assets/site.css trả 404 | Sai prefix, sai classpath:/demo-assets/, tệp chưa được đóng gói hoặc khác chữ hoa/thường |
| CSS tải được nhưng cũ | Cache-Control, CDN, browser cache, fingerprint/versioning |
| Thêm @EnableWebMvc làm static file hỏng | @EnableWebMvc đã thay đổi mô hình auto-configuration; bỏ khi chỉ muốn customizer |
| API chưa map bị báo NoResourceFoundException | Default static mapping /** có thể nhận request khi không có controller match |
| Chạy đúng local nhưng lỗi trong JAR | Tệp không nằm dưới src/main/resources hoặc cấu hình file path phụ thuộc máy |

Khi chẩn đoán, nên bật log liên quan đến Spring MVC handler mappings và quan sát danh sách request mappings nếu Actuator được bật/cho phép. Không cần sửa hoặc bật public Actuator endpoints chỉ để kiểm tra một route.

## 15. Checklist trước khi đưa vào production

1. **Đúng stack:** ứng dụng thực sự chạy Spring MVC, không phải WebFlux-only.
2. **Giữ auto-configuration:** dùng WebMvcConfigurer và không thêm @EnableWebMvc khi chỉ mở rộng MVC.
3. **Interceptor phạm vi rõ:** pattern include/exclude có test; không thay thế SecurityFilterChain.
4. **Callback đúng lifecycle:** hiểu preHandle, postHandle, afterCompletion và đặc điểm async.
5. **View controller đơn giản:** không chứa nghiệp vụ, có ViewResolver/template thực sự.
6. **Redirect có chủ đích:** target rõ, không mở redirect theo input người dùng.
7. **Resource handler hẹp:** URL prefix riêng và resource location an toàn, không expose secrets.
8. **Cache hợp lý:** TTL phù hợp với tính bất biến của assets; fingerprint khi cache dài.
9. **Không mapping conflict:** kiểm tra @RequestMapping, view controllers, static resource mapping và context path.
10. **Kiểm thử hai tầng:** MockMvc cho registration; HTTP integration test để xác minh server/proxy/cache khi cần.

## 16. Tài liệu chính thức tham khảo

- [Spring Boot 3.5 – Servlet Web Applications, MVC auto-configuration và static content](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Framework 6.2 – Interceptors](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html)
- [Spring Framework – View Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/view-controller.html)
- [Spring Framework 6.2 – Static Resources](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/static-resources.html)
- [Spring Framework – HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html)

Các code snippet hoàn chỉnh ở phần 7 và phần 8 giả định project Spring Boot 3.5.x với Java 17+, đúng dependencies và package structure đã nêu. Nếu chuyển sang Spring Boot 4.x hoặc Spring Framework 7.x, phải kiểm tra package/API, migration guide và test thực tế trước khi copy cấu hình.

Nắm được ba extension point này giúp giữ controller tập trung vào nghiệp vụ, thêm logic chung đúng phạm vi và phục vụ HTML/static assets bằng hạ tầng MVC sẵn có, đồng thời bảo toàn những mặc định hữu ích của Spring Boot.
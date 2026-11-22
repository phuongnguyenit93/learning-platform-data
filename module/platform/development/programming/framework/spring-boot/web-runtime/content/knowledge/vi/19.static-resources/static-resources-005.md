# Tùy chỉnh resource handler và tránh xung đột với API

Một ứng dụng Spring Boot có thể vừa cung cấp **REST API** (ví dụ /api/orders), vừa trả **tài nguyên tĩnh** (CSS, JavaScript, ảnh, font, PDF, favicon). Với Spring MVC, hai nhóm này thường đi qua cùng **DispatcherServlet**, nhưng được xử lý bởi những handler khác nhau. Cấu hình đúng giúp trình duyệt tải asset ổn định, API vẫn giữ status/body theo hợp đồng, và đường dẫn không bị các quy tắc bắt mọi URL hoặc SPA fallback che khuất.

Bài này dùng **Spring Boot 3.x, Java 17+, Spring MVC (Servlet)**. Các ví dụ tập trung vào một cách tổ chức dễ kiểm chứng: **/api/** dành cho endpoint nghiệp vụ, **/assets/** dành cho file công khai. Spring WebFlux có cơ chế resource handler tương đương nhưng dùng **WebFluxConfigurer** và property riêng; không áp dụng nguyên xi mã WebMvcConfigurer cho WebFlux.

## 1. Mục tiêu

Sau khi học, bạn có thể:

1. Giải thích cách Spring MVC chọn **RequestMappingHandlerMapping** cho controller và **ResourceHttpRequestHandler** cho file tĩnh.
2. Phân biệt **URL pattern** (ví dụ /assets/**) với **resource location** (ví dụ classpath:/site-assets/).
3. Tùy chỉnh cách phục vụ asset bằng **spring.mvc.static-path-pattern**, **spring.web.resources.static-locations**, hoặc **WebMvcConfigurer.addResourceHandlers(...)** đúng nhu cầu.
4. Giữ ranh giới của **/api/**, **/assets/**, **/actuator/** và các route khác; hiểu ảnh hưởng của catch-all, SPA fallback và xử lý exception.
5. Thiết kế cache, version URL, quyền truy cập và CORS phù hợp; không để file nội bộ trở thành file tải công khai.
6. Viết integration test chứng minh API không bị static handler chiếm và file đúng/mất trả status hợp lý.

Điều kiện đầu vào: biết Java annotation, Spring Boot auto-configuration, @RestController/@GetMapping, HTTP status, JSON, cấu trúc src/main/resources và cách chạy Gradle/Maven.

## 2. Resource handler nằm ở đâu trong luồng HTTP?

### 2.1. Hai nhóm handler khác trách nhiệm

~~~text
HTTP request
      |
      v
Servlet filter chain (ví dụ Spring Security nếu được bật)
      |
      v
DispatcherServlet
      |
      +--> RequestMappingHandlerMapping
      |       +--> @RestController / @Controller (@GetMapping,...)
      |       +--> handler method -> service -> JSON / status
      |
      +--> ResourceHandlerMapping
              +--> ResourceHttpRequestHandler
              +--> tìm file tại resource locations
              +--> phản hồi CSS / JS / PNG / font / PDF
~~~

Sơ đồ là mô hình khái niệm. DispatcherServlet xét các **HandlerMapping theo thứ tự ưu tiên** và dùng handler đầu tiên phù hợp. Trong cấu hình Spring MVC điển hình, mapping của controller được xét trước static resource mapping. Vì thế, một @GetMapping("/api/status") được đăng ký đúng vẫn có thể xử lý request của nó khi static mapping mặc định là /**.

**Tuy vậy, không nên dựa vào thứ tự ưu tiên để thiết kế URL.** Mapping /** có thể trở thành fallback cho API không tồn tại, khiến lỗi 404 đi theo đường tài nguyên tĩnh, chứ không đi qua một controller API. Một controller bắt mọi URL, SPA fallback hoặc custom HandlerMapping được đặt ưu tiên sai có thể tạo va chạm thật sự. Tách namespace và kiểm thử vẫn là cách an toàn.

### 2.2. URL pattern không phải đường dẫn file

Với cấu hình:

~~~java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/site-assets/");
~~~

request **GET /assets/css/site.css** yêu cầu nội dung **classpath:/site-assets/css/site.css**. Phần /assets/ là **prefix URL công khai**, còn site-assets/ là **nơi tìm tài nguyên bên trong ứng dụng**. Người dùng không được suy ra từ URL rằng file nằm ở /assets trên ổ đĩa.

**@GetMapping("/api/status")** ánh xạ request vào phương thức Java; **addResourceHandler("/assets/**")** ánh xạ request vào cơ chế đọc resource. Đừng đặt API dưới /assets/** hoặc đặt file tĩnh dưới /api/**, kể cả khi hiện tại handler ưu tiên vẫn giải quyết được.

### 2.3. Spring Boot mặc định làm gì?

Với Spring MVC auto-configuration và starter web thông dụng, Spring Boot tìm static resource từ các location trong classpath:

- **classpath:/static/**
- **classpath:/public/**
- **classpath:/resources/**
- **classpath:/META-INF/resources/**

Theo mặc định, static content dùng pattern **/***. Ví dụ **src/main/resources/static/css/site.css** có thể được gọi bằng **GET /css/site.css**. Bộ xử lý là **ResourceHttpRequestHandler**; nó tìm tài nguyên, xác định content type và hỗ trợ một số cơ chế cache/conditional request. Với executable JAR, nên đặt asset vào **src/main/resources** để được đóng gói vào classpath; **src/main/webapp** không phải lựa chọn tin cậy cho mọi executable JAR.

**Chú ý 404:** Khi static handler mặc định là /**, request **GET /api/khong-ton-tai** có thể vẫn được một resource handler nhận như một đường dẫn resource. Với Spring Framework 6.1 (Spring Boot 3.3), nếu không tìm thấy file, **NoResourceFoundException** thường được xử lý thành HTTP **404**. Khi chuyển static mapping thành /assets/** và không có API mapping, đường đi có thể là **NoHandlerFoundException**. Status cùng là 404, nhưng exception khác nhau; một @ControllerAdvice bắt tất cả exception thiếu phân loại có thể biến chúng thành body/status sai.

## 3. Thiết kế namespace để tránh xung đột

Một hợp đồng URL dễ bảo trì:

| Prefix URL | Chủ sở hữu | Ví dụ | Quy tắc |
| --- | --- | --- | --- |
| **/api/** | REST controller | /api/status, /api/orders/42 | JSON/status theo hợp đồng API; không dùng cho asset. |
| **/assets/** | ResourceHttpRequestHandler | /assets/css/site.css, /assets/logo.svg | Chỉ file công khai; GET/HEAD, 404 khi không có file. |
| **/actuator/** | Spring Boot Actuator nếu thêm dependency | /actuator/health | Endpoint vận hành có exposure/security riêng. |
| **/webjars/** | Cơ chế WebJars nếu dùng | /webjars/... | Giữ mapping có chủ đích khi cần thư viện frontend từ JAR. |
| **/** hoặc UI route | Giao diện và SPA navigation | /, /products/42 | Chỉ fallback HTML cho navigation thật; không bao phủ API/asset. |

Các prefix này là **quy ước thiết kế của bài học**, không phải keyword bắt buộc của Spring. Trong thực tế có thể dùng /static/**, /public-assets/** hoặc domain/CDN riêng, miễn các rule rõ ràng và test được.

**Điểm thiết kế quan trọng:**

- Dùng một prefix tĩnh cụ thể như **/assets/** thay vì đăng ký resource handler tùy chỉnh trên **/*** hoặc **/api/***.
- Không tạo một API controller dùng mapping quá rộng cho mọi đường dẫn rồi trông đợi file tĩnh luôn thắng. HandlerMapping có **order**, không chỉ so sánh độ cụ thể của pattern giữa mọi loại handler.
- Nếu frontend chạy như SPA, chỉ trả **index.html** cho **navigation GET chấp nhận text/html**; không biến API sai tên, file CSS thiếu hoặc yêu cầu POST thành HTML 200.
- Không để upload private hoặc file cấu hình (application.yml, .env, credential, log, source code) vào resource location công khai.
- Khi thay servlet context path hoặc chạy sau reverse proxy, nhớ prefix của ứng dụng ở bên ngoài có thể làm URL đầy đủ khác các path mapping bên trong DispatcherServlet.

## 4. Cách 1: Chỉ dùng cấu hình Spring Boot khi không cần logic resource đặc biệt

Nếu tất cả asset đều là file đóng gói và chỉ muốn chuyển static URL từ /** sang /assets/**, ưu tiên cấu hình có sẵn.

**src/main/resources/application.yml**

~~~yaml
spring:
  mvc:
    static-path-pattern: "/assets/**"
  web:
    resources:
      static-locations:
        - "classpath:/static/"
~~~

Đặt **src/main/resources/static/css/site.css**. File được cung cấp qua:

~~~text
GET /assets/css/site.css
~~~

Trong cấu hình trên, **spring.mvc.static-path-pattern** là pattern URL cho static content auto-config của MVC. **spring.web.resources.static-locations** là nơi Spring Boot tìm tài nguyên, và việc khai báo nó **thay thế danh sách static locations mặc định**. Nếu vẫn cần /public hoặc /META-INF/resources, phải cân nhắc bổ sung có chủ đích. Đừng thêm handler Java khác cùng pattern /assets/** chỉ để lặp lại cấu hình.

Ưu điểm: ít mã, giữ cơ chế auto-configuration và các tính năng mặc định liên quan. Giới hạn: khi bạn cần nhiều prefix có cache khác nhau, resource nằm ở nhiều nguồn đặc biệt, resolver/transformer riêng hoặc versioning theo đường dẫn, cần custom **WebMvcConfigurer**.

**Lưu ý khi đổi static-path-pattern:** đường dẫn tới favicon, index, WebJars, welcome page hoặc template có thể cần điều chỉnh theo cách ứng dụng thực sự dùng chúng. Không coi phép đổi prefix là một thao tác chỉ ảnh hưởng CSS; test các URL chính thức của UI.

## 5. Cách 2: Custom resource handler với WebMvcConfigurer

Khi cần chủ động chỉ định URL và location, hãy tạo bean cấu hình MVC. Để ví dụ này có **duy nhất một static namespace /assets/** và không giữ fallback mặc định /**, ta tắt **các mapping tĩnh tự động của Spring Boot** bằng **spring.web.resources.add-mappings=false**, rồi đăng ký handler thủ công. Điều này cũng loại bỏ một số hành vi auto resource/welcome page mặc định: chỉ chọn cách này khi ứng dụng kiểm soát được các đường dẫn đang phục vụ.

**Quan trọng:** **spring.web.resources.add-mappings=false** tắt đăng ký **resource handler mặc định của Boot**, không cấm **WebMvcConfigurer.addResourceHandlers(...)** tự đăng ký handler do bạn viết. Cách đơn giản ở mục 4 thường đủ nếu không cần kiểm soát chi tiết.

### 5.1. Tạo project

Tạo project Spring Boot 3.x qua Spring Initializr với:

- Java 17+, group **com.example**, artifact **resource-routes**, package **com.example.resourceroutes**.
- Dependency **Spring Web** và **Spring Boot Starter Test**.
- Build tool Gradle và Gradle wrapper được tạo cùng project.

Cây file cần bổ sung:

~~~text
resource-routes/
  src/
    main/
      java/com/example/resourceroutes/
        ResourceRoutesApplication.java
        ApiController.java
        StaticAssetsConfig.java
      resources/
        application.yml
        site-assets/
          css/
            site.css
          js/
            app.js
    test/
      java/com/example/resourceroutes/
        RouteIsolationTest.java
~~~

Không cần cài Tomcat độc lập khi starter Web đã đưa embedded server phù hợp vào ứng dụng.

### 5.2. Main

**src/main/java/com/example/resourceroutes/ResourceRoutesApplication.java**

~~~java
package com.example.resourceroutes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceRoutesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceRoutesApplication.class, args);
    }
}
~~~

Lớp main nằm ở package cha để component scan tìm controller và config cùng package.

### 5.3. API riêng ở /api/**

**src/main/java/com/example/resourceroutes/ApiController.java**

~~~java
package com.example.resourceroutes;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    public record Status(String status) { }

    @GetMapping("/api/status")
    public Status status() {
        return new Status("ok");
    }
}
~~~

Controller trả một record Java, được Jackson của Spring Web serialize thành JSON:

~~~json
{"status":"ok"}
~~~

Không thêm @GetMapping("/assets/**") vào controller; nếu có nghiệp vụ tải file cần xác thực người dùng, dùng endpoint riêng với authorization và response headers thích hợp, không trộn nó với vùng public asset.

### 5.4. Resource handler tùy chỉnh

**src/main/java/com/example/resourceroutes/StaticAssetsConfig.java**

~~~java
package com.example.resourceroutes;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class StaticAssetsConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/site-assets/")
                .setCacheControl(CacheControl.maxAge(Duration.ofMinutes(10))
                        .cachePublic());
    }
}
~~~

**Giải thích:**

1. **WebMvcConfigurer** bổ sung một phần MVC config, giữ cấu hình Spring Boot còn lại. **Không thêm @EnableWebMvc** chỉ để khai báo handler; @EnableWebMvc làm bạn nhận trách nhiệm cấu hình MVC rộng hơn và khiến nhiều MVC auto-configuration của Boot không còn áp dụng.
2. **addResourceHandler("/assets/**")** khai báo URL public mà resource handler xử lý.
3. **addResourceLocations("classpath:/site-assets/")** đặt root của file được phép phục vụ. Dấu **/** cuối location giúp path tương đối được ghép đúng.
4. **setCacheControl(...)** trả header cache cho asset. 10 phút chỉ là giá trị mẫu cân bằng khi filename chưa mang hash; chọn chính sách production theo cách cập nhật file thật.
5. **Không đăng ký "/**"** vì sẽ phủ cả đường dẫn không thuộc asset. Không đăng ký "/api/**" vào resource handler.

Spring Framework có thể phục vụ resource với header **Last-Modified** và phản hồi conditional request phù hợp. Cache-Control chỉ áp dụng cho phản hồi của resource handler; nó không tự làm cache response JSON từ @RestController.

### 5.5. Tắt riêng static mappings mặc định của Boot

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: resource-routes
  web:
    resources:
      add-mappings: false

server:
  port: 8080
~~~

Ứng dụng này chỉ public asset theo mapping custom **/assets/**; **/api/status** vẫn thuộc @RestController. Setting này **không tắt Spring MVC, controller, JSON conversion hoặc DispatcherServlet**. Nó tắt mapping resource tự động, do đó nếu bạn từng dựa vào /webjars/** hay default welcome page thì cần thiết kế lại riêng.

Đừng đồng thời sao chép cấu hình của **mục 4** vào project này rồi mong hai cơ chế luôn ghép với nhau theo ý muốn. Mục 4 và 5 là **hai lựa chọn triển khai riêng** cho cùng mục tiêu; chọn một mô hình quản lý static URL rõ ràng.

### 5.6. Tạo asset mẫu

**src/main/resources/site-assets/css/site.css**

~~~css
body {
    background-color: #f5f7ff;
}
~~~

**src/main/resources/site-assets/js/app.js**

~~~javascript
console.log("assets ready");
~~~

Các file này được đóng gói trong classpath của executable JAR. Không đặt chúng dưới **src/main/java** hoặc nhầm location **classpath:/site-assets/** với đường dẫn thư mục ngoài ổ đĩa.

### 5.7. Chạy và kiểm chứng thủ công

Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell hoặc CMD:

~~~text
gradlew.bat bootRun
~~~

Terminal thứ hai:

~~~bash
curl -s http://localhost:8080/api/status
curl -s http://localhost:8080/assets/css/site.css
curl -s http://localhost:8080/assets/js/app.js
~~~

Các response body dự kiến lần lượt là:

~~~json
{"status":"ok"}
~~~

~~~css
body {
    background-color: #f5f7ff;
}
~~~

~~~javascript
console.log("assets ready");
~~~

Kiểm tra header và status:

~~~bash
curl -i http://localhost:8080/assets/css/site.css
curl -i http://localhost:8080/assets/khong-co.css
curl -i http://localhost:8080/api/khong-co
~~~

Kết quả cần quan sát: file tồn tại trả **200**, file không có và API không có đều trả **404** theo cấu hình trên. CSS thường có **Content-Type: text/css** và **Cache-Control** theo cấu hình. Không chốt nguyên văn body lỗi hoặc tất cả header vì chúng phụ thuộc Spring Boot minor version, cấu hình error handler và môi trường.

Kiểm tra resource có nằm trong JAR bằng cách chạy **./gradlew bootJar** rồi liệt kê entry theo công cụ JDK/zip. Tập tin classpath thường được đóng gói dưới **BOOT-INF/classes/site-assets/**. Nếu chạy bằng IDE được nhưng JAR trả 404, kiểm tra đường dẫn resource thực tế bên trong artifact thay vì thay handler mapping ngẫu nhiên.

## 6. Integration test kiểm chứng ranh giới giữa asset và API

Một thay đổi đường dẫn có thể làm hỏng API dù bạn chỉ định sửa CSS. Vì thế, kiểm thử cả **positive** (asset và API đúng) lẫn **negative** (route không tồn tại trả 404).

**src/test/java/com/example/resourceroutes/RouteIsolationTest.java**

~~~java
package com.example.resourceroutes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RouteIsolationTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void apiRouteKeepsJsonContract() throws Exception {
        mvc.perform(get("/api/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void assetRouteServesClasspathFile() throws Exception {
        mvc.perform(get("/assets/css/site.css"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.parseMediaType("text/css")))
                .andExpect(content().string(
                        containsString("background-color: #f5f7ff;")));
    }

    @Test
    void missingAssetIsNotAnApiResponse() throws Exception {
        mvc.perform(get("/assets/not-found.css"))
                .andExpect(status().isNotFound());
    }

    @Test
    void missingApiDoesNotBecomeHtml() throws Exception {
        mvc.perform(get("/api/not-found"))
                .andExpect(status().isNotFound());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
./gradlew bootJar
~~~

**Vì sao test có giá trị?**

- Kiểm tra @RestController vẫn có JSON status **ok**. Không đủ nếu chỉ check mọi request đều HTTP 200.
- Kiểm tra static content có **text/css** và nội dung file đúng, thay vì vô tình trả HTML index của SPA với status 200.
- Kiểm tra URL asset sai trả 404, không redirect sang login hoặc UI một cách ngoài ý muốn.
- Kiểm tra API sai trả 404, không bị fallback SPA trả **index.html** status 200.
- Sau này, nếu thêm Spring Security, hãy bổ sung test với các role và request chưa đăng nhập; status 401/403 hợp lệ theo security policy có thể khác trường hợp ban đầu.

Đây là test **Spring MVC qua MockMvc**, khởi động application context nhưng không mở cổng TCP thật. Khi cần xác minh reverse proxy, HTTPS, servlet context path, CDN hoặc đường dẫn qua gateway, phải có test triển khai trên HTTP thực.

## 7. Vì sao mapping có thể xung đột dù code nhìn hợp lý?

### 7.1. Static handler mặc định /** nhận request API không có mapping

Giả sử @GetMapping("/api/orders") tồn tại nhưng client gọi **/api/order** (thiếu chữ s). Trong Boot mặc định, **RequestMappingHandlerMapping** không có handler match, rồi **resource mapping /*** có thể nhận request như tên file. ResourceHttpRequestHandler tìm file tương ứng, không thấy và ném **NoResourceFoundException** (Spring Framework 6.1+). Response mặc định vẫn là 404.

**Hệ quả:** nếu có một @ControllerAdvice với **@ExceptionHandler(Exception.class)** luôn trả 500, lỗi thiếu route có thể bị biến thành 500. Không kết luận rằng resource handler đã “chiếm” API hợp lệ; vấn đề là **fallback cho API không có mapping** và **cách định dạng lỗi**.

Giải pháp thiết kế: đổi static URL thành **/assets/** bằng cách 4, hoặc tắt auto static /** và đăng ký custom /assets/** như cách 5; giữ exception handling có phân loại. Nếu API bắt buộc trả một problem JSON đồng nhất, thiết kế error handler cho **NoHandlerFoundException**, **NoResourceFoundException** và các lỗi API trong phạm vi thích hợp.

### 7.2. Controller catch-all lấn sang asset

Một controller với pattern quá rộng cho tất cả request hoặc một RouterFunction order ưu tiên có thể nhận **/assets/css/site.css** trước resource handler và trả HTML/JSON khác. Hậu quả: asset có status 200 nhưng browser báo MIME type sai, CSS không được áp dụng, JavaScript không chạy.

Giải pháp: giới hạn controller ở **/api/** và UI routes cần thiết. Tránh khái niệm “mọi URL không phải API đều được trả index.html” nếu chưa loại trừ asset, actuator, webjars và đường dẫn lỗi thật. Khi các URL chồng lấn, hãy xem **HandlerMapping order**, không chỉ so độ cụ thể hai pattern ở hai handler mapping khác nhau.

### 7.3. SPA fallback làm mất 404

Trong frontend SPA, trình duyệt có thể truy cập trực tiếp **/products/42** và cần nhận **index.html** để router phía client xử lý. Nhưng fallback sai kiểu **mọi GET → index.html** cũng có thể khiến:

~~~text
GET /api/unknown       -> 200 text/html  (sai)
GET /assets/missing.js  -> 200 text/html  (sai)
GET /products/42        -> 200 text/html  (có thể đúng cho navigation SPA)
~~~

Chỉ nên fallback cho **GET/HEAD navigation** có header **Accept: text/html**, sau khi loại trừ các prefix API, asset, management, authentication và các extension file theo kiến trúc thực tế. Trả 404 thật cho asset/API không tồn tại. Một cách khác là giao toàn bộ static/SPA fallback cho reverse proxy hoặc CDN, chỉ để Spring Boot xử lý /api/**. Hãy chọn **một** owner cho route fallback và đặt integration test cho deep link lẫn URL sai.

### 7.4. WebMvcConfigurer so với @EnableWebMvc

**@Configuration + implements WebMvcConfigurer** bổ sung rule vào MVC auto-configuration hiện có của Spring Boot. **@EnableWebMvc** chuyển trách nhiệm cấu hình MVC sang dạng thủ công hơn, có thể khiến static mapping, message converter, WebJars hoặc welcome page hoạt động khác. Đừng thêm @EnableWebMvc như giải pháp ngẫu nhiên khi handler không match.

Nếu chỉ cần đổi prefix, cân nhắc property Boot trước. Nếu cần custom resolver/location/cache khác nhau, dùng addResourceHandlers với các pattern không chồng lên API. Chỉ chọn @EnableWebMvc khi thực sự muốn chủ động cấu hình MVC toàn diện và hiểu những cấu hình phải khai báo lại.

### 7.5. Trùng chính xác một pattern giữa nhiều handler

Một WebMvcConfigurer khác hoặc auto-config có thể cùng đăng ký **/assets/***. Kết quả phụ thuộc cấu hình registry/điều kiện đăng ký; có thể gặp handler không dùng location bạn kỳ vọng, thay vì được “merge” file roots một cách tự nhiên. Đừng xem nhiều addResourceHandler cùng pattern là cơ chế ghép location mặc định.

Giải pháp: tập trung ownership mapping /assets/**, hoặc bổ sung nhiều **addResourceLocations(...)** trên **một** registration có chủ đích nếu cần nhiều thư mục đọc. Giữ danh sách location ngắn và không lộ directory nội bộ.

## 8. Bổ sung location, cache và versioning có kiểm soát

### 8.1. Nhiều nguồn file trong một namespace

Ví dụ **chỉ minh họa một phần method**, không phải file Java độc lập:

~~~java
registry.addResourceHandler("/assets/**")
        .addResourceLocations(
                "classpath:/site-assets/",
                "classpath:/shared-public-assets/")
        .setCacheControl(CacheControl.maxAge(Duration.ofMinutes(10)));
~~~

Spring tìm resource trong các location cấu hình. Nếu có hai file cùng relative path, thứ tự location ảnh hưởng file được trả; đừng tạo tên trùng mà kỳ vọng hệ thống tự phân giải theo chủ đề. Không thêm **classpath:/** tùy tiện vì có thể mở rộng tập file được tìm tới phạm vi không mong muốn.

**File ngoài JAR:** Spring hỗ trợ location theo dạng file resource, chẳng hạn **file:/srv/app/public-assets/** trên máy Linux. Chỉ dùng một thư mục đã được thiết kế public, xác định quyền đọc/owner và chiến lược cập nhật. Không map cả home directory, thư mục upload private hoặc root filesystem.

### 8.2. Caching và URL có hash

Với tên file ổn định **/assets/css/site.css**, cache dài có thể khiến người dùng giữ phiên bản cũ sau deploy. Có hai nhóm chiến lược:

| Tài nguyên | URL/cách cập nhật | Cache gợi ý |
| --- | --- | --- |
| CSS/JS chưa version hóa | Tên cố định, server có thể cập nhật nội dung | Cache ngắn hoặc cần revalidation. |
| CSS/JS có content hash | Ví dụ site-<hash>.css; URL đổi khi bytes đổi | Có thể dùng cache dài/immutable nếu pipeline bảo đảm URL đúng và asset cũ còn sẵn trong thời gian chuyển tiếp. |
| HTML index của SPA | Thường chứa reference tới JS/CSS phiên bản mới | Cache ngắn hoặc no-cache/revalidation để tránh trỏ bundle cũ sai. |
| File nhạy cảm hay theo user | Không nằm trong public asset root | Phục vụ bằng endpoint được ủy quyền với cache policy riêng. |

Spring MVC có **VersionResourceResolver** và resource chain để hỗ trợ URL version hóa. Ví dụ minh họa method thay thế riêng (không dùng đồng thời với registration cũ):

~~~java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/site-assets/")
        .setCacheControl(CacheControl.maxAge(Duration.ofDays(365))
                .cachePublic())
        .resourceChain(true)
        .addResolver(new VersionResourceResolver()
                .addContentVersionStrategy("/**"));
~~~

Đoạn bổ sung này cần import **org.springframework.web.servlet.resource.VersionResourceResolver**. Nó đăng ký chiến lược resolve version content, nhưng **không tự động sửa mọi chuỗi URL viết cứng trong HTML/JS**. Tạo URL public đúng bằng **ResourceUrlProvider** hoặc pipeline build frontend phù hợp; kiểm tra lại đường dẫn có hash được sinh, truy cập được và asset cũ xử lý đúng khi rolling deploy. Với filename không đổi, không tự gắn cache một năm cho /assets/** chỉ vì đã thêm VersionResourceResolver.

Nếu triển khai CSS/JS qua CDN, cần đồng bộ **Cache-Control, compression, content type và invalidation** giữa origin và CDN. Không nên xóa asset cũ ngay khi HTML được cache ở client vẫn tham chiếu đến phiên bản đó.

### 8.3. MIME và conditional request

ResourceHttpRequestHandler xác định media type theo resource, vì vậy CSS nên trả **text/css**, JavaScript thường trả một JavaScript media type hợp lệ, ảnh trả image/* phù hợp. Không tự trả mọi file dưới dạng text/html. Browser có thể từ chối chạy script/style nếu MIME không đúng, nhất là khi có **X-Content-Type-Options: nosniff**.

Khi server có metadata phù hợp, conditional request như **If-Modified-Since** có thể dẫn tới **304 Not Modified** để tiết kiệm băng thông. Cache header và cơ chế versioning khác nhau; 304 không có nghĩa file mới được sinh, còn cache dài không bảo đảm URL phiên bản luôn đúng.

## 9. Bảo mật: không nhầm static handler với cơ chế cho phép truy cập

### 9.1. Resource location công khai là một quyết định bảo mật

**addResourceLocations(...)** khai báo vùng có thể tìm file để phục vụ công khai. Dù Spring Framework có kiểm tra path và cơ chế bảo vệ của resource handler, bạn vẫn không nên map tới thư mục chứa file cấu hình, credential, báo cáo private hoặc upload của người dùng. Không viết resource handler tự dựng file path bằng cách nối thẳng input user vào **new File(...)** rồi đọc tùy ý.

Nếu người dùng chỉ được tải file khi có quyền, hãy thiết kế một controller/endpoint download riêng với kiểm tra identity, authorization, MIME, filename, Content-Disposition và giới hạn kích thước, thay vì công khai thư mục đó như static assets.

### 9.2. Spring Security nếu project có starter Security

Resource handler **không tự bypass Spring Security filter chain**. Khi thêm Spring Security, bạn phải quyết định asset nào public và API nào yêu cầu xác thực. Ví dụ dưới đây là **cấu hình bổ sung minh họa**, chỉ biên dịch khi project có dependency Spring Security và các import tương ứng; không thuộc project Spring Web tối thiểu ở mục 5:

~~~java
package com.example.resourceroutes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/assets/**")
                        .permitAll()
                        .requestMatchers(HttpMethod.HEAD, "/assets/**")
                        .permitAll()
                        .requestMatchers("/api/**")
                        .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Đây là ví dụ tối giản cho **phân tách quyền**, không phải cấu hình security production đầy đủ: cần chính sách xác thực thật, HTTPS, CSRF, API authentication, session/cookie và route ngoại lệ theo hệ thống. Một API sai URL nhưng chưa xác thực có thể nhận 401/403 trước khi biết route tồn tại; test public/secure theo đúng hợp đồng. Không mở **/api/** cho mọi người chỉ vì client frontend cần tải ảnh public.

### 9.3. CORS

CORS kiểm soát JavaScript từ origin khác được **đọc response**, không thay thế authentication hoặc kiểm tra quyền truy cập file. Nếu frontend và API cùng origin, thường không cần thêm CORS. Nếu frontend khác origin, cấu hình CORS có chủ đích cho **/api/** và asset riêng nếu cần; tránh dùng wildcard rộng cho endpoint có credential.

Ví dụ **đoạn method minh họa** cho WebMvcConfigurer khi cần cho frontend khác origin:

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/assets/**")
            .allowedOrigins("https://frontend.example")
            .allowedMethods("GET", "HEAD");
}
~~~

Cần import **org.springframework.web.servlet.config.annotation.CorsRegistry**. Nếu Spring Security cũng bật, cần tích hợp CORS ở filter chain đúng cách; chỉ thêm MVC CORS không đủ để xử lý mọi trường hợp preflight bị Security chặn.

## 10. Phân biệt Spring MVC, WebFlux, servlet context path và reverse proxy

- **Spring MVC:** chỉnh URL bằng **spring.mvc.static-path-pattern** hoặc WebMvcConfigurer.addResourceHandlers; handler chính là **ResourceHttpRequestHandler**.
- **Spring WebFlux:** có **spring.webflux.static-path-pattern**, **WebFluxConfigurer.addResourceHandlers**, **ResourceWebHandler**. Đừng import WebMvcConfigurer vào ứng dụng chỉ dùng WebFlux với giả định chúng sẽ chạy như Servlet.
- **server.servlet.context-path=/shop** (Servlet): route nội bộ **/api/status** có URL bên ngoài là **/shop/api/status** nếu không có proxy rewrite. Asset tương tự thành **/shop/assets/css/site.css**.
- **Reverse proxy hoặc CDN:** có thể rewrite prefix, cache hoặc route static riêng. Khi trả 404, xác định **request đã tới Spring Boot hay chưa** trước khi đổi @GetMapping/addResourceHandlers.
- **Spring Actuator:** quản lý endpoint riêng, có thể chạy trên management port khác khi cấu hình; đừng che phủ /actuator/** bằng SPA fallback hoặc expose endpoint nhạy cảm chỉ để làm UI hoạt động.

Nếu dự án dùng cả Spring Web và WebFlux dependency, loại web application được chọn có quy tắc auto-configuration; đừng suy ra mọi WebFluxConfigurer sẽ được áp dụng trong runtime Servlet. Kiểm tra web stack đang thực sự chạy và test HTTP trực tiếp.

## 11. Chẩn đoán lỗi theo triệu chứng

| Triệu chứng | Khả năng cao | Cách kiểm chứng |
| --- | --- | --- |
| **GET /assets/css/site.css → 404** | URL prefix, resource location, tên file/case, build thiếu resource | Kiểm tra pattern và đường dẫn tương đối trong JAR; gọi file đơn giản. |
| **GET /api/status → 404** | @RestController không scan, method/path khác, context path/proxy rewrite | Xem startup mapping và test MockMvc; kiểm tra host/port/prefix. |
| **GET /api/unknown → 500** | @ControllerAdvice bắt NoResourceFoundException như lỗi server | Xác nhận loại exception và rule xử lý 404; giới hạn static handler. |
| **CSS/JS trả 200 nhưng trình duyệt báo MIME** | SPA fallback trả HTML hoặc proxy trả error page với HTTP 200 | Xem Network tab: response body và Content-Type, không chỉ status. |
| **Tài nguyên bị yêu cầu login** | Spring Security filter chain chặn asset | Kiểm tra requestMatchers /assets/** và chính sách public thực tế. |
| **JS/CSS vẫn là phiên bản cũ sau deploy** | Cache-Control quá dài, URL không đổi, CDN/browser cache | Kiểm tra response headers và request URL; thêm version/hash. |
| **/webjars/** đột ngột 404 | Tắt default add-mappings hoặc đổi mapping mà chưa khai báo lại | Kiểm tra webjars dependency và resource handler được đăng ký. |
| **/assets hoạt động local nhưng không hoạt động sau deploy** | Resource không đóng gói, case-sensitive FS, proxy prefix, base URL sai | Liệt kê artifact JAR, kiểm tra access log và URL tuyệt đối. |
| **Khai báo @EnableWebMvc xong static lỗi** | MVC auto-configuration bị thay đổi | Bỏ @EnableWebMvc nếu chỉ custom một handler; dùng WebMvcConfigurer. |
| **Asset private vô tình tải được** | Location public trỏ quá rộng, authorization thiếu | Ngừng expose folder, kiểm tra owner và danh sách file, thiết kế controller được bảo vệ. |
| **/api/** và /** chồng lấn khó debug | RouterFunction/controller catch-all, custom handler order | In/test các mapping, thu hẹp prefix; test cả URL tồn tại và không tồn tại. |

### Quy trình debug có bằng chứng

1. Ghi **HTTP method, URL, status, Content-Type, response body**, xem có proxy/gateway không.
2. Xác minh **resource có trong classpath/JAR**, chú ý chữ hoa/thường và dấu /** cuối location.
3. Xác định **handler thực sự xử lý**: controller method hay ResourceHttpRequestHandler; với test có thể xem handler của MvcResult, với log có thể bật mức DEBUG phù hợp cho Spring MVC trong môi trường phát triển.
4. Kiểm tra **tính đầy đủ của route**: API hợp lệ, API sai, asset hợp lệ, asset thiếu và SPA navigation.
5. Chỉ sau đó thay mapping hoặc error handler; tránh đổi nhiều cấu hình, cache và Security cùng lúc khiến không biết sửa gì đã có tác dụng.

Nếu ứng dụng trả 404 cho một request API không tồn tại, đó có thể là hành vi đúng. Lỗi cần sửa là **API tồn tại nhưng bị route khác chiếm**, **trả body/status sai hợp đồng**, hoặc **mở vùng file không nên công khai**.

## 12. Bài tập mở rộng

### 12.1. Thêm file ảnh và thử tên file sai

Thêm **src/main/resources/site-assets/images/logo.svg**, gọi **/assets/images/logo.svg** và **/assets/images/LOGO.svg**. Trên deployment có filesystem phân biệt chữ hoa/thường, tên khác nhau có thể trả 404. Dùng request đúng path và so Content-Type có thể là image/svg+xml.

### 12.2. Bật caching có giới hạn

Đổi CacheControl từ 10 phút sang 30 giây, build lại rồi xem header với **curl -i**. Giải thích vì sao server đổi file không bắt buộc client lập tức tải lại nếu cache còn hợp lệ. Sau đó thử URL có hash với ResourceUrlProvider hoặc pipeline build frontend để hiểu cache invalidation.

### 12.3. Thử lỗi NoResourceFoundException

Tạo project đối chứng dùng static mapping mặc định /**; gọi **/api/khong-co**, quan sát status 404 và loại exception qua log/exception resolver. Sau đó đổi static pattern sang /assets/** và so sánh. Không tự ép cả hai ngoại lệ vào một HTTP 500; đây là bài về **đường đi xử lý lỗi**, không phải về bắt mọi exception.

### 12.4. Kiểm tra SPA fallback bằng test

Nếu app có SPA, hãy test ít nhất:

~~~text
GET /products/42 với Accept: text/html  -> có thể trả index.html
GET /api/unknown                         -> 404, không là HTML 200
GET /assets/unknown.js                    -> 404, không là HTML 200
POST /products/42                         -> không fallback HTML chỉ vì path tồn tại
~~~

Policy của route UI phụ thuộc sản phẩm; điều bắt buộc là không để fallback che lấp API/asset.

## 13. Checklist trước khi merge/deploy

- [ ] Route API đều nằm dưới namespace đã chọn, ví dụ **/api/**; asset dưới **/assets/**.
- [ ] Không có controller/resource handler tùy chỉnh catch-all /** hoặc có lý do và test rõ ràng nếu buộc phải dùng.
- [ ] Chọn **một** phương án quản lý static: Boot properties hoặc custom registration; không cấu hình mâu thuẫn.
- [ ] Java config dùng **WebMvcConfigurer**, không bật @EnableWebMvc chỉ để thêm static handler.
- [ ] Resource location chỉ chứa file được phép công khai và được đóng gói hoặc mount đúng.
- [ ] API tồn tại trả JSON/status đúng; API sai trả lỗi thích hợp; asset hợp lệ trả đúng bytes/MIME; asset thiếu trả 404.
- [ ] SPA fallback nếu có chỉ áp dụng cho navigation hợp lệ và loại trừ /api/**, /assets/**, /actuator/**.
- [ ] Cache-Control và version URL phù hợp chiến lược release; không cache dài cho file thay đổi tại cùng URL nếu không có revalidation thích hợp.
- [ ] Nếu có Spring Security, policy cho public asset và protected API được test tách biệt.
- [ ] Nếu có reverse proxy/CDN/context path, test URL bên ngoài thực tế và kiểm tra rewrite.
- [ ] Không lộ file private, credential, upload bảo mật hay log trong public resource root.

### Câu hỏi tự kiểm tra

**1. Nếu /api/status có @GetMapping và static handler là /**, controller có luôn bị static chiếm không?** Không. Trong cấu hình MVC thông thường, controller mapping được ưu tiên cho route match. Rủi ro dễ gặp là **API không match** rơi qua static fallback hoặc rule catch-all khác thay đổi handler.

**2. Vì sao /api/unknown đôi khi xuất hiện NoResourceFoundException?** Static mapping /** có thể bắt URL không được controller xử lý; ResourceHttpRequestHandler không tìm được file. Với Spring Framework 6.1+, exception này thường được xử lý thành 404.

**3. Khi nào chỉ dùng spring.mvc.static-path-pattern?** Khi cần đổi prefix static và location đơn giản, không cần resolver/cache đặc biệt theo từng handler.

**4. Khi nào thêm WebMvcConfigurer.addResourceHandlers?** Khi cần nhiều namespace, root file riêng, cache/resolver hoặc behavior static khác mặc định, và vẫn muốn giữ Spring Boot MVC auto-configuration.

**5. spring.web.resources.add-mappings=false có tắt MVC controller không?** Không. Nó tắt auto static resource mapping của Boot; handler tự thêm bằng WebMvcConfigurer vẫn hoạt động. Cần lưu ý welcome page/WebJars nếu ứng dụng dựa vào chúng.

**6. Vì sao static handler không phù hợp để phục vụ file upload private?** Location static thường công khai theo URL và không có authorization per-file; private download phải có cơ chế bảo vệ phù hợp.

**7. Vì sao CSS nhận 200 nhưng không áp dụng?** Có thể response thật là HTML từ fallback SPA, Content-Type không phù hợp, cache cũ hoặc URL đã bị proxy rewrite; phải xem cả body/header.

### Tài liệu chính thức

- [Spring Boot 3.3 — Servlet Web Applications: Static Content / MVC Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): default locations, static-path-pattern, static-locations, @EnableWebMvc và hành vi 404.
- [Spring Framework — Web MVC Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): WebMvcConfigurer, ResourceHandlerRegistry, CacheControl, VersionResourceResolver và ResourceUrlProvider.
- [Spring Framework 6.1 — NoResourceFoundException](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/resource/NoResourceFoundException.html): exception khi handler không tìm thấy tài nguyên.

Khi tách namespace /api/** và /assets/**, cấu hình resource handler rõ ràng và kiểm thử cả đường dẫn hợp lệ lẫn không hợp lệ, bạn sẽ biết một request thuộc về **controller API**, **static resource** hay **SPA navigation**. Đây là cơ sở để hệ thống trả đúng status, MIME, cache và quyền truy cập trong lúc phát triển cũng như khi deploy.
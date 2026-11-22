# Cấu hình spring.web.resources.* và đường dẫn tài nguyên tĩnh trong Spring Boot

## 1. Tại sao phải hiểu cả đường dẫn và resource mapping?

Khi có tệp `src/main/resources/static/css/app.css`, Spring Boot có thể trả về nội dung qua URL `/css/app.css` mà không cần controller. Nhưng nếu đổi URL thành `/assets/css/app.css` hoặc chuyển tài nguyên sang thư mục khác, ta cần phân biệt **hai loại đường dẫn**:

- **Đường dẫn tìm tài nguyên**: `spring.web.resources.static-locations` quyết định Spring Boot tìm file tại những đâu, ví dụ `classpath:/static/`, `classpath:/public/` hoặc `file:/opt/app/public/`.
- **Đường dẫn truy cập qua HTTP**: `spring.mvc.static-path-pattern` trong ứng dụng Spring MVC, hoặc `spring.webflux.static-path-pattern` trong WebFlux, quyết định URL nào được đưa đến resource handler.

Các thuộc tính `spring.web.resources.*` còn điều khiển bật/tắt mapping mặc định, HTTP caching, cache phía server, versioning và lựa chọn file đã nén.

**Mục tiêu bài học:** giải thích cơ chế phục vụ tài nguyên tĩnh; tự cấu hình được location, URL prefix, context path và cache; phân biệt MVC với WebFlux; kiểm tra tệp trong JAR; xử lý lỗi 404, trình duyệt dùng cache cũ và các rủi ro công khai tệp nhạy cảm.

> **Phiên bản:** phần property áp dụng cho Spring Boot 3.5 và 4.x ở nơi tính năng được hỗ trợ. Ví dụ chạy được sử dụng Spring Boot 3.5.x, Java 17+ và Spring MVC; nếu dùng Boot 4.x, tạo dự án với `spring-boot-starter-webmvc` thay cho `spring-boot-starter-web`. Hãy đối chiếu property list với đúng phiên bản trong dự án.

## 2. Cơ chế tĩnh và cấu trúc mặc định

Spring Boot phục vụ file tĩnh thông qua framework web:

- **Spring MVC / Servlet**: `ResourceHttpRequestHandler` tiếp nhận các request khớp resource mapping.
- **Spring WebFlux / Reactive**: `ResourceWebHandler` đảm nhiệm chức năng tương đương.
- Framework lấy phần đường dẫn tương đối từ URL, tìm tài nguyên trong các `ResourceLocation` đã cấu hình, kiểm tra truy cập rồi trả nội dung HTTP cùng media type/header phù hợp.

Theo mặc định, Boot tìm trong các thư mục classpath:

~~~text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
~~~

Đây là **địa điểm bên trong classpath khi chạy**, không phải bốn tiền tố URL. Với ứng dụng Gradle/Maven, file trong `src/main/resources/static/` được đưa vào classpath khi build; trong executable Boot JAR nó thường nằm dưới `BOOT-INF/classes/static/`.

Ví dụ cấu trúc:

~~~text
src/main/
  java/com/example/assets/AssetsApplication.java
  resources/
    application.yml
    static/
      index.html
      css/
        app.css
      js/
        app.js
      images/
        logo.svg
~~~

Với ứng dụng chạy ở HTTP root và default mapping `/**`:

| Tệp trong dự án | URL |
|---|---|
| `src/main/resources/static/css/app.css` | `GET /css/app.css` |
| `src/main/resources/static/js/app.js` | `GET /js/app.js` |
| `src/main/resources/static/images/logo.svg` | `GET /images/logo.svg` |
| `src/main/resources/static/index.html` | `GET /index.html`; có thể được dùng làm welcome page cho `/` |

**Không đặt `/static` vào URL** chỉ vì tên thư mục chứa tệp là `static`. Không trộn tài nguyên tĩnh với template động trong `src/main/resources/templates/`: template cần được view engine/controller render theo cơ chế khác.

Spring MVC còn hỗ trợ resource từ gốc ServletContext. Đối với Boot executable JAR, `src/main/webapp` không phải nơi khuyến nghị đặt static resources; WebFlux không sử dụng cơ chế ServletContext và không dùng thư mục đó. Tránh giữ cùng tên tài nguyên ở nhiều static locations vì việc tra cứu/ghi đè trở nên khó kiểm soát.

## 3. Hai nhóm property phải tách biệt

| Property | Vai trò | Mặc định hoặc lưu ý |
|---|---|---|
| `spring.web.resources.static-locations` | Danh sách gốc chứa file tĩnh | Mặc định bốn classpath locations nêu trên; khi khai báo custom sẽ **thay thế** danh sách này |
| `spring.web.resources.add-mappings` | Bật static resource mappings do Boot tự đăng ký | Mặc định `true` |
| `spring.mvc.static-path-pattern` | URL pattern cho Spring MVC | Mặc định `/**` |
| `spring.webflux.static-path-pattern` | URL pattern cho WebFlux | Mặc định `/**` |
| `server.servlet.context-path` | Prefix của ứng dụng Servlet | Không đồng nghĩa với static path pattern |
| `spring.webflux.base-path` | Base path của ứng dụng WebFlux khi cấu hình | Không phải static location |
| `spring.web.resources.cache.period` | Thời lượng cache HTTP cho resources | Có thể dùng `10m`, `1h`, `7d` |
| `spring.web.resources.cache.cachecontrol.max-age` | Chỉ thị Cache-Control max-age | Có thể ghi `1h`; thuộc nhóm cachecontrol chi tiết |
| `spring.web.resources.cache.cachecontrol.cache-public` | Cho phép shared cache lưu tài nguyên công khai | Không đặt bừa cho nội dung riêng tư |
| `spring.web.resources.cache.cachecontrol.no-store` | Không lưu resource vào cache HTTP | Tránh đặt cùng chính sách cache lâu gây mâu thuẫn |
| `spring.web.resources.cache.use-last-modified` | Hỗ trợ conditional caching theo Last-Modified | Mặc định `true` |
| `spring.web.resources.chain.enabled` | Bật resource chain | Theo mặc định không bật khi không strategy nào yêu cầu |
| `spring.web.resources.chain.cache` | Cache tra cứu resource tại server | Mặc định `true` khi chain được dùng |
| `spring.web.resources.chain.strategy.content.enabled` | Version tài nguyên theo hash nội dung | Dùng kèm cơ chế tạo/rewrite versioned URLs |
| `spring.web.resources.chain.strategy.content.paths` | URL patterns dùng content versioning | Mặc định `/**` khi strategy bật |
| `spring.web.resources.chain.strategy.fixed.enabled` | Bật fixed version strategy | Dùng cùng `fixed.version` và `fixed.paths` |
| `spring.web.resources.chain.compressed` | Tìm file `.gz`/`.br` đã nén sẵn | Không tự nén toàn bộ file theo thời gian thực |

Tên `spring.web.resources.*` là **cấu hình Boot dùng chung** cho resource handling, trong khi tên property của URL pattern phụ thuộc loại web application. Vì vậy thay đổi `spring.mvc.static-path-pattern` sẽ không điều khiển mapping của một ứng dụng WebFlux thuần.

## 4. Hiểu cơ chế ánh xạ bằng một ví dụ

Cho cấu hình:

~~~yaml
spring:
  mvc:
    static-path-pattern: "/assets/**"
  web:
    resources:
      static-locations:
        - "classpath:/frontend/"
~~~

Giả sử ứng dụng có `src/main/resources/frontend/css/site.css`.

~~~text
Request: GET /assets/css/site.css
             |
             +--- pattern /assets/** được khớp
             |
             +--- đường dẫn tương đối: css/site.css
                        |
                        v
ResourceHttpRequestHandler
                        |
                        +--- location: classpath:/frontend/
                        |
                        v
Tra cứu: classpath:/frontend/css/site.css
                        |
                        v
HTTP 200 (nếu tìm thấy và được phép trả về)
~~~

Đây là bốn tên gọi khác nhau:

- `/assets/css/site.css`: **URL request**.
- `/assets/**`: **URL pattern** được MVC dùng để định tuyến resource handler.
- `css/site.css`: **đường dẫn tương đối** sau khi bỏ prefix tĩnh.
- `classpath:/frontend/css/site.css`: **đích tìm file** trong runtime.

Trong ví dụ này, đổi URL prefix `/assets` **không yêu cầu** thêm thư mục `assets` vào vị trí tệp. Đồng thời, đổi `static-locations` sang `frontend` **không tự làm** URL chứa chữ `frontend`.

Nếu controller riêng cũng đăng ký `/assets/css/site.css`, kết quả cần xem thứ tự các handler; đừng mặc định rằng static handler sẽ luôn thắng tất cả controller.

## 5. Ví dụ chạy được: đổi static URL và location

Tạo dự án từ Spring Initializr: **Spring Boot 3.5.x**, Gradle, Java 17+, dependency **Spring Web**. Dự án khởi tạo có Gradle wrapper. Đặt các tệp sau:

~~~text
src/main/
  java/demo/assets/AssetsApplication.java
  resources/
    application.yml
    frontend/
      hello.txt
      css/
        site.css
~~~

**Tệp `src/main/java/demo/assets/AssetsApplication.java`**

~~~java
package demo.assets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AssetsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AssetsApplication.class, args);
    }
}
~~~

Class trên là một Spring Boot application hoàn chỉnh khi dự án có starter MVC đã nêu. Không cần controller cho resource tĩnh.

**Tệp `src/main/resources/application.yml`**

~~~yaml
server:
  port: 8080

spring:
  mvc:
    static-path-pattern: "/assets/**"
  web:
    resources:
      add-mappings: true
      static-locations:
        - "classpath:/frontend/"
      cache:
        period: 10m
~~~

**Tệp `src/main/resources/frontend/hello.txt`** chứa:

~~~text
Hello static!
~~~

**Tệp `src/main/resources/frontend/css/site.css`** chứa:

~~~css
body {
    color: #174ea6;
}
~~~

Từ thư mục gốc project đã tạo, chạy:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi ứng dụng đã khởi động, gửi request từ terminal khác:

~~~bash
curl -fsS http://localhost:8080/assets/hello.txt
~~~

**Response body kỳ vọng:**

~~~text
Hello static!
~~~

Kiểm tra CSS:

~~~bash
curl -fsS http://localhost:8080/assets/css/site.css
~~~

**Response body kỳ vọng:**

~~~css
body {
    color: #174ea6;
}
~~~

Kiểm tra cả status và header:

~~~bash
curl -i http://localhost:8080/assets/hello.txt
curl -i http://localhost:8080/hello.txt
~~~

Khi chỉ có các tệp và cấu hình trong bài, URL thứ nhất sẽ có 200 và URL thứ hai thông thường là 404: mapping tĩnh đã chuyển sang `/assets/**`, không còn tự phục vụ file đó ở `/hello.txt`. Header phụ thuộc HTTP server và cache policy nên không giả lập nguyên văn toàn bộ header.

**Khi dùng Boot 4.x:** chọn starter Spring Web MVC (`spring-boot-starter-webmvc`); mã `AssetsApplication.java` và các property này vẫn dùng cách tương tự.

## 6. Custom locations: thay thế mặc định và khai báo nhiều nguồn

### Trường hợp 1: chỉ dùng thư mục riêng

~~~yaml
spring:
  web:
    resources:
      static-locations:
        - "classpath:/frontend/"
~~~

Danh sách default `META-INF/resources`, `resources`, `static`, `public` **không tự được cộng thêm**. Nếu file CSS vẫn nằm ở `src/main/resources/static/css/app.css`, việc đặt location chỉ còn `frontend` sẽ khiến Boot không tìm thấy CSS từ location `static` mặc định nữa.

### Trường hợp 2: giữ thư mục cũ và thêm thư mục mới

~~~yaml
spring:
  web:
    resources:
      static-locations:
        - "classpath:/static/"
        - "classpath:/frontend/"
~~~

Nếu dự án còn cần `META-INF/resources`, `resources` hoặc `public` thì cũng phải đưa các location tương ứng trở lại danh sách. Không thêm cùng một tên file ở nhiều nguồn một cách tùy tiện; nên quy ước namespace rõ ràng.

### Trường hợp 3: dùng directory ngoài JAR

~~~yaml
spring:
  web:
    resources:
      static-locations:
        - "classpath:/static/"
        - "file:/opt/my-app/public-assets/"
~~~

Nếu máy chạy ứng dụng có tệp `/opt/my-app/public-assets/manual.pdf` và URL pattern mặc định `/**`, tệp có thể được truy cập qua `/manual.pdf`. Nếu thêm pattern `/assets/**`, URL sẽ là `/assets/manual.pdf`; filesystem path vẫn không đổi.

**Lưu ý deployment:**
- `file:/opt/...` được giải quyết trong hệ thống file **của tiến trình ứng dụng**. Trong Docker, đó là filesystem của container, không mặc nhiên là đường dẫn host.
- Folder phải tồn tại và user chạy service cần quyền đọc. Nếu mount volume, kiểm tra mount thật trong container.
- Chỉ trỏ vào thư mục đã được phép công khai. Không cấu hình `file:/` hoặc thư mục chứa `application.yml`, private keys, bản sao lưu, upload riêng tư.
- Đừng tự nhận đường dẫn file từ user rồi nối chuỗi với một thư mục công khai nếu không kiểm tra ID, quyền, path traversal và symlink. Với file bảo mật, dùng API tải file có authorization.

## 7. Context path và reverse proxy

Ví dụ Servlet app:

~~~yaml
server:
  servlet:
    context-path: "/shop"

spring:
  mvc:
    static-path-pattern: "/assets/**"
  web:
    resources:
      static-locations:
        - "classpath:/frontend/"
~~~

Với file `frontend/css/site.css`, client gọi:

~~~text
GET /shop/assets/css/site.css
~~~

`/shop` đến từ **Servlet context path**. Nó không được cộng vào `classpath:/frontend/` và không cần lặp lại trong `spring.mvc.static-path-pattern`.

Nếu phía trước có reverse proxy, CDN hoặc ingress dùng prefix, cần xác định proxy **giữ prefix hay rewrite** trước khi chuyển tới Boot. Đặt prefix hai lần có thể khiến asset bị 404. Nếu frontend render URL root-relative (bắt đầu bằng `/assets`), kiểm tra có cần prefix `/shop` hoặc helper tạo URL theo context path.

Với WebFlux, property định nghĩa base path thường dùng là `spring.webflux.base-path`, không phải `server.servlet.context-path`. Cần xác định thực sự đang ở stack Servlet hay Reactive.

## 8. So sánh MVC và WebFlux

### Spring MVC

~~~yaml
spring:
  mvc:
    static-path-pattern: "/media/**"
  web:
    resources:
      static-locations:
        - "classpath:/public-files/"
~~~

`ResourceHttpRequestHandler` dùng URL `/media/**` để tra cứu `classpath:/public-files/`. Nếu có tệp `public-files/icons/logo.svg`, URL là `/media/icons/logo.svg`.

### Spring WebFlux

~~~yaml
spring:
  webflux:
    static-path-pattern: "/media/**"
  web:
    resources:
      static-locations:
        - "classpath:/public-files/"
~~~

`ResourceWebHandler` thực hiện vai trò tương đương. Nguồn tài nguyên và ý nghĩa URL prefix giống nhau; cấu hình URL dùng `spring.webflux.static-path-pattern`.

Nếu ứng dụng có cả starter MVC và WebFlux trên classpath, Boot thường ưu tiên web application type **SERVLET/MVC**. Một dự án MVC có `WebClient` không đồng nghĩa resource handler chuyển sang reactive. Kiểm tra starter và application context đang chạy thay vì chỉ nhìn thấy WebFlux dependency.

## 9. Cache-Control: thời gian cache của trình duyệt

Với static CSS/JS không thay đổi trong một thời gian, HTTP cache giúp giảm tải và thời gian truyền. Có thể cấu hình đơn giản:

~~~yaml
spring:
  web:
    resources:
      cache:
        period: 15m
~~~

Khi muốn chỉ định Cache-Control chi tiết:

~~~yaml
spring:
  web:
    resources:
      cache:
        cachecontrol:
          cache-public: true
          max-age: 1h
~~~

`cache.period` là duration cho resource handler. `cachecontrol.max-age` cùng các property `cachecontrol.*` giúp kiểm soát chỉ thị HTTP cache chi tiết hơn và có thể ghi đè cách sinh cache policy đơn giản. Không nên đặt `no-store: true` đồng thời với `cache-public: true` và `max-age: 365d` rồi kỳ vọng policy nhất quán.

### Chọn TTL theo khả năng cập nhật file

- File **không có phiên bản trong URL** như `/css/app.css` nên có TTL thận trọng hoặc yêu cầu tái kiểm tra, vì nội dung có thể thay sau deploy.
- File **có hash nội dung trong tên** như `/css/app-<hash>.css` có thể phù hợp TTL dài, vì phiên bản mới sẽ mang URL mới.
- `index.html` của frontend thường cần thời gian cache ngắn hoặc revalidation để biết các asset mới; giữ HTML quá lâu có thể khiến trang trỏ tới assets cũ hoặc đã bị xóa.

Dùng:

~~~bash
curl -i http://localhost:8080/assets/hello.txt
~~~

để xem header thực tế. Không kết luận browser đã cache vì YAML có `period`; xác nhận `Cache-Control` và công cụ Network của trình duyệt.

### Conditional request và Last-Modified

`spring.web.resources.cache.use-last-modified` mặc định `true`. Khi resource và handler có metadata thời điểm thay đổi phù hợp, response có thể chứa `Last-Modified`. Client gửi `If-Modified-Since` khi tái kiểm tra; nếu nội dung chưa đổi, server có thể trả `304 Not Modified`.

`ETag` là cơ chế khác; không giả định mọi static resource mặc định luôn có ETag chỉ vì `use-last-modified=true`. Với tệp nằm trên classpath/JAR, metadata và caching behavior có thể khác file ngoài filesystem.

## 10. Resource chain: cache nội bộ và version hóa

Resource chain xử lý việc phân giải tài nguyên, version strategy và các bước liên quan. Cần phân biệt:

- **HTTP cache**: trình duyệt/proxy dùng lại response theo `Cache-Control`.
- **`spring.web.resources.chain.cache`**: cache kết quả tra cứu trong **server-side resource chain**; không quyết định TTL trình duyệt.
- **Version strategy**: tạo URL có phiên bản để tránh asset mới bị trộn với asset cũ.

Ví dụ bật chain:

~~~yaml
spring:
  web:
    resources:
      chain:
        enabled: true
        cache: true
~~~

Giá trị mặc định của `chain.cache` là `true`, nhưng chỉ có ý nghĩa trong resource chain được kích hoạt. Resource chain có thể tự bật khi chiến lược phù hợp đã được cấu hình; đối chiếu property của phiên bản cụ thể.

### 10.1. Content hash strategy

~~~yaml
spring:
  web:
    resources:
      chain:
        strategy:
          content:
            enabled: true
            paths:
              - "/css/**"
              - "/js/**"
~~~

Về khái niệm, resource handler có thể giải quyết URL phiên bản:

~~~text
/css/app-<content-hash>.css
/js/app-<content-hash>.js
~~~

`<content-hash>` là **ký hiệu**, không phải giá trị hash thật. Khi nội dung thay đổi, version trong URL có thể thay đổi.

**Điểm quan trọng:** chỉ bật property **không tự viết lại tất cả URL hardcode trong một trang HTML tĩnh**. Muốn HTML trỏ đúng URL có hash cần cơ chế tạo/rewrite resource URL (ví dụ tích hợp URL rewriting ở Spring MVC/template, `ResourceUrlProvider`) hoặc công cụ frontend bundler đã sinh asset filename hash. Kiểm tra HTML render và request thực tế để xác nhận version strategy hoạt động.

### 10.2. Fixed version strategy

~~~yaml
spring:
  web:
    resources:
      chain:
        strategy:
          fixed:
            enabled: true
            version: "v12"
            paths:
              - "/js/lib/**"
~~~

Với cơ chế tạo URL versioned phù hợp, asset `/js/lib/library.js` có thể được tham chiếu bằng `/v12/js/lib/library.js`. File vật lý không cần nằm trong directory tên `v12`. Mỗi release cần cập nhật version có kỷ luật và bảo đảm HTML trỏ đúng version deploy.

Có thể dùng content strategy cho mã ứng dụng và fixed strategy cho thư viện, nhưng hãy để các `paths` tách bạch, tránh chồng pattern khó dự đoán.

### 10.3. Precompressed resources

~~~yaml
spring:
  web:
    resources:
      chain:
        compressed: true
~~~

Resource chain có thể dùng bản nén sẵn `.gz` hoặc `.br` nếu artifact chứa đúng file và HTTP client gửi `Accept-Encoding` phù hợp. Nó **không tự biên dịch hoặc nén** tất cả JS/CSS trong lúc chạy. Hãy kiểm tra các file được tạo trong build, header `Content-Encoding` và `Vary`; compression động của server là chức năng cấu hình khác.

## 11. Tắt auto mapping hoặc thêm custom handler

### Tắt mapping do Boot tự đăng ký

~~~yaml
spring:
  web:
    resources:
      add-mappings: false
~~~

Việc này tắt **default static resource handling của Boot**, hữu ích với một service chỉ cung cấp API hoặc ứng dụng tự quản lý resource handler. Controller và custom mapping khác vẫn có thể hoạt động; property không phải công tắc vô hiệu hóa tất cả HTTP endpoints.

### Thêm mapping riêng trong MVC

Nếu yêu cầu phức tạp hơn các property, có thể thêm một resource handler. Đây là **fragment Java cấu hình**, đặt vào ứng dụng MVC có Spring dependencies, không phải class Java chạy độc lập:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ExtraAssetsConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manuals/**")
                .addResourceLocations("classpath:/manuals/");
    }
}
~~~

Đoạn mã trên thêm mapping `/manuals/**` đến `classpath:/manuals/`. Nó không thay đổi `spring.web.resources.static-locations` và không buộc phải tắt mapping mặc định. Tránh dùng `@EnableWebMvc` chỉ để thêm một mapping: annotation này thay đổi cách Boot auto-configure MVC và có thể khiến nhiều hành vi mặc định không còn như dự kiến.

Trong WebFlux dùng `WebFluxConfigurer.addResourceHandlers` và `ResourceWebHandler` tương ứng, không dùng API MVC để cấu hình reactive app.

## 12. Welcome page, WebJars, API và SPA routing

**Welcome page:** `index.html` trong các configured static locations có thể được dùng làm trang chào `/`, với thứ tự ưu tiên phù hợp so với controller/router. Khi thay đổi locations, việc tìm trang chào cũng đi theo location mới. Nhưng không suy diễn rằng mọi đường dẫn frontend đều được fallback đến `index.html`.

**WebJars:** các tài nguyên WebJars được đóng gói trong JAR theo cấu trúc riêng. Boot có mapping thường gặp là `/webjars/**`, điều chỉnh bằng `spring.mvc.webjars-path-pattern` hoặc `spring.webflux.webjars-path-pattern` theo stack. Không nhầm nó với việc tự đặt thư viện JS tùy ý vào classpath root.

**API routes:** với static pattern `/**`, resource handler có thể bắt một request không được controller khác xử lý rồi báo tài nguyên thiếu. Vì vậy lỗi `/api/unknown` đôi khi biểu hiện như lỗi tìm static resource, không đồng nghĩa controller API đã tồn tại. Kiểm tra route/controller, thứ tự HandlerMapping và URL path trước khi thay code.

**SPA routing:** một ứng dụng React/Vue dùng client-side router có thể tải được `/` nhưng reload `/dashboard` lại 404. Cần thiết kế fallback ở proxy hoặc controller/routing layer cho các frontend routes. Không trả `index.html` cho `/api/**` hoặc mọi lỗi tài nguyên, bởi như vậy có thể biến lỗi API thật thành response 200 HTML.

## 13. Kiểm tra artifact đóng gói và vận hành

Trong dự án Gradle đã tạo, chạy:

~~~bash
./gradlew bootJar
~~~

Sau đó xem file trong JAR:

~~~bash
jar tf build/libs/your-app.jar
~~~

`your-app.jar` là tên minh họa, hãy dùng đúng tên file build thật. Trong executable Boot JAR, với ví dụ bài thực hành, cần tìm các entries tương đương:

~~~text
BOOT-INF/classes/frontend/hello.txt
BOOT-INF/classes/frontend/css/site.css
~~~

Nếu chạy được khi `bootRun` nhưng lỗi khi chạy JAR, phải kiểm tra tệp được đóng gói và profile/config ở runtime trước khi cho rằng Spring handler sai. Đối với `file:/opt/my-app/public-assets/`, tệp **không nhất thiết** nằm trong JAR; phải tồn tại ở máy/container chạy service.

Để kiểm tra sau deploy, ghi lại:
- URL thực được browser yêu cầu, kể cả context path và proxy prefix.
- Spring MVC hay WebFlux, static-path-pattern tương ứng, danh sách locations thực tế.
- Code/status/header: 200, 304, 404, 302, 401, 403; `Cache-Control`, `Last-Modified`, `Content-Type`, `Content-Encoding`.
- Nội dung file có ở artifact hoặc thư mục runtime không.
- Security/filter chain có cho phép route static công khai không.

## 14. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `GET /css/app.css` 404 sau khi đổi URL | `spring.mvc.static-path-pattern=/assets/**` | Thử `/assets/css/app.css`; xem lại pattern đúng stack |
| `/assets/css/app.css` 404, file vẫn ở `static/css` | `static-locations` đã chuyển sang `classpath:/frontend/` | Di chuyển file hoặc đưa `classpath:/static/` vào danh sách |
| Môi trường local chạy, JAR không có file | File đặt sai folder hoặc không được đưa vào artifact | Dùng `jar tf`, xem `BOOT-INF/classes` |
| Thay `spring.mvc.*` không có tác dụng | App chạy WebFlux | Dùng `spring.webflux.static-path-pattern` |
| `add-mappings=false` làm file public biến mất | Boot không đăng ký static handler | Bật lại hoặc thêm handler thủ công |
| JS/CSS cũ sau deploy | Cùng URL và thời gian cache dài | Versioned URL/hash, cân nhắc TTL của index.html |
| Bật content strategy nhưng HTML vẫn gọi URL cũ | Chưa có bước rewrite URL | Tích hợp resource URL provider/template hoặc bundler |
| Bật compressed nhưng không thấy gzip/br | Chưa có file đã nén hoặc client không yêu cầu | Kiểm tra build outputs, Accept-Encoding, headers |
| `file:` hoạt động trên host nhưng hỏng trong container | Container không có directory/mount/quyền | Kiểm tra đúng path bên trong container |
| Request static trả 302/401/403 | Security hoặc proxy đang xử lý trước handler | Kiểm tra filter chain và policy public assets |
| `/shop/assets/logo.svg` 404 | URL prefix, context path, proxy rewrite không nhất quán | Vẽ lại URL ngoài → URL nội bộ → pattern → location |
| SPA click được nhưng F5 ở route sâu lỗi | Thiếu fallback từ frontend router sang index.html | Thiết kế fallback cho frontend routes, giữ API route chính xác |
| API path trả lỗi thiếu static resource | Default static handler `/**` đã xử lý khi thiếu controller | Kiểm tra controller mapping và cân nhắc prefix `/assets/**` |

### Trình tự debug một lỗi 404

1. Ghi request URL chính xác từ tab Network/curl.
2. Xác nhận context path và proxy rewrite.
3. Xác định stack MVC/WebFlux cùng static-path-pattern.
4. Tách phần đường dẫn tương đối của resource khỏi prefix URL.
5. Đọc `static-locations` đang có hiệu lực; nhớ config custom thay thế default locations.
6. Xác minh file trong JAR hoặc directory của runtime, không chỉ ở source IDE.
7. Nếu file có thật, kiểm tra handler custom, Security/filter và route precedence.
8. Cuối cùng mới thay đổi cache, restart, hoặc invalidate CDN dựa trên header thực.

**Ví dụ xác định từng đoạn:** URL `/shop/assets/css/site.css`, context path `/shop`, pattern `/assets/**` và location `classpath:/frontend/` nghĩa là Spring phải tìm `classpath:/frontend/css/site.css`; không phải `frontend/assets/css/site.css`.

## 15. Checklist an toàn và kiểm chứng

- [ ] Phân biệt đúng URL pattern, relative resource path, classpath/file location và context path.
- [ ] Chọn property URL đúng MVC hoặc WebFlux.
- [ ] Mọi location custom thật sự tồn tại trong JAR hoặc môi trường chạy.
- [ ] Nếu muốn giữ tài nguyên mặc định, đã khai báo lại các locations cần thiết.
- [ ] Không expose directory chứa secret, backup, upload không được phép chia sẻ.
- [ ] CSS/JS/versioned URL và Cache-Control nhất quán với chiến lược deploy.
- [ ] Kiểm tra `/`, asset links, API paths và SPA deep links độc lập.
- [ ] Kiểm tra HTTP status, `Content-Type`, `Cache-Control` và 304 khi thích hợp.
- [ ] Không dùng `@EnableWebMvc`/`@EnableWebFlux` chỉ để đổi một URL.
- [ ] Chạy thử từ JAR/container và xác minh folder/path thật trước production.

## 16. Bài tập tự kiểm tra

**Câu 1.** `src/main/resources/static/images/logo.svg` được phục vụ ở URL nào khi cấu hình mặc định và không có context path?

**Đáp án:** `/images/logo.svg`.

**Câu 2.** Nếu đặt `static-locations=classpath:/frontend/`, `classpath:/static/` còn tự được tìm không?

**Đáp án:** Không. Custom list thay thế default; muốn giữ phải khai báo lại.

**Câu 3.** Có file `frontend/docs/guide.pdf` và MVC pattern `/assets/**`, location `classpath:/frontend/`. URL đúng là gì?

**Đáp án:** `/assets/docs/guide.pdf`.

**Câu 4.** Muốn đổi URL static ở WebFlux, property nào phù hợp?

**Đáp án:** `spring.webflux.static-path-pattern`, không phải `spring.mvc.static-path-pattern`.

**Câu 5.** `cache.period=1h` có giống `chain.cache=true` không?

**Đáp án:** Không. Một bên điều chỉnh HTTP cache policy cho client; bên kia cache quá trình phân giải tài nguyên tại server.

**Câu 6.** Vì sao bật content hash strategy nhưng trang HTML viết cứng `/css/app.css` vẫn gọi URL cũ?

**Đáp án:** Cần cơ chế tạo/rewrite URL đã version hóa hoặc bundler phát URL có hash; cấu hình strategy không tự sửa mọi chuỗi hardcode.

**Câu 7.** Vì sao không nên phục vụ nguyên thư mục upload của người dùng bằng `file:`?

**Đáp án:** Dễ làm lộ file riêng tư, tăng nguy cơ path traversal, sai quyền truy cập và caching dữ liệu nhạy cảm. Cần xác thực, phân quyền và endpoint lưu trữ/tải file phù hợp.

**Bài thực hành mở rộng:** trong ví dụ mục 5, tạo `frontend/docs/readme.txt` với nội dung `Docs ready`. Truy cập `/assets/docs/readme.txt`. Sau đó chỉ đổi `spring.mvc.static-path-pattern` thành `/files/**`; dự đoán URL mới `/files/docs/readme.txt` và xác nhận rằng không cần di chuyển file. Dùng `curl -i` quan sát cache headers khi thay `cache.period` từ `10m` thành `1h`.

## 17. Tài liệu tham khảo

- [Spring Boot — Servlet Web Applications / Static Content](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot — Reactive Web Applications / Static Content](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Framework — MVC Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html)
- [Spring Framework — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)

**Ghi nhớ:** `spring.web.resources.static-locations` cho biết **đọc tệp từ đâu**; `spring.mvc.static-path-pattern` hoặc `spring.webflux.static-path-pattern` cho biết **URL nào dẫn tới handler**; `spring.web.resources.cache.*` và `spring.web.resources.chain.*` quyết định **cách cache và version hóa**. Xác minh cả URL, artifact và HTTP response khi đánh giá cấu hình.

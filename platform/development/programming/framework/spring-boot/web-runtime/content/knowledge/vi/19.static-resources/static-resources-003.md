# Welcome page, `index.html` và thứ tự lựa chọn trang mặc định trong Spring Boot

## 1. Vấn đề: tại sao truy cập `/` lại hiển thị một trang HTML?

Với ứng dụng Spring Boot web, người dùng mở `http://localhost:8080/` có thể thấy trang HTML tĩnh, trang được render bằng Thymeleaf, phản hồi của một controller, chuyển hướng đăng nhập hoặc lỗi HTTP. Không phải cứ có file tên `index.html` ở bất kỳ nơi nào trong dự án là Spring Boot tự dùng file đó. **Welcome page** là cơ chế Spring Boot tự cấu hình để cung cấp trang chủ khi ứng dụng chưa định nghĩa handler phù hợp cho đường dẫn gốc `/`.

Để hiểu chính xác phải tách **hai lần lựa chọn**:

1. **Chọn handler của URL `/`**: endpoint do ứng dụng khai báo có ưu tiên hơn welcome page tự động.
2. **Chọn nội dung bên trong welcome page**: Spring Boot ưu tiên `index.html` ở static resource locations; nếu không có trang tĩnh phù hợp mới kiểm tra template tên `index`.

Phạm vi bài: Spring Boot **3.3.x**, Spring MVC/Servlet với Java 17+; có so sánh WebFlux ở cuối. Những kết luận về thứ tự giả định MVC auto-configuration mặc định và request chấp nhận HTML.

```text
GET / với Accept: text/html
        |
        +--> Functional route cho "/" khớp? --> Dùng functional route
        |
        +--> Controller mapping cho "/" khớp? --> Dùng controller
        |
        +--> Welcome page fallback?
                 |
                 +--> Static index.html tại static locations, mapping phù hợp?
                 |         |
                 |         +--> Có --> Trang welcome tĩnh
                 |
                 +--> Template engine nhận diện template "index"?
                           |
                           +--> Có --> Render template index
                           +--> Không --> Không có welcome page tự động
```

Đây là sơ đồ trách nhiệm, không phải cam kết mọi ứng dụng chạy đúng một chuỗi phương thức Java như vậy. Security filters, servlet mappings, media types, proxy rewriting và cấu hình tùy chỉnh có thể ảnh hưởng kết quả.

## 2. Ba đối tượng khác nhau: static file, welcome mapping, route

| Khái niệm | Nơi khai báo | Kết quả thường thấy |
| --- | --- | --- |
| Static file `index.html` | `src/main/resources/static/index.html` | Có thể truy cập trực tiếp `GET /index.html` |
| Welcome page | Spring Boot tự phát hiện static `index.html` hoặc template `index` | Gắn fallback cho `GET /` |
| Route `/` | `@GetMapping("/")`, `RouterFunction` | Xử lý request gốc theo logic ứng dụng |

Một file static `index.html` **không bắt buộc** phải được truy cập qua chính URL `/index.html`. Khi được nhận diện là welcome page, nó còn phục vụ ở `/`. Hai URL có liên quan nhưng không đồng nhất: route hoặc pattern khác có thể khiến `/` xử lý khác với `/index.html`.

Một template `templates/index.html` cũng không phải static file; template engine phải nhận diện tên view logic `index` để Spring Boot có thể dùng làm template welcome. Nếu không có engine phù hợp, đặt tên file `index.html` trong `templates` không tự tạo được response HTML.

## 3. Các vị trí tìm static `index.html` và thứ tự mặc định

Spring Boot 3.3 cung cấp bốn classpath static locations mặc định. Thứ tự của danh sách trong `WebProperties.Resources` là:

| Thứ tự | Static location | File trong dự án Maven/Gradle thông thường |
| --- | --- | --- |
| 1 | `classpath:/META-INF/resources/` | `src/main/resources/META-INF/resources/index.html` |
| 2 | `classpath:/resources/` | `src/main/resources/resources/index.html` |
| 3 | `classpath:/static/` | `src/main/resources/static/index.html` |
| 4 | `classpath:/public/` | `src/main/resources/public/index.html` |

Đường dẫn `src/main/resources/resources/index.html` là hợp lệ: phần `src/main/resources` đầu tiên là classpath root; `resources/` thứ hai là thư mục con thực sự tương ứng với `classpath:/resources/`.

**Nên đặt trang chủ tĩnh ở `src/main/resources/static/index.html`**, vì dễ nhận biết và thuận tiện cho người phát triển. Nếu cùng tên `index.html` ở nhiều static locations, location được tìm thấy trước có thể chiếm ưu tiên. Nếu cùng đường dẫn có trong nhiều dependency JAR, thứ tự classpath còn có thể ảnh hưởng đến lựa chọn; không nên tạo nhiều bản index cạnh tranh.

Trong ứng dụng Servlet, Boot còn có khả năng phục vụ nội dung từ root của `ServletContext` tùy cách đóng gói. Với executable JAR, thư mục `src/main/webapp` không phải lựa chọn tin cậy cho static welcome page; ưu tiên resource đóng gói trong classpath.

Static resource mapping mặc định của Spring MVC là `/**`, sử dụng `ResourceHttpRequestHandler`. Đây là **tầng phục vụ tài nguyên** sau khi request đã được ánh xạ, không phải lý do khiến route của controller thua static file.

## 4. Thứ tự ưu tiên của các handler khi xử lý `/`

Theo tài liệu Spring Boot 3.3, các handler mappings liên quan trong MVC có thứ tự mặc định:

| Mức ưu tiên | Handler mapping | Nguồn tạo ra |
| --- | --- | --- |
| Trước | `RouterFunctionMapping` | Functional routes được đăng ký qua `RouterFunction` beans |
| Tiếp | `RequestMappingHandlerMapping` | Routes từ `@Controller`, `@RestController`, `@GetMapping` |
| Sau | `WelcomePageHandlerMapping` | Trang welcome tự động |

Vì vậy, nếu một controller thực sự khớp request `GET /`, nó có thể trả kết quả riêng ngay cả khi `static/index.html` tồn tại. Tương tự, một functional route cho `GET /` có ưu tiên trước welcome page.

Ví dụ controller:

```java
package com.example.home;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RootController {

    @GetMapping("/")
    public String root() {
        return "ROOT_FROM_CONTROLLER";
    }
}
```

Ở kịch bản không có filter can thiệp, gọi `GET /` trả body đúng là:

```text
ROOT_FROM_CONTROLLER
```

Trong khi đó, nếu `static/index.html` tồn tại và static mapping không bị sửa, URL `/index.html` vẫn có thể phục vụ file tĩnh. Hai tình huống không mâu thuẫn: **controller chiếm URL `/`, không tự xóa tài nguyên `/index.html`**.

Lưu ý: `@RestController` trả `String` như trên nghĩa là response body. Một `@Controller` thông thường trả `String "index"` lại thường biểu thị **tên view** để view resolver render. Hai loại controller không nên dùng thay thế nhau khi học cơ chế chọn trang.

Các handler mappings có thể được cấu hình order khác đi trong ứng dụng nâng cao; bảng trên mô tả **mặc định**.

## 5. Thứ tự chọn nội dung trong welcome page

Nếu request gốc chưa được route nào xử lý và welcome page đủ điều kiện, Spring Boot sử dụng quy tắc:

1. **Tìm static `index.html`** trong các static resource locations đã cấu hình.
2. **Nếu không có static welcome phù hợp, tìm template tên `index`** qua template availability providers của template engine có trong ứng dụng.
3. **Nếu không có cả hai**, Boot không tự tạo welcome page từ một file HTML ngẫu nhiên.

Ví dụ cùng tồn tại:

```text
src/main/resources/
├── static/
│   └── index.html       # WELCOME_FROM_STATIC
└── templates/
    └── index.html       # WELCOME_FROM_TEMPLATE
```

Nếu đã cài Thymeleaf, không có route `/` và static mapping mặc định, `GET /` chọn **static/index.html**. Muốn kiểm chứng fallback template, hãy tạm đổi tên hoặc xóa static index ở tất cả locations đang được xét rồi restart ứng dụng.

**Điều kiện quan trọng về `/**`:** Trong cơ chế MVC của Boot, static index thường trở thành welcome page khi static resource mapping sử dụng mẫu mặc định `/**`. Nếu ứng dụng chuyển `spring.mvc.static-path-pattern` sang `/assets/**`, static index có thể vẫn được tải qua URL `/assets/index.html`, nhưng không còn là welcome tĩnh tự động tại `/`. Khi ấy template `index` được nhận diện vẫn có thể cung cấp fallback. Đừng hiểu thứ tự "static trước template" là bỏ qua điều kiện static mapping.

## 6. Auto-configuration phát hiện welcome page

Spring Boot MVC auto-configuration phối hợp các thành phần sau:

- `WebMvcAutoConfiguration`: cung cấp cấu hình mặc định cho Spring MVC, gồm hỗ trợ static resources và welcome page khi các điều kiện auto-configuration phù hợp.
- `WebProperties.Resources`: lưu các vị trí tài nguyên tĩnh và tùy chọn xử lý resources.
- `TemplateAvailabilityProviders`: kiểm tra template logic `index` có được engine hiện có hỗ trợ không.
- `WelcomePageHandlerMapping`: ánh xạ fallback cho đường dẫn gốc trong Spring MVC.
- `ResourceHttpRequestHandler` và view resolver: phục vụ static resource hoặc render template tương ứng.

Luồng khái niệm khi khởi động:

```text
SpringApplication.run(...)
    |
    +--> Tạo Servlet web application context
    |
    +--> Bật MVC auto-configuration khi điều kiện phù hợp
    |
    +--> Đọc static locations và static path pattern
    |
    +--> Kiểm tra static index hoặc template "index"
    |
    +--> Đăng ký welcome handler nếu có trang hợp lệ
    |
    +--> Khi có request, DispatcherServlet xét handler mappings theo thứ tự
```

Spring Boot tự động **nhận diện trang welcome lúc cấu hình context**, không cần lập trình viên viết `new WelcomePageHandlerMapping(...)`. Khi thêm, đổi tên hoặc xóa index trong source của ứng dụng đang chạy, nên **restart** để loại trừ việc mapping cũ vẫn còn hoặc artifact đang chạy chưa cập nhật.

Không nên giải thích việc chọn welcome page mặc định như chức năng tự phát của embedded Tomcat: trong mô hình Spring Boot MVC, Spring MVC handler mappings và resource handling đóng vai trò chính.

## 7. Thực hành A: ứng dụng có static welcome nhưng không có controller

Ví dụ sau dùng **Spring Boot 3.3.13, Java 21**. Nó có thể chạy trong một dự án Gradle đã có Wrapper và không cần thêm bất kỳ controller nào.

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/home/WelcomeApplication.java`**

```java
package com.example.home;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WelcomeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WelcomeApplication.class, args);
    }
}
```

**`src/main/resources/static/index.html`**

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trang chủ</title>
</head>
<body>
  <h1>WELCOME_FROM_STATIC</h1>
  <p>Spring Boot tự nhận diện trang chủ tĩnh.</p>
</body>
</html>
```

Từ thư mục dự án có `gradlew`:

```bash
./gradlew bootRun
```

Mở browser hoặc dùng:

```bash
curl -s -H 'Accept: text/html' http://localhost:8080/
curl -s -H 'Accept: text/html' http://localhost:8080/index.html
```

Cả hai response HTML đều chứa **`WELCOME_FROM_STATIC`** nếu cổng 8080 sẵn sàng, không có filter/security chặn và chưa đổi static routing. Đây là kiểm chứng rằng file tĩnh được dùng ở cả URL trực tiếp và fallback welcome.

Không cần tự viết `@GetMapping("/")` để chỉ phục vụ một file HTML tĩnh. Các asset khác trong `static/` như `css/site.css` vẫn dùng quy tắc static resource mapping bình thường.

## 8. Thực hành B: route `/` thắng static index

Giữ file `static/index.html` và thêm `RootController` ở mục 4 vào cùng package `com.example.home`. Restart:

```bash
./gradlew bootRun
```

Thử:

```bash
curl -s http://localhost:8080/
curl -s http://localhost:8080/index.html
```

Kết quả thứ nhất là `ROOT_FROM_CONTROLLER`; kết quả thứ hai vẫn chứa `WELCOME_FROM_STATIC`. Nguyên nhân là route `/` được xét ở `RequestMappingHandlerMapping` trước `WelcomePageHandlerMapping`.

Khi xóa hoặc vô hiệu hóa controller và restart, request root trở về welcome tĩnh nếu các điều kiện ban đầu vẫn giữ nguyên. Dùng việc thêm/bỏ route như một thí nghiệm **để hiểu thứ tự**, không phải cách khuyến khích route chồng chéo trong ứng dụng thật.

## 9. Thực hành C: template `index` thay cho static index

Để quan sát nhánh fallback template:

1. Bỏ `RootController` nếu đã thêm ở bài B.
2. Di chuyển hoặc đổi tên `src/main/resources/static/index.html`; kiểm tra không còn static `index.html` nào ở locations mặc định khác.
3. Thêm Thymeleaf vào dependencies của project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Khối dependencies trên là **bản thay thế** khối tương ứng trong bài A, không cần để hai khối giống nhau.

Tạo **`src/main/resources/templates/index.html`**:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Trang từ template</title>
</head>
<body>
  <h1>WELCOME_FROM_TEMPLATE</h1>
</body>
</html>
```

Restart và kiểm tra:

```bash
./gradlew bootRun
curl -s -H 'Accept: text/html' http://localhost:8080/
```

Body phải chứa **`WELCOME_FROM_TEMPLATE`** khi cấu hình template resolver mặc định hoạt động và không có route `/` chiếm ưu tiên. Không cần controller chỉ để bật welcome template.

**Không nhầm:** `templates/index.html` không tự trở thành static file tại URL `/index.html`. Nếu chỉ tạo file template mà không thêm template engine hỗ trợ, Spring Boot thường không có view resolver để render template đó. Những template engine khác có thể dùng phần mở rộng file khác; quy tắc nền tảng là template logic tên `index` được framework nhận diện.

## 10. Tùy biến nơi tìm file và URL truy cập

### 10.1. Thay static resource locations

**`application.properties`**

```properties
spring.web.resources.static-locations=classpath:/website/
```

Thuộc tính này **thay danh sách classpath static locations mặc định** bằng vị trí được khai báo. Để có static welcome theo cấu hình mới, đặt file tại:

```text
src/main/resources/website/index.html
```

Nếu vẫn giữ file trong `static/` nhưng đã thay locations thành `classpath:/website/`, Boot sẽ không tiếp tục tìm static index ở thư mục cũ theo mặc định.

Nếu muốn hai locations, khai báo rõ:

```properties
spring.web.resources.static-locations=classpath:/website/,classpath:/static/
```

Vị trí trước thường được ưu tiên khi cùng chứa `index.html`; hãy tránh trùng lặp để hành vi ổn định. Trong ứng dụng servlet, cấu hình còn có thể liên quan root của `ServletContext`, nhưng điều quan trọng với executable JAR là kiểm tra resource thực tế đã được đóng gói vào classpath.

### 10.2. Thay URL pattern của static resources

**`application.properties`**

```properties
spring.mvc.static-path-pattern=/assets/**
```

Với file `src/main/resources/static/index.html`, URL phục vụ tài nguyên trực tiếp trở thành:

```text
GET /assets/index.html
```

Nhưng `GET /` **không được bảo đảm** vẫn dùng static index như trước: vì welcome tĩnh có điều kiện với mapping `/**`, mẫu `/assets/**` có thể làm mất fallback static ở root. Nếu thật sự muốn route `/`, hãy tạo route hoặc dùng template welcome có điều kiện phù hợp.

So sánh các thuộc tính:

| Thuộc tính | Thay đổi |
| --- | --- |
| `spring.web.resources.static-locations` | Nơi tìm các file static |
| `spring.mvc.static-path-pattern` | URL nào được static resource handler xử lý |
| `spring.web.resources.add-mappings` | Có đăng ký mặc định các static resource mappings hay không |
| `server.port` | Cổng nhận kết nối HTTP |
| `server.servlet.context-path` | Tiền tố đường dẫn của toàn Servlet app |

Thay `static-locations` không đổi tiền tố URL; thay `static-path-pattern` không chuyển file trên ổ đĩa; thay `context-path` không tạo thêm thư mục con trong `static`.

### 10.3. Context path khác root resource path

```properties
server.servlet.context-path=/demo
```

Lúc này static welcome cho application root thường được truy cập tại:

```text
http://localhost:8080/demo/
```

Bạn vẫn giữ file ở `src/main/resources/static/index.html`, không chuyển sang `static/demo/index.html`. Đối với Spring MVC, đường dẫn nội bộ cần xử lý vẫn là `/`; servlet context path được thêm vào URL bên ngoài.

Nếu có reverse proxy, base path và rewrite rules có thể làm URL public khác URL backend. Cần kiểm tra request thực tế đến ứng dụng trước khi sửa source resources.

## 11. `Accept`, Spring Security và request không phải HTML

Welcome page được thiết kế cho điều hướng web đến trang chủ. Browser thường gửi `Accept` có `text/html`, phù hợp với cơ chế welcome. Đối với MVC, welcome mapping chỉ áp dụng khi request chấp nhận media type HTML. Vì vậy không nên giả định một API client yêu cầu riêng `application/json` sẽ nhận chính welcome HTML.

Kiểm tra:

```bash
curl -i -H 'Accept: text/html' http://localhost:8080/
curl -i -H 'Accept: application/json' http://localhost:8080/
```

Kết quả thứ hai còn phụ thuộc các mappings và exception handling của ứng dụng: có thể là một kết quả khác hoặc lỗi HTTP. Không nên khẳng định cố định mã 404/406 cho mọi trường hợp.

Spring Security có thể chạy **trước** DispatcherServlet. Nếu request `/` bị yêu cầu đăng nhập, browser có thể nhận `302` đến `/login`, `401` hoặc `403`, tùy security filter chain. Đây không nhất thiết là lỗi `WelcomePageHandlerMapping`; phải kiểm tra chính sách xác thực/ủy quyền trước khi đổi static locations.

Với SPA như React/Vue/Angular đóng gói trong `static/`, welcome page cho `/` **không tự là catch-all fallback** cho mọi URL như `/orders/123`. Client-side routing qua deep link cần cơ chế server fallback riêng, đồng thời bảo đảm không chiếm nhầm `/api/**` và các resource thực sự không tồn tại.

## 12. Khác biệt cần nhớ giữa Spring MVC và WebFlux

Spring Boot hỗ trợ welcome page trong cả Servlet MVC lẫn reactive WebFlux, cùng tư tưởng **static index trước, template index sau; route ứng dụng trước fallback**. Tuy nhiên implementation khác nhau:

| Khía cạnh | Spring MVC (Servlet) | Spring WebFlux |
| --- | --- | --- |
| Resource handler | `ResourceHttpRequestHandler` | `ResourceWebHandler` |
| Pattern static resource | `spring.mvc.static-path-pattern` | `spring.webflux.static-path-pattern` |
| Welcome handler | `WelcomePageHandlerMapping` | Welcome router function trong reactive mapping |
| Static locations | `spring.web.resources.static-locations` | `spring.web.resources.static-locations` |
| Route chủ động | MVC `@GetMapping` hoặc `RouterFunction` | Reactive `@GetMapping` hoặc `RouterFunction` |
| Template | View resolver/template engine tương thích MVC | View resolver/template engine tương thích WebFlux |

`spring.mvc.static-path-pattern` không điều khiển resource handler của WebFlux. Tương tự, `server.servlet.context-path` thuộc servlet deployment, không phải cấu hình URL cho mọi ứng dụng reactive.

Nếu project có đồng thời `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot mặc định thường suy ra **SERVLET**, vì vậy phải xác định `WebApplicationType` trước khi kết luận stack nào xử lý `/`.

## 13. Ma trận dự đoán trang hiển thị tại `/`

Giả định request `GET /` chấp nhận HTML, Spring MVC mặc định, không có filter/security blocker, static mapping `/**` trừ khi ghi chú khác:

| Route `/` | Static index hợp lệ | Template index hợp lệ | Kết quả ưu tiên |
| --- | --- | --- | --- |
| Không | Có | Không | Static `index.html` |
| Không | Không | Có | Template `index` |
| Không | Có | Có | Static `index.html` |
| `@GetMapping("/")` khớp | Có | Có | Controller |
| Functional `GET("/")` khớp | Có | Có | Functional route |
| Không | Không | Không | Không có welcome page tự động |
| Không, static pattern `/assets/**` | Có | Không | Không còn static welcome tự động tại `/` |
| Không, static pattern `/assets/**` | Có | Có | Template `index` có thể là fallback |

Ma trận minh họa **thứ tự ưu tiên**, không thay thế kiểm thử khi có handler mappings đặc biệt, content negotiation riêng, WAR servlet root hoặc reverse proxy rules.

## 14. Kiểm thử ứng dụng bằng HTTP thật

Trong dự án của bài thực hành A, đã có `spring-boot-starter-test`. Có thể viết integration test qua cổng ngẫu nhiên để kiểm tra body HTML thực sự.

**`src/test/java/com/example/home/WelcomeHttpTest.java`**

```java
package com.example.home;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WelcomeHttpTest {

    @Autowired
    TestRestTemplate client;

    @Test
    void rootServesStaticIndex() {
        ResponseEntity<String> response =
                client.getForEntity("/", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("WELCOME_FROM_STATIC");
    }
}
```

Chạy:

```bash
./gradlew test
```

Test này dành cho **static-only scenario**: phải bỏ `RootController` của bài B, dùng static index của bài A và không đổi context path. `RANDOM_PORT` bật embedded server thật; HTTP response body là bằng chứng rõ hơn về việc static welcome đã được phục vụ so với chỉ nhìn có bean resource handler.

Nếu dùng `MockMvc`, cần phân biệt việc kiểm tra mapping/forward với việc nhận body sau dispatch qua server thật. Với mục tiêu xác nhận `GET /` thực tế hiển thị file HTML, integration test HTTP như trên thường dễ diễn giải hơn.

## 15. Cách chẩn đoán khi trang chủ không đúng

Kiểm tra từ **route, cơ chế welcome, static locations, template engine** đến các tầng Security và deployment:

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Root trả text/JSON của API | Controller hoặc functional route `/` có ưu tiên | Tìm `@GetMapping("/")` và `RouterFunction` |
| Root hiện template dù có static index trong source | Static file không nằm trong location hiệu lực, file chưa vào artifact, hoặc static pattern đã đổi | Kiểm tra packaged resources, `static-locations`, `static-path-pattern` |
| `/assets/index.html` chạy, `/` không chạy | Static path chuyển sang `/assets/**`; không còn static welcome root | Cấu hình root route riêng hoặc template nếu phù hợp |
| Chỉ có `templates/index.html` mà root 404 | Thiếu template engine hoặc view resolver chưa nhận diện `index` | Kiểm tra Thymeleaf/FreeMarker starter và template config |
| `/` hiện template nhưng `/index.html` trả 404 | Template không phải static resource | Kiểm tra cách render và URL thực tế |
| Root chuyển sang login / trả 401 hay 403 | Filter hoặc Spring Security chặn | Xem filter chain, các rule cho `/` và assets |
| Root vẫn là trang cũ | Artifact cũ, proxy/browser cache hoặc chưa restart | Kiểm tra JAR/bootRun, refresh, dùng `curl` |
| `/` chạy nhưng SPA deep link không chạy | Welcome mapping chỉ xử lý root | Thiết kế fallback riêng cho client routes |
| Dùng `server.servlet.context-path=/demo` mà gọi `/` | URL ngoài thiếu prefix servlet | Thử `/demo/` |
| Sau `@EnableWebMvc` bị mất auto resource behavior | Ứng dụng thay đổi một phần MVC auto-configuration | Ưu tiên `WebMvcConfigurer` nếu muốn giữ Boot defaults |
| Có nhiều static index cạnh tranh | Static location/classpath precedence | Loại bản thừa, chọn một nguồn rõ ràng |

Lệnh có ích trong development:

```bash
curl -i -H 'Accept: text/html' http://localhost:8080/
curl -i http://localhost:8080/index.html
./gradlew bootRun --args='--debug'
```

`--debug` in điều kiện auto-configuration để hỗ trợ điều tra. Nếu có Spring Boot Actuator và chủ động expose endpoint phù hợp, `/actuator/mappings` có thể giúp quan sát handler mappings; không nên mở public endpoint quản trị chỉ vì debug welcome page.

Với nhiều Spring profiles, đọc effective properties của đúng profile đang chạy. Nếu deploy JAR/WAR/container, kiểm tra file `index.html` trong **artifact thực tế** chứ không chỉ trên working tree.

## 16. Những lỗi tư duy thường gặp và tự kiểm tra

**Các hiểu nhầm:**

1. “Có file `index.html` ở đâu cũng làm trang chủ.” Sai: phải thuộc static locations được xét hoặc template `index` được engine nhận diện.
2. “Template `index.html` thắng static vì template động hơn.” Sai: static trước, template sau trong welcome fallback.
3. “Welcome page luôn thắng `@GetMapping("/")`.” Sai: application route được xét trước.
4. “`templates/index.html` luôn phục vụ trực tiếp tại `/index.html`.” Sai: template cần view engine và không mặc nhiên là static asset.
5. “Đổi `spring.mvc.static-path-pattern` giống đổi `spring.web.resources.static-locations`.” Sai: một cái đổi URL, một cái đổi nơi tìm file.
6. “Đổi static pattern mà root vẫn luôn tự dùng static index.” Sai: phải xét điều kiện welcome với `/**`.
7. “SPA có index rồi mọi deep link đều tự hoạt động.” Sai: cần fallback routing riêng cho client-side URLs.
8. “`@RestController` trả về `"index"` đồng nghĩa render template.” Sai: đây là response body.
9. “Thay file ở source thì chương trình JAR cũ tự cập nhật.” Sai: cần đồng bộ resources và thường restart.
10. “Trang root hiển thị login nghĩa là không tìm thấy welcome.” Sai: filter/security có thể xử lý trước MVC.

**Câu hỏi ôn tập:**

- Nếu có `static/index.html`, `templates/index.html` và Thymeleaf nhưng không có route `/`, file nào được chọn mặc định?
- Nếu thêm `@GetMapping("/")`, tại sao `/` có thể khác `/index.html`?
- Vì sao có đường dẫn `src/main/resources/resources/index.html` trong danh sách hợp lệ?
- Khi set `spring.web.resources.static-locations=classpath:/website/`, phải di chuyển static index đi đâu?
- Vì sao `/assets/index.html` vẫn chạy nhưng `/` không còn welcome tĩnh sau khi đổi `spring.mvc.static-path-pattern=/assets/**`?
- Khi nào template logic `index` được render thay cho static index?
- Với `server.servlet.context-path=/shop`, URL ngoài của welcome page là gì?
- Đâu là bước chẩn đoán đầu tiên nếu request `/` trả redirect tới login?

**Nguyên tắc ứng dụng:** Với landing page tĩnh đơn giản, đặt **một** `index.html` tại `src/main/resources/static/`, giữ static mapping mặc định và không định nghĩa route root trùng lặp. Khi cần HTML động, dùng template/view controller có chủ đích. Khi ứng dụng cần hành vi đặc biệt tại `/`, hãy khai báo route rõ ràng và xem welcome page như **fallback**.

### Tài liệu tham khảo

- Spring Boot 3.3 — Servlet web applications, Static Content / Welcome Page: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive web applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework — MVC static resources: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Guide — Serving Web Content with Spring MVC: https://spring.io/guides/gs/serving-web-content
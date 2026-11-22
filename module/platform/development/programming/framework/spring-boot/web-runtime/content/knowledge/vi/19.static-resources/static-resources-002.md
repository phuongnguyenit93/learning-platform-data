# Cơ chế phục vụ tài nguyên tĩnh trong Spring MVC và Spring WebFlux

**Phạm vi:** Spring Boot 3.5.x, Java 17+, Spring MVC (Servlet stack) và Spring WebFlux (reactive stack). Bài học giải thích **cách HTTP request được ánh xạ tới CSS, JavaScript, ảnh, font, HTML tĩnh và WebJars**, cách cấu hình nơi lưu trữ/URL, cache, resource chain, bảo mật, và cách chẩn đoán lỗi khi đóng gói chạy JAR.

## 1. Tài nguyên tĩnh là gì?

**Static resource** (tài nguyên tĩnh) là tệp đã tồn tại sẵn, được server gửi cho HTTP client mà không cần dựng riêng một response từ dữ liệu nghiệp vụ ở mỗi request. Ví dụ:

- `index.html`: trang HTML có thể được gửi trực tiếp;
- `css/site.css`: stylesheet;
- `js/site.js`: JavaScript;
- `images/logo.svg`, `images/banner.png`: ảnh;
- `fonts/app.woff2`: font;
- thư viện JavaScript/CSS đã đóng gói thành WebJar.

Khái niệm “tĩnh” nói về **cách server lấy nội dung từ resource**, không có nghĩa JavaScript sẽ không chạy trên browser. Tệp HTML tĩnh vẫn có thể dùng `fetch()` gọi REST API để lấy dữ liệu động.

So sánh ba nguồn nội dung dễ nhầm:

| Nguồn | Ví dụ thư mục | Cơ chế xử lý | Phù hợp |
| --- | --- | --- | --- |
| **Static resource** | `src/main/resources/static/` | Resource handler tìm tệp và ghi HTTP response | CSS, JS, ảnh, HTML không cần render server |
| **Server-side template** | `src/main/resources/templates/` | View engine như Thymeleaf/FreeMarker render model thành HTML | Giao diện có dữ liệu render từ server |
| **REST/controller endpoint** | Java `@RestController`, `@GetMapping` | Java handler xử lý request và tạo response | JSON, tác vụ nghiệp vụ, nội dung động |

Không nên đặt dữ liệu bí mật, private keys, file cấu hình chứa credentials hoặc dữ liệu chỉ dành cho người dùng có quyền trong thư mục static công khai. Mặc định, tài nguyên tĩnh được thiết kế để có thể truy cập qua URL nếu không bị lớp bảo mật chặn.

## 2. Luồng xử lý HTTP: giống nhau về ý tưởng, khác nhau về handler

Ở mức khái niệm, khi browser truy cập `GET /css/site.css`:

1. HTTP server nhận request.
2. Hệ thống routing/handler mapping xem đường dẫn khớp với controller hay mapping tài nguyên tĩnh.
3. Khi khớp static resource handler, framework trích đường dẫn tương đối (ví dụ `css/site.css`).
4. Framework tìm tài nguyên trong các vị trí được phép, qua `ResourceResolver` nếu cấu hình resource chain.
5. Nếu tìm được, framework chọn media type thích hợp, áp dụng cache/conditional headers, rồi gửi nội dung file.
6. Nếu không có tệp hợp lệ, trả **404** qua cơ chế xử lý lỗi của ứng dụng; một số request có thể bị chặn **401/403** ở tầng security trước đó.

~~~text
Browser: GET /css/site.css
           │
           ▼
  HTTP server (Tomcat/Jetty/Netty...)
           │
      Handler mapping
           │
           ├── Controller/RouterFunction khớp cụ thể ─► handler ứng dụng
           │
           └── Mapping static / ** (mặc định) ────────► resource handler
                                                          │
                                             ResourceResolver / Transformer
                                                          │
                                                classpath:/static/
                                                classpath:/public/
                                                classpath:/resources/
                                                classpath:/META-INF/resources/
                                                          │
                                      ┌───────────────────┴─────────────────┐
                                      ▼                                     ▼
                              Có tệp hợp lệ                            Không có tệp
                              200 / 304 / ...                              404
~~~

**Trong Spring MVC:** luồng request thông qua `DispatcherServlet`; handler tài nguyên tĩnh là `org.springframework.web.servlet.resource.ResourceHttpRequestHandler`. Nguồn tài nguyên có thể nằm trên classpath và, trong ứng dụng Servlet phù hợp, ở root của `ServletContext`. Việc phục vụ static thường do Spring MVC resource handler đảm nhiệm; không nên trông chờ container “default servlet” tự phục vụ thay.

**Trong Spring WebFlux:** luồng request qua reactive `DispatcherHandler`; handler tương ứng là `org.springframework.web.reactive.resource.ResourceWebHandler`. WebFlux không phụ thuộc Servlet API, nên không dùng servlet-context root theo cách MVC, cũng không coi `src/main/webapp` là nơi chứa static của reactive app.

Handler tĩnh **không phải controller Java do ta bắt buộc phải tự viết**. Spring Boot cung cấp auto-configuration tạo các resource handler mặc định khi ứng dụng được cấu hình như một web application phù hợp.

### Vì sao một URL có thể được controller xử lý thay cho file?

Mặc định static mapping khá rộng: `/**`. Controller route có thứ tự ưu tiên thích hợp vẫn có thể xử lý URL của chính nó; static mapping đóng vai trò phục vụ resource còn lại. Vì thế `@GetMapping("/api/ping")` không bị resource handler `/**` “nuốt” trong cấu hình Boot bình thường.

Ngược lại, khi không có controller cho `/some-path`, mapping rộng của static resource có thể nhận request nhưng không tìm được file. **Spring MVC** khi đó có thể ném `NoResourceFoundException` thay cho `NoHandlerFoundException`. Hai exception khác nhau không nhất thiết nghĩa là status khác nhau: thường vẫn là HTTP 404. Nếu muốn tách định tuyến API rõ ràng, có thể giới hạn static pattern thành `/assets/**`.

## 3. Bốn vị trí static mặc định trong Spring Boot

Spring Boot tự tìm tài nguyên trong các vị trí classpath sau (đã sắp theo danh sách mặc định của cấu hình):

1. `classpath:/META-INF/resources/`
2. `classpath:/resources/`
3. `classpath:/static/`
4. `classpath:/public/`

Trong dự án Maven hoặc Gradle chuẩn, các thư mục này thường được tạo dưới `src/main/resources`. Chẳng hạn:

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/demo/DemoApplication.java
    └── resources/
        ├── static/
        │   ├── index.html
        │   ├── css/site.css
        │   ├── js/site.js
        │   └── images/logo.svg
        ├── public/
        │   └── robots.txt
        └── templates/
            └── dashboard.html
~~~

Với URL pattern mặc định `/**` và app chạy ở HTTP root:

| File trên classpath | URL HTTP | Có phục vụ trực tiếp? |
| --- | --- | --- |
| `static/index.html` | `/index.html`, thường cả `/` nhờ welcome page | Có |
| `static/css/site.css` | `/css/site.css` | Có |
| `static/js/site.js` | `/js/site.js` | Có |
| `static/images/logo.svg` | `/images/logo.svg` | Có |
| `public/robots.txt` | `/robots.txt` | Có |
| `templates/dashboard.html` | `/dashboard.html` | **Không** chỉ vì file nằm trong templates; cần view controller/renderer thích hợp |

**Thư mục `static` không xuất hiện trong URL.** `/static/css/site.css` thường 404, vì framework tìm tệp có đường dẫn tương đối `static/css/site.css` dưới vị trí `classpath:/static/`, thành ra bị lặp “static”.

Nếu đồng thời có cùng đường dẫn tương đối ở nhiều location (ví dụ `static/logo.svg` và `public/logo.svg`), việc chọn file phụ thuộc **thứ tự các locations**; nên tránh trùng tên gây khó hiểu, không dựa vào kết quả tình cờ của cách đóng gói.

**Khác biệt đóng gói cần nhớ:**
- Với **executable JAR** của Spring Boot, đặt tệp trong `src/main/resources/static/` là cách thông dụng; khi đóng gói chúng xuất hiện dưới classpath của JAR (thường trong `BOOT-INF/classes/static/`).
- `src/main/webapp` là bố cục truyền thống cho **WAR/Servlet**; với ứng dụng Spring Boot dạng JAR nó có thể bị bỏ qua, và WebFlux không hỗ trợ kiểu WAR servlet. Đừng dùng `src/main/webapp` để chứa static của ứng dụng JAR.
- `META-INF/resources` có thể nằm trong JAR phụ thuộc, thuận lợi cho frontend resources hoặc WebJars; không tự copy mọi file trong dependencies sang `static`.

## 4. URL pattern và resource location là hai khái niệm khác nhau

**URL pattern** là đường dẫn mà HTTP client dùng để yêu cầu resource. **Resource location** là chỗ server tìm file. Chúng là hai phép ánh xạ liên tiếp.

Ví dụ cấu hình MVC:

~~~properties
spring.mvc.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/site-assets/
~~~

Cùng với file `src/main/resources/site-assets/css/app.css`, URL sẽ là **`/assets/css/app.css`**, còn `/css/app.css` không được định tuyến bởi static mapping trên. Không có thư mục `assets` trên đĩa là điều hoàn toàn bình thường: `/assets/**` chỉ là **URL prefix**.

Bảng so sánh trực tiếp:

| Thành phần | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Handler tĩnh | `ResourceHttpRequestHandler` | `ResourceWebHandler` |
| Mặc định URL pattern | `/**` | `/**` |
| Cấu hình URL pattern | `spring.mvc.static-path-pattern` | `spring.webflux.static-path-pattern` |
| Cấu hình locations | `spring.web.resources.static-locations` | `spring.web.resources.static-locations` |
| Mở rộng bằng code | `WebMvcConfigurer#addResourceHandlers` | `WebFluxConfigurer#addResourceHandlers` |
| Bổ sung static từ servlet root | Có ở MVC/Servlet phù hợp | Không dùng ServletContext root |
| Kết hợp WebJars | Được hỗ trợ | Được hỗ trợ |

**Lưu ý về property chung:** `spring.web.resources.static-locations` **thay danh sách mặc định**, không tự cộng thêm. Nếu bạn chỉ khai báo `classpath:/site-assets/`, các tệp từng nằm trong `classpath:/static/` có thể không còn phục vụ như trước (với Servlet MVC, servlet-context root có điều kiện xử lý riêng). Muốn giữ nhiều location, khai báo tất cả:

~~~properties
spring.web.resources.static-locations=classpath:/site-assets/,classpath:/static/,classpath:/public/
~~~

Nếu ứng dụng có nhiều profile, hãy xác nhận **effective configuration** sau khi áp dụng properties từ file môi trường, environment variables, command-line options và profile; đôi khi một property của profile production thay toàn bộ locations.

### Base path, context path và reverse proxy

Một ứng dụng MVC được cấu hình `server.servlet.context-path=/shop` có URL hiển thị, ví dụ `/shop/css/site.css`. Với WebFlux có thể dùng `spring.webflux.base-path=/shop` trong stack tương ứng. Đây là **base path của ứng dụng**, không phải tên thư mục chứa tài nguyên.

Nếu trang HTML sử dụng liên kết tuyệt đối `href="/css/site.css"`, browser sẽ tìm tại **root của domain**, có thể sai khi app nằm dưới `/shop` hoặc phía sau reverse proxy thêm prefix. Liên kết tương đối `href="./css/site.css"` trong trang `/shop/index.html` có thể phù hợp hơn; còn ứng dụng server-side templates nên sinh URL theo context path. Cần xác nhận proxy forward headers và deployment thực tế thay vì sửa ngẫu nhiên tên file.

## 5. Spring MVC: cấu hình và handler

Trong ứng dụng có `spring-boot-starter-web`, Boot cấu hình MVC và static resource handler. Đối với trường hợp thông thường, **chỉ cần tạo file trong `src/main/resources/static/`**, không phải viết controller gọi `Files.readAllBytes(...)`.

Nếu cần thêm một thư mục custom nhưng **giữ auto-configuration của Boot**, đăng ký `WebMvcConfigurer`:

**File `src/main/java/com/example/demo/ExtraMvcAssets.java`**, thuộc **project MVC**:

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ExtraMvcAssets implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/extra/**")
                .addResourceLocations("classpath:/custom-assets/")
                .setCacheControl(CacheControl.maxAge(Duration.ofMinutes(10)));
    }
}
~~~

Nếu có file `src/main/resources/custom-assets/manual.pdf` thì URL `/extra/manual.pdf` được ánh xạ sang file đó. `setCacheControl` cấu hình cache cho mapping vừa đăng ký, không cần áp dụng cho mọi static resource. Đường location nên có dấu `/` kết thúc để phân giải tương đối đúng.

**Không thêm `@EnableWebMvc` vào cấu hình trên** nếu bạn muốn giữ Spring Boot MVC auto-configuration. Annotation này trao quyền cấu hình MVC đầy đủ cho ứng dụng, có thể làm mất các mapping hoặc tùy chỉnh mặc định của Boot. Nếu cần kiểm soát hoàn toàn, phải tự đăng ký mọi cấu hình bạn phụ thuộc.

**Điểm dễ nhầm:** `ResourceHandlerRegistry` của MVC nằm trong package `org.springframework.web.servlet.config.annotation`; nó không phải class cùng tên của reactive stack. Trộn sai import sẽ không biên dịch hoặc không áp dụng đúng.

## 6. Spring WebFlux: cùng bài toán, mô hình non-blocking

Một Spring Boot WebFlux application thường dùng `spring-boot-starter-webflux` và một HTTP runtime reactive, phổ biến là Reactor Netty. Khi client yêu cầu `GET /css/site.css`, `DispatcherHandler`/handler mappings đi đến `ResourceWebHandler`. File được trả thông qua hệ thống Spring `Resource` và cơ chế response reactive.

Default static location và URL pattern về ý tưởng **gần giống MVC**. Khác biệt chủ yếu là **kiểu web runtime**, API cấu hình, cách xử lý response reactive, và WebFlux **không có servlet context root/default servlet**.

Ví dụ đổi URL prefix trong **WebFlux**:

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

Với file `src/main/resources/static/css/site.css`, client dùng `/assets/css/site.css`. Cấu hình riêng của MVC `spring.mvc.static-path-pattern` sẽ không điều khiển routing static của WebFlux app.

Thêm thư mục custom trong WebFlux thông qua `WebFluxConfigurer`:

**File `src/main/java/com/example/demo/ExtraFluxAssets.java`**, thuộc **project WebFlux**:

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ExtraFluxAssets implements WebFluxConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/extra/**")
                .addResourceLocations("classpath:/custom-assets/")
                .setCacheControl(CacheControl.maxAge(Duration.ofMinutes(10)));
    }
}
~~~

Tương tự MVC, file `custom-assets/manual.pdf` được phục vụ qua `/extra/manual.pdf` nếu security cho phép. Không đưa **hai class `ExtraMvcAssets` và `ExtraFluxAssets` vào một project chỉ để “tăng khả năng tương thích”**; chọn đúng web stack.

Nếu project khai báo **cả** `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thông thường ưu tiên **Servlet/MVC application type**; phụ thuộc WebFlux đôi khi chỉ dùng `WebClient`. Kiểm tra dependency tree và application type; không suy ra “đang chạy WebFlux” chỉ vì code có `Mono` hay dependency WebFlux.

## 7. Ví dụ chạy được: cùng static files cho hai ứng dụng riêng

Tạo **hai thư mục project độc lập**: `mvc-static-demo` và `webflux-static-demo`. Mỗi project có một `pom.xml` với đúng **một** web starter (MVC hoặc WebFlux), dùng JDK 17+, Maven và Spring Boot 3.5.0. Các file HTML/CSS/JS giống nhau; Java main và controller cũng gần như giống nhau. Không cần database, không cần Thymeleaf.

Cây thư mục cho **mỗi** project:

~~~text
<project>/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/demo/
   │  ├─ DemoApplication.java
   │  └─ PingController.java
   └─ resources/static/
      ├─ index.html
      ├─ css/site.css
      └─ js/site.js
~~~

### 7.1. `pom.xml` của project MVC

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>mvc-static-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
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

### 7.2. `pom.xml` của project WebFlux

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>webflux-static-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
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

Dùng `pom.xml` riêng đúng với project; **không** gộp hai dependency chỉ để thử ví dụ. Với các bản Spring Boot mới hơn, cần kiểm tra Java yêu cầu và thay phiên bản parent cùng các dependency tương ứng.

### 7.3. File Java main chung

Đặt vào **cả hai project** tại `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.4. Controller thử API — chọn một theo project

Dùng file **`PingController.java`** sau trong **project MVC**:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public PingResponse ping() {
        return new PingResponse("pong");
    }

    public record PingResponse(String message) {}
}
~~~

Dùng file **`PingController.java`** sau trong **project WebFlux**:

~~~java
package com.example.demo;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public Mono<PingResponse> ping() {
        return Mono.just(new PingResponse("pong"));
    }

    public record PingResponse(String message) {}
}
~~~

Hai controller có mục đích cho thấy **URL `/api/ping` do ứng dụng xử lý**, còn CSS/JS/HTML được resource handler phục vụ. Không cần controller kiểu `@GetMapping("/css/site.css")`.

### 7.5. Ba file static chung

**`src/main/resources/static/index.html`:**

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spring static resources</title>
  <link rel="stylesheet" href="./css/site.css">
  <script defer src="./js/site.js"></script>
</head>
<body>
  <main>
    <h1>Static resources hoạt động</h1>
    <p id="status">Đang gọi /api/ping...</p>
  </main>
</body>
</html>
~~~

**`src/main/resources/static/css/site.css`:**

~~~css
body {
  font-family: system-ui, sans-serif;
  margin: 2rem;
  line-height: 1.5;
}
h1 {
  color: #245c8a;
}
~~~

**`src/main/resources/static/js/site.js`:**

~~~javascript
document.addEventListener("DOMContentLoaded", async () => {
  const status = document.querySelector("#status");
  try {
    const response = await fetch("./api/ping");
    if (!response.ok) {
      throw new Error("HTTP " + response.status);
    }
    const data = await response.json();
    status.textContent = "API trả về: " + data.message;
  } catch (error) {
    status.textContent = "Không gọi được API: " + error.message;
  }
});
~~~

Cách viết URL tương đối cho CSS, JS và API trong ví dụ dựa trên **`index.html` ở root hoặc một base path nhất quán**. Nếu bạn chuyển index vào một route con sâu hơn, thiết kế lại relative URL cho phù hợp; với proxy prefix, kiểm tra bằng Network tab của browser.

### 7.6. Chạy và kiểm tra

Tại thư mục **một** trong hai project:

~~~bash
java -version
mvn spring-boot:run
~~~

Chờ ứng dụng mở cổng mặc định **8080** (nếu không có cấu hình khác). Mở browser `http://localhost:8080/`: trang có tiêu đề “Static resources hoạt động”, được tô CSS và JavaScript sẽ cập nhật thành **“API trả về: pong”** khi request API thành công.

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/index.html
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/js/site.js
curl -i http://localhost:8080/api/ping
curl -i http://localhost:8080/not-exists.css
~~~

Kỳ vọng có thể xác minh:
- `/index.html`: **200 OK**, body bắt đầu bằng `<!doctype html>`;
- `/css/site.css`: **200 OK**, `Content-Type` phù hợp CSS;
- `/js/site.js`: **200 OK**, `Content-Type` phù hợp JavaScript;
- `/api/ping`: **200 OK** và JSON body chính xác **`{"message":"pong"}`**;
- `/not-exists.css`: **404 Not Found** trong cấu hình mặc định.

Trên môi trường thực tế, các header bổ sung (Date, cache, server, transfer encoding) và định dạng body lỗi 404 có thể thay đổi theo container, Boot config và bộ lọc bảo mật. **Không** khẳng định byte-for-byte toàn bộ HTTP response nếu chưa chạy stack cụ thể.

Để kiểm tra file có được đóng gói vào JAR hay không:

~~~bash
mvn -q clean package
jar tf target/mvc-static-demo-0.0.1-SNAPSHOT.jar
~~~

Trong **project WebFlux**, đổi tên JAR thành `webflux-static-demo-0.0.1-SNAPSHOT.jar`. Tìm các entry `BOOT-INF/classes/static/index.html`, `.../css/site.css`, `.../js/site.js`. Nếu không có, vấn đề nằm ở bước resource packaging trước khi bàn về handler mappings.

## 8. Cấu hình ví dụ: thay URL prefix, thay nơi tìm tài nguyên

**Case A — chỉ thay URL prefix, giữ file ở `static`:**

`application.properties` trong project MVC:

~~~properties
spring.mvc.static-path-pattern=/assets/**
~~~

Tương đương về mục tiêu trong project WebFlux:

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

Khi đó file `static/css/site.css` có URL `/assets/css/site.css`. Vì HTML cũng là static, đường truy cập trực tiếp hợp lý để thử là `/assets/index.html`; không mặc định suy luận rằng URL root `/` tiếp tục hành xử y hệt sau khi đổi pattern. Với `index.html` ở `/assets/index.html`, liên kết tương đối `./css/site.css` sẽ đúng `/assets/css/site.css`. Trong ví dụ JavaScript, `./api/ping` lúc này sẽ thành `/assets/api/ping` (**sai**); muốn gọi API `/api/ping` hãy cập nhật cách dựng API URL cho route đang dùng. Phân biệt **static URL prefix** với **API endpoint path** là điều quan trọng.

**Case B — thay nơi lưu file, giữ URL mặc định:**

~~~properties
spring.web.resources.static-locations=classpath:/frontend/
~~~

Đặt file `src/main/resources/frontend/css/site.css` và gọi `/css/site.css`. Location mới **thay thế** danh sách mặc định; file `src/main/resources/static/css/site.css` không còn được dò ở location mặc định đó nữa.

**Case C — thêm mapping riêng thay vì thay toàn bộ:**

Giữ file static mặc định và thêm file `src/main/resources/custom-assets/manual.pdf`. Sử dụng class `ExtraMvcAssets` (MVC) hoặc `ExtraFluxAssets` (WebFlux) ở phần 5–6 để có URL `/extra/manual.pdf`; không cần đổi global `spring.web.resources.static-locations`.

**Case D — tắt mappings static do Spring Boot cung cấp (khi thực sự cần):**

~~~properties
spring.web.resources.add-mappings=false
~~~

Sau khi tắt, các file chỉ có sẵn trong `static` sẽ không được phục vụ theo mapping Boot mặc định. Nếu tự khai báo resource handlers/router khác, hành vi do cấu hình riêng quyết định. Cần đặc biệt kiểm tra điều này trong API-only app hoặc ứng dụng được nâng cấp từ cấu hình MVC/WebFlux tự quản lý.

## 9. Caching, conditional GET, resource chain và cache busting

Static content thường được đọc rất nhiều lần. Một CDN hoặc browser cache giúp giảm tải app và latency, nhưng cache sai có thể làm người dùng nhận CSS/JS cũ. Cần phân biệt **HTTP cache** với **resource chain nội bộ của Spring**.

### 9.1. Cache-Control và Last-Modified

Ví dụ cấu hình cache chung cho Boot resource handler:

~~~properties
spring.web.resources.cache.period=3600
spring.web.resources.cache.use-last-modified=true
~~~

`3600` ở đây là **giây**, tương đương 1 giờ. Với cấu hình phù hợp, response có thể kèm `Cache-Control: max-age=3600`. Nếu resource có thời điểm chỉnh sửa xác định, handler có thể gửi `Last-Modified`. Client dùng conditional request `If-Modified-Since`; khi tài nguyên chưa thay đổi, server có thể trả **304 Not Modified** mà không gửi lại body.

Ví dụ xem headers:

~~~bash
curl -I http://localhost:8080/css/site.css
~~~

Muốn thử conditional GET một cách tin cậy, lấy đúng giá trị `Last-Modified` mà server trả, rồi gửi lại ở `If-Modified-Since`. Nếu lần sau nhận 304, browser/proxy có thể dùng bản cache đã lưu. **Không giả định mọi response đều có ETag**: Spring có thể phục vụ Last-Modified mà không tự sinh ETag; ETag cần cấu hình/handler/filter phù hợp.

Một số bản ứng dụng có reverse proxy hoặc CDN nên headers cuối cùng ở client có thể khác những gì resource handler đặt. Kiểm tra bằng HTTP client thực tế, không chỉ đọc `application.properties`.

### 9.2. Cache-busting: đổi URL khi nội dung thay đổi

Giả sử HTML trỏ `/css/site.css` và browser cache 1 năm. Sau lần triển khai CSS mới, URL không đổi, browser có thể tiếp tục dùng file cũ. **Cache busting** giải quyết bằng cách đổi URL khi nội dung đổi:

~~~text
/css/site.css
        ↓ phiên bản theo nội dung
/css/site-<content-hash>.css
~~~

Spring Boot hỗ trợ resource chain/version strategy:

~~~properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
~~~

Đây là **cấu hình chiến lược**. Framework có thể phục vụ versioned path dựa trên nội dung khi liên kết/versioned URL được tạo đúng. **Nó không tự sửa mọi chuỗi đường dẫn viết cứng trong `index.html` tĩnh**. Với Spring MVC + Thymeleaf/FreeMarker, Spring Boot có tích hợp rewrite URL trong view templates; với JSP hoặc stack khác phải cấu hình hoặc dùng `ResourceUrlProvider` tương ứng.

Trong **WebFlux**, không nên giả định một HTML tĩnh sẽ tự viết lại URL qua reactive ResourceResolver chain. Nếu ứng dụng cần filename hash trên frontend, một cách thực dụng là để bundler (Vite/Webpack…) tạo file hashed và sinh `index.html` cùng manifest/URL khớp trong build step.

Với JavaScript module import/dynamic import, chiến lược đổi **tên file** cần được kiểm tra vì module loader có thể tham chiếu đường dẫn nội bộ. Spring hỗ trợ **fixed version strategy** (version trong path) như một lựa chọn. Chọn chiến lược theo loại asset, không áp dụng content hash bừa bãi cho mọi tệp.

**Khuyến nghị cache thực tế:** Với asset có **URL thay đổi mỗi lần nội dung đổi**, có thể đặt cache dài và dùng chỉ thị `immutable` khi phù hợp. Với HTML entrypoint `index.html` giữ URL cố định, nên chọn chính sách **ngắn hoặc revalidate** để browser sớm nhận các URL CSS/JS mới. Nếu đặt cache dài cho toàn bộ `/**`, bao gồm HTML entrypoint, việc triển khai frontend sẽ dễ gặp “HTML cũ, asset mới”.

### 9.3. ResourceResolver và ResourceTransformer làm gì?

Resource chain có thể gồm các bước:
- `PathResourceResolver`: tìm và xác minh resource ở các location được phép;
- `VersionResourceResolver`: tìm/kiểm tra phiên bản trong URL;
- resolver cho file nén có sẵn (khi bật tính năng và resource tương ứng);
- transformer để biến đổi nội dung/link trong một số kịch bản cụ thể.

Pipeline này **không** là nơi chạy business logic động hay xác thực dữ liệu nghiệp vụ. Kích hoạt resource chain không tự đảm bảo gzip/Brotli ở mọi response; việc nén phụ thuộc file đã nén, Accept-Encoding và cấu hình tương thích. Resource handler cũng không tự biến mọi `.svg` hay file upload thành nội dung an toàn.

## 10. WebJars và tài nguyên trong dependency

**WebJar** đóng gói JavaScript/CSS thành JAR với cấu trúc tài nguyên web. Spring Boot có hỗ trợ truy cập mặc định dưới prefix `/webjars/**` khi đúng dependency và bố cục resource. URL thông thường có **phiên bản**:

~~~text
/webjars/<library-name>/<version>/<file-path>
~~~

Một số cơ chế phát hiện phiên bản cho đường dẫn “bỏ version” cần thêm dependency như `webjars-locator-lite`; không giả định mọi WebJar hoặc mọi phiên bản Spring Boot đều tự hỗ trợ versionless URL.

**Lựa chọn:** WebJars hữu ích khi frontend asset là dependency của Java app. Với frontend lớn được build bằng Vite/Webpack, đặt output build vào `static` hoặc phục vụ ở CDN thường đơn giản hơn. Đừng copy source frontend hoặc thư mục `node_modules` nguyên khối vào classpath để public tất cả file vô tình.

## 11. Bảo mật và ranh giới giữa tài nguyên public/private

Static handler theo thiết kế phục vụ **file từ danh sách location do server tin tưởng**; không dùng nó như API đọc file tùy ý từ đường dẫn client cung cấp.

- Chỉ đặt nội dung **public** trong static locations. Tên file chứa token, cấu hình credentials, source map chứa bí mật, file `.env` và bản dump DB đều không được public.
- Với Spring Security, có thể cần **cho phép truy cập GET** đối với static assets như `/css/**`, `/js/**`, `/images/**`, favicon, `/`/`index.html`. Cú pháp MVC `authorizeHttpRequests().requestMatchers(...).permitAll()` và WebFlux `authorizeExchange().pathMatchers(...).permitAll()` là hai API **khác nhau**. Giới hạn rule sát các path public; không mở toàn bộ `/**` chỉ để chữa lỗi CSS 403.
- `permitAll` là quyết định authorization, khác với bỏ qua hoàn toàn security filter chain. Khi bỏ filter, bạn cũng có thể bỏ các header bảo mật/điều kiện khác mà chain đặt.
- Không ánh xạ toàn bộ thư mục filesystem ngoài ứng dụng bằng `file:/` chỉ vì tiện phát triển. Nếu thực sự cần external static files, giới hạn thư mục phục vụ, quyền truy cập và cách deploy; tuyệt đối không cho user chỉ định tùy ý đường dẫn hệ thống.
- Các tệp **upload bởi người dùng** cần quy trình scan/validate, phân quyền, tên lưu riêng, chính sách Content-Type/Content-Disposition và có thể dùng object storage/CDN. Không tự coi chúng là static public.
- Dữ liệu HTML/SVG do bên thứ ba kiểm soát có thể mang nội dung hoạt động trong browser. Kiểm tra chính sách CSP, X-Content-Type-Options và cách nhúng; “file tĩnh” không đồng nghĩa “vô hại”.
- Nếu trang SPA bị chặn login, việc trả `index.html` cho mọi 404 không sửa được lỗi authentication; cần đặt route/security đúng, giữ API trả lỗi rõ ràng.

## 12. SPA, fallback route và lỗi “trang trắng”

Một Single Page Application (React/Vue/Angular…) thường có một `index.html`, nhiều hashed assets và JavaScript router. Browser truy cập trực tiếp `/orders/42` sẽ gửi **GET /orders/42** đến server; nếu server chỉ có `/index.html`, static handler thường không tự forward mọi URL về index.

Muốn deep-link SPA hoạt động, cần **fallback có điều kiện** cho route frontend, ví dụ dưới prefix `/app/**`. Tùy stack, có thể dùng MVC view controller/forward, reactive router/filter hoặc cấu hình reverse proxy. Thiết kế fallback cần:
1. Không chặn `/api/**`, `/actuator/**`, `/webjars/**`.
2. Không biến request `/assets/missing.js` hoặc `/css/missing.css` thành **HTTP 200 với HTML**, vì browser sẽ báo lỗi MIME và trang trắng.
3. Chỉ fallback cho route của frontend theo phương thức HTTP phù hợp, thường GET/HEAD, và xem xét Accept header hoặc quy tắc route.
4. Kiểm tra location asset và cache, nhất là asset hashed mới sau deploy.

Đây là một phần **bổ sung** cho static resource handling, không phải cơ chế mặc định của `ResourceHttpRequestHandler` hay `ResourceWebHandler`.

## 13. Các lỗi phổ biến và cách xác minh

| Triệu chứng | Khả năng cao | Cách kiểm tra / sửa |
| --- | --- | --- |
| `GET /static/css/site.css` → 404 | Thêm “static” sai vào URL | Dùng `/css/site.css` với mapping `/**` |
| `GET /css/site.css` → 404 sau đổi prefix | `spring.mvc.static-path-pattern` hoặc `spring.webflux.static-path-pattern` thay đổi | Dùng `/assets/css/site.css` hoặc trả về pattern phù hợp |
| CSS/JS 404 khi chạy JAR, nhưng IDE chạy được | File không nằm trong classpath đã đóng gói | `jar tf target/*.jar` và kiểm tra `BOOT-INF/classes/static/` |
| File ở `src/main/webapp` trong executable JAR | Thư mục không được xử lý như static classpath | Chuyển sang `src/main/resources/static` |
| CSS/JS trả **403** | Rule Spring Security không cho phép | Kiểm tra đúng matcher, prefix, method và filter chain |
| CSS/JS trả **200 nhưng Content-Type: text/html** | SPA fallback trả index thay file thiếu | Loại asset/API paths khỏi fallback; kiểm tra file trong JAR |
| Browser báo sai MIME type, không chạy module | URL JS trả HTML/lỗi; MIME sai | Kiểm tra Network tab, response headers và actual body |
| HTML có nhưng không tải CSS/JS khi deploy dưới `/shop` | Link tuyệt đối trỏ sai base path | Dùng URL theo context path, kiểm tra proxy prefix |
| Đặt file trong `templates` nhưng `/file.html` 404 | Template không là static resource trực tiếp | Tạo view controller hoặc đưa file sang `static` nếu đúng yêu cầu |
| Custom `static-locations` làm các file cũ biến mất | Property đã **thay** danh sách mặc định | Khai báo nhiều locations rõ ràng |
| MVC custom config làm mất mapping mặc định | Có `@EnableWebMvc` hoặc auto-config bị thay | Bỏ `@EnableWebMvc` nếu muốn Boot auto-config |
| Có dependency WebFlux nhưng custom WebFlux handler không hoạt động | App thực tế vẫn chạy MVC vì có cả web starter | Kiểm tra pom, application type và runtime logs |
| CSS cũ sau deploy | Browser/CDN cache asset URL không đổi | Dùng hashed URLs, kiểm soát TTL và cache HTML |
| “No static resource ...” trên API URL | MVC `/**` static mapping nhận đường dẫn không có controller | Kiểm tra URL/API mapping; cân nhắc static path pattern riêng |
| `GET /` không hiển thị index | Sai location, thiếu index hoặc có route riêng ưu tiên; pattern đã đổi | Kiểm tra `/index.html`, startup config và route collision |
| Đường dẫn ảnh nhúng CSS bị 404 | `url(...)` trong CSS là đường dẫn tương đối với **vị trí file CSS** | Tính URL từ `/css/site.css`, ví dụ `../images/logo.svg` |
| Tệp có ở ổ đĩa nhưng 404 | Đĩa local khác với classpath trong Docker/JAR | Kiểm tra resource nằm trong image/JAR hay đã map external location |
| Tài nguyên không hiện qua CDN/proxy | Rewrite path, cache hoặc upstream route sai | So sánh request trực tiếp app và qua proxy, kiểm tra status/headers |

### Quy trình debug gọn nhưng đủ bằng chứng

1. **Tách URL khỏi file path:** ghi chính xác URL browser gọi và file thực sự tồn tại trong package.
2. **Kiểm tra HTTP status + Content-Type + body:** dùng `curl -i` và Network tab; tránh đoán 404/403.
3. **Kiểm tra stack:** MVC hay WebFlux thực tế? Có cả starter không? Custom config nào đang chạy?
4. **Kiểm tra properties hiệu lực:** static path pattern, static locations, add-mappings, context/base path, security rules.
5. **Kiểm tra artifact:** tìm path dưới `BOOT-INF/classes` hoặc dependency JAR liên quan.
6. **Kiểm tra cache/CDN:** thử URL mới, request trực tiếp instance, kiểm tra Last-Modified/Cache-Control và stale HTML.
7. **Kiểm tra controller/router/SPA fallback:** có route bắt mất path resource hoặc biến 404 thành HTML 200 không?

## 14. Hiệu năng và triển khai thực tế

- Dùng response cache và CDN khi có lượng truy cập asset lớn; Spring Boot resource handler thuận tiện cho ứng dụng nhỏ hoặc giao diện tích hợp trong cùng JAR, còn CDN/object storage phù hợp với hệ thống frontend có nhu cầu scale độc lập.
- Không phát lại file tĩnh bằng controller tự đọc `InputStream` nếu không có lý do cụ thể. Resource handlers đã hỗ trợ truyền response, MIME types, caching và nhiều cơ chế HTTP tiêu chuẩn.
- Có thể bật nén ở container/proxy và dùng tài nguyên đã nén phù hợp; kiểm tra thực tế `Content-Encoding`, `Vary: Accept-Encoding` và các rule cache.
- Build frontend cần đảm bảo các asset references trong `index.html` trỏ đến file đúng phiên bản sau deploy. Nếu asset cache lâu, URL phải đổi theo nội dung.
- Không bật cả MVC và WebFlux chỉ vì muốn “phục vụ static nhanh hơn”: hiệu quả thường bị chi phối bởi CDN/cache, kích thước file, băng thông, TLS và cache hit, không phải việc tạo controller reactive.
- Thay đổi base-path hoặc custom URL prefix có ảnh hưởng đến service worker scope, CSP, CORS, frontend router và client cache. Kiểm tra tất cả khi đổi route.
- Khi có Spring Security hoặc reverse proxy, kiểm tra asset trên đường đi **đúng như browser thực tế**, không chỉ bằng unit test trực tiếp resource handler.

## 15. Câu hỏi tự kiểm tra

1. Đặt `src/main/resources/static/css/site.css` trong project MVC mặc định, URL nào truy cập đúng: `/css/site.css` hay `/static/css/site.css`? Vì sao?
2. File `src/main/resources/templates/dashboard.html` có tự phục vụ tại `/dashboard.html` không? Khi nào dùng template engine?
3. Điền hai handler tương ứng với MVC và WebFlux; vì sao khác import package `ResourceHandlerRegistry`?
4. Với `spring.web.resources.static-locations=classpath:/frontend/`, một file chỉ ở `classpath:/static/` có còn được dò theo danh sách mặc định không?
5. Với `spring.webflux.static-path-pattern=/assets/**` và file `static/js/site.js`, URL resource là gì?
6. Nếu có controller `@GetMapping("/api/ping")` trong MVC mặc định, vì sao mapping static `/**` không nhất thiết lấy mất route này?
7. Browser nhận `200 text/html` cho request `/js/app.js`. Vì sao file JavaScript vẫn không chạy?
8. Tại sao không nên cache `index.html` không versioned với `max-age=31536000` trong SPA có JS/CSS hashed?
9. Bật content versioning có tự sửa mọi hard-coded path trong một file HTML static không?
10. Một ứng dụng deploy ở `/shop` nhưng HTML trỏ `/css/site.css`. URL nào browser thật sự gọi và cách thiết kế lại link?
11. Với Spring Boot executable JAR, vì sao `src/main/webapp` không phải nơi nên đặt static assets?
12. Khi `/css/site.css` trả 403, bước kiểm tra có ý nghĩa hơn là tăng `spring.web.resources.cache.period`?

**Đáp án trọng tâm:** (1) `/css/site.css` vì `static` là resource location; (2) không, templates cần render; (3) MVC `ResourceHttpRequestHandler`, WebFlux `ResourceWebHandler`, mỗi stack có config package riêng; (4) không trong danh sách đã thay, trừ trường hợp location khác được cấu hình riêng; (5) `/assets/js/site.js`; (6) handler mappings phân biệt và có ưu tiên; (7) SPA fallback/response sai MIME; (8) HTML cũ không cập nhật hashed asset URLs; (9) không; (10) thường gọi root domain `/css/site.css` sai prefix, cần context-aware link; (11) file không được đóng gói theo convention executable JAR; (12) kiểm tra Spring Security authorization/filter chain.

## 16. Tài liệu chính thức

Các tài liệu sau giúp đối chiếu chính xác khi cập nhật Spring Boot/Spring Framework. Các ví dụ và property trong bài đặt trong bối cảnh **Spring Boot 3.5.x**; khi nâng major version, kiểm tra API và dependency có thay đổi hay không.

- Spring Boot 3.5, Servlet static content, cache busting và welcome page: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5, WebFlux static content và URL pattern: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5, danh mục application properties (`spring.web.resources.*`): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework, MVC static resources: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Framework, WebFlux static resources: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework, HTTP caching: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html

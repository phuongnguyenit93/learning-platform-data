# WebJars và tài nguyên đóng gói trong thư viện — Spring Boot web runtime

## 1. Hiểu đúng bản chất

Trong ứng dụng Spring Boot, ảnh, CSS, JavaScript, font, icon và các tệp tĩnh không nhất thiết phải nằm ngay trong thư mục source của **ứng dụng chính**. Chúng cũng có thể nằm trong **JAR dependency** trên runtime classpath. Spring MVC và Spring WebFlux có cơ chế tìm tài nguyên từ classpath và trả nội dung đó qua HTTP, nên một thư viện giao diện có thể mang theo asset dùng chung cho nhiều ứng dụng.

**WebJars** là quy ước đóng gói các thư viện web phía trình duyệt (ví dụ jQuery, Bootstrap) thành artifact Maven/Gradle JAR. Điểm phân biệt chính của WebJar là cấu trúc đường dẫn theo tên thư viện và phiên bản trong `META-INF/resources/webjars/`. Spring Boot đã cung cấp ánh xạ HTTP mặc định cho loại tài nguyên này.

Cần phân biệt:

- **Thư viện Java chứa tài nguyên:** bất kỳ JAR dependency nào chứa file trong các vị trí tĩnh được Spring Boot cấu hình đọc, tiêu biểu `META-INF/resources/`; không bắt buộc là WebJar.
- **WebJar:** JAR được đóng gói theo cấu trúc chuẩn cho một thư viện frontend, thường có URL dạng `/webjars/{ten-thu-vien}/{phien-ban}/{tep}`.
- **Static resource handler:** thành phần của Spring MVC/WebFlux nhận URL, tìm `Resource` trong classpath hoặc vị trí đã cấu hình, trả bytes và header HTTP. Handler này **không phải REST controller**.
- **Embedded server:** Tomcat/Jetty/Reactor Netty nhận kết nối và chuyển request vào Spring web stack; server không tự hiểu quy ước WebJars trừ khi framework/cấu hình có resource mapping phù hợp.

Ví dụ một dependency JAR chứa:

```text
some-ui-library-1.0.0.jar
└── META-INF/
    └── resources/
        └── shared-ui/
            ├── theme.css
            └── logo.svg
```

Với cấu hình Spring Boot mặc định, ứng dụng web có thể phục vụ hai URL:

```text
GET /shared-ui/theme.css
GET /shared-ui/logo.svg
```

Còn một WebJar jQuery phiên bản 3.7.1 thường có cấu trúc:

```text
jquery-3.7.1.jar
└── META-INF/
    └── resources/
        └── webjars/
            └── jquery/
                └── 3.7.1/
                    └── jquery.min.js
```

Và URL tương ứng:

```text
GET /webjars/jquery/3.7.1/jquery.min.js
```

Đường dẫn bắt đầu bằng `/webjars/` ở trên là **URL công khai**, còn `META-INF/resources/webjars/` là **đường dẫn nội bộ của JAR**. Không chèn `META-INF/resources` vào URL trình duyệt.

## 2. Vì sao tài nguyên bên trong dependency JAR được tìm thấy?

Có ba điều kiện thiết yếu:

1. **Dependency tồn tại ở runtime.** Khai báo Maven/Gradle phải đưa JAR vào runtime classpath; dependency chỉ có trong scope `test` sẽ không dùng được khi chạy production.
2. **Tệp nằm đúng đường dẫn bên trong JAR.** `META-INF/resources/` là một vị trí được Boot phục vụ mặc định. Với WebJar, phần trong đường dẫn thường là `META-INF/resources/webjars/{library}/{version}/...`.
3. **Ứng dụng có resource handler cho URL đó.** Khi dùng Spring Boot MVC/WebFlux auto-configuration thông thường, các handler mặc định được tạo; nếu người viết tắt default mapping hoặc thay toàn bộ cấu hình MVC, cần khôi phục mapping thủ công.

Đây là cơ chế classpath. Nó không yêu cầu giải nén dependency bằng tay ra `src/main/resources/static`, không yêu cầu tạo controller trả mảng byte, và không phụ thuộc vào việc lúc chạy còn thư mục source bên ngoài hay không.

### Vị trí static mặc định

Spring Boot hỗ trợ các thư mục resource trên **classpath**:

| Vị trí bên trong classpath | URL ví dụ khi cấu hình mặc định | Thường dùng cho |
| --- | --- | --- |
| `/static/site.css` | `/site.css` | Asset của ứng dụng chính |
| `/public/help.html` | `/help.html` | Trang tĩnh, tài liệu công khai |
| `/resources/banner.svg` | `/banner.svg` | Một vị trí static thay thế |
| `/META-INF/resources/shared-ui/theme.css` | `/shared-ui/theme.css` | Asset được đóng gói trong JAR thư viện |
| `/META-INF/resources/webjars/jquery/3.7.1/jquery.min.js` | `/webjars/jquery/3.7.1/jquery.min.js` | WebJar theo phiên bản |

Các ví dụ trong bảng giả định không đổi `server.servlet.context-path`, web base path, pattern static và resource locations. `/resources` trong bảng là **một thư mục trên classpath**, không phải tiền tố URL bắt buộc.

Trong project Maven/Gradle, `src/main/resources/static` và `src/main/resources/META-INF/resources` được đóng gói vào classpath khi build. Với project JAR kiểu Spring Boot:

- Class của ứng dụng và tài nguyên của ứng dụng thường ở `BOOT-INF/classes/`;
- Dependency JAR thường ở `BOOT-INF/lib/`;
- Spring Boot launcher tạo runtime classpath cho cả hai, nên resource handler vẫn có thể đọc từ JAR lồng trong executable JAR.

`src/main/webapp` là cấu trúc quen thuộc của WAR/Servlet truyền thống, **không phải vị trí được khuyến nghị khi build Spring Boot executable JAR**. Đừng đặt WebJar files hay asset dùng chung ở đây rồi kỳ vọng chúng tự đóng gói trong JAR.

## 3. Cơ chế xử lý một request WebJar tại runtime

Sơ đồ logic:

```text
Browser:
GET /webjars/jquery/3.7.1/jquery.min.js
                  |
           Embedded HTTP server
                  |
        Spring MVC / WebFlux router
                  |
      Resource handler cho /webjars/**
                  |
       Classpath resource resolution
                  |
META-INF/resources/webjars/jquery/3.7.1/jquery.min.js
        bên trong dependency JAR
                  |
    HTTP 200 + Content-Type + cache headers
                  |
                Browser
```

Với **Spring MVC**, Spring Boot cấu hình `ResourceHttpRequestHandler` qua hạ tầng `ResourceHandlerRegistry`/`HandlerMapping`. Với **Spring WebFlux**, lớp phục vụ tệp tương ứng là `ResourceWebHandler`. Cả hai đều có thể tìm static resources trong classpath và hỗ trợ WebJars.

Các lớp handler có thể xử lý nội dung theo đường dẫn tĩnh, đoán content type, hỗ trợ `Last-Modified`/conditional requests và cache headers theo cấu hình. Đường dẫn có phiên bản nằm trong URL giúp cache lâu hơn khi triển khai đúng chính sách; Spring không tự đảm bảo “immutable” cho tất cả HTTP response nếu chưa cấu hình cache.

**Quan trọng:** JavaScript được server trả như **bytes** để trình duyệt tự chạy. Spring Boot không thực thi thư viện JavaScript trên JVM chỉ vì có WebJar trên classpath.

### MVC và WebFlux khác nhau ở đâu?

| Khía cạnh | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Resource handler | `ResourceHttpRequestHandler` | `ResourceWebHandler` |
| Pattern thông thường | `/**` cho static resource | `/**` cho static resource |
| WebJars mặc định | `/webjars/**` | `/webjars/**` |
| Property đổi pattern WebJars | `spring.mvc.webjars-path-pattern` | `spring.webflux.webjars-path-pattern` |
| Property đổi static pattern | `spring.mvc.static-path-pattern` | `spring.webflux.static-path-pattern` |
| Location mặc định | `classpath:/static/`, `/public/`, `/resources/`, `/META-INF/resources/` và root servlet context tương ứng | Các vị trí classpath tương tự, nhưng không phụ thuộc vào Servlet root |
| Cách tùy biến | `WebMvcConfigurer#addResourceHandlers` | `WebFluxConfigurer#addResourceHandlers` |

Không suy luận rằng WebFlux chỉ phục vụ API JSON nên không dùng được WebJars: cả hai stack đều có static resource handler. Ngược lại, không cần lựa chọn WebFlux chỉ vì app tải nhiều file JavaScript: đó là lựa chọn về mô hình web processing, không phải quy cách đóng gói frontend assets.

## 4. Hai kiểu URL của WebJars: có phiên bản và không ghi phiên bản

### 4.1. URL có phiên bản — ưu tiên mặc định

Giả sử dependency là jQuery 3.7.1:

```html
<script src="/webjars/jquery/3.7.1/jquery.min.js"></script>
```

Đường dẫn trùng với cấu trúc bên trong WebJar. Spring Boot có thể phục vụ nó theo mapping mặc định **mà không cần thêm WebJars locator**.

Ưu điểm: rõ ràng artifact nào đang chạy, ít phải dò tìm, phù hợp caching theo phiên bản và dễ kiểm tra nguyên nhân 404. Nhược điểm: muốn nâng WebJar, phải cập nhật cả version trong URL (hoặc dùng hệ thống generate URL phù hợp).

### 4.2. URL không ghi phiên bản — cần locator hỗ trợ

Dạng URL:

```html
<script src="/webjars/jquery/jquery.min.js"></script>
```

Dạng này **không tự hoạt động với mọi project chỉ vì đã thêm `jquery` vào Maven**. Với Spring Framework hiện đại, cần có `org.webjars:webjars-locator-lite` trên classpath để Spring đăng ký `LiteWebJarsResourceResolver` phục vụ/resolve phiên bản. Với Boot 3.5.16, có thể bổ sung dependency:

```xml
<dependency>
    <groupId>org.webjars</groupId>
    <artifactId>webjars-locator-lite</artifactId>
    <version>1.1.4</version>
</dependency>
```

Đây là **đoạn dependency bổ sung trong `<dependencies>`**, không phải POM độc lập. Phiên bản locator ở đây là một ví dụ artifact đã phát hành; khi vận hành phải kiểm tra tương thích với phiên bản Spring đang sử dụng.

Khi locator đang hoạt động, yêu cầu không ghi phiên bản có thể được ánh xạ tới file nằm trong WebJar có version. Đừng nhầm “trình duyệt tự hiểu version” với “resource resolver trên server tìm version”. Việc dùng **URL có phiên bản** vẫn thường đơn giản hơn.

**Lưu ý nâng cấp:** tài liệu rất cũ có thể chỉ tới `webjars-locator-core` hoặc `webjars-locator`. Hãy đối chiếu Spring Framework/Boot phiên bản đang dùng; trong dòng tài liệu hiện đại, cơ chế được chỉ rõ là `webjars-locator-lite`.

## 5. Ví dụ chạy được: Spring Boot MVC tải jQuery từ WebJar

Ví dụ minh họa với **Java 17+**, **Maven** và **Spring Boot 3.5.16** để API và starter đồng nhất. Phiên bản jQuery 3.7.1 được ghim cho phép đối chiếu đường dẫn; đây không có nghĩa là phiên bản mới nhất phù hợp mọi dự án. Với hệ thống mới, hãy chọn phiên bản Spring Boot được hỗ trợ và cập nhật dependencies theo chính sách bảo mật.

### 5.1. Cấu trúc project

```text
webjars-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/webjarsdemo/
        │       └── WebjarsDemoApplication.java
        └── resources/
            └── static/
                ├── index.html
                └── css/
                    └── site.css
```

### 5.2. `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webjars-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.webjars</groupId>
            <artifactId>jquery</artifactId>
            <version>3.7.1</version>
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
```

`spring-boot-starter-web` đưa vào Spring MVC và embedded Tomcat mặc định; `org.webjars:jquery:3.7.1` đưa các file JS của jQuery vào **dependency JAR** trên runtime classpath. Không cần `@EnableWebMvc` hoặc thêm resource handler cho URL phiên bản.

### 5.3. Java main chạy được

Tệp `src/main/java/com/example/webjarsdemo/WebjarsDemoApplication.java`:

```java
package com.example.webjarsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebjarsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebjarsDemoApplication.class, args);
    }
}
```

Không cần viết `@RestController` để phục vụ `/index.html`, CSS hay WebJar. Đây là điểm quan trọng của bài học: **static resources được ánh xạ bằng web infrastructure**, không phải bằng Java controller tùy chỉnh.

### 5.4. HTML và CSS

Tệp `src/main/resources/static/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WebJars demo</title>
  <link rel="stylesheet" href="/css/site.css">
</head>
<body>
  <h1>Tài nguyên tĩnh từ classpath</h1>
  <p id="webjar-status">Đang kiểm tra thư viện...</p>

  <script src="/webjars/jquery/3.7.1/jquery.min.js"></script>
  <script>
    const statusElement = document.getElementById("webjar-status");
    statusElement.textContent = window.jQuery
        ? "jQuery " + window.jQuery.fn.jquery + " đã tải"
        : "Không tải được jQuery";
  </script>
</body>
</html>
```

Tệp `src/main/resources/static/css/site.css`:

```css
body {
  font-family: system-ui, sans-serif;
  max-width: 42rem;
  margin: 3rem auto;
  padding: 0 1rem;
}
h1 { color: #214d87; }
```

Đây là ba tài nguyên khác nguồn gốc: HTML và CSS nằm trong ứng dụng, còn jQuery JS đến từ dependency `org.webjars:jquery`. Spring Boot phục vụ tất cả qua HTTP.

### 5.5. Build, chạy và kết quả

Tại thư mục chứa `pom.xml`, chạy với JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Mở `http://localhost:8080/`. Sau khi script tải xong, nội dung đoạn `<p>` sẽ là:

```text
jQuery 3.7.1 đã tải
```

Kiểm tra trực tiếp:

```bash
curl -I http://localhost:8080/
curl -I http://localhost:8080/css/site.css
curl -I http://localhost:8080/webjars/jquery/3.7.1/jquery.min.js
```

Trong demo mặc định, các URL này nên trả **HTTP 200**. Header cụ thể như `Cache-Control`, `ETag`, `Last-Modified` và `Content-Length` thay đổi theo cấu hình và server, nên không đưa ra bộ header cố định.

Build executable JAR:

```bash
mvn clean package
java -jar target/webjars-demo-1.0.0.jar
```

Không cần copy thư viện jQuery ra thư mục frontend bên ngoài khi chạy JAR. Trong executable JAR, dependency thường được giữ dưới `BOOT-INF/lib/jquery-3.7.1.jar` và Spring Boot launcher tạo classpath phù hợp để Spring tìm tài nguyên.

Trên Windows PowerShell, dùng `curl.exe` nếu alias `curl` không hoạt động như mong muốn. Nếu cổng 8080 bận, chạy với tham số `--server.port=8081` sau tên JAR và thay cổng trong URL kiểm tra.

### 5.6. Điều gì xảy ra khi không có dependency?

Nếu bỏ `org.webjars:jquery` nhưng HTML vẫn trỏ tới `/webjars/jquery/3.7.1/jquery.min.js`, URL WebJar tương ứng thường trả **404** (trong demo chưa bật Spring Security). File `index.html` và `site.css` vẫn có thể chạy, vì chúng thuộc resource của ứng dụng chính.

Nếu thêm lại dependency nhưng dùng sai tên file hoặc sai version trong URL, cũng có thể 404. Đây là cách kiểm tra nhanh sự khác biệt giữa **dependency đã được khai báo** và **đường dẫn thực tế trong dependency**.

## 6. Đóng gói asset dùng chung trong JAR thư viện của chính bạn

WebJar phù hợp thư viện frontend bên thứ ba. Nhưng khi nhiều ứng dụng nội bộ chia sẻ logo, CSS design system, icon, file JS nhỏ hoặc bản CSS theo thương hiệu, bạn có thể tự tạo một **JAR chứa assets** theo quy ước `META-INF/resources`. JAR này không cần chứa Java class.

### 6.1. Tạo project thư viện `brand-assets`

Bên cạnh `webjars-demo`, tạo thư mục:

```text
brand-assets/
├── pom.xml
└── src/
    └── main/
        └── resources/
            └── META-INF/
                └── resources/
                    └── brand-assets/
                        └── theme.css
```

Tệp `brand-assets/pom.xml` đầy đủ:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>brand-assets</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

Tệp `brand-assets/src/main/resources/META-INF/resources/brand-assets/theme.css`:

```css
.brand-highlight {
  background: #f2f6fd;
  border-left: 4px solid #214d87;
  border-radius: 0.25rem;
  padding: 1rem;
}
```

Đứng trong `brand-assets`:

```bash
mvn clean install
```

Lệnh đóng gói JAR rồi cài `com.example:brand-assets:1.0.0` vào local Maven repository. Vì đây là JAR chỉ có resources, không cần tạo lớp Java. Kiểm tra:

```bash
jar tf target/brand-assets-1.0.0.jar
```

Trong danh sách phải có đường dẫn **chính xác**:

```text
META-INF/resources/brand-assets/theme.css
```

### 6.2. Dùng thư viện trong ứng dụng Spring Boot

Trong `webjars-demo/pom.xml` ở mục 5, thêm dependency sau vào **bên trong `<dependencies>`**:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>brand-assets</artifactId>
    <version>1.0.0</version>
</dependency>
```

Đây là đoạn thêm vào POM **đã có**, không phải một POM thay thế. Sau đó trong `src/main/resources/static/index.html` của ứng dụng, thêm liên kết CSS vào `<head>`:

```html
<link rel="stylesheet" href="/brand-assets/theme.css">
```

Và có thể sửa `<h1>` đang có thành:

```html
<h1 class="brand-highlight">Tài nguyên tĩnh từ classpath</h1>
```

Các thay đổi HTML trên là **đoạn bổ sung/thay thế cho file ở mục 5**, không phải HTML hoàn chỉnh thứ hai.

Khởi động lại từ thư mục `webjars-demo`:

```bash
mvn clean package
java -jar target/webjars-demo-1.0.0.jar
```

Gọi:

```bash
curl -I http://localhost:8080/brand-assets/theme.css
```

Khi dependency đã có trong runtime và không tùy biến static mapping, URL được mong đợi trả **200**. File CSS nằm trong JAR `brand-assets-1.0.0.jar`, không nằm trong `src/main/resources/static` của ứng dụng chính.

Kiểm tra executable JAR:

```bash
jar tf target/webjars-demo-1.0.0.jar
```

Danh sách thường có `BOOT-INF/lib/brand-assets-1.0.0.jar` và `BOOT-INF/lib/jquery-3.7.1.jar`. Lệnh `jar tf` trên outer JAR chỉ hiển thị **tên nested JAR**; để xem bên trong nested dependency, kiểm tra JAR thư viện riêng như bước trước. Không kết luận thư viện thiếu chỉ vì không thấy `META-INF/resources/brand-assets/theme.css` ở cấp đầu tiên của executable JAR.

### 6.3. Khi nào cần tự tạo WebJar thay vì JAR assets thường?

Nếu bạn cung cấp **một thư viện JS/CSS có tên và phiên bản độc lập**, muốn người dùng tham chiếu chuẩn `/webjars/{library}/{version}/...` và dễ nâng cấp cùng dependency, hãy đóng gói theo cấu trúc WebJars. Nếu chỉ cần tài nguyên nội bộ dùng chung với prefix riêng, `META-INF/resources/brand-assets/` đã đủ.

Không cần biến mọi file CSS nội bộ thành WebJar. Chọn cấu trúc sao cho consumer dự đoán được URL và package không va chạm namespace với thư viện khác.

## 7. Đổi đường dẫn HTTP hoặc vị trí tài nguyên

### 7.1. Các cấu hình Spring Boot liên quan

Ví dụ khi **cần** sửa pattern (không cần thêm cấu hình cho ví dụ ở trên):

```properties
# Spring MVC: đổi URL cho static resources thông thường
spring.mvc.static-path-pattern=/assets/**

# Spring MVC: đổi riêng URL của WebJars
spring.mvc.webjars-path-pattern=/vendor/**

# Cấu hình tương ứng trên WebFlux:
# spring.webflux.static-path-pattern=/assets/**
# spring.webflux.webjars-path-pattern=/vendor/**
```

Đây là **ví dụ tùy chọn**, không áp dụng đồng thời với đường dẫn demo ở mục 5–6 nếu chưa đổi URL trong HTML:

- `spring.mvc.static-path-pattern=/assets/**` có thể biến `/css/site.css` thành `/assets/css/site.css` theo mapping mới.
- `spring.mvc.webjars-path-pattern=/vendor/**` đổi đường dẫn WebJars sang dạng `/vendor/jquery/3.7.1/jquery.min.js`.
- `spring.webflux.*` là property cho WebFlux, không thay cho các property MVC khi ứng dụng đang chạy MVC.

Property `spring.web.resources.static-locations` **thay thế danh sách vị trí static mặc định**. Nếu đổi nó thành chỉ `classpath:/custom/`, bạn có thể vô tình làm `/brand-assets/theme.css` hoặc `/index.html` từ vị trí mặc định không còn được phục vụ. Hãy ghi rõ tất cả location cần giữ hoặc thêm resource handler riêng.

### 7.2. Thêm resource handler riêng cho một thư viện

Ở ứng dụng **Spring MVC**, khi muốn phục vụ CSS từ JAR `brand-assets` ở URL `/design/theme.css`, có thể thêm class Java sau (đây là class hoàn chỉnh, đặt trong package con của `com.example.webjarsdemo`):

```java
package com.example.webjarsdemo;

import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class BrandResourceConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/design/**")
                .addResourceLocations("classpath:/META-INF/resources/brand-assets/")
                .setCacheControl(CacheControl.maxAge(Duration.ofDays(7)));
    }
}
```

Với dependency ở mục 6, URL `/design/theme.css` được ánh xạ tới file `META-INF/resources/brand-assets/theme.css`. Phần còn lại của MVC auto-configuration vẫn được giữ khi bạn dùng `WebMvcConfigurer` mà **không thêm `@EnableWebMvc`**.

Nếu dùng WebFlux, thực hiện ý tưởng tương tự với `WebFluxConfigurer` và `org.springframework.web.reactive.config.ResourceHandlerRegistry`; không sao chép nguyên import MVC sang WebFlux.

**Lưu ý:** Không nên ánh xạ `classpath:/` hoặc một prefix quá rộng vào URL công khai. Hãy trỏ handler tới **thư mục assets dự kiến public**, và kiểm tra các file mà consumer thật sự có thể request.

## 8. Cache, phiên bản và URL an toàn khi triển khai

WebJars với version trong đường dẫn giúp browser phân biệt phiên bản:

```text
/webjars/jquery/3.7.1/jquery.min.js
/webjars/jquery/4.0.0/jquery.min.js
```

Nếu thay dependency jQuery sang phiên bản khác mà HTML vẫn giữ đường dẫn cũ, browser có thể nhận **404** hoặc tải phiên bản cũ từ một dependency còn sót trên classpath. Do đó update dependency và URL phải được kiểm thử cùng nhau.

### Cơ chế caching phù hợp

- **URL có version hoặc content fingerprint:** có thể cân nhắc `Cache-Control` thời gian dài khi nội dung được đảm bảo bất biến tại URL ấy.
- **URL không version, ví dụ `/brand-assets/theme.css`:** nếu cập nhật nội dung mà URL giữ nguyên, cache quá dài dễ làm trình duyệt giữ CSS cũ. Cân nhắc thời gian cache ngắn hơn hoặc dùng content-hash versioning.
- **`index.html`:** thường nên có chính sách cache linh hoạt hơn các asset fingerprinted để HTML mới có thể trỏ tới phiên bản asset mới.

Spring MVC/WebFlux có resource chain với `VersionResourceResolver`. Spring Boot còn có property:

```properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/css/**
```

Đây là **cấu hình minh họa** cho chiến lược content hash đối với đường dẫn CSS theo pattern; cần đảm bảo code tạo URL ở HTML/template dùng được URL đã version hóa. Việc chỉ bật strategy **không tự sửa một chuỗi URL hardcode trong HTML tĩnh**. Các view engine và `ResourceUrlProvider`/cơ chế rewrite hỗ trợ việc này; cần kiểm thử output trong browser.

Đừng áp `max-age` rất dài cho mọi đường dẫn `/**` khi chưa phân biệt tài nguyên bất biến và HTML. Với WebJars, URL có version từ chính artifact là một cách triển khai dễ kiểm soát.

## 9. Security và phạm vi tài nguyên được công khai

Một file nằm dưới `META-INF/resources/` hoặc path khác được map bởi resource handler nên được **coi là nội dung dành cho public HTTP**. Không đặt private key, JWT secret, file cấu hình nhạy cảm, source map nội bộ chứa thông tin cần hạn chế, dữ liệu khách hàng hoặc bản backup vào các đường dẫn này.

Các điểm cần nhớ:

1. **Spring Security** có thể yêu cầu xác thực cho `/webjars/**`, `/css/**` hoặc `/brand-assets/**` nếu cấu hình security chặn chúng. Trạng thái **401/403** có thể là lỗi quyền, không phải resource không tồn tại. Chỉ `permitAll()` cho những asset dự kiến public, giới hạn pattern đúng mức.
2. **Classpath JAR là nguồn cung cấp nội dung:** phụ thuộc web bên thứ ba cần được kiểm tra license, nguồn gốc, cập nhật bảo mật và dependency tree. Có WebJar trong JAR không tự chứng minh JavaScript an toàn.
3. **Content Security Policy (CSP):** nếu chính sách không cho inline JavaScript, đoạn `<script>` inline của demo sẽ bị chặn; trong ứng dụng thực nên chuyển script của mình sang file tĩnh và khai báo CSP phù hợp. WebJar tự host cùng origin thường giúp tránh một số phụ thuộc CDN, nhưng CSP vẫn áp dụng.
4. **CORS:** không phải lúc nào cũng cần. Nếu browser tải JS/CSS trên cùng origin, request static thông thường không cần cấu hình CORS riêng. Khi asset được tải chéo origin (đặc biệt fonts hoặc module), cần xét CORS, CSP và cách deploy.
5. **Không dùng resource handler như file server tùy ý:** cấu hình location và pattern công khai có chủ đích; không cho client chọn filesystem path tự do qua request parameter.

Dùng WebJars cũng không thay thế hoàn toàn các bước quản lý frontend: khi dự án lớn có tree-shaking, bundling, source maps, module graph phức tạp, giải pháp Node/npm + frontend bundler có thể hợp lý hơn.

## 10. Kiểm tra 404 và các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Kiểm tra và sửa |
| --- | --- | --- |
| `/webjars/jquery/3.7.1/jquery.min.js` trả 404 | Thiếu WebJar ở runtime, sai version hoặc sai file path | Kiểm tra `pom.xml`/Gradle dependency tree và đường dẫn thực trong JAR |
| URL có version chạy nhưng `/webjars/jquery/jquery.min.js` 404 | Không có locator hỗ trợ URL không version | Dùng URL có version, hoặc thêm `webjars-locator-lite` phù hợp |
| IDE chạy được, executable JAR không tải được CSS | Dependency bị khai báo sai scope, bị exclude hoặc packaging sai | Kiểm tra `BOOT-INF/lib`, JAR thư viện, chạy `java -jar` thật |
| CSS trong project chính chạy, CSS ở library JAR không chạy | File không nằm dưới location được phục vụ, sai tên prefix | Kiểm tra `jar tf brand-assets-1.0.0.jar` và `META-INF/resources/...` |
| Trả 401/403, không phải 404 | Security rule áp vào asset | Cấu hình security cho URL public, kiểm tra filter chain |
| Trả 200 nhưng trình duyệt không dùng CSS | Sai `<link>`, content type, cache cũ, CSP hoặc CSS specificity | Kiểm tra tab Network, Response/Content-Type, Console và Computed styles |
| Thêm `@EnableWebMvc` rồi mapping mặc định mất | Đã tự giành quyền cấu hình MVC khỏi Boot | Bỏ annotation nếu chỉ cần customization; dùng `WebMvcConfigurer` |
| Thay `spring.web.resources.static-locations` rồi mất index/asset | Property thay thế location mặc định | Cấu hình đầy đủ locations mong muốn hoặc thêm handler riêng |
| Đổi `spring.mvc.webjars-path-pattern` nhưng HTML vẫn dùng `/webjars/...` | Request không còn khớp pattern WebJar mới | Sửa URL theo pattern được cấu hình |
| Deploy dưới context path `/app` mà URL bắt đầu từ `/webjars/...` bị sai | URL tuyệt đối theo origin bỏ qua `/app` | Sinh URL có context path trong template (ví dụ Thymeleaf `@{/webjars/...}`) hoặc cấu hình base đúng |
| Asset từ hai dependency có cùng path | Xung đột tên resource trên classpath | Dùng prefix namespace riêng, kiểm tra dependency tree và artifact JAR |
| Dev chạy được nhưng cache production vẫn hiển thị JS/CSS cũ | URL không đổi nhưng cache quá lâu | Phiên bản/fingerprint asset và chính sách cache tương ứng |

### Quy trình chẩn đoán ngắn, có thứ tự

1. **Lấy URL thực** từ Network tab, gồm context path, URL encoding và HTTP status. Đừng chỉ nhìn đường dẫn viết trong source template.
2. **Xác nhận dependency runtime**: Maven dependency tree, POM/Gradle và kết quả build. Với WebJar, đọc artifactId, version và file path.
3. **Xác nhận đường dẫn bên trong JAR** bằng `jar tf`; đối chiếu từ `META-INF/resources` tới URL.
4. **Xác nhận loại stack và mapping**: MVC hay WebFlux, `spring.mvc.*` hoặc `spring.webflux.*`, custom resource handlers, `spring.web.resources.*`.
5. **Phân biệt lỗi:** 404 do mapping/path/packaging; 401/403 do Security; 200 nhưng giao diện lỗi do cache, CSP, JS execution hoặc MIME type.
6. **Chạy packaged JAR** đúng như môi trường triển khai, kiểm tra `curl -I`/browser, thay vì chỉ dựa trên file tồn tại trong source project.

Không cần viết một controller `@GetMapping("/webjars/...")` để khắc phục WebJar 404 trong trường hợp thông thường. Controller tự tạo có thể che lỗi root cause và làm mất caching/conditional requests của resource handler.

## 11. Khi nào nên chọn WebJar, JAR assets riêng hay frontend build?

| Phương án | Hợp với | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| **WebJar dependency** | Trang server-rendered, admin UI, thư viện JS/CSS bên thứ ba cần pin version qua Maven | Build JVM đóng gói cùng frontend asset, triển khai offline, URL theo version | Hệ sinh thái package JS/asset không luôn theo kịp npm; cần quan sát phiên bản thư viện |
| **JAR assets tự tạo** | Design system, icon/CSS/logos dùng chung giữa nhiều Spring Boot services | Một artifact dùng lại, version hóa trong Maven, tách quản trị tài nguyên | Phải tự chọn namespace, URL và chính sách cache |
| **`src/main/resources/static` của app** | Số lượng asset nhỏ, thuộc một app | Đơn giản, không có dependency riêng | Dùng lại giữa nhiều app kém thuận tiện |
| **npm + Vite/Webpack/Rollup** | SPA lớn, ES modules, bundling, tree-shaking, tối ưu frontend | Tooling frontend mạnh, chia bundle, tối ưu tài nguyên | Build pipeline phức tạp hơn, cần tích hợp đầu ra với Spring Boot/CDN |
| **CDN** | Asset public có yêu cầu phân phối toàn cầu | Có thể giảm tải server và dùng edge cache | Thêm phụ thuộc bên ngoài, cần xem CSP/SRI, độ tin cậy, version và cache |

Các phương án có thể kết hợp. Ví dụ: frontend được bundle ở CI rồi copy các asset cuối cùng vào `static` của backend; hoặc một JAR thư viện chỉ chứa các file build đã được duyệt. WebJars không yêu cầu Spring MVC cụ thể: nội dung JAR được phục vụ bởi bất kỳ runtime có resource mapping thích hợp.

## 12. Câu hỏi luyện tập

1. **Một WebJar có `jquery-3.7.1.jar`, muốn tải `jquery.min.js`, URL mặc định là gì?**  
   `/webjars/jquery/3.7.1/jquery.min.js`, nếu resource có đúng tên/path trong JAR và Boot giữ mapping mặc định.

2. **Tại sao URL không chứa `META-INF/resources`?**  
   Vì đó là classpath resource location nội bộ; Spring resource handler ánh xạ phần còn lại sang URL công khai.

3. **Một JAR `brand-assets` không có Java class có thể phục vụ CSS không?**  
   Có, nếu chứa `META-INF/resources/brand-assets/theme.css`, được đưa vào runtime classpath và Boot có mapping tương ứng.

4. **Có phải thêm WebJar là đủ để URL không có version tự chạy?**  
   Không chắc. Với Spring hiện đại, cơ chế versionless cần `webjars-locator-lite`; URL có version không cần locator.

5. **Vì sao bỏ `@EnableWebMvc` thường sửa được lỗi WebJar 404?**  
   Vì `@EnableWebMvc` khiến ứng dụng tự quản lý MVC configuration thay cho Boot auto-configuration; default resource mappings của Boot có thể không còn.

6. **Khác gì giữa 404 và 403 khi tải CSS?**  
   404 thường do không tìm thấy URL/resource; 403 là request bị từ chối bởi security hoặc chính sách truy cập. Cần kiểm tra response và filter chain trước khi chỉnh Maven.

7. **Làm sao xác nhận một resource nằm trong executable JAR?**  
   Kiểm tra JAR dependency gốc bằng `jar tf`; kiểm tra executable JAR có nested dependency ở `BOOT-INF/lib`; rồi gọi URL runtime.

8. **URL dạng `/webjars/jquery/3.7.1/jquery.min.js` có tự bắt trình duyệt cache một năm không?**  
   Không. Có version giúp có thể cache dài an toàn hơn; HTTP cache policy vẫn cần được đặt và kiểm thử.

## 13. Checklist khi đưa vào dự án

- [ ] Chọn WebJar, custom assets JAR hoặc static của ứng dụng theo phạm vi tái sử dụng.
- [ ] Ghim phiên bản dependency, xác nhận artifact tồn tại và phù hợp license/security policy.
- [ ] Xác nhận file có trong JAR tại `META-INF/resources/...` bằng `jar tf`.
- [ ] Dùng URL tương ứng với đường dẫn thật trong JAR, ưu tiên WebJar URL có version.
- [ ] Không bật `@EnableWebMvc` nếu chỉ cần bổ sung resource handlers.
- [ ] Kiểm tra các property `spring.web.resources.*` và pattern MVC/WebFlux trước khi sửa mapping.
- [ ] Đảm bảo asset thực sự public; không để bí mật vào thư mục được ánh xạ.
- [ ] Chọn cache policy riêng cho HTML và asset versioned/fingerprinted.
- [ ] Kiểm tra dưới context path/reverse proxy thực, không hardcode sai URL gốc.
- [ ] Chạy cả Maven development mode và executable JAR; kiểm tra HTTP response/Network tab.

## 14. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Servlet Web Applications / Static Content / WebJars](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot — Reactive Web Applications / Static Content](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Framework — MVC Static Resources và WebJars locator](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html)
- [Spring Framework — WebFlux Static Resources](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [WebJars — Documentation](https://www.webjars.org/documentation)
- [Maven Central — WebJar jQuery 3.7.1](https://central.sonatype.com/artifact/org.webjars/jquery/3.7.1)
- [Spring Boot — Maven executable JAR](https://docs.spring.io/spring-boot/3.5/how-to/build.html)

**Điểm cần nhớ:** WebJars là cách mang thư viện frontend vào **dependency JAR** với đường dẫn chuẩn `META-INF/resources/webjars/...`; resource handler của Spring Boot phơi bày nó qua `/webjars/**`. Các tài nguyên chung nằm trong `META-INF/resources/{namespace}/...` của **một JAR thư viện bất kỳ** cũng có thể được phục vụ bằng đường dẫn HTTP tương ứng. Hãy kiểm tra cả **classpath, đường dẫn bên trong JAR, resource mapping, security và cache** khi triển khai.
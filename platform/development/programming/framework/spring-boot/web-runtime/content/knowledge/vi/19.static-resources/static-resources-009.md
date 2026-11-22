# Tài nguyên tĩnh trong executable JAR, WAR và khi chạy từ IDE

## 1. Mục tiêu và vấn đề cốt lõi

Tài nguyên tĩnh (*static resources*) là các tệp được trả nguyên nội dung cho HTTP client, chẳng hạn `index.html`, CSS, JavaScript, ảnh, font, favicon hoặc tài liệu PDF công khai. Trong ứng dụng Spring Boot Web, chúng thường được phục vụ bởi **resource handler** đã được framework cấu hình; không cần tạo một `@GetMapping` riêng cho từng file.

Vấn đề thường xảy ra: `/css/site.css` tải thành công khi chạy main class trong IDE nhưng trả **404** sau khi build `.jar` hoặc deploy `.war`. Nguyên nhân chủ yếu là **classpath, cấu trúc archive và application context path khác nhau**, trong khi developer nhầm lẫn giữa vị trí nguồn, vị trí đóng gói và URL public.

Ba khái niệm cần tách biệt:

- **Source path:** file nằm ở đâu trong project, ví dụ `src/main/resources/static/css/site.css`.
- **Runtime resource location:** Spring tìm resource ở đâu sau khi chạy/build, ví dụ `classpath:/static/css/site.css`, bên trong archive là `BOOT-INF/classes/static/css/site.css`.
- **HTTP URL:** client gọi đường nào, ví dụ `GET /css/site.css` nếu context path và static path pattern mặc định.

Đường dẫn `src/main/resources/static` **không phải prefix URL**. Gọi `/static/css/site.css` thường sai; URL mặc định tương ứng là `/css/site.css`.

Bài này tập trung Spring Boot 3.x, Java 17+, Spring MVC/Servlet với executable JAR và WAR. WebFlux có phần riêng vì không dùng WAR/Servlet web root theo cùng cách.

## 2. Vị trí tài nguyên tĩnh mặc định trong Spring Boot

Spring Boot MVC tìm nội dung tĩnh từ các location trên classpath và từ root của `ServletContext`:

| Runtime location | Vị trí nguồn phổ biến | URL khi app chạy ở root context |
| --- | --- | --- |
| `classpath:/static/` | `src/main/resources/static/` | `/path/to/file` |
| `classpath:/public/` | `src/main/resources/public/` | `/path/to/file` |
| `classpath:/resources/` | `src/main/resources/resources/` | `/path/to/file` |
| `classpath:/META-INF/resources/` | `src/main/resources/META-INF/resources/` | `/path/to/file` |
| Servlet web root (MVC) | `src/main/webapp/` khi đóng gói WAR | `/path/to/file` |

Ví dụ dự án:

~~~text
src/main/resources/
├── static/
│   ├── index.html
│   ├── css/site.css
│   └── js/app.js
├── public/
│   └── images/logo.svg
└── META-INF/
    └── resources/robots.txt
~~~

Khi không đổi mapping, các URL tương ứng là:

~~~text
GET /                    -> static/index.html (welcome page nếu được nhận)
GET /index.html          -> static/index.html
GET /css/site.css        -> static/css/site.css
GET /js/app.js           -> static/js/app.js
GET /images/logo.svg     -> public/images/logo.svg
GET /robots.txt          -> META-INF/resources/robots.txt
~~~

Spring MVC dùng `ResourceHttpRequestHandler`; Spring WebFlux dùng `ResourceWebHandler`. Mapping tài nguyên mặc định thường là `/**`, nhưng handler cho controller/route và welcome page có thứ tự xử lý riêng. Nếu đặt hai file cùng tên tương đối vào nhiều location khác nhau, bạn tạo ra tình trạng khó dự đoán theo cấu hình/thứ tự classpath; nên chọn một source location nhất quán.

### `index.html` và `templates/index.html` là hai thứ khác nhau

`src/main/resources/static/index.html` có thể trở thành **welcome page** ở `GET /`. Ngược lại `src/main/resources/templates/index.html` là template dành cho view engine như Thymeleaf, không tự được phục vụ như file tĩnh. Muốn dùng template phải có cấu hình engine và controller/view mapping thích hợp.

File static là **public theo resource mapping** trừ khi có cơ chế bảo vệ riêng. Không để token, khóa bí mật, cấu hình riêng, backup hay dữ liệu khách hàng trong các static locations.

## 3. IDE, Gradle/Maven output và classpath

Trong IDE, thao tác Run có thể đặt source resources hoặc thư mục output vào runtime classpath. Với Gradle/Maven tiêu chuẩn:

~~~text
Nguồn:          src/main/resources/static/css/site.css
                 |
                 v
Gradle output:   build/resources/main/static/css/site.css
Maven output:    target/classes/static/css/site.css
                 |
                 v
Classpath URI:   classpath:/static/css/site.css
                 |
                 v
HTTP URL:        /css/site.css
~~~

IDE có thể dùng thư mục output riêng theo cấu hình của nó. Điều cần kiểm tra là **resource có mặt trên runtime classpath hay không**, không phải chỉ có file trên ổ đĩa. Khi sửa file ở `src/main/resources`, IDE có thể phải build/sync/copy resources lại; thay đổi IDE tự theo dõi file không bảo đảm artifact đã được đóng gói đúng.

Dấu hiệu hữu ích khi debug:

1. Chạy bằng main class IDE và truy cập `http://localhost:8080/css/site.css`.
2. Chạy `./gradlew bootRun` hoặc `./gradlew processResources` để kiểm tra file trong `build/resources/main/static/css/site.css`.
3. Đóng gói rồi **liệt kê nội dung archive**; kiểm tra `BOOT-INF/classes/...` hoặc `WEB-INF/classes/...`.
4. Khởi động chính archive đã build, gọi lại HTTP URL và so sánh.

Tài nguyên có trong IDE không có nghĩa task `bootJar`/`bootWar` chắc chắn lấy nó; build có thể có source-set tùy chỉnh, exclude hoặc file được sinh ra sau thời điểm đóng gói.

## 4. Executable JAR và vị trí thực của static resources

Spring Boot `bootJar` tạo archive có launcher, application classes và dependency. Layout minh họa:

~~~text
assets-demo.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── demo/assets/StaticAssetsApplication.class
    │   ├── application.properties
    │   └── static/
    │       ├── index.html
    │       ├── css/site.css
    │       └── js/app.js
    └── lib/
        ├── spring-webmvc-....jar
        └── ... các dependency khác
~~~

**`src/main/resources/static/css/site.css` → `BOOT-INF/classes/static/css/site.css`**. Spring Boot launcher xây classloader sao cho `BOOT-INF/classes` là classpath application, nên resource handler vẫn tìm được `classpath:/static/css/site.css`. Không cần giải nén JAR ra đĩa để phục vụ file.

### Bẫy `src/main/webapp`

`src/main/webapp` là quy ước của **Servlet WAR**, không phải location classpath static của executable JAR. Spring Boot chính thức cảnh báo rằng với JAR, phần lớn build tool **bỏ qua** thư mục này.

~~~text
src/main/webapp/css/site.css       (không dùng làm nguồn static cho bootJar)
src/main/resources/static/css/site.css  (nên dùng cho bootJar)
~~~

Nếu `src/main/webapp` tình cờ được IDE hoặc một local servlet runtime phục vụ, JAR production vẫn có thể thiếu file. Cách sửa bền vững là chuyển file sang một location đúng trong `src/main/resources` và kiểm tra archive; đừng tạo controller để che lỗi package.

### `jar` và `bootJar` khác nhau

`jar` thường tạo Java archive tiêu chuẩn. `bootJar` dùng Spring Boot plugin, đóng gói dependency và launcher để chạy bằng `java -jar`. Nếu build ra plain JAR rồi tưởng nó là executable JAR, cấu trúc/runtime classpath sẽ khác. Luôn xác nhận task tạo ra file được triển khai thật.

## 5. Ví dụ tối thiểu chạy được bằng Java 17 + Spring Boot MVC

Tạo một dự án Gradle Java. Ví dụ chọn Spring Boot `3.3.13` và Gradle plugin dependency management `1.1.6` làm phiên bản minh họa; dự án thực tế dùng phiên bản đã được kiểm soát và hỗ trợ trong hệ build của mình.

Cấu trúc:

~~~text
assets-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/demo/assets/StaticAssetsApplication.java
        └── resources/
            ├── application.properties
            └── static/
                ├── index.html
                ├── css/site.css
                └── js/app.js
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'assets-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('bootJar') {
    archiveFileName = 'assets-demo.jar'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/java/demo/assets/StaticAssetsApplication.java`:

~~~java
package demo.assets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StaticAssetsApplication {
    public static void main(String[] args) {
        SpringApplication.run(StaticAssetsApplication.class, args);
    }
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

`src/main/resources/static/index.html`:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Static Assets Demo</title>
  <link rel="stylesheet" href="css/site.css">
  <script defer src="js/app.js"></script>
</head>
<body>
  <h1>Static assets từ Spring Boot</h1>
  <p id="status">Đang đợi JavaScript</p>
</body>
</html>
~~~

`src/main/resources/static/css/site.css`:

~~~css
body {
    color: #234;
    font-family: sans-serif;
    margin: 2rem;
}
~~~

`src/main/resources/static/js/app.js`:

~~~javascript
document.getElementById("status").textContent = "JavaScript đã tải";
~~~

Không cần controller: khi Web MVC auto-configuration được giữ nguyên, Spring Boot tự phục vụ các file.

### Chạy khi phát triển

Với IDE, import project Gradle và chạy main class `demo.assets.StaticAssetsApplication`. Nếu dùng Gradle wrapper có sẵn:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi server chạy cổng 8080:

~~~bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/js/app.js
~~~

Kiểm chứng: `GET /` trả HTTP **200** với chuỗi `Static assets từ Spring Boot`; CSS trả **200** với `color: #234;`, JavaScript trả **200** với dòng `textContent = "JavaScript đã tải"`. Browser hiển thị câu "JavaScript đã tải". Thứ tự và nội dung các header hệ thống có thể thay đổi theo server/runtime.

### Đóng gói JAR, kiểm tra nội dung, chạy JAR

~~~bash
./gradlew clean bootJar
jar tf build/libs/assets-demo.jar | grep "BOOT-INF/classes/static/"
java -jar build/libs/assets-demo.jar
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
jar tf .\build\libs\assets-demo.jar |
    Select-String 'BOOT-INF/classes/static/'
java -jar .\build\libs\assets-demo.jar
~~~

Các entry cần xuất hiện (thứ tự không quan trọng):

~~~text
BOOT-INF/classes/static/index.html
BOOT-INF/classes/static/css/site.css
BOOT-INF/classes/static/js/app.js
~~~

Lặp lại ba request HTTP. Trước khi chạy JAR trên cùng host, dừng `bootRun` cũ nếu cả hai cùng chiếm cổng 8080. Nếu archive không chứa các entry trên, sửa nguồn hoặc task build; nếu archive đủ mà HTTP 404, xét mapping/config/context path trước.

**Smoke test thực tế:** copy JAR sang một thư mục khác không chứa source project rồi chạy. Nếu `GET /css/site.css` vẫn thành công, tài nguyên đã nằm trong archive, không lệ thuộc file nguồn ngoài.

## 6. WAR: hai loại location và hai cách khởi động

WAR là archive theo mô hình Servlet Web Application. Spring Boot **MVC/Servlet** có thể tạo executable WAR để chạy `java -jar`, đồng thời deploy vào Servlet container ngoài nếu cấu hình phù hợp.

Layout minh họa:

~~~text
assets-demo.war
├── META-INF/
├── WEB-INF/
│   ├── classes/
│   │   ├── demo/assets/StaticAssetsApplication.class
│   │   └── static/
│   │       ├── index.html
│   │       └── css/site.css
│   ├── lib/...
│   └── lib-provided/...
├── css/
│   └── war-only.css
└── favicon.ico
~~~

Ở đây có **hai nguồn**:

- **Classpath static:** `src/main/resources/static/css/site.css` nằm tại `WEB-INF/classes/static/css/site.css`. Spring resource handler phục vụ nó qua URL `/css/site.css` trong application context.
- **Servlet web root:** `src/main/webapp/css/war-only.css` nằm tại `css/war-only.css` ở root WAR. Khi WAR được triển khai như Servlet web app, web root là location dành riêng cho tài nguyên kiểu WAR.

Không gọi `/WEB-INF/classes/static/css/site.css` từ browser. `WEB-INF` thuộc cấu trúc nội bộ, và container không công bố nó trực tiếp; URL đúng do **resource mapping** quyết định.

**Khuyến nghị:** nếu muốn một nhóm asset chạy giống nhau khi IDE, JAR và WAR, dùng `src/main/resources/static`. Dùng `src/main/webapp` khi mục tiêu thực sự là WAR và bạn đã test kiểu deployment đó.

### Gradle cho executable và deployable WAR

Để tạo biến thể WAR từ dự án MVC ví dụ trên, dùng `build.gradle` sau thay cho cấu hình JAR:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('bootWar') {
    archiveFileName = 'assets-demo.war'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`providedRuntime` cho phép đóng gói thư viện container nhúng trong khu vực thích hợp (thường `WEB-INF/lib-provided`) khi cần cả executable WAR và deploy vào container ngoài. Không thay `providedRuntime` bằng `compileOnly` một cách tùy tiện: tích hợp test có thể thiếu các thư viện runtime cần thiết.

Để external servlet container khởi tạo Spring Boot app, thay nội dung main class bằng:

~~~java
package demo.assets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class StaticAssetsApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(StaticAssetsApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(StaticAssetsApplication.class, args);
    }
}
~~~

Đây là **cùng tệp Java** của ví dụ JAR, phiên bản dành cho WAR; không tạo hai public class trùng package/tên cùng lúc. `main()` hỗ trợ chạy executable WAR, `configure(...)` hỗ trợ container ngoài. Với Spring Boot 3.x, external container phải tương thích **Jakarta Servlet**; không dùng container cũ chỉ hỗ trợ `javax.servlet`.

Có thể thêm `src/main/webapp/css/war-only.css`:

~~~css
.war-banner { font-weight: bold; }
~~~

Lệnh:

~~~bash
./gradlew clean bootWar
jar tf build/libs/assets-demo.war | grep "WEB-INF/classes/static/"
jar tf build/libs/assets-demo.war | grep "css/war-only.css"
java -jar build/libs/assets-demo.war
~~~

Cần nhìn thấy `WEB-INF/classes/static/index.html` và `WEB-INF/classes/static/css/site.css`; tài nguyên WAR-root xuất hiện dưới `css/war-only.css`. Khi chạy ở Servlet container ngoài, context path có thể đến từ WAR name hoặc cấu hình container. Ví dụ nếu context là `/assets-demo` thì client gọi `/assets-demo/css/site.css`, không phải `/css/site.css`. Không xem tên archive là context path cố định trong mọi môi trường.

### WAR không áp dụng như nhau cho WebFlux

Spring Boot WebFlux dùng `ResourceWebHandler` với classpath locations tương tự nhưng **không dùng `src/main/webapp` và không hỗ trợ triển khai WAR theo cách Servlet MVC**. Với WebFlux, chọn executable JAR và tài nguyên trong `src/main/resources/static`. Nếu đồng thời thêm `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot mặc định ưu tiên MVC, nên cần xác định web stack thực tế.

## 7. Bảng so sánh IDE, JAR và WAR

| Tiêu chí | IDE / `bootRun` | Executable JAR | WAR |
| --- | --- | --- | --- |
| Static nguồn nên dùng | `src/main/resources/static` | `src/main/resources/static` | `src/main/resources/static`; `webapp` khi cần Servlet web root |
| Nơi chứa file lúc runtime | IDE output/classpath, thường `build/resources/main` hoặc `target/classes` | `BOOT-INF/classes/static` | `WEB-INF/classes/static` |
| `src/main/webapp` | Có thể được môi trường dev hỗ trợ; không nên dựa vào | Không đáng tin, thường không được đóng gói | Đóng gói thành WAR root |
| Build/launcher | Main class, `bootRun` | `bootJar`, `java -jar .jar` | `bootWar`, `java -jar .war` hoặc external container |
| URL mặc định | `/css/site.css` | `/css/site.css` | `/css/site.css` bên trong WAR context |
| Sai lầm dễ gặp | IDE chưa sync resource output | Tệp không nằm trong archive | Sai context path, sai cấu trúc WAR hoặc container không tương thích |

Không dùng việc IDE trả HTTP 200 để kết luận artifact production sẽ thành công. Kiểm tra **chính archive mà CI/CD phát hành**.

## 8. Cấu hình URL pattern và resource location

### Đổi URL static nhưng giữ nguyên vị trí file

Spring MVC:

~~~properties
spring.mvc.static-path-pattern=/assets/**
~~~

File `src/main/resources/static/css/site.css` bây giờ được phục vụ tại `/assets/css/site.css` (tương đối với context path). Không chuyển file vào `static/assets` vì thuộc tính này đổi **URL mapping**, không đổi vị trí nguồn.

Spring WebFlux có property khác:

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

Không dùng `spring.mvc.static-path-pattern` để điều chỉnh WebFlux thuần hoặc ngược lại.

### Thay vị trí tìm static resources

~~~properties
spring.web.resources.static-locations=classpath:/site/
~~~

Khi đó resource handler tìm từ `src/main/resources/site` (sau build thành classpath). Giá trị này **thay thế danh sách classpath static locations mặc định**; nếu cần cả custom location và default static location, khai báo rõ:

~~~properties
spring.web.resources.static-locations=classpath:/static/,classpath:/site/
~~~

Trong MVC/Servlet, root ServletContext vẫn được tự thêm như một location. Trong WebFlux không có Servlet web root. Cấu hình nhiều location chỉ nên dùng khi tránh tên file trùng nhau.

### Thay Servlet context path

~~~properties
server.servlet.context-path=/catalog
~~~

Với MVC embedded server, URL public là `/catalog/css/site.css`. File vẫn ở `static/css/site.css`. Khi chạy WAR trong external container, context path phụ thuộc cấu hình deploy; đừng hard-code path từ tên thư mục chứa JAR/WAR.

### Đọc static từ thư mục ngoài archive

~~~properties
spring.web.resources.static-locations=classpath:/static/,file:/opt/demo/public/
~~~

`file:/opt/demo/public/` là ví dụ dành cho môi trường Unix/Linux. Khi deploy, thư mục phải tồn tại và tiến trình có quyền đọc; container có thể cần volume mount. Những file bên ngoài không tự nằm trong JAR, nên test cần xác minh hạ tầng runtime. Không map những thư mục chứa dữ liệu bí mật hoặc dữ liệu upload riêng tư vào HTTP public.

### Tắt mapping mặc định

~~~properties
spring.web.resources.add-mappings=false
~~~

Nếu tắt auto static mapping mà không tự khai báo resource handler, request có thể trả 404 **dù file có trong archive**. Tương tự, cấu hình `@EnableWebMvc` hoặc `@EnableWebFlux` thường yêu cầu tự kiểm soát phần lớn framework configuration; để tùy chỉnh hạn chế, nên dùng `WebMvcConfigurer`/`WebFluxConfigurer` mà vẫn giữ auto-configuration khi phù hợp.

## 9. Tại sao `getFile()` chạy trong IDE nhưng lỗi với executable JAR?

Khi chạy IDE, resource classpath có thể là một file ngoài ổ đĩa. Sau khi đóng gói, resource được đọc từ JAR entry và **không nhất thiết ánh xạ được thành một `java.io.File` thực**.

Cách dễ hỏng:

~~~java
// Snippet mô tả lỗi thường gặp:
Resource resource = new ClassPathResource("static/css/site.css");
File file = resource.getFile(); // Có thể lỗi khi resource ở trong JAR
~~~

Để đọc đúng dữ liệu classpath, dùng stream. Ví dụ Java đầy đủ trong tệp `src/main/java/demo/assets/ReadAsset.java` (chạy với Spring Core trên classpath):

~~~java
package demo.assets;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;

public final class ReadAsset {
    private ReadAsset() {
    }

    public static void main(String[] args) throws IOException {
        ClassPathResource css =
                new ClassPathResource("static/css/site.css");

        try (InputStream in = css.getInputStream()) {
            String text = new String(
                    in.readAllBytes(), StandardCharsets.UTF_8);
            System.out.println(text.contains("color: #234;"));
        }
    }
}
~~~

Với file CSS mục 5, **stdout** của class này là:

~~~text
true
~~~

`ReadAsset` là một Java main riêng được chạy bằng IDE/JavaExec với dependency Spring trên classpath. Launcher của `assets-demo.jar` vẫn dùng main class `StaticAssetsApplication` theo cấu hình build. Trong app Boot, có thể áp dụng `ClassPathResource#getInputStream()` trong service hoặc `CommandLineRunner` với cùng nguyên tắc.

**Chú ý:** Spring MVC/WebFlux phục vụ static file qua HTTP **không yêu cầu** bạn tự đọc bằng `ClassPathResource`. Resource handler xử lý sẵn; `getInputStream()` chỉ dành cho mã Java thật sự cần đọc tài nguyên.

## 10. Test HTTP và kiểm tra artifact

Thêm test JUnit 5 với `spring-boot-starter-test` ở `src/test/java/demo/assets/StaticAssetsHttpTest.java`:

~~~java
package demo.assets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StaticAssetsHttpTest {
    @Autowired
    TestRestTemplate http;

    @Test
    void welcomePageIsServed() {
        ResponseEntity<String> response =
                http.getForEntity("/", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .contains("Static assets từ Spring Boot");
    }

    @Test
    void cssIsServed() {
        ResponseEntity<String> response =
                http.getForEntity("/css/site.css", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("color: #234;");
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.assets.StaticAssetsHttpTest
~~~

`RANDOM_PORT` khởi động HTTP server thật trên cổng động; `TestRestTemplate` biết root URL test. Test chứng minh classpath và resource mapping hoạt động **trong môi trường test**. Nó không đủ để bảo đảm tệp đã được đóng gói trong JAR/WAR: vẫn phải dùng `jar tf` và smoke test chính artifact.

Với JAR đã build:

~~~bash
jar tf build/libs/assets-demo.jar | grep "BOOT-INF/classes/static/"
curl -i http://localhost:8080/
curl -I http://localhost:8080/css/site.css
~~~

`curl -I` dùng HEAD nên response không có body; kiểm tra status 200 và media type CSS. Với WAR, thay bằng `jar tf build/libs/assets-demo.war` và dùng đúng context path khi gửi request.

## 11. Khác biệt khi triển khai thật

### Case sensitivity

Windows thường không phân biệt chữ hoa/thường trong tên file; Linux và lookup entry trong archive cần đối chiếu tên chính xác. `Logo.svg` và `logo.svg` không nên bị dùng lẫn. Một URL chạy trên máy phát triển có thể 404 trong container Linux.

### Cache cũ hoặc CDN

Khi HTTP trả 200 nhưng trình duyệt hiển thị JavaScript/CSS cũ, xem HTTP cache, CDN, reverse proxy hoặc service worker trước khi kết luận resource mới không được package. Spring Boot hỗ trợ cache-control, ví dụ:

~~~properties
spring.web.resources.cache.cachecontrol.max-age=30d
~~~

Với tài nguyên đổi nội dung thường xuyên, nên dùng file name có fingerprint/version. Resource chain có thể cấu hình versioning, nhưng HTML hard-code không tự nhiên được rewrite nếu thiếu cơ chế sinh URL tương ứng. Phân biệt **asset phiên bản mới đã deploy** với **browser đang gọi URL cache cũ**.

### WebJars và dependency resources

Các dependency có thể đóng gói resource dưới `META-INF/resources`, đặc biệt WebJars theo `META-INF/resources/webjars`. Vì vậy asset có thể được phục vụ từ dependency nested JAR mà không xuất hiện trong `BOOT-INF/classes/static`. Khi tìm nguồn của tài nguyên WebJars, kiểm tra dependency và mapping `/webjars/**`.

### SPA route fallback

Trang Single Page Application có thể tải `GET /` thành công nhưng refresh trực tiếp `/users/42` trả 404 vì đây là route của client, không phải file tĩnh. Cần cấu hình forward/fallback phù hợp cho HTML entry, đồng thời tránh bắt nhầm `/api/**` và tên asset. Đổi từ JAR sang WAR không tự giải quyết SPA routing.

### Security và header

Dù file có trong JAR, request có thể nhận 401/403 nếu security filter chặn, hoặc bị browser từ chối bởi Content Security Policy/MIME type. Phân biệt rõ **404 vì resource không tìm thấy**, **401/403 vì security**, **200 HTML fallback thay vì CSS**, và **không tải được vì proxy/network**. Không đưa dữ liệu nhạy cảm vào public static locations.

## 12. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân hay gặp | Bước xử lý |
| --- | --- | --- |
| IDE 200, JAR 404 | Static file ở `src/main/webapp` hoặc bị build exclude | `jar tf`, chuyển vào `src/main/resources/static` và build lại |
| IDE 404, JAR 200 | IDE chưa copy resources hoặc classpath root sai | Refresh Gradle/Maven, kiểm tra IDE output |
| Archive có file, HTTP 404 | Sai context/path pattern/static locations hoặc auto mapping bị tắt | Xem effective properties và handler mapping |
| WAR 404 tại `/css/...` nhưng hoạt động với `/app/css/...` | WAR được deploy với context path `/app` | Dùng đúng context root, kiểm tra cấu hình container |
| `getFile()` lỗi trong JAR | Resource là archive entry, không phải OS file | Dùng `getInputStream()` |
| WebFlux không phục vụ `src/main/webapp` | Không dùng Servlet web root | Dùng `src/main/resources/static` trong JAR |
| `index.html` 200 nhưng `/foo/bar` 404 | SPA client route chưa có server fallback | Thiết kế SPA fallback an toàn |
| CSS 200 nhưng browser báo sai MIME | Response là HTML error/fallback | Xem response body và `Content-Type` |
| Asset chỉ cũ trên browser | Cache, service worker, CDN hoặc old artifact | So checksum, URL version, cache policy |
| Linux 404, Windows chạy được | Khác chữ hoa/thường tên file | Kiểm tra path đúng từng ký tự |
| Static 404 sau `@EnableWebMvc` | MVC auto-config bị thay đổi | Khôi phục cấu hình hoặc thêm resource handler đúng |
| Tài nguyên riêng bị lộ | Đặt sai trong public static folder | Chuyển khỏi static và áp dụng auth endpoint |

**Quy trình điều tra thực tế:**

1. Xác định archive và phương thức chạy: IDE/main, `bootRun`, `java -jar`, external WAR.
2. Xác định URL đang gọi gồm context path và resource path; xem HTTP status + body thật.
3. Xác nhận đúng artifact đang được deploy, liệt kê archive bằng `jar tf`.
4. Đối chiếu nội dung archive với file nguồn, build output và source-set configuration.
5. Kiểm tra `spring.web.resources.*`, `spring.mvc.static-path-pattern` hoặc `spring.webflux.static-path-pattern`, security và mapping tùy chỉnh.
6. Nếu HTTP 200 mà UI sai, kiểm tra response Content-Type, cache, browser console, frontend base URL và proxy.

Chỉ sửa lớp gây lỗi thực tế. Khi asset không có trong archive, thêm `@GetMapping` thường không giải quyết vấn đề nguồn lực.

## 13. Tóm tắt bằng một sơ đồ

~~~text
                            FILE TRONG PROJECT
                                    |
                 +------------------+------------------+
                 |                                     |
      src/main/resources/static/             src/main/webapp/
                 |                                     |
         Build processResources                   Servlet WAR only
                 |                                     |
        +--------+--------+                            |
        |                 |                            |
      IDE              bootJar                        bootWar
  classpath output        |                            |
        |       BOOT-INF/classes/static/       WAR root + WEB-INF/classes/static/
        |                 |                            |
        +-----------------+----------------------------+
                          |
                   Web resource mapping
                          |
              URL /css/site.css (trong context)
~~~

Các file `src/main/resources/static` phù hợp cho IDE, executable JAR và WAR; `src/main/webapp` chỉ dành cho nhu cầu web root theo WAR/Servlet. Khi lỗi xuất hiện sau deploy, luôn xác minh **runtime classpath/war root trước URL mapping**.

## 14. Bài tập tự kiểm tra

**1.** File `src/main/resources/static/images/logo.png` được đóng gói JAR. URL mặc định là `/static/images/logo.png` hay `/images/logo.png`?

**Đáp án:** `/images/logo.png`; `static` không phải URL prefix.

**2.** Vì sao `src/main/webapp/css/site.css` có thể chạy ở local nhưng không có trong executable JAR?

**Đáp án:** `webapp` là vị trí nguồn cho WAR/Servlet web root; `bootJar` thường không đưa thư mục ấy vào classpath. Chuyển tới `src/main/resources/static/css/site.css` và xác nhận bằng `jar tf`.

**3.** Cùng một file CSS ở `src/main/resources/static`, vị trí bên trong JAR và WAR là gì?

**Đáp án:** JAR: `BOOT-INF/classes/static/css/site.css`; WAR: `WEB-INF/classes/static/css/site.css`.

**4.** WAR triển khai ở context `/demo`. URL CSS là `/css/site.css` hay `/demo/css/site.css`?

**Đáp án:** URL từ bên ngoài thường là `/demo/css/site.css`, nếu dùng mapping mặc định và context đúng như giả định.

**5.** Bật `spring.mvc.static-path-pattern=/assets/**`; file vẫn nằm `static/css/site.css`. URL nào đúng?

**Đáp án:** `/assets/css/site.css` trong application context.

**6.** Tại sao không dùng `new ClassPathResource(...).getFile()` cho file đóng gói trong JAR?

**Đáp án:** Resource có thể ở bên trong archive mà không có file OS tương ứng; dùng `getInputStream()`.

**7.** `@SpringBootTest` với `RANDOM_PORT` đã pass. Có còn cần kiểm tra archive production không?

**Đáp án:** Có. Test chứng minh runtime test classpath và HTTP mapping; task package vẫn có thể bỏ file khi tạo JAR/WAR.

**8.** WebFlux có dùng `src/main/webapp` để deploy WAR như Spring MVC không?

**Đáp án:** Không. Với Spring Boot WebFlux, dùng static classpath locations và executable JAR.

## 15. Tài liệu chính thức

- [Spring Boot 3.3 — Servlet Web Applications / Static Content](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): default static locations, `spring.mvc.static-path-pattern`, servlet root và cảnh báo `src/main/webapp` với JAR.
- [Spring Boot — Reactive Web Applications / Static Content](https://docs.spring.io/spring-boot/reference/web/reactive.html): `ResourceWebHandler`, `spring.webflux.static-path-pattern`, giới hạn WebFlux WAR.
- [Spring Boot — Nested JAR / Executable Archive Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html): `BOOT-INF/classes`, `WEB-INF/classes` và dependency layout.
- [Spring Boot — Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar`, `bootWar` và `providedRuntime`.
- [Spring Framework — Spring MVC Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): resource handling, caching và customization.

**Kết luận:** Đối với các asset công khai cần hoạt động ổn định khi chạy từ IDE, executable JAR và WAR, hãy đặt chúng trong `src/main/resources/static`. Quan sát **classpath, archive và HTTP URL** như ba lớp riêng, rồi kiểm tra từng lớp khi triển khai.

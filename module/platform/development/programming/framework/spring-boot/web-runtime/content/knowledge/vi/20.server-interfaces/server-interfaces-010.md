# Chẩn đoán không tìm thấy template và khác biệt thứ tự classpath trong Spring Boot

## 1. Hiểu đúng sự cố cần chẩn đoán

Trong ứng dụng Spring Boot có giao diện được render ở máy chủ, một controller có thể trả về tên view `"catalog/detail"` nhưng trình duyệt báo lỗi hoặc hiển thị một trang không đúng phiên bản. Cùng một source code, `bootRun` có thể chạy tốt, IDE chạy lỗi; ngược lại, IDE hiển thị template mới nhưng executable JAR vẫn render bản cũ.

Đây không luôn là một lỗi “đặt sai đường dẫn HTML”. Có ít nhất bốn câu hỏi độc lập:

1. **Request có đến đúng controller/handler không?** Nếu không, template engine chưa có cơ hội hoạt động.
2. **Controller trả view name hay response body?** Chỉ đường đi phù hợp mới gọi view resolution.
3. **View resolver/template resolver tạo đường dẫn tài nguyên nào?** Prefix, view name, suffix, locale, engine và customizations quyết định đích.
4. **Classpath runtime chứa tài nguyên gì, và thứ tự lookup là gì?** Khi cùng tên tài nguyên có trong nhiều source sets, modules hoặc JAR, thứ tự IDE/Gradle/executable JAR có thể ảnh hưởng kết quả.

Trong Spring Boot **3.3.x** (Spring Framework 6.1.x, Java 17+), tài liệu chính thức cảnh báo rằng IDE có thể sắp classpath khác với Maven, Gradle hoặc packaged JAR, dẫn đến không tìm thấy template mong đợi. Vì thế muốn sửa tận gốc phải kiểm tra **classpath của chính tiến trình đang lỗi**, không chỉ xem file trong IDE.

Mục tiêu của bài là phân biệt lỗi không tìm thấy view, template resource, fragment, engine và dependency; kiểm chứng vị trí template đã đóng gói; nhận diện tài nguyên trùng tên và sự khác biệt về order; chọn cách sửa có thể duy trì qua các môi trường.

## 2. Từ HTTP request đến file template: bốn tầng khác nhau

```text
HTTP GET /catalog/42
    |
    v
Spring MVC HandlerMapping
    |  tìm @GetMapping("/catalog/{id}") hoặc route tương ứng
    v
@Controller trả view name "catalog/detail"
    |  Model có product, id...
    v
Spring MVC ViewResolver
    |  chọn ThymeleafView / FreeMarkerView / ... phù hợp
    v
Template engine / TemplateResolver
    |  ví dụ Thymeleaf: classpath:/templates/ + catalog/detail + .html
    v
Resource / ClassLoader / Template loader
    |  tìm bytes thực tế trong classes directory hoặc JAR trên classpath
    v
Parse + evaluate template, model, fragment và trả HTTP response
```

Đường đi này thuộc trường hợp **Spring MVC trả tên view để render HTML**. Với `@RestController` hoặc `@ResponseBody`, giá trị `String` là body, không tự được Thymeleaf giải quyết. Với `redirect:` và `forward:`, Spring MVC xử lý prefix đặc biệt trước khi render view thường.

| Tầng | Ví dụ lỗi | Kiểm tra đúng tầng |
| --- | --- | --- |
| HTTP/handler mapping | 404 vì không có `GET /catalog/42` | Controller mapping, context path, `@RequestMapping`, method, security |
| Controller/view name | Trả `"catalog/detail.html"` trong khi suffix đã là `.html` | Giá trị return thực tế, `@Controller` vs `@RestController` |
| View/template resolver | Engine chưa cài, `prefix` hoặc `suffix` bị sửa | Bean resolvers, `spring.thymeleaf.*`, `view-names`, custom resolver order |
| Resource/classpath | File không vào artifact, trùng `templates/catalog/detail.html` trong JAR khác | ClassLoader URL(s), `BOOT-INF/classes`, nested dependency JAR, classpath index |
| Parse/render | Có file nhưng lỗi biểu thức/fragment/encoding | Root cause `TemplateInputException`, `TemplateProcessingException`, fragment expression |

**Không đồng nhất HTTP 404 với “Thymeleaf không tìm thấy template”.** Một request chưa được map thường là 404; khi route tồn tại và view không resolve/render được, lỗi có thể phát sinh trong bước render, thường dẫn tới HTTP 500. Security, custom error handler và view resolver fallback có thể làm status cụ thể khác đi.

## 3. Quy ước mặc định của các template engines trong Spring Boot

Spring Boot hỗ trợ auto-configuration cho Thymeleaf, FreeMarker, Groovy Templates và Mustache. Với cấu hình mặc định, nhiều engine tìm template trong `src/main/resources/templates`, nhưng **phần mở rộng file tùy engine**.

| Engine | Starter thường dùng | Mặc định vị trí/tên file | Controller thường trả |
| --- | --- | --- | --- |
| Thymeleaf | `spring-boot-starter-thymeleaf` | `classpath:/templates/catalog/detail.html` | `"catalog/detail"` |
| FreeMarker | `spring-boot-starter-freemarker` | `classpath:/templates/catalog/detail.ftlh` trong Boot 3.3 | `"catalog/detail"` |
| Mustache | `spring-boot-starter-mustache` | `classpath:/templates/catalog/detail.mustache` | `"catalog/detail"` |
| Groovy Templates | `spring-boot-starter-groovy-templates` | Đuôi tệp tùy cấu hình Groovy template | Tên view logic phù hợp |
| JSP | Servlet view resolver/container | Thường theo vị trí JSP được cấu hình cho WAR | Tên view, nhưng có hạn chế với embedded executable JAR |

Các giá trị Thymeleaf thường dùng trong Boot 3.3:

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.enabled=true
spring.thymeleaf.cache=true
spring.thymeleaf.check-template=true
spring.thymeleaf.check-template-location=true
```

Đây là các giá trị mặc định được **minh họa rõ để học**, không cần đưa nguyên khối vào dự án nếu chỉ muốn hành vi mặc định. `check-template-location` kiểm tra **vị trí thư mục template** có tồn tại hay không; nó không thay thế việc kiểm tra chính xác từng tệp view. `check-template` liên quan kiểm tra template khi resolve. Tắt các check để im cảnh báo có thể che lỗi cấu hình.

Trong FreeMarker, suffix mặc định của Boot 3.3 là **`.ftlh`**, không nên áp dụng `.html` của Thymeleaf cho mọi engine. Thuộc tính dùng để tùy biến bao gồm `spring.freemarker.template-loader-path`, `spring.freemarker.suffix`. Mustache dùng `spring.mustache.prefix` và `spring.mustache.suffix`. Đọc effective configuration của engine thực sự có trên classpath.

## 4. Vì sao controller trả một chuỗi mà template vẫn không được tìm?

Ví dụ đúng với Thymeleaf:

**`src/main/java/com/example/view/CatalogController.java`**

```java
package com.example.view;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class CatalogController {

    @GetMapping("/catalog")
    public String catalog(Model model) {
        model.addAttribute("product", "Java");
        return "catalog/detail";
    }
}
```

**`src/main/resources/templates/catalog/detail.html`**

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Catalog</title></head>
<body>
  <h1>CATALOG_FROM_APP</h1>
  <p th:text="${product}">fallback</p>
</body>
</html>
```

Với Thymeleaf mặc định, đường dẫn được resolve là:

```text
classpath:/templates/catalog/detail.html
```

Tại sao tên `"catalog/detail"` là đúng? Resolver ghép **prefix + view name + suffix**. Nếu code trả `"templates/catalog/detail"`, đường dẫn có thể trở thành `classpath:/templates/templates/catalog/detail.html`; nếu trả `"catalog/detail.html"` trong khi suffix `.html` còn bật, có thể thành `detail.html.html` hoặc bị engine xử lý đặc thù. Hãy dùng tên view logic nhất quán, không đoán.

**Lỗi dễ nhầm:**

```java
// @RestController => "catalog/detail" là response BODY, không render template.
@RestController
public class WrongCatalogController {
    @GetMapping("/wrong")
    public String wrong() {
        return "catalog/detail";
    }
}
```

Đoạn trên là minh họa **cách khai báo gây hiểu nhầm**, không phải một ví dụ cần cài vào ứng dụng thực tế. Đối với controller render view, dùng `@Controller` hoặc method xử lý view phù hợp; không gắn `@ResponseBody` vào method trả view name.

`return "redirect:/catalog"` tạo redirect và `return "forward:/catalog"` tạo forward theo cơ chế Spring MVC; không có nghĩa tìm các file `redirect.html` hoặc `forward.html` trong `templates`.

## 5. Phân biệt “không có resource” với “resource tồn tại nhưng render lỗi”

Các thông báo thường gặp có thể cho thấy tầng gây lỗi, nhưng **đừng kết luận chỉ từ dòng cuối của stack trace**.

| Triệu chứng / log (minh họa) | Tầng nghi vấn | Cách lần ra nguyên nhân |
| --- | --- | --- |
| `TemplateInputException: Error resolving template ...` | Engine không mở được template được yêu cầu | Kiểm tra view name, prefix, suffix, classpath, resolver |
| `template might not exist or might not be accessible` | Thymeleaf resource lookup hoặc resolver selection | Xem tên view đầy đủ, candidate path thực tế và exception cause |
| `TemplateProcessingException` | File có thể đã tải được, lỗi biểu thức/fragment/processor | Đọc nested cause, vị trí dòng/cột, model data |
| `Error resolving fragment` hoặc lỗi `th:replace` | Fragment/subtemplate không có hoặc fragment name sai | Kiểm tra fragment file, tên `th:fragment`, relative resolution |
| Cảnh báo `Cannot find template location` | Chưa tìm thấy thư mục prefix ở lúc khởi động | Kiểm tra packaging và `spring.thymeleaf.prefix`; không coi đây là kết luận về mọi view |
| 404 trước khi controller được gọi | Handler/path/security/routing | Kiểm tra URL, method, `@RequestMapping`, context path |
| Controller chạy nhưng trả body literal `"index"` | `@RestController`/`@ResponseBody` | Sửa loại controller khi muốn render view |
| Redirect đến login / 401 / 403 | Security filter chain | Kiểm tra security rules; chưa chắc là lỗi template |
| App chạy nhưng hiển thị phiên bản HTML cũ | Cache, template trùng tên, JAR cũ, reverse proxy | Xác định thực tế bytes và URL thắng classpath lookup |

Cách đọc stack trace:

1. Tìm **exception đầu tiên gắn với request** và **root cause** ở sâu bên trong.
2. Ghi lại view name, template name, fragment name, path và engine được nêu trong log.
3. Xác định controller đã được gọi bằng log/breakpoint.
4. Xác định file tương ứng có trong **artifact runtime**, không chỉ trong source tree.
5. Nếu file có thật nhưng lỗi vẫn tái hiện, chuyển sang kiểm tra thứ tự classpath và resolver configuration.

Một exception do lỗi biểu thức `${product.name}` trên model `null` không thể sửa bằng cách di chuyển tệp `index.html`; cần sửa model hoặc template expression.

## 6. Các lớp thứ tự không được đánh đồng

“Thứ tự” trong bài này có nhiều lớp quyết định, mỗi lớp giải quyết một vấn đề khác:

| Thứ tự | Quyết định | API/thành phần liên quan | Khi nào kiểm tra |
| --- | --- | --- | --- |
| Handler mapping order | Request vào controller nào? | Spring MVC `HandlerMapping` | Endpoint không chạy hoặc route trùng |
| View resolver order | Tên view được resolver nào xử lý? | `ViewResolver`, `Ordered` | Có nhiều engine, fallback hoặc resolver tùy chỉnh |
| Template resolver order | Engine tìm bản template nào trước? | Thymeleaf `ITemplateResolver`, `order`, `resolvablePatterns` | Có nhiều template resolvers/prefix hoặc nguồn filesystem |
| Resource loader/classpath order | Resource trùng đường dẫn ở classpath entry nào được chọn? | `ClassLoader.getResource(s)`, Spring `ResourceLoader` | IDE khác JAR, module/library trùng template |
| Build/packaging order | Tài nguyên được đóng gói ở đâu, dependency nào được thêm? | Gradle/Maven, `bootJar`, Boot Loader | Chạy JAR khác `bootRun` |
| Cache order/lifecycle | Renderer còn giữ bản template nào? | Template cache, restart/devtools | Source đã sửa nhưng response chưa đổi |

Ví dụ có **hai Thymeleaf TemplateResolver** với prefix khác nhau: resolver priority quyết định nguồn nào được hỏi trước. Nhưng trong **một resolver** dùng `classpath:/templates/`, nếu resource name trùng ở hai JAR, **classpath/resource lookup order** lại quyết định bản được thấy. Chỉnh Spring MVC `HandlerMapping.order` không giải quyết trường hợp có hai file `templates/catalog/detail.html` nằm trong hai JAR.

Tương tự, danh sách **static resource locations** như `classpath:/static/`, `classpath:/public/` dùng cho static files; nó **không phải thứ tự tìm template** của Thymeleaf trong `classpath:/templates/`.

## 7. Classpath: source path, runtime path và tài nguyên trùng tên

Trong cấu trúc Gradle/Maven thông thường:

```text
src/main/resources/templates/catalog/detail.html
        |
        v
build/resources/main/templates/catalog/detail.html    (Gradle thường dùng)
        |
        +--> bootRun / IDE: resources nằm trong classpath entries
        |
        +--> bootJar: BOOT-INF/classes/templates/catalog/detail.html
```

Khi JAR phụ thuộc cũng chứa:

```text
library-a.jar!/templates/catalog/detail.html
```

cùng một tên **resource tương đối trong classpath** là `templates/catalog/detail.html`. Nếu code/engine sử dụng lookup lấy **kết quả đầu tiên** (`ClassLoader.getResource`), chỉ một bản được dùng, dù nhiều bản tồn tại. `ClassLoader.getResources` có thể liệt kê nhiều URL để phục vụ chẩn đoán.

**Classpath không đồng nhất với hệ thống file source.** Một file trong thư mục `src/test/resources/templates` có thể tồn tại trong classpath khi test nhưng thường không được đóng gói vào production JAR; trái lại template từ dependency JAR có thể được thấy ở runtime mặc dù không nằm trong source của module chính.

Các kiểu resource thường gặp:

| Nguồn | Resource path trong runtime | Lưu ý |
| --- | --- | --- |
| Module chính khi `bootRun` | `build/resources/main/templates/...` hoặc output directory tương tự | Build tool có thể khác IDE |
| Module chính khi `java -jar` | `BOOT-INF/classes/templates/...` | Nằm bên trong executable JAR |
| Dependency JAR | Nested JAR trong `BOOT-INF/lib/` có `templates/...` | Cần inspect nested JAR hoặc liệt kê URL |
| Test resources | Test output/classpath | Không thể suy production JAR cũng có |
| Filesystem prefix | Ví dụ resolver `file:/.../templates/` | Phụ thuộc working directory, mount và quyền đọc |

Với Linux, tên `Detail.html` và `detail.html` khác nhau. Windows thường dùng filesystem không phân biệt hoa thường; code chạy tốt ở Windows có thể báo không tìm thấy tệp khi chuyển lên Linux/container. Dấu gạch chéo, dấu cách và ký tự Unicode cũng cần đối chiếu **đúng tên resource**.

## 8. Đặc điểm executable JAR và `classpath.idx` của Spring Boot

Executable Spring Boot JAR thường có cấu trúc:

```text
myapp.jar
├── META-INF/
├── org/springframework/boot/loader/
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/view/...
    │   ├── application.properties
    │   └── templates/catalog/detail.html
    ├── lib/
    │   ├── library-a.jar
    │   └── library-b.jar
    └── classpath.idx     (nếu được tạo)
```

Spring Boot Loader hỗ trợ các nested JAR thay vì phải giải nén toàn bộ dependencies. `BOOT-INF/classes` chứa classes/resources của ứng dụng; `BOOT-INF/lib` chứa dependencies.

Đáng chú ý, `BOOT-INF/classpath.idx` nếu có mô tả **thứ tự các nested library JAR được thêm vào classpath** khi chạy `java -jar` bằng Boot Loader. Tài liệu Spring Boot cho biết index này thường được plugin Maven/Gradle sinh ra; thứ tự trong index tương ứng với cách build tool xếp dependency classpath. **Index chỉ được Boot Loader dùng cho `java -jar`**, không được dùng khi chạy từ IDE hoặc bằng Gradle `bootRun`/Maven `spring-boot:run`.

Ví dụ mang tính mô tả:

```text
- "BOOT-INF/lib/library-b.jar"
- "BOOT-INF/lib/library-a.jar"
```

Nếu cả hai JAR có resource cùng đường dẫn, thay đổi dependency/order có thể đổi bản được tìm thấy. **Không được kết luận mọi lớp/tài nguyên luôn được chọn theo alphabet hoặc theo tên JAR**: phải xem index, classloader và resource loader thực tế của run đang lỗi. Với build reproducible, thứ tự entries trong index có thể được sắp xếp theo cơ chế của plugin; không nên dựa vào chi tiết tình cờ thay cho một nguồn template duy nhất.

Một khác biệt cực kỳ hữu ích để debug: `ClassLoader.getSystemClassLoader()` có thể **không truy cập được nested JAR resources như mong đợi** trong ứng dụng do Boot Loader khởi chạy. Trong mã chẩn đoán, ưu tiên `Thread.currentThread().getContextClassLoader()` hoặc resource loader mà framework đang dùng.

## 9. Bài thực hành Java 17 độc lập: cùng path, khác thứ tự thì khác kết quả

Ví dụ dùng **JDK 17+**, không cần Spring Boot. Chương trình tạo hai thư mục tạm thời chứa **cùng relative path** và dùng `URLClassLoader` với thứ tự khác nhau. Đây là bằng chứng trực tiếp về cơ chế lookup từ classpath entries được sắp xếp.

**Tệp `ClasspathOrderDemo.java`:**

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.List;

public class ClasspathOrderDemo {
    private static final String RESOURCE = "templates/catalog/detail.html";

    public static void main(String[] args) throws Exception {
        Path first = Files.createTempDirectory("templates-first-");
        Path second = Files.createTempDirectory("templates-second-");

        createTemplate(first, "FROM_FIRST");
        createTemplate(second, "FROM_SECOND");

        check(first, second);
        check(second, first);
    }

    private static void createTemplate(Path root, String text)
            throws IOException {
        Path file = root.resolve(RESOURCE);
        Files.createDirectories(file.getParent());
        Files.writeString(file, text, StandardCharsets.UTF_8);
    }

    private static void check(Path left, Path right) throws Exception {
        URL[] urls = {left.toUri().toURL(), right.toUri().toURL()};

        try (URLClassLoader loader = new URLClassLoader(urls, null)) {
            URL winner = loader.getResource(RESOURCE);
            List<URL> all = Collections.list(loader.getResources(RESOURCE));

            System.out.println("winner=" + read(winner));
            System.out.println("candidates=" + all.size());
        }
    }

    private static String read(URL resource) throws IOException {
        if (resource == null) {
            return "<missing>";
        }
        try (InputStream input = resource.openStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ClasspathOrderDemo.java
java ClasspathOrderDemo
```

**Stdout chính xác** với `URLClassLoader` và hai thư mục được tạo thành công:

```text
winner=FROM_FIRST
candidates=2
winner=FROM_SECOND
candidates=2
```

Tại lượt đầu, first là location ưu tiên; lượt sau đảo thứ tự nên second thắng. `getResources` cho biết **cả hai** resource đều có thật. Bài học quan trọng là “tìm thấy một resource” không chứng minh “chỉ có một resource”.

Đây là demo về cơ chế ClassLoader, **không đại diện cho mọi chi tiết trong Thymeleaf/Spring Boot**. Template engine có thể có nhiều resolvers hoặc cache, nhưng khi một bước resolution dựa vào classloader lookup first-match thì classpath order quyết định phiên bản được thấy.

## 10. Bài thực hành Spring Boot: view hoạt động khi đường đi đúng

Ví dụ MVC + Thymeleaf trên Java 21. Các file dưới đây tạo một ứng dụng đầy đủ trong một Gradle project có wrapper.

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
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/view/TemplateApplication.java`**

```java
package com.example.view;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TemplateApplication {

    public static void main(String[] args) {
        SpringApplication.run(TemplateApplication.class, args);
    }
}
```

Đặt `CatalogController.java` tại cùng package như mục 4. Tạo file Thymeleaf như mục 4. Nếu dùng thêm cấu hình, có thể đặt:

**`src/main/resources/application.properties`**

```properties
server.port=8080
```

Khởi động:

```bash
./gradlew bootRun
```

Sau đó:

```bash
curl -i -H 'Accept: text/html' http://localhost:8080/catalog
```

Với ứng dụng đơn giản này và cổng 8080 trống, response là HTTP 200 có chứa:

```text
CATALOG_FROM_APP
```

và text `Java` do model cung cấp. Các HTTP headers và HTML whitespace phụ thuộc renderer nên không ghi cố định toàn bộ response.

Từ ví dụ này có thể gây lỗi có kiểm soát:

- **Sai view name:** Đổi thành `return "catalog/unknown";` trong controller → route vẫn khớp, nhưng file `templates/catalog/unknown.html` không tồn tại.
- **Sai thư mục:** Chuyển `detail.html` sang `src/main/resources/static/catalog/detail.html` nhưng giữ controller và Thymeleaf prefix mặc định → template engine không tìm trong `static/`.
- **Sai suffix:** Cố định `spring.thymeleaf.suffix=.htm` nhưng file vẫn `.html` → resolver dự kiến file khác.
- **Thiếu engine:** Bỏ dependency Thymeleaf rồi cố render tên view → không thể kỳ vọng MVC tự render file HTML trong `templates` theo cơ chế Thymeleaf.
- **`@RestController`:** Đổi annotation của controller → trả literal string thay vì render HTML.

Chỉ thay **một biến tại một thời điểm** và restart để xác định nguyên nhân. Không dùng nhiều lỗi đồng thời vì sẽ làm stack trace và kết quả khó diễn giải.

## 11. Chẩn đoán classpath trực tiếp trong ứng dụng đang chạy

Một cách hữu ích là cho tiến trình thật liệt kê tất cả URL chứa resource name cần tìm. Với Thymeleaf mặc định và controller `return "catalog/detail"`, tên resource bên trong classpath là:

```text
templates/catalog/detail.html
```

**`src/main/java/com/example/view/TemplateResourceProbe.java`** — mẫu tích hợp cho ứng dụng Spring Boot phía trên:

```java
package com.example.view;

import java.net.URL;
import java.util.Collections;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TemplateResourceProbe {

    @Bean
    ApplicationRunner reportTemplateClasspath() {
        return args -> {
            String name = "templates/catalog/detail.html";
            ClassLoader loader =
                    Thread.currentThread().getContextClassLoader();

            URL winner = loader.getResource(name);
            List<URL> all = Collections.list(loader.getResources(name));

            System.out.println("template resource count=" + all.size());
            System.out.println("template first=" + winner);
            for (int i = 0; i < all.size(); i++) {
                System.out.println("candidate[" + i + "]=" + all.get(i));
            }
        };
    }
}
```

Đây là class cấu hình có thể biên dịch với dependencies bài thực hành; URL cụ thể không có stdout cố định vì mỗi runtime/OS khác nhau. Một ứng dụng mẫu chỉ có file trong module chính **thường** in `template resource count=1`. Nếu kết quả `count=0`, classloader này không tìm thấy resource theo tên đang kiểm tra; cần xác minh prefix/suffix hiệu lực và artifact. Nếu `count>1`, có resource trùng path và cần xác định tác nhân cung cấp từng URL.

Cẩn thận với kết luận: `getResource` mô phỏng classloader lookup, **không phải bằng chứng tuyệt đối rằng custom Thymeleaf TemplateResolver đang dùng cùng classloader/prefix**. Nếu đã cấu hình `FileTemplateResolver`, `StringTemplateResolver`, SpringResourceTemplateResolver có prefix khác hoặc nhiều resolvers, phải đối chiếu cả thiết lập resolver thật.

**Không dùng** `ClassLoader.getSystemClassLoader()` làm nguồn bằng chứng duy nhất khi chạy Boot executable JAR có nested dependencies. Dùng context classloader hoặc `ResourceLoader`/`ApplicationContext.getResources(...)` của Spring phù hợp với loader engine.

## 12. Khác nhau giữa chạy IDE, Gradle và executable JAR

| Cách chạy | Classpath thường gặp | Hệ quả khi tìm template |
| --- | --- | --- |
| IDE chạy `main` | IDE tự bố trí output resources của module và dependencies | Module hoặc JAR phụ thuộc có thể xuất hiện trước; order thay đổi khi chỉnh run configuration |
| Gradle `bootRun` | Gradle runtime classpath/output classes và resources | Thứ tự do Gradle cấu hình; có thể khác IDE |
| `./gradlew test` | Test classes/resources + main + dependencies | Test template có thể che resource production |
| `java -jar build/libs/...jar` | Boot Loader, `BOOT-INF/classes` và nested `BOOT-INF/lib` | Xét artifact thực và có thể sử dụng `classpath.idx` |
| Docker chạy packaged JAR | Về cơ bản theo artifact trong image | Có thể dùng JAR/build layer cũ hoặc mount/config khác |
| WAR trong servlet container | `WEB-INF/classes`, `WEB-INF/lib` và classloader của container | Thêm khác biệt về parent/child loader policy |

Tài liệu Spring Boot 3.3 nêu rõ: **đường chạy IDE có thể xếp classpath khác với Maven/Gradle/packaged JAR**. Nếu IDE báo thiếu template nhưng CLI chạy được, hãy thử cấu hình IDE để **output classes/resources của module ứng dụng đứng trước các dependency entries**, sau đó so sánh kết quả `TemplateResourceProbe` giữa hai cách chạy.

Điều đó không có nghĩa “bắt IDE phải giống JAR” là cách duy trì lâu dài khi có duplicate files. Nếu hai module cố ý xuất cùng `templates/catalog/detail.html`, hãy sửa ownership, namespace và packaging để chỉ có một source of truth rõ ràng.

## 13. Kiểm tra artifact đã đóng gói thật

Chỉ nhìn file trong project explorer không đủ. Với sample app từ mục 10, build:

```bash
./gradlew clean bootJar
```

`clean` ở đây là lệnh build của **bài thực hành trong project mẫu**; khi áp dụng cho dự án làm việc có thay đổi chưa lưu hoặc build cache quan trọng, chỉ chạy sau khi đã hiểu tác động. Để kiểm tra output JAR của ứng dụng mẫu, dùng tên file thực tế từ `build/libs`:

```bash
jar tf build/libs/template-demo-0.0.1-SNAPSHOT.jar
```

Tên `template-demo-0.0.1-SNAPSHOT.jar` là **minh họa** nếu đã cấu hình tên project tương ứng; trong dự án thật phải dùng filename do Gradle tạo. Trong danh sách entry, kiểm tra:

```text
BOOT-INF/classes/templates/catalog/detail.html
BOOT-INF/classes/com/example/view/TemplateApplication.class
BOOT-INF/classes/com/example/view/CatalogController.class
```

Nếu không thấy template trong `BOOT-INF/classes`, kiểm tra:

- File có thực sự nằm dưới `src/main/resources/templates` trong source set của module đang build không?
- Có cấu hình Gradle `processResources`/`sourceSets`/exclude nào lọc file không?
- Đang chạy đúng `bootJar`/artifact mới nhất hay một JAR cũ?
- Trong multimodule build, template thuộc module nào; resource ở library JAR nào?
- Trên Linux/container, tên và hoa thường có khớp không?

Dùng:

```bash
./gradlew processResources
./gradlew bootJar
```

để kiểm tra resource pipeline. Muốn biết dependency JAR nào chứa một resource trùng, cần xem nội dung JAR phụ thuộc (nested library file) hoặc dùng `getResources` trong runtime. `jar tf` trên **outer executable JAR** thường chỉ cho thấy `BOOT-INF/lib/library-a.jar`, không tự liệt kê từng entry *bên trong* library JAR đó.

Nếu application được đóng gói thành WAR, nhìn trong `WEB-INF/classes/templates/...` và JAR thư viện `WEB-INF/lib`, với lưu ý cách deploy có thể thay đổi classloader behavior.

## 14. Cấu hình Thymeleaf khi cần debug

Trong môi trường development, dùng cấu hình có chủ đích:

**`application-dev.properties`**

```properties
spring.thymeleaf.cache=false
logging.level.org.thymeleaf=DEBUG
logging.level.org.springframework.web.servlet.view=TRACE
```

Chạy sample với dev profile:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

`cache=false` giúp giảm yếu tố template cache khi sửa nội dung trong môi trường development; **nó không giải quyết path sai, classpath order sai hoặc thiếu dependency**. Không khuyến khích tắt cache toàn bộ ở production chỉ để che lỗi deploy.

Những thuộc tính cần kiểm tra đúng **effective values**:

| Thuộc tính | Mục đích | Dấu hiệu cấu hình sai |
| --- | --- | --- |
| `spring.thymeleaf.enabled` | Bật view resolution | `false` làm engine không nhận view như kỳ vọng |
| `spring.thymeleaf.prefix` | Vị trí base của template | Đổi sang classpath khác hoặc filesystem location |
| `spring.thymeleaf.suffix` | Đuôi file mặc định | Tìm `.htm` trong khi file `.html` |
| `spring.thymeleaf.check-template` | Kiểm tra template khi resolve | Tùy biến có thể ảnh hưởng fallback và thời điểm báo lỗi |
| `spring.thymeleaf.check-template-location` | Kiểm tra template location | Warning thư mục không tồn tại |
| `spring.thymeleaf.view-names` | Giới hạn tên view mà Thymeleaf xử lý | View `catalog/detail` có thể nằm ngoài pattern |
| `spring.thymeleaf.excluded-view-names` | Loại một số tên view | Resolver không chọn view mong đợi |
| `spring.thymeleaf.template-resolver-order` | Vị trí resolver trong chuỗi TemplateResolvers | Thứ tự khác dự kiến khi có nhiều resolver |

Trong Spring MVC, khi nhiều `ViewResolver` cùng tồn tại còn phải kiểm tra **order của Spring ViewResolvers** riêng. Khi nhiều Thymeleaf `ITemplateResolver` cùng tồn tại, kiểm tra **order/resolvable patterns/checkExistence** của từng template resolver. Chỉnh `spring.thymeleaf.template-resolver-order` để khắc phục một resource thiếu trên classpath là đổi sai tầng nếu chỉ có một resolver.

`--debug` của Spring Boot giúp hiện **Condition Evaluation Report** cho auto-configuration, hữu ích khi nghi không tạo Thymeleaf beans. Nó không tự in đầy đủ từng resource URL được chọn; kết hợp với `TemplateResourceProbe`.

## 15. Khi dùng nhiều template resolvers hoặc nhiều engine

Ứng dụng có thể kết hợp template nội bộ với templates của một thư viện/chủ đề (theme) hoặc nhiều engine. Khi đó có hai loại ưu tiên:

**Ví dụ logic** (mô tả cơ chế, không phải đoạn code cấu hình hoàn chỉnh):

```text
Thymeleaf TemplateResolver A: prefix=classpath:/templates-brand/
                            order=1
Thymeleaf TemplateResolver B: prefix=classpath:/templates/
                            order=2

controller returns "catalog/detail"
       |
       +--> hỏi A trước
       |       +--> nếu tìm được và được chọn: dùng template brand
       |
       +--> nếu A không xử lý/không tìm được và cho phép fallback
               +--> hỏi B
```

Điều kiện “cho phép fallback” quan trọng. Với Thymeleaf, resolver có thể đánh dấu template name thuộc phạm vi của nó, có hoặc không kiểm tra sự tồn tại trước khi trả resource. Một resolver trả candidate rồi lỗi mở file **có thể không tự chuyển sang resolver sau**, tùy cấu hình resolver. Khi muốn fallback đúng nghĩa, cần cấu hình điều kiện tồn tại, patterns và order được framework hỗ trợ, sau đó test cả trường hợp file có và không có.

Nếu dùng cả Thymeleaf và FreeMarker, chúng là những view technologies khác nhau và có thể cạnh tranh với một **logical view name**. Ở tầng MVC, kiểm tra các ViewResolver đang được đăng ký, thứ tự của chúng và `view-names` restrictions. Ở tầng resource lookup, kiểm tra file `.html` hay `.ftlh` tương ứng. **Không có một thứ tự classpath chung thay thế được việc thiết kế resolver priorities.**

Khi cần thiết kế plugin/theme có override templates, nên xây contract rõ: namespace view, custom prefix, fallback tests, và quan hệ version/dependency. Đừng dựa vào vị trí may rủi của JAR trong classpath để quyết định giao diện chính.

## 16. Chẩn đoán trong dự án đa module

Ví dụ:

```text
shop-app/
  src/main/resources/templates/orders/detail.html

shop-theme/
  src/main/resources/templates/orders/detail.html

shop-common/
  src/main/resources/templates/fragments/header.html
```

`shop-app` và `shop-theme` đều có `templates/orders/detail.html` → rủi ro duplicate resource. Nếu khi chạy IDE thư viện theme đứng trước output app, `getResource` có thể trả bản theme. Khi đóng gói JAR, vị trí và thứ tự do build/Boot Loader quyết định; hành vi có thể đảo.

Hướng xử lý:

1. Dùng `getResources("templates/orders/detail.html")` tại **runtime bị lỗi** để xác định số lượng và URL của candidate resources.
2. Xác nhận tên file trong `BOOT-INF/classes` hoặc nested library JAR.
3. Chọn **một owner cho view `orders/detail`**. Ví dụ chỉ app sở hữu view chính; theme dùng namespace `templates/theme/orders/detail.html` và resolver/routing công khai để chọn theme.
4. Nếu cần override hợp lệ, tạo **hai resolvers có order và chính sách fallback rõ ràng**. Test cả IDE, `bootRun` và packaged JAR.
5. Ngăn duplicate vô tình bằng cấu trúc package/module, resource naming convention và kiểm tra build/test phù hợp.

Resource naming theo namespace module thường bền vững hơn việc đặt tất cả view tên `index.html`, `detail.html` dưới thư mục `templates/` root. Một library có thể chứa fragment chia sẻ ở `templates/shared/fragments/...` mà không va chạm với view riêng của app.

**Không nên ép classpath order bằng cách đổi tên JAR `aaa-theme.jar`** hoặc kỳ vọng alphabet sẽ luôn quyết định ưu tiên. Điều đó dễ hỏng khi build plugin, launcher hoặc dependency graph thay đổi.

## 17. Phân tích những tình huống dễ đánh lạc hướng

### 17.1. `templates/index.html` và trang chủ `/`

Template `index` có thể làm **welcome page** khi không có static `index.html` ưu tiên và Spring Boot nhận diện template engine. Nhưng nếu ứng dụng đã khai báo `@GetMapping("/")`, route này có thể quyết định view khác. Thiếu welcome page trên `/` không đồng nghĩa thiếu mọi template trong hệ thống.

Phân biệt:

```text
src/main/resources/static/index.html      => static resource/welcome candidate
src/main/resources/templates/index.html   => template source/welcome candidate
```

Static resource handling và template resolution có cơ chế riêng. Chuyển template vào `static/` chỉ để tránh `TemplateInputException` có thể làm mất khả năng xử lý biểu thức Thymeleaf, thậm chí công bố HTML chưa xử lý đúng cách.

### 17.2. File có mặt nhưng Thymeleaf báo lỗi fragment

Ví dụ template `catalog/detail.html` có:

```html
<header th:replace="~{fragments/header :: topbar}"></header>
```

Nếu `templates/fragments/header.html` không có fragment tên `topbar`, engine đã có thể mở được `catalog/detail.html` nhưng vẫn thất bại khi render. Hãy kiểm tra **nested template name** và fragment declaration:

```html
<div th:fragment="topbar">Navigation</div>
```

Đoạn là **ví dụ fragment**; muốn dùng phải đặt nó trong `templates/fragments/header.html`, có namespace Thymeleaf và cấu trúc HTML tương ứng. Không đổi classpath order khi lỗi thực tế là fragment name.

### 17.3. `@Controller` có đường dẫn sai nhưng file template đúng

URL request `/catalog` có thể không đến method vì servlet context path `/shop` hoặc route đặt `/api/catalog`. Controller không chạy nghĩa là template path không phải nghi phạm đầu tiên. Thử đúng URL ngoài, method và `Accept`; xem Spring Security filter/redirect nếu có.

### 17.4. Cache và artifact cũ

Sửa source template trong IDE chưa chắc làm resource output directory hoặc JAR đang chạy thay đổi. Nếu `spring.thymeleaf.cache=true`, engine có thể tiếp tục dùng bản đã parse trong process. Kiểm tra theo thứ tự: đúng process/port, đúng artifact, đúng resource URL, cache, browser/reverse-proxy cache. Restart và build fresh trong môi trường kiểm thử, không xóa mọi cache một cách vô điều kiện tại production.

## 18. Kiểm thử để phát hiện lỗi trước khi deploy

Một integration test nên chứng minh **HTML thực sự được render**, không chỉ chứng minh file nằm trong source.

**`src/test/java/com/example/view/TemplateHttpTest.java`** trong sample từ mục 10:

```java
package com.example.view;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TemplateHttpTest {

    @Autowired
    private TestRestTemplate client;

    @Test
    void catalogTemplateIsRendered() {
        ResponseEntity<String> response =
                client.getForEntity("/catalog", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("CATALOG_FROM_APP");
        assertThat(response.getBody()).contains("Java");
    }
}
```

Chạy:

```bash
./gradlew test
```

Test cần sample không bật security bắt đăng nhập tại `/catalog` và không đổi context path. Vì dùng `RANDOM_PORT`, nó tạo HTTP server thật trên cổng khả dụng và xác minh body đã qua view rendering. Nếu đang chạy trong một môi trường có `@SpringBootTest` config đặc thù, phải áp dụng profile/dependency phù hợp để test có ý nghĩa.

**Để bắt lỗi classpath order**, còn cần kiểm tra **packaged JAR**. Test ở IDE chỉ đánh giá test runtime classpath; nó không bảo đảm `java -jar` sẽ thấy cùng thứ tự. Một smoke test chạy executable JAR và gọi `/catalog` có thể phát hiện khác biệt đóng gói. Dùng `TemplateResourceProbe` nếu response mismatch, hoặc thêm kiểm tra duplicate template trên runtime classpath trong môi trường test có chủ đích.

Không cần giữ probe làm logging thường trực trong production: liệt kê URL tài nguyên có thể bộc lộ chi tiết đường dẫn hệ thống. Chỉ bật dưới dev/test hoặc dùng diagnostic endpoint đã được bảo vệ.

## 19. Quy trình chẩn đoán ngắn gọn có thể áp dụng ngay

Khi gặp lỗi “template not found”, làm lần lượt:

1. **Xác định lỗi HTTP:** URL, status, redirect, controller có được gọi không, đúng profile/process/port không.
2. **Ghi view name thực tế:** controller là `@Controller`, return value chính xác là gì, có `redirect:`/`forward:`/`@ResponseBody` không.
3. **Xác định engine và resolver:** Thymeleaf/FreeMarker/Mustache? Dependency starter có mặt không? Các view resolvers và template resolvers đang hoạt động?
4. **Tính expected resource path:** với Thymeleaf mặc định `catalog/detail` → `classpath:/templates/catalog/detail.html`; với FreeMarker cần kiểm tra suffix `.ftlh`.
5. **Đối chiếu classpath runtime:** dùng context classloader `getResources`, Spring `ResourceLoader`, và inspect output resources/JAR đúng cách.
6. **Tìm duplicates và order:** nếu có nhiều URL cho cùng path, so sánh IDE, `bootRun`, test và `java -jar`; xem `BOOT-INF/classpath.idx` khi có.
7. **Kiểm tra nested cause:** nếu resource tồn tại, xem fragment, parse/expression/encoding/model và cache.
8. **Sửa đúng tầng:** đổi view name, prefix, source set, packaging, resolver order hoặc ownership của duplicate resource; thêm regression test thích hợp.

| Chứng cứ | Kết luận hợp lý | Bước tiếp theo |
| --- | --- | --- |
| Controller không chạy | Chưa cần xử lý template | Debug route, security, context path |
| Controller trả literal string body | Không đi qua view resolution | Kiểm tra annotation/API response |
| Engine thiếu/disabled | Resolver không sẵn sàng | Sửa dependencies/config |
| `getResources(...)=0` | Context classloader hiện không thấy resource path đó | Kiểm tra expected path, output resources, JAR |
| `getResources(...)>1` | Trùng resource path | Xác định owner và URL winner/order |
| JAR có app template nhưng IDE lấy template dependency | Classpath runtime khác thứ tự/nguồn | Ưu tiên output app ở IDE; loại duplicate dài hạn |
| Có resource đúng nhưng lỗi fragment | Không phải “file gốc không tồn tại” | Sửa nested template/fragment |
| `bootRun` PASS, `java -jar` FAIL | Cần kiểm tra packaging và Boot Loader classpath | Inspect artifact, dependency, index, smoke test |
| Chỉ sau chỉnh template mới gặp lỗi | Có thể cache hoặc file output chưa cập nhật | So sánh actual bytes, restart test |

## 20. Những hiểu nhầm và câu hỏi tự kiểm tra

**Hiểu nhầm 1:** “`src/main/resources/templates/x.html` đang tồn tại thì chắc chắn runtime thấy.” File có thể chưa được process, bị exclude, nằm ở module/test resource khác hoặc không thuộc artifact đang chạy.

**Hiểu nhầm 2:** “`ClassLoader.getResource` tìm thấy một bản thì không có bản trùng.” Không đúng; cần `getResources` để liệt kê nhiều URL.

**Hiểu nhầm 3:** “Thứ tự classpath giống nhau giữa IDE, Gradle và executable JAR.” Không được bảo đảm. Boot docs trực tiếp cảnh báo khác biệt này.

**Hiểu nhầm 4:** “Thứ tự `ViewResolver` quyết định thứ tự JAR trên classpath.” Hai lớp order hoàn toàn riêng; phải xác định đang lỗi ở tầng nào.

**Hiểu nhầm 5:** “`@RestController` trả `"catalog/detail"` sẽ render HTML.” Không; đó là response body literal.

**Hiểu nhầm 6:** “Template engine nào cũng tìm file `.html`.” Boot 3.3 FreeMarker mặc định `.ftlh`, Mustache `.mustache`; mỗi engine có cấu hình riêng.

**Hiểu nhầm 7:** “Tắt cache, `check-template`, hoặc warning sẽ sửa missing template.” Không; có thể chỉ che lỗi hoặc làm thời điểm lỗi thay đổi.

**Hiểu nhầm 8:** “Cứ thêm `index.html` vào `static/` là giải quyết mọi lỗi template.” Static resource và server-side template là hai tầng khác nhau.

**Hiểu nhầm 9:** “`Classpath.idx` luôn quyết định IDE classpath.” Spring Boot chỉ dùng classpath index cho đường chạy `java -jar` theo Boot Loader; IDE và `bootRun` không dùng nó.

**Câu hỏi ôn tập:**

1. Controller trả `"catalog/detail"` với Thymeleaf mặc định; expected classpath path là gì? Nếu file nằm dưới `static/`, điều gì thay đổi?
2. Vì sao `ClassLoader.getResources("templates/catalog/detail.html")` hữu ích hơn `getResource` khi nghi duplicate template?
3. `@RestController` và `@Controller` khác nhau thế nào khi method trả `String`?
4. Vì sao cùng repo có thể chạy tốt với `bootRun` nhưng fail từ executable JAR, hoặc ngược lại?
5. `BOOT-INF/classes`, `BOOT-INF/lib`, `BOOT-INF/classpath.idx` khác trách nhiệm thế nào?
6. Khi nào cần kiểm tra TemplateResolver order, và khi nào cần kiểm tra runtime classpath order?
7. `TemplateInputException` có luôn nghĩa là file gốc không tồn tại không? Hãy nêu trường hợp lỗi fragment hoặc resource access khác.
8. Bạn sẽ viết test gì để biết template được **render thật qua HTTP**, và thêm kiểm chứng nào để bắt khác biệt giữa test classpath và packaged JAR?

**Nguyên tắc vận hành:** đặt template đúng thư mục và đúng namespace, để view name phản ánh rõ path logic, tránh trùng tài nguyên trên classpath, và luôn kiểm chứng trên **cách chạy phát sinh lỗi**. Khi file tồn tại nhưng không hiển thị đúng, trước tiên phân biệt handler, view resolver, template resolver và resource loader; từ đó mới chọn cách sửa.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Servlet Web Applications, phần Template Engines và lưu ý thứ tự classpath IDE: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Boot — Nested JARs và Classpath Index: https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html
- Spring Framework — MVC View Resolvers: https://docs.spring.io/spring-framework/reference/web/webmvc-view/mvc-viewresolver.html
- Thymeleaf + Spring integration: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
- Java 17 `ClassLoader#getResources`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
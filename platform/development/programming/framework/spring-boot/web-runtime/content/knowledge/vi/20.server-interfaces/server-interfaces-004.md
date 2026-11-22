# Thymeleaf, thư mục templates và cấu hình bộ nhớ đệm mẫu trong Spring Boot

**Phạm vi:** Spring Boot web-runtime → Giao diện máy chủ. Bài này giải thích Thymeleaf và cơ chế render HTML phía server, cách Spring Boot phân giải view qua thư mục `templates`, cấu hình `spring.thymeleaf.*`, cache khi phát triển và production, những lỗi thường gặp và cách kiểm tra. Ví dụ hoàn chỉnh dùng **Java 17+, Spring Boot 3.5.0, Spring MVC, Maven**; Spring WebFlux được đối chiếu riêng để tránh lẫn hai web stack.

## 1. Thymeleaf là gì?

**Thymeleaf** là template engine Java, thường được dùng để tạo **HTML phía server (server-side rendering, SSR)** từ một file HTML mẫu kết hợp với dữ liệu của request hiện tại. Một template chứa cấu trúc trang và các thuộc tính `th:*`; controller đưa dữ liệu vào Spring `Model`; Thymeleaf xử lý biểu thức trước khi gửi HTML cuối cho browser.

Ví dụ người dùng gọi `GET /catalog?q=java`. Controller nhận query parameter, lọc một danh sách, thêm `q`, `products`, `requestCount` vào `Model`, rồi trả về tên view `catalog`. View resolver tìm `classpath:/templates/catalog.html`. Thymeleaf lấy template (từ cache nếu có), đánh giá các thuộc tính `th:text` và `th:each` bằng **model của request này**, rồi gửi response `text/html`.

~~~text
GET /catalog?q=java
        │
        ▼
Spring MVC DispatcherServlet
        │
        ▼
@Controller + Model
  q="java", items=[...], requestCount=...
        │
   return "catalog"
        │
        ▼
ThymeleafViewResolver / SpringTemplateEngine
        │
        ├─ logical name "catalog"
        ├─ template location "classpath:/templates/catalog.html"
        ├─ template cache: template đã parse nếu bật
        └─ evaluate th:* trên model của request hiện tại
        │
        ▼
HTTP 200, Content-Type: text/html, body HTML đã render
~~~

Phân biệt rõ:

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| **Template** | File nguồn có chỗ thay thế dữ liệu | `templates/catalog.html` |
| **Model** | Dữ liệu Java cho lần render | `model.addAttribute("name", "Lan")` |
| **Logical view name** | Tên controller trả về để hệ thống tìm template | `return "catalog";` |
| **ViewResolver/TemplateEngine** | Tìm, parse và xử lý template | `ThymeleafViewResolver` / `SpringTemplateEngine` |
| **HTML response** | HTML đã render gửi cho browser | `<h1>Lan</h1>` |
| **Template cache** | Tái sử dụng template representation đã parse | `spring.thymeleaf.cache=true` |

Một template có thể được lưu cache mà dữ liệu vẫn khác nhau theo request. **Template cache không mặc nhiên cache toàn bộ HTML response có tên người dùng, giỏ hàng hoặc quyền truy cập.**

### So sánh với static file và JSON API

- File `src/main/resources/static/css/site.css` do static resource handler phục vụ tại URL `/css/site.css`. Thymeleaf không cần xử lý file này.
- File `src/main/resources/templates/catalog.html` thông thường **không có URL public trực tiếp**; phải được controller hoặc router chọn làm view.
- `@RestController` trả object thường được serialize thành JSON qua message converter. Với `@RestController` trả `"catalog"`, kết quả thường là chuỗi literal `catalog` trong body, **không render `catalog.html`**.
- Một file `static/index.html` vẫn là HTML, nhưng server thường gửi nội dung gốc; các thuộc tính `th:text` đặt ở đó **không tự được chạy**.

Thymeleaf phù hợp cho form, dashboard, trang quản trị và các trang SSR. Nó có thể cùng tồn tại với CSS/JS và REST API, không bắt buộc mọi tương tác đều reload trang.

## 2. Thư mục `templates` mặc định và đường dẫn file

Trong project Spring Boot dùng Maven/Gradle convention, nơi lưu view thường là:

~~~text
src/main/resources/templates/
~~~

Khi đóng gói executable JAR, nội dung này nằm trên application classpath (thường dưới `BOOT-INF/classes/templates/`). Spring Boot 3.5 mặc định có:

~~~properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.mode=HTML
spring.thymeleaf.encoding=UTF-8
~~~

Chúng là **giá trị mặc định**: không cần viết vào file cấu hình nếu bạn chấp nhận convention.

Một số phép ánh xạ:

| Java controller trả về | Thymeleaf tìm file |
| --- | --- |
| `return "home";` | `classpath:/templates/home.html` |
| `return "catalog";` | `classpath:/templates/catalog.html` |
| `return "catalog/list";` | `classpath:/templates/catalog/list.html` |
| `return "admin/dashboard";` | `classpath:/templates/admin/dashboard.html` |

Công thức:

~~~text
physical template path = prefix + logicalViewName + suffix

"classpath:/templates/" + "catalog/list" + ".html"
= "classpath:/templates/catalog/list.html"
~~~

**Đừng trả `"templates/catalog.html"` từ controller** khi muốn render `templates/catalog.html` bằng cấu hình mặc định: nó khiến resolver tìm sai path. Và đừng coi `GET /templates/catalog.html` là endpoint tự động có sẵn.

Nếu bạn đổi:

~~~properties
spring.thymeleaf.prefix=classpath:/ui/
~~~

thì `return "catalog";` tìm `src/main/resources/ui/catalog.html`. Tất cả template và fragments cùng resolver cũng phải được tổ chức lại đúng prefix. Property `spring.web.resources.static-locations` dành cho static resources và **không thay thế** `spring.thymeleaf.prefix`.

### Cây thư mục cho ví dụ chạy được

~~~text
template-demo/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/templatedemo/
   │  ├─ TemplateDemoApplication.java
   │  └─ CatalogController.java
   └─ resources/
      ├─ application.properties
      ├─ application-dev.properties
      ├─ application-prod.properties
      ├─ messages.properties
      ├─ templates/
      │  ├─ catalog.html
      │  └─ fragments/
      │     └─ common.html
      └─ static/
         └─ css/site.css
~~~

Template nằm tại `templates`; fragments cũng là template con; stylesheet nằm tại `static` và được phục vụ bởi handler khác. Không dùng `src/main/webapp` cho app Boot executable JAR vì cách đóng gói và classpath có thể bỏ qua thư mục webapp truyền thống.

## 3. View resolution: `@Controller`, `@RestController` và tên view

Trong **Spring MVC/Servlet**, `DispatcherServlet` tìm handler cho request. Nếu handler là `@Controller` trả `String` mà không có `@ResponseBody`, Spring có thể hiểu return value là **logical view name**.

~~~java
@Controller
class GreetingController {
    @GetMapping("/hello")
    String hello(Model model) {
        model.addAttribute("name", "Lan");
        return "hello"; // sẽ tìm templates/hello.html
    }
}
~~~

Đây là **đoạn minh họa**, chưa gồm imports hay project. Nếu đổi thành `@RestController`, Java String có thể trở thành **response body trực tiếp**. Một view name có prefix đặc biệt `redirect:/hello` là chỉ thị redirect; `forward:/path` là dispatch server-side trong MVC. Chúng không tương đương tên template.

**Quy trình tìm lỗi khi không render:** xác định handler nhận URL, kiểm tra `@Controller`, tên view trả về, xem prefix/suffix và file thực sự có trên classpath, sau đó mới xem cache. Không chữa lỗi tìm file bằng cách tắt template cache.

## 4. Bộ cấu hình Thymeleaf cần nhớ

Các thuộc tính Spring Boot 3.5.x quan trọng:

| Property | Mặc định | Công dụng |
| --- | --- | --- |
| **`spring.thymeleaf.cache`** | **`true`** | Cache template đã được resolver/engine xử lý cấu trúc |
| `spring.thymeleaf.prefix` | `classpath:/templates/` | Đường dẫn gốc của template |
| `spring.thymeleaf.suffix` | `.html` | Đuôi file |
| `spring.thymeleaf.mode` | `HTML` | Template mode |
| `spring.thymeleaf.encoding` | `UTF-8` | Encoding file template |
| `spring.thymeleaf.enabled` | `true` | Bật integration view resolution |
| `spring.thymeleaf.check-template` | `true` | Kiểm tra sự tồn tại khi resolve |
| `spring.thymeleaf.check-template-location` | `true` | Kiểm tra vị trí template |
| `spring.thymeleaf.view-names` | không đặt mặc định | Chọn view name Thymeleaf được xét |
| `spring.thymeleaf.excluded-view-names` | không đặt mặc định | View names bị loại khỏi Thymeleaf resolver |
| `spring.thymeleaf.template-resolver-order` | không đặt mặc định | Thứ tự resolver khi có nhiều resolver |

**Đừng nhầm:** `check-template-location=true` không bảo đảm mọi file mà controller trả tên đều tồn tại. Nó kiểm tra location theo phạm vi cấu hình. Tên view sai vẫn có thể dẫn đến render error (thường HTTP 500 khi controller đã khớp nhưng không có view render thành công).

Nếu không cần tùy chỉnh, **để các giá trị mặc định**. Đổi prefix/suffix hoặc view names chỉ khi bạn biết ứng dụng có quy ước thư mục riêng hoặc nhiều template engines cùng tồn tại.

## 5. Ví dụ Spring Boot MVC hoàn chỉnh (Java 17)

Ví dụ tự chạy, không cần DB. Trang `GET /catalog` dùng Thymeleaf với danh sách giả lập, input tìm kiếm, fragment header, message bundle và CSS. `requestCount` tăng theo từng HTTP request để kiểm tra rằng template cache **không giữ dữ liệu model cũ**.

### 5.1. File `pom.xml`

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
  <artifactId>template-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

Starter Thymeleaf cung cấp thư viện Thymeleaf và integration với Spring theo bộ phiên bản do Spring Boot quản lý. Không cần viết `@Bean TemplateEngine` thủ công trong bài cơ bản.

### 5.2. File `src/main/java/com/example/templatedemo/TemplateDemoApplication.java`

~~~java
package com.example.templatedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TemplateDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TemplateDemoApplication.class, args);
    }
}
~~~

### 5.3. File `src/main/java/com/example/templatedemo/CatalogController.java`

~~~java
package com.example.templatedemo;

import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class CatalogController {
    private static final List<String> ITEMS =
            List.of("Java", "Spring Boot", "Thymeleaf", "Docker");

    private final AtomicLong requests = new AtomicLong();

    @GetMapping("/catalog")
    public String catalog(
            @RequestParam(defaultValue = "") String q,
            Model model) {
        String needle = q.strip().toLowerCase(Locale.ROOT);
        List<String> filtered = ITEMS.stream()
                .filter(item -> item.toLowerCase(Locale.ROOT)
                        .contains(needle))
                .toList();

        model.addAttribute("q", q);
        model.addAttribute("items", filtered);
        model.addAttribute("requestCount", requests.incrementAndGet());
        return "catalog";
    }
}
~~~

`q.strip()` và `Stream.toList()` có sẵn trong Java 17+. `AtomicLong` chỉ đếm request trong **một JVM process**, reset khi restart và không đồng bộ giữa replicas; đừng dùng làm analytics production. Nó giúp thấy dữ liệu model được tạo mới trên mỗi request.

### 5.4. File `src/main/resources/templates/catalog.html`

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title th:text="#{catalog.title}">Danh mục</title>
  <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
  <header th:replace="~{fragments/common :: banner}">
    Header mẫu sẽ được thay thế.
  </header>

  <main>
    <h1 th:text="#{catalog.title}">Danh mục sản phẩm</h1>

    <form th:action="@{/catalog}" method="get">
      <label for="q">Tìm tên:</label>
      <input id="q" name="q" type="search" th:value="${q}">
      <button type="submit">Tìm kiếm</button>
    </form>

    <p>Số lần request trong JVM:
      <strong th:text="${requestCount}">0</strong>
    </p>

    <ul>
      <li th:each="item : ${items}" th:text="${item}">
        Sản phẩm mẫu
      </li>
    </ul>

    <p th:if="${#lists.isEmpty(items)}">Không có kết quả phù hợp.</p>
  </main>
</body>
</html>
~~~

Khi server render, `th:text` thay nội dung mẫu của phần tử. `th:each` tạo nhiều `li`. `th:if` có thể bỏ phần tử nếu điều kiện sai. `@{/css/site.css}` tạo URL theo context path (hữu ích khi deploy ở `/shop`). `th:action="@{/catalog}"` giúp form gửi đúng URL; form GET chỉ dùng query parameter, không cần CSRF token cho request đọc trong ví dụ.

### 5.5. File `src/main/resources/templates/fragments/common.html`

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <header th:fragment="banner">
    <nav aria-label="Điều hướng">
      <a th:href="@{/catalog}">Catalog</a>
    </nav>
  </header>
</body>
</html>
~~~

`th:replace="~{fragments/common :: banner}"` tìm fragment `banner` trong `templates/fragments/common.html` và thay **toàn bộ** phần tử host. `th:insert` sẽ chèn fragment **vào bên trong host**, có thể tạo HTML lồng thẻ không mong muốn nếu dùng tùy tiện. Việc đặt fragments trong một file dưới `templates` giúp tái sử dụng header/footer/navigation.

### 5.6. File `src/main/resources/messages.properties`

~~~properties
catalog.title=Danh mục công nghệ
~~~

`#{catalog.title}` lấy giá trị trong message bundle theo locale. Khi làm giao diện đa ngôn ngữ, thêm `messages_vi.properties`, `messages_en.properties` và cấu hình locale resolver/chiến lược dựa trên request. **Message bundle caching khác với Thymeleaf template cache.**

### 5.7. File `src/main/resources/static/css/site.css`

~~~css
body {
  font-family: system-ui, sans-serif;
  margin: 2rem auto;
  max-width: 44rem;
  line-height: 1.5;
}
h1 { color: #245c8a; }
li { padding: 0.25rem 0; }
~~~

File CSS này được Spring phục vụ như **static resource** tại `/css/site.css`. Không cần thêm controller lấy CSS. Đặt CSS vào `templates` chỉ để theo cùng HTML sẽ làm URL static sai trong cấu hình thông thường.

### 5.8. Ba file cấu hình

**`src/main/resources/application.properties`:**

~~~properties
spring.application.name=template-demo
spring.thymeleaf.encoding=UTF-8
~~~

**`src/main/resources/application-dev.properties`:**

~~~properties
# Phát triển: thay đổi template có thể được đọc lại.
spring.thymeleaf.cache=false
~~~

**`src/main/resources/application-prod.properties`:**

~~~properties
# Sản xuất: true vốn là mặc định, đặt rõ để kiểm tra.
spring.thymeleaf.cache=true
~~~

Profile chỉ hiệu lực khi được **kích hoạt**. Nếu chạy không chỉ định `dev` hay `prod`, thuộc tính mặc định của Thymeleaf cache là **true**, trừ khi dependency DevTools hoặc nguồn cấu hình khác làm thay đổi effective property.

### 5.9. Chạy và kiểm tra bằng browser/curl

Tại thư mục project, cần JDK 17+ và Maven:

~~~bash
java -version
mvn spring-boot:run -Dspring-boot.run.profiles=dev
~~~

Trong Windows PowerShell, nếu tham số `-Dspring-boot.run.profiles=dev` bị shell tách sai, đặt cả tham số trong dấu ngoặc kép. Mở browser `http://localhost:8080/catalog`. Trang có tiêu đề **Danh mục công nghệ**, bốn mục **Java, Spring Boot, Thymeleaf, Docker** và số đếm request.

Thử:

~~~bash
curl -i "http://localhost:8080/catalog?q=java"
curl -i "http://localhost:8080/catalog?q=not-found"
curl -i "http://localhost:8080/css/site.css"
curl -i "http://localhost:8080/templates/catalog.html"
~~~

Quan sát:
1. `/catalog?q=java` thường trả **200 OK**, body HTML và phần tử danh sách chỉ còn **Java**.
2. `/catalog?q=not-found` trả HTML có dòng **Không có kết quả phù hợp.**
3. `/css/site.css` trả CSS (thường **200 OK**) qua static resource handler.
4. `/templates/catalog.html` không phải public route của template; với project này thường **404 Not Found**.
5. Refresh `/catalog` nhiều lần làm `requestCount` tăng. Nó **cũng tăng khi chạy profile prod với cache=true** vì controller tạo model mới cho mỗi request.

Chỉ diễn giải body và status trong phạm vi project ví dụ, không khẳng định mọi HTTP header/whitespace luôn giống nhau ở mọi container hay sau khi thêm Spring Security/proxy.

Kiểm tra file đã đóng gói bằng Maven:

~~~bash
mvn clean package
jar tf target/template-demo-0.0.1-SNAPSHOT.jar
~~~

Trong danh sách entry, cần tìm `BOOT-INF/classes/templates/catalog.html`, `BOOT-INF/classes/templates/fragments/common.html`, `BOOT-INF/classes/static/css/site.css` và `BOOT-INF/classes/messages.properties`.

Chạy JAR với production profile:

~~~bash
java -jar target/template-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=prod
~~~

Sau khi build, sửa file nguồn `src/main/resources/templates/catalog.html` **không tự thay nội dung trong JAR đã đóng gói**. Cần build/deploy artifact mới; đặt `cache=false` không giúp một JAR cũ tự đọc tệp nguồn từ nơi khác.

## 6. Các biểu thức Thymeleaf cần biết

| Biểu thức | Vai trò | Ví dụ |
| --- | --- | --- |
| `${...}` | Biến trong Model/context | `th:text="${name}"` |
| `*{...}` | Thuộc tính trên object đã chọn bởi `th:object` | `th:field="*{email}"` |
| `#{...}` | Giá trị trong message bundle | `th:text="#{catalog.title}"` |
| `@{...}` | Xây URL theo context path và query | `th:href="@{/catalog(q=${q})}"` |
| `~{...}` | Lấy fragment/template | `th:replace="~{fragments/common :: banner}"` |

Các thuộc tính thường dùng:
- `th:text` viết nội dung như **text được HTML-escaped**.
- `th:utext` viết HTML **không escaped**; không dùng với dữ liệu không đáng tin.
- `th:each` lặp danh sách.
- `th:if` và `th:unless` điều kiện hiển thị.
- `th:href`, `th:src`, `th:action` tạo URL.
- `th:fragment`, `th:replace`, `th:insert` tổ chức trang theo fragments.
- `th:object` và `th:field` hỗ trợ form model binding của Spring.
- `th:errors` và `#fields.hasErrors(...)` dùng khi có validation errors được controller đưa vào model.

**XSS:** với chuỗi từ người dùng `<script>alert(1)</script>`, `th:text` chuyển ký tự HTML đặc biệt thành escaped text thay vì cho trình duyệt diễn dịch làm script. `th:utext` chỉ phù hợp khi nội dung HTML đã được tin cậy/sanitized rõ ràng. Không coi tính năng template là thay thế quy tắc escape theo ngữ cảnh (HTML, JavaScript, URL).

~~~html
<p th:text="${comment}">Comment sẽ được escape.</p>
<!-- Chỉ dùng sau khi xử lý an toàn từ nguồn đáng tin. -->
<div th:utext="${trustedHtml}">HTML có thể hiển thị thật.</div>
~~~

`th:if="${isAdmin}"` chỉ ẩn/hiện giao diện, không phải authorization của API. Controller/service phải kiểm tra quyền thật.

## 7. Form binding và validation (ví dụ tích hợp, không thuộc project chạy mục 5)

Spring MVC + Thymeleaf có thể bind form vào DTO qua `th:object`, `th:field`, `@ModelAttribute`, `@Valid` và `BindingResult`. Để chạy ví dụ này, cần thêm `spring-boot-starter-validation`, DTO `ProfileForm` phù hợp, imports và controller theo ứng dụng; phần dưới chỉ minh họa quan hệ.

~~~java
@GetMapping("/profile/edit")
String edit(Model model) {
    model.addAttribute("profileForm", new ProfileForm());
    return "profile-edit";
}

@PostMapping("/profile/edit")
String save(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "profile-edit";
    }
    // Validate authorization và lưu dữ liệu theo nghiệp vụ.
    return "redirect:/profile";
}
~~~

~~~html
<form th:action="@{/profile/edit}" th:object="${profileForm}" method="post">
  <label for="email">Email</label>
  <input id="email" th:field="*{email}" type="email">
  <span th:if="${#fields.hasErrors('email')}"
        th:errors="*{email}">Email không hợp lệ</span>
  <button type="submit">Lưu</button>
</form>
~~~

`BindingResult` phải đặt **ngay sau** model attribute mà nó mô tả trong signature của handler. `th:object` phải trỏ đúng một object được controller thêm vào model. Với ứng dụng dùng cookie/session, các POST thay đổi trạng thái cần xem xét **CSRF**: Spring Security/Thymeleaf integration có thể hỗ trợ hidden token nhưng phải kiểm tra thực tế form và `SecurityFilterChain`; không tắt CSRF để chữa lỗi 403 một cách vội vàng.

## 8. Cơ chế template cache: lưu cái gì, không lưu cái gì?

Mặc định ở Spring Boot 3.5.x:

~~~properties
spring.thymeleaf.cache=true
~~~

Khi bật, Thymeleaf có thể **lưu template representation đã parse** cùng thông tin phục vụ render để tránh đọc/parse lại template ở các request tiếp theo. Khi tắt:

~~~properties
spring.thymeleaf.cache=false
~~~

engine xử lý việc tìm/parse theo cấu hình resolver mà không dựa vào cache template như trước, giúp quan sát thay đổi file khi runtime đọc được file mới, đổi lại chi phí parse và CPU có thể lớn hơn.

Điểm quan trọng là **model không bị đóng băng**:

~~~text
Request #1:
  Controller → Model(q="java", requestCount=1)
  Engine đọc/parse catalog.html nếu chưa cache
  Render HTML cho request #1

Request #2:
  Controller → Model(q="docker", requestCount=2)
  Engine có thể dùng template đã parse từ cache
  Render HTML theo model #2; không dùng HTML đã tạo ở #1
~~~

Với site nhiều người dùng, engine cache template **không được dùng như một response cache chia sẻ HTML có dữ liệu cá nhân**. Nếu xuất hiện trang user A ở user B, cần điều tra response cache/proxy/CDN, session, model/data handling và authorization, không mặc định đổ lỗi cho Thymeleaf template cache.

### Ba tầng cache dễ bị nhầm

| Tầng | Nội dung thường được lưu | Cơ chế |
| --- | --- | --- |
| **Template cache** | Template đã parse/metadata, tránh parse lặp | `spring.thymeleaf.cache` |
| **Static resource cache** | Resource resolver/transformer và HTTP headers của CSS/JS/ảnh | `spring.web.resources.chain.cache`, `spring.web.resources.cache.*` |
| **HTTP cache ở browser/proxy/CDN** | Response được lưu theo HTTP caching semantics | `Cache-Control`, `ETag`, `Last-Modified`, proxy policy |

Tắt `spring.thymeleaf.cache` **không** tự tắt browser cache cho CSS/JS, không thay đổi chính sách cache của reverse proxy và không khiến JAR tự cập nhật file. Tương tự, cấu hình `Cache-Control` cho HTTP response không làm Thymeleaf ngừng cache template đã parse.

**Template cache** khác **message bundle cache**, cache dữ liệu database/Redis, cache Hibernate, v.v. Khi debug cần xác định tầng thật sự đang gây stale data.

## 9. Development: template thay đổi nhưng trang vẫn cũ

### 9.1. Bật cache=false khi phát triển

Trong `application-dev.properties`:

~~~properties
spring.thymeleaf.cache=false
~~~

Chạy với `--spring.profiles.active=dev` hoặc Maven plugin profile. **Quan trọng:** nếu app chạy với file đã copy vào `target/classes/templates/`, thay đổi ở `src/main/resources/templates/` cần được IDE/build tool **copy sang classpath runtime**. Nếu bản trong classpath không đổi, `cache=false` vẫn cho thấy HTML cũ vì engine đọc đúng file cũ.

Quy trình kiểm tra:
1. Chạy app trong mode development và gọi `/catalog`.
2. Sửa chữ “Tìm tên:” ở template thành “Tìm công nghệ:”.
3. Xác nhận bản mới có trong classpath đang dùng, ví dụ `target/classes/templates/catalog.html` (nếu IDE/build cần copy).
4. Refresh `/catalog` bằng browser hoặc `curl`.
5. Nếu còn cũ, xác nhận effective property `spring.thymeleaf.cache` và đường `prefix` thực tế trước khi sửa HTML lần nữa.

**Không nên** kết luận “cache=false không hoạt động” chỉ vì thay file nguồn trong một dự án mà IDE chưa cập nhật runtime resources.

### 9.2. DevTools

Có thể thêm `spring-boot-devtools` vào project development:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-devtools</artifactId>
  <optional>true</optional>
</dependency>
~~~

DevTools cung cấp development-time property defaults, bao gồm:

~~~properties
spring.thymeleaf.cache=false
spring.web.resources.cache.period=0
spring.web.resources.chain.cache=false
~~~

Nó cũng có cơ chế restart khi classpath thay đổi và hỗ trợ browser LiveReload trong điều kiện phù hợp. Thay đổi dưới `templates`/`static` thường được **loại khỏi full restart** mặc định, vì chỉ cập nhật resource thường không cần restart code. Tuy nhiên DevTools không bảo đảm mọi IDE tự động copy file, không tự khiến browser nào cũng refresh nếu thiếu cấu hình và không hoạt động như development tools trong packaged production JAR thông thường.

Khi có property devtools và property explicit, **hãy xem effective configuration** thay vì đoán giá trị từ file. Nếu cần chắc chắn, đặt cache=false trực tiếp trong profile dev và cache=true trong profile prod.

### 9.3. Packaged JAR và image

Với packaged JAR, file template được **đóng gói bên trong artifact**. Đổi source tree ở ngoài rồi refresh browser không thay nội dung artifact. Khi deploy Docker/Kubernetes, cần build image/JAR mới, rollout lại và xác nhận mọi replica có cùng artifact. Đặt `cache=false` không biến JAR thành thư mục source có thể hot reload.

Trường hợp cố ý dùng template external filesystem hoặc custom resolver có thể có quy tắc khác; khi đó cần kiểm soát quyền truy cập, version và cache invalidation, tránh hệ thống nhiều replicas nhìn các bản template không nhất quán.

## 10. Production: cache=true có lợi gì?

Trong production, template ít thay đổi nhưng nhiều request đọc, cache giúp giảm chi phí tìm và parse view/template/fragments. Spring Boot bật `cache=true` theo mặc định; có thể đặt explicit trong profile production để dễ kiểm tra:

~~~properties
spring.thymeleaf.cache=true
~~~

Điều này **không làm database query nhanh hơn**; controller/service vẫn chuẩn bị model cho mỗi request, engine vẫn đánh giá expressions với dữ liệu hiện tại, và server vẫn ghi HTML vào response. Nếu latency cao do DB, N+1, network hoặc logic trong controller, tăng cache template không giải quyết nguyên nhân chính.

Cách kiểm tra hiệu quả:
- So sánh cùng workload/cùng dữ liệu giữa cache bật và tắt ở test environment.
- Đo CPU, throughput, p50/p95 latency, heap, GC và 5xx sau warm-up.
- Với nhiều fragments/layout phức tạp, kiểm tra parse/render time, nhưng không hy sinh validation/bảo mật vì tốc độ.
- Không nhầm **HTTP 304/CDN cache hit** với **Thymeleaf template cache hit**. Nếu request không vào JVM do CDN phục vụ, đó là cache response ngoài Thymeleaf.

Nếu HTML có nội dung của người dùng đăng nhập, kiểm soát `Cache-Control`/shared proxy/CDN theo chính sách dữ liệu. `cache=true` ở Thymeleaf **không cấp quyền** cho shared HTTP cache giữ bản HTML đó.

## 11. Fragments, layout và messages

Fragments giúp dùng lại header, footer, navigation, form controls và thông báo. Cú pháp:

~~~html
<!-- fragments/common.html -->
<footer th:fragment="footer">
  <small>© Trang ví dụ</small>
</footer>

<!-- Catalog view -->
<div th:replace="~{fragments/common :: footer}"></div>
~~~

`th:replace` **thay** phần tử host, còn `th:insert` chèn **bên trong** host. Nếu fragment đã có `<footer>`, dùng `th:insert` trên `<footer>` có thể tạo footer lồng footer; chọn đúng để HTML semantic hợp lệ.

Thymeleaf 3.1 hỗ trợ truyền tham số vào fragment:

~~~html
<!-- fragments/common.html -->
<section th:fragment="notice(message)">
  <p th:text="${message}">Thông báo</p>
</section>

<!-- trang khác -->
<div th:replace="~{fragments/common :: notice('Đã lưu thành công')}"></div>
~~~

**i18n:** `#{key}` tra thông điệp theo locale. Ví dụ có thể tạo:
- `messages.properties` chứa thông điệp mặc định;
- `messages_vi.properties` chứa tiếng Việt;
- `messages_en.properties` chứa tiếng Anh.

Cách chọn locale phụ thuộc `LocaleResolver`/WebFlux locale context và request (ví dụ `Accept-Language`). Nếu key hiển thị như “??catalog.title_vi??”, kiểm tra bundle location, file encoding, locale, key và cấu hình message source. Chỉnh message bundle không nhất thiết chịu tác động bởi `spring.thymeleaf.cache` vì hai tầng cache riêng.

## 12. Bảo mật khi render HTML từ model

Thymeleaf có nhiều cơ chế hạn chế thực thi biểu thức nguy hiểm, nhưng ứng dụng phải tự bảo vệ input và kiểm tra quyền. Một số quy tắc cơ bản:

1. **Ưu tiên `th:text`** cho văn bản nguồn user; nó HTML-escape output. `th:utext` chỉ dùng khi HTML đã qua quy trình trusted/sanitize.
2. Không đưa secrets, private keys, access tokens hay password vào model/HTML, kể cả khi template file không thể truy cập trực tiếp.
3. Logic phân quyền nằm trong controller/service/security filters; `th:if` chỉ điều khiển giao diện, không phải access control.
4. Không để template expressions tự gọi database liên tục; tính model ở service, tránh N+1 và truy vấn phát sinh lúc render.
5. Khi tạo URL động, kiểm tra giá trị có thể dẫn tới open redirect hoặc unsafe scheme. `@{...}` không tự biến một URL user nhập thành an toàn.
6. Form POST dùng cookie/session authentication cần xem xét CSRF đúng cách; không tắt CSRF chỉ để chữa lỗi 403.
7. Với HTML động có thông tin người dùng, cấu hình HTTP caching để shared caches không đưa response của user này cho user khác.

**Tệp `templates` không mặc định public**; đây là thuận lợi về cấu trúc, nhưng không thay thế authorization cho route render nội dung.

## 13. Thymeleaf với Spring WebFlux

Spring Boot cũng hỗ trợ Thymeleaf ở **Spring WebFlux/reactive web**. Hai stack có cấu hình view resolution khác nhau nhưng cùng ý tưởng: controller trả view name, engine dùng `templates` và model để render.

| Điểm | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Starter web | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| Starter view | `spring-boot-starter-thymeleaf` | `spring-boot-starter-thymeleaf` |
| HTTP engine | Servlet stack, `DispatcherServlet` | Reactive stack, `DispatcherHandler` |
| Template location | `classpath:/templates/` | `classpath:/templates/` |
| Cache property | `spring.thymeleaf.cache` | `spring.thymeleaf.cache` |
| View result | `String` logical view name | Có thể trả reactive type như `Mono<String>` |
| Tùy chọn thêm | Servlet view response | `spring.thymeleaf.reactive.*` như chunk-size/full mode |

Mảnh code WebFlux **minh họa, không nằm trong project MVC ở mục 5**:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import reactor.core.publisher.Mono;

@Controller
class ReactivePageController {
    @GetMapping("/reactive-page")
    Mono<String> page(Model model) {
        model.addAttribute("message", "Hello WebFlux");
        return Mono.just("reactive-page");
    }
}
~~~

Đặt `templates/reactive-page.html` chứa `th:text="${message}"` trong project WebFlux riêng. Nếu project chứa **cả** `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường ưu tiên Servlet/MVC application type; không kết luận “chạy WebFlux” chỉ từ dependency WebFlux hoặc có `Mono`. Trong WebFlux, không làm JDBC blocking nặng trực tiếp trên event loop; template caching không sửa bottleneck blocking.

## 14. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Browser hiển thị literal `catalog` | Dùng `@RestController`/`@ResponseBody` | Dùng `@Controller` để trả logical view |
| `GET /templates/catalog.html` trả 404 | Nhầm file path với URL route | Gọi `/catalog` theo controller |
| `TemplateInputException`/“Error resolving template” | Sai view name, prefix/suffix, file thiếu | Tính `prefix + view + suffix`, kiểm tra classpath |
| Controller có route nhưng response 500 | Template không tồn tại, expression/fragment lỗi | Đọc stack trace render; sửa template/Model |
| IDE chạy tốt, JAR lỗi | File không được copy/đóng gói | `jar tf target/...jar` và kiểm tra `BOOT-INF/classes/templates` |
| HTML mới không hiện khi cache=true | Template parse/cache còn bản cũ | Trong dev dùng cache=false và đúng classpath |
| cache=false nhưng HTML vẫn cũ | File nguồn chưa copy vào runtime hoặc JAR cũ | Kiểm tra `target/classes`/build process/redeploy |
| DevTools có dependency nhưng cache không tắt | DevTools không active hoặc property khác override | Kiểm tra effective `spring.thymeleaf.cache` |
| CSS không tải | CSS đặt sai thư mục, context path hoặc security | Dùng `static` và `th:href="@{/css/...}"` |
| CSS cũ, HTML mới | Browser/CDN/static resource cache | Kiểm tra HTTP response headers và build assets |
| Fragment không tìm thấy | Sai tên `th:fragment`, path, prefix | Kiểm tra `fragments/common :: banner` |
| `${...}` hiển thị nguyên dạng | File được gửi static, Thymeleaf không render | Đảm bảo có controller/view resolver |
| Key `#{...}` không được dịch | Bundle/locale/key sai | Kiểm tra `messages*.properties` và locale |
| Lỗi binding trong form | `th:object` sai tên hoặc DTO thiếu property | Đối chiếu model attributes, DTO, th:field |
| POST form 403 | Spring Security CSRF/authorization | Kiểm tra filter chain và token |
| Tắt cache production làm CPU tăng | Phải parse lại nhiều lần | Dùng cache=true, đo hiệu năng |
| Lỗi chỉ trên một replica | JAR/image khác phiên bản hoặc proxy cache | Kiểm tra version artifact của từng replica |

**Phân biệt 404 và 500:** URL không có controller/static resource tương ứng thường 404. Nếu controller đã khớp nhưng view/template không resolve hoặc lỗi khi render, thường gặp 500. Cấu hình exception handler/security có thể tạo mã khác; đừng suy luận từ mã lỗi mà bỏ qua stack trace.

### Quy trình debug thực dụng

1. Ghi rõ URL request, HTTP status và controller thực sự xử lý.
2. Xác định class dùng `@Controller` hay `@RestController` và logical view name trả về.
3. Tính path `prefix + viewName + suffix` rồi kiểm tra file tồn tại trên **runtime classpath**.
4. Kiểm tra active profile, effective `spring.thymeleaf.cache`, view resolver tùy chỉnh.
5. Nếu thiếu dữ liệu, kiểm tra `model.addAttribute(...)` và tên trong `${...}`; tránh NPE.
6. Với fragments, kiểm tra file/path và tên `th:fragment`; với i18n, kiểm tra key/locale.
7. Nếu HTML mới nhưng CSS/JS cũ, kiểm tra static URL và HTTP caches thay vì Thymeleaf.
8. Với JAR, xác minh artifact thực deploy có template mới, đừng chỉ nhìn source tree.
9. Đọc log và `curl -i` từ chính instance có lỗi. Khi bật debug logs, tránh đưa thông tin bí mật vào log.

## 15. Bài tập tự kiểm tra

1. Controller trả `"admin/users"` trong Boot Thymeleaf mặc định: tệp được tìm ở đâu?
2. Vì sao `@RestController` trả `"catalog"` lại không render `catalog.html`?
3. File `static/index.html` có `th:text`: khi truy cập trực tiếp browser có được xử lý Thymeleaf không?
4. Vì sao `requestCount` ở ví dụ vẫn tăng khi `cache=true`?
5. `application-dev.properties` có `cache=false` nhưng app chạy default profile. Có tự hiệu lực không?
6. Tắt cache nhưng sửa `src/main/resources/templates/catalog.html` mà runtime còn đọc `target/classes/templates/catalog.html` cũ. Cần kiểm tra gì?
7. Đổi file nguồn sau khi build JAR cũ, đặt `cache=false` có làm JAR nhận file mới không?
8. `th:text` và `th:utext` khác gì với chuỗi chứa `<script>`?
9. `th:replace` khác `th:insert` thế nào nếu fragment là một `header`?
10. Tại sao `spring.web.resources.cache.period=0` không thay thế `spring.thymeleaf.cache=false`?
11. `/catalog` trả HTML bình thường nhưng `/css/site.css` 404, nên sửa thư mục nào?
12. Tại sao vẫn phải kiểm soát HTTP shared-cache dù template cache không lưu HTML theo user?
13. Chỉnh `spring.thymeleaf.prefix=classpath:/ui/` thì fragment `fragments/common` sẽ được tìm tại đâu?
14. Nếu có cả starter MVC và WebFlux thì runtime mặc định thường là stack nào?
15. Cần kiểm tra dấu hiệu nào để quyết định bật cache trong production?

**Đáp án gợi ý:** (1) `classpath:/templates/admin/users.html`; (2) @RestController ghi response body; (3) không; (4) mỗi request chạy controller/model lại; (5) không, phải kích hoạt profile; (6) runtime classpath và build/IDE resource copy; (7) không, phải build/deploy; (8) escaped vs unescaped, rủi ro XSS với utext; (9) replace thay host, insert giữ host; (10) static/HTTP cache khác template parse cache; (11) kiểm tra `static`, static URL và security; (12) HTML response có thể chứa dữ liệu riêng; (13) `classpath:/ui/fragments/common.html`; (14) thường Servlet/MVC; (15) lưu lượng render, CPU, parse overhead và khả năng deploy artifact mới.

## 16. Tài liệu chính thức

- Spring Boot 3.5, Servlet Template Engines: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5, Reactive Template Engines: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5, Common Application Properties/Thymeleaf: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot Developer Tools và template cache defaults: https://docs.spring.io/spring-boot/reference/using/devtools.html
- Spring Boot Hot Swapping, Reload Templates: https://docs.spring.io/spring-boot/how-to/hotswapping.html
- Thymeleaf 3.1 Tutorial, expressions và fragments: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html
- Thymeleaf + Spring, form binding và Spring context: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html

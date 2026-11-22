# Tự cấu hình các template engine được Spring Boot hỗ trợ

> **Phạm vi:** Spring Boot web-runtime, trọng tâm ứng dụng **render HTML phía máy chủ** bằng Spring MVC và đối chiếu khả năng hỗ trợ của Spring WebFlux. Các tên property, phần mở rộng và ví dụ được diễn giải theo **Spring Boot 3.3.x với Java 17+**; khi dùng dòng Spring Boot khác, đối chiếu tài liệu chính thức của phiên bản đang chạy.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **server-side template engine**, view name, `ViewResolver`, model và HTML thực tế trả về cho trình duyệt.
2. Giải thích vì sao thêm đúng dependency và đặt file đúng thư mục có thể kích hoạt **auto-configuration** của Spring Boot mà không cần tự tạo `ViewResolver`.
3. Liệt kê đúng bốn template engine Boot 3.3 hỗ trợ tự cấu hình cho **Spring MVC**: **Thymeleaf**, **FreeMarker**, **Mustache**, **Groovy Templates**; phân biệt trường hợp WebFlux và JSP.
4. Chạy ví dụ Spring MVC + Thymeleaf có cấu trúc file đầy đủ, controller, model, template, `application.properties` và lệnh thử nghiệm.
5. Đổi engine sang FreeMarker/Mustache, hiểu điều gì đổi trong dependency, phần mở rộng template, cú pháp và cấu hình.
6. Tùy chỉnh prefix/suffix/template path/cache/view patterns bằng property, biết khi nào cần viết bean và tránh vô hiệu hóa auto-config ngoài ý muốn.
7. Chẩn đoán lỗi view không tìm thấy, trả nhầm body, lỗi parse, template cache, XSS, xung đột nhiều engine và đóng gói ứng dụng.

## 2. Template engine là gì? Luồng xử lý một trang HTML

Template engine kết hợp **mẫu HTML** và **dữ liệu của request** để tạo HTML cuối cùng trên server. Trình duyệt nhận kết quả HTML; thông thường nó **không** nhận file nguồn Thymeleaf `.html` có `th:...`, FreeMarker `.ftlh` có `<#...>`, Mustache `.mustache` có `{{...}}` hoặc mã template Groovy.

Ví dụ kinh điển: handler nhận `GET /hello?name=Lan`, đặt `name = "Lan"` vào `Model`, trả về view name `"hello"`. Engine tìm template `hello` đúng đường dẫn rồi render. Response thường có `Content-Type: text/html` (kèm charset tùy cấu hình).

```text
Browser
   |
   | GET /hello?name=Lan
   v
Spring DispatcherServlet / WebFlux DispatcherHandler
   |
   v
@Controller (gán Model: name="Lan")
   |
   | return "hello"  <-- tên view logic, không phải HTML
   v
ViewResolver / ViewResolutionResultHandler
   |
   | classpath:/templates/hello.html  (Thymeleaf)
   v
Template Engine + Model
   |
   v
HTML rendered --> HTTP response --> Browser
```

Tách bạch vai trò:

| Thành phần | Trách nhiệm |
|---|---|
| `@Controller` | Chọn luồng nghiệp vụ, cung cấp model, trả view name hoặc `ModelAndView`. |
| `Model` | Tập các thuộc tính cho template trong request, ví dụ `name`, `items`. |
| View name `"hello"` | Tên logic để resolver xác định view, **không nhất thiết là path file đầy đủ**. |
| `ViewResolver` (MVC) | Chuyển view name thành `View` phù hợp và kiểm tra prefix/suffix, loại view. |
| Template engine | Đọc template, áp dụng biểu thức/điều kiện/vòng lặp và tạo output. |
| Auto-configuration | Spring Boot đăng ký/cấu hình các bean mặc định khi dependency, classpath, môi trường web, bean và properties đáp ứng điều kiện. |

**Ví dụ quan trọng:**

```java
@Controller
class PageController {
    @GetMapping("/page")
    String page(Model model) {
        model.addAttribute("title", "Trang của Lan");
        return "home"; // view name: "home"
    }
}
```

Đoạn trên là ví dụ **trong một ứng dụng MVC đã cấu hình**, cần imports và application class; `return "home"` không gửi trực tiếp chuỗi "home" cho client. Nếu thay `@Controller` bằng `@RestController` hoặc thêm `@ResponseBody`, chuỗi return trở thành **body**, nên trang template không được render. Đây là nguyên nhân phổ biến khi người học thấy chữ `home` thay vì giao diện HTML.

## 3. Những engine được Spring Boot 3.3 tự cấu hình

Theo tài liệu Spring Boot 3.3 về Servlet Web Applications, Spring Boot có auto-configuration cho **FreeMarker, Groovy Templates, Thymeleaf, Mustache** trong ứng dụng Spring MVC. Các engine khác vẫn có thể tích hợp bằng cấu hình/framework thích hợp, nhưng không nên suy ra Boot có auto-configuration chính thức chỉ từ việc chúng hoạt động được với Spring MVC.

| Engine | Starter trên Spring Boot 3.3 | File template mặc định | Điểm phù hợp |
|---|---|---|---|
| **Thymeleaf** | `spring-boot-starter-thymeleaf` | `src/main/resources/templates/hello.html` | HTML gần cú pháp HTML tự nhiên; biểu thức, form, fragment, tích hợp Spring MVC thuận tiện. |
| **FreeMarker** | `spring-boot-starter-freemarker` | `src/main/resources/templates/hello.ftlh` | Template Language mạnh, macro/loop/điều kiện, tái sử dụng khi render HTML hoặc văn bản. |
| **Mustache** | `spring-boot-starter-mustache` | `src/main/resources/templates/hello.mustache` | Ngữ pháp gọn, logic tối giản, mô hình section và partial. |
| **Groovy Templates** | `spring-boot-starter-groovy-templates` | `src/main/resources/templates/hello.tpl` | Viết template bằng Groovy Markup Template Engine; hợp hệ thống đã dùng Groovy. |

**JSP là trường hợp khác:** Spring MVC có hỗ trợ JSP qua Servlet/JSP infrastructure, nhưng JSP **không nằm trong danh sách bốn engine trên**. Trên Spring Boot 3.3, khi dùng embedded Tomcat/Jetty, JSP có hạn chế đóng gói: JSP không được hỗ trợ trong **executable JAR**, cần cân nhắc **WAR**; Undertow không hỗ trợ JSP. Vì vậy đừng coi `spring-boot-starter-web` + JSP là tương đương với starter template engine thông thường. Đây là lý do tài liệu Boot khuyên hạn chế dùng JSP nếu có lựa chọn phù hợp.

### Phân biệt với Spring WebFlux

Spring Boot hỗ trợ auto-configuration template engine **FreeMarker, Thymeleaf, Mustache** cho WebFlux; **Groovy Templates không thuộc danh sách auto-configuration WebFlux** của tài liệu Boot 3.3. Với WebFlux, một số đặc tính của FreeMarker có giới hạn; phải kiểm tra phần property và view integration tương ứng. `spring-boot-starter-webflux` không biến mọi template engine thành một hệ thống render non-blocking hoàn toàn; việc xử lý template/biểu thức vẫn tiêu CPU.

Nếu đồng thời có `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường chọn **Servlet/MVC web application** theo cơ chế suy luận mặc định; đừng nhìn thấy `Mono` trên classpath rồi mặc định nghĩ đang có Reactor Netty server.

## 4. Auto-configuration hoạt động theo điều kiện nào?

Thay vì buộc bạn tự tạo `TemplateEngine`, `TemplateResolver`, `ViewResolver` và hàng loạt bean, Boot có các auto-configuration chuyên biệt. Chúng kiểm tra những điều kiện liên quan như:

1. Các **class từ template engine** có trong classpath (thường do starter kéo theo).
2. Các **class của Spring MVC hoặc WebFlux**, loại web application và môi trường hiện tại.
3. Những bean đã tồn tại; nhiều auto-configuration đăng ký mặc định theo kiểu `@ConditionalOnMissingBean` hay điều kiện tương đương.
4. Thuộc tính cấu hình như `spring.thymeleaf.enabled`, `spring.freemarker.enabled`, `spring.mustache.enabled`.
5. Cấu hình view resolver, đường dẫn và phần mở rộng template.

Vì vậy “đã thêm starter” **không bảo đảm** mọi resolver luôn hoạt động bất kể cấu hình: app có thể là sai web stack, bean của bạn có thể thay thế mặc định, engine có thể bị disable hoặc template nằm ngoài đường dẫn loader.

Một số bean thường gặp trong Spring MVC:

| Engine | View resolver tiêu biểu | Chức năng |
|---|---|---|
| Thymeleaf | `ThymeleafViewResolver` | Dùng cấu hình Thymeleaf để tìm `hello.html`. |
| FreeMarker | `FreeMarkerViewResolver` | Ghép loader path/prefix/suffix, thường tìm `hello.ftlh`. |
| Mustache | `MustacheViewResolver` | Tìm template Mustache theo prefix/suffix. |
| Groovy | `GroovyMarkupViewResolver` | Tìm template Groovy Markup theo path/suffix. |

Spring MVC còn có resolver nền như `InternalResourceViewResolver`, `BeanNameViewResolver`; tùy ứng dụng có thể có `ContentNegotiatingViewResolver`. Nếu tự đăng ký thêm resolver hoặc dùng nhiều engine, **thứ tự và điều kiện khớp view name** có thể ảnh hưởng engine nào được chọn. Không dựa vào “resolver nào được add sau cùng” để giải quyết xung đột: kiểm tra cấu hình resolver và view patterns trực tiếp.

**Không thêm `@EnableWebMvc` chỉ để dùng Thymeleaf.** Annotation này chuyển phần lớn thiết lập Spring MVC mặc định sang chế độ tự quản lý; nếu mục tiêu chỉ là thêm template engine hoặc mở rộng MVC, giữ Boot MVC auto-configuration và chỉ thêm bean/`WebMvcConfigurer` khi thực sự cần. `@EnableWebFlux` cũng cần cân nhắc tương tự ở phía reactive.

## 5. Quy trình tích hợp tối thiểu với Spring MVC

Với một template engine tự cấu hình, thường đủ bốn bước:

1. Dự án có Spring Boot + starter web MVC.
2. Thêm **một** starter template engine, ví dụ `spring-boot-starter-thymeleaf`.
3. Tạo file template dưới `src/main/resources/templates/` (hoặc thay path bằng properties).
4. Viết `@Controller` trả **view name**, cung cấp thuộc tính `Model`.

Ví dụ Gradle (Groovy DSL) trong dự án đã dùng Spring Boot plugin/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
```

Đây là **phần dependencies** trong build đã cấu hình, không phải toàn bộ `build.gradle`. Trong Spring Boot 3.3, Boot quản lý version các dependency thông qua dependency management/BOM; không tự đặt version lệch cho các starter nếu không có lý do.

Với Maven, phần tương ứng trong `<dependencies>` là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

Mẫu Maven này giả định parent/BOM Spring Boot đã được cấu hình. Cả hai cách trên đều mô tả **một web runtime MVC**; không cần thêm `spring-boot-starter-webflux` chỉ để render HTML trên server.

### Cấu trúc dự án

```text
src/main/
  java/
    example/views/
      ViewsApplication.java
  resources/
    application.properties
    templates/
      greeting.html
```

`templates/` trong `src/main/resources` sẽ được đóng gói thành tài nguyên classpath, nên khi chạy executable JAR, template vẫn được tìm qua `classpath:/templates/`. Đừng tự tạo `src/main/webapp` cho Thymeleaf rồi kỳ vọng Boot tự quét ở đó như template mặc định.

## 6. Ví dụ Spring MVC + Thymeleaf hoàn chỉnh

Tạo file `src/main/java/example/views/ViewsApplication.java`:

```java
package example.views;

import java.util.List;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@SpringBootApplication
public class ViewsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ViewsApplication.class, args);
    }

    @Controller
    static class GreetingController {
        @GetMapping("/greeting")
        String greeting(
                @RequestParam(defaultValue = "bạn") String name,
                Model model) {
            model.addAttribute("name", name);
            model.addAttribute("topics",
                    List.of("Spring MVC", "Thymeleaf", "Template engine"));
            return "greeting";
        }
    }
}
```

Lưu ý:

- `@Controller` là điều kiện quan trọng để `String` được diễn giải thành **view name**.
- `model.addAttribute` đưa dữ liệu vào template theo request.
- `return "greeting"` không gồm `.html` và không gồm `/templates/`; Thymeleaf resolver dùng prefix + view name + suffix để tìm file.
- Với package `example.views`, lớp application quét các component cùng package/subpackage; nested `static` controller có `@Controller` được component scan nhận diện.
- `@RequestParam(defaultValue = "bạn")` cho phép gọi URL khi không truyền `name`.

Tạo `src/main/resources/templates/greeting.html`:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Trang chào</title>
</head>
<body>
  <h1>Xin chào <span th:text="${name}">bạn</span>!</h1>
  <h2>Nội dung học:</h2>
  <ul>
    <li th:each="topic : ${topics}"
        th:text="${topic}">Một chủ đề</li>
  </ul>
</body>
</html>
```

Trong Thymeleaf, `th:text="${name}"` lấy attribute `name` từ model và **HTML-escape** nội dung theo ngữ cảnh text. Vòng lặp `th:each` tạo một `li` cho mỗi phần tử trong `topics`. Các đoạn text có sẵn bên trong phần tử là dữ liệu mẫu, được thay khi render. Vì vậy file vẫn có cấu trúc HTML dễ đọc khi mở như một template.

Ví dụ cấu hình `src/main/resources/application.properties` (các giá trị dưới đây tương đương phần lớn default của Boot 3.3):

```properties
spring.thymeleaf.enabled=true
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.mode=HTML
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.cache=true
```

Để học auto-configuration, có thể bỏ hẳn các dòng này vì Boot đã có giá trị mặc định. Giữ chúng khi muốn **làm rõ chính xác** template path, định dạng hoặc cache.

Chạy từ gốc dự án bằng:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`; với dự án Maven dùng `./mvnw spring-boot:run` hoặc `mvnw.cmd spring-boot:run`. Truy cập:

```bash
curl -i "http://localhost:8080/greeting?name=Lan"
```

Kết quả dự kiến: status `200 OK`, content type HTML, trong body có `Xin chào Lan!` và ba `li` với `Spring MVC`, `Thymeleaf`, `Template engine`. **Đừng khẳng định output HTTP nguyên văn từng byte**, vì khoảng trắng trong HTML, headers và cách serial hóa có thể khác giữa các phiên bản/container.

### Kiểm tra cơ chế escape

Gọi:

```bash
curl -i "http://localhost:8080/greeting?name=%3Cb%3ELan%3C%2Fb%3E"
```

`name` được decode thành chuỗi chứa markup `<b>Lan</b>`. Với `th:text`, HTML đầu ra phải encode các dấu `<` và `>` ở vị trí text thành entity, ví dụ `&lt;b&gt;Lan&lt;/b&gt;`. Trình duyệt nhìn thấy chữ `<b>Lan</b>` thay vì coi là thẻ bold. Khi thay bằng `th:utext` hoặc ghép chuỗi HTML thủ công, bạn bỏ qua escape và có thể tạo lỗ hổng **XSS** khi dữ liệu đến từ người dùng.

## 7. Quy đổi ví dụ sang các engine khác

Bạn **không cần giữ đồng thời bốn starter** trong dự án. Trong các phiên bản thử nghiệm dưới đây, giữ nguyên `ViewsApplication.java`, bỏ `spring-boot-starter-thymeleaf`, thêm **một** starter của engine chọn, rồi đặt template tên tương ứng. View name vẫn là `greeting`.

### 7.1. FreeMarker

Thay dependency template bằng:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-freemarker'
```

Tạo `src/main/resources/templates/greeting.ftlh`:

```ftl
<#ftl output_format="HTML" auto_esc=true>
<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Trang chào</title></head>
<body>
  <h1>Xin chào ${name}!</h1>
  <ul>
  <#list topics as topic>
    <li>${topic}</li>
  </#list>
  </ul>
</body>
</html>
```

Mã `<#list ...>` lặp qua danh sách trong model, `${...}` lấy giá trị. Với file đuôi `.ftlh` và chỉ thị output format HTML có `auto_esc=true`, các giá trị chèn vào HTML text được escape theo ngữ cảnh output format. Không tùy tiện dùng `?no_esc` với dữ liệu không đáng tin.

Các property tiêu biểu của Boot 3.3:

```properties
spring.freemarker.enabled=true
spring.freemarker.template-loader-path=classpath:/templates/
spring.freemarker.prefix=
spring.freemarker.suffix=.ftlh
spring.freemarker.charset=UTF-8
spring.freemarker.cache=false
```

**Khác Thymeleaf:** `template-loader-path` quy định vị trí nguồn template; `prefix` thường rỗng theo mặc định ở FreeMarker. Nếu đặt `spring.freemarker.prefix=pages/`, view name `greeting` sẽ tìm như `pages/greeting.ftlh` bên trong loader path. Đừng nhầm hai cấu hình này rồi tạo `templates/templates/... ` ngoài ý muốn.

### 7.2. Mustache

Thay dependency template bằng:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mustache'
```

Tạo `src/main/resources/templates/greeting.mustache`:

```html
<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Trang chào</title></head>
<body>
  <h1>Xin chào {{name}}!</h1>
  <ul>
    {{#topics}}
    <li>{{.}}</li>
    {{/topics}}
  </ul>
</body>
</html>
```

Trong Mustache, `{{name}}` chèn biến với **HTML escaping** theo quy tắc mặc định; `{{#topics}}` mở một section lặp khi value là danh sách và `{{.}}` là phần tử đang xét. `{{{name}}}` hoặc `{{& name}}` là dạng không escape, chỉ dùng khi giá trị đã qua kiểm soát ngữ cảnh và thực sự cần HTML tin cậy.

Property tiêu biểu:

```properties
spring.mustache.enabled=true
spring.mustache.prefix=classpath:/templates/
spring.mustache.suffix=.mustache
spring.mustache.charset=UTF-8
```

Mustache phù hợp khi muốn logic trong template tối giản. Các phép lọc/tính toán nghiệp vụ nên thực hiện trước trong controller/service; template chủ yếu hiển thị model. Trong ứng dụng lớn, có thể dùng partial để tái sử dụng header, footer và các đoạn giao diện.

### 7.3. Groovy Templates

Thay dependency template bằng:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-groovy-templates'
```

Boot 3.3 cung cấp cấu hình Groovy Markup view cho Spring MVC khi các class/template infrastructure phù hợp có trong classpath. Những property quan trọng:

```properties
spring.groovy.template.enabled=true
spring.groovy.template.resource-loader-path=classpath:/templates/
spring.groovy.template.suffix=.tpl
spring.groovy.template.charset=UTF-8
```

Template là file `.tpl` với cú pháp **Groovy Markup Template Engine**, khác `th:...`, `${...}` của FreeMarker hay `{{...}}` của Mustache. Ví dụ cấu trúc minh họa Groovy Markup:

```groovy
html {
    head {
        title('Trang chào')
    }
    body {
        h1("Xin chào ${name}!")
        ul {
            topics.each { topic ->
                li(topic)
            }
        }
    }
}
```

Đoạn trên là **template Groovy Markup**, không phải lớp Java và không có lệnh `javac` riêng. Khả năng escape phụ thuộc cấu hình template/markup; không giả định Groovy tự escape mọi giá trị. Kiểm tra `spring.groovy.template.configuration.auto-escape`, ngữ cảnh thẻ/thuộc tính và tài liệu Groovy Markup phù hợp phiên bản trước khi render dữ liệu không tin cậy.

**Về phạm vi:** Groovy Templates được Spring Boot tự cấu hình cho **Spring MVC** trong danh sách trên; không lấy ví dụ MVC này để tuyên bố Groovy Markup có cùng auto-configuration cho WebFlux.

### 7.4. JSP: vì sao không thay như bốn engine trên?

JSP được servlet container biên dịch/chạy theo cơ chế riêng và thường nằm trong web application context, nên **không** đơn giản là bỏ Thymeleaf starter, thêm một file `templates/greeting.jsp` và Boot tự render. Nếu dùng JSP trong Spring MVC, bạn phải cấu hình các dependency/runtime phù hợp, resolver/prefix/suffix như `spring.mvc.view.prefix` và `spring.mvc.view.suffix`, cấu trúc WAR cũng như các giới hạn của container. Trên Boot 3.3, JSP **không hỗ trợ** đóng gói **executable JAR**; dùng Tomcat/Jetty với WAR là đường thường được tài liệu đề cập, còn Undertow không hỗ trợ JSP.

Nếu mục tiêu là UI server-rendered mới chạy như executable JAR, hãy cân nhắc một trong bốn engine có auto-configuration sẵn, thường bắt đầu với Thymeleaf hoặc Mustache tùy nhu cầu.

## 8. Bảng tra cứu property quan trọng của Spring Boot 3.3

| Engine | Bật/tắt view resolution | Template path/prefix mặc định | Suffix mặc định | Cache |
|---|---|---|---|---|
| Thymeleaf | `spring.thymeleaf.enabled` | `spring.thymeleaf.prefix=classpath:/templates/` | `spring.thymeleaf.suffix=.html` | `spring.thymeleaf.cache=true` mặc định |
| FreeMarker | `spring.freemarker.enabled` | `spring.freemarker.template-loader-path=classpath:/templates/`, prefix rỗng | `spring.freemarker.suffix=.ftlh` | `spring.freemarker.cache=false` mặc định trên Boot 3.3 |
| Mustache | `spring.mustache.enabled` | `spring.mustache.prefix=classpath:/templates/` | `spring.mustache.suffix=.mustache` | Boot 3.3 có `spring.mustache.servlet.cache` cho MVC |
| Groovy Templates | `spring.groovy.template.enabled` | `spring.groovy.template.resource-loader-path=classpath:/templates/` | `spring.groovy.template.suffix=.tpl` | `spring.groovy.template.cache=false` mặc định trên Boot 3.3 |

Đây là **các giá trị đặc trưng của dòng 3.3**, không phải cam kết các khóa property hoặc default giống hệt trên mọi major release. Tham khảo *Common Application Properties* của chính version ứng dụng để xác nhận.

Ngoài các khóa chính, Boot có thể cung cấp các tùy chọn:

- **Thymeleaf:** `spring.thymeleaf.mode`, `encoding`, `check-template`, `check-template-location`, `view-names`, `excluded-view-names`, `template-resolver-order`.
- **FreeMarker:** `spring.freemarker.charset`, `view-names`, `settings.*`, `check-template-location`, cùng đường loader/prefix/suffix.
- **Mustache:** `spring.mustache.view-names`, `check-template-location`, cấu hình `servlet.*` hoặc `reactive.*` theo web stack.
- **Groovy:** `spring.groovy.template.view-names`, `resource-loader-path`, `configuration.*` và các thuộc tính render có trong version.

Cấu hình tại `application.properties`, `application.yml`, environment variables hoặc nguồn configuration của Boot phù hợp. Chọn **một nguồn cấu hình rõ ràng** cho từng môi trường để tránh nhầm giá trị bị override theo property-source precedence. Không đổi toàn bộ view infrastructure chỉ vì muốn tắt cache trong môi trường phát triển.

## 9. Điều chỉnh cấu hình theo môi trường

### 9.1. Development: giảm thời gian thấy sửa đổi

Với Thymeleaf, khi muốn template được đọc mới ở mỗi lần render trong môi trường phát triển:

```properties
# application-dev.properties
spring.thymeleaf.cache=false
```

Chạy profile dev trong ứng dụng mẫu:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Lệnh trên là cú pháp Gradle phổ biến trên shell Unix; trên Windows có thể dùng `gradlew.bat bootRun --args="--spring.profiles.active=dev"`. Khi chạy trực tiếp `java -jar`, đặt `--spring.profiles.active=dev` sau tên JAR.

Tắt template cache **không đảm bảo** sửa file `src/main/resources/templates` sẽ xuất hiện ngay nếu process đang chạy template đã được **copy vào output classpath** và build tool/IDE chưa cập nhật tài nguyên. Cần phân biệt cache engine với việc nguồn template có thực sự được ứng dụng nạp lại hay không. DevTools có thể hỗ trợ workflow reload theo cấu hình.

### 9.2. Production: ưu tiên cache và kiểm chứng đóng gói

```properties
# application-prod.properties
spring.thymeleaf.cache=true
```

Cache có thể giảm chi phí đọc/parse template, nhưng thay đổi production build thường cần release/restart phù hợp. Không bật cache để che lỗi path, lỗi dữ liệu hoặc lỗi template. Nếu app dùng FreeMarker/Mustache/Groovy, chọn các property cache phù hợp đúng version/web stack thay vì sao chép `spring.thymeleaf.cache`.

**Đảm bảo tài nguyên được đóng gói:** với Spring Boot executable JAR, file `src/main/resources/templates/greeting.html` phải có trong classpath của JAR. Có thể kiểm tra JAR sau build bằng `jar tf build/libs/<tên-jar>.jar` rồi tìm entry gần `BOOT-INF/classes/templates/greeting.html`. Tên artifact thực tế tùy project; đừng hardcode khi triển khai.

### 9.3. Đổi thư mục template để tổ chức UI

Nếu muốn lưu Thymeleaf template dưới `src/main/resources/views/`:

```properties
spring.thymeleaf.prefix=classpath:/views/
spring.thymeleaf.suffix=.html
```

Lúc đó `return "greeting"` tìm `classpath:/views/greeting.html`. Nếu muốn phân nhóm:

```text
src/main/resources/views/
  public/
    greeting.html
  admin/
    dashboard.html
```

Controller có thể trả `"public/greeting"` hoặc `"admin/dashboard"`; resolver ghép prefix/suffix để xác định file. Không dùng đường dẫn dựa trên tham số user một cách không kiểm soát (ví dụ `return request.getParameter("view")`), bởi điều này có thể khiến user chọn view không mong muốn.

## 10. Tránh xung đột khi một ứng dụng có nhiều template engine

Về kỹ thuật, classpath có thể có nhiều starter, và Spring MVC có nhiều `ViewResolver` cùng tồn tại. Tuy nhiên, nếu hai resolver đều có thể chấp nhận view name `"greeting"`, kết quả phụ thuộc điều kiện resolve, thứ tự và hành vi từng resolver. Có thể phát sinh lựa chọn sai template, lỗi resource không tồn tại hoặc response không như dự định.

**Cách dễ vận hành nhất:** một ứng dụng chủ yếu dùng **một** template engine, chỉ trộn khi có nhu cầu chuyển đổi/migration rõ ràng.

Khi buộc phải có nhiều engine, phân miền view name, ví dụ:

```text
templates/
  thymeleaf/
    profile.html
  freemarker/
    invoice.ftlh

View names:
  "thymeleaf/profile"
  "freemarker/invoice"
```

Và cân nhắc filter `view-names` (các property bên dưới là mô tả phân tách theo tên logic trong Spring Boot 3.3):

```properties
spring.thymeleaf.view-names=thymeleaf/*
spring.freemarker.view-names=freemarker/*
```

Việc cấu hình `view-names` giúp giới hạn resolver nào nên xử lý tên nào; nhưng bạn vẫn phải **kiểm tra thực tế** thứ tự và kết quả resolver trong version đang chạy, cũng như cấu hình resource paths và view resolution cho từng engine. Không mặc định mọi mẫu wildcard đều có ý nghĩa như URL route: ở đây chúng là **view name patterns**, không phải mapping HTTP.

Với một migration phức tạp, có thể tự đăng ký hoặc điều chỉnh `ThymeleafViewResolver`/`FreeMarkerViewResolver` cùng bean customizer và thứ tự. Đây là trường hợp nên đọc code/config của **auto-configuration phiên bản cụ thể** để tránh tạo bean trùng hoặc làm Boot back off ngoài ý định.

## 11. Khi nào cần viết bean cấu hình thủ công?

Dùng property trước; chỉ tự cấu hình bean khi yêu cầu vượt mức property hỗ trợ, chẳng hạn:

- Cần resolver nhiều nguồn template (classpath, database/remote repository có kiểm soát), custom dialect, extension đặc biệt.
- Cần view names, localization, escaping hoặc fragment/layout phức tạp mà property không đáp ứng.
- Cần cơ chế cache có kiểm soát và reload theo tenant/theme, hoặc engine dùng integration ngoài danh sách Boot.
- Cần đặt thứ tự các `ViewResolver` trong một ứng dụng phục vụ nhiều loại view.

### Ví dụ: bổ sung Thymeleaf dialect

Thymeleaf hỗ trợ `Dialect` mở rộng cú pháp. Spring Boot có integration cho các dialect khi thích hợp; thay vì thay cả `SpringTemplateEngine` chỉ để có một extension, dùng bean dialect tuân theo integration của Boot và kiểm chứng bean được nhận. Ví dụ sau **chỉ minh họa cấu trúc** (class `CustomDialect` phải được định nghĩa trong ứng dụng):

```java
@Configuration
class ThymeleafExtensions {
    @Bean
    IDialect customDialect() {
        return new CustomDialect();
    }
}
```

Đoạn này không phải ứng dụng Java độc lập và cần imports cụ thể theo API Thymeleaf. Lợi ích của việc giữ auto-configuration là Boot vẫn quản lý hầu hết resolver/engine/encoding/cache và các integration liên quan.

### Vì sao tránh thay `TemplateEngine` một cách không cần thiết?

Nếu bạn tự tạo `SpringTemplateEngine`, `SpringResourceTemplateResolver` hoặc bean cùng tên/kiểu mà auto-config vốn tạo, các điều kiện `@ConditionalOnMissingBean` có thể khiến cấu hình mặc định không được áp dụng. Từ đó app có thể mất integration, message source, dialect hoặc property behavior mong đợi. Hãy xác định rõ bean cần thay, cách Boot sẽ back off, và có integration test xác nhận.

### Phân biệt WebMvcConfigurer với @EnableWebMvc

Để thêm cấu hình MVC nhỏ mà vẫn dùng Boot defaults, có thể khai báo `@Configuration` implement `WebMvcConfigurer`. `@EnableWebMvc` thường dành cho trường hợp muốn tự kiểm soát cấu hình MVC toàn diện. Đừng đặt nó chỉ để thêm view template, bởi nó làm thay đổi bộ auto-configuration MVC của Boot.

## 12. Spring WebFlux và template rendering

WebFlux sử dụng `DispatcherHandler` và cơ chế view resolution reactive của Spring WebFlux, thay vì `DispatcherServlet`/`ViewResolver` của MVC. Tuy nhiên, mô hình ở cấp người phát triển tương tự: `@Controller` trả view name, model chứa dữ liệu và engine render nội dung.

Boot 3.3 auto-config **Thymeleaf, FreeMarker, Mustache** cho WebFlux. Ví dụ độc lập về controller trong **ứng dụng WebFlux đã có starter template và main class**:

```java
package example.reactiveview;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class ReactivePageController {
    @GetMapping("/reactive-greeting")
    public String greeting(Model model) {
        model.addAttribute("name", "WebFlux");
        return "greeting";
    }
}
```

File trên là **controller độc lập ở cấp class**, nhưng cần một Spring Boot WebFlux application ở package cha `example.reactiveview` và starter template tương ứng; nó **không phải ứng dụng runnable một mình**. Với Thymeleaf, file `src/main/resources/templates/greeting.html` có thể dùng lại mẫu ở ví dụ MVC.

**Lưu ý về reactive:**

- Bản thân render HTML/parse template có phần CPU; không được suy ra “không bao giờ block event loop” chỉ vì controller trả `Mono` hoặc WebFlux được dùng.
- Với FreeMarker trên WebFlux có các đặc tính không tương đương hoàn toàn MVC; tài liệu Boot lưu ý một số tính năng không hỗ trợ trong môi trường reactive.
- Thymeleaf có cấu hình `spring.thymeleaf.reactive.*` để điều khiển chế độ render/chunking trong một số tình huống. Đừng giả định view mặc định phát từng fragment ngay như SSE chỉ vì handler là reactive.
- Nếu model cần dữ liệu từ service, ưu tiên compose publisher non-blocking; tránh gọi `.block()` trong event loop. Cần cân nhắc vòng đời response, hiệu năng render, HTML escaping và response caching.
- Groovy Templates không nằm trong danh sách ba auto-configured WebFlux template engines của Boot 3.3; nếu cần integration custom, đánh giá hỗ trợ framework/phiên bản riêng.

## 13. Kiểm thử output và view resolution

Một endpoint trả status 200 **chưa đủ** chứng minh template được render đúng. Nên xác minh:

1. Request map tới đúng controller.
2. View name, đường prefix/suffix và dependency của engine phù hợp.
3. Model có đủ key và template dùng đúng cú pháp engine.
4. HTTP status, `Content-Type` và body thực sự là HTML.
5. Input không tin cậy được escape đúng; case có Unicode tiếng Việt được hiển thị đúng.
6. File được đóng gói và tìm thấy sau khi chạy JAR thật, không chỉ khi chạy từ IDE.

### Integration test chạy qua embedded HTTP server

Nếu dự án có `spring-boot-starter-test`, có thể đặt file `src/test/java/example/views/ViewsApplicationTests.java` cho ví dụ **MVC + Thymeleaf**:

```java
package example.views;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ViewsApplicationTests {
    @Autowired
    TestRestTemplate http;

    @Test
    void rendersHtmlForModelData() {
        ResponseEntity<String> result =
                http.getForEntity("/greeting?name=Lan", String.class);

        assertThat(result.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(result.getHeaders().getContentType()).isNotNull();
        assertThat(result.getHeaders().getContentType()
                .isCompatibleWith(org.springframework.http.MediaType.TEXT_HTML))
                .isTrue();

        assertThat(result.getBody())
                .contains("Xin chào")
                .contains("Lan")
                .contains("Spring MVC")
                .contains("<li");
    }
}
```

Trong `build.gradle` của dự án Boot thêm:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
```

Chạy `./gradlew test` (hoặc `gradlew.bat test` trên Windows). Test khởi động server với port ngẫu nhiên, gọi endpoint HTTP thật và kiểm tra HTML; với Boot 3.3 và test starter thông thường, `TestRestTemplate` là tiện ích tích hợp phù hợp. Nếu dự án có nhiều main classes hoặc cấu hình riêng, cần chỉ rõ Spring Boot application class trong test.

### Test riêng việc escape

Có thể thêm một assertion với request tên đã URL-encode:

```java
ResponseEntity<String> escaped = http.getForEntity(
        "/greeting?name=%3Cb%3ELan%3C%2Fb%3E",
        String.class);
assertThat(escaped.getBody()).contains("&lt;b&gt;Lan&lt;/b&gt;");
```

Đoạn này là **mảnh code bên trong method test** có sẵn biến `http`, không phải toàn bộ file tự biên dịch. Nếu input là HTML chưa tin cậy mà output chứa thẻ `<b>Lan</b>` thật, cần kiểm tra template có dùng `th:utext` hoặc cơ chế unescaped markup hay không.

## 14. Chẩn đoán auto-configuration và lỗi thường gặp

### 14.1. Trả về đúng chữ "greeting", không có HTML

**Triệu chứng:** Response body là text `greeting`.

**Nguyên nhân điển hình:** controller dùng `@RestController` hoặc method có `@ResponseBody`. Điều này khiến chuỗi return được xử lý như response body.

**Cách sửa:** dùng `@Controller`, trả view name và model; đảm bảo đúng media type khi client yêu cầu HTML.

### 14.2. 404 hoặc lỗi không tìm được template

**Nguyên nhân có thể:** thiếu file tại path, sai chữ hoa/chữ thường, suffix sai, folder không được đóng vào classpath, engine starter chưa có, cấu hình prefix nhầm, hoặc app là web stack khác dự kiến.

**Cách kiểm tra có thứ tự:**

1. Kiểm tra request có match `@GetMapping` không.
2. Kiểm tra view name controller trả ra và file thực tế dưới `src/main/resources/templates`.
3. Kiểm tra `spring.<engine>.prefix`, suffix hoặc template-loader-path.
4. Xác định dependency/starter và file có mặt trong JAR/WAR.
5. Xem exception gốc và log view resolver; không chỉ nhìn một status HTTP.
6. Nếu nhiều engine, kiểm tra resolver nào nhận view name trước.

Lỗi mapping, lỗi view resolution và lỗi trong quá trình render có thể đều làm trang không hiển thị, nhưng **status và exception không nhất thiết giống nhau**. Không gán tất cả lỗi template là 404.

### 14.3. Template không cập nhật khi sửa file

**Nguyên nhân:** engine cache; file lớp tài nguyên chưa được build tool copy; template đang nằm trong JAR; DevTools/IDE chưa refresh classpath.

**Hướng xử lý:** xác nhận file thực tế được nạp, tắt cache thích hợp trong development, cập nhật tài nguyên/restart khi cần. Production nên giữ cache theo nhu cầu và dùng quy trình deploy rõ ràng.

### 14.4. Lỗi parse hoặc expression

Mỗi engine có cú pháp riêng: Thymeleaf `th:text="${name}"`, FreeMarker `${name}`, Mustache `{{name}}`, Groovy Markup dùng cú pháp Groovy. Đổi starter mà không đổi template sẽ dẫn đến parse lỗi hoặc output literal không đúng. Kiểm tra đúng file extension, namespace nếu có, model keys và cách truy cập thuộc tính.

Với FreeMarker, truy cập biến thiếu có thể gây template error tùy biểu thức/default; có thể dùng cú pháp fallback như `${name!"Khách"}` khi thực sự muốn giá trị mặc định. Với Thymeleaf, kiểm soát null/missing model theo yêu cầu trang. Đừng để việc render template tự phát sinh truy vấn database hoặc side effect không kiểm soát chỉ vì gọi object method trong expression.

### 14.5. Hình thành XSS do render dữ liệu thô

- Thymeleaf: `th:text` escape thông thường, `th:utext` không escape.
- FreeMarker: đặt output format HTML/auto escaping, tránh `?no_esc` trên user input.
- Mustache: `{{name}}` escape, triple-mustache hoặc `&` không escape.
- Groovy: xác nhận chế độ escaping và cách chèn giá trị theo output context, không giả định an toàn mặc định.

Escaping HTML text không thay thế việc xử lý **ngữ cảnh JavaScript, CSS, URL, HTML attribute** và validate/sanitize. Không nhúng thẳng dữ liệu không đáng tin vào `<script>` hoặc các URL nguy hiểm rồi cho rằng một engine bất kỳ tự giải quyết mọi trường hợp.

### 14.6. Chạy executable JAR mà view mất

Kiểm tra file có trong `BOOT-INF/classes/templates/...` của archive; dùng đường `classpath:` phù hợp thay vì phụ thuộc working directory. Không dùng JSP trong executable JAR theo hạn chế Boot 3.3. Nếu dùng template trên file system bên ngoài, xác định rõ mount, bảo mật, chiến lược cập nhật và đường dẫn ở runtime.

### 14.7. Khi thấy nhiều resolver hoặc ứng dụng tự đổi web stack

Nếu cùng lúc có nhiều template starters, ghi danh sách actual `ViewResolver` beans và `view-names` để phát hiện xung đột. Nếu ứng dụng bất ngờ chạy MVC thay vì WebFlux, kiểm tra có `spring-boot-starter-web` cùng `spring-boot-starter-webflux` không; Boot mặc định thường ưu tiên MVC khi có cả hai. `spring.main.web-application-type` có thể là cấu hình có chủ đích, không nên thay một cách mò mẫm.

### 14.8. Dùng Condition Evaluation Report

Spring Boot hỗ trợ báo cáo điều kiện auto-configuration khi chạy với `--debug` hoặc cấu hình log phù hợp. Trong môi trường thử nghiệm, có thể thêm:

```bash
./gradlew bootRun --args='--debug'
```

Xem các mục liên quan `ThymeleafAutoConfiguration`, `FreeMarkerAutoConfiguration`, `MustacheAutoConfiguration`, `GroovyTemplateAutoConfiguration`. Đọc điều kiện **matched/not matched** thay vì đoán theo tên dependency. Nếu sử dụng Actuator `conditions` endpoint, kiểm soát quyền truy cập vì nó tiết lộ thông tin cấu hình nội bộ; không mở công khai chỉ để debug template.

## 15. Chọn engine theo nhu cầu thực tế

| Nhu cầu | Lựa chọn thường phù hợp | Điều cần cân nhắc |
|---|---|---|
| Trang HTML server-rendered cùng Spring MVC, form/fragment/validation | Thymeleaf | Cú pháp HTML-friendly, integration mạnh; hiểu escaping và layout/fragment. |
| Template HTML và tài liệu với điều kiện/macro phức tạp | FreeMarker | Kiểm soát output format, escaping, loader path, macro và null handling. |
| Giao diện/notification đơn giản, logic trình bày tối giản | Mustache | Tính rõ ràng, section/partial; xử lý logic trước trong service/controller. |
| Stack đã dùng Groovy và muốn markup template bằng Groovy | Groovy Templates (MVC) | Quản lý runtime Groovy, escaping, cú pháp và giới hạn WebFlux. |
| Dự án JSP cũ cần duy trì | JSP (MVC) | WAR, container support, rủi ro migration; không xem như auto-configured engine trong danh sách bốn. |
| REST API chỉ trả JSON | Không cần template engine | `@RestController`/`@ResponseBody` cùng message converters; tránh thêm starter vô ích. |
| Ứng dụng WebFlux cần HTML server-rendered | Thymeleaf, FreeMarker hoặc Mustache theo khả năng version | Đặc tính reactive/streaming và hiệu năng template; không suy diễn Groovy được auto-config. |

Spring Boot hỗ trợ nhiều engine để chọn công cụ phù hợp, **không có nghĩa phải lắp tất cả**. Mỗi starter thêm dependency và có thể thêm bean/view resolver; chọn ít thành phần nhất đáp ứng yêu cầu sẽ dễ hiểu và kiểm thử hơn.

## 16. Bài thực hành tự kiểm tra

**Bài A — Đổi template path:** Chuyển `greeting.html` từ `templates/` sang `views/`, đặt `spring.thymeleaf.prefix=classpath:/views/`. Giữ `return "greeting"`. Kỳ vọng endpoint vẫn render thành công khi file được đóng gói vào classpath.

**Bài B — Phân biệt view và body:** Tạm đổi `@Controller` thành `@RestController` ở ví dụ MVC, gọi `/greeting`. Hãy giải thích vì sao output thành chữ `greeting`. Sau đó đổi lại `@Controller`.

**Bài C — Đổi engine:** Bỏ Thymeleaf starter, thêm Mustache starter, dùng `greeting.mustache`. Kiểm tra phần tử danh sách được render qua `{{#topics}}` và `{{.}}`, không cần đổi controller.

**Bài D — Kiểm tra escaping:** Gửi `name=%3Cscript%3Ealert(1)%3C%2Fscript%3E` qua `curl`; xác minh output HTML **không** chứa thẻ script thực thi. Đối chiếu việc escape trong từng engine và tránh cấu hình render raw.

**Bài E — Đọc auto-config conditions:** Chạy ứng dụng với `--debug`, tìm engine auto-configuration match, giải thích dependency/bean/property đã kích hoạt. Sau đó tắt `spring.thymeleaf.enabled` trong test profile và xem ảnh hưởng đến view resolution.

**Bài F — So sánh MVC và WebFlux:** Trong project riêng chỉ dùng WebFlux starter, thêm Thymeleaf và một `@Controller` trả view name. Giải thích tại sao server không dùng `DispatcherServlet` và vì sao phần tạo HTML vẫn có chi phí xử lý.

### Câu hỏi ôn tập

**1. Spring Boot 3.3 tự cấu hình bao nhiêu engine template cho MVC?**  
Bốn: Thymeleaf, FreeMarker, Mustache, Groovy Templates.

**2. JSP có cùng cơ chế auto-configured starter và chạy executable JAR như Thymeleaf không?**  
Không. JSP nằm trong Servlet/JSP integration, có hạn chế WAR/JAR và container trong Boot 3.3.

**3. `@RestController` trả `"hello"` có render file `hello.html` không?**  
Không. `@RestController` đặt `@ResponseBody` semantics, nên chuỗi được gửi như body. `@Controller` mới phù hợp với view name.

**4. FreeMarker mặc định dùng `spring.freemarker.prefix=classpath:/templates/` đúng không?**  
Không hẳn. FreeMarker dùng **`template-loader-path=classpath:/templates/`** và `prefix` thường rỗng. Đây là hai thuộc tính khác nhau.

**5. Vì sao tắt template cache mà file vừa sửa vẫn chưa hiển thị?**  
Vì file nguồn có thể chưa được copy vào classpath đang chạy, hoặc app đang nạp template trong JAR; cache không phải tầng duy nhất.

**6. WebFlux auto-config Groovy Templates giống MVC không?**  
Không theo danh sách auto-configuration Boot 3.3; WebFlux có FreeMarker, Thymeleaf và Mustache.

**7. Khi dùng hai template engine, chỉ đặt cả hai starter là đủ tránh xung đột?**  
Không. Phải kiểm tra view resolver conditions, view name patterns, thứ tự resolver và file/resource path.

**8. Nếu một template nhận dữ liệu từ user, chức năng nào phải kiểm tra kỹ?**  
Escaping theo **ngữ cảnh output**, tránh raw HTML hoặc JavaScript injection, validate/sanitize input khi thích hợp.

## 17. Tài liệu đối chiếu chính thức

- [Spring Boot 3.3 — Servlet Web Applications: Template Engines](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html#web.servlet.spring-mvc.template-engines): danh sách engine tự cấu hình của MVC và vị trí template mặc định.
- [Spring Boot 3.3 — Reactive Web Applications: Template Engines](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html#web.reactive.webflux.template-engines): danh sách engine và giới hạn trên WebFlux.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): prefix, suffix, template path, caching và các thuộc tính từng engine.
- [Spring Boot — How-to: Customize ViewResolvers](https://docs.spring.io/spring-boot/3.3/how-to/spring-mvc.html): beans của resolver và cách tùy chỉnh view resolution.
- [Spring Framework — MVC View Technologies](https://docs.spring.io/spring-framework/reference/web/webmvc-view.html): cách Spring MVC tích hợp các công nghệ view.
- [Thymeleaf — Using Thymeleaf](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html): biểu thức, `th:text`, escaping và template mode.
- [Apache FreeMarker — Manual](https://freemarker.apache.org/docs/index.html): `.ftlh`, output formats, auto escaping, expressions và macro.
- [Mustache Specification](https://mustache.github.io/mustache.5.html): variables, sections và HTML escaping.
- [Groovy — Markup Template Engine](https://docs.groovy-lang.org/latest/html/documentation/template-engines.html#_the_markuptemplateengine): cú pháp template Groovy và thiết lập render.

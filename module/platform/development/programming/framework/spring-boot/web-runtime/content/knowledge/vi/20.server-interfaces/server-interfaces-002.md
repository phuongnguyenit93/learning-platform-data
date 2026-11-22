# ViewResolver và thứ tự tìm giao diện trong Spring Boot web runtime

> **Ngữ cảnh:** menu cha **Giao diện máy chủ**; trọng tâm là server-side rendered HTML với **Spring MVC** trên Servlet stack. Nội dung cũng chỉ ra khác biệt quan trọng với Spring WebFlux. Ví dụ thực hành dùng Spring Boot **4.1.2**, Java **17+**, Maven và Thymeleaf. Trong Spring Boot 3.x, thông thường starter MVC có tên `spring-boot-starter-web`; ở Boot 4.x có starter `spring-boot-starter-webmvc`. Các giá trị order, bean và auto-configuration thực tế cần kiểm tra theo phiên bản và cấu hình ứng dụng.

## Mục tiêu

Sau bài học, bạn có thể:

1. Giải thích vai trò của `ViewResolver`, `View`, *logical view name*, `Model` và bước render HTML.
2. Phân biệt **mapping route đến controller** với **mapping view name đến giao diện**; biết khi nào Spring MVC có và không có bước resolve view.
3. Mô tả **thứ tự thử nhiều ViewResolver**, ý nghĩa của `Ordered`/`order`, giá trị `null` khi không giải được, lý do JSP resolver cần đứng cuối.
4. Hiểu cách Spring Boot tự cấu hình Thymeleaf, FreeMarker, JSP và `ContentNegotiatingViewResolver`; phân biệt **ViewResolver của MVC** với **TemplateResolver bên trong Thymeleaf**.
5. Chạy một ứng dụng MVC trả HTML từ templates, chuyển hướng bằng `redirect:` và có một ViewResolver tùy chỉnh có ưu tiên cao hơn để thấy đường đi thực tế.
6. Chẩn đoán những lỗi như template không tìm thấy, một resolver chiếm tên view của resolver khác, 404/500, `@RestController` trả tên template thành text, và cấu hình prefix/suffix sai.

## 1. Vị trí của ViewResolver trong pipeline MVC

Giả sử browser gửi:

~~~http
GET /pages/welcome?name=Lan HTTP/1.1
Host: localhost:8080
Accept: text/html
~~~

Một controller có thể trả về chuỗi **tên giao diện logic** `"pages/welcome"` cùng một model chứa `name="Lan"`. Chuỗi này **không trực tiếp là file** và không phải nội dung HTML. `ViewResolver` giúp framework tìm một `View` để render template với model.

~~~text
Browser gửi GET /pages/welcome?name=Lan
             |
             v
Servlet container / DispatcherServlet
             |
             v
HandlerMapping tìm method @GetMapping("/pages/welcome")
             |
             v
HandlerAdapter gọi @Controller
             |
             +--> model.put("name", "Lan")
             +--> trả logical view name "pages/welcome"
             |
             v
ViewResolver chain (theo priority)
   resolver 1 -> null nếu không phù hợp
   resolver 2 -> View nếu tìm/nhận diện được
   resolver 3 -> chỉ được thử nếu cần
             |
             v
View.render(model, request, response)
   -> Thymeleaf dùng template pages/welcome.html
   -> th:text đưa tên Lan vào HTML an toàn
             |
             v
HTTP 200 + Content-Type: text/html + HTML body
~~~

Các trách nhiệm riêng:

| Thành phần | Nhận cái gì? | Trả hoặc thực hiện cái gì? |
| --- | --- | --- |
| `HandlerMapping` | Method/path/header của HTTP request | Chọn handler/controller; **chưa** chọn template |
| `HandlerAdapter` | Handler đã tìm được | Gọi handler, thu thập return value/model |
| `@Controller` + `Model` | Dữ liệu request/nghiệp vụ | Trả tên view logic và dữ liệu để hiển thị |
| `ViewResolver` | Logical view name, `Locale` và bối cảnh thích hợp | Trả đối tượng `View` hoặc `null` nếu không giải được |
| `View` | Model + request/response | Thực hiện render/forward/redirect theo view technology |
| Template engine | Template path + model | Tạo HTML hoàn chỉnh, xử lý expressions/fragments |
| Servlet response | Status, headers, nội dung | Gửi bytes về client |

**Điểm ranh giới:** `DispatcherServlet` điều phối nhiều bước, nhưng việc nhìn thấy URL `/pages/welcome` không đồng nghĩa có file `/pages/welcome.html`. **Controller quyết định view name**; resolver/engine và prefix/suffix quyết định tài nguyên thực tế.

### Ba đường đi trả kết quả khác nhau

~~~java
// Đoạn trích để so sánh; các import và lớp chưa trình bày ở đây.
@Controller
class PageController {
    @GetMapping("/page")
    String page(Model model) {
        model.addAttribute("message", "Xin chào");
        return "pages/home"; // logical view name -> ViewResolver
    }

    @GetMapping("/go")
    String go() {
        return "redirect:/page"; // yêu cầu redirect, không render file "redirect:"
    }
}

@RestController
class ApiController {
    @GetMapping("/api/message")
    String message() {
        return "pages/home"; // BODY là chính chuỗi "pages/home"
    }
}
~~~

Với `@RestController` (tương đương `@Controller` + `@ResponseBody`), `String` ở method thường được viết thẳng vào response body qua HTTP message converter, **không** đi qua resolver để tìm HTML. Với `@Controller` và return `String` không có `@ResponseBody`, chuỗi được hiểu là logical view name. Đây là nguồn gây lỗi rất thường gặp khi học SSR.

Controller cũng có thể trả `ModelAndView` chứa view name + model; `View` cụ thể; hoặc các kiểu HTTP body như `ResponseEntity<T>`. Không phải mọi return type đều kích hoạt cùng cơ chế resolve view. Ví dụ trả `ResponseEntity<String>` sẽ ghi body, không có bước tìm Thymeleaf template.

## 2. ViewResolver là hợp đồng gì?

Ở **Spring MVC (Servlet)**, giao diện chính là:

~~~java
// Hình dạng API để hiểu hợp đồng, không phải class ứng dụng cần viết lại.
public interface ViewResolver {
    View resolveViewName(String viewName, Locale locale) throws Exception;
}
~~~

Hợp đồng cho phép trả `null` nếu resolver không phù hợp với tên view. Framework có thể hỏi resolver kế tiếp trong chuỗi. Không phải resolver nào cũng kiểm tra được tài nguyên tồn tại trước khi tạo `View`; điều đó ảnh hưởng trực tiếp đến thứ tự.

Ví dụ logical view name `"pages/welcome"` với Thymeleaf:

~~~text
viewName                    = pages/welcome
spring.thymeleaf.prefix     = classpath:/templates/
spring.thymeleaf.suffix     = .html

Tài nguyên được tìm        = classpath:/templates/pages/welcome.html
~~~

Đây là quy tắc thường gặp với Thymeleaf auto-configuration. Nếu bạn đổi `spring.thymeleaf.prefix=classpath:/views/`, tài nguyên cần nằm ở `src/main/resources/views/pages/welcome.html` (trong project Maven chuẩn), dù URL của controller không phải đổi.

Một resolver có thể tự biết rằng nó **không** xử lý view name thuộc nhóm nào đó bằng cấu hình `viewNames`/`excludedViewNames` hoặc quy tắc riêng. Cách này quan trọng khi cùng ứng dụng có nhiều engine hoặc nhiều layout: resolver chuyên biệt chỉ nhận nhóm view mà nó xử lý.

## 3. Thứ tự tìm: số `order` thấp ưu tiên trước

Khi nhiều `ViewResolver` cùng có mặt, MVC sắp xếp theo thứ tự ưu tiên, thường qua `Ordered` hoặc annotation tương ứng. **Số order càng nhỏ thì ưu tiên càng cao**:

~~~text
Ordered.HIGHEST_PRECEDENCE  = -2147483648  (ưu tiên rất cao)
order -100                 = ưu tiên hơn 0
order 0
order 10
order 100
Ordered.LOWEST_PRECEDENCE   = 2147483647  (ưu tiên rất thấp)
~~~

Mô hình tư duy đơn giản cho **chuỗi resolver thông thường**:

~~~java
// Pseudocode để hiểu quy tắc, không phải mã DispatcherServlet.
for (ViewResolver resolver : sortedResolvers) {
    View view = resolver.resolveViewName(viewName, locale);
    if (view != null) {
        return view;
    }
}
throw new IllegalStateException("No matching View");
~~~

Pseudocode nói lên quy tắc ưu tiên và fallback; **không mô tả đầy đủ** các resolver tổng hợp như `ContentNegotiatingViewResolver`. Resolver tổng hợp có thể truy vấn **nhiều resolver thành viên** rồi chọn một View theo media type, không đơn thuần dừng ở resolver đầu tiên trả non-null.

### Khi nào “fallback” thực sự xảy ra?

- Resolver A **không phù hợp hoặc không giải được view** và trả `null` → MVC thử resolver tiếp theo.
- Resolver A trả một `View`, nhưng View đó **không render thành công** khi đã chọn → thường phát sinh lỗi render/response; không có cam kết Spring sẽ quay lại thử resolver B.
- Hai resolver cùng giải được một tên view → thứ tự và, nếu có, content negotiation ảnh hưởng đến lựa chọn; cần tránh pattern chồng nhau hoặc thiết lập thứ tự rõ ràng.
- Hai resolver có **cùng order** → không thiết kế dựa vào thứ tự ngẫu nhiên/không được bảo đảm giữa các bean; chủ động đặt giá trị phân biệt.

**Không gán mã 404/500 chỉ từ việc một resolver trả `null`**. HTTP status cuối cùng phụ thuộc việc handler có tồn tại hay không, trình xử lý exception và giai đoạn lỗi. Route không khớp thường là 404; route khớp nhưng template render lỗi thường dẫn đến lỗi server. Tuy nhiên routing hoặc view resolving có thể được tùy chỉnh, nên cần đọc exception/log thực tế.

### Vì sao `InternalResourceViewResolver` nên đứng cuối?

`InternalResourceViewResolver` thường xây một Servlet/JSP view từ logical name + prefix/suffix. Với JSP, nó không thể chắc chắn tài nguyên có tồn tại hay không chỉ bằng việc tạo `View`: kiểm tra thực tế xảy ra khi `RequestDispatcher.forward(...)`. Bởi vậy, nó có thể **trả một View ngay cả khi JSP vật lý không tồn tại** và ngăn các resolver sau được thử. Tài liệu Spring Framework nhấn mạnh **đặt InternalResourceViewResolver cuối chuỗi**.

Ví dụ sai:

~~~text
order 0   : InternalResourceViewResolver (tìm JSP bằng tên)
order 10  : ThymeleafViewResolver

controller trả "pages/welcome":
InternalResourceViewResolver có thể trả InternalResourceView
-> không đến được Thymeleaf như mong đợi
-> dispatch đến JSP/resource sai hoặc lỗi.
~~~

Cấu hình hợp lý khi buộc phải mix:

~~~text
Resolver chuyên biệt: chỉ nhận "admin/*" hoặc một nhóm được định nghĩa rõ
Thymeleaf/FreeMarker: nhận logical names tương ứng
InternalResourceViewResolver: fallback cuối nếu còn dùng JSP/Servlet views
~~~

Lưu ý đây là **cách tổ chức ưu tiên**, không phải các order number mặc định cố định cho mọi phiên bản Boot. Với JSP trên Spring Boot executable **JAR**, khả năng hỗ trợ bị giới hạn; thông thường chọn template engine hoặc WAR phù hợp, không thêm JSP chỉ để minh họa thứ tự.

## 4. Các resolver điển hình và ý nghĩa

| Loại | Vai trò | Khi nào nên dùng / điểm cần cảnh giác |
| --- | --- | --- |
| `ThymeleafViewResolver` | Map logical view name đến `ThymeleafView` để xử lý HTML/template | Web page SSR; cần Thymeleaf starter và template resource phù hợp |
| `FreeMarkerViewResolver` | Render template FreeMarker | Khi ứng dụng chọn FreeMarker; prefix/suffix và loader path khác Thymeleaf |
| `InternalResourceViewResolver` | Xây internal view/forward đến JSP hoặc tài nguyên Servlet | Cần đặt cuối; không phải cơ chế phục vụ mọi static file |
| `BeanNameViewResolver` | View name khớp tên một bean loại `View` | Trường hợp view đặc biệt, ví dụ view tùy chỉnh hoặc report |
| `ContentNegotiatingViewResolver` | Chọn View theo media type client mong muốn, thường qua `Accept` | Resolver tổng hợp; **không phải template engine** |
| Custom `ViewResolver` | Quyết định view theo logic riêng, có thể trả `null` | Chỉ dùng khi nhu cầu rõ; phải kiểm soát order, cache, tên và content type |
| `UrlBasedViewResolver` | Cơ sở map view name thành URL qua prefix/suffix | Chỉ phù hợp khi URL mapping đủ đơn giản; lớp con có chính sách tồn tại tài nguyên khác nhau |

Không cần khai báo toàn bộ các resolver thủ công. Với starter MVC và template engine thích hợp, Spring Boot tự cấu hình phần lớn đường đi. Chỉ can thiệp khi mặc định không thể mô tả logic view routing của ứng dụng.

### `ContentNegotiatingViewResolver` không có nghĩa “thử theo order đến đầu tiên”

Giả sử một endpoint có thể trả HTML hoặc một dạng report khác. Client có:

~~~http
Accept: text/html
~~~

Khi được cấu hình, `ContentNegotiatingViewResolver` có thể hỏi các resolver khác để có những `View` candidate rồi chọn View phù hợp với media type được yêu cầu. Nó thường được đặt **ưu tiên rất cao** để điều phối các resolver khác.

Đừng giả định chỉ cần khai báo `@Bean ViewResolver order=-999` thì luôn đứng trước mọi hành vi content negotiation. Boot có thể cung cấp một resolver tổng hợp với `Ordered.HIGHEST_PRECEDENCE` và resolver này lại gọi các resolver thành viên. Vì vậy “thứ tự” có **hai tầng**:

1. Thứ tự giữa các resolver mà MVC xử lý ở cấp ngoài.
2. Thứ tự và tiêu chí lựa chọn **bên trong resolver tổng hợp** theo view candidate và `Accept`.

Nếu hệ thống chỉ cần HTML từ Thymeleaf và JSON từ REST, kiến trúc đơn giản là **tách route HTML dùng `@Controller`** và **route JSON dùng `@RestController`/`@ResponseBody`**, thay vì thêm một tổ hợp content negotiation chỉ để route API.

### Không nhầm ba cơ chế khác nhau

| Cơ chế | Input | Output |
| --- | --- | --- |
| `HandlerMapping` | URL/method/headers của HTTP request | Handler/controller method |
| Spring MVC `ViewResolver` | Logical view name, `Locale` | Spring MVC `View` |
| Thymeleaf **TemplateResolver** | Tên template, locale, template mode, chính sách engine | Tài nguyên/template để Thymeleaf xử lý |

Thuộc tính `spring.thymeleaf.template-resolver-order` liên quan **thứ tự template resolver bên trong Thymeleaf** khi có nhiều template resolvers. Nó **không tương đương** với `order` của Spring MVC `ViewResolver`; đổi thuộc tính này không có nghĩa đổi ưu tiên Thymeleaf so với JSP ViewResolver.

## 5. Spring Boot tự cấu hình view resolution thế nào?

Thường bạn thêm:

- `spring-boot-starter-webmvc`: cấu hình Servlet web runtime và Spring MVC cho Boot 4.x.
- `spring-boot-starter-thymeleaf`: thêm Thymeleaf integration và auto-configuration tương ứng.

Với template ở `src/main/resources/templates/`, Boot thường sử dụng prefix `classpath:/templates/` và suffix `.html`. Khi bạn trả `"pages/welcome"`, ứng dụng tìm `templates/pages/welcome.html`.

Một số thuộc tính Thymeleaf quan trọng:

~~~properties
# Thường đây là giá trị mặc định; ghi ra để dễ quan sát.
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.enabled=true

# Dành cho phát triển để thấy thay đổi template khi chạy lại/tùy devtools.
# Nên bật cache trong production nếu không có yêu cầu cập nhật nóng.
spring.thymeleaf.cache=false
~~~

Không nhầm `spring.mvc.view.prefix` / `spring.mvc.view.suffix` với `spring.thymeleaf.prefix` / `spring.thymeleaf.suffix`. Nhóm `spring.mvc.view.*` gắn với internal/JSP view resolver; Thymeleaf dùng nhóm property riêng.

Boot có thể khai báo `ContentNegotiatingViewResolver`, `BeanNameViewResolver` và default internal-resource resolver cùng các resolver do template starter cung cấp. Số lượng bean, order, điều kiện auto-configuration và tên chính xác có thể thay đổi theo phiên bản, các dependency và bean ứng dụng tự định nghĩa; **đừng xây business logic dựa trên bảng order mặc định thuộc một bản Boot cũ**.

**Chính sách an toàn:** Template file nằm ở ranh giới **code/trust** của ứng dụng, có khả năng truy cập model và bean tùy tích hợp. Đừng cho người dùng tải lên/sửa trực tiếp template thực thi của server. Không đưa chuỗi query parameter làm tên view tùy ý: ví dụ `return request.getParameter("view")` có thể dẫn đến truy cập tài nguyên không mong muốn hoặc view injection. Ánh xạ input qua danh sách tên view được cho phép.

## 6. Ví dụ chạy được: Thymeleaf và ViewResolver ưu tiên cao

Mục tiêu của ứng dụng demo:

- `GET /pages/welcome?name=Lan` → controller trả `"pages/welcome"` → custom resolver **trả null** → Thymeleaf render template HTML.
- `GET /pages/about` → Thymeleaf render template khác.
- `GET /pages/plain` với `Accept: text/plain` → controller trả `"special/plain"` → resolver ứng dụng trả **custom View** → nội dung plain text.
- `GET /pages/start` → redirect HTTP đến trang welcome.
- `GET /api/ping` → REST body JSON; không dùng ViewResolver để tìm template.

Đây là **một dự án độc lập**, sử dụng Spring Boot 4.1.2, Java 17 và Maven 3.6.3+.

### Cấu trúc thư mục

~~~text
view-resolver-demo/
  pom.xml
  src/main/java/com/example/viewdemo/
    ViewDemoApplication.java
    PageController.java
    ApiController.java
    PriorityViewConfig.java
  src/main/resources/
    application.properties
    templates/pages/welcome.html
    templates/pages/about.html
~~~

### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>view-resolver-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

Parent Boot chọn bộ dependency tương thích. Starter MVC dùng server Tomcat nhúng theo mặc định. Starter Thymeleaf cung cấp view engine để tìm và render template.

### `ViewDemoApplication.java`

~~~java
package com.example.viewdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ViewDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ViewDemoApplication.class, args);
    }
}
~~~

Class chính cùng package cha của controllers/config, giúp component scan đăng ký chúng.

### `PageController.java`

~~~java
package com.example.viewdemo;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class PageController {

    @GetMapping("/pages/welcome")
    public String welcome(
            @RequestParam(defaultValue = "Khách") String name,
            Model model) {
        model.addAttribute("name", name);
        return "pages/welcome";
    }

    @GetMapping("/pages/about")
    public String about(Model model) {
        model.addAttribute("product", "Spring Boot");
        return "pages/about";
    }

    @GetMapping("/pages/plain")
    public String plain(Model model) {
        model.addAttribute("message", "View do ứng dụng tự render");
        return "special/plain";
    }

    @GetMapping("/pages/start")
    public String start() {
        return "redirect:/pages/welcome?name=Lan";
    }
}
~~~

Không dùng `@ResponseBody` cho các method trả tên template. Giá trị ở model **không quyết định view**; view được chọn bởi `return "pages/welcome"`. Các chuỗi `"pages/*"` đều được Thymeleaf giải quyết nhờ template files ở thư mục tương ứng.

### `ApiController.java`

~~~java
package com.example.viewdemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
~~~

HTTP response body là JSON, ví dụ `{"status":"ok"}`. Đây là mã đối chiếu để phân biệt việc ghi HTTP body qua message converter với việc resolve HTML template.

### `PriorityViewConfig.java` — một resolver có thứ tự rõ ràng

~~~java
package com.example.viewdemo;

import java.util.Locale;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.servlet.View;
import org.springframework.web.servlet.ViewResolver;
import org.springframework.web.servlet.view.AbstractView;

@Configuration(proxyBeanMethods = false)
public class PriorityViewConfig {

    @Bean
    ViewResolver priorityViewResolver() {
        return new PriorityResolver();
    }

    // Resolver này chỉ nhận tên "special/plain"; tên khác trả null.
    static final class PriorityResolver implements ViewResolver, Ordered {
        private final View plainView = new PlainTextView();

        @Override
        public int getOrder() {
            return -100; // số nhỏ hơn -> ưu tiên cao hơn
        }

        @Override
        public View resolveViewName(String viewName, Locale locale) {
            return "special/plain".equals(viewName) ? plainView : null;
        }
    }

    // View tự ghi response: có thể xem như một renderer rất đơn giản.
    static final class PlainTextView extends AbstractView {
        PlainTextView() {
            setContentType("text/plain;charset=UTF-8");
        }

        @Override
        protected void renderMergedOutputModel(
                Map<String, Object> model,
                HttpServletRequest request,
                HttpServletResponse response) throws Exception {
            response.setContentType(getContentType());
            response.getWriter().write(
                    String.valueOf(model.getOrDefault("message", "")));
        }
    }
}
~~~

Điểm đáng chú ý:

- `PriorityResolver` hiện thực cả `ViewResolver` và `Ordered` để công bố thứ tự. Số `-100` có ý nghĩa **ưu tiên trước các resolver có order lớn hơn**, nhưng Boot có thể có `ContentNegotiatingViewResolver` tổng hợp với ưu tiên cao hơn; resolver tổng hợp có thể hỏi `PriorityResolver` như một delegate. Không nên diễn giải `-100` là “chắc chắn method được gọi đầu tiên trong mọi phiên bản”.
- Với `"special/plain"`, resolver trả `PlainTextView`; với `"pages/welcome"`, trả `null` để resolver khác tiếp tục.
- `PlainTextView` lấy giá trị `message` trong model và ghi body text/plain. Đây là ví dụ didactic, **không phải engine template cần dùng production**.
- `@Configuration(proxyBeanMethods = false)` phù hợp vì code không cần gọi trực tiếp @Bean method từ một @Bean method khác.
- Custom resolver chỉ nắm một tên view; pattern này tránh “giành” các template Thymeleaf thông thường.

### `application.properties`

~~~properties
server.port=8080
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.cache=false
~~~

Thực hành dùng cache false để dễ thử sửa template; production nên xem lại theo nhu cầu vận hành. Nếu có biến môi trường hoặc command-line argument ghi đè property, giá trị hiệu lực có thể khác file này.

### Template `src/main/resources/templates/pages/welcome.html`

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Trang chào</title>
</head>
<body>
    <h1>Xin chào, <span th:text="${name}">Khách</span>!</h1>
    <p>Trang này được render ở máy chủ bằng Thymeleaf.</p>
    <a href="/pages/about">Giới thiệu</a>
</body>
</html>
~~~

`th:text="${name}"` lấy model attribute; Thymeleaf mặc định escape nội dung theo ngữ cảnh văn bản HTML. Nếu client gửi `name=<script>...`, nó không được đưa thẳng thành markup khi dùng `th:text`. Không chuyển sang `th:utext` cho input không tin cậy.

### Template `src/main/resources/templates/pages/about.html`

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Giới thiệu</title>
</head>
<body>
    <h1 th:text="${product}">Sản phẩm</h1>
    <p>Giao diện HTML được tìm từ tên logic <code>pages/about</code>.</p>
    <a href="/pages/welcome?name=Lan">Về trang chào</a>
</body>
</html>
~~~

### Chạy và quan sát

Trong thư mục `view-resolver-demo`:

~~~bash
mvn spring-boot:run
~~~

Terminal khác:

~~~bash
curl -i -H "Accept: text/html" \
  "http://localhost:8080/pages/welcome?name=Lan"
~~~

Kỳ vọng **HTTP 200**, Content-Type HTML và body có đoạn:

~~~html
<h1>Xin chào, <span>Lan</span>!</h1>
~~~

Những phần HTML khác vẫn nằm trong body; header như Date/Transfer-Encoding có thể khác.

~~~bash
curl -i -H "Accept: text/html" http://localhost:8080/pages/about
~~~

Kỳ vọng trang Giới thiệu với nội dung `Spring Boot` trong thẻ `h1`. Cả hai trang đều được Thymeleaf render qua logical view name.

~~~bash
curl -i -H "Accept: text/plain" http://localhost:8080/pages/plain
~~~

Kỳ vọng HTTP 200, Content-Type `text/plain;charset=UTF-8` và body chính xác:

~~~text
View do ứng dụng tự render
~~~

Đây là **View** do `PriorityResolver` tạo, không cần file `templates/special/plain.html`. Yêu cầu `Accept: text/plain` giúp tránh mơ hồ khi có content-negotiating resolver giữa nhiều dạng view.

~~~bash
curl -i http://localhost:8080/pages/start
~~~

Kỳ vọng response redirect (thường HTTP 302) và `Location` trỏ tới `/pages/welcome?name=Lan`. Dùng `curl -i -L ...` để theo redirect và nhận HTML; không có template file `redirect:/pages/welcome?name=Lan.html`.

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/ping
~~~

Kỳ vọng HTTP 200 và body JSON có trường `status` là `ok`. Route này không đi qua Thymeleaf ViewResolver.

Trên Windows PowerShell 5.1, dùng `curl.exe` để đảm bảo chạy cURL thực, ví dụ `curl.exe -i "http://localhost:8080/pages/welcome?name=Lan"`. Có thể build JAR bằng:

~~~bash
mvn package
java -jar target/view-resolver-demo-0.0.1-SNAPSHOT.jar
~~~

Mã Java cần build bằng Maven vì phụ thuộc Spring/Thymeleaf không nằm sẵn trên classpath của `javac` trần. Khi chạy JAR, template nằm trên classpath tại `BOOT-INF/classes/templates/...` trong archive do Spring Boot package.

### Những gì ví dụ xác minh

| URL | Logical name hoặc return | Kết quả cần quan sát |
| --- | --- | --- |
| `/pages/welcome?name=Lan` | `pages/welcome` | Thymeleaf chọn template `pages/welcome.html` và render model |
| `/pages/about` | `pages/about` | Thymeleaf render trang Giới thiệu |
| `/pages/plain` | `special/plain` | Custom resolver trả View text/plain |
| `/pages/start` | `redirect:/pages/welcome?name=Lan` | Chuyển hướng HTTP; không tìm file `redirect:*` |
| `/api/ping` | `Map<String,String>` từ `@RestController` | JSON body qua message conversion, không dùng view lookup |

Nếu muốn chứng minh fallback trong runtime thật, đặt breakpoint hoặc logging tại `PriorityResolver.resolveViewName(...)` và xem `viewName` của những request HTML. **Lưu ý** `ContentNegotiatingViewResolver` có thể gọi lại resolver như delegate hoặc thử nhiều candidate, vì vậy **không assert số lần gọi chính xác**; hãy kiểm tra View thực tế được dùng và nội dung HTTP.

## 7. Điều gì xảy ra nếu có nhiều template engine?

Giả sử dự án cùng tích hợp Thymeleaf và FreeMarker:

~~~text
src/main/resources/templates/pages/welcome.html
src/main/resources/templates/pages/report.ftlh
~~~

Khi controller trả `"pages/report"`, hai resolver có thể được hỏi. Nếu cả hai resolver cấu hình nhận mọi tên, việc chọn có thể lệ thuộc thứ tự, cơ chế tồn tại tài nguyên và content negotiation. Thiết kế tốt là **phân vùng view name** rõ ràng:

~~~text
pages/*    -> Thymeleaf
report/*   -> FreeMarker
special/*  -> View bean hoặc custom resolver
JSP        -> fallback cuối (nếu dự án thật sự cần)
~~~

Đây là quy ước thiết kế, không tự động có hiệu lực chỉ vì thêm tên folder. Bạn phải cấu hình các resolver/engine để chúng **chỉ nhận các pattern phù hợp**, ví dụ `viewNames`/`excludedViewNames` nếu resolver hỗ trợ, và đặt order hợp lý. Không nên có hai resolver cùng “luôn khẳng định xử lý được” mọi tên template.

Ví dụ **minh họa cấu hình** ở một dự án có FreeMarker và Thymeleaf (không ghép thêm trực tiếp vào demo trên nếu chưa cài engine và cân nhắc auto-configuration):

~~~java
// Minh họa: giả sử bạn có ThymeleafViewResolver là bean đã tạo.
// Không bắt buộc phải chỉnh order trong ứng dụng chỉ có một engine.
thymeleafViewResolver.setViewNames(new String[] {"pages/*"});
thymeleafViewResolver.setOrder(10);

// Giả sử FreeMarkerViewResolver đã có dependency và template loader đúng:
freeMarkerViewResolver.setViewNames("reports/*");
freeMarkerViewResolver.setOrder(20);

// Trường hợp JSP cần fallback:
internalResourceViewResolver.setOrder(Ordered.LOWEST_PRECEDENCE);
~~~

Đoạn này **không phải class độc lập chạy được**, chỉ làm rõ nguyên tắc cài view-name pattern/order khi ứng dụng có nhiều engine. Đừng nhầm `spring.thymeleaf.view-names` với `spring.thymeleaf.template-resolver-order`, và tránh thay đổi bean auto-config bằng tên/order tùy ý khi chưa biết phiên bản thực tế.

### Phân biệt view resolution và static resource mapping

- Template `src/main/resources/templates/pages/welcome.html` thường **không được serve như static file**. Nó được engine tìm theo logical view name và render model.
- File `src/main/resources/static/css/site.css` thường được phục vụ trực tiếp qua **static resource handler** khi client gọi `/css/site.css`.
- Trả `"css/site"` từ `@Controller` **không** có nghĩa sẽ tự tìm `static/css/site.css` như một template.

Khi debug, cần biết request được xử lý bởi `RequestMappingHandlerMapping` của controller hay `ResourceHttpRequestHandler` của static resources; chúng là hai con đường khác nhau.

## 8. Redirect, forward và view name đặc biệt

Spring MVC hỗ trợ view name với tiền tố đặc biệt:

- `redirect:/pages/welcome`: tạo HTTP redirect cho client thực hiện request mới; status thường 302 trừ khi chọn redirect status khác. Dữ liệu model/flash attributes cần được thiết kế riêng nếu muốn truyền qua redirect.
- `forward:/internal/path`: yêu cầu Servlet forward bên trong server, **không** gửi 3xx để browser đổi URL. Với các resolver dựa trên `UrlBasedViewResolver`, đây là `InternalResourceView`/`RequestDispatcher.forward`. Nó không đồng nghĩa với render Thymeleaf view path.
- `"pages/welcome"`: logical view bình thường được resolution chain xử lý.

Nếu muốn truyền dữ liệu qua redirect, dùng `RedirectAttributes` để gắn query/path variables được phép hoặc flash attributes. Không nhét dữ liệu nhạy cảm vào query string; không lưu vô hạn vào HTTP session chỉ vì nhiều trang share model.

**Về security:** tránh redirect URL người dùng cung cấp trực tiếp mà không kiểm soát, ví dụ `return "redirect:" + request.getParameter("next")`. Điều này có thể tạo open redirect. Chỉ cho phép đường dẫn nội bộ hoặc kiểm tra target theo allowlist.

## 9. ViewResolver trong Spring WebFlux khác gì?

WebFlux có cách chọn handler khác ở tầng reactive, nhưng vẫn có khái niệm **view name → view rendering**:

| Khía cạnh | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Front controller | `DispatcherServlet` | `DispatcherHandler` |
| ViewResolver interface | `org.springframework.web.servlet.ViewResolver` | `org.springframework.web.reactive.result.view.ViewResolver` |
| Kết quả resolver | `View` hoặc `null` | `Mono<View>` (có thể empty nếu không resolve được) |
| Thành phần render view | MVC view handling, `View.render(...)` của Servlet stack | `ViewResolutionResultHandler` với reactive `View` |
| Template engine | Thymeleaf/FreeMarker và các view tech được cấu hình | Engine tương thích WebFlux; có cấu hình khác MVC |
| JSP | Có thể dùng Servlet/JSP nhưng hạn chế theo packaging | Không áp dụng JSP resolver như trên Servlet stack |
| Cơ chế I/O | Servlet/MVC request execution | Pipeline Publisher/Subscriber, non-blocking integration |

Trong WebFlux, `HandlerResult` có return value và model; `ViewResolutionResultHandler` dùng các resolver để chọn view theo logical name. Người viết handler có thể trả `String` là view name trong ngữ cảnh tương ứng, nhưng không được copy đoạn code dùng `jakarta.servlet.http.HttpServletResponse` và `InternalResourceViewResolver` từ MVC sang WebFlux. Đó là **hai giao diện cùng tên nhưng package và semantics khác nhau**.

Tài liệu WebFlux cũng cảnh báo template view có quyền truy cập thông tin/bean ở bên trong context, nên không nên cho bên không tin cậy sửa template. Khi dùng reactive engine để render trang lớn hoặc model có publisher, còn phải cân nhắc buffering, streaming và event-loop blocking riêng; việc HTML SSR không tự miễn các quy tắc reactive.

## 10. Chẩn đoán khi tìm sai giao diện

Một trình tự kiểm tra hiệu quả:

1. **URL khớp controller chưa?** Dò `@GetMapping`, method HTTP, context path, `@Controller` có được component scan không. Route 404 xảy ra **trước** bước resolve view.
2. **Return value là view name hay body?** Kiểm tra `@Controller` versus `@RestController` và `@ResponseBody` trên method; `String` có semantics khác.
3. **Logical view name chính xác là gì?** Log/breakpoint ở controller: `"pages/welcome"` khác `"/pages/welcome"` và khác `"pages/welcome.html"` tùy resolver.
4. **Template file thật nằm đâu?** Với Thymeleaf mặc định: `src/main/resources/templates/pages/welcome.html`. Kiểm tra chữ hoa/chữ thường, suffix, encoding, file đã đóng gói vào JAR chưa.
5. **Starter nào có trên classpath?** Có `spring-boot-starter-thymeleaf` hoặc một engine phù hợp chưa? Có nhầm MVC/WebFlux starter hoặc thêm nhiều engine không?
6. **Resolver nào có trước?** Kiểm tra danh sách `ViewResolver` bean, `getOrder()`, view-name pattern và việc resolver trả `null` hay một View. Đặc biệt chú ý `InternalResourceViewResolver`.
7. **Có content negotiation?** Nếu response thay đổi theo `Accept`, quan sát `ContentNegotiatingViewResolver` và Content-Type của candidate View; đừng giả định order đơn giản.
8. **Có lỗi ở bước render không?** HTML template parse error, expression `th:text`, missing model attribute, layout/fragment lỗi hoặc file không tồn tại có thể ném exception **sau khi route đã khớp**.
9. **Có cache đang giữ template cũ?** Kiểm tra `spring.thymeleaf.cache`, template cache của engine, cơ chế reload và môi trường dev/prod.
10. **HTTP status nào được gửi?** Dùng `curl -i` để phân biệt 3xx redirect, 200 HTML, 404 route, 406 content negotiation, 500 render failure; không đoán từ browser chỉ thấy trang trắng.

Bảng triệu chứng thường gặp:

| Triệu chứng | Khả năng cao | Hướng xử lý |
| --- | --- | --- |
| Trình duyệt hiển thị nguyên `pages/welcome` | Controller là `@RestController` hoặc có `@ResponseBody` | Chuyển route HTML sang `@Controller`, trả logical name |
| `GET /pages/welcome` trả 404 | Không có mapping đúng URL hoặc controller không được scan | Kiểm tra `HandlerMapping` và cấu trúc package |
| Controller đã chạy nhưng báo không resolve/render được template | Thiếu template, sai prefix/suffix hoặc engine dependency | Kiểm tra view name, resource path, classpath, stack trace |
| Dùng hai template engines mà view bị render sai | Resolver nhận pattern chồng nhau; order không rõ | Tách view-name patterns và quy định ưu tiên |
| JSP resolver “ăn” hết view names | `InternalResourceViewResolver` được đặt trước resolver khác | Đặt cuối chain hoặc bỏ nếu không dùng JSP |
| Thymeleaf template sửa nhưng trang không đổi | Cache hoặc artifact đang chạy chứa bản cũ | Tắt cache dev, kiểm tra deploy/restart/build |
| `redirect:` trả nội dung lạ | Có `@ResponseBody` hoặc URL redirect sai | Kiểm tra controller return semantics, Location |
| Client `Accept: application/json` không nhận JSON | Route chỉ có HTML view, content negotiation hoặc `produces` không khớp | Tách API JSON hoặc cấu hình representations rõ ràng |
| Template hiển thị literal `${name}` | Thymeleaf engine không chạy hoặc file tĩnh không xử lý expressions | Truy cập route controller để render, kiểm tra `th:text` |
| JSP chạy ở WAR nhưng không ở executable JAR | Giới hạn của JSP/Servlet packaging | Dùng WAR được hỗ trợ hoặc chuyển template engine |

### Gợi ý quan sát resolver đang hoạt động

Có thể bật logging ở môi trường phát triển:

~~~properties
logging.level.org.springframework.web.servlet=DEBUG
logging.level.org.springframework.web.servlet.view=TRACE
logging.level.org.thymeleaf=DEBUG
~~~

Mức log và tên logger có thể thay đổi giữa các phiên bản; không dựa vào một câu log duy nhất làm kiểm thử. Có thể đăng ký một diagnostic runner **chỉ khi cần** để in danh sách bean ViewResolver và order từ `ApplicationContext`, hoặc đặt breakpoint trong resolver tùy chỉnh và `ThymeleafViewResolver`. Không bật TRACE của toàn bộ web stack trên production khi có nhiều request và thông tin nhạy cảm.

Nếu có `spring-boot-starter-actuator`, endpoint về beans/conditions có thể giúp giải thích auto-configuration, nhưng cần exposure và phân quyền phù hợp. Condition report giải thích vì sao bean được cấu hình; request test mới xác minh view nào render thật.

## 11. Bài tập ngắn với đáp án

**Tình huống 1.** Ứng dụng khai báo resolver A order=5 và resolver B order=10. Cả hai đều nhận `"home"` và trả View. Resolver nào ưu tiên trong chuỗi thông thường?

**Đáp án:** A có order nhỏ hơn, nên ưu tiên. Nhưng nếu có `ContentNegotiatingViewResolver` ở cấp trên, phải kiểm tra cách nó thu thập candidate và chọn theo media type; không tự khẳng định luôn A chỉ bằng một cặp order.

**Tình huống 2.** Resolver A trả `null` khi nhận `"reports/monthly"`. Điều đó có nghĩa HTTP 404 ngay không?

**Đáp án:** Không. MVC có thể hỏi resolver tiếp theo; chỉ khi cả pipeline không tạo được kết quả hợp lệ mới có lỗi cuối cùng. HTTP status phụ thuộc route và error handling.

**Tình huống 3.** Tại sao không nên đặt `InternalResourceViewResolver` order=0 trước Thymeleaf?

**Đáp án:** Nó có thể tạo JSP/internal View mà chưa xác minh file đích tồn tại, từ đó chiếm tên view và ngăn fallback sang Thymeleaf. Đặt resolver JSP ở cuối nếu còn dùng.

**Tình huống 4.** `@RestController` trả `"pages/welcome"` nhưng browser chỉ thấy chữ ấy. Cần sửa gì?

**Đáp án:** Dùng `@Controller` (không `@ResponseBody`) cho route trang HTML và đảm bảo Thymeleaf template phù hợp. REST controller ghi String vào HTTP body.

**Tình huống 5.** Cần đổi folder templates từ `templates/` sang `views/`. Chỉ chỉnh `spring.mvc.view.prefix` có đủ không?

**Đáp án:** Không khi dùng Thymeleaf. Đặt `spring.thymeleaf.prefix=classpath:/views/` và đặt file tương ứng, vì thuộc tính `spring.mvc.view.*` nhắm đến internal resource/JSP view.

**Tình huống 6.** Dùng `return "redirect:/pages/welcome"`; Spring tìm `redirect:/pages/welcome.html` trong templates?

**Đáp án:** Không. `redirect:` là view name đặc biệt để trả redirect HTTP. Browser có thể gửi một request mới tới đường dẫn được chuyển đến.

**Tình huống 7.** Một resolver trả View đúng nhưng template lỗi do expression. Framework có nhất thiết thử resolver kế tiếp không?

**Đáp án:** Không. Lỗi trong giai đoạn render thường là exception của View/engine đã chọn, khác với `resolveViewName` trả null. Điều tra lỗi parse/render của template và model.

**Tình huống 8.** `spring.thymeleaf.template-resolver-order` có phải thứ tự của Spring MVC `ViewResolver` không?

**Đáp án:** Không. Thuộc tính này sắp xếp resolver template bên trong Thymeleaf; Spring MVC ViewResolver là tầng khác.

## 12. Tổng hợp quy tắc cần nhớ

1. **Route mapping trước, view resolving sau:** `HandlerMapping` chọn controller; `ViewResolver` chọn View theo logical name.
2. **Số `order` thấp → ưu tiên cao:** nếu resolver trả `null`, framework có thể chuyển tiếp.
3. **Resolver “nhận bừa” có thể chặn fallback:** đặc biệt với `InternalResourceViewResolver`/JSP; đặt cuối.
4. **ContentNegotiatingViewResolver là trường hợp tổng hợp:** nó có thể hỏi nhiều resolvers và chọn candidate theo `Accept`; không rút toàn bộ hành vi về quy tắc “first non-null” một cách máy móc.
5. **ViewResolver khác TemplateResolver:** Spring MVC chọn View; Thymeleaf tiếp tục tìm/xử lý template.
6. **`@Controller` trả view name; `@RestController` trả body:** phân biệt để không bị literal string.
7. **Một project chỉ dùng Thymeleaf thường không cần custom resolver:** default Boot + đúng template path là đủ.
8. **Khi nhiều công nghệ view, đặt tên rõ và có thứ tự:** tránh prefix/suffix và pattern chồng nhau; quan sát runtime thực tế.
9. **Redirect/forward không phải template file:** cả hai là hướng điều khiển response, có semantics HTTP khác nhau.
10. **Đừng mở template hoặc view name động cho nguồn không tin cậy:** chỉ expose những view/redirect target mà ứng dụng cho phép.

## Tài liệu chính thức

- [Spring Framework — MVC View Resolution, ViewResolver chaining, redirect và forward](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html)
- [Spring Framework — MVC View Resolvers configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/view-resolvers.html)
- [Spring Framework — MVC Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html)
- [Spring Framework — @ResponseBody và @RestController](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Boot — Web MVC and Template Engines](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot — Application properties, spring.thymeleaf.*](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot — Build Systems and Starter names](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Framework — WebFlux View Resolution and View Technologies](https://docs.spring.io/spring-framework/reference/web/webflux-view.html)
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)

**Kết luận thực hành:** Hãy xác định controller có trả **logical view name** thật không; sau đó xem danh sách resolver theo order, quy tắc trả `null`, content negotiation và tài nguyên template. Chỉ khi biết từng tầng này, bạn mới giải thích chính xác vì sao một URL đi đến HTML dự kiến, bị resolver khác nhận, hoặc lỗi ở giai đoạn render.
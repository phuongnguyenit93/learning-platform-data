# Phân biệt template engine với tài nguyên HTML tĩnh

## 1. Mục tiêu học tập và tình huống

Một ứng dụng Spring Boot có thể trả về hai trang đều kết thúc bằng `.html` nhưng cách tạo ra chúng rất khác nhau:

- **HTML tĩnh (static HTML):** file HTML đã có sẵn trên classpath. Server tìm file rồi trả nội dung cho client, thông thường không thay thế biến theo từng request.
- **HTML được render bằng template engine:** file HTML là **mẫu** (template). Controller chuẩn bị dữ liệu, engine kết hợp mẫu và dữ liệu để tạo HTML phản hồi tại thời điểm xử lý request.

Trong module **Spring Boot – web-runtime**, mục tiêu là nhận biết **ai tạo response HTML**, **dữ liệu đến từ đâu**, **URL do ai quyết định**, và **khi nào cần chọn từng cách**. Bài này tập trung vào Spring MVC + Thymeleaf, đồng thời giải thích các nguyên tắc áp dụng cho FreeMarker/Mustache và các công nghệ template khác.

Sau bài học, bạn có thể:

1. Phân biệt một file trong `src/main/resources/static` với file trong `src/main/resources/templates` và hiểu vì sao đường dẫn URL của chúng khác nhau.
2. Mô tả luồng xử lý từ HTTP request đến `ResourceHttpRequestHandler` hoặc từ `@Controller` đến `ViewResolver`/Thymeleaf.
3. Dùng `Model`, `@GetMapping`, `th:text`, `th:each`, `th:if` và `th:href` để trả HTML theo dữ liệu server.
4. Phân biệt `@Controller` trả view name với `@RestController`/`@ResponseBody` trả dữ liệu response body.
5. Chạy ví dụ Java 17+, kiểm chứng sự khác nhau bằng `curl`, trình duyệt và nội dung response.
6. Tránh lỗi 404, lộ template, nhầm cú pháp, cache sai và các vấn đề an toàn khi hiển thị dữ liệu người dùng.

## 2. Định nghĩa: static HTML khác template HTML ở đâu?

**Tài nguyên HTML tĩnh:** trình duyệt nhận nội dung HTML đã được lưu thành file, ví dụ `static/about.html`. Server có thể thêm HTTP header, cache, compression hoặc kiểm tra quyền, nhưng **không chạy các biểu thức Thymeleaf trong file này** theo cơ chế static resource mặc định.

**Template engine:** phần mềm nhận template cùng các giá trị đầu vào (ví dụ `name = "Lan"`), rồi xuất HTML cuối cùng. Trong Spring Boot, Thymeleaf thường được gọi từ quy trình trả view của Spring MVC. Template engine có thể thực hiện thay thế văn bản, điều kiện, lặp danh sách, dùng fragment/layout và tạo URL theo context path. Các tính năng này **chỉ thực sự hoạt động khi template được đưa qua engine**.

Một trang HTML có giao diện nhìn hoàn toàn giống nhau ở browser vẫn có thể thuộc hai cơ chế khác nhau. Hãy xác định cơ chế bằng luồng request và mã tạo response, không chỉ nhìn phần mở rộng `.html`.

| Tiêu chí | HTML tĩnh | HTML qua template engine |
| --- | --- | --- |
| Nguồn mặc định trong Spring Boot MVC | `classpath:/static/`, `/public/`, `/resources/`, `/META-INF/resources/` | `classpath:/templates/` với template engine tương ứng |
| Thành phần tạo body | Static resource handler đọc file | Controller chọn view; view resolver + engine render |
| Giá trị theo từng request | Không tự thay thế server-side; có thể dùng JS ở browser | Có thể đưa dữ liệu `Model` vào HTML trước khi gửi |
| URL | Thường là đường dẫn tương đối của file dưới static root | URL do `@RequestMapping`/route quyết định, view name trỏ đến template |
| Cú pháp Thymeleaf `th:*` | Giữ nguyên như nội dung file, không được Spring xử lý | Được Thymeleaf xử lý nếu đúng template/context |
| Phụ thuộc template engine | Không cần | Cần starter/dependency và cấu hình engine |
| Phù hợp | Landing page, trang trợ giúp, HTML ít thay đổi | Trang cá nhân, danh sách theo DB, kết quả theo quyền/ngôn ngữ |
| Cache | Thường dễ cache rộng nếu nội dung chung | Cần phân biệt cache template và cache HTML cá nhân hóa |
| JavaScript | Có thể có | Cũng có thể có |
| Định dạng phản hồi | Thường `text/html` cho `.html` | Thường `text/html` cho view HTML |

**Không nhầm “static HTML” với “ứng dụng không có dữ liệu động”.** File HTML tĩnh vẫn có thể dùng JavaScript gọi API rồi cập nhật DOM. Khi đó phần HTML khởi đầu được phục vụ tĩnh, còn nội dung động được tạo trên **client**, không phải do template engine server render.

Ngược lại, template có thể xuất HTML không chứa dữ liệu thay đổi; điều này **không biến nó thành tài nguyên tĩnh** trong luồng Spring MVC.

## 3. Thư mục nào, đường dẫn nào và URL nào?

Với Spring Boot MVC mặc định:

~~~text
src/main/resources/
├── static/
│   ├── index.html
│   ├── about.html
│   └── css/site.css
├── public/
│   └── help.html
├── resources/
│   └── docs/readme.html
├── META-INF/resources/
│   └── pages/faq.html
└── templates/
    ├── greeting.html
    └── account/profile.html
~~~

### 3.1. Tài nguyên tĩnh

Các file dưới bốn static locations được resource handler phục vụ, thường theo mapping `/**`:

| Đường dẫn trong project | URL mặc định |
| --- | --- |
| `src/main/resources/static/index.html` | `GET /index.html`; có thể là welcome page của `GET /` |
| `src/main/resources/static/about.html` | `GET /about.html` |
| `src/main/resources/public/help.html` | `GET /help.html` |
| `src/main/resources/resources/docs/readme.html` | `GET /docs/readme.html` |
| `src/main/resources/META-INF/resources/pages/faq.html` | `GET /pages/faq.html` |

Các segment `static`, `public`, `resources` và `META-INF/resources` **không tự trở thành prefix URL**. Đối với `src/main/resources/static/about.html`, URL mặc định là `/about.html`, không phải `/static/about.html`.

### 3.2. Template

Thymeleaf mặc định tìm template tại `classpath:/templates/` và dùng suffix `.html`. Nhưng file `templates/greeting.html` **không tự có URL `/templates/greeting.html`**.

Một controller có thể khai báo:

~~~java
@GetMapping("/hello")
public String hello(Model model) {
    model.addAttribute("name", "Lan");
    return "greeting";
}
~~~

Trong một lớp `@Controller`, `return "greeting"` là **tên logic của view**. Thymeleaf tìm `classpath:/templates/greeting.html`, render và trả kết quả cho URL **`GET /hello`**. Nếu template ở `templates/account/profile.html`, tên view thường là `"account/profile"`; URL vẫn do controller quyết định và có thể không giống đường dẫn tệp.

**Lưu ý tên view:** trả `"greeting"` thường đúng với default Thymeleaf suffix `.html`. Đừng mặc định `return "greeting.html"` là cách tương đương; khi resolver ghép suffix, cấu hình có thể xử lý không như mong muốn. Dùng view name logic theo quy ước và kiểm tra cấu hình thực tế.

## 4. Hai đường đi trong Spring MVC

### 4.1. Request HTML tĩnh

~~~text
Browser -> GET /about.html
              |
              v
     DispatcherServlet / HandlerMapping
              |
              v
  ResourceHttpRequestHandler (fallback static)
              |
              v
   classpath:/static/about.html
              |
              v
   Trả nội dung file + HTTP headers
              |
              v
             Browser
~~~

Không cần `@Controller` cho từng static file. Với cấu hình mặc định, resource handler không chạy Thymeleaf để đổi `${name}` hoặc các thuộc tính `th:*`.

### 4.2. Request HTML render từ template

~~~text
Browser -> GET /hello?name=Lan
              |
              v
        DispatcherServlet
              |
              v
      @Controller / @GetMapping
              |
              v
    Model {name: "Lan", items: [...]}
              |
              v
   return "greeting" (view name)
              |
              v
    ViewResolver -> Thymeleaf
              |
              v
    templates/greeting.html + Model
              |
              v
    HTML được render -> HTTP response
              |
              v
             Browser
~~~

**Ranh giới cần nhớ:** controller thường **không trả toàn bộ HTML dưới dạng String** trong ví dụ này; nó trả *view name*. Thymeleaf mới là thành phần đọc file mẫu và tạo nội dung HTML.

Thời điểm file template được biên dịch/cache và cách thực thi phụ thuộc engine/cấu hình. Nhưng về mặt nghiệp vụ, mỗi request có thể sử dụng `Model` khác nhau và tạo ra response HTML khác nhau.

### 4.3. Khi có cùng URL

Controller mapping thường có ưu tiên cao hơn handler tài nguyên tĩnh fallback. Ví dụ, nếu có `@GetMapping("/about.html")` và file `static/about.html`, kết quả thực tế có thể đi qua controller thay vì file. Đừng dựa vào trùng đường dẫn để phân biệt hai cơ chế.

Với welcome page, Spring Boot trước hết tìm `index.html` trong static locations; nếu không tìm được thì xét template `index` khi engine phù hợp có mặt. Một route `/` khai báo rõ trong ứng dụng thường được ưu tiên trước cơ chế welcome fallback. Đây là lý do `static/index.html` và `templates/index.html` **không phải hai trang tự động hợp nhất**.

## 5. Ví dụ chạy được: một ứng dụng có cả static HTML và Thymeleaf

Tạo dự án Maven **Java 17+**, **Spring Boot 3.3.x**, có `spring-boot-starter-web` và `spring-boot-starter-thymeleaf`. Ví dụ dùng phiên bản `3.3.5` để có cấu hình Maven cụ thể, không cần database hay công cụ JavaScript build.

### 5.1. Cấu trúc tệp

~~~text
html-compare/
├── pom.xml
└── src/main/
    ├── java/com/example/htmlcompare/
    │   ├── HtmlCompareApplication.java
    │   ├── PageController.java
    │   └── ApiController.java
    └── resources/
        ├── application.properties
        ├── static/
        │   ├── index.html
        │   ├── hello-static.html
        │   └── css/site.css
        └── templates/
            └── greeting.html
~~~

### 5.2. Build và cấu hình

**Tệp `pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>html-compare</artifactId>
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

Dependency Web cung cấp Spring MVC và embedded Tomcat; dependency Thymeleaf cung cấp engine và phần auto-configuration của Spring Boot. Không cần `@EnableWebMvc` hay tự tạo `ViewResolver` cho ví dụ mặc định này.

**Tệp `src/main/resources/application.properties`**

~~~properties
server.port=8080
spring.thymeleaf.cache=false
~~~

`spring.thymeleaf.cache=false` dùng cho **học tập/phát triển** để dễ thấy sửa đổi template; không phải khuyến nghị production. Không bật/tắt cache template bằng property của static resources: đó là **hai cơ chế cache khác nhau**.

### 5.3. Java: khởi động và controller trả view

**Tệp `src/main/java/com/example/htmlcompare/HtmlCompareApplication.java`**

~~~java
package com.example.htmlcompare;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HtmlCompareApplication {
    public static void main(String[] args) {
        SpringApplication.run(HtmlCompareApplication.class, args);
    }
}
~~~

**Tệp `src/main/java/com/example/htmlcompare/PageController.java`**

~~~java
package com.example.htmlcompare;

import java.util.List;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class PageController {

    @GetMapping("/hello")
    public String hello(
            @RequestParam(name = "name", defaultValue = "bạn")
            String name,
            Model model) {
        model.addAttribute("name", name);
        model.addAttribute("items", List.of(
                "Spring MVC",
                "Thymeleaf",
                "HTML tĩnh"
        ));
        return "greeting";
    }
}
~~~

Điểm cần quan sát:

- `@Controller` cho phép phương thức trả về **view name**.
- `@GetMapping("/hello")` quyết định **URL**; không phải đường dẫn folder template.
- `@RequestParam` đọc query parameter; thiếu `name` thì dùng giá trị mặc định `"bạn"`.
- `Model` chứa dữ liệu của lần render này. `name` khác theo request, còn `items` trong bài lab là danh sách cố định.
- `return "greeting";` khiến Thymeleaf dùng file `templates/greeting.html` theo prefix/suffix mặc định.
- Không cần tạo instance Thymeleaf thủ công và không cần gọi `Files.readString` hay `getResourceAsStream` trong controller.

**Tệp `src/main/java/com/example/htmlcompare/ApiController.java`**

~~~java
package com.example.htmlcompare;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/hello")
    public Map<String, String> hello(
            @RequestParam(name = "name", defaultValue = "bạn")
            String name) {
        return Map.of("message", "Xin chào, " + name);
    }
}
~~~

Controller thứ hai minh họa một **nhánh khác**: `@RestController` ghi giá trị Java đã serialize vào HTTP response body (thông thường JSON với Jackson). `Map.of(...)` **không phải view name** và không gọi Thymeleaf. Điều này tránh nhầm giữa trả dữ liệu cho frontend và render HTML ở server.

### 5.4. Template Thymeleaf: HTML được render từ Model

**Tệp `src/main/resources/templates/greeting.html`**

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trang Thymeleaf</title>
  <link rel="stylesheet" th:href="@{/css/site.css}" href="/css/site.css">
</head>
<body>
  <h1>Xin chào, <span th:text="${name}">khách</span>!</h1>
  <p>Đây là HTML được render trên máy chủ bằng Thymeleaf.</p>
  <h2>Danh sách minh họa</h2>
  <ul>
    <li th:each="item : ${items}" th:text="${item}">Mục mẫu</li>
  </ul>
  <p th:if="${#lists.isEmpty(items)}">Chưa có mục nào.</p>
  <a th:href="@{/}">Về trang chủ</a>
</body>
</html>
~~~

Ý nghĩa:

- `th:text="${name}"` thay **nội dung** của `span` bằng giá trị `name` đã escape cho ngữ cảnh văn bản HTML.
- `th:each="item : ${items}"` nhân bản một `li` cho mỗi phần tử; `th:text="${item}"` hiện tên từng phần tử.
- `th:if="${#lists.isEmpty(items)}"` chỉ giữ đoạn HTML khi danh sách rỗng. Ở ví dụ, danh sách có ba mục nên đoạn “Chưa có mục nào” không xuất hiện trong response render.
- `th:href="@{/css/site.css}"` tạo link phù hợp với context path ứng dụng thay vì bắt buộc dùng đường dẫn root cứng trong môi trường có prefix.
- Nội dung fallback như `khách` hoặc `Mục mẫu` hữu ích khi mở template để thiết kế; khi Thymeleaf xử lý, chúng được thay thế tương ứng.

File này nằm trong `templates` nên không được phục vụ trực tiếp chỉ nhờ việc có tên `greeting.html`. Nếu truy cập `GET /templates/greeting.html` theo cấu hình mặc định, bạn không yêu cầu “render mẫu”, và thường nhận 404 vì đó không phải static resource URL hay route controller.

### 5.5. HTML tĩnh: server trả file như đã lưu

**Tệp `src/main/resources/static/index.html`**

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Static và Template</title>
  <link rel="stylesheet" href="/css/site.css">
</head>
<body>
  <h1>Trang chủ HTML tĩnh</h1>
  <p>Tệp này được phục vụ trực tiếp từ thư mục static.</p>
  <p><a href="/hello?name=Lan">Xem trang Thymeleaf với tên Lan</a></p>
  <p><a href="/hello-static.html?name=Lan">Xem HTML tĩnh với cùng tham số</a></p>
  <p><a href="/api/hello?name=Lan">Xem JSON từ RestController</a></p>
</body>
</html>
~~~

`static/index.html` có thể là welcome page cho `GET /` khi không có controller `/` hoặc cấu hình khác ưu tiên. Trong lab này, `GET /` dẫn tới trang tĩnh.

**Tệp `src/main/resources/static/hello-static.html`**

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>HTML tĩnh</title>
  <link rel="stylesheet" href="/css/site.css">
</head>
<body>
  <h1>Xin chào, <span th:text="${name}">khách</span>!</h1>
  <p>File này KHÔNG đi qua Thymeleaf.</p>
  <p>Thêm ?name=Lan vào URL không tự thay thế tên.</p>
  <a href="/">Về trang chủ</a>
</body>
</html>
~~~

Đoạn `th:text="${name}"` được cố tình đặt vào file **static** để chứng minh khác biệt: server trả nguyên thuộc tính `th:text` trong source HTML, trình duyệt thông thường không hiểu quy ước Thymeleaf và hiển thị nội dung fallback `khách`. Nếu thay URL thành `/hello-static.html?name=Mai`, **file HTML vẫn như cũ**; query string chỉ làm thay đổi dữ liệu nếu bạn tự viết logic server/client xử lý nó.

**Tệp `src/main/resources/static/css/site.css`**

~~~css
body {
  font-family: system-ui, sans-serif;
  max-width: 760px;
  margin: 2rem auto;
  line-height: 1.6;
}
h1 {
  color: #1d4ed8;
}
a {
  color: #0f766e;
}
~~~

Cùng một CSS tĩnh có thể được tham chiếu từ trang tĩnh bằng `href="/css/site.css"` và từ template bằng `th:href="@{/css/site.css}"`. **Template HTML không có nghĩa CSS/JS/image cũng phải là template.** Thông thường file asset vẫn phục vụ tĩnh để tận dụng cache.

## 6. Chạy và quan sát response thật

Tại thư mục dự án `html-compare`, sử dụng JDK 17+ và Maven, chạy:

~~~bash
mvn spring-boot:run
~~~

Sau khi thấy ứng dụng chạy ở port 8080, thử lần lượt:

~~~bash
curl -i http://localhost:8080/
curl -i "http://localhost:8080/hello?name=Lan"
curl -i "http://localhost:8080/hello?name=Mai"
curl -i "http://localhost:8080/hello-static.html?name=Lan"
curl -i "http://localhost:8080/api/hello?name=Lan"
curl -i http://localhost:8080/css/site.css
~~~

Các kết quả cần kiểm tra (không coi header/whitespace toàn bộ response là cố định):

| Request | Nguồn tạo body | Phần nội dung quan sát được |
| --- | --- | --- |
| `GET /` | `static/index.html` | `Trang chủ HTML tĩnh` |
| `GET /hello?name=Lan` | `PageController` + `greeting.html` | `Xin chào, Lan!`; có ba item |
| `GET /hello?name=Mai` | Cùng template, khác `Model` | `Xin chào, Mai!`; có ba item |
| `GET /hello-static.html?name=Lan` | File `static/hello-static.html` | `Xin chào, khách!`; không đổi theo `name` |
| `GET /api/hello?name=Lan` | `@RestController` + JSON converter | `{"message":"Xin chào, Lan"}` |
| `GET /css/site.css` | Static CSS file | Nội dung CSS; không qua view resolver |

Với `GET /hello?name=Lan`, response HTML có một đoạn tương đương:

~~~html
<h1>Xin chào, <span>Lan</span>!</h1>
~~~

Với `GET /hello-static.html?name=Lan`, trong **body HTTP** vẫn có dòng nguồn:

~~~html
<h1>Xin chào, <span th:text="${name}">khách</span>!</h1>
~~~

Đây là bằng chứng có thể quan sát được qua `curl`: template được xử lý; static HTML được trả như file. HTML engine có thể chuẩn hóa markup/whitespace khác nhau tùy cấu hình; cần kiểm tra **ý nghĩa và phần tử chính** thay vì so khớp từng byte của toàn bộ trang.

Đối với JSON, thứ tự thuộc tính JSON trong ví dụ một thuộc tính không gây vấn đề; còn các response thực tế có thể thêm header khác. Nếu dùng Windows PowerShell và gặp alias `curl`, có thể chạy `curl.exe -i ...`.

### 6.1. Thử name chứa thẻ HTML: khác biệt về escape

Chạy:

~~~bash
curl -i --get --data-urlencode "name=<script>alert(1)</script>" http://localhost:8080/hello
~~~

`th:text` sẽ escape ký tự HTML đặc biệt trong ngữ cảnh văn bản, nên phần hiển thị tương đương:

~~~html
<span>&lt;script&gt;alert(1)&lt;/script&gt;</span>
~~~

Trình duyệt sẽ hiển thị chuỗi ký tự `<script>alert(1)</script>` như văn bản, thay vì biến nó thành một phần tử `script` được thực thi. Đây là khác biệt quan trọng giữa **text output đã escape** và **raw HTML được chèn có chủ ý**.

Không đổi bừa `th:text` thành `th:utext` chỉ vì muốn giữ định dạng: `th:utext` xuất dữ liệu **không escape HTML**, có thể dẫn đến XSS nếu đầu vào không tin cậy. Escaping cần đúng ngữ cảnh; giá trị dùng trong JavaScript, CSS, URL hay thuộc tính có quy tắc riêng. Không coi mọi interpolation đều an toàn trong mọi vị trí.

### 6.2. Đóng gói JAR và kiểm tra classpath

Dừng ứng dụng rồi chạy:

~~~bash
mvn clean package
jar tf target/html-compare-0.0.1-SNAPSHOT.jar
java -jar target/html-compare-0.0.1-SNAPSHOT.jar
~~~

Trong danh sách từ `jar tf`, tìm những entry:

~~~text
BOOT-INF/classes/static/index.html
BOOT-INF/classes/static/hello-static.html
BOOT-INF/classes/static/css/site.css
BOOT-INF/classes/templates/greeting.html
~~~

Các dòng trên là **đường dẫn cần tìm trong JAR**, không phải toàn bộ output. Lớp Java đã biên dịch cũng có trong JAR. Sau khi chạy JAR, kiểm tra lại các URL giống khi chạy Maven. Nếu template thiếu khỏi artifact, endpoint `/hello` có thể lỗi xử lý view dù class Java đã được đóng gói thành công.

## 7. Các annotation dễ gây nhầm lẫn

### 7.1. @Controller và @RestController

Hai đoạn minh họa sau dùng đúng kiểu xử lý mà annotation quy định:

~~~java
@Controller
class HtmlPageController {
    @GetMapping("/page")
    String page() {
        return "greeting";
    }
}
~~~

Đây là **đoạn rút gọn** minh họa: có thể dùng trong ứng dụng đã có file `templates/greeting.html` và Thymeleaf, nhưng phải đặt class/annotation/import đúng package trước khi chạy. Giá trị `"greeting"` là **view name**.

~~~java
@RestController
class TextController {
    @GetMapping("/text")
    String text() {
        return "greeting";
    }
}
~~~

Đây cũng là **đoạn rút gọn**: response body là chuỗi `greeting`, thường có content type dạng text, **không phải nội dung template**. `@RestController` về bản chất kết hợp `@Controller` và cơ chế `@ResponseBody` cho phương thức trả dữ liệu.

Ngoài ra, trong một `@Controller`:

~~~java
@GetMapping("/plain")
@ResponseBody
public String plain() {
    return "<p>Đây là chuỗi response body</p>";
}
~~~

Giá trị trả về là body text/HTML theo converter và content type cấu hình, không phải tên template. Muốn tự trả HTML qua body, phải tự xử lý encoding/content type/escape, nhưng với trang nhiều dữ liệu động, cơ chế view/template thường rõ ràng hơn.

### 7.2. Model là dữ liệu cho view, không phải database

`Model` chứa các attribute được đưa vào lần render request. Nó **không phải** nơi lưu bền dữ liệu, không phải JDBC connection và không tự bảo đảm thông tin tồn tại ở request tiếp theo. Mỗi request nhận dữ liệu model tương ứng với code/luồng xử lý của mình.

Ví dụ một controller đọc dữ liệu từ service rồi thêm vào model:

~~~java
@GetMapping("/products")
public String products(Model model) {
    model.addAttribute("products", productService.findVisibleProducts());
    return "products";
}
~~~

Đây là **mã minh họa không độc lập** vì `productService` và template `products.html` chưa được định nghĩa. Điều cần học là **controller/service lấy dữ liệu -> Model -> engine render**; cách truy xuất DB là chủ đề khác.

### 7.3. View name khác redirect và static path

`return "greeting"` yêu cầu render view Thymeleaf; `return "redirect:/hello?name=Lan"` yêu cầu HTTP redirect đến URL khác; `return "forward:/..."` yêu cầu forward trong server theo cơ chế view của Spring. Các prefix này là cú pháp đặc biệt của Spring MVC, khác với việc ghi thẳng HTML vào response.

Nếu mục tiêu là dẫn người dùng từ controller đến file `static/about.html`, dùng redirect đúng URL, ví dụ `"redirect:/about.html"`. Không đặt chuỗi `"static/about.html"` vào `return` rồi mặc định nó sẽ được phục vụ như static resource; Thymeleaf có thể cố tìm template theo tên view đó.

## 8. Dữ liệu động có nhất thiết phải dùng template engine?

**Không.** Có ít nhất ba mô hình thường gặp:

| Mô hình | HTML khởi đầu được tạo ở đâu? | Dữ liệu mới xuất hiện ở đâu? | Ví dụ |
| --- | --- | --- | --- |
| Static HTML thuần | File có sẵn | Không có hoặc chỉ nội dung đã hardcode | Trang giới thiệu cố định |
| Static HTML + JavaScript gọi API | File có sẵn | Browser gọi JSON API rồi cập nhật DOM | Dashboard web đơn giản |
| Server-side rendering với template engine | Server kết hợp template + model | Tại server trước khi gửi HTML; client có thể cập nhật tiếp | Trang hồ sơ hoặc danh sách theo người dùng |

Đoạn JavaScript sau là **minh họa phía trình duyệt**, không phải một phần bắt buộc của project mục 5:

~~~html
<p id="message">Đang tải...</p>
<script>
  fetch("/api/hello?name=Lan")
    .then(response => {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(data => {
      document.getElementById("message").textContent = data.message;
    })
    .catch(() => {
      document.getElementById("message").textContent = "Không tải được dữ liệu";
    });
</script>
~~~

HTML có thể được phục vụ từ `static/` mà vẫn hiển thị lời chào động nhờ JS. Lúc này server trả HTML tĩnh và JSON từ `@RestController`; browser kết hợp chúng. Còn Thymeleaf trả HTML đã chứa `Lan` ngay khi response đến, dù trình duyệt chưa chạy JavaScript.

Các framework như React/Vue/Angular, static site generators và cơ chế prerender/hydration có mô hình triển khai riêng; không được đánh đồng tất cả với Thymeleaf chỉ vì cùng xuất ra HTML.

## 9. Khi nào chọn template engine, khi nào dùng HTML tĩnh?

**Ưu tiên HTML tĩnh** khi nội dung ít thay đổi theo người dùng, không cần dữ liệu server lúc render, có thể đóng gói/cache/CDN tốt, chẳng hạn hướng dẫn sử dụng, trang giới thiệu, health page tĩnh (nếu phù hợp). Một dự án SPA cũng thường cần server phục vụ file HTML/JS/CSS đã build tĩnh.

**Ưu tiên template engine** khi server đã có dữ liệu cần hiển thị theo request, cần layout/header/footer tái sử dụng, xử lý danh sách/điều kiện hoặc muốn trả trang có nội dung ngay từ response HTTP, chẳng hạn chi tiết sản phẩm, biên nhận, trang form và thông báo validation.

**Có thể kết hợp:** Thymeleaf render trang, còn CSS, JS, ảnh và font nằm trong `static/`. Đây là mẫu phổ biến: template sinh cấu trúc/nội dung theo dữ liệu; static handler phục vụ asset chung.

| Câu hỏi thực tế | Hướng chọn |
| --- | --- |
| “Nội dung có thay đổi theo user, quyền hay request không?” | Nếu có và cần có ngay trong HTML response, cân nhắc template |
| “Chỉ có một landing page/các file asset?” | Tĩnh thường đơn giản |
| “Frontend gọi REST API để cập nhật dữ liệu?” | HTML tĩnh hoặc SPA đều có thể phù hợp |
| “Cần form validation và render lỗi từ server?” | Template engine thuận tiện |
| “Cần CDN cache file CSS/JS nhiều giờ?” | Asset tĩnh có version/hash |
| “Muốn cùng header/footer giữa nhiều trang server-rendered?” | Template fragments/layout hỗ trợ tốt |
| “Muốn ít logic frontend JavaScript nhất có thể?” | Template server-side thường phù hợp |
| “Ứng dụng phải phản hồi JSON cho mobile/client khác?” | API controller trả JSON; template HTML là một kênh giao diện khác |

Đừng chọn chỉ vì “tĩnh chắc chắn nhanh hơn”. Độ trễ còn do database, cache, reverse proxy, kích thước HTML, network, số lần render, gzip/Brotli và mô hình triển khai. Static thường dễ cache vì nội dung không phụ thuộc request, nhưng SSR có thể được cache an toàn theo ngữ cảnh nếu thiết kế đúng.

## 10. Cấu hình và vấn đề cache

### 10.1. Thymeleaf template resolver

Spring Boot với starter Thymeleaf thường tự cấu hình các property:

~~~properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.cache=true
~~~

Đây là ví dụ về **giá trị mặc định thông dụng** cho ứng dụng Thymeleaf. Bạn không cần ghi các dòng này khi dùng cấu hình mặc định. `spring.thymeleaf.cache=true` giúp tái sử dụng thông tin template đã phân giải/biên dịch ở production; nó **không đồng nghĩa** với việc cache HTML cá nhân hóa của mọi request.

Trong lúc học, dùng `spring.thymeleaf.cache=false` để engine có thể kiểm tra thay đổi template dễ hơn. Khi chạy từ executable JAR, việc sửa file source trên máy thường vẫn cần build/đóng gói lại nếu thay đổi đó không nằm trong artifact; tắt template cache **không tự cập nhật byte trong JAR đã chạy**.

### 10.2. Static resources

Spring Boot MVC phục vụ static resources thông qua `ResourceHttpRequestHandler` từ các vị trí mặc định. Một số property quan trọng:

~~~properties
# Ví dụ, đổi URL tĩnh thành /assets/**
spring.mvc.static-path-pattern=/assets/**

# Ví dụ, thay danh sách nơi tìm tài nguyên tĩnh:
spring.web.resources.static-locations=classpath:/static/
~~~

Hai thuộc tính này ảnh hưởng **static handler**, không phải Thymeleaf template resolver:

- `spring.mvc.static-path-pattern` đổi mẫu URL. Nếu dùng `/assets/**`, file `static/css/site.css` sẽ được tìm ở URL `/assets/css/site.css`.
- `spring.web.resources.static-locations` **thay danh sách nguồn tĩnh mặc định**. Nếu đặt chỉ `classpath:/static/`, bạn không nên mặc định rằng các nguồn `public`, `resources`, `META-INF/resources` vẫn được liệt kê như trước.
- Không dùng `spring.web.resources.static-locations=classpath:/templates/` để “bật template”: như vậy có thể khiến template source bị phục vụ như file tĩnh thay vì đi qua engine, với hậu quả bảo mật và chức năng.
- Cấu hình static URL prefix không tự đổi URL của `@GetMapping("/hello")` hay prefix của Thymeleaf.

Nếu đồng thời có `spring.mvc.static-path-pattern=/assets/**` và template chứa `th:href="@{/css/site.css}"`, bạn phải cập nhật URL logic cho asset; chẳng hạn dùng `@{/assets/css/site.css}` nếu không có pipeline sinh resource URL phù hợp.

### 10.3. HTML có cache HTTP khác với template cache

- **Template cache:** cache nội bộ của Thymeleaf về template đã parse/resolve, giúp giảm công việc xử lý template.
- **HTTP cache:** browser/CDN/proxy giữ response theo URL, headers và chính sách. Với HTML theo người dùng, cần rất thận trọng với `Cache-Control` và các biến thể response để tránh lộ dữ liệu.
- **Static asset cache:** CSS/JS/ảnh thường có thể cache lâu với tên chứa hash/version; có thể dùng resource chain/versioning của Spring MVC để quản lý URL.

Một trang Thymeleaf có thể được render mới ở mỗi request **dù template cache đang bật**. Một file tĩnh có thể bị browser cache và không gửi request mới. Đây là hai lớp cache độc lập.

## 11. Bảo mật và những lỗi thường gặp

### 11.1. Escape dữ liệu khi render

`th:text` escape HTML trong ngữ cảnh văn bản nên phù hợp khi hiển thị tên, bình luận, giá trị chưa tin cậy. `th:utext` xuất raw HTML và chỉ nên dùng khi nội dung thực sự đáng tin hoặc đã được xử lý an toàn cho mục tiêu hiển thị. Với JavaScript inline, URL, CSS và các event handler, phải dùng cơ chế escape/phát sinh URL phù hợp ngữ cảnh và kiểm soát đầu vào.

Chỉ vì HTML được render server-side không có nghĩa ứng dụng tự an toàn trước XSS, injection, CSRF hoặc lộ dữ liệu. Phân quyền vẫn thực thi ở controller/service và filter chain; **không** đưa thông tin riêng tư vào static directory. Khi cần bảo vệ một template view, cấu hình bảo mật cho URL và dữ liệu phù hợp.

### 11.2. Bảng chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Truy cập `/hello` nhận 404 | Thiếu controller mapping hoặc gọi sai path/context path | Xem `@GetMapping` và startup logs |
| `GET /hello` nhận 500 với lỗi không tìm được template | Thiếu `templates/greeting.html`, view name sai hoặc thiếu engine | Kiểm tra path, starter Thymeleaf, prefix/suffix và JAR |
| `GET /templates/greeting.html` nhận 404 | `templates` không phải static root mặc định | Gọi URL controller `/hello` |
| Dùng `@RestController` và return `"greeting"`, browser thấy chữ “greeting” | Return bị ghi như response body | Dùng `@Controller` khi muốn resolver xử lý view name |
| Đặt `greeting.html` trong `static` mà `th:text` không đổi | Static handler không chạy Thymeleaf | Chuyển file vào `templates` và render qua controller |
| `Model` có dữ liệu nhưng HTML không thay đổi | Sai tên key, sai biểu thức, không render đúng template | Đối chiếu `addAttribute` và `${...}` |
| Sửa template mà vẫn thấy trang cũ | Template cache, browser/proxy cache hoặc JAR cũ | Kiểm tra config dev, headers và artifact đã deploy |
| Trang render được nhưng CSS bị 404 | Static path sai, context path sai, thiếu tệp trong JAR | Mở Network tab và kiểm tra URL asset |
| Lộ nội dung HTML cho người khác | Cache HTTP hoặc quyền truy cập không theo người dùng | Xem `Cache-Control`, xác thực, phân quyền, session |
| XSS sau khi chèn HTML động | Dùng raw HTML/`th:utext` hoặc context escape sai | Chuyển sang output escaped, xác thực dữ liệu |
| `/` không hiện trang như kỳ vọng | Có static `index.html`, template `index` và route `/` cạnh tranh | Kiểm tra thứ tự fallback và controller |
| Chạy local được, JAR production lỗi | Source file không được đóng gói/khác case | `jar tf` và kiểm tra đường dẫn thực |

### 11.3. Lưu ý về route và lỗi 404

Spring MVC phân biệt controller mapping và static resource handler. Nếu URL `/hello` không được khai báo và static handler `/**` nhận nó, phía server có thể ghi log lỗi “không tìm thấy static resource” thay vì “không tìm thấy controller”. Thông báo này **không có nghĩa `/hello` cần chuyển sang folder static**. Hãy kiểm tra route trước, sau đó mới kiểm tra static resources.

### 11.4. Lưu ý về chỉnh sửa khi ứng dụng đang chạy

Khi chạy bằng IDE/plugin dev, tài nguyên có thể được copy/hot reload tùy cấu hình. Khi chạy qua JAR, nội dung nằm trong artifact. Vì vậy:

- Sửa file `src/main/resources/templates/greeting.html` không đảm bảo JAR đã chạy thay đổi ngay.
- `spring.thymeleaf.cache=false` không lấy nội dung mới từ source nếu runtime vẫn dùng byte cũ trong JAR.
- Thêm cache headers cho CSS không làm Thymeleaf tự cache toàn bộ HTML của người dùng.

## 12. Bài tập áp dụng và tự kiểm tra

**Bài tập A – Dự đoán response.** Ứng dụng có `static/profile.html` chứa:

~~~html
<h1 th:text="${name}">Hồ sơ mẫu</h1>
~~~

Khi gọi `GET /profile.html?name=Lan`, server mặc định có thay chuỗi `${name}` thành `Lan` không? Nếu không, người dùng thường nhìn thấy nội dung nào?

**Bài tập B – Dự đoán URL.** Có file `templates/orders/list.html` và controller khai báo `@GetMapping("/orders")` trả `"orders/list"`. URL truy cập là `/orders` hay `/templates/orders/list.html`? Vì sao?

**Bài tập C – Controller annotation.** Tại sao `@RestController` trả String `"home"` không khiến Thymeleaf render `templates/home.html`?

**Bài tập D – Chọn kiến trúc.** Bạn cần trang hướng dẫn công khai chung cho mọi người và trang chi tiết đơn hàng theo người dùng đã đăng nhập. Nên cân nhắc đặt trang nào ở `static`, trang nào qua template? Cần thêm kiểm soát nào cho trang đơn hàng?

**Bài tập E – Tính an toàn.** Vì sao `th:text` an toàn hơn `th:utext` khi dữ liệu đến từ form người dùng? Có nên nối dữ liệu raw vào một `<script>` không?

**Bài tập F – Thực nghiệm.** Trong ứng dụng mục 5, thay `name=Lan` thành `name=Mai` trên URL `/hello` rồi so sánh với `/hello-static.html`. Đoạn nào của HTML thay đổi? Tại sao?

**Đáp án định hướng:**

1. Không. Static handler gửi file, trình duyệt thường hiển thị fallback `Hồ sơ mẫu`; thuộc tính Thymeleaf vẫn nằm trong source.
2. `/orders`, do controller định tuyến request; view name `orders/list` chỉ cho engine biết vị trí template tương ứng.
3. `@RestController` dùng semantics `@ResponseBody`, ghi String vào body thay vì resolve view.
4. Trang hướng dẫn chung có thể tĩnh; trang đơn hàng phù hợp với server render khi cần dữ liệu từ service. Phải xác thực, phân quyền từng đơn hàng và kiểm soát HTTP cache.
5. `th:text` escape HTML ở text context; `th:utext` có thể cho phép markup nguy hiểm. Với JS cần output encoding theo ngữ cảnh và tránh chèn raw untrusted data.
6. `/hello` thay tên đã render từ Model; `/hello-static.html` không tự diễn giải query param hoặc `th:text`.

## 13. Tóm lược kỹ thuật

- **HTML tĩnh** = file có sẵn, mặc định ở các static locations, thường được phục vụ bởi `ResourceHttpRequestHandler`; query parameter không tự làm nội dung file khác đi.
- **Template HTML** = file mẫu trong `templates`, được chọn qua view name của `@Controller` và render cùng `Model` bằng Thymeleaf/engine phù hợp.
- `@RestController` thường dùng để trả JSON hoặc dữ liệu trực tiếp, còn `@Controller` thường dùng để trả tên view HTML; có thể thay đổi bằng `@ResponseBody` hoặc cấu hình khác, nên luôn xét semantics thực tế của method.
- File `.html` không quyết định là static hay dynamic; **đường đi xử lý request** mới quyết định.
- Một ứng dụng thực tế thường kết hợp **template cho trang HTML theo dữ liệu** và **static assets cho CSS, JS, hình ảnh**.
- Khi debug, xem request URL, handler/controller, template path, HTTP response và file thực tế trong JAR. Khi bảo mật, kiểm soát cả escaping lẫn quyền truy cập và cache.

## 14. Tài liệu tham khảo

- Spring Boot 3.3 — Servlet Web Applications (Static Content, Welcome Page, Template Engines): https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Framework — Annotated Controllers, Return Values, Model và Views: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — Static Resources: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Thymeleaf 3.1 — Tutorial, `th:text`, `th:utext`, `th:each` và URL expressions: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html

# Biến đường dẫn, biểu thức chính quy và đường dẫn có ký tự đại diện trong Spring MVC

Spring MVC dùng các mẫu URI để quyết định controller method nào xử lý request. Một route có thể khớp URL cố định như `/products/search`, lấy định danh từ một segment như `/products/{id}`, ràng buộc segment bằng biểu thức chính quy như `/products/{id:[0-9]+}` hoặc nhận nhiều segment qua ký tự đại diện. Các cú pháp trông gần nhau nhưng khác về **độ rộng của đường dẫn được khớp**, **giá trị được capture**, **mức ưu tiên khi nhiều handler match** và **cách xử lý lỗi**.

Bài này áp dụng cho Spring MVC trên Servlet stack, tập trung vào Spring Framework 6.x và Spring Boot 3.x, dùng Java 17+. Mặc định Spring MVC 6 sử dụng `PathPatternParser` cùng các `PathPattern` đã parse. Với ứng dụng đời cũ sử dụng `AntPathMatcher` hoặc được cấu hình path matching khác, phải xác nhận lại hành vi trước khi sao chép pattern.

## 1. Mục tiêu và mô hình định tuyến

Sau bài này, bạn cần có thể:

- Giải thích `@PathVariable`, named path variable, regex constraint, `?`, `*`, `**` và `{*path}`.
- Phân biệt một path segment với nhiều segment và với query string.
- Dự đoán route cụ thể nào sẽ được chọn nếu cả literal, variable và wildcard cùng match.
- Phân biệt route không match (thường 404) với route match nhưng kiểu dữ liệu không convert được (thường 400).
- Viết và kiểm thử controller theo Spring Boot 3 với Java 17+.
- Nhận diện rủi ro ở trailing slash, URI encoding, file extension, reverse proxy và đường dẫn không đáng tin cậy.

Sơ đồ logic:

~~~text
GET /api/products/42?lang=vi
            |
            v
Servlet container → DispatcherServlet
                         |
                         v
              RequestMappingHandlerMapping
              match method GET + URL path
                         |
                         v
              "/api/products/{id:[0-9]+}"
                         |
                         v
             URI variable id = "42"
                         |
                         v
             Argument resolver:
             @PathVariable long id → 42L
                         |
                         v
                   Controller
                         |
                         v
                 HTTP response
~~~

Query `?lang=vi` có thể dùng qua `@RequestParam`, nhưng **không phải path segment** để regex của `{id}` kiểm tra. Ngoài path, `@RequestMapping` còn có điều kiện method, params, headers, consumes, produces; đúng đường dẫn vẫn chưa chắc đủ để gọi được controller.

## 2. Đường dẫn URL gồm những gì?

Xét URL:

~~~text
https://api.example.test/store/api/products/42?lang=vi#details
|______ scheme/host ____| |____ path ________| |query| fragment
~~~

Giả định web application có context path `/store` và `DispatcherServlet` map mặc định vào `/`. Controller khai báo `@RequestMapping("/api/products")` và `@GetMapping("/{id}")`. Spring MVC so khớp route `/api/products/42` trong phạm vi ứng dụng, không cần viết context path vào annotation.

Các path segment là những phần được tách bởi slash:

~~~text
/api/products/42
  |     |     |
 api products 42
~~~

Một path variable đơn `{id}` capture **một segment**, không tự nhận cả `42/reviews`. Query string `?lang=vi` được truyền ở phần khác; fragment `#details` do client quản lý và không được gửi trong HTTP request-target.

Phân biệt dấu hỏi:

- Trong **pattern** `/files/v?.txt`, ký hiệu `?` có nghĩa match đúng một ký tự trong segment.
- Trong **URL request** `/files/v1.txt?download=true`, dấu `?` mở đầu query string.

Một URI pattern thuộc Spring MVC khác với Servlet container URL mapping: pattern `/**` trong controller không đồng nghĩa pattern servlet `/*`. Container chọn web context và servlet trước, sau đó `RequestMappingHandlerMapping` của Spring mới chọn method.

## 3. Bảng cú pháp URI pattern trong PathPatternParser

| Pattern | Ý nghĩa | Ví dụ match | Ví dụ không match |
| --- | --- | --- | --- |
| `/products/list` | Route literal cố định | `/products/list` | `/products/1` |
| `/products/{id}` | Một segment, capture vào `id` | `/products/42` | `/products/42/reviews` |
| `/pages/t?st` | `?` khớp đúng một ký tự trong segment | `/pages/test`, `/pages/t3st` | `/pages/tst` |
| `/images/*.png` | `*` khớp 0 hoặc nhiều ký tự trong một segment | `/images/logo.png` | `/images/icons/logo.png` |
| `/teams/*/members` | Một segment dạng wildcard | `/teams/java/members` | `/teams/java/core/members` |
| `/assets/**` | 0 hoặc nhiều segment ở cuối route | `/assets`, `/assets/a/b` | `/other/a/b` |
| `/assets/{*path}` | Catch-all cuối route và capture phần path còn lại | `/assets/a/b.png` | `/other/a/b.png` |
| `/products/{id:[0-9]+}` | Một segment có một hay nhiều chữ số ASCII | `/products/42` | `/products/abc` |

Những quy tắc phải nhớ:

1. `?` và `*` **không vượt qua dấu slash**, chỉ kiểm soát ký tự trong một segment.
2. `{name}` capture một segment để truy cập bằng `@PathVariable`.
3. `**` match nhiều segment nhưng **không tạo named variable**.
4. `{*path}` cũng match nhiều segment ở cuối và **có tạo variable**.
5. Với `PathPatternParser`, `**` và `{*path}` chỉ hợp lệ ở **cuối pattern**; không đặt catch-all vào giữa route.

### 3.1. Ký hiệu ? trong pattern

Đoạn minh họa trong một controller:

~~~java
@GetMapping("/files/v?.txt")
public String oneLetterVersion() {
    return "one-char-version";
}
~~~

Kết quả:

~~~text
/files/v1.txt     MATCH
/files/vA.txt     MATCH
/files/v10.txt    KHÔNG MATCH
/files/v.txt      KHÔNG MATCH
~~~

Ở đây dấu `?` là một ký tự wildcard, không liên quan đến query. Nếu request có thêm `?download=true`, đường dẫn vẫn là `/files/v1.txt`.

### 3.2. Ký hiệu *: wildcard trong một segment

Pattern:

~~~java
@GetMapping("/images/*.png")
public String png() {
    return "single-level-png";
}
~~~

So khớp:

~~~text
/images/cat.png          MATCH
/images/logo-small.png   MATCH
/images/icons/cat.png    KHÔNG MATCH
~~~

Ở `/images/icons/cat.png`, có hai segment sau `/images`, nên một dấu `*` trong `*.png` không đủ. Nếu yêu cầu ứng dụng là quản lý file phân cấp, hãy dùng `{*path}` hoặc thiết kế URI có nhiều phần rõ nghĩa; đừng giả định `*` “bắt mọi thứ”.

### 3.3. Ký hiệu **: catch-all

Pattern `/resources/**` có thể match `/resources`, `/resources/logo.png` và `/resources/images/logo.png`.

Các pattern sau **không hợp lệ** khi dùng `PathPatternParser`:

~~~text
/resources/**/logo.png
/a/**/b
/a/{*rest}/meta
~~~

Điều kiện catch-all ở cuối giúp Spring so sánh độ cụ thể của các route ít mơ hồ hơn. Nếu cần endpoint `/reports/{year}/export`, nên mô tả số segment thực sự cần thay vì buộc `**` nằm ở giữa.

Một khác biệt khi nâng cấp: `AntPathMatcher` cũ cho phép một số pattern có `**` ở giữa, nhưng `PathPatternParser` không chấp nhận kiểu đó. Vì vậy cần kiểm tra những route trước đây dùng `/**/something`.

## 4. @PathVariable: trích dữ liệu từ URI template

Một controller có thể khai báo:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    public String byId(@PathVariable("id") long productId) {
        return "product-" + productId;
    }
}
~~~

Khi client gọi `GET /api/products/42`, Spring trích URI variable `id` có giá trị text `"42"`, chuyển sang Java `long` rồi gọi method. Với ví dụ trên, body response là:

~~~text
product-42
~~~

Đoạn code trên minh họa một controller cần được đặt trong ứng dụng Spring MVC đã cấu hình component scanning và dependencies. `@PathVariable("id")` nêu rõ tên variable. Nếu tên tham số Java cũng là `id`, có thể viết `@PathVariable long id` khi biên dịch với parameter name metadata phù hợp, chẳng hạn `-parameters`; nêu tên tường minh tránh phụ thuộc vào cấu hình compiler.

### 4.1. Nhiều path variables

~~~java
@GetMapping("/users/{userId}/orders/{orderId}")
public String order(
        @PathVariable("userId") long userId,
        @PathVariable("orderId") long orderId) {
    return userId + ":" + orderId;
}
~~~

Request:

~~~text
GET /users/7/orders/81
~~~

Kết quả:

~~~text
7:81
~~~

Hai biến `userId` và `orderId` lấy từ **hai segment khác nhau**. Nếu request thêm `/details` mà không có route hỗ trợ phần đó, method không tự nhận segment dư.

### 4.2. Chuyển đổi kiểu và lỗi xảy ra sau matching

URI variable ban đầu là giá trị text. Spring có thể dùng hệ thống `ConversionService` cùng các converter/formatter để chuyển thành `long`, `UUID`, `Enum` hoặc kiểu dữ liệu được ứng dụng hỗ trợ.

Ví dụ:

~~~java
@GetMapping("/orders/{id}")
public String uuid(@PathVariable("id") java.util.UUID id) {
    return id.toString();
}
~~~

Với `/orders/not-a-uuid`, route `/orders/{id}` vẫn có thể **match**, sau đó conversion từ String sang UUID thất bại. Xử lý lỗi mặc định của Spring MVC thường trả `400 Bad Request`. Đây là bước khác với regex constraint khiến URL **không match ngay từ đầu**.

### 4.3. @PathVariable khác @RequestParam

~~~java
@GetMapping("/products/{id}")
public String read(
        @PathVariable("id") long id,
        @RequestParam(name = "lang", defaultValue = "vi") String lang) {
    return id + ":" + lang;
}
~~~

Request `GET /products/42?lang=en` trả:

~~~text
42:en
~~~

Biến `id` thuộc path, còn `lang` thuộc query parameter. `/products/42?lang=en` và `/products/42?lang=vi` có **cùng phần path** khi Spring so URL pattern. Một mapping có thể dùng thêm điều kiện `params` nếu thực sự muốn chọn handler dựa trên query, nhưng đó là điều kiện riêng.

## 5. Named catch-all {*path}: capture nhiều segment

Khi cần lấy trọn phần đường dẫn còn lại:

~~~java
@GetMapping("/files/{*path}")
public String file(@PathVariable("path") String path) {
    return path;
}
~~~

Với request `GET /files/manuals/java/intro.pdf`, biến `path` nhận:

~~~text
/manuals/java/intro.pdf
~~~

**Giá trị capture bao gồm dấu slash đầu tiên** ở phần path còn lại trong ví dụ chuẩn của Spring. Vì vậy không nên mặc định giá trị là `manuals/java/intro.pdf`.

| Mapping | Khớp qua nhiều segment? | Có biến tên? |
| --- | --- | --- |
| `/files/{name}` | Không | Có: `name` |
| `/files/*` | Không | Không |
| `/files/**` | Có | Không |
| `/files/{*path}` | Có | Có: `path` |

Hãy dùng `{*path}` cho các route thực sự cần cây đường dẫn, ví dụ đường dẫn phân cấp của tài liệu trong một storage namespace. Tuy nhiên **không nối chuỗi path do client cung cấp vào đường dẫn file của hệ điều hành rồi mở file trực tiếp**. Cần kiểm tra root cho phép, canonical path, path traversal `..`, symlink, URL encoding và quyền truy cập. Một named catch-all chỉ là cơ chế match URL, **không bảo đảm an toàn dữ liệu**.

## 6. Regex constraint: {name:regex}

URI template có thể ràng buộc định dạng của segment ngay tại thời điểm tìm handler:

~~~java
@GetMapping("/products/{id:[0-9]+}")
public String product(@PathVariable("id") long id) {
    return "id=" + id;
}
~~~

Regex `[0-9]+` chấp nhận một hoặc nhiều chữ số ASCII. Các trường hợp:

~~~text
/products/42       MATCH
/products/007      MATCH
/products/abc      KHÔNG MATCH
/products/42abc    KHÔNG MATCH
/products/42/x     KHÔNG MATCH
~~~

Ràng buộc regex được áp dụng cho **segment của path**, không kiểm tra JSON body và không quyết định sự tồn tại của một tài nguyên trong database.

### 6.1. Regex và Java type là hai bước độc lập

So sánh:

~~~text
Route 1: /books/{id:[0-9]+}
         GET /books/abc
         → regex không match → xét route khác hoặc thường 404

Route 2: /books/{id}
         Java argument: @PathVariable long id
         GET /books/abc
         → route match → String→long conversion lỗi → thường 400
~~~

Một chuỗi rất lớn như `99999999999999999999999999999` vẫn thỏa `[0-9]+` nhưng **không fit trong Java `long`**. Khi đó argument conversion thất bại dù regex đã match.

Quyết định dùng regex phụ thuộc hợp đồng API:
- Nếu muốn định tuyến ID số và slug chữ sang hai handler riêng, constraint có thể hữu ích.
- Nếu muốn một endpoint tiếp nhận mọi input rồi trả lỗi validation có thông điệp cụ thể, để `{id}` không ràng buộc và validate/convert có thể hợp lý hơn.
- Không mặc định rằng request sai định dạng lúc nào cũng nên trả 400 hay 404; trạng thái thực tế phụ thuộc tầng thất bại và các handler đang đăng ký.

### 6.2. Regex slug

~~~java
@GetMapping("/articles/{slug:[a-z][a-z0-9-]*}")
public String article(@PathVariable("slug") String slug) {
    return "slug=" + slug;
}
~~~

Pattern này bắt buộc ký tự đầu là chữ thường ASCII, tiếp theo có thể là chữ thường, số hoặc dấu gạch nối.

| Path | Match? | Giải thích |
| --- | --- | --- |
| `/articles/spring-mvc` | Có | Chỉ chứa ký tự cho phép |
| `/articles/a1` | Có | Bắt đầu bằng chữ |
| `/articles/1st` | Không | Ký tự đầu là số |
| `/articles/SPRING` | Không | Chữ hoa không thuộc pattern |
| `/articles/lập-trình` | Không | Chữ có dấu không thuộc `[a-z]` |
| `/articles/a/b` | Không | Có hai segment sau `/articles` |

Regex trên chỉ là ví dụ cho **slug ASCII**. Nếu yêu cầu định danh tiếng Việt, phải chọn quy tắc slug/Unicode normalization và encoding nhất quán, không tự thay tất cả input tiếng Việt bằng pattern này.

### 6.3. Escape biểu thức chính quy trong Java string

Với regex Java như `\d+`, vì dấu `\` còn nằm bên trong Java string literal nên cần escape trong source thành `\\d+`. Ví dụ source Java:

~~~java
@GetMapping("/numbers/{id:\\d+}")
public String number(@PathVariable("id") long id) {
    return Long.toString(id);
}
~~~

Nếu muốn tránh nhầm số lượng dấu backslash ở các tầng Java string → URI template → Java regex, dùng `[0-9]+` trong ví dụ đơn giản thường dễ đọc hơn.

Không đưa regex từ client vào route declaration. Routing metadata phải được định nghĩa có kiểm soát khi khởi tạo ứng dụng; nội dung người dùng không được phép trở thành biểu thức Java regex tùy ý ở runtime để tránh nhập nhằng, hiệu năng khó dự đoán và regex denial-of-service.

### 6.4. Cẩn trọng với regex phức tạp

Spring cũng có thể trích nhiều biến từ một path segment, chẳng hạn tên, version và extension của artifact. Ví dụ cú pháp theo tài liệu Spring:

~~~java
@GetMapping("/{name:[a-z-]+}-{version:[0-9]+}{ext:\\.[a-z]+}")
public String artifact(
        @PathVariable("name") String name,
        @PathVariable("version") String version,
        @PathVariable("ext") String ext) {
    return name + "|" + version + "|" + ext;
}
~~~

Đây là **method minh họa bên trong controller**, cần import annotation; nó không phải chương trình Java độc lập. Nếu phần `name` được phép chứa `-`, việc phân tách các thành phần cùng segment có thể khó hiểu khi định dạng thực tế phức tạp. Thiết kế URI đơn giản hơn như `/artifacts/{name}/versions/{version}` thường giúp documentation và authorization dễ đọc hơn.

Dùng regex để giới hạn **cú pháp**, tiếp tục thực hiện business validation sau khi controller nhận argument. Việc một slug match pattern không có nghĩa nó tồn tại hoặc người dùng có quyền truy cập.

## 7. Khi nhiều pattern cùng match: quy tắc specificity

Giả sử controller khai báo hai route:

~~~java
@GetMapping("/products/search")
public String search() {
    return "search";
}

@GetMapping("/products/{id}")
public String byId(@PathVariable("id") String id) {
    return "id=" + id;
}
~~~

Request `GET /products/search` thỏa cả `/products/search` và `/products/{id}`, nhưng **route literal cụ thể hơn được chọn**. Thứ tự hai method trong source Java **không phải quy tắc ưu tiên**.

Với `PathPatternParser`, Spring so sánh ứng viên bằng cơ chế như `PathPattern.SPECIFICITY_COMPARATOR`:
- Các pattern cụ thể, ít wildcard/variables thường ưu tiên hơn.
- Catch-all `**` và `{*path}` được xếp sau những pattern thông thường có thể match.
- Khi có nhiều candidate cùng điểm, độ dài/cấu trúc pattern và điều kiện request mapping khác được xem xét.
- Nếu vẫn không thể phân biệt kết quả phù hợp, route có thể bị đánh giá mơ hồ, gây lỗi khi đăng ký hoặc lúc xử lý request.

Đừng lập trình theo giả định “cái nào khai báo trước sẽ thắng”.

| Request | Pattern cùng có thể match | Handler được ưu tiên thông thường |
| --- | --- | --- |
| `GET /products/search` | `/products/search`, `/products/{id}` | Literal search |
| `GET /assets/logo.png` | `/assets/*.png`, `/assets/{*path}` | One-segment PNG |
| `GET /assets/icons/logo.png` | `/assets/{*path}` | Catch-all |
| `GET /users/42` | `/users/{id}`, `/users/{*rest}` | Single-segment variable |
| `GET /users/42/settings` | `/users/{*rest}` | Catch-all (nếu không có route cụ thể hơn) |

Bảng giả định các điều kiện HTTP method, headers, produces/consumes, params cũng phù hợp. Một path match tốt không thể thắng nếu mapping không chấp nhận method của request.

### 7.1. Ambiguous mapping thường xuất hiện thế nào?

Ví dụ hai method:

~~~java
@GetMapping("/items/{id}")
public String byId(@PathVariable("id") String id) {
    return id;
}

@GetMapping("/items/{name}")
public String byName(@PathVariable("name") String name) {
    return name;
}
~~~

Tên biến `id` và `name` **không đủ phân biệt URL**: một segment bất kỳ có thể match cả hai. Spring có thể phát hiện mapping tương đương lúc khởi tạo hoặc ambiguous handler khi request được xử lý, tùy cách đăng ký/điều kiện. Phương án tốt hơn:
- Tách namespace: `/items/by-id/{id}` và `/items/by-name/{name}`.
- Hoặc dùng regex **không chồng lấn**, ví dụ `{id:[0-9]+}` và slug bắt đầu bằng chữ.
- Hoặc dùng một endpoint `/items/{key}` rồi giải quyết loại key trong nghiệp vụ.

Không thêm thêm wildcard để “hết lỗi ambiguous” nếu nó khiến URL quá rộng. Hãy diễn đạt thiết kế tài nguyên trước rồi mới chọn syntax.

## 8. Ví dụ Spring Boot 3 hoàn chỉnh có thể chạy

Dùng một dự án Spring Boot 3.x có Java 17+ với dependency `spring-boot-starter-web`. Tệp `src/main/java/demo/routing/RoutingApplication.java` chứa một public main class và một controller package-private nằm cùng package để Spring Boot component scan phát hiện.

~~~java
package demo.routing;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class RouteController {

    @GetMapping("/products/search")
    public Map<String, String> search() {
        return Map.of("route", "search");
    }

    @GetMapping("/products/{id:[0-9]+}")
    public Map<String, String> byId(@PathVariable("id") long id) {
        return Map.of("route", "by-id", "value", Long.toString(id));
    }

    @GetMapping("/products/{slug:[a-z][a-z0-9-]*}")
    public Map<String, String> bySlug(@PathVariable("slug") String slug) {
        return Map.of("route", "by-slug", "value", slug);
    }

    @GetMapping("/assets/*.png")
    public Map<String, String> png() {
        return Map.of("route", "one-png-segment");
    }

    @GetMapping("/assets/{*path}")
    public Map<String, String> asset(@PathVariable("path") String path) {
        return Map.of("route", "catch-all", "path", path);
    }

    @GetMapping("/reports/{year:[0-9]+}/{month:[0-9]+}")
    public Map<String, Integer> report(
            @PathVariable("year") int year,
            @PathVariable("month") int month) {
        return Map.of("year", year, "month", month);
    }
}
~~~

**Giải thích tính chạy được:** trong một project Spring Boot hợp lệ có plugin, repository và dependency, public class `RoutingApplication` khớp tên file, controller nằm trong cùng package được scan, `Map.of` có từ Java 9, record không bắt buộc. JSON converter thường là Jackson đi cùng starter web. Đây là mã ứng dụng phụ thuộc Spring, không phải một file có thể `javac` độc lập khi không có classpath.

Trong `build.gradle` đã cấu hình Spring Boot plugin và repositories, dependencies cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Khởi chạy trên macOS/Linux:

~~~bash
./gradlew bootRun
~~~

Hoặc Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Giả định cổng 8080 và không đổi context path, gọi:

~~~bash
curl -i "http://localhost:8080/api/products/search"
curl -i "http://localhost:8080/api/products/42"
curl -i "http://localhost:8080/api/products/spring-mvc"
curl -i "http://localhost:8080/api/assets/logo.png"
curl -i "http://localhost:8080/api/assets/icons/logo.png"
curl -i "http://localhost:8080/api/reports/2026/10"
~~~

Các JSON body được kỳ vọng, không cố định thứ tự field hoặc response headers:

| Request | Handler | JSON body tương đương |
| --- | --- | --- |
| `/api/products/search` | `search()` | `{"route":"search"}` |
| `/api/products/42` | `byId(42)` | `{"route":"by-id","value":"42"}` |
| `/api/products/spring-mvc` | `bySlug("spring-mvc")` | `{"route":"by-slug","value":"spring-mvc"}` |
| `/api/assets/logo.png` | `png()` | `{"route":"one-png-segment"}` |
| `/api/assets/icons/logo.png` | `asset(...)` | `{"route":"catch-all","path":"/icons/logo.png"}` |
| `/api/reports/2026/10` | `report(2026,10)` | `{"year":2026,"month":10}` |

Với `/api/products/search`, regex slug cũng có thể match vì `search` là chữ thường. Nhưng literal route cụ thể hơn nên được chọn.

Thử request không hợp pattern:

~~~bash
curl -i "http://localhost:8080/api/products/Hello"
curl -i "http://localhost:8080/api/products/42/extra"
curl -i "http://localhost:8080/api/reports/2026/Oct"
~~~

Nếu không có route khác, thường là 404: `Hello` không thuộc regex ID hoặc slug; `42/extra` có segment dư; `Oct` không phải chữ số. Response lỗi thực tế có thể do Spring Boot error handling/static resource mapping hoặc Spring Security tùy cấu hình.

Thử giá trị số quá lớn:

~~~bash
curl -i "http://localhost:8080/api/products/99999999999999999999999999"
~~~

Regex `[0-9]+` chấp nhận các chữ số, nhưng kiểu `long` không chứa được số đó. Argument resolution có thể trả 400. Qua đây có thể thấy **regex match không thay thế type conversion**.

## 9. Kiểm thử route bằng MockMvc

Với project Spring Boot có dependency test:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Một class test `src/test/java/demo/routing/RoutingApplicationTests.java`, cùng package với main application:

~~~java
package demo.routing;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RoutingApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void literalWinsOverSlug() throws Exception {
        mvc.perform(get("/api/products/search"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.route").value("search"));
    }

    @Test
    void numberIsCapturedAndConverted() throws Exception {
        mvc.perform(get("/api/products/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.route").value("by-id"))
                .andExpect(jsonPath("$.value").value("42"));
    }

    @Test
    void nestedPathUsesCatchAll() throws Exception {
        mvc.perform(get("/api/assets/icons/logo.png"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.route").value("catch-all"))
                .andExpect(jsonPath("$.path").value("/icons/logo.png"));
    }
}
~~~

Chạy trong project Gradle có wrapper và JUnit Platform:

~~~bash
./gradlew test
~~~

Ba test lần lượt kiểm tra route tĩnh thắng route slug, giá trị ID được convert và catch-all capture path nhiều segment. `MockMvc` kiểm tra Spring MVC routing/response mà không cần mở cổng network thực, nhưng **không đại diện đầy đủ cho proxy, Servlet container và URL encoding của production**. Nếu security hoặc ingress có path rewrite, cần thêm integration test chạy ở môi trường tương đương.

## 10. Các tình huống biên và thay đổi phiên bản

### 10.1. Trailing slash

`/api/products/42` và `/api/products/42/` khác nhau. Từ Spring Framework 6.0, việc match **trailing slash tùy chọn không được bật mặc định** như một số cấu hình/phiên bản trước. Vì vậy route `/api/products/{id}` không tự bảo đảm nhận cả hai dạng.

Giải pháp có thể là canonical URL, redirect ở proxy/filter theo chính sách rõ ràng hoặc khai báo đường dẫn bổ sung cần hỗ trợ. Với POST, redirect có thể ảnh hưởng HTTP method; cần chọn loại redirect phù hợp. Đừng âm thầm sửa route bằng cách thêm catch-all quá rộng.

### 10.2. Dấu chấm, suffix và extension

`/users/alice.json` có thể được capture bởi `/users/{name}` thành segment chứa dấu chấm. Spring MVC hiện đại **không tự động dùng `.*` suffix pattern matching** theo mặc định từ Spring 5.3. Dùng `Accept` và `produces` để thương lượng JSON/XML rõ ràng hơn việc suy từ phần mở rộng.

Nếu pattern khai báo tường minh `/images/*.png` thì dấu `.png` vẫn là một phần pattern bình thường, không phải cơ chế suy đoán media type.

### 10.3. URL encoding và dấu slash mã hóa

Ký tự `%2F` đại diện cho slash được encode. Nhưng proxy, container và framework có các chính sách khác nhau về việc chấp nhận/giải mã encoded slash. `PathPatternParser` so pattern trên cấu trúc `PathContainer` theo từng segment nhằm tránh lỗi giải mã toàn path rồi làm thay đổi cấu trúc; điều đó **không bảo đảm** mọi reverse proxy, Servlet container đều chấp nhận encoded slash hoặc xử lý giống nhau.

Đặc biệt khi phân quyền, thành phần security và handler mapping phải đồng thuận về path normalization. Cần kiểm thử encoded slash, double encoding, dot segments và dấu `;` ở ingress/container thực tế; không dựa vào đơn vị test của Spring MVC để kết luận an toàn production.

### 10.4. Unicode, chữ hoa/thường và slug

Regex `[a-z]+` chỉ cho chữ thường ASCII. Nếu slug có tiếng Việt, emoji hoặc ký tự Unicode, cần quyết định chuẩn hóa, percent encoding và giới hạn định dạng một cách nhất quán. Path matching thông thường phân biệt chữ hoa/thường trừ khi được cấu hình khác.

Nên tạo URL bằng URI builder hoặc thư viện HTTP thay vì nối dữ liệu raw từ client vào URL mà không encode. Khi thay đổi quy tắc slug, cân nhắc các URL cũ, link ngoài, bookmark và redirect để tránh phá hỏng hợp đồng public API.

### 10.5. Semicolon và matrix variables

Path có thể chứa semicolon content, ví dụ:

~~~text
/products/42;color=red;size=large
~~~

Spring MVC có cơ chế `@MatrixVariable` cho path parameters. `PathPattern` hỗ trợ parse segment và semicolon content theo thiết kế, nhưng container/proxy/security có thể thay đổi hoặc từ chối những URL này. Chỉ sử dụng matrix variables khi cả hệ thống có hợp đồng và kiểm thử rõ. Đừng nhầm chúng với query parameters dạng `?color=red&size=large`.

### 10.6. Context path và reverse proxy

Giả sử ứng dụng có `server.servlet.context-path=/store`, controller `@RequestMapping("/api")` và `@GetMapping("/products/{id}")`, URL gọi trực tiếp là `/store/api/products/42`. Controller **không viết** `/store` vào mapping.

Nếu reverse proxy phục vụ `/platform/store/api/products/42` nhưng forward nội bộ thành `/store/api/products/42`, prefix `/platform` thuộc proxy. Phải biết proxy giữ hay xóa prefix khi chẩn đoán 404. Forwarded headers chỉ nên được tin khi đến từ proxy đáng tin cậy.

## 11. Lỗi phổ biến và cách debug

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `/items/abc` trả 404 | Regex ID chỉ cho số; route không match | Mapping registry, regex, URL thực |
| `/items/abc` trả 400 | Route `{id}` đã match nhưng convert sang `long` lỗi | Argument resolver, exception handling |
| `/items/search` chạy vào handler lạ | Thiếu literal route hoặc mapping conditions khác | Specificity, HTTP method, consumes/produces |
| `/files/a/b.png` không match `*.png` | Dấu `*` không vượt slash | Cấu trúc path, có cần `{*path}` không |
| App lỗi lúc startup | Catch-all giữa pattern hoặc mapping mơ hồ | Log startup và PathPatternParser |
| Dấu slash cuối trả 404 | Trailing slash không được match mặc định | URL chuẩn và route declaration |
| Chỉ lỗi sau gateway | Proxy rewrite/encoding/context path khác | Path bên ngoài và bên trong |
| URL không tồn tại nhưng trả HTML 200 | Fallback/static resource catch-all có thể đã nhận | Handler đã chọn, Content-Type, body |

Quy trình điều tra ngắn:

1. Kiểm tra URL thực client gửi, loại HTTP method và context path.
2. Xem những `@RequestMapping` đang được đăng ký, bao gồm class prefix, method, params và media type.
3. Xác định path **không match pattern** hay **đã match nhưng argument conversion lỗi**.
4. Nếu nhiều route hợp lệ, kiểm tra specificity/ambiguity; không suy luận theo thứ tự method.
5. Với route có `**` hoặc `{*path}`, xem các path con bị catch-all nhận ngoài ý muốn.
6. Kiểm tra status/header/body HTTP thực tế và log handler/exception resolver.
7. Với encoding/redirect/proxy, xác minh hành vi end-to-end.

Có thể thử:

~~~bash
curl -i "http://localhost:8080/api/products/42"
curl -i "http://localhost:8080/api/products/search"
curl -i "http://localhost:8080/api/assets/icons/logo.png"
~~~

Nếu dùng Spring Boot Actuator và cho phép endpoint mappings với quyền phù hợp, `/actuator/mappings` có thể giúp xem các handler đã đăng ký. Không đưa endpoint quản trị ra Internet công khai.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Có hai route `GET /members/latest` và `GET /members/{id}`. Request `GET /members/latest` được chọn thế nào?

**Câu 2.** Vì sao `/files/*.csv` không match `/files/reports/2026.csv`? Muốn capture toàn bộ phần còn lại nên dùng syntax nào?

**Câu 3.** `/users/{id:[0-9]+}` với argument `long id`. Phân biệt kết quả thường thấy khi gọi `/users/abc` và `/users/999999999999999999999`.

**Câu 4.** `/teams/{team}/members/{member}` nhận request `/teams/core/members/lan`. Các giá trị capture là gì?

**Câu 5.** Tại sao `/resources/**/logo.png` không hợp lệ dưới `PathPatternParser`? Nên thiết kế ra sao?

**Câu 6.** Named catch-all `/files/{*path}` nhận `/files/docs/manual.pdf`; `path` là `docs/manual.pdf` hay `/docs/manual.pdf`? Có nên dùng raw value như filesystem path?

**Câu 7.** Regex `[a-z-]+` có nhận `Lập-trình` hay không? Nếu muốn chấp nhận Unicode cần xét điều gì?

### Đáp án giải thích

1. Literal route `/members/latest` cụ thể hơn variable `/members/{id}`, nên thường được ưu tiên.
2. `*` chỉ trong một segment. Dùng `/files/{*path}` để capture nhiều segment, hoặc `/files/**` nếu chỉ cần match.
3. `abc` không match regex nên có thể 404; chuỗi chỉ gồm số nhưng vượt miền giá trị `long` match regex rồi lỗi conversion, thường 400.
4. `team="core"`, `member="lan"`, mỗi biến nhận một segment.
5. `**` catch-all phải ở cuối với `PathPatternParser`. Dùng `/resources/{*path}` có giới hạn và kiểm tra đuôi trong service nếu thật sự cần, hoặc tạo các route cụ thể.
6. `path="/docs/manual.pdf"` có dấu slash đầu; không dùng trực tiếp để mở file. Cần kiểm tra traversal, normalization và quyền.
7. Không, regex ASCII không nhận chữ hoa hay ký tự có dấu. Cần thiết kế slug/Unicode normalization và encoding nhất quán với proxy/container.

## 13. Checklist áp dụng

Khi xây route Spring MVC:

1. Ưu tiên URI tĩnh và `{id}` một segment có ngữ nghĩa rõ.
2. Dùng regex chỉ khi định dạng ID/slug là một phần của hợp đồng URL.
3. Hiểu `?` và `*` chỉ điều khiển ký tự **trong segment**.
4. Đặt `**` hoặc `{*path}` ở cuối pattern và giới hạn namespace.
5. Dự đoán specificity khi literal, variable, wildcard giao nhau; tránh ambiguous routes.
6. Phân biệt path matching với argument conversion để xử lý lỗi đúng.
7. Test cả URL hợp lệ, URL sai regex, conversion failure, nhiều segment và trailing slash.
8. Kiểm thử security và URL encoding trên container/proxy thật nếu triển khai public.

Tư duy chính là: **pattern quyết định route match; argument resolver chuyển dữ liệu đã capture thành Java value; controller xử lý nghiệp vụ; return-value handler tạo HTTP response.** Hiểu ranh giới đó giúp bạn thiết kế REST endpoint chính xác và debug 404/400 theo đúng nguyên nhân.

**Tài liệu chuẩn:** Spring Framework Reference, *Mapping Requests / URI Patterns / Pattern Comparison*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html ; Spring Framework Reference, *Path Matching*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/path-matching.html ; Spring MVC reference về `@PathVariable` và `@RequestMapping`.
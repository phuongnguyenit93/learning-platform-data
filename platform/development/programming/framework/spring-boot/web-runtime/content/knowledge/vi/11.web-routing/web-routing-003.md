# Phân biệt định tuyến theo đường dẫn, header và query parameter trong Spring Boot

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Hiểu **định tuyến web** là bước chọn handler/controller nào sẽ xử lý một HTTP request, trước khi xử lý logic nghiệp vụ.
2. Phân biệt ba nguồn điều kiện **URL path**, **request header**, **request parameter** (thường nằm trong query string) của Spring MVC và Spring WebFlux.
3. Sử dụng chính xác **path/headers/params** trên @RequestMapping, @GetMapping, @PostMapping, đồng thời phân biệt với **@PathVariable, @RequestHeader, @RequestParam** dùng để đọc giá trị.
4. Kết hợp nhiều điều kiện, hiểu tính phù hợp, mức độ đặc hiệu và cách tránh handler mapping mơ hồ.
5. Viết ứng dụng **Spring Boot 3.3.x, Java 17+** với các endpoint minh họa riêng từng kiểu routing và một endpoint phối hợp cả header/query.
6. Kiểm tra routing bằng **curl** và **MockMvc**, nhận diện lỗi 400, 404, 405, 406, 415 theo đúng tầng xử lý.
7. Chọn phương án thiết kế API dễ duy trì, an toàn, nhất quán với cache, proxy, trình duyệt và ứng dụng client.

**Phạm vi:** Nội dung tập trung vào HTTP handler routing ở Spring Boot web runtime, ưu tiên Spring MVC và mở rộng sang annotated controllers của Spring WebFlux. Các ví dụ chạy trên **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**. Bài không đề cập routing của Spring Cloud Gateway như một chức năng tương đương của controller.

## 1. Định tuyến là gì? Nó xảy ra ở đâu?

Xét ba request:

~~~http
GET /api/items/7 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

~~~http
GET /api/items?view=summary HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

~~~http
GET /api/channels HTTP/1.1
Host: localhost:8080
X-Channel: mobile
Accept: text/plain
~~~

Chúng có thể cùng đến một máy chủ nhưng cần được gửi tới các method khác nhau:

- Request thứ nhất định danh tài nguyên bằng **path** /api/items/7.
- Request thứ hai dùng **query parameter** view=summary để chọn cách biểu diễn danh sách.
- Request thứ ba dùng **request header** X-Channel: mobile để chọn biến thể xử lý.

Trong Spring MVC, luồng logic:

~~~text
HTTP client
    |
    v
Embedded Tomcat / Servlet container
    |
    v
Servlet filters, Spring Security (nếu có)
    |
    v
DispatcherServlet
    |
    v
HandlerMapping
    |
    +-- HTTP method? GET/POST/PUT/DELETE?
    +-- URL path phù hợp?
    +-- params condition phù hợp?
    +-- headers condition phù hợp?
    +-- consumes và produces phù hợp?
    |
    v
HandlerAdapter -> argument resolvers
    |
    v
Controller method -> service
    |
    v
Response body / view -> HTTP response
~~~

**Routing diễn ra trước khi controller được gọi.** Sau khi handler được chọn, Spring mới bind những giá trị như @PathVariable, @RequestParam và @RequestHeader vào tham số Java.

Trong Spring WebFlux annotation controllers, cách khai báo @RequestMapping và các điều kiện path/headers/params tương tự, nhưng request đi qua reactive **HttpHandler/DispatcherHandler** thay vì Servlet DispatcherServlet.

### @RequestMapping là một tập hợp điều kiện

Ví dụ:

~~~java
@GetMapping(
    path = "/api/reports",
    params = {"format=brief", "page"},
    headers = "X-Client=mobile",
    produces = MediaType.APPLICATION_JSON_VALUE
)
~~~

Handler này chỉ phù hợp khi request, ở mức khái quát:

- Dùng method GET.
- Có path /api/reports.
- Có request parameter format bằng brief.
- Có request parameter page hiện diện.
- Có header X-Client với giá trị mobile.
- Client chấp nhận một response phù hợp application/json.

Nếu chỉ đáp ứng một phần, handler không phải lựa chọn phù hợp. Một controller có thể có nhiều mapping khác xử lý request đó, hoặc kết quả có thể là một phản hồi lỗi tương ứng.

## 2. Cấu trúc URL: path và query là hai phần khác nhau

Ví dụ URL:

~~~text
https://shop.example.com:8443/api/products/42?sort=price&limit=10
|------ scheme ---------|  |------ path ------| |--- query ------|
        host + port
~~~

Phân tích:

- Scheme: https.
- Host: shop.example.com.
- Port: 8443.
- Path: /api/products/42.
- Query: sort=price&limit=10.

Dấu chấm hỏi **?** phân chia path và query. Phần sau dấu ? không trở thành một path segment chỉ vì nó xuất hiện trong URL.

Ví dụ:

~~~text
/api/products/42?lang=vi
/api/products/42?lang=en
/api/products/42
~~~

Cả ba có **cùng path** /api/products/42. Nếu handler chỉ khai báo path và method, cả ba thường định tuyến tới cùng handler. Các giá trị query có thể được bind sau đó bằng @RequestParam.

### Routing không đồng nghĩa chọn theo Host

Host header hoặc HTTP/2 :authority thường xác định authority mà client hướng tới, nhưng các annotation routing cơ bản được đề cập ở đây chủ yếu chọn theo path, method, params, headers và media type. Việc định tuyến theo tên miền công khai có thể diễn ra trước Spring Boot tại DNS, reverse proxy, API gateway hoặc virtual host.

Nếu có nhiều service cùng nằm sau một gateway, cần phân biệt **gateway routing** với **controller method routing** bên trong từng ứng dụng.

## 3. Định tuyến theo đường dẫn: path-based routing

Đây là lựa chọn phổ biến nhất để định danh tài nguyên hoặc hành động HTTP rõ ràng.

~~~java
@GetMapping("/api/products")
List<Product> findAll() {
    // ...
}

@GetMapping("/api/products/{id}")
Product findById(@PathVariable long id) {
    // ...
}
~~~

Đây là hai đoạn method minh họa, chưa phải chương trình Java độc lập. Chúng biểu thị:

- GET /api/products chọn danh sách.
- GET /api/products/7 chọn tài nguyên có id bằng 7.

**@PathVariable không tạo ra route một mình.** Route tồn tại nhờ pattern /api/products/{id} trong @GetMapping; @PathVariable lấy phần được capture và chuyển thành tham số Java.

### Những dạng path pattern quan trọng

| Pattern | Ví dụ request phù hợp | Ý nghĩa |
|---|---|---|
| /api/books | /api/books | Đường dẫn tĩnh |
| /api/books/{id} | /api/books/42 | Capture một path segment |
| /api/{kind}/{id} | /api/books/42 | Capture nhiều segment |
| /files/*.pdf | /files/report.pdf | Wildcard trong một segment |
| /assets/** | /assets/css/main.css | Nhiều segment cuối đường dẫn |
| /users/{id:[0-9]+} | /users/42 | Path variable có regex constraint |

**Lưu ý PathPattern:** Spring MVC trên Boot 3.x sử dụng parsed path patterns theo cấu hình mặc định thông thường. Một số pattern catch-all với ** trong PathPattern không được phép nằm tùy ý giữa đường dẫn; nếu định nghĩa sai, ứng dụng có thể báo lỗi mapping ngay khi startup.

### Path specificity

Giả sử có:

~~~java
@GetMapping("/api/products/latest")
Product latest() {
    // ...
}

@GetMapping("/api/products/{id}")
Product byId(@PathVariable String id) {
    // ...
}
~~~

GET /api/products/latest có thể khớp cả pattern literal và pattern variable. Spring sử dụng quy tắc so sánh độ đặc hiệu để ưu tiên path tĩnh /latest trong trường hợp này. Tuy nhiên, đừng dựa vào những pattern chồng lấn khó hiểu cho API công khai; các đường dẫn càng rõ ràng càng dễ kiểm thử và duy trì.

### Vấn đề dấu gạch chéo cuối đường dẫn

~~~text
/api/products
/api/products/
~~~

Không nên giả định cả hai URL luôn được xem là một trong mọi phiên bản/configuration. Trong Spring Framework 6.x, việc tự động nhận thêm optional trailing slash không còn là mặc định như ở một số phiên bản cũ. Hãy dùng canonical URL thống nhất và chỉ bật redirect/route bổ sung khi thực sự cần.

### Path và context path

Giả sử:

~~~properties
server.servlet.context-path=/shop
~~~

và controller khai báo:

~~~java
@GetMapping("/api/products")
~~~

Đối với Spring MVC servlet application, URL bên ngoài thường là /shop/api/products. Phần **/shop** do context path của ứng dụng cung cấp, không phải một path segment mà bạn nên lặp lại trong annotation.

WebFlux có cơ chế base path khác; không dùng server.servlet.context-path để áp dụng mặc nhiên cho reactive web application.

## 4. Định tuyến theo header: headers condition

HTTP header là metadata gửi cùng request. Spring có thể dùng header để chọn handler, ví dụ khi API có biến thể xử lý theo một protocol version hoặc representation riêng.

~~~java
@GetMapping(
    path = "/api/catalog",
    headers = "X-Channel=mobile"
)
String mobile() {
    return "mobile";
}

@GetMapping(
    path = "/api/catalog",
    headers = "X-Channel=web"
)
String web() {
    return "web";
}
~~~

Đây là minh họa method đặt trong @RestController. Cả hai cùng path và GET, nhưng yêu cầu khác ở header X-Channel.

Client gửi:

~~~http
GET /api/catalog HTTP/1.1
X-Channel: mobile
~~~

Framework có thể chọn method mobile.

### Cú pháp headers

| Biểu thức | Điều kiện |
|---|---|
| headers="X-Debug" | Header X-Debug hiện diện |
| headers="!X-Debug" | Header X-Debug vắng mặt |
| headers="X-Channel=mobile" | Header có giá trị mobile |
| headers="X-Channel!=mobile" | Header không bằng mobile theo điều kiện |
| headers={"X-Channel=mobile","X-Trace"} | Cả giá trị channel và sự hiện diện trace đều phải thỏa |

Tên HTTP header là **case-insensitive** theo chuẩn HTTP, ví dụ X-Channel và x-channel là cùng tên field. Không nên mặc định **giá trị** header cũng không phân biệt hoa/thường. Việc so sánh giá trị do quy tắc từng field và mapping quyết định; với custom header, hãy thống nhất chính xác chuỗi.

### Header có thể dùng để chọn biến thể, không xác thực người dùng

Đặt:

~~~java
@GetMapping(
    path = "/api/admin",
    headers = "X-Role=admin"
)
~~~

**không tạo bảo mật.** Client có thể tự gửi X-Role: admin nếu header không được một thành phần tin cậy kiểm soát. Authentication và authorization cần được triển khai bằng Spring Security hoặc cơ chế bảo mật phù hợp, không dựa vào điều kiện mapping của header.

Có thể dùng header cho:

- Điều hướng một biến thể giao diện HTTP có hợp đồng rõ.
- Thử nghiệm feature/client version **không nhạy cảm**.
- Yêu cầu một protocol-specific header.
- Phân biệt các client nội bộ khi request đã có authentication và contract phù hợp.

Hạn chế tạo quá nhiều route khác nhau chỉ bởi các header tùy ý: chúng khó quan sát trong URL, thường bị proxy/gateway xử lý, và khiến test/caching khó hơn.

## 5. Header dùng để chọn route khác với @RequestHeader

Xem hai đoạn code:

~~~java
@GetMapping(
    path = "/api/hello",
    headers = "X-Channel=mobile"
)
String helloMobile() {
    return "hello mobile";
}
~~~

và:

~~~java
@GetMapping("/api/inspect")
String inspect(@RequestHeader("X-Channel") String channel) {
    return "channel=" + channel;
}
~~~

- headers="X-Channel=mobile" là **điều kiện chọn controller method**.
- @RequestHeader("X-Channel") là **cách lấy header sau khi route đã được chọn**.

Với ví dụ thứ hai, route /api/inspect vẫn phù hợp về path/method dù header thiếu; việc bind một @RequestHeader bắt buộc có thể gây **400 Bad Request** sau bước chọn handler. Đây không giống lỗi “không tìm thấy route phù hợp”.

Để header tùy chọn:

~~~java
@RequestHeader(value = "X-Channel", required = false) String channel
~~~

Có thể dùng defaultValue để cung cấp giá trị mặc định thay vì nhận null. Header chứa nhiều giá trị có thể được bind vào List hoặc MultiValueMap tùy API.

Một mapping chỉ cần xử lý chung dữ liệu header thường nên khai báo **một handler + @RequestHeader**, không cần tách thành nhiều handler bằng headers condition.

## 6. Định tuyến theo query parameter: params condition

Query parameter là cặp key/value phía sau dấu ? trong URL:

~~~text
GET /api/products?view=summary
GET /api/products?view=detail
GET /api/products?view=summary&page=2
~~~

Có thể chọn handler theo giá trị view:

~~~java
@GetMapping(path = "/api/products", params = "view=summary")
List<String> summary() {
    return List.of("pen", "notebook");
}

@GetMapping(path = "/api/products", params = "view=detail")
List<Product> detail() {
    // ...
}
~~~

Hai mapping khác nhau ở **params**. Giá trị view nằm trong query string khi client gọi GET ở ví dụ này.

### Cú pháp params

| Biểu thức | Ý nghĩa |
|---|---|
| params="debug" | Có request parameter debug |
| params="!debug" | Không có request parameter debug |
| params="view=summary" | Parameter view có giá trị summary |
| params="view!=summary" | Giá trị view không bằng summary theo điều kiện |
| params={"debug=true","page"} | debug có giá trị true **và** page hiện diện |

Nếu chỉ có params="debug", các URL ?debug, ?debug= và ?debug=true đều có thể đáp ứng điều kiện hiện diện, dù giá trị khác nhau. Muốn kiểm tra đúng true, dùng params="debug=true".

### Phân biệt query string với request parameters ở Servlet MVC

Trong Spring MVC, thuộc tính params của @RequestMapping kiểm tra **Servlet request parameters**. Với GET, nguồn thường là query string. Với application/x-www-form-urlencoded trong một số request POST, Servlet API có thể đưa các form fields vào request parameter map, nên đừng tuyệt đối hóa rằng params chỉ từng xét URL query.

Ví dụ bài này tập trung vào GET và query string. Khi muốn phân tích POST form, cần hiểu Content-Type, @RequestParam/@ModelAttribute và cách container parse parameters.

### @RequestParam không tự tạo route điều kiện

~~~java
@GetMapping("/api/products")
List<Product> list(
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "20") int size) {
    // ...
}
~~~

Method này có route theo **path /api/products và GET**. Tham số page/size được bind sau đó; Spring không tự tạo hai route cho ?page=1 và ?page=2.

Nếu một required @RequestParam bị thiếu, route vẫn có thể đã được chọn, rồi bước argument binding trả **400 Bad Request**. Ngược lại, nếu method có params="mode=summary" và request không thỏa điều kiện, method này không phải handler phù hợp ngay từ bước mapping.

Đó là sự khác biệt cốt lõi giữa **routing condition** và **argument binding**.

## 7. Bảng so sánh ba cơ chế

| Tiêu chí | Path | Header | Query parameter |
|---|---|---|---|
| Nằm ở đâu | Trước dấu ? của request target | Trong HTTP request headers | Sau dấu ? của URL |
| Khai báo route | path hoặc value | headers | params |
| Đọc dữ liệu sau khi chọn route | @PathVariable | @RequestHeader | @RequestParam |
| Ví dụ | /orders/42 | X-Channel: mobile | ?page=2 |
| Dùng tốt cho | Danh tính tài nguyên, cấu trúc API | Protocol/client variant, điều kiện metadata | Filter, sort, pagination, tùy chọn hiển thị |
| Nhìn trực tiếp trong URL | Có | Không | Có |
| Cache/proxy cần chú ý | URL path là thành phần cache key phổ biến | Cần xem Vary/custom cache policy | Query thường là phần URL cache key |
| Khả năng client tự sửa | Có | Có | Có |
| Có thể thay authentication không | Không | Không | Không |
| Dễ debug bằng browser address bar | Có | Không, cần devtools/curl | Có |

**Chọn đúng mô hình nghiệp vụ:** Resource id thường là path; trạng thái lọc/tìm kiếm thường là query; dữ liệu metadata mà không phù hợp cho URL có thể là header. Không đưa credentials hay dữ liệu rất nhạy cảm vào query chỉ vì @RequestParam thuận tiện: URL thường xuất hiện trong logs, lịch sử browser và hệ thống analytics.

## 8. Kết hợp path, headers, params: logic AND và OR

Ví dụ:

~~~java
@GetMapping(
    path = {"/api/products", "/api/items"},
    params = {"view=summary", "page"},
    headers = {"X-Channel=mobile", "X-Trace"},
    produces = MediaType.APPLICATION_JSON_VALUE
)
~~~

Giải thích:

- **Path array:** phù hợp khi URL là /api/products **hoặc** /api/items.
- **params array:** phải có view=summary **và** có page.
- **headers array:** phải có X-Channel=mobile **và** X-Trace.
- **produces:** response phải tương thích với khả năng client chấp nhận application/json.
- **@GetMapping:** HTTP method GET.

Không phải mọi mảng annotation đều có logic giống nhau: **các pattern path thay thế là OR; nhiều điều kiện params/headers là AND**. Nhiều HTTP methods trong @RequestMapping(method={...}) cũng là các lựa chọn cho method.

Ví dụ request thỏa điều kiện:

~~~http
GET /api/products?view=summary&page=2 HTTP/1.1
X-Channel: mobile
X-Trace: request-123
Accept: application/json
~~~

Nếu X-Trace thiếu, mapping trên không phải lựa chọn phù hợp, ngay cả khi path và query đúng. Nếu Accept chỉ chấp nhận text/plain trong khi method chỉ produces JSON, response có thể là 406 tùy tập hợp các mapping.

### Cấp class và cấp method

~~~java
@RestController
@RequestMapping(
    path = "/api",
    headers = "X-App=demo"
)
class ExampleController {

    @GetMapping(path = "/products", params = "view=summary")
    String summary() {
        return "ok";
    }
}
~~~

Đây là snippet minh họa. Class-level path /api kết hợp với method-level path /products; điều kiện header class-level tiếp tục áp dụng. Nếu yêu cầu có cả query view=summary và header X-App=demo, GET /api/products mới phù hợp.

**Ngoại lệ cần nhớ:** Với consumes/produces, một khai báo ở method-level có thể **ghi đè** điều kiện cùng loại ở class-level thay vì chỉ cộng thêm. Không suy rộng quy tắc kết hợp path/headers/params sang mọi attribute.

## 9. Request mapping conditions và argument binding là hai giai đoạn khác nhau

Trong Spring MVC:

~~~text
Bước 1: HandlerMapping lựa chọn handler
  - HTTP method, path, params, headers, consumes, produces

Bước 2: Argument resolvers lấy dữ liệu cho Java method
  - @PathVariable
  - @RequestParam
  - @RequestHeader
  - @RequestBody
  - cookie, model, request/response object, ...

Bước 3: Validation, service, response
~~~

Từ đó có ba trường hợp cần phân biệt:

**Trường hợp A — Không có route phù hợp**

Request GET /does-not-exist khi không có handler nào, thông thường trả 404.

**Trường hợp B — Route được chọn nhưng không bind được tham số**

~~~java
@GetMapping("/api/orders/{id}")
String order(@PathVariable long id) {
    return "order";
}
~~~

GET /api/orders/abc khớp path variable nhưng việc chuyển abc sang long thất bại; phản hồi thường là 400 thay vì 404.

**Trường hợp C — Có điều kiện mapping nhưng không thỏa**

~~~java
@GetMapping(path = "/api/orders", params = "view=summary")
String summary() {
    return "summary";
}
~~~

GET /api/orders?view=detail không đáp ứng params. Spring MVC có xử lý đặc thù cho một số mismatch (như request parameters), nên không thể tuyên bố **mọi** mismatch đều 404. Mã lỗi cuối cùng phụ thuộc vào những mapping khác, HTTP method, consumes/produces và exception handlers.

### Path, query và header không được kiểm tra với một thứ tự tùy ý do controller quy định

Spring Framework xây dựng thông tin mapping và so sánh các ứng viên. Không nên giả định rằng “route được khai báo trước sẽ luôn thắng” hoặc “Spring cứ thử controller từ trên xuống”. Nếu hai mapping không phân biệt đủ rõ, runtime có thể không chọn được hoặc kết quả lựa chọn gây bất ngờ.

## 10. Ví dụ hoàn chỉnh Spring Boot 3.3.x, Java 17+

Tạo một ứng dụng Spring Boot **Servlet / Spring MVC** có dependency starter-web. Ví dụ cố ý tạo các URL đơn giản, không phụ thuộc database.

### 10.1. Dependencies

Trong project Gradle Spring Boot đã có plugins/repositories phù hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây chỉ là phần dependencies trong build.gradle, không phải toàn bộ file build.gradle độc lập. Dùng Java 17 hoặc mới hơn tương thích với phiên bản Boot.

### 10.2. Java application

Tạo file **src/main/java/com/example/routing/RouteConditionsApplication.java**:

~~~java
package com.example.routing;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RouteConditionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(RouteConditionsApplication.class, args);
    }

    public record Item(long id, String name) {}

    public record SearchResult(
            String query, int limit, String client) {}

    @RestController
    @RequestMapping("/api")
    static class DemoController {

        // 1. Routing bằng path + @PathVariable.
        @GetMapping(
                path = "/items/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Item byId(@PathVariable("id") long id) {
            return new Item(id, "item-" + id);
        }

        // 2a. Cùng method/path, chọn handler theo query.
        @GetMapping(
                path = "/items",
                params = "view=summary",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        List<String> summary() {
            return List.of("pen", "notebook");
        }

        // 2b. Cùng method/path, nhưng query khác.
        @GetMapping(
                path = "/items",
                params = "view=detail",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        List<Item> details() {
            return List.of(
                    new Item(1, "pen"),
                    new Item(2, "notebook")
            );
        }

        // 3a. Chọn handler theo giá trị header.
        @GetMapping(
                path = "/channels",
                headers = "X-Channel=web",
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        String webChannel() {
            return "channel-web";
        }

        // 3b. Chọn handler theo giá trị header khác.
        @GetMapping(
                path = "/channels",
                headers = "X-Channel=mobile",
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        String mobileChannel() {
            return "channel-mobile";
        }

        // 4. Đồng thời yêu cầu cả query và header.
        @GetMapping(
                path = "/combined",
                params = {"debug=true", "page"},
                headers = "X-Trace",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Map<String, Object> combined(
                @RequestParam("page") int page,
                @RequestHeader("X-Trace") String trace) {
            return Map.of(
                    "page", page,
                    "trace", trace
            );
        }

        // 5. Chỉ bind query/header, không dùng chúng
        //    làm điều kiện phân nhánh handler.
        @GetMapping(
                path = "/search",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        SearchResult search(
                @RequestParam(
                        name = "q", defaultValue = "all") String q,
                @RequestParam(
                        name = "limit", defaultValue = "10") int limit,
                @RequestHeader(
                        name = "X-Client",
                        required = false) String client) {
            return new SearchResult(
                    q,
                    limit,
                    client == null ? "none" : client
            );
        }
    }
}
~~~

Đây là một **Java source file hoàn chỉnh cho project Spring Boot**, không phải ứng dụng javac thuần không cần dependency. Các nested static record và @RestController class nằm bên trong package com.example.routing; Spring Boot sẽ component scan controller này.

Tất cả endpoint chỉ trả dữ liệu minh họa. Không có authentication, database hoặc dữ liệu nhạy cảm. Vì vậy header condition X-Channel ở ví dụ chỉ phục vụ quan sát routing, **không đóng vai trò bảo mật**.

### 10.3. Chạy chương trình

Đặt trong src/main/resources/application.yml nếu muốn cổng cố định:

~~~yaml
server:
  port: 8080
~~~

Chạy tại thư mục gốc project:

~~~bash
./gradlew bootRun
~~~

Với PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Chờ Spring Boot thông báo ứng dụng đã khởi động. Nếu cổng 8080 đã được tiến trình khác dùng, đổi server.port và thay cổng trong các lệnh curl.

### 10.4. Thử routing theo path

~~~bash
curl -s -H 'Accept: application/json' \
  http://localhost:8080/api/items/7
~~~

Body JSON có ý nghĩa:

~~~json
{"id":7,"name":"item-7"}
~~~

Controller nhận @PathVariable("id") bằng 7, kiểu long. Nếu gọi /api/items/abc, pattern có thể match nhưng chuyển chuỗi abc sang long thất bại, thường dẫn đến 400.

### 10.5. Thử routing theo query parameter

~~~bash
curl -s 'http://localhost:8080/api/items?view=summary'
~~~

Response body:

~~~json
["pen","notebook"]
~~~

~~~bash
curl -s 'http://localhost:8080/api/items?view=detail'
~~~

Response body:

~~~json
[{"id":1,"name":"pen"},{"id":2,"name":"notebook"}]
~~~

Hai method trên đều là GET /api/items. Điều kiện params làm Spring phân biệt cách lựa chọn method, không phải @RequestParam trong chữ ký method.

Nếu URL là /api/items?view=other hoặc không có view, cả hai mapping có thể không phù hợp. **Không đoán cứng 404**: trong Spring MVC, việc tồn tại mapping đúng path/method nhưng không thỏa request parameter condition có thể được phản hồi bằng 400 do UnsatisfiedServletRequestParameterException, tùy context và exception handling.

### 10.6. Thử routing theo header

~~~bash
curl -s 'http://localhost:8080/api/channels' \
  -H 'X-Channel: web'
~~~

Body:

~~~text
channel-web
~~~

~~~bash
curl -s 'http://localhost:8080/api/channels' \
  -H 'X-Channel: mobile'
~~~

Body:

~~~text
channel-mobile
~~~

Header field-name không phân biệt hoa/thường theo HTTP. Ví dụ header x-channel: mobile thường được xử lý tương đương X-Channel: mobile.

Nếu thiếu X-Channel, không nên cố bắt mọi lỗi vào một mã số duy nhất trong ví dụ; trước tiên xem có handler khác cùng URL nhưng không có header condition không.

### 10.7. Thử điều kiện đồng thời header và query

~~~bash
curl -s -H 'Accept: application/json' \
  -H 'X-Trace: t-123' \
  'http://localhost:8080/api/combined?debug=true&page=2'
~~~

Body JSON chứa:

~~~json
{"page":2,"trace":"t-123"}
~~~

Thứ tự các key trong JSON không phải contract. Điều kiện mapping cần debug=true, page hiện diện và X-Trace hiện diện; sau khi handler được chọn, @RequestParam lấy page và @RequestHeader lấy X-Trace.

Thử bỏ riêng header X-Trace hoặc query debug=true để thấy không còn thỏa toàn bộ mapping. Dùng curl -i để quan sát status và response thực tế, không kết luận error type chỉ từ URL.

### 10.8. Thử sự khác biệt giữa binding và routing

~~~bash
curl -s -H 'X-Client: desktop' \
  'http://localhost:8080/api/search?q=java&limit=5'
~~~

Body JSON chứa:

~~~json
{"query":"java","limit":5,"client":"desktop"}
~~~

Gọi:

~~~bash
curl -s 'http://localhost:8080/api/search'
~~~

Response chứa giá trị mặc định:

~~~json
{"query":"all","limit":10,"client":"none"}
~~~

Hai request chọn **cùng method search**; @RequestParam và @RequestHeader chỉ cung cấp dữ liệu. Không có params hoặc headers mapping condition nào trên /api/search.

### 10.9. Windows PowerShell

Trong Windows PowerShell, dùng **curl.exe** để tránh bị hiểu thành alias Invoke-WebRequest:

~~~powershell
curl.exe -s "http://localhost:8080/api/items?view=summary"
curl.exe -s -H "X-Channel: mobile" "http://localhost:8080/api/channels"
curl.exe -s -H "X-Trace: t-123" "http://localhost:8080/api/combined?debug=true&page=2"
~~~

Trong PowerShell, dấu & bên trong URL cần đặt trong chuỗi có dấu nháy. Khi không có quote, shell có thể diễn giải ký tự điều khiển thay vì coi là thành phần URL.

## 11. Kiểm thử routing bằng MockMvc

Với starter-test, tạo file **src/test/java/com/example/routing/RouteConditionsApplicationTests.java**:

~~~java
package com.example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RouteConditionsApplicationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void routesByPathVariable() throws Exception {
        mockMvc.perform(get("/api/items/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.name").value("item-7"));
    }

    @Test
    void routesByQueryParameter() throws Exception {
        mockMvc.perform(
                get("/api/items").param("view", "summary"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0]").value("pen"));

        mockMvc.perform(
                get("/api/items").param("view", "detail"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].name").value("pen"));
    }

    @Test
    void routesByHeaderValue() throws Exception {
        mockMvc.perform(
                get("/api/channels").header("X-Channel", "web"))
            .andExpect(status().isOk())
            .andExpect(content().string("channel-web"));

        mockMvc.perform(
                get("/api/channels").header("X-Channel", "mobile"))
            .andExpect(status().isOk())
            .andExpect(content().string("channel-mobile"));
    }

    @Test
    void combinesHeaderAndQueryConditions() throws Exception {
        mockMvc.perform(get("/api/combined")
                    .param("debug", "true")
                    .param("page", "2")
                    .header("X-Trace", "t-123"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page").value(2))
            .andExpect(jsonPath("$.trace").value("t-123"));
    }

    @Test
    void bindsValuesWithoutExtraRoutingConditions() throws Exception {
        mockMvc.perform(get("/api/search")
                    .param("q", "java")
                    .param("limit", "5")
                    .header("X-Client", "desktop"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.query").value("java"))
            .andExpect(jsonPath("$.limit").value(5))
            .andExpect(jsonPath("$.client").value("desktop"));

        mockMvc.perform(get("/api/search"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.query").value("all"))
            .andExpect(jsonPath("$.limit").value(10))
            .andExpect(jsonPath("$.client").value("none"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Với PowerShell:

~~~powershell
.\gradlew.bat test
~~~

MockMvc thực thi pipeline Spring MVC mà **không cần mở cổng TCP thật**. Nó hữu ích để khẳng định mapping nào đã được chọn, body JSON có đúng không và argument binding diễn ra ra sao.

Đừng assert một lỗi 404 chung cho tất cả tình huống thiếu query/header. Nếu muốn kiểm thử đường lỗi, khẳng định **mã thực tế theo contract của endpoint và phiên bản Framework**, có thể dùng isBadRequest/isNotFound/isMethodNotAllowed... ở từng trường hợp cụ thể.

## 12. Khi nào mapping bị mơ hồ (ambiguous)?

Ví dụ không nên tạo:

~~~java
@GetMapping("/api/info")
String infoA() {
    return "a";
}

@GetMapping("/api/info")
String infoB() {
    return "b";
}
~~~

Hai method có cùng HTTP method và path, không có điều kiện bổ sung để phân biệt. Spring có thể báo **Ambiguous mapping** khi đăng ký mapping ở startup.

Một ví dụ khó nhận diện hơn:

~~~java
@GetMapping(path = "/api/info", params = "debug")
String debug() {
    return "debug";
}

@GetMapping(path = "/api/info", headers = "X-Verbose")
String verbose() {
    return "verbose";
}
~~~

Một request vừa có ?debug vừa có X-Verbose có thể đáp ứng cả hai nhóm điều kiện. Tùy quy tắc so sánh độ đặc hiệu của mapping, có thể có lựa chọn không như kỳ vọng hoặc trường hợp mơ hồ. Không nên tạo API phụ thuộc vào những tình huống chồng lấn mà người đọc phải suy đoán comparator.

**Thiết kế an toàn hơn:**

- Dùng một handler cho cùng một thao tác rồi bind các tùy chọn.
- Hoặc phân hoạch các route bằng các điều kiện **loại trừ lẫn nhau**, ví dụ view=summary và view=detail với hợp đồng giá trị đơn rõ ràng.
- Khi kết hợp điều kiện, lập ma trận tất cả tổ hợp path + method + query + header cần hỗ trợ.
- Thêm test cho từng tổ hợp có ý nghĩa và trường hợp thiếu điều kiện.
- Tránh dựa vào thứ tự khai báo method trong class.

### Cần phân biệt specificity của path và specificity của mapping đầy đủ

Path literal /api/items/latest thường đặc hiệu hơn /api/items/{id}. Nhưng ngoài path, Spring còn xét các điều kiện mapping khác như params, headers và media types. Một mapping có path phù hợp không có nghĩa chắc chắn được chọn nếu các điều kiện đi kèm không phù hợp.

## 13. Content-Type và Accept là trường hợp header đặc biệt

HTTP Content-Type và Accept đều là headers, nhưng Spring khuyến nghị biểu diễn chúng qua **consumes** và **produces**, thay vì viết điều kiện generic headers để thay thế.

Ví dụ:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
Product create(@RequestBody ProductInput input) {
    // ...
}
~~~

Đây là snippet minh họa và cần đặt trong controller có ProductInput/Product phù hợp.

- **consumes** xét media type **body request** mà handler hỗ trợ; thường liên quan Request Content-Type.
- **produces** xét representation mà server trả, phối hợp với request Accept.
- **headers** dùng các header conditions khác như X-Client hoặc X-Feature.
- **@RequestHeader("Content-Type")** chỉ lấy giá trị header; nó không tự thực hiện JSON decoding hay content negotiation.

Ví dụ trạng thái:

| Tình huống | Phản hồi điển hình |
|---|---|
| Path không có handler | 404 Not Found |
| Path đúng nhưng HTTP method sai, không có handler khác | 405 Method Not Allowed |
| Request Content-Type không phù hợp consumes | 415 Unsupported Media Type |
| Request Accept không phù hợp produces | 406 Not Acceptable |
| Controller được chọn, nhưng @RequestParam int parse sai | 400 Bad Request |
| Điều kiện params của mapping không phù hợp | Có thể 400 trong Spring MVC tùy match/exception handling |
| Điều kiện header custom không phù hợp | Thường không chọn mapping đó; status tùy các handler khác |

Không cố đoán mã lỗi chỉ dựa trên một dòng annotation mà chưa xem toàn bộ các handler cùng path, method và exception handlers.

## 14. Query parameter có nhiều giá trị, URL encoding và thứ tự

Query string có thể chứa lặp một key:

~~~text
/api/products?tag=java&tag=spring
~~~

Dùng binding:

~~~java
@GetMapping("/api/products")
List<String> tags(@RequestParam("tag") List<String> tags) {
    return tags;
}
~~~

Đây là method minh họa trong một REST controller. Có thể nhận nhiều giá trị tag (theo cơ chế binding), nhưng logic filter vẫn do ứng dụng thực thi.

Để giữ toàn bộ giá trị lặp và cả key, có thể dùng MultiValueMap<String,String> qua @RequestParam. Nếu chỉ dùng Map<String,String>, bạn có thể không bảo toàn đầy đủ các giá trị lặp.

### Khi dùng params="tag=java" với nhiều giá trị?

Đối với request parameters có thể lặp, việc so sánh với một giá trị có quy tắc phụ thuộc framework và cách container biểu diễn danh sách. Tránh thiết kế nhiều handler chỉ khác nhau bởi một key có thể chứa nhiều values, ví dụ tag=java và tag=spring cùng trên một URL. Thường tốt hơn dùng một handler và **@RequestParam List<String> tag** để tự xử lý filter.

### URL encoding

~~~text
q=hello%20world
name=Lan%20Anh
~~~

Phần %20 biểu diễn dấu cách trong URL encoding. Query parameter được decode trước khi bind vào tham số tương ứng theo quy tắc Servlet/WebFlux. Dấu **+** trong query có thể được giải mã thành space theo form-style encoding, nên khi cần literal plus sign phải encode đúng. Không tự viết String.split("&") / URLDecoder tùy tiện trong business controller nếu framework đã hỗ trợ binding.

### Case sensitivity và tên tham số

Thông thường **view** và **View** là hai tên parameter khác nhau trong request parameter map. Hãy thống nhất cách đặt tên (chẳng hạn lowercase camelCase) và không giả định framework tự đổi hoa/thường giống HTTP header field-name.

### Không dùng query cho thông tin cực kỳ nhạy cảm

URL thường xuất hiện ở:

- Lịch sử browser.
- Access log của web server, reverse proxy, CDN.
- Monitoring/tracing, analytics.
- HTTP cache key và link chia sẻ.

Hạn chế đặt access token, password, thông tin cá nhân không cần thiết trong query. Routing theo query không làm dữ liệu an toàn hơn so với việc truyền trong headers/body; cần bảo vệ đúng theo threat model.

## 15. Header routing với proxy, cache và trình duyệt

Header có thể không được chuyển tiếp nguyên vẹn ở mọi lớp mạng:

~~~text
Browser / Mobile
        |
        v
Reverse proxy / API gateway
        |
        v
Spring Boot @RequestMapping(headers=...)
~~~

Proxy có thể thêm, xóa hoặc chuẩn hóa một số headers theo cấu hình. Trước khi debug controller, xác minh request cuối cùng **đến được Spring** mang chính xác header mong đợi.

### Header khác với HTTP Host

Client gửi:

~~~http
GET /api/catalog HTTP/1.1
Host: shop.example.com
X-Channel: mobile
~~~

Host biểu diễn authority của request và có thể được reverse proxy dùng để chọn upstream. X-Channel là custom metadata mà controller có thể dùng trong headers condition.

Spring không tự điều hướng request sang domain/port khác chỉ vì @GetMapping(headers="X-Channel=mobile"). Controller routing chỉ quyết định method xử lý request **đã đến ứng dụng**.

### CORS không phải header routing

Khi browser gọi cross-origin API, có thể phát sinh CORS preflight OPTIONS. Một @GetMapping chỉ ràng buộc custom header không tự cấp quyền cho browser gửi header đó. Cần cấu hình CORS cho origin, methods, headers phù hợp; kể cả khi CORS cho phép, authentication/authorization vẫn phải hoạt động độc lập.

### HTTP cache và Vary

Nếu cùng URL có nhiều representation được chọn theo request header, một HTTP cache trung gian phải biết khi nào response thay đổi theo header đó. Header Vary có thể cần thiết, ví dụ:

~~~http
Vary: X-Channel
~~~

Đây là ví dụ về cache semantics, không phải header mà @GetMapping tự bảo đảm phát ra trong mọi trường hợp. Nếu dùng header để chọn tài liệu/representation nhưng không cấu hình cache đúng, client có thể nhận phiên bản đã lưu cho nhóm header khác.

Trong nhiều trường hợp, việc đặt biến thể có ý nghĩa lớn vào **path** hoặc **query** sẽ dễ quan sát và tương thích cache hơn, dù từng phương án vẫn cần thiết kế cache key và security đúng.

## 16. So sánh Spring MVC annotated routing với Spring WebFlux

Cả hai stack đều hỗ trợ:

~~~java
@GetMapping(
    path = "/api/items/{id}",
    params = "view=detail",
    headers = "X-Channel=mobile"
)
~~~

Nhưng bên trong khác:

| Thuộc tính | Spring MVC | Spring WebFlux |
|---|---|---|
| Web runtime | Servlet | Reactive HTTP stack |
| Front controller | DispatcherServlet | DispatcherHandler |
| Handler mapping tiêu biểu | RequestMappingHandlerMapping MVC | RequestMappingHandlerMapping WebFlux |
| Annotation route | @RequestMapping/@GetMapping | @RequestMapping/@GetMapping |
| Lấy path/query/header | @PathVariable/@RequestParam/@RequestHeader | Các annotation tương tự |
| Đọc/ghi JSON body | HttpMessageConverter | HttpMessageReader/Writer codecs |
| Controller return | DTO/ResponseEntity/async types | Mono/Flux/DTO/ResponseEntity |
| Functional routing | MVC.fn cũng có RouterFunction | WebFlux.fn RouterFunction |

Về mặt ý nghĩa, path/header/query vẫn là những phần của HTTP request. WebFlux không làm headers condition trở thành bảo mật, cũng không biến @RequestParam thành routing condition tự động.

**Lưu ý Boot:** Nếu dự án có cả spring-boot-starter-web và spring-boot-starter-webflux, Spring Boot thường chọn Servlet/Spring MVC làm server stack mặc định. Việc dùng WebClient không đồng nghĩa ứng dụng server đang ở WebFlux.

### WebFlux.fn và các request predicates

Ngoài annotation, WebFlux.fn có API RequestPredicate để phối hợp method, path, query và headers. Ví dụ một bean trong project **chỉ dùng starter-webflux**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
class FunctionalRouteConfig {

    @Bean
    RouterFunction<ServerResponse> demoRoute() {
        return RouterFunctions.route()
            .GET(
                "/fn/hello",
                RequestPredicates.queryParam("mode", "brief")
                    .and(RequestPredicates.headers(
                        h -> "yes".equals(h.getFirst("X-Debug")))),
                req -> ServerResponse.ok().bodyValue("hello")
            )
            .build();
    }
}
~~~

Đây là **lớp cấu hình bổ sung** trong một WebFlux application, không phải standalone application. Endpoint chỉ phù hợp khi GET /fn/hello?mode=brief và header X-Debug: yes. Không sử dụng cấu hình này để thay thế spring-boot-starter-web trong ví dụ Spring MVC phía trên; hai ví dụ minh họa hai stack khác nhau.

Trong functional routing, RequestPredicate.and kết hợp nhiều điều kiện; or cho phép một trong các điều kiện. API này là một cách viết điều kiện thay thế annotation, không phải hệ định tuyến mạng ở gateway.

## 17. Thiết kế API: lúc nào nên dùng path, query hay header?

### Trường hợp 1 — Lấy một resource

~~~http
GET /api/orders/123
~~~

Nên dùng path variable vì 123 định danh tài nguyên.

### Trường hợp 2 — Lọc và phân trang resource collection

~~~http
GET /api/orders?status=PAID&page=2&size=20
~~~

Thông thường một route GET /api/orders là đủ. Bind query bằng @RequestParam, validate giá trị và truy vấn dữ liệu. **Không cần tạo một controller method riêng cho mọi status hoặc page.**

### Trường hợp 3 — Có hai representation rõ ràng cùng URL

~~~http
GET /api/reports?format=summary
GET /api/reports?format=detail
~~~

Có thể chọn hai handler bằng params nếu cấu trúc xử lý thực sự khác biệt. Nếu chỉ khác một tùy chọn serialization nhẹ, một handler với @RequestParam có thể đơn giản hơn.

### Trường hợp 4 — API representation theo media type

~~~http
GET /api/reports HTTP/1.1
Accept: application/json
~~~

Nếu khác biệt chính là loại representation JSON/XML/text, dùng **produces** và cơ chế content negotiation thay vì tự tạo X-Format tùy tiện.

### Trường hợp 5 — Metadata protocol riêng

~~~http
GET /api/config HTTP/1.1
X-Channel: mobile
~~~

Header routing có thể phù hợp nếu contract API định nghĩa rõ và các proxy/cache được cấu hình nhất quán. Không dùng custom header để thay vai trò OAuth/JWT hoặc chính sách phân quyền.

### Trường hợp 6 — API versioning

Các cách thường gặp:

~~~text
/api/v1/orders/123                  (path version)
/api/orders?version=1               (query version)
X-API-Version: 1                    (custom header version)
Accept: application/vnd.shop.v1+json  (media type version)
~~~

Mỗi cách có trade-off về URL, khả năng cache, tooling, documentation, migration và gateway. Spring Boot 3.3 / Spring Framework 6.1 có thể thực hiện các mẫu này bằng @RequestMapping conditions, nhưng không nên mặc định các tính năng versioning mới trong Spring Framework 7 đã có ở Boot 3.3.

**Đừng thay đổi public API versioning strategy chỉ vì syntax annotation ngắn hơn.** Cần thống nhất ở gateway, docs, SDK và clients.

## 18. Đọc lỗi routing qua status HTTP

Một checklist có ích:

| Quan sát | Nơi cần kiểm tra |
|---|---|
| 404 | Không có path/handler phù hợp, custom header condition không match, hoặc route không được scan |
| 405 | Path có handler nhưng HTTP method không được hỗ trợ |
| 400 | Thiếu @RequestParam bắt buộc, convert parameter không được, hoặc request-params mapping mismatch trong MVC |
| 406 | Request Accept không tương thích với representation server có thể produce |
| 415 | Request Content-Type không phù hợp consumes |
| 401/403 | Authentication/authorization tại security filter hoặc method security |
| 500 | Lỗi ứng dụng hoặc ambiguous/runtime mapping, tùy nguyên nhân |

**Không đồng nhất 404 với sai path.** Một method GET cùng path nhưng chỉ match headers="X-Mode=web" có thể bị loại khi header không thỏa, khiến kết quả cuối cùng như không tìm thấy handler. Ngược lại, một method đúng path nhưng @RequestParam long id không convert được có thể trả 400.

### Quy trình debug từng bước

1. **HTTP method:** Client thực sự gọi GET, POST, PUT...? Có bị CORS preflight OPTIONS hoặc proxy biến đổi không?
2. **Path:** Có context path, base path, trailing slash, URL encoding hoặc rewrite từ gateway không?
3. **Route tồn tại:** Controller đã được component scan? Annotation @RestController hay @Controller có được cấu hình đúng?
4. **params:** Query key/value có chính xác không? Có repeated keys, encoding, defaultValue, required=true hay form parameters không?
5. **headers:** Header có đến server không? Tên/value có đúng, có proxy strip hay browser preflight không?
6. **Media types:** consumes và produces có phù hợp Content-Type và Accept không?
7. **Argument binding:** Sau khi route được chọn, parse int/long/UUID/enum có thành công không?
8. **Ambiguity:** Có hai method mapping trùng hoặc chồng lấn? Có startup error do duplicate mapping không?
9. **Security:** 401/403 phát sinh trước controller ở Spring Security hay tại method-level authorization?
10. **Quan sát có bằng chứng:** Bật log routing thích hợp và thêm MockMvc/WebTestClient tests cho request cụ thể.

Khi cần debug có thể bật tạm:

~~~properties
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
~~~

Tên logger trên áp dụng cho Spring MVC. Đối với WebFlux dùng logger thuộc org.springframework.web.reactive. TRACE/DEBUG có thể lộ metadata request trong log; không để bật liên tục ở production nếu không có chính sách bảo vệ dữ liệu.

## 19. Một số sai lầm rất phổ biến

### “@RequestParam làm Spring chọn handler theo query”

Sai. @RequestParam **bind giá trị** vào argument. Chỉ khi mapping có params condition thì giá trị parameter mới trực tiếp tham gia chọn handler.

### “@RequestHeader và headers là một”

Sai. @RequestHeader lấy giá trị trong controller method; headers condition được đánh giá trước để quyết định method có phù hợp không.

### “Path có chứa query string”

Sai. /api/items/7?view=summary vẫn có path /api/items/7. Query là phần riêng.

### “Viết hai @GetMapping cùng path thì Spring chọn theo thứ tự khai báo”

Sai. Hai mapping cần điều kiện đủ rõ và Spring có quy tắc so khớp/so sánh. Duplicate mapping có thể ngăn ứng dụng startup.

### “Vì X-Admin=true nên route đã được bảo vệ”

Sai. Client có thể giả mạo custom header; routing không phải authorization.

### “Thiếu query condition thì luôn trả 404”

Không chính xác. Spring MVC có xử lý request parameter mismatch riêng, có thể trả 400 trong trường hợp path/method phù hợp nhưng params condition không thỏa. Status cần xem kết quả routing thật và exception handling.

### “Header name cần đúng chữ hoa/thường”

Sai ở tầng HTTP field-name: X-Channel và x-channel về tên field không phân biệt case. **Giá trị** là một vấn đề khác.

### “CORS cho phép header thì client tự được phép gọi endpoint an toàn”

Sai. CORS chi phối việc browser cho phép cross-origin script đọc/gửi request theo chính sách; không thay authentication, firewall hoặc permission checking.

### “Tất cả client tự tạo query theo cùng encoding”

Không bảo đảm. Cần dùng URI builder hoặc thư viện HTTP đúng chuẩn để encode query, path segments và giá trị có ký tự đặc biệt. Không tự nối chuỗi các URL với input chưa encode.

### “Route trả 404 thì Spring Boot chắc chắn chưa chạy”

Không đúng. Server có thể khởi động bình thường nhưng handler không match method/path/headers/params. Hãy kiểm tra HTTP status, logs và các route khác trước khi kết luận server down.

## 20. Luyện tập với ma trận request

Giả sử bạn có ba mapping:

~~~java
@GetMapping(
    path = "/api/tasks",
    params = "mode=short",
    headers = "X-Client=web")
String shortWeb() { return "A"; }

@GetMapping(
    path = "/api/tasks",
    params = "mode=long",
    headers = "X-Client=web")
String longWeb() { return "B"; }

@GetMapping(
    path = "/api/tasks",
    params = "mode=short",
    headers = "X-Client=mobile")
String shortMobile() { return "C"; }
~~~

Đây là các method minh họa đặt trong REST controller.

| Request | Handler phù hợp theo các conditions |
|---|---|
| GET /api/tasks?mode=short, X-Client: web | A |
| GET /api/tasks?mode=long, X-Client: web | B |
| GET /api/tasks?mode=short, X-Client: mobile | C |
| GET /api/tasks?mode=long, X-Client: mobile | Không có handler trong bộ ví dụ này |
| GET /api/tasks?mode=short, thiếu X-Client | Không có handler trong bộ ví dụ này |
| POST /api/tasks?mode=short, X-Client: web | Không phù hợp HTTP method GET |

Bảng chỉ xác định **handler nào thỏa conditions trong bộ ví dụ**, không khẳng định toàn bộ HTTP status, vì một ứng dụng thực tế còn có handler khác, exception resolver và security filter.

Từ ma trận, nếu muốn thêm phiên bản mode=long, X-Client=mobile thì bạn phải tạo handler mới hoặc dùng một handler chung rồi xử lý mode/channel như dữ liệu bên trong.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Đối với /api/orders/15?include=items, phần nào là path và phần nào là query?

**Đáp án:** Path là /api/orders/15. Query parameter include có giá trị items. Nếu route /api/orders/{id}, @PathVariable lấy 15; @RequestParam có thể lấy include.

**Câu 2.** Hai handler cùng GET /api/orders, khác params="view=summary" và params="view=detail". GET /api/orders?view=detail sẽ vào đâu?

**Đáp án:** Handler có params="view=detail", nếu không có điều kiện khác ngăn lựa chọn.

**Câu 3.** GET /api/orders?view=summary đã khớp params, nhưng thiếu headers="X-Channel=mobile" ở mapping. Handler được gọi không?

**Đáp án:** Không, vì tất cả conditions áp dụng phải thỏa. Cần xem handler khác hoặc error resolver để xác định status.

**Câu 4.** Một controller dùng @GetMapping("/api/search") và @RequestParam(defaultValue="all") String q. GET /api/search?q=java có dùng route khác GET /api/search không?

**Đáp án:** Không. Cùng một route; giá trị q khác ở bước binding.

**Câu 5.** Có thể dùng @RequestHeader để đọc X-Trace-Id mà không thêm headers condition không?

**Đáp án:** Có. @RequestHeader chỉ bind giá trị sau khi route được chọn; dùng required=false hoặc defaultValue nếu header tùy chọn.

**Câu 6.** Dùng headers="X-User=alice" để chỉ cho phép Alice gọi API có an toàn không?

**Đáp án:** Không. Custom header có thể giả mạo. Phải xác thực identity và phân quyền ở lớp bảo mật.

**Câu 7.** Nếu muốn trả JSON hay XML theo Accept, nên dùng headers condition hay produces?

**Đáp án:** Thông thường dùng produces và content negotiation; writer/converter phải thực sự hỗ trợ representation tương ứng.

**Câu 8.** Hai pattern /api/products/latest và /api/products/{id} cùng match /api/products/latest. Pattern nào đặc hiệu hơn?

**Đáp án:** Literal /api/products/latest cụ thể hơn, thường được ưu tiên theo quy tắc pattern specificity.

**Câu 9.** Tại sao ?tag=java&tag=spring nên thường được xử lý ở một handler thay vì tách route theo từng tag?

**Đáp án:** Một request có nhiều giá trị cho cùng key; việc phân nhánh theo mỗi giá trị có thể chồng lấn. @RequestParam List<String> và một handler filter rõ ràng thường dễ thiết kế hơn.

**Câu 10.** Tại sao một header condition có thể làm việc trên curl nhưng fail trên browser khi gọi từ origin khác?

**Đáp án:** Browser có thể phải vượt qua CORS preflight, proxy có thể thay headers, hoặc JavaScript không được phép gửi request theo chính sách hiện tại. Kiểm tra CORS và request thực sự nhận bởi server.

## 22. Checklist áp dụng

- [ ] Mỗi endpoint có HTTP method và path rõ ràng.
- [ ] Phân biệt route selection với việc bind @PathVariable/@RequestHeader/@RequestParam.
- [ ] Dùng path cho resource identity và cấu trúc API.
- [ ] Dùng query cho filter, sort, pagination và tùy chọn tìm kiếm.
- [ ] Chỉ dùng headers condition khi metadata thực sự là một phần của contract routing.
- [ ] Không dùng custom header/query để thay authentication hoặc authorization.
- [ ] Đối với JSON/XML/text, xem consumes/produces và content negotiation trước khi thêm custom header.
- [ ] Không thiết kế route có các conditions chồng lấn khó xác định.
- [ ] Kiểm thử cả request thành công và request không thỏa path/header/query conditions.
- [ ] Cân nhắc URL encoding, repeated parameters, header normalization và reverse proxy.
- [ ] Không ghi thông tin nhạy cảm vào URL query một cách không cần thiết.
- [ ] Có logging/test để phân biệt lỗi route, binding, media type, security và nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework — Mapping Requests trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework — Mapping Requests trong Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html)
- [Spring Framework — RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Framework — RequestHeader](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html)
- [Spring Framework — WebFlux Functional Endpoints và RequestPredicates](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html)

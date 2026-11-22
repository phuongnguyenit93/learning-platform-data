# Điều kiện ánh xạ theo HTTP method, params, headers, consumes và produces trong Spring MVC

## 1. Mục tiêu: một đường dẫn chưa đủ để xác định controller method

Trong Spring Web MVC, `@RequestMapping` và các annotation rút gọn như `@GetMapping`, `@PostMapping` không chỉ chọn endpoint theo URI. Spring có thể yêu cầu **đồng thời** đúng HTTP method, request parameters, headers, kiểu nội dung request (`consumes`) và kiểu nội dung mà client chấp nhận (`produces`).

Giả sử ứng dụng nhận:

~~~http
POST /api/items?source=mobile HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json
X-Client: mobile

{"name":"Notebook"}
~~~

Các phần mang ý nghĩa riêng:

- `POST`: **HTTP method**; mô tả thao tác mà client muốn thực hiện.
- `/api/items`: **path** của tài nguyên/endpoint.
- `source=mobile`: **request parameter** dùng để lọc mapping bằng `params` nếu hợp đồng endpoint yêu cầu.
- `X-Client: mobile`: **header** dùng để lọc mapping bằng `headers` nếu được khai báo.
- `Content-Type: application/json`: kiểu representation **client gửi lên**; liên quan `consumes`.
- `Accept: application/json`: kiểu representation **client muốn server trả về**; liên quan `produces`.
- JSON body: dữ liệu thực tế được `@RequestBody`/message converter đọc **sau** khi chọn được handler phù hợp. Nội dung body **không** phải điều kiện `params` và không được so khớp bằng `consumes` theo từng thuộc tính JSON.

**Mục tiêu bài học:** nhìn vào một HTTP request và dự đoán controller method nào sẽ được chọn, giải thích vì sao request bị từ chối (ví dụ 405/415/406/400), và viết mapping rõ ràng, tránh trùng/khó hiểu. Bài tập trung vào **Spring MVC annotated controllers**, không chuyển sang chi tiết xây dựng router Spring WebFlux.

## 2. Bảng tổng quan năm nhóm điều kiện

| Annotation attribute | Đọc từ request | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| `method` / `@GetMapping` ... | HTTP method | `GET`, `POST` | Loại thao tác HTTP có thể vào endpoint |
| `params` | Request parameters (thường query hoặc form data) | `mode=full`, `debug`, `!debug` | Chỉ chọn mapping khi điều kiện tham số thỏa |
| `headers` | HTTP headers | `X-Client=mobile`, `X-Tenant` | Chỉ chọn mapping khi điều kiện header thỏa |
| `consumes` | `Content-Type` của request | `application/json` | Endpoint có chấp nhận media type của body đến không? |
| `produces` | `Accept` của request | `application/json`, `text/plain` | Endpoint có tạo được representation client chấp nhận không? |

Ví dụ một mapping có nhiều điều kiện:

~~~java
@PostMapping(
    path = "/items",
    params = "source=mobile",
    headers = "X-Client=mobile",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Item create(@RequestBody CreateItemRequest input) {
    // ... xử lý ...
}
~~~

Đoạn minh họa cần `Item`, `CreateItemRequest`, biến thể controller và import; ví dụ **chạy độc lập đầy đủ** nằm ở phần 9.

Một request phải đáp ứng **tất cả các nhóm điều kiện đã khai báo**. Nếu `POST`, URI và `Content-Type` phù hợp nhưng thiếu `source=mobile`, mapping này vẫn không phù hợp. Spring có thể tìm mapping khác, hoặc trả lỗi nếu không có lựa chọn hợp lệ.

### Phân biệt phép AND và OR

- Các **nhóm điều kiện khác loại** trên cùng mapping được kết hợp như phép **AND**.
- Một mảng `params = {"a=1","b=2"}` đòi hỏi **cả hai** điều kiện.
- Một mảng `headers = {"X-Client=mobile","X-Feature"}` cũng đòi hỏi **cả hai**.
- Nhiều giá trị media trong `consumes = {"application/json","text/plain"}` thường là **các lựa chọn thay thế** trong cùng nhóm (OR). `produces` tương tự.
- Nhiều HTTP method trong `@RequestMapping(method = {GET, POST})` là **các lựa chọn thay thế**. Tuy vậy, thông thường viết hai method chuyên trách sẽ dễ đọc và đúng ngữ nghĩa HTTP hơn.
- Nhiều path trong mảng mapping cũng là các lựa chọn URI; không có nghĩa phải khớp đồng thời tất cả path.

Spring biểu diễn tập điều kiện dưới dạng `RequestMappingInfo`, rồi dùng các `RequestCondition` tương ứng để kiểm tra request và so độ cụ thể.

## 3. Chọn theo HTTP method: GET, POST, PUT, PATCH và DELETE

Có thể khai báo tổng quát:

~~~java
@RequestMapping(path = "/items", method = RequestMethod.GET)
public List<Item> list() { ... }
~~~

Hoặc dùng annotation rút gọn, dễ thấy mục đích hơn:

~~~java
@GetMapping("/items")
public List<Item> list() { ... }

@PostMapping("/items")
public Item create(@RequestBody CreateItemRequest input) { ... }
~~~

Hai snippet trên **chỉ minh họa cú pháp**; phần thân và class hỗ trợ được lược bỏ. Chúng không thể đặt chung với một `@GetMapping("/items")` khác trùng y hệt mà không có điều kiện phân biệt.

| Annotation | Tương đương về mapping method | Ngữ nghĩa HTTP điển hình |
| --- | --- | --- |
| `@GetMapping` | `RequestMethod.GET` | Lấy representation; safe và idempotent theo HTTP |
| `@PostMapping` | `RequestMethod.POST` | Gửi dữ liệu để xử lý/tạo tài nguyên; không mặc định idempotent |
| `@PutMapping` | `RequestMethod.PUT` | Tạo/thay thế trạng thái đích theo hợp đồng; idempotent |
| `@PatchMapping` | `RequestMethod.PATCH` | Cập nhật từng phần; không mặc định idempotent |
| `@DeleteMapping` | `RequestMethod.DELETE` | Yêu cầu xóa; idempotent về hiệu ứng dự định |

**Điểm dễ bỏ sót:** `@RequestMapping("/items")` ở **method level** mà **không khai báo `method`** mặc định không giới hạn HTTP method. Đừng dùng để thay cho `@GetMapping` nếu endpoint chỉ được phép đọc.

### Khi method không hợp lệ: 405

Ví dụ chỉ có `@GetMapping("/api/items/7")` nhưng client gửi `POST /api/items/7`. Nếu path phù hợp mà phương thức HTTP không được hỗ trợ, Spring MVC thường phản hồi **405 Method Not Allowed** và có thể cung cấp header `Allow`. Đó là khác biệt với **404 Not Found** khi không có mapping path phù hợp.

**HEAD và OPTIONS:** `@GetMapping` hỗ trợ HEAD theo cơ chế MVC/Servlet trong các trường hợp thông thường, không cần viết một method riêng chỉ để bỏ body. Spring MVC cũng có xử lý OPTIONS mặc định dựa vào những HTTP method được mapping. Vì vậy không nên khẳng định rằng `@GetMapping` chỉ có thể nhận GET ở mọi trường hợp bất kể framework hỗ trợ HEAD.

## 4. Điều kiện params: hiện diện, vắng mặt hoặc giá trị cụ thể

`params` kiểm tra **request parameter** để lọc mapping. Ví dụ:

~~~java
@GetMapping(path = "/search", params = "mode=summary")
public String summary() { return "summary"; }

@GetMapping(path = "/search", params = "mode=full")
public String full() { return "full"; }
~~~

Khi gửi:

~~~http
GET /search?mode=full HTTP/1.1
Host: localhost:8080
~~~

chỉ method `full()` phù hợp với điều kiện ở ví dụ.

Các biểu thức thông dụng:

| Biểu thức | Ý nghĩa | Ví dụ request khớp |
| --- | --- | --- |
| `params = "mode"` | Có parameter tên `mode` | `?mode=full` hoặc `?mode=` |
| `params = "!mode"` | Không có parameter `mode` | `/search` |
| `params = "mode=full"` | Giá trị bằng `full` | `?mode=full` |
| `params = "mode!=full"` | Không có parameter hoặc giá trị khác `full` theo ngữ nghĩa điều kiện của Spring | `/search?mode=summary` |
| `params = {"mode=full", "page=1"}` | Cả hai cùng thỏa | `?mode=full&page=1` |

Nếu chỉ muốn chặn tham số không cho dùng, có thể dùng `!mode`; nếu muốn bắt buộc tham số tồn tại, dùng `mode`. Không nên dùng `mode!=full` như một cách bắt buộc parameter tồn tại và có giá trị khác `full`: biểu thức phủ định có thể cũng khớp khi tham số vắng mặt.

### params khác @RequestParam thế nào?

~~~java
@GetMapping(path = "/reports", params = "format=csv")
public String report(@RequestParam(defaultValue = "1") int page) {
    return "page=" + page;
}
~~~

- `params="format=csv"`: **điều kiện chọn controller method**; nếu request không có `format=csv`, method này không phải ứng viên.
- `@RequestParam int page`: **giải đối số cho method đã chọn**; ở đây `page` mặc định là 1 nếu client không gửi.
- Có thể dùng `@RequestParam("format") String format` để lấy giá trị parameter vào method body, nhưng nó không tự biến thành điều kiện chọn mapping kiểu `params="format=csv"`.

`params` có thể xét request parameters bao gồm những parameter được Servlet API cung cấp từ form URL-encoded tùy request. Dữ liệu JSON nằm trong `@RequestBody` **không** trở thành một tập request parameters chỉ vì có các thuộc tính giống tên.

### Thiếu điều kiện params trả status nào?

Nếu path và HTTP method khớp với mapping nhưng tất cả ứng viên đều bị loại **chỉ vì điều kiện params**, Spring MVC thường trả **400 Bad Request** qua cơ chế báo unsatisfied parameters. Tuy nhiên, nên kiểm thử chính xác bằng `MockMvc` hoặc integration test vì exception handler tùy biến và các điều kiện khác có thể làm thay đổi status.

## 5. Điều kiện headers: quyết định theo metadata HTTP

`headers` dùng biểu thức gần giống `params`, nhưng kiểm tra HTTP headers.

~~~java
@GetMapping(path = "/clients", headers = "X-Client=mobile")
public String mobile() { return "mobile"; }

@GetMapping(path = "/clients", headers = "X-Client=web")
public String web() { return "web"; }
~~~

Request:

~~~http
GET /clients HTTP/1.1
Host: localhost:8080
X-Client: mobile
~~~

sẽ phù hợp với method `mobile()`. Điều kiện có thể viết:

- `headers = "X-Client"`: có header tên `X-Client`.
- `headers = "!X-Client"`: header không xuất hiện.
- `headers = "X-Client=mobile"`: header có giá trị mong muốn.
- `headers = "X-Client!=mobile"`: phủ định giá trị.
- `headers = {"X-Client=mobile", "X-Feature"}`: hai điều kiện phải thỏa.

Tên header HTTP **không phân biệt hoa/thường**; giá trị header cần xét theo semantics cụ thể của header và cách matcher xử lý. Vì vậy không nên nhầm `X-Client` và `x-client` là hai header khác nhau.

**Không dùng `headers` để thay cho `consumes`/`produces`.** Spring có thể hỗ trợ biểu thức dựa trên `Content-Type`/`Accept` ở `headers`, nhưng các trường đó có cú pháp media type, wildcard và quality negotiation; sử dụng `consumes`/`produces` thể hiện đúng ý định và có logic so khớp chuyên biệt.

### Header matching không tự chứng minh quyền truy cập

Một client tự gửi `X-Client: mobile` có thể giả mạo giá trị ấy. Điều kiện mapping không thay thế authentication, authorization, signature verification hay tenant isolation. Nếu header quyết định đường xử lý đặc quyền, cần kiểm soát security ở lớp phù hợp, không tin một chuỗi client cung cấp.

## 6. consumes: server nhận được Content-Type nào?

`consumes` là điều kiện về **media type mà handler có thể tiêu thụ từ request body**, thường dựa vào `Content-Type` request.

~~~java
@PostMapping(
    path = "/items",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public void create(@RequestBody ItemInput input) {
    // ...
}
~~~

Request phù hợp:

~~~http
POST /items HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"name":"Bút"}
~~~

Request không phù hợp với điều kiện trên nếu gửi:

~~~http
POST /items HTTP/1.1
Host: localhost:8080
Content-Type: text/plain

Bút
~~~

Nếu đúng path và method nhưng media type request không được mapping chấp nhận, Spring MVC thường phản hồi **415 Unsupported Media Type**. Sau bước chọn mapping, framework còn phải có `HttpMessageConverter` phù hợp để đọc body thành Java type; đủ điều kiện `consumes` **không bảo đảm** deserialize thành công.

### Media type và wildcard

`consumes` có thể dùng:

~~~java
consumes = "application/json"
consumes = {"application/json", "application/xml"}
consumes = "application/*"
consumes = "!text/plain"
~~~

- Một danh sách media type là những lựa chọn được phép; không đòi hỏi body vừa là JSON vừa là XML.
- Wildcard media type chỉ nên dùng khi các converter và hợp đồng dữ liệu thực sự hỗ trợ.
- Negation thể hiện media type bị loại trừ nhưng **không tự tạo** khả năng đọc mọi media còn lại.
- `application/json;charset=UTF-8` có thể tương thích với điều kiện `application/json` theo quy tắc media type; không dùng so sánh chuỗi thô để tự viết lại logic này.
- Trong trường hợp request không có body hoặc không khai báo Content-Type, hành vi matching còn phụ thuộc ngữ cảnh; đừng mặc định `consumes="application/json"` luôn hoạt động giống nhau cho GET không body và POST có body. Thông thường chỉ dùng consumes khi endpoint thực sự yêu cầu request representation.

### Mapping match khác khả năng đọc dữ liệu

Ngay cả khi `Content-Type: application/json` phù hợp, JSON lỗi cú pháp như `{"name":` vẫn có thể dẫn tới **400 Bad Request** do `HttpMessageNotReadableException`. Đây là lỗi **đọc body**, khác với **415** vì media type không được hỗ trợ.

Nếu một endpoint chỉ nhận JSON, nên khai báo `consumes = MediaType.APPLICATION_JSON_VALUE` và kiểu `@RequestBody` rõ ràng. Đừng parse JSON từ chuỗi tùy tiện nếu framework đã có converter chuẩn.

## 7. produces: client chấp nhận response ở định dạng nào?

`produces` là điều kiện về **media type handler có thể trả về**, thường được chọn dựa trên `Accept` của client.

~~~java
@GetMapping(
    path = "/items/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Item get(@PathVariable long id) {
    return new Item(id, "Bút");
}
~~~

Client có thể gửi:

~~~http
GET /items/7 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Mapping JSON phù hợp. Nếu client gửi:

~~~http
GET /items/7 HTTP/1.1
Host: localhost:8080
Accept: application/pdf
~~~

mà không có mapping/converter tạo representation phù hợp, Spring MVC thường phản hồi **406 Not Acceptable**. Đây khác với **415**, vì 406 liên quan **response mong muốn**, còn 415 liên quan **request body gửi lên**.

### Accept và Content-Type đặt ở hai phía

| Header | Ai gửi? | Được dùng làm gì? | Mapping attribute |
| --- | --- | --- | --- |
| Request `Content-Type` | Client | Thông báo dạng dữ liệu body **gửi vào server** | `consumes` |
| Request `Accept` | Client | Thông báo các dạng response **client chấp nhận** | `produces` |
| Response `Content-Type` | Server | Thông báo dạng body **server đã gửi về** | Kết quả content negotiation/serialization |

Trong phản hồi JSON bình thường, server đặt `Content-Type: application/json`. Không dùng **response Content-Type** như một điều kiện đầu vào để xác định method vì nó chưa tồn tại tại thời điểm routing.

### Quality và wildcard

Header:

~~~http
Accept: application/json;q=0.9, text/plain;q=0.5
~~~

có thể nêu mức ưu tiên các media type; `q` là quality value. `Accept: */*` cho phép nhiều định dạng phù hợp, nhưng nếu có nhiều mapping cùng đường dẫn và method phân biệt **chỉ bằng `produces`**, cần kiểm thử lựa chọn/tie-breaking cho request Accept rộng. Với API sản phẩm, có thể tránh ambiguity bằng hợp đồng Accept tường minh, mapping cụ thể và test.

Dù mapping chọn được `produces="application/xml"`, server vẫn cần converter để encode object ra XML. `produces` không tự cài JAXB/Jackson XML; không hứa output XML chỉ bằng annotation khi thiếu converter.

## 8. Spring chọn mapping khi nhiều ứng viên cùng path

Về mặt ý tưởng, trong Spring MVC:

~~~text
HTTP request
    |
    v
DispatcherServlet
    |
    v
RequestMappingHandlerMapping
    |
    +-- match path pattern?
    +-- match HTTP method?
    +-- match request params?
    +-- match request headers?
    +-- match consumes / Content-Type?
    +-- match produces / Accept?
    |
    +-- Không còn ứng viên => xử lý không khớp / báo lỗi HTTP phù hợp
    |
    +-- Một ứng viên => trả HandlerMethod
    |
    +-- Nhiều ứng viên => so mức độ cụ thể / RequestMappingInfo
    |                      nếu không thể phân định => ambiguity
    v
RequestMappingHandlerAdapter
    |
    +-- resolve arguments, invoke controller, handle return value
    v
HTTP response
~~~

Đây là sơ đồ học thuật đơn giản hóa, không phải mô tả thứ tự kiểm tra tối ưu hóa trong từng phiên bản source code. Điều quan trọng là **tất cả điều kiện đã khai báo đều phải được đáp ứng** và các mapping cạnh tranh được so độ cụ thể, chứ không chọn bừa method nào khai báo trước.

### Phân biệt xung đột lúc startup và ambiguity lúc request

Hai mapping có cấu hình tương đương hoàn toàn có thể gây lỗi đăng ký **ambiguous mapping** khi ứng dụng khởi động:

~~~java
@GetMapping("/same")
public String first() { return "A"; }

@GetMapping("/same")
public String second() { return "B"; }
~~~

Đây là ví dụ **không hợp lệ để chạy đồng thời** trong cùng controller/application vì cùng path, method và điều kiện mapping. Không khắc phục bằng cách đổi tên Java method: mapping xét request conditions, không dựa vào tên method.

Hai mapping không hoàn toàn trùng điều kiện có thể đều là ứng viên cho một request cụ thể; Spring so độ ưu tiên. Nếu chúng không thể phân biệt đủ rõ, có thể gặp ambiguity tại runtime. Hãy đặt điều kiện loại trừ nhau hoặc phân đường dẫn/HTTP method rõ ràng và viết test cho các request chồng lấp.

### Điều kiện ở class và method

~~~java
@RestController
@RequestMapping(path = "/api")
class ExampleController {

    @GetMapping(path = "/items", produces = "application/json")
    List<Item> items() { ... }
}
~~~

Path cuối cùng là `/api/items`. Thường dùng class-level `@RequestMapping` cho base path, method-level shortcuts cho method/path chính xác. Với `consumes` và `produces`, khai báo ở method sẽ **ghi đè** điều kiện tương ứng ở class thay vì chỉ thêm điều kiện vào danh sách class-level; tránh nghĩ chúng luôn được cộng dồn. Với các condition khác, hãy tham khảo Spring API và kiểm thử mapping kết hợp thay vì suy diễn tùy tiện.

Không xếp hai annotation mapping khác nhau trên cùng một method, ví dụ `@GetMapping` và `@PostMapping` song song, để hy vọng chúng hợp thành OR: Spring cảnh báo và chỉ dùng mapping đầu tiên được phát hiện. Nếu thực sự cần nhiều HTTP method cùng một method, hãy dùng một `@RequestMapping(method = {RequestMethod.GET, RequestMethod.POST})` rồi xử lý nghiệp vụ cẩn thận.

## 9. Ví dụ Spring Boot MVC hoàn chỉnh cho cả năm nhóm điều kiện

Ví dụ sau độc lập, dùng Java 17+, Spring Boot 3.3.5 (Spring Framework 6.1.x) để các API minh họa ổn định. Một controller chứa các endpoint có điều kiện độc lập, tránh xung đột mapping. Không có database hoặc thư viện ngoài Web starter.

### 9.1 Cấu trúc và Gradle

~~~text
mapping-conditions-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/mapping/MappingConditionsApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'mapping-conditions-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
}
~~~

Dùng JDK 17+ và Gradle tương thích với Spring Boot plugin. Nếu project có Gradle Wrapper thì chạy wrapper; nếu chưa có, cần Gradle đã cài để chạy `gradle bootRun` hoặc tạo wrapper. Không cần bắt buộc dùng WebFlux để triển khai các mapping này.

### 9.2 Java source

Tạo `src/main/java/example/mapping/MappingConditionsApplication.java`:

~~~java
package example.mapping;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MappingConditionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(MappingConditionsApplication.class, args);
    }

    public record Item(long id, String name) {}
    public record NewItem(String name) {}

    @RestController
    @RequestMapping("/api")
    static class DemoController {

        // HTTP method + path + output JSON.
        @GetMapping(
                path = "/items/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public Item byId(@PathVariable long id) {
            return new Item(id, "Bút");
        }

        // Hai GET cùng path, chỉ một mode tương ứng được chọn.
        @GetMapping(
                path = "/find",
                params = "mode=summary",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String summary() {
            return "summary";
        }

        @GetMapping(
                path = "/find",
                params = "mode=full",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String full() {
            return "full";
        }

        // Phân biệt tham số có mặt và vắng mặt.
        @GetMapping(
                path = "/flag",
                params = "debug",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String debugOn() {
            return "debug:on";
        }

        @GetMapping(
                path = "/flag",
                params = "!debug",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String debugOff() {
            return "debug:off";
        }

        // Hai GET cùng path, nhưng yêu cầu header khác nhau.
        @GetMapping(
                path = "/clients",
                headers = "X-Client=mobile",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String mobile() {
            return "client:mobile";
        }

        @GetMapping(
                path = "/clients",
                headers = "X-Client=web",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String web() {
            return "client:web";
        }

        // Cùng POST /items nhưng tiêu thụ và trả về media khác.
        @PostMapping(
                path = "/items",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Item> createJson(@RequestBody NewItem input) {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(new Item(101L, input.name()));
        }

        @PostMapping(
                path = "/items",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE)
        public ResponseEntity<String> createText(@RequestBody String input) {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body("created: " + input);
        }

        // Cùng GET /format, phân biệt theo Accept header.
        @GetMapping(
                path = "/format",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> json() {
            return Map.of("view", "json");
        }

        @GetMapping(
                path = "/format",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String plain() {
            return "view:text";
        }
    }
}
~~~

Ví dụ có năm kiểu điều kiện chính: HTTP method (`GET`/`POST`), `params`, `headers`, `consumes` và `produces`. Với annotation `@RestController`, `String` được ghi thành response body, không được hiểu là tên HTML view.

**Lưu ý về `@PathVariable`:** Spring Boot Gradle plugin cung cấp compiler metadata phù hợp trong setup thông thường. Nếu công cụ build riêng không giữ tên parameter để reflection đọc được, hãy ghi tường minh `@PathVariable("id")` và các annotation parameter khác để tránh phụ thuộc compiler flag `-parameters`.

### 9.3 Chạy ứng dụng và kiểm tra

Với wrapper có sẵn:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Không có wrapper thì dùng `gradle bootRun` sau khi cài Gradle tương thích. Ví dụ giả định cổng mặc định là `8080` và không có ứng dụng khác chiếm cổng.

**A. GET JSON theo method, path và produces:**

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/items/7
~~~

Response mong đợi: `200 OK`, `Content-Type` là JSON, body:

~~~json
{"id":7,"name":"Bút"}
~~~

**B. params chọn summary hoặc full:**

~~~bash
curl -i "http://localhost:8080/api/find?mode=summary"
curl -i "http://localhost:8080/api/find?mode=full"
~~~

Hai body lần lượt:

~~~text
summary
full
~~~

Nếu gọi `/api/find?mode=other` hoặc không truyền `mode`, cả hai method trên không khớp điều kiện giá trị. Trong cấu hình chuẩn, trường hợp chỉ sai params thường nhận 400; test thực tế cần kiểm soát exception handler nếu ứng dụng có tùy biến.

**C. params có mặt và vắng mặt:**

~~~bash
curl -i "http://localhost:8080/api/flag?debug"
curl -i "http://localhost:8080/api/flag"
~~~

Các body:

~~~text
debug:on
debug:off
~~~

Điều kiện `params="debug"` chỉ đòi hiện diện; không đồng nghĩa `debug=true`. `?debug=false` vẫn có parameter tên `debug` và phù hợp với method `debugOn` trong demo.

**D. headers chọn client:**

~~~bash
curl -i -H "X-Client: mobile" http://localhost:8080/api/clients
curl -i -H "X-Client: web" http://localhost:8080/api/clients
~~~

Body lần lượt:

~~~text
client:mobile
client:web
~~~

Bỏ header hoặc gửi `X-Client: other` sẽ không thỏa cả hai mapping này; không khẳng định status cố định nếu ứng dụng thêm những mapping/header rules khác.

**E. POST cùng URI, khác Content-Type và Accept:**

~~~bash
curl -i -X POST "http://localhost:8080/api/items" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Notebook"}'
~~~

Status mong đợi: `201 Created`; body:

~~~json
{"id":101,"name":"Notebook"}
~~~

Đổi thành text:

~~~bash
curl -i -X POST "http://localhost:8080/api/items" \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data-binary "Pencil"
~~~

Status mong đợi: `201 Created`; body:

~~~text
created: Pencil
~~~

Sự khác biệt đến từ **hai ánh xạ `consumes`**, mỗi mapping chỉ nhận kiểu request tương ứng; đồng thời `produces` của mapping chọn ra kiểu response.

**F. produces chọn format theo Accept:**

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/format
curl -i -H "Accept: text/plain" http://localhost:8080/api/format
~~~

Body tương ứng:

~~~json
{"view":"json"}
~~~

~~~text
view:text
~~~

Đây là hai method có cùng GET/path nhưng media type phân biệt được khi client gửi Accept cụ thể. Không sử dụng kết quả cho request không gửi `Accept` để khẳng định framework luôn ưu tiên một method.

**G. Sai Content-Type, Accept hoặc HTTP method:**

~~~bash
curl -i -X POST "http://localhost:8080/api/items" \
  -H "Content-Type: application/xml" \
  -H "Accept: application/json" \
  -d '<item><name>Notebook</name></item>'

curl -i -H "Accept: application/pdf" http://localhost:8080/api/format

curl -i -X DELETE http://localhost:8080/api/items/7
~~~

Trong dự án demo và không tùy biến error handling, các status kỳ vọng theo từng trường hợp là **415 Unsupported Media Type**, **406 Not Acceptable** và **405 Method Not Allowed**. Body lỗi và danh sách header cụ thể có thể khác theo cấu hình Spring Boot. Các lệnh là ví dụ kiểm thử HTTP, không phải stdout của chương trình Java.

### 9.4 Bảng test case ngắn của demo

| Request | Mapping kỳ vọng | Kết quả |
| --- | --- | --- |
| `GET /api/items/7` + `Accept: application/json` | `byId` | JSON `{"id":7,"name":"Bút"}` |
| `GET /api/find?mode=full` | `full` | `full` |
| `GET /api/find?mode=summary` | `summary` | `summary` |
| `GET /api/flag` | `debugOff` | `debug:off` |
| `GET /api/flag?debug` | `debugOn` | `debug:on` |
| `GET /api/clients` + `X-Client: mobile` | `mobile` | `client:mobile` |
| `POST /api/items` + JSON Content-Type/Accept | `createJson` | 201 + JSON |
| `POST /api/items` + text/plain Content-Type/Accept | `createText` | 201 + text |
| `GET /api/format` + `Accept: text/plain` | `plain` | `view:text` |
| `GET /api/format` + `Accept: application/json` | `json` | JSON |
| `GET /api/format` + `Accept: application/pdf` | Không có produces phù hợp | 406 thường gặp |
| `POST /api/items` + `Content-Type: application/xml` | Không có consumes phù hợp | 415 thường gặp |
| `DELETE /api/items/7` | Không có DELETE mapping trên path | 405 thường gặp |

## 10. Những lỗi định tuyến thường gặp và cách chẩn đoán

| HTTP status / hiện tượng | Chẩn đoán đầu tiên | Hướng xử lý |
| --- | --- | --- |
| **404 Not Found** | Không có path/handler phù hợp; có thể do cấu hình context path/servlet mapping | Xem URL thật, controller registration, logs/mappings |
| **405 Method Not Allowed** | Path có mapping nhưng không cho HTTP method request | So `GET/POST/PUT/PATCH/DELETE` và `Allow` |
| **400 Bad Request** khi `params` không thỏa | Có path/method phù hợp nhưng tham số điều kiện thiếu/sai | So query/form parameters với `params` |
| **400 Bad Request** sau khi chọn handler | Sai kiểu tham số, JSON malformed, validation thất bại | So `@RequestParam`, `@PathVariable`, `@RequestBody`, converter/validator |
| **415 Unsupported Media Type** | Content-Type request không phù hợp consumes/converter | Kiểm tra đúng request `Content-Type` và codec |
| **406 Not Acceptable** | `Accept` không phù hợp produces/không tạo được representation | Kiểm tra `Accept`, `produces`, converter ghi body |
| **500/ambiguous mapping** khi startup | Trùng điều kiện đăng ký giữa nhiều method | Đổi mapping để phân biệt, không chỉ đổi tên Java method |
| **Ambiguous handler methods** lúc request | Nhiều candidate ngang ưu tiên cho request cụ thể | Thiết kế điều kiện loại trừ, thêm test case chồng lấp |
| Controller method vào đúng nhưng body sai | Mapping đã xong; có thể lỗi return-value handler/serialization | Xem `@RestController`, `ResponseEntity`, converter |
| Có header nhưng vẫn không match | Sai giá trị, whitespace, proxy làm mất header, policy gateway | Log header một cách an toàn, trace qua proxy |

**Không dùng HTTP status làm chứng cứ duy nhất**: `@ControllerAdvice`, filter/security, reverse proxy hay handler mapping tùy biến có thể thay đổi phản hồi. Cần xác định request thật mà ứng dụng nhận sau proxy và danh sách mappings thực tế.

### Log có ích khi debug

Với ứng dụng phát triển, có thể bật log mapping ở mức phù hợp trong `application.properties`:

~~~properties
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
~~~

Bật tracing chi tiết chỉ khi cần; đừng bật lâu dài cho production vì lượng log, hiệu năng và nguy cơ ghi dữ liệu nhạy cảm. Nếu có Spring Boot Actuator, endpoint `/actuator/mappings` có thể giúp xem ánh xạ được đăng ký **khi đã cài và cấu hình Actuator**, không mặc định công khai trong ứng dụng demo.

## 11. Phân biệt ranh giới của điều kiện mapping với argument resolution

Nhìn hai method:

~~~java
@GetMapping(path = "/orders", params = "status=PAID")
public String paidOrders(@RequestParam String status) { ... }

@GetMapping(path = "/orders", params = "status=PENDING")
public String pendingOrders(@RequestParam String status) { ... }
~~~

`params="status=PAID"`/`"status=PENDING"` quyết định **method nào được chọn**. Sau đó `@RequestParam String status` mới tạo đối số cho method tương ứng.

Một số đối chiếu quan trọng:

- `@RequestMapping.params` không phải `@RequestParam`.
- `@RequestMapping.headers` không phải `@RequestHeader`.
- `@RequestMapping.consumes` không phải `@RequestBody`.
- `@RequestMapping.produces` không phải `@ResponseBody`.
- `consumes`/`produces` ảnh hưởng **ứng viên mapping**; `HttpMessageConverter` và return-value handler quyết định Java body ↔ bytes thực sự.
- `headers = "X-Client=mobile"` chỉ lọc request; muốn dùng nội dung header bên trong method, vẫn phải nhận qua `@RequestHeader("X-Client")` hoặc đọc request context.

**Ví dụ quan trọng:** POST mapping có `consumes="application/json"` nhưng method nhận `@RequestBody String` vẫn có thể hoạt động theo các converter hiện có; ngược lại `@RequestBody MyDto` cần converter phù hợp. Không suy ra Java target type chỉ từ consumes.

## 12. Những ngộ nhận dễ làm API sai hợp đồng

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Cùng path chỉ được có một method controller” | Có thể có nhiều mapping cùng path khi HTTP method/params/headers/media conditions phân biệt |
| “`@RequestMapping` mặc định là GET” | Method-level không khai báo method có thể match nhiều HTTP method |
| “`params` đọc từ JSON body” | Kiểm tra request parameters, không đọc từng JSON property |
| “`@RequestParam` tự phân nhánh mapping” | Argument resolver hoạt động sau bước chọn handler |
| “`headers` tự xác thực người dùng” | Header do client gửi có thể giả mạo; authentication/authorization nằm lớp khác |
| “`consumes` đọc Accept” | `consumes` dựa vào request Content-Type |
| “`produces` đọc Content-Type request” | `produces` dựa vào request Accept/response representation |
| “Khớp consumes là parse body chắc chắn thành công” | Converter vẫn có thể thiếu hoặc dữ liệu sai cú pháp |
| “Khai báo produces XML thì chắc chắn xuất XML” | Cần XML message converter hỗ trợ Java type |
| “Mọi media type trong mảng phải đúng đồng thời” | Trong consumes/produces, media alternatives là OR |
| “Một mảng params có thể chỉ cần một giá trị đúng” | Các expression trong params array là AND |
| “Trùng mapping sẽ chọn method viết trước” | Có thể gây lỗi ambiguous mapping; phải sửa điều kiện |
| “`Accept: */*` luôn chọn JSON” | Phụ thuộc candidates và content negotiation; test hợp đồng rõ ràng |
| “415 và 406 giống nhau” | 415 về request media; 406 về response acceptable media |
| “GET mapping không bao giờ xử lý HEAD” | Spring MVC hỗ trợ HEAD cho GET mapping trong cấu hình thông thường |
| “Method-level produces luôn nối thêm class-level produces” | Method-level produces/consumes ghi đè điều kiện tương ứng ở class |

## 13. Bài tập tự kiểm tra điều kiện

**Bài 1.** Có:

~~~java
@GetMapping(path = "/search",
            params = {"type=book", "page=1"},
            headers = "X-Client=mobile",
            produces = "application/json")
public Object find() { ... }
~~~

Request nào phù hợp?

1. `GET /search?type=book&page=1` với `X-Client: mobile`, `Accept: application/json`.
2. `GET /search?type=book` với `X-Client: mobile`, `Accept: application/json`.
3. `GET /search?type=book&page=1` với `X-Client: web`, `Accept: application/json`.
4. `POST /search?type=book&page=1` với `X-Client: mobile`, `Accept: application/json`.

**Đáp án:** chỉ (1), vì tất cả điều kiện đều phải thỏa. Đoạn là minh họa mapping (không định nghĩa class/return body).

**Bài 2.** Một POST endpoint có `consumes="application/json"` và `produces="text/plain"`. Client gửi `Content-Type: application/json`, `Accept: application/json`. Điều kiện nào làm endpoint không khớp?

**Đáp án:** `produces` do client không chấp nhận `text/plain`. Muốn nhận response text, client cần gửi `Accept: text/plain` hoặc loại Accept cho phép nó theo hợp đồng.

**Bài 3.** Có hai GET `/report`, một dùng `params="mode=fast"` và một dùng `params="mode=slow"`. Client gửi `?mode=fast` thì method nào được chọn? Nếu không có `mode` thì chuyện gì xảy ra?

**Đáp án:** mapping fast được chọn. Khi thiếu mode, không có mapping nào trong hai mapping đáp ứng điều kiện params; status trong cấu hình MVC thông thường có thể là 400 do unsatisfied params, nhưng cần kiểm thử cấu hình thực.

**Bài 4.** API muốn trả JSON hoặc CSV trên cùng path. Nên dùng header tự đặt `format`, query param, hay `produces`?

**Gợi ý:** nếu đây là các representation khác nhau của cùng tài nguyên, có thể dùng `produces` và content negotiation với `Accept: application/json` hoặc `Accept: text/csv`, **nhưng** phải có converter/logic thực sự phát CSV và cần test với Accept rộng. Nếu nghiệp vụ muốn xuất báo cáo thành tệp và yêu cầu khác biệt đáng kể, endpoint export riêng hoặc query format rõ ràng có thể dễ vận hành hơn.

**Bài 5.** Tại sao chỉ sửa `@RequestBody` thành `@RequestParam` không nhất thiết giải quyết 415?

**Gợi ý:** 415 xảy ra ở tầng điều kiện `consumes`/khả năng đọc media type, có thể trước khi argument được resolve. Cần kiểm tra `Content-Type`, annotation mapping, input contract và converter chứ không chỉ đổi parameter annotation.

## 14. Checklist khi thiết kế và kiểm thử một mapping

- [ ] Method đúng ngữ nghĩa HTTP; dùng `@GetMapping`/`@PostMapping`... tường minh.
- [ ] Base path ở class và path tại method tạo ra URI cuối cùng như mong muốn.
- [ ] Chỉ dùng `params` khi cần chọn handler theo request parameters; tách rõ khỏi `@RequestParam`.
- [ ] Chỉ dùng `headers` khi cần điều kiện header thật sự; không coi điều kiện ấy là security.
- [ ] `consumes` biểu thị request `Content-Type` được chấp nhận, có converter đọc body tương ứng.
- [ ] `produces` biểu thị response representation phù hợp `Accept`, có converter ghi body tương ứng.
- [ ] Khi dùng mảng, hiểu đúng AND ở params/headers và OR ở media/method alternatives.
- [ ] Kiểm thử request thiếu param/header, giá trị sai và Content-Type/Accept không phù hợp.
- [ ] Kiểm thử 405, 400, 415, 406 và 404 trong cấu hình ứng dụng thật.
- [ ] Nếu có nhiều mappings cùng method/path, xác minh chúng phân biệt rõ bằng điều kiện và không ambiguous.
- [ ] Nếu class có consumes/produces mặc định, kiểm tra method-level overrides.
- [ ] Kiểm tra behavior với `Accept: */*`, không tự phỏng đoán format được chọn.
- [ ] Khi lỗi, phân biệt mismatch ở mapping với conversion/validation/serialization sau routing.
- [ ] Bổ sung `MockMvc`/integration tests cho đúng tổ hợp method, headers, params, media types.
- [ ] Ghi tài liệu API rõ request headers/body, response Content-Type và status errors.

**Kết luận vận dụng:** Trong Spring MVC, URL chỉ là một thành phần của `RequestMappingInfo`. Một request được đưa tới controller method khi **HTTP method, params, headers, consumes và produces** đều phù hợp với yêu cầu mapping; nếu nhiều method cạnh tranh, Spring tiếp tục đánh giá độ cụ thể. Thiết kế các điều kiện rõ ràng giúp ứng dụng phân tuyến chính xác, trả lỗi HTTP đúng nguyên nhân và tránh mapping trùng/khó debug.

### Tài liệu tham khảo chính thức

- [Spring Framework — Mapping Requests (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework 6.1 — RequestMapping annotation API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html)
- [Spring Framework 6.1 — RequestMappingInfo API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/RequestMappingInfo.html)
- [Spring Framework 6.1 — MVC Request Conditions API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/condition/package-summary.html)
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)

# Giá trị mặc định, tham số tùy chọn và dữ liệu bị thiếu trong Spring Boot

## 1. Vấn đề cốt lõi: “không gửi” không đồng nghĩa “gửi giá trị rỗng”

Khi thiết kế REST API, client có thể bỏ hẳn một dữ liệu, gửi chuỗi rỗng, gửi JSON null, gửi 0, gửi false hoặc gửi một collection rỗng. Các trạng thái này **không nhất thiết có cùng ý nghĩa nghiệp vụ**. Nếu server coi tất cả như “chưa nhập”, một API tìm kiếm có thể lọc sai dữ liệu; nghiêm trọng hơn, một API cập nhật từng phần có thể ghi đè hoặc xóa nhầm thông tin.

Spring MVC và Spring WebFlux hỗ trợ binding request qua @RequestParam, @RequestHeader, @CookieValue, @PathVariable, @RequestBody, @RequestPart và các đối tượng request tương ứng. Spring Boot tự động cấu hình nhiều thành phần đó, nhưng **không thể tự quyết định** việc một field vắng mặt sẽ dùng mặc định, giữ nguyên dữ liệu cũ hay bị từ chối.

Ví dụ hợp đồng GET /api/books:

- page không xuất hiện: dùng page=1.
- size không xuất hiện hoặc truyền size= rỗng: dùng size=20 theo @RequestParam(defaultValue).
- size=0: đây là một số được gửi thật; nếu size phải từ 1 đến 100, trả HTTP 400.
- sort không xuất hiện: dùng createdAt; sort=unknown: báo lỗi hoặc xử lý theo chính sách được tài liệu hóa.
- includeArchived không xuất hiện: có thể là “không áp dụng bộ lọc” thay vì false.
- includeArchived=false: client đã chọn false một cách tường minh.

Ví dụ hợp đồng PATCH /api/profile lại khác:

- Không gửi displayName: giữ nguyên tên hiện tại.
- Gửi displayName=null: có thể yêu cầu xóa tên (nếu API cho phép), hoặc trả lỗi.
- Gửi displayName="": có thể là dữ liệu không hợp lệ vì rỗng.
- Gửi active=false: phải giữ false, không coi đó là dấu hiệu “không nhập”.

**Mục tiêu của bài học** là biết chọn kiểu Java, annotation, default và validation phù hợp để request có nghĩa rõ ràng ngay từ HTTP boundary, đồng thời bảo toàn sự khác nhau giữa missing và các giá trị hợp lệ.

## 2. Bảng các trạng thái dữ liệu cần phân biệt

| Trạng thái | Ví dụ HTTP/JSON | Cần hiểu |
|---|---|---|
| Query parameter vắng mặt | GET /books | Không có key page trong query |
| Query parameter rỗng | GET /books?page= | Có key page, giá trị ban đầu rỗng |
| Query parameter chứa whitespace | GET /books?q=%20%20 | Có chuỗi hai dấu cách; không giống absent |
| Query parameter bằng 0 | GET /books?page=0 | Client chủ động truyền số 0 |
| Query parameter bằng false | GET /books?archived=false | Client chủ động truyền Boolean false |
| Query parameter chứa chữ null | GET /books?q=null | Chuỗi "null", không phải JSON null |
| Header không tồn tại | Không có X-Mode | Header absent |
| Header rỗng | X-Mode: | Header hiện diện nhưng rỗng, tùy HTTP client |
| Cookie không tồn tại | Không có cookie theme | Cookie absent |
| JSON object không có field | {} | Field missing |
| JSON field có null | {"name":null} | Field present với JSON null |
| JSON field có chuỗi rỗng | {"name":""} | Field present với giá trị String rỗng |
| JSON field là mảng rỗng | {"tags":[]} | Field present và có collection rỗng |
| JSON field là false hoặc 0 | {"active":false,"count":0} | Giá trị có nghĩa, không phải missing |
| HTTP body không được gửi | POST không có body | Thiếu toàn bộ nội dung body |
| HTTP body chứa JSON null | POST body là null | Có JSON token null, Java có thể nhận null |

Có ba khái niệm khác nhau:

1. **Presence**: dữ liệu có xuất hiện trong HTTP request không?
2. **Parsed value**: sau conversion/deserialization, Java nhận được kiểu/giá trị nào?
3. **Business semantics**: ứng dụng sẽ dùng mặc định, giữ nguyên, xóa, chấp nhận hay trả lỗi?

Không được suy ngược chắc chắn presence chỉ từ một biến Java null. Java null có thể đến từ field JSON thiếu, JSON null tường minh, không có query parameter, hoặc conversion/binding trả null.

### 2.1. Empty và blank khác nhau

Trong Java 17:

~~~java
"".isEmpty();     // true
"  ".isEmpty();   // false
"  ".isBlank();   // true
"0".isBlank();    // false
~~~

Đây là những biểu thức minh họa, không phải chương trình độc lập. Một giá trị toàn khoảng trắng có thể bị domain coi là không hợp lệ dù về mặt HTTP nó là một String có nội dung. @RequestParam(defaultValue=...) áp dụng cho missing/empty theo quy tắc annotation, **không phải công cụ chuẩn hóa mọi chuỗi whitespace**.

### 2.2. Query parameter không có null kiểu JSON

URL query có giá trị là chuỗi sau khi parse. Chuỗi q=null vẫn là chữ n-u-l-l nếu ứng dụng không định nghĩa sentinel riêng. Nếu client cần gửi trạng thái null tường minh trong một object, JSON body có khả năng diễn đạt tốt hơn; tuy nhiên cách áp dụng null trong thao tác CREATE/PATCH vẫn do contract quyết định.

## 3. @RequestParam: required=true, required=false và defaultValue

Một phương thức annotated controller có thể khai báo:

~~~java
@GetMapping("/books")
String books(@RequestParam(name = "page") int page) {
    return "page=" + page;
}
~~~

Snippet này phải nằm trong một @RestController phù hợp. @RequestParam có required=true theo mặc định; client thiếu page thường dẫn đến lỗi missing parameter và HTTP 400 qua error handling mặc định. Nếu page=abc, conversion sang int thất bại, thường cũng trả 400 nhưng do lỗi kiểu dữ liệu, không phải do missing.

### 3.1. required=true không phải validation hoàn chỉnh

Required chỉ yêu cầu tham số có thể được binding theo quy tắc. Nó không tự bảo đảm giá trị dương, thuộc whitelist, không chứa khoảng trắng hay hợp lệ về nghiệp vụ.

Ví dụ GET /books?page=-2 có page là int hợp lệ về kiểu nhưng có thể không hợp lệ với paging. Phải kiểm tra page >= 1, hoặc dùng Bean Validation/method validation được cấu hình phù hợp.

### 3.2. required=false và kiểu nullable

~~~java
@GetMapping("/books")
String books(@RequestParam(name = "q", required = false) String q) {
    return q == null ? "all" : q;
}
~~~

Khi q không được gửi, controller có thể nhận null. Khi q=, có thể nhận chuỗi rỗng tùy conversion. Khi q=%20%20, có thể nhận chuỗi whitespace.

Nếu một primitive như int hoặc boolean thực sự có thể thiếu mà không có default, sẽ nảy sinh vấn đề vì primitive không biểu diễn được null. **Ưu tiên Integer, Boolean hoặc Optional<T>** cho trường hợp optional và cần biết có giá trị hay không.

### 3.3. defaultValue: cách dùng cơ bản

~~~java
@GetMapping("/books")
String books(
        @RequestParam(name = "page", defaultValue = "1") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return "page=" + page + ",size=" + size;
}
~~~

Khi đặt @RequestParam(defaultValue), thuộc tính required được ngầm coi là false. Với @RequestParam, giá trị mặc định được dùng khi tham số **vắng mặt** hoặc được xem là **rỗng**.

Ví dụ các trường hợp thường gặp:

| Request | page được binding | size được binding |
|---|---:|---:|
| GET /books | 1 | 20 |
| GET /books?page=&size= | 1 | 20 |
| GET /books?page=3&size=50 | 3 | 50 |
| GET /books?page=0 | 0 | 20 |
| GET /books?page=abc | Type conversion error | Không có kết quả handler bình thường |
| GET /books?size=-1 | 1 | -1 |

**Không dùng default để che lỗi kiểu dữ liệu.** page=abc không có nghĩa “không gửi page”. size=0 cũng không phải missing, dù domain có thể quyết định từ chối nó.

Các giá trị default phải convert được sang kiểu Java tương ứng; một defaultValue="abc" cho int là lỗi cấu hình/định nghĩa API. Nếu thuộc tính chứa dấu cách, hãy kiểm thử conversion thực tế; không suy luận mọi chuỗi có whitespace đều tự kích hoạt default.

### 3.4. Optional<T>

~~~java
@GetMapping("/books")
String books(@RequestParam(name = "sort") Optional<String> sort) {
    return sort.filter(s -> !s.isBlank())
            .orElse("createdAt");
}
~~~

Đoạn này cần import java.util.Optional và được đặt trong controller. Spring hỗ trợ Optional cho nhiều argument resolver, bao gồm @RequestParam. Optional.empty biểu diễn không có giá trị ở Java, giúp code giảm thao tác kiểm tra null.

Optional **không tự giữ metadata presence ở mức wire** nếu conversion đã gộp empty/missing. Không nên lạm dụng Optional như field của mọi JSON DTO hoặc JPA entity chỉ vì @RequestParam hỗ trợ nó.

### 3.5. Boolean tùy chọn nên dùng wrapper khi cần ba trạng thái

~~~java
@RequestParam(name = "includeArchived", required = false)
Boolean includeArchived
~~~

Khi binding thành Boolean wrapper, ứng dụng có thể có true, false và null. Điều này quan trọng nếu:

- null = không lọc theo trạng thái lưu trữ;
- true = chỉ lấy mục đã lưu trữ;
- false = chỉ lấy mục chưa lưu trữ.

Nếu viết Boolean.TRUE.equals(includeArchived) và dùng ngay làm filter false, bạn đã **chủ động gộp null với false**. Điều đó chỉ đúng khi contract nói missing tương đương false.

### 3.6. Nhiều giá trị cho cùng một query key

Client có thể gửi:

~~~text
GET /books?tag=java&tag=spring&tag=web
~~~

Với @RequestParam(name="tag", required=false) List<String> tags hoặc MultiValueMap, Spring có thể bind nhiều giá trị theo hợp đồng type conversion. Nhưng không mặc định rằng missing list luôn là empty list hay parameter trùng lặp luôn được xử lý theo thứ tự mong muốn. Nếu API chỉ chấp nhận đúng một giá trị, cần có chính sách từ chối duplicate khi cần.

## 4. @RequestHeader, @CookieValue, @PathVariable và dữ liệu multipart

### 4.1. Header có thể tùy chọn hoặc có default

~~~java
@GetMapping("/client-mode")
String clientMode(
        @RequestHeader(name = "X-Mode", defaultValue = "standard")
        String mode) {
    return mode;
}
~~~

Header không được gửi sẽ dùng standard. Một header hiện diện nhưng được coi là empty cũng có thể dùng defaultValue. Không dùng header do client kiểm soát để quyết định role, tenant hay quyền truy cập nếu không có cơ chế xác thực tương ứng.

### 4.2. Cookie tùy chọn

~~~java
@GetMapping("/theme")
String theme(
        @CookieValue(name = "theme", required = false)
        String theme) {
    return theme == null || theme.isBlank() ? "system" : theme;
}
~~~

Cookie có thể vắng mặt. Việc gán theme="system" là quyết định nghiệp vụ dễ chấp nhận với UI preference, nhưng không nên tạo default thiếu an toàn cho cookie phiên đăng nhập hay quyền truy cập.

### 4.3. @PathVariable(required=false) không tự thêm một URL mới

Một mapping /orders/{id} yêu cầu path segment id để route có thể khớp. Dù annotation @PathVariable(required=false) có hỗ trợ về cách resolve, nó **không làm /orders tự khớp /orders/{id}**.

Nếu cần cả danh sách và chi tiết, định nghĩa hai route:

~~~java
@GetMapping("/orders")
String listOrders() {
    return "all orders";
}

@GetMapping("/orders/{id}")
String findOrder(@PathVariable long id) {
    return "order " + id;
}
~~~

Đây là hai method để đặt trong cùng một controller; code có thể biên dịch khi imports/annotation phù hợp. Nếu nghiệp vụ muốn dùng chung handler, có thể khai báo các URL patterns tương ứng và kiểm thử, nhưng không nên dùng optional path variable để che một thiếu sót trong route mapping.

### 4.4. Multipart file: không gửi khác file kích thước 0

Trong Spring MVC, @RequestPart(name="avatar", required=false) MultipartFile avatar có thể nhận null khi client không gửi part. Nếu có part nhưng file trống, MultipartFile.isEmpty() có thể true. Một thao tác “không đổi avatar” và “xóa avatar” nên có semantics riêng.

Trong WebFlux reactive, dùng kiểu multipart tương ứng như FilePart thay vì bê nguyên MultipartFile Servlet sang controller reactive. Multipart upload còn cần kiểm tra size limit, content type, filename và bảo mật lưu trữ.

## 5. @RequestBody: toàn body khác từng field JSON

@RequestBody giải mã HTTP message body, thường từ application/json sang Java object. Có hai câu hỏi độc lập:

1. Toàn request body có hiện diện và giải mã thành object không?
2. Mỗi field bên trong JSON object có hiện diện, hợp lệ và được phép null không?

Ví dụ JSON:

~~~json
{"title":"Spring Boot","copies":2,"published":false}
~~~

Khác với:

~~~json
{"title":"Spring Boot"}
~~~

và khác với:

~~~json
{"title":"Spring Boot","copies":null,"published":null}
~~~

Nếu Java record chỉ có String title, Integer copies, Boolean published, Jackson có thể đưa cả field vắng mặt lẫn explicit JSON null thành Java null. Vì thế **chỉ nhìn DTO null không đủ để suy ra field bị bỏ qua hay được gửi null**.

### 5.1. @RequestBody mặc định required=true

~~~java
@PostMapping("/books")
String create(@RequestBody NewBook body) {
    return body.title();
}
~~~

Method trên là snippet cần đặt trong controller và định nghĩa kiểu NewBook. Với body bắt buộc nhưng không có nội dung để bind, Spring thường trả 400. JSON sai cú pháp hoặc sai kiểu cũng có thể trả 400 do đọc/deserialize, không phải vì thiếu body. Với Content-Type không được hỗ trợ, server có thể trả 415.

Không nên đặt required=false chỉ để che lỗi từ client không gửi payload mà hợp đồng API bắt buộc.

### 5.2. @RequestBody(required=false) là tùy chọn của toàn body

~~~java
@PostMapping("/draft")
Map<String, Boolean> draft(
        @RequestBody(required = false) Map<String, Object> body) {
    return Map.of(
            "bodyPresent", body != null,
            "titlePresent", body != null && body.containsKey("title"));
}
~~~

Đoạn này cần import java.util.Map. Không có body có thể làm body==null; JSON token null cũng có thể deserialize thành null. Vì vậy kết quả bodyPresent=false trong code này có nghĩa **không có object Map đã bind**, chứ không phải khẳng định byte-level HTTP body hoàn toàn vắng mặt.

Ngay cả khi required=false, JSON malformed vẫn là lỗi; optional không có nghĩa bỏ qua lỗi parser.

### 5.3. Default trong DTO record

~~~java
public record BookInput(String title, Integer copies, Boolean published) {
    public BookInput {
        if (copies == null) copies = 1;
        if (published == null) published = false;
    }
}
~~~

Với Jackson hỗ trợ Java records, compact constructor có thể đặt default khi dữ liệu target bị null. Cách này hợp lý nếu contract CREATE định nghĩa missing và explicit null giống nhau. Tuy nhiên nó **không phân biệt** hai trạng thái, và không nên tái dùng như vậy cho PATCH khi explicit null mang nghĩa khác.

Không dùng int/boolean primitive trong DTO nếu cần biết field có xuất hiện hay không, vì primitive chỉ chứa 0/false và có thể làm mất thông tin presence. Nếu 0/false là giá trị có nghĩa, không dùng chúng làm “sentinel missing”.

### 5.4. Field initializer không phải giải pháp chung

~~~java
public class SearchDto {
    private Integer size = 20;

    public Integer getSize() { return size; }
    public void setSize(Integer size) { this.size = size; }
}
~~~

Trong Java bean, initializer có thể giữ giá trị 20 khi JSON bỏ qua size, nhưng JSON gửi "size":null có thể khiến setter gán null. Có các policy Jackson như @JsonSetter(nulls=Nulls.SKIP), song chúng phụ thuộc kiểu DTO/cách deserialize. Hãy chọn rule rõ ràng và viết test, thay vì tin rằng một initializer bảo đảm mọi trường hợp.

## 6. Bean Validation và giới hạn của required

Java có thể convert dữ liệu thành công mà giá trị vẫn không hợp lệ về nghiệp vụ. Ví dụ size=-100 là int hợp lệ, nhưng paging API có thể yêu cầu 1..100.

Với DTO:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @Positive Integer copies,
        Boolean published) {}
~~~

Cần có Bean Validation provider, thường từ spring-boot-starter-validation trong ứng dụng Boot. @Valid @RequestBody có thể kích hoạt validation phù hợp.

Bảng ý nghĩa chính:

| Constraint | Khi null | Khi không hợp lệ |
|---|---|---|
| @NotNull | Fail | Chưa bảo đảm String không rỗng |
| @NotBlank | Fail | Fail với String rỗng hoặc chỉ whitespace |
| @NotEmpty | Fail | Fail khi String/collection/map/array rỗng |
| @Positive | Thường pass khi null | Fail với số <=0 |
| @Min(1) | Thường pass khi null | Fail nếu số nhỏ hơn 1 |
| @Size(min=1) | Thường pass khi null | Fail khi kích thước ngắn hơn mức yêu cầu |

**@Positive và @Min không đồng nghĩa required.** Nếu field cần bắt buộc và phải dương, kết hợp @NotNull và @Positive/@Min. Nếu field tùy chọn, @Positive có thể kiểm tra giá trị client gửi trong khi service vẫn có quyền áp dụng default khi null.

Không silently fallback sang default mỗi khi conversion hoặc validation lỗi, trừ khi đó là policy được công khai rõ. Ví dụ size=0 nên bị từ chối thay vì âm thầm đổi thành size=20 nếu contract quy định size phải từ 1 đến 100.

### 6.1. Thứ tự xử lý quan trọng

Trong luồng request điển hình:

~~~text
HTTP request
  |
  +-- Tìm handler phù hợp
  |
  +-- Đọc query/header/body và type conversion
  |
  +-- Áp dụng defaultValue / deserialize DTO
  |
  +-- Validation nếu được cấu hình
  |
  +-- Gọi controller/service và áp dụng business defaults
  |
  +-- Trả HTTP response
~~~

Sơ đồ là tổng quát, không phải thứ tự bytecode chính xác cho mọi argument resolver. Một default gắn tại annotation có thể được áp dụng **trước khi** controller nhận biến Java. Một default chỉ tồn tại ở service sẽ được áp dụng **sau khi** dữ liệu đi qua binding/validation. Vì vậy phải đặt default ở đúng tầng và không vô tình tạo các quy tắc mâu thuẫn.

## 7. Default nên được đặt ở đâu?

| Tầng | Ví dụ | Khi nên dùng |
|---|---|---|
| HTTP annotation | @RequestParam(defaultValue="20") | Default query/header/cookie đơn giản |
| DTO constructor | copies=1 nếu null | Quy tắc deserialize/khởi tạo DTO nhất quán |
| Service layer | Thiếu sort thì chọn createdAt | Default nghiệp vụ dùng bởi HTTP, batch, event |
| Domain model | Trạng thái mặc định của entity | Bảo vệ invariant domain |
| Database | DEFAULT cho cột không cung cấp | Bảo vệ lưu trữ ở tình huống phù hợp |
| Client UI | Input page hiển thị 1 | Cải thiện trải nghiệm, không thay server rule |

Một default quan trọng nên có **một nguồn chân lý**. Nếu HTTP annotation chọn size=20 nhưng job nội bộ chọn 200, cùng nghiệp vụ có thể trả kết quả khác nhau tùy điểm vào. Khi default là rule domain, cân nhắc đặt nó ở service/domain layer rồi dùng annotation chỉ để biểu diễn HTTP convenience nhất quán.

Default có thể là thay đổi breaking về hành vi. Đổi page size mặc định từ 20 sang 100 có thể làm tăng thời gian truy vấn, số byte phản hồi và tải database dù endpoint URL không thay đổi. Cần có test và tài liệu khi cập nhật.

## 8. Ví dụ Spring Boot MVC có thể chạy: query, headers, body và validation

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring MVC (Servlet), embedded Tomcat thông dụng. Giả sử project được tạo bằng Spring Initializr/Gradle với Spring Boot plugin, trong build.gradle có các dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Không cần database cho demo. Source code sẽ trả dữ liệu mô phỏng, không lưu vào DB thật.

### 8.1. Main class

File src/main/java/dev/example/input/RequestInputApplication.java:

~~~java
package dev.example.input;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestInputApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequestInputApplication.class, args);
    }
}
~~~

### 8.2. Controller hoàn chỉnh

File src/main/java/dev/example/input/RequestInputController.java:

~~~java
package dev.example.input;

import java.util.Map;
import java.util.Optional;
import java.util.Set;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class RequestInputController {

    public record SearchResult(
            int page,
            int size,
            String keyword,
            String sort,
            Boolean includeArchived,
            boolean archiveFilterProvided) {}

    public record CreateBookInput(
            @NotBlank String title,
            @Positive Integer copies,
            Boolean published) {}

    public record BookResult(
            String title,
            int copies,
            boolean published) {}

    public record ClientHints(String mode, String theme) {}

    @GetMapping("/search")
    public SearchResult search(
            @RequestParam(name = "page", defaultValue = "1")
            int page,
            @RequestParam(name = "size", defaultValue = "20")
            int size,
            @RequestParam(name = "q", required = false)
            String q,
            @RequestParam(name = "sort")
            Optional<String> sort,
            @RequestParam(name = "includeArchived", required = false)
            Boolean includeArchived) {

        if (page < 1 || size < 1 || size > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "page must be >= 1; size must be 1..100");
        }

        String normalizedQ =
                q == null || q.isBlank() ? null : q.strip();

        String sortBy = sort
                .filter(value -> !value.isBlank())
                .map(String::strip)
                .orElse("createdAt");

        if (!Set.of("createdAt", "title").contains(sortBy)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "sort must be createdAt or title");
        }

        return new SearchResult(
                page, size, normalizedQ, sortBy,
                includeArchived, includeArchived != null);
    }

    @GetMapping("/client-hints")
    public ClientHints clientHints(
            @RequestHeader(
                    name = "X-Mode", defaultValue = "standard")
            String mode,
            @CookieValue(name = "theme", required = false)
            String theme) {

        return new ClientHints(
                mode,
                theme == null || theme.isBlank() ? "system" : theme);
    }

    @PostMapping(
            path = "/books",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookResult> create(
            @Valid @RequestBody CreateBookInput body) {

        int copies = body.copies() == null ? 1 : body.copies();
        boolean published = body.published() != null
                && body.published();

        BookResult result =
                new BookResult(body.title().strip(), copies, published);

        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @PostMapping(path = "/draft",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Boolean> optionalDraft(
            @RequestBody(required = false) Map<String, Object> body) {

        return Map.of(
                "bodyPresent", body != null,
                "titlePresent",
                body != null && body.containsKey("title"));
    }
}
~~~

Hai file Java ở trên có các import và class tương ứng trong project Spring Boot MVC Java 17+. Các records được Jackson hỗ trợ trong starter-web thông thường. Controller không truy vấn database; phần default là chính sách minh họa.

**Đọc kỹ các quyết định:**

- page=1 và size=20 chỉ dùng làm default cho missing/empty; size=-1 hoặc size=101 bị từ chối thay vì fallback.
- q là optional; code **chủ động** gộp missing và blank thành normalizedQ=null, tương ứng không lọc theo keyword.
- sort dùng Optional, missing hoặc blank về createdAt; một sort lạ bị từ chối bằng whitelist. Không đưa thẳng chuỗi sort do client gửi vào câu SQL.
- includeArchived dùng Boolean để giữ ba trạng thái true/false/null và archiveFilterProvided mô tả khi binding có giá trị.
- title phải @NotBlank. copies null dùng 1, nhưng copies=0 không pass @Positive; published null dùng false, explicit false cũng giữ false.
- optionalDraft cho phép body không bind được thành Map, nhưng bodyPresent không phân biệt vắng mặt với JSON token null.

### 8.3. Cấu hình và lệnh chạy

File src/main/resources/application.yml:

~~~yaml
server:
  port: 8080
~~~

Chạy trong thư mục Gradle project:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 8.4. Kiểm tra GET default, valid và invalid

~~~bash
curl -i "http://localhost:8080/api/search"
curl -i "http://localhost:8080/api/search?page=&size="
curl -i "http://localhost:8080/api/search?page=2&size=15&sort=title"
curl -i "http://localhost:8080/api/search?size=0"
curl -i "http://localhost:8080/api/search?page=abc"
~~~

Hai request đầu thường trả HTTP 200 với page=1, size=20. Request thứ ba trả page=2, size=15, sort="title". size=0 và page=abc thường trả HTTP 400 từ business range check hoặc type conversion. Không phụ thuộc vào một JSON error body cố định: cấu trúc lỗi do cấu hình Spring Boot/ControllerAdvice quyết định.

### 8.5. Kiểm tra false khác missing

~~~bash
curl -i "http://localhost:8080/api/search"
curl -i "http://localhost:8080/api/search?includeArchived=false"
curl -i "http://localhost:8080/api/search?includeArchived=true"
~~~

Request thiếu includeArchived có archiveFilterProvided=false; request gửi false có includeArchived=false và archiveFilterProvided=true; request gửi true có includeArchived=true và archiveFilterProvided=true. Đây là lý do không đổi mọi optional Boolean thành primitive boolean khi absence có ý nghĩa.

### 8.6. Kiểm tra body JSON mặc định

~~~bash
curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: application/json" \
  -d '{"title":"Spring Boot"}'
~~~

Kết quả chính mong đợi: HTTP 201 với body:

~~~json
{"title":"Spring Boot","copies":1,"published":false}
~~~

Khi gửi đủ field:

~~~bash
curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: application/json" \
  -d '{"title":"Web Runtime","copies":3,"published":true}'
~~~

Kết quả dự kiến:

~~~json
{"title":"Web Runtime","copies":3,"published":true}
~~~

Với body {"title":"Book","copies":0} hoặc {"copies":2} thiếu title, validation dẫn đến HTTP 400 trong cấu hình mặc định. Một HTTP body trống với @RequestBody required=true cũng bị từ chối.

Headers như Content-Length và Date không phải phần output cố định; chỉ kiểm tra status/body logic.

### 8.7. Kiểm tra header/cookie optional

~~~bash
curl -i "http://localhost:8080/api/client-hints"
curl -i "http://localhost:8080/api/client-hints" \
  -H "X-Mode: compact" -H "Cookie: theme=dark"
~~~

Lần đầu trả mode=standard, theme=system; lần sau mode=compact, theme=dark nếu request không bị proxy/filter thay đổi. Không xem X-Mode và theme cookie là thông tin xác thực.

## 9. PATCH và sự khác biệt giữa missing và explicit JSON null

Với API CREATE, việc thiếu copies hoặc gửi null có thể đều nghĩa là dùng default 1. Nhưng với PATCH, presence thường điều khiển hành động cập nhật:

~~~json
{}
~~~

có thể nghĩa “giữ nguyên các field”.

~~~json
{"displayName":null}
~~~

có thể nghĩa “xóa tên”; hoặc trả 400 nếu không cho phép null.

~~~json
{"displayName":""}
~~~

có thể nghĩa đặt chuỗi rỗng hoặc lỗi @NotBlank. Không tự gộp ba trường hợp này khi chưa có contract.

### 9.1. Vì sao DTO nullable đơn giản không đủ?

~~~java
public record ProfilePatch(String displayName, String phone) {}
~~~

Một deserializer có thể trả displayName=null cho cả khi JSON bỏ qua field lẫn khi gửi explicit null. Code:

~~~java
if (patch.displayName() != null) {
    entity.setDisplayName(patch.displayName());
}
~~~

sẽ không thể biểu diễn hành động “xóa tên bằng explicit null”. Ngược lại, nếu luôn setDisplayName(null), một request không gửi tên có thể xóa nhầm giá trị cũ.

### 9.2. Dùng JsonNode để theo dõi presence

~~~java
import com.fasterxml.jackson.databind.JsonNode;

void applyPatch(JsonNode patch, Profile profile) {
    if (!patch.isObject()) {
        throw new IllegalArgumentException("Expected JSON object");
    }

    if (!patch.has("displayName")) {
        return;
    }

    JsonNode value = patch.get("displayName");

    if (value.isNull()) {
        profile.setDisplayName(null);
    } else if (value.isTextual() && !value.textValue().isBlank()) {
        profile.setDisplayName(value.textValue().strip());
    } else {
        throw new IllegalArgumentException("Invalid displayName");
    }
}
~~~

Đây là snippet chứ không phải chương trình độc lập: cần class Profile, Jackson và cơ chế chuyển IllegalArgumentException thành HTTP 400. Điều quan trọng:

- patch.has("displayName")==false: field không có trong JSON, giữ nguyên.
- has==true và value.isNull(): field xuất hiện với JSON null.
- has==true, textual và không blank: có giá trị String hợp lệ.

JsonNode.hasNonNull("displayName") **không thay thế has(...)** khi muốn biết explicit null có xuất hiện, vì hasNonNull trả false với NullNode.

### 9.3. JSON Merge Patch và JSON Patch không phải một

Với JSON Merge Patch (RFC 7396), một member có giá trị null thường mang nghĩa xóa member trong đối tượng kết quả; member vắng mặt thường được giữ nguyên. Với JSON Patch (RFC 6902), các operation add, replace, remove biểu diễn thay đổi tường minh.

Spring Boot không tự cài toàn bộ semantics của RFC chỉ vì method dùng @PatchMapping. Hãy chọn Content-Type, validation, concurrency control (nếu cần ETag/If-Match), xử lý lỗi và đặc tả response rõ ràng.

### 9.4. False và 0 là update hợp lệ

Không dùng điều kiện sau nếu 0 là giá trị hợp lệ:

~~~java
// Sai khi muốn cho phép đặt count về 0
if (patchCount != 0) {
    entity.setCount(patchCount);
}
~~~

Tương tự, if (patchActive) bỏ qua explicit false. Với PATCH cần check **field có được gửi không**, rồi mới xét value. Một representation presence-aware hoặc JsonNode có ích hơn primitive.

## 10. Collection, enum, ngày tháng và dữ liệu lồng nhau

### 10.1. List thiếu khác list rỗng

~~~json
{}
~~~

khác với:

~~~json
{"tags":[]}
~~~

Trong PATCH, thiếu tags có thể nghĩa giữ nguyên; [] có thể nghĩa xóa mọi tag. Với Create, [] có thể là giá trị hợp lệ hoặc bị @NotEmpty từ chối. DTO List<String> có thể phân biệt [] với null trong một số trường hợp, nhưng absent và JSON null vẫn thường cùng dẫn đến null nếu không theo dõi presence.

Nên xác định giới hạn số phần tử, duplicate policy, thứ tự, cách chuẩn hóa string và hành vi khi phần tử là null.

### 10.2. Enum conversion và validation

~~~java
public enum SortDirection {
    ASC, DESC
}
~~~

Nếu nhận @RequestParam(name="direction", defaultValue="ASC") SortDirection direction, một chuỗi phù hợp có thể convert thành enum. Chuỗi không khớp như SIDEWAYS thường bị từ chối. Đừng giả định "asc" tự động bằng ASC trong mọi converter hay phiên bản. Nếu cần case-insensitive, cấu hình converter rõ ràng và test.

### 10.3. Date và timezone

~~~java
@GetMapping("/events")
String events(
        @RequestParam(name = "date", required = false)
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {

    LocalDate selected =
            date == null ? LocalDate.now(ZoneOffset.UTC) : date;

    return selected.toString();
}
~~~

Snippet cần import LocalDate, ZoneOffset, DateTimeFormat và đặt trong controller. Việc chọn ngày hiện tại theo UTC là policy minh họa; một domain theo múi giờ khách hàng cần ZoneId rõ ràng. Không thể cho stdout bất biến vì “ngày hiện tại” phụ thuộc thời điểm chạy.

### 10.4. Nested object có nhiều tầng missing

Với {"preferences":{"language":"vi"}}, có thể có các trường hợp:

- Không có preferences.
- preferences=null.
- preferences={}.
- preferences tồn tại nhưng thiếu language.
- language=null hoặc "".

Nếu API PATCH, đừng mặc định thay toàn bộ preferences object chỉ vì người dùng cập nhật một field con. Định nghĩa merge semantics và validate từng tầng.

## 11. Spring WebFlux: cùng bài toán, reactive pipeline

Spring WebFlux có annotated @RequestParam, @RequestHeader, @RequestBody và các resolver tương ứng. Tuy nhiên nó dùng non-blocking pipeline, với Mono/Flux và khác biệt trong cách đọc form data. Đối với WebFlux annotated controllers, @RequestParam tập trung vào **query parameters**; form/multipart request data dùng cơ chế đọc/binding riêng.

Một project WebFlux reactive server nên có spring-boot-starter-webflux, không cần thêm starter-web nếu muốn tránh Boot chọn Servlet MVC trong thiết lập thông thường.

### 11.1. Ví dụ controller WebFlux chạy được

File src/main/java/dev/example/reactive/ReactiveInputController.java trong project Boot WebFlux Java 17+:

~~~java
package dev.example.reactive;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/reactive")
public class ReactiveInputController {

    public record Payload(String text) {}

    @GetMapping("/search")
    public Mono<Map<String, Object>> search(
            @RequestParam(name = "page", defaultValue = "1")
            int page,
            @RequestParam(name = "q", required = false)
            String q) {

        if (page < 1) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "page must be positive"));
        }

        return Mono.just(Map.of(
                "page", page,
                "q", q == null ? "" : q));
    }

    @PostMapping("/optional-body")
    public Mono<Map<String, Boolean>> optionalBody(
            @RequestBody(required = false) Mono<Payload> body) {

        return body
                .map(value -> Map.of("bodyPresent", true))
                .defaultIfEmpty(Map.of("bodyPresent", false));
    }
}
~~~

Để chạy, đặt class @SpringBootApplication cùng package cha dev.example.reactive hoặc package trên, thêm spring-boot-starter-webflux và chạy Boot. Ví dụ không có database, không gọi block() hay subscribe() trong controller.

GET /reactive/search thiếu page trả JSON có page=1; GET /reactive/search?page=0 trả 400. POST /reactive/optional-body nhận một Payload hợp lệ trả bodyPresent=true; nếu deserializer cung cấp Mono.empty() do không có payload, kết quả có bodyPresent=false.

**Không đồng nhất absence của Publisher với byte-level absence của HTTP body.** JSON literal null có thể không tạo một Payload cụ thể; nếu cần phân biệt, hãy thiết kế representation/presence riêng.

### 11.2. Kiểm thử bằng @WebFluxTest và WebTestClient

Tạo src/test/java/dev/example/reactive/ReactiveInputControllerTest.java:

~~~java
package dev.example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = ReactiveInputController.class)
class ReactiveInputControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void missingPageUsesDefault() {
        client.get().uri("/reactive/search")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(1);
    }

    @Test
    void explicitZeroIsInvalid() {
        client.get().uri("/reactive/search?page=0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

Test trên cần spring-boot-starter-test trong WebFlux project và không bắt buộc mở port HTTP thật. Khi code có security filters/service beans khác, có thể cần thêm test configuration hoặc integration test phù hợp. WebTestClient kiểm tra reactive routing/binding/response pipeline; muốn kiểm tra TLS/proxy/connector network thật phải dùng integration test có server thực.

### 11.3. Tránh nhầm WebClient với WebFlux server

WebClient là HTTP client reactive có thể dùng ngay trong Spring MVC. Việc một controller trả Mono hoặc project có WebClient không tự chứng minh server đang dùng DispatcherHandler của WebFlux. Nếu cả starter-web và starter-webflux có mặt, Boot thường ưu tiên Servlet/MVC trừ khi cấu hình web-application-type khác.

Luôn xác nhận web stack, argument resolver và package imports khi chẩn đoán optional parameter có hành vi bất ngờ.

## 12. MockMvc: kiểm thử trạng thái missing/empty/false/0 trong MVC

Với RequestInputController ở mục 8, tạo src/test/java/dev/example/input/RequestInputControllerTest.java:

~~~java
package dev.example.input;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestInputControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingQueryUsesDefaults() throws Exception {
        mvc.perform(get("/api/search"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(1))
                .andExpect(jsonPath("$.size").value(20))
                .andExpect(jsonPath("$.sort").value("createdAt"))
                .andExpect(jsonPath("$.archiveFilterProvided").value(false));
    }

    @Test
    void emptyQueryUsesDefaults() throws Exception {
        mvc.perform(get("/api/search?page=&size="))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(1))
                .andExpect(jsonPath("$.size").value(20));
    }

    @Test
    void invalidTypeGets400() throws Exception {
        mvc.perform(get("/api/search?page=abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void explicitZeroIsNotMissing() throws Exception {
        mvc.perform(get("/api/search?size=0"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void falseIsAnExplicitValue() throws Exception {
        mvc.perform(get("/api/search?includeArchived=false"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.includeArchived").value(false))
                .andExpect(jsonPath("$.archiveFilterProvided").value(true));
    }

    @Test
    void missingJsonFieldsUseCreateDefaults() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Spring Boot\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.copies").value(1))
                .andExpect(jsonPath("$.published").value(false));
    }

    @Test
    void zeroCopiesFailsValidation() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Book\",\"copies\":0}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredTitleFails() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"copies\":2}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingBodyFails() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest());
    }
}
~~~

Từ thư mục Gradle project:

~~~bash
./gradlew test
~~~

Các test bao phủ nhiều ý nghĩa khác nhau của dữ liệu thiếu và sai. Không cần so sánh toàn bộ body lỗi mặc định của Spring Boot vì định dạng có thể khác theo phiên bản và error handler. Với API thực tế, nên có một error contract ổn định do ứng dụng định nghĩa và kiểm thử nó.

MockMvc kiểm tra request binding/MVC pipeline nhưng không thay thế integration test với network/proxy/security. Nếu API áp dụng path rewrite, content negotiation, multipart hoặc cấu hình Servlet đặc thù, cần kiểm chứng trên server thực.

## 13. Ma trận test đầu vào nên có

| Input | Hợp đồng mong đợi |
|---|---|
| Không có page | page=1 |
| page= | page=1 theo @RequestParam defaultValue |
| page=3 | page=3 |
| page=0 | HTTP 400 vì miền giá trị |
| page=abc | HTTP 400 vì type conversion |
| Không có sort | sort=createdAt |
| sort=title | sort=title |
| sort=unknown | HTTP 400 vì whitelist |
| Không có includeArchived | Không áp dụng filter, archiveFilterProvided=false |
| includeArchived=false | Giữ explicit false |
| includeArchived=true | Giữ explicit true |
| Header X-Mode thiếu | mode=standard |
| Cookie theme thiếu | theme=system |
| POST /books body thiếu | HTTP 400 vì @RequestBody required |
| JSON field title thiếu | HTTP 400 vì @NotBlank |
| JSON title có whitespace | HTTP 400 vì @NotBlank |
| JSON copies thiếu | copies=1 theo create policy |
| JSON copies=null | copies=1 theo create policy minh họa |
| JSON copies=0 | HTTP 400 vì @Positive |
| JSON published=false | Giữ explicit false |
| JSON published thiếu | published=false theo create policy |
| PATCH {} | Giữ dữ liệu hiện tại theo contract |
| PATCH {"displayName":null} | Xóa field hoặc lỗi, theo contract |
| PATCH {"tags":[]} | Xóa hết tags hoặc giữ tập rỗng theo contract |
| JSON malformed | Lỗi đọc body, thường 400 |
| Content-Type sai | Có thể 415 tùy consumes và converters |

Tập test này quan trọng hơn việc chỉ kiểm tra một request mà client gửi đầy đủ mọi field. Lỗi “optional bị coi là required”, “0 bị coi là missing” và “PATCH xóa nhầm field” thường không xuất hiện trong happy path.

## 14. Những lỗi phổ biến

**Lỗi 1 — Dùng int/boolean cho optional field không có default.** Primitive không chứa null; khi binding vắng mặt có thể lỗi hoặc làm mất trạng thái thứ ba. Dùng Integer/Boolean/Optional khi cần biểu diễn absence.

**Lỗi 2 — Dùng default để che dữ liệu sai kiểu.** page=abc là lỗi parse, không phải “thiếu page”; size=-1 là giá trị đã được gửi, không phải missing. Dùng 400 theo contract.

**Lỗi 3 — Coi false và 0 là “người dùng không nhập”.** Cả hai là giá trị hợp lệ trong nhiều domain và PATCH. Đừng dùng if (active) hoặc if (count != 0) làm phép kiểm tra presence.

**Lỗi 4 — Dùng @PathVariable(required=false) mà không thêm URL pattern tương ứng.** Annotation không tự biến /items/{id} thành /items. Route phải được khai báo rõ.

**Lỗi 5 — Tưởng @RequestBody(required=false) sẽ bỏ qua JSON sai cú pháp.** Nó cho phép trường hợp body không tồn tại; dữ liệu có nhưng sai vẫn cần error handling.

**Lỗi 6 — Đặt @Positive nhưng nghĩ nó buộc field có mặt.** Với null, @Positive thường không fail; kết hợp @NotNull nếu field bắt buộc.

**Lỗi 7 — Dùng cùng DTO defaults cho CREATE và PATCH.** CREATE có thể hợp lý khi thiếu published thì dùng false; PATCH thiếu published thường nghĩa giữ nguyên. Cần hợp đồng và DTO riêng khi semantics khác nhau.

**Lỗi 8 — Không phân biệt field thiếu với explicit null.** Với JSON DTO nullable đơn giản, cả hai có thể thành null. Nếu cần presence semantics, dùng JsonNode hoặc representation tương ứng.

**Lỗi 9 — Đặt default ở nhiều tầng mâu thuẫn.** Annotation, DTO, service và database cùng chọn default khác nhau có thể gây inconsistency. Chọn nguồn chân lý.

**Lỗi 10 — Không bảo vệ giá trị sort/filter do client gửi.** Optional không đồng nghĩa tin tưởng. Dùng whitelist, giới hạn length, range và validation; không nối chuỗi tùy ý vào SQL.

**Lỗi 11 — Dùng giá trị mặc định thiếu an toàn.** Thiếu role/tenant/auth token không được default thành quyền cao hoặc một identity tùy tiện. Dùng security context và deny-by-default.

**Lỗi 12 — Chỉ test các input hợp lệ có đủ field.** Cần test absent, empty, whitespace, null, false, zero, sai kiểu, sai miền và duplicate parameter khi liên quan.

**Lỗi 13 — Giả định mọi code Spring MVC dùng được nguyên trong WebFlux.** Các annotation có thể giống nhau, nhưng form/body/multipart và reactive handling khác. Xác nhận web stack trước khi sửa.

**Lỗi 14 — Không cập nhật tài liệu khi thay default.** Client có thể phụ thuộc vào giá trị mặc định hiện tại; đổi default có thể là thay đổi hành vi dù endpoint không đổi.

## 15. Bảo mật và độ tin cậy của default

Các trường hợp nhạy cảm phải được xét cẩn trọng:

- Thiếu authentication token phải là unauthenticated, không được tự gán một token demo.
- Thiếu tenantId không được chọn tenant khác nếu không dựa trên authenticated principal và policy server.
- Thiếu quyền thao tác không được mặc định là quyền admin.
- API chuyển tiền không nên mặc định amount/currency một cách che lỗi client.
- Không dùng query string để xác thực danh tính khi đã có security context.
- Với PUT/PATCH, không gán default làm thay đổi dữ liệu mà client không yêu cầu.
- Khi validation lỗi, không log toàn bộ mật khẩu/token hoặc dữ liệu cá nhân nhạy cảm trong error message.

Một default tốt là default **được thiết kế và được công khai**, không phải fallback vô điều kiện mỗi khi code thấy null.

## 16. Tài liệu hóa bằng OpenAPI và quy trình thiết kế

Với mỗi request field, ghi rõ:

1. Tên và vị trí: query, path, header, cookie, form, multipart hay JSON body.
2. Kiểu: String, Integer, Boolean, enum, date, object, array...
3. Có bắt buộc không?
4. Vắng mặt thì dùng default, giữ nguyên, hay trả lỗi?
5. Có cho phép JSON null không, và null khác missing như thế nào?
6. Empty string, blank, 0, false, [] được xử lý thế nào?
7. Giới hạn: min/max/length/pattern/whitelist.
8. Sai kiểu hoặc giá trị ngoài miền trả status/error code gì?
9. CREATE/PUT/PATCH có dùng cùng semantics hay không?
10. Client cũ có bị ảnh hưởng khi thay default không?

OpenAPI có required, nullable, default và constraints để mô tả hợp đồng, nhưng tài liệu không thay thế validation runtime. Tạo test cho các trạng thái quan trọng và giữ tài liệu nhất quán với code.

Một quy trình triển khai hữu ích:

~~~text
Xác định nguồn request
  -> Liệt kê missing/empty/null/false/0/[] có thể gặp
  -> Chốt nghiệp vụ cho mỗi trạng thái
  -> Chọn kiểu Java/DTO/presence representation
  -> Đặt default ở đúng tầng
  -> Cài validation và error mapping
  -> Test absent, empty, invalid, explicit values
  -> Kiểm chứng bảo mật và compatibility
  -> Công bố contract
~~~

## 17. Tự kiểm tra kiến thức

**Câu 1. @RequestParam(defaultValue="1") có biến page=0 thành 1 không?**  
Không. 0 là giá trị được gửi. Nếu không hợp lệ, cần trả lỗi hoặc xử lý theo contract, chứ default không tự chạy.

**Câu 2. required=false String và Optional<String> có giống nhau hoàn toàn không?**  
Không. Một bên thường dùng null, bên kia dùng Optional.empty cho absence; các quy tắc conversion/blank và normalize vẫn cần được định nghĩa.

**Câu 3. @RequestBody(required=false) có cho phép JSON malformed không?**  
Không. Nó cho phép thiếu body theo hợp đồng; có body sai cú pháp vẫn là lỗi.

**Câu 4. Vì sao @Positive Integer copies vẫn cho missing copies?**  
Vì null thường hợp lệ với @Positive. Nếu field bắt buộc, thêm @NotNull; nếu optional, service có thể áp dụng default.

**Câu 5. JSON {"active":false} và {} có giống nhau khi PATCH không?**  
Không nhất thiết. false là giá trị explicit; missing thường nghĩa không thay đổi. DTO presence-aware sẽ giúp giữ sự khác biệt.

**Câu 6. Có nên đặt default cho tenant/role dựa trên query string do client gửi không?**  
Không nên tạo default không an toàn. Nguồn danh tính/ủy quyền phải đến từ security context và policy server.

**Câu 7. @PathVariable(required=false) có tự thêm route /items bên cạnh /items/{id} không?**  
Không. Cần khai báo route tương ứng.

**Câu 8. Vì sao cần cả MockMvc và WebTestClient trong chương trình học?**  
Chúng kiểm thử HTTP binding ở hai stack khác nhau: MockMvc cho Servlet MVC, WebTestClient cho WebFlux reactive. Chúng không tự chứng minh toàn bộ proxy/network environment, nên cần integration test khi phù hợp.

## 18. Ghi nhớ

**Missing là câu hỏi dữ liệu có hiện diện hay không; default là quyết định ứng dụng muốn làm gì khi không có dữ liệu; validation là quyết định dữ liệu có được chấp nhận hay không.** Không nên gộp ba câu hỏi đó thành một điều kiện kiểm tra null.

Trong Spring Boot:

- @RequestParam(defaultValue=...) là cách khai báo default cho query/header cơ bản; với @RequestParam, missing/empty có thể kích hoạt default.
- required=false cùng Integer, Boolean hoặc Optional biểu diễn optional input rõ ràng hơn primitive không có default.
- @RequestBody đọc toàn bộ body; missing body khác missing JSON field. Java DTO thông thường có thể không phân biệt JSON missing và explicit null.
- @Valid với Bean Validation bảo vệ constraints; @Positive không buộc dữ liệu có mặt, @NotBlank chặn null/empty/blank.
- CREATE có thể áp dụng default cho missing field, trong khi PATCH phải bảo toàn presence semantics để tránh xóa nhầm.
- Giá trị 0, false và collection rỗng là những giá trị có nghĩa, không phải sentinel cho sự thiếu dữ liệu.
- API có default quan trọng phải có tài liệu, test missing/empty/invalid và chính sách bảo mật phù hợp.

Khi xác định rõ hành vi của mọi trạng thái dữ liệu ở HTTP boundary, ứng dụng sẽ dễ dự đoán hơn, giảm lỗi request binding và tránh những cập nhật sai do hiểu nhầm một giá trị bị thiếu.

## 19. Tài liệu tham khảo

- Spring MVC — @RequestParam: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring MVC — @RequestBody: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring WebFlux — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring WebFlux — @RequestParam: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html
- Spring Boot — Validation: https://docs.spring.io/spring-boot/reference/io/validation.html
- Jakarta Bean Validation — Specification: https://jakarta.ee/specifications/bean-validation/
- IETF RFC 7396 — JSON Merge Patch: https://www.rfc-editor.org/rfc/rfc7396
- IETF RFC 6902 — JSON Patch: https://www.rfc-editor.org/rfc/rfc6902

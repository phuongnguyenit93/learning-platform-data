# Jackson và cấu hình ánh xạ dữ liệu phù hợp với phiên bản Spring

## 1. Tại sao chủ đề này quan trọng?

Trong một API Spring MVC, controller thường nhận dữ liệu JSON bằng `@RequestBody` và trả JSON thông qua `@ResponseBody`, `@RestController` hoặc `ResponseEntity`. Spring MVC không tự biến JSON thành Java object bằng cách so từng key với từng field của controller. Nó ủy quyền việc đọc/ghi **HTTP message body** cho một `HttpMessageConverter`, thường là converter tích hợp **Jackson**.

Jackson giải quyết ánh xạ (*data mapping*) giữa biểu diễn JSON và object Java: tên trường, constructor, record, ngày giờ, enum, null, quan hệ object lồng nhau, serializer/deserializer riêng. Spring thêm lớp tích hợp giúp chọn converter theo HTTP `Content-Type`/`Accept` và cấu hình mapper thông qua bean, properties hoặc cấu hình MVC.

Điều cần đặc biệt lưu ý khi nâng cấp: **Spring Framework 6.x / Spring Boot 3.x chủ yếu dùng Jackson 2**, còn **Spring Framework 7.x / Spring Boot 4.x mặc định chuyển sang Jackson 3**. Không thể bê nguyên imports, builder customizer và mọi property cũ sang phiên bản mới.

Bài tập trung vào **Spring MVC Servlet stack**, các mốc phiên bản, cơ chế truyền JSON, lựa chọn cấu hình và cách bảo đảm hợp đồng API bằng kiểm thử. Spring WebFlux dùng codec/reactive stack khác; không áp dụng máy móc toàn bộ `HttpMessageConverter` của MVC cho WebFlux.

## 2. Chuỗi xử lý JSON từ request đến response

Giả sử client gửi:

```http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"book_title":"Spring MVC","published_on":"2026-10-01"}
```

Luồng cơ bản trong Spring MVC:

```text
HTTP request
     |
DispatcherServlet chọn @PostMapping("/api/books")
     |
@RequestBody BookRequest
     |
RequestResponseBodyMethodProcessor
     |
HttpMessageConverter chọn theo media type + kiểu Java
     |
Jackson JSON converter -> Jackson mapper đọc JSON
     |
BookRequest Java object -> controller
     |
BookResponse hoặc ResponseEntity<BookResponse>
     |
Jackson mapper ghi JSON
     |
HTTP response: Content-Type: application/json
```

Các thành phần có vai trò khác nhau:

- `@RequestBody` yêu cầu giải mã request body thành kiểu Java của tham số. Thường dùng cho JSON API.
- `@ResponseBody` đánh dấu giá trị trả về để ghi trực tiếp vào response body. `@RestController` có ý nghĩa tương đương `@Controller` kết hợp `@ResponseBody` ở cấp class.
- `ResponseEntity<T>` cho phép chủ động status, headers, body; nó không tự chọn format JSON.
- `HttpMessageConverter` quyết định khả năng đọc/ghi theo media type và Java type. Spring MVC có nhiều converter cho string, byte array, JSON, XML... tùy classpath/cấu hình.
- **Jackson mapper** đọc token JSON, khởi tạo object, chuyển dữ liệu, áp dụng annotation/custom serializer; chiều ngược lại viết object thành JSON.

Khác biệt cần phân biệt:

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| HTTP `Content-Type` | Định dạng của **body yêu cầu** | `application/json` |
| HTTP `Accept` | Định dạng **phản hồi mà client chấp nhận** | `application/json` |
| Jackson JSON mapper | Quy tắc JSON ↔ Java | `@JsonProperty("book_title")` |
| Bean Validation | Kiểm tra ràng buộc sau khi đọc DTO | `@Valid`, `@NotBlank` |
| Service/business logic | Kiểm tra dữ liệu theo trạng thái hệ thống | Mã sách đã tồn tại chưa? |
| Database mapping | Chuyển Java entity ↔ dữ liệu lưu trữ | JPA/Hibernate ORM |

**Jackson khác Hibernate ORM và khác Hibernate Validator**. Không dùng Jackson annotation thay cho authorization, kiểm tra nghiệp vụ hay constraint database.

## 3. Ma trận phiên bản Spring, Jackson và API cấu hình

| Nền tảng thường gặp | Thế hệ Jackson mặc định/ưu tiên | Kiểu mapper | JSON converter trong MVC | Hướng tùy chỉnh thường dùng |
| --- | --- | --- | --- | --- |
| Spring Framework 5.x + Boot 2.x | Jackson 2 | `com.fasterxml.jackson.databind.ObjectMapper` | `MappingJackson2HttpMessageConverter` | `spring.jackson.*`, `Jackson2ObjectMapperBuilderCustomizer`; nhiều API Jakarta vẫn ở `javax.*` |
| Spring Framework 6.0–6.2 + Boot 3.0–3.5 | Jackson 2 | `com.fasterxml.jackson.databind.ObjectMapper` | `MappingJackson2HttpMessageConverter` | `spring.jackson.*`, `Jackson2ObjectMapperBuilderCustomizer`, Jackson 2 modules |
| Spring Framework 7.0+ + Boot 4.0+ | Jackson 3 **ưu tiên mặc định** | `tools.jackson.databind.json.JsonMapper` | `JacksonJsonHttpMessageConverter` | `spring.jackson.*` theo schema Boot 4, `JsonMapperBuilderCustomizer`, Jackson 3 modules |
| Boot 4.x trong giai đoạn chuyển đổi | Có thể bật hỗ trợ Jackson 2 deprecated | `com.fasterxml.jackson.databind.ObjectMapper` cho đường legacy | Converter Jackson 2 nếu được cài/cấu hình thích hợp | Module `spring-boot-jackson2`, namespace cấu hình `spring.jackson2.*` |

Phiên bản tương thích **do BOM và dependency tree thực tế quyết định**; các khoảng trong bảng là thế hệ phát hành thông dụng, không bảo đảm mọi project không override phụ thuộc đều có đúng bản đó.

Những mốc cần nhớ:

1. **Boot 3 / Spring 6:** mã Java JSON điển hình import `com.fasterxml.jackson.databind.ObjectMapper`; customizer là `org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer`.
2. **Boot 4 / Spring 7:** chuyển phần lớn dependency group/package sang `tools.jackson`; mapper được Spring Boot cấu hình thường là `JsonMapper`, và customizer là `org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer`.
3. **Ngoại lệ package:** Jackson annotation phổ biến như `@JsonProperty`, `@JsonAlias`, `@JsonInclude`, `@JsonTypeInfo` vẫn thuộc `com.fasterxml.jackson.annotation`. Không tự đổi chúng thành `tools.jackson.annotation`.
4. `MappingJackson2HttpMessageConverter` và `Jackson2ObjectMapperBuilder` là cách tích hợp Jackson 2; **không lấy làm cấu hình mặc định cho hệ thống Jackson 3 mới**. Spring Framework 7 vẫn có hỗ trợ Jackson 2 deprecated như bước đệm nâng cấp.
5. Spring Boot 4 có `spring.jackson.use-jackson2-defaults=true` để kéo cấu hình mặc định Jackson 3 gần với hành vi Jackson 2 trong Boot 3; đây là **chế độ tương thích defaults**, không có nghĩa framework đã quay lại sử dụng thư viện Jackson 2.
6. Trong Boot 4, nếu chủ động giữ Jackson 2, dùng cấu hình `spring.jackson2.*` với module tương thích deprecated. Các property mới cho JSON reader/writer như `spring.jackson.json.read.*`, `spring.jackson.json.write.*` cần được kiểm tra theo tài liệu Boot 4 khi nâng cấp.
7. Một số API của Spring MVC dành cho **cấu hình danh sách converter** cũng đổi giữa Framework 6.2 và 7.0; kiểm tra đúng overload của `WebMvcConfigurer` trước khi sao chép ví dụ từ tài liệu.

**Quy tắc nâng cấp:** phân loại đoạn code là Jackson annotations, Jackson databind/parser, Spring MVC converter hay Spring Boot auto-configuration rồi đối chiếu **đúng major version của từng lớp**. Đừng coi thay một import là đủ.

## 4. Jackson annotation nào giải quyết bài toán nào?

Những annotation sau có tác dụng khi mapper tương ứng được kích hoạt qua Spring MVC hoặc gọi mapper trực tiếp.

| Annotation | Công dụng | Lưu ý |
| --- | --- | --- |
| `@JsonProperty("external_name")` | Đặt tên thuộc tính trong JSON độc lập với tên Java | Có tác động đến serialization/deserialization tùy nơi đặt |
| `@JsonAlias({"oldName"})` | Chấp nhận tên khác **khi đọc JSON** | Khi ghi response vẫn dùng tên chính, không tự phát ra mọi alias |
| `@JsonIgnore` | Bỏ qua một thuộc tính khỏi mapping theo ngữ cảnh annotation | Không thay cho phân quyền hoặc chiến lược DTO |
| `@JsonIgnoreProperties(ignoreUnknown=true)` | Bỏ qua JSON key không biết trên kiểu được chú thích | Có thể che giấu client gửi field sai chính tả |
| `@JsonInclude(Include.NON_NULL)` | Không ghi property có Java value `null` | Khác với `NON_EMPTY`, `NON_DEFAULT`; không làm input bắt buộc |
| `@JsonFormat(pattern="yyyy-MM-dd")` | Định dạng ngày khi đọc/ghi nếu kiểu và module hỗ trợ | Test timezone, locale và format theo contract |
| `@JsonPropertyOrder` | Điều khiển thứ tự field được ghi | Không nên lấy thứ tự JSON key làm contract trừ khi có yêu cầu thật |
| `@JsonCreator` | Chọn constructor/factory phù hợp để tạo object | Hữu ích với immutable types/constructors đặc biệt |
| `@JsonValue` | Giá trị đại diện khi serialize enum/value object | Cần xem tác động lên deserialization tương ứng |
| `@JsonView` | Chọn nhóm thuộc tính theo view trên các endpoint có cấu hình view | Không phải authorization layer; kiểm thử default inclusion |
| `@JsonTypeInfo` | Ghi/đọc thông tin polymorphic type | Cực kỳ thận trọng với type id và các subtype được phép |

Ví dụ Java records:

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

record CreateAuthorRequest(
        @JsonProperty("full_name")
        @JsonAlias({"name", "authorName"})
        String fullName) {
}

@JsonInclude(JsonInclude.Include.NON_NULL)
record AuthorResponse(
        @JsonProperty("full_name") String fullName,
        String middleName) {
}
```

Với request JSON `{"authorName":"An"}`, Jackson có thể bind thành `CreateAuthorRequest("An")`. Khi trả `new AuthorResponse("An", null)`, response là object có `"full_name":"An"` và **không có `middleName`** nếu mapper dùng đúng annotation. `@JsonAlias` dùng cho backward-compatible input; nó không sinh `"authorName"` trong response.

**Đừng mặc định rằng chỉ cần gắn `@JsonIgnore` lên password của một entity là đủ bảo vệ API.** Có thể tồn tại endpoint khác serialize entity bằng kiểu/view/mixin khác. DTO response chỉ chứa trường được phép công bố là lựa chọn rõ ràng hơn.

## 5. Ví dụ hoàn chỉnh cho Spring Boot 3.x / Spring Framework 6.x

Phần này là một mini REST API có thể chạy trên Java 17+ trong dự án Spring Boot **3.x** sử dụng Spring MVC và Jackson **2**. Không dùng đoạn này như project Boot 4 chưa được chuyển đổi: phụ thuộc, imports và mapping defaults đã khác.

### 5.1. Dependency

Ví dụ `build.gradle` **fragment** khi dự án đã có plugin Spring Boot, dependency management, repositories và Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` trong dòng Boot 3 thường kéo `spring-boot-starter-json` và Jackson 2. Để dùng `LocalDate`, Jackson Java Time hỗ trợ qua module JSR-310 đi cùng starter được Boot cấu hình. Không tự tạo một `ObjectMapper` trần bỏ qua module mặc định.

### 5.2. Source runnable

Tạo **`src/main/java/demo/jackson/JacksonDemoApplication.java`**:

```java
package demo.jackson;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.LocalDate;
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
public class JacksonDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JacksonDemoApplication.class, args);
    }
}

record BookRequest(
        @JsonProperty("book_title") String title,
        @JsonProperty("published_on")
        @JsonAlias({"publication_date"})
        @JsonFormat(pattern = "yyyy-MM-dd") LocalDate publishedOn,
        String note) {
}

@JsonInclude(JsonInclude.Include.NON_NULL)
record BookResponse(
        String id,
        @JsonProperty("book_title") String title,
        @JsonProperty("published_on")
        @JsonFormat(pattern = "yyyy-MM-dd") LocalDate publishedOn,
        String note) {
}

@RestController
@RequestMapping("/api/books")
class BookController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(@RequestBody BookRequest body) {
        BookResponse result = new BookResponse(
                "bk-1", body.title(), body.publishedOn(), body.note());
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    BookResponse get(@PathVariable String id) {
        return new BookResponse(
                id, "Spring MVC", LocalDate.of(2026, 10, 1), null);
    }
}
```

Đây là **một tệp Java biên dịch hợp lệ khi có classpath Boot 3**, vì chỉ class `JacksonDemoApplication` là `public`; record/controller còn lại package-private. Đưa vào package `demo.jackson` để component scan của `@SpringBootApplication` nhận controller.

Controller này cố ý không dùng database hoặc validation. Nó cho thấy rõ ánh xạ JSON:

- `@JsonProperty("book_title")` giữ contract JSON ổn định dù Java accessor là `title()`.
- `@JsonAlias("publication_date")` chấp nhận tên cũ của input, trong khi response giữ key `published_on`.
- `LocalDate` được đọc/ghi ở dạng ISO ngày theo `@JsonFormat(pattern = "yyyy-MM-dd")`; input sai ngày có thể gây lỗi convert.
- `@JsonInclude(NON_NULL)` áp dụng cho `BookResponse`, nên khi `note=null` response **bỏ hẳn trường note**, không trả `"note":null`.
- `POST` trả 201, `GET` trả 200. Hành vi này không liên quan đến việc persist thực sự; ID `bk-1` là giá trị demo.

### 5.3. Chạy và quan sát HTTP

Khởi động ứng dụng qua wrapper Gradle của dự án:

```bash
./gradlew bootRun
```

Yêu cầu POST sử dụng tên JSON chính:

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"book_title":"Spring MVC","published_on":"2026-10-01"}'
```

Kết quả thông thường:

```http
HTTP/1.1 201
Content-Type: application/json

{"id":"bk-1","book_title":"Spring MVC","published_on":"2026-10-01"}
```

Header thực tế như charset, content length, date có thể khác theo server. **Thứ tự key trong JSON không thuộc contract** của ví dụ. Nội dung JSON trên thể hiện tập thuộc tính mong đợi.

Yêu cầu với alias cũ:

```bash
curl -sS -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"book_title":"Spring MVC","publication_date":"2026-10-01"}'
```

Response vẫn trả key chuẩn `published_on`, không trả `publication_date`:

```json
{"id":"bk-1","book_title":"Spring MVC","published_on":"2026-10-01"}
```

Yêu cầu GET:

```bash
curl -sS 'http://localhost:8080/api/books/bk-9'
```

Body dự kiến:

```json
{"id":"bk-9","book_title":"Spring MVC","published_on":"2026-10-01"}
```

Lệnh curl trong phần này giả định dự án chạy cổng 8080 và không có filter/security/proxy thay đổi giao thức. Nếu thêm request validation, error handling hoặc JSON config, kết quả cần được kiểm thử lại.

## 6. Tùy chỉnh Jackson trong Spring Boot 3

Có ba mức lựa chọn: **annotation trên DTO**, **properties của Boot**, và **bean customizer**. Nên bắt đầu ở mức nhỏ nhất đáp ứng yêu cầu, tránh thay thế toàn bộ auto-configuration một cách không cần thiết.

### 6.1. Cấu hình bằng application properties

Trong Boot 3, ví dụ:

```properties
# Chỉ áp dụng cho mapper được Boot auto-configure trong dòng Boot 3.
spring.jackson.default-property-inclusion=non_null
spring.jackson.deserialization.fail-on-unknown-properties=true
spring.jackson.serialization.indent-output=false
spring.jackson.property-naming-strategy=SNAKE_CASE
```

Các thuộc tính minh họa này là **lựa chọn tùy chỉnh**; không tự thêm tất cả vào ứng dụng mẫu, vì đổi naming strategy toàn cục có thể tác động tới những DTO khác. Nếu đã gắn `@JsonProperty` tường minh, tên ngoài của các field đó nên được kiểm thử riêng khi phối hợp global naming strategy.

- `default-property-inclusion=non_null` bỏ properties null trong response của những đối tượng dùng cấu hình chung; `@JsonInclude` trên class/field có thể ghi đè tại phạm vi hẹp.
- `deserialization.fail-on-unknown-properties=true` làm JSON chứa key lạ gây lỗi thay vì lặng lẽ bỏ qua, trừ khi type có quy tắc riêng như `@JsonIgnoreProperties(ignoreUnknown=true)`.
- `serialization.indent-output` điều khiển pretty printing; nội dung JSON có thêm khoảng trắng nhưng không đổi mô hình dữ liệu.
- `property-naming-strategy=SNAKE_CASE` chuyển ví dụ Java `publishedOn` sang JSON `published_on` khi không có tên tường minh khác.

**Chính sách unknown fields là quyết định hợp đồng API**: strict giúp bắt lỗi gõ sai; permissive giúp client/server tiến hóa ít ma sát hơn. Không có một thiết lập luôn tối ưu. Cần kết hợp validation vì một field sai chính tả có thể trở thành `null` và validation sẽ kiểm tra độ bắt buộc nếu được kích hoạt.

### 6.2. Tùy chỉnh builder trong Boot 3

Tạo `src/main/java/demo/jackson/Jackson2Config.java`:

```java
package demo.jackson;

import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class Jackson2Config {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer prettyJson() {
        return builder -> builder.indentOutput(true);
    }
}
```

Phần này chạy với API Boot 3; nó đặt indent output cho mapper do builder Boot tạo. Nếu cùng lúc khai báo property `spring.jackson.serialization.indent-output=false`, **thứ tự cấu hình của customizer** quyết định kết quả cuối; đừng để hai nguồn thiết lập trái nhau. Khi cần ổn định, chọn một nguồn cấu hình và viết test xác minh.

Với logic serializer/deserializer phức tạp, cân nhắc **Jackson `Module`** để đăng ký serializer cho một kiểu cụ thể. Đừng tạo `new ObjectMapper()` ngẫu nhiên ở mọi controller/service: các mapper đó có thể thiếu Java Time, naming policy, inclusion policy và custom modules đang được Boot quản lý.

### 6.3. Khi nào cần trực tiếp `ObjectMapper`?

Trong service hoặc batch job nội bộ của Boot 3:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

class JsonExportService {
    private final ObjectMapper mapper;

    JsonExportService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    String toJson(Object value) throws Exception {
        return mapper.writeValueAsString(value);
    }
}
```

Đây là class Java minh họa DI; không phải controller độc lập. Inject mapper đã cấu hình từ Spring giúp quy tắc JSON nhất quán với MVC. Tuy nhiên, cần hiểu rằng converter thực tế có thể dùng mapper riêng nếu ai đó thay đổi cấu hình `HttpMessageConverters`; vì vậy **không giả định bean `ObjectMapper` được inject chắc chắn là mapper đang xử lý HTTP** khi ứng dụng có custom converter.

Jackson 2 `ObjectMapper` có thể cấu hình trước khi bắt đầu sử dụng; khi được chia sẻ trong ứng dụng, tránh sửa cấu hình runtime đồng thời với serialization từ nhiều thread. Cách an toàn là cấu hình một lần, sau đó reuse mapper hoặc reader/writer chuyên dụng.

## 7. Cấu hình message converter: thứ tự, media type và tác động của Spring Boot

Ở Spring MVC, `RequestMappingHandlerAdapter` có danh sách `HttpMessageConverter` để xử lý body. Không phải một request có thể được đọc bởi **bất kỳ** converter nào; Spring xét content type, target type và converter support.

Ví dụ API chấp nhận và trả JSON:

```java
@PostMapping(
    path = "/payload",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE)
public Payload handle(@RequestBody Payload payload) {
    return payload;
}
```

Đây là method minh họa trong `@RestController`, `Payload` và `MediaType` cần định nghĩa/import. Với một converter phù hợp:

- `Content-Type: application/json` cùng JSON hợp lệ → deserialization chạy.
- `Content-Type: text/plain` với body JSON có thể dẫn đến **415 Unsupported Media Type** vì `consumes` và converter.
- `Accept: application/xml` khi chỉ có JSON được công bố/có thể ghi có thể dẫn đến **406 Not Acceptable**.
- JSON malformed hoặc không ánh xạ được kiểu Java có thể gây `HttpMessageNotReadableException` và thường là **400 Bad Request**.
- JSON đọc thành object thành công nhưng vi phạm `@Valid`/`@Validated` là bước validation riêng; exception thường khác lỗi parse.

Trong **Framework 6.2**, `WebMvcConfigurer#configureMessageConverters(List<HttpMessageConverter<?>>)` dùng để cấu hình danh sách tùy biến (thay mặc định tùy cơ chế); `extendMessageConverters(List<HttpMessageConverter<?>>)` thích hợp khi chỉ muốn chỉnh converter đã đăng ký. Boot cũng bổ sung các converter beans do auto-configuration phát hiện. Cần chọn cách cấu hình thống nhất, kiểm thử tất cả media types thật sự được hỗ trợ.

Trong **Framework 7.x**, tài liệu chính thức trình bày cấu hình thông qua `configureMessageConverters(HttpMessageConverters.ServerBuilder)` và các converter Jackson 3. Ví dụ Framework 7 không nên copy nguyên chữ ký `List<HttpMessageConverter<?>>` từ dự án 6.2 nếu API đã đổi.

Không được tự động áp đặt converter JSON toàn cục cho mọi endpoint XML, form, byte array hoặc file download. Thứ tự converter có thể ảnh hưởng content negotiation và khả năng đọc/ghi.

## 8. Spring Boot 4 và Spring Framework 7: dùng Jackson 3

### 8.1. Package và dependency thay đổi

Khác biệt điển hình:

```text
Boot 3 / Jackson 2
  implementation 'org.springframework.boot:spring-boot-starter-web'
  com.fasterxml.jackson.databind.ObjectMapper
  MappingJackson2HttpMessageConverter
  Jackson2ObjectMapperBuilderCustomizer

Boot 4 / Jackson 3
  Spring MVC web starter theo BOM/starter Boot 4
  tools.jackson.databind.json.JsonMapper
  JacksonJsonHttpMessageConverter
  JsonMapperBuilderCustomizer
```

Đây là **bảng gợi nhớ**, không phải đoạn Gradle copy nguyên. Spring Boot 4 tách module/starter theo thế hệ mới; kiểm tra dependency hiện có qua chính BOM/guide của Boot 4 trước khi bổ sung các starter riêng.

Đối với Jackson 3, core/databind modules nằm dưới Maven group `tools.jackson` (ví dụ `tools.jackson.core:jackson-databind`). **Jackson annotations vẫn từ `com.fasterxml.jackson.annotation`**. Những loại thuộc Jackson databind như mapper, module, serializer/deserializer có thể đổi package hoặc tên API. Đừng sửa hàng loạt tất cả `com.fasterxml.jackson.*` bằng tìm–thay một cách cơ học.

### 8.2. Java config kiểu Jackson 3 của Boot 4

Trong project **Boot 4 / Jackson 3** đã có Spring MVC và auto-configuration, có thể tạo file **`src/main/java/demo/jackson/Jackson3Config.java`**:

```java
package demo.jackson;

import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.SerializationFeature;

@Configuration
class Jackson3Config {

    @Bean
    JsonMapperBuilderCustomizer prettyJson() {
        return builder -> builder.enable(
                SerializationFeature.INDENT_OUTPUT);
    }
}
```

Đây là ví dụ **dành riêng Boot 4**; không biên dịch trong Boot 3 vì `JsonMapperBuilderCustomizer` và `tools.jackson.databind.SerializationFeature` của Jackson 3 không có sẵn ở baseline cũ. Spring Boot sẽ áp dụng customizer lên builder mapper được auto-configure.

Trong một dự án Framework 7 sử dụng cấu hình MVC trực tiếp, đường JSON converter chuẩn là `JacksonJsonHttpMessageConverter` với `JsonMapper`. Ví dụ minh họa độc lập về mapper:

```java
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.SerializationFeature;

JsonMapper mapper = JsonMapper.builder()
        .enable(SerializationFeature.INDENT_OUTPUT)
        .build();
```

Đây chỉ là **fragment Jackson 3** có import/biến theo ngữ cảnh. Mapper này chưa tự đăng ký vào Spring MVC; khi viết Boot application, ưu tiên builder/customizer hoặc converter mechanism do Boot cung cấp.

### 8.3. Cấu hình properties trong Boot 4

Ví dụ dùng `application.properties` cho **Jackson 3 ở Boot 4**:

```properties
spring.jackson.serialization.indent-output=true
spring.jackson.use-jackson2-defaults=false
spring.jackson.find-and-add-modules=true
```

Trong Boot 4, các feature JSON reader/writer chuyên biệt được nhóm dưới `spring.jackson.json.read.*` và `spring.jackson.json.write.*`. Không sao chép `spring.jackson.read.*` hoặc `spring.jackson.write.*` cũ mà không kiểm tra loại feature, tên property và mapping tương đương. Một số tùy chọn không còn ánh xạ 1:1 và cần customizer.

Đối với migration từng bước:

```properties
# Tạm căn chỉnh defaults của Jackson 3 với các defaults mà Boot 3 dùng
# cho Jackson 2; KHÔNG chuyển runtime quay lại Jackson 2.
spring.jackson.use-jackson2-defaults=true
```

Chỉ đặt cờ này khi có bằng chứng hợp đồng JSON của ứng dụng phụ thuộc defaults cũ và bạn cần giai đoạn chuyển đổi. Mục tiêu cuối là có **tests mô tả contract JSON tường minh** để không phụ thuộc quá nhiều vào defaults của framework.

### 8.4. Khi cần Jackson 2 trong Boot 4

Spring Boot 4 cung cấp đường chuyển tiếp deprecated cho Jackson 2:

```groovy
// Chỉ trong dự án Boot 4 đang cần tương thích Jackson 2 tạm thời.
dependencies {
    implementation 'org.springframework.boot:spring-boot-jackson2'
}
```

Các setting của đường Jackson 2 được đặt trong namespace `spring.jackson2.*`, **không tự trộn** với mapper Jackson 3 `spring.jackson.*`. Bản thân việc thêm module compatibility không chứng minh rằng HTTP converter đang dùng mapper Jackson 2; cần xem classpath, auto-configuration, converter được chọn và test ở endpoint.

Nếu code có API dependency yêu cầu Jackson 2 ở một module, cân nhắc giữ mapper Jackson 2 **cục bộ ở ranh giới module** trong khi HTTP JSON của ứng dụng tiếp tục dùng Jackson 3; hai thế hệ có thể tồn tại đồng thời nhưng quy tắc ánh xạ không được phép mơ hồ. Hỗ trợ legacy là bước đệm có kế hoạch loại bỏ.

## 9. Đổi cấu hình của Jackson 2 sang Jackson 3 mà không phá JSON contract

Trước migration, lập **một bộ JSON contract samples** gồm input/output và status code đã được client sử dụng. Chạy chúng trên hệ thống hiện tại rồi mới nâng thư viện.

| Mối quan tâm | Boot 3 / Jackson 2 | Boot 4 / Jackson 3 |
| --- | --- | --- |
| Mapper runtime | `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.json.JsonMapper` |
| Spring Boot customizer | `Jackson2ObjectMapperBuilderCustomizer` | `JsonMapperBuilderCustomizer` |
| Spring converter | `MappingJackson2HttpMessageConverter` | `JacksonJsonHttpMessageConverter` |
| Module/serializer custom | Jackson 2 `Module`, `JsonSerializer`, `JsonDeserializer` | Jackson 3 module/serializer API; xem thay đổi tên/signature |
| Cấu hình core properties | `spring.jackson.*` theo Boot 3 | `spring.jackson.*` theo Boot 4, một số nhánh property đổi tên |
| JSON reader/writer feature settings | Nhánh `spring.jackson.read.*`/`write.*` ở các bản cũ hỗ trợ | `spring.jackson.json.read.*`/`json.write.*` cho các JSON feature tương ứng |
| Giữ hành vi mặc định gần bản cũ | Defaults do Boot 3 đặt | `spring.jackson.use-jackson2-defaults=true` (chỉ là hỗ trợ migration) |
| Tạm giữ Jackson 2 khi lên Boot 4 | Sẵn có ở baseline | `spring-boot-jackson2` deprecated và `spring.jackson2.*` |
| Jackson annotations chung | `com.fasterxml.jackson.annotation.*` | Vẫn `com.fasterxml.jackson.annotation.*` đối với annotations chung |

Kiểm thử hồi quy tối thiểu nên bao gồm:

1. **Tên field:** `camelCase`, `snake_case`, `@JsonProperty` và alias nhận vào từ client cũ.
2. **Null / field vắng:** response bỏ null hay trả null? Input thiếu field tương ứng có được chấp nhận không? Test riêng sự khác nhau giữa “vắng”, “null” và “giá trị rỗng”.
3. **Ngày giờ:** `LocalDate`, `LocalDateTime`, `OffsetDateTime` và timezone; ngày ISO, timestamp epoch, milliseconds precision. Không áp một format date-time cho mọi loại.
4. **Enum:** tên enum, viết hoa/thường, giá trị không nhận diện, giá trị JSON tùy chỉnh bằng `@JsonCreator`/`@JsonValue`.
5. **Number:** `long` lớn, `BigDecimal`, số thực, rounding/scale khi có ý nghĩa nghiệp vụ; tránh chuyển ID lớn sang `double` ở client JavaScript.
6. **Unknown fields:** có từ chối unknown field không? Có alias/backward compatibility không? Xác nhận lỗi HTTP.
7. **Object nested/collections:** cách xử lý generics, null elements, immutable constructor/record.
8. **Polymorphic data:** whitelist type hợp lệ; không cho payload tự chọn Java class tùy ý.
9. **Error response:** malformed JSON, mismatched types, unsupported media type, validation errors và cấu trúc `ProblemDetail`/API error contract.
10. **Mixed dependencies:** xác nhận chỉ có mapper/converter nào xử lý một endpoint và không vô tình bỏ module hỗ trợ Java Time.

Migration an toàn dựa trên **tests về kết quả**. Chỉ assert `ObjectMapper` tồn tại trong context là chưa chứng minh Spring MVC đang dùng đúng mapper ấy.

## 10. Một số vấn đề ánh xạ hay gây lỗi

### 10.1. Ngày giờ với `java.time`

Trong Boot 3, `spring-boot-starter-json` thường cung cấp và Boot đăng ký module Java Time. Nếu bạn tạo một `new ObjectMapper()` riêng, `LocalDate` có thể không được đọc/ghi như kỳ vọng do thiếu `JavaTimeModule` hoặc cấu hình timestamp. Ví dụ Jackson 2 thuần, **không nhất thiết cần trong Boot 3**:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule());
```

Đây là **fragment** yêu cầu dependency `jackson-datatype-jsr310` tương ứng. Trong Boot application, tốt hơn inject mapper đã được auto-configure để không mất các quy tắc chung. Trong Jackson 3, hệ sinh thái module và mặc định thay đổi; không chép imports `com.fasterxml.jackson.datatype.jsr310` sang code 3.x một cách mặc định.

Phân biệt:

- `LocalDate` biểu diễn ngày **không có giờ, timezone**; pattern `yyyy-MM-dd` phù hợp cho ngày lịch.
- `LocalDateTime` có ngày và giờ **nhưng không có offset/timezone**; không đủ để xác định thời điểm tuyệt đối.
- `OffsetDateTime` và `Instant` đại diện điểm thời gian có ngữ nghĩa offset/UTC; lựa chọn format ISO 8601 và chính sách chuyển timezone rõ ràng.
- Thay đổi global timezone không tự làm mọi kiểu `java.time` có cùng semantics. Viết test với offset khác nhau.

### 10.2. Cấu trúc object và record

Jackson có thể dùng default constructor + setters, constructor được đánh dấu `@JsonCreator`, record canonical constructor và các cơ chế introspection khác tùy phiên bản. Với Java 17 record, tên record components là một phần của hợp đồng cấu trúc trong Java; `@JsonProperty` giúp cố định tên JSON.

Nếu DTO chỉ có constructor nhiều tham số và mapper không tìm được cách tạo object, lỗi thường có thông tin “no Creators” hoặc “cannot construct instance”. Cách xử lý: dùng DTO/record phù hợp, khai báo `@JsonCreator`/`@JsonProperty` khi cần, hoặc tạo deserializer cụ thể. Tránh bật “field visibility ANY” toàn cục chỉ để sửa một DTO, vì có thể làm lộ thêm fields của kiểu khác.

### 10.3. Không biết field trong input

Hai chính sách:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

// Chấp nhận field lạ cho đúng kiểu DTO này:
@JsonIgnoreProperties(ignoreUnknown = true)
record FlexibleRequest(String name) {}
```

Hoặc, với Boot 3 muốn strict **toàn cục**:

```properties
spring.jackson.deserialization.fail-on-unknown-properties=true
```

Không đặt đồng thời hai lựa chọn trái nhau trên cùng DTO mà không hiểu precedence. Nếu client gửi `{"nmae":"An"}` thay vì `{"name":"An"}`, strict mapping sẽ bắt lỗi sớm; permissive mapping có thể tạo object với `name=null`. Bean Validation (nếu có và được kích hoạt) cần kiểm tra riêng tên bắt buộc.

### 10.4. Serialization không có nghĩa là validation

`@JsonProperty(required=true)` không phải công tắc thay thế mọi ràng buộc `@NotNull`/`@NotBlank`. Hành vi của `required` phụ thuộc nơi khai báo property/creator và Jackson version; không sử dụng nó làm lớp kiểm tra dữ liệu nghiệp vụ duy nhất.

Với API:

```java
@PostMapping
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateRequest body) {
    return ResponseEntity.status(201).build();
}
```

Đây là **method fragment**: cần import `jakarta.validation.Valid` và khai báo `CreateRequest` với constraints. Quy trình là Jackson **deserialize** trước; khi có object, Bean Validation mới kiểm tra ràng buộc. Lỗi body không parse được và lỗi constraint không hợp lệ là **hai nhóm lỗi khác nhau**, nên handler cần xử lý khác nhau.

### 10.5. Không nên serialize JPA Entity trực tiếp

Entity có thể có lazy proxies, quan hệ hai chiều, field nội bộ, dữ liệu nhạy cảm hoặc vòng tham chiếu. Jackson tự serialize graph quá rộng có thể gây recursion, extra SQL queries/N+1 hoặc vô tình lộ thông tin. DTO response giúp giới hạn contract:

```java
record UserView(long id, String displayName) {}
```

Không xem `@JsonIgnore` trên entity là kiến trúc API đầy đủ; ở boundary HTTP, convert entity sang DTO rồi serialize DTO thường dễ kiểm soát hơn.

## 11. Cách Spring MVC chọn mapper và các lỗi HTTP

| Hiện tượng | Đường gây lỗi điển hình | Điều cần kiểm tra |
| --- | --- | --- |
| `415 Unsupported Media Type` | `Content-Type`/`consumes` không tương thích | Client gửi JSON với `application/json` hay text/plain? |
| `406 Not Acceptable` | Không có converter/media type đáp ứng `Accept` | `produces`, converter và Accept header |
| `400 Bad Request` với JSON sai cú pháp | Jackson không deserialize được | JSON malformed, kiểu field, enum/date format |
| `400 Bad Request` sau khi DTO được đọc | Validation không đạt | `@Valid`/`@Validated`, `BindingResult` và error handler |
| `500 Internal Server Error` khi ghi JSON | Serialization failed lúc trả response | Vòng tham chiếu, lazy-loading, serializer, cấu hình module |
| Response field biến mất | `@JsonIgnore` hoặc inclusion policy | `@JsonInclude`, MixIn, `JsonView`, null/empty |
| Response tên field khác trước | Naming strategy / annotation / migration | `@JsonProperty`, `SNAKE_CASE`, schema contract |
| JSON date thành timestamp/array | Module/format/defaults khác | `JavaTimeModule`, mapper, `@JsonFormat`, Jackson generation |
| Chỉ một endpoint có JSON khác | Converter/mapper hoặc view riêng | Converter registry, custom `ObjectMapper`, annotation scope |

**Status trên chỉ là đường đi thông dụng**. `@ControllerAdvice`, Spring Security, proxy, filter hoặc custom exception resolver có thể thay đổi kết quả cuối. Chỉ nhìn HTTP 400 không xác định được JSON parse hay validation đã hỏng.

Ví dụ REST exception handler (đặt trong project Boot 3 mẫu, chỉ xử lý malformed JSON):

```java
package demo.jackson;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class JsonErrorAdvice {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<Map<String, String>> malformedJson(
            HttpMessageNotReadableException ex) {

        // Không gửi ex.getMostSpecificCause().getMessage() cho client.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_JSON"));
    }
}
```

Đây là class hoàn chỉnh nhưng cần Spring context của ứng dụng. Nếu bật advice này, test JSON không hợp lệ có thể assert `{"code":"INVALID_JSON"}`. Trong hệ thống production, cân nhắc `ProblemDetail` và chiến lược lỗi thống nhất để client phân biệt invalid JSON, invalid field, unauthorized và conflict.

## 12. Kiểm thử ánh xạ JSON với MockMvc

Sau khi thêm starter test như phần 5, tạo **`src/test/java/demo/jackson/JacksonDemoApplicationTests.java`**:

```java
package demo.jackson;

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
class JacksonDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void readsCanonicalNamesAndOmitsNullInResponse() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"book_title":"Spring MVC",
                     "published_on":"2026-10-01"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("bk-1"))
            .andExpect(jsonPath("$.book_title").value("Spring MVC"))
            .andExpect(jsonPath("$.published_on").value("2026-10-01"))
            .andExpect(jsonPath("$.note").doesNotExist());
    }

    @Test
    void acceptsAliasButWritesCanonicalName() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"book_title":"Spring MVC",
                     "publication_date":"2026-10-01"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.published_on").value("2026-10-01"))
            .andExpect(jsonPath("$.publication_date").doesNotExist());
    }

    @Test
    void returnsKnownJsonPropertyNames() throws Exception {
        mvc.perform(get("/api/books/bk-9")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("bk-9"))
            .andExpect(jsonPath("$.book_title").value("Spring MVC"))
            .andExpect(jsonPath("$.published_on").value("2026-10-01"))
            .andExpect(jsonPath("$.note").doesNotExist());
    }

    @Test
    void rejectsMalformedDate() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"book_title":"Spring MVC",
                     "published_on":"not-a-date"}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsNonJsonContentType() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.TEXT_PLAIN)
                .content("""
                    {"book_title":"Spring MVC"}
                    """))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

Chạy:

```bash
./gradlew test
```

Kỳ vọng năm method test **pass** trên dự án Boot 3 có JSON converter mặc định và không có Security hoặc error customization thay đổi status. Các kiểm tra dùng JSONPath nên không phụ thuộc thứ tự field/whitespace.

Nếu muốn kiểm tra strict unknown-field, thêm property `spring.jackson.deserialization.fail-on-unknown-properties=true` vào profile test, rồi gửi body chứa `"unexpected_field":1` và assert 400. Nếu muốn kiểm tra permissive mapping, tạo DTO riêng có `@JsonIgnoreProperties(ignoreUnknown=true)` và test response. Đừng dựa vào một default Jackson không được kiểm soát khi nâng major version.

### Test chính mapper so với test HTTP

| Loại test | Bao phủ | Không bao phủ |
| --- | --- | --- |
| Test `ObjectMapper` trực tiếp trong Boot 3 | Serialization/deserialization, annotation, module | MVC chọn converter, Content-Type, Accept, controller mapping |
| Test `JsonMapper` trực tiếp trong Boot 4 | Jackson 3 mapping rules | Converter/Boot MVC integration |
| `@JsonTest` (Spring Boot test slice) | Cấu hình JSON slice và component mapping | Toàn bộ MVC filter chain/endpoints |
| `@WebMvcTest` + `MockMvc` | MVC controllers, converter, selected web infrastructure | Full application/service/database nếu không thêm |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Web application context và request/response handling | Reverse proxy, browser, network transport thật |

Để xác nhận nâng cấp Boot 3 → Boot 4, kết hợp mapper-level và HTTP contract tests. Một unit test serializing một DTO bằng mapper tự tạo có thể **pass** nhưng production controller lại dùng mapper/converter khác.

## 13. Những rủi ro khi tùy biến sâu

### Thay `ObjectMapper` bean

Trong Boot 3, nếu tự khai báo bean `ObjectMapper` thay bean được Boot auto-configure, hãy chắc chắn đăng ký module và policies quan trọng (Java Time, Java Optional, parameter names, inclusion/naming, custom serializers). Boot không thể mặc nhiên áp dụng mọi điều chỉnh của bạn lên mapper đã tạo thủ công. Tương tự, Boot 4 có auto-configured `JsonMapper`/builder riêng; đừng đưa Jackson 2 bean và mong mọi converter Jackson 3 sử dụng nó.

### Polymorphic deserialization

Tránh bật **default typing quá rộng** cho payload JSON đến từ client không đáng tin, đặc biệt kiểu metadata cho phép chọn subtype bằng Java class name. Nếu cần đa hình, khai báo tập subtype hợp lệ và dùng `@JsonTypeInfo`/`@JsonSubTypes` một cách giới hạn, kết hợp validation/authorization. Review CVE và cập nhật Jackson/Spring theo bản vá phù hợp.

### Date and decimal fidelity

Chọn kiểu Java phù hợp dữ liệu:

- Số tiền: `BigDecimal` thay vì `double` nếu cần tính toán thập phân chính xác và scale/rounding có kiểm soát.
- ID 64-bit: kiểm thử với client JavaScript để tránh mất precision khi JSON number vượt giới hạn an toàn của JS; nếu cần, thiết kế contract ID dạng string.
- Thời điểm: `Instant`/`OffsetDateTime` với format ISO và timezone rõ ràng; không gửi `LocalDateTime` rồi bắt client tự đoán múi giờ.
- Enum và name casing: quy định chặt chẽ contract ở boundary, kiểm thử giá trị lạ và migration.

### Tách request DTO và response DTO

DTO dành cho input có thể cho phép alias, nhưng output nên dùng tên canonical. Không tái sử dụng entity đa mục đích nếu field bên trong có thể bị serialize ra ngoài. Đừng coi `@JsonView` hay `@JsonIgnore` là điểm kiểm soát quyền truy cập duy nhất.

## 14. Quy trình nâng cấp Jackson và Spring có kiểm chứng

1. **Chốt phiên bản thật:** kiểm tra `spring-webmvc`, Spring Boot BOM, `jackson-databind`, các Jackson modules và dependency tree. Với Gradle, dùng `./gradlew dependencies --configuration runtimeClasspath` và `dependencyInsight` cho dependency quan trọng.
2. **Chốt HTTP JSON contract:** lưu mẫu request/response của endpoint quan trọng; định nghĩa status, Content-Type, Accept, tên field, null, date, enum và unknown-field policy.
3. **Kiểm kê custom code:** tìm `ObjectMapper`, `JsonMapper`, `Jackson2ObjectMapperBuilderCustomizer`, converter custom, serializer/deserializer, mixin, Java Time, `@JsonProperty`, `@JsonView` và `spring.jackson.*`.
4. **Chọn đường migration:** lên Boot 4 và Jackson 3 là hướng ưu tiên; nếu module không tương thích, dùng Jackson 2 compatibility có thời hạn với phạm vi rõ ràng.
5. **Chuyển imports/API đúng loại:** phần lớn databind/parser sang `tools.jackson`; giữ annotation imports `com.fasterxml.jackson.annotation`; đổi Spring customizer/converter cho đúng phiên bản.
6. **Kiểm tra cấu hình properties:** xem các property reader/writer được đổi nhánh; quyết định có tạm bật `use-jackson2-defaults` không; bỏ các customizer không còn tác dụng.
7. **Chạy unit và integration tests:** xác minh Jackson mapper trực tiếp **và** pipeline HTTP thông qua MVC với cả positive/negative cases.
8. **Kiểm tra lỗi, bảo mật và observability:** không leak rejected input nhạy cảm; kiểm tra content negotiation, 400/406/415/500, monitoring và logging sau deploy.
9. **Gỡ compatibility:** khi hợp đồng đã ổn định và mọi thư viện liên quan hỗ trợ Jackson 3, loại bỏ đường Jackson 2 deprecated và tests chỉ phục vụ workaround.

Một mốc nâng cấp coi là đạt khi client quan trọng nhận **cùng hợp đồng dữ liệu** hoặc một thay đổi API versioned đã được công bố, không phải chỉ khi build xanh.

## 15. Bài tập tự kiểm tra

1. Controller Boot 3 khai báo `@PostMapping(consumes="application/json")` với `@RequestBody BookRequest`. Client gửi `Content-Type: text/plain` nhưng body là JSON hợp lệ: bước nào từ chối và HTTP status dự kiến là gì?
2. Một record Java có accessor `bookTitle()` nhưng API phải trả key `book_title`. Hãy so sánh `@JsonProperty` trên field/record component với global `SNAKE_CASE`. Cách nào phù hợp nếu chỉ một DTO có tên đặc biệt?
3. Từ input `{"publication_date":"2026-10-01"}` sang `BookRequest` và response `BookResponse`, hãy giải thích tại sao `@JsonAlias` chấp nhận tên input cũ nhưng output luôn dùng `published_on`.
4. Client gửi ngày `2026-02-30`; vì sao có thể lỗi **deserialization** trước khi Bean Validation chạy? Kiểm tra test bằng `MockMvc`.
5. Sau nâng cấp Boot 3 → Boot 4, code import `com.fasterxml.jackson.databind.ObjectMapper` và customizer Jackson 2 không tác động HTTP response mới. Hãy chỉ ra thay đổi Jackson 3 và cách xác nhận converter thực tế.
6. Khi đặt `spring.jackson.use-jackson2-defaults=true` trong Boot 4, ứng dụng đã thật sự chạy Jackson 2 chưa? Kiểm tra khái niệm **defaults compatibility** với **library/runtime generation**.
7. Một endpoint serialize entity có quan hệ hai chiều và field `passwordHash`. Hãy đề xuất response DTO và test đảm bảo JSON không lộ field nội bộ.
8. Lập ma trận contract tests cho enum, `BigDecimal`, null/vắng field, unknown JSON property và `OffsetDateTime` ở Boot 3/4. Ghi rõ hành vi muốn giữ và thay đổi được chủ động chấp nhận.
9. Viết một customizer tương đương ở Boot 3 (Jackson2ObjectMapperBuilderCustomizer) và Boot 4 (JsonMapperBuilderCustomizer), rồi chứng minh trong test HTTP đầu ra được ảnh hưởng.

## 16. Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): `MappingJackson2HttpMessageConverter`, Jackson 2 `ObjectMapper`.
- [Spring Framework 6.2 — Message Converters Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html): `WebMvcConfigurer`, converter list cho dòng Framework 6.
- [Spring Framework 7 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): converter Jackson 3 sử dụng `JsonMapper`.
- [Spring Framework 7 — MVC Converter Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/message-converters.html): `HttpMessageConverters.ServerBuilder` và converter Jackson 3.
- [Spring MVC — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): resolver, message converter và validation.
- [Spring Boot 3 — JSON](https://docs.spring.io/spring-boot/3.4/reference/features/json.html): auto-configure Jackson 2 và custom serializer/deserializer.
- [Spring Boot 4 — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): Jackson 3, `JsonMapper` và cấu hình mới.
- [Spring Boot 4 — MVC Configuration](https://docs.spring.io/spring-boot/how-to/spring-mvc.html): customizer/configuration properties Jackson 3.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): thay đổi Jackson 3, package, customizers, Jackson 2 compatibility và properties.
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): Jackson 3 mặc định ưu tiên và Jackson 2 deprecated.
- [Introducing Jackson 3 support in Spring — Spring Blog](https://spring.io/blog/2025/10/07/introducing-jackson-3-support-in-spring/): mục đích migration, compatibility defaults và ví dụ customizer Boot 3/4.

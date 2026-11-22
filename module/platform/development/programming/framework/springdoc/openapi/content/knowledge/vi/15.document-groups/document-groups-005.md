# Điều kiện về media type hoặc header khi được hỗ trợ

Springdoc có thể tạo nhiều tài liệu OpenAPI độc lập từ cùng một ứng dụng Spring Boot. Ngoài việc lọc theo package hoặc URL path, `GroupedOpenApi` còn hỗ trợ lọc operation theo media type request (`consumes`), media type response (`produces`) và điều kiện header của Spring MVC mapping (`headers`). Những bộ lọc này hữu ích khi một hệ thống có API JSON/XML, endpoint tải file hoặc các phiên bản API được chọn bằng request header.

Điều cần phân biệt là bộ lọc group chỉ quyết định operation nào xuất hiện trong tài liệu được tạo. Nó không tự thêm converter, thay đổi response, tạo header hoặc bảo vệ endpoint. Hành vi HTTP thực tế vẫn do mapping, controller, message converter và cấu hình bảo mật của ứng dụng quyết định.

## 1. Ba loại điều kiện lọc

`GroupedOpenApi.Builder` cung cấp các phương thức sau trong những phiên bản Springdoc hỗ trợ chúng:

| Phương thức | Điều kiện được kiểm tra | Thuộc tính mapping Spring thường tương ứng |
| --- | --- | --- |
| `consumesToMatch(...)` | Media type mà endpoint nhận trong request body | `consumes` |
| `producesToMatch(...)` | Media type mà endpoint có thể trả về | `produces` |
| `headersToMatch(...)` | Điều kiện trên HTTP request header | `headers` |

Ví dụ, `consumes = "application/json"` cho biết endpoint nhận JSON; `produces = "application/xml"` cho biết endpoint có thể trả XML; `headers = "X-API-VERSION=v2"` giới hạn mapping vào request có header `X-API-VERSION` mang giá trị `v2`.

Các phương thức lọc này bổ sung cho những bộ lọc quen thuộc như `pathsToMatch`, `pathsToExclude`, `packagesToScan` và `packagesToExclude`. Khi kết hợp nhiều chiều lọc, hãy xem chúng như các điều kiện thu hẹp phạm vi group: operation cần phù hợp với path/package và các điều kiện media type/header đã cấu hình. Nếu có nhiều giá trị trong cùng một loại điều kiện, kiểm tra kết quả group của phiên bản Springdoc đang dùng để xác nhận cách chúng được kết hợp.

## 2. Phân biệt `consumes`, `produces` và `headers`

Spring MVC cung cấp các thuộc tính này trên `@RequestMapping` và các annotation rút gọn như `@GetMapping`, `@PostMapping`:

- `consumes` khớp với `Content-Type` của request, tức định dạng body client gửi lên.
- `produces` khớp với `Accept` của request và mô tả định dạng response mà handler có thể tạo.
- `headers` khớp với các header request khác theo biểu thức được khai báo.

Ví dụ:

```java
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse create(@RequestBody CreateBookRequest request) {
    // Xử lý JSON request và trả JSON response.
    return new BookResponse(1L, request.title());
}
```

Trong trường hợp này, `consumesToMatch("application/json")` lọc theo định dạng request; `producesToMatch("application/json")` lọc theo định dạng response. Không dùng `headersToMatch("Content-Type=application/json")` hoặc `headersToMatch("Accept=application/json")` để thay thế hai bộ lọc media type chuyên biệt. Spring MVC đã cung cấp `consumes` và `produces` cho hai header này.

## 3. Lọc group theo media type response bằng `producesToMatch`

Giả sử cùng một hệ thống có endpoint trả JSON và endpoint trả XML. Có thể tách tài liệu thành hai group để người tích hợp chỉ xem các operation có representation phù hợp.

Controller JSON:

```java
@RestController
@RequestMapping(path = "/api/books", produces = MediaType.APPLICATION_JSON_VALUE)
class JsonBookController {

    @GetMapping
    List<BookResponse> list() {
        return List.of(new BookResponse(1L, "Spring Boot căn bản"));
    }
}
```

Controller XML:

```java
@RestController
@RequestMapping(path = "/api/books/export", produces = MediaType.APPLICATION_XML_VALUE)
class XmlBookController {

    @GetMapping
    BookXmlResponse export() {
        return new BookXmlResponse(1L, "Spring Boot căn bản");
    }
}
```

Khai báo group bằng Springdoc 2.x:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi jsonApi() {
        return GroupedOpenApi.builder()
            .group("books-json")
            .pathsToMatch("/api/**")
            .producesToMatch("application/json")
            .build();
    }

    @Bean
    GroupedOpenApi xmlApi() {
        return GroupedOpenApi.builder()
            .group("books-xml")
            .pathsToMatch("/api/**")
            .producesToMatch("application/xml")
            .build();
    }
}
```

Group `books-json` chỉ tập trung vào operation có mapping `produces` phù hợp với JSON; `books-xml` tập trung vào operation có mapping XML. Ví dụ giả định các controller và converter đã được cấu hình để thực sự trả các định dạng tương ứng.

Nếu một operation khai báo hỗ trợ cả JSON và XML, operation đó có thể phù hợp với cả hai group và xuất hiện trong cả hai tài liệu. Group không có nghĩa mỗi operation chỉ được thuộc một tài liệu.

## 4. Lọc group theo media type request bằng `consumesToMatch`

`consumesToMatch` hữu ích khi ứng dụng có nhiều loại endpoint nhận dữ liệu khác nhau, ví dụ JSON, XML hoặc multipart upload.

Ví dụ endpoint nhận file:

```java
@RestController
@RequestMapping("/api/imports")
class ImportController {

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<Void> upload(
            @RequestPart("file") MultipartFile file) {
        return ResponseEntity.accepted().build();
    }
}
```

Tạo group chỉ dành cho operation nhận multipart:

```java
@Bean
GroupedOpenApi uploadApi() {
    return GroupedOpenApi.builder()
        .group("file-uploads")
        .pathsToMatch("/api/**")
        .consumesToMatch(MediaType.MULTIPART_FORM_DATA_VALUE)
        .build();
}
```

Có thể tạo group khác cho operation nhận JSON:

```java
@Bean
GroupedOpenApi jsonRequestApi() {
    return GroupedOpenApi.builder()
        .group("json-requests")
        .pathsToMatch("/api/**")
        .consumesToMatch(MediaType.APPLICATION_JSON_VALUE)
        .build();
}
```

`consumesToMatch` lọc dựa trên điều kiện `consumes` của mapping. Nếu endpoint không khai báo `consumes`, Spring MVC có thể vẫn đọc JSON nhờ message converter, nhưng mapping không công bố điều kiện media type tường minh để bộ lọc này dựa vào. Khi cần phân nhóm theo định dạng request, hãy khai báo `consumes` rõ ràng và kiểm tra tài liệu được sinh.

## 5. Lọc group theo header bằng `headersToMatch`

Header mapping phù hợp khi API chọn handler theo một header tùy chỉnh, chẳng hạn phiên bản API hoặc chế độ tương thích. Spring MVC hỗ trợ các biểu thức header trong `headers` của `@RequestMapping`.

Một số dạng biểu thức thường gặp:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `X-API-VERSION` | Request phải có header này |
| `X-API-VERSION=v2` | Header phải có giá trị `v2` |
| `X-API-VERSION!=v1` | Header phải có giá trị khác `v1` |
| `!X-API-VERSION` | Request không được có header này |

Ví dụ controller chỉ phục vụ phiên bản v2:

```java
@RestController
@RequestMapping(
    path = "/api/books",
    headers = "X-API-VERSION=v2"
)
class BooksV2Controller {

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    List<BookResponse> list(
            @RequestHeader("X-API-VERSION") String apiVersion) {
        return List.of(new BookResponse(1L, "Spring Boot căn bản"));
    }
}
```

Group tương ứng:

```java
@Bean
GroupedOpenApi booksV2Api() {
    return GroupedOpenApi.builder()
        .group("books-v2")
        .pathsToMatch("/api/books/**")
        .headersToMatch("X-API-VERSION=v2")
        .build();
}
```

Mapping `headers` quyết định request nào được Spring chọn vào controller này. `headersToMatch` giúp group tài liệu chọn operation có điều kiện header tương ứng. `@RequestHeader` trên tham số giúp controller đọc giá trị và Springdoc có thể mô tả header parameter cho người tích hợp.

Lưu ý: chỉ khai báo `@RequestHeader("X-API-VERSION")` trên tham số method không đồng nghĩa với mapping condition `headers = "X-API-VERSION=v2"`. Nếu không có điều kiện trên `@RequestMapping`, `headersToMatch("X-API-VERSION=v2")` không có mapping condition tương ứng để lọc. Ngược lại, mapping condition có thể ràng buộc header mà không tự động tạo một tham số OpenAPI rõ ràng trong mọi cấu hình; hãy kiểm tra `/v3/api-docs/{group}` và bổ sung metadata parameter nếu cần.

## 6. Không dùng `headersToMatch` để thay thế content negotiation

`Accept` và `Content-Type` là hai header đặc biệt đã được Spring MVC mô hình hóa bằng `produces` và `consumes`. Hãy chọn bộ lọc đúng:

| Nhu cầu | Mapping Spring | Bộ lọc group |
| --- | --- | --- |
| Chỉ tài liệu cho API nhận JSON | `consumes = "application/json"` | `consumesToMatch("application/json")` |
| Chỉ tài liệu cho API trả JSON | `produces = "application/json"` | `producesToMatch("application/json")` |
| Chỉ tài liệu cho API nhận multipart | `consumes = "multipart/form-data"` | `consumesToMatch("multipart/form-data")` |
| Chỉ tài liệu cho API yêu cầu header phiên bản v2 | `headers = "X-API-VERSION=v2"` | `headersToMatch("X-API-VERSION=v2")` |

Ví dụ, nếu client gửi `Accept: application/xml`, Spring content negotiation sẽ chọn representation XML khi handler hỗ trợ. `producesToMatch("application/xml")` lọc tài liệu theo điều kiện `produces` của mapping. Không cần khai báo `headersToMatch("Accept=application/xml")`.

Tương tự, `Content-Type: application/json` được đối chiếu với `consumes`; không cần dùng `headersToMatch("Content-Type=application/json")`.

## 7. Kết hợp nhiều điều kiện trong một group

Một group có thể kết hợp path, media type và header để thu hẹp phạm vi operation:

```java
@Bean
GroupedOpenApi partnerV2JsonApi() {
    return GroupedOpenApi.builder()
        .group("partner-v2-json")
        .pathsToMatch("/api/partner/**")
        .producesToMatch(MediaType.APPLICATION_JSON_VALUE)
        .consumesToMatch(MediaType.APPLICATION_JSON_VALUE)
        .headersToMatch("X-API-VERSION=v2")
        .build();
}
```

Group này hướng đến các operation trong path `/api/partner/**`, nhận JSON, trả JSON và có mapping header phiên bản v2. Nếu một operation không khai báo một điều kiện tương ứng hoặc không thỏa một trong các điều kiện lọc, nó có thể không xuất hiện trong group.

Không nên tạo group quá hẹp đến mức người dùng khó tìm tài liệu. Chỉ kết hợp nhiều điều kiện khi chúng thể hiện một ranh giới có ý nghĩa, chẳng hạn một hợp đồng đối tác cụ thể hoặc một nhóm endpoint có cùng định dạng trao đổi.

## 8. Cấu hình group bằng `application.properties`

Ngoài bean Java, Springdoc cho phép khai báo group trong cấu hình. Ví dụ:

```properties
springdoc.group-configs[0].group=books-json
springdoc.group-configs[0].paths-to-match=/api/**
springdoc.group-configs[0].produces-to-match=application/json

springdoc.group-configs[1].group=file-uploads
springdoc.group-configs[1].paths-to-match=/api/**
springdoc.group-configs[1].consumes-to-match=multipart/form-data

springdoc.group-configs[2].group=books-v2
springdoc.group-configs[2].paths-to-match=/api/books/**
springdoc.group-configs[2].headers-to-match=X-API-VERSION=v2
```

Tên property và khả năng hỗ trợ từng bộ lọc phụ thuộc phiên bản Springdoc đang sử dụng. Nếu IDE hoặc cấu hình của phiên bản hiện tại không nhận `headers-to-match`, hãy kiểm tra API `GroupedOpenApi` và metadata configuration của đúng phiên bản; có thể dùng bean Java nếu builder có phương thức tương ứng.

Không khai báo cùng một group bằng cả bean Java và `springdoc.group-configs` nếu không có chủ đích rõ ràng. Mỗi group cần tên duy nhất và cấu hình có thể bảo trì.

## 9. Truy cập tài liệu của từng group

Với group tên `books-json`, Springdoc thường phục vụ tài liệu JSON tại:

```text
/v3/api-docs/books-json
```

Tài liệu YAML của group có thể được truy cập tại:

```text
/v3/api-docs/books-json.yaml
```

Swagger UI có thể hiển thị danh sách tài liệu group được cấu hình. Có thể mở trực tiếp UI và chọn group cần xem; khi cấu hình danh sách URL riêng, tên group phải khớp với group name đã đăng ký.

Kiểm tra từng group độc lập:

1. Mở endpoint `/v3/api-docs/{group}`.
2. Xem danh sách `paths` và operation được đưa vào.
3. Kiểm tra `requestBody.content` và `responses.content` có đúng media type.
4. Kiểm tra header parameter được mô tả khi operation yêu cầu header.
5. So sánh các group để phát hiện operation bị thiếu hoặc xuất hiện ngoài dự kiến.

Group chỉ tạo tài liệu riêng; nó không tạo URL runtime mới cho controller. Nếu cùng một controller được đưa vào nhiều group, URL HTTP thực tế vẫn giữ nguyên.

## 10. Giới hạn và những trường hợp cần kiểm tra kỹ

Các bộ lọc media type/header dựa vào metadata mapping mà Springdoc có thể đọc. Một số tình huống cần kiểm tra với phiên bản và mô hình routing thực tế:

- **Mapping không khai báo `consumes` hoặc `produces`:** converter mặc định vẫn có thể xử lý JSON, nhưng bộ lọc dựa trên mapping có thể không nhận diện operation như một endpoint được khai báo rõ media type.
- **Header chỉ được đọc bằng `@RequestHeader`:** điều này không tạo điều kiện mapping cho `headersToMatch`; cần khai báo `headers` trên mapping nếu muốn lọc theo biểu thức header.
- **Functional endpoints hoặc custom handler:** cơ chế lọc có thể khác so với controller Spring MVC dùng `@RequestMapping`. Kiểm tra hỗ trợ của phiên bản Springdoc và kiểu endpoint.
- **Một mapping có nhiều media type:** operation có thể phù hợp với nhiều group. Kiểm tra tài liệu từng group thay vì giả định chúng loại trừ lẫn nhau.
- **Wildcard media type:** điều kiện như `application/*` hoặc `*/*` phụ thuộc cách so khớp của Spring/Springdoc; xác minh kết quả thực tế.
- **Mapping kế thừa từ cấp class và method:** Spring kết hợp điều kiện mapping ở hai cấp; kiểm tra điều kiện hiệu lực của handler.
- **Custom `OpenApiCustomizer` hoặc `OperationCustomizer`:** customizer có thể thay đổi tài liệu sau khi lọc. Kiểm tra thứ tự và kết quả cuối cùng của group.

Nếu group rỗng hoặc thiếu operation, hãy kiểm tra mapping condition trên controller trước, sau đó kiểm tra các bộ lọc group và cuối cùng là customizer. Đừng thêm annotation tài liệu tùy tiện để ép operation xuất hiện nếu mapping runtime không phản ánh điều kiện đó.

## 11. Phân biệt nhóm tài liệu với bảo mật và định tuyến

Group là cách tổ chức hợp đồng OpenAPI. Một group tên `internal-v2` không tự biến endpoint thành API nội bộ hoặc bảo vệ nó bằng xác thực. Tương tự, `headersToMatch` trong cấu hình group chỉ lọc operation trong tài liệu; điều kiện runtime phải được khai báo trên mapping Spring hoặc triển khai ở security/gateway.

| Cấu hình | Tác dụng |
| --- | --- |
| `GroupedOpenApi.headersToMatch(...)` | Chọn operation cho một tài liệu group |
| `@RequestMapping(headers = ...)` | Ràng buộc request nào khớp handler Spring MVC |
| `@RequestHeader` | Đọc giá trị header trong method argument và hỗ trợ mô tả parameter |
| Spring Security | Xác thực và phân quyền request |
| Gateway / reverse proxy | Có thể định tuyến, lọc hoặc áp dụng chính sách ở biên hệ thống |

Nếu header phiên bản được dùng để chọn API version, hãy bảo đảm mapping v1/v2 không xung đột, có tài liệu riêng và có kiểm thử request gửi đúng/sai header. Nếu header chỉ dùng để phân loại tài liệu mà không ràng buộc runtime, client có thể gọi operation trong điều kiện khác với nội dung group.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Group theo JSON không có operation mong muốn | Mapping không khai báo `produces` hoặc `consumes` phù hợp | Khai báo media type rõ trên mapping và kiểm tra lại group |
| Endpoint nhận JSON nhưng không vào group `consumes` | JSON được nhận nhờ converter mặc định nhưng mapping không có `consumes` | Thêm `consumes = application/json` nếu đó là hợp đồng thực tế |
| Group theo header rỗng | Chỉ có `@RequestHeader`, không có mapping `headers` | Thêm điều kiện header vào `@RequestMapping` nếu runtime cần ràng buộc |
| Group dùng `headersToMatch("Accept=...")` không đúng | Dùng header filter thay cho `produces` | Chuyển sang `producesToMatch` |
| Group dùng `headersToMatch("Content-Type=...")` không đúng | Dùng header filter thay cho `consumes` | Chuyển sang `consumesToMatch` |
| Operation xuất hiện trong nhiều group | Mapping hỗ trợ nhiều media type hoặc các filter group chồng lấp | Xác định rõ phạm vi group; overlap có thể là chủ đích |
| Group không tồn tại ở `/v3/api-docs/{group}` | Group name sai, bean chưa được tạo hoặc cấu hình group không được bind | Kiểm tra tên group và cấu hình Springdoc |
| Header parameter không xuất hiện trong tài liệu | Mapping condition không tự được mô tả như parameter ở cấu hình hiện tại | Thêm `@RequestHeader`/`@Parameter` và kiểm tra OpenAPI |
| Functional endpoint không được lọc như controller | Bộ lọc dựa trên metadata Spring MVC mapping không áp dụng tương tự | Kiểm tra hỗ trợ của phiên bản và dùng cơ chế customizer phù hợp |

## 13. Checklist cho group theo media type hoặc header

- [ ] Chọn đúng bộ lọc: `consumesToMatch`, `producesToMatch` hoặc `headersToMatch`.
- [ ] `consumes` của controller phản ánh `Content-Type` request thực tế.
- [ ] `produces` phản ánh representation mà endpoint thực sự có thể trả.
- [ ] Header tùy chỉnh được khai báo trong `@RequestMapping(headers = ...)` nếu cần lọc theo header condition.
- [ ] Không dùng `headersToMatch` để thay thế điều kiện `Accept`/`Content-Type` chuyên biệt.
- [ ] Kết hợp path/package filter để group có phạm vi rõ ràng.
- [ ] Kiểm tra các operation có nhiều media type và khả năng xuất hiện ở nhiều group.
- [ ] Xác minh phiên bản Springdoc hỗ trợ phương thức builder/property đang dùng.
- [ ] Kiểm tra từng tài liệu tại `/v3/api-docs/{group}` và Swagger UI.
- [ ] Không nhầm bộ lọc tài liệu với định tuyến, xác thực hoặc phân quyền runtime.

`consumesToMatch`, `producesToMatch` và `headersToMatch` giúp chia tài liệu OpenAPI theo cách một operation nhận dữ liệu, trả dữ liệu hoặc được chọn bằng header mapping. Khi mapping Spring thể hiện rõ các điều kiện runtime và group dùng đúng bộ lọc tương ứng, mỗi nhóm tài liệu sẽ phản ánh chính xác hơn hợp đồng dành cho từng loại client hoặc phiên bản API.

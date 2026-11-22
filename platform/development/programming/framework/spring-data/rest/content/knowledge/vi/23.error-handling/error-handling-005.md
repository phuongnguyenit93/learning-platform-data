# 406 Not Acceptable và 415 Unsupported Media Type khi Accept hoặc Content-Type không được hỗ trợ

## Mục tiêu

Spring Data REST tự động xuất bản Spring Data repositories thành REST resources. Khi client gọi một resource, server phải xử lý hai việc riêng biệt: chọn representation để trả về cho client và đọc representation trong request body. Hai việc này dùng hai HTTP header khác nhau:

- `Accept` mô tả những media type client có thể nhận ở response.
- `Content-Type` mô tả media type của request body client đang gửi.

Nếu client yêu cầu response representation mà resource không cung cấp, server có thể trả `406 Not Acceptable`. Nếu request body có định dạng không được method trên resource hỗ trợ, server có thể trả `415 Unsupported Media Type`. Xác định đúng header và đúng loại resource là bước đầu tiên để sửa lỗi.

## 1. Phân biệt Accept và Content-Type

| Header | Dùng cho | Ví dụ |
|---|---|---|
| `Accept` | Client thông báo định dạng response mong muốn | `Accept: application/hal+json` |
| `Content-Type` | Client khai báo định dạng request body | `Content-Type: application/json` |
| `Content-Encoding` | Client khai báo cách mã hóa/nén representation gửi lên | `Content-Encoding: gzip` |

Ví dụ khi tạo một người qua `POST /people`:

- `Content-Type: application/json` cho biết body là JSON để Spring đọc và chuyển thành domain object.
- `Accept: application/hal+json` cho biết client muốn nhận response dưới dạng HAL JSON.

Không dùng `Accept` để khai báo định dạng của body đang gửi. Cũng không dùng `Content-Type` để yêu cầu định dạng response.

Spring MVC mặc định kiểm tra header `Accept` để xác định media type của response. Spring Data REST dùng HAL làm representation hypermedia mặc định; các repository resources cũng hỗ trợ `application/json` theo tài liệu chính thức.

## 2. 406 Not Acceptable: response không đáp ứng Accept

Theo HTTP Semantics (RFC 9110, mục 15.5.7), `406 Not Acceptable` có nghĩa resource không có representation hiện tại phù hợp với các negotiation header client gửi và server không muốn cung cấp representation mặc định.

Trong Spring MVC, lỗi này thường liên quan đến `HttpMediaTypeNotAcceptableException`. Handler không thể tạo response phù hợp với media type mà client yêu cầu.

Ví dụ client chỉ chấp nhận XML:

```http
GET /people HTTP/1.1
Host: localhost:8080
Accept: application/xml
```

Nếu collection resource chỉ hỗ trợ JSON/HAL JSON, `application/xml` không phù hợp và request có thể nhận `406`.

Sửa request bằng media type được endpoint hỗ trợ:

```http
GET /people HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
```

Hoặc dùng `Accept: application/json` nếu client muốn JSON representation. Spring Data REST mặc định dùng HAL cho JSON representation; có thể kiểm tra `RepositoryRestConfiguration.useHalAsDefaultJsonMediaType()` khi cần hiểu hành vi này.

Lưu ý: body response rỗng sau một request thành công không tự động là 406. Với `PUT` và `DELETE`, Spring Data REST mặc định dùng sự hiện diện của `Accept` để quyết định có trả body hay không; cấu hình `setReturnBodyOnUpdate(...)` và `setReturnBodyOnDelete(...)` có thể thay đổi hành vi tương ứng. Hãy đọc status code và header `Location` trước khi kết luận request thất bại.

## 3. 415 Unsupported Media Type: request body không được hỗ trợ

Theo RFC 9110, mục 15.5.16, `415 Unsupported Media Type` cho biết server từ chối xử lý request vì nội dung có định dạng không được method trên resource đích hỗ trợ. Vấn đề có thể đến từ `Content-Type`, `Content-Encoding` hoặc việc server kiểm tra trực tiếp nội dung.

Trong Spring MVC, lỗi thường gắn với `HttpMediaTypeNotSupportedException` khi request handler không có khả năng đọc media type được client gửi. Điều này thường xảy ra với `POST`, `PUT` hoặc `PATCH`.

Ví dụ gửi XML vào collection resource không hỗ trợ XML:

```http
POST /people HTTP/1.1
Host: localhost:8080
Content-Type: application/xml
Accept: application/hal+json

<person><name>Ada</name></person>
```

Nếu resource chỉ hỗ trợ JSON, server có thể trả `415`. Gửi JSON thực sự và khai báo đúng media type:

```http
POST /people HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/hal+json

{"name":"Ada"}
```

Chỉ đổi header thành `application/json` trong khi body vẫn là XML không phải cách sửa đúng. Giá trị `Content-Type` phải mô tả chính xác định dạng body.

## 4. Media type được Spring Data REST hỗ trợ

Media type phụ thuộc loại resource và HTTP method. Không suy ra hợp đồng của một endpoint từ endpoint khác trong cùng ứng dụng.

| Resource | Method | Media type được tài liệu liệt kê |
|---|---|---|
| Collection | `GET` | `application/hal+json`, `application/json` |
| Collection | `POST` | `application/hal+json`, `application/json` |
| Item | `GET` | `application/hal+json`, `application/json` |
| Item | `PUT` | `application/hal+json`, `application/json` |
| Item | `PATCH` | `application/hal+json`, `application/json`, `application/patch+json`, `application/merge-patch+json` |
| Association | `GET` | `application/hal+json`, `application/json` |
| Association | `PUT` | `text/uri-list` |
| Association (collection association) | `POST` | `text/uri-list` |
| Search/query resource | `GET` | `application/hal+json`, `application/json` |

Các trường hợp quan trọng:

- `POST /people` tạo entity nên JSON body có thể dùng `Content-Type: application/json`.
- `PUT /people/1` thay thế trạng thái item; `PATCH /people/1` cập nhật một phần.
- `PATCH` có thể dùng JSON Patch (`application/patch+json`) hoặc JSON Merge Patch (`application/merge-patch+json`). Body phải đúng cấu trúc và semantics của media type tương ứng.
- `PUT /people/1/manager` liên kết resource được chỉ tới vào association. Request body là URI hoặc danh sách URI, vì vậy dùng `Content-Type: text/uri-list`.
- `POST` vào collection association thêm một phần tử mới và cũng dùng `text/uri-list`.
- `text/uri-list` không phải định dạng body thay thế cho JSON khi tạo entity ở collection resource.

Ví dụ association request:

```http
PUT /people/1/manager HTTP/1.1
Host: localhost:8080
Content-Type: text/uri-list

http://localhost:8080/managers/2
```

Path `/people/1/manager` chỉ là ví dụ. Tên association path phụ thuộc domain property và cấu hình export của repository.

Ma trận trên dựa trên tài liệu Spring Data REST hiện hành. Custom controller, custom converter, cấu hình repository export và phiên bản thư viện có thể thay đổi hành vi thực tế.

## 5. Ví dụ kiểm tra bằng cURL

Thay host, collection path và thuộc tính JSON theo ứng dụng của bạn.

### 5.1. GET collection với HAL JSON

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/people
```

Kỳ vọng: response thành công (thường là `200 OK`) với `Content-Type` tương thích HAL JSON.

### 5.2. Tạo 406 với Accept không hỗ trợ

```bash
curl -i -H "Accept: application/xml" http://localhost:8080/people
```

Kỳ vọng: `406 Not Acceptable` nếu endpoint không cung cấp XML. Sửa bằng:

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/people
```

### 5.3. POST entity bằng JSON

```bash
curl -i -X POST http://localhost:8080/people   -H "Content-Type: application/json"   -H "Accept: application/hal+json"   --data '{"name":"Ada"}'
```

Kỳ vọng: resource được tạo, thường là `201 Created`. Response body và header `Location` phụ thuộc hành vi endpoint và cấu hình.

### 5.4. Tạo 415 với Content-Type không hỗ trợ

```bash
curl -i -X POST http://localhost:8080/people   -H "Content-Type: application/xml"   -H "Accept: application/hal+json"   --data '<person><name>Ada</name></person>'
```

Kỳ vọng: `415 Unsupported Media Type` nếu collection resource không nhận XML. Sửa bằng cách gửi JSON thực sự như ví dụ 5.3.

### 5.5. PATCH bằng JSON Merge Patch

```bash
curl -i -X PATCH http://localhost:8080/people/1   -H "Content-Type: application/merge-patch+json"   -H "Accept: application/hal+json"   --data '{"name":"Ada Lovelace"}'
```

Dùng `application/merge-patch+json` khi body tuân theo JSON Merge Patch. Nếu dùng JSON Patch, khai báo `application/patch+json` và gửi mảng thao tác theo định dạng JSON Patch.

### 5.6. PUT association bằng URI list

```bash
curl -i -X PUT http://localhost:8080/people/1/manager   -H "Content-Type: text/uri-list"   --data 'http://localhost:8080/managers/2'
```

Nếu gửi JSON object vào association resource, request có thể nhận 415 dù JSON được hỗ trợ trên collection resource. Hai resource có hợp đồng media type khác nhau.

## 6. Quy trình chẩn đoán

1. **Thu thập request thực tế.** Ghi URL, method, `Accept`, `Content-Type`, `Content-Encoding` và body. Dùng `curl -v`, log HTTP client hoặc reverse proxy để xem header nào thực sự đến ứng dụng.
2. **Xác định resource.** Phân biệt collection, item, association, search/query resource và custom controller. Xem link từ API root hoặc response HAL để xác định URL resource.
3. **Nếu là 406, kiểm tra Accept.** So sánh từng media type client yêu cầu với media type response của method/resource. Thử `application/hal+json` để kiểm tra response HAL. Với GET không có body, đổi `Content-Type` không giải quyết negotiation response.
4. **Nếu là 415, kiểm tra Content-Type và body.** Xác nhận body thực tế đúng định dạng đã khai báo. JSON body cần JSON converter; XML cần converter và endpoint được cấu hình hỗ trợ XML. Kiểm tra cả `Content-Encoding` nếu request có nén.
5. **Kiểm tra association.** Nếu URL là association sub-resource, xem method có yêu cầu `text/uri-list` hay không. Đừng dùng JSON entity body cho thao tác liên kết URI.
6. **Kiểm tra custom mapping.** Với controller tự viết, xem `consumes` và `produces` trên `@RequestMapping`. `consumes` ràng buộc media type của request body; `produces` ràng buộc representation response.
7. **Kiểm tra message converters.** Spring MVC dùng `HttpMessageConverter` để đọc request body và ghi response. Kiểm tra converter đã đăng ký, loại Java, media type hỗ trợ và cấu hình `WebMvcConfigurer`.
8. **Đối chiếu phiên bản.** Kiểm tra phiên bản Spring Data REST và Spring Framework thực tế trong dependency tree; đọc tài liệu cùng phiên bản. Không giả định cấu hình của một phiên bản áp dụng nguyên vẹn cho phiên bản khác.
9. **Phân biệt status code.** `400 Bad Request` thường chỉ body không hợp lệ hoặc không parse được; `404 Not Found` chỉ resource/path không tồn tại; `405 Method Not Allowed` chỉ method không được hỗ trợ hoặc không export. Đổi media type không sửa được các lỗi này.

## 7. Cấu hình media type mặc định và content negotiation

Spring Data REST cung cấp `RepositoryRestConfiguration.setDefaultMediaType(...)` để chọn media type mặc định khi request không chỉ định rõ media type. Ví dụ cấu hình HAL JSON qua `RepositoryRestConfigurer`:

```java
@Configuration
class RestMediaTypeConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setDefaultMediaType(
                MediaType.parseMediaType("application/hal+json"));
    }
}
```

Các import cần thiết phụ thuộc package của phiên bản Spring Data REST đang dùng, gồm `Configuration`, `RepositoryRestConfigurer`, `RepositoryRestConfiguration`, `CorsRegistry` và `MediaType`.

Cấu hình default media type chỉ quyết định fallback khi request không chỉ định media type. Nó không tự bật XML, không làm một `Accept` tường minh nhưng không tương thích trở nên hợp lệ và không thay đổi hợp đồng `text/uri-list` của association resource.

Ở Spring MVC, có thể tùy chỉnh cách xác định response media type bằng `WebMvcConfigurer.configureContentNegotiation(ContentNegotiationConfigurer)`. Mặc định chỉ header `Accept` được kiểm tra. Việc khai báo alias hoặc extension mapping cho XML không tự đăng ký XML message converter và cũng không đảm bảo mọi endpoint có thể serialize/deserialize XML.

Với custom endpoint, có thể khai báo rõ hợp đồng:

```java
@PostMapping(
    path = "/imports",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ResponseEntity<ImportResult> importData(@RequestBody ImportRequest request) {
    // Handle the request.
}
```

Trong ví dụ, `consumes` mô tả request body phải là JSON; `produces` mô tả response representation. Cấu hình này dành cho controller do ứng dụng quản lý, không thay thế ma trận media type của Spring Data REST repository resources.

## 8. Kiểm thử 406 và 415 với MockMvc

`MockMvc` cho phép thực hiện request qua Spring MVC request handling bằng mock request/response, không cần khởi động HTTP server thật. Có thể dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để kiểm tra repository resources đã export trong application context.

Ví dụ giả định ứng dụng có collection resource `/people`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class RepositoryMediaTypeTests {

    private static final MediaType HAL_JSON =
            MediaType.parseMediaType("application/hal+json");

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsHalJsonWhenRequested() throws Exception {
        mockMvc.perform(get("/people").accept(HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(HAL_JSON));
    }

    @Test
    void rejectsUnsupportedAcceptHeader() throws Exception {
        mockMvc.perform(get("/people").accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }

    @Test
    void rejectsUnsupportedRequestContentType() throws Exception {
        mockMvc.perform(post("/people")
                        .accept(HAL_JSON)
                        .contentType(MediaType.APPLICATION_XML)
                        .content("<person><name>Ada</name></person>"))
                .andExpect(status().isUnsupportedMediaType());
    }
}
```

Các static import và type chính:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

Chạy test bằng `./mvnw test` hoặc `./gradlew test` theo build tool của dự án. Điều chỉnh path và JSON fields cho domain model thực tế. Nếu nhận 404 hoặc 405 thay vì status dự kiến, xác minh repository đã export, collection path đúng và method đang được bật. Nếu GET trả 200 nhưng content type khác kỳ vọng, xem lại cấu hình HAL và converter trước khi thay assertion.

Nên có thêm integration tests cho các hợp đồng riêng của ứng dụng:

- POST collection với JSON body và `Content-Type: application/json`.
- PUT item với JSON body.
- PATCH item với JSON Patch hoặc JSON Merge Patch có body đúng semantics.
- PUT association với `Content-Type: text/uri-list`.
- POST collection association với `Content-Type: text/uri-list`.
- Request có Accept không hỗ trợ để xác nhận 406.
- Request có Content-Type không hỗ trợ để xác nhận 415.

## 9. Checklist xử lý sự cố

- [ ] Đã ghi lại method, URL và headers thực tế của request.
- [ ] Đã xác định resource là collection, item, association hay custom controller.
- [ ] Với 406, đã kiểm tra `Accept` và media type response được hỗ trợ.
- [ ] Với 415, đã kiểm tra `Content-Type`, `Content-Encoding` và định dạng body thực tế.
- [ ] Body khớp với media type đã khai báo.
- [ ] Association PUT/POST dùng `text/uri-list` khi endpoint yêu cầu.
- [ ] Đã xem `consumes`/`produces`, message converters và content negotiation config.
- [ ] Đã kiểm tra dependency version và tài liệu tương ứng.
- [ ] Đã kiểm thử request hợp lệ và không hợp lệ bằng MockMvc hoặc HTTP integration test.

## Tài liệu chính thức

1. [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): supported methods và media type của collection, item, association, search và query resources.
2. [Spring Data REST — Domain Object Representations](https://docs.spring.io/spring-data/rest/reference/representations.html): JSON/HAL representations và response representation.
3. [Spring Data REST — Getting started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): cấu hình repository REST qua `RepositoryRestConfigurer`.
4. [RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html): cấu hình default media type và HAL.
5. [Spring Framework — Content Types](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html): cách Spring MVC xác định requested media type và cấu hình content negotiation.
6. [Spring Framework — Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): converter đọc request body và ghi response body.
7. [HttpMediaTypeNotAcceptableException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/HttpMediaTypeNotAcceptableException.html): exception khi không thể tạo response phù hợp.
8. [HttpMediaTypeNotSupportedException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/HttpMediaTypeNotSupportedException.html): exception khi handler không hỗ trợ request media type.
9. [Spring Framework — MockMvc](https://docs.spring.io/spring/reference/testing/mockmvc.html): thực hiện và xác minh request Spring MVC trong test.
10. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): định nghĩa Content-Type, 406 (mục 15.5.7) và 415 (mục 15.5.16).

*Tài liệu tham khảo được đối chiếu ngày 2026-11-11. Khi áp dụng, hãy chọn tài liệu cùng dòng phiên bản Spring Data REST/Spring Framework với dependency thực tế của dự án.*
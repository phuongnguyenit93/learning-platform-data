# Kiểu nội dung qua Content-Type, Accept, consumes và produces

Một API HTTP có thể nhận và trả dữ liệu ở nhiều định dạng. Để client và server hiểu cùng một cách về dữ liệu được trao đổi, HTTP dùng các header như `Content-Type` và `Accept`; Spring MVC dùng các điều kiện `consumes` và `produces` để chọn handler phù hợp. Springdoc-openapi đưa những khả năng này vào hợp đồng OpenAPI để người dùng API biết request cần gửi định dạng nào và response có thể nhận định dạng nào.

## 1. Media type mô tả định dạng dữ liệu

Trong HTTP, kiểu nội dung thường được biểu diễn bằng một **media type** có dạng `type/subtype`, có thể kèm tham số:

```text
application/json
text/plain; charset=UTF-8
multipart/form-data; boundary=----WebKitFormBoundary...
```

`type` cho biết nhóm dữ liệu tổng quát; `subtype` xác định định dạng cụ thể. Tham số phía sau dấu chấm phẩy bổ sung thông tin cần thiết để diễn giải nội dung, chẳng hạn charset hoặc boundary.

Một số media type thường gặp trong API:

| Media type | Mục đích thường dùng | Ví dụ nội dung |
|---|---|---|
| `application/json` | Trao đổi object hoặc dữ liệu có cấu trúc theo JSON | `{"id":12,"name":"Bút"}` |
| `application/problem+json` | Mô tả lỗi HTTP theo Problem Details dạng JSON | `{"type":"about:blank","title":"Not Found","status":404}` |
| `application/xml` | Trao đổi dữ liệu XML | `<item><id>12</id></item>` |
| `text/plain` | Văn bản thuần | `Đã tạo đơn hàng` |
| `text/csv` | Dữ liệu dạng CSV | `id,name\n12,Bút` |
| `application/octet-stream` | Dữ liệu nhị phân tổng quát | Nội dung file |
| `application/x-www-form-urlencoded` | Các trường form được mã hóa theo dạng key-value | `name=An&active=true` |
| `multipart/form-data` | Form gồm nhiều phần, thường dùng để gửi file và metadata | Một phần là file, phần khác là JSON hoặc text |

Media type là nhãn cho cách diễn giải nội dung. Nó không tự xác nhận dữ liệu có hợp lệ theo schema nghiệp vụ hay không. Ví dụ, body có `Content-Type: application/json` vẫn có thể chứa JSON sai cú pháp hoặc thiếu trường bắt buộc.

## 2. Content-Type mô tả định dạng của body

`Content-Type` mô tả định dạng của phần body đang được gửi. Header này có thể xuất hiện trong request hoặc response.

Trong request, client dùng `Content-Type` để thông báo định dạng payload cho server:

```http
POST /api/products HTTP/1.1
Host: example.test
Content-Type: application/json

{"name":"Bút","price":12000}
```

Server dựa vào media type để chọn cách đọc body. Nếu endpoint chỉ nhận JSON mà client gửi XML hoặc `text/plain`, request không đáp ứng điều kiện nội dung của endpoint.

Trong response, server dùng `Content-Type` để thông báo định dạng body mà client sắp nhận:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":12,"name":"Bút","price":12000}
```

Không nên nhầm `Content-Type` với `Content-Encoding`. `Content-Type` mô tả loại nội dung, còn `Content-Encoding` mô tả cách mã hóa hoặc nén biểu diễn nội dung, ví dụ `gzip`.

## 3. Accept cho biết client muốn nhận loại response nào

`Accept` là header do client gửi để nêu những media type mà client có thể xử lý trong response. Nó thường được dùng khi một endpoint có thể trả nhiều định dạng.

Ví dụ:

```http
GET /api/reports/12 HTTP/1.1
Host: example.test
Accept: application/json, application/xml;q=0.8, */*;q=0.1
```

Trong ví dụ này, client ưu tiên JSON; XML được chấp nhận với mức ưu tiên thấp hơn; các media type khác có thể được chấp nhận với mức ưu tiên thấp hơn nữa. Tham số `q` có giá trị từ `0` đến `1` và thể hiện trọng số ưu tiên. `q=0` nghĩa là client không chấp nhận loại tương ứng.

Một số dạng giá trị thường gặp:

| Giá trị Accept | Ý nghĩa |
|---|---|
| `application/json` | Chỉ định JSON là định dạng được chấp nhận |
| `application/json, application/xml` | Chấp nhận cả JSON và XML |
| `application/*` | Chấp nhận các subtype thuộc nhóm `application` |
| `*/*` | Chấp nhận mọi media type |
| `application/json;q=1, application/xml;q=0.5` | Ưu tiên JSON hơn XML |

Nếu client không gửi `Accept`, server thường được phép chọn một định dạng phù hợp với endpoint và cấu hình. `Accept: */*` biểu thị client không giới hạn media type. Khi server không thể tạo bất kỳ representation nào phù hợp với yêu cầu `Accept`, kết quả điển hình là `406 Not Acceptable`.

`Accept` trong bài này nói về **media type** của response. Các header như `Accept-Language` và `Accept-Encoding` giải quyết ngôn ngữ tự nhiên và kiểu nén, là các khía cạnh thương lượng nội dung khác.

## 4. Phân biệt Content-Type và Accept

Hai header thường xuất hiện cùng nhau nhưng trả lời hai câu hỏi khác nhau:

| Header | Câu hỏi được trả lời | Hướng dữ liệu | Ví dụ |
|---|---|---|---|
| `Content-Type` | Body đang gửi có định dạng gì? | Mô tả body của message hiện tại | Request gửi JSON: `Content-Type: application/json` |
| `Accept` | Client muốn nhận response ở định dạng nào? | Client đưa ra yêu cầu cho response | `Accept: application/json` |

Một request tạo tài nguyên thường có cả hai header:

```http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Bút","price":12000}
```

Ở đây, `Content-Type` nói rằng payload request là JSON; `Accept` nói rằng client muốn response là JSON. Hai giá trị có thể khác nhau. Chẳng hạn client gửi JSON nhưng muốn tải kết quả dưới dạng CSV nếu endpoint hỗ trợ.

Với request không có body, như một lệnh `GET` thông thường, `Content-Type` thường không cần thiết. Tuy vậy, `Accept` vẫn hữu ích vì response của `GET` có body.

## 5. consumes và produces trong Spring MVC

Spring MVC cung cấp hai thuộc tính của `@RequestMapping` và các annotation rút gọn như `@GetMapping`, `@PostMapping`:

- `consumes` giới hạn media type mà handler chấp nhận trong **request body**. Spring đối chiếu điều kiện này với `Content-Type` của request.
- `produces` giới hạn media type mà handler có thể tạo cho **response**. Spring dùng điều kiện này khi xét header `Accept` của request.

Ví dụ:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @ResponseStatus(HttpStatus.CREATED)
    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ProductResponse create(@RequestBody CreateProductRequest request) {
        return new ProductResponse(12L, request.name(), request.price());
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ProductResponse get(@PathVariable long id) {
        return new ProductResponse(id, "Bút", 12000);
    }
}
```

Với mapping `POST` trên:

- Request phải có `Content-Type` tương thích với `application/json`.
- Body được đọc vào `CreateProductRequest` thông qua bộ chuyển đổi message phù hợp.
- Handler công bố response dạng JSON; request có `Accept` không tương thích có thể bị từ chối trong quá trình chọn handler hoặc thương lượng response.

Các annotation rút gọn cho phép khai báo điều kiện trực tiếp:

```java
@PostMapping(
    path = "/import",
    consumes = MediaType.TEXT_PLAIN_VALUE,
    produces = MediaType.TEXT_PLAIN_VALUE
)
String importText(@RequestBody String content) {
    return "Đã nhận " + content.length() + " ký tự";
}
```

Khi cần nhiều định dạng, có thể khai báo một tập media type:

```java
@GetMapping(
    value = "/{id}/export",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
ProductExport export(@PathVariable long id) {
    return loadExport(id);
}
```

Khai báo trên chỉ mô tả các định dạng handler cho phép. Ứng dụng còn cần `HttpMessageConverter` tương ứng để thực sự ghi JSON hoặc XML. Nếu muốn trả XML, phải có converter và cấu hình thư viện XML phù hợp; thêm `application/xml` vào `produces` không tự cài đặt khả năng tuần tự hóa XML.

## 6. Spring chuyển đổi body như thế nào?

Trong Spring MVC, các implementation của `HttpMessageConverter` đọc request body thành tham số Java và ghi đối tượng Java thành response body. Việc chọn converter phụ thuộc vào kiểu Java, media type và các converter đã được cấu hình.

Một số ví dụ:

| Dữ liệu Java | Nội dung HTTP | Converter thường gặp |
|---|---|---|
| DTO hoặc object | `application/json` | `MappingJackson2HttpMessageConverter` trong cấu hình dùng Jackson |
| `String` | `text/plain` | `StringHttpMessageConverter` |
| `byte[]` | Dữ liệu nhị phân | `ByteArrayHttpMessageConverter` |
| `Resource` | Nội dung file hoặc tài nguyên | `ResourceHttpMessageConverter` |
| DTO hoặc object | `application/xml` | Converter XML nếu ứng dụng đã thêm và cấu hình hỗ trợ XML |

`@RequestBody` yêu cầu Spring đọc body qua converter phù hợp. `@ResponseBody` và `@RestController` yêu cầu Spring ghi giá trị trả về vào response body qua converter. Vì vậy, ba điều kiện cần được xem cùng nhau: media type của message, kiểu Java của tham số/giá trị trả về và converter đang có trong ứng dụng.

Không phải mọi tham số đều được đọc từ body. `@PathVariable` lấy dữ liệu từ URL; `@RequestParam` lấy tham số query hoặc form theo cơ chế binding của Spring; `@RequestHeader` đọc header. Dùng đúng annotation giúp tránh hiểu nhầm rằng `Content-Type` điều khiển mọi dữ liệu đầu vào.

## 7. Ví dụ form và upload file

### Form URL encoded

Một form đơn giản có thể gửi:

```http
POST /api/login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=an&rememberMe=true
```

Trong Spring MVC, dữ liệu dạng form thường được bind qua `@RequestParam` hoặc `@ModelAttribute`:

```java
@PostMapping(
    path = "/login",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
LoginResult login(
    @RequestParam String username,
    @RequestParam(defaultValue = "false") boolean rememberMe
) {
    return authenticate(username, rememberMe);
}
```

### Multipart upload

`multipart/form-data` chia body thành nhiều phần. Mỗi phần có thể có header riêng, ví dụ tên trường, tên file và media type của phần đó:

```java
@PostMapping(
    path = "/files",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
UploadResult upload(
    @RequestPart("file") MultipartFile file,
    @RequestPart("metadata") UploadMetadata metadata
) {
    return store(file, metadata);
}
```

Một client có thể gửi phần `file` là `application/pdf` và phần `metadata` là `application/json`. Media type ở cấp request là `multipart/form-data`; media type của từng phần mô tả nội dung riêng của phần đó. Khi dùng trình duyệt `FormData`, hãy để trình duyệt tự tạo header `Content-Type` cùng `boundary`; nếu tự đặt `multipart/form-data` mà thiếu boundary, server có thể không phân tích được các phần.

## 8. Biểu diễn Content-Type và Accept trong OpenAPI

OpenAPI mô tả media type theo từng operation. Hai vị trí quan trọng là `requestBody.content` và `responses.<status>.content`.

Ví dụ một operation nhận JSON và trả JSON:

```yaml
paths:
  /api/products:
    post:
      summary: Tạo sản phẩm
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        '201':
          description: Sản phẩm đã được tạo
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductResponse'
        '400':
          description: Request không hợp lệ
```

Các key `application/json` trong `content` là media type. Client dùng nội dung `requestBody.content` để biết các định dạng body có thể gửi; nội dung response cho biết định dạng có thể nhận theo từng status code. Trong giao thức HTTP, client thể hiện lựa chọn response qua `Accept`, còn server thể hiện định dạng thực tế đã trả bằng `Content-Type`.

Springdoc thường suy ra thông tin media type từ mapping `consumes` và `produces`, kiểu tham số và kiểu response. Khi cần mô tả rõ ràng hơn, có thể dùng annotation của Swagger/OpenAPI:

```java
@Operation(
    summary = "Tạo sản phẩm",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateProductRequest.class)
        )
    )
)
@ApiResponse(
    responseCode = "201",
    description = "Sản phẩm đã được tạo",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductResponse.class)
    )
)
@ResponseStatus(HttpStatus.CREATED)
@PostMapping(
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ProductResponse create(@RequestBody CreateProductRequest request) {
    // ...
}
```

Các import annotation có thể dùng wildcard hoặc import cụ thể từ `io.swagger.v3.oas.annotations.*`; ví dụ trên ghi rõ kiểu `RequestBody` để phân biệt với `org.springframework.web.bind.annotation.RequestBody`.

Annotation OpenAPI mô tả hợp đồng cho tài liệu. Nó không tự cấu hình `HttpMessageConverter`, không thay đổi mapping runtime và không làm cho controller nhận được media type mà ứng dụng chưa hỗ trợ. Hãy giữ annotation tài liệu đồng bộ với `consumes`, `produces` và hành vi thực tế của endpoint.

## 9. Dùng Swagger UI để kiểm tra hợp đồng

Sau khi ứng dụng khởi động, mở Swagger UI và chọn operation cần kiểm tra. Với operation có request body, giao diện hiển thị các media type được mô tả trong `requestBody.content`. Với response, giao diện hiển thị các media type được mô tả theo status code.

Khi chọn **Try it out**, hãy kiểm tra request thực tế trong tab Network của trình duyệt:

- `Content-Type` phải phù hợp với định dạng body đã chọn.
- `Accept` phải thể hiện định dạng response mà client mong muốn.
- Body phải đúng cấu trúc schema và cách mã hóa của media type.
- Response `Content-Type` phải mô tả đúng định dạng server đã trả.

Swagger UI dựa vào tài liệu OpenAPI được công bố. Nếu tài liệu mô tả `application/xml` nhưng controller không có XML converter, thao tác thử gọi có thể thất bại dù giao diện đã hiển thị lựa chọn XML. Vì vậy, cần kiểm tra cả tài liệu sinh ra và request/response thật.

## 10. Mã lỗi thường gặp khi media type không khớp

| Mã HTTP | Tình huống thường gặp | Cách kiểm tra |
|---|---|---|
| `400 Bad Request` | Body sai cú pháp, không thể deserialize hoặc dữ liệu không thể bind vào kiểu Java | Kiểm tra body, schema, kiểu trường và thông báo lỗi parse |
| `406 Not Acceptable` | Server không thể tạo response phù hợp với `Accept` của client hoặc điều kiện `produces` | Kiểm tra `Accept`, `produces` và converter ghi response |
| `415 Unsupported Media Type` | `Content-Type` của request không được endpoint chấp nhận hoặc không có converter đọc kiểu nội dung đó | Kiểm tra `Content-Type`, `consumes` và converter đọc request |
| `404 Not Found` | Không có mapping phù hợp với đường dẫn/phương thức; trong một số tình huống điều kiện mapping cũng khiến handler không được chọn | Kiểm tra URL, HTTP method và các điều kiện mapping khác |

Ví dụ, endpoint chỉ khai báo `consumes = application/json` nhưng client gửi `Content-Type: text/plain` thường dẫn đến `415`. Ngược lại, endpoint chỉ tạo JSON nhưng client gửi `Accept: application/xml` có thể dẫn đến `406` nếu server không có representation XML phù hợp.

Không nên kết luận mọi lỗi `400`, `406` hoặc `415` đều do một header duy nhất. Một ứng dụng có thể tùy biến exception handler và cấu hình converter, vì vậy hãy đọc response body, log và mapping thực tế để tìm nguyên nhân.

## 11. Kiểm thử bằng curl và MockMvc

### Gửi JSON và yêu cầu JSON

```bash
curl -i -X POST http://localhost:8080/api/products \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"name":"Bút","price":12000}'
```

Lệnh trên kiểm tra cả chiều request và response: body là JSON, client yêu cầu JSON. Quan sát status code và `Content-Type` trong response.

### Gửi sai media type để xác nhận điều kiện consumes

```bash
curl -i -X POST http://localhost:8080/api/products \
  -H 'Content-Type: text/plain' \
  -H 'Accept: application/json' \
  --data 'name=But'
```

Nếu mapping chỉ nhận JSON, request này phải bị từ chối do media type không phù hợp.

### Kiểm tra Accept không được hỗ trợ

```bash
curl -i http://localhost:8080/api/products/12 \
  -H 'Accept: application/xml'
```

Nếu endpoint chỉ tạo JSON và không có lựa chọn XML, kiểm tra kết quả thương lượng nội dung, thường là `406`.

### Kiểm tra bằng MockMvc

```java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsProductAsJson() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Bút","price":12000}
                    """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.name").value("Bút"));
    }

    @Test
    void rejectsUnsupportedRequestContentType() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .content("name=But"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

Đây là ví dụ minh họa cách kiểm tra; test thực tế cần cấu hình mock/service và status code của controller tương ứng. Có thể bổ sung test cho `Accept`, XML converter, multipart và các response error để bảo đảm tài liệu OpenAPI phản ánh đúng hành vi.

## 12. Quy trình thiết kế và rà soát media type

Khi thiết kế một endpoint, hãy xác định rõ các câu hỏi sau:

1. Request có body không? Nếu có, client được phép gửi những media type nào?
2. Body được bind vào kiểu Java nào và converter nào sẽ đọc nó?
3. Endpoint có thể trả những representation nào cho từng status code?
4. `Accept` ảnh hưởng thế nào khi client yêu cầu định dạng không được hỗ trợ?
5. `consumes` và `produces` trong Spring mapping có khớp với `requestBody.content` và `responses.content` trong OpenAPI không?
6. Swagger UI và kiểm thử HTTP có xác nhận được header cùng payload thực tế không?

Với API công khai, hãy chọn media type phổ biến và nhất quán, mô tả rõ request/response trong OpenAPI, đồng thời kiểm thử cả trường hợp hợp lệ và trường hợp media type không được hỗ trợ. Cách làm này giúp client tích hợp đúng định dạng và giúp nhóm phát triển phát hiện sớm sai lệch giữa controller, converter và tài liệu API.

## 13. Tài liệu tham khảo

- [MDN: Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Type): ý nghĩa header mô tả media type của representation.
- [MDN: Accept](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept): cú pháp media range, wildcard và trọng số `q` trong thương lượng nội dung.
- [Spring Framework: Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): điều kiện `consumes`, `produces` và cách khai báo request mapping.
- [Spring Framework: HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): cơ chế đọc và ghi body qua `HttpMessageConverter`.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): cấu trúc `requestBody`, `responses` và `content` trong hợp đồng API.
- [Swagger Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): cách dùng annotation để mô tả operation, request body và response.

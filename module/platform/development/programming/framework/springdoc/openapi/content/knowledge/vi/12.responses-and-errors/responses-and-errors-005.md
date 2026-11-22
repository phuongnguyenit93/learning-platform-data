# Header phản hồi như `Location`, `ETag` và thông tin phân trang

HTTP response không chỉ có status code và body. Header còn truyền metadata giúp client biết tài nguyên mới nằm ở đâu, representation hiện tại có phiên bản nào, nội dung có thể dùng lại từ cache hay trang dữ liệu tiếp theo nằm ở đâu. Với Spring Boot, `ResponseEntity` là cách phổ biến để tạo response có header; với `springdoc-openapi`, `@ApiResponse(headers = ...)` mô tả các header đó trong hợp đồng OpenAPI.

Ba nhóm header thường gặp trong API:

- `Location`: chỉ ra URI của tài nguyên vừa được tạo hoặc đích chuyển hướng.
- `ETag`: định danh phiên bản của representation để cache và kiểm tra điều kiện cập nhật.
- `Link` cùng các header phân trang như `X-Total-Count`: cung cấp liên kết đến trang đầu, trang trước, trang tiếp theo, trang cuối và tổng số bản ghi.

Header được gửi trong HTTP response thực tế phải khớp với những gì OpenAPI công bố. Annotation chỉ mô tả hợp đồng; code controller hoặc filter mới tạo header khi request được xử lý.

## 1. Tạo response có header bằng `ResponseEntity`

`ResponseEntity<T>` cho phép controller kiểm soát status, header và body trong cùng một giá trị trả về:

```java
return ResponseEntity
    .status(HttpStatus.CREATED)
    .header("X-Request-Id", requestId)
    .body(result);
```

Một số method builder thường dùng:

| API | Tác dụng |
| --- | --- |
| `ResponseEntity.ok()` | Tạo response `200 OK`. |
| `ResponseEntity.created(uri)` | Tạo response `201 Created` và header `Location`. |
| `.eTag(value)` | Đặt header `ETag`. |
| `.lastModified(value)` | Đặt header `Last-Modified`. |
| `.cacheControl(value)` | Đặt chính sách `Cache-Control`. |
| `.header(name, values...)` | Thêm một hoặc nhiều giá trị header tùy tên header. |
| `.body(value)` | Gắn response body. |

Có thể dùng `HttpHeaders` nếu cần chuẩn bị nhiều header hoặc dùng cùng một tập header ở nhiều nhánh xử lý. Header name không phân biệt chữ hoa/chữ thường theo HTTP, nhưng nên dùng cách viết chuẩn như `ETag`, `Location` và `Link` để dễ đọc log và tài liệu.

## 2. `Location` cho biết tài nguyên vừa được tạo

Khi client gửi `POST` để tạo tài nguyên, server thường trả `201 Created`. Header `Location` chỉ URI để client truy cập tài nguyên mới. Đây là cách phổ biến để client biết ID hoặc đường dẫn của đối tượng vừa được tạo mà không cần tự ghép URL.

Ví dụ controller tạo đơn hàng:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    @Operation(summary = "Tạo đơn hàng")
    @ApiResponse(
        responseCode = "201",
        description = "Đơn hàng đã được tạo",
        headers = @Header(
            name = HttpHeaders.LOCATION,
            description = "URI của đơn hàng vừa tạo",
            schema = @Schema(type = "string", format = "uri",
                example = "https://api.example.com/api/orders/8d3f")
        )
    )
    ResponseEntity<OrderResponse> create(@Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        URI location = ServletUriComponentsBuilder
            .fromCurrentRequest()
            .path("/{id}")
            .buildAndExpand(created.id())
            .toUri();

        return ResponseEntity.created(location).body(created);
    }
}
```

`ResponseEntity.created(location)` tạo status `201` và đặt `Location` theo URI truyền vào. `ServletUriComponentsBuilder.fromCurrentRequest()` lấy URI của request hiện tại; `.path("/{id}")` thêm đường dẫn tài nguyên mới. Cách này giúp tránh hard-code host hoặc base path trong controller.

Trong OpenAPI, header response được khai báo bên trong response tương ứng, ở đây là `201`. `schema` mô tả giá trị header dưới dạng URI; `description` giải thích client nên dùng URI đó như thế nào. Header không nằm trong response body.

`Location` cũng có thể xuất hiện trong response redirect như `301`, `302`, `303`, `307` hoặc `308`. Trong trường hợp tạo tài nguyên, cặp `201 Created` và `Location` giúp client phân biệt việc tạo thành công với việc chỉ nhận một response có body.

## 3. `ETag` định danh phiên bản representation

`ETag` (Entity Tag) là một validator do server gửi để định danh phiên bản của representation. Client có thể lưu ETag và gửi lại trong request tiếp theo để hỏi liệu dữ liệu đã thay đổi hay chưa.

Ví dụ response:

```http
HTTP/1.1 200 OK
ETag: "order-v42"
Cache-Control: private, max-age=60
Content-Type: application/json
```

ETag có hai dạng chính:

- **Strong ETag:** ví dụ `"order-v42"`; biểu thị representation tương đương byte-for-byte theo quy tắc validator mạnh.
- **Weak ETag:** ví dụ `W/"order-v42"`; biểu thị nội dung tương đương về mặt ngữ nghĩa theo tiêu chí của server, nhưng không cam kết byte giống hệt.

Không nên tạo strong ETag chỉ từ ID bản ghi nếu nội dung response có thể thay đổi mà ID không đổi. Có thể dùng version number tăng theo mỗi lần cập nhật, hash của representation hoặc một định danh khác được bảo đảm thay đổi khi representation thay đổi. Nếu server không bảo đảm byte-for-byte, hãy cân nhắc weak ETag.

### Dùng ETag với `If-None-Match` để cache

Client gửi ETag đã lưu trong request header `If-None-Match`. Nếu representation chưa thay đổi, server có thể trả `304 Not Modified` và không gửi lại body. Client tiếp tục sử dụng bản đã cache.

```http
GET /api/orders/8d3f HTTP/1.1
If-None-Match: "order-v42"
```

Nếu dữ liệu vẫn có cùng validator:

```http
HTTP/1.1 304 Not Modified
ETag: "order-v42"
Cache-Control: private, max-age=60
```

Trong Spring MVC, `ServletWebRequest.checkNotModified(etag)` hỗ trợ xử lý điều kiện cache và đặt status thích hợp:

```java
@GetMapping("/{id}")
@Operation(summary = "Lấy đơn hàng theo mã")
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Đơn hàng được trả về",
        headers = @Header(name = "ETag", description = "Validator của representation",
            schema = @Schema(type = "string", example = "\"order-v42\""))),
    @ApiResponse(responseCode = "304", description = "Representation chưa thay đổi",
        headers = @Header(name = "ETag", description = "Validator hiện tại",
            schema = @Schema(type = "string", example = "\"order-v42\"")))
})
ResponseEntity<OrderResponse> get(
    @PathVariable UUID id,
    ServletWebRequest webRequest
) {
    OrderResponse order = orderService.getById(id);
    String etag = "\"order-v" + order.version() + "\"";

    if (webRequest.checkNotModified(etag)) {
        return null; // Spring giữ response 304 đã được thiết lập.
    }

    return ResponseEntity.ok()
        .header(HttpHeaders.ETAG, etag)
        .cacheControl(CacheControl.noCache())
        .body(order);
}
```

`checkNotModified` kiểm tra validator trong request và có thể hoàn tất response `304`; khi đó controller không cần gửi body. Ví dụ dùng version của đơn hàng để tạo ETag. Trong ứng dụng thực tế, version phải tăng mỗi khi bất kỳ dữ liệu nào ảnh hưởng đến representation thay đổi. `CacheControl.noCache()` cho phép cache lưu response nhưng yêu cầu revalidate trước khi sử dụng lại; hãy chọn chính sách cache theo tính nhạy cảm và vòng đời dữ liệu.

### Dùng `If-Match` để tránh ghi đè cập nhật

`If-Match` phục vụ một mục tiêu khác: client gửi ETag mà nó đã đọc khi muốn cập nhật tài nguyên. Server chỉ thực hiện cập nhật nếu phiên bản hiện tại còn khớp. Nếu đã có người khác cập nhật trước, server trả `412 Precondition Failed`.

```http
PUT /api/orders/8d3f HTTP/1.1
If-Match: "order-v42"
Content-Type: application/json
```

Nếu phiên bản hiện tại đã là `order-v43`, server từ chối cập nhật để client tải dữ liệu mới và xử lý xung đột. Có thể khai báo header request và response lỗi trong OpenAPI:

```java
@PutMapping("/{id}")
@Operation(summary = "Cập nhật đơn hàng có kiểm tra phiên bản")
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Cập nhật thành công",
        headers = @Header(name = "ETag", description = "Validator mới sau cập nhật",
            schema = @Schema(type = "string", example = "\"order-v43\""))),
    @ApiResponse(responseCode = "412", description = "Phiên bản tài nguyên không còn khớp")
})
ResponseEntity<OrderResponse> update(
    @PathVariable UUID id,
    @Parameter(name = "If-Match", in = ParameterIn.HEADER,
        description = "ETag mà client đã nhận ở lần đọc trước",
        schema = @Schema(type = "string", example = "\"order-v42\""))
    @RequestHeader(HttpHeaders.IF_MATCH) String ifMatch,
    @Valid @RequestBody UpdateOrderRequest request
) {
    OrderResponse updated = orderService.updateIfVersionMatches(id, ifMatch, request);
    String newEtag = "\"order-v" + updated.version() + "\"";
    return ResponseEntity.ok()
        .header(HttpHeaders.ETAG, newEtag)
        .body(updated);
}
```

Phần so sánh version và phát sinh lỗi `412` thuộc về service hoặc tầng xử lý nghiệp vụ. `@Parameter` chỉ mô tả request header; `@ApiResponse` mô tả response có thể trả về. Với `If-Match`, server cần xử lý cả trường hợp header thiếu nếu hợp đồng yêu cầu precondition bắt buộc, cũng như cú pháp ETag hợp lệ và các dạng wildcard/list theo HTTP.

## 4. Header phân trang: `Link` và tổng số bản ghi

API phân trang thường trả về một phần tử dữ liệu trong body và thông tin điều hướng trong header. Cách này giúp client biết có trang tiếp theo hay không mà không cần tự tính URL.

Ví dụ response:

```http
HTTP/1.1 200 OK
X-Total-Count: 143
X-Total-Pages: 8
Link: <https://api.example.com/api/products?page=0&size=20>; rel="first",
      <https://api.example.com/api/products?page=2&size=20>; rel="next",
      <https://api.example.com/api/products?page=7&size=20>; rel="last"
Content-Type: application/json
```

`Link` sử dụng định dạng Web Linking. Mỗi link chứa URI trong dấu ngoặc nhọn và một relation như:

| Relation | Ý nghĩa |
| --- | --- |
| `first` | Trang đầu tiên. |
| `prev` | Trang ngay trước trang hiện tại. |
| `self` | Trang hiện tại. |
| `next` | Trang tiếp theo. |
| `last` | Trang cuối cùng. |

Các relation này là giá trị phổ biến trong phân trang; server có thể bỏ `prev` ở trang đầu hoặc `next` ở trang cuối. `X-Total-Count` và `X-Total-Pages` là header tùy chỉnh của API, không phải header HTTP chuẩn chung cho mọi hệ thống. Cần ghi rõ ý nghĩa, đơn vị và cách tính trong tài liệu.

Ví dụ sử dụng Spring Data `Page<T>`:

```java
@GetMapping
@Operation(summary = "Liệt kê sản phẩm theo trang")
@ApiResponse(
    responseCode = "200",
    description = "Danh sách sản phẩm của trang hiện tại",
    headers = {
        @Header(name = "Link", description = "Các liên kết điều hướng giữa những trang",
            schema = @Schema(type = "string",
                example = "<https://api.example.com/api/products?page=2&size=20>; rel=\"next\"")),
        @Header(name = "X-Total-Count", description = "Tổng số sản phẩm thỏa điều kiện lọc",
            schema = @Schema(type = "integer", format = "int64", example = "143")),
        @Header(name = "X-Total-Pages", description = "Tổng số trang",
            schema = @Schema(type = "integer", format = "int32", example = "8"))
    }
)
ResponseEntity<List<ProductResponse>> list(
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") int size
) {
    Page<ProductResponse> result = productService.findAll(PageRequest.of(page, size));
    UriComponentsBuilder base = ServletUriComponentsBuilder.fromCurrentRequest();
    List<String> links = new ArrayList<>();

    if (result.getTotalPages() > 0) {
        links.add(pageLink(base, 0, result.getSize(), "first"));
        if (result.hasPrevious()) {
            links.add(pageLink(base, result.getNumber() - 1, result.getSize(), "prev"));
        }
        links.add(pageLink(base, result.getNumber(), result.getSize(), "self"));
        if (result.hasNext()) {
            links.add(pageLink(base, result.getNumber() + 1, result.getSize(), "next"));
        }
        links.add(pageLink(base, result.getTotalPages() - 1, result.getSize(), "last"));
    }

    return ResponseEntity.ok()
        .header("X-Total-Count", Long.toString(result.getTotalElements()))
        .header("X-Total-Pages", Integer.toString(result.getTotalPages()))
        .header(HttpHeaders.LINK, String.join(", ", links))
        .body(result.getContent());
}

private String pageLink(UriComponentsBuilder base, int page, int size, String rel) {
    String uri = base.cloneBuilder()
        .replaceQueryParam("page", page)
        .replaceQueryParam("size", size)
        .build()
        .encode()
        .toUriString();
    return "<" + uri + ">; rel=\"" + rel + "\"";
}
```

Helper `pageLink` giữ các query parameter lọc hiện có và chỉ thay `page`, `size`, vì vậy các trang tiếp theo vẫn áp dụng cùng điều kiện tìm kiếm. Ví dụ giả định `PageRequest` dùng chỉ số trang bắt đầu từ `0`. Với trang rỗng, code không tạo link `first` hoặc `last` trỏ đến trang âm; tổng trang vẫn được trả về là `0`.

Nếu API không dùng Spring Data, có thể tự tạo URI và các header tương tự từ metadata phân trang của ứng dụng. Điều quan trọng là `Link` phải trỏ đến URL có thể gọi được và giữ nguyên filter/sort mà client đã gửi.

## 5. Mô tả response header bằng `@ApiResponse`

Trong OpenAPI, response header nằm trong phần `headers` của từng response code. Springdoc hỗ trợ khai báo bằng annotation `@Header` lồng trong `@ApiResponse`:

```java
@ApiResponse(
    responseCode = "201",
    description = "Đã tạo tài nguyên",
    headers = {
        @Header(
            name = "Location",
            description = "URI của tài nguyên mới",
            schema = @Schema(type = "string", format = "uri")
        ),
        @Header(
            name = "ETag",
            description = "Validator của representation",
            schema = @Schema(type = "string", example = "\"v42\"")
        )
    }
)
```

Mỗi header nên có:

- Tên header đúng như response thực tế.
- `description` giải thích mục đích, định dạng hoặc cách client sử dụng.
- `schema` phản ánh kiểu giá trị: chuỗi, số, URI hoặc kiểu phù hợp.
- `example` hữu ích với header có cú pháp đặc biệt như ETag hoặc Link.

Không khai báo response header thành `@Parameter(in = HEADER)` vì `@Parameter` mô tả dữ liệu client gửi lên. Request header như `If-None-Match` và `If-Match` có thể dùng `@Parameter` hoặc `@RequestHeader`; response header như `ETag`, `Location`, `Link` cần nằm trong `@ApiResponse(headers = ...)`.

Một endpoint có thể có các header khác nhau theo status code. Ví dụ `201` trả `Location`, `200` trả `ETag`, `304` trả `ETag` nhưng không có body, còn `412` biểu thị precondition thất bại. Khai báo header trong đúng response để client hiểu trường hợp nào sẽ nhận được nó.

## 6. CORS và khả năng đọc header từ trình duyệt

Nếu frontend gọi API từ origin khác, trình duyệt không cho JavaScript đọc tất cả response header tùy ý. Các header cơ bản được expose theo quy tắc CORS; những header như `ETag`, `Link`, `X-Total-Count` hoặc `X-Total-Pages` thường cần được công bố qua `Access-Control-Expose-Headers`.

Ví dụ cấu hình Spring MVC:

```java
@Configuration
class WebCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE")
            .exposedHeaders("Location", "ETag", "Link",
                "X-Total-Count", "X-Total-Pages");
    }
}
```

`exposedHeaders` cho phép JavaScript đọc các header đã liệt kê sau khi request CORS thành công. Nếu ứng dụng cấu hình CORS trong Spring Security, hãy đặt quy tắc tương ứng ở cấu hình Security và bảo đảm filter CORS được áp dụng. CORS chỉ kiểm soát việc trình duyệt cho phép frontend khác origin đọc response; nó không thay thế xác thực hoặc phân quyền API.

## 7. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Response `201` không có `Location` | Code chỉ trả status mà chưa tạo URI | Dùng `ResponseEntity.created(uri)` hoặc đặt header tường minh. |
| `Location` chứa host sai | Hard-code host hoặc ứng dụng chạy sau reverse proxy | Dùng URI builder theo request và cấu hình forwarded headers đáng tin cậy ở proxy/server. |
| ETag không thay đổi sau khi cập nhật | Validator dựa trên ID không đổi hoặc version không tăng | Dùng version/hash phản ánh mọi thay đổi của representation. |
| Client luôn nhận `200` thay vì `304` | Không xử lý `If-None-Match` hoặc ETag gửi lên không khớp | Dùng `checkNotModified` hoặc triển khai conditional request đúng chuẩn. |
| Cập nhật ghi đè dữ liệu của người khác | Không kiểm tra `If-Match` hoặc version khi ghi | So sánh validator hiện tại và trả `412` khi precondition thất bại. |
| Không có link `next` dù còn dữ liệu | Tính `hasNext`, số trang hoặc query parameter sai | Dùng metadata phân trang từ nguồn dữ liệu và kiểm tra URL được tạo. |
| JavaScript không đọc được `ETag` hoặc `X-Total-Count` | Header chưa được expose qua CORS | Thêm header vào `exposedHeaders`/`Access-Control-Expose-Headers`. |
| Swagger UI không hiển thị response header | Chưa khai báo `@ApiResponse(headers = ...)` hoặc khai báo nhầm thành request parameter | Đặt `@Header` trong response code tương ứng. |

## 8. Quy trình kiểm tra header

Sau khi triển khai, kiểm tra cả HTTP response và tài liệu OpenAPI:

1. Gọi endpoint tạo tài nguyên và xác nhận `201`, `Location` trỏ đến tài nguyên mới.
2. Gọi endpoint đọc tài nguyên và lưu giá trị `ETag` trả về.
3. Gửi lại request với `If-None-Match` đúng giá trị; xác nhận server trả `304` khi dữ liệu chưa đổi.
4. Cập nhật với `If-Match` cũ sau khi version đã thay đổi; xác nhận server trả `412` và không ghi đè dữ liệu mới.
5. Gọi endpoint phân trang ở trang đầu, giữa và cuối; xác nhận `Link` có các relation phù hợp và tổng số bản ghi đúng.
6. Gọi từ frontend khác origin và xác nhận JavaScript đọc được những header đã expose.
7. Mở `/v3/api-docs`, kiểm tra từng response code có `headers` với tên, schema và mô tả đúng.

Ví dụ kiểm tra nhanh bằng curl:

```bash
# Tạo tài nguyên và xem Location.
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customerId":"c-123"}'

# Gửi ETag đã nhận để kiểm tra cache.
curl -i http://localhost:8080/api/orders/8d3f \
  -H 'If-None-Match: "order-v42"'

# Xem header điều hướng phân trang.
curl -i 'http://localhost:8080/api/products?page=1&size=20'
```

Khi kiểm tra conditional request, hãy dùng chính ETag server đã trả về, không giả định giá trị ví dụ luôn đúng. Curl hiển thị response header mà không phụ thuộc Swagger UI, nên hữu ích để phân biệt lỗi runtime với lỗi mô tả tài liệu.

## 9. Nguyên tắc áp dụng

- Trả `201 Created` cùng `Location` khi tạo tài nguyên mới và có URI để truy cập.
- Dùng ETag phản ánh phiên bản representation; chọn strong hoặc weak validator đúng với cách so sánh.
- Dùng `If-None-Match` cho cache validation và `If-Match` để tránh cập nhật mất dữ liệu.
- Trả `Link` cho điều hướng trang; mô tả rõ ý nghĩa các header tùy chỉnh như `X-Total-Count`.
- Dùng `@ApiResponse(headers = ...)` để công bố response header theo từng status code.
- Expose các header cần đọc qua JavaScript khi API được gọi cross-origin.
- Kiểm tra HTTP response thực tế và `/v3/api-docs` sau mỗi thay đổi.

Header phản hồi bổ sung ngữ cảnh quan trọng cho client: `Location` chỉ ra tài nguyên mới, `ETag` hỗ trợ cache và kiểm soát cập nhật đồng thời, còn `Link` cùng metadata phân trang giúp điều hướng tập dữ liệu. Khi code Spring tạo đúng header và springdoc mô tả chúng trong response tương ứng, client có thể tích hợp API nhất quán mà không phải suy đoán từ response body.

## Tài liệu tham khảo

- [RFC 9110 – HTTP Semantics: Location, ETag và Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 8288 – Web Linking: Link header](https://www.rfc-editor.org/rfc/rfc8288)
- [Spring Framework – `ResponseEntity`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html)
- [Spring Framework – `ServletWebRequest.checkNotModified`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/context/request/ServletWebRequest.html)
- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)

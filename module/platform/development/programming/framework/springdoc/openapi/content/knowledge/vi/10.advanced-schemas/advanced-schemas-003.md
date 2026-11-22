# ResponseEntity, Optional và quy tắc bỏ lớp bao khi được hỗ trợ

## 1. Vì sao kiểu trả về Java không luôn giống schema JSON?

Một controller Spring Boot có thể khai báo kiểu trả về như `ProductResponse`, `ResponseEntity<ProductResponse>`, `Optional<ProductResponse>` hoặc `ResponseEntity<List<ProductResponse>>`. Những kiểu này giúp Spring điều khiển HTTP response và giúp Java biểu đạt dữ liệu, nhưng không phải tất cả đều xuất hiện trong JSON mà client nhận được.

Ví dụ, với phương thức:

~~~java
@GetMapping("/api/products/{id}")
public ResponseEntity<ProductResponse> findById(
    @PathVariable Long id
) {
    return ResponseEntity.ok(productService.getByIdOrThrow(id));
}
~~~

HTTP response có status, header và body. Phần body là một đối tượng `ProductResponse`; client không nhận một object JSON có thuộc tính tên `body`, `statusCode` hay `headers` theo cấu trúc của lớp ResponseEntity.

Springdoc OpenAPI cần phân biệt **lớp bao dùng cho xử lý ở Java/Spring** với **payload thực sự được truyền trên HTTP**. Khi nhận diện được một wrapper được hỗ trợ, thư viện có thể bỏ lớp bao đó trong quá trình tạo schema và mô tả kiểu dữ liệu bên trong.

Bài này tập trung vào hai kiểu thường gặp:

- **ResponseEntity<T>**: lớp của Spring mô tả HTTP status, header và body.
- **Optional<T>**: lớp Java biểu diễn một giá trị có thể hiện diện hoặc vắng mặt.

Quy tắc bỏ lớp bao phụ thuộc loại wrapper và khả năng phân giải kiểu của phiên bản Springdoc cùng các thư viện OpenAPI đi kèm. Luôn kiểm tra tài liệu JSON/YAML sinh ra và response thực tế trước khi coi schema là chính xác.

## 2. ResponseEntity<T> đại diện cho HTTP response

`ResponseEntity<T>` thuộc Spring Framework và cho phép controller chủ động quyết định:

- HTTP status code, ví dụ 200, 201, 204 hoặc 404.
- Các HTTP response header, ví dụ Location, ETag hoặc Cache-Control.
- Body có kiểu T hoặc không có body.

Ví dụ trả về thành công:

~~~java
@GetMapping("/api/products/{id}")
public ResponseEntity<ProductResponse> findById(
    @PathVariable Long id
) {
    ProductResponse product = productService.getByIdOrThrow(id);
    return ResponseEntity.ok(product);
}
~~~

Spring dùng ResponseEntity để tạo HTTP response. Body được serialize thành JSON theo cấu hình message converter. Về mặt hợp đồng OpenAPI, schema response mô tả **ProductResponse**, còn status và header được mô tả ở các phần riêng của Response Object.

Một response tương ứng có thể được biểu diễn như sau:

~~~yaml
responses:
  "200":
    description: Tìm thấy sản phẩm
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ProductResponse'
~~~

Springdoc thường nhận diện ResponseEntity và phân giải generic type T để tạo schema cho body. Nó không cần tạo schema JSON cho cấu trúc nội bộ của lớp ResponseEntity.

## 3. Bỏ lớp bao ResponseEntity nhưng giữ thông tin HTTP

Bỏ lớp bao trong schema không có nghĩa bỏ status hoặc header của HTTP response. Hai việc này thuộc hai lớp khác nhau:

| Thành phần | Nơi thể hiện trong hợp đồng |
|---|---|
| Kiểu dữ liệu body T | Schema trong response content |
| HTTP status code | Khóa response như 200, 201, 404 |
| HTTP response header | Thuộc tính headers của Response Object |
| Media type | Khóa content như application/json |
| Body không tồn tại | Response không khai báo content hoặc mô tả content phù hợp |

Ví dụ tạo sản phẩm:

~~~java
@PostMapping("/api/products")
public ResponseEntity<ProductResponse> create(
    @Valid @RequestBody CreateProductRequest request
) {
    ProductResponse created = productService.create(request);
    URI location = URI.create("/api/products/" + created.id());

    return ResponseEntity.created(location).body(created);
}
~~~

Phương thức trên trả status 201 Created, header Location và body ProductResponse. Schema của body vẫn là ProductResponse; thông tin 201 và Location cần được mô tả riêng trong OpenAPI.

Có thể khai báo rõ:

~~~java
@PostMapping("/api/products")
@Operation(summary = "Tạo sản phẩm")
@ApiResponse(
    responseCode = "201",
    description = "Đã tạo sản phẩm",
    headers = @Header(
        name = "Location",
        description = "URL của sản phẩm vừa tạo",
        schema = @Schema(type = "string", format = "uri")
    ),
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductResponse.class)
    )
)
public ResponseEntity<ProductResponse> create(
    @Valid @RequestBody CreateProductRequest request
) {
    ProductResponse created = productService.create(request);
    URI location = URI.create("/api/products/" + created.id());

    return ResponseEntity.created(location).body(created);
}
~~~

Các annotation OpenAPI giúp công bố hợp đồng. ResponseEntity vẫn là thành phần quyết định response thật ở runtime. Nếu chỉ khai báo response 201 trong annotation nhưng code thực tế trả 200, tài liệu sẽ không khớp hành vi.

## 4. ResponseEntity<Void> và response không có body

Một số thao tác chỉ cần thông báo kết quả qua status code và không trả JSON. Ví dụ xóa tài nguyên thành công có thể trả 204 No Content:

~~~java
@DeleteMapping("/api/products/{id}")
public ResponseEntity<Void> delete(
    @PathVariable Long id
) {
    productService.delete(id);
    return ResponseEntity.noContent().build();
}
~~~

Kiểu generic `Void` cho biết response không có payload. OpenAPI nên mô tả response 204 mà không tạo schema body:

~~~yaml
responses:
  "204":
    description: Xóa sản phẩm thành công
~~~

Không nên khai báo một schema object rỗng chỉ vì kiểu Java là ResponseEntity. Nếu response thực sự không có body, hãy thể hiện điều đó bằng response code và mô tả tương ứng.

Một số tình huống khác:

~~~java
return ResponseEntity.notFound().build();
~~~

Trả 404 không có body.

~~~java
return ResponseEntity.status(HttpStatus.ACCEPTED).build();
~~~

Trả 202 không có body.

Nếu API có body lỗi cho 404 hoặc 202, hãy dùng ResponseEntity với kiểu body cụ thể và khai báo schema lỗi tương ứng. Kiểu generic của một phương thức chỉ mô tả một kiểu T; các status code khác nhau có thể có content schema khác nhau và cần được khai báo bằng `@ApiResponse` phù hợp.

## 5. Springdoc suy luận response schema từ kiểu generic

Với kiểu trả về có generic, Springdoc có thể phân tích tham số kiểu để xác định payload.

Ví dụ:

~~~java
ResponseEntity<ProductResponse>
ResponseEntity<List<ProductResponse>>
ResponseEntity<Map<String, ProductResponse>>
~~~

Các schema tương ứng thường là:

| Kiểu Java | Schema body dự kiến |
|---|---|
| `ResponseEntity<ProductResponse>` | Object ProductResponse |
| `ResponseEntity<List<ProductResponse>>` | Array có items là ProductResponse |
| `ResponseEntity<Map<String, ProductResponse>>` | Object có giá trị theo schema ProductResponse |
| `ResponseEntity<Void>` | Không có body schema |

Ví dụ danh sách:

~~~java
@GetMapping("/api/products")
public ResponseEntity<List<ProductResponse>> findAll() {
    return ResponseEntity.ok(productService.findAll());
}
~~~

Body JSON là một array:

~~~json
[
  {
    "id": 101,
    "name": "Bàn phím cơ"
  },
  {
    "id": 102,
    "name": "Chuột không dây"
  }
]
~~~

Springdoc cần giữ nguyên kiểu generic bên trong khi bỏ ResponseEntity. Nếu kiểu trả về bị khai báo raw như `ResponseEntity` hoặc dùng generic không thể xác định, thư viện có thể không suy luận được schema cụ thể. Khi đó, nên dùng kiểu trả về đầy đủ hoặc khai báo response schema tường minh.

## 6. Optional<T> biểu diễn giá trị có thể vắng mặt

`Optional<T>` thuộc Java và thường được dùng ở tầng service hoặc repository để biểu đạt rằng thao tác tìm kiếm có thể không tìm thấy dữ liệu.

Ví dụ:

~~~java
public Optional<Product> findById(Long id) {
    return productRepository.findById(id);
}
~~~

Optional giúp người gọi xử lý rõ hai trường hợp:

- Có giá trị: Optional chứa một Product.
- Không có giá trị: Optional.empty().

Optional là wrapper ở Java. JSON không có kiểu dữ liệu Optional riêng. Khi Springdoc và thư viện mô hình OpenAPI hỗ trợ phân giải wrapper này, schema được tạo thường là schema của T, không phải object có thuộc tính `present`, `empty` hoặc `value`.

Ví dụ, nếu kiểu trả về là Optional<ProductResponse> và wrapper được phân giải, schema body mô tả ProductResponse. Tuy nhiên, schema của T không tự quyết định điều gì xảy ra khi Optional.empty().

**Optional.empty() không tự động có nghĩa là HTTP 404.** Nó cũng không tự định nghĩa response code, body lỗi hay quy tắc không tìm thấy tài nguyên. Ứng dụng cần chuyển trạng thái vắng mặt thành HTTP response một cách rõ ràng.

## 7. Chuyển Optional từ service thành ResponseEntity ở controller

Một cách triển khai rõ ràng là để service trả Optional, sau đó controller quyết định status code:

~~~java
@GetMapping("/api/products/{id}")
@Operation(summary = "Lấy sản phẩm theo mã")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy sản phẩm",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy sản phẩm",
        content = @Content
    )
})
public ResponseEntity<ProductResponse> findById(
    @PathVariable Long id
) {
    return productService.findById(id)
        .map(ProductResponse::from)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

Cách này tách rõ trách nhiệm:

- Service tìm dữ liệu và trả Optional.
- Controller ánh xạ giá trị hiện diện thành 200 OK với body.
- Controller ánh xạ giá trị vắng mặt thành 404 Not Found không body.
- OpenAPI công bố hai response code và schema tương ứng.

Nếu quy ước của API là trả body lỗi khi không tìm thấy, hãy dùng response DTO lỗi và khai báo content schema cho 404. Không để client phải suy luận từ một Optional Java mà họ không nhìn thấy.

## 8. Trả Optional<T> trực tiếp từ controller

Có thể gặp controller khai báo:

~~~java
@GetMapping("/api/products/featured")
public Optional<ProductResponse> getFeatured() {
    return productService.findFeatured()
        .map(ProductResponse::from);
}
~~~

Ở cấp schema, Springdoc có thể bỏ lớp Optional nếu phiên bản và bộ phân giải kiểu hỗ trợ. Nhưng hành vi HTTP khi Optional rỗng còn phụ thuộc vào cách Spring MVC xử lý return value và cấu hình message converter/Jackson của ứng dụng.

Không nên giả định Optional rỗng luôn tạo 404, 204 hoặc một JSON null. Hãy gọi endpoint trong trường hợp có và không có dữ liệu để xác minh status, header và body thực tế.

Nếu ý nghĩa nghiệp vụ của trường hợp rỗng là “không tìm thấy tài nguyên”, hãy chuyển Optional thành ResponseEntity hoặc ném exception được ánh xạ rõ sang 404. Nếu endpoint luôn tồn tại và kết quả rỗng là một trạng thái hợp lệ, hãy định nghĩa cụ thể response body mà client nhận được.

Với API công khai, việc dùng ResponseEntity ở controller thường giúp thể hiện rõ status và body hơn so với để Optional quyết định gián tiếp hành vi HTTP.

## 9. Vì sao không nên lồng ResponseEntity<Optional<T>>?

Có thể viết:

~~~java
public ResponseEntity<Optional<ProductResponse>> findById(
    Long id
) {
    // ...
}
~~~

Nhưng kiểu này đặt hai lớp biểu đạt sự vắng mặt cạnh nhau:

- ResponseEntity quyết định status và body của HTTP response.
- Optional lại biểu đạt body có thể không có giá trị.

Điều này làm hợp đồng khó đọc. Springdoc có thể phân giải một hoặc nhiều wrapper để tạo schema T tùy khả năng hỗ trợ, trong khi runtime có thể serialize Optional rỗng theo cách khác với kỳ vọng của client.

Nên chuyển Optional thành HTTP response trước khi trả về:

~~~java
public ResponseEntity<ProductResponse> findById(Long id) {
    return productService.findById(id)
        .map(ProductResponse::from)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

Khi đó, kiểu trả về biểu đạt trực tiếp payload của response thành công và controller quyết định trường hợp vắng mặt bằng status code. OpenAPI cũng dễ mô tả từng response hơn.

## 10. Phân biệt Optional với nullable và thuộc tính không bắt buộc

Optional, nullable và required là các khái niệm khác nhau:

| Khái niệm | Phạm vi | Ý nghĩa |
|---|---|---|
| Java Optional<T> | Kiểu Java | Một giá trị có thể hiện diện hoặc vắng mặt |
| Schema nullable | Giá trị JSON | Cho phép giá trị null |
| Schema required | Thuộc tính object | Thuộc tính có bắt buộc xuất hiện không |
| RequestBody.required | HTTP request | Toàn bộ request body có bắt buộc không |
| Response content | HTTP response | Body có được trả về cho status code đó hay không |

Ví dụ, một thuộc tính response có thể không bắt buộc xuất hiện nhưng nếu xuất hiện thì phải là chuỗi. Một thuộc tính khác có thể bắt buộc xuất hiện nhưng chấp nhận null. Hai trường hợp này phải được mô tả bằng schema, không thể suy ra chỉ từ việc một field Java có kiểu Optional.

Với DTO trao đổi qua API, nên dùng kiểu dữ liệu và annotation schema thể hiện trực tiếp hợp đồng JSON. Không nên đưa Optional vào mọi field chỉ để biểu đạt rằng dữ liệu có thể thiếu. Cần xem xét cách Jackson serialize/deserialze Optional và cấu hình đang dùng trước khi đưa kiểu này vào DTO công khai.

## 11. Wrapper tùy biến có được bỏ lớp bao không?

Không phải mọi lớp generic đều là wrapper kỹ thuật có thể bỏ khỏi schema.

Ví dụ:

~~~java
public record ApiEnvelope<T>(
    String traceId,
    T data,
    String message
) {}
~~~

Nếu controller trả về:

~~~java
public ResponseEntity<ApiEnvelope<ProductResponse>> findProduct(
    @PathVariable Long id
) {
    ApiEnvelope<ProductResponse> envelope =
        productService.findEnvelope(id);

    return ResponseEntity.ok(envelope);
}
~~~

Response JSON thực tế có dạng:

~~~json
{
  "traceId": "req-123",
  "data": {
    "id": 101,
    "name": "Bàn phím cơ"
  },
  "message": "Success"
}
~~~

Trong trường hợp này, ApiEnvelope là một phần của payload công khai. Schema cần giữ object envelope cùng các thuộc tính traceId, data và message. Springdoc không nên bỏ lớp này chỉ vì tên kiểu có chữ Response hoặc Envelope.

Chỉ bỏ lớp bao khi wrapper không xuất hiện trong dữ liệu JSON truyền trên dây và cơ chế xử lý thực sự chuyển nó thành payload bên trong. Với wrapper tùy biến, không nên giả định Springdoc tự nhận biết. Hãy kiểm tra serializer, controller return handler và OpenAPI document.

Nếu tổ chức muốn công bố một schema envelope chung, hãy mô tả nó như DTO bình thường và dùng generic type cụ thể. Nếu dùng custom converter hoặc response advice để thay đổi payload, tài liệu OpenAPI phải phản ánh cấu trúc sau cùng mà client nhận được.

## 12. Khi nào cần khai báo response schema tường minh?

Springdoc thường suy luận được schema từ kiểu trả về cụ thể. Có thể cần mô tả tường minh khi:

- Phương thức trả về ResponseEntity raw hoặc wildcard.
- Generic type bị mất do kiểu trung gian hoặc method signature.
- Một operation có nhiều response code với body schema khác nhau.
- Body thành công và body lỗi dùng DTO khác nhau.
- Response có header quan trọng hoặc content type đặc biệt.
- Schema thực tế chịu ảnh hưởng bởi custom serializer hoặc ResponseBodyAdvice.

Ví dụ:

~~~java
@GetMapping("/api/products/{id}")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy sản phẩm",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy sản phẩm",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<?> findById(@PathVariable Long id) {
    // Trả về ProductResponse hoặc response lỗi theo logic ứng dụng
}
~~~

Trong ví dụ này, kiểu wildcard không cho biết schema cụ thể. Annotation mô tả riêng body của từng response code. Trong ứng dụng thật, nên cân nhắc dùng kiểu trả về rõ hơn nếu có thể để compiler, người đọc và Springdoc cùng hiểu hợp đồng.

Không nên dùng `@Schema(implementation = ...)` để ép tài liệu hiển thị một kiểu không khớp body thực tế. Annotation chỉ mô tả; nó không chuyển đổi object runtime sang schema được khai báo.

## 13. Mô tả status code và response body riêng biệt

ResponseEntity có thể trả các status code khác nhau tùy logic. Kiểu generic T không đủ để mô tả tất cả nhánh kết quả.

Ví dụ một endpoint có thể trả:

| Status | Ý nghĩa | Body |
|---|---|---|
| 200 | Tìm thấy sản phẩm | ProductResponse |
| 404 | Không tìm thấy | Không body hoặc ApiError tùy hợp đồng |
| 304 | Tài nguyên không thay đổi | Không body |
| 500 | Lỗi hệ thống | ApiError nếu ứng dụng công bố |

Nên dùng `@ApiResponse` hoặc `@ApiResponses` để công bố những trường hợp quan trọng. Nếu có response mặc định hoặc lỗi dùng chung, có thể cấu hình mô tả dùng chung theo cơ chế Springdoc phù hợp.

Cũng cần phân biệt status code được trả thật với status code được mô tả. `@ApiResponse(responseCode = "404")` không làm controller tự trả 404. Code phải thực sự trả status đó thông qua ResponseEntity, exception handler hoặc cơ chế tương ứng.

## 14. Kiểm tra quy tắc bỏ lớp bao trong tài liệu sinh ra

Sau khi khởi động ứng dụng, tải OpenAPI JSON:

~~~http
GET /v3/api-docs
~~~

Với từng operation có ResponseEntity hoặc Optional, kiểm tra:

1. Schema của response có phải kiểu payload thực tế hay đang mô tả wrapper Java không cần thiết.
2. Generic type bên trong ResponseEntity được giữ đúng, nhất là List, Map và DTO.
3. ResponseEntity<Void> không tạo schema body sai.
4. Status code 200, 201, 204, 404 và các nhánh lỗi được công bố đúng.
5. Response header như Location được mô tả nếu client cần dùng.
6. Optional<T> có được phân giải theo khả năng hỗ trợ của phiên bản đang dùng không.
7. Optional.empty() có hành vi runtime đúng với status và content đã công bố.
8. Wrapper tùy biến có được giữ lại nếu nó thực sự là JSON payload.
9. Ví dụ response khớp schema và JSON thực tế.

Có thể kiểm thử bằng integration test cho cả trường hợp có dữ liệu và không có dữ liệu. Kiểm tra status code, Content-Type, header, body và cấu trúc JSON. Với wrapper tùy biến hoặc serializer đặc biệt, cần kiểm tra trực tiếp response đã serialize.

Một số lỗi thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI hiển thị ResponseEntity như object | Bộ phân giải kiểu không nhận diện wrapper hoặc kiểu trả về khai báo raw |
| Schema body là object rỗng | Generic type bị mất hoặc DTO không được phân giải |
| Optional được mô tả thành object không mong muốn | Phiên bản thư viện hoặc model resolver chưa hỗ trợ kiểu wrapper |
| Optional.empty() trả status không như mong đợi | Chưa ánh xạ trường hợp vắng mặt sang ResponseEntity hoặc exception |
| Tài liệu chỉ có 200 dù code có 404 | Chưa khai báo các response code động bằng @ApiResponse |
| Header Location không xuất hiện | Chưa mô tả response header trong OpenAPI |
| Envelope bị bỏ khỏi schema | Cấu hình tùy biến hoặc annotation đang mô tả sai payload thực tế |
| Schema khai báo body nhưng runtime không trả body | ResponseEntity<Void>, status 204 hoặc nhánh build response không có body |

## 15. Nguyên tắc sử dụng ResponseEntity và Optional

Khi thiết kế response với Springdoc OpenAPI, hãy giữ các nguyên tắc sau:

1. Dùng ResponseEntity để điều khiển HTTP status, header và body khi cần quyết định động.
2. Xem generic type T là payload để Springdoc mô tả; kiểm tra việc bỏ lớp bao trong phiên bản dự án.
3. Dùng ResponseEntity<Void> hoặc response không có content khi HTTP response không có body.
4. Dùng Optional ở tầng service/repository để biểu đạt kết quả có thể không tìm thấy.
5. Ánh xạ Optional.empty() thành status và body rõ ràng ở controller.
6. Không giả định Optional.empty() tự động có nghĩa là 404 hoặc 204.
7. Tránh lồng ResponseEntity<Optional<T>> nếu có thể biểu đạt trường hợp vắng mặt bằng status.
8. Giữ wrapper tùy biến trong schema nếu nó là một phần JSON payload.
9. Dùng @ApiResponse để mô tả status, schema và header của từng nhánh.
10. Kiểm tra OpenAPI JSON/YAML cùng response runtime sau khi thay đổi kiểu trả về.

ResponseEntity và Optional phục vụ hai mục đích khác nhau: một kiểu điều khiển HTTP response, kiểu còn lại biểu đạt sự hiện diện của giá trị trong Java. Springdoc có thể bỏ những lớp bao được hỗ trợ để mô tả payload, nhưng hợp đồng API vẫn phải công bố rõ status, header, content và hành vi khi không có dữ liệu. Khi controller ánh xạ các trường hợp này tường minh, tài liệu OpenAPI sẽ gần với response mà client thực sự nhận được.


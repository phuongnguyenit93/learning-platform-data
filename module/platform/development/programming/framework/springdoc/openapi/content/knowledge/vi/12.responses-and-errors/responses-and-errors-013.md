# Giữ nhất quán giữa mã trạng thái được ghi trong tài liệu và phản hồi thực

Một đặc tả OpenAPI hữu ích phải mô tả đúng những gì client nhận được khi gọi API. Nếu tài liệu ghi một operation trả HTTP 404 với body ApiError nhưng ứng dụng lại trả 200 với body rỗng, client sẽ xử lý sai dù Swagger UI vẫn hiển thị hợp lệ. Tương tự, tài liệu có thể ghi 201 nhưng controller trả 200, hoặc mô tả header Location mà response thực tế không có header đó.

Với springdoc-openapi, metadata từ controller và DTO được chuyển thành tài liệu OpenAPI. Tài liệu có thể được suy ra từ kiểu trả về, mapping và annotation; phản hồi thực tế lại do Spring MVC, ResponseEntity, @ResponseStatus, exception handler, Spring Security và gateway quyết định. Bài này trình bày cách giữ hai phía đồng bộ và kiểm tra chúng bằng test tự động.

## 1. Phân biệt hợp đồng response với phản hồi runtime

Có hai kết quả cần đối chiếu:

- **Hợp đồng OpenAPI:** mô tả status code, description, response body, schema, media type và header mà client có thể nhận.
- **Phản hồi runtime:** HTTP response thực tế do ứng dụng hoặc hạ tầng trả về khi nhận request.

springdoc-openapi tạo hợp đồng từ mã nguồn và metadata. Thư viện không chạy từng nhánh nghiệp vụ để xác nhận response. Ví dụ, khai báo @ApiResponse(responseCode = "404") không khiến controller tự trả HTTP 404; khai báo schema ApiError cũng không tự tạo body lỗi.

Một response chỉ nhất quán khi các thông tin sau khớp nhau:

| Thành phần | Trong OpenAPI | Khi chạy |
|---|---|---|
| Status code | responses["404"] | HTTP status thực tế là 404 |
| Body | content và schema | JSON/XML/text thực tế được gửi |
| Media type | application/json, application/pdf... | Header Content-Type |
| Header | headers như Location, ETag, Retry-After | Header thực tế trong response |
| Ý nghĩa | description của response | Hành vi nghiệp vụ tương ứng |
| Điều kiện phát sinh | Mô tả operation và response | Nhánh controller, exception handler, security hoặc gateway |

Không chỉ so sánh mã HTTP. Body có thể sai schema, Content-Type có thể không đúng, hoặc header được công bố nhưng không được gửi.

## 2. Những nguồn quyết định status code trong Spring

Trong ứng dụng Spring Boot, status code có thể được quyết định bởi nhiều cơ chế:

| Cơ chế | Tác dụng |
|---|---|
| Giá trị trả về thông thường của controller | Spring thường trả 200 OK khi xử lý thành công và có body |
| @ResponseStatus | Đặt status cố định cho handler hoặc exception được đánh dấu |
| ResponseEntity | Cho phép chọn status, headers và body theo từng nhánh |
| @ExceptionHandler / @RestControllerAdvice | Ánh xạ exception thành HTTP response |
| Spring Security | Xử lý xác thực và phân quyền trước hoặc ngoài controller |
| Reverse proxy / API gateway | Có thể từ chối, giới hạn tốc độ hoặc tạo response trước khi request tới ứng dụng |

Vì có nhiều nguồn quyết định, việc đọc riêng controller method chưa đủ để biết mọi response runtime. Hãy kiểm tra exception handler, security configuration và gateway policy có liên quan.

Ví dụ controller trả về một object:

~~~java
@GetMapping("/{id}")
public OrderResponse getOrder(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

Nếu method trả object bình thường, Spring thường tạo response 200 khi xử lý thành công. Nhưng nếu service ném OrderNotFoundException, status phụ thuộc exception handler hoặc cơ chế xử lý exception khác.

Nếu controller cần trả nhiều status code theo kết quả, ResponseEntity thể hiện rõ từng nhánh:

~~~java
@GetMapping("/{id}")
public ResponseEntity<?> getOrder(@PathVariable String id) {
    return orderService.findById(id)
        .<ResponseEntity<?>>map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                "ORDER_NOT_FOUND",
                "Không tìm thấy đơn hàng",
                null
            )));
}
~~~

Trong ví dụ này, nhánh không tìm thấy trả 404 cùng body ApiError. Nếu API chọn ResponseEntity.notFound().build() thay cho body lỗi, schema OpenAPI và test phải phản ánh response không có body.

## 3. @ApiResponse mô tả, còn @ResponseStatus và ResponseEntity thực thi

Các annotation OpenAPI dùng để công bố hợp đồng:

~~~java
@ApiResponse(
    responseCode = "201",
    description = "Đã tạo đơn hàng",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderResponse.class)
    )
)
~~~

Đoạn trên chỉ mô tả phản hồi 201 và schema OrderResponse. Muốn controller thật sự trả 201, cần cơ chế runtime phù hợp, ví dụ:

~~~java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Hoặc:

~~~java
@PostMapping
public ResponseEntity<OrderResponse> create(
    @RequestBody CreateOrderRequest request
) {
    OrderResponse created = orderService.create(request);
    URI location = URI.create("/api/orders/" + created.getId());

    return ResponseEntity.created(location).body(created);
}
~~~

ResponseEntity.created(location) trả 201 Created và header Location. Nếu OpenAPI mô tả Location, response runtime phải gửi header đó.

Có thể kết hợp metadata và implementation:

~~~java
@PostMapping
@Operation(
    operationId = "createOrder",
    summary = "Tạo đơn hàng mới"
)
@ApiResponse(
    responseCode = "201",
    description = "Đơn hàng đã được tạo",
    headers = @Header(
        name = "Location",
        description = "URL của đơn hàng vừa tạo",
        schema = @Schema(type = "string", format = "uri")
    ),
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderResponse.class)
    )
)
public ResponseEntity<OrderResponse> create(
    @RequestBody CreateOrderRequest request
) {
    OrderResponse created = orderService.create(request);
    URI location = URI.create("/api/orders/" + created.getId());
    return ResponseEntity.created(location).body(created);
}
~~~

Khi review, kiểm tra đồng thời annotation và câu lệnh trả response. Không suy ra status runtime từ responseCode trong annotation.

## 4. Ánh xạ exception sang response nhất quán

Các lỗi nghiệp vụ thường được biểu diễn bằng exception và xử lý tập trung qua @RestControllerAdvice. Ví dụ:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(
        OrderNotFoundException exception
    ) {
        ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            "Không tìm thấy đơn hàng",
            null
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }

    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ApiError> handleConflict(
        OrderConflictException exception
    ) {
        ApiError body = new ApiError(
            "ORDER_CONFLICT",
            "Đơn hàng đã thay đổi",
            null
        );
        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }
}
~~~

Nếu operation có thể phát sinh hai exception trên, tài liệu cần công bố 404 và 409 với schema ApiError. Việc khai báo response tại controller không tự tạo ánh xạ exception; việc khai báo @ExceptionHandler cũng không tự bảo đảm mọi operation đã có metadata OpenAPI tương ứng.

Một quy ước mapping có thể dùng trong nhóm:

| Tình huống | Status thường dùng | Kiểm tra runtime |
|---|---:|---|
| Request sai cú pháp hoặc không chuyển đổi được kiểu | 400 | Jackson/Spring MVC từ chối request |
| Dữ liệu không đạt validation | 400 hoặc 422 theo chính sách API | Bean Validation và exception handler |
| Chưa xác thực | 401 | AuthenticationEntryPoint hoặc security filter |
| Đã xác thực nhưng không có quyền | 403 | AccessDeniedHandler hoặc security policy |
| Tài nguyên không tồn tại | 404 | Controller hoặc exception handler |
| Xung đột trạng thái hoặc phiên bản | 409 | Quy tắc nghiệp vụ |
| Vượt giới hạn request | 429 | Rate limiter hoặc gateway |
| Lỗi ngoài dự kiến | 500 | Exception handler hoặc container |

Đây là các lựa chọn thường gặp, không phải mapping bắt buộc cho mọi ứng dụng. Điều quan trọng là nhóm chọn chính sách nhất quán, triển khai đúng và mô tả chính sách đó trong spec.

## 5. Đừng quên response do Spring Security tạo ra

Request bị chặn bởi Spring Security có thể chưa đi tới controller. Vì vậy, @RestControllerAdvice không nhất thiết xử lý các response xác thực và phân quyền.

Thông thường:

- AuthenticationEntryPoint quyết định phản hồi khi người gọi chưa được xác thực hoặc thông tin xác thực không hợp lệ.
- AccessDeniedHandler quyết định phản hồi khi người gọi đã xác thực nhưng không đủ quyền.

Nếu API dùng JSON error body thống nhất, hãy cấu hình hai handler này để trả cùng cấu trúc hoặc cấu trúc được mô tả trong OpenAPI. Kiểm tra status, body, Content-Type và các header bảo mật cần thiết.

OpenAPI có thể mô tả security requirement ở cấp tài liệu hoặc operation, đồng thời liệt kê response 401 và 403. Tuy nhiên, security scheme chỉ mô tả cách client gửi thông tin xác thực; nó không cấu hình Spring Security.

Một endpoint công khai có thể không có 401 hoặc 403. Một endpoint bảo vệ bằng bearer token có thể có cả hai. Chỉ công bố các mã phù hợp với chính sách thực tế.

## 6. So sánh status code với ngữ nghĩa HTTP

Dùng đúng mã status giúp client biết cần làm gì tiếp theo. Một số nhầm lẫn thường gặp:

| Mã | Ý nghĩa | Điều cần xác minh |
|---|---|---|
| 200 OK | Request thành công | Body có đúng schema không? |
| 201 Created | Đã tạo tài nguyên | Location có được trả nếu API cam kết không? |
| 202 Accepted | Đã nhận yêu cầu để xử lý | Có cách theo dõi tác vụ không? |
| 204 No Content | Thành công, không có body | Response có thực sự rỗng không? |
| 400 Bad Request | Request không hợp lệ | Lỗi parse, binding hoặc validation có được ánh xạ đúng không? |
| 401 Unauthorized | Thiếu hoặc không hợp lệ thông tin xác thực | Có challenge/header cần thiết không? |
| 403 Forbidden | Không được phép truy cập | Body và status có khớp security policy không? |
| 404 Not Found | Không tìm thấy tài nguyên hoặc endpoint | Có tránh tiết lộ tài nguyên mà người dùng không được xem không? |
| 409 Conflict | Xung đột với trạng thái hiện tại | Client có đủ thông tin để giải quyết xung đột không? |
| 422 Unprocessable Content | Nội dung hiểu được nhưng không xử lý được theo quy tắc | API có dùng 422 nhất quán thay cho 400 không? |
| 429 Too Many Requests | Quá nhiều request trong khoảng thời gian | Có Retry-After hoặc thông tin quota không? |
| 500 Internal Server Error | Lỗi ngoài dự kiến của server | Không để lộ stack trace hoặc dữ liệu nội bộ |

Đặc biệt, 202 không có nghĩa tác vụ đã hoàn tất; 204 không được mang response body; 401 và 403 có ý nghĩa khác nhau; 409 thường dùng cho xung đột trạng thái chứ không phải mọi lỗi validation.

## 7. Đảm bảo body và schema khớp nhau

Giả sử OpenAPI mô tả lỗi:

~~~yaml
ApiError:
  type: object
  required:
    - code
    - message
  properties:
    code:
      type: string
    message:
      type: string
    traceId:
      type: string
~~~

Response runtime cần có cấu trúc tương ứng:

~~~json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Không tìm thấy đơn hàng",
  "traceId": "req-7f9a2c"
}
~~~

Nếu exception handler thực tế trả về một object khác, ví dụ Spring ProblemDetail với các trường type, title, status, detail và instance, schema ApiError sẽ không mô tả đúng response đó.

Với Spring Framework 6+, ProblemDetail là một lựa chọn chuẩn hóa lỗi theo Problem Details. Nếu ứng dụng sử dụng ProblemDetail, hãy mô tả schema phù hợp và kiểm tra JSON được serialize. Không khai báo ApiError chỉ vì đó là DTO lỗi mà nhóm dự định dùng; hãy kiểm tra body thực tế.

Những điểm cần so sánh:

- Tên field, kiểu dữ liệu và nesting.
- Field bắt buộc, nullable và giá trị có thể vắng mặt.
- Enum và định dạng ngày/giờ.
- Cấu trúc danh sách lỗi validation.
- Tên và ý nghĩa mã lỗi.
- Thông tin nhạy cảm không được phép gửi cho client.

Một schema có thể hợp lệ theo cú pháp nhưng vẫn sai về ngữ nghĩa so với body runtime.

## 8. Đảm bảo media type khớp Content-Type

Trong OpenAPI, response content khai báo media type như application/json, application/xml, text/csv hoặc application/pdf. Khi chạy, HTTP response có header Content-Type tương ứng.

Ví dụ tài liệu:

~~~yaml
responses:
  '200':
    description: Thông tin sản phẩm
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ProductResponse'
~~~

Nếu controller trả JSON nhưng Content-Type lại là text/plain, client generator có thể xử lý body sai. Nếu endpoint tải PDF nhưng spec ghi application/json, client có thể cố deserialize bytes thành JSON.

Hãy kiểm tra:

- @RequestMapping(produces = ...) và cấu hình message converter.
- Content-Type của response thực tế.
- Accept header của request nếu endpoint hỗ trợ nhiều representation.
- Schema tương ứng cho từng media type.
- Cách xử lý file hoặc stream của client generator.

Không khai báo một media type trong OpenAPI chỉ vì muốn Swagger UI hiển thị lựa chọn đó. Ứng dụng phải thực sự hỗ trợ loại nội dung đó.

## 9. Đảm bảo header được mô tả và gửi thực tế

Một số header quan trọng thuộc response contract:

| Header | Mục đích |
|---|---|
| Location | Địa chỉ tài nguyên vừa tạo hoặc tác vụ cần theo dõi |
| ETag | Định danh phiên bản representation |
| Retry-After | Thời gian hoặc thời điểm client nên thử lại |
| X-Request-Id | Mã truy vết request nếu API công bố |
| Cache-Control | Chính sách cache |

Nếu OpenAPI mô tả Location cho 201, test cần xác nhận response có Location. Nếu tài liệu mô tả Retry-After cho 429, rate limiter/gateway phải gửi header đó theo chính sách.

Ví dụ khai báo:

~~~java
@ApiResponse(
    responseCode = "201",
    description = "Đã tạo tài nguyên",
    headers = @Header(
        name = "Location",
        description = "URL của tài nguyên mới",
        schema = @Schema(type = "string", format = "uri")
    )
)
~~~

Annotation không tự tạo header. Controller hoặc thành phần hạ tầng phải gửi header tương ứng.

## 10. Tạo test kiểm tra response thực tế bằng MockMvc

MockMvc phù hợp để kiểm tra controller trong Spring MVC mà không cần khởi động server thật. Test nên xác nhận status, media type, header và body.

Ví dụ test nhánh không tìm thấy:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returns404WithApiErrorWhenOrderDoesNotExist() throws Exception {
        given(orderService.findById("missing"))
            .willReturn(Optional.empty());

        mockMvc.perform(get("/api/orders/{id}", "missing"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
            .andExpect(jsonPath("$.message").value("Không tìm thấy đơn hàng"));
    }
}
~~~

Tên annotation mock trong test phụ thuộc phiên bản Spring Boot và Spring Test. Với phiên bản chưa có @MockitoBean, dự án có thể dùng @MockBean. Hãy dùng API tương thích với dependency đang cài.

Test nhánh tạo mới có thể xác nhận 201 và Location:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":"C-100","items":[{"productId":"P-1","quantity":2}]}
            """))
    .andExpect(status().isCreated())
    .andExpect(header().exists(HttpHeaders.LOCATION))
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.id").isNotEmpty());
~~~

Đây là ví dụ minh họa. Cần chuẩn bị service, DTO và dữ liệu test theo ứng dụng. Với response 204, kiểm tra status và bảo đảm không có body. Với lỗi validation, gửi request sai và kiểm tra status cùng cấu trúc lỗi mà exception handler cam kết.

## 11. Kiểm tra response OpenAPI bằng test

Ngoài test HTTP, có thể kiểm tra tài liệu được springdoc sinh ra. Khi ứng dụng test đã nạp cấu hình OpenAPI, endpoint /v3/api-docs có thể được gọi qua MockMvc:

~~~java
@Test
void openApiDocumentsOrderResponses() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['200']"
        ).exists())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['404']"
        ).exists())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['404'].content['application/json'].schema"
        ).exists());
}
~~~

Test này kiểm tra metadata có được công bố, nhưng chưa chứng minh status 404 thực tế. Vì vậy, cần cả hai nhóm test:

1. **OpenAPI test:** xác minh spec có status, schema, media type và header cần thiết.
2. **Runtime test:** gửi request và xác minh status, body, Content-Type, header.

Có thể bổ sung assertion sâu hơn để kiểm tra $ref trỏ tới component tồn tại, hoặc dùng validator OpenAPI trong CI. Với tài liệu chia group, gọi endpoint của từng group cần được kiểm tra riêng.

## 12. Kiểm thử tích hợp qua server thật

MockMvc không đi qua toàn bộ hạ tầng triển khai như reverse proxy, gateway, TLS termination hoặc rate limiter bên ngoài. Nếu public contract bao gồm response do hạ tầng tạo ra, cần test ở môi trường tích hợp.

Với ứng dụng servlet, có thể dùng @SpringBootTest(webEnvironment = RANDOM_PORT) và HTTP client test để gọi server đang chạy. Với WebFlux, có thể dùng WebTestClient.

Một kiểm tra tích hợp nên xác nhận:

- URL public và path prefix.
- Status code sau khi request đi qua gateway.
- Content-Type và body.
- Header bảo mật, CORS, Location hoặc Retry-After nếu có.
- Response khi thiếu token, token sai hoặc thiếu quyền.
- Response khi vượt rate limit.
- Response lỗi khi backend không khả dụng, nếu gateway có cam kết định dạng lỗi.

Không phải mọi response gateway đều do ứng dụng Spring tạo. Nếu gateway thay đổi status hoặc body, spec public phải mô tả hành vi mà client thật sự nhìn thấy, hoặc tài liệu cần nói rõ phạm vi của API backend và gateway.

## 13. So sánh tự động OpenAPI và runtime contract

Một cách kiểm soát là lưu OpenAPI JSON thành artifact và dùng test/contract tooling để so sánh:

- Mã status được công bố với status từ integration test.
- Schema response với JSON body thực tế.
- Media type với Content-Type.
- Header đã công bố với header thực tế.
- Các operation đã thay đổi so với bản spec được phát hành.

Có thể viết test riêng cho những operation quan trọng, hoặc dùng contract testing framework để xác minh consumer/provider. Dù dùng công cụ nào, test cần dựa trên response thực tế hoặc fixture có nguồn từ implementation. Một file OpenAPI tự so sánh với chính nó không thể phát hiện controller trả sai status.

Nếu nhóm lưu snapshot spec, nên review diff khi thay đổi controller, DTO, exception handler, security hoặc gateway. Thay đổi status code có thể là breaking change vì client thường phân nhánh logic theo mã HTTP.

## 14. Những sai lệch thường gặp

| Sai lệch | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Spec ghi 201 nhưng runtime trả 200 | Chỉ thêm @ApiResponse, chưa đặt status thực tế | Dùng ResponseEntity.created hoặc @ResponseStatus(CREATED) |
| Spec ghi 404 với ApiError nhưng runtime không có body | Controller dùng notFound().build() | Trả body lỗi hoặc sửa schema thành response không body |
| Runtime trả 409 nhưng spec chỉ có 400 | Thiếu mô tả exception nghiệp vụ | Thêm @ApiResponse 409 và test |
| Spec có Location nhưng runtime thiếu header | Chỉ khai báo metadata | Thêm header vào ResponseEntity và kiểm tra test |
| Spec ghi application/json nhưng runtime trả text/plain | Media type hoặc message converter không khớp | Đồng bộ produces, Content-Type và OpenAPI content |
| Security trả 401/403 nhưng spec không có | Chưa mô tả security responses | Khai báo response và security requirement phù hợp |
| Gateway trả 429 nhưng spec không có | Rate limit nằm ngoài ứng dụng | Bổ sung hợp đồng public và test qua gateway |
| Body lỗi khác schema | Exception handler trả DTO khác | Dùng đúng schema hoặc sửa response DTO |
| 204 được mô tả có body | Response annotation khai báo content không phù hợp | Bỏ content và kiểm tra body rỗng |
| Test chỉ kiểm tra status | Chưa xác minh body, header và media type | Bổ sung assertion cho toàn bộ response contract |

## 15. Quy trình review khi thay đổi response

Khi sửa controller hoặc cách xử lý lỗi, thực hiện theo trình tự:

1. Xác định tất cả nhánh có thể trả về từ controller, service và exception handler.
2. Kiểm tra security filter, gateway hoặc rate limiter có thể tạo response riêng không.
3. Cập nhật implementation để status, body, media type và header đúng với chính sách API.
4. Cập nhật @ApiResponse/@ApiResponses và schema tương ứng.
5. Tải /v3/api-docs và kiểm tra kết quả thực tế của springdoc.
6. Chạy test runtime cho từng nhánh status quan trọng.
7. So sánh spec mới với bản đã phát hành và đánh giá ảnh hưởng client.
8. Lưu spec và kết quả test làm artifact có thể truy vết.

Nếu một status code không còn xảy ra, hãy xóa hoặc cập nhật metadata cũ. Nếu thêm nhánh mới, hãy bổ sung cả implementation, tài liệu và test trong cùng thay đổi.

## 16. Checklist đảm bảo tính nhất quán

- [ ] Status code trong @ApiResponse khớp với response runtime.
- [ ] Mọi nhánh ResponseEntity đã được mô tả.
- [ ] Exception handler có mapping status và schema tương ứng.
- [ ] Security responses 401/403 phản ánh cấu hình thực tế.
- [ ] Gateway responses như 429 được tính đến nếu thuộc public contract.
- [ ] Body runtime khớp schema, gồm field, kiểu, enum và nullable.
- [ ] Content-Type khớp media type trong OpenAPI.
- [ ] Header Location, ETag, Retry-After... được gửi khi đã công bố.
- [ ] Response 204 không có body.
- [ ] Test kiểm tra cả status, body, header và media type.
- [ ] OpenAPI test xác minh responses và schema tại /v3/api-docs.
- [ ] Test tích hợp bao phủ các response do hạ tầng tạo ra nếu cần.
- [ ] Spec mới được so sánh với bản phát hành trước.

## 17. Nguồn tra cứu

- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object)
- [OpenAPI Specification – Response Object](https://spec.openapis.org/oas/latest.html#response-object)
- [Spring Framework – ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring Framework – Exception handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring Security – Exception translation](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)

springdoc-openapi tạo tài liệu từ controller và metadata, còn Spring MVC, exception handling, security và gateway tạo phản hồi khi chạy. Hãy kiểm tra cả OpenAPI JSON lẫn HTTP response thực tế. Khi hai phía được kiểm tra trong cùng quy trình CI, thay đổi status hoặc schema sẽ được phát hiện trước khi client nhận một hợp đồng sai lệch.

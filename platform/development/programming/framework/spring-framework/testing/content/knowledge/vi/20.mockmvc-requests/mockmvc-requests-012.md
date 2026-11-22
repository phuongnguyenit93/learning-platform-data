# Giữ dữ liệu yêu cầu gần hợp đồng HTTP thực tế

MockMvc cho phép kiểm thử Spring MVC mà không cần mở cổng HTTP thật. Tuy nhiên, một bài test chỉ phản ánh đúng cách client sử dụng API khi dữ liệu gửi vào có hình dạng gần với request HTTP mà client thực sự tạo ra. Nếu test truyền dữ liệu theo cách tiện nhất cho Java nhưng khác hợp đồng HTTP, test có thể vẫn xanh trong khi ứng dụng gặp lỗi khi nhận request từ trình duyệt, mobile app hoặc service khác.

Khi viết test MockMvc, hãy mô tả request bằng các thành phần HTTP rõ ràng: method, path, query string, header, content type, body, cookie và thông tin xác thực. Với JSON, hãy gửi JSON thực tế. Với form, hãy gửi form parameter. Với upload, hãy gửi multipart part. Mỗi loại dữ liệu cần đi qua đúng cơ chế binding mà ứng dụng sử dụng trong môi trường thật.

## 1. Hợp đồng HTTP gồm những gì?

Một HTTP request không chỉ là một object DTO. Request có cấu trúc ở tầng giao thức:

~~~text
POST /api/orders?source=mobile HTTP/1.1
Host: example.test
Accept: application/json
Content-Type: application/json
Idempotency-Key: 7c9f...

{
  "sku": "COFFEE-01",
  "quantity": 2,
  "deliveryDate": "2026-11-20"
}
~~~

Các phần trên có ý nghĩa riêng:

| Thành phần | Ý nghĩa trong request | Cách thể hiện trong MockMvc |
|---|---|---|
| HTTP method | Hành động client yêu cầu | `get`, `post`, `put`, `patch`, `delete` |
| Path | Tài nguyên hoặc endpoint | URI truyền vào request builder |
| Path variable | Định danh nằm trong path | URI template và giá trị thay thế |
| Query parameter | Bộ lọc, phân trang hoặc tùy chọn trong URL | `queryParam` hoặc URI đã encode |
| Header | Metadata, thương lượng nội dung, xác thực, điều kiện request | `header`, `accept`, `contentType` |
| Body | Dữ liệu gửi lên server | `content`, `contentType` |
| Form parameter | Trường biểu mẫu | `param` cùng content type phù hợp |
| Cookie/session | Trạng thái phía client hoặc phiên đăng nhập | `cookie`, `session` |
| Multipart part | File hoặc từng phần dữ liệu của upload | `multipart` và `file` |

Controller có thể nhận một Java object, nhưng object đó thường được tạo ra sau khi Spring xử lý các thành phần HTTP. Ví dụ, `@RequestBody` dùng message converter để đọc body; `@RequestParam` đọc request parameter; `@PathVariable` lấy giá trị từ path; `@RequestHeader` lấy header. Nếu test bỏ qua các ranh giới này, nó không kiểm tra đầy đủ hợp đồng mà client phải tuân theo.

## 2. Gửi JSON như một client thật

Giả sử API tạo đơn hàng nhận JSON:

~~~java
public record CreateOrderRequest(
        String sku,
        int quantity,
        LocalDate deliveryDate,
        String note
) {
}
~~~

Controller nhận body bằng `@RequestBody`:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse response = orderService.create(request);
        return ResponseEntity
                .created(URI.create("/api/orders/" + response.id()))
                .body(response);
    }
}
~~~

Một request JSON nên khai báo rõ cả content type và accept:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "sku": "COFFEE-01",
                  "quantity": 2,
                  "deliveryDate": "2026-11-20",
                  "note": "Deliver before noon"
                }
                """))
    .andExpect(status().isCreated())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.id").isNotEmpty())
    .andExpect(jsonPath("$.sku").value("COFFEE-01"));
~~~

`contentType` mô tả định dạng body gửi lên. `accept` mô tả định dạng response mà client chấp nhận. Hai header này phục vụ hai chiều khác nhau; đặt `accept` không thay thế `contentType`.

Không nên truyền trực tiếp một DTO Java vào `content(...)`. Phương thức này nhận nội dung body, thường là chuỗi hoặc byte array. Hãy gửi JSON đã serialize:

~~~java
String json = objectMapper.writeValueAsString(request);

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content(json));
~~~

ObjectMapper nên được inject từ Spring test context khi muốn dùng cùng cấu hình Jackson với ứng dụng, chẳng hạn naming strategy, module cho Java Time, custom serializer hoặc format ngày tháng. Cách này giúp test gửi JSON theo cấu hình serialization đang dùng trong ứng dụng.

Tuy nhiên, nếu test serialize DTO bằng chính ObjectMapper của ứng dụng rồi dùng kết quả đó làm request, test có thể che giấu một số sai lệch của hợp đồng JSON. Ví dụ, nếu cả serializer và deserializer cùng đổi tên property ngoài dự kiến, test vẫn có thể chạy qua. Với các trường quan trọng của public API, nên có thêm JSON fixture viết theo hợp đồng client nhìn thấy:

~~~json
{
  "sku": "COFFEE-01",
  "quantity": 2,
  "deliveryDate": "2026-11-20",
  "note": null
}
~~~

Fixture giúp cố định tên field, kiểu dữ liệu và cách biểu diễn trên wire. Có thể đặt fixture trong `src/test/resources/http/requests/` và đọc bằng classpath resource để nhiều test dùng cùng một ví dụ đầu vào. Khi hợp đồng thay đổi có chủ đích, cập nhật fixture cùng với tài liệu API và client liên quan.

## 3. Chọn dữ liệu JSON phản ánh đúng kiểu dữ liệu

JSON có các kiểu dữ liệu riêng. Những giá trị trông giống nhau trong Java chưa chắc giống nhau trên HTTP:

~~~json
{
  "quantity": 2,
  "unitPrice": 125000.50,
  "enabled": true,
  "sku": "000123",
  "note": null,
  "tags": ["gift", "fragile"]
}
~~~

- `quantity` là number, không phải chuỗi `"2"`.
- `unitPrice` là number. Với tiền tệ, ứng dụng nên xác định rõ kiểu và quy tắc làm tròn; không so sánh số thực nhị phân bằng phép so sánh chính xác nếu nghiệp vụ cần độ chính xác thập phân.
- `enabled` là boolean, không phải `"true"`.
- `sku` là string để giữ số 0 ở đầu. Không nên biến mã định danh thành number chỉ vì nội dung có chữ số.
- `note: null` khác với việc không gửi field `note`. Tùy chính sách Jackson và DTO, hai trường hợp có thể được xử lý khác nhau.
- `tags` là array. Nếu thứ tự phần tử có ý nghĩa, test cần giữ và xác nhận thứ tự đó.

Với ngày giờ, hãy dùng định dạng đã công bố trong API. Ví dụ:

~~~json
{
  "deliveryDate": "2026-11-20",
  "createdAt": "2026-11-13T02:30:00Z",
  "requestedAt": "2026-11-13T09:30:00+07:00"
}
~~~

`LocalDate` thường được biểu diễn bằng ngày ISO như `2026-11-20`. Thời điểm cần xác định múi giờ nên có `Z` hoặc offset rõ ràng. Không dùng chuỗi ngày phụ thuộc locale của máy như `11/20/2026`, trừ khi hợp đồng API thực sự yêu cầu định dạng đó. Tránh dựa vào timezone mặc định của máy chạy test vì CI và máy lập trình viên có thể khác nhau.

Với enum, hãy gửi đúng giá trị wire đã công bố, ví dụ `"PENDING"` hoặc `"PAID"`. Không giả định client có thể gửi ordinal số của enum Java. Nếu API hỗ trợ alias hoặc chữ thường, viết test cho từng dạng được hỗ trợ và từ chối rõ ràng giá trị không hợp lệ.

## 4. Dùng query parameter và path variable đúng vị trí

Giả sử endpoint tìm đơn hàng có dạng:

~~~text
GET /api/orders?status=PAID&page=0&size=20
GET /api/orders/{orderId}
~~~

Query parameter thuộc URL. Có thể dùng `queryParam` của MockMvc request builder:

~~~java
mockMvc.perform(get("/api/orders")
        .queryParam("status", "PAID")
        .queryParam("page", "0")
        .queryParam("size", "20")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page").value(0));
~~~

Path variable phải nằm trong path:

~~~java
UUID orderId = UUID.fromString(
        "4c6d8e10-1234-4567-8901-123456789abc");

mockMvc.perform(get("/api/orders/{orderId}", orderId)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(orderId.toString()));
~~~

Không chuyển path variable thành query parameter chỉ vì controller cuối cùng cũng nhận một chuỗi. Hai URL sau là hai hợp đồng khác nhau:

~~~text
/api/orders/4c6d8e10-1234-4567-8901-123456789abc
/api/orders?id=4c6d8e10-1234-4567-8901-123456789abc
~~~

Nếu query có ký tự đặc biệt như dấu cách, dấu cộng, dấu và hoặc ký tự Unicode, hãy kiểm tra cách encode. Ví dụ, chuỗi tìm kiếm `tea & coffee` không được nối thẳng vào URL mà không encode, vì dấu `&` phân tách query parameter. Có thể tạo URI bằng `UriComponentsBuilder`:

~~~java
URI uri = UriComponentsBuilder
        .fromPath("/api/products")
        .queryParam("q", "{keyword}")
        .encode()
        .buildAndExpand("tea & coffee")
        .toUri();

mockMvc.perform(get(uri)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
~~~

Khi API nhận nhiều giá trị cho cùng một query key, hãy gửi nhiều giá trị thay vì ghép thành chuỗi tùy ý:

~~~java
mockMvc.perform(get("/api/orders")
        .queryParam("status", "PAID", "SHIPPED")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
~~~

Chỉ dùng dấu phẩy để phân tách nếu hợp đồng endpoint quy định rõ định dạng CSV. Việc Spring bind một danh sách từ query parameter không tự động có nghĩa mọi client phải gửi cùng một kiểu chuỗi.

## 5. Phân biệt JSON body với form parameter

JSON body và form parameter là hai cách gửi dữ liệu khác nhau.

JSON thường dùng:

~~~http
POST /api/orders
Content-Type: application/json

{"sku":"COFFEE-01","quantity":2}
~~~

Form URL encoded thường dùng:

~~~http
POST /login
Content-Type: application/x-www-form-urlencoded

username=alice&remember-me=true
~~~

Với form, dùng `param(...)` và content type phù hợp:

~~~java
mockMvc.perform(post("/login")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("username", "alice")
        .param("password", "correct-horse")
        .param("remember-me", "true"))
    .andExpect(status().is3xxRedirection());
~~~

Không dùng `param(...)` để giả lập một JSON body. Ngược lại, không gửi chuỗi JSON trong `content(...)` nếu controller được thiết kế nhận form field bằng `@RequestParam` hoặc `@ModelAttribute`.

Với field lặp, có thể gửi nhiều giá trị cùng tên:

~~~java
mockMvc.perform(post("/preferences")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("categories", "books", "music", "travel"))
    .andExpect(status().isOk());
~~~

Với form có checkbox, hãy mô tả đúng cách trình duyệt gửi dữ liệu. Checkbox không được chọn thường không gửi field tương ứng; checkbox được chọn thường gửi giá trị của nó. Test cần bao phủ cả trường hợp field vắng mặt và field có mặt nếu logic server phụ thuộc điều đó.

## 6. Gửi header theo vai trò của client

Header là một phần của hợp đồng request. Những header thường gặp:

- `Accept`: loại response client muốn nhận.
- `Content-Type`: định dạng body client gửi.
- `Authorization`: thông tin xác thực theo cơ chế API.
- `If-Match` hoặc `If-None-Match`: điều kiện dựa trên entity tag.
- `If-Modified-Since`: điều kiện dựa trên thời điểm cập nhật.
- `Accept-Language`: ngôn ngữ client mong muốn.
- `Idempotency-Key`: khóa chống xử lý lặp nếu API quy định.
- `X-Correlation-ID` hoặc `traceparent`: thông tin liên kết log/tracing theo hợp đồng hệ thống.

Ví dụ:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .header("Idempotency-Key", "order-request-2026-0001")
        .header("Accept-Language", "vi-VN")
        .header("X-Correlation-ID", "test-correlation-001")
        .content("""
                {
                  "sku": "COFFEE-01",
                  "quantity": 2,
                  "deliveryDate": "2026-11-20"
                }
                """))
    .andExpect(status().isCreated());
~~~

Header có ý nghĩa giao thức nên được kiểm tra qua đúng header. Đừng đưa token vào JSON body nếu API yêu cầu `Authorization`. Đừng dùng query parameter thay cho header chỉ để làm test ngắn hơn.

Nếu endpoint yêu cầu bearer token và mục tiêu là kiểm tra filter chain hoặc bộ lọc xác thực, hãy gửi header Authorization đúng định dạng:

~~~java
mockMvc.perform(get("/api/me")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
~~~

Nếu dùng Spring Security test support như `with(user("alice"))`, test đang thiết lập principal trong SecurityContext của test request. Cách này hữu ích để kiểm tra phân quyền ở tầng MVC, nhưng không kiểm tra quá trình đọc và xác minh bearer token từ HTTP header. Hãy chọn cách thiết lập theo đúng tầng cần kiểm thử.

Với ứng dụng bật CSRF protection, request thay đổi trạng thái có thể cần CSRF token:

~~~java
mockMvc.perform(post("/web/orders")
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {"sku":"COFFEE-01","quantity":2}
                """))
    .andExpect(status().isCreated());
~~~

Chỉ thêm CSRF token khi request thuộc cơ chế bảo vệ CSRF của ứng dụng. Nếu test cần chứng minh request thiếu token bị từ chối, hãy viết riêng trường hợp không dùng `csrf()` và kiểm tra status phù hợp.

## 7. Cookie và session

Cookie được client gửi trong request header Cookie. Với MockMvc, dùng `cookie(...)`:

~~~java
mockMvc.perform(get("/web/cart")
        .cookie(new Cookie("cart-id", "cart-001"))
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
~~~

Session là trạng thái server gắn với session identifier. Có thể thiết lập session attribute để kiểm thử controller phụ thuộc session:

~~~java
MockHttpSession session = new MockHttpSession();
session.setAttribute("selectedStore", "store-hcm-01");

mockMvc.perform(get("/web/checkout")
        .session(session))
    .andExpect(status().isOk());
~~~

Cookie và session có liên quan nhưng không giống nhau. Khi kiểm thử cơ chế tạo session hoặc ghi cookie vào response, hãy thực hiện request đầu tiên, lấy cookie/session từ kết quả, rồi dùng chúng cho request tiếp theo. Không chỉ đặt sẵn session attribute nếu mục tiêu là xác nhận ứng dụng thực sự tạo session và phát cookie đúng cách.

## 8. Upload file bằng multipart

Một request upload thường có content type `multipart/form-data` với boundary do client tạo. Dùng `multipart(...)` và `MockMultipartFile`:

~~~java
MockMultipartFile file = new MockMultipartFile(
        "file",
        "invoice.pdf",
        MediaType.APPLICATION_PDF_VALUE,
        "%PDF-1.7 test content".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/documents")
        .file(file)
        .param("documentType", "INVOICE")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isCreated());
~~~

Tên part `"file"` phải khớp với tên tham số mà controller nhận, ví dụ `@RequestPart("file")` hoặc `@RequestParam("file")`. Tên file, content type và bytes đều có thể ảnh hưởng tới validation hoặc xử lý phía server.

Không tự đặt header `Content-Type: multipart/form-data` thiếu boundary. Request builder multipart của MockMvc tạo request multipart phù hợp cho môi trường mock. Nếu endpoint nhận thêm một part JSON, hãy tạo part riêng với content type JSON:

~~~java
MockMultipartFile metadata = new MockMultipartFile(
        "metadata",
        "",
        MediaType.APPLICATION_JSON_VALUE,
        """
        {"documentType":"INVOICE","reference":"INV-2026-001"}
        """.getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/documents")
        .file(file)
        .file(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isCreated());
~~~

Với upload, nên có các trường hợp file rỗng, sai content type, tên part không đúng, vượt giới hạn dung lượng, thiếu metadata và file hợp lệ. Những giới hạn ở reverse proxy hoặc Servlet container thật có thể cần kiểm thử tích hợp riêng.

## 9. Tổ chức JSON fixture và dữ liệu dùng chung

JSON fixture hữu ích khi request có nhiều field hoặc cần giữ một hợp đồng ổn định qua nhiều lần thay đổi code. Có thể lưu theo cấu trúc:

~~~text
src/test/resources/
└── http/
    └── requests/
        ├── create-order-valid.json
        ├── create-order-missing-sku.json
        └── create-order-invalid-date.json
~~~

Đọc fixture bằng classpath resource:

~~~java
private String readRequestFixture(String name) throws IOException {
    ClassPathResource resource =
            new ClassPathResource("http/requests/" + name);
    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Sử dụng fixture trong test:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content(readRequestFixture("create-order-valid.json")))
    .andExpect(status().isCreated());
~~~

Fixture nên có tên thể hiện mục đích, chẳng hạn `valid`, `missing-sku` hoặc `invalid-date`. Tránh tạo một file JSON khổng lồ dùng cho mọi test rồi sửa chuỗi bằng nhiều thao tác replace; cách đó làm test khó hiểu và có thể vô tình thay đổi field không liên quan.

Với các field thay đổi theo test như timestamp, UUID hoặc số lượng, có thể dùng ObjectMapper để serialize một phần dữ liệu động hoặc xây dựng JSON bằng `ObjectNode`. Nhưng hãy giữ rõ các field quan trọng đối với hợp đồng. Ví dụ, nếu tên property `deliveryDate` là một phần cần xác nhận, fixture nên ghi chính tên đó thay vì để DTO tự sinh ra.

Các helper như `performJsonPost(...)` có thể giảm lặp:

~~~java
private ResultActions performJsonPost(String path, String body)
        throws Exception {
    return mockMvc.perform(post(path)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content(body));
}
~~~

Helper chỉ nên gom những chi tiết thực sự dùng chung. Nếu helper tự thêm header, token, query parameter hoặc body mặc định mà test không thể hiện, người đọc sẽ khó biết request thật sự đã gửi những gì. Hãy để các thành phần quan trọng của hợp đồng xuất hiện ngay trong test hoặc truyền vào helper một cách tường minh.

## 10. Kiểm thử dữ liệu hợp lệ và không hợp lệ

Một hợp đồng request bao gồm cả dữ liệu được chấp nhận và dữ liệu bị từ chối. Với body JSON, nên kiểm tra các trường hợp như:

- Body hợp lệ với đầy đủ field bắt buộc.
- Thiếu field bắt buộc.
- Field có giá trị `null`.
- Chuỗi rỗng hoặc chỉ chứa khoảng trắng.
- Number âm, bằng 0 hoặc vượt giới hạn.
- Sai kiểu dữ liệu, ví dụ gửi `"quantity": "two"`.
- Ngày sai định dạng hoặc ngày không hợp lệ.
- Enum không được hỗ trợ.
- Field lạ khi chính sách API yêu cầu từ chối field không xác định.
- Body rỗng, JSON bị lỗi cú pháp hoặc content type không được hỗ trợ.

Ví dụ kiểm tra lỗi validation:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "sku": "",
                  "quantity": 0,
                  "deliveryDate": "2026-11-20"
                }
                """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.errors").isArray());
~~~

Status và cấu trúc lỗi phải theo hợp đồng thực tế của ứng dụng. Không nên mặc định mọi lỗi binding đều trả về 400 nếu ứng dụng có exception handler tùy chỉnh. Hãy xác nhận response status, content type, error code và field path mà client dùng để hiển thị lỗi.

Đối với query parameter, kiểm tra giá trị vắng mặt, giá trị sai kiểu, giới hạn phân trang, nhiều giá trị trùng key và ký tự cần encode. Với header, kiểm tra header bắt buộc bị thiếu, giá trị không hợp lệ và cách xử lý khi header lặp nếu endpoint có quy định.

## 11. Một bài test hoàn chỉnh theo góc nhìn HTTP client

Ví dụ dưới đây thể hiện một request có method, path, query parameter, header, JSON body và response assertion:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void createsOrderFromHttpRequest() throws Exception {
        UUID orderId = UUID.fromString(
                "4c6d8e10-1234-4567-8901-123456789abc");

        given(orderService.create(any(CreateOrderRequest.class)))
                .willReturn(new OrderResponse(
                        orderId, "COFFEE-01", "CREATED"));

        mockMvc.perform(post("/api/orders")
                        .queryParam("source", "mobile")
                        .header("Idempotency-Key", "mobile-order-001")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sku": "COFFEE-01",
                                  "quantity": 2,
                                  "deliveryDate": "2026-11-20",
                                  "note": null
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION,
                        "/api/orders/" + orderId))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(orderId.toString()))
                .andExpect(jsonPath("$.sku").value("COFFEE-01"))
                .andExpect(jsonPath("$.status").value("CREATED"));

        then(orderService).should().create(argThat(request ->
                request.sku().equals("COFFEE-01")
                        && request.quantity() == 2
                        && request.deliveryDate().equals(
                                LocalDate.of(2026, 11, 20))));
    }
}
~~~

Đây là ví dụ minh họa; tên DTO, response, service và cấu trúc lỗi cần khớp với ứng dụng cụ thể. Điểm quan trọng là test gửi request theo dạng client sử dụng và xác nhận cả response HTTP lẫn dữ liệu đã được bind vào tầng nghiệp vụ.

Không nên chỉ xác minh mock service được gọi với một object bất kỳ. Nếu test dùng `any()` cho toàn bộ request mà không xác nhận field, lỗi binding như sai tên JSON property hoặc parse sai ngày có thể không được phát hiện.

## 12. Giới hạn của MockMvc và khi nào cần test HTTP thật

MockMvc gọi Spring MVC thông qua môi trường Servlet mock. Nó kiểm tra được nhiều hành vi quan trọng như mapping, argument resolver, message converter, validation, controller advice và filter được tích hợp vào test context. Nhưng MockMvc không mở socket và không gửi byte qua network stack như một HTTP client thật.

Vì vậy, MockMvc phù hợp để xác nhận hợp đồng ở ranh giới Spring MVC, nhưng không thay thế mọi kiểm thử tích hợp HTTP. Cân nhắc chạy ứng dụng trên cổng ngẫu nhiên và dùng `TestRestTemplate`, `WebTestClient` hoặc HTTP client phù hợp khi cần kiểm tra:

- Tương tác thực tế với Servlet container hoặc embedded server.
- Cấu hình connector, giới hạn header/body và cách container parse request.
- Hành vi qua reverse proxy, TLS hoặc network.
- Cấu hình CORS, compression hoặc đặc tính phụ thuộc server.
- Multipart upload ở tầng container và giới hạn dung lượng thực tế.
- Client/server interoperability với một HTTP client cụ thể.

Không cần chuyển mọi test controller sang HTTP thật. Hãy dùng MockMvc cho phần lớn kiểm thử MVC nhanh và tập trung; thêm một số test tích hợp có mục tiêu rõ ràng cho các khác biệt chỉ xuất hiện khi chạy server.

## 13. Những lỗi thường gặp khi tạo request MockMvc

| Cách viết dễ gây sai lệch | Vấn đề | Cách thể hiện phù hợp |
|---|---|---|
| Gửi DTO trực tiếp vào `content(...)` | `content` cần body dạng chuỗi hoặc byte | Serialize thành JSON hoặc dùng fixture |
| Gửi JSON nhưng thiếu `Content-Type` | Message converter có thể không chọn đúng định dạng | Đặt `contentType(APPLICATION_JSON)` |
| Dùng `Accept` thay cho `Content-Type` | Nhầm định dạng response với định dạng request body | Khai báo riêng cả hai khi cần |
| Dùng `param` để giả lập JSON | Test đi qua cơ chế request parameter thay vì JSON converter | Dùng `content` với JSON body |
| Đưa path variable vào query string | Request khác endpoint contract | Đặt giá trị trong URI path |
| Nối query string bằng phép cộng chuỗi | Có thể làm hỏng ký tự đặc biệt hoặc encode sai | Dùng `queryParam` hoặc URI builder |
| Gửi số định danh có số 0 đầu dưới dạng number | Mất định dạng định danh | Gửi JSON string |
| Dùng ngày phụ thuộc locale | Kết quả có thể khác giữa môi trường | Gửi định dạng ISO đã công bố |
| Tự đặt multipart content type không có boundary | Request multipart thiếu thông tin phân tách part | Dùng `multipart` và `MockMultipartFile` |
| Dùng principal giả để kết luận token hoạt động | Không kiểm tra việc đọc và xác minh Authorization header | Gửi token qua header trong test filter/authentication |
| Chỉ kiểm tra service mock được gọi | Không phát hiện lỗi binding hoặc dữ liệu sai | Kiểm tra các field đã bind và response HTTP |

## 14. Nguyên tắc thiết kế test request bền vững

Khi thêm một test MockMvc, hãy xác định request mà client sẽ gửi trước khi viết Java test. Sau đó thể hiện từng phần của request đúng vị trí:

1. Dùng đúng HTTP method và path.
2. Đặt định danh tài nguyên trong path nếu hợp đồng quy định path variable.
3. Đặt bộ lọc, phân trang và tùy chọn trong query parameter.
4. Khai báo `Accept`, `Content-Type` và các header nghiệp vụ cần thiết.
5. Gửi body theo đúng định dạng: JSON, form hoặc multipart.
6. Chọn dữ liệu đại diện cho kiểu wire thực tế, gồm cả ngày giờ, enum, null và định danh.
7. Kiểm tra response status, header, content type và body.
8. Kiểm tra dữ liệu đã bind vào controller/service khi điều đó giúp phát hiện sai lệch hợp đồng.

Một test tốt giúp người đọc hình dung được client đang gửi request nào và server cam kết trả về điều gì. Khi hợp đồng HTTP được thể hiện rõ trong test, thay đổi DTO, Jackson configuration, validation hoặc controller mapping sẽ có bằng chứng cụ thể để phát hiện tác động tới client.

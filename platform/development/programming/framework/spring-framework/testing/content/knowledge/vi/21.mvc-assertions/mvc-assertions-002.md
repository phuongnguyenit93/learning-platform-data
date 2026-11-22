# Content type, charset và dữ liệu body

## 1. Ba phần cần kiểm tra trong một HTTP message

Khi kiểm thử Spring MVC, một request hoặc response có thể được nhìn qua ba khía cạnh liên quan nhưng khác nhau:

- **Content type** cho biết body đang mang định dạng gì, ví dụ `application/json`, `text/plain` hoặc `application/xml`.
- **Charset** cho biết cách chuyển đổi giữa ký tự và byte đối với nội dung văn bản, ví dụ `UTF-8`.
- **Body** là dữ liệu thực tế được gửi hoặc trả về: chuỗi văn bản, JSON, XML, ảnh, tệp hoặc một dãy byte khác.

Một response có thể trả đúng JSON nhưng khai báo sai `Content-Type`. Một response có thể khai báo `text/plain;charset=UTF-8` nhưng body lại được tạo từ byte theo charset khác. Một test chỉ kiểm tra status code sẽ không phát hiện được các lỗi này.

Trong Spring MVC, `MockMvc` cho phép kiểm tra cả ba phần thông qua các matcher của `MockMvcResultMatchers.content()` và các matcher header.

## 2. Phân biệt Content-Type và Accept

Hai header thường xuất hiện cùng nhau nhưng mô tả hai hướng khác nhau:

| Header | Hướng | Ý nghĩa |
|---|---|---|
| `Content-Type` | Request hoặc response | Body hiện tại được biểu diễn theo định dạng nào |
| `Accept` | Request | Client muốn server trả về định dạng nào |

Ví dụ client gửi JSON và yêu cầu server trả JSON:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"productCode":"BOOK-01","quantity":2}
```

`Content-Type: application/json` mô tả body request để Spring chọn cách đọc dữ liệu, thường thông qua một `HttpMessageConverter`. `Accept: application/json` thể hiện định dạng response mà client chấp nhận.

Ở chiều response, server có thể trả:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":"...","status":"CREATED"}
```

`Content-Type` trong response mô tả body mà server thực sự gửi. Nó không phải bản sao máy móc của `Accept`; server chọn representation dựa trên mapping, các converter khả dụng và content negotiation.

Trong Spring MVC, hai thuộc tính của mapping giúp giới hạn hợp đồng này:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderResponse> create(
            @RequestBody CreateOrderRequest request) {
        OrderResponse response = new OrderResponse(
                UUID.randomUUID(), request.productCode(), "CREATED");
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

`consumes` giới hạn media type mà endpoint chấp nhận cho request body. `produces` giới hạn media type mà endpoint có thể tạo cho response. Khi request không đáp ứng điều kiện `consumes`, Spring thường trả `415 Unsupported Media Type`. Khi client yêu cầu một kiểu response không tương thích với `produces`, Spring thường trả `406 Not Acceptable`.

## 3. Kiểm tra Content-Type của response bằng MockMvc

Matcher `content().contentType(...)` kiểm tra media type của response theo giá trị mong đợi, bao gồm cả các parameter. Matcher `content().contentTypeCompatibleWith(...)` kiểm tra khả năng tương thích của media type, phù hợp khi parameter như `charset` có thể khác nhau.

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsJsonForCreateOrder() throws Exception {
        String requestBody = """
                {
                  "productCode": "BOOK-01",
                  "quantity": 2
                }
                """;

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(requestBody))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON));
    }
}
```

Ví dụ trên xác nhận response thuộc nhóm JSON mà không buộc test phải phụ thuộc vào việc server có thêm parameter hay không. Nếu hợp đồng API yêu cầu một media type cùng parameter cụ thể, có thể kiểm tra chính xác:

```java
.andExpect(content().contentType(
        MediaType.parseMediaType("text/plain;charset=UTF-8")))
```

Không nên dùng matcher chính xác nếu parameter không phải một phần của hợp đồng. Ví dụ, một test chỉ cần bảo đảm response là JSON thường nên dùng `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)`.

Có thể kiểm tra header trực tiếp bằng `header()`:

```java
.andExpect(header().string(
        HttpHeaders.CONTENT_TYPE,
        startsWith(MediaType.APPLICATION_JSON_VALUE)))
```

Tuy nhiên, khi mục tiêu là kiểm tra media type, matcher `contentType` thể hiện ý định rõ hơn việc so sánh chuỗi header thủ công.

## 4. Kiểm tra charset của nội dung văn bản

Charset có ý nghĩa khi body chứa văn bản. Cùng một ký tự có thể được mã hóa thành các dãy byte khác nhau tùy charset. Nếu phía gửi và phía nhận dùng cách mã hóa khác nhau, nội dung có thể bị lỗi dấu hoặc biến thành ký tự không mong muốn.

Một response văn bản có thể khai báo charset trực tiếp trong `Content-Type`:

```http
Content-Type: text/plain;charset=UTF-8
```

Trong controller, có thể tạo response với media type chỉ rõ UTF-8:

```java
@GetMapping(value = "/greeting", produces = "text/plain;charset=UTF-8")
public ResponseEntity<String> greeting() {
    return ResponseEntity.ok()
            .contentType(new MediaType(
                    "text", "plain", StandardCharsets.UTF_8))
            .body("Xin chào Spring MVC");
}
```

Test có thể kiểm tra cả media type lẫn charset:

```java
@Test
void returnsUtf8Text() throws Exception {
    mockMvc.perform(get("/greeting"))
            .andExpect(status().isOk())
            .andExpect(content().contentType(
                    new MediaType("text", "plain", StandardCharsets.UTF_8)))
            .andExpect(content().encoding(StandardCharsets.UTF_8))
            .andExpect(content().string("Xin chào Spring MVC"));
}
```

`content().encoding(...)` kiểm tra encoding mà response khai báo cho nội dung. `content().string(...)` kiểm tra body sau khi được đọc thành chuỗi. Khi hợp đồng endpoint yêu cầu UTF-8, kiểm tra cả hai giúp phát hiện trường hợp header và nội dung không khớp với mong đợi.

Không nên mặc định rằng mọi response JSON đều phải có parameter `charset=UTF-8` trong header. JSON được trao đổi giữa các hệ thống theo UTF-8; các converter JSON của Spring thường ghi JSON bằng UTF-8 và có thể trả `Content-Type: application/json` mà không thêm parameter charset. Vì vậy, hãy kiểm tra media type JSON theo tính tương thích và kiểm tra nội dung theo cấu trúc JSON. Chỉ kiểm tra `content().encoding(...)` khi charset được endpoint công bố rõ ràng hoặc là một phần của hợp đồng cần bảo vệ.

## 5. Gửi request body có charset xác định

Với request văn bản, client cần mã hóa body thành byte theo charset mà server hiểu. Có thể truyền `Content-Type` kèm charset và thiết lập encoding của request trong MockMvc:

```java
@Test
void acceptsUtf8PlainText() throws Exception {
    byte[] body = "Xin chào Nguyễn An".getBytes(StandardCharsets.UTF_8);

    mockMvc.perform(post("/api/messages")
                    .contentType(new MediaType(
                            "text", "plain", StandardCharsets.UTF_8))
                    .characterEncoding(StandardCharsets.UTF_8.name())
                    .content(body))
            .andExpect(status().isCreated());
}
```

`content(byte[])` gửi đúng dãy byte đã tạo. Đây là cách rõ ràng khi test cần kiểm soát chính xác encoding của request. `characterEncoding(...)` đặt encoding trên mock request; charset trong media type cũng mô tả encoding của body văn bản. Hai giá trị cần thống nhất.

Với JSON, nên tạo byte theo UTF-8 và khai báo `application/json`:

```java
String json = """
        {"name":"Nguyễn An","city":"Hồ Chí Minh"}
        """;

mockMvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json.getBytes(StandardCharsets.UTF_8)))
        .andExpect(status().isCreated());
```

Không cần thêm `charset=UTF-8` vào `application/json` chỉ để chứng minh request dùng UTF-8. Hãy bảo đảm byte được tạo theo UTF-8 và để converter JSON xử lý JSON theo quy tắc của định dạng.

Nếu dùng `.content(String)`, việc chuyển chuỗi thành byte phụ thuộc encoding của mock request và charset được cấu hình. Khi test tập trung vào chính xác byte hoặc ký tự ngoài ASCII, `.content(byte[])` giúp loại bỏ sự mơ hồ về bước mã hóa ở phía test.

## 6. Chọn matcher phù hợp với kiểu body

`MockMvcResultMatchers.content()` cung cấp nhiều cách kiểm tra body. Chọn matcher dựa trên cấu trúc dữ liệu mà endpoint cam kết.

| Matcher | Mục tiêu | Khi nên dùng |
|---|---|---|
| `content().string(...)` | So sánh body dưới dạng chuỗi | Văn bản thuần, nội dung HTML hoặc nội dung cần so sánh nguyên văn |
| `content().bytes(...)` | So sánh dãy byte | Ảnh, PDF, tệp tải xuống hoặc nội dung nhị phân |
| `content().json(...)` | So sánh nội dung JSON | Kiểm tra JSON mà không phụ thuộc khoảng trắng và cách trình bày |
| `content().xml(...)` | So sánh nội dung XML | Kiểm tra response XML |
| `jsonPath(...)` | Kiểm tra một phần dữ liệu JSON | Xác nhận field, giá trị, kiểu dữ liệu hoặc cấu trúc cần thiết |

### 6.1. So sánh văn bản bằng `string()`

```java
mockMvc.perform(get("/greeting"))
        .andExpect(status().isOk())
        .andExpect(content().string("Xin chào Spring MVC"));
```

Matcher này so sánh nội dung chuỗi, vì vậy dấu cách, xuống dòng và ký tự đều có thể ảnh hưởng đến kết quả. Dùng nó khi nội dung văn bản chính xác là một phần của hợp đồng.

### 6.2. So sánh byte bằng `bytes()`

```java
byte[] expected = Files.readAllBytes(
        Path.of("src/test/resources/sample-image.png"));

mockMvc.perform(get("/files/sample-image"))
        .andExpect(status().isOk())
        .andExpect(content().contentType(MediaType.IMAGE_PNG))
        .andExpect(content().bytes(expected));
```

Với dữ liệu nhị phân, không nên chuyển byte thành `String` để so sánh. Việc giải mã byte tùy tiện có thể làm thay đổi hoặc làm mất dữ liệu. Kiểm tra byte trực tiếp giữ nguyên nội dung cần xác nhận.

### 6.3. So sánh JSON bằng `json()`

```java
String expectedJson = """
        {
          "productCode": "BOOK-01",
          "quantity": 2,
          "status": "CREATED"
        }
        """;

mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(requestBody))
        .andExpect(status().isCreated())
        .andExpect(content().json(expectedJson));
```

So sánh JSON theo cấu trúc tránh phụ thuộc vào thứ tự khoảng trắng, thụt dòng hoặc cách format. Các overload của matcher cho phép lựa chọn chế độ so sánh; nếu thứ tự phần tử mảng hoặc tập field chính xác là yêu cầu, hãy chọn chế độ phù hợp và viết test thể hiện yêu cầu đó.

### 6.4. Kiểm tra field bằng `jsonPath()`

```java
mockMvc.perform(get("/api/orders/42")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("CONFIRMED"))
        .andExpect(jsonPath("$.items").isArray())
        .andExpect(jsonPath("$.items.length()").value(2));
```

`jsonPath()` phù hợp khi chỉ một phần response là quan trọng đối với test. Nó giúp test tập trung vào hợp đồng cần bảo vệ thay vì phải sao chép toàn bộ response mẫu. Nếu cần xác nhận mọi field hoặc cấu trúc JSON tổng thể, kết hợp với `content().json(...)`.

## 7. Kiểm tra content negotiation và lỗi media type

Content negotiation là quá trình Spring chọn representation phù hợp với request, đặc biệt là header `Accept` và các khai báo `produces`.

Ví dụ endpoint chỉ trả JSON:

```java
@GetMapping(value = "/api/orders/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
public OrderResponse find(@PathVariable UUID id) {
    return orderService.find(id);
}
```

Test trường hợp client chấp nhận JSON:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON));
```

Test trường hợp client yêu cầu định dạng không được endpoint cung cấp:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaType.TEXT_PLAIN))
        .andExpect(status().isNotAcceptable());
```

Đây là lỗi `406 Not Acceptable`: server không tìm được representation phù hợp với những định dạng client chấp nhận.

Với request body, endpoint có thể chỉ chấp nhận JSON:

```java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<Void> create(@RequestBody CreateOrderRequest request) {
    orderService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

Test gửi một media type không phù hợp:

```java
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.TEXT_PLAIN)
                .content("productCode=BOOK-01"))
        .andExpect(status().isUnsupportedMediaType());
```

Đây là lỗi `415 Unsupported Media Type`: endpoint không chấp nhận định dạng body request được gửi lên. Cần phân biệt `406` với `415`: `406` liên quan định dạng response client chấp nhận; `415` liên quan định dạng request body server chấp nhận.

## 8. Kiểm tra response rỗng và response không có body

Không phải endpoint nào cũng trả body. Ví dụ thao tác xóa có thể trả `204 No Content`:

```java
@DeleteMapping("/api/orders/{id}")
public ResponseEntity<Void> delete(@PathVariable UUID id) {
    orderService.delete(id);
    return ResponseEntity.noContent().build();
}
```

Test nên kiểm tra status và body rỗng:

```java
mockMvc.perform(delete("/api/orders/{id}", orderId))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

Với response không có representation, không nên ép test phải có `Content-Type` nếu hợp đồng endpoint không yêu cầu. `Content-Type` mô tả representation của body; response không có body có thể không cần khai báo kiểu nội dung.

## 9. Một ví dụ kiểm thử đầy đủ cho request và response JSON

Ví dụ sau kết hợp status, request media type, response media type và nội dung body:

```java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void createsCustomerAndReturnsJson() throws Exception {
        String requestJson = """
                {
                  "name": "Nguyễn An",
                  "email": "an@example.com"
                }
                """;

        mockMvc.perform(post("/api/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(requestJson.getBytes(StandardCharsets.UTF_8)))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.name").value("Nguyễn An"))
                .andExpect(jsonPath("$.email").value("an@example.com"))
                .andExpect(jsonPath("$.id").isNotEmpty());
    }
}
```

Test này kiểm tra dữ liệu tiếng Việt đi qua request dưới dạng byte UTF-8, đồng thời xác nhận response là JSON và các field chính có giá trị đúng. Nó không ràng buộc response JSON phải có parameter `charset`, vì parameter đó không cần thiết để xác định cách mã hóa JSON theo UTF-8.

## 10. Các lỗi thường gặp khi kiểm tra content type, charset và body

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test JSON thất bại vì `Content-Type` khác chuỗi mong đợi | Response có parameter hoặc media type tương thích nhưng không bằng tuyệt đối | Dùng `contentTypeCompatibleWith()` nếu parameter không thuộc hợp đồng |
| Request trả `415` | `Content-Type` không khớp `consumes`, hoặc không có converter đọc body đó | Kiểm tra media type, converter và `consumes` của mapping |
| Request trả `406` | `Accept` không tương thích với `produces` hoặc representation khả dụng | Gửi `Accept` phù hợp hoặc điều chỉnh representation endpoint hỗ trợ |
| Tiếng Việt bị lỗi dấu | Byte được mã hóa và giải mã bằng charset khác nhau | Kiểm tra charset của request/response và tạo byte bằng cùng charset |
| JSON matcher thất bại dù dữ liệu nhìn có vẻ đúng | Field, kiểu dữ liệu hoặc cấu trúc JSON khác mong đợi | Dùng `jsonPath()` để xác định field sai hoặc so sánh JSON với expected body rõ ràng |
| So sánh chuỗi thất bại vì xuống dòng hoặc khoảng trắng | `content().string()` so sánh nội dung chuỗi | Dùng JSON/XML matcher cho dữ liệu có cấu trúc; chỉ so sánh nguyên văn khi cần |
| Body nhị phân bị sai khi chuyển sang String | Dữ liệu không phải văn bản hoặc bị giải mã theo charset tùy ý | Dùng `content().bytes(...)` |
| Test không thấy body dù status đúng | Endpoint chủ ý trả `204`, redirect hoặc response không có representation | Xác nhận hợp đồng endpoint và kiểm tra status/header phù hợp |

Khi chẩn đoán lỗi, nên kiểm tra lần lượt: request có gửi đúng `Content-Type` không, `Accept` có phù hợp không, controller mapping có `consumes`/`produces` gì, converter nào xử lý body, và matcher đang kiểm tra representation hay dữ liệu đã giải mã.

## 11. Chọn cách kiểm tra theo hợp đồng API

- Với JSON: kiểm tra `contentTypeCompatibleWith(APPLICATION_JSON)` và dùng `json()` hoặc `jsonPath()` để xác nhận body.
- Với văn bản có charset quy định rõ: kiểm tra media type, `encoding()` và nội dung bằng `string()`.
- Với dữ liệu nhị phân: kiểm tra media type và so sánh byte bằng `bytes()`.
- Với request body: thiết lập `contentType(...)`; thiết lập `accept(...)` khi muốn kiểm tra content negotiation.
- Với endpoint có `consumes` hoặc `produces`: kiểm tra cả trường hợp hợp lệ và lỗi `415`/`406` khi đó là hành vi thuộc hợp đồng.
- Với response không có body: tập trung vào status và các header có ý nghĩa; không thêm assertion content type nếu response không có representation.

Kiểm tra content type, charset và body giúp test MVC xác nhận response đúng định dạng mà client có thể xử lý, đồng thời bảo đảm dữ liệu văn bản và dữ liệu nhị phân được truyền đúng cách. Khi matcher phản ánh đúng hợp đồng endpoint, test sẽ phát hiện được lỗi ở cả bước chọn representation, mã hóa ký tự và chuyển đổi dữ liệu.

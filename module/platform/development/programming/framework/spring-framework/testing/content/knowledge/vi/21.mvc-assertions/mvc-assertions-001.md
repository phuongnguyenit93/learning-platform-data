# Status code, header và cookie phản hồi

Trong kiểm thử Spring MVC, xác nhận response body là chưa đủ. Một endpoint còn phải trả đúng HTTP status code, header và cookie để client hiểu kết quả xử lý, điều hướng request tiếp theo, lưu trạng thái hoặc áp dụng chính sách bảo mật. `MockMvc` cung cấp các result matcher để kiểm tra những thành phần này trực tiếp trên response do `DispatcherServlet` tạo ra.

Ví dụ, hai endpoint đều có thể trả JSON chứa thông tin đơn hàng nhưng mang ý nghĩa HTTP khác nhau: tạo đơn hàng mới nên trả `201 Created` và header `Location`; truy vấn đơn hàng thành công thường trả `200 OK`; xóa thành công không cần nội dung có thể trả `204 No Content`. Nếu chỉ kiểm tra JSON, bài test có thể bỏ sót một hợp đồng HTTP sai.

## 1. Cấu trúc response HTTP

Một response HTTP gồm ba phần chính:

```text
HTTP/1.1 201 Created
Content-Type: application/json
Location: /orders/42
X-Request-Id: req-abc123
Set-Cookie: session=...; Path=/; HttpOnly; Secure

{"id":42,"status":"CREATED"}
```

- **Status code** cho biết kết quả xử lý ở mức giao thức, ví dụ `200`, `201`, `204`, `400`, `401`, `403`, `404` hoặc `500`.
- **Header** cung cấp metadata về response, định dạng nội dung, cache, điều hướng, phiên bản, giới hạn truy cập hoặc thông tin theo dõi.
- **Cookie** được gửi qua header `Set-Cookie`, cho phép server yêu cầu client lưu một giá trị và gửi lại trong các request phù hợp.
- **Body** chứa dữ liệu trả về, chẳng hạn JSON, XML, HTML hoặc có thể rỗng.

Mỗi thành phần có ý nghĩa riêng. Status code không thay thế body; header `Location` không tự tạo tài nguyên; cookie trong response không chứng minh trình duyệt đã lưu cookie. Bài test cần xác nhận đúng hợp đồng mà ứng dụng chịu trách nhiệm tạo ra.

## 2. Kiểm tra status code

Spring MVC cho phép controller xác định status bằng `ResponseEntity`, `@ResponseStatus`, `ResponseStatusException` hoặc exception handler. `MockMvc` kiểm tra status qua `status()` matcher.

### Dùng `ResponseEntity` để biểu đạt kết quả

Ví dụ controller tạo đơn hàng:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<OrderView> create(@RequestBody CreateOrder request) {
        OrderView created = orderService.create(request);
        URI location = URI.create("/orders/" + created.id());

        return ResponseEntity.created(location)
                .body(created);
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> find(@PathVariable long id) {
        return ResponseEntity.ok(orderService.find(id));
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(@PathVariable long id) {
        orderService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

Các factory method `created`, `ok` và `noContent` làm rõ ý nghĩa của response. Bài test có thể kiểm tra từng status:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"productId": "P-100", "quantity": 2}
                        """))
        .andExpect(status().isCreated());

mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk());

mockMvc.perform(delete("/orders/42"))
        .andExpect(status().isNoContent());
```

Đoạn test minh họa ba hợp đồng status khác nhau. Trong test thực tế, hãy cấu hình dữ liệu hoặc mock service phù hợp để request đi qua nhánh nghiệp vụ mong muốn.

### Những matcher status thường dùng

| Matcher | Status | Ý nghĩa thường gặp |
|---|---:|---|
| `status().isOk()` | 200 | Request được xử lý thành công và thường có response body. |
| `status().isCreated()` | 201 | Tài nguyên mới được tạo. |
| `status().isAccepted()` | 202 | Request được chấp nhận để xử lý sau. |
| `status().isNoContent()` | 204 | Xử lý thành công, không có response body. |
| `status().isBadRequest()` | 400 | Request không hợp lệ. |
| `status().isUnauthorized()` | 401 | Thiếu hoặc không có thông tin xác thực hợp lệ. |
| `status().isForbidden()` | 403 | Đã nhận diện request nhưng không cho phép truy cập. |
| `status().isNotFound()` | 404 | Không tìm thấy tài nguyên hoặc route tương ứng. |
| `status().isConflict()` | 409 | Xung đột với trạng thái hiện tại của tài nguyên. |
| `status().isInternalServerError()` | 500 | Lỗi phía server chưa được xử lý theo một response cụ thể hơn. |

Với status không có matcher chuyên biệt, có thể dùng `status().is(418)` hoặc mã tương ứng. Cách này hữu ích khi ứng dụng định nghĩa status riêng hoặc muốn kiểm tra chính xác một mã HTTP.

### Kiểm tra lỗi và exception mapping

Một exception có thể được chuyển thành status bằng `@ResponseStatus`:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
class OrderNotFoundException extends RuntimeException {

    OrderNotFoundException(long id) {
        super("Order " + id + " was not found");
    }
}
```

Hoặc dùng `@RestControllerAdvice` để kiểm soát response lỗi:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(OrderNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("ORDER_NOT_FOUND", exception.getMessage()));
    }
}

record ApiError(String code, String message) {
}
```

Test nên xác nhận cả status và cấu trúc lỗi:

```java
mockMvc.perform(get("/orders/999"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
        .andExpect(jsonPath("$.message").value("Order 999 was not found"));
```

Điều này bảo đảm exception handler chuyển lỗi thành đúng hợp đồng HTTP và client nhận được mã lỗi ổn định. Tránh chỉ kiểm tra `status().is4xxClientError()` nếu API yêu cầu cụ thể `404`; matcher tổng quát có thể che giấu việc ứng dụng trả nhầm `400` hoặc `403`.

### Status 204 và response body rỗng

`204 No Content` biểu thị response không có nội dung. Nếu endpoint dùng status này, hãy kiểm tra status và body rỗng:

```java
mockMvc.perform(delete("/orders/42"))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

Không nên mong đợi JSON `{}` hoặc chuỗi thông báo trên response `204`. Nếu client cần nhận nội dung xác nhận, cân nhắc dùng `200 OK` với body phù hợp.

## 3. Kiểm tra response header

Header có thể ảnh hưởng trực tiếp đến cách client xử lý response. Spring cung cấp `header()` matcher để xác nhận header tồn tại, vắng mặt hoặc có giá trị mong đợi.

### Header `Location` khi tạo tài nguyên

Theo quy ước HTTP, response `201 Created` thường chỉ ra URI của tài nguyên vừa tạo bằng header `Location`:

```java
mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"productId": "P-100", "quantity": 2}
                        """))
        .andExpect(status().isCreated())
        .andExpect(header().exists(HttpHeaders.LOCATION))
        .andExpect(header().string(HttpHeaders.LOCATION, "/orders/42"));
```

Nếu API trả URI tuyệt đối, hãy xác nhận đúng scheme, host, port và path theo hợp đồng của ứng dụng. Test MockMvc không tự chứng minh proxy hoặc cấu hình forwarded header ở môi trường triển khai sẽ tạo ra host/scheme chính xác.

### Header định dạng và cache

Các header thường được kiểm tra gồm:

| Header | Mục đích | Điều nên xác nhận |
|---|---|---|
| `Content-Type` | Kiểu nội dung response | Media type đúng, ví dụ `application/json`. |
| `Cache-Control` | Chính sách cache | Các directive như `no-store`, `private`, `max-age`. |
| `ETag` | Validator cho representation | Giá trị tag được tạo và thay đổi theo representation. |
| `Last-Modified` | Thời điểm representation thay đổi | Giá trị ngày giờ hợp lệ khi API sử dụng validator này. |
| `Location` | URI của tài nguyên hoặc đích redirect | Đường dẫn đúng theo hợp đồng. |
| `WWW-Authenticate` | Thử thách xác thực HTTP | Scheme và thông tin challenge đúng khi trả `401`. |
| `Vary` | Header request ảnh hưởng đến response/cache key | Các giá trị cần thiết, chẳng hạn `Accept` hoặc `Origin`. |
| `X-Request-Id` | Định danh request để theo dõi | Header được tạo hoặc truyền tiếp đúng chính sách. |

Ví dụ kiểm tra content type và chính sách cache:

```java
mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(header().string(
                HttpHeaders.CACHE_CONTROL,
                containsString("no-store")));
```

`contentTypeCompatibleWith` phù hợp khi response có thể chứa tham số như `charset=UTF-8`. Nếu hợp đồng yêu cầu chính xác cả media type và tham số, dùng `content().contentType(...)` hoặc kiểm tra giá trị header theo đúng yêu cầu.

### Kiểm tra header tồn tại, vắng mặt và giá trị

Một số cách dùng phổ biến:

```java
mockMvc.perform(get("/orders/42"))
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(header().string("X-Request-Id", "req-abc123"))
        .andExpect(header().doesNotExist("X-Debug-Token"));
```

Tên header không phân biệt chữ hoa và chữ thường theo HTTP. Dùng hằng số từ `HttpHeaders` cho các header chuẩn giúp giảm lỗi gõ sai; với header riêng của ứng dụng, nên tập trung tên header thành hằng số nếu được dùng ở nhiều nơi.

Nếu header được tạo động, chẳng hạn request id hoặc ngày giờ, tránh hard-code giá trị không ổn định. Có thể kiểm tra header tồn tại, định dạng hoặc quan hệ với dữ liệu đã biết. Chỉ kiểm tra giá trị chính xác khi test kiểm soát được nguồn tạo giá trị đó.

### Redirect và header `Location`

Redirect thường trả status thuộc nhóm `3xx` cùng `Location`. Có thể kiểm tra cả hai:

```java
mockMvc.perform(post("/login"))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(HttpHeaders.LOCATION, "/dashboard"));
```

Nếu cần kiểm tra chính xác redirect URL, `redirectedUrl("/dashboard")` cũng là một matcher chuyên biệt. Hãy phân biệt redirect với response `201 Created`: cả hai có thể có `Location`, nhưng status và ý nghĩa giao thức khác nhau.

## 4. Kiểm tra cookie phản hồi

Server gửi cookie cho client bằng header `Set-Cookie`. Cookie có thể chứa session identifier, refresh token, tùy chọn giao diện hoặc dữ liệu trạng thái phù hợp. Các thuộc tính của cookie ảnh hưởng đến phạm vi gửi lại và mức bảo vệ dữ liệu.

### Cookie được thêm bằng Servlet API

Nếu controller gọi `HttpServletResponse.addCookie`, MockMvc lưu các cookie trong `MockHttpServletResponse`. Ta có thể kiểm tra bằng `cookie()` matcher:

```java
@RestController
class PreferenceController {

    @PostMapping("/preferences/theme")
    ResponseEntity<Void> saveTheme(
            @RequestParam String theme,
            HttpServletResponse response) {

        Cookie cookie = new Cookie("theme", theme);
        cookie.setPath("/");
        cookie.setMaxAge(60 * 60);
        cookie.setHttpOnly(true);
        cookie.setSecure(true);
        response.addCookie(cookie);

        return ResponseEntity.noContent().build();
    }
}
```

Bài test xác nhận giá trị và thuộc tính cookie:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;

mockMvc.perform(post("/preferences/theme")
                .param("theme", "dark"))
        .andExpect(status().isNoContent())
        .andExpect(cookie().exists("theme"))
        .andExpect(cookie().value("theme", "dark"))
        .andExpect(cookie().path("theme", "/"))
        .andExpect(cookie().maxAge("theme", 3600))
        .andExpect(cookie().httpOnly("theme", true))
        .andExpect(cookie().secure("theme", true));
```

Các matcher này kiểm tra cookie được tạo trong response mô phỏng. Chúng không chứng minh trình duyệt đã lưu cookie hay sẽ gửi cookie trong request tiếp theo.

### Cookie tạo bằng `ResponseCookie` và header `Set-Cookie`

Spring cung cấp `ResponseCookie` để tạo cookie theo phong cách immutable, thuận tiện khi cần thuộc tính `SameSite`:

```java
ResponseCookie refreshCookie = ResponseCookie.from("refresh_token", token)
        .httpOnly(true)
        .secure(true)
        .sameSite("Strict")
        .path("/auth")
        .maxAge(Duration.ofDays(7))
        .build();

return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, refreshCookie.toString())
        .body(new TokenResponse(accessToken));
```

`ResponseCookie` được chuyển thành chuỗi header `Set-Cookie`. Trong cách tạo này, hãy kiểm tra header thay vì giả định cookie sẽ xuất hiện trong danh sách Servlet cookie của response:

```java
mockMvc.perform(post("/auth/refresh"))
        .andExpect(status().isOk())
        .andExpect(header().string(
                HttpHeaders.SET_COOKIE,
                allOf(
                        containsString("refresh_token="),
                        containsString("HttpOnly"),
                        containsString("Secure"),
                        containsString("SameSite=Strict"),
                        containsString("Path=/auth"))));
```

Đoạn test trên minh họa việc kiểm tra các directive trong header. Nếu response có nhiều cookie, mỗi cookie thường được gửi bằng một header `Set-Cookie` riêng; không nên gộp chúng thành một chuỗi duy nhất bằng dấu phẩy vì thuộc tính `Expires` có thể chứa dấu phẩy. Khi cần kiểm tra nhiều cookie, hãy xác nhận từng giá trị header hoặc dùng cookie matcher cho các cookie được thêm qua Servlet API.

### Ý nghĩa các thuộc tính bảo mật

| Thuộc tính | Tác dụng | Cách kiểm chứng |
|---|---|---|
| `HttpOnly` | JavaScript phía trình duyệt không đọc cookie qua `document.cookie`. | Xác nhận directive `HttpOnly` hoặc matcher `httpOnly`. |
| `Secure` | Trình duyệt chỉ gửi cookie qua kết nối bảo mật theo quy tắc cookie. | Xác nhận directive `Secure` hoặc matcher `secure`. |
| `SameSite` | Kiểm soát gửi cookie trong ngữ cảnh cross-site. | Kiểm tra directive `SameSite=Lax`, `Strict` hoặc `None`. |
| `Path` | Giới hạn phạm vi path mà cookie được gửi. | Xác nhận giá trị `Path`. |
| `Domain` | Xác định host/domain được phép nhận cookie. | Xác nhận giá trị `Domain` nếu ứng dụng có đặt. |
| `Max-Age` / `Expires` | Xác định thời gian tồn tại của cookie. | Xác nhận tuổi thọ hoặc thời điểm hết hạn theo chính sách. |

Đối với cookie chứa session id, refresh token hoặc thông tin nhạy cảm, cần kiểm tra `HttpOnly`, `Secure`, `SameSite`, `Path` và thời hạn theo yêu cầu bảo mật của ứng dụng. Không nên chỉ kiểm tra cookie tồn tại.

`SameSite=None` yêu cầu cookie có `Secure` theo quy tắc trình duyệt hiện đại. Bài test header có thể xác nhận server phát đúng hai directive; việc trình duyệt chấp nhận cookie vẫn cần kiểm thử ở cấp browser nếu đó là yêu cầu của sản phẩm.

### Cookie đầu vào và cookie đầu ra

Hai hướng kiểm tra cần được phân biệt:

- `.cookie(new Cookie("theme", "dark"))` trên request builder gửi cookie **đến controller**.
- `cookie().value("theme", "dark")` trên result matcher kiểm tra cookie **do controller trả về**.

Ví dụ kiểm tra server đọc cookie đầu vào:

```java
mockMvc.perform(get("/preferences/theme")
                .cookie(new Cookie("theme", "dark")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.theme").value("dark"));
```

Nếu muốn mô phỏng nhiều request có trạng thái session, có thể giữ `MockHttpSession` hoặc cookie từ response rồi gắn vào request tiếp theo. Điều này kiểm tra logic ứng dụng trong môi trường mock; nó không tái tạo đầy đủ cookie jar, chính sách SameSite, domain matching hoặc hành vi bảo mật của trình duyệt thật.

## 5. Kiểm tra header và cookie trong các luồng HTTP thường gặp

### Conditional GET và ETag

ETag là validator đại diện cho một phiên bản của resource. Client có thể gửi `If-None-Match`; nếu representation chưa thay đổi, server có thể trả `304 Not Modified` để client dùng bản đã cache.

Một bài test có thể kiểm tra cả response đầu và request có điều kiện:

```java
MvcResult first = mockMvc.perform(get("/catalog/items/42"))
        .andExpect(status().isOk())
        .andExpect(header().exists(HttpHeaders.ETAG))
        .andReturn();

String etag = first.getResponse().getHeader(HttpHeaders.ETAG);

mockMvc.perform(get("/catalog/items/42")
                .header(HttpHeaders.IF_NONE_MATCH, etag))
        .andExpect(status().isNotModified());
```

Ví dụ này giả định endpoint đã triển khai conditional request và trả cùng ETag khi representation không đổi. Nếu controller hoặc service tự tính ETag, hãy bảo đảm test dùng dữ liệu ổn định để kết quả có thể lặp lại.

### Response lỗi xác thực

Khi API dùng HTTP Basic hoặc một authentication scheme khác, response `401 Unauthorized` có thể cần header `WWW-Authenticate` để client biết cách xác thực:

```java
mockMvc.perform(get("/api/private"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().exists(HttpHeaders.WWW_AUTHENTICATE));
```

Với API dùng Bearer token, có thể xác nhận scheme `Bearer` và các tham số challenge mà ứng dụng công bố. Không nên áp đặt header này cho response `403 Forbidden`; `401` và `403` biểu đạt hai tình huống khác nhau.

### CORS và header `Vary`

Nếu API hỗ trợ CORS, test có thể gửi `Origin` và xác nhận các header CORS được trả về, chẳng hạn `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` hoặc `Access-Control-Allow-Credentials` theo cấu hình.

```java
mockMvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, "https://client.example")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
        .andExpect(status().isOk())
        .andExpect(header().exists(HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS));
```

Với response thay đổi theo `Origin`, header `Vary: Origin` có thể cần thiết để cache trung gian không dùng nhầm response giữa các origin. Kiểm tra CORS qua MockMvc xác nhận filter/configuration Spring tạo header mong đợi; nó không thay thế kiểm thử trình duyệt về CORS enforcement.

## 6. Kết hợp nhiều matcher trong một bài test

Một bài test response tốt thường xác nhận status, một số header quan trọng, cookie và body cùng lúc. Ví dụ sau minh họa hợp đồng tạo đơn hàng:

```java
mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Correlation-Id", "corr-001")
                .content("""
                        {"productId": "P-100", "quantity": 2}
                        """))
        .andExpect(status().isCreated())
        .andExpect(header().string(HttpHeaders.LOCATION, "/orders/42"))
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("CREATED"));
```

Nếu endpoint còn phát cookie, có thể nối thêm cookie matcher hoặc matcher cho `Set-Cookie` tùy cách cookie được tạo. Hãy tập trung vào những thuộc tính thuộc hợp đồng API. Kiểm tra mọi header mặc định của framework có thể khiến test dễ vỡ khi nâng cấp phiên bản mà hành vi nghiệp vụ không đổi.

Có thể tách phần thực hiện request và phần assertion bằng `MvcResult` khi cần lấy một giá trị từ response rồi dùng nó trong request tiếp theo, như ví dụ ETag. Với các assertion độc lập, nối matcher trong một `andExpect` chain giúp đọc kết quả mong đợi tại cùng một nơi.

## 7. Lỗi thường gặp khi kiểm tra response

### Chỉ kiểm tra body mà bỏ qua status

Một endpoint có thể trả JSON đúng nhưng status sai, chẳng hạn tạo tài nguyên mà trả `200` thay vì `201`, hoặc xóa thành công nhưng trả body không phù hợp với `204`. Hãy kiểm tra status theo ý nghĩa của thao tác.

### Dùng matcher quá tổng quát

`is2xxSuccessful()` chỉ chứng minh status thuộc nhóm 2xx. Nếu API yêu cầu `201 Created`, matcher này vẫn chấp nhận `200 OK` hoặc `204 No Content`. Hãy dùng matcher cụ thể khi hợp đồng xác định một mã.

### Kiểm tra `Location` mà không kiểm tra status

Header `Location` có thể xuất hiện trong response redirect hoặc các tình huống khác. Khi kiểm tra tạo resource, xác nhận cả `201 Created` và URI tài nguyên. Khi kiểm tra redirect, xác nhận status `3xx` và đích điều hướng.

### Giả định cookie matcher kiểm tra mọi header `Set-Cookie`

Cookie được thêm qua `HttpServletResponse.addCookie` được lưu trong danh sách cookie của response mock và phù hợp với `cookie()` matcher. Cookie được tự tạo thành chuỗi `ResponseCookie` rồi đặt vào header cần được kiểm tra qua `header().string(...)` hoặc cách kiểm tra header tương ứng. Hai cách ghi response này không nên bị đánh đồng.

### So sánh toàn bộ header động

Header như `Date`, `Expires`, request id hoặc token có thể thay đổi theo thời gian và từng lần chạy. Kiểm tra sự tồn tại, định dạng hoặc thuộc tính ổn định thay vì so sánh nguyên văn một giá trị không được kiểm soát.

### Nghĩ rằng MockMvc đã kiểm tra trình duyệt lưu cookie

MockMvc chỉ cho biết response mô phỏng có chứa cookie/header mong đợi. Nó không chạy browser cookie jar, không áp dụng chính sách SameSite và không chứng minh cookie được gửi lại qua một kết nối HTTPS thật. Khi cần kiểm tra hành vi trình duyệt, hãy bổ sung browser hoặc HTTP integration test phù hợp.

### Quên header do filter hoặc security tạo ra

Một số header được tạo bởi filter, Spring Security, CORS configuration hoặc reverse proxy. Nếu bài test MockMvc không đưa filter vào chuỗi, assertion có thể thất bại hoặc bỏ qua hành vi cần xác nhận. Hãy kiểm tra cấu hình test có thực sự đăng ký các filter liên quan hay không.

## 8. Gợi ý tổ chức test theo hợp đồng API

Với mỗi endpoint, có thể xác định response contract theo một bảng ngắn trước khi viết assertion:

| Trường hợp | Status | Header/cookie cần kiểm tra | Body |
|---|---:|---|---|
| Tạo tài nguyên thành công | 201 | `Location`, `Content-Type`, request id nếu có | Representation của tài nguyên mới. |
| Đọc tài nguyên thành công | 200 | `Content-Type`, cache/ETag nếu có | Representation hiện tại. |
| Xóa thành công | 204 | Header chỉ khi hợp đồng yêu cầu | Rỗng. |
| Dữ liệu không hợp lệ | 400 hoặc status đã quy định | `Content-Type` | Mã lỗi và chi tiết validation. |
| Chưa xác thực | 401 | `WWW-Authenticate` nếu scheme yêu cầu | Thông tin lỗi theo hợp đồng. |
| Không có quyền | 403 | Header theo chính sách bảo mật nếu có | Thông tin lỗi phù hợp. |
| Không tìm thấy | 404 | `Content-Type` | Mã lỗi ổn định. |

Không phải endpoint nào cũng cần mọi header hoặc cookie. Chỉ đưa vào bảng những thuộc tính thực sự có ý nghĩa với client. Sau đó dùng `MockMvc` để xác nhận các nhánh thành công và lỗi, đặc biệt là các trường hợp biên như tài nguyên vừa tạo, response rỗng, cookie hết hạn hoặc request có validator.

## 9. Checklist khi viết assertion

- [ ] Status code cụ thể khớp với ý nghĩa của thao tác.
- [ ] Response `201 Created` có `Location` khi hợp đồng yêu cầu URI tài nguyên mới.
- [ ] Response `204 No Content` không chứa body.
- [ ] `Content-Type` tương thích với định dạng mà API công bố.
- [ ] Header cache, ETag, CORS, authentication hoặc correlation được xác nhận khi thuộc hợp đồng.
- [ ] Header động được kiểm tra bằng điều kiện ổn định thay vì giá trị ngẫu nhiên.
- [ ] Cookie có đúng tên, giá trị, path, domain và thời hạn.
- [ ] Cookie nhạy cảm có các thuộc tính bảo vệ như `HttpOnly`, `Secure` và `SameSite` theo chính sách.
- [ ] Test phân biệt cookie được thêm qua Servlet API với cookie được đặt trực tiếp trong header `Set-Cookie`.
- [ ] Test không giả định MockMvc đã xác nhận browser, proxy hoặc HTTP connector thực tế.

Kiểm tra status code, header và cookie giúp bài test Spring MVC xác nhận đầy đủ hơn hợp đồng HTTP mà controller công bố. `MockMvc` cho phép kiểm tra chính xác response do Spring tạo ra trong context kiểm thử; với hành vi phụ thuộc trình duyệt, proxy hoặc container thật, cần thêm kiểm thử ở đúng tầng đó.

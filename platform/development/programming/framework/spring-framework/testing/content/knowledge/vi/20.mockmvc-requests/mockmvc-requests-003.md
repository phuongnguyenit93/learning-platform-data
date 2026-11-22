# Header, cookie và session attributes

Khi kiểm thử controller bằng MockMvc, request có thể mang nhiều loại thông tin ngoài URL và body: HTTP header, cookie và trạng thái session. Ba loại dữ liệu này đều đi vào request nhưng có cách truyền, vòng đời và ý nghĩa khác nhau. Kiểm thử cần thiết lập đúng loại dữ liệu mà controller thực sự đọc, sau đó xác nhận kết quả ở đúng phía request hoặc response.

## Phân biệt header, cookie và session

| Thành phần | Nằm ở đâu | Dùng để làm gì | Cách đưa vào MockMvc |
| --- | --- | --- | --- |
| Request header | Metadata của HTTP request | Content negotiation, ngôn ngữ, request id, thông tin client hoặc token | `.header(...)`, `.headers(...)`, `.accept(...)`, `.contentType(...)` |
| Cookie | Cặp tên/giá trị client gửi trong request; server có thể trả cookie qua `Set-Cookie` | Tùy chọn người dùng, dấu nhận diện hoặc session id | `.cookie(new Cookie(...))`; kiểm tra response bằng `cookie()` hoặc header `Set-Cookie` |
| Session attribute | Dữ liệu phía server gắn với `HttpSession` | Trạng thái cần tồn tại qua nhiều request của cùng session | `.session(...)`, `.sessionAttr(...)`, `.sessionAttrs(...)` |

Một session thường được client nhận diện bằng session cookie, chẳng hạn `JSESSIONID`, nhưng các thuộc tính như `userId` hay `cartId` được lưu ở phía server trong `HttpSession`. Vì vậy, gửi một cookie tùy ý không tự tạo ra session có các attribute tương ứng. Trong MockMvc, cách trực tiếp để kiểm tra trạng thái session là truyền đối tượng `MockHttpSession` vào request.

## Gửi request header

`MockHttpServletRequestBuilder` cung cấp `.header(name, values...)` để thêm một hoặc nhiều giá trị cho header. Có thể gọi phương thức này nhiều lần với cùng tên header để tạo header nhiều giá trị. Tên header HTTP không phân biệt chữ hoa và chữ thường.

```java
mockMvc.perform(get("/api/reports")
        .header("X-Tenant-Id", "tenant-a")
        .header("X-Request-Id", "req-123")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
```

Các phương thức chuyên biệt giúp request thể hiện rõ ý định:

- `.accept(MediaType.APPLICATION_JSON)` thiết lập header `Accept`, mô tả kiểu response client có thể nhận.
- `.contentType(MediaType.APPLICATION_JSON)` thiết lập `Content-Type`, mô tả kiểu dữ liệu của request body.
- `.headers(HttpHeaders)` đưa một tập header đã chuẩn bị vào request.
- `.header(name, value...)` phù hợp khi chỉ cần thêm một vài header tại chỗ.

Ví dụ dùng `HttpHeaders` khi nhiều test cùng cần một nhóm metadata:

```java
HttpHeaders headers = new HttpHeaders();
headers.set("X-Tenant-Id", "tenant-a");
headers.setAccept(List.of(MediaType.APPLICATION_JSON));

mockMvc.perform(get("/api/reports").headers(headers))
    .andExpect(status().isOk());
```

Không nên nhầm header với query parameter hoặc form field. `.param("page", "2")` gửi parameter; `.header("X-Page", "2")` gửi metadata HTTP. Controller có thể đọc chúng bằng các cơ chế khác nhau như `@RequestParam` và `@RequestHeader`.

### Controller đọc header

Một controller có thể khai báo header bắt buộc bằng `@RequestHeader`:

```java
@GetMapping("/api/reports")
ResponseEntity<List<Report>> reports(
        @RequestHeader("X-Tenant-Id") String tenantId) {

    List<Report> reports = reportService.findByTenant(tenantId);
    return ResponseEntity.ok()
            .header("X-Resolved-Tenant", tenantId)
            .body(reports);
}
```

Test vừa gửi header vừa kiểm tra response mà controller tạo ra:

```java
mockMvc.perform(get("/api/reports")
        .header("X-Tenant-Id", "tenant-a"))
    .andExpect(status().isOk())
    .andExpect(header().string("X-Resolved-Tenant", "tenant-a"));
```

`header()` trong `MockMvcResultMatchers` kiểm tra **response header**. Nó không xác nhận request header mà test đã gửi. Nếu cần kiểm tra chính xác request sau khi MockMvc tạo nó, có thể đọc request từ `MvcResult`:

```java
mockMvc.perform(get("/api/reports")
        .header("X-Tenant-Id", "tenant-a"))
    .andDo(result -> assertThat(
            result.getRequest().getHeader("X-Tenant-Id"))
            .isEqualTo("tenant-a"));
```

Trong test controller thông thường, nên ưu tiên kiểm tra hành vi phụ thuộc header hoặc response mà controller tạo ra. Chỉ kiểm tra trực tiếp request khi cần xác nhận cấu hình request builder hoặc một thành phần xử lý request ở tầng thấp.

## Kiểm tra response header

`MockMvcResultMatchers.header()` cung cấp các matcher để kiểm tra header trả về:

```java
mockMvc.perform(get("/api/reports/42"))
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(header().string("Cache-Control", "no-store"))
    .andExpect(header().doesNotExist("X-Debug-Info"));
```

Các dạng kiểm tra thường dùng:

| Matcher | Ý nghĩa |
| --- | --- |
| `exists(name)` | Response có header mang tên đó |
| `doesNotExist(name)` | Response không có header đó |
| `string(name, expected)` | Giá trị header bằng chuỗi mong đợi |
| `string(name, matcher)` | Giá trị header thỏa Hamcrest matcher |
| `stringValues(name, values...)` | Danh sách giá trị của header bằng các giá trị mong đợi |
| `longValue(name, value)` | Giá trị header có thể chuyển thành số long và bằng giá trị mong đợi |
| `dateValue(name, value)` | Giá trị header là ngày HTTP tương ứng với mốc thời gian mong đợi |

Với header nhiều giá trị, dùng `stringValues` để biểu đạt rõ danh sách cần kiểm tra:

```java
mockMvc.perform(get("/api/reports"))
    .andExpect(header().stringValues(
            "X-Report-Tag", "finance", "monthly"));
```

Chỉ assert các header thuộc hợp đồng của endpoint hoặc có ý nghĩa với hành vi đang kiểm tra. Những header do môi trường hoặc container tạo ra có thể thay đổi giữa các cấu hình; phụ thuộc vào chúng thường khiến test kém ổn định.

## Gửi request cookie

Để gửi cookie trong request, tạo `jakarta.servlet.http.Cookie` rồi truyền qua `.cookie(...)`:

```java
Cookie localeCookie = new Cookie("locale", "vi");

mockMvc.perform(get("/preferences")
        .cookie(localeCookie))
    .andExpect(status().isOk());
```

Có thể gửi nhiều cookie cùng lúc:

```java
mockMvc.perform(get("/preferences")
        .cookie(
                new Cookie("locale", "vi"),
                new Cookie("theme", "dark")))
    .andExpect(status().isOk());
```

Trong request, trình duyệt gửi tên và giá trị cookie. Các thuộc tính như `Path`, `Domain`, `Secure` và `HttpOnly` là chỉ thị trong response `Set-Cookie`; chúng không được gửi ngược lại thành thuộc tính của từng request cookie. Vì vậy, khi kiểm tra controller đọc cookie, test chủ yếu cần đúng tên và giá trị.

### Controller đọc cookie

`@CookieValue` bind cookie vào tham số controller:

```java
@GetMapping("/preferences")
PreferenceView preferences(
        @CookieValue(value = "locale", defaultValue = "vi") String locale) {

    return new PreferenceView(locale);
}
```

Test có thể xác nhận giá trị cookie ảnh hưởng đến response:

```java
mockMvc.perform(get("/preferences")
        .cookie(new Cookie("locale", "en")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.locale").value("en"));
```

Nếu cookie là bắt buộc, cần kiểm tra cả trường hợp thiếu cookie theo hợp đồng endpoint. Nếu có `defaultValue` hoặc `required = false`, hãy kiểm tra giá trị mặc định tương ứng. Không nên chỉ kiểm tra trường hợp cookie hợp lệ vì lỗi thường xuất hiện ở nhánh thiếu hoặc sai định dạng.

## Tạo và kiểm tra response cookie

Controller có thể thêm cookie vào response bằng `HttpServletResponse.addCookie(...)`:

```java
@PostMapping("/preferences/theme")
void saveTheme(
        @RequestParam String theme,
        HttpServletResponse response) {

    Cookie cookie = new Cookie("theme", theme);
    cookie.setPath("/");
    cookie.setHttpOnly(true);
    cookie.setSecure(true);
    cookie.setMaxAge(60 * 60);

    response.addCookie(cookie);
}
```

Dùng `MockMvcResultMatchers.cookie()` để kiểm tra cookie được trả về:

```java
mockMvc.perform(post("/preferences/theme")
        .param("theme", "dark"))
    .andExpect(status().isOk())
    .andExpect(cookie().exists("theme"))
    .andExpect(cookie().value("theme", "dark"))
    .andExpect(cookie().path("theme", "/"))
    .andExpect(cookie().httpOnly("theme", true))
    .andExpect(cookie().secure("theme", true))
    .andExpect(cookie().maxAge("theme", 3600));
```

Các thuộc tính cookie thường cần xác nhận:

- **Value:** giá trị client sẽ gửi lại ở request phù hợp.
- **Path:** giới hạn đường dẫn mà client gửi cookie.
- **Domain:** giới hạn host hoặc domain nhận cookie.
- **Max-Age:** thời gian sống tính bằng giây; giá trị âm thường biểu thị cookie theo phiên, còn `0` yêu cầu xóa cookie.
- **Secure:** client chỉ gửi cookie qua kết nối bảo mật HTTPS.
- **HttpOnly:** ngăn JavaScript phía client đọc cookie qua API cookie thông thường.

Khi xóa cookie, response thường gửi lại cookie cùng tên và phạm vi `Path`/`Domain` tương ứng với `Max-Age=0`. Test nên xác nhận cookie hết hạn theo hợp đồng của ứng dụng; chỉ kiểm tra rằng cookie không còn trong response là chưa đủ để chứng minh client sẽ xóa cookie cũ.

Nếu ứng dụng tạo `Set-Cookie` bằng `ResponseCookie` hoặc tự ghi trực tiếp header `Set-Cookie`, hãy kiểm tra header response tương ứng. Matcher `cookie()` làm việc với các cookie mà mock response nhận qua API cookie; một header `Set-Cookie` được ghi thủ công không nhất thiết xuất hiện trong danh sách cookie mock. Với response có nhiều cookie, cần kiểm tra từng giá trị `Set-Cookie` thay vì giả định chỉ có một header.

`MockMvc` không chạy trình duyệt. Vì vậy, matcher xác nhận server đã tạo cookie với các thuộc tính mong muốn; nó không mô phỏng việc trình duyệt có chấp nhận cookie, gửi cookie trên HTTPS hay áp dụng chính sách bảo mật của trình duyệt hay không.

## Thiết lập session attributes cho request

Session attribute là dữ liệu lưu trong `HttpSession`. Có hai cách thuận tiện để cung cấp dữ liệu đó cho MockMvc.

### Dùng `.sessionAttr(...)` hoặc `.sessionAttrs(...)`

Khi test chỉ cần một vài giá trị session, có thể dùng builder trực tiếp:

```java
mockMvc.perform(get("/account")
        .sessionAttr("userId", 42L)
        .sessionAttr("displayName", "An"))
    .andExpect(status().isOk());
```

Nếu có sẵn một map:

```java
Map<String, Object> attributes = Map.of(
        "userId", 42L,
        "displayName", "An");

mockMvc.perform(get("/account")
        .sessionAttrs(attributes))
    .andExpect(status().isOk());
```

Các phương thức này giúp test ngắn gọn khi chỉ cần khởi tạo trạng thái đầu vào. MockMvc tạo hoặc sử dụng session cho request để chứa các attribute đã cung cấp.

### Dùng `MockHttpSession`

Khi cần kiểm soát session cụ thể hoặc tái sử dụng cùng session qua nhiều request, tạo `MockHttpSession`:

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute("userId", 42L);
session.setAttribute("cartId", "cart-123");

mockMvc.perform(get("/cart").session(session))
    .andExpect(status().isOk());
```

`MockHttpSession` hữu ích khi test cần đọc, thêm, thay đổi hoặc xóa attribute trước và sau một request. Có thể kiểm tra session attribute của request bằng matcher `request()`:

```java
mockMvc.perform(get("/cart").session(session))
    .andExpect(request().sessionAttribute("userId", 42L))
    .andExpect(request().sessionAttribute("cartId", "cart-123"))
    .andExpect(request().sessionAttributeDoesNotExist("admin"));
```

Các matcher này xác nhận trạng thái session gắn với request được xử lý. Chúng khác với `header()` và `cookie()`, vốn kiểm tra dữ liệu HTTP response.

## Kiểm tra session được duy trì giữa nhiều request

Một tình huống quan trọng là request đầu tiên tạo hoặc cập nhật session, request tiếp theo đọc lại trạng thái đó. Hãy dùng cùng một đối tượng `MockHttpSession` cho các request trong test để mô phỏng cùng một phiên làm việc.

Ví dụ, endpoint đăng nhập lưu `userId` vào session và endpoint hồ sơ đọc lại attribute đó:

```java
MvcResult loginResult = mockMvc.perform(post("/login")
        .param("username", "an")
        .param("password", "secret"))
    .andExpect(status().isOk())
    .andReturn();

MockHttpSession session = (MockHttpSession)
        loginResult.getRequest().getSession(false);

assertThat(session).isNotNull();
assertThat(session.getAttribute("userId")).isEqualTo(42L);

mockMvc.perform(get("/account").session(session))
    .andExpect(status().isOk())
    .andExpect(request().sessionAttribute("userId", 42L));
```

Ở đây, test lấy session sau request đăng nhập rồi truyền chính đối tượng đó vào request hồ sơ. Cách làm này xác nhận trạng thái phía server được giữ qua hai lần gọi trong cùng test.

Nếu controller tạo session trong request đầu tiên, `getSession(false)` giúp lấy session hiện có mà không tạo thêm session mới. Nếu kết quả là `null`, request đó chưa tạo session hoặc chưa có session được gắn vào request; cần kiểm tra lại hành vi mong đợi của endpoint.

MockMvc không mô phỏng đầy đủ việc trình duyệt lưu và gửi `JSESSIONID` qua mạng. Truyền cùng `MockHttpSession` là cách tường minh để kiểm tra logic dùng session trong MVC test. Nếu mục tiêu là xác nhận container thật phát hành session cookie, xử lý cookie trên HTTP và duy trì session giữa các kết nối, cần một kiểm thử chạy với servlet container thực tế.

## Controller truy cập session attributes

Spring MVC cho phép đọc session attribute có sẵn bằng `@SessionAttribute`:

```java
@GetMapping("/account")
AccountView account(@SessionAttribute("userId") Long userId) {
    return accountService.findView(userId);
}
```

Test thiết lập attribute bằng `.sessionAttr(...)` rồi kiểm tra response:

```java
mockMvc.perform(get("/account")
        .sessionAttr("userId", 42L))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.userId").value(42L));
```

`@SessionAttribute` dùng để truy cập attribute đã tồn tại trong session. Nó không đồng nghĩa với `@SessionAttributes` ở cấp controller. `@SessionAttributes` chỉ định các model attribute mà Spring MVC sẽ lưu trong session trong một quy trình làm việc của controller; khi quy trình hoàn tất, controller có thể gọi `SessionStatus.setComplete()` để kết thúc việc lưu các attribute đó. Khi test loại controller này, cần kiểm tra cả việc attribute được lưu và việc trạng thái được dọn theo đúng thời điểm.

Nếu endpoint cho phép không có session attribute, khai báo tùy chọn như `@SessionAttribute(value = "userId", required = false)` hoặc xử lý trường hợp thiếu theo thiết kế. Test nên có cả request có attribute và request thiếu attribute để xác nhận hành vi thực tế.

## Phân biệt session attribute, request attribute và flash attribute

Ba loại attribute có vòng đời khác nhau:

| Loại | Vòng đời | Cách thiết lập trong MockMvc |
| --- | --- | --- |
| Request attribute | Một request hiện tại | `.requestAttr(name, value)` |
| Session attribute | Nhiều request trong cùng session | `.sessionAttr(name, value)` hoặc `.session(session)` |
| Flash attribute | Thường dùng để chuyển dữ liệu qua redirect sang request kế tiếp | `.flashAttr(name, value)` |

Không dùng `.requestAttr(...)` để mô phỏng trạng thái đăng nhập hoặc giỏ hàng cần tồn tại qua request. Tương tự, flash attribute phù hợp với dữ liệu tạm thời sau redirect, không phải nơi lưu trạng thái lâu dài của người dùng. Chọn sai loại attribute có thể làm test chạy qua nhưng không phản ánh đúng vòng đời dữ liệu trong ứng dụng.

## Kết hợp header, cookie và session trong cùng request

Một endpoint có thể đọc đồng thời tenant từ header, ngôn ngữ từ cookie và người dùng từ session. MockMvc cho phép thiết lập cả ba trên cùng request builder:

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute("userId", 42L);

mockMvc.perform(get("/api/dashboard")
        .header("X-Tenant-Id", "tenant-a")
        .cookie(new Cookie("locale", "vi"))
        .session(session)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.tenantId").value("tenant-a"))
    .andExpect(jsonPath("$.locale").value("vi"))
    .andExpect(jsonPath("$.userId").value(42L));
```

Khi test thất bại, hãy xác định lớp dữ liệu nào gây ra lỗi: header không được bind, cookie thiếu hoặc sai giá trị, session chưa có attribute, hay nghiệp vụ xử lý dữ liệu sai. Việc thiết lập từng loại dữ liệu tường minh giúp tìm nguyên nhân nhanh hơn và tránh dùng cookie để thay thế session hoặc dùng request attribute để thay thế session attribute.

## Lỗi thường gặp khi kiểm thử

- **Dùng `header()` để kiểm tra request header:** matcher này kiểm tra response. Dùng `MvcResult.getRequest()` nếu thực sự cần đọc request đã gửi.
- **Đưa cookie vào header bằng chuỗi tùy ý:** `.cookie(new Cookie(...))` thể hiện đúng cấu trúc cookie và tránh tự ghép header `Cookie` sai định dạng.
- **Cho rằng thuộc tính `HttpOnly` hoặc `Secure` có trong request cookie:** đây là thuộc tính của response `Set-Cookie`; kiểm tra chúng ở response.
- **Dùng một cookie tùy ý thay cho session:** cookie chỉ là dữ liệu client gửi. Session attribute nằm trong đối tượng session phía server.
- **Tạo session mới cho mỗi request trong cùng một kịch bản:** request sau sẽ không nhìn thấy attribute của session trước. Hãy tái sử dụng cùng `MockHttpSession`.
- **Nhầm request attribute với session attribute:** request attribute chỉ tồn tại trong một request, còn session attribute tồn tại trong phiên làm việc.
- **Giả định MockMvc kiểm tra được hành vi trình duyệt:** MockMvc kiểm tra request/response ở tầng Spring MVC, không thực thi chính sách lưu cookie của trình duyệt.
- **Assert header do môi trường tự sinh mà không có hợp đồng rõ ràng:** kết quả có thể khác giữa mock environment và servlet container thật.

## Quy trình xây dựng test

1. Xác định controller đọc dữ liệu qua `@RequestHeader`, `@CookieValue`, `@SessionAttribute` hay trực tiếp từ `HttpServletRequest`/`HttpSession`.
2. Tạo đúng dữ liệu đầu vào bằng `.header(...)`, `.cookie(...)`, `.sessionAttr(...)` hoặc `.session(...)`.
3. Thực hiện request và kiểm tra status cùng response body.
4. Kiểm tra response header bằng `header()` và response cookie bằng `cookie()` hoặc `Set-Cookie` header theo cách ứng dụng tạo cookie.
5. Kiểm tra session attribute bằng `request().sessionAttribute(...)`; nếu cần mô phỏng nhiều request, truyền lại cùng `MockHttpSession`.
6. Bổ sung trường hợp thiếu header, cookie hoặc session attribute theo hợp đồng của endpoint.
7. Nếu cần xác nhận hành vi của browser hoặc servlet container thật, chuyển phần đó sang kiểm thử tích hợp phù hợp thay vì suy luận từ mock response.

Thiết lập đúng header, cookie và session attributes giúp MockMvc kiểm tra được cách Spring MVC nhận metadata HTTP, đọc dữ liệu từ client và duy trì trạng thái phía server. Khi assertion cũng đặt đúng phía request hoặc response và đúng vòng đời dữ liệu, test sẽ phản ánh chính xác hơn hợp đồng của endpoint.

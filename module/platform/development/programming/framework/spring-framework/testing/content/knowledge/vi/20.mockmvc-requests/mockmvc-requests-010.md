# Đường dẫn context, servlet và thông tin yêu cầu

Khi dùng `MockMvc`, một request không chỉ có HTTP method và URL. `DispatcherServlet` còn nhận được các thông tin theo Servlet API như context path, servlet path, path info, query parameters, headers, body, cookies, session và request attributes. Thiết lập đúng những dữ liệu này giúp test mô phỏng chính xác cách ứng dụng được triển khai và cách client gửi request.

Phần đường dẫn cần được hiểu rõ nhất. `requestURI`, `contextPath`, `servletPath` và `pathInfo` mô tả những phần khác nhau của cùng một đường dẫn. Nếu ứng dụng chạy dưới context path hoặc `DispatcherServlet` được ánh xạ vào một servlet path riêng, test phải khai báo các phần đó nhất quán với request URI.

## 1. Các thành phần của đường dẫn Servlet

Servlet API cung cấp một số thuộc tính để mô tả đường dẫn request:

- **`requestURI`** là đường dẫn request trên server, bao gồm context path và phần đường dẫn còn lại. Query string không thuộc `requestURI`.
- **`contextPath`** là tiền tố mà web application được triển khai dưới đó. Ứng dụng chạy ở root context thường có context path rỗng; ứng dụng triển khai dưới `/shop` có context path là `/shop`.
- **`servletPath`** là phần đường dẫn được ánh xạ tới servlet đang xử lý request.
- **`pathInfo`** là phần đường dẫn còn lại sau `servletPath` đối với kiểu servlet mapping theo path; nó có thể là `null`.
- **Query string** chứa các tham số nằm sau dấu `?`, ví dụ `?page=2&sort=name`.

Với một request được xử lý bởi servlet có mapping `/api/*`, ví dụ đường dẫn đầy đủ là `/shop/api/orders/42`, các giá trị thường có dạng:

| Thuộc tính | Giá trị | Ý nghĩa |
|---|---|---|
| `requestURI` | `/shop/api/orders/42` | Đường dẫn request trên server |
| `contextPath` | `/shop` | Ứng dụng được triển khai dưới `/shop` |
| `servletPath` | `/api` | Phần khớp với servlet mapping `/api/*` |
| `pathInfo` | `/orders/42` | Phần còn lại sau servlet path |
| Query string | `?expand=items` | Thông tin truy vấn, tách khỏi request URI |

Có thể hình dung phần đường dẫn theo quan hệ:

```text
requestURI = contextPath + servletPath + pathInfo

/shop/api/orders/42
  |----| |--| |-------|
  context servlet pathInfo
  path   path
```

Đây là cách phân tách thường gặp với path mapping. Giá trị cụ thể phụ thuộc servlet mapping mà ứng dụng sử dụng. Với `DispatcherServlet` được ánh xạ vào `/`, phần đường dẫn ứng dụng thường nằm trong `servletPath` và `pathInfo` thường là `null`.

## 2. Thiết lập contextPath, servletPath và pathInfo trong MockMvc

Các request builder như `get(...)`, `post(...)` và `put(...)` nhận đường dẫn request. Khi ứng dụng chạy ở root context và dùng servlet mapping mặc định, chỉ cần truyền đường dẫn thông thường:

```java
mockMvc.perform(get("/orders/42"))
    .andExpect(status().isOk());
```

Nếu ứng dụng được triển khai dưới context path `/shop` và `DispatcherServlet` được ánh xạ theo `/api/*`, hãy đặt các thành phần đường dẫn rõ ràng:

```java
mockMvc.perform(get("/shop/api/orders/42")
        .contextPath("/shop")
        .servletPath("/api")
        .pathInfo("/orders/42"))
    .andExpect(status().isOk());
```

Ở đây:

- URI truyền vào `get(...)` là đường dẫn request đầy đủ.
- `contextPath("/shop")` mô phỏng nơi ứng dụng được triển khai.
- `servletPath("/api")` mô phỏng phần khớp với servlet mapping `/api/*`.
- `pathInfo("/orders/42")` là phần còn lại được chuyển cho Spring MVC xử lý.

Các giá trị này phải khớp với đường dẫn request và mapping của servlet. Nếu khai báo context path hoặc servlet path không phù hợp với URI, request mock có thể không hợp lệ hoặc Spring MVC sẽ tìm handler theo một đường dẫn khác với mong đợi.

Không đưa query string vào `contextPath`, `servletPath` hay `pathInfo`. Hãy thiết lập query parameters riêng bằng request builder.

## 3. Path variable và query parameter

Path variable là một phần của đường dẫn, thường được khai báo bằng `@PathVariable`. Query parameter là dữ liệu truy vấn sau dấu `?`, thường được nhận bằng `@RequestParam`.

Ví dụ controller:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/orders/{orderId}")
    OrderView findOrder(
            @PathVariable String orderId,
            @RequestParam(defaultValue = "false") boolean includeItems) {
        return new OrderView(orderId, includeItems);
    }
}
```

Test có thể điền giá trị path variable bằng URI template và truyền query parameter bằng `queryParam(...)`:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/orders/{orderId}", "ORD-42")
        .queryParam("includeItems", "true"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.orderId").value("ORD-42"))
    .andExpect(jsonPath("$.includeItems").value(true));
```

URI template giúp Spring thay giá trị vào đúng vị trí của path variable và xử lý việc mã hóa URI theo cơ chế của request builder. Với nhiều query parameter cùng tên, có thể truyền nhiều giá trị:

```java
mockMvc.perform(get("/search")
    .queryParam("tag", "spring", "testing"));
```

`queryParam(...)` biểu diễn rõ tham số trên query string. `param(...)` thiết lập request parameter trong Servlet request; nó thường được dùng khi controller chỉ quan tâm giá trị `@RequestParam`, kể cả trong test request dạng form. Nếu test cần kiểm tra chính xác query string hoặc cách URL được tạo, nên dùng `queryParam(...)` hoặc đặt query trong URI.

## 4. Gửi HTTP method, header và content negotiation

Request builder có các phương thức tương ứng với HTTP method như `get`, `post`, `put`, `patch`, `delete`, `options` và `head`. Có thể bổ sung header bằng `header(...)`; nhiều giá trị có thể được truyền cho cùng một header.

```java
import org.springframework.http.MediaType;

mockMvc.perform(get("/orders/ORD-42")
        .header("X-Trace-Id", "trace-246")
        .header("X-Client", "web", "mobile")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
```

`accept(...)` mô tả kiểu response mà client chấp nhận thông qua header `Accept`. `contentType(...)` mô tả kiểu dữ liệu được gửi trong request thông qua header `Content-Type`. Hai giá trị này có ý nghĩa khác nhau:

```java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": "C-208",
              "total": 250000
            }
            """))
    .andExpect(status().isCreated());
```

`content(...)` đặt request body. Khi kiểm thử JSON, hãy đặt `Content-Type` phù hợp và gửi JSON hợp lệ; nếu controller trả JSON, đặt `Accept` để thể hiện định dạng response mong đợi. Nếu ứng dụng dùng message converter, test theo cách này sẽ đi qua quá trình đọc body và chuyển đổi dữ liệu của Spring MVC.

## 5. Cookie, session và flash attributes

Request có thể mang thông tin qua cookie hoặc session. MockMvc hỗ trợ các cách thiết lập ngắn gọn:

```java
import jakarta.servlet.http.Cookie;
import org.springframework.mock.web.MockHttpSession;

MockHttpSession session = new MockHttpSession();
session.setAttribute("userId", "U-17");

mockMvc.perform(get("/account")
        .cookie(new Cookie("locale", "vi"))
        .session(session))
    .andExpect(status().isOk());
```

Nếu chỉ cần thêm một vài session attribute, có thể dùng `sessionAttr(...)` hoặc `sessionAttrs(...)` thay vì tạo `MockHttpSession` thủ công:

```java
mockMvc.perform(get("/account")
    .sessionAttr("userId", "U-17"));
```

Flash attributes dùng để truyền dữ liệu qua luồng redirect. Có thể thiết lập bằng `flashAttr(...)` hoặc `flashAttrs(...)`:

```java
mockMvc.perform(get("/orders/complete")
    .flashAttr("notice", "Order saved"));
```

Hãy chọn đúng nơi lưu dữ liệu theo hợp đồng của controller: cookie là dữ liệu client gửi trong request; session lưu trạng thái gắn với phiên; flash attribute phục vụ việc chuyển thông tin qua redirect; request attribute chỉ tồn tại trong request hiện tại.

## 6. Request attributes và thông tin client

Một số controller hoặc interceptor đọc request attribute do filter hoặc tầng trước đó đặt vào. Có thể thiết lập chúng trực tiếp:

```java
mockMvc.perform(get("/internal/report")
    .requestAttr("correlationId", "corr-246"));
```

Các thông tin khác có thể được đặt qua request builder:

```java
import java.util.Locale;

mockMvc.perform(get("/profile")
    .locale(Locale.forLanguageTag("vi-VN"))
    .secure(true)
    .characterEncoding("UTF-8")
    .remoteAddress("192.0.2.10"));
```

Những thuộc tính này giúp mô phỏng ngôn ngữ, kết nối bảo mật, encoding và địa chỉ client mà ứng dụng có thể sử dụng. Chỉ đặt chúng khi luồng cần kiểm thử thực sự phụ thuộc vào các thông tin đó.

Nếu cần thiết lập dữ liệu phức tạp hoặc mô phỏng một hành vi của Servlet request, request builder hỗ trợ `with(...)` để nhận `RequestPostProcessor`:

```java
mockMvc.perform(get("/profile").with(request -> {
    request.setAttribute("tenantId", "tenant-17");
    return request;
}));
```

Với ứng dụng Spring Security, các post processor như `user(...)`, `anonymous()` hoặc `csrf()` được cung cấp bởi thư viện kiểm thử Spring Security. Chúng cần dependency `spring-security-test`; đây không phải các phương thức cốt lõi của Servlet request builder.

## 7. Dùng defaultRequest cho thông tin chung

Khi nhiều request trong cùng một `MockMvc` cần các header hoặc thiết lập chung, có thể cấu hình `defaultRequest(...)` trên builder:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .defaultRequest(get("/")
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Test-Client", "mockmvc"))
    .build();
```

Các thiết lập mặc định được áp dụng khi thực hiện request; từng request vẫn có thể cung cấp giá trị riêng cho những thông tin cần thay đổi. Nên dùng default request cho dữ liệu thật sự chung của bộ test, chẳng hạn `Accept` hoặc header nhận diện client. Đường dẫn, method, body và parameter thuộc từng tình huống kiểm thử nên được khai báo tại `perform(...)` để người đọc thấy rõ request đang được gửi.

## 8. Phân biệt các loại dữ liệu request

| Dữ liệu | Request builder | Nơi ứng dụng thường đọc |
|---|---|---|
| Path variable | URI template trong `get(...)`, `post(...)`... | `@PathVariable` |
| Query parameter | `queryParam(...)` | `@RequestParam` |
| Servlet request parameter | `param(...)` | `getParameter(...)`, `@RequestParam` |
| Header | `header(...)`, `headers(...)` | `@RequestHeader`, `getHeader(...)` |
| Request body | `content(...)` và `contentType(...)` | `@RequestBody`, message converter |
| Cookie | `cookie(...)` | `@CookieValue`, `getCookies()` |
| Session | `session(...)`, `sessionAttr(...)` | `HttpSession`, `@SessionAttribute` |
| Flash attribute | `flashAttr(...)`, `flashAttrs(...)` | `RedirectAttributes`, `FlashMap` |
| Request attribute | `requestAttr(...)`, `requestAttrs(...)` | `@RequestAttribute`, `getAttribute(...)` |
| Locale / secure / remote address | `locale(...)`, `secure(...)`, `remoteAddress(...)` | `LocaleResolver`, `isSecure()`, `getRemoteAddr()` |

Không nên dùng một loại dữ liệu thay cho loại khác chỉ vì controller có thể đọc được cả hai. Ví dụ, một giá trị nằm trong query string không tương đương với header cùng tên; request body JSON cũng không tương đương với request parameter. Test cần phản ánh đúng giao thức mà client thực sự sử dụng.

## 9. Lỗi thường gặp khi thiết lập request

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Request không khớp handler khi ứng dụng có context path | Chưa đặt `contextPath(...)` hoặc request URI chưa chứa đúng tiền tố triển khai |
| Controller không nhận được phần path sau servlet mapping | `servletPath(...)` và `pathInfo(...)` không phản ánh mapping thực tế của `DispatcherServlet` |
| Path variable không được bind | URI template không khớp `@RequestMapping`, sai số lượng segment hoặc giá trị path không đúng vị trí |
| `@RequestParam` không có giá trị | Dùng nhầm path variable, header hoặc body thay cho request parameter; kiểm tra tên và cách thiết lập parameter |
| JSON body không được chuyển đổi | Thiếu hoặc sai `Content-Type`, JSON không hợp lệ, hoặc message converter không hỗ trợ kiểu dữ liệu |
| `@RequestHeader` không nhận được giá trị | Header name sai hoặc header chưa được thêm vào request |
| Dữ liệu session không xuất hiện | Dùng request khác với session mong đợi hoặc chưa thiết lập session attribute |
| Test qua mock thành công nhưng URL triển khai thật sai | Cần xác nhận context path và servlet mapping thực tế của môi trường triển khai |

Khi request không đi vào controller mong đợi, hãy kiểm tra lần lượt HTTP method, request URI, context path, servlet path, path info và mapping của controller. Sau đó mới kiểm tra parameter, header, body và session. Trình tự này giúp phân biệt lỗi định tuyến với lỗi bind dữ liệu.

## 10. Quy trình xây dựng một request MockMvc rõ ràng

1. Chọn HTTP method và URI đúng với endpoint.
2. Nếu ứng dụng có context path hoặc servlet mapping riêng, thiết lập `contextPath`, `servletPath` và `pathInfo` sao cho khớp request URI.
3. Đưa path variable vào URI template; dùng `queryParam` hoặc `param` cho request parameter.
4. Thêm header, `Accept` và `Content-Type` theo giao thức của endpoint.
5. Gửi body bằng `content(...)` nếu endpoint nhận dữ liệu trong request body.
6. Thiết lập cookie, session, flash attribute hoặc request attribute nếu nghiệp vụ cần chúng.
7. Dùng result matcher để xác nhận status, header, content type và response body.

Một request MockMvc tốt cho người đọc biết rõ client đã gửi method nào, đến đường dẫn nào, trong context và servlet mapping nào, kèm dữ liệu ở đâu. Khi mô phỏng đúng các phần của Servlet request, test sẽ kiểm tra được cả định tuyến lẫn cách Spring MVC bind thông tin vào controller.

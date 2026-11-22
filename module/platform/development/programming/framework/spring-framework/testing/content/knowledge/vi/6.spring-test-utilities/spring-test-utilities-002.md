# MockHttpServletRequest, MockHttpServletResponse và MockHttpSession

Spring Framework Test cung cấp ba đối tượng giả lập Servlet API để kiểm thử code web mà không cần khởi động servlet container thật:

- `MockHttpServletRequest` mô phỏng một HTTP request đi vào ứng dụng.
- `MockHttpServletResponse` ghi nhận status, header, cookie và nội dung response mà code tạo ra.
- `MockHttpSession` mô phỏng session phía server và lưu các attribute trong bộ nhớ.

Các lớp này thuộc package `org.springframework.mock.web` trong module `spring-test`. Chúng hữu ích khi kiểm thử một thành phần làm việc trực tiếp với `HttpServletRequest`, `HttpServletResponse` hoặc `HttpSession`, chẳng hạn servlet, filter, interceptor, adapter hoặc một helper đọc thông tin request.

Chúng cũng là nền tảng mà nhiều tiện ích kiểm thử web cấp cao hơn của Spring sử dụng. Tuy vậy, tự tạo ba đối tượng này không đồng nghĩa với việc chạy toàn bộ Spring MVC: test chỉ kiểm soát những đối tượng được truyền trực tiếp cho code cần kiểm tra.

## 1. Ba đối tượng mô phỏng điều gì?

| Lớp | Vai trò | Dữ liệu thường được thiết lập hoặc đọc |
|---|---|---|
| `MockHttpServletRequest` | Mô phỏng request gửi đến servlet | HTTP method, URI, context path, servlet path, query string, parameter, header, cookie, body, locale, principal, session và request attribute. |
| `MockHttpServletResponse` | Mô phỏng response do servlet tạo ra | Status, header, cookie, content type, encoding, body, redirect, error và trạng thái committed. |
| `MockHttpSession` | Mô phỏng session phía server | Session id, attribute, thời điểm tạo, thời điểm truy cập, trạng thái mới và thời gian không hoạt động tối đa. |

Mối quan hệ thường gặp:

```text
Test
 │
 ├── tạo MockHttpServletRequest
 │       └── chứa parameter, header, body, cookie, session...
 │
 ├── tạo MockHttpServletResponse
 │       └── ghi status, header, cookie, body...
 │
 └── gọi thành phần cần kiểm thử
         ├── đọc request
         ├── có thể thay đổi session
         └── ghi response
```

Các đối tượng này thực thi một phần hợp đồng của Servlet API trong môi trường kiểm thử. Chúng không mở socket, không gửi HTTP qua mạng và không yêu cầu Tomcat, Jetty hay servlet container khác chạy thật.

## 2. Dependency và package

Các mock servlet object được cung cấp bởi module `spring-test`. Với ứng dụng Spring Boot, dependency `spring-boot-starter-test` thường đưa Spring Test vào test classpath. Với dự án Spring Framework không dùng Boot, có thể khai báo trực tiếp `org.springframework:spring-test` ở test scope cùng JUnit Jupiter và thư viện assertion cần thiết.

Ví dụ Gradle khi tự khai báo dependency:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
}

tasks.test {
    useJUnitPlatform()
}
```

Import các lớp chính:

```java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockServletContext;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.servlet.HandlerInterceptor;
import static org.assertj.core.api.Assertions.assertThat;
```

Các ví dụ bên dưới còn sử dụng các kiểu Servlet API như `Cookie`, `HttpServletRequest`, `HttpServletResponse` và `HttpSession`, cùng các kiểu Java tiêu chuẩn như `StandardCharsets`, `Locale`, `List`. Import Servlet API phải khớp namespace của phiên bản đang dùng: Spring Framework 6.x dùng `jakarta.servlet`; Spring Framework 5.x dùng `javax.servlet`.

Các mock này độc lập với việc khởi động `ApplicationContext`. Test có thể tạo chúng bằng constructor và truyền vào code cần kiểm thử. Nếu test cần Spring MVC dispatch, có thể dùng MockMvc; nếu chỉ cần một servlet request/response để gọi trực tiếp một thành phần, không cần tạo context chỉ để có ba đối tượng này.

## 3. Tạo và cấu hình MockHttpServletRequest

`MockHttpServletRequest` cho phép thiết lập request theo cách có thể lặp lại. Test không cần tạo chuỗi HTTP thô; chỉ cần đặt method, URI, parameter, header, body và các thuộc tính liên quan.

### 3.1. Khởi tạo request

Có thể dùng constructor mặc định hoặc constructor nhận servlet context, HTTP method và request URI. Khi cần kiểm thử resource lookup hoặc thuộc tính của servlet context, có thể truyền một `MockServletContext` rõ ràng:

```java
MockServletContext servletContext = new MockServletContext();
MockHttpServletRequest request = new MockHttpServletRequest(
        servletContext,
        "POST",
        "/shop/orders"
);
```

Nếu thành phần cần kiểm thử không phụ thuộc servlet context cụ thể, constructor đơn giản thường đủ:

```java
MockHttpServletRequest request = new MockHttpServletRequest();
request.setMethod("GET");
request.setRequestURI("/orders");
```

Hãy đặt các thuộc tính liên quan cùng nhau để test diễn đạt đúng request mà ứng dụng nhận được. Ví dụ request đến endpoint dưới context path `/shop`:

```java
MockHttpServletRequest request = new MockHttpServletRequest(
        "GET",
        "/shop/orders/42"
);
request.setContextPath("/shop");
request.setServletPath("/orders/42");
```

Trong Servlet API, các giá trị này có ý nghĩa khác nhau:

| Thuộc tính | Ví dụ | Ý nghĩa |
|---|---|---|
| Request URI | `/shop/orders/42` | Đường dẫn request được server nhận, thường bao gồm context path. |
| Context path | `/shop` | Đường dẫn gốc mà ứng dụng được triển khai dưới đó; có thể là chuỗi rỗng. |
| Servlet path | `/orders/42` | Phần đường dẫn được ánh xạ tới servlet. |
| Path info | `null` hoặc phần đường dẫn còn lại | Phần thông tin đường dẫn sau servlet path trong các kiểu mapping có hỗ trợ. |
| Query string | `page=2&size=20` | Phần query trong URL, không bao gồm dấu ?. |

Không nên gán các thuộc tính đường dẫn một cách tùy tiện nếu test đang kiểm tra logic phân tích URL hoặc servlet mapping. Một bộ giá trị không nhất quán có thể khiến test mô phỏng một request khó xảy ra trong container thật.

### 3.2. Query parameter và form parameter

Request parameter được thiết lập bằng `setParameter` hoặc `addParameter`. Dùng `setParameter` khi một giá trị duy nhất là đủ; dùng `addParameter` khi một tên có nhiều giá trị.

```java
MockHttpServletRequest request = new MockHttpServletRequest("GET", "/orders");
request.setParameter("page", "2");
request.setParameter("size", "20");

assertThat(request.getParameter("page")).isEqualTo("2");
assertThat(request.getParameter("size")).isEqualTo("20");
```

Với tham số nhiều giá trị:

```java
request.addParameter("status", "PAID", "SHIPPED");

assertThat(request.getParameter("status")).isEqualTo("PAID");
assertThat(request.getParameterValues("status"))
        .containsExactly("PAID", "SHIPPED");
```

Servlet API cung cấp parameter dưới dạng chuỗi. Việc chuyển thành số, ngày hoặc enum là trách nhiệm của code xử lý request hoặc của Spring MVC argument resolver khi chạy qua DispatcherServlet. Nếu gọi trực tiếp một helper, test cần kiểm tra chính logic chuyển đổi của helper đó.

### 3.3. Header, cookie và thông tin kết nối

Có thể thiết lập header bằng `addHeader` hoặc `setHeader`, cookie bằng `setCookies`, và các thuộc tính kết nối như scheme, server name, port, secure flag hoặc remote address.

```java
MockHttpServletRequest request = new MockHttpServletRequest("GET", "/profile");
request.addHeader("X-Request-Id", "req-123");
request.addHeader("Accept", "application/json");
request.setScheme("https");
request.setServerName("example.test");
request.setServerPort(443);
request.setSecure(true);
request.setRemoteAddr("192.0.2.10");
request.setCookies(new Cookie("theme", "dark"));
```

Các thuộc tính này hữu ích khi code cần tạo absolute URL, xác định request có an toàn hay không, đọc request id, kiểm tra cookie hoặc xử lý địa chỉ client. Chúng chỉ là giá trị test thiết lập trên object. Chúng không chứng minh proxy, load balancer hoặc container thật đã chuyển tiếp các header và địa chỉ đúng.

Khi kiểm thử code dựa vào thông tin người dùng, có thể thiết lập principal hoặc remote user trên request. Tuy nhiên, gán principal trực tiếp không tương đương với việc chạy Spring Security filter chain hoặc xác minh token thật.

### 3.4. Request body và encoding

Để mô phỏng request có body, đặt content type, character encoding và byte content:

```java
String json = """
        {"sku":"SKU-1","quantity":2}
        """;

MockHttpServletRequest request = new MockHttpServletRequest("POST", "/orders");
request.setContentType("application/json");
request.setCharacterEncoding(StandardCharsets.UTF_8.name());
request.setContent(json.getBytes(StandardCharsets.UTF_8));
```

Code sử dụng `getInputStream()` hoặc `getReader()` có thể đọc nội dung từ request mock. Khi dữ liệu có ký tự ngoài ASCII, hãy xác định encoding một cách tường minh để tránh test phụ thuộc encoding mặc định của môi trường.

Đặt `Content-Type` mô tả định dạng body, còn `setCharacterEncoding` xác định cách diễn giải văn bản. Với JSON, test nên dùng byte UTF-8 và khai báo content type phù hợp. Việc parse JSON trong một controller Spring MVC vẫn cần message converter; chỉ tạo request mock rồi gọi một helper không tự kích hoạt Jackson.

### 3.5. Request attribute và locale

Request attribute là dữ liệu gắn với một request trong quá trình xử lý, khác với parameter được gửi từ client và session attribute tồn tại qua nhiều request.

```java
request.setAttribute("correlationId", "corr-456");
request.setLocale(Locale.forLanguageTag("vi-VN"));

assertThat(request.getAttribute("correlationId")).isEqualTo("corr-456");
assertThat(request.getLocale()).isEqualTo(Locale.forLanguageTag("vi-VN"));
```

Request attribute thường được filter, interceptor hoặc servlet dùng để truyền dữ liệu cho bước xử lý tiếp theo. Locale có thể được dùng để kiểm tra code chọn thông báo hoặc định dạng theo ngôn ngữ.

## 4. Đọc và kiểm tra MockHttpServletResponse

`MockHttpServletResponse` ghi lại những gì code ghi vào response. Test có thể kiểm tra status, header, cookie, content type, encoding và body mà không cần nhận response qua HTTP thật.

### 4.1. Status và header

```java
MockHttpServletResponse response = new MockHttpServletResponse();
response.setStatus(HttpServletResponse.SC_CREATED);
response.setHeader("Location", "/orders/42");
response.addHeader("X-Request-Id", "req-123");

assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_CREATED);
assertThat(response.getHeader("Location")).isEqualTo("/orders/42");
assertThat(response.getHeader("X-Request-Id")).isEqualTo("req-123");
```

Phân biệt `setHeader` và `addHeader`: thao tác set thay giá trị header theo tên, còn add bổ sung một giá trị. Điều này quan trọng với header có thể lặp lại, ví dụ một số header dạng danh sách hoặc `Set-Cookie`.

### 4.2. Content type, character encoding và response body

Response có thể ghi nội dung thông qua writer hoặc output stream. Ví dụ:

```java
MockHttpServletResponse response = new MockHttpServletResponse();
response.setContentType("text/plain");
response.setCharacterEncoding(StandardCharsets.UTF_8.name());
response.getWriter().write("Đã tạo đơn hàng");

assertThat(response.getContentType()).isEqualTo("text/plain");
assertThat(response.getCharacterEncoding()).isEqualTo("UTF-8");
assertThat(new String(response.getContentAsByteArray(), StandardCharsets.UTF_8))
        .isEqualTo("Đã tạo đơn hàng");
```

`getContentAsByteArray()` cho phép đọc byte đã ghi. Khi so sánh văn bản, giải mã byte bằng đúng charset mà response sử dụng. Một số phiên bản Spring Test còn cung cấp `getContentAsString()`; hãy dùng API phù hợp với phiên bản Spring đang khai báo.

Servlet response không cho phép code tùy tiện trộn việc lấy writer và output stream trong cùng response. Test nên mô phỏng cách sử dụng thực tế của thành phần cần kiểm thử. Nếu code gọi `getWriter()`, hãy kiểm tra kết quả qua body đã ghi thay vì lấy một output stream khác sau đó.

### 4.3. Cookie, redirect và error response

Response mock ghi nhận cookie được thêm, URL redirect và thông tin lỗi:

```java
MockHttpServletResponse response = new MockHttpServletResponse();
response.addCookie(new Cookie("session-hint", "created"));
response.sendRedirect("/login");

assertThat(response.getRedirectedUrl()).isEqualTo("/login");
```

Với response lỗi:

```java
MockHttpServletResponse response = new MockHttpServletResponse();
response.sendError(HttpServletResponse.SC_NOT_FOUND, "Order not found");

assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_NOT_FOUND);
assertThat(response.getErrorMessage()).isEqualTo("Order not found");
```

Các helper như `sendRedirect` và `sendError` giúp test kiểm tra ý định phản hồi của code. Chúng không thực sự điều hướng trình duyệt hoặc gửi trang lỗi qua mạng.

### 4.4. Buffer và trạng thái committed

Response có buffer nội dung. Các thao tác như flush buffer hoặc send error/redirect có thể ảnh hưởng trạng thái committed theo hợp đồng Servlet API. Điều này quan trọng khi code cần biết liệu header hoặc status còn có thể thay đổi hay không.

Ví dụ:

```java
MockHttpServletResponse response = new MockHttpServletResponse();
assertThat(response.isCommitted()).isFalse();

response.flushBuffer();

assertThat(response.isCommitted()).isTrue();
```

Không nên kiểm thử sâu các chi tiết buffer nội bộ của mock nếu hành vi đó không thuộc trách nhiệm ứng dụng. Khi cần chứng minh tương tác thực tế với container, hãy bổ sung test chạy qua server thật.

## 5. Quản lý session bằng MockHttpSession

`MockHttpSession` mô phỏng vùng lưu trữ session phía server. Test có thể thêm, đọc, xóa attribute, kiểm tra session id hoặc trạng thái invalidation mà không cần cookie session thật được trao đổi qua trình duyệt.

### 5.1. Tạo session và lưu attribute

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute("userId", "user-42");
session.setAttribute("cartCount", 3);

assertThat(session.getAttribute("userId")).isEqualTo("user-42");
assertThat(session.getAttribute("cartCount")).isEqualTo(3);
```

Session attribute thường dùng để lưu thông tin gắn với phiên làm việc, ví dụ giỏ hàng hoặc một trạng thái wizard. Khi test, chỉ nên đặt những attribute mà code đang kiểm thử thực sự sử dụng.

### 5.2. Gắn session vào request

Một request có thể tạo session khi gọi `getSession()` hoặc `getSession(true)`. Gọi `getSession(false)` chỉ lấy session hiện có và trả về `null` nếu request chưa có session.

```java
MockHttpServletRequest request = new MockHttpServletRequest("GET", "/cart");

assertThat(request.getSession(false)).isNull();

HttpSession createdSession = request.getSession(true);
createdSession.setAttribute("cartId", "cart-100");

assertThat(request.getSession(false)).isSameAs(createdSession);
assertThat(request.getSession().getAttribute("cartId")).isEqualTo("cart-100");
```

Nếu cần bắt đầu với session đã tồn tại, tạo `MockHttpSession` riêng và gắn vào request:

```java
MockHttpSession existingSession = new MockHttpSession();
existingSession.setAttribute("userId", "user-42");

MockHttpServletRequest request = new MockHttpServletRequest("GET", "/account");
request.setSession(existingSession);

assertThat(request.getSession(false)).isSameAs(existingSession);
```

Đây là cách mô phỏng request thứ hai hoặc request tiếp theo của cùng một session. Nếu test cần kiểm tra việc ứng dụng tạo session mới, hãy bắt đầu với request không có session để tránh vô tình bỏ qua nhánh tạo session.

### 5.3. Xóa attribute và invalidate

Session có thể xóa từng attribute bằng `removeAttribute` hoặc kết thúc bằng `invalidate`:

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute("userId", "user-42");
session.setAttribute("cartId", "cart-100");

session.removeAttribute("cartId");
assertThat(session.getAttribute("cartId")).isNull();

session.invalidate();
assertThat(session.isInvalid()).isTrue();
```

Sau khi invalidate, session không còn là phiên hợp lệ. Khi kiểm thử code xử lý logout hoặc hết phiên, hãy xác nhận hành vi ứng dụng như xóa trạng thái đăng nhập, bỏ liên kết session hoặc tạo response phù hợp. Không nên tiếp tục thao tác với session đã invalidated như thể nó còn hoạt động bình thường.

### 5.4. Thuộc tính vòng đời session

`MockHttpSession` cung cấp các API để thiết lập hoặc đọc thông tin như id, thời điểm tạo, thời điểm truy cập cuối, trạng thái mới và thời gian không hoạt động tối đa. Các thuộc tính này hữu ích khi code cần kiểm tra metadata session.

Ví dụ thiết lập khoảng thời gian không hoạt động tối đa:

```java
MockHttpSession session = new MockHttpSession();
session.setMaxInactiveInterval(900);

assertThat(session.getMaxInactiveInterval()).isEqualTo(900);
```

Giá trị này mô phỏng cấu hình timeout của session. Nó không làm cho mock tự chạy đồng hồ nền và tự hết hạn như session store của container. Muốn kiểm thử chính sách hết hạn thực tế, cần kiểm tra lớp quản lý session hoặc môi trường container tương ứng.

## 6. Kết hợp request, response và session trong một unit test

Ví dụ sau minh họa một servlet-style handler nhận request, cập nhật session và ghi response. Mục tiêu là kiểm tra code xử lý trực tiếp Servlet API; test gọi phương thức bằng hai mock object đã chuẩn bị.

```java
public class CartHandler {

    public void addItem(HttpServletRequest request, HttpServletResponse response)
            throws IOException {
        String sku = request.getParameter("sku");
        if (sku == null || sku.isBlank()) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "Missing sku");
            return;
        }

        HttpSession session = request.getSession();
        @SuppressWarnings("unchecked")
        List<String> items = (List<String>) session.getAttribute("items");
        if (items == null) {
            items = new ArrayList<>();
            session.setAttribute("items", items);
        }
        items.add(sku);

        response.setStatus(HttpServletResponse.SC_ACCEPTED);
        response.setContentType("text/plain");
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write("Added " + sku);
    }
}
```

Test cho trường hợp thành công:

```java
@Test
void addsItemToSessionAndWritesResponse() throws Exception {
    CartHandler handler = new CartHandler();
    MockHttpServletRequest request = new MockHttpServletRequest("POST", "/cart/items");
    MockHttpServletResponse response = new MockHttpServletResponse();
    request.setParameter("sku", "SKU-1");

    handler.addItem(request, response);

    assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_ACCEPTED);
    assertThat(new String(response.getContentAsByteArray(), StandardCharsets.UTF_8))
            .isEqualTo("Added SKU-1");
    @SuppressWarnings("unchecked")
    List<String> items = (List<String>) request.getSession(false).getAttribute("items");
    assertThat(items).containsExactly("SKU-1");
}
```

Test cho trường hợp thiếu parameter:

```java
@Test
void rejectsMissingSkuWithoutCreatingSession() throws Exception {
    CartHandler handler = new CartHandler();
    MockHttpServletRequest request = new MockHttpServletRequest("POST", "/cart/items");
    MockHttpServletResponse response = new MockHttpServletResponse();

    handler.addItem(request, response);

    assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_BAD_REQUEST);
    assertThat(request.getSession(false)).isNull();
}
```

Điểm đáng chú ý là test có thể quan sát cả ba vùng trạng thái: dữ liệu request được gửi vào, session được thay đổi và response được ghi ra. Test không cần tạo `DispatcherServlet`, controller bean hay application context vì đang gọi trực tiếp handler.

## 7. Dùng mock servlet object với filter và interceptor

Các đối tượng này cũng hữu ích khi kiểm thử một thành phần nhận Servlet API trực tiếp. Ví dụ một filter đọc header và gắn request attribute có thể được gọi với request/response mock và một `FilterChain` giả. Tương tự, một `HandlerInterceptor` có thể được gọi trực tiếp để kiểm tra quyết định cho phép hoặc từ chối xử lý request.

Khi gọi trực tiếp filter hoặc interceptor, test cần cung cấp đầy đủ đối số mà thành phần đó yêu cầu. Nếu filter cần `FilterConfig`, có thể dùng tiện ích mock tương ứng như `MockFilterConfig`; nếu cần mô phỏng chain, có thể dùng `MockFilterChain` trong Spring Test. Chỉ tạo các đối tượng phụ trợ mà logic đang kiểm thử sử dụng.

Ví dụ đơn giản với interceptor:

```java
class RequestIdInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        String requestId = request.getHeader("X-Request-Id");
        if (requestId == null || requestId.isBlank()) {
            response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            return false;
        }

        request.setAttribute("requestId", requestId);
        return true;
    }
}
```

Test trực tiếp:

```java
@Test
void storesRequestIdWhenHeaderIsPresent() throws Exception {
    RequestIdInterceptor interceptor = new RequestIdInterceptor();
    MockHttpServletRequest request = new MockHttpServletRequest("GET", "/orders");
    MockHttpServletResponse response = new MockHttpServletResponse();
    request.addHeader("X-Request-Id", "req-123");

    boolean proceed = interceptor.preHandle(request, response, new Object());

    assertThat(proceed).isTrue();
    assertThat(request.getAttribute("requestId")).isEqualTo("req-123");
}
```

Gọi trực tiếp `preHandle` kiểm tra logic interceptor. Nó không chứng minh interceptor đã được đăng ký đúng trong MVC configuration hoặc được gọi theo thứ tự mong muốn trong toàn bộ request pipeline. Những điều đó cần test thông qua MockMvc hoặc context test.

## 8. Khi code sử dụng RequestContextHolder

Một số code Spring không nhận request qua tham số mà lấy thông tin từ `RequestContextHolder`. Trong trường hợp này, tạo `MockHttpServletRequest` thôi chưa đủ: test phải gắn request vào thread hiện tại thông qua `ServletRequestAttributes`.

```java
MockHttpServletRequest request = new MockHttpServletRequest("GET", "/profile");
MockHttpServletResponse response = new MockHttpServletResponse();
request.setAttribute("tenantId", "tenant-1");

RequestContextHolder.setRequestAttributes(
        new ServletRequestAttributes(request, response)
);
try {
    // Gọi service/helper lấy request hiện tại từ RequestContextHolder.
} finally {
    RequestContextHolder.resetRequestAttributes();
}
```

Luôn dọn thread-bound request attributes trong `finally`. Nếu không, trạng thái của test có thể rò sang test khác khi test engine tái sử dụng thread. Có thể dùng một helper hoặc extension để gom việc bind/unbind nếu nhiều test cần cùng cơ chế.

Việc bind này chỉ thiết lập request context cho thread test. Nó không chạy servlet filter chain, không tạo request scope bean trừ khi context Spring phù hợp được khởi tạo, và không tự thiết lập Spring Security context.

## 9. Ranh giới với MockMvc và server thật

Ba mock object hữu ích ở mức Servlet API, còn MockMvc cung cấp một tầng kiểm thử cao hơn. MockMvc đưa request qua Spring MVC `DispatcherServlet` trong môi trường kiểm thử và cho phép kiểm tra kết quả xử lý theo luồng MVC.

| Cách kiểm thử | Điều được kiểm tra | Khi nên dùng |
|---|---|---|
| Gọi trực tiếp với `MockHttpServletRequest`/`MockHttpServletResponse` | Logic của servlet, filter, interceptor hoặc helper nhận Servlet API trực tiếp. | Khi muốn cô lập một thành phần và tự kiểm soát request/session/response. |
| MockMvc | Luồng Spring MVC qua DispatcherServlet, mapping, argument resolver, validation, message converter, interceptor và exception handling đã cấu hình. | Khi cần kiểm tra endpoint MVC mà không mở cổng HTTP thật. |
| Server thật qua HTTP | Tích hợp HTTP và servlet container, cổng mạng, cấu hình server, filter/container behavior và các thành phần chạy thật. | Khi cần chứng minh hành vi end-to-end qua server. |

Ví dụ, nếu muốn xác nhận `@GetMapping` được ánh xạ đúng, `@RequestParam` được bind, JSON được serialize hoặc exception handler được áp dụng, nên dùng MockMvc. Gọi trực tiếp một method controller với mock request không kích hoạt các cơ chế MVC đó.

Nếu muốn kiểm tra cookie/session qua nhiều HTTP request thật, hành vi container hoặc cấu hình proxy, cần test qua server. `MockHttpSession` chỉ mô phỏng trạng thái trong bộ nhớ và không tự gửi cookie giữa client với server.

## 10. Những giới hạn và nhầm lẫn thường gặp

### Nghĩ rằng mock request đã chạy qua servlet container

Mock request chỉ là một object được tạo trong JVM. Nó không đi qua Tomcat/Jetty, không trải qua socket, không được container ánh xạ servlet và không tự chạy filter. Muốn kiểm tra các bước đó, cần MockMvc ở tầng Spring MVC hoặc server thật ở tầng HTTP/container.

### Nghĩ rằng response mock đã gửi dữ liệu đến trình duyệt

Body và header được giữ trong object response để test đọc lại. Không có trình duyệt hoặc client nào nhận chúng. Redirect URL cũng chỉ là thông tin được ghi nhận để assertion.

### Nhầm request parameter, request attribute và session attribute

Ba loại dữ liệu có vòng đời khác nhau:

| Loại | Nguồn hoặc phạm vi | Ví dụ |
|---|---|---|
| Parameter | Giá trị client gửi trong query/form | `page=2`, `sku=SKU-1`. |
| Request attribute | Dữ liệu gắn với một request trong quá trình xử lý | Correlation id do filter thêm vào. |
| Session attribute | Dữ liệu gắn với phiên làm việc qua nhiều request | User id hoặc cart id. |

Đặt nhầm dữ liệu vào session thay vì request attribute có thể làm test vượt qua một request nhưng không phản ánh đúng thiết kế ứng dụng.

### Nghĩ rằng session mock tự hết hạn

Đặt `maxInactiveInterval` chỉ thiết lập giá trị metadata. Mock session không mô phỏng đầy đủ việc container quét session hết hạn, lưu trữ phân tán, gia hạn cookie hay xử lý concurrent request.

### Nghĩ rằng principal trên request tương đương Spring Security

Thiết lập user/principal trực tiếp trên mock request có thể giúp kiểm tra một helper đọc thông tin người dùng. Nó không thay thế việc chạy security filter chain, authentication provider, authorization rules hoặc token decoder.

### Dùng mock servlet object cho WebFlux

`MockHttpServletRequest` và `MockHttpServletResponse` mô phỏng Servlet API, phù hợp với Spring MVC/Servlet stack. Spring WebFlux có abstraction request/response riêng. Với WebFlux, ưu tiên `WebTestClient` và các mock server/exchange phù hợp.

### Đặt dữ liệu request không nhất quán

Nếu test kiểm tra URL, mapping hoặc redirect, hãy thiết lập request URI, context path, servlet path và query string phù hợp. Một request có URI chứa context path nhưng context path lại không được đặt đúng có thể khiến assertion không phản ánh request thực tế.

## 11. Cách chọn công cụ theo câu hỏi kiểm thử

- Cần kiểm tra helper đọc header, parameter hoặc request attribute? Tạo `MockHttpServletRequest` và gọi helper trực tiếp.
- Cần kiểm tra code ghi status, cookie hoặc response body? Tạo `MockHttpServletResponse` rồi đọc lại kết quả.
- Cần kiểm tra logic lưu trạng thái theo phiên? Gắn `MockHttpSession` vào request và kiểm tra session attribute.
- Cần kiểm tra filter/interceptor tự thân? Gọi thành phần trực tiếp với mock servlet object và các collaborator cần thiết.
- Cần kiểm tra controller mapping, validation, message conversion hoặc exception handling? Dùng MockMvc.
- Cần kiểm tra server, network, container hoặc trao đổi cookie thực tế? Chạy test qua HTTP server.

Khi dùng ba lớp mock này, hãy thiết lập đúng phần request mà code đọc, chỉ assertion vào phần response/session thuộc hành vi cần xác nhận, và giữ trạng thái test độc lập giữa các lần chạy. Nhờ đó, Spring Test cung cấp một môi trường Servlet API nhẹ để kiểm thử logic web mà không cần dựng toàn bộ ứng dụng.

# HttpServletRequest, HttpServletResponse, Principal và Locale trong chữ ký phương thức Spring MVC

> **Bối cảnh:** Spring Web MVC theo mô hình Servlet, với Java 17+ và Spring Boot 3.x. Bài tập trung vào **controller method arguments**: nhận trực tiếp đối tượng request, đối tượng response, thông tin người dùng đã xác thực và ngôn ngữ/vùng miền hiện hành. Các ví dụ dùng package `jakarta.servlet.*` tương thích Spring Framework 6+; dự án Spring 5 và cũ hơn còn dùng `javax.servlet.*`.

## 1. Vì sao đặt bốn kiểu này vào tham số controller?

Spring MVC cho phép một handler lấy dữ liệu request theo hai mức:

- **Mức khai báo:** `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@CookieValue`, `@RequestBody`… Spring chỉ chuyển đúng dữ liệu mà method cần.
- **Mức ngữ cảnh request/response:** Spring có thể truyền trực tiếp `HttpServletRequest`, `HttpServletResponse`, `Principal` và `Locale` vào **chữ ký phương thức** để method truy cập những khả năng hoặc thông tin rộng hơn.

Ví dụ cú pháp cốt lõi:

```java
@GetMapping("/context")
public String context(
        HttpServletRequest request,
        HttpServletResponse response,
        Principal principal,
        Locale locale) {
    response.setHeader("X-Handler", "context");
    String user = principal == null ? "anonymous" : principal.getName();
    return request.getMethod() + " / " + user
            + " / " + locale.toLanguageTag();
}
```

Đây là **đoạn method minh họa**, cần đặt trong controller và import đúng các kiểu. Spring tự tìm nguồn dữ liệu và cung cấp đối số tương ứng trong lúc gọi handler; **không cần `@RequestParam`, `@Autowired`, hay khởi tạo các đối tượng này bằng `new`**.

| Kiểu tham số | Import Java | Chức năng chính | Giá trị/đối tượng đến từ |
| --- | --- | --- | --- |
| `HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` | Xem method, URI, header, cookie, tham số, thuộc tính và session liên quan đến HTTP request | Servlet container và chuỗi xử lý request |
| `HttpServletResponse` | `jakarta.servlet.http.HttpServletResponse` | Điều khiển status, header, content type, cookie và output của HTTP response | Servlet container |
| `Principal` | `java.security.Principal` | Danh tính người dùng đã được cơ chế xác thực xác nhận | Request principal do container/filter bảo mật cung cấp |
| `Locale` | `java.util.Locale` | Ngôn ngữ/vùng miền được xác định cho request | `LocaleResolver`/`LocaleContextResolver` của Spring MVC |

**Phân biệt:** `HttpServletRequest` và `HttpServletResponse` là hai đối tượng mutable liên quan đến HTTP I/O; `Principal` và `Locale` là dữ liệu ngữ cảnh do hạ tầng xác định. Sử dụng các tham số này trong controller đồng bộ thông thường; không giữ request/response để tái sử dụng giữa nhiều request.

## 2. `HttpServletRequest`: đọc ngữ cảnh HTTP hiện tại

`HttpServletRequest` kế thừa `ServletRequest`, cung cấp API mức thấp hơn so với các annotation ánh xạ dữ liệu. Một số method phổ biến:

| Method | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `getMethod()` | HTTP method | `GET`, `POST` |
| `getRequestURI()` | Đường dẫn URI theo servlet container, thường bao gồm context path, không gồm query string | `/shop/api/orders/42` |
| `getContextPath()` | Context path của ứng dụng | `/shop` hoặc chuỗi rỗng |
| `getQueryString()` | Phần sau dấu `?`, hoặc `null` | `sort=asc&page=2` |
| `getHeader("X-Request-Id")` | Đọc header, hoặc `null` nếu vắng | `abc-123` |
| `getParameter("page")` | Một tham số request, thường từ query/form data | `2` |
| `getCookies()` | Cookie client gửi, có thể `null` | `Cookie[]` |
| `getAttribute("key")` | Thuộc tính do filter/interceptor/servlet đặt cho request | `Object` hoặc `null` |
| `getSession(false)` | Session hiện có nếu có, **không tự tạo session mới** | `HttpSession` hoặc `null` |
| `getUserPrincipal()` | Principal theo hợp đồng Servlet | `Principal` hoặc `null` |
| `getRemoteAddr()` | Địa chỉ peer kết nối đến container | Có thể là proxy, không nhất thiết IP máy người dùng |

Ví dụ đọc header và query:

```java
@GetMapping("/inspect")
public String inspect(HttpServletRequest request) {
    String requestId = request.getHeader("X-Request-Id");
    String page = request.getParameter("page");

    return "method=" + request.getMethod()
            + ", uri=" + request.getRequestURI()
            + ", page=" + page
            + ", requestId=" + requestId;
}
```

Với `GET /inspect?page=2` và header `X-Request-Id: abc-123`, body là `method=GET, uri=/inspect, page=2, requestId=abc-123` (nếu ứng dụng chạy tại context path rỗng).

### 2.1. Khi nào dùng `HttpServletRequest`, khi nào dùng annotation?

Nếu chỉ cần một giá trị, nên khai báo hẹp:

```java
@GetMapping("/products")
public String list(
        @RequestParam(defaultValue = "1") int page,
        @RequestHeader(name = "X-Request-Id", required = false)
        String requestId) {
    return "page=" + page + ", requestId=" + requestId;
}
```

Cách khai báo trên tự chuyển `page` sang `int` và thể hiện yêu cầu đầu vào rõ ràng. `HttpServletRequest` thích hợp khi cần nhiều đặc tính servlet, thông tin request chưa được annotation mô tả thuận tiện, request attribute do filter cấp, hoặc tích hợp API Servlet.

Lưu ý về luồng dữ liệu: `getInputStream()` và `getReader()` đọc **body thô**. Đừng đọc body bằng `HttpServletRequest` rồi giả định `@RequestBody` vẫn đọc lại được; stream thường chỉ đọc một lần trừ khi có wrapper thích hợp. Tương tự, `getSession()` có thể tạo session mới, còn `getSession(false)` thì không. Đừng lưu `HttpServletRequest` vào singleton field hay giữ để dùng sau vòng đời xử lý request.

### 2.2. Header, địa chỉ client và độ tin cậy

Dữ liệu header, query, cookie và đường dẫn đều do client hoặc proxy có thể tác động. Chẳng hạn, `X-Forwarded-For` là header **có thể giả mạo** nếu cấu hình reverse proxy không xác thực và chuẩn hóa đúng; `getRemoteAddr()` có thể trả IP của proxy. Không dùng một trong hai làm căn cứ duy nhất cho quyền truy cập. Kiểm tra/giới hạn kích thước input, không đưa nội dung header tùy ý vào HTML, log nhạy cảm hay tên file.

## 3. `HttpServletResponse`: điều khiển phản hồi

Spring thường tự tạo HTTP response qua `@ResponseBody`, `@RestController`, `ResponseEntity` hoặc view rendering. Khi controller nhận `HttpServletResponse`, nó có thể thao tác trực tiếp:

```java
@GetMapping("/custom")
public void custom(HttpServletResponse response) throws IOException {
    response.setStatus(HttpServletResponse.SC_ACCEPTED); // 202
    response.setContentType("text/plain;charset=UTF-8");
    response.setHeader("Cache-Control", "no-store");
    response.getWriter().write("accepted\n");
}
```

Ví dụ này là **một handler trả về `void`**: method tự ghi body. Khi HTTP response chưa bị middleware thay đổi, response dự kiến có status 202, `Content-Type: text/plain;charset=UTF-8`, `Cache-Control: no-store` và body `accepted` kèm newline. Import `java.io.IOException` và `jakarta.servlet.http.HttpServletResponse`.

Nhóm thao tác thường gặp:

| API | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `setStatus(201)` | Chọn HTTP status | Chỉ đặt mã; không tự viết body |
| `setHeader("X-Test", "1")` | Đặt/thay giá trị header | `addHeader` thêm một giá trị cho cùng tên |
| `setContentType("application/json")` | Loại nội dung phản hồi | Đặt charset trước khi lấy writer nếu cần |
| `setCharacterEncoding("UTF-8")` | Charset cho phần văn bản | Nên gọi trước `getWriter()` |
| `addCookie(cookie)` | Gửi `Set-Cookie` | Chọn `HttpOnly`, `Secure`, `SameSite` phù hợp ứng dụng |
| `getWriter()` | Ghi nội dung ký tự | Dùng cho văn bản, JSON tự ghi phải đúng format/escaping |
| `getOutputStream()` | Ghi byte, ví dụ file | Không dùng lẫn với `getWriter()` trên cùng response |
| `sendError(404)` | Gửi lỗi theo cơ chế container | Có thể kích hoạt cơ chế error handling |
| `sendRedirect("/login")` | Phản hồi chuyển hướng | Cẩn thận với URL do client cung cấp |
| `isCommitted()` | Kiểm tra response đã commit chưa | Sau commit thường không thể đổi status/header |

**Thứ tự rất quan trọng:** đặt status, content type, charset và header **trước** khi ghi body hay flush buffer. Khi response đã committed, thay đổi header/status có thể không có hiệu lực. Không vừa trực tiếp gọi `response.getWriter().write(...)` vừa trả về một body để Spring chuyển qua `HttpMessageConverter` trong cùng một handler; như vậy dễ gây ghi đúp, xung đột converter hoặc content type.

### 3.1. Khi nào nên dùng `ResponseEntity`?

Với REST API thông thường, dùng `ResponseEntity` sẽ gọn hơn và dễ kiểm tra hơn:

```java
@GetMapping("/created")
public ResponseEntity<String> created() {
    return ResponseEntity.status(201)
            .header("X-Source", "mvc")
            .contentType(MediaType.TEXT_PLAIN)
            .body("created");
}
```

Ví dụ trên dùng import `org.springframework.http.ResponseEntity` và `org.springframework.http.MediaType`; trả status 201, header `X-Source: mvc`, text body `created`. Khi **không thực sự cần Servlet API**, đây là lựa chọn thường hợp lý để phản hồi status/header/body. `HttpServletResponse` vẫn có giá trị cho streaming, cookie, tích hợp thư viện servlet hoặc xử lý ở mức HTTP thấp.

## 4. `Principal`: nhận danh tính đã xác thực

`java.security.Principal` là interface đơn giản với `String getName()`. Spring MVC có thể giải quyết đối số kiểu này theo request principal (từ `HttpServletRequest#getUserPrincipal()`). Principal phản ánh danh tính đã được tầng xác thực cung cấp; nó **không tự kích hoạt đăng nhập**, không tự kiểm tra mật khẩu và không phải bằng chứng rằng người dùng được phép truy cập mọi tài nguyên.

```java
@GetMapping("/me")
public String me(Principal principal) {
    return principal == null
            ? "No authenticated principal"
            : "Hello, " + principal.getName();
}
```

Ở request **không có principal đã xác thực**, đối số có thể là `null`; method trên xử lý an toàn. Khi container hoặc Spring Security cung cấp request principal, `principal.getName()` lấy tên của danh tính đó. Đừng mặc định toàn bộ request luôn có Principal, nhất là endpoint công khai.

### 4.1. `Principal` so với Spring Security `Authentication` / `@AuthenticationPrincipal`

- `Principal` là interface Java chuẩn, chỉ cam kết `getName()`.
- Với Spring Security, `Authentication` triển khai `Principal` và có thêm quyền hạn/credentials/details/trạng thái xác thực. Loại đối tượng cụ thể được gắn vào request phụ thuộc cách tích hợp bảo mật.
- `@AuthenticationPrincipal` là annotation riêng của Spring Security, lấy **đối tượng `Authentication.getPrincipal()`**, thường là `UserDetails` hoặc principal tùy biến; khác với việc khai báo một đối số `Principal` thuần túy.

Ví dụ minh họa cho **ứng dụng đã cài và cấu hình Spring Security**:

```java
// Ví dụ method riêng, chỉ dùng nếu tích hợp Spring Security.
@GetMapping("/username")
public String username(@AuthenticationPrincipal UserDetails currentUser) {
    return currentUser == null ? "anonymous" : currentUser.getUsername();
}
```

Cần import `org.springframework.security.core.annotation.AuthenticationPrincipal` và `org.springframework.security.core.userdetails.UserDetails`. Ví dụ này chỉ đúng khi principal thực sự là một `UserDetails`; với JWT/OAuth2/custom principal kiểu khác, cần khai báo kiểu tương ứng. Không giả định `Principal`, `Authentication` và `UserDetails` luôn cùng một object.

**Bảo mật:** tên người dùng trong Principal chỉ là nhận diện. Kiểm tra quyền truy cập bằng chính sách bảo mật (request authorization/method security, ownership checks), không bằng so sánh chuỗi lấy từ header `X-User` hay query parameter do người gọi tự nhập.

## 5. `Locale`: ngôn ngữ và vùng miền của request

`java.util.Locale` mô tả quy ước **ngôn ngữ, quốc gia/vùng** cho request, chẳng hạn `vi-VN`, `en-US` hoặc `fr-FR`. Spring MVC suy ra Locale bằng `LocaleResolver` hoặc `LocaleContextResolver` được cấu hình. Resolver mặc định thường dựa trên header HTTP `Accept-Language`; nhưng ứng dụng có thể cấu hình cookie, session hay resolver tùy biến nên kết quả **không bắt buộc trùng tuyệt đối với header**.

```java
@GetMapping("/language")
public String language(Locale locale) {
    return "locale=" + locale.toLanguageTag();
}
```

Với một cấu hình dựa vào `Accept-Language` và header `Accept-Language: vi-VN,vi;q=0.9`, body thường là `locale=vi-VN`.

Khác biệt quan trọng:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `Locale` | `vi-VN` | Ngôn ngữ/vùng miền trình bày số, ngày tháng, văn bản |
| `TimeZone` / `ZoneId` | `Asia/Ho_Chi_Minh` | Quy tắc múi giờ, giờ mùa hè và tính thời điểm địa phương |
| `Accept-Language` | `vi-VN,vi;q=0.9,en;q=0.7` | Nguyện vọng ngôn ngữ do client gửi, không phải bằng chứng địa lý |

**Locale không phải TimeZone.** Không suy múi giờ hay vị trí thật chỉ từ `vi-VN`. Với văn bản đa ngôn ngữ, dùng `MessageSource` và các bundle thông điệp; với số/ngày, dùng API định dạng phù hợp và locale đã xác định. Với timestamp, dùng `ZoneId` độc lập được xác định bởi chính sách ứng dụng hoặc lựa chọn người dùng.

Nếu dùng `AcceptHeaderLocaleResolver`, không nên kỳ vọng đổi locale thông qua `LocaleChangeInterceptor` là đủ: resolver đọc HTTP header và thường không hỗ trợ `setLocale` để thay đổi locale phía server. Muốn đổi qua cookie/session, cấu hình resolver có khả năng lưu lựa chọn locale một cách phù hợp.

## 6. Ví dụ đầy đủ có thể chạy: dùng cả bốn tham số

Tạo dự án Spring Boot **3.x**, Java **17+**, có dependency **Spring Web** bằng [Spring Initializr](https://start.spring.io/). Ví dụ này **không cài Spring Security**, vì mục tiêu là minh họa request công khai với Principal vắng mặt. Thay nội dung `src/main/java/com/example/demo/DemoApplication.java` bằng:

```java
package com.example.demo;

import java.io.IOException;
import java.security.Principal;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/context")
class ContextController {

    @GetMapping("/inspect")
    public Map<String, String> inspect(
            HttpServletRequest request,
            Principal principal,
            Locale locale) {

        Map<String, String> result = new LinkedHashMap<>();
        result.put("method", request.getMethod());
        result.put("uri", request.getRequestURI());
        result.put("locale", locale.toLanguageTag());
        result.put("user", principal == null
                ? "anonymous"
                : principal.getName());
        return result;
    }

    @GetMapping("/manual")
    public void manual(
            HttpServletRequest request,
            HttpServletResponse response,
            Principal principal,
            Locale locale) throws IOException {

        String user = principal == null
                ? "anonymous"
                : principal.getName();

        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("text/plain;charset=UTF-8");
        response.setHeader("Cache-Control", "no-store");

        response.getWriter().write(
                "method=" + request.getMethod() + "\n"
                + "locale=" + locale.toLanguageTag() + "\n"
                + "user=" + user + "\n");
    }

    @GetMapping("/entity")
    public ResponseEntity<String> entity(Locale locale) {
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .header("X-Language", locale.getLanguage())
                .body("locale=" + locale.toLanguageTag());
    }
}
```

Giải thích vai trò các endpoint:

- `GET /api/context/inspect` nhận request + principal + locale và **để Spring tự serialize `Map` thành JSON**.
- `GET /api/context/manual` có đủ **cả bốn kiểu tham số**; handler tự đặt status/header và ghi text trực tiếp qua `HttpServletResponse`, nên method trả `void`.
- `GET /api/context/entity` minh họa đối chứng: dùng `ResponseEntity` để mô tả response mà không cần cầm `HttpServletResponse`.

Chạy từ thư mục project:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

Dùng cURL để kiểm tra. Dấu `-i` hiển thị cả HTTP status/header. Ở lệnh đầu, ký tự `-s` chỉ tắt progress bar:

```bash
curl -s -H 'Accept-Language: vi-VN,vi;q=0.9' \
  http://localhost:8080/api/context/inspect
```

Với Spring Web không có security và resolver ngôn ngữ dựa trên request header, JSON body dự kiến (các trường theo thứ tự chèn):

```json
{"method":"GET","uri":"/api/context/inspect","locale":"vi-VN","user":"anonymous"}
```

Tiếp theo:

```bash
curl -i -H 'Accept-Language: vi-VN' \
  http://localhost:8080/api/context/manual
```

Phản hồi chứa status HTTP `200 OK`, header `Cache-Control: no-store`, `Content-Type: text/plain;charset=UTF-8` và **body chính xác**:

```text
method=GET
locale=vi-VN
user=anonymous
```

Có ký tự newline cuối body do `"\n"`. Các header khác (ví dụ `Date`, `Connection`) phụ thuộc container. Lệnh trên dùng cú pháp nối dòng kiểu POSIX; trên PowerShell có thể viết toàn bộ cURL trên một dòng với `curl.exe -i -H "Accept-Language: vi-VN" "http://localhost:8080/api/context/manual"`.

Cuối cùng:

```bash
curl -i -H 'Accept-Language: en-US' \
  http://localhost:8080/api/context/entity
```

Body dự kiến là `locale=en-US`, header `X-Language: en`. Nếu thêm Spring Security chưa tùy biến, endpoint có thể yêu cầu đăng nhập và kết quả `Principal` cũng phụ thuộc cấu hình security; khi đó không coi ví dụ anonymous là kết quả bắt buộc.

## 7. Spring giải quyết đối số theo cơ chế nào?

1. Servlet container tạo `HttpServletRequest`/`HttpServletResponse` cho HTTP request; filter chain có thể bọc, thêm thuộc tính hoặc xác thực request.
2. `DispatcherServlet` gọi hệ thống handler mapping để chọn controller method phù hợp.
3. `RequestMappingHandlerAdapter` phối hợp `HandlerMethodArgumentResolver` để giải quyết các tham số dựa vào **kiểu hoặc annotation**.
4. Resolver cho Servlet request/response cung cấp đối tượng servlet; resolver cho `Principal` lấy danh tính liên kết với request; resolver cho `Locale` lấy locale từ resolver đang có hiệu lực.
5. Method controller được gọi. Nếu trả Java object thông thường từ `@RestController`, Spring có thể dùng message converter để tạo body. Nếu method tự thao tác `HttpServletResponse` và trả `void`, HTTP response được viết trực tiếp.

Điểm đáng nhớ là **Spring inject giá trị theo từng HTTP request tại thời điểm gọi handler**. Không cần đánh dấu `@Autowired` trên từng tham số method. Đối số `Principal` có thể trống khi chưa xác thực; `HttpServletRequest`, `HttpServletResponse` là đối tượng request hiện hành chứ không phải bean dùng chung cho mọi request.

### 7.1. Có cần khai báo bốn tham số theo thứ tự nhất định?

Không. Mỗi đối số được resolver xử lý độc lập dựa trên kiểu/annotation, miễn method signature hợp lệ. Cả hai cách sau đều thể hiện cùng nhu cầu:

```java
public String show(HttpServletRequest request, Locale locale, Principal principal) { /* ... */ }

public String show(Locale locale, Principal principal, HttpServletRequest request) { /* ... */ }
```

**Hai dòng trên chỉ là ví dụ so sánh chữ ký, không phải hai method đầy đủ để chép vào cùng một controller**; vị trí tham số không đổi nguồn cung cấp. Tuy nhiên, hãy giữ thứ tự ổn định, dễ đọc và tránh truyền thừa đối tượng request/response khi chỉ cần một trường dữ liệu.

## 8. Lỗi thường gặp và cách sửa

| Biểu hiện | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `package javax.servlet.http does not exist` trên Spring Boot 3.x | Spring Framework 6 dùng Jakarta namespace | Đổi import thành `jakarta.servlet.http.*` |
| `NullPointerException` tại `principal.getName()` | Endpoint anonymous hoặc thiếu principal | Xử lý `principal == null`; cấu hình xác thực nếu API yêu cầu người dùng |
| `Locale` không đổi theo query `?lang=fr` | Locale resolver mặc định không đọc query đó | Cấu hình resolver/interceptor phù hợp hoặc gửi `Accept-Language` |
| `Accept-Language: vi-VN` nhưng locale khác | App có resolver tùy biến, danh sách locale hỗ trợ hoặc fallback | Kiểm tra `LocaleResolver`, cấu hình supported locales và request thực nhận |
| Trả header/status không như dự kiến | Response đã được commit hoặc do filter/container sửa | Đặt status/header trước lúc ghi/flush, kiểm tra filter |
| `IllegalStateException` khi ghi body | Gọi `getWriter()` và `getOutputStream()` trên một response | Chọn đúng một cách ghi body |
| JSON/text bị lỗi encoding | Đặt charset sau khi đã lấy writer/ghi body | Đặt `Content-Type` và encoding trước `getWriter()` |
| Gửi dữ liệu hai lần hoặc response hỏng | Tự ghi qua response và đồng thời trả body để converter xử lý | Dùng một chiến lược: `void` + viết trực tiếp, hoặc `ResponseEntity`/body converter |
| Client IP không đúng | Ứng dụng ở sau reverse proxy | Dựa vào cấu hình proxy tin cậy, tránh tin header tự khai |
| Controller đọc body nhưng `@RequestBody` trống | Request stream đã bị đọc | Chỉ đọc body một lần hoặc dùng caching wrapper đúng cách |

### 8.1. Tránh nhập nhằng khi kết hợp các cơ chế

- `@RequestHeader("Accept-Language") String raw` trả chuỗi header do client gửi; `Locale locale` trả đối tượng đã được resolver xác định. Hai giá trị không đồng nghĩa.
- `@RequestParam("user") String user` là input client tự cung cấp; `Principal principal` được hình thành qua cơ chế xác thực. Không dùng request parameter thay principal cho quyết định bảo mật.
- `HttpServletRequest#getUserPrincipal()` là lối đọc thủ công tương ứng với cách lấy principal ở API Servlet. Khai báo `Principal` ngay trong signature rõ ý định hơn khi chỉ cần tên người dùng.
- `HttpServletResponse#setStatus(404)` chỉ đổi status; `ResponseEntity.notFound().build()` là cách khai báo response phổ biến trong REST; `sendError(404)` có thể kích hoạt error handling của container. Chọn theo ý định.
- `Locale` dành cho lược đồ hiển thị và quốc tế hóa, không phải cơ chế phân quyền hay định danh người dùng.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Tại sao controller không cần `@Autowired` cho `HttpServletRequest`?

**Đáp án:** Trong Spring MVC, hệ thống `HandlerMethodArgumentResolver` có sẵn khả năng cung cấp request object làm đối số của handler method.

**Câu 2.** Request chưa đăng nhập tới controller có `Principal principal`. Có nên gọi `principal.getName()` ngay không?

**Đáp án:** Không. Principal có thể `null`; kiểm tra trước và bảo vệ route bằng security nếu cần quyền đăng nhập.

**Câu 3.** `Accept-Language: fr-FR` có luôn đảm bảo `locale.toLanguageTag()` trả `fr-FR`?

**Đáp án:** Không. Resolver, danh sách locale hỗ trợ và fallback của ứng dụng quyết định locale; header chỉ là một nguồn đầu vào.

**Câu 4.** Muốn status 201 + header `Location` + JSON body, nên dùng gì trong REST API?

**Đáp án:** Thường chọn `ResponseEntity` để trả status, header và body rõ ràng, ít phải thao tác trực tiếp trên servlet response.

**Câu 5.** Tại sao nên đặt `response.setContentType("text/plain;charset=UTF-8")` trước `getWriter()`?

**Đáp án:** Servlet response cần xác định content type và mã hóa trước khi mở writer/ghi body, tránh charset không như mong muốn hoặc không còn đổi được sau commit.

## 10. Tài liệu chính thức

- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): danh sách đối số hỗ trợ, gồm `ServletRequest`, `ServletResponse`, `Principal` và `Locale`.
- [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): `void`, `ResponseEntity`, cách Spring xử lý kết quả method.
- [Spring Framework — Locale Resolution](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html): `LocaleResolver`, `AcceptHeaderLocaleResolver` và các resolver khác.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): điều khiển status/header/body bằng Spring MVC.
- [Spring Security — Spring MVC Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html): phân biệt `Principal` và `@AuthenticationPrincipal`.
- [Jakarta Servlet — HttpServletRequest / HttpServletResponse](https://jakarta.ee/specifications/servlet/): API HTTP request/response ở mức container.

**Điểm cần ghi nhớ:** `HttpServletRequest` đọc ngữ cảnh request; `HttpServletResponse` cho phép kiểm soát response trực tiếp; `Principal` cho biết danh tính đã được xác thực nếu có; `Locale` biểu thị quy ước ngôn ngữ/vùng miền của request. Spring MVC tự resolve bốn tham số trong handler method, còn kiểm soát quyền truy cập và lựa chọn ngôn ngữ phụ thuộc vào cấu hình tương ứng.

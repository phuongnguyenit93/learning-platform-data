# @RequestHeader và @CookieValue trong Spring MVC

## Mục tiêu bài học

Sau bài này, bạn có thể đọc và chuyển đổi HTTP request header bằng `@RequestHeader`; đọc cookie từ request bằng `@CookieValue`; xử lý trường hợp thiếu giá trị, giá trị mặc định và lỗi chuyển kiểu; chọn đúng cách lấy một hoặc nhiều header; viết và kiểm thử controller Spring MVC mà không nhầm header/cookie với query parameter hay request body.

Phạm vi: **Spring MVC (Servlet stack)**, Java 17+, ví dụ dùng Spring Boot 3.x và package `jakarta.servlet`. Trong Spring WebFlux cũng có hai annotation này, nhưng cơ chế xử lý request thuộc reactive stack và không phải trọng tâm ở đây.

## 1. Header và cookie xuất hiện ở đâu trong HTTP?

Một request có thể mang metadata trong **header**, cookie trong header đặc biệt `Cookie`, dữ liệu URL trong query string và dữ liệu gửi lên trong body:

~~~http
GET /api/inspect?source=mobile HTTP/1.1
Host: localhost:8080
X-Request-Id: req-42
X-Retry-Count: 3
Accept-Language: vi-VN
Cookie: theme=dark; visitCount=7
~~~

- `@RequestHeader("X-Request-Id")` lấy header `X-Request-Id` (giá trị `req-42`).
- `@CookieValue("theme")` lấy **cookie có tên `theme`** (giá trị `dark`) từ request.
- `@RequestParam("source")` sẽ lấy query parameter `source=mobile`; đó là cơ chế khác.
- `@RequestBody` đọc body, không dùng để đọc header/cookie.

**Điểm phân biệt quan trọng:** `Cookie` là header HTTP chứa danh sách cookie, còn `@CookieValue` phân tích để lấy **cookie theo tên**. Header `Set-Cookie` thuộc **response** khi server yêu cầu trình duyệt lưu cookie; không phải cách dùng `@CookieValue` để đọc cookie từ request.

| Tiêu chí | `@RequestHeader` | `@CookieValue` |
| --- | --- | --- |
| Đọc từ | Header của HTTP request | Cookie của HTTP request |
| Chọn bằng | Tên header, ví dụ `X-Request-Id` | Tên cookie, ví dụ `theme` |
| Kiểu thường gặp | `String`, `Integer`, `List<String>`, `HttpHeaders` | `String`, `Integer`, `Cookie` |
| Bắt buộc theo mặc định | Có (`required=true`) | Có (`required=true`) |
| Nếu thiếu và không có default | Thường phản hồi HTTP 400 | Thường phản hồi HTTP 400 |
| Nếu `defaultValue` được đặt | Giá trị fallback; không còn bắt buộc | Giá trị fallback; không còn bắt buộc |

Theo giao thức HTTP, **tên header không phân biệt hoa/thường**; tên cookie thì cần dùng đúng tên đã đặt (tránh tự ý đổi chữ hoa/thường). Cả header và cookie đều là dữ liệu do client gửi, **không tự động đáng tin cậy**.

## 2. Cú pháp và cơ chế binding

Hai annotation được khai báo tại **tham số của handler method** (`@GetMapping`, `@PostMapping`…):

~~~java
@GetMapping("/example")
public String example(
        @RequestHeader("X-Request-Id") String requestId,
        @CookieValue("theme") String theme) {
    return requestId + ":" + theme;
}
~~~

Spring MVC tìm handler theo URL và HTTP method, sau đó các argument resolver đọc header hoặc cookie tương ứng và bind vào tham số. Nếu tham số là `Integer`, `Long`, enum hoặc kiểu khác được hệ thống conversion hỗ trợ, Spring áp dụng **type conversion**. Không phải JSON deserialization: việc đọc hai annotation này không cần `HttpMessageConverter` hoặc `@RequestBody`.

Các thuộc tính chính áp dụng cho **cả hai**:

~~~java
@RequestHeader(name = "X-Request-Id", required = false)
@RequestHeader(value = "X-Request-Id", defaultValue = "unknown")
@CookieValue(name = "theme", required = false)
@CookieValue(value = "theme", defaultValue = "light")
~~~

- `name` và `value` là hai cách đặt cùng một tên; cú pháp rút gọn `@RequestHeader("X-Request-Id")` tương đương `value = "X-Request-Id"`.
- `required = true` là mặc định: nếu request thiếu dữ liệu bắt buộc, Spring MVC phát sinh lỗi binding và thông thường trả **400 Bad Request**.
- `required = false` cho phép thiếu. Với tham số tham chiếu như `String`, `Integer` hoặc `Cookie`, kết quả thường là `null`; có thể dùng `Optional<T>` khi phù hợp.
- `defaultValue = "light"` cung cấp fallback nếu thiếu **hoặc giá trị rỗng**, và ngầm làm `required = false`. Chuỗi mặc định cũng phải chuyển được sang kiểu đích khi có chuyển kiểu.
- Đối với giá trị tùy chọn, tránh kiểu nguyên thủy như `int` nếu có thể trả `null`; ưu tiên `Integer`, `Optional<Integer>` hoặc đặt `defaultValue`.

## 3. Ví dụ Spring Boot MVC chạy được

Tạo dự án bằng Spring Initializr với **Java 17+**, **Maven**, Spring Boot **3.x**, dependency **Spring Web** (kéo theo `spring-boot-starter-web`). Dùng hai file dưới đây; nếu muốn chạy phần kiểm thử, thêm dependency **Spring Boot Starter Test**.

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/demo/HeaderCookieController.java`**

~~~java
package com.example.demo;

import jakarta.servlet.http.Cookie;
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class HeaderCookieController {

    @GetMapping("/inspect")
    public RequestSnapshot inspect(
            @RequestHeader(name = "X-Request-Id", defaultValue = "anonymous")
            String requestId,
            @RequestHeader(name = "X-Retry-Count", required = false)
            Integer retryCount,
            @CookieValue(name = "theme", defaultValue = "light")
            String theme,
            @CookieValue(name = "visitCount", required = false)
            Integer visitCount) {

        return new RequestSnapshot(requestId, retryCount, theme, visitCount);
    }

    // Một tham số có thể bắt buộc: request thiếu header hoặc cookie sẽ bị từ chối.
    @GetMapping("/mandatory")
    public String mandatory(
            @RequestHeader("X-Request-Id") String requestId,
            @CookieValue("consent") String consent) {
        return requestId + ":" + consent;
    }

    // Đọc cả bộ header; getFirst chỉ trả giá trị đầu tiên của một tên.
    @GetMapping("/trace")
    public String trace(@RequestHeader HttpHeaders headers) {
        String traceId = headers.getFirst("X-Trace-Id");
        return traceId == null ? "none" : traceId;
    }

    // Spring có thể chuyển header dạng danh sách phân tách bởi dấu phẩy.
    @GetMapping("/accept")
    public List<String> accept(
            @RequestHeader(name = "Accept", required = false)
            List<String> acceptedTypes) {
        return acceptedTypes == null ? List.of() : acceptedTypes;
    }

    // Khi cần thuộc tính đối tượng Cookie của Servlet, có thể nhận Cookie.
    @GetMapping("/raw-cookie")
    public String rawCookie(
            @CookieValue(name = "theme", required = false) Cookie cookie) {
        return cookie == null ? "missing" : cookie.getName() + "=" + cookie.getValue();
    }

    public record RequestSnapshot(
            String requestId,
            Integer retryCount,
            String theme,
            Integer visitCount) {}
}
~~~

**Cách hoạt động:** `/inspect` trả một record được Spring MVC tuần tự hóa thành JSON. `X-Retry-Count` và `visitCount` được chuyển từ chuỗi HTTP sang `Integer`; hai tham số tùy chọn có thể là `null`. `/mandatory` minh họa yêu cầu bắt buộc; `/trace` dùng `HttpHeaders`; `/raw-cookie` dùng `jakarta.servlet.http.Cookie`.

Chạy trong thư mục dự án:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows có thể dùng `mvnw.cmd spring-boot:run`; nếu không có Maven Wrapper, dùng `mvn spring-boot:run` khi đã cài Maven.

Gửi một request có cả header và cookie:

~~~bash
curl -s -H "X-Request-Id: req-42" -H "X-Retry-Count: 3" --cookie "theme=dark; visitCount=7" http://localhost:8080/api/inspect
~~~

**Nội dung JSON kỳ vọng** (thứ tự các property JSON không quan trọng):

~~~json
{"requestId":"req-42","retryCount":3,"theme":"dark","visitCount":7}
~~~

Thử bỏ tất cả header/cookie do ví dụ tự định nghĩa:

~~~bash
curl -s http://localhost:8080/api/inspect
~~~

Với cấu hình JSON mặc định của Spring Boot 3, kết quả tương đương:

~~~json
{"requestId":"anonymous","retryCount":null,"theme":"light","visitCount":null}
~~~

Hai tình huống khác để quan sát:

~~~bash
curl -i http://localhost:8080/api/mandatory
curl -i -H "X-Request-Id: req-42" -H "X-Retry-Count: abc" http://localhost:8080/api/inspect
~~~

Request thứ nhất thiếu thông tin bắt buộc; request thứ hai không thể chuyển `abc` thành `Integer`. Mặc định Spring MVC thường trả **HTTP 400** cho cả hai. Nội dung JSON lỗi thay đổi theo cấu hình ứng dụng, vì vậy **không nên phụ thuộc vào một body lỗi cố định**.

> Nếu dùng PowerShell trên Windows, gọi `curl.exe` để dùng cú pháp CLI `curl` nhất quán; trong một số môi trường `curl` là alias của PowerShell.

## 4. Đọc một header, nhiều giá trị và toàn bộ header

### Một tên header

~~~java
@GetMapping("/language")
public String language(
        @RequestHeader(name = "Accept-Language", required = false)
        String acceptLanguage) {
    return acceptLanguage == null ? "not specified" : acceptLanguage;
}
~~~

Ví dụ `Accept-Language: vi-VN, en;q=0.8` được đọc dưới dạng chuỗi. Nếu mục tiêu là chọn locale theo cơ chế đàm phán ngôn ngữ của Spring, `Locale` hoặc `LocaleResolver` thường phù hợp hơn việc tự tách chuỗi `Accept-Language`.

### Một header có nhiều giá trị

Header có thể có nhiều dòng cùng tên hoặc biểu diễn một danh sách bằng dấu phẩy. Spring hỗ trợ `String[]`, `List<String>` cho trường hợp có thể chuyển đổi; ví dụ endpoint `/api/accept` trên có thể nhận:

~~~bash
curl -s -H "Accept: application/json, text/plain" http://localhost:8080/api/accept
~~~

Kết quả danh sách minh họa:

~~~json
["application/json","text/plain"]
~~~

Tuy nhiên **không phải mọi header HTTP đều được phép ghép hoặc tách đơn giản bằng dấu phẩy**; cú pháp từng header có thể có dấu nháy, tham số hoặc quy tắc đặc biệt. Với dữ liệu cần phân tích chính xác, dùng API chuyên biệt như `HttpHeaders.getAccept()` thay vì tự split chuỗi.

### Lấy tất cả header

~~~java
@GetMapping("/header-count")
public int headerCount(@RequestHeader HttpHeaders headers) {
    return headers.size();
}
~~~

Với tham số `@RequestHeader` không có tên, Spring có thể bind cả bộ header vào `HttpHeaders`, `Map<String, String>` hoặc `MultiValueMap<String, String>`:

- `Map<String, String>`: biểu diễn một giá trị cho mỗi tên; có thể mất thông tin nếu header có nhiều giá trị.
- `MultiValueMap<String, String>`: giữ danh sách giá trị cho mỗi tên.
- `HttpHeaders`: API HTTP chuyên dụng, có phương thức như `getFirst`, `getAccept`, `getContentType`; thường là lựa chọn rõ ràng nhất khi cần nhiều header.

Đọc mọi header không có nghĩa là nên **trả hoặc log nguyên bộ**: các header như `Authorization` hay `Cookie` có thể chứa bí mật.

## 5. Đọc cookie và hiểu những gì server thực sự nhận

Ví dụ trình duyệt gửi:

~~~http
Cookie: theme=dark; visitCount=7
~~~

Thì `@CookieValue("theme") String theme` lấy `dark`, `@CookieValue("visitCount") Integer visits` lấy số `7`. Trong Spring MVC dùng Servlet, bạn cũng có thể khai báo tham số kiểu `jakarta.servlet.http.Cookie` để đọc `getName()`, `getValue()`, `getPath()`… Tuy nhiên chỉ các thuộc tính thật sự có sẵn trong **cookie request** mới đáng tin để quan sát; các thuộc tính cấu hình lúc server gửi `Set-Cookie` (như `HttpOnly`, `Secure`, `SameSite`) **không được gửi lại trong header `Cookie`** của request.

Server thường cấp cookie qua response, ví dụ:

~~~http
HTTP/1.1 200 OK
Set-Cookie: theme=dark; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Ở request sau đủ điều kiện, client chỉ gửi cặp tên–giá trị như `Cookie: theme=dark`. `Secure` yêu cầu gửi cookie qua kết nối an toàn theo quy tắc trình duyệt; `HttpOnly` hạn chế truy cập từ JavaScript; `SameSite` ảnh hưởng việc đính kèm cookie trong ngữ cảnh cross-site. Những thuộc tính này cần thiết kế ở **lúc thiết lập cookie**, không cấu hình bằng `@CookieValue`.

Cookie có thể vắng mặt do chưa được set, hết hạn, không khớp `Domain`/`Path`, chính sách `SameSite`, hoặc yêu cầu credentials của trình duyệt. Không kết luận “Spring đọc lỗi” trước khi kiểm tra tab Network của trình duyệt xem request có thật sự chứa header `Cookie` hay không.

## 6. Quyết định `required`, `defaultValue` và xử lý lỗi

| Tình huống | Khai báo phù hợp | Kết quả |
| --- | --- | --- |
| Header bắt buộc | `@RequestHeader("X-Request-Id") String id` | Thiếu → thường 400 |
| Header tùy chọn | `@RequestHeader(name="X-Retry-Count", required=false) Integer count` | Thiếu → `null` |
| Header có fallback | `@RequestHeader(name="X-Source", defaultValue="web") String source` | Thiếu/rỗng → `web` |
| Cookie bắt buộc | `@CookieValue("consent") String consent` | Thiếu → thường 400 |
| Cookie tùy chọn | `@CookieValue(name="theme", required=false) String theme` | Thiếu → `null` |
| Cookie có fallback | `@CookieValue(name="theme", defaultValue="light") String theme` | Thiếu/rỗng → `light` |
| Giá trị không chuyển kiểu được | `@CookieValue("visitCount") Integer n` nhận `abc` | Thường 400 do lỗi conversion |

Các ngoại lệ thường gặp ở Spring MVC: `MissingRequestHeaderException` và `MissingRequestCookieException` khi thiếu dữ liệu bắt buộc; lỗi chuyển kiểu như `MethodArgumentTypeMismatchException` khi chuỗi không hợp lệ. Bạn có thể dùng `@ControllerAdvice`/`@ExceptionHandler` nếu API cần cấu trúc lỗi tùy chỉnh. **Đừng biến mặc định 400 thành 200 chỉ để che lỗi client.**

Nếu muốn giá trị số mặc định, cấu hình trực tiếp `defaultValue = "0"`; Spring sẽ chuyển chuỗi `"0"` sang `Integer`. Không dùng `required=false int count` vì `int` không nhận `null`.

## 7. Kiểm thử bằng MockMvc

Với dependency `spring-boot-starter-test` trong dự án Spring Boot 3.x, thêm file **`src/test/java/com/example/demo/HeaderCookieControllerTest.java`**:

~~~java
package com.example.demo;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(HeaderCookieController.class)
class HeaderCookieControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readsHeaderAndCookies() throws Exception {
        mockMvc.perform(get("/api/inspect")
                        .header("X-Request-Id", "req-42")
                        .header("X-Retry-Count", "3")
                        .cookie(new Cookie("theme", "dark"),
                                new Cookie("visitCount", "7")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requestId").value("req-42"))
                .andExpect(jsonPath("$.retryCount").value(3))
                .andExpect(jsonPath("$.theme").value("dark"))
                .andExpect(jsonPath("$.visitCount").value(7));
    }

    @Test
    void appliesDefaultsWhenMissing() throws Exception {
        mockMvc.perform(get("/api/inspect"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requestId").value("anonymous"))
                .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void rejectsMissingRequiredValues() throws Exception {
        mockMvc.perform(get("/api/mandatory"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidNumber() throws Exception {
        mockMvc.perform(get("/api/inspect")
                        .header("X-Retry-Count", "abc"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy bằng:

~~~bash
./mvnw test
~~~

`MockMvc` xây dựng request giả lập đủ header/cookie và kiểm tra HTTP status, giá trị JSON; không cần mở server thật. Kiểm thử cả trường hợp có giá trị, thiếu giá trị tùy chọn, thiếu giá trị bắt buộc và lỗi chuyển kiểu để tránh nhầm lẫn giữa **fallback** và **bad request**.

## 8. Bảo mật và lỗi triển khai thường gặp

1. **Không tin header/cookie như bằng chứng danh tính.** Client có thể tự gửi `X-User-Id` hoặc chỉnh cookie `role=admin`. Để xác thực/phân quyền, dùng Spring Security và `Principal`/`Authentication`; session ID hoặc token phải được xác minh tại server.
2. **Không log dữ liệu nhạy cảm.** `Authorization`, cookie phiên, access token và thông tin nhận diện không nên được in vào log hay trả về trong response ví dụ thực tế. Cookie giá trị nhạy cảm nên cân nhắc `HttpOnly`, `Secure`, `SameSite` và thời hạn phù hợp; `HttpOnly` không tự loại bỏ CSRF.
3. **Phân biệt cookie gửi đến và cookie đặt đi.** `@CookieValue` đọc request. Muốn set cookie, sử dụng response `Set-Cookie` (ví dụ `ResponseCookie`/HTTP response header), kiểm soát `Path`, `Domain`, `Max-Age`, `Secure`, `HttpOnly`, `SameSite`.
4. **Không giả định header tùy chọn luôn có.** Việc dereference `null` khi dùng `required=false` có thể gây `NullPointerException`. Chọn wrapper/`Optional`/default hợp lý.
5. **Không tự tách mọi header bằng dấu phẩy.** Header phức tạp cần parser theo chuẩn; khi cần multi-value, dùng `HttpHeaders` hoặc `MultiValueMap` và API chuyên biệt.
6. **Không nhầm thiếu dữ liệu với dữ liệu sai định dạng.** `required=false` xử lý thiếu, không có nghĩa `"abc"` hợp lệ đối với `Integer`. Tùy yêu cầu API, giữ 400 và cung cấp thông báo lỗi rõ ràng.
7. **Không phụ thuộc vào header tự do từ reverse proxy.** Header như `X-Forwarded-For` chỉ nên tin theo cấu hình proxy đáng tin và chính sách của hệ thống; chúng không mặc nhiên là địa chỉ IP thật của người gọi.
8. **Không ép browser gửi cookie khi chính sách chặn.** Cần kiểm tra HTTPS, domain/path, SameSite và credentials với các request từ frontend. Kiểm tra request thực tế trước khi sửa controller.

## 9. Checklist áp dụng nhanh

- Nếu cần **metadata HTTP**, dùng `@RequestHeader`; nếu cần **cookie đã được client gửi**, dùng `@CookieValue`.
- Xác định chính xác tên, kiểu Java đích, có bắt buộc hay không và cần fallback hay không.
- Với nhiều header, chọn `HttpHeaders` hoặc `MultiValueMap`; không làm mất các giá trị lặp.
- Kiểm thử cả dữ liệu hợp lệ, thiếu và không chuyển kiểu được; không dùng header/cookie chưa xác minh để quyết định phân quyền.

## Tham khảo chính thức

- [Spring Framework — `@RequestHeader`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html)
- [Spring Framework — `@CookieValue`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html)
- [Spring Framework — Controller Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html)

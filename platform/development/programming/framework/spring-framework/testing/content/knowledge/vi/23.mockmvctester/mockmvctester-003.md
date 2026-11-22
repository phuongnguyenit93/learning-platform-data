# Tạo yêu cầu và kiểm tra kết quả bằng fluent assertion

`MockMvcTester` là API kiểm thử Spring MVC theo phong cách AssertJ, được giới thiệu trong Spring Framework 6.2. Nó giúp viết một request và kiểm tra kết quả bằng chuỗi fluent assertion: tạo request, khai báo URI và dữ liệu gửi lên, sau đó xác nhận HTTP status và response body ngay trên cùng biểu thức.

`MockMvcTester` vẫn sử dụng `MockMvc` và `DispatcherServlet` ở bên dưới. Request được xử lý qua Spring MVC trong môi trường mock, không mở cổng HTTP và không khởi động servlet container thật. Điểm thay đổi chính là cách tạo request và diễn đạt assertion trở nên gọn, liền mạch hơn.

## 1. Điều kiện sử dụng MockMvcTester

`MockMvcTester` có từ Spring Framework 6.2 trở lên và cần AssertJ trên test classpath. Trong dự án Spring Boot, `spring-boot-starter-test` thường cung cấp các thư viện kiểm thử cần thiết, bao gồm AssertJ.

Ví dụ dependency Gradle khi dùng Spring Boot:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Nếu quản lý dependency trực tiếp, cần có `spring-test` phiên bản 6.2 trở lên và `assertj-core` tương thích. Hãy để Spring Boot BOM hoặc dependency management của dự án quản lý phiên bản đồng bộ; không nên nâng riêng `spring-test` lên một phiên bản khác với phần Spring Framework còn lại.

Với Spring Boot 3.4 trở lên, khi AssertJ có trên classpath và test dùng cấu hình MockMvc, Boot có thể tự cấu hình bean `MockMvcTester`. Những dự án Spring Boot cũ hơn có thể chưa có auto-configuration này; vẫn có thể tạo `MockMvcTester` thủ công nếu phiên bản Spring Framework thực tế đã là 6.2 trở lên.

## 2. Tạo MockMvcTester từ MockMvc

`MockMvcTester` có thể được tạo từ một `MockMvc` đã cấu hình. Cách này phù hợp khi test đang dùng `WebApplicationContext` và muốn tái sử dụng cấu hình MVC hiện có:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

Nếu chỉ kiểm thử một controller với cấu hình tối thiểu, có thể tạo `MockMvc` bằng `standaloneSetup(...)` rồi bọc nó bằng `MockMvcTester`:

```java
MockMvc mockMvc = MockMvcBuilders
    .standaloneSetup(new GreetingController())
    .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

Chọn `webAppContextSetup` khi muốn dùng các bean và cấu hình MVC đã nạp trong web application context. Chọn `standaloneSetup` khi phạm vi kiểm thử tập trung vào controller và không cần toàn bộ web context.

## 3. Tiêm MockMvcTester trong Spring Boot

Với Spring Boot có hỗ trợ auto-configuration cho `MockMvcTester`, có thể tiêm trực tiếp vào test:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTests {

    @Autowired
    private MockMvcTester mvc;
}
```

`@SpringBootTest` nạp application context của ứng dụng. `@AutoConfigureMockMvc` cấu hình hạ tầng MockMvc; trong các phiên bản Boot có hỗ trợ, bean `MockMvcTester` được tạo dựa trên hạ tầng đó nếu AssertJ có sẵn.

Nếu không có bean `MockMvcTester`, hãy kiểm tra phiên bản Spring Framework, phiên bản Spring Boot và AssertJ trên test classpath. Với Spring Framework 6.2 nhưng chưa có Boot auto-configuration tương ứng, có thể tiêm `MockMvc` rồi gọi `MockMvcTester.create(mockMvc)` trong test setup.

## 4. Tạo request và kiểm tra status bằng fluent assertion

`MockMvcTester` cung cấp request builder cho các HTTP method phổ biến như `get()`, `post()`, `put()`, `patch()`, `delete()`, `options()` và `head()`. Builder cho phép thiết lập URI, path variable, parameter, header, cookie, session, content type và request body.

Giả sử controller trả về lời chào dạng text:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting")
    String greeting(
            @RequestParam(defaultValue = "friend") String name) {
        return "Hello " + name;
    }
}
```

Với `MockMvc` truyền thống, test thường gọi `perform(...)` rồi nối các `andExpect(...)`. Với `MockMvcTester`, request builder có thể được đưa thẳng vào AssertJ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

@Test
void returnsGreetingForRequestedName() {
    assertThat(mvc.get().uri("/greeting").param("name", "Mai"))
        .hasStatusOk()
        .bodyText()
        .isEqualTo("Hello Mai");
}
```

Biểu thức trên thực hiện request và kiểm tra kết quả theo thứ tự:

1. `mvc.get()` tạo request GET.
2. `uri("/greeting")` chọn endpoint.
3. `param("name", "Mai")` gửi request parameter mà controller nhận qua `@RequestParam`.
4. `hasStatusOk()` xác nhận HTTP status là 200.
5. `bodyText().isEqualTo(...)` xác nhận nội dung response.

Không cần tạo biến `MvcResult`, gọi `andReturn()` hay viết matcher riêng cho từng assertion thông thường.

## 5. Kiểm tra JSON response

Với endpoint trả JSON, có thể dùng `bodyJson()` để kiểm tra cấu trúc JSON và truy vấn một trường bằng JsonPath.

Ví dụ controller tạo đơn hàng và trả về mã đơn hàng:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @PostMapping("/orders")
    @ResponseStatus(HttpStatus.CREATED)
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        return new OrderResponse("ORD-42", request.customerId());
    }
}

record CreateOrderRequest(String customerId) {
}

record OrderResponse(String id, String customerId) {
}
```

Test có thể gửi JSON và kiểm tra status cùng trường trong response:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;

@Test
void createsOrderAndReturnsItsIdentifier() {
    assertThat(mvc.post().uri("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerId": "C-208"
                }
                """))
        .hasStatus(HttpStatus.CREATED)
        .bodyJson()
        .extractingPath("$.id")
        .isEqualTo("ORD-42");
}
```

`contentType(...)` khai báo kiểu dữ liệu request; `content(...)` gửi JSON body; `accept(...)` thể hiện client mong muốn response dạng JSON. `hasStatus(...)` kiểm tra status cụ thể; `bodyJson()` chuyển sang assertion dành cho JSON; `extractingPath(...)` lấy giá trị tại JSONPath đã chỉ định.

Nếu chỉ cần so sánh toàn bộ response body dạng text, dùng `bodyText()`. Khi cần xác nhận cấu trúc hoặc một vài trường JSON, `bodyJson()` giúp test ít phụ thuộc vào thứ tự field và khoảng trắng trong chuỗi JSON.

## 6. Kiểm tra lỗi HTTP và response nghiệp vụ

Fluent assertion cũng hữu ích khi kiểm tra tình huống lỗi. Ví dụ, endpoint không tìm thấy đơn hàng có thể trả về status 404 và một JSON lỗi đã được `@ControllerAdvice` chuẩn hóa:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.http.HttpStatus;

@Test
void returnsNotFoundForUnknownOrder() {
    assertThat(mvc.get().uri("/orders/{id}", "missing"))
        .hasStatus(HttpStatus.NOT_FOUND)
        .bodyJson()
        .extractingPath("$.code")
        .isEqualTo("ORDER_NOT_FOUND");
}
```

Test kiểm tra cả mã HTTP và mã lỗi nghiệp vụ. Chỉ kiểm tra status 404 có thể bỏ sót trường hợp response chứa sai error code; chỉ kiểm tra JSON body cũng có thể bỏ sót việc ứng dụng trả sai HTTP status.

Với lỗi được xử lý bởi `@ExceptionHandler` hoặc `@ControllerAdvice`, hãy xác nhận response cuối cùng mà client nhận được. Nếu mục tiêu là kiểm tra trực tiếp exception được ném ra trước khi Spring xử lý, đó là một mục tiêu kiểm thử khác và có thể cần kiểm tra exception ở tầng service hoặc gọi component phù hợp.

## 7. Thiết lập thông tin request

Request builder của `MockMvcTester` hỗ trợ các thông tin thường dùng tương tự request builder của MockMvc:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.http.MediaType;

assertThat(mvc.get().uri("/account")
        .header("X-Trace-Id", "trace-276")
        .cookie(new jakarta.servlet.http.Cookie("locale", "vi"))
        .sessionAttr("userId", "U-17")
        .accept(MediaType.APPLICATION_JSON))
    .hasStatusOk();
```

Các phương thức thường dùng gồm:

| Phương thức | Ý nghĩa |
|---|---|
| `uri(...)` | Chọn URI và truyền path variable |
| `param(...)` / `queryParam(...)` | Thiết lập request parameter hoặc query parameter |
| `header(...)` | Thêm HTTP header |
| `cookie(...)` | Thêm cookie vào request |
| `session(...)` / `sessionAttr(...)` | Thiết lập session hoặc session attribute |
| `contentType(...)` | Khai báo kiểu dữ liệu request body |
| `accept(...)` | Khai báo kiểu response client chấp nhận |
| `content(...)` | Thiết lập request body |

Chỉ đưa vào request các dữ liệu thuộc hợp đồng của endpoint. Ví dụ, nếu controller đọc `@RequestHeader`, hãy dùng `header(...)`; nếu controller đọc `@RequestParam`, hãy dùng `param(...)` hoặc `queryParam(...)`. Không thay thế header bằng parameter chỉ vì tên dữ liệu giống nhau.

## 8. So sánh MockMvcTester và MockMvc truyền thống

Hai API cùng kiểm thử Spring MVC thông qua MockMvc infrastructure. Sự khác biệt chủ yếu nằm ở cách xây dựng request và diễn đạt assertion.

| Nội dung | MockMvc | MockMvcTester |
|---|---|---|
| Tạo request | `mockMvc.perform(get(...))` | `mvc.get().uri(...)` |
| Kiểm tra status | `.andExpect(status().isOk())` | `.hasStatusOk()` |
| Kiểm tra text | `.andExpect(content().string("..."))` | `.bodyText().isEqualTo("...")` |
| Kiểm tra JSON | `jsonPath("$.id").value(...)` | `.bodyJson().extractingPath("$.id").isEqualTo(...)` |
| Kết quả trung gian | `MvcResult` | Fluent assertion từ request/result |
| Hạ tầng thực thi | `DispatcherServlet` và servlet mock | Dùng lại MockMvc infrastructure |

Ví dụ cùng một kiểm thử theo hai cách:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// MockMvc truyền thống
mockMvc.perform(get("/greeting").param("name", "Mai"))
    .andExpect(status().isOk())
    .andExpect(content().string("Hello Mai"));

// MockMvcTester
assertThat(mvc.get().uri("/greeting").param("name", "Mai"))
    .hasStatusOk()
    .bodyText().isEqualTo("Hello Mai");
```

`MockMvc` vẫn hữu ích khi cần các `ResultMatcher`, `ResultHandler`, `MvcResult` hoặc cách điều khiển chi tiết đã có trong test cũ. `MockMvcTester` phù hợp khi muốn viết assertion trực tiếp theo phong cách AssertJ. Hai cách có thể cùng tồn tại trong một dự án; không cần chuyển đổi toàn bộ test chỉ để sử dụng API mới.

## 9. Giới hạn và lỗi thường gặp

`MockMvcTester` không phải HTTP client gửi request qua mạng. Nó không kiểm tra cổng server, TLS, reverse proxy hay khác biệt của servlet container thật. Khi cần xác nhận những hành vi đó, hãy dùng kiểm thử khởi động server và gửi HTTP request thực tế.

Một số lỗi thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Không tìm thấy `MockMvcTester` | Spring Framework thấp hơn 6.2 hoặc dependency `spring-test` không nằm trên test classpath |
| Không tiêm được bean trong Spring Boot | Boot chưa có auto-configuration hỗ trợ, thiếu AssertJ hoặc chưa bật cấu hình MockMvc |
| `NoSuchMethodError` hoặc lỗi tương thích Spring | Các module Spring Framework dùng phiên bản không đồng bộ; kiểm tra BOM và dependency overrides |
| Request không khớp endpoint | Sai method, URI, context path, servlet path hoặc request parameter |
| JSON body không được bind | Sai `Content-Type`, JSON không hợp lệ hoặc message converter không phù hợp |
| Assertion status đúng nhưng body sai | Kiểm tra riêng `bodyText()` hoặc `bodyJson()` và dữ liệu controller trả về |

Khi chuyển một test cũ sang `MockMvcTester`, nên giữ nguyên kịch bản request và các điều kiện cần kiểm tra. Thay đổi cách viết assertion trước, sau đó xác nhận status và body vẫn thể hiện cùng hợp đồng HTTP.

## 10. Quy trình viết fluent assertion

1. Đảm bảo dự án dùng Spring Framework 6.2 trở lên và có AssertJ trong test classpath.
2. Tạo hoặc tiêm `MockMvcTester` từ MockMvc infrastructure.
3. Chọn HTTP method và URI bằng `get()`, `post()` hoặc builder tương ứng.
4. Thêm path variable, parameter, header, cookie, session và body đúng với endpoint.
5. Dùng `hasStatusOk()` hoặc `hasStatus(...)` để xác nhận HTTP status.
6. Dùng `bodyText()` hoặc `bodyJson()` để kiểm tra response body.
7. Giữ lại MockMvc truyền thống cho test cần matcher hoặc result handler đặc thù.

`MockMvcTester` giúp request và assertion nằm trong một biểu thức dễ đọc: mô tả client gửi gì, sau đó xác nhận server Spring MVC trả gì. Hiểu điều kiện phiên bản và cách kết hợp với MockMvc truyền thống sẽ giúp áp dụng fluent assertion đúng nơi mà không làm thay đổi phạm vi kiểm thử.

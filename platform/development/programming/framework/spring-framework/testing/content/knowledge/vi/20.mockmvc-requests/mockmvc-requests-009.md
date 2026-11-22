# RequestPostProcessor cho dữ liệu bổ sung

Khi gửi request bằng MockMvc, các phương thức của `MockHttpServletRequestBuilder` như `param(...)`, `header(...)`, `cookie(...)`, `sessionAttr(...)` và `requestAttr(...)` đã đáp ứng nhiều tình huống phổ biến. Tuy nhiên, đôi khi test cần chuẩn bị dữ liệu theo logic riêng, thiết lập nhiều thuộc tính cùng lúc hoặc dùng lại một cách bổ sung request ở nhiều test. `RequestPostProcessor` cung cấp một điểm mở rộng cho những trường hợp đó.

`RequestPostProcessor` nhận một `MockHttpServletRequest`, thay đổi hoặc bổ sung dữ liệu trên request rồi trả lại request đã xử lý. Ta gắn processor vào request builder bằng `.with(...)` trước khi gọi `mockMvc.perform(...)`.

## 1. RequestPostProcessor hoạt động ở đâu?

Luồng cơ bản của một test MockMvc:

```text
MockMvcRequestBuilders.get("/orders")
             |
             v
    MockHttpServletRequestBuilder
             |
             v
       .with(processor)
             |
             v
 RequestPostProcessor.postProcessRequest(request)
             |
             v
       MockMvc.perform(request)
             |
             v
 DispatcherServlet -> Controller -> Response
```

Interface nằm trong package `org.springframework.test.web.servlet.request` và có phương thức:

```java
MockHttpServletRequest postProcessRequest(MockHttpServletRequest request);
```

Processor được gọi trên request mock mà builder chuẩn bị. Nó có thể thêm header, đặt request attribute, thiết lập principal hoặc điều chỉnh những thuộc tính Servlet khác. Sau khi xử lý, processor phải trả về request để MockMvc tiếp tục thực hiện request đó.

`RequestPostProcessor` chỉ làm việc với request. Nó không nhận response và không phải nơi để assertion về status, body hay header phản hồi. Hãy dùng `ResultMatcher` như `status()`, `content()` và `header()` để kiểm tra response.

## 2. Khi nào nên dùng `.with(...)`?

Với dữ liệu đơn giản, ưu tiên API có sẵn trên request builder vì chúng thể hiện ý định trực tiếp:

```java
mockMvc.perform(get("/orders")
        .param("status", "OPEN")
        .header("X-Request-Id", "req-123")
        .cookie(new Cookie("locale", "vi"))
        .sessionAttr("cartId", "cart-42")
        .requestAttr("traceId", "trace-123"));
```

Dùng `RequestPostProcessor` khi:

- Cần thiết lập một thuộc tính mà builder không có phương thức tiện ích tương ứng.
- Một request cần được bổ sung nhiều giá trị có liên quan theo cùng một quy tắc.
- Cùng một cách chuẩn bị request được sử dụng trong nhiều test.
- Dữ liệu cần được tính toán hoặc lấy từ tham số của một factory method.
- Muốn đóng gói một cấu hình test như tenant, correlation ID hoặc thông tin xác thực.

Không cần tạo processor riêng cho mỗi header hoặc parameter đơn giản. Một lambda ngắn phù hợp khi logic chỉ xuất hiện ở một test; một factory method hoặc class riêng hữu ích khi logic được dùng lại.

## 3. Tạo processor bằng lambda

Vì `RequestPostProcessor` có một phương thức cần triển khai, có thể viết bằng lambda:

```java
RequestPostProcessor tenantHeader = request -> {
    request.addHeader("X-Tenant-Id", "tenant-42");
    return request;
};
```

Gắn processor vào request:

```java
mockMvc.perform(get("/orders").with(tenantHeader))
        .andExpect(status().isOk());
```

Ở đây, `addHeader(...)` bổ sung header vào request mock. Controller có thể đọc giá trị đó qua `@RequestHeader` hoặc `HttpServletRequest#getHeader(...)`.

Ví dụ controller đọc tenant ID:

```java
@RestController
class TenantController {

    @GetMapping("/tenant")
    String tenant(@RequestHeader("X-Tenant-Id") String tenantId) {
        return tenantId;
    }
}
```

Test sử dụng processor:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new TenantController())
        .build();

RequestPostProcessor tenantHeader = request -> {
    request.addHeader("X-Tenant-Id", "tenant-42");
    return request;
};

mockMvc.perform(get("/tenant").with(tenantHeader))
        .andExpect(status().isOk())
        .andExpect(content().string("tenant-42"));
```

Ví dụ dùng `standaloneSetup` để tập trung vào controller và processor. Nếu test cần Spring MVC configuration đầy đủ, có thể dùng `webAppContextSetup(...)` hoặc cấu hình Spring Boot phù hợp.

## 4. Bổ sung nhiều loại dữ liệu trên request

Processor nhận `MockHttpServletRequest`, vì vậy có thể sử dụng các API của request mock. Một số trường hợp thường gặp:

### Thêm header

```java
RequestPostProcessor requestHeaders = request -> {
    request.addHeader("X-Tenant-Id", "tenant-42");
    request.addHeader("X-Correlation-Id", "corr-100");
    return request;
};
```

Dùng `addHeader(...)` khi muốn bổ sung header. Nếu cần thiết lập hoặc thay đổi giá trị của một header trong test, hãy cân nhắc hành vi của request mock và tránh để nhiều processor cùng ghi một header với các giá trị xung đột.

### Đặt request attribute

```java
RequestPostProcessor requestAttributes = request -> {
    request.setAttribute("tenantId", "tenant-42");
    request.setAttribute("featureEnabled", Boolean.TRUE);
    return request;
};
```

Request attribute tồn tại trong phạm vi request hiện tại. Controller hoặc interceptor có thể đọc qua `@RequestAttribute` hoặc `request.getAttribute(...)`. Đây là dữ liệu phía server đã được đặt vào request; nó không giống header hoặc parameter do client gửi lên.

### Đặt session attribute

```java
RequestPostProcessor sessionData = request -> {
    request.getSession(true).setAttribute("cartId", "cart-42");
    return request;
};
```

`getSession(true)` tạo session nếu request chưa có session. Dữ liệu được lưu trong session và có thể tồn tại qua nhiều request dùng cùng session. Nếu chỉ cần một session attribute đơn giản, builder cũng có `sessionAttr(...)`; processor phù hợp khi cần chuẩn bị nhiều giá trị hoặc áp dụng logic riêng.

### Thiết lập principal

Có thể đặt principal của request mock để kiểm tra controller đọc `Principal` hoặc `HttpServletRequest#getUserPrincipal()`:

```java
RequestPostProcessor principal = request -> {
    request.setUserPrincipal(() -> "alice");
    return request;
};
```

Đây là principal được đặt trực tiếp trên Servlet request. Nó không tự tạo một phiên đăng nhập Spring Security hoặc chứng minh security filter chain đã xác thực người dùng. Với test Spring Security, nên dùng các processor chuyên dụng của `spring-security-test` như `user(...)` khi mục tiêu là cung cấp một `Authentication` cho Spring Security.

### Thiết lập thông tin kết nối

```java
RequestPostProcessor httpsRequest = request -> {
    request.setScheme("https");
    request.setSecure(true);
    request.setServerName("api.example.test");
    request.setServerPort(443);
    request.setRemoteAddr("192.0.2.25");
    return request;
};
```

Những thuộc tính này hữu ích khi ứng dụng tạo absolute URL, kiểm tra secure request hoặc ghi nhận địa chỉ client. Đây là dữ liệu của request mock; test không tạo kết nối mạng thật.

## 5. Tạo processor có thể tái sử dụng

Khi nhiều test cần cùng một quy tắc, hãy đóng gói nó thành factory method. Ví dụ sau nhận tenant ID làm tham số nên mỗi request có thể dùng tenant khác nhau:

```java
static RequestPostProcessor tenant(String tenantId) {
    return request -> {
        request.addHeader("X-Tenant-Id", tenantId);
        return request;
    };
}
```

Sử dụng trong các test:

```java
mockMvc.perform(get("/tenant").with(tenant("tenant-a")))
        .andExpect(status().isOk())
        .andExpect(content().string("tenant-a"));

mockMvc.perform(get("/tenant").with(tenant("tenant-b")))
        .andExpect(status().isOk())
        .andExpect(content().string("tenant-b"));
```

Có thể tạo class riêng nếu processor có nhiều tham số hoặc logic dài:

```java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

final class TenantRequestPostProcessor implements RequestPostProcessor {

    private final String tenantId;

    TenantRequestPostProcessor(String tenantId) {
        this.tenantId = tenantId;
    }

    @Override
    public MockHttpServletRequest postProcessRequest(MockHttpServletRequest request) {
        request.addHeader("X-Tenant-Id", tenantId);
        return request;
    }
}
```

Gọi class này qua `.with(new TenantRequestPostProcessor("tenant-42"))`. Class riêng giúp đặt tên rõ ràng và gom logic nhiều bước, còn factory method thường gọn hơn cho một processor nhỏ.

## 6. Kết hợp nhiều RequestPostProcessor

Một request builder có thể nhận nhiều lời gọi `.with(...)`:

```java
mockMvc.perform(get("/orders")
        .with(tenant("tenant-42"))
        .with(request -> {
            request.addHeader("X-Correlation-Id", "corr-123");
            return request;
        })
        .with(request -> {
            request.setAttribute("featureEnabled", Boolean.TRUE);
            return request;
        }))
        .andExpect(status().isOk());
```

Các processor được áp dụng tuần tự trên request builder. Vì thế, nếu hai processor cùng sửa một thuộc tính, processor chạy sau có thể thay đổi kết quả của processor trước. Nên phân chia trách nhiệm rõ ràng và tránh để nhiều processor cùng ghi một header, principal hoặc attribute nếu test không chủ ý kiểm tra tình huống ghi đè.

Khi một nhóm processor luôn đi cùng nhau, có thể gom chúng vào một processor duy nhất để test dễ đọc hơn. Tuy nhiên, giữ chúng riêng cũng hữu ích nếu từng phần có thể tái sử dụng độc lập.

## 7. Dùng RequestPostProcessor của Spring Security

Spring Security cung cấp các `RequestPostProcessor` riêng trong module `spring-security-test`. Chúng thường được dùng để chuẩn bị trạng thái bảo mật cho MockMvc test, ví dụ user đã xác thực hoặc CSRF token.

Ví dụ:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(post("/admin/reports")
        .with(user("alice").roles("ADMIN"))
        .with(csrf()))
        .andExpect(status().isOk());
```

- `user("alice").roles("ADMIN")` cung cấp người dùng đã xác thực cùng authority tương ứng trong ngữ cảnh Spring Security test.
- `csrf()` thêm CSRF token hợp lệ vào request để vượt qua kiểm tra CSRF khi cấu hình bảo mật yêu cầu token.

Để các processor này có tác dụng như mong đợi, test cần dependency `spring-security-test` và MockMvc phải được tích hợp với Spring Security filter chain, ví dụ qua `SecurityMockMvcConfigurers.springSecurity()` khi dựng builder thủ công hoặc cấu hình MockMvc của Spring Boot. Nếu filter chain không chạy, việc đặt user hoặc CSRF token không kiểm tra được hành vi bảo mật thực tế.

Ví dụ dựng MockMvc thủ công với Spring Security:

```java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

`user(...)` là cách chuẩn bị `SecurityContext` cho test. Nó không mô phỏng toàn bộ quy trình đăng nhập như gửi username/password đến một trang login. Nếu cần kiểm thử authentication mechanism thực tế, hãy gửi request qua đúng endpoint và filter chain liên quan.

## 8. RequestPostProcessor và các cách thêm dữ liệu khác

| Nhu cầu | API phù hợp | Ví dụ |
|---|---|---|
| Query parameter | Request builder | `.param("page", "2")` |
| Header đơn giản | Request builder | `.header("X-Trace-Id", "t-1")` |
| Cookie | Request builder | `.cookie(new Cookie("lang", "vi"))` |
| Session attribute đơn giản | Request builder | `.sessionAttr("cartId", "c-1")` |
| Request attribute đơn giản | Request builder | `.requestAttr("tenantId", "t-1")` |
| Dữ liệu cần logic hoặc nhiều thuộc tính | `RequestPostProcessor` | `.with(tenantAndTrace("t-1", "trace-1"))` |
| User hoặc CSRF trong Spring Security | Security request post-processors | `.with(user("alice")).with(csrf())` |

Các API của builder thường dễ đọc hơn cho dữ liệu đơn lẻ. Processor hữu ích khi muốn đóng gói quy tắc hoặc thay đổi request theo logic riêng.

## 9. Ví dụ hoàn chỉnh: gửi tenant và correlation ID

Giả sử controller trả về thông tin nhận được từ request:

```java
@RestController
class RequestInfoController {

    @GetMapping("/request-info")
    String requestInfo(@RequestHeader("X-Tenant-Id") String tenantId,
                       @RequestHeader("X-Correlation-Id") String correlationId) {
        return tenantId + ":" + correlationId;
    }
}
```

Tạo factory method để bổ sung cả hai header:

```java
static RequestPostProcessor requestInfo(String tenantId, String correlationId) {
    return request -> {
        request.addHeader("X-Tenant-Id", tenantId);
        request.addHeader("X-Correlation-Id", correlationId);
        return request;
    };
}
```

Test:

```java
import org.junit.jupiter.api.Test;

import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class RequestPostProcessorTests {

    private final MockMvc mockMvc = MockMvcBuilders
            .standaloneSetup(new RequestInfoController())
            .build();

    @Test
    void addsTenantAndCorrelationHeaders() throws Exception {
        mockMvc.perform(get("/request-info")
                .with(requestInfo("tenant-42", "corr-123")))
                .andExpect(status().isOk())
                .andExpect(content().string("tenant-42:corr-123"));
    }
}
```

Ví dụ cho thấy processor có thể đóng gói nhiều header thành một đơn vị có tên theo ý nghĩa nghiệp vụ. Test chỉ cần truyền dữ liệu và kiểm tra response.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Processor không có tác dụng | Tạo processor nhưng quên gắn bằng `.with(...)` | Gắn processor vào đúng request builder được gửi cho `mockMvc.perform(...)` |
| Request bị lỗi khi chạy | `postProcessRequest` không trả về request | Luôn trả về đối tượng `MockHttpServletRequest` đã xử lý |
| Controller không đọc được dữ liệu | Đặt request attribute trong khi controller đang đọc header hoặc parameter | Chọn đúng kênh dữ liệu: header, parameter, request attribute hay session attribute |
| Giá trị bị ghi đè | Nhiều processor sửa cùng một thuộc tính | Kiểm soát thứ tự và phân chia trách nhiệm giữa các processor |
| Dữ liệu rò rỉ giữa các test | Dùng chung object mutable hoặc session state không chủ ý | Tạo dữ liệu mới cho mỗi request; chỉ chia sẻ processor bất biến |
| `user(...)` không tạo trạng thái xác thực mong đợi | Thiếu `spring-security-test` hoặc security filter chain không chạy | Thêm dependency và tích hợp Spring Security với MockMvc |
| Request có principal nhưng authorization vẫn thất bại | Chỉ gọi `setUserPrincipal(...)`, không thiết lập SecurityContext của Spring Security | Dùng processor `user(...)` khi test Spring Security |

## 11. Nguyên tắc sử dụng

- Dùng API trực tiếp của request builder cho parameter, header, cookie và attribute đơn giản.
- Dùng `RequestPostProcessor` khi cần logic bổ sung, nhiều thuộc tính liên quan hoặc một quy tắc dùng lại.
- Luôn trả về `MockHttpServletRequest` từ `postProcessRequest`.
- Tạo dữ liệu theo từng request và tránh trạng thái mutable dùng chung giữa các test.
- Khi kết hợp nhiều processor, giữ thứ tự rõ ràng và tránh ghi đè ngoài ý muốn.
- Dùng `ResultMatcher` để kiểm tra response; processor chỉ chuẩn bị request.
- Với Spring Security, dùng processor thuộc `spring-security-test` và bảo đảm security filter chain thực sự tham gia MockMvc.

## 12. Ghi nhớ

`RequestPostProcessor` là điểm mở rộng để tùy chỉnh `MockHttpServletRequest` trước khi MockMvc thực thi request. Gắn processor bằng `.with(...)`; triển khai có thể dùng lambda, factory method hoặc class riêng. Nó phù hợp để bổ sung header, request/session attribute, principal hoặc thông tin kết nối theo logic riêng. Với dữ liệu đơn giản, các phương thức sẵn có trên request builder thường dễ đọc hơn; với trạng thái xác thực và CSRF, hãy dùng các processor chuyên dụng của Spring Security.


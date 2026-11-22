# Đăng ký Filter và thứ tự xử lý trong MockMvc

Filter là một phần của Servlet request processing pipeline. Filter có thể kiểm tra hoặc thay đổi request trước khi request đến `DispatcherServlet`, rồi xử lý response khi lời gọi trong filter chain quay trở lại. Khi viết test với MockMvc, cần đăng ký những filter mà request phải đi qua và kiểm soát thứ tự của chúng để kết quả kiểm thử phản ánh đúng cấu hình mong muốn.

Bài này tập trung vào việc đăng ký filter với MockMvc, ánh xạ filter theo URL và xác nhận thứ tự chạy. Ví dụ dùng JUnit Jupiter và Spring Framework 6 trở lên; với Spring Framework 5.x, thay các import `jakarta.servlet.*` bằng `javax.servlet.*` tương ứng.

## 1. Filter nằm ở đâu trong request flow?

Trong ứng dụng Spring MVC, một request thường đi qua chuỗi sau:

```text
HTTP request
    |
    v
Filter A
    |
    v
Filter B
    |
    v
DispatcherServlet
    |
    v
HandlerMapping -> Controller
    |
    v
HTTP response quay ngược qua Filter B, rồi Filter A
```

Filter chạy trước `DispatcherServlet`, nên có thể xử lý những mối quan tâm ở cấp Servlet như encoding, CORS, authentication, logging, correlation ID hoặc bọc request/response. Một filter gọi `filterChain.doFilter(request, response)` để chuyển quyền xử lý cho filter tiếp theo. Khi filter tiếp theo hoàn tất, luồng thực thi quay về dòng lệnh sau lời gọi đó.

Filter khác với `HandlerInterceptor`: interceptor thuộc pipeline Spring MVC và làm việc quanh handler/controller; filter thuộc Servlet pipeline và chạy trước `DispatcherServlet`. Nếu cần kiểm tra logic phụ thuộc vào handler đã được chọn, interceptor có thể phù hợp hơn. Nếu cần kiểm tra hành vi ở cấp request/response Servlet, hãy kiểm tra filter.

## 2. Chọn cách dựng MockMvc

MockMvc có hai cách dựng phổ biến:

| Cách dựng | Khi nào dùng | Cách đăng ký filter |
|---|---|---|
| `standaloneSetup(...)` | Kiểm thử một hoặc vài controller với cấu hình MVC tối thiểu | Gọi `addFilters(...)` hoặc `addFilter(...)` trên builder |
| `webAppContextSetup(webApplicationContext)` | Kiểm thử với cấu hình Spring MVC và application context đã nạp | Gọi `addFilters(...)` hoặc `addFilter(...)` trên builder khi filter cần tham gia request của MockMvc |

Ví dụ standalone:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .addFilters(new CharacterEncodingFilter("UTF-8", true))
        .build();
```

Ví dụ dùng `WebApplicationContext`:

```java
@Autowired
private WebApplicationContext webApplicationContext;

MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .addFilters(characterEncodingFilter, auditFilter)
        .build();
```

`standaloneSetup` không tự nạp toàn bộ cấu hình ứng dụng. Test phải cung cấp controller, controller advice, converter, argument resolver và filter cần thiết cho kịch bản. `webAppContextSetup` dùng cấu hình MVC từ context, nhưng khi tự dựng MockMvc, hãy đăng ký rõ filter mà test cần chạy qua thay vì giả định một filter bean bất kỳ luôn tự xuất hiện trong filter chain của builder.

## 3. Đăng ký một hoặc nhiều filter

`MockMvcBuilders` trả về builder có các phương thức đăng ký filter:

- `addFilters(Filter... filters)` đăng ký một nhóm filter áp dụng cho mọi request được MockMvc thực hiện.
- `addFilter(Filter filter, String... urlPatterns)` đăng ký filter với các URL pattern được chỉ định.

Ví dụ đăng ký nhiều filter:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .addFilters(encodingFilter, requestLoggingFilter, authenticationFilter)
        .build();
```

Với cách đăng ký này, các filter được đưa vào chain theo thứ tự truyền vào. Vì vậy, thứ tự trong danh sách có ý nghĩa: `encodingFilter` chạy trước `requestLoggingFilter`, rồi đến `authenticationFilter`. Khi cần thứ tự dễ đọc và ổn định, hãy đặt tất cả filter trong một lời gọi `addFilters(...)` theo thứ tự mong muốn.

Đăng ký filter theo URL pattern:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .addFilter(apiAuditFilter, "/api/*")
        .build();
```

Trong ví dụ, `apiAuditFilter` được ánh xạ cho URL thuộc `/api/*`. Một request như `/api/orders` sẽ khớp pattern; request `/health` thì không. URL pattern là một phần của cấu hình mapping Servlet, vì vậy hãy chọn pattern phù hợp với URL mà test gửi đến.

Khi filter chỉ phục vụ một nhóm endpoint, mapping cụ thể giúp test thể hiện đúng phạm vi của filter. Khi filter cần chạy cho mọi endpoint trong test, dùng `addFilters(...)` sẽ ngắn gọn hơn.

## 4. Thứ tự filter và cách request đi qua chain

Servlet filter chain có hai chiều quan sát:

- **Chiều vào:** filter đầu tiên chạy trước. Sau đó filter gọi `filterChain.doFilter(...)` để chuyển sang filter kế tiếp.
- **Chiều ra:** khi downstream xử lý xong, các filter tiếp tục thực thi phần code nằm sau lời gọi `doFilter`, theo thứ tự ngược lại.

Giả sử đăng ký `firstFilter` rồi `secondFilter`, trace thường có dạng:

```text
first:before
second:before
controller
second:after
first:after
```

Thứ tự này giải thích vì sao một filter ngoài có thể đo thời gian tổng của filter bên trong và controller, hoặc bọc response để xử lý sau khi downstream hoàn tất.

### Ví dụ kiểm tra thứ tự bằng MockMvc

Filter đơn giản ghi lại thời điểm vào và ra:

```java
import java.io.IOException;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

class TraceFilter extends OncePerRequestFilter {

    private final String name;
    private final List<String> trace;

    TraceFilter(String name, List<String> trace) {
        this.name = name;
        this.trace = trace;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain)
            throws ServletException, IOException {
        trace.add(name + ":before");
        try {
            filterChain.doFilter(request, response);
        } finally {
            trace.add(name + ":after");
        }
    }
}
```

Controller dùng trong test:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PingController {

    @GetMapping("/ping")
    String ping() {
        return "pong";
    }
}
```

Test xác nhận response và thứ tự filter:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class FilterOrderTests {

    @Test
    void filtersRunInRegistrationOrder() throws Exception {
        List<String> trace = new ArrayList<>();

        MockMvc mockMvc = MockMvcBuilders
                .standaloneSetup(new PingController())
                .addFilters(
                        new TraceFilter("first", trace),
                        new TraceFilter("second", trace))
                .build();

        mockMvc.perform(get("/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));

        assertEquals(Arrays.asList(
                "first:before",
                "second:before",
                "second:after",
                "first:after"), trace);
    }
}
```

Test này xác nhận đồng thời hai điều: endpoint vẫn trả về nội dung mong đợi và filter chain thực thi theo thứ tự đăng ký. `try/finally` trong filter giúp ghi lại phần kết thúc ngay cả khi downstream ném exception; nếu chỉ thêm log sau `doFilter` mà không có `finally`, log đó sẽ không chạy khi có exception.

## 5. Thứ tự khi dùng Spring Boot

Trong test Spring Boot, `@AutoConfigureMockMvc` có thuộc tính `addFilters`. Giá trị mặc định là `true`, nghĩa là các filter từ application context được đưa vào MockMvc. Có thể tắt việc thêm filter khi test chỉ cần kiểm tra MVC mà không cần chạy filter chain:

```java
@WebMvcTest(PingController.class)
@AutoConfigureMockMvc(addFilters = true)
class PingControllerTests {

    @Autowired
    private MockMvc mockMvc;

    // Tests
}
```

Để test bỏ qua các filter đã cấu hình trong context:

```java
@WebMvcTest(PingController.class)
@AutoConfigureMockMvc(addFilters = false)
class PingControllerWithoutFiltersTests {
    // Tests chỉ tập trung vào MVC handler.
}
```

Chỉ tắt filter khi đó là phạm vi test mong muốn. Ví dụ, nếu ứng dụng dùng Spring Security, tắt filter có thể làm request trong test không còn đi qua security filter chain và kết quả không phản ánh hành vi xác thực/phân quyền của ứng dụng.

Khi dùng Spring Boot để đăng ký filter cho Servlet container, thứ tự thường được điều khiển bằng `FilterRegistrationBean#setOrder(...)` hoặc `@Order` trên filter bean. Giá trị order nhỏ hơn có độ ưu tiên cao hơn và được đưa lên trước. Dùng `FilterRegistrationBean` khi cần cấu hình rõ URL pattern, dispatcher type hoặc order:

```java
@Bean
FilterRegistrationBean<AuditFilter> auditFilterRegistration() {
    FilterRegistrationBean<AuditFilter> registration =
            new FilterRegistrationBean<>(new AuditFilter());
    registration.addUrlPatterns("/api/*");
    registration.setOrder(20);
    return registration;
}
```

Đây là cấu hình đăng ký filter ở Spring Boot. Nếu test tự tạo MockMvc builder và gọi `.addFilters(first, second)`, hãy xem thứ tự trong lời gọi builder là thứ tự test đang yêu cầu; không nên dựa vào `@Order` để thay thế thứ tự đã truyền rõ ràng ở đó.

## 6. Filter có thể chặn request

Filter không bắt buộc phải gọi `filterChain.doFilter(...)`. Nó có thể tự tạo response và kết thúc chain, chẳng hạn khi request không đạt điều kiện:

```java
public class HeaderGuardFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain)
            throws ServletException, IOException {
        if (request.getHeader("X-Client-Token") == null) {
            response.sendError(HttpServletResponse.SC_FORBIDDEN);
            return;
        }

        filterChain.doFilter(request, response);
    }
}
```

Test có thể xác nhận request bị chặn:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new PingController())
        .addFilters(new HeaderGuardFilter())
        .build();

mockMvc.perform(get("/ping"))
        .andExpect(status().isForbidden());
```

Khi filter chặn request, filter đứng sau và controller sẽ không được gọi. Nếu cần xác nhận điều đó, có thể dùng mock collaborator hoặc một cờ kiểm tra trong test để chứng minh handler không chạy.

## 7. Kiểm tra mapping và tránh đăng ký trùng

Khi test không thấy filter chạy, hãy xem lại các điểm sau:

- Filter đã được đăng ký trên đúng MockMvc instance mà test đang sử dụng chưa?
- Request URL có khớp URL pattern được truyền vào `addFilter(...)` không?
- Test có đang dùng `@AutoConfigureMockMvc(addFilters = false)` không?
- Filter có điều kiện bỏ qua request, chẳng hạn kiểm tra header, path hoặc dispatcher type, không?
- Filter có được đăng ký hai lần, vừa qua cấu hình Boot vừa qua lời gọi `addFilters(...)`, khiến nó chạy lặp không?

Đăng ký trùng có thể làm log xuất hiện hai lần, thay đổi response hoặc khiến assertion về số lần gọi thất bại. Chọn một cơ chế đăng ký rõ ràng cho mỗi filter trong cấu hình test.

Với `OncePerRequestFilter`, mặc định filter được thiết kế để tránh xử lý lặp trong cùng một request dispatch. Tuy vậy, hành vi với async dispatch hoặc error dispatch còn phụ thuộc vào các hook và dispatcher type liên quan. Nếu test có async request, hãy kiểm tra riêng luồng dispatch đó thay vì suy luận từ một request đồng bộ thông thường.

## 8. Các tình huống thực tế

| Nhu cầu | Cách thiết lập gợi ý | Điều cần assertion |
|---|---|---|
| Mọi request phải có encoding UTF-8 | Đăng ký `CharacterEncodingFilter` bằng `addFilters(...)` | Encoding của request/response hoặc nội dung tiếng Việt trả về |
| Chỉ API cần audit | Dùng `addFilter(auditFilter, "/api/*")` | Filter chạy với `/api/...` và không chạy với URL ngoài pattern |
| Xác nhận authentication chạy trước controller | Đăng ký security filter chain trong MockMvc | Request thiếu thông tin xác thực bị từ chối; request hợp lệ tới được handler |
| Đo hoặc ghi trace toàn request | Đặt trace filter trước các filter cần quan sát | Trace có thứ tự vào/ra như mong đợi |
| Kiểm thử controller mà không xét filter | Với Spring Boot, cân nhắc `addFilters = false` | Assertion chỉ phản ánh handler và cấu hình MVC trong phạm vi test |

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Filter không được gọi | Chưa đăng ký vào MockMvc hoặc URL không khớp mapping | Dùng `addFilters(...)` hoặc sửa URL pattern |
| Filter chạy sau filter khác ngoài dự kiến | Thứ tự truyền vào builder không đúng | Sắp xếp lại danh sách trong `addFilters(...)` |
| Filter chạy hai lần | Được đăng ký qua nhiều cơ chế hoặc có nhiều dispatch | Loại bỏ đăng ký trùng; kiểm tra dispatcher type |
| Controller không được gọi | Filter đã chặn request hoặc không gọi `filterChain.doFilter(...)` | Kiểm tra điều kiện chặn và nhánh chuyển tiếp |
| Test Boot không có hành vi security như ứng dụng | `addFilters` bị tắt hoặc security filter không nằm trong test context | Bật filter registration và nạp đúng security configuration |
| Không thấy log phần kết thúc filter khi có lỗi | Code sau `doFilter` không nằm trong `finally` | Dùng `try/finally` nếu cần cleanup hoặc ghi nhận kết thúc |

## 10. Ghi nhớ

Đăng ký filter cho MockMvc bằng `addFilters(...)` khi filter áp dụng cho mọi request, hoặc `addFilter(filter, urlPatterns...)` khi cần giới hạn theo URL. Với builder thủ công, thứ tự đăng ký quyết định thứ tự filter đi vào chain. Filter chạy phần trước downstream theo thứ tự đăng ký và phần sau downstream theo thứ tự ngược lại. Trong Spring Boot, `@AutoConfigureMockMvc(addFilters = true)` đưa các filter từ application context vào MockMvc; order của filter ở cấu hình Boot có thể được điều khiển bằng `FilterRegistrationBean` hoặc `@Order`. Hãy kiểm tra filter chain bằng request thực tế của MockMvc để bảo đảm test đang chạy đúng cấu hình dự định.


# MockMvc với đầy đủ filter Spring Session cần kiểm chứng

MockMvc cho phép kiểm thử ứng dụng Spring MVC mà không cần khởi chạy web server thật. Tuy nhiên, test chỉ gọi controller chưa đủ để chứng minh Spring Session hoạt động đúng. Việc tích hợp session diễn ra qua `SessionRepositoryFilter`, filter bọc request/response và chuyển API `HttpSession` sang repository Spring Session.

Muốn kiểm chứng session được lưu và tải lại, MockMvc phải chạy với application context và filter chain thực tế của ứng dụng. Test nên gửi request đầu tiên để tạo session, lấy session cookie từ response, rồi gửi cookie đó ở request tiếp theo. Khi repository là Redis hoặc JDBC thật, cách kiểm tra này chứng minh đường đi từ HTTP request qua filter đến kho dữ liệu dùng chung.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao MockMvc cần chạy qua `SessionRepositoryFilter`.
- Chọn `@SpringBootTest` kết hợp `@AutoConfigureMockMvc` khi cần full filter chain.
- Phân biệt `webAppContextSetup` với `standaloneSetup`.
- Kiểm tra việc tạo session, phát cookie, tải lại thuộc tính và invalidate.
- Hiểu giới hạn của `MockHttpSession` khi kiểm tra persistence của Spring Session.
- Kết hợp Spring Security filter chain và CSRF test support.
- Xác minh filter order, repository thực tế và giới hạn của MockMvc so với browser test.

## 1. Vì sao phải kiểm thử qua filter?

Trong ứng dụng Servlet, `SessionRepositoryFilter` là điểm tích hợp chính giữa Servlet container và Spring Session. Filter bọc `HttpServletRequest` và `HttpServletResponse` để các lời gọi `getSession()`, `setAttribute()` hoặc `invalidate()` sử dụng session repository thay cho session cục bộ của container.

Luồng xử lý khái quát:

~~~mermaid
sequenceDiagram
    participant T as MockMvc test
    participant F as SessionRepositoryFilter
    participant C as Spring MVC controller
    participant R as SessionRepository
    participant D as Redis/JDBC
    T->>F: HTTP request + cookie nếu có
    F->>R: Tải session theo ID
    R->>D: Đọc session
    D-->>R: Dữ liệu phiên
    R-->>F: Session được quản lý
    F->>C: Dispatch request đã được bọc
    C->>C: Đọc hoặc cập nhật HttpSession
    C-->>F: Response
    F->>R: Lưu hoặc xóa session
    R->>D: Ghi dữ liệu
    D-->>R: Hoàn tất
    F-->>T: Response và Set-Cookie nếu cần
~~~

Nếu test bỏ qua filter, controller vẫn có thể làm việc với `HttpSession` do Mock Servlet API cung cấp. Test có thể pass dù Spring Session repository không hề được gọi. Vì vậy, điều cần chứng minh không chỉ là controller đọc lại được một thuộc tính trong mock request context, mà là request kế tiếp với session cookie có thể tải dữ liệu qua Spring Session.

## 2. Các thành phần cần có trong test context

| Thành phần | Vai trò trong kiểm thử |
|---|---|
| Spring MVC application context | Tạo controller, handler mapping, converter và cấu hình web thực tế |
| `SessionRepositoryFilter` | Chuyển API `HttpSession` sang Spring Session |
| `SessionRepository` | Lưu/tải session qua Redis, JDBC hoặc repository được cấu hình |
| `CookieSerializer` | Đọc session ID từ cookie và phát cookie trên response |
| Spring Security filter chain | Kiểm tra authentication, authorization và CSRF nếu ứng dụng dùng Spring Security |
| MockMvc | Tạo request và kiểm tra response mà không cần cổng HTTP thật |

Với Spring Boot, cách phổ biến để đưa các filter trong application context vào MockMvc là:

~~~java
@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class SessionMvcIntegrationTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

`addFilters` mặc định là `true` trong cấu hình `@AutoConfigureMockMvc` của Spring Boot, nhưng ghi rõ giúp ý định test dễ nhận biết khi đọc code. Cấu hình này đăng ký các filter bean trong application context với MockMvc. Hãy kiểm tra cấu hình test không ghi đè bằng `addFilters = false`.

Nếu không dùng Spring Boot, có thể tạo MockMvc từ `WebApplicationContext` và thêm các filter thực tế:

~~~java
import jakarta.servlet.Filter;

MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .addFilters(sessionRepositoryFilter, springSecurityFilterChain)
        .build();
~~~

Đoạn code minh họa việc thêm filter; `sessionRepositoryFilter` và `springSecurityFilterChain` phải là các đối tượng triển khai Servlet `Filter` lấy từ cấu hình ứng dụng. Bean `SecurityFilterChain` chỉ mô tả cấu hình chuỗi bảo mật, không phải đối tượng truyền trực tiếp vào `addFilters`; trong ứng dụng Spring Security, filter thực tế thường là `FilterChainProxy` được đăng ký dưới tên `springSecurityFilterChain`. Đảm bảo các filter được thêm theo đúng thứ tự mà ứng dụng Servlet sử dụng. Không tạo một `SessionRepositoryFilter` thứ hai nếu context đã có filter thật.

## 3. Chọn webAppContextSetup hay standaloneSetup?

| Cách dựng MockMvc | Thành phần được nạp | Phù hợp để |
|---|---|---|
| `webAppContextSetup(context)` | Dựa trên Spring `WebApplicationContext`; có thể thêm các filter của ứng dụng | Kiểm thử tích hợp MVC, cấu hình session và security |
| `standaloneSetup(controller)` | Controller và cấu hình MVC tối thiểu do test cung cấp | Unit test nhanh cho controller, mapping hoặc response |

`standaloneSetup` không tự nạp toàn bộ cấu hình Servlet, Spring Session và filter chain của ứng dụng. Nếu dùng cách này mà không thêm đúng filter, test không chứng minh được Spring Session đang lưu session.

Với mục tiêu kiểm chứng đầy đủ filter Spring Session, ưu tiên `@SpringBootTest` + `@AutoConfigureMockMvc` hoặc `webAppContextSetup` có filter thực tế. Có thể giữ `standaloneSetup` cho test đơn vị khác, nhưng không dùng kết quả của nó để kết luận persistence qua Spring Session đã được xác minh.

## 4. Dùng repository thực tế trong test

MockMvc chỉ mô phỏng lớp HTTP và Servlet. Để kiểm tra Spring Session, cần cấu hình repository phù hợp:

- JDBC: dùng `spring-session-jdbc`, datasource test và schema Spring Session tương ứng.
- Redis: dùng `spring-session-data-redis` và Redis test instance.
- Repository in-memory: hữu ích cho kiểm tra filter wiring nhanh, nhưng không chứng minh dữ liệu tồn tại qua restart hoặc chia sẻ giữa các process.

Ví dụ cấu hình test profile với JDBC:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:sessiontest;DB_CLOSE_DELAY=-1
    username: sa
    password:
  session:
    store-type: jdbc
    jdbc:
      initialize-schema: always
~~~

Đây là ví dụ cho phiên bản Spring Boot hỗ trợ các property trên và H2 dùng trong test. Cần có JDBC driver H2, `spring-session-jdbc` và starter JDBC. Với production database, integration test quan trọng nên chạy trên cùng loại database hoặc môi trường tương đương để phát hiện khác biệt SQL dialect, schema, transaction và serialization.

Nếu dùng Redis, test nên kết nối Redis container riêng hoặc dịch vụ Redis test được quản lý theo lifecycle của test. Không trỏ test vào Redis production. Khi test cần xác minh dữ liệu chia sẻ giữa instance, hãy dùng cùng một repository backend cho các application context tương ứng.

Không chỉ mock `SessionRepository` nếu mục tiêu là kiểm chứng filter-to-store path. Mock có thể hữu ích cho test lỗi hoặc unit test adapter, nhưng không xác minh cookie serializer, mapping session ID, schema hoặc TTL thực tế.

Trong ví dụ Servlet, các import có thể dùng `jakarta.servlet.http` với Spring Boot 3/Spring Framework 6; dự án cũ dùng `javax.servlet.http`. Hãy dùng đúng namespace theo dòng Spring Framework của ứng dụng.

## 5. Tạo endpoint kiểm thử session

Một controller nhỏ có thể cung cấp ba thao tác: ghi thuộc tính, đọc thuộc tính và invalidate session. Trong dự án thực tế, đặt endpoint tương tự trong test fixture hoặc dùng endpoint nghiệp vụ có sẵn; không nhất thiết thêm endpoint debug vào production.

~~~java
@RestController
@RequestMapping("/test/session")
class SessionProbeController {

    @PostMapping("/value")
    String write(
            HttpServletRequest request,
            @RequestParam String value) {
        request.getSession(true).setAttribute("probe", value);
        return "saved";
    }

    @GetMapping("/value")
    ResponseEntity<String> read(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.notFound().build();
        }

        Object value = session.getAttribute("probe");
        if (value == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(value.toString());
    }

    @PostMapping("/invalidate")
    ResponseEntity<Void> invalidate(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }
}
~~~

Controller dùng `getSession(false)` khi đọc để không vô tình tạo một phiên mới trong lúc kiểm tra session không tồn tại. Nếu đọc bằng `getSession()` mặc định, request kiểm tra có thể tạo session mới và làm test hiểu nhầm rằng phiên cũ vẫn còn.

## 6. Kiểm tra tạo session và round-trip qua cookie

Đây là test cốt lõi: request đầu tiên ghi thuộc tính; response trả cookie session; request thứ hai gửi cookie đó và đọc lại giá trị.

~~~java
@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class SessionMvcIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void sessionAttributeIsAvailableOnNextRequest() throws Exception {
        MvcResult writeResult = mockMvc.perform(post("/test/session/value")
                        .param("value", "alpha"))
                .andExpect(status().isOk())
                .andReturn();

        Cookie sessionCookie =
                writeResult.getResponse().getCookie("SESSION");

        assertThat(sessionCookie).isNotNull();

        mockMvc.perform(get("/test/session/value")
                        .cookie(sessionCookie))
                .andExpect(status().isOk())
                .andExpect(content().string("alpha"));
    }
}
~~~

Ví dụ dùng tên cookie mặc định thường gặp của Spring Session Servlet là `SESSION`. Nếu ứng dụng đổi tên cookie qua `CookieSerializer`, test phải dùng đúng tên đã cấu hình. Với Spring Security bật CSRF, POST cần token hợp lệ; phần tiếp theo trình bày cách bổ sung.

Điểm quan trọng là request thứ hai chỉ mang cookie session ID. Test không truyền lại `MockHttpSession` hay thuộc tính Java từ request trước. Nhờ vậy, session phải được filter tải từ repository.

## 7. Vì sao không chỉ dùng MockHttpSession?

MockMvc hỗ trợ `.session(new MockHttpSession())` để gắn mock session trực tiếp vào request. Cách này tiện cho controller test khi cần đặt sẵn một thuộc tính hoặc giả lập trạng thái Servlet.

Tuy nhiên, nếu mục tiêu là xác minh Spring Session repository, truyền `MockHttpSession` có thể khiến test dựa vào session do mock Servlet request cung cấp. Nó không chứng minh rằng cookie do Spring Session phát ra có thể được dùng để tải dữ liệu từ Redis/JDBC.

Phân biệt:

| Cách kiểm thử | Điều được kiểm tra |
|---|---|
| `.session(mockHttpSession)` | Controller xử lý thuộc tính trong mock session được gắn vào request |
| Request 1 tạo session, lấy `Set-Cookie`, request 2 gửi `.cookie(cookie)` | Đường đi session ID qua filter và repository |
| Dùng repository test thật | Cả filter path và khả năng lưu trữ của backend được kiểm tra |

`MockHttpSession` vẫn hữu ích cho các test controller tập trung vào logic session đơn giản. Chỉ cần không xem nó là bằng chứng thay thế cho round-trip Spring Session.

## 8. Kiểm tra filter thực sự được áp dụng

Một test round-trip thành công là bằng chứng hành vi tốt hơn việc chỉ kiểm tra bean tồn tại. Có thể bổ sung một số kiểm tra cấu hình:

- Application context có bean `SessionRepositoryFilter` đúng loại.
- MockMvc được cấu hình với `addFilters = true` hoặc filter được thêm tường minh.
- Filter chain có `SessionRepositoryFilter` trước các filter cần dùng `HttpSession`, đặc biệt là Spring Security.
- Response khi tạo session có `Set-Cookie` với tên và thuộc tính đúng.
- Request tiếp theo gửi cookie và đọc được dữ liệu.

Không nên chỉ assert rằng một bean filter tồn tại. Filter có thể tồn tại nhưng chưa được đăng ký vào MockMvc, hoặc thứ tự filter không đúng. Kiểm tra end-to-end qua request cookie mới xác minh hành vi tích hợp.

### 8.1. Thứ tự filter

`SessionRepositoryFilter` cần chạy trước các filter khác có truy cập `HttpSession`, để những filter đó nhìn thấy session do Spring Session quản lý. Spring Security thường cần session để lưu SecurityContext, áp dụng session fixation protection hoặc thực hiện logout.

Trong ứng dụng Boot, auto-configuration của Spring Session thiết lập thứ tự filter phù hợp. Khi tự dựng MockMvc hoặc thêm filter thủ công, hãy giữ thứ tự tương đương. Nếu thêm security filter trước session filter, một phần request có thể sử dụng session container thay vì repository.

Không thêm filter hai lần. Một filter được đăng ký tự động trong context và đồng thời được thêm thủ công vào MockMvc có thể chạy lặp, tạo hành vi khó dự đoán.

## 9. Kiểm thử khi Spring Security bật CSRF

Khi ứng dụng dùng Spring Security, POST có thể bị từ chối nếu thiếu CSRF token. Test phải giữ security filter chain để kiểm tra cấu hình thực tế, đồng thời thêm token hợp lệ cho request dự định thành công.

Ví dụ với Spring Security Test:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

mockMvc.perform(post("/test/session/value")
        .with(csrf())
        .param("value", "alpha"))
    .andExpect(status().isOk());
~~~

Để kiểm tra CSRF filter đang hoạt động, gửi POST thiếu token:

~~~java
mockMvc.perform(post("/test/session/value")
        .param("value", "alpha"))
    .andExpect(status().isForbidden());
~~~

Hai ví dụ này giả định endpoint đã được cấu hình quyền truy cập phù hợp và dependency `spring-security-test` có trong test scope. Nếu endpoint yêu cầu authentication, bổ sung user test, ví dụ `.with(user("tester"))` hoặc annotation phù hợp.

Không tắt CSRF chỉ để test session dễ pass. Nếu ứng dụng xác thực bằng cookie, CSRF là một phần của cấu hình bảo mật cần được kiểm chứng.

## 10. Kiểm tra invalidate và cookie hết hạn

Khi logout hoặc gọi `session.invalidate()`, Spring Session cần xóa phiên ở repository. Response cũng thường phát cookie hết hạn để trình duyệt ngừng gửi session ID cũ.

Test có thể thực hiện:

1. Tạo session và lấy cookie.
2. Gửi POST invalidate với cookie và CSRF token nếu Spring Security bật.
3. Kiểm tra response status và header `Set-Cookie` theo cookie serializer.
4. Gửi request đọc với cookie cũ.
5. Xác minh session không còn thuộc tính cũ; endpoint trả 404 hoặc tạo phiên mới chỉ khi code chủ động yêu cầu.

Không chỉ assert cookie đã hết hạn. Cookie là trạng thái phía trình duyệt; repository phải xóa hoặc vô hiệu hóa session ở phía server. Một client vẫn có thể gửi lại cookie cũ bằng HTTP client tự viết.

## 11. Kiểm tra nhiều request và cập nhật session

MockMvc có thể gửi nhiều request liên tiếp với cùng cookie để kiểm tra trạng thái được giữ qua các request:

- Request A ghi `theme=dark`.
- Request B đọc `theme`.
- Request C đổi thành `theme=light`.
- Request D xác nhận giá trị mới.

Đối với test cạnh tranh, phát nhiều request song song với cùng cookie và xác minh invariant. MockMvc là API đồng bộ, nhưng có thể được gọi từ nhiều thread trong test. Dù vậy, kiểm tra hành vi production ở nhiều instance vẫn nên dùng server/container và shared store thật.

Không giả định `HttpSession` tự cung cấp atomic read-modify-write. Một test có thể chứng minh dữ liệu được lưu và tải lại nhưng không chứng minh bộ đếm hoặc chuỗi kiểm tra-cập nhật là nguyên tử. Với quy tắc nghiệp vụ, test phải kiểm tra cơ chế đồng bộ ở database hoặc Redis.

## 12. Cookie flags và giới hạn của MockMvc

MockMvc có thể kiểm tra header `Set-Cookie` mà ứng dụng phát ra:

~~~java
mockMvc.perform(post("/test/session/value")
        .with(csrf())
        .param("value", "alpha"))
    .andExpect(status().isOk())
    .andExpect(header().string(
            "Set-Cookie",
            org.hamcrest.Matchers.containsString("HttpOnly")));
~~~

Có thể kiểm tra thêm `Secure`, `SameSite`, `Path` và tên cookie theo cấu hình. Tuy nhiên MockMvc không thực thi chính sách cookie của trình duyệt. Nó không quyết định trình duyệt có gửi cookie trong iframe, cross-site POST hoặc điều hướng top-level hay không.

Vì vậy:

- MockMvc kiểm tra server phát header cookie đúng.
- Browser automation kiểm tra trình duyệt lưu và gửi cookie theo `SameSite`, `Secure`, `Domain` và `Path`.
- Test chạy HTTPS thật hoặc môi trường proxy gần production để kiểm tra `Secure` và forwarded headers.

Không dùng MockMvc để kết luận cookie `SameSite=Lax` đã chặn một request CSRF trong trình duyệt. Đó là hành vi của browser và cần browser test.

## 13. Kiểm tra session repository và dữ liệu backend

Khi test với JDBC, có thể truy vấn repository hoặc database test để xác nhận session record được tạo và xóa. Tuy nhiên nên ưu tiên kiểm tra qua HTTP round-trip; SQL trực tiếp là kiểm tra bổ sung cho lỗi schema hoặc persistence.

Khi test với Redis, có thể dùng repository API hoặc kiểm tra key trong Redis test instance. Tránh gắn test vào cấu trúc key nội bộ nếu không cần, vì namespace và serialization có thể thay đổi theo phiên bản/cấu hình.

Những gì cần kiểm chứng:

- Session ID được phát ra và có thể tải lại.
- Thuộc tính được serialize và deserialize đúng.
- Timeout/inactivity được áp dụng theo cấu hình.
- Invalidate xóa hoặc vô hiệu hóa phiên.
- Lỗi backend được thể hiện rõ thay vì bị hiểu nhầm là session không tồn tại.
- Hai application context dùng cùng backend có thể đọc cùng phiên.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Test controller pass nhưng session không tồn tại trong Redis/JDBC | MockMvc bỏ qua filter hoặc dùng mock session | Bật filter và kiểm tra bằng cookie round-trip |
| POST trả 403 ngoài dự kiến | Spring Security CSRF filter đang hoạt động nhưng test thiếu token | Dùng `.with(csrf())` cho request hợp lệ; giữ test thiếu token riêng |
| Response không có cookie session | Controller chưa tạo session, cookie serializer đổi tên hoặc filter không chạy | Kiểm tra endpoint, filter chain và cookie name |
| Request sau không đọc được thuộc tính | Cookie không được gửi, session chưa được lưu hoặc repository khác nhau | Dùng cookie lấy từ response và xác minh backend |
| `standaloneSetup` không dùng Spring Session | Test không nạp đầy đủ application context/filter | Dùng `webAppContextSetup` hoặc Spring Boot MockMvc integration |
| Dùng `.session(MockHttpSession)` rồi kết luận repository hoạt động | Test dựa trên mock Servlet session | Kiểm tra bằng cookie round-trip qua repository thật |
| Session filter chạy hai lần | Filter vừa auto-register vừa add thủ công | Chỉ đăng ký một lần trong đúng thứ tự |
| Security filter thấy session khác | Filter order không tương đương production | Đặt `SessionRepositoryFilter` trước filter cần `HttpSession` |
| Test cookie SameSite pass nhưng browser vẫn gửi khác dự kiến | MockMvc không thực thi browser cookie policy | Chạy browser automation trên trình duyệt mục tiêu |

## 15. Checklist cho MockMvc với Spring Session

- [ ] Dùng `@SpringBootTest` và `@AutoConfigureMockMvc(addFilters = true)` khi cần full filter chain.
- [ ] Nếu dùng `webAppContextSetup`, thêm filter thực tế đúng thứ tự.
- [ ] Không dùng `standaloneSetup` làm bằng chứng cho session persistence nếu không gắn filter thật.
- [ ] Dùng repository test phù hợp: JDBC, Redis hoặc in-memory theo mục tiêu.
- [ ] Request đầu tiên tạo session và trả cookie.
- [ ] Request tiếp theo gửi cookie đó, không truyền lại `MockHttpSession`.
- [ ] Kiểm tra thuộc tính được lưu và tải lại.
- [ ] Kiểm tra invalidate và cookie hết hạn.
- [ ] Giữ Spring Security filter chain và kiểm thử CSRF token.
- [ ] Xác minh `SessionRepositoryFilter` đứng trước filter cần dùng `HttpSession`.
- [ ] Kiểm tra `Set-Cookie` flags nhưng dùng browser test cho hành vi thực tế.
- [ ] Không gắn test vào cấu trúc key nội bộ của Redis nếu không cần.
- [ ] Có integration test với backend thật và nhiều instance cho các luồng quan trọng.

MockMvc chỉ kiểm chứng Spring Session khi request đi qua `SessionRepositoryFilter` và repository được cấu hình trong application context. Hãy tạo session ở request đầu, lấy cookie từ response, gửi cookie ở request tiếp theo và xác minh thuộc tính được tải lại từ repository. Kết hợp filter chain thực tế, Spring Security/CSRF và backend test phù hợp; dùng browser test bổ sung cho chính sách cookie mà MockMvc không mô phỏng.

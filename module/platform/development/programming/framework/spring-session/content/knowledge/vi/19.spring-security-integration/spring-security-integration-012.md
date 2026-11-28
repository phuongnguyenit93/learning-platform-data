# Kiểm thử đăng nhập, truy cập được bảo vệ và đăng xuất trên nhiều nút

## Mục tiêu bài học

Khi ứng dụng Spring Session chạy trên nhiều instance, người dùng có thể đăng nhập ở nút A, gửi request tiếp theo đến nút B rồi đăng xuất ở nút C. Nếu các nút cùng dùng một kho session chia sẻ như Redis hoặc JDBC, trạng thái xác thực phải được khôi phục nhất quán ở mọi nút.

Một bài kiểm thử chỉ chạy trên một instance không chứng minh được điều đó. Cần kiểm tra luồng đăng nhập, truy cập tài nguyên được bảo vệ, đổi Session ID sau xác thực, logout và việc ID cũ mất hiệu lực khi request được chuyển giữa các nút.

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa Spring Security, HttpSession và Spring Session repository.
- Thiết kế kiểm thử đăng nhập ở nút A và truy cập được bảo vệ ở nút B.
- Xác minh SecurityContext được lưu và khôi phục qua Redis hoặc JDBC.
- Kiểm thử Session ID sau authentication và hành vi session fixation protection.
- Đăng xuất ở một nút rồi xác minh phiên bị vô hiệu hóa trên nút khác.
- Phân biệt kiểm thử MockMvc trong một application context với kiểm thử nhiều instance thực tế.
- Xử lý CSRF token, cookie, redirect và response theo cấu hình bảo mật.
- Phát hiện lỗi do namespace, serializer, filter order, DataSource hoặc repository không đồng nhất.

## 1. Vì sao phải kiểm thử qua nhiều nút?

Trong kiến trúc nhiều instance, load balancer phân phối request đến một trong các ứng dụng đang chạy. Session không thể chỉ nằm trong bộ nhớ cục bộ của một JVM nếu request tiếp theo có thể đến instance khác.

Ví dụ người dùng đăng nhập ở A rồi được chuyển đến B:

~~~text
                Load balancer
                /           \
               v             v
          Application A  Application B
               |             |
               +------+------+
                      |
                      v
              Shared session store
                 Redis / JDBC
~~~

Nếu session được lưu đúng cách:

1. Request đăng nhập đến A.
2. Spring Security xác thực thông tin người dùng.
3. Session fixation protection đổi Session ID nếu cần.
4. Spring Session ghi trạng thái phiên và SecurityContext vào repository dùng chung.
5. Response trả cookie hoặc định danh mới cho client.
6. Request tiếp theo mang định danh đó đến B.
7. B đọc session từ repository và khôi phục trạng thái xác thực.
8. Khi logout tại B, repository xóa hoặc vô hiệu hóa session.
9. Request sau đó gửi ID cũ đến A cũng không còn được xác thực.

Nếu ứng dụng chỉ dùng session trong bộ nhớ, A có thể xác thực thành công nhưng B không biết người dùng đã đăng nhập. Đây là lỗi thường gặp khi chuyển từ một instance sang nhiều instance mà chưa cấu hình Spring Session đúng.

### Ba hành vi cần chứng minh

| Hành vi | Bằng chứng cần có |
|---|---|
| Đăng nhập | Authentication thành công và response mang định danh phiên hiện hành |
| Truy cập được bảo vệ | Một nút khác khôi phục SecurityContext và cho phép truy cập |
| Đăng xuất | Sau khi logout tại một nút, mọi nút dùng chung repository đều từ chối phiên cũ |

Kiểm thử phải xác minh trạng thái phía server, không chỉ kiểm tra response có status 200 hoặc cookie có xuất hiện.

## 2. Spring Security lưu trạng thái xác thực ở đâu?

Trong ứng dụng Servlet, Spring Security lưu trạng thái xác thực trong `SecurityContext`. Với cấu hình session-based thông thường, `SecurityContextRepository` phối hợp với `HttpSession` để lưu và tải SecurityContext giữa các request.

Spring Session thay nơi quản lý HttpSession bằng repository dùng chung. Controller và Spring Security tiếp tục sử dụng Servlet API, còn dữ liệu session được lưu trong Redis hoặc JDBC.

Luồng đọc trạng thái xác thực:

1. Client gửi cookie chứa Session ID.
2. `SessionRepositoryFilter` đọc định danh và tải session từ repository.
3. Spring Security filter chain truy cập HttpSession đã được bọc.
4. `SecurityContextRepository` tải SecurityContext đã lưu trong session.
5. Authorization filter kiểm tra quyền truy cập.
6. Nếu người dùng có quyền, request được chuyển đến controller.

Luồng ghi trạng thái sau login:

1. Authentication filter xác thực credential.
2. Session authentication strategy thực hiện các chính sách session, chẳng hạn đổi ID.
3. SecurityContext được lưu theo cấu hình của Spring Security.
4. Spring Session ghi session vào repository.
5. Resolver gửi Session ID hiện hành về client.

### Vai trò của các thành phần

| Thành phần | Trách nhiệm |
|---|---|
| Spring Security filter chain | Xác thực và phân quyền request |
| `SecurityContext` | Giữ Authentication hiện tại |
| `SecurityContextRepository` | Lưu và tải SecurityContext |
| `HttpSession` | Giao diện session của Servlet |
| `SessionRepositoryFilter` | Chuyển thao tác HttpSession sang Spring Session |
| Redis/JDBC repository | Lưu trạng thái session dùng chung |
| Session ID resolver | Đọc và gửi định danh qua cookie hoặc header |

Nếu Spring Security lưu SecurityContext vào session cục bộ của container thay vì session được Spring Session quản lý, nút B sẽ không khôi phục được trạng thái từ Redis/JDBC. Vì vậy, thứ tự filter và cấu hình tích hợp phải được xác minh.

## 3. Xây dựng kịch bản kiểm thử chuẩn

Một kịch bản cơ bản nên có ít nhất hai instance ứng dụng độc lập, A và B, cùng kết nối đến một repository session.

Chuỗi hành động:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Node A
    participant S as Shared Redis/JDBC
    participant B as Node B

    C->>A: GET /login
    A-->>C: Trang login và CSRF token
    C->>A: POST /login
    A->>S: Lưu session và SecurityContext
    A-->>C: Cookie Session ID mới
    C->>B: GET /api/me + cookie mới
    B->>S: Tải session
    S-->>B: Session và SecurityContext
    B-->>C: 200 / thông tin người dùng
    C->>B: POST /logout + CSRF token
    B->>S: Invalidate / xóa session
    B-->>C: Logout thành công
    C->>A: GET /api/me + ID cũ
    A->>S: Tìm session cũ
    S-->>A: Không còn session hợp lệ
    A-->>C: 401 hoặc redirect đến login
~~~

Nên kiểm thử theo đúng thứ tự này để xác định lỗi nằm ở login, lưu session, khôi phục session hay logout.

### Chuẩn bị hai nút

Hai nút cần:

- Chạy cùng phiên bản ứng dụng hoặc phiên bản được xác nhận tương thích.
- Dùng cùng Redis deployment hoặc cùng database session.
- Dùng cùng namespace Redis hoặc cùng schema/table JDBC.
- Dùng cùng serializer và định dạng thuộc tính.
- Dùng cùng cookie name, path, domain và resolver.
- Dùng cùng cấu hình Spring Security và authentication provider.
- Có cấu hình CSRF phù hợp với client.
- Không phụ thuộc sticky session để bài test chứng minh kho session dùng chung.

Có thể chạy hai application context trên hai cổng khác nhau trong cùng tiến trình để kiểm thử nhanh. Để kiểm tra hành vi sát production hơn, nên chạy hai JVM/container riêng, vì chúng có bộ nhớ, connection pool và vòng đời độc lập.

## 4. Chuẩn bị endpoint kiểm thử

Ứng dụng cần có một endpoint yêu cầu xác thực, chẳng hạn:

~~~java
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "status", "authenticated"
        );
    }
}
~~~

Endpoint này chỉ trả thông tin người dùng hiện tại. Nó không nhận username từ request để quyết định danh tính. Danh tính lấy từ `Authentication` do Spring Security cung cấp.

Cấu hình bảo mật ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/login", "/csrf").permitAll()
                        .anyRequest().authenticated()
                )
                .formLogin(Customizer.withDefaults())
                .logout(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation -> fixation.changeSessionId())
                )
                .build();
    }
}
~~~

Đây là cấu hình minh họa cho form login. Ứng dụng thực tế có thể dùng authentication provider, user service hoặc custom login endpoint khác. Cần giữ CSRF protection nếu client dùng cookie tự động gửi theo request.

Endpoint `/api/me` phải được bảo vệ. Nếu cấu hình cho phép truy cập ẩn danh, bài test không thể chứng minh trạng thái xác thực đã được khôi phục.

### Endpoint CSRF cho test HTTP

Với kiểm thử qua HTTP thật, client cần lấy CSRF token theo cơ chế ứng dụng. Có thể tạo endpoint chỉ phục vụ môi trường test để trả token hiện tại:

~~~java
import java.util.Map;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfTestController {

    @GetMapping("/csrf")
    public Map<String, String> csrf(CsrfToken token) {
        return Map.of(
                "headerName", token.getHeaderName(),
                "parameterName", token.getParameterName(),
                "token", token.getToken()
        );
    }
}
~~~

Chỉ expose endpoint dạng này trong test hoặc môi trường được bảo vệ. Không cần tạo endpoint CSRF riêng trong production nếu ứng dụng đã có cơ chế phát token phù hợp cho frontend.

CSRF token có thể được gắn với session. Vì vậy, client phải giữ cookie và gửi token tương ứng khi POST login hoặc logout. Không lấy token từ một session rồi dùng cùng token với một session khác.

## 5. Kiểm thử đăng nhập trên nút A

Đăng nhập cần xác minh nhiều hơn việc endpoint login trả redirect hoặc response thành công.

Các điều cần xác minh:

- Credential hợp lệ được chấp nhận.
- Credential sai bị từ chối.
- Authentication được lưu trong SecurityContext.
- Session ID được tạo hoặc đổi theo session fixation strategy.
- Response gửi cookie/định danh hiện hành.
- Session được ghi vào repository dùng chung.
- Không ghi credential hoặc Session ID vào log.

### Kiểm thử với MockMvc trong một nút

MockMvc phù hợp để kiểm tra security filter chain và hành vi login ở một application context:

~~~java
MvcResult result = mockMvc.perform(post("/login")
        .with(csrf())
        .param("username", "alice")
        .param("password", "correct-password"))
    .andReturn();

assertThat(result.getResponse().getStatus())
        .isIn(302, 303);
~~~

Status cụ thể phụ thuộc success handler và cấu hình ứng dụng. Test đầy đủ nên kiểm tra redirect URL hoặc response body theo hợp đồng login của ứng dụng.

MockMvc không tự chứng minh request tiếp theo được xử lý bởi instance khác. Nó là test ở mức filter chain trong một context.

### Kiểm tra Session ID sau login

Nếu dùng cookie resolver, đọc cookie từ response login. Cookie có thể được tạo từ request trước login rồi được thay giá trị sau session fixation protection.

Nên lưu riêng:

- Cookie trước đăng nhập, nếu test có tạo session ẩn danh.
- Cookie sau đăng nhập.
- CSRF token dùng cho logout.

Không lấy ID trước login làm cookie chính cho các request đã xác thực. ID sau login mới là định danh cần được client sử dụng.

Nếu cấu hình dùng header resolver, thay thao tác đọc cookie bằng đọc response header tương ứng và gửi lại header đó trong request tiếp theo.

## 6. Kiểm thử truy cập được bảo vệ trên nút B

Sau khi login tại A, giữ nguyên Session ID mới và gửi request đến B.

Kết quả mong đợi:

- B tải được session từ repository dùng chung.
- Spring Security khôi phục Authentication.
- Endpoint được bảo vệ trả response thành công.
- Username trả về khớp người dùng đã đăng nhập.
- Không cần login lại chỉ vì request chuyển nút.

Ví dụ request:

~~~http
GET /api/me HTTP/1.1
Host: node-b.example.test
Cookie: SESSION=<session-id-after-login>
~~~

Kết quả mong đợi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

Response body minh họa:

~~~json
{
  "username": "alice",
  "status": "authenticated"
}
~~~

Tên cookie và cấu trúc response phải khớp ứng dụng. Không ghi giá trị Session ID vào log kiểm thử; nếu cần đối chiếu, giữ trong bộ nhớ test hoặc dùng mã tham chiếu đã che.

### Kiểm tra request ẩn danh

Gửi request đến B không có cookie/ID:

~~~http
GET /api/me HTTP/1.1
Host: node-b.example.test
~~~

Nếu endpoint yêu cầu xác thực, kết quả thường là 401 hoặc redirect đến trang login tùy authentication entry point. Test phải chấp nhận đúng hợp đồng đã cấu hình, nhưng không được chấp nhận 200 với danh tính giả hoặc nội dung được bảo vệ.

### Kiểm tra người dùng và quyền

Không chỉ kiểm tra có Authentication. Hãy xác minh:

- Username/principal đúng.
- Role hoặc authority cần thiết được khôi phục.
- Người dùng không có quyền bị từ chối.
- Một request có Session ID hợp lệ nhưng quyền không đủ vẫn bị 403 hoặc xử lý theo policy.
- Session không bị chia sẻ nhầm giữa hai người dùng.

Nếu session chứa custom principal hoặc authority object, serializer và class version phải tương thích trên cả A và B.

## 7. Kiểm thử logout tại nút B

Logout cần kết thúc phiên phía server và yêu cầu client ngừng sử dụng định danh cũ.

Với cấu hình logout mặc định của Spring Security, endpoint thường là POST /logout khi CSRF được bật. Request phải mang CSRF token hợp lệ.

Luồng:

1. Client gửi request logout đến B cùng cookie session hiện tại.
2. Spring Security xác nhận CSRF token.
3. Logout handler xóa SecurityContext.
4. HttpSession bị invalidate theo cấu hình.
5. Spring Session repository xóa hoặc đánh dấu session đã kết thúc.
6. Response yêu cầu client xóa cookie hoặc định danh.
7. Client xóa cookie khỏi cookie jar.

Không coi việc response gửi cookie hết hạn là bằng chứng duy nhất rằng logout đã hoàn tất. Cần kiểm tra repository và thử lại ID cũ trên một nút khác.

### Vì sao phải giữ bản sao ID cũ trong test?

Trình duyệt thường xóa cookie sau response logout. Nếu test chỉ dùng cookie jar đã được cập nhật, request tiếp theo không gửi ID nào cả. Khi đó, test chỉ chứng minh client đã xóa cookie, chưa chứng minh server đã vô hiệu hóa session.

Để kiểm tra server-side invalidation:

1. Sao lưu cookie session hợp lệ sau login vào biến test riêng.
2. Gửi logout ở B bằng cookie đó.
3. Giữ bản sao ID cũ trong bộ nhớ test.
4. Gửi request đến A với ID cũ.
5. Xác minh A không khôi phục được Authentication.

Bản sao này chỉ dùng trong test và phải được giữ kín như credential. Không đưa vào artifact, log hoặc báo cáo.

## 8. Xác minh ID cũ mất hiệu lực trên nút A

Sau khi logout ở B, gửi lại request được bảo vệ đến A bằng Session ID cũ đã lưu trước đó.

Kết quả mong đợi:

- Repository không còn trả session đã xác thực cho ID cũ.
- SecurityContext không được khôi phục.
- Endpoint được bảo vệ từ chối request hoặc chuyển hướng đến login.
- Không có instance nào tiếp tục chấp nhận phiên đã logout.

Ví dụ:

~~~text
POST http://node-b.example.test/logout
Cookie: SESSION=<authenticated-session-id>
X-CSRF-TOKEN: <valid-token>

GET http://node-a.example.test/api/me
Cookie: SESSION=<same-old-session-id>
~~~

Request cuối phải bị từ chối theo authentication entry point. Nếu A vẫn trả thông tin người dùng, cần điều tra việc repository có thực sự dùng chung, logout có invalidate session và SecurityContext có được lưu trong session đó hay không.

### Không chỉ kiểm tra nút đã logout

Một lỗi phổ biến là logout làm mất session trong bộ nhớ của B nhưng session trong Redis/JDBC vẫn tồn tại hoặc A đang dùng một repository khác. Vì vậy, test phải gửi ID cũ đến ít nhất một instance khác sau logout.

Nếu có ba hoặc nhiều instance, có thể chạy cùng assertion trên từng nút hoặc luân phiên request qua load balancer để xác minh toàn cụm.

## 9. Kiểm thử bằng hai application context

Một cách kiểm thử tự động là khởi động hai application context độc lập cùng kết nối một Redis hoặc database test.

Ví dụ mô hình:

~~~text
Test process
  |
  +-- ApplicationContext A : port 18081
  |       |
  |       +-- Spring Security
  |       +-- Spring Session
  |       +-- Shared Redis/JDBC
  |
  +-- ApplicationContext B : port 18082
          |
          +-- Spring Security
          +-- Spring Session
          +-- Shared Redis/JDBC
~~~

Hai context phải có:

- Cấu hình security tương đương.
- Cùng session repository backend.
- Cùng namespace/schema.
- Cùng serializer.
- Cookie resolver giống nhau.
- Authentication provider có cùng dữ liệu người dùng.

Có thể dùng hai cổng ngẫu nhiên hoặc hai cổng được cấp riêng. Không để test vô tình gửi cả hai request đến cùng một cổng vì load balancer hoặc test client có thể che mất lỗi multi-node.

### Ví dụ cấu trúc test

Đoạn sau mô tả thứ tự kiểm tra. Các hàm client là helper do test suite triển khai để gửi HTTP request và quản lý cookie/CSRF:

~~~java
@Test
void loginOnA_accessOnB_logoutOnB_invalidatesOnA() {
    LoginResult login = clientA.login("alice", "correct-password");

    String authenticatedCookie = login.sessionCookie();
    assertThat(authenticatedCookie).isNotBlank();

    ProtectedResult onB =
            clientB.getProtected(authenticatedCookie);

    assertThat(onB.status()).isEqualTo(200);
    assertThat(onB.username()).isEqualTo("alice");

    clientB.logout(
            authenticatedCookie,
            login.csrfTokenForLogout()
    );

    ProtectedResult afterLogout =
            clientA.getProtected(authenticatedCookie);

    assertThat(afterLogout.status()).isIn(401, 302);
}
~~~

Đây là cấu trúc minh họa, không phải một test class hoàn chỉnh có thể chạy nguyên trạng. LoginResult, ProtectedResult và HTTP client là helper của dự án. Trong test thực tế, CSRF token cho logout phải thuộc đúng session hiện hành và được lấy theo cơ chế của ứng dụng.

Nên bổ sung kiểm tra rằng ID sau login khác ID trước login nếu ứng dụng tạo session ẩn danh trước khi xác thực.

## 10. Kiểm thử với Redis

Khi dùng Redis, hai instance phải dùng cùng Redis deployment và namespace.

Các điểm cần xác minh:

- Session key được ghi sau login.
- B tải được session bằng ID từ response của A.
- Logout xóa hoặc vô hiệu hóa session.
- A không thể tải lại session cũ sau logout.
- TTL phù hợp với session timeout.
- Serializer giống nhau giữa hai instance.
- Redis connection và namespace không bị cấu hình khác theo profile.

Có thể dùng Testcontainers để khởi động Redis riêng cho test. Nếu test tạo hai application context, cả hai phải trỏ cùng container và cùng database/namespace.

Không dùng mock Redis nếu mục tiêu là xác minh repository thật. Mock có thể giúp unit test logic, nhưng không kiểm tra serialization, TTL, key namespace hoặc hành vi Redis repository.

### Kiểm tra TTL

Session timeout và TTL Redis có liên quan nhưng không hoàn toàn đồng nghĩa. Test có thể đọc TTL của key session cụ thể bằng Redis client hoặc redis-cli, nhưng phải biết đúng key pattern của phiên bản Spring Session đang dùng.

Không phụ thuộc vào tên key nội bộ cố định trong test lâu dài nếu schema repository có thể thay đổi giữa các phiên bản. Ưu tiên xác minh session qua repository API và chỉ dùng kiểm tra key/TTL như một assertion bổ sung.

## 11. Kiểm thử với JDBC

Khi dùng Spring Session JDBC, hai instance phải dùng cùng database, schema, table name và DataSource có quyền phù hợp.

Các điểm cần xác minh:

- Login tạo hoặc cập nhật hàng session.
- Các thuộc tính và SecurityContext được lưu trong bảng thuộc tính.
- B có thể tải session bằng Session ID.
- Logout invalidate session trong database.
- A không thể khôi phục Authentication từ ID cũ.
- Cleanup hết hạn hoạt động theo cấu hình.
- Transaction và connection pool đủ cho hai instance.

Dùng database test cùng hệ quản trị production hoặc Testcontainers. H2 có thể hữu ích cho test nhanh nhưng không đại diện đầy đủ cho kiểu BLOB, transaction, locking và JDBC driver của PostgreSQL, MySQL, SQL Server hoặc Oracle.

Không tự xóa hàng session bằng SQL trong test để mô phỏng logout. Hãy gọi endpoint logout và kiểm tra kết quả qua ứng dụng; SQL chỉ nên dùng để quan sát dữ liệu test nếu cần.

## 12. CSRF, cookie và client test

Khi xác thực dựa trên cookie, trình duyệt tự động gửi cookie theo phạm vi domain/path và chính sách SameSite. Do đó, POST login, logout hoặc request thay đổi trạng thái có thể cần CSRF token.

Test cần phân biệt:

- Cookie session: định danh phiên.
- CSRF token: chứng minh request thay đổi trạng thái có token hợp lệ.
- Authentication: danh tính đã được xác thực.
- Authorization: danh tính có quyền thực hiện hành động.

Một Session ID hợp lệ không thay thế CSRF token. Một CSRF token hợp lệ cũng không chứng minh người dùng đã xác thực.

### Kiểm thử cookie

Xác minh các thuộc tính phù hợp:

- Cookie name nhất quán giữa các instance.
- Path và Domain đúng.
- Secure được bật trong HTTPS production.
- HttpOnly được bật nếu frontend không cần đọc cookie.
- SameSite phù hợp luồng điều hướng và cross-site.
- Response login cập nhật ID sau session fixation protection.
- Response logout yêu cầu xóa cookie.

Trong test local HTTP, cookie Secure có thể không được gửi bởi một số client. Có thể dùng cấu hình test riêng, nhưng phải có test HTTPS hoặc kiểm tra cấu hình production để xác minh Secure không bị tắt ngoài ý muốn.

### Kiểm thử header resolver

Nếu ứng dụng dùng header resolver thay cookie:

1. Lấy Session ID từ response header sau login.
2. Gửi header đó đến nút B.
3. Gửi logout đến B.
4. Gửi lại cùng ID cũ đến A.
5. Xác minh request bị từ chối.

Không giả định client sẽ tự quản lý header như trình duyệt quản lý cookie. Test phải tự lưu và gửi lại giá trị header theo giao thức ứng dụng.

## 13. Kiểm thử session fixation và logout cùng nhau

Session fixation protection và logout cần được kiểm thử trong cùng một luồng vì chúng liên quan trực tiếp đến định danh.

Một kịch bản đầy đủ:

1. Truy cập trang login tại A để tạo session ẩn danh nếu ứng dụng có hành vi đó.
2. Lưu Session ID trước login.
3. Đăng nhập hợp lệ tại A.
4. Xác minh Session ID sau login khác ID trước login khi chiến lược đổi ID được áp dụng.
5. Dùng ID mới truy cập endpoint bảo vệ tại B.
6. Đăng xuất tại B.
7. Dùng lại ID mới đã lưu trong test để truy cập A.
8. Xác minh request không còn Authentication.
9. Thử ID trước login và xác minh ID đó cũng không thể truy cập phiên đã xác thực.

Không nên chỉ kiểm tra cookie bị đổi mà bỏ qua quyền truy cập. Điều cần chứng minh là định danh mới đại diện cho phiên đã xác thực, còn định danh cũ không thể tiếp tục dùng để chiếm phiên.

## 14. Kiểm thử lỗi và tình huống biên

| Tình huống | Kết quả mong đợi |
|---|---|
| Sai mật khẩu tại A | Không tạo Authentication hợp lệ |
| Không gửi cookie đến B | Request bảo vệ bị từ chối |
| Gửi ID không tồn tại | Không khôi phục được session |
| Session hết hạn trước request đến B | B yêu cầu xác thực lại |
| Logout bằng CSRF token sai | Logout bị từ chối theo CSRF policy |
| Logout hai lần | Lần sau không làm phiên sống lại |
| Request đến A sau logout tại B | ID cũ không còn được xác thực |
| Redis/JDBC tạm thời không khả dụng | Request session xử lý lỗi theo policy, không giả lập local session |
| Serializer không tương thích | Lỗi được phát hiện, không trả danh tính sai |
| Cookie name khác giữa A và B | Test phát hiện B không khôi phục được phiên |

### Logout lặp lại

Một logout request có thể được gửi lại do client retry hoặc mạng mất response. Hãy xác minh hành vi khi session đã bị invalidate. Ứng dụng không nên khôi phục session chỉ vì logout được gọi lần hai.

### Redis hoặc database lỗi

Nếu kho session không khả dụng, ứng dụng không thể xác minh trạng thái phiên dùng chung. Không nên chuyển âm thầm sang session local vì điều đó tạo ra hành vi không nhất quán giữa các nút.

Test cần xác minh ứng dụng trả lỗi phù hợp, ghi nhận metric và không cấp quyền dựa trên trạng thái cũ không thể kiểm tra.

## 15. Chạy test không phụ thuộc sticky session

Sticky session có thể khiến mọi request của một client luôn đến cùng instance. Điều đó hữu ích trong một số kiến trúc, nhưng không chứng minh Spring Session đang chia sẻ trạng thái giữa các nút.

Để kiểm thử đúng:

- Gọi trực tiếp địa chỉ/cổng của A và B trong test.
- Hoặc cấu hình load balancer test có thể ép request luân phiên.
- Xác minh request sau login thật sự đến nút khác.
- Ghi lại node identifier trong response test, không ghi Session ID.
- Không dựa vào cookie affinity của load balancer để giữ client ở A.

Một header như `X-Test-Node` chỉ nên được bật trong test để xác nhận request đã đến đúng instance. Không expose thông tin topology nội bộ ra production response nếu không cần.

## 16. Những lỗi thường gặp và cách điều tra

**Login thành công ở A nhưng B chuyển hướng về login.**  
Kiểm tra B có dùng cùng Redis/JDBC repository, namespace/schema, serializer, Session ID resolver và cookie name không. Xác minh SecurityContext đã được lưu trong session dùng chung.

**B đọc được session nhưng username không đúng.**  
Kiểm tra custom principal, serializer, authentication provider và dữ liệu người dùng giữa các instance. Không chỉ kiểm tra session ID có tồn tại.

**Logout ở B nhưng A vẫn chấp nhận ID cũ.**  
Kiểm tra logout có thực sự invalidate session, SecurityContext có được xóa và repository có được chia sẻ không. Xác minh request logout đã gửi CSRF token hợp lệ và handler đã chạy.

**Cookie mới không được lưu sau login.**  
Kiểm tra session fixation strategy, resolver, Set-Cookie, cookie path/domain, Secure và client cookie jar.

**MockMvc test pass nhưng multi-node test fail.**  
MockMvc chạy trong một application context và có thể dùng mock session. Chạy test với hai instance và repository thật để phát hiện cấu hình phân tán.

**Test chỉ pass khi sticky session bật.**  
Một nút có thể đang dùng session trong bộ nhớ local hoặc node khác không có cùng repository. Ép request qua nút khác để kiểm tra.

**Logout bị 403.**  
Kiểm tra CSRF token và cách client gửi token. Không tắt CSRF trong production chỉ để làm test pass.

**ID cũ vẫn được gửi sau logout.**  
Client có thể chưa xóa cookie. Nhưng kể cả ID cũ được gửi lại, server vẫn phải từ chối phiên đã bị invalidate.

**Node A và B dùng cấu hình khác nhau.**  
So sánh profile, environment variables, secret, namespace, serializer, cookie resolver và version dependency.

## 17. Checklist cho CI và staging

Một pipeline kiểm thử session nhiều nút nên có:

- Unit test cho authentication và authorization rule.
- MockMvc test cho login, protected endpoint, logout và CSRF.
- Integration test với Redis hoặc JDBC repository thật.
- Hai application instance hoặc hai application context độc lập.
- Kiểm thử login tại A, truy cập tại B.
- Kiểm thử logout tại B, từ chối ID cũ tại A.
- Kiểm thử session fixation ID trước/sau login.
- Kiểm thử cookie/header resolver.
- Kiểm thử TTL và session expiration.
- Kiểm thử serializer giữa các instance.
- Kiểm thử request không có ID, ID sai và session hết hạn.
- Kiểm thử Redis/database unavailable.
- Kiểm thử không bật sticky session trong kịch bản multi-node.
- Dọn dữ liệu test sau mỗi lần chạy bằng namespace hoặc schema riêng.

Nên có một test smoke chạy trước khi phát hành và một bộ integration test đầy đủ trong CI. Nếu hệ thống có rolling deployment, thêm test phiên bản cũ và mới cùng truy cập repository để kiểm tra tương thích dữ liệu.

## 18. Tự kiểm tra

1. Vì sao một bài test login trên một instance không chứng minh session được chia sẻ?
2. Spring Security lưu trạng thái xác thực vào đâu trong cấu hình session-based thông thường?
3. Vai trò của SessionRepositoryFilter trong luồng request là gì?
4. Sau login tại A, cần kiểm tra gì khi truy cập endpoint được bảo vệ tại B?
5. Vì sao phải giữ bản sao Session ID trước khi logout trong test?
6. Logout tại B cần tạo ra kết quả nào khi ID cũ được gửi lại đến A?
7. Vì sao CSRF token và Session ID là hai giá trị khác nhau?
8. Vì sao test với MockMvc chưa đủ cho kiểm thử nhiều nút?
9. Những cấu hình nào phải giống nhau giữa các instance?
10. Sticky session có thể che giấu lỗi gì?
11. Cần làm gì nếu login thành công nhưng B không khôi phục được SecurityContext?
12. Vì sao không nên chuyển sang local session khi Redis/JDBC tạm thời không khả dụng?

### Gợi ý trả lời

1. Vì request login và request tiếp theo có thể cùng chạy trong một JVM, không chứng minh instance khác đọc được repository dùng chung.
2. Thông thường SecurityContextRepository lưu SecurityContext trong HttpSession.
3. Filter đọc Session ID, tải session và bọc request/response để Servlet API sử dụng Spring Session repository.
4. B phải khôi phục đúng Authentication, username và quyền, rồi cho phép endpoint theo policy.
5. Vì client jar có thể xóa cookie sau logout; giữ bản sao giúp kiểm tra server đã vô hiệu hóa ID cũ.
6. A phải không khôi phục được Authentication và từ chối endpoint được bảo vệ.
7. Session ID định danh phiên; CSRF token bảo vệ request thay đổi trạng thái khỏi request giả mạo.
8. MockMvc thường chạy trong một application context và có thể dùng mock session, không mô phỏng hai node độc lập.
9. Repository endpoint, namespace/schema, serializer, cookie/header resolver, security config và phiên bản tương thích.
10. Sticky session có thể khiến mọi request đến cùng node, che giấu việc session chưa được chia sẻ.
11. Kiểm tra repository, namespace, serializer, SecurityContext persistence, filter order và cookie.
12. Vì local session không chia sẻ giữa các node và có thể tạo trạng thái xác thực không nhất quán.

## Kết luận

Kiểm thử Spring Security trên nhiều nút phải chứng minh một phiên được tạo ở A có thể được khôi phục ở B và bị vô hiệu hóa ở mọi nút sau khi logout. Spring Security lưu Authentication trong SecurityContext; Spring Session tích hợp HttpSession với Redis hoặc JDBC để trạng thái này được chia sẻ. SessionRepositoryFilter, SecurityContextRepository, resolver và repository phải được cấu hình tương thích.

Kịch bản quan trọng nhất là đăng nhập tại A, dùng cookie hoặc header mới truy cập endpoint được bảo vệ tại B, logout tại B rồi gửi lại ID cũ đến A để xác minh bị từ chối. Hãy dùng repository thật, hai instance độc lập, CSRF token hợp lệ và không dựa vào sticky session. MockMvc hữu ích cho filter chain trong một context, nhưng chỉ integration test nhiều nút mới chứng minh được hành vi chia sẻ session trong môi trường phân tán.


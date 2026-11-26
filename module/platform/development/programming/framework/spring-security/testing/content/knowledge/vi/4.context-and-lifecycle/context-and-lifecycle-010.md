# Ngữ cảnh luồng test không tự đi qua HTTP đến máy chủ chạy thật

Một bài test có thể dùng `@WithMockUser(username = "lan")` và đọc được người dùng `lan` từ `SecurityContextHolder`. Nhưng khi bài test gửi một HTTP request tới ứng dụng đang chạy trên cổng thật, controller vẫn có thể nhận request vô danh hoặc trả `401 Unauthorized`. Đây không phải lỗi ngẫu nhiên: context được gắn vào luồng chạy test không tự trở thành dữ liệu của HTTP request.

Trong module **SPRING_SECURITY_TESTING**, bài học thuộc chương **Ngữ cảnh và vòng đời**, giải thích ranh giới giữa context của test thread và context của request server. Điểm này rất quan trọng khi chuyển từ `MockMvc` sang kiểm thử tích hợp với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, `TestRestTemplate` hoặc `WebTestClient.bindToServer()`. Người học cần biết cách gửi credentials, bearer token, cookie hoặc session qua HTTP thật để kiểm chứng xác thực, phân quyền và bảo vệ HTTP trên ứng dụng Servlet/Reactive.

## 1. SecurityContextHolder là trạng thái trong tiến trình, không phải HTTP header

Trên ứng dụng Servlet, `SecurityContextHolder` mặc định sử dụng chiến lược `MODE_THREADLOCAL`. Context được lưu gắn với thread đang xử lý. Khi test dùng `@WithMockUser`, listener của Spring Security Test tạo authentication và đặt context cho thread chạy phương thức test.

~~~text
Thread chạy JUnit
  @WithMockUser("lan")
       │
       ▼
  TestSecurityContextHolder
       │
       └── SecurityContextHolder (ThreadLocal của test thread)
                 │
                 └── test đọc được Authentication "lan"

HTTP request gửi qua socket
       │
       ├── URL
       ├── HTTP method
       ├── headers
       ├── cookies
       └── body
             │
             ▼
       Máy chủ nhận request
             │
             ▼
       Thread xử lý request trên server
             │
             └── SecurityContextHolder riêng của request
~~~

HTTP chỉ truyền dữ liệu nằm trong request: method, URL, header, cookie và body. `SecurityContextHolder` không tự được tuần tự hóa vào request, không tự thêm `Authorization` header và cũng không gửi `JSESSIONID` sang server.

Ngay cả khi test và server chạy trong cùng một JVM, request qua cổng mạng vẫn đi qua ranh giới HTTP và được server xử lý theo vòng đời request của nó. Thread server không tự đọc ThreadLocal của thread JUnit. Vì vậy:

- `@WithMockUser` chứng minh test thread có authentication giả lập.
- `SecurityContextHolder.getContext()` trong test không chứng minh server nhận được người dùng đó.
- Muốn server xác thực request, test phải gửi thông tin mà cơ chế xác thực của server hiểu được.
- Muốn tái sử dụng phiên đăng nhập, client phải giữ và gửi lại cookie/session tương ứng.

## 2. Phân biệt MockMvc với máy chủ chạy thật

Cả `MockMvc` và HTTP client đều có thể gửi request trong test, nhưng chúng đi qua các đường xử lý khác nhau.

| Đặc điểm | `MockMvc` | HTTP client tới server thật |
| --- | --- | --- |
| Máy chủ TCP/HTTP đang lắng nghe cổng | Không cần | Có |
| Cách gọi | Dispatch request giả lập vào Spring MVC trong tiến trình test | Gửi HTTP qua socket tới địa chỉ/cổng server |
| Thread xử lý | Thường nằm trong quá trình thực thi MockMvc của test | Thread/container xử lý request ở phía server |
| Context từ `@WithMockUser` | Có thể được cấp vào request qua tích hợp Spring Security Test | Không tự truyền qua mạng |
| Cách cung cấp danh tính | `user(...)`, `authentication(...)`, `testSecurityContext()` hoặc annotation test đã tích hợp | Authorization header, cookie/session, chứng thư hoặc credential thực |
| Điều kiểm chứng | Filter chain và authorization trong MVC test context | Hành vi của server khi nhận request HTTP thật |

Với `MockMvc`, `springSecurity()` tích hợp các filter và thành phần test postprocessor cần thiết. `@WithMockUser` có thể cung cấp authentication cho request giả lập vì Spring Security Test chủ động nối context của test với request.

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot khởi động server trên một cổng thật. Một HTTP client kết nối đến cổng đó không được `@WithMockUser` tự động cấp danh tính. Phải gửi thông tin xác thực qua HTTP.

Sơ đồ:

~~~text
MockMvc test
  @WithMockUser("lan")
       │
       ▼
  TestContext / TestSecurityContextHolder
       │
       ▼
  MockMvc + springSecurity()
       │
       ▼
  SecurityFilterChain trong MVC test
       │
       ▼
  Controller

RANDOM_PORT test
  @WithMockUser("lan") ──► chỉ đặt context cho test thread
       │
       ▼
  WebTestClient / TestRestTemplate / HttpClient
       │  gửi HTTP headers/cookies/body
       ▼
  Socket / embedded server
       │
       ▼
  SecurityFilterChain của server
       │
       ▼
  Controller
~~~

Không nên coi `RANDOM_PORT` là “MockMvc chạy ở port khác”. Đây là một đường kiểm thử tích hợp khác: request thực sự đi qua HTTP server và chỉ mang danh tính được truyền trong giao thức.

## 3. Ví dụ: @WithMockUser không xác thực request tới RANDOM_PORT

Giả sử ứng dụng có endpoint `GET /api/profile` yêu cầu người dùng đã đăng nhập và dùng HTTP Basic. Ta viết test như sau:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpDoesNotInheritTestContextTest {

    @LocalServerPort
    int port;

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void testThreadHasUserButServerRequestIsAnonymous() {
        // Có thể đọc "lan" ở test thread.
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("lan");

        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        // Không gửi Authorization header hoặc cookie.
        client.get().uri("/api/profile")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

Ví dụ giả định server bật HTTP Basic entry point, endpoint yêu cầu authentication và không có cơ chế đăng nhập khác tự cấp session. `WebTestClient.bindToServer()` tạo client kết nối qua HTTP đến server đang lắng nghe cổng được cấp. Request không có credentials nên server xử lý như một request chưa đăng nhập, dù test thread đang có `lan`.

Các import bổ sung cần có trong ví dụ là `SecurityContextHolder` và `WithMockUser`. Ở đây `@WithMockUser` chỉ phục vụ assertion trên test thread; nó không thay thế thông tin xác thực mà HTTP client phải gửi.

Nếu endpoint dùng form login, custom entry point hoặc trả redirect, status của request vô danh có thể là `302` thay vì `401`. Kỳ vọng phải bám theo cấu hình `SecurityFilterChain` của ứng dụng.

## 4. Gửi credentials qua HTTP Basic

Với HTTP Basic, client gửi header `Authorization: Basic ...`. Test phải dùng một username/password mà `AuthenticationManager` hoặc `UserDetailsService` phía server thực sự chấp nhận.

Ví dụ với `WebTestClient` kết nối server thật:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpBasicLiveServerTest {

    @LocalServerPort
    int port;

    @Test
    void sendsBasicCredentialsToServer() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        client.get()
                .uri("/api/profile")
                .headers(headers -> headers.setBasicAuth(
                        "lan", "correct-test-password"))
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

Ví dụ giả định người dùng `lan` tồn tại trong cấu hình xác thực của ứng dụng và password test là hợp lệ. Header Basic chỉ là phương thức vận chuyển credential; server vẫn phải kiểm tra credential bằng provider/authentication manager. Nếu gửi password sai, kỳ vọng thường là `401` theo cấu hình HTTP Basic.

Có thể viết ca âm:

~~~java
client.get()
        .uri("/api/profile")
        .headers(headers -> headers.setBasicAuth("lan", "wrong-password"))
        .exchange()
        .expectStatus().isUnauthorized();
~~~

Đây là test xác thực qua HTTP thật: nó kiểm chứng credential được gửi tới server và server xử lý kết quả xác thực. `@WithMockUser` không tham gia vào việc xác minh password này.

Không nên đặt password thật của môi trường production trong source test. Hãy dùng tài khoản fixture, test profile hoặc secret dành riêng cho môi trường kiểm thử.

## 5. Gửi bearer token tới Resource Server

Với OAuth2 Resource Server dùng JWT, HTTP request phải mang header:

~~~http
Authorization: Bearer <access-token>
~~~

Khi test chạy server thật, cần gửi một access token mà cấu hình decoder của server có thể xác minh. Token đó thường được ký bằng test key mà ứng dụng cấu hình tin cậy, hoặc được phát hành bởi một authorization server dành cho integration test.

~~~java
client.get()
        .uri("/api/reports")
        .headers(headers -> headers.setBearerAuth(validSignedAccessToken))
        .exchange()
        .expectStatus().isOk();
~~~

`validSignedAccessToken` là token test đã được tạo và ký theo cấu hình decoder/issuer/audience của server. Đoạn code trên chỉ minh họa việc gửi token qua HTTP; nó không tự tạo token hợp lệ.

Một test token sai chữ ký hoặc token hết hạn có thể kỳ vọng `401`. Một token có chữ ký hợp lệ nhưng thiếu scope/authority cần thiết có thể nhận `403`. Phân biệt hai tình huống:

| Token/request | Xác thực token | Authorization | Kết quả thường gặp |
| --- | --- | --- | --- |
| Không có bearer token | Không có credential | Không thể đáp ứng yêu cầu đăng nhập | `401` hoặc entry point redirect |
| Token sai chữ ký/issuer/hết hạn | Thất bại | Không đi tới quyết định quyền thông thường | `401` |
| Token hợp lệ, thiếu scope | Thành công | Thiếu authority | `403` |
| Token hợp lệ, đủ scope | Thành công | Được phép | `200` hoặc status thành công của endpoint |

Với `MockMvc`, request postprocessor `jwt()` tạo JWT authentication giả lập để kiểm tra authorization. Nó không chứng minh decoder đã xác minh chữ ký. Muốn kiểm tra decoder, issuer, audience, thời hạn và chữ ký, phải gửi token qua HTTP tới server hoặc gọi thành phần decoder với token thực sự phù hợp.

## 6. Session và cookie cũng phải đi qua HTTP

Không phải ứng dụng nào cũng dùng HTTP Basic hoặc bearer token. Với form login hoặc session-based authentication, server thường tạo session sau khi người dùng đăng nhập thành công và trả cookie (thường là `JSESSIONID`). Client phải giữ cookie đó và gửi lại ở request tiếp theo.

Luồng tổng quát:

~~~text
Client gửi POST /login với credentials (+ CSRF token nếu bật)
       │
       ▼
Server xác thực credentials
       │
       ├─ thất bại ─► 401/302 theo cấu hình
       │
       └─ thành công
              │
              ▼
       Tạo/cập nhật session và lưu SecurityContext
              │
              ▼
       Response: Set-Cookie: JSESSIONID=...
              │
              ▼
Client lưu cookie
              │
              ▼
Request kế tiếp gửi Cookie: JSESSIONID=...
              │
              ▼
Server tải SecurityContext từ session/repository
~~~

Trong test HTTP thật, dùng client có cookie store hoặc lấy cookie từ response rồi gửi lại. Không thể chỉ gọi `SecurityContextHolder.setContext(...)` ở test thread và mong server có session tương ứng.

Nếu ứng dụng bật CSRF, request login hoặc request thay đổi trạng thái có thể cần CSRF token hợp lệ. Đừng bỏ qua CSRF chỉ để test login chạy được; nếu mục tiêu là kiểm tra luồng form login thực, hãy lấy token theo cơ chế ứng dụng và gửi kèm request.

`MockMvc` có thể dùng session/request postprocessor để mô phỏng trạng thái session trong MVC test. Nhưng test đó vẫn khác với việc kiểm chứng cookie được tạo, truyền và sử dụng qua HTTP server thật.

## 7. Ví dụ WebTestClient gửi HTTP thật tới server

`WebTestClient` có hai kiểu sử dụng cần phân biệt:

- `bindToApplicationContext(...)` hoặc `bindToController(...)`: test gắn vào application context/controller trong tiến trình, không nhất thiết mở cổng HTTP thật.
- `bindToServer().baseUrl(...)`: client kết nối đến server qua HTTP, có thể dùng với server Servlet hoặc Reactive đang chạy.

Ví dụ dưới đây dùng `RANDOM_PORT` và `bindToServer()`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpSecurityTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void createHttpClient() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    void noCredentialIsRejected() {
        client.get()
                .uri("/api/reports")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validBasicCredentialIsAccepted() {
        client.get()
                .uri("/api/reports")
                .headers(headers -> headers.setBasicAuth(
                        "lan", "correct-test-password"))
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

Ví dụ cần endpoint `/api/reports`, HTTP Basic, và user/password test được cấu hình trong ứng dụng. `@LocalServerPort` lấy cổng ngẫu nhiên mà server đã khởi động. Client được tạo trong `@BeforeEach` để mỗi test dùng một client có base URL rõ ràng.

Có thể dùng cùng cách này để test ứng dụng WebFlux; `WebTestClient.bindToServer()` không tự biến request thành một test context nội bộ. Request thực sự được gửi tới server và phải mang credential/token/cookie phù hợp.

Nếu dùng `TestRestTemplate` trong Spring Boot Servlet test, nguyên tắc vẫn giống nhau: `withBasicAuth("lan", "password")` hoặc gửi header/cookie tương ứng để server nhận được thông tin xác thực. Không có API nào khiến `@WithMockUser` tự chuyển thành HTTP Basic credential.

## 8. TestSecurityContextHolder cũng không phải kênh truyền HTTP

`TestSecurityContextHolder` lưu context riêng cho test và đồng bộ với `SecurityContextHolder` trên test thread. Trong MockMvc, request postprocessor `testSecurityContext()` có thể đọc context này và cấp vào request giả lập.

~~~java
mockMvc.perform(get("/api/profile")
        .with(testSecurityContext()))
        .andExpect(status().isOk());
~~~

Đây là hành vi do Spring Security Test tích hợp với MockMvc, không phải HTTP client gửi một object `SecurityContext` qua mạng.

Không có header chuẩn nào như `X-Security-Context` mà Spring Security tự hiểu để khôi phục toàn bộ context. Nếu tự gửi một JSON chứa username/role trong header tùy biến, server không được tin dữ liệu đó trừ khi ứng dụng có một cơ chế xác thực và bảo vệ rõ ràng. Không nên tạo một endpoint hoặc filter chấp nhận principal tùy ý từ client để thay thế authentication.

Server cần xác minh credential hoặc token theo cơ chế tin cậy của nó, sau đó tạo authentication và đặt vào context request. Đây là ranh giới bảo mật cốt lõi: **client gửi bằng chứng xác thực; server quyết định danh tính và quyền**.

## 9. Phân biệt test context, request context và session context

Ba loại trạng thái sau có vòng đời và cách truyền khác nhau:

| Loại trạng thái | Được tạo bởi | Phạm vi | Cách được dùng lại |
| --- | --- | --- | --- |
| Test context | `@WithMockUser`, listener hoặc code test | Phương thức test/thread JUnit | Listener quản lý; MockMvc có thể được cấp qua test postprocessor |
| Request context | Security filter chain khi xử lý request | Một HTTP request trên server | Filter/repository tải và dọn theo request |
| Session context | Cơ chế lưu bảo mật trong session/repository nếu ứng dụng bật | Nhiều request gắn cùng session | Client gửi lại session cookie hoặc session identifier phù hợp |

Một người dùng có thể xuất hiện trong cả ba trạng thái, nhưng không có nghĩa chúng tự đồng bộ. Ví dụ, `@WithMockUser` tạo test context cho `lan`; MockMvc có thể cấp `lan` vào request giả lập; session của server vẫn chưa chắc được tạo hoặc lưu. Ngược lại, một client đăng nhập qua HTTP Basic có thể được server xác thực trên mỗi request mà không cần session.

Với `SecurityContextRepository`, cách lưu context phụ thuộc cấu hình. `HttpSessionSecurityContextRepository` có thể lưu trong HTTP session; repository kiểu request attribute hoặc stateless có vòng đời khác. Khi kiểm thử server thật, hãy xác định ứng dụng đang dùng mô hình session hay stateless để gửi đúng dữ liệu.

## 10. Những tình huống kiểm thử nên có

Đối với một endpoint bảo vệ, nên phân tách các mục tiêu:

| Mục tiêu | Cách kiểm thử phù hợp | Bằng chứng |
| --- | --- | --- |
| Service nhận được principal để kiểm tra logic nghiệp vụ | Unit test hoặc test Spring với `@WithMockUser` | Principal/authority trên test context |
| Method security cho phép/từ chối theo authority | `@WithMockUser` + gọi method được bảo vệ | Giá trị trả về hoặc `AccessDeniedException` |
| HTTP authorization trong Servlet filter chain | `MockMvc` tích hợp `springSecurity()` | Status/body/header của request giả lập |
| HTTP server thật chấp nhận Basic credentials | `RANDOM_PORT` + HTTP client gửi Basic header | Server trả kết quả khi credentials đúng/sai |
| Resource Server xác minh JWT thật | `RANDOM_PORT` + bearer token được ký theo cấu hình | Token hợp lệ được nhận, token sai bị từ chối |
| Session được tạo và tái sử dụng | HTTP login, giữ cookie, gửi request tiếp theo | Cookie/session và trạng thái xác thực qua nhiều request |
| WebFlux server thật nhận user/token | `RANDOM_PORT` + `WebTestClient.bindToServer()` | Kết quả HTTP từ server Reactive |
| Test chỉ cần mô phỏng claim để kiểm tra authorization | `jwt()` hoặc `mockJwt()` trong test phù hợp | Authorization theo claim/authority giả lập |

Đừng gộp tất cả mục tiêu vào một bài test. Một test dùng `@WithMockUser` có thể kiểm tra rất tốt method security, nhưng không chứng minh password đúng hoặc JWT signature hợp lệ. Một test HTTP thật xác minh credentials đi qua server, nhưng không nhất thiết cần lặp lại mọi ca unit test cho service.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Test thread thấy `lan` nhưng server trả `401` | `@WithMockUser` không truyền qua socket | Gửi Basic header, bearer token hoặc session cookie |
| MockMvc test thành công nhưng RANDOM_PORT thất bại | MockMvc dùng test postprocessor cấp context; live server yêu cầu HTTP credentials | Viết test riêng cho đường HTTP thật |
| HTTP Basic luôn trả `401` | Username/password không đúng với UserDetailsService/AuthenticationManager hoặc filter chưa bật | Kiểm tra test user và SecurityFilterChain |
| JWT mock thành công nhưng bearer token thật bị từ chối | Mock bỏ qua decoder/signature validation | Dùng token ký bởi test key/issuer được decoder tin cậy |
| Login thành công nhưng request tiếp theo mất user | Client không giữ/gửi lại cookie session, hoặc server không lưu context | Kiểm tra Set-Cookie, cookie store và SecurityContextRepository |
| POST trả `403` dù credentials đúng | Thiếu CSRF token | Gửi CSRF token đúng quy trình hoặc kiểm tra cấu hình stateless phù hợp |
| `WebTestClient` không mở được kết nối | Server chưa chạy hoặc sai port/base URL | Dùng `RANDOM_PORT` và `@LocalServerPort` |
| `@WithMockUser` làm test pass dù server chưa cấu hình user đó | Mock user không cần tài khoản thật | Dùng HTTP thật với credential của user được cấu hình |
| Server chạy cùng JVM nhưng vẫn không nhận context test | Thread và ranh giới HTTP độc lập | Truyền danh tính qua giao thức, không dựa vào ThreadLocal |

## 12. Bài thực hành

Tạo một ứng dụng Servlet có endpoint `GET /api/profile` yêu cầu authentication và endpoint `GET /api/admin` yêu cầu `ROLE_ADMIN`. Cấu hình HTTP Basic cho integration test, sau đó:

1. Viết một test `@WithMockUser` và chứng minh test thread đọc được principal.
2. Khởi động server bằng `@SpringBootTest(webEnvironment = RANDOM_PORT)`, gửi request không có header và xác minh server từ chối.
3. Gửi HTTP Basic với password đúng/sai; so sánh phản hồi.
4. Gửi Basic credentials của người có `ROLE_READER` đến `/api/admin` và xác minh authorization từ chối.
5. Gửi credentials của người có `ROLE_ADMIN` và xác minh endpoint được phép.
6. Nếu ứng dụng dùng Resource Server, tạo JWT test được ký bởi key mà decoder tin cậy, gửi bằng bearer header và thêm ca token sai chữ ký/hết hạn.
7. Nếu ứng dụng dùng session, thực hiện login, giữ cookie trả về và gửi request thứ hai với cookie đó.
8. So sánh cùng một ca phân quyền giữa MockMvc và client tới RANDOM_PORT; giải thích dữ liệu danh tính được cấp bằng cách nào trong mỗi trường hợp.

Sau bài thực hành, hãy tự trả lời: **Danh tính đang nằm trong test thread, request của MockMvc hay request HTTP của server? Client đã gửi bằng chứng xác thực nào? Server xác minh bằng cơ chế nào?** Khi phân biệt được ba ranh giới này, bạn sẽ tránh nhầm một test context giả lập với một phiên đăng nhập thật.

## Tài liệu tham khảo

- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)

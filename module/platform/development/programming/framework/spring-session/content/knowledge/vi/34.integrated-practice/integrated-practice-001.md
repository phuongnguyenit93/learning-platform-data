# Xây dựng ứng dụng lưu tùy chọn người dùng bằng HttpSession

Trong bài thực hành này, ta xây dựng một ứng dụng Spring MVC nhỏ cho phép người dùng chọn giao diện, ngôn ngữ, múi giờ và chế độ hiển thị gọn. Ứng dụng lưu các tùy chọn vào HttpSession để những request tiếp theo có thể đọc lại mà không phải gửi toàn bộ lựa chọn trong mỗi request. Spring Session quản lý session thông qua repository; với Redis, nhiều instance ứng dụng có thể cùng khôi phục một phiên dù request được chuyển tới JVM khác.

Mục tiêu là hiểu trọn vòng đời: tạo session khi người dùng lưu tùy chọn, đọc lại session ở request sau, cập nhật hoặc xóa tùy chọn, hết hạn theo TTL và đăng xuất. Đây là trạng thái cá nhân tạm thời gắn với phiên trình duyệt. Nếu tùy chọn cần tồn tại lâu dài, đồng bộ giữa thiết bị hoặc có giá trị nghiệp vụ, nên lưu hồ sơ người dùng trong database; session có thể giữ bản tùy chỉnh tạm thời hoặc tham chiếu tới hồ sơ đó.

## 1. Kết quả cần đạt

Sau khi hoàn thành, ứng dụng có các hành vi:

1. Request GET chưa có session trả về tùy chọn mặc định và không tạo session không cần thiết.
2. Request PUT nhận tùy chọn hợp lệ, tạo session nếu chưa có và lưu một DTO nhỏ trong HttpSession.
3. Request GET tiếp theo dùng cùng session cookie để đọc lại đúng tùy chọn.
4. Request DELETE xóa tùy chọn khỏi session nhưng không nhất thiết đăng xuất người dùng.
5. Session hết hạn thì tùy chọn tạm thời không còn được khôi phục.
6. Nhiều application instance dùng cùng Spring Session repository có thể đọc cùng session.
7. Logout invalidate session phía server; cookie cũ không thể khôi phục phiên đã bị thu hồi.

Luồng tổng quát:

~~~mermaid
flowchart TD
    B[Browser] -->|GET /api/preferences| A[Spring MVC application]
    A --> F[SessionRepositoryFilter]
    F --> R[Spring Session repository]
    R --> D[(Redis)]
    D --> R
    R --> F
    F --> A
    A -->|JSON preferences| B
    B -->|PUT preferences + session cookie| A
    A -->|setAttribute| F
    F -->|save session| R
    R --> D
~~~

Browser giữ cookie chứa session ID. Cookie không chứa toàn bộ tùy chọn; session attributes được lưu trong repository. Khi request tiếp theo gửi cookie, Spring Session tìm session theo ID và cung cấp HttpSession cho controller.

## 2. Công nghệ và cấu trúc dự án

Ví dụ dùng Spring Boot 3, Spring MVC, Spring Session Redis và Bean Validation. Có thể dùng JDBC repository thay Redis nếu ứng dụng đã có database phù hợp.

Các dependency Maven chính:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Dùng Spring Boot dependency management để chọn phiên bản tương thích, không tự đặt một phiên bản Spring Session khác với Spring Boot BOM nếu chưa kiểm tra compatibility matrix.

Một cấu trúc source đơn giản:

~~~text
src/main/java/com/example/preferences/
    PreferencesApplication.java
    config/SessionConfiguration.java
    web/PreferencesController.java
    web/UpdatePreferencesRequest.java
    domain/UserPreferences.java
src/main/resources/
    application.yml
src/test/java/com/example/preferences/
    PreferencesControllerTest.java
~~~

## 3. Cấu hình Spring Session Redis

Ví dụ application.yml cho môi trường local:

~~~yaml
server:
  port: 8080

spring:
  data:
    redis:
      host: localhost
      port: 6379
  session:
    timeout: 30m
    redis:
      namespace: preferences-app:sessions
      flush-mode: on-save
      save-mode: on-set-attribute
~~~

Các property cụ thể có thể thay đổi theo phiên bản Spring Boot. Hãy kiểm tra metadata cấu hình của dependency đang dùng. Namespace giúp tách session của ứng dụng khỏi keyspace của ứng dụng khác trong cùng Redis. Nếu chạy nhiều instance của cùng ứng dụng, mọi instance phải dùng cùng Redis endpoint, namespace, serializer và chính sách session.

FlushMode ON_SAVE thường lưu thay đổi ở bước hoàn tất lưu session; SaveMode ON_SET_ATTRIBUTE giới hạn việc lưu theo những attribute được set. Hai mode này ảnh hưởng thời điểm và lượng dữ liệu ghi, không thay thế transaction nghiệp vụ hoặc cơ chế khóa khi nhiều request đồng thời cập nhật cùng session.

Trong môi trường thực tế, lấy host, port, username/password và TLS từ secret/configuration management. Không commit password vào source control. Nếu dùng Redis Sentinel hoặc Cluster, cấu hình discovery/topology tương ứng và kiểm thử failover riêng.

## 4. Cấu hình cookie session

Cookie cần được bảo vệ vì session ID là bearer credential: ai có ID hợp lệ có thể thử sử dụng phiên tương ứng. Với ứng dụng Servlet, có thể cấu hình CookieHttpSessionIdResolver và DefaultCookieSerializer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieHttpSessionIdResolver;
import org.springframework.session.web.http.DefaultCookieSerializer;
import org.springframework.session.web.http.HttpSessionIdResolver;

@Configuration
class SessionConfiguration {

    @Bean
    HttpSessionIdResolver httpSessionIdResolver() {
        CookieHttpSessionIdResolver resolver =
                new CookieHttpSessionIdResolver();

        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SESSION");
        serializer.setCookiePath("/");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");

        resolver.setCookieSerializer(serializer);
        return resolver;
    }
}
~~~

Ví dụ trên giả định production chạy HTTPS. Trong local HTTP development, Secure cookie có thể không được gửi bởi browser; dùng profile local với cấu hình phù hợp, nhưng giữ Secure bật ở production. Nếu TLS kết thúc tại reverse proxy, cấu hình forwarded headers từ proxy tin cậy hoặc đặt secure policy rõ ràng.

Không đặt Domain rộng hơn nhu cầu. Nếu chỉ một host dùng ứng dụng, host-only cookie thường giảm phạm vi lộ credential. HttpOnly ngăn JavaScript đọc cookie trực tiếp; Secure giới hạn truyền qua HTTPS; SameSite Lax giảm một số request cross-site nhưng không thay thế CSRF protection.

Chỉ đăng ký resolver tùy chỉnh khi đã xác minh Spring Session filter dùng bean đó. Không đồng thời đăng ký nhiều resolver/filter quản lý session.

## 5. Thiết kế dữ liệu tùy chọn người dùng

Chỉ lưu dữ liệu nhỏ, ổn định và cần thiết cho request. Ví dụ:

~~~java
package com.example.preferences.domain;

public enum Theme {
    LIGHT,
    DARK,
    SYSTEM
}
~~~

~~~java
package com.example.preferences.domain;

public record UserPreferences(
        Theme theme,
        String locale,
        String timeZone,
        boolean compactMode
) implements java.io.Serializable {
    public static UserPreferences defaults() {
        return new UserPreferences(
                Theme.SYSTEM,
                "vi",
                "Asia/Ho_Chi_Minh",
                false
        );
    }
}
~~~

Tách request DTO để xác thực input:

~~~java
package com.example.preferences.web;

import com.example.preferences.domain.Theme;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record UpdatePreferencesRequest(
        @NotNull Theme theme,
        @NotBlank
        @Pattern(regexp = "[a-z]{2}(-[A-Z]{2})?")
        String locale,
        @NotBlank String timeZone,
        boolean compactMode
) {
}
~~~

Locale được giới hạn theo contract đơn giản của ví dụ. Ứng dụng thực tế có thể dùng danh sách locale được hỗ trợ hoặc Locale.forLanguageTag rồi xác minh kết quả. Múi giờ phải được kiểm tra bằng ZoneId.of vì chuỗi bất kỳ không phải timezone hợp lệ.

Không lưu password, access token dài hạn, thông tin thanh toán hoặc toàn bộ entity ORM trong session. Với dữ liệu lớn, lưu một ID tham chiếu và tải nội dung từ service/database.

## 6. Tạo endpoint đọc và cập nhật tùy chọn

Controller dùng HttpServletRequest để truy cập HttpSession. Điểm quan trọng là GET dùng getSession(false) để không tạo session mới chỉ vì người dùng mở trang; PUT dùng getSession(true) vì hành động lưu tùy chọn cần một nơi giữ trạng thái.

~~~java
package com.example.preferences.web;

import java.time.DateTimeException;
import java.time.ZoneId;

import com.example.preferences.domain.UserPreferences;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/preferences")
class PreferencesController {

    private static final String ATTRIBUTE =
            "com.example.preferences.v1";

    @GetMapping
    ResponseEntity<UserPreferences> get(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.ok(UserPreferences.defaults());
        }

        Object value = session.getAttribute(ATTRIBUTE);
        if (value instanceof UserPreferences preferences) {
            return ResponseEntity.ok(preferences);
        }

        return ResponseEntity.ok(UserPreferences.defaults());
    }

    @PutMapping
    ResponseEntity<UserPreferences> update(
            @Valid @RequestBody UpdatePreferencesRequest input,
            HttpServletRequest request) {

        try {
            ZoneId.of(input.timeZone());
        }
        catch (DateTimeException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Múi giờ không hợp lệ");
        }

        UserPreferences preferences = new UserPreferences(
                input.theme(),
                input.locale(),
                input.timeZone(),
                input.compactMode()
        );

        HttpSession session = request.getSession(true);
        session.setAttribute(ATTRIBUTE, preferences);

        return ResponseEntity.ok(preferences);
    }

    @DeleteMapping
    ResponseEntity<Void> reset(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.removeAttribute(ATTRIBUTE);
        }
        return ResponseEntity.noContent().build();
    }
}
~~~

Import Map đã được giữ lại để có thể mở rộng response thành metadata, nhưng có thể bỏ nếu IDE báo không sử dụng. Trong một dự án thực tế, có thể chuyển phần validate timezone sang validator/service riêng và dùng exception handler chung để chuẩn hóa lỗi 400.

Tên attribute có namespace và version để giảm va chạm với ứng dụng hoặc thư viện khác. DTO có version trong key giúp thay đổi contract có kế hoạch. Nếu attribute tồn tại nhưng không deserialize được sau rolling deployment, xử lý lỗi có quan sát và yêu cầu tạo lại tùy chọn; không tiếp tục dùng object sai kiểu.

## 7. Tại sao GET không tạo session mới?

Nếu controller gọi getSession() trong mọi GET, mỗi khách truy cập trang tùy chọn có thể tạo một session mới dù chỉ muốn xem mặc định. Điều đó làm tăng số session, Redis key hoặc database row, cookie response và tải cleanup.

Sự khác biệt:

| API | Hành vi |
| --- | --- |
| getSession(false) | Trả session hiện có hoặc null; không tạo mới |
| getSession() / getSession(true) | Trả session hiện có hoặc tạo session mới |
| session.getAttribute(key) | Đọc attribute; không tạo session mới |
| session.removeAttribute(key) | Xóa một attribute, không invalidate toàn bộ session |
| session.invalidate() | Hủy session hiện tại |

GET không có session trả tùy chọn mặc định nhưng không cần ghi mặc định vào session. Chỉ khi người dùng chủ động lưu hoặc ứng dụng có lý do cần giữ lựa chọn mới tạo session.

## 8. Chạy ứng dụng và thử bằng HTTP

Khởi động Redis local, sau đó chạy Spring Boot. Có thể kiểm tra bằng curl:

~~~bash
# Đọc mặc định; request chưa có session
curl -i http://localhost:8080/api/preferences

# Lưu tùy chọn và ghi cookie vào cookie jar
curl -i -c prefs-cookies.txt -b prefs-cookies.txt \
  -X PUT http://localhost:8080/api/preferences \
  -H "Content-Type: application/json" \
  -d '{"theme":"DARK","locale":"vi","timeZone":"Asia/Ho_Chi_Minh","compactMode":true}'

# Đọc lại bằng cùng cookie
curl -i -b prefs-cookies.txt http://localhost:8080/api/preferences

# Xóa tùy chọn nhưng giữ session
curl -i -b prefs-cookies.txt \
  -X DELETE http://localhost:8080/api/preferences

# Đọc lại; kết quả trở về mặc định
curl -i -b prefs-cookies.txt http://localhost:8080/api/preferences
~~~

Cookie jar chỉ dùng trong máy local/test. Không commit file này hoặc gửi nó vào ticket; nó chứa session credential. Nếu cookie Secure được bật, dùng HTTPS trong môi trường kiểm thử hoặc cấu hình profile local riêng.

Kết quả mong đợi:

- GET đầu trả theme SYSTEM, locale vi, timezone Asia/Ho_Chi_Minh và compactMode false.
- PUT trả tùy chọn mới và Set-Cookie khi session được tạo.
- GET tiếp theo trả đúng giá trị đã lưu.
- DELETE trả 204 và chỉ xóa attribute tùy chọn.
- GET sau DELETE trả mặc định; session đăng nhập hiện tại (nếu có) vẫn có thể còn nguyên.

## 9. Kiểm thử validation

Các input không hợp lệ phải bị từ chối trước khi ghi vào session:

| Input | Kết quả |
| --- | --- |
| theme không thuộc enum | HTTP 400 |
| locale rỗng | HTTP 400 |
| locale sai pattern | HTTP 400 |
| timeZone không tồn tại | HTTP 400 |
| JSON thiếu trường bắt buộc | HTTP 400 |
| body quá lớn | Từ chối theo giới hạn request body của ứng dụng |

Không ghi dữ liệu đầu vào chưa xác thực vào session rồi mới kiểm tra. Session có thể được chia sẻ qua nhiều node; một attribute sai định dạng sẽ gây lỗi cho mọi node cùng đọc.

## 10. Viết integration test cho session round-trip

Test cần đi qua Spring Session filter để xác minh cookie và repository, không chỉ gọi trực tiếp controller. Với MockMvc, bảo đảm filter được đăng ký trong test context; với Redis integration, dùng Testcontainers hoặc Redis test instance riêng.

Ví dụ phần test round-trip bằng MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PreferencesControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void preferencesAreAvailableOnTheNextRequest() throws Exception {
        MvcResult saved = mockMvc.perform(put("/api/preferences")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "theme": "DARK",
                                  "locale": "vi",
                                  "timeZone": "Asia/Ho_Chi_Minh",
                                  "compactMode": true
                                }
                                """))
                .andExpect(status().isOk())
                .andReturn();

        Cookie sessionCookie = saved.getResponse().getCookie("SESSION");
        assertThat(sessionCookie).isNotNull();

        mockMvc.perform(get("/api/preferences").cookie(sessionCookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.theme").value("DARK"))
                .andExpect(jsonPath("$.compactMode").value(true));
    }
}
~~~

Ví dụ giả định cookie name là SESSION và filter có trong MockMvc chain. Nếu dùng resolver/cookie name khác, sửa test tương ứng. Với Spring Session Redis, cần cấu hình Redis test backend và xác minh session thực sự được lưu ở repository; MockHttpSession truyền trực tiếp không chứng minh round-trip qua Redis.

Nên bổ sung test:

- GET không có session trả default và không phát cookie tạo session.
- PUT hợp lệ tạo session.
- PUT không hợp lệ trả 400 và không lưu giá trị.
- DELETE chỉ xóa attribute tùy chọn.
- Cookie cũ sau logout không khôi phục session.
- Session hết hạn không còn trả tùy chọn cũ.

## 11. Kiểm thử TTL và session expiration

Với timeout 30 phút, session có thể hết hạn sau 30 phút không hoạt động. Khi kiểm thử, dùng timeout ngắn trong test profile, ví dụ vài giây, nhưng không assert backend xóa key đúng một millisecond tuyệt đối.

Phân biệt:

- Logical expiration: Spring Session không được khôi phục session đã hết hạn.
- Physical cleanup: Redis TTL hoặc job database xóa dữ liệu vật lý.

Test logic nên xác minh request với cookie cũ không đọc được tùy chọn đã lưu sau khi session hết hạn. Test backend có thể poll key/record theo deadline riêng. Redis TTL có độ trễ thực thi; database cleanup có thể chạy theo batch. Dữ liệu còn vật lý trong một khoảng ngắn không có nghĩa repository được phép trả session đã hết hạn.

Không dùng Reactor virtual time để kết luận Redis server đã đếm hết TTL. Ứng dụng Servlet cũng cần dùng thời gian thật hoặc Clock được inject trong custom logic; timer backend không tự tiến theo clock test của JVM.

## 12. Kiểm thử nhiều application instance

Để chứng minh tùy chọn không phụ thuộc một JVM:

1. Khởi chạy node A và B với cùng Redis endpoint và namespace.
2. PUT tùy chọn qua A và giữ cookie.
3. GET qua B với cùng cookie.
4. Xác minh B đọc được đúng tùy chọn.
5. Cập nhật qua B rồi GET lại qua A.
6. Dừng A và xác minh B vẫn đọc được session.

Nếu load balancer bật sticky session, request có thể luôn quay về một node và làm phép thử không đủ giá trị. Trong test, gọi trực tiếp từng node hoặc tắt affinity có kiểm soát. Không cần sticky session để Spring Session chia sẻ dữ liệu; repository chung mới là thành phần giữ session state.

## 13. Cập nhật đồng thời và lost update

HttpSession không phải database transaction và không tự merge hai request cùng đọc một snapshot. Ví dụ hai tab cùng tải preferences, tab A đổi locale, tab B đổi theme rồi cả hai cùng ghi một DTO mới. Request ghi sau có thể ghi đè thay đổi của request trước nếu mỗi request dựng DTO từ snapshot cũ.

Với tùy chọn đơn giản, có thể chấp nhận last-write-wins và ghi rõ hành vi. Nếu cần tránh mất thay đổi:

- Thiết kế endpoint cập nhật từng trường thay vì thay toàn bộ DTO.
- Đọc trạng thái hiện tại và merge các trường được gửi, trong giới hạn đảm bảo không có race.
- Dùng version/optimistic locking ở kho dữ liệu nghiệp vụ nếu yêu cầu nhất quán cao.
- Lưu preferences lâu dài trong database với cột version và cập nhật có điều kiện.

Một lần ghi session có thể được serialize lại toàn bộ object; không giả định hai request cập nhật hai attribute độc lập luôn được merge nguyên tử. Redis/JDBC shared repository giúp nhiều node cùng truy cập, nhưng không tự giải quyết concurrent lost update.

## 14. Phân biệt reset tùy chọn và logout

Reset preferences chỉ nên gọi removeAttribute trên key tùy chọn. Logout cần invalidate session và thường được thực hiện qua Spring Security logout handler hoặc API logout có bảo vệ.

| Hành động | Kết quả |
| --- | --- |
| removeAttribute(preferencesKey) | Xóa tùy chọn, giữ session còn lại |
| invalidate() | Hủy toàn bộ session hiện tại |
| Spring Security logout | Thường xóa SecurityContext, invalidate session và xử lý cookie theo cấu hình |
| Session timeout | Repository không còn khôi phục phiên sau idle timeout |

Không dùng invalidate() cho nút “Đặt lại tùy chọn” nếu session còn chứa authentication, CSRF state hoặc dữ liệu tạm khác. Ngược lại, không chỉ removeAttribute preferences khi người dùng bấm logout; phải thu hồi toàn bộ phiên theo security policy.

Nếu ứng dụng có Spring Security, bật bảo vệ CSRF cho request thay đổi trạng thái và cấu hình logout theo phiên bản. Không tạo endpoint GET để logout hoặc reset vì GET có thể bị kích hoạt ngoài ý muốn.

## 15. Bảo mật dữ liệu session

Tùy chọn giao diện thường ít nhạy cảm, nhưng session repository có thể chứa authentication và các thuộc tính khác. Áp dụng các nguyên tắc:

- Chỉ truyền cookie qua HTTPS trong production.
- Bật HttpOnly và Secure; chọn SameSite phù hợp.
- Giữ cookie domain/path hẹp nhất có thể.
- Không log session ID, cookie hoặc toàn bộ session attributes.
- Không lưu secret, password hoặc access token dài hạn trong session nếu không cần.
- Kiểm tra authorization trước khi đọc/ghi tùy chọn của người dùng đã xác thực.
- Dùng CSRF protection nếu xác thực dựa trên cookie.
- Giới hạn kích thước request và số lượng/độ lớn session attributes.

Session preferences không phải nguồn tin cậy cho quyền truy cập. Ví dụ locale hoặc theme không thể quyết định user có được phép xem dữ liệu của tenant khác hay không.

## 16. Lưu tùy chọn lâu dài ở đâu?

HttpSession phù hợp khi tùy chọn chỉ cần tồn tại trong phiên hoặc trong một khoảng idle timeout. Khi session hết hạn, Redis có thể xóa dữ liệu và người dùng trở về mặc định. Điều đó hợp lý với chế độ xem tạm thời, wizard ngắn hoặc tùy chọn chưa đăng nhập.

Nếu người dùng mong muốn theme/locale được giữ qua nhiều ngày, nhiều thiết bị hoặc sau logout, lưu bản chính trong user profile database. Sau authentication, ứng dụng có thể tải profile và đặt một bản cache nhỏ trong session. Khi người dùng đổi tùy chọn:

1. Xác thực người dùng.
2. Cập nhật profile database bằng transaction.
3. Cập nhật session cache nếu cần.
4. Request tiếp theo đọc từ cache hoặc profile theo chính sách.

Không coi Redis session là backup của hồ sơ người dùng. TTL, eviction, logout và failover có thể làm session mất; dữ liệu cần tồn tại lâu dài phải có persistence/backup phù hợp.

## 17. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| PUT trả thành công nhưng GET không thấy tùy chọn | Cookie không được gửi lại hoặc session không được lưu | Kiểm tra Set-Cookie, cookie path/domain, repository logs |
| Mỗi request tạo session mới | Cookie bị chặn, resolver sai hoặc proxy không chuyển cookie | Kiểm tra browser devtools và cookie serializer |
| Node B không thấy session do A tạo | Khác Redis namespace/endpoint hoặc serializer | So sánh config của hai node |
| Session mất sớm | Timeout nhỏ, request không refresh, TTL cấu hình sai | Kiểm tra last access, timeout và backend TTL |
| Session tồn tại lâu sau expiry | Cleanup chậm hoặc key phụ còn lại | Xác minh logical lookup riêng với physical cleanup |
| Lỗi deserialize sau deploy | DTO/class/serializer không tương thích | Kiểm tra classpath và format phiên bản cũ/mới |
| Hai tab ghi đè tùy chọn | Concurrent lost update | Xác định last-write-wins hoặc dùng versioned profile store |
| Reset làm người dùng logout | Code gọi invalidate thay vì removeAttribute | Tách reset preferences khỏi logout |

Khi điều tra, không xóa toàn bộ namespace Redis để “làm sạch” vì có thể làm mọi người dùng logout. Dùng session test riêng, correlation ID và metrics repository; không ghi session ID vào log.

## 18. Mở rộng sang JDBC repository

Nếu không dùng Redis, có thể dùng Spring Session JDBC và schema tương ứng với phiên bản. Ứng dụng cần:

- Dependency Spring Session JDBC phù hợp.
- DataSource và transaction manager.
- Bảng session/attributes được tạo bằng migration.
- Runtime DB user có quyền SELECT, INSERT, UPDATE, DELETE cần thiết.
- Cleanup session hết hạn và index phù hợp.

Nhiều node có thể dùng cùng database/schema/table. Cần tính tổng connection pool trên mọi node và kiểm thử duplicate key, lock contention, schema migration, permission và connection exhaustion. Không bật schema initialization tự động trên mọi production node nếu migration được quản lý riêng.

## 19. Bài tập mở rộng

1. Thêm tùy chọn font size với enum hoặc danh sách giá trị hợp lệ.
2. Thêm endpoint PATCH cập nhật riêng locale để giảm việc ghi đè các trường khác.
3. Thêm profile test có timeout ngắn và kiểm thử session expiration.
4. Chạy hai application instance và kiểm tra session round-trip giữa node.
5. Bật Spring Security, bảo vệ endpoint và kiểm tra CSRF.
6. Lưu preferences lâu dài trong database cho user đã đăng nhập, dùng session làm cache.
7. Thêm metric đếm session create, lookup miss, save error và expiration.
8. Kiểm thử rolling deployment khi DTO preferences thay đổi version.

## 20. Checklist hoàn thành

- [ ] Ứng dụng dùng Spring MVC và Spring Session repository đã cấu hình.
- [ ] Cookie session có name/path/security attributes phù hợp.
- [ ] GET không tạo session nếu chưa có và trả giá trị mặc định.
- [ ] PUT validate dữ liệu rồi lưu DTO nhỏ vào HttpSession.
- [ ] GET tiếp theo với cùng cookie đọc lại đúng tùy chọn.
- [ ] DELETE xóa riêng attribute preferences.
- [ ] Logout invalidate toàn bộ session theo security policy.
- [ ] Session hết hạn không còn khôi phục tùy chọn cũ.
- [ ] Hai application node dùng cùng repository đọc được cùng session.
- [ ] Concurrent update behavior được xác định và kiểm thử.
- [ ] Không log hoặc làm lộ session ID.
- [ ] Dữ liệu cần tồn tại lâu dài được lưu trong profile database, không chỉ trong session.

## 21. Kết luận

Ứng dụng tùy chọn người dùng cho thấy HttpSession giúp giữ trạng thái nhỏ giữa nhiều HTTP request. Controller dùng getSession(false) khi chỉ đọc, getSession(true) khi người dùng lưu tùy chọn, setAttribute để lưu DTO và removeAttribute để reset riêng phần tùy chọn. Spring Session thay nơi lưu mặc định bằng repository như Redis hoặc JDBC, cho phép nhiều application node cùng khôi phục session.

Để triển khai an toàn, cần bảo vệ cookie, validate dữ liệu trước khi lưu, kiểm thử round-trip qua filter/repository, hiểu TTL và logout, đồng thời xác định cách xử lý hai request cập nhật đồng thời. Session phù hợp với trạng thái tạm thời; hồ sơ người dùng cần tồn tại lâu dài nên được lưu trong database nghiệp vụ và chỉ cache trong session khi có lợi ích rõ ràng.

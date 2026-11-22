# Kiểm tra chính sách truy cập sau khi triển khai thực tế

Sau khi triển khai springdoc-openapi, cần xác minh người dùng thực tế chỉ truy cập được Swagger UI và tài liệu OpenAPI theo đúng chính sách đã thiết kế. Cấu hình trong mã nguồn chưa đủ để chứng minh tài liệu đã được bảo vệ: reverse proxy có thể mở một đường dẫn khác, một document group có thể bị bỏ sót trong security matcher, hoặc CDN có thể phục vụ lại nội dung đã cache.

Việc kiểm tra cần bao gồm toàn bộ bề mặt tài liệu: trang Swagger UI, tài nguyên tĩnh của UI, OpenAPI JSON/YAML mặc định, tài liệu của từng group và các URL đã tùy biến. Hãy kiểm tra bằng người dùng chưa đăng nhập, người dùng đã đăng nhập nhưng thiếu quyền và người dùng có quyền phù hợp.

## 1. Xác định chính sách truy cập mong muốn

Trước khi kiểm thử, cần ghi rõ tài liệu nào được công khai và ai được phép đọc. Không có một chính sách duy nhất phù hợp cho mọi ứng dụng.

| Loại tài liệu | Chính sách thường gặp | Cách kiểm tra |
|---|---|---|
| API public | Mọi người có thể đọc đặc tả | Truy cập từ phiên ẩn danh và mạng bên ngoài |
| API nội bộ | Chỉ nhân viên hoặc mạng nội bộ được truy cập | Thử từ mạng ngoài và tài khoản không thuộc nhóm |
| API đối tác | Chỉ tài khoản đối tác được cấp quyền | Thử bằng tài khoản đối tác hợp lệ và tài khoản khác |
| API quản trị | Chỉ nhóm vận hành hoặc quản trị được đọc | Thử người dùng thường, người dùng thiếu role và quản trị viên |
| Tài liệu đã tắt | Không cung cấp Swagger UI hoặc OpenAPI trong môi trường đó | Xác minh endpoint trả 404 hoặc phản hồi tương ứng với cấu hình tắt |

Hãy xác định riêng quyền truy cập UI và quyền tải OpenAPI document. Một người có thể được phép xem trang giới thiệu nhưng không được tải tài liệu nội bộ; một hệ thống khác có thể yêu cầu cùng một quyền cho cả UI và JSON.

Không xem URL khó đoán, robots.txt, CORS hoặc việc ẩn nút Swagger UI là cơ chế phân quyền. Người dùng vẫn có thể gọi trực tiếp endpoint tài liệu nếu server cho phép.

## 2. Liệt kê toàn bộ endpoint cần bảo vệ

Với cấu hình mặc định của springdoc, các URL thường gặp gồm:

| Thành phần | URL mặc định |
|---|---|
| OpenAPI document mặc định | /v3/api-docs |
| OpenAPI document dạng YAML | /v3/api-docs.yaml |
| Document group | /v3/api-docs/{group} |
| Trang Swagger UI | /swagger-ui.html |
| Tài nguyên Swagger UI | /swagger-ui/** |

Nếu có nhiều group, ví dụ public, partner và internal, hãy kiểm tra từng URL group. Việc bảo vệ /v3/api-docs nhưng bỏ sót /v3/api-docs/{group} có thể khiến tài liệu nhóm vẫn truy cập được.

Đường dẫn có thể thay đổi qua cấu hình:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /docs
~~~

Khi thay đổi path, security matcher, proxy rule, firewall và kịch bản kiểm thử cũng phải cập nhật. Không giả định endpoint vẫn nằm ở đường dẫn mặc định.

Ngoài các URL trên, hãy kiểm tra endpoint JSON/YAML của từng group, đường dẫn redirect từ /swagger-ui.html tới tài nguyên UI, file cấu hình Swagger UI, URL được cấu hình trong springdoc.swagger-ui.url hoặc urls, URL do API gateway công bố sau khi rewrite path và endpoint tài liệu trên management port nếu ứng dụng có cấu hình riêng.

Tạo danh sách URL từ cấu hình triển khai thực tế và dùng danh sách đó làm cơ sở kiểm tra. Đừng chỉ thử một trang UI rồi kết luận toàn bộ tài liệu đã được bảo vệ.

## 3. Hiểu kết quả HTTP khi kiểm tra quyền

Các mã phản hồi thường giúp xác định policy đang được thực thi:

| Kết quả | Ý nghĩa thường gặp | Cần xác minh |
|---|---|---|
| 200 OK | Request được chấp nhận | Nội dung có đúng tài liệu dự kiến và đúng đối tượng không |
| 302 Found hoặc redirect tương đương | Chuyển tới trang đăng nhập hoặc URL khác | Redirect có đúng cơ chế SSO và không lộ đường dẫn nội bộ không |
| 401 Unauthorized | Chưa có thông tin xác thực hợp lệ | Có WWW-Authenticate phù hợp khi dùng HTTP authentication không |
| 403 Forbidden | Đã xác thực nhưng không đủ quyền, hoặc policy từ chối | Người dùng thiếu authority/role có bị chặn đúng không |
| 404 Not Found | Endpoint không tồn tại hoặc được ẩn có chủ đích | Tài liệu có thực sự bị tắt hay path bị cấu hình sai |
| 5xx | Lỗi ứng dụng, proxy hoặc upstream | Kiểm tra log và health của dịch vụ |

Mã phản hồi phụ thuộc cách xác thực. Với HTTP Basic hoặc Bearer, request chưa xác thực thường nhận 401. Với form login hoặc SSO, trình duyệt có thể được chuyển hướng tới trang đăng nhập. Người đã đăng nhập nhưng thiếu quyền thường nhận 403.

Không đánh giá policy chỉ bằng mã trạng thái. Ví dụ 200 có thể trả về trang đăng nhập HTML thay vì OpenAPI JSON; 302 có thể đưa người dùng tới một host ngoài dự kiến. Hãy kiểm tra cả Content-Type, Location và nội dung phản hồi.

## 4. Bảo vệ tài liệu bằng Spring Security

Ví dụ dưới đây dùng HTTP Basic và authority DOCS_READ để giới hạn tài liệu. Tài khoản thật nên được quản lý qua hệ thống danh tính hoặc kho người dùng phù hợp với môi trường:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain documentationSecurity(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher(
                "/v3/api-docs",
                "/v3/api-docs/**",
                "/v3/api-docs.yaml",
                "/swagger-ui.html",
                "/swagger-ui/**"
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasAuthority("DOCS_READ")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là ví dụ minh họa hai security filter chain. Chain đầu tiên chỉ áp dụng cho các URL tài liệu; chain thứ hai xử lý những request còn lại. @Order và securityMatcher cần được cấu hình nhất quán để request tài liệu không rơi vào một chain ít hạn chế hơn.

Nếu dùng hasRole("API_DOCS"), Spring Security thường kiểm tra authority ROLE_API_DOCS. Nếu dùng hasAuthority("DOCS_READ"), tên authority phải khớp chính xác. Không cấp quyền đọc tài liệu cho mọi tài khoản chỉ để Swagger UI hoạt động.

Trong hệ thống dùng form login, OAuth2 Login, SSO hoặc JWT, thay HTTP Basic bằng cơ chế xác thực tương ứng. Chính sách authorization cho các URL tài liệu vẫn cần được áp dụng rõ ràng.

## 5. Bảo vệ các document group

Endpoint /v3/api-docs/{group} cũng là tài liệu có thể chứa schema, endpoint và metadata riêng. Hãy xác minh tất cả group đều nằm trong vùng bảo vệ dự kiến.

Ví dụ muốn giới hạn tài liệu nội bộ bằng authority riêng:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        "/v3/api-docs/internal",
        "/v3/api-docs/internal/**"
    ).hasAuthority("INTERNAL_DOCS_READ")
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml",
        "/swagger-ui.html",
        "/swagger-ui/**"
    ).hasAuthority("DOCS_READ")
);
~~~

Đặt matcher cụ thể trước matcher tổng quát để group nhạy cảm không bị rule rộng hơn bắt trước. Khi dùng nhiều SecurityFilterChain, hãy xác minh thứ tự chain và matcher cấp chain; thứ tự matcher bên trong một chain không thể sửa một request đã được chain trước đó nhận.

Nếu Swagger UI hiển thị danh sách nhiều tài liệu, người dùng có thể nhìn thấy tên group dù họ không có quyền tải nội dung của group đó. Cân nhắc chỉ đưa các group được phép vào danh sách springdoc.swagger-ui.urls, hoặc dùng cơ chế đăng nhập và phân quyền phù hợp cho cả danh sách lẫn từng document.

Không dựa vào việc xóa một group khỏi dropdown để bảo vệ nội dung. Nếu URL group vẫn được phục vụ, người dùng có thể gọi trực tiếp URL đó.

## 6. Phân quyền theo role hoặc scope

Có thể phân quyền bằng role của người dùng:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/swagger-ui.html", "/swagger-ui/**")
        .hasRole("API_DOCS")
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).hasRole("API_DOCS")
    .anyRequest().authenticated()
);
~~~

Hoặc dùng scope trong access token khi tài liệu được bảo vệ bằng OAuth2 Resource Server:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers(
            "/v3/api-docs",
            "/v3/api-docs/**",
            "/v3/api-docs.yaml",
            "/swagger-ui.html",
            "/swagger-ui/**"
        ).hasAuthority("SCOPE_api.docs.read")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(resourceServer -> resourceServer
        .jwt(Customizer.withDefaults())
    );
~~~

Authority ví dụ phải được ánh xạ từ claim hoặc scope thực tế trong token. Hãy xác minh issuer, audience, chữ ký, thời hạn và cách Spring Security ánh xạ scope trước khi dùng rule này.

Một lưu ý quan trọng với Swagger UI: UI thường cần tải OpenAPI document trước khi hiển thị đầy đủ các operation và nút Authorize. Nếu chính document JSON chỉ chấp nhận Bearer token nhưng UI chưa có cách lấy và gửi token trước khi tải spec, người dùng có thể gặp vòng phụ thuộc: cần spec để đăng nhập nhưng cần đăng nhập để tải spec. Với UI tương tác, cân nhắc session/SSO hoặc một cơ chế xác thực browser phù hợp; không nhúng access token tĩnh vào cấu hình UI để né vấn đề này.

## 7. Kiểm tra matcher và thứ tự filter chain

Một cấu hình authorization có thể trông đúng nhưng vẫn không bảo vệ endpoint nếu request được xử lý bởi chain khác.

Các điểm cần kiểm tra:

1. securityMatcher của chain tài liệu có bao phủ toàn bộ URL thực tế không?
2. Chain tài liệu có @Order ưu tiên phù hợp so với chain tổng quát không?
3. Có chain nào trước đó nhận request và dùng permitAll() không?
4. Các matcher cụ thể cho group nội bộ có đứng trước matcher tổng quát không?
5. URL sau reverse proxy có được rewrite trước khi Spring Security nhận request không?
6. Khi thay springdoc.api-docs.path hoặc springdoc.swagger-ui.path, matcher có được cập nhật không?
7. Có cấu hình web.ignoring() hoặc bypass filter nào vô tình bỏ qua bảo vệ không?

Không dùng web.ignoring() cho tài liệu cần phân quyền. Bỏ qua security filter có thể khiến endpoint không được xác thực và authorization như dự kiến. Với tài nguyên cần công khai, thường nên dùng permitAll() trong chain thích hợp để vẫn giữ các filter bảo vệ chung.

## 8. Kiểm tra sau reverse proxy hoặc API gateway

Trong production, client thường truy cập qua domain hoặc gateway, không gọi trực tiếp cổng của Spring Boot. Gateway có thể xác thực một lớp, rewrite path hoặc cache response. Vì vậy, cần kiểm tra từ đúng URL công khai mà người dùng sẽ truy cập.

~~~text
Client
  |
  v
https://api.example.com/docs
  |
  v
Reverse proxy / API gateway
  |
  | rewrite /docs to /swagger-ui.html
  | forward identity headers (nếu có)
  v
Spring Boot + Spring Security + springdoc
  |
  +--> Swagger UI
  +--> /v3/api-docs
  +--> /v3/api-docs/{group}
~~~

Kiểm tra:

- Gateway không mở public một path tài liệu nội bộ.
- Rewrite rule không bỏ qua authentication middleware.
- Header định danh người dùng chỉ được tin cậy khi gateway loại bỏ header giả từ client và tự đặt lại.
- Spring Boot không thể bị truy cập trực tiếp từ mạng ngoài để bypass gateway nếu kiến trúc yêu cầu mọi request đi qua gateway.
- X-Forwarded-* hoặc forwarded header được xử lý đúng để URL công bố trong OpenAPI khớp domain công khai.
- Gateway và CDN không cache response tài liệu có kiểm soát truy cập thành nội dung dùng chung cho người chưa xác thực.

Nếu gateway đã xác thực người dùng rồi truyền identity header tới ứng dụng, cần giới hạn kết nối backend để chỉ gateway đáng tin cậy có thể gửi header đó. Nếu client có thể tự gửi X-User, X-Roles hoặc header tương tự tới backend, họ có thể giả mạo danh tính.

## 9. Kiểm tra cache và phân phối nội dung

OpenAPI JSON/YAML có thể chứa endpoint nội bộ, tên schema, mô hình dữ liệu và thông tin triển khai. Với tài liệu có kiểm soát truy cập, cần bảo đảm proxy, CDN và browser không dùng chung response giữa các người dùng hoặc giữa môi trường.

Kiểm tra các header:

- Cache-Control: chính sách cache phù hợp với độ nhạy và cơ chế xác thực.
- Vary: nếu response thay đổi theo header xác thực hoặc cookie, cache phải phân biệt đúng ngữ cảnh.
- Age hoặc header riêng của CDN: giúp nhận biết response có thể đến từ cache.
- Via hoặc header gateway: hỗ trợ xác định lớp nào đã phục vụ response.

Với tài liệu nhạy cảm, cân nhắc Cache-Control: private, no-store hoặc chính sách tương đương theo yêu cầu bảo mật. Không chỉ kiểm tra header ở ứng dụng; hãy gọi qua domain production để xác nhận gateway/CDN không ghi đè chính sách.

Khi chuyển tài liệu từ private sang public hoặc ngược lại, xem xét purge cache cũ và kiểm tra các bản sao đã được phân phối. Xóa đường dẫn ở origin không tự xóa nội dung đã được CDN cache.

## 10. Kiểm tra CSRF, CORS và xác thực trình duyệt

Swagger UI thường tải tài liệu bằng các request GET. Những request đọc dữ liệu này thường không cần CSRF token. Tuy nhiên, nút Try it out có thể gửi POST, PUT, PATCH hoặc DELETE tới API; nếu ứng dụng dùng cookie/session authentication, các request thay đổi dữ liệu vẫn cần chính sách CSRF phù hợp.

Không tắt CSRF toàn cục chỉ để Swagger UI hoạt động. Hãy xác định request nào dùng cookie, request nào dùng Bearer token và áp dụng chính sách theo đúng cơ chế xác thực.

CORS chỉ điều khiển browser có được phép đọc response cross-origin. CORS không thay thế authentication hoặc authorization. Nếu Swagger UI và API cùng origin, thường không cần mở CORS riêng cho việc tải tài liệu. Nếu chúng khác origin, hãy chỉ cho phép origin, method và header cần thiết.

Khi kiểm tra qua browser, mở Developer Tools và xem Network:

- Trang UI có tải được HTML, JavaScript, CSS và cấu hình không?
- Request tới OpenAPI JSON/YAML có gửi cookie hoặc token đúng cách không?
- Redirect đăng nhập có quay lại đúng trang không?
- Có lỗi CORS hoặc mixed content không?
- Request Try it out có CSRF token hoặc Authorization header cần thiết không?
- Response có vô tình chứa token, cookie hoặc thông tin xác thực trong body không?

## 11. Kiểm thử bằng curl từ môi trường triển khai

Thực hiện kiểm tra từ máy hoặc runner có thể truy cập domain công khai. Các lệnh dưới đây dùng URL minh họa.

### 11.1. Request không có thông tin xác thực

~~~bash
curl -i https://api.example.com/v3/api-docs
curl -i https://api.example.com/v3/api-docs.yaml
curl -i https://api.example.com/swagger-ui.html
curl -i https://api.example.com/swagger-ui/index.html
curl -i https://api.example.com/v3/api-docs/internal
~~~

Nếu chính sách yêu cầu đăng nhập, các request này phải nhận kết quả từ chối hoặc redirect tới cơ chế đăng nhập đã định. Không được nhận tài liệu nội bộ dưới dạng 200 chỉ vì thử qua một path khác.

### 11.2. Request bằng tài khoản có quyền

Với HTTP Basic, có thể để curl hỏi mật khẩu thay vì ghi mật khẩu trong command:

~~~bash
curl -i -u docs-reader https://api.example.com/v3/api-docs
~~~

Sau đó thử các URL group và Swagger UI bằng cùng tài khoản. Nếu dùng Bearer token, cung cấp token qua một biến môi trường trong shell kiểm thử và tránh lưu token trong file script hoặc lịch sử command.

### 11.3. Request bằng tài khoản thiếu quyền

Đăng nhập bằng một tài khoản hợp lệ nhưng không có authority đọc tài liệu. Kết quả mong đợi thường là 403. Kiểm tra riêng group nội bộ để chắc chắn tài khoản chỉ có quyền public không đọc được tài liệu internal.

Không coi việc tài khoản không thể mở trang UI là đủ. Hãy gọi trực tiếp các endpoint JSON/YAML, vì người dùng có thể bỏ qua giao diện.

## 12. Kiểm thử tự động với MockMvc

Có thể dùng Spring Boot test để xác minh policy ngay trong ứng dụng. Ví dụ dưới đây giả định endpoint tài liệu được bảo vệ bằng authority DOCS_READ:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentationAccessTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousUserCannotReadOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userWithoutDocumentationAuthorityIsForbidden() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .with(user("ordinary-user")))
            .andExpect(status().isForbidden());
    }

    @Test
    void documentationReaderCanReadOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .with(user("docs-reader")
                    .authorities(new SimpleGrantedAuthority("DOCS_READ"))))
            .andExpect(status().isOk());
    }
}
~~~

Ví dụ kiểm thử giả định HTTP Basic hoặc một cơ chế trả 401 cho anonymous. Nếu ứng dụng dùng form login, kết quả có thể là redirect; hãy điều chỉnh assertion theo chính sách đã chọn. Cần thêm test cho YAML, Swagger UI, tài nguyên tĩnh và từng group, không chỉ test /v3/api-docs.

Các test dùng request post processor của Spring Security, vì vậy cần dependency spring-security-test ở test scope. MockMvc kiểm tra filter chain trong ứng dụng. Nó không kiểm tra cấu hình gateway, CDN, DNS hoặc network policy production. Vì vậy vẫn cần kiểm thử tích hợp qua domain triển khai.

## 13. Ma trận kiểm thử người dùng và endpoint

Lập ma trận để tránh bỏ sót trường hợp:

| Người gọi | Swagger UI | OpenAPI mặc định | Group public | Group internal |
|---|---|---|---|---|
| Chưa đăng nhập | Theo policy | Theo policy | Theo policy | Theo policy |
| Người dùng thường | Từ chối hoặc chỉ xem UI | Từ chối | Từ chối hoặc cho phép theo policy | Từ chối |
| Tài khoản đối tác | Theo policy đối tác | Theo policy | Cho phép | Từ chối |
| Nhân viên nội bộ | Cho phép | Cho phép | Cho phép nếu được cấp | Theo role nội bộ |
| Quản trị viên | Cho phép | Cho phép | Cho phép | Cho phép |

Điền kết quả mong đợi cụ thể theo hệ thống, sau đó ghi nhận HTTP status và nội dung thực tế cho từng ô. Nếu policy phân quyền khác nhau giữa UI và document, thể hiện điều đó rõ ràng trong ma trận.

## 14. Khi muốn tắt tài liệu trong production

Nếu môi trường production không cần phát hành tài liệu, có thể tắt endpoint OpenAPI và Swagger UI bằng cấu hình:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Sau khi triển khai, xác minh các endpoint mặc định và endpoint group không còn phục vụ tài liệu. Kết quả thường là 404 hoặc phản hồi tương ứng với routing của ứng dụng. Nếu tài liệu vẫn xuất hiện, kiểm tra profile đang active, cấu hình override, gateway route và artifact đang chạy.

Tắt Swagger UI nhưng để OpenAPI JSON hoạt động vẫn có thể công khai toàn bộ hợp đồng. Ngược lại, tắt OpenAPI nhưng giữ trang UI có thể khiến UI không tải được spec. Hãy quyết định rõ có tắt cả hai hay chỉ một phần.

Nếu cần tài liệu cho đội vận hành nhưng không muốn công khai trên production, có thể triển khai một portal nội bộ hoặc một profile/instance riêng được bảo vệ bằng mạng và identity policy phù hợp.

## 15. Phân biệt bảo vệ tài liệu với bảo vệ API

Đặt security rule cho /v3/api-docs/** chỉ bảo vệ tài liệu. Nó không tự bảo vệ endpoint nghiệp vụ như /api/orders hoặc /api/admin.

Ngược lại, bảo vệ API bằng JWT không có nghĩa Swagger UI và OpenAPI đã được bảo vệ. Hai bề mặt cần được kiểm thử độc lập:

| Bề mặt | Câu hỏi cần trả lời |
|---|---|
| Swagger UI | Ai được tải trang và tài nguyên UI? |
| OpenAPI JSON/YAML | Ai được đọc schema, path, operation và security metadata? |
| API runtime | Ai được gọi endpoint và thực hiện hành động? |
| Authorization server | Ai được đăng nhập, cấp token và xin scope? |
| Gateway/CDN | Ai có thể truy cập hoặc nhận nội dung đã cache? |

Tài liệu có thể tiết lộ tên endpoint nội bộ, cấu trúc request/response, cơ chế bảo mật và mô hình nghiệp vụ. Dù không chứa dữ liệu thật, đây vẫn có thể là thông tin cần giới hạn theo chính sách của tổ chức.

## 16. Những lỗi thường gặp sau triển khai

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ bảo vệ /swagger-ui.html | JSON/YAML vẫn truy cập công khai | Bảo vệ cả OpenAPI endpoint và tài nguyên UI |
| Bỏ sót /v3/api-docs/{group} | Group nội bộ vẫn bị lộ | Dùng matcher bao phủ group và kiểm thử từng group |
| Matcher dùng path mặc định sau khi đã đổi cấu hình | Endpoint mới không nằm trong rule | Đồng bộ matcher với springdoc.api-docs.path và swagger-ui.path |
| Chain tổng quát đứng trước chain tài liệu | Request tài liệu bị xử lý bởi policy khác | Kiểm tra @Order và securityMatcher |
| Dùng permitAll() cho tài nguyên UI nhưng quên JSON | UI tải được nhưng spec có thể bị lộ hoặc không hoạt động | Xác định policy riêng cho HTML, assets và documents |
| Chỉ ẩn group khỏi dropdown | Người dùng vẫn gọi URL group trực tiếp | Phân quyền endpoint group ở server |
| Gateway rewrite bỏ qua xác thực | URL công khai không tuân theo policy ứng dụng | Kiểm thử qua gateway và kiểm tra rewrite rule |
| CDN cache tài liệu private | Người chưa xác thực có thể nhận bản cache | Cấu hình cache private/no-store và purge cache |
| Dùng CORS thay cho authorization | Client ngoài browser vẫn gọi được endpoint | Áp dụng authentication và authorization tại server |
| Tắt UI nhưng quên OpenAPI JSON | Hợp đồng vẫn được phát hành | Tắt và kiểm tra cả hai nếu production không cần docs |
| Tài liệu yêu cầu Bearer token nhưng UI không tải được spec | Vòng phụ thuộc trước khi Authorize | Dùng session/SSO hoặc cơ chế tải spec phù hợp |
| Chỉ kiểm thử bằng tài khoản quản trị | Không phát hiện người dùng thường đọc được tài liệu | Kiểm thử anonymous, thiếu quyền và đủ quyền |

## 17. Quy trình xác minh trước và sau release

Thực hiện theo thứ tự:

1. Ghi chính sách public, partner, internal và admin cho từng tài liệu.
2. Liệt kê UI, assets, JSON, YAML, group và URL tùy biến.
3. Đối chiếu springdoc.*.path với matcher của Spring Security.
4. Kiểm tra thứ tự SecurityFilterChain và authority/role/scope.
5. Kiểm thử anonymous, user thiếu quyền và user đủ quyền bằng MockMvc.
6. Triển khai lên môi trường kiểm thử và gọi endpoint qua domain gateway.
7. Kiểm tra redirect, status, Content-Type, Location và nội dung response.
8. Kiểm tra cache, forwarded headers, path rewrite và khả năng bypass gateway.
9. Mở Swagger UI bằng browser và kiểm tra toàn bộ request trong Network panel.
10. Xác minh từng document group bằng URL trực tiếp.
11. Nếu production không phát hành docs, bật cấu hình disable và xác minh endpoint không còn phục vụ.
12. Lưu lại kết quả kiểm thử để đối chiếu sau mỗi lần thay đổi security hoặc hạ tầng.

Sau khi thay đổi phiên bản Spring Security, springdoc, path, gateway hoặc SSO, chạy lại các kiểm tra liên quan. Một thay đổi tưởng như chỉ ảnh hưởng giao diện có thể làm URL document hoặc filter chain thay đổi.

## 18. Ghi nhớ

- Xác định rõ ai được đọc Swagger UI, OpenAPI JSON/YAML và từng document group.
- Bảo vệ cả trang UI, tài nguyên tĩnh, endpoint mặc định, YAML và group.
- Kiểm tra path thực tế sau khi cấu hình springdoc.api-docs.path hoặc springdoc.swagger-ui.path.
- Xác minh thứ tự SecurityFilterChain, securityMatcher và matcher theo role/scope.
- Dùng 401, 403, redirect hoặc 404 theo policy; kiểm tra cả nội dung và header response.
- Kiểm thử từ domain production qua reverse proxy/API gateway, không chỉ gọi localhost.
- Kiểm tra cache/CDN để tài liệu private không được chia sẻ giữa người dùng.
- CORS không thay thế authentication; không tắt CSRF toàn cục chỉ để Swagger UI hoạt động.
- MockMvc giúp kiểm thử filter chain; cần thêm kiểm thử tích hợp qua hạ tầng triển khai.
- Nếu không phát hành tài liệu trong production, tắt cả OpenAPI và Swagger UI rồi xác minh endpoint thực tế.
- Bảo vệ tài liệu không thay thế bảo vệ API runtime; hai bề mặt cần policy và kiểm thử riêng.

Sau khi triển khai springdoc-openapi, hãy xác minh chính sách bằng các request thực tế từ nhiều loại tài khoản và qua đúng đường đi production. Chỉ kết luận tài liệu được bảo vệ khi mọi URL UI, JSON/YAML và document group đều trả kết quả đúng với ma trận quyền đã định, kể cả qua gateway và cache.

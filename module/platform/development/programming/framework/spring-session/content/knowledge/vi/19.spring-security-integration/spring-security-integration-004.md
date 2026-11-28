# Khôi phục và lưu SecurityContext theo phiên bản, cấu hình Spring Security

Spring Security lưu trạng thái xác thực hiện tại trong một đối tượng SecurityContext. Trong ứng dụng Servlet dùng Spring Session, SecurityContext thường được lưu như một thuộc tính của HttpSession; Spring Session đưa thuộc tính đó vào kho dùng chung như Redis hoặc JDBC. Nhờ vậy, request tiếp theo có thể đến một instance khác nhưng vẫn khôi phục được Authentication của người dùng.

Điểm quan trọng là SecurityContextHolder và kho session có hai vai trò khác nhau. SecurityContextHolder cung cấp ngữ cảnh xác thực cho code đang xử lý request hiện tại. SecurityContextRepository chịu trách nhiệm đọc và ghi ngữ cảnh để request sau có thể khôi phục. Đặc biệt từ Spring Security 6, việc đặt SecurityContext vào SecurityContextHolder không đồng nghĩa nó sẽ tự động được lưu vào session. Cấu hình và code xác thực tùy chỉnh cần tuân thủ chính sách lưu tường minh.

## 1. SecurityContext gồm những gì?

SecurityContext chứa một đối tượng Authentication. Authentication thường biểu diễn:

- Principal: danh tính người dùng hoặc client đã xác thực.
- Authorities: các quyền hoặc vai trò được cấp.
- Trạng thái authenticated: cho biết xác thực đã hoàn tất hay chưa.
- Details: thông tin phụ trợ của quá trình xác thực, nếu có.

Ví dụ, sau khi người dùng đăng nhập, Authentication có thể chứa UserDetails làm principal và danh sách quyền như ROLE_USER. Spring Security đặt SecurityContext hiện tại vào SecurityContextHolder để các thành phần như authorization filter, method security và controller có thể truy cập.

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null && authentication.isAuthenticated()) {
    Object principal = authentication.getPrincipal();
}
~~~

Không nên coi SecurityContextHolder là kho lưu trữ lâu dài. Trong mô hình Servlet, ngữ cảnh thường gắn với request/thread và được dọn khi request kết thúc. Để request kế tiếp nhận ra người dùng, SecurityContext phải được khôi phục từ SecurityContextRepository.

## 2. Vai trò của SecurityContextRepository

SecurityContextRepository là abstraction của Spring Security để tải và lưu SecurityContext. Trong tích hợp Servlet truyền thống, implementation quan trọng là HttpSessionSecurityContextRepository. Nó lưu ngữ cảnh vào HttpSession, thường dưới thuộc tính có tên SPRING_SECURITY_CONTEXT.

Khi ứng dụng dùng Spring Session, HttpSession đã được Spring Session thay bằng session repository dùng chung. Do đó, SecurityContext được lưu qua HttpSession cũng đi vào Redis hoặc JDBC mà không cần controller tự thao tác với Redis key hoặc bảng JDBC.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as Spring Security filters
    participant H as SecurityContextHolder
    participant R as SecurityContextRepository
    participant S as Spring Session
    participant D as Redis hoặc JDBC
    C->>F: Request có session ID
    F->>R: loadDeferredContext / loadContext
    R->>S: Đọc HttpSession
    S->>D: Tìm session và thuộc tính
    D-->>S: Session data
    S-->>R: SPRING_SECURITY_CONTEXT
    R-->>H: SecurityContext
    F->>H: Đặt ngữ cảnh cho request
    F-->>C: Xử lý request và response
    Note over R,D: Khi có xác thực mới, context phải được lưu theo chính sách
~~~

Các API tải ngữ cảnh khác nhau giữa các thế hệ Spring Security. Các phiên bản mới có cơ chế tải trì hoãn qua DeferredSecurityContext; code ứng dụng nên phụ thuộc vào SecurityContextRepository và cấu hình DSL thay vì gọi API nội bộ của filter.

### 2.1. HttpSessionSecurityContextRepository

Repository này liên kết SecurityContext với HttpSession. Khi tải ngữ cảnh, nó tìm thuộc tính đã lưu trong session. Khi lưu, nó có thể tạo session nếu được phép và nếu cần thiết. Khi context rỗng hoặc không còn xác thực, hành vi xóa/không lưu phụ thuộc implementation và phiên bản.

Không nên tự đọc hoặc tự ghi thuộc tính SPRING_SECURITY_CONTEXT bằng session.setAttribute trong controller. Hãy dùng SecurityContextRepository để Spring Security xử lý vòng đời, session creation policy và các chi tiết tương thích.

### 2.2. DelegatingSecurityContextRepository

Các cấu hình Spring Security hiện đại thường dùng DelegatingSecurityContextRepository để kết hợp nhiều repository. Một cấu hình phổ biến kết hợp:

- RequestAttributeSecurityContextRepository: giữ context trong phạm vi request và hỗ trợ các lần dispatch như ERROR.
- HttpSessionSecurityContextRepository: giữ context giữa các request thông qua HttpSession.

Việc kết hợp giúp vừa duy trì context trong các dispatch của cùng request, vừa lưu trạng thái đăng nhập qua session. Repository mặc định có thể khác theo phiên bản và cấu hình; chỉ thay nó khi ứng dụng có nhu cầu rõ ràng.

## 3. Spring Session kết nối với Spring Security như thế nào?

Spring Session tích hợp vào Servlet container bằng SessionRepositoryFilter. Filter này bọc request/response để HttpSession mà ứng dụng sử dụng được ánh xạ đến SessionRepository. Spring Security không cần biết session được lưu ở bộ nhớ container, Redis hay JDBC; nó tiếp tục làm việc qua HttpSession và SecurityContextRepository.

Khi request đến:

1. SessionRepositoryFilter khôi phục HttpSession từ session ID client gửi.
2. Spring Security tải SecurityContext thông qua SecurityContextRepository.
3. SecurityContext được đặt vào SecurityContextHolder trong phạm vi xử lý request.
4. Các filter xác thực và phân quyền dùng Authentication và authorities.
5. Nếu có đăng nhập mới hoặc thay đổi context cần lưu, Spring Security ghi context qua repository.
6. Spring Session lưu thuộc tính session vào kho chia sẻ theo cấu hình.

Vì vậy, thứ tự filter và việc Spring Session filter chạy trước phần xử lý bảo mật có ý nghĩa. Trong ứng dụng Spring Boot được cấu hình chuẩn, starter và auto-configuration thường thiết lập thứ tự cần thiết. Nếu tự đăng ký filter hoặc dùng nhiều FilterRegistrationBean, phải xác minh SessionRepositoryFilter được đặt đúng vị trí và chỉ đăng ký một lần.

## 4. Cấu hình SecurityFilterChain với session dùng chung

Một cấu hình Servlet cơ bản có thể dùng form login, cho phép session khi cần và sử dụng SecurityContextRepository kết hợp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository securityContextRepository)
            throws Exception {

        http
            .securityContext(context -> context
                .securityContextRepository(securityContextRepository)
                .requireExplicitSave(true)
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
~~~

Đây là ví dụ cho ứng dụng Servlet dùng Spring Security hiện đại. Các import và DSL cần khớp phiên bản dependency của dự án. Nếu cấu hình mặc định đã cung cấp repository phù hợp, không cần khai báo bean chỉ để lặp lại mặc định. Điểm quan trọng là toàn bộ filter chain và code xác thực tùy chỉnh phải dùng cùng SecurityContextRepository.

SessionCreationPolicy.IF_REQUIRED cho phép tạo session khi cần để lưu SecurityContext hoặc các tính năng khác. Nếu ứng dụng cần xác thực không trạng thái, phải chọn chính sách và cơ chế xác thực khác phù hợp; không dùng STATELESS rồi kỳ vọng SecurityContext được khôi phục từ HttpSession.

## 5. Thay đổi quan trọng giữa các phiên bản Spring Security

Một thay đổi cần chú ý khi nâng cấp từ các cấu hình Spring Security cũ lên 5.8/6.x là cách lưu SecurityContext.

| Cơ chế | Hành vi tải | Hành vi lưu |
|---|---|---|
| SecurityContextPersistenceFilter kiểu cũ | Tải context trước khi xử lý request | Theo dõi thay đổi và tự lưu khi request hoàn tất |
| SecurityContextHolderFilter hiện đại | Tải context, thường theo cơ chế deferred | Không tự động lưu mọi thay đổi; thành phần xác thực phải lưu tường minh |

Trong mô hình cũ, code có thể đặt Authentication vào SecurityContextHolder và dựa vào filter tự lưu context khi response hoàn tất. Với mô hình hiện đại, SecurityContextHolderFilter chỉ đảm nhiệm tải context và dọn holder; nó không tự lưu thay đổi chỉ vì ứng dụng gọi setContext.

Spring Security 6 mặc định yêu cầu explicit save. Cách này làm rõ nơi nào chịu trách nhiệm lưu trạng thái xác thực và tránh việc mọi thay đổi tạm thời trong request vô tình tạo hoặc cập nhật session.

### 5.1. Dấu hiệu lỗi sau nâng cấp

Một lỗi thường gặp:

1. Endpoint đăng nhập tùy chỉnh xác thực username/password thành công.
2. Code tạo SecurityContext và gọi SecurityContextHolder.setContext(context).
3. Response trả thành công.
4. Request kế tiếp đến nhưng người dùng bị xem là anonymous.

Nguyên nhân có thể là context chỉ được đặt trong holder của request hiện tại mà không được lưu qua SecurityContextRepository. Khi request kết thúc, holder được dọn; request sau không có context để tải từ session.

### 5.2. requireExplicitSave

Trong cấu hình hiện đại, requireExplicitSave(true) thể hiện rõ việc code xác thực phải lưu context. Một số phiên bản cho phép đặt false để chuyển tiếp hành vi cũ dựa trên SecurityContextPersistenceFilter. Đây có thể là cầu nối migration ngắn hạn, nhưng không nên dùng để che giấu các filter tùy chỉnh chưa được sửa.

Khi nâng cấp, hãy kiểm kê các điểm tự xác thực như custom authentication filter, REST login controller, SSO callback, remember-me integration hoặc cơ chế impersonation. Mỗi điểm tạo Authentication mới cần xác định rõ nơi lưu context và thời điểm lưu.

## 6. Lưu SecurityContext tường minh trong luồng đăng nhập tùy chỉnh

Nếu ứng dụng tự triển khai endpoint đăng nhập thay vì dùng formLogin, sau khi AuthenticationManager xác thực thành công, cần tạo context và lưu nó bằng repository.

Ví dụ controller Servlet:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@RestController
public class LoginController {

    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository securityContextRepository;

    public LoginController(
            AuthenticationManager authenticationManager,
            SecurityContextRepository securityContextRepository) {
        this.authenticationManager = authenticationManager;
        this.securityContextRepository = securityContextRepository;
    }

    @PostMapping("/api/login")
    public ResponseEntity<Void> login(
            @RequestBody LoginRequest body,
            HttpServletRequest request,
            HttpServletResponse response) {

        Authentication authentication =
            authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    body.username(), body.password()
                )
            );

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        securityContextRepository.saveContext(context, request, response);
        return ResponseEntity.noContent().build();
    }

    public record LoginRequest(String username, String password) {}
}
~~~

Ví dụ minh họa nguyên tắc; ứng dụng cần cấu hình AuthenticationManager, xử lý AuthenticationException, CSRF, giới hạn đăng nhập và phản hồi lỗi. Phải gọi saveContext trước khi response được commit để repository có thể tạo session và gửi session cookie nếu cần.

Không chỉ gọi SecurityContextHolder.setContext. Cũng không tự gọi session.setAttribute("SPRING_SECURITY_CONTEXT", context), vì làm vậy bỏ qua repository, request-scoped storage và chính sách của Spring Security.

### 6.1. Built-in authentication filter

Các cơ chế xác thực tích hợp như form login thường đã biết cách lưu context qua SecurityContextRepository. Không cần controller tự lưu lần thứ hai khi để filter chuẩn xử lý toàn bộ luồng. Việc lưu tường minh đặc biệt quan trọng với code xác thực do ứng dụng tự viết.

## 7. SessionCreationPolicy ảnh hưởng đến việc lưu context

SessionCreationPolicy điều khiển Spring Security có tạo hoặc sử dụng HttpSession hay không:

| Chính sách | Hành vi | Tác động tới SecurityContext |
|---|---|---|
| ALWAYS | Luôn tạo session | Có session để lưu context |
| IF_REQUIRED | Tạo khi tính năng cần | Thường phù hợp ứng dụng đăng nhập bằng session |
| NEVER | Không chủ động tạo session nhưng có thể dùng session sẵn có | Có thể khôi phục context nếu session đã tồn tại; không nên kỳ vọng tự tạo session mới |
| STATELESS | Không tạo và không dùng HttpSession để lưu SecurityContext | Không dùng session-backed authentication |

Nếu dùng Spring Session Redis/JDBC cho đăng nhập web truyền thống, IF_REQUIRED thường là lựa chọn phù hợp. Tuy nhiên, các thành phần khác như request cache, CSRF hoặc flow xác thực cũng có thể ảnh hưởng việc tạo session. Cần kiểm tra toàn bộ cấu hình thay vì chỉ nhìn một dòng sessionCreationPolicy.

Không chọn STATELESS chỉ để giảm tải session trong khi vẫn mong SecurityContext tồn tại qua nhiều request. Nếu chọn stateless, dùng cơ chế credential/token và SecurityContextRepository phù hợp với mô hình đó.

## 8. Session fixation protection và đổi session ID

Trước đăng nhập, client có thể đã có session ẩn danh. Sau khi xác thực thành công, Spring Security cần ngăn kẻ tấn công lợi dụng session ID đã biết trước. Chính sách session fixation protection thường thay đổi session ID sau xác thực.

Với Servlet container hỗ trợ Servlet 3.1+, chiến lược changeSessionId() đổi ID của session hiện tại mà vẫn giữ các thuộc tính hợp lệ. Các chiến lược khác có thể tạo session mới và chuyển thuộc tính hoặc thay đổi hành vi tùy cấu hình.

Khi dùng Spring Session:

- Để Spring Security thực hiện session fixation protection qua API Servlet.
- Đảm bảo SessionRepositoryFilter được đăng ký đúng để thao tác session ID đi qua Spring Session.
- Kiểm tra ID mới được gửi cho client sau đăng nhập.
- Xác nhận request kế tiếp trên instance khác vẫn khôi phục được SecurityContext.
- Không tự giữ session ID cũ trong JavaScript hoặc cache client.

Không tự viết logic đổi ID bằng cách tạo một chuỗi ngẫu nhiên rồi gán vào cookie. Session ID phải được framework tạo và quản lý theo cơ chế an toàn.

## 9. Logout và xóa SecurityContext khỏi kho phiên

Logout cần xóa SecurityContext khỏi holder và kết thúc hoặc làm sạch session theo chính sách. Cấu hình logout tích hợp của Spring Security thường phối hợp các handler để:

- Xóa Authentication khỏi SecurityContextHolder.
- Gọi SecurityContextLogoutHandler để xóa context và invalidate HttpSession theo cấu hình.
- Xóa session cookie hoặc yêu cầu resolver hết hạn cookie.
- Chuyển hướng hoặc trả response phù hợp.

Khi dùng Spring Session, invalidate HttpSession sẽ được ánh xạ tới repository dùng chung. Dữ liệu session bị xóa hoặc vô hiệu hóa theo implementation; request tiếp theo mang ID cũ không được khôi phục trạng thái xác thực.

Ví dụ cấu hình:

~~~java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("SESSION")
);
~~~

Cookie name SESSION chỉ là ví dụ; phải dùng đúng tên cookie mà resolver thực tế phát. Với API REST, có thể trả 204 thay vì redirect. Logout endpoint cần bảo vệ CSRF theo mô hình ứng dụng; không biến logout thành GET không được bảo vệ.

## 10. SecurityContext và serialization trong Redis/JDBC

SecurityContext là object graph, không chỉ là một chuỗi username. Nó có thể chứa Authentication, principal, authorities và details. Khi Spring Session lưu thuộc tính này trong Redis hoặc JDBC, serializer của repository phải có khả năng chuyển đổi và khôi phục toàn bộ object graph.

Các lưu ý:

- Nếu dùng Java serialization, các lớp principal và object lồng bên trong cần tương thích với serializer.
- Custom UserDetails nên nhỏ, ổn định và triển khai Serializable nếu serializer yêu cầu.
- Không đặt entity ORM lớn, proxy lazy, service hoặc resource đang mở vào principal/details.
- Nếu dùng JSON serializer, cần cấu hình type mapping an toàn cho SecurityContext và các kiểu Authentication được dùng.
- Không bật polymorphic typing rộng để deserialize mọi class từ payload.
- Tất cả node phải dùng phiên bản Spring Security, Spring Session và serializer tương thích trong giai đoạn rolling deployment.

Không tự serialize SecurityContext thành JSON trong controller. Để SecurityContextRepository và SessionRepository quản lý dữ liệu theo cấu hình đã chọn.

### 10.1. Nâng cấp phiên bản khi session cũ còn tồn tại

Một lần deploy mới có thể thay đổi class principal, authorities hoặc cấu hình serializer. Session được ghi bởi phiên bản cũ vẫn có thể còn trong Redis/JDBC và được đọc bởi phiên bản mới.

Trước khi nâng cấp:

1. Lưu fixture SecurityContext đại diện từ phiên bản hiện tại trong môi trường test an toàn.
2. Xác minh phiên bản mới deserialize được fixture cũ.
3. Kiểm tra cả principal tùy chỉnh, authorities và details.
4. Nếu rolling deployment có hai phiên bản cùng chạy, xác định node cũ có thể đọc dữ liệu do node mới ghi hay không.
5. Nếu format không tương thích, triển khai reader tương thích trước writer mới hoặc lên kế hoạch hết hạn/thu hồi session cũ.

Không ghi SecurityContext hoặc session ID thật vào repository test công khai hay log. Fixture cần được làm sạch dữ liệu nhạy cảm.

## 11. Quản lý nhiều phiên đăng nhập

Một người dùng có thể có nhiều session trên trình duyệt hoặc thiết bị khác nhau. Spring Security hỗ trợ kiểm soát concurrent session, nhưng khi dùng Spring Session trên nhiều instance, registry cần tra cứu được các session từ kho chia sẻ.

Trong Servlet, có thể dùng SpringSessionBackedSessionRegistry cùng repository hỗ trợ tìm session theo principal. Điều này giúp kiểm soát giới hạn phiên trên toàn cụm thay vì chỉ nhìn các session mà một JVM đã thấy.

Các điều kiện cần kiểm tra:

- Repository triển khai API index theo principal phù hợp.
- Principal name được xác định nhất quán trên mọi node.
- Cấu hình maximum sessions và expired-session strategy giống nhau.
- Logout hoặc session expiration cập nhật registry/index.
- Kiểm thử hai lần đăng nhập đồng thời được xử lý theo đúng chính sách.

Không dùng một SessionRegistry chỉ lưu trong bộ nhớ cục bộ nếu mục tiêu là giới hạn số phiên trên toàn cụm. Mỗi instance có thể nhìn thấy một tập session khác nhau và vượt quá giới hạn toàn hệ thống.

## 12. Phân biệt Servlet SecurityContextRepository và WebFlux

Bài học này tập trung vào ứng dụng Servlet dùng HttpSession và Spring Session. WebFlux có mô hình khác:

| Servlet | WebFlux |
|---|---|
| HttpSession | WebSession |
| SecurityContextRepository trong Servlet security chain | ServerSecurityContextRepository |
| HttpSessionSecurityContextRepository | WebSessionServerSecurityContextRepository hoặc implementation phù hợp |
| SecurityContextHolder theo request/thread | Reactive SecurityContext qua Reactor Context |

Không dùng HttpSessionSecurityContextRepository cho WebFlux thuần. Trong reactive application, không dựa vào ThreadLocal SecurityContextHolder theo cách Servlet; security context được truyền qua Reactor Context và các API reactive security.

Nếu ứng dụng có cả Servlet và WebFlux stack, cần xác định rõ loại chain và repository được áp dụng cho từng request path. Không chia sẻ bean repository không tương thích chỉ vì cả hai cùng có tên SecurityContextRepository.

## 13. Kiểm thử khôi phục và lưu SecurityContext

Kiểm thử phải chứng minh request sau, kể cả khi đến node khác, nhận được Authentication đã lưu. Chỉ kiểm tra SecurityContextHolder trong cùng request không đủ.

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Form login | Đăng nhập qua filter chuẩn, giữ cookie | Response xác thực thành công và session được tạo khi cần |
| Request tiếp theo | Gửi cookie cũ tới endpoint bảo vệ | Authentication được khôi phục |
| Custom login | Gọi AuthenticationManager rồi saveContext | Request sau được xác thực |
| Chỉ set holder | Bỏ qua saveContext trong test migration | Request sau không được coi là đã đăng nhập trong chế độ explicit save |
| Chuyển instance | Login ở A, request tiếp theo ở B | B khôi phục cùng SecurityContext |
| Session fixation | Đăng nhập với session ID cũ | Client nhận ID mới và context vẫn được lưu |
| Logout | Gọi logout và gửi lại ID cũ | Phiên bị invalidate, request bị từ chối |
| Hết hạn | Chờ idle timeout | Context không còn được khôi phục |
| Deserialize cũ | Đọc fixture từ phiên bản trước | Dữ liệu được khôi phục hoặc lỗi được xử lý an toàn |
| Concurrent sessions | Đăng nhập từ nhiều client | Giới hạn phiên được áp dụng toàn cụm |

Ví dụ kiểm thử tích hợp với MockMvc:

~~~java
MvcResult login = mockMvc.perform(post("/login")
        .param("username", "alice")
        .param("password", "test-password"))
    .andExpect(status().is3xxRedirection())
    .andReturn();

MockHttpSession session =
    (MockHttpSession) login.getRequest().getSession(false);

mockMvc.perform(get("/profile").session(session))
    .andExpect(status().isOk());
~~~

Ví dụ chỉ minh họa flow; status và cách lấy session phụ thuộc cấu hình form login. Với Spring Session Redis/JDBC thực tế, nên dùng integration test chạy repository thật và kiểm tra request qua hai application instance hoặc hai application context.

### 13.1. Kiểm tra explicit save

Thêm một test cho endpoint xác thực tùy chỉnh:

1. Xác thực credentials qua AuthenticationManager.
2. Tạo SecurityContext và gọi saveContext.
3. Giữ cookie/ID từ response.
4. Gửi request mới đến endpoint cần authentication.
5. Xác nhận principal và authorities đúng.

Sau đó có thể tạo test âm bỏ thao tác saveContext để xác nhận hệ thống không dựa nhầm vào trạng thái ThreadLocal của request trước.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Đăng nhập thành công nhưng request sau anonymous | Context chỉ được đặt trong SecurityContextHolder, chưa được lưu | Gọi SecurityContextRepository.saveContext trong flow tùy chỉnh |
| Nâng Spring Security 6 thì session không giữ đăng nhập | Chuyển sang explicit save nhưng custom filter vẫn dựa auto-save cũ | Kiểm kê và cập nhật mọi điểm tạo Authentication |
| Context không xuất hiện trong Redis/JDBC | Session không được tạo, repository khác hoặc save chưa chạy | Kiểm tra session policy, repository và response lifecycle |
| Một node đọc được, node khác deserialize lỗi | Serializer/classpath khác nhau | Đồng bộ dependency và dữ liệu principal |
| Logout xong session cũ còn hiệu lực | Chỉ xóa cookie hoặc không invalidate repository | Dùng logout handler và xác minh delete/invalidate |
| Đăng nhập làm mất thuộc tính session | Session fixation strategy hoặc code tạo session mới không migrate attribute như mong đợi | Kiểm tra chiến lược fixation và test attribute migration |
| Concurrent session limit không đúng | SessionRegistry chỉ ở local memory hoặc principal index thiếu | Dùng SpringSessionBackedSessionRegistry và repository index phù hợp |
| SecurityContext bị lưu trong ứng dụng stateless | Session policy và repository cấu hình không nhất quán | Chọn rõ stateful hoặc stateless architecture |
| Lỗi chỉ xảy ra trong rolling deployment | Hai phiên bản không tương thích SecurityContext/principal serialization | Kiểm thử fixture cũ và chiến lược reader-first |

## 15. Nguyên tắc triển khai

- Dùng SecurityContextRepository để quản lý việc tải và lưu SecurityContext.
- Trong ứng dụng Servlet dùng Spring Session, HttpSessionSecurityContextRepository lưu context qua HttpSession; Spring Session đưa session vào Redis/JDBC.
- Phân biệt SecurityContextHolder trong request với repository lưu context giữa các request.
- Với Spring Security hiện đại, hiểu cơ chế explicit save; custom authentication flow phải gọi saveContext trước khi response commit.
- Dùng cùng SecurityContextRepository trong filter chain và code xác thực tùy chỉnh.
- Chọn SessionCreationPolicy phù hợp; không dùng STATELESS nếu cần session-backed authentication.
- Giữ session fixation protection, logout invalidation và cookie/header resolver nhất quán.
- Đảm bảo principal và Authentication object tương thích với serializer của repository.
- Khi nâng phiên bản, kiểm thử dữ liệu SecurityContext cũ và ma trận đọc/ghi giữa các node.
- Dùng registry chia sẻ khi cần giới hạn concurrent sessions trên nhiều instance.
- Với WebFlux, dùng reactive security context repository và WebSession, không áp dụng cấu hình Servlet.

Spring Session cung cấp nơi lưu HttpSession dùng chung, còn Spring Security quản lý việc khôi phục và lưu SecurityContext. Khi hai lớp được cấu hình nhất quán, request có thể chuyển qua nhiều instance mà vẫn giữ đúng danh tính và quyền của người dùng. Khi nâng cấp Spring Security, đặc biệt từ cơ chế tự lưu cũ sang explicit save, cần rà soát từng luồng xác thực tùy chỉnh để bảo đảm context được ghi vào repository trước khi request kết thúc.

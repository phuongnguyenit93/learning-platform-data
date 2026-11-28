# Phiên lưu trạng thái và cơ chế xác thực có những trách nhiệm riêng

Trong ứng dụng Spring Servlet, HTTP session và xác thực là hai cơ chế phối hợp với nhau nhưng giải quyết hai vấn đề khác nhau. Session giữ trạng thái tương tác giữa nhiều request; xác thực xác định principal nào đang thực hiện request và những thông tin quyền hạn nào đã được xác minh. Spring Session thay đổi nơi lưu HttpSession, còn Spring Security quản lý quá trình xác thực, lưu SecurityContext và kiểm tra quyền truy cập.

Phân biệt hai trách nhiệm này giúp tránh những lỗi như coi mọi session đều đã đăng nhập, lưu toàn bộ trạng thái nghiệp vụ vào SecurityContext, hoặc nghĩ rằng chuyển session sang Redis tự động làm cho việc xác thực trở nên an toàn hơn. Spring Session có thể giúp nhiều instance cùng khôi phục session; Spring Security vẫn phải xác minh Authentication và authorization theo từng request.

Bài học tập trung vào ứng dụng Servlet dùng Spring Session với Redis hoặc JDBC và tích hợp Spring Security theo mô hình stateful. WebFlux dùng WebSession và các API reactive riêng, không dùng trực tiếp các cấu hình HttpSession trong bài này.

## 1. Hai câu hỏi khác nhau: trạng thái phiên và danh tính đã xác thực

Một ứng dụng web có thể cần nhớ nhiều loại thông tin giữa các request:

- Giỏ hàng tạm thời của khách truy cập.
- Ngôn ngữ hoặc tùy chọn giao diện.
- Tiến độ của một quy trình nhiều bước.
- Thông tin đăng nhập đã được xác minh.
- Trạng thái CSRF hoặc các dữ liệu hỗ trợ bảo mật khác.

Những dữ liệu đó không cùng một loại. Session là vùng lưu trạng thái gắn với một phiên HTTP. Authentication là đối tượng mô tả danh tính đã được xác thực và các quyền được cấp. SecurityContext là nơi Spring Security giữ Authentication hiện tại cho quá trình xử lý request.

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| HttpSession | Ứng dụng cần nhớ trạng thái nào giữa các request của client này? | Giỏ hàng, locale, trạng thái wizard |
| Authentication | Request hiện tại đại diện cho ai và có authorities nào? | Principal alice với ROLE_USER |
| SecurityContext | Spring Security đặt Authentication hiện tại ở đâu trong quá trình xử lý? | SecurityContext chứa Authentication |
| SecurityContextRepository | Làm thế nào để khôi phục/lưu SecurityContext giữa các request? | HttpSessionSecurityContextRepository |
| SessionRepository của Spring Session | Lưu và tải dữ liệu HttpSession từ kho nào? | Redis hoặc JDBC |

Một session có thể tồn tại mà không có Authentication đã xác thực. Ví dụ, người dùng chưa đăng nhập thêm hàng vào giỏ hàng; ứng dụng tạo session để lưu giỏ hàng. Ngược lại, một ứng dụng có thể xác thực từng request bằng bearer token và không dùng HttpSession để lưu trạng thái đăng nhập.

Vì vậy, không được suy ra rằng có session ID là người dùng đã đăng nhập, hoặc rằng không có session thì request chắc chắn chưa được xác thực. Phải kiểm tra Authentication theo cơ chế Spring Security đang cấu hình.

## 2. Vai trò của Spring Session

Spring Session quản lý vòng đời và dữ liệu HttpSession. Trong Servlet integration, SessionRepositoryFilter bọc request và response để lời gọi Servlet API như request.getSession() làm việc với session do Spring Session quản lý.

Với Redis hoặc JDBC, repository lưu dữ liệu phiên ở kho dùng chung. Khi request tiếp theo mang session ID hợp lệ, repository tải lại dữ liệu để instance hiện tại tiếp tục xử lý.

Spring Session chịu trách nhiệm cho các vấn đề như:

- Tạo, tìm, cập nhật và xóa phiên.
- Lưu các thuộc tính HttpSession trong Redis hoặc JDBC.
- Quản lý thời hạn không hoạt động theo cấu hình repository.
- Trao đổi session ID qua cookie hoặc resolver được cấu hình.
- Hỗ trợ chia sẻ session giữa nhiều instance.
- Phát các sự kiện vòng đời theo khả năng của repository.

Spring Session không tự xác minh mật khẩu, không quyết định người dùng có vai trò quản trị hay không và không thay thế AuthenticationManager hoặc authorization rules của Spring Security.

## 3. Vai trò của Spring Security

Spring Security xử lý xác thực và phân quyền. Khi người dùng gửi thông tin xác thực, một authentication mechanism chuyển thông tin đó tới AuthenticationManager hoặc thành phần xác thực tương ứng. Nếu thành công, ứng dụng nhận được Authentication có principal và authorities.

Các thành phần chính:

| Thành phần | Trách nhiệm |
|---|---|
| AuthenticationManager | Điều phối quá trình xác thực |
| AuthenticationProvider | Kiểm tra thông tin xác thực theo cơ chế cụ thể |
| Authentication | Đại diện danh tính đã xác thực hoặc yêu cầu xác thực |
| SecurityContext | Chứa Authentication hiện tại |
| SecurityContextHolder | Cung cấp SecurityContext cho code xử lý request |
| SecurityContextRepository | Khôi phục và lưu SecurityContext giữa các request |
| AuthorizationFilter / authorization manager | Kiểm tra quyền truy cập tài nguyên |

Spring Security đặt SecurityContext vào SecurityContextHolder trong phạm vi request. Với cấu hình stateful, SecurityContextRepository có thể lưu context vào HttpSession để request sau khôi phục Authentication.

Spring Security còn đảm nhiệm các chính sách liên quan như bảo vệ session fixation, quản lý logout, CSRF, kiểm soát số phiên đồng thời và authorization. Các chức năng này hoạt động trên session khi được cấu hình phù hợp, nhưng không phải do Spring Session tự cung cấp.

## 4. SecurityContext được lưu trong HttpSession như thế nào?

Trong cấu hình Servlet stateful thông thường, Spring Security sử dụng HttpSessionSecurityContextRepository như một phần của SecurityContextRepository. Ở các cấu hình hiện đại, repository mặc định có thể là DelegatingSecurityContextRepository kết hợp RequestAttributeSecurityContextRepository và HttpSessionSecurityContextRepository.

Luồng tổng quát:

    Request có session ID
             |
             v
    SessionRepositoryFilter
             |
             | Khôi phục HttpSession từ Redis/JDBC
             v
    Spring Security filter chain
             |
             | SecurityContextRepository đọc context
             v
    SecurityContextHolder
             |
             | Authentication được khôi phục
             v
    Authorization kiểm tra quyền
             |
             v
    Controller / Service xử lý nghiệp vụ

Khi xác thực thành công, authentication mechanism tạo hoặc cập nhật SecurityContext. Context được lưu thông qua SecurityContextRepository theo chính sách save của cấu hình Spring Security. Với mô hình dùng HttpSession, HttpSessionSecurityContextRepository đặt SecurityContext vào session.

Ví dụ cấu hình khái niệm:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Khi cấu hình stateful mặc định phù hợp, Spring Security có thể lưu SecurityContext vào HttpSession. Spring Session thay cơ chế lưu HttpSession phía container bằng repository của nó. Controller không cần tự serialize Authentication vào Redis hoặc JDBC.

Không nên tự viết code lưu mật khẩu, token gốc hoặc Authentication tùy ý vào session. Hãy để authentication mechanism và SecurityContextRepository quản lý context theo cấu hình Spring Security.

## 5. Phân biệt SecurityContextHolder với nơi lưu lâu dài

SecurityContextHolder là nơi truy cập context trong quá trình xử lý request. Nó không phải kho dữ liệu lâu dài. Trong mô hình Servlet truyền thống, context thường được gắn với thread đang xử lý request và được dọn khi request kết thúc.

SecurityContextRepository mới là thành phần quyết định context được khôi phục hoặc lưu ở đâu. Ví dụ:

- HttpSessionSecurityContextRepository lưu SecurityContext vào HttpSession.
- RequestAttributeSecurityContextRepository giữ context trong phạm vi request và có thể chia sẻ giữa các dispatch.
- NullSecurityContextRepository không lưu context vào session.
- DelegatingSecurityContextRepository kết hợp nhiều repository theo cấu hình.

Trong Spring Security hiện đại, cơ chế lưu SecurityContext có thể yêu cầu save tường minh. Điều này giúp ứng dụng kiểm soát rõ khi nào context được lưu. Các authentication mechanism tích hợp sẵn thường thực hiện việc lưu phù hợp; nếu tự viết filter xác thực, cần kiểm tra cấu hình requireExplicitSave và gọi SecurityContextRepository.saveContext(...) khi cần.

Ví dụ minh họa việc lưu context tường minh:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);

SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

Đây là ví dụ cho custom authentication flow. Không cần thêm thao tác save này vào mọi controller; hãy dùng cơ chế xác thực chuẩn của Spring Security nếu có thể. Sau khi request kết thúc, SecurityContextHolder được dọn theo filter lifecycle; dữ liệu muốn tồn tại ở request tiếp theo phải được lưu qua repository phù hợp.

## 6. Cấu hình Spring Session và Spring Security cùng hoạt động

Với Spring Boot Servlet application dùng Redis, dependency thường gồm starter web, Spring Security, Spring Session Redis và starter Redis. Với JDBC, dùng module Spring Session JDBC cùng starter JDBC và driver database.

Ví dụ cấu hình Redis:

~~~yaml
spring:
  session:
    store-type: redis
    timeout: 30m
    redis:
      namespace: shop:session
  data:
    redis:
      host: localhost
      port: 6379
~~~

Ví dụ cấu hình JDBC:

~~~yaml
spring:
  session:
    store-type: jdbc
    timeout: 30m
  datasource:
    url: jdbc:postgresql://localhost:5432/app
    username: session_app
    password: ${SESSION_DB_PASSWORD}
~~~

Tên property kết nối Redis có thể khác giữa các dòng Spring Boot. Cần dùng metadata cấu hình của phiên bản dự án. Với JDBC, schema Spring Session phải được tạo và migration trước khi ứng dụng ghi phiên.

Trong cả hai trường hợp, Spring Security vẫn làm việc với HttpSession và SecurityContextRepository. Spring Session đảm nhiệm phần lưu trữ HttpSession ở Redis/JDBC. Không cần viết một AuthenticationProvider riêng chỉ vì đổi session store.

## 7. Thứ tự filter: điều kiện để Security dùng đúng session

SessionRepositoryFilter phải chạy trước những filter cần truy cập HttpSession, bao gồm Spring Security filter chain. Nhờ đó, khi Spring Security đọc hoặc tạo HttpSession, nó làm việc với wrapper của Spring Session.

Nếu một filter chạy trước SessionRepositoryFilter tạo session qua container gốc, ứng dụng có thể vô tình tạo hai ngữ cảnh session: một session cục bộ của container và một session được Spring Session quản lý. Hậu quả có thể là SecurityContext được lưu ở nơi không chia sẻ, hoặc request chuyển sang instance khác không khôi phục được trạng thái xác thực.

Khi dùng Spring Boot auto-configuration, thứ tự filter thường được cấu hình phù hợp. Nếu tự đăng ký filter hoặc thay đổi FilterRegistrationBean, cần xác minh thứ tự cuối cùng:

1. SessionRepositoryFilter áp dụng trước.
2. Spring Security FilterChainProxy xử lý sau.
3. Các filter tùy chỉnh đọc HttpSession/SecurityContext nằm ở vị trí phù hợp.
4. Không đăng ký SessionRepositoryFilter hai lần.
5. Không tạo HttpSession trong filter chạy trước Spring Session.

Kiểm thử qua nhiều instance là cách tốt để phát hiện filter order sai: đăng nhập ở instance A rồi gửi request đã xác thực đến instance B.

## 8. SessionCreationPolicy quyết định Spring Security có dùng session không

Spring Security cung cấp SessionCreationPolicy để điều khiển việc tạo và sử dụng HttpSession trong quá trình bảo mật.

| Chính sách | Hành vi |
|---|---|
| ALWAYS | Luôn tạo HttpSession nếu cần cho security |
| IF_REQUIRED | Chỉ tạo HttpSession khi cần |
| NEVER | Không chủ động tạo HttpSession, nhưng có thể sử dụng session đã tồn tại |
| STATELESS | Không tạo và không dùng HttpSession để lấy SecurityContext |

Ví dụ cấu hình stateful:

~~~java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
);
~~~

IF_REQUIRED thường phù hợp với form login hoặc ứng dụng web cần duy trì đăng nhập qua session. Khi xác thực thành công, SecurityContext có thể được lưu trong session.

Ví dụ cấu hình stateless:

~~~java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
~~~

STATELESS phù hợp với API xác thực từng request bằng bearer token hoặc cơ chế không dựa vào HttpSession. Trong chính sách này, Spring Security không dùng HttpSession để khôi phục SecurityContext. Spring Session vẫn có thể được dùng cho một nhu cầu trạng thái khác của ứng dụng, nhưng session đó không tự trở thành nơi lưu Authentication của SecurityFilterChain stateless.

Cần phân biệt chính sách session của Spring Security với việc Spring Session có được bật hay không. Hai cấu hình điều khiển hai tầng khác nhau.

## 9. Có session không có nghĩa là đã xác thực

Ứng dụng có thể tạo session cho người dùng chưa đăng nhập. Ví dụ:

~~~java
@GetMapping("/cart")
public CartView cart(HttpServletRequest request) {
    HttpSession session = request.getSession();

    Cart cart = (Cart) session.getAttribute("cart");
    return cart == null ? CartView.empty() : CartView.from(cart);
}
~~~

Endpoint này có thể tạo session để lưu giỏ hàng ẩn danh. Session tồn tại không có nghĩa Authentication đã được xác thực.

Khi bảo vệ endpoint, dùng authorization rules hoặc kiểm tra Authentication theo cách Spring Security cung cấp. Không viết logic kiểu "nếu cookie SESSION tồn tại thì cho truy cập".

Ví dụ bảo vệ endpoint:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/cart/**", "/public/**").permitAll()
    .requestMatchers("/account/**").authenticated()
    .requestMatchers("/admin/**").hasRole("ADMIN")
);
~~~

Spring Security khôi phục Authentication từ SecurityContextRepository nếu có context hợp lệ. Sau đó authorization kiểm tra yêu cầu của endpoint. Session chỉ cung cấp ngữ cảnh lưu trữ; quyền truy cập vẫn được quyết định bởi security configuration.

## 10. Có Authentication không nhất thiết phải dùng HttpSession

Một ứng dụng REST có thể dùng bearer token ở mỗi request. Spring Security xác minh token, tạo Authentication cho request hiện tại rồi xử lý authorization. Nếu cấu hình STATELESS, SecurityContext không được lưu trong HttpSession.

Điều này thường phù hợp khi:

- API client gửi bearer token trong Authorization header.
- Mỗi request tự mang credential và được xác minh độc lập.
- Backend không cần giữ trạng thái đăng nhập trong HttpSession.
- Các instance không cần chia sẻ SecurityContext qua session store.

Ngược lại, form login truyền thống thường dùng session để duy trì trạng thái đăng nhập giữa các request. Không nên bật STATELESS cho luồng form login mà vẫn mong SecurityContext được khôi phục từ HttpSession.

Cũng không nên nhầm session ID với access token. Session ID là khóa tra cứu dữ liệu trạng thái ở server. JWT hoặc access token có định dạng, chữ ký, claims và quy trình xác minh riêng.

## 11. Session fixation và thay đổi session ID sau đăng nhập

Nếu kẻ tấn công biết trước session ID của nạn nhân và nạn nhân đăng nhập bằng ID đó, kẻ tấn công có thể tìm cách tiếp tục sử dụng phiên. Đây là rủi ro session fixation.

Spring Security cung cấp session fixation protection. Tùy Servlet container và cấu hình, chiến lược có thể thay đổi session ID hiện tại hoặc tạo session mới và chuyển các thuộc tính hợp lệ.

Với Spring Session, thao tác đổi ID được phản ánh trong repository và resolver gửi ID mới về client. Nếu dùng cookie, response cập nhật cookie; nếu dùng header resolver, response header chứa ID mới theo cơ chế resolver.

Một số điểm cần xác minh:

- Chiến lược session fixation đang dùng.
- ID có được đổi sau khi xác thực thành công không.
- Client có nhận và gửi lại ID mới không.
- Thuộc tính phiên cần giữ có được migrate đúng không.
- ID cũ không còn được dùng để khôi phục phiên.
- Hành vi có giống nhau khi request được xử lý ở instance khác không.

Không tự tạo session ID trong controller hoặc JavaScript. Việc xoay vòng phải do Spring Security/Spring Session thực hiện qua API hỗ trợ.

## 12. Logout phải xử lý cả Authentication và session

Đăng xuất là quá trình thu hồi trạng thái xác thực và phiên theo chính sách ứng dụng. Spring Security logout flow có thể:

- Xóa Authentication khỏi SecurityContext.
- Xóa SecurityContext khỏi repository.
- Invalidate HttpSession.
- Xóa cookie hoặc thông báo resolver loại bỏ session ID.
- Gọi logout handlers để thực hiện nghiệp vụ bổ sung.

Ví dụ cấu hình logout:

~~~java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("SESSION")
);
~~~

Tên cookie cần khớp với resolver thực tế. Với cấu hình mặc định Spring Session, cookie thường là SESSION; nếu đã đổi tên, cần cập nhật cấu hình tương ứng. Nếu dùng header resolver, việc xóa cookie không áp dụng; client cần xử lý header hết hạn.

Không chỉ xóa cookie ở trình duyệt mà bỏ phiên ở repository. Nếu session ID bị lộ, bản ghi phía server vẫn có thể bị sử dụng cho đến khi hết hạn hoặc bị thu hồi. Ngược lại, nếu chỉ invalidate server mà client không nhận response, client có thể tiếp tục gửi ID cũ nhưng server phải từ chối phiên đã xóa.

Nếu ứng dụng cần đăng xuất mọi thiết bị, logout phiên hiện tại là chưa đủ. Cần tìm và thu hồi các session khác thuộc principal theo repository/index hỗ trợ, đồng thời xử lý trường hợp phiên mới được tạo trong lúc thu hồi đang chạy.

## 13. CSRF trong ứng dụng xác thực bằng session

Khi trình duyệt tự động gửi cookie session, request có thể mang credential mà người dùng không chủ động gắn vào từng thao tác. Một trang độc hại có thể tìm cách khiến trình duyệt gửi request thay mặt người dùng. Đây là cơ sở của Cross-Site Request Forgery (CSRF).

Spring Security bật bảo vệ CSRF cho các cấu hình phù hợp và có thể lưu CSRF token trong HttpSession. Spring Session lưu session đó ở Redis/JDBC, nhưng không thay thế cơ chế tạo, xác minh hoặc phân phối CSRF token.

Các nguyên tắc:

- Không tắt CSRF chỉ vì session được lưu trong Redis hoặc JDBC.
- Với form, đưa CSRF token vào request theo cơ chế Spring Security.
- Với SPA, cấu hình cách lấy và gửi token phù hợp.
- SameSite cookie là lớp phòng vệ bổ sung, không phải thay thế toàn bộ CSRF protection.
- Xác định rõ endpoint nào dùng cookie/session và endpoint nào dùng bearer token stateless.

Nếu ứng dụng dùng header resolver, custom header có thể thay đổi khả năng gửi credential từ cross-site form, nhưng không tự động loại bỏ CSRF. XSS và cấu hình CORS quá rộng vẫn có thể khiến credential bị lạm dụng.

## 14. Quản lý nhiều phiên và trạng thái tài khoản

Một principal có thể đăng nhập trên nhiều thiết bị. Mỗi thiết bị thường có session ID riêng, dù Authentication bên trong các session đại diện cùng một principal.

Spring Security có thể cấu hình giới hạn số phiên đồng thời. Spring Session cung cấp tích hợp session registry cho một số repository và use case; ví dụ SpringSessionBackedSessionRegistry dùng khả năng tìm phiên của repository. Khả năng và cấu hình cụ thể phụ thuộc repository, index support và phiên bản.

Ví dụ cấu hình giới hạn phiên ở mức khái niệm:

~~~java
http.sessionManagement(session -> session
    .maximumSessions(2)
);
~~~

Để cấu hình hoạt động đúng, cần đăng ký SessionRegistry phù hợp và xác minh repository có hỗ trợ truy vấn phiên theo principal. Không giả định mọi SessionRepository đều hỗ trợ các thao tác quản lý phiên đồng thời như nhau.

Cũng cần có chính sách khi tài khoản bị khóa, mật khẩu bị đổi hoặc quyền bị thu hồi. Authentication được lưu trong session là một snapshot tại thời điểm xác thực; nếu quyền hoặc trạng thái tài khoản thay đổi, ứng dụng cần cơ chế làm mới hoặc thu hồi session để tránh tiếp tục dùng thông tin cũ quá lâu.

## 15. Dữ liệu nào nên lưu trong session?

Session là vùng trạng thái ngắn hạn. Chỉ lưu dữ liệu cần thiết để tiếp tục tương tác giữa các request.

| Dữ liệu | Nơi lưu thường phù hợp |
|---|---|
| SecurityContext trong stateful authentication | Spring Security SecurityContextRepository, thường dùng HttpSession |
| Giỏ hàng tạm thời của khách vãng lai | HttpSession hoặc cart service tùy yêu cầu |
| Locale, theme, trạng thái wizard | Session nếu dữ liệu nhỏ và ngắn hạn |
| Hồ sơ người dùng, vai trò gốc, trạng thái tài khoản | Database/domain service; không coi session là nguồn chuẩn |
| Đơn hàng, thanh toán, tồn kho | Database nghiệp vụ với transaction phù hợp |
| Password, private key, refresh token dài hạn | Không lưu tùy tiện trong session; dùng cơ chế bảo mật chuyên biệt |

Không lưu entity lớn, connection, servlet request/response, service bean hoặc object graph phụ thuộc framework vào session. Dữ liệu session cần serialize được nếu repository lưu ngoài JVM; với nhiều instance, các phiên bản ứng dụng cũng cần hiểu cùng format.

Đặc biệt, không dùng thuộc tính session như nguồn chuẩn duy nhất cho quyền nghiệp vụ lâu dài. Authorization cần dựa trên chính sách và dữ liệu có thẩm quyền, hoặc có cơ chế refresh/revocation phù hợp.

## 16. Vận hành nhiều instance: Spring Session chia sẻ state, Spring Security áp dụng policy

Trong hệ thống nhiều instance, load balancer có thể gửi request đầu tiên đến instance A và request tiếp theo đến instance B. Spring Session cho phép B khôi phục HttpSession từ Redis/JDBC. Spring Security sau đó đọc SecurityContext từ session và áp dụng authorization rules.

Luồng:

    Client
      |
      | SESSION cookie
      v
    Load balancer
      |
      +------> Instance A
      |           |
      |           | Spring Session filter
      |           v
      |        Redis/JDBC
      |           |
      |           v
      |        HttpSession + SecurityContext
      |
      +------> Instance B
                  |
                  | Spring Session filter
                  v
               Redis/JDBC
                  |
                  v
           Khôi phục cùng session
                  |
                  v
           Spring Security authorization

Để vận hành ổn định:

- Tất cả instance dùng chung session repository và namespace.
- Cùng cấu hình cookie/resolver, timeout và serializer tương thích.
- Spring Session filter chạy trước Spring Security filter chain.
- Các instance dùng cấu hình SecurityContextRepository nhất quán.
- Các class được serialize trong session tương thích giữa các phiên bản.
- Logout và ID rotation được kiểm thử qua nhiều instance.
- Không dựa vào sticky session để thay thế kho session dùng chung.

Spring Session giúp chia sẻ trạng thái phiên, nhưng không đồng bộ tự động mọi dữ liệu bảo mật bên ngoài session. Ví dụ, thay đổi quyền trong database hoặc thu hồi token ở dịch vụ khác cần cơ chế riêng.

## 17. Chẩn đoán các lỗi tích hợp thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Session tồn tại nhưng endpoint vẫn trả 401 | Không có SecurityContext hợp lệ hoặc context không được lưu | Kiểm tra Authentication flow và SecurityContextRepository |
| Cookie có nhưng người dùng bị xem là anonymous | Session chưa đăng nhập, ID hết hạn hoặc context không khôi phục | Kiểm tra repository, cookie và SecurityContext |
| Đăng nhập thành công nhưng request sau mất xác thực | Context không được save, session ID không được gửi lại hoặc filter order sai | Kiểm tra explicit save, response cookie và thứ tự filter |
| Request qua instance B mất đăng nhập | Instance không dùng cùng repository/namespace hoặc serializer không tương thích | Kiểm tra cấu hình node và session store |
| Logout xong ID cũ vẫn dùng được | Chỉ xóa cookie, chưa invalidate session phía server | Kiểm tra logout handlers và repository |
| Đổi mật khẩu nhưng phiên cũ còn quyền | Authentication snapshot vẫn tồn tại trong session | Thu hồi phiên hoặc làm mới xác thực theo chính sách |
| Session được tạo cho endpoint công khai | Endpoint gọi getSession() hoặc cấu hình security tạo session | Kiểm tra SessionCreationPolicy và code truy cập session |
| API bearer token vô tình tạo HttpSession | Cấu hình stateful hoặc code nghiệp vụ tạo session | Kiểm tra STATELESS và các filter/controller |
| CSRF lỗi sau khi chuyển Redis | Token repository hoặc frontend flow chưa được cấu hình phù hợp | Kiểm tra CSRF token lifecycle, cookie và request header |

Khi điều tra, phân chia vấn đề thành bốn lớp: client có gửi session ID không; Spring Session có khôi phục HttpSession không; Spring Security có khôi phục Authentication không; authorization có cho phép endpoint không. Không kết luận Redis/JDBC lỗi chỉ vì request nhận 401.

## 18. Kiểm thử tích hợp theo vòng đời xác thực

Một bài kiểm thử chỉ kiểm tra endpoint login trả 200 chưa đủ. Cần xác minh session và Authentication được duy trì đúng giữa các request.

Các trường hợp nên kiểm thử:

1. Request chưa đăng nhập truy cập endpoint công khai thành công.
2. Request chưa đăng nhập truy cập endpoint yêu cầu xác thực bị từ chối hoặc redirect theo cấu hình.
3. Endpoint công khai tạo session ẩn danh; xác nhận session đó không được xem là đã xác thực.
4. Đăng nhập thành công; xác nhận response gửi session ID.
5. Gửi request tiếp theo bằng cookie/header và xác nhận principal được khôi phục.
6. Xác nhận endpoint có role yêu cầu chỉ được truy cập khi authorities phù hợp.
7. Kiểm tra session ID thay đổi sau xác thực theo chiến lược session fixation.
8. Logout; xác nhận session bị invalidate và ID cũ không khôi phục được Authentication.
9. Đổi mật khẩu/khóa tài khoản; xác nhận chính sách thu hồi session hoạt động.
10. Gửi request đến instance khác và xác nhận SecurityContext được khôi phục.
11. Chạy hai request đồng thời cùng session và kiểm tra cập nhật SecurityContext/session không bị ghi đè ngoài dự kiến.
12. Với STATELESS, xác nhận SecurityContext không được lưu/đọc từ HttpSession.
13. Kiểm tra CSRF token với các request thay đổi trạng thái.
14. Kiểm tra log không chứa session ID, cookie hoặc thông tin xác thực nhạy cảm.

Dùng MockMvc cho kiểm thử Servlet security chain; với Redis/JDBC, nên có integration test sử dụng repository thực hoặc môi trường kiểm thử tương thích. Để xác nhận nhiều instance, chạy hai instance hoặc test environment có thể định tuyến request qua cả hai node.

## 19. Quy trình thiết kế và cấu hình

Khi tích hợp Spring Session với Spring Security, thực hiện theo thứ tự:

1. Xác định ứng dụng là Servlet hay WebFlux.
2. Chọn repository Spring Session phù hợp, ví dụ Redis hoặc JDBC.
3. Xác định ứng dụng cần stateful session authentication hay stateless bearer authentication.
4. Với stateful, cấu hình SecurityContextRepository sử dụng HttpSession theo chính sách mong muốn.
5. Chọn SessionCreationPolicy phù hợp; không dùng STATELESS nếu muốn khôi phục Authentication từ HttpSession.
6. Xác nhận SessionRepositoryFilter chạy trước Spring Security.
7. Cấu hình cookie, timeout, CSRF và session fixation protection.
8. Xác định logout chỉ cho phiên hiện tại hay mọi phiên của tài khoản.
9. Kiểm thử login, request xác thực, role, logout, hết hạn và nhiều instance.
10. Theo dõi số session, lỗi khôi phục SecurityContext, lỗi repository và hoạt động thu hồi.

Nếu ứng dụng có nhiều loại client, có thể tách security filter chain theo endpoint hoặc loại xác thực. Ví dụ, trang web dùng session/cookie trong khi API machine-to-machine dùng bearer token stateless. Hãy làm rõ đường đi của mỗi request để không vô tình dùng session policy sai.

## Kết luận

Spring Session và Spring Security có hai trách nhiệm riêng nhưng phối hợp trong mô hình xác thực stateful. Spring Session quản lý HttpSession và lưu trạng thái vào Redis/JDBC; Spring Security xác thực principal, lưu/khôi phục Authentication qua SecurityContextRepository và kiểm tra quyền truy cập. Session có thể tồn tại khi chưa đăng nhập, còn xác thực stateless có thể hoạt động mà không cần HttpSession. Khi triển khai, hãy chọn SessionCreationPolicy rõ ràng, bảo đảm filter order, dùng SecurityContextRepository phù hợp, bảo vệ session fixation/CSRF, invalidate phiên khi logout và kiểm thử luồng qua nhiều instance.

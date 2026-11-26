Bạn giải thích Spring Security bảo vệ một ứng dụng Servlet/Spring MVC ở những lớp xử lý HTTP nào?
Bạn phân biệt bảo mật dựa trên Servlet Filter với bảo mật được thực thi trong Spring MVC HandlerInterceptor ra sao?
Bạn mô tả một request đi từ Servlet container qua Spring Security rồi tới DispatcherServlet như thế nào?
Bạn giải thích DelegatingFilterProxy nối Servlet filter registration với bean security do ApplicationContext quản lý ra sao?
Bạn phân biệt FilterChainProxy với SecurityFilterChain trong việc điều phối các security filters như thế nào?
Bạn sẽ xác định cách FilterChainProxy lựa chọn SecurityFilterChain đầu tiên khớp request như thế nào?
Bạn mô tả vai trò của HttpSecurity khi tạo một SecurityFilterChain bean cho Servlet application ra sao?
Bạn phân biệt HttpSecurity configuration DSL với những filters thực thi tại runtime theo vòng đời nào?
Bạn sẽ tổ chức cấu hình bảo mật Spring MVC bằng @Bean SecurityFilterChain trong một ứng dụng Spring Boot ra sao?
Bạn phân tích vì sao một ứng dụng có thể compile và chạy nhưng route vẫn không được bảo vệ vì không khớp bất kỳ SecurityFilterChain nào như thế nào?
Bạn sẽ đặt một fallback filter chain để bảo vệ routes chưa khai báo mà không vô tình bỏ qua endpoints công khai như thế nào?
Bạn phân biệt @Order của nhiều SecurityFilterChain beans với thứ tự requestMatchers trong từng chain như thế nào?
Bạn sẽ xác định những matcher nào được áp dụng khi hai SecurityFilterChain cùng có thể khớp một URL ra sao?
Bạn giải thích securityMatcher giới hạn phạm vi của chain khác gì requestMatchers trong authorizeHttpRequests như thế nào?
Bạn sẽ thiết kế chain cho /api/** dùng bearer token và chain cho /web/** dùng form login theo cách nào?
Bạn phân tích rủi ro dùng matcher quá rộng ở chain ưu tiên cao khiến chain hẹp không bao giờ được chọn như thế nào?
Bạn sẽ kiểm tra filter chain được chọn cho request có đường dẫn được reverse proxy viết lại như thế nào?
Bạn phân biệt Servlet contextPath, servletPath và pathInfo trong việc định vị request để so khớp bảo mật ra sao?
Bạn sẽ đánh giá ảnh hưởng của trailing slash, encoded path và path parameters tới các matcher của Spring Security như thế nào?
Bạn giải thích StrictHttpFirewall hỗ trợ ngăn một số URL bất thường hoặc mơ hồ trước khi khớp security rules ra sao?
Bạn sẽ cấu hình RequestMatcher phù hợp với cách Spring MVC ánh xạ controller paths trong phiên bản đang dùng như thế nào?
Bạn phân tích lý do requestMatchers áp dụng cùng pattern nhưng khác HTTP method có thể cho phép quyền khác nhau ra sao?
Bạn sẽ thiết kế quy tắc mặc định denyAll cho những đường dẫn không được xác định là public hoặc authenticated như thế nào?
Bạn phân biệt permitAll với WebSecurityCustomizer.ignoring khi cần cho phép truy cập static resources ra sao?
Bạn phân tích vì sao loại một route ra khỏi SecurityFilterChain có thể làm mất các HTTP security headers hoặc protection khác như thế nào?
Bạn sẽ quyết định khi nào cấu hình public endpoint bằng permitAll thay vì bỏ qua filter chain ra sao?
Bạn mô tả cách FilterChainProxy cuối cùng bàn giao request về Servlet FilterChain khi security checks hoàn tất ra sao?
Bạn phân biệt một Spring Security filter với một Servlet Filter do ứng dụng tự đăng ký qua FilterRegistrationBean như thế nào?
Bạn sẽ tránh custom filter chạy hai lần nếu nó vừa là Spring bean vừa được thêm vào HttpSecurity ra sao?
Bạn giải thích addFilterBefore, addFilterAfter và addFilterAt ảnh hưởng thứ tự custom authentication filter như thế nào?
Bạn sẽ sử dụng OncePerRequestFilter khi cần kiểm tra metadata chung trên mỗi request theo điều kiện nào?
Bạn phân tích vì sao OncePerRequestFilter không tự có nghĩa filter sẽ chạy đúng một lần trong mọi dạng Servlet dispatch bất đồng bộ như thế nào?
Bạn sẽ kiểm tra ảnh hưởng của DispatcherType.REQUEST, ASYNC và ERROR tới security filter invocation như thế nào?
Bạn sẽ dùng debug logging để truy ngược chain và filters thực sự chạy mà không ghi thông tin nhạy cảm ra sao?
Bạn mô tả vì sao Spring Security Servlet filter layer và các annotation trên MVC controller là hai tầng bảo vệ bổ sung như thế nào?
Bạn giải thích SecurityContextHolder quản lý SecurityContext cho xử lý Servlet request thông thường ra sao?
Bạn phân biệt SecurityContext với Authentication trong một request đã xác thực thành công như thế nào?
Bạn mô tả SecurityContextHolderStrategy mặc định dựa vào ThreadLocal và ảnh hưởng của thread reuse ra sao?
Bạn sẽ lấy Authentication từ SecurityContextHolder mà không đưa SecurityContext vào tất cả domain services như thế nào?
Bạn phân biệt Principal do HttpServletRequest.getUserPrincipal trả về với Authentication trong Spring Security ra sao?
Bạn sẽ sử dụng @AuthenticationPrincipal ở Spring MVC controller để đọc principal theo kiểu phù hợp như thế nào?
Bạn phân tích nguy cơ tin userId trong query parameter thay vì authenticated principal khi truy cập tài nguyên riêng ra sao?
Bạn mô tả SecurityContextHolderFilter phối hợp với SecurityContextRepository để nạp context cho request như thế nào?
Bạn phân biệt SecurityContextHolderFilter với SecurityContextPersistenceFilter trong các cấu hình Servlet security khác nhau ra sao?
Bạn sẽ xác định vì sao Authentication được set vào SecurityContextHolder nhưng request tiếp theo không còn đăng nhập ra sao?
Bạn giải thích SecurityContextRepository.saveContext được dùng khi cần lưu context cho các request tiếp theo như thế nào?
Bạn phân biệt HttpSessionSecurityContextRepository với RequestAttributeSecurityContextRepository về vòng đời lưu context ra sao?
Bạn sẽ chọn NullSecurityContextRepository cho một bearer-only API theo điều kiện nào?
Bạn phân tích tác động của DelegatingSecurityContextRepository khi security context được nạp hoặc lưu qua nhiều repository ra sao?
Bạn sẽ xác định khi nào Authentication trong SecurityContext là AnonymousAuthenticationToken và không phải user đã đăng nhập ra sao?
Bạn mô tả AnonymousAuthenticationFilter tạo context cho một request không có authentication thực sự như thế nào?
Bạn phân biệt security context của remember-me user với fully authenticated browser user khi kiểm tra thao tác rủi ro cao như thế nào?
Bạn sẽ thiết kế cơ chế cleanup SecurityContext khi exception xuất hiện giữa filter chain để tránh rò danh tính sang request sau ra sao?
Bạn phân tích rủi ro dùng MODE_INHERITABLETHREADLOCAL với thread pool được tái sử dụng giữa nhiều requests như thế nào?
Bạn sẽ sử dụng DelegatingSecurityContextRunnable hoặc DelegatingSecurityContextExecutor khi xử lý task bất đồng bộ từ Servlet request như thế nào?
Bạn phân biệt truyền Authentication vào background task với việc tái sử dụng session authentication đã hết hạn như thế nào?
Bạn sẽ quyết định khi nào không nên truyền user SecurityContext cho scheduled job chạy độc lập theo nguyên tắc nào?
Bạn phân tích hành vi của Servlet async processing khi một request bắt đầu tại thread A rồi tiếp tục tại thread B như thế nào?
Bạn sẽ kiểm tra việc propagation SecurityContext qua WebAsyncManagerIntegrationFilter khi MVC trả Callable như thế nào?
Bạn phân biệt xử lý Callable và DeferredResult của Spring MVC về thời điểm context có thể cần được truyền sang thread khác ra sao?
Bạn sẽ thiết kế test request bất đồng bộ bảo đảm Authentication không bị lẫn giữa hai user như thế nào?
Bạn mô tả khi nào SecurityContext cần được lưu trước khi Servlet response commit hoặc redirect tới login success page ra sao?
Bạn sẽ xác định lý do exception ở async dispatch không tạo phản hồi phù hợp nếu filter chain không được gọi như dự kiến như thế nào?
Bạn đánh giá tác động của việc tự tạo thread trong MVC controller lên cleanup và SecurityContext propagation ra sao?
Bạn phân tích vì sao dùng @Async không tự bảo đảm phương thức nền có đầy đủ user authentication context như thế nào?
Bạn giải thích AuthenticationManager và AuthenticationProvider phối hợp để kiểm tra thông tin đăng nhập trong Servlet application như thế nào?
Bạn phân biệt Authentication trước kiểm tra credentials với Authentication đã xác minh thành công theo các thuộc tính nào?
Bạn mô tả UsernamePasswordAuthenticationFilter lấy username và password từ form login POST như thế nào?
Bạn sẽ cấu hình formLogin với loginPage, loginProcessingUrl và các success/failure handlers theo cách nào?
Bạn phân biệt đường dẫn GET hiển thị trang login với đường dẫn POST do authentication filter xử lý ra sao?
Bạn sẽ xử lý form login khi user vào trước một protected URL để sau xác thực quay lại đúng trang như thế nào?
Bạn mô tả RequestCache lưu SavedRequest và SavedRequestAwareAuthenticationSuccessHandler dùng nó như thế nào?
Bạn phân tích rủi ro open redirect nếu ứng dụng tin tham số redirect do client gửi sau đăng nhập ra sao?
Bạn sẽ chọn AuthenticationSuccessHandler và AuthenticationFailureHandler cho trang HTML khác với JSON API như thế nào?
Bạn phân biệt AuthenticationEntryPoint với AuthenticationFailureHandler theo lý do request cần xác thực hay đăng nhập thất bại ra sao?
Bạn sẽ cấu hình LoginUrlAuthenticationEntryPoint cho browser và 401 JSON entry point cho REST API như thế nào?
Bạn mô tả BasicAuthenticationFilter xác thực header Authorization: Basic trong Servlet request như thế nào?
Bạn phân biệt HTTP Basic với form login về cách client lưu và gửi lại credentials ra sao?
Bạn sẽ quyết định khi nào HTTP Basic có thể dùng cho endpoint nội bộ và những biện pháp TLS/rate limiting nào phải có?
Bạn phân tích vì sao HTTP Basic credentials có thể bị lộ qua proxy logs nếu không có quy tắc loại bỏ headers ra sao?
Bạn sẽ xác định vai trò của UserDetailsService và DaoAuthenticationProvider trong username/password login như thế nào?
Bạn mô tả PasswordEncoder.matches so sánh mật khẩu với stored hash mà không cần giải mã hash ra sao?
Bạn phân biệt DelegatingPasswordEncoder với BCryptPasswordEncoder khi cần thay đổi thuật toán hash qua thời gian như thế nào?
Bạn sẽ thiết kế nâng cấp password hash không khiến user phải đổi mật khẩu ngay khi triển khai phiên bản mới ra sao?
Bạn phân tích nguy cơ báo rõ tài khoản không tồn tại so với mật khẩu sai làm lộ user enumeration như thế nào?
Bạn sẽ xử lý account disabled, locked hoặc password expired mà vẫn giữ thông báo HTTP phù hợp ra sao?
Bạn mô tả ProviderManager chọn AuthenticationProvider phù hợp với UsernamePasswordAuthenticationToken như thế nào?
Bạn sẽ xác định hành vi khi nhiều providers cùng supports một token type nhưng có mức độ tin cậy khác nhau ra sao?
Bạn phân tích nguy cơ fallback sang phương thức xác thực yếu hơn khi provider mạnh báo BadCredentialsException như thế nào?
Bạn sẽ thiết kế logout sau một lần login bằng form để xóa SecurityContext và invalidate HttpSession ra sao?
Bạn phân biệt logout success redirect với việc xác nhận server đã thu hồi phiên đăng nhập như thế nào?
Bạn sẽ xử lý login failure trong một request đang có session cũ để không vô tình giữ quyền của principal trước đó như thế nào?
Bạn đánh giá khi nào nên yêu cầu user xác thực lại trước khi thay đổi mật khẩu hoặc phương thức MFA ra sao?
Bạn sẽ kiểm thử full login flow từ POST credentials tới protected MVC controller thay vì chỉ mock Authentication như thế nào?
Bạn mô tả HttpSessionSecurityContextRepository giúp duy trì login state giữa các requests trình duyệt ra sao?
Bạn phân biệt Servlet HttpSession với SecurityContext được giữ trong request hiện tại về vòng đời như thế nào?
Bạn sẽ chọn SessionCreationPolicy.IF_REQUIRED so với SessionCreationPolicy.STATELESS theo các loại endpoint như thế nào?
Bạn phân tích vì sao bật STATELESS cho một chain bảo vệ HTML login có thể làm session persistence không như mong đợi ra sao?
Bạn sẽ xác định khi nào SessionCreationPolicy.NEVER không đồng nghĩa ứng dụng sẽ không dùng HttpSession có sẵn như thế nào?
Bạn mô tả SessionAuthenticationStrategy tham gia vào các thay đổi liên quan session sau xác thực như thế nào?
Bạn giải thích session fixation attack có thể xảy ra khi session ID không thay đổi sau khi đăng nhập ra sao?
Bạn sẽ cấu hình bảo vệ session fixation bằng changeSessionId hoặc migrateSession theo giới hạn Servlet container nào?
Bạn phân biệt changeSessionId và newSession trong chính sách chống session fixation theo dữ liệu được giữ lại ra sao?
Bạn sẽ kiểm tra ID session trước và sau login mà vẫn xác nhận các attributes hợp lệ không bị mất như thế nào?
Bạn phân tích nguy cơ lưu secrets hoặc credentials trong HttpSession kéo dài quá thời gian cần thiết ra sao?
Bạn sẽ cấu hình cookie Secure, HttpOnly và SameSite theo HTTPS và cross-site UI architecture như thế nào?
Bạn phân biệt SameSite=Lax với SameSite=None khi frontend và backend nằm trên các sites khác nhau ra sao?
Bạn sẽ thiết kế timeout phiên theo inactivity và chính sách absolute expiration mà không nhầm hai khái niệm như thế nào?
Bạn mô tả SessionRegistry giúp theo dõi active sessions trong cấu hình concurrency control ra sao?
Bạn sẽ giới hạn số concurrent sessions cho một tài khoản khi đăng nhập từ nhiều browsers như thế nào?
Bạn phân biệt ConcurrentSessionControlAuthenticationStrategy với ConcurrentSessionFilter về nhiệm vụ như thế nào?
Bạn sẽ đánh giá khi nào cần HttpSessionEventPublisher để session registry nhận đúng session destruction events ra sao?
Bạn phân tích vì sao concurrency control cục bộ không đủ khi chạy nhiều Spring Boot replicas sau load balancer ra sao?
Bạn sẽ lựa chọn Spring Session hoặc shared session storage cho ứng dụng nhiều pods theo yêu cầu nào?
Bạn sẽ kiểm tra session affinity và khả năng chia sẻ session state giữa các instances khi một instance bị restart như thế nào?
Bạn đánh giá rủi ro user bị khóa tài khoản nhưng session cũ vẫn còn Authentication với quyền hợp lệ ra sao?
Bạn mô tả RememberMeAuthenticationFilter phục hồi danh tính trong tình huống session hết hạn như thế nào?
Bạn phân biệt remember-me cookie với session cookie về mục tiêu, mức tin cậy và khả năng revoke ra sao?
Bạn sẽ quyết định khi nào cần PersistentTokenBasedRememberMeServices thay vì token-based remember-me không lưu trạng thái phía server ra sao?
Bạn phân tích nguy cơ remember-me token bị lấy cắp và được tái sử dụng trong thời gian dài như thế nào?
Bạn sẽ thiết kế policy xóa remember-me token khi logout hoặc đổi mật khẩu theo kỳ vọng bảo mật nào?
Bạn mô tả SecurityContextLogoutHandler thực hiện những thao tác cleanup nào khi logout được gọi ra sao?
Bạn phân biệt LogoutHandler và LogoutSuccessHandler khi tích hợp cleanup nhiều nguồn state như thế nào?
Bạn sẽ cấu hình logout URL, HTTP method và CSRF rule để một website khác không thể kích hoạt logout trái ý muốn như thế nào?
Bạn sẽ làm gì khi browser xóa session cookie nhưng server session chưa được invalidate và còn hiệu lực ra sao?
Bạn phân tích rủi ro một session ID đi qua URL rewriting và xuất hiện trong browser history hoặc logs như thế nào?
Bạn sẽ kiểm thử truy cập trang yêu cầu fullyAuthenticated với một remember-me authentication để xác minh chính sách ra sao?
Bạn sẽ xác định cách người dùng logout một thiết bị khác khi ứng dụng hỗ trợ nhiều sessions theo cách nào?
Bạn đánh giá khi nào cần làm mới authorities trong session sau khi backend thay đổi roles của user như thế nào?
Bạn giải thích authorizeHttpRequests dùng AuthorizationManager để quyết định truy cập Servlet HTTP requests như thế nào?
Bạn phân biệt authenticated(), fullyAuthenticated() và permitAll() khi áp dụng quy tắc cho MVC endpoint ra sao?
Bạn sẽ thiết kế rule cho GET /orders và DELETE /orders/{id} dựa trên các authorities khác nhau như thế nào?
Bạn phân biệt hasRole với hasAuthority khi user có GrantedAuthority chứa tiền tố ROLE_ như thế nào?
Bạn sẽ xác định vì sao cấu hình hasRole("ADMIN") từ chối một authentication có authority "ADMIN" ra sao?
Bạn phân tích nguy cơ áp dụng requestMatchers("/api/**").permitAll() trước matcher bảo vệ /api/admin/** như thế nào?
Bạn sẽ kiểm tra đường dẫn /api/orders/{id} với HTTP method khác nhau không bị áp dụng rule quá rộng như thế nào?
Bạn mô tả cách RequestMatcher sử dụng method, path hoặc các thuộc tính request khác để xác định authorization policy ra sao?
Bạn phân biệt securityMatcher chọn chain với authorization matcher chọn chính sách truy cập như thế nào?
Bạn sẽ xây dựng một AuthorizationManager tùy chỉnh khi quyền phụ thuộc tenant hoặc ownerId như thế nào?
Bạn phân tích vì sao role USER không đủ để xác nhận user sở hữu bản ghi được gọi qua path variable ra sao?
Bạn sẽ đặt kiểm tra object ownership ở service layer để bảo vệ cả MVC và background calls theo cách nào?
Bạn phân biệt request-based authorization với method-level authorization khi cùng service được nhiều controllers gọi như thế nào?
Bạn sẽ kích hoạt @EnableMethodSecurity và sử dụng @PreAuthorize để bảo vệ một service method ra sao?
Bạn phân tích rủi ro method security dùng proxy không chặn self-invocation trong cùng bean như thế nào?
Bạn sẽ sử dụng @PostAuthorize khi quyền phụ thuộc object trả về nhưng cần cân nhắc side effects nào?
Bạn mô tả ExceptionTranslationFilter phân biệt unauthenticated với access denied khi method security ném lỗi như thế nào?
Bạn sẽ trả về JSON 403 cho một user đã đăng nhập nhưng thiếu permission theo chuẩn response nào?
Bạn phân tích rủi ro trả 404 để che existence của tài nguyên nhưng ghi lỗi không nhất quán khiến thông tin vẫn bị lộ ra sao?
Bạn sẽ áp dụng denial logging không đưa thông tin cá nhân hoặc chi tiết nội bộ về policy vào logs như thế nào?
Bạn sẽ tổ chức tests cho admin-only MVC endpoints, owner-only object access và anonymous requests ra sao?
Bạn sẽ xác định khi nào @AuthenticationPrincipal được dùng để tìm domain user mà không để client giả danh qua request payload như thế nào?
Bạn phân biệt protected resources và public static assets để thiết kế policy không làm hỏng trang login ra sao?
Bạn sẽ đặt fallback anyRequest().denyAll() sau các authorization matchers theo yêu cầu an toàn nào?
Bạn đánh giá vai trò của deny-by-default trong ứng dụng MVC có nhiều controller mới được bổ sung theo thời gian như thế nào?
Bạn giải thích CSRF tấn công một Servlet application dùng cookie-based authentication qua hành vi nào của trình duyệt?
Bạn phân biệt CSRF protection với authentication và authorization khi request đã mang session cookie hợp lệ ra sao?
Bạn mô tả CsrfFilter xác minh CSRF token cho các HTTP methods có khả năng thay đổi trạng thái như thế nào?
Bạn sẽ xác định khi nào một HTTP GET có side effect làm thiết kế trở nên rủi ro dù được coi là safe method ra sao?
Bạn phân biệt HttpSessionCsrfTokenRepository với CookieCsrfTokenRepository về nơi lưu token và cách frontend truy cập như thế nào?
Bạn sẽ cấu hình CSRF token trên form login và form logout theo những bước nào?
Bạn phân tích vì sao API chỉ có JSON body nhưng vẫn dùng session cookie thì không thể bỏ qua CSRF ra sao?
Bạn sẽ thiết kế cơ chế lấy CSRF token cho một SPA được phục vụ từ Spring MVC theo cách nào?
Bạn mô tả CsrfTokenRequestAttributeHandler xử lý việc đưa CSRF token vào request attributes như thế nào?
Bạn sẽ kiểm tra ảnh hưởng của deferred CSRF token loading tới trang HTML hoặc SPA ra sao?
Bạn phân tích khi nào cơ chế BREACH protection và token masking ảnh hưởng cách SPA gửi CSRF token từ cookie ra sao?
Bạn sẽ thiết kế ngoại lệ CSRF tối thiểu cho webhook có chữ ký độc lập mà không tắt CSRF cho toàn bộ /api/** ra sao?
Bạn phân biệt CSRF attack với cross-origin fetch bị CORS chặn theo khả năng browser vẫn gửi request như thế nào?
Bạn mô tả CorsFilter hoặc CORS integration trong HttpSecurity tham gia xử lý preflight OPTIONS trước authentication ra sao?
Bạn sẽ cấu hình CorsConfigurationSource với allowlisted origins, methods và headers cho frontend riêng như thế nào?
Bạn phân tích nguy cơ sử dụng wildcard origin đồng thời cho phép credentials khiến dữ liệu nhạy cảm bị truy cập sai ra sao?
Bạn sẽ xác định khi nào Access-Control-Allow-Credentials cần thiết cho cookie session và khi nào nên tránh nó như thế nào?
Bạn phân biệt same-origin với same-site để lựa chọn SameSite cookie và CSRF protection ra sao?
Bạn sẽ kiểm tra trường hợp preflight OPTIONS bị trả 401 hoặc 403 trước khi controller nhận actual request như thế nào?
Bạn giải thích vì sao CORS không thay thế bearer-token validation hoặc object authorization như thế nào?
Bạn sẽ xác minh browser chặn đọc response do CORS nhưng server vẫn đã xử lý request state-changing như thế nào?
Bạn phân tích rủi ro cấu hình allowedOrigins quá rộng trong một ứng dụng có privileged admin API như thế nào?
Bạn sẽ thiết kế CORS policies riêng cho /api/** và /ui/** khi hai filter chains có đặc thù khác nhau như thế nào?
Bạn sẽ chẩn đoán CSRF token không khớp do session đổi sau login trong một browser flow như thế nào?
Bạn sẽ kiểm thử một POST có HttpSession cookie hợp lệ nhưng thiếu CSRF token bị từ chối ra sao?
Bạn sẽ kiểm thử một POST có CSRF token đúng nhưng thiếu authority vẫn bị từ chối theo authorization rules như thế nào?
Bạn sẽ thiết kế test cho cross-origin request có Origin không thuộc allowlist mà không nhầm kết quả với authentication failure ra sao?
Bạn đánh giá rủi ro disabled CSRF trên tất cả routes chỉ để unit tests dễ viết hơn như thế nào?
Bạn sẽ phân biệt trường hợp tắt CSRF hợp lý cho API stateless dùng Authorization bearer header với trường hợp vẫn dùng cookie authentication ra sao?
Bạn sẽ thiết kế chính sách CSRF/CORS cho một ứng dụng có cả MVC login và REST API không trạng thái như thế nào?
Bạn giải thích các HTTP security headers mặc định có mục tiêu bảo vệ nào trong Spring Security Servlet?
Bạn sẽ sử dụng HttpSecurity.headers để cấu hình Content-Security-Policy khi ứng dụng phục vụ trang HTML như thế nào?
Bạn phân biệt CSP script-src với frame-ancestors trong bảo vệ nội dung và chống clickjacking ra sao?
Bạn sẽ lựa chọn X-Frame-Options hoặc CSP frame-ancestors tùy chính sách embedding nào?
Bạn phân tích nguy cơ tắt frame options để nhúng một admin screen vào iframe không tin cậy ra sao?
Bạn mô tả Strict-Transport-Security giúp browser ghi nhớ yêu cầu dùng HTTPS như thế nào?
Bạn sẽ xác định điều kiện nào cần kiểm tra trước khi bật HSTS includeSubDomains ở môi trường production ra sao?
Bạn phân biệt HTTPS redirect tại reverse proxy với chính sách HSTS do ứng dụng công bố theo vai trò nào?
Bạn sẽ cấu hình X-Content-Type-Options để giảm nguy cơ browser tự đoán MIME type như thế nào?
Bạn phân tích vì sao XSS vẫn có thể xảy ra dù đã bật CSRF và session security như thế nào?
Bạn sẽ thiết kế CSP phù hợp với HTML template hoặc SPA mà không phải dùng unsafe-inline rộng rãi như thế nào?
Bạn đánh giá khi nào cần phát hành CSP Report-Only trước khi bắt đầu chặn script ngoài policy ra sao?
Bạn sẽ kiểm tra response headers thực tế sau reverse proxy để bảo đảm headers do Spring Security tạo không bị proxy xóa ra sao?
Bạn phân tích rủi ro lộ session cookie qua request chạy HTTP nếu TLS termination và Secure cookie không được cấu hình đúng như thế nào?
Bạn sẽ dùng ForwardedHeaderFilter hoặc cấu hình trusted forwarded headers khi ứng dụng chạy sau reverse proxy theo yêu cầu nào?
Bạn đánh giá nguy cơ tin X-Forwarded-Proto do client tự gửi nếu reverse proxy chưa làm sạch header như thế nào?
Bạn sẽ thiết kế audit events cho 401/403 và login failures mà không ghi mật khẩu, cookies hoặc access tokens ra sao?
Bạn phân biệt lỗi application trả 403 với lỗi WAF hoặc reverse proxy trả 403 theo dấu vết nào?
Bạn sẽ xây dựng monitoring cho số lần 401, 403, CSRF rejections và login latency bằng Micrometer như thế nào?
Bạn sẽ tránh đưa user ID, session ID hoặc raw URL chứa token vào metric labels để hạn chế cardinality và lộ dữ liệu ra sao?
Bạn phân tích tác động của một authentication provider bị chậm lên số Servlet request threads đang bị chiếm giữ như thế nào?
Bạn sẽ cấu hình timeout cho LDAP/OIDC calls để login không chặn Servlet threads quá lâu ra sao?
Bạn sẽ xác định khi nào một browser security issue xuất phát từ cookie policy thay vì Spring Security authorization như thế nào?
Bạn đánh giá cách làm health/readiness checks không cần bypass toàn bộ filter chain ra sao?
Bạn mô tả oauth2Login() thêm các thành phần gì vào một Servlet SecurityFilterChain để hỗ trợ browser login qua OpenID Provider?
Bạn phân biệt OAuth2 Login và OAuth2 Resource Server trong Spring Security theo cơ chế đăng nhập và dữ liệu Authentication ra sao?
Bạn sẽ xác định vai trò của ClientRegistrationRepository khi cấu hình nhiều OAuth2 login providers như thế nào?
Bạn mô tả OAuth2AuthorizationRequestRedirectFilter khởi tạo OAuth2 authorization code flow như thế nào?
Bạn sẽ phân biệt authorization request lưu state với HTTP session authentication sau callback thành công như thế nào?
Bạn phân tích nguy cơ state mismatch khi browser mở nhiều login tabs hoặc callback đến sai session như thế nào?
Bạn sẽ sử dụng OAuth2LoginAuthenticationFilter để hoàn tất callback nhận authorization code theo cơ chế nào?
Bạn mô tả PKCE và state hỗ trợ giảm các rủi ro nào khi sử dụng authorization code flow ra sao?
Bạn sẽ xác định redirect URI phải khớp với đăng ký tại IdP và cấu hình reverse proxy như thế nào?
Bạn phân biệt OidcUser với OAuth2User về thông tin danh tính và claims cung cấp cho Spring MVC như thế nào?
Bạn sẽ ánh xạ OAuth2User authorities sang các quyền nội bộ mà không tin toàn bộ attributes được trả về như thế nào?
Bạn phân tích rủi ro liên kết tài khoản theo email mà không kiểm tra issuer và subject của OIDC token ra sao?
Bạn sẽ thiết kế local logout khác với OIDC RP-initiated logout theo tính năng IdP hỗ trợ như thế nào?
Bạn đánh giá khi nào cần xóa OAuth2AuthorizedClient cùng local session khi user logout ra sao?
Bạn sẽ tổ chức browser login qua OIDC trong /ui/** và bearer JWT cho /api/** mà không lẫn cơ chế xác thực như thế nào?
Bạn mô tả oauth2ResourceServer().jwt() cấu hình bearer token validation cho Servlet REST API như thế nào?
Bạn phân biệt BearerTokenAuthenticationFilter với OAuth2LoginAuthenticationFilter về loại request và đầu vào như thế nào?
Bạn sẽ đặt SessionCreationPolicy.STATELESS cho bearer-only API trong khi browser chain vẫn dùng HttpSession như thế nào?
Bạn phân tích vì sao dùng ID token thay bearer access token cho API có thể sai audience và ý nghĩa token ra sao?
Bạn sẽ cấu hình JwtDecoder kiểm tra issuer, audience, thời hạn và chữ ký trước khi chấp nhận Authentication như thế nào?
Bạn sẽ sử dụng JwtAuthenticationConverter để chuyển scope claims thành GrantedAuthority theo API policy như thế nào?
Bạn phân biệt scope SCOPE_orders.read với role ROLE_ADMIN khi xây dựng hasAuthority và hasRole ra sao?
Bạn sẽ giải thích khi nào nên dùng opaque token introspection thay vì JWT validation cục bộ theo yêu cầu thu hồi quyền nào?
Bạn sẽ kiểm tra API trả 401 invalid_token khác 403 insufficient_scope khi bearer token đã được xác minh ra sao?
Bạn phân tích nguy cơ token bị log qua Authorization header khi một security filter ném exception ra sao?
Bạn sẽ đánh giá tác động khi /api/** có cả cookie-based authentication và bearer authentication ngoài ý muốn ra sao?
Bạn sẽ thiết kế tests phân biệt session user có quyền trên HTML page với bearer client chỉ được gọi REST endpoints nào?
Bạn sẽ chẩn đoán một OAuth2 callback thất bại do wrong forwarded host hoặc redirect scheme sau reverse proxy như thế nào?
Bạn sẽ kiểm tra refresh token hoặc authorized client credentials không bị trả ra frontend JSON của một MVC controller như thế nào?
Bạn đánh giá yêu cầu kiểm thử invalid issuer, expired bearer token và OAuth2 state mismatch trên Servlet stack như thế nào?
Bạn phân biệt unit test AuthorizationManager với MockMvc integration test chạy toàn bộ Spring Security Servlet filters như thế nào?
Bạn sẽ cấu hình MockMvc với springSecurity() để các security filters thật được dùng trong MVC tests ra sao?
Bạn mô tả @AutoConfigureMockMvc hỗ trợ kiểm thử SecurityFilterChain trong Spring Boot context như thế nào?
Bạn sẽ sử dụng @WebMvcTest cùng cấu hình security cần thiết mà không cho test tự động bỏ qua security ra sao?
Bạn phân tích vì sao dùng @WithMockUser không chứng minh filter authentication hoặc password encoder hoạt động thực tế như thế nào?
Bạn sẽ sử dụng @WithUserDetails khi cần nạp UserDetails thật cho các method-security tests như thế nào?
Bạn mô tả user() request postprocessor giả lập Authentication tại request level theo mục tiêu nào?
Bạn sẽ dùng formLogin() và csrf() request postprocessors để test đăng nhập thành công như thế nào?
Bạn sẽ kiểm tra formLogin failure mà không để framework trả thông báo có thể phân biệt username tồn tại ra sao?
Bạn phân biệt kiểm tra HTTP redirect sau login với kiểm tra SecurityContext đã lưu cho request kế tiếp như thế nào?
Bạn sẽ dùng MockHttpSession qua hai requests liên tiếp để xác minh authenticated session được duy trì ra sao?
Bạn sẽ kiểm tra session fixation protection qua sự thay đổi session ID sau form login như thế nào?
Bạn mô tả logout() request postprocessor giúp kiểm tra flow đăng xuất trong MockMvc như thế nào?
Bạn sẽ kiểm thử logout làm request sau không còn truy cập được endpoint protected như thế nào?
Bạn phân tích rủi ro chỉ test cookie bị xóa mà không kiểm tra HttpSession bị invalidate ra sao?
Bạn sẽ kiểm thử GET public resource và POST state-changing resource để thấy CSRF protection hoạt động thế nào?
Bạn sẽ dùng csrf().useInvalidToken() để mô phỏng CSRF token sai trong MockMvc test như thế nào?
Bạn đánh giá cách test POST không CSRF token nhưng có authenticated user để phân biệt 403 do CSRF với 403 do thiếu role ra sao?
Bạn sẽ kiểm thử preflight OPTIONS qua MockMvc với Origin và Access-Control-Request-Method như thế nào?
Bạn sẽ kiểm tra CORS response headers không cấp credential access cho origin không được phép ra sao?
Bạn mô tả cách kiểm tra các security headers như HSTS, CSP và X-Frame-Options qua test HTTP response như thế nào?
Bạn sẽ thiết kế test nhiều SecurityFilterChain để xác nhận /ui/account không nhận bearer-only policy của /api/** ra sao?
Bạn phân tích vì sao @WithMockUser có thể che lỗi matcher khiến API không có authentication filter ra sao?
Bạn sẽ dùng jwt() request postprocessor cho authorization test nhưng không coi đó là test JwtDecoder validation như thế nào?
Bạn sẽ xây dựng integration test JWT ký bằng test key để xác minh decoder thực sự từ chối invalid signature như thế nào?
Bạn sẽ kiểm tra OIDC callback sai state hoặc nonce với một mock IdP trong Servlet integration test như thế nào?
Bạn phân biệt kiểm thử Servlet async MVC Callable với một test service method dùng @Async khi xác minh SecurityContext propagation như thế nào?
Bạn sẽ dùng asyncDispatch trong MockMvc để xác minh kết quả controller bất đồng bộ có đúng security context như thế nào?
Bạn đánh giá test bảo vệ error dispatch và error pages để tránh vô tình lộ dữ liệu ngoài security chain ra sao?
Bạn sẽ kiểm tra filters hoặc method security chặn access khi client đổi HTTP method dù path vẫn như cũ ra sao?
Bạn phân tích rủi ro suite chỉ test roles được phép mà không test unauthenticated và forbidden cases như thế nào?
Bạn sẽ thiết kế test với path encoding, trailing slash và context path để phát hiện matcher bypass như thế nào?
Bạn sẽ dùng Testcontainers khi cần xác minh browser login từ external LDAP hoặc session store thật trong integration test ra sao?
Bạn sẽ kiểm tra production build không vô tình dùng security test configuration có permitAll quá rộng như thế nào?
Bạn sẽ tổ chức test data với mật khẩu giả và token giả để không lộ thông tin môi trường thật vào CI logs ra sao?
Bạn sẽ xác định các negative tests tối thiểu cho form login, session, logout, CSRF, CORS, bearer token và admin access ra sao?
Nếu /api/orders trả redirect tới login page thay vì 401 JSON, bạn sẽ kiểm tra SecurityFilterChain matching và AuthenticationEntryPoint như thế nào?
Nếu một public endpoint bị 403 do rule anyRequest().denyAll(), bạn sẽ xác định vị trí requestMatchers phù hợp như thế nào?
Nếu một Servlet Filter tự đăng ký lại qua HttpSecurity làm kiểm tra token hai lần, bạn sẽ loại bỏ duplicate registration ra sao?
Nếu request có trailing slash hoặc encoded slash đi qua rule sai, bạn sẽ điều tra RequestMatcher và StrictHttpFirewall như thế nào?
Nếu form login POST trả 403 trước khi kiểm mật khẩu, bạn sẽ kiểm tra CsrfFilter và loginProcessingUrl ra sao?
Nếu user login thành công nhưng request kế tiếp anonymous, bạn sẽ kiểm tra saveContext, SecurityContextRepository và SessionCreationPolicy như thế nào?
Nếu SecurityContext bị lẫn giữa hai requests khi một thread pool được tái sử dụng, bạn sẽ kiểm tra cleanup và context propagation ra sao?
Nếu user A sửa dữ liệu user B vì endpoint chỉ dùng authenticated(), bạn sẽ bổ sung authorization ở tầng dữ liệu hoặc service như thế nào?
Nếu method @PreAuthorize không hoạt động do self-invocation, bạn sẽ thay đổi cách gọi hoặc thiết kế bean như thế nào?
Nếu HttpSession ID không đổi sau login, bạn sẽ kiểm tra session fixation protection và SessionAuthenticationStrategy ra sao?
Nếu logout chỉ xóa cookie còn HttpSession vẫn hoạt động, bạn sẽ thiết kế lại LogoutHandler và verification ra sao?
Nếu CSRF được tắt để cho webhook chạy nhưng các form nhạy cảm cũng mất bảo vệ, bạn sẽ giới hạn exception theo matcher như thế nào?
Nếu preflight OPTIONS bị 401 dù actual request có bearer token, bạn sẽ điều chỉnh CORS integration và filter order ra sao?
Nếu SameSite cookie không được gửi trong OAuth2 callback, bạn sẽ đánh giá cookie policy và flow redirects như thế nào?
Nếu reverse proxy trả X-Forwarded-Proto không chuẩn khiến OAuth2 redirect URI sai, bạn sẽ kiểm tra trusted forwarded headers ra sao?
Nếu session concurrency giới hạn một login nhưng user vẫn có nhiều phiên trên các pods, bạn sẽ kiểm tra shared session state và SessionRegistry như thế nào?
Nếu access token hết hạn nhưng API trả 403 thay vì 401, bạn sẽ kiểm tra BearerTokenAuthenticationEntryPoint và JWT validation ra sao?
Nếu browser login qua OIDC thành công nhưng API bearer security chain nhận nhầm session, bạn sẽ chỉnh matcher và stateless policy như thế nào?
Nếu MockMvc @WithMockUser tests PASS nhưng production login lỗi, bạn sẽ bổ sung test thật qua form filters và PasswordEncoder ra sao?
Nếu triển khai Spring MVC production có admin pages, form login, session và OAuth2-protected API, bạn sẽ tổ chức filter chains, SecurityContext, CSRF/CORS, logout và kiểm thử như thế nào?

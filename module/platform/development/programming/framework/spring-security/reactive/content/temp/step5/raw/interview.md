Bạn giải thích Spring Security bảo vệ ứng dụng Spring WebFlux theo mô hình reactive khác với ứng dụng Servlet MVC như thế nào?
Bạn phân biệt SecurityWebFilterChain và SecurityFilterChain của Servlet stack về kiểu filter, ngữ cảnh thực thi và khả năng dùng chung cấu hình ra sao?
Bạn mô tả một HTTP request đi qua WebFilterChainProxy, SecurityWebFilterChain và WebFlux handler được bảo vệ như thế nào?
Bạn giải thích vai trò của ServerHttpSecurity khi định nghĩa xác thực, phân quyền và các cơ chế bảo vệ HTTP trong WebFlux ra sao?
Bạn xác định lúc nào dùng cấu hình mặc định của Spring Security và lúc nào cần khai báo một SecurityWebFilterChain riêng cho ứng dụng như thế nào?
Bạn thiết kế SecurityWebFilterChain yêu cầu xác thực với API riêng tư nhưng vẫn cho phép truy cập health endpoint công khai như thế nào?
Bạn phân biệt securityMatcher ở cấp SecurityWebFilterChain với pathMatchers trong authorizeExchange theo phạm vi áp dụng chính sách ra sao?
Bạn đánh giá rủi ro đặt một matcher quá rộng trước một chain đặc thù khiến chain phía sau không bao giờ được áp dụng như thế nào?
Bạn thiết kế nhiều SecurityWebFilterChain có thứ tự rõ ràng để tách bảo mật API bearer token và trang web đăng nhập bằng session ra sao?
Bạn giải thích cách SecurityWebFiltersOrder giúp xác định vị trí tương đối của các bộ lọc bảo mật reactive như thế nào?
Bạn phân biệt WebFilter dùng cho xử lý HTTP chung với SecurityWebFilterChain dùng cho xác thực và kiểm soát truy cập ra sao?
Bạn xác định khi nào custom WebFilter không nên tự parse JWT hoặc tự cấp quyền thay cho Spring Security authentication manager như thế nào?
Bạn thiết kế quy tắc phân quyền theo HTTP method và path để GET công khai nhưng POST chỉ dành cho người có quyền phù hợp ra sao?
Bạn phân biệt pathMatchers với matcher dựa trên ServerWebExchange khi chính sách còn phụ thuộc header hoặc thuộc tính request như thế nào?
Bạn phân tích rủi ro đặt anyExchange().permitAll trước các quy tắc bảo vệ tài nguyên quan trọng trong cấu hình authorizeExchange như thế nào?
Bạn xác định cách kiểm tra policy khi route có biến đường dẫn, trailing slash hoặc URL encoded characters để tránh bypass như thế nào?
Bạn thiết kế endpoint trả HTTP 401 cho caller chưa xác thực và HTTP 403 cho caller đã xác thực nhưng thiếu quyền như thế nào?
Bạn phân biệt ServerAuthenticationEntryPoint với ServerAccessDeniedHandler trong xử lý lỗi bảo mật của WebFlux ra sao?
Bạn cấu hình phản hồi lỗi authentication theo ProblemDetail hoặc JSON contract mà không để lộ chi tiết xác minh credentials như thế nào?
Bạn đánh giá sự khác nhau giữa lỗi từ Spring Security WebFilter và lỗi domain được xử lý bởi WebExceptionHandler của WebFlux như thế nào?
Bạn lựa chọn khi nào dùng HTTP Basic cho môi trường nội bộ có kiểm soát và khi nào cần OAuth2 bearer token cho API công khai ra sao?
Bạn phân biệt việc thiết lập SecurityContext trong Servlet bằng ThreadLocal với cách reactive chain gắn security information vào Reactor Context như thế nào?
Bạn giải thích cách ReactiveSecurityContextHolder cung cấp SecurityContext cho các thành phần bên trong cùng reactive subscriber chain ra sao?
Bạn xác định vì sao gọi SecurityContextHolder.getContext() trong một WebFlux handler không phải cách tin cậy để lấy principal reactive như thế nào?
Bạn sử dụng ReactiveSecurityContextHolder.getContext() để lấy Authentication trong một Mono pipeline mà không gọi block như thế nào?
Bạn phân biệt Reactor Context với mutable request attributes hoặc singleton state khi mang danh tính người dùng qua các bước bất đồng bộ ra sao?
Bạn thiết kế việc thêm correlation ID vào Reactor Context nhưng không vô tình ghi đè SecurityContext mà Spring Security đã tạo ra như thế nào?
Bạn giải thích contextWrite tác động tới ngữ cảnh của subscriber và vì sao vị trí đặt operator có thể làm thay đổi khả năng đọc context như thế nào?
Bạn xác định khi nào deferContextual phù hợp để lấy metadata theo từng subscription thay vì truy cập biến global có thể bị dùng chung như thế nào?
Bạn phân tích tác động của subscribeOn và publishOn tới thread thực thi và vì sao Reactor Context không đồng nghĩa ThreadLocal context như thế nào?
Bạn kiểm tra một pipeline chuyển qua scheduler khác có còn truy cập đúng ReactiveSecurityContextHolder hay không bằng kỹ thuật nào?
Bạn thiết kế xử lý bất đồng bộ trong controller mà không tự gọi subscribe làm mất quyền kiểm soát lifecycle và security context của WebFlux ra sao?
Bạn đánh giá rủi ro tạo một CompletableFuture ngoài Reactor chain rồi giả định SecurityContext sẽ được truyền tự động như thế nào?
Bạn lựa chọn cách truyền identity hoặc authorization metadata vào background job khi tác vụ tiếp tục sau khi HTTP request kết thúc như thế nào?
Bạn phân biệt SecurityContext với transaction context và tracing context để tránh coi chúng có cùng vòng đời hoặc cách propagation ra sao?
Bạn thiết kế test hai requests khác tenant chạy đồng thời nhằm phát hiện SecurityContext bị trộn giữa các subscriptions như thế nào?
Bạn phân tích sự cố một flatMap branch lấy nhầm principal do shared mutable field trong singleton bean bằng cách nào?
Bạn đánh giá vì sao không nên giữ Authentication của người dùng hiện tại trong instance variable của WebFilter hoặc service singleton như thế nào?
Bạn xác định cách logging user ID an toàn trong WebFlux khi MDC dùng ThreadLocal và một event-loop thread phục vụ nhiều requests như thế nào?
Bạn thiết kế giải pháp context propagation cho reactive-to-blocking adapter mà không chuyển token hoặc principal qua ThreadLocal không được dọn ra sao?
Bạn giải thích khi nào cần dùng Context Propagation utilities cho observability mà không đồng nhất propagation tracing với propagation authorization như thế nào?
Bạn xác định những hạn chế khi dùng @Async hoặc scheduled tasks bên ngoài HTTP pipeline để truy cập SecurityContext của caller như thế nào?
Bạn mô tả vai trò của AuthenticationWebFilter trong việc trích xuất credentials và thực hiện xác thực trên reactive HTTP request như thế nào?
Bạn phân biệt ServerAuthenticationConverter với ReactiveAuthenticationManager về nhiệm vụ tạo Authentication token và xác minh credentials ra sao?
Bạn thiết kế custom ServerAuthenticationConverter để đọc một header xác thực riêng mà không chấp nhận dữ liệu tùy ý từ query string ra sao?
Bạn xác định cách xử lý AuthenticationWebFilter khi request không có credentials so với khi credentials được cung cấp nhưng sai như thế nào?
Bạn sử dụng ReactiveAuthenticationManager để xác minh một loại Authentication riêng mà không block event-loop như thế nào?
Bạn phân biệt AuthenticationWebFilter authentication success handler và failure handler theo hành vi đặt context hoặc trả lỗi như thế nào?
Bạn thiết kế kiểm tra credentials qua external service bằng WebClient với timeout, connection limits và phản hồi fail closed ra sao?
Bạn đánh giá rủi ro gọi JDBC blocking hoặc RestClient blocking trực tiếp trong ReactiveAuthenticationManager khi traffic tăng như thế nào?
Bạn xác định khi nào cần tách blocking user store sang boundedElastic và những giới hạn tài nguyên còn tồn tại như thế nào?
Bạn thiết kế retry cho một xác thực phụ thuộc IdP mà không tự động retry khi mật khẩu hoặc token thực sự không hợp lệ như thế nào?
Bạn phân biệt UserDetailsRepositoryReactiveAuthenticationManager với việc tự xây một ReactiveAuthenticationManager dùng external identity service ra sao?
Bạn sử dụng ReactiveUserDetailsService để lấy người dùng mà không đưa thao tác database chặn vào reactive authentication flow như thế nào?
Bạn phân biệt MapReactiveUserDetailsService phù hợp cho thử nghiệm với dịch vụ user store có persistence và audit trong production ra sao?
Bạn thiết kế PasswordEncoder và chính sách kiểm tra mật khẩu trong một reactive login mà không lưu password dạng rõ trong log như thế nào?
Bạn xác định cách bảo vệ endpoint đăng nhập trước brute-force hoặc credential stuffing mà không dựa vào việc block event-loop trong filter như thế nào?
Bạn phân biệt authentication state được lưu trong WebSession với một bearer-token resource server không duy trì phiên đăng nhập như thế nào?
Bạn giải thích vai trò của ServerSecurityContextRepository khi lưu và nạp SecurityContext qua nhiều HTTP requests như thế nào?
Bạn so sánh WebSessionServerSecurityContextRepository với NoOpServerSecurityContextRepository theo yêu cầu stateful login và stateless API như thế nào?
Bạn thiết kế chính sách quản lý web session cho WebFlux có SSO login, timeout và shared session store trong nhiều replica như thế nào?
Bạn đánh giá vì sao local WebSession không tự đồng bộ với phiên SSO tại OpenID Provider khi người dùng đăng xuất từ ứng dụng khác như thế nào?
Bạn xác định khi nào cần rotation session identifier sau xác thực và kiểm tra các tính năng session security theo phiên bản Spring Security ra sao?
Bạn thiết kế cleanup SecurityContext khi logout để subscriber hoặc request mới không còn được coi là authenticated như thế nào?
Bạn phân biệt authentication thành công với authorization hợp lệ cho từng business resource trong một WebFlux service như thế nào?
Bạn giải thích authorizeExchange áp dụng quy tắc ở lớp HTTP khác với reactive method security tại service boundary như thế nào?
Bạn sử dụng @EnableReactiveMethodSecurity để bảo vệ phương thức trả Mono hoặc Flux theo khả năng được hỗ trợ như thế nào?
Bạn thiết kế @PreAuthorize cho một reactive service method nhưng vẫn kiểm tra quyền sở hữu business resource từ database như thế nào?
Bạn phân biệt quyền ROLE_ và authority SCOPE_ khi ánh xạ token claims vào các quy tắc phân quyền ra sao?
Bạn xác định cách tùy biến GrantedAuthority khi Identity Provider trả group claims nhưng ứng dụng chỉ chấp nhận các quyền có trong allowlist như thế nào?
Bạn thiết kế phân quyền theo tenant ID đã được xác thực thay vì tin tenantId do client gửi qua header hoặc path như thế nào?
Bạn đánh giá rủi ro thao tác phân quyền sau khi lấy toàn bộ dữ liệu thay vì áp điều kiện tenant ngay trong truy vấn reactive repository như thế nào?
Bạn xử lý Mono.empty từ bước tải resource trong một rule phân quyền mà không nhầm thành cho phép truy cập mặc định ra sao?
Bạn phân biệt lỗi thiếu quyền với resource không tồn tại khi lựa chọn phản hồi 403 hoặc 404 nhằm hạn chế lộ sự tồn tại của dữ liệu như thế nào?
Bạn thiết kế reactive AuthorizationManager kiểm tra yêu cầu bảo mật bằng Mono mà không giữ shared mutable decision state như thế nào?
Bạn xác định khi nào nên kiểm tra quyền tại route, service và data-access layer để tránh authorization gap giữa các entry points như thế nào?
Bạn phân tích tác động của onErrorResume trong đoạn kiểm tra quyền nếu lỗi truy vấn bị biến thành một quyết định cho phép như thế nào?
Bạn xác định cách đảm bảo các nhánh switchIfEmpty và defaultIfEmpty không vô tình biến thiếu Authentication thành authenticated principal như thế nào?
Bạn thiết kế policy cho việc thu hồi quyền ngay trong phiên đang mở và nêu rõ giới hạn khi authorities chỉ được lấy lúc đăng nhập như thế nào?
Bạn phân biệt scope của access token với kiểm tra quyền truy cập vào một đơn hàng cụ thể thuộc người dùng khác như thế nào?
Bạn đánh giá khi nào cần kiểm tra authorization ở từng message của WebSocket thay vì chỉ tại HTTP handshake như thế nào?
Bạn xác định cách bảo vệ SSE endpoint và xử lý một kết nối dài khi quyền hoặc token bị thu hồi trong lúc stream đang mở như thế nào?
Bạn thiết kế authentication cho API trả Flux dữ liệu nhiều trang mà vẫn duy trì chính sách bảo mật khi dữ liệu được phát bất đồng bộ ra sao?
Bạn giải thích oauth2ResourceServer trên ServerHttpSecurity hỗ trợ xác thực bearer token cho WebFlux API như thế nào?
Bạn phân biệt JWT token validation với opaque token introspection khi lựa chọn resource server authentication strategy ra sao?
Bạn sử dụng ReactiveJwtDecoder để xác minh chữ ký và claims của JWT mà không tự parse token rồi tin vào dữ liệu chưa kiểm chứng như thế nào?
Bạn cấu hình JWT issuer validation để token phát bởi một IdP khác không được dùng tại API của ứng dụng như thế nào?
Bạn xác định cách kiểm tra audience claim để access token dành cho API A không được dùng truy cập API B như thế nào?
Bạn thiết kế OAuth2TokenValidator cho ReactiveJwtDecoder để bổ sung quy tắc token type hoặc business audience phù hợp như thế nào?
Bạn giải thích exp, nbf và clock skew ảnh hưởng tới việc chấp nhận JWT tại resource server như thế nào?
Bạn đánh giá rủi ro chấp nhận thuật toán chữ ký không nằm trong allowlist khi JWT header khai báo alg khác với cấu hình tin cậy như thế nào?
Bạn xác định cách cấu hình JWKS URI và xử lý kid chưa có trong cache khi provider xoay vòng khóa như thế nào?
Bạn thiết kế hành vi fail closed nếu JWKS endpoint tạm thời không khả dụng mà không tự động chuyển sang xác minh chữ ký không an toàn như thế nào?
Bạn phân biệt JWT có chữ ký hợp lệ với token đã bị thu hồi hoặc đã mất quyền tại Authorization Server theo giới hạn của local validation ra sao?
Bạn lựa chọn thời hạn access token và chiến lược thu hồi quyền khi hệ thống dùng JWT tự xác minh không gọi introspection cho mỗi request như thế nào?
Bạn đánh giá khi nào dùng JwtIssuerReactiveAuthenticationManagerResolver cho nhiều issuer tin cậy thay vì chấp nhận mọi issuer từ token như thế nào?
Bạn thiết kế danh sách issuer theo tenant đã đăng ký để tránh gọi discovery endpoints từ issuer URL không đáng tin cậy ra sao?
Bạn xác định cách tách key cache và token validator giữa nhiều providers khi resource server hỗ trợ nhiều tenants như thế nào?
Bạn thiết kế custom JWT authorities converter để mapping scopes và groups có kiểm soát mà không lấy mọi claim làm ROLE_ADMIN như thế nào?
Bạn giải thích vai trò của ReactiveJwtAuthenticationConverterAdapter khi cần đưa logic chuyển JWT sang Authentication vào reactive resource server như thế nào?
Bạn phân biệt JwtAuthenticationToken với OidcUser và vì sao Resource Server không nên mặc định xem access token là ID token như thế nào?
Bạn xác định cách đổi principal name claim khi token không dùng sub trực tiếp và các hệ quả tới audit hoặc authorization như thế nào?
Bạn thiết kế xử lý JWT thiếu claim bắt buộc theo hướng từ chối thay vì gán quyền ngầm như thế nào?
Bạn phân tích lỗi issuer đúng nhưng audience sai trong một JWT bằng log an toàn mà không ghi nguyên token như thế nào?
Bạn xác định cách bảo vệ OAuth2 bearer token khỏi rò rỉ trong query string, URL logs và error pages của WebFlux như thế nào?
Bạn so sánh đọc Authorization header với dùng ServerBearerTokenAuthenticationConverter tùy chỉnh khi nhận token theo một cơ chế riêng ra sao?
Bạn đánh giá rủi ro cho phép bearer token từ nhiều vị trí không được kiểm soát khiến xuất hiện xung đột credentials hoặc token leak như thế nào?
Bạn thiết kế xử lý AuthenticationException khi token hết hạn để API trả WWW-Authenticate và thông tin lỗi an toàn như thế nào?
Bạn phân biệt HTTP 401 invalid_token với HTTP 403 insufficient_scope khi Resource Server đã xác minh một token nhưng thiếu quyền như thế nào?
Bạn xác định cách kiểm tra sự nhất quán giữa JWT roles trong token và dữ liệu tenant hiện hành trước khi cho phép thao tác nhạy cảm như thế nào?
Bạn giải thích opaque token introspection khác JWT signature validation về nguồn quyết định hiệu lực và phụ thuộc runtime vào Authorization Server ra sao?
Bạn sử dụng ReactiveOpaqueTokenIntrospector để tra trạng thái active và attributes của bearer token trong WebFlux như thế nào?
Bạn thiết kế HTTP client dùng cho introspection với timeout và giới hạn connection pool để không làm nghẽn tất cả API requests ra sao?
Bạn đánh giá cách xử lý phản hồi introspection active=false khác với lỗi mạng hoặc HTTP 503 từ introspection endpoint như thế nào?
Bạn phân biệt fallback sang accept token khi introspection server lỗi với chính sách fail closed cần có ở API nhạy cảm như thế nào?
Bạn lựa chọn mức cache introspection responses để giảm độ trễ nhưng vẫn đáp ứng yêu cầu thu hồi token trong thời gian cho phép như thế nào?
Bạn xác định cách ngăn cache key và principal mapping của opaque tokens bị chia sẻ sai giữa các tenants như thế nào?
Bạn thiết kế authority mapping từ introspection scopes hoặc claims theo chính sách riêng mà không coi mọi thuộc tính trả về đều là quyền hợp lệ như thế nào?
Bạn so sánh latency, khả năng thu hồi và chi phí vận hành giữa JWT và opaque token khi API có tải cao và IdP thường xuyên bảo trì như thế nào?
Bạn đánh giá khi nào cần bảo vệ client credentials dùng cho introspection endpoint và cách thực hiện secret rotation mà không lộ bí mật như thế nào?
Bạn giải thích oauth2Login trên SecurityWebFilterChain dùng để đăng nhập qua OAuth2 hoặc OpenID Connect theo reactive stack như thế nào?
Bạn phân biệt oauth2Login với oauth2ResourceServer khi cùng WebFlux application vừa phục vụ giao diện người dùng vừa công bố API bearer token như thế nào?
Bạn thiết kế ReactiveClientRegistrationRepository để quản lý các OpenID Providers được phép đăng nhập vào ứng dụng như thế nào?
Bạn phân biệt OIDC Authorization Code Flow với Resource Server JWT validation theo bên phát token, bên nhận token và mục đích xử lý ra sao?
Bạn xác định cách duy trì state và code_verifier trong OAuth2 login redirects mà không làm mất authorization request khi browser quay lại callback như thế nào?
Bạn giải thích PKCE và nonce bảo vệ những phần nào của Authorization Code và OIDC login trong Spring Security WebFlux như thế nào?
Bạn thiết kế validation cho OIDC issuer, audience, signature và nonce trước khi tạo reactive Authentication như thế nào?
Bạn phân biệt OIDC ID token dùng thiết lập danh tính đăng nhập với OAuth2 access token dùng gọi downstream API như thế nào?
Bạn xác định lúc nào cần gọi UserInfo endpoint và bảo đảm subject trả về khớp ID token để tránh trộn danh tính như thế nào?
Bạn thiết kế đăng nhập nhiều OpenID Providers mà mỗi registration chỉ được tin issuer và JWKS đã được quản trị phê duyệt như thế nào?
Bạn giải thích vai trò của ServerOAuth2AuthorizationRequestRepository trong việc lưu pending authorization request qua các redirect ra sao?
Bạn xác định trường hợp nhiều browser tabs khởi tạo login cùng lúc gây ghi đè state và cách kiểm thử tình huống này như thế nào?
Bạn đánh giá rủi ro callback OIDC diễn ra ở replica khác khi session store không được chia sẻ hoặc load balancer thay đổi routing ra sao?
Bạn thiết kế logout reactive với OidcClientInitiatedServerLogoutSuccessHandler nhưng không nhầm xóa WebSession với global SSO logout như thế nào?
Bạn phân biệt RP-initiated logout, front-channel logout và back-channel logout theo ranh giới bảo đảm mà ứng dụng có thể triển khai ra sao?
Bạn xác định khi nào phải xóa local authorized client state sau logout và khi nào các refresh tokens vẫn có thể còn hiệu lực tại IdP như thế nào?
Bạn giải thích ReactiveOAuth2AuthorizedClientManager hỗ trợ lấy hoặc làm mới access token để WebClient gọi API được bảo vệ ra sao?
Bạn thiết kế ServerOAuth2AuthorizedClientExchangeFilterFunction chỉ thêm bearer token cho đúng downstream host và ClientRegistration như thế nào?
Bạn đánh giá vì sao dùng default authorized client trên WebClient có thể dẫn tới gửi nhầm token người dùng sang dịch vụ khác như thế nào?
Bạn phân biệt token refresh failure với downstream HTTP 403 khi reactive WebClient phải quyết định reauthorize hay báo thiếu quyền như thế nào?
Bạn xác định cách giới hạn retry cho token endpoint để khi IdP lỗi không làm tăng tải lên toàn bộ ứng dụng như thế nào?
Bạn thiết kế background task reactive dùng Client Credentials mà không cố lấy SecurityContext từ một HTTP request đã kết thúc như thế nào?
Bạn so sánh token gắn với người dùng và token gắn với client application khi gọi API từ một pipeline xử lý nền ra sao?
Bạn phân tích rủi ro phát lại một downstream POST khi access token hết hạn mà lời gọi đầu tiên có thể đã tạo side effect như thế nào?
Bạn thiết kế chính sách multi-tenant cho authorized clients để token của tenant A không được chọn khi một request của tenant B được xử lý ra sao?
Bạn giải thích CSRF bảo vệ những request nào trong ứng dụng WebFlux có cookie-based authentication như thế nào?
Bạn phân biệt CSRF với CORS theo mô hình đe dọa và vai trò của browser khi request sử dụng cookies như thế nào?
Bạn đánh giá khi nào có thể vô hiệu hóa CSRF cho một stateless bearer-token API và vì sao không nên làm điều đó tùy tiện với web login ra sao?
Bạn sử dụng ServerCsrfTokenRepository để lưu và kiểm tra CSRF token trong reactive request lifecycle như thế nào?
Bạn thiết kế CSRF protection cho form đăng nhập hoặc thao tác POST của SPA dùng WebSession với chính sách token phù hợp như thế nào?
Bạn phân biệt CookieServerCsrfTokenRepository với cơ chế lưu CSRF token trong session theo cách token được phân phối tới client như thế nào?
Bạn xác định cách cấu hình cookie CSRF để JavaScript có thể đọc token khi thực sự cần nhưng không làm lộ session cookie như thế nào?
Bạn phân tích nguyên nhân POST từ browser trả HTTP 403 dù authentication đã thành công khi CSRF token thiếu hoặc sai ra sao?
Bạn thiết kế kiểm thử chứng minh một request dùng cookie authentication bị từ chối khi không có CSRF token hợp lệ như thế nào?
Bạn đánh giá tác động của logout và token rotation lên những form hoặc AJAX requests đang giữ CSRF token cũ ra sao?
Bạn giải thích CORS preflight hoạt động với Origin, Access-Control-Request-Method và response headers của WebFlux như thế nào?
Bạn phân biệt cấu hình CorsWebFilter với cấu hình CORS trong SecurityWebFilterChain để tránh xử lý preflight sai thứ tự như thế nào?
Bạn thiết kế allowed origins, methods, headers và credentials theo danh sách nguồn được tin cậy thay vì mở wildcard không kiểm soát như thế nào?
Bạn xác định vì sao allowCredentials=true không phù hợp với wildcard origin trong chính sách CORS dành cho browser như thế nào?
Bạn phân tích trường hợp CORS preflight bị trả HTTP 401 vì authentication filter xử lý trước CORS bằng cách nào?
Bạn thiết kế CORS policy cho nhiều subdomains được phép nhưng không dùng phép kiểm tra chuỗi suffix dễ bị giả mạo ra sao?
Bạn đánh giá vì sao một API có CORS chặt vẫn cần authentication và authorization vì non-browser clients không phụ thuộc CORS như thế nào?
Bạn phân biệt SameSite cookie protection với CORS và CSRF token khi quyết định phòng thủ nhiều lớp cho browser như thế nào?
Bạn thiết kế HTTP response headers như HSTS, frame options và content type protection phù hợp với WebFlux security policy như thế nào?
Bạn xác định cách kiểm tra Spring Security headers có thực sự xuất hiện trong response của endpoint streaming hoặc error route như thế nào?
Bạn phân biệt WebSessionServerSecurityContextRepository với NoOpServerSecurityContextRepository khi áp chính sách không lưu SecurityContext như thế nào?
Bạn đánh giá khi nào yêu cầu authentication bằng session cần chính sách timeout, session invalidation và bảo vệ session cookie như thế nào?
Bạn xác định cách hạn chế rủi ro session fixation trong reactive login và kiểm thử khả năng hỗ trợ cụ thể của Spring Security version như thế nào?
Bạn thiết kế giới hạn kích thước HTTP request và số kết nối streaming để giảm khả năng kẻ tấn công giữ tài nguyên khi đã vượt qua authentication như thế nào?
Bạn phân tích nguyên nhân một security filter chờ service blocking làm tất cả requests trên một event-loop tăng latency như thế nào?
Bạn đánh giá rủi ro dùng onErrorResume hoặc onErrorComplete trong authentication pipeline khiến lỗi trở thành xác thực thành công như thế nào?
Bạn thiết kế fallback cho IdP timeout để ứng dụng từ chối truy cập an toàn mà vẫn cung cấp lỗi vận hành có thể quan sát như thế nào?
Bạn xác định cách áp timeout cho reactive authorization lookup trong database và xử lý timeout mà không cấp quyền mặc định ra sao?
Bạn thiết kế chính sách rate limiting riêng cho login, token introspection và API nghiệp vụ mà không dựa vào mutable state trong singleton filter như thế nào?
Bạn phân biệt circuit breaker cho JWT JWKS retrieval hoặc opaque introspection với việc bỏ qua chữ ký hoặc trạng thái token khi provider lỗi như thế nào?
Bạn đánh giá rủi ro cache authorization decision hoặc GrantedAuthority quá lâu khi người dùng bị thu hồi quyền trong hệ thống ngoài ra sao?
Bạn xác định cách chặn thông tin nhạy cảm trong Authentication, Authorization header và security exceptions bị ghi vào logs hoặc traces như thế nào?
Bạn thiết kế observability cho WebFlux security ghi số lần 401, 403, lỗi JWT validation và token introspection timeout mà không tạo high-cardinality labels ra sao?
Bạn phân biệt audit event cho một lần login, một lần denied access và một lần thay đổi quyền theo dữ liệu tối thiểu cần ghi như thế nào?
Bạn xây dựng runbook phân biệt lỗi issuer/audience validation với lỗi quyền nghiệp vụ khi production xuất hiện nhiều HTTP 403 như thế nào?
Bạn xác định dấu hiệu mất Reactor Context khiến request đã đăng nhập nhưng reactive service nhìn thấy anonymous principal và cách điều tra như thế nào?
Bạn thiết kế kiểm thử WebFlux security bằng WebTestClient và SecurityMockServerConfigurers.springSecurity để áp dụng filter chain thật như thế nào?
Bạn sử dụng mockJwt trong WebTestClient để kiểm tra resource server authorization theo authorities mà không phải chạy IdP thật như thế nào?
Bạn phân biệt mockJwt với integration test dùng JWT có chữ ký thật để chứng minh ReactiveJwtDecoder thực hiện validation như thế nào?
Bạn sử dụng mockOAuth2Login và mockOidcLogin để kiểm tra behavior của controller hoặc method security mà không giả lập toàn bộ authorization code flow như thế nào?
Bạn thiết kế test OAuth2 login end-to-end với mock Authorization Server để kiểm tra state, PKCE và OIDC nonce như thế nào?
Bạn kiểm thử bearer token expired, sai issuer, sai audience và không khớp signing key nhằm xác minh resource server từ chối đúng như thế nào?
Bạn thiết kế test opaque token introspection trả active=false hoặc HTTP 503 để phân biệt invalid token với lỗi upstream ra sao?
Bạn sử dụng @WithMockUser trong reactive method-security test và xác định khi nào nó không thay thế được kiểm thử SecurityWebFilterChain như thế nào?
Bạn thiết kế WebTestClient test xác nhận unauthenticated request trả 401 và authenticated request thiếu authority trả 403 như thế nào?
Bạn kiểm thử thứ tự SecurityWebFilterChains để endpoint công khai không bị vô tình yêu cầu token còn endpoint riêng tư không bị bỏ bảo vệ như thế nào?
Bạn kiểm tra matcher path variables và encoded URL trong WebTestClient để phát hiện bypass phân quyền giữa các routes như thế nào?
Bạn thiết kế test parallel WebFlux requests dưới hai principals để chứng minh ReactiveSecurityContextHolder không bị lẫn giữa subscriptions ra sao?
Bạn sử dụng StepVerifier để kiểm thử reactive authorization pipeline với contextWrite mà không dựa vào Thread.sleep như thế nào?
Bạn kiểm tra method security khi service trả Mono.empty hoặc Flux.error để bảo đảm không có đường cho phép truy cập ngoài ý muốn như thế nào?
Bạn thiết kế test CSRF cho WebSession POST, stateless bearer POST và request preflight để tránh kết luận sai rằng tất cả đều cần cùng chính sách ra sao?
Bạn kiểm thử CORS với Origin không được phép và credentials để xác nhận policy từ chối trước khi xử lý dữ liệu nhạy cảm như thế nào?
Bạn xây dựng test WebClient được cấp OAuth2AuthorizedClient của tenant A nhưng gửi request tới service dành cho tenant B nhằm phát hiện token leak như thế nào?
Bạn kiểm thử token refresh lỗi invalid_grant mà không lặp vô hạn hoặc tiếp tục dùng token đã thu hồi như thế nào?
Bạn lựa chọn kiểm thử bằng WebTestClient bindToApplicationContext hay bindToServer theo mục tiêu kiểm tra filter chain và HTTP stack production như thế nào?
Bạn xác định những thao tác WebFlux security cần test bằng server thật để phát hiện lỗi proxy headers, session cookies hoặc cross-origin redirects ra sao?
Bạn đề xuất kiến trúc bảo mật cho Spring WebFlux kết hợp SecurityWebFilterChain, reactive context, method authorization, JWT/opaque OAuth2, OIDC login, CSRF/CORS và test automation như thế nào?

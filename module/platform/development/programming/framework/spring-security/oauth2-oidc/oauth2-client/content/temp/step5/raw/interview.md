Bạn giải thích vai trò của OAuth 2.0 Client trong Spring Security khi ứng dụng cần đăng nhập người dùng hoặc gọi một API được bảo vệ như thế nào?
Bạn phân biệt OAuth 2.0 Client với Authorization Server và Resource Server theo trách nhiệm trong cùng một hệ thống như thế nào?
Bạn so sánh OAuth 2.0 authorization delegation với OpenID Connect authentication khi quyết định mục tiêu của một login flow ra sao?
Bạn mô tả vai trò của Resource Owner, Client, Authorization Server và Resource Server trong một authorization code flow như thế nào?
Bạn phân biệt public client và confidential client theo khả năng bảo vệ credentials và yêu cầu xác thực tại token endpoint như thế nào?
Bạn xác định khi nào dùng Authorization Code với PKCE thay vì Client Credentials trong ứng dụng cần quyền của người dùng như thế nào?
Bạn giải thích vì sao Client Credentials không đại diện cho một người dùng đang đăng nhập mà thường đại diện cho chính ứng dụng như thế nào?
Bạn đánh giá vì sao Resource Owner Password Credentials không phù hợp cho thiết kế OAuth2 Client mới dù một số hệ thống cũ vẫn đề cập đến nó như thế nào?
Bạn phân biệt access token, refresh token và OIDC ID token theo đối tượng sử dụng và mức độ tin cậy như thế nào?
Bạn xác định khi nào ứng dụng chỉ cần oauth2Client mà không cần oauth2Login trong SecurityFilterChain như thế nào?
Bạn phân biệt chức năng oauth2Login và oauth2Client khi cùng ứng dụng vừa đăng nhập qua IdP vừa gọi downstream API như thế nào?
Bạn thiết kế ranh giới giữa local session của ứng dụng web và OAuth2AuthorizedClient dùng để gọi API thay mặt người dùng như thế nào?
Bạn giải thích vì sao ứng dụng nhận OAuth2 login thành công không mặc nhiên có quyền truy cập mọi Resource Server như thế nào?
Bạn lựa chọn cách mô hình hóa scopes cần thiết cho từng downstream API mà không yêu cầu quyền quá rộng ngay từ lần đăng nhập đầu ra sao?
Bạn phân biệt delegated access token với application access token khi cùng một WebClient có thể gọi nhiều loại API như thế nào?
Bạn đánh giá tác động của token expiration tới trải nghiệm đăng nhập và khả năng gọi API sau nhiều phút không hoạt động như thế nào?
Bạn thiết kế chính sách giảm thu thập claims và không lưu dữ liệu OAuth2/OIDC ngoài mục đích nghiệp vụ như thế nào?
Bạn xác định những điều kiện nào khiến một OAuth2 Client cần HTTPS, session integrity và bảo vệ redirect URLs như thế nào?
Bạn so sánh triển khai OAuth2 Client trên servlet stack và reactive stack theo API, context propagation và storage như thế nào?
Bạn giải thích các thành phần ClientRegistration mô tả provider endpoints, client credentials, scopes và authorization grant type ra sao?
Bạn phân biệt registrationId của Spring Security với client_id được đăng ký ở Authorization Server như thế nào?
Bạn sử dụng ClientRegistrationRepository để cung cấp thông tin cấu hình cho nhiều Authorization Servers trong ứng dụng như thế nào?
Bạn lựa chọn InMemoryClientRegistrationRepository hay kho đăng ký động khi ứng dụng chỉ có vài provider hoặc nhiều tenant như thế nào?
Bạn thiết kế cấu hình client-id, client-secret, scope và redirect-uri theo từng môi trường mà không ghi secrets vào repository như thế nào?
Bạn phân biệt authorizationUri, tokenUri, userInfoUri và jwkSetUri theo vai trò của từng endpoint như thế nào?
Bạn đánh giá khi nào có thể sử dụng issuer-uri hoặc provider discovery thay vì khai báo thủ công mọi endpoint OAuth2/OIDC như thế nào?
Bạn xác định vì sao metadata discovery phải đến từ issuer tin cậy và không nên tự động theo URL tùy ý từ request của người dùng ra sao?
Bạn thiết kế kiểm tra redirect-uri template khi ứng dụng chạy sau reverse proxy với public scheme HTTPS như thế nào?
Bạn phân biệt clientAuthenticationMethod client_secret_basic với client_secret_post và lựa chọn theo khả năng provider hỗ trợ như thế nào?
Bạn quyết định khi nào cần private_key_jwt hoặc phương thức xác thực client khác và kiểm tra phạm vi Spring Security version hỗ trợ ra sao?
Bạn giải thích yêu cầu quản lý client secret khác gì với quản lý khóa dùng ký ID token của OpenID Provider như thế nào?
Bạn xác định phương án xoay vòng client secret mà không làm gián đoạn đồng loạt các phiên authorized clients hiện có như thế nào?
Bạn đánh giá nguy cơ cấu hình sai một ClientRegistration khiến access token bị gửi tới provider không dự kiến như thế nào?
Bạn thiết kế cơ chế chọn ClientRegistration dựa trên yêu cầu nghiệp vụ thay vì cho client tùy ý nhập registrationId chưa được kiểm duyệt như thế nào?
Bạn so sánh registration cho đăng nhập OIDC với registration cho service-to-service Client Credentials theo scope và principal semantics như thế nào?
Bạn xác định cách cập nhật metadata JWKS hoặc token endpoint khi provider thực hiện key rotation hay migration như thế nào?
Bạn kiểm tra các lỗi startup hoặc runtime khi ClientRegistration thiếu authorizationUri hay redirectUri cần thiết cho một grant type như thế nào?
Bạn phân biệt thiết lập provider metadata bằng property configuration với tùy biến ClientRegistration bằng Java code theo khả năng kiểm thử ra sao?
Bạn giải thích OAuth2AuthorizationRequestRedirectFilter bắt đầu authorization flow trên servlet stack như thế nào?
Bạn xác định vai trò của endpoint /oauth2/authorization/{registrationId} trong việc khởi tạo một browser-based login như thế nào?
Bạn mô tả cách authorization request mang client_id, redirect_uri, response_type, scope và state tới Authorization Server như thế nào?
Bạn giải thích tại sao state cần được ràng buộc với yêu cầu đăng nhập ban đầu để chống login CSRF và response substitution như thế nào?
Bạn thiết kế lưu trữ OAuth2AuthorizationRequest an toàn khi người dùng mở nhiều tab đăng nhập cùng lúc như thế nào?
Bạn phân biệt HttpSessionOAuth2AuthorizationRequestRepository với custom authorization request repository trong tình huống không có sticky sessions ra sao?
Bạn đánh giá rủi ro sử dụng cookie lưu authorization request nếu không bảo vệ tính toàn vẹn, độ nhạy cảm và thời gian hết hạn ra sao?
Bạn xác định cách xử lý state không khớp hoặc đã hết hạn mà không bắt đầu login loop không kiểm soát như thế nào?
Bạn giải thích PKCE code_challenge và code_verifier bảo vệ Authorization Code khỏi bị đổi lấy token bởi một bên khác như thế nào?
Bạn phân biệt S256 với plain code challenge method và xác định chính sách nên dùng khi provider hỗ trợ PKCE như thế nào?
Bạn cấu hình OAuth2AuthorizationRequestCustomizers.withPkce hoặc resolver tùy biến theo phiên bản Spring Security để kích hoạt PKCE như thế nào?
Bạn thiết kế cách giữ code_verifier gắn với đúng browser authorization request đến lúc thực hiện token exchange như thế nào?
Bạn đánh giá vì sao client secret không thay thế hoàn toàn giá trị bảo vệ của PKCE trong Authorization Code Flow hiện đại như thế nào?
Bạn xác định điều gì xảy ra khi provider trả authorization code nhưng token request thiếu hoặc sai code_verifier như thế nào?
Bạn phân biệt authorization code một lần sử dụng với access token được phát sau token exchange về vòng đời và nguy cơ phát lại ra sao?
Bạn mô tả cách OAuth2LoginAuthenticationFilter xử lý callback /login/oauth2/code/{registrationId} trong servlet login flow như thế nào?
Bạn thiết kế callback routing để chống nhầm registrationId khi ứng dụng hỗ trợ nhiều OAuth2 providers ra sao?
Bạn phân biệt redirect_uri được dùng trong authorization request và redirect_uri gửi tới token endpoint theo yêu cầu kiểm tra của provider như thế nào?
Bạn xác định cách tránh open redirect nếu tham số yêu cầu quay lại trang trước được lưu trong saved request hoặc custom success handler ra sao?
Bạn giải thích token endpoint cần xác minh những thông tin nào trước khi phát tokens cho Authorization Code grant như thế nào?
Bạn đánh giá ảnh hưởng của request timeout khi đổi authorization code lấy token và cách xử lý kết quả không chắc chắn ra sao?
Bạn lựa chọn cách hiện thị lỗi access_denied do user từ chối consent khác với lỗi invalid_client hoặc invalid_grant như thế nào?
Bạn thiết kế AuthenticationSuccessHandler và AuthenticationFailureHandler cho OAuth2 login để phân biệt đăng nhập thành công, thiếu quyền và lỗi callback ra sao?
Bạn xác định cách chẩn đoán vòng lặp login do cookie SameSite, session loss hoặc cấu hình proxy khiến state không được tìm thấy ra sao?
Bạn phân biệt implicit flow với Authorization Code + PKCE về việc access token có cần đi qua front-channel hay không như thế nào?
Bạn thiết kế quy trình consent lại khi ứng dụng cần thêm scope mới mà không mặc định mọi người dùng đã chấp thuận quyền đó như thế nào?
Bạn đánh giá khi nào cần incremental authorization và cách hiển thị scope bổ sung cho người dùng một cách minh bạch như thế nào?
Bạn thiết kế kiểm tra authorization code không xuất hiện trong HTTP logs hoặc error pages khi xử lý callback như thế nào?
Bạn mô tả vai trò của SecurityFilterChain khi kết hợp oauth2Login với authorization rules cho trang người dùng như thế nào?
Bạn phân biệt principal của oauth2Login với token mà OAuth2AuthorizedClient lưu giữ để gọi downstream API như thế nào?
Bạn giải thích scope openid làm Authorization Code Flow trở thành một yêu cầu OIDC có nhận ID token như thế nào?
Bạn mô tả các bước OIDC Relying Party kiểm tra ID token sau khi nhận tokens từ OpenID Provider như thế nào?
Bạn phân biệt OidcUser với OAuth2User theo nguồn claims, các hợp đồng danh tính và API truy cập thông tin như thế nào?
Bạn xác định khi nào chọn OidcUserService thay vì OAuth2UserService cho các tùy biến identity mapping như thế nào?
Bạn giải thích vì sao giải mã JWT payload chưa đủ để tin vào ID token nếu chưa xác minh chữ ký và các claims bắt buộc như thế nào?
Bạn kiểm tra iss claim để bảo đảm ID token phát từ đúng OpenID Provider mà ClientRegistration mong đợi như thế nào?
Bạn phân biệt aud claim và azp claim khi ID token dành cho nhiều audiences và cần xác minh client hợp lệ như thế nào?
Bạn thiết kế kiểm tra exp, iat và giới hạn clock skew của ID token để không chấp nhận token cũ quá lâu như thế nào?
Bạn xác định khi nào auth_time hoặc max_age cần được sử dụng để yêu cầu đăng nhập đủ mới cho một thao tác nhạy cảm ra sao?
Bạn giải thích OIDC nonce ràng buộc ID token với authorization request ban đầu và phân biệt nonce với OAuth state như thế nào?
Bạn thiết kế quy trình xác minh nonce khi browser khởi tạo song song nhiều OIDC logins từ các tab khác nhau như thế nào?
Bạn phân biệt xác minh chữ ký ID token qua JWKS với xác minh access token tại Resource Server như thế nào?
Bạn đánh giá rủi ro chấp nhận thuật toán ký do JWT header tự khai báo mà không kiểm tra chính sách thuật toán của provider như thế nào?
Bạn xác định cách chọn signing key theo kid và xử lý lúc JWKS của provider được cập nhật khi xoay vòng khóa như thế nào?
Bạn thiết kế retry có giới hạn khi JWKS endpoint chưa công bố khóa mới mà không tự động tin bất kỳ endpoint hoặc khóa khác như thế nào?
Bạn phân biệt encrypted ID token với signed ID token và các bước giải mã/xác minh cần được hỗ trợ rõ ràng như thế nào?
Bạn xác định khi nào at_hash hoặc c_hash cần được kiểm tra theo OIDC flow thực tế thay vì mặc định áp dụng mọi trường hợp như thế nào?
Bạn giải thích vì sao ID token hợp lệ không chứng minh access token cũng hợp lệ cho bất kỳ downstream API nào như thế nào?
Bạn xác định cách bảo vệ subject identifier ổn định khi người dùng đổi email hoặc profile information tại OpenID Provider như thế nào?
Bạn phân biệt sub claim và email claim khi ánh xạ một user vào tài khoản nội bộ có thể thay đổi email ra sao?
Bạn thiết kế account linking dựa trên issuer và sub để hai OpenID Providers không vô tình cấp cùng một tài khoản nội bộ như thế nào?
Bạn đánh giá rủi ro tự gán quyền cao khi email_verified=false hoặc group claim chưa được kiểm tra provenance như thế nào?
Bạn xác định trường hợp nào dùng UserInfo endpoint để bổ sung claims mà không coi dữ liệu profile là authorization decision tự động như thế nào?
Bạn kiểm tra UserInfo sub có khớp ID token sub để tránh trộn dữ liệu của hai danh tính như thế nào?
Bạn phân biệt claims từ ID token và claims lấy sau từ UserInfo khi mapping OidcUser cho ứng dụng như thế nào?
Bạn thiết kế cache UserInfo response có thời hạn hợp lý mà không giữ thông tin cá nhân đã bị thay đổi hoặc thu hồi quá lâu ra sao?
Bạn sử dụng GrantedAuthoritiesMapper để chuyển OAuth2/OIDC authorities sang quyền ứng dụng dựa trên chính sách allowlist như thế nào?
Bạn phân biệt granted scopes với application roles và xác định tại sao scope chưa đủ kiểm tra quyền truy cập business resource như thế nào?
Bạn thiết kế mapping authorities theo tenant membership thay vì cho rằng nhóm ADMIN của một IdP áp dụng toàn hệ thống như thế nào?
Bạn kiểm thử trường hợp provider thay đổi kiểu claim groups từ chuỗi sang mảng mà ứng dụng vẫn phải fail closed như thế nào?
Bạn xác định nơi kiểm tra tài khoản bị vô hiệu hóa trong ứng dụng dù OIDC login đã xác thực danh tính thành công như thế nào?
Bạn phân biệt OAuth2AuthorizedClient với ClientRegistration theo sự khác nhau giữa metadata provider và tokens được ủy quyền như thế nào?
Bạn giải thích OAuth2AuthorizedClientRepository lưu authorized clients theo HTTP request/principal trên servlet stack như thế nào?
Bạn phân biệt OAuth2AuthorizedClientService với OAuth2AuthorizedClientRepository theo phạm vi lưu trữ và truy xuất như thế nào?
Bạn lựa chọn HttpSessionOAuth2AuthorizedClientRepository hay một service backed by database khi ứng dụng cần nhiều replica và khôi phục session như thế nào?
Bạn thiết kế chính sách mã hóa và kiểm soát truy cập khi access token hoặc refresh token được lưu trong database như thế nào?
Bạn đánh giá rủi ro token của user A bị nạp vào request của user B do principal name hoặc storage key không phân tách đúng như thế nào?
Bạn giải thích OAuth2AuthorizedClientManager quyết định khi nào cấp hoặc tái cấp authorized client theo authorization grant như thế nào?
Bạn phân biệt DefaultOAuth2AuthorizedClientManager với AuthorizedClientServiceOAuth2AuthorizedClientManager theo sự phụ thuộc vào servlet request context ra sao?
Bạn xác định trường hợp nào cần một authorized client manager phù hợp để gọi API trong scheduled job không có HTTP request như thế nào?
Bạn cấu hình OAuth2AuthorizedClientProvider hỗ trợ authorization_code, refresh_token hoặc client_credentials theo use case như thế nào?
Bạn đánh giá vì sao một authorized client có thể hết hạn access token nhưng chưa chắc có refresh token để tự làm mới như thế nào?
Bạn giải thích Refresh Token Grant khác với việc redirect browser đăng nhập lại theo sự hiện diện của người dùng như thế nào?
Bạn thiết kế kiểm tra expiresAt và clock skew trước khi dùng access token để tránh token gần hết hạn gây thất bại hàng loạt như thế nào?
Bạn xác định phản ứng an toàn khi provider trả invalid_grant cho refresh token đã bị thu hồi như thế nào?
Bạn thiết kế OAuth2AuthorizationFailureHandler để loại bỏ authorized client không còn hiệu lực theo đúng principal và registration như thế nào?
Bạn phân biệt failure ở token refresh endpoint với HTTP 403 trả về từ resource API khi quyết định có cần reauthorize như thế nào?
Bạn đánh giá khi nào không nên retry refresh token sau invalid_grant vì có thể gây vòng lặp vô hạn như thế nào?
Bạn thiết kế logic đồng bộ nhiều request của cùng user khi access token hết hạn đồng thời để hạn chế refresh stampede ra sao?
Bạn xác định rủi ro refresh token rotation khi hai requests cùng dùng token cũ và một yêu cầu khiến token còn lại bị vô hiệu hóa ra sao?
Bạn quyết định nên lưu lại rotated refresh token như thế nào để không ghi đè token mới bằng kết quả từ request chậm hơn ra sao?
Bạn kiểm tra trường hợp OAuth2AuthorizedClientManager không trả về authorized client và lựa chọn cách phản hồi phù hợp với HTTP request hoặc background job như thế nào?
Bạn giải thích authorized client context attributes hỗ trợ truyền thông tin bổ sung cho authorization provider trong các grant được hỗ trợ như thế nào?
Bạn phân biệt client_credentials token gắn với một application identity với authorization_code token gắn với một người dùng cụ thể như thế nào?
Bạn thiết kế principal identifier ổn định khi lưu Client Credentials authorized client để các background jobs không tạo quá nhiều token ngoài ý muốn như thế nào?
Bạn xác định cách cô lập authorized clients giữa các tenants cùng dùng một registrationId hoặc shared identity provider như thế nào?
Bạn phân tích tác động của session invalidation đến authorized clients lưu trong HTTP session so với authorized clients lưu bên ngoài như thế nào?
Bạn quyết định khi nào token cần được xóa khi người dùng logout dù access token còn hiệu lực tại Authorization Server như thế nào?
Bạn giải thích tại sao local logout không mặc nhiên thu hồi access token hoặc refresh token đang được Authorization Server cấp như thế nào?
Bạn thiết kế token lifecycle monitoring chỉ dùng metadata như expiry và error class thay vì ghi token value vào log như thế nào?
Bạn đánh giá rủi ro token bị giữ trong heap dump hoặc trace attributes khi instrumentation ghi nhận nội dung Authorization header ra sao?
Bạn xác định chính sách thời hạn và cleanup authorized client entries khi người dùng lâu không hoạt động trong nhiều tháng như thế nào?
Bạn giải thích WebClient có thể sử dụng OAuth2AuthorizedClientManager để tự chèn Bearer access token vào request downstream như thế nào?
Bạn phân biệt ServletOAuth2AuthorizedClientExchangeFilterFunction với ServerOAuth2AuthorizedClientExchangeFilterFunction theo môi trường MVC và WebFlux như thế nào?
Bạn thiết kế WebClient cấu hình servlet OAuth2 client support để gọi một API theo registrationId được chọn tường minh như thế nào?
Bạn đánh giá vì sao setDefaultOAuth2AuthorizedClient có thể làm access token của user bị gửi sang một downstream không đúng đối tượng như thế nào?
Bạn lựa chọn khi nào setDefaultClientRegistrationId phù hợp cho WebClient chỉ gọi một trusted service và khi nào cần chỉ định trên từng request ra sao?
Bạn xác định cách chỉ định OAuth2AuthorizedClient cụ thể qua attributes khi một request downstream phải thay mặt một user nhất định như thế nào?
Bạn phân biệt việc WebClient gửi token sẵn có với việc tự động lấy token theo Client Credentials Grant như thế nào?
Bạn thiết kế nhiều WebClient instances có token policies khác nhau để tránh gửi token của một API tới host không được phép như thế nào?
Bạn đánh giá rủi ro WebClient follow redirect sang host lạ kèm Bearer token và cách kiểm soát destination như thế nào?
Bạn xác định cách giới hạn scopes cho WebClient gọi service báo cáo khác với service thanh toán để áp nguyên tắc least privilege như thế nào?
Bạn xử lý downstream HTTP 401 khi access token bị thu hồi trước expiresAt mà không tự động retry vô hạn như thế nào?
Bạn phân biệt lỗi OAuth2 authorization tại client manager với HTTP 401 do downstream Resource Server trả về như thế nào?
Bạn thiết kế retry network tạm thời cho API idempotent mà không gửi lại thao tác thanh toán có side effect ngoài ý muốn như thế nào?
Bạn đánh giá vì sao refresh token thành công không bảo đảm downstream API chấp nhận quyền mới hoặc audience của access token ra sao?
Bạn xác định khi nào cần chọn OAuth2ClientHttpRequestInterceptor cho RestClient theo khả năng được hỗ trợ của Spring Security version như thế nào?
Bạn so sánh RestClient dùng OAuth2 client interceptor với WebClient filter theo mô hình blocking, reactive và xử lý lỗi như thế nào?
Bạn thiết kế một HTTP Service Client dựa trên RestClient hoặc WebClient với OAuth2 credentials được kiểm soát ở adapter như thế nào?
Bạn phân biệt sử dụng OAuth2AuthorizedClientManager cho scheduled tasks với dựa vào SecurityContextHolder có thể rỗng ở background thread như thế nào?
Bạn đánh giá tác động của TaskExecutor đổi thread tới việc tra principal và authorized client khi WebClient được gọi bất đồng bộ như thế nào?
Bạn thiết kế client gọi downstream với token theo user mà không sao chép token vào thread-local được tái sử dụng giữa nhiều requests như thế nào?
Bạn giải thích các thành phần ReactiveClientRegistrationRepository và ServerOAuth2AuthorizedClientRepository trên WebFlux khác servlet contracts như thế nào?
Bạn phân biệt ReactiveOAuth2AuthorizedClientService với ServerOAuth2AuthorizedClientRepository khi chọn nơi lưu token cho reactive server ra sao?
Bạn sử dụng ReactiveOAuth2AuthorizedClientManager để cấp phát authorized clients trong reactive pipeline như thế nào?
Bạn phân biệt DefaultReactiveOAuth2AuthorizedClientManager và AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager theo ngữ cảnh reactive web request hoặc background process như thế nào?
Bạn thiết kế cấu hình reactive OAuth2 authorized client provider cho Client Credentials và Refresh Token theo từng loại downstream request như thế nào?
Bạn xác định khi nào bật oauth2Login trong SecurityWebFilterChain và cách khai báo authorization rules cho WebFlux như thế nào?
Bạn so sánh reactive oauth2Login với servlet oauth2Login theo nơi lưu authorization request, state và SecurityContext như thế nào?
Bạn phân biệt ServerOAuth2AuthorizationRequestRepository với servlet OAuth2AuthorizationRequestRepository khi bảo vệ state trong quá trình redirect như thế nào?
Bạn giải thích Reactor Context lưu security information ra sao và vì sao ThreadLocal không tự động theo toàn bộ reactive pipeline như thế nào?
Bạn xác định rủi ro gọi block trong WebFlux login callback hoặc token refresh khi event-loop cần giữ tính nonblocking như thế nào?
Bạn thiết kế WebClient reactive truyền OAuth2AuthorizedClient theo Reactor Context hoặc request attributes mà không dựa vào global mutable state như thế nào?
Bạn phân biệt mutateWith mockOidcLogin của WebTestClient test support với việc thực hiện authorization code flow thật như thế nào?
Bạn kiểm tra khi một reactive WebClient call được subscribe sau HTTP response thì authorized client và principal context còn tồn tại hay không như thế nào?
Bạn thiết kế cách truyền user identity an toàn sang asynchronous publisher khi luồng xử lý kéo dài quá vòng đời ServerWebExchange như thế nào?
Bạn xác định cách tránh giữ ServerWebExchange hoặc SecurityContext trong singleton bean để dùng lại giữa các tenants như thế nào?
Bạn đánh giá tác động của token refresh khi nhiều reactive subscribers cùng khởi tạo authorization cho một principal như thế nào?
Bạn xử lý lỗi timeout của token endpoint trong reactive pipeline mà không nuốt lỗi hoặc trả response thành công giả như thế nào?
Bạn thiết kế reactive OAuth2 client gọi nhiều downstream services song song nhưng giữ đúng registration và token audience cho từng nhánh như thế nào?
Bạn phân biệt cơ chế Spring Security testing của MockMvc và WebTestClient theo cách bổ sung OAuth2 user hoặc authorized client ra sao?
Bạn đánh giá khi nào blocking REST client chỉ thích hợp trong servlet code và khi nào cần nonblocking WebClient ở reactive code như thế nào?
Bạn giải thích OpenID Connect RP-initiated logout khác với chỉ xóa local authentication và HTTP session trong ứng dụng như thế nào?
Bạn sử dụng OidcClientInitiatedLogoutSuccessHandler để điều hướng servlet user tới end_session_endpoint của OpenID Provider như thế nào?
Bạn xác định cách chọn post_logout_redirect_uri hợp lệ với provider và bảo vệ khỏi open redirect như thế nào?
Bạn phân biệt id_token_hint với access token khi chuẩn bị tham số cho một RP-initiated logout request như thế nào?
Bạn thiết kế chính sách logout khi provider không công bố end_session_endpoint trong OIDC discovery metadata như thế nào?
Bạn giải thích OidcClientInitiatedServerLogoutSuccessHandler phục vụ reactive OIDC logout và những khác biệt với servlet handler như thế nào?
Bạn đánh giá giới hạn của RP-initiated logout trong việc kết thúc sessions của các ứng dụng SSO khác như thế nào?
Bạn phân biệt front-channel logout và back-channel logout với RP-initiated logout theo cách ứng dụng được thông báo kết thúc phiên ra sao?
Bạn xác định cách xử lý OIDC logout callback khi local session đã hết hạn trước khi OpenID Provider hoàn thành đăng xuất như thế nào?
Bạn thiết kế xóa local OAuth2AuthorizedClient state sau logout mà không khẳng định mọi access token đã bị thu hồi tại provider như thế nào?
Bạn so sánh revoke access token và revoke refresh token tại authorization server theo mức độ hạn chế quyền tiếp tục gọi API như thế nào?
Bạn xác định khi nào OIDC reauthentication hoặc max_age là cần thiết dù browser vẫn có SSO session tại IdP như thế nào?
Bạn thiết kế hành vi đăng nhập lại sau logout khi provider vẫn còn session SSO mà ứng dụng chỉ muốn kết thúc local session như thế nào?
Bạn giải thích vai trò của spring-security-test trong việc kiểm thử OAuth2 login và authorized client mà không gọi IdP thật như thế nào?
Bạn sử dụng MockMvc request post-processors oauth2Login và oidcLogin để tạo authenticated principal trong controller test như thế nào?
Bạn phân biệt mockOAuth2User hoặc OidcUser trong unit test với kiểm thử việc xác minh ID token bằng test provider thật ra sao?
Bạn thiết kế MockMvc test kiểm tra @PreAuthorize khi principal đến từ OIDC và authorities đã được mapping như thế nào?
Bạn sử dụng oauth2Client test support để cấu hình authorized client cho HTTP request trong bài kiểm thử Spring MVC như thế nào?
Bạn xác định cách kiểm thử một client_credentials manager trong service không có HTTP session bằng fake token endpoint như thế nào?
Bạn thiết kế integration test Authorization Code + PKCE với test Authorization Server để kiểm chứng state, code_verifier và token exchange như thế nào?
Bạn kiểm thử đăng nhập bị từ chối khi callback trả state khác với authorization request ban đầu như thế nào?
Bạn xây dựng test khi provider trả authorization code hết hạn hoặc sai redirect_uri và xác minh ứng dụng không tạo session xác thực như thế nào?
Bạn kiểm thử ID token có signature hợp lệ nhưng issuer hoặc audience sai để xác minh ranh giới tin cậy của OIDC Relying Party như thế nào?
Bạn thiết kế test JWKS key rotation khi provider dùng kid mới và đảm bảo client không chấp nhận khóa không được đăng ký tin cậy như thế nào?
Bạn kiểm thử nonce không khớp hoặc thiếu trong ID token khi login request thực sự gửi nonce như thế nào?
Bạn thiết kế test UserInfo trả subject khác ID token và xác minh ứng dụng từ chối trộn profile của hai người dùng như thế nào?
Bạn sử dụng WebTestClient với mockOidcLogin hoặc mockOAuth2Login để kiểm tra SecurityWebFilterChain của WebFlux như thế nào?
Bạn thiết kế WebTestClient test reactive authorized client khi OAuth2 token phải được chèn vào downstream WebClient request như thế nào?
Bạn phân biệt mock token response với mock HTTP resource server khi test WebClient tự thêm Authorization header và xử lý HTTP 401 như thế nào?
Bạn kiểm thử refresh token rotation với hai requests cạnh tranh để phát hiện việc ghi đè token mới bằng credential cũ như thế nào?
Bạn thiết kế test invalid_grant buộc loại bỏ authorized client và yêu cầu reauthorization thay vì tiếp tục gọi API với token lỗi ra sao?
Bạn kiểm thử lựa chọn sai ClientRegistration dẫn đến gửi access token nhầm API và ngăn hành vi đó bằng allowlist host như thế nào?
Bạn thiết kế integration test hai tenants có cùng registrationId nhưng khác issuer để phát hiện rò rỉ authorized client state như thế nào?
Bạn kiểm thử logout Servlet và Reactive với provider có end_session_endpoint và provider không hỗ trợ endpoint này như thế nào?
Bạn xác định cách dùng deterministic clock trong test token expiresAt để tránh test flaky do Thread.sleep như thế nào?
Bạn đánh giá khi nào cần kiểm thử trên browser thật để phát hiện lỗi SameSite cookie, callback redirects và consent screens mà mock HTTP tests bỏ sót ra sao?
Bạn thiết kế metrics về số lần authorization success, token refresh error, invalid_grant và latency của downstream OAuth2 client calls như thế nào?
Bạn xác định cách log registrationId, issuer và correlation ID để điều tra lỗi mà không ghi access token, refresh token hoặc ID token như thế nào?
Bạn phân tích sự cố OAuth2 login thành công nhưng WebClient downstream liên tục trả 401 bằng các bước kiểm tra scope, audience và token expiry như thế nào?
Bạn thiết kế runbook khi provider JWKS endpoint không khả dụng hoặc token endpoint trả 503 mà không nới lỏng xác thực ra sao?
Bạn đánh giá khi nào circuit breaker hoặc retry budget cho token refresh cần khác với retry dành cho API nghiệp vụ như thế nào?
Bạn đề xuất kiến trúc Spring Security OAuth2/OIDC Client cho ứng dụng hỗ trợ Servlet và Reactive, PKCE, authorized client storage, token refresh, OIDC logout và integration testing như thế nào?

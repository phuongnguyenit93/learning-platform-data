Bạn giải thích OAuth 2.0 Resource Server có trách nhiệm nào trong việc bảo vệ API Spring Security?
Bạn phân biệt Resource Server, Authorization Server, OAuth2 Client và Resource Owner theo luồng truy cập API như thế nào?
Bạn sẽ mô tả đường đi của một HTTP request mang bearer access token qua Spring Security tới controller ra sao?
Bạn phân biệt access token dùng tại Resource Server với ID token của OpenID Connect theo mục đích và audience như thế nào?
Bạn sẽ xác định khi nào Spring Boot ứng dụng cần oauth2-resource-server thay vì oauth2-login theo đặc điểm client như thế nào?
Bạn giải thích bearer token có ý nghĩa gì về khả năng sử dụng token khi bất kỳ bên nào lấy được nó như thế nào?
Bạn sẽ lựa chọn JWT hay opaque token cho một API theo yêu cầu latency, bảo mật và thu hồi quyền nào?
Bạn phân biệt authentication của token với authorization của một thao tác truy cập business resource như thế nào?
Bạn mô tả cách OAuth2 Resource Server chuyển token đã được xác minh thành Authentication trong SecurityContext ra sao?
Bạn sẽ xác định principal của bearer request khi claim sub không trùng với username trong hệ thống nội bộ như thế nào?
Bạn phân tích vì sao resource server không được tin một access token chỉ vì nó có định dạng ba phần ngăn bởi dấu chấm ra sao?
Bạn sẽ xử lý request không mang Authorization header khác với request mang bearer token sai như thế nào?
Bạn phân biệt HTTP status 401 và 403 theo trạng thái xác thực token và quyền thực hiện thao tác ra sao?
Bạn sẽ thiết kế chính sách deny by default cho các API không được khai báo công khai như thế nào?
Bạn phân tích rủi ro cho phép mọi token có chữ ký hợp lệ truy cập cùng một API khi chúng được phát hành cho audience khác ra sao?
Bạn sẽ xác định trust boundary giữa resource server và external identity provider theo những kiểm tra nào?
Bạn phân biệt access token lấy qua authorization code flow với client credentials flow về ngữ cảnh chủ thể ra sao?
Bạn sẽ biểu diễn machine principal từ client credentials token sao cho không bị nhầm với end-user principal như thế nào?
Bạn phân tích vì sao client_id hoặc azp claim không thay thế sub hay authorization policy trong mọi token profile ra sao?
Bạn sẽ thiết kế API có cả public và protected routes mà không bỏ qua Spring Security filter chain cho các public routes như thế nào?
Bạn giải thích vì sao resource server vẫn cần HTTPS dù token đã được ký số như thế nào?
Bạn sẽ giới hạn nơi client được phép gửi bearer token để không làm lộ token qua query string hoặc URL logs ra sao?
Bạn phân biệt proof-of-possession token với bearer token theo nguy cơ đánh cắp và phát lại như thế nào?
Bạn sẽ đánh giá yêu cầu DPoP hoặc mTLS sender-constrained tokens nếu Authorization Server và Resource Server đều hỗ trợ ra sao?
Bạn phân tích vì sao JWT tự chứa claims không đồng nghĩa các claims đều đủ tin cậy để quyết định quyền trên từng bản ghi như thế nào?
Bạn sẽ phân biệt scope được cấp cho client với quyền sở hữu dữ liệu cụ thể của người dùng ra sao?
Bạn mô tả cách Spring Security đưa một bearer principal tới @AuthenticationPrincipal trong MVC controller như thế nào?
Bạn sẽ xác định cách tách domain identity ra khỏi issuer-specific JWT claims để API ít phụ thuộc IdP ra sao?
Bạn sẽ xử lý trường hợp API cần chấp nhận access token từ nhiều IdPs mà không đánh đồng các namespace người dùng ra sao?
Bạn đánh giá các điều kiện nào cần được xác minh trước khi coi một bearer request đã authenticated như thế nào?
Bạn giải thích SecurityFilterChain và HttpSecurity cấu hình OAuth2 Resource Server cho Spring MVC application như thế nào?
Bạn sẽ tổ chức HttpSecurity.oauth2ResourceServer để xác minh JWT từ issuer đáng tin cậy theo cách nào?
Bạn mô tả vai trò của BearerTokenAuthenticationFilter trong việc trích xuất và xác thực access token ra sao?
Bạn phân biệt BearerTokenAuthenticationToken với JwtAuthenticationToken ở giai đoạn trước và sau JWT validation như thế nào?
Bạn sẽ xác định cách BearerTokenAuthenticationFilter chọn AuthenticationManager và xử lý kết quả thành công như thế nào?
Bạn mô tả JwtAuthenticationProvider dùng JwtDecoder và converter để xác thực JWT thành Authentication ra sao?
Bạn phân biệt AuthenticationManager với AuthenticationManagerResolver<HttpServletRequest> khi từng request cần một manager khác nhau như thế nào?
Bạn sẽ cấu hình SecurityFilterChain riêng cho /api/** có bearer authentication và /ui/** có form login ra sao?
Bạn phân tích rủi ro API vô tình nhận HttpSession authentication vì nhiều security chains chồng matcher như thế nào?
Bạn sẽ xác định khi nào securityMatcher và requestMatchers gây ra khoảng trống chưa được bảo vệ như thế nào?
Bạn phân biệt SessionCreationPolicy.STATELESS với bảo đảm tuyệt đối rằng mọi bộ lọc đều không động tới HttpSession ra sao?
Bạn sẽ kiểm tra SecurityContextRepository phù hợp với một API stateless theo yêu cầu nào?
Bạn phân tích rủi ro custom filter lưu Authentication vào session khi Resource Server được thiết kế không trạng thái ra sao?
Bạn sẽ dùng DefaultBearerTokenResolver để xử lý Authorization header theo các quy tắc an toàn nào?
Bạn phân biệt BearerTokenResolver tùy chỉnh với parsing Authorization header thủ công trong từng controller như thế nào?
Bạn sẽ quyết định có cho phép bearer token trong form body hoặc URI query theo rủi ro và tiêu chuẩn nào?
Bạn phân tích nguy cơ chấp nhận nhiều token từ nhiều vị trí trong một request khiến nguồn danh tính trở nên mơ hồ ra sao?
Bạn sẽ xác minh Authorization header bị sai schema, thiếu token hoặc trùng headers được xử lý an toàn như thế nào?
Bạn mô tả ExceptionTranslationFilter, AuthenticationEntryPoint và AccessDeniedHandler phối hợp khi Resource Server từ chối request ra sao?
Bạn sẽ cấu hình BearerTokenAuthenticationEntryPoint để phản hồi yêu cầu cần access token theo ngữ nghĩa nào?
Bạn phân biệt BearerTokenAuthenticationEntryPoint với BearerTokenAccessDeniedHandler về 401 và 403 như thế nào?
Bạn sẽ xử lý tình huống HTTP OPTIONS CORS preflight không mang bearer token nhưng trình duyệt cần nhận CORS headers ra sao?
Bạn phân tích vì sao CORS allowlist không chứng minh bearer token có quyền thực hiện API operation như thế nào?
Bạn sẽ xác định khi nào cần CSRF protection với API có bearer authentication nhưng cũng chấp nhận authentication cookie như thế nào?
Bạn sẽ đặt requestMatchers theo HTTP method để phân biệt quyền đọc và quyền ghi mà không mở quyền nhầm ra sao?
Bạn sẽ kiểm tra một request đã qua JwtAuthenticationProvider nhưng controller vẫn nhận anonymous Authentication do cấu hình context sai như thế nào?
Bạn phân tích vì sao custom authentication filter có thể chạy hai lần nếu vừa đăng ký servlet filter vừa thêm vào SecurityFilterChain ra sao?
Bạn sẽ bảo đảm token không xuất hiện trong MDC, audit logs hoặc exception body của một request lỗi như thế nào?
Bạn sẽ thiết kế authorization failure response thống nhất mà không làm lộ chính xác cấu hình token validation của hệ thống ra sao?
Bạn đánh giá cách bảo vệ actuator endpoints tách khỏi bearer API khi dùng nhiều SecurityFilterChain như thế nào?
Bạn giải thích cấu trúc header, payload và signature của JWT liên quan đến khả năng Resource Server xác minh token như thế nào?
Bạn phân biệt JWS đã ký với JWE đã mã hóa theo khả năng bảo mật và xử lý của Resource Server ra sao?
Bạn mô tả JwtDecoder trong Spring Security thực hiện những bước nào trước khi trả Jwt hợp lệ?
Bạn sẽ cấu hình NimbusJwtDecoder sử dụng JWK Set endpoint của issuer đáng tin cậy như thế nào?
Bạn phân biệt issuer-uri với jwk-set-uri trong cấu hình Resource Server về khám phá metadata và nơi lấy khóa ra sao?
Bạn sẽ sử dụng JwtDecoders.fromIssuerLocation khi cần suy ra cấu hình xác minh từ issuer metadata theo điều kiện nào?
Bạn phân tích rủi ro cấu hình jwk-set-uri thủ công nhưng bỏ kiểm tra iss claim như thế nào?
Bạn sẽ thiết kế JwtValidators.createDefaultWithIssuer để kiểm tra issuer và thời hạn token ra sao?
Bạn mô tả JwtIssuerValidator, JwtTimestampValidator và custom OAuth2TokenValidator phối hợp trong validation ra sao?
Bạn sẽ bổ sung DelegatingOAuth2TokenValidator để kiểm tra audience cùng các ràng buộc JWT khác như thế nào?
Bạn phân biệt chữ ký JWT hợp lệ với tính hợp lệ của iss, aud, exp và nbf như thế nào?
Bạn sẽ xác định audience hợp lệ khi một JWT chứa nhiều aud values theo policy của API ra sao?
Bạn phân tích vì sao API chỉ xác minh exp mà không xét nbf hoặc clock skew có thể nhận token ngoài cửa sổ hợp lệ ra sao?
Bạn sẽ chọn clock skew tolerance cho JwtTimestampValidator theo điều kiện đồng bộ thời gian nào?
Bạn mô tả vai trò của iat claim trong giám sát tuổi token và những giới hạn khi dùng nó làm điều kiện truy cập ra sao?
Bạn sẽ kiểm tra sub claim vắng mặt hoặc khác định dạng mà application yêu cầu như thế nào?
Bạn phân biệt iss của authorization server với tenant identifier nằm trong custom claim theo phạm vi tin cậy ra sao?
Bạn sẽ thiết kế validation riêng khi cùng issuer phát hành access tokens cho nhiều resources hoặc audiences khác nhau như thế nào?
Bạn phân tích nguy cơ dùng ID token từ OIDC provider làm access token khi Resource Server chỉ nhìn signature và issuer ra sao?
Bạn mô tả JWK Set (JWKS) chứa những trường khóa công khai nào để phục vụ signature verification?
Bạn phân biệt kid trong JWT header với việc JWT signature thực sự được kiểm bằng public key nào như thế nào?
Bạn sẽ xác định lý do một JWT có kid không khớp khóa nào trong JWKS và cách phản hồi phù hợp ra sao?
Bạn phân tích nguy cơ tin đường dẫn jku hoặc x5u do token header chỉ định rồi fetch key từ host không tin cậy như thế nào?
Bạn sẽ giới hạn thuật toán JWS được chấp nhận thay vì tin alg do token tự công bố như thế nào?
Bạn mô tả trường hợp alg=none hoặc algorithm confusion có thể gây hậu quả gì nếu decoder kiểm tra sai chính sách ra sao?
Bạn sẽ xác minh trường hợp RS256 token được đưa vào decoder chỉ cho phép thuật toán khác có bị từ chối như thế nào?
Bạn phân biệt symmetric HMAC secret với asymmetric public/private key khi nhiều resource servers cần xác minh JWT ra sao?
Bạn sẽ quyết định thời điểm dùng RSA hoặc EC signing algorithms theo khả năng hỗ trợ và chính sách bảo mật nào?
Bạn phân tích rủi ro cấp shared symmetric secret cho nhiều microservices rồi mọi service đều có khả năng ký token như thế nào?
Bạn mô tả quy trình JWKS key rotation khi IdP công bố khóa mới và giữ khóa cũ trong thời gian chuyển đổi ra sao?
Bạn sẽ xử lý JWT mang kid mới khi JWK Set cache của một resource server chưa được làm mới như thế nào?
Bạn phân biệt lỗi JWKS endpoint bị outage với lỗi JWT signature thực sự không hợp lệ trong chẩn đoán ra sao?
Bạn sẽ tổ chức cache và timeout lấy JWKS để Resource Server không phụ thuộc mạng trên mọi request ra sao?
Bạn phân tích rủi ro cache JWKS quá lâu sau khi một signing key bị thu hồi khẩn cấp như thế nào?
Bạn sẽ thiết kế chính sách refresh JWKS có giới hạn để tránh thác request tới issuer khi xuất hiện kid lạ như thế nào?
Bạn đánh giá khi nào cần cấu hình JWKS endpoint cố định để ứng dụng startup không phụ thuộc vào issuer discovery endpoint ra sao?
Bạn sẽ xác minh issuer discovery metadata không dẫn application tới endpoint thuộc domain không đáng tin cậy như thế nào?
Bạn mô tả cách xử lý lỗi malformed JWT hoặc payload vượt kích thước tối đa trước khi thực hiện validation tốn tài nguyên ra sao?
Bạn sẽ xác định rủi ro nhúng PII hoặc secret vào JWT payload có thể được client giải mã dù có chữ ký như thế nào?
Bạn phân biệt JWT bị chỉnh sửa claims nhưng signature không hợp lệ với token đã ký đúng nhưng cấp quyền quá rộng ra sao?
Bạn sẽ đánh giá cách chống replay token sau khi bị đánh cắp nếu Resource Server chỉ kiểm chữ ký và thời hạn ra sao?
Bạn giải thích scope của OAuth 2.0 access token được chuyển thành GrantedAuthority trong Spring Security như thế nào?
Bạn mô tả JwtGrantedAuthoritiesConverter đọc scope hoặc scp claim và tạo SCOPE_ authorities theo cấu hình như thế nào?
Bạn sẽ sử dụng JwtAuthenticationConverter để thay đổi authorities hoặc principal claim của JwtAuthenticationToken ra sao?
Bạn phân biệt scope mang tên orders.read với authority SCOPE_orders.read mà request matcher kiểm tra như thế nào?
Bạn sẽ cấu hình hasAuthority("SCOPE_orders.read") cho API truy vấn đơn hàng như thế nào?
Bạn phân tích rủi ro gọi hasRole thay vì hasAuthority khi access token chỉ có SCOPE_ prefix ra sao?
Bạn sẽ xử lý token có scope là chuỗi phân cách bằng dấu cách so với scp là mảng values như thế nào?
Bạn phân biệt việc tin scope claim do issuer cấp với việc lấy roles tự khai báo từ request body ra sao?
Bạn sẽ chọn quy tắc map custom roles claim thành authorities mà không vô tình đồng nhất role với scope như thế nào?
Bạn phân tích rủi ro dùng claim groups quá lớn làm token tăng kích thước và thay đổi quyền chậm ra sao?
Bạn sẽ giới hạn authorities chỉ được sinh từ claims của token issuer tin cậy theo cách nào?
Bạn sẽ thiết kế multi-issuer authority mapping khi cùng scope name có ý nghĩa khác nhau giữa hai nhà phát hành ra sao?
Bạn phân biệt resource-level scope với ownership của một order cụ thể trong business authorization như thế nào?
Bạn sẽ dùng @PreAuthorize để kiểm tra scope đồng thời kiểm tra owner của dữ liệu theo cách nào?
Bạn phân tích vì sao một JWT chứa SCOPE_admin không có nghĩa API phải mặc nhiên cấp mọi quyền mà không kiểm tra audience hoặc issuer ra sao?
Bạn sẽ tổ chức PermissionEvaluator hoặc custom AuthorizationManager khi quyền phụ thuộc tenant và resource identifier như thế nào?
Bạn phân biệt xác thực máy qua client_credentials với quyền của end user khi API có dữ liệu cá nhân ra sao?
Bạn sẽ xây dựng policy chỉ cho client credentials token gọi endpoints dành cho service accounts theo điều kiện nào?
Bạn phân tích nguy cơ dùng preferred_username hoặc email làm khóa định danh khi giá trị thay đổi hoặc không được verify ra sao?
Bạn sẽ dùng iss+sub để định danh principal từ nhiều issuers mà tránh trùng tài khoản theo cách nào?
Bạn mô tả cách @AuthenticationPrincipal Jwt hoặc JwtAuthenticationToken giúp truy cập claims ở controller ra sao?
Bạn sẽ thiết kế domain principal adapter để không phải đọc custom claims trực tiếp ở mọi business service như thế nào?
Bạn đánh giá khi nào cần kiểm tra account còn hoạt động trong database dù token mang scope hợp lệ ra sao?
Bạn sẽ kiểm thử thiếu scope, scope lạ và scope hợp lệ nhưng sai ownership theo từng kết quả 403 nào?
Bạn phân tích vì sao chỉ dùng request-level access rules không đủ bảo vệ những GraphQL field hoặc service method được gọi từ nhiều ngõ vào ra sao?
Bạn sẽ thiết kế policy bảo vệ cả Servlet controllers và background service calls mà không phụ thuộc chỉ vào URL ra sao?
Bạn giải thích opaque access token khác JWT ở chỗ Resource Server không thể tự đọc và xác minh toàn bộ claims như thế nào?
Bạn mô tả OAuth2 Token Introspection endpoint trả metadata gì khi một opaque token đang active?
Bạn sẽ sử dụng OpaqueTokenIntrospector trong Spring Security để xác minh bearer opaque token như thế nào?
Bạn phân biệt OpaqueTokenIntrospector với JwtDecoder về nguồn sự thật để xác thực token ra sao?
Bạn sẽ cấu hình introspection-uri và client credentials được cấp riêng cho Resource Server theo nguyên tắc nào?
Bạn phân tích nguy cơ lưu introspection client secret trong source code hoặc log HTTP headers ra sao?
Bạn mô tả luồng Resource Server nhận token rồi gửi request xác minh tới Authorization Server introspection endpoint như thế nào?
Bạn sẽ xác định cách xử lý introspection response active=false theo OAuth2 error semantics ra sao?
Bạn phân biệt lỗi token inactive với lỗi mạng hoặc HTTP 5xx của introspection service ra sao?
Bạn sẽ thiết kế retry có backoff cho introspection outage nhưng không retry token bị báo inactive như thế nào?
Bạn đánh giá tác động của request timeout khi introspection endpoint chậm tới throughput của API ra sao?
Bạn sẽ xác định chính sách fail-closed khi introspection service không khả dụng nhưng request có token chưa xác minh ra sao?
Bạn phân tích nguy cơ cho phép API truy cập dữ liệu nhạy cảm chỉ vì introspection endpoint đã timeout như thế nào?
Bạn sẽ map introspection attributes như sub, scope và client_id thành principal và authorities theo cách nào?
Bạn phân biệt BearerTokenAuthentication của opaque token với JwtAuthenticationToken của JWT theo dữ liệu gốc và accessors ra sao?
Bạn sẽ tạo custom OpaqueTokenIntrospector để bổ sung authority mapping theo ngữ cảnh ứng dụng trong trường hợp nào?
Bạn phân tích rủi ro custom introspector trả authorities từ dữ liệu client chưa xác minh thay vì từ phản hồi tin cậy ra sao?
Bạn sẽ giới hạn quyền truy cập introspection endpoint của Resource Server chỉ ở thao tác cần thiết như thế nào?
Bạn sẽ sử dụng TLS và certificate verification để bảo vệ token khi gửi tới introspection endpoint ra sao?
Bạn phân biệt xác thực introspection client bằng client secret với mTLS client authentication theo hỗ trợ của provider như thế nào?
Bạn sẽ quyết định có cache introspection result hay không theo yêu cầu latency và tốc độ thu hồi token nào?
Bạn phân tích vì sao cache active=true quá lâu khiến token revoked vẫn được chấp nhận ra sao?
Bạn sẽ thiết kế cache key hoặc token fingerprint mà không lưu raw access token vào logging hoặc metrics như thế nào?
Bạn đánh giá khi nào introspection cache cần gắn issuer hoặc tenant context để không trộn token namespaces ra sao?
Bạn sẽ xử lý introspection response thiếu scope hoặc sub khi policy của API yêu cầu các thuộc tính đó như thế nào?
Bạn phân tích nguy cơ dùng client_id từ introspection response để coi token là end-user token khi grant type không rõ ra sao?
Bạn sẽ kiểm tra audience/resource constraints nếu introspection response cung cấp thông tin phù hợp như thế nào?
Bạn sẽ thiết kế degradation policy khi introspection provider thay đổi response schema nhưng API vẫn phải fail safely ra sao?
Bạn sẽ đo số lượt introspection calls mỗi request và hiệu quả cache để tối ưu vận hành như thế nào?
Bạn sẽ so sánh chi phí kiểm tra thu hồi token giữa JWT offline verification và opaque online introspection theo SLA nào?
Bạn giải thích cơ chế multi-tenant Resource Server lựa chọn trusted issuer dựa trên yêu cầu nào?
Bạn phân biệt nhiều issuer cùng ký JWT với một issuer phát hành token có tenant_id claim theo mô hình tin cậy ra sao?
Bạn sẽ sử dụng JwtIssuerAuthenticationManagerResolver khi từng tenant có issuer URL khác nhau theo cách nào?
Bạn mô tả AuthenticationManagerResolver<HttpServletRequest> có thể chọn AuthenticationManager theo request context như thế nào?
Bạn sẽ xác định danh sách trusted issuers trước khi chấp nhận một issuer mới vào production ra sao?
Bạn phân tích vì sao lấy iss claim chưa xác minh rồi tự ý gọi discovery URL của nó có thể tạo SSRF ra sao?
Bạn sẽ hạn chế dynamic issuer discovery bằng allowlist hoặc tenant registry đã được quản trị như thế nào?
Bạn phân biệt tenant do hostname hoặc đường dẫn API xác định với tenant claim nằm trong token theo chính sách kiểm tra nào?
Bạn sẽ kiểm tra tenant trong route có khớp tenant đã được xác minh từ JWT hoặc introspection response như thế nào?
Bạn phân tích rủi ro tin tenant_id do client tự gửi qua header dù token thuộc tenant khác ra sao?
Bạn sẽ thiết kế per-issuer JwtDecoder với JWKS và validators riêng để cô lập các vùng tin cậy như thế nào?
Bạn sẽ xác định cách xử lý hai issuers sử dụng cùng kid nhưng khác public keys ra sao?
Bạn phân tích nguy cơ dùng JWKS cache toàn cục sai khóa khiến token issuer A được kiểm bằng trust configuration của issuer B ra sao?
Bạn sẽ map identity theo (issuer, subject) để tránh hai users có sub giống nhau nhưng thuộc các tenants khác như thế nào?
Bạn sẽ thiết kế authority prefixes hoặc permission mapping khác nhau cho tenants mà không cấp nhầm quyền quản trị ra sao?
Bạn đánh giá khả năng một tenant dùng opaque tokens trong khi tenant khác dùng JWT và cách tổ chức manager selection ra sao?
Bạn sẽ phân biệt cơ chế phát hiện token type bằng policy định sẵn với việc tin một header do client tự khai báo như thế nào?
Bạn sẽ thiết kế onboarding tenant mới mà không cho user tùy ý đăng ký một issuer không được xác minh như thế nào?
Bạn phân tích rủi ro tenant registry update sai làm toàn bộ request được xác thực bởi issuer nhầm như thế nào?
Bạn sẽ xác định cách thu hồi issuer bị xâm phạm khỏi danh sách tin cậy mà không ảnh hưởng các issuers khác ra sao?
Bạn sẽ xây dựng test token của issuer A bị từ chối khi đi vào endpoint chỉ dành cho tenant B như thế nào?
Bạn phân tích vì sao authentication thành công với issuer tin cậy chưa đủ để cho phép truy cập dữ liệu thuộc tenant khác ra sao?
Bạn sẽ thiết kế log và metrics per issuer với tên chuẩn hóa nhưng không ghi access token hoặc subject vào tags như thế nào?
Bạn sẽ xác định giới hạn cache JWKS hoặc AuthenticationManager trên mỗi tenant để tránh tiêu thụ memory không giới hạn ra sao?
Bạn đánh giá khi nào cùng một issuer dùng nhiều audiences nên tách JwtDecoder configurations hoặc policy validators như thế nào?
Bạn sẽ quản lý rotation client secrets của introspection cho từng tenant theo cách nào?
Bạn phân tích nguy cơ lỗi network của một tenant gây cascade failure cho tenants khác nếu sử dụng cùng connection pool ra sao?
Bạn sẽ thiết kế circuit breaker hoặc concurrency limits theo tenant cho introspection để cô lập sự cố như thế nào?
Bạn sẽ xác định điểm kiểm tra tenant authorization trong cả request filter và business service như thế nào?
Bạn đánh giá cách triển khai canary trust configuration khi chuyển một tenant sang issuer mới ra sao?
Bạn giải thích SecurityWebFilterChain của WebFlux đảm nhận bảo vệ resource server khác SecurityFilterChain servlet như thế nào?
Bạn sẽ cấu hình ServerHttpSecurity.oauth2ResourceServer cho JWT authentication trong Spring WebFlux ra sao?
Bạn phân biệt ReactiveJwtDecoder với JwtDecoder khi ứng dụng sử dụng Reactor-based authentication ra sao?
Bạn sẽ dùng NimbusReactiveJwtDecoder khi WebFlux cần tải JWK Set và xác minh JWT theo chính sách nào?
Bạn mô tả AuthenticationWebFilter phối hợp với reactive authentication manager để xác minh bearer request như thế nào?
Bạn sẽ sử dụng ServerBearerTokenAuthenticationConverter để lấy bearer token trong WebFlux theo yêu cầu nào?
Bạn phân biệt Servlet BearerTokenAuthenticationFilter với reactive AuthenticationWebFilter về execution model như thế nào?
Bạn sẽ xác định cách ReactiveSecurityContextHolder truyền Authentication qua Reactor Context như thế nào?
Bạn phân tích vì sao ThreadLocal SecurityContextHolder không phải nguồn đáng tin cậy cho mọi bước trong reactive pipeline ra sao?
Bạn sẽ kiểm tra context bị mất khi code tự subscribe tạo một reactive chain độc lập như thế nào?
Bạn sẽ thiết kế reactive authorization sao cho downstream Mono không dùng blocking JPA hoặc LDAP call trên event loop ra sao?
Bạn đánh giá khi nào reactive opaque token introspection phù hợp với API có lưu lượng lớn như thế nào?
Bạn sẽ sử dụng ReactiveOpaqueTokenIntrospector để xác minh opaque tokens mà không chặn Reactor event loop ra sao?
Bạn sẽ xử lý lỗi network của reactive introspector bằng Mono error signal mà vẫn trả 401 hoặc 5xx phù hợp theo tình huống như thế nào?
Bạn phân biệt Mono phát authentication error với Mono trả empty trong một reactive authentication flow theo semantics ra sao?
Bạn sẽ dùng ReactiveJwtAuthenticationConverterAdapter khi tái sử dụng JwtAuthenticationConverter trong reactive service theo cách nào?
Bạn sẽ thiết kế WebFlux method security với @EnableReactiveMethodSecurity và @PreAuthorize dựa trên JWT authorities như thế nào?
Bạn phân tích rủi ro controller reactive trả Flux trước khi xác minh quyền truy cập từng dữ liệu thuộc tenant khác ra sao?
Bạn sẽ xác định cách ServerHttpSecurity áp dụng 401 và 403 cho bearer token invalid hoặc thiếu scope ra sao?
Bạn sẽ giới hạn size và concurrency của JWKS/introspection requests trong reactive stack như thế nào?
Bạn sẽ kiểm tra Reactor Context propagation khi chuyển execution qua publishOn hoặc subscribeOn như thế nào?
Bạn phân tích rủi ro một custom WebFilter đọc request body để tìm token và làm mất body cho downstream handlers như thế nào?
Bạn sẽ lựa chọn authentication trong Authorization header thay vì URI query cho WebFlux SSE hoặc streaming endpoint ra sao?
Bạn sẽ xử lý client cancellation khi introspection request đang chờ remote server để không rò connections như thế nào?
Bạn đánh giá cách cấu hình distinct reactive authentication managers cho nhiều trusted issuers theo policy nào?
Bạn sẽ xử lý asynchronous authority enrichment sau JWT decoding mà không làm blocking hoặc bỏ qua validation ra sao?
Bạn sẽ đánh giá tác động của Reactor retryWhen tại introspection call khi provider trả token inactive như thế nào?
Bạn phân tích vì sao rate limiting JWT verification và introspection khác nhau về CPU, I/O và downstream dependency ra sao?
Bạn sẽ dùng WebTestClient để kiểm tra bearer authenticated route và anonymous route trong WebFlux như thế nào?
Bạn sẽ thiết kế tracing trong reactive context mà không đưa claims nhạy cảm vào span attributes ra sao?
Bạn giải thích HTTP WWW-Authenticate: Bearer challenge có ý nghĩa gì đối với client khi API trả 401?
Bạn phân biệt OAuth2 errors invalid_request, invalid_token và insufficient_scope theo nguyên nhân và status như thế nào?
Bạn sẽ xác định lúc nào Resource Server trả 403 insufficient_scope thay vì 401 invalid_token ra sao?
Bạn mô tả BearerTokenAccessDeniedHandler giúp xây response khi một token hợp lệ nhưng thiếu quyền ra sao?
Bạn sẽ cấu hình AuthenticationEntryPoint và AccessDeniedHandler tùy biến mà vẫn giữ semantics bearer challenge như thế nào?
Bạn phân tích rủi ro trả chi tiết chữ ký JWT hoặc nội dung introspection secret trong API error body ra sao?
Bạn sẽ xử lý trường hợp access token bị malformed mà không ném stack trace về phía client như thế nào?
Bạn sẽ phân biệt lỗi issuer không tin cậy với issuer đúng nhưng JWKS endpoint không khả dụng trong runbook như thế nào?
Bạn đánh giá khi nào lỗi network của JWKS endpoint cần được biểu diễn như authentication failure hoặc service availability issue ra sao?
Bạn sẽ thiết kế structured logging cho token validation failures nhưng không lưu toàn bộ access token ra sao?
Bạn phân tích vì sao ghi payload JWT vào log có thể tiết lộ PII dù JWT không có mật mã hóa ra sao?
Bạn sẽ xác định cách băm fingerprint token phục vụ điều tra mà không tạo identifier cho metrics có cardinality cao ra sao?
Bạn sẽ xây dựng policy kiểm soát maximum Authorization header size nhằm ngăn request chứa token quá lớn như thế nào?
Bạn sẽ phân biệt việc resource server thu hồi một JWT với việc authorization server đánh dấu opaque token inactive ra sao?
Bạn sẽ thiết kế short-lived JWT và refresh policy để giới hạn cửa sổ rủi ro sau khi access token bị đánh cắp như thế nào?
Bạn phân tích vì sao resource server không nên nhận refresh token để đổi hoặc sử dụng thay access token như thế nào?
Bạn sẽ cân nhắc token denylist hoặc revocation cache khi cần chặn JWT trước khi hết hạn theo điều kiện nào?
Bạn đánh giá nguy cơ denylist trong memory không đồng bộ giữa nhiều resource server replicas ra sao?
Bạn sẽ định nghĩa TTL cho revocation records dựa trên exp của token thay vì giữ vô hạn như thế nào?
Bạn phân tích khi nào thay đổi password hoặc khóa user cần thu hồi access token và lúc nào cần session logout riêng ra sao?
Bạn sẽ kiểm tra token có jti hoặc stable session identifier theo chính sách issuer trước khi xây cơ chế revocation như thế nào?
Bạn phân biệt thu hồi signing key với thu hồi một token cụ thể về tác động tới những token khác như thế nào?
Bạn sẽ ứng phó sự cố rò signing private key bằng rotation, JWKS refresh và trust-policy update như thế nào?
Bạn phân tích rủi ro resource server chấp nhận JWT cũ ký bằng key đã bị ngừng tin cậy nhưng còn trong cache ra sao?
Bạn sẽ thiết kế tối thiểu hóa downtime khi cần emergency revoke signing key cho nhiều resource servers ra sao?
Bạn sẽ so sánh revocation lookup tại resource server với introspection cho mọi request về bảo mật và chi phí như thế nào?
Bạn đánh giá cần làm gì khi authorization server thu hồi user permissions nhưng JWT cũ vẫn có scopes chưa hết hạn ra sao?
Bạn sẽ thiết kế step-up authorization ở business layer khi token authentication thành công nhưng hành động cần assurance cao ra sao?
Bạn phân tích vì sao resource server không thể tự suy ra MFA đã hoàn tất nếu token không có claims đáng tin cậy về assurance ra sao?
Bạn sẽ xác định cách kiểm tra amr hoặc acr claims khi chúng có trong profile token được issuer quy định ra sao?
Bạn sẽ thiết kế error và retry policy cho expired JWT mà không làm client tạo vòng lặp refresh vô hạn như thế nào?
Bạn phân tích rủi ro API đưa WWW-Authenticate header chứa quá nhiều thông tin nội bộ về cấu hình issuer ra sao?
Bạn sẽ tạo runbook phân biệt 401 no token, 401 invalid token, 403 missing scope và 503 introspection outage như thế nào?
Bạn sẽ dùng Micrometer để quan sát latency và failure rate của JWT decoding trong Spring Security Resource Server như thế nào?
Bạn phân biệt authentication failure rate với authorization denial rate khi thiết kế dashboard bảo mật ra sao?
Bạn sẽ theo dõi JWKS fetch latency, cache refresh và số lần gặp kid không xác định bằng metrics nào?
Bạn phân tích rủi ro đặt JWT subject, email, token hoặc jti làm metrics labels tạo cardinality cao và lộ dữ liệu ra sao?
Bạn sẽ kiểm tra p95 API latency tăng do introspection endpoint trong khi database vẫn đáp ứng nhanh như thế nào?
Bạn sẽ đánh giá mô hình caching opaque introspection results bằng hit rate, revocation lag và traffic như thế nào?
Bạn phân tích ảnh hưởng của JWT signing algorithm và token kích thước lớn lên CPU khi API chịu tải cao ra sao?
Bạn sẽ thiết kế load test so sánh offline JWT verification với remote introspection theo concurrency nào?
Bạn sẽ giới hạn số connections tới introspection endpoint khi nhiều requests bị retry do timeout như thế nào?
Bạn phân tích vì sao retry storm sau IdP outage có thể làm hỏng cả dịch vụ đang phục hồi ra sao?
Bạn sẽ thiết kế circuit breaker cho dependency introspection mà không chấp nhận token chưa được kiểm tra như thế nào?
Bạn sẽ phân biệt readiness của API với liveness khi JWKS endpoint hoặc introspection server đang không sẵn sàng ra sao?
Bạn sẽ quyết định khi nào cache JWKS giúp API tiếp tục xử lý token ký bằng khóa đã biết trong outage như thế nào?
Bạn phân tích rủi ro startup gọi issuer metadata endpoint làm service không khởi động khi IdP đang bảo trì ra sao?
Bạn sẽ thiết kế logging với correlation ID để lần theo một HTTP 401 mà không ghi credential material ra sao?
Bạn sẽ hạn chế trace span attributes ở mức issuer alias, token type và kết quả kiểm tra theo quy định nào?
Bạn phân tích khi nào nhiều tenants cần bulkheads riêng để một issuer chậm không làm cạn resource server threads ra sao?
Bạn sẽ điều tra một đợt tăng đột biến invalid signature có thể đến từ client bug, key rotation hay tấn công như thế nào?
Bạn sẽ kiểm tra cấu hình clock synchronization khi nhiều resource server nodes bất đồng về việc JWT đã hết hạn ra sao?
Bạn đánh giá các chỉ số nào cho thấy JwtDecoder đang phải tải JWKS quá thường xuyên vì cache configuration không đúng như thế nào?
Bạn sẽ quản lý trusted issuer configuration và secrets qua môi trường mà không lưu credentials vào Git như thế nào?
Bạn sẽ định nghĩa checklist production cho TLS, token audience, issuer, allowed algorithms, authority mapping và error handling ra sao?
Bạn sẽ đánh giá security review khi chuyển API từ opaque token introspection sang JWT self-validation theo những rủi ro nào?
Bạn sẽ lập kế hoạch rollout hai loại token đồng thời trong giai đoạn chuyển đổi mà không bỏ qua xác minh phù hợp cho từng loại như thế nào?
Bạn phân tích nguy cơ thay đổi scope naming giữa hai IdP làm các REST endpoints bị cấp quyền rộng hoặc từ chối sai ra sao?
Bạn sẽ thiết kế feature flags cho auth configuration nhưng không cho phép tắt validation trong production như thế nào?
Bạn sẽ xác minh các Spring Boot actuator endpoints không vô tình công bố issuer secrets hoặc authentication internals ra sao?
Bạn phân biệt unit test JwtGrantedAuthoritiesConverter với integration test thực hiện JWT signature validation qua SecurityFilterChain như thế nào?
Bạn sẽ dùng MockMvc với springSecurity() để kiểm tra một endpoint chỉ nhận bearer token hợp lệ như thế nào?
Bạn mô tả jwt() request postprocessor trong spring-security-test giúp mô phỏng JwtAuthenticationToken theo cách nào?
Bạn phân tích vì sao test dùng jwt() mock không chứng minh JwtDecoder thật sự xác minh issuer, signature hay audience ra sao?
Bạn sẽ tạo test dùng JWKS mock server để ký một JWT hợp lệ rồi đi qua JwtDecoder thật như thế nào?
Bạn sẽ kiểm thử JWT có signature không hợp lệ nhưng scope đầy đủ vẫn phải bị từ chối ra sao?
Bạn sẽ kiểm thử JWT sai issuer hoặc sai audience và kiểm tra HTTP 401 như thế nào?
Bạn sẽ kiểm tra nbf trong tương lai, exp trong quá khứ và clock skew boundary qua một clock kiểm soát ra sao?
Bạn sẽ tạo test JWT có kid không tồn tại trong JWKS và xác minh key-fetch failure được xử lý an toàn như thế nào?
Bạn sẽ mô phỏng signing key rotation trong JWKS và xác minh decoder chấp nhận khóa mới theo policy như thế nào?
Bạn phân tích vì sao kiểm thử chỉ có happy path không phát hiện token substitution giữa resource servers ra sao?
Bạn sẽ viết test token có scope orders.read nhưng thiếu orders.write để xác minh route POST trả 403 như thế nào?
Bạn sẽ kiểm tra user có đúng scope nhưng sai resource ownership vẫn bị authorization service từ chối ra sao?
Bạn sẽ sử dụng @WithMockUser cho test method security khi cần hiểu ranh giới với bearer authentication test như thế nào?
Bạn sẽ xây dựng test opaque token bằng opaqueToken() request postprocessor và phân biệt với introspection integration test ra sao?
Bạn sẽ dùng mock HTTP introspection server để xác minh active=false bị từ chối và active=true được ánh xạ đúng authorities như thế nào?
Bạn sẽ kiểm tra introspection endpoint timeout làm Resource Server fail closed thay vì cho request qua như thế nào?
Bạn sẽ kiểm thử introspection response không có sub hoặc scope theo policy của ứng dụng ra sao?
Bạn sẽ viết test phát hiện raw bearer tokens không xuất hiện trong logs sau một authentication failure như thế nào?
Bạn sẽ sử dụng WebTestClient với mockJwt() để kiểm tra WebFlux access rules mà không bỏ qua các negative cases nào?
Bạn phân biệt mockJwt() của reactive security test với một test có ReactiveJwtDecoder thật ở những lớp nào?
Bạn sẽ kiểm thử Reactor Context của authenticated user không bị rò sang một subscriber khác như thế nào?
Bạn sẽ xây dựng integration test cho JwtIssuerAuthenticationManagerResolver chỉ chấp nhận trusted issuers như thế nào?
Bạn sẽ kiểm thử JWT của tenant A không được phép gọi API của tenant B dù cả hai issuers đều tin cậy ra sao?
Bạn sẽ kiểm thử malformed Authorization header, nhiều bearer tokens và token đặt trong query parameter bị xử lý theo policy như thế nào?
Bạn sẽ xác minh unauthenticated API trả WWW-Authenticate header phù hợp còn valid token thiếu scope trả 403 ra sao?
Bạn sẽ kiểm thử CORS preflight hoạt động nhưng POST thực vẫn đòi bearer token và scope như thế nào?
Bạn sẽ dùng @SpringBootTest khi cần xác minh cấu hình issuer-uri, JWKS và các security filter beans đồng thời ra sao?
Bạn sẽ tổ chức Testcontainers hoặc test HTTP server riêng khi cần tái hiện network outage của introspection endpoint như thế nào?
Bạn sẽ tạo stress test cho key rotation và JWKS cache refresh mà không làm flaky các test khác như thế nào?
Bạn sẽ chạy security regression tests sau nâng Spring Security version để kiểm tra JWT validators và converter behavior như thế nào?
Bạn đánh giá tập test tối thiểu bảo vệ Resource Server trước invalid token, wrong tenant, revoked token và missing authorities như thế nào?
Nếu API trả 401 cho JWT hợp lệ ngay sau IdP key rotation, bạn sẽ kiểm tra kid, JWKS cache và allowed algorithms như thế nào?
Nếu JwtDecoder chấp nhận token của issuer đúng nhưng audience thuộc một dịch vụ khác, bạn sẽ bổ sung validation ra sao?
Nếu access token ký đúng nhưng scope từ provider A được hiểu sai thành role admin, bạn sẽ sửa JwtGrantedAuthoritiesConverter hoặc policy như thế nào?
Nếu resource server nhận một OIDC ID token như bearer access token, bạn sẽ kiểm tra token type, audience và claim requirements như thế nào?
Nếu API nhận token từ issuer không nằm trong allowlist, bạn sẽ xử lý JwtIssuerAuthenticationManagerResolver mà không tự gọi URL chưa tin cậy như thế nào?
Nếu user của tenant A có cùng sub với user tenant B, bạn sẽ xây principal identity theo iss+sub ra sao?
Nếu SecurityFilterChain dành cho browser vô tình áp dụng cho /api/** khiến API trả HTML login, bạn sẽ sửa chain matching như thế nào?
Nếu một bearer token hợp lệ được xác thực nhưng thiếu scope và API trả 401 thay vì 403, bạn sẽ kiểm tra AccessDeniedHandler như thế nào?
Nếu opaque introspection server trả 500 liên tục, bạn sẽ tổ chức timeout, fail-closed và backoff mà không chấp nhận token chưa xác minh ra sao?
Nếu cache introspection vẫn nhận token đã revoked, bạn sẽ điều chỉnh TTL và revocation SLA như thế nào?
Nếu JWT của người dùng bị đánh cắp nhưng chưa hết hạn, bạn sẽ lựa chọn revoke token hoặc key rotation theo phạm vi ảnh hưởng như thế nào?
Nếu Authorization header bị ghi vào distributed tracing, bạn sẽ thay đổi sanitization ở filter và logging như thế nào?
Nếu API WebFlux mất authentication trong một Mono được subscribe riêng, bạn sẽ sửa Reactor Context propagation như thế nào?
Nếu một request chờ JWKS fetch khiến p99 latency tăng, bạn sẽ thiết kế caching, connection timeouts và metrics như thế nào?
Nếu test với jwt() PASS nhưng production từ chối JWT do sai issuer metadata, bạn sẽ bổ sung test qua decoder và JWKS thật như thế nào?
Nếu token client credentials được sử dụng truy cập dữ liệu user qua endpoint không kiểm tra chủ sở hữu, bạn sẽ thiết kế phân biệt principal và authorization ra sao?
Nếu API mới phải hỗ trợ JWT, opaque token, nhiều tenants, Servlet và WebFlux, bạn sẽ tổ chức trust policies, converters, errors, token revocation và kiểm thử như thế nào?

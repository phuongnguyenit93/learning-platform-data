Bạn giải thích Spring Security phân biệt authentication và authorization trong một luồng HTTP request như thế nào?
Bạn mô tả vai trò của Authentication khi biểu diễn danh tính, credentials, principal và authorities ra sao?
Bạn phân biệt Authentication được gửi để xác thực với Authentication đã được xác thực thành công theo các thuộc tính nào?
Bạn sẽ kiểm tra isAuthenticated của một Authentication mà không nhầm với việc user đã đăng nhập bằng một yếu tố mạnh như thế nào?
Bạn phân tích rủi ro tin tưởng một Authentication do mã ứng dụng tự tạo mà chưa được AuthenticationManager kiểm tra ra sao?
Bạn sẽ quyết định loại Authentication token phù hợp với username/password, bearer token và chứng chỉ client theo tiêu chí nào?
Bạn phân biệt Authentication.getPrincipal với Authentication.getCredentials về vòng đời lưu trữ dữ liệu nhạy cảm ra sao?
Bạn sẽ thiết kế principal nội bộ ổn định khi username có thể đổi hoặc có nhiều identity providers như thế nào?
Bạn phân tích vì sao GrantedAuthority nên mô tả quyền đã được xác minh chứ không lấy trực tiếp từ payload của client ra sao?
Bạn sẽ thiết kế ánh xạ roles hoặc groups từ identity source sang GrantedAuthority theo nguyên tắc nào?
Bạn phân biệt SimpleGrantedAuthority với các đối tượng quyền nghiệp vụ cần dữ liệu bổ sung ra sao?
Bạn sẽ xác định danh tính hiện tại từ Authentication thay vì tin userId do request khai báo như thế nào?
Bạn mô tả AuthenticationManager là hợp đồng gì và ai gọi nó trong authentication flow như thế nào?
Bạn sẽ dùng ProviderManager để phối hợp nhiều AuthenticationProvider theo nguyên tắc lựa chọn nào?
Bạn phân biệt AuthenticationManager với AuthenticationProvider về trách nhiệm điều phối và kiểm tra credentials ra sao?
Bạn giải thích AuthenticationProvider.supports ảnh hưởng việc ProviderManager chọn provider cho Authentication type như thế nào?
Bạn sẽ xác định provider nào được gọi khi nhiều AuthenticationProviders cùng hỗ trợ một token type ra sao?
Bạn phân tích ý nghĩa provider trả null so với ném AuthenticationException khi không thể hoặc không chấp nhận xác thực như thế nào?
Bạn sẽ tổ chức provider chain để có các cơ chế đăng nhập độc lập mà không fallback thiếu kiểm soát ra sao?
Bạn phân biệt BadCredentialsException, UsernameNotFoundException và AuthenticationServiceException theo loại lỗi xác thực như thế nào?
Bạn sẽ chuẩn hóa phản hồi ra client để không tiết lộ user có tồn tại hay không dù lỗi gốc khác nhau ra sao?
Bạn mô tả ProviderNotFoundException giúp chẩn đoán tình huống AuthenticationManager không có provider phù hợp như thế nào?
Bạn sẽ sử dụng AuthenticationManagerResolver khi cách xác thực thay đổi theo request hoặc tenant như thế nào?
Bạn đánh giá rủi ro chọn AuthenticationManager theo header tenant do client tự tạo mà không xác minh ngữ cảnh ra sao?
Bạn sẽ thiết kế một custom AuthenticationProvider cho hệ thống định danh nội bộ mà vẫn tôn trọng vòng đời Authentication ra sao?
Bạn phân tích khi nào custom provider không nên tự lưu plaintext credentials trong principal hoặc logs ra sao?
Bạn sẽ xác định lỗi từ provider là transient infrastructure failure hay invalid credentials để quyết định có retry hay không như thế nào?
Bạn sẽ thiết kế unit test cho provider khi token type không được hỗ trợ để xác minh hành vi contract ra sao?
Bạn mô tả vai trò của AbstractAuthenticationToken khi triển khai một Authentication type có metadata riêng như thế nào?
Bạn phân biệt UsernamePasswordAuthenticationToken được tạo từ request với token sau authentication mà provider trả về ra sao?
Bạn sẽ kiểm tra object returned từ AuthenticationProvider không mang credentials không cần thiết trong response ra sao?
Bạn giải thích ProviderManager có chính sách eraseCredentialsAfterAuthentication để giảm lưu giữ dữ liệu bí mật như thế nào?
Bạn phân tích rủi ro cache UserDetails hoặc Authentication object mutable bị mất password nếu thông tin được xóa credentials in-place ra sao?
Bạn sẽ đánh giá khi nào parent AuthenticationManager được dùng trong kiến trúc nhiều manager như thế nào?
Bạn phân biệt hiệu lực của một Authentication trong SecurityContext với quyết định cấp quyền thực hiện request như thế nào?
Bạn sẽ thiết kế đường đi của authentication failure để không tạo SecurityContext cho danh tính chưa được xác minh ra sao?
Bạn đánh giá ranh giới giữa chính sách nhận dạng người dùng của identity provider và chính sách phân quyền của ứng dụng như thế nào?
Bạn mô tả DelegatingFilterProxy kết nối servlet filter chain với Spring-managed FilterChainProxy như thế nào?
Bạn phân biệt FilterChainProxy với SecurityFilterChain trong cấu hình và xử lý request ra sao?
Bạn sẽ giải thích HttpSecurity xây dựng các security filters theo từng SecurityFilterChain như thế nào?
Bạn phân tích thứ tự SecurityFilterChain matching khi một ứng dụng có nhiều matcher hoặc endpoints như thế nào?
Bạn sẽ xác định vì sao một request không đi qua authentication filter như dự kiến do securityMatcher không khớp ra sao?
Bạn phân biệt securityMatcher chọn filter chain với requestMatchers áp dụng authorization rules bên trong chain như thế nào?
Bạn sẽ chọn cách cấu hình một filter chain cho browser session và một chain khác cho REST bearer API như thế nào?
Bạn đánh giá rủi ro một endpoint rơi ngoài mọi SecurityFilterChain và bị bỏ qua xác thực ngoài dự kiến ra sao?
Bạn giải thích UsernamePasswordAuthenticationFilter lấy credentials từ form login request và gọi AuthenticationManager như thế nào?
Bạn phân biệt AbstractAuthenticationProcessingFilter với một custom OncePerRequestFilter chỉ đọc header ra sao?
Bạn sẽ thiết kế custom authentication filter mà không tự tái hiện logic quản lý context và success/failure của framework như thế nào?
Bạn mô tả BasicAuthenticationFilter kiểm tra HTTP Basic Authorization header theo lifecycle nào?
Bạn phân biệt HTTP Basic với form login về cách credentials được gửi lại giữa các requests như thế nào?
Bạn sẽ bảo vệ Basic authentication bằng TLS và tránh ghi Authorization header vào logs như thế nào?
Bạn phân tích vì sao ExceptionTranslationFilter không tự thực hiện password verification mà điều phối authentication entry point hoặc access-denied response ra sao?
Bạn phân biệt AuthenticationEntryPoint với AuthenticationFailureHandler theo thời điểm một request bị yêu cầu đăng nhập hoặc một nỗ lực đăng nhập thất bại ra sao?
Bạn sẽ cấu hình LoginUrlAuthenticationEntryPoint cho browser nhưng trả 401 hợp lý cho API như thế nào?
Bạn mô tả vai trò của AuthenticationSuccessHandler sau khi một authentication filter xác thực thành công như thế nào?
Bạn phân biệt SavedRequestAwareAuthenticationSuccessHandler với simple redirect khi người dùng quay lại URL trước đăng nhập ra sao?
Bạn sẽ kiểm tra open redirect risks khi success handler nhận redirect target từ query parameter như thế nào?
Bạn phân tích vì sao AuthenticationFailureHandler không nên trả thông báo riêng tiết lộ rằng một username có tồn tại ra sao?
Bạn sẽ xác định khi nào một failure phải xóa Authentication và SecurityContext cũ trước khi trả response ra sao?
Bạn mô tả cơ chế AnonymousAuthenticationFilter điền Authentication cho request không có người dùng thực sự được xác thực như thế nào?
Bạn phân biệt AnonymousAuthenticationToken với Authentication hợp lệ của user đã đăng nhập dù isAuthenticated có thể true ra sao?
Bạn sẽ kiểm tra anonymous authentication không vượt qua chính sách authenticated access như thế nào?
Bạn giải thích SecurityContextHolder lưu SecurityContext cho code thực thi trong ngữ cảnh hiện tại như thế nào?
Bạn phân biệt SecurityContext và Authentication về đối tượng chứa trạng thái và dữ liệu danh tính ra sao?
Bạn sẽ lựa chọn SecurityContextHolderStrategy phù hợp cho servlet request processing so với xử lý nền như thế nào?
Bạn mô tả vai trò của ThreadLocal trong SecurityContextHolder mặc định và các giới hạn khi chuyển thread ra sao?
Bạn sẽ tránh rò SecurityContext từ request này sang request khác khi threads được tái sử dụng trong thread pool như thế nào?
Bạn phân tích rủi ro dùng MODE_INHERITABLETHREADLOCAL trong executor có workers sống lâu như thế nào?
Bạn sẽ dùng DelegatingSecurityContextRunnable hoặc DelegatingSecurityContextExecutor khi cần truyền context an toàn tới task bất đồng bộ ra sao?
Bạn phân biệt truyền SecurityContext tới @Async worker với việc tự tạo Authentication mới cho hệ thống background như thế nào?
Bạn sẽ thiết kế job hệ thống dùng một danh tính service account hạn chế quyền thay vì giả mạo danh tính user như thế nào?
Bạn mô tả SecurityContextHolderFilter và SecurityContextRepository phối hợp để load context trong servlet request như thế nào?
Bạn phân biệt SecurityContextHolderFilter với SecurityContextPersistenceFilter trong cấu hình Spring Security hiện đại và legacy ra sao?
Bạn sẽ xác định vì sao thiết lập SecurityContextHolder.getContext().setAuthentication thủ công không luôn tự lưu phiên đăng nhập giữa requests ra sao?
Bạn giải thích saveContext của SecurityContextRepository giúp persist một SecurityContext theo chiến lược lưu nào?
Bạn sẽ phân biệt RequestAttributeSecurityContextRepository với HttpSessionSecurityContextRepository theo phạm vi lưu context ra sao?
Bạn phân tích khi nào NullSecurityContextRepository phù hợp với API stateless và hệ quả với form login như thế nào?
Bạn sẽ đảm bảo SecurityContext luôn được cleanup khi filter hoặc handler ném exception như thế nào?
Bạn đánh giá cách security filters và exception handlers ảnh hưởng tới người dùng khi một nỗ lực xác thực chưa hoàn tất như thế nào?
Bạn giải thích UserDetailsService đóng vai trò nào trong DaoAuthenticationProvider khi dùng username/password như thế nào?
Bạn phân biệt UserDetailsService với AuthenticationProvider trong việc nạp account và kiểm tra credentials ra sao?
Bạn sẽ triển khai loadUserByUsername để truy vấn user theo định danh có chuẩn hóa hợp lý như thế nào?
Bạn phân tích nguy cơ thay đổi quy tắc normalize username làm đăng nhập nhầm tài khoản ra sao?
Bạn sẽ sử dụng InMemoryUserDetailsManager trong test hoặc demo mà không lạm dụng cho production như thế nào?
Bạn phân biệt JdbcUserDetailsManager với custom UserDetailsService khi schema tài khoản không theo mặc định ra sao?
Bạn mô tả UserDetails biểu diễn enabled, accountNonLocked, accountNonExpired và credentialsNonExpired ra sao?
Bạn sẽ thiết kế phản hồi khi account bị khóa hoặc chưa kích hoạt mà không lộ thông tin tồn tại tài khoản như thế nào?
Bạn phân tích cách DaoAuthenticationProvider phối hợp UserDetailsPasswordService trong cập nhật mật khẩu hash cũ theo chính sách nào?
Bạn giải thích PasswordEncoder thực hiện matching mật khẩu đã nhập với hash lưu trữ như thế nào?
Bạn phân biệt BCryptPasswordEncoder với DelegatingPasswordEncoder về thuật toán và chính sách chuyển đổi hash ra sao?
Bạn sẽ cấu hình DelegatingPasswordEncoder sử dụng prefix như {bcrypt} để hỗ trợ nâng cấp hash ra sao?
Bạn phân tích vì sao lưu plaintext password hoặc dùng một fast hash không có work factor phù hợp làm tăng rủi ro như thế nào?
Bạn sẽ thiết kế password migration mà không buộc mọi user đặt lại mật khẩu cùng thời điểm như thế nào?
Bạn phân biệt encoder.matches với encoder.encode khi xác thực và lưu mật khẩu mới ra sao?
Bạn sẽ điều chỉnh password hashing cost mà không làm authentication endpoint quá tải khi traffic tăng như thế nào?
Bạn phân tích rủi ro mật khẩu hash bị double-encoded khi luồng đăng ký và thay đổi mật khẩu có hai tầng encode ra sao?
Bạn sẽ thiết kế password reset token có thời hạn, dùng một lần và gắn với account theo cách nào?
Bạn đánh giá những bước cần thực hiện sau khi user reset password để vô hiệu hóa sessions hoặc tokens cũ ra sao?
Bạn sẽ sử dụng compromised-password checking hoặc quy tắc chính sách mật khẩu để giảm nguy cơ credential stuffing như thế nào?
Bạn phân biệt brute-force password guessing với credential stuffing về tín hiệu vận hành và biện pháp bảo vệ như thế nào?
Bạn sẽ đặt rate limit theo account và nguồn request để giảm password spraying mà không làm dễ khóa hàng loạt user ra sao?
Bạn phân tích rủi ro tạo username enumeration qua khác biệt thời gian phản hồi khi user không tồn tại như thế nào?
Bạn sẽ phân biệt user-not-found với bad password ở log nội bộ nhưng trả cùng thông điệp cho client như thế nào?
Bạn mô tả AuthenticationSuccessEvent và AbstractAuthenticationFailureEvent giúp quan sát login attempts như thế nào?
Bạn sẽ cấu hình AuthenticationEventPublisher để thu thập success/failure events phù hợp ra sao?
Bạn phân tích rủi ro dùng authentication events để ghi cả raw credentials vào audit store như thế nào?
Bạn sẽ quyết định khi nào đặt audit login vào AuthenticationSuccessHandler so với lắng nghe authentication events như thế nào?
Bạn đánh giá nếu login success handler thất bại khi ghi log nhưng credentials đã được xác minh thì nên xử lý ra sao?
Bạn sẽ thiết kế cơ chế xác thực passwordless bằng one-time login link mà không mặc định coi nó tương đương MFA như thế nào?
Bạn phân tích rủi ro one-time token bị lộ qua browser history, referrer hoặc email forwarding như thế nào?
Bạn sẽ xây dựng vòng đời one-time token có expiry, one-time consumption và chống replay như thế nào?
Bạn phân biệt email verification khi tạo account với proof of possession mạnh cho một phiên đăng nhập mới như thế nào?
Bạn sẽ chọn thông tin nào đưa vào principal để vừa hỗ trợ authorization vừa tránh lộ PII không cần thiết ra sao?
Bạn đánh giá cách đồng bộ trạng thái account bị vô hiệu hóa trong database với Authentication đã có trong SecurityContext như thế nào?
Bạn giải thích session-based authentication của Spring Security duy trì trạng thái đăng nhập qua HTTP requests như thế nào?
Bạn phân biệt HttpSession với SecurityContextRepository khi quyết định nơi lưu SecurityContext ra sao?
Bạn sẽ xác định khi nào nên dùng SessionCreationPolicy.IF_REQUIRED và khi nào dùng STATELESS như thế nào?
Bạn phân tích rủi ro cấu hình SessionCreationPolicy.STATELESS nhưng đồng thời kỳ vọng form login được giữ qua HttpSession như thế nào?
Bạn sẽ thiết kế remember-me authentication không làm sai kỳ vọng về mức tin cậy của session đăng nhập như thế nào?
Bạn mô tả RememberMeAuthenticationFilter dùng RememberMeServices để khôi phục authentication trong trường hợp nào?
Bạn phân biệt remember-me cookie với session cookie về thời gian sống và nguy cơ đánh cắp ra sao?
Bạn sẽ dùng PersistentTokenBasedRememberMeServices trong tình huống nào cần thu hồi token theo từng thiết bị ra sao?
Bạn phân tích nguy cơ lưu remember-me token không có cơ chế rotation hoặc revocation khi bị đánh cắp ra sao?
Bạn sẽ lựa chọn Secure, HttpOnly và SameSite cho authentication cookies theo môi trường nào?
Bạn mô tả session fixation xảy ra như thế nào khi session ID không được thay đổi sau đăng nhập thành công?
Bạn sẽ cấu hình bảo vệ session fixation bằng cách thay đổi session ID hoặc tạo session mới như thế nào?
Bạn phân biệt changeSessionId với migrateSession theo ảnh hưởng tới session attributes ra sao?
Bạn sẽ xác minh session fixation protection không làm mất trạng thái cần thiết của shopping cart hoặc saved request ra sao?
Bạn giải thích SessionAuthenticationStrategy được sử dụng khi authentication thành công trong những trường hợp nào?
Bạn sẽ thiết kế giới hạn số concurrent sessions của một user theo chính sách nào?
Bạn phân biệt ConcurrentSessionControlAuthenticationStrategy với SessionRegistry trong việc từ chối hoặc theo dõi session ra sao?
Bạn sẽ xác định khi nào dùng HttpSessionEventPublisher để SessionRegistry cập nhật trạng thái session đóng ra sao?
Bạn phân tích vấn đề session concurrency khi ứng dụng chạy nhiều replicas nhưng registry chỉ ở memory ra sao?
Bạn sẽ chọn shared session store hoặc session registry phân tán khi cần kiểm soát nhiều phiên như thế nào?
Bạn đánh giá cách logout ở một thiết bị khác ảnh hưởng các active sessions và remember-me tokens ra sao?
Bạn mô tả SecurityContextLogoutHandler xóa authentication và invalidates session theo cấu hình như thế nào?
Bạn sẽ dùng LogoutHandler và LogoutSuccessHandler theo các trách nhiệm riêng khi thiết kế logout ra sao?
Bạn phân tích rủi ro chỉ xóa cookie phía client nhưng vẫn giữ session hợp lệ ở server ra sao?
Bạn sẽ tổ chức explicit logout trên browser và server-side session invalidation để chặn session reuse như thế nào?
Bạn phân biệt timeout do session idle với absolute session expiration theo chính sách bảo mật như thế nào?
Bạn sẽ xử lý session expired bằng JSON 401 cho API nhưng chuyển login page cho browser theo cách nào?
Bạn đánh giá nguy cơ session data lưu trong Redis tiếp tục hợp lệ dù database account đã bị khóa như thế nào?
Bạn sẽ quyết định khi nào cần reauthenticate user trước thao tác thanh toán hoặc đổi credential ra sao?
Bạn phân tích vì sao CSRF protection quan trọng với browser authentication dùng cookie nhưng có chính sách khác cho token được gửi ở Authorization header ra sao?
Bạn sẽ cấu hình CSRF token cho form login và logout mà không vô hiệu hóa toàn bộ bảo vệ để sửa lỗi 403 như thế nào?
Bạn sẽ xử lý CORS và cookie SameSite khi giao diện web và API nằm ở các origins khác nhau như thế nào?
Bạn phân biệt session replication với session persistence và điều gì xảy ra khi một server restart ra sao?
Bạn sẽ thiết kế strategy refresh authentication authorities cho session có nhóm quyền thay đổi giữa phiên như thế nào?
Bạn đánh giá cách kiểm thử session fixation, concurrent sessions và logout revocation với nhiều browser clients như thế nào?
Bạn giải thích LDAP bind authentication và password comparison khác nhau như thế nào khi tích hợp Spring Security với LDAP?
Bạn sẽ quyết định khi nào dùng LdapBindAuthenticationManagerFactory để dựng AuthenticationManager cho LDAP như thế nào?
Bạn phân biệt LdapBindAuthenticationManagerFactory với LdapPasswordComparisonAuthenticationManagerFactory theo cách kiểm tra mật khẩu ra sao?
Bạn mô tả vai trò của DefaultSpringSecurityContextSource trong cấu hình URL và base DN của LDAP như thế nào?
Bạn sẽ sử dụng search filter an toàn để tìm user DN theo username mà không ghép chuỗi LDAP filter tùy tiện như thế nào?
Bạn phân tích nguy cơ LDAP injection khi username chứa các ký tự đặc biệt làm thay đổi điều kiện tìm kiếm ra sao?
Bạn sẽ chọn userDnPatterns hay userSearchBase và userSearchFilter trong trường hợp nào?
Bạn đánh giá ảnh hưởng của service account search permissions tới khả năng tìm user trước bind như thế nào?
Bạn sẽ ánh xạ LDAP group membership thành GrantedAuthority bằng LdapAuthoritiesPopulator theo chính sách nào?
Bạn phân biệt group role trong LDAP với application permission cần kiểm tra theo business domain ra sao?
Bạn phân tích rủi ro attribute memberOf không có hoặc khác semantics giữa OpenLDAP và Active Directory như thế nào?
Bạn sẽ xử lý các nhóm lồng nhau hoặc tên group trùng nhau ở nhiều OU khi tạo authorities như thế nào?
Bạn sẽ kiểm tra LDAP server certificate trước khi thực hiện bind với user credentials qua LDAPS hoặc StartTLS ra sao?
Bạn phân tích vì sao một fallback về kết nối LDAP plaintext sau TLS failure là không an toàn ra sao?
Bạn sẽ thiết kế connection timeout và authentication error handling khi LDAP server bị outage như thế nào?
Bạn phân biệt invalid credentials với connection failure khi provider trả lỗi và khi audit login attempts ra sao?
Bạn sẽ giới hạn số lượt bind authentication để tránh LDAP account lockout khi có credential stuffing ra sao?
Bạn phân tích nguy cơ dùng pooled context của user A cho xác thực của user B do quản lý connection sai ra sao?
Bạn sẽ xác định thời điểm refresh LDAP group authorities trong active session hoặc bearer token như thế nào?
Bạn đánh giá chiến lược fail-closed khi LDAP group lookup thất bại nhưng user bind đã thành công ra sao?
Bạn sẽ kiểm thử LDAP authentication với test directory và user DN chứa ký tự đặc biệt như thế nào?
Bạn phân biệt LDAP authentication qua Spring Security với việc dùng Spring LDAP LdapTemplate để truy vấn nghiệp vụ ra sao?
Bạn sẽ tổ chức cấu hình nhiều LDAP domains mà không chọn sai authentication provider dựa trên input chưa tin cậy như thế nào?
Bạn phân tích rủi ro trả chi tiết LDAP bind error codes cho client dẫn tới lộ trạng thái account ra sao?
Bạn sẽ xây dựng integration test khi server đổi mật khẩu tài khoản, thu hồi group membership hoặc hết hạn certificate ra sao?
Bạn giải thích OAuth2 Login trong Spring Security xác thực người dùng thông qua Authorization Server hoặc OpenID Provider như thế nào?
Bạn phân biệt OAuth 2.0 authorization với OpenID Connect authentication về những thông tin xác định danh tính ra sao?
Bạn mô tả authorization code flow qua browser redirect và callback trong oauth2Login như thế nào?
Bạn sẽ xác định vai trò của ClientRegistrationRepository khi ứng dụng hỗ trợ nhiều identity providers như thế nào?
Bạn phân biệt ClientRegistration với OAuth2AuthorizedClient về cấu hình provider và tokens của một lần ủy quyền ra sao?
Bạn sẽ dùng OAuth2AuthorizationRequestRedirectFilter để bắt đầu login flow dựa trên registration nào?
Bạn mô tả OAuth2LoginAuthenticationFilter xử lý callback chứa authorization code theo luồng nào?
Bạn phân tích vai trò của state parameter để phòng ngừa login CSRF và response injection như thế nào?
Bạn sẽ xác minh state từ callback khớp authorization request trước khi hoàn tất authentication như thế nào?
Bạn giải thích PKCE hỗ trợ bảo vệ authorization code flow khỏi code interception như thế nào?
Bạn sẽ quyết định khi nào bắt buộc PKCE dù ứng dụng là confidential client có client secret ra sao?
Bạn phân biệt redirect URI đã đăng ký với redirect URI lấy từ request và nguy cơ open redirect như thế nào?
Bạn sẽ bảo vệ client secret trong môi trường server và tránh lộ qua logs hoặc frontend bundles như thế nào?
Bạn mô tả OIDC ID token chứa các claims như issuer, subject, audience, expiration và nonce như thế nào?
Bạn phân biệt ID token với OAuth2 access token về mục đích sử dụng ở ứng dụng client ra sao?
Bạn sẽ xác minh issuer, audience, signature và token lifetime trước khi tin ID token như thế nào?
Bạn giải thích nonce giúp ràng buộc ID token với authorization request để giảm replay risk như thế nào?
Bạn sẽ thiết kế account linking khi cùng người dùng đăng nhập qua hai identity providers khác nhau theo nguyên tắc nào?
Bạn phân tích rủi ro đồng nhất user chỉ dựa vào email chưa được verify hoặc có thể thay đổi như thế nào?
Bạn sẽ dùng cặp issuer và subject của OIDC để định danh tài khoản bên ngoài ổn định như thế nào?
Bạn mô tả OidcUserService và OAuth2UserService tham gia nạp attributes của người dùng sau login như thế nào?
Bạn phân biệt ID token claims với UserInfo response khi xác định attributes và authorities ra sao?
Bạn sẽ lựa chọn OAuth2UserService phù hợp khi identity provider có user info format khác chuẩn như thế nào?
Bạn phân tích nguy cơ tin UserInfo email hoặc groups mà không kiểm tra nguồn và mức xác minh của claims như thế nào?
Bạn sẽ ánh xạ OidcUser hoặc OAuth2User thành principal ứng dụng mà không lưu access token vào business DTO ra sao?
Bạn đánh giá khi nào cần dùng GrantedAuthoritiesMapper để chuyển external authorities sang application authorities ra sao?
Bạn sẽ tổ chức logout giữa local Spring session và OIDC provider theo kỳ vọng nào?
Bạn phân biệt local logout với RP-initiated logout hoặc front-channel logout do provider hỗ trợ theo tính năng nào?
Bạn sẽ thiết kế logic khi access token hết hạn nhưng browser vẫn còn local authenticated session như thế nào?
Bạn phân tích vì sao refresh token cần lưu trữ an toàn và không được gửi vô điều kiện cho browser clients ra sao?
Bạn sẽ xác định vòng đời OAuth2AuthorizedClientService khi ứng dụng lưu tokens cho outbound API calls ra sao?
Bạn mô tả cách xử lý user hủy quyền cấp phép tại IdP trong lúc Spring session vẫn tồn tại ra sao?
Bạn sẽ thiết kế callback error handling khi user từ chối consent hoặc provider trả lỗi tạm thời như thế nào?
Bạn phân tích rủi ro OAuth2 login bị trộn session giữa hai người dùng khi browser đồng thời bắt đầu hai login flows ra sao?
Bạn sẽ cấu hình nhiều SecurityFilterChain cho OIDC browser login và bearer API mà không nhầm endpoint callbacks như thế nào?
Bạn đánh giá khi nào application nên nhận biết authentication assurance như auth_time hoặc amr claims theo chính sách provider như thế nào?
Bạn sẽ kiểm tra token issuer discovery metadata và JWK rotation khi OIDC provider đổi signing keys ra sao?
Bạn sẽ tổ chức audit OIDC login có correlation ID mà không ghi authorization code hoặc id_token ra sao?
Bạn phân tích lý do OAuth2 access token từ provider A không được tự động chấp nhận bởi API tin provider B như thế nào?
Bạn sẽ kiểm thử state mismatch, invalid nonce, expired ID token và wrong issuer bằng test OIDC provider như thế nào?
Bạn giải thích OAuth2 Resource Server trong Spring Security xác thực bearer token khác với oauth2Login dùng browser session như thế nào?
Bạn phân biệt JWT bearer authentication với opaque token introspection theo cách server xác minh token ra sao?
Bạn mô tả BearerTokenAuthenticationFilter tìm token từ HTTP request và chuyển cho authentication manager như thế nào?
Bạn sẽ dùng JwtAuthenticationProvider và JwtDecoder khi API cần kiểm tra chữ ký và claims của JWT như thế nào?
Bạn phân biệt JwtDecoder dùng JWK Set với lựa chọn thuật toán tin cậy theo chính sách bảo mật như thế nào?
Bạn sẽ cấu hình issuer-uri và audience validation để không nhận token phát hành cho một ứng dụng khác như thế nào?
Bạn phân tích nguy cơ token substitution khi service chỉ kiểm tra chữ ký mà không kiểm tra issuer hoặc audience ra sao?
Bạn sẽ xác minh expiration, not-before và clock skew policy với JWT authentication như thế nào?
Bạn phân biệt JwtAuthenticationToken với OAuth2AuthenticationToken của một OAuth2 login thành công ra sao?
Bạn sẽ ánh xạ scope và role claims sang GrantedAuthority bằng JwtAuthenticationConverter như thế nào?
Bạn phân tích vì sao scope có trong access token không đồng nghĩa user được phép thao tác với mọi bản ghi nghiệp vụ ra sao?
Bạn sẽ xây dựng OAuth2TokenValidator bổ sung để kiểm tra token constraints riêng của resource server như thế nào?
Bạn mô tả OpaqueTokenIntrospector gọi authorization server để kiểm tra active token và lấy attributes như thế nào?
Bạn phân biệt caching introspection responses với yêu cầu thu hồi quyền nhanh và nguy cơ token revoked vẫn được dùng ra sao?
Bạn sẽ thiết kế timeout, backoff và fail-closed khi introspection endpoint không sẵn sàng như thế nào?
Bạn phân tích rủi ro log bearer token đầy đủ khi một request bị từ chối xác thực ra sao?
Bạn sẽ xác định nguồn lấy bearer token được phép để tránh nhận token ở query string và bị lộ qua logs như thế nào?
Bạn phân biệt token authentication không cần HttpSession với token được lưu trong browser cookie theo tác động CSRF như thế nào?
Bạn sẽ xử lý HTTP 401 và WWW-Authenticate header cho token invalid hoặc expired theo chuẩn nào?
Bạn đánh giá trường hợp JWT được xác minh hợp lệ nhưng user account đã bị khóa ở database có cần kiểm tra bổ sung như thế nào?
Bạn sẽ thiết kế revocation strategy cho JWT tự xác minh không có khả năng thu hồi tức thời mặc định như thế nào?
Bạn phân tích rủi ro sử dụng refresh token như access token tại resource server theo thiết kế sai như thế nào?
Bạn sẽ thiết kế AuthenticationManagerResolver theo issuer hoặc tenant nhưng chỉ chọn trong allowlist các issuers tin cậy như thế nào?
Bạn phân biệt service-to-service client credentials token với user-delegated token khi xây dựng Authentication principal ra sao?
Bạn sẽ xác định cách đồng bộ thời gian giữa API servers và identity provider để giảm false token expiration như thế nào?
Bạn sẽ viết test API không nhận JWT thiếu audience hoặc sai signature dù có authorities đúng ra sao?
Bạn đánh giá khi nào nên tách OAuth2 Resource Server bearer authentication khỏi session-based browser login ở các URL khác nhau như thế nào?
Bạn giải thích passkey dựa trên WebAuthn thay thế việc gửi mật khẩu bằng một cuộc kiểm tra mật mã public-key như thế nào?
Bạn phân biệt passkey authentication với password-based login theo khả năng chống phishing và quản lý credential ra sao?
Bạn sẽ xác định yêu cầu Relying Party ID và origin khi triển khai WebAuthn trong một Spring Security application như thế nào?
Bạn mô tả quá trình registration challenge được tạo, lưu và kiểm tra khi thêm passkey mới ra sao?
Bạn sẽ ngăn registration challenge bị dùng lại hoặc gắn sai vào một user session như thế nào?
Bạn phân biệt attestation với assertion trong đăng ký và xác thực WebAuthn như thế nào?
Bạn sẽ lựa chọn khi nào cần đánh giá attestation trust thay vì mặc định chấp nhận loại authenticator phù hợp chính sách ra sao?
Bạn phân tích vì sao server chỉ lưu public-key credential và metadata chứ không lưu private key của authenticator như thế nào?
Bạn sẽ tổ chức kho credential ID, public key và user handle theo account để hỗ trợ nhiều thiết bị như thế nào?
Bạn mô tả cách assertion signature chứng minh quyền sở hữu credential mà không phải gửi secret từ client ra sao?
Bạn sẽ kiểm tra WebAuthn challenge, origin, RP ID hash và user presence/user verification flags như thế nào?
Bạn phân biệt user presence với user verification trong một WebAuthn assertion theo assurance requirement như thế nào?
Bạn sẽ thiết kế policy yêu cầu user verification cho hành động rủi ro cao trong trường hợp nào?
Bạn phân tích nguy cơ chấp nhận assertion có origin không khớp dẫn tới bypass ranh giới Relying Party như thế nào?
Bạn sẽ đánh giá ý nghĩa của signature counter khi authenticator đồng bộ hoặc counter không tăng theo dự đoán như thế nào?
Bạn phân biệt discoverable credentials với non-discoverable credentials khi hỗ trợ username-less login ra sao?
Bạn sẽ thiết kế luồng đăng nhập không nhập username trước nhưng vẫn ánh xạ credential về đúng user như thế nào?
Bạn phân tích rủi ro đăng ký passkey vào tài khoản đã bị session hijacking khi server không yêu cầu reauthentication ra sao?
Bạn sẽ yêu cầu step-up hoặc xác nhận lại danh tính trước khi thêm hoặc xóa passkey theo chính sách nào?
Bạn sẽ tổ chức đăng ký passkey trên nhiều thiết bị và phục hồi account khi người dùng mất hết thiết bị ra sao?
Bạn phân biệt passkey được đồng bộ giữa thiết bị với credential gắn chặt thiết bị theo threat model như thế nào?
Bạn sẽ xác định khi nào một fallback password hoặc recovery flow làm suy yếu lợi ích chống phishing của passkey như thế nào?
Bạn phân tích rủi ro WebAuthn challenge không có hạn sử dụng hoặc không được liên kết với phiên xác thực ra sao?
Bạn sẽ kiểm thử sai origin, challenge reuse, invalid signature và credential ID không tồn tại bằng cách nào?
Bạn sẽ đánh giá cách tích hợp passkey vào nhiều SecurityFilterChain và authentication success/failure flow hiện có như thế nào?
Bạn phân biệt hai yếu tố xác thực độc lập với hai bước kiểm tra dùng cùng một thiết bị hoặc cùng một secret như thế nào?
Bạn sẽ thiết kế MFA policy dựa trên mức độ rủi ro của tài khoản và thao tác chứ không chỉ dựa vào tên role ra sao?
Bạn phân biệt TOTP với email one-time code và WebAuthn theo mức kháng phishing và phụ thuộc ngoài như thế nào?
Bạn sẽ quản lý shared secret TOTP ở server với encryption và rotation theo nguyên tắc nào?
Bạn phân tích nguy cơ OTP được chấp nhận nhiều lần trong cùng time window nếu server không có chống replay ra sao?
Bạn sẽ thiết kế giới hạn số lần thử OTP và khóa tạm mà không làm attacker dễ gây denial-of-service cho tài khoản như thế nào?
Bạn phân biệt verification of second factor với việc tự nâng authorities mà chưa ghi nhận assurance của authentication như thế nào?
Bạn sẽ xây dựng MFA step-up khi user thay password hoặc thiết lập phương thức thanh toán theo policy nào?
Bạn sẽ xác định cách lưu trạng thái hoàn tất factor để một session chưa đủ MFA không truy cập endpoint yêu cầu assurance cao ra sao?
Bạn phân tích rủi ro gắn permanent authority MFA_VERIFIED cho tài khoản khiến các sessions chưa hoàn tất MFA cũng được coi là đủ điều kiện như thế nào?
Bạn sẽ thiết kế recovery codes một lần, lưu dạng hash và vô hiệu hóa sau sử dụng theo cách nào?
Bạn phân biệt backup code recovery với việc bỏ qua MFA hoàn toàn khi helpdesk can thiệp vào account như thế nào?
Bạn sẽ xác định cách xử lý người dùng bỏ dở bước thứ hai mà không để lại một fully authenticated session ngoài ý muốn ra sao?
Bạn đánh giá việc thay đổi phương thức MFA có cần xóa hoặc hạ cấp các sessions hiện tại như thế nào?
Bạn sẽ kiểm thử step-up yêu cầu đủ factor trên tất cả các đường gọi kể cả API và background actions ra sao?
Bạn giải thích Spring Security authentication testing nên tách unit test provider với integration test filter chain theo tiêu chí nào?
Bạn sẽ dùng spring-security-test để giả lập principal nhưng vẫn phân biệt giả lập context với xác thực credentials thật như thế nào?
Bạn mô tả vai trò của @WithMockUser trong kiểm thử authorization mà không chứng minh login flow đã chạy ra sao?
Bạn sẽ lựa chọn @WithUserDetails khi test cần custom UserDetails từ UserDetailsService như thế nào?
Bạn phân tích vì sao một @WithMockUser test có thể PASS dù UsernamePasswordAuthenticationFilter hoặc password encoder bị cấu hình sai ra sao?
Bạn sẽ dùng MockMvc và springSecurity() để kiểm thử form login end-to-end trong SecurityFilterChain như thế nào?
Bạn sẽ xác minh formLogin().user(...) và password(...) thành công hoặc thất bại trong các test requests ra sao?
Bạn sẽ kiểm tra CSRF token khi gửi POST tới login endpoint trong MockMvc theo cấu hình thực tế như thế nào?
Bạn phân biệt test form login redirect thành công với test SecurityContext đã được lưu và dùng lại cho request tiếp theo như thế nào?
Bạn sẽ thiết kế integration test đăng nhập xong truy cập resource cần authenticated session rồi logout như thế nào?
Bạn phân tích rủi ro test chỉ assert HTTP 302 mà không xác minh principal, session hoặc security context ra sao?
Bạn sẽ kiểm tra SecurityContextHolder không rò authentication từ test case trước sang case sau như thế nào?
Bạn sẽ test custom AuthenticationProvider cả loại Authentication được hỗ trợ và loại bị từ chối ra sao?
Bạn sẽ xác minh ProviderManager không fallback sang provider yếu hơn khi provider mạnh báo credentials sai như thế nào?
Bạn phân tích trường hợp filter chain phù hợp không được chọn khiến authentication filter không chạy trong MockMvc như thế nào?
Bạn sẽ kiểm tra unauthenticated API nhận 401 thay vì bị redirect tới login page khi cấu hình nhiều chains ra sao?
Bạn sẽ test lỗi authentication thất bại trả thông tin thống nhất cho user không tồn tại và sai password ra sao?
Bạn sẽ sử dụng Testcontainers cho LDAP hoặc fake identity provider khi cần xác minh integration authentication thật ra sao?
Bạn sẽ tạo integration test với OIDC test provider để kiểm tra state, nonce và ID token signature như thế nào?
Bạn phân tích vì sao test OAuth2 Login bằng mocked principal không đủ xác minh redirect URI, code exchange và callback validation ra sao?
Bạn sẽ kiểm tra OAuth2 Resource Server từ chối JWT hết hạn, sai audience và issuer không tin cậy ra sao?
Bạn sẽ dùng jwt() trong security test để kiểm tra authorization của request nhưng không nhầm với test JwtDecoder thật như thế nào?
Bạn sẽ xác minh BearerTokenAuthenticationFilter không nhận token từ nguồn không được phép và không log token ra sao?
Bạn phân tích cách test session fixation bằng cách so sánh session identifier trước và sau login thành công như thế nào?
Bạn sẽ tạo test đồng thời hai phiên để kiểm tra giới hạn concurrent sessions và SessionRegistry ra sao?
Bạn sẽ kiểm thử invalidation của remember-me token sau logout hoặc password reset theo yêu cầu nào?
Bạn đánh giá cách test passkey WebAuthn challenge, RP ID, origin và assertion verification không phụ thuộc thiết bị thật như thế nào?
Bạn sẽ kiểm thử TOTP replay, recovery code one-time consumption và MFA step-up bằng một clock kiểm soát như thế nào?
Bạn phân tích vì sao test MFA chỉ kiểm tra OTP đúng nhưng không thử bỏ qua bước thứ hai là chưa đầy đủ như thế nào?
Bạn sẽ thiết kế security tests cho WebFlux bằng WebTestClient và mock authentication theo reactive context ra sao?
Bạn phân biệt SecurityContextHolder với ReactiveSecurityContextHolder khi kiểm thử authentication qua Reactor chain như thế nào?
Bạn sẽ kiểm thử authentication context vẫn đúng khi ứng dụng dùng @Async và DelegatingSecurityContextExecutor ra sao?
Bạn sẽ xác minh audit events không chứa raw password, OTP hoặc bearer token ngay cả khi login thất bại như thế nào?
Bạn sẽ thiết kế metrics với Micrometer cho login success, login failure, MFA challenge và authentication latency như thế nào?
Bạn phân tích rủi ro đặt username, email hoặc token vào metric labels làm lộ thông tin và tăng cardinality ra sao?
Bạn sẽ thiết lập alert cho password spraying, anomalous login rates và JWT validation failures theo những tín hiệu nào?
Bạn sẽ xây dựng runbook phân biệt password encoder mismatch, session persistence failure và provider unavailability như thế nào?
Bạn đánh giá cách theo dõi p95 login latency mà tách database, LDAP, OIDC code exchange và password hashing cost như thế nào?
Bạn sẽ đặt readiness khác liveness khi identity provider tạm không sẵn sàng nhưng ứng dụng vẫn có các endpoints công khai như thế nào?
Nếu authentication request có token đúng loại nhưng ProviderManager báo ProviderNotFoundException, bạn sẽ chẩn đoán provider registration và supports như thế nào?
Nếu user login thành công nhưng request sau mất Authentication, bạn sẽ kiểm tra SecurityContextRepository và saveContext như thế nào?
Nếu SecurityContext bị rò sang user khác khi dùng executor, bạn sẽ xác minh cleanup và context propagation ra sao?
Nếu browser truy cập API nhận 302 tới form login thay vì 401, bạn sẽ kiểm tra matching SecurityFilterChain và entry point như thế nào?
Nếu user nhập đúng mật khẩu nhưng DaoAuthenticationProvider luôn báo bad credentials, bạn sẽ kiểm tra PasswordEncoder, UserDetails và hash format ra sao?
Nếu sau login session ID không đổi khiến kiểm thử session fixation thất bại, bạn sẽ chỉnh session authentication strategy như thế nào?
Nếu logout chỉ xóa cookie còn HttpSession vẫn hợp lệ trên server, bạn sẽ sửa cơ chế invalidation như thế nào?
Nếu account đã bị khóa nhưng remember-me cookie vẫn tạo Authentication, bạn sẽ thiết kế account-state validation ra sao?
Nếu LDAP server ngừng hoạt động và ứng dụng trả lỗi sai mật khẩu cho mọi user, bạn sẽ phân loại lỗi provider và xử lý fail-closed như thế nào?
Nếu group membership từ LDAP thay đổi mà users đã đăng nhập vẫn giữ authorities cũ, bạn sẽ đặt chính sách refresh theo mức rủi ro ra sao?
Nếu OIDC callback có state mismatch nhưng client cố retry, bạn sẽ điều tra session và chống login CSRF như thế nào?
Nếu người dùng có cùng email ở hai OIDC issuers và bị liên kết nhầm account, bạn sẽ đổi quy tắc identity mapping như thế nào?
Nếu JWT signature hợp lệ nhưng audience không thuộc API này, bạn sẽ bổ sung validator và test negative case như thế nào?
Nếu bearer authentication trở thành stateful do cookie/session ngoài ý muốn, bạn sẽ kiểm tra SessionCreationPolicy và filter chains ra sao?
Nếu một passkey assertion có origin khác origin đã đăng ký, bạn sẽ xử lý và log sự kiện an toàn như thế nào?
Nếu user mất thiết bị passkey duy nhất, bạn sẽ thiết kế recovery có xác minh danh tính mà không tạo đường bypass dễ bị chiếm đoạt ra sao?
Nếu một OTP có thể dùng lại hai lần trong cùng time window, bạn sẽ thêm chống replay và kiểm thử như thế nào?
Nếu user chưa hoàn tất MFA nhưng vẫn gọi được endpoint đổi thông tin thanh toán, bạn sẽ kiểm tra session assurance và access rules ra sao?
Nếu test @WithMockUser PASS nhưng đăng nhập thực qua OAuth2 thất bại, bạn sẽ bổ sung integration tests vào những bước nào?
Nếu cần thiết kế xác thực cho Spring Security production có browser, API, LDAP, OIDC, passkey và MFA, bạn sẽ tổ chức providers, filter chains, SecurityContext, session, tests và observability như thế nào?

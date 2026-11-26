Bạn giải thích Spring Security cung cấp những lớp bảo vệ nào cho một ứng dụng Spring web?
Bạn phân biệt authentication và authorization theo thứ tự kiểm tra và kết quả bảo vệ tài nguyên như thế nào?
Bạn sẽ xác định ranh giới trách nhiệm giữa Spring Security, application service và identity provider ra sao?
Bạn mô tả cơ chế mặc định của Spring Boot khi có spring-boot-starter-security nhưng chưa khai báo SecurityFilterChain riêng như thế nào?
Bạn sẽ quyết định khi nào cần custom SecurityFilterChain thay vì giữ auto-configuration mặc định ra sao?
Bạn phân biệt bảo vệ request HTTP với bảo vệ một lời gọi service không đi qua HTTP như thế nào?
Bạn sẽ giải thích vì sao dependency Spring Security có mặt trong classpath chưa bảo đảm mọi endpoint đều được bảo vệ đúng chính sách ra sao?
Bạn phân biệt các mối đe dọa xác thực giả mạo, truy cập trái phép và đánh cắp phiên ở mức hệ thống như thế nào?
Bạn sẽ lập threat model cơ bản cho một REST API có người dùng và quyền quản trị theo các bước nào?
Bạn phân tích nguy cơ dựa vào frontend ẩn nút chức năng thay vì thực thi authorization trên server như thế nào?
Bạn sẽ xác định các endpoint công khai, endpoint cần đăng nhập và endpoint đòi hỏi quyền cao trong một ứng dụng ra sao?
Bạn mô tả nguyên tắc deny by default được triển khai trong Spring Security như thế nào?
Bạn sẽ thiết kế cấu hình tối thiểu để các endpoint chưa được liệt kê không vô tình trở thành public ra sao?
Bạn phân biệt permitAll với việc bỏ qua hoàn toàn Spring Security filter chain về hệ quả bảo mật như thế nào?
Bạn sẽ quyết định khi nào tài nguyên tĩnh nên được permitAll thay vì loại khỏi security filters như thế nào?
Bạn mô tả vai trò của @EnableWebSecurity trong ứng dụng dùng cấu hình Java so với cấu hình tự động của Spring Boot như thế nào?
Bạn sẽ dùng @Bean SecurityFilterChain để cấu hình bảo vệ cho một nhóm request theo cách nào?
Bạn phân biệt HttpSecurity là công cụ build cấu hình với SecurityFilterChain là kết quả áp dụng tại runtime như thế nào?
Bạn sẽ tổ chức security configuration thành những bean có trách nhiệm rõ ràng thay vì một class chứa mọi policy ra sao?
Bạn phân tích nguy cơ một cấu hình kiểm thử nới lỏng SecurityFilterChain bị nạp nhầm trong production như thế nào?
Bạn sẽ xác định sự khác nhau giữa Spring MVC servlet security và Spring WebFlux reactive security trong cấu hình như thế nào?
Bạn phân biệt SecurityFilterChain của servlet với SecurityWebFilterChain của WebFlux theo cơ chế xử lý ra sao?
Bạn sẽ chọn bảo vệ HTTP endpoint tại lớp filter và bảo vệ thao tác nghiệp vụ tại method level theo tiêu chí nào?
Bạn đánh giá khi nào việc kết hợp request security và method security là phòng vệ chiều sâu thay vì lặp logic không cần thiết như thế nào?
Bạn sẽ tổ chức roles, permissions và ownership policies sao cho kiểm thử được và không phụ thuộc tên endpoint ra sao?
Bạn phân tích rủi ro cấp ROLE_ADMIN cho service account chỉ vì tiện cấu hình một integration test như thế nào?
Bạn sẽ tách secrets của authentication khỏi application.yml được commit vào repository như thế nào?
Bạn sẽ thiết kế chính sách bật TLS và bảo vệ cookies cùng Spring Security trong môi trường reverse proxy ra sao?
Bạn mô tả vai trò của SecurityProperties và cấu hình ứng dụng khi bổ sung Spring Security vào Spring Boot như thế nào?
Bạn sẽ xác định đâu là default behavior của framework và đâu là rule do ứng dụng bổ sung bằng test ra sao?
Bạn đánh giá khi nào thay đổi phiên bản Spring Security có thể làm thay đổi DSL hoặc default security policy như thế nào?
Bạn sẽ lập checklist kiểm tra security configuration sau mỗi nâng cấp Spring Boot theo những tiêu chí nào?
Bạn phân tích vì sao việc trả HTTP 200 cho health endpoint không chứng minh các API khác đã được phân quyền như thế nào?
Bạn sẽ giải thích trách nhiệm của security team và developer đối với public routes và quyền trên dữ liệu như thế nào?
Bạn mô tả DelegatingFilterProxy chuyển một HTTP request từ servlet container tới Spring-managed security filters như thế nào?
Bạn phân biệt FilterChainProxy với từng SecurityFilterChain trong quá trình chọn policy cho một request ra sao?
Bạn giải thích HttpSecurity cấu hình các bộ lọc Spring Security theo cơ chế nào?
Bạn sẽ xác định cách nhiều SecurityFilterChain beans được chọn theo thứ tự ưu tiên khi request tới ứng dụng như thế nào?
Bạn mô tả vai trò của @Order khi cấu hình nhiều SecurityFilterChain có thể cùng khớp một request ra sao?
Bạn phân biệt securityMatcher với requestMatchers của authorizeHttpRequests theo phạm vi ảnh hưởng như thế nào?
Bạn sẽ bảo vệ /api/** bằng bearer authentication và /web/** bằng session login với hai filter chains ra sao?
Bạn phân tích rủi ro request không khớp bất kỳ SecurityFilterChain nào nên không được filter xử lý như thế nào?
Bạn sẽ xác định lý do filter chain dành cho API không chạy do matcher bị cấu hình sai như thế nào?
Bạn phân biệt thứ tự security request matchers với thứ tự rules bên trong một authorizeHttpRequests chain ra sao?
Bạn sẽ thiết kế một fallback SecurityFilterChain để xử lý request chưa có chính sách cụ thể như thế nào?
Bạn mô tả cách FilterChainProxy ủy quyền cho servlet FilterChain tiếp theo sau khi security checks hoàn tất ra sao?
Bạn sẽ xác định vị trí của một custom filter so với UsernamePasswordAuthenticationFilter hoặc BasicAuthenticationFilter theo yêu cầu nào?
Bạn phân biệt addFilterBefore, addFilterAfter và addFilterAt của HttpSecurity khi đặt custom filter như thế nào?
Bạn sẽ đánh giá rủi ro thêm custom filter không được Spring quản lý dependencies hoặc lifecycle đúng cách ra sao?
Bạn phân tích vấn đề filter vừa được đăng ký trong servlet container vừa được thêm vào SecurityFilterChain dẫn đến thực thi trùng như thế nào?
Bạn sẽ quyết định khi nào dùng OncePerRequestFilter để kiểm tra dữ liệu HTTP trước authentication như thế nào?
Bạn mô tả SecurityContextHolderFilter tham gia vào vòng đời request và SecurityContext như thế nào?
Bạn phân biệt SecurityContextHolderFilter với SecurityContextPersistenceFilter ở các cấu hình hoặc phiên bản Spring Security như thế nào?
Bạn sẽ chẩn đoán request đến controller nhưng SecurityContextHolder.getContext().getAuthentication() không đúng kỳ vọng ra sao?
Bạn mô tả AnonymousAuthenticationFilter bổ sung danh tính anonymous trong trường hợp nào?
Bạn phân biệt AnonymousAuthenticationToken với authenticated user trong một authorization expression như thế nào?
Bạn sẽ xác định vì sao isAuthenticated có thể gây hiểu nhầm khi code tự kiểm tra anonymous token như thế nào?
Bạn giải thích ExceptionTranslationFilter xử lý AuthenticationException hoặc AccessDeniedException trong chuỗi filter như thế nào?
Bạn phân biệt AuthenticationEntryPoint với AccessDeniedHandler khi quyết định trả 401 hoặc 403 ra sao?
Bạn sẽ cấu hình 401 JSON cho unauthenticated REST requests mà không redirect sang HTML login page như thế nào?
Bạn mô tả vai trò của AuthenticationFailureHandler với lỗi phát sinh trực tiếp trong quá trình login như thế nào?
Bạn sẽ thiết kế error handling không hiển thị stack trace hoặc thông tin tài khoản nhạy cảm trên HTTP response như thế nào?
Bạn phân tích vì sao exception bị bắt và chuyển thành HTTP 200 trong custom filter có thể che lỗi xác thực ra sao?
Bạn sẽ sử dụng debug logging của Spring Security để tìm filter chain đã được chọn mà không bật logging chứa credentials như thế nào?
Bạn sẽ xác định vì sao request chỉ gặp 403 trên HTTP OPTIONS preflight trước khi đi đến custom authentication filter ra sao?
Bạn phân biệt StrictHttpFirewall với path matching thông thường khi có encoded path hoặc URL bất thường như thế nào?
Bạn sẽ thiết kế kiểm thử cho những đường dẫn có trailing slash, ký tự encoded và method khác nhau để tránh bypass rule ra sao?
Bạn phân tích rủi ro reverse proxy rewrite URL khác với path mà SecurityFilterChain đang thực sự so khớp như thế nào?
Bạn sẽ kiểm tra một HTTP request đi qua các filters đúng thứ tự khi có nhiều custom filters như thế nào?
Bạn giải thích Authentication mô tả những thông tin nào trong phiên xử lý bảo mật của Spring Security?
Bạn phân biệt principal, credentials và GrantedAuthority trong một Authentication object như thế nào?
Bạn sẽ giải thích cách AuthenticationManager kiểm tra một yêu cầu đăng nhập và trả Authentication đã xác thực như thế nào?
Bạn phân biệt AuthenticationManager với AuthenticationProvider trong phối hợp nhiều cơ chế xác thực ra sao?
Bạn sẽ xác định vai trò của ProviderManager khi có nhiều AuthenticationProvider beans trong một hệ thống như thế nào?
Bạn mô tả AuthenticationProvider.supports ảnh hưởng cách chọn provider cho từng loại token ra sao?
Bạn phân tích rủi ro tự tạo Authentication.isAuthenticated=true từ input client mà không đi qua kiểm tra credentials như thế nào?
Bạn sẽ dùng UserDetailsService để nạp trạng thái account và authorities cho đăng nhập username/password như thế nào?
Bạn phân biệt UserDetailsService với repository user nghiệp vụ khi ứng dụng có nhiều thuộc tính không cần cho xác thực ra sao?
Bạn sẽ cấu hình DaoAuthenticationProvider cùng PasswordEncoder cho đăng nhập thông thường ra sao?
Bạn mô tả PasswordEncoder.matches kiểm chứng mật khẩu với hash đã lưu như thế nào?
Bạn phân biệt BCryptPasswordEncoder với DelegatingPasswordEncoder về chính sách lựa chọn và nâng cấp thuật toán ra sao?
Bạn sẽ quyết định cách migrate password hashes cũ khi sử dụng DelegatingPasswordEncoder như thế nào?
Bạn phân tích rủi ro lưu plaintext passwords hoặc log password input ngay cả trong môi trường staging như thế nào?
Bạn sẽ xử lý trạng thái account disabled, locked hoặc expired trong UserDetails theo chính sách nào?
Bạn phân biệt BadCredentialsException và AuthenticationServiceException để quyết định response và cảnh báo vận hành như thế nào?
Bạn sẽ thiết kế thông báo lỗi đăng nhập không tiết lộ tài khoản có tồn tại hay không ra sao?
Bạn mô tả UsernamePasswordAuthenticationFilter tham gia form login ở giai đoạn nào?
Bạn phân biệt formLogin với httpBasic theo cách client gửi credentials và duy trì authentication như thế nào?
Bạn sẽ chọn HTTP Basic cho automation nội bộ trong trường hợp nào và cần biện pháp phòng vệ nào?
Bạn phân tích vì sao dùng HTTP Basic trên kênh không TLS có thể làm lộ mật khẩu của người dùng ra sao?
Bạn sẽ cấu hình formLogin loginPage và loginProcessingUrl riêng theo yêu cầu ứng dụng như thế nào?
Bạn phân biệt trang hiển thị form login với endpoint xử lý POST credentials trong Spring Security như thế nào?
Bạn sẽ quyết định khi nào custom AuthenticationSuccessHandler phù hợp hơn redirect mặc định ra sao?
Bạn mô tả SavedRequestAwareAuthenticationSuccessHandler khôi phục request được bảo vệ trước login như thế nào?
Bạn sẽ kiểm tra open redirect khi ứng dụng nhận URL chuyển hướng sau login từ client như thế nào?
Bạn sẽ xác định liệu login form đã gửi CSRF token đúng cách khi HTTP 403 trước authentication ra sao?
Bạn phân biệt authenticated() với fullyAuthenticated() trong chính sách cho phép truy cập có remember-me như thế nào?
Bạn sẽ đánh giá khi nào phải yêu cầu xác thực lại trước khi đổi mật khẩu hoặc khóa bảo mật ra sao?
Bạn mô tả AuthenticationEventPublisher hoặc authentication events giúp theo dõi đăng nhập thành công và thất bại như thế nào?
Bạn sẽ thiết kế audit authentication events mà không lưu raw password hoặc bearer token ra sao?
Bạn phân tích vì sao đăng nhập thành công không có nghĩa user được phép thực hiện mọi thao tác nghiệp vụ ra sao?
Bạn sẽ cấu hình multiple authentication mechanisms mà không để provider yếu vô tình thay thế kiểm tra provider mạnh như thế nào?
Bạn sẽ kiểm thử account lockout và unlock scenarios để xác minh chính sách xác thực được thực thi ra sao?
Bạn đánh giá khi nào nên tách authentication khỏi ứng dụng qua identity provider nhưng vẫn giữ authorization tại service như thế nào?
Bạn giải thích SecurityContext lưu Authentication trong lúc xử lý một request như thế nào?
Bạn phân biệt SecurityContextHolder với SecurityContextRepository trong việc giữ context tạm và lưu context giữa requests ra sao?
Bạn sẽ lấy principal từ SecurityContextHolder trong service nhưng tránh phụ thuộc quá sâu vào static API như thế nào?
Bạn mô tả @AuthenticationPrincipal giúp controller nhận danh tính hiện tại theo cơ chế nào?
Bạn phân biệt Principal và Authentication argument ở controller về dữ liệu bảo mật được cung cấp ra sao?
Bạn sẽ thiết kế service nhận current user identifier thay vì truyền toàn bộ Authentication xuống repository như thế nào?
Bạn phân tích nguy cơ dùng username lấy từ request body thay vì authenticated principal khi truy cập tài nguyên cá nhân ra sao?
Bạn sẽ xác định vì sao SecurityContext không tự động có mặt trong một thread mới do @Async tạo ra như thế nào?
Bạn mô tả DelegatingSecurityContextExecutor hỗ trợ chuyển security context đến background task ra sao?
Bạn sẽ kiểm thử SecurityContext được cleanup đúng khi servlet container tái sử dụng worker threads như thế nào?
Bạn phân tích rủi ro sử dụng MODE_INHERITABLETHREADLOCAL cho thread pools sống lâu như thế nào?
Bạn sẽ xác định khi nào cần RequestAttributeSecurityContextRepository thay vì session-backed storage ra sao?
Bạn mô tả HttpSessionSecurityContextRepository lưu SecurityContext vào HttpSession theo điều kiện nào?
Bạn phân biệt NullSecurityContextRepository với repository lưu session khi cấu hình API stateless như thế nào?
Bạn sẽ hiểu yêu cầu explicit save SecurityContext ở cấu hình dùng SecurityContextHolderFilter như thế nào?
Bạn phân tích vì sao setAuthentication thủ công mà không save context có thể làm request sau trở về anonymous như thế nào?
Bạn sẽ thiết kế logout clear SecurityContext và vô hiệu hóa session đúng cách như thế nào?
Bạn giải thích HttpSession giữ trạng thái đăng nhập browser khác với token bearer gửi theo mỗi request như thế nào?
Bạn sẽ cấu hình SessionCreationPolicy.IF_REQUIRED và SessionCreationPolicy.STATELESS theo loại client nào?
Bạn phân tích hậu quả khi một REST API đặt STATELESS nhưng một endpoint kỳ vọng remember-me hoặc session login ra sao?
Bạn sẽ phân biệt idle timeout và absolute session expiry khi lập chính sách phiên đăng nhập như thế nào?
Bạn mô tả SessionAuthenticationStrategy hỗ trợ bảo vệ session khi người dùng được xác thực như thế nào?
Bạn sẽ giải thích session fixation attack và cách Spring Security đổi session ID sau đăng nhập ra sao?
Bạn phân biệt changeSessionId với migrateSession theo yêu cầu giữ session attributes như thế nào?
Bạn sẽ kiểm tra session ID trước và sau login để xác minh chống session fixation như thế nào?
Bạn phân tích vì sao cookie có Secure và HttpOnly vẫn cần bảo vệ CSRF khi browser tự gửi cookie ra sao?
Bạn sẽ lựa chọn SameSite cookie policy phù hợp khi frontend và backend khác origins như thế nào?
Bạn mô tả RememberMeAuthenticationFilter khôi phục trạng thái đăng nhập khi session đã hết như thế nào?
Bạn phân biệt remember-me token với HttpSession cookie theo khả năng thu hồi và thời gian sống ra sao?
Bạn sẽ xác định khi nào remember-me authentication không đủ để cho phép thao tác nhạy cảm như thế nào?
Bạn sẽ thiết kế persistent remember-me tokens có khả năng revoke khi user logout trên nhiều thiết bị ra sao?
Bạn phân tích rủi ro browser bị đánh cắp remember-me cookie và yêu cầu rotation hoặc invalidation ra sao?
Bạn sẽ giới hạn số phiên đồng thời bằng cơ chế session concurrency của Spring Security theo chính sách nào?
Bạn mô tả SessionRegistry giúp theo dõi authenticated sessions khi cần concurrency control như thế nào?
Bạn phân tích vì sao SessionRegistry cục bộ không đủ cho ứng dụng có nhiều replicas không chia sẻ state ra sao?
Bạn sẽ chọn shared session store như Spring Session Redis khi cần quản lý session xuyên nhiều instance ra sao?
Bạn sẽ dùng LogoutHandler và LogoutSuccessHandler để tách cleanup khỏi phản hồi logout như thế nào?
Bạn đánh giá khi nào password reset phải vô hiệu hóa các active sessions và remember-me tokens ra sao?
Bạn giải thích AuthorizationManager chịu trách nhiệm quyết định quyền truy cập trong Spring Security hiện đại như thế nào?
Bạn phân biệt kiểm tra quyền ở URL request và kiểm tra quyền ở service method theo bề mặt tấn công như thế nào?
Bạn sẽ sử dụng authorizeHttpRequests để yêu cầu login cho /account/** và hạn chế /admin/** như thế nào?
Bạn phân biệt hasRole("ADMIN") với hasAuthority("ROLE_ADMIN") theo cơ chế role prefix ra sao?
Bạn sẽ xác định vì sao hasRole("ADMIN") không khớp khi GrantedAuthority thực tế là "ADMIN" như thế nào?
Bạn phân biệt hasAnyRole với hasAnyAuthority khi một endpoint hỗ trợ nhiều nhóm người dùng ra sao?
Bạn sẽ chọn access rule dựa trên authority thay vì role khi hệ thống có permissions chi tiết như thế nào?
Bạn mô tả permitAll, denyAll và authenticated khi xây dựng các mức bảo vệ request như thế nào?
Bạn phân biệt authenticated, fullyAuthenticated và anonymous về trạng thái được rule chấp nhận ra sao?
Bạn sẽ xác định tác động của requestMatchers ordering khi rule rộng /api/** đứng trước /api/admin/** như thế nào?
Bạn phân tích rủi ro match thiếu một HTTP method khiến thao tác ghi vô tình dùng cùng rule với GET như thế nào?
Bạn sẽ tạo rule chỉ cho phép quản trị viên gọi DELETE của một tài nguyên theo cách nào?
Bạn mô tả cách RequestMatcher giúp diễn đạt URL, HTTP method hoặc điều kiện request theo chính sách ra sao?
Bạn sẽ quyết định khi nào MVC request matcher semantics quan trọng với controller mapping thực tế như thế nào?
Bạn phân tích nguy cơ một API có path variable chứa identifier nhưng rule chỉ kiểm tra role chứ không kiểm tra ownership như thế nào?
Bạn sẽ thiết kế authorization kiểm tra ownerId theo authenticated principal thay vì ownerId do client tự cung cấp ra sao?
Bạn phân biệt role-based access control với attribute-based access control trong nghiệp vụ nhiều tenants như thế nào?
Bạn sẽ xác định cách tenant boundaries được áp dụng tại service và query thay vì chỉ tại endpoint như thế nào?
Bạn phân tích vì sao một endpoint có quyền truy cập chung vẫn có thể trả dữ liệu của người dùng khác nếu thiếu object-level authorization ra sao?
Bạn sẽ bật @EnableMethodSecurity và dùng @PreAuthorize cho một service method theo cách nào?
Bạn phân biệt @PreAuthorize với @PostAuthorize về thời điểm quyết định quyền được thực thi ra sao?
Bạn sẽ lựa chọn @Secured hoặc @RolesAllowed khi cần biểu diễn rule đơn giản so với @PreAuthorize như thế nào?
Bạn mô tả cách method security xử lý Authentication và method arguments trong SpEL như thế nào?
Bạn sẽ xác định rủi ro tự gọi một method @PreAuthorize trong cùng bean khiến proxy không intercept như thế nào?
Bạn phân tích sự khác nhau giữa method security proxy interception và kiểm tra quyền thủ công trong domain service ra sao?
Bạn sẽ đặt @PreAuthorize trên interface hay implementation theo proxy type và cấu hình thực tế như thế nào?
Bạn sẽ xác định thời điểm @PreAuthorize kiểm tra quyền trước khi có side effects và vì sao @PostAuthorize có thể quá muộn cho thao tác ghi như thế nào?
Bạn đánh giá rủi ro @PostAuthorize đọc toàn bộ tập dữ liệu nhạy cảm trước khi lọc quyền ra sao?
Bạn sẽ kiểm tra quyền trên từng record trong một collection trả về mà không nạp toàn bộ dữ liệu khi chưa cần như thế nào?
Bạn mô tả @PostFilter hoặc @PreFilter ảnh hưởng collection data ở method boundary theo điều kiện nào?
Bạn sẽ phân biệt filtering ở method layer với ràng buộc tenant trong SQL query về bảo mật và hiệu năng như thế nào?
Bạn sẽ sử dụng PermissionEvaluator hoặc custom AuthorizationManager khi rule vượt quá role đơn giản như thế nào?
Bạn phân tích rủi ro biểu thức SpEL phức tạp khó kiểm thử và phụ thuộc implementation details ra sao?
Bạn sẽ thiết kế reusable authorization policy bean để tái sử dụng giữa HTTP và method security như thế nào?
Bạn đánh giá khi nào dùng meta-annotation cho các @PreAuthorize rules lặp lại nhằm tăng khả năng review như thế nào?
Bạn sẽ chẩn đoán AccessDeniedException từ @PreAuthorize và phân biệt với lỗi chưa có authentication như thế nào?
Bạn phân tích lý do 403 Forbidden không nên được sửa bằng cách cấp quyền rộng hơn cho mọi user ra sao?
Bạn sẽ viết tests bảo đảm user thiếu permission bị từ chối dù request vẫn có session hợp lệ như thế nào?
Bạn sẽ đặt rule mặc định bảo vệ các method mới trong service theo kiến trúc không phụ thuộc chỉ vào annotations như thế nào?
Bạn giải thích cơ chế tấn công CSRF lợi dụng việc browser tự gửi cookie cùng request như thế nào?
Bạn phân biệt CSRF với XSS về nguồn tấn công và biện pháp phòng vệ chính như thế nào?
Bạn sẽ giải thích vì sao Spring Security bật CSRF protection mặc định với nhiều cấu hình servlet như thế nào?
Bạn mô tả CsrfFilter tham gia kiểm tra request thay đổi trạng thái theo cơ chế nào?
Bạn phân biệt request GET an toàn với POST/PUT/DELETE khi quyết định có yêu cầu CSRF token ra sao?
Bạn sẽ xác định khi nào một endpoint GET thực hiện thay đổi dữ liệu là sai thiết kế dù không bị CSRF check chặn như thế nào?
Bạn phân tích vì sao API dùng cookie authentication không nên tắt CSRF chỉ vì payload là JSON như thế nào?
Bạn sẽ quyết định khi nào một API nhận bearer token qua Authorization header có thể áp dụng chính sách CSRF khác browser session như thế nào?
Bạn mô tả CsrfTokenRepository quản lý token cần kiểm tra trong Spring Security như thế nào?
Bạn phân biệt HttpSessionCsrfTokenRepository với CookieCsrfTokenRepository về vị trí lưu token và cách client nhận token ra sao?
Bạn sẽ thiết kế một SPA lấy CSRF token từ cookie hoặc endpoint và gửi lại trong header theo cách nào?
Bạn đánh giá ảnh hưởng của cookie HttpOnly tới cách frontend JavaScript đọc CSRF token trong một kiến trúc SPA như thế nào?
Bạn sẽ kiểm tra CSRF token có bị thiếu hoặc không khớp khi login POST trả 403 như thế nào?
Bạn phân tích khi nào deferred CSRF token loading ảnh hưởng việc SPA khởi tạo trước request thay đổi trạng thái ra sao?
Bạn sẽ xác định cấu hình CSRF token request handler phù hợp với SPA và cơ chế token masking như thế nào?
Bạn sẽ bảo vệ endpoint logout dùng cookie authentication khỏi cross-site logout như thế nào?
Bạn mô tả cách logout handling phối hợp với CSRF để tránh request giả từ website ngoài ra sao?
Bạn phân biệt CSRF token với session ID hoặc access token theo chức năng nào?
Bạn sẽ tạo CSRF exclusions tối thiểu cho webhook đã có cơ chế xác minh riêng như thế nào?
Bạn phân tích rủi ro đặt csrf().disable() trên mọi SecurityFilterChain chỉ để webhook hoạt động ra sao?
Bạn sẽ kiểm thử một POST có session cookie nhưng thiếu CSRF token phải bị từ chối như thế nào?
Bạn sẽ kiểm thử một POST có CSRF token hợp lệ được xử lý nhưng vẫn phải qua authorization như thế nào?
Bạn giải thích CORS kiểm soát hành vi đọc phản hồi cross-origin của browser khác với authentication như thế nào?
Bạn phân biệt CORS policy với CSRF protection dù cả hai đều liên quan cross-origin requests như thế nào?
Bạn sẽ cấu hình cors() và CorsConfigurationSource theo danh sách origins thật sự tin cậy như thế nào?
Bạn phân tích rủi ro trả Access-Control-Allow-Origin quá rộng kèm Access-Control-Allow-Credentials như thế nào?
Bạn sẽ xử lý preflight OPTIONS trước authentication để browser client hoạt động đúng như thế nào?
Bạn mô tả CORS preflight kiểm tra phương thức và headers được phép mà không chứng minh caller đã đăng nhập như thế nào?
Bạn sẽ phân biệt same-origin và same-site khi thiết kế cookies SameSite cho frontend/API ra sao?
Bạn phân tích vì sao CORS allowlist không thay thế authorization trên từng API endpoint ra sao?
Bạn sẽ thiết kế Content-Security-Policy nhằm giảm khả năng thực thi script không tin cậy như thế nào?
Bạn phân biệt CSP với CSRF token ở loại hành vi tấn công được hạn chế như thế nào?
Bạn sẽ cấu hình HTTP Strict-Transport-Security để browser ưu tiên HTTPS theo các điều kiện triển khai nào?
Bạn phân tích vì sao HSTS phải được cấu hình cùng chiến lược HTTPS và reverse proxy đúng thay vì chỉ thêm header ra sao?
Bạn sẽ sử dụng X-Content-Type-Options để giảm rủi ro MIME sniffing như thế nào?
Bạn sẽ bảo vệ trang đăng nhập khỏi clickjacking bằng frame-ancestors hoặc frame options theo chính sách nào?
Bạn phân biệt X-Frame-Options với CSP frame-ancestors khi cho phép nhúng một số trang cụ thể như thế nào?
Bạn sẽ cấu hình security headers qua HttpSecurity.headers mà tránh vô tình làm hỏng assets hoặc embedding hợp lệ ra sao?
Bạn phân tích rủi ro XSS trong trang login dù Spring Security đã bật session và CSRF như thế nào?
Bạn sẽ kiểm tra cookies, redirects và security headers của trang login trong browser devtools theo các tiêu chí nào?
Bạn phân biệt stateful browser session và stateless API token về cách Authentication được xây lại qua các requests như thế nào?
Bạn sẽ chọn HTTP Basic, form login hoặc bearer token cho browser, CLI và backend API theo mục tiêu nào?
Bạn giải thích OAuth2 Resource Server cung cấp bearer authentication cho API Spring như thế nào?
Bạn phân biệt oauth2Login dành cho đăng nhập người dùng với oauth2ResourceServer dành cho xác thực access token như thế nào?
Bạn sẽ xác định khi nào OIDC cung cấp thông tin identity cho login còn OAuth2 access token được dùng để gọi API như thế nào?
Bạn phân tích rủi ro dùng OIDC ID token làm bearer access token cho resource server khi mục đích token không phù hợp như thế nào?
Bạn mô tả BearerTokenAuthenticationFilter tham gia xác thực một Authorization: Bearer header như thế nào?
Bạn phân biệt JWT validation cục bộ với opaque token introspection qua authorization server về độ trễ và thu hồi token ra sao?
Bạn sẽ cấu hình oauth2ResourceServer().jwt() cùng nguồn public keys hợp lệ theo Spring Security DSL như thế nào?
Bạn phân tích vì sao resource server cần kiểm tra issuer, audience và expiration ngoài chữ ký JWT ra sao?
Bạn sẽ ánh xạ scope claims từ JWT sang GrantedAuthority cho policy truy cập API như thế nào?
Bạn phân biệt token scope với quyền sở hữu từng object trong hệ thống như thế nào?
Bạn sẽ xác định cách xử lý JWT đã hết hạn hoặc issuer sai bằng HTTP 401 đúng semantics ra sao?
Bạn sẽ tổ chức logging cho bearer authentication failure mà không ghi raw access tokens vào logs như thế nào?
Bạn phân tích vì sao JWT tự xác minh không tự bảo đảm account đã bị khóa sẽ mất quyền ngay lập tức ra sao?
Bạn sẽ lựa chọn token lifetime và revocation strategy theo độ nhạy cảm của ứng dụng như thế nào?
Bạn sẽ quyết định khi nào không nên tự triển khai custom JWT parser mà dùng JwtDecoder của Spring Security ra sao?
Bạn phân tích nguy cơ chọn thuật toán signature chỉ dựa trên token header do attacker kiểm soát ra sao?
Bạn sẽ sử dụng issuer validation và trust configuration cố định để tránh chấp nhận token từ provider lạ như thế nào?
Bạn sẽ quyết định khi nào một custom OncePerRequestFilter đọc API key là phù hợp và phải tạo Authentication như thế nào?
Bạn phân biệt API key với user bearer token theo danh tính và khả năng revoke ra sao?
Bạn sẽ lưu API keys dưới dạng hash và giới hạn quyền theo client application theo cách nào?
Bạn phân tích rủi ro truyền token trong query parameter làm lộ thông tin qua logs, history hoặc Referer ra sao?
Bạn sẽ tách SecurityFilterChain cho /api/** stateless khỏi /ui/** dùng session để tránh cookie authentication ngoài ý muốn như thế nào?
Bạn đánh giá khi nào request cache hoặc remember-me không phù hợp với API chỉ nhận bearer tokens ra sao?
Bạn sẽ xác định hành vi logout trong session-based app khác việc thu hồi một bearer token không lưu ở server như thế nào?
Bạn sẽ giải thích cách refresh token được bảo vệ khác với access token và vì sao resource server không nên chấp nhận refresh token như thế nào?
Bạn sẽ lựa chọn các test case token invalid signature, wrong issuer, expired và missing permission theo ranh giới nào?
Bạn sẽ xác minh một endpoint chỉ cho phép authentication qua đúng cơ chế đã thiết kế thay vì chấp nhận session hoặc header không mong muốn như thế nào?
Bạn phân biệt unit test của authorization policy với integration test kiểm tra toàn bộ Spring Security filter chain như thế nào?
Bạn sẽ dùng spring-security-test để thiết lập SecurityContext giả trong test service theo cách nào?
Bạn mô tả @WithMockUser giúp kiểm thử quyền method nhưng không xác nhận authentication filter thật đã chạy như thế nào?
Bạn sẽ dùng @WithUserDetails khi test cần UserDetails và authorities theo repository test fixture như thế nào?
Bạn sẽ sử dụng MockMvc với springSecurity() để chạy các security filters trong MVC integration test ra sao?
Bạn phân tích vì sao MockMvc test không apply Spring Security có thể cho kết quả giả về bảo vệ endpoint như thế nào?
Bạn sẽ gửi request chưa đăng nhập và xác nhận HTTP 401 hoặc redirect tùy policy trong MockMvc như thế nào?
Bạn sẽ kiểm thử user đăng nhập có role USER bị từ chối DELETE của admin endpoint như thế nào?
Bạn mô tả formLogin() request builder và csrf() request postprocessor được dùng trong MockMvc tests như thế nào?
Bạn sẽ kiểm thử form login với password đúng, password sai và account disabled theo các kết quả nào?
Bạn phân tích vì sao test chỉ kiểm tra redirect login thành công mà không kiểm tra session hoặc principal có thể bỏ sót lỗi ra sao?
Bạn sẽ dùng user() request postprocessor để kiểm tra authorization mà không nhầm với login integration test như thế nào?
Bạn sẽ kiểm tra session persistence bằng hai requests liên tiếp dùng cùng MockHttpSession theo cách nào?
Bạn sẽ viết test cho logout để session và SecurityContext không còn được dùng sau khi logout ra sao?
Bạn đánh giá cách kiểm thử chống session fixation với session ID trước và sau xác thực thành công như thế nào?
Bạn sẽ kiểm thử POST thiếu CSRF token bị từ chối nhưng GET public vẫn chạy bình thường ra sao?
Bạn sẽ xác minh CSRF exception chỉ áp dụng endpoint webhook đã có bảo vệ khác chứ không áp dụng mọi API như thế nào?
Bạn phân tích cách tạo test CORS preflight OPTIONS với Origin và Access-Control-Request-Headers theo case nào?
Bạn sẽ kiểm thử Content-Security-Policy và HSTS response headers ở môi trường HTTPS phù hợp như thế nào?
Bạn sẽ kiểm tra filter chain matching khi /api/private và /web/private có authentication khác nhau ra sao?
Bạn sẽ viết test đảm bảo URL có encoded characters hoặc trailing slash không bypass securityMatcher như thế nào?
Bạn đánh giá cách kiểm thử anonymous user, remember-me user và fully authenticated user theo mức quyền khác nhau như thế nào?
Bạn sẽ sử dụng @WithMockUser cùng @PreAuthorize để kiểm tra method security khi controller được gọi trực tiếp như thế nào?
Bạn phân tích vì sao test @PreAuthorize chỉ dùng mock bean không chứng minh interceptor của service thực sự được kích hoạt ra sao?
Bạn sẽ kiểm tra self-invocation của secured method bị bỏ qua proxy bằng một integration test ra sao?
Bạn mô tả jwt() request postprocessor tạo fake JwtAuthenticationToken để test quyền mà không kiểm tra signature như thế nào?
Bạn sẽ viết negative test cho JwtDecoder thật từ chối token invalid thay vì chỉ test với jwt() mock như thế nào?
Bạn sẽ dùng WebTestClient và mock authentication khi ứng dụng dùng reactive SecurityWebFilterChain như thế nào?
Bạn phân biệt ReactiveSecurityContextHolder với SecurityContextHolder ThreadLocal trong reactive test như thế nào?
Bạn sẽ tổ chức test data không dùng password thật hoặc access tokens đã triển khai trong môi trường khác như thế nào?
Bạn sẽ test cấu hình có nhiều SecurityFilterChain beans mà mỗi request chỉ áp dụng policy mong muốn ra sao?
Bạn đánh giá khi nào chạy SpringBootTest để phát hiện bean wiring hoặc configuration conflict thay vì chỉ slice test MVC như thế nào?
Bạn sẽ ghi nhận audit login failures và authorization denials mà không đưa credentials hoặc PII vào test logs ra sao?
Bạn mô tả Micrometer metrics có thể đo authentication failures, 401/403 rate và latency theo endpoint như thế nào?
Bạn sẽ tránh đưa username, token hoặc session ID vào metric labels khi theo dõi an ninh như thế nào?
Bạn sẽ lập runbook phân biệt lỗi password encoder, CSRF token, CORS preflight và sai SecurityFilterChain match như thế nào?
Bạn sẽ sử dụng debug traces để xác định lý do một Authentication bị coi là anonymous trong request ra sao?
Bạn sẽ kiểm tra quyền và chính sách HTTP headers sau mỗi lần nâng Spring Security version theo quy trình nào?
Bạn sẽ mô tả checklist go-live cho các API gồm deny-by-default, session, CSRF, CORS, TLS và security tests như thế nào?
Nếu API chưa đăng nhập trả 302 HTML login thay vì 401 JSON, bạn sẽ tìm lại AuthenticationEntryPoint và filter chain matching như thế nào?
Nếu /api/admin/export được truy cập bởi role USER do rule /api/** đứng trước rule hẹp hơn, bạn sẽ sửa thứ tự requestMatchers ra sao?
Nếu một endpoint mới không khớp SecurityFilterChain nào nên không bị bảo vệ, bạn sẽ bổ sung fallback policy và test như thế nào?
Nếu custom authentication filter chạy hai lần mỗi request, bạn sẽ kiểm tra cả servlet filter registration và SecurityFilterChain như thế nào?
Nếu SecurityContext bị mất khi một service dùng @Async, bạn sẽ tổ chức context propagation và cleanup như thế nào?
Nếu login thành công nhưng request sau vẫn anonymous, bạn sẽ kiểm tra SecurityContextRepository, session policy và saveContext ra sao?
Nếu user đã đăng nhập vẫn nhận 403 khi gọi method @PreAuthorize, bạn sẽ kiểm tra authorities và role prefix như thế nào?
Nếu user A dùng path ID của user B và endpoint chỉ kiểm tra authenticated(), bạn sẽ bổ sung object-level authorization ở tầng nào?
Nếu một service gọi nội bộ method có @PreAuthorize nhưng quyền không được kiểm tra, bạn sẽ xử lý proxy self-invocation ra sao?
Nếu session ID không đổi sau login, bạn sẽ xác minh và cấu hình session fixation protection như thế nào?
Nếu logout chỉ xóa cookie nhưng session cũ vẫn được server chấp nhận, bạn sẽ kiểm tra LogoutHandler và session invalidation ra sao?
Nếu browser login POST bị 403 trước khi so sánh mật khẩu, bạn sẽ điều tra CSRF token và request mapping như thế nào?
Nếu webhook từ hệ thống ngoài bị CSRF chặn, bạn sẽ giới hạn ngoại lệ endpoint nhưng vẫn xác minh chữ ký webhook ra sao?
Nếu API cho phép CORS mọi origin kèm credentials, bạn sẽ giới hạn origins và kiểm tra cookie/CSRF exposure như thế nào?
Nếu một OPTIONS preflight bị từ chối trước khi controller chạy, bạn sẽ kiểm tra CORS filter và authorization chain ra sao?
Nếu Content-Security-Policy chặn script hợp lệ trên login page, bạn sẽ điều chỉnh policy có kiểm soát mà không tắt CSP như thế nào?
Nếu API nhận JWT có chữ ký hợp lệ nhưng sai audience, bạn sẽ điều chỉnh JwtDecoder validators và negative tests ra sao?
Nếu token JWT hết hạn vẫn được client gửi lại liên tục, bạn sẽ phân biệt cơ chế trả 401 với refresh flow ra sao?
Nếu test @WithMockUser PASS nhưng đăng nhập thật vẫn lỗi, bạn sẽ mở rộng kiểm thử qua filters và PasswordEncoder như thế nào?
Nếu cần bảo vệ một ứng dụng Spring MVC mới gồm trang login, admin API và bearer API, bạn sẽ thiết kế SecurityFilterChain, SecurityContext, authorization, session, CSRF và kiểm thử như thế nào?

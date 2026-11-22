# Kiểm thử filter chain, endpoint matcher và cấu hình issuer

Spring Authorization Server thường chạy cùng các endpoint nghiệp vụ của ứng dụng trong một Spring Security filter chain. Các endpoint OAuth 2.0/OIDC như authorization, token, JWK Set, introspection và userinfo có yêu cầu bảo mật riêng. Nếu request đi nhầm filter chain, endpoint có thể bị chặn bởi form login, bỏ qua quy tắc xác thực client, hoặc nhận cấu hình session và CSRF không phù hợp. Nếu issuer cấu hình sai, metadata discovery và token có thể công bố một địa chỉ khác với địa chỉ mà client đang sử dụng.

Kiểm thử chức năng cần chứng minh ba điều: request đến endpoint Authorization Server được định tuyến vào đúng SecurityFilterChain; request của ứng dụng tiếp tục dùng chain mặc định; issuer xuất hiện nhất quán trong metadata và token. Hãy kiểm thử qua MockMvc với filter chain thật được nạp trong application context, thay vì chỉ kiểm tra từng bean cấu hình riêng lẻ.

## 1. Phân biệt SecurityFilterChain matcher và authorization matcher

Spring Security có hai lớp quyết định khác nhau:

- securityMatcher chọn SecurityFilterChain nào sẽ xử lý một HTTP request. FilterChainProxy duyệt các chain theo thứ tự và sử dụng chain đầu tiên có matcher trả về true.
- requestMatchers bên trong authorizeHttpRequests quyết định request được phép truy cập hay phải xác thực sau khi đã vào một chain.

Hai loại matcher này không thay thế nhau. Việc viết requestMatchers("/oauth2/**").authenticated() trong chain mặc định không tự tạo một chain riêng cho Authorization Server. Ngược lại, securityMatcher("/oauth2/**") chỉ chọn chain; nó không thay thế các quy tắc authorization bên trong chain đó.

Với Authorization Server, nên lấy matcher từ OAuth2AuthorizationServerConfigurer.getEndpointsMatcher(). Matcher này gắn với tập endpoint do configurer quản lý, kể cả khi một số endpoint được tùy chỉnh. Tránh tự liệt kê thủ công một vài đường dẫn như /oauth2/authorize và /oauth2/token vì có thể bỏ sót JWK Set, introspection, revocation, device authorization hoặc endpoint OIDC.

## 2. Cấu hình hai filter chain

Ví dụ sau dùng API cấu hình hiện đại của Spring Security 6 và Spring Authorization Server phiên bản có OAuth2AuthorizationServerConfigurer.authorizationServer(). Chain có thứ tự cao hơn dành cho các endpoint giao thức; chain thứ hai xử lý phần còn lại của ứng dụng.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults())
        )
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
        )
        .exceptionHandling(exceptions ->
                exceptions.defaultAuthenticationEntryPointFor(
                        new LoginUrlAuthenticationEntryPoint("/login"),
                        new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
                )
        );

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public-probe", "/assets/**").permitAll()
                .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Chain thứ hai không khai báo securityMatcher nên hoạt động như chain dự phòng cho các request còn lại. Thứ tự là một phần của hành vi bảo mật: nếu chain dự phòng đứng trước và matcher của nó bắt mọi request, chain Authorization Server sẽ không được gọi. Khi dùng phiên bản Spring Authorization Server cũ hơn, cách khởi tạo hoặc áp dụng configurer có thể khác; giữ nguyên nguyên tắc dùng endpoint matcher từ configurer và xác nhận API theo phiên bản dependency thực tế.

Trong ví dụ, OIDC được bật để có discovery và userinfo. Nếu ứng dụng không hỗ trợ OpenID Connect, bỏ cấu hình oidc và bỏ các kiểm thử chỉ dành cho OIDC. Các endpoint OAuth 2.0 vẫn phải được kiểm thử theo cấu hình thực tế.

## 3. Cấu hình issuer cố định

Issuer là định danh URL của Authorization Server. Client dùng issuer để kiểm tra metadata, đối chiếu token và xác định máy chủ phát hành. Trong môi trường production, thường nên cấu hình issuer công khai ổn định thay vì để giá trị thay đổi theo Host header của request đến:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://identity.example.com")
            .build();
}
~~~

Giá trị issuer phải khớp chính xác với issuer mà client được cấu hình tin cậy, bao gồm scheme, hostname, port nếu có và path. Tránh tự thêm hoặc bỏ dấu gạch chéo cuối một cách không nhất quán. Các URL endpoint trong metadata thường được xây dựng dựa trên issuer và cấu hình endpoint của server.

Nếu triển khai sau reverse proxy hoặc ingress, ứng dụng có thể nhận request nội bộ bằng HTTP trong khi client truy cập bằng HTTPS. Khi issuer không được cấu hình tĩnh, server có thể suy ra địa chỉ từ request hiện tại; lúc đó Forwarded hoặc X-Forwarded-* headers ảnh hưởng đến scheme và host mà ứng dụng nhìn thấy. Chỉ xử lý các header này từ proxy đáng tin cậy. Không cho phép client Internet tự gửi header forwarded tùy ý để quyết định issuer.

## 4. Chuẩn bị integration test

Dùng application context chứa đúng hai SecurityFilterChain, AuthorizationServerSettings, RegisteredClientRepository, OAuth2AuthorizationService và JWKSource như ứng dụng tích hợp. Ví dụ các test sau dùng Spring Boot với MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationServerSecurityIntegrationTests {

    private static final String ISSUER =
            "https://identity.example.com";

    @Autowired
    MockMvc mockMvc;

    @Autowired
    FilterChainProxy springSecurityFilterChain;

    @Autowired
    JwtDecoder jwtDecoder;

    // Các test ở những mục tiếp theo đặt trong lớp này.
}
~~~

Nếu dùng @WebMvcTest, phải import rõ cả hai chain và các bean phụ thuộc của Authorization Server. Một test slice chỉ nạp chain ứng dụng hoặc chỉ nạp chain Authorization Server có thể tạo kết quả đúng giả tạo vì nó không kiểm tra thứ tự chọn chain trong context đầy đủ.

Với JWK Set endpoint, cần có JWKSource bean chứa khóa public tương ứng. Với discovery OIDC, bật OIDC trong configurer. Tạo client, user và consent bằng fixture riêng để các bài test không phụ thuộc dữ liệu còn lại từ lần chạy trước.

## 5. Kiểm tra matcher và thứ tự chain

Có thể kiểm tra trực tiếp các matcher như một chẩn đoán bổ sung. Ví dụ dưới đây giả định context test có đúng chain Authorization Server ở vị trí đầu và chain ứng dụng ở vị trí tiếp theo:

~~~java
@Test
void authorizationServerMatcherSelectsProtocolEndpointsOnly() {
    List<SecurityFilterChain> chains =
            springSecurityFilterChain.getFilterChains();

    MockHttpServletRequest authorizeRequest =
            new MockHttpServletRequest("GET", "/oauth2/authorize");
    MockHttpServletRequest tokenRequest =
            new MockHttpServletRequest("POST", "/oauth2/token");
    MockHttpServletRequest applicationRequest =
            new MockHttpServletRequest("GET", "/public-probe");

    assertThat(chains.get(0).matches(authorizeRequest)).isTrue();
    assertThat(chains.get(0).matches(tokenRequest)).isTrue();
    assertThat(chains.get(0).matches(applicationRequest)).isFalse();
}
~~~

Bài test này kiểm tra matcher của chain đầu. Nó không thay thế kiểm thử HTTP vì FilterChainProxy còn phụ thuộc thứ tự và hành vi thực tế của các filter. Nếu ứng dụng có thêm chain cho actuator, tài nguyên tĩnh hoặc API riêng, cập nhật test theo thứ tự dự kiến của tất cả chain trong test context.

## 6. Chứng minh request của ứng dụng đi vào chain dự phòng

Đường dẫn /public-probe trong ví dụ cấu hình được permitAll bởi chain ứng dụng. Hãy tạo một endpoint probe chỉ trong test hoặc dùng một endpoint công khai sẵn có:

~~~java
@Test
void applicationRouteUsesApplicationSecurityRules() throws Exception {
    mockMvc.perform(get("/public-probe"))
            .andExpect(status().isOk());
}
~~~

Nếu request này bị chain Authorization Server bắt nhầm, quy tắc authenticated của chain đầu có thể chuyển nó sang login hoặc trả lỗi xác thực. Test endpoint công khai của ứng dụng vì vậy giúp phát hiện chain đầu vô tình dùng matcher quá rộng như anyRequest hoặc /**.

Nên có thêm một endpoint nghiệp vụ cần đăng nhập để xác nhận chain ứng dụng vẫn yêu cầu authentication. Một endpoint public thành công không chứng minh toàn bộ quy tắc của chain thứ hai đúng; nó chỉ xác nhận một trường hợp đại diện.

## 7. Kiểm tra hành vi của các endpoint Authorization Server

Các test HTTP sau chứng minh endpoint giao thức được phục vụ bởi cấu hình Authorization Server. Đường dẫn mặc định có thể được thay đổi bằng AuthorizationServerSettings, do đó dùng path thực tế của ứng dụng khi đã tùy chỉnh endpoint.

**JWK Set endpoint:** Khi JWKSource đã cấu hình, endpoint public cần trả JSON chứa danh sách khóa công khai:

~~~java
@Test
void jwkSetEndpointIsReachableWithoutLogin() throws Exception {
    mockMvc.perform(get("/oauth2/jwks"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.keys").isArray());
}
~~~

JWK Set công khai chỉ nên chứa public key. Không để private key member như d, p, q, dp, dq, qi hoặc oth xuất hiện trong response. Có thể bổ sung assertion kiểm tra từng JWK không chứa các private member này.

**Authorization endpoint:** Với request HTML chưa đăng nhập, chain Authorization Server có thể chuyển người dùng đến trang login thông qua AuthenticationEntryPoint:

~~~java
@Test
void authorizationEndpointRequiresUserAuthentication() throws Exception {
    mockMvc.perform(get("/oauth2/authorize")
                    .accept(MediaType.TEXT_HTML)
                    .param("response_type", "code")
                    .param("client_id", "browser-client")
                    .param("redirect_uri", "https://client.example/callback")
                    .param("scope", "openid profile")
                    .param("state", "state-test"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                    HttpHeaders.LOCATION, containsString("/login")));
}
~~~

Test này tập trung vào trường hợp request trình duyệt chưa có phiên người dùng. Một request thiếu client_id hoặc redirect_uri có thể bị từ chối ở bước xác thực protocol trước khi đến bước đăng nhập; vì vậy hãy dùng client và redirect URI hợp lệ khi kiểm tra AuthenticationEntryPoint.

**Token endpoint:** Token endpoint phải thực hiện client authentication theo phương thức đăng ký. Một test âm tính có thể gửi client credentials sai và xác nhận server trả OAuth error invalid_client, không trả token:

~~~java
@Test
void tokenEndpointRejectsInvalidClientCredentials() throws Exception {
    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("browser-client", "wrong-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "client_credentials")
                    .param("scope", "api.read"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_client"))
            .andExpect(jsonPath("$.access_token").doesNotExist());
}
~~~

Đăng ký client fixture với grant type client_credentials và phương thức client authentication tương ứng để request đến được bước kiểm tra credential. Nếu dùng phương thức xác thực khác, thay helper HTTP Basic cho phù hợp. Không dùng request sai grant type để kết luận client authentication đang hoạt động.

## 8. Kiểm tra OIDC discovery và issuer

Khi OIDC được bật, discovery endpoint công bố issuer và các endpoint mà client cần gọi. Kiểm tra issuer và URL endpoint quan trọng trong cùng một response:

~~~java
@Test
void oidcDiscoveryPublishesConfiguredIssuerAndEndpoints() throws Exception {
    mockMvc.perform(get("/.well-known/openid-configuration"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.issuer").value(ISSUER))
            .andExpect(jsonPath("$.authorization_endpoint")
                    .value(ISSUER + "/oauth2/authorize"))
            .andExpect(jsonPath("$.token_endpoint")
                    .value(ISSUER + "/oauth2/token"))
            .andExpect(jsonPath("$.jwks_uri")
                    .value(ISSUER + "/oauth2/jwks"));
}
~~~

Nếu endpoint được tùy chỉnh, cập nhật các URL mong đợi theo AuthorizationServerSettings. Nếu ứng dụng không bật OIDC, có thể kiểm tra OAuth 2.0 Authorization Server Metadata tại well-known endpoint mà phiên bản và cấu hình đang cung cấp; không mong đợi OIDC discovery hoạt động khi OIDC chưa bật.

Issuer trong metadata phải giống issuer dùng khi phát hành token. Với ID token lấy được sau một authorization code flow có scope openid, giải mã bằng JwtDecoder được cấu hình với JWKSource tương ứng và kiểm tra claim iss:

~~~java
Jwt idToken = jwtDecoder.decode(idTokenValue);
assertThat(idToken.getClaimAsString("iss")).isEqualTo(ISSUER);
~~~

Ví dụ này giả định test đã hoàn tất authorization code flow với scope openid và lấy được ID token hợp lệ. Nếu test access token dạng JWT, cũng kiểm tra claim iss theo định dạng token mà ứng dụng phát hành. Với opaque access token, không thể đọc claim JWT trực tiếp; hãy kiểm tra issuer qua metadata và introspection theo hợp đồng của ứng dụng.

## 9. Kiểm tra issuer khi có Host và forwarded headers

Một issuer tĩnh phải giữ nguyên khi request đến với Host header khác. Bài test này phát hiện cấu hình vô tình suy issuer từ host do request cung cấp:

~~~java
@Test
void configuredIssuerDoesNotFollowArbitraryHostHeader() throws Exception {
    mockMvc.perform(get("/.well-known/openid-configuration")
                    .header(HttpHeaders.HOST, "untrusted.example"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.issuer").value(ISSUER));
}
~~~

Nếu hệ thống dựa vào forwarded headers để dựng public URL, tạo test riêng cho proxy được tin cậy và kiểm tra scheme, host, port, context path. Đồng thời kiểm tra request trực tiếp từ nguồn không tin cậy không thể giả mạo issuer bằng Forwarded hoặc X-Forwarded-Host. Không nên khẳng định một header forwarded luôn bị bỏ qua hoặc luôn được tin; hành vi phụ thuộc vào cấu hình proxy và ForwardedHeaderFilter của ứng dụng.

## 10. Ma trận kiểm thử chức năng

| Kịch bản | Request/điểm quan sát | Kết quả mong đợi |
|---|---|---|
| Authorization endpoint | GET /oauth2/authorize với request hợp lệ, chưa đăng nhập | Chuyển đến login theo cấu hình HTML entry point |
| Token endpoint | POST /oauth2/token với client secret sai | invalid_client, không có access token |
| JWK Set | GET /oauth2/jwks | 200 JSON, chỉ có public key |
| OIDC discovery | GET /.well-known/openid-configuration | Metadata có issuer và endpoint URL chính xác |
| Route ứng dụng công khai | GET /public-probe | Được chain ứng dụng permitAll xử lý |
| Route ứng dụng cần đăng nhập | GET endpoint nghiệp vụ bảo vệ | Yêu cầu authentication |
| Issuer với Host lạ | Discovery request có Host không tin cậy | Issuer vẫn giữ giá trị cấu hình tĩnh |
| Token OIDC | Giải mã ID token đã phát hành | Claim iss khớp issuer đã công bố |

## 11. Những lỗi cấu hình thường gặp

**Chain Authorization Server không đứng trước:** FilterChainProxy chọn chain dự phòng đầu tiên có matcher phù hợp. Khi chain ứng dụng bắt mọi request đứng trước, các endpoint OAuth có thể bị chuyển sang login hoặc chịu quy tắc không dành cho giao thức.

**Tự viết matcher quá hẹp:** Matcher chỉ chứa authorize và token có thể bỏ sót JWK Set, metadata, introspection, revocation hoặc OIDC. Lấy matcher từ configurer để danh sách endpoint được đồng bộ với cấu hình.

**Nhầm matcher với authorization rule:** securityMatcher chọn chain; authorizeHttpRequests quy định quyền trong chain đó. Cần kiểm tra cả hai lớp.

**Issuer không ổn định sau proxy:** Nếu ứng dụng dựng issuer từ request nhưng không xử lý đúng forwarded headers, metadata có thể công bố http hoặc hostname nội bộ. Nếu tin header forwarded từ mọi nguồn, client có thể làm sai địa chỉ công bố. Cấu hình static issuer hoặc giới hạn forwarded headers ở proxy đáng tin cậy.

**Chỉ kiểm tra metadata:** Discovery đúng chưa chắc token phát hành có issuer đúng. Hãy kiểm tra cả claim iss của ID token hoặc JWT access token khi luồng test tạo ra token tương ứng.

**Test slice thiếu filter chain:** Một test chỉ import một SecurityFilterChain không thể phát hiện lỗi thứ tự giữa chain Authorization Server và chain ứng dụng. Dùng application context tích hợp hoặc import đầy đủ các chain trong test.

## 12. Checklist trước khi phát hành

- [ ] Authorization Server dùng securityMatcher lấy từ OAuth2AuthorizationServerConfigurer.getEndpointsMatcher().
- [ ] Chain Authorization Server có thứ tự trước chain ứng dụng bắt mọi request.
- [ ] Chain ứng dụng tiếp tục xử lý các route nghiệp vụ và tài nguyên tĩnh theo chính sách riêng.
- [ ] Test chứng minh endpoint authorize, token và JWK Set đi qua cấu hình dự kiến.
- [ ] JWK Set chỉ công bố public key.
- [ ] OIDC discovery hoạt động khi OIDC được bật và công bố issuer chính xác.
- [ ] Issuer trong ID token hoặc JWT access token khớp issuer trong metadata.
- [ ] Host và forwarded headers không thể làm sai issuer công khai.
- [ ] Test dùng application context có đầy đủ các filter chain như môi trường triển khai.

Khi các bài kiểm thử này chạy trong CI, thay đổi về endpoint, thứ tự filter chain, proxy hoặc issuer sẽ được phát hiện trước khi làm gián đoạn luồng OAuth 2.0/OIDC của client.

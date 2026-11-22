# Lỗi claims, audience và quyền truy cập tại Resource Server

Resource Server có thể nhận được access token nhưng vẫn từ chối request vì claim thiếu hoặc sai kiểu, issuer không được tin cậy, audience không dành cho API, hoặc scope/role không được ánh xạ thành authority mà Spring Security yêu cầu. Một số trường hợp trả 401 Unauthorized vì token không hợp lệ; trường hợp khác trả 403 Forbidden vì token đã được xác thực nhưng principal không có quyền truy cập endpoint.

Khi xử lý lỗi, cần lần theo toàn bộ đường đi của quyền: Authorization Server phát hành claim nào, Resource Server xác minh token ra sao, converter chuyển claim thành GrantedAuthority thế nào và security rule so sánh authority nào. Bài này tập trung vào Spring Security Resource Server trong hệ thống OAuth 2.0/OpenID Connect sử dụng Spring Authorization Server.

## 1. Phân biệt lỗi xác thực token và lỗi phân quyền

Bước đầu tiên là xác định request thất bại ở tầng nào. Không nên bắt đầu bằng cách thêm role vào token hoặc nới lỏng security matcher trước khi biết token bị từ chối vì lý do gì.

| Kết quả | Ý nghĩa thường gặp | Điểm cần kiểm tra |
|---|---|---|
| 401 Unauthorized | Không có bearer token, token không parse được, chữ ký sai, hết hạn, issuer/audience không hợp lệ hoặc introspection không active | Authentication filter, JwtDecoder hoặc OpaqueTokenIntrospector |
| 403 Forbidden | Token đã được chấp nhận nhưng thiếu scope/role/authority hoặc bị policy từ chối | JwtAuthenticationConverter, authority mapping và authorization rule |
| 404 Not Found | Có thể do route không tồn tại hoặc ứng dụng cố ý che endpoint | Request mapping, security matcher và error handling |
| 200 nhưng dữ liệu không đúng phạm vi | API xác thực thành công nhưng kiểm tra quyền ở tầng dữ liệu thiếu hoặc sai | Method security, tenant/ownership policy và query filter |

Trong cấu hình Resource Server mặc định, lỗi xác thực bearer token thường được xử lý bởi BearerTokenAuthenticationEntryPoint; lỗi phân quyền thường đi qua BearerTokenAccessDeniedHandler hoặc access-denied handler tùy chỉnh. Response thực tế có thể khác khi ứng dụng thay exception handler.

Một cách đọc nhanh:

- **401**: kiểm tra token có hợp lệ và được chấp nhận làm credential không.
- **403**: kiểm tra principal đã có đúng authority mà endpoint yêu cầu chưa.
- **401 sau khi đổi issuer/audience**: kiểm tra validator và metadata.
- **403 sau khi đổi claim scope/roles**: kiểm tra converter và biểu thức authorization.

Không dùng status code làm bằng chứng duy nhất. Đọc WWW-Authenticate khi có, log đã làm sạch, exception category và kết quả validator. Không ghi raw JWT hoặc gửi token tới công cụ decode công khai.

## 2. Xác định loại token và nguồn claim

Trước khi phân tích claim, xác định API đang nhận loại token nào:

- **JWT access token**: Resource Server xác minh chữ ký, thời hạn và các validator của JWT.
- **Opaque access token**: Resource Server thường gọi introspection endpoint để kiểm tra trạng thái và nhận metadata.
- **OIDC ID Token**: token dành cho OIDC client để xác thực người dùng; không mặc định dùng thay access token khi gọi API.

ID Token thường có audience là client_id của ứng dụng OIDC. Access token cần audience phù hợp với resource server/API. Dùng ID Token để gọi API hoặc kiểm tra aud theo sai profile có thể dẫn đến từ chối đúng hoặc chấp nhận nhầm token.

Với JWT, payload có thể đọc được nhưng chưa được tin cậy cho tới khi chữ ký và các claim bắt buộc được xác minh. Việc decode JWT thành công không chứng minh token hợp lệ.

Với opaque token, không thể decode claim từ chuỗi token. Hãy kiểm tra response introspection và active, sau đó kiểm tra cách Resource Server ánh xạ metadata thành principal/authority. Không áp dụng giả định về claim JWT cho opaque token.

## 3. Kiểm tra claim được phát hành từ Authorization Server

Khi Resource Server báo thiếu scope, roles, aud hoặc tenant_id, cần xác định claim có thực sự được phát hành trong access token hay không. Đừng chỉ nhìn vào cấu hình client hoặc ID Token.

Trong Spring Authorization Server, có thể tùy biến JWT access token bằng OAuth2TokenCustomizer<JwtEncodingContext>. Ví dụ thêm audience và claim quyền cho access token:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> accessTokenCustomizer() {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        context.getClaims().claim(
                "aud",
                List.of("https://api.example.test")
        );

        context.getClaims().claim(
                "roles",
                List.of("ORDER_READER")
        );
    };
}
~~~

Đây là ví dụ minh họa; policy thực tế phải xác định audience và role từ client, authorization hoặc nguồn quyền đáng tin cậy. Không cấp role quản trị chỉ vì client gửi một tham số tùy ý. Nếu token format là opaque, JWT customizer không phải điểm phát hành claim; cần kiểm tra custom access token format và introspection metadata tương ứng.

Khi kiểm tra token được phát hành, xác minh:

- Token đang kiểm tra là access token đúng của lần gọi API.
- Claim nằm trong access token, không phải chỉ trong ID Token.
- Tên claim đúng chính tả và đúng chữ hoa/thường.
- Giá trị claim đúng kiểu JSON mà Resource Server mong đợi.
- Claim được thêm vào trước khi ký token.
- Token thực tế được tạo từ đúng issuer, client, grant type và cấu hình.
- Không có customizer khác ghi đè hoặc xóa claim sau đó.

Một số lỗi phổ biến:

| Triệu chứng | Nguyên nhân có thể |
|---|---|
| Token không có roles | Customizer không chạy cho access token hoặc điều kiện token type sai |
| Claim chỉ xuất hiện trong ID Token | Logic tùy biến đang chạy cho OIDC ID Token |
| scope là chuỗi nhưng converter mong mảng | Hai bên không thống nhất schema claim |
| aud không có API đích | Audience chưa được thêm hoặc token được phát hành cho resource khác |
| Node A có claim, node B không có | Cấu hình customizer hoặc deployment không đồng nhất |
| Claim có giá trị cũ | Nguồn quyền/cache chưa được cập nhật trước khi phát hành token |

## 4. Kiểm tra kiểu dữ liệu và tên claim

JWT claims là JSON. Tên claim và kiểu dữ liệu phải thống nhất giữa Authorization Server và Resource Server. Các giá trị có vẻ tương đương trong log có thể không tương đương khi converter đọc chúng.

Ví dụ các dạng scope thường gặp:

~~~json
{
  "scope": "openid profile orders.read"
}
~~~

~~~json
{
  "scp": ["openid", "profile", "orders.read"]
}
~~~

Ví dụ roles:

~~~json
{
  "roles": ["ORDER_READER", "ORDER_OPERATOR"]
}
~~~

Các trường hợp dễ gây lỗi:

- scope thay vì scp, hoặc ngược lại.
- roles thay vì authorities.
- role là một chuỗi nhưng converter mong danh sách.
- Scope dạng chuỗi nhưng được ngăn cách bằng dấu phẩy thay vì khoảng trắng.
- Claim lồng trong object, ví dụ realm_access.roles, trong khi converter chỉ đọc claim cấp cao nhất.
- Giá trị role có prefix ROLE_ nhưng converter lại tự thêm prefix lần nữa.
- Claim có kiểu number/boolean trong khi logic đang ép thành string.

JWT claim names phân biệt chữ hoa/chữ thường. roles, Roles và ROLE là các tên khác nhau. Nếu thay đổi schema claim, phải triển khai đồng bộ Authorization Server và Resource Server, đồng thời xem xét token cũ còn hiệu lực đang mang schema trước đó.

Không sửa token bằng cách decode rồi thay payload. Chữ ký sẽ không còn hợp lệ. Cần sửa nguồn phát hành hoặc converter và cấp token mới.

## 5. Kiểm tra scope được ánh xạ thành GrantedAuthority

Spring Security Resource Server mặc định dùng JwtGrantedAuthoritiesConverter để chuyển scope thành authority. Theo cấu hình mặc định, converter tìm claim scope hoặc scp, tách scope và thêm prefix SCOPE_.

Ví dụ token có:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

có thể tạo các authority:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Vì vậy, rule:

~~~java
.requestMatchers("/orders/**").hasAuthority("SCOPE_orders.read")
~~~

phù hợp với authority mặc định. Rule hasAuthority("orders.read") sẽ không khớp nếu converter đã thêm prefix SCOPE_.

### 5.1 Scope claim không đúng tên

Nếu Authorization Server phát hành permissions thay cho scope, converter mặc định sẽ không tự hiểu claim đó. Có thể cấu hình claim name:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter authoritiesConverter =
            new JwtGrantedAuthoritiesConverter();

    authoritiesConverter.setAuthoritiesClaimName("permissions");
    authoritiesConverter.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(authoritiesConverter);

    return converter;
}
~~~

Khi đó token cần có cấu trúc phù hợp, ví dụ permissions: "orders.read orders.write" nếu converter đang tách chuỗi theo khoảng trắng. Nếu claim là JSON array, xác minh converter/version đang dùng xử lý đúng kiểu đó. Có thể viết converter riêng nếu schema của hệ thống khác quy ước mặc định.

### 5.2 Prefix bị thiếu hoặc bị nhân đôi

Nếu authorityPrefix được đặt thành chuỗi rỗng, authority có thể là orders.read. Nếu converter thêm SCOPE_ trong khi claim đã chứa SCOPE_orders.read, kết quả có thể thành SCOPE_SCOPE_orders.read.

Hãy ghi log danh sách authority sau xác thực trong môi trường test/dev hoặc đặt breakpoint tại JwtAuthenticationConverter. Không ghi raw token. So sánh authority thực tế với biểu thức trong authorizeHttpRequests hoặc @PreAuthorize.

### 5.3 Scope không phải role

Scope và role thường biểu diễn hai khái niệm khác nhau:

- Scope mô tả quyền mà client được phép yêu cầu đối với resource, ví dụ orders.read.
- Role mô tả vai trò nghiệp vụ của principal, ví dụ ORDER_ADMIN.

Không tự động biến mọi scope thành role hoặc ngược lại. Nếu endpoint yêu cầu role, hãy cấp role từ nguồn quyền tin cậy và map rõ ràng. Dùng hasAuthority("SCOPE_orders.read") cho scope và hasRole("ORDER_ADMIN") cho role theo quy ước prefix của Spring Security.

## 6. Kiểm tra role và authority mapping

hasRole("ADMIN") trong Spring Security thường tương đương kiểm tra authority ROLE_ADMIN. Trong khi đó, hasAuthority("ADMIN") so sánh chính xác chuỗi ADMIN, không tự thêm prefix.

Bảng đối chiếu:

| Rule | Authority cần có |
|---|---|
| hasAuthority("SCOPE_orders.read") | SCOPE_orders.read |
| hasAuthority("ROLE_ORDER_ADMIN") | ROLE_ORDER_ADMIN |
| hasRole("ORDER_ADMIN") | ROLE_ORDER_ADMIN |
| hasAuthority("ORDER_ADMIN") | ORDER_ADMIN |
| hasAnyRole("ORDER_ADMIN", "SUPPORT") | ROLE_ORDER_ADMIN hoặc ROLE_SUPPORT |

Nếu token có:

~~~json
{
  "roles": ["ORDER_ADMIN"]
}
~~~

thì mặc định JwtGrantedAuthoritiesConverter không tự biến claim roles thành ROLE_ORDER_ADMIN. Cần cấu hình converter riêng.

Ví dụ converter cho claim roles dạng array:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

    Converter<Jwt, Collection<GrantedAuthority>> rolesConverter = jwt -> {
        List<String> roles = jwt.getClaimAsStringList("roles");

        if (roles == null) {
            return Collections.emptyList();
        }

        return roles.stream()
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .toList();
    };

    Converter<Jwt, Collection<GrantedAuthority>> combined = jwt -> {
        Collection<GrantedAuthority> authorities =
                new ArrayList<>(scopeConverter.convert(jwt));

        authorities.addAll(rolesConverter.convert(jwt));
        return authorities;
    };

    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(combined);

    return converter;
}
~~~

Ví dụ trên yêu cầu Java version hỗ trợ Stream.toList(); với Java cũ hơn, thay bằng collector tương ứng. Cần bổ sung các import Spring Security và Java Collections/Converter. Nếu role claim lồng trong object hoặc có schema phức tạp, viết extractor có kiểm tra kiểu dữ liệu và từ chối giá trị không hợp lệ.

Không thêm prefix mù quáng. Nếu claim đã chứa ROLE_ORDER_ADMIN, việc nối thêm ROLE_ sẽ tạo authority sai. Hãy quyết định một schema thống nhất: claim lưu tên role thuần hay lưu authority hoàn chỉnh.

## 7. Kiểm tra issuer và audience

Một token có thể có chữ ký hợp lệ nhưng vẫn không dành cho Resource Server đang xử lý request. Hai claim quan trọng là:

- iss: Authorization Server phát hành token.
- aud: resource/client mà token được phát hành cho.

Issuer phải khớp giá trị Resource Server tin cậy. Audience của access token phải chứa định danh API đích theo policy. Không dùng azp thay cho aud; azp có ý nghĩa trong ngữ cảnh OIDC client và không thay thế kiểm tra audience của API.

### 7.1 Kiểm tra issuer

Nếu Resource Server cấu hình bằng issuer URI, Spring Security có thể tự cấu hình issuer validation theo URI đó. Nếu tự tạo JwtDecoder bằng JWK Set URI, phải thêm validator issuer rõ ràng.

~~~java
NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(
                "https://auth.example.test"
        )
);
~~~

Nếu token có iss khác do sai hostname, scheme, path hoặc trailing slash, decoder sẽ từ chối. So sánh chính xác issuer trong token với issuer được cấu hình, đồng thời kiểm tra discovery metadata và cấu hình reverse proxy.

### 7.2 Kiểm tra audience

Không nên giả định việc xác minh chữ ký hoặc issuer tự động xác minh audience. Nếu API yêu cầu audience cụ thể, bổ sung validator:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    if (jwt.getAudience().contains("https://api.example.test")) {
        return OAuth2TokenValidatorResult.success();
    }

    OAuth2Error error = new OAuth2Error(
            OAuth2ErrorCodes.INVALID_TOKEN,
            "Required audience is missing",
            null
    );
    return OAuth2TokenValidatorResult.failure(error);
};

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator
        )
);
~~~

Ví dụ trên yêu cầu ít nhất một audience khớp. Nếu policy yêu cầu đúng một audience, phải kiểm tra thêm số lượng và nội dung danh sách. Cần thống nhất cách biểu diễn audience giữa Authorization Server và Resource Server.

### 7.3 Audience thiếu ngay từ token được phát hành

Nếu Resource Server yêu cầu https://api.example.test nhưng access token không có audience đó, kiểm tra cấu hình phát hành token. Với JWT access token, có thể thêm claim aud bằng OAuth2TokenCustomizer<JwtEncodingContext> như ví dụ ở phần 3. Nếu ứng dụng hỗ trợ resource indicators, kiểm tra client có gửi resource phù hợp và Authorization Server có áp dụng policy mapping đúng không.

Không phát hành cùng một audience chung cho mọi API nếu điều đó khiến token có thể dùng chéo giữa các resource server. Audience nên phản ánh đích sử dụng và được kiểm tra ở từng API.

## 8. Kiểm tra endpoint authorization rule và method security

Sau khi xác minh token và authority mapping, kiểm tra rule bảo vệ endpoint. Một lỗi phổ biến là converter tạo SCOPE_orders.read nhưng endpoint yêu cầu ROLE_ORDERS_READ, hoặc rule dùng hasRole trong khi authority không có prefix ROLE_.

Ví dụ cấu hình:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .requestMatchers("/admin/**")
                .hasRole("ORDER_ADMIN")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(resourceServer -> resourceServer
            .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    jwtAuthenticationConverter()))
        );

    return http.build();
}
~~~

Khi bật method security, kiểm tra thêm annotation:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Order getOrder(String id) {
    // ...
}
~~~

Request có thể vượt qua filter-chain matcher nhưng vẫn bị từ chối ở method security. Ngược lại, một endpoint có matcher quá rộng có thể được phép ở filter chain nhưng business method lại thiếu kiểm tra ownership hoặc tenant.

Kiểm tra:

- Đúng SecurityFilterChain có xử lý request path không?
- Request matcher có đúng HTTP method và path không?
- Có chain nào có @Order cao hơn bắt request trước không?
- JwtAuthenticationConverter có được gắn vào đúng Resource Server chain không?
- @EnableMethodSecurity có bật nếu ứng dụng dựa vào @PreAuthorize không?
- Biểu thức hasRole/hasAuthority có đúng prefix không?
- Có custom AuthorizationManager hoặc access decision logic ghi đè rule không?
- Business logic có kiểm tra ownership, tenant và trạng thái tài nguyên không?

Không chỉ dựa vào role cấp cao để bảo vệ dữ liệu đa tenant. Một người dùng có quyền orders.read vẫn chỉ được đọc các order thuộc tenant hoặc phạm vi được cấp.

## 9. Chẩn đoán opaque token và introspection

Nếu Resource Server dùng opaque token, luồng xác thực khác JWT:

1. Client gửi bearer token tới API.
2. Resource Server gọi introspection endpoint của Authorization Server.
3. Authorization Server trả metadata token, trong đó active cho biết token có đang active theo chính sách hay không.
4. Resource Server chuyển metadata thành principal và authority.

Khi token bị 401, kiểm tra:

- Introspection endpoint có truy cập được không?
- Client dùng để gọi introspection có xác thực đúng không?
- Response có active: true không?
- Token có hết hạn hoặc bị revoke không?
- Audience/resource có được trả về và được validator kiểm tra không?
- Resource Server có cache introspection result quá lâu không?

Khi token bị 403, kiểm tra metadata scope/authority và OpaqueTokenIntrospector. Mặc định, Spring Security ánh xạ scope trong introspection response thành authority có prefix SCOPE_ theo cơ chế tương ứng. Nếu Authorization Server trả claim custom như roles, cần custom introspector hoặc converter để map role.

Không áp dụng JWT JwtDecoder để xử lý opaque token. Ngược lại, không dùng introspection chỉ để che một cấu hình JWT decoder sai nếu kiến trúc đang dùng JWT local validation.

## 10. Kiểm thử và tái hiện lỗi claims/permissions

Một bộ kiểm thử tốt cần cô lập từng validator và từng bước mapping. Nếu test issuer sai đồng thời chữ ký sai, test chỉ chứng minh chữ ký bị từ chối. Nếu test scope thiếu đồng thời token hết hạn, kết quả 401 không chứng minh authorization rule hoạt động.

### 10.1 Unit test cho audience validator

Tạo JWT fixture có chữ ký/decoder phù hợp với test, issuer và thời hạn hợp lệ; chỉ thay audience. Có thể kiểm tra trực tiếp OAuth2TokenValidator<Jwt>:

~~~java
@Test
void rejectsTokenForDifferentAudience() {
    Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .issuer("https://auth.example.test")
            .subject("user-123")
            .audience(List.of("https://billing.example.test"))
            .issuedAt(Instant.now())
            .expiresAt(Instant.now().plusSeconds(300))
            .build();

    OAuth2TokenValidatorResult result =
            audienceValidator.validate(jwt);

    assertThat(result.hasErrors()).isTrue();
}
~~~

Đây là test validator trực tiếp, không xác minh chữ ký. Cần có test tích hợp riêng với JWT ký thật bằng test key để chứng minh decoder chạy cả signature, issuer, thời hạn và audience validator.

### 10.2 Test scope-to-authority mapping

Test converter với các dạng claim:

| Claim đầu vào | Authority mong đợi |
|---|---|
| scope: "orders.read" | SCOPE_orders.read |
| scp: ["orders.read"] | Phụ thuộc converter/configuration được chọn |
| roles: ["ORDER_ADMIN"] | ROLE_ORDER_ADMIN nếu custom role converter được cấu hình |
| roles: ["ROLE_ORDER_ADMIN"] | Chỉ đúng nếu converter không thêm prefix lần nữa hoặc đã chuẩn hóa |
| Không có scope/roles | Không tự sinh authority nghiệp vụ |

Xác minh danh sách GrantedAuthority sau converter, không chỉ assert claim có trong JWT.

### 10.3 Test endpoint với token thiếu quyền

Có thể dùng Spring Security Test jwt() request post-processor để kiểm tra authorization rule của endpoint:

~~~java
mockMvc.perform(get("/orders/123")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
        )))
    .andExpect(status().isForbidden());
~~~

Cách này tạo Authentication test trực tiếp, thường không chạy quá trình decode và validate JWT thật. Nó hữu ích để kiểm tra rule endpoint, nhưng không chứng minh issuer, signature, audience hoặc converter production hoạt động đúng. Bổ sung integration test gửi JWT thật được ký bằng test key qua Resource Server.

### 10.4 Ma trận kiểm thử tối thiểu

| Test ID | Đầu vào | Kết quả mong đợi |
|---|---|---|
| CLAIM-01 | Thiếu claim scope | Không có scope authority |
| CLAIM-02 | Scope sai kiểu JSON | Converter xử lý theo policy, không tự cấp quyền |
| CLAIM-03 | Claim roles sai tên | Không tạo role authority |
| CLAIM-04 | Role có prefix bị nhân đôi | Endpoint từ chối do không khớp authority |
| ISS-01 | Issuer khác | 401 / invalid token |
| ISS-02 | Thiếu issuer | Token bị từ chối |
| AUD-01 | Audience là API khác | 401 / invalid token |
| AUD-02 | Thiếu audience bắt buộc | 401 / invalid token |
| AUTH-01 | Token hợp lệ nhưng thiếu scope | 403 |
| AUTH-02 | Token có scope nhưng thiếu role | 403 |
| AUTH-03 | Đúng role nhưng sai tenant/owner | Từ chối theo business policy |
| OPAQUE-01 | Introspection trả active=false | 401 |
| OPAQUE-02 | Token active nhưng thiếu authority | 403 |

## 11. Quy trình xử lý production

Khi API bắt đầu trả 401/403 bất thường:

1. Ghi nhận endpoint, HTTP method, thời điểm, correlation ID và instance ID.
2. Xác định Resource Server đang dùng JWT hay opaque token.
3. Nếu 401, kiểm tra bearer extraction, chữ ký, issuer, audience, thời hạn hoặc introspection active.
4. Nếu 403, kiểm tra principal và danh sách GrantedAuthority sau authentication.
5. Đối chiếu claim thực tế với schema và policy đã thống nhất; dùng token fixture hoặc fingerprint nội bộ để liên kết log.
6. Kiểm tra converter, authority prefix, security matcher và method security.
7. Kiểm tra tenant/ownership policy tại business layer.
8. Tái hiện trên test environment với một token hợp lệ và một claim thay đổi duy nhất.
9. Triển khai sửa đổi đồng bộ và theo dõi tỷ lệ 401/403 sau khi phát hành.

Trong production, không log toàn bộ JWT hoặc claim nhạy cảm. Có thể ghi tên claim cần thiết, loại lỗi validator, audience đã chuẩn hóa, issuer category, client ID và correlation ID theo chính sách dữ liệu. Tránh log PII hoặc quyền chi tiết của người dùng nếu không cần cho điều tra.

Khi thay đổi claim schema, converter hoặc audience policy, cân nhắc token cũ còn hiệu lực. Resource Server có thể nhận token phát hành trước deployment với claim format khác. Có thể cần thời gian chuyển tiếp hỗ trợ schema cũ, rút ngắn TTL token, hoặc buộc cấp token mới theo kế hoạch. Không nới lỏng audience/issuer validator để giữ tương thích với token sai đích.

Một báo cáo xử lý tốt nêu rõ lỗi nằm ở phát hành claim, xác thực JWT/introspection, ánh xạ authority hay authorization rule; ghi lại test đã tái hiện và kết quả sau sửa. Khi theo dõi đủ chuỗi từ claim đến GrantedAuthority và endpoint policy, đội vận hành có thể sửa lỗi 401/403 chính xác mà vẫn giữ được ranh giới tin cậy của OAuth 2.0/OpenID Connect.


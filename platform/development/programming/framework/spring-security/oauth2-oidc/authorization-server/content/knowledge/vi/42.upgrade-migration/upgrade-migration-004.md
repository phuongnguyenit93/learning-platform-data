# Cập nhật Java DSL, API bị deprecated và điểm mở rộng công khai

Spring Authorization Server và Spring Security phát triển theo từng phiên bản. Khi nâng cấp, cấu hình bảo mật có thể cần chuyển từ các adapter cũ sang bean `SecurityFilterChain`, từ cách nối chuỗi bằng `and()` sang lambda DSL, hoặc từ API đã deprecated sang điểm mở rộng công khai mới. Nếu chỉ sửa cho hết lỗi biên dịch, hệ thống vẫn có thể thay đổi thứ tự filter, phạm vi matcher, cách xử lý consent hoặc cách phát hành token.

Bài học này trình bày cách đọc thay đổi API, tổ chức lại Java DSL, chọn đúng SPI công khai và kiểm chứng hành vi OAuth 2.0/OpenID Connect sau nâng cấp. Các ví dụ dùng phong cách cấu hình hiện đại của Spring Security và Spring Authorization Server. Tên phương thức và khả năng tương thích cụ thể phụ thuộc phiên bản đang dùng; hãy đối chiếu Javadoc và migration notes của đúng phiên bản đích trước khi áp dụng.

## Mục tiêu

Sau bài học, bạn có thể:

- Nhận diện các cấu hình cũ thường gặp và xác định hướng chuyển đổi tương ứng.
- Tổ chức nhiều `SecurityFilterChain` bằng matcher và thứ tự rõ ràng.
- Viết Java DSL bằng lambda và cấu hình `OAuth2AuthorizationServerConfigurer` theo API của phiên bản đích.
- Phân biệt API cấu hình với các điểm mở rộng công khai dành cho lưu trữ, xác thực, token và khóa.
- Thay thế cách tùy biến dựa trên lớp nội bộ bằng các interface hoặc customizer được hỗ trợ.
- Nâng cấp theo từng bước và kiểm thử các luồng authorization code, PKCE, client authentication, refresh token và OIDC.

## 1. Bắt đầu bằng việc xác định phiên bản

Trước khi sửa code, hãy ghi nhận phiên bản của Java, Spring Boot, Spring Framework, Spring Security và Spring Authorization Server. Các thành phần này có quan hệ tương thích; nâng riêng một thư viện có thể đưa vào một API mà phiên bản còn lại chưa hỗ trợ.

Với dự án Spring Boot, ưu tiên dùng dependency management hoặc BOM do phiên bản Boot quản lý. Chỉ override phiên bản Spring Security hoặc Spring Authorization Server khi đã xác minh ma trận tương thích và có lý do rõ ràng. Tránh khai báo nhiều phiên bản khác nhau của các module `spring-security-*` trong cùng ứng dụng.

Lập danh sách cấu hình và điểm mở rộng hiện có trước khi thay đổi:

| Khu vực | Cần kiểm kê |
|---|---|
| Security configuration | `WebSecurityConfigurerAdapter`, các bean `SecurityFilterChain`, thứ tự chain và matcher |
| Authorization Server | `OAuth2AuthorizationServerConfigurer`, endpoint matcher, OIDC và các endpoint tùy chỉnh |
| Client và consent | `RegisteredClientRepository`, `OAuth2AuthorizationConsentService` |
| Authorization | `OAuth2AuthorizationService`, chính sách lưu và thu hồi token |
| Token | `OAuth2TokenGenerator`, `OAuth2TokenCustomizer`, converter và provider tùy chỉnh |
| Khóa | `JWKSource`, `JwtEncoder`, keystore hoặc KMS/HSM |
| Tích hợp | Resource Server, login, CORS, CSRF, method security và filter tự viết |

Ghi lại hành vi hiện tại của từng luồng: endpoint được gọi, client authentication method, grant type, scope, định dạng token, consent, thời hạn token và cách thu hồi. Đây là cơ sở để so sánh trước và sau nâng cấp.

## 2. Những thay đổi Java DSL thường gặp

Các thay đổi dưới đây là hướng chuyển đổi phổ biến khi ứng dụng tiến từ cấu hình Spring Security đời cũ sang cấu hình bean và lambda DSL. Không phải mọi phương thức cũ đều bị xóa trong cùng một phiên bản. Hãy kiểm tra chú thích `@Deprecated`, phiên bản đánh dấu deprecated và phiên bản dự kiến loại bỏ trong Javadoc của thư viện đang dùng.

| Cách cấu hình cũ | Hướng chuyển đổi | Lý do |
|---|---|---|
| `WebSecurityConfigurerAdapter` | Khai báo bean `SecurityFilterChain` và `WebSecurityCustomizer` khi thực sự cần | Mỗi chain có thể được cấu hình và kiểm thử độc lập |
| `authorizeRequests()` | `authorizeHttpRequests(...)` | API phân quyền request hiện đại, hỗ trợ lambda DSL |
| `antMatchers(...)`, `mvcMatchers(...)` | `requestMatchers(...)` với matcher phù hợp | API matcher được hợp nhất theo phiên bản Spring Security |
| Nối `.and()` qua nhiều configurer | Cấu hình lồng bằng lambda | Giảm phụ thuộc vào kiểu trả về và làm rõ phạm vi cấu hình |
| `http.apply(configurer)` ở các phiên bản đã deprecated | `http.with(configurer, customizer)` nếu phiên bản đích hỗ trợ | Cách gắn configurer theo API mới |
| Cấu hình Authorization Server qua helper mặc định | Cấu hình rõ `OAuth2AuthorizationServerConfigurer` khi cần kiểm soát endpoint | Nhìn thấy matcher, OIDC và các điểm tùy biến tại một nơi |
| Dựa vào implementation nội bộ | Dùng interface, converter, provider và customizer công khai | Giảm phụ thuộc vào chi tiết triển khai có thể thay đổi |

### 2.1. Chuyển từ adapter sang `SecurityFilterChain`

Trong cấu hình cũ, một lớp thường kế thừa `WebSecurityConfigurerAdapter` rồi override phương thức cấu hình. Với cấu hình dựa trên bean, khai báo `SecurityFilterChain` trực tiếp:

```java
@Configuration
@EnableWebSecurity
public class ApplicationSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**", "/health/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

`SecurityFilterChain` biểu diễn một tập filter cùng điều kiện áp dụng. Khi có nhiều chain, chain được chọn theo thứ tự và matcher. Request chỉ đi qua chain phù hợp đầu tiên; vì vậy thứ tự và phạm vi matcher là một phần của logic bảo mật.

`WebSecurityCustomizer` chỉ nên dùng khi cần bỏ qua hoàn toàn Spring Security cho một số request tĩnh thực sự phù hợp. Với phần lớn endpoint, dùng `permitAll()` trong `authorizeHttpRequests` để request vẫn đi qua các filter cần thiết.

### 2.2. Chuyển sang lambda DSL

Ví dụ cấu hình theo kiểu nối chuỗi cũ:

```java
http
    .authorizeRequests()
        .antMatchers("/assets/**").permitAll()
        .anyRequest().authenticated()
    .and()
    .formLogin();
```

Viết lại bằng lambda DSL:

```java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/assets/**").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(Customizer.withDefaults());
```

Lambda DSL làm rõ mỗi cấu hình thuộc configurer nào. Không cần gọi `.and()` để quay lại đối tượng `HttpSecurity`. Khi di chuyển một cấu hình dài, hãy chuyển từng nhóm chức năng và giữ nguyên thứ tự rule phân quyền; rule tổng quát như `anyRequest()` phải đứng sau các rule cụ thể.

### 2.3. Chọn request matcher chính xác

Không thay mọi `antMatchers` bằng một chuỗi `requestMatchers` mà không xem lại ngữ nghĩa. Matcher có thể dựa trên đường dẫn, HTTP method, servlet path hoặc loại request. Kiểm tra:

- Đường dẫn có context path hoặc servlet path riêng hay không.
- Rule có giới hạn HTTP method hay đang áp dụng cho mọi method.
- Các endpoint nội bộ có bị matcher tổng quát bắt trước không.
- Có khác biệt giữa trailing slash, path variable và wildcard không.
- Request dispatch kiểu `FORWARD`, `ERROR` hoặc `ASYNC` có cần chính sách riêng không.

Với yêu cầu phức tạp, tạo matcher tường minh, đặt tên biến có ý nghĩa và viết kiểm thử cho cả trường hợp được phép lẫn bị từ chối. Đừng dựa vào việc hai matcher có cú pháp gần giống nhau để kết luận chúng có hành vi tương đương.

## 3. Cấu hình Authorization Server bằng configurer công khai

Authorization Server thường có một chain riêng cho các endpoint giao thức. Cách cấu hình tường minh giúp ứng dụng kiểm soát matcher của các endpoint và bật OIDC tại đúng nơi.

Ví dụ cho các phiên bản Spring Authorization Server cung cấp factory `OAuth2AuthorizationServerConfigurer.authorizationServer()` và Spring Security hỗ trợ `HttpSecurity.with(...)`:

```java
@Configuration
public class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer
                    .oidc(Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là mẫu cấu hình cho API có trong phiên bản đích. Với bản cũ hơn, constructor, generic type hoặc cách gắn configurer có thể khác; không sao chép nguyên mẫu vào một phiên bản chưa hỗ trợ. Dùng Javadoc của artifact đang được build để xác nhận chữ ký thực tế.

Một số điểm cần chú ý:

- `getEndpointsMatcher()` gom các endpoint do Authorization Server quản lý. Dùng matcher này để chain giao thức không vô tình áp dụng cho toàn bộ ứng dụng.
- `@Order(1)` khiến chain Authorization Server được xét trước chain ứng dụng. Nếu thứ tự ngược lại, chain ứng dụng có thể bắt request trước.
- Chain ứng dụng phải có matcher hoặc rule phù hợp cho các request còn lại.
- Bật OIDC bằng `oidc(...)` khi hệ thống cần các chức năng OpenID Connect; không bật chỉ vì ứng dụng sử dụng OAuth 2.0.
- Mỗi `HttpSecurity` chỉ được build thành một `SecurityFilterChain`. Không tái sử dụng cùng một đối tượng đã build cho nhiều bean.

### 3.1. Tùy chỉnh endpoint và consent

Các configurer con là điểm cấu hình công khai cho từng nhóm endpoint. Ví dụ, trang consent có thể được chuyển đến giao diện do ứng dụng quản lý. Đoạn mã sau thay phần nội dung callback `.with(...)` trong ví dụ cấu hình trước; không gọi `.with(...)` lần thứ hai cho cùng configurer:

```java
http.with(authorizationServerConfigurer, authorizationServer ->
    authorizationServer
        .authorizationEndpoint(authorizationEndpoint ->
            authorizationEndpoint.consentPage("/oauth2/consent")
        )
        .oidc(Customizer.withDefaults())
);
```

Trang consent cần hiển thị client, scope và thông tin quyền cần chấp thuận từ dữ liệu đã được máy chủ xác thực. Khi gửi quyết định consent, trình duyệt phải quay lại endpoint được thiết kế cho luồng authorization và giữ đúng các tham số giao thức. Không tự tạo endpoint nhận consent mà bỏ qua kiểm tra trạng thái, client hoặc authorization request.

Tùy theo phiên bản và nhu cầu, configurer còn cung cấp các khu vực như client authentication, token endpoint, authorization endpoint, device authorization, device verification, token introspection, token revocation và các endpoint OIDC. Chỉ cấu hình những chức năng ứng dụng thực sự sử dụng; kiểm tra chữ ký phương thức trong Javadoc vì API con có thể thay đổi theo release.

### 3.2. Cấu hình issuer và endpoint bằng `AuthorizationServerSettings`

Trong các phiên bản đã chuyển sang `AuthorizationServerSettings`, dùng bean này để định nghĩa issuer và đường dẫn endpoint. Ví dụ:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .build();
}
```

Nếu cần thay đổi endpoint path, builder cung cấp các thuộc tính tương ứng theo phiên bản, chẳng hạn authorization endpoint, token endpoint, JWK Set endpoint, introspection và revocation. Không đổi issuer tùy tiện giữa các môi trường: issuer là định danh được đưa vào metadata và token, đồng thời được resource server dùng để xác minh nguồn phát hành.

Khi chuyển từ các cấu hình cũ như `ProviderSettings`, kiểm tra phiên bản đánh dấu API đó deprecated và dùng `AuthorizationServerSettings` nếu phiên bản đích cung cấp. Xác minh discovery metadata, issuer trong token và các URL endpoint sau khi nâng cấp.

## 4. Phân biệt cấu hình với điểm mở rộng công khai

Java DSL quyết định cách ghép các thành phần bảo mật. Điểm mở rộng công khai quyết định ứng dụng thay đổi hành vi nghiệp vụ ở đâu. Nên chọn đúng loại extension point thay vì thay thế filter hoặc provider nội bộ khi không cần thiết.

| Nhu cầu | Điểm mở rộng nên xem xét |
|---|---|
| Lưu client đã đăng ký | `RegisteredClientRepository` |
| Lưu authorization và token đã cấp | `OAuth2AuthorizationService` |
| Lưu quyết định consent | `OAuth2AuthorizationConsentService` |
| Tùy chỉnh claim JWT | `OAuth2TokenCustomizer<JwtEncodingContext>` |
| Tùy chỉnh claim access token opaque | `OAuth2TokenCustomizer<OAuth2TokenClaimsContext>` |
| Sinh token | `OAuth2TokenGenerator` và các generator được hỗ trợ |
| Xác thực request tại endpoint | `AuthenticationConverter` và `AuthenticationProvider` |
| Cung cấp khóa ký và JWKS | `JWKSource<SecurityContext>` hoặc tích hợp signer phù hợp |
| Cấu hình issuer và endpoint | `AuthorizationServerSettings` |
| Tùy chỉnh endpoint | Configurer công khai của endpoint tương ứng |

Các interface này có hợp đồng và trách nhiệm khác nhau. Ví dụ, repository lưu trữ dữ liệu client không thay thế dịch vụ lưu authorization; customizer thay đổi claim không thay thế quy trình xác thực request; còn `AuthenticationProvider` không nên tự viết lại toàn bộ filter chain.

### 4.1. Lưu trữ client, authorization và consent

Ba abstraction lưu trữ quan trọng có vai trò riêng:

- `RegisteredClientRepository` tìm và lưu cấu hình client như client ID, phương thức xác thực, grant type, redirect URI, scope và thời hạn token.
- `OAuth2AuthorizationService` lưu trạng thái authorization cùng token và metadata liên quan, hỗ trợ tìm kiếm theo ID hoặc token.
- `OAuth2AuthorizationConsentService` lưu các scope mà resource owner đã chấp thuận cho client.

Khi chuyển từ in-memory sang JDBC hoặc kho dữ liệu riêng, cần giữ nguyên ngữ nghĩa của `save`, `remove`, các phương thức tra cứu và cách xử lý token đã thu hồi. Với dữ liệu authorization, không chỉ lưu chuỗi token: cần bảo toàn trạng thái, thời điểm phát hành/hết hạn, metadata và thông tin cần cho introspection hoặc revoke.

Nếu tự triển khai một repository hoặc service, hãy dùng interface công khai và kiểm thử các trường hợp không tìm thấy bản ghi, cập nhật đồng thời, thu hồi, hết hạn và khởi động lại ứng dụng. Không kế thừa lớp triển khai JDBC chỉ để ghi đè một phương thức nội bộ nếu API công khai không cam kết hỗ trợ cách đó.

### 4.2. Tùy chỉnh JWT bằng `OAuth2TokenCustomizer`

Khi cần thêm claim cho JWT, dùng `OAuth2TokenCustomizer<JwtEncodingContext>`:

```java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            context.getClaims().claim("application", "rental-api");
        }
    };
}
```

Ví dụ chỉ thêm một claim tĩnh để minh họa vị trí tùy biến. Trong ứng dụng thực tế, chỉ thêm dữ liệu đã được xác thực và cần thiết cho bên nhận token. Không đưa mật khẩu, client secret, refresh token, dữ liệu cá nhân không cần thiết hoặc thông tin nội bộ nhạy cảm vào JWT vì token có thể được nhiều thành phần đọc.

Kiểm tra `context.getTokenType()` trước khi thêm claim để tránh vô tình áp dụng cùng một dữ liệu cho ID token và access token. Nếu claim phụ thuộc vào client hoặc principal, xác định rõ nguồn dữ liệu, quyền truy cập và tác động khi dữ liệu thay đổi.

Với access token dạng opaque/reference, customizer phù hợp là `OAuth2TokenCustomizer<OAuth2TokenClaimsContext>` khi generator và phiên bản đang dùng hỗ trợ. Không dùng JWT customizer để kỳ vọng thay đổi nội dung token opaque.

### 4.3. Thay đổi token generator

`OAuth2TokenGenerator` là abstraction để sinh access token, refresh token hoặc token định dạng JWT tùy cấu hình. Khi cần thay đổi cách sinh token, hãy xác định loại token và generator phù hợp trước khi tạo generator tùy chỉnh.

Ví dụ cấu trúc thường gặp trong ứng dụng phát hành JWT:

```java
JwtGenerator jwtGenerator = new JwtGenerator(jwtEncoder);
jwtGenerator.setJwtCustomizer(jwtTokenCustomizer);

OAuth2AccessTokenGenerator accessTokenGenerator =
    new OAuth2AccessTokenGenerator();

OAuth2TokenGenerator<?> tokenGenerator =
    new DelegatingOAuth2TokenGenerator(
        jwtGenerator,
        accessTokenGenerator,
        new OAuth2RefreshTokenGenerator()
    );
```

Đoạn mã minh họa cách kết hợp generator, không phải cấu hình đầy đủ cho mọi hệ thống. Cần cung cấp `JwtEncoder` dựa trên nguồn khóa phù hợp, cấu hình customizer cho access token opaque nếu sử dụng, và xác nhận generator được gắn vào configurer hoặc bean theo cơ chế của phiên bản đích. Không thêm hoặc bỏ generator mà chưa kiểm tra định dạng token, grant type và chính sách refresh token hiện tại.

### 4.4. Thêm grant type tùy chỉnh

Khi giao thức nghiệp vụ yêu cầu một grant type riêng, điểm tích hợp chính thường là converter và provider ở token endpoint:

1. `AuthenticationConverter` đọc HTTP request, xác minh cấu trúc tham số và chuyển thành một loại `Authentication` dành cho grant đó.
2. `AuthenticationProvider` kiểm tra client, principal, điều kiện cấp quyền và dữ liệu đầu vào; từ chối request sai bằng lỗi OAuth phù hợp.
3. Provider dùng các dịch vụ công khai như `OAuth2AuthorizationService` và `OAuth2TokenGenerator` để lưu authorization và sinh token.
4. Đăng ký converter và provider với token endpoint configurer theo API của phiên bản đang dùng.

Ví dụ dạng cấu hình:

```java
authorizationServerConfigurer.tokenEndpoint(tokenEndpoint ->
    tokenEndpoint
        .accessTokenRequestConverter(customGrantAuthenticationConverter)
        .authenticationProvider(customGrantAuthenticationProvider)
);
```

Đây là điểm đăng ký; hai thành phần `customGrantAuthenticationConverter` và `customGrantAuthenticationProvider` phải được triển khai với kiểu `Authentication` riêng, kiểm tra đầy đủ quyền của client và xử lý lỗi theo giao thức. Không chấp nhận một grant type chỉ vì client gửi tên grant trong request. Grant phải được cho phép trong cấu hình client và phải có chính sách xác thực, chống replay, thời hạn và thu hồi rõ ràng.

Nếu nhu cầu có thể đáp ứng bằng grant type chuẩn như authorization code với PKCE hoặc client credentials, ưu tiên giao thức chuẩn để giữ khả năng tương thích và giảm gánh nặng bảo mật.

### 4.5. Tùy chỉnh client authentication

Với phương thức xác thực client bổ sung, xem xét `AuthenticationConverter` và `AuthenticationProvider` của client authentication configurer. Converter phân tích thông tin xác thực từ request; provider xác minh client và credential theo phương thức đã đăng ký. Không tự đọc client secret từ request ở một filter rời rồi bỏ qua quy tắc lưu trữ, so sánh và xử lý lỗi của Authorization Server.

Khi hỗ trợ nhiều phương thức, kiểm tra `RegisteredClient` có khai báo đúng `ClientAuthenticationMethod` hay không. Thử cả trường hợp client dùng phương thức được phép, phương thức không được phép, credential sai, client không tồn tại và request chứa nhiều cách gửi credential cùng lúc.

## 5. Mở rộng endpoint bằng API được hỗ trợ

Mỗi endpoint có một nhóm extension point riêng. Hãy đặt tùy biến gần endpoint sở hữu nó để người bảo trì thấy rõ phạm vi tác động.

| Endpoint | Nhu cầu thường gặp | Hướng mở rộng |
|---|---|---|
| Authorization | Chuyển trang consent, thêm converter hoặc provider | Authorization endpoint configurer |
| Token | Thêm grant, xử lý request token hoặc tùy chỉnh response | Token endpoint configurer, converter, provider, generator |
| Client authentication | Thêm phương thức xác thực client | Client authentication configurer |
| Introspection | Tùy chỉnh cách kiểm tra token reference | Introspection endpoint configurer và service lưu authorization |
| Revocation | Điều chỉnh xử lý thu hồi | Revocation endpoint configurer và service lưu authorization |
| Device authorization/verification | Điều chỉnh giao diện hoặc xử lý device flow | Configurer của device endpoint |
| OIDC UserInfo | Ánh xạ claim người dùng được phép công bố | OIDC UserInfo endpoint configurer và mapper công khai |
| JWKS | Công bố khóa công khai | `JWKSource` và cấu hình khóa |

Không nên thêm filter vào trước hoặc sau một filter nội bộ của Authorization Server nếu một configurer hoặc SPI đã có thể đáp ứng nhu cầu. Vị trí filter nội bộ có thể thay đổi theo phiên bản, dẫn đến lỗi khó phát hiện như request bị xác thực hai lần, bỏ qua kiểm tra CSRF hoặc endpoint không nhận được lỗi OAuth đúng định dạng.

Nếu bắt buộc tích hợp filter riêng ở cấp ứng dụng, hãy xác định chain áp dụng, vị trí tương đối với filter chuẩn, cách xử lý exception và matcher. Viết kiểm thử chứng minh filter không can thiệp nhầm endpoint giao thức.

## 6. Quản lý khóa và tích hợp JWT

Nguồn khóa là một điểm mở rộng quan trọng nhưng không nên bị trộn với logic tùy biến claim. `JWKSource<SecurityContext>` cung cấp khóa phù hợp cho các thành phần JWT; `JwtEncoder` dùng khóa để ký. Tùy hạ tầng, khóa có thể đến từ keystore, secret manager, KMS hoặc HSM.

Khi nâng cấp cấu hình khóa:

- Giữ nguyên issuer và thuật toán được các bên tiêu thụ hỗ trợ, trừ khi có kế hoạch thay đổi giao thức.
- Đảm bảo `kid` duy nhất trong phạm vi JWKS và khóa công khai tương ứng được công bố.
- Không đóng gói private key hoặc mật khẩu keystore vào source control hay image.
- Kiểm tra quyền đọc/ ký của workload identity đối với KMS/HSM.
- Khi xoay vòng, công bố khóa công khai mới trước khi dùng khóa đó để ký; giữ khóa cũ trong thời gian các token đã phát hành còn cần xác minh.
- Kiểm thử cả quá trình khởi động, tải lại khóa và lỗi khi nguồn khóa tạm thời không sẵn sàng.

Không thay `JWKSource` bằng cách truy cập field hoặc lớp nội bộ của encoder. Nếu cần dùng HSM không cung cấp private key dưới dạng JWK, thiết kế tích hợp signer theo API công khai tương thích với thư viện JWT được chọn và kiểm thử chữ ký bằng public key.

## 7. Những lỗi nâng cấp thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Endpoint token trả 404 hoặc bị chain ứng dụng chặn | Matcher hoặc thứ tự `SecurityFilterChain` sai | Kiểm tra `getEndpointsMatcher()`, `@Order` và matcher của chain còn lại |
| Endpoint giao thức yêu cầu form login ngoài dự kiến | Chain ứng dụng bắt request trước hoặc chain Authorization Server không đúng phạm vi | Bật log bảo mật phù hợp trong môi trường thử nghiệm và xác nhận chain được chọn |
| Code biên dịch báo phương thức deprecated hoặc không tồn tại | Phiên bản đích đã đổi hoặc loại bỏ API | Đọc Javadoc và release notes đúng phiên bản; kiểm tra dependency tree |
| Scope hoặc consent thay đổi sau nâng cấp | Repository hoặc consent service có hành vi khác | So sánh bản ghi consent và request authorization trước/sau |
| JWT thiếu claim | Customizer không được gắn vào generator đúng cách hoặc điều kiện token type không khớp | Kiểm tra bean, generator và payload JWT trong test |
| JWT không xác minh được sau khi đổi cấu hình | Issuer, thuật toán, `kid` hoặc JWKS thay đổi | So sánh discovery metadata, JWKS và header JWT |
| Refresh token không hoạt động | Grant type, thời hạn, reuse/rotation hoặc lưu trữ authorization thay đổi | Kiểm tra cấu hình client, token generator và trạng thái authorization |
| Custom grant không được nhận | Converter không được đăng ký hoặc provider không hỗ trợ token xác thực | Kiểm tra thứ tự converter/provider và điều kiện `supports` |
| Tích hợp tự viết bị lỗi sau nâng cấp | Phụ thuộc implementation nội bộ hoặc thứ tự filter | Chuyển sang SPI công khai và kiểm thử hợp đồng tích hợp |

Không xử lý lỗi bằng cách hạ mức bảo vệ, cho phép mọi request hoặc tắt xác thực tạm thời trên môi trường thật. Hãy tái hiện lỗi bằng test hoặc môi trường staging và xác định chính xác chain, matcher hay extension point gây ra vấn đề.

## 8. Quy trình nâng cấp có kiểm soát

Một quy trình thực tế có thể chia thành các bước sau:

1. **Chốt phiên bản đích.** Xác nhận phiên bản Java, Spring Boot, Spring Security và Spring Authorization Server tương thích; ghi nhận dependency tree.
2. **Tạo baseline.** Chạy test hiện tại và lưu lại hành vi của các luồng OAuth/OIDC, metadata, JWKS và token.
3. **Lập danh sách API cần thay.** Tìm các adapter cũ, phương thức deprecated, matcher cũ, configurer tự viết và import từ package implementation.
4. **Chuyển Java DSL.** Đưa cấu hình sang `SecurityFilterChain`, lambda DSL và matcher tường minh; giữ nguyên thứ tự rule và thứ tự chain.
5. **Chuyển configurer Authorization Server.** Dùng API configurer của phiên bản đích; xác minh endpoint matcher, OIDC và các cấu hình con.
6. **Di chuyển extension point.** Chuyển lưu trữ sang repository/service công khai, tùy chỉnh token bằng customizer và tích hợp grant/authentication qua converter/provider.
7. **Kiểm thử hồi quy.** Chạy kiểm thử chức năng và bảo mật cho từng grant, endpoint, consent, token, khóa và lỗi.
8. **Triển khai thử và quan sát.** So sánh tỷ lệ lỗi, độ trễ, số token phát hành, lỗi xác minh và dữ liệu authorization giữa bản cũ và bản mới.
9. **Triển khai theo kế hoạch rollback.** Giữ khả năng quay lại phiên bản ứng dụng và dữ liệu tương thích trong thời gian chuyển đổi; không rollback bằng cách phục hồi dữ liệu đã mất hoặc làm sống lại token đã thu hồi.

Nâng cấp theo từng nhóm thay đổi giúp xác định nguyên nhân nhanh hơn. Nếu thay DSL, repository, generator và khóa cùng lúc, một lỗi cấp token có thể bắt nguồn từ nhiều khu vực và khó khoanh vùng.

## 9. Kiểm thử sau khi cập nhật

Không xem việc build thành công là bằng chứng nâng cấp hoàn tất. Cần xác minh hành vi giao thức và chính sách bảo mật.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Discovery metadata | Issuer, endpoint và capability công bố đúng |
| JWKS | Khóa công khai có `kid` đúng và xác minh được chữ ký token |
| Authorization Code | Redirect URI, state, code exchange và client authentication đúng |
| PKCE | `code_verifier` hợp lệ được chấp nhận; verifier sai hoặc thiếu bị từ chối theo chính sách |
| Consent | Scope được hiển thị, chấp thuận và từ chối đúng; consent đã lưu được đọc lại |
| Client Credentials | Chỉ client được phép mới nhận token với scope được cấp |
| Refresh Token | Client và grant được phép; token hết hạn, thu hồi hoặc không hợp lệ bị từ chối |
| Introspection/Revocation | Token active/inactive phản ánh đúng trạng thái lưu trữ và thu hồi |
| OIDC | ID token, UserInfo và logout hoạt động đúng nếu tính năng được bật |
| Negative cases | Client secret sai, redirect URI sai, scope không được phép và grant không hỗ trợ đều bị từ chối |
| Multi-chain security | Request được xử lý bởi đúng chain và không bỏ qua xác thực |

Với MockMvc, kiểm thử nên gửi request thực qua filter chain để xác minh matcher, CSRF và thứ tự filter. Kiểm thử service riêng vẫn hữu ích cho repository, customizer và provider, nhưng không thay thế kiểm thử tích hợp endpoint.

Kiểm tra thêm các thay đổi liên quan đến Java và Jakarta khi nâng từ hệ Spring cũ sang thế hệ Spring Boot mới. Nếu ứng dụng chuyển từ `javax.*` sang `jakarta.*`, cập nhật import, dependency và thư viện tích hợp tương ứng; không thay thế hàng loạt bằng thao tác văn bản mà không kiểm tra hợp đồng của thư viện.

## 10. Nguyên tắc giữ tích hợp bền vững

- Ưu tiên API được tài liệu hóa và public SPI. Một lớp nằm trong package `internal`, `impl` hoặc có phạm vi truy cập hạn chế thường không phải hợp đồng mở rộng ổn định.
- Giữ logic nghiệp vụ ở service của ứng dụng; dùng converter/provider để nối giao thức với service đó.
- Dùng customizer cho thay đổi claim hoặc metadata trong phạm vi được hỗ trợ, không sửa trực tiếp đối tượng nội bộ sau khi token đã phát hành.
- Tránh phụ thuộc vào thứ tự filter nội bộ nếu framework cung cấp configurer cho cùng nhu cầu.
- Giữ matcher, thứ tự chain và rule phân quyền ngắn gọn, có test thể hiện request nào được phép.
- Ghi rõ phiên bản API tối thiểu mà extension tùy chỉnh yêu cầu.
- Khi nâng thư viện, xử lý deprecation theo từng release và xóa adapter cũ sau khi test chứng minh hành vi tương đương.

## Kết luận

Nâng cấp Java DSL và API của Authorization Server cần bảo toàn hành vi bảo mật ở từng endpoint. `SecurityFilterChain`, lambda DSL và `OAuth2AuthorizationServerConfigurer` giúp cấu hình rõ ràng hơn; các SPI như repository, authorization service, token customizer, generator, converter và provider tạo ranh giới mở rộng ổn định. Khi chốt phiên bản tương thích, chuyển từng nhóm API, kiểm thử toàn bộ luồng OAuth/OIDC và quan sát sau triển khai, ứng dụng sẽ giảm phụ thuộc vào API cũ mà vẫn giữ đúng chính sách cấp và xác minh token.

# client_secret_jwt và xác minh client assertion

## 1. Bối cảnh và mục tiêu

Trong ứng dụng Spring Boot sử dụng **Spring Security** và **Spring Authorization Server** để xây dựng **OAuth 2.0/OpenID Connect (OIDC) Authorization Server**, client thường phải chứng minh danh tính trước khi được cấp token hoặc gọi một số endpoint giao thức. <code>client_secret_jwt</code> là một phương thức **client authentication**: client tạo một **JWT có chữ ký HMAC** bằng secret được chia sẻ với Authorization Server, rồi gửi JWT đó trong tham số <code>client_assertion</code>.

Ví dụ xuyên suốt: service <code>orders-batch</code> chạy tác vụ nội bộ và được đăng ký với grant <code>client_credentials</code>, scope <code>orders.read</code>. Service tạo assertion mới cho mỗi lần xác thực, ký bằng khóa HMAC là client secret, sau đó gửi đến <code>https://auth.example.com/oauth2/token</code>. Authorization Server xác minh assertion, kiểm tra client đã đăng ký và chỉ sau đó mới xử lý grant để cấp access token.

Bài học giúp bạn:

1. Phân biệt client assertion với **access token, ID Token, authorization grant** và client secret gửi trực tiếp qua HTTP.
2. Hiểu cách xây JWT assertion theo tiêu chuẩn, đặc biệt <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, <code>iat</code>, <code>nbf</code>, <code>jti</code> và JWS header.
3. Cấu hình <code>RegisteredClient</code> và thuật toán HMAC trong Spring Authorization Server; biết các filter/provider chịu trách nhiệm xác thực.
4. Bổ sung validation ở server, kiểm soát chống replay và vòng đời secret, đồng thời hiểu giới hạn của validation mặc định.
5. Kiểm thử những yêu cầu hợp lệ, sai chữ ký, sai client, sai audience, hết hạn và lặp lại assertion.

**Phạm vi:** Bài trình bày giao thức và kiến trúc Servlet của Spring Authorization Server, dùng kiểu API quen thuộc ở nhánh Spring Authorization Server 1.x. Những phiên bản Spring Security mới hơn đã tích hợp các thành phần Authorization Server và có thể khác package/DSL; cần đối chiếu version đang chạy. Các đoạn mã là ví dụ học thuật, không phải một dự án Spring Boot đầy đủ có thể chạy riêng lẻ.

## 2. Client authentication diễn ra ở đâu?

OAuth 2.0 phân biệt **client authentication** (client là ai) với **authorization grant** (cơ sở nào cho phép cấp access token). Hai việc có thể nằm trong cùng yêu cầu đến token endpoint nhưng được kiểm tra bởi những thành phần khác nhau.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as orders-batch (Client)
    participant AS as Spring Authorization Server
    participant R as RegisteredClientRepository
    participant V as JWT assertion validator
    participant T as Token Endpoint / Grant Provider
    C->>C: Tạo JWT mới, ký HMAC bằng client secret
    C->>AS: POST /oauth2/token, grant_type=client_credentials, client_assertion=JWT
    AS->>R: Tìm RegisteredClient và kiểm tra method đã đăng ký
    R-->>AS: orders-batch + client settings
    AS->>V: Xác minh HMAC, alg, iss/sub/aud, thời gian, replay policy
    V-->>AS: Client hợp lệ hoặc invalid_client
    AS->>T: Nếu client hợp lệ, xử lý grant và phạm vi truy cập
    T-->>C: Access token hoặc lỗi giao thức
~~~

Trong Spring Authorization Server, <code>OAuth2ClientAuthenticationFilter</code> nhận request client authentication. Theo cấu hình mặc định của framework, <code>JwtClientAssertionAuthenticationConverter</code> chuyển dữ liệu request thành đối tượng authentication, còn <code>JwtClientAssertionAuthenticationProvider</code> sử dụng <code>JwtClientAssertionDecoderFactory</code> để kiểm tra JWT đối với <code>RegisteredClient</code> cụ thể.

Kết quả xác thực client có thể được gắn vào <code>SecurityContext</code> để token endpoint hoặc endpoint tương ứng tiếp tục xử lý. **Xác thực client thành công không có nghĩa grant hoặc mọi scope đều được chấp nhận**: Authorization Server vẫn phải kiểm tra grant type, quyền client, policy, token lifetime và các điều kiện liên quan.

## 3. Phân biệt <code>client_secret_jwt</code> với các cơ chế gần giống

| Cơ chế | Credential client gửi | Cách kiểm tra | Khi nào dùng |
| --- | --- | --- | --- |
| <code>client_secret_basic</code> | Client ID và secret qua HTTP Basic | So khớp secret với dữ liệu đăng ký | Confidential client đơn giản, chỉ qua HTTPS |
| <code>client_secret_post</code> | Client ID và secret trong form body | So khớp secret | Khi cần tương thích với endpoint hỗ trợ cách này; hạn chế lộ body |
| **<code>client_secret_jwt</code>** | JWT được ký HMAC bằng shared secret | Kiểm tra chữ ký, claims và chính sách client | Confidential client cần assertion thời gian ngắn |
| <code>private_key_jwt</code> | JWT được ký bằng **private key** của client | Kiểm tra public key đáng tin và claims | Client có thể bảo quản private key riêng, thuận lợi tách khóa |
| <code>none</code> | Không có client credential bí mật | Chính sách cho public client, thường cần PKCE ở Authorization Code | SPA/mobile không thể giữ secret |
| <code>tls_client_auth</code> / <code>self_signed_tls_client_auth</code> | Xác thực qua chứng chỉ TLS | Kiểm tra chứng chỉ và ràng buộc đăng ký | Môi trường có hạ tầng mTLS phù hợp |

Đừng nhầm:

- **JWT client assertion** chứng minh danh tính **OAuth client** với Authorization Server.
- **JWT access token** là token được cấp để client gọi **Resource Server**, với audience của API theo thiết kế.
- **OIDC ID Token** là bằng chứng xác thực End-User dành cho OIDC client.
- **JWT Bearer authorization grant** dùng <code>grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer</code> để trình một assertion làm **grant**; đó là mục đích khác với <code>client_assertion</code>.

Một token JWT có chữ ký hợp lệ của client **không được tự động xem là access token**. Chấp nhận cùng JWT ở những ngữ cảnh khác nhau có thể gây lỗi token substitution hoặc cross-JWT confusion.

## 4. Giao thức gửi assertion theo RFC 7523

### 4.1. HTTP request

Khi client dùng <code>client_secret_jwt</code> cho grant <code>client_credentials</code>:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=orders.read&
client_id=orders-batch&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=eyJhbGciOiJIUzI1NiIsInR5cCI6ImNsaWVudC1hdXRoZW50aWNhdGlvbitqd3QifQ...
~~~

Các dấu xuống hàng và chuỗi JWT rút gọn chỉ để dễ đọc. Request thật phải được **form-URL-encode chính xác**, dùng HTTPS, gửi toàn bộ assertion dạng compact JWS và **không ghi JWT/secret nguyên văn vào log**.

Hai tham số cốt lõi:

| Tham số | Giá trị/ý nghĩa |
| --- | --- |
| <code>client_assertion_type</code> | Hằng số <code>urn:ietf:params:oauth:client-assertion-type:jwt-bearer</code>. |
| <code>client_assertion</code> | Một JWT đã ký, có thời hạn ngắn, chứng minh quyền sở hữu client secret. |

<code>client_id</code> trong ví dụ giúp định danh rõ client; nếu gửi, nó phải nhất quán với <code>iss</code>/<code>sub</code> và đăng ký thực tế. Không dùng thêm <code>Authorization: Basic ...</code> để trình một phương thức client authentication thứ hai trong cùng request. Grant có thể là <code>authorization_code</code>, <code>refresh_token</code> hoặc loại phù hợp khác nếu client được đăng ký; ví dụ này dùng <code>client_credentials</code> để tập trung vào xác thực client.

### 4.2. Header và payload JWT

Ví dụ JWS header:

~~~json
{
  "alg": "HS256",
  "typ": "client-authentication+jwt"
}
~~~

Ví dụ payload với các thời điểm **minh họa**, phải thay bằng timestamp Unix thực tế khi tạo assertion:

~~~json
{
  "iss": "orders-batch",
  "sub": "orders-batch",
  "aud": "https://auth.example.com",
  "iat": 1794800000,
  "nbf": 1794800000,
  "exp": 1794800060,
  "jti": "7b6c24a5-16c1-4f0c-b8d9-b812ab7ed8fc"
}
~~~

Không sử dụng các timestamp trên nguyên trạng. Trên thực tế, client đặt <code>iat</code> bằng thời điểm hiện tại, <code>exp</code> sau đó một khoảng ngắn (ví dụ 60 giây), <code>jti</code> mới cho mỗi assertion; chính sách server sẽ quyết định mức lệch đồng hồ và TTL được chấp nhận.

| Trường | Yêu cầu và cách kiểm tra |
| --- | --- |
| <code>alg</code> | Thuật toán ký JWT, ở đây HMAC SHA-256. Server chỉ chấp nhận thuật toán đã đăng ký/cho phép cho client; **không chấp nhận <code>none</code>**. |
| <code>typ</code> | RFC 10070 khuyến nghị giá trị <code>client-authentication+jwt</code> để phân biệt assertion xác thực client. Dùng quy tắc tương thích khi triển khai với client cũ. |
| <code>iss</code> | Với client authentication, <code>iss</code> là **client ID** của client phát hành JWT. |
| <code>sub</code> | Với client authentication, **bắt buộc là client ID**. Không phải End-User và không phải issuer URL của Authorization Server. |
| <code>aud</code> | Định danh issuer của **Authorization Server đích**, duy nhất theo quy định RFC 10070. |
| <code>exp</code> | Bắt buộc; JWT hết hạn phải bị từ chối. Nên từ chối thời hạn quá xa theo policy. |
| <code>nbf</code> | Tùy chọn; nếu có, không chấp nhận JWT trước thời điểm này (ngoại trừ clock skew được chấp nhận). |
| <code>iat</code> | Tùy chọn theo RFC 7523; hữu ích để giới hạn độ tuổi, phát hiện đồng hồ sai. |
| <code>jti</code> | Tùy chọn theo RFC 7523; nên cấp giá trị duy nhất và kiểm tra replay khi cần chống tái sử dụng assertion. |

**Lưu ý:** Các ví dụ legacy đôi khi đặt <code>aud</code> là URL token endpoint. Điều đó không còn phù hợp với yêu cầu mới dành riêng cho **JWT client authentication** trong RFC 10070 (11/2026), trình bày ở phần tiếp theo.

## 5. Yêu cầu audience mới trong RFC 10070 (11/2026)

**RFC 10070** cập nhật RFC 7521, 7522, 7523 và 9126 để loại bỏ cách lựa chọn audience dễ gây nhầm lẫn khi assertion được gửi đến Authorization Server. Với **JWT client authentication**, quy tắc hiện hành là:

1. Authorization Server phải có một **issuer identifier** ổn định theo RFC 8414.
2. JWT client assertion phải có **<code>aud</code> là duy nhất issuer identifier đó**, ví dụ <code>https://auth.example.com</code>.
3. JWT client assertion **không được dùng URL token endpoint làm audience**, ngay cả khi request vật lý được gửi tới <code>https://auth.example.com/oauth2/token</code>.
4. Authorization Server phải **từ chối** assertion có audience khác hoặc nhiều audience; client phải sửa cách sinh assertion cho tương thích.
5. Client **nên** dùng JWS header <code>typ=client-authentication+jwt</code>; RFC không khuyến nghị từ chối chỉ vì client cũ chưa gắn explicit type, nhằm duy trì tương thích khi audience đã được siết chặt.

Ví dụ kiểm tra audience:

| JWT claim <code>aud</code> | Kết quả theo RFC 10070 |
| --- | --- |
| <code>"https://auth.example.com"</code> | Hợp lệ về **điều kiện audience** nếu đúng issuer server. |
| <code>"https://auth.example.com/oauth2/token"</code> | **Từ chối**: token endpoint không phải issuer identifier. |
| <code>["https://auth.example.com", "https://other.example.com"]</code> | **Từ chối**: có thêm audience khác. |
| <code>"https://orders.api.example.com"</code> | **Từ chối**: đây là API, không phải Authorization Server. |
| Không có <code>aud</code> | **Từ chối**. |

Mảng audience chứa **duy nhất một giá trị issuer** có thể biểu diễn cùng nội dung theo quy tắc JSON Web Token, nhưng nên tạo chuỗi issuer rõ ràng khi công cụ cho phép. Việc kiểm tra phải xác định **tập audience chỉ có đúng issuer**; phép kiểm tra kiểu <code>contains(issuer)</code> đơn thuần sẽ cho phép mảng nhiều audience và không đủ cho yêu cầu mới.

RFC 10070 áp dụng cụ thể cho **client authentication assertion**; JWT được dùng làm **authorization grant** có quy định audience riêng. Đừng suy ra mọi JWT OAuth 2.0 đều phải đặt <code>aud</code> là issuer Authorization Server: access token dành cho Resource Server có audience khác theo profile.

**Vấn đề tương thích phiên bản:** Một số phiên bản triển khai hoặc client cũ có thể vẫn áp dụng validation cho audience theo RFC 7523 ban đầu, chấp nhận URL token endpoint hoặc nhiều audience. Cần kiểm tra chính xác version Spring Authorization Server đang chạy và bổ sung validator phù hợp nếu chưa tuân RFC 10070; không tự suy rằng thư viện đã cập nhật mọi thay đổi giao thức.

## 6. HMAC và bí mật được chia sẻ

Với <code>client_secret_jwt</code>, client và Authorization Server cùng biết **shared secret**. Client tạo chữ ký JWS theo thuật toán HMAC được cấu hình. Đối với <code>HS256</code>, HMAC dùng byte của **UTF-8 representation của client secret** làm khóa:

~~~text
JWT signing input = BASE64URL(header) + "." + BASE64URL(payload)
signature         = HMAC-SHA256(UTF8(client_secret), signing_input)
client_assertion  = BASE64URL(header) + "." + BASE64URL(payload)
                    + "." + BASE64URL(signature)
~~~

Authorization Server phải tìm đúng client được đăng ký, lấy **key tương ứng từ nguồn tin cậy**, rồi xác minh chữ ký. Không phải cứ decode JSON claims thấy <code>iss</code>/<code>sub</code> trùng là đủ: kẻ tấn công có thể tự tạo payload bất kỳ nếu không kiểm tra HMAC.

### 6.1. Độ dài và entropy của secret

Một secret ký HS256 nên được sinh bằng **bộ tạo số ngẫu nhiên mật mã**, có entropy tối thiểu tương ứng mức an toàn mong muốn (thông thường tối thiểu 256 bit cho HS256). Mật khẩu dễ đoán như <code>secret123</code> hoặc secret dùng lại giữa nhiều client dễ bị thử khóa ngoại tuyến nếu assertion bị lộ.

HMAC không tạo ra lợi ích “không cần bảo vệ secret” chỉ vì client không truyền secret trực tiếp trong HTTP form. Ai có secret đều có thể tự ký assertion hợp lệ; vì vậy secret phải được phân phối/bảo vệ như credential. Luôn dùng TLS và giữ request/response khỏi log, proxy analytics hoặc hệ thống giám sát thu thập payload.

### 6.2. HMAC secret khác password hash

Đây là điểm dễ mắc lỗi khi triển khai <code>client_secret_jwt</code>:

- Với <code>client_secret_basic</code>, server có thể lưu **hash một chiều** của secret (ví dụ BCrypt) và so khớp secret client gửi.
- Với <code>client_secret_jwt</code>, server cần **khóa HMAC** để tự tính và xác minh chữ ký. BCrypt hash không thể được đảo ngược để lấy lại đúng byte của secret gốc.
- Vì vậy phải thiết kế **nơi cung cấp secret/khóa HMAC có thể sử dụng để verify**: secret manager/KMS hoặc nguồn tin cậy được bảo vệ; phối hợp với <code>RegisteredClientRepository</code> và decoder factory của phiên bản framework. Không mặc định rằng lưu <code>{bcrypt}...</code> ở <code>RegisteredClient.clientSecret</code> sẽ tương thích trực tiếp với HMAC verification.

Spring Security khuyến nghị client secret trong <code>RegisteredClient</code> được định dạng phù hợp <code>PasswordEncoder</code> cho các luồng xác thực bằng secret; đồng thời <code>client_secret_jwt</code> có yêu cầu key vật liệu HMAC riêng. Khi cần cùng client dùng nhiều phương thức, hãy thiết kế lưu trữ/rotation và kiểm thử thực tế theo implementation, không suy diễn từ mô tả property. Cân nhắc <code>private_key_jwt</code> khi không muốn server lưu shared signing secret.

## 7. Đăng ký client trong Spring Authorization Server

### 7.1. Ví dụ Java <code>RegisteredClient</code>

~~~java
// Đoạn trích cấu hình Spring Authorization Server 1.x.
// Chỉ dành cho demo cô lập: {noop} không bảo vệ secret tại nơi lưu.
RegisteredClient batchClient = RegisteredClient
    .withId("orders-batch-record-001")
    .clientId("orders-batch")
    .clientSecret("{noop}DEMO_REPLACE_WITH_RANDOM_HIGH_ENTROPY_SECRET")
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_JWT)
    .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("orders.read")
    .clientSettings(ClientSettings.builder()
        .tokenEndpointAuthenticationSigningAlgorithm(MacAlgorithm.HS256)
        .build())
    .build();

RegisteredClientRepository clients =
    new InMemoryRegisteredClientRepository(batchClient);
~~~

<code>ClientAuthenticationMethod.CLIENT_SECRET_JWT</code> cho phép phương thức này. <code>tokenEndpointAuthenticationSigningAlgorithm(MacAlgorithm.HS256)</code> ấn định thuật toán HMAC cho JWT client authentication. Không dùng thuật toán RSA/EC (ví dụ <code>RS256</code>) cho shared-secret assertion, vì đó là miền của <code>private_key_jwt</code>.

Giá trị secret ở đây **cố ý là placeholder không dùng được trong production**; để thử thật cần thay bằng một secret ngẫu nhiên đủ mạnh, phân phối đồng nhất ở client và server và kiểm tra định dạng lưu trữ theo version Spring. <code>{noop}</code> chỉ giúp minh họa local, không phải lựa chọn lưu credential ở production. <code>InMemoryRegisteredClientRepository</code> phù hợp học tập; production nên dùng repository có lưu trữ bền vững và cơ chế bảo vệ secret.

### 7.2. Spring Boot properties có thể đăng ký method

Với những phiên bản Spring Boot có auto-configuration Spring Authorization Server, có thể định nghĩa một client tĩnh dưới namespace <code>spring.security.oauth2.authorizationserver.client</code>:

~~~yaml
spring:
  security:
    oauth2:
      authorizationserver:
        client:
          orders-batch:
            registration:
              client-id: orders-batch
              client-secret: "{noop}LOCAL_DEMO_ONLY_SECRET"
              client-authentication-methods:
                - client_secret_jwt
              authorization-grant-types:
                - client_credentials
              scopes:
                - orders.read
            token-endpoint-authentication-signing-algorithm: HS256
~~~

**Lưu ý:** property mapping và vị trí thuộc tính nâng cao phụ thuộc Spring Boot version. Ví dụ mô tả ý tưởng đăng ký và phải được đối chiếu với configuration metadata của bản đang dùng. Không đặt một client thật đồng thời trong YAML và <code>RegisteredClientRepository</code> do Java tự tạo rồi mong hai nguồn được hợp nhất; auto-configuration có thể back off khi phát hiện bean thủ công. Với production, ưu tiên secret manager, không commit giá trị khóa thật vào YAML.

### 7.3. Vì sao vẫn cần cấu hình Authorization Server SecurityFilterChain?

<code>RegisteredClient</code> chỉ là **bản đăng ký client**, không tự cung cấp token endpoint. Authorization Server phải có các thành phần giao thức thông qua DSL:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());
    return http.build();
}
~~~

Đây là **khung DSL**, cần thêm những bean cơ sở của Authorization Server và chain/đăng nhập nếu có End-User. Filter <code>OAuth2ClientAuthenticationFilter</code> và provider JWT client assertion là một phần của cấu hình Authorization Server mặc định khi được bật đúng. Không viết filter riêng để tự parse JWT trừ khi có yêu cầu mở rộng rõ ràng và đã xác minh các hook framework.

## 8. Client tạo JWT assertion thế nào?

Client cần dùng secret gốc đã được cấp qua cơ chế bí mật, không dùng chuỗi <code>{noop}...</code> hay BCrypt hash của server làm key. Với Spring Security JOSE/JWT, có thể dùng <code>NimbusJwtEncoder</code> và <code>ImmutableSecret</code> để ký HMAC.

~~~java
// Mã chạy ở CLIENT backend, không đặt trong ứng dụng frontend/mobile.
String clientId = "orders-batch";
String issuerOfAuthorizationServer = "https://auth.example.com";
String rawSecret = secretManager.read("oauth/orders-batch/hmac-secret");

// secretManager là abstraction do ứng dụng cung cấp. Key HS256 phải mạnh.
byte[] hmacKey = rawSecret.getBytes(StandardCharsets.UTF_8);
JwtEncoder encoder = new NimbusJwtEncoder(
    new ImmutableSecret<SecurityContext>(hmacKey));

Instant now = Instant.now();
JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuer(clientId)
    .subject(clientId)
    .audience(List.of(issuerOfAuthorizationServer))
    .issuedAt(now)
    .notBefore(now)
    .expiresAt(now.plusSeconds(60))
    .id(UUID.randomUUID().toString())
    .build();

JwsHeader header = JwsHeader.with(MacAlgorithm.HS256)
    .type("client-authentication+jwt")
    .build();

String assertion = encoder.encode(
    JwtEncoderParameters.from(header, claims)).getTokenValue();
~~~

<code>SecretManager</code> ở đây là một ví dụ giao diện của ứng dụng, không phải class có sẵn của Spring Security. Phải cung cấp implementation an toàn, ví dụ tích hợp secret manager được phép dùng. <code>ImmutableSecret</code> thuộc Nimbus JOSE/JWT; import và dependency phải tương thích với phiên bản Spring Boot/Spring Security.

Sau đó gửi form request (ví dụ với Spring <code>WebClient</code>):

~~~java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("grant_type", "client_credentials");
form.add("scope", "orders.read");
form.add("client_id", clientId);
form.add("client_assertion_type",
    "urn:ietf:params:oauth:client-assertion-type:jwt-bearer");
form.add("client_assertion", assertion);

// Token endpoint phải là URL HTTPS tin cậy, cấu hình theo metadata.
Mono<String> response = WebClient.create()
    .post()
    .uri("https://auth.example.com/oauth2/token")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData(form))
    .retrieve()
    .bodyToMono(String.class);
~~~

Đoạn mã dùng <code>WebClient</code> làm ví dụ gửi request; cần cấu hình timeout, kiểm soát TLS, xử lý lỗi và deserialization token response trước khi dùng trong production. Nên **tạo assertion mới mỗi lần cần xác thực**, thay vì cache một assertion cho nhiều request. Không đưa assertion vào log hoặc analytics.

**Chú ý về audience:** <code>audience(List.of(issuerOfAuthorizationServer))</code> biểu diễn đúng một audience. Nếu framework encode ra JSON array một phần tử thì nó vẫn phải giữ đúng một giá trị issuer; với các bên yêu cầu dạng chuỗi hãy kiểm tra interoperability theo cấu hình thực tế. Không lấy token endpoint URI thay cho issuer.

## 9. Các bước xác minh một client assertion

Để chấp nhận request <code>client_secret_jwt</code>, Authorization Server cần thực hiện tập kiểm tra phối hợp:

~~~mermaid
flowchart TD
    R["POST /oauth2/token"] --> A{"Có client_assertion_type hợp lệ, JWT đúng định dạng?"}
    A -- Không --> E["invalid_client"]
    A -- Có --> B{"Tìm được RegisteredClient và được phép client_secret_jwt?"}
    B -- Không --> E
    B -- Có --> C{"alg HMAC đã đăng ký, chữ ký đúng khóa của client?"}
    C -- Không --> E
    C -- Có --> D{"iss = sub = client_id, aud chỉ có issuer AS?"}
    D -- Không --> E
    D -- Có --> F{"exp / nbf / iat và TTL phù hợp?"}
    F -- Không --> E
    F -- Có --> G{"jti chưa dùng nếu áp dụng chính sách anti-replay?"}
    G -- Không --> E
    G -- Có --> H["Client authenticated"]
    H --> I{"Grant type, scope, policy hợp lệ?"}
    I -- Không --> J["Từ chối theo lỗi grant/scope tương ứng"]
    I -- Có --> K["Phát hành access token"]
~~~

Sơ đồ diễn tả **các phép kiểm tra logic**; thứ tự chính xác giữa parser/decoder/provider và grant provider phụ thuộc implementation. Một số kiểm tra như giới hạn tuổi <code>iat</code>, TTL tối đa và chống replay <code>jti</code> là **hardening bổ sung**, không nên mặc định framework đã bật chúng.

### 9.1. Kiểm tra client và thuật toán

- Tìm đúng <code>RegisteredClient</code> theo thông tin client, không dùng header <code>kid</code> hoặc <code>iss</code> không xác thực để chọn **bất kỳ** secret nào ngoài phạm vi client.
- Kiểm tra client đã đăng ký <code>CLIENT_SECRET_JWT</code>, secret chưa hết hạn/bị thu hồi và client còn hoạt động theo policy.
- Chỉ chấp nhận <code>HS256</code> nếu client được cấu hình HS256; ngăn thay thế bằng <code>alg=none</code>, <code>RS256</code> hoặc thuật toán khác.
- Với HMAC, secret thuộc **đúng client**, không dùng một khóa chung dễ làm client A giả mạo client B.
- Không yêu cầu <code>jwkSetUrl</code> cho <code>client_secret_jwt</code> HMAC thông thường; <code>private_key_jwt</code> dùng public key/JWKS và có mô hình bảo quản khóa khác.

### 9.2. Kiểm tra claims

1. <code>iss</code> phải là client ID hợp lệ và nhất quán với client đã tìm được.
2. <code>sub</code> phải bằng client ID, không phải username của người dùng.
3. <code>aud</code> chỉ chứa issuer của Authorization Server theo RFC 10070.
4. <code>exp</code> phải tồn tại và chưa hết hạn; server nên giới hạn khoảng thời gian hợp lý để tránh assertion sống quá lâu.
5. <code>nbf</code> nếu có phải cho phép sử dụng tại thời điểm hiện tại; <code>iat</code> nên được giới hạn khi áp dụng chính sách tuổi assertion.
6. Nếu triển khai chống replay, <code>jti</code> phải là duy nhất theo client trong cửa sổ chấp nhận và chỉ được dùng một lần.
7. Header <code>typ</code> nên nhận dạng đúng loại assertion; cần quản lý tương thích với client cũ theo RFC 10070 và RFC 8725.

Không chỉ kiểm tra <code>iss</code>/<code>sub</code> khi JWT chưa được xác thực chữ ký. Việc decode Base64URL hoặc đọc payload JWT **không** tự xác minh nguồn phát hành.

### 9.3. Assertion chỉ xác thực client, chưa cấp scope

Sau khi client được xác thực, token endpoint còn kiểm tra <code>grant_type</code>, scope, policy và kiểu client. Ví dụ: một assertion HS256 hoàn toàn hợp lệ của <code>orders-batch</code> vẫn không cho phép client yêu cầu <code>billing.admin</code> nếu scope đó không nằm trong đăng ký/chính sách. Cũng không được chấp nhận grant type client chưa được cấp quyền dùng.

## 10. Bổ sung validator trong Spring Authorization Server

### 10.1. Validation mặc định và khoảng trống có thể cần bổ sung

Tài liệu Spring Authorization Server mô tả <code>JwtClientAssertionDecoderFactory.DEFAULT_JWT_VALIDATOR_FACTORY</code> là bộ validator mặc định cho <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code> và <code>nbf</code>. Nó không phải cam kết rằng tất cả chính sách tùy biến như TTL tối đa, <code>jti</code> chống replay hoặc audience **đúng duy nhất issuer** theo RFC 10070 đều đã được thực thi ở mọi phiên bản.

Để bổ sung quy tắc, framework cung cấp hook <code>JwtClientAssertionAuthenticationProvider.setJwtDecoderFactory()</code>. Cách làm chuẩn là **giữ validator mặc định và bổ sung validator**, thay vì thay thế toàn bộ quy tắc bắt buộc.

### 10.2. Ví dụ bổ sung audience duy nhất issuer và giới hạn TTL

Ví dụ dưới dùng Spring Authorization Server 1.x, kiểm tra một lớp hardening của **JWT client assertion**. Nó giả định có các bean infrastructure của Authorization Server và nhập đúng các class theo version:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.clientAuthentication(clientAuth ->
                clientAuth.authenticationProviders(providers -> {
                    for (AuthenticationProvider provider : providers) {
                        if (provider instanceof JwtClientAssertionAuthenticationProvider jwtProvider) {
                            JwtClientAssertionDecoderFactory factory =
                                new JwtClientAssertionDecoderFactory();

                            factory.setJwtValidatorFactory(client ->
                                new DelegatingOAuth2TokenValidator<>(
                                    JwtClientAssertionDecoderFactory
                                        .DEFAULT_JWT_VALIDATOR_FACTORY.apply(client),
                                    issuerOnlyAndShortLifetime("https://auth.example.com")
                                )
                            );
                            jwtProvider.setJwtDecoderFactory(factory);
                        }
                    }
                }))
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}

private static OAuth2TokenValidator<Jwt> issuerOnlyAndShortLifetime(
        String expectedIssuer) {
    return jwt -> {
        List<String> audiences = jwt.getAudience();
        if (audiences.size() != 1
                || !expectedIssuer.equals(audiences.get(0))) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "Client assertion must target the AS issuer only", null));
        }

        Instant issuedAt = jwt.getIssuedAt();
        Instant expiresAt = jwt.getExpiresAt();
        if (issuedAt == null || expiresAt == null
                || issuedAt.isAfter(Instant.now().plusSeconds(30))
                || expiresAt.isAfter(issuedAt.plusSeconds(120))) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "Invalid client assertion lifetime", null));
        }
        return OAuth2TokenValidatorResult.success();
    };
}
~~~

Giới hạn 120 giây và 30 giây clock skew chỉ là **chính sách minh họa**; hãy đặt theo yêu cầu bảo mật/đồng bộ thời gian thực tế. Bộ validator mặc định vẫn kiểm tra các claim tiêu chuẩn. Trong HTTP response, lỗi JWT client authentication cần được ánh xạ thành **<code>invalid_client</code>** theo RFC 7523; chuỗi <code>invalid_token</code> trong <code>OAuth2Error</code> ở ví dụ là mã lỗi nội bộ của validator, không phải khuyến nghị trả lỗi <code>invalid_token</code> cho client.

**Một lưu ý quan trọng:** ví dụ bảo đảm audience chỉ chứa issuer và kiểm tra lifetime, nhưng **chưa triển khai kho chống replay <code>jti</code>**. Để xác thực client assertion trên hệ thống phân tán, cần thêm cơ chế lưu/kiểm tra <code>jti</code> dùng chung theo TTL và nguyên tắc atomic, không sử dụng một <code>HashSet</code> cục bộ rồi coi là an toàn trong nhiều instance.

### 10.3. Không dùng JWT Resource Server decoder làm decoder client assertion

JWT access token do Authorization Server ký thường được Resource Server xác minh bằng JWK **public** của Authorization Server. Ngược lại, <code>client_secret_jwt</code> phải được xác minh bằng **shared secret của client** và phải đối chiếu registered client. Đây là hai mối tin cậy khác nhau.

Không trỏ decoder của client assertion tới JWKS public mà Authorization Server công bố cho access token/ID Token. Cũng không đưa HMAC secret vào JWKS public endpoint. <code>JwtClientAssertionDecoderFactory</code> tồn tại để tạo decoder trong **ngữ cảnh RegisteredClient**, không phải một decoder dùng chung không biết client nào ký.

## 11. Chống replay và quản lý <code>jti</code>

JWT assertion thường là **bearer credential thời gian ngắn**: ai có bản sao assertion còn hiệu lực có thể thử gửi lại đến token endpoint. Kiểm tra chữ ký và <code>exp</code> chống sửa payload, nhưng **không tự ngăn replay trong cửa sổ thời gian hợp lệ**.

RFC 7523 cho phép dùng <code>jti</code> để nhận diện token và lưu các giá trị đã dùng trong thời hạn hợp lệ. Một thiết kế giảm rủi ro replay nên:

1. Client sinh <code>jti</code> mới bằng UUID ngẫu nhiên/định danh đủ entropy cho **mỗi assertion**.
2. Server sau khi xác minh chữ ký và xác nhận client sẽ ghi dấu <code>(registeredClientId, jti)</code> trong cache/database **tập trung**, đặt TTL ít nhất bao trùm thời hạn assertion cộng clock skew liên quan.
3. Thao tác chấp nhận jti **phải atomic**: request đầu tiên tạo bản ghi thành công, request tiếp theo cùng jti bị từ chối. Không dùng trình tự kiểm tra-đọc rồi ghi riêng gây race condition.
4. Nếu không thể quyết định trạng thái replay vì kho bị lỗi, áp dụng chính sách fail closed cho những endpoint yêu cầu chống replay.
5. Không log toàn bộ assertion để phục vụ audit. Có thể log client ID, thời điểm, kết quả và hash/ID được kiểm soát phù hợp với chính sách dữ liệu.

**Đây là thiết kế bổ sung**, không phải tuyên bố Spring Authorization Server tự có sẵn jti cache đáp ứng tất cả các điều kiện trên. Nếu áp dụng, phải xác định hook/provider thích hợp, test concurrent requests và chiến lược expiry/cleanup.

Với JWT HMAC đã bị lộ secret, chống replay bằng jti chỉ ngăn gửi lại **cùng một assertion**; kẻ nắm secret vẫn có thể ký assertion khác. Do đó cần cả bảo vệ secret, rotation và phát hiện bất thường.

## 12. Vận hành secret, thuật toán và issuer an toàn

### 12.1. Bảo vệ và xoay client secret

Vì HMAC yêu cầu cả client và server có thể tính chữ ký bằng cùng key, cần quản lý:

- **Tạo khóa:** sinh secret entropy cao, dùng đủ byte cho HS256/HS384/HS512 theo thuật toán được phê duyệt.
- **Phân phối:** trao đổi qua secret manager và kênh bảo mật; chỉ backend confidential client và Authorization Server có quyền đọc.
- **Lưu trữ:** mã hóa/giới hạn quyền truy cập khóa; không sao chép vào source code, log, metrics, frontend, CI output hoặc ticket.
- **Rotation:** xác định thời điểm chuyển khóa, cửa sổ tương thích, cập nhật client và server theo trật tự an toàn; không tự coi mọi client/version hỗ trợ nhiều khóa HMAC đồng thời.
- **Thu hồi:** khi nghi lộ khóa, thay secret, chặn assertion cũ và xem xét token đã phát hành theo khả năng revocation; cập nhật audit/incident response.
- **Giám sát:** theo dõi tỷ lệ <code>invalid_client</code>, sai audience, sai alg, jti lặp và lỗi đồng hồ; rate-limit có cân nhắc để tránh brute force/DoS.

Nếu sản phẩm yêu cầu khả năng xoay khóa độc lập theo <code>kid</code> và công bố public key mà không chia sẻ secret, <code>private_key_jwt</code> thường phù hợp hơn. Không đặt một <code>kid</code> do client tự gửi thành chỉ thị tin cậy để đọc khóa bất kỳ từ URL bên ngoài.

### 12.2. Issuer và proxy

Trong môi trường reverse proxy:

~~~text
Client -- HTTPS --> https://auth.example.com/oauth2/token
                         |
                         v
                 Trusted reverse proxy
                         |
                         v
                 Authorization Server app
                 internal: http://auth-svc:9000

JWT client assertion aud = "https://auth.example.com"
AuthorizationServerSettings.issuer = "https://auth.example.com"
~~~

<code>aud</code> phải là **issuer công khai** mà server công bố (không phải <code>http://auth-svc:9000</code>). Cần đồng bộ issuer với OAuth Authorization Server Metadata/OIDC discovery. Forwarded headers phải do proxy đáng tin đặt và không thể bị người dùng giả mạo để làm thay đổi issuer hoặc endpoint tính toán.

### 12.3. Mức tương thích tiêu chuẩn

Nếu triển khai từ ví dụ cũ của RFC 7523 trước tháng 11/2026, hãy kiểm tra xem client có đang tạo <code>aud</code> là token endpoint hoặc cho nhiều audience hay không. Khi nâng cấp để đáp ứng RFC 10070, cần chuyển cả client tạo assertion và logic validation của Authorization Server theo kế hoạch triển khai, tránh tự mở ngoại lệ chấp nhận audience không đúng nhằm “chạy được” trong dài hạn.

## 13. Lỗi trả về và cách chẩn đoán

Trong client authentication, JWT sai hoặc không phù hợp phải dẫn đến lỗi OAuth <code>invalid_client</code>; status HTTP thường là 400 hoặc 401 tùy trường hợp/cách triển khai và yêu cầu HTTP authentication. Không bộc lộ secret, chi tiết signing key hoặc toàn bộ JWT trong response.

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| <code>invalid_client</code> ngay cả khi client ID tồn tại | Client chưa đăng ký <code>client_secret_jwt</code>, secret/key sai, client bị vô hiệu hoặc assertion sai. |
| Sai chữ ký HMAC | Dùng raw secret khác nhau, bytes/UTF-8 khác, alg khác, key quá ngắn hoặc dùng BCrypt hash thay key. |
| Sai <code>iss</code>/<code>sub</code> | Client assertion điền username/issuer AS thay vì client ID; client ID không khớp đăng ký. |
| Sai <code>aud</code> | Dùng token endpoint URL thay issuer AS hoặc đưa nhiều audience; điều này phải bị từ chối theo RFC 10070. |
| Hết hạn/chưa hợp lệ | <code>exp</code>/<code>nbf</code>/<code>iat</code> sai hoặc đồng hồ giữa client/server lệch. |
| Lặp assertion | Cùng <code>jti</code> bị gửi lại và bị replay policy từ chối. |
| Assertion hợp lệ nhưng không được cấp token | Grant type/scope không đăng ký, policy server khác từ chối; kiểm tra lỗi grant riêng. |
| Token endpoint trả HTML login hoặc 404 | Security filter chain AS không khớp, chưa gắn configurer hoặc request rơi vào chain web. |
| Lỗi sau rotation | Client/server dùng key phiên bản khác nhau hoặc quá sớm ngừng chấp nhận khóa cũ. |

Một phương pháp chẩn đoán an toàn là ghi log **mã lỗi và client ID**, thời gian, ID request và thông tin điều kiện validation (ví dụ <code>aud_mismatch</code>), nhưng không ghi assertion/secret nguyên văn. Trong môi trường dev có thể bật Spring Security DEBUG có kiểm soát; tránh TRACE ở production hoặc pipeline log không an toàn.

## 14. Kiểm thử <code>client_secret_jwt</code>

### 14.1. Ma trận integration test

| Test | Thay đổi đầu vào | Kết quả kỳ vọng |
| --- | --- | --- |
| Client hợp lệ | HS256 đúng key, <code>iss=sub=orders-batch</code>, audience đúng issuer, thời hạn còn hiệu lực | Client được xác thực; grant được xử lý theo policy. |
| Sai key | Ký HMAC bằng secret của client khác | <code>invalid_client</code>. |
| Sai thuật toán | Đổi <code>alg</code> sang <code>none</code>, <code>RS256</code> hoặc HMAC alg không đăng ký | <code>invalid_client</code>. |
| Sai client ID | <code>sub</code> là client khác với <code>iss</code>/<code>client_id</code> | <code>invalid_client</code>. |
| Sai audience kiểu cũ | <code>aud=https://auth.example.com/oauth2/token</code> | Từ chối theo RFC 10070. |
| Thêm audience thứ hai | <code>aud</code> chứa issuer và một URL khác | Từ chối theo RFC 10070. |
| Không có <code>exp</code> hoặc <code>exp</code> đã quá | Thiếu claim/hết hạn | <code>invalid_client</code>. |
| Quá hạn TTL nội bộ | <code>exp</code> đặt quá xa so với <code>iat</code> | Từ chối nếu bật giới hạn TTL. |
| <code>nbf</code> ở tương lai | Chưa đến thời gian hiệu lực | Từ chối theo clock skew. |
| Gửi lại cùng <code>jti</code> | Hai request ký cùng assertion | Request sau bị từ chối **nếu đã thiết kế chống replay**. |
| Client không đăng ký JWT method | RegisteredClient chỉ hỗ trợ <code>client_secret_basic</code> | <code>invalid_client</code>. |
| JWT hợp lệ nhưng scope ngoài đăng ký | Client xin <code>admin.write</code> | Từ chối scope/grant thích hợp, không cấp quyền vượt đăng ký. |
| Client Credentials không có End-User | JWT client assertion hợp lệ | Token biểu thị client/service theo grant, không tạo phiên End-User. |
| Restart/multi-node/rotation | Đổi instance hoặc khóa | Hành vi nhất quán theo kho secret và trạng thái replay. |

Các test cần thực hiện request qua <code>OAuth2ClientAuthenticationFilter</code>, <code>JwtClientAssertionAuthenticationProvider</code> và token endpoint thực. Chỉ unit-test hàm đọc claim hoặc dùng MockMvc với <code>authentication()</code> giả không chứng minh chữ ký và audience được xác minh.

### 14.2. Ví dụ kiểm thử validator audience

Đoạn dưới minh họa một unit test cho **validator bổ sung ở phần 10**, không thay cho integration test:

~~~java
@Test
void rejectsMultipleAudiencesForClientAssertion() {
    OAuth2TokenValidator<Jwt> validator =
        issuerOnlyAndShortLifetime("https://auth.example.com");

    Instant now = Instant.now();
    Jwt assertion = Jwt.withTokenValue("test-only")
        .header("alg", "HS256")
        .issuer("orders-batch")
        .subject("orders-batch")
        .audience(List.of(
            "https://auth.example.com",
            "https://other.example.com"))
        .issuedAt(now)
        .expiresAt(now.plusSeconds(60))
        .build();

    assertThat(validator.validate(assertion).hasErrors()).isTrue();
}
~~~

Mã thử này chỉ xác nhận hàm custom audience validator từ chối nhiều audience. Nó **không kiểm tra chữ ký** vì <code>Jwt.withTokenValue()</code> tạo đối tượng JWT dùng cho test. Để chứng minh tích hợp xác thực client, cần gọi token endpoint bằng một assertion được ký thật bằng key đã đăng ký và kiểm tra kết quả HTTP.

### 14.3. Những bất biến bảo mật cần giữ

~~~text
Accepted client assertion:
  authenticated client == RegisteredClient(client_id)
  iss == sub == client_id
  aud == AS issuer (duy nhất)
  alg == registered JWS algorithm
  signature verified with the corresponding client key
  exp/nbf valid; TTL policy satisfied
  jti not replayed (nếu chính sách yêu cầu)

After client authentication:
  granted scopes ⊆ client registered/policy allowed scopes
  grant type ∈ client registered/allowed grant types
~~~

## 15. Bài tập vận dụng

Bạn đang thiết kế Authorization Server cho ba client: <code>batch-exporter</code>, <code>billing-worker</code> và <code>dashboard-spa</code>.

1. Chọn phương thức client authentication phù hợp cho từng client. Giải thích vì sao một SPA trong trình duyệt không được coi là confidential client chỉ vì ứng dụng có JavaScript tạo JWT.
2. Viết <code>RegisteredClient</code> cho <code>batch-exporter</code> dùng <code>client_secret_jwt</code> với HS256 và <code>client_credentials</code>, scope <code>reports.export</code>. Chỉ ra chỗ lấy secret từ secret manager.
3. Dựng payload JWT với <code>iss=sub=batch-exporter</code>, <code>aud=https://identity.example.com</code>, <code>exp</code> sau <code>iat</code> 60 giây, <code>jti</code> duy nhất. Giải thích vì sao không dùng <code>https://identity.example.com/oauth2/token</code> làm audience.
4. Thiết kế validation gồm kiểm tra key, thuật toán, registered method, issuer/sub, sole audience, thời gian và cơ chế chống replay chạy trên hai instance.
5. Lập kế hoạch xoay HMAC secret khi nghi bị lộ, xác định các token/authorization cần xem xét, thời gian chuyển đổi và cách đo lỗi xác thực.
6. Viết integration test gửi JWT đúng và JWT bị sửa một byte trong payload; xác minh request sai phải nhận <code>invalid_client</code>.
7. So sánh chi phí vận hành và ranh giới tin cậy giữa <code>client_secret_jwt</code> với <code>private_key_jwt</code> trong hệ thống nhiều client.

Một bài làm đạt yêu cầu phải **phân biệt xác thực client với cấp access token**, mô tả đúng khóa HMAC, kiểm tra audience theo RFC 10070 và không mặc định những chính sách bổ sung như replay protection đã được framework tự thực hiện.

## 16. Tài liệu tham khảo

- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): định nghĩa cách gửi JWT client assertion và các claims cơ bản.
- [RFC 10070 (11/2026) — Updates to JWT Client Authentication and Assertion-Based Grants](https://www.rfc-editor.org/rfc/rfc10070): cập nhật bắt buộc về audience duy nhất là issuer Authorization Server và khuyến nghị explicit JWT type.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer identifier và metadata.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thuật toán, explicit typing và chống token confusion.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc claims, audience và thời gian.
- [OpenID Connect Core 1.0, §9 — Client Authentication](https://openid.net/specs/openid-connect-core-1_0.html#ClientAuthentication): <code>client_secret_jwt</code>, HMAC key từ client secret và các phương thức OIDC.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): <code>OAuth2ClientAuthenticationFilter</code>, converter/provider, tùy chỉnh <code>JwtClientAssertionDecoderFactory</code>.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, <code>ClientSettings</code>, repository và algorithm settings.
- [Spring Boot — OAuth2 Support](https://docs.spring.io/spring-boot/reference/security/oauth2.html): ví dụ auto-configuration và thuộc tính client.

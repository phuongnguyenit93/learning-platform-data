# Kiểm chứng metadata, HTTPS và chứng chỉ trong từng môi trường

Khi một **Spring Security OAuth 2.0 Resource Server** được cấu hình với `issuer-uri`, ứng dụng cần biết **Authorization Server nào đáng tin**, lấy khóa xác minh token từ đâu và kiểm tra JWT có thật sự được cấp cho API này hay không. Thông tin đó thường được công bố qua cơ chế **issuer discovery** của OAuth 2.0 / OpenID Connect (OIDC), kết nối bằng **HTTPS**.

Một cấu hình nhìn có vẻ đơn giản:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
```

thực chất dựa vào nhiều điều kiện: tên miền trỏ tới đúng hệ thống, chứng chỉ TLS hợp lệ với JVM của Resource Server, metadata trả về mô tả **đúng issuer**, địa chỉ JWKS không bị thay thế, chữ ký JWT khớp với khóa đã tin cậy và các claim như `iss`, `aud`, `exp` đáp ứng hợp đồng của API.

**Mục tiêu của bài học:** biết cách **kiểm chứng metadata, HTTPS và chứng chỉ ở từng môi trường development, staging, production**, phát hiện cấu hình lệch mà không phải tắt xác minh TLS, đồng thời phân biệt hai loại khóa thường bị nhầm: **chứng chỉ TLS bảo vệ kết nối** và **khóa JWK dùng xác minh chữ ký JWT**.

> **Bối cảnh minh họa:** API Orders chạy Spring Boot 3.x / Spring Security 6.x trên Servlet stack; Authorization Server có issuer riêng cho mỗi môi trường. URL trong bài là địa chỉ ví dụ, không phải dịch vụ đang hoạt động. Những hành vi phụ thuộc phiên bản Spring Boot/Security cần được kiểm tra với bản thư viện thực tế khi triển khai.

## 1. Bốn lớp tin cậy cần kiểm tra riêng

| Lớp | Đối tượng kiểm chứng | Câu hỏi cần trả lời | Thành phần thường chịu trách nhiệm |
|---|---|---|---|
| **Issuer configuration** | `issuer-uri`, định danh tenant/realm | API tin **Authorization Server nào**? | Cấu hình Resource Server |
| **Discovery metadata** | `issuer`, `jwks_uri` và metadata liên quan | Tài liệu tìm được có đúng **issuer đã chọn** không? | Spring Security / cấu hình discovery |
| **HTTPS và chứng chỉ TLS** | Tên miền, chuỗi chứng chỉ, CA tin cậy, thời hạn | Kết nối tới endpoint metadata/JWKS có phải kết nối bảo mật tới host mong đợi không? | TLS stack và JVM truststore |
| **JWT và quyền truy cập** | Chữ ký JWS, `iss`, `aud`, `exp`, `scope` | Token có hợp lệ, dành cho API này và đủ quyền không? | `JwtDecoder`, validators, authorization policy |

Các lớp này hỗ trợ nhau nhưng **không thay thế nhau**:

- **HTTPS hợp lệ** chỉ xác minh kết nối tới host theo mô hình chứng chỉ TLS; không chứng minh mọi JWT do host đó phát hành đều được API phép sử dụng.
- **Metadata hợp lệ** giúp tìm và xác định nguồn khóa đáng tin; không thay thế bước xác minh chữ ký của từng token.
- **Chữ ký JWT hợp lệ** không thay thế kiểm tra `iss` hoặc `aud`. Một token cấp cho Inventory API không tự được dùng ở Orders API.
- **`iss` đúng** không cứu được cấu hình tin nhầm JWKS hoặc bỏ qua TLS certificate validation.
- **Khóa JWT (JWK)** và **TLS certificate** phục vụ các ranh giới khác nhau. Cùng là “key/certificate” nhưng cách sử dụng và vòng đời không đồng nhất.

## 2. Issuer là định danh chính xác, không chỉ là một hostname

Issuer URI là định danh ổn định của Authorization Server mà Resource Server quyết định tin cậy. Ví dụ:

```text
https://login.example.com/realms/orders
```

Trong JWT:

```json
{
  "iss": "https://login.example.com/realms/orders",
  "aud": ["orders-api"],
  "sub": "user-42",
  "exp": 2000000000
}
```

Resource Server cần so sánh `iss` với issuer đã cấu hình theo **giá trị chính xác**, không chỉ so phần hostname hoặc một prefix bất kỳ.

| Cấu hình mong đợi | `iss` trong JWT | Nhận định |
|---|---|---|
| `https://login.example.com/realms/orders` | `https://login.example.com/realms/orders` | Đúng issuer nếu các điều kiện token khác cũng hợp lệ |
| `https://login.example.com/realms/orders` | `https://login.example.com/realms/billing` | Sai realm / issuer |
| `https://login.example.com/realms/orders` | `https://login.staging.example.com/realms/orders` | Sai môi trường |
| `https://login.example.com/realms/orders` | `http://login.example.com/realms/orders` | Sai scheme |
| `https://login.example.com/realms/orders` | `https://login.example.com/realms/orders/` | Có khác biệt dấu `/` cuối; cần theo hợp đồng issuer chính xác |

Không tự sửa `iss` bằng cách thay `http` thành `https`, cắt đường dẫn tenant hoặc bỏ dấu slash để “cho khớp”. Nếu issuer sai, hãy kiểm tra cấu hình bên phát hành, discovery, reverse proxy và client trước khi thay chính sách xác minh.

### 2.1. Định danh issuer khác địa chỉ backend nội bộ

Một tổ chức có thể triển khai Authorization Server trong Kubernetes tại địa chỉ nội bộ `http://identity-svc:8080` nhưng đưa ra ngoài qua gateway:

```text
https://login.example.com/realms/orders
        │
        └── Reverse proxy / ingress (TLS)
                  │
                  └── identity-svc:8080 (private network)
```

Nếu issuer được công bố là `https://login.example.com/realms/orders` thì:

- Metadata nên khai `issuer` đúng định danh công khai đó.
- JWT nên dùng `iss` đúng định danh đó.
- Resource Server cần xác minh `iss` theo định danh đó.
- TLS certificate cho endpoint công khai phải hợp lệ với **`login.example.com`**.
- Internal hostname `identity-svc` không tự trở thành issuer chỉ vì ứng dụng chạy ở đó.

Vận hành reverse proxy cần cấu hình external base URL / forwarded headers theo cơ chế được hỗ trợ của Authorization Server, không để ứng dụng phát sinh issuer thay đổi theo host của mỗi request.

## 3. Discovery metadata là gì?

Trong OAuth 2.0 và OIDC, Authorization Server có thể xuất bản tài liệu JSON metadata để client và Resource Server tìm các endpoint/khóa liên quan.

Hai chuẩn thường gặp:

1. **OpenID Connect Discovery 1.0** với tài liệu OIDC Provider Configuration tại `.well-known/openid-configuration` theo quy tắc URL của OIDC.
2. **RFC 8414 — OAuth 2.0 Authorization Server Metadata** tại `.well-known/oauth-authorization-server` theo quy tắc xác định URL từ issuer.

Spring Security có hỗ trợ tìm provider metadata dựa trên issuer trong các mô hình phù hợp. **Không nên tự ghép chuỗi URL bằng giả định một đường dẫn luôn đúng**: trường hợp issuer có path/realm thì vị trí `.well-known` ở OIDC và OAuth Authorization Server Metadata có thể khác nhau theo đặc tả.

Ví dụ issuer:

```text
https://login.example.com/realms/orders
```

Một OIDC provider có thể cung cấp metadata theo dạng:

```text
https://login.example.com/realms/orders/.well-known/openid-configuration
```

Với RFC 8414, cách đặt `.well-known/oauth-authorization-server` liên quan path của issuer có quy tắc riêng, ví dụ:

```text
https://login.example.com/.well-known/oauth-authorization-server/realms/orders
```

Tùy nhà cung cấp và phiên bản, endpoint thực tế có thể hỗ trợ nhiều cách hoặc tuân theo một chuẩn cụ thể. Nên **bắt đầu từ issuer được đăng ký**, để discovery của thư viện xử lý cơ chế hỗ trợ, và kiểm tra JSON thực tế thay vì đoán URL.

### 3.1. Ví dụ metadata của một issuer

```json
{
  "issuer": "https://login.example.com/realms/orders",
  "authorization_endpoint": "https://login.example.com/realms/orders/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/orders/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.com/realms/orders/protocol/openid-connect/certs",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
```

Đây là **JSON minh họa**: những trường bắt buộc/tùy chọn tùy chuẩn và vai trò provider; tên endpoint có thể khác. Điều Resource Server thường cần nhất khi xác minh JWT là **issuer và JWKS URI**, còn Authorization Code / token endpoint chủ yếu do OAuth/OIDC Client sử dụng.

### 3.2. Cần kiểm chứng những gì trong metadata?

| Hạng mục | Cách hiểu đúng | Khi không đạt |
|---|---|---|
| **JSON hợp lệ** | HTTP response là metadata có cấu trúc đúng, không phải trang login HTML hoặc lỗi gateway | Không tin metadata; kiểm tra endpoint, redirect, proxy |
| **`issuer` đúng** | Metadata issuer bằng chính xác `issuer-uri` đã cấu hình | Từ chối / sửa cấu hình nguồn |
| **`jwks_uri` được tin cậy** | Là endpoint khóa xác minh do issuer đã tin cậy công bố qua metadata và TLS hợp lệ | Không theo địa chỉ tùy tiện hoặc URL do token gợi ý |
| **HTTPS hợp lệ** | Kết nối tới metadata và JWKS có chain/hostname certificate hợp lệ | Không bỏ xác minh; xử lý chứng chỉ, truststore, DNS |
| **Endpoint thực tế truy cập được** | Trả metadata/JWKS theo giao thức, quyền network và proxy phù hợp | Xử lý network policy, DNS, ingress, firewall |
| **Thuật toán ký phù hợp** | Issuer phát hành JWT theo thuật toán mà Resource Server cho phép | Thống nhất hợp đồng ký, không mở tự do theo `alg` trong token |
| **Tên môi trường/tenant** | Metadata không trỏ lẫn staging ↔ production, realm A ↔ realm B | Tách issuer và kiểm tra cấu hình triển khai |

**Không lấy metadata từ request client cung cấp.** Resource Server chỉ tin một issuer hoặc tập issuer được phép theo cấu hình của mình. Nếu ứng dụng đa issuer, mỗi issuer cần được đăng ký/allowlist và xác minh riêng.

### 3.3. Các endpoint metadata không phải tất cả đều cần public

Tài liệu metadata có thể công bố `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`, `introspection_endpoint`, `revocation_endpoint` và `jwks_uri` tùy triển khai. Việc có URL trong metadata **không có nghĩa** mọi endpoint đều truy cập vô điều kiện hoặc Resource Server cần gọi tất cả.

- `authorization_endpoint`: phục vụ luồng chuyển hướng cấp quyền từ OAuth client.
- `token_endpoint`: cấp/refresh token sau khi client hoàn thành grant và xác thực khi cần.
- `jwks_uri`: công bố public signing keys phục vụ JWT verification.
- `introspection_endpoint`: phục vụ opaque token validation theo quyền xác thực riêng.
- `revocation_endpoint`: phục vụ thao tác thu hồi token theo chính sách của Authorization Server.

Với Resource Server **JWT**, thường chỉ cần discovery/JWKS và các chính sách xác minh. Không nên đưa client secret của token endpoint vào Resource Server chỉ vì token endpoint có mặt trong metadata.

## 4. Từ discovery đến xác minh JWT: luồng tin cậy

```mermaid
sequenceDiagram
    autonumber
    participant RS as Spring Resource Server
    participant TLS as HTTPS / TLS trust
    participant AS as Authorization Server
    participant JWKS as JWKS endpoint
    participant C as OAuth Client
    RS->>TLS: Kết nối tới discovery URL đã cấu hình
    TLS->>AS: HTTPS + xác minh hostname/chứng chỉ
    AS-->>RS: Metadata JSON (issuer, jwks_uri, ...)
    RS->>RS: Kiểm tra issuer trong metadata đúng cấu hình
    RS->>TLS: Kết nối jwks_uri tin cậy
    TLS->>JWKS: HTTPS + xác minh chứng chỉ
    JWKS-->>RS: JWKS chứa các public keys
    C->>RS: GET /api/orders + Bearer access token
    RS->>RS: Xác minh JWS theo khóa/alg cho phép
    RS->>RS: Kiểm tra iss, aud, exp, nbf, scope...
    alt Tất cả điều kiện đạt
        RS-->>C: Trả dữ liệu nếu được phân quyền
    else Token hoặc hạ tầng xác minh lỗi
        RS-->>C: Từ chối theo chính sách và trạng thái lỗi
    end
```

Luồng này mang tính khái niệm: Spring có thể fetch metadata/JWKS **khi khởi động hoặc khi cần**, tùy cấu hình/phiên bản và cache. Nếu khóa đã được cache, không nhất thiết có HTTP request tới JWKS trên **mỗi lần gọi API**.

Điểm không thay đổi là việc tin JWT phải nối tiếp một đường tin cậy hợp lệ:

```text
Issuer được cấu hình
        ↓
Metadata có issuer đúng + HTTPS đáng tin
        ↓
JWKS URI được issuer công bố + HTTPS đáng tin
        ↓
Public key / thuật toán xác minh được chấp nhận
        ↓
JWT signature và claims hợp lệ
        ↓
Authorization policy của Orders API
```

Nếu một mắt xích quan trọng hỏng, không được “cứ cho qua” bằng cách bỏ kiểm tra chữ ký hoặc bỏ TLS verification.

## 5. Phân biệt chứng chỉ TLS và khóa ký JWT

Đây là chỗ hay nhầm khi debug lỗi “certificate”, “key”, “signature”.

| Thuộc tính | Chứng chỉ TLS / HTTPS | Khóa xác minh chữ ký JWT / JWKS |
|---|---|---|
| Mục tiêu | Bảo vệ kết nối và xác thực tên endpoint TLS | Kiểm tra token có chữ ký hợp lệ dưới khóa issuer tin cậy |
| Sử dụng tại đâu | Kết nối Resource Server → metadata/JWKS endpoint | `JwtDecoder` xác minh Bearer JWT |
| Cách xác minh | Hostname/SAN, chain certificate, CA trust, thời hạn, chính sách TLS | JWS signature, thuật toán, `kid`/key phù hợp, issuer/audience/time/claims |
| Vật liệu công bố | Server certificate và các intermediate cần thiết | Public JWKs khi dùng chữ ký bất đối xứng |
| Secret phải giữ kín | Private key TLS ở server/gateway | Private signing key JWT ở Authorization Server |
| Rotation | Đổi/reissue TLS certificate và chain | Đổi signing key, công bố public key mới qua JWKS |
| Lỗi điển hình | `PKIX path building failed`, hostname mismatch | `Invalid signature`, unknown `kid` / no matching key |

Một **TLS certificate hết hạn** có thể khiến Spring không fetch được metadata hoặc JWKS mặc dù JWT thực tế vẫn được ký đúng. Ngược lại, TLS hoàn toàn hợp lệ vẫn không làm một JWT có chữ ký sai trở nên hợp lệ.

**JWKS không phải truststore CA.** Public JWKs được sử dụng cho token verification; truststore của JVM chứa các CA/certificate được tin cậy khi tạo kết nối TLS. Không import toàn bộ JWKS vào Java truststore và nghĩ rằng như vậy đã giải quyết việc xác minh HTTPS.

Trong một số JWK, trường `x5c` hoặc `x5t` có thể gắn chứng chỉ X.509 với signing key. Điều đó vẫn **không biến token signing certificate thành chứng chỉ TLS cho hostname**. Hệ thống cần kiểm chứng từng mục đích theo tiêu chuẩn tương ứng.

## 6. HTTPS và chứng chỉ cần xác minh gì?

### 6.1. Chuỗi chứng chỉ và CA tin cậy

Khi Resource Server kết nối:

```text
https://login.example.com/realms/orders/.well-known/openid-configuration
```

TLS client trong JVM nhận certificate chain của server và cần xác lập đường tin cậy đến một **trust anchor** (CA hoặc certificate mà JVM tin cậy), áp dụng các giới hạn của chính sách PKIX/TLS.

Chuỗi minh họa:

```text
login.example.com (leaf/server certificate)
        │ signed by
        ▼
Intermediate CA
        │ signed by
        ▼
Trusted Root CA trong JVM truststore
```

Yêu cầu thông thường gồm:

- Leaf certificate còn hiệu lực theo đồng hồ của hệ thống.
- Hostname trong URL được bao phủ bởi **Subject Alternative Name (SAN)** hợp lệ.
- Chain dẫn tới CA/trust anchor được tin cậy, đủ intermediate certificate.
- Certificate/key usage, thuật toán và chính sách TLS được JVM hỗ trợ.
- Kết nối dùng TLS theo yêu cầu của môi trường, không hạ xuống HTTP tùy tiện.
- Gateway trả đúng certificate khi có nhiều domain dùng cùng IP; **SNI** có thể ảnh hưởng certificate được chọn.

Nếu trình duyệt trên laptop mở URL được nhưng ứng dụng Java trong container lỗi, **không có nghĩa JVM certificate validation bị sai**. Laptop và JVM/container có thể dùng **hai truststore khác nhau**.

### 6.2. Hostname verification và SAN

Ví dụ metadata được gọi qua:

```text
https://login.example.com/.well-known/openid-configuration
```

TLS certificate phải hợp lệ cho `login.example.com` (theo SAN và quy tắc xác minh tên máy chủ). Certificate chỉ có SAN `identity.internal.example.com` không được chấp nhận cho URL công khai nói trên chỉ vì hai hostname trỏ về cùng một IP.

Các tình huống điển hình:

| URL kết nối | SAN của certificate | Kết luận |
|---|---|---|
| `https://login.example.com` | `DNS:login.example.com` | Phù hợp nếu chain và thời hạn cũng đúng |
| `https://login.example.com` | `DNS:identity.example.com` | Hostname mismatch |
| `https://login.staging.example.com` | `DNS:login.example.com` | Không tự phù hợp với staging hostname |
| `https://10.0.0.10` | Chỉ có `DNS:login.example.com` | Không tự hợp lệ cho địa chỉ IP |
| `https://login.example.com` | `DNS:*.example.com` | Có thể khớp một cấp theo quy tắc wildcard, nhưng vẫn cần kiểm tra chain và chính sách |

Không “sửa” mismatch bằng cách tắt hostname verification. Sửa lại URL, DNS, SNI, ingress hoặc certificate SAN theo tên miền thực tế được sử dụng.

### 6.3. TLS certificate không xác minh issuer JWT một cách trực tiếp

Một endpoint HTTPS có certificate hợp lệ vẫn có thể công bố metadata với `issuer` khác điều Resource Server mong đợi:

```json
{
  "issuer": "https://login.example.com/realms/other-tenant",
  "jwks_uri": "https://login.example.com/realms/other-tenant/keys"
}
```

Dù HTTPS đúng, metadata này **không** nên được chấp nhận cho issuer `https://login.example.com/realms/orders`. Việc kiểm tra cả `issuer` giúp chặn nhầm realm/tenant và misrouting từ reverse proxy.

### 6.4. Chứng chỉ do CA nội bộ hoặc self-signed

Trong môi trường nội bộ, tổ chức có thể dùng **private CA** thay vì public CA. JVM cần tin đúng CA hoặc trust anchor được phê duyệt. Một số phương án:

- Cấp server certificate từ CA nội bộ và đặt CA certificate đúng vào truststore của ứng dụng.
- Sử dụng secret/config mount quản lý trong Kubernetes để đưa truststore theo workload.
- Nếu dịch vụ đã có certificate được CA phổ biến tin cậy, ưu tiên dùng truststore chuẩn của runtime.
- Với local development thật sự biệt lập, có thể tạo CA/dev certificate riêng; không chuyển khóa hoặc truststore dev sang staging/prod.

**Không khuyến nghị tắt kiểm tra TLS bằng TrustManager chấp nhận mọi certificate hoặc HostnameVerifier luôn trả true.** Cách đó loại bỏ một phần ranh giới tin cậy để tải metadata/JWKS, dễ tạo điều kiện cho man-in-the-middle thay thế khóa xác minh.

## 7. Tách cấu hình theo development, staging và production

Mỗi môi trường cần có **nguồn định danh được xác định rõ**, certificate tin cậy và chính sách network phù hợp. Ví dụ:

| Môi trường | Issuer dự kiến | JWKS dự kiến | Chứng chỉ/CA |
|---|---|---|---|
| **Development** | `https://login.dev.example.com/realms/orders` | JWKS thuộc **dev issuer** | Public CA hoặc dev CA được cấp riêng, chỉ trust trong dev |
| **Staging** | `https://login.staging.example.com/realms/orders` | JWKS thuộc **staging issuer** | CA được môi trường staging tin cậy, SAN đúng staging hostname |
| **Production** | `https://login.example.com/realms/orders` | JWKS thuộc **production issuer** | Certificate TLS production hợp lệ và được tin cậy, chính sách vận hành/rotation riêng |

Không dùng **một issuer chung** cho mọi môi trường chỉ để giảm số biến cấu hình nếu các môi trường có ranh giới an toàn độc lập. Token từ dev không nên được chấp nhận ở production chỉ vì cùng `sub` hoặc `kid`.

### 7.1. Hồ sơ cấu hình theo profile Spring Boot

Có thể dùng các file Spring profile theo môi trường, chẳng hạn:

**`application-dev.yml`**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.dev.example.com/realms/orders
          audiences:
            - orders-api-dev
```

**`application-staging.yml`**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.staging.example.com/realms/orders
          audiences:
            - orders-api-staging
```

**`application-prod.yml`**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
          audiences:
            - orders-api
```

Tên `aud` chỉ là ví dụ để minh họa sự tách biệt. Audience phải khớp chính xác hợp đồng token mà Authorization Server thực tế phát hành. Thuộc tính `audiences` khả dụng ở các phiên bản Spring Boot có hỗ trợ; với phiên bản khác, cần validator `aud` được cấu hình rõ ràng.

**Không đưa CA private key, HMAC JWT signing secret, OAuth client secret hoặc mật khẩu truststore thực vào YAML commit.** Nếu phải cung cấp truststore, đưa file và mật khẩu qua cơ chế secret được tổ chức quản lý.

### 7.2. Các giá trị cần quản lý như “hợp đồng môi trường”

Tối thiểu mỗi môi trường cần công bố cho đội triển khai:

- **Issuer identifier chuẩn** (exact URL, gồm scheme, host, port/path và trailing slash nếu có).
- **Discovery type/metadata endpoint** thực sự hỗ trợ (OIDC, OAuth AS Metadata).
- **JWKS URI** được issuer công bố, thông tin thuật toán ký và chính sách key rotation.
- **Resource identifier / audience** của Orders API.
- **CA/truststore policy** và ai chịu trách nhiệm cấp/đổi TLS certificate.
- **Egress/DNS/proxy** để Resource Server gọi được metadata/JWKS.
- **Thời hạn token, clock skew, scope/authority** và quy tắc xử lý lỗi.
- **Owner và quy trình xử lý sự cố** khi issuer sai, certificate hết hạn hoặc signing key rotation thất bại.

Những thông tin trên cần được thống nhất giữa nhóm vận hành Authorization Server, nhóm Resource Server và nhóm hạ tầng. “URL mở được trên trình duyệt của tôi” không thay thế kiểm chứng trực tiếp ở runtime.

## 8. Cấu hình Spring Security Resource Server cho issuer discovery

### 8.1. Trường hợp phổ biến: chỉ cấu hình `issuer-uri`

Với Spring MVC trên Spring Boot 3.x / Spring Security 6.x, ví dụ Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
          audiences:
            - orders-api
```

Security chain:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Ở mô hình này Spring Security dùng issuer để tìm cấu hình liên quan, thiết lập `JwtDecoder`, tải khóa xác minh phù hợp và kiểm tra các claim được cấu hình. Quyền `SCOPE_orders.read` phụ thuộc mapping scope/authority của JWT; thêm converter nếu issuer có quy ước khác.

**Không giả định chỉ cần issuer là đủ:** Resource Server vẫn phải xác minh **audience**, loại access token/`typ` khi theo hồ sơ RFC 9068, thời gian, thuật toán và điều kiện nghiệp vụ. Nếu có custom `JwtDecoder`, bảo đảm các validator cần thiết vẫn được áp dụng.

### 8.2. Trường hợp khai báo cả `issuer-uri` và `jwk-set-uri`

Khi muốn cấu hình rõ JWKS URI từ metadata **đã kiểm chứng**, có thể:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
          jwk-set-uri: https://login.example.com/realms/orders/protocol/openid-connect/certs
          audiences:
            - orders-api
```

Ý nghĩa:

- `issuer-uri` giữ vai trò **định danh issuer tin cậy**, dùng cho kiểm tra `iss`.
- `jwk-set-uri` cung cấp **địa chỉ lấy public JWKs** thay vì bắt buộc khám phá địa chỉ khóa từ metadata tại lúc cấu hình decoder.
- `audiences` là ví dụ kiểm tra resource đích ở bản Spring Boot hỗ trợ.

Đây là một cách **giảm phụ thuộc vào metadata discovery ở startup** được mô tả trong tài liệu Spring Security cho các bản tương ứng, nhưng Resource Server vẫn có thể phải liên lạc với **JWKS endpoint khi cần khóa**, ví dụ lúc xác minh token đầu tiên hoặc gặp `kid` chưa có trong cache. Không suy luận rằng khai báo `jwk-set-uri` nghĩa là ứng dụng không bao giờ cần network.

**Rủi ro cấu hình:** nếu điền nhầm JWKS URI của tenant hoặc môi trường khác, chữ ký có thể thất bại hoặc tạo ranh giới tin cậy sai. Giá trị `jwk-set-uri` phải được lấy từ hợp đồng/metadata đáng tin và được quản lý cùng issuer; không nhận URL tùy ý từ HTTP request hoặc JOSE header của token.

### 8.3. Vì sao startup có thể thất bại vì metadata?

Trong một số kiểu tự động cấu hình, việc khởi tạo `JwtDecoder` từ issuer có thể truy vấn discovery endpoint để lấy metadata và `jwks_uri`. Nếu issuer không truy cập được, kết nối TLS bị lỗi hoặc tài liệu không phù hợp, ứng dụng có thể thất bại ngay lúc startup. Các phiên bản/cách khai báo khác nhau có thời điểm fetch khác nhau; vì vậy **không nên khẳng định mọi bản Spring luôn fetch ở startup hoặc luôn lazy**.

Cần phân biệt:

- **Startup dependency:** ứng dụng cần metadata để khởi tạo decoder.
- **Runtime dependency:** API cần lấy signing key mới hoặc làm mới JWKS cache khi xác minh JWT.
- **Sự cố mạng tạm thời:** một số token có thể vẫn được verify bằng key trong cache, nhưng key rotation hoặc khởi động instance mới có thể bị ảnh hưởng.

Giải pháp đúng là kiểm soát dependency, timeout/cache, readiness, ingress/network và cấu hình metadata/JWKS. Không nên chuyển sang “accept JWT without signature” để vượt qua lỗi kết nối.

## 9. Kiểm tra HTTPS và metadata từ đúng môi trường chạy

Kiểm tra trên laptop có thể khác với kiểm tra trong **container/pod/VM** vì DNS, proxy, network policy và truststore khác nhau. Khi có lỗi, nên thực hiện các kiểm tra từ **runtime hoặc một môi trường kỹ thuật có cấu hình mạng và certificate trust tương đương**.

### 9.1. Kiểm tra metadata bằng curl

Ví dụ trên máy hỗ trợ curl:

```bash
curl --verbose --fail \
  --header "Accept: application/json" \
  "https://login.example.com/realms/orders/.well-known/openid-configuration"
```

Quan sát:

1. DNS có phân giải đúng hostname không?
2. TCP/TLS có kết nối được không?
3. TLS certificate có được xác minh thành công không?
4. HTTP response có phải `200` và JSON metadata không?
5. `issuer` trong JSON có **khớp chính xác** issuer dự kiến không?
6. `jwks_uri` có HTTPS và thuộc nguồn đáng tin không?
7. Response có bị redirect sang trang login, reverse proxy HTML hay tenant khác không?

Lệnh trên giả định provider hỗ trợ **đường dẫn OIDC Discovery** cụ thể. Nếu hệ thống theo RFC 8414 hoặc dùng path issuer khác, dùng URL metadata theo tài liệu của provider.

Trên Windows PowerShell, `curl` có thể là alias của `Invoke-WebRequest`; gọi **`curl.exe`** nếu muốn đúng cú pháp của curl bản native.

**Không dùng tùy chọn `-k` hoặc `--insecure` để tuyên bố môi trường đã vượt qua kiểm chứng TLS.** Các tùy chọn ấy cố ý bỏ xác minh certificate và sẽ che mất vấn đề thật.

### 9.2. Kiểm tra JWKS URI

Lấy `jwks_uri` từ metadata đã xác minh, ví dụ:

```bash
curl --verbose --fail \
  "https://login.example.com/realms/orders/protocol/openid-connect/certs"
```

Phản hồi có thể có dạng:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "orders-signing-2026-01",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS_EXAMPLE",
      "e": "AQAB"
    }
  ]
}
```

`n` trong JSON minh họa **không phải public key thật**. Điều cần kiểm tra là endpoint trả **JWK Set đúng cấu trúc**, có public keys cần thiết, `kid`/algorithm liên quan tới token đang phát hành và không tiết lộ symmetric secret/private key.

Cẩn trọng với JWK `kty=oct`: đó là **khóa đối xứng** và không được công khai secret HMAC trên JWKS công khai. Với các thuật toán bất đối xứng, public JWKs có thể xuất bản an toàn theo thiết kế.

### 9.3. Kiểm tra certificate chain và SNI bằng OpenSSL

```bash
openssl s_client \
  -connect login.example.com:443 \
  -servername login.example.com \
  -showcerts \
  -verify_return_error
```

Các mục cần xem trong kết quả:

- Certificate leaf có tên miền phù hợp và còn hạn.
- Server cung cấp intermediate certificate cần thiết.
- SNI dẫn tới đúng virtual host/certificate.
- Đường tin cậy đến CA phù hợp nếu OpenSSL host có truststore tương ứng.
- TLS handshake không gặp lỗi về certificate hoặc protocol.

**Giới hạn:** OpenSSL sử dụng cơ chế trust riêng của môi trường lệnh; kết quả thành công trên máy debug **không chứng minh** JVM truststore của application container cũng tin CA đó. Dùng công cụ này để hiểu chain và chứng chỉ, rồi đối chiếu với truststore JVM.

### 9.4. Kiểm tra JVM truststore bằng keytool

Xem loại/cấu hình truststore được JVM sử dụng, sau đó kiểm tra từng certificate/alias phù hợp. Ví dụ với file truststore PKCS12 do tổ chức quản lý:

```bash
keytool -list -v \
  -keystore /opt/app/certs/truststore.p12 \
  -storetype PKCS12
```

Lệnh có thể yêu cầu mật khẩu truststore; **không ghi mật khẩu vào lệnh xuất hiện trong lịch sử shell hoặc CI log**. Không phải tất cả deployments có truststore riêng: JVM thường dùng default truststore của runtime trừ khi cấu hình khác.

Có thể đưa CA được phê duyệt vào truststore riêng bằng quy trình hạ tầng (ví dụ dùng `keytool -importcert` sau khi xác minh fingerprint/nguồn certificate qua kênh độc lập). **Đừng import tùy tiện leaf certificate xuất hiện trong một kết nối đang bị nghi ngờ**, vì như vậy có thể vô tình pin một certificate của đối tượng tấn công.

### 9.5. Kiểm tra thời gian hệ thống

TLS certificates có `notBefore`/`notAfter`; JWT có `iat`, `nbf`, `exp`. Nếu đồng hồ host/pod lệch lớn, cả TLS lẫn JWT validation có thể lỗi.

- Đồng bộ thời gian của VM/node bằng NTP hoặc dịch vụ thời gian đáng tin.
- Xem thời hạn TLS certificate và thời gian thực tế trên runtime.
- Chỉ sử dụng clock skew nhỏ, có lý do và nhất quán cho JWT.
- Không tăng clock skew cực lớn để “chữa” hết hạn token hay chứng chỉ.

## 10. Java truststore và môi trường container

### 10.1. Truststore mặc định và custom truststore

Ứng dụng Java thường xác minh HTTPS thông qua TLS/JSSE với truststore của JVM hoặc cấu hình client TLS cụ thể. Trong môi trường container, JVM image có thể có danh sách CA khác với máy local.

Nếu tổ chức dùng private CA, một cách cấu hình là cung cấp **truststore PKCS12** cho JVM:

```text
-Djavax.net.ssl.trustStore=/opt/app/certs/truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

Mật khẩu truststore nếu cần được cung cấp qua cơ chế secret an toàn, không hardcode vào ví dụ, mã nguồn hoặc log. Đây là **system properties** mẫu của JSSE; framework HTTP client tùy chỉnh có thể sử dụng cấu hình TLS riêng.

**Cảnh báo thiết kế:** chỉ định custom truststore có thể làm tập CA mặc định bị thay thế trong một số cấu hình. Nếu service còn gọi các HTTPS endpoint khác, một truststore quá hẹp có thể làm chúng lỗi. Quy trình tạo truststore phải có chính sách rõ về các CA được phép và mức tin cậy.

### 10.2. Certificate ở ingress khác certificate ở backend

Giả sử TLS kết thúc tại ingress:

```text
Spring Resource Server ── HTTPS ──> Identity Ingress
                                      │ TLS termination
                                      ▼
                                Identity service
```

Resource Server là **TLS client** đối với ingress, nên certificate mà nó nhìn thấy là certificate **của ingress cho hostname endpoint kết nối**. Certificate nội bộ giữa ingress và identity service là một lớp khác, tùy chính sách mạng nội bộ và có thể cũng dùng TLS/mTLS.

Nếu resource server đi trực tiếp tới service address thay vì ingress, cần thiết kế TLS hostname và trust cho **địa chỉ thực sự được kết nối**. Không được chuyển từ issuer URL HTTPS sang internal HTTP một cách tùy tiện để né certificate lỗi.

### 10.3. Forward proxy và TLS interception

Ở một số mạng doanh nghiệp, outbound HTTPS đi qua proxy có thể thực hiện TLS inspection. Trong trường hợp đó, JVM có thể nhìn thấy certificate được ký bởi **enterprise proxy CA** thay vì CA của đích ban đầu.

Điều cần làm là kiểm tra:

- Proxy có được tổ chức cho phép đối với kết nối metadata/JWKS không?
- JVM tin enterprise CA theo chính sách không?
- Proxy có làm thay đổi nội dung metadata/JWKS hoặc route sang tenant khác không?
- Đường kết nối được bảo vệ, được kiểm toán và không mở rộng quyền chỉnh sửa metadata/JWKS ngoài ý muốn không?

Không nhập một CA lạ chỉ để hết lỗi `PKIX path building failed`. Việc tin CA có nghĩa cho phép CA đó xác thực các hostname trong phạm vi kiểm soát, nên phải là quyết định hạ tầng có kiểm chứng.

## 11. Các lỗi phổ biến và cách xác định nguyên nhân

| Dấu hiệu / lỗi | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `PKIX path building failed` | JVM không tìm được chain tới CA tin cậy; thiếu intermediate/private CA | Kiểm tra certificate chain, CA của JVM/runtime, truststore |
| `No subject alternative DNS name matching ... found` | URL hostname không nằm trong SAN của certificate | Kiểm tra DNS, URL endpoint, ingress, SAN/SNI |
| `certificate has expired` hoặc `not yet valid` | Certificate ngoài thời hạn hoặc clock lệch | Kiểm tra certificate dates và đồng hồ runtime |
| Kết nối được bằng curl laptop nhưng Java container lỗi | Truststore/proxy/DNS khác nhau | Chạy chẩn đoán từ pod/VM, xem JVM TLS configuration |
| Discovery trả `404` | Sai well-known path, sai issuer path, provider không hỗ trợ endpoint đó | Kiểm tra OIDC vs RFC 8414 discovery và URL issuer chuẩn |
| Discovery trả trang HTML/login | Proxy định tuyến sai, endpoint bị bảo vệ hoặc redirect không mong đợi | Xem status, redirects, response body, ingress route |
| Metadata `issuer` không khớp | Sai realm, external base URL, proxy scheme/host, staging/prod chéo | Đối chiếu exact issuer với metadata và JWT `iss` |
| `jwks_uri` trỏ sai host/tenant | Metadata hoặc reverse proxy sai; cấu hình hardcode nhầm | Chỉ dùng URL JWKS đúng issuer đã kiểm chứng |
| JWT ký đúng nhưng `iss` sai | Token từ issuer/môi trường khác | Kiểm tra claim `iss` từ token đã xác minh và config |
| JWT `aud` sai | Token được phát hành cho API khác | Kiểm tra resource indicator, client request và audience config |
| Không tìm thấy `kid` phù hợp trong JWKS | Signing key vừa rotate, cache cũ hoặc JWKS endpoint sai | Xem keyset/`kid`/rotation/caching |
| Lỗi kết nối JWKS khi token có `kid` mới | Không egress, DNS, certificate hoặc JWKS đang lỗi | Kiểm tra runtime → JWKS và readiness phụ thuộc khóa |
| JWT `exp` hết hạn | Token cũ hoặc đồng hồ lệch | Xin token mới, kiểm tra time sync; không bỏ exp validation |
| `403` sau khi xác minh token thành công | Scope/authority hoặc quyền đối tượng không đủ | Xem converter, resource policy, tenant/ownership checks |

Các lỗi “JWT invalid” và “TLS certificate invalid” nằm ở **những tầng khác nhau**. Nếu lỗi ở TLS của discovery/JWKS, việc sửa `JwtAuthenticationConverter` sẽ không giúp. Nếu lỗi ở `aud`/`iss`, import thêm CA cũng không thay đổi nội dung JWT.

### 11.1. Lỗi metadata issuer bị thay bằng địa chỉ nội bộ

**Triệu chứng:**

```text
Resource Server config:
  https://login.example.com/realms/orders

Metadata issuer:
  http://identity-svc:8080/realms/orders
```

Kết nối TLS tới ingress có thể hoàn toàn hợp lệ, nhưng metadata issuer khác với cấu hình. Cần sửa **external issuer/base URL** hoặc cấu hình forwarded headers/reverse proxy của Authorization Server để nó công bố issuer thật, thay vì cho API chấp nhận cả nội bộ và công khai mà không có hợp đồng.

### 11.2. Lỗi certificate trên staging nhưng production hoạt động

Có thể staging dùng CA nội bộ, SAN thiếu `login.staging.example.com`, hoặc truststore của staging container không chứa CA đúng. Cách xử lý:

1. Xác minh endpoint thực tế của staging và hostname.
2. Xem certificate chain/SAN từ mạng của staging.
3. Xác minh CA đã được phê duyệt và nạp đúng vào JVM truststore.
4. Kiểm tra pod có dùng đúng JVM image và truststore mount không.
5. Chạy lại kết nối TLS bình thường, **không** dùng `--insecure` hoặc `trustAll`.

Không copy truststore production sang staging một cách máy móc nếu chính sách CA và certificate chain của hai môi trường khác nhau.

### 11.3. Lỗi signing key rotation

Một token mới có `kid=signing-key-2026-02` nhưng JWKS cache của một Resource Server chỉ có `signing-key-2026-01`. Điều này có thể do:

- Issuer ký bằng khóa mới trước khi JWKS công bố public key tương ứng.
- Gateway/cache giữ JWKS quá cũ.
- Resource Server không truy cập được JWKS URI khi cần refresh.
- JWKS URI hardcode sang môi trường/tenant cũ.

Phối hợp rotation bằng cách công bố public key mới trước khi issuer dùng nó để ký, giữ khóa cũ theo chính sách trong khoảng token cũ còn hiệu lực, và giám sát lỗi xác minh. Không “chữa” bằng cách bỏ signature verification.

## 12. Metadata và HTTPS với nhiều issuer / tenant

Một Resource Server có thể phục vụ nhiều tenant và tin nhiều Authorization Server, nhưng phải kiểm soát **tập issuer được phép**.

Ví dụ một API có thể nhận token từ:

```text
https://login.example.com/realms/tenant-a
https://login.example.com/realms/tenant-b
```

Dù cùng hostname/certificate TLS, hai issuer có thể có **metadata, JWKS và hợp đồng audience khác nhau**.

Điều kiện để bảo vệ ranh giới tenant:

- Chỉ cho phép các issuer được cấu hình/đăng ký chính thức.
- Metadata `issuer` của mỗi tenant phải khớp chính xác định danh tenant tương ứng.
- Không dùng `kid` làm định danh khóa toàn cục giữa các issuer; `kid` chỉ có ý nghĩa trong ngữ cảnh tập khóa đã tin cậy.
- JWT từ tenant A không mặc định có quyền với tài nguyên tenant B, kể cả khi token hợp lệ.
- Nếu cần chọn `AuthenticationManager` động, chỉ dùng thông tin chưa xác minh để **định tuyến sơ bộ trong allowlist**, sau đó decoder được chọn vẫn phải xác minh đúng issuer/chữ ký/audience.
- Không cho request tự chỉ định bất kỳ `issuer_uri` hoặc `jwks_uri` nào rồi buộc server tải về; mô hình đó dễ tạo **SSRF** và token trust confusion.

Một chứng chỉ HTTPS tốt cho hostname chung không thay thế việc phân biệt các realm/tenant ở tầng OAuth/OIDC.

## 13. Quy tắc xác minh không được bỏ qua

### 13.1. Không tin khóa lấy từ URL tùy ý trong JWT

Một JOSE header có thể mang `kid` và đôi khi các trường tham chiếu khóa như `jku` hoặc `x5u`. Không nên để JWT do client gửi **quyết định nguồn khóa mới** mà Resource Server tự tải về và tin.

Nguồn tin cậy phải bắt đầu từ **issuer cấu hình/allowlist**, metadata được xác minh qua HTTPS, và JWK Set mà hệ thống đã chấp nhận theo chính sách. `kid` chỉ giúp chọn một khóa trong tập khóa đó.

### 13.2. Chỉ chấp nhận thuật toán hợp đồng cho phép

Nếu Authorization Server dùng `RS256`, Resource Server phải xác minh bằng public key tương ứng, không cho token tự chuyển sang `HS256` hoặc `alg=none`.

- Giới hạn thuật toán bằng cấu hình decoder thích hợp.
- Không dùng public RSA key bytes làm shared secret cho HMAC.
- Không bỏ xác minh signature vì không tải được JWKS.
- Với JWT access token theo **RFC 9068**, cần kiểm tra `typ=at+jwt` / `application/at+jwt` và các required claims theo hợp đồng profile.

### 13.3. Luôn xác minh audience và quyền

Ví dụ token có:

```json
{
  "iss": "https://login.example.com/realms/orders",
  "aud": ["billing-api"],
  "scope": "billing.read"
}
```

Nó có thể được phát hành bởi đúng issuer và có chữ ký hợp lệ, nhưng Orders API **phải từ chối** vì `aud` không chứa `orders-api`. Sau khi token hợp lệ về issuer/audience/time, endpoint còn phải kiểm tra scope và quyền nghiệp vụ trên từng đơn hàng/tenant.

### 13.4. Không nhầm ID token với access token

Trong OIDC, ID token chứng minh kết quả đăng nhập **cho client**. ID token và access token có thể đều là JWS ký bằng khóa trong cùng hệ thống. Nếu Resource Server chỉ kiểm tra chữ ký mà bỏ qua token type và audience, có nguy cơ nhận nhầm ID token.

Do đó hợp đồng cần nêu rõ API chấp nhận **access token loại nào**, `aud` nào và validator nào. Việc có thể tải OIDC metadata không tự cho phép API sử dụng ID token như Bearer access token.

### 13.5. Chứng chỉ TLS và mTLS

Nếu tổ chức yêu cầu **mutual TLS (mTLS)**, Resource Server (đóng vai HTTP client khi tải metadata/JWKS) có thể phải cung cấp client certificate để kết nối tới server. Đây là **lớp xác thực TLS bổ sung** và cần keystore/client key riêng, không đồng nhất với signing key của JWT.

mTLS còn có thể được dùng để ràng buộc access token với client theo các hồ sơ OAuth tương ứng; đó là một hợp đồng khác với việc **Resource Server tải JWKS qua HTTPS**. Không nên nhầm rằng chỉ bật HTTPS thông thường là đã có sender-constrained token.

## 14. Kiểm chứng theo vòng đời triển khai

### 14.1. Trước khi đưa môi trường vào sử dụng

Có thể dùng bảng sau để bàn giao giữa các nhóm:

| Kiểm tra | Dev | Staging | Production |
|---|---|---|---|
| Issuer URL chính thức đã được xác nhận | Có | Có | Có |
| HTTPS endpoint dùng certificate/CA hợp lệ | Có | Có | Có |
| Hostname SAN khớp URL được cấu hình | Có | Có | Có |
| Runtime JVM tin đúng CA theo chính sách | Có | Có | Có |
| Metadata JSON hợp lệ, `issuer` exact match | Có | Có | Có |
| `jwks_uri` tin cậy và truy cập được từ runtime | Có | Có | Có |
| Public keys/`kid` khớp token của môi trường | Có | Có | Có |
| `iss`, `aud`, `exp`/`nbf` được xác minh | Có | Có | Có |
| ID token hoặc token môi trường khác bị từ chối | Có | Có | Có |
| Scope/authority và quyền nghiệp vụ được thực thi | Có | Có | Có |
| Có owner, lịch/cảnh báo certificate và key rotation | Có | Có | Có |

Bảng này là **định hướng nội dung kỹ thuật**, không phải kết quả đã chạy trên hệ thống. Mỗi triển khai cần ghi nhận bằng chứng ở môi trường thực tế: endpoint, timestamp, certificate fingerprint/chain qua nguồn tin cậy, metadata version, runtime Java image và kết quả kiểm tra tương ứng.

### 14.2. Theo dõi khi hệ thống đang vận hành

Nên theo dõi những tín hiệu có giá trị:

- Số lần discovery/JWKS fetch thất bại theo nguyên nhân DNS, TCP, TLS, HTTP status.
- Xu hướng JWT verification failure theo loại `invalid_signature`, `invalid_issuer`, `invalid_audience`, `expired` hoặc `unknown_kid`, không ghi raw token.
- Ngày hết hạn TLS certificate và thời điểm thay certificate theo lịch.
- Việc issuer công bố key mới qua JWKS trước khi bắt đầu ký bằng key đó.
- Thời gian truy cập JWKS và tình trạng cache khi rotate.
- Sai lệch `iss` sau deploy đổi ingress/hostname.
- Sự khác biệt cấu hình issuer/truststore giữa các replicas/pods.

Không đưa token, client secret, private key, refresh token hoặc dữ liệu cá nhân trong claims vào logs/traces. Dùng request ID, error code, issuer identifier đã được duyệt để logging và trạng thái hạ tầng.

### 14.3. Phản ứng khi discovery hoặc JWKS bị lỗi

Các lựa chọn phụ thuộc yêu cầu availability và mô hình cache, nhưng nguyên tắc không đổi:

- Nếu không thể lấy được **khóa tin cậy cần thiết** để xác minh JWT, Resource Server **không thể tự tuyên bố token hợp lệ**.
- Nếu có public key được cache và còn phù hợp, có thể xác minh token bằng cache theo cơ chế của thư viện/cấu hình; phải hiểu giới hạn khi issuer rotate/revoke keys.
- Nếu xác minh không thực hiện được, trả lỗi thích hợp hoặc xem service chưa ready theo chính sách, **không chấp nhận token chưa xác minh**.
- Xử lý căn nguyên ở metadata, mạng, certificate, JWKS hoặc rotation.
- Không tự đổi sang issuer “gần giống” hoặc môi trường khác chỉ vì môi trường chính đang lỗi.

Bảo vệ token verification là một phần của ranh giới an toàn của API, nên mục tiêu availability phải được đáp ứng qua thiết kế hạ tầng và cache, không bằng cách nới lỏng trust.

## 15. Một ví dụ xuyên suốt: staging từ 401 tới nguyên nhân thực

Giả sử client ở staging lấy access token và gọi:

```http
GET /api/orders/42 HTTP/1.1
Host: api.staging.example.com
Authorization: Bearer STAGING_ACCESS_TOKEN
```

Ứng dụng được triển khai với:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.staging.example.com/realms/orders
          audiences:
            - orders-api-staging
```

Một số tình huống:

**Tình huống A — Metadata issuer trỏ production**

```json
{
  "issuer": "https://login.example.com/realms/orders",
  "jwks_uri": "https://login.example.com/realms/orders/keys"
}
```

Kết nối HTTPS có thể hợp lệ nhưng issuer discovery **không đúng staging**. Cần sửa URL/route/base URL của Authorization Server hoặc cấu hình môi trường. Không đổi `issuer-uri` sang production để token staging “chạy được”.

**Tình huống B — Metadata đúng nhưng certificate chain thiếu intermediate**

Khi Java kết nối HTTPS, TLS validation lỗi và decoder không lấy được metadata/JWKS. Cần sửa certificate chain do ingress phục vụ hoặc truststore theo CA được phê duyệt. Không bật `trustAll`.

**Tình huống C — TLS và metadata đúng nhưng token có `aud=orders-api`**

Issuer staging phát hành token với audience production. JWT có thể ký đúng nhưng Resource Server staging phải từ chối vì audience không khớp `orders-api-staging`. Cần sửa resource indicator/đăng ký client và policy phát hành token ở Authorization Server.

**Tình huống D — Token đúng issuer/audience nhưng signing key vừa đổi**

Token mới có `kid` chưa có ở cache của một số pod; một số request lỗi còn các pod khác hoạt động. Kiểm tra JWKS thực tế, cache, network egress và kế hoạch rotation. Không tắt signature verification và không hardcode public key cũ vĩnh viễn.

**Tình huống E — Token hợp lệ nhưng bị trả 403**

Khi authentication đã thành công, 403 thường chỉ ra vấn đề **authorization**: thiếu `orders.read`, mapping scope/authority sai hoặc không có quyền với đơn hàng 42. Không sửa certificate hoặc issuer khi lớp xác thực đã đi qua.

## 16. Tóm lược mô hình tư duy

```text
CẤU HÌNH TIN CẬY
  issuer-uri = định danh issuer chính xác, đúng môi trường/tenant
                  │
                  ▼
DISCOVERY
  metadata hợp lệ và metadata.issuer = issuer-uri
  jwks_uri là nguồn public keys đã được xác minh
                  │
                  ▼
KẾT NỐI TLS
  HTTPS → hostname/SAN → certificate chain → CA/JVM truststore
                  │
                  ▼
XÁC MINH JWT
  Chữ ký / thuật toán / khóa đúng
  iss / aud / exp / nbf / token type đúng
                  │
                  ▼
PHÂN QUYỀN API
  scope / authority / tenant / quyền trên tài nguyên
```

Khi một hệ thống **Spring Security Resource Server** dùng issuer discovery, hãy coi `issuer-uri`, discovery metadata, HTTPS certificate chain và JWKS là **một chuỗi tin cậy được kiểm chứng theo từng môi trường**. Development, staging và production có thể dùng cùng mô hình cấu hình, nhưng phải có issuer và certificate policy phù hợp với ranh giới của chính mình. **Sửa nguyên nhân tại tầng sai**—discovery, TLS, JWT validation hay authorization—giúp hệ thống hoạt động đúng mà vẫn giữ nguyên các yêu cầu bảo mật.

## 17. Tài liệu tiêu chuẩn và tham chiếu

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata và các quy tắc xác định vị trí `.well-known`.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration, issuer và OIDC discovery.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK và JWK Set.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `nbf` và các claim JWT.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): cách xác minh chữ ký JWS.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): giới hạn thuật toán, issuer/audience validation và token confusion.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `issuer-uri`, `jwk-set-uri`, `JwtDecoder` và validator cho Servlet stack.

Các chuẩn giúp xác định **hợp đồng xác minh**, còn khả năng kết nối và cách nạp CA/truststore phải được kiểm chứng trên **JVM/container/host cụ thể**. Cùng một issuer hoạt động trên laptop chưa đủ chứng minh API production có thể truy xuất metadata/JWKS an toàn.

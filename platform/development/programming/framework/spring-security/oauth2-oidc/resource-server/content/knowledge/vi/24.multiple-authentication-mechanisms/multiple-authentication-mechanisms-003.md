# Không suy ra mức tin cậy chỉ từ hình dạng hoặc số dấu chấm của token

## 1. Bài toán trong Resource Server có nhiều cơ chế xác thực

Một API sử dụng **Spring Security OAuth 2.0 / OIDC Resource Server** có thể nhận access token JWT, opaque access token, hoặc token do các Authorization Server khác nhau phát hành. Một số ứng dụng còn đồng thời hỗ trợ browser session, HTTP Basic, service-to-service token, hoặc các hồ sơ token dành cho mục đích khác.

Khi lập trình viên muốn chọn cách xác thực, một ý tưởng rất dễ xuất hiện:

```java
// SAI: cấu trúc chuỗi không chứng minh nguồn phát hành hay độ tin cậy.
boolean looksLikeJwt = token.split("\\.").length == 3;

if (looksLikeJwt) {
    return jwtAuthenticationManager.authenticate(authentication);
}
return introspectionAuthenticationManager.authenticate(authentication);
```

Giả định ngầm ở đây là:

- Có **hai dấu chấm** tức là JWT đáng được tin theo nhánh JWT.
- Không có hai dấu chấm tức là opaque token phải được introspect.
- Chỉ cần nhìn kiểu chuỗi là biết nên áp chính sách xác thực nào.
- Nếu thử JWT không thành công, cứ thử introspection là đủ.

**Cả bốn giả định đều không an toàn.** Hai dấu chấm có thể xuất hiện trong chuỗi ngẫu nhiên. Một compact JWS ba thành phần có thể chứa chữ ký giả, payload không phải JWT claims, hoặc là **ID Token** chứ không phải OAuth access token. Một opaque access token vẫn có thể chứa dấu chấm. Một JWT có thể được mã hóa bằng JWE compact với **năm thành phần**, chứ không phải ba. Và ngay cả token thực sự là JWT cũng phải được kiểm **chữ ký, thuật toán, issuer, audience, hạn dùng, token type và chính sách phân quyền**.

Bài học thuộc chương **Nhiều cơ chế xác thực** của mô-đun **Spring Security OAuth 2.0 OIDC Resource Server**. Mục tiêu là thiết kế **ranh giới tin cậy** khi phải hỗ trợ nhiều cơ chế/token profiles, không nhầm *format detection* với *authentication* hoặc *authorization*.

Ví dụ xuyên suốt:

- Resource Server: `orders-api`.
- Trusted issuer: `https://auth.example.test/realms/orders`.
- JWT access-token audience: `orders-api`.
- Endpoint JWT-only: `/api/jwt/orders/**`.
- Endpoint introspection-only: `/api/opaque/orders/**`.
- Scope đọc đơn: `orders:read`.
- Chủ thể: `alice-123` và `bob-456`.
- Opaque introspection endpoint: `https://auth.example.test/oauth2/introspect`.

Tên miền, token và credential đều là minh họa. Phần code dành cho **Spring Boot 3.x, Spring Security 6.x, Java 17+ Servlet/MVC**, sau đó chỉ ra khác biệt với **WebFlux**.

> **Nguyên tắc bất biến:** **Hình dạng của token có thể giúp định tuyến phân tích cú pháp, nhưng không cấp bất kỳ mức tin cậy nào.** Trust chỉ hình thành sau khi token được xác minh theo một **chính sách đã được định nghĩa trước** và gắn với đúng issuer/resource/token profile.

---

## 2. Phân biệt năm khái niệm trước khi viết code

| Khái niệm | Câu hỏi | Có thể kết luận từ dấu chấm? |
|---|---|---|
| **Token format** | Chuỗi *trông giống* dạng compact JWS, JWE hoặc reference token? | Chỉ phỏng đoán sơ bộ về cú pháp. |
| **Token parsing** | Chuỗi có cấu trúc header/payload/base64url/JSON theo serializer không? | Không; phải parse đúng định dạng. |
| **Token authentication** | Token do nguồn tin cậy phát hành, chữ ký/`active`/issuer/time có hợp lệ không? | **Không.** |
| **Token applicability** | Đây có đúng access token được phép dùng cho `orders-api` không? | **Không.** |
| **Authorization** | Caller có scope, vai trò, tenant và quyền trên object này không? | **Không.** |

Một token có thể được parse thành công nhưng authentication không hợp lệ. Một token có thể authentication hợp lệ nhưng là **ID Token** cho ứng dụng frontend nên không phù hợp với Resource Server. Một access token có thể hợp lệ cho `orders-api` nhưng không có quyền đọc đơn của Bob.

### 2.1. Ba thuật ngữ nên dùng đúng

- **Syntax/format recognition:** quan sát vị trí dấu chấm, header có dạng JSON, độ dài chuỗi hoặc prefix.
- **Verification/validation:** dùng public key/JWKS tin cậy hoặc introspection endpoint tin cậy để quyết định token được chấp nhận theo các validators.
- **Access control:** sau authentication, kiểm scope/authority, tenant, owner, ACL, delegated permissions và quy tắc nghiệp vụ.

**Không chuyển một kết quả syntax recognition thành `Authentication.isAuthenticated() == true`.** Chính sách truy cập cần dựa trên principal từ cơ chế xác minh, không dựa vào dữ liệu chưa xác minh.

### 2.2. Sơ đồ nhánh an toàn và không an toàn

```mermaid
flowchart TD
    A["Authorization: Bearer <token>"] --> B{"Chính sách API/route/issuer đã đăng ký?"}
    B -->|JWT-only| C["JwtDecoder với nguồn key/alg/issuer/aud đã tin"]
    B -->|Introspection-only| D["OpaqueTokenIntrospector tới AS đã tin"]
    B -->|Không có contract| E["Deny: không tự chọn dựa vào số dấu chấm"]
    C --> F{"Chữ ký, claims, profile hợp lệ?"}
    D --> G{"active + metadata + resource binding hợp lệ?"}
    F -->|Không| H["Authentication failure"]
    G -->|Không| H
    F -->|Có| I["Authenticated principal theo token policy"]
    G -->|Có| I
    I --> J{"Đủ scope và object permission?"}
    J -->|Không| K["403/404 theo policy"]
    J -->|Có| L["Cho phép xử lý nghiệp vụ"]
```

Điều quan trọng là **policy được xác định trước khi tin token**. Không có nhánh “JWT verify lỗi thì tự đổi sang chế độ dễ hơn” hoặc “opaque introspection lỗi thì tự tin payload JWT”.

---

## 3. Hai dấu chấm nói lên điều gì về JWS?

Một JWS dạng **compact serialization** có cấu trúc khái quát:

```text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
```

Ba thành phần được phân tách bởi **hai dấu chấm**.

Ví dụ minh họa, không phải chữ ký hợp lệ:

```text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.eyJzdWIiOiJhbGljZS0xMjMifQ.fake-signature
```

Trong ví dụ này:

- Thành phần đầu *có thể* decode thành JWS protected header.
- Thành phần thứ hai *có thể* decode thành payload.
- Thành phần thứ ba chỉ là chuỗi minh họa, **không phải cryptographic proof**.
- Header có thể khai `alg=RS256`, nhưng **chưa có bằng chứng** chữ ký thực sự do issuer tin cậy tạo ra.

Chỉ đếm dấu chấm không chứng minh được:

1. Các thành phần có cú pháp Base64URL hợp lệ.
2. Header có giá trị `alg` được phép.
3. Chữ ký hợp lệ với **trusted key**.
4. Nội dung payload là JWT Claims Set.
5. `iss` của payload thuộc issuer allowlist.
6. `aud` phù hợp API.
7. `exp`, `nbf` còn hiệu lực.
8. JWT là **OAuth 2.0 access token** chứ không phải một loại assertion khác.
9. Token không bị thu hồi hoặc bị hạn chế theo chính sách AS.
10. Caller có đủ quyền với resource được yêu cầu.

**Đếm dấu chấm chỉ là thao tác với chuỗi, không phải một thuật toán xác thực.**

### 3.1. Không phải mọi JWS đều là access token

Một JWS có thể ký:

- Một JWT claims set.
- Dữ liệu khác không phải JWT claims.
- Một assertion dành cho client authentication.
- Một token có mục đích khác, ví dụ ID Token/OIDC.
- Một tài liệu hoặc thông điệp ứng dụng được đóng gói JWS.

Vì vậy “JWS compact ba phần” không đồng nghĩa “JWT access token hợp lệ cho Resource Server”.

JWT được phát hành trong một token profile cụ thể mới có ý nghĩa. RFC 9068 định nghĩa một profile **JWT Access Token** của OAuth 2.0, nhưng không phải mọi JWT ba phần trên Internet đều theo profile đó.

### 3.2. Một JWT ba phần có thể là token giả

Attacker tự tạo:

```json
{
  "alg": "RS256",
  "kid": "some-key"
}
```

và payload:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "sub": "admin",
  "aud": ["orders-api"],
  "scope": "orders:admin",
  "exp": 1890003600
}
```

Sau đó attacker ghi bất kỳ byte nào vào phần chữ ký. Chuỗi kết quả có hai dấu chấm, header/payload trông hợp lý và có scope admin, nhưng **không vượt qua JWS signature verification** nếu Resource Server làm đúng.

Một đoạn code như sau là lỗi nghiêm trọng:

```java
// KHÔNG DÙNG: parse claims chưa xác minh để tạo quyền.
Map<String, Object> claims = parseBase64UrlJwtPayload(rawToken);

Authentication auth = new UsernamePasswordAuthenticationToken(
    claims.get("sub"),
    null,
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
SecurityContextHolder.getContext().setAuthentication(auth);
```

Một JSON payload do client tự tạo không bao giờ là bằng chứng cấp authority.

### 3.3. `alg=none` không làm token thành “JWT hợp lệ”

JWS có khái niệm **Unsecured JWT** trong một số bối cảnh chuẩn đặc biệt, có dạng header chứa `alg="none"` và phần signature rỗng:

```text
header.payload.
```

Nó vẫn có **hai dấu chấm**. Nhưng API Bearer thông thường không được chấp nhận token không có bảo vệ cryptographic như một credential đăng nhập. Không viết code “nếu có hai dấu chấm thì skip verify vì JWT” hoặc “signature rỗng vẫn hợp lệ nếu header nói none”.

Cơ chế decoder phải có **allowlist thuật toán**; không để JWT header do attacker gửi tự quyết định mức xác minh.

---

## 4. Bốn dấu chấm: JWE compact không tự được tin hơn JWT

JWE compact serialization có năm thành phần:

```text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
```

Năm thành phần được ngăn bằng **bốn dấu chấm**.

JWE có mục đích **bảo mật nội dung** bằng encryption và integrity protection trong mô hình JOSE. Nhưng việc một chuỗi trông giống JWE không chứng minh:

- Nó thực sự giải mã được bằng khóa mà API tin.
- Người phát hành là Authorization Server được phép.
- Claims được bảo vệ theo token profile của API.
- Token có audience, expiry và scope phù hợp.
- Bên mã hóa token cũng là bên có quyền phát hành access token.

Một JWT có thể được bảo vệ bằng JWS hoặc JWE, kể cả **nested JWT**. JWT dạng JWE compact không thể được xử lý như JWS ba phần chỉ bằng cách đổi nhánh dựa trên số dấu chấm.

### 4.1. Spring Security Resource Server có tự giải JWE không?

Đường cấu hình JWT Resource Server thông dụng với `NimbusJwtDecoder` tập trung vào **xác minh JWT được ký bằng JWS**. Không nên tự giả định cấu hình `issuer-uri`/`jwk-set-uri` mặc định có thể **giải mã JWE** hoặc xác minh toàn bộ nested-JWT profile.

Nếu hệ thống thật sự dùng encrypted JWT/JWE:

1. Có hợp đồng issuer, encryption key management và decryption algorithm rõ.
2. Xác minh các JOSE headers, các layer ký/mã hóa và token claims theo profile.
3. Không dùng số dấu chấm làm quyết định “nâng mức tin cậy”.
4. Nếu token được xem là **opaque đối với Resource Server**, có thể dùng introspection **nếu AS có hợp đồng hỗ trợ**.
5. Không đưa private decryption key vào code hoặc log; phân quyền truy cập và rotation phải được thiết kế riêng.

**Một JWE năm thành phần không mặc nhiên an toàn hơn JWS ba thành phần** trong vai trò access token. Encryption và authentication/authorization trả lời các câu hỏi khác nhau.

### 4.2. Cả “ba phần” và “năm phần” đều không đủ

| Biểu hiện | Kết luận có thể rút ra | Không được suy ra |
|---|---|---|
| Hai dấu chấm | Có hình dạng giống JWS compact. | JWT access token hợp lệ. |
| Bốn dấu chấm | Có hình dạng giống JWE compact. | JWE giải mã thành công, do issuer tin cậy phát hành. |
| Không có dấu chấm | Không giống compact JWS ba phần. | Opaque token active hoặc thuộc issuer được phép. |
| Mười dấu chấm | Chỉ là một chuỗi lạ. | Token chắc chắn không được issuer dùng làm opaque reference. |
| Prefix `eyJ` | Có vẻ là một đoạn Base64URL JSON. | Signature hợp lệ hoặc trusted issuer. |

Số dấu chấm chỉ hữu ích như một **đặc điểm cú pháp không đáng tin**, không thể thay thế trust policy.

---

## 5. Opaque token có thể chứa dấu chấm

Trong OAuth 2.0, **opaque token** là token mà Resource Server **không thể hoặc không nên tự diễn giải nội dung đáng tin**. Nó thường là chuỗi ngẫu nhiên/reference token, được Authorization Server tra cứu qua Token Introspection theo RFC 7662 hoặc cơ chế được hợp đồng hóa.

Một số chuỗi opaque có thể trông như:

```text
xH8m7N2aQfKL0sT1
abc.def.ghi
ref.2026.q4.54bad1
a.b.c.d.e
```

Số dấu chấm trong những ví dụ này **không làm token thành JWT/JWS/JWE**. Bên phát hành có thể chọn alphabet/encoding chứa `.`; cách biểu diễn không tạo thông tin xác thực.

Bearer token transport cũng cho phép một phạm vi ký tự nhất định, bao gồm dấu chấm trong cú pháp của RFC 6750. Do đó **đếm dấu chấm không phải cách phân biệt đáng tin giữa JWT và opaque token**.

### 5.1. Introspection có thể áp dụng cả với JWT

RFC 7662 không giới hạn introspection chỉ cho chuỗi opaque “không có dấu chấm”. Một Authorization Server có thể hỗ trợ introspection đối với JWT access token hoặc nhiều loại token khác.

Điều quyết định là **hợp đồng của Authorization Server và Resource Server**:

- Introspection endpoint có quyền kiểm tra loại token đó không?
- Requester có quyền introspect token thuộc resource này không?
- `active` được hiểu theo trạng thái/revocation/issuer của token thế nào?
- Endpoint có trả `aud`, `iss`, `scope` hoặc claims mà API cần không?
- Có bảo đảm chỉ access token dành cho `orders-api` được xem là sử dụng được không?

Nếu mọi access token cho một API đều được AS hỗ trợ introspection theo **một contract chặt**, Resource Server có thể introspect tất cả chúng **không quan tâm chuỗi có mấy dấu chấm**.

### 5.2. `active=true` không tự cấp mọi quyền

Ví dụ:

```json
{
  "active": true,
  "iss": "https://auth.example.test/realms/orders",
  "aud": ["payments-api"],
  "scope": "orders:read",
  "sub": "alice-123"
}
```

Dù introspection báo active, token này **không dành cho `orders-api`** nếu audience contract yêu cầu `orders-api`. Đừng chấp nhận chỉ vì token “không giống JWT” nên được xem là opaque và AS trả active.

Nếu introspection response không có `aud`/`iss`, API phải có **resource binding** được AS thực thi theo credential/introspection requester hoặc một hợp đồng tương đương; không tự bỏ yêu cầu này.

---

## 6. JWT, ID Token, access token và token confusion

### 6.1. OIDC ID Token không phải API access token

OIDC ID Token có thể là **JWT ba phần có chữ ký hợp lệ** do **cùng issuer** với access token phát hành. Nó nhằm cung cấp thông tin xác thực user cho **OIDC client**, không mặc nhiên cho phép sử dụng làm credential ở OAuth 2.0 Resource Server.

Ví dụ ID Token có:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "sub": "alice-123",
  "aud": ["web-portal"],
  "exp": 1890003600,
  "nonce": "random-login-nonce"
}
```

Trong khi access token dự kiến cho API có:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1890003600
}
```

Ngay cả hai token đều có signature đúng, ID Token có audience `web-portal` không được chấp nhận ở `orders-api`. Chữ ký hợp lệ chứng minh một issuer đã phát hành assertion, **không cho phép thay đổi mục đích sử dụng assertion**.

Một chương trình chỉ gọi `jwtDecoder.decode(token)` mà quên audience/token-type validation có nguy cơ gặp **cross-JWT confusion** hoặc **token substitution**.

### 6.2. `typ` và explicit token profile

RFC 9068 định nghĩa JWT access-token profile sử dụng header type như `at+jwt`, cùng các requirements khác. Ví dụ:

```json
{
  "alg": "RS256",
  "kid": "signing-key-2026-11",
  "typ": "at+jwt"
}
```

Không dùng `typ` chưa xác minh như bằng chứng độc lập. Nó là một **điều kiện cần kiểm theo hợp đồng đã cấu hình**, kết hợp với signature, issuer, audience và claims. Một số issuer có profile khác, hoặc dùng `typ="JWT"`; Resource Server cần thống nhất và test hồ sơ thực tế thay vì suy ra toàn bộ contract từ header.

Khi ứng dụng nhận nhiều loại JWT khác nhau, RFC 8725 khuyến nghị **validation rules loại trừ lẫn nhau** cho từng loại: một ID Token và một access token không nên cùng vượt qua cùng một bộ validator chỉ vì chúng đều là JWT.

### 6.3. JWT `iss` chưa verify chỉ có thể là hint trong allowlist

Một số hệ thống nhiều issuers đọc `iss` từ payload để **chọn decoder**. Điều đó có thể chấp nhận được **chỉ như bước lựa chọn trong tập trusted issuers đã cấu hình**, không như bằng chứng rằng issuer được tin.

Sai:

```java
// KHÔNG DÙNG: attacker tự tạo iss và JWKS endpoint.
String issuer = decodeWithoutVerifying(token).getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
return decoder.decode(token);
```

Đúng về nguyên tắc:

```text
unverified iss = hint
    ↓
find issuer in static/trusted allowlist?
    ├─ no  -> reject
    └─ yes -> select pre-approved decoder/key source
                   ↓
              verify signature and iss == expected issuer
                   ↓
              verify aud, exp, typ/profile and authorities
```

Đừng đưa arbitrary issuer URL vào discovery/JWKS fetch; ngoài authentication bypass còn có rủi ro **SSRF** và outbound network abuse.

---

## 7. Nguy cơ “downgrade”: thất bại ở một cơ chế rồi thử cơ chế khác

Một anti-pattern rất nguy hiểm trong hệ thống hỗ trợ JWT lẫn opaque:

```java
// KHÔNG DÙNG: JWT lỗi thì "cứu" bằng cơ chế khác.
try {
    return validateAsJwt(rawToken);
} catch (Exception ignored) {
    return introspectAsOpaque(rawToken);
}
```

Vấn đề không chỉ là “có thêm một cách kiểm token”. Nó có thể làm **rối ranh giới an ninh**:

- JWT sai issuer/audience/type bị từ chối ở decoder, nhưng introspection endpoint trả `active=true` theo tiêu chuẩn khác.
- JWT sai chữ ký nhưng raw string tình cờ cũng là một reference token active trong một AS khác.
- Token bị thu hồi ở một nguồn nhưng được nhận ở nguồn khác do cache hoặc policy không thống nhất.
- Một nhánh bắt buộc audience/tenant, nhánh kia chỉ kiểm `active`.
- Error response/token downgrade trở thành một công cụ dò xem loại token nào được chấp nhận.
- Mỗi request có thể gây hai cuộc gọi upstream, tạo tải/latency và khó audit.

**Một cơ chế thất bại không được tự động hạ xuống cơ chế ít điều kiện hơn.** Nếu cùng API **cố ý** hỗ trợ hai loại access token, đó phải là policy có giới hạn, được review, và đảm bảo mọi đường đi đều đạt **cùng mức xác minh tối thiểu** cho resource đó.

### 7.1. Khi nào retry một cơ chế là hợp lệ?

**Retry network** ngắn cho lỗi tạm thời ở cùng một introspection endpoint là câu hỏi availability, khác với “thử authentication provider khác”. Cần phân biệt:

| Hành vi | Có thể chấp nhận? | Điều kiện |
|---|---|---|
| Retry HTTPS introspection sau timeout transient | Có thể. | Bounded retries/backoff, fail closed khi không có kết quả. |
| Refresh JWKS từ **trusted JWKS URL** khi gặp unknown `kid` | Có thể. | Bám key source allowlist, không lấy URL từ token header. |
| JWT sai audience → gọi opaque introspection để tìm nơi chấp nhận | **Không nên**. | Tránh bypass resource binding. |
| JWT sai chữ ký → parse payload rồi tự tạo principal | **Không**. | Không có bằng chứng phát hành. |
| Introspection trả `active=false` → decode raw token để cho qua | **Không nên**. | Tránh vô hiệu hóa semantics revocation/provider. |
| Dùng một introspection endpoint được AS hợp đồng cho cả JWT và reference token | Có thể. | Một validation policy chung, resource binding và schema chặt. |
| Tách JWT-only/opaque-only theo API route | Có thể. | Không có route alias dẫn đến nâng quyền hoặc bypass. |

### 7.2. Không bắt `Exception` quá rộng

Một custom resolver có thể viết:

```java
try {
    return jwtDecoder.decode(token);
} catch (Exception exception) {
    return null;  // tiếp tục thử Basic/session/opaque
}
```

Điều này che khuất:

- JWT invalid thật.
- JWKS endpoint timeout.
- Bug parse/serialization.
- Lỗi cấu hình trusted keys.
- Outage trong dependency.

Không đánh đồng lỗi token với lỗi hạ tầng và không đưa `null` làm tín hiệu “cho cơ chế khác thử” nếu contract không cho phép. Dù error mapping bên ngoài có thể là 401 hoặc 5xx, request chưa được xác minh **không được vào nghiệp vụ**.

---

## 8. Chọn cơ chế dựa trên nguồn nào thì đáng tin hơn?

Một thiết kế an toàn nên trả lời **trước khi nhìn token**: endpoint này chấp nhận credential scheme nào, do issuer nào cấp, dành cho audience/resource nào và có bắt buộc scope nào?

### 8.1. Route/path được công bố rõ

Ví dụ:

```text
/api/jwt/orders/**     -> chỉ JWT access token đã ký, trusted issuer A
/api/opaque/orders/**  -> chỉ token introspection tại AS B
```

Client có thể chọn URL, nhưng **mỗi URL là một resource có policy cố định**. Không tồn tại một route bí mật cho cùng dữ liệu mà xác thực yếu hơn. Nếu hai endpoint cùng truy cập một tập orders, chúng phải có authorization/business checks tương đương và không được biến thành đường vòng để truy cập trái quyền.

### 8.2. Host/tenant đã được registry cho phép

Ví dụ:

```text
acme.api.example.test -> tenant Acme -> issuer được allowlist
beta.api.example.test -> tenant Beta -> issuer được allowlist
```

Host vẫn là **input được client chọn**, vì vậy không phải bằng chứng caller thuộc tenant. Nhưng nó có thể chọn **policy issuer đã đăng ký**; sau đó token phải verify đúng issuer/tenant. Proxy `Forwarded` và `X-Forwarded-Host` chỉ được dùng khi gateway đã strip/overwrite headers từ client không tin cậy.

Không tạo issuer/JWKS URL động bằng cách nối host untrusted vào một string, ví dụ `https://{host}/.well-known/jwks.json`, rồi tin bất kỳ host nào.

### 8.3. API audience/resource contract

Một API có thể chỉ chấp nhận token dành cho `orders-api`. Đây là điều kiện phải được thực thi ở **mọi cơ chế**:

- JWT: kiểm `aud` trong verified claims.
- Opaque: kiểm `aud` trong trusted introspection metadata, hoặc dựa trên AS policy ràng buộc token với introspection requester theo hợp đồng.
- Service credentials: có quyền client-specific và resource binding riêng.
- User tokens: có subject và resource owner semantics rõ.

Nếu một cơ chế chỉ yêu cầu `active=true` còn cơ chế khác yêu cầu `iss`/`aud`/`typ`, API có nguy cơ tạo **assurance gap** giữa các đường.

### 8.4. Một issuer allowlist cho nhiều JWT issuers

Một hệ thống có thể dùng `JwtIssuerAuthenticationManagerResolver` hoặc resolver tương đương để chọn `AuthenticationManager` dựa trên issuer hint **nằm trong trusted allowlist**. Điều kiện bắt buộc:

1. Issuer được đăng ký/onboard trước.
2. Key source được phép từ metadata/trusted registry, không từ attacker.
3. Token được verify đúng issuer đã chọn.
4. Audience và token type/profile đúng API.
5. Subject/tenant namespace rõ ràng.
6. Resolver không chấp nhận issuer bất kỳ ngoài danh mục.

Không kết luận rằng “JWT có `iss` khớp tên tenant thì chắc hợp lệ”; verify và policy vẫn phải thực thi.

---

## 9. Mẫu an toàn A: tách `SecurityFilterChain` cho hai vùng API

Với Spring Security Servlet, một cách dễ kiểm soát là **hai filter chains** dùng matchers khác nhau. Không cần phân loại token bằng dấu chấm.

### 9.1. Dependencies

Nếu dự án dùng Spring Boot parent/BOM quản lý versions:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`spring-boot-starter-oauth2-resource-server` cung cấp Resource Server support; JWT signature validation cần JOSE libraries được BOM quản lý theo dependency graph thích hợp.

### 9.2. Cấu hình issuer/JWKS và introspection

`application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/realms/orders
          jwk-set-uri: https://auth.example.test/realms/orders/jwks
          audiences:
            - orders-api
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Các placeholders lấy từ runtime property sources. **Không lưu client secret thật trong Git hoặc code Java.**

- JWT mode dùng key source tin cậy + validators.
- Opaque mode dùng introspection endpoint + client authentication.
- Việc cả hai nhóm properties có mặt **không tự chứng minh** chúng đã được áp dụng cho đúng routes; các `SecurityFilterChain` dưới đây phải chọn mode tường minh.
- Introspection client ID là credential của Resource Server **để hỏi AS**, khác `client_id` metadata của token.

### 9.3. Hai chains với matchers cố định

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class MultiMechanismSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain jwtOrdersApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/jwt/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/jwt/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/jwt/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain introspectedOrdersApi(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/api/opaque/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/opaque/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/opaque/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain rejectUndeclaredRoutes(HttpSecurity http)
            throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll())
            .build();
    }
}
```

**Đây là ví dụ phân vùng API để học, không phải một production config đầy đủ.** Đặc biệt:

- `@Order` và `securityMatcher` chọn **filter chain đầu tiên khớp**; không tự thử chain thứ hai khi JWT authentication thất bại ở chain thứ nhất.
- Chain thứ nhất dùng **JWT**, không sniff số dấu chấm.
- Chain thứ hai dùng **opaque introspection**, cũng không sniff số dấu chấm.
- Chain cuối cùng deny-by-default để routes không thuộc hai vùng không vô tình chạy không bảo vệ. Cần thiết kế error handling cho catch-all phù hợp API.
- `csrf(...disable)` chỉ phù hợp với API stateless không dùng cookie/session authentication. Web login endpoints cần CSRF và session policy riêng.
- Nếu API cần public health endpoints hoặc actuator, định nghĩa policy và filter chain riêng đúng scope, không gắn `permitAll()` bừa vào mọi đường.
- Nếu cả hai vùng đọc cùng database, **service/repository phải có tenant/owner checks giống nhau**; việc đặt JWT/opaque ở URL khác nhau không tự làm dữ liệu an toàn.

### 9.4. Điều gì xảy ra khi token “trông giống JWT” đi vào nhánh opaque?

```http
GET /api/opaque/orders/42 HTTP/1.1
Authorization: Bearer a.b.c
```

Chain `/api/opaque/**` vẫn gọi `OpaqueTokenIntrospector`. Nó **không** chuyển sang `JwtDecoder` chỉ vì chuỗi có hai dấu chấm. Authorization Server quyết định token có active và đúng resource/token profile không; nếu inactive hoặc không có scope, request bị từ chối theo chính sách.

Ngược lại:

```http
GET /api/jwt/orders/42 HTTP/1.1
Authorization: Bearer opaque-value-without-dots
```

JWT chain yêu cầu `JwtDecoder` xác minh JWS; chuỗi không thể được kiểm như JWT access token sẽ bị từ chối. Nó **không** tự chuyển tới opaque endpoint để tìm cách cho qua.

### 9.5. Hai routes không được trở thành bypass của nhau

Nếu một order có thể được truy cập qua:

```text
/api/jwt/orders/42
/api/opaque/orders/42
```

cả hai phải áp dụng **cùng yêu cầu tài nguyên**: đúng issuer/AS contract, audience `orders-api`, read scope, tenant và owner. Không cho nhánh opaque dùng `.anyRequest().authenticated()` còn nhánh JWT dùng `SCOPE_orders:read`, vì attacker có thể chọn URL yếu hơn.

Đừng xây dựng “JWT-only admin API” và “opaque legacy API” có quyền tương đương nhưng một nhánh bỏ qua object authorization.

---

## 10. Mẫu an toàn B: chỉ một cơ chế introspection cho API hỗ trợ nhiều dạng access token

Một lựa chọn hợp lệ khác là **API chỉ có một chính sách authentication: RFC 7662 introspection**. AS bảo đảm token được introspect đúng và trả metadata được Resource Server phép sử dụng, bất kể token trông như JWT hay reference token.

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders:read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth ->
            oauth.opaqueToken(Customizer.withDefaults()))
        .build();
}
```

Tư duy này có lợi thế: **một giao thức xác thực cho cả token formats**, không cần format sniffing. Nhưng chỉ an toàn khi AS có hợp đồng:

- Chỉ trả `active=true` cho **access token hợp lệ** mà introspection requester có quyền dùng/kiểm tra.
- Có resource binding cho `orders-api` (qua `aud` hoặc policy introspection client).
- Có issuer/profile/token type checks rõ.
- `scope`/`roles`/tenant fields được xác định rõ.
- Có cách phân biệt inactive token với HTTP client credential/network lỗi.
- Có quyết định về introspection caching và revocation latency.

**Không coi `active=true` là quyền gọi tất cả endpoints**. Resource Server vẫn phải enforce authorities và object-level permissions.

### 10.1. Những điều không nên giả định về RFC 7662

Theo RFC 7662, response bắt buộc chứa `active` boolean. Các metadata `iss`, `aud`, `sub`, `exp`, `client_id`, `scope` và `token_type` là **tùy chọn trong giao thức**.

Nếu ứng dụng cần kiểm audience và issuer, phải thống nhất contract bắt buộc riêng hoặc bảo đảm AS giới hạn token cho đúng resource. Không tự phát minh default audience/issuer khi response không có trường.

Opaque introspection endpoint không phải “JWT verification fallback” theo mặc định; nó là **một authentication policy được chọn từ đầu**.

---

## 11. Khi cùng một URL bắt buộc nhận nhiều cơ chế

Một sản phẩm legacy có thể không thể thay URL và phải chấp nhận cả JWT access token lẫn reference token trên `GET /api/orders/**`. Trong trường hợp đó, câu hỏi thiết kế **không phải** “đếm dấu chấm thế nào” mà là “định nghĩa bộ issuer/token profiles được phép và cơ chế nào xác minh từng profile, không cho token substitution/downgrade”.

### 11.1. Lựa chọn ưu tiên: một contract introspection chung

Nếu Authorization Server có khả năng introspect cả JWT và reference tokens, dùng một `OpaqueTokenIntrospector` cho URL đó. Như vậy token được đánh giá theo một nguồn trạng thái/policy chung mà không sniff format.

### 11.2. Nếu phải có hai verification pipelines

Cần thiết kế một resolver có tính chính sách, ví dụ:

- Registry cố định các trusted issuers và JWKS endpoints.
- Registry định nghĩa các profile được chấp nhận, token types, audiences, signing algorithms, client authentication.
- Có quy tắc **xác định và ràng buộc token với profile** không dựa đơn thuần vào “hai dấu chấm”.
- Các metadata được đọc trước xác minh (nếu có) chỉ để **tìm trong allowlist**, không tự trở thành bằng chứng.
- Nếu token đã được quyết định thuộc một profile, **sai signature/issuer/audience/time là thất bại cuối cùng**, không thử provider khác có quy tắc nhẹ hơn.
- Nếu có trường hợp ambiguous giữa hai profiles, từ chối hoặc áp cùng một policy đủ mạnh đã thống nhất, không chọn nhánh “dễ qua”.
- Có negative integration tests cho mọi token substitution giữa profiles.
- Không cho JWT/opaque clients khác nhau cùng cấp quyền cao hơn dự kiến chỉ vì cả hai tạo `Authentication`.

**Nếu không xác định được một disambiguation rule đáng tin**, có thể cần thay đổi API/token contract, thay vì chấp nhận một heuristic không chứng minh được.

### 11.3. Đừng tự xây “try all providers until one passes” một cách mù quáng

Spring Security có nhiều kiểu authentication providers/managers. Tuy nhiên một `ProviderManager` với nhiều providers **không tự biến mọi thứ thành một thiết kế JWT/opaque an toàn**:

- Có provider chỉ hỗ trợ một authentication token class.
- Thứ tự provider và exception handling có ý nghĩa.
- Một provider có thể được thử sau provider khác trong một số tình huống.
- Nếu providers chấp nhận cùng credential với điều kiện khác nhau, policy có thể khó kiểm chứng.
- Fallback có thể làm issuer/audience/type checks không thống nhất.

Thiết kế phải nêu rõ **đúng provider nào được phép xác minh token/profile nào**, không chỉ thêm hai providers vào list rồi mong framework chọn chính xác.

### 11.4. Không dùng `BearerTokenResolver` để xác thực

`BearerTokenResolver` có trách nhiệm **lấy Bearer token từ HTTP request** (thường qua `Authorization` header), không phải xác thực chữ ký, issuer, audience hoặc scopes.

Một custom resolver có thể giới hạn cách truyền token, nhưng không thể trả lời “token nào đáng tin” chỉ vì chuỗi có ba đoạn. Đừng nhầm **extraction** với **authentication**.

---

## 12. Spring Security multi-issuer JWT: dùng issuer hint đúng cách

Khi **tất cả token được cho phép trên route đều là JWT access tokens** từ một số trusted issuers, có thể dùng issuer resolver — đây **không phải** chiến lược phân biệt JWT với opaque token bằng dấu chấm.

Ví dụ ý tưởng trong Spring Security Servlet:

```java
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtIssuerAuthenticationManagerResolver;

import jakarta.servlet.http.HttpServletRequest;

AuthenticationManagerResolver<HttpServletRequest> resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://idp-a.example.test/realms/orders",
        "https://idp-b.example.test/realms/orders"
    );
```

Sau đó có thể cấu hình resolver theo DSL tương ứng trên `oauth2ResourceServer(...)` hoặc `BearerTokenAuthenticationFilter` của version được dùng. Một số API builder/factory thay đổi giữa phiên bản Spring Security; khi triển khai thật cần tham khảo tài liệu bản thư viện cụ thể.

**Ý nghĩa chính:**

- Issuer hint từ token **không được chấp nhận nếu không nằm trong allowlist**.
- Chọn đúng manager/JWKS theo trusted issuer.
- Manager phải xác minh chữ ký và expected issuer, audience, time, token type/profile.
- Một JWT có `iss` giả từ issuer chưa đăng ký bị từ chối.
- Opaque token không phải profile của resolver này và không được tự “chạy sang” opaque auth vì parse fail.

### 12.1. Bổ sung audience và token profile

Ngay cả với trusted issuer resolver, Resource Server phải bảo đảm token dành cho `orders-api`. Nếu customized `JwtDecoder` không thêm audience validator, bạn có thể chấp nhận token của `payments-api` được ký cùng keyset.

Trong môi trường nhiều issuers, nên có cấu hình theo issuer:

| Issuer | JWK source | Audience | Allowed alg | Token profile |
|---|---|---|---|---|
| `idp-a.example.test/realms/orders` | Trusted JWKS A | `orders-api` | RS256 | JWT access token A |
| `idp-b.example.test/realms/orders` | Trusted JWKS B | `orders-api` | ES256 | JWT access token B |

Tập hợp này là **policy được khai báo trước**. Không lấy JWKS URL động theo `jku`, `x5u` hoặc `iss` chưa kiểm chứng từ JWT.

### 12.2. Với mỗi tenant một issuer

Nếu `/t/acme/**` bắt buộc token từ issuer Acme, tenant routing có thể chọn **trusted issuer policy** rồi decoder kiểm tra token đúng issuer. Host/path vẫn là request target, không phải bằng chứng membership; token phải verify đúng issuer/resource/tenant, và dữ liệu phải tenant-scoped.

Nếu request Acme mang token Beta, phải từ chối. Không sửa mismatch bằng cách tự chuyển query sang Beta chỉ vì token đó được verify bởi một issuer khác.

---

## 13. Các yêu cầu validate ở mọi cơ chế

### 13.1. Đối với JWT JWS access token

Một `JwtDecoder` được cấu hình đúng cần kiểm:

1. Cú pháp JWS/JWT chấp nhận được.
2. **JWS signature** hợp lệ với trusted public key.
3. **Algorithm allowlist** (ví dụ chỉ RS256 theo contract).
4. **Issuer** trong allowlist/expected issuer.
5. **Audience** chứa `orders-api`.
6. **Time**: `exp`, `nbf`; clock skew theo policy.
7. **Token type/profile**: tránh ID Token và JWT khác mục đích.
8. Required claims `sub`/`client_id`/`scope` theo user/workload profile.
9. Principal và authorities chỉ được tạo từ claims đã xác minh.
10. HTTP/method/object authorization được áp dụng riêng.

Không để `kid`, `jku` hoặc `alg` chưa xác minh tự tạo nguồn trust. Unknown `kid` chỉ có thể thúc đẩy refresh từ **trusted JWKS endpoint** theo chính sách, không tải key tùy ý từ URL trong token.

### 13.2. Đối với opaque/introspection access token

Một `OpaqueTokenIntrospector` cần:

1. Chỉ gọi **trusted introspection endpoint** cố định/allowlist.
2. Xác thực introspection requester bằng credential phù hợp.
3. HTTPS/TLS, timeout, rate limits và log masking.
4. Kiểm response có `active` boolean; `false` → reject.
5. Kiểm **resource/audience binding** theo metadata hoặc AS policy.
6. Kiểm issuer/token type/profile theo contract.
7. Parse `scope`/roles/tenant có schema rõ; không tự cấp mặc định.
8. Không tạo principal khi HTTP/network/schema lỗi.
9. Chính sách caching/revocation hữu hạn và fail-closed.
10. HTTP/method/object authorization được áp dụng riêng.

RFC 7662 có thể introspect nhiều loại token, nên **request có hai dấu chấm không tự là lỗi** ở nhánh opaque. Cơ chế được chọn theo resource policy, không phải token string.

### 13.3. Đối với web session hoặc HTTP Basic

Nếu hệ thống cũng có web login session:

- Phân vùng rõ `/web/**` và `/api/**` bằng matchers/filter chains.
- API Bearer-only không tái sử dụng `JSESSIONID` để authenticate khi Bearer invalid/absent.
- `SessionCreationPolicy.STATELESS` thường phù hợp API Bearer, nhưng cần kiểm tra không có custom filter/session fallback.
- Browser cookie authentication cần CSRF protection theo threat model.
- HTTP Basic nếu được phép phải có policy và transport TLS; không tự “thử Basic” khi Bearer JWT sai.
- Một client gửi cả cookie lẫn Bearer phải được xử lý theo policy explicit; không để cookie quyền cao đè Bearer user quyền thấp.

Không dùng “nhiều cơ chế” làm lý do cho phép **bất kỳ credential nào có vẻ hợp lệ** đi vào cùng service mà không phân biệt assurance level.

---

## 14. Spring Security: JWT decoder không phải một parser văn bản

Một cấu hình JWT Resource Server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/realms/orders
          audiences:
            - orders-api
```

Mục tiêu là để `JwtDecoder` thực hiện **verification + validation**, không chỉ tách chuỗi thành ba phần.

Một custom decoder:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class TrustedJwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer =
            "https://auth.example.test/realms/orders";
        String jwks =
            "https://auth.example.test/realms/orders/jwks";

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwks)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains("orders-api")) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience is not allowed",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audience
            )
        );

        return decoder;
    }
}
```

**Đây là mẫu issuer + audience + algorithm validation**. Khi tự tạo bean `JwtDecoder`, Spring Boot có thể **không áp dụng lại** các validators từ YAML `issuer-uri`/`audiences`. Đừng bỏ `JwtValidators.createDefaultWithIssuer` hoặc audience validator. Với RFC 9068 JWT access-token profile, còn cần kiểm các điều kiện `typ`/required claims theo token contract thực tế; không mặc định code trên đáp ứng mọi profile.

Một token có đúng hai dấu chấm nhưng signature giả **không** vượt qua decoder này. Một JWT có chữ ký đúng nhưng `aud=web-portal` cũng phải bị từ chối.

### 14.1. `NimbusJwtDecoder` không tự chấp nhận JWE mọi loại

Cấu hình `withJwkSetUri(...)` ở trên dành cho JWS signature verification với keyset đã tin. Nó **không đồng nghĩa** hỗ trợ giải mã mọi JWE compact năm phần hoặc nested JWT. Nếu AS phát encrypted tokens, hãy thiết kế pipeline và crypto keys phù hợp theo profile, hoặc sử dụng introspection khi AS hỗ trợ.

### 14.2. Không lấy public key từ JWT header

Một attacker có thể đưa:

```json
{
  "alg": "RS256",
  "kid": "attacker-key",
  "jku": "https://attacker.example.test/jwks.json"
}
```

Không chuyển `jku` thành HTTP request chỉ vì token header nói vậy. JWKS URL phải đến từ **configuration/discovery đã tin**, không phải input attacker. Đây là biện pháp chống key substitution và SSRF.

---

## 15. Kiểm thử những chuỗi dễ đánh lừa parser

Một bộ test giá trị phải có dữ liệu cố tình **mâu thuẫn giữa hình dạng và sự thật**. Nếu chỉ test “JWT thật có hai dấu chấm, opaque thật không dấu chấm”, bug format sniffing có thể không lộ.

### 15.1. Ma trận kiểm thử format khác trust

| Input / token | Hình dạng | Endpoint/profile | Kỳ vọng |
|---|---|---|---|
| JWS ba phần, chữ ký hợp lệ, issuer/aud/profile đúng | Hai dấu chấm | JWT-only | Authentication thành công, sau đó kiểm scope/owner. |
| JWS ba phần, payload bị sửa, chữ ký cũ | Hai dấu chấm | JWT-only | Từ chối, thường 401. |
| JWS ba phần, chữ ký ngẫu nhiên | Hai dấu chấm | JWT-only | Từ chối. |
| `a.b.c` | Hai dấu chấm | JWT-only | Không được xem là verified JWT. |
| `a.b.c` | Hai dấu chấm | Opaque-only, AS báo `active=false` | Từ chối từ introspection. |
| `a.b.c` | Hai dấu chấm | Opaque-only, AS xác nhận access token active đúng resource | Có thể authenticate nếu đạt contract. |
| `abcDEF123` | Không dấu chấm | Opaque-only, active=true đúng resource | Có thể authenticate. |
| `abcDEF123` | Không dấu chấm | JWT-only | Từ chối; không tự fallback. |
| `a.b.c.d.e` | Bốn dấu chấm | JWT JWS-only | Từ chối nếu decoder không hỗ trợ JWE. |
| `a.b.c.d.e` | Bốn dấu chấm | Opaque-only, active=true đúng resource | Có thể authenticate theo contract AS. |
| JWS header `alg=none`, signature rỗng | Hai dấu chấm | JWT-only | Từ chối theo signed access-token policy. |
| JWT ký bởi private key attacker | Hai dấu chấm | JWT-only | Từ chối dù claims trông hợp lệ. |
| JWT issuer không trong allowlist | Hai dấu chấm | JWT-only | Từ chối. |
| JWT issuer đúng, audience khác API | Hai dấu chấm | JWT-only | Từ chối. |
| OIDC ID Token signed đúng, `aud=web-portal` | Hai dấu chấm | API access-token profile | Từ chối. |
| JWT access token đúng, thiếu `orders:read` | Hai dấu chấm | Read endpoint | Authenticated, nhưng bị 403 do thiếu quyền. |
| Opaque token active đúng resource, thiếu scope | Bất kỳ | Read endpoint | Không cấp read authority → 403. |
| JWT đúng, scope đúng, khác tenant | Hai dấu chấm | Read endpoint | Từ chối quyền tenant. |
| JWT đúng, scope đúng, order của Bob | Hai dấu chấm | Read endpoint | Từ chối object permission. |
| Introspection lỗi HTTP 503 | Bất kỳ | Opaque-only | Fail closed; không thử local parse để cho qua. |
| JWKS endpoint lỗi khi chưa có key | Hai dấu chấm | JWT-only | Fail closed; không chuyển introspection tùy tiện. |

**Điểm kiểm thử chính:** token ba phần có thể bị từ chối ở JWT mode; token ba phần **có thể là opaque hợp lệ** khi AS xác nhận theo contract; token không dấu chấm không tự được chấp nhận. Cả 401 và 403 đều phải xuất phát từ **kết quả xác thực/phân quyền**, không phải độ dài/shape chuỗi.

### 15.2. Bộ dữ liệu kiểm thử chống nhầm loại token

Nên tạo:

```text
jwt-valid-orders-read
jwt-valid-orders-write-only
jwt-valid-payments-audience
jwt-valid-web-portal-id-token
jwt-expired
jwt-forged-signature
jwt-alg-none
opaque-active-orders-read-without-dots
opaque-active-orders-read-with-two-dots
opaque-active-orders-read-with-four-dots
opaque-inactive-with-two-dots
opaque-active-payments-audience
opaque-active-no-scope
arbitrary-string-with-two-dots
arbitrary-string-with-zero-dots
```

Các tên fixture là **mô tả**, không phải giá trị token thật. Với JWT signing test, dùng RSA/EC keypair thử nghiệm và JWKS endpoint test. Với opaque, dùng mock AS introspection endpoint có khả năng trả metadata cho token thử nghiệm.

---

## 16. Test tích hợp: đảm bảo route không bị format sniffing

### 16.1. Test bằng `MockMvc` với header Bearer thật

`spring-security-test` cung cấp `jwt()`/`opaqueToken()` để dựng principal giả. Chúng rất hữu ích cho HTTP authorization, nhưng **bỏ qua decoder/introspection pipeline**. Vì thế không dùng chúng để chứng minh cơ chế chọn token theo route.

Để test format confusion thật, cần:

1. Gửi HTTP header `Authorization: Bearer ...` thật qua `MockMvc` hoặc embedded server.
2. Dùng `JwtDecoder` test có policy rõ, hoặc tốt hơn là JWT signed thật + local JWKS.
3. Dùng `OpaqueTokenIntrospector` test endpoint/spy để chứng minh opaque route gọi đúng AS.
4. Assert **cơ chế không được chọn** không bị gọi.
5. Assert status, authorities và domain data đúng.
6. Không dùng client secret production trong tests.

### 16.2. Bài kiểm tra có thể thực hiện ở mức scenario

```java
@Test
void jwtShapedOpaqueTokenStillGoesToIntrospectionRoute()
        throws Exception {

    // Given introspection endpoint chỉ công nhận token "a.b.c"
    // với active=true, aud=orders-api, scope=orders:read.

    mvc.perform(get("/api/opaque/orders/42")
            .header("Authorization", "Bearer a.b.c"))
        .andExpect(status().isOk());

    // Cần spy/mock AS chứng minh introspection đã được gọi.
    // Không để JwtDecoder được gọi cho request này.
}
```

Test này là **skeleton**, chỉ đúng nếu có controller/fixtures cấp quyền trên order 42. Việc assert `isOk()` cần tenant/owner fixtures phù hợp. Trong test thực tế có thể assert spy interaction và response principal/subject tương ứng.

Ví dụ ngược lại:

```java
@Test
void opaqueLookingTokenIsNotRoutedToIntrospectionFromJwtApi()
        throws Exception {

    mvc.perform(get("/api/jwt/orders/42")
            .header("Authorization",
                "Bearer opaque-test-token"))
        .andExpect(status().isUnauthorized());

    // Verify introspection endpoint không được gọi.
}
```

Đây cũng là skeleton giả định JWT decoder từ chối chuỗi không phải signed JWT access token. Nếu test chỉ dùng `jwt()`, nó sẽ không thực sự kiểm cơ chế route/token extraction.

### 16.3. Test bearer header malformed và transport

Không được cho phép hai kênh token cùng lúc chỉ vì format không rõ:

```http
GET /api/jwt/orders/42?access_token=token-B HTTP/1.1
Authorization: Bearer token-A
```

Cần kiểm tra `BearerTokenResolver`/server policy và RFC 6750. Mặc định nên ưu tiên `Authorization` header, không mở query-string token vì dễ rò vào proxy logs, browser history. Một token có dấu chấm trong header vẫn phải được truyền nguyên vẹn đến **cơ chế đã cấu hình**; không xóa dấu chấm, không decode Base64URL thủ công để “làm sạch” credential.

### 16.4. Đừng test chỉ một phía

Nếu chỉ test `GET /api/jwt/orders/**`, có thể không phát hiện `/api/opaque/orders/**` là đường đi yếu hơn. Bộ test phải kiểm:

- JWT valid → JWT route cho phép theo scope/owner.
- JWT invalid → JWT route 401, **không introspect**.
- Opaque active → opaque route cho phép theo contract.
- Opaque inactive → opaque route 401, **không thử JWT**.
- Token có hai dấu chấm → opaque route vẫn introspect.
- Token không dấu chấm → JWT route vẫn cần decoder.
- Một token có scope sai → 403 trên **cả hai routes**.
- Một token có audience sai → không truy cập trên **cả hai routes**.
- Một caller cross-tenant → không truy cập trên **cả hai routes**.
- URL không được khai báo → bị deny-by-default.

---

## 17. Kiểm thử mật mã với JWT ký thật

### 17.1. Vì sao mock decoder chưa đủ?

Một test với `JwtDecoder` stub có thể trả claims giả cho chuỗi `a.b.c` mà không verify chữ ký. Nó giúp test **Spring filter routing**, nhưng không chứng minh production decoder an toàn.

Để kiểm trust root:

1. Tạo RSA test keypair `K1`.
2. Công bố public JWK của `K1` qua trusted local JWKS endpoint.
3. Dùng private key test để ký JWS access token.
4. Cấu hình `NimbusJwtDecoder` với JWKS test và issuer/audience validator.
5. Gửi signed token qua `Authorization: Bearer` tới JWT route.
6. Sửa một byte payload nhưng giữ chữ ký, assert 401.
7. Ký token bằng private key `K2` không trong trusted JWKS, assert 401.
8. Tạo ID Token `aud=web-portal` được ký đúng `K1`, assert API từ chối.
9. Thử `alg=none`, `HS256` hoặc `jku` attacker, assert không bypass.
10. Không dùng private signing key production trong test.

**Không thể chứng minh cryptographic verification** bằng cách chỉ gọi Base64URL decode và assert `sub`. Chính chữ ký cùng nguồn key tin cậy và các validators mới tạo trust.

### 17.2. Không dùng JWE shape như một đường vòng

Khi test chuỗi năm thành phần, xác định hợp đồng thật:

- JWT-only signed-JWS route không hỗ trợ JWE → từ chối.
- JWE-specific route đã thiết kế → decrypt/validate đúng profile và keys.
- Opaque introspection route → AS quyết định token có active và resource binding.
- Không có cơ chế nào được phép → từ chối.

Không tự thêm “JWE accepted” vào decoder chỉ vì test gặp 4 dấu chấm.

---

## 18. Xác thực thành công không đồng nghĩa được quyền xem tài nguyên

Một token hợp lệ chứa:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "tenant_id": "tenant-a"
}
```

vẫn không được dùng để xem đơn thuộc Bob hoặc tenant B.

Nên có tầng dữ liệu:

```java
public OrderDto readOrder(
        String orderId,
        VerifiedActor actor) {

    return repository
        .findByIdAndTenantIdAndOwnerIssuerAndOwnerSubject(
            orderId,
            actor.tenantId(),
            actor.issuer(),
            actor.subject())
        .map(this::toDto)
        .orElseThrow(OrderNotFoundException::new);
}
```

`VerifiedActor` phải được tạo từ **authenticated principal** đã qua JWT/introspection và schema validation; các field tenant/user không lấy từ raw token chưa xác minh hoặc HTTP headers do client gửi.

Với workload token (Client Credentials), `sub` có thể là service identity chứ không phải user. Vì vậy actor profile và access policy có thể khác, nhưng **vẫn phải ràng buộc đúng resource/tenant và scopes**.

### 18.1. Một AccessDenied không làm token “invalid”

Phân biệt:

| Kết quả | Ý nghĩa | Phản hồi thường thấy |
|---|---|---|
| JWT signature sai | Authentication thất bại. | 401, Bearer `invalid_token`. |
| Opaque introspection `active=false` | Authentication thất bại. | 401. |
| Token hợp lệ nhưng `aud` không đúng API | Token không được chấp nhận cho resource này. | 401. |
| Token hợp lệ nhưng thiếu `orders:read` | Authentication có thể thành công, authorization thất bại. | 403, có thể `insufficient_scope`. |
| Token hợp lệ, đủ read, sai owner/tenant | Object authorization thất bại. | 403 hoặc 404 theo API policy. |

Không gộp cả năm trường hợp thành một quy tắc “token có ba phần hay không”. Trong Spring Security, `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` thường đảm nhiệm challenge tương ứng với authentication/authorization context.

---

## 19. Các lỗi implementation dễ gặp

### 19.1. Dùng `String.split("\\.")` không hiểu semantics

`String.split(...)` còn có hành vi mặc định bỏ các phần rỗng cuối. Vì thế:

```text
header.payload.
```

có thể bị đếm sai số phần nếu dùng `split("\\.")` không truyền limit phù hợp. Nhưng **sửa kỹ thuật split không giải quyết vấn đề bảo mật**: một parser đếm phần chính xác vẫn không xác minh token.

Nếu cần diagnostics về serialization, dùng JOSE library chuẩn thay vì tự tách/chuyển base64 bằng tay. **Không dùng kết quả parser để cấp trust.**

### 19.2. Cho `alg=none` vì JWT có đúng cấu trúc

Đây là lỗi authentication. Decoder phải từ chối token không có integrity protection theo signed-access-token contract. Không cho attacker tự chọn algorithm hoặc public key.

### 19.3. Lấy key từ `jku`/`x5u` trong header

Đây có thể là key-source confusion và SSRF. Chỉ dùng JWKS URL được cấu hình hoặc lấy từ issuer metadata đã tin, không từ input của JWT.

### 19.4. Coi mọi `eyJ...` là JWT

`eyJ` chỉ là prefix thường gặp khi Base64URL decode ra JSON bắt đầu bằng `{"...`. Attacker có thể tạo opaque string hoặc một chuỗi giả mở đầu bằng `eyJ`. Không dùng prefix làm trust signal.

### 19.5. Coi token không dấu chấm là opaque active

Một opaque token chỉ active khi được Authorization Server xác minh bằng introspection (hoặc cơ chế hợp đồng tương đương). Chuỗi ngẫu nhiên không dấu chấm **không tự hợp lệ**.

### 19.6. JWT sai rồi fallback qua opaque mode

Có nguy cơ bypass validators chặt và làm lộ token tới endpoint không được phép. Policy phải định nghĩa mode trước; failed authentication không đổi mode.

### 19.7. Coi mọi `active=true` là access token dành cho API

Introspection response có thể thiếu audience/token-type theo RFC 7662. Cần AS–API contract về resource binding, issuer, token type và scope. Không dùng token của `payments-api` gọi `orders-api`.

### 19.8. Nhận OIDC ID Token vì nó cũng ký RSA

ID Token là assertion cho OIDC client; cần kiểm access-token profile/audience. Chữ ký cùng issuer không làm ID Token thành API access token.

### 19.9. Lấy issuer từ unverified payload để tự động trust

Một JWT tự khai `iss` không thể yêu cầu ứng dụng tải keys từ issuer tùy ý. Chỉ tin registry/allowlist các issuers đã onboard.

### 19.10. Dùng Basic/session làm fallback

API Bearer-only không được chuyển sang web session hoặc HTTP Basic sau Bearer token thất bại nếu không có chính sách explicit. Có thể tạo cơ hội sử dụng identity của user khác trên cùng browser/cookie.

### 19.11. Không kiểm tenant/owner

Authentication bằng JWT hay introspection không thay thế object-level authorization. Scope `orders:read` không tự cho phép xem mọi order thuộc mọi tenant.

### 19.12. Test chỉ dùng `jwt()` hoặc `opaqueToken()`

Test post-processors dựng authentication giả, không kiểm JWT signature, issuer/audience, token extraction hay introspection HTTP. Cần signed-token và mock-AS integration tests riêng.

### 19.13. Phân loại theo extension của URL

`/tokens/abc.jwt`, một filename có `.jwt` hoặc query parameter `format=jwt` cũng do client điều khiển, không phải bằng chứng token format hay trust. Nếu API có route riêng, phải xác định policy độc lập và verify token theo policy đó.

### 19.14. Kiểm tra `isAuthenticated()` của một token tự tạo

Một object `Authentication` có thể được code tự xây với `isAuthenticated=true` nhưng chứa claims chưa verify. Chỉ nên tạo authenticated token qua provider/manager đã thực hiện xác minh thực sự; không đặt cờ verified bằng suy luận từ số dấu chấm.

### 19.15. Cache “last validated token” theo connection hoặc IP

Cùng IP hoặc TCP connection có thể phục vụ nhiều users. Không sử dụng principal của request trước cho request không token hoặc token khác. Với introspection cache, khóa theo token/issuer/resource/policy và TTL rõ, không lưu raw Bearer credential ở nơi có thể bị log.

---

## 20. Quan sát và xử lý sự cố mà không làm lộ token

Một hệ thống đa cơ chế nên phân biệt các lỗi:

```text
AUTHN_JWT_SIGNATURE_INVALID
AUTHN_JWT_ISSUER_MISMATCH
AUTHN_JWT_AUDIENCE_MISMATCH
AUTHN_JWT_TOKEN_TYPE_INVALID
AUTHN_OPAQUE_INACTIVE
AUTHN_INTROSPECTION_SCHEMA_INVALID
AUTHN_INTROSPECTION_UPSTREAM_FAILURE
AUTHN_MECHANISM_NOT_ALLOWED_FOR_ROUTE
AUTHZ_SCOPE_MISSING
AUTHZ_TENANT_DENIED
AUTHZ_OBJECT_DENIED
```

Đây là **reason codes cho log/metrics nội bộ**, không phải các mã lỗi Bearer được RFC 6750 định nghĩa. Khi trả client, giữ HTTP status/challenge đúng ngữ cảnh và hạn chế rò thông tin.

### 20.1. Không log raw token để debug số dấu chấm

Một anti-pattern:

```java
log.info("raw token={} dotCount={}", token, countDots(token));
```

Bearer token là **credential**, nên log nó sẽ tạo nguy cơ chiếm dụng nếu logs bị truy cập. Chỉ cần quan sát:

- Matched API route template, security chain ID.
- Authentication mechanism **đã được chọn từ policy**, không phải “phỏng đoán format”.
- Issuer configuration ID từ registry.
- Error reason có cardinality hữu hạn.
- Tỷ lệ JWT validation failures, introspection failures.
- JWKS latency/cache refresh, introspection latency.
- Client correlation/request ID.

Không đưa `sub`, `jti`, token hoặc payload unverified vào metric labels. Không đưa full introspection response chứa PII vào error logs.

### 20.2. Dấu hiệu của downgrade bug

Nếu log nội bộ ghi:

```text
jwt_verification_failed → fallback_to_opaque → authenticated
```

trên cùng một request mà policy không định nghĩa điều đó, cần điều tra ngay. Các bước:

1. Xác định route/chain thực sự được chọn.
2. Xác định cơ chế nào tạo `Authentication` cuối cùng.
3. Kiểm issuer/audience/type/scope validators của từng provider.
4. Kiểm có code catch-all/fallback hay token-format regex không.
5. Kiểm AS introspection có trả `active=true` cho token khác resource không.
6. Thử token giả ba phần, ID token và JWT sai signature.
7. Chặn route bypass bằng cấu hình policy rõ và regression tests.

Không sửa bằng cách log thêm raw token production hoặc tắt JWT signature validation để tránh 401.

---

## 21. Thực hành: phân tích sáu request

### Tình huống A — JWT giả có hai dấu chấm

```http
GET /api/jwt/orders/42 HTTP/1.1
Authorization: Bearer header.payload.fake
```

**Đúng:** JWT decoder xác minh chữ ký theo trusted key và từ chối. **Sai:** hệ thống chỉ đếm hai dấu chấm rồi tạo principal.

### Tình huống B — Opaque token hợp lệ có hai dấu chấm

```http
GET /api/opaque/orders/42 HTTP/1.1
Authorization: Bearer a.b.c
```

Introspection endpoint được AS cho phép kiểm tra `a.b.c`. Nếu trả `active=true` với audience, scope và actor hợp đồng đủ thì có thể tạo authentication. Việc token có hai dấu chấm không làm nó thành JWT.

### Tình huống C — JWT hợp lệ nhưng gửi sai route

```http
GET /api/opaque/orders/42 HTTP/1.1
Authorization: Bearer <valid-jwt>
```

Nếu opaque route dùng introspection-only, AS quyết định token này có thể introspect hay không. Không tự chuyển sang JWT branch; không giả định “valid JWT” ở issuer nào đó đủ cho mọi API.

### Tình huống D — ID Token được ký đúng

```http
GET /api/jwt/orders/42 HTTP/1.1
Authorization: Bearer <valid-oidc-id-token>
```

Nếu `aud=web-portal` và token type/profile là ID Token, Resource Server phải từ chối. Chữ ký đúng không thay đổi audience/purpose.

### Tình huống E — JWT đúng issuer nhưng sai audience

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "aud": ["payments-api"],
  "scope": "orders:read"
}
```

API `orders-api` từ chối dù chữ ký và scope đều đúng. JWT có hai dấu chấm không chứng minh applicability.

### Tình huống F — Token đúng nhưng order của tenant khác

```text
Token: JWT signed, aud=orders-api, scope=orders:read, tenant=t-acme
URL:   /api/jwt/orders/42
Order: id=42, tenant=t-beta
```

API phải từ chối theo tenant/object policy. Đây là **authorization boundary**, không phải format detection.

---

## 22. Checklist bàn giao cho một Resource Server đa cơ chế

| Câu hỏi | Yêu cầu cần đạt |
|---|---|
| **API này nhận cơ chế nào?** | JWT-only, introspection-only hoặc multi-profile có contract; không đoán từ dấu chấm. |
| **Nguồn chọn cơ chế là gì?** | Route/host/issuer registry đáng tin, hoặc một introspection policy chung. |
| **Có fallback provider không?** | Không downgrade khi token invalid; mọi exception/path được thiết kế tường minh. |
| **JWT key trust root là gì?** | JWKS/public key từ trusted issuer/config; không từ `jku` attacker. |
| **JWT alg allowlist?** | Chỉ algorithms được cấu hình; không nhận `none` khi policy yêu cầu JWS signed. |
| **Issuer/audience/time?** | Kiểm từ verified token, đúng `orders-api` và token lifetime. |
| **Token type/profile?** | Từ chối ID Token/refresh token/assertion không dành cho API. |
| **Introspection contract?** | `active` boolean, đúng client auth, resource binding, metadata schema. |
| **Scope/authority mapping?** | Không tự thêm quyền khi scope thiếu hoặc claim sai kiểu. |
| **Tenant/object checks?** | Thực thi trên service/repository, không chỉ HTTP route. |
| **Two-route parity?** | Không có endpoint alternative cho cùng dữ liệu với policy yếu hơn. |
| **Multi-issuer allowlist?** | Issuer hint không được phép trust arbitrary URLs. |
| **HTTP challenges?** | 401 vs 403, `WWW-Authenticate` và các errors theo RFC 6750. |
| **Caching/revocation?** | Bounded TTL, no identity reuse giữa requests. |
| **Testing?** | JWT giả/ID token/opaque có dấu chấm/JWE shape/AS errors, signed JWT và introspection integration. |
| **Observability?** | Reason codes, request IDs; không log raw Bearer token/secret/PII. |

---

## 23. Mô hình quyết định cuối cùng

```text
API Resource Server receives:
  Authorization: Bearer <arbitrary string>
                         │
                         ▼
   Choose predefined security policy for resource
    ├─ JWT access-token profile
    │    └─ trusted issuer/JWKS + signature/alg/iss/aud/exp/typ validation
    │
    ├─ Opaque/introspection access-token profile
    │    └─ trusted AS + authenticated introspection + active/resource metadata
    │
    └─ Unsupported mechanism
         └─ DENY
                         │
                         ▼
           Did selected mechanism verify?
                  ├─ No  → reject
                  └─ Yes → authenticated principal
                                │
                                ▼
                    Check scope / actor / tenant / object
                             ├─ Deny
                             └─ Permit
```

**Không có bước “đếm dấu chấm để quyết định mức tin cậy”.** Nếu có bước nhận diện format vì lý do hiệu năng, nó chỉ là **input chưa được xác minh** phục vụ parser nội bộ, không được phép làm thay đổi trust policy hoặc tạo authentication thành công.

## 24. Tài liệu kỹ thuật tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): compact serialization, protected header, signature và `kid`.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516.html): năm thành phần của JWE compact serialization, encryption/integrity.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): JWT claims, issuer, audience, time và unsecured JWT.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): trusted public key sets.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): cross-JWT confusion, token substitution, mutually exclusive validation rules, algorithm/key trust.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): `at+jwt`, access-token-specific claims và profile.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): active metadata, introspection request và resource binding policy.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): cú pháp Bearer token, HTTP transport/challenge.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): phân biệt OIDC ID Token và OAuth access token.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, verified JWT, issuer/audience validation.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector` và introspection.
- [Spring Security — OAuth 2.0 Resource Server Multitenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): trusted issuers và resolver.
- [Spring Security — Java Configuration / SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): nhiều chains, `securityMatcher` và thứ tự matching.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): route-level authorization.
- [OWASP — JSON Web Token Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): các rủi ro thường gặp khi triển khai JWT.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, resource-level permission checks.

**Kết luận:** **Token có hai dấu chấm không vì thế mà đáng tin là JWT; token không có dấu chấm không vì thế mà là opaque token hợp lệ.** Compact JWS, JWE, reference tokens và ID Tokens có thể có hình dạng giống hoặc khác nhau, nhưng **không có hình dạng nào tự chứng minh danh tính, issuer, audience hay quyền**. Với Spring Security hỗ trợ nhiều cơ chế, hãy chọn cơ chế theo **policy đã định nghĩa trước**, xác minh token đầy đủ trong nhánh đó, không fallback để hạ cấp kiểm tra, và luôn áp scope/tenant/object authorization sau khi authentication thành công.

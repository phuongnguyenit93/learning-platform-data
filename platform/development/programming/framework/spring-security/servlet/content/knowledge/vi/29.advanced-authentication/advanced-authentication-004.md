# Passkey với WebAuthn: đăng ký thông tin xác thực và đăng nhập

**Bối cảnh:** Spring Security cho **Servlet/Spring MVC**, Java 17+, Spring Boot 3.x và phiên bản Spring Security có module WebAuthn/passkey tương ứng. Nội dung đi từ nguyên lý public-key credential đến hai luồng **registration** và **authentication**, dữ liệu backend phải lưu, kiểm tra bảo mật bắt buộc, tích hợp SecurityFilterChain, ví dụ JavaScript và kiểm thử. Tên endpoint tự thiết kế trong ví dụ luôn được ghi rõ để không nhầm với đường dẫn mặc định của một release Spring Security cụ thể.

## 1. Passkey và WebAuthn hoạt động dựa trên điều gì?

**Passkey** là thông tin xác thực dựa trên cặp khóa bất đối xứng. Khi đăng ký, authenticator tạo **private key** được bảo vệ trên thiết bị hoặc trong hệ sinh thái quản lý passkey và **public key** gửi tới Relying Party (RP, tức ứng dụng). Khi đăng nhập, authenticator ký một challenge mới do server phát ra; server dùng public key đã lưu để kiểm tra chữ ký. Private key **không được gửi tới Spring Security**, và backend không phải lưu mật khẩu dùng lại của passkey.

**WebAuthn (Web Authentication API)** là giao diện tiêu chuẩn của browser với hai thao tác chính:

- `navigator.credentials.create({ publicKey: ... })`: yêu cầu tạo credential và trả public key/attestation data để đăng ký.
- `navigator.credentials.get({ publicKey: ... })`: yêu cầu assertion được ký bởi credential đã tồn tại để xác thực.

WebAuthn thuộc hệ sinh thái **FIDO2**, cùng CTAP cho giao tiếp giữa thiết bị/browser và authenticator (USB, NFC, BLE, platform authenticator, passkey manager). Spring MVC **không triển khai CTAP**; server phát WebAuthn options, xác minh response và quản lý tài khoản/phiên.

### 1.1 Khác mật khẩu và OTP như thế nào?

| Yếu tố | Password | OTP/TOTP | Passkey/WebAuthn |
| --- | --- | --- | --- |
| Bằng chứng đăng nhập | Bí mật do người dùng biết. | Mã tạm thời hoặc secret. | Chữ ký hợp lệ từ private key gắn RP ID. |
| Server giữ | Password hash. | Thông tin kiểm tra OTP. | Credential ID + public key + mapping tài khoản. |
| Khả năng bị phishing | Có thể nhập nhầm vào trang giả. | OTP có thể bị relay. | Có ràng buộc RP ID/origin, chống phishing tốt hơn. |
| Trải nghiệm | Người dùng nhập mật khẩu. | Đọc/nhập mã. | Thao tác thiết bị, PIN/sinh trắc/khóa bảo mật tùy authenticator. |
| Đòi hỏi recovery | Có. | Có. | Có, đặc biệt khi mất mọi thiết bị/passkey. |

**Sinh trắc không đi tới server.** Face ID, vân tay hoặc PIN chỉ mở khóa authenticator và đáp ứng yêu cầu xác minh người dùng ở thiết bị. Backend nhận chữ ký và cờ **User Presence (UP)** / **User Verification (UV)**, không nhận ảnh mặt hoặc template vân tay.

Passkey có thể **đồng bộ qua nhiều thiết bị** hoặc **gắn với authenticator phần cứng**; không phải mọi passkey đều hardware-bound. Vì vậy chính sách thiết bị, attestation và sign counter cần được lựa chọn theo rủi ro thực tế.

## 2. Các thuật ngữ và ranh giới tin cậy

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Relying Party (RP)** | Ứng dụng đăng ký/xác minh credential, ví dụ Spring MVC Portal. |
| **RP ID** | Domain logic của credential, chẳng hạn `example.com` hoặc `localhost`; **không** chứa scheme, port, path. |
| **Origin** | Scheme + host + port của trang gọi WebAuthn, ví dụ `https://login.example.com` hoặc `http://localhost:8080`. |
| **Authenticator** | Thành phần nắm private key, tạo credential và ký assertion. |
| **User handle** | Bytes ổn định đại diện cho tài khoản tại RP; tránh dùng email có thể thay đổi làm ID bất biến. |
| **Credential ID** | Định danh credential; backend dùng để tìm public key được đăng ký. |
| **Challenge** | Dãy bytes ngẫu nhiên do backend tạo cho một lần registration/login; có TTL và phải chống replay. |
| **Public key** | Khóa công khai từ registration, lưu tại backend để xác minh signature. |
| **Attestation** | Thông tin tùy chọn về xuất xứ/chính sách của authenticator trong registration. |
| **Assertion** | Kết quả authentication gồm authenticator data, client data và chữ ký. |
| **Discoverable credential** | Credential mà authenticator có thể tìm theo RP ID, hỗ trợ đăng nhập không nhập username. |

### RP ID khác origin

Ví dụ user truy cập trang `https://login.example.com`. RP ID có thể là `example.com` nếu đáp ứng quy tắc domain hợp lệ, còn **origin** của trang vẫn là `https://login.example.com`. Server phải cấu hình cả **RP ID cố định** và **allowlist origin chính xác**. WebAuthn dùng hash của RP ID trong dữ liệu authenticator; `clientDataJSON` chứa origin, và server phải kiểm tra cả hai.

- `rpId: "example.com"` là tên miền, **không** phải `"https://example.com:443"`.
- `origin: "https://login.example.com"` có scheme; cổng khác mặc định (nếu có) thuộc origin.
- Không dùng RP ID tùy ý như `"com"` hoặc một domain ngoài phạm vi website.
- `localhost` với `http://localhost:8080` thường là ngoại lệ secure context cho **development**. Production nên dùng HTTPS thật và domain được quản trị.
- Thay RP ID sau khi đã phát hành có thể khiến credential cũ không dùng ở domain mới; lập kế hoạch domain/RP ID từ đầu.

**Không lấy RP ID và allowed origins từ request JSON của client.** Chúng là cấu hình đáng tin cậy ở backend. Một request có header `Origin` trông đúng cũng chưa phải bằng chứng; WebAuthn verifier phải kiểm tra `origin` trong client data gắn với response.

## 3. Credential cần lưu những gì?

Mô hình lưu trữ gợi ý cho mỗi credential:

| Field | Kiểu dữ liệu | Mục đích |
| --- | --- | --- |
| `account_id` | User ID nội bộ | Liên kết với tài khoản đã xác minh. |
| `user_handle` | Bytes ổn định | Liên kết user entity WebAuthn với account, có thể hỗ trợ username-less login. |
| `credential_id` | Bytes / Base64url, **unique** | Tìm credential qua assertion. |
| `public_key` | COSE public key hoặc dạng thư viện hỗ trợ | Xác minh chữ ký đăng nhập. |
| `algorithm` | COSE algorithm | Chọn trình xác minh đúng thuật toán đã đăng ký. |
| `signature_count` | Số không âm | Theo dõi dấu hiệu clone khi authenticator có counter có ý nghĩa. |
| `backup_eligibility / backup_state` | Flags BE/BS, nếu có | Quan sát đặc tính có thể backup/sync. |
| `transports` | internal, usb, nfc, ble, hybrid… | Gợi ý cho browser UX; không phải bằng chứng phân quyền. |
| `status` | active/revoked | Ngăn credential đã bị vô hiệu hóa. |
| `created_at / last_used_at / label` | Metadata | Quản lý danh sách passkey và audit. |

**Private key, PIN, fingerprint, face template** không thuộc database backend. Credential ID/public key không phải secret tương tự password, nhưng user handle, credential IDs, attestation metadata vẫn có thể nhận diện người dùng nên cần bảo vệ và chính sách lưu trữ.

Challenge cần lưu tạm trong challenge repository/cache (với TTL, loại thao tác và binding). Một credential có thể tồn tại song song nhiều bản trên nhiều thiết bị; account có thể sở hữu **nhiều passkeys**. Dùng unique constraint cho credential ID, không dựa riêng vào JavaScript `excludeCredentials` để chống trùng.

## 4. Đăng ký passkey: luồng registration

Thường user đã đăng nhập bằng mật khẩu/MFA, OIDC hoặc cơ chế bootstrap an toàn trước khi được thêm passkey. Registration là thao tác cấp **một cách đăng nhập mới** vào account, vì vậy bắt buộc bảo vệ chống CSRF và kiểm tra quyền/reauthentication theo rủi ro.

```text
User             Browser                  Spring Servlet RP            Authenticator
 |  Thêm passkey    |                             |                           |
 |----------------->| POST registration options   |                           |
 |                  |---------------------------->|                           |
 |                  |  challenge + rp + user + options                         |
 |                  |<----------------------------|                           |
 |                  | navigator.credentials.create({publicKey})                |
 |                  |-------------------------------------------------------->|
 |                  |           tạo keypair, yêu cầu PIN/UV nếu cần            |
 |                  |<--------------------------------------------------------|
 |                  | credentialId + clientDataJSON + attestationObject       |
 |                  | POST registration verify    |                           |
 |                  |---------------------------->|                           |
 |                  | verify challenge/origin/RP/flags, persist public key    |
 |                  |<----------------------------|                           |
 |  Đã thêm passkey |                             |                           |
```

Đây là **sơ đồ giao thức**. Trong phần JavaScript bên dưới, hai endpoint `/passkeys/registration/options` và `/passkeys/registration/verify` là **API minh họa do ứng dụng tự triển khai**, không phải cam kết endpoint mặc định của Spring Security.

### 4.1 Tạo creation options ở backend

Backend tạo challenge **mới từ CSPRNG** (chẳng hạn 32 random bytes), lưu pending challenge gắn tài khoản/session/flow `REGISTRATION` và thời hạn ngắn. Trả cho browser cấu hình tương đương JSON sau:

```json
{
  "challenge": "<fresh-base64url-challenge>",
  "rp": { "id": "localhost", "name": "Passkey Demo" },
  "user": {
    "id": "<stable-base64url-user-handle>",
    "name": "alice@example.test",
    "displayName": "Alice"
  },
  "pubKeyCredParams": [
    { "type": "public-key", "alg": -7 },
    { "type": "public-key", "alg": -257 }
  ],
  "authenticatorSelection": {
    "residentKey": "required",
    "userVerification": "required"
  },
  "attestation": "none",
  "timeout": 60000,
  "excludeCredentials": []
}
```

Các giá trị đặt trong `<...>` là **placeholder mô tả dạng dữ liệu**, không thể gửi trực tiếp cho browser làm challenge hợp lệ.

- `challenge`: Base64url string đại diện **bytes ngẫu nhiên**, khác mỗi attempt, không dùng timestamp hay username làm nguồn duy nhất.
- `rp.id`: RP ID được backend cấu hình; `rp.name` chỉ để hiển thị.
- `user.id`: opaque **byte identifier** ổn định, khác username/email; `name` và `displayName` là thông tin hiển thị.
- `pubKeyCredParams`: danh sách thuật toán COSE được backend hỗ trợ; `-7` thường là ES256, `-257` là RS256.
- `residentKey: "required"` tạo nhu cầu **discoverable credential** cho username-less passkey login. Nếu chỉ làm second factor, có thể cân nhắc `preferred` theo UX và policy.
- `userVerification: "required"` yêu cầu xác minh người dùng cục bộ; không tự động có nghĩa backend nhận sinh trắc.
- `attestation: "none"` phù hợp nhiều ứng dụng consumer không cần nhận diện model thiết bị. Attestation được quản lý riêng nếu tổ chức có policy hardware/enterprise.
- `excludeCredentials` gợi ý authenticator tránh tạo credential đã biết; backend vẫn phải kiểm tra uniqueness.
- `timeout` là gợi ý cho browser; server phải có TTL và one-time use riêng.

### 4.2 Authenticator tạo credential

Browser gọi `navigator.credentials.create` rồi nhận object `PublicKeyCredential`. Các thành phần chính:

- `credential.id` hoặc `rawId`: credential identifier.
- `response.clientDataJSON`: JSON có `type = "webauthn.create"`, `challenge`, `origin` và các thuộc tính tùy trường hợp.
- `response.attestationObject`: CBOR gồm authenticator data (trong đó có public key/credential ID khi đăng ký) và attestation statement.
- `response.getTransports()`: gợi ý cách thiết bị hỗ trợ giao tiếp, nếu API có sẵn.
- `getClientExtensionResults()`: kết quả extensions nếu dùng.

Browser không xuất private key cho JavaScript. Trình quản lý passkey quyết định credential được lưu ở đâu/có đồng bộ không.

### 4.3 Server xác minh registration trước khi persist

Một WebAuthn server verifier đáng tin cậy phải:

1. Tìm pending registration challenge và xác minh **đúng session + account + mục đích**, còn hạn, chưa dùng.
2. Phân tích `clientDataJSON`; kiểm tra `type="webauthn.create"`, challenge **khớp bytes gốc**, `origin` được cho phép, những quy tắc cross-origin/top-origin nếu có.
3. Phân tích CBOR attestation và authenticator data: kiểm tra `rpIdHash == SHA-256(rpId)`, cờ **UP**, **UV** khi policy yêu cầu, cấu trúc attested credential data và thuật toán khóa phù hợp.
4. Nếu policy yêu cầu attestation trust, kiểm tra chain/metadata/attestation statement theo tiêu chuẩn; khi dùng `attestation:"none"` **không** giả định thiết bị thuộc model đáng tin cụ thể.
5. Lấy credential ID và public key đã xác minh, **gắn với account đang authenticated ở server**, kiểm tra credential ID chưa thuộc account khác.
6. Đánh dấu challenge đã dùng atomically và persist trong transaction an toàn; chỉ trả thành công sau khi DB xác nhận, đồng thời audit event.

Server không được tin trường `user.id`/`accountId` do client đưa vào verify body để chọn tài khoản; tính toàn vẹn phải dựa trên session đã xác minh, challenge binding và dữ liệu credential.

## 5. Đăng nhập passkey: luồng authentication

Đăng nhập phải sử dụng **challenge mới** và **assertion signature** thay vì tin credential ID đơn thuần.

```text
Browser                   Spring Servlet RP                Authenticator
  |  POST login options          |                                |
  |----------------------------->|                                |
  |  challenge + rpId + UV policy|                                |
  |<-----------------------------|                                |
  | navigator.credentials.get({publicKey})                         |
  |--------------------------------------------------------------->|
  |                        Chọn passkey, user presence/verification |
  |<---------------------------------------------------------------|
  |  credentialId + authenticatorData + clientDataJSON + signature |
  | POST login verify            |                                |
  |----------------------------->|                                |
  | verify challenge/origin/rp/signature/account mapping          |
  | tạo Spring Authentication/session nếu hợp lệ                  |
  |<-----------------------------|                                |
  | GET /me + session cookie     |                                |
  |----------------------------->|                                |
```

### 5.1 Login có username và login không username

**Username-first:** frontend hỏi username/email; backend tìm credential IDs đã đăng ký cho account, trả `allowCredentials`. Sau assertion, backend phải kiểm tra credential thực sự thuộc account đã chọn.

**Username-less (discoverable):** backend trả options không cần `allowCredentials`; authenticator/browser có thể đưa ra passkey tương ứng RP ID. Backend tìm account theo **credential ID** sau verify và đối chiếu `userHandle` khi có. Không lấy account từ username user tự gửi ở verify request.

Ví dụ login request options:

```json
{
  "challenge": "<fresh-base64url-challenge>",
  "rpId": "localhost",
  "userVerification": "required",
  "timeout": 60000
}
```

Với username-first, backend có thể thêm:

```json
{
  "allowCredentials": [
    {
      "type": "public-key",
      "id": "<registered-credential-id-base64url>",
      "transports": ["internal", "hybrid"]
    }
  ]
}
```

Credential ID không phải secret đăng nhập, nhưng không nên phơi bày danh sách credential và trạng thái account không cần thiết; cân nhắc chống user enumeration/rate limiting.

### 5.2 Browser tạo assertion gồm những gì?

Response từ `navigator.credentials.get` gồm:

- `id`/`rawId`: định danh credential để backend tra public key.
- `response.clientDataJSON`: `type="webauthn.get"`, challenge, origin và ngữ cảnh.
- `response.authenticatorData`: `rpIdHash`, UP/UV, `signCount` và các flags.
- `response.signature`: chữ ký của authenticator trên **`authenticatorData || SHA-256(clientDataJSON)`**.
- `response.userHandle`: có thể null trong một số luồng; nếu có phải đối chiếu mapping.

**Credential ID đúng không đủ để đăng nhập**: nó có thể là thông tin công khai. Server phải xác minh signature bằng **public key đã đăng ký cho credential ID đó** và toàn bộ ràng buộc challenge/RP/origin/flags.

### 5.3 Server xác minh assertion

1. Tải pending login challenge, còn hạn, đúng flow/session/attempt, chưa được sử dụng.
2. Kiểm tra `clientDataJSON.type = "webauthn.get"`, challenge khớp bytes, origin trong allowlist; xử lý cross-origin theo policy.
3. Kiểm tra `rpIdHash` đúng SHA-256(RP ID) đã cấu hình.
4. Kiểm tra cờ **UP** và cờ **UV** nếu policy bắt buộc. Browser yêu cầu UV không bảo đảm authenticator đã làm nếu server không kiểm tra flag.
5. Tìm credential active theo credential ID, kiểm tra không bị thu hồi, đúng account, userHandle khớp nếu có.
6. Xác minh chữ ký với public key/thuật toán đã lưu và bytes xác thực chính xác.
7. Xử lý `signCount` cùng các cờ backup BE/BS theo chính sách rủi ro. Synced passkeys có thể báo counter 0 hoặc không tăng đơn điệu; đừng mặc định coi mọi counter 0 là clone.
8. Tiêu thụ challenge một lần, cập nhật last-used/counter và hoàn tất **Spring Security Authentication/SecurityContext/session** bằng handler/cơ chế framework phù hợp.

Một controller trả JSON `{"authenticated":true}` nhưng không tạo/lưu `SecurityContext` **chưa phải đăng nhập thật**. Session fixation protection, security context persistence và authorization rules phải hoạt động sau verify.

## 6. Tích hợp vào Spring Security Servlet

Các phiên bản Spring Security hiện đại có module hỗ trợ **WebAuthn/passkeys**, dùng DSL `HttpSecurity.webAuthn(...)`. **Xác minh version/module trước khi áp dụng**: một project dùng Spring Security cũ có thể chưa có method `webAuthn`; endpoints mặc định, repository interfaces và UI khác nhau theo release. Tránh tự phát minh tên endpoint “mặc định” khi chưa kiểm tra thư viện thực tế.

### 6.1 Cấu hình Spring Boot với WebAuthn DSL

Với BOM quản lý phiên bản Spring Security có module WebAuthn tương ứng, dependency Gradle có thể gồm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-webauthn'
}
```

**`src/main/java/com/example/passkey/SecurityConfig.java`**

```java
package com.example.passkey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .webAuthn(webAuthn -> webAuthn
                .rpId("localhost")
                .rpName("Passkey Demo")
                .allowedOrigins("http://localhost:8080")
            );

        return http.build();
    }
}
```

**`src/main/java/com/example/passkey/PasskeyDemoApplication.java`**

```java
package com.example.passkey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasskeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasskeyDemoApplication.class, args);
    }
}
```

**Giải thích và phạm vi chạy:** cấu hình dành cho release hỗ trợ WebAuthn DSL, **không** phải chương trình Java chuẩn chạy bằng `javac` thuần. Tạo dự án Spring Boot/Spring MVC từ Spring Initializr với Java 17+, cài đúng WebAuthn module tương thích, Gradle wrapper và cấu hình user/repository/UI tương ứng. Nếu Spring không tìm thấy `webAuthn` khi compile, cần kiểm tra **version/module** trước khi thay đổi nghiệp vụ. Chạy bằng `./gradlew bootRun` (Windows: `.\gradlew.bat bootRun`) sau khi đủ các thành phần framework/registration UI.

Ở ví dụ, `formLogin` có thể dùng làm **bootstrap login** để user đã chứng minh tài khoản được quyền đăng ký passkey; một ứng dụng production có thể chọn cơ chế bootstrap khác. `webAuthn` giúp Spring quản lý flow theo module, nhưng vẫn cần thiết kế **credential repository durable, account mapping, thu hồi, authorization, quản lý session và recovery**. Không suy ra chỉ thêm snippet là đã có schema production, trang quản lý passkey hoàn chỉnh hay endpoint tùy chỉnh.

**Development:** `rpId("localhost")` và `allowedOrigins("http://localhost:8080")` chỉ áp dụng khi browser gọi WebAuthn từ origin localhost này. **Production:** dùng RP ID và allowed origin của website HTTPS thật, tránh wildcard và nguồn không kiểm soát. Nếu HTML được phục vụ bởi frontend origin khác backend API, phải xác định đúng browser origin, cookie/CSRF/CORS và kiến trúc RP ID từ đầu.

**Security defaults:** giữ CSRF protection cho endpoints thay đổi trạng thái dựa trên session cookie. Không gọi `csrf.disable()` chỉ vì registration/login thử bị 403. Nếu module Spring Security định nghĩa endpoint và CSRF integration riêng, frontend phải tuân theo **contract thực tế** của release.

### 6.2 Khi tự triển khai endpoint với thư viện WebAuthn khác

Nếu không dùng WebAuthn DSL của Spring hoặc cần workflow đặc thù, hãy chọn một thư viện **WebAuthn server-side verifier được duy trì và kiểm thử**, tích hợp:

- `/passkeys/registration/options` — chỉ cho account đã xác minh/đủ quyền thêm credential.
- `/passkeys/registration/verify` — xác minh WebAuthn registration, lưu credential với transaction/unique constraint.
- `/passkeys/login/options` — tạo challenge, trả request options cho login.
- `/passkeys/login/verify` — xác minh assertion, tạo Spring `Authentication`, lưu `SecurityContext` và session an toàn.

Đây là **tên route tự thiết kế** cho bài học, không phải API Java của framework. Dùng `AuthenticationProvider`/filter hoặc authentication success handler và `SecurityContextRepository` thích hợp để login được duy trì đúng vòng đời. **Không tự viết parser CBOR/COSE và thuật toán verify signature từ đầu** cho production.

## 7. JavaScript: chuyển binary đúng trước khi gọi WebAuthn

WebAuthn sử dụng `ArrayBuffer`/`Uint8Array` cho challenge, user handle, credential ID và response. JSON truyền dữ liệu nhị phân qua **Base64url**. Không đưa chuỗi Base64url vào `new TextEncoder().encode(...)` để làm challenge: đó là bytes của **chuỗi đã mã hóa**, không phải challenge bytes gốc.

### 7.1 Hàm Base64url ↔ binary

```javascript
function decodeBase64url(input) {
  const base64 = input.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
  const raw = atob(padded);
  return Uint8Array.from(raw, ch => ch.charCodeAt(0));
}

function encodeBase64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);

  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function requireWebAuthn() {
  if (!window.PublicKeyCredential || !navigator.credentials) {
    throw new Error("WebAuthn is not available in this context");
  }
}
```

`decodeBase64url` nhận string Base64url hợp lệ, trả đúng bytes. `encodeBase64url` dùng với `ArrayBuffer` response. Browser mới có thể hỗ trợ `PublicKeyCredential.parseCreationOptionsFromJSON`, `parseRequestOptionsFromJSON` và `credential.toJSON()` để giảm mã chuyển đổi, nhưng nên kiểm tra độ hỗ trợ trên browser mục tiêu.

### 7.2 Hàm POST JSON với CSRF token

Hợp đồng minh họa giả định frontend cùng origin với Spring Servlet app, đã có CSRF token hợp lệ được server cung cấp qua HTML/endpoint. Tên header/token phải khớp repository/request handler ứng dụng.

```javascript
async function postJson(url, payload, csrfToken) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": csrfToken
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error("HTTP " + response.status + " at " + url);
  }
  return response.json();
}
```

Ví dụ trên không tự tạo `csrfToken`; token phải được server phát và browser gửi đúng theo chính sách Spring Security hiện hành. Đừng đặt một token giả/tĩnh hoặc tắt CSRF để bypass 403.

### 7.3 Client đăng ký passkey

```javascript
async function registerPasskey(csrfToken) {
  requireWebAuthn();

  // Custom application endpoints, not Spring default endpoints.
  const options = await postJson(
    "/passkeys/registration/options", {}, csrfToken
  );

  const publicKey = {
    ...options,
    challenge: decodeBase64url(options.challenge),
    user: {
      ...options.user,
      id: decodeBase64url(options.user.id)
    },
    excludeCredentials: (options.excludeCredentials ?? []).map(c => ({
      ...c,
      id: decodeBase64url(c.id)
    }))
  };

  const credential = await navigator.credentials.create({ publicKey });
  if (!credential || credential.type !== "public-key") {
    throw new Error("No credential created");
  }

  const response = credential.response;
  const payload = {
    id: credential.id,
    rawId: encodeBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: encodeBase64url(response.clientDataJSON),
      attestationObject: encodeBase64url(response.attestationObject),
      transports: typeof response.getTransports === "function"
        ? response.getTransports() : []
    },
    clientExtensionResults: credential.getClientExtensionResults()
  };

  return postJson(
    "/passkeys/registration/verify", payload, csrfToken
  );
}
```

**Điều kiện thành công:** server đã verify, lưu vào DB, liên kết đúng account và trả response thành công. User bấm xác nhận PIN/vân tay **chưa đủ** để báo “đăng ký xong” nếu backend chưa persist. Browser có thể ném `NotAllowedError` khi user hủy prompt hoặc timeout và `NotSupportedError` khi authenticator/policy không đáp ứng.

### 7.4 Client đăng nhập bằng passkey

```javascript
async function loginWithPasskey(csrfToken) {
  requireWebAuthn();

  const options = await postJson(
    "/passkeys/login/options", {}, csrfToken
  );

  const publicKey = {
    ...options,
    challenge: decodeBase64url(options.challenge),
    allowCredentials: options.allowCredentials?.map(c => ({
      ...c,
      id: decodeBase64url(c.id)
    }))
  };

  const credential = await navigator.credentials.get({ publicKey });
  if (!credential || credential.type !== "public-key") {
    throw new Error("No assertion received");
  }

  const response = credential.response;
  const payload = {
    id: credential.id,
    rawId: encodeBase64url(credential.rawId),
    type: credential.type,
    response: {
      authenticatorData: encodeBase64url(response.authenticatorData),
      clientDataJSON: encodeBase64url(response.clientDataJSON),
      signature: encodeBase64url(response.signature),
      userHandle: response.userHandle
        ? encodeBase64url(response.userHandle) : null
    },
    clientExtensionResults: credential.getClientExtensionResults()
  };

  return postJson("/passkeys/login/verify", payload, csrfToken);
}
```

Nếu `options.allowCredentials` không có, browser có thể chọn một **discoverable credential** đúng RP ID; nếu có, nó thường chọn trong tập credential đã chỉ định. Backend phải thực thi xác minh signature/account mapping, sau đó tạo `Authentication` và session. Code JS này là **client-only sketch**, backend endpoints cần được triển khai theo contract; nó không thể hoạt động độc lập chỉ bằng Spring MVC static files.

## 8. Ví dụ Java 17 chạy độc lập: phát challenge ngẫu nhiên

Chỉ phần tạo challenge sau đây là **Java SE**, biên dịch bằng JDK 17 không cần Spring. Nó chứng minh cách dùng **SecureRandom** và Base64url, chưa phải WebAuthn verifier.

**`WebAuthnChallengeDemo.java`**

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class WebAuthnChallengeDemo {

    public static void main(String[] args) {
        byte[] challenge = new byte[32];
        new SecureRandom().nextBytes(challenge);

        String base64url = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(challenge);

        System.out.println("bytes=" + challenge.length);
        System.out.println("base64urlLength=" + base64url.length());
        System.out.println("containsPadding=" + base64url.contains("="));
    }
}
```

Biên dịch và chạy:

```bash
javac WebAuthnChallengeDemo.java
java WebAuthnChallengeDemo
```

Stdout **chính xác** (không in giá trị challenge ngẫu nhiên):

```text
bytes=32
base64urlLength=43
containsPadding=false
```

32 bytes = 256 bit, chuyển thành 43 ký tự Base64url không padding. Giá trị challenge **phải khác giữa các attempt**, được lưu kèm TTL/flow/binding và sử dụng một lần. Không dùng username, timestamp hoặc UUID có dự đoán làm challenge duy nhất.

## 9. Pseudocode backend và nơi cần dùng thư viện WebAuthn

Đây là **pseudocode**, không phải Java API thực tế. Các method `verifier.verify...` chỉ tượng trưng cho thư viện WebAuthn verifier đã được kiểm thử; không copy thẳng thành production code.

```text
createRegistrationOptions(authenticatedUser, session):
    requireUserCanAddPasskey(authenticatedUser)
    challenge = secureRandomBytes(32)
    savePending(
        kind=REGISTRATION, account=authenticatedUser.id,
        session=session.id, expiresInMinutes=3, oneTime=true
    )
    return creationOptions(challenge, rpId, stableUserHandle, policy)

finishRegistration(authenticatedUser, response, session):
    pending = atomicallyConsumePending(REGISTRATION, session)
    requirePendingMatchesAccountAndNotExpired(pending, authenticatedUser)
    result = verifier.verifyRegistration(
        response, expectedChallenge=pending.challenge,
        expectedOrigins=trustedOrigins, expectedRpId=rpId,
        userVerificationPolicy=policy
    )
    requireCredentialIdUnique(result.credentialId)
    savePublicKeyCredentialInTransaction(
        account=authenticatedUser.id, credential=result
    )
    audit("passkey-added")

createLoginOptions(session, optionalAccount):
    challenge = secureRandomBytes(32)
    savePending(LOGIN, session=session.id, expiresInMinutes=3)
    return requestOptions(challenge, rpId, accountCredentialsIfAny)

finishLogin(response, session):
    pending = atomicallyConsumePending(LOGIN, session)
    requireNotExpired(pending)
    stored = findActiveCredential(response.rawId)
    requireExists(stored)
    verified = verifier.verifyAssertion(
        response, stored.publicKey, stored.algorithm,
        expectedChallenge=pending.challenge,
        expectedOrigins=trustedOrigins, expectedRpId=rpId,
        requireUserVerification=true
    )
    requireVerified(verified)
    requireUserHandleMatchesAccountIfPresent(verified, stored)
    updateCounterBackupFlagsAndLastUsedSafely()
    completeSpringAuthenticationAndSession(stored.account)
    audit("passkey-login")
```

Atomicity của việc consume challenge và lưu dữ liệu phải được thiết kế nhất quán theo transaction/cache. Thử hai request cạnh tranh với cùng challenge: **chỉ một lần** được thành công. Không dựa vào việc frontend vô hiệu hóa nút submit để chống replay.

### 9.1 Bảng kiểm tra bắt buộc ở server

| Điều kiện | Registration | Authentication |
| --- | --- | --- |
| Pending challenge đúng flow, TTL, one-time | Có | Có |
| `clientDataJSON.type` | `webauthn.create` | `webauthn.get` |
| `clientDataJSON.challenge`, origin | So khớp | So khớp |
| `rpIdHash` từ authenticator data | So khớp RP ID | So khớp RP ID |
| UP/UV theo policy | Kiểm tra | Kiểm tra |
| Attestation/credential public key | Phân tích và kiểm tra trước khi lưu | Dùng public key đã lưu |
| Signature của assertion | Không phải luồng assertion | **Bắt buộc verify** |
| Credential ID/account | Unique, gắn current account | Tra mapping đáng tin, active/not revoked |
| User handle | Gắn user entity | So khớp nếu có |
| Sign counter/backup flags | Lưu ban đầu | Đánh giá và cập nhật |
| Spring Security session | Giữ phiên đủ quyền khi đăng ký | Thiết lập sau login đã xác minh |

**Không tự xác thực bằng cách đọc Base64 clientDataJSON rồi chỉ so challenge:** cần xác minh toàn bộ origin/RP hash/flags và chữ ký đúng bytes/thuật toán. Một thư viện chuẩn giúp tránh sai sót parse CBOR/COSE, signature DER/raw encoding và kiểm tra trạng thái.

## 10. Những lựa chọn thiết kế và rủi ro thực tế

### 10.1 Passkey đơn lẻ hay MFA?

**Passwordless:** user đăng nhập chỉ bằng passkey, nên đặt `userVerification:"required"` phù hợp mô hình xác thực và kiểm tra UV flag tại backend. Một số authenticators/platform browsers có hạn chế UX; cung cấp fallback đủ mạnh.

**MFA/step-up:** một passkey có thể dùng như một yếu tố trong quy trình có nhiều bước. Không tự suy ra cứ thêm WebAuthn là đạt mọi chính sách MFA; phải hiểu authenticator có UV, cách liên kết phiên và những factors/assurance mà tổ chức yêu cầu.

### 10.2 Đồng bộ passkey và sign counter

Một số passkey đồng bộ trên nhiều thiết bị; counter có thể bằng 0 hoặc không tăng như khóa phần cứng truyền thống. `signCount` và cờ BE/BS nên dùng như **tín hiệu rủi ro theo đặc tính authenticator**, không là điều kiện cứng không phù hợp làm hỏng passkey hợp lệ. Đừng bỏ hoàn toàn giám sát nếu production có policy chống clone.

### 10.3 Attestation

`attestation:"none"` phổ biến cho consumer UX và quyền riêng tư. Một ứng dụng doanh nghiệp yêu cầu chỉ thiết bị được quản lý có thể dùng attestation trust validation/phần cứng đã phê duyệt; đó là **chính sách bổ sung có chứng cứ**, không tự động có khi được cấp public key. Không tin AAGUID hay model string do client gửi nếu chưa có cách xác minh thích hợp.

### 10.4 Account recovery và thu hồi

- Cho user đăng ký nhiều passkeys để tránh một điểm lỗi duy nhất.
- Cung cấp UI xem, đặt tên và **thu hồi** passkey, yêu cầu authenticated/step-up session và CSRF token.
- Nếu mất mọi thiết bị, recovery phải đủ mạnh, có cooldown/audit/anti-abuse theo rủi ro. Recovery yếu có thể triệt tiêu lợi ích chống phishing.
- Tài khoản bị khóa/xóa phải vô hiệu hóa credential liên quan; cập nhật mapping/backup policy.
- Login WebAuthn không chứng minh mọi request sau đó; giữ session timeout, logout, session fixation protection và authorization ở backend.

### 10.5 CSRF, XSS và phiên web

Trong Servlet app xác thực bằng cookie session, browser có thể tự gửi cookie. **Đăng ký một credential mới** là hành động rất nhạy cảm và cần chống CSRF; nếu attacker ép victim đăng ký passkey của attacker, có nguy cơ account takeover. Đăng nhập cũng cần chống **login CSRF** và gắn đúng challenge/session. Không tắt `csrf()` chỉ vì passkey flow dùng public-key cryptography.

WebAuthn giảm phishing tại domain giả nhờ RP ID/origin binding nhưng **không tự sửa XSS trong origin thật**, lỗi authorization, session theft hoặc recovery yếu. Dùng HTTPS, CSP/escaping, cookie `Secure`/`HttpOnly`/`SameSite`, CSRF và server-side authorization đầy đủ.

## 11. Lỗi thường gặp và nguyên nhân thật

| Dấu hiệu | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| `navigator.credentials` không có | Insecure context, browser/platform không hỗ trợ. | Dùng HTTPS hoặc localhost dev đáng tin; kiểm tra support. |
| `SecurityError` khi tạo/lấy credential | RP ID sai domain, origin không được phép, context iframe/policy hạn chế. | Kiểm tra RP ID và allowed origins chính xác, chính sách iframe nếu dùng. |
| `NotAllowedError` trong prompt | User hủy, timeout, UV không đạt hoặc authenticator không có. | UX fallback, không coi là thành công; kiểm tra options và capabilities. |
| Backend báo challenge mismatch | Dùng challenge cũ/khác flow, Base64url bị encode sai. | Decode thành bytes trước WebAuthn; store challenge một lần, so khớp bản gốc. |
| Registration thành công ở browser nhưng không lưu | Server attestation/origin/RP/UV check sai, DB unique hoặc transaction lỗi. | Debug verifier có kiểm soát, không bỏ security checks. |
| `InvalidStateError` registration | Credential đã tồn tại / excludeCredentials. | Hiển thị quản lý passkeys, xử lý duplicate đúng. |
| Assertion không tìm thấy credential | Không persist, storage reset, RP ID khác hoặc mapping sai. | Kiểm tra credentialId/DB và RP ID nhất quán. |
| Assertion signature invalid | Sai public key/alg, bytes bị thay đổi, response giả mạo. | Dùng thư viện verifier chuẩn, không viết crypto riêng. |
| Login verify OK nhưng tiếp tục 302/401 | Chưa tạo/lưu `Authentication` trong `SecurityContext`, session cookie không hợp lệ. | Tích hợp authentication success/session persistence, kiểm tra cookies. |
| POST registration bị 403 | CSRF token thiếu/sai hoặc user không đủ quyền. | Tách lỗi CSRF với WebAuthn, không disable CSRF. |
| Passkey ở thiết bị đồng bộ lỗi khi counter không tăng | Backend giả định mọi authenticator counter tăng. | Xử lý counter/BE/BS theo policy phù hợp. |
| Đổi host/domain rồi passkey “mất” | Credential ràng buộc RP ID trước đó. | Có kế hoạch domain/RP/migration/recovery. |
| User được xác thực nhưng xem nhầm tài khoản | Backend tin username từ client thay vì credential/userHandle mapping. | Lookup credential đã verify, match account và authorization. |

## 12. Kịch bản kiểm thử end-to-end

**Luồng thành công:**

1. Đăng nhập bootstrap bằng phương thức đủ tin cậy, gọi registration options; mỗi lần nhận challenge mới.
2. Browser gọi `navigator.credentials.create`, user xác minh cục bộ. Backend xác minh và lưu credential/public key vào account hiện tại.
3. Logout, bắt đầu login options với challenge khác. Browser gọi `navigator.credentials.get` và nhận assertion.
4. Server xác minh challenge/origin/RP/UP/UV/signature, tạo Spring session. Gọi endpoint được bảo vệ `/me` thấy đúng account.
5. Đăng ký passkey thứ hai, thu hồi passkey thứ nhất và kiểm tra credential đã revoked không thể đăng nhập nữa.

**Luồng cần từ chối:**

- Gửi lại assertion cũ cùng challenge đã dùng; phải bị từ chối (anti-replay).
- Dùng response của registration để verify login hoặc challenge attempt khác; phải bị từ chối.
- Thay origin/RP ID hoặc sửa bytes signature/clientData/authenticatorData; phải bị từ chối.
- Không đạt UV khi policy yêu cầu; phải bị từ chối.
- Credential ID hợp lệ nhưng gắn account khác; không được cấp phiên sai.
- Chưa authenticated mà gọi registration cho user khác; phải bị từ chối.
- Gửi hai verify cùng credential/challenge cạnh tranh; chỉ một transaction hợp lệ.
- User không còn đủ quyền tài nguyên sau login; backend vẫn phải trả 403 cho endpoint ngoài quyền.

**Cách quan sát:** DevTools → Network xác minh options có challenge, RP ID, userVerification và JSON/Base64url fields đúng; sau login kiểm tra `Set-Cookie`/session và request `/me`. Khi debug, che credential IDs, cookies, account identifiers và response nhạy cảm trước khi chia sẻ logs/HAR. `curl` có thể kiểm tra HTTP contract, nhưng **không tự tạo assertion WebAuthn hợp lệ** nếu không có authenticator/private key tương ứng.

## 13. Checklist triển khai

- RP ID cố định, đúng domain; allowed origins là allowlist chính xác, production HTTPS.
- Registration chỉ cho account đã xác minh; có CSRF, quyền thêm credential và step-up nếu cần.
- Challenge từ `SecureRandom`/CSPRNG, TTL, one-time, flow/session/account binding.
- Frontend chuyển Base64url ↔ bytes đúng, xử lý hủy prompt/fallback.
- Backend dùng thư viện WebAuthn verifier đã kiểm thử: type, challenge, origin, RP hash, UP/UV, public key, COSE algorithm và signature.
- Credential repository durable có unique ID/account mapping, trạng thái thu hồi, counter/backup flags và audit.
- Authentication tạo `SecurityContext`/session an toàn; vẫn áp dụng authorization ở service/controller.
- Có recovery, nhiều passkeys, thiết kế session/logout và chính sách thiết bị/sync/attestation theo nhu cầu.
- Kiểm tra đúng WebAuthn DSL/module/endpoint của **Spring Security release đang chạy**; không coi ví dụ API tự thiết kế là endpoint framework có sẵn.

**Ghi nhớ:** **Registration** tạo credential ở authenticator rồi lưu **public key, credential ID và mapping tài khoản** sau khi server xác minh. **Authentication** dùng private key ký một **challenge mới**, backend kiểm tra signature cùng challenge/origin/RP/UP/UV và tạo phiên Spring Security. Sức mạnh của passkey đến từ **ràng buộc RP ID, xác minh server-side chính xác, chống replay và vòng đời credential an toàn**, chứ không chỉ từ nút “Đăng nhập bằng passkey”.

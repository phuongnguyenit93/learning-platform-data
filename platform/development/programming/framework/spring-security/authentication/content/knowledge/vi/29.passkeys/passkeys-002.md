# Passkey: Authenticator, Relying Party và credential khóa công khai

## 1. Mục tiêu và bức tranh tổng thể

**Passkey** là một loại **discoverable WebAuthn public-key credential** dùng để đăng nhập mà không cần gửi mật khẩu bí mật chung cho ứng dụng. Mỗi credential gắn với một **Relying Party (RP)** cụ thể, dựa trên cặp khóa mật mã: **private key** được authenticator/provider quản lý và **public key** được RP lưu để xác minh chữ ký khi người dùng đăng nhập.

Ba khái niệm chính trong đề bài:

- **Authenticator:** thành phần tạo và quản lý credential, thực hiện xác nhận tương tác người dùng và ký thử thách bằng private key. Có thể tích hợp trên điện thoại/máy tính hoặc là khóa bảo mật rời.
- **Relying Party:** ứng dụng/dịch vụ tin vào kết quả xác minh WebAuthn. RP tạo challenge, khai báo RP ID và origin được phép, lưu public key cùng credential ID, xác minh assertion và cấp phiên đăng nhập.
- **Public-key credential:** bản ghi định danh một cặp khóa và metadata liên quan. **Credential private key không được gửi đến RP**; RP lưu public key cùng mã credential để dùng khi xác minh.

Sau bài này, bạn có thể:

1. Phân biệt **RP**, **browser/WebAuthn client**, **authenticator** và **người dùng** trong cùng một sơ đồ.
2. Giải thích cách đăng ký credential bằng `navigator.credentials.create()` và đăng nhập bằng `navigator.credentials.get()`.
3. Phân biệt **credential ID**, **user handle**, **public key**, **private key**, **RP ID**, **origin**, **challenge**, **UP/UV**, **attestation** và **assertion**.
4. Biết các dữ liệu RP phải lưu và các điều kiện **phải kiểm tra phía server**.
5. Hiểu cách bật passkey/WebAuthn trong Spring Security 6.5 cho ứng dụng Java 17+ và các giới hạn khi đưa vào production.

**Phạm vi:** bài tập trung vào mô hình WebAuthn/FIDO2 trong **ứng dụng web Spring Security Servlet**. Passkey là cơ chế chứng minh danh tính; nó **không tự thay thế authorization**, không tự cấp OAuth access token và không tự xử lý mọi luồng khôi phục tài khoản.

## 2. Bốn thực thể trong một lần dùng passkey

~~~text
                  Người dùng
             (chọn tài khoản,
              PIN/biometric)
                     │
                     ▼
      ┌─────────────────────────────┐
      │ Authenticator               │
      │ - tạo cặp khóa              │
      │ - giữ/quản lý private key   │
      │ - xác nhận UP/UV            │
      │ - ký WebAuthn assertion     │
      └──────────────▲──────────────┘
                     │  giao tiếp qua
                     │  nền tảng/CTAP
                     ▼
      ┌─────────────────────────────┐
      │ Browser / WebAuthn Client   │
      │ navigator.credentials       │
      │ - kiểm ngữ cảnh web         │
      │ - điều phối create/get      │
      │ - cung cấp clientDataJSON   │
      └──────────────▲──────────────┘
                     │ HTTPS
                     ▼
      ┌─────────────────────────────┐
      │ Relying Party (RP)          │
      │ Spring Security / Backend   │
      │ - phát challenge            │
      │ - kiểm origin và RP ID      │
      │ - lưu credential ID +       │
      │   public key + account      │
      │ - kiểm chữ ký assertion     │
      │ - tạo session, cấp quyền    │
      └─────────────────────────────┘
~~~

**RP** không phải browser và không phải authenticator. Browser chỉ là phần mềm trung gian giữa RP web và authenticator. Browser/WebAuthn client biết origin của trang gọi API, trình bày UI chọn passkey và chuyển dữ liệu qua giao diện phù hợp. Authenticator thực hiện thao tác dùng khóa; RP xác minh kết quả ở máy chủ.

### 2.1. Bảng trách nhiệm

| Thành phần | Có gì? | Làm gì? | Không nên làm gì? |
| --- | --- | --- | --- |
| Người dùng | Thiết bị, passkey provider, PIN/biometric khi áp dụng | Chọn tài khoản/credential và cho phép thao tác | Gửi mã PIN hoặc dữ liệu sinh trắc học cho website |
| WebAuthn client (browser) | Origin, API `navigator.credentials` | Gọi authenticator, tạo client data, kiểm ngữ cảnh | Tự khẳng định user đã xác thực thay server |
| Authenticator | Private key hoặc quyền truy cập khóa qua credential provider | Tạo khóa, ký, báo cờ UP/UV | Gửi private key cho RP |
| Relying Party (server) | Challenge, RP policy, credential ID, public key và account mapping | Xác minh chữ ký và các ràng buộc; tạo local session | Tin `credential.id` hoặc username do client tự gửi khi chưa verify |

**Authenticator** có thể là platform authenticator (Windows Hello, thiết bị Android/iOS, hệ sinh thái passkey provider) hoặc roaming authenticator (khóa bảo mật USB/NFC/Bluetooth). **CTAP** là giao thức giữa client và roaming authenticator; **WebAuthn** là API/giao thức phía web giữa RP, browser và authenticator.

## 3. Credential khóa công khai là gì?

Khi tạo một WebAuthn credential, authenticator tạo hoặc quản lý vật liệu khóa mật mã phù hợp với thuật toán RP và authenticator hỗ trợ. Trong mô hình ký số thông dụng:

- **Credential private key:** chỉ được dùng để ký và được bảo vệ bởi authenticator/provider. RP không có private key.
- **Credential public key:** được xuất ra trong đáp ứng đăng ký và lưu tại server RP.
- **Credential ID:** định danh byte sequence do authenticator cung cấp, giúp RP tìm đúng credential record khi đăng nhập; thường được serialize dưới Base64URL.
- **User handle:** chuỗi byte opaque do RP sinh, ổn định cho một tài khoản; dùng liên kết tài khoản trong các luồng discoverable credential. Không mặc định là email hay username.
- **RP ID:** tên miền để ràng buộc credential, ví dụ `login.example.com` hoặc `example.com` theo policy.
- **Metadata:** thuật toán COSE, thời điểm tạo/lần sử dụng, display label, transports, AAGUID hoặc trạng thái backup/counter khi cần.

Bản ghi RP thường có dạng **mô hình dữ liệu**:

~~~text
account_id                42
user_handle               <opaque bytes, unique, stable>
credential_id             <opaque bytes, unique for RP>
credential_public_key     <COSE public key bytes>
public_key_algorithm      -7  (ES256, ví dụ)
signature_counter         7
backup_eligible           true/false (khi có thông tin)
backup_state              true/false (khi có thông tin)
label                     "Laptop cá nhân"
created_at                ...
last_used_at              ...
status                    active / revoked
~~~

Các trường trên mang tính minh họa thiết kế, **không phải một schema mặc định bắt buộc** của Spring Security. Tùy thư viện WebAuthn bạn còn cần một số định dạng/thuộc tính khác. Với passkey đồng bộ, việc phản ánh `signCount` hoặc backup state cần xử lý theo quy tắc của authenticator; không giả định mọi thiết bị dùng counter tăng đơn điệu.

**Không lưu private key trong database RP.** Nếu public key/credential ID của RP bị lộ thì attacker không tự ký được assertion hợp lệ vì thiếu private key, nhưng vẫn phải bảo vệ dữ liệu account mapping, credential management và session để tránh chiếm đoạt tài khoản.

### 3.1. Credential có phải password được băm không?

Không. Password authentication thường yêu cầu client gửi một bí mật để server kiểm tra. Với WebAuthn, server tạo một **thử thách mới**, authenticator ký dữ liệu gắn với RP ID/challenge/origin và server kiểm bằng **public key** đã đăng ký. Không có “password hash” tương ứng phải truyền cho RP trong mỗi lần đăng nhập.

### 3.2. Credential ID có phải bí mật?

Không nên coi credential ID là password hay bearer token. ID chỉ giúp chọn bản ghi public key; biết ID không đủ giả chữ ký. Tuy vậy, ID và user handle vẫn có thể có tính nhận diện và ảnh hưởng riêng tư; không log/đưa công khai không cần thiết.

## 4. Passkey, WebAuthn credential và discoverable credential

**WebAuthn public-key credential** là khái niệm chung. **Passkey** trong cách dùng hiện nay là credential **discoverable** có thể được authenticator tìm theo RP ID khi người dùng không nhập username trước.

Có hai trường hợp:

- **Username-first:** người dùng nhập tên tài khoản. RP tìm credential records của tài khoản và đưa danh sách `allowCredentials` cho browser.
- **Username-less/discoverable:** browser gọi `navigator.credentials.get()` với danh sách `allowCredentials` rỗng/không có theo quy trình phù hợp. Authenticator/provider tìm credential cho RP ID và người dùng chọn tài khoản; RP dựa vào credential ID và `userHandle` đã xác minh để tìm đúng account.

Không nhầm `userHandle` với `user.name` hay `user.displayName` trong registration options. `user.id` (user handle) phải ổn định cho account. Username/email có thể thay đổi và có thể trùng giữa tenant; server cần mapping bất biến phù hợp.

### 4.1. Device-bound và synced passkeys

| Loại | Đặc điểm | Điểm cần quản lý |
| --- | --- | --- |
| Device-bound | Private key gắn vào một authenticator/thiết bị và thông thường không đồng bộ | Mất thiết bị → cần credential khác hoặc recovery |
| Synced passkey | Provider có thể sao lưu/đồng bộ vật liệu khóa theo cơ chế bảo vệ riêng sang thiết bị của cùng người dùng | Bảo mật tài khoản provider, recovery và sync fabric |
| Roaming security key | Khóa phần cứng có thể dùng trên nhiều máy qua USB/NFC | Quản lý khóa mất/thay thế, attestation nếu doanh nghiệp yêu cầu |
| Platform authenticator | Tích hợp vào máy hoặc điện thoại, dùng PIN/biometric cục bộ | Chính sách khóa màn hình, backup và quản trị thiết bị |

Nói “private key không bao giờ rời bất kỳ thiết bị nào” **không chính xác cho tất cả synced passkeys**. Điều chính xác là **RP không nhận private key và không có khả năng ký thay authenticator** trong mô hình chuẩn; passkey provider có thể đồng bộ khóa qua cơ chế được bảo vệ.

## 5. RP ID và origin: khóa chống phishing của WebAuthn

Hai khái niệm quan trọng nhưng khác nhau:

- **RP ID:** tên miền không có scheme và port, ví dụ `example.com`.
- **Origin:** bộ ba scheme + host + port của trang đang chạy WebAuthn, ví dụ `https://login.example.com:443` (biểu diễn URL thực tế có thể chuẩn hóa port).

Ví dụ:

~~~text
Origin ứng dụng: https://login.example.com
RP ID:           example.com

Origin ứng dụng: https://login.example.com
RP ID:           login.example.com

Origin ứng dụng: https://evil.example.net
RP ID yêu cầu:   example.com        → không được chấp nhận theo quy tắc thường
~~~

Quy tắc WebAuthn: RP ID phải tương ứng với effective domain của origin hoặc một registrable domain suffix hợp lệ, trừ các cơ chế mở rộng được đặc tả riêng. Không thể chọn bừa RP ID của domain khác; không dùng public suffix như `com`.

**Rủi ro khi đặt RP ID quá rộng:** dùng `example.com` cho nhiều subdomain có thể cho phép nhiều origin trong cùng phạm vi yêu cầu credential, nên tất cả origin thuộc phạm vi chính sách phải được kiểm soát. Ưu tiên RP ID hẹp và ổn định, chỉ mở rộng khi ứng dụng thực sự cần chia sẻ credential giữa các subdomain đáng tin.

### 5.1. Origin phải được kiểm phía server

Trình duyệt đặt `origin` vào `clientDataJSON`. RP cần xác minh giá trị này thuộc danh sách origin được phép, **không** tin origin do frontend tự khai trong JSON tùy ý. Nếu ứng dụng có proxy/layer đa domain, cấu hình danh sách origin **cố định** và đúng chính xác với scheme/host/port public.

WebAuthn chạy trong **secure context**. Triển khai production phải dùng HTTPS. Với dev, `http://localhost:8080` là ngoại lệ origin được coi là đáng tin theo mô hình WebAuthn; tránh suy rộng cho mọi địa chỉ HTTP/IP nội bộ. Do đó, cấu hình `rpId("localhost")` kết hợp `allowedOrigins("http://localhost:8080")` chỉ dành cho **demo local**.

### 5.2. Vì sao phishing resistance không tuyệt đối?

Một website giả mạo tại `evil.example.net` không thể sử dụng passkey có RP ID `example.com` trong WebAuthn thông thường. Server cũng kiểm `origin`/`rpIdHash` để chống lỗi cấu hình hoặc client bất thường. Tuy nhiên passkey **không chống được mọi tấn công**: XSS vào origin thật, chiếm session hiện có, quy trình recovery yếu, kẻ xấu được phép đăng ký passkey mới hoặc phân quyền sai vẫn nguy hiểm.

## 6. Registration ceremony: tạo credential lần đầu

Registration thường diễn ra **sau khi đã biết user/account** và phải có quyền đăng ký passkey cho chính account đó (đã đăng nhập, xác thực lại gần đây hoặc qua onboarding đáng tin).

~~~text
User                Browser                    RP server                Authenticator
 |                     |                           |                          |
 | chọn "Add passkey" |                           |                          |
 |-------------------->| POST registration options |                          |
 |                     |-------------------------->|                          |
 |                     |  challenge + rp + user    |                          |
 |                     |<--------------------------|                          |
 |                     | navigator.credentials.create({publicKey: options})   |
 |                     |----------------------------------------------------->|
 |                     |                tạo cặp khóa, xác nhận UP/UV          |
 |                     |<-----------------------------------------------------|
 |                     |  credential + attestation response                   |
 |                     | POST credential JSON    |                          |
 |                     |-------------------------->|                          |
 |                     |   kiểm challenge, origin, rpIdHash, flags,           |
 |                     |   attestation policy, account binding                |
 |                     |   lưu credential ID + public key + userHandle        |
 |                     |<--------------------------|  success                 |
~~~

### 6.1. Tạo options phía RP

Server tạo `PublicKeyCredentialCreationOptions` có thể gồm:

~~~json
{
  "rp": {
    "id": "login.example.com",
    "name": "Learning Portal"
  },
  "user": {
    "id": "b3BhcXVlLXVzZXItNDI",
    "name": "learner@example.com",
    "displayName": "Learner"
  },
  "challenge": "c2VydmVyLWdlbmVyYXRlZC1yYW5kb20tYnl0ZXM",
  "pubKeyCredParams": [
    {"type": "public-key", "alg": -7},
    {"type": "public-key", "alg": -8}
  ],
  "timeout": 60000,
  "excludeCredentials": [],
  "authenticatorSelection": {
    "residentKey": "required",
    "userVerification": "required"
  },
  "attestation": "none"
}
~~~

Đây là **JSON minh họa cấu trúc**, chuỗi challenge và user ID không phải secrets/test vectors để dùng lại. Trong thực tế:

- Challenge phải được tạo bằng CSPRNG, đủ entropy (nên ≥16 byte, thường dùng 32 byte), có TTL ngắn, gắn đúng ceremony và **một lần dùng**.
- `user.id` là user handle opaque đã được RP tạo và liên kết với tài khoản; không để client tự chọn ID account tùy ý.
- `pubKeyCredParams` biểu thị các thuật toán mà RP sẵn sàng chấp nhận, chẳng hạn COSE `-7` (ES256) hoặc `-8` (EdDSA) khi thư viện/hệ sinh thái hỗ trợ.
- `residentKey="required"` yêu cầu credential discoverable phù hợp với trải nghiệm passkey.
- `userVerification="required"` yêu cầu xác minh user tại authenticator; chỉ nên chọn theo chính sách UX/bảo mật và kiểm UP/UV ở phản hồi.
- `attestation="none"` thích hợp cho nhiều sản phẩm consumer; doanh nghiệp có thể cần attestation bổ sung theo policy thiết bị/khóa.

Server không được lưu challenge vô hạn hoặc dùng cùng một challenge cho mọi tài khoản. Với session-based web, phải bảo vệ endpoint cấp options và đăng ký bằng CSRF token, và ngăn registration dựa trên một session bị cướp.

### 6.2. Browser gọi authenticator

Đoạn JavaScript sau chỉ minh họa browser API; ứng dụng phải lấy options từ server, chuyển các trường binary Base64URL thành `ArrayBuffer` đúng chuẩn rồi gửi response đã encode lên backend:

~~~javascript
// Đoạn minh họa (chưa bao gồm fetch/CSRF/JSON encoding).
const credential = await navigator.credentials.create({
  publicKey: creationOptionsWithArrayBuffers
});

// credential.response là AuthenticatorAttestationResponse.
// Gửi các trường cần thiết về server qua HTTPS để xác minh.
~~~

Các trường binary cần xử lý đúng gồm `challenge`, `user.id`, `excludeCredentials[].id`. Browser WebAuthn API không nhận mọi Base64URL string y nguyên làm binary. Kết quả chứa `rawId`, `response.clientDataJSON` và `response.attestationObject` phải serialize/encode phù hợp contract của thư viện server.

### 6.3. Authenticator trả gì lúc đăng ký?

Registration response gồm thông tin để RP thu được:

- **Credential ID** và **credential public key**.
- **Authenticator data** với `rpIdHash`, flags, signCount và (trong registration) attested credential data.
- **Client data** chứa `type="webauthn.create"`, challenge, origin và các trường theo bối cảnh.
- **Attestation statement** nếu được yêu cầu/hỗ trợ; có thể là none/self/basic/enterprise theo chính sách và triển khai.
- **User presence / user verification** flags mà RP phải kiểm theo yêu cầu.

Server phải dùng một **thư viện WebAuthn đúng chuẩn** xác minh toàn bộ ràng buộc, không tự parse vài trường và kết luận registration thành công.

### 6.4. Lưu bản ghi đúng account

RP **chỉ lưu credential sau khi mọi kiểm tra thành công**, gắn vào user mà ceremony đăng ký đã được ủy quyền. Không lấy username/account ID từ payload chưa xác thực rồi cho credential của attacker gắn vào tài khoản nạn nhân.

Nên lưu nhiều credential cho một account để hỗ trợ nhiều thiết bị và có cơ chế recovery được kiểm soát. `excludeCredentials` giúp tránh đăng ký lại cùng credential trên authenticator; server vẫn cần unique constraint theo credential ID.

## 7. Authentication ceremony: dùng private key để chứng minh danh tính

Sau khi đăng ký, user đăng nhập bằng một **challenge mới**:

~~~text
Browser                  RP server                     Authenticator
   |                         |                                |
   | POST authentication     |                                |
   | options                 |                                |
   |------------------------>|                                |
   | challenge, rpId,        |                                |
   | allowCredentials / UV   |                                |
   |<------------------------|                                |
   | navigator.credentials.get({publicKey: options})         |
   |-------------------------------------------------------->|
   |                      chọn credential, xác nhận UP/UV     |
   |<--------------------------------------------------------|
   | assertion: credential ID, authenticatorData,             |
   |            clientDataJSON, signature, userHandle        |
   |------------------------>|                                |
   |                         | tìm public key theo ID          |
   |                         | kiểm challenge/origin/rp ID     |
   |                         | kiểm UP/UV + signature/counter  |
   |                         | gắn account, tạo local session  |
   |<------------------------| success                         |
~~~

### 7.1. Authentication options

Ví dụ:

~~~json
{
  "challenge": "bmV3LWNzcHJuZy1jaGFsbGVuZ2U",
  "timeout": 60000,
  "rpId": "login.example.com",
  "allowCredentials": [],
  "userVerification": "required"
}
~~~

Đây là **minh họa** (không dùng giá trị challenge này ngoài tài liệu). Nếu `allowCredentials` rỗng, authenticator có thể đề xuất các **discoverable credentials** thuộc RP ID. Với username-first, RP có thể cung cấp một danh sách credential ID của đúng account cần xác thực.

### 7.2. Browser gọi get()

~~~javascript
// Đoạn minh họa; requestOptionsWithArrayBuffers là options
// đã chuyển Base64URL challenge và credential IDs sang binary.
const assertion = await navigator.credentials.get({
  publicKey: requestOptionsWithArrayBuffers
});

// assertion.response là AuthenticatorAssertionResponse.
// Gửi ID, authenticatorData, clientDataJSON, signature,
// userHandle (nếu có) theo contract API server.
~~~

Nếu người dùng từ chối, timeout hoặc không có credential phù hợp, browser có thể trả lỗi như `NotAllowedError` hoặc `SecurityError` tùy tình huống. Không coi mọi lỗi là “sai passkey” rồi khuyến khích đăng ký lại không kiểm soát.

### 7.3. Authenticator ký những byte nào?

Với authentication assertion chuẩn, authenticator tạo chữ ký trên:

~~~text
authenticatorData || SHA-256(clientDataJSON)
~~~

Trong đó:

- `authenticatorData` chứa `rpIdHash = SHA-256(RP ID)`, flags UP/UV và các thành phần khác như signature counter.
- `clientDataJSON` do WebAuthn client cung cấp chứa `type="webauthn.get"`, challenge, origin và các trường theo bối cảnh.
- Private key của credential tạo chữ ký bằng thuật toán đã đăng ký; server dùng **public key** tương ứng kiểm chữ ký.

**Quan trọng:** server không chỉ so `signature` rồi coi hợp lệ. Nó còn phải so từng thành phần và chính sách ceremony. Tự thay `clientDataJSON` hoặc challenge sẽ làm hỏng chữ ký hay thất bại kiểm tra dữ liệu.

### 7.4. Checklist bắt buộc phía RP khi kiểm assertion

1. **Tìm đúng credential:** từ credential ID mà browser trả về, truy xuất bản ghi đã đăng ký; credential không tồn tại hoặc bị revoke → từ chối.
2. **Kiểm `type`:** client data phải thể hiện `webauthn.get`, không nhầm với `webauthn.create`.
3. **Kiểm challenge:** đúng byte challenge đã tạo, thuộc request/session/transaction dự kiến, còn hiệu lực và chưa sử dụng.
4. **Kiểm origin:** nằm trong danh sách origin đã cho phép; xử lý `crossOrigin`, `topOrigin`/iframe nếu triển khai trường hợp đặc biệt.
5. **Kiểm `rpIdHash`:** khớp SHA-256 của RP ID được kỳ vọng.
6. **Kiểm chữ ký:** sử dụng credential public key đã lưu và đúng thuật toán; data chính xác theo WebAuthn.
7. **Kiểm UP/UV:** UP là user presence; UV là user verification. Nếu chính sách yêu cầu UV thì cờ UV phải được bật, không đánh đồng chỉ chạm khóa với xác minh user.
8. **Kiểm user handle và account mapping:** credential thuộc đúng account/tenant; không đổi account theo trường client gửi khi không khớp dữ liệu đã lưu.
9. **Kiểm signature counter phù hợp:** nếu authenticator có counter đáng tin, xử lý tình huống không tăng như dấu hiệu rủi ro; không áp dụng quy tắc cứng “phải tăng” cho mọi synced credential có counter 0.
10. **Dọn trạng thái:** tiêu thụ challenge, cập nhật metadata, tạo Spring `Authentication` và session bảo vệ chống session fixation.

Chỉ khi **tất cả các kiểm tra tương ứng chính sách** thành công mới thiết lập phiên người dùng. Đừng triển khai validator bằng vài biểu thức if đơn giản; dùng WebAuthn4J hoặc thư viện đã kiểm thử để xử lý CBOR/COSE và toàn bộ protocol.

## 8. Các cờ và trường quan trọng trong WebAuthn

### 8.1. User Presence (UP) và User Verification (UV)

| Thuộc tính | Chứng minh điều gì? | Ví dụ | Không chứng minh |
| --- | --- | --- | --- |
| **UP** | Người tương tác với authenticator hiện diện/đã chấp thuận thao tác | Chạm vào security key | Đã xác minh danh tính cục bộ bằng PIN/biometric |
| **UV** | Authenticator đã xác minh user cục bộ theo cơ chế hỗ trợ | PIN, biometric, password thiết bị | Chứng cứ để RP thu thập biometric |
| **BE/BS** | Backup eligibility / backup state khi authenticator báo cáo | Credential có thể đồng bộ hoặc đã backup | Bảo đảm chất lượng bảo mật của cloud sync provider |
| **signCount** | Counter theo authenticator/credential khi có | RP có thể phát hiện bất thường nếu counter được dùng | Tuyệt đối chứng minh thiết bị bị clone khi bằng 0 hoặc không tăng |

Khi tổ chức muốn **passkey sign-in có xác minh người dùng cục bộ**, RP nên yêu cầu `userVerification="required"` và server phải kiểm UV. Cảm biến vân tay/Face ID chỉ gửi kết quả verification thông qua authenticator; RP không nhận bản mẫu sinh trắc học.

### 8.2. Attestation khác assertion

**Attestation** xảy ra khi **đăng ký** credential: giúp RP đánh giá thông tin về authenticator hoặc nguồn gốc credential theo policy. Có thể gồm attestation statement, AAGUID, chứng thư attestation; trong nhiều use case consumer, `attestation="none"` là đủ để giảm tracking/privacy risks.

**Assertion** xảy ra khi **đăng nhập**: chữ ký trên challenge mới và dữ liệu WebAuthn chứng minh quyền sử dụng private key của credential đã đăng ký.

Attestation không phải mật khẩu và không mặc định cần thiết để đăng nhập. Không yêu cầu mọi người dùng trình chứng thư attestation X.509 doanh nghiệp khi sản phẩm không cần policy xác minh thiết bị.

### 8.3. Các định dạng dữ liệu

- `attestationObject`: CBOR object, thường chứa `authData` và attestation statement.
- `authenticatorData`: binary, gồm RP ID hash/flags/counter và các phần mở rộng.
- `clientDataJSON`: JSON bytes do browser tạo về type, challenge, origin.
- `credentialPublicKey`: public key ở dạng COSE_Key; server cần decoder COSE đúng.
- `credential.id`/`rawId`: byte ID, thường chuyển sang Base64URL trong API JSON.
- `signature`: bytes được tạo bởi authenticator.
- `userHandle`: identifier account dạng opaque bytes, có thể xuất hiện khi authentication.

**Base64URL là encoding, không phải chữ ký hay mã hóa bí mật.** Khi đưa binary qua JSON, chỉ encode/decode đúng chiều, không lấy chuỗi Base64URL để so trực tiếp với byte array một cách tùy tiện.

## 9. Ví dụ Spring Boot 3.5 + Spring Security 6.5 (Java 17+)

Spring Security 6.5 hỗ trợ đăng ký và xác minh passkey trong ứng dụng Servlet bằng WebAuthn, dựa vào thư viện **WebAuthn4J**. Ví dụ này dùng **login bằng mật khẩu để đăng ký passkey lần đầu**, sau đó thử **passkey login**. Đây là **demo học tập**: không có persistence lâu dài, account recovery, audit, rate limiting hoặc policy doanh nghiệp.

### 9.1. Tạo Maven project

Tạo cấu trúc:

~~~text
passkey-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── passkey/
                    └── PasskeyDemoApplication.java
~~~

Tệp `pom.xml` đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>passkey-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

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
            <groupId>com.webauthn4j</groupId>
            <artifactId>webauthn4j-core</artifactId>
            <version>0.29.7.RELEASE</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Phiên bản WebAuthn4J ở đây dựa theo hướng dẫn Spring Security 6.5. Nếu nâng lên Spring Security 7 hoặc Boot 4, **kiểm lại dependency**: hệ module và cấu hình WebAuthn có thể khác. Không mặc định copy phiên bản này cho mọi phiên bản Spring.

### 9.2. Java source đầy đủ

Tạo `src/main/java/demo/passkey/PasskeyDemoApplication.java`:

~~~java
package demo.passkey;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PasskeyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasskeyDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .webAuthn(webAuthn -> webAuthn
                .rpId("localhost")
                .rpName("Passkey Learning Demo")
                .allowedOrigins("http://localhost:8080"));

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-password")
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }

    @RestController
    static class ExampleController {

        @GetMapping({"/", "/public"})
        String welcome() {
            return "Passkey demo running";
        }

        @GetMapping("/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("username", authentication.getName());
        }
    }
}
~~~

**Giải thích:**

1. `formLogin(...)` tạo đường đăng nhập bằng password cho bước **onboarding demo**; không phải yêu cầu của WebAuthn rằng passkey luôn cần password.
2. `webAuthn(...)` bật tích hợp passkey: RP ID `localhost`, chỉ tin origin `http://localhost:8080`.
3. `.anyRequest().authenticated()` bảo vệ `/me` và các route khác; default WebAuthn registration page cần người dùng đã xác thực để tạo credential gắn đúng tài khoản.
4. `UserDetailsService` tạo user demo `learner`. `{noop}` **chỉ được dùng trong bài lab**; production dùng PasswordEncoder mạnh, không lưu password rõ.
5. Spring Security 6.5 cung cấp giao diện đăng ký credential ở `/webauthn/register` và hỗ trợ passkey trên login page mặc định.
6. Repository WebAuthn mặc định lưu in-memory; sau restart dữ liệu passkey demo **không tồn tại**, mặc dù passkey provider trên thiết bị vẫn có thể giữ credential cũ. Production cần persistent storage và credential lifecycle.

### 9.3. Chạy thử trên localhost

Trong thư mục `passkey-demo`, với JDK 17+ và Maven đã cài:

~~~bash
mvn spring-boot:run
~~~

Browser mở **chính xác** `http://localhost:8080` (không dùng `http://127.0.0.1:8080` cho demo RP ID/origin này). Nếu ứng dụng khởi động, trang public hiển thị:

~~~text
Passkey demo running
~~~

Truy cập `http://localhost:8080/me` khi chưa đăng nhập → Spring Security chuyển đến trang login. Đăng nhập bằng:

~~~text
Username: learner
Password: demo-password
~~~

Sau đó truy cập:

~~~text
http://localhost:8080/webauthn/register
~~~

Dùng trình duyệt/thiết bị hỗ trợ WebAuthn, tạo passkey theo UI hệ điều hành hoặc passkey provider. Có thể yêu cầu PIN/biometric cục bộ. Sau đăng ký thành công:

1. Đăng xuất qua `/logout` theo luồng Spring Security phù hợp.
2. Mở lại trang login và chọn phương thức passkey nếu trình duyệt và giao diện mặc định hiển thị.
3. Chọn passkey đã đăng ký, xác minh tại authenticator.
4. Truy cập `/me`. Response JSON dự kiến:

~~~json
{"username":"learner"}
~~~

Kết quả đăng nhập phụ thuộc browser/OS, WebAuthn4J, RP ID/origin đúng, trạng thái session và passkey có sẵn. Không khẳng định có một stdout Java đặc biệt khi credential được đăng ký, vì đó là quy trình browser↔server.

**Phân biệt thử nghiệm:** mã Spring ở trên là **một ứng dụng runnable trong Maven khi dependency tương thích**, nhưng không có một “passkey giả” do mã Java tạo sẵn. Cần thao tác browser/authenticator thật để hoàn tất WebAuthn ceremony.

### 9.4. Endpoint minh họa khi xây frontend riêng

Theo hướng dẫn Spring Security 6.5, các endpoint có thể gặp:

| Endpoint | Vai trò | Lưu ý |
| --- | --- | --- |
| `GET /webauthn/register` | Giao diện đăng ký mặc định | User phải được xác thực |
| `POST /webauthn/register/options` | Sinh creation options + challenge | CSRF token; thay đổi trạng thái |
| `POST /webauthn/register` | Nhận registration response | CSRF; chỉ ghi sau validation |
| `POST /webauthn/authenticate/options` | Sinh authentication options + challenge | CSRF; ràng buộc ceremony |
| `POST /login/webauthn` | Nhận authentication assertion | CSRF; tạo authentication khi hợp lệ |

Khi tự viết frontend, browser cần chuyển binary fields Base64URL↔ArrayBuffer và gửi payload đúng JSON contract của phiên bản Spring Security đang dùng. Không giả định response shape tùy ý của thư viện JavaScript khác tự tương thích với endpoint mặc định.

Spring Security 6.5 có các interface lưu credential như `PublicKeyCredentialUserEntityRepository` và `UserCredentialRepository`; có implementation JDBC và cho phép custom repository bean. Repository challenge/creation options có thể mặc định dựa vào HTTP session; khi đa replica cần bảo đảm session/sticky routing hoặc shared state thích hợp.

## 10. Chương trình Java 17 độc lập: private key ký, public key kiểm

Chương trình này **không phải WebAuthn server/client**. Nó chỉ chứng minh nguyên tắc chữ ký bất đối xứng trong một credential: private key ký dữ liệu gắn với một RP/challenge; public key phát hiện khi dữ liệu bị thay. WebAuthn thật dùng `authenticatorData || SHA-256(clientDataJSON)`, kiểm origin/rpIdHash/counter/flags và xử lý CBOR/COSE như mục 7.

Tạo tệp `CredentialSignatureDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Base64;

public class CredentialSignatureDemo {

    static byte[] sign(PrivateKey key, byte[] message) throws Exception {
        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(key);
        signer.update(message);
        return signer.sign();
    }

    static boolean verify(PublicKey key, byte[] message, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(key);
        verifier.update(message);
        return verifier.verify(signature);
    }

    static byte[] bytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(256);
        KeyPair credentialKeys = generator.generateKeyPair();

        byte[] challenge = new byte[32];
        new SecureRandom().nextBytes(challenge);
        String challengeText = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(challenge);

        String original = "rp=login.example.com|challenge=" + challengeText;
        byte[] signature = sign(credentialKeys.getPrivate(), bytes(original));

        String wrongRp = "rp=evil.example.net|challenge=" + challengeText;
        String wrongChallenge = original + "-modified";

        System.out.println("valid=" +
                verify(credentialKeys.getPublic(), bytes(original), signature));
        System.out.println("wrongRp=" +
                verify(credentialKeys.getPublic(), bytes(wrongRp), signature));
        System.out.println("wrongChallenge=" +
                verify(credentialKeys.getPublic(), bytes(wrongChallenge), signature));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 CredentialSignatureDemo.java
java CredentialSignatureDemo
~~~

**Stdout chính xác:**

~~~text
valid=true
wrongRp=false
wrongChallenge=false
~~~

Giải thích: mỗi lần chạy tạo một cặp khóa và challenge mới, nhưng kết quả boolean giống nhau; public key kiểm chữ ký hợp lệ trên dữ liệu gốc và phát hiện hai trường hợp sửa thông điệp.

**Không dùng demo crypto này làm authentication backend**: nó thiếu browser-provided origin, cấu trúc authenticator data, RP ID hash, challenge persistence, UP/UV, credential record/account mapping, chuẩn COSE và mọi yêu cầu WebAuthn khác.

## 11. Tại sao Spring Security cần kho credential riêng?

Một user có thể có nhiều credential và nhiều thiết bị. Hệ thống cần lưu **public keys cùng metadata theo account**, đồng thời phân biệt tài khoản quản trị app với passkey identity.

Ví dụ:

~~~text
users
  user_id: 42
  username: learner

webauthn_users
  user_id: 42
  user_handle: opaque-account-identity

credentials
  credential_id: <binary ID>
  user_id: 42
  public_key: <COSE>
  signature_counter: ...
  status: active
  created_at: ...
  last_used_at: ...
~~~

Schema trên minh họa mô hình quan hệ, không phải DDL của Spring. Điều bắt buộc về bảo mật:

- Bản ghi **credential ID phải unique** theo namespace hợp lệ.
- Credential được gắn **duy nhất với account đã xác thực trong registration**; không gắn theo email chưa xác minh.
- Nếu thay email/username, user handle ổn định và credential mapping vẫn đúng.
- Hủy credential phải khiến login bằng credential đó không còn được chấp nhận, kể cả authenticator/provider vẫn còn lưu private key.
- Trong cluster, tất cả instances phải dùng cùng credential store và nhất quán counter/challenge lifecycle.

### Credential management cần gì?

Một UI an toàn nên hỗ trợ:

- Liệt kê credential theo label, thời điểm tạo, lần dùng gần nhất và loại/thiết bị khi có metadata.
- Thêm passkey sau khi **recent reauthentication** hoặc một proof mạnh tương đương.
- Xóa một credential sau bước xác nhận có quyền, không dựa vào ID do client tự gửi.
- Cảnh báo khi thêm/xóa credential; kiểm tra khi xóa chiếc cuối cùng.
- Cho phép nhiều passkeys để giảm phụ thuộc một thiết bị.
- Quy trình recovery được bảo vệ tương xứng với passkey; tránh password fallback quá yếu vô hiệu hóa lợi ích phishing resistance.

## 12. Các rủi ro và giới hạn bảo mật thường bị hiểu sai

### 12.1. Phishing resistance đến từ đâu?

Passkey bị ràng buộc với RP ID, còn browser client tạo `clientDataJSON` chứa origin và challenge. Authenticator ký dữ liệu liên kết với RP ID; RP kiểm chữ ký và các trường liên quan. Một trang khác domain không thể hợp lệ dùng credential cùng RP ID trong luồng WebAuthn chuẩn. Điều này tốt hơn password/OTP dễ bị chuyển tiếp tới trang giả.

Nhưng **chỉ bật WebAuthn mà server bỏ kiểm origin/challenge/rpIdHash** sẽ phá vỡ bảo vệ. Dùng thư viện đã được duy trì và kiểm thử các nhánh âm tính.

### 12.2. Không chống mọi rủi ro của session

Passkey login có thể an toàn nhưng session cookie sau login vẫn bị đánh cắp qua XSS, cấu hình cookie sai hoặc session fixation. Tiếp tục cấu hình:

- HTTPS, HSTS, CSP và kiểm soát XSS.
- Cookie `Secure`/`HttpOnly`/`SameSite` phù hợp, session fixation protection.
- CSRF protection cho chức năng thay đổi trạng thái, nhất là đăng ký/xóa credential.
- Rate limiting, audit, session timeout và giới hạn các hành động nhạy cảm.
- Reauthentication cho thêm passkey, đổi recovery method hoặc thao tác quản trị.

### 12.3. UP không đồng nghĩa UV

Chạm một security key có thể cho thấy **user presence** mà chưa xác minh user cục bộ. Nếu policy yêu cầu PIN/biometric, server phải yêu cầu UV và **kiểm cờ UV**. Không tuyên bố “passkey lúc nào cũng MFA” chỉ vì một số thiết bị có biometrics.

### 12.4. Attestation không mặc định cần thiết

Attestation có thể giúp doanh nghiệp giới hạn authenticator theo danh sách tin cậy nhưng thêm phức tạp/privacy constraints. Với dịch vụ consumer, yêu cầu `attestation="none"` thường phù hợp. Dù attestation thành công vẫn phải kiểm public key, challenge, RP ID và account binding.

### 12.5. Đồng bộ và mất thiết bị

Synced passkeys hỗ trợ đăng nhập trên nhiều thiết bị qua nhà cung cấp đồng bộ, nhưng tổ chức cần đánh giá bảo mật tài khoản sync, chính sách recovery của provider và yêu cầu assurance. Device-bound có thể phù hợp môi trường độ bảo đảm cao, nhưng phải có credential thay thế nếu mất khóa. Không đưa ra khẳng định tuyệt đối rằng synced/device-bound nào cũng an toàn hơn trong mọi use case.

## 13. Lỗi thường gặp khi tích hợp WebAuthn

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `navigator.credentials` không có/throw SecurityError | Trang không secure context, RP ID không hợp lệ | Dùng HTTPS; dev dùng `http://localhost`; kiểm effective domain |
| Browser báo `NotAllowedError` | Người dùng hủy, timeout, thiếu credential, authenticator không đáp ứng | Đọc lỗi browser không tiết lộ nội bộ; cho retry hợp lý |
| Register xong nhưng login fail sau restart | Credential repository in-memory bị reset | Dùng database persistent |
| Challenge mismatch | Session mất, challenge hết hạn, request lặp hoặc binary decoding sai | Store short TTL, base64url đúng, bind session/operation |
| Origin mismatch | Truy cập bằng host/port/scheme khác config | Đặt `allowedOrigins` theo public origin thực |
| RP ID hash mismatch | `rpId` đổi giữa đăng ký và đăng nhập | Dùng RP ID ổn định đúng domain |
| Signature failed | Public key sai credential ID, data decode/serialize sai hoặc signature bị thay | Không tự viết crypto parser; dùng thư viện |
| User verification required nhưng UV=false | Authenticator không xác minh user cục bộ | Chọn thiết bị/phương thức hỗ trợ, duy trì policy UV |
| Có credential nhưng user bị gán sai | Sai `userHandle`/credentialId→account mapping | Kiểm mapping phía server và unique constraints |
| Counter không tăng | Synced key/counter zero hoặc rủi ro clone | Áp quy tắc counter theo thiết bị/thư viện, audit |
| POST options/register trả 403 | CSRF thiếu hoặc tài khoản chưa được xác thực | Gửi CSRF token đúng và bảo vệ registration |
| Dùng `127.0.0.1` cho demo RP `localhost` | Origin/RP ID không khớp | Dùng đúng `http://localhost:8080` |
| Người dùng mất thiết bị, không còn passkey | Chưa có multiple credentials/recovery | Quy trình đăng ký credential bổ sung và recovery mạnh |
| Kẻ có session cũ thêm passkey mới | Thiếu recent reauthentication | Require step-up, thông báo thay đổi, audit |

## 14. Checklist triển khai production

### Cấu hình RP

- [ ] RP ID tối thiểu, ổn định và chỉ bao phủ origins đáng tin.
- [ ] HTTPS production; hostname/scheme/port public trùng `allowedOrigins`.
- [ ] Dùng thư viện WebAuthn server được cập nhật; không tự viết COSE/CBOR validator.
- [ ] Challenge tạo bằng CSPRNG, đủ entropy, có TTL, one-time và bind ceremony.
- [ ] Cấu hình danh sách thuật toán đáng tin, user verification theo policy.
- [ ] Đảm bảo registration chỉ cho account đã xác thực/được onboarding hợp lệ.
- [ ] Xác minh type/challenge/origin/rpIdHash/UP/UV/signature/account mapping.
- [ ] Attestation policy có mục đích rõ, tôn trọng privacy.
- [ ] Signature counter và backup flags được xử lý an toàn, không áp logic sai cho synced passkeys.

### Dữ liệu và vòng đời

- [ ] Lưu credential ID, public key, user handle, owner, metadata cần thiết trong storage persistent.
- [ ] Hỗ trợ thêm nhiều passkeys và quản lý/xóa/revoke có xác thực lại.
- [ ] Kiểm userHandle/credential ID uniqueness và tenant isolation.
- [ ] Thiết kế account recovery mạnh, không hạ chuẩn bảo mật qua password/email fallback yếu.
- [ ] Theo dõi audit/passkey enrollment, bất thường, loss/recovery, device rotation.
- [ ] Bảo vệ session, CSRF, XSS, cookie, rate limiting như các cơ chế đăng nhập khác.

### Kiểm thử tối thiểu

- [ ] Register thành công và login bằng passkey thật.
- [ ] Login không có credential, credential bị xóa hoặc revoked.
- [ ] Challenge hết hạn, lặp lại/challenge sai.
- [ ] Origin và RP ID sai; giả mạo JSON fields.
- [ ] Chữ ký sai, credential ID không tồn tại.
- [ ] UP/UV flag không thỏa policy.
- [ ] Credential thuộc user A không thể authenticate thành user B.
- [ ] Login sau restart/đa replica khi dùng persistent storage.
- [ ] Thêm/xóa credential trái quyền hoặc thiếu recent reauthentication phải bị từ chối.
- [ ] Recovery và thiết bị mất/tráo đổi tài khoản không vượt quyền.

Để kiểm thử server-side validation trong Java, ưu tiên các fixtures WebAuthn đúng cấu trúc và integration tests qua browser/authenticator giả lập có kiểm soát, không chỉ unit test rằng JSON có trường `signature`.

## 15. Câu hỏi tự kiểm tra

1. Relying Party và authenticator có phải cùng một thành phần không? Private key thuộc phía nào?
2. Tại sao server cần lưu cả credential ID lẫn public key?
3. `user.id` (user handle) khác email/username ra sao?
4. Browser làm nhiệm vụ gì giữa JavaScript WebAuthn API và authenticator?
5. Khi đăng ký, `navigator.credentials.create()` trả attestation response hay authentication assertion?
6. Khi đăng nhập, vì sao server phải kiểm `SHA-256(RP ID)` trong authenticator data?
7. Chỉ kiểm chữ ký bằng public key đã đủ cho một WebAuthn login hợp lệ chưa? Thiếu những gì?
8. Sự khác nhau giữa User Presence và User Verification là gì?
9. Tại sao synced passkey không có nghĩa private key vĩnh viễn chỉ tồn tại trên một thiết bị?
10. Vì sao passkey vẫn cần CSRF, session management và account recovery mạnh?
11. Vì sao demo dùng `localhost`, không phải mọi HTTP hostname tùy ý?
12. Nếu account bị chiếm session và kẻ xấu đăng ký passkey mới, passkey có tự bảo vệ account khỏi trường hợp này không?

**Kết luận:** Authenticator là bên **quản lý private key và ký**, browser là bên **điều phối WebAuthn và cung cấp origin**, RP là bên **phát challenge, lưu public key và xác minh toàn bộ ràng buộc**. Credential khóa công khai bảo đảm server không cần giữ một shared-secret password để xác thực user, nhưng chỉ an toàn khi các bước registration, assertion verification, session và recovery đều được thiết kế đúng.

## 16. Tài liệu chính thức và hướng dẫn bảo mật

- [W3C — Web Authentication Level 3](https://www.w3.org/TR/webauthn-3/)
- [Spring Security 6.5 — Passkeys (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html)
- [Spring Security 6.5 — WebAuthnConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/WebAuthnConfigurer.html)
- [OWASP — Passkey Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Passkey_Security_Cheat_Sheet.html)
- [FIDO Alliance — Passkeys](https://fidoalliance.org/passkeys-2/)
- [MDN — Web Authentication API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API)
- [Spring Blog — Spring Boot 3.4 / WebAuthn demo](https://spring.io/blog/2024/11/24/bootiful-34-security/)

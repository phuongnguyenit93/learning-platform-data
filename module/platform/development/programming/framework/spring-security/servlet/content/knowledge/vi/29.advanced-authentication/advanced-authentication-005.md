# Relying Party ID, origin, HTTPS và lưu trữ thông tin xác thực WebAuthn

## 1. Mục tiêu và mô hình bảo mật

**WebAuthn** (Web Authentication) cho phép ứng dụng xác thực người dùng bằng thông tin xác thực khóa công khai gắn với một **Relying Party (RP)**. Một authenticator (ví dụ khóa bảo mật phần cứng, nền tảng của điện thoại hoặc passkey đồng bộ) tạo/sử dụng cặp khóa. **Private key** do authenticator quản lý; server lưu **public key** và metadata cần thiết để kiểm tra chữ ký.

WebAuthn chống phishing nhờ ràng buộc thông tin xác thực với danh tính website: trình duyệt kiểm soát **Relying Party ID (RP ID)** và tạo dữ liệu có **origin** của trang gọi WebAuthn; server phải xác minh cả hai khi hoàn tất đăng ký và đăng nhập. WebAuthn không chỉ là “ký một challenge”. Một chữ ký hợp lệ dưới khóa công khai **không đủ** nếu challenge, origin, RP ID, trạng thái người dùng và chính sách user verification không khớp.

Trong ứng dụng **Spring Security Servlet**, hãy coi những thành phần sau là các lớp khác nhau:

- **RP ID:** định danh domain cho phạm vi sử dụng credential, ví dụ `example.com`. Không chứa `https://`, cổng hoặc đường dẫn.
- **Origin:** nguồn website cụ thể, về cơ bản là bộ ba `scheme://host[:port]`, ví dụ `https://login.example.com`. Phải đối chiếu với tập origin được ứng dụng chấp thuận.
- **HTTPS / secure context:** điều kiện an toàn để browser cung cấp WebAuthn API trong môi trường sản xuất, đồng thời bảo vệ challenge và phiên đăng nhập trên đường truyền.
- **Public-key credential store:** lưu credential ID, public key, user handle, counter và metadata; **không lưu private key** hoặc xem credential ID như password.
- **Ceremony verification:** xác minh đúng đăng ký (`navigator.credentials.create`) hoặc xác thực (`navigator.credentials.get`), nhất là `challenge`, `clientDataJSON`, `authenticatorData` và chữ ký.

Mục tiêu cuối bài: cấu hình RP ID/origin hợp lý, hiểu bước xác minh, thiết kế bảng lưu credential an toàn, có thể kiểm thử một số bất biến với Java 17+ và tránh lỗi phổ biến khi triển khai passkeys với Spring Security.

## 2. RP ID và origin: liên quan nhưng không giống nhau

### 2.1. Relying Party ID là gì?

RP ID là định danh domain mà authenticator dùng để gắn credential với relying party. Nó thường là hostname hoặc hậu tố domain hợp lệ của hostname trang web gọi WebAuthn, **không được chọn tùy ý một domain không liên quan hoặc một public suffix như `com`** trong trường hợp thông thường.

Ví dụ ứng dụng đăng nhập ở `https://login.example.com`:

- RP ID `login.example.com`: chỉ phạm vi cụ thể của host đăng nhập.
- RP ID `example.com`: có thể hỗ trợ nhiều subdomain thuộc `example.com` nếu kiến trúc và policy origin cho phép.
- RP ID `accounts.other.example`: không phải RP ID hợp lệ theo quan hệ domain thông thường của origin `login.example.com`.
- RP ID `com`: không hợp lệ vì là public suffix.
- RP ID `https://example.com` hoặc `example.com:443`: **không đúng định dạng**; đây không phải hostname RP ID.

**Nguyên tắc an toàn:** chọn RP ID cố định, nhỏ nhất có thể để đáp ứng phạm vi truy cập thực tế. Nếu các subdomain thuộc các nhóm quản trị/rủi ro khác nhau, chia RP ID phù hợp và dùng allowlist origin chặt chẽ. Không tự động đặt RP ID ở domain cha chỉ vì “muốn dùng passkey ở mọi subdomain”.

Có những cơ chế mở rộng cho **related origins** ở các phiên bản WebAuthn/browser nhất định; đây là quy trình có ràng buộc riêng, không có nghĩa mọi domain khác nhau được tự do dùng chung RP ID. Trước khi dùng, phải kiểm tra đặc tả, hỗ trợ trình duyệt và cấu hình tin cậy. Với kiến trúc thông thường, hãy áp dụng quy tắc host/hậu tố domain hợp lệ.

### 2.2. Origin là gì?

Origin mô tả **website thực sự gọi WebAuthn API**. Với web thông thường, origin gồm scheme (HTTP/HTTPS), hostname và cổng (cổng mặc định có quy tắc chuẩn hóa). Một số ví dụ:

| Website gọi API | RP ID `example.com` | Origin server cần xét |
| --- | --- | --- |
| `https://example.com` | Hợp lệ theo quan hệ domain | `https://example.com` |
| `https://login.example.com` | Hợp lệ theo quan hệ domain | `https://login.example.com` |
| `https://app.example.com` | Hợp lệ theo quan hệ domain | `https://app.example.com` |
| `https://login.example.com:8443` | Domain RP ID vẫn khớp | **Origin khác** với `https://login.example.com` do cổng |
| `https://evil-example.com` | **Không** cùng domain/hậu tố hợp lệ | `https://evil-example.com` không được chấp nhận |
| `http://login.example.com` | HTTPS không được bảo đảm | Không phải origin sản xuất an toàn cho WebAuthn |

Một RP ID có thể tương ứng **nhiều origin hợp lệ**: ví dụ server chỉ cho phép `https://login.example.com` và `https://account.example.com` dùng cùng `example.com`. Nhưng danh sách phải **tường minh** và được kiểm soát, không nên khớp chuỗi tùy tiện bằng `endsWith("example.com")` vì `evil-example.com` cũng kết thúc theo cách so sánh ngây thơ.

**Origin khác với HTTP `Origin` header do request gửi lên.** Khi xác minh WebAuthn, server cần đọc trường `origin` nằm trong **`clientDataJSON`** do WebAuthn client tạo, đồng thời thực hiện các kiểm tra chữ ký và challenge. Đừng lấy `Host`, `X-Forwarded-Host` hoặc `Origin` header đơn lẻ làm bằng chứng rằng assertion là từ đúng origin. Các header hạ tầng có thể hữu ích để xử lý routing/CSRF, nhưng không thay thế kiểm tra WebAuthn.

### 2.3. Vì sao cần cả RP ID và origin?

Hai kiểm tra chặn những vấn đề khác nhau:

1. Authenticator tạo `rpIdHash = SHA-256(rpId)` trong `authenticatorData`, gắn assertion với RP ID.
2. `clientDataJSON.origin` cho biết origin nơi browser thực hiện WebAuthn ceremony; server so sánh với các origin được cho phép.
3. Dữ liệu dùng để ký có ràng buộc `authenticatorData` với `clientDataJSON`, nên không thể chỉ sửa origin hoặc rpIdHash tùy tiện mà vẫn giữ chữ ký hợp lệ.

Nếu chỉ xét rpIdHash mà không xác minh origin, một subdomain không đáng tin nhưng vẫn nằm trong phạm vi RP ID có thể trở thành rủi ro. Nếu chỉ so origin mà không xét rpIdHash, server không chứng minh được credential đang được dùng cho đúng RP ID đã dự kiến. **Luôn kiểm tra cả hai.**

## 3. rpIdHash, clientDataJSON và chữ ký

Trong giai đoạn xác thực bằng WebAuthn, server thường nhận các thành phần chính:

```text
credential.id / rawId       -> Credential ID dùng tìm public key
response.clientDataJSON     -> JSON bytes của client data
response.authenticatorData  -> Authenticator data bytes
response.signature          -> Chữ ký từ authenticator
response.userHandle         -> Có thể có user handle (discoverable credential)
```

Server xác minh tối thiểu:

- `clientDataJSON.type` là `webauthn.get` khi xác thực hoặc `webauthn.create` khi đăng ký.
- `clientDataJSON.challenge` khớp challenge **đã phát hành cho ceremony này**, chưa hết hạn/chưa bị sử dụng; xử lý base64url và bytes chính xác.
- `clientDataJSON.origin` nằm trong allowlist origin của RP, không chỉ khớp tên miền gần giống.
- `authenticatorData.rpIdHash` khớp `SHA-256` của RP ID đã cấu hình.
- Cờ **User Presence (UP)**, **User Verification (UV)** và các quy tắc bổ sung được kiểm tra theo chính sách và loại ceremony.
- Với authentication, chữ ký được xác minh bằng public key đã lưu của credential trên chuỗi byte **`authenticatorData || SHA-256(clientDataJSON)`**, không phải bằng cách ký lại chuỗi JSON đã parse/serialize.
- Các trường credential ID, user handle và tài khoản phải nhất quán với credential store; quyền truy cập tài khoản không được quyết định chỉ từ một user ID do browser gửi.

Nếu bước kiểm tra nào không đạt, **không tạo phiên đăng nhập hay ghi nhận credential thành công**.

### 3.1. Java 17+ demo: RP ID hash và quan hệ hậu tố domain

Chương trình sau độc lập, chỉ dùng JDK 17. Nó minh họa độ dài SHA-256 của RP ID và so khớp hậu tố domain có dấu chấm phân cách. **Không dùng hàm demo để thay một WebAuthn verifier thực sự** vì nó không kiểm tra public suffix, IDN, related origins, client data hay chữ ký.

File `WebAuthnRpIdDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Locale;

public final class WebAuthnRpIdDemo {
    static byte[] rpIdHash(String rpId) throws NoSuchAlgorithmException {
        return MessageDigest.getInstance("SHA-256")
            .digest(rpId.getBytes(StandardCharsets.UTF_8));
    }

    static boolean hasRpIdSuffix(String host, String rpId) {
        String h = host.toLowerCase(Locale.ROOT);
        String rp = rpId.toLowerCase(Locale.ROOT);
        return h.equals(rp) || h.endsWith("." + rp);
    }

    public static void main(String[] args) throws Exception {
        String rpId = "example.com";
        byte[] expected = rpIdHash(rpId);

        System.out.println(expected.length);
        System.out.println(hasRpIdSuffix("login.example.com", rpId));
        System.out.println(hasRpIdSuffix("evil-example.com", rpId));
        System.out.println(MessageDigest.isEqual(
            expected, rpIdHash("example.com")));
        System.out.println(MessageDigest.isEqual(
            expected, rpIdHash("other.example.com")));
    }
}
```

Chạy:

```bash
javac WebAuthnRpIdDemo.java
java WebAuthnRpIdDemo
```

Stdout chính xác:

```text
32
true
false
true
false
```

**Lưu ý về triển khai thật:** RP ID phải qua kiểm tra hợp lệ theo WebAuthn/browser, bao gồm quy tắc public suffix và các trường hợp IDN; không nên tự viết policy bằng cách chỉ so một suffix string. Chữ ký phải được kiểm tra trên bytes gốc, dùng thư viện triển khai WebAuthn có kiểm thử và cập nhật an toàn.

## 4. HTTPS, secure contexts và reverse proxy

### 4.1. HTTPS là yêu cầu nền tảng

Trên trình duyệt hiện đại, WebAuthn là API chỉ khả dụng trong **secure context**. Trong sản xuất, website đăng ký/đăng nhập cần sử dụng HTTPS, chứng chỉ hợp lệ, và không bị downgrade sang HTTP.

- `https://login.example.com` là ví dụ origin sản xuất hợp lệ khi TLS và cấu hình RP đúng.
- `http://login.example.com` không phải origin WebAuthn sản xuất thích hợp.
- Browser có ngoại lệ về **potentially trustworthy localhost** phục vụ phát triển, ví dụ `http://localhost`. **Không suy ra** HTTP trên domain staging/production bất kỳ cũng được.
- Khi phát triển trên IP, tên host tùy biến hoặc proxy, hành vi secure context/RP ID có thể khác; kiểm tra trực tiếp trên môi trường thật thay vì nới policy production.

HTTPS không thay cho WebAuthn origin verification. Một trang phishing cũng có thể có chứng chỉ HTTPS hợp lệ cho *domain của attacker*. WebAuthn chỉ chống phishing đúng khi RP ID/origin/challenge và chữ ký được kiểm tra chính xác.

### 4.2. TLS termination qua proxy

Kiến trúc:

```text
Browser -- HTTPS --> Gateway / Load Balancer
                      |
                      +-- TLS / trusted internal link -->
                          Spring Boot Servlet application
```

Server phải biết domain public thật để cấu hình RP ID và allowed origins. Không tự lấy RP ID từ `request.getServerName()` khi request có thể được route qua nội bộ; cũng không tự tin mọi giá trị `X-Forwarded-*` từ Internet là đáng tin.

Các yêu cầu:
1. Chỉ tin các forwarded headers do **reverse proxy đã xác thực/được kiểm soát** tạo ra.
2. Proxy phải loại bỏ giá trị `Forwarded` / `X-Forwarded-*` do client ngoài tự gửi trước khi gắn giá trị mới.
3. Đặt RP ID và allowed origins bằng cấu hình rõ ràng theo môi trường, ví dụ production RP ID `example.com` và origin `https://login.example.com`.
4. Bật redirect HTTP → HTTPS, HSTS cho host phù hợp sau khi đã kiểm tra khả năng phục vụ HTTPS lâu dài; dùng cookie `Secure`/`HttpOnly`/`SameSite` cho session khi có.
5. Bảo vệ kết nối giữa proxy và ứng dụng theo kiến trúc; không để endpoint thực sự bị gọi trực tiếp từ mạng công cộng qua HTTP không kiểm soát.

Cổng quan trọng đối với **origin**: `https://login.example.com:8443` không giống `https://login.example.com`. RP ID thì không chứa cổng. Khi đổi từ dev sang production, đừng copy origin dev vào allowlist production.

## 5. Luồng đăng ký credential (Registration / create)

Đăng ký là thời điểm tạo cặp khóa và liên kết public key với tài khoản.

```text
(1) User đăng nhập bằng phương thức đáng tin
    -> yêu cầu đăng ký passkey, có kiểm tra reauthentication nếu cần
(2) Server tạo challenge ngẫu nhiên, ngắn hạn, duy nhất cho ceremony
    -> trả PublicKeyCredentialCreationOptions
(3) Browser gọi navigator.credentials.create({ publicKey: ... })
    -> kiểm tra origin/RP ID; authenticator tạo credential
(4) Browser trả credential ID + attestation response về server
(5) Server xác minh challenge, type, origin, RP ID hash,
    UP/UV flags, credential public key, định dạng/thuật toán...
(6) Chỉ sau verify thành công mới ghi credential vào database
    -> buộc nó với đúng account và đánh dấu ceremony đã dùng
```

### 5.1. Những thành phần của creation options

Ví dụ **cấu trúc minh họa** (các trường nhị phân cần được đưa về dạng byte đúng trước khi gọi browser API):

```json
{
  "rp": {
    "id": "example.com",
    "name": "Example"
  },
  "user": {
    "id": "BASE64URL_USER_HANDLE",
    "name": "alice@example.com",
    "displayName": "Alice"
  },
  "challenge": "BASE64URL_RANDOM_CHALLENGE",
  "pubKeyCredParams": [
    { "type": "public-key", "alg": -7 },
    { "type": "public-key", "alg": -257 }
  ],
  "timeout": 60000,
  "attestation": "none",
  "authenticatorSelection": {
    "userVerification": "required"
  }
}
```

Trong WebAuthn API gốc, `challenge` và `user.id` là bytes (`BufferSource`), **không phải string nguyên xi**. Nếu HTTP API chuyển options ở dạng JSON, client phải dùng chuyển đổi base64url → bytes hoặc browser helper hỗ trợ JSON WebAuthn. `user.id` (user handle) nên là định danh opaque, ổn định, không chứa thông tin cá nhân rõ ràng như email. Tên hiển thị chỉ dùng để giúp người dùng nhận biết credential; không dùng làm khóa bảo mật.

Những điểm cần xác minh khi hoàn tất registration:

- User **đã được xác thực** và được quyền thêm credential cho chính tài khoản đó.
- Challenge là ngẫu nhiên mật mã, đủ độ dài (thực tiễn thường dùng ít nhất 16 byte, ưu tiên 32 byte), ràng buộc với transaction/user, thời gian sống ngắn và không được sử dụng lại.
- `clientDataJSON.type == "webauthn.create"`; `origin` thuộc allowlist; challenge chính xác.
- `authenticatorData.rpIdHash` khớp RP ID; UP/UV đáp ứng policy.
- Attested credential data chứa credential ID và public key; kiểm tra cấu trúc/thuật toán phù hợp với policy.
- Nếu chính sách **yêu cầu attestation về loại authenticator**, phải xác minh chuỗi tin cậy, metadata và trust policy. Nếu không cần device attestation, có thể dùng `attestation: "none"`, nhưng vẫn phải verify dữ liệu đăng ký cần thiết.
- Credential ID chưa bị gán cho tài khoản khác trong cùng RP, tuân thủ unique constraint; lưu theo đúng tài khoản đã đăng nhập.
- Chỉ persist sau khi verifier trả thành công; bỏ challenge và trạng thái chờ sau thành công hoặc hết hạn.

**Attestation không phải assertion.** Attestation liên quan bước đăng ký/thông tin xuất xứ authenticator; assertion là chứng minh sở hữu private key trong lúc đăng nhập. Đừng yêu cầu attestation nhầm ở mọi lần đăng nhập, và đừng tin attestation chỉ vì client gửi một certificate.

## 6. Luồng xác thực (Authentication / get)

Với credential đã đăng ký, browser gọi `navigator.credentials.get` để tạo assertion dựa trên challenge mới.

```text
(1) Client yêu cầu bắt đầu đăng nhập
(2) Server tạo challenge mới, ràng buộc transaction
    -> trả PublicKeyCredentialRequestOptions (rpId, challenge,
       allowCredentials nếu phù hợp, userVerification...)
(3) Browser gọi navigator.credentials.get({ publicKey: ... })
    -> authenticator tạo chữ ký bằng private key thích hợp
(4) Server nhận credential ID, clientDataJSON,
    authenticatorData, signature, userHandle (có thể null)
(5) Server tìm credential đã lưu và xác minh:
    - challenge + origin + type == webauthn.get
    - rpIdHash + UP/UV
    - signature bằng public key đã đăng ký
    - credential/userHandle/account binding và counter/policy
(6) Nếu hợp lệ, tạo Authentication/session theo kiến trúc Spring Security
    và cập nhật metadata credential một cách an toàn
```

### 6.1. Request options

```json
{
  "challenge": "BASE64URL_NEW_CHALLENGE",
  "rpId": "example.com",
  "timeout": 60000,
  "userVerification": "required"
}
```

Không có `allowCredentials` ở ví dụ này: trình duyệt có thể sử dụng **discoverable credential** (passkey) và hỗ trợ luồng username-less phù hợp. Nếu hệ thống đã biết tài khoản, có thể gửi `allowCredentials` là danh sách credential IDs của tài khoản được phép dùng. Dù chọn mô hình nào, server phải tự xác minh credential ID và ràng buộc user; không tin bất kỳ account ID/userHandle nào client gửi mà chưa đối chiếu database.

### 6.2. Chữ ký cần kiểm tra chính xác

Với assertion:

```text
signedBytes = authenticatorDataBytes ||
              SHA-256(clientDataJSONBytes)

verifySignature(storedPublicKey, signedBytes, signatureBytes)
```

Dấu `||` là nối byte, không phải phép cộng string. Không lấy JSON rồi stringify lại trước khi hash: chữ ký dùng **bytes gốc** của `clientDataJSON`. Thư viện verifier chịu trách nhiệm decode COSE public key, signature algorithm, authenticator flags và kiểm tra cấu trúc; không nên tự triển khai đầy đủ WebAuthn crypto bằng regex hay parser tùy ý.

Một `signature` hợp lệ vẫn chưa đủ nếu `origin` hoặc `challenge` sai. Đặc biệt, server không được chấp nhận challenge từ một tài khoản/transaction khác hoặc challenge đã dùng.

### 6.3. UP, UV, BE, BS và signCount

- **UP (User Presence):** authenticator ghi nhận tương tác hiện diện của người dùng khi ceremony yêu cầu.
- **UV (User Verification):** authenticator đã thực hiện xác minh người dùng cục bộ theo yêu cầu, chẳng hạn biometrics/PIN. Nếu chính sách đòi UV, server phải kiểm tra cờ **UV**; không chỉ tin trường `userVerification: "required"` từ request options.
- **BE (Backup Eligible)** và **BS (Backup State):** metadata hữu ích cho credential có khả năng đồng bộ/dự phòng; phải xem chúng theo chính sách WebAuthn và biến thể authenticator, không dùng làm căn cứ duy nhất để chấp nhận/từ chối.
- **`signCount`:** bộ đếm có thể hỗ trợ phát hiện credential bị clone trong một số authenticator. Với passkeys đồng bộ/đa thiết bị, counter có thể bằng 0 hoặc không tăng theo cách truyền thống. **Không áp quy tắc “counter không tăng thì tài khoản chắc chắn bị chiếm” cho mọi passkey**; thay vào đó dùng tín hiệu rủi ro, chính sách sản phẩm và xử lý đồng bộ được tài liệu hóa.

Sau xác minh thành công có thể cập nhật `lastUsedAt`, counter và trạng thái backup; chú ý concurrent requests và optimistic locking. Không để cuộc đua ghi counter làm cho một assertion chưa xác minh được đánh dấu thành công.

## 7. Lưu trữ public-key credential: dữ liệu nào thuộc server?

WebAuthn lưu private key tại **authenticator**; với passkey đồng bộ, khóa có thể được bảo vệ và đồng bộ theo cơ chế của hệ sinh thái, nhưng server RP vẫn **không nhận private key**. Server cần giữ bản ghi public credential và quan hệ tài khoản.

| Trường | Kiểu lưu gợi ý | Mục đích / lưu ý |
| --- | --- | --- |
| `user_id` | Khóa nội bộ tới bảng users | Chủ tài khoản thực; bắt buộc kiểm soát quyền khi thêm/xóa credential |
| `rp_id` | String domain đã cấu hình | Ngăn lẫn credential giữa các RP và hỗ trợ audit/migration |
| `credential_id` | Bytes/BYTEA hoặc base64url chuẩn hóa | ID do authenticator trả, dùng lookup; unique trong phạm vi RP |
| `public_key_cose` | Bytes/BYTEA | Public key ở dạng COSE/format tương ứng với verifier; **không phải secret** |
| `user_handle` | Bytes/BYTEA (opaque, ổn định) | Liên kết account cho passkey discoverable; không nên dùng email/password |
| `sign_count` | Số nguyên không âm | Counter theo tiêu chuẩn, không giả định luôn tăng |
| `backup_eligible`, `backup_state` | Boolean/nullable | Metadata hỗ trợ policy/risk assessment |
| `aaguid` | UUID/bytes, nếu có | Metadata loại authenticator; không phải bằng chứng độ tin cậy khi không kiểm attestation |
| `transports` | List/JSON tùy nhu cầu | Hint hỗ trợ lựa chọn credential; không phải yếu tố xác thực |
| `created_at`, `last_used_at` | Timestamp | Audit, UI quản lý credential, phát hiện bản ghi cũ |
| `revoked_at` hoặc trạng thái | Timestamp/enum | Gỡ phương thức xác thực khi user báo mất thiết bị |
| `display_name` | Text do user đặt | Cho UI “MacBook”, “Security Key”; không đưa vào quyết định auth |

### 7.1. Ví dụ schema PostgreSQL

Đây là **một schema minh họa có thể chạy trên PostgreSQL**, với giả định ứng dụng đã có bảng `app_users(id UUID PRIMARY KEY)`. Chọn schema thực theo các repository của phiên bản Spring Security/WebAuthn library đang dùng; **không tự cho rằng class Spring Security sẽ tự ánh xạ vào bảng này**.

```sql
CREATE TABLE webauthn_credentials (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id),
    rp_id VARCHAR(253) NOT NULL,
    credential_id BYTEA NOT NULL,
    public_key_cose BYTEA NOT NULL,
    user_handle BYTEA NOT NULL,
    sign_count BIGINT NOT NULL DEFAULT 0 CHECK (sign_count >= 0),
    backup_eligible BOOLEAN,
    backup_state BOOLEAN,
    aaguid UUID,
    display_name VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,

    CONSTRAINT uq_webauthn_rp_credential
        UNIQUE (rp_id, credential_id)
);

CREATE INDEX idx_webauthn_credentials_user
    ON webauthn_credentials (user_id)
    WHERE revoked_at IS NULL;
```

Giải thích:
- `credential_id` và `public_key_cose` cần lưu **bytes đúng**, không chuyển qua encoding có thể làm mất `+`, `/` hoặc dấu `=` rồi so sánh sai. Nếu API truyền base64url, decode ở biên và lưu nhất quán.
- Ràng buộc `UNIQUE (rp_id, credential_id)` giảm nguy cơ một credential được gán trái phép vào hai account của cùng RP. Khi có lỗi trùng phải **từ chối/điều tra**, không tự gán lại account.
- `user_handle` nên được tạo bằng CSPRNG, ổn định với **mỗi account** và lưu ở user identity store; việc lặp lại user handle trong nhiều credential cùng account là bình thường. Có thể thay schema bằng foreign key tới bảng mapping userHandle riêng.
- `revoked_at` thể hiện trạng thái đã gỡ credential; verifier không được chấp nhận một bản ghi đã thu hồi.
- Đây là dữ liệu bảo mật và quyền riêng tư: hạn chế quyền DB, sao lưu an toàn, giám sát truy cập, bảo vệ dữ liệu theo chính sách tổ chức. Dù public key không phải password, quan hệ account ↔ thiết bị/credential ID có thể nhạy cảm về quyền riêng tư.

### 7.2. Không lưu sai loại bí mật

**Không lưu** private key, PIN, biometrics, secret của authenticator hoặc một bản sao credential từ thiết bị vì server không cần chúng. Đừng thu thập thông tin biometric chỉ để xác minh `UV`; WebAuthn được thiết kế để authenticator thực hiện xác minh cục bộ và RP chỉ kiểm tra kết quả theo cờ/protocol.

**Không xem `credential_id` là bearer token hay password.** Nó dùng để lookup public key; ai biết credential ID **không tự đăng nhập được** nếu không tạo chữ ký hợp lệ bằng private key. Tuy nhiên không nên công bố hàng loạt credential IDs/user handles vì có thể gây tracking, enumeration hoặc làm lộ mối liên kết tài khoản.

### 7.3. Challenge storage khác credential storage

**Challenge** không phải credential: challenge là giá trị ngắn hạn để chống replay, phải tạo mới cho từng ceremony. Có thể lưu trạng thái challenge trong server-side session hoặc cache thời gian sống ngắn (`Redis`, DB TTL, session store); khóa tra cứu phải gắn với transaction và user/flow thích hợp. Phải kiểm tra một lần và vô hiệu hóa sau khi hoàn thành/hết hạn.

Ví dụ model trạng thái:

```text
challenge_id / transaction_id
challenge_bytes
ceremony_type: register | authenticate
expected_rp_id
allowed_origins
user_id (đăng ký; hoặc user context phù hợp)
created_at / expires_at / consumed_at
```

Phía HTTP API chỉ đưa challenge và transaction reference cần thiết; không để client chọn lại expected RP ID/origins tùy ý ở bước hoàn tất. Nếu dùng thiết kế stateless challenge bằng signed state, vẫn phải đảm bảo chống replay, gắn ceremony/context và expiration; chữ ký của state **không tự đảm bảo single-use**.

## 8. Spring Security Servlet: tích hợp WebAuthn đúng lớp

Spring Security có hỗ trợ WebAuthn/passkeys trong các phiên bản hiện đại. **Tên DSL, endpoints, repositories và khả năng tùy chỉnh có thể khác giữa các phiên bản Spring Security**; luôn kiểm tra API trong dependency đang dùng, migration guide và bộ test của ứng dụng. Không tự viết lại validator tiền tiêu chuẩn nếu thư viện đã cung cấp cơ chế kiểm tra an toàn.

### 8.1. Định hình cấu hình đúng

Bản phác thảo Spring Security 6.4+ dưới đây biểu thị các ý chính trong `SecurityFilterChain`, dùng WebAuthn configurer có `rpId` và `allowedOrigins`. Đây là **đoạn cấu hình trong ứng dụng Spring Boot** (có Spring Security version hỗ trợ WebAuthn), không phải một chương trình Java độc lập:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebAuthnSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .webAuthn(webAuthn -> webAuthn
                .rpId("example.com")
                .allowedOrigins("https://login.example.com"));

        return http.build();
    }
}
```

Các điểm cần đọc đúng:
1. **`rpId("example.com")`** là RP ID dạng domain, không có scheme/port.
2. **`allowedOrigins("https://login.example.com")`** là danh sách origin website được server chấp nhận cho WebAuthn ceremonies, không phải CORS allowlist tự động cho mọi request.
3. Authentication flow, trang login, endpoints bắt đầu/kết thúc ceremony, cách lưu credential/user handle và UI đăng ký phải được cấu hình thêm đúng theo module/API phiên bản đang dùng. **Đừng xem đoạn trên là một ứng dụng passkey hoàn chỉnh**.
4. Không tắt CSRF toàn cục vì “đã có WebAuthn”. Browser vẫn có thể duy trì session cookie sau khi WebAuthn đăng nhập; các POST/PATCH/DELETE khác cần CSRF protection phù hợp.
5. Không mở `permitAll` cho mọi API quản lý credential. **Thêm credential** và **xóa credential** là thao tác account-sensitive, phải yêu cầu user đã xác thực, và thường nên yêu cầu xác thực lại (step-up/recent authentication).

Một lớp config đúng không thay việc thiết kế storage và verifier. Trong nhiều triển khai Spring Security, nhà phát triển phải cung cấp repository lưu user/credential (hoặc dùng JDBC implementation phù hợp). Đọc chính xác giao diện repository, schema và phương thức cấu hình của **version** trước khi đặt tên bean/bảng thực tế.

### 8.2. Quản trị RP ID và allowed origins theo môi trường

Ví dụ một chiến lược có thể kiểm tra được:

| Môi trường | RP ID | Allowed origins | Ghi chú |
| --- | --- | --- | --- |
| Production | `example.com` | `https://login.example.com` | Domain/HTTPS thật, chỉ origin đăng nhập đáng tin |
| Staging | `staging.example.com` | `https://login.staging.example.com` | Không dùng chung credential scope không cần thiết với production |
| Local dev | `localhost` khi được browser/library hỗ trợ | `http://localhost:8080` | Ngoại lệ secure-context localhost chỉ dành cho dev |
| Multi-origin có chủ đích | `example.com` | `https://login.example.com`, `https://account.example.com` | Chỉ nếu cả hai origin được vận hành và bảo vệ ở cùng mức tin cậy |

Nếu muốn đổi RP ID từ `login.example.com` sang `example.com`, **credential cũ không tự đổi scope**. Người dùng có thể phải đăng ký credential mới hoặc thực hiện kế hoạch migration đúng đặc tả/cơ chế cho phép. Đừng đổi cấu hình production mà chưa chuẩn bị phương án cho các credential đã tồn tại.

### 8.3. Browser API và JSON conversion

Browser dùng hai WebAuthn operations:

```javascript
// Đăng ký (sau khi fetch options từ server):
const creationOptions =
    PublicKeyCredential.parseCreationOptionsFromJSON(optionsJson);
const credential = await navigator.credentials.create({
  publicKey: creationOptions
});
// Gửi credential.toJSON() về endpoint hoàn tất đăng ký.

// Đăng nhập (sau khi fetch options từ server):
const requestOptions =
    PublicKeyCredential.parseRequestOptionsFromJSON(requestOptionsJson);
const assertion = await navigator.credentials.get({
  publicKey: requestOptions
});
// Gửi assertion.toJSON() về endpoint hoàn tất xác thực.
```

Đây là **mã mô tả workflow**, với `optionsJson`/`requestOptionsJson` do backend trả trong bước trước; không phải file chạy độc lập. Các helper JSON hiện đại và `toJSON()` cần được **feature-detect** theo trình duyệt; nếu chưa hỗ trợ, phải chuyển các trường nhị phân base64url ↔ `ArrayBuffer` đúng cách. Không gửi trực tiếp string JSON làm `challenge` của WebAuthn API mà bỏ chuyển đổi bytes.

Client JavaScript chỉ điều phối browser. **Server mới là nơi quyết định ceremony có hợp lệ hay không**, sau khi kiểm tra challenge, RP ID, origin, các flags, signature và tài khoản. Không nên cho frontend lựa chọn RP ID, origin allowlist hoặc “đã verify” rồi server tin vào boolean client trả.

## 9. Kiểm soát phiên, CSRF và quản lý credential

WebAuthn tự bảo vệ việc tạo assertion bằng challenge và origin binding, nhưng hệ thống account vẫn có nhiều bề mặt cần bảo vệ.

### 9.1. Đăng ký credential là thao tác nhạy cảm

Nếu attacker gắn được credential của họ vào tài khoản nạn nhân, họ có thể đăng nhập về sau. Vì vậy endpoint “add passkey” nên:
- Yêu cầu user đã đăng nhập đúng tài khoản, có CSRF protection khi dùng cookie/session.
- Cân nhắc **recent authentication/step-up** trước khi thêm hoặc xóa passkey.
- Ràng buộc challenge với account và ceremony đang đăng ký.
- Không cho client tự khai báo `user_id` khác với account của session rồi persist.
- Gửi thông báo bảo mật và lưu audit record khi có credential mới hoặc bị gỡ.
- Có cách hủy credential bị mất/đánh cắp, đồng thời tránh khóa tài khoản khi người dùng mất thiết bị cuối cùng.

### 9.2. Login WebAuthn và session cookie

Sau assertion hợp lệ, Spring Security thường thiết lập authentication và có thể tạo phiên đăng nhập thông qua session cookie theo kiến trúc ứng dụng. Khi đó:
- Session cookie cần `Secure`, `HttpOnly`, `SameSite` phù hợp và chính sách session fixation/logout.
- Các endpoint thay đổi dữ liệu vẫn cần chống CSRF khi browser tự gửi cookie.
- Không lấy WebAuthn challenge làm token CSRF dùng lại cho toàn bộ ứng dụng.
- Không đưa credential ID, challenge hoặc raw authenticator response vào URL.
- Rate limit bắt đầu/hoàn tất ceremony và thao tác quản lý credential; hạn chế account enumeration bằng lỗi/response phù hợp.

### 9.3. Phân biệt “phishing-resistant” với “không bao giờ bị tấn công”

WebAuthn giảm nguy cơ phishing kiểu thu mật khẩu và TOTP nhập vào website giả vì khóa được ràng buộc với RP ID. Tuy nhiên XSS trên đúng origin, session cookie bị chiếm, extension độc hại, tài khoản khôi phục yếu hoặc credential quản trị không an toàn vẫn có thể gây mất tài khoản. Bảo vệ origin, session, recovery, domain management và supply chain là các phần không thể bỏ qua.

## 10. Kiểm thử và QA thiết kế

### 10.1. Ma trận test RP ID/origin

| Test | Kỳ vọng |
| --- | --- |
| `https://login.example.com` với RP ID `example.com` | Phù hợp theo quan hệ domain; origin phải có trong allowlist |
| `https://evil-example.com` với RP ID `example.com` | Không hợp lệ theo quan hệ RP ID |
| `https://login.example.com:8443` khi chỉ allow `https://login.example.com` | Origin khác do port, phải từ chối |
| `http://login.example.com` khi production HTTPS-only | Không được chấp nhận |
| RP ID `https://example.com` | Sai định dạng RP ID |
| Origin chưa được allow nhưng rpIdHash đúng | Server vẫn từ chối ceremony |
| `clientDataJSON.type` sai | Server từ chối |
| Challenge cũ/sai/đã consume | Server từ chối, không tạo auth |
| `authenticatorData.rpIdHash` không khớp | Server từ chối |
| Chữ ký không hợp lệ | Server từ chối |
| UV bắt buộc nhưng UV flag không có | Server từ chối |
| Credential ID đã thuộc account khác | Registration phải bị từ chối, không gán lại |
| Credential đã bị revoke | Assertion không tạo đăng nhập |
| Username-less login gửi userHandle không khớp mapping | Server từ chối |
| Counter không tăng ở passkey đồng bộ | Thực thi policy/risk handling đã thiết kế; không kết luận clone một cách máy móc |

### 10.2. API-level integration test

Trong Spring Security Servlet application, nên kiểm thử các luồng end-to-end với một thư viện WebAuthn test/vector phù hợp:

1. Đăng ký credential từ một origin hợp lệ, sau đó kiểm tra row DB có `credential_id`, public key, đúng user và RP ID; không có private key.
2. Thử hoàn tất đăng ký với `clientDataJSON.origin` khác allowlist hoặc challenge sai; không có row DB mới.
3. Đăng nhập bằng credential vừa đăng ký với challenge mới và chữ ký đúng; kiểm tra `Authentication`/session được cấp và audit `last_used_at` được cập nhật.
4. Thử replay assertion cũ; từ chối do challenge đã dùng/hết hạn.
5. Thử đổi credential ID hoặc user handle sang account khác; từ chối.
6. Đổi scheme, host hoặc port origin mà không cập nhật allowlist; từ chối.
7. Test cookie CSRF khi thêm/xóa passkey, và test rate-limit/reauth.
8. Chạy qua reverse proxy thật để đảm bảo public origin và cấu hình forwarded headers đúng, không có trust-header injection.

**Không dùng MockMvc request giả với `Authentication` đã có rồi tuyên bố đã kiểm thử WebAuthn crypto.** Test như vậy chỉ kiểm tra authorization/filter logic; phải có test riêng cho challenge, client data, authenticator data và signature verification.

### 10.3. Checklist vận hành

- [ ] Chọn RP ID theo domain thực, không có scheme/port/path, không dùng public suffix.
- [ ] Allowed origins là danh sách chính xác theo môi trường, bao gồm port khi cần, không dùng wildcard tùy tiện.
- [ ] Sản xuất dùng HTTPS/TLS hợp lệ; forwarded headers chỉ tin từ proxy đã kiểm soát.
- [ ] Registration và authentication tạo challenge bằng CSPRNG, có TTL, bound context và single-use.
- [ ] Verify `type`, challenge, `clientDataJSON.origin`, `rpIdHash`, UP/UV, signature và account mapping.
- [ ] Registration lưu credential ID/public key/user handle/counter/metadata sau khi verify thành công; **không lưu private key/PIN/biometrics**.
- [ ] Unique constraint trên credential ID theo RP, kiểm soát quyền thêm/xóa credential, hỗ trợ revoke và recovery.
- [ ] Chính sách `signCount` cân nhắc synced passkeys và backup flags, không coi counter 0 là lỗi hiển nhiên.
- [ ] Có test negative cho origin lạ, rpIdHash khác, challenge replay, signature sai, credential bị revoke và account substitution.
- [ ] Nếu login tạo session cookie, vẫn áp CSRF protection cho thao tác thay đổi dữ liệu, session hardening và logout.
- [ ] Đã thử staging/production với domain khác nhau, không “di chuyển” credential scope bằng cách sửa RP ID.
- [ ] Dùng verifier/repository tương thích với Spring Security version thực tế, không tự viết lại WebAuthn cryptography.

## 11. Lỗi phổ biến và lời giải

1. **Nhầm RP ID với origin:** đặt `rpId("https://login.example.com")`. Sửa thành domain RP ID, còn origin phải được cấu hình riêng.
2. **Chỉ kiểm rpIdHash:** bỏ qua `clientDataJSON.origin`. Sửa bằng allowlist exact origin và verify signature/challenge.
3. **Dùng wildcard theo đuôi không có dấu chấm:** `endsWith("example.com")` có thể chấp nhận `evil-example.com`. Dùng thư viện chuẩn và allowlist origin rõ ràng.
4. **Bỏ qua port:** `https://login.example.com:8443` không cùng origin với bản HTTPS cổng mặc định.
5. **Dùng HTTP trên domain production:** secure context/transport không đạt; phải phục vụ HTTPS.
6. **Cấu hình RP ID dựa vào Host header từ client:** có thể bị header spoofing, nhất là sau proxy. Đọc từ cấu hình tin cậy.
7. **Lưu private key ở backend:** sai mô hình WebAuthn. Backend lưu public-key credential, không yêu cầu private key.
8. **Lưu challenge làm credential lâu dài:** nhầm dữ liệu ngắn hạn với thông tin xác thực đã đăng ký; challenge phải single-use và hết hạn.
9. **Quên kiểm tra chữ ký trên bytes gốc:** parse/serialize lại `clientDataJSON` trước khi hash có thể sai và tạo logic verification yếu.
10. **Tin userHandle do browser gửi:** phải đối chiếu credential ID và mapping tài khoản từ DB.
11. **Xử lý mọi signCount bằng quy tắc tăng tuyệt đối:** synced passkeys có thể không có counter hữu dụng; dùng policy/risk handling phù hợp.
12. **Coi WebAuthn thay CSRF:** nếu login tạo cookie session, thao tác account vẫn phải chống CSRF.
13. **Chuyển domain/RP ID rồi cho rằng passkeys cũ vẫn hoạt động:** scope là thuộc tính ràng buộc, cần migration có kế hoạch.
14. **Cho phép đăng ký passkey từ request ẩn danh cho account tùy chọn:** có thể dẫn đến account takeover; registration phải buộc vào người dùng và quyền phù hợp.
15. **Coi test “user đã đăng nhập” là test WebAuthn:** thiếu kiểm tra challenge/origin/rpIdHash/signature thực.

**Tóm tắt:** RP ID trả lời “credential thuộc phạm vi domain nào”; origin trả lời “trang web nào đã gọi WebAuthn”; HTTPS bảo đảm secure context và đường truyền; credential store giữ **credential ID + public key + ràng buộc account + metadata**, không giữ private key. Một WebAuthn ceremony chỉ thành công sau khi server đã xác minh **challenge, origin, RP ID hash, chữ ký và chính sách người dùng**. Trong Spring Security Servlet, hãy dùng tích hợp WebAuthn phù hợp phiên bản, lưu credential bền vững và kiểm thử cả luồng bảo mật qua proxy/browser.

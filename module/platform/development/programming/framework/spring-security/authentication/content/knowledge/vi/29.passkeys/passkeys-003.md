# Passkey: luồng đăng ký credential khác với luồng xác thực bằng assertion

## 1. Bức tranh tổng quan

Passkey dùng công nghệ WebAuthn/FIDO2, cho phép Relying Party (RP, ứng dụng web) xác thực người dùng bằng mật mã khóa công khai. Ứng dụng không cần nhận password hay private key của passkey. Người dùng có thể mở khóa passkey bằng PIN, sinh trắc học hoặc cơ chế xác minh của authenticator.

**WebAuthn có hai ceremony khác nhau, không thể hoán đổi:**

- **Registration / credential creation:** Browser gọi `navigator.credentials.create()`; authenticator tạo credential mới và cặp khóa. Server kiểm chứng phản hồi đăng ký, rồi lưu **credential ID + public key + liên kết với tài khoản**.
- **Authentication / assertion:** Browser gọi `navigator.credentials.get()`; authenticator dùng **private key đã có** để ký một thử thách mới. Server kiểm chứng chữ ký bằng **public key đã lưu khi đăng ký**, sau đó xác thực tài khoản.

> **Đăng ký là cấp và liên kết một phương thức đăng nhập mới. Assertion là dùng phương thức đã đăng ký để chứng minh quyền sử dụng credential.** Thành công ở `create()` chưa phải đăng nhập; thành công ở `get()` cũng chưa phải đăng nhập cho đến khi server xác minh assertion.

Mục tiêu của bài học:
1. Hiểu điểm chung và khác nhau giữa registration challenge và authentication challenge.
2. Phân biệt `attestationObject` trong đăng ký với `authenticatorData + signature` trong assertion.
3. Nắm bộ kiểm tra WebAuthn tại server: `challenge`, `type`, `origin`, `rpIdHash`, UP/UV, attestation/credential data hoặc signature.
4. Triển khai cấu hình Spring Security 6.5 dùng Java 17+ cho cả hai luồng, hiểu state và persistence.
5. Kiểm thử account linking, replay, chống phishing, dữ liệu credential và session.

## 2. Thành phần và thuật ngữ

| Thành phần / dữ liệu | Ý nghĩa |
|---|---|
| **Relying Party (RP)** | Server ứng dụng sở hữu tài khoản, tạo challenge/options và kiểm tra kết quả |
| **Browser / WebAuthn client** | User agent chạy `navigator.credentials.create/get`, cung cấp thông tin `origin` |
| **Authenticator** | Thiết bị, nền tảng hoặc passkey provider tạo/giữ private key và thực hiện ký |
| **Credential ID** | Giá trị nhị phân định danh một credential để server lookup |
| **Public key** | Server lưu sau khi đăng ký và dùng để kiểm tra chữ ký login |
| **Private key** | Không chuyển đến RP; passkey provider bảo vệ và có thể đồng bộ trong mô hình multi-device |
| **RP ID** | Domain, ví dụ `example.com`, được băm vào authenticator data |
| **Origin** | Scheme + hostname + port của trang, ví dụ `https://login.example.com` |
| **Challenge** | Byte sequence ngẫu nhiên, mới cho một ceremony; ngăn replay |
| **user.id / userHandle** | Định danh opaque ổn định của tài khoản trong RP, không nhất thiết là username/email |
| **Attestation** | Dữ liệu về credential mới và, nếu policy yêu cầu, thông tin nguồn gốc authenticator |
| **Assertion** | Dữ liệu chứng minh private key đã ký thử thách và ngữ cảnh phiên xác thực |
| **UP** | User Presence: authenticator thấy dấu hiệu người dùng hiện diện |
| **UV** | User Verification: authenticator xác minh người dùng theo cơ chế như PIN/sinh trắc học |

Một passkey đồng bộ có thể sử dụng được trên nhiều thiết bị. Không được mặc định “private key luôn bị khóa cứng trong đúng một máy”; tuy nhiên private key **không được gửi tới server RP** trong registration hay authentication.

### Hai phép kiểm tra khác nhau

~~~text
REGISTRATION:
  create() → authenticator tạo key pair
  → trả credential ID + attestation object
  → RP xác minh rồi LƯU PUBLIC KEY MỚI

AUTHENTICATION:
  get() → authenticator dùng PRIVATE KEY ĐÃ CÓ ký challenge
  → trả authenticatorData + clientDataJSON + signature
  → RP LOOKUP PUBLIC KEY ĐÃ LƯU và verify chữ ký
~~~

**Credential ID không phải password:** biết credential ID không đủ để tạo assertion hợp lệ. **Chữ ký registration/attestation cũng không phải chữ ký authentication**; attestation có ý nghĩa riêng đối với việc kiểm chứng nguồn gốc và thuộc tính credential lúc tạo.

## 3. Bảng so sánh registration và authentication

| Tiêu chí | Registration | Authentication |
|---|---|---|
| Mục đích | Liên kết credential mới vào tài khoản | Xác minh credential đã liên kết |
| API trên browser | `navigator.credentials.create` | `navigator.credentials.get` |
| Options | `PublicKeyCredentialCreationOptions` | `PublicKeyCredentialRequestOptions` |
| User | RP phải biết tài khoản được phép thêm passkey | RP tìm account theo credential ID/userHandle đã kiểm tra |
| Khóa mật mã | Authenticator tạo cặp public/private key | Sử dụng private key của credential đã tồn tại |
| `clientDataJSON.type` | `webauthn.create` | `webauthn.get` |
| Response subtype | `AuthenticatorAttestationResponse` | `AuthenticatorAssertionResponse` |
| Trường chính | `attestationObject`, `clientDataJSON` | `authenticatorData`, `clientDataJSON`, `signature`, có thể `userHandle` |
| Xác minh server | Challenge, RP ID, origin, flags, credential structure, attestation policy | Challenge, RP ID, origin, flags, user binding, **signature bằng stored public key** |
| Kết quả sau khi thành công | Ghi bản ghi credential, không tự tạo phiên đăng nhập mới | Xác thực người dùng, tạo/cập nhật Authentication/session |
| Rủi ro nổi bật | Attacker lén gắn passkey của mình vào tài khoản nạn nhân | Replay, dùng credential sai account, bỏ xác minh chữ ký |

Hai luồng đều cần **server-generated challenge**, nhưng không dùng chung challenge hoặc cùng kiểu response. Một browser response cho `webauthn.create` không được nhận ở endpoint `webauthn.get`.

## 4. Luồng registration: tạo và liên kết credential mới

Giả định Alice đang đăng nhập bằng phương pháp hiện có và bấm **Thêm passkey**. Nếu là account signup passkey-first, ứng dụng cần một quy trình chứng minh quyền tạo tài khoản và liên kết được bảo vệ riêng, không cho người lạ chỉ nhập email Alice là thêm key vào account đó.

~~~text
Alice/browser                       RP server                    Authenticator
     |                                 |                               |
     | POST /webauthn/register/options |                               |
     |-------------------------------->| xác định account Alice        |
     |                                 | sinh challenge C1              |
     |                                 | lưu state C1 + account         |
     |<--------------------------------| trả creation options           |
     | navigator.credentials.create()  |                               |
     |---------------------------------------------------------------->|
     |                                 |              tạo cặp key mới   |
     |                                 |              UP/UV theo policy |
     |<----------------------------------------------------------------|
     | nhận attestation response        |                               |
     | POST /webauthn/register          |                               |
     |-------------------------------->| verify create/C1/origin/RP ID |
     |                                 | trích xuất credential/public  |
     |                                 | lưu liên kết với Alice         |
     |<--------------------------------| thành công                     |
~~~

### R1. Server trả creation options

Ví dụ JSON mô tả cấu trúc của options (challenge, user ID là dữ liệu ví dụ, không dùng lại khi vận hành):

~~~json
{
  "rp": {"id": "example.com", "name": "Learning App"},
  "user": {
    "id": "dXNlcjQy",
    "name": "alice@example.com",
    "displayName": "Alice"
  },
  "challenge": "FJ9YpeCb1MR7COoaX84e00veXBxSXd6Z_8V-9yYGkd8",
  "pubKeyCredParams": [
    {"type": "public-key", "alg": -7},
    {"type": "public-key", "alg": -8}
  ],
  "timeout": 300000,
  "excludeCredentials": [],
  "authenticatorSelection": {
    "residentKey": "preferred",
    "userVerification": "required"
  },
  "attestation": "none"
}
~~~

- `rp.id`: domain RP; không phải URL có scheme/port. Ví dụ `example.com` có thể được dùng bởi origin `https://login.example.com` theo quy tắc domain thích hợp.
- `user.id`: ID opaque ổn định do server cấp cho Alice. Không coi `user.name`/email là khóa mật mã.
- `challenge`: phải sinh bằng CSPRNG, lưu với ceremony/account/session và TTL; đủ entropy, mới cho mỗi request.
- `pubKeyCredParams`: danh sách thuật toán được chấp nhận; `-7` là ES256, `-8` là EdDSA theo COSE.
- `excludeCredentials`: IDs đã đăng ký có thể giúp tránh lặp trên authenticator; server vẫn phải tự enforce uniqueness.
- `residentKey`: liên quan discoverable credential và trải nghiệm login không cần nhập username.
- `userVerification`: mức yêu cầu như `required` hoặc `preferred`. Server phải kiểm tra flags thực tế; gửi options chưa đủ.
- `attestation: none`: RP không yêu cầu chứng minh nguồn gốc thiết bị qua chứng chỉ attestation; không có nghĩa bỏ kiểm tra đăng ký.

### R2. Browser gọi create

Browser chuyển các trường nhị phân `challenge`, `user.id`, `excludeCredentials[].id` từ Base64URL JSON về `ArrayBuffer`, sau đó:

~~~javascript
const credential = await navigator.credentials.create({
  publicKey: creationOptions
});
~~~

Đây là một lệnh của **browser JavaScript**, không phải Java. `creationOptions` phải được lấy trực tiếp từ RP và decode đúng các trường byte. WebAuthn chỉ có thể chạy trong secure context; website thật dùng HTTPS, `http://localhost` là ngoại lệ local development mà browser hỗ trợ.

Authenticator tạo key pair và credential ID gắn với RP ID, kiểm tra user presence/verification theo thiết bị và policy. **Private key không xuất hiện trong `credential.response`.**

### R3. Browser gửi attestation response

Hình dạng dữ liệu sau khi encode các trường nhị phân thành Base64URL:

~~~json
{
  "id": "dYF7EGnRFFIXkpXi9XU2wg",
  "rawId": "dYF7EGnRFFIXkpXi9XU2wg",
  "type": "public-key",
  "response": {
    "clientDataJSON": "eyJ0eXBlIjoid2ViYXV0aG4uY3JlYXRlIn0",
    "attestationObject": "o2NmbXRkbm9uZWdhdHRTdG10oA"
  }
}
~~~

JSON trên chỉ thể hiện **hình dạng field**; các byte rút gọn không tạo registration hợp lệ. Dữ liệu thật được browser/authenticator trả sau khi `create()` thành công.

`clientDataJSON` sau khi decode có:
- `type = "webauthn.create"`
- `challenge` bằng đúng giá trị C1 server phát hành
- `origin` chính xác của trang web
- `crossOrigin` và có thể `topOrigin`, dùng theo chính sách cross-origin

`attestationObject` là dữ liệu CBOR gồm `fmt`, `authData`, `attStmt`. `authData` chứa `rpIdHash`, flags, signature counter và **attested credential data**: AAGUID, credential ID và credential public key dưới dạng COSE.

### R4. Server kiểm chứng registration trước khi lưu

RP phải hoàn thành các kiểm tra sau:

1. **Quyền liên kết:** request thuộc tài khoản Alice **đã được xác thực và cho phép đăng ký**. Không dựa vào trường `user.id` hoặc email do client tự điền để chọn account đích.
2. **Ceremony state:** tìm challenge C1 đã tạo, đúng session/account, chưa hết hạn và chưa được dùng.
3. **Client type:** `clientDataJSON.type` phải là `webauthn.create`; challenge phải khớp.
4. **Origin:** so khớp với allowlist chính xác và kiểm tra `crossOrigin/topOrigin` nếu áp dụng.
5. **RP ID hash:** `rpIdHash == SHA-256(expectedRpId)`.
6. **UP/UV:** thực thi đúng chính sách user presence/verification; kiểm tra thuật toán cho phép và dữ liệu credential.
7. **Attestation:** xử lý statement/trust path theo format/policy. Nếu `none`, không yêu cầu chứng chỉ nhà sản xuất nhưng các kiểm tra registration khác vẫn là bắt buộc.
8. **Lưu trữ:** kiểm tra credential ID duy nhất và không liên kết bất hợp pháp tới user khác; chỉ sau khi thành công lưu **credential ID, public key, account ID, metadata** và tiêu thụ challenge.

**Browser `create()` thành công khác server registration thành công.** UI chỉ báo “Đã thêm passkey” sau khi RP chấp nhận và lưu credential, không phải khi thiết bị vừa trả attestation.

## 5. Attestation và public key có ý nghĩa gì?

**Attestation** liên quan đến việc ghi nhận/kiểm chứng đặc điểm hoặc nguồn gốc authenticator **lúc credential được tạo**, tùy chính sách RP. Nó có thể:
- có format `none`, không đưa bằng chứng nguồn gốc thiết bị;
- dùng self attestation hoặc attestation statement/trust chain được chấp nhận;
- hỗ trợ policy thiết bị/enterprise trong hệ thống yêu cầu cao, với đánh đổi quyền riêng tư và tương thích.

**Không có yêu cầu mọi passkey consumer phải kèm chứng chỉ sản xuất được RP tin.** Với `attestation=none`, RP vẫn xác minh challenge, origin, rpIdHash, flags, credential structure và lưu public key hợp lệ.

Registration thông thường không xác thực user bằng chữ ký của credential **đã đăng ký từ trước**; nó tạo/ghi credential mới. Vì vậy bước bảo vệ account trước khi thêm credential là tối quan trọng. Nếu attacker gắn passkey của họ vào account Alice, lần sau attacker có thể đăng nhập như Alice bằng **credential được server lưu**.

## 6. Luồng authentication: xác thực bằng assertion

Sau registration, RP đã lưu credential ID + public key. Trong lần login tiếp theo, server phát hành **challenge mới C2** và sử dụng khóa công khai đó để verify.

~~~text
Alice/browser                      RP server                  Authenticator
     |                                |                              |
     | POST /webauthn/authenticate/   |                              |
     | options                        |                              |
     |------------------------------->| tạo challenge C2             |
     |<-------------------------------| trả request options          |
     | navigator.credentials.get()    |                              |
     |-------------------------------------------------------------->|
     |                                |             chọn credential   |
     |                                |             UP/UV, ký C2      |
     |<--------------------------------------------------------------|
     | nhận assertion response        |                              |
     | POST /login/webauthn           |                              |
     |------------------------------->| lookup credential ID         |
     |                                | verify C2, origin, rpIdHash  |
     |                                | verify signature/public key  |
     |                                | kiểm tra account/role        |
     |<-------------------------------| auth success + session      |
~~~

### A1. Server trả request options

~~~json
{
  "challenge": "mx_wD_MxCWQAP5gpGj8dqnlT7G2HxWBZxAunYADAgT0",
  "timeout": 300000,
  "rpId": "example.com",
  "allowCredentials": [],
  "userVerification": "required"
}
~~~

- `challenge` C2 mới và **khác C1**; không được tái sử dụng giữa các login hoặc các session.
- `rpId` vẫn phải khớp domain credential.
- `allowCredentials` có thể là danh sách credential IDs cho username đã biết. Khi trống, browser có thể chọn discoverable credential phù hợp; server **vẫn phải xác minh ID, key và account mapping**.
- `userVerification` được kiểm tra lại từ authenticator flags, không chỉ dựa vào UI browser.

### A2. Browser gọi get

~~~javascript
const assertion = await navigator.credentials.get({
  publicKey: requestOptions
});
~~~

`requestOptions.challenge` và `allowCredentials[].id` nếu có là `ArrayBuffer` đã được decode từ Base64URL. Authenticator chọn credential tương ứng với RP ID và ký **challenge/ngữ cảnh hiện tại** bằng private key đã có. **Không tạo cặp khóa mới.**

### A3. Browser gửi assertion

~~~json
{
  "id": "dYF7EGnRFFIXkpXi9XU2wg",
  "rawId": "dYF7EGnRFFIXkpXi9XU2wg",
  "type": "public-key",
  "response": {
    "clientDataJSON": "eyJ0eXBlIjoid2ViYXV0aG4uLmdldCJ9",
    "authenticatorData": "y9GqwTRaMpzVDbXq1dyEAXVOxrou08k22ggRC45MKNgdAAAAAA",
    "signature": "MEUCIQDBylREhLzAQ_QMXqly7sZjotCP6mMde0bo-4KbK0zaIQ",
    "userHandle": null
  }
}
~~~

Các byte trong ví dụ không tạo assertion hợp lệ; tên field và cấu trúc mới là nội dung cần nhớ. `userHandle` có thể null trong một số luồng. Khi có `userHandle`, RP phải đối chiếu với account được liên kết, không xem đó là chứng cứ độc lập bỏ qua signature.

`clientDataJSON.type = "webauthn.get"`. Trong assertion có **`authenticatorData` và `signature` tách rời**; không có public key mới được tin từ phía client. Đây là dấu hiệu dễ nhận nhất để phân biệt với registration.

## 7. Server kiểm chứng assertion bằng public key đã lưu

Ở mức khái niệm, authenticator ký:

~~~text
clientDataHash = SHA-256(clientDataJSON)
signedBytes = authenticatorData || clientDataHash
signature = Sign(credentialPrivateKey, signedBytes)

RP:
  credential = lookup(credentialId)
  Verify(credential.storedPublicKey, signedBytes, signature)
~~~

Dấu `||` là phép nối byte. Đây chỉ là mô hình giải thích; thuật toán ký cụ thể do COSE key/algorithm và WebAuthn verifier xử lý. **Không tự xây parser CBOR hoặc bộ kiểm chứng mật mã WebAuthn** thay cho thư viện đã được kiểm thử.

Các điều kiện cần xác minh cùng chữ ký:

1. Credential ID tồn tại, chưa revoked, đúng account (nếu đã biết username), thuộc RP/tenant phù hợp.
2. Challenge C2 chính xác, chưa hết hạn/chưa sử dụng, liên kết với ceremony/session.
3. `clientDataJSON.type == "webauthn.get"`.
4. `origin` phù hợp allowlist; kiểm tra `crossOrigin/topOrigin` theo chính sách.
5. `authenticatorData.rpIdHash` là SHA-256 của expected RP ID.
6. UP/UV được chấp nhận; nếu policy yêu cầu UV mà authenticator chỉ có UP, phải từ chối.
7. `signature` hợp lệ với **public key đã lưu từ registration**.
8. Nếu có `userHandle`, account mapping phù hợp; account vẫn active, không bị hạn chế.
9. Kiểm tra/cập nhật signature counter và các backup flags theo policy; tiêu thụ challenge để chống replay.
10. Tạo Spring Security `Authentication`/session và kiểm tra authorization domain, **không tự nâng quyền chỉ vì login bằng passkey**.

### Vì sao challenge là điều kiện chống replay?

Nếu attacker có một assertion trước đó, chữ ký của nó được tạo cho **challenge trước**. Ở lần login mới server phải cấp challenge mới và từ chối assertion cũ. Nếu server bỏ kiểm tra challenge, dùng state global chung hoặc chấp nhận challenge đã hết hạn, thì chữ ký đúng có thể không đủ bảo vệ replay.

### `signCount` và passkey đồng bộ

Một số authenticator có counter, một số luôn trả `0`. Passkey đồng bộ giữa thiết bị có thể không có counter tăng tuyến tính. Giá trị bất thường là **tín hiệu đánh giá rủi ro** chứ không phải bằng chứng clone tuyệt đối. Cần xem backup eligibility/state, loại authenticator và chính sách WebAuthn, tránh từ chối mọi passkey vì counter không tăng.

## 8. Điểm kiểm tra bảo mật chung nhưng khác kết quả

| Kiểm tra | Registration | Authentication |
|---|---|---|
| Challenge mới | Gắn với **account đang thêm key** | Gắn với **login attempt** |
| Type trong clientDataJSON | `webauthn.create` | `webauthn.get` |
| Origin | Bắt buộc đối chiếu | Bắt buộc đối chiếu |
| RP ID hash | Bắt buộc đối chiếu | Bắt buộc đối chiếu |
| User Presence / Verification | Theo policy enrollment | Theo policy đăng nhập |
| Public key | Trích xuất và lưu sau verification | Lấy từ DB đã đăng ký |
| Attestation trust | Theo policy tạo credential | Không thay chữ ký login |
| Signature login | Không phải bước chính ở đây | **Bắt buộc verify** |
| Account | Xác minh **ai được gắn credential** | Xác minh **credential thuộc ai** |
| Kết quả | Thêm credential record | Tạo Authentication và session |

**Không dùng email, displayName hoặc user.id do client gửi để gắn credential vào account khác.** Registration là thao tác quản trị phương thức đăng nhập; phải yêu cầu tài khoản được xác minh hoặc quy trình bootstrap được bảo vệ, có CSRF và cân nhắc step-up.

## 9. Ví dụ Spring Boot 3.x + Spring Security 6.5 + Java 17

Spring Security 6.4/6.5 có cấu hình WebAuthn trong Servlet DSL. Ở dòng 6.5, tài liệu yêu cầu thêm `webauthn4j-core` bên cạnh Spring Security web; **không dùng cách thêm `spring-security-webauthn` của dòng 7.x cho project này**.

Ví dụ tạo ứng dụng demo gồm password login ban đầu để Alice đăng ký passkey, sau đó login bằng passkey. Mã nguồn Java bên dưới là file của một **project Maven Spring Boot hoàn chỉnh**, không chạy độc lập bằng `javac` thiếu Spring dependencies.

### 9.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
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

`spring-boot-starter-security` kéo theo `spring-security-web`. Version thư viện WebAuthn4J ở đây tương ứng với ví dụ tài liệu Spring Security 6.5. Khi nâng lên Spring Security 7 cần đối chiếu lại dependency, không trộn API của các nhánh phiên bản.

### 9.2. File cấu hình ứng dụng

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

demo:
  user:
    password: ${DEMO_USER_PASSWORD}
~~~

Password lấy từ biến môi trường; không hardcode username/password thực vào source. Thiếu biến thì ứng dụng phải báo thiếu cấu hình, không tự dùng password yếu.

### 9.3. Class khởi động

File `src/main/java/com/example/passkey/PasskeyDemoApplication.java`:

~~~java
package com.example.passkey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasskeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasskeyDemoApplication.class, args);
    }
}
~~~

### 9.4. Spring Security configuration

File `src/main/java/com/example/passkey/SecurityConfiguration.java`:

~~~java
package com.example.passkey;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String password) {
        var alice = User.withUsername("alice")
                .password(encoder.encode(password))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .webAuthn(webAuthn -> webAuthn
                        .rpName("Passkey Demo")
                        .rpId("localhost")
                        .allowedOrigins("http://localhost:8080"))
                .build();
    }
}
~~~

**Điểm cần hiểu:**
- `.formLogin(...)` cho Alice đăng nhập lần đầu bằng password demo. Chỉ user đã xác thực mới được thêm credential vào tài khoản đó qua registration flow.
- `.webAuthn(...)` bật passkey registration và authentication theo Spring Security; không phải tự viết lớp xác minh chữ ký.
- `.anyRequest().authenticated()` bảo vệ tài nguyên; login và các entry points do bộ lọc Spring Security quản lý theo cấu hình này.
- `.rpId("localhost")` là RP ID cho **local development**. Browser cho phép `http://localhost` làm secure context đặc biệt; production phải dùng HTTPS cùng domain RP/allowed origin thích hợp.
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` mã hóa password trong demo; không dùng `{noop}` để lưu mật khẩu production.
- Không vô hiệu hóa CSRF: Spring Security dùng request POST cho các bước tạo/tiêu thụ challenge, cần CSRF token phù hợp.
- User và WebAuthn credentials **mặc định ở bộ nhớ**, nên demo không phù hợp production hoặc cluster.

### 9.5. Endpoint xem trạng thái sau login

File `src/main/java/com/example/passkey/ProfileController.java`:

~~~java
package com.example.passkey;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    @GetMapping("/me")
    public Map<String, Object> profile(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authenticated", authentication.isAuthenticated());
    }
}
~~~

Khi Alice đăng nhập hợp lệ bằng password hoặc passkey và gọi `GET /me`, dự kiến nhận JSON gồm `username: "alice"` và `authenticated: true`. Thứ tự khóa JSON không được bảo đảm. Endpoint không trả credential ID, khóa riêng hay chi tiết phiên.

### 9.6. Chạy thử

Từ thư mục project, với Java 17+ và Maven:

~~~bash
export DEMO_USER_PASSWORD='local-demo-password'
mvn spring-boot:run
~~~

Windows PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "local-demo-password"
mvn spring-boot:run
~~~

Giá trị password chỉ dành cho môi trường localhost, không sử dụng ở môi trường có thể truy cập từ bên ngoài.

Các bước trong browser hỗ trợ WebAuthn:
1. Mở `http://localhost:8080/login`; đăng nhập `alice` với password demo.
2. Truy cập `http://localhost:8080/webauthn/register`; Spring Security cung cấp trang đăng ký credential. Thực hiện tạo passkey bằng PIN/sinh trắc học hoặc security key.
3. Spring nhận attestation và lưu credential ID + public key cho Alice sau khi xác minh.
4. Logout. Quay lại trang login và chọn phương thức đăng nhập bằng passkey được cung cấp.
5. Browser tạo assertion với credential cũ; Spring kiểm tra challenge, origin, RP ID và signature, sau đó tạo authentication.
6. Truy cập `/me` và xem user Alice.

**Không dùng `curl` gửi một JSON tự tạo để thay authenticator**, vì không có chữ ký hợp lệ. Nếu browser không cho dùng `localhost` với môi trường cụ thể, thiết lập hostname và HTTPS phù hợp; không tắt origin validation chỉ để demo chạy.

## 10. Endpoint Spring Security 6.5: tách đúng hai ceremony

Tài liệu Spring Security 6.5 mô tả:

| Hành động | Method + path | Kết quả |
|---|---|---|
| Xin creation options | `POST /webauthn/register/options` | Challenge và options gắn với user đã xác thực |
| Gửi attestation | `POST /webauthn/register` | Đăng ký credential, trả kết quả sau verification |
| Xin authentication options | `POST /webauthn/authenticate/options` | Challenge mới cho login |
| Gửi assertion | `POST /login/webauthn` | Kiểm chứng chữ ký và hoàn tất login |

Các POST nêu trên dùng CSRF token theo cấu hình chuẩn, cùng cookie/session phù hợp. Cả `/webauthn/register/options` và `/webauthn/authenticate/options` thay đổi server-side challenge state nên không chỉ là GET tĩnh.

Trong Spring 6.5, request đăng ký được mô tả dạng JSON **`publicKey.credential`**, trong khi login assertion gửi `id`, `rawId`, `response` trực tiếp:

~~~text
Registration request:
  POST /webauthn/register
  publicKey.credential.response.attestationObject
  publicKey.credential.response.clientDataJSON
  publicKey.credential.id
  publicKey.label

Authentication request:
  POST /login/webauthn
  id, rawId, type
  response.authenticatorData
  response.clientDataJSON
  response.signature
  response.userHandle (nếu có)
~~~

Đừng tự nhận `/webauthn/register` là login endpoint hoặc trộn response body của hai loại. Trang default registration/login của Spring là tham chiếu thuận tiện để xây frontend tùy biến.

## 11. Browser JavaScript: nhị phân và payload có gì khác?

Browser WebAuthn API nhận `ArrayBuffer` cho `challenge`, registration `user.id`, `excludeCredentials[].id` và authentication `allowCredentials[].id`; JSON từ server thường mang Base64URL. Các hàm hỗ trợ minh họa:

~~~javascript
function fromBase64Url(s) {
  const base64 = s.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), c => c.charCodeAt(0)).buffer;
}

function toBase64Url(buffer) {
  const bytes = new Uint8Array(buffer);
  let value = "";
  for (const n of bytes) value += String.fromCharCode(n);
  return btoa(value).replace(/\+/g, "-").replace(/\//g, "_")
      .replace(/=+$/g, "");
}

function decodeCreationOptions(json) {
  return {
    ...json,
    challenge: fromBase64Url(json.challenge),
    user: {...json.user, id: fromBase64Url(json.user.id)},
    excludeCredentials: (json.excludeCredentials ?? []).map(c => ({
      ...c, id: fromBase64Url(c.id)
    }))
  };
}

function decodeRequestOptions(json) {
  return {
    ...json,
    challenge: fromBase64Url(json.challenge),
    allowCredentials: (json.allowCredentials ?? []).map(c => ({
      ...c, id: fromBase64Url(c.id)
    }))
  };
}
~~~

Sau khi nhận options từ backend bằng `fetch` đã kèm CSRF/session và kiểm tra HTTP response:

~~~javascript
// Ceremony registration: tạo credential mới.
const created = await navigator.credentials.create({
  publicKey: decodeCreationOptions(creationOptionsJson)
});

const registrationPayload = {
  publicKey: {
    credential: {
      id: created.id,
      rawId: toBase64Url(created.rawId),
      type: created.type,
      response: {
        clientDataJSON: toBase64Url(created.response.clientDataJSON),
        attestationObject: toBase64Url(
          created.response.attestationObject),
        transports: created.response.getTransports?.() ?? []
      },
      clientExtensionResults: created.getClientExtensionResults()
    },
    label: "Laptop"
  }
};
~~~

Authentication khác ở phần payload:

~~~javascript
// Ceremony authentication: dùng credential đã đăng ký để ký.
const assertion = await navigator.credentials.get({
  publicKey: decodeRequestOptions(authenticationOptionsJson)
});

const authenticationPayload = {
  id: assertion.id,
  rawId: toBase64Url(assertion.rawId),
  type: assertion.type,
  response: {
    clientDataJSON: toBase64Url(assertion.response.clientDataJSON),
    authenticatorData: toBase64Url(
      assertion.response.authenticatorData),
    signature: toBase64Url(assertion.response.signature),
    userHandle: assertion.response.userHandle
      ? toBase64Url(assertion.response.userHandle) : null
  },
  clientExtensionResults: assertion.getClientExtensionResults()
};
~~~

Đây là code phía browser minh họa **serialization** và phân biệt hai response, không bao gồm toàn bộ trang HTML/fetch/CSRF/error UI. Khi tự triển khai giao diện, gửi `registrationPayload` đến `POST /webauthn/register` sau khi đã lấy options, và gửi `authenticationPayload` đến `POST /login/webauthn`. Chỉ đánh dấu thành công sau **phản hồi server đã xác minh**, không phải lúc `create/get` resolve.

## 12. Repository và vòng đời credential

Sau registration, RP thường lưu:
- `credential_id` (bytes, unique);
- `user_id` nội bộ hoặc WebAuthn user entity;
- `public_key_cose` (khóa công khai đã được xác minh);
- signature counter, backup flags, transports theo chính sách;
- created time, last-used time, trạng thái revoked, nhãn thân thiện.

Không lưu private key. Không dùng `email` do client gửi làm khóa account binding.

Schema **minh họa nghiệp vụ**, không phải schema bắt buộc của Spring:

~~~sql
CREATE TABLE app_passkey_credentials (
    credential_id       BYTEA PRIMARY KEY,
    user_id             VARCHAR(100) NOT NULL,
    public_key_cose     BYTEA NOT NULL,
    sign_count          BIGINT NOT NULL DEFAULT 0,
    backup_eligible     BOOLEAN,
    backed_up           BOOLEAN,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at        TIMESTAMPTZ,
    revoked_at          TIMESTAMPTZ
);
~~~

Spring Security 6.5 dùng `PublicKeyCredentialUserEntityRepository` và `UserCredentialRepository`. Default có lưu trong bộ nhớ; với JDBC có `JdbcPublicKeyCredentialUserEntityRepository` và `JdbcUserCredentialRepository`. Khi chuyển production, dùng **đúng DDL/schema Spring Security của phiên bản tương ứng**, cấu hình transaction/constraint, không giả định bảng minh họa tương thích với repository framework.

Một account có thể có **nhiều passkeys**. Cần UI xem/thêm/xóa credential được bảo vệ, reauthentication khi thêm hoặc xóa key nhạy cảm, audit, thông báo cho owner và cơ chế recovery chống account takeover. Xóa/thu hồi key phải ngăn login bằng public key đó nữa, kể cả đã đồng bộ trên thiết bị khác.

## 13. Các ranh giới tin cậy quan trọng

### 13.1. Quyền thêm passkey là quyền nhạy cảm

Registration không được mở công khai để ai cũng đăng ký credential vào `user.id` của account khác. Server phải:
- nhận diện account từ SecurityContext đã xác minh (hoặc bootstrap enrollment state đáng tin);
- kiểm soát session freshness và cân nhắc step-up;
- giữ CSRF protection;
- thông báo/audit khi passkey được thêm hoặc xóa;
- chống race/duplicate credential IDs.

Nếu attacker thêm key của mình vào account Alice, lần login sau attacker có thể tạo assertion **hoàn toàn hợp lệ** với key của họ: lỗi nằm ở **registration account binding**, không phải chữ ký assertion.

### 13.2. Origin và RP ID chống phishing nhưng phải cấu hình đúng

WebAuthn credential được gắn với RP ID/domain. Browser đưa origin vào client data. Server phải kiểm tra chính xác:
- RP ID là domain phù hợp với origin thực tế;
- `rpIdHash` trong authenticator data;
- `origin` scheme/host/port đúng allowlist;
- chính sách iframe/crossOrigin/topOrigin nếu hỗ trợ.

Dùng HTTPS trong triển khai thực. `http://localhost` chỉ là ngoại lệ phát triển. Không wildcard mọi origin để vượt lỗi reverse proxy, và không coi passkey đã chống được XSS trên **origin thật** hoặc lỗ hổng account recovery.

### 13.3. Passkey không miễn trừ authorization/session

Sau assertion hợp lệ, Spring vẫn phải xác định account active và roles, kiểm tra truy cập theo endpoint/tenant/object. Session fixation, timeout, logout và thông báo bảo mật đều cần thiết kế. Không cấp `ROLE_ADMIN` chỉ vì một user có passkey.

### 13.4. Đồng bộ và chứng thực thiết bị

Passkey có thể đồng bộ qua nhà cung cấp. `signCount` không phải bằng chứng một máy vật lý duy nhất. Nếu doanh nghiệp cần key phần cứng không đồng bộ, phải thiết kế authenticator/attestation policy cụ thể, đánh giá privacy và khả năng tương thích; không chỉ đặt `userVerification=required` là đạt device-bound credential.

## 14. Các lỗi phổ biến

1. **Lấy `navigator.credentials.create()` làm đăng nhập:** sai; nó tạo credential mới, server cần kiểm tra và lưu vào user đã được phép.
2. **Lấy `navigator.credentials.get()` làm bước tạo public key:** sai; public key đã có từ registration.
3. **Không kiểm tra `clientDataJSON.type`:** response `webauthn.create` và `webauthn.get` phải đi qua đúng verifier.
4. **Tạo challenge ở client, dùng lại challenge hoặc không kiểm tra TTL:** có thể dẫn tới replay/hỗn loạn state.
5. **Dùng user ID do client gửi để liên kết credential:** dễ bị account takeover.
6. **Không kiểm tra origin/RP ID:** suy yếu phishing resistance.
7. **Tin rawId là bằng chứng:** credential ID giúp lookup, không chứng minh private key.
8. **Không kiểm tra signature assertion:** không chứng minh được credential holder.
9. **Kiểm tra signature bằng public key vừa do request login gửi:** attacker có thể tự dựng cặp khóa; phải dùng stored public key.
10. **Bắt buộc attestation certificate với mọi passkey:** sẽ làm hỏng passkey consumer; cần policy riêng.
11. **Cho rằng `userHandle` luôn khác null:** phải hỗ trợ trường hợp thiếu/null và kiểm tra binding.
12. **Ép signCount tăng tuyến tính cho mọi passkey:** không phù hợp một số authenticator và passkey đồng bộ.
13. **Dùng WebAuthn khi origin là HTTP Internet:** browser chặn vì không phải secure context; localhost là ngoại lệ.
14. **Tắt CSRF để POST options chạy:** thay vì vậy cần gửi đúng CSRF token/cookie.
15. **Credential mất sau restart:** dùng in-memory store của demo; production cần persistent repository.
16. **Lẫn dependency Spring 6.5 và 7.x:** dùng đúng docs theo version.
17. **Trả HTTP 200 ngay khi browser get resolve:** chưa đủ; RP phải verify assertion trước khi login.

## 15. Ma trận kiểm thử hai ceremony

| Test | Registration | Authentication | Kết quả mong đợi |
|---|---|---|---|
| Luồng hợp lệ | User đã login, tạo key mới | Sign bằng private key đã liên kết | Đăng ký thành công; login thành công |
| Người lạ cố thêm key cho Alice | Không có session/step-up | Không áp dụng | Từ chối |
| Dùng challenge cũ | Replay attestation | Replay assertion | Từ chối |
| Challenge thuộc session khác | Trộn flow | Trộn flow | Từ chối |
| `clientDataJSON.type` sai | Gửi `webauthn.get` | Gửi `webauthn.create` | Từ chối |
| Origin không được phép | Sai `origin` | Sai `origin` | Từ chối |
| RP ID hash sai | Sai `rpIdHash` | Sai `rpIdHash` | Từ chối |
| Thiếu cờ UV theo policy required | Không hợp lệ | Không hợp lệ | Từ chối |
| CBOR/COSE bị hỏng | attestation invalid | Không áp dụng | Từ chối |
| Credential ID đã gắn account khác | Duplicate/cross-account | Không áp dụng | Từ chối |
| Credential ID chưa từng lưu | Không áp dụng | Unknown ID | Từ chối |
| Chữ ký bị sửa | Không áp dụng | Invalid signature | Từ chối |
| `userHandle` không khớp account | Không áp dụng | Wrong user binding | Từ chối |
| Account disabled | Không cho thêm key | Assertion đúng nhưng account bị khóa | Từ chối |
| Counter 0 hoặc key được backup | Lưu metadata | Không tăng mỗi lần | Theo risk policy hỗ trợ multi-device |
| Mất DB/memory sau restart | Key không còn | Không lookup được | Dùng persistent store |
| Không có CSRF token | Options/submit bị chặn | Options/submit bị chặn | Không cho bypass |
| Passkey login thành công nhưng không có quyền business | Không liên quan | Identity hợp lệ | Authorization vẫn 403/404 |

Test `MockMvc` chỉ giả lập `Authentication` không chứng minh thư viện đã kiểm tra chữ ký WebAuthn. Cần integration tests với fixtures/valid authenticators, negative cases challenge/origin/signature, và end-to-end trên browser secure context. Thử lại khi đổi reverse proxy, domain, browser hoặc repository.

## 16. Checklist production

- [ ] Registration gắn credential với account **server đã xác thực**, có CSRF và step-up theo rủi ro.
- [ ] Mỗi create/get ceremony sinh challenge mới CSPRNG, lưu theo session/flow, TTL và one-time use.
- [ ] Luôn xác minh đúng `webauthn.create` vs `webauthn.get`.
- [ ] Origin chính xác, RP ID và `rpIdHash` đúng domain; production dùng HTTPS.
- [ ] Registration kiểm tra attestation/credential data theo policy rồi mới lưu public key.
- [ ] Authentication lookup stored public key và kiểm tra signature, flags, credential ID, account mapping.
- [ ] Không lấy quyền business từ dữ liệu client tự khai; user status và authorization vẫn được kiểm tra.
- [ ] `userHandle` có thể null; discoverable/passkey sync được xử lý phù hợp.
- [ ] Không giả định `signCount` luôn tăng; có risk policy cho synced passkeys.
- [ ] Persistent credential store, unique constraint, backup, recovery và revoke hoạt động trên nhiều instance.
- [ ] Bảo vệ trang add/remove passkey, log an toàn, có thông báo thiết bị mới.
- [ ] Session, logout, reauthentication và account recovery không trở thành lối đi yếu hơn.
- [ ] Java/Spring Security/WebAuthn dependency cùng một dải phiên bản tương thích.
- [ ] Test âm tính cho replay, sai signature, sai origin/RP ID, quyền đăng ký và cross-account.

## 17. Kết luận

**Registration dùng `navigator.credentials.create()` để tạo và liên kết public key/credential ID mới với tài khoản; Authentication dùng `navigator.credentials.get()` để ký challenge bằng private key đã có và chứng minh khả năng sử dụng credential đó.**

Hai ceremony giống nhau ở việc cần challenge, origin, RP ID và chính sách UP/UV, nhưng khác hoàn toàn ở dữ liệu **attestationObject** so với **authenticatorData/signature**, cách tìm public key và kết quả business **lưu credential** so với **tạo phiên xác thực**. Không thể đổi tên endpoint hoặc copy payload giữa hai bước để thay thế verification.

## 18. Tài liệu tham khảo

1. [Spring Security 6.5 — Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html): dependency, cấu hình WebAuthn, persistence và hai cặp endpoint.
2. [W3C WebAuthn Level 3 — Registration](https://www.w3.org/TR/webauthn-3/#sctn-registering-a-new-credential): creation options, attestation response và verification procedure.
3. [W3C WebAuthn Level 3 — Authentication](https://www.w3.org/TR/webauthn-3/#sctn-verifying-assertion): assertion, challenge, signature, origin và flags.
4. [W3C WebAuthn Level 3 — Security Considerations](https://www.w3.org/TR/webauthn-3/#sctn-security-considerations): RP ID, phishing resistance, attestation và privacy.
5. [Spring Security 6.5 API — WebAuthnConfigurer](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/WebAuthnConfigurer.html): `rpId`, `rpName`, `allowedOrigins`.
6. [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): SecurityContext, Authentication và session.
7. [FIDO Alliance — Passkeys](https://fidoalliance.org/passkeys/): tổng quan passkeys, phương thức mở khóa, discoverable/synced credentials.

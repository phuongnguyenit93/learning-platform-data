# User presence, user verification và ý nghĩa của chính sách xác minh trong Passkey

## 1. Mục tiêu và phạm vi

Passkey dựa trên **WebAuthn/FIDO2**: ứng dụng web (Relying Party, viết tắt **RP**) lưu public key của một credential; authenticator giữ private key và tạo chữ ký cho challenge của RP khi đăng nhập. Trong mỗi phản hồi, authenticator còn đưa các **cờ trạng thái** (flags) để RP biết thao tác đã có **user presence (UP)** và/hoặc **user verification (UV)** hay chưa.

Hai câu hỏi nghe gần giống nhưng khác bản chất:

- **User presence (UP):** đã có bằng chứng về **tương tác/chủ đích sử dụng authenticator**, ví dụ chạm nút trên security key.
- **User verification (UV):** authenticator đã thực hiện **xác minh cục bộ người dùng**, ví dụ PIN, sinh trắc học, phương thức mở khóa thiết bị được authenticator chấp nhận.

Bài này làm rõ **cách đọc UP/UV**, yêu cầu `userVerification` của WebAuthn (`required`, `preferred`, `discouraged`), cách RP xác minh flags **sau khi đã kiểm tra chữ ký**, và ý nghĩa vận hành trong Spring Security. Trọng tâm là Spring MVC/Servlet với Spring Security **6.4–6.5 và 7.x**, Java 17+; WebFlux có cơ chế khác và không thể dùng nguyên `HttpSecurity` Servlet.

Sau bài học, bạn sẽ:

1. Giải thích chính xác sự khác nhau giữa UP, UV, chữ ký WebAuthn và nhận diện tài khoản.
2. Nhận biết byte `flags` trong `authenticatorData`, tách các bit UP/UV và không nhầm với BE/BS.
3. Lựa chọn chính sách `required`, `preferred` hoặc `discouraged` theo rủi ro nghiệp vụ.
4. Phân biệt yêu cầu gửi đến browser/authenticator với **điều kiện mà server bắt buộc kiểm tra**.
5. Hiểu hai ceremony **registration (`create`)** và **authentication (`get`)**, cùng các trường hợp ngoại lệ có chủ đích.
6. Tích hợp passkey bằng `HttpSecurity.webAuthn(...)` và kiểm thử các trường hợp UP/UV có/không.
7. Không ngộ nhận `UV=1` là quyền `ROLE_ADMIN`, là biết danh tính người thật, hay đương nhiên có đủ MFA theo mọi chính sách.

## 2. Mô hình tin cậy: ai kiểm tra điều gì?

Trong WebAuthn có ít nhất bốn thành phần:

| Thành phần | Nhiệm vụ |
| --- | --- |
| **RP / Spring Security** | Sinh challenge, quản lý options, RP ID và origin được tin; lưu credential public key; xác minh assertion/registration, xác thực account và cấp quyền |
| **Browser / WebAuthn client** | Gọi `navigator.credentials.create()` hoặc `.get()`, điều phối authenticator, ràng buộc origin/RP ID và gửi kết quả về RP |
| **Authenticator** | Giữ private key của credential, yêu cầu thao tác hiện diện/xác minh cục bộ theo chính sách, tạo chữ ký và flags |
| **Người dùng** | Tương tác với thiết bị và chứng minh được quyền sử dụng authenticator theo quy tắc UV của thiết bị |

Sơ đồ khi đăng nhập:

```text
Browser                         RP / Spring Security             Authenticator
  |                                     |                               |
  | POST /webauthn/authenticate/options|                               |
  |------------------------------------>| tạo challenge + request opts |
  |<------------------------------------| rpId, userVerification, ...  |
  | navigator.credentials.get({publicKey})                              |
  |------------------------------------------------------------------->|
  |                                     |            thử UP và/hoặc UV   |
  |                                     |    ký challenge-bound data    |
  |<-------------------------------------------------------------------|
  | POST /login/webauthn              |                                 |
  |------------------------------------>| verify signature, challenge   |
  |                                     | origin, rpIdHash, UP, UV, ...  |
  |                                     | -> Authentication/session     |
  |<------------------------------------| thành công hoặc từ chối       |
```

**Một assertion chỉ đáng tin sau khi đã xác minh toàn bộ ngữ cảnh WebAuthn.** Một client độc hại có thể gửi JSON tự tạo có `"uv": true`, nhưng đó không phải bằng chứng. UP/UV có ý nghĩa vì chúng nằm trong `authenticatorData`, phần dữ liệu được **bao phủ bởi chữ ký** của credential trong authentication ceremony.

WebAuthn chống phishing bằng cách gắn credential với **RP ID** và xác minh **origin**; UP/UV không phải cơ chế thay cho việc ràng buộc origin, RP ID hoặc kiểm tra chữ ký.

## 3. User presence (UP) là gì?

**UP** trả lời: “Có một hành động tương tác mà authenticator chấp nhận làm dấu hiệu người dùng **có mặt và chủ ý** khi thực hiện thao tác hay không?”

Ví dụ:

- Người dùng **chạm** vào cảm biến tiếp xúc trên USB/NFC security key.
- Người dùng **xác nhận** yêu cầu sử dụng passkey trên thiết bị.
- Một authenticator kết hợp thao tác mở khóa và xác nhận trong một trải nghiệm duy nhất.

UP **không khẳng định**:
- người đã chạm chính là chủ sở hữu hợp pháp của account;
- đã có PIN, vân tay hoặc Face ID;
- trình duyệt đang nói chuyện với RP thật nếu server bỏ qua kiểm tra origin/chữ ký;
- người dùng đã được cấp quyền nghiệp vụ trong ứng dụng.

Trong `authenticatorData.flags`, **bit 0** (mask `0x01`) biểu diễn **User Present**. `UP=1` nghĩa authenticator đã thực hiện presence test; `UP=0` nghĩa không có kết quả presence test như vậy trong phản hồi.

Theo WebAuthn Level 3, **luồng authentication assertion thông thường kiểm tra UP bit phải bằng 1**. Có những trường hợp đặc biệt như cơ chế tạo credential nâng cấp trong nền có quy định khác, nhưng chúng **không** làm một màn hình đăng nhập passkey thông thường được phép tự bỏ kiểm tra UP.

## 4. User verification (UV) là gì?

**UV** trả lời: “Authenticator có xác minh **người sử dụng nó** bằng cơ chế cục bộ trước khi cho dùng credential không?”

Các ví dụ:
- Nhập PIN của authenticator (ví dụ PIN FIDO2 của security key).
- Xác minh vân tay/nhận diện khuôn mặt được thiết bị chấp thuận.
- Xác thực bằng mật khẩu/PIN mở khóa thiết bị, nếu phương thức đó được thiết bị sử dụng làm UV trong quy trình WebAuthn.

Trong `authenticatorData.flags`, **bit 2** (mask `0x04`) biểu diễn **User Verified**. `UV=1` khẳng định authenticator đã thực hiện phương thức UV thỏa chính sách thiết bị cho thao tác này; `UV=0` là chưa chứng minh được UV cho thao tác.

Một số điều **không thể suy ra** từ `UV=1`:

- Không biết **cụ thể** vân tay, PIN hay phương thức nào đã được sử dụng nếu không có cơ chế dữ liệu/bảo đảm bổ sung.
- Không biết **danh tính pháp lý** của con người; UV thường xác minh người được quyền sử dụng **authenticator**, không phải kiểm tra hộ chiếu.
- Không biết ai khác có thể mở khóa cùng thiết bị hoặc quản lý tài khoản đồng bộ passkey.
- Không có bằng chứng người dùng được phép thao tác nghiệp vụ như rút tiền hoặc đổi role.
- Không được tự động kết luận credential là phần cứng không thể sao chép, không đồng bộ hoặc đạt một mức assurance cụ thể.

**Tình huống dễ nhầm:** security key chỉ cần chạm vật lý vẫn có thể tạo chữ ký hợp lệ, `UP=1` và `UV=0`. Một authenticator có PIN/sinh trắc học có thể trả `UP=1`, `UV=1`. Chữ ký đúng trong cả hai trường hợp **không đồng nghĩa** mức xác minh người sử dụng ngang nhau.

## 5. UP và UV không phải hai cách gọi của cùng một thao tác

| Tình huống | UP | UV | Diễn giải cho luồng đăng nhập tiêu chuẩn |
| --- | --- | --- | --- |
| Security key yêu cầu chạm, không yêu cầu PIN | 1 | 0 | Có tương tác; **không** có bằng chứng UV. Chỉ được chấp nhận nếu RP cho phép không có UV |
| Device passkey yêu cầu mở khóa rồi xác nhận | 1 | 1 | Có tương tác và có UV; vẫn phải kiểm tra chữ ký và các ràng buộc khác |
| Authenticator trả dữ liệu không chứng minh presence | 0 | 0 | Authentication ceremony thông thường phải từ chối vì thiếu UP |
| UV bit bật nhưng UP bit tắt | 0 | 1 | Không được bỏ yêu cầu UP của assertion thông thường chỉ vì UV bật |
| Không có assertion/chữ ký hợp lệ | — | — | Không tin bất kỳ flags nào do request cung cấp |

Ký hiệu `1` và `0` chỉ là giá trị bit; **không thể chỉ đọc hai bit rồi cấp phiên đăng nhập**. RP phải biết credential đã đăng ký, so chữ ký với public key, kiểm tra challenge, origin, `rpIdHash`, thời hạn/chống replay và các điều kiện khác.

Hai câu hỏi phải được tách:

1. **Có private key hợp lệ cho RP này không?** Kiểm tra chữ ký và ràng buộc credential.
2. **Người sử dụng authenticator đã được xác minh ở mức nào?** Kiểm tra UP và UV theo policy lưu ở server.

## 6. `authenticatorData` chứa flags ở đâu?

Đối với authentication assertion, `authenticatorData` là dãy byte (ít nhất **37 byte** trong cấu trúc cơ bản):

```text
0                    31  32      33                   36
+----------------------+--------+-----------------------+
| rpIdHash (32 bytes)  | flags  | signCount (4 bytes)   | ...
+----------------------+--------+-----------------------+
                          ^
                          byte index 32
```

Bố cục bit trong byte `flags` (bit 0 là bit thấp nhất):

| Bit | Mask | Tên | Ý nghĩa chính |
| --- | --- | --- | --- |
| 0 | `0x01` | **UP** | User Present |
| 1 | `0x02` | RFU1 | Dành riêng, không tự diễn giải |
| 2 | `0x04` | **UV** | User Verified |
| 3 | `0x08` | **BE** | Backup Eligible: credential có thể được sao lưu/đồng bộ |
| 4 | `0x10` | **BS** | Backup State: credential hiện đang ở trạng thái backup |
| 5 | `0x20` | RFU2 | Dành riêng |
| 6 | `0x40` | **AT** | Có attested credential data, thường xuất hiện ở registration |
| 7 | `0x80` | **ED** | Có extension data |

Cách kiểm tra:

```text
UP = (flags & 0x01) != 0
UV = (flags & 0x04) != 0
BE = (flags & 0x08) != 0
BS = (flags & 0x10) != 0
```

Ví dụ:
- `flags=0x01`: UP=1, UV=0, BE=0, BS=0.
- `flags=0x05`: UP=1, UV=1, BE=0, BS=0.
- `flags=0x1D`: UP=1, UV=1, BE=1, BS=1.
- `flags=0x00`: UP=0, UV=0, không đạt policy đăng nhập thông thường.

**BE/BS khác UV:** passkey có thể đồng bộ sang nhiều thiết bị và vẫn yêu cầu UV mỗi lần. Một passkey trên phần cứng không đồng bộ cũng có thể không thực hiện UV khi chỉ chạm vào key. `BS=1` không phải bằng chứng “đã dùng Face ID”, còn `UV=1` không tiết lộ passkey có đang đồng bộ hay không.

Theo quy tắc trạng thái credential, `BS=1` đòi hỏi credential đó backup eligible (`BE=1`). Không tự giải thích trạng thái backup mà bỏ qua validation theo spec.

## 7. Chương trình Java 17+ chạy được: đọc cờ và so chính sách

Đoạn sau **chỉ** trình diễn giải mã flags và điều kiện logic UP/UV. Nó **không** xác minh chữ ký, không so challenge và **không được dùng làm bộ xác thực WebAuthn production**.

Tạo file `WebAuthnFlagsDemo.java`:

```java
import java.util.Locale;

public class WebAuthnFlagsDemo {
    private static final int UP = 0x01;
    private static final int UV = 0x04;
    private static final int BE = 0x08;
    private static final int BS = 0x10;

    private static boolean has(int flags, int mask) {
        return (flags & mask) != 0;
    }

    // Logic minh họa sau khi WebAuthn signature/context đã được xác minh.
    private static boolean allowed(int flags, boolean requireUv) {
        if (!has(flags, UP)) {
            return false;
        }
        return !requireUv || has(flags, UV);
    }

    public static void main(String[] args) {
        int[] samples = { 0x00, 0x01, 0x05, 0x1D };

        for (int flags : samples) {
            System.out.printf(
                Locale.ROOT,
                "flags=0x%02X UP=%s UV=%s BE=%s BS=%s "
                    + "required=%s preferred=%s%n",
                flags,
                has(flags, UP),
                has(flags, UV),
                has(flags, BE),
                has(flags, BS),
                allowed(flags, true),
                allowed(flags, false)
            );
        }
    }
}
```

Chạy:

```bash
javac WebAuthnFlagsDemo.java
java WebAuthnFlagsDemo
```

**stdout chính xác:**

```text
flags=0x00 UP=false UV=false BE=false BS=false required=false preferred=false
flags=0x01 UP=true UV=false BE=false BS=false required=false preferred=true
flags=0x05 UP=true UV=true BE=false BS=false required=true preferred=true
flags=0x1D UP=true UV=true BE=true BS=true required=true preferred=true
```

Giải thích:
- `requireUv=true` chỉ cho qua khi **UP=1 và UV=1**.
- `requireUv=false` vẫn yêu cầu UP=1, nhưng **không** bắt buộc UV.
- Cột `preferred` trong ví dụ minh họa **điều kiện chấp nhận** khi RP không bắt buộc UV, không chứng minh browser luôn chọn UV.
- `0x1D` vừa chứa UP/UV vừa có backup flags; **không** kết luận chỉ vì đồng bộ thì UV yếu hơn.
- Ví dụ đọc một số nguyên giả định đại diện `flags`. Trong một WebAuthn verifier thật, phải lấy flags từ **`authenticatorData` được chữ ký bảo vệ**; không dùng query param `flags` hoặc field JSON do client khai báo để cấp quyền.

Tự kiểm tra: đổi `0x05` thành `0x01` thì policy `required` phải từ chối; policy không bắt buộc UV có thể chấp nhận **sau các kiểm tra WebAuthn khác**.

## 8. `required`, `preferred`, `discouraged`: chính sách quan trọng nhất

Trong WebAuthn API, RP gửi `userVerification` khi gọi:

- `navigator.credentials.create({ publicKey: ... })` cho registration, trong `authenticatorSelection.userVerification`.
- `navigator.credentials.get({ publicKey: ... })` cho authentication, trong `userVerification`.

`UserVerificationRequirement` có ba giá trị:

| Giá trị | Ý định của RP | Đối với assertion thiếu UV |
| --- | --- | --- |
| **`"required"`** | Bắt buộc authenticator thực hiện UV | **Từ chối**; nếu không thực hiện được UV, browser/authenticator thường báo lỗi |
| **`"preferred"`** | Muốn UV khi có thể, ưu tiên UX/tương thích | Không nhất thiết từ chối chỉ vì `UV=0` |
| **`"discouraged"`** | Không yêu cầu/không muốn phát sinh UV khi có thể tránh | Không mặc định từ chối `UV=0`; nhưng vẫn có thiết bị thực hiện UV |

**Chú ý:** `discouraged` **không phải** lệnh “cấm authenticator xác minh người dùng”. Một thiết bị có thể thực hiện UV theo chính sách riêng, và khi có bằng chứng hợp lệ, flag UV có thể vẫn bằng 1.

### Khi chọn `required`

Cân nhắc dùng cho:
- Đăng nhập **passwordless** đòi hỏi cả quyền sở hữu credential và xác minh cục bộ.
- Step-up authentication trước thao tác nhạy cảm nếu policy đòi UV.
- Đăng ký hoặc thay đổi passkey trong tình huống tổ chức yêu cầu thiết bị phải xác minh người đang thao tác.
- Tài khoản có mức rủi ro cao, nơi UP-only không đáp ứng chính sách.

Rủi ro UX: authenticator không hỗ trợ UV, PIN chưa cài, sinh trắc học lỗi hoặc UV bị khóa có thể khiến người dùng không đăng nhập được. Cần recovery bảo mật, không hạ policy âm thầm.

### Khi chọn `preferred`

Cân nhắc khi:
- Sản phẩm cần nhận nhiều loại authenticator, bao gồm security key chỉ có thao tác chạm.
- Có phương thức xác thực bổ sung khác và thiết kế risk-based rõ ràng.
- Đang chuyển đổi sang passkey, nhưng không muốn coi tất cả thiết bị thiếu UV là lỗi.

**Cảnh báo:** `preferred` không bảo đảm mỗi lần authentication đều có UV. Nếu ứng dụng quảng bá “đăng nhập chỉ thành công khi có PIN hoặc sinh trắc học” nhưng nhận cả `UV=0`, thì tuyên bố và chính sách không khớp.

### Khi chọn `discouraged`

Chỉ dùng khi thực sự có lý do thiết kế về tương thích/UX và **không cần** UV cho ceremony này. Không tự chọn `discouraged` cho đăng nhập passwordless có rủi ro cao chỉ vì muốn bỏ mọi lời nhắc.

### Khác biệt “gửi yêu cầu” với “xác minh kết quả”

Một lỗi bảo mật nghiêm trọng là chỉ gửi:

```json
{
  "userVerification": "required"
}
```

tới browser rồi **tin** browser đã thực hiện yêu cầu. RP phải nhớ **chính sách do server thiết lập** và khi xử lý assertion phải xác nhận **UV bit thực tế**. Nếu `UV=0`, việc client có hiển thị một màn hình yêu cầu nhập PIN không thể thay thế kiểm tra sau xác thực.

Đối với `"preferred"`, dù UV=0 vẫn có thể chấp nhận WebAuthn assertion hợp lệ, nhưng ứng dụng cần xác định rõ **mức assurance** của phiên; không sử dụng nó như bằng chứng UV cho giao dịch đòi step-up.

## 9. Registration và authentication là hai ceremony độc lập

### 9.1. Registration (`navigator.credentials.create`)

RP yêu cầu tạo credential mới cho account:

```json
{
  "rp": { "id": "example.org", "name": "Example" },
  "user": {
    "id": "<base64url-opaque-user-handle>",
    "name": "linh@example.org",
    "displayName": "Linh"
  },
  "challenge": "<fresh-base64url-random>",
  "pubKeyCredParams": [
    { "type": "public-key", "alg": -7 }
  ],
  "authenticatorSelection": {
    "residentKey": "preferred",
    "userVerification": "required"
  },
  "attestation": "none"
}
```

Đây là **sơ đồ JSON**, không phải request đủ để tự tạo passkey mà không có challenge/user handle thật. Browser nhận `PublicKeyCredentialCreationOptions`, chuyển các trường nhị phân từ base64url sang byte arrays, rồi gọi `.create()`.

Quy trình server:
1. Xác minh account đang **được phép đăng ký credential** và đã xác thực/reauth theo policy.
2. Sinh challenge mới, lưu trạng thái với session hoặc transaction.
3. Xác minh response type `webauthn.create`, challenge, origin, RP ID hash, dữ liệu attestation/credential public key, UP và UV **theo chính sách registration**.
4. Lưu credential ID, public key, user handle, metadata và các cờ có ý nghĩa; gắn với đúng account.
5. Không để browser tự khai account ID khác trong response nhằm chiếm account người khác.

Đặc biệt, **userVerification khi registration** không tự đặt mặc định cho **mọi lần authentication về sau**. Nếu login cần UV, hãy đặt và thực thi policy riêng ở bước `get`.

### 9.2. Authentication (`navigator.credentials.get`)

RP cấp options để chứng minh quyền dùng credential đã đăng ký:

```json
{
  "challenge": "<fresh-base64url-random>",
  "rpId": "example.org",
  "timeout": 300000,
  "allowCredentials": [],
  "userVerification": "required"
}
```

`allowCredentials: []` có thể dùng trong discoverable credential/passkey login; tùy luồng, RP có thể gửi danh sách credential IDs cụ thể khi đã biết username. `timeout` chỉ là gợi ý thời gian thực hiện trên client, không thay cho TTL challenge phía server.

Client nhận options từ server và gọi:

```javascript
// Giả sử `publicKeyOptions` đã được nhận từ RP và chuyển các trường
// challenge/credential ID về Uint8Array đúng định dạng WebAuthn.
const assertion = await navigator.credentials.get({
  publicKey: publicKeyOptions
});
```

Đây là **snippet browser**, không phải file JS hoàn chỉnh; phải có HTTPS secure context (ngoại lệ local development phù hợp), server endpoint và hàm decode base64url. Khi gửi kết quả về Spring Security, các trường binary phải encode đúng.

Một response authentication chứa:
- `id`/`rawId`: credential ID.
- `response.clientDataJSON`: `type`, `challenge`, `origin`, `crossOrigin`...
- `response.authenticatorData`: `rpIdHash`, flags và `signCount`.
- `response.signature`: chữ ký do private key credential tạo.
- `response.userHandle`: có thể có hoặc không, tùy loại credential/luồng.

RP phải kiểm tra response theo **request đã lưu**, không đọc trường `userVerification` mới từ request POST do browser tự gửi rồi tự quyết định chấp nhận.

## 10. Thứ tự kiểm tra assertion trên server

Có thể dùng checklist sau khi xử lý một authentication assertion WebAuthn:

1. **Định dạng và loại**: giải mã binary an toàn, từ chối dữ liệu sai cấu trúc/kích thước, `clientDataJSON.type` phải là `"webauthn.get"`.
2. **Challenge**: challenge trong `clientDataJSON` phải trùng challenge **đã phát** cho giao dịch đang chờ, còn hạn và chưa dùng lại.
3. **Origin**: phải đúng origin tin cậy (scheme/host/port); `https://app.example.org` không tự đồng nghĩa `https://evil.example.org`.
4. **RP ID hash**: SHA-256 của RP ID kỳ vọng phải khớp 32 byte đầu của `authenticatorData`; không lấy RP ID từ client mà bỏ kiểm tra.
5. **Credential**: tra credential ID đã đăng ký và public key, trạng thái thu hồi, mapping đúng user/account; kiểm tra `userHandle` theo quy tắc flow.
6. **Chữ ký**: xác minh `signature` với public key đã lưu trên dữ liệu `authenticatorData || SHA256(clientDataJSON)` theo WebAuthn algorithm.
7. **UP**: với authentication assertion thông thường, `flags & 0x01` phải bật.
8. **UV**: nếu policy server yêu cầu user verification, `flags & 0x04` phải bật; nếu không, authentication thất bại.
9. **Sign count/các extensions**: xử lý counter và rủi ro clone theo spec, đặc điểm credential và chính sách; không cho phép dữ liệu extension không hợp lệ thay đổi policy.
10. **Account/authorization**: kiểm tra account còn enabled/được phép login, tạo `Authentication` và session theo policy; quyền ứng dụng không đến từ `UP/UV` một cách tự động.

Thứ tự logic minh họa có thể khác giữa thư viện xác minh. Điều quan trọng là **không** tách kiểm tra UP/UV khỏi xác thực chữ ký và challenge.

### Một phản ví dụ sai

```java
// SAI: request parameter do browser tự đặt không phải bằng chứng WebAuthn.
boolean verified = "true".equals(request.getParameter("uv"));
if (verified) {
    // Không được cấp session hoặc role chỉ từ điều kiện này.
}
```

Không viết bộ xác minh chữ ký WebAuthn bằng `if` trên JSON field. Dùng verifier tuân thủ chuẩn của Spring Security/WebAuthn4J và test toàn bộ failure paths.

## 11. Spring Security: cách bật Passkey login đúng phiên bản

Spring Security thêm hỗ trợ WebAuthn/passkeys từ **6.4**. Tài liệu 6.5 và 7.x dùng `HttpSecurity.webAuthn(...)` cho Servlet, nhưng **dependency được yêu cầu khác nhau**.

| Dòng thư viện | Khởi đầu phù hợp |
| --- | --- |
| Spring Security trước 6.4 | Không có `webAuthn(...)` DSL tích hợp theo ví dụ này; dùng integration tương thích hoặc nâng cấp |
| Spring Security **6.4–6.5**, Boot 3.x tương ứng | Dùng Spring Security WebAuthn trong `spring-security-web`, thêm dependency **WebAuthn4J core** được tài liệu đúng phiên bản yêu cầu |
| Spring Security **7.x** | Theo hướng dẫn 7.x, thêm module `spring-security-webauthn` cùng phiên bản với các module Security |
| Spring WebFlux | Không gắn `HttpSecurity`/`SecurityFilterChain` của Servlet vào `SecurityWebFilterChain`; kiểm tra hỗ trợ/đường tích hợp reactive theo phiên bản |

### 11.1. Gradle dependencies cho Spring Security 6.5

Trong dự án Spring Boot **3.x** đã có Gradle plugins và dependency management tương thích với Spring Security 6.5:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'
}
```

`0.29.7.RELEASE` là phiên bản WebAuthn4J core được tài liệu Spring Security **6.5** liệt kê; khi dùng bản Spring Security khác, phải kiểm tra yêu cầu tương thích, không tự buộc JAR cũ vào bản mới.

Với **Spring Security 7.x**, tài liệu yêu cầu bổ sung:

```groovy
dependencies {
    implementation 'org.springframework.security:spring-security-webauthn'
}
```

Dòng trên là **dependency bổ sung** cho một ứng dụng Spring MVC đã có dependencies Web/Security đúng phiên bản. Không trộn `spring-security-webauthn:7.x` với các module Security 6.x.

### 11.2. Cấu hình Servlet tối thiểu

File `src/main/java/example/passkey/PasskeySecurityConfig.java`:

```java
package example.passkey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class PasskeySecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .webAuthn(webAuthn -> webAuthn
                .rpId("example.org")
                .allowedOrigins("https://example.org")
            );

        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails demo = User.withUsername("linh@example.org")
            .password("{noop}demo-password-not-for-production")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(demo);
    }
}
```

Với `.formLogin(withDefaults())`, demo cho phép user đã đăng nhập bằng password **đăng ký** passkey trước rồi dùng nó cho login tiếp theo. Giá trị password `{noop}` hoàn toàn **không phù hợp production**; dùng `PasswordEncoder` mạnh và account repository thật trong ứng dụng thực tế.

`rpId` phải nhất quán với domain mà RP sở hữu (ví dụ `example.org`); `allowedOrigins` là danh sách origin thực sự được tin. Không đặt wildcard tùy ý hoặc dùng `localhost` public ngoài môi trường test. Để chạy demo thật, cần host HTTPS tương ứng, browser có passkey/WebAuthn, persistence cho credential và CSRF/session hoạt động.

**Điểm trọng tâm của bài:** cấu hình trên **bật WebAuthn**, chưa khẳng định mọi assertion đều bắt buộc `UV=1`. Theo tài liệu Spring Security 6.5, ví dụ authentication options trả:

```json
{
  "rpId": "example.localhost",
  "userVerification": "preferred",
  "allowCredentials": []
}
```

`"preferred"` có thể tạo xác thực hợp lệ với `UV=0`. Vì vậy, đối với production cần UV, **phải kiểm tra cấu hình request-options/verification thực tế** của đúng phiên bản Spring Security và thiết kế policy phía server; không suy diễn rằng `.webAuthn(...)` mặc định luôn tương đương `"required"`.

### 11.3. Các HTTP endpoint thường thấy

| Endpoint | Mục đích | Ghi chú |
| --- | --- | --- |
| `POST /webauthn/register/options` | Yêu cầu options cho registration | Cần user đang authenticated và CSRF hợp lệ theo hướng dẫn |
| `POST /webauthn/register` | Nộp attestation/credential registration | Verify và lưu public key/credential thuộc đúng account |
| `POST /webauthn/authenticate/options` | Lấy options/challenge cho authentication | Tạo request state, cần CSRF theo cấu hình mặc định |
| `POST /login/webauthn` | Nộp assertion để đăng nhập | Verify `webauthn.get`, signature, challenge, origin, flags |

Các endpoint mặc định có thể được tùy biến theo phiên bản/config. Trong production, hãy giữ `challenge` ở session hoặc repository dùng chung phù hợp multi-node và xóa/tiêu thụ đúng sau một lần. Không bỏ CSRF vô điều kiện chỉ vì các request có JSON.

### 11.4. Ví dụ request options không phải kết quả xác minh

Tạo ra response JSON:

```json
{
  "challenge": "base64url-challenge-from-server",
  "rpId": "example.org",
  "userVerification": "required"
}
```

chỉ là **bước phát hành yêu cầu**. RP phải đồng thời thực thi `UV=1` khi kiểm tra assertion. Không chỉ sửa field trên browser:

```javascript
publicKeyOptions.userVerification = "required";
```

rồi nghĩ server đã tăng assurance; browser có thể bị sửa. Chính sách RP phải được cấu hình và được verifier áp dụng ở phía server. Khi cần tùy biến request-options provider, repository hoặc verifier, dùng API **đúng minor version** và bảo đảm yêu cầu đã lưu được đối chiếu khi nhận assertion. Không invent một method `.webAuthn(w -> w.userVerification(...))` nếu Javadoc configurer phiên bản thực không có method đó.

## 12. Thiết kế chính sách theo trường hợp sử dụng

**Chính sách xác minh** không chỉ là một string trong JSON. Nó là tập điều kiện server quyết định **được đăng nhập không**, **được làm gì** và **bao lâu thì cần xác minh lại**.

| Tình huống | Chính sách UV gợi ý | Lý do và lưu ý |
| --- | --- | --- |
| Đăng nhập passkey **passwordless** cho hệ thống nội bộ nhạy cảm | `required` | Cần xác minh người đang dùng authenticator, không chỉ chạm key |
| Chuyển đổi từ password sang passkey, ưu tiên hỗ trợ thiết bị cũ | `preferred` nếu policy rủi ro chấp nhận | Phải chấp nhận rằng có phiên `UV=0` và không gắn nhãn “đã được xác minh cục bộ” |
| Login password + security key chỉ có UP như một yếu tố bổ sung | Có thể không bắt buộc UV trên **lần dùng key đó** | Phải có policy đảm bảo yếu tố password đã được kiểm tra và yêu cầu MFA phù hợp; không cho bypass factor |
| Đổi thông tin thanh toán, API key, thêm/xóa passkey | `required` với **challenge mới/reauth** nếu thiết kế step-up | Một lần login cũ không nên tự đủ cho giao dịch rủi ro cao |
| Account phục hồi khi mất passkey | Recovery được kiểm soát riêng | Không âm thầm đặt `discouraged` trên mọi login để chữa lỗi |
| Kiosk/shared workstation | Đánh giá kỹ thiết bị/ownership, có thể không cho dùng sync passkey tùy policy | UV trên thiết bị dùng chung không chứng minh danh tính pháp lý hoặc ngăn người khác có PIN |

Các lựa chọn trên mang tính kiến trúc, **không** phải quy định cứng cho mọi sản phẩm. Phải đối chiếu threat model, chính sách tổ chức và yêu cầu assurance; đôi khi tốt hơn là dùng IdP hỗ trợ passkeys/MFA và để ứng dụng nhận kết quả xác thực có ràng buộc từ IdP.

### `preferred` không phải “required có fallback”

Một hệ thống gửi `"preferred"` rồi khi UV=0 tự chấp nhận và cấp **cùng quyền** với UV=1 đã chọn chính sách chấp nhận UP-only. Nó không âm thầm có độ an toàn tương đương `required`.

Có hai thiết kế hợp lý:
- **Một mức login:** chỉ cấp session khi assertion có UV theo policy, nếu không thì lỗi/fallback bảo mật.
- **Phân mức assurance:** server cấp session hạn chế cho chứng minh UP-only, và yêu cầu xác thực bổ sung/step-up trước chức năng nhạy cảm.

Điều kiện bắt buộc: server **ghi nhận mức xác minh đã thực sự kiểm tra**, không chấp nhận cờ `uv` từ form hoặc tự coi mọi phiên passkey đều UV.

## 13. Registration policy và authentication policy có thể khác nhau

Một lỗi vận hành là cấu hình `"userVerification": "required"` lúc **đăng ký** rồi không chú ý rằng lần **đăng nhập** vẫn có thể gửi `"preferred"`.

Hãy kiểm tra riêng:

| Ceremony | Dữ liệu cần giữ | Policy cần xác minh |
| --- | --- | --- |
| `create` | Challenge, account ID/user handle, RP ID, origin, credential options | UP/UV theo yêu cầu registration, public key/credential mới, attestation policy |
| `get` | Challenge, relying party, allowed credential(s), session và expected UV | Chữ ký với public key đã lưu, UP=1, UV theo yêu cầu **authentication** |
| Step-up `get` | Challenge mới gắn với account, hành động/risk context và TTL | `UV=1` nếu policy cần, chứng minh fresh-auth và cập nhật assurance an toàn |

Một credential được đăng ký khi `UV=1` **không** chứng minh rằng **mọi assertion về sau** đều có `UV=1`. Cần kiểm tra **mỗi lần**. Đồng thời, `UV=0` ở một lần `get` **không** có nghĩa credential bị đổi private key; nó chỉ phản ánh mức user verification được chứng minh trong lần thao tác đó.

Nếu chỉ có login passkey, chính sách `required` cần được thực thi trước khi thiết lập `Authentication` chứ không phải chỉ ở một controller `/sensitive` sau khi đã cấp session đầy đủ.

## 14. WebAuthn, authentication factor và phân quyền Spring Security

WebAuthn chứng minh việc dùng credential và các điều kiện tương ứng; Spring Security quyết định account và authorities.

```text
WebAuthn assertion hợp lệ
      |
      +--> Verify public key + challenge + origin + rpIdHash
      |
      +--> Verify UP=1
      |
      +--> Verify UV theo server policy
      |
      v
Authenticated principal (account)
      |
      v
GrantedAuthority, hasRole/hasAuthority, @PreAuthorize
```

- `ROLE_ADMIN` **không** được sinh vì UV=1.
- UP/UV **không** thay thế role mapping từ account repository, nhóm hoặc policy engine.
- Cùng một account có thể có nhiều passkeys với authenticator/capability khác nhau; nên đánh giá theo **assertion hiện tại**, không áp dụng giả định cố định chỉ dựa trên kiểu passkey trong profile.
- Nếu cần mức assurance riêng, thiết kế trạng thái session/`Authentication` bảo vệ phía server và kiểm thử step-up; không đưa một `role=UV` vào request do client kiểm soát.

### Passkey có tự động là MFA không?

Một **user-verifying** cryptographic authenticator có thể hỗ trợ mức assurance đa yếu tố khi đáp ứng chuẩn và chính sách tương ứng. Tuy nhiên, mệnh đề “có passkey là luôn có MFA” là thiếu chính xác:

- Với `UV=0`, có thể chỉ có chứng minh quyền sử dụng private key và sự hiện diện của người thao tác.
- Với `UV=1`, authenticator đã xác minh cục bộ người sử dụng; mức bảo đảm thực tế còn phụ thuộc authenticator, quản trị khóa, đồng bộ, enrollment, recovery và tiêu chuẩn áp dụng.
- Một yêu cầu MFA do tổ chức đặt ra có thể đòi thêm tín hiệu/ràng buộc cụ thể; không tự coi mọi thiết bị và mọi mức UV giống nhau.

Không đánh đồng “Face ID hiện lên” với “RP chắc chắn nhận `UV=1`”. UI là trải nghiệm, **signed flags và server verification** mới là dữ liệu kỹ thuật cần kiểm tra.

## 15. Passkey đồng bộ, BE/BS và chính sách quản lý thiết bị

Các passkey có thể là:
- **Single-device credential:** khóa gắn với một authenticator và không đồng bộ.
- **Multi-device/synced credential:** khóa có thể được backup và đồng bộ qua hệ sinh thái hoặc nhà quản lý passkey.

`BE` và `BS` giúp RP có tín hiệu về backup eligibility/state. Nhưng:

1. `BE=1` không nói **lúc này** người dùng có hoặc chưa xác minh bằng PIN/biometric; đó là vai trò của `UV`.
2. `BS=1` không chứng minh ngay chính xác có bao nhiêu bản sao hoặc thiết bị đang giữ credential.
3. `BE=0` không đủ để tuyên bố chứng thư phần cứng mạnh, đạt cấp độ compliance cụ thể hoặc không bị xâm phạm.
4. `signCount` có thể bằng 0 hoặc có hành vi không đơn điệu ở credential đồng bộ; không dùng nó như một phép thử duy nhất để kết luận clone.
5. Nếu tổ chức cần thiết bị được quản lý, xuất xứ authenticator hoặc hardware attestation, phải có **attestation/device policy** riêng, không suy ra từ UV.

Một ứng dụng có thể yêu cầu `UV=1` cho mọi passkey mà vẫn chấp nhận cả passkey đồng bộ và security key, miễn verification policy phù hợp. Ngược lại, có thể chặn credential multi-device vì yêu cầu nội bộ; đó là **quyết định quản trị thiết bị**, không phải ý nghĩa của UV.

## 16. Kiểm thử theo ma trận chính sách

Phần lớn lỗi UP/UV xuất hiện khi chỉ thử happy path với điện thoại đã bật sinh trắc học.

### 16.1. Bảng test cần có

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Assertion có signature/challenge/origin đúng, UP=1, UV=1; policy `required` | **Chấp nhận** nếu account và mọi ràng buộc khác hợp lệ |
| Tương tự, UP=1, UV=0; policy `required` | **Từ chối**, không tạo authenticated session |
| Tương tự, UP=1, UV=0; policy `preferred` | Có thể chấp nhận theo policy, nhưng không được tự gắn assurance UV |
| Signature đúng nhưng UP=0, UV=1; login thông thường | **Từ chối** vì thiếu user presence |
| UP=1, UV=1, nhưng signature sai | **Từ chối** |
| UP=1, UV=1, nhưng challenge không khớp hoặc replay | **Từ chối** |
| UP=1, UV=1, nhưng origin/RP ID sai | **Từ chối** |
| Assertion đã qua WebAuthn nhưng account bị khóa | **Từ chối** theo account policy |
| Assertion hợp lệ, account thiếu `ROLE_ADMIN` | **Từ chối** endpoint admin (authorization) |
| Registration dùng `required`, login dùng `preferred` | Xác minh là **hai policy khác**; không tự kết luận login đã UV |
| Client sửa options từ `preferred` sang `required` hoặc ngược lại | Server vẫn thực thi chính sách **đã lưu**, không tin options do client tự đổi |
| Session UP-only đòi chức năng nhạy cảm | Yêu cầu step-up phù hợp; không cấp quyền chỉ nhờ session cũ |
| Mất session/challenge trên cluster | Login phải thất bại an toàn và có retry hợp lý, không tắt challenge check |
| Credential bị xóa/thu hồi | Login phải thất bại dù chữ ký từ private key cũ đúng |
| Cờ BE/BS thay đổi ngoài quy tắc spec | Áp dụng credential state validation và audit, không bỏ qua |

### 16.2. Unit test Java 17 cho quyết định flags

Trong ví dụ này, `WebAuthnFlagsDemo.allowed` là private để phục vụ `main`. Nếu muốn kiểm thử độc lập, có thể tạo một utility riêng có method public phù hợp rồi gọi từ JUnit. Với code Java **thuần JDK**, đoạn `main` ở mục 7 đủ để kiểm tra các trường hợp nhị phân cơ bản bằng `javac`/`java`.

**Giới hạn của test flags:** tính toán boolean từ `0x01` hoặc `0x05` **không kiểm chứng WebAuthn**. Một integration test đúng phải dùng verifier của Spring Security/WebAuthn4J hoặc authenticator thử nghiệm, có registration public key và một chữ ký hợp lệ. Cần tạo các ca âm tính (signature/challenge/origin/UV) mà verifier thực tế từ chối.

### 16.3. Kiểm tra cấu hình Spring Security qua HTTP

Với WebAuthn flow mặc định trong Spring Security 6.5:

```http
POST /webauthn/authenticate/options
X-CSRF-TOKEN: <valid-session-csrf-token>
```

Response mẫu (rút gọn):

```json
{
  "challenge": "<server-generated-base64url>",
  "rpId": "example.org",
  "allowCredentials": [],
  "userVerification": "preferred"
}
```

Sau khi policy được tăng lên `required` theo thiết kế server, test phải xác minh **cả hai**:
1. Options từ server thực sự nêu `userVerification: "required"` cho giao dịch cần UV.
2. Assertion thiếu UV dù có chữ ký hợp lệ **vẫn bị verifier từ chối** và không có session được cấp.

Nếu chỉ kiểm tra JSON options mà không kiểm tra failure path UV=0, test vẫn chưa bảo vệ chính sách thực tế.

### 16.4. Không bỏ qua các lỗi hạ tầng

- RP ID và HTTPS origin khác nhau sau reverse proxy: cần cấu hình đúng host public/allowed origins.
- Session/lưu challenge mất khi load balancer chuyển request giữa các instance: kiểm tra sticky/distributed session và TTL.
- CSRF bị chặn vì UI gọi POST options sai cách: phải truyền token CSRF hợp lệ thay vì tắt toàn bộ.
- Browser không có secure context hoặc authenticator không có PIN/UV: có thể gặp `NotAllowedError`/failure khác; xử lý UX và recovery rõ ràng.
- Người dùng có nhiều credentials/thiết bị: phải map credential ID/user handle đúng account, không dựa vào email client tự khai.
- Quá trình xóa/thêm credential không có reauth: có thể tạo đường account takeover dù login WebAuthn chính đã mạnh.

## 17. Các phản mẫu (anti-pattern) cần tránh

**Sai 1: `UP=1` đồng nghĩa xác thực sinh trắc học.**

Không đúng: chạm security key có thể chỉ chứng minh UP. Nếu giao dịch cần UV, phải kiểm tra `UV=1`.

**Sai 2: Có chữ ký hợp lệ nên không cần UP/UV.**

Chữ ký chứng minh credential private key được dùng. Yêu cầu chủ đích người dùng và xác minh cục bộ là điều kiện **bổ sung**.

**Sai 3: Gửi `userVerification:"required"` rồi không kiểm tra UV trên server.**

Đó chỉ là chỉ dẫn cho client/authenticator. Kẻ tấn công có thể sửa HTTP client code; server phải enforce dựa trên signed authenticatorData và policy lưu tại RP.

**Sai 4: `preferred` có nghĩa là luôn có sinh trắc học nếu điện thoại hỗ trợ.**

Không có bảo đảm như vậy. “Preferred” cho phép thiếu UV theo policy.

**Sai 5: Thấy `UV=1` rồi bỏ qua signature hoặc challenge.**

Một JSON response giả vẫn có thể chứa byte với UV=1. Flags chỉ đáng tin sau khi verifier đã kiểm tra chữ ký, challenge, origin, RP ID và credential.

**Sai 6: Thấy `UV=1` là cấp `ROLE_ADMIN`.**

UV phản ánh **cách authentication được thực hiện**, không phản ánh **entitlements**; role phải đến từ nguồn phân quyền đáng tin.

**Sai 7: Đăng ký passkey với UV rồi mọi login sau mặc định đạt UV.**

UP/UV được báo **trên từng ceremony**. Login yêu cầu UV phải kiểm tra trên assertion login đó.

**Sai 8: Không có UV thì luôn không an toàn và phải xóa credential.**

Một credential UP-only có thể phù hợp trong luồng password + security key hoặc profile rủi ro thấp; quyết định dựa trên policy thực tế. Không được âm thầm nâng assurance của nó.

**Sai 9: Cho phép bypass UV khi hỗ trợ thiết bị cũ mà không thông báo.**

Fallback làm giảm assurance. Nếu phải cho phép, nên có kiểm soát risk, audit, session scope và recovery riêng.

**Sai 10: Thay đổi flags bytes trong JSON test rồi coi đó là integration test WebAuthn.**

Thay byte sẽ làm chữ ký không còn hợp lệ; một test chỉ tạo payload lỗi không chứng minh verifier xử lý chính xác trường hợp **signature đúng nhưng UV=0**. Cần test harness/authenticator tạo phản hồi hợp lệ với flags mong muốn.

## 18. Quy trình thiết kế policy trước khi triển khai

Một nhóm phát triển có thể chốt các câu hỏi này trước khi quyết định `required` hay `preferred`:

1. **Mục tiêu xác thực?** Passwordless login, password + security key, đăng ký thiết bị, hay reauth cho giao dịch?
2. **Mức độ nhạy cảm?** Tài khoản phổ thông, dữ liệu cá nhân, tài chính, quản trị hạ tầng?
3. **Có yêu cầu UV mọi lần không?** Nếu không, phiên UP-only được cấp những tính năng nào?
4. **Thiết bị hỗ trợ?** Platform authenticator, roaming hardware key, passkey đồng bộ, người dùng không có PIN/biometric?
5. **Enrollment và recovery ra sao?** Ai có quyền thêm/xóa passkey, xử lý mất máy, khóa thiết bị, đổi số điện thoại/email thế nào?
6. **Server enforce ở đâu?** Request options, lưu challenge/policy, assertion verifier, session/step-up và authorization?
7. **Có yêu cầu chính sách device/attestation riêng không?** UV/BE/BS không đủ để trả lời câu hỏi độ tin cậy của thiết bị.
8. **Kiểm thử ca âm tính thế nào?** Bao gồm `UP=0`, `UV=0`, signature sai, challenge replay, wrong origin và account revoked.
9. **Nhật ký và quan sát?** Ghi mức xác thực/loại lỗi có kiểm soát mà không lưu raw assertions/credential material nhạy cảm.
10. **Phiên bản framework?** Đối chiếu đúng dependency và API WebAuthn của 6.4, 6.5 hoặc 7.x; không copy nguyên cấu hình khác major.

Với **passwordless passkey** chứa dữ liệu nhạy cảm, lựa chọn thông dụng là **bắt buộc UV** và kiểm chứng cờ trên server. Nếu dùng `"preferred"` vì khả năng tiếp cận, phải mô tả rõ chỗ nào chấp nhận phiên thiếu UV và chỗ nào cần step-up.

## 19. Câu hỏi tự kiểm tra

**Câu 1:** User chạm security key và nhận `UP=1, UV=0`. Có thể nói “đã nhập PIN” không?

Không. UP cho biết test hiện diện, UV mới là bằng chứng về xác minh cục bộ. Nếu policy `required`, phải từ chối assertion thiếu UV.

**Câu 2:** Browser trả `"userVerification":"required"` trong options và UI có hiển thị Face ID. Đã đủ để cấp session chưa?

Chưa. RP phải xác minh WebAuthn assertion bằng public key, challenge, origin, RP ID hash, UP và UV **trên dữ liệu đã được ký**; không dựa vào UI.

**Câu 3:** Một passkey synced có `BE=1,BS=1` liệu luôn có UV=1?

Không. Backup eligibility/state và user verification là các chiều dữ liệu khác nhau.

**Câu 4:** Tại sao `userVerification:"preferred"` không tương đương `required`?

Vì preferred có thể cho phép hoàn tất ceremony khi UV bit không bật. Required phải từ chối trường hợp đó.

**Câu 5:** User đăng ký credential với `UV=1`, sau đó login bằng cùng credential với `UV=0`. Có thể dựa vào thông tin lúc đăng ký để coi login đạt UV?

Không. Mức UV của **lần authentication hiện tại** phải được kiểm tra riêng.

**Câu 6:** Có thể xét `hasRole("ADMIN")` chỉ từ `UV=1` không?

Không. UV chứng minh một đặc tính của lần xác thực; role là quyết định authorization từ chính sách account/entitlements riêng.

**Câu 7:** Nếu một assertion có `UV=1` nhưng `origin` sai thì sao?

Phải **từ chối**. UP/UV không bù được thiếu kiểm tra origin và RP ID, chữ ký hoặc challenge.

## 20. Tóm tắt cốt lõi

- **UP = có tương tác/presence test**, không phải xác minh danh tính người sở hữu.
- **UV = authenticator đã xác minh người dùng cục bộ**, không nói rõ phương thức, không tự cấp quyền.
- `required` nghĩa server **phải từ chối** assertion thiếu UV; `preferred` và `discouraged` **không bắt buộc** UV nhưng luồng login thông thường vẫn cần UP.
- Flags ở byte 32 của `authenticatorData` và được bảo vệ bằng **chữ ký WebAuthn**. Không tin cờ tự khai từ browser.
- **Registration và authentication có chính sách UV riêng**; kiểm tra kết quả trên từng ceremony.
- Spring Security có WebAuthn/passkeys từ **6.4**; cấu hình Servlet qua `.webAuthn(...)`, nhưng dependency và API tùy biến thay đổi theo phiên bản 6.5/7.x.
- Cơ chế hợp lệ luôn phải gồm **signature, challenge, origin, RP ID, credential mapping, UP/UV policy, account status**; quyền nghiệp vụ được kiểm tra sau authentication.
- Để nâng bảo đảm cho giao dịch nhạy cảm, dùng step-up với challenge mới và xác minh UV thật, không chỉ sửa JSON options hoặc dựa vào phiên đăng nhập cũ.

## 21. Tài liệu chuẩn và API để đối chiếu

- W3C Web Authentication Level 3, Recommendation ngày 25-08-2026: https://www.w3.org/TR/webauthn-3/
- W3C WebAuthn Level 3: authenticator data flags và verification steps (xem mục Authenticator Data và Verifying an Authentication Assertion): https://www.w3.org/TR/webauthn-3/
- Spring Security 6.5 — Passkeys (Servlet), dependencies và endpoints: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html
- Spring Security 7.0 — Passkeys (Servlet), module `spring-security-webauthn`: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passkeys.html
- Javadoc Spring Security — `UserVerificationRequirement` (`REQUIRED`, `PREFERRED`, `DISCOURAGED`): https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/webauthn/api/UserVerificationRequirement.html
- Javadoc Spring Security — `PublicKeyCredentialRequestOptions`: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/web/webauthn/api/PublicKeyCredentialRequestOptions.html
- WebAuthn4J reference — user presence/user verification verification parameters: https://webauthn4j.github.io/webauthn4j/en/
- NIST SP 800-63B-4 — Authentication and Authenticator Management, WebAuthn flags và assurance: https://pages.nist.gov/800-63-4/sp800-63b.html

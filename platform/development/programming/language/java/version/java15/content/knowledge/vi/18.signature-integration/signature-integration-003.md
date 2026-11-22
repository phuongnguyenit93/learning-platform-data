# Định danh khóa, phiên bản định dạng và đổi khóa trong tích hợp chữ ký số (Java 15+)

## 1. Bài toán khi chữ ký số đi vào hệ thống thật

Khi một ứng dụng ký một chuỗi byte, việc dùng `Signature.getInstance("Ed25519")`, `initSign(...)`, `update(...)` và `sign()` mới giải quyết **một nửa** bài toán. Hệ thống nhận còn cần biết:

1. **Khóa công khai nào** được phép xác minh chữ ký? Làm sao tìm đúng khóa khi ứng dụng có hàng chục hoặc hàng trăm khóa?
2. **Phiên bản định dạng dữ liệu được ký** là phiên bản nào? Bên nhận diễn giải byte của message và header ra sao?
3. **Thuật toán và biến thể chữ ký** là gì? Bên nhận có được phép tin giá trị `alg` do bên gửi tự khai báo không?
4. Khi **xoay vòng khóa (key rotation / rollover)**, các chữ ký đã phát hành bằng khóa cũ được kiểm tra thế nào, và đến lúc nào mới ngừng chấp nhận chúng?
5. Khi khóa bị **lộ hoặc thu hồi**, phải xử lý chữ ký cũ và chữ ký mới theo chính sách nào?

Đây là bài về **tích hợp chữ ký**, chứ không chỉ về nguyên lý của EdDSA. Java 15 bổ sung Ed25519/Ed448 và các kiểu EdEC thông qua JEP 339; các API JCA này vẫn còn hiệu lực trong Java hiện hành. Khái niệm định danh khóa, định dạng đã ký và vòng đời khóa cũng áp dụng cho các hệ thống ký số khác.

**Nguyên tắc cốt lõi:** bên nhận chỉ nên dùng **public key đã có trong một tập khóa đáng tin**, được đối chiếu theo `kid` và chính sách thuật toán; tuyệt đối không lấy một public key tùy ý mà kẻ gửi kèm rồi kết luận chữ ký xác minh đúng tức là đã xác thực người gửi.

## 2. Ba chiều cần tách rõ: `kid`, `version` và `alg`

Một message đã ký có thể có cấu trúc khái niệm:

~~~text
{
  "format": "SIG1",
  "kid": "...",
  "alg": "Ed25519",
  "payload": "<base64url bytes>",
  "signature": "<base64url bytes>"
}
~~~

Đây là **mô hình minh họa**; nó không phải JSON Web Signature (JWS) hoàn chỉnh và chưa phải wire format sẵn dùng. Nếu triển khai JSON/JWS/COSE chính thức, phải tuân thủ toàn bộ chuẩn đó.

| Trường | Mục đích | Có đổi khi đổi khóa? | Quy tắc |
| --- | --- | --- | --- |
| `kid` — Key ID | Chọn bản ghi khóa công khai trong kho khóa tin cậy | **Thường có** | Không phải private key, không tự cấp quyền tin cậy |
| `format` / `version` | Nêu cách parse và xây dựng dãy byte **được ký** | **Không nhất thiết** | Đổi khi format/canonicalization/protocol thật sự thay đổi |
| `alg` | Nêu thuật toán hoặc profile ký, như Ed25519/Ed448 | Có thể có | Phải khớp với chính sách và public key tin cậy |
| `payload` | Nội dung cần xác thực | Theo mỗi thông điệp | Phải giữ byte chính xác; không ký “nội dung nhìn giống nhau” |
| `signature` | Chữ ký trên dãy byte được quy định | Theo mỗi lần ký/message | Xác minh bằng khóa được phép và đúng thuật toán |

**Không trộn lẫn ba trục:**

- **Rotation khóa**: khóa A (Ed25519) → khóa B (Ed25519 hoặc Ed448). `kid` đổi; `format=SIG1` có thể vẫn giữ nguyên.
- **Nâng format**: `SIG1` → `SIG2` do thay byte encoding, canonicalization hoặc trường dữ liệu. Có thể vẫn dùng cùng khóa, nhưng phải quản lý được phiên bản và tính tương thích.
- **Đổi thuật toán**: Ed25519 → Ed448. Đây là thay đổi profile mật mã, có thể đi cùng rotation nhưng **không tự buộc phải thay wire format** nếu format được thiết kế cho nhiều thuật toán.

Điều này rất quan trọng khi có nhiều phiên bản ứng dụng chạy song song trong giai đoạn deploy.

## 3. `kid`: định danh khóa chứ không phải bằng chứng khóa đáng tin

`kid` là chuỗi định danh giúp verifier **tìm khóa phù hợp**. RFC 7517 (JSON Web Key, mục 4.5) cho phép dùng `kid` để chọn khóa trong JWK Set khi rollover; **cấu trúc của giá trị `kid` không bị quy định cố định**, nhưng các khóa khác nhau nên có định danh khác nhau trong cùng phạm vi sử dụng.

Có hai cách hay gặp:

### 3.1. ID do hệ thống quản lý cấp

~~~text
tenant-west:signing:2026-11
tenant-west:signing:2027-02
~~~

Giá trị là nhãn nghiệp vụ được cấp phát **duy nhất trong phạm vi trust domain**, ví dụ một issuer/tenant/ứng dụng. Phải lưu ánh xạ bền vững:

~~~text
(issuer, kid) → publicKey, allowedAlgorithm, lifecycleStatus,
                validFrom, validUntil, policyVersion
~~~

Một `kid` **không đủ duy nhất toàn cầu** nếu mỗi tenant đều có `"key-1"`. Verifier cần biết **issuer/trust domain đã được xác thực hoặc được chọn theo đường truyền tin cậy** trước khi truy cập kho khóa.

### 3.2. ID dẫn xuất từ fingerprint public key

Ví dụ trong bài dùng:

~~~java
String kid = Base64.getUrlEncoder().withoutPadding()
    .encodeToString(
        MessageDigest.getInstance("SHA-256")
            .digest(publicKey.getEncoded()));
~~~

Với public key Ed25519/Ed448 của provider phần mềm cho phép xuất khóa, `getEncoded()` thường là `SubjectPublicKeyInfo` (SPKI) DER, **không phải** raw public key 32/57 byte theo RFC 8032. SHA-256 trả 32 byte nên base64url **không padding** dài **43 ký tự**.

**Các điều kiện cần hiểu:**

- Fingerprint phải được tính trên **biểu diễn byte đã chuẩn hóa hoặc được quy định trước**, không lẫn giữa raw Ed25519 và SPKI DER.
- Hai đối tượng khóa toán học tương đương có thể có **biểu diễn khác nhau**; fingerprint trên định dạng khác nhau có thể khác nhau. Giao thức phải thống nhất định dạng.
- Dùng **đầy đủ SHA-256** giúp giảm nguy cơ trùng ID; nếu rút ngắn fingerprint, phải đánh giá xác suất trùng và có cơ chế phát hiện xung đột.
- Nếu provider/HSM không cho xuất public key theo định dạng này, dùng ID được cấp bởi hệ thống quản lý khóa, certificate ID hoặc phương án phù hợp **được xác thực**, không đoán ID từ một giá trị chưa có.
- **`kid` dù là hash của public key vẫn không tự chứng minh đáng tin**. Một kẻ tấn công cũng có thể tự tạo cặp khóa, tự tính `kid` và tự ký. Chỉ chấp nhận khóa khi public key đã được đưa vào **trusted registry** theo quy trình được ủy quyền.

**Không tái dùng `kid` cho một public key khác** trong cùng trust domain, kể cả khi khóa cũ đã bị thu hồi. Việc nhập khóa vào registry nên phát hiện ID trùng nhưng bytes không khớp và từ chối, để tránh thay thế khóa âm thầm.

## 4. Trust registry: dữ liệu nào cần nằm phía verifier?

Verifier cần có **danh sách công khai các khóa được ủy quyền**, được nạp từ nguồn tin cậy (cấu hình ký, KMS, JWKS đã xác thực/cố định issuer hoặc chứng chỉ đã xác thực).

Một bản ghi thường bao gồm:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `issuer` hoặc `tenant` | Phân vùng quyền tin cậy và namespace của `kid` |
| `kid` | Định danh khóa trong namespace đó |
| `publicKey` | Khóa công khai tin cậy để verify; có thể là SPKI DER hoặc handle/certificate đã xác minh |
| `allowedAlgorithm` | Ví dụ **Ed25519** hoặc **Ed448**, không được lấy tùy ý từ header |
| `status` | `ACTIVE`, `VERIFY_ONLY`, `REVOKED`, `EXPIRED` ... theo chính sách |
| `notBefore` / `notAfter` | Ràng buộc hiệu lực và giai đoạn chấp nhận theo quy tắc ứng dụng |
| `source` / `policyVersion` | Nguồn ủy quyền, audit trail và chính sách đã áp dụng |

Ví dụ quy trình xác minh:

~~~text
Nhận envelope
     │
     ▼
Kiểm tra schema/size/format phiên bản
     │
     ▼
Chọn trust domain đã xác thực → tra kid
     │
     ▼
Lấy publicKey, algorithm và status từ registry tin cậy
     │
     ▼
Đối chiếu alg trong header với thuật toán được phép
     │
     ▼
Xây chính xác byte đã ký theo format version
     │
     ▼
Signature.initVerify(trustedPublicKey)
Signature.update(signedBytes)
Signature.verify(signature)
     │
     ▼
Áp dụng time/policy/replay checks → chấp nhận hoặc từ chối
~~~

**Phải từ chối `kid` không biết**, không tự gửi HTTP tới URL do message chỉ định để tải khóa mới về một cách không kiểm soát. Việc nhập khóa mới phải là hành động **quản trị có xác thực** hoặc cập nhật tự động qua **nguồn được pin và bảo vệ**, không phải quyết định của chính kẻ gửi message.

Trong mô hình nhiều tenant, phải chọn khóa trong **đúng namespace**, không cho một chữ ký hợp lệ ở tenant B được chấp nhận cho tenant A chỉ vì cùng chuỗi `kid`.

## 5. Versioning: ký chính xác byte nào và vì sao header quan trọng?

### 5.1. Không chỉ ký payload rồi bỏ ngoài `format/kid/alg`

Một lỗi thiết kế:

~~~text
signature = Sign(privateKey, payload)
envelope  = {format, kid, alg, payload, signature}
~~~

Khi `format`, `kid` hoặc `alg` **không** nằm trong vùng ký, attacker có thể sửa metadata; có thể dẫn đến thuật toán/khóa/chính sách bị diễn giải sai. Dù một số thay đổi vẫn bị từ chối do kiểm tra khác, tốt hơn nên thiết kế **metadata quan trọng được xác thực** rõ ràng.

Thiết kế minh họa:

~~~text
signedBytes = CanonicalEncode(
    DOMAIN, formatVersion, kid, alg, payloadBytesOrCanonicalPayload
)
signature = Sign(privateKey, signedBytes)
~~~

`DOMAIN` là hằng nhận diện ngữ cảnh ứng dụng/protocol (ví dụ `demo.example/signature-envelope`). Nó giúp giảm nguy cơ một chữ ký được chấp nhận nhầm trong **một ngữ cảnh ứng dụng khác** dùng cùng khóa/byte.

**Không có một hàm `CanonicalEncode` phổ quát trong Java cho mọi format.** Hai phía phải dùng đúng quy tắc mã hóa đã công bố: field order, kiểu dữ liệu, byte order, length prefix, encoding UTF-8, dạng base64url, cách phân biệt trường vắng mặt và trường rỗng.

### 5.2. Bẫy khi nối chuỗi tùy tiện

~~~text
("ab", "c") → "abc"
("a", "bc") → "abc"
~~~

Nếu ký theo cách `kid + payload` mà không có độ dài/dấu phân cách an toàn, hai bộ trường khác nhau có thể dẫn tới **cùng dãy byte**. Ví dụ trong mục 9 dùng `DataOutputStream.writeInt(length)` theo sau bởi bytes UTF-8 từng trường, loại bỏ mơ hồ kiểu này.

Với JSON, không được tự giả định hai cách serialize bằng nhau. `{"a":1,"b":2}` và `{"b":2,"a":1}` có thể mang cùng ý nghĩa trong ứng dụng nhưng byte khác. Chọn một trong hai chiến lược:

1. **Ký chính xác byte của payload trên wire**; verifier phải có nguyên byte ban đầu, không parse rồi serialize khác trước verify.
2. **Định nghĩa/tuân thủ canonicalization chuẩn** áp dụng cho loại dữ liệu, và cả hai phía đều tạo cùng kết quả.

Không tự dùng `toString()` của Map/object làm canonicalization. Với JSON signature/JWS, tốt nhất dùng **thư viện triển khai đúng chuẩn JWS/JOSE/COSE**, thay vì tự nghĩ ra một protocol mang tên giống chuẩn.

### 5.3. Tách version format khỏi version của khóa

| Sự kiện | `kid` | `format` | Thao tác |
| --- | --- | --- | --- |
| Tạo khóa mới cùng thuật toán | Đổi | Có thể giữ | Đưa public key mới vào trusted registry |
| Đổi Ed25519 sang Ed448 | Đổi | Có thể giữ nếu format hỗ trợ | Nâng chính sách allowlist và bảo đảm provider phía nhận hỗ trợ |
| Thay canonicalization | Có thể giữ | **Nên đổi** | Mô tả rõ quy tắc build signed bytes mới |
| Thay payload schema có ảnh hưởng ký | Có thể giữ | Theo thiết kế protocol | Kiểm tra tương thích và phạm vi dữ liệu được ký |
| Thu hồi private key bị lộ | Không tái dùng ID | Không bắt buộc đổi | Ngừng ký bằng khóa cũ, áp dụng chính sách verify/revocation |

**Đừng dùng số version thay thế cho `kid`**: "v2" không chỉ ra khóa nào nếu cùng lúc có nhiều issuer/tenant hoặc nhiều khóa trong đợt rollover. **Đừng đổi `format` chỉ vì thay khóa**, vì nó có thể buộc tất cả consumer phải cập nhật parser không cần thiết.

### 5.4. Fail closed khi gặp version không biết

Nếu verifier chỉ hỗ trợ `SIG1`, envelope ghi `SIG2` phải bị từ chối với lỗi giao thức có kiểm soát. Không thử parse `SIG2` như `SIG1` một cách “cố gắng cho qua” rồi ký/xác minh theo phỏng đoán.

Với nhiều version đang được hỗ trợ, **giữ quy tắc decode và xây dựng byte độc lập theo version** trong một khoảng chuyển tiếp đã có kế hoạch. Không dùng một phép chuẩn hóa ngầm có thể thay đổi theo phiên bản thư viện/JVM mà không kiểm thử.

## 6. Quy trình đổi khóa không gây gián đoạn

Hãy xét khóa A đang dùng để ký, và chuẩn bị đổi sang khóa B.

### 6.1. Các trạng thái vòng đời

| Trạng thái | Có được ký **mới**? | Có thể verify chữ ký cũ? | Cách hiểu |
| --- | --- | --- | --- |
| `STAGED` | Không | Theo chính sách chuẩn bị | Public key đã được phân phối, chưa bật ký |
| `ACTIVE` | Có | Có | Khóa hiện được ủy quyền ký |
| `VERIFY_ONLY` | **Không** | **Có** trong thời hạn chính sách | Duy trì tương thích với message cũ |
| `REVOKED` | Không | **Không** theo chính sách chặn nghiêm ngặt | Khóa không còn đáng tin để chấp nhận |
| `RETIRED/DELETED` | Không | Phụ thuộc việc còn giữ public record/đã hết retention | Dọn private material, metadata theo chính sách |

**Đây là mô hình trạng thái của ứng dụng**, không phải các enum bắt buộc có trong Java JCA. Một tổ chức có thể có thêm `COMPROMISED`, `SUSPENDED`, hiệu lực theo thời gian hoặc phân loại theo tenant/mục đích.

**`REVOKED` không chỉ là khóa “cũ”**: khóa cũ có thể hoàn toàn an toàn nhưng không còn được dùng để ký mới (`VERIFY_ONLY`). Khóa bị thu hồi vì lộ/bị vô hiệu phải được xử lý theo chính sách nghiêm ngặt hơn.

### 6.2. Thứ tự rollout an toàn

1. **Tạo khóa B** bằng CSPRNG/provider/KMS phù hợp; không tái sử dụng private seed A.
2. **Cấp `kidB` duy nhất**, đăng ký public key B, thuật toán, chính sách và nguồn ủy quyền. Thông báo/truyền public key bằng kênh **đáng tin**, có audit và rollback plan.
3. **Phân phối public key B đến tất cả verifier trước**, nhưng vẫn để A ký. Kiểm tra mọi cụm triển khai đã nạp B và hỗ trợ thuật toán B.
4. **Chuyển signer sang B** bằng cấu hình được kiểm soát; ghi `kidB` trên message mới. Hạn chế A sang `VERIFY_ONLY`.
5. **Giữ A cho verify** trong khoảng giao thoa phù hợp với thời hạn tối đa của message cũ, cache, queue, retry và độ trễ xử lý.
6. Khi hết thời hạn hoặc theo sự kiện bảo mật, **ngừng chấp nhận A** theo chính sách; sau đó dọn private material, public registry/tombstone theo retention/audit và bảo vệ không tái cấp `kidA`.

~~~text
Thời gian ──────────────────────────────────────────────────────►

Signer:      [ ký bằng A ]─────┐
                              └─[ ký bằng B ]──────────────────►

Verifier:    [ chấp nhận A ]─────────────────┐
                         [ chấp nhận B ]─────┴──────────────────►

                         ↑
               Khóa B phải tới verifier
               TRƯỚC khi signer chuyển sang B.
~~~

Nếu signer đổi khóa trước khi những verifier còn cũ nhận được B, các chữ ký mới sẽ bị từ chối vì **unknown kid** dù thuật toán ký hoạt động đúng.

### 6.3. Hệ thống phân tán và race khi xoay vòng

- Phải có **một chỉ thị chọn khóa ký hiện hành** được quản trị rõ ràng; tránh mỗi instance tự quyết định bằng đồng hồ cục bộ không đồng bộ.
- Khi phân phối registry theo cache, có thể phát sinh giai đoạn consumer thiếu B. Thiết kế TTL, refresh, xác thực nguồn, canary, quan sát tỷ lệ `unknown kid`.
- Tách quyền **signer** (private key) và **verifier** (public key). Verifier không cần bản sao private seed.
- Duy trì log audit về ai kích hoạt/thu hồi khóa, version của registry và thời điểm thay đổi; không ghi private material.
- Không tự động thử “mọi khóa trong registry” khi `kid` không tồn tại: vừa đắt, vừa làm mờ lỗi cấu hình và tăng rủi ro nhầm phạm vi tin cậy.

### 6.4. Thu hồi vì lộ khóa là trường hợp khác rotation định kỳ

Nếu private key A bị lộ, không chỉ đưa nó sang `VERIFY_ONLY` như trường hợp xoay vòng bình thường. Một kẻ có private key bị lộ có thể tạo chữ ký mới mà về mặt mật mã giống chữ ký hợp lệ. **Chữ ký tự nó không chứng minh đã được tạo trước thời điểm lộ khóa**.

Tùy policy có thể phải:
- Ngay lập tức ngừng ký bằng A và cập nhật **revocation** đến mọi verifier.
- Từ chối chữ ký A kể cả trên dữ liệu được cho là cũ, hoặc áp dụng quy tắc lưu trữ lịch sử có **timestamp/chứng cứ thời điểm đáng tin**.
- Đánh giá lại những giao dịch đã chấp nhận, phát hành khóa B mới, thông báo sự cố và audit.
- Giữ record `kidA` ở trạng thái revoked/tombstone để tránh ID được tái sử dụng.

**Đừng mặc định chữ ký “được gửi kèm timestamp” là bằng chứng ngày ký đáng tin**: timestamp tự khai báo cũng có thể được kẻ nắm private key đặt ngược thời gian. Đối với chữ ký tài liệu lưu trữ lâu năm, cần hồ sơ chứng cứ thời gian và chính sách xác minh phù hợp.

## 7. Chống tấn công metadata và algorithm confusion

### 7.1. Không tin `alg` chỉ vì nó nằm trong envelope

Nếu message tự khai báo `alg=Ed25519` hoặc `alg=Ed448`, verifier phải:

1. Lấy `kid` trong **trust domain đã xác định**.
2. Tra **public key đã cấp quyền** và `allowedAlgorithm` của record đó.
3. **Từ chối** nếu `alg` không khớp với thuật toán được phép, hoặc thuật toán không nằm trong allowlist hệ thống.
4. Tạo `Signature` bằng **thuật toán đáng tin ở record**, không chạy bất kỳ tên thuật toán người gửi đưa vào nếu chưa so khớp.
5. Xác minh **metadata đã được ký** cùng payload, không chấp nhận việc sửa header làm thay đổi cách diễn giải.

Không bao giờ có nhánh “không biết thuật toán thì bỏ qua kiểm tra chữ ký”. Không đồng nhất `"none"`, tên alias hoặc thuật toán khác với sự hợp lệ của chữ ký. Cụ thể, trong demo `"Ed25519"` và `"Ed448"` là tên chuẩn JCA; không giả định mã định danh này cũng là giá trị `alg` đúng của JOSE trong mọi phiên bản/protocol.

### 7.2. Không chấp nhận public key trong message như nguồn tin cậy mặc định

~~~text
{ kid, alg, publicKeyFromSender, payload, signature }
~~~

Nếu verifier chỉ lấy `publicKeyFromSender` rồi gọi `verify`, attacker có thể tạo cặp khóa của riêng mình, ký payload giả và chuyển cả public key cho verifier. `verify=true` khi đó **không** cung cấp authentication theo danh tính mong muốn.

Nếu protocol thật sự chấp nhận khóa kèm message, phải có **bước chứng thực riêng** (certificate chain/issuer đã pin, trust anchor, kênh ủy quyền và chính sách liên quan). `kid` là selector, **không phải root of trust**.

### 7.3. Không dùng `kid` làm URL/path trực tiếp

Một chuỗi `kid` đến từ đối tác hoặc người dùng có thể chứa ký tự đặc biệt; **không ghép nó thành đường dẫn tệp, câu SQL, URL fetch hoặc key trong log không escape**. Hãy dùng bản ghi đã đăng ký và truy vấn có validation/parameterization. Nếu làm JWK/JWKS, chỉ lấy khóa từ **nguồn tin cậy cấu hình trước**, không chạy theo một URL bất kỳ do token tự cung cấp.

### 7.4. Giới hạn kích thước và chuẩn hóa biểu diễn

Thông điệp đầu vào có thể rất lớn hoặc sai định dạng. Nên có:
- Giới hạn byte của envelope, payload, signature và từng trường.
- Schema/version allowlist và giới hạn `kid`, `alg`.
- Kiểm tra base64url **canonical** nếu format yêu cầu, không chấp nhận nhiều biểu diễn byte tương đương mà chưa quy định.
- Parser chống trùng key JSON, trùng header, biểu diễn số khác nhau hoặc Unicode normalization ngoài hợp đồng.
- Rate limit và kiểm soát tài nguyên nếu số chữ ký xác minh lớn.

Kiểm tra dữ liệu đầu vào và chữ ký mật mã là **hai bước khác nhau**. Tránh để input thiếu/nhầm định dạng khiến verifier ném exception không xử lý, hoặc phá vỡ giới hạn tài nguyên.

## 8. Java 15+ kết nối với Ed25519/Ed448 như thế nào?

Java 15 có hỗ trợ EdDSA trong JCA nhờ JEP 339. Các API hiện hành:

| API | Vai trò | Ví dụ |
| --- | --- | --- |
| `KeyPairGenerator` | Tạo khóa bất đối xứng EdDSA | `getInstance("Ed25519")` hoặc `getInstance("Ed448")` |
| `Signature` | Ký hoặc verify byte | `getInstance("Ed25519")` / `getInstance("Ed448")` |
| `KeyFactory` | Import public key đã encode/`KeySpec` | `getInstance("Ed25519")` |
| `MessageDigest` | Tạo fingerprint nếu hệ thống chọn ID dạng hash | `getInstance("SHA-256")` |
| `PublicKey.getEncoded()` | Thường trả SPKI DER với provider xuất khóa | Dùng theo hợp đồng định danh/định dạng |
| `Base64.getUrlEncoder()` | Encode bytes thành URL-safe text | `withoutPadding()` theo format đã chọn |

Với các ứng dụng dùng `EdDSAParameterSpec` (Ed25519ctx, Ed25519ph, Ed448ph), **mode, prehash và context** cũng phải thống nhất giữa signer/verifier; đây là một phần của **profile chữ ký** cần mô tả trong protocol và chính sách khóa. Code dưới đây dùng **pure mode** Ed25519 và Ed448 để tập trung vào định danh và rotation.

**Một lưu ý hiệu năng/đúng đắn:** `Signature` là đối tượng mutable có state `initSign/verify → update → sign/verify`. Tạo instance **riêng cho mỗi thao tác** thay vì chia sẻ một `Signature` đang thay đổi giữa nhiều request. Kho public key tin cậy có thể được quản lý tập trung; phiên ký/xác minh phải cô lập theo request.

### Ký đúng bytes theo format

Bên ký phải đưa **chính dãy byte đã được chuẩn hóa** cho `Signature.update(...)`. Bên nhận xây lại đúng bytes đó. Không ký `String.getBytes()` mà thiếu charset; dùng UTF-8 hoặc encoding quy định, và không sửa newline hoặc whitespace giữa ký và verify.

Nếu message chỉ chứa bản `payloadB64`, hãy quy định rõ cả hai bên ký trên **base64url string canonical** hay trên **raw decoded payload**, và kiểm tra tính canonical. Demo chọn ký trên chuỗi `payloadB64` cùng metadata, vì envelope lưu chuỗi đó; một format khác hoàn toàn có thể chọn raw bytes miễn là cả hai bên nhất quán.

## 9. Chương trình Java đầy đủ: `kid`, format version và key rollover

Đây là demo **offline**, không dùng framework hoặc thư viện thứ ba. Nó triển khai một envelope **minh họa cho bài học**, **không tuyên bố tương thích JWS/JWT/COSE** và không thay thế thư viện protocol/validation đã được đánh giá bảo mật. Các khóa tạo bằng provider JDK khi chạy để tránh hardcode private key.

Chương trình minh họa:

1. Tạo Ed25519 key A; tạo ID bằng SHA-256 của public key SPKI DER; đăng ký trong trusted registry.
2. Ký và verify payload A với format `SIG1`, `kidA`, `alg=Ed25519`.
3. Chứng minh sửa payload, thuật toán, version hoặc `kid` không qua verify.
4. Tạo Ed448 key B, đăng ký; chuyển A sang `VERIFY_ONLY` và B sang `ACTIVE`.
5. Trong giai đoạn overlap, chữ ký A cũ **vẫn verify**, nhưng A **không còn được phép ký mới** theo policy.
6. Chữ ký mới từ B dùng Ed448, có `kidB` khác, nhưng **giữ nguyên `SIG1`**.
7. Thu hồi A; từ đó chương trình từ chối chữ ký cũ A theo **chính sách demo**, trong khi B còn hợp lệ.

### 9.1. Cách canonicalize của ví dụ

Hàm `bytesToSign` xây byte theo thứ tự cố định:

~~~text
length(DOMAIN) || UTF8(DOMAIN)
length(format) || UTF8(format)
length(kid)    || UTF8(kid)
length(alg)    || UTF8(alg)
length(payloadB64) || UTF8(payloadB64)
~~~

Trong đó `length` là số byte được ghi bằng `DataOutputStream.writeInt` (4 byte, big-endian) và `||` là nối byte. Do có prefix độ dài, việc đổi vị trí ranh giới của hai trường sẽ **không** tạo cùng chuỗi đầu vào. `DOMAIN` phân tách cách sử dụng chữ ký của ví dụ này khỏi những ứng dụng khác.

**Cảnh báo:** demo này không triển khai parser mạng hay schema validation toàn diện; các trường là object Java có sẵn. Trong production cần bổ sung parser nghiêm ngặt, giới hạn cấu trúc/độ dài, xử lý null, chống dữ liệu trùng, metadata của issuer/tenant và các bước xác thực nguồn khóa. Khi có format chuẩn được quy định, ưu tiên **thư viện tuân thủ chuẩn** thay vì đưa format này vào sản phẩm.

### 9.2. Mã hoàn chỉnh

Lưu thành **`SignatureKeyRotationDemo.java`**, tệp UTF-8:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

public class SignatureKeyRotationDemo {
    static final String FORMAT = "SIG1";
    static final String DOMAIN = "demo.example/signature-envelope";
    static final Base64.Encoder B64 = Base64.getUrlEncoder().withoutPadding();
    static final Base64.Decoder DECODER = Base64.getUrlDecoder();

    enum Status { ACTIVE, VERIFY_ONLY, REVOKED }

    static final class TrustedKey {
        final String kid;
        final String algorithm;
        final PublicKey publicKey;
        Status status;

        TrustedKey(String algorithm, PublicKey publicKey, Status status)
                throws GeneralSecurityException {
            this.kid = fingerprint(publicKey);
            this.algorithm = algorithm;
            this.publicKey = publicKey;
            this.status = status;
        }
    }

    static final class Envelope {
        final String format, kid, algorithm, payloadB64, signatureB64;

        Envelope(String format, String kid, String algorithm,
                 String payloadB64, String signatureB64) {
            this.format = format;
            this.kid = kid;
            this.algorithm = algorithm;
            this.payloadB64 = payloadB64;
            this.signatureB64 = signatureB64;
        }
    }

    static String fingerprint(PublicKey publicKey)
            throws GeneralSecurityException {
        byte[] spki = publicKey.getEncoded();
        if (spki == null) {
            throw new InvalidKeyException("This demo needs an encoded public key");
        }
        return B64.encodeToString(
                MessageDigest.getInstance("SHA-256").digest(spki));
    }

    static void putTrusted(Map<String, TrustedKey> registry, TrustedKey key) {
        TrustedKey previous = registry.putIfAbsent(key.kid, key);
        if (previous != null && !Arrays.equals(
                previous.publicKey.getEncoded(), key.publicKey.getEncoded())) {
            throw new IllegalStateException("kid collision");
        }
    }

    static void field(DataOutputStream out, String value) throws Exception {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static byte[] bytesToSign(Envelope e) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        field(out, DOMAIN);
        field(out, e.format);
        field(out, e.kid);
        field(out, e.algorithm);
        field(out, e.payloadB64);
        out.flush();
        return buffer.toByteArray();
    }

    static Envelope sign(TrustedKey trusted, PrivateKey privateKey,
                         String text) throws Exception {
        if (trusted.status != Status.ACTIVE) {
            throw new IllegalStateException("key not active for signing");
        }
        String payloadB64 = B64.encodeToString(
                text.getBytes(StandardCharsets.UTF_8));
        Envelope unsigned = new Envelope(
                FORMAT, trusted.kid, trusted.algorithm, payloadB64, "");
        Signature signer = Signature.getInstance(trusted.algorithm);
        signer.initSign(privateKey);
        signer.update(bytesToSign(unsigned));
        return new Envelope(unsigned.format, unsigned.kid,
                unsigned.algorithm, unsigned.payloadB64,
                B64.encodeToString(signer.sign()));
    }

    static boolean canonicalBase64Url(String value) {
        try {
            return B64.encodeToString(DECODER.decode(value)).equals(value);
        } catch (IllegalArgumentException badEncoding) {
            return false;
        }
    }

    static boolean verify(Envelope e, Map<String, TrustedKey> registry)
            throws Exception {
        if (!FORMAT.equals(e.format)) return false;
        if (e.payloadB64.length() > 4096
                || e.signatureB64.length() > 1024) return false;
        if (!canonicalBase64Url(e.payloadB64)
                || !canonicalBase64Url(e.signatureB64)) return false;

        TrustedKey trusted = registry.get(e.kid);
        if (trusted == null || trusted.status == Status.REVOKED) return false;
        if (!trusted.algorithm.equals(e.algorithm)) return false;

        Signature verifier = Signature.getInstance(trusted.algorithm);
        verifier.initVerify(trusted.publicKey);
        verifier.update(bytesToSign(e));
        return verifier.verify(DECODER.decode(e.signatureB64));
    }

    public static void main(String[] args) throws Exception {
        Map<String, TrustedKey> trusted = new HashMap<>();
        KeyPair pairA = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        TrustedKey keyA = new TrustedKey(
                "Ed25519", pairA.getPublic(), Status.ACTIVE);
        putTrusted(trusted, keyA);

        Envelope old = sign(keyA, pairA.getPrivate(), "Hóa đơn 42 🌿");
        boolean initialValid = verify(old, trusted);
        System.out.println("format=" + old.format);
        System.out.println("initialAlgorithm=" + old.algorithm);
        System.out.println("initialValid=" + initialValid);
        System.out.println("kidLength43=" + (old.kid.length() == 43));

        Envelope editedPayload = new Envelope(old.format, old.kid,
                old.algorithm, B64.encodeToString(
                "Hóa đơn 43 🌿".getBytes(StandardCharsets.UTF_8)),
                old.signatureB64);
        boolean payloadEditedValid = verify(editedPayload, trusted);
        System.out.println("payloadEditedValid=" + payloadEditedValid);

        Envelope editedAlgorithm = new Envelope(old.format, old.kid,
                "Ed448", old.payloadB64, old.signatureB64);
        System.out.println("algorithmEditedValid=" +
                verify(editedAlgorithm, trusted));

        Envelope editedFormat = new Envelope("SIG2", old.kid,
                old.algorithm, old.payloadB64, old.signatureB64);
        System.out.println("versionEditedValid=" + verify(editedFormat, trusted));

        Envelope unknownKid = new Envelope(old.format, "unknown-kid",
                old.algorithm, old.payloadB64, old.signatureB64);
        System.out.println("unknownKidValid=" + verify(unknownKid, trusted));

        KeyPair pairB = KeyPairGenerator.getInstance("Ed448").generateKeyPair();
        TrustedKey keyB = new TrustedKey(
                "Ed448", pairB.getPublic(), Status.ACTIVE);
        putTrusted(trusted, keyB);
        keyA.status = Status.VERIFY_ONLY;

        Envelope rotated = sign(keyB, pairB.getPrivate(), "Hóa đơn 44 🌿");
        boolean oldValidDuringOverlap = verify(old, trusted);
        boolean newValid = verify(rotated, trusted);
        System.out.println("differentKid=" + !old.kid.equals(rotated.kid));
        System.out.println("oldValidDuringOverlap=" + oldValidDuringOverlap);
        System.out.println("oldStillActiveForSigning=" +
                (keyA.status == Status.ACTIVE));
        System.out.println("newAlgorithm=" + rotated.algorithm);
        System.out.println("newFormatUnchanged=" + rotated.format.equals(old.format));
        System.out.println("newSignatureBytes=" +
                DECODER.decode(rotated.signatureB64).length);
        System.out.println("newValid=" + newValid);

        Envelope editedKid = new Envelope(old.format, keyB.kid,
                old.algorithm, old.payloadB64, old.signatureB64);
        System.out.println("kidEditedValid=" + verify(editedKid, trusted));

        keyA.status = Status.REVOKED;
        boolean oldValidAfterRevoke = verify(old, trusted);
        boolean newValidAfterRevoke = verify(rotated, trusted);
        System.out.println("oldValidAfterRevoke=" + oldValidAfterRevoke);
        System.out.println("newValidAfterRevoke=" + newValidAfterRevoke);
        System.out.println("checks=" +
                (initialValid && old.kid.length() == 43
                 && !payloadEditedValid
                 && !verify(editedAlgorithm, trusted)
                 && !verify(editedFormat, trusted)
                 && !verify(unknownKid, trusted)
                 && !old.kid.equals(rotated.kid)
                 && oldValidDuringOverlap && newValid
                 && keyA.status == Status.REVOKED
                 && "Ed448".equals(rotated.algorithm)
                 && rotated.format.equals(old.format)
                 && DECODER.decode(rotated.signatureB64).length == 114
                 && !verify(editedKid, trusted)
                 && !oldValidAfterRevoke && newValidAfterRevoke));
    }
}
~~~

### 9.3. Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 SignatureKeyRotationDemo.java
java SignatureKeyRotationDemo
~~~

Code cũng biên dịch thành công khi thay `--release 17` bằng `--release 15`, vì Ed25519/Ed448 đã có trong Java 15 và các lớp Java SE còn lại đều khả dụng. Chạy kiểm chứng trên **JDK 24** cho stdout chính xác:

~~~text
format=SIG1
initialAlgorithm=Ed25519
initialValid=true
kidLength43=true
payloadEditedValid=false
algorithmEditedValid=false
versionEditedValid=false
unknownKidValid=false
differentKid=true
oldValidDuringOverlap=true
oldStillActiveForSigning=false
newAlgorithm=Ed448
newFormatUnchanged=true
newSignatureBytes=114
newValid=true
kidEditedValid=false
oldValidAfterRevoke=false
newValidAfterRevoke=true
checks=true
~~~

### 9.4. Đọc kết quả đúng cách

- `format=SIG1`: cả trước và sau rotation đều dùng **cùng một quy tắc envelope**.
- `kidLength43=true`: fingerprint là SHA-256 của SPKI DER, base64url không padding; số ký tự ổn định 43, **giá trị cụ thể khác theo khóa mới mỗi lần chạy**.
- `initialValid=true`: verifier tra `kidA` đúng trong registry và xác minh thông điệp đã ký.
- `payloadEditedValid=false`: ký đúng bytes; chỉ sửa message đã khiến verify thất bại.
- `algorithmEditedValid=false`: header khai báo Ed448 nhưng registry cho khóa A là Ed25519, nên bị từ chối.
- `versionEditedValid=false`: verifier demo chỉ hỗ trợ `SIG1`, không tự hạ cấp/đoán `SIG2`.
- `unknownKidValid=false`: verifier **không tự chấp nhận khóa chưa đăng ký**.
- `differentKid=true`: khi sinh key B mới, định danh khóa cũng mới.
- `oldValidDuringOverlap=true`: bản ghi A ở `VERIFY_ONLY` vẫn cho phép verify message cũ trong khoảng chuyển tiếp.
- `oldStillActiveForSigning=false`: A đã ngừng là khóa ký hiện hành; trong demo `sign(...)` kiểm tra `status==ACTIVE`.
- `newAlgorithm=Ed448` và `newSignatureBytes=114`: key B dùng Ed448 với signature raw 114 byte; Ed25519 thường 64 byte.
- `newFormatUnchanged=true`: đổi thuật toán/khóa **không bắt buộc** đổi phiên bản format.
- `kidEditedValid=false`: sửa khóa mục tiêu trên envelope không tạo được chữ ký hợp lệ dưới khóa khác.
- `oldValidAfterRevoke=false`: sau khi đặt A thành `REVOKED`, verifier demo **chủ động từ chối** A dù chữ ký A có thể vẫn đúng về mặt toán học. Đây là **chính sách minh họa**, không phải quy luật chung bắt buộc cho mọi hệ thống lưu trữ chữ ký.
- `newValidAfterRevoke=true`: thu hồi A không ảnh hưởng đến khóa B đang được cho phép.
- `checks=true`: những điều kiện kiểm chứng chính trong chương trình đều đạt.

**Phạm vi bảo mật của demo:** registry chỉ là `HashMap` trong bộ nhớ, không có phân vùng issuer/tenant, xác thực quản trị, kiểm soát đồng thời, lưu bền vững, chứng cứ thời gian, schema parser, expiration hay chống replay. Nó cố ý giữ trọng tâm ở **kid + version + key rotation**. Để dùng sản xuất, các lớp quản lý khóa, parser và policy này cần được triển khai/thẩm định riêng.

## 10. Phân biệt xác minh mật mã với xác minh nghiệp vụ

`Signature.verify(...) == true` chỉ cho biết chữ ký hợp lệ trên các byte đã cho với public key đang dùng; hệ thống **chưa nên chấp nhận hành động** nếu chưa kiểm tra:

- Public key thuộc **đúng issuer/tenant** được ủy quyền cho loại giao dịch này.
- `kid`, thuật toán và trạng thái khóa đang được policy cho phép.
- Message đúng **phiên bản schema/format** và không vi phạm giới hạn dữ liệu.
- Thời điểm hiệu lực, mục đích ký, tài khoản/người dùng, audience và quyền thực hiện hành động.
- Timestamp, nonce, transaction ID hoặc một cơ chế chống replay được **ký và được kiểm tra server-side**.
- Định dạng nội dung ký phù hợp với những byte thực sự được xử lý (tránh trường hợp verify một byte string nhưng xử lý một object parse khác).

Chữ ký hợp lệ **không tự chống replay**, không mã hóa dữ liệu và không tạo ra danh tính đáng tin cho public key đến từ nguồn chưa được xác thực.

Đối với dữ liệu lưu trữ dài hạn, cần phân biệt:
- **Tính hợp lệ mật mã tại thời điểm kiểm tra**.
- **Trạng thái khóa tại thời điểm phát hành**.
- **Trạng thái khóa hiện tại**.
- **Chính sách chấp nhận lịch sử** cùng chứng cứ thời gian tin cậy, quy định của nghiệp vụ/pháp lý.

Không dùng mỗi trường `createdAt` do bên gửi tự khai báo làm bằng chứng chữ ký đã tồn tại trước khi khóa bị lộ.

## 11. Các bẫy khi tích hợp với JWS/JWT, JWKS và định dạng khác

RFC 7517 quy định `kid` trong JSON Web Key để định danh và chọn khóa trong một tập khóa, đặc biệt hữu ích khi rollover. RFC 7515 quy định JSON Web Signature (JWS) và cách xây dựng **JWS Signing Input**.

Tuy nhiên:

- **`kid` không mặc định là SHA-256 của SPKI** trong JWK/JWS. Ví dụ bài chọn phương án này **cho custom envelope**; hệ thống JWK có thể dùng ID opaque do issuer cấp.
- `"Ed25519"` / `"Ed448"` là các **tên thuật toán JCA** trong Java; tên thuật toán/profile trong **JOSE/COSE** phải tuân theo registry và phiên bản đặc tả của hệ sinh thái tương ứng. Đừng copy nguyên chuỗi tên JCA vào JWS `alg` mà chưa kiểm tra chuẩn được giao thức yêu cầu.
- **Không dùng hàm `bytesToSign(...)` của demo để tạo JWS**. JWS đã có quy tắc mã hóa protected header và payload để xây đúng signing input.
- Nếu nhận JWKS qua mạng, phải biết **issuer và endpoint tin cậy** từ cấu hình/chứng thực. Không lấy URL do message tự cung cấp rồi tin bất kỳ public key nào từ đó.
- Đừng chọn public key chỉ dựa trên `kid` nếu một registry có nhiều tenant. Phải xác định namespace và chính sách tin cậy từ đúng đối tác.
- Key rotation của JWKS cần cân nhắc cache, thời gian phân phối và đồng bộ giữa signer/verifier; không xóa khóa A ngay sau khi B xuất hiện nếu message A còn hợp lệ theo policy.
- Nếu format bao gồm certificate chain, yêu cầu xác minh certificate path/hostname/usage tương ứng **không biến mất** chỉ vì chữ ký EdDSA verify thành công.

**Chọn đúng cấp độ trừu tượng:** sử dụng thư viện JWS/JOSE/COSE được bảo trì nếu ứng dụng thật sự dùng những giao thức này; code tự xây envelope trong bài dùng để hiểu các quyết định kiến trúc, không phải lựa chọn mặc định cho sản phẩm.

## 12. Lỗi phổ biến và cách phòng tránh

| Cách làm sai | Cách đúng |
| --- | --- |
| Dùng `kid` từ message để tin luôn khóa do sender đưa kèm | Tra từ trusted registry/issuer đã xác thực |
| Dùng `kid` làm secret | `kid` là **metadata công khai**, không chứa private key |
| Tái cấp `kid` cũ cho khóa mới | Gán ID duy nhất; giữ tombstone khi cần |
| Coi `kid` là hash mặc định bắt buộc theo RFC 7517 | `kid` có thể do ứng dụng cấp; format không cố định |
| Trộn version format với key version | Quản lý `format`, `kid` và `alg` riêng |
| Ký mỗi payload, để `alg/format/kid` nằm ngoài vùng được xác thực | Xác thực metadata quan trọng và byte payload bằng quy tắc rõ ràng |
| Ghép nhiều trường mà không có framing | Dùng length prefix/canonical encoding chuẩn |
| Tin `alg` trong header để chọn bất kỳ thuật toán nào | Đối chiếu allowlist và thuật toán của trusted key |
| Tự cho phép `SIG2` vì parser gần giống `SIG1` | Fail closed đối với version không hỗ trợ |
| Chuyển signer sang B trước khi verifier biết B | Phân phối B trước, chuyển signer sau |
| Xóa public key A ngay khi B bắt đầu ký | Giữ A verify-only trong thời hạn giao thoa nếu policy cho phép |
| Giữ khóa lộ ở `VERIFY_ONLY` như rotation thông thường | Đánh giá/từ chối theo revocation policy và xử lý sự cố |
| Dựa vào timestamp tự khai báo để tin chữ ký trước khi lộ khóa | Dùng chứng cứ thời gian đáng tin khi cần |
| Tự tải khóa từ URL trong token/message không xác thực | Chỉ dùng source đã pin/kiểm soát theo issuer |
| Cho rằng `Signature.verify=true` là đủ cho mọi hành động | Kiểm tra issuer, quyền, schema, thời gian và chống replay |
| Dùng `String.getBytes()` không nhất quán | Ký đúng bytes với encoding/canonicalization được quy định |

## 13. Checklist triển khai và kiểm thử key rotation

**Trước khi bật khóa mới:**

- Định nghĩa trust domain/issuer và quy tắc tạo `kid`.
- Xác định định dạng public key, thuật toán, profile EdDSA và phiên bản envelope.
- Provision B qua kênh tin cậy tới các verifier; kiểm tra signer vẫn dùng A trong giai đoạn provision.
- Kiểm tra latency/cache/JWKS refresh và khả năng verify B từ từng cụm.
- Ghi audit event khi tạo, đăng ký, kích hoạt, chuyển trạng thái và hủy khóa; không để lộ private seed.

**Khi chuyển đổi:**

- Bật B làm khóa ký hiện hành, A thành verify-only.
- Ký test message bằng B và xác minh ở tất cả verifier.
- Tiếp tục verify message cũ bằng A trong khoảng chuyển tiếp đã được phê duyệt.
- Theo dõi số lượng `unknown kid`, lỗi thuật toán không khớp, version không hỗ trợ, verify failure, key registry lag và lỗi HSM/provider.

**Trước khi thu hồi/xóa A:**

- Xác nhận policy retention, thời gian hết hạn của message, queue/retry và nhu cầu kiểm toán/lưu trữ.
- Nếu khóa bị compromise, thực hiện quy trình sự cố thay vì áp dụng máy móc lịch đổi định kỳ.
- Cập nhật chính sách chấp nhận A đến tất cả verifier; bảo đảm không vô tình cấp lại `kidA`.

**Các bài kiểm thử nên chạy:**

1. Chữ ký đúng với khóa A/B → thành công trong giai đoạn được phép.
2. Sửa payload byte → thất bại.
3. Sửa `alg`, `kid`, `format` → thất bại.
4. `kid` không có trong registry → từ chối.
5. B chưa được provision → verifier từ chối; sau provision → verifier chấp nhận.
6. A chuyển `VERIFY_ONLY` → không ký mới nhưng có thể verify message cũ theo policy.
7. A chuyển `REVOKED` → từ chối theo policy nghiêm ngặt đã chọn.
8. Hai tenant cùng ID nhưng khác key → không có lỗi nhầm namespace.
9. Chữ ký đúng nhưng message hết hạn/replay/không đúng audience → từ chối ở lớp nghiệp vụ.
10. Dữ liệu base64url sai, payload vượt size, version lạ, duplicate field → parser từ chối an toàn.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `kid` không đủ để xác định người ký?  
**Đáp án:** `kid` chỉ là nhãn chọn khóa. Phải có **trusted public key** đã được liên kết với issuer/tenant và quyền hạn hợp lệ.

**Câu 2.** Đổi từ Ed25519 A sang Ed448 B có bắt buộc nâng `SIG1` lên `SIG2` không?  
**Đáp án:** **Không**, nếu `SIG1` được quy định cho phép cả hai thuật toán và verifier có support/policy phù hợp. `kid` và `alg` đổi; format chỉ đổi nếu cách biểu diễn hoặc giao thức đổi.

**Câu 3.** Khi A không còn ký mới, có phải ngừng verify tất cả chữ ký A ngay không?  
**Đáp án:** **Không bắt buộc**. Rotation bình thường có thể giữ A ở `VERIFY_ONLY` đến hết khoảng chấp nhận. Nhưng nếu A bị lộ thì cần chính sách thu hồi nghiêm ngặt hơn.

**Câu 4.** Tại sao ký cả `format/kid/alg`?  
**Đáp án:** Vì những trường đó ảnh hưởng **cách diễn giải và xác minh thông điệp**. Chúng cần được xác thực cùng payload, hoặc được bảo vệ bằng một cơ chế tương đương do protocol quy định.

**Câu 5.** Vì sao hash SPKI DER thành `kid` vẫn chưa cho phép tin ngay public key mới?  
**Đáp án:** Hash chỉ định danh **một byte string của khóa**; ai cũng có thể tự sinh khóa và tự tính hash. Quyền tin cậy chỉ đến từ **quy trình provision/ủy quyền**.

**Câu 6.** Có thể xác nhận message “ký trước khi khóa lộ” nhờ timestamp do chính người gửi đặt trong payload không?  
**Đáp án:** **Không đủ**. Khi private key đã bị lộ, kẻ nắm nó cũng có thể tự tạo chữ ký với timestamp tự khai báo. Cần chứng cứ thời gian đáng tin phù hợp với chính sách.

## 15. Tài liệu chuẩn và API hiện hành

- **Oracle Java SE 26 — `java.security.Signature`**: ký/xác minh byte và trạng thái đối tượng. https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html
- **Oracle Java SE 26 — `java.security.KeyPairGenerator`**: sinh cặp khóa theo thuật toán. https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyPairGenerator.html
- **Oracle Java SE 26 — `MessageDigest`**: SHA-256 và cách tính digest cho fingerprint. https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/MessageDigest.html
- **OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)**, Ed25519/Ed448 có trong Java 15: https://openjdk.org/jeps/339
- **RFC 8032 — EdDSA**: Ed25519 và Ed448. https://www.rfc-editor.org/rfc/rfc8032
- **RFC 7517 — JSON Web Key**, mục `4.5` về `kid` và key rollover: https://www.rfc-editor.org/rfc/rfc7517#section-4.5
- **RFC 7515 — JSON Web Signature**, quy tắc protected header và signing input: https://www.rfc-editor.org/rfc/rfc7515
- **RFC 8410 — Algorithm Identifiers for Ed25519, Ed448, X25519, X448**, định dạng public key SPKI và private key ASN.1: https://www.rfc-editor.org/rfc/rfc8410
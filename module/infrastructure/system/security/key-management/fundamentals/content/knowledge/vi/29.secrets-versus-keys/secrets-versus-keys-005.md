# Signing secret

Trong chương **Secrets và key** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích signing secret và cách bảo vệ bí mật dùng để tạo mã xác thực thông điệp hoặc chữ ký cho request. Trong nhiều hệ thống, signing secret là khóa đối xứng dùng với HMAC; bên giữ secret có thể vừa tạo vừa xác minh mã xác thực. Vì vậy, signing secret cần được quản lý như một cryptographic key có quyền hạn rõ ràng. Cần phân biệt nó với private key của chữ ký số bất đối xứng, certificate công khai và các bí mật đăng nhập thông thường.

## 1. Signing secret là gì?

**Signing secret** là một giá trị bí mật được dùng để tạo bằng chứng mật mã cho dữ liệu hoặc request. Trong mô hình phổ biến nhất, secret là khóa đối xứng đầu vào cho HMAC (Hash-based Message Authentication Code). Bên gửi dùng secret để tạo MAC; bên nhận có cùng secret để tính lại và xác minh MAC.

Signing secret thường xuất hiện trong:

- Webhook: nhà cung cấp ký nội dung sự kiện để hệ thống nhận kiểm tra nguồn gửi và tính toàn vẹn.
- API request signing: client ký method, path, timestamp, nonce và nội dung request để server xác thực request.
- JWT dùng thuật toán HS256, HS384 hoặc HS512: cùng một secret được dùng để ký và xác minh token.
- Giao tiếp giữa các dịch vụ: hai service chia sẻ secret để tạo và kiểm tra HMAC.
- File hoặc message authentication: tạo MAC để phát hiện nội dung bị sửa đổi.

Signing secret phải có entropy cao, được sinh bằng nguồn ngẫu nhiên mật mã và chỉ được phân phối cho thành phần cần ký hoặc xác minh. Không dùng mật khẩu người dùng, API token dễ đoán hoặc chuỗi cấu hình ngắn làm HMAC key.

## 2. Signing secret, HMAC key và private signing key

Từ “signature” đôi khi được dùng rộng trong tài liệu sản phẩm để chỉ HMAC. Về mặt mật mã, HMAC là message authentication code dùng khóa bí mật chung; chữ ký số bất đối xứng sử dụng private key để ký và public key để xác minh.

| Đặc điểm | HMAC signing secret | Asymmetric signing key pair |
|---|---|---|
| Khóa tạo bằng chứng | Shared secret | Private key |
| Khóa xác minh | Cùng shared secret | Public key tương ứng |
| Ai có thể tạo chữ ký/MAC? | Bất kỳ bên nào có secret | Bên giữ private key |
| Ai có thể xác minh? | Bên có secret | Bất kỳ bên nào có public key |
| Có thể phân phối cho bên xác minh mà không cấp quyền ký? | Không | Có |
| Phù hợp | Webhook, service-to-service, API request giữa các bên đã chia sẻ secret | Phát hành token cho nhiều verifier, code signing, document signing và xác minh công khai |

HMAC cung cấp xác thực thông điệp và tính toàn vẹn giữa các bên cùng giữ secret. Nó không cung cấp non-repudiation: vì mọi bên có secret đều có thể tạo MAC hợp lệ, không thể chỉ dựa vào MAC để chứng minh duy nhất bên nào đã tạo thông điệp.

Với chữ ký số bất đối xứng, bên ký giữ private key; bên xác minh chỉ cần public key. Certificate có thể liên kết public key với danh tính thông qua CA. Certificate là dữ liệu công khai, không phải signing secret.

## 3. Signing secret là secret hay key?

Signing secret vừa là một **secret** theo cách phân loại tài sản, vừa là một **cryptographic key** theo chức năng mật mã. Hai cách gọi mô tả hai khía cạnh:

- “Secret” nhấn mạnh giá trị phải được giữ kín, kiểm soát truy cập và phân phối hạn chế.
- “Key” nhấn mạnh nó tham gia thuật toán mật mã, có thuật toán, độ dài, mục đích, phiên bản và vòng đời.

Do đó, signing secret cần được quản lý bằng quy trình key management: tạo, định danh, phân phối, sử dụng, giám sát, rotation, thu hồi và hủy. Chỉ lưu chuỗi secret trong một file cấu hình không phải là quản lý vòng đời đầy đủ.

Không dùng cùng một secret cho HMAC signing và mã hóa dữ liệu. Hai mục đích có yêu cầu và rủi ro khác nhau. Nếu cần tạo nhiều khóa từ một master secret, dùng KDF được thiết kế phù hợp và domain separation để tạo khóa riêng cho từng purpose.

## 4. HMAC hoạt động như thế nào?

HMAC kết hợp một hàm hash mật mã với khóa bí mật để tạo MAC. Với HMAC-SHA-256, đầu vào gồm secret key và message; kết quả là một tag có độ dài 256 bit.

~~~text
tag = HMAC-SHA-256(signing_secret, message)
~~~

Bên nhận dùng cùng secret và đúng message để tính tag dự kiến, sau đó so sánh với tag nhận được. Nếu message bị sửa hoặc secret không đúng, tag thường không khớp.

HMAC không mã hóa message. Nội dung vẫn có thể đọc được nếu không có lớp mã hóa khác. HMAC cũng không tự chống replay: một request hợp lệ có thể bị gửi lại nguyên vẹn nếu giao thức không ràng buộc timestamp, nonce, sequence number hoặc trạng thái đã xử lý.

~~~mermaid
flowchart LR
    A[Sender] --> B[Message]
    K[Shared signing secret] --> C[HMAC]
    B --> C
    C --> D[Message + MAC]
    D --> E[Receiver]
    K2[Cùng signing secret] --> F[Tính HMAC lại]
    E --> F
    F --> G{MAC khớp?}
    G -->|Có| H[Chấp nhận tính toàn vẹn]
    G -->|Không| I[Từ chối]
~~~

Việc MAC khớp chỉ chứng minh message được tạo bởi một bên có secret và chưa bị thay đổi theo mô hình HMAC. Ứng dụng vẫn cần kiểm tra quyền nghiệp vụ, danh tính key owner, thời hạn, replay và các ràng buộc của request.

## 5. Tạo signing secret an toàn

Signing secret nên được tạo bằng CSPRNG, có độ dài đủ cho thuật toán và policy. Với HMAC-SHA-256, một khóa ngẫu nhiên 32 byte (256 bit) là lựa chọn thực tế phổ biến. Không dùng password, UUID không được thiết kế làm key, timestamp hoặc chuỗi do con người tự nghĩ.

Ví dụ tạo secret 32 byte trong Java:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class SigningSecretGenerator {
    public static byte[] generate() {
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);
        return secret;
    }

    public static String encode(byte[] secret) {
        return Base64.getEncoder().encodeToString(secret);
    }
}
~~~

Base64 chỉ là encoding để vận chuyển hoặc lưu trữ; nó không mã hóa và không bảo vệ secret. Khi lưu trong secret manager, cần dùng cơ chế bảo vệ của dịch vụ. Khi truyền secret cho đối tác, phải dùng kênh cấp phát đã xác thực và không gửi qua ticket, log hoặc chat thông thường.

Không tái sử dụng một signing secret cho nhiều khách hàng hoặc nhiều môi trường. Secret riêng cho từng integration, tenant hoặc consumer giúp thu hẹp phạm vi ảnh hưởng khi một bên bị xâm phạm và hỗ trợ thu hồi độc lập.

## 6. Lưu trữ và phân phối signing secret

Signing secret cần nằm trong kho bí mật có kiểm soát truy cập. Lựa chọn phụ thuộc nền tảng và yêu cầu bảo mật:

| Nơi lưu | Đặc điểm | Kiểm soát cần có |
|---|---|---|
| Secret manager/vault | Cấp phát secret cho workload theo danh tính và policy | IAM tối thiểu, audit, versioning, rotation và giới hạn môi trường |
| KMS/HSM | Có thể giữ key material không exportable và thực hiện HMAC/MAC bên trong dịch vụ | Quyền MAC/verify riêng, key policy, audit và khả năng provider tích hợp |
| Encrypted configuration | Ứng dụng giải mã cấu hình khi khởi động | Bảo vệ wrapping key, quyền đọc file, log và pipeline triển khai |
| Environment variable | Cách cấp cấu hình đơn giản cho process | Hạn chế quyền xem process environment, crash dump, diagnostics và log |

Không commit secret vào Git, source code, Dockerfile, image layer, file cấu hình mẫu hoặc CI log. Không ghi secret vào exception message, tracing span, telemetry hoặc debug output.

Phân phối secret cần xác định:

- Ai là owner và bên nào được phép ký/xác minh.
- Secret ID hoặc key ID và phiên bản.
- Thuật toán HMAC được phép.
- Môi trường, tenant và phạm vi request.
- Thời điểm bắt đầu/kết thúc hiệu lực.
- Kênh cấp phát, xác nhận nhận secret và quy trình thu hồi.

Nếu provider hỗ trợ HMAC bằng key handle trong HSM/KMS, ưu tiên thao tác bên trong thiết bị để tránh export raw secret. Tuy nhiên, cần xác minh provider hỗ trợ đúng thuật toán, operation và cách xác thực workload.

## 7. Ký webhook bằng HMAC

Webhook thường gửi một payload tới endpoint của bên nhận. Nhà cung cấp có thể gửi kèm header chứa HMAC tag để bên nhận kiểm tra nội dung. Một giao thức webhook an toàn cần quy định rõ:

- Secret hoặc key ID nào được dùng.
- Chính xác byte nào được ký: raw request body, timestamp cộng body hay một canonical representation.
- Thuật toán HMAC và encoding của tag.
- Tên header và quy tắc parse.
- Cách xử lý timestamp, nonce và replay.
- Cách rotation secret trong giai đoạn hai bên chuyển đổi.

Nếu nhà cung cấp ký raw body, bên nhận phải xác minh đúng byte body nhận được trước khi parse hoặc serialize lại JSON. Parse rồi serialize có thể thay đổi khoảng trắng, thứ tự thuộc tính hoặc encoding, làm HMAC khác dù dữ liệu logic có vẻ giống nhau.

Ví dụ Java xác minh HMAC-SHA-256 cho một payload đã nhận:

~~~java
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class WebhookVerifier {
    public static boolean verify(
            byte[] rawBody,
            String suppliedTagBase64,
            SecretKey signingSecret) throws Exception {

        byte[] suppliedTag =
                Base64.getDecoder().decode(suppliedTagBase64);
        if (suppliedTag.length != 32) {
            return false;
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(signingSecret);
        byte[] expectedTag = mac.doFinal(rawBody);
        return MessageDigest.isEqual(expectedTag, suppliedTag);
    }
}
~~~

Ví dụ giả định nhà cung cấp ký raw body và mã hóa tag bằng Base64. Trong production, cần xử lý Base64 sai định dạng, header trùng lặp, kích thước body, key ID, timestamp và lỗi provider. Không dùng thuật toán hoặc encoding do request tự chọn nếu nó không nằm trong allowlist.

Độ dài tag HMAC-SHA-256 đầy đủ là 32 byte. Nếu giao thức cho phép cắt ngắn tag, phải tuân thủ đúng độ dài và policy đã thống nhất; không tự cắt tag để giảm kích thước. Dùng MessageDigest.isEqual để so sánh hai giá trị có độ dài đã được kiểm tra, tránh so sánh chuỗi thông thường có thể dừng ở byte khác đầu tiên.

## 8. Canonicalization khi ký API request

API request signing thường cần ký nhiều thành phần hơn body để tránh kẻ tấn công thay đổi phương thức, đường dẫn hoặc tham số. Hai bên phải thống nhất một canonical request format.

Một cấu trúc minh họa:

~~~text
HTTP_METHOD
CANONICAL_PATH
CANONICAL_QUERY
CONTENT_HASH
TIMESTAMP
NONCE
KEY_ID
~~~

Sau đó:

~~~text
signature = HMAC-SHA-256(signing_secret, canonical_request)
~~~

Các quy tắc canonicalization phải được định nghĩa chính xác:

- Method được chuẩn hóa theo quy tắc cố định, ví dụ chữ hoa.
- Path có quy tắc percent-encoding và xử lý dấu slash nhất quán.
- Query parameters có quy tắc sắp xếp, encoding và xử lý key lặp.
- Content hash được tính trên đúng bytes của body.
- Timestamp có định dạng, timezone và độ chính xác thống nhất.
- Nonce có entropy hoặc uniqueness phù hợp và được server kiểm tra.
- Header được chọn để ký phải có quy tắc trim/whitespace và xử lý trùng lặp.

Không ký một chuỗi ghép tùy tiện mà không có delimiter hoặc encoding không mơ hồ. Hai message khác nhau không được phép tạo cùng canonical representation do nhập nhằng phân tách trường. Có thể dùng length-prefix, định dạng chuẩn hoặc separator đã được escape theo đặc tả.

Server phải tự dựng canonical request từ request thực nhận và metadata đã kiểm tra, sau đó xác minh MAC. Không tin một canonical string do client gửi kèm mà server không tái tạo.

## 9. Signing secret trong JWT

JWT có thể dùng thuật toán HMAC như HS256, HS384 hoặc HS512. Với HS256, cùng một secret được dùng để ký và xác minh JWT. Vì mọi verifier đều cần secret, mọi verifier cũng có khả năng tạo token hợp lệ.

Điều này tạo ra khác biệt kiến trúc:

- HS256 phù hợp khi các thành phần tin cậy cùng một miền bảo mật và chấp nhận chia sẻ quyền ký.
- RS256 hoặc ES256 dùng private key để ký và public key để xác minh; có thể phân phối public key tới nhiều verifier mà không cấp quyền phát hành token.
- Nếu dùng thuật toán bất đối xứng, private key cần được bảo vệ trong KMS/HSM hoặc keystore phù hợp; public key có thể phân phối qua JWKS hoặc certificate theo giao thức.

Khi xác minh JWT:

1. Chọn thuật toán từ allowlist cấu hình phía server, không tin trường alg do token tự khai báo.
2. Chọn đúng key theo issuer, audience và key ID đã được tin cậy.
3. Xác minh chữ ký/MAC trước khi tin claims.
4. Kiểm tra issuer, audience, expiration, not-before và các claim cần thiết.
5. Áp dụng authorization riêng sau authentication.

Không dùng cùng một secret HS256 cho nhiều ứng dụng hoặc tenant nếu các miền đó không được phép phát hành token cho nhau. Nếu nhiều dịch vụ chỉ cần xác minh, cân nhắc chữ ký bất đối xứng để tránh phân phối signing secret rộng.

## 10. Chống replay và xác minh thời gian

Một HMAC hợp lệ có thể bị gửi lại. Kẻ tấn công không cần biết secret nếu họ thu thập được một request hợp lệ và gửi lại trong một ngữ cảnh mà server chấp nhận.

Các biện pháp thường dùng:

- **Timestamp:** ký timestamp cùng request và chỉ chấp nhận trong một cửa sổ thời gian ngắn.
- **Nonce:** yêu cầu nonce duy nhất cho mỗi request và lưu trạng thái đã dùng trong khoảng thời gian phù hợp.
- **Sequence number:** dùng số thứ tự tăng dần khi giao thức có trạng thái.
- **Idempotency key:** ngăn một thao tác nghiệp vụ bị thực hiện nhiều lần.
- **Expiration:** giới hạn thời gian hợp lệ của token hoặc message.
- **Request binding:** ký method, path, body hash, audience hoặc recipient để tránh chuyển request sang endpoint khác.

Timestamp đơn lẻ không luôn ngăn replay trong cửa sổ cho phép. Nếu request có tác động tài chính hoặc không thể lặp, cần nonce/idempotency state ở server. Đồng hồ giữa các hệ thống cũng cần được đồng bộ và có chính sách skew rõ ràng.

## 11. Key ID, version và nhiều signing secret

Hệ thống có thể cần nhiều secret cùng lúc để hỗ trợ nhiều đối tác, tenant hoặc giai đoạn rotation. Mỗi secret cần một định danh không bí mật, chẳng hạn key ID.

Thông tin gắn với một signing key có thể gồm:

- Key ID và version.
- Algorithm, ví dụ HmacSHA256.
- Owner, consumer hoặc tenant.
- Mục đích và phạm vi request được phép ký.
- Thời gian tạo, hiệu lực và thời điểm dự kiến retire.
- Vị trí lưu trong secret manager/KMS/HSM.
- Trạng thái active, verify-only, disabled, compromised hoặc destroyed.

Key ID giúp bên nhận chọn đúng secret mà không phải thử lần lượt mọi key. Key ID không được xem là bằng chứng tin cậy nếu client có thể tùy ý chỉ định ID; server phải ánh xạ ID vào owner, endpoint, tenant và policy đã đăng ký.

Giới hạn số key được thử khi xác minh. Không cho request tùy ý làm server quét qua một danh sách key không giới hạn, vì điều đó có thể gây tăng tải và mở rộng khả năng xác minh nhầm miền.

## 12. Signing secret rotation

Rotation thay secret cũ bằng secret mới để giới hạn thời gian sử dụng và xử lý yêu cầu vận hành. Quy trình phải phối hợp giữa bên tạo MAC và tất cả bên xác minh.

Một quy trình rotation có overlap:

1. Tạo secret mới bằng CSPRNG hoặc tạo key object mới trong KMS/HSM.
2. Gán key ID/version mới và cấu hình thuật toán, scope cùng thời điểm kích hoạt.
3. Phân phối secret mới qua kênh đã xác thực tới các bên được phép.
4. Cập nhật bên xác minh để chấp nhận key mới; có thể tạm thời chấp nhận key cũ trong giai đoạn overlap.
5. Chuyển bên ký sang dùng key mới.
6. Theo dõi request theo key ID để xác nhận không còn traffic dùng key cũ.
7. Ngừng xác minh bằng key cũ và thu hồi quyền truy cập.
8. Hủy secret cũ và các bản sao theo policy.

Trong giai đoạn overlap, key cũ chỉ nên được giữ ở trạng thái verify-only nếu giao thức và hệ thống hỗ trợ. Không để bên ký tiếp tục tạo message mới bằng key cũ sau thời điểm cutover.

Không thể “re-sign” một request cũ chỉ bằng cách đổi key ID; tag cũ được tạo từ secret cũ. Nếu message còn cần xác minh, phải giữ key cũ trong thời gian retention có kiểm soát hoặc lưu bằng chứng xác minh theo thiết kế.

## 13. Xử lý signing secret bị lộ

Nếu signing secret bị lộ, kẻ tấn công có thể tạo HMAC hợp lệ hoặc JWT hợp lệ trong phạm vi secret đó. Cần coi đây là sự cố xác thực và làm mới niềm tin.

Các bước xử lý:

1. Xác định secret ID/version, owner, ứng dụng, tenant và các bên đã nhận secret.
2. Chặn hoặc thu hồi quyền sử dụng secret bị ảnh hưởng; với KMS/HSM, disable key operation theo quy trình.
3. Tạo secret mới và phân phối qua kênh an toàn.
4. Chuyển các bên xác minh và ký sang key mới; không chấp nhận key cũ sau thời hạn khẩn cấp đã định.
5. Kiểm tra log để xác định request, token hoặc webhook bất thường đã được ký bằng key bị lộ.
6. Thu hồi token hoặc credential liên quan nếu có thể; xử lý session và hành động nghiệp vụ bị ảnh hưởng.
7. Xác minh không còn bản secret trong source, build artifact, image, backup hoặc log có thể truy cập.
8. Lưu audit và bằng chứng sự cố mà không sao chép secret vào báo cáo.

Nếu secret dùng chung cho nhiều đối tác, phạm vi ảnh hưởng rộng hơn và việc rotation có thể cần phối hợp nhiều bên. Đây là lý do nên dùng secret riêng cho từng integration hoặc tenant khi khả thi.

## 14. Phân quyền và audit

Quyền sử dụng signing secret có thể tương đương quyền giả mạo một bên trong giao thức. Do đó, quyền lấy secret và quyền gọi thao tác ký cần được kiểm soát nghiêm.

- Chỉ cấp quyền cho workload identity hoặc operator có nhiệm vụ.
- Tách quyền quản trị secret khỏi quyền sử dụng secret khi nền tảng hỗ trợ.
- Ưu tiên API HMAC trong KMS/HSM để ứng dụng không cần đọc key bytes.
- Giới hạn operation, key ID, tenant, context và môi trường.
- Yêu cầu phê duyệt nhiều bên cho key có tác động lớn hoặc key dùng chung.
- Ghi audit về principal, key ID, operation, thời điểm và kết quả.
- Không ghi secret, raw key bytes, password hoặc payload nhạy cảm vào audit log.
- Giám sát tần suất ký bất thường, sai MAC tăng đột biến và truy cập secret ngoài lịch.

Nếu một service có quyền gọi HMAC với secret trong KMS, tiến trình bị chiếm quyền vẫn có thể lạm dụng API ký. Non-exportable bảo vệ key material khỏi bị lấy ra, nhưng không tự ngăn sử dụng trái phép qua API. Cần authorization và giới hạn operation ở tầng dịch vụ.

## 15. Signing secret và encryption key

Signing secret dùng để tạo MAC, còn encryption key dùng để mã hóa/giải mã. Dù cả hai đều là cryptographic key, không nên tái sử dụng cùng một key cho cả hai mục đích.

| Tiêu chí | HMAC signing secret | Encryption key |
|---|---|---|
| Mục tiêu | Xác thực nguồn có secret và phát hiện sửa đổi | Bảo vệ tính bí mật của dữ liệu |
| Phép toán | HMAC/MAC | Cipher encryption/decryption |
| Bên nhận cần gì? | Cùng secret để xác minh MAC | Khóa giải mã hoặc cơ chế unwrap tương ứng |
| Kết quả | Authentication tag | Ciphertext, thường kèm IV/nonce và tag nếu AEAD |
| Rủi ro khi lộ | Có thể giả mạo message/token trong phạm vi key | Có thể giải mã dữ liệu hoặc mã hóa dữ liệu giả tùy quyền |

HMAC không cung cấp confidentiality. Nếu request chứa thông tin nhạy cảm, cần TLS và có thể cần mã hóa ở tầng ứng dụng. Không dùng HMAC như một cách mã hóa nội dung.

Nếu một master key cần sinh nhiều key con, dùng KDF chuẩn như HKDF với context/purpose riêng cho signing và encryption. Không chỉ cắt chuỗi hoặc dùng cùng bytes cho nhiều thuật toán.

## 16. Lỗi thường gặp

- **Dùng password làm signing secret:** entropy thấp, dễ đoán và có thể bị dò offline.
- **Dùng secret ngắn hoặc tự đặt:** không đủ sức chống brute force.
- **Đưa secret vào source code hoặc image:** bí mật bị nhân bản qua repository và pipeline.
- **Chia sẻ một secret cho mọi tenant:** compromise một tenant ảnh hưởng tới các tenant khác.
- **Nhầm HMAC với chữ ký số:** bên xác minh có secret cũng có thể tạo MAC.
- **Tin rằng HMAC mã hóa payload:** message vẫn có thể đọc được nếu không có encryption.
- **Không canonicalize request:** sender và receiver ký các biểu diễn khác nhau hoặc attacker thay đổi trường không được ký.
- **So sánh tag bằng toán tử chuỗi thông thường:** có thể tạo timing side channel.
- **Không kiểm tra độ dài tag/encoding:** chấp nhận dữ liệu lỗi hoặc định dạng không mong muốn.
- **Không chống replay:** request hợp lệ bị gửi lại để lặp hành động.
- **Tin key ID do client tự khai:** có thể chọn nhầm miền key hoặc gây thử nhiều key.
- **Rotate không có overlap hoặc kế hoạch cutover:** request hợp lệ bị từ chối hoặc key cũ tiếp tục được dùng quá lâu.
- **Xóa key cũ trước khi hoàn tất migration:** message/token còn trong thời gian hợp lệ không thể xác minh.
- **Cho rằng HSM ngăn mọi giả mạo:** ứng dụng bị chiếm quyền vẫn có thể gọi thao tác ký nếu được cấp quyền.

## 17. Ví dụ luồng webhook end-to-end

Một nhà cung cấp gửi webhook sự kiện thanh toán tới merchant. Hai bên đã cấp một HMAC secret riêng cho integration.

1. Nhà cung cấp tạo raw JSON body và timestamp.
2. Nhà cung cấp dựng message theo đặc tả, ví dụ timestamp + dấu phân cách + raw body.
3. Nhà cung cấp tính HMAC-SHA-256 bằng secret của integration.
4. Nhà cung cấp gửi body, timestamp, key ID và tag trong header.
5. Merchant kiểm tra key ID thuộc integration nào và lấy đúng secret version.
6. Merchant kiểm tra timestamp nằm trong cửa sổ cho phép.
7. Merchant tính lại HMAC trên đúng bytes và so sánh tag theo cách chống timing.
8. Merchant kiểm tra nonce/event ID đã xử lý chưa và áp dụng idempotency.
9. Chỉ sau khi MAC và replay checks đạt, merchant mới parse/ủy quyền xử lý sự kiện.
10. Khi rotation, hai bên phân phối key mới, overlap có thời hạn, cutover và retire key cũ.

Nếu attacker sửa số tiền trong body, MAC không khớp. Nếu attacker gửi lại nguyên request hợp lệ, MAC vẫn khớp; timestamp, event ID và idempotency state giúp ngăn xử lý lặp. Nếu secret bị lộ, attacker có thể tạo webhook giả cho integration đó, vì vậy cần thu hồi và rotation ngay.

## 18. Checklist vận hành signing secret

- [ ] Signing secret được xác định là HMAC/shared secret hay private signing key bất đối xứng.
- [ ] Mục đích, owner, consumer, tenant và phạm vi request được ghi nhận.
- [ ] Secret được tạo bằng CSPRNG với entropy phù hợp, không dùng password.
- [ ] Mỗi integration/tenant/môi trường có key riêng khi cần tách blast radius.
- [ ] Secret được lưu trong secret manager/KMS/HSM hoặc cơ chế đã được phê duyệt.
- [ ] Không có secret trong source, image, CI log, ticket, chat hoặc telemetry.
- [ ] Thuật toán HMAC được cố định theo allowlist và tag được kiểm tra đúng độ dài.
- [ ] Canonicalization quy định chính xác bytes được ký.
- [ ] Tag được so sánh bằng API chống timing phù hợp.
- [ ] Request có timestamp, nonce hoặc idempotency để chống replay.
- [ ] Key ID được ánh xạ tới owner và policy tin cậy phía server.
- [ ] Rotation có version, overlap, cutover, verify-only và retire rõ ràng.
- [ ] Có quy trình compromise response và thu hồi secret.
- [ ] Audit ghi key ID/operation/principal nhưng không ghi secret hoặc payload nhạy cảm.
- [ ] Signing secret được tách khỏi encryption key và các mục đích khác.

Signing secret là bí mật có quyền tạo bằng chứng xác thực cho message hoặc request. Với HMAC, mọi bên có secret đều có thể tạo và xác minh MAC, nên việc phân phối secret đồng nghĩa phân phối quyền ký. Quản lý an toàn cần tạo khóa ngẫu nhiên mạnh, tách biệt theo mục đích và miền tin cậy, bảo vệ bằng secret manager/KMS/HSM, xác minh message theo canonical format, chống replay và rotate có kế hoạch. Khi cần nhiều bên xác minh mà không trao quyền ký, nên cân nhắc chữ ký số bất đối xứng với private key được giữ riêng và public key được phân phối.

# Ảnh hưởng đến signature cũ — Đánh giá chữ ký số lịch sử khi khóa ký bị thu hồi hoặc compromise

## 1. “Ảnh hưởng đến signature cũ” là vấn đề gì?

**Ảnh hưởng đến signature cũ** là câu hỏi: **khi private signing key, chứng thư, cơ quan chứng thực hoặc hạ tầng ký bị nghi lộ, bị thu hồi, hết hạn hay xoay vòng, những chữ ký số đã tạo trước đó còn được xác minh và tin cậy đến mức nào?**

Câu trả lời không thể chỉ là **“khóa bị revoke thì mọi chữ ký cũ đều sai”** hoặc **“verify ra true thì mọi chữ ký cũ vẫn an toàn”**.

Một chữ ký lịch sử có ít nhất ba lớp đánh giá khác nhau:

1. **Tính đúng đắn mật mã:** chữ ký có khớp bytes của tài liệu và public verification key hay không?
2. **Tính tin cậy của danh tính và thời điểm:** public key đó có được ràng buộc với người/tổ chức ký tại thời điểm liên quan, chứng thư có trạng thái phù hợp, và thời gian ký có bằng chứng đáng tin không?
3. **Tính hợp lệ theo nghiệp vụ/chính sách:** người ký có thẩm quyền, nội dung được phê duyệt, giao dịch không bị thu hồi hoặc vô hiệu theo quy tắc riêng hay không?

Một private key **đã bị lộ sau ngày ký** không mặc nhiên khiến mọi phép kiểm tra chữ ký được tạo trước đó thất bại. Tuy nhiên, nếu **thời điểm lộ không thể xác định**, hoặc đối thủ có khả năng tạo chữ ký giả và gắn ngày ký do họ tự khai, hệ thống không thể tự tin kết luận một chữ ký cũ là hợp lệ chỉ dựa trên phép toán verify.

Bài thuộc chương **Revocation và compromise** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**. Chủ đề gắn với **vòng đời khóa** từ sinh, phân phối, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy; đồng thời liên hệ **mật mã bất đối xứng, chữ ký số, PKI, KMS/HSM, kiểm soát truy cập, kiểm toán và bảo vệ chứng cứ dài hạn**.

> **Nguyên tắc chính:** Phải tách **cryptographic verification**, **certificate/path validation**, **temporal evidence** và **business authorization**. Thu hồi khóa có thể thay đổi quyết định tin cậy đối với chữ ký cũ, nhưng không làm phép toán chữ ký thay đổi một cách thần kỳ.

### Mục tiêu học tập

Sau bài, người học có thể:

- Giải thích vì sao `Signature.verify()` có thể trả `true` cho một chữ ký của khóa hiện đã bị compromise.
- Phân biệt **key rotation**, **certificate expiration**, **certificate revocation**, **raw private key exposure** và **unauthorized signing API use**.
- Đánh giá dấu thời gian đáng tin cậy, CRL, OCSP và **bằng chứng xác minh tại thời điểm lịch sử**.
- Xử lý **hợp đồng điện tử, PDF ký số, artifact phần mềm, JWT/JWS và chứng thư CA** theo mục tiêu riêng.
- Lập quy trình **phân loại, cô lập, lưu chứng cứ, thay khóa, chuyển niềm tin và kiểm thử**.
- Thử ví dụ Java 11 minh họa **crypto-valid khác trusted**.

## 2. Chữ ký số được tạo và xác minh như thế nào?

Trong hệ thống ký số bất đối xứng, người ký giữ **private signing key**; các bên kiểm tra sử dụng **public verification key** tương ứng.

~~~text
Tạo chữ ký:
    S = Sign(privateKey_v1, message_or_digest, algorithm)

Kiểm tra mật mã:
    cryptoValid = Verify(publicKey_v1, message_or_digest, S, algorithm)
~~~

Các thuật toán thường gặp gồm **RSA-PSS, ECDSA và Ed25519** theo profile/giao thức được chấp thuận. Đối với ECDSA, chất lượng nonce trong quá trình ký là yếu tố cực kỳ quan trọng; đối với RSA-PSS, salt/padding/hash phải đúng profile. Không được dùng một thuật toán “verify được” như bằng chứng rằng mọi khâu quản lý khóa đều an toàn.

### Tài liệu cũ cần những gì để verify?

| Thành phần | Vai trò | Nếu thiếu |
| --- | --- | --- |
| **Bytes tài liệu được ký** | Input của phép verify | Không biết chữ ký gắn với dữ liệu nào |
| **Signature bytes** | Giá trị chữ ký | Không thể thực hiện kiểm tra mật mã |
| **Thuật toán và parameters** | Xác định cách verify | Có thể không khớp hoặc bị downgrade |
| **Public verification key** | Kiểm tra chữ ký | Không cần private key để verify |
| **Key/certificate identity** | Chọn đúng public key | Dễ chọn nhầm hoặc bị thay khóa công khai |
| **Chứng thư/path/trust** | Ràng buộc key với danh tính | `verify=true` chưa chứng minh ai ký |
| **Time/revocation evidence** | Đánh giá trạng thái theo thời gian | Khó xác minh chữ ký trước/sau sự cố |
| **Business approval/context** | Người ký có thẩm quyền ký nội dung không | Có thể là chữ ký trái phép nhưng hợp lệ mật mã |

**Không cần giữ private signing key cũ để kiểm tra một chữ ký lịch sử.** Cần giữ **public verification material và bằng chứng tin cậy phù hợp**, cùng dữ liệu/chữ ký gốc.

### Không nhầm với HMAC

HMAC dùng **shared secret** để tạo và verify MAC; bên biết secret có khả năng tạo MAC mới. HMAC không có cùng mô hình công bố **public verification key** và chứng thư PKI. Trong bài này, “signature cũ” chủ yếu nói về **chữ ký số bất đối xứng**; MAC sẽ được so sánh riêng.

## 3. Ba câu hỏi độc lập: valid, trusted và authorized

Một hệ thống kiểm tra chữ ký đầy đủ thường phải trả lời nhiều câu hỏi, không chỉ boolean.

| Câu hỏi | Phương pháp | Một kết quả có thể xảy ra |
| --- | --- | --- |
| **Crypto valid?** | Verify chữ ký với đúng public key và bytes | `VALID` hoặc `INVALID` |
| **Public key đúng người ký?** | Chứng thư, trust chain, key registry/attestation | `TRUSTED`, `UNTRUSTED`, `UNKNOWN` |
| **Key/cert hợp lệ vào thời điểm liên quan?** | Cryptoperiod, CRL/OCSP, temporal evidence | `ACCEPT`, `REJECT`, `INDETERMINATE` |
| **Thời điểm ký có đáng tin?** | Trusted timestamp và chứng cứ thời gian | `PROVEN`, `CLAIMED_ONLY`, `UNKNOWN` |
| **Nội dung được phê duyệt?** | Workflow, exact digest/manifest, role và policy | `AUTHORIZED`, `NOT_AUTHORIZED`, `UNKNOWN` |
| **Có compromise ảnh hưởng không?** | Incident record, earliest plausible exposure | `AFFECTED`, `UNDETERMINED`, `NOT_IN_SCOPE` |

Ví dụ: Một HSM đã ký tài liệu theo lệnh API trái phép. Phép `Verify()` trả `true`, nhưng **tài liệu có thể chưa được người có thẩm quyền phê duyệt**. Đây là lỗi **signing oracle/authorization**, không nhất thiết là raw private key leak.

Ngược lại, một chứng thư đã hết hạn ngày hôm nay **không tự làm thay đổi bytes/chữ ký** được tạo trong thời hạn trước đó. Việc chấp nhận chữ ký lịch sử tùy thuộc **chính sách xác minh và bằng chứng đáng tin tại thời điểm phù hợp**.

## 4. Trục thời gian của chữ ký lịch sử

Muốn đánh giá ảnh hưởng, phải làm rõ nhiều mốc **có thể khác nhau**.

~~~mermaid
flowchart LR
    A[Tạo chữ ký theo thời gian được khai] --> B[Timestamp token được TSA phát hành]
    B --> C[Mốc sớm nhất nghi private key lộ]
    C --> D[Phát hiện sự cố]
    D --> E[CA ghi revocation / trust policy thay đổi]
    E --> F[Thời điểm verifier kiểm tra]
~~~

Sơ đồ chỉ mô tả **một trình tự ví dụ**. Trong sự cố thật, thời điểm lộ có thể **sớm hơn timestamp**, không rõ, hoặc revocation được ghi sau khi đã xảy ra lạm dụng.

### Những mốc không nên gộp

- `claimedSigningTime`: thời gian ghi trong metadata do người ký/phần mềm gửi. **Không tự đáng tin**.
- `trustedTimestampTime`: thời gian do **TSA đáng tin** chứng nhận trên một message imprint đúng, với kiểm tra token và trust tương ứng.
- `earliestPlausibleExposure`: thời điểm sớm nhất mà secret có thể đã lộ; có thể `UNKNOWN`.
- `confirmedMisuseAt`: thời điểm một thao tác ký trái phép được chứng minh.
- `revocationTime`: thời điểm trạng thái chứng thư được ghi là thu hồi theo dữ liệu PKI.
- `invalidityDate`: nếu có, có thể mô tả thời điểm khóa/chứng thư bị xem là không còn an toàn theo ý nghĩa trường đó; **không phải lúc nào cũng tồn tại**.
- `validationTime`: thời điểm kiểm tra hiện tại hoặc **thời điểm lịch sử mà chính sách yêu cầu**.
- `evidenceCaptureTime`: lúc lưu CRL/OCSP, timestamp và chứng cứ vào kho archive.

**Không lấy `document.createdAt` hoặc timestamp do ứng dụng tự ghi làm bằng chứng chống backdating.**

### Ví dụ minh họa

~~~text
01/03  Hợp đồng A được ký, phần mềm ghi "signedAt=01/03"
02/03  TSA đáng tin cấp timestamp cho chữ ký A
08/03  Earliest plausible private-key exposure (theo điều tra)
10/03  Phát hiện khóa có thể bị lộ
11/03  CA công bố certificate revoked
15/03  Một verifier mở lại hợp đồng A
~~~

Nếu bằng chứng độc lập đủ mạnh cho thấy chữ ký A đã tồn tại **muộn nhất ngày 02/03** và mốc lộ sớm nhất thực sự **sau đó**, A có cơ sở tốt hơn để được xem xét lịch sử. Nhưng **không phải TSA token tự động chứng minh người ký có thẩm quyền**, và mốc lộ đôi khi không thể xác định chắc.

## 5. Những sự kiện về khóa ảnh hưởng tới signature cũ khác nhau

| Sự kiện | Bytes chữ ký cũ | Tác động tới trust |
| --- | --- | --- |
| **Rotate signing key** theo kế hoạch | Không đổi | Verifier cần giữ public key/cert cũ theo retention |
| **Certificate hết hạn** | Không đổi | Đánh giá tại thời điểm ký đáng tin, policy và chain |
| **Certificate bị revoke vì keyCompromise** | Không đổi | Nghiêm trọng: cần xét thời điểm compromise và evidence |
| **Certificate bị revoke vì cessationOfOperation** | Không đổi | Tác động tùy chính sách, khác key material leak |
| **Private key raw bị sao chép** | Không đổi | Có thể tạo chữ ký giả; khó phân biệt chữ ký hợp pháp/giả |
| **HSM Sign API bị lạm dụng** | Không đổi | Có thể có chữ ký giả dù raw private key không lộ |
| **CA issuing key bị compromise** | Không đổi | Chain/certificates/revocation evidence liên quan bị ảnh hưởng |
| **Public key được công bố** | Không đổi | Bình thường; chỉ đáng lo nếu trust/key binding bị thay |
| **Thay JWT signing key** | JWT bytes không đổi | Verifier policy/JWKS cập nhật; token cũ có thể bị từ chối |
| **Thu hồi quyền IAM ký** | Không đổi | Chặn ký mới, không thu hồi những chữ ký đã phát |
| **Xóa private key khỏi HSM** | Không đổi | Không thể ký mới; public verify vẫn có thể hoạt động |
| **Hash/signature algorithm trở nên yếu** | Không đổi | Niềm tin lâu dài có thể giảm, cần archival evidence/migration |

**Không thể có chính sách mặc định duy nhất cho mọi dòng**. Bài học là cần biết *vì sao* key/cert mất trạng thái chấp nhận, **khi nào** và **tiêu chí xác minh** của hệ thống.

## 6. Mất private key và mất quyền kiểm soát ký không giống nhau

### 6.1. Raw private key exposure

Khi attacker lấy được raw private key, họ có thể **tạo chữ ký mới ngoài hệ thống**, dùng thuật toán và định dạng được cho phép, nếu không có điều kiện hỗ trợ khác. Key có thể đã được sao chép vào nhiều nơi.

Hậu quả quan trọng:

- Có thể **giả mạo người ký** trong những domain tin cùng public key.
- Có thể **backdate một trường `signingTime` do attacker tự khai**.
- Có thể tạo token/artifact mới dù IAM/HSM nguồn đã revoke.
- Không thể “thu hồi” bản sao raw private key đã ở ngoài boundary chỉ bằng `DisableKey`.
- Cần **rotate key pair, cập nhật verifier trust, đánh giá chữ ký đã phát và xử lý key history**.

### 6.2. Signing API misuse / signing oracle

Private key **vẫn nằm trong HSM non-exportable** nhưng attacker chiếm workload credential có quyền gọi `Sign` trên digest tùy ý.

Hậu quả:

- HSM có thể tạo **chữ ký thật** trên nội dung không được phê duyệt.
- Không nhất thiết attacker có thể tiếp tục ký **sau khi credential/grant bị chặn**.
- Cần lập danh sách mọi `Sign SUCCESS`, exact digest, caller, thời điểm và approval.
- Rotation có thể hữu ích để thiết lập trust mới, **nhưng không sửa được workflow Sign thiếu authorization**.

### 6.3. Vì sao điều tra phải phân loại chính xác?

Nếu chỉ có **signing-oracle misuse**, một kết luận “raw key chắc chắn đã lộ” không được bằng chứng hỗ trợ. Nếu raw key đã bị sao chép, tuyên bố “đã revoke IAM nên ổn” lại đánh giá thiếu nguy cơ.

**Cả hai đều có thể ảnh hưởng tới chữ ký cũ, nhưng đường ứng cứu và mức độ tự tin về timestamp/identity khác nhau.**

## 7. Kiểm tra mật mã là bước cần thiết nhưng không đủ

Để verify một chữ ký số, hệ thống cần đúng:

- **Tài liệu/manifest/payload gốc** được ký, kể cả canonicalization khi định dạng có quy tắc biến đổi.
- **Thuật toán và parameters** đã được chấp thuận.
- **Signature bytes** đầy đủ.
- **Public verification key** tương ứng với private signing key đã dùng.
- Nếu là signed envelope, cần kiểm tra **những trường nào thực sự nằm trong phần được ký**.

### Một trường metadata không được ký có thể bị sửa

~~~text
Signed payload:
    invoiceId=42
    amount=500

Unsigned UI metadata:
    signerName="Finance Director"
    signingTime="2026-03-01"
~~~

Nếu attacker đổi `signerName` hoặc `signingTime` **ngoài phần dữ liệu được bảo vệ**, phép verify có thể vẫn trả true cho payload. Verifier phải hiểu **cấu trúc được ký và trường không được ký**.

### Tài liệu PDF và nhiều chữ ký

PDF có thể có **incremental updates**, nhiều revision và nhiều chữ ký. Không chỉ kiểm tra byte range của một chữ ký rồi suy ra **toàn bộ file hiện tại không có thay đổi ảnh hưởng nội dung**. Phải dùng validator hiểu signed revisions, transforms, DocMDP/FieldMDP khi có, và policy chấp nhận các thay đổi sau ký.

### Không thử mọi public key để “tìm key verify được”

Dùng **key ID, chứng thư, signer identity và context đáng tin** để chọn key. Cho token/file tự chỉ `kid` hoặc public key tùy ý rồi chấp nhận khi verify true có thể tạo **key substitution hoặc signature confusion**.

## 8. Chứng thư số, chain và thời điểm đánh giá

Khi chữ ký sử dụng PKI/X.509, public key thường nằm trong **certificate**. Một kết quả đáng tin cần đánh giá:

1. **Chứng thư của người ký** đúng identity/purpose và policy.
2. **Certificate chain** tới trust anchor được chấp thuận.
3. **Validity period** (`notBefore`, `notAfter`) của từng chứng thư tại thời điểm cần xét.
4. **Key usage / Extended Key Usage / certificate policies** theo ứng dụng và loại chữ ký.
5. **Revocation status** của các chứng thư liên quan khi chính sách yêu cầu.
6. **Thuật toán và độ mạnh** tại thời điểm liên quan, khả năng yếu đi về sau.
7. **Trusted time evidence** cho việc xác định chữ ký đã tồn tại từ khi nào.
8. **Những sự kiện CA compromise/trust-store changes** tác động đến chain.

### Certificate hết hạn hôm nay có làm signature hôm qua sai?

Không làm phép toán verify sai. Việc chấp nhận chữ ký lịch sử phụ thuộc **profile, bằng chứng thời gian, path validation policy và trạng thái thu hồi**.

Một verifier chỉ gọi `certificate.checkValidity()` ở **thời điểm hiện tại** có thể từ chối chữ ký trên chứng thư đã hết hạn, nhưng điều đó **không phải quy tắc duy nhất** cho long-term validation. Các quy trình lịch sử có thể cần đánh giá dựa trên **thời điểm ký đã được chứng minh**.

### Trust anchor không bất biến

CA root có thể bị gỡ khỏi trust store, bị điều tra compromise hoặc thay policy. Validation lịch sử đôi khi cần ghi **trust list/trust anchor state và chính sách áp dụng tại thời điểm thích hợp**, nhưng phải phân biệt **trạng thái đã được lưu** với niềm tin hiện hành của tổ chức.

## 9. CRL: hiểu đúng ngày và lý do thu hồi chứng thư

**Certificate Revocation List (CRL)** là danh sách chứng thư bị CA thu hồi, được CA ký theo cơ chế PKI. Khi đánh giá chữ ký cũ, không chỉ cần biết “certificate revoked=true”.

### Những trường cần hiểu

| Trường/khái niệm | Ý nghĩa |
| --- | --- |
| **Serial number + issuer** | Xác định chứng thư được đề cập |
| **Revocation date/time** | Thời điểm chứng thư được liệt kê thu hồi theo dữ liệu CA |
| **Reason code** | Lý do như `keyCompromise`, `cACompromise`, `cessationOfOperation`, `superseded` |
| **Invalidity date** | Nếu có, có thể nêu mốc được cho là xảy ra compromise/invalidity |
| **CRL thisUpdate/nextUpdate** | Mốc công bố và lần cập nhật dự kiến |
| **CRL signature** | Xác thực danh sách và CA/CRL signer |
| **Delta CRL** | Bản cập nhật phụ thuộc base CRL khi triển khai |
| **Issuing distribution point/scope** | Phạm vi CRL liên quan certificate |

### `revocationDate` không tự bằng “thời điểm key bị lộ”

CA có thể phát hiện sự cố ngày 10/3 và công bố revoke ngày 11/3, trong khi dấu hiệu lộ đã có từ ngày 3/3. **Revocation date là dữ liệu về hành động thu hồi**, không luôn chứng minh chính xác lúc private key mất bí mật.

Nếu có **invalidityDate** đáng tin và phù hợp policy, nó có thể cung cấp thông tin bổ sung. Nhưng **không phải CRL nào cũng có trường này**, và việc validator sử dụng thông tin ra sao tùy profile/chính sách.

### `keyCompromise` khác `superseded`

- `keyCompromise` gợi ý private key không còn đáng tin.
- `superseded` hoặc `cessationOfOperation` có thể phản ánh thay đổi vận hành.
- `cACompromise` cần xử lý phạm vi issuing authority rộng hơn.
- Một `reason` có thể vắng hoặc không đầy đủ: không mặc định lý do không được ghi nghĩa là key chắc chắn không lộ.

**Không được thiết kế “mọi chữ ký trước revocation date đều tốt”** mà bỏ qua giả thuyết lộ xảy ra sớm hơn.

## 10. OCSP: trạng thái chứng thư không phải dấu thời gian ký

**Online Certificate Status Protocol (OCSP)** cung cấp phản hồi về trạng thái chứng thư theo các semantics giao thức và profile áp dụng.

### Ba trạng thái thường gặp

- **`good`:** responder không khẳng định chứng thư bị revoked theo ngữ nghĩa OCSP tại phản hồi; không đồng nghĩa chứng thư chắc chắn được cấp hợp lệ hoặc signer có thẩm quyền.
- **`revoked`:** responder báo chứng thư bị thu hồi (kèm thông tin phù hợp).
- **`unknown`:** responder không biết trạng thái chứng thư theo yêu cầu.

### Các thời điểm trong OCSP

| Trường | Ý nghĩa |
| --- | --- |
| `thisUpdate` | Thời điểm trạng thái được biết là đúng theo phản hồi |
| `nextUpdate` | Mốc kỳ vọng có thông tin mới, nếu có |
| `producedAt` | Lúc responder tạo phản hồi |
| `revocationTime` | Thời điểm thu hồi được công bố |
| `revocationReason` | Lý do, nếu có |
| responder signature/cert | Tính xác thực phản hồi và quyền của responder |

**OCSP `good` tại một thời điểm không phải bằng chứng rằng chữ ký được tạo vào thời điểm đó**, và cũng không thể chứng minh private signing key chưa từng bị sao chép.

### Khi kiểm tra chữ ký cũ

- Xác minh chữ ký OCSP và **ủy quyền responder**.
- Đánh giá thời gian phản hồi, freshness và profile.
- Đối chiếu `CertID`, issuer, serial chính xác.
- Cân nhắc **archived OCSP/CRL evidence** nếu kiểm tra lịch sử.
- Xử lý `unknown`, timeout hoặc hết hạn evidence theo **chính sách xác minh**, không tùy tiện coi thành `good`.

**“Fail open” với OCSP/CRL** có thể tạo quyết định trust thiếu cơ sở đối với chữ ký rủi ro cao. Ngược lại, hệ thống offline cần có phương án lưu bằng chứng trước hoặc quy trình trạng thái `INDETERMINATE` rõ ràng.

## 11. Dấu thời gian đáng tin cậy — giá trị và giới hạn

**Trusted timestamp** là bằng chứng thời gian được một **Time-Stamping Authority (TSA)** hoặc cơ chế thời gian tin cậy phù hợp tạo ra và ký, thường theo **RFC 3161** hoặc profile tương ứng.

Trong mô hình phổ biến:

1. Hệ thống tính **hash/message imprint** của chữ ký hoặc đối tượng cần đóng dấu.
2. TSA xác nhận một imprint và **thời gian TSA cấp token**.
3. Bên kiểm tra xác minh token, TSA certificate, policy, hash, chain và các điều kiện thời gian.
4. Khi đối tượng khớp imprint, token có thể hỗ trợ kết luận **đối tượng đã tồn tại không muộn hơn thời điểm được TSA chứng nhận**, trong phạm vi bảo đảm và giả định của TSA.

~~~mermaid
sequenceDiagram
    participant S as Signer service
    participant TSA as Trusted TSA
    participant ARC as Evidence archive
    participant V as Historical verifier
    S->>S: Sign document bằng private signing key
    S->>TSA: Gửi message imprint theo timestamp profile
    TSA-->>S: Signed timestamp token + genTime
    S->>ARC: Lưu signature, token và trust evidence
    V->>ARC: Tải signed artifact + evidence
    V->>V: Verify signature và timestamp token/imprint
    V->>V: Xét thời điểm, revocation, compromise và policy
~~~

### Timestamp giúp gì khi key bị compromise?

Giả sử một signature có timestamp token đáng tin chứng minh **signature bytes** đã tồn tại muộn nhất ngày 01/03, còn điều tra có cơ sở vững rằng private key chỉ bị lộ sau ngày 10/03. Bằng chứng này **tăng cơ sở** để đánh giá signature tồn tại trước giai đoạn compromise.

### Timestamp không chứng minh điều gì?

- Không tự chứng minh **người có thẩm quyền** đã phê duyệt tài liệu.
- Không tự chứng minh private key **chưa bị lộ trước `genTime`**.
- Không chứng minh **nội dung ngoài phạm vi imprint** đã tồn tại vào ngày đó.
- Không đảm bảo TSA hoặc timestamp signing key **không bị compromise**.
- Không chứng minh thời gian người ký tự khai là thật.
- Không làm mất hiệu lực các sự kiện pháp lý/nghiệp vụ khác.

### Timestamp phải bao phủ đúng đối tượng

**Document timestamp**, **signature timestamp** và metadata `signingTime` có phạm vi khác nhau. Một token trên **hash tài liệu** không nhất thiết chứng minh đúng **signature bytes cụ thể** đã tồn tại ở thời điểm đó. Thiết kế LTV cần xác định **message imprint có thực sự ràng buộc chữ ký, tài liệu, signer và evidence cần thiết không**.

## 12. LTV — Long-Term Validation của chữ ký cũ

**Long-Term Validation (LTV)** là khả năng xác minh chữ ký trong thời gian dài, kể cả khi certificate đã hết hạn, URL OCSP không còn hoạt động hoặc thuật toán/hệ thống PKI đã thay đổi.

Các chuẩn và profile thường liên quan gồm **CMS/CAdES**, **XMLDSig/XAdES**, **PDF/PAdES** cùng timestamp và validation evidence. Mỗi định dạng có quy tắc đóng gói/chứng cứ riêng; không áp một parser cho mọi loại chữ ký.

### Một gói evidence có thể cần

| Evidence | Mục đích |
| --- | --- |
| Signed document / original bytes | Xác định chính xác payload được ký |
| Signature bytes và algorithm parameters | Verify mật mã |
| Signer certificate và certificate chain | Ràng buộc danh tính và trust |
| CRL/OCSP phản hồi hợp lệ theo chính sách | Tái dựng revocation status |
| Trusted signature timestamp | Chứng minh signature tồn tại không muộn hơn một mốc |
| Archive timestamp | Bảo vệ tính toàn vẹn của tập chứng cứ theo thời gian |
| Trust-list/policy version | Giải thích quyết định tại thời điểm đánh giá |
| Key compromise incident record | Xác định earliest exposure và phạm vi |
| Business approval/provenance | Xác định nội dung được phép ký |
| Evidence integrity metadata | Chống tráo đổi/gỡ bỏ chứng cứ |

### Cơ chế gia hạn chứng cứ

Với thời hạn lưu trữ dài, hash/signature algorithms và khóa TSA có thể yếu hoặc hết hạn. Một chiến lược **archive timestamp renewal/evidence renewal** có thể cần:

1. Kiểm tra bộ chứng cứ hiện tại **trước khi** thuật toán cũ không còn chấp nhận.
2. Tạo timestamp/khối chứng cứ mới bao phủ **tập bytes và evidence thích hợp**.
3. Lưu chain chứng cứ, provenance và verification policy.
4. Thử xác minh bằng verifier độc lập và xử lý algorithm deprecation.

**Không thể chữa một chữ ký đã bị giả mạo trong quá khứ chỉ bằng timestamp mới đặt ngày hôm nay**. Dấu thời gian mới chỉ cung cấp bảo đảm tương ứng với thời điểm nó được tạo và dữ liệu nó bao phủ.

## 13. Historical validation không phải “quay đồng hồ máy về ngày xưa”

Một sai lầm là đổi `system clock` về ngày ký rồi gọi thư viện `verify()`/`checkValidity()` để kết luận chữ ký cũ hợp lệ.

Đánh giá theo thời gian lịch sử đòi hỏi:

- **Thời điểm thích hợp có bằng chứng đáng tin**, không chỉ `signedAt` trong file.
- **Certificate path** và trust policy áp dụng theo trường hợp.
- **Revocation evidence** có provenance/validity phù hợp.
- **Compromise timeline** và trạng thái key/CA.
- **Algorithm strength và security policy**.
- **Tính toàn vẹn của document và mọi signed attributes**.
- **Business authorization** tại thời điểm ký.

### Các trạng thái cần có

Thay vì chỉ:

~~~text
valid = true | false
~~~

nên có kết quả dạng:

~~~text
CRYPTO_INVALID
CRYPTO_VALID_TRUST_ACCEPTED
CRYPTO_VALID_HISTORICAL_REVIEW_REQUIRED
CRYPTO_VALID_REVOKED_OR_UNTRUSTED
INDETERMINATE_MISSING_EVIDENCE
POLICY_REJECTED
~~~

Đây là **mẫu phân loại logic**, không phải enum chuẩn của mọi hệ thống. Một số giao thức quy định kết quả riêng; phải giữ semantics của profile/standards liên quan.

### “Revoked” là dữ liệu đầu vào, không tự là toàn bộ phán quyết

Cùng một chứng thư bị thu hồi có thể tạo các quyết định khác nhau cho:

- Một **hợp đồng ký có timestamp đáng tin trước mốc compromise được chứng minh**.
- Một **JWT ngắn hạn được trình bày sau khi signing key bị lộ**.
- Một **release binary bị ký trái phép đúng ngày key misuse**.
- Một **tài liệu có claimed signingTime trước sự cố nhưng không có timestamp đáng tin**.

Chính sách phải phản ánh **loại ứng dụng, thời gian và tài sản được bảo vệ**.

## 14. Kịch bản A: private signing key của cá nhân/doanh nghiệp bị lộ

Khi raw private key bị sao chép, attacker có thể tạo chữ ký mà verifier dùng public key cũ sẽ kiểm tra **đúng về mặt mật mã**.

### Các câu hỏi then chốt

1. Khóa bị lộ **sớm nhất có thể khi nào**?
2. Những chữ ký nào được tạo **trước/giữa/sau** cửa sổ nghi lộ?
3. Có timestamp đáng tin **bao phủ signature bytes** không?
4. Evidence TSA/CA có còn đáng tin và không thuộc compromise không?
5. Có bản ghi workflow/bên nhận/transaction chứng minh ý chí và thẩm quyền ký không?
6. Có chữ ký giả nào đã được gửi hoặc lưu bên ngoài không?
7. Certificate đã revoke với lý do gì, có `invalidityDate` hay thông tin incident bổ sung?
8. Có hệ thống verify nào tiếp tục chấp nhận old key mà không xét revocation không?

### Trường hợp thời điểm lộ chưa xác định

Nếu **earliest plausible exposure = UNKNOWN**, một timestamp cũ có thể chỉ chứng minh chữ ký đã tồn tại vào một ngày, **không loại trừ đối thủ đã có khóa trước ngày đó**. Khi ấy kết quả có thể là **cần review**, thay vì cố ép vào `VALID` hoặc `INVALID`.

### Không xóa khóa để “sửa chữ ký cũ”

Xóa private key ở nguồn không xóa chữ ký đã phát. Với một raw copy bị attacker giữ, họ vẫn có thể ký ngoại tuyến. Phải xử lý **trust policy, certificate revocation, verifier updates, partner notification và các output bị giả mạo**.

## 15. Kịch bản B: HSM non-exportable nhưng bị dùng ký trái phép

Đây là tình huống khác raw key exposure.

### Bối cảnh

Private key `invoice-signing-v4` được sinh và giữ trong HSM với `non-exportable`. Workload có quyền `Sign` trên digest bất kỳ, không yêu cầu `documentApprovalId`. Credential workload bị lấy.

### Điều có thể kết luận

- HSM có thể tạo **chữ ký mật mã hợp lệ** từ lệnh của attacker.
- Nếu key attributes và audit đáng tin, **chưa có căn cứ khẳng định raw key đã export**.
- Các chữ ký đã được tạo trong giai đoạn bị chiếm có thể **không được owner phê duyệt**.
- Chữ ký hợp lệ trước giai đoạn misuse có thể có **evidence nghiệp vụ riêng** để tiếp tục được xem xét.

### Điều cần làm

1. Chặn credential, grants và đường `Sign` trực tiếp.
2. Bảo toàn HSM operation logs và application workflow logs.
3. Đối chiếu **exact digest được ký** với manifest/tài liệu đã phê duyệt.
4. Xác định những output đã phát hành tới bên nhận.
5. Tạo signing key mới và giới hạn API bằng **approved digest/transaction binding**.
6. Cập nhật public verification trust và xử lý chữ ký v4 theo policy incident.
7. Thử negative tests chứng minh signer mới không ký tài liệu chưa được duyệt.

**Việc rotate key mà không sửa authorization sẽ để key mới tiếp tục bị lạm dụng.**

## 16. Kịch bản C: CA private key bị compromise

Nếu private key của **issuing CA hoặc root CA** bị compromise, phạm vi có thể rộng hơn nhiều so với một signer cuối.

### Nguy cơ

- Kẻ tấn công có thể tạo **certificates giả** dưới chain tương ứng.
- Có thể xuất hiện chứng thư mới không có trong hệ thống issuance chính thức.
- Trust vào nhiều **leaf signing certificates** và chứng cứ PKI bị ảnh hưởng.
- Việc kiểm tra CRL/OCSP cần xét **tính tin cậy của CA/CRL signer và thời gian**.
- Revocation/trust remediation có thể đòi hỏi **CA rollover, subordinate reissuance, root program updates và partner coordination**.

### Không được suy luận đơn giản

**“Leaf private key không lộ nên mọi chữ ký vẫn tốt”** có thể là kết luận sai nếu chain chứng thư bị làm giả hoặc verifier tin trust anchor bị compromise.

Ngược lại, không thể tự tuyên bố **mọi chữ ký trong toàn hệ thống vô hiệu tuyệt đối** mà chưa đánh giá scope, certificate issuance, timestamp/evidence và chính sách.

### Runbook CA incident

- Cô lập CA signing operations, access và backup/escrow.
- Điều tra key material, issuance logs, certificate transparency/audit khi áp dụng.
- Xác định affected chains, trust anchors và relying parties.
- Phát cảnh báo/revocation/reissuance theo thủ tục PKI có thẩm quyền.
- Cập nhật verifiers và trust stores với khả năng rollback có giám sát.
- Bảo toàn chứng cứ lịch sử, kể cả **public cert chains, trusted timestamps và audit**.
- Lưu lại lý do của từng quyết định tin cậy đối với các signatures cũ.

## 17. Key rotation bình thường: chữ ký cũ có cần hủy không?

**Rotation theo lịch** không đồng nghĩa key cũ bị compromise.

~~~text
Ngày 01: Signing key v1 hoạt động.
Ngày 20: Tạo signing key v2 và phân phối public key v2.
Ngày 25: Ngừng dùng v1 để tạo chữ ký mới.
Ngày 30: Verifier vẫn cần public key v1 để kiểm tra chữ ký v1.
~~~

### Reader/verifier-first cutover

Đối với hệ thống có nhiều bên nhận:

1. Chuẩn bị **public verification key/cert v2** từ nguồn đáng tin.
2. Cho verifier nhận diện `keyId/version` và **thuật toán** v2.
3. Chuyển **signing service chỉ new-sign bằng v2**.
4. Chặn workload/region cũ tiếp tục ký v1.
5. Định nghĩa **legacy verification policy** cho chữ ký v1.
6. Giữ các public key/evidence cần thiết cho retention.
7. Khi có compromise về sau, **đánh giá lại** những chữ ký v1 theo timeline mới.

### Vì sao không xóa public key v1 ngay?

Không có public verification key, người nhận có thể không kiểm tra được tài liệu đã ký v1, dù tài liệu hoàn toàn hợp lệ. Public key không phải secret; có thể được lưu trữ theo chính sách để xác minh lịch sử.

**Giữ public key để kiểm tra không đồng nghĩa tin vô điều kiện mọi chữ ký mới xuất hiện mang `kid=v1`.**

## 18. Thu hồi certificate và thu hồi key use không giống nhau

Một hệ thống có nhiều lớp “revocation”:

| Hành động | Ảnh hưởng new-use | Ảnh hưởng signature lịch sử |
| --- | --- | --- |
| Revoke IAM `Sign` permission | Chặn một đường gọi HSM/KMS | Signature bytes cũ không đổi |
| Disable signing key resource | Provider có thể chặn mọi Sign | Verify bằng public key vẫn có thể hoạt động |
| Destroy private key trong HSM | Chặn ký từ bản đó; có thể mất recovery | Không xóa public signature, không chắc xóa raw copies |
| Revoke X.509 certificate | Thay đổi trạng thái trust trong PKI | Cần policy/time/evidence để đánh giá |
| Remove key khỏi JWKS | Verifier thường không còn nhận key đó | Có thể từ chối JWT cũ dù verify toán học đúng |
| Invalidate JWT sessions/denylist | Chặn token sau thời điểm chính sách | Không làm signature token thay đổi |
| Withdraw software release trust | Chặn artifact được phân phối/chấp nhận | Artifact cũ cần inventory/evidence |
| Supersede public key/certificate | Dùng new signer để ký mới | Old signature có thể còn xác minh lịch sử |

### Khi nói “revoke signature cũ”, phải định nghĩa chính xác

Chữ ký bất đối xứng đã tạo là **bytes bất biến**. Tổ chức thường không “xóa” tính chất mật mã của chữ ký, mà **rút niềm tin, thu hồi chứng thư, ngừng chấp nhận token/artifact hoặc gắn trạng thái giao dịch bị hủy**.

Ví dụ, một hợp đồng có thể được **hủy hiệu lực bằng một hành vi pháp lý/nghiệp vụ khác**, không phải vì thuật toán ECDSA của chữ ký gốc bỗng trở nên sai.

## 19. JWT/JWS: chữ ký cũ trong token không giống hợp đồng lưu trữ dài hạn

**JSON Web Signature (JWS)** bảo vệ tính toàn vẹn/xác thực theo key và algorithm được chấp thuận. JWT có thể được ký bằng JWS và có **thời hạn sống ngắn**.

### Khi JWT signing key bị nghi lộ

Attacker giữ private key hoặc shared HMAC secret có thể phát token giả với `sub`, `aud`, `exp` hoặc claims khác. Vì vậy:

- Không chỉ chờ những token hiện có hết hạn nếu attacker **có thể tiếp tục tạo token mới**.
- Cần chặn old signing key/new-use và cập nhật **verifier trust/JWKS**.
- Khi phù hợp, thu hồi sessions/refresh tokens, denylist `jti` hoặc epoch theo issuer.
- Xác minh `iss`, `aud`, `exp`, `nbf`, token type, allowed `alg`, key source và policy.
- Không tin `kid`, `jku`, `x5u` hoặc JWK do token không đáng tin tự chỉ định mà thiếu trust restriction.
- Xét thời gian cache JWKS và **rollover giữa nhiều service/region**.

### Có nên giữ old `kid` trong JWKS không?

Nếu rotation bình thường, verifier có thể tạm cần old public key để kiểm tra token chưa hết hạn.

Nếu key bị compromise, **tiếp tục tin old key** có thể cho phép attacker tạo token giả cho tới khi trust bị cắt. Phải quyết định theo risk tier và authentication architecture, có thể chấp nhận **invalidate cả token hợp lệ** để loại bỏ rủi ro.

### `iat` trong JWT không phải trusted timestamp

Claim `iat` nằm trong payload token được ký bởi **chính key có thể đã lộ**. Attacker có private key có thể ký token với `iat` do họ tự chọn. **Không dùng `iat` làm bằng chứng độc lập rằng token được phát trước compromise**.

### JWT cũng cần provenance nghiệp vụ

Ngay cả khi JWT verify true, token có thể được cấp trái phép bởi một signing oracle. Điều tra cần liên kết **issuer logs, authorized session, event ID, credential chain**, không chỉ xem chữ ký.

## 20. Software release, container images và artifact signing

Một chữ ký cũ trên phần mềm có mục tiêu khác chữ ký tài liệu:

- Người dùng cần biết artifact có **đúng nguồn và không bị sửa**.
- Hệ thống có thể cần chính sách **release approval, build provenance, digest và transparency logs**.
- Khi signing key lộ, attacker có thể tạo **artifact độc hại nhưng chữ ký hợp lệ mật mã**.

### Những câu hỏi phải xác minh

1. **Digest chính xác** của artifact nào đã được ký?
2. Chữ ký gắn với **image digest, manifest, package hay mutable tag**?
3. Build/release pipeline có approved change và source commit provenance không?
4. Có **transparency log, independent attestation hoặc timestamp** đáng tin không?
5. Key của release đã bị lộ ở đâu và từ khi nào?
6. Những artifact đã phát hành nào phải **withdraw/quarantine/re-sign**?
7. Verifier/download client đang tin **key IDs và policy** nào?
8. Có máy khách offline hoặc bản cache cũ vẫn nhận artifact v1 không?

### Một signature hợp lệ không bảo đảm artifact an toàn

Nếu attacker có quyền dùng HSM Sign, artifact độc hại vẫn có thể được ký **bằng private key thật**. Cần ràng buộc ký với **approved digest và build provenance**, không chỉ cấp quyền `Sign` cho CI runner.

### Xử lý chữ ký release lịch sử

Một release đã có timestamp/transparency/provenance được tin cậy **trước mốc compromise** có cơ sở đánh giá khác artifact mới xuất hiện sau khi key bị lộ. Nhưng nếu **earliest exposure** không xác định, phải xét bằng chứng độc lập và quyết định trust của hệ phân phối, không tự khẳng định an toàn.

## 21. PDF, hóa đơn và hợp đồng: lịch sử chữ ký có thể được xét khác nhau

Một hợp đồng điện tử hay hóa đơn ký số thường được lưu giữ lâu hơn JWT. Các yếu tố cần đánh giá:

- Bản bytes đã ký, PDF signed revision/byte range và các thay đổi sau ký.
- Chứng thư người ký, key usage và certificate chain.
- **Trusted signature timestamp** nếu có và phạm vi token.
- CRL/OCSP, TSA evidence, trust lists hoặc chính sách ngành.
- Thời điểm nghi compromise, điều tra liệu chữ ký được tạo trước hay trong cửa sổ.
- Role/delegation/approval của người ký, quyền của tổ chức.
- Tình trạng nghiệp vụ của giao dịch, hợp đồng bị hủy/sửa hay đã hoàn tất.
- Nghĩa vụ lưu giữ và khả năng kiểm tra bằng phần mềm độc lập.

### Ba kết quả cần tách

**“Chữ ký được mã hóa đúng”** không đồng nghĩa **“người ký đã phê duyệt giao dịch”**, và cả hai không tự quyết định **“hợp đồng còn hiệu lực pháp lý”**.

Những kết luận pháp lý phụ thuộc **luật áp dụng, profile chữ ký, chính sách tin cậy, chứng cứ, hợp đồng và quy trình giải quyết tranh chấp**. Tài liệu kỹ thuật không nên hứa rằng mọi signature có TSA đều được chấp nhận pháp lý hoặc mọi cert revoked đều vô hiệu retroactively.

### Nếu chữ ký cũ đã có validation evidence

Giữ **nguyên gói chứng cứ** và kiểm tra các cơ chế integrity của nó. Không chỉ lưu ảnh “dấu xanh hợp lệ” của trình đọc PDF; giao diện có thể thay đổi theo trust store, thời điểm hoặc chính sách.

## 22. Quy trình đánh giá signature cũ sau compromise

Một workflow kiểm tra có thể bắt đầu bằng câu hỏi **“đang kiểm tra loại chữ ký nào?”**.

~~~mermaid
flowchart TD
    A[Signature lịch sử] --> B{Verify mật mã đúng?}
    B -->|Không| X[CRYPTO_INVALID hoặc dữ liệu sai]
    B -->|Có| C[Đúng key ID, signer, thuật toán và scope?]
    C -->|Không| U[UNTRUSTED / KEY_MISMATCH]
    C -->|Có| D[Kiểm tra certificate/path hoặc key registry]
    D --> E[Kiểm tra revocation, compromise timeline]
    E --> F{Có trusted time evidence hợp lệ?}
    F -->|Có| G[Đối chiếu token/imprint với thời điểm nghi lộ]
    F -->|Không| H[Không tin thời gian tự khai; review hoặc indeterminate]
    G --> I[Kiểm tra business approval và signed content]
    H --> I
    I --> J[Quyết định theo policy: accept/reject/review]
~~~

**Sơ đồ là trình tự logic**, không thay một bộ xác minh theo chuẩn PDF/CMS/XMLDSig/PKIX, cũng không khẳng định một timestamp luôn đủ để kết luận.

### Tách kiểm tra và quyết định

Nên lưu **factual findings**:

~~~text
cryptoSignatureValid       = true
signerIdentityValidated    = true
certificateRevoked         = true
revocationReason           = keyCompromise
trustedTimeEvidence        = missing
earliestExposureTime       = unknown
businessApprovalEvidence   = present
~~~

sau đó mới áp **policy** để trả trạng thái.

### Khi evidence thiếu

Trạng thái **`INDETERMINATE` hoặc `REVIEW_REQUIRED`** thường trung thực hơn việc tự động `VALID`. Một chữ ký được xác minh toán học nhưng không đủ dữ liệu về trust/time vẫn có thể cần chuyên gia kiểm tra.

## 23. Java 11+: chữ ký cũ vẫn verify được sau rotation

Ví dụ Java sau minh họa **sự độc lập giữa crypto verification và trust decision**.

- Tạo **hai cặp khóa EC P-256 riêng** cho v1 và v2.
- Ký dữ liệu bằng v1 rồi tạo chữ ký mới bằng v2.
- Kiểm tra chữ ký v1 với **public key v1** sau khi registry đánh dấu v1 `COMPROMISED`.
- Chứng minh đổi nội dung hoặc dùng public key v2 **không verify được chữ ký v1**.
- Hàm policy đặt chữ ký từ v1 vào `HISTORICAL_REVIEW_REQUIRED` dù phép verify true.

**Mã không triển khai chứng thư PKI, CRL/OCSP, TSA hoặc trusted signing time.** Nó không được dùng trực tiếp để kết luận chữ ký lịch sử được chấp nhận trong production.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;

public final class HistoricalSignatureAfterCompromiseDemo {

    enum KeyState {
        ACTIVE,
        RETIRED,
        SUSPECTED_COMPROMISE,
        COMPROMISED
    }

    enum Decision {
        CRYPTO_INVALID,
        ACCEPT_CURRENT_KEY_IN_DEMO,
        HISTORICAL_REVIEW_REQUIRED
    }

    static final class PublicKeyRecord {
        final String keyId;
        final PublicKey publicKey;
        final KeyState state;

        PublicKeyRecord(String keyId, PublicKey publicKey,
                        KeyState state) {
            this.keyId = keyId;
            this.publicKey = publicKey;
            this.state = state;
        }
    }

    static KeyPair generateP256() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"),
                new SecureRandom());
        return generator.generateKeyPair();
    }

    static byte[] sign(KeyPair signer, byte[] payload)
            throws GeneralSecurityException {
        Signature signature = Signature.getInstance("SHA256withECDSA");
        signature.initSign(signer.getPrivate(), new SecureRandom());
        signature.update(payload);
        return signature.sign();
    }

    static boolean verify(PublicKey key, byte[] payload,
                          byte[] sigBytes)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(key);
        verifier.update(payload);
        return verifier.verify(sigBytes);
    }

    static Decision decideDemo(boolean cryptoValid,
                               PublicKeyRecord key) {
        if (!cryptoValid) {
            return Decision.CRYPTO_INVALID;
        }
        if (key.state != KeyState.ACTIVE) {
            // Không tự chấp nhận dựa vào claimed signingTime.
            // Cần kiểm tra PKI, timestamp, compromise và approval.
            return Decision.HISTORICAL_REVIEW_REQUIRED;
        }
        return Decision.ACCEPT_CURRENT_KEY_IN_DEMO;
    }

    public static void main(String[] args) throws Exception {
        KeyPair oldKey = generateP256();
        KeyPair newKey = generateP256();

        byte[] document = "approved-invoice-demo"
                .getBytes(StandardCharsets.UTF_8);
        byte[] changedDocument = "altered-invoice-demo"
                .getBytes(StandardCharsets.UTF_8);

        byte[] oldSignature = sign(oldKey, document);

        // Key v1 có thể đã bị compromise: công khai v1 vẫn verify được.
        PublicKeyRecord oldRecord = new PublicKeyRecord(
                "invoice-signing-v1", oldKey.getPublic(),
                KeyState.COMPROMISED);

        PublicKeyRecord newRecord = new PublicKeyRecord(
                "invoice-signing-v2", newKey.getPublic(),
                KeyState.ACTIVE);

        boolean oldCryptoValid = verify(
                oldRecord.publicKey, document, oldSignature);
        boolean changedValid = verify(
                oldRecord.publicKey, changedDocument, oldSignature);
        boolean wrongKeyValid = verify(
                newRecord.publicKey, document, oldSignature);

        byte[] newSignature = sign(newKey, document);
        boolean newCryptoValid = verify(
                newRecord.publicKey, document, newSignature);

        System.out.println("Old signature crypto-valid: "
                + oldCryptoValid);
        System.out.println("Old signature policy: "
                + decideDemo(oldCryptoValid, oldRecord));
        System.out.println("Changed content accepted: "
                + changedValid);
        System.out.println("Old signature with new public key: "
                + wrongKeyValid);
        System.out.println("New signature crypto-valid: "
                + newCryptoValid);
        System.out.println("New signature demo-policy: "
                + decideDemo(newCryptoValid, newRecord));

        // Production phải xác thực key registry và signer identity,
        // revocation evidence, TSA, approval và incident timeline.
        // Không log private key hay tài liệu nhạy cảm.
    }
}
~~~

### Kết quả điển hình

~~~text
Old signature crypto-valid: true
Old signature policy: HISTORICAL_REVIEW_REQUIRED
Changed content accepted: false
Old signature with new public key: false
New signature crypto-valid: true
New signature demo-policy: ACCEPT_CURRENT_KEY_IN_DEMO
~~~

### Giới hạn an toàn

1. **Không có certificate chain hoặc trust store**; public keys được sinh và đưa trực tiếp vào registry demo. Production phải biết **ai sở hữu key**.
2. `COMPROMISED` chỉ là một trạng thái test; **chưa có dữ kiện về thời điểm lộ**.
3. Không có timestamp đáng tin. Mã **không được tự chấp nhận chữ ký cũ chỉ vì claimed time**.
4. Quyết định `ACCEPT_CURRENT_KEY_IN_DEMO` **không phải production trust validation**; chỉ minh họa policy.
5. Không có IAM/HSM signing boundary; private keys ở cùng JVM.
6. ECDSA chữ ký có thể khác nhau giữa các lần ký cùng payload; điều quan trọng là **verify đúng**, không so bytes chữ ký.
7. Không có audit, signed document format, chain revocation, algorithm deprecation hay retention.
8. Chữ ký đã có không tự mất khả năng verify khi key v1 bị đánh dấu compromised.
9. Nếu attacker đã có private key v1, họ có thể tạo **một signature khác cũng verify=true**; ví dụ không ngăn được điều đó.
10. Demo không chạy integration tests với provider; dùng **test vectors và PKI/TSA test environment** khi triển khai thật.

## 24. Mô hình policy kiểm tra chữ ký lịch sử

Một hệ thống quản trị chữ ký có thể lưu **policy version** riêng, không sửa signature bytes.

~~~yaml
schemaVersion: "1"
policyId: "historical-invoice-signature-validation"
revision: "v4"
signaturePurpose: "INVOICE_APPROVAL"
algorithmPolicy:
  allowedCurrentAlgorithms: ["ECDSA_P256_SHA256", "RSA_PSS_SHA256"]
  verifyAlgorithmParameters: true
identity:
  requireTrustedSignerIdentity: true
  requireApprovedRoleAtSigning: true
  checkCertificateKeyUsage: true
temporalEvidence:
  requireTrustedTimeForCompromisedKeyHistoricalAcceptance: true
  rejectSelfDeclaredSigningTimeAsSoleEvidence: true
  validateTimestampImprintAndTsaTrust: true
revocation:
  checkSignerAndRelevantIssuerStatus: true
  useVerifiedHistoricalRevocationEvidence: true
  treatUnknownAs: "INDETERMINATE"
incident:
  considerEarliestPlausibleExposureTime: true
  requireManualReviewWhenExposureTimeUnknown: true
business:
  requireApprovedDocumentDigest: true
  ensureDocumentRevisionMatchesSignedBytes: true
resultModel:
  - "CRYPTO_INVALID"
  - "TRUST_ACCEPTED"
  - "TRUST_REJECTED"
  - "HISTORICAL_REVIEW_REQUIRED"
  - "INDETERMINATE_MISSING_EVIDENCE"
audit:
  logKeyIdAndPolicyRevision: true
  prohibitRawPrivateKeyAndSensitivePayload: true
~~~

**Đây là đặc tả yêu cầu khái niệm**, không phải config dùng trực tiếp với một thư viện PKIX/PAdES/JWS bất kỳ.

### Có nên mặc định `trusted timestamp = accepted`?

Không. Một timestamp hợp lệ **không thay thế**:

- Certificate/identity trust.
- Phạm vi key purpose và business approval.
- Đánh giá liệu key đã lộ trước timestamp chưa.
- Revocation/CA/TSA compromise.
- Kiểm tra signed content và algorithm security.

**Policy phải kết hợp nhiều evidence**, thay vì một boolean `hasTimestamp`.

## 25. Key inventory và retention cho chữ ký cũ

Khi rotating/revoking signing key, cần lưu **dấu vết quan hệ key–artifact–certificate–incident**.

### Key inventory tối thiểu

| Trường | Mục đích |
| --- | --- |
| `keyId/materialVersion` | Định danh đúng private/public key pair |
| `keyPurpose` | `INVOICE_SIGNATURE`, `RELEASE_SIGNING`, `JWT_SIGNING`... |
| `keyOrigin` | Sinh trong HSM, import, restore |
| `publicVerificationMaterial` | Public key/certificate archive |
| `certificateSerial/issuer` | Tra CRL/OCSP đúng đối tượng |
| `cryptoperiod` | Khi nào key được phép ký mới |
| `keyState` | Active, retired, suspected, compromised, destroyed |
| `incidentRef` | Liên kết earliest exposure và bằng chứng |
| `trustDistribution` | JWKS, certificate chain, verifier configs |
| `artifactsSigned` | Mapping tới document digest hoặc release manifest |
| `timestampEvidenceRefs` | Token TSA và archive |
| `validationPolicyVersion` | Vì sao chữ ký được accept/reject |
| `retention/hold` | Nghĩa vụ lưu và khả năng tái xác minh |

### Tránh lưu raw private key “để verify chữ ký cũ”

Không cần raw private key để verify. Giữ private key đã nghi lộ ở nhiều nơi chỉ làm tăng rủi ro và gánh nặng custody. Cần xem **quy trình pháp chứng, nghĩa vụ lưu trữ và phục hồi** trước khi tiêu hủy key material.

### Dữ liệu backup có thể còn chữ ký cũ

PDF, email, object version, signed release, database snapshot và ledger có thể vẫn được truy cập sau nhiều năm. Nếu key v1 bị gỡ khỏi toàn bộ registry, chức năng verify history có thể hỏng. Giải pháp là **archival public key + evidence + policy**, không phải tự cho phép Sign bằng key v1 trở lại.

## 26. Audit và chứng cứ khi quyết định chữ ký cũ còn đáng tin hay không

Mỗi lần validation quan trọng nên có đủ metadata để **tái dựng kết luận**.

~~~yaml
schemaVersion: "1"
eventType: "HISTORICAL_SIGNATURE_VALIDATION"
eventId: "val-2030-0099"
documentReference: "invoice-archive-0042"
signedDigestReference: "digest-ref-0042"
signatureReference: "signature-id-22"
key:
  keyId: "invoice-signing-v3"
  certificateIssuerRef: "approved-issuer"
  certificateSerialRef: "serial-ref"
cryptography:
  algorithm: "ECDSA_P256_SHA256"
  verificationResult: "VALID"
trust:
  chainResult: "VALIDATED_FOR_SELECTED_POLICY"
  revocationResult: "REVOKED_KEY_COMPROMISE"
  trustedTimeEvidence: "PRESENT_AND_VALIDATED"
  historicalAssessment: "REVIEW_REQUIRED"
incident:
  incidentRef: "INC-2030-042"
  earliestPlausibleExposureUtc: "UNKNOWN"
business:
  approvalReference: "invoice-approval-22"
decision:
  finalResult: "HISTORICAL_REVIEW_REQUIRED"
  policyRevision: "historical-validation-v4"
observedAtUtc: "2030-05-20T08:00:00Z"
~~~

Không đưa **private key, raw DEK/KEK, confidential document plaintext, HSM PIN hoặc bearer tokens** vào audit. Với `documentReference` và `signedDigestReference`, cần quyền truy cập tương ứng để không rò PII.

### Audit “valid” phải nêu tầng nào valid

Các sự kiện nên tránh chỉ có `signatureValid=true`. Cần phân biệt:

- `cryptographicVerification`.
- `certificateChainValidation`.
- `revocationEvidence`.
- `trustedTimestampValidation`.
- `businessAuthorization`.
- `finalPolicyDecision`.

Nếu validation service báo `TRUST_ACCEPTED`, cần truy được **policy revision và evidence IDs**, không chỉ một badge xanh.

### Bảo toàn chứng cứ

Log nguồn, CA/TSA responses và incident notes cần tính toàn vẹn, retention và quyền sửa/xóa độc lập. Có thể dùng **append-only/WORM, chữ ký log, hash chain hoặc archive timestamp** khi phù hợp; các kỹ thuật này không thay thế kiểm soát quyền và tính chính xác dữ liệu gốc.

## 27. Incident response: phải làm gì với signature cũ?

Khi phát hiện private signing key bị nghi lộ hoặc signing API bị lạm dụng, có thể tổ chức theo các bước sau.

### Giai đoạn A — Cô lập và giữ bằng chứng

1. Mở incident và xác định **key ID/material version** cùng issuer/certificate.
2. Thu hồi credential/grants, chặn direct `Sign` không hợp lệ.
3. Bảo toàn **HSM/KMS Sign logs, IAM policy changes, release/transaction approvals**.
4. Xác định **raw key exposure** hay chỉ có **API signing misuse**.
5. Ghi **earliest plausible exposure**, thời điểm phát hiện và confidence.
6. Không xóa key/evidence để “làm sạch” trước khi đánh giá retention.
7. Thông báo key owner, custodian, security, PKI/release/data owner theo runbook.

### Giai đoạn B — Chuyển sang key mới

1. Sinh key pair v2 bằng nguồn tin cậy, đúng purpose, non-exportable khi yêu cầu.
2. Xác minh trust, certificate, algorithms, IAM và audit.
3. Phân phối **public verification key/certificate v2** qua kênh đáng tin.
4. Chuyển signing service sang **new-sign v2** và chặn new-sign v1.
5. Cập nhật verifier policies, JWKS/PKI/trust stores và caches.
6. Tránh fail-open sang v1 khi provider/key v2 không sẵn sàng.
7. Thử negative tests với compromised/retired key.

### Giai đoạn C — Rà soát chữ ký lịch sử

1. Lập inventory **tài liệu, JWT, release artifacts và chứng thư** gắn key v1.
2. Tách nhóm trước/giữa/sau cửa sổ nghi lộ.
3. Thu thập **trusted timestamps, CRL/OCSP, certificate chains, approvals**.
4. Đánh giá mỗi nhóm theo **policy ứng dụng**.
5. Gắn `ACCEPT`, `REJECT`, `REVIEW` hoặc `INDETERMINATE` có chứng cứ.
6. Thông báo relying parties khi cần, thu hồi token/artifacts sai phạm.
7. Lưu kết quả, policy revision, residual risk và trách nhiệm xử lý tiếp.

### Giai đoạn D — Đóng sự cố

Chỉ đóng sau khi kiểm tra **root cause**, năng lực kiểm toán, tình trạng old key, dữ liệu/chữ ký bị ảnh hưởng, các bên nhận đã cập nhật và khả năng tái xác minh lâu dài. **Rotation completed** không đồng nghĩa **historical signatures reviewed**.

## 28. Ba tình huống minh họa

### 28.1. Hợp đồng ký trước khi private key bị lộ

Doanh nghiệp ký hợp đồng A, và một TSA đáng tin đóng dấu thời gian cho **signature value**. Sau đó đội bảo mật phát hiện private signing key có thể đã bị sao chép.

**Nếu** điều tra có chứng cứ đủ tốt rằng **thời điểm sớm nhất có thể bị lộ sau trusted timestamp**, hợp đồng A có cơ sở tốt hơn để được xem xét là chữ ký lịch sử. Nhưng vẫn cần chain, revocation, business approval và hiệu lực giao dịch.

**Nếu** không xác định được thời điểm lộ, không được coi timestamp cũ tự động chứng minh người ký hợp pháp. Kết quả có thể là **historical review required**.

### 28.2. CI release signer bị dùng làm signing oracle

Private key nằm trong HSM non-exportable. Workload signing API bị chiếm, attacker gửi digest của một binary chưa được approved và được HSM ký thành công.

Bằng chứng cho thấy **chữ ký crypto-valid**, nhưng digest không xuất hiện trong release approval. Phải **thu hồi artifact, chặn signing oracle, xoay key khi phù hợp, cập nhật verifier trust và rà soát danh sách output**.

**Bài học:** Không có raw key leak vẫn có thể có chữ ký trái phép.

### 28.3. JWT signing key bị lộ cùng ngày phát hành token

Một JWT được trình bày hôm nay, chứa `iat` khai là hôm qua, chữ ký đúng dưới public key v1. Raw private key v1 đã bị xác nhận lộ.

`iat` là claim do người tạo token tự cung cấp; attacker có private key có thể tự ký claim này. **Không dùng `iat` để chứng minh token phát trước sự cố.**

Trong hệ thống xác thực, giải pháp có thể là **chấm dứt trust vào v1, chuyển issuer v2 và vô hiệu các token/session bị ảnh hưởng**. Hệ quả là một số token hợp lệ cũ bị từ chối, nhưng có thể cần thiết để ngăn token giả. Đây là quyết định khác với historical validation của hợp đồng có TSA và bằng chứng độc lập.

## 29. Kiểm thử và negative tests

Một chính sách lịch sử chỉ đáng tin khi đã kiểm thử cả **mật mã, trust, thời gian và nghiệp vụ**.

### Kiểm thử mật mã

1. Signature đúng với payload đúng và public key đúng trả `true`.
2. Thay một byte trong payload được ký làm verification thất bại.
3. Dùng public key của key version khác không xác minh được chữ ký cũ.
4. Sai thuật toán/parameters bị từ chối, không tự downgrade.
5. Signed attributes/canonicalization phù hợp đúng profile.
6. Chữ ký PDF có incremental updates phải kiểm tra **signed revision** chính xác.

### Kiểm thử trust và thời gian

1. Certificate hết hạn hôm nay, nhưng có evidence lịch sử phù hợp: trả đúng kết quả policy, không mặc định một chiều.
2. Certificate revoked `keyCompromise`: validator xét cả mốc lộ khả dĩ và timestamp evidence.
3. `claimedSigningTime` tự khai **không đủ** để chứng minh trước compromise.
4. Timestamp token bị sửa hoặc imprint khác chữ ký: bị từ chối.
5. TSA certificate/path không được tin cậy: không dùng token làm trusted time.
6. OCSP/CRL `unknown` hoặc thiếu evidence: xử lý `INDETERMINATE` theo policy.
7. `revocationDate` và `invalidityDate` có giá trị khác nhau: xử lý theo semantics, không coi như một.
8. Certificate chain có intermediate compromised hoặc trust anchor thay đổi: không chỉ validate leaf.
9. Archive timestamp hết hạn/algorithm yếu: có hướng kiểm tra và renewal evidence.
10. System clock bị thay **không làm verifier coi claimed time đáng tin**.

### Kiểm thử ứng dụng

1. JWT có valid signature nhưng `aud` sai: bị từ chối.
2. JWT valid v1 sau trust cutover compromise: bị từ chối theo incident policy.
3. Token có `kid`/URL chỉ key attacker: không được chọn trust tùy ý.
4. HSM `Sign` trên digest chưa approved: business gateway chặn.
5. Release manifest ký đúng nhưng artifact digest bị thay: bị từ chối.
6. PDF hiện tại bị chỉnh nội dung ngoài signed revision theo policy cấm: bị phát hiện.
7. Chữ ký cũ thiếu evidence: status review/indeterminate, không giả định approved.
8. Verifier không có public key cũ do rotation: đưa ra lỗi trust/config rõ ràng, không thử private key.
9. Key v1 bị compromised: hệ thống không **new-sign bằng v1** dù vẫn lưu public verify.
10. Audit ghi rõ crypto result/trust/policy/incident reference, không log secret.

### Kiểm thử vận hành

- JWKS cache lag/multi-region rollout.
- PKI CRL/OCSP unavailable và offline archival evidence.
- Trust store versions và timestamp/timezone.
- Rollback ứng dụng không bật lại old signing key.
- Backup/restore tài liệu/evidence, không làm mất chain.
- Rebuild signature inventory từ key ID/certificate serial.
- Revocation notification tới relying parties và response tracking.
- Incident tabletop cho **key leak**, **signing-oracle misuse** và **CA compromise**.

## 30. Những lỗi đánh giá signature cũ thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| “Revoke key thì mọi `Verify()` trả false” | Nhầm phép toán với trust | Verify public key độc lập, đánh giá policy riêng |
| “`Verify()` true thì tài liệu chắc chắn hợp lệ” | Bỏ qua identity/time/approval | Phân tách crypto, PKI, temporal và business |
| Coi `signedAt` trong file là trusted time | Attacker có thể backdate | Trusted timestamp/evidence độc lập |
| Coi JWT `iat` chứng minh token phát trước key leak | Attacker có thể tự ký thời gian | Session/issuer logs, trust cutover |
| Coi timestamp luôn chứng minh người ký có thẩm quyền | TSA không xác nhận authorization | Business approval và identity checks |
| Coi timestamp sau key leak vẫn “cứu” mọi chữ ký | Chữ ký giả có thể được timestamp | Đối chiếu earliest exposure |
| Coi `revocationDate` là chính xác lúc raw key lộ | Sai timeline | Investigate invalidityDate và evidence |
| Coi certificate `expired` tự động vô hiệu mọi chữ ký trước đó | Mất historical validation | Policy + trusted time + chain evidence |
| Coi CRL/OCSP `good` là bảo đảm không private-key leak | Sai ngữ nghĩa trạng thái | Đánh giá compromise riêng |
| Coi OCSP `unknown` là `good` | Fail open | Indeterminate/review theo policy |
| Không kiểm tra OCSP/CRL signer authorization | Tin dữ liệu giả | Xác minh response/CRL signatures và issuer |
| Không lưu validation evidence | Về sau URL PKI không truy cập | LTV/archive và renewal |
| Chỉ lưu ảnh badge “valid” | Không tái dựng chứng cứ | Lưu signed bytes, chain, TSA, policy |
| Xóa public key v1 sau rotation | Không verify được chữ ký lịch sử | Archive public verification material |
| Giữ v1 trong JWKS vô hạn sau compromise | Attacker vẫn có thể phát JWT giả | Incident trust cutoff |
| Coi `kid` do token đưa là trust anchor | Key substitution | Allowed issuer/key registry |
| Không phân biệt private key leak và Sign API misuse | Remediation sai | Điều tra boundary, output và credential |
| Rotate HSM key nhưng vẫn cho ký digest tùy ý | Signing oracle lặp lại | Approval exact digest và SoD |
| Coi HSM non-exportable là không thể có chữ ký giả | Underestimate API misuse | Business-level signing gate |
| Chỉ xét leaf cert, không xét issuing CA | Bỏ qua CA compromise | Path/trust chain incident |
| Coi mọi chữ ký lịch sử đều vô hiệu pháp lý | Kết luận pháp lý thiếu căn cứ | Chính sách và chứng cứ theo luật áp dụng |
| Coi chữ ký hợp đồng giống JWT | Sai retention/threat model | Use-case-specific validation |
| Chỉ verify artifact mutable tag | Bị tráo artifact | Sign/verify immutable digest/manifest |
| PDF verify một byte range rồi tin toàn file | Bỏ qua incremental changes | Profile-aware PDF validator |
| Lấy claimed timestamp làm thời điểm CA validity | Backdating | Trusted temporal evidence |
| Thay algorithm nhưng giữ bằng chứng hash yếu vô hạn | LTV suy yếu | Evidence renewal trước khi suy giảm |
| Xóa private key để “xóa” chữ ký đã phát | Signature vẫn tồn tại | Revocation/trust/business action |
| Log nguyên signed document nhạy cảm vào SIEM | Rò dữ liệu | Metadata references, least privilege |
| Chỉ lưu `signatureValid=true` | Không biết tầng nào pass | Structured validation decision |
| Đóng incident ngay khi writer chuyển v2 | Bỏ sót chữ ký v1 | Historical signature review riêng |

## 31. Checklist production: xử lý ảnh hưởng đến signature cũ

### A. Nhận diện phạm vi

1. **Key identity:** Có key ID/material version, signer/certificate serial, issuer và purpose?
2. **Sự kiện:** Rotation định kỳ, certificate expiry, revocation, suspected raw leak hay API misuse?
3. **Loại tài sản:** PDF/hợp đồng, JWT, software artifact, chứng thư CA hay thông điệp HMAC?
4. **Inventory:** Có danh sách signatures/artifact digests/public keys liên quan?
5. **Incident timeline:** Earliest plausible exposure, detection, revoke, cutover và verification time rõ?
6. **Confidence:** Có phân biệt sự kiện đã xác nhận với giả thuyết?
7. **Raw key vs oracle:** Đã xác định bytes bị lộ hay chỉ quyền Sign bị lạm dụng?
8. **CA scope:** Có intermediate/root hoặc TSA compromise không?

### B. Kiểm tra mật mã và trust

9. **Signed bytes:** Có dữ liệu gốc đúng revision/canonicalization?
10. **Algorithm:** Chữ ký dùng đúng profile và parameters được phép?
11. **Public key:** Verifier lấy từ nguồn tin cậy, không chỉ `kid` tự khai?
12. **Crypto:** Có ghi rõ verification result độc lập với trust result?
13. **Certificate chain:** Có kiểm tra đường dẫn, validity, key usage và policies?
14. **CRL/OCSP:** Có verify nguồn, signature, freshness, revocation status?
15. **Revocation reason:** Đã phân biệt `keyCompromise`, `cACompromise`, `superseded`?
16. **Time distinction:** `revocationTime`, `invalidityDate`, `thisUpdate`, `producedAt` không bị nhầm?
17. **Trusted timestamp:** Có xác minh TSA trust, signature, imprint và phạm vi token?
18. **No self-declared time trust:** `signedAt`, JWT `iat`, PDF metadata không tự được chấp nhận?
19. **LTV evidence:** Có archive CRL/OCSP, cert chain, timestamps và renewal plan?
20. **Policy version:** Có thể tái dựng quyết định hôm nay và tại thời điểm lịch sử?

### C. Xử lý business và incident

21. **Authorization:** Có evidence digest/transaction được người có thẩm quyền phê duyệt?
22. **Signer isolation:** Đã chặn credential/grants và direct Sign API trái phép?
23. **Fresh key:** Signing key v2 được sinh từ nguồn tin cậy và áp dụng quyền đúng?
24. **Verifier readiness:** Public key/cert v2 được phân phối trước khi new-sign cutover?
25. **No old new-sign:** Workload và region không tiếp tục ký v1?
26. **Old public verification:** Có giữ khả năng kiểm tra lịch sử mà không tiếp tục tin chữ ký giả?
27. **JWT incident:** Có kế hoạch cutoff/denylist/session revoke và JWKS cache?
28. **Release incident:** Có artifact provenance, withdraw/quarantine, immutable digest?
29. **Document incident:** Có phân biệt tính đúng mật mã, chứng cứ thời gian và hiệu lực nghiệp vụ/pháp lý?
30. **CA incident:** Có xử lý chain, relying parties và trust anchor theo runbook?
31. **Unknown exposure time:** Chữ ký thiếu bằng chứng được đưa vào review, không auto-pass?
32. **Partner notice:** Những bên nhận có được thông báo trust changes đúng scope?

### D. Lưu trữ, kiểm thử và audit

33. **Evidence retention:** Signed bytes, public cert, TSA, CRL/OCSP, approvals và incident notes được lưu?
34. **Archive renewal:** Có kế hoạch khi hash/TSA certificate/algorithm sắp không còn phù hợp?
35. **Privacy:** Không log private keys, tài liệu nhạy cảm hoặc bearer tokens vào SIEM?
36. **Audit separation:** Ghi crypto result, trust result, business result và final policy decision riêng?
37. **Negative tests:** Wrong key, modified payload, bad TSA, unknown OCSP, key leak scenarios được thử?
38. **PDF revisions:** Có kiểm tra thay đổi sau ký theo policy?
39. **JWT claims:** `iss/aud/exp/nbf/alg/kid` và issuer trust được xác minh?
40. **Cross-region:** Verifier/JWKS/PKI/trust-store caches đồng bộ theo kế hoạch?
41. **Rollback:** Không tự bật lại v1 để ký khi v2 lỗi?
42. **Restore drill:** Có thể xác minh chữ ký lịch sử từ backup/evidence độc lập?
43. **Residual risk:** Biết attacker có thể còn raw key/copies và old outputs không thể xóa?
44. **Closure:** Có owner, policy revision, evidence và quyết định đối với từng nhóm chữ ký cũ?

## 32. Tổng kết

**Ảnh hưởng đến signature cũ** khi khóa ký bị thu hồi hoặc compromise là vấn đề **tin cậy theo thời gian**, không chỉ là phép toán mật mã. **Chữ ký cũ có thể vẫn `Verify() == true` với public key cũ** dù private key đã bị lộ hoặc certificate bị revoked. Nhưng điều đó **không chứng minh** người có thẩm quyền đã ký, thời điểm tự khai là thật, hoặc chữ ký còn được chấp nhận theo chính sách.

Muốn kết luận phải kiểm tra **signed bytes, public-key identity, certificate path, CRL/OCSP, trusted timestamp, compromise timeline, business approvals và algorithm security**. Dấu thời gian đáng tin có thể chứng minh signature đã tồn tại không muộn hơn một mốc, nhưng **không chữa được key đã lộ trước mốc đó** và không thay thế authorization. Với **JWT**, việc tiếp tục tin old signing key sau compromise có thể cho phép token giả; với **hợp đồng/PDF** có chứng cứ lưu dài hạn, cần historical validation; với **software release**, phải đối chiếu exact artifact digest và provenance; với **CA compromise**, phải xét cả trust chain.

**Xoay vòng khóa ký mới và chặn new-sign v1 là việc cần thiết nhưng chưa đủ**. Tổ chức còn phải **lưu public verification material, bảo toàn evidence, phân loại chữ ký lịch sử, cập nhật relying parties và có quyết định `ACCEPT/REJECT/REVIEW/INDETERMINATE` dựa trên chính sách minh bạch**. Không nên xóa bỏ toàn bộ quá khứ chỉ từ một nhãn `REVOKED`, cũng không nên tin mọi chữ ký cũ chỉ vì một API trả `true`.

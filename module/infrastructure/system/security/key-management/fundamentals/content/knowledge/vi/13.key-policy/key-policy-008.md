# Revocation policy — Chính sách thu hồi khóa mật mã

## 1. Revocation policy là gì và vì sao cần có?

**Revocation policy (chính sách thu hồi khóa)** quy định **khi nào, ai, bằng chứng nào và bằng cơ chế nào hệ thống phải ngừng sử dụng hoặc ngừng tin cậy một khóa mật mã**. Chính sách cũng xác định **phạm vi ảnh hưởng, thời điểm hiệu lực, cách thông báo cho các bên phụ thuộc, quy trình thay khóa, kiểm tra kết quả và lưu bằng chứng kiểm toán**.

Ví dụ, hệ thống Java dùng một private signing key trong HSM để ký token. Khi phát hiện tài khoản service có quyền **Sign** bị chiếm, nhóm bảo mật phải có khả năng chặn phát hành token mới, đánh giá token đã được ký và khiến các dịch vụ xác minh áp dụng quyết định thu hồi. **Chỉ đổi trạng thái khóa trong một bảng dữ liệu không tự khiến các API và bộ nhớ đệm ngừng tin khóa đó**.

Trong học phần **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, Revocation policy thuộc chương **Key policy**: một chính sách bảo vệ khóa phải trải suốt vòng đời **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**, kết nối mật mã đối xứng, bất đối xứng, chữ ký số, **KMS/HSM, envelope encryption, phân quyền và kiểm toán**. Thu hồi là một quyết định bảo mật có hậu quả trực tiếp lên **tính bí mật, tính toàn vẹn, tính xác thực và tính sẵn sàng**.

> **Nguyên tắc:** **Thu hồi niềm tin hoặc quyền dùng khóa không đồng nghĩa xóa vật liệu khóa.** Một khóa đã bị lộ không trở lại bí mật khi bị disable; một chứng chỉ bị thu hồi cũng không tự làm mọi bộ xác minh nhận biết ngay. Chính sách phải chỉ rõ **hành vi nào thực sự bị chặn và bằng chứng nào chứng minh việc chặn có hiệu lực**.

## 2. Những đối tượng nào có thể bị thu hồi?

Từ **revocation** được dùng cho nhiều lớp trong hệ thống. Cần xác định **đối tượng và ranh giới hiệu lực** trước khi thiết kế API hoặc quy trình.

| Đối tượng | Thu hồi cái gì? | Cơ chế thường gặp | Điều không được suy diễn |
| --- | --- | --- | --- |
| **Khóa đối xứng DEK** | Quyền Encrypt/Decrypt với một DEK hoặc việc tin DEK còn an toàn | Policy gate, thu hồi quyền, vô hiệu hóa key wrapper, thay DEK | Disable KEK không xóa được mọi bản sao DEK dạng rõ |
| **KEK / root key** | Quyền Wrap/Unwrap hoặc miền tin cậy của cây khóa | KMS/HSM IAM, key policy, disable/retire, migration | Rewrap không khôi phục tính bí mật của DEK đã lộ |
| **Private signing key** | Quyền Sign và sự tin cậy vào chữ ký mới | Chặn Sign, thu hồi chứng chỉ/khóa công khai tương ứng, chuyển signer | Non-exportable không loại bỏ khả năng lạm dụng Sign API |
| **X.509 certificate** | Sự tin cậy vào chứng chỉ theo PKI policy | CRL, OCSP hoặc cơ chế trạng thái chứng chỉ do hệ thống áp dụng | Disable private key tại server không tự cập nhật toàn bộ client |
| **JWK/JWKS verification key** | Việc chấp nhận chữ ký token theo issuer, key ID và policy | Thay tập khóa tin cậy, cache refresh/invalidation, token revocation policy | Xóa một JWK khỏi endpoint không lập tức xóa bản cache của mọi verifier |
| **MAC/HMAC key** | Quyền tạo/chấp nhận tag từ bí mật chung | Dừng Generate/Verify, đổi secret và key ID, cập nhật hai phía | Bên còn giữ key cũ vẫn có thể tạo tag hợp lệ về toán học |
| **Pepper** | Quyền sử dụng bí mật trong password hashing | Chặn/migrate pepper version, reset mật khẩu khi cần | Không thể tái tạo mọi verifier với pepper mới từ hash một chiều |
| **API grant/credential** | Quyền của một danh tính được phép gọi KMS/HSM | Revoke IAM grant/role/session/token | Thu hồi credential không đồng nghĩa key bytes đã bị xóa |
| **Trust anchor / CA key** | Quyền tin một nguồn phát hành chứng chỉ hoặc chữ ký | Cập nhật truststore, PKI incident process, phân phối trust mới | Không phải mọi client tự cập nhật trust anchor tức thời |

### 2.1. Thu hồi khóa và thu hồi một credential không giống nhau

Giả sử **DEK** vẫn an toàn nhưng token của workload có quyền KMS Decrypt bị lộ. Có thể cần **thu hồi principal/session/grant** ngay, điều tra nội dung đã bị truy cập và đánh giá có cần thay DEK hay không. Đây là sự cố **lạm dụng quyền sử dụng khóa**, chưa tự chứng minh vật liệu DEK đã bị trích xuất.

Ngược lại, nếu **raw DEK** đã bị đăng vào repository công khai, thu hồi IAM **không đủ**: người có khóa và ciphertext có thể giải mã bên ngoài KMS. Trong trường hợp đó cần xem xét **thay DEK và mã hóa lại dữ liệu**.

### 2.2. Thu hồi khóa ký khác kiểm tra chữ ký lịch sử

Private signing key dùng để **Sign**; public verification key dùng để **Verify**. Thu hồi quyền ký mới có thể cần thực hiện ngay. Với **chữ ký lịch sử**, quyết định chấp nhận hay không còn phụ thuộc **thời điểm ký đáng tin cậy, loại tài liệu, lý do thu hồi và chính sách bằng chứng**. Không nên mặc định tất cả chữ ký quá khứ luôn hợp lệ hoặc luôn giả chỉ dựa vào trạng thái hiện tại.

## 3. Phân biệt revocation với suspension, rotation, expiry và destruction

| Khái niệm | Mục tiêu | Có thể quay lại dùng? | Điểm cần chú ý |
| --- | --- | --- | --- |
| **Suspension/disable** | Tạm chặn thao tác khi nghi có vấn đề hoặc bảo trì | Có thể, tùy chính sách | Thường là biện pháp containment; không xóa vật liệu |
| **Retirement/deactivation** | Ngừng dùng cho tác vụ mới theo kế hoạch | Có thể cho phép đọc/xác minh lịch sử | Không đồng nghĩa khóa đã lộ |
| **Expiry** | Kết thúc hiệu lực theo mốc thời gian | Thường cần cấp/đổi phiên bản theo chính sách | Hết hạn không tự chứng minh compromise |
| **Rotation** | Thay sang khóa mới và chuyển phụ thuộc | Khóa cũ có thể còn tạm dùng có điều kiện | Không tự chặn được bản sao khóa cũ |
| **Revocation** | Thu hồi niềm tin/quyền đối với khóa theo policy | Phụ thuộc nguyên nhân, thường không tự phục hồi khi đã xác nhận compromised | Phải lan truyền tới mọi thành phần quyết định chấp nhận khóa |
| **Destruction** | Hủy vật liệu khóa trong phạm vi quản lý | Có thể không thể đảo ngược | Phải kiểm kê ciphertext, backup, DR và nhu cầu khôi phục |
| **Compromised** | Trạng thái an ninh: khóa hoặc quyền dùng khóa bị xâm phạm | Không được tự động chuyển về trusted | Có thể dẫn tới revoke, disable, rotate và destroy theo playbook |

**Một key record có thể đồng thời được đánh dấu compromised và disabled.** Nếu chỉ có một trường \`status\` và không có lịch sử, hệ thống dễ làm mất thông tin **vì sao** khóa bị vô hiệu hóa.

### 3.1. Máy trạng thái mang tính chính sách

~~~mermaid
stateDiagram-v2
    [*] --> PRE_ACTIVE: Sinh và phê duyệt
    PRE_ACTIVE --> ACTIVE: Kích hoạt theo key policy
    ACTIVE --> SUSPENDED: Nghi vấn / yêu cầu khẩn
    SUSPENDED --> ACTIVE: False positive + phê duyệt
    ACTIVE --> RETIRED: Hết hạn / rotate bình thường
    ACTIVE --> REVOKED: Xâm phạm / mất tin cậy
    SUSPENDED --> REVOKED: Xác nhận sự cố
    RETIRED --> REVOKED: Phát hiện sự cố với khóa cũ
    RETIRED --> DESTROYED: Hết phụ thuộc và retention
    REVOKED --> DESTROYED: Sau containment/migration
~~~

**Đây không phải danh sách trạng thái chuẩn của một KMS cụ thể.** KMS có thể chỉ hỗ trợ Enabled/Disabled/Pending deletion; ứng dụng cần ánh xạ **security status**, **lifecycle state** và **trạng thái API thực tế** một cách tường minh.

## 4. Điều gì kích hoạt chính sách thu hồi?

Một chính sách tốt xác định **điều kiện kích hoạt**, **mức độ khẩn cấp** và **quyết định tạm thời khi chưa đủ bằng chứng**. Không nên đợi xác nhận hoàn toàn mọi dấu vết nếu sự cố đang cho phép tạo chữ ký giả hoặc đọc dữ liệu trái phép.

| Trigger | Ví dụ | Phản ứng ban đầu nên cân nhắc |
| --- | --- | --- |
| **Lộ vật liệu khóa** | Private key xuất hiện trong Git, DEK nằm trong log bị đọc trái phép | Cô lập quyền, ngừng sử dụng khóa cũ, điều tra và chuẩn bị thay khóa |
| **Lạm dụng API mật mã** | HSM ghi Sign/Unwrap từ principal bị chiếm | Thu hồi credential/grant, tạm dừng thao tác liên quan, kiểm tra bản ghi hoạt động |
| **Khóa/nguồn tin cậy bị đánh tráo** | Truststore hoặc JWKS đổi public key không qua phê duyệt | Khôi phục nguồn tin cậy, chặn key mới đáng ngờ, đánh giá chữ ký đã được chấp nhận |
| **Mất quyền kiểm soát đối tác** | Đối tác báo MAC key bị lộ, nhân sự giữ key nghỉ việc | Thu hồi bí mật/quyền liên quan và cấp phát key mới |
| **Vấn đề thuật toán/tham số** | Nhóm DH yếu hoặc RSA key không đáp ứng policy | Đánh giá chuyển đổi, ngừng phát hành tác vụ mới theo mức rủi ro |
| **Sử dụng sai giao thức** | Tái sử dụng nonce AES-GCM dưới cùng DEK | Ngừng Encrypt bằng DEK liên quan, điều tra bản mã, thay key và xử lý dữ liệu |
| **Hết thời hạn hoặc hết mục đích** | Certificate expired, tenant kết thúc hợp đồng | Deactivate/retire theo lịch; chỉ ghi compromised nếu thực sự có căn cứ |
| **Yêu cầu pháp lý/quản trị** | Tổ chức dừng tin một CA hoặc signer | Ban hành quyết định trust policy, phân phối và xác nhận hiệu lực |

### 4.1. Suspicion không phải kết luận cuối cùng

Ví dụ, một cảnh báo bất thường chưa chứng minh private key đã bị xuất. Nhưng chính sách có thể yêu cầu **suspend ngay quyền Sign** để giảm thiệt hại. Sau điều tra:

- Nếu là false positive: phục hồi theo luồng có phê duyệt và lưu đủ dấu vết.
- Nếu xác nhận compromise: **revoke** và xử lý vật liệu/khóa phụ thuộc.
- Nếu thiếu bằng chứng: ghi mức bất định và áp dụng quyết định theo rủi ro, không tự động bỏ cảnh báo chỉ vì log không đầy đủ.

Nên tách **evidence status** (suspected/confirmed) và **enforcement state** (active/suspended/revoked) để vận hành chính xác.

## 5. Thành phần tối thiểu của một Revocation policy

Một chính sách thu hồi không nên chỉ có câu “khi lộ khóa thì thu hồi”. Cần tối thiểu các nội dung sau:

1. **Scope:** Loại khóa, chủ thể quản lý, tenant, environment, vùng, thuật toán, purpose và các hệ thống relying party.
2. **Trigger and severity:** Sự kiện nào dẫn đến suspend/revoke và tiêu chí phân loại khẩn cấp.
3. **Authority:** Ai được báo sự cố, ai được ra lệnh containment, ai phê duyệt quyết định không thể đảo ngược.
4. **Effective time:** Thời điểm quyết định có hiệu lực; phân biệt thời điểm phát hiện, thời điểm nghi bị lộ và mốc KMS/PKI thực sự áp dụng.
5. **Usage semantics:** Chặn thao tác nào: Encrypt, Decrypt, Wrap, Unwrap, Sign, Verify, GenerateMac hoặc Export.
6. **Propagation:** Hệ thống nào cần nhận quyết định, TTL/cache, IAM grants, truststores, JWKS, CRL/OCSP, DR và backup.
7. **Migration:** Khóa thay thế, DEK/KEK phụ thuộc, rewrap/re-encrypt, token/chữ ký đang có và đường khôi phục.
8. **Failure behavior:** Khi không xác minh được trạng thái khóa thì từ chối, tạm dừng hay cho phép một luồng lịch sử có kiểm soát?
9. **Evidence and audit:** Incident/change ID, lý do, chứng cứ, requester/approver, API receipts, trạng thái lan truyền và kết quả thử nghiệm.
10. **Review and closure:** Điều kiện kết thúc, thời hạn giữ bằng chứng, rủi ro tồn dư và cải tiến chính sách.

### 5.1. Ví dụ chính sách dạng cấu hình

~~~yaml
# Minh họa cấu trúc policy nội bộ, KHÔNG phải cú pháp API của KMS.
policyId: key-revocation-prod-v2
policyVersion: 2
scope:
  environment: production
  keyPurposes: [data-encryption, key-wrapping, digital-signature, mac]
  tenants: [tenant-a, tenant-b]
triggers:
  confirmedSecretExposure: immediate-containment
  confirmedUnauthorizedSigning: immediate-containment
  plannedRetirement: scheduled-review
roles:
  incidentCommander: security-response
  keyOwner: service-owner
  independentApprover: security-approver
enforcement:
  defaultOnUnknownStatus: deny
  forbidNewUseWhenSuspended: true
  forbidNewUseWhenRevoked: true
  requireKmsPolicyReconciliation: true
propagation:
  targets: [key-registry, kms-policy, iam, jwks-or-pki, workload-cache, dr]
  requirePerTargetAcknowledgement: true
verification:
  requireNegativeAccessTest: true
  requireDependentDataReview: true
audit:
  keepIncidentReference: true
  neverLogKeyMaterial: true
~~~

Đây chỉ là **mẫu tư duy về các trường cần có**, không phải một chính sách có thể dùng nguyên văn trong hạ tầng. Những giá trị như **thời gian phát tán tối đa, thời hạn chấp nhận khóa cũ, vai trò phê duyệt và cách xử lý lỗi** phải được xác định bằng mức độ rủi ro, yêu cầu nghiệp vụ và khả năng kỹ thuật của môi trường cụ thể.

### 5.2. Chính sách cần tránh “một kích thước cho tất cả”

Thu hồi **private signing key có nguy cơ tạo chữ ký giả** thường cần ngăn việc ký và thông báo relying parties khẩn cấp. Ngược lại, ngừng một **DEK đã hoàn toàn nghỉ dùng** có thể cần duy trì khả năng Decrypt lịch sử có kiểm soát cho đến khi dữ liệu được re-encrypt.

Một policy tốt có **quy tắc chung** nhưng mô tả **hành động theo key type, purpose và security status**, không dùng một câu lệnh DeleteKey duy nhất.

## 6. Quy tắc hiệu lực: revoke từ khi nào và áp dụng cho ai?

Trong sự cố khóa, có ít nhất ba mốc thời gian:

- **Suspected exposure time:** Thời điểm sớm nhất có căn cứ cho rằng khóa hoặc quyền dùng khóa đã bị xâm phạm.
- **Revocation decision time:** Thời điểm người hoặc hệ thống có thẩm quyền ra quyết định thu hồi.
- **Enforcement effective time:** Thời điểm từng hệ thống dùng khóa **thật sự áp dụng** chính sách, ví dụ KMS từ chối Sign, cache JWT không còn nhận khóa hoặc client cập nhật CRL/truststore.

**Không đồng nhất ba mốc này.** Một quyết định lúc 10:00 có thể chỉ được một cụm dịch vụ nhận lúc 10:03. Việc có khóa trong cache tại 10:02 là một **khoảng phơi nhiễm**, không phải bằng chứng quyết định đã được thực thi đầy đủ.

### 6.1. “Effective immediately” phải có nghĩa kỹ thuật

Nếu chính sách yêu cầu revoke ngay:

1. Chặn **quyền tạo giá trị mật mã mới** tại nơi phát sinh: KMS/HSM, IAM và workload.
2. Chặn **đường xác minh/giải mã không được phép** tại nơi tiêu thụ.
3. Đưa thông tin thu hồi tới cache, gateway, service mesh, relying party và DR.
4. Ghi thời điểm từng thành phần xác nhận và kiểm thử đường bị cấm.
5. Báo cáo **chưa hoàn tất** nếu còn hệ thống ngoài tầm kiểm soát hoặc cần thủ tục cập nhật thủ công.

“Immediate” là **mục tiêu của playbook**, không phải phép bảo đảm mạng phân tán cập nhật đồng thời. Nếu cần mức độ trễ tối đa, phải đặt mục tiêu đo được và kiểm thử các thành phần thực tế.

### 6.2. Không lấy timestamp do đối thủ cung cấp làm bằng chứng

Một thông điệp có thể mang trường \`issuedAt\`, \`signedAt\` hoặc \`kid\`, nhưng nếu các trường này do người gửi chưa đáng tin cậy tự khai báo, chúng **không đủ để chứng minh chữ ký được tạo trước lúc khóa bị lộ**.

Đối với chữ ký lịch sử cần được công nhận, có thể cần **trusted timestamp, audit record đáng tin cậy, trạng thái chứng chỉ tại thời điểm phù hợp và chính sách lưu giữ bằng chứng**. Những dữ kiện này khác nhau giữa tài liệu pháp lý, gói phần mềm, JWT và webhook.

## 7. Thu hồi khóa đối xứng, DEK/KEK và envelope encryption

Đối với **mã hóa dữ liệu at rest**, revocation policy cần xác định **khóa nào được dùng trực tiếp** và **khóa nào chỉ bảo vệ khóa khác**.

~~~mermaid
flowchart TD
    ROOT["KMS/HSM trust boundary"] --> KEK["KEK production v3"]
    KEK --> WRAP1["Wrapped DEK tenant A v7"]
    KEK --> WRAP2["Wrapped DEK tenant B v4"]
    WRAP1 --> DATA1["Ciphertext tenant A"]
    WRAP2 --> DATA2["Ciphertext tenant B"]
    INCIDENT["Sự cố với KEK?"] -.->|"Đánh giá tất cả wrapped DEK"| KEK
    ROTATE["Kế hoạch: rewrap và/hoặc re-encrypt"] --> WRAP1
    ROTATE --> WRAP2
~~~

### 7.1. DEK bị lộ

Nếu một **raw DEK** bị lộ, nên ngừng Encrypt mới bằng DEK cũ, sinh DEK mới bằng nguồn ngẫu nhiên đáng tin cậy và đánh giá **re-encrypt** dữ liệu phụ thuộc. Trong lúc di chuyển có thể cần một đường Decrypt cũ được cô lập, phê duyệt và giám sát.

**Không chỉ rewrap chính DEK đã lộ** bằng KEK mới rồi tuyên bố dữ liệu an toàn: kẻ tấn công vẫn có thể dùng bản sao DEK để giải mã ciphertext cũ đã lấy được.

### 7.2. KEK bị lộ hoặc quyền Unwrap bị lạm dụng

Với **raw KEK bị lộ**, các bản wrapped DEK mà đối thủ có thể thu thập được có nguy cơ bị giải bọc. Cần kiểm kê phụ thuộc, backup, dữ liệu mã hóa và các đường xuất khóa, rồi quyết định có cần thay cả DEK hay không.

Nếu chỉ có **quyền API Unwrap/Decrypt bị chiếm**, chưa chắc key bytes đã bị xuất. Phản ứng trước mắt thường là **thu hồi IAM/session/grant**, cô lập workload và điều tra những dữ liệu/DEK mà API đã trả. Quyết định rotate hay re-encrypt cần dựa trên phạm vi đã đánh giá, không bỏ qua nguy cơ bản sao DEK đã rời KMS.

### 7.3. Rewrap không phải re-encrypt

| Hành động | Thay đổi điều gì? | Không tự giải quyết điều gì? |
| --- | --- | --- |
| **Rewrap** | Bảo vệ một DEK dưới KEK mới | Không thay DEK đang dùng để mã hóa dữ liệu |
| **Re-encrypt** | Giải mã dữ liệu hợp lệ và mã hóa bằng DEK mới | Không xóa bản sao ciphertext/plaintext kẻ tấn công đã giữ |
| **Revoke API permission** | Chặn một danh tính gọi KMS/HSM theo policy | Không thu hồi raw key đã bị sao chép |
| **Disable key** | Chặn thao tác được KMS hỗ trợ trong phạm vi nền tảng | Không xóa mọi bản sao tại ứng dụng, cache và backup |
| **Destroy material** | Loại bỏ vật liệu khóa theo quy trình hủy | Có thể làm mất khả năng đọc dữ liệu nếu chưa migration; không thu hồi bí mật đã lộ |

Chính sách cần nói rõ **thao tác nào bị cấm ngay, thao tác nào tạm được phép để cứu dữ liệu, ai có thể phê duyệt ngoại lệ, và thời hạn ngoại lệ**. Đường phục hồi không được trở thành cơ chế fallback vĩnh viễn.

## 8. Thu hồi khóa ký số, chứng chỉ X.509 và PKI

Trong chữ ký số, cần phối hợp ba lớp: **private signing key**, **chứng chỉ/public verification key** và **bên xác minh (relying party)**.

### 8.1. Khóa ký bị lộ thì phải làm gì?

1. **Ngừng Sign** bằng private key bị ảnh hưởng; thu hồi principal/credential có quyền ký.
2. Điều tra các chữ ký đã phát hành và thời điểm có thể bị xâm phạm.
3. Sinh cặp khóa mới, bảo vệ private key qua HSM/KMS khi phù hợp, phát hành/phân phối public verification key đáng tin cậy.
4. Nếu dùng PKI, kích hoạt **quy trình thu hồi chứng chỉ** theo CA/chính sách; cập nhật CRL/OCSP hoặc kênh thông báo trạng thái được quy định.
5. Đảm bảo bên xác minh **thực sự kiểm tra chain, danh tính, Key Usage/EKU, thời hạn và revocation status** theo policy, không chỉ gọi \`Signature.verify\`.
6. Lưu chứng cứ sự cố, giải quyết chữ ký lịch sử theo thời điểm/bằng chứng phù hợp.

### 8.2. CRL và OCSP có vai trò gì?

- **CRL (Certificate Revocation List):** Danh sách chứng chỉ bị thu hồi do CA phát hành và ký; bên xác minh cần kiểm tra nguồn, chữ ký, thời hạn cập nhật và chính sách xử lý.
- **OCSP (Online Certificate Status Protocol):** Cơ chế hỏi trạng thái chứng chỉ, tùy giao thức và CA. Phải đánh giá tính xác thực, hiệu lực phản hồi, cache và hành vi khi không liên lạc được responder.

**Một chứng chỉ hiện còn trong thời hạn không có nghĩa chưa bị thu hồi.** Ngược lại, **có một CRL cũ trong cache** cũng không bảo đảm trạng thái tại thời điểm xác minh vẫn phù hợp chính sách.

**Lưu ý:** Cách kiểm tra thu hồi và khả năng truy cập responder khác nhau theo PKI/use case. Một hệ thống chứng chỉ riêng có thể dùng registry/trust policy do tổ chức vận hành, không nhất thiết CRL/OCSP công khai. Phải tuân thủ đặc tả và nhu cầu kiểm chứng thực tế, không mặc định cứ bật một tham số chung là hoàn chỉnh.

### 8.3. Xử lý khi không kiểm tra được trạng thái

Một câu hỏi quan trọng là **fail closed** hay có ngoại lệ khi CRL/OCSP không sẵn sàng. Đối với hoạt động bảo mật nhạy cảm, không nên mặc định chấp nhận chứng chỉ mà không có thông tin thu hồi đạt yêu cầu.

Trong những hệ thống yêu cầu sẵn sàng cao, chính sách có thể cho phép sử dụng **bằng chứng trạng thái đã xác thực còn trong hiệu lực**, hoặc cơ chế ngoại lệ được phê duyệt. Cần phân biệt **thiếu kết nối tạm thời** với **có xác nhận chứng chỉ không bị thu hồi**; không gọi mọi tình huống là \`good\`.

## 9. JWKS, JWT và vấn đề cache khóa đã thu hồi

Một hệ thống OAuth/OIDC có thể xác minh JWT có chữ ký dựa trên **issuer** và tập **JWKS** công bố public keys. Khi khóa ký bị ảnh hưởng, ứng dụng có thể công bố khóa mới và loại bỏ khóa cũ khỏi JWKS, nhưng:

- Nhiều verifier vẫn giữ **JWK cũ trong cache**.
- JWT đã phát hành có thể vẫn còn **\`exp\` chưa hết hạn**.
- JWT header **\`kid\` không phải bằng chứng tin cậy** và có thể trùng giữa issuer.
- Chính sách kiểm tra **issuer, audience, loại token, thời hạn và quyền** vẫn cần thực thi sau bước Verify.

### 9.1. Xoay vòng JWKS bình thường khác thu hồi khẩn cấp

**Rotation bình thường:** Có thể phát public key mới **trước** khi private key mới ký, giữ public key cũ một khoảng có kiểm soát để xác minh token còn hiệu lực.

**Compromised key:** Không được kéo dài thời gian tin khóa cũ chỉ vì thuận tiện. Nếu kẻ tấn công có thể ký JWT bằng khóa cũ, cần **ngừng chấp nhận key đó sớm nhất theo playbook**, phân phối invalidation tới verifier, cân nhắc vô hiệu hóa token/phiên liên quan và phối hợp xử lý sự cố.

### 9.2. Xóa JWK không tương đương thu hồi token tức thời

Một verifier offline hoặc cache lâu vẫn có thể chấp nhận chữ ký theo khóa đã bị xóa ở endpoint. Một hệ thống có thể cần thêm **revocation registry, minimum accepted key epoch, token invalidation, cache invalidation hoặc online authorization check**, tùy kiến trúc.

**Không thiết kế verifier tự tải khóa từ \`jku\`/\`x5u\` do token chưa xác thực cung cấp.** Việc tải một public key hợp lệ do đối thủ chỉ định không chứng minh token đến từ issuer tin cậy.

### 9.3. Luồng thu hồi khóa JWT

~~~mermaid
sequenceDiagram
    participant SOC as Security / Key owner
    participant ISS as Token issuer + HSM
    participant REG as Key registry / JWKS
    participant API as API verifier + cache
    SOC->>ISS: Chặn Sign với key v1; kích hoạt key v2
    SOC->>REG: Revoke v1, phát trust policy mới
    REG-->>API: Thông báo invalidation / refresh có kiểm soát
    API->>REG: Đối chiếu issuer, key ID, version, policy
    API->>API: Từ chối token ký bằng v1 nếu policy cấm
    API-->>SOC: Acknowledge + bằng chứng negative test
    Note over SOC,API: Token/phiên cũ cần đánh giá riêng; cache chưa cập nhật là rủi ro
~~~

Một JWKS chỉ là **phương tiện phân phối public key**, còn quyết định thu hồi đòi hỏi **policy, trạng thái và cơ chế nhất quán ở relying parties**.

## 10. Revocation policy cho MAC key, pepper và giao thức đối xứng

### 10.1. MAC key dùng chung giữa hai dịch vụ

HMAC cho webhook sử dụng một **bí mật chung**. Nếu key bị lộ, một đối thủ biết secret có thể tạo tag hợp lệ cho thông điệp giả.

Quy trình thu hồi nên:

1. Xác định partner/workload, environment, tenant, key ID và thời điểm có thể lộ.
2. Chặn các endpoint hoặc quy tắc chấp nhận nguy hiểm khi còn dùng key cũ.
3. Sinh **MAC key mới** có entropy đủ mạnh, cấp phát an toàn đến đúng hai bên.
4. Kích hoạt key mới theo mốc phối hợp; chỉ giữ cửa sổ xác minh key cũ khi rủi ro cho phép.
5. Kiểm tra **timestamp, request ID và idempotency** để chống replay; một tag đúng không tự ngăn gửi lại thông điệp.
6. Ngừng hẳn key cũ, kiểm tra các bản sao và log giao dịch có nguy cơ giả mạo.

Với khóa **đã bị compromised**, một cửa sổ “chấp nhận cả v1 và v2” thường là rủi ro lớn: đối thủ tiếp tục có thể giả mạo bằng v1. Cần có quyết định khẩn cấp, không áp dụng máy móc chiến thuật overlap của rotation bình thường.

### 10.2. Pepper bị lộ

Pepper trong password hashing là bí mật **khác salt**. Nếu pepper bị lộ cùng với password hash, kẻ tấn công có thể thực hiện quá trình thử mật khẩu theo thiết kế. Cần giữ **Argon2id/scrypt/PBKDF2 phù hợp**, salt riêng cho từng bản ghi và triển khai migration/đặt lại mật khẩu theo rủi ro.

**Không thể luôn “rewrap” hoặc thay pepper trên toàn bộ password verifier mà không có mật khẩu người dùng**. Vì password hashing một chiều, thường phải chuyển sang pepper mới khi đăng nhập thành công hoặc yêu cầu reset, cùng một thời hạn giải quyết các tài khoản không hoạt động.

### 10.3. Nonce reuse và thu hồi khóa mã hóa

Nếu **AES-GCM nonce** bị lặp dưới cùng DEK, khóa có thể không còn đủ an toàn để tiếp tục mã hóa dù raw key chưa bị lấy. Chính sách thu hồi phải cho phép **trigger từ việc sử dụng mật mã sai**, không chỉ từ việc phát hiện secret trong log.

Việc thay key không tự sửa ciphertext đã tạo bằng nonce sai. Cần xác định bản mã ảnh hưởng, dừng sử dụng DEK, đánh giá re-encrypt và kiểm thử chống lặp nonce trong các instance dùng chung khóa.

## 11. Phân phối trạng thái thu hồi trong hệ thống phân tán

Hệ thống có thể có **key registry**, KMS/HSM, IAM, ứng dụng Java, cache JWT, CDN, gateway, client offline và vùng **DR**. Một policy chỉ có ý nghĩa khi các thành phần ra quyết định **nhìn thấy trạng thái phù hợp**.

### 11.1. Mô hình lan truyền

~~~mermaid
flowchart TD
    DECISION["Revocation decision<br/>incident ID + key ID/version + reason"]
    DECISION --> REG["Key registry / security status"]
    DECISION --> KMS["KMS/HSM: disable, revoke grant,<br/>policy enforcement"]
    DECISION --> TRUST["PKI/JWKS/trust policy<br/>dành cho verifier"]
    REG --> CACHE["Ứng dụng Java / cache / gateway"]
    TRUST --> CACHE
    DECISION --> DR["Replica, region và DR"]
    CACHE --> ACK["Acknowledgement + negative test"]
    KMS --> ACK
    DR --> ACK
    TRUST --> ACK
    ACK --> AUDIT["Audit: đã áp dụng / chưa áp dụng<br/>rủi ro tồn dư"]
~~~

### 11.2. Cách xử lý stale cache

**Stale cache** là một trong những nguyên nhân phổ biến khiến ứng dụng tiếp tục tin khóa cũ:

- Một service giữ bản \`active=true\` từ trước.
- JWT verifier cache JWKS cũ.
- Một vùng DR khôi phục cấu hình cũ.
- Một workload vẫn giữ secret key trong bộ nhớ dù quyền trên KMS đã bị thu hồi.

Biện pháp cần cân nhắc:

1. Cache theo **issuer + key ID/version + environment/tenant/purpose**, không dùng kid làm định danh tin cậy duy nhất.
2. Có cơ chế **invalidating revocation events**, TTL/bộ đếm phiên bản và kiểm tra lại status ở những thao tác nhạy cảm.
3. Với sự cố khẩn, hỗ trợ **push hoặc điều khiển tập trung** để chặn key ngay thay vì chỉ chờ TTL.
4. Khi nguồn policy không sẵn sàng, **không tự fail open** với trạng thái đã biết là revoked/compromised.
5. Sau restore backup, đối chiếu một **tombstone hoặc revocation epoch bền vững** để không hồi sinh trạng thái tin cậy cũ.

**Không có cache strategy nào thay thế quyền kiểm soát KMS/IAM thực tế** nếu workload vẫn giữ raw key ở nơi khác.

### 11.3. SLO và xác nhận thực thi

Chính sách có thể đặt mục tiêu như **thời gian phát hiện**, **thời gian cô lập quyền**, **thời gian mọi verifier nhận policy mới** và **tỷ lệ thành phần xác nhận**. Những ngưỡng này cần được tổ chức phê duyệt và kiểm thử; không có một con số cố định phù hợp mọi hệ thống.

Một bảng theo dõi nên biết:

| Hạng mục | Trạng thái cần đo | Bằng chứng phù hợp |
| --- | --- | --- |
| KMS key / grants | Đã chặn thao tác bị cấm? | Policy API status, negative request test |
| Issuer / signer | Đã ngừng Sign v1 và bắt đầu v2? | Audit Sign, active key version |
| JWKS/PKI | Trạng thái thu hồi được công bố đúng? | Bằng chứng signed CRL/OCSP, registry/JWKS snapshot |
| API verifiers | Đã ngừng chấp nhận token/signature không còn tin cậy? | Negative verify test, cache version |
| DR/backup | Khôi phục có làm sống lại quyền cũ không? | Restore drill, state reconciliation |
| Dữ liệu ciphertext | Đã migrate bản mã liên quan chưa? | Đối soát key ID/version, kiểm tra đọc dữ liệu |

**Đừng báo “revocation complete” chỉ vì một API trả 200 OK**; cần kiểm tra **hành vi bảo mật tại các điểm thực thi**.

## 12. Quy trình vận hành Revocation policy

Một runbook thu hồi có thể tổ chức thành các bước sau.

### Bước 1 — Nhận cảnh báo và xác định đối tượng

Ghi **key ID, version, thuật toán, purpose, owner, environment, tenant, trust source**, và liên kết incident/change ticket. Phân biệt **lộ vật liệu khóa**, **lạm dụng quyền**, **đánh tráo public key**, **lỗi thuật toán** hay **hết hạn bình thường**.

Nếu chưa chắc, có thể **suspend** ngay các thao tác rủi ro cao trong khi bảo toàn log và điều tra.

### Bước 2 — Chặn quyền sử dụng và ngăn phát hành mới

Tùy loại khóa, chặn **Encrypt, Wrap, Sign, GenerateMac** bằng key cũ; thu hồi các IAM grants và workload credentials liên quan. Nếu vẫn cần đường khôi phục, cô lập nó vào **quy trình đặc biệt có phê duyệt**, không để API thông thường tùy ý dùng key bị nghi compromised.

### Bước 3 — Đánh giá phụ thuộc và tác động

Xác định **root → KEK → DEK → ciphertext**, hoặc **signing key → certificate/JWKS → relying parties/tokens**, cùng backup, cache, nhiều region/tenant, kỳ hạn lưu trữ và khoảng thời gian rủi ro.

**Không chỉ đếm số lượng khóa:** một KEK có thể bảo vệ nhiều DEK; một signer có thể ký hàng triệu token đã được lưu trữ hoặc còn hiệu lực.

### Bước 4 — Tạo và phân phối khóa thay thế

Sinh key mới bằng CSPRNG/KMS/HSM được phê duyệt, đặt quyền tối thiểu và key ID/version mới. Đổi signer/MAC key hoặc thực hiện rewrap/re-encrypt theo nhu cầu. Với PKI/JWKS, bảo đảm relying parties có đường nhận public verification key mới **đáng tin cậy**.

### Bước 5 — Công bố và thực thi trạng thái thu hồi

Ban hành revocation record có lý do, thời điểm, policy version và danh sách điểm phải cập nhật. Đồng bộ tới registry, KMS/HSM, IAM, PKI/JWKS, các dịch vụ xác minh, cache và DR.

### Bước 6 — Xác minh bằng test âm tính và test khả dụng

**Test âm tính:** yêu cầu Sign/Decrypt/Verify bằng key bị cấm phải bị từ chối **ở đúng các ngữ cảnh policy quy định**. **Test khả dụng:** dữ liệu cần lưu vẫn có thể truy xuất bằng đường migration được phép, token/chữ ký mới được xác minh đúng và các dịch vụ không tự động tắt xác thực để vượt lỗi.

### Bước 7 — Thu hồi/hủy vật liệu và lưu hồ sơ

Khi không còn phụ thuộc hoặc đã có quyết định về rủi ro mất khả năng đọc, tiến hành retire/destroy theo API và chính sách riêng. Nếu hành động mới ở **pending deletion**, chưa được báo là đã hủy. Giữ audit record và rủi ro tồn dư không chứa secret material.

## 13. Java 17: policy gate chặn sử dụng khóa đã thu hồi

Ví dụ sau minh họa cách **ứng dụng Java có thể từ chối một thao tác** nếu key registry xác định khóa đã revoked/suspended, sai environment, sai tenant hoặc policy snapshot đã quá hạn.

**Ranh giới:** Đây là **logic policy gate**; không phải một SDK thu hồi khóa hoàn chỉnh và **không gọi trực tiếp KMS**. Trong production, trạng thái phải được lấy từ **registry đã xác thực**, quyền IAM/KMS phải được cấu hình độc lập và việc chặn phải được kiểm chứng tại API thực.

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public final class RevocationPolicyDemo {
    enum KeyState {
        ACTIVE, SUSPENDED, RETIRED, REVOKED, DESTROYED
    }

    enum Operation {
        ENCRYPT, DECRYPT, WRAP, UNWRAP, SIGN, VERIFY, GENERATE_MAC
    }

    record KeyRecord(
            String keyId,
            int version,
            String environment,
            String tenant,
            KeyState state,
            Instant revokedEffectiveAt,
            Set<Operation> approvedOperations
    ) {}

    record AuthenticatedWorkload(
            String principalId,
            String environment,
            Set<String> allowedTenants,
            Set<Operation> allowedOperations
    ) {}

    record PolicySnapshot(
            Instant validUntil,
            String policyVersion
    ) {}

    static boolean allowOperation(
            AuthenticatedWorkload workload,
            KeyRecord key,
            PolicySnapshot policy,
            String tenant,
            Operation operation,
            Instant serverNow
    ) {
        if (workload == null || key == null || policy == null ||
                tenant == null || operation == null || serverNow == null) {
            return false;
        }

        // Đừng dùng policy snapshot quá hạn hoặc thiếu metadata tin cậy.
        if (policy.validUntil() == null ||
                !serverNow.isBefore(policy.validUntil()) ||
                policy.policyVersion() == null ||
                policy.policyVersion().isBlank()) {
            return false;
        }
        if (key.keyId() == null || key.keyId().isBlank() ||
                key.version() <= 0 || key.state() != KeyState.ACTIVE) {
            return false;
        }

        // Chặn key có mốc revoke đã có hiệu lực.
        if (key.revokedEffectiveAt() != null &&
                !serverNow.isBefore(key.revokedEffectiveAt())) {
            return false;
        }

        // Các trường workload đến từ hệ thống xác thực,
        // không phải do HTTP client tự đặt.
        if (workload.principalId() == null ||
                workload.principalId().isBlank() ||
                !Objects.equals(workload.environment(), key.environment()) ||
                !Objects.equals(key.tenant(), tenant)) {
            return false;
        }
        if (!workload.allowedTenants().contains(tenant)) {
            return false;
        }
        return workload.allowedOperations().contains(operation) &&
                key.approvedOperations().contains(operation);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-28T00:00:00Z");
        PolicySnapshot snapshot = new PolicySnapshot(
                now.plusSeconds(120), "revocation-policy-v2");

        AuthenticatedWorkload signer = new AuthenticatedWorkload(
                "orders-prod-signer", "production",
                Set.of("tenant-a"), Set.of(Operation.SIGN));

        KeyRecord active = new KeyRecord(
                "sign-prod", 2, "production", "tenant-a",
                KeyState.ACTIVE, null, Set.of(Operation.SIGN));
        KeyRecord revoked = new KeyRecord(
                "sign-prod", 1, "production", "tenant-a",
                KeyState.REVOKED, now.minusSeconds(30),
                Set.of(Operation.SIGN));

        System.out.println("Active v2 SIGN: " +
                allowOperation(signer, active, snapshot,
                        "tenant-a", Operation.SIGN, now));
        System.out.println("Revoked v1 SIGN: " +
                allowOperation(signer, revoked, snapshot,
                        "tenant-a", Operation.SIGN, now));
        System.out.println("Expired policy snapshot: " +
                allowOperation(signer, active,
                        new PolicySnapshot(now.minusSeconds(1), "old"),
                        "tenant-a", Operation.SIGN, now));
    }
}
~~~

**Kết quả mong đợi:**

~~~text
Active v2 SIGN: true
Revoked v1 SIGN: false
Expired policy snapshot: false
~~~

### 13.1. Những bảo đảm code chưa cung cấp

1. **\`KeyState.ACTIVE\` phải đến từ nguồn tin cậy.** Nếu client có thể sửa record thành ACTIVE, policy gate không còn giá trị.
2. Snapshot policy phải có **phiên bản và tính toàn vẹn**, cơ chế invalidation khi có thu hồi khẩn; TTL ngắn không tự bảo đảm cập nhật ngay.
3. **\`allowOperation\` chỉ là một lớp từ chối sớm**. IAM/KMS/HSM cần tự chặn thao tác theo quyền và trạng thái thực.
4. Chương trình minh họa từ chối **mọi thao tác** với khóa revoked. Nếu có **xác minh chữ ký lịch sử** được phê duyệt, nên dùng **luồng riêng** có chính sách và bằng chứng tin cậy; không mở lỏng điều kiện Verify trong đường thông thường.
5. Production cần xử lý race condition giữa **kiểm tra policy** và **gọi KMS**. Revocation control plane phải cập nhật KMS/grants để khóa không tiếp tục được dùng nếu trạng thái thay đổi giữa hai thao tác.
6. Khóa bị compromised có thể đã tồn tại **ngoài KMS**. Việc trả \`false\` trong Java không thu hồi được raw key mà kẻ tấn công đã sao chép.
7. Log nên ghi key ID/version, principal, operation, tenant, policy decision và correlation ID; **không ghi private key, DEK, MAC key, pepper hoặc plaintext**.

### 13.2. Tại sao không tự động cho VERIFY với key bị revoked?

Một chữ ký có thể hợp lệ về toán học dù khóa đã bị lộ; việc cho phép Verify phụ thuộc câu hỏi **“có được chấp nhận chữ ký này cho mục đích và thời điểm này hay không?”**. Đường xử lý lưu trữ dài hạn có thể kiểm tra **trusted timestamp, trạng thái chứng chỉ lịch sử và chính sách hồ sơ**. Đây là bài toán khác với chấp nhận token hoặc yêu cầu mới trong một API giao dịch.

## 14. Tình huống hệ thống: khóa ký JWT production bị nghi xâm phạm

Giả sử nền tảng Java có:

- **Identity Service** ký access token bằng private RSA key trong HSM.
- **JWKS endpoint** công bố public verification key theo \`kid\`.
- **12 API services** cache JWKS theo chu kỳ.
- **KMS/HSM audit** ghi nhận nhiều lệnh Sign từ một workload identity không còn đáng tin cậy.

### 14.1. Phản ứng theo policy

**Giai đoạn xác minh ban đầu:**

1. Gắn incident ID với signer key v1, xác minh principal, thời gian và log Sign; không mặc định kết luận private key đã bị xuất.
2. **Tạm dừng lệnh Sign v1**, thu hồi credential/grant nghi bị chiếm và bảo vệ HSM.
3. Đánh giá token/chữ ký đã ký trong khoảng có thể bị lạm dụng, phân biệt sự cố **Sign API abuse** với **raw key exposure**.

**Giai đoạn thay và thu hồi:**

4. Kích hoạt private key v2 đáng tin cậy; phát hành public verification key v2 trong registry/JWKS từ issuer đã được xác thực.
5. Ban hành revocation policy cho v1. Với key compromised, không chỉ coi nó là rotation bình thường có cửa sổ chấp nhận v1 kéo dài.
6. Đẩy invalidation/phiên bản trust policy đến các API; xử lý API offline hoặc cache chưa nhận theo mức độ rủi ro và kế hoạch fail closed.
7. Nếu cần, vô hiệu hóa token/phiên liên quan; kiểm tra **\`iss\`, \`aud\`, \`exp\`, token type, scope** và quyền sau Verify.

**Giai đoạn chứng minh hiệu lực:**

8. Mỗi API thử một token do khóa v1 ký trong tình huống không còn được phép và phải **từ chối**; token v2 hợp lệ phải được xử lý đúng.
9. Kiểm tra một API vừa được khôi phục từ backup không quay về trust policy cũ.
10. Kiểm tra HSM không còn nhận Sign v1, ghi ack từ từng dịch vụ và rủi ro của bên thứ ba chưa cập nhật.

### 14.2. Điều gì sẽ thất bại nếu chỉ xóa JWK v1?

| Thành phần | Rủi ro còn lại |
| --- | --- |
| HSM | Principal xấu có thể vẫn gọi Sign bằng v1 nếu chưa chặn |
| API verifier | Cache cũ có thể chấp nhận token v1 |
| Token | Token v1 có chữ ký hợp lệ toán học và còn \`exp\` |
| DR/backup | Restore có thể tái phân phối cấu hình hoặc trust cũ |
| Key registry | Có thể ghi revoked nhưng chưa thực thi ở API thực |
| Audit | Không biết hệ thống nào đã áp dụng hoặc chưa áp dụng |

**Bài học:** Revocation policy phải liên kết **phía tạo chữ ký, phía phân phối trust, phía xác minh và các phiên/token đang tồn tại**. Chỉ sửa một endpoint không tạo ra sự bảo đảm toàn hệ thống.

## 15. Kiểm toán, đo lường và các quyết định ngoại lệ

### 15.1. Hồ sơ revocation cần ghi những gì?

| Trường | Mục đích |
| --- | --- |
| **revocationId / incidentId** | Liên kết cảnh báo, quyết định và bằng chứng |
| **keyId + keyVersion + owner** | Xác định đúng vật liệu và chủ thể chịu trách nhiệm |
| **keyType / purpose / environment** | Xác định hành vi bị cấm và miền ảnh hưởng |
| **reason + evidence reference** | Lý do thu hồi và căn cứ, không chứa key bytes |
| **suspectedAt / decidedAt / effectiveAt** | Phân biệt mốc sự cố, quyết định và hiệu lực |
| **requester / approver / emergency authority** | Kiểm soát quyền và tách nhiệm vụ |
| **policyVersion / enforcement targets** | Truy xuất quy tắc áp dụng và nơi cần cập nhật |
| **acks / negative-test results** | Bằng chứng không còn chấp nhận/sử dụng khóa ở nơi bị cấm |
| **migration / residual dependencies** | Dữ liệu, token, chữ ký, backup còn chịu ảnh hưởng |
| **closure + residual risk** | Kết luận chính xác những gì đã/ chưa xử lý |

### 15.2. Các chỉ số vận hành đáng theo dõi

- **Time to detect:** Thời gian phát hiện nguy cơ sau sự kiện xâm phạm.
- **Time to contain:** Thời gian chặn quyền sử dụng nguy hiểm.
- **Propagation lag:** Độ trễ từ quyết định đến khi từng verifier/workload áp dụng.
- **Unacknowledged relying parties:** Số thành phần chưa xác nhận trạng thái mới.
- **Legacy key usage:** Các yêu cầu còn thử dùng key đã revoked/retired.
- **Data migration coverage:** Tỷ lệ ciphertext/wrapped DEK đã chuyển theo policy.
- **Revocation test failures:** Các trường hợp key cũ vẫn được chấp nhận trái chính sách.

Không đặt mục tiêu đẹp trên giấy rồi không kiểm thử **client offline, cache, đa region, thất bại mạng và restore backup**.

### 15.3. Ngoại lệ phải có thời hạn và bằng chứng

Một số nghiệp vụ có thể yêu cầu đường **Decrypt recovery** hoặc **xác minh chữ ký lịch sử** sau khi key đã retired. Nếu khóa đã compromised, ngoại lệ cần thẩm định riêng và không được cho phép tạo giá trị mật mã mới trái policy.

Hồ sơ ngoại lệ nên có **lý do, owner, phạm vi dữ liệu, thao tác, thời điểm hết hiệu lực, người phê duyệt độc lập và audit**. Không cấu hình \`allowRevoked=true\` như một cờ chung có thể bật cho mọi dịch vụ.

## 16. Các lỗi hay gặp khi xây chính sách thu hồi

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ cập nhật \`status=REVOKED\` trong database | KMS, HSM, JWT verifier hoặc cache vẫn có thể dùng key | Đồng bộ control plane, IAM, KMS và relying parties; negative test |
| Coi disable là destroy | Raw key và backup có thể vẫn tồn tại | Phân biệt thao tác, evidence và quy trình hủy |
| Coi rotation tự sửa compromise | Bản sao key/ciphertext cũ vẫn có thể bị khai thác | Đánh giá thay DEK, re-encrypt, thu hồi quyền và dữ liệu đã lộ |
| Dùng overlap v1/v2 dài với MAC key bị lộ | Đối thủ tiếp tục giả mạo bằng v1 | Phân biệt compromised revocation với planned rotation |
| Cho client tự chọn \`kid\` để mở trust tùy ý | Dùng nhầm key của issuer/tenant khác | Gắn issuer, owner, purpose, environment và key policy |
| Tin URL JWKS do token chưa xác thực chỉ định | Key substitution và rủi ro SSRF | Chỉ dùng issuer/endpoint đã được cấu hình tin cậy |
| Xóa JWK và tưởng mọi token bị từ chối ngay | Cache/verifier offline còn chấp nhận token cũ | Invalidation, trust version, policy về token/phiên |
| Để JWT \`exp\` quyết định toàn bộ sự cố | Token giả vẫn có thể có exp hợp lệ | Kiểm tra signing key status, issuer, session và quyền |
| Không xác thực trạng thái chứng chỉ | Có thể tin cert đã bị revoke | Thực thi PKI revocation checks theo policy và ngữ cảnh |
| Xem lỗi OCSP/CRL là “good” mặc định | Chấp nhận chứng chỉ khi chưa có bằng chứng phù hợp | Quy định fail-closed hoặc bằng chứng cache còn hiệu lực |
| Cho VERIFY lịch sử tự động với revoked key | Có thể chấp nhận chữ ký giả mới | Dùng đường forensic/historical policy có chứng cứ thời gian |
| Chỉ revoke grant nhưng key bytes đã lộ | Kẻ có raw key vẫn dùng bên ngoài KMS | Xử lý compromise vật liệu, thay key và dữ liệu phụ thuộc |
| Hủy key ngay khi dữ liệu cũ còn cần đọc | Mất khả năng khôi phục hợp lệ | Inventory, migration và approval trước destruction |
| Quên DR, backup hoặc cache lâu | Key cũ bị hồi sinh sau restore | Tombstone, đối soát và thử restore |
| Không lưu incident/effective timestamps | Không xác định được khoảng phơi nhiễm và chứng cứ | Lưu sự kiện, ack và kết quả kiểm thử theo timeline |
| Log private key/DEK để “debug revoke” | Làm rộng thêm phạm vi lộ bí mật | Audit metadata/key ID, tuyệt đối tránh key material |

## 17. Checklist đánh giá Revocation policy

Trước khi coi chính sách thu hồi đã sẵn sàng cho production, hãy trả lời:

1. **Đối tượng:** Đang thu hồi vật liệu khóa, quyền API, chứng chỉ, public verification key, trust anchor, MAC key hay pepper?
2. **Nguyên nhân:** Có phân biệt suspected, confirmed compromise, expiry và planned retirement?
3. **Phạm vi:** Có key ID/version, owner, tenant, environment, region, purpose và hệ thống phụ thuộc?
4. **Authority:** Ai được tạm đình chỉ khẩn cấp, ai phê duyệt revocation và ai quyết định destruction?
5. **Hiệu lực:** Có tách suspectedAt, decidedAt, effectiveAt và thời gian lan truyền thực tế?
6. **Thao tác:** Với trạng thái revoked/suspended, những phép Encrypt/Decrypt/Wrap/Unwrap/Sign/Verify/GenerateMac nào bị cấm?
7. **KMS/HSM/IAM:** Đã thật sự thu hồi principal/grant và chặn API chứ không chỉ thay field trong inventory?
8. **PKI:** Nếu liên quan chứng chỉ, đã xem xét chain, trust anchor, CRL/OCSP, hiệu lực và bên xác minh?
9. **JWT/JWKS:** Có cách xử lý cache, \`kid\`, issuer, token đã phát hành và client offline?
10. **Khóa chung:** MAC key/pepper có quy trình cấp phát mới và migration phù hợp với tính chất của từng cơ chế?
11. **Dữ liệu:** Đã lập bản đồ DEK/KEK/root và quyết định rewrap hay re-encrypt đúng rủi ro?
12. **Lịch sử:** Có chính sách riêng cho chữ ký/tài liệu cần xác minh lịch sử mà không tạo lối đi vòng cho token mới?
13. **Phân phối:** Có ack, TTL/invalidation, negative test và xử lý stale cache ở mọi environment/DR?
14. **Lỗi:** Khi policy, KMS, OCSP hoặc registry không sẵn sàng, có tránh fail-open và fallback sang key bị cấm?
15. **Kiểm toán:** Có incident ID, lý do, bằng chứng, mốc thời gian, người phê duyệt và phạm vi còn tồn dư?
16. **Kiểm thử:** Đã thử signed token cũ, revoked key, cross-tenant, restore backup, nhiều instance và race condition?
17. **Kết thúc:** Có tiêu chí xác minh việc chặn, migration, xử lý backup/retention và destruction theo phạm vi?

## 18. Ghi nhớ

- **Revocation policy** quyết định **lúc nào và bằng cách nào ngừng tin/cho phép dùng khóa**. Nó khác với **rotation, disable, expiry và destruction**.
- **Thu hồi phải có hiệu lực tại nơi sử dụng hoặc xác minh**, không chỉ trong key registry. KMS/HSM/IAM, PKI/JWKS, cache, client và DR có thể cần cập nhật bằng những cơ chế khác nhau.
- **Một khóa bị compromised không trở lại bí mật sau khi bị revoke.** Nếu raw DEK đã lộ, phải đánh giá thay DEK và re-encrypt; rewrap đơn thuần không đủ.
- **Chữ ký số và chứng chỉ có chiều thời gian:** kiểm tra chữ ký lịch sử theo bằng chứng/thời điểm/chính sách phù hợp; không mặc định tin revoked key cho các yêu cầu mới.
- **JWT/JWKS và HMAC đều cần quy trình xử lý key cũ**, vì token cũ, cache cũ và bí mật chia sẻ cũ có thể tiếp tục được sử dụng.
- **Phân quyền, kiểm toán, incident response và kiểm thử phủ định** biến một quyết định thu hồi thành biện pháp bảo mật đo được.
- **Fail closed** với những thao tác không còn được phép, nhưng vẫn thiết kế **đường migration/forensic có phê duyệt** khi phải bảo vệ dữ liệu hợp lệ và nghĩa vụ lưu trữ.

Khi xây **Revocation policy**, hãy bắt đầu bằng ba câu hỏi: **“Khóa nào không còn đáng tin và vì sao?”, “Những thành phần nào vẫn có thể dùng hoặc chấp nhận khóa đó?”, “Bằng chứng nào chứng minh quyền sử dụng và niềm tin đã thực sự bị thu hồi mà không làm mất dữ liệu cần giữ?”** Câu trả lời cho ba câu hỏi này quyết định một chính sách có thực thi được hay chỉ tồn tại trên tài liệu.

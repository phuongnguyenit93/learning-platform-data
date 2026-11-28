# Key owner

> **Chương:** Vai trò và trách nhiệm  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Key owner là ai?

**Key owner (chủ sở hữu chịu trách nhiệm đối với khóa)** là **vai trò chịu trách nhiệm cuối cùng về việc một khóa mật mã được tạo, quản trị, sử dụng, thay thế và kết thúc vòng đời theo đúng mục đích và chính sách**. Key owner có trách nhiệm xác định **vì sao khóa tồn tại, tài sản/dữ liệu nào phụ thuộc vào khóa, ai được phép dùng, mức rủi ro được chấp nhận và khi nào cần thay đổi hoặc thu hồi khóa**.

Trong một doanh nghiệp, key owner có thể là **một bộ phận được chỉ định**, ví dụ nhóm phụ trách nền tảng thanh toán, kèm người chịu trách nhiệm chính và người dự phòng. Key owner **không nhất thiết là người trực tiếp giữ byte secret key**, không mặc nhiên có quyền xuất private key, không phải tài khoản thực thi mọi thao tác mật mã và cũng không phải người được tự ý vượt qua IAM/KMS/HSM.

Ví dụ: **Billing Security Owner** được giao trách nhiệm đối với KEK bảo vệ DEK của dữ liệu thanh toán. Nhóm nền tảng KMS vận hành HSM; dịch vụ Billing được cấp quyền `WrapKey/UnwrapKey` theo nhu cầu; bộ phận an ninh kiểm soát chính sách; auditor kiểm tra bằng chứng. Nếu key sắp hết cryptoperiod hoặc một workload bị chiếm, **key owner phải bảo đảm có quyết định và người thực hiện**, dù không tự cầm private key.

**Thông điệp chính:** *ownership* là **accountability** (trách nhiệm giải trình và quyết định trong phạm vi được giao), không phải **possession** (đang có bản sao vật liệu khóa) hay **unlimited privilege** (mọi quyền trên KMS).

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **key owner**, **key custodian**, **key administrator**, **key user**, **data owner**, **security officer** và **auditor**.
- Xây dựng **RACI** rõ ràng cho các hoạt động tạo, cấp phát, kích hoạt, sử dụng, xoay vòng, thu hồi và hủy khóa.
- Định nghĩa trách nhiệm owner về **algorithm/key policy, cryptoperiod, IAM, inventory, audit, KMS/HSM, backup và ứng phó sự cố**.
- Thiết kế **phân tách nhiệm vụ (separation of duties)**, không cấp mọi quyền cho một tài khoản vì người đó là owner.
- Xử lý **chuyển giao ownership**, khóa mồ côi, thay đổi tổ chức và trách nhiệm đối với DEK/KEK, khóa ký số, PSK.
- Thực hành mô hình phân quyền bằng **Java 17** và hiểu vì sao kiểm tra tại ứng dụng không thay thế KMS/HSM authorization.

## 2. Vì sao cần một key owner được chỉ định rõ?

Không có owner, khóa có thể vẫn mã hóa và giải mã dữ liệu trong nhiều năm, nhưng khi có biến cố lại không ai trả lời được những câu hỏi cơ bản:

1. **Khóa này bảo vệ dữ liệu gì, thuộc tenant/hệ thống nào?**
2. **Ai đã phê duyệt thuật toán, mục đích sử dụng và mức bảo vệ?**
3. **Khi nào phải ngừng tạo bản mã/chữ ký mới bằng key version hiện tại?**
4. **Những bản sao lưu và ciphertext nào còn cần khóa cũ?**
5. **Ai có quyền chấp thuận rotation, revocation hoặc destruction?**
6. **Ai chịu trách nhiệm phối hợp với các verifier khi public signing key thay đổi?**
7. **Ai điều phối xử lý sự cố nếu secret bị lộ hoặc HSM/secret store bị lạm dụng?**

Đây là vấn đề **quản trị rủi ro** chứ không thuần túy là vấn đề API. Một key AES-256 được sinh bằng CSPRNG và nằm trong HSM vẫn có thể gây thiệt hại nếu **không rõ ràng người chịu trách nhiệm, quyền dùng quá rộng hoặc khóa bị xóa trước khi kiểm tra backup**.

### Ví dụ thất bại do thiếu ownership

Ba dịch vụ cùng dùng một KEK: Billing, Reports và Archive. Nhóm Billing đổi sang KEK mới rồi xóa KEK cũ vì nghĩ đã hoàn thành rotation. Reports có thể vẫn chạy vì dùng DEK mới, nhưng Archive mất khả năng unwrap DEK trong backup năm trước.

**Nguyên nhân gốc** không chỉ là thiếu test. Không có key owner chịu trách nhiệm xác định **phạm vi phụ thuộc, recipient-usage period, rollback và điều kiện hủy khóa**, còn các nhóm sử dụng key không có quy trình được tham vấn.

Key owner giải quyết lỗ hổng này bằng **inventory, change approval, RACI và bằng chứng kiểm tra dữ liệu phụ thuộc trước khi thay đổi trạng thái khóa**.

## 3. Phân biệt các vai trò trong key management

Tên gọi có thể khác giữa tổ chức, cloud provider và tiêu chuẩn. Bảng sau là **mô hình phân vai tham khảo**, không phải định nghĩa chức danh bắt buộc của một sản phẩm KMS.

| Vai trò | Trách nhiệm chính | Không tự động có quyền |
| --- | --- | --- |
| **Key owner** | Chịu trách nhiệm về policy, mục đích, quyền sử dụng, vòng đời, rủi ro và quyết định thay đổi khóa | Xuất raw key, gọi mọi `Decrypt`/`Sign`, sửa log |
| **Key custodian** | Bảo quản, vận hành và bảo vệ vật liệu khóa/backup theo quy trình được duyệt | Tự quyết mục đích dùng khóa hoặc bỏ qua phê duyệt |
| **Key administrator / KMS operator** | Cấu hình KMS/HSM, key state, IAM, rotation job, tài nguyên kỹ thuật | Đọc plaintext nghiệp vụ hay duyệt mọi giao dịch |
| **Key user / consuming workload** | Dùng khóa qua API cho operation và resource được ủy quyền | Thay policy, xóa key, export material |
| **Data owner / business owner** | Quyết định phân loại dữ liệu, quyền truy cập dữ liệu và retention nghiệp vụ | Tự cấp `Sign`/`Decrypt` ngoài policy mật mã |
| **Security architect / security officer** | Đưa ra baseline, kiểm soát ngoại lệ, đánh giá rủi ro, điều phối ứng phó | Mặc nhiên giữ tất cả khóa hoặc xử lý mọi request |
| **Approver / change authority** | Duyệt thay đổi nhạy cảm theo workflow và ngưỡng rủi ro | Trở thành executor của thao tác chỉ nhờ quyền duyệt |
| **Auditor** | Xem xét bằng chứng, quyền và tuân thủ, phát hiện bất thường | Mặc nhiên có `ExportKey`, `Decrypt` hoặc `DeleteKey` |
| **Incident commander** | Ra quyết định khẩn cấp và điều phối cô lập khi có sự cố | Tái kích hoạt key đã compromise mà không xử lý rủi ro |

### 3.1. Key owner khác data owner

**Data owner** chịu trách nhiệm dữ liệu, ví dụ “lịch sử giao dịch của tenant A được lưu trong 7 năm và chỉ những nhóm này được đọc”. **Key owner** chịu trách nhiệm **khóa bảo vệ dữ liệu đó**, bao gồm ai vận hành KEK, khi nào rotation và điều kiện hủy.

Hai vai trò có thể do cùng một bộ phận đảm nhiệm trong tổ chức nhỏ, nhưng **quyết định quyền truy cập dữ liệu và quyết định quyền sử dụng khóa vẫn phải được kiểm tra riêng**. Có quyền `Decrypt` trên KMS **không đồng nghĩa** người dùng được đọc mọi bản ghi thuộc mọi tenant.

### 3.2. Key owner khác key custodian

Key owner quyết định **mục tiêu và mức rủi ro chấp nhận**; key custodian bảo đảm **vật liệu được bảo vệ và thao tác được thực hiện đúng quy trình**.

Ví dụ, owner phê duyệt “private key ký hóa đơn không được xuất khỏi HSM”. Custodian vận hành HSM, tạo key bên trong thiết bị, cấu hình quyền và lưu bằng chứng key reference; owner **không cần và không nên yêu cầu xuất PEM của private key để kiểm tra**.

### 3.3. Chủ sở hữu nên là vai trò tổ chức, có người chịu trách nhiệm cụ thể

Gắn ownership duy nhất với tên một nhân viên dễ sinh **orphan key** khi người đó nghỉ việc. Một thực hành tốt là ghi **owner team/service**, **accountable contact** và **backup/delegate**, đồng thời có workflow thay đổi người phụ trách. Không dùng một hộp thư chung không có người chịu trách nhiệm hoặc một tài khoản root làm câu trả lời cho câu hỏi “owner là ai?”.

## 4. Mẫu RACI cho các hoạt động trên vòng đời khóa

**RACI** giúp làm rõ:

- **R — Responsible:** trực tiếp thực hiện công việc.
- **A — Accountable:** chịu trách nhiệm cuối cùng về quyết định và kết quả; thông thường một A rõ ràng cho một hoạt động.
- **C — Consulted:** cần tham vấn trước khi ra quyết định.
- **I — Informed:** cần nhận thông tin/kết quả.

Bảng dưới đây là **ví dụ tổ chức**, không phải sơ đồ phân quyền áp đặt cho mọi doanh nghiệp. “App team” ở đây đại diện cho owner của workload sử dụng khóa, không phải người dùng cuối.

| Hoạt động | Key owner | KMS custodian | App team | Security / IR | Auditor |
| --- | --- | --- | --- | --- | --- |
| Định nghĩa purpose/cryptoperiod/key profile | **A** | R | C | C | I |
| Sinh key version theo policy đã duyệt | **A** | **R** | C | C | I |
| Đăng ký key inventory và activation plan | **A** | **R** | C | C | I |
| Phê duyệt quyền dùng `Sign/Wrap/Decrypt` | **A** | R | C | C | I |
| Xác thực quyền truy cập dữ liệu nghiệp vụ | I | C | **A/R** | C | I |
| Chuyển primary và rotation có kế hoạch | **A** | **R** | R | C | I |
| Cô lập/revoke khẩn cấp khi compromise | C | R | R | **A** | I |
| Xác nhận không còn dữ liệu phụ thuộc trước destroy | **A** | R | C | C | I |
| Đánh giá định kỳ bằng chứng và tuân thủ | A | C | C | C | **R** |

**Chú ý:** bảng thể hiện **trách nhiệm làm việc**, không phải cấp quyền máy móc. Việc người nào là A cho rotation **không tự tạo IAM `kms:ScheduleKeyDeletion`**. Một sự cố khẩn cấp có thể có incident commander được ủy quyền **revoke ngay** để hạn chế thiệt hại, rồi hoàn tất phê duyệt và hậu kiểm; không nên phải chờ key owner không liên lạc được trong khi attacker tiếp tục ký giả.

### Quy tắc thiết kế RACI

1. Mỗi hành động quan trọng có **người chịu trách nhiệm quyết định cuối cùng**.
2. Vai trò **thực hiện** và **phê duyệt** được phân tách khi rủi ro yêu cầu.
3. **Khẩn cấp** có đường xử lý riêng nhưng phải kiểm toán và hậu kiểm.
4. Có người dự phòng, lịch trực và cách **escalate** khi owner vắng mặt.
5. RACI được ánh xạ sang **IAM/KMS policies, ticket workflow và access review**; không chỉ là bảng trong tài liệu.

## 5. Trách nhiệm cốt lõi của key owner

### 5.1. Xác định mục đích và phạm vi bảo vệ

Owner phải biết **khóa dùng để làm gì**: AES-GCM bảo vệ dữ liệu, KEK bọc DEK, HMAC xác thực thông điệp, private key ký chứng từ, PSK xác thực thiết bị hay ECDH phục vụ key agreement.

Khóa cần gắn với **service, tenant, environment, data classification, protocol và authorized operations**. Một key dùng cho staging không được chuyển sang production chỉ vì cùng thuật toán; một HMAC key không nên được dùng lại làm AES key.

### 5.2. Phê duyệt chính sách sinh khóa

Owner chịu trách nhiệm bảo đảm có **key generation policy** được phê duyệt:

- Thuật toán, key size/curve, provider và mức an toàn phù hợp.
- **CSPRNG/DRBG** hoặc đường sinh trong **KMS/HSM**; không seed từ timestamp, `Math.random()` hay `Random` cho bí mật.
- Yêu cầu **exportability/non-extractability**, boundary, backup và key import.
- Profile riêng cho DEK, KEK, private signing key, PSK và session secrets khi cần.
- Thẩm quyền tạo khóa, workflow approval, inventory và audit.

Owner không nhất thiết tự viết code sinh khóa. Custodian hoặc nền tảng kỹ thuật có thể thực hiện, nhưng owner phải **được thông báo và có bằng chứng rằng kết quả đúng profile**.

### 5.3. Bảo đảm quyền tối thiểu

Owner xác định **ai cần thao tác mật mã gì**; KMS/IAM admin cấu hình và kiểm tra quyền theo quy trình. Ví dụ, signer chỉ cần `Sign`, verifier chỉ cần public key; dịch vụ báo cáo có thể không cần `Unwrap` nếu nhận dữ liệu đã được ứng dụng có quyền xử lý.

### 5.4. Quản lý cryptoperiod và rotation

Owner bảo đảm có kế hoạch **activation, thời hạn tạo bảo vệ mới, thời gian xử lý dữ liệu cũ, rotation triggers và destruction criteria**. Khi đến hạn, successor key/version phải được chuẩn bị trước, key registry/trust được cập nhật và các dịch vụ phụ thuộc được kiểm thử.

### 5.5. Xác định retention và kế hoạch phục hồi

Khóa cũ có thể vẫn cần để **decrypt/unwrap backup, xác minh chữ ký lịch sử hoặc phục hồi dữ liệu**. Owner phải tham vấn data owner về retention và kiểm tra restore trước khi chấp thuận hủy. **Hủy KEK sớm có thể làm mất dữ liệu hợp lệ vĩnh viễn**, trong khi giữ secret quá lâu làm tăng rủi ro bị lộ.

### 5.6. Điều phối sự cố và theo dõi audit

Owner bảo đảm có runbook khi **khóa bị lộ, bị dùng sai mục đích, mất khả năng sử dụng, principal bị chiếm hoặc policy bị sửa trái phép**. Không phải owner tự điều tra mọi log; phải có trách nhiệm phối hợp security, custodian, app team và đối tác.

**Một key owner tốt chịu trách nhiệm về kết quả kiểm soát**, không đơn giản là người có thể mở dashboard và nhìn thấy trạng thái Enabled.

## 6. Vòng đời khóa qua góc nhìn key owner

~~~mermaid
flowchart TD
    Req[Nhu cầu bảo vệ dữ liệu hoặc chữ ký] --> Owner[Key owner xác định scope và risk]
    Owner --> Policy[Phê duyệt generation/usage/lifecycle policy]
    Policy --> Gen[Custodian / KMS/HSM sinh khóa đúng profile]
    Gen --> Inv[Đăng ký key ID/version và owner vào inventory]
    Inv --> Activate[Pre-active, kiểm tra activation và IAM]
    Activate --> Use[Workload dùng khóa đúng purpose]
    Use --> Monitor[Audit, usage limits, cryptoperiod]
    Monitor --> Decision{Đến hạn hoặc có sự cố?}
    Decision -->|Rotation bình thường| Rotate[Tạo successor và chuyển primary]
    Decision -->|Suspected compromise| Revoke[Containment / revoke / incident response]
    Rotate --> Dep[Kiểm tra dữ liệu và backup phụ thuộc]
    Revoke --> Dep
    Dep --> Destroy[Phê duyệt hủy sau khi đủ điều kiện]
~~~

Các bước cụ thể khác nhau giữa **khóa phiên TLS tạm thời**, **DEK ngắn hạn**, **KEK dài hạn** và **khóa ký số**. Với khóa phiên, nhiều thao tác do giao thức tự quản; owner có thể chịu trách nhiệm **policy và cấu hình TLS/PSK** thay vì phê duyệt từng traffic key được sinh tự động.

### Trách nhiệm theo giai đoạn

| Giai đoạn | Quyết định/đầu ra owner cần bảo đảm |
| --- | --- |
| **Plan / Generate** | Purpose, thuật toán, nguồn sinh, HSM/KMS boundary, owner, approval |
| **Provision** | Phân phối đúng hệ thống, môi trường, tenant; không để raw key vào file/log |
| **Pre-active** | Key ID/version, metadata, IAM và kế hoạch kích hoạt đầy đủ |
| **Active / Use** | Chỉ cho phép đúng operation, resource, thời gian và hạn mức |
| **Rotate / Rekey** | Khóa mới, cutover, khả năng đọc dữ liệu/chữ ký cũ, cache invalidation |
| **Suspend / Revoke** | Từ chối thao tác không còn được phép, rút trust nơi cần thiết |
| **Retire / Archive** | Giữ khả năng khôi phục hợp lệ, không ký/mã hóa mới bằng key hết hạn |
| **Destroy** | Xác định không còn dữ liệu/backup phụ thuộc, có quyết định crypto-erasure nếu chủ đích |
| **Audit** | Chứng minh lịch sử ra quyết định và việc enforce thực tế |

## 7. Key owner, IAM và separation of duties

**Ownership phải được chuyển thành chính sách có thể thực thi**. IAM và KMS/HSM policy bảo vệ thao tác kỹ thuật, trong khi authorization của ứng dụng bảo vệ dữ liệu và nghiệp vụ.

### 7.1. Quyền key admin và key user phải khác nhau

Ví dụ một KEK trong KMS có thể liên quan:

| Vai trò kỹ thuật | Quyền điển hình (mang tính khái niệm) | Không nên có |
| --- | --- | --- |
| **Key provisioning service** | Tạo/đăng ký key đúng profile | Quyền đọc dữ liệu khách hàng không cần thiết |
| **Key policy administrator** | Quản lý metadata và policy được phê duyệt | Xuất private key hoặc tự decrypt mọi record |
| **Billing runtime** | `Wrap/Unwrap` DEK theo workload và scope | `DeleteKey`, sửa audit, xuất KEK |
| **Signing runtime** | `Sign` qua HSM theo approval nghiệp vụ | Export private key, sửa chứng thư/registry |
| **Verifier** | Lấy public key đáng tin để `Verify` | Quyền `Sign` hoặc private key |
| **Security auditor** | Đọc audit và policy snapshots | Gọi `Decrypt`/ `Sign` không cần thiết |

Các tên operation chỉ để giải thích; **API và IAM actions thực tế khác nhau theo nhà cung cấp**. Có nơi `DisableKey` chặn mọi hoạt động, có nơi có key version state và quyền chi tiết; owner phải **kiểm tra bằng negative tests**, không suy luận chỉ từ tên API.

### 7.2. Phân tách phê duyệt và thực thi

Với thao tác rủi ro cao như **xóa KEK, export key, thay root trust hoặc đổi signing policy**, có thể yêu cầu **dual control/two-person approval**:

1. Owner đưa ra nhu cầu và đánh giá phụ thuộc/rủi ro.
2. Security/chủ thể phê duyệt độc lập kiểm tra điều kiện.
3. Custodian hoặc automation có quyền được cấp thực thi.
4. Auditor/monitoring đối chiếu việc thực thi với phê duyệt và log.

Không phải mọi khóa phiên hay DEK ngắn hạn đều cần con người ký duyệt. Quy tắc phân quyền phải theo **loại khóa và mô hình đe dọa**, vẫn bảo đảm automation chỉ được làm những việc đã được chủ sở hữu phê duyệt theo policy.

### 7.3. Quyền trên key khác quyền trên dữ liệu

Giả sử data service được `Unwrap` một DEK từ KMS. Service **vẫn phải xác thực tenant/resource và hành động** trước khi giải mã/trả plaintext. Key owner bảo đảm ranh giới khóa; data owner và app team bảo đảm ranh giới dữ liệu. **Không cấp quyền giải mã mọi tenant chỉ vì key hợp lệ**.

## 8. Key owner trong KMS/HSM và kiểm soát vật liệu khóa

**KMS (Key Management Service)** quản lý key references, policies và thao tác theo API dịch vụ. **HSM (Hardware Security Module)** có thể giữ private/secret key trong vùng bảo vệ phần cứng và thực hiện thao tác mà không xuất raw key.

Key owner cần biết **key material thực sự sinh/lưu ở đâu**, chứ không chỉ biết một tên key:

- **Generated inside HSM:** phù hợp khi policy yêu cầu private signing key **không xuất được**.
- **Generated in JVM rồi import:** khóa đã tồn tại ngoài HSM trước khi import; không tương đương lịch sử sinh trong HSM.
- **KMS GenerateDataKey:** trong một số kiến trúc, API trả **DEK dạng rõ tạm thời và bản DEK đã bọc** cho workload; không mặc định mọi KMS có API này.
- **KMS/HSM non-extractable:** giúp giảm rủi ro bị sao chép bytes nhưng **không ngăn lạm dụng API `Sign/Decrypt`** nếu quyền bị chiếm.
- **BYOK/Key import:** owner cần phê duyệt bên sinh, nguồn entropy, kênh import, nơi còn bản sao và trách nhiệm hủy.

Owner không nên yêu cầu “gửi cho tôi private key để kiểm tra”. Thay vào đó, sử dụng **key ID/version, chứng cứ cấu hình, provider metadata, audit và phép thử từ chối export** khi phù hợp.

### 8.1. Shared responsibility với nhà cung cấp cloud

Cloud provider có thể bảo vệ HSM và hạ tầng nền, nhưng tổ chức vẫn phải xác định **ai tạo key, ai được dùng, policy IAM, region, backup, delete protection, retention và incident response**. Key owner chịu trách nhiệm phối hợp ranh giới đó; không mặc nhiên giao toàn bộ trách nhiệm quản trị cho nhà cung cấp vì họ vận hành KMS.

### 8.2. Phòng rủi ro “owner có toàn quyền”

Chỉ vì người phụ trách được ghi là owner **không có nghĩa họ nên tự cấp cho mình `kms:Decrypt`, `ExportKey` hoặc `DeleteKey`**. Các thay đổi quyền của owner cần review độc lập và audit giống các principal khác. Nguyên tắc là **least privilege + separation of duties**, không phải tin tuyệt đối vào chức danh.

## 9. Ownership đối với DEK, KEK và envelope encryption

Trong **envelope encryption**, **DEK (Data Encryption Key)** dùng mã hóa dữ liệu bằng AES-GCM/ChaCha20-Poly1305; **KEK (Key Encryption Key)** bảo vệ DEK bằng cơ chế wrapping/encryption.

~~~mermaid
flowchart LR
    DataOwner[Data owner: loại dữ liệu, retention, quyền đọc] --> App[Ứng dụng xử lý dữ liệu]
    KeyOwner[Key owner: lifecycle, policy, IAM cho DEK/KEK] --> KMS[KMS/HSM bảo vệ KEK]
    App --> DEK[DEK ngẫu nhiên tạm thời]
    DEK --> AEAD[AEAD mã hóa + nonce + AAD]
    AEAD --> CT[(Ciphertext và tag)]
    DEK --> Wrap[Wrap DEK]
    KMS --> Wrap
    Wrap --> WDEK[(Wrapped DEK + key ID/version)]
    CT --> Storage[(Kho dữ liệu)]
    WDEK --> Storage
    Audit[Audit key usage và approval] --> KeyOwner
    App --> Audit
    KMS --> Audit
~~~

### 9.1. Ai là owner của DEK và KEK?

Không có quy tắc bắt buộc mọi DEK cùng owner với KEK:

- **Key owner của KEK:** có thể là nhóm Platform Security quản lý master wrapping keys trong KMS cho nhiều dịch vụ.
- **Key owner của DEK:** có thể là nhóm phụ trách ứng dụng/miền dữ liệu, chịu trách nhiệm scope, hạn dùng và re-encrypt.
- **Data owner:** xác định quyền truy cập dữ liệu và thời hạn lưu; tham vấn trước khi key bị hủy.

Nếu KEK dùng chung nhiều tenant, **phải biết rõ phạm vi**, quyền của từng tenant và những DEK nào phụ thuộc. Một compromise của KEK có thể ảnh hưởng đến **wrapped DEK đã bị thu thập**, nên **chỉ thay alias hoặc rewrap bản hiện tại không luôn đủ**.

### 9.2. Rotation không xóa trách nhiệm về backup

Owner KEK phải phối hợp với owner DEK và data owner trước khi:

1. Ngừng `Wrap` bằng KEK cũ.
2. Tạo KEK mới và chuyển primary.
3. **Rewrap DEK** nếu chưa có dấu hiệu lộ DEK.
4. Kiểm tra mọi snapshot/backup cũ còn unwrap được.
5. Ngừng quyền unwrap và hủy KEK cũ khi không còn phụ thuộc.

Nếu **DEK bị lộ**, rewrap không đổi nội dung DEK; cần đánh giá **DEK mới và re-encrypt**. Nếu **KEK và wrapped DEK cũ đã bị đối thủ lấy**, rewrap bản hiện tại cũng **không làm đối thủ quên bản copy cũ**. Owner phải phối hợp incident response và data owner đánh giá phạm vi dữ liệu đã có thể mất bí mật.

### 9.3. Nonce/usage limit cũng thuộc phạm vi kiểm soát

Một DEK được tạo rất mạnh vẫn có thể gây hỏng bảo mật nếu AES-GCM dùng lại **cùng cặp (key, nonce)**. Owner cần bảo đảm kiến trúc có **nonce strategy, usage limit và rotation/rekey** phù hợp; app team là người thực thi ở tầng mã hóa.

## 10. Ownership của private signing key, PKI và chữ ký lịch sử

Khóa ký số có các vai trò phân tách:

| Thành phần | Trách nhiệm được giao |
| --- | --- |
| **Signing key owner** | Xác định đối tượng được phép ký, phạm vi, cryptoperiod, HSM policy và rotation |
| **Signer runtime** | Kiểm tra phê duyệt nghiệp vụ rồi yêu cầu HSM `Sign` |
| **Certificate/PKI operator** | Quản lý CSR, chứng thư, trust chain và công bố trạng thái theo quy trình |
| **Public-key registry operator** | Phân phối public key/chứng thư đúng issuer và key version |
| **Verifier owner** | Xác thực trust binding, thuật toán, chữ ký, chứng thư và chính sách chấp nhận |
| **Auditor/IR** | Truy vết thao tác, xử lý ký giả, trạng thái revocation và bằng chứng thời gian |

**Private key ký mới** có thể bị retire khi hết originator-usage period. Nhưng public key/chứng thư có thể cần giữ để **Verify chữ ký lịch sử**. Key owner phải phê duyệt chính sách retention/trust dựa trên:

- Chứng thư và **chuỗi tin cậy** đến trust anchor được phê duyệt.
- **Key usage/EKU** và mục đích ký.
- Thời hạn hiệu lực và **trạng thái thu hồi CRL/OCSP** theo chính sách.
- **Trusted timestamp** hoặc bằng chứng thời gian phù hợp nếu cần chứng minh chữ ký tạo trước khi khóa bị lộ.
- Nghĩa vụ lưu giữ tài liệu và yêu cầu pháp lý áp dụng.

**`Signature.verify() = true` không tự chứng minh giao dịch được ủy quyền hoặc ký trước thời điểm compromise**. Owner chịu trách nhiệm bảo đảm quy trình tin cậy chứ không chỉ lưu một public key.

### 10.1. Khi private key ký bị nghi lộ

Owner phối hợp security/custodian để:

1. **Chặn lệnh `Sign`** trên key cũ và cô lập principal bị nghi chiếm.
2. Phân loại: key material bị xuất, HSM API bị lạm dụng hay trust binding sai?
3. **Thu hồi chứng thư/registry binding** khi phù hợp; xử lý cache của các bên xác minh.
4. Tạo key mới trong approved boundary, phân phối public key/chứng thư qua kênh tin cậy.
5. Rà soát chữ ký trong giai đoạn ảnh hưởng, bằng chứng thời gian và quyền nghiệp vụ.

Không giả định việc **disable KMS key** tự cập nhật mọi JWKS hoặc client PKI; các luồng tin cậy có vòng đời riêng.

## 11. Ownership của PSK, HMAC và shared secret

**PSK (pre-shared key)** và **HMAC key** thường được nhiều bên cùng biết hoặc cùng dùng cho một mục đích xác định. Shared secret trong (EC)DH lại có thể được hai phía tính độc lập và chỉ sống trong một phiên.

Key owner cần ghi rõ:

- **Những bên nào được cấp PSK/HMAC key**, phương thức cấp phát an toàn, bên nhận và trách nhiệm bảo vệ.
- Bí mật có **riêng từng thiết bị, tenant, workload** hay dùng chung trong một miền đã phê duyệt?
- Có định nghĩa **version, cryptoperiod, rotation, revocation và cache/offline handling** không?
- Shared secret có được xử lý qua **HKDF/key schedule** để tách các khóa theo hướng/mục đích không?
- Ai quản lý **trust/authentication** của peer, để tránh DH bị MITM?

Ví dụ: một đội IoT dùng **một PSK chung cho toàn bộ 50.000 thiết bị** sẽ gặp khó khăn khi thiết bị bị mất. Key owner cần đánh giá phạm vi sự cố và cân nhắc **PSK riêng từng thiết bị, chứng thư thiết bị hoặc AKE được đánh giá**, thay vì để một khóa chung vô hạn.

**Không phải mọi ephemeral TLS traffic key cần một người owner riêng**. Thông thường nhóm vận hành hệ thống là owner của **cấu hình TLS, cipher suites, trust anchors, session/ticket key policy và kiểm soát vòng đời phiên**, trong khi thư viện giao thức quản lý traffic secret tạm thời.

## 12. Quy trình owner phê duyệt và thực thi thay đổi khóa

Một quy trình an toàn phải có **bằng chứng trước khi làm**, thao tác được thực thi bởi quyền thích hợp và **kết quả đọc lại sau khi làm**.

~~~mermaid
sequenceDiagram
    participant Requester as Service / Data owner
    participant Owner as Key owner
    participant Security as Security approver
    participant Ops as KMS custodian
    participant Inventory as Inventory + audit
    participant KMS as KMS/HSM
    Requester->>Owner: Yêu cầu tạo/rotate/revoke/destroy
    Owner->>Inventory: Kiểm tra key ID, version, scope, dữ liệu phụ thuộc
    Owner->>Security: Đánh giá rủi ro và phê duyệt theo ngưỡng
    Security-->>Owner: Approval/denial có ticket
    Owner->>Ops: Thực thi thay đổi đã duyệt
    Ops->>KMS: Gọi API theo IAM và operation policy
    KMS-->>Ops: Key reference/state/result
    Ops->>Inventory: Ghi actual state, revision, audit event
    Inventory-->>Owner: Báo cáo kiểm chứng và exception
    Owner-->>Requester: Quyết định và phạm vi hiệu lực
~~~

### 12.1. Tạo khóa mới

Owner xác định purpose, thuật toán/độ mạnh, nguồn entropy, HSM/KMS location, quyền và ngày activation. Custodian tạo theo profile và đăng ký inventory. **Sinh khóa thành công không đồng nghĩa tự động Active**; cần kiểm tra provisioning, approval, key usage và chính sách thời gian.

### 12.2. Rotation

Owner bảo đảm có successor key, cutover plan, consumer readiness, key version trên ciphertext/signature, chính sách xử lý dữ liệu cũ và **rollback không kích hoạt lại khóa compromised**. Rotation không chỉ là đổi alias `current`.

### 12.3. Revocation khẩn cấp

Nếu key bị lộ, **incident commander** có thể được ủy quyền chặn ngay lệnh có rủi ro theo runbook, trong khi key owner phối hợp phạm vi, recovery và truyền thông. Phải xác minh các node/cache/verifier đã ngừng chấp nhận đúng thứ cần chặn; **revocation không làm attacker mất byte secret đã sao chép**.

### 12.4. Destruction / crypto-erasure

Trước khi destroy, owner phải nhận xác nhận của các đội phụ thuộc rằng **ciphertext, wrapped DEK, backup, chữ ký lịch sử và retention** đã được xử lý đúng. Crypto-erasure có thể được dùng có chủ đích để làm mất khả năng giải mã, nhưng chỉ bảo đảm trong điều kiện **không còn bản sao key có thể khôi phục** và mô hình dữ liệu đáp ứng giả định.

## 13. Key inventory và bằng chứng ownership

Key owner không thể quản trị những khóa **không tìm thấy**. **Key inventory** phải chứa các metadata đủ để tìm owner, phạm vi và tác động của một thay đổi, nhưng **không lưu raw key material**.

### Bản ghi minh họa

~~~json
{
  "keyId": "billing-kek",
  "keyVersion": "v4",
  "keyClass": "WRAPPING_KEY",
  "algorithm": "AES-256",
  "ownerTeam": "billing-security",
  "accountableContactRole": "billing-key-owner-oncall",
  "backupOwnerTeam": "platform-security",
  "custodian": "managed-kms-platform",
  "dataOwnerRef": "payments-data-governance",
  "tenantScope": "production/billing",
  "providerKeyRef": "kms://example/billing-kek/v4",
  "allowedOperations": ["WRAP", "UNWRAP"],
  "lifecycleState": "PRE_ACTIVE",
  "primaryForNewUse": false,
  "createdAt": "2026-11-28T08:00:00Z",
  "activationAt": "2026-12-01T00:00:00Z",
  "newUseUntil": "2027-03-01T00:00:00Z",
  "oldUseUntil": "2027-09-01T00:00:00Z",
  "policyRevision": 21,
  "approvalRef": "KEY-ROTATION-204",
  "lastReviewedAt": "2026-11-28T09:00:00Z"
}
~~~

**Bản ghi trên chỉ minh họa schema**; `kms://...` không phải API/URI chuẩn của mọi provider. Vì `activationAt` vẫn nằm trong tương lai tại thời điểm `lastReviewedAt`, khóa được ghi nhận ở **PRE_ACTIVE** và **chưa là primary**. Chỉ chuyển sang ACTIVE và lựa chọn cho thao tác mới khi đến hạn, hoàn tất phê duyệt, IAM và kiểm tra trạng thái thực tế trong KMS/HSM; không tự xem metadata là bằng chứng activation đã thành công.

### Metadata owner cần kiểm tra định kỳ

| Thuộc tính | Câu hỏi kiểm tra |
| --- | --- |
| `ownerTeam` / contact | Team còn tồn tại, có on-call/delegate và nhận cảnh báo không? |
| `keyId/version` | Có đúng version đang dùng ở production và bản ghi backup không? |
| `purpose` / scope | Có được dùng ngoài môi trường/tenant đã duyệt không? |
| `lifecycleState` | Có phù hợp với `activationAt`, thời gian hiện tại và state KMS không? |
| `policyRevision` | Có thay đổi quyền/thuật toán không được duyệt không? |
| `lastUsedAt` | Key đã nghỉ hưu có còn nhận request bất thường không? |
| `dependentAssets` | Có ciphertext, backup, chứng thư hoặc service nào phụ thuộc? |
| `auditRef` | Có truy vết được ai tạo, ai phê duyệt, ai dùng, ai đổi trạng thái? |

**Một inventory không đáng tin vẫn nguy hiểm**: nếu attacker tự sửa owner/team hoặc `revokedAt`, có thể bỏ qua đường phê duyệt. Vì vậy, kiểm soát quyền ghi, versioning, integrity của sự kiện và audit thay đổi metadata là bắt buộc theo mức rủi ro.

## 14. Java 17: policy gate minh họa quyền của key owner

Ví dụ sau **không thao tác với KMS/HSM thật**. Nó mô hình hóa hai ý tưởng:

1. **Ownership không tự cấp quyền sử dụng khóa:** một yêu cầu wrap/unwrap phải có quyền IAM và quyền truy cập resource/tenant hợp lệ.
2. **Rotation cần change approval tách vai:** thông tin key owner và approver độc lập phải được xác thực trong workflow tin cậy, không lấy tùy ý từ request client.

~~~java
import java.time.Instant;
import java.util.Set;

public final class KeyOwnerPolicyDemo {
    enum State { PRE_ACTIVE, ACTIVE, RETIRED, SUSPENDED, REVOKED, DESTROYED }
    enum Operation { WRAP_NEW, UNWRAP_EXISTING }

    record KeyMeta(
            String keyId,
            String keyVersion,
            String ownerTeam,
            String tenantScope,
            State state,
            Instant activationAt,
            Instant newUseUntil,
            Instant oldUseUntil,
            Set<Operation> allowedOperations,
            long policyRevision) {
        KeyMeta {
            if (keyId == null || keyId.isBlank()
                    || keyVersion == null || keyVersion.isBlank()
                    || ownerTeam == null || ownerTeam.isBlank()
                    || tenantScope == null || tenantScope.isBlank()
                    || state == null || activationAt == null
                    || newUseUntil == null || oldUseUntil == null
                    || allowedOperations == null || policyRevision < 1
                    || !activationAt.isBefore(newUseUntil)
                    || newUseUntil.isAfter(oldUseUntil)) {
                throw new IllegalArgumentException("Invalid key inventory");
            }
            allowedOperations = Set.copyOf(allowedOperations);
        }
    }

    record AccessContext(
            String workloadId,
            String tenant,
            boolean iamAllowed,
            boolean resourceAllowed) {}

    // Đọc từ approval registry đã xác thực, không tin payload do client tự ký.
    record ChangeApproval(
            String keyId,
            String ownerTeam,
            String requesterId,
            String securityApproverId,
            String ticketId,
            boolean approved) {}

    static boolean mayUse(
            KeyMeta key, AccessContext actor, Operation op, Instant now) {
        if (key == null || actor == null || op == null || now == null
                || !actor.iamAllowed() || !actor.resourceAllowed()
                || !key.tenantScope().equals(actor.tenant())
                || !key.allowedOperations().contains(op)
                || now.isBefore(key.activationAt())) {
            return false;
        }
        return switch (op) {
            case WRAP_NEW ->
                    key.state() == State.ACTIVE
                    && now.isBefore(key.newUseUntil());
            case UNWRAP_EXISTING ->
                    (key.state() == State.ACTIVE
                            || key.state() == State.RETIRED)
                    && now.isBefore(key.oldUseUntil());
        };
    }

    static boolean mayApproveRotation(
            KeyMeta key, ChangeApproval approval) {
        if (key == null || approval == null
                || !approval.approved()
                || approval.ticketId() == null
                || approval.ticketId().isBlank()
                || approval.requesterId() == null
                || approval.securityApproverId() == null
                || approval.requesterId()
                        .equals(approval.securityApproverId())) {
            return false;
        }
        return key.keyId().equals(approval.keyId())
                && key.ownerTeam().equals(approval.ownerTeam())
                && key.state() != State.REVOKED
                && key.state() != State.DESTROYED;
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-12-01T00:00:00Z");
        Instant endNew = Instant.parse("2027-03-01T00:00:00Z");
        Instant endOld = Instant.parse("2027-09-01T00:00:00Z");

        KeyMeta key = new KeyMeta(
                "billing-kek", "v4", "billing-security",
                "tenant-42", State.ACTIVE, start, endNew, endOld,
                Set.of(Operation.WRAP_NEW, Operation.UNWRAP_EXISTING), 21);

        AccessContext authorized = new AccessContext(
                "billing-service", "tenant-42", true, true);
        AccessContext crossTenant = new AccessContext(
                "billing-service", "tenant-99", true, true);

        Instant duringActive = Instant.parse("2027-01-15T00:00:00Z");
        if (!mayUse(key, authorized, Operation.WRAP_NEW, duringActive)) {
            throw new AssertionError("Expected authorized use");
        }
        if (mayUse(key, crossTenant, Operation.WRAP_NEW, duringActive)) {
            throw new AssertionError("Cross-tenant key use accepted");
        }
        if (mayUse(key, authorized, Operation.WRAP_NEW, endNew)) {
            throw new AssertionError("Cryptoperiod boundary violated");
        }

        ChangeApproval approval = new ChangeApproval(
                "billing-kek", "billing-security",
                "rotation-requester", "security-approver",
                "KEY-ROTATION-204", true);
        if (!mayApproveRotation(key, approval)) {
            throw new AssertionError("Expected approved rotation");
        }
        ChangeApproval selfApproved = new ChangeApproval(
                "billing-kek", "billing-security",
                "same-person", "same-person",
                "KEY-ROTATION-205", true);
        if (mayApproveRotation(key, selfApproved)) {
            throw new AssertionError("Self-approval must be denied");
        }
        System.out.println("Key owner policy checks passed");
    }
}
~~~

### Giải thích giới hạn của ví dụ

- Đây là **mô hình nghiệp vụ/policy**, không tự tạo khóa, không thực hiện AES-GCM và **không gọi KMS**.
- `iamAllowed`, `resourceAllowed`, `ownerTeam` và `approved` **phải được xác định bởi dịch vụ danh tính, policy engine và approval registry đáng tin**, không nhận nguyên giá trị Boolean từ client.
- `mayApproveRotation` mới kiểm tra **một số điều kiện mẫu**. Production còn cần xác thực danh tính người duyệt, quyền ký duyệt, hiệu lực của ticket, quorum/dual control khi cần, trạng thái incident và **audit không thể bị chỉnh sửa tùy ý**.
- `RETIRED` có thể được `UNWRAP_EXISTING` theo chính sách minh họa; **không phải mọi KMS hỗ trợ decrypt-only khi key Disabled**.
- Thực thi quyền **tại chính nơi dùng key** vẫn cần thiết để tránh TOCTOU, stale cache và việc ứng dụng bị vượt qua.
- Với key có thể bị compromised, yêu cầu rotation/revoke được điều phối theo **incident workflow**, không chỉ dựa vào điều kiện trạng thái và thời gian của đoạn code.

**Kết luận kỹ thuật:** key owner cung cấp quyết định trách nhiệm và policy; **KMS/HSM, IAM và ứng dụng phải thực thi** quyết định đó ở nhiều lớp.

## 15. Chuyển giao ownership, offboarding và orphan keys

**Key owner có thể thay đổi; khóa không thể bị bỏ mặc.** Khi reorganize bộ phận, dự án ngừng vận hành hoặc nhân viên nghỉ việc, cần một **handover** có thể kiểm toán.

### 15.1. Quy trình chuyển giao owner

1. **Tìm key inventory** theo owner team, service, tenant, region và vai trò đang rời tổ chức.
2. **Liệt kê phụ thuộc:** ciphertext, wrapped DEK, backup, certificates, JWKS, PSK, partner integrations và jobs.
3. Chọn owner mới có **thẩm quyền và khả năng vận hành**, đồng thời chỉ định backup/contact.
4. Handover **policy, cryptoperiod, key state, rotation calendar, incident runbook, restore procedure và exceptions**.
5. Cập nhật **owner metadata**, approval workflow, on-call và IAM; không tự động cấp raw key chỉ vì owner đổi.
6. Thu hồi credential/quyền của cá nhân cũ; kiểm tra token, HSM roles, KMS grants và tài khoản CI liên quan.
7. Ghi **thời điểm, người phê duyệt và kết quả xác nhận của owner mới**; thực hiện access review sau chuyển giao.

Không đồng nhất việc **chuyển trách nhiệm quản trị** với việc **rotate vật liệu khóa**. Khi chỉ đổi owner, có thể không cần sinh key mới nếu key chưa lộ; nhưng nếu tài khoản cũ từng có raw secret hoặc quyền không còn kiểm soát, phải đánh giá **compromise, revocation và rotation** riêng.

### 15.2. Orphan key là gì?

**Orphan key** là khóa **không còn owner có thể chịu trách nhiệm hợp lệ hoặc không rõ hệ thống nào phụ thuộc**. Đây là rủi ro lớn vì có thể vừa bị bỏ quên không rotate, vừa bị xóa nhầm làm mất dữ liệu.

Runbook nên phân loại orphan key:

| Nhóm | Hướng xử lý |
| --- | --- |
| **Còn active và đang dùng** | Cô lập thông tin owner thiếu, tìm dịch vụ phụ thuộc, gán owner mới sau review |
| **Có ciphertext/backup phụ thuộc** | Không destroy ngay; xác minh recovery, rewrap/re-encrypt và retention |
| **Không dùng nhưng còn quyền rộng** | Giảm quyền, theo dõi và áp quy trình retirement |
| **Không xác định nguồn sinh/trust** | Đánh giá rủi ro, có thể tạm chặn, tạo key thay thế và kiểm tra dữ liệu |
| **Nghi compromise** | Incident response, revoke theo phạm vi và đánh giá tác động, không chỉ đổi owner |

## 16. Audit, access review và chỉ số trách nhiệm

Key owner cần được **đo bằng bằng chứng**, không phải chỉ bằng trạng thái “Owner assigned” trên dashboard.

### 16.1. Sự kiện audit nên liên kết được

| Sự kiện | Metadata quan trọng |
| --- | --- |
| **Key created/provisioned** | Key ID/version, requester, owner, custodian, policy revision, provider ref |
| **Access granted/revoked** | Principal, operation, scope, approver, thời điểm hiệu lực |
| **Key activated/rotated** | Version cũ/mới, primary, cryptoperiod, change ticket và trạng thái consumer |
| **Sensitive operation** | `Sign`, `Unwrap`, `Decrypt` theo principal, key version, verdict, request ID |
| **Compromise/revocation** | Incident ID, lý do, hành động containment, propagation và outstanding risks |
| **Key destroyed** | Approval, xác nhận phụ thuộc/backup, evidence từ provider, retention result |
| **Owner transferred** | Owner cũ/mới, người phê duyệt, IAM handover, ngày có hiệu lực |

**Không log** private key, raw DEK/KEK, PSK, password, token bearer, plaintext hoặc toàn bộ nội dung giao dịch nhạy cảm chỉ để chứng minh một thao tác. Audit được phân quyền, bảo đảm integrity và giữ theo retention.

### 16.2. Chỉ số và cảnh báo nên có

- Số key version **chưa có owner hoặc backup contact hợp lệ**.
- Key **quá cryptoperiod** nhưng vẫn nhận `Encrypt/Wrap/Sign` mới.
- Khóa **retired** vẫn được yêu cầu `Sign` hoặc `Wrap` mới.
- Quyền `Decrypt/Unwrap/Sign` **quá rộng** hoặc không được review đúng chu kỳ.
- Số workload/tenant cùng phụ thuộc **một KEK/PSK** vượt giới hạn thiết kế.
- Key sắp **destroy** trong khi backup còn chứa wrapped DEK hoặc chữ ký cần chứng cứ.
- Tỷ lệ rotation hoàn tất, lỗi rewrap/restore, orphan keys và exception còn mở.
- Độ trễ từ **revoke** tới khi các consumer nhận state mới và thử nghiệm từ chối đạt yêu cầu.

Không đánh giá owner chỉ bằng số lượng khóa đã tạo hoặc số lần rotation; **khả năng khôi phục dữ liệu và chất lượng quyền/trust** cũng quan trọng.

## 17. Tình huống thực tế: phân vai cho nền tảng thương mại đa tenant

Một nền tảng thương mại cần bảo vệ thông tin thanh toán, lưu hóa đơn có chữ ký số và cung cấp kết nối API cho nhiều đối tác.

### Các khóa liên quan

1. **KEK `billing-kek`** trong KMS/HSM, bọc DEK bảo vệ dữ liệu thanh toán.
2. **DEK** phục vụ mã hóa bản ghi bằng AES-GCM với nonce/AAD phù hợp.
3. **Private signing key `invoice-signing`** để ký hóa đơn; public key/chứng thư được cung cấp cho đối tác xác minh.
4. **HMAC/PSK riêng** cho các tích hợp cần symmetric authentication theo giao thức được phê duyệt.

### Phân vai đề xuất

| Phạm vi | Key owner | Custodian/Operator | Workload dùng | Đơn vị cần tham vấn |
| --- | --- | --- | --- | --- |
| `billing-kek` | Billing Security | Platform KMS | Billing API | Data governance, Security |
| DEK mã hóa bản ghi | Billing/Data Platform | Encryption service/KMS adapter | Data service có quyền resource | Tenant data owner |
| `invoice-signing` | Invoice Governance | HSM operations | Signing service | PKI, Legal/Compliance, Security |
| PSK đối tác | Integration Security | Secret manager operator | Gateway đúng partner | Partner owner, Incident Response |

Tên đội trong bảng chỉ là **ví dụ tổ chức**. Điều quan trọng là **không để một key dùng chung không ai chịu trách nhiệm**, và tránh một vai trò có thể vừa duyệt, vừa thực thi, vừa xóa audit mà không có kiểm soát.

### Giai đoạn 1 — Tạo và cấp phát

Billing Security duyệt profile AES-256/KEK, nguồn entropy/KMS và cryptoperiod. Platform KMS tạo KEK, ghi key reference vào inventory. Data service dùng DEK được cấp theo kiến trúc, **không bao giờ lấy raw KEK từ KMS** nếu policy cấm export. Invoice Governance duyệt private key ký không xuất được; HSM operator sinh khóa và PKI operator xử lý chứng thư.

### Giai đoạn 2 — Sử dụng

Billing API kiểm tra **người dùng/tenant có quyền truy cập bản ghi**, rồi mới gọi `Unwrap` khi cần. Signing service kiểm tra **hóa đơn đã được duyệt**, rồi mới gọi `Sign`. Verifier dùng public key đã xác thực, **không cần quyền `Sign`**. Owner theo dõi key usage và IAM, không yêu cầu truy cập mọi plaintext.

### Giai đoạn 3 — Rotation bình thường

KEK mới được tạo và kích hoạt theo lịch; dữ liệu mới được wrap bằng key version mới, bản ghi cũ tiếp tục unwrap theo policy hoặc rewrap. Owner kiểm tra **backup, tenant dependencies và error rates** trước khi cho destroy KEK cũ. Private signing key mới được công bố trước qua PKI/JWKS/registry tin cậy khi cần; chữ ký cũ được xác minh theo chính sách lịch sử.

### Giai đoạn 4 — Sự cố

Một service account có quyền `Unwrap` bị chiếm. Incident commander phối hợp **thu hồi credential/IAM và đóng session** ngay; custodian kiểm tra KMS/HSM logs. Key owner xác định liệu **chỉ bị lạm dụng API** hay **key material/DEK/ciphertext đã bị lấy**. Nếu DEK bị lộ, có thể phải **tạo DEK mới và re-encrypt**; nếu chỉ đổi KEK mà bỏ qua DEK đã lộ, rủi ro vẫn tồn tại.

**Kết luận tình huống:** phân vai rõ giúp nhóm Security có quyền ứng phó khẩn cấp, nhóm Platform vận hành khóa, nhóm ứng dụng bảo vệ dữ liệu đúng tenant và **key owner chịu trách nhiệm cuối cùng về điều kiện an toàn và phục hồi**.

## 18. Sai lầm thường gặp khi giao vai trò key owner

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Không gắn owner cho key | Không ai phụ trách rotation, backup hoặc sự cố | Bắt buộc owner/contact khi đăng ký key |
| Gắn owner vào một nhân viên duy nhất | Orphan key khi nhân viên rời tổ chức | Owner team + contact + backup/handover |
| Coi owner phải giữ raw private key | Tăng rủi ro lộ secret | Owner quản trị policy; custodian/KMS/HSM giữ material |
| Cấp owner quyền `Decrypt/Sign/Delete` toàn hệ thống | Lạm dụng quyền, khó phân tách nhiệm vụ | Least privilege, dual control khi cần |
| Nhầm owner dữ liệu với owner khóa | Không rõ trách nhiệm retention vs rotation | Phân biệt data governance với crypto lifecycle |
| RACI chỉ có trên giấy, IAM không theo | Bypass approval và policy | Ánh xạ sang workflow/IAM, test quyền thực tế |
| Sinh key từ `Math.random()` nhưng owner chỉ xem key size | Khóa dễ đoán | Approved CSPRNG/generation policy và evidence |
| Đổi alias rồi coi đã rotation vật liệu | Khóa cũ vẫn có thể bị lộ | Tạo material mới, versioning và cập nhật consumer |
| Destroy key trước khi hỏi app/data owner | Mất ciphertext và backup | Dependency inventory, rewrap và restore test |
| Owner tự phê duyệt mọi thao tác nhạy cảm | Thiếu kiểm soát độc lập | Two-person approval/separation of duties |
| HSM key non-exportable nên bỏ authorization `Sign` | Attacker dùng API ký giả | Kiểm tra chính sách nghiệp vụ trước Sign |
| Bỏ qua public key verification sau khi retire signer | Mất kiểm chứng chữ ký lịch sử | Retention public key/chứng thư và evidence |
| Rewrap KEK khi DEK đã lộ, rồi tuyên bố an toàn | Attacker vẫn giải mã ciphertext cũ | Đánh giá thay DEK, re-encrypt và bản sao đã bị lấy |
| Revoke chỉ trong registry, bỏ cache verifier | Client vẫn tin key cũ | Propagation/negative tests ở mọi điểm chấp nhận |
| Owner chuyển team nhưng IAM cũ còn hiệu lực | Quyền dư thừa sau offboarding | Access review, credential revoke và handover audit |
| Chỉ log alias thay vì key ID/version thực tế | Không truy vết được version đang dùng | Audit actual key reference, principal, policyRevision |

## 19. Checklist dành cho key owner

- [ ] Mỗi key ID/version có **owner team, accountable contact và backup** còn hoạt động?
- [ ] Đã xác định đúng **data owner, custodian, operator, key user, security approver và auditor**?
- [ ] Có RACI cho generation, activation, usage, rotation, revoke, restore và destroy?
- [ ] Quyền IAM/KMS/HSM phản ánh **least privilege** và separation of duties thay vì danh xưng owner?
- [ ] Algorithm, key size/curve, CSPRNG/provider, generation boundary được phê duyệt?
- [ ] Private signing key/KEK cần non-extractable đã được tạo và bảo vệ ở approved HSM/KMS?
- [ ] Đã tách **DEK, KEK, HMAC/PSK, private signing key, public verification key và session keys** theo purpose?
- [ ] Inventory lưu key ID/version, owner, purpose, provider ref, state, `activationAt`, cryptoperiod và policy revision?
- [ ] Quyền sử dụng khóa được kiểm tra **ở KMS/HSM** và quyền dữ liệu **ở tầng ứng dụng**?
- [ ] Có chính sách **nonce uniqueness** và giới hạn số lần/khối lượng mã hóa với AEAD?
- [ ] Rotation có successor key, key version metadata, canary, rewrap/re-encrypt và kiểm thử backup?
- [ ] Với chữ ký số, public key/trust binding, chứng thư, revocation và bằng chứng thời gian lịch sử đã có owner?
- [ ] Với PSK/HMAC, phạm vi từng thiết bị/tenant và cách cấp phát/thu hồi đã được ghi rõ?
- [ ] Sự cố nghi compromise có quyền **containment khẩn cấp**, điều tra và kiểm tra consumer cache?
- [ ] Trước destroy có xác nhận của app/data owner về ciphertext, wrapped DEK, backup và retention?
- [ ] Tất cả change approval, state change, key usage và exception có audit **không lộ secret**?
- [ ] Có kế hoạch owner transfer/offboarding và phát hiện orphan keys định kỳ?
- [ ] Đã test các trường hợp thiếu quyền, sai tenant, sai purpose, key expired/revoked và self-approval?

## 20. Câu hỏi tự kiểm tra

**1. Key owner có phải là người giữ private key không?**  
Không. Key owner chịu trách nhiệm về policy, mục đích, vòng đời, quyền và rủi ro. Key material có thể do KMS/HSM hoặc custodian quản lý; owner không mặc nhiên được xuất private key.

**2. Key owner khác data owner ở đâu?**  
Key owner quản trị vòng đời và chính sách của khóa, còn data owner xác định quyền truy cập và retention của dữ liệu được bảo vệ. Hai vai trò phải phối hợp nhưng không thay thế lẫn nhau.

**3. Vì sao trong RACI không nên vừa phê duyệt vừa thực hiện thao tác xóa root key mà không có kiểm soát?**  
Vì dễ xảy ra sai sót, lạm dụng hoặc che giấu hành vi. Tùy mức rủi ro cần separation of duties, dual approval và audit độc lập.

**4. Ai chịu trách nhiệm nếu KEK mới đã Active nhưng backup cũ không unwrap được?**  
Key owner chịu trách nhiệm giải trình về quy trình, còn custodian/app team chịu trách nhiệm thực hiện và kiểm thử theo RACI. Phải kiểm tra phụ thuộc/restore trước khi loại bỏ KEK cũ.

**5. Key owner của private signing key cần quan tâm gì khi rotation?**  
Nguồn sinh và ranh giới HSM, quyền `Sign`, cryptoperiod, công bố public key/chứng thư, trust và khả năng kiểm tra chữ ký lịch sử.

**6. Một KEK không xuất được từ HSM có chắc chắn không bị lạm dụng không?**  
Không. Attacker có thể chiếm principal có quyền API `Decrypt/Unwrap`; phải bảo vệ IAM và authorization nghiệp vụ.

**7. Khi nhân viên được ghi là owner nghỉ việc, có cần luôn thay toàn bộ key material không?**  
Không mặc nhiên. Cần handover ownership, thu hồi quyền cũ và đánh giá liệu raw key hoặc credential đã lộ; chỉ rotate/revoke theo rủi ro và policy.

**8. Vì sao chỉ rewrap DEK đôi khi không đủ sau sự cố?**  
Nếu DEK đã bị lộ, hoặc attacker giữ KEK cũ cùng wrapped DEK cũ, họ vẫn có thể giải mã dữ liệu đã thu thập. Cần đánh giá thay DEK và re-encrypt.

**9. Ownership trong inventory có đủ để ngăn service truy cập sai tenant không?**  
Không. Phải kiểm soát tenant/resource authorization tại ứng dụng và IAM/operation policy tại KMS/HSM, tránh stale cache và TOCTOU.

**10. Khi key bị compromise, có nên chờ owner phê duyệt đầy đủ trước khi chặn attacker?**  
Không nên nếu rủi ro đang diễn ra. Quy trình phải có quyền containment khẩn cấp được ủy quyền cho incident commander/security, sau đó ghi nhận, phối hợp owner và hậu kiểm.

## Ghi nhớ

**Key owner là vai trò chịu trách nhiệm cuối cùng về mục đích, chính sách, quyền sử dụng, rủi ro và vòng đời của một khóa mật mã; không đồng nghĩa là người nắm raw key hoặc có mọi quyền trên KMS/HSM.** Quản trị tốt cần **RACI rõ ràng, separation of duties, inventory có owner và key version, least privilege, audit, approval và quy trình handover**. Key owner kết nối từ **sinh khóa bằng CSPRNG, cấp phát, activation, cryptoperiod, sử dụng, rotation, revocation đến destruction**, phối hợp với data owner, custodian, ứng dụng và security. Với **DEK/KEK và envelope encryption, chữ ký số/PKI, PSK/HMAC, session keys và KMS/HSM**, trách nhiệm được phân tách nhưng không được bỏ trống: **khóa mạnh chỉ mang lại bảo vệ bền vững khi luôn có người chịu trách nhiệm quản trị đúng cách**.

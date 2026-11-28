# Quorum approval

> **Chương:** Vai trò và trách nhiệm  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Quorum approval là gì?

**Quorum approval (phê duyệt theo số lượng tối thiểu những người có thẩm quyền)** là cơ chế yêu cầu một **tập hợp đủ lớn và đúng điều kiện các bên phê duyệt độc lập** đồng ý trước khi hệ thống cho thực hiện một thay đổi hoặc thao tác mật mã nhạy cảm. Quy tắc thường được diễn tả bằng **M-of-N**: ít nhất **M** trong **N** người/đơn vị đủ tư cách phải phê duyệt, kèm những điều kiện bổ sung về vai trò, phạm vi, thời hạn và tính độc lập.

Ví dụ: tổ chức có ba người được ủy quyền xem xét xóa **root KEK** (Key Encryption Key); chính sách yêu cầu **2-of-3**, trong đó **ít nhất một người thuộc Security**. Một yêu cầu có hai chữ ký của cùng một người không đạt quorum; hai người hợp lệ nhưng đều ở nhóm vận hành cũng không đạt nếu thiếu vai trò Security bắt buộc. Ngay cả khi hai người đã phê duyệt, hành động **chưa chắc được phép** nếu key/version, dữ liệu phụ thuộc, thời hạn hoặc chính sách KMS/HSM không còn hợp lệ.

Mục tiêu là giảm nguy cơ **một người hoặc một tài khoản đơn lẻ** tự ý tạo root key, đổi policy, xuất/xóa key, kích hoạt lại khóa nguy hiểm hoặc thực hiện quyết định có thể làm mất dữ liệu. Quorum approval là **kiểm soát về thẩm quyền và quy trình**; nó không tự làm khóa mạnh hơn về mặt toán học và không thể bảo vệ nếu đường thực thi có thể **bỏ qua toàn bộ cơ chế phê duyệt**.

### Ví dụ thực tế

Ứng dụng thanh toán lưu dữ liệu bằng DEK (Data Encryption Key), các DEK được bọc bởi KEK trong KMS. Khi có kế hoạch **hủy KEK phiên bản cũ**, Key owner yêu cầu xác nhận rằng mọi wrapped DEK và backup còn phụ thuộc đã được xử lý. Security kiểm tra nguy cơ; custodian xác nhận trạng thái KMS/HSM. Chỉ khi đạt quorum và preflight, hệ thống mới cho phép thực hiện lệnh theo kế hoạch.

**Không phải thao tác mật mã nào cũng cần con người phê duyệt.** Việc mỗi request API đều phải có hai người nhấn nút `Decrypt` là không thực tế trong nhiều hệ thống. Quorum thường dành cho **thao tác quản trị rủi ro cao**; các thao tác runtime hợp lệ được kiểm soát bởi IAM, ứng dụng và policy đã phê duyệt.

### Mục tiêu học tập

- Hiểu **M-of-N**, điều kiện về vai trò, danh tính và tính độc lập của bên duyệt.
- Phân biệt **quorum approval**, **dual control**, **multi-factor authentication**, **split knowledge**, **Shamir secret sharing**, **threshold cryptography** và **distributed consensus quorum**.
- Thiết kế phê duyệt cho **generation, import/export, activation, rotation, revocation, destruction và thay đổi IAM/KMS/HSM policy**.
- Phân vai **key owner, security approver, custodian, data owner, executor và auditor**.
- Thực thi **request binding, approval expiry, replay protection, policy versioning, audit** và chống bypass.
- Áp dụng ví dụ **Java 17** và nhận diện giới hạn của kiểm tra quorum trong ứng dụng.

## 2. Hiểu M-of-N: không chỉ đếm số lần bấm “Approve”

Giả sử nhóm phê duyệt được phép gồm **N = 5** người. Chính sách **3-of-5** yêu cầu ít nhất ba **danh tính phân biệt, hợp lệ**, nhưng một cấu hình an toàn còn phải trả lời:

1. Năm người có **đang được ủy quyền** cho key và action này không?
2. Ba người có đại diện **đúng vai trò bắt buộc** không?
3. Từng người có được xác thực mạnh và **tự mình đưa ra quyết định** không?
4. Ba quyết định có phê duyệt **chính xác cùng một request/version/parameters** không?
5. Chúng còn hiệu lực tại **thời điểm thực thi** không?
6. Người yêu cầu hay người thực thi có được tính là approver không?
7. Có đường gọi API trực tiếp khiến hành động vẫn diễn ra dù quorum thất bại không?

| Ví dụ policy | Ý nghĩa | Cần kiểm tra thêm |
| --- | --- | --- |
| **2-of-3** | Ít nhất hai trong ba bên đủ tư cách | Các danh tính độc lập, cùng request và chưa hết hạn |
| **3-of-5** | Ít nhất ba trong năm bên đủ tư cách | Danh sách eligible approvers và revocation của từng người |
| **2-of-3 + Security bắt buộc** | Đạt số lượng và có ít nhất một Security approver | Người thuộc Security không phải cùng người phê duyệt hai lần |
| **Key owner + Security approver** | Hai vai trò được yêu cầu cùng đồng ý | Hai người khác nhau, không chỉ hai nhóm IAM của cùng account |
| **2-of-3 custodian + 1 data owner** | Hai người giữ khóa và một người chịu trách nhiệm dữ liệu | Cách định nghĩa số người/nhóm và phạm vi phụ thuộc phải rõ |

**Quorum count** khác **role constraints**. Một policy có thể vừa yêu cầu số lượng tối thiểu, vừa yêu cầu một hoặc nhiều vai trò cụ thể, lại cấm một số cặp xung đột lợi ích.

### 2.1. Một người có nhiều tài khoản vẫn là một người

Nếu một kỹ sư sở hữu hai service accounts và tạo hai approval bằng hai tài khoản, đó **không phải hai phê duyệt độc lập**. Cần gắn quyết định với **danh tính người thực (hoặc danh tính tổ chức được ủy quyền)** đã được xác minh; xác thực mạnh bằng MFA/passkey, kiểm tra group membership và cơ chế anti-impersonation. Hai lần MFA của cùng một người cũng **không bằng hai người duyệt**.

### 2.2. Không biến quorum thành bầu chọn thiếu ngữ cảnh

Quyết định quorum không phải “đa số trong kênh chat đã đồng ý” nếu một số người không được phép duyệt. Một approval phải gắn với **một key ID/version, action, phạm vi tài nguyên/tenant, tham số, policy revision và thời hạn**. Việc sửa request sau khi được duyệt phải khiến các approval cũ **không còn khớp**.

### 2.3. Quorum tăng chi phí lạm dụng nhưng không loại bỏ thông đồng

Hai người độc lập vẫn có thể bị chiếm tài khoản hoặc thông đồng. Quorum **giảm single-person failure**, không đảm bảo phòng chống một nhóm thông đồng đủ lớn. Với root keys cực kỳ nhạy cảm, cần kết hợp **role diversity, hardware-backed authentication, audit độc lập, key ceremony, giới hạn thời gian và kiểm soát đường thực thi**.

## 3. Quorum approval khác các cơ chế gần giống

Các thuật ngữ “multi-party”, “two-person rule” và “M-of-N” có thể xuất hiện trong cả **governance** và **mật mã**, nhưng không được đánh đồng.

| Cơ chế | Điều được bảo đảm khi cấu hình đúng | Điều không tự bảo đảm |
| --- | --- | --- |
| **Quorum approval (workflow)** | Đủ quyết định được ủy quyền trước thao tác | Byte khóa được chia thành nhiều phần; KMS chắc chắn chặn đường bypass |
| **Dual control / two-person rule** | Một thao tác cần ít nhất hai chủ thể độc lập tham gia | Luôn có chính sách M-of-N linh hoạt hoặc bảo vệ vật liệu bằng threshold cryptography |
| **Separation of duties** | Phân tách người yêu cầu, phê duyệt, vận hành, kiểm toán | Một lệnh đã đạt quorum nếu thiếu kiểm tra request |
| **Multi-factor authentication (MFA)** | Một danh tính chứng minh nhiều yếu tố xác thực | Có **nhiều người** duyệt |
| **Split knowledge** | Không một bên riêng lẻ biết đầy đủ bí mật theo phương pháp chia tách đã thiết kế | Có approval workflow gắn với key use và cryptoperiod |
| **Shamir secret sharing (k-of-n)** | Có thể khôi phục secret từ k share hợp lệ theo sơ đồ | Các bên cùng chấp thuận một lệnh; ngăn key tái lập rồi bị xuất |
| **Threshold signature / threshold cryptography** | Nhiều bên phối hợp thực hiện phép toán mà trong thiết kế phù hợp không cần tái tạo raw private key ở một nơi | Tự xác thực mục đích kinh doanh, tenant hoặc người đề nghị |
| **Distributed consensus quorum** | Đủ node tham gia quyết định/đồng thuận theo giao thức phân tán | Đủ người có thẩm quyền đồng ý xóa khóa |

### 3.1. Ví dụ làm rõ

Một HSM có **private key không xuất được**. Security thiết lập quy trình phải có **2-of-3 approvers** trước khi gọi `ScheduleDeletion`; đây là **quorum approval**. Private key vẫn nằm nguyên trong HSM, không bị tách thành hai mảnh.

Một hệ thống khác chia một **recovery secret** thành năm share và yêu cầu ba share để tái tạo nó. Đó là **3-of-5 secret sharing**. Có đủ share **không đồng nghĩa** chủ thể được phép dùng secret để ký hoặc giải mã, trừ khi hệ thống còn xác thực request/policy.

Một cơ chế **threshold signing** có thể yêu cầu hai thành viên cùng tạo chữ ký mà không tái tạo private key bên ngoài các thành phần được kiểm soát. Đây là một tính chất **mật mã** bổ sung; vẫn cần authorization trước khi ký.

**Kết luận:** khi nói “quorum 3-of-5”, luôn hỏi **ba người phê duyệt, ba share khôi phục hay ba thành viên tham gia tính toán mật mã?**

## 4. Vai trò và trách nhiệm trong phê duyệt khóa

**Key owner** chịu trách nhiệm về mục đích, policy, cryptoperiod và tác động của thao tác; **custodian** vận hành hạ tầng bảo vệ key; **security approver** kiểm tra rủi ro và tính phù hợp; **data owner** xác nhận ảnh hưởng tới dữ liệu; **auditor** kiểm tra bằng chứng.

| Vai trò | Trách nhiệm khi có yêu cầu rủi ro cao | Quyền không mặc nhiên có |
| --- | --- | --- |
| **Requester / initiator** | Lập yêu cầu, mô tả lý do, key ID/version, tác động và rollback | Tự phê duyệt yêu cầu của mình |
| **Key owner** | Bảo đảm mục đích, dữ liệu phụ thuộc, cryptoperiod và phạm vi thay đổi | Có mọi `Sign`, `Decrypt`, `ExportKey`, `DeleteKey` |
| **Security approver** | Đánh giá sự cố, baseline, policy và tác động bảo mật | Tự thực thi lệnh ngoài đường đã kiểm soát |
| **Data owner** | Xác nhận retention, backup, rủi ro mất dữ liệu/khả năng phục hồi | Cấp quyền dùng private key ký hoặc root KEK |
| **Key custodian / KMS operator** | Chuẩn bị, thực hiện API đúng policy, xác minh state | Tự duyệt xóa khóa mà mình đang vận hành |
| **Approval service** | Xác minh danh tính, eligibility, request binding, quorum/expiry | Lưu raw private key hay quyết định nghiệp vụ thay owner |
| **Execution broker** | Gọi API KMS/HSM sau khi có authorization hợp lệ | Bỏ qua policy bằng tài khoản đặc quyền không kiểm soát |
| **Auditor / monitoring** | Kiểm tra provenance, tính toàn vẹn và kết quả thực thi | Sửa/xóa audit hoặc tự bật lại key bị revoke |
| **Incident commander** | Kích hoạt lệnh containment khẩn cấp theo ủy quyền | Tự ý hủy khóa trước khi đánh giá recovery nếu không được phép |

**RACI** giúp làm rõ: **R** trực tiếp làm, **A** chịu trách nhiệm cuối cùng, **C** cần tham vấn, **I** nhận thông tin. Quorum xác định **những người phê duyệt được tính**; hai khái niệm liên quan nhưng không giống nhau.

### RACI tham khảo

| Hành động | Key owner | Security | Custodian | Data owner | Auditor |
| --- | --- | --- | --- | --- | --- |
| Phê duyệt profile sinh root KEK | **A** | C / approver độc lập | R | C | I |
| Tạo private signing key trong HSM | **A** | Approver độc lập khi policy yêu cầu | **R** | C | I |
| Chuyển primary KEK theo lịch | **A** | C / approver theo risk tier | **R** | C | I |
| Thu hồi `Sign` khi compromise khẩn cấp | C | **A** | **R** | I | I |
| Hủy KEK sau khi xác nhận không còn backup phụ thuộc | **A** | Approver độc lập | **R** | **C / xác nhận** | I |
| Kiểm toán các quyết định và ngoại lệ | C | C | C | I | **R** |

**Không cấp IAM trực tiếp từ cột A/R.** Bảng RACI nói ai có trách nhiệm, còn quyền API phải được cấu hình riêng và thử nghiệm, đặc biệt với lệnh destructive.

## 5. Những thao tác cần quorum và thao tác không nên bị chặn vô lý

**Risk-based policy** quyết định action nào cần một, hai, ba hay nhiều bên phê duyệt. Các ngưỡng sau **chỉ là ví dụ thiết kế**, không phải quy tắc bắt buộc của một tiêu chuẩn hay nhà cung cấp cloud.

| Hoạt động | Gợi ý quản trị | Giải thích |
| --- | --- | --- |
| Tạo **root KEK / root signing key** | Quorum gồm owner + Security hoặc ceremony M-of-N | Key ảnh hưởng diện rộng và có thể sống lâu |
| **Import/BYOK** private key nhạy cảm | Quorum, kiểm soát nguồn sinh và import | Key có thể đã ở ngoài boundary; cần traceability |
| Thay IAM/key policy làm tăng quyền `Decrypt/Sign/Export` | Quorum độc lập | Thay đổi quyền có thể vô hiệu hóa mọi lớp kiểm soát khác |
| Xuất hoặc backup raw key khi policy cho phép | Quorum nghiêm ngặt, kênh được kiểm soát | Rủi ro vật liệu khóa bị sao chép |
| Chuyển **primary KEK** theo rotation đã kiểm thử | Approval theo risk tier, có thể tự động theo policy đã duyệt | Không nên tạo downtime vì chờ người bấm mỗi lần |
| Hủy key version còn dữ liệu phụ thuộc | Quorum + xác nhận backup/restore | Có thể gây mất dữ liệu không thể đảo ngược |
| Thu hồi quyền của principal đang bị chiếm | **Containment khẩn cấp theo runbook** | Không chờ quorum nếu thời gian chờ giúp attacker tiếp tục gây hại |
| Tạo **ephemeral TLS session key** | Tự động qua giao thức chuẩn | Không cần người duyệt từng phiên |
| Mã hóa/giải mã dữ liệu hợp lệ theo request API | IAM, tenant authorization và key usage policy | Quorum từng request thường không phù hợp; ngoại lệ với giao dịch cực kỳ nhạy cảm |
| Đánh giá bản sao lưu và crypto-erasure | Quorum cho bước destroy, data-owner sign-off | Phân biệt revoke và hủy không thể khôi phục |

### Bảo vệ hành động thay đổi chính policy quorum

Nếu bất kỳ một admin nào có thể giảm threshold từ **3-of-5 xuống 1-of-1**, mọi quorum trước đó trở nên hình thức. Vì vậy, **thay đổi danh sách approver, threshold, role constraints, key policy, root trust và quyền execution broker** phải được bảo vệ bằng quy trình **không yếu hơn yêu cầu mà nó thay đổi**, hoặc bằng hệ thống kiểm soát mạnh độc lập.

Một mô hình hiệu quả là **policy được version hóa, thay đổi có hai-person review, kiểm tra độc lập trước deploy, immutable audit và kiểm tra thực quyền KMS/HSM**.

## 6. Phê duyệt chính xác **cái gì**? Request binding

Quorum chỉ có ý nghĩa khi tất cả approval tham chiếu **cùng một thay đổi bất biến về mặt ý nghĩa**. Một request nên có các trường:

| Trường | Mục đích |
| --- | --- |
| `requestId` | Định danh duy nhất, hỗ trợ idempotency |
| `keyId` và **`keyVersion`** | Chỉ đúng vật liệu khóa; không dựa duy nhất vào alias `current` |
| `action` | `CREATE_ROOT`, `ROTATE_KEK`, `EXPORT`, `SCHEDULE_DESTROY`... |
| `tenant/environment/region` | Giới hạn phạm vi đối tượng và workload |
| `requestedBy`, `executor` | Kiểm tra tách vai với approvers |
| `parameters` | Thuật toán, scope, thời gian delete, policy delta, approval dependencies |
| `policyId` / `policyRevision` | Phê duyệt dưới đúng phiên bản quy tắc |
| `createdAt`, `expiresAt` | Không cho approval tồn tại vô hạn |
| `intentDigest` | Fingerprint của biểu diễn request **chuẩn hóa, không mơ hồ** |
| `evidenceRefs` | Kết quả preflight, backup dependency, impact assessment |

**Thay một byte có ý nghĩa của request cần yêu cầu phê duyệt lại.** Ví dụ, phê duyệt **hủy `kek-v4` sau 30 ngày** không cho phép executor đổi tham số thành **hủy ngay `kek-v3`** hoặc mở rộng phạm vi sang mọi tenant.

### 6.1. Digest ràng buộc, không phải chữ ký tự động

Có thể tính **SHA-256 digest** trên biểu diễn request đã canonicalize, có **độ dài trường rõ ràng** và policy revision. Digest giúp phát hiện request đổi nội dung khi đối chiếu approval, nhưng **digest công khai tự nó không xác thực ai đã duyệt**. Approval phải được bảo vệ bởi **identity service, chữ ký/MAC, session bảo mật hoặc kho trạng thái tin cậy** theo kiến trúc.

Không tự nối chuỗi theo kiểu `keyId + action + parameters` nếu giá trị có thể tạo nhập nhằng. Dùng **serialization có tính xác định** và xác minh tất cả trường ảnh hưởng đến quyết định.

### 6.2. Approval có thời hạn và dễ bị stale

Mỗi approval nên có:

- Danh tính và vai trò được **xác thực tại thời điểm duyệt** và kiểm tra lại điều kiện tư cách khi execute theo policy.
- Request ID và **intent digest** giống bản được lưu.
- Thời gian phát hành, **thời hạn hiệu lực**, trạng thái hủy approval nếu người duyệt rút lại.
- Tình trạng **policy version** và state của khóa tại thời điểm execute.

Nếu key đã bị revoke, policy đã thay, owner đã rời tổ chức hoặc dữ liệu phụ thuộc thay đổi quan trọng, đừng lấy một approval cũ để hợp thức hóa thao tác mới.

## 7. Kiến trúc thực thi: approval service phải chặn được hành động thật

Một kiến trúc phổ biến dùng **approval workflow** để ra quyết định và **execution broker** để gọi KMS/HSM bằng quyền giới hạn.

~~~mermaid
sequenceDiagram
    participant Req as Requester
    participant WF as Approval service
    participant IAM as Identity / policy source
    participant Owner as Key owner approver
    participant Sec as Security approver
    participant Exec as Execution broker
    participant KMS as KMS / HSM
    participant Audit as Audit log
    Req->>WF: Tạo request với key/version/action/parameters
    WF->>IAM: Xác minh requester và policy hiện hành
    IAM-->>WF: Policy revision + approver eligibility
    WF->>Owner: Gửi immutable request digest để review
    Owner->>WF: Approval đã xác thực
    WF->>Sec: Gửi cùng request digest để review
    Sec->>WF: Approval đã xác thực
    WF->>WF: Kiểm tra quorum, distinct identity, role, expiry
    WF->>Exec: Permit token ngắn hạn, single-use, scoped
    Exec->>IAM: Revalidate policy/quyền và key state
    IAM-->>Exec: Permit/deny mới nhất
    Exec->>KMS: Thực thi đúng action + key version đã duyệt
    KMS-->>Exec: Result / actual state
    Exec->>Audit: Ghi execution result, request ID, key/version
    Exec-->>WF: Receipt + reconciliation status
~~~

**Sơ đồ là mô hình logic**, không phải API chung của mọi KMS. “Permit token” phải có cơ chế **chống giả mạo, thời hạn ngắn, single-use và ràng buộc action/key/version**; nếu chỉ là Boolean `approved=true` do client gửi, nó có thể bị giả.

### 7.1. Không có đường bypass trực tiếp

Nếu workload có thể trực tiếp gọi `DeleteKey` bằng quyền IAM của chính nó, quorum ở giao diện web **không bảo vệ được gì**. Những operation nhạy cảm phải được hạn chế để **chỉ broker/cơ chế HSM multi-party control được ủy quyền** có thể thực hiện. Đồng thời phải bảo vệ chính **quyền tạo credential hoặc sửa IAM của broker**, không để admin thay policy rồi đi vòng.

### 7.2. KMS/HSM khác nhau về khả năng

Một số HSM cung cấp cơ chế **multi-person authorization, quorum cho key ceremony hoặc token/role bảo vệ vật lý**. Nhiều managed KMS chỉ cung cấp **IAM/key policy**, không tự thực hiện workflow M-of-N cho mọi API. Khi nền tảng không hỗ trợ quorum native, dùng **approval service + broker + IAM deny trực tiếp**, kiểm tra thực tế khả năng bypass và hạn chế administrative override.

**Không thể chứng minh một key là non-extractable chỉ vì approval đã đạt quorum.** Cần xác minh key class, generation boundary, export policy và năng lực thực của HSM/KMS.

### 7.3. Chặn TOCTOU

**TOCTOU (time-of-check to time-of-use)** xảy ra khi đã phê duyệt một request dưới policy cũ nhưng **trạng thái/phiên bản khóa hoặc quyền đã thay** trước khi gọi KMS. Broker phải kiểm tra lại **policy revision, key state, pending deletion, expected version và ràng buộc tham số** sát thời điểm thực thi.

Với việc cập nhật trạng thái trong database, dùng **compare-and-swap/version check hoặc transaction** để claim một request đúng một lần. Tuy nhiên KMS là **dịch vụ bên ngoài** nên không có transaction chung mặc định; phải có **idempotency, reconciliation, xác minh actual state và cách phục hồi lệnh đã thực thi nhưng trả response lỗi**.

## 8. Separation of duties, tính độc lập và quyền khẩn cấp

**Separation of duties (SoD)** không chỉ yêu cầu hai nút `Approve`. Cần phân biệt:

- **Requester** đề xuất: phải cung cấp lý do, scope, key reference và tác động.
- **Approver** đánh giá: không có động cơ/quyền tự động để hợp thức hóa yêu cầu của mình.
- **Executor** thực thi: chỉ có quyền chạy action sau khi policy engine cấp phép.
- **Auditor** đối chiếu: có quyền đọc bằng chứng nhưng không được sửa hoặc xóa lịch sử.

Một policy nghiêm ngặt có thể cấm **requester/executor tính vào quorum**, đòi hỏi approver từ **Security và Key owner** là hai người khác nhau, hoặc yêu cầu thêm **data owner** trước khi hủy KEK còn backup. Đây là quy tắc theo từng operation/risk class.

### 8.1. Chống thông đồng và chiếm quyền

Biện pháp giảm rủi ro bao gồm:

1. **Identity proofing và MFA mạnh**; không tính hai account do một người kiểm soát là hai thành viên.
2. **Role diversity**: bắt buộc người từ miền quản trị khác, không chỉ cùng một nhóm vận hành.
3. **Approval được ký/xác thực**, ràng buộc với request digest và challenge chống replay.
4. **Thời hạn ngắn**, trạng thái approval có thể rút lại và không thể chuyển sang request khác.
5. **Alert bất thường** khi cùng cặp approver luôn duyệt lệnh destructive, hoặc approval diễn ra quá nhanh.
6. **Independent immutable audit**, review các override và quyền thay policy.

Quorum không thay code review, đào tạo bảo mật, quy trình thay đổi hay giám sát hành vi lạm dụng.

### 8.2. “Break-glass” khi có sự cố

Nếu private signing key bị nghi lộ và attacker đang ký giả, chờ ba approvers ở ba múi giờ có thể **kéo dài thiệt hại**. Vì vậy có thể thiết kế **đường containment khẩn cấp**: Incident commander/IR có quyền **tạm ngừng `Sign`, revoke principal/session hoặc khóa truy cập** theo runbook, không cần chờ đủ quorum của thao tác **destroy vĩnh viễn**.

Break-glass phải:

- Chỉ bao gồm **các hành động và mục tiêu được phép** (ví dụ disable signing path, không tự export key).
- Dùng danh tính khẩn cấp bảo vệ mạnh, **TTL ngắn**, cảnh báo tức thời, log bất biến.
- Có **hậu kiểm và phê duyệt** để xử lý tác động, tránh quyền khẩn cấp tồn tại dài hạn.
- Được **kiểm thử diễn tập**; không có shortcut mở lại key đã xác nhận compromised mà không đánh giá rủi ro.

**Containment nhanh và hủy khóa vĩnh viễn là hai mức quyết định khác nhau.** Không dùng lý do khẩn cấp để vượt qua kiểm tra backup/retention của một lệnh hủy có thể làm mất dữ liệu hợp lệ.

## 9. Threshold cryptography và Shamir: liên quan nhưng khác quorum workflow

Đối với root secret hoặc khóa recovery, tổ chức có thể sử dụng **Shamir Secret Sharing (SSS)**: tách một bí mật thành **n share**, sao cho cần ít nhất **k share** để tái tạo bí mật theo mô hình đã thiết kế. Trong một sơ đồ lý tưởng, ít hơn k share không đủ thông tin để khôi phục giá trị.

### 9.1. Ý tưởng toán học

Với một trường hữu hạn thích hợp, chủ thể khởi tạo chọn đa thức ngẫu nhiên bậc `k-1`:

\[
f(x) = s + a_1x + a_2x^2 + \cdots + a_{k-1}x^{k-1},
\]

trong đó `s = f(0)` là bí mật, còn share thứ `i` là `(i, f(i))`. Từ **k điểm phân biệt** có thể nội suy để tìm `f(0)`. Các hệ số, trường hữu hạn và random source phải đúng chuẩn; đây là mô tả để hiểu nguyên lý, **không phải hướng dẫn tự viết secret sharing từ đầu**.

| Vấn đề | Workflow approval M-of-N | Secret sharing k-of-n |
| --- | --- | --- |
| Đối tượng điều khiển | Quyền thực hiện một action cụ thể | Khả năng tái tạo một secret |
| Điều kiện | Người duyệt, role, deadline, action/key version | Các share hợp lệ, đủ k phần |
| Có thể kiểm toán “vì sao thao tác được duyệt”? | Có nếu workflow được thiết kế đúng | Không tự có thông tin ý định nghiệp vụ |
| Có cần lộ raw key khi dùng? | Không nhất thiết | **Reconstruction có thể làm secret xuất hiện** nếu không bảo vệ boundary |
| Phù hợp để | Approve rotate, export, delete, policy changes | Recovery/escrow theo mô hình tin cậy |

### 9.2. Threshold signature và key ceremony

Một **threshold signature scheme** có thể cho nhiều bên phối hợp ký mà **không tái tạo private key đầy đủ trong RAM của một chủ thể**, tùy thuật toán/triển khai. Đây **không giống** việc lấy k share rồi dựng private key tại một server thông thường để ký.

**Key ceremony** cho root of trust có thể dùng **dual control, split knowledge, smart cards, HSM roles, tamper-evident evidence, quorum approvals và threshold cryptography** kết hợp. Mỗi cơ chế giải quyết **một vấn đề**:

- Quorum approval: ai được quyết định khởi tạo/phục hồi/xóa?
- HSM/non-extractability: key material nằm trong ranh giới nào?
- Split knowledge/threshold: một bên có thể nắm hoặc sử dụng toàn bộ key không?
- Audit: làm sao chứng minh quyết định và thao tác đã diễn ra đúng?

Không coi một bảng “đã đủ ba share” là bằng chứng rằng yêu cầu phục hồi đã **được Security và owner phê duyệt**.

## 10. Quorum approval theo từng giai đoạn key lifecycle

Quorum phải được **thiết kế xuyên suốt vòng đời khóa**, không chỉ tại nút `Delete`.

~~~mermaid
flowchart TD
    Plan[Key owner xác định purpose, risk và policy] --> Request[Tạo change request bất biến]
    Request --> Quorum{Quorum/role/expiry đạt?}
    Quorum -->|Không| Denied[Từ chối, audit, không thực thi]
    Quorum -->|Có| Preflight[Revalidate policy, state, dependencies]
    Preflight -->|Không đạt| Denied
    Preflight -->|Đạt| Exec[Execution broker / KMS-HSM]
    Exec --> Evidence[Actual state + audit receipt]
    Evidence --> Stage{Key lifecycle stage}
    Stage --> Generate[Generation / Import]
    Stage --> Activate[Activation / Policy change]
    Stage --> Rotate[Rotation / Rewrap]
    Stage --> Revoke[Revoke / Containment]
    Stage --> Destroy[Destruction / Crypto-erasure]
~~~

### 10.1. Generation và import

**Root KEK**, private signing key dài hạn hoặc key phục vụ nhiều hệ thống có thể yêu cầu quorum trước khi sinh. Approval cần gắn với **algorithm, key size/curve, provider/HSM boundary, exportability, usage và owner**.

Nếu policy đòi hỏi private key **sinh trong HSM không xuất được**, việc quorum phê duyệt “tạo key” **không cho phép** tạo key bằng `KeyPairGenerator` trên laptop rồi import. Các thuộc tính kỹ thuật vẫn phải được KMS/HSM enforce.

### 10.2. Activation và thay primary

Khi đưa một key version vào **Active**, kiểm tra `activationAt`, cryptoperiod, trust/public-key distribution, IAM và consumer readiness. Nếu chuyển alias/primary từ `v4` sang `v5`, approval cần **gắn rõ version đích** và điều kiện ngừng dùng `v4` cho bảo vệ mới. Không để người thực thi đổi alias sang version khác sau khi duyệt.

### 10.3. Rotation

Rotation định kỳ có thể được **tự động hóa theo policy đã duyệt**. Quorum nên bảo vệ **phê duyệt chính sách rotation, thay đổi thuật toán, thay root key hoặc cutover ảnh hưởng diện rộng**, thay vì bắt người duyệt từng lần sinh DEK.

Trong envelope encryption, **rewrap DEK** dưới KEK mới có thể đủ cho rotation KEK thông thường; nếu **DEK bị lộ**, cần đánh giá **DEK mới và re-encrypt**. Quorum phải nhìn thấy kết quả kiểm tra backup/dependency, không chỉ dòng trạng thái “rotation succeeded”.

### 10.4. Revocation và compromise

Khi khóa bị lộ, **ngừng quyền `Sign/Decrypt/Unwrap` nguy hiểm ngay** theo quyền IR khẩn cấp đã phân công. Phê duyệt quorum có thể cần cho **thay đổi trust root**, thay khóa dài hạn hoặc xử lý dữ liệu diện rộng; nhưng không nên đặt một quy trình M-of-N chậm chạp làm chậm containment khi attacker đang hành động.

**Revoke** không làm mất raw key mà attacker đã lấy. Nếu KEK và wrapped DEK đã bị lấy, rewrap bản hiện tại không xóa bản cũ; cần đánh giá ảnh hưởng đến DEK và ciphertext.

### 10.5. Destruction

Hủy KEK có thể khiến **backup và ciphertext không thể khôi phục**; cần xác nhận đầy đủ:

- Đúng **key ID/version**, không phải alias động.
- Không còn DEK, wrapped DEK, archive hoặc backup yêu cầu key này; hoặc crypto-erasure được chủ đích phê duyệt.
- Data owner xác nhận retention và legal hold liên quan.
- Có kiểm thử restore hoặc bằng chứng migration theo runbook.
- Thời gian chờ xóa/khả năng hủy lệnh của nhà cung cấp đã được hiểu rõ.

**Một approval cho `SCHEDULE_DESTROY` không mặc nhiên cho phép `DELETE_IMMEDIATELY`**. Nếu provider dùng trạng thái PendingDeletion, phải kiểm tra lại key/version và actual state.

## 11. DEK, KEK và quorum trong envelope encryption

### Vì sao cần quorum đặc biệt với KEK?

Trong **envelope encryption**, DEK mã hóa dữ liệu; KEK bọc DEK. Một **KEK cấp cao** có thể bảo vệ hàng triệu bản ghi qua nhiều DEK và backup. Thao tác **Export, Disable, Rotate, Destroy** KEK ảnh hưởng vượt xa một record, nên phù hợp để đưa vào **risk-based quorum policy**.

~~~mermaid
flowchart LR
    Data[Data owner: dữ liệu, retention, legal hold] --> Preflight[Dependency preflight]
    Owner[Key owner: lifecycle, key version] --> Quorum[Quorum approval]
    Security[Security approver] --> Quorum
    Preflight --> Quorum
    Quorum --> Broker[Execution broker]
    Broker --> KMS[KMS/HSM quản lý KEK]
    KMS --> DEKs[Wrapped DEKs + version references]
    DEKs --> CT[(Ciphertext / backups)]
    Broker --> Audit[Audit + reconciliation]
    Quorum --> Audit
~~~

### Ví dụ policy theo rủi ro

- **Mã hóa record mới với DEK:** không cần quorum cho từng record; ứng dụng kiểm tra tenant authorization và nonce uniqueness.
- **Sinh DEK theo profile đã duyệt:** thường tự động qua KMS/KeyGenerator phù hợp.
- **Chuyển KEK primary theo lịch:** approval theo risk tier hoặc automation đã được ủy quyền, có canary/rollback.
- **Thay key policy cho phép export KEK:** quorum nghiêm ngặt hoặc từ chối hoàn toàn nếu policy cấm export.
- **Destroy KEK root:** M-of-N có Security và owner, kèm xác nhận **data owner về backup/dependencies**.

**Không coi quorum là thay thế IAM:** một request `Unwrap` thành công ở KMS chưa đủ để cho người dùng đọc bản ghi tenant khác. Ứng dụng phải kiểm tra resource authorization, còn broker/KMS kiểm tra key usage/identity.

## 12. Quorum với private signing key, PKI và trust

Đối với private signing key phục vụ hóa đơn, giao dịch hoặc CA, có hai lớp:

1. **Quản trị key material**: sinh, import, rotate, export, hủy, cấp quyền `Sign`.
2. **Quản trị trust**: phát hành chứng thư, cập nhật JWKS/public key registry, thay trust anchor, thu hồi chứng thư, đánh giá chữ ký lịch sử.

Quorum ở lớp (1) **không tự cập nhật** verifier của lớp (2). Nếu private key bị lộ, hệ thống có thể phải **chặn ký mới** tại HSM và **thu hồi niềm tin/chứng thư** tại CA/registry, đồng thời phân phối cập nhật đến client cache.

**Chữ ký toán học hợp lệ chưa đủ chứng minh giao dịch hợp pháp**. Với tài liệu cũ, `Signature.verify() == true` không nói được chữ ký có được tạo trước compromise hay do người có thẩm quyền phê duyệt. Cần **trusted timestamp**, certificate chain, trạng thái CRL/OCSP và chính sách lịch sử phù hợp.

### Key ceremony của CA

Các thao tác như tạo root CA key, bật root signing capability, thay trust anchor hoặc xuất recovery share thường có **mức rủi ro rất cao**. Một key ceremony có thể yêu cầu:

- HSM được phê duyệt, người tham gia có vai trò xác định.
- M-of-N approvals và/hoặc thẻ vật lý/shares theo thiết kế.
- Ghi biên bản, quan sát độc lập, kiểm tra key attributes và audit.
- Phê duyệt riêng cho từng action; không dùng “phê duyệt tạo CA key” làm giấy phép ký bất kỳ chứng thư nào về sau.

**Không tự xây threshold signing protocol** để thay sản phẩm chuẩn hoặc dịch vụ đã được đánh giá; security model của việc ký phải được xem xét cùng ứng dụng/PKI.

## 13. Mẫu policy-as-code và audit event

Ví dụ sau minh họa cấu hình cho **thao tác hủy KEK**. Đây là **schema khái niệm**, không phải cấu hình trực tiếp của một nhà cung cấp KMS:

~~~json
{
  "policyId": "critical-kek-change",
  "revision": 24,
  "action": "SCHEDULE_DESTROY",
  "keyClass": "ROOT_KEK",
  "environment": "production",
  "minimumDistinctApprovers": 3,
  "eligibleRoles": [
    "KEY_OWNER",
    "SECURITY",
    "DATA_GOVERNANCE",
    "PLATFORM_CUSTODIAN"
  ],
  "requiredRoles": ["SECURITY", "KEY_OWNER"],
  "forbidRequesterAsApprover": true,
  "forbidExecutorAsApprover": true,
  "requestTtlMinutes": 30,
  "approvalTtlMinutes": 15,
  "requireExactKeyVersion": true,
  "requireDataDependencyCheck": true,
  "requireBackupRestoreEvidence": true,
  "defaultAction": "DENY",
  "directProviderApiAccess": "BROKER_ONLY"
}
~~~

Ví dụ trên yêu cầu **3 approvers riêng biệt**, trong đó phải có **ít nhất một `SECURITY` và một `KEY_OWNER`**, và người yêu cầu/người thực thi không được tính vào quorum. Hành động còn cần **đủ bằng chứng preflight**; nếu không có backup evidence, **3 approvals vẫn chưa đủ để execute**.

### Audit event tham khảo

~~~json
{
  "eventType": "KEY_CHANGE_EXECUTED",
  "requestId": "chg-2026-01128",
  "action": "SCHEDULE_DESTROY",
  "keyId": "billing-root-kek",
  "keyVersion": "v4",
  "requestDigest": "sha256:example-digest-not-real",
  "policyRevision": 24,
  "quorumRequired": 3,
  "quorumSatisfied": true,
  "requiredRolesSatisfied": true,
  "preflightEvidenceRef": "backup-check-2026-98",
  "executionPrincipal": "kms-execution-broker",
  "providerResult": "PENDING_DELETION",
  "recordedAt": "2026-11-28T10:20:00Z"
}
~~~

**Không cần đưa raw DEK/KEK/private key vào log** để kiểm toán quorum. Lưu **request ID, version, action, approver identities theo mức cần thiết, policy revision, result, bằng chứng và correlation ID**. Audit phải được bảo vệ toàn vẹn, có kiểm soát truy cập và retention phù hợp.

### Chống lộ metadata nhạy cảm

Danh sách approver, key references, tenant ID và thông tin phân quyền có thể là **metadata nhạy cảm**. Không công bố toàn bộ lịch sử phê duyệt hoặc sơ đồ hạ tầng cho bên không được phép chỉ vì bản thân raw key không xuất hiện trong audit.

## 14. Java 17: kiểm tra quorum trước khi cho phép thao tác quản trị

Đoạn mã sau là **policy gate minh họa**, không trực tiếp gọi KMS/HSM. Nó kiểm tra:

1. Request có key/version, action, tenant, người đề nghị, người thực thi và **policy revision**.
2. Approval khớp **request ID và digest của các trường chuẩn hóa**, không bị đổi action/parameters.
3. Mỗi approver được đếm **một lần**, có **role hợp lệ** và không trùng requester/executor.
4. Phải đạt **minimumDistinct** và **requiredRoles**.
5. Thời điểm request/approval còn hiệu lực; tất cả approval đến từ **dịch vụ xác thực tin cậy**.

Ví dụ dùng SHA-256 làm **fingerprint của ý định request**, không phải cơ chế xác thực danh tính. `proofVerified` trong dữ liệu demo là **kết quả đã xác minh do trusted approval service cung cấp**; không được cho client tự đặt nó thành `true` trong production.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class QuorumApprovalDemo {
    enum Action { CREATE_ROOT, ROTATE_KEK, SCHEDULE_DESTROY }

    record ChangeRequest(
            String id, String keyRef, String tenant, Action action,
            String canonicalParameters, String requesterId,
            String executorId, long policyRevision,
            Instant createdAt, Instant deadline) {}

    record Approval(
            String requestId, String intentDigest, String approverId,
            String role, Instant approvedAt, Instant expiresAt,
            boolean proofVerified) {}

    record Policy(
            int minimumDistinct, Set<String> allowedRoles,
            Set<String> requiredRoles, Duration maximumRequestTtl) {
        Policy {
            if (minimumDistinct < 2 || allowedRoles == null
                    || requiredRoles == null
                    || maximumRequestTtl == null
                    || !allowedRoles.containsAll(requiredRoles)
                    || maximumRequestTtl.isZero()
                    || maximumRequestTtl.isNegative()) {
                throw new IllegalArgumentException("Invalid quorum policy");
            }
            allowedRoles = Set.copyOf(allowedRoles);
            requiredRoles = Set.copyOf(requiredRoles);
        }
    }

    // Length-prefix từng trường để tránh nhập nhằng khi nối chuỗi.
    static String digest(ChangeRequest r) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        String[] fields = {
                r.id(), r.keyRef(), r.tenant(), r.action().name(),
                r.canonicalParameters(), r.requesterId(), r.executorId(),
                Long.toString(r.policyRevision()),
                r.createdAt().toString(), r.deadline().toString()
        };
        for (String field : fields) {
            byte[] data = field.getBytes(StandardCharsets.UTF_8);
            md.update(ByteBuffer.allocate(4).putInt(data.length).array());
            md.update(data);
        }
        return HexFormat.of().formatHex(md.digest());
    }

    static boolean hasQuorum(
            ChangeRequest req, List<Approval> approvals, Policy policy,
            Map<String, String> trustedRoleByIdentity,
            long currentPolicyRevision, Instant now) throws Exception {
        if (req == null || approvals == null || policy == null
                || trustedRoleByIdentity == null || now == null
                || req.id() == null || req.id().isBlank()
                || req.keyRef() == null || req.keyRef().isBlank()
                || req.tenant() == null || req.tenant().isBlank()
                || req.action() == null || req.canonicalParameters() == null
                || req.requesterId() == null || req.executorId() == null
                || req.requesterId().equals(req.executorId())
                || req.createdAt() == null || req.deadline() == null
                || req.policyRevision() != currentPolicyRevision
                || now.isBefore(req.createdAt())
                || !now.isBefore(req.deadline())
                || !req.deadline().isAfter(req.createdAt())
                || Duration.between(req.createdAt(), req.deadline())
                        .compareTo(policy.maximumRequestTtl()) > 0) {
            return false;
        }

        String intent = digest(req);
        Set<String> people = new HashSet<>();
        Set<String> roles = new HashSet<>();

        for (Approval a : approvals) {
            if (a == null || a.approverId() == null || a.role() == null
                    || a.approvedAt() == null || a.expiresAt() == null
                    || !a.proofVerified()
                    || !req.id().equals(a.requestId())
                    || !intent.equals(a.intentDigest())
                    || req.requesterId().equals(a.approverId())
                    || req.executorId().equals(a.approverId())
                    || !policy.allowedRoles().contains(a.role())
                    || !a.role().equals(
                            trustedRoleByIdentity.get(a.approverId()))
                    || a.approvedAt().isBefore(req.createdAt())
                    || a.approvedAt().isAfter(now)
                    || !a.expiresAt().isAfter(now)
                    || !people.add(a.approverId())) {
                return false; // deny on malformed/replayed/duplicate approval
            }
            roles.add(a.role());
        }
        return people.size() >= policy.minimumDistinct()
                && roles.containsAll(policy.requiredRoles());
    }

    public static void main(String[] args) throws Exception {
        Instant now = Instant.parse("2026-11-28T10:00:00Z");
        Policy policy = new Policy(
                2,
                Set.of("KEY_OWNER", "SECURITY", "DATA_GOVERNANCE"),
                Set.of("SECURITY"),
                Duration.ofMinutes(30));
        ChangeRequest request = new ChangeRequest(
                "change-101", "billing-kek/v4", "production/billing",
                Action.SCHEDULE_DESTROY,
                "delayDays=30;backupCheck=backup-88",
                "requester-1", "kms-broker", 24,
                now.minusSeconds(120), now.plusSeconds(600));
        String intent = digest(request);
        Map<String, String> trustedRoles = Map.of(
                "alice", "KEY_OWNER", "bob", "SECURITY",
                "charlie", "DATA_GOVERNANCE");

        Approval a = new Approval(
                request.id(), intent, "alice", "KEY_OWNER",
                now.minusSeconds(90), now.plusSeconds(300), true);
        Approval b = new Approval(
                request.id(), intent, "bob", "SECURITY",
                now.minusSeconds(60), now.plusSeconds(300), true);

        if (!hasQuorum(request, List.of(a, b), policy,
                trustedRoles, 24, now)) {
            throw new AssertionError("Expected valid 2-of-3 quorum");
        }
        if (hasQuorum(request, List.of(a, a), policy,
                trustedRoles, 24, now)) {
            throw new AssertionError("Duplicate approver was counted");
        }
        if (hasQuorum(request, List.of(a), policy,
                trustedRoles, 24, now)) {
            throw new AssertionError("One approval cannot satisfy quorum");
        }

        // Cùng approvals nhưng đổi tham số -> digest không khớp.
        ChangeRequest mutated = new ChangeRequest(
                request.id(), request.keyRef(), request.tenant(),
                request.action(), "delayDays=0;backupCheck=none",
                request.requesterId(), request.executorId(),
                request.policyRevision(),
                request.createdAt(), request.deadline());
        if (hasQuorum(mutated, List.of(a, b), policy,
                trustedRoles, 24, now)) {
            throw new AssertionError("Changed request was accepted");
        }
        if (hasQuorum(request, List.of(a, b), policy,
                trustedRoles, 25, now)) {
            throw new AssertionError("Stale policy revision accepted");
        }

        System.out.println("Quorum policy demo: PASS");
        // Production: CHƯA có KMS call; cần IAM, approval proof,
        // preflight, atomic claim, single-use permit và reconciliation.
    }
}
~~~

### 14.1. Phân tích những bảo đảm và giới hạn

**Code minh họa có thể chứng minh:** distinct approvers, chính sách vai trò, cùng intent digest, hạn dùng, requester/executor không được tính và không dùng revision đã cũ.

**Code chưa chứng minh:** MFA/chữ ký của từng approval, identity-to-person mapping, tình trạng người duyệt vừa bị offboard, role diversity giữa tổ chức, kiểm tra backup/dependency, quyền dùng KMS, trạng thái key khi execute, atomic single-use claim hay tình trạng HSM. Những điều đó phải được thực thi tại **dịch vụ đáng tin và điểm gọi KMS/HSM**.

Đặc biệt, `trustedRoleByIdentity` phải đến từ **identity provider được quản trị**, không phải map client gửi; `canonicalParameters` phải do **server chuẩn hóa**, không chấp nhận nhiều dạng biểu diễn một action; `proofVerified` không bao giờ được nhận trực tiếp từ người gọi. Trong hệ thống thật nên dùng **permit có bảo vệ mật mã** được ràng buộc request và chống replay, cùng log độc lập.

### 14.2. Tại sao không xuất raw key để kiểm tra quorum?

Không cần và không nên xuất private key/KEK để “xác minh approval thành công”. Broker có thể đọc **operation result, key ID/version và trạng thái được provider trả về**. Nếu key thuộc loại non-extractable, policy phải kiểm tra **hành vi từ chối export**, không vô tình đưa vật liệu khóa vào log/debug.

## 15. Rủi ro thường gặp trong triển khai quorum

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Hai account của cùng một người được tính là hai approvers | Vượt yêu cầu độc lập | Ánh xạ tới người/đơn vị đã xác minh, chống self-approval |
| Chỉ đếm hai click, không kiểm tra vai trò | Không đạt yêu cầu Security/data owner | Role/organization constraints cùng quorum count |
| Approval không gắn key version và parameters | Dùng approval của request khác hoặc đổi scope | Canonical intent digest, key ID/version và policy revision |
| Dùng approval đã hết hạn hoặc đã bị thu hồi | Chấp nhận quyết định không còn hiệu lực | TTL, revocation và revalidation tại execute |
| Requester tự duyệt hoặc executor tự ký duyệt | Xung đột lợi ích | SoD, định danh độc lập và dual control |
| Admin có thể giảm threshold tùy ý | Bypass mọi kiểm soát quorum | Bảo vệ thay đổi policy/quorum bằng kiểm soát tương đương hoặc mạnh hơn |
| KMS API vẫn gọi trực tiếp được | Workflow chỉ là UI decoration | IAM deny direct access, execution broker/HSM control |
| Client gửi `approved=true` | Có thể giả quyết định | Approval đã xác thực, permission token chống giả mạo |
| Không kiểm tra key state khi thực thi | TOCTOU, dùng key đã revoke | Revalidate sát KMS call, kiểm tra actual state |
| Không có idempotency/atomic claim | Retry tạo hai action hoặc xóa sai thời điểm | Transaction/CAS, request ID và reconciliation |
| Quorum cho mọi `Decrypt` request | Bị nghẽn và giảm availability không cần thiết | Risk-based policy; IAM/runtime authorization cho thao tác thường |
| Quorum chặn cả containment khẩn cấp | Attacker tiếp tục gây hại khi chờ duyệt | Emergency disable/revoke giới hạn scope và hậu kiểm |
| 3-of-5 Shamir được hiểu như 3 approvals | Bỏ qua ủy quyền sử dụng secret | Phân tách threshold recovery và approval workflow |
| Dùng chung KEK cho mọi tenant mà không inventory | Không biết tác động của destroy/revoke | Scope rõ, danh sách wrapped DEK và backup dependency |
| Hủy KEK vì quorum đã đủ nhưng chưa kiểm tra backup | Mất dữ liệu không thể phục hồi | Quorum + mandatory dependency/restore preflight |
| KMS/HSM key không xuất được nên bỏ kiểm tra `Sign` | Có thể ký giả qua API | Authorize operation, principal và transaction context |
| Ghi key material vào audit để chứng minh thao tác | Mở rộng sự cố lộ bí mật | Chỉ log metadata, result và bằng chứng tối thiểu |

## 16. Kiểm toán, giám sát và kiểm thử âm tính

Quorum không đủ nếu không thể **chứng minh** nó đã được thực thi. Mỗi request nên có **event trail** tối thiểu:

~~~text
REQUEST_CREATED
  -> APPROVER_ELIGIBILITY_CHECKED
  -> APPROVAL_RECORDED (identity / role / digest / expiry)
  -> QUORUM_VERIFIED
  -> DEPENDENCY_PREFLIGHT_PASSED
  -> EXECUTION_PERMIT_ISSUED (one-time / scope)
  -> KMS_OPERATION_ATTEMPTED
  -> KMS_ACTUAL_STATE_VERIFIED
  -> REQUEST_CLOSED / EXCEPTION_RECONCILED
~~~

### Các phép kiểm phủ định nên có

| Test | Kỳ vọng |
| --- | --- |
| **1-of-2** hoặc **2-of-3** chưa đủ | Từ chối |
| Một approver duyệt hai lần dưới hai account | Không tính là hai người độc lập |
| Đủ người nhưng thiếu **Security** bắt buộc | Từ chối |
| Requester trùng một approver | Từ chối khi policy cấm self-approval |
| Thay `keyVersion` hoặc `deleteAt` sau khi approve | Digest khác, yêu cầu duyệt lại |
| Approval đã hết hạn / policy revision đổi | Từ chối và yêu cầu đánh giá lại |
| Một người bị thu hồi quyền sau khi approve | Revalidate eligibility; từ chối theo policy |
| Direct API gọi `DeleteKey` không qua broker | IAM/HSM chặn |
| Broker nhận lại permit đã dùng | Từ chối replay |
| KMS trả lỗi mơ hồ sau request destructive | Reconcile state; không thử lại mù quáng |
| Backup vẫn phụ thuộc key định destroy | Preflight chặn dù đủ quorum |
| Incident commander dùng quyền khẩn cấp để export key | Từ chối vì vượt emergency scope |

### Chỉ số có giá trị

- **Quorum bypass attempts:** hành động quản trị được gọi mà thiếu permit.
- **Approval latency** theo action và risk class; cảnh báo khi duyệt quá nhanh hoặc quá lâu bất thường.
- **Policy revision mismatches** và approvals không còn hợp lệ.
- **Pending requests** đã hết hạn, người duyệt vắng mặt, quorum không đạt.
- **KMS reconciliation failures** sau lệnh destructive.
- **Emergency overrides**, mục tiêu, TTL và tình trạng hậu kiểm.
- **Key inventory drift**: request duyệt cho version X nhưng actual action ảnh hưởng version Y.
- **Dependency failures**: backup/DEK còn phụ thuộc key định xóa.

**Audit không phải nơi lưu raw private key, KEK/DEK, PSK hoặc plaintext.** Người kiểm toán chỉ cần định danh, mục tiêu, bằng chứng phê duyệt, kết quả và mối liên hệ yêu cầu–thao tác.

## 17. Tình huống thực tế: hủy KEK trong nền tảng thanh toán đa tenant

Một nền tảng thanh toán dùng **AES-GCM** để mã hóa dữ liệu bằng DEK; DEK được bọc bởi KEK `billing-root-kek/v4` trong KMS/HSM. Nhóm muốn hủy `v4` sau khi chuyển sang `v5`.

### Bối cảnh và policy

Key inventory ghi `v4` đã hết **originator-usage period**, nhưng một số backup lâu năm có thể chứa wrapped DEK liên quan. Chính sách yêu cầu **3-of-4 approvers**, trong đó phải có **Key owner và Security**, đồng thời có **xác nhận không còn phụ thuộc backup**. `SCHEDULE_DESTROY` được phân biệt rõ với **disable**, **revoke** và **destroy ngay**.

### Giai đoạn 1 — Tạo yêu cầu

Một **change coordinator** (người đề nghị, không nằm trong quorum và không phải executor) tạo request theo kế hoạch của Key owner, gồm `keyId=billing-root-kek`, `version=v4`, `action=SCHEDULE_DESTROY`, thời gian chờ, policy revision, danh sách tenant và kết quả kiểm tra DEK/backup. Dịch vụ workflow ghi **digest của cấu hình chuẩn hóa** và chặn sửa action sau khi gửi duyệt.

### Giai đoạn 2 — Phê duyệt độc lập

Key owner, Security và một người từ Data Governance/KMS operations được xác minh danh tính và vai trò. Không tính người đề nghị nếu policy cấm. Nếu một người mất quyền trong quá trình chờ, các approval được revalidate trước khi thực thi.

### Giai đoạn 3 — Phát hiện backup chưa di chuyển

Backup ở tenant B vẫn chứa một wrapped DEK dưới `v4`. Dù đã có **ba approvals**, dependency preflight **từ chối hủy**. Nhóm thực hiện rewrap/kiểm tra restore hoặc quyết định retention phù hợp; nếu dữ liệu phải được giữ, không được phá khả năng giải mã chỉ vì đã “đạt 3-of-4”.

### Giai đoạn 4 — Thực thi có kiểm soát

Sau khi dependencies được xử lý, phê duyệt được làm mới nếu request/parameters đã thay. Broker đối chiếu **exact key version, trạng thái, policy revision**, rồi gọi API theo quyền IAM giới hạn. Sau response, broker đối chiếu trạng thái KMS (chẳng hạn `PendingDeletion` nếu provider dùng trạng thái đó), ghi audit receipt và thông báo người liên quan.

### Giai đoạn 5 — Tình huống khẩn cấp khác

Trong lúc chờ, một signer HSM khác bị nghi lộ và attacker đang phát sinh chữ ký giả. Security **không dùng request destroy KEK** để giải quyết chuyện này. Incident commander dùng **runbook containment riêng** để chặn `Sign`, thu hồi principal/chứng thư phù hợp, rồi mới điều tra, rotate và thực hiện các phê duyệt bổ sung.

**Bài học:** quorum approval giúp tránh quyết định đơn lẻ, nhưng chỉ an toàn khi đi cùng **scope đúng, dependency checks, IAM enforcement, key state và cơ chế phản ứng sự cố nhanh**.

## 18. Checklist thiết kế quorum approval

- [ ] Đã phân loại operation theo **risk tier** và xác định khi nào cần người duyệt thay vì automation?
- [ ] Chính sách có **M-of-N**, danh sách eligible identities, required roles và điều kiện SoD rõ ràng?
- [ ] Hai tài khoản của cùng một người **không** được tính là hai approvers độc lập?
- [ ] Requester, executor, key owner, security approver, custodian và auditor có trách nhiệm phân biệt?
- [ ] Approval gắn với **exact key ID/version, action, parameters, tenant/environment, policy revision**?
- [ ] Canonical request digest có biểu diễn ổn định, không mơ hồ; approval có proof xác thực?
- [ ] Approval và request có **TTL**, khả năng revoke, revalidation và chống replay?
- [ ] Broker có **single-use permit**, idempotency, trạng thái execution và reconciliation?
- [ ] IAM/KMS/HSM **chặn direct API** tới operation nhạy cảm ngoài đường đã được duyệt?
- [ ] Quyền sửa threshold, approver list và policy được bảo vệ ít nhất tương đương lệnh nó quản trị?
- [ ] Non-extractability và điều kiện sinh key trong HSM được **provider thực thi**, không chỉ khai báo?
- [ ] Với DEK/KEK có **envelope encryption, versioning, AAD/nonce strategy và backup dependency inventory**?
- [ ] Với private signing key có quy trình **PKI/JWKS/trust, key usage, revocation và verification lịch sử**?
- [ ] Quorum dùng cho destruction có **data owner sign-off, restore tests, retention/legal hold** phù hợp?
- [ ] Khi compromise có **containment khẩn cấp** được giới hạn scope và có hậu kiểm?
- [ ] State, policy revision và eligibility được **kiểm tra lại khi execute**, tránh TOCTOU/cache cũ?
- [ ] Đã thử thiếu quorum, duplicate identity, role thiếu, request bị sửa, expiry, direct bypass và retry?
- [ ] Audit truy vết được **approved intent → broker permit → KMS actual result**, không ghi raw key?
- [ ] Đã xem xét **collusion, availability, vacation/offboarding, node offline và emergency override**?

## 19. Câu hỏi tự kiểm tra

**1. “2-of-3 quorum approval” nghĩa là gì?**  
Ít nhất hai trong ba bên đủ tư cách phải phê duyệt cùng một yêu cầu, với danh tính độc lập và các điều kiện role/scope/time áp dụng. Hai lần duyệt từ cùng người không đạt.

**2. M-of-N approvals có phải Shamir secret sharing không?**  
Không. Approval là quyết định có thẩm quyền; Shamir k-of-n là cơ chế khôi phục secret từ đủ shares. Có thể kết hợp nhưng không thay thế nhau.

**3. Tại sao hai approvers hợp lệ có thể vẫn chưa đủ?**  
Vì policy có thể yêu cầu một role bắt buộc, backup preflight, key version chính xác, IAM enforcement hoặc policy revision chưa thay đổi.

**4. Vì sao digest của request không thay được xác thực người duyệt?**  
Vì SHA-256 digest chỉ xác định nội dung; bất kỳ ai cũng có thể tính lại. Cần chứng cứ phê duyệt được ràng buộc với danh tính từ dịch vụ tin cậy.

**5. HSM key không xuất được có khiến quorum phê duyệt `Sign` không cần thiết?**  
Không. Principal có quyền `Sign` có thể lạm dụng API dù không lấy được byte private key; phải bảo vệ quyền gọi và mục đích nghiệp vụ.

**6. Nếu KMS IAM vẫn cho admin gọi `DeleteKey` trực tiếp thì workflow quorum có hiệu quả không?**  
Không đáng tin cậy. Admin có thể bỏ qua workflow; cần bảo vệ quyền đặc quyền, giới hạn execution path và kiểm thử direct bypass.

**7. Tại sao không yêu cầu quorum khi đang cần chặn ký giả khẩn cấp?**  
Chờ nhiều người có thể tăng thiệt hại; cần runbook containment hẹp, có ủy quyền và audit tức thời, tách khỏi thao tác hủy vĩnh viễn.

**8. Quorum 3-of-4 đã đủ để xóa KEK khi backup vẫn còn wrapped DEK không?**  
Không. Phải đáp ứng phụ thuộc/retention và kiểm thử recovery; quorum không biến một hành động nguy hiểm thành an toàn.

**9. Nguy cơ TOCTOU trong phê duyệt khóa là gì?**  
Lúc approve policy/state hợp lệ nhưng trước execute chúng thay đổi. Broker phải revalidate và ràng buộc version/action sát thời điểm thực thi.

**10. Thay chính sách từ 3-of-5 xuống 1-of-1 có cần kiểm soát không?**  
Có. Nếu một admin tự giảm threshold thì toàn bộ hàng rào quorum có thể bị vô hiệu; thay đổi phải được bảo vệ bằng quy trình độc lập tương đương hoặc mạnh hơn.

## Ghi nhớ

**Quorum approval là cơ chế yêu cầu đủ số lượng và đúng vai trò các bên có thẩm quyền trước khi thực hiện thao tác mật mã hoặc thay đổi key policy có rủi ro cao.** Nó giúp giảm sai sót/lạm dụng của một cá nhân, nhưng **không đồng nghĩa chia key thành shares hoặc threshold cryptography**, cũng không thay **MFA, IAM, HSM non-extractability, kiểm tra dữ liệu phụ thuộc và audit**. Một thiết kế an toàn phải ràng buộc phê duyệt với **exact request/key version, intent digest, danh tính, role, deadline và policy revision**, chặn đường gọi KMS/HSM trực tiếp, revalidate trước thực thi và có **containment khẩn cấp** không để attacker tiếp tục gây hại. Trong toàn bộ vòng đời khóa — **generation, provisioning, activation, usage, rotation, revocation và destruction** — hãy phối hợp **Key owner, Security, custodian, data owner, execution broker và auditor**; kết nối với **DEK/KEK, envelope encryption, chữ ký số/PKI, key inventory, cryptoperiod và backup** để quyết định M-of-N thực sự bảo vệ hệ thống thay vì chỉ là hai nút “Approve” trên giao diện.

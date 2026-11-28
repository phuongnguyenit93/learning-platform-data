# Suspended state: Trạng thái tạm đình chỉ trong vòng đời khóa mật mã

Một dịch vụ thanh toán ký các bản ghi giao dịch bằng private key được giữ trong HSM. Bộ phận vận hành phát hiện số lần gọi API **Sign** tăng đột biến và nghi ngờ một service account bị chiếm quyền. Xóa private key ngay lập tức có thể làm mất khả năng điều tra hoặc khôi phục những quy trình đang phụ thuộc khóa; tiếp tục cho phép ký lại tạo rủi ro phát hành thêm chữ ký trái phép. Lựa chọn phù hợp trong nhiều quy trình phản ứng sự cố là **tạm đình chỉ sử dụng khóa (suspend)** trong khi xác minh tình hình và quyết định hành động tiếp theo.

**Suspended state** là trạng thái vòng đời cho biết khóa **tạm thời không được sử dụng cho những thao tác thuộc phạm vi đình chỉ**, nhưng **key material và metadata vẫn được giữ lại** và có thể có một con đường **khôi phục hoạt động** theo điều kiện kiểm soát. Đây không phải từ đồng nghĩa với hủy khóa, và cũng **không chứng minh khóa chưa từng bị lộ**. Sơ đồ trạng thái, danh sách thao tác bị chặn và quy tắc reactivation **phải được xác định theo chuẩn, KMS/HSM, giao thức và chính sách cụ thể**; không phải mọi nhà cung cấp đều có một trạng thái API tên **SUSPENDED**.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, suspended state nối vòng đời **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy** với AES-GCM, chữ ký số, mật mã bất đối xứng, KMS/HSM, envelope encryption, IAM và kiểm toán. Mục tiêu là biết **khi nào phải chặn thao tác khóa, chặn ở đâu, dữ liệu cũ bị ảnh hưởng gì và khi nào được phép khôi phục**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **suspended state** và phân biệt nó với **active**, **deactivated**, **disabled**, **revoked**, **compromised** và **destroyed**.
2. Thiết kế **bảng quyết định theo trạng thái × mục đích khóa × thao tác × danh tính gọi** thay vì chỉ kiểm tra một boolean.
3. Phân tích tác động đình chỉ **DEK, KEK, private signing key, HMAC key, key agreement key** tới dữ liệu hoặc chữ ký lịch sử.
4. Xây dựng quy trình **suspend → điều tra → reactivate hoặc retire/rotate/revoke** có phê duyệt, audit và điều kiện rõ ràng.
5. Nhận diện rủi ro **cached key, session key, multi-region propagation, race condition, alias và batch job đang chạy**.
6. Viết mô hình kiểm tra policy trong Java 17 và hiểu tại sao demo ứng dụng không thay thế cơ chế chặn ở KMS/HSM.
7. Chuẩn bị kế hoạch khôi phục nghiệp vụ mà không vội mở lại quyền sử dụng một khóa có khả năng đã bị xâm phạm.

## 2. Suspended là gì và không phải là gì?

Về mặt khái niệm, một khóa có thể được tạo và kiểm tra, sau đó **kích hoạt** để sử dụng theo purpose, rồi **tạm đình chỉ** khi cần tạm chặn. Khi nguyên nhân được xử lý và policy cho phép, khóa có thể trở lại active; nếu đã lộ, hết hạn hoặc không còn tin cậy, có thể phải chuyển sang tuyến xử lý khác.

~~~mermaid
stateDiagram-v2
    [*] --> PreActive: Tạo và đăng ký
    PreActive --> Active: Phê duyệt kích hoạt
    Active --> Suspended: Tạm chặn theo policy
    Suspended --> Active: Xét duyệt khôi phục
    Suspended --> Deactivated: Ngừng dùng lâu dài
    Active --> Deactivated: Hết cryptoperiod / retirement
    Active --> Compromised: Xác nhận lộ/chiếm quyền
    Suspended --> Compromised: Điều tra xác nhận lộ
    Compromised --> Destroyed: Hủy khi đủ điều kiện
    Deactivated --> Destroyed: Hủy khi hết phụ thuộc
    Destroyed --> [*]
~~~

Sơ đồ này là **mô hình học tập**, không phải API hay sơ đồ chuyển trạng thái bắt buộc của mọi KMS. Các hệ thống thực có thể dùng tên **Enabled/Disabled**, **PendingDeletion**, **Archived**, **Revoked** hoặc trạng thái do ứng dụng định nghĩa. Đừng tự gán khả năng khôi phục chỉ vì nhìn thấy một tên trạng thái tương tự.

### 2.1. So sánh các khái niệm dễ nhầm

| Khái niệm | Ý nghĩa khái quát | Khả năng sử dụng hoặc phục hồi |
|---|---|---|
| **Pre-active** | Đã tạo/nhập và đăng ký nhưng chưa cho dùng chính thức | Chờ kích hoạt theo policy |
| **Active** | Cho phép các thao tác đúng purpose, key state và IAM | Không đồng nghĩa mọi caller được dùng mọi thao tác |
| **Suspended** | **Tạm chặn có chủ đích** trong thời gian chờ xét duyệt/sự kiện | Có thể re-activate nếu policy và đánh giá rủi ro cho phép |
| **Deactivated/retired** | Ngừng sử dụng theo vòng đời hoặc kết thúc cryptoperiod | Có thể chỉ còn quyền xử lý dữ liệu lịch sử tùy chính sách |
| **Disabled** | Trạng thái hoặc cờ vận hành chặn API tại một sản phẩm | Có thể trùng hiệu ứng kỹ thuật của suspend, nhưng không tự có cùng ý nghĩa nghiệp vụ |
| **Revoked** | Quyền tin cậy hoặc quyền sử dụng bị thu hồi theo một hệ thống chính sách | Không tự đồng nghĩa byte khóa đã bị hủy; đặc biệt khác certificate revocation |
| **Compromised** | Khóa bị lộ hoặc có căn cứ coi tính bí mật/toàn vẹn khóa không còn đáng tin | Không tự khôi phục như một sự cố tạm thời thông thường |
| **Destroyed** | Vật liệu khóa bị hủy theo cơ chế/phạm vi áp dụng | Thường không thể thực hiện phép toán với key material đã hủy; cần xét bản sao và backup |

**Một khóa có thể vừa bị đánh dấu Suspended trong ứng dụng, vừa đang Enabled ở KMS** nếu hai hệ thống không được đồng bộ. Khi đó việc chặn trong UI **không bảo đảm** API KMS đã từ chối thao tác. Hành vi thực tế phải kiểm tra **điểm thực thi (enforcement point)**.

### 2.2. Suspended không có nghĩa vật liệu khóa đã biến mất

Khi suspend, các thành phần sau thường **vẫn tồn tại**:

- Private key/DEK/KEK ở kho khóa hoặc HSM, nếu chưa có thao tác hủy.
- Key ID, version, purpose, owner, cryptoperiod, lịch sử policy và audit.
- Bản mã, encrypted/wrapped DEK, chữ ký và thông điệp lịch sử.
- Các bản sao **DEK/derived key/session key đã xuất** vào tiến trình, cache hoặc thiết bị khác.
- Public key/certificate/JWKS đã phân phối và được cache bởi verifier hoặc đối tác.

Điều này giải thích tại sao **suspend không phải crypto-erasure**, không thu hồi được bản sao đã rò rỉ và không tự chặn mọi phép toán **offline**.

### 2.3. Hai trục độc lập: trạng thái vòng đời và quyền sử dụng

Để quyết định một operation hợp lệ, chỉ nhìn **state == ACTIVE** là chưa đủ. Ít nhất phải xét:

~~~text
decision = Policy(
    keyLifecycleState,
    keyPurposeAndAlgorithm,
    keyVersion,
    requestedOperation,
    authenticatedPrincipal,
    tenantAndResource,
    approvalAndRiskState,
    effectiveTimeAndRegion
)
~~~

Ví dụ một RSA key đang **Active** nhưng purpose chỉ cho **Sign** thì API **Decrypt** vẫn phải bị chặn. Ngược lại, một bản chữ ký cũ có thể được xác minh bằng public key đã lưu ở verifier, **dù private signing key đang Suspended ở KMS**. Việc **chấp nhận** chữ ký đó về nghiệp vụ còn phụ thuộc chính sách tin cậy và thời điểm.

## 3. Các thao tác nào phải chặn khi khóa bị Suspended?

Không có bảng cấp phép duy nhất đúng cho mọi hệ thống. Bảng dưới là **chính sách minh họa theo hướng fail-closed** đối với các thao tác sử dụng key material bí mật ở một KMS trung tâm. Nếu sản phẩm hoặc tổ chức cần **decrypt-only để phục hồi dữ liệu**, phải định nghĩa một exception/đường xử lý được kiểm soát chứ không ngầm suy ra rằng “Suspended vẫn giải mã được”.

| Operation | Active đúng purpose/IAM | Suspended mặc định | Ngoại lệ hoặc lưu ý |
|---|---|---|---|
| **Encrypt với DEK/KEK được quản lý** | Cho phép | **Chặn** | Có thể chuyển sang key version mới |
| **Decrypt bằng DEK/KEK được quản lý** | Cho phép | **Chặn** | Recovery decrypt-only chỉ khi policy/phê duyệt và KMS hỗ trợ |
| **Wrap/Unwrap DEK** | Cho phép theo purpose | **Chặn** | Kế hoạch rewrap/migration phải có đường quyền riêng |
| **Sign bằng private key** | Cho phép | **Chặn** | Không phát hành chữ ký mới từ khóa đang điều tra |
| **GenerateMac bằng HMAC key** | Cho phép | **Chặn** | Dừng tạo MAC mới, chuyển version nếu cần |
| **VerifyMac trong KMS bằng HMAC key** | Cho phép | **Chặn** | Verification lịch sử cần đường chính sách riêng nếu có |
| **DeriveKey từ root secret** | Cho phép theo scope | **Chặn** | Key con đã xuất/cached không tự bị vô hiệu |
| **ECDH/KeyAgreement bằng private key** | Cho phép | **Chặn** | Session đã thiết lập có thể tiếp tục hoạt động nếu chưa bị kết thúc |
| **Verify chữ ký bằng public key** | Cho phép nếu trust hợp lệ | **Không tự bị chặn bởi private key state** | Phải kiểm tra trust/certificate status và policy của verifier |
| **Mã hóa bằng public key công khai** | Cho phép nếu public key được tin cậy | **Không tự bị chặn ở bên gửi offline** | Phải ngừng công bố/chấp nhận key version theo policy; có rủi ro tạo ciphertext không giải mã được |

**Phân biệt hai câu hỏi:** (1) *Thiết bị có còn cho gọi phép toán không?* và (2) *Nghiệp vụ có còn tin kết quả đó không?* Một thiết bị có thể chặn **Sign**, nhưng chứng thư public key vẫn chưa bị thu hồi. Một verifier có thể tiếp tục Verify chữ ký cũ, nhưng chính sách có thể không cho **chấp nhận** chữ ký tạo sau thời điểm khóa được xác định bị lộ.

### 3.1. Chính sách “read/decrypt-only” khi Suspend

Một số hệ thống có nhu cầu giữ khả năng đọc dữ liệu đã mã hóa trong khi dừng tạo bản mã mới. Điều này **không nhất thiết** nên được biểu diễn bằng Suspended:

- Nếu khóa **hết hạn sử dụng cho mã hóa mới nhưng vẫn đáng tin để đọc bản mã cũ**, một trạng thái **Deactivated/Retired/Decrypt-only** có thể diễn đạt rõ hơn.
- Nếu khóa **đang bị nghi lộ**, cho phép **Decrypt** rộng rãi có thể tăng thiệt hại và che giấu lạm dụng. Nên hạn chế hoặc dừng theo runbook.
- Nếu phải khôi phục có kiểm soát, dùng **break-glass authorization**, mục đích và thời hạn cụ thể, hai người phê duyệt hoặc công cụ migration riêng nếu policy yêu cầu.

Không tự đặt **allowDecryptWhenSuspended=true** trong ứng dụng rồi coi đó là bảo đảm của KMS. Phải kiểm tra sản phẩm có hỗ trợ hay không và **mọi đường gọi trực tiếp** đều đi qua enforcement tương ứng.

## 4. Khi nào nên Suspend?

### 4.1. Các tình huống điển hình

| Tình huống | Vì sao Suspend có thể phù hợp? | Bước tiếp theo |
|---|---|---|
| **Nghi service account bị chiếm quyền** | Chặn ký/giải mã hoặc cấp khóa mới trong thời gian điều tra | Thu hồi credential, audit, đánh giá có cần rotate hay không |
| **Key usage tăng đột biến** | Giảm thiểu sự cố có thể xảy ra trước khi rõ nguyên nhân | Xem log caller, request, tenant, policy, workload |
| **Sai cấu hình IAM/KMS policy** | Chặn tạm khi sửa quyền sử dụng quá rộng | Kiểm thử deny/allow sau sửa và phê duyệt reactivation |
| **Chờ phê duyệt hoặc tuân thủ** | Ngăn thao tác khi điều kiện quản trị chưa thỏa | Hoàn tất approval, ghi nhận lý do và thời hạn |
| **Dừng dịch vụ hoặc bảo trì HSM có kế hoạch** | Ngăn gọi trong khoảng chuyển đổi nếu cần | Phối hợp traffic, failover và đường phục hồi |
| **Nghi ngờ RNG/nonce issue** | Ngừng cấp key mới hoặc phép mã hóa có thể không an toàn | Khoanh vùng, thay key/nonce strategy, re-encrypt nếu cần |
| **Yêu cầu pháp lý/điều tra nội bộ** | Tạm bảo toàn key material và chứng cứ, chặn thao tác mới | Xác lập quyền, retention, sự kiện kết thúc và phê duyệt |

**Không phải mọi outage đều là suspended state.** Nếu KMS không truy cập được do mạng, dịch vụ có thể thất bại khi dùng khóa dù metadata vẫn là Active. Hãy phân biệt **operational unavailability** với quyết định quản trị **suspend** để tránh báo cáo và cơ chế recovery sai.

### 4.2. Suspend không dùng để che một compromise đã xác nhận

Khi có chứng cứ private key hoặc root/DEK đã bị lộ, **tạm đình chỉ** có thể là thao tác khẩn cấp đầu tiên, nhưng không được coi đó là trạng thái cuối cùng:

1. Chặn quyền sử dụng khóa và credential liên quan ngay khi có cơ sở.
2. Khoanh vùng khóa/phiên bản, nguồn lộ, thời điểm, ciphertext/chữ ký/derived keys bị ảnh hưởng.
3. Tạo **khóa thay thế từ nguồn an toàn**, kiểm tra public key trust và các hệ thống phụ thuộc.
4. Thực hiện **rotate, revoke, re-encrypt, rewrap, token/session revocation** khi thích hợp.
5. Chuyển khóa cũ sang trạng thái phù hợp với policy rủi ro; không đơn giản “resume” khóa đã được xác nhận compromised.

Nếu DEK đã bị lộ, chỉ **rewrap cùng DEK** dưới KEK mới không sửa được việc dữ liệu cũ có thể bị giải mã. Nếu private signing key bị lộ, tắt API Sign **không xóa được các bản private key đã bị sao chép ra ngoài** và không tự ngăn tạo chữ ký offline.

## 5. Trạng thái chuyển đổi và điều kiện khôi phục

### 5.1. Active → Suspended

Yêu cầu chuyển trạng thái nên chứa:

- **Key ID và version cụ thể**, không chỉ alias có thể trỏ sang khóa khác.
- **Actor** đã xác thực, quyền **SuspendKey**, nguồn phê duyệt hoặc ticket.
- **Reason code** có cấu trúc: SUSPECTED_COMPROMISE, POLICY_VIOLATION, MAINTENANCE, COMPLIANCE_HOLD…
- **Time, expiry/review deadline**, phạm vi tenant/workload và kế hoạch thông báo.
- **Policy revision / event ID** để xử lý đồng thời, retry và điều tra.

Quy trình khái quát:

~~~mermaid
sequenceDiagram
    participant SOC as Security/Ops
    participant KM as Key Management Control Plane
    participant KMS as KMS/HSM
    participant APP as Workload
    participant AUD as Audit
    SOC->>KM: Suspend(keyId, version, reason, ticket)
    KM->>KM: Authenticate + authorize + validate state
    KM->>KMS: Chặn thao tác theo policy/provider
    KMS-->>KM: Xác nhận hoặc lỗi rõ ràng
    KM->>AUD: State transition, actor, revision, result
    KM-->>SOC: Kết quả + effective scope
    APP->>KMS: Sign/Decrypt/Unwrap theo key reference
    KMS-->>APP: Denied nếu đình chỉ đã có hiệu lực
~~~

**Không tuyên bố đình chỉ thành công chỉ vì UI/API quản trị nhận request.** Cần hiểu khi nào quyết định có hiệu lực ở **data plane**, các vùng/replica nào đã áp dụng, thao tác đang chạy có bị chặn không và cách xác minh.

### 5.2. Suspended → Active (reactivation)

Việc mở lại khóa phải là một **quyết định mới được kiểm soát**, không phải tự bỏ cờ sau thời hạn:

1. Xác minh nguyên nhân suspend đã được xử lý và **không có bằng chứng khóa bị lộ** theo tiêu chí được chấp thuận.
2. Thu hồi/sửa credential, IAM, key policy, cấu hình nguồn RNG và workload nếu nguyên nhân liên quan.
3. Kiểm tra trạng thái thực trên KMS/HSM, key version, cryptoperiod, mục đích và các chính sách tin cậy.
4. Đánh giá ảnh hưởng tới ciphertext, token, chữ ký và phiên đang hoạt động.
5. Có approval phù hợp, có thể cần **separation of duties** hoặc hai người phê duyệt.
6. Đổi state bằng phép cập nhật có kiểm tra revision, ghi audit và kiểm thử thực tế **allowed/denied operations**.
7. Khôi phục traffic theo rollout có giám sát, hạn mức và điều kiện rollback.

**Không re-activate một khóa đã được xác định compromised chỉ bằng thao tác đổi state.** Khi bản chất key material không còn đáng tin, giải pháp thường là **khóa mới**, còn khóa cũ tiếp tục bị hạn chế, được xử lý theo yêu cầu điều tra/lưu trữ và cuối cùng hủy.

### 5.3. Suspended → Retired/Compromised/Destroyed

Đình chỉ kéo dài không có nghĩa khóa có thể bị xóa ngay. Trước khi retire/destroy:

- Kiểm tra có ciphertext cũ cần **Decrypt**, **Unwrap**, hoặc dữ liệu backup chưa chuyển đổi không.
- Kiểm tra có public-key signature cần xác minh trong thời gian lưu trữ không.
- Đối chiếu khóa còn trong **KMS alias, HSM partition, backup, replica, key cache** hay không.
- Xác định cần **rewrap DEK, re-encrypt payload**, chuyển khóa ký hay cập nhật trust store/JWKS.
- Phê duyệt kế hoạch hủy và bằng chứng thực thi, không bỏ qua legal hold hoặc retention policy.

## 6. Suspended state trong hệ thống phân tán

Một trạng thái trên database không thể ngay lập tức điều khiển mọi instance nếu **quyền kiểm soát thực tế** nằm ở cache hoặc ở dịch vụ khác.

### 6.1. Những vùng có thể vẫn sử dụng khóa cũ

| Nơi giữ key hoặc quyền | Rủi ro khi Suspend | Cách kiểm soát |
|---|---|---|
| **KMS/HSM trực tiếp** | Một số API/region chưa áp dụng state hoặc có in-flight request | Hiểu consistency/provider contract, xác minh data plane |
| **Plaintext DEK cache trong JVM** | Ứng dụng tiếp tục AES-GCM không cần gọi KMS | TTL ngắn, invalidation, giới hạn phạm vi, dừng workload khi cần |
| **Key handle/session trong HSM** | Session đang mở có thể có đặc tính riêng | Kiểm tra chính sách revoke/close session, vendor semantics |
| **Private key file ngoài KMS** | Có thể dùng offline dù KMS “suspend” alias | Quản lý bản sao/export, OS IAM, rotate key và revoke trust |
| **Public key ở verifier** | Verify chữ ký cũ vẫn chạy offline | Chính sách chấp nhận, certificate status, key registry, timestamp |
| **Public encryption key ở đối tác** | Tiếp tục mã hóa DEK cho public key cũ | Ngừng công bố/chấp nhận version, thông báo và migration |
| **Session key đã dẫn xuất** | Kết nối/phiên đang tồn tại có thể tiếp tục | Revoke session/credential, TTL, reset session theo threat model |
| **Batch job/queue** | Job đang chạy hoặc đã lấy DEK trước thời điểm chặn | Check state tại enforcement point, cancel/pause, kiểm tra kết quả |

### 6.2. Race condition giữa kiểm tra state và dùng khóa

Đoạn code sau không đủ an toàn nếu state và operation không được liên kết:

~~~java
if (keyRepository.isActive(keyId)) {
    // Sau thời điểm check, Ops có thể chuyển key sang SUSPENDED.
    cipher.encryptWithCachedKey(plaintext);
}
~~~

Đây là vấn đề **time-of-check/time-of-use (TOCTOU)**. Nếu **Cryptographic Operation** thực hiện trong KMS/HSM, nơi kiểm tra trạng thái có thể nằm cùng ranh giới kiểm soát với phép toán theo thiết kế provider. Nếu dùng local DEK đã xuất, state của KMS **không tự chặn được phép mã hóa diễn ra trong JVM**.

Các biện pháp phụ thuộc mức yêu cầu:

1. **Enforcement tại nơi sử dụng material:** policy ở KMS/HSM hoặc crypto gateway bắt buộc.
2. **Bounded cache/lease:** cấp key-use lease với TTL và khả năng revoke được định nghĩa, hiểu rõ cửa sổ hiệu lực còn lại.
3. **Version/revision checks:** không tin một state copy quá cũ, có cơ chế invalidation và fail-closed theo rủi ro.
4. **Quy trình khẩn cấp:** chặn traffic, dừng worker hoặc thu hồi credential/session nếu không thể chặn khóa đã xuất.
5. **Audit các thao tác in-flight:** ghi nhận operation hoàn thành sau thời điểm nhận yêu cầu đình chỉ và đánh giá ảnh hưởng.

**Strong consistency của một metadata store không sửa được việc key bytes đã rời khỏi store.** Chính sách phải định nghĩa rõ suspended state ràng buộc tới đâu và thời điểm nào, tránh tạo lời hứa “ngay tức thì trên toàn hệ thống” khi kiến trúc không thể đáp ứng.

### 6.3. Multi-region, retry và event ordering

Nếu control plane phát **KeySuspended(keyId, version, revision=42)** qua event bus, các consumer cần:

- Áp dụng state theo **revision tăng đơn điệu** để không nhận event **KeyActivated(revision=41)** đến muộn rồi vô tình mở lại.
- Xử lý duplicate event idempotent và kiểm tra signature/authentication của event nguồn nếu giao thức có yêu cầu.
- Chặn fail-open khi không thể lấy trạng thái mới mà chính sách bắt buộc phải xác nhận trước mỗi operation.
- Theo dõi region nào đã xác nhận policy revision và vận hành có giới hạn trong khi propagation chưa hoàn tất.
- Không dùng thay đổi **alias** để né việc xử lý key version đang đình chỉ.

Khả năng chặn thao tác ở region khác, API đã cấp phép và worker đang xử lý phải được ghi cụ thể trong **runbook**, không chỉ vẽ một sơ đồ state machine.

## 7. Ảnh hưởng tới envelope encryption, DEK và KEK

Trong **envelope encryption**, một **DEK (Data Encryption Key)** dùng để mã hóa dữ liệu, thường bằng **AES-GCM**; một **KEK (Key Encryption Key)** bảo vệ DEK thông qua cơ chế **wrap/unwrap**. KEK có thể nằm trong KMS/HSM. Việc suspend **KEK** và suspend **DEK** ảnh hưởng khác nhau.

~~~mermaid
sequenceDiagram
    participant App as Java Service
    participant KMS as KMS/HSM giữ KEK
    participant DB as Database
    App->>KMS: GenerateDataKey/WrapDEK với KEK-v3
    KMS-->>App: DEK tạm + wrapped DEK
    App->>App: AES-GCM Encrypt(plaintext, DEK, nonce, AAD)
    App->>DB: ciphertext+tag, nonce, wrapped DEK, keyRef
    Note over KMS: Security chuyển KEK-v3 sang Suspended
    App->>DB: Đọc ciphertext cũ
    DB-->>App: wrapped DEK + ciphertext metadata
    App->>KMS: Unwrap/Decrypt(wrapped DEK, KEK-v3)
    KMS-->>App: Denied theo suspended policy
    Note over App: Không tự fallback sang plaintext hoặc khóa khác
~~~

**Chú ý:** Đây là một luồng minh họa cho KMS có thao tác **GenerateDataKey/Decrypt** theo ngữ nghĩa tương ứng; các nhà cung cấp khác nhau về loại key, payload và tính năng. Không suy ra một KMS cụ thể luôn có trạng thái Suspended riêng hoặc luôn chặn cùng bộ API.

### 7.1. Khi KEK bị Suspended

- Nếu KMS **chặn Unwrap/Decrypt** cho KEK-v3, dịch vụ có thể **không mở được wrapped DEK** của bản ghi cũ, dù AES-GCM ciphertext/tag vẫn nguyên vẹn.
- Nếu một workload đã giữ **plaintext DEK trong cache**, nó có thể tiếp tục giải mã trong một khoảng thời gian mà không gọi KMS; chính sách suspend ở KMS đơn lẻ không chặn được cache.
- Nếu có KEK-v4 đã kích hoạt, **bản ghi cũ không tự chuyển sang v4** chỉ vì alias thay đổi. Cần rewrap bằng quy trình được phép hoặc giữ đường khôi phục phù hợp.
- Nếu key version v3 đang bị nghi **compromised**, mở lại v3 để phục vụ di chuyển dữ liệu có thể trái chính sách. Phải dùng **quy trình recovery có phê duyệt**, giới hạn scope và audit.

### 7.2. Khi DEK bị Suspended

Nếu DEK được quản lý như key handle trong crypto service, có thể chặn trực tiếp Encrypt/Decrypt theo key ID. Nhưng nếu DEK đã được xuất dưới dạng **byte[] hoặc SecretKeySpec** trong Java, KMS không thể trực tiếp ngăn JVM sử dụng những bytes đó. Muốn bảo đảm ngừng dùng DEK, phải quản lý nơi giữ DEK, cache TTL, workload credentials, session và quyền truy cập bản mã.

Trong AES-GCM, **nonce phải không trùng với cùng DEK**. Suspended không làm **reset nonce history** và không cho phép dùng lại một nonce cũ khi sau này tái kích hoạt. Cần giữ giới hạn số lần mã hóa và state của bộ cấp nonce xuyên restart/rotation.

### 7.3. Suspend, rotate và rewrap không giống nhau

| Thao tác | Key material nào thay đổi? | Dữ liệu AES-GCM cũ |
|---|---|---|
| **Suspend KEK** | Thường không đổi material, đổi quyền/trạng thái | Có thể bị chặn đường unwrap DEK |
| **Reactivate KEK** | Thường không đổi material | Có thể khôi phục unwrap nếu trust và policy cho phép |
| **Rotate KEK** | Tạo hoặc chuyển sang KEK mới | Có thể rewrap **cùng DEK**, bản mã payload không đổi |
| **Rotate DEK** | Tạo DEK mới | Dữ liệu cũ muốn dùng DEK mới cần re-encrypt |
| **Revoke quyền sử dụng** | Có thể không đổi key | Chặn caller theo IAM; cached DEK có thể còn |
| **Destroy KEK/DEK** | Hủy material theo contract | Có thể mất vĩnh viễn khả năng đọc dữ liệu nếu không có đường khôi phục khác |

Một **DEK đã bị lộ** không trở nên bí mật trở lại khi KEK được rewrap. Cần đánh giá thay DEK, mã hóa lại payload, điều tra những bản mã đã bị thu thập và xử lý cả bản sao/backup theo threat model.

## 8. Ảnh hưởng tới chữ ký số, public key và PKI

Khóa ký có hai thành phần: **private signing key** dùng **Sign**, còn **public verification key** dùng **Verify**. Suspended state thường nhắm đến khả năng sử dụng **private key** trong một ranh giới quản lý, không khiến public key đã phát hành biến mất.

### 8.1. Dừng Sign mới khác với ngừng tin chữ ký cũ

Ví dụ **auth-sign-v4** được dùng để ký JWT:

1. Nhóm an ninh chuyển private key **auth-sign-v4** sang Suspended tại KMS.
2. Auth Service phải **ngừng phát token mới bằng v4**; có thể chuyển sang v5 đã chuẩn bị nếu policy cho phép.
3. API Gateway có thể vẫn có **public key v4** trong JWKS cache và vẫn Verify được token v4.
4. Nếu v4 chỉ tạm ngừng vì bảo trì, token v4 còn hiệu lực có thể tiếp tục được chấp nhận **theo policy**.
5. Nếu v4 nghi bị lộ, cần cân nhắc **thu hồi phiên/token, loại bỏ hoặc thay đổi trust**, thời gian chấp nhận key v4 và phạm vi sự cố; không chỉ tin việc KMS đã chặn Sign.

**kid** trong JWT chỉ là gợi ý chọn khóa trong tập key **đã được xác thực**. Không cho phép token tùy ý cung cấp URL public key hoặc thuật toán để né trạng thái đã quyết định. JWT được **ký** không tự có tính bí mật payload; khi cần giữ bí mật phải dùng cơ chế mã hóa phù hợp.

### 8.2. Certificate revocation là một cơ chế khác

**Suspend private key tại KMS** và **thu hồi chứng thư X.509** không phải cùng một thao tác:

| Hành động | Bề mặt tác động |
|---|---|
| Suspend key trong KMS/HSM | Các operation đi qua key service theo contract |
| Revoke certificate bằng cơ chế PKI | Quyết định tin cậy của những verifier kiểm tra trạng thái chứng thư |
| Xóa hoặc rotate JWKS key | Khả năng chọn key tại những verifier dùng JWKS, chịu ảnh hưởng cache |
| Rotate private signing key | Chữ ký mới dùng key pair/version mới |
| Thu hồi session hoặc token | Quyền thực hiện nghiệp vụ của credential đã phát |

Một chứng thư có thể đã bị thu hồi nhưng verifier **không kiểm tra trạng thái thu hồi** vẫn chấp nhận chữ ký theo các bước verify đơn giản. Ngược lại, một private key có thể bị Suspended vì lý do vận hành mà **không có căn cứ thu hồi danh tính/chứng thư**. Quy trình an ninh phải phối hợp các lớp theo tình huống.

### 8.3. Tài liệu ký dài hạn

Tài liệu điện tử cần xác minh sau nhiều năm có thể yêu cầu lưu **certificate chain, timestamp đáng tin, thông tin trạng thái thu hồi tại mốc phù hợp, thuật toán và chứng cứ liên quan**. Chỉ giữ public key và chạy phép Verify không tự giải quyết yêu cầu pháp lý hoặc khả năng tin cậy chữ ký lịch sử. Suspended state ở thời điểm hiện tại **không tự chứng minh** mọi chữ ký lịch sử hợp lệ hoặc vô hiệu.

## 9. Suspended với HMAC, KDF và khóa thỏa thuận

### 9.1. HMAC key

Một **HMAC key** đang Suspended thường cần chặn **GenerateMac** mới. Việc **VerifyMac** với thông điệp lịch sử có thể bị chặn hoàn toàn hoặc có đường xử lý riêng tùy policy. Nếu người nhận tự giữ bản sao HMAC key, họ vẫn có thể tính MAC offline dù KMS đã suspend bản chính.

HMAC tag không phải chữ ký số bất đối xứng: cả bên gửi và bên nhận cùng biết khóa bí mật đều có khả năng tạo tag. Chống phát lại cần **timestamp, message ID, expiry, idempotency**, không có sẵn trong HMAC hay trạng thái khóa.

### 9.2. KDF root key, PRK và derived keys

Một hệ thống dùng **HKDF** có thể dẫn xuất nhiều key từ root secret:

~~~text
root-v3 (IKM) --> HKDF-Extract --> PRK
    |
    +--> HKDF-Expand(info=tenant-42/DATA_ENCRYPTION) --> DEK-A
    |
    +--> HKDF-Expand(info=tenant-42/REQUEST_MAC) --> MAC-A
~~~

Nếu suspend **root-v3** trong derivation service:

- Có thể chặn **DeriveKey mới** qua API quản lý.
- Những **PRK, OKM hoặc DEK đã nằm trong cache** vẫn tồn tại, chưa chắc bị vô hiệu.
- Việc xóa một derived key trong tiến trình không đảm bảo crypto-erasure nếu root và info vẫn cho phép **tái dẫn xuất**.
- Nếu root bị lộ, chỉ đổi nhãn **info** không cứu được các derived keys tiếp theo. Cần thay **root secret** và xử lý những nhánh bị ảnh hưởng.

Salt và info của HKDF thường không cần giữ bí mật; chúng cần được tái tạo đúng và được xác thực trong ngữ cảnh. Khi rotate root hoặc thay derivation version, dữ liệu dùng derived key cũ **không tự chuyển đổi**.

### 9.3. Key agreement và session key

Khi private key dùng cho ECDH/X25519 bị Suspended, hệ thống nên ngừng **thiết lập phiên mới** bằng key đó theo policy. Nhưng các **session key đã dẫn xuất** có thể tiếp tục hoạt động cho đến khi phiên bị kết thúc hoặc bị thu hồi. Nếu nghi ngờ private key/credential đã bị lộ, có thể cần **terminate sessions, revoke tokens và đánh giá tính an toàn phiên lịch sử** tùy thiết kế giao thức, ephemeral key handling và forward secrecy.

Không cho rằng HKDF hay TLS tự kế thừa trạng thái **Suspended** của một khóa quản trị: state ở control plane và khả năng sử dụng session key trong data plane là hai vấn đề riêng.

## 10. Thiết kế policy state-machine trong Java 17

Ví dụ sau mô hình hóa quyết định **fail-closed**: khi một key record ở **SUSPENDED**, ứng dụng từ chối mọi thao tác sử dụng **secret key/private key** trong danh sách quản lý. Mỗi transition tăng **revision** và dùng **compare-and-set** để tránh ghi đè trạng thái đồng thời trong **một JVM**. Đây là **mô hình giảng dạy**, không phải KMS hoặc hệ thống phân tán hoàn chỉnh.

~~~java
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

public final class SuspendedKeyPolicyDemo {
    enum State {
        PRE_ACTIVE, ACTIVE, SUSPENDED,
        DEACTIVATED, COMPROMISED, DESTROYED
    }

    enum Operation {
        ENCRYPT, DECRYPT, SIGN, WRAP, UNWRAP,
        GENERATE_MAC, VERIFY_MAC, DERIVE_KEY
    }

    // Key ID, version và revision đều là metadata, không phải raw key.
    record KeyRecord(
            String keyId,
            int keyVersion,
            State state,
            Set<Operation> allowedPurposes,
            long revision
    ) {
        KeyRecord {
            allowedPurposes = Set.copyOf(allowedPurposes);
        }
    }

    record Decision(boolean allowed, String reason, long revision) {}

    static final class Gate {
        private final AtomicReference<KeyRecord> current;

        Gate(KeyRecord initial) {
            current = new AtomicReference<>(initial);
        }

        Decision authorize(
                Operation operation,
                boolean principalAuthorized,
                boolean tenantAuthorized) {
            KeyRecord key = current.get();
            if (!principalAuthorized || !tenantAuthorized) {
                return new Decision(false, "IAM_OR_TENANT_DENIED",
                        key.revision());
            }
            if (key.state() != State.ACTIVE) {
                return new Decision(false, "KEY_NOT_ACTIVE",
                        key.revision());
            }
            if (!key.allowedPurposes().contains(operation)) {
                return new Decision(false, "PURPOSE_DENIED",
                        key.revision());
            }
            return new Decision(true, "ALLOW", key.revision());
        }

        // Quyền quản trị, xác thực actor và audit bền vững
        // phải được thực thi bởi control plane bên ngoài demo.
        KeyRecord suspend(String actor, String ticket) {
            if (actor.isBlank() || ticket.isBlank()) {
                throw new IllegalArgumentException("Missing audit context");
            }
            return transition(State.ACTIVE, State.SUSPENDED);
        }

        KeyRecord reactivate(String actor, String ticket,
                             boolean securityReviewApproved) {
            if (actor.isBlank() || ticket.isBlank()
                    || !securityReviewApproved) {
                throw new SecurityException("Approval is required");
            }
            return transition(State.SUSPENDED, State.ACTIVE);
        }

        private KeyRecord transition(State expected, State target) {
            for (;;) {
                KeyRecord old = current.get();
                if (old.state() != expected) {
                    throw new IllegalStateException(
                            "Invalid transition from " + old.state());
                }
                KeyRecord next = new KeyRecord(
                        old.keyId(), old.keyVersion(), target,
                        old.allowedPurposes(), old.revision() + 1);
                if (current.compareAndSet(old, next)) {
                    return next;
                }
            }
        }
    }

    public static void main(String[] args) {
        KeyRecord key = new KeyRecord(
                "billing-sign-key", 3, State.ACTIVE,
                Set.of(Operation.SIGN), 7L);
        Gate gate = new Gate(key);

        System.out.println("Sign before suspend: "
                + gate.authorize(Operation.SIGN, true, true).allowed());
        System.out.println("Decrypt on sign-only key: "
                + gate.authorize(Operation.DECRYPT, true, true).allowed());

        KeyRecord suspended = gate.suspend("security-operator", "INC-123");
        System.out.println("State after suspend: " + suspended.state());
        System.out.println("Sign while suspended: "
                + gate.authorize(Operation.SIGN, true, true).allowed());

        try {
            gate.reactivate("security-operator", "INC-123", false);
            throw new AssertionError("Approval should be required");
        } catch (SecurityException expected) {
            System.out.println("Reactivation without approval rejected");
        }

        KeyRecord active = gate.reactivate(
                "security-operator", "INC-123", true);
        System.out.println("State after approved review: " + active.state());
        System.out.println("Sign after approved review: "
                + gate.authorize(Operation.SIGN, true, true).allowed());
        // Đây chỉ là policy demo; không có phép ký thật hay IAM thật.
    }
}
~~~

Lưu thành **SuspendedKeyPolicyDemo.java**, sau đó chạy với JDK 17+:

~~~bash
javac SuspendedKeyPolicyDemo.java
java SuspendedKeyPolicyDemo
~~~

Kết quả mong đợi:

~~~text
Sign before suspend: true
Decrypt on sign-only key: false
State after suspend: SUSPENDED
Sign while suspended: false
Reactivation without approval rejected
State after approved review: ACTIVE
Sign after approved review: true
~~~

### 10.1. Vì sao demo chưa đủ cho production?

1. **Chỉ dùng AtomicReference trong một JVM.** Nó không đồng bộ với node khác, HSM, KMS hay plaintext key đã được xuất.
2. **Kiểm tra trước operation chưa atomic với operation.** Có thể xảy ra race giữa **authorize** và lệnh **Sign** thực tế. Nên đặt enforcement tại điểm thực hiện mật mã hoặc dùng cơ chế lease/revision có contract rõ.
3. **Các boolean IAM/tenant là dữ liệu giả lập.** Production phải xác thực identity, kiểm tra quyền theo key ID/version, purpose, tenant và môi trường.
4. **Tham số securityReviewApproved chỉ là minh họa.** Nó không thay thế workflow phê duyệt, bằng chứng điều tra hoặc separation of duties.
5. **Không có trạng thái lỗi provider hoặc propagation.** Phải xử lý failure, consistency, retry, timeout và in-flight operation theo KMS/HSM thực tế.
6. **Chưa quản lý key material.** Record không chứa private key hay DEK và không thực hiện cryptographic operation; mọi material cần giữ trong kho được bảo vệ.
7. **Không có audit bền vững.** Production phải lưu actor, reason/ticket, key version, policy revision, quyết định và effective time ở hệ thống kiểm toán được kiểm soát.
8. **Không phải mọi operation đều cùng policy.** Verification bằng public key có thể thực hiện ngoài KMS; deactivated có thể có decrypt-only, còn compromised thường không được reactivate.

Điểm đúng của ví dụ là tư duy **deny theo state trước khi cho phép purpose/IAM**, **version hóa policy**, và **chỉ có transition hợp lệ**. Các bảo đảm về thời điểm đình chỉ, tính đồng bộ và độ tin cậy phải đến từ kiến trúc control plane/data plane thực.

## 11. Kiểm thử Suspended state đúng cách

### 11.1. Bảng test theo state và operation

| Test case | Mong đợi | Ý nghĩa |
|---|---|---|
| ACTIVE + đúng caller/tenant/purpose + Sign | **ALLOW** | Đường hoạt động chuẩn |
| ACTIVE + caller thiếu quyền + Sign | **DENY** | State không bỏ qua IAM |
| ACTIVE + key chỉ Sign + Decrypt | **DENY** | State không bỏ qua purpose |
| SUSPENDED + Sign/Encrypt/Wrap | **DENY** | Chặn phát sinh output bảo mật mới theo policy |
| SUSPENDED + Decrypt/Unwrap/DeriveKey | **DENY mặc định** | Recovery nếu cần phải đi đường riêng được kiểm soát |
| SUSPENDED + Verify bằng public key offline | **Phụ thuộc verifier trust policy** | Không suy luận từ API private key |
| SUSPENDED + request reactivation thiếu approval | **DENY** | Không mở khóa chỉ vì hết hạn timer |
| COMPROMISED + request reactivation | **DENY** | Không xem compromise là bảo trì |
| DESTROYED + mọi secret-key operation | **DENY** | Không có material để dùng theo thiết kế |
| Event ACTIVE revision 41 đến sau SUSPENDED revision 42 | **Không ghi đè về ACTIVE** | Chống stale event |
| KMS unavailable trong lúc check state | **Fail theo policy; không tự ALLOW** | Chặn fail-open ngoài ý muốn |
| Cipher/Sign request bắt đầu trước suspension | **Có hành vi được định nghĩa và audit** | Kiểm soát in-flight race |

Các bài test phải kiểm tra **hành vi thực** chứ không chỉ giá trị field trong database. Ví dụ: sau khi xác nhận suspend một key ID cụ thể, cố gọi KMS **Sign/Decrypt** bằng một workload có quyền trước đó trong môi trường thử an toàn. Không dùng khóa production hoặc lộ raw key material chỉ để chứng minh policy.

### 11.2. Test với cache, alias và distributed clients

- **Cached DEK:** dịch vụ đã lấy DEK rồi mới nhận lệnh suspend; kiểm tra thời hạn cache, khả năng dừng workload và tác động thực tế.
- **Key alias:** alias trỏ từ v3 sang v4; kiểm tra client giữ **version v3** có bị chặn đúng, không có bypass qua alias cũ.
- **Multi-region:** kiểm tra thời điểm state có hiệu lực và báo cáo replication lag theo contract của nhà cung cấp.
- **In-flight batch:** một job đang giải mã nhiều đối tượng phải có cơ chế pause/cancel theo chính sách hoặc ghi audit đầy đủ.
- **State revision:** event cũ không được “đánh thức” key sau event suspend mới.
- **Recovery:** không thể reactivate nếu approval thiếu, đã hết cryptoperiod hoặc key bị đánh dấu compromised.
- **Audit:** test log có đủ **key ID/version, actor, reason, timestamp, decision**, không rò DEK/private key/PII.

### 11.3. Tránh những test sai

Không có cơ sở khi viết test kiểu “YAML ghi SUSPENDED nên mọi ciphertext cũ không thể giải mã được”. Với cache DEK, plaintext key ngoài KMS, hoặc private key nằm trên máy khác, điều đó có thể sai. Cũng không nên test bằng cách hủy một khóa production để kiểm tra khả năng chặn; destruction thường là hành động không đảo ngược và cần quy trình riêng.

## 12. Runbook phản ứng khi cần tạm đình chỉ khóa

Một runbook nên có **owner, thông số key reference, giới hạn tác động, điều kiện kích hoạt, thẩm quyền phê duyệt, kiểm thử và tiêu chí kết thúc**.

### 12.1. Trước khi suspend

1. **Định danh khóa:** xác nhận key ID, version, thuật toán, owner, mục đích, môi trường và tenant. Không thao tác mơ hồ qua alias nếu có nhiều version.
2. **Xác định sự cố:** lý do suspend, bằng chứng, risk level, incident/ticket ID và tác động dự kiến.
3. **Rà soát phụ thuộc:** service nào gọi **Encrypt/Decrypt/Sign/Unwrap/DeriveKey**, job nào chạy, cache nào giữ key.
4. **Chuẩn bị fallback an toàn:** có key version thay thế đã được kiểm tra, queue/retry hay chế độ read-only phù hợp không? Không fallback sang plaintext, khóa mặc định hoặc thuật toán yếu.
5. **Phê duyệt theo policy:** trong sự cố khẩn cấp có thể cho security role suspend ngay, còn reactivation cần quy trình chặt hơn.

### 12.2. Khi thực hiện

1. **Gửi lệnh suspend** qua control plane đáng tin cậy hoặc cập nhật policy ở điểm thực thi theo nhà cung cấp.
2. **Ghi audit** actor, keyRef/version, reason, ticket, effective time, policy revision và kết quả.
3. **Xác minh data plane:** thử một thao tác hợp lệ trước đây ở môi trường/đường kiểm tra an toàn, bảo đảm nhận kết quả denied theo kỳ vọng.
4. **Giảm exposure ngoài KMS:** đánh giá cached DEK, session key, export, background jobs, token, key handles và IAM.
5. **Theo dõi lỗi nghiệp vụ:** hàng đợi, request timeout, failed decrypt, failed signing, key alias, phiên còn mở và các region chưa cập nhật.

### 12.3. Sau khi suspend

1. **Điều tra:** xác định khóa bị lộ thật hay chỉ lỗi cấu hình/vận hành; khoanh vùng thời gian và thao tác bất thường.
2. **Quyết định nhánh xử lý:** reactivate có phê duyệt, migrate/retire hoặc đánh dấu compromised và thay khóa.
3. **Nếu migrate:** xác định cần **rewrap** hay **re-encrypt**, dữ liệu cũ có thể khôi phục ra sao và khi nào được hủy khóa.
4. **Nếu reactivate:** kiểm tra điều kiện an toàn, policy, key purpose/cryptoperiod, approval và cập nhật toàn bộ enforcement points.
5. **Lưu chứng cứ:** audit logs, key-state transitions, quyết định và bài kiểm tra; không lưu raw secret vào ticket.

### 12.4. Ma trận quyết định nhanh

| Kết quả điều tra | Quyết định gợi ý | Điều không được làm |
|---|---|---|
| Lỗi cấu hình đã sửa, không có dấu hiệu lộ key, policy cho phép | Review và **reactivate** | Mở trước khi xác minh enforcement và IAM |
| Đến hạn retirement, key material vẫn đáng tin | Chuyển sang **deactivated/decrypt-only** nếu thiết kế hỗ trợ | Coi đó là sự cố compromise |
| Chưa rõ có lộ khóa, rủi ro còn lớn | Tiếp tục **suspended**, thu hẹp quyền, điều tra/rotate | Resume chỉ để hết cảnh báo |
| Xác nhận private key/DEK/KEK bị lộ | Xử lý **compromised**, revoke/replace, migrate dữ liệu | Chỉ chuyển từ Suspended về Active |
| Dữ liệu cũ vẫn cần key để khôi phục | Lập kế hoạch **recovery/migration** có phê duyệt | Destroy ngay khi chưa thử restore |
| Không còn phụ thuộc, retention và approval đủ | Hủy theo **key destruction process** | Nhầm xóa alias/UI record với hủy toàn bộ key material |

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ đổi cột **status=SUSPENDED** trong database | KMS/HSM vẫn cho phép operation | Chặn tại enforcement point, xác minh data plane |
| Đánh đồng **Suspended** với **Destroyed** | Kỳ vọng sai về khả năng khôi phục và key material còn lại | Phân biệt lifecycle state với hủy material |
| Nghĩ suspend private key làm mọi chữ ký cũ vô hiệu | Verifier offline vẫn có public key và signature hợp lệ toán học | Thiết kế trust, certificate revocation và chính sách thời gian |
| Cho **Decrypt** mặc định trong Suspended mà không kiểm tra policy | Có thể tiếp tục lạm dụng khóa đang điều tra | Fail-closed, recovery exception có phê duyệt |
| Re-enable sau timeout mà không điều tra | Khóa bị lộ có thể được dùng tiếp | Security review và quyết định theo risk |
| Chỉ suspend KEK trong khi ứng dụng cache plaintext DEK | Vẫn đọc/mã hóa được dữ liệu offline | Cache policy, revoke credential, dừng workload khi cần |
| Đổi alias mà không kiểm tra key version | Bypass hoặc bản mã lịch sử bị hỏng | Pin/resolve version, audit migration |
| Không xét multi-region propagation | Một vùng vẫn xử lý Sign/Decrypt | Theo dõi policy revision và effective region |
| Cho event ACTIVE cũ ghi đè SUSPENDED mới | Vô tình mở quyền | Revision monotonic, event authentication |
| Gặp KMS timeout thì fallback sang local key | Bypass trạng thái đình chỉ | Fail-closed khi policy yêu cầu, đường recovery phê duyệt |
| Rewrap DEK đã lộ rồi coi như an toàn | Kẻ tấn công vẫn có DEK | Rotate DEK, re-encrypt và đánh giá phạm vi sự cố |
| Hủy KEK khi chưa xử lý wrapped DEK cũ | Mất khả năng đọc bản mã | Thử restore, migration, backup/retention review |
| Log plaintext key trong lúc điều tra | Tạo lỗ rò rỉ mới | Chỉ ghi key ID/version, actor, operation, reason, outcome |
| Tin KMS non-exportable ngăn mọi abuse | Caller vẫn có thể lạm dụng Sign/Decrypt API | IAM, policy, quota, audit và incident response |

## 14. Tình huống tổng hợp: Đình chỉ khóa ký và khóa dữ liệu

Một nền tảng Java có **Billing Service** ký hóa đơn bằng **RSA-PSS hoặc Ed25519**, **Customer Service** mã hóa hồ sơ bằng **AES-GCM**, còn KEK và private signing key được quản lý trong KMS/HSM.

Một sự cố phát sinh khi credential của Billing Service bị nghi đánh cắp và số lần **Sign** vượt hạn mức bình thường. Đồng thời Customer Service nhận cảnh báo KMS policy cho phép quá nhiều workload gọi **Unwrap**.

**Lộ trình xử lý:**

1. **Định danh:** Security ghi chính xác **billing-sign-v5** và **customer-kek-v3**, purpose, owner, tenant/workload và tài sản liên quan.
2. **Suspend signing key:** chặn API Sign cho **billing-sign-v5** tại enforcement point; giữ metadata/audit để điều tra. Không xuất private key vào môi trường debug.
3. **Xử lý JWT/tài liệu ký:** phân biệt chữ ký đã phát hành, public key đang cache và trường hợp cần revoke trust. Nếu chưa xác nhận private key lộ, không mặc định toàn bộ tài liệu ký trước đây giả mạo.
4. **Suspend hoặc siết Unwrap policy:** với **customer-kek-v3**, chọn cách chặn theo mức rủi ro và yêu cầu đọc dữ liệu. Không cấp blanket decrypt exception để tránh gián đoạn mà bỏ qua IAM.
5. **Kiểm tra cache:** xác định Customer Service đã giữ DEK nào, TTL bao lâu, có cần dừng instance hoặc thu hồi session.
6. **Kích hoạt phương án mới:** tạo/kiểm tra key version mới trong KMS/HSM; chuyển thao tác mới sang version mới khi an toàn.
7. **Migration:** nếu KEK v3 vẫn đáng tin và policy cho phép, rewrap DEK cũ. Nếu chính DEK bị lộ, phải xem xét re-encrypt payload bằng DEK mới.
8. **Audit/review:** ghi mọi transition, operation bị từ chối, thao tác recovery được chấp thuận và kết quả xác minh data plane.
9. **Kết luận:** chỉ re-activate nếu đã giải quyết căn nguyên và không có bằng chứng compromise; nếu khóa lộ, tiếp tục quy trình thay thế và hủy có kiểm soát.

Tình huống minh họa vì sao trạng thái **Suspended** không nên được xây như một nút tắt/bật đơn giản trong giao diện. Nó phải đi cùng **IAM, actual enforcement, audit, dữ liệu lịch sử, policy về trust và kế hoạch chuyển đổi khóa**.

## 15. Checklist review thiết kế Suspended state

1. **Định nghĩa trạng thái:** tên gọi Suspended trong sản phẩm và hệ thống nghiệp vụ thực sự có ngữ nghĩa gì?
2. **Operations:** những thao tác Encrypt, Decrypt, Sign, Verify, Wrap, Unwrap, GenerateMac, DeriveKey nào bị chặn theo policy?
3. **Enforcement:** chặn ở control plane, KMS/HSM data plane hay chỉ ứng dụng? Có đường bypass không?
4. **Key reference:** chuyển state theo key ID/version, owner, purpose rõ ràng, không nhầm với alias?
5. **IAM:** ai có quyền Suspend, Reactivate, ManagePolicy và thực hiện crypto operations? Có separation of duties?
6. **Incident evidence:** reason, ticket, actor, timestamp, policy revision và approval được audit bền vững?
7. **Propagation:** có thời điểm hiệu lực, in-flight operation và multi-region consistency được định nghĩa?
8. **Cached material:** local DEK/private key/session key/derived key có thể tiếp tục dùng thế nào và bị thu hồi ra sao?
9. **Cryptoperiod:** reactivation có bị từ chối nếu khóa hết hạn, revoked hoặc compromised?
10. **Lịch sử:** ciphertext, wrapped DEK, signature, public-key trust, backup và phiên còn phụ thuộc khóa nào?
11. **Recovery:** có kế hoạch decrypt-only exception, rewrap, re-encrypt, rotate và kiểm tra restore trước khi hủy?
12. **Testing:** test ALLOW/DENY, race, retry, stale event, fail-closed và khả năng phục hồi trên enforcement point thật?
13. **Monitoring:** có cảnh báo signature failure, KMS denied, cache bypass, policy drift và sự kiện reactivation trái phép?
14. **Hủy/thu hồi:** đã tách suspend với disable, revoke certificate, revoke token, crypto-erasure và destruction?

### Câu hỏi tự kiểm tra

**Câu 1.** Đánh dấu một key record là SUSPENDED trong database có chắc chắn ngăn mọi API Sign/Decrypt?

**Trả lời:** **Không.** Phải xác định và kiểm thử **enforcement point**. KMS/HSM, private key offline hoặc DEK cached có thể không đọc state ứng dụng.

**Câu 2.** Khi private signing key bị Suspended, các chữ ký đã phát hành có tự mất hiệu lực toán học không?

**Trả lời:** **Không.** Public key vẫn Verify được. Việc chấp nhận chữ ký lịch sử còn phụ thuộc trust policy, certificate status, thời điểm và kết quả điều tra.

**Câu 3.** Có thể tái kích hoạt một khóa đã được chứng minh bị lộ chỉ vì đã hết thời hạn tạm đình chỉ?

**Trả lời:** **Không.** Khóa compromised cần quy trình ứng phó/thay thế; không coi hết timeout là bằng chứng material đã an toàn.

**Câu 4.** Tại sao suspend KEK có thể khiến dữ liệu cũ không đọc được dù bản mã AES-GCM không thay đổi?

**Trả lời:** Vì ứng dụng có thể cần **Unwrap DEK** qua KEK đã suspend trước khi giải mã. Nếu KMS chặn Unwrap và không có DEK cached hoặc đường recovery được phép, không thể khôi phục plaintext.

**Câu 5.** Suspend KEK có chắc ngăn một ứng dụng đang giữ plaintext DEK trong cache giải mã không?

**Trả lời:** **Không.** Ứng dụng có thể dùng DEK offline. Cần quản lý cache, credential, workload và phiên theo threat model.

**Câu 6.** Mở khóa về Active và rewrap DEK có làm DEK đã bị lộ trở nên an toàn trở lại không?

**Trả lời:** **Không.** Rewrap không thay DEK. Nếu DEK bị lộ cần cân nhắc thay khóa dữ liệu, re-encrypt và đánh giá bản mã đã bị ảnh hưởng.

**Câu 7.** Một verifier dùng public key lưu trong JWKS cache có thể chấp nhận JWT đã ký trước khi key bị suspend không?

**Trả lời:** **Có thể**, tùy policy. Suspend private key ở KMS không tự cập nhật JWKS cache, token/session revocation hay quy tắc trust của verifier.

**Câu 8.** Có được coi KMS timeout là trạng thái SUSPENDED và tự fallback sang key local để không gián đoạn dịch vụ không?

**Trả lời:** **Không.** Operational unavailability khác quyết định đình chỉ. Fallback không kiểm soát có thể bỏ qua policy; cần fail-closed hoặc đường recovery được phê duyệt.

**Câu 9.** Một event Active revision 41 đến sau Suspended revision 42. Có nên áp dụng event đến sau để re-activate không?

**Trả lời:** **Không.** Phải xét revision và nguồn sự kiện; event cũ không được ghi đè trạng thái mới chỉ vì đến muộn.

**Câu 10.** Suspended và Destroyed có tương đương không?

**Trả lời:** **Không.** Suspended thường giữ key material và có khả năng phục hồi có kiểm soát; Destroyed liên quan đến hủy key material theo contract. Cả hai còn chịu ảnh hưởng của backup và các bản sao ngoài kho khóa.

**Điểm cốt lõi:** **Suspended state là biện pháp tạm chặn có kiểm soát trong vòng đời khóa, không phải hủy khóa hay bằng chứng khóa vẫn an toàn.** Một triển khai đúng phải chỉ rõ **operation bị chặn, IAM, nơi enforcement, thời điểm hiệu lực, key ID/version, cache, dữ liệu lịch sử, audit và con đường điều tra/recovery**. Khôi phục chỉ được thực hiện khi policy và bằng chứng an ninh cho phép; khóa đã compromised cần xử lý thay thế, thu hồi và hủy theo vòng đời phù hợp.

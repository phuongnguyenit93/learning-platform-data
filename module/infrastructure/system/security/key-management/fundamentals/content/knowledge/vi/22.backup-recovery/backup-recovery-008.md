# Không escrow signing key tùy tiện — Bảo vệ quyền ký và khả năng phục hồi

## 1. Escrow signing key là gì?

**Key escrow** là cơ chế một bên thứ ba, một nhóm quản trị hoặc một hệ thống phục hồi được giữ **bản sao khóa**, **vật liệu cho phép khôi phục khóa**, hoặc **khả năng khôi phục/quyền sử dụng khóa** theo một điều kiện đã định. Với private signing key, escrow có nghĩa là ngoài chủ thể hoặc dịch vụ được ủy quyền ký, còn có một bên có thể lấy lại hoặc kích hoạt khả năng ký bằng cùng key material.

Ví dụ, một doanh nghiệp dùng **Ed25519 private key** để ký biên nhận thanh toán. Để “phòng trường hợp mất khóa”, đội vận hành export private key ra file, mã hóa file bằng password rồi gửi cho một nhóm quản trị giữ. Khi cần, nhóm này có thể khôi phục private key và ký biên nhận dưới cùng danh tính/key ID. Đây là một dạng escrow, dù file được mã hóa và không nằm trong ứng dụng chính.

Vấn đề là **signing key đại diện cho quyền tạo chữ ký**, không chỉ là bí mật cần giữ để đọc dữ liệu cũ. Người có private key hoặc quyền gọi Sign có thể tạo thông điệp được bên nhận xem là đến từ signer đó, nếu relying party vẫn tin public key tương ứng. Vì vậy, escrow tùy tiện có thể tạo thêm một chủ thể có khả năng **mạo danh người ký, dịch vụ ký hoặc tổ chức phát hành**.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài học thuộc chương **Backup và recovery**, nối quản lý khóa với KMS/HSM, chữ ký số, key lifecycle, kiểm soát truy cập, kiểm toán, khôi phục thảm họa và xử lý compromise.

> **Nguyên tắc:** Không escrow private signing key chỉ vì quy trình backup của encryption key đang có escrow. Trước tiên phải chứng minh nhu cầu phục hồi đúng loại khóa, đánh giá rủi ro mạo danh, rồi chọn cơ chế phục hồi hẹp nhất có thể.

### 1.1. Escrow không chỉ là file chứa private key

Trong thực tế, “escrow” có thể mang nhiều hình thức:

- **Raw-key escrow:** Export private key dạng rõ hoặc một bản serialized có thể khôi phục.
- **Encrypted private-key escrow:** Bản private key được mã hóa bằng password hoặc một wrapping key; người giữ escrow có thể khôi phục nếu có đủ quyền/vật liệu.
- **HSM secure backup:** HSM tạo backup blob được bảo vệ trong backup domain của nhà sản xuất hoặc hệ thống HSM; không nhất thiết lộ raw private key cho ứng dụng.
- **HSM replication/cluster:** Key được provision/replicate sang các HSM khác để duy trì khả năng ký khi một thiết bị hoặc vùng lỗi.
- **Threshold/quorum recovery:** Nhiều người hoặc thiết bị cùng phê duyệt thao tác khôi phục, kích hoạt hoặc sử dụng khóa.
- **Threshold/MPC signing:** Nhiều bên cùng tham gia tạo chữ ký theo giao thức mà không cần một bên khôi phục raw private key đầy đủ.

Những hình thức này **không tương đương nhau** về mặt bảo mật. HSM-native backup, replication và threshold signing có thể giữ key trong ranh giới phần cứng hoặc phân tán quyền; raw-key escrow tạo thêm bản sao bí mật có thể bị đánh cắp.

### 1.2. Backup, replication, escrow và recovery khác nhau

| Khái niệm | Mục tiêu | Rủi ro cần đánh giá |
| --- | --- | --- |
| **Backup** | Giữ khả năng khôi phục tài sản sau lỗi hoặc mất mát | Bản sao, quyền đọc, retention và nơi lưu |
| **Replication** | Duy trì dịch vụ qua nhiều thiết bị/vùng | Nhiều điểm thực thi cùng quyền ký, đồng bộ state |
| **Escrow** | Một bên/nhóm có thể khôi phục hoặc tiếp cận key theo điều kiện | Thêm chủ thể có khả năng ký hoặc mạo danh |
| **Recovery** | Quy trình đưa dịch vụ/tài sản về trạng thái hoạt động | Xác thực yêu cầu, phê duyệt, integrity và audit |
| **Key rotation** | Chuyển hoạt động mới sang key material mới | Consumer rollout, key version và lịch sử chữ ký |
| **Key destruction** | Hủy vật liệu theo policy | Không làm mất dữ liệu/evidence còn cần; xác nhận bản sao |

Một backup không nhất thiết là escrow: ví dụ HSM backup blob chỉ có thể restore vào một HSM thuộc cùng security domain, với quorum và key-encryption key được kiểm soát. Nhưng nếu bên giữ backup có thể tự khôi phục private key và ký, **về quyền lực thực tế họ đang nắm một cơ chế escrow** và phải được threat-model như vậy.

## 2. Vì sao signing key khác decryption key?

Một **decryption key** thường được giữ để giải mã ciphertext đã tạo trước đó. Nếu mất key duy nhất, tổ chức có thể không còn đọc được dữ liệu hợp lệ. Vì thế một số hệ thống có nhu cầu rõ ràng về backup/recovery hoặc escrow đối với **decryption keys**.

Một **signing key** lại cho phép tạo chữ ký mới dưới danh tính đã được gắn với public key. Nếu private signing key bị mất nhưng public key, certificate và bằng chứng chữ ký cũ còn được lưu, tổ chức thường vẫn có thể **Verify chữ ký lịch sử**. Tổ chức có thể tạo key pair mới và phát hành/đăng ký public key mới để ký trong tương lai.

| Câu hỏi | Decryption key | Signing key |
| --- | --- | --- |
| Mất private/secret key gây hậu quả chính nào? | Có thể mất khả năng mở dữ liệu đã mã hóa | Mất khả năng tạo chữ ký mới bằng key/danh tính cũ |
| Public key có giải quyết được việc khôi phục không? | Không đối với ciphertext được mã hóa bằng private recipient key | Public verification key vẫn có thể Verify chữ ký cũ |
| Bản backup có thể làm gì? | Khôi phục khả năng đọc dữ liệu cũ | Khôi phục quyền tạo chữ ký mới dưới cùng danh tính/key |
| Ai nắm backup có thể làm gì? | Có thể giải mã dữ liệu nếu có ciphertext và quyền phù hợp | Có thể ký giả mạo dưới key identity nếu khôi phục/được phép Sign |
| Khi mất key, có thể thay key mới không? | Có thể, nhưng dữ liệu cũ cần re-encrypt khi còn đọc được | Có thể tạo key pair mới; cần cập nhật trust/consumers |
| Cần giữ gì để Verify lịch sử? | Không áp dụng theo cùng cách | Public key, certificate/trust chain, signed bytes và evidence liên quan |

**Không thể áp dụng máy móc chính sách escrow của encryption key cho signing key.** Khả năng khôi phục dữ liệu và khả năng mạo danh người ký là hai mục tiêu khác nhau.

### 2.1. Mất signing key không đồng nghĩa mất chữ ký cũ

Giả sử một dịch vụ đã ký 10 triệu biên nhận bằng **signer-v1**. Private key-v1 sau đó bị hủy có kiểm soát. Nếu tổ chức còn:

- Public verification key-v1 hoặc certificate tương ứng.
- Chữ ký và đúng bytes đã ký.
- Thông tin issuer, thuật toán, key ID/version và policy.
- Timestamp/revocation evidence khi yêu cầu.

thì bên xác minh vẫn có thể kiểm tra chữ ký về mặt toán học. Việc đánh giá chữ ký có đáng tin ở thời điểm phát hành còn phụ thuộc **key compromise, trust policy và bằng chứng thời gian**, nhưng không cần private key-v1 chỉ để Verify.

Nếu cần ký biên nhận mới, tổ chức có thể sinh **signer-v2**, đăng ký public-v2 và chuyển dịch vụ. Do đó, lý do “phải escrow private signer để không mất khả năng Verify lịch sử” là không đúng.

### 2.2. Escrow có thể phá vỡ ý nghĩa của attribution

Với chữ ký số, private key thường được gắn với một **chủ thể chịu trách nhiệm**: cá nhân, tổ chức, CA, release pipeline hoặc dịch vụ. Nếu một bên khác có thể khôi phục và dùng cùng key:

- Chữ ký mới có thể được tạo mà không có sự tham gia của chủ thể ban đầu.
- Khó phân biệt ai thực sự yêu cầu hoặc thực hiện việc ký nếu audit không đủ mạnh.
- Chủ thể có thể phủ nhận chữ ký, trong khi bên giữ escrow cũng có khả năng tạo ra nó.
- Quy trình pháp lý/tuân thủ có thể không chấp nhận mô hình custody đó cho loại chữ ký đang xét.

Escrow không tự động làm chữ ký mất hiệu lực về mặt toán học, nhưng có thể làm yếu **bằng chứng về quyền kiểm soát, attribution và non-repudiation**. Những kết luận pháp lý phải theo quy định và trust framework cụ thể.

## 3. Rủi ro khi escrow signing key tùy tiện

### 3.1. Mở rộng số chủ thể có quyền mạo danh

Mỗi bản sao private key hoặc đường khôi phục có thể tạo thêm:

- Người có thể lấy key material.
- Người có thể phê duyệt restore.
- Quản trị viên backup/HSM có thể kích hoạt key.
- Hệ thống lưu bản sao có thể bị xâm nhập.
- Quy trình khẩn cấp có thể bị lợi dụng hoặc giả mạo.

Nếu một signing key ban đầu chỉ được phép sử dụng bởi **Payments Signing Service**, việc đưa raw key vào kho escrow dùng chung làm mở rộng trust boundary sang các tài khoản và nhóm vận hành khác.

### 3.2. Escrow trở thành mục tiêu có giá trị cao

Attacker có thể không cần xâm nhập ứng dụng ký chính. Họ có thể nhắm tới:

- Backup repository hoặc object store chứa encrypted key blobs.
- Password/wrapping key của file escrow.
- Quorum members hoặc các thiết bị giữ recovery shares.
- HSM backup domain và admin credentials.
- Ticket/change-management process cho yêu cầu restore.
- Máy trạm của người quản trị được phép tải hoặc kích hoạt backup.

Một nơi lưu escrow chứa nhiều private signing keys có thể trở thành **điểm tập trung rủi ro**, khiến một sự cố ảnh hưởng nhiều issuer, tenant hoặc hệ thống.

### 3.3. Có thể tạo chữ ký giả ngoài hệ thống kiểm soát

Nếu attacker lấy được raw private key, họ có thể ký bằng thư viện mật mã riêng mà không gọi KMS/HSM. Khi đó:

- KMS audit không thấy những chữ ký được tạo ngoài HSM.
- Rate limit và business authorization của signing service không còn bảo vệ các chữ ký đó.
- Key ID/public key vẫn có thể Verify chữ ký giả về mặt toán học.
- Rotation ở hệ thống chính không xóa bản raw key attacker đã sao chép.

Đây là một khác biệt quan trọng giữa **HSM Sign API abuse** và **raw private-key compromise**.

### 3.4. Tăng rủi ro nội gián và xung đột trách nhiệm

Một nhân sự có quyền khôi phục escrow có thể có khả năng tạo chữ ký dưới danh nghĩa một dịch vụ hoặc cá nhân. Nếu người đó đồng thời có quyền:

- Phê duyệt giao dịch.
- Truy cập nội dung cần ký.
- Khôi phục private key.
- Xóa hoặc chỉnh sửa audit logs.

thì separation of duties bị phá vỡ. Không nên gom các quyền đó vào một role chỉ vì quy trình vận hành thuận tiện.

### 3.5. Backup cũ có thể tồn tại lâu hơn key policy

Private signing key có thể được sao lưu vào:

- Snapshot định kỳ.
- Archive/object version.
- Bản sao ngoài site.
- Backup catalog hoặc replication target.
- Máy tính của nhân viên hoặc removable media.

Nếu không có inventory và retention, tổ chức có thể nghĩ đã hủy key nhưng **bản escrow cũ vẫn có thể khôi phục**. Ngược lại, xóa backup không đúng quy trình có thể làm mất khả năng khôi phục của những key mà tổ chức thực sự cần.

### 3.6. Khó chứng minh ai đã ký

Audit của HSM có thể chứng minh một operation Sign đã được gọi bởi principal cụ thể. Nhưng nếu private key được export và sử dụng bên ngoài:

- Không còn đầy đủ HSM operation logs cho những chữ ký ngoài.
- Có thể không biết ai đã cầm bản key hoặc tạo chữ ký.
- Timestamp do payload tự khai có thể bị giả.
- Việc điều tra chữ ký lịch sử khó phân biệt signer hợp lệ và người giữ escrow.

### 3.7. Escrow và compromise có thể tạo vòng lặp

Khi private signer bị nghi lộ, tổ chức cần containment và có thể phải revoke key. Nếu backup escrow không được kiểm soát, một nhóm có thể **restore chính key đã bị revoke** để duy trì dịch vụ. Điều này hồi sinh đường ký giả và làm mất hiệu lực quyết định containment.

Mọi cơ chế backup/recovery phải tôn trọng **revocation state, incident tombstone và key lifecycle policy hiện hành**; không chỉ khôi phục bytes.

## 4. Những loại signing key cần chính sách khác nhau

Không phải mọi private signing key đều có cùng giá trị, cách dùng và yêu cầu liên tục.

| Loại signing key | Nhu cầu thường gặp | Định hướng backup/escrow |
| --- | --- | --- |
| **Personal document signing key** | Gắn với một cá nhân, chữ ký có ý nghĩa attribution | Thường không escrow raw private key; chủ thể quản lý thiết bị/credential theo quy định |
| **Qualified/electronic signature key** | Có thể chịu yêu cầu pháp lý và quy trình cấp phát đặc thù | Tuân theo trust service/provider và luật áp dụng; không tự tạo escrow ngoài mô hình được chứng nhận |
| **Enterprise service signing key** | Ký JWT, receipt, webhook manifest hoặc message tự động | Ưu tiên HSM/KMS, HA/replication và controlled backup trong security domain |
| **Code/release signing key** | Ký artifact/phần mềm được downstream tin | HSM hoặc signing service có approval; bảo vệ pipeline, provenance và release authorization |
| **TLS server authentication key** | Xác thực server/mTLS endpoint | Có thể rekey/reissue certificate khi mất; HA cần theo kiến trúc HSM/secret management |
| **Intermediate CA signing key** | Ký certificate cho một miền PKI | Backup/recovery rất nghiêm ngặt, HSM domain và quorum theo CPS/policy |
| **Root CA signing key** | Trust anchor có blast radius rộng | Offline HSM, key ceremony, quorum, secure backup/recovery và kiểm toán đặc biệt |
| **Ephemeral signing/session-related key** | Thời gian sống ngắn trong protocol | Không áp dụng escrow dài hạn tùy tiện; lifecycle theo giao thức |

### 4.1. Personal signing key

Nếu private key đại diện cho **chữ ký của một cá nhân**, việc tổ chức giữ bản escrow có thể cho phép tổ chức ký thay cá nhân. Với chữ ký cần thể hiện **sự kiểm soát riêng của người ký**, escrow raw private key có thể đi ngược mục đích và yêu cầu của trust framework.

Nên phân biệt:

- **Recovery của tài khoản/credential:** Khôi phục quyền truy cập vào dịch vụ hoặc thiết bị theo quy trình.
- **Recovery của signing private key:** Khôi phục đúng key material để tiếp tục tạo chữ ký dưới cùng public key.
- **Re-enrollment/re-key:** Tạo key pair mới và liên kết public key mới với danh tính sau xác minh.

Không biến quy trình khôi phục tài khoản thành một đường khôi phục private signing key mà người dùng không biết.

### 4.2. Enterprise service signing key

Một service signer có thể cần **availability cao**: nếu một HSM module hỏng, hệ thống vẫn cần ký message hợp lệ. Điều đó không mặc nhiên yêu cầu export raw private key ra file escrow. Có thể dùng:

- HSM cluster/replication được kiểm soát.
- HSM-native backup/restore trong cùng security domain.
- Nhiều signer instances cùng truy cập một key handle qua policy.
- Threshold/MPC signing nếu yêu cầu kiến trúc phù hợp.
- Key pair mới và trust rollout nếu mất key không thể phục hồi.

Chọn theo **RTO/RPO, threat model, provider capability và yêu cầu pháp lý**, không theo thói quen backup file.

### 4.3. CA root/intermediate key

CA key có thể cần kế hoạch backup/recovery rất nghiêm ngặt vì mất key có thể ảnh hưởng khả năng phát hành/chuyển tiếp trust. Tuy nhiên, chính vì **blast radius cực lớn**, việc escrow phải được quản lý như một key ceremony: offline storage, quorum, dual control, secure HSM backup, kiểm tra định kỳ và hồ sơ đầy đủ.

Không áp dụng một chính sách “không bao giờ backup bất kỳ signing key nào”. Bài học là **không escrow tùy tiện**; những key đặc biệt có yêu cầu liên tục/trust phải có mô hình phục hồi được thiết kế và phê duyệt riêng.

## 5. Quyết định có cần backup hoặc escrow signing key không?

Trước khi tạo bản sao private signing key, phải chứng minh **mất key sẽ gây hậu quả gì**, **có cách phục hồi nào ít rủi ro hơn**, và **ai có thể sử dụng key sau recovery**.

### 5.1. Decision tree

~~~mermaid
flowchart TD
    A["Signing key cần continuity/DR?"] --> B{"Mất key có làm mất<br/>dữ liệu lịch sử không?"}
    B -->|"Không; chỉ mất khả năng ký mới"| C["Có thể re-key và cập nhật<br/>public trust/consumers?"]
    C -->|"Có"| D["Ưu tiên key pair mới,<br/>giữ public verification evidence"]
    C -->|"Không"| E["Xác định dependency và<br/>RTO/RPO thực tế"]
    B -->|"Có yêu cầu đặc thù"| E
    E --> F{"Có thể dùng HSM HA,<br/>replication hoặc threshold signing?"}
    F -->|"Có"| G["Thiết kế HA/backup trong<br/>security boundary"]
    F -->|"Không"| H["Xem xét exception escrow<br/>với threat model và approvals"]
    G --> I["Key ceremony, quorum,<br/>audit, restore tests"]
    H --> I
    D --> J["Phê duyệt policy và kiểm thử"]
    I --> J
~~~

### 5.2. Câu hỏi bắt buộc

1. **Business requirement:** Cần tiếp tục ký dưới cùng key identity hay chỉ cần tiếp tục cung cấp dịch vụ ký?
2. **Historical need:** Có thật sự cần private key cũ để Verify chữ ký không? Nếu không, giữ public key/evidence là đủ.
3. **Recovery objective:** RTO/RPO nào cần đạt? Có thể chấp nhận sinh key pair mới và cập nhật consumers không?
4. **Threat model:** Ai có thể lấy backup, recovery shares, wrapping key hoặc yêu cầu restore?
5. **Custody:** Ai sở hữu, ai giữ, ai phê duyệt và ai thực hiện restore? Có separation of duties không?
6. **HSM semantics:** Backup có thể restore ở đâu, bằng ai, vào thiết bị nào, có thể export raw key không?
7. **Revocation:** Làm sao bảo đảm key bị revoke/compromised không thể được restore rồi Sign lại?
8. **Evidence:** Có log mọi lần backup, restore, activation, Sign và policy changes không?
9. **Retention:** Bản backup tồn tại bao lâu, được hủy khi nào và kiểm tra mọi bản sao ra sao?
10. **Compliance:** Có quy định chữ ký cá nhân, CA, code signing hoặc trust service nào chi phối không?

### 5.3. Không nhầm continuity của service với continuity của key

Một service có thể cần sẵn sàng 99.99%, nhưng điều đó không tự có nghĩa **phải khôi phục đúng private key cũ**. Nếu downstream có thể tin public key v2 sau rollout, service có thể tạo signer-v2 và tiếp tục ký. Đây là **service continuity bằng re-key**.

Ngược lại, một CA root key hoặc một danh tính ký gắn với hợp đồng/thiết bị legacy có thể có yêu cầu giữ cùng public identity lâu dài. Khi đó cần đánh giá secure recovery, nhưng không được tự động biến nó thành một file private key dùng chung.

## 6. Các phương án thay escrow raw private key

### 6.1. HSM high availability và replication

Một cụm HSM có thể cho nhiều module thực hiện Sign bằng cùng logical key hoặc key được replicate theo cơ chế bảo vệ của nhà cung cấp. Mục tiêu là **khả năng sẵn sàng**, không phải tạo một bản raw private key cho ứng dụng.

Thiết kế cần xác minh:

- Replication domain và key attributes được bảo toàn.
- Chỉ HSM được phê duyệt mới nhận key.
- Mỗi module có physical/security controls và admin roles phù hợp.
- Một node bị compromise không tự cấp quyền truy cập mọi node.
- Revocation/disable state và policy updates lan truyền.
- Audit có thể phân biệt module, principal, operation và key version.

**Replication vẫn làm tăng số nơi có khả năng ký.** Vì vậy phải threat-model số HSM replicas và quyền admin, không xem HA là miễn phí về bảo mật.

### 6.2. HSM-native secure backup

Một số HSM hỗ trợ export **backup object được wrap/đóng gói trong một backup domain**, chỉ có thể restore bởi HSM cùng domain hoặc theo quy trình quorum. Đây khác với export private key dạng PKCS#8/PEM ra file mà ứng dụng có thể mở.

Điều cần kiểm tra:

1. Backup blob có được mã hóa bằng **backup key/domain key** được bảo vệ không?
2. Ai có thể tạo backup, ai có thể restore và ai có thể thay đổi policy?
3. Có cần quorum/dual control hay không?
4. Restore có bắt buộc vào HSM được đăng ký và xác thực không?
5. Key attributes như **non-extractable, sign-only, sensitive** có được giữ sau restore?
6. Có thể restore vào môi trường staging/test hoặc account khác không?
7. Backup có thể bị replay để khôi phục một key đã revoked không?
8. Có log và evidence cho từng lần backup/restore không?

Không suy từ nhãn “HSM backup” rằng **raw private key không thể bị lấy trong mọi tình huống**. Cần đọc semantics, configuration và threat model của provider cụ thể.

### 6.3. Threshold/quorum control

**Quorum** có thể yêu cầu nhiều cá nhân/thiết bị cùng phê duyệt một hành động nhạy cảm như backup, restore, activate hoặc delete. Ví dụ **2-of-3 custodians** phải tham gia theo chính sách.

Quorum giúp giảm nguy cơ một cá nhân đơn lẻ tự khôi phục key, nhưng cần:

- Danh tính custodian độc lập và xác thực mạnh.
- Phân phối quyền ở các địa điểm/nhóm khác nhau.
- Quy trình thay custodian khi nghỉ việc/mất thiết bị.
- Chống collusion, phishing và coercion.
- Audit ai đã tham gia và hành động nào được phê duyệt.
- Diễn tập trường hợp một hoặc nhiều custodians không khả dụng.

**M-of-N không tự bảo đảm an toàn** nếu các shares nằm cùng một password manager, cùng một admin account hoặc cùng một laptop.

### 6.4. Threshold/MPC signing

Trong một số kiến trúc, **threshold signature hoặc multi-party computation (MPC)** cho phép nhiều bên cùng tham gia tạo chữ ký mà không cần tái dựng private key hoàn chỉnh ở một nơi duy nhất.

Lợi ích có thể gồm:

- Không có một bản raw private key hoàn chỉnh để escrow theo cách truyền thống.
- Yêu cầu nhiều bên/thiết bị cùng tham gia ký.
- Phân tán trust và giảm phụ thuộc vào một HSM/host.

Nhưng threshold signing có **protocol, setup, share refresh, recovery và operational complexity** riêng. Nếu nhiều shares bị compromise hoặc coordinator bị lạm dụng, hệ thống vẫn có thể bị tấn công. Không tự xây protocol threshold/MPC hoặc chia private key bằng cách cắt chuỗi bytes.

### 6.5. Re-key thay vì restore cùng key

Nếu key cũ bị mất nhưng public verification material vẫn có, một chiến lược thường đơn giản hơn là:

1. Sinh key pair mới trong HSM/KMS.
2. Xác minh owner/issuer và đăng ký public key mới.
3. Roll out trust/certificate/JWKS cho consumers.
4. Chuyển Sign mới sang key-v2.
5. Giữ public-v1 và evidence lịch sử theo retention.
6. Ghi nhận key-v1 không còn khả năng ký mới.

Chiến lược này phù hợp khi **không cần tiếp tục ký dưới cùng private key**. Nó có thể không phù hợp với một số CA/root trust, thiết bị offline hoặc giao thức legacy; khi đó phải có kế hoạch migration riêng.

## 7. Key ceremony và dual control khi có recovery

Nếu một signing key thật sự cần secure backup/recovery, phải coi thao tác đó là **key ceremony có thẩm quyền**, không phải một thao tác copy file của quản trị viên.

### 7.1. Các vai trò cần tách

| Vai trò | Trách nhiệm | Không nên mặc nhiên có |
| --- | --- | --- |
| **Key owner** | Xác định purpose, risk và business need | Quyền tự export/restore mọi key |
| **Security/PKI authority** | Phê duyệt key profile, ceremony và trust implications | Quyền tự ký dữ liệu nghiệp vụ |
| **HSM operator** | Thực hiện thao tác backup/restore theo runbook | Quyền đơn phương mở quorum |
| **Custodians** | Giữ recovery components/approval factors | Toàn bộ components trong cùng một nơi |
| **Auditor/witness** | Xác minh quy trình và hồ sơ | Raw key access không cần thiết |
| **Application signer** | Gọi Sign theo IAM/business policy | Backup, export hoặc change key policy |
| **Incident commander** | Quyết định containment/revocation khi sự cố | Tự bỏ qua dual control không có evidence |

### 7.2. Quy trình ceremony minh họa

~~~mermaid
sequenceDiagram
    participant O as Key owner
    participant S as Security/PKI approver
    participant C1 as Custodian A
    participant C2 as Custodian B
    participant H as HSM backup domain
    participant A as Auditor
    O->>S: Yêu cầu backup/recovery + business rationale
    S->>S: Review risk, purpose, retention, quorum
    S-->>O: Approval có scope và expiry
    C1->>H: Xác thực phần/quyền thứ nhất
    C2->>H: Xác thực phần/quyền thứ hai
    H->>H: Tạo secure backup object trong domain
    H-->>A: Audit reference, key ID/version, result
    A->>A: Đối chiếu custody, policy và evidence
    Note over O,H: Không export raw private key ra ứng dụng
~~~

### 7.3. Nội dung ceremony record

Một hồ sơ cần ghi:

- **Purpose và business justification** cho backup/restore.
- Key ID/version, algorithm, key usage và HSM security domain.
- Approvers, custodians, operator và witness.
- Thiết bị/vùng backup, thời điểm UTC, procedure version.
- Backup object reference và integrity metadata.
- Quorum policy, expiration/retention và access restrictions.
- Restore test result và key attributes sau restore.
- Cách xử lý revocation/tombstone và destruction.

Không ghi raw private key, HSM PIN, recovery secret hoặc shares vào biên bản. Các phần nhạy cảm phải ở đúng secure custody mechanism, không biến tài liệu ceremony thành bản escrow mới.

## 8. Khi nào ngoại lệ escrow có thể được xem xét?

Có những hệ thống mà **mất private signing key cũ** gây ảnh hưởng đặc biệt lớn: CA root/intermediate, hệ thống ký thiết bị offline, một số hệ thống công nghiệp/viễn thông hoặc nền tảng legacy không thể nhanh chóng cập nhật public trust. Trong trường hợp đó, secure backup/recovery có thể là yêu cầu hợp lệ.

Tuy nhiên, **“cần DR” không đủ để tự động cho phép raw private-key escrow**. Phải có lý do kinh doanh, threat model, phê duyệt và cơ chế hạn chế việc sử dụng khóa sau recovery.

### 8.1. Điều kiện tối thiểu cho ngoại lệ

Một exception proposal nên chứng minh:

1. **Business necessity:** Vì sao re-key và cập nhật public trust không đáp ứng RTO/RPO hoặc yêu cầu pháp lý/giao thức?
2. **Key classification:** Đây là personal signer, service signer, code-signing key hay CA key? Ai chịu trách nhiệm về danh tính?
3. **Least dangerous mechanism:** Vì sao HSM replication, HSM-native backup hoặc threshold signing không đủ?
4. **Custody and quorum:** Ai giữ backup/recovery factors? Có cần nhiều người độc lập phê duyệt?
5. **Use restriction:** Sau restore, key chỉ được dùng cho purpose/algorithm/operation nào?
6. **Revocation awareness:** Làm sao ngăn restore một key đã bị compromised/revoked?
7. **Audit and evidence:** Có thể chứng minh ai tạo, giữ, truy cập, restore và sử dụng key?
8. **Retention/destruction:** Backup hết hạn khi nào, ai phê duyệt hủy và kiểm kê mọi replicas ra sao?
9. **Recovery testing:** Restore được thử trong môi trường cô lập mà không tạo chữ ký production ngoài ý muốn?
10. **Residual risk acceptance:** Người có thẩm quyền hiểu rằng thêm recovery path đồng nghĩa thêm trust boundary?

### 8.2. Không dùng một ngoại lệ chung cho toàn bộ key inventory

Không nên có policy kiểu:

~~~yaml
allPrivateKeys:
  backup: true
  escrow: shared-admin-vault
~~~

Policy như vậy bỏ qua **key purpose, owner, tenant, environment và hậu quả mạo danh**. Cần exception riêng theo từng key class hoặc key resource, có expiry và review date.

### 8.3. Ngoại lệ phải có thời hạn và điều kiện chấm dứt

Ví dụ:

~~~yaml
# Mẫu khái niệm, không phải cấu hình của KMS cụ thể.
exceptionId: EXC-CA-ROOT-004
keyRef: offline-root-ca-v2
purpose: certificate-authority-signing
mechanism: hsm-native-secure-backup
rawPrivateKeyExport: false
securityDomain: root-ca-backup-domain
approval:
  owner: pki-governance
  requiredCustodians: 3
  minimumApprovals: 2
  dualControl: true
restore:
  requireIncidentOrApprovedCeremony: true
  requireCurrentRevocationCheck: true
  destinationHsmAllowlist: root-ca-hsm-cluster
  signDisabledUntilApproval: true
retention:
  reviewDate: "2027-11-28"
  destroyAfter: "2030-11-28"
  legalHoldOverridesDestruction: true
audit:
  recordBackupRestoreAndSign: true
  alertOnRestore: true
~~~

**Đây là ví dụ policy quản trị**, không khẳng định mọi HSM hỗ trợ những trường này. Các thuộc tính cần được ánh xạ vào cơ chế thực thi thực tế, runbook và hệ thống audit. Đặc biệt, trường signDisabledUntilApproval phải được thực thi tại HSM/authorization gateway, không chỉ nằm trong YAML.

## 9. Quy trình backup signing key trong HSM

Nếu đã phê duyệt backup, mục tiêu là **khôi phục trong đúng security boundary** mà không tạo một bản private key có thể dùng tùy tiện bên ngoài.

### 9.1. Trước khi backup

- Xác nhận **key owner, purpose, algorithm, key ID/version, HSM attributes và state**.
- Kiểm tra private key có thật sự cần khôi phục cùng identity hay có thể re-key.
- Xác định HSM backup domain, destination allowlist, quorum và custodian roles.
- Kiểm tra key policy **Sign-only**, non-extractable/sensitive và IAM grants.
- Có change/ceremony approval, retention, restore test plan và incident contact.
- Xác nhận key chưa bị **revoked/compromised**; không backup một key đã mất tin cậy chỉ để giữ khả năng sử dụng.

### 9.2. Thực hiện backup

1. Operator và custodians xác thực theo quy trình độc lập.
2. HSM thực hiện **backup object operation** trong security domain đã phê duyệt.
3. Ghi backup reference, HSM/module identity, key ID/version, thời gian UTC và kết quả.
4. Lưu backup object trong kho bảo vệ phù hợp, tách quyền với ứng dụng ký.
5. Bảo vệ metadata và inventory; không ghi raw key hoặc recovery secret vào logs.
6. Đối chiếu attributes sau backup theo khả năng provider.

### 9.3. Bảo quản

- Lưu bản backup ở **vùng vật lý/logic tách biệt** với production HSM khi DR yêu cầu.
- Dùng encryption/integrity và access controls theo backup domain.
- Tách custodians, storage administrators và application signer.
- Có cảnh báo truy cập, copy, export, restore hoặc thay đổi ACL.
- Kiểm soát mọi bản sao và thời hạn retention.
- Không để backup trong cùng account/role mà workload Sign có thể tự đọc/restore.

### 9.4. Restore test

Restore test cần diễn ra trong **HSM/partition thử nghiệm được phê duyệt**, có cách ly với production issuer và relying parties. Kiểm tra:

1. Backup blob được xác thực và thuộc đúng domain.
2. Restore cần đúng quorum/dual control.
3. Key attributes/purpose và non-extractability được giữ.
4. Private key không xuất thành file cho ứng dụng.
5. Key không tự chuyển sang **ACTIVE/Sign-enabled** chỉ vì restore thành công.
6. Chỉ một signer test được phép tạo signature thử nghiệm, và public test key không bị nhầm với production trust.
7. Audit ghi đủ custodian, operator, destination HSM, key version và outcome.
8. Key test được retire/destroy theo test plan sau khi hoàn tất.

**Restore test thành công không phải phê duyệt dùng key trong production.** Cần một bước activation riêng và kiểm tra revocation/current policy.

## 10. Quy trình recovery trong thảm họa

### 10.1. Phân loại tình huống

| Tình huống | Mục tiêu | Hướng xử lý |
| --- | --- | --- |
| **Một HSM node hỏng, key còn replica** | Duy trì Sign service | Failover sang HSM replica đã được phê duyệt; kiểm tra state/audit |
| **Một vùng mất kết nối, HSM khác còn hoạt động** | Khôi phục dịch vụ ở region DR | Điều phối traffic và key access theo region policy |
| **HSM cluster mất nhưng secure backup còn** | Phục hồi cùng key identity nếu được phép | Quorum restore vào HSM mới, kiểm tra attributes/revocation |
| **Private signing key bị mất hoàn toàn, không có backup** | Tiếp tục ký mới | Re-key, phát public trust mới, giữ public evidence cũ |
| **Private signing key bị compromise** | Ngăn ký giả | Revoke/disable key và trust; không restore key cũ để duy trì dịch vụ |
| **Escrow custodians không khả dụng** | Khôi phục có kiểm soát | Dùng quorum/contingency đã thiết kế; không phá dual control tùy tiện |
| **Backup blob bị hỏng** | Đánh giá khả năng phục hồi | Dùng replica/backup khác đã kiểm tra; nếu không có thì re-key |
| **Certificate hết hạn nhưng private key an toàn** | Duy trì xác thực endpoint | Reissue/rekey theo PKI policy; certificate renewal không nhất thiết cần escrow |

### 10.2. Phân biệt mất key và compromise key

Đây là quyết định quan trọng nhất:

- **Lost/unavailable, chưa có dấu hiệu lộ:** Recovery từ backup có thể phù hợp nếu owner, custody và key state vẫn tin cậy.
- **Compromised:** Không restore để tiếp tục ký bằng key đó; containment/revocation và key replacement là trọng tâm.
- **Unknown:** Tạm suspend theo risk, bảo toàn evidence và điều tra. Không tự kết luận key an toàn chỉ vì backup vẫn dùng được.

Một backup có thể giúp **khôi phục khả năng hoạt động**, nhưng cũng có thể **khôi phục lại quyền của attacker** nếu key đã bị revoke hoặc compromise trước snapshot.

### 10.3. Quy trình DR activation

~~~mermaid
flowchart TD
    A["DR declared / HSM unavailable"] --> B["Xác định lost vs unavailable vs compromised"]
    B --> C{"Key còn được tin cậy?"}
    C -->|"Không / compromised"| D["Không restore signer cũ<br/>revoke + create new key"]
    C -->|"Có"| E{"Replica hoạt động?"}
    E -->|"Có"| F["Failover HSM theo policy"]
    E -->|"Không"| G["Secure backup restore<br/>với quorum/dual control"]
    F --> H["Verify key state, attributes,<br/>IAM và audit"]
    G --> H
    D --> I["Register public key mới<br/>roll out trust/consumers"]
    H --> J{"Activation được duyệt?"}
    J -->|"Có"| K["Enable Sign theo scope"]
    J -->|"Không"| L["Giữ Sign disabled,<br/>điều tra/khắc phục"]
    I --> M["Verify new signer và service recovery"]
    K --> M
~~~

### 10.4. RTO/RPO phải gắn với mô hình trust

**RTO** là thời gian mục tiêu để khôi phục dịch vụ; **RPO** là mức dữ liệu/trạng thái có thể chấp nhận mất. Với signing service, cần định nghĩa thêm:

- Có thể **tạm ngừng ký** trong bao lâu?
- Có thể dùng **key pair mới** và cập nhật consumers trong RTO không?
- Có bao nhiêu relying parties offline hoặc cần certificate pinning?
- Key version và audit state có thể đồng bộ đến mức nào?
- Có chấp nhận **degraded mode** chỉ cho đọc/Verify mà không ký mới không?

Không đạt RTO bằng cách đưa raw private key vào một vault ít kiểm soát hơn. Nếu availability thực sự đòi hỏi replication, phải xây security boundary tương xứng.

## 11. Nếu buộc phải escrow: kiểm soát rủi ro như một đặc quyền cực nhạy cảm

Trong ngoại lệ đã được phê duyệt, escrow phải được xem như **quyền có thể tạo chữ ký dưới một danh tính đáng tin**, không phải một tác vụ backup bình thường.

### 11.1. Nguyên tắc bảo vệ

- **Purpose-bound:** Escrow chỉ áp dụng cho key ID/version và mục đích được duyệt; không áp dụng wildcard.
- **No raw export by default:** Ưu tiên backup blob trong HSM security domain hoặc cơ chế threshold đã thẩm định.
- **Quorum:** Không một custodian hoặc administrator đơn lẻ có thể restore/activate/sign.
- **Separation of duties:** Người đề nghị, phê duyệt, thực hiện và kiểm toán là các vai trò tách biệt.
- **Offline/isolated custody:** Bảo vệ bản backup và recovery factors khỏi account/role production.
- **Short-lived activation:** Sau restore, Sign chỉ được bật trong scope/thời hạn cần thiết.
- **Revocation-aware:** Backup không thể làm sống lại key đã revoked/compromised.
- **Complete audit:** Mọi backup, copy, access, restore, activation, Sign, policy change và destruction đều có evidence.
- **Periodic review:** Kiểm tra custodian, quyền, retention, provider semantics và restore tests.

### 11.2. Không cho phép escrow custodian tự ký nghiệp vụ

Custodian có thể tham gia **quorum restore**, nhưng không mặc nhiên được cấp quyền ký mọi message. Sau restore, key nên:

1. Được nạp vào HSM đã allowlist.
2. Giữ nguyên key purpose/algorithm và Sign-only attributes.
3. Ở trạng thái **disabled hoặc chưa được activation**.
4. Chỉ được activation theo approval của owner/security authority.
5. Chỉ được signer workload được duyệt gọi Sign.
6. Có alert khi có lần Sign đầu tiên và mỗi lần sử dụng trong DR window.

Nếu HSM/provider không hỗ trợ tách quyền restore và Sign như mong muốn, phải ghi nhận hạn chế và chọn kiến trúc/biện pháp bù trừ khác; không giả định YAML policy có thể tạo ra tính năng không tồn tại.

### 11.3. Custodian lifecycle

Escrow có thể mất an toàn khi người giữ share rời tổ chức hoặc thiết bị bị mất. Quy trình phải có:

- Xác thực danh tính và kiểm tra quyền custodian định kỳ.
- Thu hồi quyền ngay khi đổi vai trò/nghỉ việc/mất thiết bị.
- Thay thế share/factor theo cơ chế HSM/provider, không tự chia lại raw private key.
- Đảm bảo quorum còn đủ sau khi một custodian bị thay.
- Kiểm tra collusion risk và không để một quản trị viên kiểm soát danh sách custodian.
- Diễn tập tình huống **một hoặc nhiều custodians unavailable**.

### 11.4. Backup không được override revocation

Khi key-v1 bị compromise và đã revoke, backup-v1 phải được đánh dấu **quarantined/invalid for recovery** theo control plane có thẩm quyền. Restore workflow cần kiểm tra:

- Key ID/version và revocation status.
- Incident/tombstone records.
- HSM security domain, destination và current policy.
- Approval scope/expiry.
- Các grants/aliases cũ không được tự khôi phục.

Không dùng một bản backup snapshot cũ làm nguồn duy nhất quyết định key còn active. **Current trust state phải thắng trạng thái cũ trong backup.**

## 12. Nếu không escrow: kế hoạch phục hồi khi private signing key bị mất

Đối với nhiều signing keys, phương án đơn giản và an toàn hơn là **không phục hồi private key cũ**, mà sinh key pair mới và cập nhật trust.

### 12.1. Quy trình re-key

1. Xác minh key cũ **mất/unavailable** chứ không phải bị compromise.
2. Đăng ký sự kiện mất key và ngăn mọi bản backup/replica không rõ nguồn tự được dùng.
3. Sinh **private/public pair mới** trong HSM/KMS hoặc thiết bị ký được phê duyệt.
4. Thiết lập key purpose, algorithm, IAM grants và owner mới.
5. Phát hành certificate/JWKS/trusted registry entry cho public key mới.
6. Roll out verifier/partner/client theo kế hoạch và kiểm thử trước cutover.
7. Chuyển Sign mới sang key-v2; ghi key ID/version trên artifacts.
8. Giữ **public key-v1, certificate chain và evidence lịch sử** theo retention.
9. Thu hồi trust v1 nếu có nguy cơ compromise; nếu chỉ mất private key, xử lý theo chính sách và thời hạn chữ ký.
10. Đóng key-v1 ở trạng thái phù hợp, kiểm kê và hủy các artifacts không còn cần.

### 12.2. Chữ ký lịch sử không cần private key để xác minh

Khi key-v1 không còn khả năng ký, public-v1 vẫn có thể dùng để **Verify chữ ký đã tạo trước đó**. Để đánh giá độ tin cậy lịch sử, có thể cần:

- Public key/certificate đúng issuer và purpose.
- Certificate chain và trust policy có hiệu lực tại thời điểm liên quan.
- CRL/OCSP hoặc revocation evidence khi áp dụng.
- Timestamp token/long-term validation evidence nếu profile yêu cầu.
- Original signed bytes, signature và algorithm parameters.

**Không giữ private signer chỉ để Verify chữ ký cũ.** Giữ private key cũ làm tăng quyền tạo chữ ký mới; public material và bằng chứng là phần phục vụ xác minh.

### 12.3. Nếu consumers không thể cập nhật public key nhanh

Đây là một **compatibility constraint**, không tự động là lý do escrow:

- Đánh giá certificate rollover, multiple trusted public keys hoặc versioned JWKS.
- Dùng một giai đoạn chuyển đổi được phê duyệt nếu key cũ vẫn an toàn.
- Thông báo và xác nhận với partner/clients.
- Đặt deadline và đo consumer adoption.
- Nếu private key bị compromise, không giữ trust v1 chỉ để tiện tương thích; xử lý emergency revocation.

### 12.4. Nếu private key mất nhưng public identity bị pin cố định

Một số thiết bị/partner pin public key hoặc certificate fingerprint. Khi đó re-key có thể cần **re-enrollment, firmware update, out-of-band trust update hoặc migration protocol**. Đây là lý do cần lập kế hoạch continuity trước khi mất key; nó không biến việc raw private-key escrow thành lựa chọn mặc định.

## 13. Pháp lý, attribution và non-repudiation

Escrow signing key có thể ảnh hưởng tới **ai được xem là người ký**, **ai kiểm soát private key** và **bằng chứng nào chứng minh chữ ký được tạo hợp lệ**. Những câu hỏi này phụ thuộc loại chữ ký, jurisdiction, trust service provider, hợp đồng và chính sách của tổ chức.

### 13.1. Chữ ký cá nhân và chữ ký tổ chức

- Với **chữ ký cá nhân**, private key có thể phải nằm dưới quyền kiểm soát của chính người ký hoặc thiết bị/dịch vụ được quy định. Tổ chức escrow raw private key có thể xung đột với mục tiêu chứng minh sự kiểm soát cá nhân.
- Với **chữ ký tổ chức**, tổ chức có thể là chủ thể ký và có thể cần cơ chế continuity; nhưng quyền ký phải gắn với **quy trình phê duyệt, người yêu cầu và service identity**, không phải mọi quản trị viên.
- Với **CA signing key**, key ceremony, CPS, HSM và quorum thường có yêu cầu đặc biệt do phạm vi trust.

Không khẳng định mọi luật đều cấm escrow hoặc mọi chữ ký có escrow đều vô hiệu. Cần đối chiếu **quy định áp dụng, tiêu chuẩn/trust framework và hồ sơ pháp lý** trước khi phê duyệt.

### 13.2. Escrow làm yếu non-repudiation như thế nào?

Non-repudiation không chỉ là tính chất toán học của thuật toán. Nó phụ thuộc **quản lý danh tính, kiểm soát private key, bằng chứng ký, timestamp, audit và quy định**.

Nếu một escrow custodian có thể khôi phục key và ký ngoài quy trình:

- Một chữ ký hợp lệ có thể do nhiều chủ thể tiềm năng tạo ra.
- HSM audit có thể không bao phủ chữ ký được tạo sau raw-key export.
- Khó chứng minh người ký ban đầu thực sự kiểm soát key ở thời điểm ký.
- Quy trình pháp lý có thể yêu cầu khai báo hoặc hạn chế việc tổ chức giữ key.

### 13.3. Bằng chứng cần lưu thay vì raw private key

Đối với chữ ký lịch sử, ưu tiên giữ:

- Original message/document bytes và signature.
- Public verification key/certificate chain.
- Key ID/version, algorithm và signature profile.
- Certificate status/revocation evidence theo thời điểm.
- Trusted timestamp và validation data nếu cần.
- Audit event về signer principal, request ID, approval và result.

Những dữ liệu này hỗ trợ kiểm tra **ai/đơn vị nào được hệ thống cho phép ký**, nhưng không tự bảo đảm kết luận pháp lý nếu quy trình custody không đáp ứng yêu cầu.

## 14. Java 17: mô hình policy quyết định backup signing key

Đoạn code sau minh họa cách **từ chối raw private-key export/escrow theo mặc định** và chỉ cho phép một số cơ chế HSM/threshold đã được phê duyệt. Nó không kết nối HSM thật và không tạo/serialize private key.

~~~java
import java.time.Instant;
import java.util.Objects;

public final class SigningKeyBackupPolicyDemo {
    private SigningKeyBackupPolicyDemo() {}

    enum KeyClass {
        PERSONAL_SIGNATURE,
        SERVICE_SIGNING,
        CODE_SIGNING,
        CA_ROOT
    }

    enum BackupMode {
        NONE,
        HSM_REPLICATION,
        HSM_SECURE_BACKUP,
        THRESHOLD_SIGNING,
        RAW_PRIVATE_KEY_ESCROW
    }

    record Request(
            KeyClass keyClass,
            BackupMode mode,
            boolean explicitApproval,
            boolean sameSecurityDomain,
            boolean destinationAllowlisted,
            int independentApprovals,
            int minimumApprovals,
            boolean revocationCheckPassed,
            boolean caSpecificApproval,
            Instant approvalExpiresAt
    ) {}

    record Decision(boolean allowed, String reason) {}

    static Decision evaluate(Request request, Instant now) {
        Objects.requireNonNull(request);
        Objects.requireNonNull(now);

        if (request.mode() == BackupMode.NONE) {
            return new Decision(true, "NO_PRIVATE_KEY_BACKUP_REQUESTED");
        }
        if (request.mode() == BackupMode.RAW_PRIVATE_KEY_ESCROW) {
            return new Decision(false, "RAW_PRIVATE_KEY_ESCROW_DENIED_BY_DEFAULT");
        }
        if (request.keyClass() == KeyClass.PERSONAL_SIGNATURE) {
            return new Decision(false, "PERSONAL_SIGNER_REQUIRES_SEPARATE_TRUST_POLICY");
        }
        if (!request.explicitApproval()) {
            return new Decision(false, "MISSING_EXPLICIT_APPROVAL");
        }
        if (request.approvalExpiresAt() == null ||
                !now.isBefore(request.approvalExpiresAt())) {
            return new Decision(false, "APPROVAL_EXPIRED");
        }
        if (!request.sameSecurityDomain() ||
                !request.destinationAllowlisted()) {
            return new Decision(false, "DESTINATION_OUTSIDE_APPROVED_BOUNDARY");
        }
        if (request.independentApprovals() < request.minimumApprovals() ||
                request.minimumApprovals() < 2) {
            return new Decision(false, "QUORUM_NOT_SATISFIED");
        }
        if (!request.revocationCheckPassed()) {
            return new Decision(false, "KEY_REVOKED_OR_STATUS_UNKNOWN");
        }
        if (request.keyClass() == KeyClass.CA_ROOT &&
                !request.caSpecificApproval()) {
            return new Decision(false, "CA_ROOT_REQUIRES_CA_SPECIFIC_APPROVAL");
        }
        return new Decision(true, "APPROVED_HSM_OR_THRESHOLD_MECHANISM");
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-28T00:00:00Z");

        Request rawExport = new Request(
                KeyClass.SERVICE_SIGNING,
                BackupMode.RAW_PRIVATE_KEY_ESCROW,
                true, true, true, 3, 2, true,
                false,
                Instant.parse("2026-12-01T00:00:00Z"));

        Request secureHsmBackup = new Request(
                KeyClass.SERVICE_SIGNING,
                BackupMode.HSM_SECURE_BACKUP,
                true, true, true, 2, 2, true,
                false,
                Instant.parse("2026-12-01T00:00:00Z"));

        Request revokedKeyBackup = new Request(
                KeyClass.SERVICE_SIGNING,
                BackupMode.HSM_SECURE_BACKUP,
                true, true, true, 2, 2, false,
                false,
                Instant.parse("2026-12-01T00:00:00Z"));

        Request caRootWithoutApproval = new Request(
                KeyClass.CA_ROOT,
                BackupMode.HSM_SECURE_BACKUP,
                true, true, true, 3, 2, true,
                false,
                Instant.parse("2026-12-01T00:00:00Z"));

        System.out.println("Raw escrow: " +
                evaluate(rawExport, now).reason());
        System.out.println("HSM backup: " +
                evaluate(secureHsmBackup, now).reason());
        System.out.println("Revoked key: " +
                evaluate(revokedKeyBackup, now).reason());
        System.out.println("CA root without CA approval: " +
                evaluate(caRootWithoutApproval, now).reason());
    }
}
~~~

Kết quả minh họa:

~~~text
Raw escrow: RAW_PRIVATE_KEY_ESCROW_DENIED_BY_DEFAULT
HSM backup: APPROVED_HSM_OR_THRESHOLD_MECHANISM
Revoked key: KEY_REVOKED_OR_STATUS_UNKNOWN
CA root without CA approval: CA_ROOT_REQUIRES_CA_SPECIFIC_APPROVAL
~~~

### 14.1. Giới hạn của policy demo

1. **Enum và record không thực thi HSM attributes/IAM**; production phải cấu hình backend và kiểm thử operation thật.
2. **sameSecurityDomain** là metadata đầu vào; caller không được tự khai giá trị true. Phải lấy từ registry/attestation đáng tin.
3. **independentApprovals** không chứng minh approvers thực sự độc lập; cần IAM/identity và audit.
4. **revocationCheckPassed** phải được xác minh từ control plane hiện hành, không lấy từ snapshot cũ.
5. **Personal signing key** có thể có quy trình thiết bị/recovery được chứng nhận; demo từ chối mọi backup mode để nhấn mạnh cần policy riêng, không phải kết luận pháp lý chung.
6. **CA root** có thể có quy trình secure backup đặc biệt; demo yêu cầu trường phê duyệt CA riêng ngoài approval thông thường.
7. Chưa có retention, backup object integrity, custody transfer, restore tests, legal hold hoặc destruction workflow.
8. Không có thao tác Export/Restore/Sign thực tế; code chỉ mô tả một policy gate.

### 14.2. Nguyên tắc triển khai

Không để client gửi explicitApproval=true, sameSecurityDomain=true hoặc revocationCheckPassed=true trong request rồi tin các trường đó. Chúng phải được lấy từ **approval service, HSM inventory, destination allowlist và revocation control plane** được xác thực. Nếu policy service không truy cập được, hành động backup/restore nhạy cảm nên **fail closed**.

## 15. Case study: Payments Signing Service cần DR

Một nền tảng thanh toán Java có:

- **Payments API:** Xác thực giao dịch và kiểm tra quyền phê duyệt.
- **Receipt Signing Service:** Ký biên nhận bằng Ed25519 private key trong HSM.
- **HSM cluster:** Hai vùng triển khai, có cơ chế HA/replication theo security domain.
- **Partner Gateway:** Verify biên nhận bằng public key từ trusted registry.
- **Security/PKI:** Quản lý key purpose, IAM, rotation, revocation và audit.
- **SRE/DR:** Đảm bảo RTO, failover và khôi phục.

### 15.1. Yêu cầu ban đầu

Đội vận hành đề xuất **export private key ra PKCS#8**, mã hóa bằng password và cất ở vault chung để “nếu HSM mất thì còn key ký tiếp”. Cách đề xuất này có các vấn đề:

1. Vault chung mở rộng trust boundary khỏi HSM.
2. Người có password/vault access có thể có raw private key và ký ngoài signing service.
3. HSM audit không bao phủ chữ ký được tạo từ bản export.
4. Một bản backup có thể bị copy, snapshot hoặc tồn tại ngoài retention.
5. Không có cơ chế chắc chắn ngăn restore key đã revoked sau compromise.

### 15.2. Thiết kế được chọn

Sau khi đánh giá RTO, partner rollout và khả năng HSM, tổ chức chọn:

- HSM replication giữa hai vùng trong **approved security domain**.
- HSM-native backup blob được bảo vệ theo backup domain và quorum.
- **Không export raw private key** ra file cho application/vault.
- Signer workload có quyền Sign theo key ID/purpose; SRE không có quyền Sign tùy ý.
- Custodian/operator chỉ tham gia backup/restore ceremony; không tự gửi payload ký.
- Public key/certificate history được lưu riêng trong trusted registry.
- Mọi DR restore phải kiểm tra **current revocation status** và cần activation approval.

### 15.3. Khi primary HSM hỏng

1. SRE khai báo DR và xác định đây là **availability failure**, chưa có dấu hiệu compromise.
2. IR/PKI kiểm tra key state và policy; xác nhận key vẫn được tin.
3. Traffic chuyển sang HSM replica đã được phê duyệt.
4. Signer xác thực bằng workload identity và tiếp tục Sign qua API.
5. Audit ghi HSM module/region, principal, key ID/version và kết quả.
6. Sau khi primary phục hồi, kiểm tra replication consistency, policy và logs.

Không cần export private key ra filesystem chỉ vì một HSM node hỏng.

### 15.4. Khi toàn bộ HSM cluster mất

Nếu secure backup còn và key chưa bị compromise, có thể tiến hành **quorum restore** vào HSM mới theo ceremony. Sau restore:

- Kiểm tra key attributes và backup provenance.
- Giữ key ở trạng thái chưa cho production Sign.
- Xác nhận owner/security approval và current revocation state.
- Kiểm tra public key fingerprint khớp key đã đăng ký.
- Kích hoạt signer workload theo scope và ghi audit.

Nếu backup không phục hồi được, tổ chức có thể **re-key** và phối hợp partner cập nhật public key. Không tạo raw-key escrow mới chỉ để tránh một lần migration.

### 15.5. Khi private signer bị compromise

Đây là tình huống khác hoàn toàn:

1. Chặn Sign bằng key-v1 và thu hồi grants/principals có liên quan.
2. Đánh dấu backup-v1 **không đủ điều kiện recovery**.
3. Không restore signer-v1 sang HSM DR để “khôi phục dịch vụ”.
4. Tạo signer-v2 từ boundary sạch và đăng ký public-v2.
5. Cập nhật partner trust/revocation và điều tra receipts đã ký.
6. Giữ public-v1/evidence lịch sử theo policy, nhưng không giữ đường Sign-v1.

**Backup được tạo trước sự cố không làm key trở nên an toàn.** Recovery phải tôn trọng revocation và incident state mới nhất.

## 16. Case study: CA root signing key và secure backup

Một CA root key có thể ký intermediate CA certificates, tạo ra trust chain được nhiều hệ thống chấp nhận. **Mất root private key** có thể khiến CA không thể phát hành hoặc thực hiện một số hoạt động quản trị theo quy trình. Nhưng **lộ root private key** có thể cho attacker khả năng phát hành chứng chỉ giả trong phạm vi trust của CA.

### 16.1. Vì sao CA root có nhu cầu đặc biệt?

- Root CA thường được giữ **offline** hoặc trong môi trường kiểm soát chặt.
- Việc thay root trust có thể cần cập nhật nhiều relying parties, thiết bị và hệ thống lâu đời.
- Một số hoạt động certificate lifecycle cần continuity của trust anchor.
- Root key có blast radius lớn nên mất khả năng phục hồi cũng có thể là rủi ro vận hành nghiêm trọng.

### 16.2. Secure backup không có nghĩa escrow tùy tiện

Một thiết kế có thể dùng:

- HSM offline hoặc partition riêng.
- HSM-native secure backup trong security domain được phê duyệt.
- Custodian quorum/dual control và key ceremony có witness.
- Vùng lưu backup tách biệt và kiểm soát vật lý.
- Restore chỉ vào HSM allowlist, không export raw private key.
- Audit/retention/restore tests và quy trình xử lý key compromise riêng.

Các yêu cầu cụ thể phải theo **Certificate Practice Statement (CPS), policy của CA, trust framework và tiêu chuẩn áp dụng**. Không sao chép một mô hình CA root sang service signer thông thường.

### 16.3. Root key bị compromise

Nếu root private key bị compromise, **không được khôi phục từ backup rồi tiếp tục phát hành certificate** như một sự cố phần cứng. Cần incident response về trust:

- Dừng các hoạt động CA liên quan.
- Đánh giá certificates/intermediates đã ký và relying parties.
- Xử lý trust anchor mới, certificate revocation/rollover theo PKI governance.
- Thông báo/đồng bộ với các bên tin CA theo quy định.
- Quarantine/destroy các backup của root key cũ theo quyết định có thẩm quyền.

**Secure backup hỗ trợ phục hồi khi mất/ hỏng thiết bị**, nhưng không được trở thành đường hồi sinh một CA key đã mất tin cậy.

## 17. Kiểm thử backup/recovery của signing key

Một quy trình backup chỉ đáng tin khi có **bằng chứng restore được, quyền được giới hạn và revocation không bị bypass**.

### 17.1. Ma trận kiểm thử

| Bài kiểm thử | Kết quả mong đợi |
| --- | --- |
| Application signer thử Export private key | Provider/IAM từ chối |
| Custodian đơn lẻ yêu cầu restore | Quorum/dual control từ chối |
| HSM backup blob đưa sang domain không được duyệt | Restore bị từ chối |
| Restore backup vào HSM allowlist trong DR | Chỉ thành công sau ceremony/approval |
| Key attributes sau restore | Sign-only/non-extractable/purpose giữ đúng theo provider |
| Restore thành công nhưng chưa có activation approval | Sign vẫn disabled |
| Key-v1 đã revoked, backup-v1 được yêu cầu restore | Workflow từ chối |
| Key-v1 bị compromised trước snapshot | Backup không được dùng để khôi phục signer-v1 |
| HSM node hỏng nhưng replica còn | Failover không cần raw key export |
| Toàn cluster mất, backup hợp lệ | Quorum restore theo runbook |
| Backup blob bị thay đổi | Integrity/provenance check phát hiện |
| Một custodian nghỉ việc | Quyền bị thu hồi và quorum được tái cấu hình |
| Hai người có cùng một admin credential | Test phát hiện không có độc lập thực sự; policy không chấp nhận |
| DR signer ký message ngoài scope | Authorization từ chối và audit cảnh báo |
| Sign operation từ HSM replica | Audit xác định được module/region/principal |
| Backup hết retention | Destruction workflow xử lý mọi bản sao theo policy |
| Restore snapshot cũ sau incident | Current revocation/tombstone ngăn key bị thu hồi sống lại |
| Re-key sau mất key | Public-v2 được phân phối và consumers Verify thành công |
| Verify chữ ký lịch sử sau private key destroy | Thành công khi public evidence và trust policy còn hợp lệ |
| Chữ ký v1 sau compromise | Verifier áp dụng revocation/trust policy, không chỉ Verify toán học |

### 17.2. Kiểm thử định kỳ

- **Backup creation test:** Chứng minh backup object được tạo đúng domain và custody.
- **Restore drill:** Thực hiện trong môi trường cô lập, có quorum và audit.
- **Failover test:** HSM replica có thể xử lý Sign theo policy khi node/vùng lỗi.
- **Revocation test:** Backup cũ không khôi phục key đã revoked/compromised.
- **Key attribute test:** Sign-only và non-exportability được giữ theo khả năng provider.
- **Consumer test:** Public key/certificate và signature history vẫn được xác minh đúng.
- **Custodian rotation drill:** Thay người giữ quyền mà không mất quorum hoặc tạo single point of failure.
- **Destruction test/evidence review:** Bản backup hết hạn được xử lý, không còn replica ngoài inventory.

Không thực hiện test Export raw private key trên production signer chỉ để chứng minh export bị chặn. Dùng test key hoặc negative operation được phê duyệt theo ranh giới provider.

## 18. Anti-patterns khi backup/escrow signing key

| Sai lầm | Rủi ro | Cách làm đúng |
| --- | --- | --- |
| **Áp dụng escrow của DEK/KEK cho private signer** | Mở thêm quyền mạo danh | Chính sách backup riêng theo key purpose |
| **Export private key ra PKCS#8/PEM rồi đặt password** | Raw key có thể được dùng ngoài HSM | HSM-native backup/replication hoặc re-key |
| **Gửi file backup qua email/chat** | Mất custody, khó kiểm soát bản sao | Approved secure backup domain và quorum |
| **Một administrator vừa backup, restore, vừa Sign** | Single-person control và insider risk | Separation of duties, dual control |
| **Mọi private keys dùng chung một escrow vault** | Blast radius tập trung | Tách theo owner, purpose, security domain |
| **Cho custodian quyền Sign nghiệp vụ** | Recovery authority trở thành signing authority | Custodian chỉ tham gia ceremony |
| **Restore tự động bật Sign** | Backup có thể bị lạm dụng ngay khi khôi phục | Restore disabled; activation approval riêng |
| **Restore key đã revoked vì backup còn hợp lệ** | Hồi sinh key compromise | Kiểm tra current revocation/tombstone |
| **Coi non-exportable là không cần audit** | API abuse vẫn có thể xảy ra | Audit Sign/restore/admin và content authorization |
| **Giữ private signer chỉ để Verify lịch sử** | Thêm khả năng ký giả không cần thiết | Giữ public key/certificate/evidence |
| **Coi certificate renewal là backup key** | Có thể không giữ được private material hoặc không đổi key | Tách reissue, rekey và backup |
| **Dùng backup raw key cho personal signature** | Có thể phá attribution/kiểm soát cá nhân | Theo trust framework; re-enroll/re-key khi cần |
| **Tạo bản sao trước khi kiểm tra key state** | Sao lưu key đã compromised/revoked | Preflight revocation và incident status |
| **Không kiểm tra attributes sau restore** | Key có thể trở thành exportable hoặc usage rộng | Readback attributes và negative tests |
| **Không kiểm tra backup retention** | Bản sao cũ tồn tại vô thời hạn | Inventory, review và destruction evidence |
| **Không test custodian unavailable** | Recovery thất bại khi khẩn cấp | Quorum drills và custodian lifecycle |
| **Dùng một quorum share trên nhiều thiết bị của cùng người** | Quorum giả, không độc lập | Independent custodians/devices/locations |
| **Dùng backup làm phương án cho mọi outage** | Tăng quyền không cần thiết | HA/replication, failover và re-key |
| **Không tách lost key và compromised key** | Restore key attacker có thể sử dụng | Phân loại sự cố trước khi recovery |
| **Chỉ giữ raw key mà không giữ public trust history** | Không hỗ trợ Verify/attribution đúng cách | Lưu public keys, certificates, timestamps và audit |

## 19. Checklist đánh giá “Không escrow signing key tùy tiện”

Trước khi duyệt backup/recovery design, hãy kiểm tra:

1. **Key purpose:** Đây là personal, service, code-signing, TLS, intermediate CA hay root CA key?
2. **Business need:** Cần khôi phục đúng key identity hay chỉ cần service tiếp tục ký?
3. **Historical verification:** Public key/certificate/evidence đã đủ cho chữ ký cũ chưa?
4. **Re-key option:** Có thể sinh key pair mới và cập nhật consumers không?
5. **Escrow distinction:** Cơ chế đề xuất là raw escrow, encrypted copy, HSM backup, replication hay threshold signing?
6. **Threat model:** Ai có thể lấy backup, restore, activate hoặc sử dụng key?
7. **Blast radius:** Key có đại diện cho nhiều tenants, CA trust, release pipeline hoặc payment domain?
8. **Attribution:** Escrow có ảnh hưởng quyền kiểm soát của người ký hoặc non-repudiation không?
9. **Compliance:** Có CPS, trust service, quy định chữ ký điện tử hoặc hợp đồng chi phối?
10. **Least-risk mechanism:** HSM HA/replication/native backup hoặc re-key có đủ không?
11. **Non-exportability:** Raw private key có thể rời HSM không? Semantics được kiểm chứng ở đâu?
12. **Backup domain:** Backup object chỉ restore trong security domain/destination allowlist?
13. **Quorum:** Có bao nhiêu custodian độc lập và approval factors?
14. **Separation of duties:** Owner, approver, operator, custodian và auditor có tách?
15. **Custodian lifecycle:** Có quy trình thay người, mất thiết bị và revoke quyền?
16. **Restore state:** Key sau restore có disabled cho đến activation approval?
17. **Purpose preservation:** Sign-only/algorithm/key attributes có được giữ?
18. **Revocation check:** Backup đã bị quarantine nếu key bị compromised/revoked?
19. **Audit:** Có log backup, copy, restore, activation, Sign và destruction?
20. **Offline custody:** Bản backup và recovery factors có tách khỏi production signer?
21. **Retention:** Có expiry, review date và inventory mọi replicas?
22. **DR objectives:** RTO/RPO có chứng minh cần cùng key hay re-key được?
23. **Failover:** Có HSM replica hoặc DR region được test?
24. **Restore drill:** Có diễn tập trong môi trường cô lập và quorum thật?
25. **Negative tests:** Application không Export; custodian đơn lẻ không Restore/Sign?
26. **Historical evidence:** Public key/certificate chain, signed bytes, timestamp và revocation evidence được giữ?
27. **Incident handling:** Có phân biệt lost/unavailable với compromised?
28. **Backup destruction:** Có kiểm soát mọi bản copy và bằng chứng hủy?
29. **Exception governance:** Escrow exception có owner, expiry, approvers và residual-risk acceptance?
30. **Independent review:** Security/PKI, data owner, audit và legal/compliance đã xem xét?

## 20. Ghi nhớ

- **Signing key là quyền tạo chữ ký dưới một danh tính**, vì vậy bản backup có thể trở thành một quyền mạo danh mới.
- **Không áp dụng máy móc escrow của encryption key cho signing key.** Mất DEK/KEK có thể làm mất khả năng đọc dữ liệu cũ; mất private signer thường làm mất khả năng ký mới, trong khi public key vẫn có thể Verify chữ ký lịch sử.
- **Backup, replication, escrow và recovery khác nhau.** HSM-native backup hoặc replication có thể giữ key trong security boundary, nhưng vẫn cần threat model số điểm có thể Sign.
- **Không export raw private signing key ra file/vault chỉ để tiện DR.** Ưu tiên HSM HA/replication, secure backup trong HSM domain, threshold/MPC hoặc re-key tùy nhu cầu.
- **Một escrow exception phải có business justification, key classification, quorum, dual control, separation of duties, retention, audit và expiry.**
- **Custodian không mặc nhiên có quyền ký nghiệp vụ.** Restore, activation và Sign phải là các quyết định/quyền riêng.
- **Backup không được override revocation.** Không khôi phục signer đã compromised/revoked chỉ vì backup được tạo trước sự cố.
- **Nếu private signer bị mất nhưng chưa compromise**, có thể tạo key pair mới, cập nhật public trust và giữ public verification evidence cũ.
- **Nếu private signer bị compromise**, phải containment/revoke, thay key và cập nhật relying parties; không restore key cũ để duy trì availability.
- **CA root/intermediate keys có thể cần secure backup đặc biệt**, nhưng phải tuân theo CPS, HSM ceremony, quorum và trust governance.
- **Forensics, non-repudiation và pháp lý phụ thuộc custody/audit/timestamp**, không chỉ thuật toán chữ ký.
- **Kiểm thử backup/recovery phải chứng minh cả khả năng khôi phục lẫn khả năng từ chối**: raw export, single-person restore, restore key revoked và Sign ngoài scope.

Trước khi escrow một signing key, hãy trả lời ba câu hỏi: **“Nếu mất key, chúng ta có thực sự cần tiếp tục ký bằng đúng key identity này không?”, “Có thể đạt RTO bằng HSM replication, secure backup hoặc re-key mà không tạo raw private-key copy không?”, “Nếu recovery xảy ra, ai có thể khôi phục, ai được phép Sign và làm sao chứng minh key đã bị revoke không thể sống lại?”** Chỉ khi nhu cầu và rủi ro được chứng minh, ngoại lệ mới được phê duyệt bằng **policy, ceremony, quorum, audit và restore tests**.


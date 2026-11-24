# Credential renewal

> **Chương:** Credential lifecycle  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Gia hạn và thay thế credential an toàn trong suốt vòng đời, xử lý thời hạn, xoay vòng khóa/secret, chuyển đổi không gián đoạn, thu hồi credential cũ và phản ứng khi có dấu hiệu lộ.

## 1. Credential renewal là gì?

**Credential renewal (gia hạn credential)** là quá trình duy trì khả năng xác thực bằng cách cấp mới, thay thế hoặc cập nhật một credential trước khi nó hết hiệu lực hoặc khi có lý do bảo mật/nghiệp vụ. Credential có thể là mật khẩu, khóa API, chứng chỉ số, khóa SSH, passkey, seed MFA hoặc credential của workload/service account.

Ví dụ, một dịch vụ nội bộ dùng API key để gọi hệ thống thanh toán. Trước khi key hiện tại hết hạn hoặc theo chính sách xoay vòng, nhóm vận hành tạo key mới, cập nhật secret store, triển khai ứng dụng dùng key mới, xác nhận request thành công rồi thu hồi key cũ. Nếu thu hồi key cũ trước khi mọi instance chuyển đổi, dịch vụ có thể ngừng hoạt động; nếu giữ key cũ quá lâu, rủi ro khi key đã lộ sẽ kéo dài.

Renewal không chỉ là đổi một chuỗi bí mật. Đó là một thay đổi có kiểm soát đối với danh tính, quyền, hệ thống tiêu thụ credential, trạng thái phiên và khả năng khôi phục. Quy trình phải biết credential nào đang tồn tại, ai sở hữu, dùng ở đâu, khi nào hết hạn, cách thay thế và cách xác nhận credential cũ không còn được chấp nhận.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt renewal, rotation, replacement, rekeying, re-issuance và revocation.
- Xây dựng inventory và ownership cho credential.
- Chọn cách gia hạn phù hợp với mật khẩu, chứng chỉ, API key, SSH key, passkey và credential của workload.
- Thiết kế chuyển đổi có overlap, kiểm tra và rollback an toàn.
- Xử lý credential hết hạn, mất, bị lộ hoặc không còn được phép sử dụng.
- Tự động hóa renewal mà không để secret xuất hiện trong log hoặc pipeline.
- Kiểm thử việc thu hồi credential cũ và xử lý sự cố.

## 2. Renewal, rotation và revocation khác nhau thế nào?

Các thuật ngữ liên quan thường được dùng lẫn nhau, nhưng mô tả những thay đổi khác nhau:

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Renewal** | Duy trì hiệu lực bằng cách cấp mới/gia hạn theo chính sách | Gia hạn chứng chỉ TLS trước ngày hết hạn |
| **Rotation** | Thay credential đang dùng bằng credential mới theo chu kỳ hoặc sự kiện | Tạo API key mới rồi chuyển ứng dụng sang key đó |
| **Replacement** | Thay credential cũ bằng credential khác, thường do mất hoặc đổi phương thức | Thay khóa bảo mật bị mất |
| **Rekeying** | Tạo cặp khóa mới thay cho cặp khóa hiện tại | Tạo private/public key mới cho chứng chỉ client |
| **Re-issuance** | Cấp lại credential hoặc chứng thư theo quy trình phát hành | CA cấp lại chứng chỉ sau khi tạo CSR mới |
| **Revocation** | Vô hiệu hóa credential trước khi hết hạn | Thu hồi chứng chỉ hoặc API key bị lộ |
| **Expiration** | Credential tự hết hiệu lực theo thời gian | Chứng chỉ hết hạn hoặc token quá thời điểm exp |

Renewal có thể đi cùng rotation hoặc rekeying, nhưng không phải lúc nào cũng vậy. Một chứng chỉ có thể được cấp lại với cùng public key, trong khi một quy trình bảo mật tốt hơn có thể yêu cầu tạo key pair mới. Gia hạn thời hạn không đồng nghĩa private key đã được thay mới.

### Credential không có cùng cơ chế hết hạn

- Chứng chỉ số thường có thời điểm hết hiệu lực và cần gia hạn trước khi hết hạn.
- Access token thường có thời hạn ngắn và được cấp mới qua authorization server.
- API key có thể có hạn hoặc tồn tại đến khi bị thu hồi tùy thiết kế.
- Mật khẩu có thể không có ngày hết hạn định kỳ; thay đổi khi có dấu hiệu lộ, người dùng yêu cầu hoặc chính sách phù hợp yêu cầu.
- Passkey thường không cần gia hạn định kỳ như chứng chỉ; cần quản lý đăng ký, thay thế, mất thiết bị và thu hồi.

Không áp dụng một lịch rotation chung cho mọi loại credential.

## 3. Vòng đời credential

Một credential thường đi qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Planned
    Planned --> Issued
    Issued --> Active
    Active --> RenewalPending
    RenewalPending --> NewCredentialActive
    NewCredentialActive --> OldCredentialRetired
    Active --> Revoked
    RenewalPending --> Revoked
    Active --> Expired
    NewCredentialActive --> Revoked
    OldCredentialRetired --> [*]
    Revoked --> [*]
    Expired --> [*]
~~~

Một quy trình renewal cần quản lý cả trạng thái của credential mới lẫn credential cũ. Không nên đánh dấu credential cũ đã nghỉ hưu chỉ vì credential mới được tạo; phải xác minh các client đã chuyển đổi và chính sách chấp nhận credential cũ đã được cập nhật.

### Các giai đoạn

1. **Inventory:** xác định credential, chủ sở hữu, mục đích, quyền và nơi sử dụng.
2. **Plan:** chọn thời điểm, phương thức, người phê duyệt và phương án dự phòng.
3. **Issue:** tạo credential mới qua hệ thống phát hành đáng tin cậy.
4. **Distribute:** chuyển secret/key/certificate tới đúng thành phần bằng kênh bảo vệ.
5. **Activate:** bật credential mới và kiểm tra hoạt động.
6. **Migrate:** chuyển từng consumer sang credential mới.
7. **Verify:** xác nhận request mới thực sự dùng credential mới.
8. **Retire/revoke:** ngừng chấp nhận credential cũ.
9. **Audit:** lưu kết quả, thời điểm, người/phần mềm thực hiện và ngoại lệ.

## 4. Inventory và ownership

Không thể gia hạn an toàn một credential mà tổ chức không biết nó tồn tại hoặc đang được dùng ở đâu.

Một credential inventory nên ghi nhận:

| Trường | Mục đích |
|---|---|
| credential_id | Định danh bản ghi, không phải secret |
| credential_type | Password, API key, certificate, passkey, SSH key... |
| subject_or_owner | Người dùng, service account hoặc workload sở hữu |
| issuer | Hệ thống/CA phát hành |
| consumer | Ứng dụng, host, API hoặc RP sử dụng |
| scope_or_permissions | Quyền được credential đại diện |
| created_at | Thời điểm phát hành |
| expires_at | Hạn hết hiệu lực nếu có |
| last_used_at | Lần cuối được sử dụng nếu có telemetry |
| rotation_policy | Chu kỳ hoặc trigger renewal |
| status | Planned, active, pending, revoked, expired... |
| owner_team | Nhóm chịu trách nhiệm |

Không lưu secret thô trong inventory. Lưu tham chiếu tới secret manager, certificate store hoặc credential registry. Phân biệt chủ sở hữu nghiệp vụ với hệ thống phát hành và đội vận hành.

### Phát hiện credential không còn owner

Credential mồ côi thường xuất hiện khi nhân viên nghỉ việc, service bị thay thế hoặc môi trường cũ không được dọn. Quy trình cần:

- Tìm credential không có owner/team đang hoạt động.
- Xác định consumer còn sử dụng hay không.
- Kiểm tra quyền và lịch sử sử dụng.
- Chuyển ownership hoặc thu hồi có kiểm soát.
- Không xóa một key chỉ vì không có metadata nếu chưa kiểm tra tác động.

## 5. Khi nào cần renewal hoặc rotation?

Trigger phụ thuộc loại credential và mức rủi ro:

- Đến gần ngày hết hạn của chứng chỉ hoặc credential có lifetime.
- Credential bị lộ, bị mất hoặc nghi bị sao chép.
- Người sở hữu rời tổ chức hoặc thay đổi vai trò.
- Thay đổi quyền, tenant, môi trường hoặc mục đích sử dụng.
- Có sự cố ở CA, secret manager, endpoint hoặc hệ thống phát hành.
- Thuật toán hoặc kích thước khóa không còn được chấp nhận.
- Phát hiện credential dùng ở vị trí không mong đợi.
- Có yêu cầu tuân thủ hoặc chính sách nội bộ cụ thể.
- Đến lịch rotation đã được đánh giá cho loại secret đó.

### Rotation định kỳ không giải quyết mọi vấn đề

Rotation thường xuyên có thể giảm thời gian sử dụng của một secret bị lộ, nhưng cũng tạo rủi ro vận hành nếu quy trình triển khai sai. Nếu key mới được lưu ở cùng nơi không an toàn, hoặc pipeline ghi secret vào log, rotation chỉ tạo thêm bản sao của secret.

Với mật khẩu người dùng, ép thay đổi theo lịch ngắn mà không có dấu hiệu compromise có thể khiến người dùng chọn biến thể dễ đoán hoặc ghi lại ở nơi không an toàn. Nên ưu tiên mật khẩu dài, kiểm tra mật khẩu bị lộ, MFA chống phishing và đổi mật khẩu khi có bằng chứng lộ hoặc yêu cầu hợp lệ. Tuân thủ tiêu chuẩn/nghĩa vụ áp dụng cho tổ chức nếu chúng quy định khác.

## 6. Gia hạn mật khẩu người dùng

Mật khẩu thường được thay đổi qua luồng đổi mật khẩu hoặc reset password. Hai thao tác có mức assurance khác nhau:

- **Change password:** người dùng đang đăng nhập và chứng minh quyền kiểm soát tài khoản theo chính sách trước khi đặt mật khẩu mới.
- **Password reset:** người dùng không có mật khẩu hiện tại hoặc đã mất quyền truy cập; cần recovery flow để xác minh lại chủ thể.

### Quy trình đổi mật khẩu an toàn

1. Xác thực lại khi cần, đặc biệt với session cũ hoặc hành động nhạy cảm.
2. Kiểm tra mật khẩu mới theo chính sách độ dài, blocklist và chống mật khẩu phổ biến/bị lộ.
3. Không áp đặt quy tắc thay ký tự máy móc nếu không cần thiết.
4. Hash mật khẩu bằng password hashing scheme phù hợp với salt riêng và tham số chi phí được quản lý.
5. Cập nhật verifier một cách nguyên tử.
6. Xử lý session/refresh token theo chính sách, nhất là khi đổi do nghi ngờ compromise.
7. Gửi thông báo bảo mật tới kênh đã xác minh.
8. Ghi audit nhưng không log mật khẩu cũ hoặc mới.

### Khi nào nên yêu cầu đổi?

- Người dùng chủ động yêu cầu.
- Có bằng chứng mật khẩu bị lộ hoặc xuất hiện trong credential stuffing.
- Tổ chức phát hiện kho verifier hoặc hệ thống xử lý mật khẩu bị compromise.
- Tài khoản được khôi phục và chính sách yêu cầu credential mới.
- Chính sách pháp lý/ngành nghề cụ thể yêu cầu.

Không coi việc hết một khoảng thời gian tùy ý là bằng chứng mật khẩu bị lộ. Nếu có dấu hiệu compromise, ngoài đổi mật khẩu còn cần thu hồi session, refresh token và kiểm tra MFA/recovery method.

### Không gửi mật khẩu qua notification

Thông báo chỉ xác nhận thay đổi và hướng dẫn người dùng tự truy cập website/app chính thức. Không gửi mật khẩu mới, link có quyền reset lâu dài hoặc mã bí mật trong email/SMS.

## 7. Gia hạn chứng chỉ số

Chứng chỉ số liên kết public key với danh tính hoặc thuộc tính của một chủ thể theo chính sách của Certificate Authority (CA). Chứng chỉ có thời hạn hiệu lực; ứng dụng cần thay mới trước khi hết hạn để tránh lỗi TLS, mTLS hoặc xác thực client.

### Renewal và rekeying

- **Renew với cùng key pair:** tạo CSR hoặc yêu cầu cấp mới dùng lại public key hiện tại. Việc này có thể giảm thay đổi ở consumer nhưng không thay private key.
- **Renew với key pair mới:** tạo private/public key mới, cấp chứng chỉ mới và chuyển consumer sang key mới. Cách này phù hợp khi cần giảm rủi ro key cũ hoặc theo chính sách.

Nếu private key nghi bị lộ, cấp chứng chỉ mới với cùng key pair không xử lý được nguyên nhân. Phải tạo key pair mới, thu hồi chứng chỉ cũ và đánh giá nơi key đã bị lộ.

### Quy trình certificate renewal

1. Theo dõi thời điểm hết hạn và đặt cảnh báo trước thời hạn đủ để xử lý sự cố.
2. Xác định subject/SAN, EKU, key usage, CA, thuật toán và consumer.
3. Quyết định giữ key hay rekey dựa trên threat model.
4. Tạo CSR và private key trong vùng bảo vệ phù hợp.
5. Xác minh yêu cầu cấp phát và domain/identity control theo chính sách CA.
6. Nhận certificate mới và kiểm tra chain, SAN, EKU, validity, algorithm.
7. Triển khai vào keystore/secret store và cập nhật consumer.
8. Kiểm tra handshake hoặc xác thực mTLS trên môi trường thực tế.
9. Thu hồi chứng chỉ cũ nếu cần, rồi gỡ key/certificate cũ khỏi nơi sử dụng.
10. Cập nhật inventory và cảnh báo.

### Overlap có kiểm soát

Có thể cho phép chứng chỉ cũ và mới cùng hợp lệ trong một khoảng chuyển đổi để các node cập nhật lần lượt. Overlap phải có giới hạn và kết thúc bằng việc gỡ bỏ hoặc thu hồi chứng chỉ cũ. Không để hai chứng chỉ cùng hoạt động vô thời hạn chỉ vì không biết consumer nào còn dùng bản cũ.

### Thu hồi và trạng thái chứng chỉ

Khi chứng chỉ bị compromise, CA có thể thu hồi và công bố trạng thái qua CRL hoặc OCSP tùy hệ sinh thái. Consumer cần được cấu hình và vận hành để kiểm tra trạng thái theo yêu cầu. Việc thu hồi không đảm bảo mọi client lập tức ngừng chấp nhận chứng chỉ nếu chúng không kiểm tra trạng thái hoặc dùng cache cũ.

## 8. Xoay vòng API key và application secret

API key và client secret thường được dùng bởi ứng dụng, script, tích hợp hoặc service account. Chúng có thể được lưu trong secret manager, biến môi trường hoặc cấu hình triển khai.

### Quy trình xoay vòng không gián đoạn

~~~mermaid
sequenceDiagram
    participant O as Owner / Operator
    participant M as Secret manager
    participant A as Application instances
    participant S as API server
    O->>M: Tạo key version mới
    M->>S: Đăng ký public verifier / key mới
    M-->>A: Cấp key mới qua kênh bảo vệ
    A->>S: Gửi request bằng key mới
    S->>S: Xác minh key mới và scope
    S-->>A: Request thành công
    A->>S: Ngừng dùng key cũ trên mọi instance
    O->>S: Thu hồi key cũ
    S-->>O: Key cũ không còn hợp lệ
    O->>M: Đánh dấu version cũ retired
~~~

### Các bước

1. Tạo key mới với scope tối thiểu và owner rõ ràng.
2. Đăng ký key mới ở phía server mà không xóa key cũ ngay.
3. Cập nhật secret manager và triển khai consumer theo từng đợt.
4. Xác nhận mọi instance, job và worker đã dùng key mới.
5. Theo dõi request còn sử dụng key cũ.
6. Thu hồi key cũ sau khi đạt điều kiện chuyển đổi.
7. Kiểm tra key cũ bị từ chối và lưu audit.

### Dual-active không có nghĩa dual-trust vô thời hạn

Trong thời gian overlap, cả hai key có thể được chấp nhận để tránh downtime. Hãy giới hạn cửa sổ overlap, theo dõi từng key ID và có deadline thu hồi. Nếu key cũ bị lộ, không nhất thiết chờ migration bình thường; có thể cần thu hồi khẩn cấp và chấp nhận gián đoạn có kiểm soát.

### Không ghi secret vào log hoặc pipeline

- Không in giá trị secret trong lệnh shell, build log hoặc exception.
- Dùng secret manager và cơ chế cấp phát ngắn hạn nếu có thể.
- Giới hạn quyền đọc secret theo workload/role.
- Tránh đưa secret vào source code, image layer hoặc artifact.
- Không gửi key qua chat hoặc ticket không được bảo vệ.
- Kiểm tra telemetry để chắc rằng log không chứa Authorization header.

## 9. SSH key và khóa truy cập quản trị

SSH key thường có cặp public/private. Public key được cài trên server hoặc hệ thống quản lý danh tính; private key được giữ ở client hoặc hardware authenticator.

### Thay SSH key

1. Tạo key pair mới bằng thuật toán được tổ chức chấp nhận.
2. Bảo vệ private key bằng passphrase và/hoặc hardware security key khi phù hợp.
3. Đăng ký public key mới trên hệ thống quản lý hoặc host mục tiêu.
4. Kiểm tra truy cập bằng key mới ở một phiên riêng.
5. Gỡ public key cũ khỏi mọi nơi đã cài.
6. Thu hồi key qua central access management nếu có.
7. Kiểm tra log đăng nhập và cập nhật inventory.

Nếu private key cũ bị lộ, phải coi mọi hệ thống đã tin public key đó có nguy cơ. Xác định phạm vi host, account, agent forwarding và các bản sao private key.

### Tránh lockout

Đừng xóa key duy nhất đang hoạt động trước khi kiểm tra key mới và phương thức break-glass. Với hệ thống quan trọng, có thể cần hai người phê duyệt, console access hoặc phương thức khôi phục được kiểm soát.

## 10. Passkey và MFA credential

Passkey và authenticator MFA có vòng đời khác chứng chỉ hoặc API key.

### Passkey

Passkey thường không có ngày hết hạn ngắn theo kiểu chứng chỉ. Thay vì gia hạn định kỳ, tổ chức quản lý:

- Đăng ký passkey sau khi xác thực đủ mạnh.
- Cho phép người dùng đăng ký nhiều passkey/khóa bảo mật dự phòng.
- Xem và thu hồi credential theo thiết bị hoặc credential ID.
- Thay thế khi thiết bị mất, credential bị nghi lộ hoặc tài khoản bị compromise.
- Xử lý passkey đồng bộ theo hệ sinh thái và chính sách của nhà cung cấp.
- Yêu cầu xác thực lại trước khi xóa credential cuối cùng hoặc thêm phương thức recovery mới.

Không xóa passkey cũ chỉ vì người dùng vừa đăng ký passkey mới. Trước tiên xác nhận credential mới dùng được và người dùng còn phương thức dự phòng phù hợp.

### TOTP và authenticator seed

Seed TOTP là secret dài hạn dùng tạo mã theo thời gian. Nếu thiết bị mất hoặc seed bị lộ:

1. Xác minh người yêu cầu reset MFA bằng recovery process phù hợp.
2. Vô hiệu hóa seed cũ và recovery code đã dùng/không còn an toàn.
3. Tạo seed mới bằng nguồn ngẫu nhiên an toàn.
4. Đăng ký authenticator mới và kiểm tra mã.
5. Cấp recovery code mới nếu chính sách cho phép.
6. Thông báo và xem xét thu hồi session.

Không gửi seed TOTP hoặc recovery code qua email. Không để người dùng tiếp tục dùng seed cũ sau khi đã xác định compromise.

### Push authenticator

Khi thay điện thoại hoặc cài lại ứng dụng, cần đăng ký thiết bị mới và thu hồi registration cũ theo quy trình. Push approval cần chống MFA fatigue và number matching/context binding khi nền tảng hỗ trợ. Một push token mới không tự chứng minh người đăng ký là chủ tài khoản.

## 11. Workload identity và credential ngắn hạn

Service account, container, VM, job và workload có thể dùng certificate, signed token hoặc credential được cấp động. Credential ngắn hạn giúp giảm cửa sổ sử dụng khi bị lộ và giảm nhu cầu lưu secret tĩnh lâu dài.

### Ưu tiên cấp credential theo danh tính workload

Thay vì đặt một API key dùng chung trong image, workload có thể chứng minh danh tính với hệ thống cấp phát rồi nhận credential ngắn hạn theo quyền cần thiết. Mô hình có thể dùng workload identity federation, mTLS hoặc hệ thống cấp certificate nội bộ.

### Renewal tự động

- Workload lấy credential từ issuer đã cấu hình và xác thực.
- Credential mới được cấp trước khi credential cũ hết hạn.
- Consumer cập nhật credential trong bộ nhớ hoặc secret store.
- Health check xác nhận request dùng credential mới.
- Credential cũ hết hiệu lực theo TTL hoặc bị thu hồi.
- Nếu issuer không khả dụng, workload xử lý theo giới hạn an toàn đã định; không kéo dài credential vô thời hạn.

### Không biến fallback thành credential vĩnh viễn

Nếu hệ thống cấp phát tạm ngừng, việc dùng một secret tĩnh dự phòng không thời hạn có thể làm mất lợi ích của credential ngắn hạn. Fallback cần thời gian giới hạn, quyền tối thiểu, audit và điều kiện quay lại luồng chuẩn.

## 12. Overlap, migration và rollback

Gia hạn credential trong hệ thống phân tán thường không thể cập nhật mọi consumer cùng một thời điểm. Overlap giúp chuyển đổi an toàn nhưng tạo khoảng thời gian hai credential cùng có hiệu lực.

### Mẫu triển khai

~~~mermaid
flowchart TD
    A["Inventory + owner + consumers"] --> B["Issue credential mới"]
    B --> C["Register new credential"]
    C --> D["Deploy consumers theo từng đợt"]
    D --> E{"Health check và telemetry đạt?"}
    E -->|"Không"| F["Dừng rollout / rollback consumer"]
    F --> G["Điều tra, giữ trạng thái an toàn"]
    E -->|"Có"| H["Xác nhận không còn traffic dùng credential cũ"]
    H --> I["Revoke credential cũ"]
    I --> J["Verify old credential bị từ chối"]
    J --> K["Close change và audit"]
~~~

### Điều kiện trước khi thu hồi key cũ

- Mọi consumer đã được xác định.
- Các instance/worker/job đã chuyển sang key mới.
- Request thực tế thành công bằng key mới.
- Không còn traffic hợp lệ dùng key cũ trong cửa sổ quan sát đã chọn.
- Có phương án rollback không yêu cầu tái sử dụng key đã bị compromise.
- Người chịu trách nhiệm phê duyệt thu hồi đã rõ.

### Rollback không phải luôn khôi phục credential cũ

Nếu key mới gây lỗi do cấu hình, có thể rollback ứng dụng trong khi key cũ vẫn còn hợp lệ trong overlap. Nhưng nếu key cũ bị lộ, không được khôi phục nó chỉ để làm dịch vụ chạy lại. Cần sửa cấu hình hoặc cấp credential khác.

## 13. Thu hồi khẩn cấp khi credential bị lộ

Renewal theo lịch và phản ứng compromise là hai quy trình khác nhau. Khi có bằng chứng credential bị lộ, ưu tiên containment và điều tra; không chờ đến ngày rotation kế tiếp.

### Quy trình ứng phó

1. Xác định loại credential, owner, scope và consumer.
2. Đánh giá khả năng attacker đang sử dụng credential.
3. Thu hồi hoặc vô hiệu hóa credential bị lộ theo thứ tự giảm tác động.
4. Cấp credential mới qua kênh an toàn nếu hệ thống cần tiếp tục hoạt động.
5. Thu hồi session, refresh token hoặc quyền ủy quyền liên quan khi phù hợp.
6. Kiểm tra log truy cập, thay đổi quyền và dữ liệu đã bị truy cập.
7. Xác định nguồn lộ: log, source code, CI/CD, endpoint, backup hay con người.
8. Xóa secret khỏi nơi lưu không an toàn và xử lý bản sao theo quy trình.
9. Thông báo người dùng/đội vận hành theo chính sách sự cố.
10. Cập nhật inventory, incident record và biện pháp phòng ngừa.

### Thu hồi không đồng nghĩa mọi bản sao lập tức mất hiệu lực

Một JWT tự chứa có thể tiếp tục được chấp nhận đến thời điểm hết hạn nếu resource server không kiểm tra trạng thái. Một chứng chỉ đã thu hồi có thể vẫn được client chấp nhận nếu client không kiểm tra CRL/OCSP hoặc dùng cache cũ. Một API key có thể vẫn được một node cache chấp nhận.

Sau khi revoke, cần kiểm tra từng consumer và cơ chế cache/introspection/denylist để xác nhận trạng thái có hiệu lực trên toàn hệ thống.

## 14. Tự động hóa renewal

Tự động hóa giảm lỗi do con người và giúp xử lý nhiều credential đúng hạn, nhưng automation có quyền phát hành/thu hồi credential cũng là một tài sản nhạy cảm.

### Nguyên tắc

- Tự động phát hiện credential sắp hết hạn.
- Có owner và consumer rõ trước khi thực hiện.
- Dùng workload identity hoặc quyền tối thiểu để gọi issuer/secret manager.
- Không ghi secret vào log, artifact hoặc thông báo.
- Có idempotency để retry không tạo nhiều credential không cần thiết.
- Có health check sau khi triển khai.
- Có deadline thu hồi credential cũ.
- Có cảnh báo khi renewal thất bại hoặc sắp hết hạn.
- Có audit và phê duyệt cho thay đổi đặc quyền hoặc rủi ro cao.

### Lập lịch theo thời hạn còn lại

Hệ thống nên cảnh báo theo nhiều mốc trước khi hết hạn, đủ thời gian xử lý lỗi CA, DNS, approval hoặc deployment. Không đợi đến phút cuối mới chạy renewal.

### Xử lý lỗi tự động

Nếu renewal thất bại:

- Giữ credential hiện tại nếu nó còn hợp lệ và chưa bị compromise.
- Retry có backoff và giới hạn.
- Báo owner khi vượt ngưỡng.
- Không xóa credential cũ chỉ vì job renewal đã bắt đầu.
- Nếu credential cũ sắp hết hạn, chuyển sang quy trình khẩn cấp/maintenance đã chuẩn bị.

Nếu credential cũ bị lộ, không tiếp tục dùng nó chỉ vì automation cấp mới thất bại. Cần áp dụng incident response và phương án tạm thời có kiểm soát.

## 15. Ví dụ quy trình xoay vòng API key

**Bối cảnh:** Một backend gọi dịch vụ báo cáo bằng API key. Key cũ còn hoạt động, nhưng đến kỳ rotation theo chính sách. Ứng dụng chạy nhiều instance ở hai vùng triển khai.

### Kế hoạch

1. Inventory xác định key ID, owner team, quyền reports:read và các instance tiêu thụ.
2. Secret manager tạo version mới; secret chỉ được phân phối cho workload được phép.
3. API server chấp nhận key mới và key cũ trong khoảng overlap có deadline.
4. Triển khai instance theo từng vùng, kiểm tra health check và request metrics theo key ID.
5. Chờ hết chu kỳ của worker/job cũ; xác nhận không còn request hợp lệ bằng key cũ.
6. Thu hồi key cũ ở API server.
7. Gửi request thử bằng key cũ trong môi trường kiểm thử để xác nhận bị từ chối.
8. Đóng change, cập nhật inventory và lưu audit.

### Nếu một vùng chưa chuyển đổi

Không thu hồi key cũ một cách mù quáng nếu đây là rotation bình thường và chưa có dấu hiệu compromise. Dừng rollout, xác định instance chưa cập nhật và xử lý. Nếu key cũ bị lộ, ưu tiên thu hồi và chuyển vùng còn lại sang key mới hoặc phương án khẩn cấp; chấp nhận gián đoạn có kiểm soát nếu cần.

### Kết quả mong đợi

Key mới hoạt động trên mọi consumer, key cũ bị từ chối, không có secret trong log và quyền của key mới không rộng hơn mức cần thiết.

## 16. Kiểm thử credential renewal

Kiểm thử trong môi trường được phép với credential và consumer thử nghiệm:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Credential sắp hết hạn | Cảnh báo đến đúng owner trước thời hạn |
| Certificate được cấp mới | Chain, SAN, EKU, key usage và validity được kiểm tra |
| Certificate re-issue với key cũ | Hệ thống ghi nhận key không đổi; không tuyên bố đã rekey |
| Certificate được rekey | Consumer xác minh được key mới và chain |
| API key mới được đăng ký | Consumer dùng key mới thành công trong overlap |
| Một instance chưa chuyển key | Rotation chưa đóng; có cảnh báo và owner |
| Key cũ bị revoke | Mọi consumer tuân thủ chính sách từ chối key cũ |
| Secret manager timeout | Không log secret; job retry có giới hạn và giữ trạng thái an toàn |
| Job renewal chạy lặp | Idempotency ngăn tạo thay đổi trùng không cần thiết |
| Password reset do compromise | Session/token liên quan được xử lý theo policy |
| Password không bị lộ nhưng đến kỳ tùy ý | Không ép đổi nếu policy hiện hành không yêu cầu |
| Passkey mới được thêm | Credential mới được kiểm tra trước khi xóa credential dự phòng |
| TOTP seed bị lộ | Seed cũ bị vô hiệu hóa và seed mới được đăng ký an toàn |
| SSH key mới được cài | Truy cập bằng key mới thành công trước khi gỡ key cũ |
| Workload credential hết hạn | Workload lấy credential mới trước khi credential cũ hết hiệu lực |
| Renewal thất bại | Có alert, retry và fallback; không xóa credential còn hợp lệ |
| Credential cũ bị lộ | Thu hồi khẩn cấp và điều tra consumer/cache |
| Rollback sau deploy lỗi | Không tái kích hoạt credential đã compromise |
| Secret xuất hiện trong build log | Kiểm soát redaction/secret scanning phát hiện và ngăn lộ |
| Credential không còn owner | Có quy trình gán owner hoặc thu hồi có kiểm soát |

### Chỉ số vận hành

- Tỷ lệ renewal thành công trước expiry.
- Số credential hết hạn ngoài dự kiến.
- Số credential active không có owner.
- Thời gian từ phát hiện compromise đến revoke có hiệu lực.
- Thời gian overlap trung bình và số key cũ còn được sử dụng.
- Tỷ lệ consumer chuyển đổi thành công ở lần triển khai đầu.
- Số lần rollback và nguyên nhân.
- Số secret bị phát hiện trong log, source hoặc artifact.
- Tỷ lệ credential có inventory, owner và rotation policy đầy đủ.

## 17. Checklist thiết kế credential renewal

- [ ] Phân biệt renewal, rotation, rekey, replacement, re-issuance và revocation.
- [ ] Có inventory, owner, issuer, consumer, scope và trạng thái cho credential.
- [ ] Secret thô không được lưu trong inventory, ticket hoặc log.
- [ ] Chính sách renewal phù hợp với loại credential và threat model.
- [ ] Password không bị ép đổi định kỳ tùy tiện khi không có căn cứ hoặc yêu cầu áp dụng.
- [ ] Certificate được theo dõi expiry; quyết định rõ giữ key hay rekey.
- [ ] API key/client secret có overlap giới hạn, telemetry và deadline revoke key cũ.
- [ ] SSH key được triển khai và kiểm tra trước khi xóa key cũ.
- [ ] Passkey/MFA credential có phương thức dự phòng và quy trình thu hồi khi mất/lộ.
- [ ] Workload identity ưu tiên credential ngắn hạn và cấp phát theo danh tính.
- [ ] Credential mới được phân phối qua secret manager/keystore an toàn.
- [ ] Consumer đã chuyển đổi được xác minh bằng telemetry/health check.
- [ ] Có rollback nhưng không tái sử dụng credential đã compromise.
- [ ] Thu hồi được kiểm tra tại mọi consumer, cache và resource server liên quan.
- [ ] Automation có quyền tối thiểu, idempotency, retry/backoff và audit.
- [ ] Có cảnh báo trước expiry và quy trình xử lý renewal thất bại.
- [ ] Có quy trình khẩn cấp khi secret/key bị lộ.
- [ ] Có kiểm thử expiry, overlap, revoke, failover, rollback và log redaction.

## Ghi nhớ

Credential renewal là quá trình duy trì và thay thế khả năng xác thực một cách có kiểm soát. Mỗi loại credential có vòng đời khác nhau: chứng chỉ cần gia hạn trước expiry; API key và secret cần rotation có overlap; mật khẩu thay đổi theo sự kiện và chính sách; passkey/MFA cần quản lý đăng ký, thay thế và thu hồi; workload identity có thể dùng credential ngắn hạn.

Hãy biết credential đang ở đâu, ai sở hữu và hệ thống nào sử dụng. Cấp credential mới, triển khai và xác minh trước khi retire credential cũ trong rotation bình thường; thu hồi khẩn cấp khi có bằng chứng compromise. Gia hạn chỉ hoàn tất khi consumer dùng credential mới, credential cũ không còn được chấp nhận và kết quả đã được kiểm toán.

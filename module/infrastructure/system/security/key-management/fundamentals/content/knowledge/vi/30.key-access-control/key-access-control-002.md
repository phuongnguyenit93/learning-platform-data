# Machine identity truy cập key

Machine identity là danh tính được gán cho một workload, dịch vụ, máy chủ, container, job hoặc thiết bị để hệ thống có thể xác thực và cấp quyền cho nó. Khi một workload cần dùng khóa trong KMS hoặc HSM, machine identity giúp xác định chính xác workload nào được phép thực hiện thao tác nào trên khóa nào, trong điều kiện nào.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, machine identity là nền tảng của kiểm soát truy cập khóa. Thay vì phân phối một khóa hoặc một mật khẩu quản trị dùng chung cho nhiều máy, hệ thống xác thực từng workload bằng danh tính riêng, sau đó áp dụng chính sách quyền tối thiểu. Cách này hỗ trợ truy vết, thu hồi và giới hạn phạm vi ảnh hưởng khi một workload bị xâm nhập.

## 1. Machine identity là gì?

Machine identity là danh tính số đại diện cho một thực thể không phải con người. Thực thể đó có thể là:

- Một ứng dụng backend chạy trên máy ảo.
- Một Kubernetes workload chạy trong pod.
- Một hàm serverless hoặc scheduled job.
- Một agent triển khai phần mềm.
- Một thiết bị IoT hoặc gateway.
- Một dịch vụ xử lý dữ liệu cần gọi KMS để giải mã data key.

Danh tính có thể được biểu diễn bằng service account, workload identity, certificate, token hoặc một định danh do nền tảng cấp. Machine identity cho phép hệ thống phân biệt workload này với workload khác, kể cả khi chúng chạy trên cùng một cluster hoặc cùng một máy chủ.

Ví dụ, dịch vụ thanh toán và dịch vụ báo cáo cùng chạy trong một Kubernetes cluster. Cả hai cần đọc dữ liệu được mã hóa. Dịch vụ thanh toán có thể được phép yêu cầu giải mã data key cho một nhóm dữ liệu thanh toán; dịch vụ báo cáo chỉ được phép giải mã dữ liệu tổng hợp đã được phê duyệt. Dùng một credential chung cho cả hai sẽ làm mất khả năng phân biệt và giới hạn quyền.

Machine identity không đồng nghĩa với tên máy, địa chỉ IP hoặc tên process. Những giá trị này có thể thay đổi, bị giả mạo hoặc được nhiều workload dùng chung. Danh tính cần được cấp phát và xác minh bởi một authority đáng tin cậy.

## 2. Phân biệt xác thực và ủy quyền

Kiểm soát truy cập khóa có hai câu hỏi riêng:

- **Authentication (xác thực):** workload nào đang yêu cầu thao tác? Hệ thống kiểm tra bằng chứng danh tính có hợp lệ và còn hiệu lực không.
- **Authorization (ủy quyền):** workload đã xác thực được phép làm gì, trên khóa hoặc tài nguyên nào, trong điều kiện nào?

Một token hợp lệ chỉ chứng minh danh tính hoặc quyền đại diện được token thể hiện. Nó không tự động có nghĩa workload được phép giải mã mọi khóa. KMS/HSM phải áp dụng chính sách ủy quyền sau khi xác thực.

~~~mermaid
flowchart TD
    A[Workload yêu cầu thao tác với key] --> B[Authentication]
    B --> C{Danh tính hợp lệ?}
    C -->|Không| D[Từ chối]
    C -->|Có| E[Authorization policy]
    E --> F{Đúng principal, action, resource và context?}
    F -->|Không| D
    F -->|Có| G[KMS/HSM thực hiện thao tác]
    G --> H[Audit event]
~~~

Ví dụ, một workload có thể được xác thực là service account của dịch vụ invoice. Chính sách vẫn cần quyết định account đó có quyền Decrypt trên key invoice-production hay chỉ có quyền GenerateDataKey. Việc xác thực thành công không được bỏ qua bước này.

## 3. Vì sao cần machine identity riêng cho từng workload?

Nếu nhiều dịch vụ dùng chung một API key hoặc credential quản trị, hệ thống khó xác định nguồn của một thao tác giải mã. Khi credential bị lộ, tất cả dịch vụ dùng chung nó có thể bị ảnh hưởng và việc thu hồi có thể làm gián đoạn toàn bộ hệ thống.

Danh tính riêng đem lại các lợi ích:

- **Phân quyền theo workload:** mỗi dịch vụ chỉ nhận quyền cần thiết cho chức năng của nó.
- **Giới hạn phạm vi ảnh hưởng:** sự cố ở một workload không mặc nhiên cấp quyền cho các workload khác.
- **Audit rõ ràng:** log có thể gắn thao tác với principal cụ thể.
- **Thu hồi độc lập:** vô hiệu hóa một danh tính mà không phải đổi credential cho toàn bộ hệ thống.
- **Phân tách môi trường:** production, staging và development có danh tính và quyền riêng.
- **Tự động hóa an toàn:** nền tảng có thể cấp credential ngắn hạn thay vì lưu secret tĩnh trong cấu hình.

Một workload không nên mượn danh tính của node, máy chủ hoặc service account tổng quát nếu nền tảng có thể cấp danh tính riêng cho workload đó. Nếu nhiều ứng dụng chạy dưới cùng một OS user hoặc cùng một cloud role, ranh giới quyền giữa chúng có thể không đủ rõ.

## 4. Các thành phần của machine identity

Một hệ thống machine identity thường có các thành phần:

| Thành phần | Vai trò |
|---|---|
| Principal / subject | Định danh workload, ví dụ service account hoặc SPIFFE ID |
| Identity provider | Cấp hoặc xác nhận danh tính, chẳng hạn cloud identity service, OIDC provider hoặc CA nội bộ |
| Credential / proof | Bằng chứng xác thực như token ngắn hạn, certificate và private key |
| Trust configuration | Quy định issuer, CA, audience, subject hoặc loại credential được chấp nhận |
| Authorization policy | Ánh xạ principal với action, key resource và điều kiện |
| KMS/HSM | Thực thi thao tác khóa và kiểm tra chính sách |
| Audit system | Ghi nhận yêu cầu, principal, kết quả và metadata phục vụ điều tra |

Danh tính cần có định danh ổn định trong phạm vi quản trị, nhưng credential chứng minh danh tính nên có thời hạn và có thể thay mới. Ví dụ, SPIFFE ID có thể biểu diễn workload theo trust domain và path; certificate SVID được cấp trong thời gian ngắn để chứng minh workload sở hữu danh tính đó.

Không nên dùng một trường metadata do workload tự khai báo làm bằng chứng danh tính. Identity provider phải xác minh workload dựa trên nguồn tin cậy như node attestation, orchestrator, cloud control plane hoặc certificate authority.

## 5. Các cách cấp và xác thực machine identity

### Workload identity của nền tảng

Cloud hoặc container platform có thể gán service account/role cho workload. Workload lấy credential qua cơ chế được nền tảng bảo vệ và dùng credential đó để gọi dịch vụ KMS. Ví dụ, một pod có thể được liên kết với service account riêng; một workload trên máy ảo có thể nhận instance role.

Ưu điểm là giảm nhu cầu lưu access key dài hạn trong file cấu hình. Tuy nhiên, cần cấu hình đúng liên kết giữa workload và identity. Nếu mọi pod có thể dùng chung node identity hoặc metadata endpoint không được giới hạn, một pod bị xâm nhập có thể tìm cách lấy credential của workload khác.

### OIDC workload federation

Workload có thể nhận một OIDC token từ identity provider của nền tảng. KMS hoặc một dịch vụ STS xác minh issuer, audience, subject và thời hạn rồi trao credential ngắn hạn với quyền giới hạn.

Các trường cần kiểm tra gồm:

- **Issuer:** token do identity provider nào phát hành.
- **Audience:** token được phát hành cho dịch vụ nào; tránh chấp nhận token dành cho ứng dụng khác.
- **Subject:** workload hoặc service account nào được token đại diện.
- **Expiry / issued-at:** token còn hiệu lực và thời gian phát hành có hợp lệ không.
- **Signature / key ID:** chữ ký token được xác minh bằng khóa công khai đúng của issuer.

Không chấp nhận token chỉ vì chữ ký hợp lệ. Phải ràng buộc issuer, audience, subject và các claim cần thiết với workload được phép.

### Mutual TLS và workload certificate

Trong mô hình mTLS, mỗi workload có certificate và private key riêng. Hai phía xác minh certificate của nhau theo CA và policy đã cấu hình. Certificate có thể mang URI SAN hoặc định danh workload khác.

Private key chứng minh danh tính phải được bảo vệ. Nếu certificate được cấp ngắn hạn, hệ thống có thể tự động gia hạn và thu hồi khi workload không còn hợp lệ. Cần xác minh chain, thời hạn, mục đích sử dụng và danh tính trong certificate; không chỉ kiểm tra rằng TLS handshake đã thành công.

### Static API key hoặc client secret

Một số hệ thống cũ dùng access key hoặc client secret dài hạn. Cách này có thể hoạt động nhưng làm tăng rủi ro lưu trữ, sao chép và xoay vòng bí mật. Nếu chưa thể loại bỏ, cần lưu trong secret manager, giới hạn quyền, theo dõi sử dụng, thay mới theo lịch và có khả năng thu hồi khẩn cấp.

Ưu tiên credential ngắn hạn được cấp tự động khi nền tảng hỗ trợ. Credential tĩnh không nên được nhúng trong source code, container image, script triển khai hoặc biến môi trường được chia sẻ rộng rãi.

## 6. Machine identity gọi KMS/HSM như thế nào?

Một luồng điển hình khi ứng dụng dùng envelope encryption:

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant ID as Identity provider
    participant K as KMS/HSM
    participant D as Data store
    W->>ID: Yêu cầu credential cho workload
    ID-->>W: Token hoặc credential ngắn hạn
    W->>K: GenerateDataKey hoặc Decrypt
    K->>K: Xác thực principal và kiểm tra policy
    K-->>W: Plaintext data key hoặc wrapped data key
    W->>W: Mã hóa/giải mã dữ liệu bằng data key
    W->>D: Lưu ciphertext và encrypted data key
    K-->>W: Audit event được ghi nhận
~~~

Trong envelope encryption, KMS thường bảo vệ Key Encryption Key (KEK) hoặc khóa quản lý tương đương. Workload yêu cầu tạo data key; KMS trả về data key dạng plaintext để workload dùng trong bộ nhớ và một bản đã được mã hóa bởi KEK. Workload mã hóa dữ liệu bằng data key, lưu ciphertext cùng encrypted data key, rồi loại bỏ bản plaintext khi không còn cần.

Khi đọc dữ liệu, workload gửi encrypted data key tới KMS để giải mã nếu policy cho phép. KMS không cần trao KEK cho workload. Cách này giảm việc phân phối khóa gốc và cho phép kiểm soát thao tác Decrypt tại KMS.

Quyền GenerateDataKey và Decrypt có mức ảnh hưởng khác nhau. Một workload chỉ ghi dữ liệu có thể cần GenerateDataKey; workload đọc dữ liệu cần Decrypt. Tách quyền theo luồng nghiệp vụ giúp hạn chế khả năng một dịch vụ bị xâm nhập vừa tạo vừa giải mã mọi dữ liệu.

## 7. Thiết kế quyền tối thiểu cho key access

Chính sách cần xác định ít nhất bốn yếu tố:

1. **Principal:** machine identity nào được gọi.
2. **Action:** thao tác khóa nào được phép.
3. **Resource:** key hoặc nhóm key nào được phép truy cập.
4. **Condition/context:** điều kiện bổ sung như môi trường, tenant, encryption context, nguồn mạng, thời hạn hoặc workload claim.

Các action thường gặp:

| Action | Ý nghĩa | Mức độ cần kiểm soát |
|---|---|---|
| Encrypt | Mã hóa dữ liệu hoặc data key | Chỉ cấp cho workload có nhu cầu mã hóa |
| Decrypt | Giải mã ciphertext hoặc encrypted data key | Nhạy cảm cao vì có thể mở dữ liệu đã bảo vệ |
| GenerateDataKey | Tạo data key cho envelope encryption | Cấp theo key và use case ghi dữ liệu |
| Sign | Ký dữ liệu bằng private key | Chỉ cấp cho dịch vụ có trách nhiệm ký |
| Verify | Xác minh chữ ký | Thường không cần quyền dùng private key; có thể xác minh bằng public key |
| GetPublicKey | Lấy public key tương ứng | Có thể cho phép rộng hơn tùy loại khóa và policy |
| CreateKey / ImportKey | Tạo hoặc nhập key material | Quyền quản trị nhạy cảm |
| UpdateKeyPolicy / DisableKey / ScheduleDeletion | Thay đổi hoặc vô hiệu hóa khóa | Nên tách khỏi quyền runtime thông thường |

Một ứng dụng runtime thường không cần quyền tạo key, thay đổi policy, xóa key hoặc cấp quyền cho principal khác. Quyền quản trị khóa nên thuộc vai trò vận hành riêng, có phê duyệt và audit.

### Ví dụ policy khái niệm

Ví dụ JSON dưới đây minh họa ý tưởng cấp quyền cho workload invoice chỉ được giải mã bằng một key cụ thể trong môi trường production. Đây không phải policy có thể áp dụng nguyên trạng cho mọi KMS; cú pháp, tên action và cách biểu diễn principal phụ thuộc nhà cung cấp.

~~~json
{
  "principal": "workload://prod/invoice-service",
  "resource": "key://prod/invoice-data",
  "actions": [
    "Decrypt"
  ],
  "conditions": {
    "environment": "production",
    "purpose": "invoice-read",
    "tenant": "tenant-42"
  }
}
~~~

Điều kiện phải được KMS hoặc lớp authorization đáng tin cậy xác minh từ context đã được ràng buộc với request. Không được tin một giá trị tenant hoặc purpose do client tự gửi nếu client có thể tự sửa nó. Với envelope encryption, encryption context/AAD có thể ràng buộc ciphertext với metadata nghiệp vụ, nhưng phải thiết kế thống nhất giữa lúc mã hóa và giải mã.

## 8. Phân tách quyền theo môi trường và workload

Không nên dùng cùng một machine identity hoặc cùng một key policy cho mọi môi trường. Development, test, staging và production có mức độ tin cậy, dữ liệu và quyền vận hành khác nhau.

Ví dụ:

| Workload | Môi trường | Quyền cần thiết | Quyền không nên có |
|---|---|---|---|
| Invoice API | Production | Decrypt data key của invoice; GenerateDataKey nếu ghi | CreateKey, UpdateKeyPolicy, ScheduleDeletion |
| Invoice API | Staging | Dùng key staging | Decrypt key production |
| Reporting job | Production | Decrypt key cho dữ liệu báo cáo đã phê duyệt | Decrypt key của payment hoặc secret |
| CI/CD deployer | Production | Cấp hoặc gắn identity theo quy trình deploy | Decrypt dữ liệu ứng dụng |
| Key administrator | Production | Quản trị policy, rotation và trạng thái key theo phê duyệt | Dùng quyền runtime để đọc dữ liệu nghiệp vụ thường xuyên |

Tách identity theo workload giúp tránh việc một quyền vô tình lan sang ứng dụng khác. Tách key theo môi trường hoặc miền dữ liệu còn tạo ranh giới rõ hơn khi cần thu hồi hoặc điều tra.

Không dựa vào tên alias để phân biệt production và staging nếu policy không ràng buộc đúng key resource. Alias là nhãn tham chiếu, không phải cơ chế authorization.

## 9. Điều kiện ngữ cảnh và ràng buộc sử dụng key

Ngoài principal/action/resource, policy có thể giới hạn theo context:

- Workload thuộc namespace, cluster hoặc trust domain cụ thể.
- Token có issuer, audience và subject được cho phép.
- Yêu cầu chỉ được thực hiện trong môi trường production hoặc vùng mạng đã phê duyệt.
- Encryption context chứa tenant, loại bản ghi hoặc mục đích nghiệp vụ phù hợp.
- Key chỉ được sử dụng cho thao tác Encrypt/Decrypt hoặc Sign đã định nghĩa.
- Request gắn với phiên hoặc transaction hợp lệ.

Điều kiện phải dựa trên thuộc tính được xác thực hoặc được dịch vụ tin cậy tạo ra. Nếu ứng dụng gửi một trường context tùy ý, attacker có thể thay đổi nó để vượt qua policy. Cần kiểm thử cả trường hợp thiếu claim, claim sai, token hết hạn và context không khớp.

Với hệ thống nhiều tenant, phải bảo đảm tenant identity được lấy từ nguồn xác thực và ràng buộc với dữ liệu mã hóa. Không dựa riêng vào tenant ID trong URL hoặc request body để quyết định key được dùng.

## 10. Thu hồi identity và credential

Khi workload bị xâm nhập, bị gỡ bỏ hoặc không còn được phép truy cập key, cần vô hiệu hóa danh tính và credential liên quan. Các bước có thể gồm:

1. Xác định principal, workload instance, token/certificate và key resource đã được truy cập.
2. Ngừng cấp credential mới cho workload hoặc thu hồi service account/role binding.
3. Vô hiệu hóa certificate, client secret hoặc access key bị ảnh hưởng.
4. Thu hồi hoặc chờ hết hạn token ngắn hạn theo cơ chế identity provider; xem xét giới hạn session/token cache.
5. Gỡ quyền principal khỏi key policy hoặc IAM policy.
6. Nếu có khả năng key material hoặc plaintext data key đã bị lấy, đánh giá phạm vi dữ liệu và cân nhắc re-encrypt bằng key mới.
7. Rà soát audit log để xác định thao tác, thời gian, resource và dữ liệu liên quan.

Xóa một service account khỏi cấu hình không nhất thiết làm vô hiệu hóa ngay mọi token đã phát hành. Một số hệ thống chỉ kiểm tra token đến khi hết hạn hoặc dùng cache. Cần hiểu thời gian hiệu lực credential, cơ chế revocation và thời gian lan truyền policy của nền tảng.

Nếu chỉ credential của workload bị lộ nhưng key material không bị xuất, thu hồi identity và quyền có thể chặn các yêu cầu mới. Nếu attacker đã lấy plaintext data key hoặc plaintext dữ liệu, việc thu hồi identity không thể làm những bản sao đó biến mất; phải đánh giá lại dữ liệu và thực hiện các biện pháp ứng phó tương ứng.

## 11. Audit và giám sát key access

Mọi thao tác nhạy cảm với key nên tạo audit event có thể liên kết với machine identity. Tối thiểu nên ghi:

- Principal hoặc workload identity đã xác thực.
- Action và key resource được yêu cầu.
- Thời điểm, kết quả thành công/thất bại và mã lỗi.
- Request ID, session hoặc correlation ID.
- Context cần thiết như môi trường, tenant hoặc encryption context đã được chính sách cho phép ghi.
- Nguồn gọi hoặc workload metadata đã được xác thực.

Không ghi plaintext key, passphrase, access token, private key hoặc plaintext data key vào audit log. Log phải được bảo vệ khỏi sửa/xóa trái phép và có thời gian lưu theo yêu cầu điều tra.

Các tín hiệu cần cảnh báo:

- Một workload lần đầu gọi Decrypt hoặc gọi trên key ngoài phạm vi bình thường.
- Tăng đột biến số lượng yêu cầu Decrypt/GenerateDataKey.
- Thao tác key từ môi trường, cluster hoặc vị trí không dự kiến.
- Nhiều lần xác thực thất bại hoặc token có issuer/audience không hợp lệ.
- Thay đổi key policy, cấp quyền mới hoặc vô hiệu hóa audit.
- Một principal runtime cố gọi CreateKey, UpdateKeyPolicy hoặc ScheduleDeletion.

Audit cần giúp trả lời ai đã yêu cầu thao tác nào trên key nào, trong khoảng thời gian nào và kết quả ra sao. Nếu log chỉ ghi username chung hoặc IP node, khả năng điều tra sẽ hạn chế.

## 12. Machine identity và HSM

Khi key nằm trong HSM, machine identity vẫn cần được xác thực và ủy quyền. HSM có thể dùng token, partition, role hoặc session để xác định ứng dụng được phép gọi thao tác. Provider PKCS#11 hoặc provider chuyên dụng chuyển yêu cầu từ JCA/JCE tới thiết bị.

Các nguyên tắc:

- Mỗi workload hoặc nhóm workload có danh tính/token riêng nếu HSM và kiến trúc cho phép.
- Giới hạn key object theo quyền Sign, Decrypt, Derive, Wrap hoặc Unwrap cần thiết.
- Không chia sẻ PIN hoặc token administrator cho mọi ứng dụng.
- Tách quyền quản trị HSM, quản trị key và sử dụng key trong runtime.
- Dùng key non-extractable khi yêu cầu bảo vệ không cho xuất private/secret key.
- Ghi audit việc login, truy cập object, thao tác key và thay đổi policy.

Không phải mọi HSM đều có mô hình IAM theo từng workload. Một số thiết bị dựa vào partition hoặc credential của client. Khi đó, cần thiết kế ranh giới workload ở lớp gateway/provider và giới hạn credential truy cập thiết bị. Không nên giả định HSM tự hiểu Kubernetes service account hoặc cloud workload identity nếu chưa có tích hợp cụ thể.

## 13. Ví dụ thiết kế luồng truy cập key cho Java service

Một Java service có thể dùng credential provider của nền tảng để nhận và làm mới workload credential, rồi dùng SDK KMS để yêu cầu GenerateDataKey hoặc Decrypt. Cấu trúc khái quát:

~~~java
// Pseudocode: API và kiểu dữ liệu cụ thể phụ thuộc KMS SDK.
KmsClient kms = KmsClient.builder()
        .credentialProvider(workloadIdentityProvider)
        .build();

DataKeyResult result = kms.generateDataKey(
        productionInvoiceKey,
        "AES_256",
        Map.of(
                "environment", "production",
                "purpose", "invoice-write"));

byte[] plaintextDataKey = result.plaintextKey();
byte[] encryptedDataKey = result.encryptedKey();

try {
    byte[] ciphertext = encryptWithAead(
            plaintextDataKey,
            nonce,
            invoicePayload,
            authenticatedContext);
    persist(ciphertext, encryptedDataKey, nonce);
} finally {
    Arrays.fill(plaintextDataKey, (byte) 0);
}
~~~

Đây là pseudocode mô tả luồng, không phải API của một nhà cung cấp cụ thể. Trong triển khai thật, credential provider cần lấy và làm mới credential ngắn hạn từ nguồn danh tính tin cậy; SDK có thể quản lý retry và object key theo cách riêng. Phải bảo đảm KMS policy chỉ cấp đúng action/resource cho service.

Xóa mảng byte bằng cách ghi đè giúp giảm thời gian giữ plaintext data key trong mảng đó, nhưng không bảo đảm mọi bản sao do SDK, JVM hoặc thư viện mật mã tạo ra đều đã bị xóa. Hạn chế sao chép key material và không ghi nó ra log hoặc file tạm.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng một machine identity cho nhiều dịch vụ | Khó truy vết và thu hồi riêng lẻ | Cấp identity riêng theo workload và môi trường |
| Dùng static access key trong image hoặc source | Credential có thể bị sao chép và tồn tại lâu | Dùng workload identity hoặc credential ngắn hạn |
| Chỉ xác thực token mà không kiểm tra audience/subject | Token dành cho workload khác có thể bị chấp nhận | Ràng buộc issuer, audience, subject và thời hạn |
| Cấp quyền KMS quản trị cho runtime | Workload bị xâm nhập có thể thay policy hoặc xóa key | Tách quyền sử dụng key và quyền quản trị |
| Cho phép Decrypt trên mọi key | Tăng phạm vi dữ liệu có thể bị lộ | Giới hạn resource và điều kiện theo tenant/use case |
| Dựa vào IP hoặc tên máy làm danh tính | Có thể bị giả mạo hoặc thay đổi theo hạ tầng | Dùng identity do nền tảng/CA cấp và xác minh |
| Xóa service account nhưng bỏ qua token đang hiệu lực | Credential cũ có thể tiếp tục được dùng | Thu hồi theo cơ chế nền tảng, rút ngắn TTL và kiểm tra cache |
| Ghi token hoặc plaintext data key vào log | Làm lộ credential hoặc key material | Redact log và giới hạn dữ liệu audit |
| Cho rằng HSM tự phân quyền từng workload | Các workload có thể dùng chung token/partition | Xác minh mô hình client identity và phân quyền thực tế của HSM |
| Tin tenant/purpose do request tự khai báo | Có thể truy cập nhầm key hoặc dữ liệu tenant khác | Ràng buộc context với danh tính đã xác thực và AAD |

## 15. Checklist triển khai

- [ ] Mỗi workload có machine identity riêng theo môi trường và chức năng.
- [ ] Identity được cấp bởi authority đáng tin cậy; không dùng IP hoặc tên process làm bằng chứng duy nhất.
- [ ] Ưu tiên workload identity hoặc credential ngắn hạn thay cho static access key.
- [ ] Xác minh issuer, audience, subject, thời hạn và chữ ký của token/certificate.
- [ ] Tách authentication khỏi authorization và kiểm tra policy ở KMS/HSM.
- [ ] Cấp quyền theo principal, action, key resource và context cần thiết.
- [ ] Tách quyền Encrypt, Decrypt, GenerateDataKey, Sign và quyền quản trị.
- [ ] Phân tách identity và key giữa production, staging, development và tenant.
- [ ] Ràng buộc encryption context/AAD với dữ liệu và danh tính đã xác thực.
- [ ] Bảo vệ credential, private key và plaintext data key; không ghi vào log.
- [ ] Có quy trình thu hồi identity, token, certificate và quyền truy cập key.
- [ ] Audit mọi thao tác key theo principal và cảnh báo hành vi bất thường.
- [ ] Kiểm thử token sai audience, workload giả mạo, quyền vượt phạm vi và tình huống thu hồi.
- [ ] Xác minh mô hình phân quyền thực tế nếu tích hợp HSM hoặc PKCS#11.

Machine identity cho phép KMS/HSM biết workload nào đang yêu cầu sử dụng khóa và áp dụng quyền đúng theo mục đích. Thiết kế an toàn cần danh tính riêng, credential có thể thu hồi, xác thực chặt chẽ, chính sách quyền tối thiểu theo action/resource/context và audit gắn với từng workload.

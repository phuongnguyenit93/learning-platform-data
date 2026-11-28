# Key access policy

Trong chương **Access control cho key** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích cách xây dựng chính sách kiểm soát quyền truy cập khóa mật mã. Key access policy xác định chủ thể nào được phép thực hiện thao tác nào trên khóa nào, trong điều kiện nào và với mục đích gì. Chính sách tốt giới hạn quyền theo nguyên tắc tối thiểu, tách quyền sử dụng khóa khỏi quyền quản trị vòng đời, áp dụng kiểm soát ở KMS/HSM và ứng dụng, đồng thời tạo audit trail đủ để điều tra.

## 1. Key access policy là gì?

**Key access policy** là tập hợp quy tắc quyết định ai hoặc thành phần nào được phép sử dụng hay quản trị một cryptographic key. Chính sách có thể được thực thi bởi KMS, HSM, hệ điều hành, ứng dụng hoặc nhiều lớp phối hợp.

Một policy thường trả lời năm câu hỏi:

1. **Principal:** ai đang yêu cầu? Ví dụ user, service account, workload identity, application role hoặc administrator.
2. **Resource:** khóa nào hoặc nhóm khóa nào bị tác động?
3. **Action:** principal muốn làm gì? Ví dụ encrypt, decrypt, sign, verify, wrap, unwrap, rotate hoặc delete.
4. **Context:** yêu cầu đến từ môi trường, tenant, region, workload, thời điểm hoặc điều kiện nào?
5. **Decision:** cho phép, từ chối hay yêu cầu phê duyệt bổ sung?

Policy cần gắn quyền với mục đích sử dụng cụ thể. Một service chỉ cần giải mã dữ liệu đơn hàng không nên mặc nhiên có quyền export key, thay đổi policy hoặc xóa key. Người quản trị key policy cũng không nhất thiết cần quyền đọc plaintext của dữ liệu ứng dụng.

Key access policy là một phần của key management. Nó bổ sung cho quy trình tạo, cấp phát, lưu trữ, sử dụng, rotation, thu hồi và destruction bằng cách xác định ai được thực hiện từng thao tác trong suốt vòng đời.

## 2. Phân biệt authentication và authorization

Hai bước này trả lời hai câu hỏi khác nhau:

- **Authentication:** xác định principal là ai hoặc workload nào đang gửi yêu cầu.
- **Authorization:** quyết định principal đã được xác thực có được thực hiện action trên key cụ thể hay không.

Ví dụ, workload identity có thể chứng minh request đến từ service thanh toán. Điều đó không có nghĩa service này được phép dùng mọi key trong tài khoản. Authorization cần kiểm tra key ID, action, tenant, môi trường và policy tương ứng.

Không dùng tên service do request tự khai làm bằng chứng danh tính. Principal phải được xác thực bằng cơ chế tin cậy như workload identity, certificate, token ngắn hạn hoặc thông tin xác thực được cấp bởi nền tảng.

## 3. Các thành phần của một policy

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Principal | Danh tính hoặc vai trò yêu cầu | order-service-prod |
| Resource | Key ID, key version hoặc nhóm key | key/orders-data-prod |
| Action | Thao tác mật mã hoặc quản trị | Decrypt |
| Context/condition | Điều kiện bổ sung | tenant=merchant-42, environment=production |
| Effect | Kết quả quy tắc | Allow hoặc Deny |
| Scope | Phạm vi áp dụng | Một key, một project, một account hoặc một key family |
| Validity | Thời gian hoặc trạng thái hiệu lực | Active, thời hạn grant, emergency disable |

Policy nên dùng định danh ổn định cho principal và key. Tránh dựa vào tên hiển thị có thể đổi hoặc alias không được kiểm soát. Alias hữu ích cho vận hành, nhưng quyết định authorization cần được ràng buộc với resource ID thực tế và trạng thái hiện tại của key.

## 4. Các action cần kiểm soát

Không nên coi “được truy cập key” là một quyền duy nhất. Các thao tác có mức rủi ro khác nhau:

| Nhóm | Action điển hình | Rủi ro nếu cấp quá rộng |
|---|---|---|
| Sử dụng dữ liệu | Encrypt, decrypt, encrypt/decrypt data | Có thể làm lộ plaintext hoặc mã hóa dữ liệu trái phép |
| Xác thực và ký | Sign, verify, MAC, derive | Có thể giả mạo chữ ký/MAC hoặc tạo khóa con ngoài mục đích |
| Quản lý khóa bao | Wrap, unwrap | Có thể lấy lại DEK hoặc làm lộ key material được bọc |
| Tạo và nhập | Generate, import, create replica | Có thể tạo key không theo policy hoặc đưa key material không tin cậy vào hệ thống |
| Truy xuất | Get public key, describe key, list versions | Có thể tiết lộ metadata hoặc cấu trúc tài sản |
| Quản trị | Update policy, create grant, change tags, enable/disable | Có thể mở rộng quyền cho principal khác hoặc làm gián đoạn dịch vụ |
| Vòng đời | Rotate, schedule deletion, cancel deletion, destroy | Có thể làm mất khả năng giải mã hoặc phá vỡ trust |
| Xuất khóa | Export, backup, restore | Có thể tạo bản sao key material ngoài miền bảo vệ |

Quyền verify public signature thường ít nhạy cảm hơn quyền sign, vì verify dùng public key. Với HMAC, verify vẫn cần shared secret; principal có quyền verify HMAC thường cũng có khả năng tạo MAC. Policy cần phản ánh khác biệt này thay vì chỉ dựa vào tên action.

## 5. Nguyên tắc least privilege

**Least privilege** yêu cầu mỗi principal chỉ có những quyền tối thiểu cần cho nhiệm vụ cụ thể. Khi áp dụng cho key access:

- Cấp quyền theo từng key hoặc nhóm key có cùng purpose, không cấp wildcard toàn bộ key nếu không cần.
- Tách quyền encrypt và decrypt nếu workload chỉ cần một chiều.
- Tách quyền sign khỏi quyền quản trị key.
- Không cấp export nếu ứng dụng có thể dùng key handle hoặc API mật mã.
- Giới hạn quyền theo tenant, environment, service identity và context.
- Cấp quyền tạm thời khi chỉ cần cho một tác vụ triển khai hoặc phục hồi.
- Thu hồi grant khi workload, user hoặc integration ngừng hoạt động.

Ví dụ, một service ghi dữ liệu có thể chỉ cần Encrypt bằng key của tenant tương ứng; service đọc dữ liệu có thể cần Decrypt nhưng không cần thay đổi policy. Một key administrator có thể quản lý metadata và rotation nhưng không cần quyền decrypt dữ liệu nghiệp vụ.

Least privilege cần được đánh giá cả theo khả năng kết hợp quyền. Một principal có thể không có quyền export key nhưng có quyền decrypt mọi ciphertext do attacker gửi; trong một số hệ thống, điều đó vẫn có thể trở thành decryption oracle. Hãy giới hạn cả dữ liệu, context và số lượng operation.

## 6. Default deny và cách đánh giá policy

Một thiết kế an toàn thường áp dụng **default deny**: nếu không có quy tắc cho phép rõ ràng thì từ chối. Điều này giúp quyền mới không tự động xuất hiện khi một key hoặc principal được thêm vào.

Thứ tự đánh giá thường cần xác định rõ:

1. Xác thực principal và nguồn credential.
2. Kiểm tra key có tồn tại, đang active và cho phép action hay không.
3. Áp dụng các deny rule bắt buộc.
4. Đánh giá allow rule theo principal, resource, action và condition.
5. Kiểm tra grant, boundary, organization policy hoặc guardrail cấp cao hơn.
6. Trả quyết định và ghi audit.

Nhiều nền tảng dùng quy tắc explicit deny có ưu tiên cao hơn allow; một số hệ thống có thêm permission boundary, organization policy hoặc grant. Không giả định mọi KMS/HSM đánh giá policy giống nhau. Phải đọc đúng mô hình authorization của nền tảng đang dùng và kiểm thử các trường hợp allow, deny, thiếu context và xung đột policy.

~~~mermaid
flowchart TD
    A[Request principal + key + action] --> B{Principal đã xác thực?}
    B -->|Không| X[Từ chối]
    B -->|Có| C{Key active và action hợp lệ?}
    C -->|Không| X
    C -->|Có| D{Có explicit deny?}
    D -->|Có| X
    D -->|Không| E{Có allow rule khớp resource và context?}
    E -->|Không| X
    E -->|Có| F{Guardrail hoặc grant cho phép?}
    F -->|Không| X
    F -->|Có| G[Cho phép operation]
    G --> H[Audit decision và operation]
~~~

Đây là mô hình tư duy tổng quát. Cách một sản phẩm thực hiện policy evaluation có thể khác; policy engine cần được kiểm chứng bằng tài liệu và thử nghiệm thực tế.

## 7. RBAC và ABAC cho key access

Hai mô hình phổ biến có thể được kết hợp:

| Mô hình | Cách cấp quyền | Điểm mạnh | Rủi ro cần quản lý |
|---|---|---|---|
| RBAC (Role-Based Access Control) | Gán quyền cho role rồi gán principal vào role | Dễ chuẩn hóa theo chức năng và đội vận hành | Role quá rộng hoặc tích lũy nhiều role |
| ABAC (Attribute-Based Access Control) | Đánh giá thuộc tính principal, resource, action và context | Quyền linh hoạt theo tenant, môi trường, purpose | Attribute sai, thiếu hoặc do caller tự kiểm soát |
| Hybrid | Role xác định nhóm action, condition giới hạn resource/context | Dễ mở rộng mà vẫn có ràng buộc chi tiết | Policy phức tạp, cần kiểm thử đầy đủ |

Ví dụ RBAC: role order-reader có quyền decrypt trên key dành cho dữ liệu đơn hàng. Ví dụ ABAC: chỉ cho phép nếu principal thuộc order-service, key có tag purpose=orders, environment=production và request context có tenant phù hợp.

Không dùng tag hoặc attribute do chính caller tùy ý gửi để tự cấp quyền. Các thuộc tính quyết định authorization phải đến từ nguồn tin cậy, được bảo vệ khỏi sửa đổi trái phép và có quy tắc xử lý khi thiếu dữ liệu.

## 8. Tách quyền sử dụng khóa và quyền quản trị

Một nguyên tắc quan trọng là tách **data-plane permissions** khỏi **control-plane permissions**:

- Data plane là các thao tác sử dụng key để encrypt, decrypt, sign, verify, wrap hoặc unwrap.
- Control plane là các thao tác tạo key, thay đổi policy, cấp grant, gắn tag, bật/tắt, rotate hoặc schedule deletion.

Một service ứng dụng thường chỉ cần data-plane permission trên một số key nhất định. Nhóm quản trị nền tảng có thể cần control-plane permission nhưng không cần đọc plaintext. Một nhóm security có thể phê duyệt policy hoặc giám sát audit mà không cần trực tiếp sử dụng key.

| Vai trò | Quyền nên có | Quyền thường không cần |
|---|---|---|
| Application workload | Operation tối thiểu trên key cụ thể | Update policy, create grant, delete key, export |
| Key operator | Quản lý trạng thái, rotation theo quy trình | Decrypt dữ liệu nghiệp vụ mặc định |
| Security approver | Review policy, phê duyệt thay đổi nhạy cảm | Dùng key cho workload |
| Auditor | Đọc audit log và metadata cần thiết | Sign, decrypt, export key |
| Break-glass administrator | Quyền khẩn cấp có kiểm soát và thời hạn | Sử dụng thường xuyên hoặc không ghi audit |

Tách quyền giúp giảm nguy cơ một tài khoản bị chiếm quyền vừa thay policy, vừa cấp quyền cho chính nó và sử dụng key để lấy dữ liệu.

## 9. Separation of duties và dual control

**Separation of duties** phân chia các bước nhạy cảm giữa nhiều vai trò. **Dual control** yêu cầu ít nhất hai người hoặc hai principal độc lập tham gia trước khi thao tác quan trọng được thực hiện.

Các thao tác có thể cần dual control:

- Thay đổi key policy cho key production quan trọng.
- Tạo grant rộng hoặc cấp quyền cho principal mới.
- Export hoặc restore key backup.
- Thay đổi quorum hoặc security domain của HSM.
- Schedule deletion hoặc hủy CA/master key.
- Phê duyệt emergency access.

Ví dụ, một operator tạo yêu cầu rotate key; một approver khác xác nhận phạm vi, dependency và kế hoạch rollback. HSM có thể yêu cầu M-of-N custodians để thực hiện ceremony quản trị. Cần lưu danh tính từng người, thời điểm và nội dung phê duyệt.

Không phải mọi thao tác đều cần nhiều người. Áp dụng dual control cho thao tác rủi ro cao, có khả năng gây mất dữ liệu hoặc mở rộng quyền, để tránh làm quy trình vận hành thông thường quá chậm.

## 10. Context-aware access và ràng buộc theo mục đích

Policy có thể giới hạn quyền theo context ngoài principal và key:

- Environment: production, staging hoặc development.
- Tenant/account/project: chỉ dữ liệu thuộc miền đã được cấp.
- Workload identity: service cụ thể, namespace hoặc workload attestation.
- Region hoặc network boundary: chỉ từ vùng triển khai được phê duyệt.
- Time window: grant tạm thời hoặc thao tác trong cửa sổ bảo trì.
- Key purpose: encryption, signing, tokenization hoặc backup.
- Data context: tenant ID, record type hoặc application ID được ràng buộc với ciphertext.

Một số KMS hỗ trợ encryption context: tập cặp key-value được gắn vào thao tác encrypt/decrypt và được xác thực như AAD. Có thể dùng context condition trong policy để giới hạn decrypt chỉ khi encryption context khớp.

Encryption context không phải bí mật; nó thường được truyền cùng request và có thể xuất hiện trong audit log. Không đưa password, access token hoặc dữ liệu nhạy cảm vào context. Giá trị context cần được chuẩn hóa và tái tạo chính xác khi decrypt; nếu khác nhau, operation có thể thất bại.

Context chỉ có giá trị bảo vệ nếu được xác định từ nguồn tin cậy. Nếu caller được tự chọn tenant ID tùy ý và policy chỉ kiểm tra sự hiện diện của trường đó, attacker có thể khai tenant khác. Cần ràng buộc context với danh tính và quyền nghiệp vụ đã xác thực.

## 11. Key policy, IAM policy và grant

Trong KMS, quyền truy cập có thể được biểu diễn qua nhiều lớp:

- **Key policy:** policy gắn trực tiếp với key, xác định principal và action được phép.
- **Identity/IAM policy:** policy gắn với user, role hoặc workload identity.
- **Grant:** quyền có phạm vi cụ thể được cấp cho principal hoặc dịch vụ, thường có thể thu hồi.
- **Organization policy/permission boundary:** guardrail giới hạn quyền tối đa hoặc cấm một số thao tác.
- **Application authorization:** kiểm tra quyền nghiệp vụ trước khi gọi KMS.

Không phải nền tảng nào cũng có tất cả các lớp trên hoặc kết hợp chúng theo cùng cách. Một số hệ thống yêu cầu key policy trực tiếp cho phép principal; một số hệ thống đánh giá identity policy cùng resource policy. Hãy xác định mô hình thực tế và tránh suy luận rằng một IAM allow luôn đủ.

Grant nên có scope, grantee, operation, thời hạn hoặc cơ chế retire nếu nền tảng hỗ trợ. Tránh grant wildcard, grant không có owner hoặc grant tồn tại sau khi workload bị xóa.

## 12. Policy cho các loại key khác nhau

Policy cần phản ánh purpose và loại key:

| Loại key | Principal thường dùng | Action cần kiểm soát |
|---|---|---|
| Data Encryption Key (DEK) | Application hoặc crypto service | Encrypt/decrypt dữ liệu, thường thông qua envelope encryption |
| Key Encryption Key (KEK) | KMS/HSM và workload được ủy quyền | Wrap/unwrap DEK, rotate KEK |
| HMAC/signing key | Signing service hoặc webhook service | MAC/sign; hạn chế principal có quyền tạo tag |
| TLS private key | TLS endpoint hoặc HSM-backed service | Sign handshake; hạn chế export và quyền ký tùy ý |
| CA private key | PKI service và custodians | Issue/sign certificate theo ceremony và policy chặt |
| Backup key | Backup/restore service và custodian | Wrap/unwrap backup, restore theo phê duyệt |

Không dùng một key cho nhiều mục đích chỉ để giảm số lượng key. Purpose separation giúp policy rõ ràng, rotation độc lập và giới hạn tác động khi một service hoặc key bị compromise.

## 13. Kiểm soát export và non-exportable key

Export là thao tác rủi ro cao vì tạo bản sao key material ngoài KMS/HSM. Với nhiều workload, ứng dụng chỉ cần gọi encrypt/decrypt/sign bằng key handle, không cần đọc raw key.

Các lựa chọn:

- Non-exportable key: key material không được xuất khỏi thiết bị hoặc dịch vụ.
- Wrapped export: chỉ cho phép export ở dạng được mã hóa bằng wrapping key được kiểm soát.
- No export: policy từ chối export cho mọi principal ứng dụng.
- Controlled backup/restore: backup theo quy trình riêng, có dual control và audit.

Non-exportable không đồng nghĩa không thể bị lạm dụng. Nếu principal có quyền decrypt, kẻ tấn công chiếm được principal có thể yêu cầu KMS decrypt dữ liệu. Nếu principal có quyền sign, attacker có thể yêu cầu tạo chữ ký giả dù không lấy được private key. Do đó, cần kiểm soát operation, context, rate, data scope và ứng dụng gọi key.

## 14. Key access trong envelope encryption

Envelope encryption thường dùng DEK để mã hóa dữ liệu và KEK để wrap DEK. Ứng dụng không cần quyền export KEK; nó chỉ cần quyền gọi wrap/unwrap hoặc KMS decrypt trên wrapped DEK.

Một policy an toàn có thể quy định:

1. Workload chỉ được dùng một KEK cụ thể trong môi trường production.
2. Workload chỉ được unwrap DEK khi encryption context khớp tenant và purpose.
3. Workload không được export KEK, update key policy hoặc schedule deletion.
4. Chỉ key operator được rotate KEK theo quy trình.
5. Chỉ backup/restore role được dùng quyền phục hồi theo phê duyệt.
6. Audit ghi principal, key ID, operation, context và kết quả.

~~~mermaid
flowchart TD
    A[Application workload] --> B[Request unwrap DEK]
    B --> C[Authorization: principal + key + action + context]
    C -->|Allow| D[KMS/HSM dùng KEK]
    C -->|Deny| X[Từ chối và audit]
    D --> E[DEK được trả về hoặc dùng qua handle]
    E --> F[Ứng dụng mã hóa/giải mã dữ liệu]
    F --> G[Ciphertext + wrapped DEK]
    G --> H[Storage]
~~~

Nếu ứng dụng nhận DEK dạng plaintext trong bộ nhớ, cần giảm thời gian tồn tại, giới hạn heap dump và quyền truy cập tiến trình. Khi provider hỗ trợ thao tác trong HSM/KMS, cân nhắc giữ key operation bên trong dịch vụ.

## 15. Ví dụ policy theo nguyên tắc tối thiểu

Giả sử hệ thống có key dùng để bảo vệ dữ liệu đơn hàng production. Order service cần decrypt DEK đã wrap cho tenant của nó. Một policy logic có thể mô tả:

~~~yaml
policy_name: order-data-decrypt
default_effect: deny
rules:
  - effect: allow
    principal: workload:order-service-prod
    resource: key:orders-kek-prod
    actions:
      - decrypt
    conditions:
      environment: production
      tenant_context: matches_authenticated_tenant
      purpose: orders-data
  - effect: deny
    principal: "*"
    resource: key:orders-kek-prod
    actions:
      - export
      - update_policy
      - schedule_deletion
~~~

Đây là pseudo-policy để minh họa mô hình, không phải schema dùng trực tiếp cho một KMS cụ thể. Trong triển khai thực tế, cần ánh xạ principal, resource, action và condition vào cú pháp chính thức của nền tảng. Quy tắc deny phải được bảo đảm có hiệu lực trong mô hình policy evaluation đang dùng.

Policy này không tự chứng minh tenant context là hợp lệ. Ứng dụng phải xác thực caller và lấy tenant từ nguồn tin cậy trước khi tạo request KMS. Nếu tenant context do client tự gửi mà không được kiểm tra, condition có thể bị lợi dụng.

## 16. Kiểm soát ở ứng dụng và ở KMS/HSM

Nên thực thi defense in depth:

- **Application layer:** xác thực user, kiểm tra quyền nghiệp vụ, tenant ownership, record access và mục đích yêu cầu.
- **Workload identity layer:** xác thực service, cấp credential ngắn hạn và giới hạn scope.
- **KMS/HSM layer:** kiểm tra principal, key, action, context, key state và policy.
- **Infrastructure layer:** giới hạn network, host, process identity, filesystem và quyền quản trị.
- **Audit/monitoring layer:** ghi nhận thao tác, phát hiện bất thường và cảnh báo.

KMS/HSM không hiểu đầy đủ ngữ cảnh nghiệp vụ của ứng dụng. Ví dụ, KMS có thể biết order-service được phép decrypt bằng key orders-kek, nhưng không biết user cuối có quyền xem order 123 hay không. Ứng dụng vẫn phải kiểm tra quyền đó trước khi gọi decrypt.

Ngược lại, chỉ kiểm tra authorization ở ứng dụng là chưa đủ nếu credential của ứng dụng bị lộ. Policy ở KMS/HSM tạo thêm ranh giới để hạn chế key và operation mà credential có thể sử dụng.

## 17. Audit và giám sát key access

Audit trail cần đủ thông tin để trả lời ai đã làm gì, với key nào, khi nào, từ đâu và kết quả ra sao.

Các trường hữu ích:

- Timestamp và request/correlation ID.
- Principal hoặc workload identity đã xác thực.
- Key ID, key version và purpose.
- Action được yêu cầu.
- Decision: allow hoặc deny.
- Context/condition đã áp dụng ở mức không nhạy cảm.
- Nguồn request, region hoặc workload metadata.
- Kết quả operation và mã lỗi.
- Tham chiếu change ticket/approval nếu là thao tác quản trị.

Không ghi raw key material, pepper, password, access token hoặc plaintext nhạy cảm vào audit log. Encryption context cũng không nên chứa bí mật vì có thể được ghi lại.

Các tín hiệu cần giám sát:

- Principal lần đầu truy cập một key hoặc truy cập key ngoài lịch.
- Tăng đột biến decrypt, unwrap hoặc sign.
- Denied request tăng mạnh hoặc nhiều lần thử key ID.
- Policy/grant thay đổi ngoài cửa sổ bảo trì.
- Key được export, schedule deletion hoặc restore.
- Workload đã nghỉ nhưng vẫn dùng key.
- Operation từ region, network hoặc identity không thường lệ.

Log cần được bảo vệ khỏi sửa đổi và xóa trái phép; quyền đọc audit nên tách khỏi quyền sử dụng key. Đặt cảnh báo theo mức độ quan trọng và có người chịu trách nhiệm xử lý.

## 18. Cấp quyền tạm thời và break-glass access

Một số thao tác cần quyền nâng cao trong thời gian ngắn, ví dụ điều tra sự cố, restore dữ liệu hoặc chuyển đổi key. Không nên cấp quyền thường trực chỉ để đáp ứng tình huống hiếm.

Quy trình tạm thời có thể gồm:

1. Người yêu cầu nêu lý do, key, action và thời hạn.
2. Owner hoặc security approver xác nhận phạm vi.
3. Cấp credential/grant ngắn hạn với scope tối thiểu.
4. Bắt buộc MFA hoặc xác thực mạnh cho thao tác quản trị nếu nền tảng hỗ trợ.
5. Giám sát thao tác trong thời gian quyền có hiệu lực.
6. Tự động hết hạn hoặc thu hồi grant.
7. Review audit sau khi hoàn tất.

Break-glass account cần được bảo vệ riêng, không dùng cho công việc hàng ngày, có kiểm soát truy cập vật lý hoặc xác thực mạnh, cảnh báo khi sử dụng và quy trình hậu kiểm. Không để tài khoản khẩn cấp trở thành đường vòng bỏ qua mọi policy.

## 19. Key state và access policy trong vòng đời

Quyền truy cập phải xét cả trạng thái của key:

| Trạng thái key hoặc chế độ policy | Cách policy nên xử lý |
|---|---|
| Pending creation | Chỉ cho phép thao tác provisioning được phê duyệt |
| Enabled/active | Cho phép action đúng purpose và principal |
| Disabled | Từ chối operation sử dụng key; chỉ cho phép quản trị cần thiết |
| Rotation in progress | Cho phép version mới và version cũ theo kế hoạch chuyển tiếp |
| Retired-use policy (decrypt-only/verify-only) | Chặn tạo dữ liệu mới; giữ quyền đọc/xác minh có giới hạn nếu cần |
| Compromised | Cô lập, disable hoặc revoke theo incident response |
| Pending deletion | Chặn operation mới theo policy và kiểm tra dependency |
| Destroyed | Không còn key material để sử dụng; audit và metadata lịch sử vẫn được giữ theo policy |

Một key đã disable không nhất thiết đã bị hủy; một key đang pending deletion cũng chưa chắc đã được zeroize. Policy và monitoring cần phản ánh chính xác trạng thái, không suy luận rằng thao tác disable đã kết thúc vòng đời.

## 20. Kiểm thử key access policy

Không chỉ kiểm thử trường hợp được phép. Cần kiểm thử cả các tình huống bị từ chối và trường hợp policy thay đổi:

- Principal đúng, key đúng, action đúng và context hợp lệ: phải allow.
- Principal đúng nhưng key khác: phải deny.
- Principal đúng nhưng action quá quyền: phải deny.
- Context thiếu, sai tenant hoặc sai environment: phải deny.
- Key disabled, compromised hoặc destroyed: phải deny operation sử dụng.
- Principal đã bị thu hồi hoặc credential hết hạn: phải deny.
- Có explicit deny xung đột với allow: kết quả phải theo semantics đã định nghĩa.
- Workload cũ đã nghỉ: không còn grant hoặc quyền hiệu lực.
- Key rotation: principal chỉ dùng được version trong giai đoạn cho phép.
- Break-glass: có approval, expiry, audit và hậu kiểm.

Nên dùng policy simulator hoặc môi trường thử nghiệm nếu nền tảng hỗ trợ. Kiểm thử cả API trực tiếp và đường gọi qua ứng dụng, vì application authorization và KMS authorization có thể cho kết quả khác nhau.

## 21. Các sai lầm thường gặp

- **Cấp quyền wildcard:** principal có thể dùng nhiều key hơn nhu cầu.
- **Gộp quyền sign/decrypt với quản trị:** một credential bị lộ có thể vừa sử dụng key vừa mở rộng quyền.
- **Dùng một role cho mọi workload:** khó giới hạn tenant và blast radius.
- **Tin caller-provided context:** attacker tự khai tenant hoặc purpose để thỏa điều kiện.
- **Không có default deny:** key mới hoặc principal mới có thể nhận quyền ngoài dự kiến.
- **Chỉ kiểm soát ở ứng dụng:** credential bị lộ có thể gọi KMS trực tiếp.
- **Chỉ dựa vào KMS:** bỏ qua quyền nghiệp vụ của user cuối trong ứng dụng.
- **Cho rằng non-exportable là đủ:** attacker vẫn có thể gọi sign/decrypt qua API nếu có quyền.
- **Grant không có owner hoặc expiry:** quyền tồn tại sau khi workload không còn cần.
- **Không audit denied operation:** bỏ lỡ tín hiệu dò quét và cấu hình sai.
- **Không review policy định kỳ:** quyền tích lũy theo thời gian.
- **Không tính key state:** cho phép dùng key disabled hoặc tiếp tục dùng key compromised.
- **Break-glass không hậu kiểm:** quyền khẩn cấp trở thành đường truy cập thường trực.

## 22. Checklist thiết kế Key access policy

- [ ] Mỗi key có owner, purpose, environment và classification rõ ràng.
- [ ] Principal được xác thực bằng workload/user identity tin cậy.
- [ ] Policy xác định rõ resource, action và context.
- [ ] Default deny được áp dụng; explicit deny có semantics rõ ràng.
- [ ] Quyền encrypt/decrypt/sign/verify/wrap/unwrap được tách phù hợp.
- [ ] Quyền data plane và control plane được phân tách.
- [ ] Least privilege được áp dụng theo key, tenant và environment.
- [ ] RBAC/ABAC attributes đến từ nguồn tin cậy.
- [ ] Quyền export bị cấm hoặc có phê duyệt và wrapping phù hợp.
- [ ] Key policy, IAM policy, grant và guardrail được kiểm tra cùng nhau.
- [ ] Có separation of duties và dual control cho thao tác rủi ro cao.
- [ ] Application authorization và KMS/HSM authorization cùng được thực thi.
- [ ] Key state, rotation, disable, revoke và deletion được phản ánh trong policy.
- [ ] Audit ghi principal, key ID, action, context và decision mà không ghi bí mật.
- [ ] Có cảnh báo cho truy cập bất thường, policy change và thao tác quản trị nhạy cảm.
- [ ] Grant tạm thời có expiry; break-glass có approval và hậu kiểm.
- [ ] Có test allow, deny, context mismatch, revoked identity và rotation.
- [ ] Policy được review định kỳ và mỗi thay đổi có owner/bằng chứng.

Key access policy xác định ranh giới giữa principal, key và thao tác mật mã trong từng ngữ cảnh. Chính sách an toàn cần default deny, least privilege, tách quyền sử dụng khỏi quyền quản trị, ràng buộc theo purpose và context, đồng thời thực thi ở cả ứng dụng lẫn KMS/HSM. Khi policy gắn với vòng đời key, có audit đáng tin cậy và được kiểm thử cả trường hợp allow lẫn deny, tổ chức giảm nguy cơ lạm dụng khóa, lộ dữ liệu và mất khả năng phục hồi.

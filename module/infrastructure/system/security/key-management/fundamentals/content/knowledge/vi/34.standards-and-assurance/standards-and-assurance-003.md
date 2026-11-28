# Key management policy theo NIST

**Key management policy (chính sách quản lý khóa mật mã)** là tập hợp các quy tắc cấp tổ chức xác định khóa nào được phép sử dụng, ai chịu trách nhiệm, khóa phải được bảo vệ ra sao và các hoạt động trong vòng đời khóa phải tuân theo kiểm soát nào. Chính sách tạo ra một chuẩn chung để các nhóm phát triển, vận hành, an ninh, kiểm toán và nhà cung cấp dịch vụ cùng quản lý khóa nhất quán.

NIST cung cấp hướng dẫn và khung kiểm soát để tổ chức xây dựng chính sách. Các tài liệu quan trọng gồm NIST SP 800-57 Part 1 về quản lý khóa, SP 800-130 về thiết kế hệ thống quản lý khóa mật mã (CKMS), SP 800-152 về yêu cầu CKMS trong phạm vi hệ thống liên bang Hoa Kỳ, SP 800-53 về kiểm soát an ninh và SP 800-131A về chuyển đổi thuật toán/độ dài khóa. Tổ chức cần xác định tài liệu nào áp dụng cho môi trường của mình; không phải mọi khuyến nghị NIST đều tự động trở thành nghĩa vụ pháp lý cho mọi tổ chức.

Chính sách phải kết nối yêu cầu bảo vệ dữ liệu với các quyết định kỹ thuật: tạo khóa, phân phối, lưu trữ, cấp quyền sử dụng, cryptoperiod, rotation, backup, recovery, xử lý compromise, thu hồi và destruction. Một chính sách tốt nêu rõ kết quả bắt buộc và trách nhiệm; tiêu chuẩn kỹ thuật cùng quy trình vận hành sẽ cụ thể hóa cách thực hiện trong KMS, HSM, Java KeyStore và ứng dụng.

## 1. Vai trò của Key management policy

Khóa mật mã là tài sản có thể bảo vệ nhiều loại dữ liệu và dịch vụ. Nếu mỗi nhóm tự chọn thuật toán, tự lưu khóa hoặc tự quyết định thời hạn sử dụng, tổ chức dễ xuất hiện khóa trùng mục đích, khóa không có owner, quyền truy cập quá rộng, backup không kiểm soát và dữ liệu không thể giải mã sau khi thay đổi hệ thống.

Key management policy giải quyết các vấn đề này bằng cách:

- Xác định phạm vi hệ thống, dữ liệu, môi trường và loại khóa phải tuân theo chính sách.
- Quy định vai trò, quyền hạn và trách nhiệm trong từng giai đoạn vòng đời.
- Đặt yêu cầu tối thiểu về thuật toán, độ dài, sinh khóa, lưu trữ và sử dụng.
- Kiểm soát truy cập, phân tách nhiệm vụ và phê duyệt thao tác đặc quyền.
- Quy định cryptoperiod, rotation, backup, recovery, compromise, revocation và destruction.
- Bảo đảm hoạt động khóa có audit, monitoring và bằng chứng kiểm toán.
- Quản lý ngoại lệ, rủi ro còn lại và kế hoạch nâng cấp thuật toán.

Chính sách không nên chỉ nói “mọi khóa phải được bảo vệ an toàn”. Mỗi yêu cầu cần có phạm vi áp dụng, chủ thể chịu trách nhiệm, cách kiểm chứng và bằng chứng có thể thu thập.

## 2. NIST cung cấp hướng dẫn nào cho quản lý khóa?

Các tài liệu NIST có vai trò khác nhau và nên được dùng đúng mục đích:

| Tài liệu | Vai trò trong xây dựng chính sách |
|---|---|
| **SP 800-57 Part 1 Rev. 5** | Hướng dẫn chung về quản lý khóa: loại khóa, mục đích sử dụng, bảo vệ, cryptoperiod, backup, recovery, compromise và destruction |
| **SP 800-130** | Khung thiết kế hệ thống quản lý khóa mật mã (CKMS), giúp xác định các chủ đề và yêu cầu cần xem xét trong thiết kế |
| **SP 800-152** | Yêu cầu đối với CKMS trong hệ thống liên bang Hoa Kỳ; hữu ích làm tham chiếu assurance khi phạm vi áp dụng phù hợp |
| **SP 800-53 Rev. 5** | Danh mục kiểm soát an ninh và quyền riêng tư; có các kiểm soát liên quan quản lý khóa và bảo vệ mật mã như SC-12, SC-13 |
| **SP 800-131A Rev. 2** | Hướng dẫn chuyển đổi việc sử dụng thuật toán và độ dài khóa khi mức an toàn hoặc khuyến nghị thay đổi |
| **FIPS 140-3** | Yêu cầu bảo mật đối với cryptographic module; có thể được yêu cầu trong môi trường hoặc hợp đồng cần module được xác nhận phù hợp |

SP 800-57 là nguồn nền tảng để xây dựng quy tắc quản lý khóa. SP 800-130 giúp thiết kế CKMS; SP 800-152 hướng đến bối cảnh liên bang; SP 800-53 hỗ trợ ánh xạ kiểm soát; SP 800-131A hỗ trợ quản lý thay đổi thuật toán. FIPS 140-3 đánh giá cryptographic module, không thay thế toàn bộ chính sách quản lý khóa của tổ chức.

## 3. Phân biệt policy, standard, procedure và key management practice

Tổ chức nên tách yêu cầu cấp chính sách khỏi thông số kỹ thuật và hướng dẫn thao tác để dễ quản trị thay đổi.

| Tài liệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Policy** | Điều gì bắt buộc và ai chịu trách nhiệm? | Khóa production phải có owner, được quản lý tập trung và có audit |
| **Standard** | Mức kỹ thuật tối thiểu là gì? | Thuật toán, độ dài khóa, module, KDF, nonce và cryptoperiod được chấp thuận |
| **Procedure / runbook** | Thực hiện công việc theo bước nào? | Tạo key version, cấp policy, canary, cutover, verify và retire key cũ |
| **Key management practices** | Tổ chức thực tế vận hành, bảo vệ và kiểm soát khóa ra sao? | Mô tả KMS/HSM, phân quyền, backup, recovery, audit và xử lý incident |
| **Evidence / records** | Làm sao chứng minh đã tuân thủ? | Key inventory, approval, audit event, rotation report và recovery test |

Một thay đổi về số vòng PBKDF2 hoặc cấu hình provider có thể cần cập nhật standard và procedure mà không phải viết lại policy. Ngược lại, nếu tổ chức quyết định cho phép một nhóm mới export private key, đó là thay đổi rủi ro và quyền hạn, cần xem xét ở cấp policy và phê duyệt tương ứng.

## 4. Phạm vi và phân loại khóa

Chính sách cần xác định khóa nào thuộc phạm vi quản lý, kể cả khóa do ứng dụng, nhà cung cấp, cloud KMS hoặc HSM tạo và vận hành. Phạm vi nên bao gồm production, non-production, backup, disaster recovery, CI/CD, endpoint, thiết bị và hệ thống bên thứ ba có xử lý key material.

Khóa nên được phân loại theo nhiều chiều:

- **Theo thuật toán:** symmetric, asymmetric, key agreement, key wrapping, MAC và signing key.
- **Theo chức năng:** DEK, KEK, master/root key, TLS key, code-signing key, certificate private key, HMAC key.
- **Theo mức độ nhạy cảm:** khóa công khai, khóa bí mật thông thường, khóa có ảnh hưởng rộng, khóa gốc hoặc khóa điều khiển hệ thống.
- **Theo môi trường:** development, test, staging, production và disaster recovery.
- **Theo chủ sở hữu:** ứng dụng, dịch vụ, tenant, nhóm nghiệp vụ hoặc tổ chức.

Không phải mọi secret đều là encryption key. API token, password database và OAuth client secret cũng cần được quản lý, nhưng có thể có chính sách lưu trữ khác. Public key và certificate có thể được phân phối công khai, song nguồn gốc, tính toàn vẹn và trạng thái tin cậy vẫn phải được xác minh.

## 5. Vai trò và phân tách nhiệm vụ

Chính sách cần gán trách nhiệm rõ ràng. Một người hoặc một workload không nên tự tạo, tự phê duyệt, export, sử dụng và hủy khóa có ảnh hưởng cao mà không có kiểm soát độc lập.

| Vai trò | Trách nhiệm chính |
|---|---|
| Business/data owner | Xác định dữ liệu, mục đích bảo vệ, mức độ quan trọng và yêu cầu sẵn sàng |
| Key owner | Chịu trách nhiệm vòng đời của key ID/version và xác nhận dependency |
| Key custodian / KMS administrator | Vận hành kho khóa, tạo/cấp phát/rotate/disable theo policy |
| Security architect | Phê duyệt thiết kế mật mã, phân loại, key hierarchy và rủi ro |
| Application/workload owner | Tích hợp API, quản lý metadata và dùng khóa đúng mục đích |
| Auditor | Kiểm tra bằng chứng, quyền truy cập, audit trail và ngoại lệ |
| Incident responder | Điều phối compromise response, revoke, recovery và điều tra |

Với thao tác nhạy cảm như export, phục hồi root key, thay đổi policy của KEK hoặc destruction không thể đảo ngược, chính sách có thể yêu cầu dual control, quorum hoặc phê duyệt độc lập. Phân tách nhiệm vụ cần được thực thi bằng IAM/policy, quy trình phê duyệt và audit; chỉ ghi tên vai trò trong tài liệu là chưa đủ.

## 6. Quy định về tạo khóa và lựa chọn thuật toán

Chính sách nên yêu cầu key material được sinh bằng nguồn ngẫu nhiên mật mã và cryptographic module/provider phù hợp. Không dùng password, timestamp, UUID không phù hợp, số ngẫu nhiên thông thường hoặc dữ liệu nghiệp vụ làm key material.

Các yêu cầu nên được chuẩn hóa:

- Chỉ dùng thuật toán, mode, curve, key size và tham số được tổ chức chấp thuận.
- Chọn mức bảo mật dựa trên loại dữ liệu, thời gian cần bảo vệ và hướng dẫn hiện hành.
- Dùng CSPRNG hoặc cơ chế tạo khóa đã được provider/KMS/HSM hỗ trợ.
- Tách khóa theo mục đích; không tái sử dụng một key cho encryption, MAC, wrapping và signing nếu thiết kế không cho phép rõ ràng.
- Dùng AEAD cho mã hóa dữ liệu khi phù hợp; quản lý nonce/IV và authentication tag theo yêu cầu thuật toán.
- Lưu metadata đủ để xác định thuật toán, key version và định dạng dữ liệu trong tương lai.
- Có kế hoạch crypto agility để thay thuật toán hoặc provider mà không mất khả năng đọc dữ liệu.

SP 800-131A hỗ trợ đánh giá việc tiếp tục, hạn chế hoặc ngừng sử dụng thuật toán/độ dài khóa. Chính sách không nên đóng cứng một danh sách thuật toán vĩnh viễn; cần có standard được rà soát định kỳ và quy trình chuyển đổi khi khuyến nghị thay đổi.

## 7. Phân phối, cấp phát và lưu trữ khóa

Khóa phải được phân phối qua kênh xác thực và được bảo vệ. Với khóa đối xứng, cần bảo đảm chỉ các bên được phép nhận key material hoặc gọi thao tác qua KMS. Với khóa bất đối xứng, public key có thể phân phối rộng nhưng phải xác minh nguồn gốc; private key cần được bảo vệ nghiêm ngặt.

Chính sách nên quy định:

- Ưu tiên KMS/HSM hoặc hệ thống quản lý khóa tập trung cho khóa production.
- Khóa có giá trị cao nên được tạo và giữ trong ranh giới bảo vệ phù hợp; cân nhắc non-exportable.
- Dùng envelope encryption cho dữ liệu cần mã hóa ở quy mô lớn: DEK mã hóa payload, KEK bảo vệ DEK.
- Không lưu key material rõ trong source code, repository, image, log, ticket, email hoặc cấu hình thông thường.
- Tách key material khỏi ciphertext và metadata; bảo vệ KEK độc lập với nơi lưu dữ liệu.
- Không dùng cùng một master secret cho nhiều môi trường hoặc tenant.
- Quản lý backup, replica và disaster recovery như các bản sao nhạy cảm của khóa.

Java KeyStore có thể phù hợp với một số trường hợp lưu khóa ở cấp ứng dụng, nhưng password bảo vệ keystore không biến nó thành HSM. Nếu cần chống trích xuất key material hoặc kiểm soát tập trung, cân nhắc KMS/HSM và provider tương ứng.

## 8. Access control và sử dụng khóa

Chính sách cần xác định ai được gọi thao tác nào trên key ID/version nào. Cấp quyền theo least privilege và default deny; tách quyền quản trị khóa khỏi quyền sử dụng khóa.

Ví dụ phân tách action:

| Action | Quyền cần quản lý riêng |
|---|---|
| `Encrypt` / `Decrypt` | Workload cần mã hóa hoặc giải mã đúng loại dữ liệu |
| `Sign` / `Verify` | Dịch vụ ký và bên xác minh; private signing key phải được kiểm soát chặt |
| `WrapKey` / `UnwrapKey` | Dịch vụ quản lý DEK/KEK và quy trình migration được phê duyệt |
| `ExportKey` / `ImportKey` | Quy trình di chuyển hoặc recovery đặc biệt; ưu tiên wrapped export và dual control |
| `Disable` / `Rotate` | Key custodian hoặc automation được ủy quyền |
| `ScheduleDeletion` / `Destroy` | Quyền đặc biệt, có kiểm tra dependency và phê duyệt độc lập |

Policy nên giới hạn principal, resource, action, environment, tenant, region, purpose và thời hạn. Một workload có quyền `Decrypt` không tự động được quyền `ExportKey`; quyền đọc metadata không đồng nghĩa quyền lấy key material. Các quyết định allow/deny phải được ghi audit.

## 9. Cryptoperiod và rotation

**Cryptoperiod** là khoảng thời gian khóa được phép dùng cho một mục đích mật mã. Chính sách cần xác định cách chọn cryptoperiod theo loại khóa, thuật toán, lượng dữ liệu, tần suất sử dụng, mức độ nhạy cảm, khả năng compromise và yêu cầu lưu giữ.

Không nên áp dụng một thời hạn duy nhất cho mọi loại khóa. Khóa dùng mã hóa dữ liệu lớn, khóa ký, KEK, khóa TLS và khóa xác thực có vai trò cùng rủi ro khác nhau. SP 800-57 cung cấp hướng dẫn để xem xét thời gian sử dụng khóa; tổ chức cần lập standard cụ thể dựa trên đánh giá rủi ro và môi trường triển khai.

Chính sách nên quy định:

- Khi nào tạo version mới: định kỳ, đạt hạn mức sử dụng, thay đổi thuật toán, thay đổi owner hoặc có dấu hiệu compromise.
- Khi nào ngừng dùng khóa cũ cho thao tác tạo dữ liệu/chữ ký mới.
- Có cho phép decrypt/verify dữ liệu cũ trong giai đoạn chuyển tiếp hay không.
- Cách dual-read/single-write, rewrap DEK hoặc re-encrypt payload.
- Tiêu chí xác minh trước khi retire và destroy khóa cũ.
- Cách rollback rotation khi lỗi, và điều kiện bắt buộc forward recovery khi khóa cũ không còn tin cậy.

Với khóa ký, cần xem xét thời điểm tạo chữ ký và thời gian xác minh chữ ký lịch sử. Với khóa mã hóa, dữ liệu có thể cần giải mã lâu sau khi khóa ngừng dùng để mã hóa mới. Vì vậy, end-of-use không nhất thiết đồng nghĩa destroy ngay.

## 10. Backup, escrow và recovery

Mất khóa có thể khiến dữ liệu không thể giải mã hoặc dịch vụ không thể ký/xác thực. Tuy nhiên, backup khóa tạo thêm bản sao nhạy cảm và có thể làm tăng phạm vi compromise. Chính sách cần quy định khóa nào được backup, ai có quyền phục hồi và cách bảo vệ bản sao.

Các yêu cầu nên có:

- Chỉ backup khóa có nhu cầu phục hồi được phê duyệt; không mặc định export mọi khóa.
- Bảo vệ backup bằng wrapping/encryption độc lập và lưu ở miền kiểm soát phù hợp.
- Tách quyền tạo backup, truy cập backup và thực hiện recovery.
- Dùng dual control/quorum cho root key hoặc khóa có ảnh hưởng rộng.
- Ghi nhận key ID/version, thời gian, nguồn, checksum/fingerprint và người thực hiện.
- Kiểm thử recovery định kỳ trong môi trường kiểm soát.
- Đảm bảo backup, metadata và wrapping key cùng tồn tại trong thời gian dữ liệu cần được bảo vệ.
- Hủy bản backup hết hạn theo chính sách retention và destruction.

Escrow hoặc recovery key có thể hỗ trợ phục hồi nhưng phải được thiết kế cẩn thận. Nếu một cá nhân hoặc một hệ thống duy nhất có thể khôi phục mọi khóa, escrow trở thành điểm tập trung rủi ro. Chính sách cần giới hạn mục đích, số người phê duyệt, phạm vi và audit.

## 11. Xử lý khóa bị compromise và thu hồi

Khi nghi ngờ key material bị lộ, tổ chức cần xác định phạm vi dữ liệu, workload, bản sao và thao tác có thể bị ảnh hưởng. Chính sách phải chỉ rõ ai được kích hoạt incident response, quyền disable/revoke khẩn cấp và cách phối hợp thay thế khóa.

Quy trình tối thiểu nên bao gồm:

1. Xác định key ID/version, loại khóa, owner, thời điểm phát hiện và bằng chứng.
2. Đánh giá liệu key material, wrapped key, credential quản trị hoặc workload identity có bị lộ không.
3. Chặn thao tác mới bằng khóa bị compromise theo policy; thu hồi quyền/session liên quan.
4. Tạo khóa sạch và cấp quyền cho workload cần tiếp tục hoạt động.
5. Đánh giá dữ liệu/ciphertext đã được bảo vệ bởi khóa cũ; rewrap hoặc re-encrypt khi cần.
6. Với signing key/certificate, đánh giá chữ ký, certificate revocation và relying party.
7. Bảo toàn audit, log và bằng chứng điều tra.
8. Xử lý bản sao trong backup, replica, file tạm và hệ thống bên thứ ba.
9. Destroy khóa và bản sao theo quy trình sau khi dependency được xử lý.
10. Ghi nhận nguyên nhân gốc, phạm vi ảnh hưởng và hành động phòng ngừa.

Revoke quyền ở KMS không thu hồi được bản key material đã export và bị sao chép. Rewrap DEK không xóa được wrapped DEK cũ mà attacker đã lấy. Chính sách cần phân biệt thu hồi quyền sử dụng trong hệ thống với xử lý bản sao đã rời khỏi ranh giới tin cậy.

## 12. Destruction và crypto-erasure

Key destruction là bước kết thúc vòng đời khóa. Xóa alias hoặc record metadata không chứng minh key material đã bị hủy. Chính sách phải xác định phương pháp hủy theo nơi lưu và cơ chế backup.

Yêu cầu cần xem xét:

- Xác minh không còn dữ liệu, archive, replica hoặc backup cần khóa để giải mã.
- Xác định tất cả bản sao key material, wrapped key và bản sao trong HSM/KMS backup.
- Thu hồi quyền, disable hoặc schedule deletion theo state machine của provider.
- Áp dụng dual control cho khóa có giá trị cao hoặc thao tác không thể đảo ngược.
- Ghi bằng chứng destruction: key ID/version, actor, approver, thời gian, phương pháp và kết quả.
- Kiểm tra retention/legal hold và nghĩa vụ lưu trữ trước khi hủy.

**Crypto-erasure** có thể làm dữ liệu không thể giải mã bằng cách hủy khóa mã hóa duy nhất cần thiết. Cách này chỉ có hiệu lực nếu mọi bản sao khóa và bản sao backup có thể phục hồi đều được xử lý; nếu còn một bản sao key material, dữ liệu có thể vẫn giải mã được. Cần đánh giá crypto-erasure theo threat model và bằng chứng của KMS/HSM.

## 13. Audit, monitoring và bằng chứng assurance

Chính sách cần yêu cầu ghi nhận các hoạt động quan trọng trong vòng đời khóa: create, import, export, encrypt, decrypt, sign, unwrap, policy change, rotate, disable, revoke, recovery và destroy.

Audit event tối thiểu nên xác định:

- Principal/workload và danh tính đã xác thực.
- Key ID, version, loại khóa và owner.
- Action, decision, outcome, thời gian và request/correlation ID.
- Policy hoặc approval áp dụng cho thao tác đặc quyền.
- Lý do từ chối, lỗi và trạng thái hoàn tất.

Không ghi key material, private key, password, PIN, token hoặc plaintext vào log. Audit log cần được bảo vệ tính toàn vẹn, phân tách quyền quản trị, lưu giữ theo chính sách và giám sát pipeline để phát hiện event bị mất hoặc đến trễ.

Evidence phục vụ assurance có thể gồm key inventory, policy version, approval record, access review, audit event, rotation report, recovery test, destruction certificate/record, incident report và kết quả kiểm tra cấu hình KMS/HSM. Mỗi yêu cầu trong policy nên có ít nhất một cách kiểm chứng và một owner chịu trách nhiệm.

## 14. Quản lý nhà cung cấp, cloud KMS và trách nhiệm dùng chung

Khi dùng cloud KMS/HSM hoặc dịch vụ quản lý khóa bên ngoài, chính sách cần xác định ranh giới trách nhiệm giữa tổ chức và nhà cung cấp.

Các câu hỏi cần trả lời:

- Ai kiểm soát root key, wrapping key và key metadata?
- Khóa được tạo trong KMS/HSM nào và module có chứng nhận/validation phù hợp yêu cầu không?
- Nhà cung cấp có thể truy cập key material hoặc thao tác quản trị nào?
- Audit log có thể xuất sang tài khoản lưu trữ độc lập không?
- Có hỗ trợ non-exportable, dual control, backup, replication và recovery không?
- Cách di chuyển khóa khi đổi nhà cung cấp hoặc kết thúc hợp đồng là gì?
- Ai chịu trách nhiệm thông báo compromise, outage hoặc thay đổi dịch vụ?
- Dữ liệu và khóa được lưu ở region/jurisdiction nào theo yêu cầu hợp đồng?

Không nên giả định nhà cung cấp chịu toàn bộ trách nhiệm chỉ vì họ vận hành HSM. Tổ chức vẫn phải quản lý principal, policy, workload, dữ liệu, quyền truy cập và cấu hình sử dụng dịch vụ theo shared responsibility model.

## 15. Ngoại lệ và chấp nhận rủi ro

Một hệ thống cũ có thể chưa hỗ trợ KMS, một đối tác có thể yêu cầu định dạng khóa đặc biệt hoặc một thuật toán cũ có thể cần duy trì tạm thời để đọc dữ liệu lưu trữ. Chính sách cần có quy trình ngoại lệ rõ ràng thay vì bỏ qua kiểm soát.

Một yêu cầu ngoại lệ nên ghi:

- Quy tắc policy không thể đáp ứng và lý do.
- Hệ thống, dữ liệu, key ID/version và phạm vi bị ảnh hưởng.
- Rủi ro, khả năng xảy ra và tác động.
- Biện pháp bù trừ, giới hạn truy cập và giám sát bổ sung.
- Người chịu trách nhiệm và người có thẩm quyền chấp nhận rủi ro.
- Thời điểm bắt đầu, ngày hết hạn và kế hoạch khắc phục.
- Điều kiện thu hồi ngoại lệ sớm nếu xuất hiện sự cố.

Ngoại lệ không nên vô thời hạn. Mỗi lần gia hạn cần đánh giá lại rủi ro và bằng chứng. Không dùng quy trình ngoại lệ để hợp thức hóa việc export khóa hoặc tiếp tục dùng thuật toán không còn được chấp thuận mà không có kế hoạch chuyển đổi.

## 16. Đưa policy vào cấu hình và tự động hóa

Chính sách chỉ có hiệu lực khi được chuyển thành kiểm soát có thể thực thi. Có thể biểu diễn một phần yêu cầu bằng policy-as-code, guardrail trong CI/CD, cấu hình KMS và workflow phê duyệt.

Ví dụ dưới đây là cấu hình minh họa độc lập với nhà cung cấp:

```yaml
keyPolicy:
  scope: production
  defaultDecision: DENY
  key:
    classification: HIGH
    ownerRequired: true
    allowedAlgorithms:
      - AES-256-GCM
      - RSA-OAEP-SHA-256-3072
      - RSASSA-PSS-SHA-256-3072
  storage:
    managedKmsRequired: true
    nonExportableByDefault: true
  permissions:
    separateCryptoAndExport: true
    exportRequiresApproval: true
    wrappedExportPreferred: true
  lifecycle:
    cryptoperiodProfileRequired: true
    rotationPlanRequired: true
    recoveryTestRequired: true
    destructionApprovalRequired: true
  audit:
    logKeyOperations: true
    logSecretMaterial: false
    immutableArchiveRequired: true
```

Đây là ví dụ về cách diễn đạt yêu cầu; không phải schema YAML chuẩn của NIST hoặc cú pháp policy KMS cụ thể. Các tên RSA trong ví dụ đã gắn với scheme và mục đích: OAEP cho mã hóa/đóng gói dữ liệu khóa phù hợp, PSS cho chữ ký; không dùng RSA như thuật toán mã hóa trực tiếp payload lớn. Tổ chức cần chuyển các trường này thành control thực tế, kiểm tra bằng automated test và xác minh trên KMS/HSM. Nếu policy-as-code nói `nonExportableByDefault` nhưng key được tạo với thuộc tính exportable, guardrail chưa được thực thi.

Automation nên có approval gate cho export, recovery và destroy; idempotency cho rotation; checkpoint cho migration; cảnh báo khi key không có owner hoặc sắp hết cryptoperiod; và bằng chứng cho mỗi lần thay đổi policy. Các thao tác nhạy cảm phải có audit độc lập và cơ chế fail-closed phù hợp.

## 17. Đo lường mức độ tuân thủ policy

Tổ chức cần các chỉ số để biết policy có được áp dụng thực tế hay không. Một số metrics hữu ích:

- Tỷ lệ khóa có owner, classification, purpose và key version đầy đủ.
- Tỷ lệ khóa production nằm trong KMS/HSM được chấp thuận.
- Số khóa exportable và số lần export theo loại khóa.
- Tỷ lệ key version quá cryptoperiod hoặc chưa có rotation plan.
- Số principal có quyền wildcard hoặc quyền export rộng.
- Tỷ lệ thao tác đặc quyền có approval và audit event.
- Tỷ lệ recovery test và rotation test thành công.
- Số khóa bị compromise, số incident và thời gian thu hồi quyền.
- Số khóa đã retired nhưng còn dependency chưa được xử lý.
- Số ngoại lệ đang mở, sắp hết hạn hoặc quá hạn khắc phục.

Metrics cần có định nghĩa, nguồn dữ liệu, owner, chu kỳ báo cáo và ngưỡng xử lý. Không dùng một tỷ lệ tổng hợp để che giấu nhóm khóa rủi ro cao; nên phân tích theo key classification, môi trường, owner và loại khóa.

## 18. Rà soát và cập nhật chính sách

Chính sách quản lý khóa cần được rà soát định kỳ và khi có thay đổi lớn. Các trigger có thể gồm:

- NIST hoặc tiêu chuẩn được tổ chức áp dụng thay đổi khuyến nghị.
- Thuật toán, key size hoặc cryptographic module không còn được chấp thuận.
- Tổ chức chuyển cloud/KMS/HSM hoặc thay đổi kiến trúc multi-tenant.
- Có incident, phát hiện audit hoặc lỗ hổng ảnh hưởng key management.
- Thay đổi pháp lý, hợp đồng, dữ liệu hoặc yêu cầu lưu giữ.
- Có loại khóa, workload hoặc use case mới.

Mỗi phiên bản policy cần có owner, người phê duyệt, ngày hiệu lực, lịch sử thay đổi, phạm vi và ngày rà soát tiếp theo. Khi cập nhật policy, cần đánh giá tác động tới key inventory, ứng dụng, ciphertext cũ, backup, certificate, workload và quy trình recovery.

## 19. Mẫu cấu trúc Key management policy

Một tài liệu policy chính thức có thể tổ chức theo cấu trúc sau:

1. **Purpose:** mục tiêu và kết quả bảo vệ cần đạt.
2. **Scope:** hệ thống, dữ liệu, môi trường, nhân sự và nhà cung cấp thuộc phạm vi.
3. **References:** NIST, tiêu chuẩn nội bộ, hợp đồng và yêu cầu pháp lý áp dụng.
4. **Definitions:** key, key material, DEK, KEK, cryptoperiod, compromise, revoke và destroy.
5. **Governance:** owner, custodian, approver, auditor và incident responder.
6. **Key classification:** loại khóa, mức nhạy cảm, purpose và owner.
7. **Cryptographic requirements:** thuật toán, độ dài, generation, provider và crypto agility.
8. **Lifecycle controls:** create, distribute, activate, use, rotate, retire, revoke và destroy.
9. **Storage and access:** KMS/HSM, KeyStore, exportability, IAM, least privilege và dual control.
10. **Backup and recovery:** phạm vi backup, escrow, quorum, recovery test và retention.
11. **Compromise response:** phát hiện, cô lập, thay khóa, xử lý dữ liệu và điều tra.
12. **Audit and monitoring:** event, log integrity, alert, retention và evidence.
13. **Third-party management:** shared responsibility, assurance và exit plan.
14. **Exceptions:** phê duyệt, biện pháp bù trừ, thời hạn và chấp nhận rủi ro.
15. **Compliance and review:** metrics, kiểm toán, owner và lịch cập nhật.

## 20. Checklist đánh giá Key management policy theo NIST

- Chính sách có owner, phạm vi, phiên bản và phê duyệt rõ ràng.
- Có xác định tài liệu NIST/tiêu chuẩn nào áp dụng và giới hạn áp dụng.
- Có inventory khóa với owner, purpose, classification, algorithm và version.
- Vai trò key owner, custodian, approver và auditor được phân tách phù hợp.
- Có quy tắc generation, distribution, storage và cryptographic module.
- Thuật toán, key size và tham số được rà soát theo hướng dẫn hiện hành.
- Quyền encrypt/decrypt/sign/wrap/export/disable/destroy được tách biệt.
- Có cryptoperiod, rotation, retire và rollback/forward recovery.
- Backup, escrow, recovery và destruction được kiểm soát và diễn tập.
- Có quy trình compromise response và revocation.
- Audit ghi thao tác khóa, bảo vệ tính toàn vẹn và không chứa key material.
- KMS/HSM và nhà cung cấp có trách nhiệm, bằng chứng assurance và exit plan.
- Ngoại lệ có người chấp nhận rủi ro, biện pháp bù trừ và ngày hết hạn.
- Policy được thực thi qua cấu hình, automation và kiểm thử định kỳ.
- Metrics, review cycle và evidence chứng minh tuân thủ được xác định.

Key management policy theo NIST là nền tảng quản trị để biến hướng dẫn mật mã thành trách nhiệm, quy tắc và bằng chứng có thể kiểm tra. SP 800-57 giúp định hướng cách bảo vệ khóa trong vòng đời; SP 800-130 và SP 800-152 hỗ trợ thiết kế CKMS theo phạm vi phù hợp; SP 800-53 giúp ánh xạ kiểm soát; SP 800-131A hỗ trợ chuyển đổi thuật toán. Chính sách chỉ thực sự có hiệu lực khi được chuyển thành standard, procedure, IAM/KMS/HSM policy, automation, audit và kiểm thử có owner chịu trách nhiệm.

## Tài liệu tham khảo

- [NIST SP 800-57 Part 1 Rev. 5: Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [NIST SP 800-130: A Framework for Designing Cryptographic Key Management Systems](https://csrc.nist.gov/pubs/sp/800/130/final)
- [NIST SP 800-152: A Profile for U.S. Federal Cryptographic Key Management Systems](https://csrc.nist.gov/pubs/sp/800/152/final)
- [NIST SP 800-53 Rev. 5: Security and Privacy Controls for Information Systems and Organizations](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
- [NIST SP 800-131A Rev. 2: Transitioning the Use of Cryptographic Algorithms and Key Lengths](https://csrc.nist.gov/pubs/sp/800/131/a/r2/final)
- [FIPS 140-3: Security Requirements for Cryptographic Modules](https://csrc.nist.gov/pubs/fips/140-3/final)

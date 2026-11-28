# Checklist production key readiness

Trong bài thực hành này, bạn sẽ đánh giá một hệ thống quản lý khóa mật mã trước khi đưa vào production. Bạn sẽ kiểm tra kiến trúc, loại khóa, nơi tạo và lưu key material, quyền sử dụng, quy trình rotation, backup/restore, audit, monitoring, xử lý sự cố và khả năng vận hành. Kết quả là một bộ hồ sơ readiness có bằng chứng, các vấn đề cần khắc phục và quyết định Go/No-Go rõ ràng.

Một hệ thống có thể mã hóa dữ liệu đúng trong môi trường development nhưng vẫn chưa sẵn sàng production. Ví dụ: key được lưu trong file cấu hình, quyền decrypt cấp cho toàn bộ service account, backup không giữ được key version cũ, hoặc không ai biết phải làm gì khi private key bị lộ. Checklist này giúp biến các yêu cầu quản lý khóa thành những câu hỏi có thể xác minh trước khi phát hành.

## 1. Kết quả cần đạt

Sau bài thực hành, bạn có thể:

- Xác định phạm vi và mục đích của từng khóa trong một hệ thống production.
- Kiểm tra kiến trúc KMS/HSM, envelope encryption và trust boundary.
- Đánh giá cách tạo, lưu trữ, sử dụng và phân quyền key material.
- Kiểm tra nonce/IV, thuật toán, metadata và tính toàn vẹn của dữ liệu mã hóa.
- Đánh giá rotation, revocation, backup, restore và destruction.
- Xác minh audit log, monitoring, alert và incident runbook.
- Thu thập bằng chứng và phân loại finding theo mức độ rủi ro.
- Đưa ra quyết định Go, Conditional Go hoặc No-Go có căn cứ.

## 2. Bối cảnh bài tập

Bạn là thành viên nhóm platform security chuẩn bị đưa dịch vụ Customer Records lên production. Dịch vụ lưu hồ sơ khách hàng và thông tin giao dịch trong database và object storage. Hệ thống dùng envelope encryption:

- Ứng dụng mã hóa dữ liệu bằng Data Encryption Key (DEK).
- Key Encryption Key (KEK) được quản lý trong KMS.
- Một số workload chạy trên Kubernetes ở nhiều replica.
- Workload identity được dùng để xác thực khi gọi KMS.
- Audit event từ KMS được gửi về kho log tập trung.
- Backup database và object storage được lưu theo retention policy.
- Đội vận hành cần có khả năng rotation và khôi phục dữ liệu khi xảy ra sự cố.

Trước khi go-live, nhóm cần chứng minh hệ thống có thể bảo vệ khóa trong điều kiện bình thường và khi có lỗi. Bạn sẽ sử dụng checklist để đánh giá thiết kế và bằng chứng của nhóm phát triển.

## 3. Phạm vi và nguyên tắc đánh giá

Checklist áp dụng cho khóa mã hóa dữ liệu, khóa bọc khóa, khóa ký, HMAC key, private key TLS và credential có quyền sử dụng KMS/HSM. Không phải hệ thống nào cũng dùng tất cả loại khóa; mục không áp dụng cần ghi rõ lý do.

Nguyên tắc đánh giá:

1. Đánh giá theo threat model và mức độ nhạy cảm của dữ liệu.
2. Kiểm tra hành vi thực tế và bằng chứng, không chỉ dựa vào câu trả lời “đã cấu hình”.
3. Mỗi khóa production phải có owner, purpose, phạm vi và vòng đời.
4. Quyền sử dụng khóa phải tối thiểu và gắn với danh tính có thể truy vết.
5. Khả năng khôi phục dữ liệu được xem là yêu cầu bảo mật và vận hành.
6. Một finding nghiêm trọng không thể được bù bằng nhiều mục checklist ít rủi ro đã đạt.
7. Không thu thập hoặc đưa key material thật vào readiness report.

## 4. Cách sử dụng checklist

Với mỗi mục, ghi một trong các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| PASS | Đã kiểm tra và có bằng chứng đáp ứng yêu cầu |
| FAIL | Có bằng chứng cho thấy yêu cầu chưa đạt |
| PARTIAL | Có một phần kiểm soát nhưng còn khoảng trống cụ thể |
| N/A | Không áp dụng; phải ghi lý do và người xác nhận |
| NOT TESTED | Chưa có bằng chứng hoặc chưa thực hiện kiểm tra |

Mỗi mục cần lưu:

- ID của checklist.
- Trạng thái.
- Link hoặc ID bằng chứng.
- Người kiểm tra và thời điểm.
- Finding hoặc rủi ro còn lại.
- Owner khắc phục và hạn hoàn thành nếu chưa đạt.

Không đánh dấu PASS chỉ vì tài liệu thiết kế có mô tả kiểm soát. Với kiểm soát quan trọng, cần bằng chứng cấu hình, audit event, test result hoặc diễn tập vận hành.

## 5. Gate 1: Inventory và ownership

Trước khi đánh giá kỹ thuật, xác định hệ thống thực sự có những khóa nào và ai chịu trách nhiệm.

- [ ] Mỗi key resource có key ID ổn định và owner chịu trách nhiệm.
- [ ] Mỗi khóa có purpose rõ ràng: encryption, key wrapping, signing, HMAC hoặc TLS.
- [ ] Có phân loại dữ liệu và hệ thống phụ thuộc vào khóa.
- [ ] Có environment, project/account, region và security boundary.
- [ ] Có thuật toán, kích thước khóa, trạng thái và key version.
- [ ] Có consumer/workload được phép sử dụng từng khóa.
- [ ] Có phân biệt key administrator, key operator, application consumer và auditor.
- [ ] Có inventory cho encrypted DEK, certificate, secret và key reference liên quan khi cần.
- [ ] Có danh sách backup, replica, archive hoặc export phụ thuộc vào version khóa.
- [ ] Có owner và quy trình xử lý cho khóa không còn consumer hoặc không rõ nguồn gốc.

**Bằng chứng cần xem:** key inventory, CMDB/service catalog, KMS resource list, certificate inventory, data flow diagram và danh sách owner.

**Điều kiện block:** có khóa production không xác định được owner hoặc purpose; không thể xác định dữ liệu nào phụ thuộc vào khóa; hoặc có key resource ngoài inventory mà chưa được giải thích.

## 6. Gate 2: Kiến trúc và trust boundary

Đánh giá nơi khóa được tạo, lưu và sử dụng; ranh giới tin cậy giữa ứng dụng, KMS/HSM, database và người vận hành.

- [ ] Có sơ đồ luồng dữ liệu và luồng key operation.
- [ ] Có xác định rõ dữ liệu plaintext tồn tại ở đâu và trong bao lâu.
- [ ] Key material được tách khỏi ciphertext và kho dữ liệu nghiệp vụ.
- [ ] KMS/HSM hoặc key provider được chọn phù hợp với mức nhạy cảm.
- [ ] Workload không được phép truy cập trực tiếp vào key store của workload khác.
- [ ] Có ranh giới giữa production và non-production.
- [ ] Có ranh giới giữa application workload và control plane quản trị khóa.
- [ ] Có phương án khi KMS/HSM unavailable hoặc network partition.
- [ ] Có xác định vùng địa lý, region failover và dependency của key service.
- [ ] Có đánh giá blast radius nếu một workload hoặc key administrator bị compromise.

**Bằng chứng cần xem:** architecture diagram, threat model, data flow, network policy, KMS/HSM deployment model và disaster recovery design.

## 7. Gate 3: Thuật toán và cách sử dụng mật mã

Kiểm tra primitive, thuật toán và mode phù hợp với mục tiêu bảo vệ.

- [ ] Encryption được dùng cho dữ liệu cần khôi phục; hashing được dùng cho mục tiêu một chiều.
- [ ] Password được lưu bằng password hashing chuyên dụng, không phải mã hóa có thể giải mã.
- [ ] Dữ liệu mới dùng thuật toán và mode được phê duyệt.
- [ ] AEAD như AES-GCM hoặc ChaCha20-Poly1305 được ưu tiên khi phù hợp.
- [ ] Không dùng ECB hoặc thuật toán lỗi thời cho thiết kế mới.
- [ ] Nếu có CBC/CTR legacy, ciphertext được xác thực bằng MAC theo thiết kế an toàn.
- [ ] Key size, curve và algorithm phù hợp policy hiện hành.
- [ ] Có allowlist thuật toán và format version khi đọc ciphertext.
- [ ] Có kiểm tra integrity/authentication tag trước khi sử dụng plaintext.
- [ ] Không có fallback âm thầm sang thuật toán yếu hơn khi provider lỗi.
- [ ] Thư viện mật mã được duy trì và có quy trình vá lỗ hổng.
- [ ] Không tự triển khai cipher, padding, KDF hoặc protocol mật mã.

**Bằng chứng cần xem:** crypto design, dependency inventory, cấu hình provider, code review và test result.

## 8. Gate 4: Key generation và chất lượng key material

- [ ] Key được tạo bằng CSPRNG hoặc chức năng tạo khóa của KMS/HSM.
- [ ] Không dùng timestamp, counter đơn giản, password hoặc Math.random làm khóa.
- [ ] Key được tạo đúng algorithm, size, curve và purpose.
- [ ] Key ID/version được ghi nhận ngay khi tạo.
- [ ] Exportability được tắt khi không có nhu cầu hợp lệ.
- [ ] Key pair được tạo trong HSM khi yêu cầu bảo vệ private key ở mức cao.
- [ ] Có kiểm soát khi import key material từ bên ngoài.
- [ ] Import procedure xác minh nguồn, định dạng, algorithm và quyền phê duyệt.
- [ ] Không có key mặc định, hard-coded key hoặc test key được dùng ở production.
- [ ] Việc tạo khóa có audit event và actor/workload identity.

**Bằng chứng cần xem:** KMS/HSM key metadata, generation policy, import ceremony record và audit event. Không yêu cầu người đánh giá xuất key material để kiểm tra.

## 9. Gate 5: Key storage và protection

- [ ] Key material được lưu trong KMS/HSM hoặc key store đã được phê duyệt.
- [ ] Private key và secret không nằm trong source code, Git history, container image hoặc artifact.
- [ ] Không lưu key cạnh ciphertext trong cùng miền truy cập không được bảo vệ.
- [ ] Secret manager hoặc keystore có access control và audit.
- [ ] File-based key store có permission, owner và host protection phù hợp.
- [ ] Không đưa key vào log, trace, exception, crash dump hoặc support bundle.
- [ ] Plaintext DEK chỉ tồn tại trong bộ nhớ cần thiết.
- [ ] Cache key có TTL, giới hạn scope và cơ chế invalidation phù hợp.
- [ ] Có kiểm soát memory dump, debug endpoint và quyền truy cập process.
- [ ] Backup của key material hoặc HSM state được bảo vệ theo quy trình riêng.

**Bằng chứng cần xem:** KMS/HSM configuration, secret manager policy, file permission, deployment manifest, container scan và log review.

## 10. Gate 6: Envelope encryption và metadata

Nếu hệ thống dùng envelope encryption, cần kiểm tra toàn bộ quan hệ giữa DEK, KEK và ciphertext.

- [ ] DEK được sinh ngẫu nhiên hoặc bởi KMS theo API được phê duyệt.
- [ ] KEK chỉ dùng để bảo vệ DEK theo purpose được cấu hình.
- [ ] Encrypted DEK được lưu cùng metadata cần thiết nhưng plaintext DEK không được lưu.
- [ ] Record lưu key ID và key version chính xác.
- [ ] Ciphertext lưu nonce/IV, tag và algorithm/format metadata cần thiết.
- [ ] AAD hoặc encryption context được chuẩn hóa và có schema/version.
- [ ] AAD ràng buộc ciphertext với tenant, record hoặc data domain phù hợp.
- [ ] AAD không chứa secret hoặc dữ liệu cá nhân không cần thiết.
- [ ] Decrypt/unwrap được thực hiện sau authorization ở tầng ứng dụng.
- [ ] Không thử mọi key trong key ring để tìm khóa có thể giải mã.
- [ ] Có chính sách cache và thời gian tồn tại của plaintext DEK.
- [ ] Có cách xác định các object còn phụ thuộc KEK version cũ.

**Bằng chứng cần xem:** envelope format, data model, sample metadata đã loại bỏ secret, KMS usage policy và test AAD/integrity.

## 11. Gate 7: IAM và quyền sử dụng khóa

Đây là gate quan trọng vì một khóa không exportable vẫn có thể bị lạm dụng qua API Decrypt, Sign hoặc Unwrap.

- [ ] Mỗi workload dùng danh tính riêng, không chia sẻ credential giữa service không liên quan.
- [ ] Ưu tiên workload identity hoặc credential ngắn hạn.
- [ ] Chỉ cấp operation cần thiết cho từng principal.
- [ ] Scope permission được giới hạn theo key, project, tenant và environment.
- [ ] Application consumer không có quyền tạo, rotate, export hoặc destroy nếu không cần.
- [ ] Key administrator không mặc nhiên có quyền đọc dữ liệu nghiệp vụ.
- [ ] Auditor có thể đọc audit/metadata nhưng không được sử dụng khóa.
- [ ] Policy change, export, disable hoặc destroy có phê duyệt phù hợp.
- [ ] Có dual control hoặc separation of duties cho thao tác rủi ro cao khi yêu cầu.
- [ ] Có quy trình thu hồi role, session và credential khi workload ngừng hoạt động.
- [ ] Có negative authorization test cho principal không được phép.
- [ ] Quyền kế thừa từ group, project và organization được rà soát.

**Bằng chứng cần xem:** IAM policy, key policy, role binding, identity mapping, access review và test deny.

## 12. Gate 8: Rotation và version management

- [ ] Có rotation policy theo thời gian hoặc trigger rủi ro.
- [ ] Policy nêu rõ loại khóa nào cần rotation và có tạo key material mới hay không.
- [ ] Có current version và lịch sử version rõ ràng.
- [ ] Version mới được xác minh trước khi cutover.
- [ ] Encrypt/sign mới dùng version hiện hành sau cutover.
- [ ] Decrypt/verify dữ liệu cũ vẫn dùng được version cũ trong thời gian được phép.
- [ ] Có rewrap khi thay KEK và re-encrypt khi DEK cần thay.
- [ ] Rotation workflow có idempotency, retry, backoff và xử lý concurrency.
- [ ] Có theo dõi consumer chưa chuyển version.
- [ ] Rollback không đưa hệ thống về khóa đã bị compromise.
- [ ] Version cũ chỉ bị disable/retire/destroy sau khi kiểm tra dependency và retention.
- [ ] Có test rotation trên môi trường gần production.

**Bằng chứng cần xem:** rotation policy, workflow log, key version metadata, migration report và test result.

## 13. Gate 9: Backup và recovery

Khả năng khôi phục phải được chứng minh bằng diễn tập, không chỉ bằng việc backup job báo thành công.

- [ ] Backup dữ liệu giữ metadata key ID/version cần thiết.
- [ ] Backup key hoặc HSM state dùng cơ chế được thiết kế và bảo vệ phù hợp.
- [ ] Quyền restore được giới hạn và có phê duyệt.
- [ ] Backup không làm lộ key material vào kho file thông thường.
- [ ] Retention của key version tương thích với retention của backup/archive.
- [ ] Có runbook restore dữ liệu mã hóa.
- [ ] Đã thử restore vào môi trường cô lập.
- [ ] Dữ liệu restore giải mã và vượt qua integrity check.
- [ ] Có xác minh RTO/RPO liên quan đến KMS/HSM và key availability.
- [ ] Có phương án region/provider outage nếu kiến trúc yêu cầu.
- [ ] Không destroy key version còn cần để restore dữ liệu.

**Bằng chứng cần xem:** backup policy, restore exercise report, key retention policy, recovery runbook và kết quả checksum.

## 14. Gate 10: Revocation và key destruction

- [ ] Có tiêu chí disable, revoke, retire và destroy rõ ràng.
- [ ] Có quy trình khẩn cấp khi key material hoặc credential bị lộ.
- [ ] Có thể ngăn principal tiếp tục gọi thao tác mật mã trái phép.
- [ ] Certificate revocation được xử lý qua CRL/OCSP hoặc cơ chế phù hợp.
- [ ] Có inventory các consumer, ciphertext, encrypted DEK và backup phụ thuộc.
- [ ] Rewrap/re-encrypt hoàn tất hoặc có ngoại lệ được phê duyệt trước khi destroy.
- [ ] Có retention/legal hold review.
- [ ] Destroy cần approval và audit theo policy.
- [ ] Có xác minh trạng thái sau destruction.
- [ ] Không còn bản sao key material không được kiểm soát trong backup, host hoặc artifact.

**Bằng chứng cần xem:** destruction policy, revocation workflow, approval record, dependency report và audit event.

## 15. Gate 11: Audit và monitoring

- [ ] KMS/HSM audit log được bật cho các thao tác quan trọng.
- [ ] Event có principal, key ID/version, operation, timestamp và outcome theo khả năng nguồn.
- [ ] Log được gửi đến vùng lưu trữ có kiểm soát truy cập riêng.
- [ ] Quyền đọc, ghi, xóa và thay retention được tách biệt.
- [ ] Có bảo vệ tính toàn vẹn và retention phù hợp.
- [ ] Không ghi key material, plaintext, token hoặc secret vào event.
- [ ] Có dashboard cho key usage, version, error và quota.
- [ ] Có cảnh báo Decrypt/Sign/Unwrap bất thường.
- [ ] Có cảnh báo principal lạ, policy change và thao tác export.
- [ ] Có cảnh báo key sắp hết hạn hoặc rotation workflow bị treo.
- [ ] Có cảnh báo audit pipeline mất event, ingestion lag hoặc heartbeat.
- [ ] Alert có owner, severity, evidence và runbook.

**Bằng chứng cần xem:** audit configuration, sample event đã làm sạch, dashboard, alert rule và alert delivery test.

## 16. Gate 12: Incident response và vận hành

- [ ] Có runbook key compromise và danh sách người liên hệ.
- [ ] Runbook phân biệt key material exposure, unauthorized key usage và credential compromise.
- [ ] Có thể xác định blast radius theo key ID, version, principal và resource.
- [ ] Có quy trình containment để revoke credential, giới hạn quyền hoặc disable key.
- [ ] Có phương án tạo khóa mới và cập nhật consumer.
- [ ] Có hướng dẫn rewrap/re-encrypt và xác minh dữ liệu.
- [ ] Có quy trình khôi phục dịch vụ và kiểm tra backup.
- [ ] Có quy trình giữ hoặc hủy khóa cũ sau sự cố.
- [ ] Đã diễn tập ít nhất một tình huống có liên quan đến hệ thống.
- [ ] Có post-incident review và action tracking.

**Bằng chứng cần xem:** runbook, on-call schedule, tabletop exercise, incident record mẫu và action item.

## 17. Gate 13: Application và deployment readiness

- [ ] Ứng dụng lấy key qua provider/API được phê duyệt, không dùng key hard-code.
- [ ] Key ID/version được lưu cùng ciphertext hoặc metadata tương ứng.
- [ ] Ứng dụng xác minh authorization trước decrypt/unwrap.
- [ ] Ứng dụng xử lý authentication tag failure và provider error an toàn.
- [ ] Không có fallback sang thuật toán yếu hoặc key mặc định.
- [ ] Không log plaintext hoặc key material.
- [ ] Secret/certificate được mount hoặc phân phối đúng workload.
- [ ] Deployment không đóng gói private key vào image.
- [ ] Rolling deployment kiểm tra mọi replica và region.
- [ ] Có health check cho KMS/HSM dependency.
- [ ] Có rate limit, retry và timeout phù hợp.
- [ ] Có cơ chế xử lý khi KMS unavailable mà không mở rộng quyền hoặc bỏ qua mã hóa.

**Bằng chứng cần xem:** application configuration, deployment manifest, code review, integration test và runtime log.

## 18. Gate 14: Kiểm thử bảo mật và vận hành

Các test tối thiểu cần có:

- [ ] Encrypt/decrypt round-trip cho dữ liệu hợp lệ.
- [ ] Ciphertext/tag/AAD bị sửa phải bị từ chối.
- [ ] Nonce/IV tuân thủ chiến lược uniqueness.
- [ ] Principal không có quyền bị deny.
- [ ] Workload tenant A không truy cập key/data tenant B.
- [ ] Rotation giữ được khả năng đọc dữ liệu lịch sử.
- [ ] Dữ liệu ghi mới dùng key version mới sau cutover.
- [ ] Rewrap/re-encrypt có thể tiếp tục sau worker crash.
- [ ] Backup trước rotation restore thành công.
- [ ] KMS timeout/throttling không làm workflow sai trạng thái.
- [ ] Audit event được ghi và truy vấn được.
- [ ] Alert đến đúng owner khi có hành vi bất thường.
- [ ] Runbook được diễn tập và có bằng chứng kết quả.

Không dùng production key hoặc dữ liệu production để thử phá hủy, export hay cố tình làm lộ key. Dùng resource test độc lập và dữ liệu giả lập.

## 19. Gate 15: Documentation và change management

- [ ] Có kiến trúc và threat model được owner phê duyệt.
- [ ] Có key inventory và certificate inventory cập nhật.
- [ ] Có policy generation, access, rotation, backup, recovery và destruction.
- [ ] Có runbook vận hành và incident response.
- [ ] Có danh sách owner, approver và on-call.
- [ ] Có change record cho các thay đổi policy và key lifecycle.
- [ ] Có quy trình review định kỳ và xử lý exception.
- [ ] Có hướng dẫn onboarding/offboarding workload.
- [ ] Có quy trình cập nhật tài liệu khi key owner hoặc consumer thay đổi.
- [ ] Có retention cho audit evidence và readiness record.

## 20. Phân loại finding

Phân loại finding dựa trên tác động và khả năng khai thác:

| Mức | Ví dụ | Ảnh hưởng đến go-live |
|---|---|---|
| Critical | Production key material bị lộ; principal không xác định có quyền decrypt diện rộng; không thể bảo vệ hoặc khôi phục dữ liệu quan trọng | No-Go |
| High | Key storage không đạt policy; quyền quá rộng; không có rotation/recovery; audit quan trọng bị tắt | Thông thường No-Go cho đến khi khắc phục hoặc có quyết định ngoại lệ cấp cao có căn cứ |
| Medium | Thiếu alert phụ, inventory chưa đầy đủ ở phạm vi hạn chế, tài liệu chưa cập nhật nhưng kiểm soát thực tế có bằng chứng | Có thể Conditional Go với owner và deadline |
| Low | Thiếu mô tả, dashboard chưa tối ưu hoặc vấn đề không làm suy giảm kiểm soát cốt lõi | Có thể chấp nhận với action item |

Không cộng điểm PASS để bù cho một Critical hoặc High finding. Readiness là quyết định dựa trên các gate bắt buộc và rủi ro còn lại, không phải phép tính trung bình đơn giản.

## 21. Quy tắc Go / Conditional Go / No-Go

### Go

Chọn Go khi:

- Tất cả gate bắt buộc đạt.
- Không còn Critical hoặc High finding chưa được xử lý.
- Có bằng chứng cho key protection, access control, rotation, recovery và audit.
- Owner vận hành và incident response đã được chỉ định.
- Các exception còn lại có mức rủi ro chấp nhận được theo quy trình.

### Conditional Go

Chỉ cân nhắc khi:

- Không có Critical finding.
- Khoảng trống còn lại có phạm vi giới hạn và không làm mất kiểm soát cốt lõi.
- Có biện pháp giảm thiểu tạm thời đã triển khai.
- Có owner, deadline, tiêu chí hoàn thành và người có thẩm quyền chấp nhận rủi ro.
- Có điều kiện tự động dừng hoặc rollback nếu rủi ro tăng.

### No-Go

Chọn No-Go khi:

- Không biết khóa nào bảo vệ dữ liệu production hoặc ai chịu trách nhiệm.
- Key material/credential bị lộ hoặc có dấu hiệu đang bị lạm dụng.
- Principal không phù hợp có quyền decrypt/sign/export diện rộng.
- Không thể khôi phục dữ liệu do thiếu key version hoặc backup.
- Không có cách rotation/containment cho khóa trọng yếu.
- Audit bị tắt hoặc không đủ khả năng điều tra thao tác nhạy cảm.
- Có Critical/High finding chưa có kiểm soát bù đáng tin cậy.

## 22. Bài tập thực hành: đánh giá một hệ thống mẫu

Giả sử nhóm phát triển cung cấp thông tin:

- DEK được sinh bằng KMS GenerateDataKey.
- Encrypted DEK được lưu trong cùng record với ciphertext.
- KEK nằm trong KMS, nhưng mọi service trong project dùng chung một service account.
- Service account có quyền Encrypt và Decrypt trên toàn bộ key ring.
- Rotation KEK bật tự động, nhưng chưa có báo cáo rewrap dependency.
- Database backup chạy hàng ngày; chưa có bằng chứng restore sau rotation.
- KMS audit log bật nhưng chỉ nhóm cloud administrator có quyền đọc.
- Alert chỉ gửi khi API KMS lỗi, chưa có cảnh báo Decrypt spike.
- Runbook key compromise mới có hướng dẫn liên hệ security, chưa có bước containment cụ thể.

### Nhiệm vụ

1. Đánh giá từng phát biểu theo checklist và gán PASS, FAIL, PARTIAL, N/A hoặc NOT TESTED.
2. Ghi ít nhất sáu finding, mỗi finding có rủi ro, bằng chứng cần thu thập và hành động khắc phục.
3. Xác định finding nào là Critical/High và có thể block go-live.
4. Đề xuất quyền riêng cho writer, reader, migration worker và auditor.
5. Thiết kế test restore backup sau KEK rotation.
6. Đề xuất tối thiểu ba alert cho hoạt động sử dụng khóa bất thường.
7. Đưa ra quyết định Go, Conditional Go hoặc No-Go và giải thích.

### Gợi ý phân tích

| Phát hiện | Đánh giá ban đầu | Lý do |
|---|---|---|
| Một service account dùng chung | FAIL | Khó quy trách nhiệm và giới hạn quyền theo workload |
| Decrypt trên toàn key ring | FAIL | Quyền vượt quá nhu cầu của từng service |
| Không có rewrap dependency report | NOT TESTED | Chưa chứng minh dữ liệu và encrypted DEK đã chuyển version |
| Chưa thử restore sau rotation | NOT TESTED | Khả năng khôi phục chưa được chứng minh |
| Auditor chỉ có cloud admin đọc log | PARTIAL | Thiếu quyền audit độc lập, dễ phụ thuộc administrator |
| Không có Decrypt spike alert | FAIL | Khó phát hiện lạm dụng key usage sớm |
| Runbook chỉ ghi liên hệ security | FAIL | Thiếu containment, phạm vi, rotation và recovery |

Với thông tin hiện có, quyết định phù hợp là No-Go cho đến khi quyền dùng chung được tách, restore được diễn tập, dependency của version được xác định, audit có khả năng truy cập độc lập và incident runbook đủ bước. Nếu tổ chức chọn một phương án khác, cần có bằng chứng và phê duyệt rủi ro cụ thể.

## 23. Mẫu readiness record

Sử dụng mẫu dưới đây để ghi lại kết quả đánh giá. Các giá trị là ví dụ và cần thay bằng dữ liệu thực của dự án.

~~~yaml
production_key_readiness:
  service: customer-records
  environment: production
  assessment_date: 2026-11-28
  assessor: platform-security
  owner: customer-platform

  decision:
    status: NO_GO
    rationale: "Shared identity has broad decrypt access; restore and incident response are unverified."

  scope:
    keys:
      - key_id: customer-records-kek
        purpose: key-encryption
        owner: customer-platform
      - key_id: customer-records-dek
        purpose: data-encryption
        owner: customer-platform

  findings:
    - id: KEY-READY-001
      severity: high
      status: open
      description: "Multiple services share a principal with broad decrypt permission."
      owner: platform-iam
      due_date: 2026-12-05

    - id: KEY-READY-002
      severity: high
      status: open
      description: "Backup restore after KEK rotation has not been demonstrated."
      owner: customer-platform
      due_date: 2026-12-08

  evidence:
    architecture: "ARCH-REVIEW-021"
    access_review: "IAM-REVIEW-114"
    restore_test: "NOT-AVAILABLE"
    audit_sample: "KMS-AUDIT-SAMPLE-08"
~~~

Readiness record không chứa secret, private key, DEK plaintext hoặc credential. Chỉ lưu key reference, finding, owner và ID của bằng chứng.

## 24. Bằng chứng cần có trước khi ký duyệt

Một bộ hồ sơ tốt nên có:

| Nhóm | Bằng chứng tối thiểu |
|---|---|
| Architecture | Sơ đồ luồng dữ liệu, key flow, trust boundary và threat model |
| Inventory | Key ID/version, purpose, owner, consumer và dependency |
| Key protection | KMS/HSM configuration, exportability, storage policy |
| Access control | IAM/key policy, role mapping, access review và deny test |
| Crypto implementation | Algorithm/mode, nonce strategy, AAD, library version và test |
| Rotation | Rotation policy, version transition, migration/re-wrap report |
| Recovery | Backup policy, restore evidence, RTO/RPO và retention |
| Audit | Sample event, access policy, integrity/retention và query test |
| Monitoring | Dashboard, alert rule, delivery test và owner |
| Incident response | Runbook, tabletop result và escalation path |
| Operations | On-call, change record, exception approval và lifecycle owner |

Nếu bằng chứng chứa dữ liệu nhạy cảm, chỉ lưu reference đến kho evidence được kiểm soát. Không sao chép key material vào hồ sơ readiness.

## 25. Checklist tổng hợp trước Go-live

### Inventory và thiết kế

- [ ] Tất cả khóa production có owner, purpose và consumer.
- [ ] Trust boundary, data flow và blast radius được mô tả.
- [ ] KMS/HSM hoặc key provider được phê duyệt.

### Mật mã và bảo vệ khóa

- [ ] Algorithm/mode được phê duyệt; AEAD được dùng khi phù hợp.
- [ ] Nonce/IV và AAD được quản lý đúng.
- [ ] Key được sinh an toàn, tách khỏi dữ liệu và không hard-code.
- [ ] Plaintext DEK và private key được bảo vệ trong bộ nhớ và runtime.

### Quyền và vòng đời

- [ ] Workload identity riêng và least privilege.
- [ ] Có rotation, revocation, backup, restore và destruction policy.
- [ ] Dữ liệu cũ và backup vẫn truy cập được sau rotation.
- [ ] Có kiểm soát dual control cho thao tác nhạy cảm khi cần.

### Quan sát và ứng phó

- [ ] Audit event đầy đủ và được bảo vệ.
- [ ] Alert cho usage anomaly, policy change và pipeline gap.
- [ ] Runbook key compromise có thể thực hiện được.
- [ ] Có owner, on-call và escalation.

### Bằng chứng và quyết định

- [ ] Các gate bắt buộc có bằng chứng.
- [ ] Critical/High finding đã đóng hoặc có quyết định theo thẩm quyền.
- [ ] Exception có owner, deadline và biện pháp giảm thiểu.
- [ ] Go/Conditional Go/No-Go được ghi rõ cùng người phê duyệt.

## 26. Câu hỏi tự đánh giá

1. Vì sao inventory và ownership là điều kiện đầu tiên của production readiness?
2. Vì sao key không exportable vẫn có thể bị lạm dụng?
3. Khác biệt giữa rewrap DEK và re-encrypt dữ liệu là gì?
4. Vì sao backup thành công không chứng minh restore thành công?
5. Những quyền nào nên tách khỏi quyền decrypt của application workload?
6. Cần bằng chứng gì để xác nhận rotation đã hoàn tất?
7. Vì sao audit log cần có người đọc độc lập với key administrator?
8. Khi nào một finding khiến quyết định phải là No-Go?
9. Vì sao không nên dùng điểm trung bình để bù một finding Critical?
10. Readiness record cần lưu những thông tin nào và cần loại bỏ dữ liệu nào?

## 27. Gợi ý đáp án

1. Inventory xác định khóa nào tồn tại, ai chịu trách nhiệm và dữ liệu nào phụ thuộc. Thiếu các thông tin này thì không thể đánh giá phạm vi, rotation hoặc recovery.
2. Principal có thể gọi API Decrypt, Sign hoặc Unwrap mà không cần export key material.
3. Rewrap thay KEK bảo vệ encrypted DEK; re-encrypt thay DEK dùng mã hóa ciphertext dữ liệu.
4. Backup job chỉ chứng minh dữ liệu đã được ghi. Restore còn phụ thuộc key version, quyền, metadata, KMS/HSM availability và integrity.
5. Export, create, rotate, change policy, disable và destroy thường cần tách khỏi quyền encrypt/decrypt của workload.
6. Cần current version, consumer coverage, dữ liệu cũ đọc được, dữ liệu mới dùng version mới, audit event và trạng thái version cũ.
7. Tách quyền giúp giảm nguy cơ administrator có thể sửa hoặc che giấu bằng chứng về hoạt động khóa.
8. Khi key material bị lộ, quyền decrypt/sign quá rộng, không thể khôi phục dữ liệu hoặc thiếu containment cho khóa trọng yếu.
9. Một kiểm soát cốt lõi bị phá vỡ không thể được bù bởi nhiều mục ít quan trọng đã đạt.
10. Lưu trạng thái gate, finding, owner, thời gian, key reference và evidence ID; không lưu private key, secret, token hoặc plaintext.

## 28. Kết luận và đầu ra cần nộp

Checklist production key readiness giúp đánh giá một hệ thống quản lý khóa bằng các gate có thể kiểm chứng. Một quyết định Go-live đáng tin cậy phải dựa trên inventory đầy đủ, kiến trúc và trust boundary rõ ràng, thuật toán phù hợp, key generation/storage an toàn, quyền tối thiểu, rotation có kiểm soát, backup/restore đã thử, audit có thể điều tra và incident response có thể thực hiện. Mỗi finding cần có mức độ, bằng chứng, owner và hạn xử lý. Các vấn đề Critical hoặc High ở kiểm soát cốt lõi thường phải chặn go-live cho đến khi được khắc phục hoặc có quyết định ngoại lệ đúng thẩm quyền.

**Đầu ra của bài thực hành:**

1. Checklist đã điền trạng thái cho từng gate.
2. Danh sách finding có severity, evidence, owner và due date.
3. Bộ bằng chứng readiness được lưu trong kho có kiểm soát.
4. Kết quả test rotation và backup/restore.
5. Quyết định Go, Conditional Go hoặc No-Go cùng rationale và người phê duyệt.

# Test key rotation

Test key rotation là hoạt động kiểm thử toàn bộ quy trình thay thế khóa mật mã đang được sử dụng bằng khóa hoặc phiên bản khóa mới. Kiểm thử phải xác nhận khóa mới được tạo và kích hoạt đúng policy, ứng dụng chuyển sang dùng khóa mới cho thao tác phát sinh, dữ liệu cũ vẫn có thể được xử lý theo chính sách, quyền truy cập được giữ đúng phạm vi và hệ thống có thể phục hồi khi một bước rotation thất bại.

Trong quản lý khóa mật mã, rotation ảnh hưởng trực tiếp đến khả năng bảo mật và tính sẵn sàng. Một lần chuyển đổi sai có thể làm dữ liệu không thể giải mã, chữ ký không thể xác minh, dịch vụ mất kết nối hoặc khóa cũ tiếp tục được dùng ngoài dự kiến. Vì vậy, test key rotation cần bao phủ cả thuật toán mật mã, metadata, KMS/HSM, ứng dụng, backup, audit và quy trình vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích mục đích và các kiểu key rotation trong vòng đời khóa.
- Phân biệt rotation của DEK, KEK, khóa ký, khóa HMAC và khóa riêng TLS.
- Xác định các invariant bảo mật và tính toàn vẹn cần giữ trong suốt quá trình chuyển đổi.
- Thiết kế test case cho tạo khóa, chuyển phiên bản hiện hành, đọc dữ liệu cũ và ghi dữ liệu mới.
- Kiểm thử rewrap, re-encrypt, dual-read, cutover, rollback và xử lý lỗi.
- Kiểm tra quyền, audit event, backup/restore và hoạt động KMS/HSM.
- Xây dựng kiểm thử tự động có thể chạy lặp lại mà không làm lộ key material.

## 2. Key rotation là gì?

Key rotation là quá trình thay khóa đang được dùng bằng key material mới hoặc chuyển sang một phiên bản mới của cùng một key resource. Rotation làm giảm thời gian một khóa được sử dụng, giới hạn ảnh hưởng khi khóa bị lộ và hỗ trợ đáp ứng chính sách mật mã.

Một khóa logic có thể có nhiều version:

- Version cũ đã được dùng để mã hóa hoặc ký trong quá khứ.
- Version mới được chọn cho các thao tác tạo dữ liệu hoặc chữ ký mới.
- Version cũ có thể tiếp tục được giữ để giải mã dữ liệu lịch sử hoặc xác minh chữ ký cũ.
- Một version có thể bị disable, scheduled for destruction hoặc destroyed theo policy.

Rotation không nhất thiết đồng nghĩa với việc mã hóa lại mọi dữ liệu ngay lập tức. Với KEK trong envelope encryption, hệ thống có thể rewrap encrypted DEK bằng KEK version mới mà giữ nguyên ciphertext dữ liệu. Với DEK bị thay thế, dữ liệu đã mã hóa bằng DEK cũ thường cần được giải mã rồi mã hóa lại nếu mục tiêu là chuyển dữ liệu sang DEK mới.

Kiểm thử phải bắt đầu từ chính sách rotation: loại khóa nào được xoay, chu kỳ hoặc trigger nào áp dụng, version cũ được giữ bao lâu và consumer được phép sử dụng version nào cho từng thao tác.

## 3. Vì sao phải kiểm thử rotation?

Rotation là thay đổi có tác động xuyên suốt nhiều thành phần. Một unit test xác nhận hàm tạo khóa trả về kết quả không đủ chứng minh hệ thống đã chuyển đổi an toàn.

Kiểm thử giúp phát hiện:

1. Khóa mới được tạo sai thuật toán, độ dài, purpose hoặc protection level.
2. Metadata đánh dấu nhầm version hiện hành hoặc cập nhật không nguyên tử.
3. Ứng dụng tiếp tục mã hóa bằng version cũ sau cutover.
4. Dữ liệu lịch sử không thể giải mã vì version cũ bị xóa hoặc mất metadata.
5. Encrypted DEK không được rewrap hoặc ciphertext bị ghi đè sai.
6. Hai worker rotation chạy đồng thời tạo ra trạng thái không nhất quán.
7. Retry tạo nhiều version hoặc triển khai lặp không idempotent.
8. Rollback đưa hệ thống về khóa đã bị compromise hoặc không tương thích.
9. Backup không chứa đủ key reference để khôi phục dữ liệu.
10. Audit log thiếu sự kiện hoặc ghi nhầm principal, key ID và version.

Mục tiêu là chứng minh hệ thống chuyển đổi có kiểm soát, giữ được khả năng truy cập dữ liệu hợp lệ và ngăn việc sử dụng khóa ngoài policy.

## 4. Phân biệt các kiểu rotation cần kiểm thử

| Loại rotation | Điều được thay thế | Điều cần kiểm thử |
|---|---|---|
| DEK rotation | Khóa trực tiếp mã hóa dữ liệu | Ciphertext mới dùng DEK mới; dữ liệu cũ vẫn đọc được hoặc được re-encrypt |
| KEK rotation | Khóa bọc các DEK | Encrypted DEK được rewrap; ứng dụng mở được DEK bằng KEK version mới |
| Signing key rotation | Private key tạo chữ ký | Signer dùng key mới; verifier chấp nhận chữ ký hợp lệ từ key cũ trong thời gian chuyển tiếp |
| HMAC key rotation | Secret dùng tạo và xác minh MAC | Producer và verifier chuyển version đồng bộ; MAC sai bị từ chối |
| TLS key rotation | Key pair gắn với chứng thư | Endpoint trình certificate mới và private key tương ứng; client/server xác thực được |
| KMS automatic rotation | KMS tạo version mới theo policy | Lịch rotation, trạng thái version, API encryption/decryption và audit event |
| Manual rotation | Operator hoặc workflow yêu cầu version mới | Phê duyệt, quyền, cutover, theo dõi và xử lý lỗi |

Không dùng một bộ test duy nhất cho mọi loại khóa. Chẳng hạn, test dữ liệu cũ sau DEK rotation khác với test xác minh chữ ký được tạo bởi signing key version cũ.

## 5. Các invariant phải được giữ

Invariant là điều kiện phải luôn đúng trước, trong và sau rotation. Xác định invariant trước khi viết test giúp tập trung vào hành vi bảo mật thay vì chỉ kiểm tra workflow có chạy hết bước.

Các invariant phổ biến:

- **Không mất khả năng giải mã hợp lệ:** dữ liệu được tạo trước rotation vẫn đọc được trong thời gian retention yêu cầu.
- **Ghi mới bằng version hiện hành:** mọi thao tác mã hóa mới sau cutover dùng version được policy chỉ định.
- **Không hạ cấp âm thầm:** lỗi khi dùng version mới không được tự động khiến ứng dụng quay lại version cũ để ghi mới nếu policy không cho phép.
- **Không dùng sai mục đích:** key version chỉ được dùng cho purpose và thuật toán được cấu hình.
- **Không lộ key material:** test, log, report và fixture không chứa plaintext private key hoặc secret.
- **Không mở rộng quyền:** rotation không tự cấp thêm quyền cho principal không liên quan.
- **Không phá vỡ tính toàn vẹn:** dữ liệu, authentication tag, MAC và chữ ký được kiểm tra đúng.
- **Trạng thái có thể truy vết:** mỗi version và thao tác chuyển đổi có ID, timestamp, actor và kết quả.
- **Không hủy quá sớm:** version cũ chỉ bị destroy khi đã đáp ứng điều kiện retention, backup và phụ thuộc dữ liệu.
- **Tính nhất quán phân tán:** mọi consumer được cập nhật theo trạng thái đã xác minh, không dựa vào giả định rằng một node đại diện cho toàn hệ thống.

## 6. Xây dựng test strategy

Một chiến lược kiểm thử hoàn chỉnh nên chia thành nhiều lớp:

| Lớp kiểm thử | Phạm vi | Ví dụ |
|---|---|---|
| Unit test | Logic quản lý version, policy và metadata | Chọn đúng current version, từ chối version disabled |
| Component test | Adapter KMS/HSM, secret store và repository | Tạo version, lấy metadata, kiểm tra quyền |
| Integration test | Ứng dụng với KMS/HSM và database | Encrypt bằng version mới, decrypt dữ liệu cũ |
| Workflow test | Toàn bộ rotation pipeline | Create, validate, cutover, verify và retire |
| Failure injection | Lỗi mạng, timeout, quota, worker crash | Retry không tạo trạng thái sai |
| Security test | Authorization, isolation và audit | Principal không được phép không thể rotate hoặc decrypt |
| Recovery test | Backup, restore và rollback | Khôi phục dữ liệu cần key version cũ |
| Performance test | Latency, throughput và tải KMS | Rotation không làm quá tải KMS hoặc dịch vụ |

Unit test nên dùng interface hoặc fake KMS để kiểm tra logic nhanh. Integration test phải chạy với KMS/HSM test resource có policy và quyền gần với production. Không thay thế toàn bộ integration test bằng mock vì mock không kiểm tra được hành vi thực tế của provider, versioning hoặc authorization.

## 7. Chuẩn bị môi trường và dữ liệu kiểm thử

Trước khi chạy test:

1. Dùng project, account, key ring hoặc HSM partition dành riêng cho test.
2. Tạo key có purpose, thuật toán và policy tương tự production nhưng không chứa dữ liệu production.
3. Tạo bộ dữ liệu giả lập có thể xác minh tính toàn vẹn sau encrypt/decrypt.
4. Ghi nhận key ID, version ban đầu và trạng thái trước test.
5. Cấu hình quyền riêng cho test runner và operator.
6. Bật audit log và xác định nơi truy vấn event.
7. Chuẩn bị cách cleanup tài nguyên test theo retention của môi trường.

Không dùng key production chỉ để kiểm tra rotation. Không đưa private key, DEK plaintext hoặc secret thật vào fixture, snapshot, test report hay repository. Nếu cần dữ liệu giống production, tạo dữ liệu tổng hợp và khóa test độc lập.

Đồng hồ trong môi trường test cần được đồng bộ nếu test dựa trên thời điểm hiệu lực, expiry hoặc lịch rotation. Với test time-based, ưu tiên clock abstraction hoặc thời gian mô phỏng thay vì chờ đến ngày thực tế.

## 8. Kiểm thử tạo key version mới

Khi rotation bắt đầu, hệ thống cần tạo hoặc yêu cầu KMS tạo key material/version mới theo policy.

Các kiểm tra cần có:

- Version mới có ID khác version cũ.
- Key algorithm, size, curve, purpose và protection level đúng cấu hình.
- Key mới nằm trong đúng project, key ring, HSM partition hoặc security domain.
- Exportability và policy được đặt đúng.
- Key state ban đầu và trạng thái sau khi tạo phù hợp với workflow.
- Metadata liên kết version mới với logical key chính xác.
- Principal tạo version có quyền phù hợp và audit event được ghi nhận.

Không kiểm thử chất lượng ngẫu nhiên bằng cách yêu cầu hai khóa liên tiếp phải khác nhau trong một số lượng mẫu nhỏ rồi coi đó là chứng minh entropy. Việc đánh giá CSPRNG và entropy cần phương pháp chuyên biệt. Trong kiểm thử ứng dụng, xác nhận provider đã dùng cơ chế sinh khóa được phê duyệt và không có code tự tạo khóa từ timestamp hoặc dữ liệu dễ đoán.

## 9. Kiểm thử chuyển current version

Tạo version mới không đồng nghĩa ứng dụng đã dùng version đó. Hệ thống cần một bước cutover rõ ràng để xác định version nào dùng cho thao tác mới.

Test nên xác minh:

1. Trước cutover, thao tác mã hóa mới dùng version cũ.
2. Sau cutover thành công, thao tác mã hóa mới dùng version mới.
3. Metadata current version được cập nhật đúng key ID và version ID.
4. Consumer đọc được metadata mới sau khi cache được refresh theo policy.
5. Không có khoảng thời gian mà ứng dụng không tìm được version hợp lệ.
6. Nếu cutover thất bại, current version không bị cập nhật một phần.
7. Các node khác nhau hội tụ về cùng trạng thái sau thời gian đồng bộ cho phép.

Nếu hệ thống dùng alias hoặc key reference trỏ đến version hiện hành, cần test alias update và cache invalidation. Không giả định alias đổi là mọi process lập tức nhìn thấy thay đổi nếu ứng dụng có cache cục bộ.

## 10. Kiểm thử dữ liệu cũ và dữ liệu mới

Đây là nhóm test quan trọng nhất đối với khóa mã hóa.

Tạo dữ liệu trước rotation:

1. Sinh plaintext giả lập.
2. Mã hóa bằng version cũ.
3. Lưu ciphertext cùng key ID, version, nonce/IV và encryption context cần thiết.
4. Chạy rotation và chuyển current version.
5. Đọc lại dữ liệu cũ bằng cơ chế version-aware.
6. Xác minh plaintext thu được khớp dữ liệu ban đầu.

Tạo dữ liệu sau rotation:

1. Gửi request mã hóa mới sau cutover.
2. Xác nhận metadata của ciphertext trỏ đến version mới.
3. Giải mã dữ liệu mới bằng version mới.
4. Xác minh plaintext khớp và authentication tag hợp lệ.
5. Xác nhận không có fallback sang version cũ khi version mới gặp lỗi.

Ví dụ ma trận:

| Dữ liệu | Version tạo ciphertext | Kết quả mong đợi |
|---|---|---|
| Record A trước rotation | v1 | Đọc được bằng v1 theo policy |
| Record B sau rotation | v2 | Đọc được bằng v2 |
| Record A sau migration | v2 nếu đã re-encrypt | Đọc được bằng v2; metadata cập nhật nhất quán |
| Ciphertext bị sửa | v1 hoặc v2 | Decrypt thất bại do kiểm tra integrity |
| Ciphertext thiếu version metadata | Không xác định | Xử lý theo policy rõ ràng; không đoán version hoặc mở rộng quyền |

Nếu ứng dụng cần hỗ trợ nhiều version khi đọc, test phải xác nhận version được lấy từ metadata đáng tin cậy của ciphertext hoặc record. Không thử tuần tự mọi khóa trong key ring để “tìm khóa giải mã được”, vì cách này làm rộng quyền và che giấu lỗi metadata.

## 11. Kiểm thử DEK rotation

DEK trực tiếp mã hóa dữ liệu nên rotation có thể yêu cầu chuyển đổi ciphertext.

Hai cách triển khai thường gặp:

- **Lazy migration:** dữ liệu cũ tiếp tục dùng DEK version cũ khi đọc; dữ liệu mới dùng DEK mới. Dữ liệu cũ được re-encrypt khi có truy cập hoặc theo batch.
- **Bulk re-encryption:** worker đọc ciphertext cũ, giải mã bằng DEK cũ, mã hóa bằng DEK mới và cập nhật metadata.

Test lazy migration:

- Dữ liệu cũ đọc được sau cutover.
- Lần ghi mới dùng DEK mới.
- Khi một record cũ được cập nhật, hệ thống có chuyển nó sang DEK mới theo policy hay không.
- Metadata không bị thay đổi trước khi ciphertext mới được lưu thành công.

Test bulk re-encryption:

- Tất cả record trong tập mục tiêu được xử lý hoặc có trạng thái lỗi rõ ràng.
- Retry không làm hỏng record đã chuyển đổi.
- Concurrent write không bị ghi đè bởi dữ liệu cũ hơn.
- Checkpoint cho phép tiếp tục sau worker crash.
- Record lỗi được cách ly và có thể xử lý lại.
- Hash/checksum hoặc authentication tag được xác minh sau chuyển đổi.

Không xóa DEK cũ trước khi mọi ciphertext, backup, replica và archive cần giữ đã được chuyển đổi hoặc có phương án giải mã được phê duyệt.

## 12. Kiểm thử KEK rotation và rewrap

KEK thường bảo vệ DEK bằng envelope encryption. Khi thay KEK, có thể rewrap DEK mà không phải mã hóa lại toàn bộ dữ liệu.

Test rewrap nên xác nhận:

1. Encrypted DEK ban đầu được mở bằng KEK version cũ theo quyền được cấp.
2. DEK plaintext chỉ tồn tại trong vùng xử lý được bảo vệ và không bị ghi log.
3. DEK được bọc bằng KEK version mới.
4. Encrypted DEK mới cùng key reference/version được ghi nguyên tử.
5. Ứng dụng lấy DEK mới và giải mã được ciphertext dữ liệu ban đầu.
6. Các record chưa rewrap vẫn đọc được bằng version cũ trong thời gian chuyển tiếp.
7. Khi hoàn tất, không còn object trong phạm vi migration tham chiếu KEK cũ ngoài ngoại lệ được phê duyệt.

Test trường hợp rewrap thất bại giữa chừng. Hệ thống phải giữ bản encrypted DEK cũ còn hợp lệ hoặc có transaction/backup để khôi phục. Không ghi đè encrypted DEK cũ bằng một giá trị mới chưa được xác minh.

Nếu KEK cũ bị compromise, rewrap chỉ phù hợp khi DEK được đánh giá vẫn an toàn. Nếu attacker có thể đã mở hoặc lấy DEK, cần xem xét tạo DEK mới và re-encrypt dữ liệu.

## 13. Kiểm thử signing key rotation

Với khóa ký bất đối xứng, rotation cần phối hợp signer và verifier.

Test cần bao gồm:

- Signer sử dụng private key version mới sau cutover.
- Chữ ký mới xác minh được bằng public key version mới.
- Chữ ký được tạo trước rotation vẫn xác minh được trong khoảng tương thích được policy cho phép.
- Verifier từ chối chữ ký sai, chữ ký bị sửa hoặc chữ ký từ key ID không được tin cậy.
- Key ID trong token, signature envelope hoặc metadata trỏ đúng public key.
- JWKS hoặc key registry cập nhật public key mới và có chiến lược cache refresh.
- Sau thời điểm retire, verifier không còn tin cậy key cũ cho chữ ký mới hoặc token mới theo policy.

Nếu hệ thống phát hành JWT, test kid và JWKS rotation. Một verifier có thể cache JWKS; cần kiểm tra thời gian cache, hành vi khi gặp kid mới và cách xử lý khi endpoint JWKS tạm thời không khả dụng.

Không xóa public key cũ ngay nếu vẫn cần xác minh token hoặc artifact hợp lệ được phát hành trước rotation. Thời gian giữ phụ thuộc thời hạn token, retention và chính sách xác minh.

## 14. Kiểm thử HMAC rotation

HMAC sử dụng cùng một secret ở phía tạo và xác minh MAC. Vì vậy, hai phía phải có chiến lược chuyển đổi đồng bộ.

Một mô hình phổ biến dùng key ID:

1. Producer bắt đầu ký thông điệp mới bằng key version mới.
2. Consumer nhận key ID và chọn secret tương ứng từ kho được bảo vệ.
3. Trong thời gian chuyển tiếp, consumer có thể xác minh MAC bằng version cũ và mới theo policy.
4. Sau khi mọi producer đã chuyển đổi và thời hạn thông điệp cũ kết thúc, retire key cũ.

Test:

- MAC mới hợp lệ với key mới.
- MAC cũ chỉ được chấp nhận trong khoảng chuyển tiếp được quy định.
- MAC sai hoặc key ID không tồn tại bị từ chối.
- Consumer không thử mọi secret nếu key ID không hợp lệ.
- Producer không phát hành message mới với key ID cũ sau cutover.
- Cache secret được cập nhật và không giữ version đã bị thu hồi ngoài giới hạn.

Không gửi HMAC secret qua message. Message chỉ nên mang key ID hoặc phiên bản công khai; secret được lấy từ kho quản lý an toàn.

## 15. Kiểm thử quyền và phân tách nhiệm vụ

Rotation thường yêu cầu các quyền khác nhau: tạo version, cập nhật alias, đọc metadata, sử dụng khóa, rewrap và disable version cũ. Test phải xác nhận đúng principal được thực hiện từng bước.

| Principal | Hành động được phép | Hành động phải bị từ chối |
|---|---|---|
| Rotation service | Tạo version mới và cập nhật current version trong scope được giao | Export key material hoặc thay policy toàn tổ chức |
| Application workload | Encrypt bằng current version; decrypt version được phép | Tạo key, rotate hoặc destroy key |
| Migration worker | Decrypt dữ liệu nguồn và encrypt/rewrap đích trong phạm vi migration | Đọc khóa ngoài project hoặc tenant |
| Auditor | Đọc metadata, version và audit event | Decrypt, sign, export hoặc sửa policy |
| Key administrator | Quản trị cấu hình theo phê duyệt | Tự ý bỏ qua dual control nếu policy yêu cầu |

Kiểm thử cả positive và negative authorization. Một rotation thành công không đủ nếu workload ứng dụng vô tình nhận thêm quyền quản trị.

Nếu policy yêu cầu dual control, test phải xác minh một người không thể tự khởi tạo và tự phê duyệt thao tác nhạy cảm. Kiểm tra cả quyền kế thừa từ project, group và service account.

## 16. Kiểm thử concurrency và phân tán

Nhiều node hoặc worker có thể cùng phát hiện đến hạn rotation. Nếu không có điều phối, chúng có thể tạo nhiều version, ghi đè current version hoặc thực hiện migration song song trên cùng dữ liệu.

Các tình huống cần thử:

- Hai rotation request cùng logical key đến gần như đồng thời.
- Worker restart sau khi tạo version nhưng trước khi cập nhật metadata.
- Worker mất kết nối sau khi KMS đã hoàn tất request nhưng trước khi nhận response.
- Alias update thành công ở control plane nhưng một số node còn cache version cũ.
- Migration worker và ứng dụng cùng cập nhật một record.
- Event đến muộn hoặc retry khiến trạng thái workflow bị xử lý lại.

Kết quả mong đợi:

- Chỉ một rotation workflow được coi là chủ sở hữu tại một thời điểm hoặc các workflow được điều phối an toàn.
- Request lặp không tạo version ngoài dự kiến.
- Metadata không trỏ đến version chưa được xác minh.
- Record không bị mất update do race condition.
- Các node hội tụ về current version trong giới hạn thời gian đã thiết kế.
- Audit trail phân biệt được attempt, retry và kết quả cuối.

## 17. Kiểm thử idempotency và retry

Một thao tác có thể thành công tại KMS nhưng client timeout trước khi nhận response. Nếu retry tạo version mới lần nữa, hệ thống có thể phát sinh nhiều version không cần thiết.

Test nên mô phỏng:

- Timeout trước khi request đến KMS.
- Timeout sau khi KMS xử lý nhưng trước khi client nhận response.
- Lỗi tạm thời khi cập nhật metadata.
- Lỗi ghi encrypted DEK mới.
- Worker bị dừng sau mỗi bước của workflow.
- Retry sau khi trạng thái đã chuyển sang completed.

Hệ thống cần dùng operation ID, idempotency token hoặc cơ chế tra cứu trạng thái provider nếu được hỗ trợ. Trước khi lặp lại mutation, kiểm tra trạng thái thực tế và tiếp tục workflow từ checkpoint.

Retry cần có backoff, jitter, giới hạn số lần và phân loại lỗi. Không retry vô hạn với lỗi authorization, policy hoặc cấu hình.

## 18. Kiểm thử rollback và phục hồi

Rollback trong rotation không phải lúc nào cũng có nghĩa quay lại dùng khóa cũ cho mọi thao tác. Nếu rotation được thực hiện do nghi ngờ compromise, không được khôi phục việc sử dụng khóa đã bị xác nhận lộ.

Test rollback nên chia theo tình huống:

- Cutover chưa xảy ra: giữ current version cũ, bỏ version mới chưa kích hoạt theo policy.
- Version mới đã active nhưng deploy ứng dụng lỗi: khôi phục cấu hình ứng dụng tương thích mà vẫn tuân thủ trạng thái an toàn của khóa.
- Re-encryption dở dang: tiếp tục từ checkpoint hoặc khôi phục record từ bản sao hợp lệ.
- Rewrap dở dang: record chưa chuyển đổi vẫn đọc được bằng encrypted DEK cũ trong thời gian cho phép.
- Backup restore: metadata và key version cần thiết vẫn tồn tại, có thể giải mã dữ liệu khôi phục.

Không destroy version cũ trong cùng bước cutover. Việc retire và destroy cần có điều kiện riêng, bằng chứng migration hoàn tất và phê duyệt theo policy.

## 19. Kiểm thử backup và restore sau rotation

Backup có thể chứa ciphertext được mã hóa bằng version cũ, metadata key reference và encrypted DEK. Nếu chỉ backup dữ liệu mà không giữ khả năng truy cập version khóa cần thiết, restore có thể thất bại.

Test restore:

1. Tạo dữ liệu test và backup trước rotation.
2. Thực hiện rotation theo quy trình.
3. Khôi phục backup vào môi trường test cô lập.
4. Xác minh metadata chỉ ra đúng key ID/version.
5. Kiểm tra KMS/HSM còn giữ version cần thiết và policy cho phép restore workload sử dụng.
6. Giải mã dữ liệu và xác minh checksum hoặc nội dung.
7. Kiểm tra audit event ghi nhận thao tác restore/decrypt.

Thử cả backup cũ và backup được tạo sau rotation. Xác định rõ thời hạn cần giữ version cũ dựa trên retention của backup, archive và yêu cầu phục hồi.

## 20. Kiểm thử trạng thái version và vòng đời

KMS có thể quản lý trạng thái version như enabled, disabled, primary, pending destruction hoặc destroyed. Tên trạng thái và khả năng thao tác khác nhau giữa provider.

Test cần xác minh:

- Version mới được tạo ở trạng thái mong đợi.
- Chỉ một version được đánh dấu primary/current nếu mô hình yêu cầu.
- Version cũ không còn được dùng để mã hóa mới sau cutover.
- Version cũ vẫn được dùng để decrypt hoặc verify nếu policy cho phép.
- Version disabled bị từ chối đúng với các thao tác bị cấm.
- Scheduled destruction không xảy ra trước retention hoặc approval.
- Version destroyed không thể được khôi phục hoặc sử dụng như thể còn tồn tại.

Không giả định mọi provider cho phép cùng một tập thao tác trên version disabled. Test phải theo hợp đồng API và policy thực tế của KMS/HSM.

## 21. Kiểm thử audit và monitoring

Rotation cần tạo được audit trail có thể truy vết:

- Ai hoặc workload nào khởi tạo rotation?
- Key ID và version cũ/mới là gì?
- Ai phê duyệt và policy nào được áp dụng?
- Khi nào version mới được tạo, validate, đặt current và dùng lần đầu?
- Có bao nhiêu consumer đã chuyển đổi?
- Khi nào version cũ bị disable, retire hoặc schedule destruction?
- Có lỗi, retry hoặc rollback nào xảy ra?

Test nên xác minh event có principal, operation, key ID/version, timestamp, request ID và outcome theo khả năng nguồn. Không ghi plaintext key material, DEK, private key hoặc secret vào log.

Monitoring cần cảnh báo:

- Rotation đến hạn nhưng workflow chưa bắt đầu.
- Rotation thất bại hoặc bị treo ở trạng thái pending.
- Version cũ tiếp tục được dùng để encrypt/sign sau cutover.
- Version mới không có hoạt động dự kiến sau triển khai.
- Một consumer chưa cập nhật.
- Audit event bị thiếu hoặc ingestion lag vượt ngưỡng.
- Có thao tác disable, export hoặc destroy ngoài change record.

## 22. Kiểm thử KMS/HSM integration

KMS/HSM là thành phần thực thi policy và thao tác mật mã. Integration test cần xác minh hành vi provider thực tế:

- Key version được tạo trong đúng resource và security boundary.
- API trả đúng key ID/version và metadata.
- Quyền encrypt/decrypt/sign/verify được áp dụng theo policy.
- Key material không exportable nếu policy yêu cầu.
- Rotation API hoặc scheduler hoạt động theo lịch.
- HSM partition và quorum/dual control được áp dụng khi có.
- Provider error, quota, throttling và service outage được xử lý đúng.
- Audit event được phát ra và có thể truy vấn.

Mock có thể mô phỏng lỗi để kiểm tra retry logic, nhưng cần ít nhất một nhóm integration test với môi trường test của provider để xác nhận semantics của versioning, alias, disable và rotation.

Không dùng thao tác destroy trên khóa production làm test. Nếu cần kiểm tra destruction workflow, dùng resource test có dữ liệu giả lập và xác nhận trước khi thực hiện.

## 23. Kiểm thử hiệu năng và khả năng mở rộng

Rotation có thể tạo tải lớn lên KMS/HSM và hệ thống lưu trữ khi nhiều khóa đến hạn cùng lúc. Test cần đo:

- Thời gian tạo version mới.
- Latency encrypt/decrypt/sign trước và sau rotation.
- Throughput KMS/HSM khi chạy nhiều rotation song song.
- Số lần retry và tỷ lệ throttling.
- Thời gian cập nhật metadata và cache propagation.
- Thời gian rewrap hoặc re-encrypt toàn bộ tập dữ liệu.
- Ảnh hưởng đến request nghiệp vụ và p95/p99 latency.

Thử tải theo các kịch bản có kiểm soát: nhiều key cùng đến hạn, migration chạy song song với traffic bình thường và một vùng KMS chậm. Xác định concurrency limit, batch size, rate limit và lịch phân tán để không gây quá tải.

Không chạy load test bằng khóa hoặc dữ liệu production nếu chưa có kế hoạch được phê duyệt. Dùng tài nguyên test và giới hạn chi phí/quota.

## 24. Ví dụ kiểm thử tích hợp bằng Java

Ví dụ sau minh họa cách kiểm tra dữ liệu được mã hóa trước rotation vẫn đọc được và dữ liệu mới sử dụng version hiện hành. Interface là mô hình giả định; adapter thực tế cần triển khai theo KMS hoặc key service đang sử dụng.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class KeyRotationIntegrationTest {

    private final TestKeyService keys = TestKeyService.createIsolated();
    private final TestEncryptedRepository repository =
            new TestEncryptedRepository(keys);

    @Test
    void oldDataRemainsReadableAndNewWritesUseCurrentVersion() {
        byte[] oldPlaintext = "record-before-rotation".getBytes();
        EncryptedRecord oldRecord = repository.write(oldPlaintext);
        String oldVersion = oldRecord.keyVersion();

        String newVersion = keys.rotateAndActivate(oldRecord.keyId());

        assertNotEquals(oldVersion, newVersion);

        byte[] newPlaintext = "record-after-rotation".getBytes();
        EncryptedRecord newRecord = repository.write(newPlaintext);

        assertEquals(newVersion, newRecord.keyVersion());
        assertArrayEquals(oldPlaintext, repository.read(oldRecord));
        assertArrayEquals(newPlaintext, repository.read(newRecord));
    }
}
~~~

Test này cần chạy trong môi trường cô lập. TestKeyService và TestEncryptedRepository là abstraction minh họa, không phải API của một nhà cung cấp. Test thực tế nên bổ sung assertion về audit event, authorization, ciphertext integrity và cleanup tài nguyên.

## 25. Ví dụ test lỗi khi cutover

Một tình huống quan trọng là tạo version mới thành công nhưng cập nhật current version thất bại. Hệ thống không được để metadata ở trạng thái nửa cũ nửa mới.

~~~text
given:
  currentVersion = v4
  createVersion(v5) succeeds
  activateVersion(v5) returns temporary failure

when:
  rotation workflow retries

then:
  currentVersion remains v4 until activation succeeds
  no new writes reference an unvalidated version
  retry resumes or safely repeats using the same operation identity
  audit records the failed attempt and final result
~~~

Test thêm trường hợp activation đã thành công tại provider nhưng response bị timeout. Khi retry, workflow cần đọc trạng thái provider và nhận ra v5 đã active thay vì tạo v6 không cần thiết.

## 26. Test matrix tổng hợp

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| KR-001 | Tạo version mới hợp lệ | Version ID mới và metadata đúng |
| KR-002 | Sai algorithm hoặc purpose | Rotation bị từ chối trước cutover |
| KR-003 | Cutover thành công | Ghi mới dùng version mới |
| KR-004 | Đọc ciphertext cũ | Decrypt thành công theo policy |
| KR-005 | Đọc ciphertext mới | Decrypt thành công bằng version mới |
| KR-006 | Version cũ bị disable | Thao tác bị từ chối theo policy |
| KR-007 | Hai rotation request đồng thời | Không tạo trạng thái current version xung đột |
| KR-008 | Timeout sau khi provider xử lý | Retry không tạo rotation trùng |
| KR-009 | Rewrap DEK | DEK mở được bằng KEK mới và dữ liệu cũ vẫn đọc được |
| KR-010 | Re-encrypt DEK | Ciphertext mới dùng DEK mới và integrity hợp lệ |
| KR-011 | Signing key rotation | Chữ ký mới xác minh bằng public key mới |
| KR-012 | HMAC key rotation | Producer và verifier chuyển version đúng |
| KR-013 | Principal không có quyền | Rotation hoặc decrypt bị deny |
| KR-014 | Backup trước rotation | Restore và decrypt thành công |
| KR-015 | Worker crash giữa migration | Tiếp tục từ checkpoint, không mất dữ liệu |
| KR-016 | Version cũ còn consumer | Không destroy trước khi dependency được xử lý |
| KR-017 | Audit event | Ghi đúng actor, key ID, version và outcome |
| KR-018 | KMS throttling | Backoff và giới hạn concurrency hoạt động |
| KR-019 | Current version chưa propagate | Consumer hội tụ hoặc báo lỗi rõ ràng |
| KR-020 | Ciphertext bị sửa | Integrity verification thất bại |

Test matrix cần gắn với requirement và mức độ rủi ro. Không phải mọi hệ thống đều dùng tất cả loại khóa, nhưng các kịch bản liên quan phải có kết quả mong đợi và bằng chứng kiểm thử.

## 27. Tiêu chí hoàn tất rotation

Một workflow chỉ nên được đánh dấu hoàn tất khi các điều kiện áp dụng đều đạt:

- Version mới đã được tạo, xác minh và active.
- Consumer ghi mới đã dùng version mới.
- Dữ liệu cũ vẫn đọc được hoặc migration đã hoàn tất theo phạm vi.
- Không còn consumer ngoài dự kiến dùng version cũ cho thao tác mới.
- Backup/restore và dữ liệu lịch sử vẫn đáp ứng retention.
- Quyền của rotation service và application không bị mở rộng ngoài policy.
- Audit trail ghi đủ các bước và kết quả.
- Monitoring không còn cảnh báo migration hoặc version mismatch chưa xử lý.
- Version cũ được giữ, disable hoặc schedule destruction theo quyết định có phê duyệt.

Nếu một số dữ liệu chưa chuyển đổi nhưng vẫn có kế hoạch xử lý, workflow phải thể hiện trạng thái partial hoặc pending thay vì báo completed.

## 28. Những sai lầm thường gặp

- Chỉ kiểm tra KMS trả về version mới mà không kiểm tra ứng dụng đã dùng version đó.
- Xóa version cũ ngay sau cutover khiến dữ liệu hoặc backup lịch sử không thể giải mã.
- Giả định KEK rotation luôn yêu cầu re-encrypt toàn bộ dữ liệu hoặc ngược lại, giả định rewrap luôn đủ khi DEK đã lộ.
- Không lưu key version cùng ciphertext hoặc metadata record.
- Dùng mock cho toàn bộ test và bỏ qua hành vi thực tế của KMS/HSM.
- Không kiểm thử timeout sau khi provider đã hoàn tất thao tác.
- Cho phép nhiều worker rotation chạy đồng thời mà không có điều phối.
- Retry không idempotent làm tạo nhiều version hoặc ghi đè metadata.
- Rollback về khóa đã bị compromise.
- Không kiểm tra quyền deny và quyền kế thừa.
- Không thử backup/restore sau khi thay key version.
- Không kiểm tra audit event, cache propagation và consumer chưa cập nhật.
- Đưa key material thật vào test fixture hoặc log.

## 29. Checklist trước khi release rotation workflow

- [ ] Có policy xác định trigger, chu kỳ, loại khóa và cách giữ version cũ.
- [ ] Đã xác định invariant về đọc dữ liệu cũ, ghi dữ liệu mới và quyền truy cập.
- [ ] Test chạy trên KMS/HSM test resource riêng.
- [ ] Key version mới đúng algorithm, purpose, scope và protection level.
- [ ] Current version chỉ được cập nhật sau khi version mới được xác minh.
- [ ] Ciphertext mới tham chiếu đúng key ID/version.
- [ ] Dữ liệu cũ vẫn giải mã hoặc đã được re-encrypt và xác minh.
- [ ] Rewrap và re-encrypt được phân biệt theo tình trạng DEK.
- [ ] Signing key/HMAC rotation đã kiểm tra producer và verifier.
- [ ] Concurrency, retry, timeout và worker crash đã được kiểm thử.
- [ ] Authorization positive/negative và separation of duties đạt yêu cầu.
- [ ] Backup/restore hoạt động với version cũ và mới.
- [ ] Audit event và monitoring phản ánh đúng trạng thái.
- [ ] Rollback không đưa hệ thống về khóa đã bị compromise.
- [ ] Có tiêu chí rõ ràng trước khi disable hoặc destroy version cũ.
- [ ] Không có key material hoặc secret thật trong test artifact.

## Kết luận

Test key rotation phải chứng minh hệ thống thay khóa mà vẫn giữ được tính bí mật, toàn vẹn và khả năng truy cập dữ liệu hợp lệ. Kiểm thử cần xác nhận version mới được tạo đúng policy, được kích hoạt nhất quán và được dùng cho thao tác mới; đồng thời version cũ tiếp tục phục vụ dữ liệu lịch sử trong thời gian được phép. Với envelope encryption, cần phân biệt rewrap KEK với re-encrypt dữ liệu khi DEK bị ảnh hưởng. Các test phải bao gồm quyền truy cập, concurrency, retry, rollback, backup/restore, audit và hiệu năng của KMS/HSM. Chỉ retire hoặc destroy version cũ sau khi consumer, dữ liệu, backup và yêu cầu retention đã được xác minh. Một bộ test tốt giúp rotation trở thành thay đổi có thể dự đoán, quan sát và phục hồi thay vì một thao tác rủi ro trong production.

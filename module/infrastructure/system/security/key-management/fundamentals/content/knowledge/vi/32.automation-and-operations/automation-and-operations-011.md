# Runbook key compromise

Runbook key compromise là tài liệu hướng dẫn đội vận hành và an ninh xử lý khi khóa mật mã có dấu hiệu bị lộ, bị truy cập trái phép hoặc bị sử dụng ngoài mục đích được phê duyệt. Runbook giúp đội ứng phó xác định khóa và dữ liệu chịu ảnh hưởng, giới hạn hoạt động của kẻ tấn công, thay thế hoặc thu hồi khóa, khôi phục dịch vụ và bảo toàn bằng chứng.

Trong quản lý khóa mật mã, sự cố có thể liên quan đến nhiều loại tài sản: DEK dùng mã hóa dữ liệu, KEK dùng bọc DEK, khóa ký số, khóa riêng TLS, khóa HMAC, khóa gốc của hệ thống hoặc credential có quyền gọi KMS. Mỗi loại có tác động khác nhau. Một khóa mã hóa bị lộ có thể làm mất tính bí mật của dữ liệu; khóa ký bị lộ có thể cho phép tạo chữ ký giả; khóa xác thực bị lộ có thể mở đường cho truy cập vào dịch vụ quản lý khóa. Runbook cần phân biệt các trường hợp này để chọn biện pháp ứng phó đúng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện dấu hiệu và phạm vi của sự cố key compromise.
- Phân biệt lộ key material với lộ credential hoặc quyền truy cập KMS.
- Đánh giá tác động theo loại khóa, mục đích sử dụng và cấu trúc envelope encryption.
- Kích hoạt đội ứng phó, phân loại mức độ nghiêm trọng và bảo toàn bằng chứng.
- Chọn biện pháp containment phù hợp như thu hồi credential, giới hạn quyền, disable key hoặc chặn thao tác.
- Lập kế hoạch tạo khóa mới, rotation, rewrap, re-encrypt và certificate revocation.
- Khôi phục dịch vụ có kiểm soát và xác minh khóa mới được sử dụng đúng.
- Ghi nhận quyết định, thời gian, phạm vi ảnh hưởng và bài học sau sự cố.

## 2. Key compromise là gì?

Key compromise là tình huống tính bí mật hoặc tính toàn vẹn của khóa mật mã không còn được bảo đảm. Khóa có thể đã bị sao chép, truy xuất trái phép, sử dụng bởi principal không được phép hoặc bị đặt vào môi trường không còn đáp ứng yêu cầu bảo vệ.

Không phải mọi sự cố truy cập KMS đều chứng minh key material đã bị lộ. Ví dụ, một workload có thể gọi Decrypt trái phép trong khi khóa vẫn không exportable và nằm trong HSM. Trường hợp đó là sự cố lạm dụng quyền sử dụng khóa; tác động vẫn có thể nghiêm trọng dù attacker chưa lấy được bản sao key material.

Ngược lại, một private key bị sao chép từ file backup có thể bị compromise ngay cả khi chưa có event KMS bất thường. Việc điều tra phải xem xét cả khả năng lộ vật liệu khóa, khả năng sử dụng khóa từ xa và quyền quản trị hệ thống giữ khóa.

## 3. Phân biệt các loại sự cố liên quan đến khóa

| Loại sự cố | Ví dụ | Tác động chính |
|---|---|---|
| Key material exposure | Private key, AES key hoặc HMAC key bị sao chép ra ngoài | Attacker có thể tự thực hiện phép mật mã bằng khóa bị lộ |
| Unauthorized key usage | Principal lạ gọi Decrypt hoặc Sign qua KMS | Dữ liệu có thể bị giải mã hoặc thông điệp giả mạo dù key material không bị export |
| Credential compromise | KMS API token, service account key hoặc cloud credential bị lộ | Attacker có thể sử dụng quyền của danh tính bị chiếm đoạt |
| Key administrator compromise | Tài khoản quản trị bị chiếm quyền, sửa policy hoặc tạo role mới | Phạm vi ảnh hưởng có thể mở rộng sang nhiều khóa và workload |
| HSM boundary compromise | Thiết bị, partition hoặc quyền quản trị HSM bị xâm phạm | Mức bảo đảm về bảo vệ key material trong HSM có thể không còn đáng tin |
| Signing key compromise | Private key ký số bị lộ hoặc bị dùng trái phép | Chữ ký giả có thể được bên nhận tin cậy |
| Certificate compromise | Private key tương ứng với chứng thư TLS bị lộ | Có thể giả mạo endpoint hoặc client trong phạm vi trust |

Runbook phải ghi rõ loại sự cố đang được nghi ngờ và bằng chứng hỗ trợ. Nếu chưa biết key material có bị lộ hay chưa, hãy xử lý theo mức rủi ro của khóa và giữ trạng thái là suspected compromise cho đến khi có kết luận.

## 4. Những loại khóa và phạm vi ảnh hưởng

### 4.1. Data Encryption Key (DEK)

DEK trực tiếp mã hóa dữ liệu. Nếu DEK bị lộ, attacker có thể giải mã ciphertext được bảo vệ bởi DEK đó nếu họ có bản ciphertext tương ứng. Phạm vi ảnh hưởng phụ thuộc số bản ghi, file, tenant hoặc backup dùng cùng DEK.

Biện pháp khắc phục thường cần tạo DEK mới và mã hóa lại dữ liệu còn cần bảo vệ. Nếu DEK được dùng cho một tập dữ liệu nhỏ, phạm vi xử lý có thể giới hạn. Nếu một DEK được tái sử dụng rộng, cần đánh giá toàn bộ dữ liệu và bản sao liên quan.

### 4.2. Key Encryption Key (KEK)

KEK bảo vệ DEK trong mô hình envelope encryption. Nếu KEK bị lộ, attacker có thể tìm các encrypted DEK và thử mở chúng bằng KEK đã lấy được. Cần xác định encrypted DEK nào được bảo vệ bởi KEK, các bản sao của chúng ở đâu và có bị truy cập hay không.

Nếu có bằng chứng KEK bị lộ nhưng DEK plaintext chưa bị lộ, có thể tạo KEK mới và rewrap các DEK còn tin cậy. Nếu không thể chứng minh DEK chưa bị lộ hoặc attacker đã có thể mở DEK, cần cân nhắc tạo DEK mới và re-encrypt dữ liệu.

### 4.3. Khóa ký số

Private key ký số bị lộ cho phép attacker tạo chữ ký mới có thể được xác minh bằng public key tương ứng. Cần xác định hệ thống nào tin cậy khóa, loại token hoặc artifact nào được ký và khoảng thời gian chữ ký có thể bị giả mạo.

Biện pháp thường gồm ngừng ký bằng khóa cũ, tạo key pair mới, cập nhật trust store hoặc key registry, thu hồi chứng thư nếu khóa gắn với certificate và xác minh lại chữ ký phát sinh trong khoảng nghi ngờ.

### 4.4. Khóa riêng TLS hoặc mTLS

Private key TLS bị lộ có thể hỗ trợ giả mạo endpoint hoặc client tùy vai trò chứng thư và điều kiện xác thực. Cần xác định SAN, issuer, serial number, client/server role, các endpoint dùng khóa và cơ chế kiểm tra thu hồi của client.

Tạo key pair mới, cấp chứng thư mới, triển khai trên mọi endpoint và thu hồi chứng thư cũ theo chính sách. Với mTLS, phối hợp cả client và server để tránh một phía vẫn tin cậy chứng thư đã bị compromise.

### 4.5. Khóa HMAC và khóa xác thực

Khóa HMAC dùng chung bị lộ có thể cho phép tạo MAC hợp lệ. Credential dùng để gọi KMS có thể cho phép attacker thực hiện thao tác dưới danh tính của workload. Cần phân biệt hai trường hợp: lộ khóa HMAC yêu cầu thay khóa và cập nhật các bên xác minh; lộ credential KMS yêu cầu thu hồi credential, giới hạn principal và điều tra các thao tác đã thực hiện.

## 5. Mô hình envelope encryption và blast radius

Trong envelope encryption, DEK mã hóa dữ liệu; KEK bảo vệ DEK. Khi một KEK bị compromise, không mặc định toàn bộ dữ liệu đã bị giải mã. Cần lập bản đồ:

- KEK và các phiên bản KEK liên quan.
- Các encrypted DEK được bọc bởi từng KEK version.
- Dữ liệu hoặc object tham chiếu từng DEK.
- Backup, replica, archive và export có chứa encrypted DEK.
- Workload có quyền unwrap hoặc decrypt.
- Thời điểm và phạm vi truy cập đáng ngờ.

Mục tiêu là xác định blast radius: tập tài nguyên có thể bị ảnh hưởng bởi một khóa hoặc một principal. Không chỉ dựa vào tên khóa; cần dùng metadata, inventory, encryption context và audit event có sẵn.

Nếu attacker chỉ lấy được encrypted DEK mà không có KEK hoặc quyền gọi thao tác giải bọc, dữ liệu có thể vẫn được bảo vệ. Nếu attacker lấy được cả KEK và encrypted DEK, giả định an toàn đó không còn đúng.

## 6. Dấu hiệu phát hiện key compromise

Các tín hiệu thường gặp:

- Key material xuất hiện trong repository, artifact, ticket, log, crash dump hoặc nơi chia sẻ không được phép.
- Có lệnh export hoặc download key material ngoài quy trình được duyệt.
- Principal lạ hoặc workload không có owner gọi Decrypt, UnwrapKey hoặc Sign.
- Số lượng thao tác mật mã tăng đột biến hoặc xuất hiện từ nguồn mạng bất thường.
- KMS policy, role binding, HSM partition hoặc quyền export thay đổi ngoài lịch.
- Secret manager ghi nhận truy cập secret từ danh tính hoặc môi trường mới.
- Private key được sao chép, file permission thay đổi hoặc backup được truy cập trái phép.
- Chứng thư bị dùng từ endpoint không được đăng ký hoặc có dấu hiệu giả mạo.
- Một key version bị disable, enable hoặc schedule deletion ngoài yêu cầu thay đổi.
- Hệ thống audit mất event, subscription bị tắt hoặc log có khoảng trống bất thường.

Một cảnh báo đơn lẻ có thể do lỗi cấu hình hoặc batch job hợp lệ. Hãy đối chiếu với deployment, change ticket, owner, lịch vận hành và các nguồn log độc lập trước khi kết luận.

## 7. Phân loại mức độ nghiêm trọng

Mức độ sự cố nên dựa trên độ nhạy cảm của khóa, khả năng attacker sử dụng khóa, phạm vi dữ liệu, trạng thái khai thác và tác động sẵn sàng.

| Mức | Tình huống tham khảo | Phản ứng |
|---|---|---|
| Critical | Có bằng chứng key material của khóa gốc, khóa ký production hoặc KEK diện rộng bị lộ; attacker đang sử dụng; dữ liệu hoặc danh tính quan trọng bị ảnh hưởng | Kích hoạt incident response khẩn cấp, containment ngay, chỉ huy sự cố và đánh giá tác động liên tục |
| High | Credential có quyền Decrypt/Sign hoặc private key của một dịch vụ production bị lộ; phạm vi có thể xác định nhưng chưa thấy khai thác diện rộng | Thu hồi credential hoặc khóa liên quan, triển khai khóa thay thế và điều tra toàn bộ phạm vi |
| Medium | Có truy cập bất thường hoặc secret bị đưa vào vị trí rủi ro nhưng chưa có bằng chứng sử dụng trái phép | Giới hạn quyền, bảo toàn bằng chứng, xác minh mức phơi lộ và thay khóa theo đánh giá |
| Low / Informational | Phát hiện bản sao thử nghiệm đã hết hiệu lực hoặc cảnh báo sai được xác minh, không có đường truy cập tới tài nguyên nhạy cảm | Ghi nhận, khắc phục nguồn phát hiện và cập nhật inventory |

Không hạ mức sự cố chỉ vì chưa thấy dữ liệu bị tải xuống. Việc attacker có khả năng giải mã, ký hoặc sử dụng khóa đã là một rủi ro cần xử lý.

## 8. Vai trò trong quá trình ứng phó

Một sự cố khóa thường liên quan nhiều nhóm. Cần chỉ định người chịu trách nhiệm cho từng phần:

| Vai trò | Trách nhiệm |
|---|---|
| Incident Commander | Điều phối, đặt mức độ ưu tiên, quyết định escalation và theo dõi tiến độ |
| Key Owner | Xác định mục đích khóa, consumer, dữ liệu phụ thuộc và phương án thay thế |
| KMS/HSM Operator | Thực hiện disable, policy change, rotation, rewrap hoặc thao tác HSM được phê duyệt |
| Security Incident Responder | Phân tích dấu hiệu xâm nhập, thu thập bằng chứng và xác định phạm vi attacker |
| Application Owner | Cập nhật workload, kiểm tra chức năng và xác minh dữ liệu sau khôi phục |
| IAM/Platform Operator | Thu hồi credential, session, role binding và giới hạn danh tính bị ảnh hưởng |
| Audit/Compliance Contact | Bảo toàn hồ sơ, đánh giá yêu cầu báo cáo và theo dõi bằng chứng |

Với sự cố nghiêm trọng, một người nên giữ vai trò chỉ huy để các nhóm không thực hiện các thay đổi mâu thuẫn. Các thao tác có thể làm mất khả năng giải mã hoặc phá hủy bằng chứng cần được điều phối rõ ràng.

## 9. Nguyên tắc ứng phó

Khi nghi ngờ key compromise, áp dụng các nguyên tắc:

1. Ưu tiên bảo vệ con người, hệ thống và dữ liệu quan trọng.
2. Hạn chế khả năng attacker tiếp tục sử dụng khóa hoặc credential.
3. Bảo toàn audit log và bằng chứng trước khi chúng bị ghi đè hoặc xóa.
4. Xác định phạm vi theo key ID, version, principal, resource và thời gian.
5. Thay thế khóa theo đúng loại và mục đích sử dụng.
6. Kiểm tra khả năng khôi phục dữ liệu trước khi hủy hoặc xóa khóa cũ.
7. Xác minh hệ thống đã dùng khóa mới và quyền truy cập đã được giới hạn.
8. Ghi lại mọi quyết định, người thực hiện, thời gian và kết quả.

Không gửi key material nghi bị lộ vào ticket, chat, email hoặc báo cáo sự cố. Dùng key ID, fingerprint đã được kiểm soát và vị trí lưu trữ để tham chiếu.

## 10. Checklist 15 phút đầu

Trong giai đoạn đầu, mục tiêu là xác nhận tín hiệu, thiết lập điều phối và ngăn tình hình xấu đi:

- [ ] Mở incident record và ghi thời điểm phát hiện.
- [ ] Chỉ định Incident Commander và Key Owner.
- [ ] Ghi key ID, key version, loại khóa, purpose, environment và owner.
- [ ] Xác định sự cố là suspected hay confirmed compromise.
- [ ] Ghi nhận nguồn phát hiện: audit event, cảnh báo, repository scan, người báo cáo hoặc nhà cung cấp.
- [ ] Bảo toàn log và snapshot cấu hình có liên quan.
- [ ] Kiểm tra thao tác Decrypt, Sign, Export, UnwrapKey và thay đổi policy gần thời điểm phát hiện.
- [ ] Xác định principal và workload có thể sử dụng khóa.
- [ ] Đánh giá có hoạt động trái phép đang tiếp diễn hay không.
- [ ] Quyết định biện pháp containment ban đầu và thông báo owner liên quan qua quy trình incident nội bộ.

Nếu có bằng chứng attacker đang khai thác khóa production, không trì hoãn containment chỉ để hoàn tất toàn bộ điều tra. Ghi lại bằng chứng sẵn có và tiếp tục điều tra song song với việc giới hạn truy cập.

## 11. Thu thập và bảo toàn bằng chứng

Trước khi thay đổi trạng thái khóa hoặc policy, thu thập các bằng chứng có thể lấy an toàn và nhanh chóng:

- KMS audit event và HSM audit log.
- Key metadata, key version, purpose, protection level và trạng thái hiện tại.
- IAM role binding, key policy, resource policy và lịch sử thay đổi.
- Secret manager access log và lịch sử version của secret.
- Cloud audit log, identity provider log, session và token issuance event.
- Application log, API gateway log, trace ID và deployment history.
- Repository, CI/CD, artifact registry hoặc file path nơi secret có thể bị lộ.
- Backup/replica inventory và mapping giữa KEK, DEK và dữ liệu.

Lưu bản sao theo cơ chế bảo vệ bằng chứng của tổ chức, ghi nguồn, thời gian thu thập, người thu thập và checksum nếu quy trình yêu cầu. Hạn chế quyền truy cập vào evidence store.

Không tải key material nghi bị lộ về máy cá nhân để kiểm tra. Nếu cần xác minh file hoặc bản sao, dùng môi trường điều tra được kiểm soát và quy trình xử lý dữ liệu nhạy cảm.

## 12. Xác định phạm vi ảnh hưởng

Phạm vi điều tra nên trả lời:

1. Khóa nào bị nghi ngờ? Key ID và version cụ thể là gì?
2. Loại khóa, thuật toán, purpose và protection level?
3. Khóa được tạo, lưu hoặc sử dụng ở đâu?
4. Những principal nào có quyền quản trị, export hoặc sử dụng?
5. Những dữ liệu, tenant, certificate, token hoặc artifact nào phụ thuộc vào khóa?
6. Có bản sao trong backup, cache, snapshot, repository hoặc môi trường thử nghiệm không?
7. Thời điểm sớm nhất có thể bị lộ và thời điểm cuối cùng có thể bị sử dụng?
8. Có bằng chứng truy cập, giải mã, ký hoặc export trái phép không?
9. Khóa có được dùng chung giữa nhiều môi trường hoặc ứng dụng không?
10. Có khóa con hoặc encrypted DEK nào được bảo vệ bởi khóa bị ảnh hưởng không?

Lập danh sách tài nguyên theo trạng thái: confirmed affected, potentially affected, investigated and cleared hoặc unknown. Không gộp mọi tài nguyên vào một nhóm nếu bằng chứng khác nhau.

## 13. Containment: giới hạn quyền sử dụng khóa

Containment là bước giảm khả năng attacker tiếp tục sử dụng khóa. Biện pháp phải phù hợp với loại sự cố và yêu cầu sẵn sàng của dịch vụ.

Các lựa chọn có thể gồm:

- Thu hồi access token, service account key hoặc credential bị lộ.
- Vô hiệu hóa session hoặc workload identity bị chiếm đoạt.
- Gỡ role binding hoặc thu hẹp permission của principal đáng ngờ.
- Chặn nguồn gọi tại gateway hoặc network policy nếu nguồn đã được xác định.
- Tạm dừng job hoặc workload đang tạo request bất thường.
- Tắt quyền export hoặc thay policy để ngăn truy xuất key material.
- Disable key hoặc key version nếu cần chặn thao tác mật mã ngay.

Disable key có thể làm gián đoạn các dịch vụ đang phụ thuộc vào nó, bao gồm giải mã dữ liệu lịch sử. Trước khi thực hiện, đánh giá tác động và chuẩn bị phương án khôi phục. Nếu attacker đang dùng khóa để gây thiệt hại, ưu tiên chặn hoạt động trái phép và phối hợp với owner để quản lý gián đoạn.

Không chỉ xoay vòng khóa mà bỏ qua credential bị lộ. Nếu attacker vẫn giữ quyền quản trị KMS, họ có thể cấp quyền lại, sử dụng khóa mới hoặc thay đổi policy lần nữa.

## 14. Containment theo từng loại khóa

| Loại bị ảnh hưởng | Containment ưu tiên | Lưu ý |
|---|---|---|
| DEK | Dừng consumer hoặc thao tác giải mã đáng ngờ; giới hạn quyền đọc dữ liệu liên quan | Xác định chính xác tập ciphertext và bản sao dùng DEK |
| KEK | Thu hẹp quyền unwrap/decrypt, chặn principal đáng ngờ, xem xét disable key | Cần inventory encrypted DEK và phụ thuộc dữ liệu |
| Signing key | Dừng ký bằng khóa nghi bị lộ, chặn signer và thông báo bên xác minh theo quy trình | Chuẩn bị key pair và trust metadata mới |
| TLS/mTLS private key | Thay key pair, triển khai certificate mới, chặn endpoint bị ảnh hưởng khi cần | Phối hợp server, client, load balancer và trust store |
| HMAC key | Dừng xác thực dựa trên key cũ khi có thể, chuyển các bên sang key mới | Mọi bên ký và xác minh phải chuyển đổi nhất quán |
| KMS credential | Thu hồi credential/session, disable principal hoặc giảm role | Xem lại mọi thao tác khóa do principal thực hiện |
| HSM administrator credential | Thu hồi hoặc thay credential, kiểm tra audit và cấu hình partition | Có thể cần quy trình quản trị thiết bị và dual control |

Containment không nhất thiết là hủy khóa. Trong nhiều trường hợp, giữ khóa cũ ở trạng thái bị giới hạn là cần thiết để giải mã dữ liệu lịch sử hoặc bảo toàn bằng chứng trong khi điều tra.

## 15. Quyết định disable, revoke hay rotate

Ba hành động này có ý nghĩa khác nhau:

- **Disable:** tạm ngăn một khóa hoặc version thực hiện một số hoặc mọi thao tác theo khả năng nền tảng. Khóa vẫn tồn tại và có thể được enable lại nếu policy cho phép.
- **Revoke:** thu hồi chứng thư hoặc credential được bên khác kiểm tra trạng thái; ví dụ certificate revocation qua OCSP/CRL.
- **Rotate:** thay khóa hiện hành bằng key material mới, cập nhật consumer và quản lý version cũ.

Không dùng các thuật ngữ thay thế cho nhau. Với private key TLS bị lộ, thường cần tạo key pair mới và revoke certificate cũ. Với KEK bị lộ, có thể cần disable version cũ, tạo KEK mới và rewrap DEK. Với credential KMS bị lộ, phải revoke credential và rà soát permission; chỉ rotate key material không giải quyết được credential compromise.

## 16. Rotation và thay thế khóa

Khi đã quyết định thay khóa:

1. Tạo key mới trong KMS/HSM hoặc môi trường được phê duyệt.
2. Xác định thuật toán, độ dài, purpose, protection level và policy.
3. Cấp quyền cho đúng workload và người vận hành theo least privilege.
4. Cập nhật key reference hoặc key version trong secret/config store.
5. Triển khai consumer theo từng nhóm hoặc canary nếu phù hợp.
6. Kiểm tra thao tác encrypt, decrypt, sign hoặc verify bằng khóa mới.
7. Theo dõi audit event để xác nhận principal hợp lệ đã chuyển đổi.
8. Thu hẹp hoặc vô hiệu hóa khóa cũ theo kế hoạch.
9. Rà soát các consumer, backup và batch job còn dùng khóa cũ.

Với khóa ký, cần cập nhật public key, certificate, JWKS hoặc trust store ở các bên xác minh. Với HMAC, tất cả bên tạo và xác minh MAC phải chuyển sang cùng key version. Với khóa mã hóa, cần quyết định có phải re-encrypt dữ liệu đã tồn tại hay không.

## 17. Rewrap và re-encrypt trong envelope encryption

Hai thao tác này giải quyết phạm vi khác nhau:

### 17.1. Rewrap DEK

Rewrap dùng KEK mới để bảo vệ lại DEK hiện có. Dữ liệu được mã hóa bằng DEK có thể giữ nguyên ciphertext; chỉ encrypted DEK thay đổi. Phương án này phù hợp khi KEK bị lộ hoặc cần thay KEK, trong khi DEK được đánh giá vẫn an toàn.

Quy trình:

1. Tạo KEK mới và cấp quyền cần thiết.
2. Lấy encrypted DEK từ metadata hoặc kho dữ liệu.
3. Mở DEK bằng cơ chế được kiểm soát nếu còn an toàn để thực hiện.
4. Bọc DEK bằng KEK mới.
5. Ghi encrypted DEK mới cùng key reference/version mới theo thao tác nguyên tử.
6. Xác minh ứng dụng đọc được dữ liệu bằng đường dẫn mới.
7. Theo dõi số lượng DEK đã chuyển đổi và các object còn tham chiếu KEK cũ.

### 17.2. Re-encrypt dữ liệu

Re-encrypt giải mã dữ liệu bằng khóa cũ rồi mã hóa lại bằng DEK mới. Cần cân nhắc khi DEK bị lộ hoặc có bằng chứng plaintext đã bị truy cập trái phép. Rewrap đơn thuần không làm thay đổi ciphertext đã mã hóa bằng DEK bị compromise.

Quy trình re-encrypt phải xử lý batch, checkpoint, tính toàn vẹn dữ liệu, retry, concurrent write và khả năng rollback. Không xóa encrypted DEK hoặc khóa cũ cho đến khi dữ liệu mới đã được xác minh và backup cần thiết vẫn khôi phục được.

Nếu attacker đã đọc plaintext trong thời gian compromise, re-encrypt chỉ bảo vệ dữ liệu sau khi chuyển đổi; nó không thể làm cho bản plaintext đã bị sao chép trở nên bí mật trở lại.

## 18. Xử lý khóa ký và chứng thư bị compromise

Với signing key:

1. Dừng sử dụng private key nghi bị lộ để ký nội dung mới.
2. Tạo key pair mới trong KMS/HSM.
3. Cập nhật public key trong JWKS, key registry hoặc trust store.
4. Nếu khóa gắn với chứng thư, yêu cầu CA revoke certificate cũ và cấp certificate mới.
5. Xác định khoảng thời gian từ lúc có thể bị lộ đến lúc dừng ký.
6. Kiểm tra token, artifact, firmware, package hoặc tài liệu được ký trong khoảng đó.
7. Xác minh lại chữ ký bằng public key và trạng thái trust thích hợp; đánh dấu hoặc phát hành lại artifact khi cần.
8. Thông báo cho consumer về key ID mới và thời điểm ngừng tin cậy key ID cũ.

Với JWT hoặc token tự chứa, consumer có thể tiếp tục tin cậy chữ ký cũ nếu public key cũ vẫn nằm trong JWKS cache. Cần có kế hoạch loại bỏ key cũ, cập nhật cache và xử lý token đã phát hành trong khoảng nghi ngờ. Không chỉ thay private key phía signer mà quên các bên xác minh.

## 19. Khôi phục dịch vụ

Khôi phục phải đưa hệ thống về trạng thái hoạt động với khóa mới và quyền đã được rà soát. Trước khi mở lại traffic:

- Xác nhận key mới đang active và có đúng purpose.
- Xác nhận role binding, key policy và IAM chỉ cấp quyền cần thiết.
- Kiểm tra các thao tác mật mã với dữ liệu thử nghiệm và dữ liệu được phép.
- Xác minh mọi replica, vùng và consumer đã cập nhật.
- Kiểm tra audit event mới ghi nhận đúng principal, key ID/version và operation.
- Xác minh backup và quy trình restore hoạt động với thiết kế khóa mới.
- Theo dõi lỗi, latency, quota và các cảnh báo sau cutover.

Mở lại dịch vụ theo từng bước nếu có thể. Giữ cơ chế rollback nhưng không rollback về một khóa đã xác nhận bị compromise. Nếu phải duy trì khóa cũ để giải mã dữ liệu lịch sử, giới hạn quyền sử dụng, giám sát chặt và ghi rõ thời hạn xử lý.

## 20. Kiểm tra tính toàn vẹn và phạm vi dữ liệu

Sau rotation hoặc re-encrypt, cần xác minh dữ liệu vẫn đọc được và không bị thay đổi ngoài ý muốn:

- So sánh số lượng object hoặc record trước và sau chuyển đổi.
- Kiểm tra hash, checksum, authentication tag hoặc cơ chế integrity phù hợp.
- Chạy kiểm tra giải mã trên mẫu dữ liệu và tập dữ liệu quan trọng.
- Kiểm tra metadata, encryption context, tenant và key reference.
- Xác nhận backup, replica và archive có thể khôi phục theo chính sách.
- Ghi lại object chưa chuyển đổi, lỗi và lý do.

Không coi việc thao tác KMS thành công là bằng chứng dữ liệu đã được khôi phục đầy đủ. Cần kiểm tra ở tầng ứng dụng và dữ liệu.

## 21. Bảo toàn khóa cũ và điều kiện hủy

Sau sự cố, có thể cần giữ khóa cũ để:

- Giải mã dữ liệu lịch sử còn được phép truy cập.
- Khôi phục backup hoặc archive.
- Xác minh chữ ký hoặc điều tra artifact cũ.
- Phục vụ điều tra pháp chứng và yêu cầu kiểm toán.

Giữ khóa cũ không có nghĩa tiếp tục cho phép sử dụng tự do. Có thể disable các thao tác không cần thiết, giới hạn quyền decrypt cho workload phục hồi chuyên biệt, cô lập key version và tăng giám sát.

Chỉ hủy khóa khi đã xác nhận dữ liệu phụ thuộc được chuyển đổi hoặc không còn cần khôi phục, retention và legal hold đã được xem xét, backup không còn yêu cầu khóa đó và owner phê duyệt. Hủy khóa quá sớm có thể gây mất dữ liệu vĩnh viễn; giữ khóa compromise không kiểm soát lại kéo dài rủi ro. Quyết định phải được ghi nhận.

## 22. Kịch bản cụ thể: KEK production bị nghi lộ

Giả sử hệ thống phát hiện một principal không rõ owner gọi UnwrapKey trên KEK dùng bảo vệ DEK của dịch vụ Customer Data.

1. Incident Commander mở sự cố mức High hoặc Critical theo phạm vi dữ liệu và xác nhận principal, key ID/version, thời điểm và request ID.
2. Security Responder bảo toàn KMS audit log, IAM log, key policy và metadata của encrypted DEK.
3. IAM Operator thu hồi credential hoặc session của principal đáng ngờ, gỡ role binding không hợp lệ và ngăn cấp lại quyền.
4. Key Owner lập danh sách encrypted DEK, tenant, object, backup và workload phụ thuộc KEK.
5. KMS Operator đánh giá khả năng disable KEK cũ mà không gây mất khả năng đọc dữ liệu cần thiết.
6. Tạo KEK mới, cấu hình policy và cấp quyền tối thiểu cho workload hợp lệ.
7. Nếu DEK được đánh giá chưa bị lộ, rewrap DEK bằng KEK mới; nếu DEK có thể đã bị lộ, tạo DEK mới và re-encrypt dữ liệu theo mức độ rủi ro.
8. Triển khai consumer và xác minh dữ liệu đọc được bằng key reference mới.
9. Disable hoặc giới hạn KEK cũ, theo dõi mọi request còn sử dụng nó và xử lý các object chưa chuyển đổi.
10. Hoàn tất điều tra, đánh giá dữ liệu có thể đã bị truy cập và ghi lại quyết định giữ hoặc hủy khóa cũ.

Kịch bản này minh họa cách phối hợp containment, điều tra và khôi phục. Trình tự thực tế cần điều chỉnh theo KMS, HSM, kiến trúc dữ liệu và mức độ hoạt động của attacker.

## 23. Runbook thao tác dạng checklist

### Phát hiện và điều phối

- [ ] Ghi thời gian phát hiện, nguồn cảnh báo và người báo cáo.
- [ ] Mở incident record và chỉ định Incident Commander.
- [ ] Xác định key ID, version, owner, purpose và environment.
- [ ] Phân loại suspected/confirmed và mức độ nghiêm trọng.

### Bảo toàn bằng chứng và xác định phạm vi

- [ ] Thu thập KMS/HSM audit log, IAM log và secret access log.
- [ ] Lưu key metadata, policy và role binding.
- [ ] Xác định principal, workload, resource và khoảng thời gian nghi ngờ.
- [ ] Lập danh sách dữ liệu, DEK, certificate hoặc artifact phụ thuộc.
- [ ] Ghi nhận backup, replica và các bản sao có thể chứa key material.

### Containment

- [ ] Thu hồi credential hoặc session bị lộ.
- [ ] Giới hạn principal và permission không hợp lệ.
- [ ] Dừng workload hoặc job đang tạo hoạt động bất thường.
- [ ] Quyết định disable key/version theo tác động sẵn sàng và mức độ khai thác.
- [ ] Theo dõi event để xác nhận attacker không còn sử dụng được quyền cũ.

### Thay thế và khôi phục

- [ ] Tạo key mới và kiểm tra purpose, algorithm, protection level.
- [ ] Cấp quyền tối thiểu cho consumer hợp lệ.
- [ ] Thực hiện rewrap hoặc re-encrypt theo loại compromise.
- [ ] Cập nhật signer, certificate, JWKS hoặc trust store nếu liên quan.
- [ ] Triển khai trên mọi consumer và xác minh endpoint.
- [ ] Kiểm tra tính toàn vẹn dữ liệu và khả năng restore.

### Đóng sự cố

- [ ] Xác minh hoạt động bất thường đã dừng.
- [ ] Rà soát quyền, secret, backup và bản sao còn tồn tại.
- [ ] Quyết định trạng thái khóa cũ và điều kiện hủy.
- [ ] Hoàn tất báo cáo tác động, bằng chứng và quyết định.
- [ ] Ghi nhận hành động phòng ngừa và owner thực hiện.

## 24. Ví dụ mẫu incident record

Mẫu dưới đây là cấu trúc ghi nhận sự cố, không chứa key material:

~~~yaml
incident:
  id: INC-2026-0042
  type: suspected-key-compromise
  severity: high
  detected_at: 2026-11-28T04:15:00Z
  commander: security-incident-lead

affected_key:
  key_id: key/customer-data-kek
  key_version: v7
  purpose: key-encryption
  environment: production
  owner: customer-platform

assessment:
  key_material_exposed: unknown
  unauthorized_usage: confirmed
  affected_data_scope: under-investigation

containment:
  credential_revoked: true
  principal_restricted: true
  key_disabled: pending-impact-review

recovery:
  replacement_key_id: pending
  rewrap_status: not-started
  data_integrity_check: pending

evidence:
  audit_case: SEC-CASE-1042
  request_ids:
    - req-example-001
~~~

Các giá trị là ví dụ. Incident record thực tế cần theo schema và hệ thống quản lý sự cố của tổ chức. Không lưu secret, private key hoặc plaintext trong record.

## 25. Giao tiếp và báo cáo trong sự cố

Thông tin cần được chia sẻ theo nhu cầu công việc và quy trình ứng phó:

- Incident Commander cần trạng thái, mức độ, quyết định và blocker.
- Key Owner cần danh sách consumer, dữ liệu phụ thuộc và kế hoạch chuyển đổi.
- Application Owner cần thời gian dự kiến, thay đổi key reference và bước xác minh.
- Security và audit cần bằng chứng, phạm vi, timeline và quyết định xử lý.
- Các bên bị ảnh hưởng cần thông tin chính xác theo quy trình thông báo của tổ chức.

Không gửi key material hoặc credential qua kênh báo cáo. Khi cần chỉ rõ khóa, dùng key ID, version, certificate serial hoặc fingerprint phù hợp.

Mỗi cập nhật nên ghi rõ điều đã xác minh, điều còn chưa biết, hành động tiếp theo, owner và thời điểm cập nhật. Tránh khẳng định dữ liệu đã an toàn khi chưa hoàn tất đánh giá phạm vi và khả năng truy cập.

## 26. Sau sự cố: root cause và cải thiện

Sau khi khôi phục, thực hiện post-incident review:

1. Xây dựng timeline từ dấu hiệu đầu tiên đến containment, rotation và recovery.
2. Xác định nguyên nhân gốc: quyền quá rộng, secret lưu sai nơi, pipeline thiếu giám sát, lỗ hổng ứng dụng hoặc quy trình vận hành.
3. Đánh giá vì sao cơ chế phòng ngừa và phát hiện hiện tại không ngăn được sự cố sớm hơn.
4. Xác định dữ liệu, hệ thống và bên liên quan bị ảnh hưởng.
5. Ghi nhận quyết định disable, revoke, rotate, rewrap, re-encrypt và giữ khóa cũ.
6. Tạo action item có owner, deadline và tiêu chí hoàn thành.
7. Cập nhật inventory, policy, runbook, alert rule và quy trình access review.
8. Diễn tập lại kịch bản sau khi thay đổi để xác nhận biện pháp cải thiện có hiệu quả.

Không dùng post-incident review để tìm người chịu lỗi cá nhân. Mục tiêu là hiểu điều kiện kỹ thuật và quy trình đã cho phép sự cố xảy ra, sau đó giảm khả năng tái diễn.

## 27. Những sai lầm cần tránh

- Chỉ rotate khóa mà không thu hồi credential hoặc quyền quản trị đã bị lộ.
- Disable khóa ngay lập tức mà không đánh giá ảnh hưởng đến giải mã và restore, trừ khi containment khẩn cấp yêu cầu.
- Rewrap DEK rồi kết luận dữ liệu đã an toàn dù DEK có thể đã bị lộ.
- Re-encrypt nhưng quên backup, replica, archive hoặc object chưa chuyển đổi.
- Hủy khóa cũ trước khi xác minh dữ liệu phụ thuộc và khả năng khôi phục.
- Thay private signing key nhưng không cập nhật public key hoặc trust store ở consumer.
- Reissue certificate nhưng không revoke certificate cũ khi private key đã bị compromise.
- Tin rằng key không exportable đồng nghĩa không thể bị lạm dụng qua API Decrypt hoặc Sign.
- Chỉ xem KMS log mà bỏ qua IAM, secret manager, application và deployment log.
- Ghi key material hoặc credential nghi bị lộ vào incident ticket.
- Không kiểm tra quyền của principal có thể cấp lại quyền sau containment.
- Đóng sự cố khi dashboard đã yên lặng nhưng chưa xác minh các consumer và dữ liệu phụ thuộc.

## 28. Checklist sẵn sàng trước sự cố

- [ ] Mỗi khóa production có owner, purpose, classification và inventory consumer.
- [ ] Có mapping KEK-DEK-data object cho hệ thống envelope encryption.
- [ ] Có quy trình khẩn cấp để thu hồi credential, giới hạn principal và disable key.
- [ ] Có người được phân công vận hành KMS/HSM và người chỉ huy sự cố.
- [ ] Audit log được gửi đến vùng riêng, bảo vệ toàn vẹn và có retention phù hợp.
- [ ] Có thể truy vấn event theo key ID, version, principal, operation và request ID.
- [ ] Có bản sao policy, metadata và cấu hình cần thiết để điều tra.
- [ ] Có phương án tạo key mới và cấp quyền cho workload hợp lệ.
- [ ] Có quy trình rewrap và re-encrypt đã được kiểm thử.
- [ ] Có phương án cập nhật signing key, certificate, JWKS và trust store.
- [ ] Backup và restore đã được kiểm thử với key version cần thiết.
- [ ] Có tiêu chí quyết định giữ, disable hoặc hủy khóa cũ.
- [ ] Có runbook liên hệ owner và escalation theo mức độ.
- [ ] Đã diễn tập key compromise và ghi nhận thời gian containment/recovery.

## Kết luận

Runbook key compromise biến phản ứng với sự cố lộ hoặc lạm dụng khóa thành một quy trình có thể điều phối, kiểm chứng và lặp lại. Đội ứng phó cần phân biệt key material exposure, unauthorized key usage và credential compromise; xác định loại khóa cùng dữ liệu phụ thuộc; bảo toàn audit evidence; rồi giới hạn quyền và hoạt động của attacker. Phương án thay thế phụ thuộc vai trò của khóa: DEK có thể cần re-encrypt dữ liệu, KEK có thể cần rewrap DEK, signing key cần thay trust metadata và certificate liên quan, còn credential KMS cần thu hồi danh tính và quyền. Khôi phục chỉ hoàn tất khi consumer dùng khóa mới, dữ liệu được xác minh, quyền đã được rà soát và khóa cũ có trạng thái được kiểm soát. Runbook cần được diễn tập định kỳ để đội vận hành có thể xử lý sự cố nhanh mà vẫn bảo toàn khả năng khôi phục và bằng chứng điều tra.

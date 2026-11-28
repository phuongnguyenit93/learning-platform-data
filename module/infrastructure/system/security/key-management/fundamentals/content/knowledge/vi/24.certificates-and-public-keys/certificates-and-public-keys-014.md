# Certificate và private key lifecycle

Trong chương **Certificate và public key** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này trình bày vòng đời của chứng thư số và khóa riêng từ khi tạo đến khi ngừng sử dụng và hủy. Chứng thư và private key có quan hệ mật thiết nhưng không phải cùng một tài sản: chứng thư là dữ liệu công khai do CA ký để liên kết danh tính với public key; private key là bí mật cho phép chủ thể thực hiện thao tác ký, giải mã hoặc xác thực. Quản lý an toàn cần theo dõi cả hai, cùng các bản sao, quyền truy cập và dữ liệu phụ thuộc.

## 1. Hai tài sản có vòng đời liên kết

**Certificate** là cấu trúc dữ liệu được CA ký, chứa public key, thông tin chủ thể, issuer, thời hạn, serial number, mục đích sử dụng và các ràng buộc khác. Chứng thư cho phép bên khác kiểm tra public key thuộc về danh tính nào và có được CA tin cậy xác nhận hay không.

**Private key** là phần bí mật của cặp khóa bất đối xứng. Chủ thể dùng nó để tạo chữ ký số hoặc thực hiện thao tác giải mã tùy thuật toán và thiết kế. Private key phải được bảo vệ khỏi truy cập, sao chép và sử dụng trái phép. Public key có thể được công bố; private key không được gửi cho CA cùng CSR và không được phân phối như một phần của chứng thư.

| Thành phần | Tính chất | Vai trò |
|---|---|---|
| Private key | Bí mật, cần kiểm soát chặt | Ký, giải mã hoặc chứng minh quyền sở hữu khóa theo giao thức |
| Public key | Có thể công bố | Xác minh chữ ký hoặc tham gia trao đổi khóa theo thuật toán |
| Certificate | Công khai, được CA ký | Liên kết public key với danh tính và giới hạn sử dụng |
| Certificate chain | Các chứng thư liên kết theo quan hệ issuer | Cho phép xây dựng đường dẫn xác minh tới trust anchor |
| Trust store | Danh sách trust anchor hoặc chứng thư được cấu hình tin cậy | Xác định điểm tin cậy mà ứng dụng dùng để xác minh chain |

Một private key có thể tồn tại trước khi chứng thư được cấp và có thể tiếp tục tồn tại sau khi chứng thư hết hạn. Ngược lại, chứng thư có thể được sao chép và phân phối rộng rãi mà không làm lộ private key. Vì thế, trạng thái của chứng thư không thể được dùng thay cho trạng thái của private key.

## 2. Vòng đời tổng thể

Vòng đời thường gồm các giai đoạn sau:

1. **Planning:** xác định danh tính, mục đích sử dụng, thuật toán, thời hạn và chính sách.
2. **Key generation:** tạo cặp khóa bằng nguồn ngẫu nhiên an toàn và trong môi trường phù hợp.
3. **Enrollment:** tạo CSR, xác minh danh tính và yêu cầu CA cấp chứng thư.
4. **Issuance:** CA phát hành chứng thư sau khi xác minh yêu cầu và áp dụng policy.
5. **Provisioning:** liên kết chứng thư với private key và phân phối tới đúng dịch vụ hoặc thiết bị.
6. **Active use:** sử dụng private key theo quyền được cấp, đồng thời kiểm tra chứng thư và chain.
7. **Monitoring:** theo dõi thời hạn, trạng thái, vị trí, quyền truy cập và dấu hiệu lộ khóa.
8. **Renewal hoặc rotation:** gia hạn chứng thư và quyết định có tiếp tục dùng key pair cũ hay tạo key pair mới.
9. **Retirement, revocation hoặc archival:** ngừng cấp phát, thu hồi chứng thư khi cần và giữ lại tài sản cần thiết cho xác minh hoặc giải mã lịch sử.
10. **Destruction:** hủy private key và các bản sao khi không còn nhu cầu hợp lệ.

Không phải mọi loại khóa đều đi qua các giai đoạn giống hệt nhau. Khóa TLS server, khóa ký mã nguồn, khóa ký tài liệu và khóa giải mã có mục đích cũng như yêu cầu lưu giữ khác nhau. Chính sách cần phân loại trước khi quy định backup, rotation và destruction.

## 3. Planning: xác định mục đích và policy

Trước khi tạo key pair, certificate owner cần xác định:

- Danh tính hoặc dịch vụ mà chứng thư đại diện.
- Subject và Subject Alternative Name (SAN), bao gồm DNS name, IP hoặc URI SAN nếu phù hợp.
- Mục đích: TLS server, TLS client, ký mã nguồn, ký tài liệu, email hay giải mã.
- Thuật toán, độ dài khóa hoặc elliptic curve được policy chấp thuận.
- Nơi tạo và lưu private key: phần mềm, HSM, TPM, smart card hoặc thiết bị chuyên dụng.
- Private key có được phép export hay phải non-exportable.
- Thời hạn chứng thư, cryptoperiod của khóa và thời điểm bắt đầu renewal.
- Ai được yêu cầu, phê duyệt, sử dụng, backup, phục hồi và hủy.
- Dữ liệu hoặc chữ ký nào sẽ phụ thuộc vào khóa trong thời gian dài.

Không nên dùng một cặp khóa cho nhiều mục đích khác nhau nếu policy hoặc mô hình đe dọa yêu cầu tách biệt. Chẳng hạn, khóa ký số và khóa giải mã có quyền hạn cũng như nhu cầu lưu giữ khác nhau. Tách mục đích giúp giới hạn tác động khi một khóa bị lộ hoặc cần hủy.

## 4. Tạo private key an toàn

Private key phải được tạo bằng bộ sinh số ngẫu nhiên mật mã (CSPRNG) và thuật toán được phê duyệt. Không tự tạo khóa bằng timestamp, chuỗi dễ đoán, dữ liệu người dùng hoặc random generator thông thường.

Các lựa chọn lưu giữ phổ biến:

| Môi trường | Đặc điểm | Khi phù hợp |
|---|---|---|
| Software keystore | Khóa được bảo vệ bằng quyền hệ điều hành và cơ chế mã hóa của kho | Ứng dụng có mức rủi ro phù hợp và kiểm soát host tốt |
| HSM | Khóa có thể được tạo và sử dụng bên trong thiết bị; hỗ trợ policy và kiểm soát phần cứng | Khóa CA, ký số quan trọng hoặc workload có yêu cầu bảo vệ cao |
| TPM | Khóa được gắn với phần cứng và trạng thái thiết bị theo khả năng nền tảng | Danh tính thiết bị, boot hoặc workload cục bộ |
| Smart card/token | Khóa được giữ trong thiết bị người dùng, thao tác có thể yêu cầu PIN hoặc xác nhận | Chữ ký cá nhân và xác thực người dùng |
| Cloud KMS/HSM | Dịch vụ quản lý tạo, lưu, sử dụng và policy của khóa | Hệ thống cloud cần kiểm soát tập trung và audit |

Ưu tiên tạo private key ngay trong HSM hoặc thiết bị bảo vệ khóa khi cần bảo đảm khóa không thể export. Nếu cần export, phải dùng cơ chế wrapping hoặc backup được nền tảng hỗ trợ, mã hóa bằng khóa bảo vệ độc lập và giới hạn người có quyền mở bản sao.

Private key không được đưa vào source code, image container, file cấu hình công khai, ticket, chat hoặc log. Quyền đọc file và quyền gọi thao tác ký/giải mã cần được xem xét riêng: một ứng dụng có thể được phép yêu cầu HSM ký mà không được phép lấy private key ra ngoài.

## 5. Enrollment: CSR và xác minh danh tính

Certificate Signing Request (CSR) thường chứa public key, subject, SAN và các thông tin yêu cầu khác. CSR được ký bằng private key tương ứng để chứng minh người yêu cầu đang nắm giữ khóa riêng. CSR không chứa private key.

Quy trình enrollment:

1. Tạo key pair trong môi trường đã được phê duyệt.
2. Tạo CSR từ public key và thông tin danh tính cần chứng nhận.
3. Gửi CSR qua cổng hoặc API của CA.
4. Xác minh quyền kiểm soát tên miền, tổ chức, thiết bị hoặc danh tính người yêu cầu.
5. CA kiểm tra policy, profile, thuật toán và các ràng buộc.
6. CA chấp thuận hoặc từ chối yêu cầu và ghi lại quyết định.

Với chứng thư TLS công khai, CA có thể yêu cầu DNS challenge hoặc HTTP challenge để xác minh quyền kiểm soát tên miền. Với PKI nội bộ, quy trình có thể yêu cầu ticket, owner approval hoặc xác nhận của quản trị viên PKI.

Người yêu cầu không được tự quyết định danh tính ngoài phạm vi được ủy quyền. CA phải áp dụng profile phù hợp để tránh cấp chứng thư có SAN, EKU hoặc quyền sử dụng vượt quá nhu cầu.

## 6. Issuance: cấp và kiểm tra chứng thư

Sau khi xác minh, CA tạo chứng thư mới và ký bằng CA private key. Chứng thư thường có serial number, issuer, subject, public key, thời hạn, Key Usage, Extended Key Usage (EKU), Basic Constraints và chữ ký CA.

Trước khi triển khai, owner cần kiểm tra:

- Subject và SAN đúng với dịch vụ hoặc chủ thể.
- Public key trong chứng thư khớp với private key đã tạo.
- Issuer và chain dẫn tới trust anchor được chấp nhận.
- Not Before và Not After phù hợp với kế hoạch.
- Key Usage và EKU phù hợp mục đích.
- Thuật toán, độ dài khóa và certificate policy đáp ứng yêu cầu.
- Serial number và fingerprint được ghi vào inventory.

Chứng thư được phát hành thành công không có nghĩa nó đã được triển khai đúng. Nếu chứng thư không khớp private key, ứng dụng không thể thực hiện thao tác cần thiết. Nếu chain thiếu intermediate hoặc client không tin cậy CA, kết nối có thể thất bại.

## 7. Provisioning và phân phối

Provisioning là quá trình đưa certificate, chain và tham chiếu tới private key vào đúng dịch vụ, thiết bị hoặc người dùng. Cần bảo đảm chứng thư được gắn với đúng key handle hoặc private key, đúng môi trường và đúng endpoint.

Các nguyên tắc:

- Phân phối chứng thư công khai và chain qua kênh xác thực.
- Không gửi private key cùng certificate cho các bên chỉ cần xác minh.
- Nếu cần chuyển private key, dùng cơ chế export/wrapping được phê duyệt và truyền qua kênh bảo mật.
- Giới hạn quyền đọc và sử dụng private key theo service identity.
- Kiểm soát quyền ghi keystore, secret volume và cấu hình TLS.
- Triển khai theo phiên bản, có kiểm tra tính toàn vẹn và khả năng rollback.
- Với cluster, xác minh tất cả node và vùng đều dùng đúng cặp certificate/private key.

Với mTLS, mỗi bên có thể cần certificate và private key riêng. Trust store của mỗi bên chứa trust anchor để xác minh chứng thư peer. Không nhầm trust store với nơi lưu private key của chính workload.

## 8. Active use: sử dụng private key và certificate

Private key chỉ nên được sử dụng cho mục đích đã được phê duyệt. Ứng dụng có thể gọi thao tác ký hoặc giải mã thông qua HSM/KMS mà không đọc key material. Mỗi lần sử dụng quan trọng cần gắn với principal, key ID, operation và audit record.

Một số ví dụ:

| Mục đích | Cách sử dụng private key | Vai trò certificate |
|---|---|---|
| TLS server authentication | Ký dữ liệu handshake theo giao thức và bộ mật mã được thương lượng | Cung cấp danh tính server và public key cho client |
| TLS client authentication | Chứng minh danh tính client trong mTLS | Cho server xác minh client certificate và chain |
| Code signing | Ký hash của artifact hoặc gói phần mềm | Liên kết public key với publisher và chính sách ký |
| Document signing | Ký dữ liệu tài liệu hoặc hash theo chuẩn chữ ký | Cung cấp danh tính người ký và thông tin xác minh |
| Decryption | Thực hiện thao tác giải mã theo thuật toán | Cung cấp public key và danh tính liên quan; tùy hệ thống, certificate có thể phục vụ trao đổi khóa |

Trong TLS 1.3, certificate private key thường dùng để ký xác thực handshake. Khóa mã hóa dữ liệu phiên được thiết lập từ cơ chế trao đổi khóa, thường là ephemeral Diffie-Hellman; không nên mô tả private key của certificate như khóa trực tiếp mã hóa toàn bộ lưu lượng TLS.

Khi sử dụng, ứng dụng cần kiểm tra chain, hostname hoặc danh tính peer, thời hạn, mục đích và trạng thái thu hồi theo policy. Certificate hợp lệ về chữ ký không tự động cấp quyền nghiệp vụ cho chủ thể; authorization vẫn là quyết định riêng của ứng dụng.

## 9. Monitoring và quản lý inventory

Một hệ thống quản lý vòng đời cần biết chứng thư và private key đang ở đâu, ai chịu trách nhiệm và trạng thái hiện tại là gì.

Inventory nên ghi:

- Certificate ID, serial number, fingerprint, issuer và chain.
- Subject, SAN, Key Usage, EKU và certificate policy.
- Not Before, Not After và trạng thái renewal.
- Public key algorithm, key size/curve và fingerprint.
- Key ID hoặc HSM object reference tương ứng với private key.
- Vị trí lưu, môi trường, endpoint, application owner và technical owner.
- Key generation time, cryptoperiod, lần rotation gần nhất và trạng thái export.
- Quyền sử dụng, backup/escrow, tham chiếu dữ liệu phụ thuộc và trạng thái destruction.

Theo dõi cả chứng thư trong inventory và chứng thư endpoint thực sự trình bày. Sự khác biệt có thể chỉ ra rollout chưa hoàn tất, node cũ chưa được cập nhật hoặc một thiết bị vẫn dùng certificate đã hết hạn.

Thiết lập cảnh báo trước khi certificate hết hạn và theo dõi dấu hiệu private key bị sử dụng bất thường. Cảnh báo cần gắn với owner và quy trình xử lý, không chỉ tạo thông báo chung trong hệ thống giám sát.

## 10. Renewal và key rotation

Certificate renewal là cấp chứng thư mới để thay thế hoặc tiếp nối chứng thư hiện tại. Key rotation là thay cặp khóa hoặc chuyển sang key version mới. Hai thao tác có thể diễn ra cùng nhau nhưng không đồng nghĩa.

| Trường hợp | Certificate | Private key |
|---|---|---|
| Renewal giữ key pair | Chứng thư mới được cấp cho public key hiện tại | Tiếp tục dùng private key cũ |
| Renewal có rekey | Chứng thư mới gắn với public key mới | Tạo và triển khai private key mới |
| Reissue | CA cấp lại chứng thư theo thay đổi hoặc lỗi | Có thể giữ hoặc thay khóa tùy nguyên nhân |
| Compromise response | Chứng thư cũ cần được revoke theo policy | Tạo khóa mới và cô lập/hủy khóa bị lộ sau khi xử lý điều tra |

Quy trình rotation nên gồm:

1. Tạo key pair mới bằng cơ chế an toàn.
2. Tạo CSR và yêu cầu CA cấp certificate mới.
3. Kiểm tra public key, SAN, EKU, validity và chain.
4. Phân phối certificate mới cùng tham chiếu private key mới.
5. Triển khai theo đợt và kiểm thử từ client thực tế.
6. Xác nhận mọi endpoint đã dùng key pair mới.
7. Retire hoặc revoke certificate cũ theo tình trạng.
8. Xử lý private key cũ theo nhu cầu giải mã, xác minh và retention.

Nếu có certificate pinning, thiết bị ngoại tuyến hoặc đối tác cố định fingerprint, cần phối hợp cập nhật trước khi chuyển đổi. Không xóa key pair cũ trước khi xác nhận mọi hệ thống phụ thuộc đã chuyển sang phiên bản mới hoặc có kế hoạch lưu giữ hợp lệ.

## 11. Expiration, revocation và trạng thái khóa

Các trạng thái sau cần được phân biệt:

| Sự kiện | Ảnh hưởng đến certificate | Ảnh hưởng đến private key |
|---|---|---|
| Expiration | Chứng thư hết thời hạn; bên xác minh thường từ chối theo policy | Private key vẫn tồn tại và có thể vẫn thực hiện phép toán |
| Revocation | CA công bố chứng thư không còn đáng tin cậy trước hạn | Không tự động xóa hoặc zeroize private key |
| Disable key | Tùy nền tảng, thao tác sử dụng private key bị chặn | Key material thường vẫn còn và có thể bật lại |
| Key compromise | Certificate cần được xem xét revoke/distrust | Private key phải được cô lập, thay thế và xử lý theo incident response |
| Destruction | Chứng thư công khai có thể vẫn được lưu để kiểm tra lịch sử | Private key và mọi bản sao có thể phục hồi bị loại bỏ |

Certificate expiration không hủy private key. Revocation cũng không xóa key material. Nếu private key bị lộ, chỉ cấp chứng thư mới nhưng dùng lại public key cũ không khắc phục được rủi ro. Cần tạo cặp khóa mới và xử lý chứng thư cũ.

Trạng thái thu hồi có thể được phân phối qua CRL, OCSP hoặc cơ chế của nền tảng. Client phải có chính sách kiểm tra phù hợp; không phải mọi ứng dụng đều xử lý revocation giống nhau. Với CA root bị compromise, cần cập nhật trust store hoặc chính sách distrust; chỉ revoke leaf certificate có thể không đủ.

## 12. Backup và archival private key

Không phải private key nào cũng nên được backup. Quyết định phụ thuộc mục đích:

- **TLS server authentication key:** thường có thể tạo key pair mới khi thay thế; backup cần cân nhắc lợi ích phục hồi với rủi ro mở rộng số bản private key.
- **Code signing key:** backup có thể cần cho tính liên tục, nhưng phải được kiểm soát nghiêm ngặt vì có thể tạo chữ ký giả mạo.
- **Document signing key:** cần phân biệt việc giữ bằng chứng xác minh chữ ký với việc giữ private key để ký mới.
- **Decryption key:** có thể cần lưu giữ lâu dài để giải mã dữ liệu đã mã hóa trong quá khứ; hủy quá sớm có thể làm mất dữ liệu.
- **CA private key:** có phạm vi ảnh hưởng lớn, cần policy backup, HSM, dual control và kế hoạch disaster recovery riêng.

Nếu backup private key được cho phép:

1. Chỉ tạo bản sao qua cơ chế được phê duyệt.
2. Mã hóa hoặc wrap bằng backup key độc lập.
3. Lưu ở miền lỗi và miền quyền hạn tách biệt.
4. Áp dụng dual control hoặc M-of-N khi cần.
5. Ghi inventory, owner, vị trí, phiên bản và thời hạn lưu giữ.
6. Kiểm tra khả năng phục hồi định kỳ trong môi trường kiểm soát.
7. Hủy backup khi hết nhu cầu, đồng thời xử lý backup wrapping key theo dependency.

Archival không có nghĩa là tiếp tục cho phép sử dụng private key. Khóa được lưu để giải mã dữ liệu cũ phải có policy chỉ cho phép decrypt, giới hạn người truy cập và ghi audit. Khóa ký đã nghỉ hưu thường không nên tiếp tục có quyền ký mới.

Để xác minh chữ ký lịch sử, tổ chức thường cần giữ public certificate, certificate chain, trạng thái thu hồi tại thời điểm liên quan, timestamp và dữ liệu kiểm chứng. Việc xác minh chữ ký không đòi hỏi giữ private key của người ký.

## 13. Xử lý private key bị compromise

Khi nghi ngờ private key bị lộ, cần coi đây là sự cố bảo mật. Mục tiêu là ngăn sử dụng tiếp, xác định phạm vi và thiết lập danh tính mật mã mới.

1. Cô lập host, token, HSM partition hoặc tài khoản có thể đã bị xâm phạm.
2. Chặn thao tác ký/giải mã hoặc quyền sử dụng khóa theo mức khẩn cấp.
3. Xác định thời điểm, nguồn, bản sao và đối tượng có thể đã truy cập private key.
4. Tìm các certificate, service, artifact, dữ liệu hoặc chữ ký phụ thuộc.
5. Tạo key pair mới trong môi trường tin cậy.
6. Yêu cầu CA cấp certificate mới và triển khai lên mọi endpoint.
7. Revoke certificate cũ và cập nhật CRL/OCSP hoặc trust policy theo quy trình.
8. Đánh giá dữ liệu đã mã hóa, chữ ký đã tạo và khả năng giả mạo trong thời gian bị lộ.
9. Bảo toàn bằng chứng điều tra theo quyền hạn; không tiếp tục phát tán private key.
10. Hủy key material và các bản sao bị compromise sau khi xử lý yêu cầu điều tra/lưu giữ được phê duyệt.

Đối với khóa ký, kẻ tấn công có thể tạo chữ ký giả trong thời gian private key bị kiểm soát. Đối với khóa giải mã, kẻ tấn công có thể đọc ciphertext đã thu thập nếu có đủ dữ liệu cần thiết. Việc thay khóa không thể làm dữ liệu đã bị giải mã hoặc sao chép trước đó trở lại bí mật.

## 14. Destruction: hủy private key đúng cách

Private key cần được hủy khi hết nhu cầu hợp lệ, hết thời hạn lưu giữ hoặc sau khi thay thế/ứng phó sự cố theo policy. Hủy phải bao gồm mọi bản có thể phục hồi:

- Key object trong KMS/HSM hoặc thiết bị bảo vệ.
- File keystore, bản export và bản sao trong máy chủ.
- Backup, replica, escrow và bản lưu ngoại tuyến.
- Cache, bộ nhớ tạm, crash dump và các tiến trình có thể còn giữ key material.
- Bản wrapping hoặc khóa bảo vệ backup có thể mở lại private key.

Với HSM, dùng thao tác xóa object hoặc zeroization đúng phạm vi theo hướng dẫn nhà cung cấp. Không zeroize toàn bộ thiết bị hoặc security domain nếu yêu cầu chỉ liên quan đến một key object. Với KMS, phân biệt disable, pending deletion và destruction hoàn tất; một yêu cầu xóa đang chờ chưa chứng minh key material đã bị hủy.

Với private key trong phần mềm, xóa file thông thường không bảo đảm dữ liệu biến mất khỏi snapshot, journal, SSD hoặc backup. Dùng cơ chế sanitization của nền tảng và xử lý tất cả bản sao theo chính sách.

Trước khi hủy, xác nhận dữ liệu còn phụ thuộc đã được chuyển đổi hoặc hết nhu cầu, không có legal hold và không còn yêu cầu giải mã lịch sử. Sau khi hủy, lưu bằng chứng gồm key ID, phiên bản, người phê duyệt, người thực hiện, thời điểm, phạm vi bản sao và kết quả xác minh; không lưu private key trong bằng chứng.

## 15. Certificate lifecycle và private key lifecycle theo loại sử dụng

| Loại | Certificate lifecycle | Private key lifecycle |
|---|---|---|
| TLS server | Cấp, triển khai, theo dõi hạn, renew/revoke | Tạo, bảo vệ, dùng để xác thực handshake, rotate và hủy |
| mTLS workload | Cấp tự động theo workload identity, thời hạn thường ngắn, renew liên tục | Tạo và rotate theo workload; hạn chế export và thu hồi khi workload bị loại bỏ |
| Code signing | Cấp theo publisher, kiểm tra policy, renew hoặc revoke khi cần | Giữ trong HSM/token, kiểm soát phê duyệt ký, backup rất hạn chế và hủy khi hết nhu cầu |
| Document signing | Chứng thư liên kết người ký, có thể cần timestamp và bằng chứng dài hạn | Kiểm soát quyền ký; giữ private key chỉ khi còn nhu cầu ký hợp lệ |
| Decryption | Chứng thư có thể hỗ trợ phân phối public key và định danh | Có thể phải archive private key để giải mã dữ liệu cũ theo retention |
| CA | CA certificate xác định issuer và chain tin cậy | CA private key có phạm vi rất lớn; cần HSM, ceremony, backup và destruction đặc biệt |

Đặc biệt, CA private key không được quản lý như private key leaf thông thường. Compromise CA key có thể làm mất niềm tin vào nhiều chứng thư đã phát hành. Việc tạo, backup, rotation, revoke và destruction của CA key cần quy trình PKI riêng, phân quyền nhiều bên và kế hoạch thay trust anchor.

## 16. Ví dụ: vòng đời chứng thư TLS của một API

Một API doanh nghiệp dùng certificate với SAN là api.example.com. Private key được tạo trong HSM và không export được.

1. Owner xác nhận tên miền, mục đích TLS server và thời hạn chứng thư.
2. HSM tạo key pair; public key được dùng để tạo CSR.
3. CA xác minh quyền kiểm soát tên miền và phát hành certificate.
4. Nhóm vận hành kiểm tra SAN, EKU, validity, chain và public key khớp HSM key handle.
5. Certificate và intermediate chain được triển khai lên load balancer; private key vẫn nằm trong HSM.
6. Monitoring theo dõi expiry và endpoint thực tế.
7. Trước hạn, hệ thống tạo key pair mới trong HSM, yêu cầu certificate mới và triển khai theo đợt.
8. Sau khi mọi node phục vụ certificate mới, certificate cũ được retire; nếu có compromise thì revoke.
9. Private key cũ được hủy theo policy sau khi xác nhận không còn nhu cầu hợp lệ.
10. Inventory và audit log ghi nhận key ID cũ/mới, certificate serial, người phê duyệt và kết quả.

Ví dụ này cho thấy certificate có thể được phân phối tới nhiều endpoint trong khi private key không cần rời HSM. Khi rekey, cả certificate và key reference phải được cập nhật đồng bộ.

## 17. Checklist quản lý vòng đời

- [ ] Đã xác định owner, danh tính, mục đích và policy cho certificate/key pair.
- [ ] Private key được tạo bằng CSPRNG và thuật toán được phê duyệt.
- [ ] Đã chọn môi trường lưu phù hợp; quyền export được giới hạn.
- [ ] CSR chỉ chứa public key và thông tin yêu cầu, không chứa private key.
- [ ] CA đã xác minh danh tính và phát hành đúng profile.
- [ ] Certificate khớp private key, SAN, EKU, validity và chain đều hợp lệ.
- [ ] Certificate và key reference được triển khai đúng endpoint.
- [ ] Quyền sử dụng private key và audit được kiểm soát.
- [ ] Inventory và cảnh báo expiry/rotation được cập nhật.
- [ ] Renewal/rekey được kiểm thử trên mọi endpoint và client liên quan.
- [ ] Revocation và compromise response có runbook.
- [ ] Backup/archival có lý do, quyền hạn, wrapping và retention rõ ràng.
- [ ] Private key cũ được giữ hoặc hủy theo mục đích, không theo trạng thái certificate đơn thuần.
- [ ] Destruction bao gồm backup, replica, escrow và mọi bản có thể phục hồi.

Certificate và private key lifecycle cần được quản lý như hai luồng tài sản có liên kết. Chứng thư xác nhận danh tính và public key; private key cung cấp khả năng thực hiện thao tác mật mã. Gia hạn chứng thư không tự động thay private key, hết hạn hoặc revoke chứng thư không tự động hủy private key, và hủy private key không xóa các chứng thư công khai đã phát hành. Khi tổ chức theo dõi rõ mục đích, quyền, phiên bản, phụ thuộc, retention và bằng chứng ở từng giai đoạn, hệ thống có thể duy trì xác thực đáng tin cậy, giảm thời gian phơi nhiễm khóa và kết thúc vòng đời an toàn.

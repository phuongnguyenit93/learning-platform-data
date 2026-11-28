# Risk-based cryptoperiod: Xác định thời hạn sử dụng khóa dựa trên rủi ro

**Risk-based cryptoperiod** là cách xác định thời hạn một khóa mật mã được phép thực hiện các thao tác bảo vệ mới dựa trên mức rủi ro của khóa, dữ liệu, thuật toán, khối lượng sử dụng và môi trường vận hành. Thay vì áp dụng cùng một chu kỳ cho mọi khóa, tổ chức đánh giá từng loại khóa và đặt giới hạn phù hợp với tác động nếu khóa bị lộ, bị phân tích, bị sử dụng sai hoặc không còn đáp ứng yêu cầu an toàn.

Cryptoperiod là một phần của key policy. Nó quy định khoảng thời gian khóa được phép sử dụng cho một hoặc nhiều mục đích mật mã. Khi khoảng này kết thúc, khóa có thể phải ngừng tạo bản mã hoặc chữ ký mới, chuyển sang trạng thái chỉ giải mã/xác minh, được thay bằng phiên bản mới, hoặc bị thu hồi theo chính sách. Việc kết thúc cryptoperiod không đồng nghĩa phải hủy ngay key material: dữ liệu cũ, chữ ký lịch sử, bản backup và bản mã lưu trữ có thể vẫn cần khóa cũ.

Trong quản lý khóa mật mã, xác định cryptoperiod phải cân bằng rủi ro mật mã với khả năng vận hành và yêu cầu lưu giữ dữ liệu. Chu kỳ quá dài làm tăng thời gian và khối lượng dữ liệu có thể bị ảnh hưởng nếu khóa bị lộ. Chu kỳ quá ngắn làm tăng số lần chuyển đổi, nguy cơ lỗi triển khai, chi phí và khả năng mất khả năng giải mã nếu quy trình giữ khóa cũ không được thiết kế đúng.

## 1. Cryptoperiod là gì?

**Cryptoperiod** là khoảng thời gian mà một khóa được phép sử dụng cho mục đích mật mã đã xác định. Khoảng này thường được tính từ lúc khóa được kích hoạt hoặc bắt đầu sử dụng đến thời điểm ngừng sử dụng theo policy. Một khóa có thể có thời hạn theo lịch, giới hạn theo số lần sử dụng, giới hạn theo lượng dữ liệu đã xử lý hoặc kết hợp nhiều điều kiện.

Ví dụ, một DEK có thể được dùng để mã hóa dữ liệu của một đối tượng trong một khoảng thời gian hoặc cho đến khi đạt giới hạn số bản ghi. Một khóa ký có thể được phép ký artifact mới trong một giai đoạn; sau đó private key ngừng ký nhưng public key vẫn được giữ để xác minh chữ ký đã tạo trước đó. Một KEK có thể ngừng wrap DEK mới nhưng vẫn cần unwrap những DEK cũ cho đến khi dữ liệu được rewrap hoặc hết thời hạn lưu giữ.

Cryptoperiod không phải là một thuộc tính thời gian duy nhất áp dụng cho mọi thao tác của khóa. Cần mô tả rõ thao tác nào được phép trong từng giai đoạn.

## 2. Phân biệt các khoảng sử dụng khóa

Trong thực tế, cần phân biệt thời gian khóa được dùng để tạo bảo vệ mới và thời gian khóa còn cần thiết để xử lý dữ liệu đã được bảo vệ:

| Khoảng | Ý nghĩa | Ví dụ |
|---|---|---|
| Originator-usage period | Khoảng thời gian chủ thể được phép dùng khóa để tạo bảo vệ mật mã mới. | Encrypt dữ liệu mới, ký thông điệp mới hoặc tạo MAC mới. |
| Recipient-usage period | Khoảng thời gian khóa còn được phép dùng để xử lý dữ liệu đã được bảo vệ trước đó. | Decrypt ciphertext cũ, verify chữ ký hoặc kiểm tra MAC cũ. |
| Activation period | Khoảng thời gian khóa đã được tạo và được phép bắt đầu sử dụng theo trạng thái hệ thống. | Key version được KMS bật và cấp grant cho workload. |
| Retention period | Khoảng thời gian phải giữ khóa hoặc khả năng truy cập khóa để xử lý dữ liệu, chữ ký hay backup còn lưu. | Giữ khóa giải mã archive trong thời gian lưu trữ hồ sơ. |
| Recovery/backup retention | Khoảng thời gian bản backup và phương tiện phục hồi phải được bảo vệ, sẵn sàng. | Giữ HSM backup và recovery shares theo chính sách DR. |

Originator-usage period và recipient-usage period có thể khác nhau. Khi khóa ký hết thời gian được phép ký, private key có thể bị disable cho thao tác sign, nhưng public key/certificate vẫn cần để xác minh chữ ký cũ. Với khóa mã hóa, việc ngừng encrypt bằng phiên bản cũ không có nghĩa được xóa khóa ngay; ứng dụng có thể còn phải decrypt dữ liệu đã mã hóa bằng phiên bản đó.

Một key policy nên thể hiện các mốc này riêng biệt, tránh một trường expiresAt duy nhất bị hiểu nhầm là mọi thao tác phải dừng hoặc key material phải bị hủy tại cùng thời điểm.

## 3. Vì sao cryptoperiod phải dựa trên rủi ro?

Mỗi khóa có mức phơi nhiễm và hậu quả khác nhau. Một khóa dùng một lần cho dữ liệu tạm thời có bối cảnh khác với khóa gốc CA, khóa ký phát hành phần mềm hoặc KEK bảo vệ hàng triệu DEK.

Cryptoperiod dựa trên rủi ro giúp:

- Giới hạn lượng dữ liệu và số thao tác chịu ảnh hưởng nếu khóa bị lộ.
- Giảm thời gian kẻ tấn công có thể sử dụng một khóa đã đánh cắp.
- Thích ứng với thuật toán, key size và tiến bộ phân tích mật mã.
- Đáp ứng thời hạn lưu giữ, yêu cầu pháp lý, tiêu chuẩn và cam kết với khách hàng.
- Ưu tiên nguồn lực rotation cho các khóa có tác động lớn.
- Giữ khả năng giải mã/xác minh dữ liệu cũ trong khi chuyển sang khóa mới.
- Tạo cơ sở giải trình vì sao một loại khóa có chu kỳ ngắn hoặc dài hơn loại khác.

Không có một số ngày cố định phù hợp cho mọi loại khóa, thuật toán và môi trường. Chu kỳ phải dựa trên tiêu chuẩn áp dụng, khuyến nghị của nhà cung cấp, giới hạn thuật toán, mô hình đe dọa và khả năng triển khai đã được kiểm thử.

## 4. Các yếu tố quyết định cryptoperiod

### Giá trị và độ nhạy của dữ liệu

Dữ liệu tài chính, định danh, sức khỏe, bí mật kinh doanh hoặc dữ liệu chịu quy định thường có hậu quả lớn nếu bị giải mã trái phép. Dữ liệu cần giữ bí mật trong nhiều năm cũng tạo yêu cầu khác với dữ liệu phiên có vòng đời ngắn.

Nếu kẻ tấn công có thể lưu ciphertext hôm nay và chờ đến khi thuật toán hoặc khóa yếu đi trong tương lai, thời hạn cần bảo vệ dữ liệu phải được xem xét cùng tuổi thọ bí mật của dữ liệu. Thời gian lưu trữ dài có thể đòi hỏi thuật toán mạnh hơn, key size phù hợp, kế hoạch crypto-agility và bảo vệ key version lâu dài.

### Thuật toán và độ dài khóa

Cryptoperiod chịu ảnh hưởng bởi mức an toàn của thuật toán, key size, cấu hình và tiến bộ mật mã. Thuật toán bị suy yếu, tham số không còn được khuyến nghị hoặc thư viện/provider sắp ngừng hỗ trợ có thể buộc tổ chức rút ngắn thời hạn hoặc thay khóa sớm.

Không thể kéo dài cryptoperiod chỉ bằng cách dùng khóa lớn nếu thuật toán, mode, nonce handling hoặc triển khai có lỗi. Ngược lại, một thuật toán còn được xem là an toàn vẫn có thể cần rotation sớm nếu khóa bị truy cập bởi quá nhiều principal hoặc xử lý khối lượng dữ liệu quá lớn.

### Khối lượng dữ liệu và số lần sử dụng

Một khóa càng xử lý nhiều dữ liệu hoặc nhiều phép toán thì mức phơi nhiễm và một số rủi ro thống kê càng tăng. Với AEAD như AES-GCM, giới hạn số lần mã hóa, tổng lượng dữ liệu và tính duy nhất của nonce là điều kiện an toàn quan trọng. Không được dùng một ngưỡng số byte hoặc số lần gọi chung cho mọi cấu hình; phải tuân thủ giới hạn của chuẩn, thư viện và provider cụ thể.

Theo dõi số lần encrypt/sign/MAC, tổng byte, số nonce đã dùng, số đối tượng được bảo vệ và số tenant sử dụng khóa. Một khóa có thể đến giới hạn theo lượng dữ liệu trước khi đạt ngày hết hạn theo lịch.

### Mức độ phơi nhiễm và khả năng truy cập

Khóa nằm trong HSM không exportable, chỉ có một service identity được gọi sign, có audit và phê duyệt thường có bối cảnh khác khóa phần mềm được phân phối tới nhiều máy chủ. Các yếu tố làm tăng phơi nhiễm gồm:

- Private key hoặc symmetric key có thể export.
- Key material tồn tại trong heap, file tạm, snapshot hoặc dump.
- Nhiều người hoặc workload có quyền sử dụng.
- Quyền decrypt/sign quá rộng hoặc thiếu separation of duties.
- Khóa được dùng chung giữa nhiều ứng dụng hoặc tenant.
- Thiếu audit, phát hiện bất thường hoặc kiểm soát phiên truy cập.
- Nhà cung cấp, thiết bị hoặc môi trường lưu trữ có mức bảo đảm thấp hơn yêu cầu.

Khóa có phạm vi sử dụng rộng hoặc dễ bị truy cập trái phép thường cần chu kỳ ngắn hơn, kiểm soát mạnh hơn hoặc tách thành nhiều khóa nhỏ theo tenant/purpose.

### Tác động khi khóa bị compromise

Đánh giá hậu quả nếu khóa bị lộ:

- Có thể giải mã một bản ghi, một tenant hay toàn bộ kho dữ liệu?
- Có thể giả mạo chữ ký phần mềm, chứng thư hoặc giao dịch không?
- Có thể tạo MAC hợp lệ hoặc mạo danh dịch vụ?
- Có thể mở gói nhiều DEK hoặc backup key không?
- Khóa có quyền ở production, môi trường quản trị hoặc hạ tầng PKI không?
- Có thể phát hiện việc sử dụng trái phép trong bao lâu?

Khóa có blast radius lớn cần được ưu tiên bảo vệ, theo dõi và rotation. Một cryptoperiod dài chỉ có thể được cân nhắc khi có lý do rõ ràng, ranh giới bảo vệ mạnh và phương án xử lý sự cố phù hợp.

### Khả năng vận hành và phụ thuộc

Rotation không đơn giản là tạo khóa mới. Hệ thống phải cập nhật ứng dụng, phân phối public key/certificate, rewrap DEK hoặc re-encrypt dữ liệu, giữ khóa cũ để xử lý dữ liệu lịch sử và xác minh mọi replica.

Nếu hệ thống chưa có khả năng triển khai khóa mới an toàn, việc đặt chu kỳ quá ngắn có thể tạo lỗi thường xuyên. Điều này không phải lý do để bỏ qua rủi ro; nó là tín hiệu cần đầu tư vào automation, inventory, versioning, reconciliation và recovery.

### Tiêu chuẩn, hợp đồng và khuyến nghị nhà cung cấp

Các tiêu chuẩn hoặc quy định có thể quy định thời hạn tối đa, thuật toán, key size, cách quản lý vòng đời hoặc bằng chứng kiểm toán. Dịch vụ KMS/HSM cũng có thể áp dụng giới hạn số lần sử dụng, thời gian hoặc loại thao tác. Tổ chức cần xác định yêu cầu bắt buộc cho từng phạm vi và áp dụng giới hạn chặt nhất có liên quan.

Không dùng ví dụ trong tài liệu này thay cho yêu cầu hiện hành của tiêu chuẩn, hợp đồng hoặc hướng dẫn nhà cung cấp. Khi có nhiều yêu cầu, ghi rõ nguồn và phiên bản để có thể rà soát khi chúng thay đổi.

## 5. Ma trận rủi ro để xác định cryptoperiod

Một phương pháp thực tế là đánh giá likelihood và impact, sau đó chọn mức kiểm soát và giới hạn sử dụng. Có thể dùng thang điểm nội bộ để phân loại, nhưng điểm số chỉ hỗ trợ quyết định; không thay thế phân tích mật mã hoặc giới hạn bắt buộc.

| Yếu tố | Rủi ro thấp hơn | Rủi ro cao hơn |
|---|---|---|
| Data sensitivity | Dữ liệu công khai hoặc ít nhạy cảm. | Dữ liệu mật, tài chính, định danh hoặc chịu quy định. |
| Data retention | Vòng đời ngắn, dễ loại bỏ. | Lưu trữ nhiều năm hoặc cần xác minh lâu dài. |
| Key exposure | Không exportable trong HSM, principal rất hạn chế. | Key phần mềm, nhiều bản sao, nhiều principal truy cập. |
| Usage volume | Ít phép toán, dữ liệu ít, giới hạn được theo dõi. | Khối lượng lớn, tần suất cao hoặc gần giới hạn thuật toán. |
| Blast radius | Một workload hoặc một đối tượng. | Nhiều tenant, hệ thống hoặc dữ liệu quan trọng. |
| Algorithm status | Thuật toán và tham số còn được phê duyệt. | Thuật toán yếu, tham số lỗi thời hoặc sắp bị loại bỏ. |
| Monitoring | Có audit, phát hiện và phản ứng nhanh. | Thiếu visibility hoặc thời gian phát hiện dài. |
| Rotation readiness | Automation và rollback đã được kiểm thử. | Thao tác thủ công, phụ thuộc không rõ hoặc chưa có recovery. |

Ví dụ phân loại:

- **Thấp:** khóa dùng trong môi trường thử nghiệm, dữ liệu không nhạy cảm, không có dependency lâu dài.
- **Trung bình:** DEK của một dịch vụ nội bộ, quyền hạn chế, volume có thể đo và rotation tự động.
- **Cao:** KEK production bảo vệ nhiều DEK, khóa ký artifact hoặc khóa mTLS dùng rộng trong hạ tầng.
- **Rất cao:** CA root/intermediate, khóa ký firmware/phát hành, backup master key hoặc khóa có khả năng mở dữ liệu quy mô lớn.

Mức phân loại phải được xác nhận với owner và security function. Không suy ra rằng khóa trong HSM luôn có rủi ro thấp: một khóa HSM có quyền sign mọi artifact phát hành vẫn có tác động rất lớn nếu principal gọi khóa bị chiếm quyền.

## 6. Phương pháp xây dựng cryptoperiod

Có thể thực hiện theo quy trình sau:

1. **Inventory:** xác định key ID/version, loại khóa, owner, purpose, môi trường và dữ liệu phụ thuộc.
2. **Phân loại:** xác định mức nhạy cảm, retention, blast radius và mức độ quan trọng.
3. **Kiểm tra mật mã:** xem thuật toán, key size, mode, nonce policy, provider và giới hạn sử dụng.
4. **Đánh giá phơi nhiễm:** xem exportability, principal, vị trí lưu, logging, HSM/KMS và khả năng phát hiện compromise.
5. **Thu thập giới hạn:** lấy yêu cầu từ tiêu chuẩn, hợp đồng, key policy, vendor và thuật toán.
6. **Đặt giới hạn trên:** xác định tuổi tối đa và giới hạn số lần/khối lượng sử dụng nếu có.
7. **Chọn trigger rotation:** theo thời gian, số thao tác, lượng dữ liệu, sự kiện hoặc kết hợp.
8. **Xác định giai đoạn sau rotation:** quyền encrypt/sign mới, decrypt/verify cũ, retention và ngày hủy.
9. **Kiểm thử:** thử rotation, rollback, recovery và xử lý dữ liệu lịch sử.
10. **Phê duyệt và rà soát:** ghi lý do, người chịu trách nhiệm, nguồn tiêu chuẩn và thời điểm xem xét lại.

Cryptoperiod nên là giới hạn tối đa, không phải lịch cứng khiến hệ thống bỏ qua tín hiệu compromise. Nếu có dấu hiệu khóa bị lộ, lỗi thuật toán hoặc nonce reuse, phải kích hoạt quy trình khẩn cấp ngay cả khi khóa mới chỉ được tạo gần đây.

## 7. Trigger rotation: thời gian, volume và sự kiện

Không nên chỉ dùng ngày hết hạn để quyết định rotation. Kết hợp nhiều trigger giúp phản ứng phù hợp với cách khóa thực sự được sử dụng:

| Trigger | Ví dụ | Hành động |
|---|---|---|
| Age-based | Đạt tuổi tối đa theo key profile. | Tạo version mới và chuyển sang dùng cho bảo vệ mới. |
| Usage-based | Đạt giới hạn số lần gọi hoặc tổng byte theo thuật toán/provider. | Ngừng dùng cho thao tác mới và rotate. |
| Event-based | Nhân sự rời nhóm, principal bị compromise, thay đổi trust boundary. | Rà soát quyền và rotate nếu mức phơi nhiễm thay đổi. |
| Algorithm-based | Thuật toán hoặc key size bị loại khỏi danh sách phê duyệt. | Chuyển sang thuật toán/khóa mới theo kế hoạch crypto-agility. |
| Incident-based | Nghi ngờ lộ key material, export bất thường hoặc HSM bị xâm nhập. | Kích hoạt emergency rotation/rekey và incident response. |
| Dependency-based | CA, HSM, KMS account hoặc wrapping hierarchy sắp thay đổi. | Chuyển khóa và dependency trước khi mất hỗ trợ. |

Với khóa mã hóa AEAD, giới hạn usage phải tính theo quy tắc của mode và implementation, bao gồm nonce uniqueness, số invocation và lượng dữ liệu. Với khóa ký, theo dõi số lượng chữ ký, mục đích ký, principal và nguy cơ lạm dụng. Với KEK, theo dõi số DEK được wrap/unwrap và phạm vi dữ liệu được bảo vệ.

## 8. Cryptoperiod theo từng loại khóa

### Data Encryption Key (DEK)

DEK thường có phạm vi dữ liệu hẹp hơn KEK. Có thể dùng một DEK cho một đối tượng, một phiên hoặc một nhóm dữ liệu tùy kiến trúc. Phạm vi càng nhỏ thì blast radius khi lộ càng giới hạn.

Cryptoperiod của DEK cần xem xét:

- Lượng dữ liệu và số lần encrypt bằng cùng khóa.
- Mode mã hóa, nonce/IV và giới hạn thuật toán.
- Độ nhạy và thời hạn lưu giữ dữ liệu.
- Khả năng lưu wrapped DEK và metadata cùng ciphertext.
- Chi phí re-encrypt nếu cần thay khóa.

Với envelope encryption, khi DEK mới được dùng cho dữ liệu mới, wrapped DEK cũ có thể vẫn cần để giải mã dữ liệu cũ. Nếu DEK bị compromise, cần đánh giá re-encrypt dữ liệu bị ảnh hưởng; chỉ đổi KEK hoặc tạo DEK mới không làm ciphertext cũ tự an toàn trở lại.

### Key Encryption Key (KEK)

KEK bảo vệ nhiều DEK nên có thể có blast radius lớn. Cryptoperiod cần tính đến số DEK, tenant, hệ thống và backup phụ thuộc. Rotation KEK thường có thể thực hiện bằng cách unwrap rồi wrap lại DEK bằng KEK mới, nếu quy trình và policy cho phép.

Không hủy KEK cũ ngay sau khi tạo KEK mới. Chỉ retire hoặc destroy sau khi xác minh toàn bộ DEK, backup, replica và bản lưu trữ cần thiết đã được rewrap hoặc có phương án phục hồi hợp lệ.

### Khóa ký số

Private signing key dùng tạo chữ ký mới; public key dùng xác minh chữ ký đã tạo. Khi cryptoperiod của private key kết thúc, có thể ngừng sign bằng key version cũ nhưng vẫn giữ public key/certificate và metadata để xác minh chữ ký lịch sử.

Với code signing, firmware, tài liệu hoặc giao dịch có thời hạn xác minh dài, cần lưu certificate chain, timestamp, revocation evidence và policy tại thời điểm ký. Thay khóa ký không làm chữ ký cũ mất giá trị một cách tự động; cách đánh giá phụ thuộc trust policy, timestamp và trạng thái chứng thư.

### HMAC key

HMAC key thường được dùng cả tạo và xác minh MAC. Khi rotation, hệ thống có thể ngừng tạo MAC bằng key cũ nhưng tạm thời vẫn chấp nhận xác minh MAC cũ. Cần xác định thời hạn chấp nhận MAC cũ và tránh cho phép attacker kéo dài thời gian replay.

### TLS và mTLS private key

Private key của TLS server/client và thời hạn certificate là hai vấn đề liên quan nhưng khác nhau. Certificate có notAfter; private key có cryptoperiod theo key policy. Gia hạn certificate có thể dùng lại key pair hoặc tạo key pair mới tùy chính sách. Nếu private key bị compromise, phải rekey và xử lý revoke; chỉ renew certificate với cùng key không giải quyết được.

Session key trong TLS thường có vòng đời ngắn và được tạo theo handshake/key schedule. Không dùng cryptoperiod của certificate để suy ra thời hạn session key.

### CA key và khóa hạ tầng

CA root, intermediate, firmware signing hoặc backup master key thường có tác động rất rộng. Thời hạn sử dụng cần kết hợp kiểm soát HSM, quorum, ceremony, audit, backup/recovery và kế hoạch chuyển trust anchor. Rotation CA không chỉ tạo khóa mới: cần phát hành chain mới, phân phối trust bundle và duy trì xác minh chứng thư cũ theo policy.

## 9. Ví dụ chính sách cryptoperiod theo rủi ro

Bảng dưới đây chỉ minh họa cách một tổ chức có thể cấu trúc policy. Các khoảng thời gian và ngưỡng usage phải được xác định từ tiêu chuẩn, vendor, thuật toán, threat model và phê duyệt nội bộ; không dùng các con số ví dụ như khuyến nghị phổ quát.

| Key profile | Mức rủi ro | Trigger chính | Khi ngừng bảo vệ mới | Xử lý khóa cũ |
|---|---|---|---|---|
| DEK cho dữ liệu tạm | Thấp/trung bình | Tuổi hoặc số byte/invocation. | Encrypt bằng DEK mới. | Giữ đủ để đọc dữ liệu còn tồn tại; hủy khi hết retention. |
| DEK cho dữ liệu nhạy cảm | Cao | Tuổi, volume, tenant hoặc sự kiện. | Chuyển sang DEK mới; đánh giá re-encrypt nếu compromise. | Giữ wrapped DEK theo retention và kiểm soát truy cập. |
| KEK production | Cao/rất cao | Tuổi, số DEK phụ thuộc, sự kiện KMS/HSM. | Wrap DEK mới bằng KEK mới. | Rewrap DEK và backup trước khi retire/destroy. |
| Signing key | Cao/rất cao | Tuổi, số chữ ký, algorithm sunset hoặc compromise. | Ngừng ký mới bằng private key cũ. | Giữ public key/certificate và bằng chứng để verify lịch sử. |
| HMAC key | Trung bình/cao | Tuổi, số MAC, số principal và replay window. | Tạo MAC bằng key mới. | Chỉ verify MAC cũ trong cửa sổ được định nghĩa. |
| TLS private key | Theo dịch vụ và exposure | Tuổi, certificate lifecycle, compromise hoặc policy. | Triển khai key pair mới nếu rekey. | Giữ mapping cần thiết cho rollback trong thời gian an toàn. |
| CA key | Rất cao | Policy PKI, algorithm lifecycle, incident và kế hoạch trust migration. | Ngừng ký mới bằng CA key cũ theo kế hoạch. | Giữ public certificate, chain và evidence phục vụ validation lịch sử. |

Điểm quan trọng là policy phải nêu rõ trigger, người chịu trách nhiệm, thời hạn xử lý, thao tác bị dừng, thao tác còn được phép và điều kiện hủy. Một bảng chỉ ghi “rotate mỗi N tháng” chưa đủ cho vận hành.

## 10. Rotation khi cryptoperiod kết thúc

Một quy trình rotation có kiểm soát thường gồm:

1. **Đánh giá:** xác nhận key version, trigger, dữ liệu và dịch vụ phụ thuộc.
2. **Tạo khóa mới:** dùng thuật toán, key size, purpose và provider được phê duyệt.
3. **Đăng ký:** ghi key ID/version, metadata, owner và trạng thái.
4. **Cấp quyền:** grant cho đúng workload và operation.
5. **Kiểm tra:** thử encrypt/sign mới và negative authorization.
6. **Chuyển đổi:** ứng dụng bắt đầu dùng key version mới cho dữ liệu hoặc chữ ký mới.
7. **Duy trì xử lý cũ:** cho phép decrypt/verify bằng version cũ trong thời gian cần thiết.
8. **Di trú:** rewrap DEK, re-encrypt dữ liệu hoặc cập nhật trust chain khi phù hợp.
9. **Đối soát:** xác nhận không còn dependency ngoài kế hoạch.
10. **Retire/destroy:** disable, revoke hoặc hủy theo key policy và retention.

Nên triển khai theo canary hoặc từng nhóm workload khi có thể. Giữ khả năng rollback trong thời gian chuyển đổi, nhưng không rollback về khóa đã compromise hoặc thuật toán đã bị cấm.

## 11. Rewrap và re-encrypt: chọn đúng thao tác

Rotation không phải lúc nào cũng cần giải mã và mã hóa lại toàn bộ dữ liệu. Phân biệt:

| Thao tác | Thay đổi | Dùng khi |
|---|---|---|
| Rewrap DEK | Giữ nguyên DEK và ciphertext; thay lớp KEK bọc DEK. | KEK cần rotate nhưng DEK và dữ liệu chưa bị compromise. |
| Re-encrypt data | Tạo DEK mới và mã hóa lại plaintext thành ciphertext mới. | DEK bị compromise, thuật toán/mode thay đổi hoặc policy yêu cầu đổi khóa dữ liệu. |
| Re-sign | Tạo chữ ký mới bằng signing key mới cho artifact hoặc dữ liệu cần ký lại. | Private signing key bị compromise hoặc chữ ký mới phải dùng key version mới. |
| Reissue certificate | CA cấp certificate mới cho public key/key pair theo policy. | Certificate sắp hết hạn, thay đổi danh tính hoặc rekey. |

Rewrap chỉ thay đổi cách bảo vệ DEK. Nếu DEK đã bị lộ, rewrap DEK cũ không làm DEK đó bí mật trở lại. Tương tự, cấp certificate mới với public key cũ không khắc phục private key đã compromise.

## 12. Quản lý giai đoạn chuyển tiếp và khóa cũ

Trong giai đoạn chuyển tiếp, hệ thống có thể cần hai version cùng tồn tại:

- Version mới được dùng để encrypt/sign/MAC dữ liệu mới.
- Version cũ chỉ được dùng để decrypt/verify dữ liệu đã tạo trước đó.

Cần gắn version hoặc key ID vào metadata ciphertext, chữ ký, token hoặc record để chọn đúng khóa khi xử lý. Không suy ra version từ thứ tự file hoặc alias có thể thay đổi.

Đặt ngày kết thúc recipient-usage period dựa trên retention, thời hạn xác minh và tiến độ di trú. Trước khi retire/destroy, kiểm tra:

- Không còn ciphertext hoặc wrapped DEK cần khóa cũ.
- Backup và snapshot đã được rewrap hoặc có phương án phục hồi.
- Chữ ký lịch sử vẫn có public key và evidence cần thiết.
- Không còn node, consumer, job hoặc đối tác dùng key version cũ.
- Inventory, policy và audit ghi nhận trạng thái cuối.

Nếu dữ liệu phải được lưu lâu dài, khóa giải mã hoặc cơ chế phục hồi có thể cần được giữ tương ứng lâu dài. Việc giữ khóa phải đi cùng bảo vệ mạnh, quyền hạn chế và rà soát định kỳ.

## 13. Emergency rotation khi nghi ngờ compromise

Emergency rotation được kích hoạt khi có dấu hiệu key material bị lộ, principal bị chiếm quyền, export bất thường, thiết bị bị xâm nhập, nonce reuse hoặc lỗi mật mã nghiêm trọng.

Các bước phản ứng:

1. Xác định key ID/version, loại khóa, principal và phạm vi dữ liệu/chữ ký bị ảnh hưởng.
2. Chặn hoặc thu hồi quyền truy cập đáng ngờ; bảo toàn audit evidence.
3. Ngừng dùng khóa cũ cho thao tác bảo vệ mới nếu có thể.
4. Tạo key version mới hoặc key pair mới trong KMS/HSM được phê duyệt.
5. Cấp quyền mới theo least privilege và kiểm tra khả năng sử dụng.
6. Re-encrypt, rewrap, re-sign hoặc reissue theo bản chất sự cố.
7. Revoke certificate/grant/session liên quan nếu cần.
8. Kiểm tra backup, replica, cache, heap dump và key material đã export.
9. Theo dõi việc sử dụng khóa cũ và xác minh các consumer đã chuyển đổi.
10. Hủy khóa cũ khi đã đáp ứng điều kiện pháp lý, retention và recovery.

Không đợi đến cryptoperiod định kỳ nếu có dấu hiệu compromise. Rotation theo lịch không thay thế incident response.

## 14. Theo dõi tuổi khóa và mức sử dụng

Để áp dụng risk-based cryptoperiod, inventory và monitoring cần theo dõi ít nhất:

- Key ID/version, key class, owner, purpose và environment.
- Thời điểm tạo, kích hoạt và bắt đầu cryptoperiod.
- Thời điểm hết originator-usage period và recipient-usage period.
- Thuật toán, key size, mode và provider.
- Số lần encrypt/decrypt/sign/verify/MAC/wrap/unwrap.
- Tổng byte hoặc số đối tượng đã xử lý khi có ý nghĩa.
- Trạng thái nonce allocation/uniqueness đối với mode yêu cầu.
- Số principal, grant, workload và tenant đang dùng.
- Export event, policy change, access denied và sự kiện compromise.
- Key version cũ còn dependency hoặc ciphertext chưa di trú.

Không phải KMS nào cũng cung cấp mọi bộ đếm. Nếu provider không có metric volume, ứng dụng hoặc gateway có thể ghi usage counter theo key ID/version, bảo đảm không log key material và chống sửa đổi số liệu. Bộ đếm phải đủ tin cậy để không reset hoặc mất khi ứng dụng restart.

## 15. Ví dụ policy YAML cho risk-based cryptoperiod

Ví dụ dưới đây mô tả một policy logic. Nó không phải cú pháp chuẩn của KMS cụ thể:

~~~yaml
key_profile: customer-data-dek
purpose: data-encryption
environment: production

cryptoperiod:
  activated_at: required
  max_age_days: 90
  max_encrypt_operations: 500000
  max_encrypted_bytes: 1099511627776
  rotation_triggers:
    - age_limit
    - operation_limit
    - byte_limit
    - suspected_compromise

usage:
  after_rotation:
    new_encrypt: new_version_only
    decrypt_old_data: previous_versions_until_retention_end

protection:
  exportable: false
  allowed_operations:
    - encrypt
    - decrypt
  require_audit: true

retirement:
  require_dependency_check: true
  require_backup_validation: true
  destroy_after_retention: true
~~~

Các ngưỡng trong YAML chỉ là ví dụ minh họa. Trước khi triển khai, phải xác định giới hạn theo thuật toán, mode, nonce strategy, provider, volume dự kiến và yêu cầu nội bộ. Với AES-GCM, không dùng max_encrypted_bytes thay cho kiểm soát nonce uniqueness hoặc các giới hạn khác của cấu hình GCM.

## 16. Ví dụ Java kiểm tra điều kiện rotation

Đoạn mã sau minh họa cách đánh giá trigger theo tuổi, số thao tác và lượng dữ liệu. Đây là logic ứng dụng đơn giản, không phải thuật toán xác định cryptoperiod phổ quát. Policy và ngưỡng phải được nạp từ cấu hình đã phê duyệt; bộ đếm phải được lưu bền vững theo từng key version.

~~~java
import java.time.Duration;
import java.time.Instant;

public final class RotationDecision {

    public record Usage(
            Instant activatedAt,
            long encryptOperations,
            long encryptedBytes) {
    }

    public record Policy(
            Duration maxAge,
            long maxEncryptOperations,
            long maxEncryptedBytes) {
    }

    public static boolean rotationDue(
            Usage usage,
            Policy policy,
            Instant now) {

        if (usage == null || policy == null || now == null
                || usage.activatedAt() == null
                || policy.maxAge() == null) {
            throw new IllegalArgumentException(
                    "Thiếu dữ liệu đánh giá rotation");
        }
        if (usage.encryptOperations() < 0
                || usage.encryptedBytes() < 0
                || policy.maxAge().isNegative()
                || policy.maxAge().isZero()
                || policy.maxEncryptOperations() <= 0
                || policy.maxEncryptedBytes() <= 0) {
            throw new IllegalArgumentException(
                    "Ngưỡng cryptoperiod không hợp lệ");
        }
        if (now.isBefore(usage.activatedAt())) {
            throw new IllegalArgumentException(
                    "Thời điểm đánh giá sớm hơn thời điểm kích hoạt");
        }

        boolean ageLimitReached =
                !now.isBefore(usage.activatedAt().plus(policy.maxAge()));
        boolean operationLimitReached =
                usage.encryptOperations()
                        >= policy.maxEncryptOperations();
        boolean byteLimitReached =
                usage.encryptedBytes()
                        >= policy.maxEncryptedBytes();

        return ageLimitReached
                || operationLimitReached
                || byteLimitReached;
    }
}
~~~

Ví dụ dùng record nên yêu cầu Java 16 trở lên. Trong production, cần xử lý tràn số khi cộng bộ đếm, sai lệch đồng hồ, cập nhật đồng thời, reset counter theo version và retry an toàn. Nên phát cảnh báo trước khi đạt ngưỡng để có thời gian tạo khóa mới và chuyển workload. Nếu nhận sự kiện compromise, phải kích hoạt emergency process ngay thay vì chờ hàm rotationDue.

## 17. Kiểm thử và assurance cho cryptoperiod

Một chính sách chỉ có giá trị khi có thể kiểm tra và chứng minh được. Các bài test nên bao gồm:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Khóa đạt tuổi tối đa | Rotation được kích hoạt hoặc cảnh báo theo SLA. |
| Khóa đạt usage/byte limit | Không tiếp tục dùng cho thao tác bảo vệ mới vượt ngưỡng. |
| Khóa chưa đến ngưỡng | Không rotate sớm ngoài policy, trừ khi có event/risk trigger. |
| Có suspected compromise | Emergency rotation được kích hoạt bất kể tuổi khóa. |
| Version mới được tạo | Metadata, policy, grant và kiểm thử mật mã đều thành công trước activation. |
| Dữ liệu cũ còn dùng version cũ | Decrypt/verify vẫn hoạt động trong recipient-usage period. |
| Rewrap KEK | Wrapped DEK mới mở được; ciphertext dữ liệu không đổi và vẫn giải mã được. |
| Re-encrypt DEK | Ciphertext mới giải mã đúng; version cũ được giữ theo retention. |
| Principal ngoài phạm vi gọi key | Bị từ chối và có audit event. |
| Rotation thất bại giữa chừng | Workflow giữ trạng thái rõ, có retry/rollback và không hủy khóa cũ sớm. |
| Hết retention | Khóa cũ được retire/destroy theo approval và có bằng chứng. |

Assurance evidence có thể gồm key inventory, policy version, approval record, usage metric, rotation event, test report, dependency scan và audit log. Bằng chứng cần chỉ ra vì sao chu kỳ được chọn là phù hợp, ai phê duyệt và điều kiện nào sẽ làm thay đổi quyết định.

## 18. Rà soát và điều chỉnh cryptoperiod

Cryptoperiod không phải giá trị bất biến. Rà soát khi:

- Thuật toán, key size hoặc thư viện/provider thay đổi.
- Tiêu chuẩn, quy định hoặc hợp đồng cập nhật.
- Dữ liệu được phân loại lại hoặc retention tăng.
- Khóa được dùng bởi nhiều workload/tenant hơn dự kiến.
- Có thay đổi HSM/KMS, exportability hoặc access policy.
- Monitoring phát hiện usage tăng, principal mới hoặc hành vi bất thường.
- Một sự cố compromise xảy ra trong hệ thống tương tự.
- Automation, recovery hoặc khả năng re-encrypt được cải thiện hoặc suy giảm.

Mỗi lần rà soát cần lưu phiên bản policy, lý do thay đổi, tác động lên key version đang hoạt động và kế hoạch chuyển tiếp. Không thay đổi cryptoperiod hàng loạt mà không kiểm tra khả năng xử lý dữ liệu lịch sử.

## 19. Những sai lầm thường gặp

**Dùng một chu kỳ cho mọi khóa.** Khóa DEK ngắn hạn, KEK, khóa ký và CA key có mục đích và blast radius khác nhau. Phân loại theo key profile.

**Chỉ dựa vào tuổi khóa.** Một khóa có thể đạt giới hạn volume hoặc gặp compromise trước ngày rotation. Kết hợp age, usage và event trigger.

**Coi hết originator-usage period là phải hủy ngay.** Dữ liệu cũ hoặc chữ ký lịch sử có thể vẫn cần khóa. Tách thời gian tạo bảo vệ mới khỏi thời gian xử lý dữ liệu cũ.

**Rotate KEK nhưng quên rewrap DEK.** DEK cũ có thể vẫn phụ thuộc KEK cũ. Đối soát toàn bộ wrapped DEK và backup trước khi hủy KEK.

**Rewrap DEK đã bị lộ.** Rewrap không làm DEK compromise trở nên an toàn. Cần tạo DEK mới và re-encrypt dữ liệu bị ảnh hưởng.

**Renew certificate nhưng giữ private key đã lộ.** Certificate mới không khắc phục compromise của private key. Tạo key pair mới và revoke certificate cũ theo quy trình.

**Đặt usage threshold mà không tính nonce.** Với AEAD, số byte không thay thế yêu cầu nonce uniqueness và giới hạn invocation. Tuân thủ profile cụ thể.

**Rotate quá thường xuyên nhưng chưa có automation.** Thao tác thủ công lặp lại có thể gây lỗi và bỏ sót dependency. Cần kiểm thử pipeline và rollback.

**Không giữ key version cũ.** Dữ liệu archive hoặc chữ ký lịch sử có thể không còn xử lý được. Giữ version theo retention và kiểm soát truy cập.

**Không có bằng chứng giải trình.** Không lưu threat assessment, nguồn tiêu chuẩn, usage metric và approval khiến tổ chức không thể chứng minh quyết định chu kỳ.

## 20. Checklist xây dựng risk-based cryptoperiod

**Đánh giá rủi ro**

- [ ] Có inventory và owner cho từng key ID/version.
- [ ] Xác định purpose, algorithm, key size, provider và exportability.
- [ ] Phân loại dữ liệu, retention và blast radius.
- [ ] Đánh giá volume, số thao tác, nonce policy và số principal.
- [ ] Kiểm tra tiêu chuẩn, hợp đồng và giới hạn provider.

**Đặt policy**

- [ ] Xác định originator-usage và recipient-usage period riêng.
- [ ] Đặt max age và giới hạn usage phù hợp thuật toán.
- [ ] Có age-based, usage-based và event-based triggers.
- [ ] Quy định quyền sau rotation: encrypt/sign mới và decrypt/verify cũ.
- [ ] Quy định điều kiện retire, revoke và destroy.

**Vận hành**

- [ ] Có automation, canary, rollback và reconciliation.
- [ ] Theo dõi tuổi, số thao tác, byte và key version đang được dùng.
- [ ] Rewrap hoặc re-encrypt theo đúng loại sự cố.
- [ ] Giữ khóa cũ theo retention và dependency.
- [ ] Có emergency rotation khi nghi ngờ compromise.

**Assurance**

- [ ] Policy có owner, version, approval và lý do.
- [ ] Đã test rotation, recovery, negative authorization và xử lý dữ liệu cũ.
- [ ] Có audit event và metric đủ để chứng minh thực thi.
- [ ] Rà soát lại khi thuật toán, dữ liệu, môi trường hoặc tiêu chuẩn thay đổi.

Risk-based cryptoperiod giúp tổ chức giới hạn thời gian và phạm vi sử dụng khóa theo mức rủi ro thực tế. Quyết định tốt phải xét đồng thời thuật toán, lượng dữ liệu, độ nhạy, khả năng truy cập, hậu quả compromise và khả năng rotation. Khi tách rõ thời gian tạo bảo vệ mới với thời gian cần giải mã hoặc xác minh dữ liệu cũ, tổ chức có thể thay khóa đúng lúc mà vẫn duy trì khả năng truy cập dữ liệu và bằng chứng mật mã trong suốt vòng đời.

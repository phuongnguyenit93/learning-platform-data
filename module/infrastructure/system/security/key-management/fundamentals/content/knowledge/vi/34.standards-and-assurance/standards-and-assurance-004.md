# OWASP Key Management Cheat Sheet

**OWASP Key Management Cheat Sheet** là hướng dẫn thực hành giúp đội ngũ phát triển và vận hành quản lý khóa mật mã an toàn trong ứng dụng. Nội dung tập trung vào toàn bộ vòng đời khóa: lựa chọn thuật toán, sinh khóa, lưu trữ, phân phối, sử dụng, xoay vòng, sao lưu, khôi phục, xử lý khi bị lộ và hủy khóa.

Điểm cốt lõi là khóa cần được quản lý như một tài sản bảo mật có danh tính, chủ sở hữu, mục đích sử dụng, quyền truy cập và vòng đời rõ ràng. Một thuật toán mạnh không thể bù cho khóa được sinh yếu, lưu cùng dữ liệu đã mã hóa, phân phối qua kênh không an toàn hoặc không thể thu hồi khi bị xâm phạm.

Cheat Sheet của OWASP là hướng dẫn kỹ thuật và vận hành cho người xây dựng ứng dụng. Nó không phải chứng nhận sản phẩm, không tự động chứng minh hệ thống tuân thủ một tiêu chuẩn pháp quy và cũng không thay thế đánh giá rủi ro, yêu cầu của tổ chức hoặc quy định ngành. Cần dùng hướng dẫn này cùng chính sách mật mã, tiêu chuẩn áp dụng và khả năng thực tế của KMS/HSM/provider.

## 1. Mục tiêu và phạm vi của Key Management Cheat Sheet

Mục tiêu của quản lý khóa là bảo vệ tính bí mật, toàn vẹn, xác thực và khả năng sẵn sàng của dữ liệu trong suốt vòng đời sử dụng khóa. Với mỗi khóa, tổ chức cần trả lời được:

- Khóa được dùng cho mục đích nào: mã hóa, giải mã, ký, xác minh, MAC hay thỏa thuận khóa?
- Ai hoặc workload nào sở hữu và được phép sử dụng khóa?
- Khóa được sinh ở đâu, bằng provider nào và theo tham số nào?
- Vật liệu khóa được lưu ở đâu và có thể export hay không?
- Dữ liệu, ciphertext, chữ ký hoặc DEK nào phụ thuộc vào khóa?
- Khi nào cần rotate, revoke, disable hoặc destroy?
- Làm thế nào để backup và khôi phục mà không tạo thêm bản sao không kiểm soát?
- Bằng chứng nào chứng minh các thao tác quản trị khóa đã diễn ra đúng policy?

Phạm vi quản lý không chỉ gồm private key hoặc symmetric key. Nó còn gồm key-encryption key (KEK), data-encryption key (DEK), khóa HMAC, khóa ký, khóa dẫn xuất, khóa phiên và metadata cần thiết để sử dụng chúng an toàn.

## 2. Xây dựng chính sách mật mã trước khi tạo khóa

Trước khi gọi API sinh khóa, cần có chính sách quy định thuật toán và mục đích được phép. Chính sách cần xem xét:

- Mô hình đe dọa và mức độ nhạy cảm của dữ liệu.
- Thuật toán, key size, curve và chế độ hoạt động được chấp thuận.
- Mục đích sử dụng (key usage) và các operation bị cấm.
- Provider, KMS hoặc HSM được phép sử dụng.
- Thời hạn hoạt động và điều kiện rotation.
- Yêu cầu backup, recovery, audit và destruction.
- Yêu cầu tương thích, pháp quy hoặc chứng nhận của môi trường.

Mức chống chịu tính toán tối thiểu cần xét đến năng lực của đối thủ, thời gian dữ liệu phải được bảo vệ, nơi dữ liệu được lưu và khả năng bị lộ. Dữ liệu cần giữ bí mật nhiều năm có thể đòi hỏi lựa chọn khóa mạnh hơn dữ liệu có vòng đời ngắn. OWASP dẫn chiếu NIST SP 800-131A để đánh giá độ dài khóa phù hợp với thuật toán; khi chuyển sang Elliptic Curve, cần so sánh mức an toàn tương đương theo hướng dẫn như NIST SP 800-57.

Không nên chọn thuật toán chỉ vì API có hỗ trợ hoặc ví dụ trên Internet đang dùng. Cần tránh thuật toán và chế độ đã lỗi thời hoặc không phù hợp với use case, chẳng hạn DES, 3DES cho thiết kế mới, RC4, ECB cho mã hóa dữ liệu thông thường hoặc RSA với kích thước khóa không đạt policy hiện hành.

Với mã hóa dữ liệu ứng dụng, ưu tiên authenticated encryption như AES-GCM hoặc một AEAD đã được tổ chức phê duyệt. Với chữ ký, chọn scheme có padding và tham số đúng giao thức. Với thỏa thuận khóa, dùng cơ chế phù hợp như ECDH/X25519 rồi đưa shared secret qua KDF; không dùng shared secret thô làm khóa ứng dụng.

Các giá trị như key size tối thiểu, thời hạn và thuật toán được phép cần được quản lý tập trung và rà soát định kỳ. OWASP đưa ra hướng dẫn thực hành; chính sách cuối cùng phải xét tiêu chuẩn và yêu cầu hiện hành của môi trường triển khai.

## 3. Sinh khóa bằng nguồn ngẫu nhiên mật mã

Khóa cần được tạo bằng cryptographically secure random number generator (CSPRNG) hoặc dịch vụ sinh khóa đáng tin cậy. Trong Java, dùng **SecureRandom**, **KeyGenerator**, **KeyPairGenerator** hoặc KMS/HSM. Không dùng **java.util.Random**, timestamp, UUID thông thường, bộ đếm hoặc chuỗi do người phát triển tự nghĩ làm vật liệu khóa.

OWASP khuyến nghị tạo khóa bên trong cryptographic module đáp ứng yêu cầu FIPS 140-2 hoặc FIPS 140-3 phù hợp với môi trường; random bit generator tạo giá trị ngẫu nhiên cũng cần nằm trong module đó. Hardware cryptographic module được ưu tiên khi cần mức bảo vệ cao. Việc chọn module phải xét phiên bản chuẩn, phạm vi chứng nhận và yêu cầu áp dụng thực tế, không chỉ dựa vào nhãn sản phẩm.

Ví dụ sinh khóa AES bằng JCA:

~~~java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class KeyGeneration {
    private KeyGeneration() {
    }

    public static SecretKey generateAesKey() throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, random);

        return generator.generateKey();
    }
}
~~~

Độ dài 256 bit trong ví dụ chỉ phù hợp khi provider và policy môi trường cho phép. Nếu chính sách yêu cầu cấu hình khác, hãy truyền cấu hình từ policy đã được phê duyệt. Không tự seed SecureRandom bằng một giá trị cố định trong production; việc seed sai có thể làm giảm tính khó đoán của đầu ra.

Ví dụ dùng provider mặc định của JCA để minh họa API. Nếu môi trường yêu cầu FIPS, phải cấu hình provider và cryptographic module đã được phê duyệt, xác minh phạm vi validation và bảo đảm cả thao tác sinh khóa lẫn random bit generator nằm trong module phù hợp.

Với khóa bất đối xứng, cần chỉ định thuật toán và tham số rõ ràng. Ví dụ RSA cần key size theo policy; EC cần named curve được chấp thuận. Với HSM/KMS, ưu tiên sinh khóa ngay trong ranh giới bảo vệ nếu khóa không cần export.

Không nên tự viết thuật toán sinh khóa hoặc tự tạo entropy bằng cách ghép các giá trị môi trường. Hãy dùng API và provider được duy trì, có đánh giá bảo mật và được tổ chức phê duyệt.

## 4. Lưu trữ khóa tách biệt với dữ liệu được bảo vệ

Một nguyên tắc quan trọng là không lưu khóa giải mã cùng nơi hoặc cùng quyền truy cập với ciphertext theo cách khiến một lần lộ dữ liệu đồng thời làm lộ khóa. Nếu kẻ tấn công lấy được cả dữ liệu mã hóa và khóa, mã hóa không còn tạo ra ranh giới bảo vệ.

Các lựa chọn lưu trữ thường gặp:

| Cơ chế | Vai trò | Trường hợp phù hợp |
|---|---|---|
| KMS | Quản lý key resource, policy, version và thao tác mật mã qua API | Ứng dụng cloud hoặc hệ thống tích hợp dịch vụ quản lý khóa |
| HSM | Bảo vệ vật liệu khóa trong phần cứng và thực hiện thao tác bên trong thiết bị | Khóa trọng yếu, signing key, yêu cầu non-exportable |
| Java KeyStore | Lưu key entry và certificate theo provider | Ứng dụng Java hoặc triển khai tại chỗ |
| Secret manager | Lưu và phân phối password, token, API credential và một số secret | Cấu hình ứng dụng và credential |
| OS/platform keystore | Lưu khóa theo cơ chế bảo vệ của hệ điều hành hoặc nền tảng | Desktop, mobile hoặc workload được hỗ trợ |

Không nên coi các lựa chọn trên thay thế hoàn toàn nhau. Secret manager phù hợp với nhiều loại credential; KMS cung cấp vòng đời và thao tác khóa; HSM bảo vệ vật liệu khóa bằng ranh giới phần cứng. Ứng dụng nên dùng key reference hoặc API của dịch vụ khi có thể, thay vì đọc raw key bytes.

Tránh hardcode khóa trong source code, commit vào Git, đóng gói trong container image, ghi vào log hoặc lưu trong file cấu hình có quyền đọc rộng. Mã hóa file chứa khóa bằng một khóa khác chỉ có ý nghĩa khi khóa bảo vệ được lưu và kiểm soát độc lập.

Không lưu key ở dạng plaintext trên persistent storage. Nếu bắt buộc phải export khóa sang thiết bị hoặc database offline, hãy wrap bằng KEK có thuật toán và độ mạnh tương đương hoặc cao hơn khóa được bảo vệ; đồng thời áp dụng integrity protection để phát hiện thay thế hoặc sửa đổi. Khi có thể, thực hiện truy cập và thao tác mật mã bên trong vault thay vì để application code đọc raw key.

Khi thiết lập hoặc nhận khóa qua một giao thức, có thể cần key confirmation để xác minh các bên thực sự có cùng khóa dự kiến. Việc kiểm tra tính toàn vẹn của key wrapping và mối liên hệ giữa key với metadata cũng giúp phát hiện khóa bị thay thế hoặc metadata bị sửa.

## 5. Envelope encryption: tách DEK và KEK

Envelope encryption giúp tách khóa mã hóa dữ liệu khỏi khóa dùng để bảo vệ khóa dữ liệu:

1. Sinh một DEK ngẫu nhiên cho dữ liệu hoặc một phạm vi dữ liệu phù hợp.
2. Dùng DEK mã hóa dữ liệu bằng AEAD.
3. Dùng KEK trong KMS/HSM để wrap hoặc encrypt DEK.
4. Lưu ciphertext, encrypted DEK và metadata cần thiết cùng nhau.
5. Khi giải mã, yêu cầu KMS/HSM unwrap DEK rồi dùng DEK giải mã dữ liệu.

Cách này giúp ứng dụng không cần lưu một master key có quyền giải mã toàn bộ dữ liệu. KEK có thể được quản lý tập trung, giới hạn quyền theo workload và dùng để re-wrap DEK khi rotation.

Encrypted DEK không phải raw key material, nhưng vẫn là dữ liệu nhạy cảm vì nó là đường dẫn tới khóa dữ liệu nếu KEK còn hoạt động. Metadata cần lưu key version ID của KEK, thuật toán, nonce/IV và AAD theo định dạng đã chuẩn hóa.

Không tái sử dụng DEK cho phạm vi rộng hơn thiết kế. Với AES-GCM, cần bảo đảm nonce không lặp lại dưới cùng một khóa. Nếu dùng một DEK cho nhiều bản ghi, phải có chiến lược nonce và giới hạn số lượng operation phù hợp.

## 6. Phân phối khóa an toàn

Khóa và credential cần được chuyển tới consumer qua kênh đã xác thực và bảo vệ tính bí mật/toàn vẹn. Không gửi key material qua email, chat, ticket, log hoặc file chia sẻ không được kiểm soát.

Các nguyên tắc:

- Xác thực cả bên gửi và bên nhận.
- Dùng TLS và cơ chế xác thực endpoint đúng.
- Cấp khóa hoặc credential theo danh tính workload, không dựa vào địa chỉ IP đơn lẻ.
- Giới hạn consumer, môi trường và operation.
- Ưu tiên credential ngắn hạn hoặc dynamic secret.
- Tránh xuất raw key nếu KMS/HSM có thể thực hiện operation thay ứng dụng.
- Ghi nhận việc cấp phát và truy cập mà không ghi giá trị bí mật.

Khi phải chuyển key material giữa các miền tin cậy, cần dùng key wrapping hoặc giao thức trao đổi khóa được thiết kế cho mục đích đó. Không tự mã hóa khóa bằng một khóa tùy ý hoặc gửi nó trong cùng kênh với thông tin giải mã.

Khi cần chuyển khóa, dùng secure channel đã xác thực và bảo vệ tính toàn vẹn. Khóa sau khi phân phối phải được sử dụng trong cryptographic module phù hợp với yêu cầu bảo đảm của hệ thống. OWASP dẫn chiếu NIST SP 800-133 cho hướng dẫn bổ sung về sinh và quản lý vật liệu khóa.

## 7. Kiểm soát truy cập và phân tách nhiệm vụ

Quyền truy cập khóa cần theo nguyên tắc least privilege. Principal chỉ nên có đúng operation và key scope cần thiết:

- Service cần mã hóa có thể chỉ cần Encrypt hoặc GenerateDataKey.
- Service cần đọc dữ liệu có thể cần Decrypt trên một nhóm khóa cụ thể.
- Signing service chỉ được ký bằng signing key được chỉ định.
- Nhóm vận hành có thể quản lý metadata nhưng không mặc nhiên có quyền export key.
- Quyền sửa key policy, grant, rotate và destroy cần được tách theo trách nhiệm.

Với thao tác nhạy cảm, áp dụng separation of duties, phê duyệt độc lập hoặc quorum theo chính sách. Không để một principal vừa tạo khóa, tự cấp quyền rộng, tự export và tự xóa audit.

JIT access có thể cấp quyền đặc biệt trong thời gian ngắn khi có ticket hoặc incident. Grant cần ràng buộc principal, key ID, operation, thời hạn và lý do. Khi công việc kết thúc, thu hồi grant hoặc để nó hết hạn theo policy.

## 8. Sử dụng khóa đúng mục đích

Không dùng một khóa cho nhiều mục đích mật mã không liên quan nếu không có thiết kế và phân tích phù hợp. Tách khóa theo purpose giúp giới hạn tác động khi một khóa bị lộ hoặc policy bị cấu hình sai.

Theo nguyên tắc được OWASP dẫn chiếu từ NIST, một khóa nhìn chung chỉ nên phục vụ một mục đích: mã hóa, xác thực, key wrapping, sinh số ngẫu nhiên hoặc chữ ký số. Tách purpose giúp policy dễ kiểm tra và ngăn một khóa bị dùng sai ngữ cảnh.

Ví dụ:

- AES key dùng mã hóa dữ liệu.
- HMAC key dùng xác thực thông điệp.
- Private key dùng ký số.
- Public key dùng xác minh chữ ký hoặc mã hóa theo giao thức tương ứng.
- Key agreement private key dùng thỏa thuận khóa.
- KEK dùng wrap DEK, không dùng làm khóa dữ liệu trực tiếp.

Key usage và algorithm phải tương thích. Không dùng RSA signing key cho mục đích mã hóa tùy tiện; không dùng X25519 như khóa chữ ký; không dùng public key chưa xác minh danh tính để tin cậy một bên.

Với giao thức trao đổi khóa, ephemeral key có thể hỗ trợ Perfect Forward Secrecy (PFS): việc lộ khóa dài hạn về sau không tự động làm lộ các phiên trước đó nếu giao thức và quá trình xóa bí mật phiên được triển khai đúng. Cần dùng cơ chế key agreement được chuẩn hóa và không tái sử dụng ephemeral private key ngoài phạm vi giao thức cho phép.

Trong Java, tránh chuyển đổi raw key thành String, ghi getEncoded() ra log hoặc lưu trong exception. Với khóa HSM-backed, object Key có thể chỉ là handle và getEncoded() có thể trả null; đó là hành vi có thể đúng với non-exportable key.

## 9. Rotation và quản lý phiên bản

Rotation thay thế một phiên bản khóa bằng phiên bản mới theo lịch hoặc theo sự kiện. Cần có key version ID bất biến để ciphertext cũ luôn xác định được khóa cần dùng.

Một chiến lược thường dùng là **single-write, multi-read**:

- Mã hóa dữ liệu mới bằng version hiện hành.
- Tiếp tục giải mã dữ liệu cũ bằng version cũ còn được phép.
- Re-encrypt dữ liệu cũ hoặc re-wrap DEK theo kế hoạch.
- Chỉ retire/destroy version cũ khi không còn dependency và đã kiểm tra backup.

Không nên thay alias rồi giả định toàn bộ dữ liệu đã được chuyển đổi. Alias có thể trỏ tới version mới trong khi ciphertext cũ vẫn phụ thuộc version trước. Metadata của ciphertext/envelope cần chứa version ID chính xác.

Rotation có thể được kích hoạt bởi lịch, thay đổi chính sách, thay đổi nhân sự hoặc workload, nghi ngờ compromise, thay đổi thuật toán hoặc sự kiện vận hành. Khi khóa bị compromise, cần incident response khẩn cấp thay vì chờ lịch rotation thông thường.

Khoảng thời gian một khóa được phép sử dụng gọi là **cryptoperiod**. Thời hạn cần dựa trên thuật toán, độ mạnh khóa, môi trường, threat model, mức nhạy cảm và lượng dữ liệu được bảo vệ. Cần phân biệt thời gian khóa được dùng để tạo bảo vệ mới (originator usage) với thời gian còn được dùng để xử lý dữ liệu cũ (recipient usage). Không áp dụng một lịch cố định cho mọi loại khóa.

OWASP dẫn một số mốc tham khảo từ NIST SP 800-57: khóa mã hóa đối xứng dùng cho workload dung lượng thấp có thể có originator usage tối đa khoảng hai năm; hệ thống lưu lượng cao hoặc link encryption có thể cần giới hạn ở mức một ngày hoặc một tuần. Recipient usage thường được giới hạn không quá ba năm sau khi originator usage kết thúc. Private signing key thường có originator cryptoperiod khoảng một đến ba năm, trong khi public verification key có thể được giữ lâu hơn để xác minh dữ liệu đã ký lưu trữ. Static key-agreement pair có thể có thời hạn ngắn hơn; ephemeral pair thường chỉ dùng cho một giao dịch thỏa thuận khóa. Đây là ví dụ tham khảo, không phải lịch bắt buộc cho mọi hệ thống.

Rotation cần tính cả lượng sử dụng, không chỉ thời gian. Ví dụ, với AES-GCM dùng random 96-bit IV, giới hạn số lần mã hóa trên cùng một khóa cần tuân theo NIST SP 800-38D; OWASP nêu mốc tham chiếu tối đa 2^32 encryption operations trên tất cả thiết bị dùng chung khóa để hạn chế rủi ro va chạm IV. Hệ thống lưu lượng cao có thể cần rotate sớm hơn theo usage counter.

Gia hạn certificate không nhất thiết thay cặp khóa bên dưới. Lịch certificate renewal và key replacement cần được quản lý riêng. Ưu tiên tự động hóa rotation qua KMS hoặc giao thức quản lý certificate phù hợp; nếu phải rotate thủ công, ghi timestamp, operator identity và change/authorization reference.

## 10. Backup và recovery

Backup khóa cần được bảo vệ tương đương hoặc cao hơn khóa đang hoạt động. Nếu mất khóa giải mã, dữ liệu có thể không còn truy cập được; nếu backup bị lộ, kẻ tấn công có thể khôi phục vật liệu khóa.

Cần xác định:

- Khóa nào được phép backup và khóa nào phải non-exportable.
- Backup nằm ở đâu, được mã hóa bằng cơ chế nào và ai có quyền restore.
- Có cần kiểm soát kép hoặc quorum khi khôi phục không.
- Backup có version và metadata đủ để khôi phục đúng key identity không.
- Retention và destruction của backup diễn ra thế nào.
- Có thể khôi phục dịch vụ trong RTO/RPO đã cam kết không.

Không backup khóa bằng cách export raw bytes sang file tùy ý. Dùng chức năng backup/replication được provider hỗ trợ và giữ ranh giới bảo vệ. Việc backup cần được kiểm thử định kỳ bằng restore trong môi trường cô lập; một bản backup chưa từng restore thành công chưa chứng minh khả năng recovery.

Không để restore backup cũ làm sống lại khóa đã bị revoke hoặc destroy. Control plane cần có tombstone hoặc trạng thái thu hồi đáng tin cậy để ngăn việc khôi phục metadata cũ làm key trở lại hoạt động ngoài policy.

**Escrow** là lưu giữ có kiểm soát một bản sao khóa để phục hồi hoặc điều tra. OWASP lưu ý không escrow khóa dùng cho chữ ký số; với khóa phục vụ mã hóa, tổ chức có thể cân nhắc nhu cầu escrow để khôi phục dữ liệu khi khóa bị mất hoặc hỏng. Nếu áp dụng, escrow cần được phê duyệt, giới hạn người truy cập, bảo vệ bằng cryptographic module phù hợp, ghi audit và kiểm thử restore. Escrow không phải lý do để tạo bản sao không kiểm soát.

Inventory backup/escrow nên xác định duy nhất từng khóa, người hoặc workload sử dụng, thời điểm sử dụng, dữ liệu được bảo vệ và các khóa khác được bọc bởi khóa đó. Quan hệ này giúp xác định phạm vi ảnh hưởng khi compromise và biết bản sao nào cần thu hồi hoặc hủy.

## 11. Xử lý khi khóa bị lộ hoặc nghi ngờ bị compromise

Khi có dấu hiệu key compromise, ưu tiên hạn chế khả năng sử dụng khóa và xác định phạm vi ảnh hưởng:

1. Xác định key ID/version, loại khóa, owner và hệ thống phụ thuộc.
2. Thu hồi grant, credential hoặc quyền truy cập đáng ngờ.
3. Disable key nếu phù hợp với tình huống và policy.
4. Phát hành key version mới bằng nguồn tin cậy.
5. Chuyển writer và consumer sang khóa mới.
6. Re-encrypt dữ liệu hoặc re-wrap DEK khi cần.
7. Kiểm tra log sử dụng, chữ ký, ciphertext và dữ liệu có thể đã bị truy cập.
8. Đánh giá backup, replica và bản sao raw key đã export.
9. Thông báo và lưu bằng chứng theo quy trình incident response.
10. Destroy vật liệu bị compromise khi đã xử lý dependency và yêu cầu pháp lý.

Hành động phù hợp phụ thuộc loại khóa. Nếu private signing key bị lộ, có thể cần thu hồi certificate, thay key pair và đánh giá chữ ký trong khoảng thời gian rủi ro. Nếu KEK bị lộ, encrypted DEK có thể cần re-wrap bằng KEK mới; nếu DEK cũng bị lộ, dữ liệu có thể cần mã hóa lại bằng DEK mới.

Kế hoạch compromise recovery cần được lập thành tài liệu và dễ truy cập khi sự cố xảy ra. Kế hoạch nên nêu người cần thông báo và người thực hiện recovery, phương pháp re-key, inventory khóa và nơi sử dụng, cách đào tạo nhân sự, quy trình kiểm tra trạng thái revoke, cách giám sát toàn bộ hoạt động re-keying và cách xác định dữ liệu hoặc chữ ký có thể bị ảnh hưởng. Tùy sự cố, có thể cần kiểm tra thiết bị, xác định chữ ký không còn đáng tin và phân phối keying material mới.

Không chỉ xóa file hoặc secret khỏi kho rồi coi sự cố đã kết thúc. Nếu giá trị đã bị lộ, nó phải được xem là không còn đáng tin cậy và cần revoke/rotate tại hệ thống thực sự chấp nhận nó.

## 12. Destruction và crypto erasure

Khi khóa không còn cần thiết, phải hủy theo policy và xác minh đúng semantics của provider. Cần phân biệt:

- Disable: ngăn một số operation nhưng có thể bật lại.
- Revoke access: thu hồi quyền của principal, vật liệu khóa vẫn tồn tại.
- Delete alias/entry: xóa tham chiếu, không nhất thiết hủy vật liệu.
- Schedule deletion: lên lịch hủy sau cửa sổ chờ.
- Destroy/zeroize: hủy vật liệu khóa theo cam kết của KMS/HSM.
- Crypto erasure: làm dữ liệu không thể giải mã bằng cách hủy mọi bản sao khóa cần thiết.

Crypto erasure chỉ có ý nghĩa khi không còn bản sao khóa giải mã, bản export, DEK, backup hoặc plaintext ở hệ thống khác. Hủy KEK không đủ nếu DEK đã được lưu riêng ở nơi khác. Hủy private key không nhất thiết phải xóa public key dùng xác minh chữ ký cũ.

Không dùng unit test hoặc một lỗi decrypt đơn lẻ làm bằng chứng đã zeroize mọi bản sao. Cần đối chiếu metadata, audit, replica, backup và bằng chứng provider; giới hạn của việc chứng minh xóa vật lý phải được ghi rõ.

## 13. Audit và khả năng truy vết

Các thao tác quan trọng trong vòng đời khóa cần được audit: create, import, export, use, grant, rotate, disable, revoke, backup, restore và destroy.

Một audit event nên có:

- Actor hoặc workload identity.
- Key ID và version.
- Operation và mục đích.
- Timestamp, request ID và correlation ID.
- Policy/approval context.
- Kết quả thành công, từ chối hoặc lỗi.
- Provider, KMS/HSM resource và môi trường.
- Lý do hoặc change/incident reference.

Không ghi raw key, secret, token, plaintext hoặc dữ liệu nhạy cảm vào log. Audit log nên được gửi tới kho tập trung có quyền truy cập tách biệt, đồng bộ thời gian và cơ chế chống sửa đổi phù hợp.

Monitoring cần phát hiện truy cập ngoài baseline, nhiều lần AccessDenied, thao tác nhạy cảm ngoài giờ, thay đổi policy bất thường, rotation thất bại, key sắp hết hạn và lỗi backup/recovery. Cảnh báo cần gắn với key criticality và operation; không chỉ dựa vào số lượng event.

Accountability cần bao phủ người và workload có quyền xem, sử dụng hoặc kiểm soát khóa, kể cả khi vật liệu khóa được giữ dưới dạng ciphertext. Tối thiểu, hệ thống phải biết ai có thể xem plaintext symmetric/private key; mục tiêu tốt hơn là truy vết mọi principal có quyền truy cập hoặc quản trị key. OWASP khuyến nghị rà soát định kỳ cả security plan/procedure lẫn hiệu lực của các cơ chế bảo vệ; hoạt động của người vận hành và người bảo trì cũng cần được xem xét để phát hiện hành vi bất thường.

## 14. Ví dụ Java: tạo và sử dụng khóa mà không xuất key material

Ví dụ dưới đây minh họa tạo AES key và mã hóa bằng AES-GCM. Khóa được giữ trong đối tượng SecretKey; ứng dụng không gọi getEncoded() và không ghi vật liệu khóa ra log.

~~~java
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class SecureDataEncryption {
    private static final int NONCE_LENGTH = 12;
    private static final int TAG_LENGTH_BITS = 128;

    private SecureDataEncryption() {
    }

    public static SecretKey createKey() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, new SecureRandom());
        return generator.generateKey();
    }

    public static byte[] encrypt(
            SecretKey key,
            byte[] plaintext,
            byte[] aad) throws Exception {

        byte[] nonce = new byte[NONCE_LENGTH];
        new SecureRandom().nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            key,
            new GCMParameterSpec(TAG_LENGTH_BITS, nonce)
        );
        cipher.updateAAD(aad);

        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        // Định dạng minh họa: nonce || ciphertext || authentication tag.
        byte[] result = new byte[nonce.length + ciphertextAndTag.length];
        System.arraycopy(nonce, 0, result, 0, nonce.length);
        System.arraycopy(
            ciphertextAndTag, 0, result, nonce.length,
            ciphertextAndTag.length
        );

        return result;
    }
}
~~~

Đây là ví dụ minh họa API JCA, không phải một hệ thống key management hoàn chỉnh. Trong ứng dụng thực tế:

- Khóa cần được lưu hoặc tham chiếu trong KeyStore/KMS/HSM theo policy.
- Nonce phải duy nhất với cùng khóa; với lưu lượng lớn hoặc nhiều instance, cần chiến lược nonce có thể chứng minh không trùng.
- AAD cần được tạo từ metadata có encoding ổn định, ví dụ record ID, tenant và format version.
- Ciphertext cần lưu nonce, key version ID và metadata cần thiết để giải mã.
- Nếu dùng KMS/HSM, ưu tiên envelope encryption và thao tác wrap/unwrap DEK qua dịch vụ.
- Không trả raw key material cho caller chỉ để thuận tiện tích hợp.

## 15. Bảo vệ khóa trong bộ nhớ

Khóa có thể bị lộ khi ở dạng plaintext trong RAM, kể cả khi khóa được lưu an toàn trong HSM hoặc KMS. Cần hiểu tiến trình giữ key material ở đâu, trong bao lâu và những thành phần nào có thể đọc vùng nhớ đó.

- Giảm thời gian khóa tồn tại ở dạng plaintext trong bộ nhớ.
- Hạn chế số bản sao và không chuyển key material qua nhiều lớp ứng dụng nếu không cần thiết.
- Không đưa khóa vào String, log, exception, heap dump hoặc telemetry.
- Giới hạn quyền đọc process memory, debug interface, crash dump và swap theo chính sách nền tảng.
- Ưu tiên thực hiện thao tác trong KMS/HSM hoặc secure cryptographic module thay vì tải raw key vào ứng dụng.
- Dùng API zeroization hoặc secure-memory của nền tảng khi có; hiểu rõ giới hạn của managed runtime.

Trong Java, việc ghi đè một mảng byte/char chỉ là biện pháp best-effort. Garbage collector có thể di chuyển object, thư viện có thể tạo bản sao nội bộ và String là bất biến. Không được tuyên bố đã xóa sạch mọi bản sao chỉ vì gọi Arrays.fill trên một buffer. Với khóa không cần export, nên giữ khóa dưới dạng handle do provider quản lý.

## 16. Trust store và chứng chỉ

Trust store chứa certificate, public key và thông tin tin cậy được ứng dụng dùng để xác thực đối tác hoặc chuỗi chứng chỉ. Trust store không phải nơi để công khai tin cậy mọi certificate được thêm vào. Việc chèn một root certificate không đáng tin có thể khiến ứng dụng chấp nhận endpoint hoặc danh tính giả mạo.

Cần có các kiểm soát:

- Giới hạn ai và ứng dụng nào được phép cập nhật trust store.
- Bảo vệ tính toàn vẹn của certificate và object được lưu.
- Không cho export key entry nếu chưa xác thực và ủy quyền.
- Đặt policy nghiêm ngặt cho việc export key material giữa ứng dụng và thành phần mạng.
- Dùng quy trình cập nhật trust store an toàn, có review, audit và khả năng rollback.
- Phân biệt public certificate có thể phân phối với private key tương ứng phải được giữ bí mật.

Kiểm thử trust store cần bao gồm certificate hợp lệ, certificate hết hạn, chain không tin cậy, root certificate bị thay thế và principal không có quyền cập nhật. Không chỉ kiểm tra rằng file trust store có thể mở được.

## 17. Chọn thư viện quản lý khóa và mật mã

Chỉ sử dụng thư viện mật mã có uy tín, được duy trì và cập nhật. Ưu tiên implementation đã được kiểm thử độc lập hoặc được đánh giá/validated theo yêu cầu của môi trường, chẳng hạn module đáp ứng FIPS khi chính sách hoặc quy định yêu cầu.

Khi chọn thư viện/provider, kiểm tra:

- Lịch sử bảo trì, quy trình phát hành bản vá và khả năng tương thích với JDK.
- Thuật toán, tham số và key usage thực sự được hỗ trợ.
- Cách quản lý key material, memory, exception và log.
- Khả năng tích hợp với KeyStore, PKCS#11, KMS hoặc HSM.
- Bằng chứng kiểm thử/validation và phạm vi chính xác của chứng nhận.
- Khả năng xử lý lỗi, rotation, non-exportable key và audit.

Không coi việc thư viện có nhãn FIPS hoặc dùng provider có tên quen thuộc là bằng chứng mọi cấu hình ứng dụng đều tuân thủ. Cần xác định module nào được validated, phiên bản nào, chế độ vận hành nào và thao tác nào nằm trong phạm vi đó.

## 18. Checklist áp dụng OWASP Key Management Cheat Sheet

Có thể dùng checklist sau khi thiết kế hoặc rà soát một hệ thống:

| Nhóm | Câu hỏi kiểm tra |
|---|---|
| Policy | Thuật toán, key size, usage và provider có được phê duyệt không? |
| Generation | Khóa được sinh bằng CSPRNG, KeyGenerator, KeyPairGenerator hoặc KMS/HSM tin cậy không? |
| Storage | Key material có tách khỏi ciphertext và được bảo vệ bởi KMS/HSM/KeyStore phù hợp không? |
| Distribution | Khóa/credential có được phân phối qua kênh xác thực và bảo vệ không? |
| Access control | Quyền có theo least privilege, workload identity, JIT và separation of duties không? |
| Usage | Khóa có được dùng đúng purpose, algorithm và protocol không? |
| Rotation | Có version ID, write version, read compatibility và kế hoạch migration không? |
| Backup | Backup có được bảo vệ, restore thử và kiểm soát quyền không? |
| Compromise | Có playbook revoke, rotate, re-encrypt và điều tra không? |
| Destruction | Có xử lý replica, backup, cache, export và dependency trước khi destroy không? |
| Audit | Các thao tác vòng đời có audit và log không chứa key material không? |
| Testing | Có unit, integration, negative, recovery và provider/HSM test không? |

Checklist không thay thế việc kiểm tra bằng chứng. Với mỗi câu trả lời “Có”, cần xác định artifact hoặc bằng chứng: policy, cấu hình KMS, test report, audit event, recovery exercise, change record hoặc attestation của provider.

## 19. Các lỗi thường gặp khi áp dụng hướng dẫn

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Chỉ chọn thuật toán mạnh mà bỏ qua quản lý khóa | Khóa có thể bị lộ hoặc mất quyền kiểm soát | Quản lý toàn bộ lifecycle |
| Hardcode key trong source hoặc image | Khóa lan vào Git, artifact và bản sao | Lấy key reference/secret lúc runtime |
| Lưu key cạnh ciphertext | Một lần lộ dữ liệu có thể làm lộ luôn khóa | Tách quyền và nơi lưu khóa |
| Dùng một key cho nhiều purpose | Tăng blast radius và khó rotation | Tách key theo usage |
| Export raw key không cần thiết | Tạo thêm bản sao khó kiểm soát | Dùng KMS/HSM operation và non-exportable key |
| Rotation chỉ đổi alias | Ciphertext cũ có thể không xác định đúng version | Lưu key version ID trong metadata |
| Không kiểm thử backup restore | Có thể mất khả năng giải mã khi sự cố | Diễn tập recovery định kỳ |
| Chỉ xóa alias để tuyên bố destruction | Key material vẫn còn tồn tại | Xác minh object state và provider evidence |
| Không có incident playbook | Xử lý compromise chậm và thiếu nhất quán | Diễn tập revoke/rotate/re-encrypt |
| Coi Cheat Sheet là chứng nhận tuân thủ | Đánh giá sai mức bảo đảm | Đối chiếu tiêu chuẩn và yêu cầu áp dụng riêng |

## 20. Nguyên tắc triển khai an toàn

- Xây dựng policy mật mã trước khi tạo khóa; quy định algorithm, parameters, key usage, provider và lifecycle.
- Dùng CSPRNG hoặc KMS/HSM đáng tin cậy để sinh khóa; không tự tạo RNG.
- Tách key material khỏi ciphertext, source code, image và log.
- Ưu tiên KMS/HSM và envelope encryption khi kiến trúc phù hợp.
- Cấp quyền tối thiểu theo principal, key, operation và môi trường.
- Phân tách nhiệm vụ cho thao tác tạo, import, export, rotate, policy change và destroy.
- Gắn key version ID vào ciphertext/envelope và duy trì khả năng đọc dữ liệu cũ trong giai đoạn chuyển đổi.
- Bảo vệ backup, kiểm thử restore và kiểm kê mọi bản sao.
- Có playbook xử lý compromise và xác minh phạm vi dữ liệu phụ thuộc.
- Chỉ destroy sau khi xử lý dependency, backup, replica và retention.
- Audit đầy đủ nhưng không ghi key material, token hoặc plaintext.
- Kiểm thử provider, KMS/HSM, rotation, recovery, access denial và destruction trong môi trường cô lập.
- Dùng OWASP Cheat Sheet như hướng dẫn thực hành; đối chiếu yêu cầu pháp quy, tiêu chuẩn và chính sách nội bộ trước khi tuyên bố assurance hoặc compliance.

OWASP Key Management Cheat Sheet nhấn mạnh rằng bảo vệ dữ liệu phụ thuộc vào cách quản lý khóa trong toàn bộ vòng đời. Thuật toán phù hợp, nguồn sinh khóa tin cậy, nơi lưu trữ được bảo vệ, quyền truy cập tối thiểu, rotation có kiểm soát, backup/recovery và destruction có bằng chứng phải được thiết kế như một hệ thống thống nhất. Chỉ khi có policy, kiểm thử và audit tương ứng, tổ chức mới có thể đánh giá được mức bảo đảm thực tế của key management.

Tài liệu tham khảo:

- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html).
- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management.
- NIST SP 800-38D — Galois/Counter Mode (GCM) and GMAC.
- NIST SP 800-88 Rev. 2 — Guidelines for Media Sanitization.
- NIST SP 800-131A — Transitioning the Use of Cryptographic Algorithms and Key Lengths.
- NIST SP 800-133 — Recommendation for Cryptographic Key Generation.

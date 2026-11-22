# 11.8. Sao lưu, phục hồi và xử lý sự cố mất hoặc lộ khóa

## 1. Vì sao sao lưu khóa khác với sao lưu dữ liệu?

Trong một hệ thống dùng mật mã, **khóa** có thể là điều kiện duy nhất để giải mã cơ sở dữ liệu, phục hồi tệp, xác thực thông điệp, kiểm tra chữ ký cũ hoặc mở các khóa dữ liệu đã được bọc. Một bản sao lưu ciphertext còn nguyên vẹn **không có ích cho việc giải mã** nếu khóa cần thiết đã mất và không tồn tại phương án phục hồi hợp lệ.

Đồng thời, sao lưu khóa làm tăng số vị trí bí mật có thể bị đánh cắp. Vì vậy quản lý khóa phải cân bằng **tính sẵn sàng (availability)** với **tính bí mật, toàn vẹn, xác thực và khả năng kiểm soát sử dụng**.

Ba tình huống phải phân biệt:

1. **Khóa không truy cập được nhưng chưa có dấu hiệu bị lộ:** ví dụ node KMS tạm thời ngừng hoạt động, keystore bị xóa nhầm, thiết bị lưu khóa hỏng. Mục tiêu là phục hồi bí mật đúng phiên bản trong môi trường tin cậy, sau đó kiểm tra dữ liệu và ứng dụng. Không tự động kết luận khóa bị xâm phạm.
2. **Khóa bị mất vĩnh viễn:** không có bản sao, escrow, khả năng reconstruct/re-derive được phê duyệt hoặc cơ chế recover từ nhà cung cấp. Nếu dữ liệu chỉ được mã hóa dưới khóa đó, về nguyên tắc **không thể lấy lại plaintext bằng cách tạo khóa mới**. Đây chính là hệ quả của bảo mật mật mã.
3. **Khóa bị lộ hoặc nghi bị lộ (compromised/suspected compromise):** attacker có thể biết khóa hoặc dùng được chức năng ký/giải mã. **Chỉ restore bản sao hoặc đổi alias không làm khóa cũ an toàn lại.** Cần cô lập, xác định phạm vi, thay khóa, thay biện pháp bảo vệ dữ liệu, thu hồi quyền liên quan và xử lý hậu quả.

Bài này tập trung vào **vòng đời khóa** trong Java/JCA/JCE, không chỉ cách gọi `KeyStore.load`. Mục tiêu là xây được chính sách backup/restore, phân loại đúng mất và lộ khóa, vận hành sự cố, chọn khi nào *rotate*, *rewrap*, *re-encrypt* hay *revoke*, và hiểu giới hạn của việc cứu dữ liệu bằng bản sao lưu.

## 2. Thuật ngữ cần dùng nhất quán

| Thuật ngữ | Ý nghĩa | Cần nhớ |
| --- | --- | --- |
| **Backup (sao lưu)** | Bản sao được bảo vệ để phục hồi sau sự cố | Có lịch tạo, bảo vệ, thử phục hồi, giữ/xóa theo chính sách |
| **Recovery/restore (phục hồi)** | Khôi phục khả năng dùng đúng khóa/phiên bản cho chức năng được phép | Phải xác minh tính toàn vẹn và quyền khôi phục |
| **Archive (lưu trữ dài hạn)** | Giữ vật liệu hoặc metadata phục vụ mục đích truy cập cũ/đối soát | Không mặc định được dùng lại để tạo dữ liệu bảo vệ mới |
| **Key rotation** | Chuyển sang khóa/phiên bản mới cho thao tác mới | Không tự thay lớp mã hóa của ciphertext cũ |
| **Rewrap** | Giải bọc DEK rồi bọc lại **cùng DEK** bằng KEK mới | Không thay bí mật DEK dùng mã hóa payload |
| **Re-encrypt/rekey** | Giải mã dữ liệu cũ và mã hóa lại với **DEK mới, nonce mới** theo giao thức | Cần dữ liệu có thể truy cập và quyền dùng khóa cũ trong môi trường an toàn |
| **Revoke/disable** | Cấm hoặc giới hạn việc sử dụng khóa/chứng thư/credential | Không khiến bản sao khóa đã bị kẻ tấn công lấy trở nên vô dụng |
| **Destroy/crypto-erasure** | Hủy các bản sao key material theo chính sách, khiến dữ liệu mã hóa không thể phục hồi nếu không còn đường khác | Phải xét backup, archive, snapshot, replica và khóa dẫn xuất |
| **KeyId/keyVersion** | Định danh và phiên bản giúp tìm đúng khóa để giải mã/verify | Không được tự coi giá trị keyId từ client là chứng cứ tin cậy |

**Backup không giống replication.** Một hệ thống nhiều replica có thể cùng xóa nhầm hoặc đồng bộ khóa bị phá hoại đến tất cả bản sao. Một backup độc lập, bất biến hoặc cách ly có thể chống lỗi đó tốt hơn, nhưng cũng phải quản lý quyền đọc và kiểm tra restore.

**Backup không giống quyền sử dụng vĩnh viễn.** Khóa hết thời gian dùng để **tạo** ciphertext/chữ ký mới có thể còn cần để **giải mã** dữ liệu cũ hoặc **xác minh** chữ ký lịch sử. Chính sách phải phân biệt *originator-usage period* với *recipient-usage period* theo loại khóa và quy định áp dụng; khôi phục không có nghĩa mọi quyền tạo dữ liệu mới tự trở lại.

## 3. Không phải khóa nào cũng nên sao lưu theo cùng cách

Câu hỏi đầu tiên của một kế hoạch khôi phục: **khóa gì, ai sở hữu, dùng cho việc gì, không còn khóa thì ảnh hưởng thế nào?**

| Loại khóa | Khi mất | Chiến lược backup/restore cần cân nhắc | Khi nghi bị lộ |
| --- | --- | --- | --- |
| **DEK** (*data-encryption key*) đối xứng | Không giải mã được các bản ghi chỉ dùng DEK đó | Bọc DEK bởi KEK, giữ wrapped DEK và metadata; backup DEK riêng chỉ theo chính sách | Tạo DEK mới và **mã hóa lại** dữ liệu bị ảnh hưởng; đánh giá dữ liệu có thể đã bị đọc |
| **KEK** (*key-encryption key*) | Không giải bọc được các DEK dưới KEK đó | KMS/HSM versioning, backup hoặc dự phòng theo cơ chế được nhà cung cấp cho phép | Tạo KEK mới; *rewrap* các DEK còn tin cậy; nếu old wrapped DEK có thể đã bị attacker lấy, phải đánh giá **re-encrypt bằng DEK mới** |
| **Master/root key** | Có thể mất khả năng phục hồi nhiều nhánh khóa | Quy trình DR riêng, quorum, HSM replication/backup chính thức, nhiều miền lỗi | Sự cố nghiêm trọng: xác định toàn bộ key hierarchy và phạm vi ảnh hưởng, thay thế có kiểm soát |
| **Private key ký số** | Không tạo được chữ ký **mới** bằng identity/key cũ | Nói chung **hạn chế sao lưu** và không archive private signing key chỉ để kiểm tra chữ ký cũ; policy có thể yêu cầu sinh cặp mới | Ngừng ký, thu hồi/đánh dấu key compromised, phát hành public key/chứng thư mới, rà soát chữ ký phát sinh trong thời gian nghi vấn |
| **Private key giải mã/transport** | Có thể không giải mã được key material đã gửi cho public key tương ứng | Phục hồi được theo policy, bảo vệ như secret; không đồng nhất với signing key | Thay cặp khóa; phục hồi dữ liệu và thay bảo vệ nếu cần |
| **Public key/chứng thư** | Mất khả năng verify/định danh nếu thiếu trust metadata | Giữ bản sao công khai, cert chain, trust anchors và thông tin phiên bản | Khi private key tương ứng lộ, đánh dấu/thu hồi trust, không chỉ thay file public key |
| **HMAC key/API shared secret** | Không verify tag/token cũ; có thể gián đoạn giao thức | Backup theo mục đích, quản lý thời hạn và phiên bản; tránh nhân rộng bí mật không cần thiết | Rotate, từ chối tag/token tạo dưới khóa bị lộ theo policy; phối hợp đối tác |
| **Ephemeral session key** | Mất phiên tạm thời; có thể phải handshake lại | Thường **không backup**; tạo phiên mới | Hủy phiên, đàm phán lại khóa, điều tra phạm vi |
| **Password-derived key** | Không dẫn xuất lại được nếu mất password, salt hoặc tham số cần thiết | Bảo vệ password/credential theo policy; luôn giữ salt, thuật toán, chi phí và metadata không bí mật cần cho derivation | Thay credential/derived keys khi có thể; xem dữ liệu đã bảo vệ có bị lộ hay chưa |

**Điểm quan trọng về signing key:** hướng dẫn quản lý khóa NIST SP 800-57 Part 1 Rev. 5 nêu rằng việc backup **private signature key** không được khuyến khích trong đa số trường hợp và việc archive private signature key không phù hợp chính sách tài liệu đó. Việc giữ public key/certificate cho verify chữ ký lịch sử là chuyện **khác** với giữ private key để có thể tiếp tục ký. Luôn theo quy định cụ thể của tổ chức và ngành.

**Khóa không xuất được (non-exportable):** nếu private/secret key được tạo trong HSM hoặc KMS với chính sách không export, đừng cố lấy `getEncoded()` hay copy raw key để “backup”. Nhiều provider trả `null` hoặc từ chối export. Backup/replication phải đi qua chức năng **được HSM/KMS hỗ trợ** (secure key backup, HSM-to-HSM clone, multi-region replicated key, disaster-recovery domain), nếu có; những giải pháp này có giới hạn quyền, loại khóa, vùng địa lý và các điều kiện riêng.

## 4. Thiết kế envelope encryption để giảm phạm vi phục hồi

Với dữ liệu có quy mô lớn, nên cân nhắc mô hình *envelope encryption*:

- **DEK:** khóa ngẫu nhiên cho một đối tượng, nhóm đối tượng hoặc phân vùng theo chính sách. DEK dùng để mã hóa dữ liệu bằng AEAD, ví dụ `AES/GCM/NoPadding`.
- **KEK:** khóa dùng để *wrap/unwrap* DEK. KEK có thể được quản lý bằng KMS/HSM, và DEK khi lưu thường ở **dạng đã được bọc**.
- **Metadata:** gắn bản ghi với `keyId`, `keyVersion`, thuật toán, tham số, nonce/IV, AAD, version của record, wrapped DEK và các thông tin cần để khôi phục.

```text
                 KMS/HSM: KEK phiên bản v1
                         |
DEK ngẫu nhiên --------- wrap ---------> wrappedDEK(v1)
     |                                           |
AES-GCM(payload, IV, AAD)                        |
     |                                           |
     +---- lưu cùng record: ciphertext || tag ---+
                                + IV + AAD + keyId/keyVersion

Khi đọc:
  metadata + wrappedDEK -> KMS/HSM unwrap bằng KEK v1 -> DEK
  DEK + IV + AAD + ciphertext/tag -> AEAD decrypt + xác thực
```

Lợi ích: dữ liệu lớn không phải mã hóa lại chỉ vì **KEK thường kỳ được xoay**; có thể dùng `KEK-v2` bọc lại **cùng DEK** và cập nhật metadata atomically. Nhưng nếu **DEK** đã lộ, hoặc attacker có thể đã thu cả **KEK-v1** lẫn **wrappedDEK-v1** trước khi rewrap, việc đổi lớp bọc **không xóa khả năng giải mã của kẻ tấn công từ dữ liệu cũ**. Lúc đó cần đánh giá mã hóa lại payload với **DEK mới** và giới hạn tác động quá khứ.

Một thành công của `unwrap` chỉ nói có key material dùng được; không tự chứng minh requester được phép đọc tenant hoặc record. Authorization, audit, chính sách scope và kiểm tra tag vẫn cần thiết.

## 5. Phải sao lưu những gì để phục hồi *đúng khóa*?

### 5.1. Không chỉ có một file keystore

Một **bộ recovery** hữu ích có thể bao gồm:

1. **Vật liệu khóa được phép backup:** khóa hoặc bản sao *đã bọc/mã hóa* theo đúng chính sách; không export khóa non-exportable.
2. **Key inventory và mapping:** keyId, keyVersion, alias, owner/service, tenant, purpose, thuật toán, kích thước, thời điểm tạo/kích hoạt/hết hạn và trạng thái compromised/revoked.
3. **Định dạng và tham số mã hóa:** `AES/GCM/NoPadding`, IV/nonce, tag length, AAD và serialization/schema. Mất IV/AAD/tag có thể làm dữ liệu không giải mã/xác thực được dù có key.
4. **Thông tin về bọc khóa:** wrappedDEK, wrappingKeyId/version, thuật toán wrap và chính sách access vào KMS/HSM.
5. **Thông tin KDF (nếu có):** salt, KDF name/version, iterations hoặc work factor, output length, normalization/encoding. Salt thường không bí mật nhưng **cần đúng** để tạo lại key.
6. **Chứng thư và trust metadata:** public certificate chain, trust anchors, CRL/OCSP/policy hoặc thông tin kiểm tra chữ ký dài hạn khi trường hợp sử dụng yêu cầu.
7. **Dữ liệu đã mã hóa cùng snapshot/version phù hợp:** backup database/ciphertext, file objects, manifest/checksum, schema migration và logs cần để tái dựng state.
8. **Quy trình recovery:** tài liệu có version, người có quyền, nơi lấy backup, cách verify integrity, yêu cầu dual approval, điểm dừng khẩn cấp, rollback, audit và phương án hoạt động khi KMS region mất.

Ví dụ: sao lưu riêng `KeyStore` nhưng quên **entry password**, alias hay byte `iv` tương ứng trong database vẫn có thể dẫn đến *không thể phục hồi*; ngược lại, sao lưu tất cả dữ liệu mà chỉ lưu KEK trong cùng hệ thống đang bị xóa cũng có thể gây vòng lặp không khởi động được.

### 5.2. Phải phá vòng phụ thuộc khi bootstrap

**Anti-pattern:** backup database được mã hóa bằng key A; backup key A lại nằm trong chính database đó, còn hệ thống chỉ giải mã được database sau khi đã lấy được key A. Đây là vòng phụ thuộc không có recovery path.

Thiết kế giải pháp khởi động độc lập:

- KMS/HSM có khả năng phục hồi theo chính sách bên ngoài database chính.
- Một bản key backup hợp lệ được bảo vệ bằng cơ chế độc lập có đủ người/quyền để khôi phục khi prod không hoạt động.
- Credentials/approval để khôi phục **không** chỉ nằm trong ứng dụng hoặc tài khoản có thể mất cùng sự cố.
- Quy trình có thể thực hiện trong một **môi trường sạch** khi hệ thống production nghi bị xâm nhập.

### 5.3. Bản backup phải khớp phiên bản dữ liệu

Thay đổi khóa và rewrap có thể làm metadata/wrappedDEK thay đổi. Sao lưu database tại thời điểm T nhưng chỉ có KEK ở thời điểm T+1 hoặc T−1 có thể làm một phần dữ liệu không mở được.

Do đó cần:

- Giữ các phiên bản KEK cần cho **giải mã dữ liệu hợp lệ** đến hết thời hạn truy cập/retention theo chính sách.
- Ghi chính xác `keyVersion`/`wrappingKeyVersion` vào record.
- Cập nhật wrappedDEK và metadata **atomically** hoặc có kế hoạch migrate/retry idempotent.
- Xác minh khôi phục **từ snapshot thực tế**, bao gồm cả bản ghi cũ trước rotation, không chỉ kiểm tra bản ghi mới nhất.

Không xóa bản KEK cũ khi còn dữ liệu hợp lệ không có cơ chế mở bằng khóa mới, trừ khi chính sách **crypto-shredding** chủ đích chấp nhận mất khả năng giải mã.

## 6. Bảo mật bản sao lưu khóa: backup là tài sản rất nhạy cảm

Một bản sao khóa hữu dụng cho người vận hành **cũng có thể hữu dụng cho kẻ tấn công** nếu bị lộ. Mục tiêu không phải “có thật nhiều bản copy”, mà là có đủ **bản sao độc lập, được bảo vệ và kiểm thử được**.

### 6.1. Bảo vệ bí mật và tính toàn vẹn

- **Mã hóa key backup/wrapping:** dùng KMS/HSM hoặc cơ chế bảo vệ mạnh phù hợp loại key. Với password-based keystore như PKCS#12, mật khẩu cần được tạo và bảo vệ tốt; không sử dụng mật khẩu demo, mật khẩu ngắn hoặc hardcode trong source.
- **Kiểm soát IAM:** riêng quyền backup, đọc backup, restore, import key, quản lý KEK và quyền dùng khóa cho nghiệp vụ. Áp dụng **least privilege** và phân tách trách nhiệm.
- **Dual control/quorum:** phục hồi khóa gốc quan trọng có thể yêu cầu hai hoặc nhiều người phê duyệt, được audit, không để một tài khoản đơn lẻ tự export mọi thứ.
- **Bảo đảm integrity:** checksum để phát hiện hỏng; cơ chế xác thực như MAC/chữ ký số hoặc kiểm tra tích hợp của keystore/backup service để phát hiện sửa trái phép. **Checksum không khóa không đủ** để bảo vệ trước người có quyền sửa cả backup và checksum.
- **Bảo mật vận chuyển:** dùng kênh có xác thực và mã hóa khi chuyển backup qua mạng; tránh gửi raw key vào chat, email, issue tracker hoặc log.

### 6.2. Phòng ransomware, xóa nhầm và thiên tai

- Giữ backup có **lịch sử phiên bản**, cơ chế bất biến/không sửa được trong thời gian retention nếu phù hợp, và quyền xóa độc lập với quyền vận hành hệ thống chính.
- Đặt bản sao ở miền lỗi khác: zone/region độc lập hoặc offline khi mô hình rủi ro yêu cầu.
- Thường áp dụng nguyên tắc có bản sao độc lập (ví dụ mô hình **3-2-1** về dữ liệu) nhưng không xem một con số là **bảo đảm an ninh khóa**. Mỗi bản sao bí mật cũng mở thêm bề mặt tấn công; policy khóa phải đánh giá riêng.
- Kiểm soát retention, truy cập vào snapshot cũ, đối tác lưu trữ và chu trình xóa/hủy backup hết hạn.

**Bản sao bất biến chỉ ngăn một số kiểu sửa/xóa**; nó không ngăn kẻ có quyền đọc snapshot lấy raw key hay ciphertext. Cần kết hợp kiểm soát đọc và mã hóa.

### 6.3. Split knowledge và chia sẻ bí mật

Với root recovery material có giá trị cao, có thể dùng kỹ thuật **secret sharing** hoặc cơ chế quorum do HSM/vendor hỗ trợ. Ví dụ lược đồ k-of-n cho phép khôi phục khi có đủ mảnh được bảo vệ, giảm phụ thuộc một người.

Tuy nhiên:

- Đừng chia AES key bằng cách cắt các đoạn byte rồi tự gọi đó là Shamir Secret Sharing; cần lược đồ toán học và implementation chuẩn có xử lý lỗi.
- Mảnh khóa vẫn là bí mật; phải bảo vệ, đánh số, quản lý người giữ, tránh hai người cùng một domain lỗi và có quy trình chống lộ mảnh.
- Phải kiểm thử khôi phục thật trong môi trường kiểm soát. Quorum không thay thế audit hay phê duyệt.
- Nếu mất đủ nhiều mảnh dưới ngưỡng khôi phục, dữ liệu có thể **mất vĩnh viễn**.

### 6.4. Chống rò rỉ qua vận hành

Không in `SecretKey.getEncoded()`, private key, plaintext recovery password hay bytes chứa key vào CI logs, APM, exception text, crash dump, support ticket. Hạn chế heap dump/snapshot trên máy xử lý khóa. Java `Arrays.fill` trên một mảng chỉ là thao tác dọn **mảng đó**, không bảo đảm mọi bản sao đã biến mất khỏi JVM/provider/OS.

## 7. RTO, RPO và kiểm tra phục hồi

- **RTO (Recovery Time Objective):** thời gian gián đoạn tối đa có thể chấp nhận cho chức năng mã hóa/giải mã/xác minh.
- **RPO (Recovery Point Objective):** mức mất dữ liệu/trạng thái cho phép, ví dụ bản ghi metadata hay mapping key version. Với key material **không tái tạo được**, việc mất **một phiên bản khóa cần thiết** có thể khiến dữ liệu tương ứng không bao giờ phục hồi, dù bản ghi dữ liệu có backup.
- **Recovery rehearsal:** diễn tập định kỳ để kiểm tra không chỉ “file backup tồn tại” mà cả **mở được keystore và giải mã được dữ liệu mẫu thật** dưới key version đúng trong môi trường cô lập.

Một bài kiểm thử phục hồi tốt nên đo các mốc: lấy bản backup, xác nhận tính toàn vẹn, phê duyệt quyền, khởi tạo KMS/HSM, load key, khôi phục metadata/data, giải mã/verify bản ghi cũ và mới, vận hành với traffic giới hạn, hoàn tất audit. Ghi lại thời gian thực tế so với RTO/RPO.

**Không đưa khóa production ra máy phát triển chỉ để thử backup.** Dùng môi trường DR tách biệt, role có giới hạn hoặc test keys; đối với khóa production chỉ thực hiện quy trình phục hồi được phê duyệt, có kiểm soát và log phù hợp.

## 8. Quy trình phục hồi khi khóa mất nhưng KHÔNG nghi bị lộ

### Bước 1 — Phân loại và khoanh vùng sự cố

Xác định đây là **mất khả năng truy cập** (KMS down, quyền bị thu hồi nhầm), **hỏng key store**, **xóa nhầm key version**, hay **mất mọi bản sao**. Kiểm tra telemetry, lịch rotation, thay đổi IAM, keyId/version và thông báo của nhà cung cấp. **Đừng tạo key mới dưới cùng alias rồi mong giải mã được ciphertext cũ.**

Nếu phát hiện dấu hiệu truy cập trái phép hoặc không xác định được tính tin cậy, chuyển sang quy trình **nghi compromised**, không vô điều kiện restore rồi đưa khóa cũ vào production.

### Bước 2 — Xác nhận một nguồn backup đáng tin

Lấy manifest đã ký/được xác thực, snapshot tương ứng với phiên bản dữ liệu, kiểm tra nguồn lưu trữ, quyền đọc và tính toàn vẹn. Xác định **đúng bí mật** cần phục hồi (DEK, KEK, private decrypt key, metadata).

Nếu key non-exportable từ HSM/KMS, chỉ dùng tính năng sao lưu/replication/restore chính thức được hỗ trợ; **không cố dump raw key** để lách bảo vệ.

### Bước 3 — Khôi phục có kiểm soát

Phục hồi trong môi trường sạch, với phê duyệt theo policy. Kiểm soát secret handling, không log material, gắn alias/key version chính xác, ngăn nhầm tenant và đặt lại IAM. Nếu khóa cũ đã hết kỳ **tạo** bảo vệ mới, chỉ cho phép mục đích **đọc/giải mã** đã được phép.

### Bước 4 — Xác minh ứng dụng

Dùng dữ liệu kiểm tra đã biết để xác nhận key phục hồi đúng: giải mã AEAD thành công **và kiểm tra tag**, mở được bản ghi từ trước/sau rotation, không dùng sai algorithm/IV/AAD, các phiên bản khóa vẫn tra được. Rà soát quyền và audit, rồi cho traffic trở lại dần.

### Bước 5 — Điều tra nguyên nhân gốc

Nếu lỗi do policy/IAM, automation xóa key quá sớm, thiếu snapshot key metadata hoặc vùng DR không đủ, cập nhật quy trình và kiểm thử lại. Không chỉ giải quyết một yêu cầu restore duy nhất.

**Trường hợp không còn bản sao đáng tin:** nếu ciphertext được bảo vệ bởi một khóa ngẫu nhiên mạnh đã bị hủy và không còn recovery path, không có API Java nào “đoán lại khóa”. Có thể tìm các đường khôi phục *đã tồn tại* như wrappedDEK dự phòng hoặc vùng KMS dự phòng; nếu không có, phải công bố mức ảnh hưởng và phục hồi dữ liệu từ **nguồn plaintext hợp lệ khác**, nếu tồn tại. Không hạ chuẩn mật mã hoặc đưa dữ liệu sai ra làm dữ liệu đã phục hồi.

## 9. Khi khóa bị lộ hoặc NGHI bị lộ: incident response khác hẳn

**Nguyên tắc:** khi private/secret key có thể đã bị attacker sao chép, việc thay password bảo vệ file hoặc vô hiệu hóa một alias **không thu hồi được byte khóa đã lộ**. Kẻ tấn công có thể đã có key/ciphertext/tag/bản backup cũ. Cần xác định tác động đối với cả dữ liệu hiện tại và lịch sử.

### 9.1. Phát hiện, kích hoạt và bảo toàn chứng cứ

Các chỉ dấu: key export bất thường, bản keystore trong repository/public bucket, KMS decrypt/sign gọi từ nguồn không quen, private key xuất hiện trong CI logs, quyền cloud bị chiếm, bản backup bị tải trái phép, chứng thư hoặc token ký xuất hiện ngoài hệ thống.

Khi nghi vấn:

1. Kích hoạt quy trình incident response, xác định **incident commander**, các nhóm Security, SRE, application, compliance/pháp lý và owner dữ liệu.
2. **Hạn chế ngay khả năng sử dụng khóa**: tạm dừng endpoint ký/giải mã không cần thiết, vô hiệu hóa credential đã bị đánh cắp, cô lập workload và hạn chế quyền KMS. Các bước phải cân nhắc ảnh hưởng availability và thứ tự cho hệ thống tối quan trọng.
3. Bảo vệ log, dấu vết truy cập, phiên bản backup, audit KMS và cấu hình để điều tra; không trì hoãn containment chỉ vì muốn thu thêm bằng chứng.
4. Ghi rõ **thời điểm nghi bắt đầu và kết thúc**, service/tenant/key versions bị ảnh hưởng và phạm vi người có thể đã đọc hoặc sửa dữ liệu.

### 9.2. Tạo khóa mới trong miền tin cậy mới

Sinh **key material mới độc lập**, ưu tiên KMS/HSM/vùng tin cậy chưa bị xâm nhập, không chỉ sửa tên file hoặc thay `alias`. Nếu control plane, máy chủ hoặc IAM đã bị attacker chiếm, phải xử lý root cause và credential trước/sóng song khi đưa khóa mới vào; nếu không attacker có thể lấy ngay key mới.

Đổi cấu hình writer/service để **dừng dùng key bị lộ cho thao tác bảo vệ mới**. Duy trì quyền chỉ-đọc/giải mã cũ (nếu thực sự cần phục hồi dữ liệu và được phê duyệt) trong môi trường cô lập với thời hạn rất ngắn, rồi giảm quyền/hủy theo kế hoạch.

### 9.3. Xử lý tài sản đã bảo vệ bằng khóa lộ

| Khóa bị lộ | Hậu quả tiềm năng | Biện pháp thường cần |
| --- | --- | --- |
| **DEK** mã hóa dữ liệu | Attacker có thể đọc ciphertext tương ứng họ có được và tạo ciphertext/tag giả nếu nắm các tham số | Tạo **DEK mới**, mã hóa lại dữ liệu cần bảo vệ bằng nonce mới, đánh giá dữ liệu từng bị đọc/sửa |
| **KEK** bọc DEK | Attacker có thể unwrap những wrappedDEK có thể truy cập, kể cả trong backups cũ | Rotate KEK; **rewrap** DEK còn tin cậy; nếu old KEK + old wrappedDEK có thể đã lộ, xem DEK như compromised và **re-encrypt payload** |
| **Private signing key** | Attacker có thể ký dữ liệu/token/phần mềm giả | Dừng sign, thu hồi cert/trust, phát hành key mới, rà soát và có thể tái phát hành artefact, invalidation token/allowlist theo policy |
| **HMAC/API shared secret** | Attacker có thể tạo tag/token hợp lệ | Rotate/revoke shared secret, cập nhật tất cả bên tham gia, loại bỏ token/tag cũ theo cửa sổ ảnh hưởng |
| **TLS private key** | Có nguy cơ giả mạo endpoint và ảnh hưởng một số phiên theo giao thức/cipher suite | Thay keypair/cert, thu hồi cert khi phù hợp, cập nhật trust/deploy; đánh giá phiên lịch sử dựa vào cơ chế forward secrecy |
| **Root/master key** | Nhiều nhánh key hierarchy có thể lộ | Kích hoạt DR/IR mức cao, liệt kê toàn bộ khóa con và dữ liệu, thay thế theo dependency graph, giảm phạm vi và phối hợp với vendor |

**Không thể “làm cho dữ liệu đã bị đọc trở lại bí mật”.** Re-encrypt giúp bảo vệ bản **mới** sau khi khóa cũ không còn được dùng, nhưng không xóa ciphertext cũ hay plaintext attacker đã lấy. Retention và quyền truy cập vào snapshot cũ là một phần của đánh giá.

### 9.4. Rewrap KHÔNG luôn tương đương re-encrypt

Ví dụ cần phân biệt:

- **Đổi KEK định kỳ, không có dấu hiệu lộ:** một DEK vẫn bí mật có thể được bọc lại bằng KEK mới. Ciphertext của payload không đổi; thời gian migration thường thấp.
- **Lộ KEK nhưng các DEK và wrappedDEK cũ chắc chắn không lọt vào tay attacker theo threat model:** rewrap có thể là một phần biện pháp, nhưng phải đánh giá bằng chứng và các bản backup cũ; không dễ khẳng định chắc chắn.
- **Lộ DEK, hoặc lộ KEK + các wrappedDEK mà attacker có thể giữ:** thay KEK **không lấy lại tính bí mật** của DEK cũ. Cần **DEK mới** và re-encrypt dữ liệu; dữ liệu lịch sử đã bị copy có thể vẫn truy cập được bằng key cũ.
- **Lộ signing private key:** không có “rewrap signatures”. Chữ ký đã sinh cần được xét theo thời gian, quy trình ký, timestamp/evidence và chính sách tin cậy; việc phát hành khóa mới không tự làm các chữ ký giả thời kỳ cũ biến mất.

### 9.5. Thu hồi, thông báo và xác minh kết thúc

- Với chứng thư cần phát hành/kiểm tra cơ chế thu hồi như CRL/OCSP theo PKI áp dụng; lưu ý người nhận có thể cache, bỏ qua hoặc áp dụng chính sách khác. Chỉ “đã thu hồi cert” không đảm bảo mọi verifier ngay lập tức dừng tin khóa.
- Với JWT/token ký hoặc HMAC, phải xét token đã phát hành, TTL, keyId, session, cache và những verifier vẫn chấp nhận khóa cũ. Thay `kid` hoặc khóa sign mới không tự hủy token cũ khi verifier vẫn cho phép public key/secret cũ.
- Với dữ liệu có thể đã bị đọc hoặc sửa, đánh giá nghĩa vụ thông báo theo hợp đồng/pháp lý/quy định ngành. Không tự khẳng định đã có breach dữ liệu chỉ từ một log bất thường; phải phân loại và ghi rõ mức độ chắc chắn.
- Kiểm thử lại quyền, đo hoạt động bất thường sau rotation, đối soát số bản ghi được migrate, tag AEAD và khả năng đọc, rà soát snapshot cũ, kế hoạch xóa khóa cũ và bằng chứng audit.
- Sau sự cố, thực hiện postmortem và cập nhật quyền export/backup, IAM, DR, chính sách lưu key, logging, automation và drill.

## 10. Java 17+: ví dụ PKCS#12 backup và restore một AES SecretKey

Java cung cấp `java.security.KeyStore` để quản lý các entry khóa/chứng thư. Với JDK/provider hỗ trợ **PKCS#12** chứa `SecretKeyEntry`, ta có thể đặt một khóa AES trong keystore có mật khẩu bảo vệ, serialize keystore và load lại.

**Đây là bài demo kỹ thuật, không phải giải pháp backup production:** khóa được tạo ngẫu nhiên, các password cố định trong mã **chỉ để minh họa**, bản backup chỉ ở bộ nhớ cùng process, không có backup bất biến/offline, trust, HSM/KMS, quorum, audit hay DR. Không dùng password hoặc mẫu lưu backup này nguyên xi trong ứng dụng thật.

Chương trình làm bốn phép thử:

1. Tạo AES key và dùng AES-GCM mã hóa một chuỗi đơn giản.
2. Đưa key vào `KeyStore.SecretKeyEntry` với alias `dek-v1` và `KeyStore.PasswordProtection`, ghi keystore dạng PKCS#12 thành bytes.
3. Khởi tạo KeyStore **mới từ backup bytes**, lấy lại key bằng entry password và giải mã ciphertext. Bên khôi phục phải có **IV**, ciphertext và tag từ bản ghi dữ liệu; key một mình không đủ.
4. Thử entry password sai và một AES key khác để thấy restore/decrypt bị từ chối.

Tạo `KeyBackupRestoreDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.UnrecoverableKeyException;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class KeyBackupRestoreDemo {
    private static byte[] encrypt(SecretKey key, byte[] iv, byte[] plaintext)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        return cipher.doFinal(plaintext);
    }

    private static byte[] decrypt(SecretKey key, byte[] iv, byte[] encrypted)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
        return cipher.doFinal(encrypted);
    }

    public static void main(String[] args) throws Exception {
        // Demo-only passwords; never hardcode actual recovery credentials.
        char[] storePassword = {'d','e','m','o','-','s','t','o','r','e','-','p','a','s','s'};
        char[] entryPassword = {'d','e','m','o','-','e','n','t','r','y','-','p','a','s','s'};
        byte[] backupBytes = null;
        try {
            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(128);
            SecretKey originalKey = generator.generateKey();
            byte[] iv = new byte[12];
            new SecureRandom().nextBytes(iv);
            byte[] plaintext = "ho-so-du-lieu-v1"
                    .getBytes(StandardCharsets.UTF_8);
            byte[] ciphertextAndTag = encrypt(originalKey, iv, plaintext);

            KeyStore backupStore = KeyStore.getInstance("PKCS12");
            backupStore.load(null, storePassword);
            KeyStore.PasswordProtection protection =
                    new KeyStore.PasswordProtection(entryPassword);
            try {
                backupStore.setEntry("dek-v1",
                        new KeyStore.SecretKeyEntry(originalKey), protection);
            } finally {
                protection.destroy();
            }

            ByteArrayOutputStream sink = new ByteArrayOutputStream();
            backupStore.store(sink, storePassword);
            backupBytes = sink.toByteArray();

            KeyStore restoredStore = KeyStore.getInstance("PKCS12");
            restoredStore.load(new ByteArrayInputStream(backupBytes), storePassword);
            SecretKey recoveredKey =
                    (SecretKey) restoredStore.getKey("dek-v1", entryPassword);
            if (recoveredKey == null) {
                throw new IllegalStateException("Missing key alias");
            }
            System.out.println("Recovered alias exists: " +
                    restoredStore.containsAlias("dek-v1"));
            System.out.println("Restored decrypts payload: " +
                    Arrays.equals(plaintext,
                            decrypt(recoveredKey, iv, ciphertextAndTag)));

            boolean rejectedWrongEntryPassword = false;
            char[] wrongPassword = {'w','r','o','n','g'};
            try {
                restoredStore.getKey("dek-v1", wrongPassword);
            } catch (UnrecoverableKeyException expected) {
                rejectedWrongEntryPassword = true;
            } finally {
                Arrays.fill(wrongPassword, '\0');
            }
            System.out.println("Wrong entry password rejected: " +
                    rejectedWrongEntryPassword);

            SecretKey unrelatedKey = generator.generateKey();
            boolean rejectedWrongKey = false;
            try {
                decrypt(unrelatedKey, iv, ciphertextAndTag);
            } catch (AEADBadTagException expected) {
                rejectedWrongKey = true;
            }
            System.out.println("Unrelated key decrypt rejected: " +
                    rejectedWrongKey);
        } finally {
            Arrays.fill(storePassword, '\0');
            Arrays.fill(entryPassword, '\0');
            if (backupBytes != null) Arrays.fill(backupBytes, (byte) 0);
        }
    }
}
```

Biên dịch và chạy (Java 17+ với provider hỗ trợ PKCS#12 SecretKeyEntry và AES-GCM):

```bash
javac KeyBackupRestoreDemo.java
java KeyBackupRestoreDemo
```

Stdout đã kiểm chứng với OpenJDK/provider thử nghiệm:

```text
Recovered alias exists: true
Restored decrypts payload: true
Wrong entry password rejected: true
Unrelated key decrypt rejected: true
```

### 10.1. Điểm cần hiểu sau ví dụ

- `KeyStore.getInstance("PKCS12")` chỉ định **loại keystore**; `SecretKeyEntry` giữ key, `PasswordProtection` biểu diễn thông tin bảo vệ entry. `KeyStore.store` serialize bản backup; `load` và `getKey` khôi phục key theo alias.
- `storePassword` và `entryPassword` là hai **vai trò** bảo vệ: keystore integrity/load và khả năng lấy từng entry; provider có thể có giới hạn riêng về password và hỗ trợ loại entry. Không coi việc code chạy trên một provider là bảo đảm hành vi mọi PKCS#12 provider đều giống nhau.
- PKCS#12 là **định dạng container bảo vệ dữ liệu khóa**, không phải tự động là quy trình DR đủ IAM, audit, anti-ransomware, retention, multi-region và escrow. Password demo rất yếu, **không dùng thật**.
- `AES/GCM/NoPadding` xác thực ciphertext/tag: giải mã bằng key không liên quan bị từ chối với `AEADBadTagException` trong ví dụ. Đừng giải mã mà bỏ qua lỗi tag.
- `IV` dài 12 byte chỉ cho **một lần mã hóa trong demo**. Với GCM, mỗi lần mã hóa bằng cùng key cần IV/nonce duy nhất theo policy; không tái dùng IV cho payload mới.
- `PasswordProtection.destroy()` giúp xóa bản sao password bên trong chính object protection đó. `Arrays.fill` ở `finally` xử lý một số array do caller sở hữu, nhưng **không xóa chắc chắn mọi bản sao trong KeyStore, ByteArrayOutputStream, provider, JIT/GC hoặc RAM**.
- `restoredStore.getKey` cần alias và entry password; trong production còn cần đúng key version, authorization và trust vào nguồn backup. Nếu missing alias hoặc key sai, **không tạo một AES key ngẫu nhiên thay thế rồi gọi đó là restore**.
- Nếu nhà cung cấp KMS/HSM không cho export, ví dụ PKCS#12 này **không áp dụng trực tiếp**. Sử dụng cơ chế backup/DR chính thức của vendor, và không giảm policy non-exportable chỉ để chạy được demo.

### 10.2. Điều ví dụ KHÔNG chứng minh

- Không có thao tác ghi bản backup ra môi trường lưu trữ ngoài process nên **không** chứng minh khả năng sống sót sau khi mất máy.
- Không test restore từ nhiều region, password escrow độc lập, snapshot tương thích, IAM hoặc đối chiếu audit.
- Chương trình giữ `originalKey` và `restoredStore` trong cùng process; nó kiểm thử **đường serialize/load/getKey** nhưng chưa mô phỏng mất toàn bộ original memory và chạy trên máy sạch.
- Không khẳng định backup container không thể bị brute force nếu password yếu; không dùng password trong mã thật.
- Không xác thực người được phép restore, không quản lý rotation hoặc key-compromise incident.
- Không bảo đảm xóa key/backup bytes khỏi mọi nơi trong JVM và OS.

## 11. Runbook ngắn cho một ca phục hồi production

Giả sử hệ thống có dữ liệu `AES-GCM`, DEK được bọc bằng KEK của KMS:

### A. Khi dịch vụ bị mất quyền giải mã nhưng không nghi lộ khóa

1. Mở incident, xác định keyId/version, tenant, số bản ghi và lỗi cụ thể; giữ nguyên dữ liệu và metadata.
2. Kiểm tra khả năng dùng lại KMS replica, quyền IAM hoặc key version vẫn tồn tại. **Không** tự sinh key mới dưới version cũ.
3. Lấy backup hợp lệ có integrity và phê duyệt, khôi phục trong vùng sạch bằng chức năng được phép.
4. Test decrypt AEAD một tập bản ghi từ nhiều kỳ rotation; kiểm tra tag, AAD, IV và expected plaintext/hash không nhạy cảm.
5. Khôi phục traffic có quan sát, ghi audit, sửa nguyên nhân và diễn tập lại.

### B. Khi nghi khóa bị lộ

1. Chặn export/use trái phép, cô lập nguồn rò, bảo toàn chứng cứ, xác định blast radius và mọi bản sao backup.
2. Tạo key mới trong trust domain được kiểm soát; thay IAM/credential có liên quan.
3. Ngừng **encrypt/sign mới** bằng key nghi lộ. Xử lý những dữ liệu đang được bảo vệ bởi key đó theo phân loại DEK/KEK/signing key.
4. Với dữ liệu có nguy cơ bị đọc từ ciphertext cũ, re-encrypt dưới DEK mới nếu khả thi; với KEK rotation đơn thuần, rewrap có thể đủ nếu DEK vẫn được bảo mật theo đánh giá.
5. Revoke/deprecate cert/verification keys, API tokens, shared secrets, trust pin và cache theo tác động thực tế.
6. Kiểm thử version mới, kiểm tra migration đầy đủ, ghi nhận hạn chế của dữ liệu lịch sử và nghĩa vụ thông báo.
7. Hủy/dừng dùng key cũ theo retention/khả năng đọc cũ **và** chính sách compromised; không giữ mặc định một key đã lộ chỉ vì “có thể cần sau này”.

### C. Khi chỉ còn ciphertext, mất mọi khóa cần thiết

1. Kiểm tra backup/escrow/wrappedDEK/khả năng rederive đã được thiết kế từ trước.
2. Nếu không có đường phục hồi mật mã hợp lệ, ghi nhận **không thể giải mã** bằng khóa mới; cân nhắc nguồn dữ liệu gốc khác (nếu có) và quy trình thông báo/business continuity.
3. Xem lại thiết kế DR, redundancy, lifecycle key version và chính sách crypto-erasure để tránh tái diễn.

## 12. Bảng lỗi phổ biến khi sao lưu/khôi phục

| Lỗi | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Chỉ backup ciphertext, không có KEK/DEK recover path | Có dữ liệu nhưng không thể giải mã | Thiết kế đầy đủ key hierarchy và DR bootstrap |
| Chỉ giữ “khóa hiện tại”, xóa mọi version cũ | Dữ liệu mã hóa trước rotation không mở được | Retain key versions cần cho recipient-use theo policy |
| Backup keystore nhưng mất password/alias/metadata | Không load/getKey được hoặc dùng sai key | Tách credential escrow, inventory và test restore |
| Lưu backup key ở cùng máy/tài khoản cloud với primary | Một lần xóa/ransomware làm mất cả hai | Tách fault domain, quyền xóa, bản sao bất biến/cách ly |
| Đưa private key raw vào repo/CI/log | Nhân bản bí mật khó kiểm soát | Cấm export không cần thiết, rotate/IR nếu lộ |
| Đổi alias và tưởng đã rotate key | Bytes secret cũ không đổi | Tạo **key material** mới và cập nhật writer/policy |
| Lộ KEK nhưng chỉ rewrap, bỏ qua backup cũ | Attacker có thể vẫn unwrap old wrappedDEK | Đánh giá lịch sử; re-encrypt bằng DEK mới khi cần |
| Lộ DEK nhưng chỉ đổi KEK | Dữ liệu vẫn có thể bị giải mã bằng DEK đã lộ | Re-encrypt payload dưới DEK mới |
| Private signing key mất và restore không theo policy | Tăng bề mặt giả mạo chữ ký, có thể vi phạm chính sách | Ưu tiên tạo cặp mới; lưu public cert cũ cho verify |
| Restore từ backup chưa kiểm chứng trong prod đang bị chiếm | Kẻ tấn công lấy luôn khóa vừa phục hồi | Kiểm chứng trust, làm sạch môi trường và quyền trước |
| Chỉ kiểm tra checksum của file backup | Người sửa được cả file và checksum vẫn qua test | Dùng integrity/authenticity có khóa hoặc kiểm soát tương đương |
| Tạo AES key mới và ghi đè alias của key bị mất | Ciphertext cũ không giải mã được, có thể làm hỏng mapping | Giữ keyId/version bất biến; tạo alias/version mới đúng |
| Xem password cố định trong demo là an toàn | File P12 dễ bị brute force hoặc bị lộ trong code | Sinh/bảo quản credential thật theo chính sách |
| Không diễn tập | Backup tồn tại nhưng không phục hồi được dưới áp lực | Test từ backup thực tế, đo RTO/RPO, audit định kỳ |
| Không cập nhật verifier hoặc token cache sau compromise | Key bị lộ vẫn được tin để ký/xác thực | Revoke/distribute trust thay thế và kiểm tra mọi consumer |
| Dùng lại nonce AES-GCM sau restore/counter rollback | Có thể phá hỏng bảo mật AEAD khi reuse (key,nonce) | Quản lý uniqueness trên mọi phiên bản/replica; khi không chắc thì rotate key |

**Chú ý khi rollback database:** nếu hệ thống cấp phát AES-GCM nonce bằng counter, khôi phục snapshot cũ có thể làm counter quay lại giá trị đã dùng, gây **reuse (key, nonce)** trên dữ liệu mới. Phải thiết kế bộ cấp phát nonce chống rollback/đa writer, hoặc **đổi khóa mã hóa** trước khi tiếp tục phát sinh record theo policy. Đừng coi backup restore chỉ là vấn đề đúng key.

## 13. Checklist vận hành và các bài thực hành

### Trước sự cố

- [ ] Có danh mục keyId/version, algorithm, key owner, dùng để encrypt/decrypt/sign/verify/wrap, dữ liệu phụ thuộc và vùng lưu.
- [ ] Quy định rõ loại key nào được backup, loại nào không export, loại nào chỉ giữ public certificate; retention theo use period.
- [ ] Key backup có mã hóa/xác thực, quyền restore độc lập, dual control phù hợp, audit và bảo vệ khỏi xóa nhầm/ransomware.
- [ ] Metadata gồm IV/tag/AAD/KDF params/wrappedDEK/KEK version; database và key snapshots phục hồi tương thích.
- [ ] Có kế hoạch phục hồi khi KMS/HSM/region/account unavailable, gồm credential escrow và bootstrap không vòng phụ thuộc.
- [ ] Có giới hạn thời gian RTO/RPO và restore rehearsal dưới môi trường DR tách biệt.
- [ ] Có playbook **khác nhau** cho mất key, key unavailable, key compromised và mất cả key backup.
- [ ] Có chiến lược rotate/rewrap/re-encrypt, keyId migration, token/certificate revocation và log chứng cứ.

### Sau khi xử lý

- [ ] Đã kiểm tra AEAD tag/verify, dữ liệu từ nhiều phiên bản và tenant, không chỉ một object mẫu.
- [ ] Đã xác minh writer không còn dùng key cũ để bảo vệ dữ liệu mới nếu key đã hết hạn/compromised.
- [ ] Đã định danh bản sao cũ còn lại (backup/snapshot/cache/replica) và rủi ro key material lộ.
- [ ] Đã đóng incident, audit hoạt động restore, lưu bài học về permission, automation và monitoring.

### Tự kiểm tra

1. Nếu ciphertext và IV còn đủ nhưng **DEK mất vĩnh viễn**, tại sao tạo AES key mới không giúp decrypt?
2. Vì sao backup **private signing key** không nên coi giống backup **DEK** để giải mã dữ liệu cũ?
3. Phân biệt **restore**, **rotate**, **rewrap**, **re-encrypt**, **revoke** và **destroy** bằng một ví dụ AES-GCM có KEK.
4. Khi lộ KEK-v1, đổi sang KEK-v2 và rewrap toàn bộ DEK có đủ ngăn kẻ tấn công đã giữ bản wrappedDEK-v1 không? Điều gì cần thêm?
5. Chỉ có file `backup.p12` nhưng không có store/entry password và key mapping thì còn thiếu những điều kiện phục hồi nào?
6. Khi mất khóa do KMS outage nhưng không có dấu hiệu lộ, vì sao không nhất thiết phải re-encrypt toàn bộ database?
7. Tại sao **khôi phục key vào production vẫn còn malware** có thể khiến sự cố nghiêm trọng hơn?
8. Sau khi restore từ snapshot cũ, vì sao AES-GCM nonce counter cần được kiểm tra trước khi encrypt mới?
9. Một chữ ký số tạo trước khi private key bị nghi lộ có còn đáng tin không? Cần thêm bằng chứng, thời gian, cert revocation và policy nào?
10. Làm sao kiểm tra được backup thành công theo nghĩa **có thể phục hồi và dùng đúng key**, chứ không chỉ “file tồn tại”?

**Bài thực hành A:** chạy `KeyBackupRestoreDemo.java` rồi thử đổi alias `dek-v1` khi gọi `getKey`, hoặc nhập entry password sai; kết luận theo lỗi trả về. Chỉ dùng khóa và password **demo**.

**Bài thực hành B:** mô phỏng records theo `keyVersion=v1` và `v2`; viết migration giả lập chỉ đọc/giải mã dữ liệu v1, ghi mới bằng v2; tránh xóa v1 khi còn record hợp lệ phụ thuộc.

**Bài thực hành C:** tạo bảng diễn tập giả định “mất KEK, không nghi lộ” và “lộ KEK + wrapped DEK”. Liệt kê nguồn tin cậy, blast radius, bước containment, số data objects cần rewrap/re-encrypt, kiểm thử và điều kiện cho phép quay lại hoạt động.

**Bài thực hành D:** diễn tập một bản backup metadata thiếu `iv` hoặc sai `keyVersion` và một lần rollback nonce counter. Ghi rõ vì sao chỉ khôi phục secret key là chưa đủ và chiến lược ngăn reuse (key, nonce).

## 14. Tài liệu tham khảo chính thức

- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): quản lý vòng đời key material, backup, archive, recovery, compromised keys và khác biệt use period.
- [Java SE 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): `KeyStore.getInstance`, `load`, `setEntry`, `store`, `getKey` và các loại entry.
- [Java SE 17 — KeyStore.SecretKeyEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.SecretKeyEntry.html): entry chứa `SecretKey`.
- [Java SE 17 — KeyStore.PasswordProtection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.PasswordProtection.html): thông tin bảo vệ entry, sao chép password và `destroy`.
- [Java SE 17 — KeyGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): tạo khóa AES ngẫu nhiên với provider.
- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): AEAD, `AES/GCM/NoPadding`, xác thực tag và `AEADBadTagException`.
- [NIST SP 800-38D — GCM](https://csrc.nist.gov/pubs/sp/800/38/d/final): nguyên tắc về IV/nonce, mã hóa/xác thực dữ liệu bằng GCM.

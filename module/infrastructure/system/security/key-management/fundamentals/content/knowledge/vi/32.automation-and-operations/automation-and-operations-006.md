# Dual-read rotation

Dual-read rotation là chiến lược chuyển đổi khóa trong đó ứng dụng tạm thời có thể đọc dữ liệu được bảo vệ bằng cả khóa cũ và khóa mới, nhưng chỉ ghi dữ liệu mới bằng khóa mới. Mô hình này thường được gọi là dual-read, single-write. Nó cho phép thay khóa theo từng bước mà không buộc phải mã hóa lại toàn bộ dữ liệu trong cùng một thời điểm.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, dual-read rotation kết nối hoạt động xoay vòng khóa với tính liên tục dịch vụ, quản lý phiên bản key, envelope encryption, quyền truy cập, migration dữ liệu và kiểm toán. Thiết kế cần xác định chính xác khóa nào được dùng để đọc từng bản ghi, khi nào writer chuyển sang khóa mới, cách xử lý dữ liệu cũ và điều kiện thu hồi khóa cũ.

## 1. Dual-read rotation là gì?

Giả sử dữ liệu hiện tại được mã hóa bằng khóa K1. Tổ chức muốn chuyển sang K2. Nếu thay K1 ngay lập tức, ứng dụng có thể không đọc được những bản ghi vẫn còn ciphertext được mã hóa bằng K1. Nếu giữ K1 mãi mãi, khóa cũ tiếp tục có quyền giải mã và bề mặt rủi ro không được thu hẹp.

Dual-read rotation giải quyết quá trình chuyển đổi theo các bước:

- Reader hỗ trợ giải mã dữ liệu bằng K1 và K2.
- Writer được chuyển sang chỉ mã hóa dữ liệu mới bằng K2.
- Dữ liệu cũ được chuyển đổi dần từ K1 sang K2 khi có thể.
- Khi không còn dữ liệu hoặc bản sao cần K1, quyền sử dụng K1 được thu hồi và key được retire theo chính sách.

Mô hình này tạo một giai đoạn tương thích có kiểm soát. Ứng dụng biết chọn đúng key version dựa trên metadata của ciphertext hoặc encrypted data key.

~~~mermaid
flowchart TD
    A[Ciphertext cũ: K1] --> C[Reader hỗ trợ K1 và K2]
    B[Ciphertext mới: K2] --> C
    C --> D[Plaintext]
    E[Writer] --> F[Chỉ mã hóa bằng K2]
    F --> B
    G[Migration worker] --> H[Đọc dữ liệu K1]
    H --> I[Mã hóa hoặc wrap lại bằng K2]
    I --> B
~~~

## 2. Dual-read, single-write và dual-write

Trong rotation thông thường, dual-read không có nghĩa là ghi đồng thời hai bản ciphertext cho mỗi dữ liệu. Writer chỉ tạo bản mới bằng K2; reader hiểu được cả định dạng cũ và mới.

| Mô hình | Đọc | Ghi | Nhận xét |
|---|---|---|---|
| Single-key | Chỉ K1 | K1 | Trạng thái trước rotation |
| Dual-read, single-write | K1 và K2 | Chỉ K2 | Mô hình phổ biến để chuyển đổi an toàn |
| Dual-write | Có thể đọc K1/K2 | Ghi cả K1 và K2 | Tăng số bản sao, tạo vấn đề đồng bộ và xử lý lỗi kép |
| New-key only | Chỉ K2 | K2 | Trạng thái cuối sau khi migration hoàn tất |

Dual-write thường phức tạp hơn vì hai lần ghi có thể không cùng thành công, dữ liệu có thể lệch nhau và rollback khó xác định bản nào là nguồn sự thật. Chỉ dùng dual-write khi có yêu cầu kiến trúc rõ ràng, cơ chế đồng bộ và quy tắc xử lý partial failure.

## 3. Metadata để chọn đúng key version

Reader cần biết ciphertext hoặc encrypted data key được bảo vệ bằng key nào. Không nên thử lần lượt mọi khóa cho đến khi một khóa giải mã thành công. Cách đó làm tăng chi phí, che giấu lỗi metadata, có thể tạo đường downgrade và khiến việc kiểm toán khó hơn.

Metadata thường bao gồm:

- Key identifier hoặc logical key reference.
- Key version hoặc key generation.
- Thuật toán, mode và định dạng ciphertext.
- Nonce/IV và authentication tag nếu dùng AEAD.
- Encrypted data key nếu dùng envelope encryption.
- Context/AAD cần thiết để xác thực dữ liệu.
- Schema version để reader chọn đúng cách diễn giải.

Ví dụ metadata khái niệm:

~~~json
{
  "formatVersion": 2,
  "keyId": "customer-record-key",
  "keyVersion": "v2",
  "algorithm": "AES-256-GCM",
  "nonce": "base64-encoded-nonce",
  "ciphertext": "base64-encoded-ciphertext"
}
~~~

Đây là ví dụ cấu trúc, không phải định dạng bắt buộc của KMS. Metadata phải được xác thực hoặc ràng buộc với ciphertext bằng AAD/chữ ký phù hợp. Nếu attacker có thể sửa keyVersion hoặc algorithm mà không bị phát hiện, ứng dụng có thể chọn sai key hoặc xử lý dữ liệu theo chế độ yếu hơn.

Khi keyId hoặc keyVersion không được nhận diện, reader phải từ chối và ghi nhận lỗi an toàn. Không âm thầm dùng key mặc định hoặc bỏ qua kiểm tra phiên bản.

## 4. Các giai đoạn của dual-read rotation

Một quy trình có kiểm soát thường gồm:

1. **Inventory:** tìm tất cả nơi dữ liệu, backup, archive và encrypted data key đang dùng K1.
2. **Prepare K2:** tạo key version mới, kiểm tra policy, thuật toán, backup và khả năng khôi phục.
3. **Deploy dual-read:** triển khai reader có thể đọc cả K1 và K2 trong khi writer vẫn ghi K1.
4. **Verify compatibility:** xác minh mọi instance, batch job, consumer và công cụ khôi phục đều đọc được cả hai phiên bản.
5. **Switch writer:** đổi writer để mọi dữ liệu mới được mã hóa bằng K2.
6. **Migrate existing data:** chuyển dữ liệu cũ hoặc re-wrap encrypted data key theo thiết kế.
7. **Observe:** theo dõi số lần đọc K1, số bản ghi còn lại và lỗi migration.
8. **Retire K1:** khi đã thỏa điều kiện, loại bỏ quyền sử dụng K1, disable rồi destroy theo chính sách và retention.

~~~mermaid
flowchart TD
    A[Inventory dữ liệu và key K1] --> B[Tạo K2]
    B --> C[Deploy reader K1 + K2]
    C --> D[Kiểm thử mọi workload]
    D --> E[Chuyển writer sang K2]
    E --> F[Migration dữ liệu cũ]
    F --> G[Theo dõi K1 usage và dữ liệu tồn]
    G --> H{Còn phụ thuộc K1?}
    H -->|Có| F
    H -->|Không| I[Thu hồi quyền K1]
    I --> J[Disable / Retire K1]
    J --> K[Destroy theo retention và phê duyệt]
~~~

Thứ tự này giúp ứng dụng có khả năng đọc dữ liệu mới trước khi writer bắt đầu tạo dữ liệu bằng K2. Không chuyển writer trước khi tất cả reader cần thiết đã hỗ trợ định dạng mới.

## 5. Giai đoạn chuẩn bị key mới

Trước khi dùng K2, cần xác nhận:

- Thuật toán và key size được chính sách cho phép.
- K2 được tạo trong đúng KMS/HSM, account, project, tenant và region.
- Key policy cấp đúng quyền cho writer, reader và migration worker.
- Backup/recovery của K2 đáp ứng yêu cầu khôi phục dữ liệu.
- Key version metadata có thể lưu và đọc nhất quán.
- Ứng dụng và provider hỗ trợ thuật toán, tham số và key object mới.
- Có kế hoạch xử lý dữ liệu cũ, archive và bản sao ngoại tuyến.

Không tái sử dụng cùng key material dưới một alias mới để giả lập rotation. Rotation phải xác định rõ liệu key material mới có được tạo hay chỉ thay cách tham chiếu/phiên bản. Alias là tên trỏ tới key; đổi alias không đồng nghĩa tạo key mới.

## 6. Triển khai reader hỗ trợ hai phiên bản

Reader phải đọc metadata, xác định key version, lấy đúng key reference và thực hiện giải mã. Ví dụ pseudocode:

~~~java
byte[] decrypt(EncryptedRecord record) {
    KeyReference key = keyRegistry.resolve(
            record.keyId(),
            record.keyVersion());

    if (key == null || !key.isAllowedForDecrypt()) {
        throw new SecurityException("Unknown or unavailable key version");
    }

    return aeadDecrypt(
            key,
            record.nonce(),
            record.ciphertext(),
            record.authenticatedMetadata());
}
~~~

Đây là pseudocode; keyRegistry và aeadDecrypt cần được triển khai bằng KMS/provider và thư viện mật mã thực tế. Reader phải kiểm tra keyId/keyVersion, thuật toán, nonce, tag và AAD theo định dạng đã định nghĩa. Không log plaintext hoặc key material khi có lỗi.

Trong giai đoạn dual-read, key registry hoặc KMS mapping phải giữ được cả K1 và K2. Reader chỉ được phép dùng K1 để giải mã dữ liệu có metadata chỉ rõ K1; không nên tự động fallback sang K1 khi giải mã bằng K2 thất bại. Lỗi tag có thể chỉ ra ciphertext bị sửa hoặc AAD sai, không phải lý do để thử khóa cũ.

## 7. Chuyển writer sang key mới

Sau khi toàn bộ reader cần thiết đã được nâng cấp và kiểm thử, writer được cấu hình chỉ dùng K2 cho dữ liệu mới. Một số kiểm soát cần có:

- Key version dùng để ghi phải được cấu hình rõ ràng và có thể quan sát.
- Writer từ chối ghi nếu K2 không sẵn sàng; không tự quay lại K1 nếu chưa có quyết định rollback được phê duyệt.
- Metadata của ciphertext phải ghi đúng keyId/keyVersion và format version.
- Audit log ghi nhận key reference và thao tác, không ghi key bytes hoặc plaintext.
- Triển khai theo đợt để phát hiện lỗi tương thích trước khi chuyển toàn bộ workload.

Khi chạy nhiều instance, cần bảo đảm cấu hình writer nhất quán. Nếu một instance cũ vẫn ghi K1 sau cutover, số bản ghi phụ thuộc K1 sẽ tiếp tục tăng và điều kiện retire không thể đạt.

## 8. Migration ciphertext từ key cũ sang key mới

Nếu dữ liệu được mã hóa trực tiếp bằng K1, migration cần giải mã ciphertext bằng K1 rồi mã hóa plaintext bằng K2. Mỗi bản ghi cần được cập nhật nguyên tử để metadata và ciphertext luôn khớp.

~~~mermaid
flowchart LR
    A[Ciphertext K1] --> B[Decrypt bằng K1]
    B --> C[Plaintext trong bộ nhớ]
    C --> D[Encrypt bằng K2]
    D --> E[Ciphertext K2]
    E --> F[Atomic update metadata và ciphertext]
~~~

Quy trình cho từng bản ghi:

1. Đọc ciphertext, key version, nonce và AAD hiện tại.
2. Xác minh metadata và giải mã bằng đúng K1.
3. Tạo nonce mới và mã hóa plaintext bằng K2.
4. Cập nhật ciphertext, nonce, tag, key version và format metadata trong một transaction hoặc thao tác compare-and-swap.
5. Chỉ đánh dấu bản ghi hoàn tất sau khi dữ liệu mới được lưu bền vững.
6. Xóa bản sao plaintext tạm thời theo khả năng của runtime và không ghi ra log.

Không tái sử dụng nonce cũ khi mã hóa lại bằng khóa mới. Với AES-GCM, nonce phải duy nhất dưới mỗi khóa. Dùng nonce mới cho lần mã hóa mới giúp giảm rủi ro va chạm và tách biệt bản mã.

## 9. Envelope encryption: re-wrap DEK hay re-encrypt dữ liệu?

Trong envelope encryption, dữ liệu được mã hóa bằng Data Encryption Key (DEK), còn DEK được mã hóa/wrap bằng Key Encryption Key (KEK) do KMS/HSM quản lý. Khi rotation KEK, có thể chỉ cần re-wrap DEK.

### Re-wrap DEK

Nếu DEK vẫn an toàn và chỉ cần thay KEK:

1. Lấy encrypted DEK đang được wrap bằng KEK K1.
2. Dùng KMS/HSM giải mã hoặc re-encrypt encrypted DEK sang KEK K2.
3. Cập nhật encrypted DEK và metadata key version.
4. Giữ nguyên ciphertext dữ liệu vì DEK không thay đổi.

~~~mermaid
flowchart TD
    A[Ciphertext dữ liệu] --> D[Giữ nguyên]
    B[Encrypted DEK do KEK K1 wrap] --> C[Re-wrap bằng KEK K2]
    C --> E[Encrypted DEK mới]
    D --> F[Dữ liệu sau rotation]
    E --> F
~~~

Một số KMS hỗ trợ thao tác ReEncrypt hoặc chuyển đổi wrapped key trực tiếp trong dịch vụ, giúp tránh đưa plaintext DEK về ứng dụng. Nếu phải giải mã DEK trong ứng dụng, cần bảo vệ nó trong bộ nhớ, giới hạn quyền và xóa tham chiếu sau khi dùng.

### Re-encrypt dữ liệu bằng DEK mới

Nếu DEK bị nghi ngờ lộ, chỉ re-wrap DEK bằng KEK mới là không đủ: attacker đã có DEK cũ vẫn có thể giải mã ciphertext cũ. Khi đó cần tạo DEK mới, giải mã dữ liệu bằng DEK cũ trong môi trường được kiểm soát, mã hóa lại bằng DEK mới và wrap DEK mới bằng KEK mới.

| Tình huống | Hành động thường phù hợp |
|---|---|
| Chỉ rotation KEK theo cryptoperiod, DEK không bị lộ | Re-wrap encrypted DEK sang KEK mới |
| DEK bị lộ hoặc nghi ngờ compromise | Tạo DEK mới và re-encrypt dữ liệu |
| KEK bị lộ | Đánh giá phạm vi encrypted DEK, re-wrap bằng KEK mới; nếu plaintext DEK có thể đã bị lấy, đánh giá cả việc tạo DEK mới |
| Chỉ đổi alias hoặc policy | Không mặc nhiên cần re-encrypt; xác định liệu key material có thay đổi hay không |

## 10. Xử lý dữ liệu đồng thời thay đổi

Trong khi migration chạy, ứng dụng vẫn có thể cập nhật cùng bản ghi. Nếu migration ghi đè ciphertext mới hơn bằng bản chuyển đổi từ snapshot cũ, dữ liệu có thể bị mất hoặc quay về trạng thái cũ.

Các cách kiểm soát:

- Dùng optimistic locking với version number hoặc ETag.
- Chỉ cập nhật nếu keyVersion và rowVersion vẫn giống giá trị đã đọc.
- Nếu compare-and-swap thất bại, bỏ kết quả migration cũ và đọc lại bản ghi mới nhất.
- Thiết kế migration idempotent để chạy lại không làm hỏng dữ liệu đã chuyển.
- Dùng checkpoint và cursor bền vững để tiếp tục sau khi worker dừng.
- Giới hạn tốc độ migration để không làm cạn CPU, memory, KMS quota hoặc connection pool.

Ví dụ logic:

~~~text
record = read(id)
if record.keyVersion == K1:
    plaintext = decrypt(K1, record)
    replacement = encrypt(K2, plaintext)
    update record
      set replacement
      where id = record.id
        and keyVersion = K1
        and rowVersion = record.rowVersion
    if update_count == 0:
        retry from latest record
~~~

Nếu transaction thất bại sau khi mã hóa nhưng trước khi cập nhật, ciphertext mới chưa được commit và có thể được tạo lại. Nếu transaction đã commit nhưng worker chết trước khi ghi checkpoint, lần chạy lại phải nhận ra bản ghi đã ở K2 và bỏ qua.

## 11. Quyền KMS/HSM trong giai đoạn dual-read

Quyền truy cập cần được điều chỉnh theo từng vai trò:

| Principal | Quyền với K1 | Quyền với K2 |
|---|---|---|
| Runtime reader | Decrypt trong thời gian chuyển đổi | Decrypt |
| Runtime writer | Không cần Encrypt sau cutover | Encrypt hoặc GenerateDataKey |
| Migration worker | Decrypt | Encrypt/GenerateDataKey |
| Key administrator | Quản trị theo phê duyệt | Quản trị theo phê duyệt |
| Backup/restore worker | Decrypt nếu archive còn dùng K1 | Decrypt theo dữ liệu mới |

Không cấp quyền quản trị key cho runtime chỉ vì rotation đang diễn ra. Migration worker có thể cần quyền rộng hơn runtime, nhưng nên là principal riêng, có thời hạn và được audit.

Khi dữ liệu K1 đã được chuyển hết, thu hồi quyền Decrypt K1 khỏi runtime và migration worker theo kế hoạch. Sau đó kiểm tra backup, archive, snapshot, replica và dữ liệu ngoại tuyến trước khi disable hoặc destroy key. Việc thu hồi grant phải được xác minh trên tất cả lớp policy và session có liên quan.

## 12. Theo dõi tiến độ và tiêu chí retire key cũ

Không nên retire K1 chỉ vì migration job báo hoàn tất. Cần đo và xác minh:

- Số bản ghi còn tham chiếu K1.
- Số lần decrypt K1 từ runtime, batch job và migration worker.
- Số archive, backup, snapshot và replica còn cần K1.
- Tình trạng các hệ thống downstream và công cụ restore.
- Lỗi decrypt, lỗi tag, lỗi KMS và retry trong giai đoạn chuyển đổi.
- Kết quả restore thử từ backup sau khi chuyển đổi.
- Thời gian không còn request K1 đủ dài để bao phủ chu kỳ batch và workload ít chạy.

Metric hữu ích:

| Metric | Mục đích |
|---|---|
| Records by key version | Đếm dữ liệu còn dùng từng key version |
| Decrypt requests by key version | Theo dõi mức sử dụng K1/K2 |
| Migration completed/failed | Theo dõi tiến độ và lỗi |
| Migration retry/conflict count | Phát hiện cập nhật đồng thời hoặc lỗi lặp |
| Old-key access after cutover | Phát hiện writer/reader cũ hoặc phụ thuộc bị bỏ sót |
| KMS latency/throttling | Theo dõi tác động migration tới dịch vụ |

Tiêu chí retire phải tính cả retention. Một backup hợp lệ có thể còn dùng K1 trong nhiều tháng; nếu destroy K1 trước khi backup hết hạn hoặc được chuyển đổi, tổ chức có thể mất khả năng khôi phục dữ liệu.

## 13. Rollback trong dual-read rotation

Rollback phải được chuẩn bị trước khi chuyển writer. Reader mới nên tương thích với dữ liệu K1 và K2, còn phiên bản ứng dụng có thể rollback phải đọc được format và metadata mới.

Các nguyên tắc:

- Giữ K1 khả dụng cho decrypt trong thời gian rollback được phê duyệt.
- Không rollback ứng dụng về phiên bản chỉ đọc được K1 sau khi writer đã tạo dữ liệu K2.
- Nếu cần chuyển writer về K1, chỉ thực hiện khi K1 chưa bị compromise và policy cho phép.
- Không xóa K2 hoặc metadata K2 khi đã có dữ liệu được mã hóa bằng K2.
- Sau rollback, tiếp tục theo dõi bản ghi và request K1/K2; lập kế hoạch hoàn tất migration sau khi lỗi được xử lý.

Nếu K1 bị thu hồi do compromise confirmed, không dùng rollback như lý do để mở lại quyền K1. Khi đó cần quy trình emergency rotation, chấp nhận gián đoạn nếu cần và ưu tiên ngăn truy cập bằng key đã mất an toàn.

## 14. Phân biệt planned rotation và emergency rotation

Dual-read rotation phù hợp nhất với rotation có kế hoạch, khi K1 vẫn được xem là đủ tin cậy trong giai đoạn chuyển đổi. Khi K1 bị compromise, giữ khả năng decrypt K1 lâu hơn có thể làm tăng nguy cơ.

| Tình huống | Hướng xử lý |
|---|---|
| Rotation định kỳ, K1 chưa bị compromise | Dual-read, single-write; migration; retire theo retention |
| K1 hết cryptoperiod nhưng vẫn được phép decrypt dữ liệu cũ | Chuyển writer sang K2, giữ quyền đọc K1 có thời hạn |
| K1 bị nghi ngờ lộ | Giới hạn principal, điều tra và xác định mức độ; rút ngắn cửa sổ dual-read theo risk decision |
| K1 bị xác nhận lộ | Kích hoạt incident response, thu hồi quyền phù hợp, tạo key mới và đánh giá re-encryption; không mặc định giữ K1 mở để thuận tiện |
| K1 mất hoặc bị destroy nhầm | Thực hiện recovery từ backup/HSM backup nếu có; không giả định K2 có thể thay thế K1 cho ciphertext cũ |

Rotation không xóa được plaintext hoặc key material mà attacker đã lấy trước đó. Nếu K1 đã bị lộ, cần xác định dữ liệu nào có thể bị giải mã và thời gian compromise có thể bắt đầu từ khi nào.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chuyển writer sang K2 trước khi reader hỗ trợ K2 | Ứng dụng cũ không đọc được dữ liệu mới | Deploy và kiểm thử dual-read trước cutover |
| Reader thử mọi key nếu giải mã thất bại | Che giấu metadata sai, tăng bề mặt lỗi và nguy cơ downgrade | Chọn key theo keyId/keyVersion đã xác thực |
| Writer vẫn có instance ghi K1 | Dữ liệu cũ tiếp tục phát sinh, không thể retire K1 | Đồng bộ cấu hình và theo dõi write version |
| Re-wrap DEK khi DEK đã bị lộ | Ciphertext vẫn giải mã được bằng DEK cũ | Tạo DEK mới và re-encrypt dữ liệu |
| Re-encrypt dữ liệu nhưng không cập nhật metadata nguyên tử | Ciphertext và key version không khớp | Transaction hoặc compare-and-swap |
| Migration ghi đè bản ghi mới hơn | Mất cập nhật đồng thời | Optimistic locking và retry từ bản mới nhất |
| Destroy K1 quá sớm | Backup/archive hoặc bản ghi cũ không thể giải mã | Kiểm tra toàn bộ retention và restore trước retire |
| Giữ K1 vô thời hạn | Khóa cũ tiếp tục mở dữ liệu và quyền tích lũy | Đặt tiêu chí, owner và deadline retire |
| Không theo dõi decrypt K1 sau cutover | Bỏ sót consumer cũ hoặc truy cập bất thường | Audit theo key version và principal |
| Dùng alias mới nhưng key material không đổi | Rotation chỉ thay tên, không thay khóa | Xác minh key version/material thực tế |

## 16. Checklist triển khai

- [ ] Xác định rõ key material nào đang bảo vệ dữ liệu và mục tiêu rotation.
- [ ] Inventory ciphertext, encrypted DEK, backup, archive, snapshot và consumer phụ thuộc K1.
- [ ] Tạo K2 và xác minh thuật toán, policy, region, backup và khả năng khôi phục.
- [ ] Lưu keyId/keyVersion và metadata cần thiết cùng ciphertext.
- [ ] Deploy dual-read cho mọi reader trước khi chuyển writer.
- [ ] Kiểm thử đọc dữ liệu K1/K2 và từ chối key version không hợp lệ.
- [ ] Chuyển writer sang K2 và xác minh không còn ghi mới bằng K1.
- [ ] Chọn re-encrypt dữ liệu hay re-wrap DEK theo việc DEK có còn tin cậy không.
- [ ] Dùng nonce mới cho mỗi lần mã hóa mới và xác thực metadata bằng AAD.
- [ ] Dùng transaction/optimistic locking để tránh migration ghi đè dữ liệu mới.
- [ ] Theo dõi số bản ghi, decrypt request, lỗi, retry và KMS throttling theo key version.
- [ ] Xác minh backup/restore và consumer ít chạy trước khi retire K1.
- [ ] Thu hồi quyền K1, disable và destroy theo retention/phê duyệt.
- [ ] Giữ kế hoạch rollback tương thích với dữ liệu K2; không mở lại key đã compromise.

Dual-read rotation giúp chuyển đổi khóa mà vẫn duy trì khả năng đọc dữ liệu trong giai đoạn migration. Mô hình an toàn cần reader hỗ trợ phiên bản mới trước, writer chỉ ghi bằng key mới, metadata chọn đúng key, migration có tính nguyên tử và idempotent, cùng tiêu chí retire dựa trên dữ liệu, backup và audit thực tế.

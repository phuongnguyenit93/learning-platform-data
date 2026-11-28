# Yêu cầu cryptography

## 1. Đặc tả mật mã bắt đầu từ mục tiêu bảo vệ

**Cryptography** cung cấp các cơ chế như mã hóa, xác thực thông điệp, chữ ký, hàm băm và dẫn xuất khóa. Yêu cầu bảo mật phải xác định thuộc tính cần đạt, dữ liệu và đối phương liên quan, thay vì chỉ ghi tên một thuật toán.

Câu “dữ liệu phải được mã hóa bằng AES” chưa cho biết mode, cách sinh và giữ khóa, nonce, tính toàn vẹn, ràng buộc với tenant, cách xử lý lỗi hay điều kiện phục hồi. Một triển khai có AES vẫn có thể dùng sai mode, lặp nonce hoặc cho principal ngoài quyền gọi hàm giải mã.

Trong chương **Verification framework** của module yêu cầu bảo mật, mục tiêu là chuyển rủi ro thành điều kiện cụ thể, đo được và có thể kiểm chứng. Bài tham chiếu các nhóm yêu cầu của **ASVS 5.0.0 V11**, đồng thời xây một hồ sơ sản phẩm minh họa. ASVS nhấn mạnh inventory, triển khai mật mã đáng tin cậy, vòng đời khóa và khả năng thích ứng khi cơ chế cần thay đổi. [Nguồn: ASVS 5.0.0 — V11 Cryptography](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x20-V11-Cryptography.md).

Ví dụ xuyên suốt là lưu báo cáo nhạy cảm trong object storage. Bên có bản sao storage không được đọc nội dung chỉ từ dữ liệu lưu; sửa ciphertext hoặc chuyển nó sang report/tenant khác phải bị phát hiện; chỉ caller có quyền mới được yêu cầu giải mã.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Chọn thuộc tính bảo vệ và loại cơ chế phù hợp với từng tài sản.
2. Viết profile có thuật toán, tham số, format, phạm vi khóa và hành vi lỗi rõ ràng.
3. Đặc tả sinh, sử dụng, rotation, thu hồi, phục hồi và hủy khóa.
4. Liên kết yêu cầu với điểm cưỡng chế và bằng chứng kiểm thử.
5. Phân biệt triển khai đúng một cơ chế với kết luận bảo mật cho toàn hệ thống.

## 2. Chọn đúng thuộc tính và cơ chế

### 2.1. Những cơ chế không thay thế nhau

| Cơ chế | Thuộc tính chính | Điều không tự được bảo đảm |
|---|---|---|
| Mã hóa | Giữ bí mật nội dung trước bên không có khóa | Tính toàn vẹn nếu cách mã hóa không có xác thực; quyền người gọi |
| AEAD | Mã hóa có xác thực và ràng buộc dữ liệu liên kết | Chống replay hoặc xác minh quyền nghiệp vụ một cách tự động |
| Hàm băm không khóa | Tạo digest hỗ trợ các cấu trúc bảo mật phù hợp | Xác thực nguồn trước bên có thể sửa cả dữ liệu lẫn digest |
| MAC/HMAC | Xác thực/toàn vẹn giữa các bên giữ khóa chung | Phân biệt người ký trong một nhóm cùng giữ khóa; bên xác minh cũng có thể tạo MAC |
| Chữ ký số | Xác minh thông điệp theo khóa công khai tương ứng | Tính bí mật nội dung; sự tin cậy của danh tính nếu chưa có trust binding |
| Password hashing/KDF | Tăng chi phí đoán mật khẩu và hỗ trợ xác minh | Đảm bảo mật khẩu yếu không bao giờ bị đoán; thay thế rate limit |
| TLS hoặc giao thức kênh được bảo vệ | Bảo vệ dữ liệu trên kênh và xác minh peer theo cấu hình | Bảo vệ mọi bản sao lưu trữ hoặc một endpoint đã bị chiếm quyền |

Mỗi mục đích cần có khóa, ngữ cảnh và chính sách riêng phù hợp. Không dùng một chuỗi bí mật làm đồng thời khóa mã hóa, khóa MAC và khóa ký token chỉ vì thư viện nhận cùng kiểu dữ liệu bytes.

### 2.2. Đặt lớp bảo vệ đúng với đối phương

Mã hóa volume có thể bảo vệ một loại tình huống mất thiết bị hoặc bản sao dữ liệu, nhưng không tự chặn một tiến trình được cấp quyền đọc volume. Mã hóa ở tầng ứng dụng có thể giảm quyền đọc của storage, song tiến trình ứng dụng có quyền giải mã vẫn phải được bảo vệ.

OWASP khuyến nghị chọn lớp mã hóa theo threat model và ưu tiên mode có xác thực khi phù hợp. [Nguồn: OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html).

Trong ví dụ, encrypted object không thay thế phân quyền report. Nếu API cho người dùng A yêu cầu giải mã report của B, dữ liệu vẫn có thể bị lộ qua đúng hàm giải mã được cấp quyền. Cần đặc tả cả khả năng đọc ciphertext, khả năng dùng khóa và khả năng nhận plaintext.

## 3. Mô hình đe dọa và hồ sơ yêu cầu

### 3.1. Các kịch bản cần kiểm soát

| Mã rủi ro | Kịch bản | Điều cần kiểm chứng |
|---|---|---|
| R1 | Đọc trộm storage, backup hoặc kênh truyền | Bản sao trong phạm vi không đủ để khôi phục nội dung ngoài quyền |
| R2 | Sửa ciphertext, metadata hoặc chuyển dữ liệu sang ngữ cảnh khác | Cơ chế xác thực phát hiện và không phát plaintext trước kết luận |
| R3 | Sinh khóa/nonce không phù hợp hoặc tái sử dụng ngoài giới hạn | Nguồn sinh, phạm vi duy nhất và hành vi khi retry/restart |
| R4 | Principal ngoài quyền dùng khóa hoặc dùng nhầm môi trường/mục đích | Policy tại ứng dụng và key service, binding đúng resource |
| R5 | Lộ khóa, rotation sai hoặc hủy key cũ quá sớm | Thu hồi đầu cuối, migration và khả năng phục hồi theo dữ liệu |
| R6 | Chọn sai primitive, tham số hoặc tự viết cơ chế không được đánh giá | Profile và implementation được phê duyệt, test phù hợp |
| R7 | Lỗi giải mã, key service hoặc input quá cỡ tạo oracle/rò dữ liệu | Xử lý lỗi an toàn, giới hạn tài nguyên và không fallback mất bảo vệ |
| R8 | Báo cáo/test sai revision hoặc bỏ đường crypto ít được dùng | Inventory và bằng chứng theo artifact/configuration/platform |

### 3.2. Một yêu cầu mật mã cần những trường nào?

| Trường | Ví dụ cần làm rõ |
|---|---|
| Dữ liệu và vòng đời | Báo cáo, bản xuất, tệp tạm, log và backup nào nằm trong phạm vi? |
| Thuộc tính và đối phương | Bí mật trước storage reader, phát hiện sửa đổi, chống giả mạo hoặc replay? |
| Profile | Thuật toán/mode, độ dài khóa, tag, nonce và format/version được phép |
| Key binding | Khóa nào, ai dùng được, môi trường/tenant/mục đích và hạn dùng |
| Dữ liệu được xác thực | Metadata nào đi vào AAD/MAC/chữ ký; nguồn có thẩm quyền của chúng |
| Lỗi và giới hạn | Từ chối lúc nào, dữ liệu nào không được công bố, byte/time/RAM theo hợp đồng |
| Vòng đời | Rotation, compromise, decrypt lịch sử, migration và điều kiện hủy |
| Bằng chứng | Test vector, test âm, review, cấu hình provider, audit và phục hồi |

Một lựa chọn thuật toán cần được đánh giá cùng độ dài khóa và tham số thực, không chỉ tên thuật toán. Nếu sản phẩm có yêu cầu đối với module được kiểm định, phải xác minh đúng module/version/cấu hình tương ứng; dùng một thuật toán được chấp nhận không tự chứng minh toàn ứng dụng có chứng nhận đó.

## 4. Profile thuật toán, randomness và nonce

### 4.1. Profile được phê duyệt và khả năng từ chối

Ứng dụng cần allowlist profile theo mục đích và phiên bản. Caller không được chọn thuật toán tùy ý, giảm tag, đổi mode hoặc cung cấp khóa để bypass chính sách. Profile lạ, tham số không đúng hoặc metadata không hợp lệ phải bị từ chối theo hợp đồng.

Tên “AES” chưa đủ xác định một phép mã hóa an toàn. Với dữ liệu mới của ví dụ, nhóm chọn một profile AEAD được quản lý; không tự fallback sang mode khác khi provider không hỗ trợ. Các cơ chế cũ phục vụ migration phải có phạm vi đọc riêng và điều kiện ngừng dùng, không mở lại cho mọi thao tác ghi mới.

### 4.2. Randomness phải theo đúng mục đích

| Giá trị | Yêu cầu cần làm rõ |
|---|---|
| Khóa bí mật | Nguồn CSPRNG/key generation được tin cậy, đủ độ dài và phạm vi sử dụng |
| Token cần không đoán được | Entropy theo profile; mã hóa Base64/hex không tự tạo entropy |
| Nonce/IV | Điều kiện duy nhất/khó đoán đúng với thuật toán, không áp một quy tắc cho mọi mode |
| Salt mật khẩu | Riêng cho từng bản ghi theo cơ chế password hashing; không phải khóa bí mật |

Trong Java, một API như `SecureRandom` là ví dụ nguồn phù hợp cho nhu cầu mật mã khi dùng đúng; các PRNG thông thường phục vụ mô phỏng không được dùng thay cho key/token bảo mật. [Nguồn: OWASP Cryptographic Storage — Secure Random Number Generation](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html#secure-random-number-generation).

Không tự seed nguồn mật mã bằng timestamp, ID người dùng hoặc một hằng số. Khi nguồn sinh trả lỗi, thao tác phụ thuộc nó phải dừng theo chính sách, không dùng chuỗi mặc định. Test phân bố hoặc việc không thấy trùng trong một mẫu hữu hạn không chứng minh nguồn có tính bảo mật.

### 4.3. Uniqueness của GCM cần được thiết kế

Với GCM, không được lặp IV/nonce cho các lần mã hóa dưới cùng khóa. Vi phạm có thể phá các bảo đảm bí mật/xác thực; random nonce hữu hạn vẫn cần giới hạn và thiết kế phù hợp, không phải bảo đảm tuyệt đối không trùng. AAD được xác thực nhưng không được mã hóa. [Nguồn: NIST SP 800-38D](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf).

Một thiết kế dùng một khóa cho rất nhiều bản ghi phải quản lý giới hạn số lần dùng, chiến lược nonce và tính bền vững qua restart, nhiều instance, restore và retry. Không chỉ kiểm tra một counter trong RAM của một process.

Hồ sơ ví dụ ở phần sau chọn cách cấp DEK mới cho từng lần mã hóa object version bất biến, với ticket mã hóa một lần. Nếu phải retry một phép mã hóa đã thất bại, lấy DEK/nonce mới; nếu chỉ truyền lại đúng ciphertext đã hoàn tất thì đó là thao tác sao chép bytes, không phải mã hóa plaintext lần nữa bằng cùng cặp khóa/nonce.

## 5. Ví dụ: envelope encryption cho báo cáo

### 5.1. Hợp đồng của profile minh họa

**DEK** là khóa mã hóa dữ liệu; **KEK** là khóa dùng bảo vệ khóa dữ liệu. Envelope encryption giữ ciphertext cùng DEK đã được wrap, trong khi KEK được quản lý theo policy riêng. Ví dụ này là đặc tả kiến trúc; triển khai phải dùng thư viện/định dạng và cơ chế wrap đã được đánh giá, không tự viết primitive hoặc giao thức mật mã.

| Thuộc tính | Profile `report-aead-v1` của ví dụ |
|---|---|
| Nội dung | Một phiên bản báo cáo bất biến, tối đa 1 MiB plaintext |
| Mã hóa | AES-256-GCM qua implementation được phê duyệt |
| DEK | 256 bit, sinh từ nguồn được tin cậy, mới cho mỗi lần mã hóa |
| Nonce | 96 bit, theo cơ chế sinh đã chấp nhận; ticket DEK chỉ dùng mã hóa một lần |
| Tag | 128 bit; không chấp nhận tag bị rút ngắn |
| AAD | Version/profile, môi trường, tenant, report ID, object version và purpose theo biểu diễn canonical đã đặc tả |
| Wrap DEK | Key service/KMS với key binding và authenticated context tương ứng |
| Key access | Danh tính workload đúng môi trường/mục đích và quyền report đã được kiểm tra |
| Cache DEK | Không giữ qua các request trong hồ sơ cơ sở của ví dụ |
| Metadata ngoài body | Tối đa 8 KiB theo schema của profile; kiểm tra trước cấp phát không giới hạn |

Các độ dài và giới hạn ở bảng là profile minh họa, không thay thế đánh giá cho mọi sản phẩm. `1 MiB = 1.048.576 byte`, `1 KiB = 1.024 byte`. Format thực cần xác định rõ giới hạn ở bytes đã decode, phần header và cách parser kiểm tra trước khi cấp phát.

### 5.2. Metadata cần đủ để xác minh và phục hồi

```yaml
envelope_version: 1
crypto_profile: report-aead-v1
key_ref: kms://production/report-data
key_version: immutable-version-reference
wrapped_dek: BASE64_PLACEHOLDER
nonce: BASE64_PLACEHOLDER
ciphertext: BASE64_PLACEHOLDER
tag: BASE64_PLACEHOLDER
context:
  environment: production
  tenant_id: tenant-fixture
  report_id: report-fixture
  object_version: version-fixture
  purpose: report-storage
```

Đây là schema mô tả, không phải format có thể dùng nguyên văn cho một KMS. Các placeholder không phải khóa, nonce hoặc ciphertext thực. Metadata không mặc nhiên bí mật nhưng vẫn cần phân quyền và tính toàn vẹn; tenant/report ID cũng có thể là thông tin nhạy cảm theo hệ thống.

AAD phải dùng biểu diễn duy nhất đã đặc tả, chẳng hạn encoding có phân định độ dài và phiên bản, không ghép chuỗi mơ hồ. Bên đọc dựng expected context từ danh tính và record có thẩm quyền, không tin toàn bộ `context` do envelope tự khai.

Các trường wrap có thể cần đổi khi rewrap KEK. Profile phải phân định context bất biến được AEAD bảo vệ với metadata wrap được cơ chế wrap/binding của key service bảo vệ. Không vô tình đưa một trường cần đổi vào AAD rồi giả định có thể sửa nó mà không xác thực lại dữ liệu.

### 5.3. Luồng đọc và giải mã tham chiếu

```text
read_report(request):
    context = verified_identity_and_tenant(request)
    grant = authorize_exact_report_version(context, request.report_id)
    envelope = load_bounded_envelope(grant.object_reference)
    profile = require_approved_profile_and_schema(envelope)
    expected = build_canonical_context_from_trusted_record(grant, profile)
    require envelope.context matches expected
    require key_reference_is_allowed_for(grant, profile, envelope.key_ref)

    dek = NONE
    try:
        dek = key_service.unwrap_as_authorized_workload(
            envelope.wrapped_dek,
            allowed_key_version=envelope.key_version,
            authenticated_context=expected
        )
        plaintext = approved_aead.decrypt_and_authenticate_complete(
            key=dek,
            nonce=envelope.nonce,
            ciphertext=envelope.ciphertext,
            tag=envelope.tag,
            aad=expected,
            profile=profile
        )
        audit_success_without_sensitive_values(grant, envelope.key_version)
        return plaintext_to_authorized_consumer(plaintext)
    finally:
        release_key_material_with_platform_supported_protection(dek)
```

Các hàm là hợp đồng trách nhiệm, không phải API có sẵn. Quyền nghiệp vụ phải kiểm tra trước khi dùng capability giải mã; key service cũng phải cưỡng chế quyền của workload. `key_ref`/version từ envelope chỉ được dùng sau khi ràng buộc với tập được cho phép, không biến thành một API unwrap tùy ý bằng quyền hệ thống.

Không phát plaintext cho caller, parser tiếp theo hoặc log trước khi xác minh tag hoàn tất. Nếu API streaming có thể trả bytes trước kết luận xác thực, cần giữ riêng có giới hạn hoặc dùng cơ chế framing đã được đánh giá với hợp đồng xác thực riêng; không bỏ qua điểm này chỉ để giảm RAM.

AEAD không tự chứng minh dữ liệu là version mới nhất hoặc thao tác chưa từng xảy ra. Expected object version, quyền truy cập và các điều kiện replay/freshness phải đến từ hợp đồng ứng dụng. Copy lại một envelope hợp lệ sang record khác không được mở đường đọc vì tag vẫn đúng trong ngữ cảnh gốc.

### 5.4. Luồng ghi và ticket mã hóa một lần

```text
write_report_version(request):
    grant = authorize_new_immutable_version(request)
    plaintext = receive_and_validate_bounded_report(max_bytes=1MiB)
    expected = canonical_context_from_authoritative_grant(grant)
    ticket = issue_fresh_data_key_ticket(grant, expected, report_aead_v1)

    try:
        # Chuyển trạng thái bền vững trước khi gọi primitive.
        require consume_ticket_atomically_for_one_encryption(ticket)
        sealed = approved_aead.encrypt_and_authenticate(
            key=ticket.dek,
            nonce=ticket.nonce,
            plaintext=plaintext,
            aad=expected,
            profile=report_aead_v1
        )
        envelope = assemble_bounded_envelope(sealed, ticket.wrapped_key, expected)
        persist_and_publish_exact_immutable_version(envelope, grant)
    finally:
        retire_ticket_even_if_attempt_outcome_is_unknown(ticket)
        release_key_material_with_platform_supported_protection(ticket.dek)
```

Ticket là đối tượng điều phối của thiết kế minh họa, không phải bảo đảm mặc định của KMS hoặc AEAD. Nó ràng buộc DEK, nonce, purpose và object version; cấp mới phải thực sự sinh vật liệu khóa mới bằng cơ chế được phê duyệt. Một ticket không được phát lại sau restart, restore hoặc retry. Nếu trạng thái tiêu thụ không xác định, bỏ ticket và cấp mới thay vì thử lại bằng cùng vật liệu.

Giới hạn một lần mã hóa không giới hạn số lần đọc một ciphertext hợp lệ đã lưu. Retry truyền bytes đã hoàn tất có thể dùng lại đúng envelope; phải giữ cùng nội dung và binding, không gọi primitive lần nữa với plaintext có thể đã đổi. Hai worker cạnh tranh cùng report version cần cơ chế publish/idempotency để chỉ công bố kết quả được cho phép.

Thiết kế này giảm việc phải quản lý hàng triệu nonce dưới một DEK dùng chung, nhưng vẫn phụ thuộc chất lượng nguồn sinh, cơ chế ticket và phạm vi khóa. Kiểm thử phải chủ động buộc cấp trùng ticket để kiểm tra khả năng chặn; chỉ lấy mẫu thấy DEK/nonce khác nhau chưa đủ chứng minh tính đúng.

## 6. Vòng đời khóa, rotation và phục hồi

### 6.1. Tách khóa và trách nhiệm

Key inventory cần ghi mục đích, môi trường, consumer, thuật toán/profile, key ID/version, nơi được phép dùng, dữ liệu đang phụ thuộc và owner. Không lưu raw key vào inventory. Quyền sinh/wrap/unwrap, quản trị policy và hủy key cần được cấp theo trách nhiệm, không gom vào principal runtime có quyền rộng.

OWASP hướng dẫn quản lý khóa theo vòng đời, gồm sinh, phân phối, lưu, compromise, phục hồi và hủy. [Nguồn: OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html).

Khóa giữa production/staging và giữa mã hóa/MAC/ký cần được tách theo thiết kế. Nếu dùng key derivation cho các mục đích khác nhau, phải dùng KDF và domain separation được phê duyệt; không tự lấy substring hoặc hash tùy ý của một master secret.

### 6.2. Rotation không phải một thao tác duy nhất

| Thay đổi | Có thể giữ nguyên điều gì? | Điều phải xác minh |
|---|---|---|
| Rewrap DEK bằng KEK mới | Có thể giữ DEK và ciphertext nếu profile cho phép | Wrap/context/version mới, quyền mới và khả năng đọc cũ đúng hạn |
| Thay DEK hoặc profile mã hóa dữ liệu | Không mặc định giữ ciphertext/tag cũ | Mã hóa lại với khóa/nonce mới và cập nhật metadata có kiểm soát |
| Thay signing/MAC key | Thông điệp cũ có thể còn cần xác minh theo policy | Trust, thời gian chấp nhận, revocation và replay/freshness |
| Thu hồi quyền dùng key | Không tự đảo ngược plaintext hoặc key đã bị lấy trước đó | Chặn thao tác mới, cache/consumer và phạm vi dữ liệu đã lộ |

Rewrap không sửa được việc DEK đã lộ, vì DEK và ciphertext có thể vẫn như cũ. Khi nghi lộ DEK, cần đánh giá dữ liệu bị ảnh hưởng và kế hoạch mã hóa lại/thu hồi capability phù hợp; khi KEK bị lộ, cần đánh giá khả năng đối phương đã unwrap những DEK nào.

Một yêu cầu thu hồi cần có mốc và điểm cưỡng chế. Ví dụ sản phẩm có thể đặt chặn thao tác giải mã mới trong 5 phút từ khi lệnh thu hồi có thẩm quyền được chấp nhận. Giá trị đó chỉ được dùng khi provider, cache, job và quyền hiện hành chứng minh đáp ứng; nó không có nghĩa đã thu hồi dữ liệu mà bên khác đọc trước đó.

### 6.3. Không hủy key trước khi dữ liệu hết phụ thuộc

Ciphertext và backup lịch sử có thể cần key version cũ. Quy trình phải xác định dữ liệu đã migration, thời hạn giữ, bản sao nào còn cần giải mã và bài restore nào xác nhận có thể phục hồi. Key đã hết dùng cho ghi mới vẫn có thể cần quyền đọc lịch sử được giới hạn.

Hủy key sớm có thể gây mất dữ liệu; giữ mọi key vô thời hạn với quyền rộng làm tăng rủi ro. Crypto-erasure cũng cần chứng minh phạm vi bản sao và khóa liên quan, không tự kết luận một lệnh delete key đã xóa mọi plaintext/dump từng tồn tại.

Trong runtime quản lý bộ nhớ, cần hạn chế thời gian giữ và bản sao của key/plaintext, dùng API phù hợp để giải phóng hoặc xóa khi khả thi. Không cam kết đã zeroize tuyệt đối mọi bản sao trong GC, swap hoặc crash dump nếu nền tảng không cung cấp bằng chứng đó.

## 7. Đặc tả theo từng mục đích mật mã

### 7.1. Password hashing khác mã hóa dữ liệu cần đọc lại

Với mật khẩu đăng nhập, mục tiêu thường là xác minh mà không phải giữ khả năng lấy lại mật khẩu gốc. Cần dùng password hashing có salt và cost phù hợp; hàm băm nhanh đơn thuần hoặc mã hóa có thể đảo ngược không phải lựa chọn mặc định cho mục đích này. [Nguồn: OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

Một hồ sơ password hashing cần chỉ rõ:

- Thuật toán và phiên bản được cho phép; ví dụ lựa chọn Argon2id phải kèm tham số memory, iteration và parallelism đã được phê duyệt.
- Cách tạo salt riêng cho mỗi bản ghi, lưu tham số cùng hash và quản lý pepper nếu thiết kế có dùng.
- Giới hạn input, concurrency, CPU/RAM và hành vi khi quá tải để endpoint xác thực không trở thành điểm gây cạn tài nguyên.
- Cách xác minh bản ghi cũ, nâng tham số sau lần xác thực hợp lệ và từ chối format không được phép.
- Quy trình reset khi không còn đủ điều kiện xác minh; không tìm cách “giải mã hash” để phục hồi mật khẩu.

Tham số phải được chọn từ hướng dẫn còn hiệu lực và benchmark trên hạ tầng mục tiêu. Bài không đặt một con số cost dùng chung cho mọi sản phẩm. Giảm cost khi tải cao hoặc fallback sang hash nhanh mà không có chính sách là thay đổi mức bảo vệ, cần bị ngăn theo hợp đồng.

Salt không cần bí mật và không thay thế pepper/khóa. Nếu dùng pepper, cần nguồn cấp, quyền đọc, rotation và xử lý mất/lộ riêng; thay pepper không nhất thiết thực hiện được cho mọi bản ghi mà không có mật khẩu hoặc kế hoạch chuyển đổi tương ứng.

### 7.2. Hash, MAC và chữ ký cần binding đúng dữ liệu

Digest lưu cạnh một tệp hữu ích để xác định nội dung, nhưng bên sửa được cả tệp lẫn digest có thể thay đồng thời hai giá trị. Nếu cần xác thực trước đối phương có quyền đó, phải dùng một cơ chế có trust/key binding phù hợp, không gọi checksum là bằng chứng nguồn đáng tin.

Với MAC/chữ ký, hồ sơ cần quy định bytes nào được xác thực, canonicalization, version, purpose, danh tính bên gửi/nhận và key selection. Chỉ `signature_valid=true` chưa chứng minh thông điệp dành cho dịch vụ này, còn hiệu lực hoặc được phép dùng cho thao tác hiện tại.

Ví dụ một thông điệp xác nhận xuất báo cáo có thể cần ràng buộc `issuer`, `audience`, `report_id`, `object_version`, `action`, thời hạn và message ID. Thuộc tính cần chống replay phải có cơ chế theo dõi/khước từ replay hoặc hợp đồng idempotency phù hợp; chữ ký hợp lệ không tự ngăn gửi lại.

`key_id` trong thông điệp là đầu vào chưa tin cậy. Bên xác minh chỉ tra trong tập key/issuer/purpose được cấu hình có thẩm quyền, không tải tùy ý một URL khóa do caller cung cấp. Thuật toán được phép cũng phải đến từ policy; không để thông điệp tự hạ xuống chế độ không có xác thực.

Khi so sánh MAC hoặc giá trị bí mật, dùng primitive xác minh/so sánh phù hợp của thư viện và đánh giá side channel trong ngữ cảnh thực thi. Một vòng test timing không thấy khác biệt không đủ chứng minh code luôn constant-time trên mọi runtime, compiler và phần cứng.

### 7.3. Mật mã khóa công khai và giao thức kênh

Phải xác định cần chữ ký, key agreement hay mã hóa hybrid; một primitive key agreement không tự cung cấp format ciphertext, xác thực peer hoặc chống replay. Ưu tiên giao thức và implementation đã được đánh giá thay vì tự ghép primitive thành một giao thức mới.

Với TLS, cần profile kênh riêng: version/suite được chấp nhận, trust store, kiểm tra danh tính peer, chứng chỉ, rotation và hành vi khi không xác minh được. Một profile lưu trữ AES-256-GCM đạt không chứng minh client HTTP đang xác minh hostname đúng.

Đổi sang một thuật toán có tên mới cũng không tự làm hệ thống sẵn sàng cho rủi ro tương lai. Khi dữ liệu cần bí mật lâu dài hoặc có phụ thuộc khóa công khai, kế hoạch chuyển đổi phải tính tới protocol, key wrapping, thư viện, kích thước thông điệp và khả năng tương tác. Lựa chọn cụ thể cần được cập nhật theo tiêu chuẩn và implementation đã được chấp nhận tại thời điểm áp dụng.

## 8. Xử lý lỗi, tài nguyên và dữ liệu đang được sử dụng

### 8.1. Fail securely tại mọi điểm phụ thuộc

Các lỗi như profile lạ, key version không được phép, unwrap bị từ chối, tag không hợp lệ, nonce sai độ dài hoặc nguồn sinh lỗi phải tạo kết quả không cung cấp plaintext và không công bố dữ liệu ghi dở. Không tự thử tất cả khóa, đổi thuật toán, tắt xác thực tag hoặc ghi plaintext để “giữ dịch vụ chạy”.

Một envelope có thể hỏng ở bước parse trước khi gọi crypto. Cần kiểm tra schema, field lặp, độ dài và kiểu trước cấp phát lớn hoặc gọi key service. Không tin một trường khai báo `length` để quyết định cấp RAM không giới hạn; phải đếm bytes thực theo ranh giới được đặc tả.

Hồ sơ ví dụ dùng plaintext tối đa 1 MiB, ciphertext GCM tương ứng tối đa 1 MiB và tag tách riêng 16 byte. Metadata tối đa 8 KiB tính theo biểu diễn canonical ở storage, gồm context, key reference, wrapped DEK, nonce và các field ngoài ciphertext/tag; transport encoding cần trần wire riêng vì Base64 có overhead. Profile phải tương thích kích thước wrap thực của provider, không mặc định mọi KMS trả blob cùng cỡ.

Giải mã lỗi không được đưa plaintext tạm vào response, log, event hoặc downstream parser. Phần giữ riêng cũng cần quyền, dung lượng và cleanup; cất plaintext vào một file tạm được mọi tiến trình đọc không đáp ứng yêu cầu chỉ vì chưa trả về HTTP.

### 8.2. Lỗi bên ngoài và bằng chứng bên trong

Response cho caller không được làm lộ key material, trạng thái nội bộ hoặc chi tiết cho phép biến endpoint thành công cụ dò. Hệ thống có thể giữ mã lỗi cấu trúc trong audit được phân quyền để vận hành phân biệt lỗi xác thực dữ liệu, thiếu quyền và outage của provider.

Che thông báo không đủ ngăn mọi oracle: thời gian phản hồi, kích thước và tác động phụ cũng cần được xem xét. Không cam kết “hết side channel” chỉ từ việc mọi lỗi đều trả cùng một chuỗi hoặc cùng status code.

Khả năng gọi key service phải có quota, deadline, giới hạn đồng thời và retry theo hợp đồng. Ví dụ triển khai có thể chọn tối đa 3 giây cho một lần unwrap và 5 giây cho toàn thao tác đọc liên quan, không retry tự động trong hồ sơ cơ sở. Đây là ngân sách minh họa cần đo ở từng thành phần; timeout ở API không tự chứng minh lời gọi nền hoặc bộ đệm đã được dừng/dọn.

### 8.3. Plaintext trong bộ nhớ và khả năng quan sát

Mã hóa khi lưu hoặc truyền không loại bỏ plaintext lúc xử lý. Cần xác định nơi plaintext xuất hiện: buffer, heap, temporary file, cache, swap, diagnostic và crash dump. Bảo vệ tiến trình, quyền đọc và giảm lưu trữ không cần thiết là phần của threat model.

Audit cần principal/workload, môi trường, purpose, resource/version ID, profile/key version, quyết định và mã liên kết phù hợp. Không ghi DEK/KEK, password, plaintext, raw token hoặc payload đầy đủ. Ngay cả AAD hoặc ID cũng cần chính sách riêng tư phù hợp; không mặc định mọi metadata đều có thể công khai.

## 9. Khung kiểm chứng và cách tham chiếu ASVS

### 9.1. Liên kết yêu cầu có phiên bản

Các mã trong bảng là tham chiếu **ASVS 5.0.0**; mô tả được tóm tắt để chỉ hướng đối chiếu, không thay văn bản chuẩn hoặc chứng minh đã đáp ứng toàn bộ mức. [Nguồn: ASVS 5.0.0 — V11 Cryptography](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x20-V11-Cryptography.md).

| Tham chiếu | Trọng tâm đối chiếu |
|---|---|
| `v5.0.0-11.1.1`, `v5.0.0-11.1.2` | Chính sách/vòng đời khóa và inventory có phạm vi sử dụng |
| `v5.0.0-11.2.1`, `v5.0.0-11.2.2` | Implementation được đánh giá và khả năng chuyển đổi |
| `v5.0.0-11.3.3`, `v5.0.0-11.3.4` | Bảo vệ sửa đổi và cách dùng nonce/IV |
| `v5.0.0-11.4.2`, `v5.0.0-11.5.1` | Password hashing và giá trị cần không đoán được |

Các mã `CR-*` và `AC-*` ở phần sau là yêu cầu/test của sản phẩm minh họa. Một CR có thể đóng góp cho nhiều mục chuẩn hoặc thuộc phạm vi phân quyền, dữ liệu, vận hành ngoài nhóm V11. Không gán mọi quyết định của hồ sơ ví dụ thành nghĩa vụ nguyên văn của ASVS.

### 9.2. Bốn lớp bằng chứng cần phối hợp

| Lớp | Điều cần xác minh | Giới hạn của bằng chứng |
|---|---|---|
| Quyết định/kiến trúc | Dữ liệu, threat model, profile, key binding và vòng đời đã được chốt | Tài liệu tồn tại chưa chứng minh code giữ đúng |
| Code/library/provider | Primitive được gọi đúng tham số, nguồn sinh, quyền và cấu hình | Tên thư viện không chứng minh mọi wrapper/đường gọi đúng |
| Chức năng và test âm | Sửa ciphertext, sai context, ngoài quyền, lỗi KMS/RNG và tài nguyên | Test hữu hạn không chứng minh độ mạnh toán học hoặc mọi side channel |
| Vận hành/khôi phục | Rotation, thu hồi, restore, migration và audit | Một lần đổi alias không chứng minh dữ liệu/backup đã chuyển khóa |

Test vector độc lập hoặc known-answer test có thể xác nhận primitive/wrapper xử lý đúng bytes và tham số trong phạm vi. Round-trip đơn thuần chỉ chứng minh hai chiều của cùng implementation tương thích; cùng một lỗi ở cả hai chiều vẫn có thể làm round-trip xanh.

Không đánh giá độ mạnh thuật toán bằng cách “thử brute force không thành công trong vài giờ”. Cơ sở chọn cơ chế phải đến từ tiêu chuẩn, phân tích và implementation được chấp nhận; test sản phẩm tập trung vào tích hợp, tham số, quyền, format và hành vi lỗi.

### 9.3. Kết quả phải gắn đúng đối tượng

Record cần có requirement/profile version, artifact/revision, library/provider/configuration, platform, key resource thử, phương pháp, expected/actual và người chịu trách nhiệm. Không ghi khóa production vào bằng chứng.

Một đường crypto chưa inventory hoặc một provider không truy cập được cần trạng thái chưa kiểm chứng/bị chặn. N/A phải có lý do điều kiện không tồn tại; thiếu test không phải N/A. Chấp nhận rủi ro là quyết định riêng, không tự biến một yêu cầu vi phạm thành PASS.

## 10. Ma trận rủi ro, yêu cầu và bằng chứng nghiệm thu

Các yêu cầu dưới đây đặc tả hồ sơ báo cáo và các mục đích crypto khác nếu chúng hiện diện trong ứng dụng. Owner dữ liệu chịu trách nhiệm phạm vi bảo vệ; nhóm ứng dụng chịu trách nhiệm quyền, format và tích hợp; nền tảng key service chịu trách nhiệm capability và vòng đời khóa; bên an toàn hỗ trợ profile và kiểm chứng. Từng trách nhiệm phải được giao cho chủ thể cụ thể khi áp dụng.

| ID / rủi ro | Yêu cầu kiểm chứng được | Điểm cưỡng chế | Bằng chứng chấp nhận |
|---|---|---|---|
| CR-01 / R1, R8 | Phải có inventory use case/key/profile/certificate trong phạm vi, mục tiêu bảo vệ, dữ liệu và owner; không lưu raw key trong inventory. | Quản lý thiết kế và inventory | AC-01: đối chiếu được đường crypto thực với record và phát hiện phần còn thiếu. |
| CR-02 / R6 | Phải dùng profile và implementation được phê duyệt; ghi mới chỉ dùng profile hiện hành, từ chối profile/tham số ngoài policy và không tự hạ bảo vệ. | Wrapper crypto và cấu hình provider | AC-02: profile lạ, tag rút ngắn hoặc mode cũ không được ghi mới hay fallback. |
| CR-03 / R3 | Key/token phải dùng nguồn sinh phù hợp; profile GCM phải giữ điều kiện nonce theo khóa qua retry/restart/restore; ticket ví dụ chỉ được mã hóa một lần. | Key generation, ticket store và wrapper AEAD | AC-03: lỗi nguồn sinh hoặc tiêu thụ lại ticket bị chặn; retry không mã hóa bằng cặp cũ. |
| CR-04 / R2 | Ciphertext và context phải được xác thực; expected AAD đến từ nguồn có thẩm quyền; không phát plaintext trước xác minh hoàn tất. | AEAD, envelope parser và downstream sink | AC-04: thay bytes/tag/nonce/AAD hoặc chuyển tenant/report làm thao tác thất bại, không lộ plaintext. |
| CR-05 / R4 | Trước khi giải mã phải xác minh quyền report và binding key/purpose/môi trường; key service cưỡng chế quyền workload, không chấp nhận key reference tùy ý. | API/service và key service | AC-05: ngoài quyền không gọi unwrap; principal sai môi trường bị key service từ chối độc lập. |
| CR-06 / R5 | Rotation/thu hồi phải có mốc và phạm vi; hồ sơ minh họa chặn thao tác giải mã mới bằng quyền bị thu hồi trong tối đa 5 phút, không cache DEK qua request. | Key policy, consumer và vận hành | AC-06: đo quyền thực tại consumer/provider, kiểm tra rewrap khác với thay DEK và không hồi sinh quyền cũ. |
| CR-07 / R1, R5 | Không hủy key lịch sử khi dữ liệu/backup còn cần; phải thử restore và xác minh điều kiện migration/retention trước hủy. | Key lifecycle và phục hồi dữ liệu | AC-07: dữ liệu mẫu còn hạn đọc được đúng quyền; hủy sớm bị ngăn theo quy trình. |
| CR-08 / R6 | Nếu lưu mật khẩu đăng nhập, phải dùng profile password hashing được duyệt với salt/cost/version và kế hoạch nâng; không dùng hash nhanh hoặc mã hóa đảo ngược làm mặc định. | Thành phần xác thực và policy tham số | AC-08: tham số/salt/migration đúng, không fallback giảm cost; đường tải nằm trong ngân sách. |
| CR-09 / R2, R6 | MAC/chữ ký phải xác minh đúng bytes, trust/key/purpose; freshness/replay thực thi theo hợp đồng riêng; thông điệp không tự chọn khóa/thuật toán ngoài policy. | Verifier và state nghiệp vụ | AC-09: sai key/issuer/audience/purpose và replay ngoài hợp đồng bị từ chối. |
| CR-10 / R7 | Lỗi parse/authentication/KMS/RNG không được công bố plaintext hoặc dữ liệu dở; hồ sơ giới hạn 1 MiB plaintext, 8 KiB metadata và ngân sách unwrap/đọc 3/5 giây đã đặc tả. | Parser, supervisor, storage và error handler | AC-10: biên byte, timeout và lỗi từng bước được xử lý có giới hạn, không rò dữ liệu hoặc fallback. |
| CR-11 / R1, R7 | Key/plaintext/secret không được ghi vào log, trace, dump hay tệp tạm ngoài quyền; audit giữ đủ ID/quyết định để điều tra. | Runtime, diagnostic, audit và quyền storage | AC-11: marker fixture được bảo vệ trên mọi đầu ra thuộc phạm vi, audit vẫn truy vết được. |
| CR-12 / R5, R8 | Phải có kế hoạch chuyển profile/key và bằng chứng đúng artifact/configuration; migration/rollback không tự mở lại profile ghi đã cấm hoặc bỏ kiểm tra quyền. | Migration, gate và release/restore | AC-12: đọc dữ liệu lịch sử đúng policy, ghi mới đúng profile và từ chối kết luận từ evidence không khớp. |

Không coi bảng này là bộ kiểm tra đầy đủ của ASVS V11 hay toàn ứng dụng. Ví dụ một hệ thống dùng TLS hoặc crypto trong môi trường xử lý đặc thù còn cần các yêu cầu và bằng chứng đúng phạm vi đó. Một test PASS cho CR-04 không tự chứng minh CR-05 về quyền hoặc CR-07 về phục hồi.

## 11. Test và acceptance criteria

### 11.1. Môi trường và oracle

Dùng key resource thử, fixture tenant A/B, object version bất biến, thư viện/provider đúng version mục tiêu và một key service thử có thể quan sát quyết định. Không dùng key, password hay dữ liệu production để chứng minh lỗi.

Quan sát ít nhất các điểm phù hợp: lời gọi cấp/unwrap key, wrapper AEAD, sink plaintext, trạng thái object, audit và tác vụ nền. Sink nhận dữ liệu thử phải ghi được có bytes nào được công bố trước khi kết thúc xác minh; chỉ mã HTTP không đủ làm oracle.

Key fixture trong known-answer test có thể cố định để so bytes kỳ vọng, nhưng không được dùng trong đường sinh khóa production hoặc đưa cơ chế nonce cố định của test vào cấu hình chạy thật. Tách fault injection của test khỏi khả năng caller có thể bật ở môi trường sản xuất.

### 11.2. Các ca nghiệm thu chi tiết

**AC-01 — Inventory và phạm vi bảo vệ, truy vết CR-01.**

Đối chiếu inventory với code/configuration và các đường API, worker, backup/restore trong phạm vi. Thêm một fixture ký/MAC hoặc một helper crypto không có record; hồ sơ phải ghi khoảng trống và owner xử lý, không tự kết luận chỉ có đúng một đường mã hóa. Mỗi key/profile cần chỉ được dữ liệu và môi trường được phép dùng, cùng nơi không được dùng. Inventory/report không chứa raw key.

**AC-02 — Profile và implementation, truy vết CR-02.**

Với profile hợp lệ, chạy known-answer test có nguồn kỳ vọng độc lập cho primitive/wrapper và test tích hợp của envelope. Thử profile lạ, key length sai, nonce không đủ 12 byte hoặc tag không đủ 16 byte trong profile báo cáo; thao tác phải từ chối theo hợp đồng. Tắt khả năng profile ở provider: hệ thống không đổi sang mode không xác thực hoặc ghi plaintext. Nếu có profile legacy read-only phục vụ migration, thử dùng nó để ghi mới phải bị từ chối.

Round-trip xanh là đối chứng hữu ích nhưng không thay known-answer test hoặc kiểm tra nguồn implementation. Nếu có yêu cầu về module được kiểm định, bằng chứng phải chỉ đúng module/version/chế độ đang dùng, không chỉ tên thuật toán trong cấu hình.

**AC-03 — Nguồn sinh và tính dùng một lần, truy vết CR-03.**

Gây lỗi nguồn sinh/cấp DEK, rồi xác minh không dùng hằng số, timestamp hoặc khóa mặc định. Hai worker cùng tiêu thụ một ticket: nhiều nhất một worker được phép gọi primitive mã hóa với vật liệu của ticket đó. Thử tiêu thụ lại sau restart, restore và khi kết quả lần trước không xác định; ticket cũ phải bị từ chối, retry lấy vật liệu mới.

Thử retry bước upload của envelope đã hoàn tất: hệ thống chỉ gửi lại đúng bytes đã giữ, không mã hóa lại plaintext dưới cùng cặp key/nonce. Kiểm tra nguồn cấp ticket thực sinh DEK theo thiết kế; token ticket mới mà bên trong trả lại cùng key bị cache không đáp ứng yêu cầu. Các quan sát dùng ticket/key-version fixture ID hoặc instrumentation được kiểm soát, không log DEK thật.

**AC-04 — Chống sửa đổi và sai context, truy vết CR-04.**

Tạo envelope hợp lệ cho report A/version V1 rồi lần lượt thay một bit ciphertext, tag, nonce, cắt ngắn nội dung và thay AAD. Mọi biến thể không hợp lệ phải thất bại xác thực hoặc bị từ chối trước đó, không phát plaintext tới response/parser/event/log. Đối chứng là envelope nguyên vẹn được giải mã đúng bởi caller đủ quyền.

Copy toàn envelope sang report khác hoặc tenant B, rồi đổi metadata tự khai cho giống context mới: expected context từ record có thẩm quyền vẫn phải ngăn giải mã sai binding. Khôi phục envelope V1 vào vị trí được yêu cầu là V2 phải bị chặn bởi kiểm tra version/freshness; tag đúng trong context V1 không được dùng làm bằng chứng V1 là version hiện hành.

Với adapter streaming, cố ý làm sai tag cuối sau khi đã sinh một phần plaintext nội bộ; sink bên ngoài không được nhận phần plaintext chưa xác thực. Đây là kiểm tra tích hợp API, không chỉ kiểm tra primitive trả lỗi ở cuối.

**AC-05 — Quyền ở hai điểm cưỡng chế, truy vết CR-05.**

Caller A thử report của B, một report cùng tenant nhưng thiếu quyền và key reference ngoài tập được phép. Nhánh ngoài quyền report phải bị từ chối trước unwrap; dữ liệu trong envelope không được tự chọn KMS key có quyền rộng hơn. Tiếp theo dùng principal fixture staging gọi trực tiếp key service production fixture: provider phải từ chối dù bỏ qua lớp kiểm tra ứng dụng.

Kiểm tra caller đủ quyền với binding đúng vẫn đọc được. Một key service cấp quyền workload không hiểu toàn bộ quyền report không được dùng thay lớp phân quyền nghiệp vụ; cả hai điều kiện phải có bằng chứng phù hợp.

**AC-06 — Rotation, rewrap và thu hồi, truy vết CR-06.**

Rewrap một wrapped DEK từ KEK version cũ sang mới theo profile: ciphertext/AAD bất biến có thể giữ nguyên và dữ liệu vẫn đọc được đúng quyền. Sau đó thay DEK: phải tạo ciphertext/tag với cặp key/nonce mới, không chỉ sửa trường `key_version` trong envelope. Ca thử phải phân biệt hai thao tác này bằng bằng chứng thực tế.

Chấp nhận lệnh thu hồi có thẩm quyền tại `t0`, giữ một số request đang chạy và tạo request mới qua nhiều instance. Trong tối đa 5 phút từ `t0`, không thao tác giải mã mới nào bằng quyền bị thu hồi được phép thành công trong phạm vi đã đặc tả; key service và consumer phải không tái dùng cache DEK qua request. Xác định riêng cách xử lý request đã được chấp nhận trước `t0` và plaintext đã giao, không báo rằng đã thu hồi các bản sao ấy.

Một job cũ hoặc restore cấu hình cũ không được làm quyền tự hoạt động lại. Nếu provider không thể đáp ứng mốc này, ghi yêu cầu chưa đạt hoặc thay thiết kế theo quy trình, không chỉ đo thời gian gửi lệnh.

**AC-07 — Key lịch sử và restore, truy vết CR-07.**

Tạo dữ liệu/backup fixture ở hai key version, chuyển ghi mới sang version mới và giới hạn key cũ theo chính sách đọc lịch sử. Restore trong môi trường được cấp phải đọc đúng dữ liệu còn hạn; principal không được cấp vẫn bị từ chối. Trước khi hủy key cũ, quy trình phải kiểm tra còn bản dữ liệu/backup phụ thuộc hay không.

Một yêu cầu hủy khi còn phụ thuộc phải không được thực hiện như thao tác bảo trì thường lệ. Sau khi đáp ứng đầy đủ điều kiện retention/migration, thử hủy trên fixture và xác minh hậu quả được dự kiến. Không dùng fixture đã mất khả năng giải mã làm bằng chứng rằng production sẽ luôn phục hồi được.

**AC-08 — Password hashing, truy vết CR-08.**

Nếu ứng dụng lưu mật khẩu, tạo hai bản ghi cùng password fixture: salt riêng và record phải chứa thuật toán/param/version cần để xác minh. Kiểm tra cấu hình cost đúng profile, ca password sai, input quá cỡ và tải đồng thời theo ngân sách xác thực. Không thử chứng minh độ an toàn bằng việc brute force thất bại trong thời gian ngắn.

Xác thực một record cũ được phép rồi nâng theo kế hoạch; record mới dùng profile hiện hành và vẫn xác minh đúng. Provider thiếu thuật toán hoặc tải cao không được làm hệ thống fallback sang hash nhanh/giảm cost trái policy. Nếu sản phẩm thật không lưu mật khẩu, ghi N/A có phạm vi và bằng chứng, không dựng một PASS giả cho chức năng không tồn tại.

**AC-09 — MAC/chữ ký và replay, truy vết CR-09.**

Với use case hiện diện, xác minh thông điệp hợp lệ rồi thử sửa bytes, sai khóa, sai purpose/issuer/audience, thuật toán ngoài policy hoặc `key_id` dẫn tới nguồn không được cấp. Hệ thống phải từ chối theo hợp đồng mà không gọi endpoint khóa tùy ý do thông điệp cung cấp.

Gửi lại một thông điệp có chữ ký còn hợp lệ trong ngữ cảnh không cho phép replay: state/message-ID policy phải ngăn tác động lặp. Nếu thao tác được thiết kế idempotent thì kết quả phải đúng hợp đồng, không thực hiện lặp side effect ngoài quyền. Kiểm tra lựa chọn primitive xác minh phù hợp; một test timing ổn định không được báo như bằng chứng toán học của constant-time.

**AC-10 — Biên tài nguyên và lỗi, truy vết CR-10.**

| Ca fixture | Kết quả cần quan sát |
|---|---|
| Plaintext hợp lệ dài `1 MiB - 1` và đúng `1 MiB` | Không bị từ chối chỉ vì chạm giới hạn, nếu điều kiện khác đạt |
| Plaintext/ciphertext hoặc metadata vượt trần của profile | Bị chặn có giới hạn, không cấp phát/đọc toàn bộ rồi mới kiểm tra |
| Trường độ dài khai báo nhỏ nhưng bytes thực lớn | Bộ đếm thực và giới hạn wire/decode vẫn có hiệu lực |
| Envelope field lặp, kiểu sai, tag thiếu hoặc key version bị cấm | Từ chối theo schema/policy, không thử dò mọi key hoặc profile |
| Unwrap quá 3 giây hoặc toàn thao tác đọc quá 5 giây | Dừng/thu hồi công việc theo hợp đồng đã đo, không giữ tác vụ nền vô hạn |
| KMS/RNG lỗi, lỗi ghi storage hoặc tag không hợp lệ | Không fallback mất bảo vệ, không công bố plaintext/tệp dở |

Ranh giới metadata 8 KiB dùng cách đo canonical đã đặc tả, không đo tùy ý theo chuỗi debug. Chốt sai số đồng hồ, kích thước buffer và cơ chế dừng nền trước khi chạy. Ngân sách 3/5 giây là giá trị minh họa của phần đọc; quy trình migration dài hơn cần ngân sách riêng, không âm thầm bỏ giới hạn ở request người dùng.

**AC-11 — Audit, bộ nhớ và dữ liệu nhạy cảm, truy vết CR-11.**

Dùng marker plaintext/key fixture để kiểm tra log, trace, exception, diagnostic, cache và file tạm trong phạm vi. Marker không được xuất hiện ở kênh ngoài quyền; dump nếu được phép phải có policy quyền/lưu rõ, không công khai trong artifact CI. Audit vẫn liên kết được principal, report/version, profile/key-version và kết quả mà không cần raw material.

Review cách giữ/giải phóng vật liệu và đặc tính nền tảng; test bộ nhớ hữu hạn không được dùng để cam kết mọi bản sao đã zeroize. Kết nối tới key service/storage cần giữ kiểm tra danh tính và profile kênh hiện hành, không tắt xác minh TLS để vượt một lỗi trust trong ca thử.

**AC-12 — Migration, rollback và bằng chứng, truy vết CR-12.**

Chuyển từ profile fixture cũ sang mới: ghi mới chỉ dùng profile mới, đọc cũ chỉ trong phạm vi được phép và migration không công bố dữ liệu chưa được xác thực. Ngắt migration giữa chừng rồi resume; trạng thái từng object/version, quyền và ticket phải tránh mã hóa lặp bằng vật liệu cũ hoặc làm mất dữ liệu.

Thử rollback ứng dụng không hiểu profile mới: kế hoạch phải có consumer tương thích hoặc phương án phục hồi được cấp quyền, không tự mở profile ghi đã cấm. Báo cáo của artifact/provider/configuration khác không tự được tính cho candidate hiện tại. Chỉ kết luận hoàn tất migration khi bằng chứng dữ liệu, backup và quyền đáp ứng điều kiện đã chốt.

### 11.3. Điều kiện chấp nhận và giới hạn kết luận

CR-01–CR-12 cần owner, cấu hình/thiết kế cưỡng chế và bằng chứng tương ứng trong phạm vi. Phần không áp dụng, chưa kiểm chứng và rủi ro chấp nhận phải được ghi riêng; một mục FAIL bắt buộc không được bù bằng số PASS của mục khác.

Các ca AC-01–AC-12 là đặc tả nghiệm thu để triển khai thực hiện. Bài không tuyên bố chúng đã được chạy, đã kiểm định module mật mã hoặc đã chứng minh toàn ứng dụng đáp ứng ASVS. Đặc biệt, test round-trip, sửa bit và lỗi provider không tự chứng minh primitive không có điểm yếu toán học hoặc mọi side channel đã được loại bỏ.

## 12. Crypto agility và duy trì yêu cầu theo thời gian

### 12.1. Thay cơ chế có kiểm soát

Crypto agility là khả năng thay key/profile/implementation theo kế hoạch mà vẫn giữ quyền, dữ liệu và khả năng kiểm chứng. Nó không có nghĩa cho caller chọn mọi thuật toán hoặc để cấu hình tùy ý hạ mức bảo vệ.

Kế hoạch chuyển đổi cần chỉ rõ format/version, cách nhận diện dữ liệu cũ, write profile, read allowlist, migration, khả năng khôi phục và thời điểm loại bỏ đường legacy. Với dữ liệu cần bí mật dài hạn, phải xem cả cơ chế bảo vệ DEK, key establishment và các bên nhận, không chỉ thuật toán mã hóa body.

Một format tự mô tả giúp vận hành khi được parser và policy kiểm soát. Ngược lại, một trường `algorithm` không được xác thực hoặc không bị giới hạn có thể tạo downgrade/confusion. Thay đổi tham số, thư viện/provider hoặc platform cần đánh giá lại bằng chứng bị ảnh hưởng, ngay cả khi tên profile giữ nguyên.

### 12.2. Nối yêu cầu với kiến trúc và vận hành

Với ví dụ báo cáo, chuỗi bằng chứng cần nối được: phân loại dữ liệu → threat model → profile `report-aead-v1` → quyền report/key service → envelope/ticket → test âm → rotation/restore → artifact/configuration được triển khai. Mỗi lần thay key policy hoặc bổ sung worker cần xác định lại đường nào được sử dụng và ai có khả năng nhận plaintext.

Khi phát hiện compromise, không chỉ rotate rồi đóng việc. Cần điều tra quyền/khóa đã bị dùng, bản sao dữ liệu có thể đã đọc, audit và khả năng phục hồi; các thông tin đó quyết định cần rewrap, re-encrypt hay thay cơ chế/phạm vi quyền. Bí mật của dữ liệu đã bị lấy trước đó không thể được phục hồi chỉ bằng thay key hiện tại.

Yêu cầu mật mã có thể kiểm chứng khi nó mô tả được thuộc tính cần giữ, vật liệu và quyền liên quan, hành vi bình thường/lỗi, vòng đời dữ liệu cùng bằng chứng đúng phạm vi. Tên thuật toán là một phần của hồ sơ đó; chất lượng tích hợp và quản lý khóa quyết định cơ chế có giữ được mục tiêu trong sản phẩm hay không.

### 12.3. Nguồn chính thức

- [ASVS 5.0.0 — V11 Cryptography](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x20-V11-Cryptography.md): nhóm yêu cầu tham chiếu theo phiên bản.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): hướng dẫn chọn lớp bảo vệ, cơ chế và nguồn sinh.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): quản lý vật liệu khóa và vòng đời.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): profile và triển khai bảo vệ mật khẩu.
- [NIST SP 800-38D](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf): đặc tả GCM/GMAC, IV, dữ liệu liên kết và xác thực.

Các yêu cầu CR, ca AC, ticket một lần, giới hạn byte và thời hạn của hồ sơ là thiết kế minh họa của bài. Khi áp dụng phải xác nhận tính phù hợp với dữ liệu, provider và môi trường, đồng thời giữ nguyên ngữ nghĩa của yêu cầu chuẩn được dùng làm tham chiếu.

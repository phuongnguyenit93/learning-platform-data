# Rotation policy — Chính sách xoay vòng khóa mật mã

## 1. Rotation policy là gì?

**Rotation policy** (*chính sách xoay vòng khóa*) quy định **khi nào, vì lý do gì, bằng cách nào và ai được phép thay vật liệu khóa mật mã đang được sử dụng bằng vật liệu khóa mới**. Chính sách phải bao trùm cả giai đoạn chuẩn bị, chuyển đổi sang khóa mới (*cutover*), xử lý dữ liệu và chữ ký cũ, kiểm tra sau chuyển đổi, thu hồi quyền và hủy khóa khi không còn phụ thuộc.

Ví dụ, hệ thống Billing dùng một **KEK (Key Encryption Key)** trong KMS để bọc các **DEK (Data Encryption Key)** mã hóa hóa đơn. Chính sách đặt ra một kỳ đánh giá định kỳ, nhưng thay KEK không có nghĩa đơn giản tạo `kek-v2`, đổi alias rồi xóa `kek-v1`: những bản DEK được bọc bằng `kek-v1` vẫn phải được giải bọc hoặc chuyển đổi theo một cách an toàn. Nếu xóa bản khóa cũ khi chưa giải quyết phụ thuộc, ứng dụng có thể mất dữ liệu dù ciphertext còn nguyên.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, rotation policy là thành phần của **key policy** và gắn với toàn bộ vòng đời: **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**. Chính sách còn cần liên kết với mật mã đối xứng và bất đối xứng, chữ ký số, KMS/HSM, **envelope encryption**, quản trị quyền sử dụng và kiểm toán.

> **Nguyên tắc:** Xoay vòng khóa không chỉ là **thay một tên key hoặc lịch chạy định kỳ**. Muốn rotation thành công, phải tạo **vật liệu khóa mới an toàn**, chuyển hoạt động mới sang đúng phiên bản, giữ khả năng xử lý dữ liệu cũ theo chính sách và chứng minh những quyền/đường sử dụng cũ đã được kiểm soát.

### Các câu hỏi chính sách phải trả lời

1. **What:** Những loại khóa và phạm vi dữ liệu nào thuộc chính sách?
2. **When:** Khi nào phải đánh giá hoặc thực hiện rotation — theo thời gian, số lần sử dụng, sự cố hay thay đổi rủi ro?
3. **Who:** Ai đề xuất, phê duyệt, thực hiện, xác minh và kiểm toán?
4. **How:** Sinh khóa mới ở đâu; phân phối, cutover, rewrap, re-encrypt và rollback thế nào?
5. **After:** Khóa cũ được phép `Decrypt`, `Verify` hoặc `Unwrap` đến bao giờ; khi nào thu hồi/hủy?
6. **Evidence:** Dựa vào bằng chứng nào để kết luận đã chuyển đổi đúng và không mất khả năng khôi phục dữ liệu?

## 2. Phân biệt rotation với các khái niệm liên quan

| Khái niệm | Điều thực sự thay đổi | Ví dụ | Điểm cần tránh nhầm |
| --- | --- | --- | --- |
| **Rotation / rekey** | Thay **vật liệu khóa** dùng trong phạm vi đã định | Sinh AES key v2 thay v1 | Đổi alias đơn thuần chưa chắc đã đổi vật liệu |
| **Key version change** | Chuyển sang phiên bản vật liệu hoặc phiên bản logical key | `kek-v1` → `kek-v2` | Version/alias của provider có thể có semantics riêng |
| **Rewrap** | Bọc lại DEK bằng KEK khác hoặc phiên bản mới | DEK không đổi, wrapped DEK thay đổi | Không phục hồi bí mật nếu chính DEK đã lộ |
| **Re-encrypt** | Mã hóa lại dữ liệu bằng DEK khác | AES-GCM DEK v1 → DEK v2 | Cần nonce/AAD/tag mới và migration có kiểm soát |
| **Cryptoperiod** | Khoảng thời gian khóa được phép dùng cho mục đích cụ thể | Giới hạn thời gian ký/mã hóa mới | Không nhất thiết đồng nghĩa thời hạn lưu chứng cứ |
| **Deactivate** | Ngừng sử dụng khóa để bảo vệ/tạo dữ liệu mới | Dừng `Sign` bằng signing-v1 | Có thể vẫn cần `Decrypt` hoặc verify lịch sử |
| **Suspend / disable** | Tạm chặn thao tác theo rủi ro/chính sách | Chặn KEK khi nghi lạm dụng | Không mặc nhiên đổi key material |
| **Revoke certificate** | Thay đổi trạng thái tin cậy của chứng thư PKI | Thu hồi chứng thư khóa ký bị lộ | Không tự xóa các bản sao private key |
| **Destroy** | Tiêu hủy vật liệu khóa theo cơ chế được chấp nhận | Hủy KEK sau hết phụ thuộc | Có thể không thể đảo ngược, cần kiểm tra backup |
| **Renew certificate** | Phát hành chứng thư mới, có thể với cùng hoặc khóa khác | TLS certificate renewal | **Không bảo đảm key rotation** nếu vẫn dùng private key cũ |

### Rotation khác activation

Một khóa mới thường trải qua giai đoạn **pre-activation**: đã sinh và cấu hình nhưng chưa dùng cho dữ liệu sản xuất. Khi mọi điều kiện đã đạt và có phê duyệt, hệ thống kích hoạt quyền/đường sử dụng khóa mới. **Rotation** là quy trình lớn hơn, bao gồm cả việc giảm phụ thuộc và nghỉ dùng khóa cũ.

### Không phải phép toán nào cũng có cùng vòng đời

Một private key **ký số** thường cần ngừng tạo chữ ký mới nhưng public key tương ứng vẫn được dùng xác minh chữ ký lịch sử. Một **KEK** có thể không còn dùng để bọc DEK mới nhưng vẫn cần để giải bọc DEK cũ. Ngược lại, một **DEK bị lộ** có thể đòi hỏi mã hóa lại dữ liệu, không chỉ chuyển luồng ghi mới.

## 3. Mục tiêu bảo mật của rotation policy

Chính sách xoay vòng phục vụ nhiều mục tiêu nhưng không nên được mô tả là cơ chế tự chữa mọi vấn đề mật mã.

### 3.1. Giới hạn phạm vi ảnh hưởng

Nếu một khóa được dùng mãi mãi cho rất nhiều dữ liệu, khi khóa lộ, **phạm vi dữ liệu phụ thuộc khóa** có thể rất rộng. Phân đoạn theo phiên bản, tenant, service và cryptoperiod giúp quản lý ảnh hưởng, thu hẹp tập bản mã/chữ ký cần điều tra.

### 3.2. Giảm thời gian sử dụng khóa có rủi ro

Khóa có thể bị sử dụng bởi quá nhiều dịch vụ, truy cập từ môi trường không mong muốn, hoặc phụ thuộc một thuật toán/sản phẩm dần không còn phù hợp. Chính sách đánh giá và thay khóa định kỳ giúp thúc đẩy rà soát IAM, thuật toán, nguồn entropy và hệ phụ thuộc.

### 3.3. Đáp ứng nghĩa vụ nghiệp vụ và tuân thủ

Các tiêu chuẩn, ngành và tổ chức có thể yêu cầu **cryptoperiod**, phê duyệt, quy trình đổi khóa, lưu giữ bằng chứng hoặc biện pháp khẩn cấp. **Không tồn tại một chu kỳ cố định áp dụng an toàn cho mọi loại khóa.** Phải tham chiếu chính sách thực tế, loại dữ liệu, thuật toán, mức bảo đảm, lưu lượng sử dụng và yêu cầu pháp lý hiện hành.

### 3.4. Chuẩn bị đổi thuật toán và nhà cung cấp

Rotation cũng là cơ hội thay thuật toán, curve, kích thước khóa, provider KMS/HSM hoặc triển khai mô hình mới (ví dụ thay khóa ký cũ bằng khóa ký ở HSM). Thay **thuật toán** thường khó hơn thay vật liệu cùng thuật toán vì cần di chuyển định dạng, thư viện và bên xác minh.

### Giới hạn quan trọng

Nếu đối thủ đã **sao chép plaintext DEK** hoặc **private signing key**, xoay khóa vào ngày hôm nay **không thu hồi được bản sao đã bị lấy** và không xóa dữ liệu/chữ ký đã được tạo trước đó. Cần kết hợp incident response, đánh giá lịch sử, thay trust và đôi khi **re-encrypt**.

## 4. Xây dựng chính sách theo rủi ro, không chỉ theo lịch

Một rotation policy tốt dùng **nhiều loại trigger** và xác định **mức ưu tiên**, thay vì đặt một cron job cố định cho mọi key.

### 4.1. Scheduled rotation

Đặt mốc đánh giá hoặc thời hạn sử dụng mới dựa trên mục đích, độ nhạy, mức độ sử dụng, nguồn tạo và cryptoperiod. Ví dụ **minh họa, không phải yêu cầu tiêu chuẩn chung**:

~~~text
Key nhóm A: đánh giá định kỳ mỗi quý
Key nhóm B: xét điều kiện thay sau một thời gian sử dụng được phê duyệt
Private signing key: kế hoạch thay gắn với chứng thư và lịch phân phối verifier
Ephemeral agreement key: tạo mới theo phiên/handshake thay vì cron hàng quý
~~~

Một khóa có thể cần **rà soát hàng quý** nhưng **chỉ rotation khi đến cryptoperiod hoặc xuất hiện trigger rủi ro**. Không đồng nhất tần suất review với tần suất đổi vật liệu khóa.

### 4.2. Event-driven rotation

Các sự kiện có thể bắt buộc đánh giá/thay khóa sớm:

- Nghi ngờ hoặc xác nhận **key material bị lộ**.
- Credential dùng KMS/HSM bị chiếm, grant/IAM bị lạm dụng hoặc phát hiện sử dụng khóa ngoài mục đích.
- Thay đổi owner/custodian, tổ chức, đối tác nhận HMAC hoặc tenant boundary khi mô hình rủi ro yêu cầu.
- Phát hiện lỗi RNG, KDF, nonce, thư viện mật mã, thiết bị hoặc quy trình nhập key.
- Thuật toán, độ dài khóa, chứng thư hoặc cấu hình không còn được chấp nhận.
- Đạt hạn mức sử dụng, số thông điệp hoặc nonce do giao thức/thuật toán quy định.
- Mất/đổi thiết bị chứa private key, thu hồi quyền truy cập hoặc nghi bị sao chép backup.

**Sự kiện nghi compromise** thường phải kích hoạt **cô lập trước**, rồi xác định phạm vi thay khóa và dữ liệu liên quan. Không chờ hết lịch định kỳ mới phản ứng.

### 4.3. Usage-driven rotation

Một số thuật toán/mode có **giới hạn về số lần sử dụng, kích thước dữ liệu hoặc nonce**. Ví dụ AES-GCM không cho lặp nonce dưới cùng khóa; chiến lược cấp nonce và hạn mức số bản mã trên mỗi khóa phải được quy định theo đặc tả và mô hình hệ thống.

**Không suy luận** rằng thay khóa hàng năm tự bảo đảm an toàn nonce nếu một instance có thể tái sử dụng nonce chỉ sau vài phút. Rotation policy phải kết hợp **số lượt dùng**, **cách cấp phát nonce** và **cách nhận biết giới hạn**.

### 4.4. Bảng quyết định rủi ro

| Tín hiệu | Độ ưu tiên thường gặp | Hành động ban đầu | Quyết định tiếp theo |
| --- | --- | --- | --- |
| Đến kỳ review nhưng key còn trong cryptoperiod | Theo lịch | Rà soát purpose/IAM/thuật toán | Giữ, lên lịch thay hoặc điều chỉnh policy |
| Gần hết hạn ký mới/cryptoperiod | Cao theo lead time | Chuẩn bị key mới và client readiness | Cutover trước deadline |
| Đạt hạn mức nonce/message của giao thức | Cao/khẩn tùy giới hạn | Ngừng thao tác mới khi cần | Thay key, sửa nonce allocation |
| Nghi lộ private signing key | Khẩn | Suspend `Sign`, cô lập principal | Điều tra, thay key/trust, xử lý chữ ký |
| Xác nhận DEK lộ | Khẩn | Chặn dùng mới, kiểm kê bản mã | Thay DEK, cân nhắc re-encrypt và ứng cứu |
| Nghi lộ KEK hoặc grant | Khẩn | Cô lập quyền, đánh giá availability | Rotate KEK/rewrap, đánh giá DEK |
| Thuật toán không còn đạt chính sách | Theo thời hạn rủi ro | Ngừng cấp dùng mới khi phù hợp | Chuyển thuật toán, định dạng, chứng thư |

**Policy cần chỉ rõ ai được quyết định khẩn cấp và deadline xử lý.** Bảng trên chỉ đưa ra cấu trúc tư duy, không tạo SLA tự động cho mọi tổ chức.

## 5. Phân loại theo purpose, key type và phạm vi

**Purpose** từ key inventory là đầu vào quan trọng của rotation policy. Không nên quản lý mọi tài nguyên dưới nhãn chung `MASTER_KEY`.

| Loại khóa | Mục đích | Chiến lược thay khóa | Khả năng cần giữ |
| --- | --- | --- | --- |
| **DEK** | Mã hóa dữ liệu AES-GCM | Tạo DEK mới cho dữ liệu mới; di chuyển/re-encrypt dữ liệu cũ theo yêu cầu | Decrypt bản mã gắn với phiên bản cũ |
| **KEK** | Bọc/giải bọc DEK | Thay KEK, chuyển bọc DEK qua rewrap hoặc theo semantics của KMS | Unwrap những DEK chưa di chuyển |
| **Private signing key** | Ký hóa đơn, manifest, chứng thư | Tạo cặp mới, cập nhật public key/chứng thư và verifier, dừng ký mới bằng key cũ | Verify chữ ký lịch sử |
| **HMAC key** | Xác thực webhook, thông điệp hoặc token | Phát hành secret mới cho các bên, gắn key version, chuyển tạo/verify MAC | Verify tag cũ trong cửa sổ được duyệt |
| **Static ECDH key** | Thiết lập secret với peer | Thay cặp EC/X25519, phân phối public key và xác thực peer | Ảnh hưởng phiên cũ tùy giao thức |
| **Ephemeral ECDHE key** | Key agreement trong một handshake | Sinh theo phiên/handshake và hủy khi hết cần | Không giữ private key lâu dài chỉ để phục vụ rotation |
| **TLS authentication key** | Xác thực endpoint/peer | Thay private key/chứng thư và triển khai tới endpoint | Tin cậy đường TLS mới; phiên cũ theo giao thức |
| **JWT signing key** | Ký access token | Phát key mới trong JWKS/registry trước cutover, thay `kid` | Xác minh token cũ đến khi hết hạn/revoked |
| **Recovery KEK** | Phục hồi DEK theo chính sách | Xoay riêng, cập nhật các recovery wraps và quyền | Khôi phục dữ liệu cũ đúng phạm vi |
| **CA/TSA private key** | Ký chứng thư hoặc dấu thời gian | Theo chính sách PKI/TSA chuyên biệt, kế hoạch dài hạn | Xác minh chứng thư và bằng chứng lịch sử |

### Hai nguyên tắc xuyên suốt

1. **Key material và operation phải phù hợp Purpose.** Không xoay private signing key bằng cách lấy một AES key, và không coi chuyển certificate là thay private key nếu không sinh cặp mới.
2. **Chọn phạm vi rotation phù hợp.** Nếu một HMAC key được dùng chung cho nhiều đối tác, sự cố một đối tác có thể buộc thay secret ở tất cả; tách key theo tenant/partner khi phù hợp để giới hạn ảnh hưởng.

## 6. Rotation policy và cryptoperiod

**Cryptoperiod** là thời gian khóa được cho phép dùng cho một mục đích nhất định. Với nhiều hệ thống, phải phân biệt:

- **New-use period:** cho phép tạo ciphertext, chữ ký hoặc MAC mới.
- **Legacy-processing period:** còn phải giải mã, giải bọc hoặc kiểm tra dữ liệu/chữ ký có từ trước.
- **Retention period:** thời hạn giữ chứng cứ và dữ liệu theo nghiệp vụ/pháp lý, không đồng nghĩa phải giữ mọi private key.
- **Destruction eligibility:** điều kiện được phép hủy vật liệu khóa sau khi không còn phụ thuộc.

Ví dụ chính sách cho KEK:

~~~text
2030-01-01: KEK-v2 được tạo và kiểm tra ở pre-activation
2030-01-10: KEK-v2 active để Wrap DEK mới
2030-01-10: KEK-v1 ngừng Wrap mới nhưng còn phục vụ Unwrap theo policy
2030-02-10: Hoàn tất rewrap những DEK cần di chuyển
2030-03-01: Xác minh không còn bản bọc phụ thuộc KEK-v1
Sau phê duyệt: KEK-v1 mới đủ điều kiện bị hủy theo retention/backup
~~~

Các mốc thời gian này **chỉ là ví dụ**. Tổ chức phải xác định deadline thực tế theo mục tiêu availability, mức rủi ro, quy mô dữ liệu và chính sách lưu giữ.

### Không dùng tuổi khóa làm thước đo duy nhất

Một private key không xuất được ở HSM có thể có risk profile khác secret được sao chép tới nhiều môi trường. Một DEK mã hóa hàng tỷ bản ghi mỗi ngày có quy mô sử dụng khác DEK cho một tập dữ liệu nhỏ. Vì vậy **số lần sử dụng, mức độ phân phối, thuật toán và khả năng bị lộ** là các đầu vào quan trọng bên cạnh thời gian.

## 7. Quy trình rotation end-to-end

~~~mermaid
flowchart TD
    Trigger[Trigger theo lịch, usage hoặc sự cố] --> Scope[Kiểm kê key, version và hệ phụ thuộc]
    Scope --> Review[Risk review + approval + rollout plan]
    Review --> Create[Sinh key material mới trong môi trường phù hợp]
    Create --> Prepare[Pre-activation: IAM, metadata, verifier/client readiness]
    Prepare --> Check{Preflight và negative tests đạt?}
    Check -->|Không| Stop[Dừng, sửa và giữ khóa cũ nếu còn an toàn]
    Check -->|Có| Activate[Active và chuyển new-use routing]
    Activate --> Observe[Theo dõi, đối chiếu key version, lỗi, audit]
    Observe --> Migrate[Rewrap/re-encrypt hoặc duy trì read/verify cũ]
    Migrate --> Retire[Ngừng tạo dữ liệu mới bằng key cũ]
    Retire --> Dependency{Hết phụ thuộc và retention?}
    Dependency -->|Chưa| Legacy[Giữ legacy operation tối thiểu + rà soát định kỳ]
    Legacy --> Dependency
    Dependency -->|Rồi| Destroy[Phê duyệt tiêu hủy và kiểm chứng backup]
~~~

Sơ đồ trình bày **luồng chuẩn có kế hoạch**. Khi nghi compromise, bước đầu có thể là **suspend/cô lập ngay**, không đợi hoàn thành toàn bộ preflight; phải có nhánh xử lý khẩn cấp riêng.

### Giai đoạn 1 — Inventory và dependency mapping

Xác định chính xác:

- Key ID/version, loại key, thuật toán, nơi lưu KMS/HSM, owner/custodian, purpose, environment, tenant.
- Những ứng dụng, batch job, client, partner, chứng thư và vùng nào đang dùng.
- Tập dữ liệu, ciphertext, wrapped DEK, chữ ký, MAC, token hoặc phiên phụ thuộc.
- Cách định danh phiên bản trong dữ liệu: key ID trong envelope/manifest/header, `kid` trong JWT, certificate identifier, key fingerprint.
- Backup, archive, disaster recovery và bản sao key material nếu có.

**Không có dependency inventory thì không nên xóa khóa cũ** chỉ vì không thấy API call gần đây: có thể một bản backup hoặc artifact chưa được mở lại trong thời gian dài.

### Giai đoạn 2 — Chuẩn bị và kiểm thử

Sinh key mới bằng CSPRNG/KMS/HSM đáp ứng mục đích. Kiểm tra quyền, tham số, chứng thư, khả năng tương thích, kênh phân phối public key/secret, rollback và giới hạn thời gian. Khóa mới nên ở trạng thái **pre-activation về chính sách** cho tới khi đạt điều kiện.

### Giai đoạn 3 — Cutover

Chuyển **hoạt động mới** sang key version mới theo một bước có thể kiểm toán, sử dụng key ID/version rõ ràng. Tùy hệ thống, có thể cần rollout theo vùng/canary, đảm bảo cả writer và reader hiểu định dạng mới.

### Giai đoạn 4 — Di chuyển và retirement

Tùy loại key, thực hiện **rewrap DEK**, **re-encrypt bản mã**, cập nhật JWKS/chứng thư, chuyển giao HMAC secret hoặc duy trì khả năng đọc/xác minh lịch sử. Khi các phụ thuộc còn tồn tại, không hủy phiên bản cũ.

### Giai đoạn 5 — Xác minh và đóng thay đổi

Đối chiếu log KMS, metadata và dữ liệu. Kiểm tra tỷ lệ dùng key version mới, khả năng đọc dữ liệu cũ, hiệu năng, sai lệch giữa node/region và trạng thái các bên nhận. Ghi kết quả và người phê duyệt kết thúc.

## 8. KMS automatic rotation khác application key rotation

**Automatic rotation** là tính năng hấp dẫn nhưng **ngữ nghĩa phụ thuộc nhà cung cấp, loại khóa, cấu hình, khóa nhập và thao tác được hỗ trợ**.

### 8.1. Automatic rotation của key resource

Một số KMS có thể tự thay **backing key material** theo lịch trong một **logical key resource** mà ứng dụng vẫn sử dụng cùng key ID/ARN/URI. Dịch vụ có thể lưu thông tin cần thiết để giải mã các ciphertext được tạo bởi phiên bản vật liệu cũ.

Điều này **không đồng nghĩa**:

- Tự mã hóa lại mọi ciphertext/DEK bên ngoài KMS.
- Tự thay private key ký số, chứng thư hoặc JWT JWKS cho mọi loại key.
- Tự thu hồi mọi bản sao plaintext DEK đã được cấp ra.
- Tự xoay secret của đối tác HMAC ngoài KMS.
- Tự thay thuật toán, key usage, IAM/grant hoặc key owner.
- Tự giải quyết các bản backup và dữ liệu ngoài hệ thống của provider.

Không nên khẳng định một API automatic rotation áp dụng cho **mọi loại AES, HMAC, RSA, EC, imported key material hoặc multi-region key**. Phải kiểm tra tài liệu và trạng thái thực tế của sản phẩm.

### 8.2. Manual rotation hoặc thay resource

Với một số khóa, đặc biệt khóa bất đối xứng, khóa nhập, khóa có chứng thư, key của đối tác hoặc sản phẩm không hỗ trợ automatic rotation cho loại đó, quy trình có thể phải **tạo key resource mới**, phân phối public key/secret và cập nhật tham chiếu của ứng dụng.

Thay alias từ `signing-current` sang `signing-v2` chỉ là **routing**; phải chứng minh rằng **key material phía sau khác** và các bên xác minh biết đúng public key mới.

### 8.3. Phân biệt ba lớp phiên bản

| Lớp | Ví dụ | Phải xử lý |
| --- | --- | --- |
| **Logical key resource** | KMS resource ID | IAM, alias, state, audit |
| **Material version** | Vật liệu AES bên trong logical resource | Decrypt ciphertext cũ theo semantics KMS |
| **Application key version** | `kek-v2`, `invoice-sign-v5`, `kid` | Routing, metadata, protocol, client compatibility |

Ba lớp có thể trùng hoặc khác nhau. **Không dựa vào alias để quyết định liệu dữ liệu lịch sử còn giải mã được hay không.** Thực tế cần dựa vào định dạng ciphertext, version metadata và đặc tả provider.

## 9. Case study: xoay KEK trong envelope encryption

Giả sử Billing mã hóa hóa đơn bằng **AES-GCM với DEK ngẫu nhiên**. Mỗi DEK được bọc bởi KEK trong KMS. Hệ thống muốn đổi từ `KEK-v1` sang `KEK-v2`.

~~~mermaid
sequenceDiagram
    participant Owner as Key owner
    participant KMS as KMS/HSM
    participant App as Billing encryption service
    participant DB as Data + key metadata
    Owner->>KMS: Phê duyệt và tạo KEK-v2
    Note over KMS: KEK-v2 pre-activation, chính sách được kiểm tra
    Owner->>App: Phê duyệt cutover sang KEK-v2
    App->>KMS: Wrap DEK mới với KEK-v2
    KMS-->>App: Wrapped DEK v2
    App->>DB: Lưu ciphertext + wrapped DEK + key version
    Note over App,DB: DEK cũ có thể vẫn đang được bọc bởi KEK-v1
    App->>DB: Đọc wrapped DEK v1 cần rewrap
    App->>KMS: Rewrap theo API hoặc Unwrap có quyền + Wrap bằng v2
    KMS-->>App: Wrapped DEK v2 sau xác minh
    App->>DB: Cập nhật bản bọc và key version theo giao dịch
    Note over Owner,DB: Chỉ retire/hủy KEK-v1 sau kiểm tra mọi phụ thuộc
~~~

### 9.1. Tại sao rewrap thường không cần re-encrypt toàn bộ?

Trong envelope encryption:

~~~text
Ciphertext = AES-GCM-Encrypt(DEK, plaintext, nonce, AAD)
wrappedDEK_v1 = Wrap(KEK_v1, DEK)

Sau rotation KEK:
wrappedDEK_v2 = Wrap(KEK_v2, DEK)

DEK không đổi trong thao tác rewrap;
ciphertext có thể giữ nguyên nếu DEK, nonce, AAD và tag không đổi.
~~~

Đây là **mô hình khái niệm**. Cơ chế KMS có thể có API re-encrypt/wrap với semantics riêng; không giả định mọi provider cho phép xuất raw DEK hoặc rewrap theo đúng thao tác nêu trên.

### 9.2. Rewrap an toàn cần gì?

- **Đúng bản bọc đầu vào:** kiểm tra key ID/version, thuật toán, tenant và AAD/context nếu cơ chế dùng.
- **Xác thực và toàn vẹn:** không ghi đè bản bọc cũ nếu đầu ra mới chưa được xác nhận có thể giải bọc theo chính sách.
- **Khả năng retry:** operation và cập nhật metadata cần có idempotency/revision để không làm mất bản bọc khi process chết.
- **Giới hạn plaintext DEK:** nếu API trả DEK rõ, hạn chế thời gian trong bộ nhớ, không log, không đưa vào queue ngoài vùng bảo vệ.
- **Migration progress:** thống kê còn bao nhiêu wrapped DEK dùng KEK-v1, gồm archive và backup.
- **Giữ v1 khi cần:** cho phép legacy unwrap có kiểm soát đến khi hoàn tất, trừ trường hợp incident response đòi cô lập.

### 9.3. Nếu DEK đã bị lộ?

**Chỉ rewrap không đủ.** Đối thủ giữ DEK vẫn có thể giải mã ciphertext cũ mà họ đã có. Cần đánh giá thay DEK, **re-encrypt dữ liệu**, cập nhật bản bọc, truy vết truy cập và xử lý nghĩa vụ thông báo sự cố. Xoay KEK cũng không bảo đảm xóa được mọi bản sao DEK có sẵn trong cache, snapshot hoặc backup.

## 10. Case study: rotation DEK và chiến lược re-encrypt

Khác với KEK, **DEK mã hóa trực tiếp dữ liệu**. Rotation DEK có các lựa chọn:

1. **New-write-only rotation:** DEK mới dùng cho bản ghi mới; bản ghi cũ tiếp tục dùng DEK cũ. Phù hợp khi chính sách cho phép data version cũ tồn tại và key cũ vẫn an toàn.
2. **Lazy re-encryption:** Khi đọc/sửa một bản ghi, chuyển sang DEK mới có kiểm soát. Có thể cần job nền cho bản ghi không được đọc thường xuyên.
3. **Bulk re-encryption:** Di chuyển toàn bộ dữ liệu phụ thuộc sang DEK mới theo kế hoạch có batching, kiểm tra và khả năng resume.
4. **Emergency re-encryption:** Khi DEK bị lộ, ưu tiên hạn chế truy cập và đánh giá dữ liệu lịch sử; job di chuyển cần được thiết kế theo độ nhạy và phạm vi đã bị ảnh hưởng.

### Các điểm bắt buộc

- Mỗi ciphertext phải có cách tìm được đúng **DEK version** và **nonce/IV**, cùng AAD nếu dùng AEAD.
- Khi mã hóa lại bằng **AES-GCM**, tạo nonce mới đúng quy tắc; không tái sử dụng nonce dưới cùng key.
- Giải mã bản cũ phải xác minh tag trước khi ghi bản mới. Không cho phép dữ liệu sai tính toàn vẹn được “chuyển đổi thành hợp lệ”.
- Cập nhật ciphertext, tag, nonce và key ID theo **transaction hoặc cơ chế versioned/atomic**; tránh trạng thái ciphertext mới nhưng metadata trỏ key cũ.
- Backup phải có lộ trình: xóa DEK-v1 sớm có thể khiến bản backup cũ không phục hồi được.
- Re-encryption tốn I/O/CPU và có thể tác động latency, consistency; cần throttling và cơ chế xác minh.

**Không phải một lịch rotation đồng nghĩa lập tức mã hóa lại hàng petabyte dữ liệu.** Chính sách phải nói rõ **mục tiêu, thời hạn migration, ngoại lệ và tiêu chí hoàn thành**.

## 11. Signing-key rotation, chứng thư và kiểm tra chữ ký cũ

Một **private signing key** dùng ký hóa đơn, phần mềm hoặc chứng thư cần chính sách chú ý **niềm tin của bên xác minh**. Không được coi việc KMS tạo key v2 là đủ.

### 11.1. Các bước điển hình

1. Sinh **private/public key pair mới** đúng thuật toán trong HSM/KMS hoặc vùng bảo vệ được chấp thuận.
2. Kiểm tra chính sách `Sign`, quyền không xuất private key, key usage và nguồn ngẫu nhiên.
3. Phát hành/đăng ký **public verification key/chứng thư**, nếu hồ sơ PKI yêu cầu.
4. Phân phối trust chain, `kid`, JWKS hoặc identifier mới tới bên xác minh **trước khi bắt đầu ký mới**.
5. Chuyển signing workload sang **key v2**; ghi nhận phiên bản được dùng cho mỗi chữ ký.
6. Chặn ký mới bằng v1, nhưng giữ **public key/chứng thư và bằng chứng** để kiểm tra chữ ký lịch sử.
7. Xử lý private key v1 theo retention/cryptoperiod và chính sách hủy; không xóa chứng cứ cần cho những chữ ký dài hạn.

~~~mermaid
sequenceDiagram
    participant KM as Key custodian
    participant HSM as HSM/KMS
    participant Issuer as Signing service
    participant Verifier as Verifier/partner
    KM->>HSM: Tạo signing key v2 (chưa active)
    HSM-->>KM: Public key/chứng thư tham chiếu
    KM->>Verifier: Phân phối public key hoặc trust metadata v2
    Verifier-->>KM: Đã sẵn sàng xác minh
    KM->>Issuer: Cutover new signatures sang v2
    Issuer->>HSM: Sign bằng key v2 theo chính sách
    HSM-->>Issuer: Chữ ký v2
    Issuer-->>Verifier: Dữ liệu + chữ ký + key/cert identity
    Note over Verifier: Tiếp tục xác minh chữ ký v1 theo chứng cứ lịch sử
~~~

### 11.2. JWT và `kid`

Trong hệ thống phát hành JWT, một chiến lược phổ biến là **publish-before-use**:

- Đưa public key mới vào JWKS tin cậy và cho verifier làm mới cache.
- Chỉ sau khi tương thích, phát token mới với `kid` trỏ key mới.
- Duy trì public key cũ cho token hợp lệ chưa hết hạn, trừ khi chính sách ứng cứu yêu cầu thu hồi sớm.
- Khi không còn token hợp lệ phụ thuộc, mới loại public key cũ khỏi tập cho phép.

**Không được tin một `kid` bất kỳ để fetch public key từ URL do attacker điều khiển.** Verifier phải khóa issuer, audience, thuật toán được phép, trust source và ràng buộc key ID.

### 11.3. Certificate renewal khác key rotation

Thay một chứng thư TLS/PKI **với cùng private key** không phải key rotation theo nghĩa thay vật liệu khóa. Chính sách cần ghi rõ mục tiêu: **renew certificate** hay **generate a new key pair and reissue certificate**.

### 11.4. Chữ ký lịch sử và trusted timestamp

Chữ ký số cũ có thể cần kiểm tra nhiều năm sau khi khóa ký đã ngừng hoạt động. Công tác giữ **public key, chứng thư, CRL/OCSP hoặc bằng chứng LTV/TSA** (tùy profile) khác với việc tiếp tục cho private key ký mới. Nếu private key v1 được kết luận compromised, phải đánh giá độ tin cậy của chữ ký cũ dựa trên thời gian và bằng chứng, không coi phép `Verify` đúng về mặt toán học là đủ.

## 12. HMAC, webhook và rotating shared secrets

**HMAC key** là bí mật dùng chung cho bên tạo và bên xác minh MAC. Đổi HMAC key khó hơn thay public verification key vì **cả hai bên đều phải biết bí mật mới** và bảo vệ nó.

### Mẫu chuyển tiếp có kiểm soát

| Giai đoạn | Sender | Receiver | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| **Chuẩn bị** | Có key v1, nhận key v2 an toàn nhưng chưa dùng | Cài khả năng xác minh v1/v2 theo key ID | Đường phân phối secret, log |
| **Cutover** | Tạo HMAC mới bằng v2 | Xác minh theo version cho phép | Nhầm version hoặc key lookup |
| **Grace window** | Chỉ tạo tag v2 | Có thể tạm verify v1 cho retry cũ | Replay, kéo dài quyền key v1 |
| **Kết thúc** | Không dùng v1 | Dừng xác minh bằng v1 khi đã hết thông điệp hợp lệ | Không bỏ quên consumer/queue |
| **Compromise** | Ngừng dùng key lộ ngay khi khả thi | Không tiếp tục tin vào tag từ key lộ | Không dùng grace window mù quáng |

Gắn **key ID/version** và thông tin như timestamp, event ID vào định dạng thông điệp theo giao thức. Những trường có giá trị bảo mật phải **được ràng buộc vào dữ liệu được MAC xác thực**, với serialization không mơ hồ. Có thể cần **nonce/event ID và cửa sổ thời gian** để chống replay; HMAC tự nó chỉ xác thực message với secret, không tự chống phát lại.

**Không phát cùng một HMAC key cho mọi đối tác nếu không có lý do rõ ràng.** Tách theo partner/tenant có thể giảm blast radius và đơn giản hóa rotation khi một đối tác bị mất secret.

## 13. ECDH, TLS và sự khác biệt giữa khóa dài hạn/ephemeral

### 13.1. Static agreement key

**Static ECDH/X25519 key** có thể được đăng ký giữa các thiết bị hoặc dịch vụ. Rotation cần sinh cặp mới, phân phối public key và bảo đảm giao thức xác thực peer/trust trước khi cho phép thỏa thuận phiên mới. Nếu khóa tĩnh bị lộ, phạm vi ảnh hưởng phiên cũ phải phân tích theo giao thức.

### 13.2. Ephemeral ECDHE key

Một private agreement key tạm sinh cho từng phiên/handshake **không nên chờ cron mỗi quý** mới được đổi. Việc sinh mới/hủy các khóa tạm thuộc **state machine của giao thức**. Forward secrecy phụ thuộc giao thức xác thực, việc hủy bí mật tạm, và khả năng bảo vệ traffic secrets đã sinh.

Trong TLS 1.3, cần phân biệt **private key xác thực dài hạn** (ví dụ của chứng thư) với **(EC)DHE key share tạm**. Chúng có vòng đời, cơ chế rotation và tác động compromise khác nhau.

### 13.3. TLS certificate rotation

Kế hoạch thay chứng thư/private key máy chủ còn phải xét:

- Trust chain, SAN/hostname, key usage và thuật toán được chấp nhận.
- Nhiều instance/load balancer/region có đồng bộ certificate bundle không.
- Client connection pool và TLS session đang mở có tiếp tục sử dụng khóa phiên đã thiết lập không.
- Khả năng restart/hot reload, giám sát lỗi handshake và xác nhận không phục vụ certificate hết hạn.
- Nếu private authentication key bị lộ, xử lý thu hồi trust/credential và đánh giá phiên, không chỉ chờ chứng thư cũ hết hạn.

### 13.4. Thay HSM/KMS provider

Chuyển nhà cung cấp là một dạng migration đặc biệt: private key **không xuất được** có thể buộc tạo key pair mới, đổi chứng thư/định danh và cập nhật mọi bên phụ thuộc. Không mặc định “copy alias sang KMS mới” sẽ giữ nguyên vật liệu.

## 14. Quy trình phê duyệt, phân tách nhiệm vụ và IAM

Rotation policy phải nói rõ **vai trò và quyền quyết định**. Nếu một principal tự tạo key mới, cấp `Decrypt`, thay alias và xóa key cũ mà không kiểm soát, chính sách lịch rotation sẽ ít giá trị.

| Vai trò | Trách nhiệm | Điều không nên mặc định được làm |
| --- | --- | --- |
| **Key owner** | Phê duyệt mục đích, cryptoperiod, trigger, deadline, thay đổi phạm vi và mức rủi ro | Tự xuất key material hoặc thay quyền KMS |
| **Key custodian** | Sinh/cấu hình khóa, KMS/HSM, key version, backup/DR và thao tác chuyển đổi | Tự ký dữ liệu/giải mã ngoài nhiệm vụ |
| **Application owner** | Sẵn sàng hỗ trợ key version, tích hợp, cutover, xử lý dữ liệu và rollback | Tự thay state để bỏ qua review |
| **Security reviewer** | Kiểm tra entropy, thuật toán, least privilege, rủi ro compromise và bằng chứng kiểm thử | Tự phê duyệt thay đổi do mình thực thi khi cần độc lập |
| **Incident responder** | Suspend/cô lập khẩn cấp và phân tích ảnh hưởng | Xóa vĩnh viễn khóa khi chưa biết dữ liệu phụ thuộc |
| **Auditor** | Đối chiếu kế hoạch, phê duyệt, thao tác thực, dữ liệu lịch sử và kết quả | Sửa nhật ký hoặc sử dụng key material |

### Kiểm soát truy cập

- Quyền `CreateKey/GenerateDataKey`, `Sign`, `Decrypt`, `GenerateMac`, `DeriveKey`, `Wrap/Unwrap` và thay policy/alias phải được tách theo nhu cầu.
- Key mới phải được tạo với chính sách **pre-activation**: chưa cho production dùng trước phê duyệt.
- Chặn được lời gọi trực tiếp KMS/HSM trái policy, không chỉ từ chối ở application gateway.
- Nếu có break-glass để xử lý dữ liệu cũ, giới hạn principal, scope, thời gian, số thao tác và audit; sau đó thu hồi.
- Không đưa raw DEK/KEK, private key, HMAC secret hoặc reset token vào audit hoặc công cụ ticket.

### Approval cho scheduled và incident rotation khác nhau

Scheduled rotation có thể đi qua change request và các cửa sổ triển khai. Khi compromise, security team có thể phải **suspend ngay** theo quyền khẩn cấp, rồi phê duyệt hậu kiểm theo chính sách. **Quyền resume** hoặc xóa hẳn khóa nên có yêu cầu riêng, tránh mở lại một key đã lộ.

## 15. Mẫu rotation policy — metadata có thể kiểm toán

Dưới đây là **ví dụ khai báo chính sách**, không phải file cấu hình cloud KMS, và các mốc thời gian chỉ mang tính minh họa.

~~~yaml
policyId: "billing-kek-rotation-v1"
policyVersion: "1.0"
appliesTo:
  environment: "production"
  service: "billing-platform"
  keyPurpose: "DEK_KEY_WRAPPING"
  keyType: "SYMMETRIC_KEK"
  keyInventorySelector: "purpose-and-service"

governance:
  keyOwner: "billing-data-protection-owner"
  keyCustodian: "platform-kms-team"
  reviewer: "security-architecture"
  changeApprovalRequired: true
  emergencySuspensionRole: "security-incident-responder"

rotationTriggers:
  scheduledReview: "every-quarter"
  newUseCryptoperiod: "according-to-approved-cryptoperiod"
  eventDriven:
    - "SUSPECTED_KEY_COMPROMISE"
    - "UNAUTHORIZED_KEY_USE"
    - "ALGORITHM_OR_PROVIDER_RISK"
    - "POLICY_OR_DATA_SCOPE_CHANGE_REQUIRING_NEW_KEY"

preflight:
  verifyKeyMaterialProvenance: true
  verifyKmsPolicyAndIam: true
  testNewKeyInApprovedScope: true
  verifyReadersSupportKeyVersion: true
  verifyRestoreAndBackupDependencies: true

cutover:
  requireExplicitApproval: true
  activateNewKeyBeforeNewWrites: true
  forbidUnapprovedFallback: true
  requireKeyVersionInWrappedDekMetadata: true
  requireAuditForKeyRoutingChange: true

legacy:
  stopOldKeyForNewWrap: true
  permitControlledOldUnwrapUntilMigrationComplete: true
  rewrapRequired: "per-risk-and-retention-plan"
  destroyOnlyAfterDependencyCheck: true

incidentResponse:
  failClosedOnCompromise: true
  evaluateDekExposure: true
  requireDataImpactAssessment: true
  revokeAffectedGrantsAndSessions: true

evidence:
  recordApproval: true
  recordKeyIdsAndVersions: true
  recordNegativeTests: true
  recordMigrationCoverage: true
  recordDestructionAfterRetention: true
~~~

### Những điều mẫu chính sách phải được bổ sung khi triển khai

1. **Mã thời gian cụ thể**: lịch đánh giá và cryptoperiod đã duyệt theo loại khóa, không để chuỗi chung chung trong production.
2. **Phân cấp chính sách**: global minimum, service-specific override và điều kiện exception/waiver.
3. **Tính ràng buộc IAM**: ai thực sự được gọi KMS theo key ID, operation, vùng và tenant.
4. **Tính khả dụng**: SLA đọc/ghi, khả năng rollback, hàng đợi retry, độ trễ và mục tiêu phục hồi.
5. **Phụ thuộc lịch sử**: số DEK/backup/chữ ký/tag chưa chuyển, chi phí và thời hạn.
6. **Cơ chế kiểm toán**: nguồn log đáng tin, retention, kiểm chứng trạng thái thực và lịch rà soát.

**Không chứa private key, secret, plaintext DEK hay password trong file chính sách**. Các ID như `approvalRef`, `policyVersion` và `keyId` phải gắn với hệ thống có thẩm quyền thay vì chỉ tự khai báo bằng text.

## 16. Ví dụ Java 11+: đánh giá trigger rotation, không tự đổi khóa

Ví dụ sau chỉ quyết định **có cần xử lý rotation** từ metadata và tín hiệu rủi ro hay không. Nó **không tạo khóa hoặc thay trạng thái KMS/HSM**; đây là bước đánh giá trong control plane, cần được theo sau bởi phê duyệt và workflow kỹ thuật.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public final class RotationPolicyDemo {
    enum KeyState {
        PRE_ACTIVATION, ACTIVE, SUSPENDED,
        DEACTIVATED, COMPROMISED, DESTROYED
    }

    enum RiskSignal {
        NONE, SUSPECTED_EXPOSURE, ALGORITHM_DEPRECATED
    }

    enum Decision {
        NO_ACTION, PLAN_ROTATION, INCIDENT_RESPONSE, REVIEW_STATE
    }

    static final class RotationPolicy {
        final Duration maximumNewUseAge;
        final long maximumNewUseOperations;

        RotationPolicy(Duration maximumNewUseAge, long maximumNewUseOperations) {
            if (maximumNewUseAge == null || maximumNewUseAge.isZero()
                    || maximumNewUseAge.isNegative()
                    || maximumNewUseOperations < 1) {
                throw new IllegalArgumentException("Invalid rotation policy");
            }
            this.maximumNewUseAge = maximumNewUseAge;
            this.maximumNewUseOperations = maximumNewUseOperations;
        }
    }

    static final class KeyRecord {
        final String keyId;
        final String purpose;
        final KeyState state;
        final Instant activatedAt;
        final long newUseOperations;

        KeyRecord(String keyId, String purpose, KeyState state,
                  Instant activatedAt, long newUseOperations) {
            if (keyId == null || keyId.isEmpty()
                    || purpose == null || purpose.isEmpty()
                    || state == null || activatedAt == null
                    || newUseOperations < 0) {
                throw new IllegalArgumentException("Invalid key record");
            }
            this.keyId = keyId;
            this.purpose = purpose;
            this.state = state;
            this.activatedAt = activatedAt;
            this.newUseOperations = newUseOperations;
        }
    }

    static Decision evaluate(
            RotationPolicy policy, KeyRecord key,
            RiskSignal signal, Clock clock) {

        Objects.requireNonNull(policy, "policy");
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(signal, "signal");
        Objects.requireNonNull(clock, "clock");

        // Rủi ro khẩn cấp phải ưu tiên hơn lịch.
        if (signal == RiskSignal.SUSPECTED_EXPOSURE
                || key.state == KeyState.COMPROMISED) {
            return Decision.INCIDENT_RESPONSE;
        }
        if (signal == RiskSignal.ALGORITHM_DEPRECATED) {
            return Decision.PLAN_ROTATION;
        }

        // Không tự re-activate key đang suspended/deactivated.
        if (key.state != KeyState.ACTIVE) {
            return Decision.REVIEW_STATE;
        }

        Instant now = clock.instant();
        if (now.isBefore(key.activatedAt)) {
            return Decision.REVIEW_STATE;
        }

        boolean ageLimitReached = !now.isBefore(
                key.activatedAt.plus(policy.maximumNewUseAge));
        boolean useLimitReached =
                key.newUseOperations >= policy.maximumNewUseOperations;

        return ageLimitReached || useLimitReached
                ? Decision.PLAN_ROTATION
                : Decision.NO_ACTION;
    }

    public static void main(String[] args) {
        // CHỈ DEMO: 90 ngày là thông số giả định, không phải
        // khuyến nghị cho mọi key loại nào cũng như nhau.
        RotationPolicy demoPolicy =
                new RotationPolicy(Duration.ofDays(90), 1_000_000L);

        Clock now = Clock.fixed(
                Instant.parse("2030-04-15T00:00:00Z"), ZoneOffset.UTC);

        KeyRecord activeKek = new KeyRecord(
                "billing-kek-v2", "DEK_KEY_WRAPPING",
                KeyState.ACTIVE, Instant.parse("2030-01-01T00:00:00Z"),
                200_000L);

        System.out.println("Scheduled: "
                + evaluate(demoPolicy, activeKek,
                        RiskSignal.NONE, now));
        System.out.println("Suspected exposure: "
                + evaluate(demoPolicy, activeKek,
                        RiskSignal.SUSPECTED_EXPOSURE, now));

        KeyRecord suspended = new KeyRecord(
                "billing-kek-v2", "DEK_KEY_WRAPPING",
                KeyState.SUSPENDED, Instant.parse("2030-01-01T00:00:00Z"),
                200_000L);
        System.out.println("Suspended: "
                + evaluate(demoPolicy, suspended,
                        RiskSignal.NONE, now));
    }
}
~~~

**Kết quả dự kiến:**

~~~text
Scheduled: PLAN_ROTATION
Suspected exposure: INCIDENT_RESPONSE
Suspended: REVIEW_STATE
~~~

### Điều ví dụ thể hiện

- **Age/usage** có thể cùng là trigger.
- **Suspected exposure** được xử lý theo luồng ứng cứu riêng, không chờ lịch.
- Khóa `SUSPENDED` không tự được mở lại chỉ vì tới mốc rotation.
- `Duration.ofDays(90)` là dữ liệu demo, **không phải mức cryptoperiod áp dụng chung**.

### Thiếu gì để trở thành hệ thống thật?

- Xác minh key inventory, nguồn dữ liệu `newUseOperations`, cảnh báo lỗi meter và giới hạn của từng thuật toán.
- Sử dụng policy được phê duyệt theo **purpose, risk tier, key type**, không dùng một đối tượng chung cho mọi khóa.
- IAM/key policy KMS/HSM, approval/dual control, quyết định đầu vào có ký hoặc kiểm chứng nguồn.
- State machine có **idempotency, compare-and-swap/revision**, phân tán và chống race.
- Workflow tạo vật liệu mới, client readiness, canary, cutover, migration/rewrap/re-encrypt.
- Khả năng suspend khẩn cấp, rollback, giữ dữ liệu cũ, lưu log và chứng cứ hủy.
- **Fail closed** khi trạng thái provider không xác định, không fallback sang RNG/key cũ ngoài phê duyệt.

## 17. Cutover, rollback và các lỗi hệ phân tán

Rotation phải tính đến nhiều service, vùng, cache và yêu cầu đang xử lý.

### 17.1. Publish-before-use, dual-read/single-write

Một mẫu chuyển đổi hữu ích là:

- **Prepare:** Key v2 đã có ở KMS và policy, reader/verifier được triển khai để nhận **v1 + v2** theo quyền.
- **Cutover:** Writer/signer chỉ dùng **v2** cho output mới; không tự động chọn key v1 khi gặp lỗi v2.
- **Grace/legacy:** Reader/verifier có thể xử lý output v1 trong thời hạn và phạm vi đã duyệt.
- **Retire:** Khi mọi phụ thuộc được xử lý, ngừng quyền mới v1 và hủy theo quy trình.

**Dual-read không có nghĩa phải luôn giữ mọi private key hoạt động.** Ví dụ chữ ký số chỉ cần public key cũ để verify; nhưng DEK/KEK cần private/symmetric secret cho decrypt/unwrap nếu chưa migrate.

### 17.2. Alias và cache

`currentKey` hoặc `activeKeyId` có thể bị cache theo service instance. Nếu control plane đổi alias nhưng ứng dụng cũ chưa refresh, một số request vẫn dùng key cũ. Cần:

- Mốc cutover và **policy revision** rõ ràng.
- Kiểm tra điều kiện sử dụng ở điểm thực thi, không chỉ lúc khởi động.
- Theo dõi tỷ lệ tạo output bằng **key ID/version thực**.
- Cơ chế vô hiệu cache, quản lý đồng bộ đa vùng và thời hạn cửa sổ chuyển đổi.
- Chặn thao tác new-use v1 khi chính sách yêu cầu dù alias chưa cập nhật.

### 17.3. Rollback không phải hủy v2

Nếu key v2 đã mã hóa record hoặc ký tài liệu thật, rollback routing về v1 **không xóa phụ thuộc mới trên v2**. Phải tiếp tục lưu được key v2 để giải mã/xác minh output đã tạo, hoặc có kế hoạch migration hợp lệ.

Không xóa v2 chỉ vì rollback deployment. Nếu v2 bị nghi compromise, phải đi theo **incident response**, không dùng rollback như cách hợp thức hóa khóa không an toàn.

### 17.4. Transaction và idempotency

Với dữ liệu đã mã hóa, **ciphertext + key ID + nonce + tag/AAD metadata** phải nhất quán. Với rewrap, **wrapped DEK + KEK version** phải được cập nhật cùng nhau theo giao dịch/atomic state change có thể phục hồi.

Workflow cần idempotency token, checkpoint, retry/backoff, kiểm thử crash recovery và kiểm tra dữ liệu ngẫu nhiên. Đừng để một job bị restart bọc DEK nhiều lần nhưng metadata không khớp.

## 18. Kiểm thử và tiêu chí hoàn thành rotation

Một key được tạo mới không đủ để kết luận đã rotation thành công.

### Test theo giai đoạn

| Giai đoạn | Kiểm thử cần có | Kết quả mong đợi |
| --- | --- | --- |
| Preflight | Kiểm tra thuật toán, entropy, key type, IAM và quyền export | Không dùng key sai mục đích |
| Pre-activation | Gọi thử operation sản xuất bằng key chưa active | **Bị từ chối** theo policy |
| Reader readiness | Giải mã/xác minh output v1 và v2 trên môi trường được phép | Hai phiên bản được nhận đúng |
| Cutover | Tạo output mới, kiểm tra key ID/version | Mọi output mới dùng v2 theo kế hoạch |
| Negative testing | Dùng sai tenant, principal, purpose, operation | Bị từ chối |
| Migration | Kiểm tra rewrap/re-encrypt từng batch; crash/retry | Không mất bản bọc, metadata nhất quán |
| Multi-region | Kiểm tra cache/alias/replica ở mọi vùng | Không có writer dùng key sai |
| Legacy validation | Khôi phục backup hoặc xác minh chữ ký v1 | Không mất khả năng xử lý theo retention |
| Retirement | Thử operation new-use v1 | Bị từ chối |
| Destruction readiness | Liệt kê tất cả dữ liệu và bản backup phụ thuộc | Không còn đường cần key bị hủy |

### Các chỉ số nên theo dõi

- Phần trăm output mới theo key version `v2` so với `v1`.
- Số wrapped DEK còn phụ thuộc KEK cũ.
- Số bản mã cần re-encrypt, số đã hoàn tất và lỗi tính toàn vẹn.
- Số client/verifier đã nhận public key mới.
- Số request `Sign/Decrypt/Unwrap` bị từ chối không đúng dự kiến.
- Lượng request dùng key cũ sau cutover, theo principal/region.
- Chứng cứ phê duyệt, test âm tính, thời điểm đổi IAM/policy và trạng thái final.

Không chỉ giám sát `success rate`: nếu một ứng dụng vẫn ký bằng v1 mà bên nhận còn tin v1, request có thể thành công trong khi **rotation policy đã bị vi phạm**.

## 19. Rotation khẩn cấp khi key compromise

**Compromise** không phải một phiên bản nhanh của scheduled rotation. Cần xử lý **threat model và tác động lịch sử**.

### Runbook khái niệm

1. **Cô lập:** Suspend/disable key hoặc thu hồi principal/grant; chặn ký/mã hóa/unwrap theo mức rủi ro.
2. **Bảo toàn chứng cứ:** Key ID, event log, thời điểm, người gọi, API, bản sao key material, kết quả phát hành và trạng thái policy.
3. **Xác định điều gì thực sự lộ:** Chỉ credential truy cập KMS, hay raw KEK/DEK/private signing key? Đối thủ có ciphertext/public key/tag nào?
4. **Phạm vi:** Liệt kê bản mã, wrapped DEK, chữ ký, JWT, HMAC webhook, thỏa thuận khóa và backup liên quan.
5. **Sinh key mới từ nguồn tin cậy:** Nếu vấn đề là entropy/RNG yếu, sửa nguồn trước khi tạo vật liệu mới.
6. **Chuyển quyền và trust:** IAM, key policy, chứng thư/JWKS/public key, secret đối tác và đường sử dụng.
7. **Xử lý dữ liệu lịch sử:** Re-encrypt khi DEK bị lộ; đánh giá dữ liệu trước đây đã bị lấy, chữ ký/token đã phát và khả năng giả mạo.
8. **Giám sát và thông báo:** Theo yêu cầu tổ chức/pháp lý, cập nhật owner, partner, auditor và kế hoạch phòng ngừa tái phát.
9. **Retire/hủy:** Chỉ tiêu hủy khi đã đánh giá phụ thuộc, bằng chứng lưu trữ và rủi ro; private key compromised không nên được resume để dùng bình thường.

### Cần phân biệt các trường hợp

| Đối tượng lộ | Chỉ đổi KEK có đủ không? | Việc cần đánh giá |
| --- | --- | --- |
| **KMS API credential** nhưng key material chưa xác định lộ | Không thể kết luận | Các lần `Decrypt/Sign/Unwrap` đã bị lạm dụng, IAM, grant và key usage |
| **KEK plaintext** | **Không tự đủ** | Các wrapped DEK/ciphertext mà đối thủ có thể tiếp cận, nguy cơ DEK lộ |
| **DEK plaintext** | **Không** | Re-encrypt dữ liệu, bản mã lịch sử, backup và rò rỉ plaintext |
| **Private signing key** | Không liên quan đơn thuần KEK | Chữ ký đã phát, giả mạo, chứng thư/JWKS/trust, key replacement |
| **HMAC key** | Không | Tag có thể bị giả mạo, partner secret, anti-replay, key version |
| **Static ECDH private key** | Không | Phiên liên quan, shared secret, public key pinning, giao thức và forward secrecy |

Không tuyên bố rằng rotation xong là **mọi bản mã bị thu thập trước đó đều được bảo vệ trở lại**. Đối thủ có thể đã sao chép bí mật/đã giải mã plaintext.

## 20. Lỗi thường gặp trong rotation policy

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Một lịch 90 ngày cho mọi khóa | Không phù hợp purpose, usage và risk | Cryptoperiod/trigger theo loại và phạm vi |
| Chỉ thay alias, không xác minh key material mới | Tưởng đã rotate nhưng vẫn dùng secret cũ | Kiểm tra key ID, version và provenance |
| Tin automatic KMS rotation đã re-encrypt DB | Ciphertext hoặc DEK cũ vẫn phụ thuộc theo semantics | Phân biệt logical/material/application rotation |
| Xóa KEK cũ ngay sau cutover | Wrapped DEK chưa chuyển không mở được | Dependency inventory và rewrap/legacy unwrap |
| Chỉ rewrap khi DEK bị lộ | Không ngăn đối thủ dùng DEK đã lấy | Thay DEK, re-encrypt và xử lý dữ liệu quá khứ |
| Rotate signing key nhưng không phân phối public key | Verifier từ chối chữ ký mới | Publish-before-use, PKI/JWKS/partner readiness |
| Coi certificate renewal là private-key rotation | Vẫn dùng key material cũ | Tạo cặp mới và cấp chứng thư theo mục tiêu |
| Gỡ public key cũ quá sớm | Không verify được token/chữ ký lịch sử hợp lệ | Grace window/retention có kiểm soát |
| Giữ HMAC v1 verify vô thời hạn | Cửa sổ giả mạo kéo dài khi secret lộ | TTL/retry policy, anti-replay, sunset |
| Không kiểm tra nonce/usage limit | Có thể lặp nonce GCM dù vừa rotate | Nonce allocation + per-key limits |
| Fallback im lặng sang key cũ khi key mới lỗi | Tạo output trái policy | Fail closed, approved rollback |
| Không xét cache/region | Node vẫn dùng v1 sau cutover | Revision, invalidation, negative tests |
| Không giữ version trong ciphertext/tag/manifest | Không biết dùng key nào để xác minh/giải mã | Envelope metadata/key ID rõ ràng |
| Không có owner/custodian | Không ai chịu trách nhiệm decision và incident | Key inventory + RACI + approval |
| Ghi secret vào ticket/log để hỗ trợ rotation | Lộ key material | Dùng ID/handle, không xuất plaintext key |
| Hủy key trước khi thử restore backup | Mất khả năng khôi phục | Kiểm thử DR, retention và destruction approval |
| Đổi quyền `Sign` nhưng không xét token đã phát | JWT/chữ ký cũ vẫn được bên nhận tin | Cập nhật trust/revocation và kiểm tra lịch sử |
| Chỉ kiểm tra happy path | Sai permission, stale cache không bị phát hiện | Negative test và diễn tập thất bại |
| Chờ lịch định kỳ dù nghi compromise | Tiếp tục sử dụng bí mật đã lộ | Emergency isolation và event-driven rotation |

## 21. Checklist xây dựng Rotation policy cho production

1. **Inventory:** Đã xác định key ID/version, algorithm, type, purpose, owner, custodian, nơi lưu và các môi trường/tenant không?
2. **Threat model:** Độ nhạy dữ liệu, khả năng bị lộ, số bản sao key material, tần suất sử dụng và tác động nếu compromise?
3. **Cryptoperiod:** Có thời hạn new-use/legacy-processing/retention rõ ràng, phù hợp từng loại khóa và chính sách tổ chức?
4. **Trigger:** Ngoài lịch, có xử lý compromise, IAM abuse, RNG failure, algorithm change, usage/nonce limits và thay đối tác?
5. **Lead time:** Có đủ thời gian tạo khóa mới, cấp/phân phối chứng thư hoặc secret, thử DR và chuẩn bị client?
6. **Key generation:** Vật liệu mới được tạo bằng CSPRNG/HSM/KMS phù hợp, không sao chép secret cũ hoặc dùng seed có thể đoán?
7. **Pre-activation:** Khóa mới có bị chặn dùng production trước khi được phê duyệt, và có kiểm thử từ chối thực sự ở provider?
8. **KMS semantics:** Hiểu rõ automatic rotation, key material version, logical key, imported key, khả năng export và alias của sản phẩm?
9. **Separation of duties:** Tạo key, phê duyệt, cutover, dùng key, rotate, destroy và audit có quyền độc lập thích hợp?
10. **DEK/KEK:** Có phân biệt rewrap với re-encrypt và dữ liệu phụ thuộc từng phiên bản?
11. **AEAD:** Với AES-GCM/CTR, đã có quy tắc nonce/IV và hạn mức mỗi key, không dựa vào calendar rotation để che lỗi nonce?
12. **Signing keys:** Bên xác minh có public key/chứng thư mới trước cutover; còn cơ chế xác minh chữ ký lịch sử?
13. **JWT/HMAC:** Có xử lý key ID, cache, grace period, retry, revocation và anti-replay theo mục đích?
14. **ECDH/TLS:** Phân biệt static/ephemeral agreement key với signing/authentication key; khi cần đã thay chứng thư và session/trust đúng?
15. **Cutover:** Writer/signer chọn đúng key version, reader/verifier biết version, các node/region thống nhất và có phương án ngừng dùng v1?
16. **Rollback:** Nếu v2 đã tạo dữ liệu/chữ ký thật, có giữ khả năng decrypt/verify chúng sau khi rollback routing?
17. **Migration:** Rewrap/re-encrypt có transaction, idempotency, checkpoint, integrity check và tiến độ được theo dõi?
18. **Backup/DR:** Có kiểm thử phục hồi bản backup cũ, đánh giá replica/snapshot và điều kiện hủy key còn phụ thuộc?
19. **Emergency:** Khi nghi compromise, có quyền cô lập khẩn cấp, phân tích ảnh hưởng lịch sử và kế hoạch phát lại trust/key?
20. **Auditing:** Có log owner, approver, policy version, key ID, operation, mốc cutover, negative test và hoàn tất migration mà không lộ secret?
21. **Success criteria:** Có thể chứng minh không còn output mới bằng key cũ, dữ liệu lịch sử vẫn xử lý đúng và mọi ngoại lệ đã được phê duyệt?
22. **Hủy khóa:** Chỉ destroy khi đã đạt dependency/retention checks và có bằng chứng xử lý vật liệu, grant, backup theo mô hình KMS/HSM?

### Ghi nhớ

**Rotation policy** phải quy định **trigger, cryptoperiod, trách nhiệm, cách tạo khóa mới, cutover, xử lý phụ thuộc, rollback, thu hồi và hủy**. Một lịch định kỳ duy nhất không phù hợp mọi loại khóa; cần **chính sách theo purpose và rủi ro**, có nhánh khẩn cấp khi nghi compromise. **Automatic rotation của KMS** không mặc nhiên thay mọi key resource hoặc mã hóa lại toàn bộ dữ liệu. Với **envelope encryption**, thay **KEK** có thể cần **rewrap DEK**, trong khi thay **DEK** có thể đòi **re-encrypt dữ liệu**; nếu DEK đã lộ, rewrap không phục hồi bí mật. Với **chữ ký số, JWT, HMAC và ECDH/TLS**, phải giải quyết việc phân phối/verifier, trust và dữ liệu/phiên đã tồn tại. Chính sách chỉ có hiệu lực khi được **cưỡng chế bởi IAM/KMS/HSM, ứng dụng, key inventory, kiểm toán và quy trình vòng đời**; rotation hoàn thành khi bằng chứng chứng minh cả hoạt động mới lẫn phụ thuộc lịch sử được xử lý an toàn.

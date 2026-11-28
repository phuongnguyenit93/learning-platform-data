# Envelope metadata (Siêu dữ liệu của envelope encryption)

## 1. Envelope metadata là gì và tại sao quan trọng?

**Envelope metadata** là tập hợp thông tin đi kèm dữ liệu đã mã hóa theo mô hình **envelope encryption**, giúp hệ thống xác định **định dạng, thuật toán, khóa bọc, khóa dữ liệu đã bọc, tham số AEAD và ngữ cảnh cần xác thực** để có thể giải mã đúng sau nhiều năm, qua rotation, backup, migration hoặc thay đổi ứng dụng.

Trong envelope encryption, hai khóa thường có vai trò khác nhau:

- **DEK (Data Encryption Key):** mã hóa trực tiếp plaintext thành ciphertext, thường bằng AES-GCM hoặc thuật toán AEAD phù hợp.
- **KEK (Key Encryption Key):** bọc/bảo vệ DEK; có thể nằm trong KMS/HSM với chính sách IAM và vòng đời riêng.
- **Encrypted/wrapped DEK:** bản DEK đã được bảo vệ bởi KEK, có thể lưu cạnh ciphertext mà không đồng nghĩa tiết lộ plaintext DEK.

Metadata là cầu nối để một reader biết **ciphertext nào được mã hóa dưới DEK nào, DEK đó được bọc bằng KEK nào, sử dụng thuật toán/phiên bản gì và cần AAD/context gì**.

Ví dụ: một hóa đơn được mã hóa năm 2025, KEK đổi năm 2026 và được khôi phục từ backup năm 2028. Nếu bản ghi chỉ chứa ciphertext mà không giữ encrypted DEK, nonce, tag, key reference và schema version đúng, ứng dụng có thể **không còn khả năng giải mã**, dù dữ liệu và KMS vẫn tồn tại.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài học này gắn trực tiếp metadata với vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, rotation, revocation đến destruction**, đồng thời kết nối mật mã đối xứng, chữ ký số, KMS/HSM, IAM, kiểm toán và khả năng khôi phục.

**Điểm trọng tâm:** metadata thường **không cần bí mật như DEK**, nhưng phải **đúng, đầy đủ, có định dạng ổn định và được bảo vệ tính toàn vẹn theo mô hình tin cậy**.

## 2. Nhắc lại luồng envelope encryption

~~~mermaid
flowchart LR
    P["Plaintext + trusted context"] --> E["AEAD Encrypt với DEK"]
    G["CSPRNG / KMS sinh DEK"] --> E
    G --> W["KMS/HSM: Wrap DEK dưới KEK"]
    E --> C["Ciphertext + nonce + tag"]
    W --> D["Encrypted DEK + KEK reference"]
    C --> M["Envelope record + metadata"]
    D --> M
    V["Format / algorithm / tenant / AAD version"] --> M
~~~

Biểu diễn khái niệm:

\[
(C,T)=\operatorname{AEAD.Enc}(DEK,N,P,A)
\]

\[
E_{DEK}=\operatorname{Wrap}_{KEK}(DEK,\operatorname{context})
\]

Ở đây:

- \(P\) là plaintext; \(C\) là ciphertext; \(T\) là authentication tag.
- \(N\) là nonce của AEAD; \(A\) là additional authenticated data.
- \(E_{DEK}\) là encrypted DEK; context là thông tin ràng buộc của cơ chế wrap/KMS nếu hỗ trợ.
- KEK có thể là một key do KMS/HSM quản lý, không export ra dạng rõ.

**Không giả định mọi KMS đều dùng API tên GenerateDataKey hoặc Wrap, và không đồng nhất encryption context của KMS với AAD của data AEAD.** Cách làm cụ thể phụ thuộc provider.

### 2.1. Envelope là một cấu trúc dữ liệu, không chỉ là ciphertext

Một envelope thường bao gồm phần đầu **header/metadata**, một hoặc nhiều phần **encrypted key material** và **payload ciphertext**. Không nên lưu chỉ ciphertext rồi kỳ vọng ứng dụng “nhớ” key version hoặc thuật toán theo ngày tạo.

### 2.2. Vì sao encrypted DEK được đặt cạnh ciphertext?

Bản encrypted DEK chỉ cho phép lấy DEK rõ khi có **KEK thích hợp cùng quyền unwrap và context hợp lệ**. Việc lưu encrypted DEK cùng object hỗ trợ sao lưu, chuyển dữ liệu và giảm phụ thuộc bảng ánh xạ riêng; tuy nhiên **không được để plaintext KEK, plaintext DEK hoặc quyền KMS toàn cục cùng ranh giới đọc storage**.

## 3. Các nhóm trường metadata

Một envelope record cần định danh rõ **format**, **key binding**, **cryptographic parameters**, **business context** và **lifecycle**.

| Nhóm | Trường minh họa | Mục đích |
|---|---|---|
| **Format** | envelopeVersion, encodingVersion, algorithmSuite | Chọn parser và bộ thuật toán được phép |
| **Payload cipher** | contentAlgorithm, nonce, tag, ciphertext | Giải mã và xác thực nội dung |
| **Data key** | encryptedDek, dekLength, dekId nếu có | Khôi phục DEK mà không lưu DEK rõ |
| **Wrapping** | wrapAlgorithm, kekRef, kekMaterialVersion, wrappingContextVersion | Tìm đúng KEK và ngữ cảnh unwrap |
| **Data binding** | tenantId, objectId, purpose, aadSchemaVersion | Ngăn tráo record, nhầm scope và nhầm purpose |
| **Lifecycle** | createdAt, dataKeyVersion, policyVersion, rotationGeneration | Phục vụ audit, migration, đọc dữ liệu lịch sử |
| **Integrity extension** | headerSignature hoặc MAC nếu thiết kế yêu cầu | Bảo vệ những header field ngoài data AEAD |
| **Operational** | recordId, migrationRevision, storageChecksum | Hỗ trợ vận hành và chống thao tác lặp |

**Không phải mọi hệ thống phải có toàn bộ trường trên.** Điều bắt buộc là tất cả thông tin cần để chọn đúng thuật toán/khóa và tái tạo byte AAD/context phải hiện diện hoặc có thể lấy **từ nguồn ổn định, tin cậy**.

### 3.1. Metadata công khai không có nghĩa vô hại

Tenant ID, key reference, region, thuật toán, độ dài ciphertext hoặc timestamp có thể làm lộ thông tin vận hành hoặc liên kết người dùng. Vì thế, metadata thường **không phải secret mật mã**, nhưng vẫn có thể là **dữ liệu nhạy cảm về riêng tư hoặc hạ tầng** cần hạn chế truy cập.

### 3.2. Không lưu secret trong metadata chỉ để tiện khôi phục

Không đưa vào header:

- Plaintext DEK/KEK hoặc recovery seed.
- Password hoặc HMAC/shared secret.
- Private signing key.
- Credential gọi KMS và bearer token.
- Bản rõ dữ liệu nghiệp vụ nhạy cảm.

**Key reference không phải secret key, nhưng password/credential đi cùng key reference vẫn là bí mật.**

## 4. Ví dụ envelope record tự mô tả

~~~json
{
  "envelopeVersion": 3,
  "suite": "AES-256-GCM+KMS-WRAPPED-DEK",
  "payload": {
    "nonce": "BASE64_12_BYTE_NONCE",
    "ciphertextAndTag": "BASE64_CIPHERTEXT_AND_16_BYTE_TAG"
  },
  "key": {
    "kekRef": "kms/prod/region-x/orders-kek",
    "kekMaterialVersion": "provider-specific-v4",
    "encryptedDek": "BASE64_WRAPPED_32_BYTE_DEK",
    "wrapContextVersion": 1
  },
  "binding": {
    "tenantId": "tenant-42",
    "objectId": "invoice-901",
    "purpose": "invoice-storage",
    "aadSchemaVersion": 2
  },
  "createdAt": "2026-11-28T03:00:00Z"
}
~~~

Tất cả giá trị Base64 ở đây là **placeholder**, không phải bản mã hoặc khóa thật; ví dụ không thể đem giải mã trực tiếp.

**Envelope version** là phiên bản của định dạng tổng thể; **key material version** là thông tin về vật liệu do provider quản lý; **AAD schema version** và **wrap context version** định nghĩa cách tái tạo ngữ cảnh xác thực. Chúng **không phải cùng một thứ**.

### 4.1. Lưu tag riêng hay gộp cùng ciphertext?

Nhiều thư viện Java trả về ciphertext kèm tag ở cuối sau AES-GCM doFinal; một số API khác dùng tag field riêng. Hai định dạng đều có thể hợp lý nếu **ghi rõ cách mã hóa, độ dài tag và cách đọc lại**.

Không cho một reader tự đoán tag nằm ở đâu, vì lỗi parsing có thể làm mất dữ liệu hoặc dẫn tới hành vi chấp nhận dữ liệu chưa được xác thực.

### 4.2. Không để field algorithm trở thành điểm hạ cấp bảo mật

Trường suite phải được so sánh với **allowlist của ứng dụng**, ví dụ chỉ phiên bản đã duyệt dùng AES-GCM và một cách bọc DEK tương thích. Metadata do storage cung cấp là dữ liệu **chưa tin cậy**; attacker không được biến nó thành lựa chọn AES-ECB, cipher không xác thực hoặc “none”.

## 5. Bốn kiểu phiên bản cần phân biệt

| Phiên bản | Nó mô tả điều gì? | Thay đổi khi nào? |
|---|---|---|
| **Envelope format version** | Layout/serialization của toàn bộ record | Khi đổi cấu trúc header, parser hoặc layout |
| **Payload algorithm suite version** | Thuật toán, kích thước key/nonce/tag và cơ chế AEAD | Khi thay bộ mã hóa hoặc các tham số |
| **KEK material reference/version** | Vật liệu và key reference dùng để unwrap DEK | Khi rewrap encrypted DEK sang KEK khác hoặc provider đổi version theo API |
| **AAD/wrapping context schema version** | Quy tắc xây dựng bytes AAD và context KMS | Khi đổi những trường hoặc cách canonical hóa |

Một bản ghi có thể có **envelopeVersion=3** nhưng được wrap bằng KEK v7, trong khi AAD schema vẫn v2. Không nên đồng nhất tất cả vào một trường version chung rồi dùng để đoán logic.

### 5.1. Khi KEK alias thay đổi

Một alias như orders-kek/current có thể được cập nhật sau rotation. Điều đó **không nhất thiết** khiến mọi encrypted DEK cũ có thể được unwrap bằng key mới. Cần lưu **key reference phù hợp với cơ chế của provider** và xác minh cách provider quản lý version/history.

Không tự suy diễn rằng một field keyMaterialVersion của provider nào cũng là chuỗi có thể đặt tùy ý; với một số KMS, encrypted key blob đã chứa thông tin định tuyến/version nội bộ.

### 5.2. Compatibility phải được định nghĩa trước

Reader cần biết:

- Những format versions nào được hỗ trợ.
- Khi nào reject unknown future version.
- Có giới hạn migration/retention cho old formats không.
- Cách xử lý data được mã hóa bằng algorithm đã bị loại khỏi policy.
- Những metadata nào cần lưu để reader tương lai không phải “đoán”.

**Fail-closed:** Không tìm thấy parser/algorithm hợp lệ thì **từ chối**, không tự quay lại thuật toán yếu.

## 6. Nonce/IV của data AEAD: ý nghĩa và cách lưu

Với **AES-GCM**, nonce (IV) dùng cùng DEK trong phép Encrypt; khi Decrypt phải có **đúng nonce đã dùng**. Nonce **không cần bí mật**, nhưng **tính duy nhất của cặp (DEK, nonce)** là yêu cầu thiết kế quan trọng.

### 6.1. Nonce 96 bit trong GCM

96-bit nonce thường được sử dụng vì phù hợp cấu trúc GCM và API phổ biến. Nhưng:

- **Không được tái sử dụng** nonce với cùng DEK.
- Random 96-bit nonce chỉ có bảo đảm xác suất không trùng trong một giới hạn sử dụng nhất định.
- Với nhiều writers, VM snapshots hoặc retry logic, cần thiết kế **nonce strategy** rõ ràng.
- Ghi lại nonce đi cùng ciphertext không vi phạm bí mật.
- Không lấy nonce từ password, objectId rồi nghĩ rằng đó là DEK mới.

### 6.2. Tag phải được xác minh

GCM tag bảo vệ tính toàn vẹn/xác thực của ciphertext cùng AAD. Khi tag sai, ứng dụng phải **từ chối plaintext**, không dùng dữ liệu chưa được xác thực.

Với Java JCA, AES/GCM/NoPadding thường nhận GCMParameterSpec với tag length, và doFinal trong quá trình Decrypt sẽ báo lỗi xác thực nếu tag không hợp lệ.

### 6.3. Một DEK dùng cho bao nhiêu bản ghi?

Nếu mỗi object có DEK độc lập, quản lý nonce đơn giản hơn nhưng tăng số encrypted DEKs. Nếu một DEK dùng cho nhiều object/chunk, cần quản lý nonce uniqueness, usage limits và key version qua tất cả writers.

**Không chỉ dựa vào việc “thấy nonce khác nhau trong một mẫu nhỏ” để chứng minh an toàn ở toàn bộ hệ thống.**

## 7. AAD: ràng buộc metadata với ciphertext

**AAD (Additional Authenticated Data)** là dữ liệu được kiểm tra tính toàn vẹn trong AEAD, nhưng **không được mã hóa**. Nó thường dùng để ràng buộc ciphertext với ngữ cảnh nghiệp vụ.

Ví dụ AAD logic:

~~~text
protocol = invoice-envelope
aadSchemaVersion = 2
tenantId = tenant-42
objectId = invoice-901
purpose = invoice-storage
dataFormatVersion = 3
~~~

Nếu Encrypt và Decrypt sử dụng **cùng bytes AAD**, thay đổi metadata được ràng buộc sẽ dẫn đến thất bại xác thực khi kiểm tra tag.

### 7.1. Không thể chỉ nối chuỗi tùy tiện

Các chuỗi như:

~~~text
a|bc
ab|c
~~~

có thể gây nhập nhằng nếu cách ghép không có cấu trúc và delimiter có thể xuất hiện trong giá trị. Với JSON, thứ tự thuộc tính, khoảng trắng, Unicode normalization và number encoding có thể khác giữa các runtime.

**Nên định nghĩa encoding byte-level ổn định**: ví dụ length-prefix theo UTF-8, thứ tự trường cố định, version rõ, giới hạn độ dài và quy tắc Unicode nếu hệ thống cần.

### 7.2. AAD phải dựa vào nguồn scope đáng tin

Nếu attacker có quyền sửa cả tenantId trong database và gửi tenantId tùy ý trong request, AAD khớp với bản ghi tự khai **không tự chứng minh** user được quyền đọc tenant đó.

Luồng an toàn:

1. Xác thực principal và lấy tenant/scope từ nguồn tin cậy.
2. Xác minh ownership/authorization đối với object cần đọc.
3. Dùng expected tenant/object/purpose tạo AAD.
4. Gọi KMS Unwrap trong key scope được phép.
5. AEAD Decrypt/Verify; chỉ trả plaintext nếu mọi bước thành công.

**AAD bảo vệ tính toàn vẹn ngữ cảnh khi có DEK phù hợp, không thay thế business authorization.**

### 7.3. Header field nào cần ràng buộc?

Thường xem xét **tenantId, objectId, purpose, data format version, suite identifier, classification** và bất kỳ thuộc tính ảnh hưởng cách sử dụng plaintext. Những field không ràng buộc phải có lý do rõ.

Cần cẩn trọng với **metadata thay đổi độc lập**: nếu AAD chứa một keyRef hoặc ciphertext của encrypted DEK, thao tác **rewrap DEK** làm đổi header và có thể khiến tag của payload không còn hợp lệ. Vì vậy nên phân biệt **AAD ổn định của payload** và **wrapping metadata có thể thay khi rotation**, bảo vệ từng phần bằng cơ chế thích hợp.

## 8. KMS encryption context khác payload AAD

Một số KMS cho phép cung cấp **encryption context** khi bọc/giải bọc DEK. Nó có thể là AAD của **phép mã hóa DEK tại KMS**, khác AAD của **AES-GCM mã hóa dữ liệu**.

~~~mermaid
flowchart TB
    M["Trusted tenant/object/purpose"] --> C["Canonical data AAD"]
    M --> K["KMS encryption context"]
    D["Data plaintext"] --> E["AES-GCM Encrypt với DEK"]
    C --> E
    E --> P["Payload ciphertext + tag + nonce"]
    R["DEK"] --> E
    R --> W["KMS Wrap dưới KEK"]
    K --> W
    W --> B["Encrypted DEK"]
    P --> S["Envelope record"]
    B --> S
~~~

### 8.1. Không tự suy rằng hai context được liên kết

Ứng dụng phải chủ động định nghĩa **cùng identity, object scope hoặc binding đã kiểm chứng** ở cả hai miền. Một số KMS dùng context để ràng buộc ciphertext blob, số khác có API và semantics khác nhau.

**Đừng đặt password, token, PII nhạy cảm vào context** chỉ vì nó là tham số KMS: một số provider đưa context vào audit log và không coi nó là secret.

### 8.2. Ví dụ context

~~~json
{
  "purpose": "invoice-storage",
  "tenant": "tenant-42",
  "object": "invoice-901",
  "contextVersion": "1"
}
~~~

Đây là **ví dụ**. Với context này, thay object khác khi Unwrap cần dẫn tới thất bại nếu provider ràng buộc context như thiết kế. Ứng dụng còn phải kiểm tra business authorization trước khi gọi Unwrap.

### 8.3. Context độc lập giúp kiểm tra tại hai lớp

- **KMS wrap context:** ràng buộc wrapped DEK với một ngữ cảnh.
- **Payload AAD:** ràng buộc ciphertext với ngữ cảnh khi có DEK.
- **Authorization:** xác định requester có quyền với ngữ cảnh đó.
- **Audit:** xác nhận principal/key/operation được dùng theo policy.

Không có lớp nào thay hoàn toàn các lớp còn lại.

## 9. Metadata và threat model của thao tác tráo đổi

Metadata không phải tất cả đều được xác thực theo cùng một cách. Xác định những kịch bản tampering có thể xảy ra.

| Thao tác của attacker | Nếu không có binding phù hợp | Biện pháp |
|---|---|---|
| Đổi tenantId/objectId | Có thể khiến ứng dụng chọn scope sai | Business authz + payload AAD |
| Đổi suite sang cipher yếu | Downgrade thuật toán | Algorithm allowlist + version policy |
| Thay keyRef | KMS chọn KEK ngoài scope hoặc lỗi unwrap | Key reference allowlist + IAM/context |
| Tháo hoặc đổi encrypted DEK | Giải mã sai hoặc key substitution | Authenticated wrap/context, payload tag và key scope |
| Copy trọn record hợp lệ sang object khác | Replay/cross-object substitution | **Expected object identity** từ nguồn tin cậy được ràng buộc vào AAD |
| Đổi createdAt/lifecycle state | Ra quyết định sai nếu metadata thiếu xác thực | Metadata integrity, registry và kiểm toán |
| Đổi nonce/tag | Decrypt lỗi, hoặc phá bảo mật khi writer dùng nonce sai | AEAD verification + nonce strategy |
| Truncate/reorder chunks | Mất hoặc tráo phần ciphertext | Chunk index, total count, stream context được xác thực |

### 9.1. Swapping toàn bộ envelope

Nếu attacker copy **toàn bộ envelope hợp lệ** từ object A sang object B, cả ciphertext và tag có thể vẫn hợp lệ dưới DEK đi kèm. Để ngăn việc áp data A cho B, hệ thống phải **ràng buộc expected object identity** lấy từ storage path/record ownership hoặc nguồn tin cậy độc lập, rồi đưa identity đó vào AAD hoặc guard thích hợp.

Chỉ xây AAD từ **metadata bên trong envelope do attacker cũng có thể copy** thì chưa nhất thiết phát hiện việc đổi chỗ trọn gói.

### 9.2. Field mutable và immutable

**Immutable payload binding:** tenant/object/purpose/format/suite theo phiên bản dữ liệu.

**Mutable wrapping metadata:** KEK reference, encrypted DEK và wrapping context liên quan có thể được thay trong rewrap mà **không đổi plaintext DEK hay ciphertext**.

Khi thiết kế, phải đảm bảo mutable metadata **được KMS/key-wrap/context và workflow bảo vệ**, chứ không chỉ loại nó khỏi payload AAD rồi cho chỉnh tùy ý.

## 10. Phân biệt authentication với authorization

**Authentication của AEAD** cho biết plaintext và AAD không bị thay đổi trái quy tắc dưới khóa được chọn, theo tính chất của thuật toán. **Authorization** cho biết một người hoặc service **có được phép** truy cập data/key hay không.

Ví dụ một service có KMS Decrypt trên KEK dùng chung, nhưng được phép truy cập chỉ tenant A. Việc service nhận một encrypted DEK của tenant B rồi giải mã thành công **không chứng minh** yêu cầu thuộc quyền tenant A.

Kiểm soát cần có:

- Xác thực end-user và workload identity.
- Kiểm tra object ownership với nguồn đáng tin.
- Chỉ cho keyRef thuộc phạm vi tenant/service được phê duyệt.
- Định nghĩa KMS grants và encryption context nếu provider hỗ trợ.
- Ràng buộc metadata payload với AAD.
- Audit truy cập dữ liệu cùng KMS operations bằng correlation ID.

**Không dùng keyRef, kid hoặc filename như một authorization token.**

## 11. Parser: xem envelope metadata là dữ liệu chưa đáng tin

Reader có thể nhận record từ database, object store, backup, message queue, đối tác hoặc người dùng. Dù lưu trong “hệ thống nội bộ”, metadata vẫn cần **kiểm tra đầu vào**.

Những guard hữu ích:

1. Chỉ cho **envelopeVersion** đã biết; reject phiên bản lạ hoặc đã bị cấm.
2. Chỉ cho **algorithmSuite** và tag length trong allowlist.
3. Giới hạn độ dài của **keyRef, tenantId, objectId, encryptedDek, nonce, ciphertext** trước khi cấp phát buffer.
4. Xác minh **nonce length** theo suite; với mẫu AES-GCM 96-bit nonce là 12 byte.
5. Xác minh ciphertextAndTag tối thiểu đủ tag (ví dụ 16 byte nếu tag 128 bit).
6. Từ chối missing fields, duplicate JSON keys mơ hồ, invalid base64 và metadata không hợp lệ.
7. Kiểm soát **canonical encoding**, Unicode, version và tính nhất quán của fields.
8. Kiểm tra **keyRef/tenant/purpose** với scope tin cậy trước KMS call.
9. Chống DoS: giới hạn JSON depth, kích thước, số encrypted recipients, KDF cost parameters nếu có.
10. Không hiển thị exception nội bộ chứa key material hoặc dữ liệu nhạy cảm.

Không fallback sang **plaintext mode, AES-ECB hoặc skip-tag** chỉ vì không parse được metadata phiên bản mới.

## 12. Java 17: mô hình metadata rõ ràng với KMS abstraction

Ví dụ dùng **Java JCA** mã hóa AES-GCM và một interface KMS để minh họa ranh giới giữa payload metadata với wrapping metadata. Trong demo:

- Payload metadata cố định ở **format v3, suite AES-256-GCM-v3**.
- AAD dùng **encoding length-prefixed** ràng buộc tenant, object, purpose và format.
- KMS context được xây dựng từ cùng **trusted Scope**, nhưng là tham số của **phép bọc DEK**, không phải của AES-GCM payload.
- KEK không được xuất dưới dạng rõ; storage giữ wrapped DEK.
- Reader nhận **expected Scope và expected KEK reference từ tầng đã xác thực/phân quyền**, không tin client tùy ý gửi giá trị.
- KeyService là abstraction; chưa có implementation cloud KMS cụ thể. **Không tạo KEK hard-code** để giả lập khả năng bảo vệ của KMS.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import java.util.Objects;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class EnvelopeMetadataExample {
    private static final int VERSION = 3;
    private static final String SUITE = "AES-256-GCM-v3";
    private static final int NONCE_LEN = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RNG = new SecureRandom();

    // Scope được lấy sau xác thực và kiểm tra nghiệp vụ.
    public record Scope(
        String tenantId,
        String objectId,
        String purpose
    ) {}

    // Các giá trị trả về do KMS tạo: DEK rõ chỉ dùng tạm.
    public record DataKey(
        byte[] plaintextDek,
        byte[] wrappedDek
    ) {}

    public interface KeyService {
        DataKey generateDataKey(
            String authorizedKekRef,
            Map<String, String> context
        ) throws Exception;

        byte[] unwrap(
            String authorizedKekRef,
            byte[] wrappedDek,
            Map<String, String> context
        ) throws Exception;
    }

    // Những trường được phép lưu trong data store.
    // byte[] trong record là mutable: production cần
    // clone/immutable storage, parser và schema validation.
    public record Envelope(
        int version,
        String suite,
        String kekRef,
        String tenantId,
        String objectId,
        String purpose,
        byte[] wrappedDek,
        byte[] nonce,
        byte[] ciphertextAndTag
    ) {}

    private static void requireScope(Scope s) {
        Objects.requireNonNull(s);
        requireText(s.tenantId());
        requireText(s.objectId());
        requireText(s.purpose());
    }

    private static void requireText(String s) {
        if (s == null || s.isBlank()
                || s.getBytes(StandardCharsets.UTF_8).length > 255) {
            throw new IllegalArgumentException(
                "Invalid scope component");
        }
    }

    private static Map<String, String> wrapContext(Scope s) {
        return Map.of(
            "contextVersion", "1",
            "tenant", s.tenantId(),
            "object", s.objectId(),
            "purpose", s.purpose()
        );
    }

    // Không dựa vào thứ tự map/JSON hay cách nối tùy tiện.
    private static byte[] payloadAad(Scope s) throws Exception {
        requireScope(s);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(VERSION);
            writeField(out, SUITE);
            writeField(out, s.tenantId());
            writeField(out, s.objectId());
            writeField(out, s.purpose());
        }
        return buffer.toByteArray();
    }

    private static void writeField(
            DataOutputStream out, String value) throws Exception {
        byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);
        if (utf8.length == 0 || utf8.length > 255) {
            throw new IllegalArgumentException("Invalid AAD field");
        }
        out.writeShort(utf8.length);
        out.write(utf8);
    }

    public static Envelope encrypt(
            KeyService kms, String authorizedKekRef,
            Scope scope, byte[] plaintext) throws Exception {
        Objects.requireNonNull(kms);
        Objects.requireNonNull(plaintext);
        requireText(authorizedKekRef);
        requireScope(scope);

        DataKey generated = kms.generateDataKey(
            authorizedKekRef, wrapContext(scope));

        if (generated == null
                || generated.plaintextDek() == null
                || generated.plaintextDek().length != 32
                || generated.wrappedDek() == null
                || generated.wrappedDek().length == 0) {
            throw new IllegalStateException("Invalid KMS response");
        }

        byte[] plaintextDek = generated.plaintextDek();
        try {
            byte[] nonce = new byte[NONCE_LEN];
            RNG.nextBytes(nonce);

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                Cipher.ENCRYPT_MODE,
                new SecretKeySpec(plaintextDek, "AES"),
                new GCMParameterSpec(TAG_BITS, nonce)
            );
            cipher.updateAAD(payloadAad(scope));
            byte[] ciphertextAndTag = cipher.doFinal(plaintext);

            return new Envelope(
                VERSION, SUITE, authorizedKekRef,
                scope.tenantId(), scope.objectId(), scope.purpose(),
                generated.wrappedDek().clone(),
                nonce, ciphertextAndTag
            );
        } finally {
            // Chỉ xóa best-effort mảng code nắm quyền sở hữu.
            Arrays.fill(plaintextDek, (byte) 0);
        }
    }

    public static byte[] decrypt(
            KeyService kms,
            String expectedKekRef,
            Scope trustedScope,
            Envelope record) throws Exception {
        Objects.requireNonNull(kms);
        Objects.requireNonNull(record);
        requireScope(trustedScope);
        requireText(expectedKekRef);

        // expectedKekRef phải đến từ policy/registry đáng tin,
        // không chỉ copy từ record hoặc request client.
        if (record.version() != VERSION
                || !SUITE.equals(record.suite())
                || !expectedKekRef.equals(record.kekRef())
                || !trustedScope.tenantId().equals(record.tenantId())
                || !trustedScope.objectId().equals(record.objectId())
                || !trustedScope.purpose().equals(record.purpose())
                || record.nonce() == null
                || record.nonce().length != NONCE_LEN
                || record.ciphertextAndTag() == null
                || record.ciphertextAndTag().length < 16
                || record.wrappedDek() == null
                || record.wrappedDek().length == 0) {
            throw new SecurityException(
                "Envelope scope or format mismatch");
        }

        byte[] plaintextDek = kms.unwrap(
            expectedKekRef, record.wrappedDek().clone(),
            wrapContext(trustedScope)
        );

        if (plaintextDek == null || plaintextDek.length != 32) {
            throw new SecurityException("Invalid data key");
        }
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                Cipher.DECRYPT_MODE,
                new SecretKeySpec(plaintextDek, "AES"),
                new GCMParameterSpec(TAG_BITS, record.nonce())
            );
            cipher.updateAAD(payloadAad(trustedScope));
            // doFinal sẽ thất bại nếu GCM tag không hợp lệ.
            return cipher.doFinal(record.ciphertextAndTag());
        } finally {
            Arrays.fill(plaintextDek, (byte) 0);
        }
    }
}
~~~

### 12.1. Phần nào là metadata của payload?

**version, suite, tenantId, objectId và purpose** được đưa vào AAD. **nonce và ciphertextAndTag** là tham số/ciphertext của AEAD. Reader dùng **Scope độc lập** đã được cấp quyền để tái tạo AAD, nhờ đó việc tráo record sang tenant/object khác không tự trở nên hợp lệ chỉ vì envelope có metadata tự khai.

### 12.2. Phần nào là metadata của wrapping?

**kekRef, wrappedDek và wrapContext** phục vụ KMS. Chúng **không được đưa vào payload AAD trong mẫu này**, để có thể rewrap DEK sang KEK mới mà không buộc phải mã hóa lại payload, miễn rằng dữ liệu/DEK chưa bị lộ và quy trình cập nhật được bảo vệ.

Điều đó **không cho phép sửa wrapping fields tùy ý**: application phải kiểm tra KEK nằm trong scope được phép, KMS xác thực context, và migration áp dụng transaction/version/approval.

### 12.3. Giới hạn cần nhận diện

Đây là ví dụ **logic dữ liệu**, chưa phải component production:

- **KeyService chưa được triển khai**. Không thể chứng minh KMS provider behavior chỉ từ interface.
- **Record chứa byte arrays mutable**; production cần defensive copy, immutable representation hoặc serialization boundaries.
- **Chưa có parser JSON/CBOR, storage, KMS SDK, key version mapping hay main method**.
- **Chưa thực thi end-user authz**; trustedScope và expectedKekRef chỉ có ý nghĩa khi được tầng tin cậy cấp.
- **Chưa đặt giới hạn ciphertext/wrapped key length hoặc response sizes toàn diện**.
- **Arrays.fill không bảo đảm zeroize mọi bản sao trong JCE/JVM**.
- **Nonce 96 bit sinh ngẫu nhiên** cần đánh giá quy mô/usage limits; không bảo đảm uniqueness vô hạn.
- **Chưa có retry/idempotency** của KMS, persistence, transaction và cache invalidation.
- **Không lưu vật liệu plaintext key/credentials trong audit hoặc exception**.

Cách dùng đúng là tham khảo để thiết kế interface an toàn, sau đó tích hợp với nhà cung cấp KMS/HSM có chính sách IAM và kiểm thử negative permissions.

## 13. Serialization: chọn định dạng và chuẩn hóa byte chính xác

Envelope có thể được lưu ở JSON, CBOR, Protocol Buffers, Avro hoặc một binary format riêng được thiết kế chặt chẽ. Không có định dạng nào tự bảo đảm bảo mật nếu parser mơ hồ.

| Format | Lợi ích | Điểm cần kiểm soát |
|---|---|---|
| **JSON + Base64** | Dễ xem/log/debug schema | Duplicate keys, number coercion, Unicode, schema, base64 validation |
| **CBOR** | Binary gọn, typed values | Canonical CBOR nếu cần ký/header MAC, parser limits |
| **Protocol Buffers** | Schema typed, backward compatibility | Unknown fields, field presence, canonical bytes nếu dùng làm AAD |
| **Binary TLV/length-prefix** | Byte-level rõ ràng, dễ define AAD | Overflow, length bounds, endianness, versioning |
| **Multipart envelope** | Payload lớn có thể streaming/chunk | Chunk count, ordering, per-chunk AEAD tag và manifest integrity |

### 13.1. Đừng MAC hoặc ký “JSON tùy ý”

Nếu một phần metadata phải có chữ ký/MAC độc lập, bên ký và bên kiểm tra phải xử lý **cùng bytes**. JSON object thường có thể được serialize khác thứ tự, whitespace hoặc Unicode.

Có hai lựa chọn khái niệm:

1. **Chuẩn hóa (canonicalize)** một định dạng với quy tắc được xác định rõ, kiểm thử liên ngôn ngữ.
2. **Ký/MAC một cấu trúc binary đã định nghĩa byte-level** và version của nó.

Không tạo AAD bằng chuỗi nối “tenant + object + version” mà không có delimiter/length-prefix chống nhập nhằng.

### 13.2. Phân biệt integrity của transport, storage và crypto payload

- **TLS** bảo vệ kênh truyền trong phạm vi giao thức, không chứng minh record đã nằm nguyên vẹn lâu dài.
- **Object storage checksums** giúp phát hiện corruption hoặc tải không đủ; không thay authentication tag trước attacker có thể sửa checksum.
- **AEAD tag** kiểm tra payload và AAD dưới DEK, theo thuật toán.
- **Wrap authentication/context** bảo vệ DEK đã bọc theo cơ chế KMS.
- **Header signature/MAC** có thể cần nếu metadata không nằm trong payload AAD hoặc wrap context và vẫn phải được bảo vệ.

Không coi một checksum như CRC32/SHA-256 thông thường là **authentication** nếu attacker có thể sửa cả dữ liệu và checksum.

## 14. Một envelope có nhiều người nhận/KEK

Một số thiết kế dùng **một DEK để mã hóa payload**, nhưng bọc DEK nhiều lần cho các người nhận hoặc miền key khác nhau. Khi đó metadata có thể chứa:

~~~json
{
  "envelopeVersion": 3,
  "suite": "AES-256-GCM",
  "payload": {
    "nonce": "BASE64_NONCE",
    "ciphertextAndTag": "BASE64_CIPHERTEXT_TAG"
  },
  "recipients": [
    {
      "recipientId": "team-analytics",
      "kekRef": "kms/.../analytics-kek",
      "encryptedDek": "BASE64_WRAPPED_DEK_1"
    },
    {
      "recipientId": "team-accounting",
      "kekRef": "kms/.../accounting-kek",
      "encryptedDek": "BASE64_WRAPPED_DEK_2"
    }
  ]
}
~~~

**Rủi ro mới:** mỗi người nhận có khả năng unwrap DEK sẽ có thể giải mã toàn bộ payload theo scope đó. Thêm một recipient là **mở rộng quyền**, không chỉ thay đổi metadata vô hại.

### 14.1. Quy tắc thiết kế

- Giới hạn số recipients và kích thước header để tránh DoS.
- Không chọn recipient chỉ vì client gửi recipientId tùy ý.
- Ràng buộc authorization của từng recipient với key policy/owner và mục đích.
- Xác định rõ cách revoke recipient: chỉ xóa một encryptedDek entry **không làm mất plaintext DEK** đã từng được người nhận giữ.
- Nếu cần hạn chế một bên không được decrypt dữ liệu mới, cần DEK/recipient-set mới theo thiết kế.
- Đánh giá cách bảo vệ **integrity của recipient list**: thay đổi có thể là thao tác grant/revoke cần audit và approval.

### 14.2. Rotation nhiều KEK

Một số recipient có thể được rewrap độc lập, nhưng phải quản lý **transaction/revision** và tránh race giữa add/remove recipient và rotation. Nếu DEK hoặc một KEK bị lộ, rủi ro là của **payload chung**, không chỉ của một header entry.

## 15. Envelope metadata cho dữ liệu lớn và chunked encryption

Với payload lớn, đọc/mã hóa toàn bộ vào RAM có thể không phù hợp. Thiết kế có thể mã hóa thành nhiều chunk AEAD, mỗi chunk có nonce/tag, cùng một hoặc nhiều DEK theo key schedule.

~~~mermaid
flowchart TD
    H["Envelope header: suite, keyRef, wrapped DEK"] --> M["Authenticated manifest"]
    M --> C0["Chunk 0: nonce0 + ciphertext0 + tag0"]
    M --> C1["Chunk 1: nonce1 + ciphertext1 + tag1"]
    M --> C2["Chunk N: nonceN + ciphertextN + tagN"]
    A["Trusted object ID + expected total chunks"] --> M
~~~

### 15.1. Metadata cần mở rộng

- **Chunk index/sequence number**, tổng số chunk hoặc marker kết thúc được xác thực.
- **Nonce derivation strategy** và key ID/version cho từng chunk nếu có thay đổi.
- **Total length** và bản sắc object cần được ràng buộc.
- **Manifest integrity** ngăn xóa, tráo thứ tự, duplicate hoặc truncate chunk.
- **Format version** cho phép reader phân biệt một AEAD tag toàn payload với tag từng chunk.

**Không tự chia ciphertext của một AES-GCM operation thành các phần rồi coi mỗi phần độc lập đã được xác thực**. Nếu dùng per-chunk encryption, phải có protocol xác thực thứ tự và tính đầy đủ riêng.

### 15.2. Tránh reuse nonce khi retry/multiwriter

Nếu mỗi chunk dùng cùng DEK, nonce strategy phải đảm bảo duy nhất khi có multiwriter, restart, retry và rollback. Không tái sử dụng cùng (key, nonce) cho plaintext khác chỉ vì chunk index được đặt lại từ 0 sau khi reconnect.

### 15.3. Không trả plaintext chunk trước khi biết cấu trúc tổng thể hợp lệ

Ngay cả khi từng chunk có AEAD tag đúng, một stream bị truncate có thể có các chunk đầu hợp lệ nhưng thiếu phần cuối. Ứng dụng phải có cách phát hiện **truncation/reorder/replay**, và tránh xử lý nghiệp vụ không thể hoàn nguyên trước khi tính toàn vẹn tổng thể được kiểm tra theo protocol.

## 16. Metadata trong database và object storage

Một schema quan hệ minh họa:

~~~sql
CREATE TABLE protected_objects (
    object_id             VARCHAR(128) PRIMARY KEY,
    tenant_id             VARCHAR(128) NOT NULL,
    envelope_version      INTEGER NOT NULL,
    suite_id              VARCHAR(64) NOT NULL,
    kek_ref               VARCHAR(512) NOT NULL,
    encrypted_dek         BYTEA NOT NULL,
    gcm_nonce             BYTEA NOT NULL,
    ciphertext_and_tag    BYTEA NOT NULL,
    aad_schema_version    INTEGER NOT NULL,
    record_revision       BIGINT NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL
);
~~~

Đây là cú pháp gần **PostgreSQL** và chỉ là mẫu. Một triển khai thật cần các trường/key version/context phù hợp provider, index, access control, retention, validation, schema migration và giới hạn kích thước.

### 16.1. Lưu cạnh ciphertext hay tách thành manifest?

Hai cách đều có thể hợp lý:

- **In-band envelope:** header + encrypted DEK + ciphertext trong một blob; dễ backup atomically và di chuyển.
- **Out-of-band metadata:** metadata ở DB/registry, payload ở object storage; thuận tiện indexing nhưng phải giữ **tính nhất quán của các tham chiếu**.

Nếu metadata nằm riêng:

1. Dùng object ID/etag/version để khóa đúng bản payload.
2. Khi đổi wrapping entry, dùng revision/CAS ngăn stale writer.
3. Backup phải bao gồm cả payload và metadata tương ứng.
4. Không lưu “encrypted DEK mới” nhưng để metadata keyRef cũ.
5. Kiểm tra các nơi replicates nhận đủ update.

### 16.2. Metadata là một phần của backup

Backup chỉ ciphertext nhưng mất nonce, tag, encrypted DEK hoặc keyRef đúng sẽ có thể **không giải mã được**. Cần kiểm thử restore cả envelope, schema, KEK availability và IAM recovery path.

## 17. Rotation KEK: metadata nào thay, metadata nào giữ?

Khi rotate **KEK** trong tình huống bình thường và **DEK chưa bị lộ**, có thể **rewrap cùng DEK** dưới KEK mới. Khi đó thường:

| Thành phần | Thay đổi? | Vì sao? |
|---|---|---|
| **Plaintext data / ciphertext** | Không nhất thiết | Vẫn dùng DEK cũ để đọc payload |
| **Payload nonce/tag** | Không | Payload AEAD không bị làm lại |
| **Payload AAD schema** | Thường không | Ràng buộc object/purpose không đổi |
| **Wrapped DEK** | **Có** | DEK được bọc bằng KEK khác/vật liệu khác |
| **KEK ref/material version** | **Có** | Reader cần trỏ tới đường Unwrap mới |
| **Wrap context/version** | Có thể | Nếu cơ chế wrap/context thay đổi theo policy |
| **Envelope record revision** | **Có** | Cho phép xử lý transaction và stale updates |
| **Audit/rotation event** | **Có** | Truy vết ai/bao giờ/under which approval |

~~~mermaid
sequenceDiagram
    participant M as Rotation worker
    participant K as KMS/HSM
    participant D as Envelope store
    M->>D: Đọc envelope revision 12
    M->>K: Rewrap encrypted DEK v1 -> KEK v2
    K-->>M: New wrapped DEK + key reference
    M->>D: CAS update wrapped DEK, kekRef, revision 13
    D-->>M: Success hoặc conflict
    M->>D: Readback version/context
    Note over M,D: Không đổi ciphertext/tag nếu DEK giữ nguyên
~~~

### 17.1. Không đặt mutable wrapping fields vào payload AAD một cách thiếu kế hoạch

Nếu payload tag được tính với AAD bao gồm **encrypted DEK bytes hoặc KEK ref v1**, thay wrapping fields khi rewrap sẽ khiến reader dùng AAD mới và **tag cũ không còn khớp**.

Các phương án thiết kế:

- **Giữ AAD payload ổn định** ở tenant/object/purpose/suite/format, bảo vệ wrapped DEK qua KMS context và kiểm soát update metadata.
- Hoặc nếu AAD buộc phải bao gồm wrapping fields, phải **tính lại tag bằng một operation mã hóa hợp lệ** và kiểm chứng nhất quán, không sửa metadata độc lập.

Thao tác cập nhật tag mới mà không tái tạo đúng AEAD authentication theo provider không phải “vá tag” đơn giản.

### 17.2. Nếu KEK hoặc DEK bị compromise

**Rewrap không tự khắc phục lộ DEK plaintext.** Nếu DEK đã bị lộ, phải đánh giá **generate DEK mới và re-encrypt payload**. Nếu KEK đã lộ, đối thủ có thể đã thu thập wrapped DEK cũ và giải bọc offline; cần đánh giá dữ liệu/DEK trong blast radius thay vì chỉ đổi metadata.

## 18. Rotation DEK hoặc algorithm suite: tác động metadata

Thay **DEK** thường kéo theo:

1. Generate DEK mới bằng CSPRNG/KMS/HSM.
2. Decrypt payload cũ hợp lệ (với quyền và xác thực tag).
3. Re-encrypt dưới DEK mới, nonce và tag mới.
4. Wrap DEK mới bằng KEK được phép.
5. Cập nhật encrypted DEK, nonce, ciphertext/tag, key references, format/revision theo nhu cầu.
6. Commit atomically hoặc qua workflow có checkpoint/CAS.
7. Kiểm thử decrypt/restore và đảm bảo không dùng DEK cũ cho dữ liệu mới.

### 18.1. Algorithm migration không phải chỉ đổi tên field

Không thể chỉ đổi suite từ AES-GCM sang một thuật toán khác mà giữ ciphertext/tag cũ. Phải **giải mã hợp lệ rồi mã hóa lại theo protocol mới**, trong khi xử lý dữ liệu lịch sử theo policy versioning.

### 18.2. AAD schema migration

Nếu AAD schema đổi từ v2 sang v3, reader cũ vẫn cần tái tạo AAD v2 cho ciphertext cũ. Nếu muốn ràng buộc thêm trường vào AAD của dữ liệu cũ, cần **tạo lại authentication tag** bằng một encryption/authentication operation phù hợp, thường gắn với migration/re-encrypt.

**Không cho decrypter tự bỏ AAD khi gặp lỗi**: điều đó làm yếu hoặc phá kiểm tra tính toàn vẹn ngữ cảnh.

## 19. Tính nhất quán của metadata khi cập nhật phân tán

Envelope có thể được đọc/ghi bởi nhiều services, jobs hoặc regions. Một request stale có thể làm mất key reference hoặc ghi đè encrypted DEK mới.

### 19.1. Lỗi kinh điển

1. Job A đọc encrypted DEK được bọc bởi KEK v1 ở revision 7.
2. Job B đã rewrap và cập nhật KEK v2, revision 8.
3. Job A cập nhật một metadata field khác bằng bản record cũ và vô tình ghi lại encrypted DEK v1.
4. Registry nói v2, nhưng object lại trỏ về v1 hoặc mất mapping.

Nếu sau đó v1 bị hủy, dữ liệu có thể không thể unwrap.

### 19.2. Compare-and-swap

~~~sql
-- Cú pháp minh họa, tùy database/transaction.
UPDATE protected_objects
SET encrypted_dek = :new_wrapped_dek,
    kek_ref = :new_kek_ref,
    record_revision = record_revision + 1
WHERE object_id = :object_id
  AND tenant_id = :tenant_id
  AND record_revision = :expected_revision;
~~~

Nếu số dòng update bằng 0, phải **đọc lại record, kiểm tra trạng thái và tái đánh giá**, không bỏ điều kiện revision để cố ghi đè.

### 19.3. Không có ACID transaction chung giữa database và KMS

KMS Rewrap và DB UPDATE thường không nằm trong một transaction phân tán ACID. Dùng:

- **Operation ID/idempotency key** và trạng thái PREPARING/APPLYING/VERIFYING.
- **KMS rewrap** dưới quyền đã phê duyệt.
- **CAS update** header có revision.
- **Readback** encryptedDEK/keyRef/ability to decrypt theo policy.
- **Reconciler** cho lệnh timeout/failure, không tự destroy v1.
- **Audit events** có old/new key references, actor, outcome nhưng không chứa DEK rõ.

### 19.4. Chú ý multi-region replication

Dữ liệu có thể đã replicated sang region B trong khi KEK mới chưa khả dụng hoặc quyền DR chưa đủ. Không xem một metadata update “thành công ở region A” là kết luận mọi backup/replica có thể decrypt.

## 20. Backup và disaster recovery: metadata cũng phải được khôi phục

Dù ciphertext và encrypted DEK được sao lưu đầy đủ, dữ liệu vẫn có thể không đọc lại được nếu mất **nonce, tag, keyRef/version, AAD schema hoặc KMS encryption context**.

| Thành phần | Nếu thiếu | Biện pháp |
|---|---|---|
| Ciphertext | Mất dữ liệu đã mã hóa | Storage backup và integrity check |
| Nonce/tag | Không thể AES-GCM Decrypt/Verify | Lưu cùng bản ghi, định nghĩa tag layout |
| Encrypted DEK | Không thể khôi phục data key | Backup atomically với payload/manifest |
| KEK reference/version | Chọn sai hoặc không tìm thấy key | Version-aware registry và provider metadata |
| KEK availability | Encrypted DEK còn nhưng không unwrap được | Key recovery/DR theo chính sách |
| AAD/context schema | Không tái tạo được bytes kiểm tra | Versioned encoding và test fixtures |
| Trusted object/tenant identity | Không chứng minh đúng data scope | Lưu ownership trong nguồn đáng tin |
| IAM recovery permissions | Recovery principal bị từ chối | DR roles/JIT approval và audit |

### 20.1. Không backup KEK dạng rõ cạnh ciphertext

Nếu plaintext KEK được lưu cùng database snapshot trong một bucket có cùng quyền đọc, boundary giữa key và dữ liệu gần như không còn giá trị khi bucket bị lộ.

**Encrypted DEK cạnh ciphertext là bình thường; plaintext KEK nên nằm trong KMS/HSM hoặc miền phục hồi được bảo vệ riêng.**

### 20.2. Restore test phải giải mã thật

Một diễn tập khôi phục có ý nghĩa cần:

1. Restore envelope và metadata đúng phiên bản.
2. Xác minh keyRef, material version và trusted scope.
3. Dùng recovery role được phê duyệt gọi KMS với context tương ứng.
4. Giải bọc DEK, tái tạo đúng AAD, Decrypt và Verify tag.
5. Đối chiếu nội dung với test oracle hoặc dữ liệu kiểm chứng đã được bảo vệ.
6. Ghi audit, kiểm tra không lộ raw key trong log/snapshot.
7. Xác minh quy trình tương tự ở region và backup histories theo retention.

**Backup success không đồng nghĩa decrypt/restore success.** Không destroy KEK cũ cho tới khi encrypted DEKs còn phụ thuộc đã được rewrap hoặc hết nghĩa vụ lưu giữ.

## 21. Envelope metadata trong key lifecycle

~~~mermaid
flowchart LR
    G["Generate DEK / chọn KEK"] --> E["Create envelope metadata"]
    E --> S["Store ciphertext + encrypted DEK"]
    S --> U["Decrypt theo expected scope"]
    U --> R["Rotate: KEK rewrap / DEK re-encrypt"]
    R --> V["Update version + verify"]
    V --> T["Retire old key khi dependencies cleared"]
    T --> D["Revoke / Destroy theo approval"]
    A["Audit + inventory"] --> E
    A --> R
    A --> D
~~~

| Giai đoạn | Metadata có vai trò gì? |
|---|---|
| **Generation** | Ghi key origin, algorithm, key usage, owner và KEK/DEK references |
| **Provisioning** | Ràng buộc tenant/purpose và IAM với key scope |
| **Encrypt** | Lưu suite/version, nonce/tag, wrapped DEK, AAD/context schema |
| **Storage** | Bảo vệ tính toàn vẹn bản ghi, retention và revision |
| **Decrypt** | Chọn đúng key/version, kiểm tra AAD/authz, verify tag |
| **Rotate KEK** | Thay encryptedDEK + KEK ref/context và metadata revision |
| **Rotate DEK** | Cập nhật ciphertext/nonce/tag và DEK material mới |
| **Revoke** | Hỗ trợ truy tìm records/key version và cache consumers |
| **Destroy** | Chứng minh encrypted DEK/backup dependencies đã được xử lý |

### 21.1. Key inventory liên hệ tới envelope

~~~text
KEK / material version
   |
   +-- encrypted DEK references
         |
         +-- dataset / object / tenant
         +-- envelope format + AAD schema
         +-- snapshots / archive / DR replicas
~~~

Nếu không thể truy ra các encrypted DEKs đang dùng một KEK, operator không có cơ sở chắc chắn để kết luận có thể hủy KEK mà không làm mất dữ liệu.

### 21.2. Metadata trạng thái không thay provider enforcement

Một field status=REVOKED trong database không ngăn KMS Decrypt nếu provider vẫn cho phép hoặc ứng dụng đã cache plaintext DEK. Phải kiểm tra **KMS observed state, IAM, reader behavior, cache invalidation và audit**.

### 21.3. Crypto-shredding không phải xóa keyRef

Crypto-shredding chỉ có cơ sở khi vật liệu cần giải mã đã **bị hủy thật**, không còn bản sao/recovery path thuộc phạm vi và không làm mất dữ liệu của tenant khác. Xóa keyRef khỏi database không có nghĩa KEK/DEK đã biến mất.

## 22. Fail-safe khi envelope metadata lỗi

| Tình huống | Không làm | Cách xử lý |
|---|---|---|
| Unknown envelopeVersion | Đoán parser | Reject hoặc migration được duyệt |
| Unknown suite | Fallback AES-ECB hoặc không mã hóa | Reject theo allowlist |
| Missing nonce/tag | Trả plaintext chưa xác thực | Reject record |
| Wrong encryption context | Thử hàng loạt key/context khác | Fail và kiểm tra nguồn metadata |
| AAD mismatch | Bỏ AAD để đọc cho được | Treat as integrity/authz failure |
| Unknown keyRef | Dùng default master key | Kiểm tra registry/key policy, fail-closed |
| Tag verification failure | Dùng output chưa xác thực | Không trả plaintext |
| Header quá lớn/nesting sâu | Cấp phát buffer tùy ý | Schema and size bounds trước decode |
| KMS timeout/outage | Sinh hard-coded emergency key | Fail-safe hoặc recovery path được phê duyệt |
| Revision stale | Ghi đè metadata mới | CAS, retry/reconcile sau khi đọc lại |
| Duplicated JSON fields | Chọn tùy parser | Reject input mơ hồ |
| Audit thiếu coverage | Tuyên bố không có misuse | Nêu rõ giới hạn chứng cứ |

Lỗi trả về cho client không nên tiết lộ thông tin giúp xác định **key hoặc object của tenant khác có tồn tại không**, trong khi internal logs có thể cần error code đủ điều tra nhưng **không chứa plaintext DEK, password, bearer token hoặc dữ liệu nhạy cảm**.

## 23. Case study: tráo envelope giữa hai tenant

Một SaaS lưu hóa đơn của tenant A và B. Reader dùng tenantId lấy từ JSON envelope làm AAD mà **không so sánh với tenant được xác thực**. Một attacker copy nguyên envelope hợp lệ của tenant B sang object path của tenant A.

### 23.1. Vì sao tag có thể vẫn hợp lệ?

Ciphertext, DEK và AAD lấy từ envelope B vẫn nhất quán. AEAD tag đúng **không tự chứng minh nội dung thuộc object A**.

### 23.2. Cách sửa

1. Xác thực người dùng/tenant A bằng identity provider.
2. Kiểm tra quyền đọc invoice-901 từ registry/data model đáng tin.
3. Dùng **expected tenant/object/purpose** từ dữ liệu đã kiểm tra, không chỉ từ envelope.
4. Xác thực keyRef thuộc scope A, dùng đúng KMS context.
5. Decrypt với AAD dựa trên expected scope và verify tag.
6. Reject nếu envelope B bị tráo vào object A; audit cross-tenant anomaly.

**Bài học:** envelope metadata cần được ràng buộc với **nguồn identity và object ownership độc lập**, không tự chứng minh quyền bằng chính field attacker có thể copy.

## 24. Case study: KEK rewrap làm hỏng tag của payload

Một hệ thống định nghĩa AAD của AES-GCM gồm: tenantId, objectId, **kekRef và encryptedDEK bytes**. Khi rotate KEK v1 sang v2, worker chỉ rewrap DEK, thay keyRef/encryptedDEK trong header.

### 24.1. Kết quả

Payload không đổi nhưng reader tính AAD mới, do đó GCM tag cũ không khớp. Data có thể **không giải mã được** sau một bước rotation tưởng như chỉ thay lớp bọc.

### 24.2. Thiết kế lại

- Chọn **payload AAD ổn định** theo tenant/object/purpose/suite/format.
- Bảo vệ wrapped DEK bằng **KMS authenticated context và key policy**, không để caller sửa keyRef tùy ý.
- Dùng transaction/CAS cho cập nhật wrapped DEK, keyRef, revision.
- Verify reader vẫn unwrap đúng DEK và payload tag hợp lệ.
- Không hủy KEK v1 trước khi mọi object/backup cần thiết đã chuyển.

Nếu dữ liệu lịch sử đã đưa wrapping fields vào AAD, cần migration tái tạo payload AEAD/tag hợp lệ thay vì đổi metadata tùy ý.

## 25. Case study: archive còn ciphertext nhưng thiếu envelope metadata

Một archive giữ ciphertext và encrypted DEK, nhưng đã bỏ **wrap context version, original objectId và KEK material reference**. Sau vài năm, alias KEK đổi và AAD schema nâng cấp.

Backup restore thành công, nhưng KMS Unwrap hoặc AES-GCM Verify thất bại.

### 25.1. Phòng ngừa

- Định nghĩa **self-describing envelope** và schema được version hóa.
- Giữ key reference/material version phù hợp provider, context schema và trusted object identity.
- Lưu **test fixtures/known-answer records** của từng format version.
- Kiểm thử DR trên archive nhiều đời, không chỉ dữ liệu mới nhất.
- Duy trì KEK availability/reader support đúng retention.
- Rewrap/migrate trước khi bỏ legacy KEK/parser.
- Không bỏ tag verification hoặc thử đoán key bằng heuristic thiếu kiểm soát.

**Metadata đủ chưa phải là mọi thứ:** nếu KEK đã bị destroy thật và không còn recovery path, metadata không thể tái tạo vật liệu khóa ngẫu nhiên đã mất.

## 26. Ma trận kiểm thử envelope metadata

| Tình huống | Kết quả mong đợi |
|---|---|
| Envelope đúng suite/version/keyRef/context | KMS Unwrap + AEAD Verify thành công |
| Unsupported envelopeVersion | Reject |
| Suite đổi sang AES-ECB/none | Reject theo allowlist |
| Nonce sai độ dài suite AES-GCM mẫu | Reject |
| Tag/ciphertext bị sửa 1 byte | Decrypt thất bại |
| Trusted scope tenant A khác record tenant B | Reject trước KMS call |
| Copy nguyên envelope từ object B sang A | Không cho đọc như object A |
| Thay keyRef ngoài scope | IAM/key policy/allowlist từ chối |
| Encrypted DEK sai bytes | Unwrap hoặc AEAD verify thất bại |
| KMS context khác lúc wrap | Unwrap thất bại nếu provider bind context |
| Header có duplicate JSON keys | Parser reject theo schema |
| Base64/format lỗi hoặc header quá lớn | Reject trước phân bổ tài nguyên lớn |
| Legacy AAD schema version được hỗ trợ | Reader tạo đúng bytes AAD cũ |
| Legacy insecure algorithm đã bị cấm | Reject/migration, không downgrade |
| Rewrap KEK, giữ DEK và AAD ổn định | Wrapped DEK/keyRef đổi; payload tag vẫn đúng |
| Rewrap làm thay fields chứa trong AAD cũ | Negative test bắt lỗi |
| DEK rotation | Cập nhật ciphertext, nonce/tag và wrapped DEK |
| Nhiều recipients, unauthorized addition | Approval/policy từ chối |
| Xóa recipient wrapper đã từng bị lộ DEK | Không coi đã thu hồi DEK rõ khỏi người đó |
| Chunked stream bị reorder/truncate | Authenticated chunk manifest phát hiện |
| Nonce trùng dưới cùng DEK/multiwriter | Thiết kế/test ngăn hoặc báo lỗi |
| KMS rewrap xong nhưng DB update lỗi | Reconciler xử lý, không báo completed |
| CAS conflict giữa rotation jobs | Reject stale write, retry có kiểm soát |
| Backup thiếu nonce/wrapped DEK/context | Restore test phát hiện |
| KEK cũ còn archive dependencies | Destruction guard chặn |
| KMS disabled, application còn cache plaintext DEK | Cache handling và revoke test phát hiện |
| Audit envelope operations | Actor, keyRef/version, suite/outcome; không có raw key |
| Cross-region backup | Có key recovery và ability-to-decrypt được xác minh |

**Đừng chỉ chạy Encrypt/Decrypt round-trip**, vì chương trình vẫn có thể giải mã đúng khi IAM quá rộng, header cho phép key substitution hoặc reader không kiểm tra tenant authorization.

## 27. Lỗi phổ biến, checklist và câu hỏi tự kiểm tra

### 27.1. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Lưu plaintext DEK cạnh ciphertext | Storage leak làm lộ data | Wrapped DEK, KEK riêng trong KMS/HSM |
| Thiếu nonce/tag | Dữ liệu không thể AEAD Decrypt/Verify | Self-describing envelope |
| Chỉ lưu alias “current” | Không giải mã được dữ liệu cũ sau rotation | Key ref/version phù hợp provider |
| Nhầm envelopeVersion với KEK version | Reader chọn sai format hoặc key | Tách các phiên bản |
| Suite do header tùy chọn | Downgrade thuật toán | Algorithm allowlist |
| AAD tạo từ JSON không canonical | Reader tạo bytes khác | Binary length-prefix/canonical schema |
| Tenant lấy từ client hoặc envelope tự khai | Cross-tenant decryption oracle | Trusted expected scope |
| Không ràng buộc object identity | Copy envelope sang object khác | Bind AAD với expected object |
| Bỏ tag/AAD khi lỗi | Chấp nhận plaintext chưa xác thực | Fail-closed |
| Đưa encryptedDEK/keyRef vào payload AAD nhưng vẫn muốn rewrap | Rotation làm mất tag hợp lệ | Tách mutable wrapping khỏi stable payload binding |
| Không bảo vệ wrapping metadata | Key substitution/recipient tampering | KMS context, IAM và workflow |
| Đổi algorithm field nhưng giữ ciphertext | Dữ liệu hỏng và vi phạm policy | Decrypt/re-encrypt migration |
| Không giới hạn header size/JSON depth | Denial of service | Parser bounds |
| Log DEK/secret khi điều tra | Tạo nguồn lộ mới | Chỉ audit metadata |
| Không xác thực recipient list | Mở rộng quyền chia sẻ DEK | Approval và access scope |
| Chunking thiếu manifest | Truncation/reorder không phát hiện đầy đủ | Authenticated chunk protocol |
| KMS/DB update không có revision | Stale writer làm rollback metadata | CAS, idempotency, reconciliation |
| Hủy KEK khi backup còn encrypted DEK | Mất khả năng khôi phục | Dependency inventory và DR test |
| Xóa keyRef rồi gọi crypto-shredding | Secret/backup có thể vẫn tồn tại | Verify destruction/recovery state |
| Chỉ test format mới nhất | Legacy data không đọc được | Versioned fixtures và backward compatibility |

### 27.2. Checklist thiết kế production

Trước khi chấp nhận định dạng **Envelope metadata**:

- **Scope:** purpose, tenant, object, algorithm/key usage và retention được xác định?
- **Required fields:** envelope/suite version, keyRef/material version, encryptedDEK, nonce, tag và schema context đủ để giải mã?
- **Key protection:** plaintext DEK/KEK không nằm cùng quyền đọc ciphertext?
- **AAD:** format byte-level ổn định, expected object/tenant/purpose từ nguồn đáng tin?
- **KMS:** wrap context đúng provider, keyRef trong allowlist và grants đúng scope?
- **Authorization:** kiểm tra user/workload/tenant/object trước Unwrap?
- **Format policy:** reject unsupported suite, duplicate keys, invalid input và downgrade?
- **Nonce/tag:** AES-GCM nonce duy nhất dưới từng DEK, tag được kiểm tra trước khi dùng plaintext?
- **Mutable metadata:** có workflow riêng cho wrapped DEK/keyRef/revision, không phá payload AAD?
- **Versioning:** envelope, suite, key material, AAD/context schema được phân biệt?
- **Multi-recipient:** thêm/xóa recipients có approval/audit và giới hạn?
- **Chunking:** sequence, total length và authenticated manifest được bảo vệ?
- **Concurrency:** CAS, operation ID, retry/idempotency, KMS/DB reconciliation?
- **Backup/DR:** giữ metadata, schema và KEK recovery; đã test restore nhiều version?
- **Lifecycle:** rewrap vs re-encrypt, revoke, cached DEK, destruction dependencies?
- **Audit:** actor, keyRef/version, operation, outcome; không có raw secret?
- **Tests:** tamper, cross-tenant, parsing, nonce, downgrade, region, migration, rollback?

### 27.3. Câu hỏi tự kiểm tra

**Câu 1. Encrypted DEK có thể lưu cùng ciphertext không?**  
**Trả lời:** Có. Đó là mẫu envelope encryption phổ biến nếu KEK/quyền Unwrap được bảo vệ riêng và wrapped DEK được bảo vệ phù hợp.

**Câu 2. EnvelopeVersion và KEK material version có giống nhau không?**  
**Trả lời:** Không. Một bên mô tả format, bên kia mô tả vật liệu khóa dùng unwrap.

**Câu 3. Nonce và tag của AES-GCM có cần bí mật không?**  
**Trả lời:** Thường không. Nonce cần duy nhất dưới cùng key, tag phải được verify.

**Câu 4. AAD khác KMS encryption context ra sao?**  
**Trả lời:** AAD xác thực dữ liệu payload; context KMS có thể xác thực phép bọc DEK. Chúng không tự liên kết nếu ứng dụng chưa thiết kế.

**Câu 5. Nếu copy cả envelope hợp lệ từ object A sang B, tag có thể vẫn đúng không?**  
**Trả lời:** Có. Cần expected object identity từ nguồn tin cậy để ngăn tráo object.

**Câu 6. Vì sao không nên đưa encrypted DEK bytes vào payload AAD khi muốn rewrap độc lập?**  
**Trả lời:** Rewrap thay encrypted DEK bytes, khiến tag cũ không khớp AAD mới. Cần bảo vệ wrapping fields riêng.

**Câu 7. Khi DEK lộ, chỉ rewrap bằng KEK mới đã đủ chưa?**  
**Trả lời:** Không. Kẻ giữ DEK rõ vẫn có thể giải mã ciphertext; cần đánh giá thay DEK và re-encrypt.

**Câu 8. KeyRef có phải quyền giải mã không?**  
**Trả lời:** Không. IAM/KMS policy và authorization theo object/tenant quyết định quyền.

**Câu 9. Vì sao phải giới hạn kích thước metadata trước khi decode?**  
**Trả lời:** Để tránh cấp phát bộ nhớ hoặc gọi KMS vô hạn từ input giả mạo, giảm nguy cơ DoS.

**Câu 10. Khi KMS rewrap thành công nhưng DB chưa update, phải làm gì?**  
**Trả lời:** Dùng workflow/reconciler và revision để phục hồi nhất quán; không tuyên bố đã hoàn thành hoặc xóa KEK cũ.

**Câu 11. Backup ciphertext và encrypted DEK đủ để restore chưa?**  
**Trả lời:** Chưa chắc. Cần nonce, tag, format/AAD/context schema, KEK availability và recovery permissions.

**Câu 12. Crypto-shredding có nghĩa xóa keyRef trong metadata không?**  
**Trả lời:** Không. Cần hủy vật liệu khóa thực sự và đánh giá mọi bản sao/recovery path.

**Câu 13. Một headerSignature/MAC luôn bắt buộc không?**  
**Trả lời:** Không. Phụ thuộc những trường nào đã được bảo vệ bằng AEAD AAD, authenticated wrapping hoặc miền metadata đáng tin.

**Câu 14. Với chunked encryption, mỗi chunk có tag đúng đã bảo đảm toàn bộ file đầy đủ chưa?**  
**Trả lời:** Chưa. Cần bảo vệ số lượng, thứ tự và tính đầy đủ của stream.

**Câu 15. KMS DisableKey có tự vô hiệu một DEK đã cache trong RAM không?**  
**Trả lời:** Không tự động. Cần TTL/usage limits, cache invalidation và policy enforcement tại consumer.

---

**Ghi nhớ:** **Envelope metadata** là hợp đồng dữ liệu và an toàn mật mã cho phép **chọn đúng DEK/KEK, thuật toán, nonce/tag, AAD, KMS context, key material version và trusted object scope**. Thiết kế tốt phải vừa **tách plaintext key khỏi ciphertext**, vừa bảo vệ **metadata quan trọng khỏi tráo đổi/downgrade**, duy trì khả năng **rewrap, re-encrypt, backup/restore, kiểm toán, revocation và destruction** mà không làm mất dữ liệu hợp lệ hoặc mở đường giải mã sai tenant.



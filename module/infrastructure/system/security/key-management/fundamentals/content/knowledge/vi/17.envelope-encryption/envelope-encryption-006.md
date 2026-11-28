# KEK tách khỏi DEK: nguyên tắc phân tầng khóa trong envelope encryption

## 1. Vì sao không dùng một khóa cho mọi việc?

Giả sử một hệ thống Java lưu 20 triệu hồ sơ trong cơ sở dữ liệu. Cách triển khai đầu tiên có vẻ đơn giản: đặt một **AES key** trong biến môi trường và sử dụng chính khóa đó để mã hóa mọi hồ sơ. Nhưng ngay khi cần thay khóa, hệ thống gặp hàng loạt vấn đề:

- Muốn đổi khóa phải đọc, giải mã và mã hóa lại toàn bộ dữ liệu; mất thời gian, băng thông và có nguy cơ gián đoạn.
- Nếu một máy chủ ứng dụng bị chiếm và lộ raw key, attacker có thể giải mã mọi bản mã đã sao chép.
- Khóa được nhân bản ở nhiều service, deployment, job backup và môi trường, rất khó biết ai đang giữ bản sao.
- Chính sách IAM chỉ có thể cấp hoặc thu hồi quyền với một bí mật chung, khó tách **quyền bảo vệ khóa** khỏi **quyền đọc dữ liệu**.
- Không thể dễ dàng quản lý từng khách hàng, bản ghi, lô dữ liệu và vòng đời lưu trữ khác nhau.
- Khi cần hủy quyền giải mã một nhóm dữ liệu, thao tác với khóa chung có thể ảnh hưởng các nhóm không liên quan.

**Envelope encryption** xử lý những khó khăn này bằng cách chia khóa thành nhiều tầng. Điểm cốt lõi của bài học là **KEK tách khỏi DEK**:

- **DEK — Data Encryption Key**: khóa dùng để mã hóa/giải mã **dữ liệu thực tế**.
- **KEK — Key Encryption Key**: khóa dùng để **mã hóa/bọc (wrap)** DEK và phục hồi DEK bằng **unwrap** trong một cơ chế được phê duyệt.

Dữ liệu được mã hóa bằng DEK; bản thân DEK được bảo vệ bằng KEK. KEK thường được quản lý trong **KMS/HSM** hoặc một hệ thống quản lý khóa có mức bảo vệ cao hơn. DEK có thể là khóa riêng cho mỗi bản ghi, đối tượng, tệp hoặc lô dữ liệu theo threat model.

**Thông điệp quan trọng:** Tách KEK khỏi DEK không phải là “dùng hai thuật toán phức tạp hơn”. Đây là quyết định **phân tầng trách nhiệm**, giúp giảm số nơi chứa khóa giá trị cao, kiểm soát quyền, xoay vòng lớp bảo vệ khóa và truy vết phụ thuộc dữ liệu.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, kiến thức này liên kết **mật mã đối xứng, KMS/HSM, key classification, key lifecycle, IAM, audit, backup, rotation và incident response**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của **DEK**, **KEK**, wrapped DEK và **envelope**.
2. Vẽ luồng **write/encrypt** và **read/decrypt**, xác định nơi raw DEK có thể hiện diện.
3. Phân biệt **DEK encryption** với **KEK wrapping**, **KEK rotation**, **rewrap** và **re-encrypt**.
4. Chọn granularity của DEK theo hồ sơ, đối tượng, tenant hoặc batch và nêu trade-off.
5. Giải thích vì sao **KEK non-exportable vẫn có thể bị lạm dụng qua KMS Decrypt/Unwrap API**.
6. Thiết kế metadata gồm **key ID/version, wrapped DEK, nonce, tag, AAD, encryption context và schema version**.
7. Nhận diện sự cố như **key reuse, GCM nonce reuse, cross-tenant decrypt, key deletion sai thời điểm, quyền IAM rộng**.
8. Hiểu chiến lược **KMS/HSM grants, key custody, approval, audit và recovery**.
9. Đọc ví dụ **Java 17** dùng AES-GCM với hai khóa độc lập, thử **rewrap không đổi ciphertext dữ liệu**.
10. Lập checklist kiểm tra kiến trúc envelope encryption và tự đánh giá rủi ro.

## 2. Từ điển thuật ngữ: không nhầm tầng dữ liệu và tầng khóa

| Thuật ngữ | Chức năng | Vật liệu bí mật? | Vị trí thường thấy |
| --- | --- | --- | --- |
| **Plaintext data** | Dữ liệu gốc cần bảo vệ | Có thể rất nhạy cảm | RAM ứng dụng trong thời gian xử lý |
| **DEK** | Khóa Encrypt/Decrypt dữ liệu | **Có** | Sinh từ CSPRNG/KMS; tồn tại ngắn hạn trong process hoặc bên trong cryptographic module |
| **KEK** | Khóa Wrap/Unwrap DEK | **Có** | KMS/HSM, key vault hoặc ranh giới mật mã được quản lý |
| **Wrapped DEK** | Bản mã của DEK dưới KEK | Không phải raw key; vẫn phải bảo vệ integrity/context | Lưu cùng ciphertext/metadata hoặc trong registry |
| **Data ciphertext** | Dữ liệu đã mã hóa dưới DEK | Thường không bí mật về bản thân byte, nhưng vẫn có thể nhạy cảm về metadata | Database, object storage, backup |
| **Nonce/IV** | Giá trị dùng cho cơ chế mã hóa cụ thể | Thường không bí mật; phải đáp ứng quy tắc uniqueness | Gắn với ciphertext ở mỗi tầng AEAD |
| **Authentication tag** | Kiểm tra integrity/authenticity của dữ liệu dưới khóa | Không phải bí mật | Gắn với bản mã |
| **AAD** | Metadata được xác thực nhưng không mã hóa bởi AEAD | Không nên chứa secret; phải lấy từ context đúng | Ràng buộc tenant, resource, purpose, version |
| **Encryption context** | Metadata gắn với thao tác KMS khi provider hỗ trợ | Thường **không bí mật** | KMS wrap/unwrap request và audit metadata |
| **Key ID/version** | Tham chiếu key material để giải mã/rotate | Không phải bí mật, nhưng cần integrity/access control | Envelope header, key registry, inventory |
| **Cryptoperiod** | Khoảng thời gian key được phép dùng cho mục đích cụ thể | Không | Policy và key inventory |

### 2.1. KEK và DEK có thể cùng là AES key, nhưng không cùng purpose

Một DEK AES-256 và KEK AES-256 đều có thể dài 256 bit. Điều làm chúng khác nhau không chỉ là độ dài:

- **DEK** được phép dùng cho **data Encrypt/Decrypt**.
- **KEK** được phép dùng cho **key wrapping/unwrapping**.
- KEK được cấp quyền riêng, kiểm toán riêng, lưu ở ranh giới quản lý chặt hơn.
- DEK và KEK phải là **vật liệu khóa khác nhau**, sinh/derive theo profile được phê duyệt.
- Không tái sử dụng cùng raw key cho cả hai tầng chỉ vì thuật toán AES có thể xử lý cả dữ liệu và bytes của key.

**Key purpose separation** giảm nguy cơ làm lẫn domain, kiểm soát quyền sai và phá kế hoạch rotation.

### 2.2. Một hay nhiều tầng KEK?

Trong thực tế có thể có phân cấp:

~~~text
HSM root/master key
       |
       +-- KEK của ứng dụng/tenant (được quản lý)
                    |
                    +-- Wrapped DEK cho object A
                    |       |
                    |       +-- AES-GCM ciphertext A
                    |
                    +-- Wrapped DEK cho object B
                            |
                            +-- AES-GCM ciphertext B
~~~

Các hệ thống KMS có thể gọi key quản lý là **KMS key**, **customer-managed key** hoặc **master key**. Tên gọi phụ thuộc nhà cung cấp; hãy xác định nó thực sự thực hiện **Wrap/Unwrap hay Encrypt/Decrypt** trên loại vật liệu nào. Không suy diễn key topology chỉ từ nhãn “master”.

### 2.3. Chữ “tách” phải hiểu ở ba chiều

1. **Tách vật liệu khóa:** KEK và DEK là hai secrets khác nhau, có thể do hai cơ chế/ranh giới quản lý khác nhau tạo ra.
2. **Tách mục đích và quyền:** workload được cấp quyền Encrypt data không mặc nhiên có quyền chỉnh KEK policy; key administrator không mặc nhiên đọc plaintext.
3. **Tách vòng đời:** KEK có thể rotation/rewrap mà không thay ciphertext; DEK có thể re-encrypt dữ liệu mà không bắt buộc thay mọi KEK.

Tách biệt này **không tự bảo đảm tenant isolation hoặc confidentiality** nếu triển khai không kiểm soát RAM, IAM hoặc AAD.

## 3. Kiến trúc envelope encryption và ranh giới bí mật

~~~mermaid
flowchart TB
    APP["Java application"] -->|"Request GenerateDataKey / Wrap"| KMS["KMS / HSM: quản lý KEK"]
    KMS -->|"Wrapped DEK + plaintext DEK tạm thời tùy API"| APP
    APP -->|"AES-GCM Encrypt với DEK"| C["Data ciphertext"]
    APP -->|"Wrapped DEK + key metadata"| W["Envelope metadata"]
    C --> STORE[("Database / object storage")]
    W --> STORE
    IAM["IAM / Key policy + owner/custodian"] --> KMS
    AUD["Audit protected"] <-->|"Key operation metadata"| KMS
    APP -->|"Business authorization + app audit"| AUD
~~~

**Điểm dễ bị hiểu sai:** Nhiều KMS cung cấp API trả cả **plaintext DEK và wrapped DEK** về ứng dụng (ví dụ mô hình GenerateDataKey). Điều đó giúp ứng dụng mã hóa dữ liệu nhanh bằng AES-GCM nhưng **plaintext DEK xuất hiện trong RAM**. KEK có thể vẫn non-exportable, song mô hình không có nghĩa **mọi secret luôn nằm trong HSM**.

Một số kiến trúc khác thực hiện Encrypt/Decrypt dữ liệu trực tiếp bên trong cryptographic module hoặc cung cấp API không lộ DEK cho ứng dụng. Chọn mô hình theo kích thước dữ liệu, latency, provider capabilities, dữ liệu cần bảo vệ và threat model.

### 3.1. Các trust boundaries chính

| Ranh giới | Điều cần bảo vệ |
| --- | --- |
| **Ứng dụng Java** | DEK/plaintext trong RAM; authorization, dữ liệu nhạy cảm không rơi vào log/dump |
| **KMS/HSM** | KEK material, key operations, policy/grants, key state, audit và recovery |
| **Network** | Giao tiếp TLS/peer identity với KMS; credentials không bị đánh cắp |
| **Storage** | Ciphertext và wrapped DEK không bị thay/copy chéo context; version/metadata nguyên vẹn |
| **Identity & IAM** | Workload chỉ có quyền đúng key/action/environment, tránh tự cấp grant |
| **Inventory/backup** | Biết owner, key ID/version, dependencies, retention và đường restore |
| **Audit** | Ghi hoạt động Sign/Decrypt/Unwrap/rotation và ngăn sửa/xóa trái phép |

KMS có thể kiểm tra rằng workload được phép Unwrap KEK, nhưng **không nhất thiết biết invoice ID nào thuộc tenant nào**. Ứng dụng vẫn phải xác thực principal và phân quyền trên resource.

### 3.2. Kiến trúc không có “bảo vệ tuyệt đối”

- Khi application host bị chiếm lúc đang xử lý plaintext, attacker có thể lấy **data/DEK trong bộ nhớ**.
- Nếu IAM cho phép **Unwrap rộng**, attacker có thể lấy nhiều DEKs dù KEK non-exportable.
- Nếu dữ liệu đã bị sao chép cùng plaintext DEK, việc rotation KEK về sau **không khiến attacker mất dữ liệu đã lấy**.
- Nếu KMS/HSM hoặc trust configuration bị compromise, blast radius có thể rất lớn.
- Nếu storage mất **key ID/version, nonce, authentication tag hoặc AAD schema**, ciphertext có thể trở nên không giải được.

Envelope encryption **hạn chế phạm vi và tạo cấu trúc quản trị**; tính an toàn phụ thuộc quyền, cấu hình, vận hành và kiểm tra đúng của từng tầng.

## 4. Luồng ghi: mã hóa dữ liệu bằng DEK, bọc DEK bằng KEK

Giả sử service phải lưu một hóa đơn mới trong tenant A.

### 4.1. Trình tự

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Java BillingService
    participant K as KMS/HSM
    participant D as Database
    participant L as Audit
    C->>A: Save invoice (authenticated request)
    A->>A: Authorize principal, tenant, invoice ID
    A->>K: GenerateDataKey / key-wrap workflow
    K-->>A: Plaintext DEK tạm thời + wrapped DEK
    A->>A: Tạo data nonce, expected AAD
    A->>A: AES-GCM Encrypt data bằng DEK
    A->>D: Ciphertext + data nonce/tag + wrapped DEK
    A->>D: KEK ID/version + schema/profile metadata
    A->>A: Giảm thời gian sống plaintext DEK
    K->>L: Audit operation + key metadata
    A->>L: Audit request/result, không log secrets
    A-->>C: Lưu thành công
~~~

Các bước nghiệp vụ quan trọng:

1. **Xác thực và phân quyền:** principal có quyền ghi hóa đơn vào tenant A?
2. **Chọn KEK từ nguồn tin cậy:** dựa vào service/environment/tenant policy; không nhận bất kỳ key ID do client gợi ý.
3. **Sinh DEK:** dùng CSPRNG/KMS đúng profile. DEK có thể riêng mỗi object, batch hoặc workload theo quyết định đã phê duyệt.
4. **Wrap DEK:** qua KEK trong KMS/HSM hoặc cơ chế key wrapping được phép.
5. **Mã hóa dữ liệu:** dùng AEAD như AES-GCM, tạo nonce đúng quy tắc dưới DEK và AAD ràng buộc tenant/resource/purpose.
6. **Lưu envelope:** ghi data ciphertext/tag/nonce cùng wrapped DEK và metadata định dạng/version.
7. **Hạn chế vật liệu rõ:** không giữ DEK/plaintext lâu hơn cần thiết, không đưa vào log/trace hoặc exception.
8. **Audit:** lưu key ID/operation/result/request correlation, không lưu raw secrets.

### 4.2. Đường mã hóa không đồng nghĩa đường KMS phải thấy plaintext dữ liệu

Với mô hình ứng dụng AES-GCM local, KMS chỉ cần xử lý **DEK** (hoặc tạo ra DEK), không cần nhận toàn bộ hóa đơn. Điều này có lợi cho:

- **Hiệu năng**: dữ liệu lớn được mã hóa bằng AES local, giảm KMS round trips trên từng block.
- **Băng thông**: KMS không phải xử lý megabytes/gigabytes nội dung.
- **Phân tách ranh giới**: provider KMS không cần thấy nội dung nghiệp vụ trong đường wrap.
- **Quy mô**: KEK quản lý số lượng DEKs lớn, ứng dụng tự xử lý data encryption.

Đổi lại, ứng dụng **phải bảo vệ DEK trong RAM**, nonce, AAD và đúng quyền truy cập dữ liệu. Nếu muốn giảm tối đa nơi tồn tại DEK rõ, cần cân nhắc mô hình HSM/enclave/provider APIs hỗ trợ, với trade-off latency/throughput.

### 4.3. Vì sao data ciphertext không được bọc trực tiếp bằng KEK cho mọi bản ghi?

Về mặt toán học, một số KMS cho phép mã hóa payload nhỏ trực tiếp với key quản lý. Nhưng dùng KEK cho toàn bộ dữ liệu lớn:

- Gắn chi phí và quota KMS vào mọi lần data encryption.
- Tăng phụ thuộc mạng/KMS cho khối lượng lớn.
- Làm mờ ranh giới **key operation** và **data operation**.
- Khó đạt mô hình DEK-per-object để giảm phạm vi lộ khóa.
- Có thể vượt giới hạn kích thước plaintext của API KMS.
- Mở rộng số thao tác nhạy cảm và cần kiểm soát audit/availability.

Không nên biến KEK thành DEK chỉ vì “cũng là AES key”. Dùng **key đúng purpose và đúng API**.

## 5. Luồng đọc: unwrap DEK, sau đó giải mã dữ liệu

Để đọc hóa đơn:

~~~mermaid
sequenceDiagram
    participant U as Authorized user
    participant A as Java BillingService
    participant D as Database
    participant K as KMS/HSM
    U->>A: Read invoice
    A->>A: Authenticate + authorize tenant and record
    A->>D: Fetch envelope, encrypted data, metadata
    D-->>A: Ciphertext + wrapped DEK + key ref + nonce/tag
    A->>A: Validate envelope schema, IDs, sizes, trusted context
    A->>K: Unwrap wrapped DEK với approved KEK/context
    K-->>A: Plaintext DEK tạm thời hoặc operation handle
    A->>A: AES-GCM Decrypt với expected data AAD
    A->>A: Nếu authentication failure => reject
    A-->>U: Trả data đã được phân quyền
~~~

Các điểm bắt buộc:

- **Kiểm tra quyền trước Unwrap:** không truy cập KMS chỉ vì bản ghi có wrapped DEK.
- **Không chọn KEK tùy ý từ dữ liệu chưa tin:** dùng key registry mapping, expected tenant/service/purpose và policy.
- **Bảo vệ integrity của context:** nếu tenant ID hoặc object ID đến từ storage, đối chiếu với resource/identity đã xác thực.
- **AEAD authentication:** tag failure phải từ chối; không thử bỏ AAD hoặc fallback về mode cũ.
- **Không coi data decrypt thành công là authorization:** một service có quyền mở khóa kỹ thuật vẫn có thể không được đọc dữ liệu của user khác.
- **Key state và cryptoperiod:** key đã retired có thể chỉ dùng Decrypt dữ liệu lịch sử trong phạm vi được cho phép.
- **Audit:** ghi thao tác key không tiết lộ DEK hoặc nội dung hóa đơn.

### 5.1. Có thể giả mạo metadata envelope không?

**Nonce, tag, wrapped DEK, key reference và version** thường nằm cạnh bản mã, nhưng không phải mọi trường đều mặc nhiên được bảo vệ integrity bởi AES-GCM của dữ liệu.

Ví dụ attacker có thể thay **keyId** để ứng dụng thử một KEK khác. Chính sách phải ràng buộc:

1. **Trusted key registry/allowlist** theo tenant và purpose.
2. Context/AAD cho **wrap** ràng buộc KEK reference, tenant, object và protocol version khi phù hợp.
3. AAD cho **data encryption** ràng buộc tenant, object, schema/purpose.
4. Key selection phải qua business authorization và IAM.
5. Serialization/version phải rõ ràng, tránh ambiguous concatenation.

**Chỉ có data GCM tag đúng không chứng minh toàn bộ header đã được kiểm tra**. Xác định trường nào được xác thực ở tầng nào và dùng nguồn tin cậy khi resolve key.

## 6. Vì sao KEK và DEK cần tách cả vòng đời?

### 6.1. Granularity và cryptoperiod khác nhau

| Tiêu chí | DEK | KEK |
| --- | --- | --- |
| **Phạm vi** | Một object, record, chunk/batch hoặc tập dữ liệu theo chính sách | Nhiều DEKs theo tenant/service/environment |
| **Chức năng** | Encrypt/Decrypt dữ liệu | Wrap/Unwrap data keys |
| **Storage** | Thường chỉ lưu dưới dạng wrapped trong envelope; có thể tồn tại tạm ở RAM | Lưu trong KMS/HSM với ranh giới và IAM chặt |
| **Số lượng** | Có thể hàng triệu | Thường ít hơn đáng kể so với DEKs |
| **Rotation** | Có thể cần **re-encrypt dữ liệu** | Có thể **rewrap DEK** mà giữ nguyên ciphertext |
| **Blast radius nếu raw key lộ** | Dữ liệu thuộc DEK đó | Nhiều DEKs có thể bị ảnh hưởng nếu attacker có wrapped copies |
| **Backup/retention** | Cần wrapped DEK và context khớp dữ liệu được lưu | Phải giữ đường Unwrap hợp lệ theo dữ liệu còn phụ thuộc |
| **Quyền** | Ứng dụng xử lý dữ liệu được cho phép | Principal có quyền KMS cụ thể + policy/SoD |

Nếu mỗi bản ghi dùng DEK riêng, lộ một DEK thường ảnh hưởng bản ghi đó; nhưng nếu ứng dụng reuse một DEK cho mọi bản ghi cùng tenant, blast radius tăng lên. Không có granularity duy nhất đúng cho mọi hệ thống.

### 6.2. DEK per-object, per-tenant hay per-batch?

| Mô hình | Ưu điểm | Nhược điểm và điều kiện |
| --- | --- | --- |
| **DEK per-object** | Giới hạn phạm vi lộ khóa; nonce dễ quản lý khi mỗi DEK chỉ dùng cho một encryption | Tăng số wrapped DEKs/metadata và thao tác wrap, có thể tăng chi phí KMS |
| **DEK per-batch** | Giảm số key operations, phù hợp luồng dữ liệu theo lô | Cần nonce strategy đáng tin, usage bounds và giới hạn batch |
| **DEK per-tenant** | Dễ mapping và quản lý một lớp tài nguyên mỗi tenant | Lộ DEK có thể ảnh hưởng nhiều records, rotation phức tạp, nonce reuse đáng chú ý |
| **DEK per-segment/chunk** | Thích hợp đối tượng lớn và xử lý streaming theo phần | Mỗi chunk cần nonce/indices/tag binding và anti-reordering |
| **Một DEK toàn hệ thống** | Triển khai đơn giản | Blast radius rất rộng; thường không phù hợp dữ liệu nhạy cảm đa tenant |

**DEK per-object không có nghĩa KMS key per-object.** Nhiều DEKs khác nhau có thể được wrap bằng cùng một KEK được quản lý; đó chính là lợi ích của envelope encryption.

### 6.3. DEK rotation khác KEK rotation

- **Rotate DEK:** dùng DEK mới cho plaintext, tạo **ciphertext/tag/nonce mới** qua re-encrypt; lưu đúng wrapped DEK mới.
- **Rotate KEK:** bảo vệ lại cùng DEK dưới KEK mới bằng **rewrap**, có thể giữ data ciphertext, nonce và tag.
- **Rotate signing key:** tạo cặp signing mới và cập nhật public trust; không phải wrap/re-encrypt data.
- **Rotate HMAC key:** có quy tắc phát hành MAC mới và xác minh MAC lịch sử theo protocol.
- **Rotate root/derivation key:** có thể ảnh hưởng nhiều derived keys; cần inventory dependency.

Hai thao tác DEK/KEK có thể cùng xảy ra khi rủi ro nghiêm trọng, nhưng **không nên bị gộp thành một từ “rotate” mơ hồ**.

## 7. Rewrap KEK khác với re-encrypt dữ liệu

### 7.1. Trước và sau rewrap

~~~text
Ban đầu:
  Data --AES-GCM(DEK-v1, nonce-data-v1)--> Ciphertext-v1
  DEK-v1 --Wrap(KEK-v1, nonce-wrap-v1)--> WrappedDEK-v1

Sau khi rotate KEK:
  Data ciphertext-v1, nonce-data-v1, tag-data-v1 KHÔNG ĐỔI
  DEK-v1 --Wrap(KEK-v2, nonce-wrap-v2)--> WrappedDEK-v2

Sau khi rotate DEK:
  Data --AES-GCM(DEK-v2, nonce-data-v2)--> Ciphertext-v2
  DEK-v2 --Wrap(KEK-v2, nonce-wrap-v3)--> WrappedDEK-v2
~~~

**Rewrap** thay đổi **cách bảo vệ DEK**, không thay khóa mã hóa data. **Re-encrypt** tạo bản mã dữ liệu mới dưới một DEK khác; thường cần đọc plaintext trong môi trường được phép và xử lý tính nhất quán của bản ghi.

### 7.2. Ranh giới tin cậy khi rewrap

Một cách đơn giản:

1. Unwrap DEK dưới KEK cũ.
2. Wrap **cùng DEK** dưới KEK mới.
3. Thay metadata wrapped DEK và version.
4. Xác minh data ciphertext vẫn mở đúng và có thể restore.

Nhưng bước 1 có thể xuất **plaintext DEK về ứng dụng**, tạo rủi ro mới. Một số KMS có API **re-encrypt/rewrap nội bộ** giữa keys mà không trả plaintext DEK về client; nên ưu tiên khi provider và security policy hỗ trợ.

**Không tự gọi một KMS API “ReEncrypt” rồi giả định nó cũng re-encrypt toàn bộ data ciphertext.** Nhiều API chỉ thay lớp bảo vệ blob DEK.

### 7.3. Rewrap không sửa lịch sử nếu KEK cũ đã bị lộ

Giả sử attacker đã sao chép:

~~~text
old KEK material
+ old wrapped DEKs
+ old data ciphertext
~~~

Sau khi rewrap toàn bộ DEKs dưới KEK mới, attacker vẫn có **bản copy của ba thành phần cũ**. Việc chuyển metadata trong database không xóa dữ liệu attacker đã lấy.

Do đó:

- Nếu KEK cũ **chỉ hết cryptoperiod** và chưa có dấu hiệu lộ, rewrap có thể phù hợp.
- Nếu raw KEK đã bị lộ và attacker có old wrapped DEKs, phải đánh giá **DEK/data impact**, có thể cần **re-encrypt bằng DEK mới**.
- Nếu raw DEK đã lộ, **chỉ rewrap DEK cũ không đủ**.
- Nếu quyền KMS bị lạm dụng nhưng raw KEK không xuất được, phải điều tra **lời gọi Unwrap/Decrypt, dữ liệu/DEKs đã nhận, audit và credential exposure**.
- Nếu đã lộ plaintext, không có rotation nào khiến attacker quên bản copy đã lấy.

### 7.4. Một lần rotate KEK không thể hủy ngay KEK cũ

Backup, snapshot và offline archive có thể vẫn chứa **wrapped DEK theo KEK-v1**. Trước khi destroy:

- Kiểm kê dữ liệu và backup phụ thuộc KEK-v1.
- Bảo đảm đã rewrap hoặc re-encrypt các bản cần giữ.
- Chạy **restore test** trong môi trường kiểm soát.
- Xem retention/hold/rollback requirements.
- Có owner approval, custodian execution, audit evidence.
- Chỉ khi không còn phụ thuộc hợp lệ mới destroy theo runbook.

**Backup ciphertext có checksum đúng vẫn có thể vô dụng nếu key material hoặc metadata cần unwrap đã mất.**

## 8. Chọn cơ chế wrapping: không coi “mã hóa bytes của khóa” là đủ

Mục đích của key wrapping là bảo vệ **tính bí mật và tính toàn vẹn** của DEK trong khi lưu/truyền giữa các ranh giới. Không nên tự xây Wrap bằng AES-ECB hoặc “AES-CBC không MAC”.

### 8.1. Các lựa chọn thường gặp

| Cơ chế | Vai trò | Lưu ý chính sách |
| --- | --- | --- |
| **KMS GenerateDataKey** | Sinh DEK và trả blob DEK được bọc dưới key quản lý | Có thể trả plaintext DEK; cần quản lý RAM, IAM và context |
| **KMS Encrypt/Decrypt hoặc Wrap/Unwrap APIs** | Bảo vệ bytes của DEK theo API provider | Giới hạn kích thước, thuật toán, grants và semantics theo provider |
| **AES Key Wrap (AES-KW)** | Cơ chế bọc key chuyên dụng | Dùng mode/parameters đúng chuẩn, không tự thiết kế |
| **AES-KWP** | Key wrapping có padding cho độ dài không chia block phù hợp | Phân biệt với CBC/ECB padding thường |
| **AEAD như AES-GCM** | Có thể mã hóa DEK dưới KEK với integrity và AAD | **Nonce của tầng wrap** cần uniqueness dưới KEK; context phải được xác thực |
| **RSA-OAEP** | Có thể wrap DEK bằng public key theo use case hợp lệ | Chỉ phù hợp payload nhỏ, xử lý hash/MGF/label và key purpose |

**Không dùng hash một chiều của DEK để “wrap”**: hash không thể unwrap. **Không mã hóa trực tiếp KEK bằng DEK** như một phép đảo tầng chỉ vì API cho phép.

### 8.2. Nếu dùng AEAD cho cả hai tầng

~~~text
Data layer:
  DEK + nonce-data + AAD-data -> ciphertext-data + tag-data

Key-wrapping layer:
  KEK + nonce-wrap + AAD-wrap -> wrapped-DEK + tag-wrap
~~~

Đây là **hai lần mã hóa với hai khóa và hai domain/context khác nhau**.

- **nonce-data** phải tuân thủ uniqueness dưới **DEK**.
- **nonce-wrap** phải tuân thủ uniqueness dưới **KEK**; KEK có thể dùng hàng triệu lần, nên thiết kế nonce/quota càng quan trọng.
- **AAD-data** có thể gồm tenant, object, purpose, schema version.
- **AAD-wrap** có thể gồm tenant, object, wrapped key purpose, KEK version, algorithm/profile.
- Nếu có KMS encryption context, nó chỉ được bảo vệ theo **semantics của API KMS**, không tự tương đương với AAD-data.
- Không có cơ chế chống **replay/rollback** chỉ nhờ hai tag đúng; cần version/state logic nếu có nguy cơ phát lại envelope hợp lệ cũ.

### 8.3. AEAD không xác thực một principal có quyền nghiệp vụ

Một wrapped DEK với tag hợp lệ có thể được unwrap dưới KEK đúng. Nhưng caller có quyền gọi KMS chưa chắc có quyền đọc **hóa đơn cụ thể**. Quyền nghiệp vụ phải được kiểm tra **trước** key operations và theo trusted identity–resource mapping.

## 9. Envelope metadata: phải lưu đủ để giải mã, nhưng không tin mù quáng

Một envelope thường gồm phần header và các blobs:

~~~json
{
  "formatVersion": 2,
  "dataAlgorithm": "AES-256-GCM",
  "dataNonceBase64": "<data nonce>",
  "ciphertextAndTagBase64": "<encrypted payload + tag>",
  "wrappedDek": {
    "wrappingProfile": "KMS-APPROVED-PROFILE",
    "kekReference": "<opaque trusted KMS key reference>",
    "kekVersion": "v3",
    "encryptedDekBase64": "<opaque wrapped DEK>"
  },
  "contextSchema": "invoice-envelope-v2",
  "resourceRef": "invoice-154"
}
~~~

Các chuỗi trong dấu ngoặc nhọn chỉ là placeholders, không phải vật liệu thật. Không chứa **raw DEK, raw KEK, private key hoặc password** trong envelope.

### 9.1. Metadata có thể yêu cầu thêm trường

Tùy wrapping provider và data format:

- **Wrap nonce/IV/tag** riêng nếu wrapper dùng AEAD ở phía ứng dụng.
- **KMS encryption context** hoặc nguồn để dựng context nhất quán khi Unwrap.
- **KDF salt/info/version** nếu DEK được derive theo lược đồ được phê duyệt.
- **Chunk index, total length, chunk nonce/tag** nếu file được mã hóa theo nhiều phần.
- **Content encoding/compression/profile version** cần biết để giải mã.
- **Object version và anti-rollback state** nếu bản cũ có thể bị thay thế trái phép.
- **Provider/region** và khóa thay thế trong migration nếu có cấu trúc cross-region.

### 9.2. Byte encoding phải xác định

AAD hoặc context thường chứa nhiều trường. Nối chuỗi không có phân định có thể gây nhập nhằng:

~~~text
("ab", "c") -> "abc"
("a", "bc") -> "abc"
~~~

Nên dùng **length-prefix encoding, canonical serialization hoặc protobuf/CBOR profile rõ ràng**. Trong Java, có thể dùng DataOutputStream ghi độ dài byte UTF-8 của từng field trước nội dung, hoặc dùng canonical schema được thiết kế và phiên bản hóa.

Thống nhất **Unicode normalization/UTF-8, field ordering, version, null handling**. Hai hệ thống tính ra AAD khác nhau sẽ thất bại xác thực dù dùng đúng key.

### 9.3. AAD không mã hóa metadata

AAD bảo vệ integrity khi được xác thực bằng AEAD nhưng **không làm metadata bí mật**. Không đưa password, token, PII không cần thiết hoặc raw key vào encryption context/AAD rồi nghĩ rằng chúng được mã hóa. Nhiều KMS có thể ghi context vào audit.

### 9.4. Không coi format version là thuật toán do client chọn

Một envelope có thể lưu tên thuật toán để phục vụ migration, nhưng **resolver phải so tên với allowlist/policy và key type đã duyệt**, không gọi Cipher theo bất kỳ chuỗi algorithm nào attacker tự gắn. Đường đọc legacy phải có **scope, expiry và controls**, không phải fallback khi tag lỗi.

## 10. Security policy của KEK và DEK: quyền nào thuộc về ai?

Phân tầng khóa chỉ có ý nghĩa khi quyền sử dụng cũng được phân tầng.

| Vai trò/chủ thể | Hoạt động hợp lệ theo phạm vi | Điều không nên mặc định có |
| --- | --- | --- |
| **Data writer** | Xin/nhận DEK và Encrypt data đúng tenant | Unwrap toàn bộ old DEKs, đổi key policy |
| **Data reader** | Unwrap DEK cần thiết và Decrypt đúng resource | Sign, Export KEK, hủy khóa |
| **KMS/HSM key custodian** | Quản lý KEK lifecycle, recovery, rotation theo approval | Đọc toàn bộ plaintext dữ liệu |
| **Key owner** | Quyết định purpose, cryptoperiod, data scope và rủi ro | Tự xuất KEK hoặc cấp quyền tùy ý |
| **IAM/key administrator** | Cấu hình grants/policy theo workflow | Tự cấp Decrypt rồi tự xóa audit |
| **Security auditor** | Đọc metadata và audit, đối soát key inventory | Unwrap, Sign hoặc lấy raw key |
| **Recovery operator** | Dùng restore-only grants có thời hạn/quorum | Quyền Decrypt thường trực mọi dữ liệu |
| **Application end user** | Thực hiện nghiệp vụ đã phân quyền | Gọi KMS với key ID bất kỳ |

### 10.1. Least privilege ở hai tầng

**Tầng KMS/IAM:** principal nào được dùng KEK nào, với action **GenerateDataKey, Encrypt, Decrypt, Wrap, Unwrap, ChangePolicy, ScheduleDeletion**? Provider có hỗ trợ context conditions không? Có role assume/cross-account path nào cấp quyền gián tiếp?

**Tầng ứng dụng:** principal có được xem **resource của tenant A** không? Có business policy, data classification hoặc approval nào khác?

Hai tầng phải đạt đồng thời. KMS non-exportable **không thay authorization**. Thậm chí tài khoản chỉ được CreateGrant hoặc ChangePolicy có thể tự cấp quyền Unwrap nếu không có separation of duties.

### 10.2. KMS encryption context và tenant binding

Một số KMS hỗ trợ context như:

~~~json
{
  "service": "billing",
  "environment": "production",
  "purpose": "wrap-invoice-dek",
  "tenant": "tenant-A"
}
~~~

Để giảm nguy cơ cross-tenant:

1. Chọn **trusted tenant ID** từ authenticated session và resource owner đã xác minh.
2. Dựng context có schema cố định; không dùng dữ liệu từ header client làm nguồn quyền độc lập.
3. Dùng KMS key policy/conditions khi provider hỗ trợ.
4. Ràng buộc **AAD-data** với chính tenant/object đó.
5. Kiểm tra business authorization trước KMS Decrypt.
6. Ghi audit key ID và operation, tránh log raw secrets/PII.

Context giúp phát hiện/từ chối sai ngữ cảnh nhưng **không phải ranh giới tenant hoàn chỉnh nếu caller có thể tự tùy ý chọn context và đã có quyền Decrypt trên nhiều key**.

## 11. Threat model: tách KEK/DEK giảm rủi ro nào, không giảm rủi ro nào?

| Tình huống | KEK/DEK separation giúp gì? | Giới hạn còn lại |
| --- | --- | --- |
| **Một DEK lộ** | Giới hạn dữ liệu nếu DEK có scope hẹp | Attacker vẫn đọc được ciphertext thuộc DEK đó |
| **KEK lộ** | Giữ DEKs trong dạng wrapped khi KEK còn bí mật | Nếu KEK và wrapped DEKs cùng lộ, nhiều DEKs bị ảnh hưởng |
| **App server bị chiếm** | App không nhất thiết giữ KEK raw | Attacker có thể lấy DEK/plaintext từ RAM hoặc lạm dụng KMS API |
| **KMS API bị lạm dụng** | IAM/audit có điểm kiểm soát tập trung | Non-exportable không chặn attacker có quyền Unwrap |
| **Database bị sao chép** | Chỉ có data ciphertext + wrapped DEKs, thiếu KEK thì khó giải | Metadata có thể lộ; rollback/replay, future KEK compromise |
| **Cần rotate KEK** | Rewrap nhanh hơn re-encrypt mọi dữ liệu | Old copies/backup có thể còn phụ thuộc hoặc đã bị lộ |
| **Cần rotate DEK** | Có thể re-encrypt từng object/batch theo scope | Phải xử lý plaintext, consistency và old backups |
| **KEK bị hủy nhầm** | Dễ xác định dependency nếu inventory tốt | Nếu mất đường unwrap cuối, dữ liệu không phục hồi |
| **Nonce reuse AES-GCM** | Hai tầng có nonce/key riêng giúp cấu trúc rõ | Không tự loại nguy cơ nonce reuse dưới cùng DEK/KEK |
| **Tenant B yêu cầu dữ liệu A** | Có thể dùng KEK per-tenant và AAD | Vẫn cần business authorization và trusted identity |
| **Attacker thay envelope header** | Context/AAD, key registry và authenticated metadata hỗ trợ phát hiện | Không tự được bảo vệ nếu trường nằm ngoài mọi authentication |
| **Attacker replay envelope cũ hợp lệ** | AEAD giữ integrity của bản cũ | Cần object version/anti-rollback để đảm bảo freshness |

Một thiết kế tốt **xác định rõ blast radius, key material residency và đường authorization**. Câu “chúng tôi có KMS và AES-256” không trả lời đủ các câu hỏi đó.
## 12. Java 17: triển khai hai tầng khóa và minh họa KEK rewrap

Đoạn mã sau là ví dụ **tự chứa, không cần thư viện ngoài JDK 17**. Nó thực hiện:

1. Sinh một **KEK-v1** bằng KeyGenerator và dùng nó chỉ để bảo vệ DEK.
2. Sinh một **DEK riêng** để mã hóa dữ liệu hóa đơn bằng AES-GCM.
3. **Bọc DEK** bằng AES-GCM sử dụng KEK-v1, nonce của tầng wrap và AAD riêng.
4. Giải mã envelope với **tenant, object và KEK ID kỳ vọng**, đồng thời kiểm tra tag.
5. Sinh **KEK-v2** và **rewrap cùng DEK** mà không cần thay ciphertext của hóa đơn.
6. Thử sửa ciphertext/tag và giả mạo tenant để xác nhận đường từ chối.
7. Không in KEK, DEK hoặc nội dung nhạy cảm của production.

**Thiết kế có chủ đích:** Hai tầng cùng dùng AES-GCM cho demo nhưng **key material, nonce và AAD độc lập**. Trong production, nên dùng **KMS/HSM wrapping API hoặc cơ chế wrapping được phê duyệt** để giảm khả năng KEK raw hiện diện trong JVM. Đừng dùng đoạn demo này để thay thế KMS client hoặc một thư viện production đã được kiểm tra.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class KekDekSeparationDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String CIPHER = "AES/GCM/NoPadding";
    private static final int NONCE_LENGTH = 12;
    private static final int TAG_BITS = 128;
    private static final int ENVELOPE_VERSION = 1;

    // Metadata và ciphertext. Trong production phải defensive-copy
    // mọi byte[] và kiểm tra kích thước đầu vào để tránh mutation/DoS.
    record WrappedDek(
            String kekId,
            byte[] wrapNonce,
            byte[] wrappedDekAndTag) {}

    record Envelope(
            int formatVersion,
            String tenantId,
            String objectId,
            byte[] dataNonce,
            byte[] dataCiphertextAndTag,
            WrappedDek wrappedDek) {}

    private static void require(boolean condition, String problem) {
        if (!condition) {
            throw new SecurityException(problem);
        }
    }

    private static SecretKey newAes256Key() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RANDOM);
        return generator.generateKey();
    }

    private static byte[] newNonce() {
        byte[] nonce = new byte[NONCE_LENGTH];
        RANDOM.nextBytes(nonce);
        return nonce;
    }

    // Length-prefixed UTF-8 giúp tránh ambiguity: ("ab","c")
    // không được mã hóa cùng bytes với ("a","bc").
    private static byte[] aad(
            String domain,
            String tenantId,
            String objectId,
            String contextId) throws Exception {

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            field(out, domain);
            field(out, tenantId);
            field(out, objectId);
            field(out, contextId);
        }
        return bytes.toByteArray();
    }

    private static void field(
            DataOutputStream out, String value) throws Exception {
        byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(encoded.length);
        out.write(encoded);
    }

    // Trong demo KEK tồn tại ở JVM. Production nên Wrap qua KMS
    // không xuất KEK material. Mỗi Wrap tạo nonce mới dưới KEK.
    private static WrappedDek wrap(
            byte[] dekMaterial,
            SecretKey kek,
            String kekId,
            String tenantId,
            String objectId) throws Exception {

        require(dekMaterial.length == 32,
            "Only AES-256 DEK is supported in this demo");

        byte[] wrapNonce = newNonce();
        Cipher wrapCipher = Cipher.getInstance(CIPHER);
        wrapCipher.init(Cipher.ENCRYPT_MODE, kek,
            new GCMParameterSpec(TAG_BITS, wrapNonce));
        wrapCipher.updateAAD(aad(
            "wrap-dek-v1", tenantId, objectId, kekId));

        byte[] wrapped = wrapCipher.doFinal(dekMaterial);
        return new WrappedDek(kekId, wrapNonce, wrapped);
    }

    private static byte[] unwrap(
            WrappedDek wrapped,
            SecretKey kek,
            String expectedKekId,
            String tenantId,
            String objectId) throws Exception {

        require(wrapped != null
                && expectedKekId.equals(wrapped.kekId()),
            "Unapproved KEK reference");
        require(wrapped.wrapNonce() != null
                && wrapped.wrapNonce().length == NONCE_LENGTH,
            "Invalid wrap nonce");

        Cipher unwrapCipher = Cipher.getInstance(CIPHER);
        unwrapCipher.init(Cipher.DECRYPT_MODE, kek,
            new GCMParameterSpec(TAG_BITS, wrapped.wrapNonce()));
        unwrapCipher.updateAAD(aad(
            "wrap-dek-v1", tenantId, objectId, expectedKekId));

        byte[] rawDek = unwrapCipher.doFinal(
            wrapped.wrappedDekAndTag());
        if (rawDek.length != 32) {
            Arrays.fill(rawDek, (byte) 0);
            throw new SecurityException("Unexpected DEK length");
        }
        return rawDek;
    }

    static Envelope encrypt(
            byte[] plaintext,
            String trustedTenant,
            String trustedObjectId,
            SecretKey kek,
            String approvedKekId) throws Exception {

        // Giả định caller đã được xác thực và được phân quyền
        // đối với tenant/object; đây không phải auth layer.
        SecretKey dek = newAes256Key();

        byte[] dataNonce = newNonce();
        Cipher dataCipher = Cipher.getInstance(CIPHER);
        dataCipher.init(Cipher.ENCRYPT_MODE, dek,
            new GCMParameterSpec(TAG_BITS, dataNonce));
        dataCipher.updateAAD(aad(
            "invoice-data-v1", trustedTenant,
            trustedObjectId, "AES-256-GCM"));
        byte[] ciphertext = dataCipher.doFinal(plaintext);

        // Chỉ local demo được phép lấy raw DEK bằng getEncoded().
        byte[] rawDek = dek.getEncoded();
        require(rawDek != null && rawDek.length == 32,
            "Demo DEK is not encodable");
        try {
            WrappedDek wrapped = wrap(
                rawDek, kek, approvedKekId,
                trustedTenant, trustedObjectId);
            return new Envelope(
                ENVELOPE_VERSION,
                trustedTenant, trustedObjectId,
                dataNonce, ciphertext, wrapped);
        } finally {
            Arrays.fill(rawDek, (byte) 0); // Best-effort.
        }
    }

    static byte[] decrypt(
            Envelope stored,
            SecretKey kek,
            String expectedKekId,
            String trustedTenant,
            String trustedObjectId) throws Exception {

        // So sánh ngữ cảnh với trusted authorization result,
        // không dùng giá trị chưa xác thực làm nguồn quyền.
        require(stored != null
                && stored.formatVersion() == ENVELOPE_VERSION
                && trustedTenant.equals(stored.tenantId())
                && trustedObjectId.equals(stored.objectId()),
            "Envelope not authorized for this resource");

        require(stored.dataNonce() != null
                && stored.dataNonce().length == NONCE_LENGTH,
            "Invalid data nonce");

        byte[] rawDek = unwrap(
            stored.wrappedDek(), kek, expectedKekId,
            trustedTenant, trustedObjectId);

        try {
            SecretKey dataKey = new SecretKeySpec(rawDek, "AES");
            Cipher dataCipher = Cipher.getInstance(CIPHER);
            dataCipher.init(Cipher.DECRYPT_MODE, dataKey,
                new GCMParameterSpec(TAG_BITS, stored.dataNonce()));
            dataCipher.updateAAD(aad(
                "invoice-data-v1", trustedTenant,
                trustedObjectId, "AES-256-GCM"));

            // Plaintext chỉ được trả nếu cả wrap tag và data tag
            // được xác thực thành công.
            return dataCipher.doFinal(
                stored.dataCiphertextAndTag());
        } finally {
            Arrays.fill(rawDek, (byte) 0); // Best-effort.
        }
    }

    static Envelope rewrap(
            Envelope original,
            SecretKey oldKek,
            String oldKekId,
            SecretKey newKek,
            String newKekId,
            String trustedTenant,
            String trustedObjectId) throws Exception {

        require(original != null
                && original.formatVersion() == ENVELOPE_VERSION
                && trustedTenant.equals(original.tenantId())
                && trustedObjectId.equals(original.objectId()),
            "Envelope not authorized for rewrap");

        // Chỉ lấy DEK ra để bọc lại; không Decrypt DATA.
        byte[] rawDek = unwrap(
            original.wrappedDek(), oldKek, oldKekId,
            trustedTenant, trustedObjectId);

        try {
            WrappedDek rewrapped = wrap(
                rawDek, newKek, newKekId,
                trustedTenant, trustedObjectId);

            // Same data nonce/tag/ciphertext references (demo).
            // Production cần defensive copies và atomic update.
            return new Envelope(
                original.formatVersion(),
                original.tenantId(), original.objectId(),
                original.dataNonce(),
                original.dataCiphertextAndTag(),
                rewrapped);
        } finally {
            Arrays.fill(rawDek, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        SecretKey kekV1 = newAes256Key();
        SecretKey kekV2 = newAes256Key();

        String tenant = "tenant-A";
        String object = "invoice-154";
        byte[] message = "demo-data-not-sensitive"
            .getBytes(StandardCharsets.UTF_8);

        Envelope before = encrypt(
            message, tenant, object, kekV1, "billing-kek-v1");

        byte[] readBefore = decrypt(
            before, kekV1, "billing-kek-v1", tenant, object);
        require(MessageDigest.isEqual(message, readBefore),
            "Initial decrypt mismatch");
        System.out.println("Encrypt and decrypt: PASS");

        Envelope after = rewrap(
            before,
            kekV1, "billing-kek-v1",
            kekV2, "billing-kek-v2",
            tenant, object);

        // Cùng data ciphertext, chỉ wrapped DEK được thay.
        require(Arrays.equals(
                before.dataCiphertextAndTag(),
                after.dataCiphertextAndTag()),
            "Rewrap unexpectedly changed data ciphertext");
        require(Arrays.equals(
                before.dataNonce(), after.dataNonce()),
            "Rewrap unexpectedly changed data nonce");

        byte[] readAfter = decrypt(
            after, kekV2, "billing-kek-v2", tenant, object);
        require(MessageDigest.isEqual(message, readAfter),
            "Decrypt after KEK rotation mismatch");
        System.out.println("KEK rewrap without data re-encrypt: PASS");

        try {
            decrypt(after, kekV2, "billing-kek-v2",
                "tenant-B", object);
            throw new AssertionError("Cross-tenant access was accepted");
        } catch (SecurityException expected) {
            System.out.println("Wrong tenant context: REJECTED");
        }

        byte[] tamperedData = after.dataCiphertextAndTag().clone();
        tamperedData[tamperedData.length - 1] ^= 1;
        Envelope tampered = new Envelope(
            after.formatVersion(),
            after.tenantId(), after.objectId(),
            after.dataNonce(), tamperedData, after.wrappedDek());

        try {
            decrypt(tampered, kekV2, "billing-kek-v2",
                tenant, object);
            throw new AssertionError("Tampering was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Modified data authentication tag: REJECTED");
        }

        // Không in raw KEK, DEK hoặc decrypted production data.
    }
}
~~~

Kết quả kỳ vọng:

~~~text
Encrypt and decrypt: PASS
KEK rewrap without data re-encrypt: PASS
Wrong tenant context: REJECTED
Modified data authentication tag: REJECTED
~~~

### 12.1. Những nguyên tắc ví dụ thể hiện đúng

- **DEK và KEK là hai khóa khác nhau**: một khóa mã hóa dữ liệu, khóa còn lại bảo vệ bytes của DEK.
- **Hai nonce độc lập**: data nonce và wrap nonce được sinh cho những phép Encrypt khác nhau.
- **Hai AAD domains độc lập**: invoice-data-v1 và wrap-dek-v1, tránh dùng lẫn purpose.
- **Tenant/object binding**: người gọi phải cung cấp trusted context khớp envelope.
- **Key ID kiểm tra trước Unwrap**: không tự chọn mọi key theo metadata chưa xác minh.
- **Authenticated encryption ở cả hai tầng**: tag sai làm thao tác Decrypt thất bại.
- **Rewrap giữ nguyên data ciphertext**: thay wrapped DEK và KEK reference, không đọc plaintext data.
- **Không in bí mật**: output chỉ có trạng thái thử nghiệm.
- **Giảm thời gian tồn tại raw DEK**: xóa best-effort các mảng do ứng dụng trực tiếp nắm.

### 12.2. Giới hạn lớn cần hiểu trước khi áp dụng

**Đây là ví dụ học tập, không phải production encryption library.**

1. **KEK tồn tại raw trong JVM** và được tạo bằng KeyGenerator; với hệ thống nhạy cảm nên đưa KEK vào KMS/HSM không xuất được.
2. **DEK được lấy qua getEncoded()** để wrap local. SecretKeySpec và provider có thể **sao chép vật liệu**; Arrays.fill không bảo đảm xóa hết mọi bản sao trong heap/native memory.
3. **Records chứa byte[] mutable** và rewrap dùng chung references; production phải defensive copy/immutable payload, kiểm tra kích thước dữ liệu và serialization.
4. **SecureRandom với nonce 96-bit** chỉ minh họa số ít phép mã hóa. Một KEK wrap rất nhiều DEKs cần **nonce allocation strategy, usage limits và collision-risk management**, đặc biệt khi nhiều instance.
5. **Không có IAM/KMS thật** hoặc authentication cho actor. Biến trustedTenant/trustedObjectId phải đến từ kết quả xác thực và kiểm tra quyền nghiệp vụ.
6. **Không có version/anti-replay ledger**: attacker có thể phát lại một envelope cũ hợp lệ trừ khi có state/sequence và rollback protection.
7. **Không có crash consistency/transaction atomicity** giữa cập nhật wrapped DEK và key metadata trong database.
8. **Không có multi-region key migration** hoặc backup/restore được kiểm tra.
9. **Không chứng minh key CSPRNG entropy tuyệt đối** hay HSM attestation; chỉ trình diễn primitive trong một đường thực thi.
10. **Không giới hạn số lượng key operations** và không áp dụng rate limits/quota/monitoring.
11. **Một DEK per-object** giúp mô hình nonce data đơn giản hơn nhưng chưa tự đảm bảo các điều kiện nếu cùng DEK được dùng lại ở nơi khác.
12. **Không dùng Exception fallback**: nếu tag sai thì từ chối, không chuyển sang ECB/CBC hoặc thử một danh sách key trái phép.

Nếu sử dụng KMS thật, nên thay hai hàm **wrap/unwrap** bằng provider SDK và policy/context phù hợp; không nên xuất KEK vào JVM chỉ để tương thích chữ ký hàm của demo.

## 13. Thiết kế KMS/HSM thật: quản lý KEK mà không phát raw KEK

### 13.1. Một luồng GenerateDataKey phổ biến

~~~text
Ứng dụng -> KMS:
  GenerateDataKey(approvedKekRef, keySpec, encryptionContext)

KMS -> Ứng dụng:
  PlaintextDEK (chỉ giữ trong RAM theo policy)
  EncryptedDEK / wrapped key blob

Ứng dụng:
  AES-GCM Encrypt(data, PlaintextDEK, nonce, AAD)
  Persist(ciphertext, nonce/tag, EncryptedDEK, key metadata)
  Hạn chế thời gian giữ PlaintextDEK
~~~

Các API và thông số cụ thể tùy nhà cung cấp. Có provider cho phép chọn số bit DEK, có provider cung cấp một opaque encrypted data key và yêu cầu context khớp khi decrypt. Không giả định API nào cũng có cùng semantics.

### 13.2. Quyền cần tối thiểu

- **Writer-only service:** có thể cần GenerateDataKey/Encrypt, nhưng không nhất thiết cần Decrypt mọi wrapped DEK lịch sử.
- **Reader service:** có thể cần Unwrap/Decrypt đúng KEK, với authorization trên resource.
- **Rotation worker:** chỉ cần các quyền rewrap/migration thích hợp; hoạt động theo maintenance approval.
- **Custodian:** được quản lý KEK lifecycle, không mặc nhiên có quyền nhận plaintext DEK.
- **Administrator:** không được tự cấp quyền Decrypt rồi tự chỉnh/xóa audit.
- **Auditor:** đọc metadata, grants và logs có giới hạn, không cần raw key.

Các tên tác vụ trong API có thể khác: một hệ thống cloud gọi **Decrypt** để unwrap encrypted data key; một HSM cung cấp **UnwrapKey**. Rà soát **hành vi thật và effective permissions**.

### 13.2.1. Đường kiểm soát quyền trước khi Unwrap

~~~mermaid
flowchart LR
    U["Caller / workload identity"] --> B{"Business authorization tenant + object?"}
    B -->|"Không"| DENY["Reject trước KMS call"]
    B -->|"Có"| M["Trusted key mapping + context"]
    M --> IAM{"KMS IAM / key grants cho phép?"}
    IAM -->|"Không"| DENY
    IAM -->|"Có"| KMS["KMS/HSM Unwrap KEK"]
    KMS --> DEK["Plaintext DEK tạm trong authorized boundary"]
    DEK --> AEAD["AES-GCM data decrypt + expected AAD/tag"]
    AEAD --> P{"Authentication valid?"}
    P -->|"Không"| DENY
    P -->|"Có"| OUT["Return authorized plaintext"]
~~~

Sơ đồ này cho thấy **DEK được trả ra chỉ sau các kiểm tra quyền thích hợp** theo thiết kế, nhưng kiểm soát IAM vẫn phải được áp dụng ở KMS để ngăn các lời gọi trực tiếp bỏ qua business layer. Với API không trả plaintext DEK, thay nút DEK bằng thao tác giải mã nằm trong cryptographic module theo provider.

### 13.3. Context binding là quan trọng nhưng không phải authorization đầy đủ

Với KMS encryption context:

~~~json
{
  "service": "billing",
  "purpose": "invoice-dek-wrap",
  "tenant": "tenant-A",
  "environment": "production"
}
~~~

Ứng dụng phải lấy tenant và purpose từ trusted configuration/session/resource. Nếu principal được phép KMS Decrypt tất cả KEKs và có thể tự chọn tenant context, key service có thể vẫn trả DEK khi attacker chọn context trùng dữ liệu bị đánh cắp.

Cần đồng thời:

1. KMS IAM/key policy có key scope/conditions được phép.
2. Ứng dụng kiểm tra **principal → tenant → resource**.
3. Wrapped DEK được gắn context/metadata xác thực.
4. AES-GCM AAD-data gắn object/purpose chính xác.
5. Audit key usage, đặc biệt các lời gọi Decrypt/Unwrap bất thường.

### 13.4. Khi nào nên dùng HSM thay vì KMS managed?

Không có câu trả lời phổ quát. Xem xét:

- Yêu cầu pháp lý/tiêu chuẩn và **đặc tính module đã được đánh giá**.
- Ai chịu trách nhiệm hardware partition, firmware, quorum/ceremony và HA.
- Khả năng **non-exportable KEK**, wrapping algorithm và key attributes.
- Cách kiểm soát **grants, SoD và audit** ở nền tảng.
- Availability/latency/quota và chi phí vận hành.
- Backup/restore, region replication, disaster recovery.
- Khả năng chuyển nhà cung cấp và crypto-agility.

Một HSM đặt tại chỗ **không tự an toàn hơn mọi KMS** nếu người quản trị có quyền quá rộng hoặc recovery process không kiểm soát. Nên ưu tiên **mô hình có thể chứng minh quyền, ranh giới và khả năng khôi phục**.

## 14. Lựa chọn granularity: hiệu năng, số thao tác KMS và caching

Tách KEK/DEK giúp xử lý dữ liệu nhanh nhưng vẫn có trade-off giữa chi phí, throughput, IAM và blast radius.

### 14.1. So sánh ba mô hình

| Kiến trúc | Số lần cần key operations | Điểm mạnh | Điểm cần kiểm soát |
| --- | --- | --- | --- |
| **DEK mỗi object, KEK mỗi tenant/service** | Có thể 1 wrap khi ghi và 1 unwrap khi đọc, trước caching | Blast radius dữ liệu nhỏ và key ownership rõ | KMS quotas, latency, nhiều metadata, audit volume |
| **DEK mỗi batch** | Giảm tần suất wrap/unwrap | Hiệu năng tốt khi xử lý lô | Nonce management, usage limits, blast radius batch |
| **DEK một thời gian rồi cache/reuse** | Giảm KMS roundtrips | Throughput cao | Cache lifecycle, DEK exposure, revoke lag, nonce reuse |

**Không có “KMS call mỗi byte dữ liệu”.** Các luồng local AES-GCM xử lý bulk ciphertext; KMS bảo vệ key material. Nhưng nhu cầu Unwrap mỗi read có thể tạo bottleneck nếu thiếu thiết kế cache/throughput.

### 14.2. Cache plaintext DEK: chỉ khi có chính sách

Caching có thể giảm latency nhưng tăng:

- Thời gian raw DEK tồn tại trong RAM.
- Số requests/records mà attacker có thể đọc khi chiếm process.
- Độ trễ của **revocation**: disable KMS grant không xóa key đã cache.
- Nguy cơ log/dump/heap snapshot làm lộ nhiều DEKs.
- Bất cập khi key/tenant/access state thay đổi mà cache vẫn coi key hợp lệ.

Nếu được phép cache, cần **TTL, max size, tenant/key segregation, invalidation, secure memory handling, audit và incident response**. Không cache KEK raw ở ứng dụng chỉ để tiết kiệm KMS calls khi policy yêu cầu non-exportable.

### 14.3. KMS outage và fail-closed

Một KMS tạm ngừng có thể khiến ứng dụng không unwrap được DEK mới. Không nên:

- Chuyển sang **một hard-coded fallback KEK**.
- Ghi plaintext xuống storage để “chờ mã hóa sau”.
- Bỏ xác thực AAD/tag khi KMS lỗi.
- Mở IAM cho role khác không được phê duyệt.
- Dùng plaintext DEK cache vô hạn không theo policy.

Cần thiết kế **retry/backoff, circuit breaker, HA/multi-region hỗ trợ, rate limits, degraded mode được phân tích, recovery runbook** và cách phản hồi lỗi an toàn. Một số dịch vụ có thể tạm từ chối write/read thay vì hạ cấp bảo mật.

### 14.4. Streaming và file lớn

DEK-per-file thường hợp lý cho object lớn nhưng cần xử lý chunk:

- Mỗi chunk có **nonce riêng** hoặc construction được thiết kế theo chỉ số chunk.
- Xác thực **chunk index, file ID, total length/manifest** để ngăn hoán đổi, cắt bớt hoặc phát lại chunk.
- Giới hạn kích thước, số chunk và số lần dùng DEK.
- Không áp dụng một AES-GCM nonce cho toàn bộ những lời gọi Encrypt độc lập.
- Không cho ứng dụng dùng plaintext chunk chưa được xác thực.

Nếu cần xử lý dữ liệu lớn an toàn, ưu tiên **streaming AEAD protocol/library được đánh giá**, không tự ghép nhiều tag rồi mặc định chúng bảo vệ thứ tự và tính hoàn chỉnh của file.

## 15. Lifecycle: ai rotate và ai giữ được khả năng giải mã lịch sử?

~~~mermaid
flowchart LR
    GEN["Create approved KEK"] --> ACT["Activate for Wrap new DEKs"]
    ACT --> USE["Wrap/Unwrap trong approved scope"]
    USE --> ROT{"Rotate due / compromise?"}
    ROT -->|"Định kỳ"| NEW["New KEK version"]
    NEW --> RW["Rewrap DEKs và lưu đúng metadata"]
    RW --> LEG["Old KEK: legacy unwrap/restore only"]
    LEG --> CHECK["Inventory dependencies + backup restore test"]
    CHECK -->|"Đã giải quyết"| DEST["Approve controlled deletion"]
    ROT -->|"Compromise"| INC["Contain + assess exposure + rekey"]
    INC --> NEW
~~~

### 15.1. Tách cryptoperiod theo operation

Một KEK có thể không còn được **Wrap mới** sau rotation nhưng vẫn cần **Unwrap** những DEKs cũ cho đến khi migration/retention kết thúc. Điều này cần policy của hệ thống, không phải provider nào cũng hỗ trợ state **decrypt-only** native.

Tương tự, DEK đã thôi tạo bản mã mới có thể được giữ để đọc dữ liệu cũ theo thời hạn. **Không nhầm rotation với destruction**.

### 15.2. Từ Create đến Destroy

| Giai đoạn | KEK | DEK |
| --- | --- | --- |
| **Generation** | Sinh/import trong KMS/HSM approved boundary | CSPRNG/KMS per object/batch |
| **Provision/registration** | Owner/custodian, allowed operations, rotation và recovery | Gắn purpose/object/tenant/metadata, lưu wrapped form |
| **Active use** | Wrap/Unwrap theo IAM/context và audit | Encrypt/Decrypt data bằng AEAD |
| **Rotation** | Rewrap DEKs dưới KEK mới | Re-encrypt dữ liệu nếu thay DEK |
| **Revocation/disable** | Chặn key usage hoặc principal; đánh giá cache | Ngừng dùng raw DEK, thay dữ liệu/key nếu cần |
| **Backup/restore** | Giữ đường Unwrap đúng version và quorum | Wrapped DEK/ciphertext/context còn nguyên |
| **Destroy** | Sau dependency check + approval | Khi không còn dữ liệu cần giải hoặc theo cryptographic erasure policy |

### 15.3. Quy trình rewrap production có khả năng khôi phục

1. **Inventory** mọi wrapped DEKs dưới KEK cũ, gồm backups và offline archives nếu cần.
2. **Tạo KEK mới** trong provider/boundary được duyệt.
3. **Giới hạn migration principal** theo key IDs/operations, time-bound và audit.
4. **Rewrap** từng DEK bằng KMS nội bộ nếu hỗ trợ, không làm lộ raw DEK không cần thiết.
5. **Ghi atomic metadata:** version, wrapped blob, context, status/checkpoint.
6. **Xác minh** dữ liệu vẫn Decrypt được dưới KEK mới bằng test được phê duyệt.
7. **Retry idempotent:** nếu job dừng giữa chừng, có thể tiếp tục mà không phá records.
8. **Quản lý concurrent writes:** dữ liệu mới bắt đầu dùng KEK mới theo cutover plan; tránh writer viết lại key cũ sau scan.
9. **Giữ old KEK** ở trạng thái legacy được kiểm soát đến khi rollback/backup dependencies giải quyết.
10. **Restore test** với snapshots đại diện, có owner/custodian/auditor sign-off trước destroy.

### 15.4. Không phá tính nhất quán khi rewrap

Nếu storage cập nhật wrapped DEK **không đồng bộ** với key reference, crash giữa hai thao tác có thể khiến envelope trỏ tới KEK mới nhưng blob còn dưới KEK cũ.

Giải pháp có thể gồm:

- Transaction ghi **wrappedDEK + key version + migration marker** atomically.
- Versioned envelope và compare-and-swap.
- Double-write hoặc giữ old/new wrapped blobs trong giai đoạn chuyển tiếp có kiểm soát.
- Checkpoint, retry, verification và cleanup sau cutover.
- Backup/migration evidence có integrity và thời hạn.

Không chọn giải pháp chỉ vì “backup có ciphertext”, vì **metadata/wrapped DEK bị sai** cũng đủ làm mất dữ liệu.

## 16. Backup, disaster recovery và cryptographic erasure

### 16.1. Thành phần cần để khôi phục

~~~text
Backup data có:
  Data ciphertext + data nonce/tag + AAD/format version
  Wrapped DEK + wrapping context + KEK ID/version
  Trusted mapping/registry và quyền Unwrap
  KEK material còn sống trong KMS/HSM hoặc recovery path được phê duyệt
~~~

**Không nhất thiết cần raw DEK trong backup**, vì wrapped DEK có thể được lưu cùng ciphertext. Nhưng phải đảm bảo **KEK và key metadata** tương ứng còn khôi phục được.

### 16.2. Trường hợp backup giải mã thất bại

- KEK đã bị destroy trước khi hết retention.
- Key ID/alias bị mất hoặc trỏ sai region/version.
- Encryption context khi restore khác context lúc wrap.
- Wrapped DEK/tag bị sửa hoặc không thuộc key được chọn.
- Nonce/tag/AAD của data layer không được lưu.
- Recovery operator bị thu hồi mọi quyền mà không có break-glass được quản lý.
- Backup chỉ lưu ciphertext nhưng không lưu wrapped DEK.
- Quá trình rewrap ghi một nửa metadata rồi crash.

**Restore test phải thực sự giải mã và xác thực dữ liệu test**, không chỉ xác nhận backup tồn tại hoặc hash khớp.

### 16.3. Crypto-shredding không đơn giản là DeleteKey

Một số hệ thống dùng **cryptographic erasure**: nếu không thể khôi phục DEK/KEK cuối cùng dùng giải mã dữ liệu, ciphertext trở nên không thể giải trong giả định thuật toán/khóa còn an toàn.

Nhưng cần kiểm tra:

- Có **bản sao KEK/DEK** trong KMS replicas, backup vault, escrow, cache, dumps hoặc logs không?
- Có **bản wrapped DEK cũ** và raw KEK cũ đã bị sao chép không?
- Dữ liệu có từng được lưu plaintext ở search index, replica hoặc export không?
- KMS provider có lifecycle/pending deletion và retention của backup key material nào?
- Một KEK dùng chung nhiều DEKs có ảnh hưởng dữ liệu khác không được phép xóa không?
- Có yêu cầu pháp lý/hợp đồng giữ data hoặc key không?

**Xóa KEK dùng chung để xóa một bản ghi có thể vô tình làm mất khả năng đọc hàng triệu bản ghi khác.** Nếu cần xóa mật mã theo từng object, DEK per-object và quản lý bản sao/key dependencies chặt chẽ sẽ hữu ích hơn; vẫn phải đánh giá nơi data/keys có thể tồn tại.

## 17. Audit và key inventory: separation phải nhìn thấy được

### 17.1. Bản ghi key inventory tối thiểu

~~~yaml
kekId: billing-kek-v3
keyClass: KEK
service: billing
environment: production
tenantScope: tenant-A
providerReference: "kms://account/region/opaque-key-ref"
origin: KMS_GENERATED
approvedWrappingProfile: APPROVED-KMS-WRAP
state: ACTIVE
ownerRole: billing-platform
custodianRole: crypto-operations
cryptoperiodPolicyRef: "policy/billing-kek"
allowedOperations:
  - WRAP
  - UNWRAP
rotationDueRef: "schedule/approved-rotation"
dependencyIndexRef: "inventory/wrapped-dek-index"
recoveryPolicyRef: "policy/billing-recovery"
auditRef: "evidence-store://key-operations"
~~~

Inventory chỉ lưu **metadata và references**, không phải raw KEK/DEK. DEK có thể được ghi nhận gián tiếp qua **object ID, wrapped DEK reference, KEK version** mà không cần tạo một bản ghi chi tiết riêng cho mọi DEK nếu quy mô rất lớn; quan trọng là có thể đối soát dependencies.

### 17.2. Những sự kiện cần audit

| Sự kiện | Evidence hữu ích |
| --- | --- |
| **Create/Import KEK** | Key ID, origin, algorithm, owner/custodian, approval |
| **GenerateDataKey/Wrap** | Workload, key ID/version, timestamp, result, context metadata an toàn |
| **Unwrap/Decrypt** | Principal, operation, key, result, request ID, anomalous volume |
| **Grant/KeyPolicy change** | Principal, before/after, approver, change ticket |
| **Rotate/Rewrap** | Old/new KEK, number of updated envelopes, errors, checkpoint |
| **Re-encrypt DEK/data** | Object version, old/new DEK references, result |
| **Backup/Restore** | Recovery test results và key dependencies |
| **Disable/Revoke/Destroy** | Reason, approvals, state transition, dependency check |
| **Exception/Break-glass** | Scope, risk owner, expiry, post-use review |

**Không log raw DEK/KEK, passwords, recovery shares, plaintext sensitive data hoặc TLS traffic secrets**. KMS context thường không bí mật, nhưng có thể xuất hiện trong audit và tiết lộ tenant/object metadata nên cũng cần kiểm soát quyền và tối thiểu hóa.

### 17.3. Separation of duties

- **Key owner** quyết định purpose/risk/retention.
- **Key custodian** giám hộ KEK lifecycle/recovery theo runbook.
- **Key admin** thực thi policy/grants nhưng không được tự đọc mọi dữ liệu.
- **Application owner** chịu trách nhiệm business authorization, AEAD format và key usage trong code.
- **Security reviewer/auditor** đánh giá IAM/key inventory/audit và xác nhận closure độc lập.
- **Risk approver** chấp nhận ngoại lệ với phạm vi, thời hạn và compensating controls.

Với root/KEK rủi ro cao có thể cần **dual control, HSM quorum và split knowledge** khi thích hợp. Không nhầm dual approval với cơ chế phân chia key material m-of-n.
## 18. Tình huống thực tế A: đổi KEK mà không cần mã hóa lại 10 triệu bản ghi

### 18.1. Bối cảnh

BillingService có 10 triệu hóa đơn. Mỗi hóa đơn dùng **DEK riêng**; mọi DEKs được wrap bằng **KEK-v1** trong KMS. Theo lịch rotation, tổ chức cần chuyển sang **KEK-v2**.

Phương án sai là giải mã và mã hóa lại cả 10 triệu hóa đơn dù **DEKs chưa bị lộ** và AES-GCM data ciphertext vẫn đáp ứng policy. Phương án đó tạo áp lực I/O, tăng thời gian plaintext tồn tại và có nguy cơ gây gián đoạn không cần thiết.

### 18.2. Phương án rewrap có kiểm soát

1. Tạo KEK-v2 đúng profile trong KMS, xác minh key state/attributes/IAM.
2. Chuyển **new writes** sang wrap bằng KEK-v2 sau khi application readiness đạt.
3. Di chuyển từng envelope cũ: KMS unwrap/rewrap DEK của hóa đơn bằng API không xuất DEK nếu provider hỗ trợ.
4. Ghi **wrapped DEK mới, KEK reference/version và migration marker** atomically.
5. Giữ **data ciphertext/nonce/tag** không đổi.
6. Test decrypt mẫu có rủi ro cao, phát hiện lỗi ngữ cảnh hoặc metadata.
7. Theo dõi số bản ghi thành công/thất bại, đảm bảo rerun idempotent.
8. Kiểm kê old backups/archives còn phụ thuộc KEK-v1.
9. Thử restore đủ nguồn, chỉ deprecate rồi destroy KEK-v1 khi dependency review cho phép.

### 18.3. Điều kiện quyết định

**Chọn rewrap** khi muốn đổi lớp bảo vệ DEK mà **không cần đổi chính DEK**, và KEK-v1 không có dấu hiệu raw compromise làm nguy hiểm những bản wrapped DEK đã bị sao chép.

Nếu root/KEK-v1 bị lộ cùng dữ liệu được bảo vệ, chỉ rewrap database hiện tại **không khắc phục những bản copy lịch sử**. Khi đó incident team phải đánh giá liệu cần **re-encrypt bằng DEKs mới** và xử lý dữ liệu đã bị lộ.

## 19. Tình huống thực tế B: KMS non-exportable nhưng service account bị cấp Decrypt quá rộng

### 19.1. Bối cảnh

PaymentService dùng KEK trong HSM để wrap DEKs. KEK non-exportable và chưa từng có bằng chứng raw key bị xuất. Một service account phục vụ báo cáo lại có quyền **KMS Unwrap/Decrypt** nhiều KEKs ngoài nhiệm vụ.

### 19.2. Vì sao KEK tách khỏi DEK chưa đủ?

Nếu attacker chiếm credential của service account, họ có thể:

- Gọi KMS để unwrap nhiều encrypted DEKs.
- Dùng plaintext DEK nhận về để giải mã ciphertext đã lấy từ database/backups.
- Lách application business authorization nếu họ gọi KMS trực tiếp bằng quyền rộng.
- Tạo nhiều requests qua thời gian trong khi raw KEK vẫn luôn nằm trong HSM.

Do đó **non-exportable bảo vệ raw KEK**, không tự bảo vệ **quyền sử dụng KEK**.

### 19.3. Ứng phó

- Thu hồi/giới hạn grant theo approved scope và chặn credential đáng ngờ.
- Đối soát IAM effective permission bao gồm nhóm, assumed roles, resource-based grants, cross-account.
- Kiểm tra audit KMS Unwrap/Decrypt, tập key IDs, thời điểm và principal.
- Đánh giá ciphertext/DEKs đã bị truy cập và có cần re-encrypt không.
- Thêm test DENY/least privilege trước khi cấp quyền trong CI/IaC.
- Tách key admin khỏi workload có quyền dữ liệu, triển khai time-bound grants khi phù hợp.
- Nếu có dấu hiệu misuse đang diễn ra, kích hoạt **incident response ngay**, không đợi access review định kỳ.

**Không chỉ rotate KEK nếu grants trên KEK-v2 vẫn quá rộng**; phải sửa đường cấp quyền.

## 20. Tình huống thực tế C: tenant B sao chép envelope của tenant A

### 20.1. Bối cảnh

Hai tenant dùng cùng KEK của một ứng dụng vì lý do vận hành; mỗi record có DEK riêng. Một attacker của tenant B sao chép từ storage một envelope thuộc tenant A và thử gửi nó vào API của B.

Nếu ứng dụng chỉ đọc key ID trong envelope và gọi KMS Unwrap, rồi giải mã dưới DEK, nó có thể tiết lộ dữ liệu của A. Một KEK dùng chung không tự ràng buộc tenant identity.

### 20.2. Lớp kiểm soát cần có

~~~text
Authenticated caller tenant = B
Requested object belongs to tenant = A
                   |
                   v
Business authorization: DENY
                   |
          Không gọi KMS Unwrap
~~~

Ngay cả khi API có route chưa đủ business checks, **wrap context/AAD** và **data AAD** nên ràng buộc tenant/object/purpose từ nguồn đáng tin:

- Wrap có context **tenant A / object X**, không tự cho tenant B đổi sang context B.
- Data ciphertext có AAD **tenant A / object X**; sai context dẫn đến tag failure.
- KEK selection/mapping được kiểm soát, không lấy vô điều kiện từ user-supplied header.
- IAM giảm khả năng principal B dùng KEK/operations trên scope A.

### 20.3. Điều cần tránh

Không nói “chúng tôi có AAD nên không cần kiểm tra quyền”. AAD có thể xác nhận dữ liệu ràng buộc với context A, nhưng caller có thể khai context A nếu API không kiểm tra **principal→resource**. Phải có cả **authorization** và **cryptographic binding**.

## 21. Tình huống thực tế D: backup đúng checksum nhưng KEK đã bị xóa

### 21.1. Bối cảnh

Đội lưu trữ bảo vệ file bằng DEKs per-file và KEK-v1. Sau rotation sang KEK-v2, job kiểm tra chỉ nhìn các object hiện tại. Một kho offline backup vẫn chứa wrapped DEKs dưới KEK-v1. Quá trình destroy KEK-v1 hoàn tất và không còn recovery copy nào phù hợp.

### 21.2. Hậu quả

- Ciphertext trong backup còn nguyên, checksum khớp.
- Wrapped DEKs vẫn tồn tại, nhưng không còn **đường unwrap hợp lệ**.
- Không thể lấy DEK để decrypt file, dù AES-256-GCM chưa bị phá.
- Nếu đây là bản sao duy nhất, dữ liệu có thể bị mất vĩnh viễn.

### 21.3. Biện pháp phòng ngừa

- Duy trì dependency index giữa **KEK version, wrapped DEK, dataset và backup retention**.
- Chạy restore test với bản backup tiêu biểu trước destruction.
- Lập kế hoạch rewrap/re-encrypt bao gồm offline snapshots.
- Không để một người tự yêu cầu, thực thi và xác nhận hủy KEK cấp cao.
- Đưa pending deletion của KMS vào hệ thống cảnh báo.
- Kiểm tra khả năng recovery/quorum và credential lifecycle.

Điểm học được: envelope encryption cung cấp **confidentiality và flexibility**, nhưng nếu quản lý vòng đời sai, nó có thể trở thành nguyên nhân mất **availability**.

## 22. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| **Cùng một raw key là DEK và KEK** | Lẫn mục đích, tăng blast radius, rotation khó | Sinh hai khóa riêng và tách usage |
| **Một DEK toàn hệ thống** | Lộ một key có thể đọc dữ liệu mọi tenant | Chọn granularity theo object/batch/tenant |
| **Dùng KEK mã hóa toàn bộ data trực tiếp** | Tải KMS cao, khó phân tầng và usage scopes | Dùng DEK cho bulk data, KEK cho key material |
| **Wrap DEK bằng AES-ECB/CBC trần** | Thiếu integrity/key wrapping semantics | KMS wrapping hoặc AES-KW/KWP/AEAD được phê duyệt |
| **AES-GCM nonce-wrap lặp dưới KEK** | Rủi ro bí mật và integrity với key blob | Nonce allocation, usage limit và provider strategy |
| **Rewrap được coi là re-encrypt dữ liệu** | Đánh giá sai rủi ro raw DEK compromise | Phân biệt KEK rotation với DEK replacement |
| **Không lưu KEK version** | Không biết key nào mở wrapped DEK | Versioned envelope và trusted registry |
| **Tin keyId từ client** | Chọn nhầm KEK hoặc cross-tenant | Resolve từ trusted policy và resource |
| **AAD-data không ràng buộc object** | Hoán đổi ciphertext qua resource | Canonical AAD với tenant/object/purpose |
| **KMS context chứa password/token** | Secret có thể lộ qua logs | Context không bí mật, giảm dữ liệu |
| **GCM tag fail rồi thử fallback** | Fail-open/downgrade | Reject, migrate legacy theo policy độc lập |
| **Cấp Decrypt mọi KEK cho mọi app** | Lạm dụng KMS để lấy DEKs | Least privilege và access review |
| **KEK non-exportable nên không cần audit** | API misuse không được phát hiện | Audit Unwrap/Decrypt và anomaly alerts |
| **Lưu raw DEK trong database/log** | Database/log compromise thành raw key compromise | Chỉ wrapped DEK, hạn chế RAM/dump |
| **Cache DEK vô hạn** | Revocation chậm, tăng key exposure | Bounded TTL, invalidation, policy |
| **Rewrap chỉ cập nhật blob, không cập nhật version** | Mất khả năng mở dữ liệu khi crash | Atomic envelope update |
| **Destroy KEK ngay sau rotation** | Backup cũ không thể restore | Dependency check + restore tests |
| **Dùng KEK deletion để xóa một record** | Có thể phá nhiều records khác | DEK-per-object và crypto-erasure policy |
| **Bỏ qua replay/rollback** | Envelope cũ hợp lệ thay state mới | Version ledger/idempotency và state checks |
| **Nghĩ KEK/DEK đủ chống attacker đã có plaintext** | Đánh giá sai incident impact | Xử lý exfiltration và key usage/material compromise |

## 23. Checklist triển khai KEK tách khỏi DEK

### Thiết kế và key generation

1. Có phân biệt rõ **DEK mã hóa data** và **KEK bọc DEK**?
2. DEK/KEK được sinh bằng **CSPRNG/KMS/HSM** phù hợp, không reuse raw key?
3. Key type, size, algorithm, wrapping profile và purpose có policy được duyệt?
4. DEK granularity (object/batch/tenant) có được chọn theo threat model?
5. KEK lưu trong ranh giới bảo vệ phù hợp, non-exportable khi yêu cầu?
6. Có quy định use case nào được dùng KMS GenerateDataKey trả plaintext DEK?
7. Có kiểm soát raw DEK trong RAM/heap dumps/logging/metrics?
8. Không dùng ECB hay CBC không xác thực để wrap DEK?
9. Nếu dùng AES-GCM cho wrap, nonce uniqueness dưới KEK được thiết kế?
10. Nếu dùng AES-GCM cho data, nonce uniqueness dưới DEK được thiết kế?

### Envelope, context và authorization

11. Có lưu **data ciphertext, data nonce, tag** đầy đủ?
12. Có lưu **wrapped DEK**, key ID/version và wrapping algorithm/context cần thiết?
13. Có ràng buộc **tenant, object, purpose và schema version** bằng AAD phù hợp?
14. AAD và encryption context có canonical encoding, version rõ?
15. Key resolver dùng **trusted registry**, không dùng key ID tùy ý từ client?
16. Có kiểm tra principal→tenant→resource trước KMS Unwrap?
17. KMS grants giới hạn principal, key ID và operation?
18. Quyền **ChangePolicy/CreateGrant** có SoD và audit?
19. KMS encryption context không bị nhầm với business authorization?
20. Không đưa raw secrets hoặc PII không cần thiết vào context/AAD?
21. Authentication tag failure luôn **fail closed**, không fallback unsafe?
22. Có anti-replay/rollback khi object/version nghiệp vụ cần tính mới?

### Rotation và vòng đời

23. Có phân biệt **KEK rewrap** và **DEK re-encrypt**?
24. Khi rotate KEK, migration có atomic update của blob + reference/version?
25. Có checkpoint, retry, idempotency và concurrent-write cutover?
26. Có inventory dependencies cho KEK versions và wrapped DEKs?
27. Old KEK có thể Unwrap lịch sử theo policy trong thời gian cần thiết?
28. Trước destroy KEK có dependency review, approval và restore tests?
29. Khi DEK đã lộ, có kế hoạch **thay DEK và re-encrypt**?
30. Khi KEK đã lộ, có đánh giá cả old wrapped blobs đã bị sao chép?
31. Khi IAM bị lạm dụng, có audit và đánh giá dữ liệu/DEK đã được unwrap?
32. Cryptoperiod, owner/custodian và key states có được review định kỳ?

### Vận hành, backup và audit

33. Có cơ chế giới hạn DEK cache và revoke lag?
34. KMS/HSM outage có degraded mode an toàn, không plaintext fallback?
35. Restore test bao gồm **KEK access + wrapped DEK + data metadata**?
36. Recovery shares/quorum/operator roles có được quản lý và kiểm tra bàn giao?
37. Không dùng shared KEK deletion để xóa một record ngoài blast radius?
38. Audit KMS Wrap/Unwrap, grants, rotation và deletion có integrity?
39. Evidence/logs không chứa raw KEK/DEK/private key, plaintext nhạy cảm?
40. Có negative tests cho sai tenant, tag, key reference và key state?
41. Có monitor quyền Decrypt/Unwrap bất thường và key usage volume?
42. Có xác minh ciphertext sau rewrap vẫn không đổi mà vẫn Decrypt được?
43. Có data format/algorithm version cho migration, không algorithm downgrade?
44. Có trách nhiệm rõ giữa key owner, custodian, administrator và auditor?
45. Khi đổi provider/region có kế hoạch key portability/recovery và IAM tương ứng?

## 24. Câu hỏi tự kiểm tra

**Câu 1.** KEK và DEK khác nhau ở đâu?

**Đáp án:** DEK **Encrypt/Decrypt dữ liệu**, còn KEK **Wrap/Unwrap DEK**. Chúng là hai vật liệu khác nhau, có mục đích, quyền và vòng đời riêng. Cả hai có thể là AES key nhưng không nên là cùng một raw key.

**Câu 2.** Vì sao không tạo một KEK riêng cho từng bản ghi rồi dùng nó trực tiếp mã hóa data?

**Đáp án:** Có thể có use case quản lý trực tiếp payload nhỏ trong KMS, nhưng với bulk data cách này thường tốn KMS calls, quota, latency và làm mờ mục đích khóa. Envelope encryption cho phép **ít KEKs bảo vệ nhiều DEKs**, trong khi ứng dụng dùng DEK cho dữ liệu.

**Câu 3.** Database chứa ciphertext và wrapped DEK. Nếu attacker chỉ sao chép database, họ có thể tự unwrap được không?

**Đáp án:** Không chỉ từ hai blobs nếu KEK vẫn bí mật và thuật toán/implementation an toàn. Tuy nhiên attacker có thể lợi dụng **KMS grants, app credentials, metadata hoặc backup/KEK compromise**; phải bảo vệ cả quyền và môi trường.

**Câu 4.** Một KEK non-exportable có thể bị lạm dụng không?

**Đáp án:** Có. Principal có quyền **KMS Unwrap/Decrypt** có thể nhận plaintext DEK qua API tùy provider; non-exportable không đồng nghĩa không thể dùng khóa trái phép.

**Câu 5.** KEK rotation có luôn phải re-encrypt toàn bộ data không?

**Đáp án:** Không. **Rewrap** có thể bảo vệ lại cùng DEK dưới KEK mới, giữ data ciphertext/nonce/tag không đổi. Nếu DEK đã lộ hoặc risk assessment cần thay data key, phải **re-encrypt**.

**Câu 6.** KEK-v1 raw đã bị attacker lấy cùng old wrapped DEKs và ciphertext; rewrap dữ liệu hiện tại có đủ khắc phục không?

**Đáp án:** Không. Attacker có thể unwrap những bản DEKs cũ đã sao chép. Phải đánh giá **DEK/data impact**, có thể cần DEK mới và re-encrypt; rotation không thu hồi được dữ liệu đã bị sao chép.

**Câu 7.** DEK bị lộ nhưng KEK vẫn an toàn. Chỉ wrap lại DEK dưới KEK mới có đủ không?

**Đáp án:** Không. Attacker đã có DEK để giải mã ciphertext thuộc DEK đó. Cần thay **DEK** và bảo vệ lại dữ liệu tương ứng.

**Câu 8.** Có thể dùng cùng nonce-wrap cho các lần wrap khác nhau dưới một KEK AES-GCM không?

**Đáp án:** Không. **Nonce reuse dưới cùng GCM key** có thể phá bí mật và integrity. Mỗi tầng cần chiến lược nonce riêng theo khóa, quy mô và hạn mức.

**Câu 9.** KMS encryption context có thể thay business authorization không?

**Đáp án:** Không. Context có thể bảo vệ/ràng buộc thao tác wrap, nhưng ứng dụng vẫn phải kiểm tra **principal được phép truy cập tenant và object nào**. AAD của data ciphertext là cơ chế riêng.

**Câu 10.** Một envelope có tag đúng vẫn có thể bị replay không?

**Đáp án:** Có. Attacker có thể phát lại một envelope cũ vẫn xác thực hợp lệ. Nếu hệ thống cần tính mới, phải có **version/sequence/state ledger, idempotency hoặc anti-rollback**.

**Câu 11.** Vì sao key ID phải đi kèm version và trusted mapping?

**Đáp án:** Alias có thể đổi đích khi rotation; dữ liệu cũ cần mở bằng đúng key material. Nếu key reference do attacker tự chọn, có nguy cơ key confusion/cross-tenant.

**Câu 12.** Sau KEK rewrap, những byte nào có thể giữ nguyên?

**Đáp án:** Nếu DEK không đổi và không re-encrypt data, **data ciphertext, data nonce và data tag có thể giữ nguyên**. Thay đổi nằm ở **wrapped DEK, wrapping nonce/tag/context và KEK reference/version**.

**Câu 13.** Vì sao không xóa KEK-v1 ngay sau khi chuyển new writes sang KEK-v2?

**Đáp án:** Dữ liệu/backups cũ còn có thể chứa wrapped DEKs dưới KEK-v1. Cần dependency inventory, migration/rewrap, restore test và phê duyệt trước khi destroy.

**Câu 14.** DEK-per-object làm blast radius nhỏ hơn nhưng đổi lại điều gì?

**Đáp án:** Tăng wrapped key metadata và có thể tăng KMS calls/chi phí, dù có thể tối ưu bằng batching/caching theo chính sách. Nó thường giúp cô lập phạm vi lộ DEK và đơn giản hóa số lần dùng một DEK.

**Câu 15.** Có nên cache plaintext DEK vô hạn để không cần gọi KMS khi đọc?

**Đáp án:** Không. Cache kéo dài thời gian sống secret, làm tăng hậu quả khi chiếm ứng dụng và làm chậm revocation. Nếu được phép cache, cần TTL, limits, tenant isolation, invalidation và incident plan.

**Câu 16.** Backup hash/checksum khớp chứng minh backup decrypt được chưa?

**Đáp án:** Chưa. Phải giữ **wrapped DEK, KEK/version, KMS context, nonce/tag/AAD, trust/key registry và quyền restore** và thực hiện test giải mã.

**Câu 17.** Vì sao demo Java có thể dùng AES-GCM cho DEK wrap nhưng production nên cân nhắc KMS?

**Đáp án:** Demo cho thấy hai tầng AEAD dùng key/nonce/AAD riêng; nó giữ **raw KEK trong JVM** và không tự quản lý IAM/HSM/nonce usage ở quy mô lớn. KMS/HSM giúp giữ KEK trong security boundary và điều khiển Wrap/Unwrap theo quyền.

**Câu 18.** Nếu KMS outage, ứng dụng có được lưu plaintext tạm thay vì ciphertext không?

**Đáp án:** Không nên. Đây là fail-open làm mất bảo mật. Cần retry/backoff, HA hoặc từ chối thao tác theo degraded-mode policy đã phân tích; không được bỏ encryption.

**Câu 19.** KEK custodian có nhất thiết phải có quyền giải mã mọi hóa đơn không?

**Đáp án:** Không. Custodian có thể quản lý key lifecycle/backup/rotation mà không có **business authorization hoặc KMS Unwrap** dữ liệu. Cần separation of duties và review effective access.

**Câu 20.** Một hệ thống đã tách KEK–DEK có tự bảo đảm an toàn trước dữ liệu bị thay không?

**Đáp án:** Không. Cần **AEAD/tag verification, đúng nonce/AAD, trusted key mapping, IAM và authorization**, cùng rollback protection nếu cần. Tách tầng khóa là nền tảng của kiến trúc, không thay các kiểm soát còn lại.

## 25. Kết luận

**KEK tách khỏi DEK là nguyên tắc trọng tâm của envelope encryption.** DEK dùng để mã hóa dữ liệu, KEK dùng để bảo vệ DEK. Cách tổ chức này cho phép **giảm số nơi cần giữ khóa quản lý có giá trị cao, cô lập quyền, chọn granularity cho dữ liệu và xoay vòng KEK bằng rewrap mà không nhất thiết mã hóa lại toàn bộ ciphertext**.

Trong hệ thống Java, lớp ứng dụng phải xử lý **AES-GCM nonce, authentication tag, canonical AAD, tenant/resource authorization và raw DEK lifetime**. KMS/HSM nên quản lý KEK qua **key reference, IAM grants, wrapping operations, audit và recovery policy**. Mô hình **non-exportable** không xóa rủi ro **API misuse**; rotation KEK không thay thế **DEK re-encrypt** khi DEK hoặc dữ liệu cũ đã bị lộ.

**Phân tách KEK–DEK có giá trị khi cả vật liệu khóa, quyền sử dụng, vòng đời, metadata và bằng chứng kiểm soát đều được phân tách và quản lý nhất quán.**


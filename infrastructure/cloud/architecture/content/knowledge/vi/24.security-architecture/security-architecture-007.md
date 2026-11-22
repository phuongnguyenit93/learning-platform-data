# Mã hóa khi truyền, khi lưu và quản lý quyền giải mã

> **Chương:** Kiến trúc bảo mật  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai; cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt mã hóa khi truyền (in transit), mã hóa khi lưu (at rest) và mã hóa ở cấp ứng dụng/field.
2. Thiết kế TLS cho client, service-to-service, database, queue và kết nối quản trị; xác định điểm kết thúc TLS và ranh giới tin cậy.
3. Giải thích vai trò của certificate, trust chain, private key, CA, mTLS và vòng đời chứng chỉ.
4. Mô tả envelope encryption, DEK, KEK, KMS/HSM và cách bảo vệ dữ liệu ở database, object storage và backup.
5. Thiết kế quyền sử dụng key riêng cho encrypt/decrypt, tách vai trò vận hành và kiểm soát truy cập theo workload/tenant.
6. Lập kế hoạch tạo, lưu trữ, phân phối, xoay vòng, thu hồi, backup và hủy key; phân tích ảnh hưởng đến dữ liệu lịch sử.
7. Xác định rủi ro ở secret, log, cache, replica, snapshot và bản sao dữ liệu.
8. Kiểm chứng thiết kế bằng policy review, certificate/key rotation drill, access test và restore test.

## 1. Vì sao cần mã hóa trong kiến trúc cloud?

Ứng dụng cloud gửi dữ liệu qua nhiều ranh giới: trình duyệt tới gateway, gateway tới service, service tới database, producer tới broker, worker tới storage và dữ liệu được sao lưu sang vùng khác. Dữ liệu cũng tồn tại ở nhiều dạng: memory, file tạm, object, bảng database, snapshot, log, cache và bản backup.

Mã hóa giúp giảm khả năng đọc được dữ liệu khi kẻ tấn công nghe lén đường truyền, truy cập trái phép vào storage hoặc lấy được bản sao. Tuy nhiên, mã hóa **không tự xác thực người dùng, không tự cấp quyền, không ngăn ứng dụng hợp lệ đọc dữ liệu sai tenant và không bảo vệ plaintext sau khi đã được giải mã trong process**.

Một thiết kế cần trả lời ba câu hỏi:

- **Dữ liệu được bảo vệ ở đâu?** Trên network, storage, backup, field nhạy cảm hay khi xử lý?
- **Ai có thể giải mã?** Workload identity, role, service account hoặc con người nào có quyền dùng key?
- **Ai kiểm soát key?** Ai tạo, xoay, disable, revoke, khôi phục và hủy key?

### 1.1. Ba lớp bảo vệ thường gặp

| Lớp | Mục tiêu | Ví dụ |
|---|---|---|
| **Encryption in transit** | Bảo vệ dữ liệu khi di chuyển qua network | TLS giữa browser và API, mTLS giữa hai service |
| **Encryption at rest** | Bảo vệ dữ liệu khi lưu trên media | Database encryption, object storage encryption, encrypted backup |
| **Application/field-level encryption** | Bảo vệ giá trị khỏi các tầng lưu trữ hoặc nhóm truy cập rộng hơn | Mã hóa số định danh trước khi ghi database |

Các lớp bổ trợ nhau. TLS không bảo vệ file sau khi lưu; mã hóa đĩa không ngăn một role database hợp lệ query dữ liệu; field encryption không thay thế kiểm soát quyền đọc record.

### 1.2. Ranh giới và giới hạn

Giả sử client gọi Booking API, API ghi database, phát event và lưu bản sao:

- TLS có thể bảo vệ client → gateway và gateway → API.
- Kết nối database nên được mã hóa và xác thực server; có thể thêm client certificate nếu nền tảng hỗ trợ và threat model yêu cầu.
- Database/storage mã hóa at rest bằng key do dịch vụ quản lý hoặc key do tổ chức kiểm soát.
- Backup và replica phải nằm trong cùng phạm vi encryption, retention và access policy.
- Field chứa PII có thể được mã hóa trước khi ghi, nhưng cần thiết kế search/index và quản lý key tương ứng.
- Log/trace phải che dữ liệu nhạy cảm; mã hóa log không giải quyết việc quá nhiều người được quyền đọc log.

Khi ứng dụng cần xử lý dữ liệu, plaintext thường xuất hiện trong memory hoặc tại endpoint giải mã. Nếu cần bảo vệ cả dữ liệu trong lúc xử lý, phải đánh giá kỹ thuật khác như confidential computing/TEE, tokenization hoặc xử lý trên dữ liệu đã biến đổi; các kỹ thuật này có phạm vi và giới hạn riêng.

## 2. Mã hóa khi truyền: TLS và xác thực kết nối

### 2.1. TLS bảo vệ điều gì?

TLS (Transport Layer Security) thiết lập kênh truyền có bảo vệ mật mã giữa hai endpoint. Với cấu hình đúng, TLS cung cấp:

- **Confidentiality:** bên thứ ba trên đường truyền khó đọc nội dung.
- **Integrity:** phát hiện dữ liệu bị sửa đổi trong khi truyền.
- **Server authentication:** client xác minh server theo certificate và hostname.
- **Client authentication tùy chọn:** với mutual TLS, server cũng xác minh certificate của client.

TLS không xác minh người dùng được phép đặt booking nào, không tự ngăn replay ở tầng nghiệp vụ và không bảo vệ plaintext sau khi TLS kết thúc. Ứng dụng vẫn cần authentication, authorization, rate limit, input validation và audit.

### 2.2. TLS termination và các hop

Một request có thể đi qua nhiều điểm kết thúc TLS:

~~~mermaid
flowchart LR
    C[Browser / Mobile] ==>|TLS| EDGE[CDN / WAF / Load Balancer]
    EDGE ==>|TLS or mTLS| GW[API Gateway]
    GW ==>|TLS or mTLS| APP[Booking Service]
    APP ==>|TLS| DB[(Database)]
    APP ==>|TLS| MQ[Message Broker]
~~~

Mỗi đường là một kênh mã hóa riêng. Khi CDN/load balancer giải mã TLS, plaintext có thể tồn tại tại thành phần đó; mã hóa lại ở hop tiếp theo tạo một kênh mới, không biến toàn tuyến thành một TLS session duy nhất.

Cần xác định:

- TLS kết thúc ở đâu và thành phần nào có thể nhìn thấy plaintext?
- Backend hop có bắt buộc TLS hay gateway có thể gọi HTTP nội bộ?
- Ai cấp và gia hạn certificate cho từng listener/service?
- Hostname/SNI và hostname verification được kiểm tra ra sao?
- Header thể hiện client identity có được gateway tạo lại/ghi đè an toàn không?
- Log tại proxy có lưu header/body/token nhạy cảm không?

Không coi network private là lý do bỏ TLS giữa các service. Trong cloud, traffic nội bộ vẫn có thể đi qua shared infrastructure, service mesh, proxy hoặc miền quản trị khác.

### 2.3. Chọn phiên bản và cấu hình TLS

Ưu tiên phiên bản TLS còn được hỗ trợ và cấu hình cipher suite/algorithm theo chuẩn bảo mật hiện hành của nền tảng và tổ chức. Với dịch vụ Internet hiện đại, TLS 1.2 và TLS 1.3 thường là các phiên bản cần xem xét; hạn chế giao thức cũ như SSL và TLS 1.0/1.1 theo chính sách tương thích đã được đánh giá.

Các nguyên tắc:

- Tắt giao thức/cipher yếu và thuật toán lỗi thời.
- Dùng certificate chain hợp lệ, hostname/SAN khớp và trust store được quản lý.
- Bật hostname verification; không bỏ qua lỗi certificate trong production.
- Chọn session resumption và 0-RTT theo semantics ứng dụng; tránh dùng cơ chế có rủi ro replay cho request thay đổi trạng thái nếu chưa phân tích.
- Theo dõi certificate expiry, handshake failure, TLS version và cipher thực tế.
- Kiểm tra cấu hình trên edge, gateway, service, database, broker và admin endpoint, không chỉ website public.

Cấu hình cụ thể phải theo khuyến nghị provider, thư viện runtime, compliance và client support. Không sao chép cipher list cũ vào production mà không kiểm chứng.

### 2.4. Server certificate và trust chain

Server gửi certificate để chứng minh danh tính. Client xác minh:

1. Certificate được ký bởi CA nằm trong trust store hoặc chain dẫn tới trust anchor đáng tin.
2. Thời hạn certificate còn hợp lệ.
3. Hostname/SAN khớp tên client đang kết nối.
4. Key usage/extended key usage phù hợp vai trò server authentication.
5. Certificate chưa bị thu hồi theo cơ chế kiểm tra được áp dụng (OCSP/CRL hoặc policy khác).

Certificate public có thể phân phối rộng; **private key đi kèm phải được bảo vệ nghiêm ngặt**. Không commit private key vào Git, container image, frontend bundle, ticket hoặc log. Private key nên được giữ trong secret manager, HSM hoặc key store được bảo vệ; cấp quyền truy cập theo workload và xoay khi có nguy cơ lộ.

### 2.5. Mutual TLS (mTLS)

Trong mTLS, cả client và server đều trình certificate để xác thực danh tính ở tầng transport. Đây là lựa chọn hữu ích cho service-to-service, workload-to-database hoặc partner integration khi cần ràng buộc danh tính workload bằng PKI.

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant B as Service B
    A->>B: ClientHello
    B-->>A: Server certificate + proof
    A->>A: Verify server chain and hostname
    B-->>A: Request client certificate
    A-->>B: Client certificate + proof
    B->>B: Verify client chain, identity and policy
    A->>B: Encrypted application request
    B-->>A: Encrypted response
~~~

mTLS tăng độ tin cậy về danh tính kết nối nhưng không thay thế authorization. Service B vẫn phải kiểm tra service A được phép gọi operation nào và truy cập tenant/resource nào. Certificate identity cần được ánh xạ sang principal/role theo policy rõ ràng.

### 2.6. Certificate lifecycle

Một lifecycle hợp lý gồm:

- **Issue:** xác minh danh tính workload/hostname, cấp certificate từ CA được phê duyệt.
- **Distribute:** cấp qua secret/certificate manager hoặc workload agent; hạn chế export private key.
- **Install:** cập nhật listener/client trust store mà không ghi key vào image hoặc source.
- **Renew/rotate:** tự động gia hạn trước expiry, hỗ trợ overlap giữa certificate cũ và mới.
- **Revoke:** thu hồi khi lộ key, workload bị compromise hoặc identity không còn hợp lệ.
- **Audit/retire:** lưu metadata và lịch sử; xóa bản sao private key theo quy trình.

Cần đo số ngày còn lại trước expiry, renewal failure, handshake failure và certificate chưa được rotate. Certificate được gia hạn nhưng service không reload file mới vẫn có thể hết hạn trong production.

## 3. Mã hóa khi lưu: storage, database và backup

### 3.1. Encryption at rest

Mã hóa at rest bảo vệ dữ liệu lưu trên media/object/block/file storage bằng cơ chế mã hóa của dịch vụ hoặc ứng dụng. Một triển khai managed thường mã hóa block/object/database page bằng data key và bảo vệ data key bằng key management service.

Cần bao phủ:

- Database primary, replica, read replica, snapshot và automated backup.
- Object storage, version, replication destination và archive tier.
- Block volume, file share, persistent disk và container volume.
- Queue/broker storage, dead-letter queue và message archive nếu có.
- Search index, cache persistence, analytics extract và temporary staging.
- Log, trace, crash dump và artifact có thể chứa dữ liệu nhạy cảm.

Không suy luận mọi bản sao tự động được mã hóa chỉ vì storage chính đã bật encryption. Kiểm tra từng loại backup, export, cross-region copy và dịch vụ nhận dữ liệu.

### 3.2. Server-side encryption và client-side encryption

| Cách làm | Vị trí mã hóa/giải mã | Ưu điểm | Giới hạn |
|---|---|---|---|
| **Server-side encryption (SSE)** | Dịch vụ storage/database thực hiện | Tích hợp tốt, ít thay đổi ứng dụng | Dịch vụ vẫn giải mã khi workload có quyền đọc; không che plaintext khỏi service |
| **Client-side/application encryption** | Ứng dụng mã hóa trước khi gửi storage và giải mã sau khi đọc | Có thể hạn chế dịch vụ lưu trữ nhìn thấy plaintext | Ứng dụng quản lý key, rotation, search và compatibility phức tạp hơn |
| **Volume/disk encryption** | Tầng block/device | Bao phủ file/page trên volume khi offline | Không thay thế encryption ở tầng ứng dụng, transport hoặc quyền database |
| **Field-level encryption** | Chỉ field nhạy cảm | Giảm phạm vi plaintext và có thể tách quyền | Query/index/sort khó hơn, cần thiết kế token/search riêng |

SSE thường phù hợp làm baseline encryption at rest cho managed service. Với threat model cần ngăn database operator hoặc storage export đọc một số field, cân nhắc client/field-level encryption hoặc tokenization; cần xác định ai giữ key và ứng dụng nào được phép giải mã.

### 3.3. Scope encryption và plaintext

~~~mermaid
flowchart TB
    APP[Application] -->|TLS + encrypted payload| DB[(Encrypted Database)]
    DB --> SNAP[(Encrypted Snapshot / Backup)]
    DB --> REP[(Encrypted Replica)]
    APP -->|TLS| OBJ[(Encrypted Object Storage)]
    APP --> LOG[Log / Trace Pipeline]
    LOG --> MASK[Redaction / Data minimization]
    MASK --> STORE[(Encrypted Log Storage)]
    KEY[KMS / HSM] -. key operations .-> APP
    KEY -. protects data keys .-> DB
    KEY -. protects data keys .-> OBJ
~~~

Sơ đồ mô tả các lớp bảo vệ; triển khai cụ thể có thể dùng provider-managed key mà ứng dụng không trực tiếp gọi KMS. Log phải giảm thiểu plaintext ngay từ đầu. Nếu ứng dụng ghi token/email vào log rồi mới mã hóa storage, người đọc log hợp lệ vẫn có thể xem dữ liệu.

## 4. Quản lý khóa và envelope encryption

### 4.1. Tại sao không dùng một master key cho mọi dữ liệu?

Một khóa duy nhất có phạm vi dùng quá rộng tạo blast radius lớn. Nếu key lộ hoặc bị thu hồi, toàn bộ dữ liệu phụ thuộc key có thể bị ảnh hưởng. Mã hóa nhiều dữ liệu trực tiếp bằng một key cũng làm quản lý rotation, phân quyền, throughput và audit khó hơn.

**Envelope encryption** dùng ít nhất hai lớp khóa:

- **Data Encryption Key (DEK):** khóa dữ liệu dùng để mã hóa một object, record, file hoặc nhóm dữ liệu.
- **Key Encryption Key (KEK):** khóa cấp cao dùng để mã hóa/bọc (wrap) DEK; thường được quản lý trong KMS/HSM.

Luồng:

1. Ứng dụng yêu cầu KMS tạo DEK hoặc sinh DEK bằng CSPRNG theo quy trình được chấp thuận.
2. Plaintext DEK được sử dụng trong memory để mã hóa dữ liệu bằng authenticated encryption.
3. Ứng dụng gửi encrypted DEK tới KMS để wrap, hoặc nhận cả plaintext DEK và ciphertext DEK theo API dịch vụ.
4. Lưu ciphertext data cùng wrapped DEK, nonce/IV, algorithm/version và metadata cần thiết.
5. Khi đọc, workload được authorization gọi KMS unwrap DEK; giải mã data trong memory và xóa plaintext key khỏi vùng dùng khi có thể.

### 4.2. Sơ đồ envelope encryption

~~~mermaid
sequenceDiagram
    participant App as Application
    participant KMS as KMS / HSM
    participant Store as Data Storage
    App->>KMS: Generate or request data key
    KMS-->>App: Plaintext DEK + wrapped DEK
    App->>App: Encrypt data with DEK (AEAD)
    App->>Store: Ciphertext + wrapped DEK + nonce + metadata
    Note over Store: Plaintext DEK is not stored
    Store-->>App: Ciphertext + wrapped DEK + metadata
    App->>KMS: Unwrap DEK (authorized workload identity)
    KMS-->>App: Plaintext DEK
    App->>App: Authenticate and decrypt ciphertext
~~~

Không phải API KMS nào cũng trả plaintext DEK theo cùng cách; một số dịch vụ có encrypt/decrypt API hoặc data key caching riêng. Phải dùng SDK/API và semantics chính thức của provider.

### 4.3. Thuộc tính dữ liệu mã hóa

| Thuộc tính | Mục đích |
|---|---|
| encrypted_data | Nội dung ciphertext |
| wrapped_dek | DEK đã được mã hóa bởi KEK |
| key_id/key_version | Xác định key hoặc version dùng để wrap |
| algorithm | Thuật toán/suite và phiên bản |
| nonce/IV | Tham số duy nhất cần thiết cho chế độ mã hóa |
| authentication_tag | Tag xác thực nếu dùng AEAD |
| schema/version | Cấu trúc plaintext và quy tắc giải mã |
| associated_data | Metadata không bí mật được gắn với ciphertext để xác thực ngữ cảnh |

Không được tái sử dụng nonce trái với yêu cầu thuật toán/chế độ. Với AES-GCM, nonce/IV cần tính duy nhất theo key theo giới hạn của chuẩn triển khai; phát sinh ngẫu nhiên không kiểm soát có thể tạo xác suất va chạm khi số lượng lớn. Dùng thư viện crypto đã kiểm chứng, không tự thiết kế primitive.

Authenticated encryption (AEAD), ví dụ AES-GCM hoặc ChaCha20-Poly1305 trong môi trường phù hợp, cung cấp cả confidentiality và integrity. Không dùng mã hóa không xác thực cho payload nhạy cảm nếu thiếu MAC/kiểm tra toàn vẹn đúng cách.

### 4.4. DEK scope

DEK có thể được tạo theo:

- Mỗi object/file: phạm vi lỗi nhỏ, quản lý nhiều key metadata hơn.
- Mỗi record/field: cách ly mạnh hơn, tăng overhead và khó query.
- Mỗi tenant: dễ cô lập tenant và hủy/rotate theo khách, nhưng dữ liệu lớn có thể cần nhiều DEK/version.
- Mỗi batch/dataset: giảm số lần gọi KMS, nhưng blast radius plaintext key/cache lớn hơn.

Chọn scope theo volume, rủi ro, yêu cầu xóa/rotate và throughput. Tài liệu hóa nơi lưu wrapped DEK, key ID, cache lifetime và quy trình rewrap.

## 5. KMS, HSM và phân cấp khóa

### 5.1. Vai trò của KMS

Key Management Service (KMS) cung cấp API và control plane để tạo, lưu, bảo vệ, sử dụng, xoay, disable và audit key. KMS thường giảm nhu cầu tự vận hành HSM/key server nhưng vẫn cần policy và quyền đúng.

Một key record có thể có:

- Key ID/resource identifier và alias.
- Algorithm/key type, usage (encrypt/decrypt, sign/verify, wrap).
- Key state: enabled, disabled, pending deletion/destroyed.
- Region/account/project, owner, rotation policy.
- Key policy/IAM grant và audit event.
- Metadata liên kết tới workload, data classification và business owner.

KMS key không phải secret mà ứng dụng nên tải về để dùng trực tiếp. Với nhiều mô hình, thao tác cryptographic diễn ra trong dịch vụ bảo vệ key hoặc qua data key API; private key của asymmetric key có thể không export được.

### 5.2. HSM

Hardware Security Module (HSM) là phần cứng hoặc dịch vụ dựa trên phần cứng bảo vệ thao tác mật mã và key material trong môi trường kiểm soát. HSM có thể cần khi:

- Quy định compliance yêu cầu mức bảo vệ/hình thức kiểm soát cụ thể.
- Cần key không export, audit hoặc kiểm soát dual control.
- Workload cần crypto operation chuyên biệt hoặc throughput dự đoán.
- Tổ chức cần tự kiểm soát hơn vòng đời/hạ tầng key.

HSM tăng chi phí và yêu cầu vận hành, backup/replication, availability, client library và quy trình quản trị. Không mặc định HSM làm toàn hệ thống an toàn nếu ứng dụng vẫn log plaintext hoặc role có thể yêu cầu decrypt tùy ý.

### 5.3. Key hierarchy

~~~mermaid
flowchart TB
    ROOT[Root / HSM protected boundary]
    ROOT --> KEK1[KEK: Production data]
    ROOT --> KEK2[KEK: Backup vault]
    ROOT --> KEK3[KEK: Tenant / domain scope]
    KEK1 --> D1[Wrapped DEKs: Database objects]
    KEK1 --> D2[Wrapped DEKs: Object data]
    KEK2 --> D3[Wrapped DEKs: Backup sets]
    KEK3 --> D4[Wrapped DEKs: Sensitive fields]
~~~

Sơ đồ minh họa phân cấp logic. Một triển khai có thể dùng cloud-managed root key, customer-managed key, key per environment hoặc hierarchy khác theo provider. Tránh tự xây root-key hierarchy bên ngoài khả năng bảo vệ và quy trình backup đã được đánh giá.

### 5.4. Provider-managed và customer-managed key

| Loại | Mô tả | Đánh đổi |
|---|---|---|
| Provider-managed key | Nhà cung cấp tạo/vận hành key và rotation theo dịch vụ | Ít thao tác; mức kiểm soát policy/rotation tùy dịch vụ |
| Customer-managed key (CMK) | Khách hàng kiểm soát policy, disable, rotation hoặc deletion theo khả năng dịch vụ | Kiểm soát/audit tốt hơn; lỗi policy/key state có thể làm ứng dụng mất khả năng đọc |
| Customer-provided key | Khách hàng cung cấp material hoặc key theo mô hình dịch vụ hỗ trợ | Kiểm soát material cao; rủi ro lưu trữ, backup, rotation và trách nhiệm lớn hơn |

Tên gọi và semantics khác nhau giữa nhà cung cấp. Đọc rõ key ownership, exportability, rotation, regional scope, backup và deletion behavior. Không nhầm customer-managed key với field-level encryption do ứng dụng tự thực hiện.

## 6. Quyền giải mã: ai được dùng key và với dữ liệu nào?

### 6.1. Tách quyền sử dụng dữ liệu và quyền quản trị key

Các quyền cần được phân biệt:

- **Encrypt/generate data key:** tạo ciphertext hoặc DEK mới.
- **Decrypt/unwrap:** lấy plaintext hoặc mở DEK để đọc dữ liệu.
- **Re-encrypt/rewrap:** bọc DEK bằng KEK khác mà không cần giải mã payload nếu dịch vụ hỗ trợ.
- **Manage key policy:** sửa quyền hoặc cấu hình key.
- **Rotate:** tạo version/material mới theo cơ chế dịch vụ.
- **Disable/revoke/delete:** ngừng hoặc hủy key.
- **Audit/read metadata:** xem lịch sử và trạng thái key.

Ứng dụng runtime có thể cần decrypt dữ liệu booking nhưng không cần quyền disable/delete KEK. Đội security có thể quản key policy nhưng không có quyền đọc dữ liệu nghiệp vụ. Separation of duties giảm khả năng một credential bị lộ dẫn tới cả đọc dữ liệu lẫn xóa key.

### 6.2. Ma trận quyền mẫu

| Principal | Encrypt/generate | Decrypt/unwrap | Manage policy | Disable/delete | Audit |
|---|---:|---:|---:|---:|---:|
| Booking API runtime | Có, trong scope booking | Có, dữ liệu booking được phép | Không | Không | Không |
| Analytics workload | Có thể không | Chỉ curated dataset đã cấp | Không | Không | Không |
| Backup service | Có/rewrap theo policy | Restore scope được duyệt | Không | Không | Metadata |
| Security key admin | Theo quy trình | Không mặc định | Có | Theo dual control | Có |
| Auditor | Không | Không | Không | Không | Read-only |
| Break-glass operator | Tạm thời theo incident | Chỉ phạm vi phê duyệt | Theo thời hạn | Có thể cần dual approval | Có |

Bảng chỉ là mẫu phân tách trách nhiệm; một số KMS gộp action hoặc policy theo key/service. Kiểm tra chính xác authorization model của nền tảng.

### 6.3. Policy theo workload identity

~~~text
Principal: booking-api-production
Allowed actions:
  - GenerateDataKey
  - Decrypt
Resource:
  - booking-production-key
Conditions:
  - environment == production
  - workload identity == booking-api
  - encryption context tenant_scope == assigned scope
Denied:
  - DisableKey
  - ScheduleKeyDeletion
  - PutKeyPolicy
~~~

Đây là policy giả mã, không phải cú pháp trực tiếp của một cloud provider. Trong policy thực, dùng resource ID cụ thể, conditions được hỗ trợ và kiểm thử bằng principal thực. Encryption context/AAD có thể ràng buộc ciphertext với ngữ cảnh nhưng không thay thế authorization của ứng dụng.

### 6.4. Tenant isolation và quyền support

Với multi-tenant:

- Có thể dùng key riêng theo tenant hoặc key domain với DEK riêng; chọn theo compliance, cost và khả năng scale.
- Key/DEK metadata phải liên kết tenant bằng ngữ cảnh xác thực, không tin tenant ID do client tùy ý gửi.
- Không cho tenant A dùng ciphertext hoặc wrapped DEK của tenant B bằng cách sửa ID.
- Support access phải có approval, thời hạn, audit và mục đích rõ.
- Khi offboard tenant, định nghĩa xóa data key có làm cryptographic erasure hay còn plaintext/backup/cache ở nơi khác.

**Cryptographic erasure** chỉ có hiệu quả nếu toàn bộ bản dữ liệu liên quan không thể giải mã bằng key còn tồn tại hoặc bản sao key khác. Xóa một key trong KMS không xóa plaintext đã export, DEK cache, replica hoặc bản backup dùng key khác.

## 7. Rotation, re-encryption và thu hồi key

### 7.1. Rotation không phải lúc nào cũng phải mã hóa lại toàn bộ dữ liệu

Với envelope encryption, có thể xoay KEK theo hai cách:

- Tạo KEK version mới và **rewrap các DEK** từ key cũ sang key mới. Ciphertext dữ liệu vẫn giữ nguyên nếu DEK không đổi.
- Tạo DEK mới và **re-encrypt dữ liệu**. Cần đọc ciphertext, giải mã bằng DEK cũ rồi mã hóa lại với DEK mới.

Rewrap thường ít tốn I/O hơn vì chỉ xử lý wrapped DEK/metadata, nhưng chỉ phù hợp khi threat model cho phép giữ DEK cũ. Nếu DEK nghi bị lộ, chỉ rewrap DEK đã lộ không loại bỏ việc attacker đã có plaintext key. Khi đó cần tạo DEK mới và re-encrypt dữ liệu tương ứng.

### 7.2. Quy trình rotation tham chiếu

1. Xác định key, workload, dataset, backup và consumer phụ thuộc.
2. Tạo key version mới hoặc key mới; thiết lập policy và audit.
3. Cấp quyền cho workload sử dụng key mới; kiểm tra decrypt/encrypt ở môi trường thử.
4. Chuyển ghi mới sang key version mới.
5. Rewrap DEK hoặc re-encrypt dữ liệu theo kế hoạch và batch có kiểm soát.
6. Kiểm tra tỷ lệ record/object đã chuyển, decrypt test và lỗi.
7. Giữ key cũ ở trạng thái decrypt-only trong cửa sổ migration/retention khi phù hợp.
8. Xác nhận không còn dữ liệu/backup cần key cũ trước khi disable/revoke.
9. Theo dõi ứng dụng, restore path và audit; cập nhật inventory/runbook.

Không disable key cũ ngay khi write path đã dùng key mới. Snapshot cũ, replica, archive, backup và dữ liệu chưa backfill có thể vẫn cần key cũ trong nhiều tháng.

### 7.3. Rotation, disable và deletion khác nhau

| Hành động | Ý nghĩa | Rủi ro |
|---|---|---|
| Rotation | Tạo material/version mới theo policy; hành vi phụ thuộc KMS | Client cũ hoặc dữ liệu cũ cần compatibility |
| Disable | Ngừng một số thao tác dùng key | App/restore có thể không decrypt được |
| Revoke access | Loại quyền của principal | Có thể gián đoạn workload nếu dependency chưa chuyển |
| Schedule deletion | Đặt lịch hủy key theo policy dịch vụ | Hủy không thể đảo ngược sau thời gian chờ |
| Destroy material | Hủy key material theo cơ chế tương ứng | Dữ liệu được bảo vệ có thể mất khả năng giải mã vĩnh viễn |

Đừng dùng disable/delete như nút xử lý đầu tiên khi nghi credential bị lộ nếu chưa xác định impact. Trong incident, có thể cần revoke principal, rotate secret/certificate, disable key theo quyết định, đồng thời giữ khả năng phục hồi dữ liệu sạch.

### 7.4. Key compromise response

Khi nghi key hoặc private key bị lộ:

- Xác định loại key, thời gian, principal và dữ liệu có thể bị ảnh hưởng.
- Chặn/thu hồi quyền truy cập và credential bị compromise.
- Xác định attacker có thể gọi decrypt hay đã lấy plaintext key/material.
- Tạo key mới trong trust boundary đã làm sạch.
- Re-encrypt dữ liệu nếu key material/DEK có thể bị lộ; rewrap đơn thuần có thể không đủ.
- Xem xét certificate revoke, session/token invalidation và thay credential liên quan.
- Kiểm tra access log KMS, storage, database, export và unusual decrypt volume.
- Phục hồi từ backup sạch nếu dữ liệu bị sửa/xóa, đồng thời giữ evidence.
- Cập nhật khách hàng/đơn vị quản lý theo quy trình incident và nghĩa vụ thông báo.

## 8. Bảo vệ key, secret và cấu hình

### 8.1. Phân biệt key, certificate và application secret

| Loại | Vai trò | Ví dụ |
|---|---|---|
| Encryption key | Mã hóa/giải mã dữ liệu | DEK, KEK, database key |
| Signing key | Ký và xác minh chữ ký | Private key ký JWT hoặc artifact |
| TLS private key | Chứng minh danh tính endpoint trong TLS | Private key của server/client certificate |
| Password/API secret | Xác thực tới dịch vụ khác | DB password, API token |
| Certificate | Chứa public key và thông tin danh tính được CA ký | X.509 certificate |

Không lưu tất cả vào một file cấu hình dùng chung. Secret manager, KMS và certificate manager có chức năng khác nhau; cần chọn dịch vụ phù hợp và giới hạn quyền.

### 8.2. Những nơi không được để key

- Source code, Git history, pull request và issue tracker.
- Frontend/mobile bundle nếu đó là key bí mật; mọi secret shipped tới client có thể bị trích xuất.
- Docker image, package artifact, build cache hoặc test fixture.
- Log, trace, crash dump, telemetry attribute và shell history.
- File backup không mã hóa hoặc thư mục tạm có quyền rộng.
- Chat/email/ticket hoặc tài liệu chia sẻ công khai.

Nếu secret từng được commit, xóa dòng khỏi repository hiện tại chưa đủ: history, fork, cache và artifact có thể còn. Cần coi key đã lộ, rotate/revoke và xử lý toàn bộ bản sao.

### 8.3. Cấp secret runtime

Ứng dụng nên lấy secret/key qua workload identity và secret manager với scope tối thiểu. Cần quyết định:

- Fetch lúc startup hay theo yêu cầu; refresh khi rotation.
- Cache secret/key trong memory bao lâu.
- Xử lý khi KMS/secret manager tạm không sẵn sàng.
- Cách tránh ghi plaintext khi log exception.
- Ai có thể impersonate workload identity.
- Cách thu hồi credential khi pod/VM bị compromise.

Cache giúp giảm latency và phụ thuộc KMS nhưng kéo dài thời gian sử dụng credential cũ. Cache lifetime phải phù hợp rotation, revocation và threat model; không cache plaintext key vô thời hạn.

## 9. Mã hóa ở cấp ứng dụng và field-level encryption

### 9.1. Khi nào cần thêm lớp mã hóa?

Mã hóa volume/database của provider thường đủ để bảo vệ media và bản snapshot khỏi truy cập vật lý hoặc đường storage trái phép. Nhưng đôi khi tổ chức cần giảm khả năng đọc plaintext của:

- Database administrator hoặc operator của storage.
- Analytics workload chỉ được xem một số field.
- Nhiều service dùng chung database nhưng không phải service nào cũng được xem PII.
- Bản export hoặc object có thể được chia sẻ cho bên thứ ba.

Field-level encryption mã hóa giá trị trước khi persist. Tuy nhiên, nó làm các truy vấn equality/range/sort khó hơn vì ciphertext không giữ thứ tự hay equality ổn định theo mặc định.

### 9.2. Ví dụ field encryption

~~~text
Input:
  customer_id = opaque identifier
  national_id = plaintext-sensitive-value

Application:
  DEK = data key scoped to approved domain/tenant
  ciphertext, nonce, tag = AEAD_Encrypt(DEK, value, associated_data)
  wrapped_DEK = KMS_Wrap(KEK, DEK)

Persist:
  customer_id
  encrypted_national_id
  nonce
  authentication_tag
  wrapped_DEK
  key_id + schema_version
~~~

Khi đọc, ứng dụng xác thực principal và tenant, lấy wrapped DEK, gọi KMS unwrap, xác thực tag/AAD rồi giải mã trong memory. Nếu tag không hợp lệ, xử lý như dữ liệu bị sửa hoặc key/metadata sai; không trả plaintext hoặc bỏ qua lỗi xác thực.

### 9.3. Tìm kiếm trên dữ liệu đã mã hóa

Randomized encryption tạo ciphertext khác nhau cho cùng plaintext, giúp giảm rò rỉ pattern nhưng không hỗ trợ equality lookup trực tiếp. Có thể dùng:

- **Tokenization:** thay giá trị nhạy cảm bằng token tham chiếu trong vault/service chuyên trách.
- **Blind index/HMAC token:** tạo giá trị tìm kiếm xác định bằng key riêng, lưu riêng với ciphertext.
- **Deterministic encryption:** cùng plaintext có thể tạo ciphertext giống nhau trong một scope; hỗ trợ equality nhưng rò rỉ pattern/tần suất.
- **Search service có quyền:** giải mã trong service được kiểm soát hoặc truy vấn qua API chuyên dụng.

Mỗi lựa chọn có rò rỉ thông tin khác nhau. Blind index/HMAC token vẫn có thể tiết lộ giá trị trùng, tần suất hoặc cho phép correlation; key tìm kiếm phải tách khỏi key mã hóa và có policy riêng. Không dùng hash không khóa cho số điện thoại/email/ID có không gian giá trị dễ đoán.

### 9.4. Dữ liệu cần sort/range

Mã hóa thông thường không bảo toàn thứ tự, vì vậy các truy vấn BETWEEN, sort theo số tiền hoặc range theo ngày không còn đơn giản. Tránh tự phát triển order-preserving encryption nếu chưa có phân tích chuyên sâu về rò rỉ. Thường nên giữ field không nhạy cảm/đã giảm độ nhạy để lọc, dùng tokenization, phân vùng service hoặc xử lý ở môi trường được cấp quyền.

## 10. Các bản sao dữ liệu: backup, replica, log, cache và export

Encryption policy phải theo dữ liệu qua toàn bộ vòng đời:

| Vị trí | Rủi ro thường gặp | Kiểm soát |
|---|---|---|
| Primary DB | Role đọc quá rộng; query export | DB role, network, encryption, audit |
| Read replica | Tạo thêm bản dữ liệu có PII | Kế thừa key/policy, giới hạn consumer |
| Snapshot/PITR | Backup key/retention không đúng | Backup vault, KMS policy, restore drill |
| Object version/replica | Bản cũ còn tồn tại sau khi xóa | Lifecycle, inventory, deletion workflow |
| Queue/DLQ | Payload chứa PII tồn tại lâu | Payload minimization, encryption, retention, restricted access |
| Cache | Plaintext trong memory/persistence | Network isolation, TTL, encryption nếu hỗ trợ, access control |
| Log/trace | Token/PII bị ghi ngoài ý muốn | Redaction ở nguồn, sampling, role và retention |
| Export/CSV | File tải xuống nằm ngoài control plane | Short-lived URL, encryption, watermark/audit, expiry |
| Temporary files | File plaintext trong worker volume | Ephemeral encrypted storage, cleanup, restricted process |

Mã hóa storage không thay thế data minimization. Cách tốt nhất để không lộ một dữ liệu là không thu thập hoặc không sao chép nó nếu không cần cho nghiệp vụ.

## 11. Bảo vệ tính toàn vẹn, authenticity và key usage

### 11.1. Encryption khác signing

- **Encryption** giúp người không có key không đọc được nội dung.
- **Message authentication code (MAC)** xác nhận dữ liệu không bị sửa bởi bên không có secret key.
- **Digital signature** cho phép xác minh dữ liệu do holder của private signing key ký, dùng public key để verify.

AEAD thường kết hợp confidentiality và integrity cho ciphertext. Chữ ký số phù hợp khi cần kiểm chứng nguồn gốc artifact, document hoặc message qua nhiều hệ thống. Không dùng encryption đơn thuần làm bằng chứng ai đã gửi dữ liệu.

### 11.2. Signing key và rotation

Với token/JWT hoặc artifact ký số, consumer có thể cần public key cũ để verify token/artifact được phát hành trước rotation. Vì vậy cần:

- Key ID/version trong header/metadata.
- Cửa sổ overlap public key cũ/mới.
- Token lifetime và revoke/deny policy.
- Quy trình thu hồi private key bị compromise.
- Không nhầm signing key với encryption KEK.

Nếu dùng một key cho nhiều mục đích, sự cố ở một protocol có thể ảnh hưởng protocol khác. Tách key theo purpose và algorithm/domain theo nguyên tắc key separation.

### 11.3. Audit key usage

Audit cần trả lời:

- Principal nào gọi encrypt/decrypt/unwrap?
- Thời gian, key ID, region/account và context là gì?
- Request thuộc workload/tenant nào?
- Có lượng decrypt bất thường, gọi từ vị trí lạ hoặc ngoài giờ không?
- Ai thay đổi key policy, rotation, disable hoặc deletion schedule?

Không ghi plaintext, raw key, token hoặc toàn bộ encryption context chứa PII vào audit log. Dùng request ID, principal ID và metadata tối thiểu để điều tra; bảo vệ log khỏi sửa/xóa và kiểm soát người đọc.

## 12. Hiệu năng, availability và chi phí của key operations

### 12.1. KMS là dependency runtime

Nếu mỗi request gọi KMS nhiều lần, latency và quota KMS có thể ảnh hưởng API. Nếu KMS hoặc network tới KMS lỗi, workload có thể không giải mã được dữ liệu.

Các lựa chọn:

- Dùng envelope encryption để giảm kích thước payload gửi tới KMS; KMS chỉ wrap/unwrap DEK.
- Cache DEK có thời hạn và scope nhỏ nếu policy cho phép.
- Giới hạn số lần gọi KMS, áp retry có backoff/jitter và deadline.
- Pre-warm hoặc cấp data key cho batch job theo cơ chế an toàn.
- Theo dõi KMS throttling, latency, availability và decrypt failure.
- Không retry vô hạn hoặc mở fallback sang plaintext khi KMS lỗi.

Cache plaintext DEK giảm phụ thuộc runtime nhưng tăng thời gian attacker có thể dùng key nếu process bị compromise. Cần giới hạn TTL, memory access, process isolation và xóa key khi kết thúc thao tác theo khả năng runtime.

### 12.2. Retry và availability

KMS error có thể là permission denied, throttling, timeout, invalid ciphertext, disabled key hoặc service outage:

- Permission/configuration error: retry thường không giải quyết, cần cảnh báo.
- Throttling/transient network: retry có backoff, jitter, deadline và giới hạn.
- Invalid ciphertext/tag: không retry mù; có thể là corruption/tampering.
- Disabled/deleted key: đi vào quy trình key recovery/incident, không bypass bằng key không được phép.

Không fallback sang plaintext hoặc key hard-code để duy trì availability. Khả năng phục hồi key và quyền giải mã là một phần của DR; test restore phải chứng minh key vẫn dùng được ở recovery region/account.

### 12.3. Chi phí

TCO mã hóa gồm KMS/HSM key và request encrypt/decrypt/wrap; certificate authority, cấp/gia hạn certificate và secret manager; storage overhead cho nonce, tag, wrapped DEK, metadata và version; compute CPU và latency cho crypto; backup/replication key, HSM/region và audit logs; nhân lực vận hành, access review, rotation và incident drill.

Tối ưu chi phí bằng envelope encryption, scope DEK phù hợp, giảm dữ liệu cần mã hóa ở application, cache có kiểm soát và lifecycle metadata; không loại bỏ audit/backup/segregation chỉ để giảm một khoản phí KMS.

## 13. Quy trình thiết kế security architecture

1. **Inventory dữ liệu:** loại dữ liệu, classification, volume, flow, owner và retention.
2. **Threat model:** ai có thể nghe lén, đọc storage, lấy credential, sửa dữ liệu hoặc chiếm quyền KMS?
3. **Vẽ data flow và trust boundary:** điểm TLS termination, storage, replica, backup, log và export.
4. **Chọn baseline encryption:** TLS cho mọi hop phù hợp; at-rest cho storage/backup; field-level/tokenization khi yêu cầu.
5. **Chọn key hierarchy:** provider-managed/customer-managed, KEK/DEK scope, KMS/HSM và region.
6. **Thiết kế access policy:** workload identity, encrypt/decrypt, admin/audit, separation of duties và tenant context.
7. **Định nghĩa lifecycle:** issue, distribute, cache, rotate, rewrap, revoke, recover và destroy.
8. **Thử workload:** latency, quota, concurrency, failover KMS, restore, certificate renewal và key compromise.
9. **Đưa vào vận hành:** dashboard, alert, inventory, audit, runbook và review định kỳ.

### 13.1. Mẫu data flow inventory

| Data flow | Classification | Transport protection | At-rest protection | Principal có thể giải mã |
|---|---|---|---|---|
| Browser → API | Confidential | TLS + server auth | Không lưu ở edge hoặc log được giảm thiểu | API runtime sau authentication |
| API → Booking DB | Confidential/PII | TLS, có thể mTLS | DB encryption, backup encryption | Booking DB role + workload |
| API → Event broker | Internal/PII tối thiểu | TLS/mTLS | Broker storage encryption | Consumer được duyệt |
| DB → Backup vault | Confidential/PII | Private channel/TLS theo dịch vụ | Backup key riêng hoặc policy được xác minh | Recovery role |
| Worker → Email provider | Confidential | TLS | Secret/token được quản lý; log không chứa nội dung nhạy cảm | Worker scope cụ thể |
| Analytics → Curated lake | Confidential hoặc de-identified | TLS | Object/table encryption | Analytics identity được duyệt |

Ma trận phải phản ánh flow thật. Nếu gateway kết thúc TLS rồi gọi backend qua plaintext, cột transport phải ghi rõ; không đánh dấu toàn flow TLS chỉ vì client connection được mã hóa.

### 13.2. Mẫu key inventory

| Thuộc tính | Giá trị cần quản lý |
|---|---|
| key_id / alias | Định danh key không bí mật |
| purpose | Encryption, wrapping, signing hoặc TLS |
| scope | Environment, domain, tenant hoặc dataset |
| owner | Team chịu trách nhiệm |
| key policy | Principal/action/resource/condition |
| lifecycle | Created, enabled, rotation, expiry, deletion |
| dependencies | Database, object, backup, service và version |
| recovery | Backup/replica, quyền decrypt và quy trình khôi phục |
| audit | Log location, alert owner và retention |

Inventory không chứa key material, secret hoặc private key.

## 14. Kiểm thử và diễn tập

### 14.1. Kiểm thử TLS/certificate

| Test | Mục đích | Tiêu chí |
|---|---|---|
| Hostname mismatch | Bắt lỗi cấu hình server identity | Client từ chối handshake |
| Expired/untrusted certificate | Kiểm tra trust/expiry | Kết nối bị từ chối và có alert |
| mTLS client không hợp lệ | Kiểm tra workload identity | Server không cho request vào app |
| Backend hop | Xác minh TLS sau termination | Không có plaintext hop ngoài policy |
| Rotation overlap | Gia hạn không gây outage | Client mới/cũ được hỗ trợ trong cửa sổ |
| Revocation | Ngừng certificate bị compromise | Kết nối mới bị từ chối theo policy |

### 14.2. Kiểm thử KMS và encryption at rest

- Tạo dữ liệu mới và xác nhận ciphertext/wrapped DEK được lưu đúng.
- Thử decrypt bằng workload identity hợp lệ.
- Thử principal không được phép; phải bị từ chối và được audit.
- Disable key ở môi trường test; xác nhận workload báo lỗi an toàn, không rơi về plaintext.
- Rotate KEK và kiểm tra dữ liệu cũ/mới đọc được trong giai đoạn overlap.
- Rewrap/re-encrypt theo batch và đối soát số record/object.
- Restore backup vào recovery environment và xác nhận key/permission có sẵn.
- Thử KMS throttling/network outage, kiểm tra retry, timeout và alert.

### 14.3. Kiểm thử field encryption và data leakage

- Ciphertext thay đổi khi mã hóa randomized cho cùng plaintext theo kỳ vọng thuật toán.
- Tag/AAD mismatch khiến giải mã thất bại.
- Tenant A không giải mã được ciphertext của tenant B.
- Log, exception, trace và crash dump không ghi plaintext/key.
- Export/cache/temp file tuân theo chính sách.
- Key cũ vẫn được quản lý trong thời gian cần restore; sau khi hết retention mới có thể hủy theo phê duyệt.

### 14.4. Diễn tập rotation và incident

1. Rotate certificate cho một nhóm service, theo dõi handshake và error rate.
2. Rotate KEK, rewrap DEK và xác nhận record cũ/mới.
3. Giả lập principal bị compromise, revoke quyền và phát hành identity mới.
4. Restore backup trong region khác bằng key policy và quyền DR.
5. Đo thời gian xử lý và dependency còn thiếu; cập nhật runbook.

Không diễn tập disable/delete key production nếu chưa có phê duyệt, phạm vi ảnh hưởng, backup, recovery path và điều kiện dừng. Dùng key/test dataset riêng để kiểm thử destructive action.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ bật HTTPS ở edge | Backend hop có thể truyền plaintext | Mã hóa từng hop qua trust boundary |
| Bỏ hostname verification | Có TLS nhưng client có thể kết nối nhầm server | Verify hostname, chain và trust store |
| Dùng mTLS nhưng không authorization | Service hợp lệ truy cập operation/tenant không được phép | Map identity sang role và policy |
| Cho app runtime quyền quản lý/xóa KEK | Credential app bị lộ có thể phá cả dữ liệu và key | Tách quyền encrypt/decrypt với admin/delete |
| Mã hóa volume rồi cho rằng PII đã được bảo vệ mọi nơi | Log/export/cache/replica vẫn có plaintext | Inventory toàn bộ data lifecycle, giảm thiểu và bảo vệ bản sao |
| Hard-code key trong app/image/Git | Key bị trích xuất và tồn tại trong history | KMS/secret manager, rotate và xử lý leak |
| Xoay key rồi xóa key cũ ngay | Backup/record cũ không còn decrypt được | Inventory dependency, overlap và restore test |
| Rewrap DEK đã bị lộ và coi sự cố đã xử lý | Attacker có thể đã giữ plaintext DEK | Re-encrypt bằng DEK mới theo incident scope |
| Dùng một key cho mọi purpose/tenant | Blast radius lớn, khó audit | Tách purpose/scope và policy |
| Không lưu metadata để giải mã | Ciphertext không thể phục hồi dù key còn | Lưu key ID/version, nonce, tag, schema version |
| Log plaintext rồi mã hóa log storage | Người có quyền đọc log vẫn thấy PII | Redact/minimize trước khi ghi |
| Cache plaintext DEK vô thời hạn | Process compromise cho phép đọc lâu dài | TTL/scope, memory hygiene và revocation plan |
| Xem encryption là authorization | Caller hợp lệ đọc sai tenant | AuthN, authZ, tenant isolation và audit |
| Không restore test bằng key ở DR region | Backup tồn tại nhưng không giải mã được | Diễn tập end-to-end gồm KMS/IAM/network |

## 16. Bài thực hành: thiết kế mã hóa cho nền tảng đặt lịch

**Tình huống:** Một nền tảng đặt lịch có Web/Mobile, API Gateway, Booking Service, relational database, event broker, object storage và analytics lake. Dữ liệu gồm booking, email/điện thoại, thông tin thanh toán tham chiếu và tài liệu đính kèm. Hệ thống triển khai ở hai region; một số tenant yêu cầu kiểm soát key riêng. Booking API cần latency thấp; đội vận hành cần restore dữ liệu khi DR.

Hãy xây dựng thiết kế:

1. **Data classification:** phân loại dữ liệu public/internal/confidential/PII; xác định field nào không cần lưu và nơi nào có bản sao.
2. **TLS map:** vẽ client → gateway → service → DB/broker/storage; đánh dấu termination, TLS/mTLS, server/client identity và trust boundary.
3. **Certificate lifecycle:** xác định CA, issuance, private key storage, rotation, overlap, revoke, expiry alert và owner.
4. **At-rest baseline:** xác định database, replica, snapshot, object, queue, backup, log và analytics có encryption nào.
5. **Field encryption:** chọn field cần application-level encryption/tokenization; giải thích tác động tới tìm kiếm, index, sort và analytics.
6. **Key hierarchy:** thiết kế KEK/DEK, key scope theo environment/domain/tenant, KMS/HSM và metadata cần lưu.
7. **Authorization:** tạo ma trận principal/action/resource; tách workload decrypt khỏi security admin và break-glass.
8. **Rotation/recovery:** mô tả rotation KEK, rewrap/re-encrypt, key compromise và cách giữ khả năng restore backup cũ.
9. **Observability:** metric KMS latency/throttle/decrypt failure, certificate expiry/handshake, audit và cảnh báo bất thường.
10. **Kiểm thử:** thử tenant isolation, principal trái phép, TLS hostname mismatch, certificate rotation, key rotation, KMS outage và restore DR.
11. **Well-Architected:** nêu đánh đổi về security, reliability, performance, cost, operations và sustainability.

### Bảng quyết định mẫu

| Flow/data | Bảo vệ khi truyền | Bảo vệ khi lưu | Quyền giải mã | Bằng chứng |
|---|---|---|---|---|
| Web/Mobile → Gateway | TLS, hostname verification | Không lưu request body nhạy cảm ở edge log | Gateway/API theo identity | TLS scan, log test |
| Gateway → Booking API | TLS hoặc mTLS | Runtime secret được quản lý | Booking workload | Backend hop test, IAM |
| Booking API → DB | TLS, DB server identity | DB/backup encryption | Booking DB role/workload | Connection test, restore |
| Booking API → Broker | TLS/mTLS | Broker storage encryption | Consumer được duyệt | ACL/decrypt test |
| PII field trong DB | TLS trong DB flow | Field AEAD + wrapped DEK khi cần | Service/domain được cấp | Tenant isolation, tag/AAD test |
| Backup sang Region B | TLS/private replication theo dịch vụ | Backup vault key riêng hoặc policy phù hợp | DR recovery role | Cross-region restore drill |
| Analytics lake | TLS | Object/table encryption, masking | Analytics identity | Access review, PII scan |

**Tiêu chí hoàn thành:** Người review có thể lần theo dữ liệu nhạy cảm từ lúc nhận tới lúc xóa, biết từng hop được mã hóa thế nào, key do ai kiểm soát, principal nào giải mã được và cách phục hồi khi key/certificate bị lỗi hoặc bị compromise. Các giả định chưa được provider xác nhận phải được đánh dấu để thử nghiệm.

## 17. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi về encryption và key management | Bằng chứng |
|---|---|---|
| **Operational Excellence** | Certificate/key có inventory, owner, rotation automation, alert và runbook? | Rotation drill, expiry dashboard, key inventory |
| **Security** | TLS đúng, key scope nhỏ, least privilege, audit và data minimization? | TLS test, IAM policy test, audit review, leakage scan |
| **Reliability** | KMS/key có HA/recovery, backup giải mã được, rotation không gây outage? | Restore drill, key recovery, failure test |
| **Performance Efficiency** | Crypto/KMS latency, throughput và cache có đáp ứng tải? | p95 decrypt, KMS throttle, load test |
| **Cost Optimization** | Số key, KMS calls, HSM, logs và storage overhead có phù hợp? | KMS cost/showback, DEK scope review |
| **Sustainability** | Có giảm dữ liệu sao chép, key/version và compute crypto thừa? | Data lifecycle, utilization, retention review |

Mã hóa tốt không chỉ là chọn thuật toán mạnh. Nó là sự kết hợp của kênh truyền được xác thực, storage được bảo vệ, key có vòng đời và quyền rõ, plaintext được giảm thiểu, và khả năng phục hồi được kiểm chứng.

## 18. Khung ghi nhớ

- **In transit:** bảo vệ từng hop bằng TLS; xác minh certificate/hostname và dùng mTLS khi cần xác thực workload hai chiều.
- **At rest:** bao phủ database, object, replica, snapshot, backup, queue, log và export; kiểm tra từng bản sao.
- **Envelope encryption:** DEK mã hóa dữ liệu, KEK/KMS bảo vệ DEK; lưu metadata đủ để giải mã.
- **Key authorization:** tách quyền encrypt/decrypt khỏi quyền sửa policy, disable hoặc delete key; dùng workload identity và least privilege.
- **Rotation có kế hoạch:** phân biệt rotate, rewrap, re-encrypt, revoke và delete; giữ key cũ khi còn backup/record cần đọc.
- **Field-level encryption có đánh đổi:** giảm plaintext exposure nhưng ảnh hưởng search, sort, index và analytics.
- **Kiểm chứng end-to-end:** certificate renewal, key rotation, unauthorized decrypt, backup restore, KMS outage và incident response.

Kiến trúc mã hóa đáng tin cậy bảo vệ dữ liệu từ đường truyền tới bản sao lưu, đồng thời giới hạn rõ ai có thể giải mã và ai được quản trị key. Mọi lựa chọn cần tính cả vòng đời dữ liệu, hiệu năng và khả năng phục hồi: ciphertext chỉ hữu ích khi key được bảo vệ, quyền được cấp đúng, metadata còn đầy đủ và tổ chức có thể giải mã hợp lệ khi cần.

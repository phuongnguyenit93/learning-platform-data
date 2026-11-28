# Thiết kế encryption cho database

Một database thường chứa nhiều loại dữ liệu có giá trị và mức nhạy cảm khác nhau: thông tin định danh, hồ sơ khách hàng, dữ liệu thanh toán, token tích hợp và lịch sử giao dịch. Chỉ bật tính năng mã hóa của database chưa chắc đã bảo vệ dữ liệu trước mọi tình huống. Nếu ứng dụng hoặc tài khoản database hợp lệ bị lạm dụng, dữ liệu có thể vẫn được đọc ở dạng rõ. Nếu bản backup được sao chép ra ngoài, lớp mã hóa ở ổ đĩa có thể không đủ để bảo vệ bản sao đó. Nếu key bị mất, ciphertext có thể trở thành dữ liệu không thể khôi phục.

Bài này xây dựng một thiết kế mã hóa cho database của một nền tảng dịch vụ có nhiều tenant. Thiết kế kết hợp mã hóa ở tầng lưu trữ, mã hóa trường nhạy cảm tại ứng dụng, envelope encryption, quản lý key bằng KMS/HSM, kiểm soát truy cập, rotation, backup/recovery và kiểm toán. Trọng tâm là tạo ra kiến trúc có thể vận hành lâu dài, kể cả khi dữ liệu tăng trưởng, key thay đổi hoặc xảy ra sự cố.

## 1. Bối cảnh và yêu cầu thiết kế

Giả sử một nền tảng quản lý khách hàng lưu các thông tin như:

- Họ tên, email và số điện thoại.
- Mã định danh khách hàng và thông tin xác minh.
- Thông tin tài khoản thanh toán được phép lưu theo phạm vi nghiệp vụ.
- Địa chỉ và một số thuộc tính hồ sơ nhạy cảm.
- Lịch sử giao dịch và trạng thái xử lý.

Database chạy trên hạ tầng cloud, có nhiều tenant dùng chung cụm dịch vụ. Ứng dụng truy cập database qua connection pool; backup được sao chép sang vùng khác; hệ thống analytics và tìm kiếm nhận dữ liệu qua CDC hoặc pipeline xử lý.

Thiết kế cần đáp ứng các yêu cầu:

| Yêu cầu | Mục tiêu |
|---|---|
| Bảo vệ dữ liệu khi lưu trữ | Ciphertext và backup không tiết lộ plaintext khi bị sao chép trái phép |
| Giới hạn phạm vi lộ dữ liệu | Một key bị lộ không làm ảnh hưởng toàn bộ tenant hoặc database |
| Cô lập tenant | Không thể dùng quyền của tenant này để giải mã dữ liệu tenant khác |
| Quản lý key | Có owner, purpose, version, cryptoperiod, rotation và destruction policy |
| Khả năng truy vấn | Các trường cần tìm kiếm có thiết kế riêng, tránh làm lộ quá nhiều thông tin |
| Hiệu năng | Không gọi KMS cho mọi thao tác nhỏ nếu có thể dùng envelope encryption hợp lý |
| Khả năng khôi phục | Có thể restore database và giải mã dữ liệu từ backup trong môi trường DR |
| Kiểm toán | Biết principal nào sử dụng key nào, cho operation gì và vào thời điểm nào |
| Vận hành an toàn | Có quy trình xử lý key compromise, lỗi KMS và migration dữ liệu |

Không có một kiểu mã hóa duy nhất đáp ứng tất cả yêu cầu. Cần phân loại dữ liệu, xác định threat model và chọn lớp bảo vệ theo từng ranh giới.

## 2. Threat model: cần chống lại ai và điều gì?

Trước khi chọn thuật toán, cần xác định tài sản và đối thủ mà thiết kế phải đối phó.

| Mối đe dọa | Khả năng của đối thủ | Lớp bảo vệ và giới hạn |
|---|---|---|
| Mất ổ đĩa hoặc snapshot | Đọc trực tiếp phương tiện lưu trữ | Disk/volume encryption và TDE giúp bảo vệ dữ liệu trên phương tiện |
| Lộ bản backup | Có bản sao database hoặc object backup | Backup encryption, envelope encryption và kiểm soát recovery key |
| Database dump bị đánh cắp | Đọc schema, ciphertext và metadata | Application-level field encryption giữ plaintext ngoài database |
| DBA hoặc tài khoản DB bị lạm dụng | Truy vấn dữ liệu bằng quyền database | Field encryption giảm khả năng đọc plaintext; audit và SoD kiểm soát thao tác |
| SQL injection | Gửi truy vấn qua ứng dụng | Parameterized query, authorization và field encryption; nếu ứng dụng có quyền decrypt thì vẫn có nguy cơ |
| Compromise application runtime | Đọc bộ nhớ, gọi KMS hoặc lấy plaintext sau giải mã | Workload identity, least privilege, isolation, monitoring và giảm thời gian plaintext tồn tại |
| Lộ KMS credential | Gọi các thao tác key ngoài ý muốn | IAM giới hạn key/operation/context, credential ngắn hạn, alert và revoke |
| Lộ một DEK | Giải mã dữ liệu được mã hóa bằng DEK đó | DEK scope nhỏ, per-record/per-object và quy trình re-encryption |
| Lộ KEK | Mở bọc các DEK được bảo vệ bởi KEK | KEK trong KMS/HSM, policy nghiêm ngặt, rotation/rewrap và đánh giá phạm vi |
| Người nội bộ lạm dụng quyền | Truy cập dữ liệu hợp lệ nhưng sai mục đích | JIT, MFA, approval, SoD, audit và access review |
| Rò rỉ qua log/CDC/cache | Plaintext được sao chép sang hệ thống phụ | Data minimization, redaction, encryption và quyền truy cập riêng |

Một thiết kế cần nói rõ giới hạn. Application-level encryption bảo vệ database dump khi kẻ tấn công chỉ có bản sao ciphertext. Nó không tự bảo vệ plaintext nếu ứng dụng đang chạy bị chiếm quyền và có thể gọi decrypt. Tương tự, TDE giúp bảo vệ file database và backup theo cơ chế của nền tảng, nhưng không ngăn một truy vấn SQL hợp lệ đọc dữ liệu ở dạng rõ.

## 3. Chọn lớp mã hóa phù hợp

Có thể triển khai nhiều lớp cùng lúc vì mỗi lớp bảo vệ một ranh giới khác nhau.

| Lớp | Mã hóa ở đâu? | Bảo vệ tốt trước | Không giải quyết đầy đủ |
|---|---|---|---|
| TLS | Giữa client, service, database và KMS | Nghe lén hoặc sửa dữ liệu trên đường truyền | Quyền truy cập plaintext ở endpoint |
| Disk/volume encryption | Ổ đĩa hoặc volume | Mất phương tiện lưu trữ, truy cập block trái phép khi đã khóa | Tài khoản DB hợp lệ truy vấn dữ liệu |
| Database TDE | File database, log và phạm vi được sản phẩm hỗ trợ | Database files hoặc backup bị sao chép | DBA hoặc ứng dụng có quyền đọc dữ liệu |
| Column/field encryption | Một số cột hoặc trường nhạy cảm | Database dump, một số trường hợp DBA chỉ có quyền đọc ciphertext | Compromise ứng dụng/KMS có quyền giải mã |
| Application-level envelope encryption | Ứng dụng mã hóa bằng DEK, KMS bảo vệ DEK | Rò rỉ ciphertext và bản backup không có quyền KMS | Runtime ứng dụng hoặc principal decrypt bị chiếm quyền |
| Tokenization | Thay dữ liệu bằng token tham chiếu | Giảm lưu trữ trực tiếp dữ liệu nhạy cảm | Compromise token vault hoặc luồng ánh xạ token |

Một cấu hình thực tế có thể dùng TLS cho mọi kết nối, TDE cho database volume và application-level encryption cho các trường nhạy cảm nhất. Backup cần được bảo vệ riêng theo đường đi và nơi lưu giữ.

### Khi nào chỉ dùng TDE là đủ?

TDE có thể phù hợp nếu threat model chủ yếu là mất thiết bị, lộ file database hoặc backup ở tầng lưu trữ, và tài khoản quản trị database được kiểm soát tốt. TDE đơn giản hóa ứng dụng vì database tự xử lý mã hóa/giải mã.

Nếu cần giảm khả năng DBA, tài khoản database hoặc bản dump đọc được các trường nhạy cảm, cần xem xét mã hóa ở tầng ứng dụng hoặc một cơ chế column encryption có ranh giới tin cậy phù hợp. Cần kiểm tra cụ thể nơi plaintext xuất hiện, cách quản lý key và khả năng truy vấn của sản phẩm.

### Khi nào dùng field-level encryption?

Field-level encryption phù hợp với những trường có mức nhạy cảm cao và ít cần truy vấn trực tiếp bằng phép so sánh hoặc sắp xếp. Ví dụ, mã định danh cá nhân hoặc dữ liệu xác minh có thể được mã hóa trước khi ghi xuống database.

Không nên mã hóa toàn bộ trường một cách máy móc. Các trường phục vụ join, filter, sort, aggregate hoặc uniqueness cần thiết kế riêng. Mã hóa ngẫu nhiên thông thường làm cho cùng một plaintext tạo ciphertext khác nhau, do đó database không thể tìm theo giá trị gốc bằng phép so sánh trực tiếp.

## 4. Kiến trúc tổng thể đề xuất

Thiết kế dùng ba lớp bảo vệ chính:

1. TLS cho mọi kết nối giữa client, ứng dụng, database và KMS.
2. TDE hoặc disk encryption cho database storage và các bản backup theo khả năng nền tảng.
3. Envelope encryption ở ứng dụng cho các trường nhạy cảm.

KMS/HSM giữ KEK. Ứng dụng yêu cầu KMS tạo DEK và nhận về DEK bản rõ dùng trong bộ nhớ cùng bản DEK đã được bọc. Ứng dụng mã hóa payload bằng DEK, lưu ciphertext và encrypted DEK vào database. Khi đọc, ứng dụng kiểm tra quyền truy cập trước, yêu cầu KMS mở bọc DEK, xác minh AEAD tag và chỉ sau đó mới trả plaintext cho caller được phép.

~~~mermaid
flowchart TD
    U[Client đã xác thực] -->|HTTPS/TLS| A[Application service]
    A -->|Authorization và tenant check| P[Policy layer]
    A -->|TLS + workload identity| K[KMS/HSM giữ KEK]
    K -->|DEK bản rõ + encrypted DEK| A
    A -->|DEK bản rõ trong bộ nhớ| C[AES-GCM encryption]
    C -->|Ciphertext + nonce + metadata| D[(Database)]
    C -->|Encrypted DEK| D
    D -->|Ciphertext + encrypted DEK| A
    A -->|Decrypt DEK theo context| K
    K -->|DEK bản rõ trong bộ nhớ| A
    A -->|AEAD verify + decrypt| U
    D -.->|TDE / volume encryption| S[Encrypted storage]
    D -.->|Encrypted backup| B[Backup repository]
~~~

Database chỉ lưu ciphertext của trường nhạy cảm và encrypted DEK. KMS giữ KEK, kiểm soát quyền mở bọc và ghi audit event. Ứng dụng là nơi plaintext xuất hiện trong thời gian xử lý, vì vậy runtime, log, tracing, crash dump và quyền workload phải được bảo vệ.

## 5. Phân cấp key: KEK và DEK

Envelope encryption tách key dùng mã hóa dữ liệu khỏi key dùng bảo vệ các key khác.

- **DEK (Data Encryption Key):** mã hóa payload hoặc trường dữ liệu.
- **KEK (Key Encryption Key):** bọc và mở bọc DEK.
- **KMS/HSM:** quản lý KEK, policy, version, audit và thao tác cryptographic.

Ví dụ một hệ thống có thể dùng KEK riêng theo môi trường và data domain:

| KEK | Phạm vi | Principal được phép |
|---|---|---|
| kek-prod-customer-v1 | Dữ liệu hồ sơ khách hàng production | Workload customer service và nhóm vận hành được phê duyệt |
| kek-prod-payment-v1 | Dữ liệu thanh toán production | Workload payment service |
| kek-staging-customer-v1 | Dữ liệu staging đã giảm nhạy cảm | Workload staging |
| kek-backup-prod-v1 | Bảo vệ gói backup theo thiết kế riêng | Backup/recovery service |

Tên trên chỉ là ví dụ định danh. Trong production, nên dùng immutable key ID hoặc ARN và metadata version rõ ràng. Alias có thể hữu ích cho cấu hình hiện hành, nhưng không nên là thông tin duy nhất để giải mã dữ liệu lịch sử nếu alias có thể trỏ sang key khác.

### Chọn phạm vi của DEK

Có ba lựa chọn thường gặp:

| Phạm vi DEK | Ưu điểm | Đánh đổi |
|---|---|---|
| Mỗi trường hoặc mỗi bản ghi | Giới hạn blast radius nhỏ, dễ cô lập và xóa theo đối tượng | Nhiều DEK, nhiều encrypted envelope và chi phí KMS cao hơn |
| Mỗi aggregate/khách hàng | Cân bằng giữa cô lập và hiệu năng | Một DEK bảo vệ nhiều trường của cùng khách hàng; rotation cần xử lý cả aggregate |
| Mỗi tenant hoặc nhóm dữ liệu lớn | Ít key và ít thao tác KMS | Blast radius lớn; một key compromise ảnh hưởng nhiều dữ liệu |

Với ví dụ này, chọn DEK theo một hồ sơ khách hàng hoặc một aggregate có phạm vi nhỏ. Một DEK có thể mã hóa một payload chứa các trường nhạy cảm của hồ sơ. Nếu có yêu cầu cô lập cao hơn, có thể dùng DEK riêng cho từng trường hoặc đối tượng. Cần giới hạn số lượng dữ liệu và số phép toán trên mỗi DEK theo thuật toán và policy.

Không nên tạo một DEK toàn cục cho mọi tenant. Cách đó làm tăng phạm vi ảnh hưởng và khiến việc cô lập hoặc hủy dữ liệu theo tenant khó hơn.

### Vì sao không lưu KEK trong database?

Nếu KEK được lưu cùng database với encrypted DEK, kẻ lấy được database có thể có cả ciphertext và phương tiện mở bọc. KEK nên nằm trong ranh giới KMS/HSM độc lập, với policy xác định principal và operation được phép. Database chỉ lưu định danh key và encrypted DEK.

## 6. Thiết kế schema để lưu ciphertext và metadata

Ứng dụng cần lưu đủ thông tin để giải mã về sau. Không được chỉ lưu ciphertext mà bỏ mất nonce, key reference hoặc phiên bản AAD.

Một mô hình đơn giản gồm bảng envelope và bảng dữ liệu mã hóa. SQL dưới đây dùng kiểu dữ liệu PostgreSQL; cần ánh xạ sang kiểu tương đương của database đang triển khai:

~~~sql
CREATE TABLE customer_key_envelopes (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    encrypted_dek BYTEA NOT NULL,
    kek_key_id TEXT NOT NULL,
    kek_key_version TEXT NOT NULL,
    wrapping_mechanism TEXT NOT NULL,
    key_context_version SMALLINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE customer_sensitive_fields (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    field_name TEXT NOT NULL,
    ciphertext BYTEA NOT NULL,
    nonce BYTEA NOT NULL,
    algorithm TEXT NOT NULL,
    aad_version SMALLINT NOT NULL,
    schema_version INTEGER NOT NULL,
    row_version BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, customer_id, field_name),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customer_key_envelopes (tenant_id, customer_id)
);
~~~

Trong ví dụ, ciphertext chứa cả ciphertext và authentication tag theo cách API AES-GCM trả về. Nếu sản phẩm hoặc định dạng lưu trữ tách tag thành cột riêng, cần lưu rõ và kiểm tra khi đọc.

Các trường metadata có ý nghĩa:

| Trường | Mục đích |
|---|---|
| tenant_id, customer_id | Xác định phạm vi dữ liệu và kiểm tra tenant |
| encrypted_dek | DEK đã được KMS bọc |
| kek_key_id, kek_key_version | Xác định key dùng để mở bọc DEK |
| wrapping_mechanism | Ghi nhận cơ chế/provider dùng để bảo vệ DEK |
| nonce | Nonce dùng cho AEAD; cần lưu cùng ciphertext |
| algorithm | Thuật toán mã hóa dữ liệu |
| aad_version | Phiên bản quy tắc tạo associated data |
| schema_version | Phiên bản cấu trúc payload |
| row_version | Hỗ trợ optimistic concurrency khi update/rotation |

Key ID, key version, nonce và AAD không phải bí mật theo nghĩa key material, nhưng cần bảo vệ tính toàn vẹn. Thay đổi metadata sai có thể làm dữ liệu không giải mã được hoặc khiến ứng dụng áp dụng sai context.

Cần có index và constraint để tránh ghép encrypted DEK của khách hàng này với ciphertext của khách hàng khác. Khóa ngoại trong ví dụ chỉ là một lớp bảo vệ; ứng dụng vẫn phải xác thực tenant và resource ở mọi request.

## 7. Chọn thuật toán và định dạng ciphertext

Với dữ liệu nhạy cảm trong database, một lựa chọn phổ biến là authenticated encryption with associated data (AEAD), chẳng hạn AES-GCM, khi được triển khai theo policy và thư viện đã phê duyệt.

AES-GCM cung cấp:

- Mã hóa để bảo vệ confidentiality.
- Authentication tag để phát hiện ciphertext hoặc AAD bị sửa.
- Associated data để ràng buộc ciphertext với metadata như tenant, record và field.

Một profile có thể quy định:

| Thành phần | Ví dụ lựa chọn |
|---|---|
| Data encryption | AES-256-GCM |
| DEK | 256-bit ngẫu nhiên từ KMS hoặc CSPRNG được phê duyệt |
| Nonce | 96-bit, sinh mới cho mỗi lần mã hóa với cùng key |
| Authentication tag | 128-bit |
| AAD | tenant ID, record ID, field name, schema version, AAD version |
| DEK wrapping | Cơ chế KMS/HSM được phê duyệt |
| Encoding | Binary envelope hoặc định dạng versioned có schema rõ |

Các giá trị này là profile thiết kế minh họa; cần đối chiếu policy mật mã, thư viện, KMS/HSM và yêu cầu triển khai của tổ chức trước khi áp dụng.

### Nonce phải duy nhất theo key

Với AES-GCM, không được tái sử dụng cùng nonce với cùng key. Nếu dùng một DEK cho nhiều trường, mỗi lần mã hóa phải có nonce mới. Nonce ngẫu nhiên có xác suất va chạm dù rất nhỏ; với DEK dùng cho nhiều lần ghi hoặc nhiều instance đồng thời, cần theo dõi số lần mã hóa và lượng dữ liệu, áp dụng giới hạn theo profile mật mã, hoặc dùng cơ chế cấp nonce có tính duy nhất được thiết kế an toàn. Rotation DEK phải diễn ra trước khi chạm giới hạn sử dụng đã phê duyệt. Nếu không thể bảo đảm quản lý nonce an toàn, cần thay đổi phạm vi DEK hoặc dùng cơ chế được thiết kế phù hợp.

Không dùng timestamp hoặc record ID làm nonce cố định. Nonce ngẫu nhiên 96-bit là lựa chọn phổ biến trong nhiều thiết kế, nhưng hệ thống phải xét số lượng lần mã hóa trên cùng key và giới hạn của profile đã chọn.

### AAD ràng buộc dữ liệu với đúng ngữ cảnh

AAD không được mã hóa nhưng được xác thực cùng ciphertext. Ví dụ:

- Tenant ID.
- Customer ID.
- Tên trường.
- Phiên bản schema.
- Phiên bản quy tắc AAD.

Nếu attacker chuyển ciphertext từ tenant A sang tenant B, ứng dụng tạo AAD cho tenant B; tag sẽ không xác minh nếu ciphertext ban đầu được tạo với AAD tenant A.

AAD phải được serialize theo một định dạng canonical. Không nối chuỗi tùy tiện vì các chuỗi khác nhau có thể tạo cùng biểu diễn nếu không có ranh giới trường rõ ràng. Khi thay đổi quy tắc AAD, phải tăng aad_version và duy trì khả năng giải mã dữ liệu cũ trong migration.

## 8. Luồng ghi dữ liệu

Khi ứng dụng nhận yêu cầu cập nhật một hồ sơ khách hàng, luồng ghi có thể diễn ra:

1. Xác thực người gọi và kiểm tra quyền sửa đúng customer thuộc tenant.
2. Xác định các trường cần mã hóa và schema version.
3. Gọi KMS bằng workload identity để tạo DEK cho phạm vi hồ sơ.
4. Nhận DEK bản rõ trong bộ nhớ và encrypted DEK.
5. Tạo nonce mới và canonical AAD.
6. Mã hóa payload bằng AES-GCM.
7. Ghi encrypted DEK, ciphertext, nonce, key ID/version và metadata trong cùng transaction database.
8. Không ghi plaintext hoặc DEK bản rõ vào log, tracing hay message queue.
9. Giải phóng tham chiếu đến DEK bản rõ sau khi hoàn thành.

Khi KMS tạo DEK nhưng transaction database thất bại, có thể phát sinh encrypted envelope chưa được tham chiếu. Đây là orphaned envelope; cần có quy trình retry hoặc dọn dẹp theo inventory. Không được lưu DEK bản rõ vào hàng đợi để retry.

Nếu một hồ sơ gồm nhiều trường mã hóa bằng cùng DEK, cần bảo đảm nonce riêng cho từng lần mã hóa và AAD khác nhau theo field. Nếu transaction thất bại giữa chừng, cần tránh trạng thái chỉ một phần trường đã được cập nhật. Có thể dùng một transaction chứa toàn bộ metadata/ciphertext, hoặc một trạng thái versioned record để reader không trộn các phiên bản.

## 9. Luồng đọc và giải mã dữ liệu

Luồng đọc phải kiểm tra authorization trước khi yêu cầu KMS mở bọc DEK.

1. Xác thực principal và xác minh quyền đọc customer thuộc tenant tương ứng.
2. Truy xuất ciphertext cùng encrypted DEK và metadata.
3. Kiểm tra tenant ID, customer ID, field name, algorithm, AAD version và key reference.
4. Gọi KMS decrypt/unwrap với key ID/version và encryption context đã lưu.
5. Nhận DEK bản rõ trong bộ nhớ.
6. Tạo lại đúng canonical AAD từ dữ liệu đã xác thực.
7. Dùng AES-GCM xác minh tag và giải mã.
8. Nếu tag không hợp lệ, từ chối plaintext và ghi security event.
9. Trả dữ liệu cho thành phần được phép; không ghi plaintext vào log.
10. Giảm thời gian giữ DEK và plaintext trong bộ nhớ.

Nếu tenant check được thực hiện sau khi giải mã, một lỗi authorization có thể khiến ứng dụng vô tình mở dữ liệu của tenant khác. Do đó, kiểm tra principal, tenant và resource cần diễn ra trước thao tác decrypt.

Lỗi authentication tag phải được xử lý như lỗi integrity hoặc context mismatch. Không được bỏ qua tag, thử giải mã bằng chế độ không xác thực hoặc trả về một phần plaintext. API bên ngoài nên tránh tiết lộ chi tiết nội bộ giúp attacker xây dựng oracle.

## 10. Ví dụ Java 17 cho AES-GCM và envelope encryption

Ví dụ dưới đây minh họa một DEK cho một hồ sơ khách hàng (aggregate). Ứng dụng tạo envelope một lần, dùng cùng DEK để mã hóa các trường thuộc hồ sơ đó với nonce mới cho mỗi trường, rồi lưu envelope và ciphertext trong cùng transaction. KmsClient là interface đại diện cho adapter của nhà cung cấp; implementation thực tế phải dùng workload identity, policy, timeout, retry và audit phù hợp.

~~~java
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;

public final class DatabaseFieldCrypto {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int DEK_BYTES = 32;
    private static final int AAD_VERSION = 1;

    private final SecureRandom random = new SecureRandom();
    private final KmsClient kms;

    public DatabaseFieldCrypto(KmsClient kms) {
        this.kms = kms;
    }

    public GeneratedEnvelope createCustomerEnvelope(
            String kekId, String tenantId, String customerId
    ) throws Exception {
        Map<String, String> context = context(tenantId, customerId);
        DataKey generated = kms.generateDataKey(kekId, DEK_BYTES, context);
        byte[] plaintextDek = generated.plaintextKey();
        if (plaintextDek == null || plaintextDek.length != DEK_BYTES) {
            destroyDek(plaintextDek);
            throw new SecurityException("Invalid KMS DEK length");
        }
        if (generated.encryptedKey() == null || generated.encryptedKey().length == 0
                || generated.keyId() == null || generated.keyVersion() == null) {
            destroyDek(plaintextDek);
            throw new SecurityException("Incomplete KMS data-key response");
        }

        Envelope envelope = new Envelope(
                generated.encryptedKey(),
                generated.keyId(),
                generated.keyVersion(),
                tenantId,
                customerId,
                "KMS-ENVELOPE",
                1
        );
        return new GeneratedEnvelope(plaintextDek, envelope);
    }

    public byte[] openCustomerEnvelope(
            Envelope envelope,
            String expectedTenantId,
            String expectedCustomerId
    ) throws Exception {
        if (!envelope.tenantId().equals(expectedTenantId)
                || !envelope.customerId().equals(expectedCustomerId)
                || envelope.contextVersion() != 1
                || !"KMS-ENVELOPE".equals(envelope.wrappingMechanism())
                || envelope.encryptedDek() == null
                || envelope.encryptedDek().length == 0
                || envelope.kekId() == null
                || envelope.kekVersion() == null) {
            throw new SecurityException("Envelope context mismatch");
        }
        return kms.decryptDataKey(
                envelope.encryptedDek(),
                envelope.kekId(),
                envelope.kekVersion(),
                context(expectedTenantId, expectedCustomerId)
        );
    }

    public EncryptedField encryptField(
            byte[] dek,
            String tenantId,
            String customerId,
            String fieldName,
            int schemaVersion,
            byte[] plaintext
    ) throws Exception {
        requireDek(dek);
        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                new SecretKeySpec(dek, "AES"),
                new GCMParameterSpec(TAG_BITS, nonce)
        );
        cipher.updateAAD(aad(
                tenantId, customerId, fieldName,
                schemaVersion, AAD_VERSION
        ));

        return new EncryptedField(
                cipher.doFinal(plaintext),
                nonce,
                "AES-256-GCM",
                AAD_VERSION,
                schemaVersion
        );
    }

    public byte[] decryptField(
            byte[] dek,
            String expectedTenantId,
            String expectedCustomerId,
            String fieldName,
            EncryptedField value
    ) throws Exception {
        requireDek(dek);
        if (!"AES-256-GCM".equals(value.algorithm())
                || value.aadVersion() != AAD_VERSION
                || value.nonce() == null
                || value.nonce().length != NONCE_BYTES
                || value.ciphertextAndTag() == null
                || value.ciphertextAndTag().length < TAG_BITS / 8) {
            throw new SecurityException("Unsupported encryption profile");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                new SecretKeySpec(dek, "AES"),
                new GCMParameterSpec(TAG_BITS, value.nonce())
        );
        cipher.updateAAD(aad(
                expectedTenantId,
                expectedCustomerId,
                fieldName,
                value.schemaVersion(),
                value.aadVersion()
        ));

        try {
            return cipher.doFinal(value.ciphertextAndTag());
        } catch (AEADBadTagException e) {
            throw new SecurityException(
                    "Ciphertext authentication failed", e
            );
        }
    }

    private static void requireDek(byte[] dek) {
        if (dek == null || dek.length != DEK_BYTES) {
            throw new SecurityException("Invalid DEK length");
        }
    }

    public static void destroyDek(byte[] dek) {
        if (dek != null) {
            Arrays.fill(dek, (byte) 0);
        }
    }

    private static Map<String, String> context(
            String tenantId, String customerId) {
        return Map.of(
                "purpose", "customer-database-aggregate",
                "tenant", tenantId,
                "customer", customerId
        );
    }

    private static byte[] aad(
            String tenantId,
            String customerId,
            String fieldName,
            int schemaVersion,
            int aadVersion) {

        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);

            out.writeInt(aadVersion);
            writeText(out, tenantId);
            writeText(out, customerId);
            writeText(out, fieldName);
            out.writeInt(schemaVersion);
            out.flush();

            return bytes.toByteArray();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static void writeText(
            DataOutputStream out, String value) throws IOException {
        byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(encoded.length);
        out.write(encoded);
    }

    public interface KmsClient {
        DataKey generateDataKey(
                String kekId, int bytes, Map<String, String> context
        ) throws Exception;

        byte[] decryptDataKey(
                byte[] encryptedKey,
                String kekId,
                String keyVersion,
                Map<String, String> context
        ) throws Exception;
    }

    public record DataKey(
            byte[] plaintextKey,
            byte[] encryptedKey,
            String keyId,
            String keyVersion
    ) {}

    public record GeneratedEnvelope(byte[] plaintextDek, Envelope envelope) {}

    public record Envelope(
            byte[] encryptedDek,
            String kekId,
            String kekVersion,
            String tenantId,
            String customerId,
            String wrappingMechanism,
            int contextVersion
    ) {}

    public record EncryptedField(
            byte[] ciphertextAndTag,
            byte[] nonce,
            String algorithm,
            int aadVersion,
            int schemaVersion
    ) {}
}
~~~

Khi ghi một hồ sơ, ứng dụng gọi createCustomerEnvelope, mã hóa từng trường bằng plaintextDek với nonce mới, rồi lưu envelope và tất cả EncryptedField trong cùng transaction. Sau transaction, ứng dụng gọi destroyDek trong khối finally. Khi đọc, ứng dụng gọi openCustomerEnvelope một lần, giải mã các trường được phép bằng cùng DEK, rồi gọi destroyDek. Nếu transaction ghi thất bại, envelope có thể trở thành orphaned nhưng plaintext DEK không được đưa vào queue hoặc log để retry.

Trong ứng dụng thực tế, DTO lưu ciphertext, nonce và encrypted DEK phải defensive-copy các mảng byte. Đối tượng giữ DEK bản rõ cần có ownership rõ ràng và API đóng/hủy để xóa đúng mảng đang giữ; không trả defensive copy rồi vô tình chỉ xóa bản sao. Cần kiểm tra độ dài DEK, nonce và ciphertext; xác minh key ID/version do KMS trả về; và chỉ chấp nhận algorithm/AAD version trong allowlist.

Một số điểm cần bổ sung trong adapter thực tế:

- Dùng workload identity và kiểm tra policy cho từng key/operation.
- Áp dụng timeout và retry có giới hạn cho KMS; không retry mù các thao tác có side effect.
- Không log request/response chứa DEK bản rõ hoặc plaintext.
- Việc Arrays.fill chỉ là biện pháp best-effort trong JVM; garbage collector và bản sao bộ nhớ có thể khiến không thể bảo đảm zeroization tuyệt đối.
- Kiểm thử tenant mismatch, sai AAD, ciphertext bị sửa, nonce sai độ dài và encrypted DEK bị tráo.
- Kiểm tra schema version và AAD version trước khi gọi KMS để tránh tạo decrypt oracle.

## 11. Truy vấn, index và tìm kiếm trên dữ liệu mã hóa

Mã hóa ngẫu nhiên khiến database không thể trực tiếp tìm plaintext bằng equality, range hoặc prefix query. Đây là hệ quả cần xử lý trong thiết kế dữ liệu.

### Tách trường hiển thị và trường tìm kiếm

Ví dụ, email được mã hóa để hiển thị cho người có quyền. Nếu nghiệp vụ cần tìm khách hàng theo email, có thể tạo một blind index bằng HMAC với key riêng:

- Chuẩn hóa email theo quy tắc nghiệp vụ.
- Tính HMAC bằng một search key riêng.
- Lưu giá trị HMAC trong cột index.
- Khi tìm kiếm, chuẩn hóa input và tính lại HMAC.
- Chỉ trả kết quả sau khi kiểm tra quyền và xác minh dữ liệu cần thiết.

Blind index làm lộ khả năng so sánh bằng nhau và có thể tiết lộ tần suất hoặc quan hệ trùng lặp. Nó không tương đương với mã hóa ngẫu nhiên và không che giấu mọi thông tin thống kê. Search key phải tách khỏi DEK/KEK, có policy và rotation riêng.

Không dùng cùng key mã hóa dữ liệu làm HMAC key. Nếu cần hỗ trợ nhiều kiểu truy vấn, phải đánh giá leakage trước khi chọn searchable encryption hoặc tokenization.

### Những truy vấn khó hỗ trợ

- Range query trên số tiền hoặc ngày tháng.
- Prefix search trên tên/email.
- Sort theo giá trị plaintext.
- Aggregate trực tiếp trên trường mã hóa.
- Unique constraint trên plaintext.

Có thể giữ một số thuộc tính ít nhạy cảm ở dạng rõ, dùng tokenization, blind index có giới hạn hoặc chuyển truy vấn sang dịch vụ chuyên biệt. Mỗi lựa chọn cần ghi rõ dữ liệu nào bị lộ qua index và ai có thể truy vấn.

## 12. Multi-tenant isolation

Với SaaS nhiều tenant, tenant isolation cần được thực hiện ở nhiều lớp:

1. Xác thực tenant từ identity hoặc session tin cậy; không chỉ tin vào tenant ID do client gửi.
2. Query database luôn ràng buộc tenant ID.
3. AAD chứa tenant ID và record ID theo canonical encoding.
4. KMS encryption context chứa tenant và purpose nếu provider hỗ trợ.
5. IAM/policy giới hạn workload theo key hoặc key family được phép.
6. DEK scope đủ nhỏ để giảm blast radius.
7. Audit ghi tenant context và principal đã xác thực.

Nếu mỗi tenant có KEK riêng, khả năng cô lập tăng nhưng số lượng key và chi phí vận hành cũng tăng. Nếu nhiều tenant dùng chung KEK nhưng DEK riêng, cần policy và AAD mạnh để ngăn tráo ciphertext; tuy vậy, compromise KEK có thể ảnh hưởng nhiều tenant. Lựa chọn phụ thuộc mức cô lập, số tenant, chi phí và khả năng quản trị.

Không dùng AAD như cơ chế authorization duy nhất. AAD bảo vệ tính gắn kết của ciphertext với context; authorization phải kiểm tra người gọi có quyền đọc resource tương ứng.

## 13. Kiểm soát truy cập tới database và KMS

Cần tách quyền ứng dụng, con người và dịch vụ vận hành.

| Principal | Quyền nên có | Giới hạn |
|---|---|---|
| Customer API workload | GenerateDataKey/Decrypt cho KEK của customer domain | Chỉ môi trường production và operation được yêu cầu |
| Payment workload | Sử dụng key payment domain | Không truy cập key customer domain nếu không có lý do |
| Database service account | Đọc/ghi ciphertext và metadata | Không có quyền gọi KMS trực tiếp |
| DBA | Quản trị schema, backup và hiệu năng | Không mặc nhiên có quyền decrypt plaintext |
| Key operator | Quản trị metadata/rotation theo quy trình | JIT, ticket, approval và audit |
| Security approver | Phê duyệt thay đổi nhạy cảm | Không tự thực hiện mọi thao tác |
| Auditor | Đọc log, policy và evidence | Không sửa policy hoặc xóa log |
| Backup/recovery workload | Thao tác cần thiết để restore | Chỉ trong recovery scope được phê duyệt |

Workload nên dùng workload identity hoặc credential ngắn hạn thay cho access key tĩnh. Quyền decrypt phải được giới hạn theo key, operation, context và môi trường. Quyền thay đổi policy, export key material và schedule deletion cần kiểm soát đặc biệt.

Với thao tác con người trên production, dùng JIT/PAM, MFA mạnh, ticket và approval độc lập. Mỗi thao tác phải có principal riêng để audit xác định được ai đã làm gì.

## 14. Rotation và migration dữ liệu

Rotation có hai phạm vi thường bị nhầm lẫn:

- **KEK rotation:** thay key bảo vệ DEK. Có thể rewrap encrypted DEK sang KEK mới mà không cần mã hóa lại toàn bộ ciphertext.
- **DEK rotation:** thay key mã hóa payload. Cần giải mã và mã hóa lại dữ liệu bằng DEK mới.

TDE master key hoặc database encryption key có quy trình riêng của sản phẩm database; không nên gộp với rotation của DEK ở tầng ứng dụng.

### KEK rotation

Một quy trình có thể gồm:

1. Tạo KEK mới và xác minh policy.
2. Cấu hình dữ liệu ghi mới dùng KEK mới.
3. Duy trì khả năng mở bọc DEK cũ bằng KEK cũ.
4. Rewrap encrypted DEK theo batch.
5. Ghi key ID/version mới cùng encrypted DEK trong transaction.
6. Dùng optimistic concurrency để tránh ghi đè cập nhật đồng thời.
7. Kiểm tra restore và dữ liệu lịch sử.
8. Chỉ loại bỏ KEK cũ sau khi dependency inventory chứng minh không còn encrypted DEK cần nó.

Một số KMS hỗ trợ rotation nội bộ và tự quản lý phiên bản key. Semantics phụ thuộc provider: key ID có thể giữ nguyên trong khi backing key material thay đổi; ciphertext cũ vẫn có thể giải mã bằng phiên bản trước. Phải kiểm tra tài liệu và API của provider, không giả định mọi dịch vụ có cùng hành vi.

### DEK rotation

Với DEK rotation, dùng chiến lược dual-read/single-write:

- Reader hỗ trợ giải mã phiên bản cũ và mới.
- Writer chỉ ghi ciphertext mới bằng DEK hiện hành.
- Job migration đọc record theo batch, giải mã, mã hóa lại, rồi cập nhật bằng compare-and-swap dựa trên row_version.
- Nếu record đã được cập nhật bởi request mới, job bỏ qua và đọc lại.
- Ghi migration state để retry có tính idempotent.
- Chỉ hủy key cũ sau khi kiểm tra toàn bộ backup, replica, archive và legal hold.

~~~mermaid
flowchart TD
    A[Đăng ký key version mới] --> B[Writer chuyển sang DEK mới]
    B --> C[Reader hỗ trợ v1 và v2]
    C --> D[Migration worker đọc record v1]
    D --> E[Decrypt bằng DEK v1]
    E --> F[Encrypt bằng DEK v2]
    F --> G{row_version còn đúng?}
    G -->|Có| H[CAS update ciphertext + envelope]
    G -->|Không| I[Đọc lại record mới nhất]
    I --> D
    H --> J[Kiểm tra số record còn v1]
    J --> K{Còn dependency?}
    K -->|Có| D
    K -->|Không| L[Đánh giá backup và phê duyệt retire v1]
~~~

Không xóa key cũ ngay khi writer đã chuyển sang key mới. Các record chưa migrate và backup lịch sử có thể vẫn cần phiên bản cũ.

## 15. Backup, restore và disaster recovery

Backup database chỉ hữu ích nếu có thể khôi phục cả ciphertext, encrypted DEK, metadata và khả năng gọi KMS đúng cách.

Một gói backup cần bảo đảm:

- Ciphertext và nonce được lưu đầy đủ.
- Encrypted DEK và key ID/version không bị tách khỏi record.
- AAD version và schema version được giữ nguyên.
- KEK cần thiết vẫn tồn tại và có thể sử dụng trong recovery.
- Recovery workload có quyền phù hợp nhưng không có quyền quá rộng.
- Backup được mã hóa, kiểm tra integrity và lưu trong miền phục hồi độc lập.
- Restore drill được thực hiện trong môi trường cô lập.

Một lỗi thường gặp là backup database thành công nhưng key KMS chỉ tồn tại trong account hoặc region không thể truy cập trong DR. Khi đó, dữ liệu đã restore vẫn không giải mã được. Cần thiết kế dependency map và quy trình phục hồi KMS/HSM trước khi sự cố xảy ra.

Không copy plaintext DEK vào backup để tránh phụ thuộc KMS. Nếu cần backup key material, phải tuân theo cơ chế backup/restore được bảo vệ của KMS/HSM, có quorum và kiểm soát độc lập.

## 16. Xóa dữ liệu và crypto-erasure

Khi người dùng yêu cầu xóa dữ liệu, cần phân biệt xóa row khỏi database, xóa bản sao backup theo retention, và crypto-erasure bằng cách hủy key cần thiết.

Nếu DEK được dùng riêng cho một record hoặc aggregate, việc hủy mọi bản sao DEK và encrypted DEK có thể làm ciphertext tương ứng không thể giải mã. Trong mô hình envelope encryption ở bài này, KMS giữ KEK còn DEK được tạo rồi bọc; vì vậy crypto-erasure phụ thuộc vào việc xử lý tất cả bản sao encrypted DEK trong database, replica, backup và archive, cùng mọi bản plaintext DEK còn sót. Nếu KEK vẫn tồn tại và encrypted DEK còn được lưu ở đâu đó, dữ liệu vẫn có thể khôi phục.

Một quy trình xóa cần:

1. Xác minh quyền và căn cứ xóa.
2. Kiểm tra retention, legal hold và dependency.
3. Xóa hoặc vô hiệu hóa dữ liệu theo chính sách.
4. Xử lý encrypted DEK và các bản sao liên quan.
5. Xác định thời điểm backup hết hạn hoặc được làm sạch.
6. Nếu dùng crypto-erasure, chứng minh mọi đường khôi phục key đều được kiểm soát.
7. Ghi audit evidence.

Không hủy KEK dùng chung cho nhiều khách hàng chỉ để xóa một hồ sơ. Phạm vi key phải đủ nhỏ để hỗ trợ mục tiêu xóa mà không làm mất dữ liệu của chủ thể khác.

## 17. Vận hành, giám sát và hiệu năng

Mã hóa database tạo thêm chi phí CPU, KMS request, network latency và công việc vận hành. Cần đo lường trên workload thực tế.

Các chỉ số hữu ích:

| Metric | Ý nghĩa |
|---|---|
| KMS request latency | Độ trễ khi tạo hoặc mở bọc DEK |
| KMS error/denied rate | Lỗi dịch vụ hoặc policy |
| Encrypt/decrypt latency | Chi phí xử lý tại ứng dụng |
| AEAD tag failure count | Sự cố integrity, metadata mismatch hoặc tampering |
| Records by key version | Tiến độ rotation và số record còn phụ thuộc key cũ |
| Wrapped DEK count by KEK | Phạm vi dependency của KEK |
| Cache hit/miss | Hiệu quả cache và mức độ tiếp xúc DEK |
| Restore success rate | Khả năng phục hồi thực tế |
| Orphaned envelope count | DEK đã tạo nhưng không gắn với record hợp lệ |

### Cache DEK

Cache DEK bản rõ có thể giảm số lần gọi KMS, nhưng làm tăng thời gian và phạm vi mà key material tồn tại trong bộ nhớ. Nếu dùng cache:

- Giới hạn theo workload, tenant và key version.
- Đặt TTL ngắn theo risk assessment.
- Không persist cache xuống disk.
- Có cơ chế invalidate khi key bị compromise hoặc quyền bị thu hồi.
- Không chia sẻ cache giữa tenant hoặc service không cùng trust boundary.
- Giám sát cache hit, expiry và invalidation.
- Cân nhắc ảnh hưởng của heap dump, core dump và crash reporting.

Cache không nên trở thành nơi lưu trữ DEK lâu dài. Nếu có yêu cầu không để DEK bản rõ rời khỏi KMS/HSM, dùng API thực hiện phép toán trong ranh giới bảo vệ thay vì client-side envelope encryption.

## 18. Xử lý sự cố và key compromise

Phản ứng phụ thuộc loại tài nguyên bị lộ:

| Sự cố | Tác động | Hành động chính |
|---|---|---|
| Database dump bị lộ | Attacker có ciphertext và metadata | Xác định trường mã hóa, kiểm tra KMS access và khả năng lộ plaintext ở nơi khác |
| Một DEK bản rõ bị lộ | Dữ liệu của record/aggregate tương ứng có thể bị giải mã | Cô lập record scope, tạo DEK mới, re-encrypt và điều tra nguồn lộ |
| KEK bị nghi ngờ compromise | Nhiều DEK được bọc có thể bị ảnh hưởng | Disable/contain theo provider, rotate KEK, rewrap DEK và đánh giá encrypted DEK đã bị lấy |
| KMS credential bị lộ | Attacker có thể gọi API trong phạm vi policy | Revoke credential/session, siết policy, tìm audit event và đánh giá decrypt/sign đã thực hiện |
| Plaintext bị ghi vào log | Dữ liệu đã lộ ở hệ thống logging | Hạn chế truy cập, xử lý retention/copy, xóa theo policy và đánh giá nghĩa vụ thông báo |
| AAD hoặc metadata bị sửa | Tag có thể thất bại hoặc dữ liệu bị gắn sai context | Fail closed, giữ bằng chứng và phục hồi metadata tin cậy |

Khi key compromise, rotation một mình không đủ. Cần xác định thời điểm compromise, ai có thể gọi operation, encrypted DEK nào đã bị sao chép và plaintext có thể đã xuất hiện ở đâu. Nếu dữ liệu đã bị giải mã và lấy đi, mã hóa lại không thu hồi được bản sao plaintext.

Không tự động hủy KEK ngay khi có nghi ngờ nếu hành động đó có thể phá hủy khả năng phục hồi hoặc điều tra. Cần phối hợp incident response, key owner và security approver để chọn containment, revocation, rotation và destruction theo mức độ sự cố.

## 19. Kiểm thử thiết kế

Kiểm thử phải bao phủ cả crypto correctness, authorization, data integrity, rotation và recovery.

| Nhóm | Kiểm thử | Kết quả mong đợi |
|---|---|---|
| Encryption | Mã hóa rồi giải mã payload hợp lệ | Nhận lại đúng plaintext |
| Nonce | Mỗi lần mã hóa tạo nonce mới | Không tái sử dụng nonce với cùng DEK |
| AEAD integrity | Sửa một byte ciphertext hoặc tag | Decrypt thất bại |
| AAD binding | Dùng sai tenant, record hoặc field | Decrypt thất bại |
| Key reference | Dùng sai KEK ID/version | Không mở bọc được DEK |
| Authorization | User tenant A đọc record tenant B | Bị từ chối trước khi gọi KMS |
| IAM | Workload gọi operation ngoài policy | KMS deny và ghi audit |
| Search index | Thay đổi search key hoặc normalization | Migration có kiểm soát, không làm lộ plaintext |
| KEK rotation | Rewrap một batch DEK | Ciphertext dữ liệu không đổi; encrypted DEK dùng key mới |
| DEK rotation | Re-encrypt record v1 sang v2 | Dữ liệu đọc được, row_version không bị ghi đè |
| Concurrent update | User cập nhật trong lúc migration | CAS phát hiện conflict và retry an toàn |
| Backup | Restore database cùng key dependencies | Giải mã được dữ liệu kiểm thử |
| KMS outage | KMS timeout hoặc unavailable | Request xử lý theo chính sách; không fallback sang plaintext |
| Logging | Tạo lỗi decrypt | Không có DEK, credential hoặc plaintext trong log |
| Deletion | Xóa record có backup và legal hold | Không hủy key trước khi dependency clearance |

Nên kiểm thử cả negative path. Một hệ thống mã hóa chỉ chứng minh được khả năng bảo vệ khi nó từ chối đúng các thao tác sai context, sai tenant, key bị disable hoặc tag không hợp lệ.

## 20. Kế hoạch triển khai theo giai đoạn

Một lộ trình có kiểm soát giúp giảm rủi ro migration:

1. **Inventory và phân loại:** xác định trường nhạy cảm, luồng dữ liệu, bản sao, backup, CDC, analytics và người có quyền truy cập.
2. **Threat model:** xác định đối thủ, trust boundary, mức lộ dữ liệu chấp nhận được và yêu cầu recovery.
3. **Crypto profile:** chọn AEAD, DEK scope, KEK hierarchy, AAD schema, nonce strategy và key versioning.
4. **KMS/IAM:** tạo key theo môi trường và data domain; thiết lập workload identity, policy, audit và approval.
5. **Schema migration:** thêm ciphertext, nonce, encrypted DEK, key reference, AAD version và row version.
6. **Application integration:** mã hóa khi ghi, authorization trước decrypt, redaction và error handling.
7. **Backfill:** mã hóa dữ liệu cũ theo batch, có checkpoint, retry idempotent và CAS.
8. **Dual-read/single-write:** hỗ trợ đọc plaintext cũ trong thời gian chuyển đổi có kiểm soát, writer mới chỉ ghi ciphertext.
9. **Cutover:** xác minh tỷ lệ dữ liệu đã mã hóa, dừng đọc plaintext và cập nhật quyền database.
10. **Rotation/recovery drill:** thử KEK rotation, DEK rotation, backup restore và KMS outage.
11. **Retire:** xử lý dữ liệu tạm, bản sao và key cũ sau khi đủ điều kiện.
12. **Continuous assurance:** theo dõi metrics, audit, access review, inventory và test định kỳ.

Nếu cần chạy migration trên dữ liệu production, cần có kế hoạch rollback, backup đã kiểm tra, giới hạn tốc độ và cách xử lý record được cập nhật đồng thời.

## 21. Các quyết định thiết kế cần ghi thành ADR

Một Architecture Decision Record (ADR) giúp đội phát triển, bảo mật và vận hành hiểu tại sao thiết kế được chọn.

ADR nên ghi:

- Phạm vi dữ liệu được mã hóa và lý do phân loại.
- Threat model và những giới hạn được chấp nhận.
- Lớp mã hóa: TLS, TDE, field encryption, backup encryption.
- Thuật toán, key size, nonce và tag profile.
- DEK scope và KEK hierarchy.
- Cách tạo canonical AAD và versioning.
- Schema lưu encrypted envelope.
- IAM role và operation được phép.
- Cơ chế rotation, rewrap, re-encryption và rollback.
- Backup, recovery, legal hold và deletion policy.
- Logging, monitoring, evidence và incident runbook.
- Người phê duyệt, owner và ngày review tiếp theo.

Không ghi secret, plaintext DEK, credential hoặc key material vào ADR. Chỉ ghi định danh key và metadata cần thiết.

## 22. Những sai lầm thường gặp

**Chỉ bật TDE rồi coi dữ liệu đã được bảo vệ khỏi DBA.** TDE thường giải mã dữ liệu cho database engine; tài khoản có quyền truy vấn vẫn có thể đọc plaintext.

**Lưu KEK cạnh database.** Nếu attacker lấy cả ciphertext lẫn KEK, envelope encryption mất phần lớn giá trị bảo vệ.

**Dùng một DEK cho mọi tenant.** Blast radius lớn và khó xử lý xóa hoặc compromise theo tenant.

**Không lưu nonce hoặc AAD version.** Dữ liệu có thể không giải mã được sau thay đổi ứng dụng.

**Tái sử dụng nonce với AES-GCM.** Điều này có thể làm suy giảm nghiêm trọng tính bảo mật của AEAD.

**Dùng deterministic encryption cho mọi trường để dễ tìm kiếm.** Equality và frequency leakage có thể tiết lộ thông tin về dữ liệu.

**Tin rằng AAD thay thế authorization.** AAD ràng buộc ciphertext với context; policy vẫn phải kiểm tra quyền của principal.

**Decrypt trước khi kiểm tra tenant.** Có thể tạo đường truy cập chéo tenant hoặc oracle không mong muốn.

**Xóa key cũ ngay sau rotation.** Backup và dữ liệu lịch sử có thể vẫn phụ thuộc phiên bản cũ.

**Không kiểm thử restore.** Backup ciphertext không có giá trị nếu không thể phục hồi KMS/KEK và mở bọc DEK.

**Cache DEK không giới hạn.** Key material có thể tồn tại lâu trong heap, dump hoặc process không còn đáng tin cậy.

**Ghi plaintext vào log hoặc tracing.** Một đường bảo vệ database có thể bị phá vỡ bởi hệ thống quan sát.

## 23. Checklist trước khi đưa vào production

- [ ] Dữ liệu được phân loại và có owner.
- [ ] Threat model xác định rõ tài sản, đối thủ và giới hạn.
- [ ] TLS được bật cho kết nối ứng dụng, database và KMS.
- [ ] TDE/disk encryption được cấu hình và kiểm tra theo nền tảng.
- [ ] Trường nhạy cảm được mã hóa ở tầng phù hợp.
- [ ] DEK và KEK được tách biệt.
- [ ] DEK scope được chọn theo blast radius và hiệu năng.
- [ ] KEK được quản lý trong KMS/HSM.
- [ ] Workload dùng identity ngắn hạn và least privilege.
- [ ] Key ID/version và metadata được lưu cùng ciphertext.
- [ ] Nonce, tag và AAD được lưu/kiểm tra đúng.
- [ ] AAD canonical ràng buộc tenant, record và field.
- [ ] Authorization được kiểm tra trước decrypt.
- [ ] Search index có key riêng và leakage được đánh giá.
- [ ] Không có plaintext hoặc key material trong log, trace và backup không bảo vệ.
- [ ] KEK rotation và DEK rotation có quy trình riêng.
- [ ] Migration có CAS, checkpoint, retry idempotent và rollback.
- [ ] Backup giữ encrypted DEK, metadata và dependency tới KMS.
- [ ] Restore drill xác minh giải mã được dữ liệu.
- [ ] Deletion và crypto-erasure xét đến replica, archive, backup và legal hold.
- [ ] Audit ghi principal, key, operation, context và kết quả.
- [ ] Có cảnh báo KMS denial, decrypt bất thường và AEAD tag failure.
- [ ] Có incident runbook cho DEK, KEK và credential compromise.
- [ ] Có test âm tính cho sai tenant, sai AAD, sai key version và ciphertext tampering.
- [ ] Có ADR, owner, approver và lịch review.

## 24. Kết luận

Thiết kế encryption cho database cần bắt đầu từ dữ liệu, threat model và ranh giới tin cậy. TLS bảo vệ dữ liệu trên đường truyền; TDE và disk encryption bảo vệ tầng lưu trữ; application-level envelope encryption giúp giữ các trường nhạy cảm ở dạng ciphertext trong database. KMS/HSM bảo vệ KEK, còn DEK mã hóa payload với AEAD và AAD ràng buộc dữ liệu vào đúng tenant, record và field.

Một thiết kế tốt còn phải xử lý truy vấn, multi-tenant isolation, quyền con người và workload, rotation, backup/recovery, xóa dữ liệu, hiệu năng và sự cố compromise. Key cũ cần được giữ khi dữ liệu hoặc backup còn phụ thuộc; plaintext và key material phải được hạn chế trong bộ nhớ và không xuất hiện trong log. Kiểm thử tag, context, authorization, migration và restore là điều kiện để chứng minh hệ thống hoạt động đúng.

Mã hóa database không chỉ là chọn AES và bật một tùy chọn trong database engine. Đó là thiết kế một chuỗi bảo vệ gồm dữ liệu, key, identity, policy, ứng dụng, backup và quy trình vận hành. Khi từng thành phần có phạm vi, owner, phiên bản và bằng chứng rõ ràng, tổ chức có thể bảo vệ dữ liệu nhạy cảm mà vẫn duy trì khả năng truy vấn, khôi phục và thay đổi key trong suốt vòng đời hệ thống.


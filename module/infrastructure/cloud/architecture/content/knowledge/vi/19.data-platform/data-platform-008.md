# Quản lý dữ liệu nhạy cảm và vòng đời dữ liệu phân tích

## 1. Vì sao dữ liệu phân tích cũng cần được quản trị như dữ liệu giao dịch?

Một nền tảng dữ liệu thường gom thông tin từ nhiều hệ thống: đơn hàng, thanh toán, tài khoản, ứng dụng di động, website, CRM, log vận hành, thiết bị và đối tác. Khi dữ liệu được sao chép vào data lake, warehouse, feature store, notebook hoặc môi trường thử nghiệm, phạm vi người có thể truy cập và số bản sao thường tăng nhanh. Dữ liệu vốn được bảo vệ trong một ứng dụng giao dịch có thể xuất hiện trong file export, bảng phân tích, cache, bản backup, log hoặc tập dữ liệu dùng để huấn luyện mô hình.

**Dữ liệu nhạy cảm không mất tính nhạy cảm khi được chuyển sang nền tảng phân tích.** Một bảng đã bỏ tên người dùng vẫn có thể nhận diện cá nhân qua email băm không có salt phù hợp, số điện thoại, vị trí chi tiết, timestamp hoặc kết hợp nhiều thuộc tính. Một bộ dữ liệu tổng hợp vẫn có thể tiết lộ thông tin nếu nhóm quá nhỏ hoặc cho phép truy vấn lặp để suy ra một cá nhân.

Quản lý dữ liệu nhạy cảm vì thế phải bao trùm toàn bộ vòng đời: thu thập, truyền, lưu, biến đổi, phân tích, chia sẻ, sao lưu, lưu trữ dài hạn và xóa. Mục tiêu là cho đúng người và đúng workload dùng đúng dữ liệu trong thời gian cần thiết, với khả năng chứng minh ai đã truy cập và dữ liệu đã được xử lý theo chính sách.

Trong module **CLOUD_ARCHITECTURE**, đây là một quyết định kiến trúc liên quan trực tiếp tới bảo mật, độ tin cậy, khả năng mở rộng, chi phí và vận hành. Thiết kế tốt cần cân bằng giá trị phân tích với quyền riêng tư, yêu cầu lưu trữ, tính sẵn sàng và khả năng kiểm toán theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân loại dữ liệu theo mức nhạy cảm, mục đích sử dụng và chủ sở hữu.
- Thiết kế data minimization, masking, pseudonymization, tokenization và encryption.
- Thiết lập identity, access control, row/column-level security và audit.
- Phân biệt retention, archival, legal hold và deletion.
- Thiết kế vòng đời dữ liệu từ ingestion đến raw, curated, serving và archive.
- Theo dõi lineage, catalog, quality, consent và quyền sử dụng dữ liệu.
- Lập chính sách lifecycle và kiểm thử việc xóa/khôi phục trên mọi bản sao.

## 2. Phân loại dữ liệu và xác định mức bảo vệ

Không thể kiểm soát hiệu quả nếu hệ thống không biết nó đang lưu dữ liệu gì. Bước đầu là xác định dataset, field, nguồn, owner, mục đích và mức độ nhạy cảm.

### 2.1. Ví dụ các lớp phân loại

| Lớp | Đặc điểm | Ví dụ | Kiểm soát thường cần |
| --- | --- | --- | --- |
| Public | Được phép công bố rộng | Danh mục sản phẩm công khai, tài liệu marketing đã duyệt | Integrity, change control và nguồn chính thức |
| Internal | Dùng trong tổ chức, không dành cho công chúng | Báo cáo nội bộ, mã sản phẩm nội bộ | Identity công ty, least privilege, audit |
| Confidential | Có thể gây thiệt hại nếu lộ | Giá hợp đồng, doanh thu, kế hoạch kinh doanh | Quyền theo nhóm, encryption, audit và hạn chế export |
| Restricted / Highly sensitive | Tác động lớn đến cá nhân, tài chính, an toàn hoặc nghĩa vụ pháp lý | Credential, dữ liệu định danh, payment data, hồ sơ nhạy cảm | Mục đích cụ thể, quyền rất hẹp, masking/tokenization, kiểm soát xuất dữ liệu và giám sát tăng cường |

Tên lớp và cách áp dụng phải phù hợp chính sách tổ chức và quy định pháp lý liên quan. Không nên mặc định cùng một nhãn “PII” có nghĩa bảo vệ giống nhau ở mọi quốc gia hoặc mọi ngành.

### 2.2. Nhận diện dữ liệu nhạy cảm ở cấp field

Một bảng có thể chứa nhiều mức nhạy cảm:

| Field | Phân loại gợi ý | Lý do |
| --- | --- | --- |
| order_id | Internal hoặc Confidential | ID giao dịch có thể liên kết tới hồ sơ khác |
| customer_email | Restricted/PII | Định danh và liên hệ trực tiếp |
| phone_number | Restricted/PII | Định danh và liên hệ trực tiếp |
| shipping_address | Restricted/PII | Vị trí và thông tin cá nhân |
| product_category | Public/Internal | Có thể ít nhạy cảm khi tách khỏi khách hàng |
| order_total | Confidential | Giá trị giao dịch và hành vi mua |
| payment_token | Restricted | Có thể cho phép truy cập dịch vụ thanh toán hoặc liên kết tài khoản |
| event_timestamp | Tùy ngữ cảnh | Có thể giúp suy ra hành vi và nhận diện khi ghép dữ liệu |

Không chỉ field riêng lẻ mới nhạy cảm. Một tập gồm tuổi, mã bưu chính, giới tính và timestamp có thể tạo tổ hợp đủ hiếm để nhận diện người. Phân loại phải xem xét khả năng liên kết (linkability) và bối cảnh truy cập.

### 2.3. Dataset inventory

Mỗi dataset quan trọng nên có metadata tối thiểu:

- Tên dataset, mô tả nghiệp vụ, schema và vị trí lưu.
- Data owner, technical custodian và steward.
- Nguồn thu thập, mục đích, căn cứ/quyền sử dụng và nhóm người dùng.
- Classification, field nhạy cảm, tenant/jurisdiction và consent/usage constraints nếu có.
- Retention, legal hold, backup, deletion method và thời hạn áp dụng.
- Downstream consumer, export, replica, cache và bản sao.
- Lineage, quality checks, access policy và audit location.

Không cần chờ catalog hoàn hảo mới bảo vệ dữ liệu. Với dataset chưa rõ classification, áp dụng vùng cách ly và quyền truy cập hạn chế cho tới khi owner xác nhận.

## 3. Data minimization: chỉ thu thập và giữ thứ thực sự cần

Biện pháp giảm rủi ro hiệu quả nhất thường bắt đầu trước encryption: **không thu thập hoặc không đưa vào pipeline những thuộc tính không cần cho mục đích đã xác định**.

### 3.1. Thu thập tối thiểu

Đối với mỗi field, hỏi:

1. Tính năng hoặc phân tích nào cần field này?
2. Có thể dùng thuộc tính ít nhạy cảm hơn hay không?
3. Có cần độ chính xác đầy đủ hay chỉ cần nhóm/phân vị?
4. Có cần lưu giá trị gốc lâu dài hay chỉ cần dùng tạm trong bước xử lý?
5. Có thể tính toán ở nguồn rồi chỉ gửi kết quả tổng hợp không?
6. Khi mục đích kết thúc, dữ liệu cần bị xóa hoặc chuyển trạng thái nào?

Ví dụ, báo cáo hiệu quả chiến dịch có thể chỉ cần tỉnh/thành và tháng, không cần địa chỉ đầy đủ và thời điểm chính xác đến giây. Phân tích tuổi có thể cần nhóm tuổi, không cần ngày sinh. Phân tích thanh toán có thể cần provider transaction reference, không cần lưu thông tin thẻ đầy đủ.

### 3.2. Tách dữ liệu định danh khỏi dữ liệu phân tích

Một mô hình thường dùng là lưu thông tin định danh trong vùng có quyền truy cập hẹp, còn dữ liệu phân tích sử dụng surrogate key hoặc token:

~~~mermaid
flowchart LR
    Source["Nguồn nghiệp vụ"] --> Ingest["Ingestion + validation"]
    Ingest --> PII["Identity vault / restricted zone"]
    Ingest --> Transform["Minimize + tokenize"]
    PII --> Map[("Token mapping store")]
    Transform --> Lake["Analytics zone"]
    Lake --> Curated["Curated datasets"]
    Curated --> BI["BI / data science"]
    BI -->|Chỉ khi có lý do được duyệt| Broker["Controlled re-identification service"]
    Broker --> PII
~~~

Các analyst thường chỉ thấy token, nhóm tuổi hoặc khu vực tổng quát. Một dịch vụ riêng có thể giải mã/ánh xạ token khi nghiệp vụ cần, với quyền phê duyệt, audit và purpose limitation.

Tách vùng không tự bảo đảm bảo mật. Cần giới hạn đường join, credentials, network, export và các notebook có thể tải mapping ra ngoài.

### 3.3. Tách mục đích sử dụng

Dữ liệu thu thập để xử lý đơn hàng không mặc nhiên được dùng cho mọi mục đích khác như quảng cáo, profiling hoặc huấn luyện mô hình. Catalog nên lưu purpose/usage tags, và pipeline hoặc access layer phải thực thi giới hạn đó. Khi mục đích thay đổi, cần đánh giá lại quyền sử dụng, thông báo/consent nếu áp dụng, retention và ảnh hưởng tới dữ liệu đã chia sẻ.

## 4. Masking, pseudonymization, tokenization và anonymization

Các kỹ thuật này không tương đương. Chọn kỹ thuật theo mức bảo vệ cần thiết và khả năng dùng dữ liệu sau biến đổi.

| Kỹ thuật | Cách làm | Có thể khôi phục danh tính? | Trường hợp phù hợp |
| --- | --- | --- | --- |
| Masking | Ẩn một phần hoặc thay bằng ký tự cố định | Có thể nếu dữ liệu gốc vẫn còn ở nguồn khác | Hiển thị hỗ trợ, môi trường demo |
| Pseudonymization | Thay định danh bằng mã giả/token ổn định | Có nếu còn mapping hoặc khóa liên kết | Phân tích cần theo dõi cùng entity mà không cần tên thật |
| Tokenization | Thay dữ liệu nhạy cảm bằng token, mapping giữ riêng | Có qua token vault/dịch vụ được bảo vệ | Payment reference, customer identity |
| Hashing | Biến đổi một chiều theo thuật toán hash | Không trực tiếp, nhưng input ít entropy có thể dò ngược | Integrity hoặc so khớp có kiểm soát; cần salt/pepper tùy mục đích |
| Generalization | Giảm độ chi tiết, ví dụ ngày thành tháng hoặc tuổi thành nhóm | Không trực tiếp, nhưng vẫn có rủi ro kết hợp | Báo cáo thống kê và dashboard |
| Anonymization | Biến đổi nhằm loại bỏ khả năng nhận diện hợp lý trong bối cảnh xác định | Theo mục tiêu không thể tái nhận diện bằng phương tiện có thể sử dụng | Chia sẻ dữ liệu khi đã đánh giá rủi ro tái nhận diện |

Pseudonymized data vẫn có thể là dữ liệu cá nhân nếu tồn tại cách liên kết trở lại. Hash email không mặc nhiên ẩn danh: attacker có thể hash từ danh sách email phổ biến và so sánh. Mask một phần số điện thoại có thể vẫn nhận diện được khi kết hợp quốc gia, tên hoặc lịch sử.

### 4.1. Ví dụ masking

~~~text
Email gốc:       linh.nguyen@example.test
Email hiển thị:  l***@example.test

Số điện thoại:   +84 912 345 678
Hiển thị:        +84 ****** 678

Ngày sinh:       1994-08-17
Báo cáo:         nhóm tuổi 30-39
~~~

Masking hiển thị không đồng nghĩa giá trị đã được masking trong storage. Nếu analyst có thể query raw table hoặc export file gốc thì kiểm soát UI không đủ.

### 4.2. Hashing đúng mục đích

Hash không có khóa phù hợp để lưu mật khẩu; password hashing cần thuật toán chuyên dụng chậm có salt riêng như Argon2id, scrypt hoặc bcrypt. Với pseudonymization, HMAC với secret key quản lý riêng có thể giảm khả năng dò dictionary hơn hash thuần cho các giá trị ít entropy:

~~~text
subject_token = HMAC-SHA-256(secret_key, canonical_customer_id)
~~~

Ví dụ là công thức khái niệm, không phải hướng dẫn tự triển khai key management. Phải chuẩn hóa input, tách secret theo môi trường/mục đích, version hóa key và giới hạn quyền tính token. Nếu token cần ổn định qua thời gian, rotation phải có kế hoạch migration hoặc ánh xạ version.

### 4.3. Rủi ro tái nhận diện

Một dataset không chứa tên vẫn có thể bị tái nhận diện khi:

- Kết hợp với dataset công khai hoặc dữ liệu đối tác.
- Các nhóm dữ liệu quá nhỏ hoặc có thuộc tính hiếm.
- Timestamp, vị trí và chuỗi hành vi tạo dấu vân tay.
- Một người dùng có nhiều lượt truy vấn để suy ra giá trị bị ẩn.
- Token ổn định được dùng chung giữa nhiều hệ thống làm tăng khả năng liên kết.

Đánh giá anonymization cần xem adversary, dữ liệu phụ có thể tiếp cận, mục tiêu chia sẻ, kích thước nhóm và khả năng query. Các kỹ thuật như k-anonymity, l-diversity hoặc differential privacy có thể hỗ trợ một số loại phát hành thống kê, nhưng không phải chứng nhận tự động rằng dữ liệu đã an toàn.

## 5. Encryption và quản lý khóa

Encryption bảo vệ dữ liệu khi bị truy cập trái phép ở một số lớp, nhưng không thay thế access control. Khi ứng dụng hoặc analyst có quyền hợp lệ giải mã, dữ liệu vẫn hiển thị ở dạng rõ trong bộ nhớ hoặc kết quả truy vấn.

### 5.1. Các lớp mã hóa

| Trạng thái dữ liệu | Biện pháp | Cần chú ý |
| --- | --- | --- |
| In transit | TLS giữa source, ingestion, storage, query engine và client | Xác minh certificate, hostname và phiên bản protocol |
| At rest | Mã hóa object, disk, database, warehouse, snapshot và backup | Kiểm tra mọi bản sao và bản export |
| In use | Hạn chế truy cập, isolation, secure enclave/confidential computing nếu có yêu cầu | Khó áp dụng rộng, có giới hạn hiệu năng/tính năng |
| Field-level | Mã hóa một số cột hoặc thuộc tính nhạy cảm | Query, indexing, join và key access có thể phức tạp hơn |

Encryption at rest có thể do provider quản lý mặc định hoặc dùng customer-managed key. Cần xác minh phạm vi thực sự được bảo vệ: object version, replica, log, temporary spill file, snapshot, export và cache.

### 5.2. Key management

- Dùng KMS/HSM hoặc dịch vụ quản lý khóa được tổ chức phê duyệt; tránh tự lưu master key trong cùng bucket/database.
- Phân tách quyền sử dụng key và quyền quản lý key. Analyst không cần quyền disable hoặc rotate key chỉ vì họ được đọc bảng.
- Thiết kế rotation, key version, re-encryption và khả năng giải mã dữ liệu cũ.
- Có quy trình backup/recovery cho key metadata và quyền truy cập ở region DR.
- Audit thao tác tạo, dùng, rotate, disable và xóa key.
- Thiết lập cảnh báo trước expiration và kiểm thử ứng dụng sau rotation.

Customer-managed key tăng quyền kiểm soát nhưng cũng tạo một dependency vận hành. Nếu key bị disable nhầm, dữ liệu có thể không truy cập được dù storage vẫn sẵn sàng.

### 5.3. Field-level encryption ảnh hưởng phân tích

Mã hóa email hoặc định danh ở cấp field có thể làm truy vấn equality, join, grouping và search khó hơn. Deterministic encryption cho phép một số kiểu so sánh nhưng có thể làm lộ pattern lặp; randomized encryption che pattern tốt hơn nhưng không hỗ trợ equality trực tiếp. Không tự thiết kế thuật toán mã hóa; sử dụng thư viện và dịch vụ phù hợp, đánh giá threat model cùng chuyên gia bảo mật.

## 6. Identity và kiểm soát truy cập dữ liệu

Một nền tảng dữ liệu thường có nhiều vai trò: data engineer, analyst, data scientist, dashboard user, application service, pipeline service account và administrator. Không nên cấp quyền theo nhóm rộng kiểu “mọi người trong dự án đều đọc được toàn bộ lake”.

### 6.1. Least privilege và separation of duties

| Vai trò | Quyền thường cần | Quyền nên hạn chế |
| --- | --- | --- |
| Ingestion service | Ghi vào landing/raw path đã định | Đọc mọi dataset và xóa backup |
| Data engineer | Đọc source được giao, ghi curated output | Truy cập PII không cần cho transform |
| Analyst | Đọc curated/aggregate theo business domain | Đọc raw restricted data và mapping vault |
| Data scientist | Dùng dataset đã giảm thiểu hoặc được phê duyệt | Export raw identifiers ra notebook |
| BI viewer | Query semantic model/dashboard được cấp | SQL trực tiếp lên raw zone |
| Security/audit | Đọc audit evidence và metadata cần điều tra | Thay đổi dữ liệu nghiệp vụ |
| Platform admin | Quản trị hạ tầng và policy theo quy trình | Mặc nhiên sử dụng dữ liệu nghiệp vụ |

Tách nhiệm vụ giữa người tạo dataset, người phê duyệt quyền và người vận hành key/backup giúp giảm nguy cơ lạm quyền. Quyền đặc biệt nên cấp có thời hạn và ghi audit.

### 6.2. RBAC và ABAC

- **RBAC (Role-Based Access Control):** quyền gắn với role; dễ quản lý theo chức năng và nhóm công việc.
- **ABAC (Attribute-Based Access Control):** quyết định dựa trên thuộc tính như classification, tenant, region, purpose, project, thời gian hoặc thiết bị.

Một kiến trúc có thể kết hợp cả hai: analyst có role đọc curated data, nhưng ABAC chỉ cho phép khi dataset không vượt classification được duyệt và người dùng thuộc đúng tenant/project.

### 6.3. Row-level và column-level security

Row-level security giới hạn bản ghi mà người dùng được thấy, ví dụ mỗi tenant chỉ nhìn thấy đơn hàng của mình. Column-level security ẩn hoặc giới hạn cột nhạy cảm, ví dụ analyst đọc tổng tiền và loại sản phẩm nhưng không đọc email.

Ví dụ logic:

~~~sql
-- Ví dụ minh họa chính sách theo tenant.
CREATE POLICY tenant_isolation
ON curated.orders
USING (tenant_id = current_setting('app.tenant_id'));
~~~

Đoạn SQL phụ thuộc engine và cách thiết lập session context. Không coi một biến session do client tự gửi là bằng chứng tenant đáng tin cậy; identity và tenant context phải được backend xác thực, tránh connection pool tái sử dụng context sai giữa request.

Row/column security cần được kiểm thử bằng negative test: user tenant A không đọc được tenant B; analyst không thể lấy cột restricted qua view, export, query engine hoặc notebook khác.

### 6.4. Data sharing và export

Chia sẻ data qua view, clean room, API hoặc file export đều cần contract về:

- Ai là recipient và mục đích sử dụng được phép.
- Dataset/field nào được chia sẻ, mức granular và retention.
- Có được join với dữ liệu bên ngoài không.
- Cách xác thực, mã hóa, audit và thu hồi quyền.
- Ai chịu trách nhiệm khi recipient tạo bản sao downstream.

Không gửi file đính kèm chứa dữ liệu restricted chỉ vì việc cấp quyền trực tiếp có vẻ phức tạp hơn. Dùng cơ chế chia sẻ có thời hạn, watermark/audit và hạn chế export nếu dịch vụ hỗ trợ.

## 7. Audit, monitoring và phát hiện lạm dụng

Access policy cho biết ai được phép; audit log cho biết ai đã thực hiện thao tác. Hai thứ đều cần thiết.

### 7.1. Những sự kiện nên ghi nhận

- Đăng nhập, token issuance, role assumption và thay đổi identity.
- Đọc bảng, view, object, column hoặc file nhạy cảm.
- Export/download, tạo snapshot, chia sẻ dataset hoặc cấp signed URL.
- Thay đổi IAM, ACL, row/column policy, KMS key và retention.
- Tạo/xóa dataset, thay schema, chạy job transform và thay lineage.
- Truy cập bất thường theo khối lượng, thời gian, vị trí hoặc hành vi truy vấn.

Audit record nên có principal, action, resource, timestamp, source context, outcome, request/job ID và thông tin policy decision phù hợp. Không ghi payload, secret hoặc toàn bộ query literal chứa dữ liệu cá nhân nếu không cần điều tra.

### 7.2. Bảo vệ audit log

Audit log cũng là dữ liệu nhạy cảm. Cần:

- Ghi vào vùng riêng, quyền append/write tách khỏi quyền sửa/xóa.
- Đồng bộ thời gian và giữ metadata phục vụ điều tra.
- Mã hóa, integrity protection và retention theo chính sách.
- Sao lưu hoặc chuyển log sang miền quản trị độc lập nếu mức rủi ro yêu cầu.
- Giám sát việc ngừng logging, giảm volume đột ngột hoặc thay đổi retention.

Không để một administrator duy nhất vừa có thể thực hiện thao tác dữ liệu vừa có thể xóa sạch dấu vết.

### 7.3. Phát hiện truy vấn bất thường

Một analyst thường query vài bảng curated nhưng đột nhiên tải hàng chục triệu hàng restricted, đọc nhiều tenant hoặc chạy export vào thời điểm bất thường. Hệ thống có thể cảnh báo theo:

- Query volume/bytes scanned tăng đột biến.
- Nhiều truy vấn thử đoán dữ liệu hoặc lọc từng phần để suy ra giá trị.
- Export/download vượt ngưỡng theo user, role hoặc dataset.
- Truy cập raw zone từ notebook/project không được cấp.
- Truy cập sau giờ hoặc từ context bất thường theo chính sách nội bộ.

Alert cần kết hợp business context để tránh false positive và có quy trình điều tra, tạm khóa token, bảo toàn audit và thông báo owner.

## 8. Consent, purpose limitation và quyền sử dụng

Quyền kỹ thuật đọc được dữ liệu không đồng nghĩa có quyền sử dụng dữ liệu cho mọi mục đích. Một pipeline cần biết dữ liệu được thu thập theo purpose nào, consent/status có điều kiện gì và mục đích nào được phép downstream.

### 8.1. Metadata về mục đích

Catalog hoặc governance registry có thể lưu:

- Processing purpose và business owner.
- Loại dữ liệu/chủ thể dữ liệu, jurisdiction và classification.
- Consent hoặc trạng thái opt-in/opt-out nếu applicable.
- Allowed use, prohibited use và hạn chế chia sẻ.
- Thời điểm hiệu lực, nguồn bằng chứng và version của policy.
- Dataset downstream phụ thuộc vào dữ liệu đó.

Không phải mọi dữ liệu đều dựa trên consent; căn cứ xử lý tùy pháp luật và ngữ cảnh. Bài toán kiến trúc là giữ metadata cần thiết để thực thi lựa chọn đã được tổ chức và pháp chế xác nhận.

### 8.2. Propagate privacy signals

Nếu người dùng rút consent hoặc yêu cầu xóa, pipeline cần biết ảnh hưởng tới bảng curated, aggregate, feature store, cache, model training data, export và backup. Cần thiết kế deletion/tombstone event hoặc workflow có ID để tìm mọi bản sao.

Một số kết quả tổng hợp có thể không còn liên kết hợp lý với cá nhân; một số model/feature có thể vẫn ghi nhớ đặc tính từ dữ liệu huấn luyện. Việc có phải xóa hoặc retrain hay không cần được đánh giá theo pháp lý, kỹ thuật và khả năng nhận diện, không tự suy từ việc đã xóa raw row.

## 9. Retention: giữ dữ liệu bao lâu?

Retention là thời gian hoặc điều kiện mà dữ liệu được phép tồn tại trước khi archive, delete hoặc chuyển trạng thái theo chính sách. Giữ dữ liệu mãi mãi làm tăng chi phí, bề mặt tấn công và khó đáp ứng yêu cầu xóa; xóa quá sớm có thể phá audit, điều tra, đối soát hoặc phân tích xu hướng.

### 9.1. Xác định retention theo dataset

| Dataset | Mục đích | Retention cần cân nhắc |
| --- | --- | --- |
| Raw event | Replay, điều tra pipeline và xây lại curated | Cửa sổ replay, privacy và chi phí storage |
| Curated transaction history | Báo cáo, đối soát và phân tích nghiệp vụ | Nghĩa vụ lưu hồ sơ, mục đích sử dụng và yêu cầu xóa |
| Aggregated metrics | Trend và planning | Giá trị phân tích, rủi ro tái nhận diện và thời hạn |
| Application log | Troubleshooting và security investigation | Thời gian điều tra, chi phí và data minimization |
| Notebook/temp output | Thử nghiệm ngắn hạn | TTL ngắn, tự động cleanup |
| Backup | Khôi phục sau lỗi/xóa nhầm | Backup policy, legal hold, immutability và RPO/RTO |

Không tự đặt thời hạn pháp lý trong code nếu chưa có policy được owner/pháp chế phê duyệt. Hệ thống nên nhận retention như metadata/config có version, owner và review date.

### 9.2. Retention khác với lifecycle tier

Retention quyết định dữ liệu còn được giữ không; lifecycle tier quyết định dữ liệu được lưu ở lớp nào và chi phí/truy xuất ra sao. Một object có thể chuyển sang archive sau 90 ngày nhưng vẫn cần giữ 7 năm. Ngược lại log có thể bị xóa sau 30 ngày dù storage tier rẻ hơn vẫn còn chỗ.

### 9.3. Legal hold và exception

Legal hold hoặc investigation hold có thể tạm dừng việc xóa theo yêu cầu có thẩm quyền. Cần có:

- Người/đơn vị đặt hold và căn cứ.
- Dataset, tenant, thời gian và bản sao chịu ảnh hưởng.
- Ngày rà soát, điều kiện giải phóng hold và audit trail.
- Cơ chế lifecycle tôn trọng hold, không để batch cleanup xóa nhầm.

Không biến hold thành retention vô hạn mặc định; cần rà soát và giải phóng khi không còn căn cứ.

## 10. Vòng đời dữ liệu trong nền tảng phân tích

Một data platform thường tổ chức dữ liệu thành các vùng có mục đích và mức tin cậy khác nhau. Tên vùng thay đổi theo kiến trúc, nhưng nguyên tắc là giữ rõ nguồn gốc, mức biến đổi, owner và quyền truy cập.

~~~mermaid
flowchart LR
    Sources["Operational DB / Apps / Events"] --> Ingest["Ingestion + schema validation"]
    Ingest --> Raw["Landing / Raw zone"]
    Raw --> Validate["Quality + privacy transform"]
    Validate --> Curated["Curated / Trusted zone"]
    Curated --> Serve["Serving / Semantic models"]
    Serve --> BI["BI / ML / Data products"]
    Raw --> Archive["Archive / Retention"]
    Curated --> Archive
    Raw --> Delete["Expiry / deletion workflow"]
    Curated --> Delete
    Serve --> Delete
~~~

### 10.1. Landing và raw zone

Landing/Raw giữ bản nhận từ source hoặc bản gần nguồn để replay, audit và điều tra. Vì đây thường là nơi có nhiều field nhạy cảm nhất, cần:

- Giới hạn ingestion identity được ghi đúng path/topic.
- Tách raw restricted zone khỏi khu vực analyst truy cập thường ngày.
- Validate schema, source identity, timestamp, checksum và format.
- Gắn metadata về source, arrival time, batch/event ID, classification và retention.
- Mã hóa, audit, chống overwrite hoặc lưu version theo yêu cầu.
- Không dùng raw làm nơi chia sẻ mặc định cho notebook, BI hoặc export.

Raw không nhất thiết phải là bản sao vô thời hạn. Có thể dùng cửa sổ lưu ngắn để replay và sau đó chỉ giữ curated/aggregate cần thiết.

### 10.2. Validated và curated zone

Curated zone chứa dữ liệu đã chuẩn hóa, kiểm tra quality, xử lý duplicate, áp dụng business rules và privacy transformation. Đây thường là vùng phục vụ phần lớn analyst.

Một pipeline tốt nên:

- Kiểm tra schema contract và compatibility trước khi publish.
- Chuẩn hóa timezone, currency, encoding, identifier và null semantics.
- Xử lý duplicate, late-arriving event và record lỗi có quarantine.
- Áp dụng masking/tokenization/minimization theo mục đích.
- Ghi lineage từ output về source và version transform.
- Lưu quality metrics, freshness, owner và ngày cập nhật.
- Publish atomically hoặc qua versioned snapshot để consumer không thấy dataset nửa chừng.

Không ghi đè dữ liệu hợp lệ bằng output thiếu hoặc lỗi. Với batch, dùng staging path/table rồi validate và swap/publish; với streaming, có checkpoint và state recovery.

### 10.3. Serving và semantic layer

Serving zone/semantic model cung cấp dữ liệu theo use case: dashboard, metric layer, API, feature store hoặc data product. Không nên để từng dashboard tự join raw restricted tables và tự định nghĩa metric theo cách khác nhau.

Semantic model nên quản lý:

- Định nghĩa metric, dimension và grain của dữ liệu.
- Row/column security và tenant filtering.
- Freshness/SLA, data owner và certified status.
- Quy tắc aggregate và ngăn suy ra thông tin từ nhóm quá nhỏ.
- Query logging, export policy và quota.

## 11. Data catalog, lineage và ownership

Khi một dataset được copy/biến đổi qua nhiều pipeline, cần biết nó đến từ đâu, ai sở hữu và nơi nào còn bản sao. Catalog và lineage giúp trả lời những câu hỏi này.

### 11.1. Data catalog

Catalog là kho metadata mô tả dataset và cách dùng. Một entry hữu ích gồm:

| Metadata | Nội dung |
| --- | --- |
| Identity | Tên, location, format, schema, partition và version |
| Business context | Mô tả, domain, owner, steward và data product |
| Classification | Sensitivity, PII fields, tenant/jurisdiction, allowed use |
| Lifecycle | Created/updated time, retention, tier, deletion/hold status |
| Quality | Freshness, completeness, validity, uniqueness và known issue |
| Access | Roles, policies, approved purpose và access request path |
| Lineage | Upstream source, job/version, downstream dataset và consumer |

Catalog metadata cũng cần quyền và audit. Không công bố schema nhạy cảm, sample row có PII hoặc query preview cho user không được phép.

### 11.2. Lineage

Lineage thể hiện dataset nào được tạo từ source nào, qua job nào và được consumer nào sử dụng. Lineage hữu ích khi:

- Tìm mọi bảng/downstream bị ảnh hưởng khi một field đổi classification.
- Xác định nơi phải xóa hoặc sửa dữ liệu khi có privacy request.
- Điều tra lỗi do source schema hoặc transform thay đổi.
- Đánh giá tác động khi tắt dataset hoặc thay đổi retention.
- Chứng minh báo cáo được tạo từ nguồn và logic nào.

Lineage ở mức bảng là điểm khởi đầu; với dữ liệu nhạy cảm nên cố gắng theo dõi tới column/field và transform quan trọng. Không phải hệ thống nào cũng tự thu thập đầy đủ lineage; có thể cần instrumentation và convention trong pipeline.

### 11.3. Owner và steward

Data owner chịu trách nhiệm về mục đích, chất lượng và quyền sử dụng nghiệp vụ; platform/data custodian chịu trách nhiệm hạ tầng, bảo vệ và vận hành; data steward duy trì metadata, định nghĩa và quy tắc. Trách nhiệm cần rõ để không có dataset “không ai sở hữu” nhưng nhiều người có quyền đọc.

## 12. Data quality, schema evolution và khả năng tái lập

Dữ liệu nhạy cảm được bảo vệ tốt nhưng sai lệch vẫn có thể dẫn tới quyết định gây hại. Quality và governance phải đi cùng security.

### 12.1. Quality dimensions

- **Completeness:** trường bắt buộc có dữ liệu theo kỳ vọng.
- **Validity:** giá trị phù hợp domain, format và quy tắc.
- **Accuracy:** dữ liệu phản ánh sự thật nghiệp vụ ở mức có thể kiểm chứng.
- **Uniqueness:** không có duplicate ngoài semantics cho phép.
- **Consistency:** quy tắc giữa bảng/source không mâu thuẫn.
- **Timeliness/freshness:** dữ liệu cập nhật trong thời gian cam kết.
- **Integrity:** quan hệ khóa, checksum và ràng buộc nguồn được bảo toàn.

Mỗi dataset quan trọng nên có quality rule, threshold, owner, alert và cách quarantine. Không chỉ log lỗi rồi tiếp tục publish output như dữ liệu sạch.

### 12.2. Schema evolution

Thay đổi schema ảnh hưởng pipeline, dashboard, model và access policy. Cần phân loại:

| Thay đổi | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Thêm field optional | Consumer cũ thường có thể bỏ qua nếu contract hỗ trợ | Version schema, kiểm thử consumer và cập nhật catalog |
| Đổi type hoặc semantics | Query/logic cũ có thể sai hoặc lỗi | Tạo field/version mới, migration và dual-read có thời hạn |
| Xóa field | Downstream/retention/deletion có thể còn phụ thuộc | Lineage impact analysis, migrate consumer và deprecate |
| Thay identifier | Join, token mapping và dedup có thể sai | Mapping version, backfill và validation |
| Tăng độ nhạy field | Quyền cũ có thể quá rộng | Reclassify, update policies và audit |

### 12.3. Reproducibility

Để tái tạo kết quả phân tích, cần version hóa source snapshot hoặc watermark, schema, code transform, dependency, parameter, reference data và environment. Không nhất thiết giữ PII vô hạn chỉ để tái tạo; có thể dùng snapshot đã pseudonymize/aggregate hoặc immutable event đã giảm thiểu nếu đủ cho mục đích.

## 13. Data deletion: xóa đúng và chứng minh đã xóa

Xóa dữ liệu trong bảng chính không đồng nghĩa xóa mọi bản sao. Dữ liệu có thể tồn tại trong raw files, curated tables, materialized views, warehouse cache, search index, feature store, export, notebook, object version, replica và backup.

### 13.1. Xây dựng deletion workflow

1. Xác thực yêu cầu và phạm vi subject/tenant/dataset.
2. Xác định mục đích, căn cứ, legal hold và các ngoại lệ được phê duyệt.
3. Tra catalog/lineage để tìm nguồn, downstream, replica, cache, export và processor.
4. Tạo deletion job ID và trạng thái theo dõi; không phụ thuộc thao tác thủ công rời rạc.
5. Xóa hoặc xử lý theo policy ở nguồn và các bản sao online; phát tombstone/deletion event tới pipeline.
6. Rebuild aggregate/index/materialized view nếu không thể xóa chính xác một record.
7. Xác định cách xử lý backup/archive: expire theo lịch, crypto-erasure hoặc restore-and-redact nếu chính sách yêu cầu và kỹ thuật hỗ trợ.
8. Verify bằng query/scan có kiểm soát, catalog state và acknowledgement của processor.
9. Lưu evidence tối thiểu về hoàn thành, lỗi, ngoại lệ và thời điểm; không lưu lại chính PII đã yêu cầu xóa trong audit.

### 13.2. Deletion propagation

~~~mermaid
flowchart TB
    Request["Verified deletion request"] --> Registry["Subject / tenant registry"]
    Registry --> Lineage["Catalog + lineage lookup"]
    Lineage --> Source["Source / OLTP"]
    Lineage --> Raw["Raw lake"]
    Lineage --> Curated["Curated tables"]
    Lineage --> Serving["Views / indexes / features"]
    Lineage --> Export["Exports / downstream processors"]
    Source --> Verify["Verification + evidence"]
    Raw --> Verify
    Curated --> Verify
    Serving --> Verify
    Export --> Verify
    Verify --> Done["Closed / exception tracked"]
~~~

Một workflow có thể xử lý bất đồng bộ; trạng thái “đã tiếp nhận” không phải “đã xóa hoàn tất”. Cần phân biệt pending, completed, failed và legally retained.

### 13.3. Deletion trong backup

Backup immutable hoặc retention lock có thể không cho phép xóa một record riêng lẻ ngay lập tức. Tổ chức cần xác định chính sách được phê duyệt: giữ backup tới hết retention, cách ly và giới hạn restore, hoặc crypto-erasure nếu key scope và semantics cho phép. Khi khôi phục backup cũ, cần chạy lại deletion ledger/tombstone trước khi đưa dữ liệu trở lại môi trường phục vụ.

Không tuyên bố “xóa hoàn toàn” nếu dữ liệu vẫn tồn tại trong backup được phép giữ. Trạng thái trả lời nên mô tả rõ phần đã xóa khỏi hệ thống online, phần đang chờ hết backup retention và căn cứ ngoại lệ.

### 13.4. Crypto-erasure

Crypto-erasure là làm cho ciphertext không thể giải mã bằng cách hủy hoặc thu hồi key liên quan. Nó chỉ phù hợp khi key scope, key backup, replica, cache và bản sao plaintext được kiểm soát. Nếu nhiều tenant dùng chung data encryption key hoặc plaintext export tồn tại ngoài storage, hủy một key không xóa được mọi bản sao. Đây là quyết định kiến trúc cần đánh giá kỹ, không phải nút xóa phổ quát.

## 14. Storage lifecycle: hot, warm, cold và archive

Data platform có thể dùng nhiều tier để cân bằng chi phí và tốc độ truy cập. Lifecycle tự động chuyển dữ liệu theo tuổi, access pattern, classification và mục đích.

| Tier | Đặc điểm | Dùng cho |
| --- | --- | --- |
| Hot | Truy cập thường xuyên, latency thấp, query trực tiếp | Dataset active, dashboard, pipeline hiện thời |
| Warm | Truy cập định kỳ hoặc theo đợt, chi phí thấp hơn tùy dịch vụ | Lịch sử gần, dữ liệu phục vụ điều tra |
| Cold | Truy cập hiếm, có thể chấp nhận truy xuất chậm hơn | Lịch sử lâu dài, dữ liệu ít được query |
| Archive | Chi phí lưu thấp nhưng restore có thể mất nhiều thời gian/phí | Hồ sơ giữ lâu, backup và audit theo chính sách |

Không có mapping tier cố định giữa mọi provider. Có dịch vụ tính theo GB, có dịch vụ tính theo throughput/request; có tier archive cần restore trước khi đọc. Phải kiểm tra minimum storage duration, retrieval fee, restore time, early deletion charge và khả năng query trực tiếp.

### 14.1. Policy lifecycle theo data class

Không chuyển mọi dataset sang archive sau cùng một số ngày. Một policy nên xét:

- Classification và giới hạn pháp lý/contract.
- Data owner và business purpose.
- Access frequency và SLA truy xuất.
- Retention/hold, backup và deletion workflow.
- Format, compression, partitioning và khả năng đọc lại.
- Chi phí storage, retrieval, request và network.

Dataset restricted có thể cần mã hóa, key tách biệt và quyền archive hẹp hơn. Dữ liệu public có thể ưu tiên CDN/cache và lifecycle tối ưu dung lượng.

### 14.2. File format và partitioning

Ở data lake, columnar format như Parquet/ORC thường giúp query chỉ đọc cột cần thiết và nén tốt cho phân tích. Partition theo ngày, tenant hoặc domain có thể giảm bytes scanned, nhưng partition quá nhỏ hoặc quá nhiều file nhỏ gây metadata overhead và query chậm.

Partition key không nên chứa trực tiếp PII nếu folder/path xuất hiện trong log hoặc catalog. Cần chọn grain theo query pattern và privacy boundary; không partition theo giá trị hiếm đến mức tạo một file/partition cho mỗi cá nhân.

### 14.3. Compaction và small files

Streaming ingestion có thể tạo hàng triệu file nhỏ. Compaction hợp nhất file theo partition/time window, giảm metadata và tăng hiệu quả query. Compaction phải bảo toàn idempotency, schema, lineage, watermark và deletion marker; khi chạy đồng thời với consumer phải có cơ chế publish snapshot ổn định.

## 15. Data sharing, analytics và machine learning

Dữ liệu phân tích thường được dùng lại bởi nhiều team và công cụ. Chia sẻ rộng làm tăng giá trị nhưng cũng tăng số bản sao và bề mặt tấn công.

### 15.1. Curated data product

Thay vì cấp quyền raw, domain team có thể công bố data product có:

- Schema và metric được định nghĩa.
- Owner và SLA freshness/availability.
- Classification, allowed purpose và retention.
- Row/column policy hoặc aggregate-only interface.
- Quality score, lineage và version.
- Cách request access, audit và deprecation.

Data product giúp consumer dùng hợp đồng ổn định và giảm join tùy tiện vào nguồn nhạy cảm.

### 15.2. Notebook và môi trường data science

Notebook thường cho phép tải dữ liệu xuống local disk, cache, output cell hoặc file export. Cần:

- Dùng workspace được quản lý với identity và network policy.
- Không cấp quyền raw rộng hơn nhu cầu thí nghiệm.
- Dùng masked/synthetic sample cho development.
- Quản lý output/temporary storage và tự động cleanup.
- Kiểm soát chia sẻ notebook, logs, package và external connector.
- Giới hạn export ra thiết bị cá nhân hoặc public bucket.

### 15.3. Feature store và model training

Feature store có thể lưu thuộc tính liên quan người dùng và được dùng cho prediction online/offline. Phải theo dõi lineage từ source tới feature, timestamp/event-time, consent/allowed use, retention và cách xử lý deletion. Offline training data và online serving store có thể có bản sao khác nhau; cần workflow cập nhật/expire cả hai.

Model được huấn luyện từ dữ liệu cá nhân có thể ghi nhớ một số thông tin. Xóa source row không bảo đảm tự động loại bỏ ảnh hưởng đã học. Khi cần, đánh giá retraining, unlearning capability hoặc giới hạn mô hình theo policy và risk assessment.

### 15.4. Aggregate và differential privacy

Aggregate giúp giảm chi tiết nhưng không tự loại bỏ rủi ro khi group quá nhỏ. Có thể áp dụng ngưỡng số lượng tối thiểu, suppression, query budget, noise hoặc differential privacy cho một số thống kê. Differential privacy cung cấp một định nghĩa định lượng về mức ảnh hưởng của một cá nhân tới kết quả; nó cần privacy budget và triển khai đúng, không đơn giản là thêm nhiễu tùy ý.

## 16. Well-Architected: đánh đổi của data lifecycle

| Góc nhìn | Quyết định thiết kế | Đánh đổi |
| --- | --- | --- |
| **Operational Excellence / Vận hành** | Catalog, ownership, lineage, policy-as-code, deletion workflow và runbook | Tự động hóa giảm thao tác tay nhưng cần metadata chuẩn và owner chịu trách nhiệm |
| **Security / Bảo mật** | Classification, minimization, IAM, encryption, masking, audit và private networking | Kiểm soát sâu tăng công sức governance và đôi khi làm query phức tạp hơn |
| **Reliability / Độ tin cậy** | Backup, immutable copy, restore test, quality checks và lineage | Nhiều bản sao tăng durability nhưng làm deletion và consistency khó hơn |
| **Performance Efficiency / Hiệu quả hiệu năng** | Partition, columnar format, compaction, cache và tiering | Tối ưu query có thể tăng preprocessing và metadata maintenance |
| **Cost Optimization / Tối ưu chi phí** | Retention, lifecycle, archive và data minimization | Archive tiết kiệm lưu trữ nhưng tăng retrieval time/cost |
| **Sustainability / Bền vững** | Giảm dữ liệu trùng, field không cần, scan thừa và thời gian lưu | Giảm footprint nhưng phải giữ đủ dữ liệu cho audit và nghiệp vụ |

Chỉ số nên theo dõi:

- Tỷ lệ dataset có owner, classification, retention và lineage đầy đủ.
- Số field restricted được giảm thiểu/mask trong curated zone.
- Số tài khoản có quyền raw và số lần export restricted data.
- Tỷ lệ deletion request hoàn thành đúng SLA, số ngoại lệ legal hold.
- Dữ liệu quá hạn retention và dung lượng theo tier.
- Query bytes scanned, freshness, quality failure và restore success.
- Chi phí trên một pipeline/report hoặc một TB dữ liệu hữu ích.

## 17. Bài thực hành: quản trị dữ liệu phân tích cho nền tảng thương mại điện tử

Một doanh nghiệp thu thập order, payment, customer profile, clickstream và log ứng dụng vào data lake. Analyst cần phân tích doanh thu, chiến dịch và hành vi khách hàng. Data scientist xây dựng mô hình dự đoán rời bỏ. Bộ phận audit cần truy xuất lịch sử giao dịch; người dùng có thể gửi yêu cầu xóa hoặc rút consent cho mục đích marketing theo chính sách đã được tổ chức xác nhận.

**Yêu cầu bài làm:**

1. Lập data inventory và phân loại từng field trong customer, order, payment, clickstream và log.
2. Xác định field không cần thiết cho dashboard doanh thu và đề xuất minimization.
3. Thiết kế raw, curated và serving zones; chỉ rõ vùng nào chứa PII và ai được đọc.
4. Chọn masking/tokenization/pseudonymization cho email, phone và customer ID; mô tả key/mapping store và luồng re-identification được duyệt.
5. Thiết kế RBAC/ABAC, row-level security theo tenant, column-level security và negative tests.
6. Đề xuất retention riêng cho raw events, curated transactions, aggregate, logs, notebook outputs và backup; thể hiện legal hold.
7. Vẽ lineage và deletion workflow từ source tới lake, warehouse, feature store, export và backup.
8. Thiết kế lifecycle hot/warm/cold/archive, format và partitioning cho clickstream.
9. Đề xuất audit/alert để phát hiện export bất thường và truy cập raw không đúng purpose.
10. Đưa ra chỉ số đo hiệu quả security, privacy, quality, cost và khả năng khôi phục.

### Gợi ý đánh giá

Một thiết kế tốt không cấp raw data cho tất cả analyst. Dashboard doanh thu có thể dùng curated aggregate; analyst hành vi dùng pseudonymous customer key và dữ liệu đã giảm độ chính xác; mapping định danh nằm trong restricted vault với quyền rất hẹp. Data scientist cần dataset có purpose được phê duyệt và lineage tới source.

Retention phải cân bằng audit, nhu cầu phân tích và quyền xóa; backup có policy riêng và không được mô tả là đã xóa ngay nếu vẫn còn bản sao trong thời hạn được giữ. Mỗi dataset cần owner, access policy, retention, quality và lineage. Lifecycle tier phải tính retrieval SLA, không chỉ giá lưu trữ.

## 18. Checklist trước khi đưa data platform vào production

- [ ] Có inventory, owner, steward và classification cho từng dataset quan trọng.
- [ ] Field nhạy cảm và dữ liệu có thể liên kết để nhận diện đã được đánh dấu.
- [ ] Purpose/allowed use, consent hoặc điều kiện sử dụng được quản lý theo nguồn.
- [ ] Đã loại bỏ field không cần và giảm độ chi tiết trước khi đưa vào analytics zone.
- [ ] Masking, pseudonymization, tokenization hoặc anonymization được chọn đúng mục tiêu và threat model.
- [ ] Mapping/token vault và key được tách quyền, mã hóa, audit và có kế hoạch rotation/recovery.
- [ ] RBAC/ABAC, row/column security, tenant isolation và negative test đã được triển khai.
- [ ] Raw/restricted zone không được chia sẻ mặc định cho analyst/notebook.
- [ ] Encryption in transit/at rest bao phủ data, export, log, snapshot và backup.
- [ ] Audit ghi nhận read/export/policy/key changes và được bảo vệ khỏi sửa/xóa tùy tiện.
- [ ] Retention, lifecycle, legal hold và deletion có owner, version, review date và runbook.
- [ ] Lineage đủ để tìm downstream copy và xử lý schema/privacy change.
- [ ] Deletion workflow bao gồm source, raw, curated, serving, index, feature, export, cache và backup.
- [ ] Backup/restore có thử nghiệm; sau restore có thể áp dụng lại deletion ledger/tombstone.
- [ ] Data quality, schema evolution, freshness và publish atomicity được kiểm tra.
- [ ] Hot/warm/cold/archive tier đáp ứng retrieval SLA và TCO.
- [ ] Notebook, ML feature/training data và data sharing có policy riêng.
- [ ] Có cảnh báo query/export bất thường, retention expiry, quality failure và deletion SLA.
- [ ] Đã diễn tập access revocation, key rotation, deletion, restore và incident response.

**Ghi nhớ:** Quản lý dữ liệu nhạy cảm bắt đầu bằng việc biết dữ liệu nào tồn tại, vì sao cần nó và ai sở hữu. Hãy giảm dữ liệu trước khi bảo vệ, áp dụng quyền tối thiểu và biến đổi định danh phù hợp mục đích, rồi quản lý retention/xóa xuyên suốt raw, curated, serving, archive, export và backup. Một data platform trưởng thành cần catalog, lineage, quality, audit và lifecycle automation để dữ liệu phân tích vừa có giá trị, vừa được sử dụng đúng mục đích, đúng thời hạn và có thể kiểm chứng.

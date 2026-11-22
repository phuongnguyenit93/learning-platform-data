# Mã hóa đường truyền và dữ liệu được lưu

Một dịch vụ Java lưu hồ sơ khách hàng trong PostgreSQL. Kết nối JDBC dùng TLS, ổ đĩa database được mã hóa và backup nằm trong object storage có bật mã hóa. Dữ liệu đã an toàn tuyệt đối chưa? **Chưa.** Mỗi cơ chế bảo vệ một nhóm mối đe dọa khác nhau. TLS không ngăn một tài khoản DB có quyền SELECT đọc plaintext; mã hóa volume không che dữ liệu trước tiến trình database đang chạy; mã hóa trường ở ứng dụng cũng không thay thế phân quyền và transaction.

Trong chương **An toàn dữ liệu** thuộc module **DATA_PERSISTENCE_FUNDAMENTALS**, bài học này tập trung vào cách thiết kế và kiểm chứng **mã hóa dữ liệu trên đường truyền (encryption in transit)** cùng **mã hóa dữ liệu được lưu (encryption at rest)**, từ kết nối Java/JDBC, database, cache, WAL và backup tới quản lý khóa, khôi phục và kiểm thử.

> **Nguyên tắc:** trước khi chọn giải pháp mã hóa, hãy xác định dữ liệu xuất hiện ở đâu, bên nào được giải mã, ai giữ khóa, tài khoản nào có quyền đọc và cơ chế nào chứng minh kết nối hoặc bản lưu thật sự được bảo vệ.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt dữ liệu in transit, at rest và in use; nhận diện những điểm plaintext xuất hiện.
- Giải thích TLS bảo vệ payload trên từng hop và phân biệt mã hóa kênh với xác thực danh tính máy chủ.
- Cấu hình PostgreSQL JDBC dùng TLS có xác minh CA **và hostname**, kiểm thử chứng chỉ sai phải bị từ chối.
- Hiểu cách mTLS, vòng đời chứng chỉ và connection pool ảnh hưởng đến kết nối an toàn.
- So sánh mã hóa volume, backup, transparent/database encryption và mã hóa tại tầng ứng dụng.
- Dùng AEAD như AES-GCM có nonce phù hợp, authentication tag, AAD và phiên bản khóa.
- Thiết kế lưu trữ khóa, phân quyền KMS/HSM, rotation và phục hồi dữ liệu đã mã hóa.
- Bảo vệ replication, WAL, cache, export, log, snapshot và pipeline backup/restore.
- Phân biệt mã hóa với hashing mật khẩu, tokenization, masking, parameterized SQL và authorization.
- Xây dựng test TLS, test ciphertext, kiểm thử key rotation và xử lý lỗi theo nguyên tắc fail-closed.

## 2. Mô hình mối đe dọa trước khi cấu hình

Một hệ thống persistence có nhiều ranh giới:

~~~mermaid
flowchart LR
    U["Client"] -->|HTTPS| G["API Gateway"]
    G -->|TLS/mTLS nếu cần| J["Java Service"]
    J -->|JDBC TLS| P[("PostgreSQL Primary")]
    P -->|Replicated WAL| R[("Standby")]
    P -->|Backup path| B["Backup Storage"]
    J -->|TLS| C[("Cache / Broker")]
    J -->|TLS + identity| K["KMS / Key Service"]
~~~

| Mối đe dọa | Điều có thể bị lộ hoặc sửa | Bảo vệ cần xem xét |
|---|---|---|
| Nghe lén mạng Java–DB | SQL, tham số, kết quả | TLS trên connection, xác minh server |
| Máy chủ giả hoặc DNS bị điều hướng | Kết nối tới attacker | Chứng chỉ, CA và hostname validation |
| Ổ đĩa hoặc snapshot bị lấy cắp | Data files, WAL, dump | Encryption at rest, quyền và vòng đời khóa |
| Backup lưu sai vùng hoặc bucket | Bản sao đầy đủ dữ liệu | Backup encryption, IAM, phân vùng, audit |
| DB superuser hoặc app credential bị chiếm | Plaintext qua SELECT hợp lệ | Least privilege; có thể cần application-level encryption |
| Sửa bản ghi đã mã hóa | Ciphertext bị hoán đổi, thay đổi | AEAD và AAD gắn đúng ngữ cảnh |
| Rò dữ liệu từ log, heap dump, cache | PII sau khi ứng dụng giải mã | Data minimization, masking, hardening, retention |
| Mất khóa giải mã | Không thể phục hồi bản lưu | Key backup, DR, test restore, quản lý key version |
| SQL injection | Query bị thao túng | PreparedStatement, phân quyền tối thiểu; mã hóa không thay thế |

### 2.1. Ba trạng thái cần bảo vệ

- **In transit:** byte đang đi giữa trình duyệt–API, proxy–service, Java–DB, primary–replica hoặc DB–backup.
- **At rest:** các byte được ghi ra data files, index, WAL, temporary files, disk, snapshot, log, export, object storage hoặc cache có persistence.
- **In use:** plaintext trong JVM, ResultSet, buffer, tiến trình DB, memory, debugger hoặc crash dump.

TLS và disk encryption không tự bảo vệ hoàn toàn dữ liệu **in use**. Khi ứng dụng cần hiển thị tên hoặc dùng trường đó để xử lý nghiệp vụ, plaintext sẽ có lúc xuất hiện ở phạm vi được cấp quyền.

### 2.2. Bí mật không đồng nghĩa tính đúng đắn

Một record được AES mã hóa vẫn có thể bị ứng dụng cập nhật sai trạng thái hoặc ghi hai lần khi COMMIT timeout. Mã hóa không thay thế ACID, optimistic locking, backup, audit, idempotency, row-level security hay kiểm soát truy cập theo tenant. Các trách nhiệm này cần được thiết kế song song.

## 3. TLS bảo vệ đường truyền theo từng hop

TLS, khi được cấu hình đúng, cung cấp tính bí mật, toàn vẹn bản tin và xác thực endpoint phù hợp với handshake. Người quan sát gói mạng không đọc được payload SQL/HTTP trong một phiên TLS, và việc sửa payload trong quá trình truyền sẽ bị phát hiện.

Tuy nhiên, bảo vệ chỉ tồn tại trên **đoạn kết nối** đã thiết lập TLS:

~~~text
Browser --HTTPS--> Gateway --HTTP--> Java --TLS--> PostgreSQL
~~~

Trong ví dụ trên, gateway đã giải mã HTTPS và hop gateway–Java dùng HTTP plaintext. Không thể tuyên bố “mã hóa toàn tuyến” chỉ vì hai đầu bên ngoài bật TLS. Khi có reverse proxy, load balancer, service mesh hoặc TLS termination, cần lập sơ đồ chính xác từng hop và nơi plaintext xuất hiện.

TLS cũng không che hoàn toàn metadata như địa chỉ IP, port, kích thước traffic hoặc thời điểm kết nối.

### 3.1. Xác minh server quan trọng hơn chỉ bật SSL

Kênh TLS tới một server giả vẫn có thể bị đọc bởi server giả đó. Client cần:

1. Tin cậy CA/chứng chỉ gốc được quản trị đúng.
2. Kiểm tra chuỗi chứng chỉ và điều kiện hợp lệ.
3. Xác minh hostname sử dụng để kết nối khớp danh tính của chứng chỉ.
4. Từ chối chứng chỉ hết hạn, sai hostname hoặc không được tin cậy.
5. Không âm thầm chuyển về non-TLS khi chính sách yêu cầu mã hóa.

Trình tự này đặc biệt quan trọng với JDBC vì query có thể mang dữ liệu cá nhân hoặc credential trong giao thức kết nối.

## 4. PostgreSQL JDBC: chọn đúng sslmode

PgJDBC hỗ trợ các chế độ SSL/TLS với cam kết khác nhau:

| sslmode | Ý nghĩa cơ bản | Nhận xét |
|---|---|---|
| disable | Không dùng SSL/TLS | Không phù hợp với đường truyền bắt buộc mã hóa |
| allow/prefer | Có thể thương lượng đường kết nối không TLS theo cơ chế ưu tiên/fallback | Không dùng để cưỡng chế TLS |
| require | Yêu cầu kênh mã hóa, nhưng không phải hợp đồng kiểm tra đầy đủ CA và hostname | Không đủ để chống server giả theo yêu cầu xác thực chặt |
| verify-ca | Xác minh chuỗi chứng chỉ theo CA tin cậy | Chưa kiểm tra hostname ở mức verify-full |
| **verify-full** | TLS, xác minh CA và hostname server | Nên ưu tiên nếu chính sách bắt buộc xác thực server |

Hành vi chi tiết của driver/SSL factory có thể khác giữa phiên bản/cấu hình; bảng mô tả quy tắc ở mức thiết kế cho PostgreSQL JDBC. Cần kiểm tra driver đang chạy và test từ chính ứng dụng.

### 4.1. URL JDBC có xác minh hostname

~~~properties
spring.datasource.url=jdbc:postgresql://db.prod.example.internal:5432/orders?sslmode=verify-full&sslrootcert=/etc/app/certs/db-ca.pem
spring.datasource.username=orders_app
# Password cấp từ secret manager, không viết vào file mẫu.
~~~

Điều kiện:

- DNS name trong URL cần khớp certificate SAN được cấp cho endpoint thực tế.
- db-ca.pem chứa CA/certificate public tin cậy, **không phải private key server**.
- File trust cần phân phối qua cơ chế cấu hình phù hợp với môi trường.
- User và password vẫn phải được bảo vệ, phân quyền tối thiểu và rotate riêng.
- Đừng sửa lỗi certificate bằng việc tắt xác minh hostname hoặc chấp nhận mọi chứng chỉ.

Ví dụ đường dẫn trên là đường dẫn giả định trong container Linux. Với môi trường khác, chọn cách quản lý trust anchor và SSL factory được driver hỗ trợ.

### 4.2. Các lỗi cấu hình đáng tránh

~~~text
# Không dùng cho kết nối DB production có policy TLS:
jdbc:postgresql://db.prod.example.internal/orders?sslmode=disable

# Không coi yêu cầu mã hóa mà thiếu xác minh danh tính
# là tương đương verify-full:
jdbc:postgresql://db.prod.example.internal/orders?sslmode=require
~~~

Nếu verify-full thất bại, cần kiểm tra DNS endpoint, SAN, chuỗi CA, certificate rotation, SSL termination ở proxy, đồng hồ và trust store. **Test bắt buộc:** hostname sai và CA không tin cậy phải làm kết nối thất bại, không được tự downgrade.

### 4.3. Kiểm tra TLS của connection đang dùng

~~~sql
SELECT ssl, version, cipher, bits
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
~~~

Kết quả ssl=true cho biết phiên PostgreSQL hiện tại dùng TLS; version/cipher mô tả giao thức và thuật toán. Nó **không chứng minh** ứng dụng đã xác minh CA và hostname; điều đó phải được xác nhận từ cấu hình và integration test của client.

## 5. Connection pool và vòng đời TLS

HikariCP/DataSource thường tạo physical connection và PgJDBC thực hiện handshake TLS khi kết nối mới được mở. Gọi Connection.close() trên handle của pool thường hoàn trả handle logic, không thiết lập phiên TLS mới trên từng query.

Hệ quả:

- Rotate chứng chỉ server hoặc CA có thể chỉ ảnh hưởng **kết nối mới**; các phiên đang mở có vòng đời riêng.
- Pool cần chính sách maxLifetime, validation và cách làm mới connection có kiểm soát khi thay chứng chỉ.
- Cấu hình trust store phải tồn tại trên mọi instance/worker, không chỉ một máy.
- Health check SELECT 1 không tự chứng minh chính sách certificate validation.
- Không tạo pool mới trên mỗi request; quản lý connection pool ở cấp application lifecycle.
- Khi dùng proxy, kiểm tra TLS cả từ ứng dụng tới proxy và hop proxy–DB khi cần.

Ví dụ:

~~~java
HikariConfig config = new HikariConfig();
config.setJdbcUrl(
    "jdbc:postgresql://db.prod.example.internal:5432/orders"
    + "?sslmode=verify-full"
    + "&sslrootcert=/etc/app/certs/db-ca.pem"
);
config.setUsername(dbUser);
config.setPassword(secretProvider.currentDbPassword());
config.setPoolName("orders-db");
config.setMaximumPoolSize(20); // Chỉ là ví dụ cú pháp.
HikariDataSource dataSource = new HikariDataSource(config);
// Đóng DataSource khi ứng dụng shutdown theo lifecycle.
~~~

Tránh log connection string chứa secret. Kích thước pool và timeouts phải được chọn theo workload và số application instance, không copy cứng từ ví dụ.

## 6. PostgreSQL server, xác thực client và mTLS

Một PostgreSQL tự quản trị có thể bật TLS qua cấu hình server:

~~~conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
~~~

Private key phải được bảo vệ bằng quyền file, vòng đời khóa và khả năng reload/rotate phù hợp hệ điều hành và phiên bản PostgreSQL. Với managed database, dùng cơ chế cấp cert được nhà cung cấp hỗ trợ thay vì giả định quyền sửa file nội bộ.

Một rule minh họa trong pg_hba.conf:

~~~conf
# Ví dụ chỉ cho một subnet IPv4 nội bộ, chưa phải policy đầy đủ.
hostssl orders orders_app 10.20.0.0/16 scram-sha-256
~~~

Rule hostssl chỉ match kết nối TLS; **nó không tự cấm non-TLS nếu có rule khác cho phép**. Cần rà soát toàn bộ rule, thứ tự, IPv6, network ACL và firewall.

### 6.1. Server identity và user identity là hai câu hỏi

- Xác thực máy chủ trả lời: *App đã kết nối đúng DB endpoint chưa?*
- Xác thực client/user trả lời: *Ai được đăng nhập, với quyền gì?*

SCRAM hoặc certificate client authentication thuộc lớp xác thực người dùng, nhưng tài khoản DB vẫn phải có quyền tối thiểu với schema/table/function cần thiết. Chứng chỉ mTLS không phải giấy phép đọc mọi bảng.

### 6.2. Khi dùng mutual TLS

Với mTLS, server cũng yêu cầu client trình chứng chỉ phù hợp để xác thực danh tính kết nối. Nó đòi hỏi:

- CA và cơ chế cấp phát chứng chỉ client đúng identity.
- Private key client được cất giữ/giới hạn quyền.
- Quy tắc ánh xạ danh tính client sang role/authorization khi hạ tầng hỗ trợ.
- Rotation, revoke, cách xử lý certificate hết hạn hoặc lộ.
- Kiểm thử thay CA/chứng chỉ khi connection pool còn phiên cũ.

### 6.3. Các hop khác cần xem xét độc lập

JDBC TLS không tự bảo vệ Java–Redis, Java–Kafka, API–KMS, database–replica, backup–object storage hay internal service–service. Những tuyến có chứa dữ liệu nhạy cảm phải có encryption-in-transit policy, xác thực endpoint, và boundary rõ ràng. Chỉ kiểm tra JDBC là chưa đủ cho toàn bộ persistence pipeline.

## 7. Dữ liệu được lưu ở nhiều nơi hơn bảng chính

Mã hóa at rest nhằm bảo vệ dữ liệu **trên phương tiện lưu trữ**. Một sơ đồ dữ liệu hoàn chỉnh phải xét cả nơi lưu bản sao, log và file tạm:

| Nơi lưu | Dữ liệu có thể xuất hiện | Điều cần bảo vệ |
|---|---|---|
| Table data files và indexes | Plaintext của cột và giá trị index | Volume/storage encryption, quyền filesystem |
| WAL/redo/transaction log | Thay đổi dữ liệu phục vụ crash recovery | Encryption của volume và WAL archive |
| Temporary files, swap, sort spill | Bản sao trung gian khi DB/JVM xử lý | Disk encryption, giới hạn temp, OS permissions |
| Snapshot/volume clone | Bản sao của cả cơ sở dữ liệu | Snapshot encryption và quyền truy cập |
| Logical dump/CSV export | Kết quả SELECT ở dạng có thể đọc | File encryption, TLS khi chuyển, retention |
| Full backup và WAL archive | Dữ liệu để khôi phục | Mã hóa, quyền đọc bản lưu, kiểm thử restore |
| Read replica và DR site | Bản sao dữ liệu ở node khác | Chính sách mã hóa at rest và TLS độc lập |
| Redis/search index/broker | Projection, event, cache entry | Encryption/identity/TTL theo hệ thống |
| Logs/APM/heap dump | SQL parameters, PII, tokens | Redaction, phân quyền xem, giới hạn thời gian giữ |

**Một nơi lưu plaintext không được quản lý có thể phá toàn bộ mục tiêu mã hóa database.** Ví dụ data volume được mã hóa nhưng bản dump CSV nằm ở một bucket mở công khai vẫn gây rò rỉ.

### 7.1. Phân loại dữ liệu trước khi chọn lớp mã hóa

Với từng field, hãy ghi rõ:

- Dữ liệu là công khai, nội bộ, PII, credential, thông tin tài chính hay nhạy cảm khác?
- Ai cần plaintext, trong bước nào của nghiệp vụ, trong bao lâu?
- Có cần WHERE, LIKE, ORDER BY, JOIN hoặc index trên nội dung không?
- Field được sao chép đến cache, log, search index, export hay backup nào?
- Mức độ tổn thất chấp nhận nếu mất khóa giải mã là bao nhiêu?
- Quy định/hợp đồng có yêu cầu khóa do khách hàng kiểm soát, vùng lưu hoặc lịch rotation không?

Không phải mọi cột đều cần mã hóa ở tầng ứng dụng. Chọn đúng lớp bảo vệ theo threat model và yêu cầu sử dụng.

## 8. Các lớp mã hóa dữ liệu khi lưu

### 8.1. Volume và disk encryption

Mã hóa block/volume bảo vệ dữ liệu lưu khi ổ đĩa hoặc snapshot bị lấy cắp **mà kẻ tấn công không có quyền với khóa giải mã**.

Ưu điểm: thường ít thay đổi code, có thể bao phủ nhiều loại file trên cùng volume và tích hợp với KMS của hạ tầng.

Giới hạn:

- Khi volume đang mount và DB chạy, PostgreSQL vẫn đọc plaintext ở tầng logic; tài khoản SQL đủ quyền vẫn SELECT được.
- Không tự mã hóa logical dump xuất ra nơi khác.
- Không ngăn một process đã có quyền OS/DB phù hợp đọc dữ liệu.
- Backup, snapshot, swap, temp và WAL archive cần kiểm kê độc lập.

### 8.2. Transparent Database Encryption hoặc mã hóa do DB thực hiện

Một số DBMS hay dịch vụ managed hỗ trợ encryption cho tablespace, data files hoặc các đối tượng lưu trữ. Phạm vi bảo vệ, cách quản lý khóa và WAL/temp/backup coverage phụ thuộc sản phẩm/phiên bản cụ thể.

Khi chọn, cần xác nhận:

1. Những file nào thực sự được mã hóa?
2. Ai giữ và có quyền gọi key, DBA hay cloud operator?
3. Có bao phủ snapshots, backups, replicas và file tạm không?
4. Khi rotate key, dữ liệu cũ được mã hóa lại thế nào?
5. SELECT và logical export có trả plaintext cho tài khoản có quyền không?

Không giả định mọi bản phân phối PostgreSQL có cùng một tính năng TDE. Phải đối chiếu với đúng platform và cấu hình đang chạy.

### 8.3. Mã hóa trường ở database

Có thể dùng hàm mã hóa trong database hoặc extension như pgcrypto trên PostgreSQL. Nhưng nếu SQL cung cấp plaintext và key tới DB, database engine đã thấy dữ liệu ở dạng rõ và có thể ghi chúng vào một số vùng nhớ hoặc log tùy cách dùng.

Do đó mã hóa cột ở DB không tự chứng minh rằng tài khoản vận hành DB không thể quan sát plaintext. Mô hình này cần đánh giá đặc biệt đường truyền key, quyền gọi hàm decrypt và log có tham số nhạy cảm.

### 8.4. Mã hóa trường ở ứng dụng Java

Với trường rất nhạy cảm, Java có thể mã hóa **trước khi ghi qua JDBC**, giữ key ngoài quyền truy cập database:

~~~text
Plaintext trong Java service
       |
       v
AEAD encryption (key + nonce + AAD)
       |
       v
keyId + nonce + ciphertext + authentication tag
       |
       v
JDBC TLS -> PostgreSQL lưu ciphertext
~~~

Ưu điểm:

- Bản dump database chỉ chứa ciphertext đối với field đã mã hóa ở app.
- Quyền SELECT ở DB không nhất thiết đồng nghĩa có quyền giải mã.
- Có thể phân tách chính sách quyền dùng khóa khỏi quyền truy cập bảng.

Đánh đổi:

- LIKE, ORDER BY, range query và index trên plaintext không còn vận hành trực tiếp như trước.
- Phải quản lý key version, format ciphertext, lỗi decrypt và rotation.
- Java service sẽ giữ plaintext ở memory khi xử lý.
- Một attacker có thể điều khiển app đang có quyền giải mã vẫn có thể khai thác dữ liệu trong phạm vi quyền đó.

### 8.5. Chọn lớp bảo vệ theo mối đe dọa

| Cơ chế | Nghe lén mạng | Trộm file lưu offline | DB-only reader thấy plaintext? | SQL bình thường trên field |
|---|---|---|---|---|
| TLS | Bảo vệ hop TLS | Không | Có, nếu user có quyền | Có |
| Disk/volume encryption | Không tự bảo vệ mạng | Có, nếu key được bảo vệ | Thường có | Có |
| DB/TDE | Không tự bảo vệ mạng | Có theo phạm vi engine | Thường có nếu được SELECT | Thường có |
| App-level field encryption | Che field ngay từ khi rời app; vẫn dùng TLS | Có cho ciphertext | Có thể không, nếu tách quyền key | Bị hạn chế |
| Authorization/RLS | Không thay TLS | Không thay encryption | Giới hạn user nào đọc | Có trong phạm vi quyền |

Các lớp bảo vệ thường **được phối hợp**, không phải chỉ chọn một.

## 9. AEAD: mã hóa có xác thực

Đối với mã hóa field trong Java, nên ưu tiên primitive đã được đánh giá rộng rãi như **AES-GCM**, qua cryptographic API được hỗ trợ. AEAD (*authenticated encryption with associated data*) giúp:

- Che plaintext khỏi bên không có key.
- Phát hiện ciphertext/tag bị sửa.
- Xác thực thêm metadata không mã hóa (*AAD*) gắn với ngữ cảnh record.

Một envelope cần tối thiểu:

~~~text
formatVersion + keyId + nonce + ciphertextAndTag
~~~

Trong Java, Cipher với AES/GCM/NoPadding thường xuất ra ciphertext nối với authentication tag sau doFinal.

### 9.1. Nonce và khóa

Với AES-GCM thường dùng nonce 96 bit (12 byte). Nonce **không cần bí mật**, có thể lưu cùng ciphertext, nhưng không được tái sử dụng cặp nonce–key giữa hai lần mã hóa. Tái sử dụng có thể phá nghiêm trọng tính bảo mật.

- Tạo nonce bằng SecureRandom hoặc chiến lược duy nhất được thiết kế chặt.
- Không dùng một IV cố định, timestamp đơn giản hoặc chuỗi cứng cho mọi record.
- Nếu dùng nonce random, tính toán giới hạn số lần mã hóa trên một key và rủi ro va chạm khi hệ thống mở rộng.
- Nếu dùng counter, phải chống trùng qua restart, đa instance và failover.
- Không tự thiết kế crypto từ AES-ECB hoặc CBC không có cơ chế xác thực phù hợp.

### 9.2. AAD: chống tráo ciphertext giữa record

AAD là metadata được xác thực nhưng không mã hóa, ví dụ:

~~~text
AAD = encode(tenantId, recordId, fieldName)
~~~

Encoding cần không mơ hồ: dùng chiều dài cố định hoặc length-prefix, tránh nối các chuỗi có thể va chạm biểu diễn. Khi giải mã phải dùng cùng AAD; ciphertext của tenant A được ghép sang tenant B sẽ không qua tag check nếu key/AAD phù hợp.

**AEAD không tự chống replay một ciphertext hợp lệ cũ vào đúng ngữ cảnh cũ.** Nếu cần ngăn rollback về phiên bản record cũ, còn phải có version/invariant/transaction bền vững ở tầng nghiệp vụ.

### 9.3. Không nhầm encoding với mã hóa

Base64 là cách biểu diễn binary, **không che dữ liệu**. Hash không có khóa cũng không phải mã hóa đảo ngược. Encryption, hashing và encoding giải quyết các vấn đề khác nhau; cần chọn theo mục đích.

## 10. Ví dụ Java: AES-GCM mã hóa trường nhạy cảm

Ví dụ này minh họa mã hóa ở **application boundary** trước khi dữ liệu đi qua JDBC. Khóa được lấy qua một KeyProvider trừu tượng; không hardcode key vào source hoặc lưu cùng bảng mà không có ranh giới bảo vệ.

### 10.1. Contract khóa và envelope

~~~java
import javax.crypto.SecretKey;

public record KeyRef(String keyId, SecretKey key) {}

public interface KeyProvider {
    KeyRef currentForEncryption();
    SecretKey forDecryption(String keyId);
}

public record CipherEnvelope(
    String keyId,
    String nonceB64,
    String ciphertextAndTagB64
) {}
~~~

Base64 chỉ giúp biểu diễn binary dưới dạng string, **không** thay thế mã hóa. Trong hệ thống thực tế, thêm formatVersion của envelope và giới hạn kích thước từng trường.

### 10.2. Cài đặt mã hóa và giải mã

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Objects;
import java.util.UUID;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class CustomerFieldCrypto {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private final SecureRandom random = new SecureRandom();
    private final KeyProvider keys;

    public CustomerFieldCrypto(KeyProvider keys) {
        this.keys = Objects.requireNonNull(keys);
    }

    public CipherEnvelope encrypt(
            String plaintext,
            long tenantId,
            UUID recordId,
            String fieldName) throws GeneralSecurityException {

        Objects.requireNonNull(plaintext);
        Objects.requireNonNull(recordId);
        Objects.requireNonNull(fieldName);

        KeyRef current = keys.currentForEncryption();
        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            current.key(),
            new GCMParameterSpec(TAG_BITS, nonce)
        );
        cipher.updateAAD(aad(tenantId, recordId, fieldName));

        byte[] encrypted = cipher.doFinal(
            plaintext.getBytes(StandardCharsets.UTF_8)
        );

        return new CipherEnvelope(
            current.keyId(),
            Base64.getEncoder().encodeToString(nonce),
            Base64.getEncoder().encodeToString(encrypted)
        );
    }

    public String decrypt(
            CipherEnvelope value,
            long tenantId,
            UUID recordId,
            String fieldName) throws GeneralSecurityException {

        Objects.requireNonNull(value);
        byte[] nonce = Base64.getDecoder().decode(value.nonceB64());
        if (nonce.length != NONCE_BYTES) {
            throw new GeneralSecurityException("Invalid nonce size");
        }

        SecretKey key = keys.forDecryption(value.keyId());
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE,
            key,
            new GCMParameterSpec(TAG_BITS, nonce)
        );
        cipher.updateAAD(aad(tenantId, recordId, fieldName));

        byte[] plaintext = cipher.doFinal(
            Base64.getDecoder().decode(value.ciphertextAndTagB64())
        );
        return new String(plaintext, StandardCharsets.UTF_8);
    }

    private static byte[] aad(
            long tenantId,
            UUID recordId,
            String fieldName) {

        byte[] field = fieldName.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(8 + 16 + 4 + field.length)
            .putLong(tenantId)
            .putLong(recordId.getMostSignificantBits())
            .putLong(recordId.getLeastSignificantBits())
            .putInt(field.length)
            .put(field)
            .array();
    }
}
~~~

Đây là **mã minh họa**, không phải một triển khai KMS đầy đủ. Cần bổ sung kiểm tra null/độ dài cipher input, format version, chính sách key usage, giới hạn số lần encrypt theo key, xử lý lỗi provider và các biện pháp bảo vệ memory/log.

Điểm cần hiểu:

- Mỗi lần encrypt tạo nonce mới; SecretKey phải là khóa AES phù hợp, được cấp qua nguồn an toàn.
- GCMParameterSpec(128, nonce) chỉ định authentication tag 128 bit.
- updateAAD gắn ciphertext với tenant, record và tên field.
- doFinal ở decrypt sẽ kiểm tra authentication tag; sai key/AAD/ciphertext phải thất bại.
- Envelope giữ keyId để hỗ trợ giải mã ciphertext từ những key version cũ.
- String plaintext và byte arrays tồn tại trong memory JVM; không ghi vào log hay error response.
- Đổi recordId, tenantId hoặc fieldName có thể yêu cầu re-encryption vì AAD thay đổi.
- Cần bảo đảm **không tái sử dụng nonce trong cùng key** khi scale qua nhiều instance.

### 10.3. Test crypto quan trọng

| Test | Điều phải xác nhận |
|---|---|
| Round trip | Giải mã đúng với key và AAD |
| Hai lần encrypt cùng plaintext | Nonce mới, ciphertext khác nhau theo cơ chế random |
| Sửa ciphertext hoặc tag | Decrypt thất bại, không trả plaintext giả |
| Đổi tenant/record/field | AAD verification thất bại |
| Key version cũ | Vẫn decrypt được theo chính sách retention |
| Thiếu key | Fail-closed, báo lỗi có kiểm soát |
| Input Base64/nonce sai | Từ chối payload |
| Unicode/giới hạn kích thước | Đúng encoding, không tiêu thụ memory vô hạn |
| SQL log, exception và trace | Không lộ plaintext hay secret |

Chỉ test “mã hóa rồi giải mã lại đúng chuỗi” chưa đủ; một thuật toán không xác thực cũng có thể qua test đó.

## 11. Lưu ciphertext và giới hạn truy vấn trên dữ liệu mã hóa

Một schema đơn giản cho hồ sơ có field nhạy cảm:

~~~sql
CREATE TABLE customer_profiles (
    tenant_id bigint NOT NULL,
    customer_id uuid NOT NULL,
    display_name text NOT NULL,
    secret_key_id text NOT NULL,
    secret_nonce bytea NOT NULL,
    secret_ciphertext bytea NOT NULL,
    version bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, customer_id)
);
~~~

Có thể lưu envelope thành ba cột hoặc một blob có format version; bytea lưu binary trực tiếp mà không cần overhead Base64. Khi cài đặt, phải thống nhất format, keyId, nonce, authentication tag và cơ chế migrate sang format mới.

**Tất cả metadata cần giải mã phải được ghi nguyên tử với ciphertext.** Nếu cập nhật keyId nhưng để ciphertext cũ, record có thể không giải mã được. Với nhiều writer, dùng optimistic version, transaction và constraint để ngăn cập nhật đè.

### 11.1. Quy trình ghi ở Java

~~~text
API xác thực tenant + quyền
  -> Kiểm tra dữ liệu nghiệp vụ
  -> Lấy key version hiện hành từ KeyProvider
  -> AES-GCM encrypt với AAD gắn tenant/record/field
  -> BEGIN transaction trên DB
  -> INSERT/UPDATE keyId + nonce + ciphertext + version
  -> COMMIT
  -> Trả DTO theo quyền, không log plaintext
~~~

Tạo ciphertext **trước khi mượn connection DB** có thể giảm thời gian giữ connection nếu việc lấy khóa từ KMS mất thời gian. Nhưng nếu AAD cần version mới hoặc ID được sinh trong DB, phải thiết kế để các giá trị đó ổn định và khớp với transaction. Một transaction thất bại có thể để ciphertext đã tính nằm trong memory nhưng không được commit; đây không phải một record đã ghi.

Khi COMMIT timeout, không suy “chưa ghi”. Retry bằng business key/idempotency ổn định; encrypt lại với nonce mới tạo ciphertext khác nhưng không được tạo hai bản ghi nghiệp vụ.

### 11.2. Ciphertext có thể làm mất khả năng search

Với randomized AEAD, hai lần encrypt cùng plaintext bằng cùng key nhưng nonce mới tạo hai ciphertext khác nhau. Vì thế:

~~~sql
-- Không thể tìm chính xác email plaintext bằng
-- cách encrypt lại email rồi so ciphertext.
SELECT customer_id
FROM customer_profiles
WHERE secret_ciphertext = :encrypted_again;
~~~

LIKE, prefix search, range comparison và ORDER BY trên plaintext cũng không tự làm việc trên ciphertext. Khi thiết kế persistence, phải quyết định:

- Tra cứu theo customerId/business ID không nhạy cảm rồi decrypt field sau khi xác thực quyền.
- Lưu read projection/search index theo chính sách rủi ro riêng.
- Với equality lookup phù hợp, cân nhắc blind index dùng **HMAC có khóa riêng** trên giá trị chuẩn hóa.
- Dùng tokenization/lookup service nếu cần giảm quyền truy cập trực tiếp dữ liệu gốc.
- Tránh sáng tạo “mã hóa cho phép mọi phép so sánh” mà chưa đánh giá rò thông tin và yêu cầu mật mã.

### 11.3. Blind index vẫn tiết lộ mẫu bằng nhau

Ví dụ tư duy:

~~~text
normalizedEmail = normalize(email)
lookupToken     = HMAC(indexKey, normalizedEmail)
~~~

Một chỉ mục HMAC giúp thực hiện equality lookup nhưng vẫn làm lộ quan hệ bằng nhau/tần suất xuất hiện và metadata truy vấn. Nếu index key bị lộ, attacker có thể thử từ điển; dữ liệu có miền nhỏ đặc biệt dễ suy đoán từ các mẫu.

Cần:

- Tách HMAC index key khỏi encryption key.
- Chuẩn hóa đúng business semantics, không tự lowercase mọi identifier.
- Có quy trình rotate index key và tái xây dựng index, giữ UNIQUE consistency.
- Không dùng SHA-256 không khóa trên email/số điện thoại rồi gọi đó là mã hóa.
- Không dùng blind index như thể cung cấp prefix/range search an toàn.

### 11.4. Mã hóa không thay database invariant

AEAD phát hiện ciphertext bị sửa với tag sai, nhưng không chứng minh một ciphertext cũ hợp lệ không bị replay trong cùng AAD. Nó cũng không ngăn một người có quyền Java hợp lệ sửa field trái quy tắc nghiệp vụ. Cần phiên bản record, authorization, audit, transaction và các ràng buộc dữ liệu tương ứng.

## 12. Quản lý khóa: quan trọng không kém thuật toán

Câu hỏi then chốt không phải chỉ là “AES-256 hay AES-128”, mà là **ai cấp khóa, ai có quyền giải mã, khóa lưu ở đâu, khóa sống bao lâu và làm gì khi mất hoặc lộ khóa**.

### 12.1. Những điều không nên làm

- Hardcode key trong repository hoặc commit vào Git.
- Lưu khóa giải mã plaintext trong cùng bảng/cùng backup với ciphertext mà không có cơ chế bảo vệ độc lập.
- Đưa key lên URL, SQL string, log, metrics label hoặc exception.
- Sử dụng một khóa duy nhất cho mọi tenant, môi trường và mục đích mà không có đánh giá blast radius.
- Cho mọi instance có quyền quản trị KMS nếu chỉ cần decrypt một tập field.
- Xóa key cũ ngay khi chuyển writer sang key mới mà chưa re-encrypt toàn bộ bản lịch sử.
- Nhầm “mã hóa key bằng một key khác cùng lưu trong config” với key separation thực chất.

### 12.2. KMS, HSM và key hierarchy

Một thiết kế envelope encryption có thể dùng:

- **KEK (key-encryption key):** khóa được quản lý trong KMS/HSM, dùng để bảo vệ các data key.
- **DEK (data-encryption key):** khóa mã hóa dữ liệu ở ứng dụng; có thể dùng cho một record, một tenant, một tập/epoch dữ liệu tùy thiết kế.
- **Encrypted DEK:** DEK được wrap dưới KEK; lưu cùng record/metadata hoặc trong kho key thích hợp.
- **Key ID/version:** cho phép chọn KEK hoặc DEK thích hợp trong quá trình giải mã.

~~~mermaid
flowchart TD
    K[("KMS / KEK")] -->|wrap / unwrap theo identity| D["DEK trong service khi sử dụng"]
    D -->|AEAD encrypt| C[("DB lưu ciphertext")]
    K --> W[("DB/metadata lưu wrapped DEK")]
    C --> R["Decrypt path"]
    W --> R
    R -->|KMS unwrap theo quyền| K
~~~

Sơ đồ mô tả logic; KMS thực tế thường cung cấp API GenerateDataKey/Encrypt/Decrypt hoặc primitive tương ứng. Có thể chọn cách gọi KMS trực tiếp hay cache data key trong memory có giới hạn, tùy SLO và khả năng kiểm soát quyền.

**Envelope encryption không có nghĩa database hiểu/giữ plaintext DEK.** Nếu ứng dụng mã hóa trước JDBC và DB chỉ thấy ciphertext, quyền decrypt có thể phân tách khỏi quyền đọc DB.

### 12.3. Least privilege của quyền dùng khóa

Xét hai service:

- Order Service được phép encrypt/decrypt một số field liên quan đơn hàng.
- Reporting Service chỉ cần số lượng đơn theo tenant, không cần decrypt PII.

Không cấp quyền decrypt cho Reporting Service chỉ vì nó SELECT cùng database. Nếu cần trường dữ liệu đã khử định danh, tạo projection phù hợp thay vì để mọi worker lấy raw ciphertext và key.

Với ứng dụng multi-tenant, có thể cân nhắc khóa khác nhau theo tenant hoặc scope dữ liệu, nhưng số lượng khóa, hiệu năng và quản trị tăng theo. Phải xác định danh tính tenant từ security context đáng tin, không chỉ từ một biến đầu vào do khách hàng tự đặt.

### 12.4. Phân biệt key availability và data availability

Nếu database còn sống nhưng KMS không sẵn sàng, ứng dụng có thể truy vấn ciphertext song **không thể decrypt**. Cần quyết định fail-closed, queue thao tác, sử dụng cached data key theo chính sách được duyệt hoặc trả lỗi dịch vụ tạm thời.

Không tự fallback sang trả dữ liệu plaintext từ backup/cache không được bảo vệ. Một “fallback” làm mất ranh giới bảo mật có thể gây hậu quả nghiêm trọng hơn outage.

### 12.5. Kiểm soát thời gian sống của plaintext key

Khóa khi được giải mã vào memory cần:

- Giới hạn phạm vi process/instance được phép nhận.
- Tránh log, heap dump, debug endpoint và serialization.
- Giới hạn thời gian cache key và có kế hoạch làm mới.
- Dùng cơ chế secret distribution và identity/role ngắn hạn phù hợp.
- Cảnh báo truy cập KMS bất thường, thay đổi policy và thất bại decrypt.

Không thể đảm bảo mọi bản sao key byte đã được xóa khỏi bộ nhớ JVM chỉ bằng một câu Arrays.fill khi thư viện đã tạo nhiều bản copy; cần harden runtime và giới hạn quyền đọc memory.

## 13. Rotation: ba việc khác nhau

### 13.1. Rotate chứng chỉ TLS

Mục tiêu là thay private key/chứng chỉ hoặc trust anchor cho các connection mới. Quy trình thường cần:

1. Phát hành chứng chỉ mới và xác nhận SAN/hostname.
2. Phân phối CA chain hoặc trust anchor tới các client trước thời điểm cutover khi đổi CA.
3. Triển khai server certificate.
4. Kiểm thử kết nối mới từ từng ứng dụng/region/instance.
5. Theo dõi handshake failures; thay kết nối cũ theo lifecycle pool.
6. Thu hồi chứng chỉ cũ theo cửa sổ tương thích và kế hoạch incident.

Không thay CA và chứng chỉ server trong một bước khiến toàn bộ client chưa nhận trust anchor mới bị ngắt kết nối.

### 13.2. Rotate key mã hóa field

Một quy trình khả dụng:

~~~text
key-v1: có thể decrypt dữ liệu cũ
key-v2: bắt đầu dùng cho encrypt mới
        |
        +-- Bản ghi mới -> keyId=v2
        +-- Bản cũ v1 -> vẫn decrypt qua key-v1
        |
        v
Backfill re-encrypt v1 -> v2 theo batch
        |
        v
Đối soát không còn ciphertext phụ thuộc v1 trong scope
        |
        v
Đóng quyền dùng key-v1 theo chính sách/retention
~~~

**Không xóa key-v1 ngay lúc v2 bắt đầu hoạt động** nếu dữ liệu cũ, backup hoặc snapshot vẫn cần v1 để restore. Bản backup lưu dữ liệu mã hóa bằng v1 vẫn cần khả năng truy cập khóa tương ứng trong kịch bản phục hồi, hoặc được rewrap/re-encrypt bằng cơ chế an toàn đã thử nghiệm.

### 13.3. Rotate KEK khác re-encrypt dữ liệu bằng DEK mới

Nếu envelope encryption cho phép rewrap DEK dưới KEK mới, có thể không cần giải mã rồi mã hóa lại toàn bộ nội dung dữ liệu. Nhưng rewrap KEK **không loại bỏ hậu quả nếu DEK đã bị lộ**. Khi nghi DEK compromise, cần tạo DEK mới và re-encrypt dữ liệu liên quan theo quy trình ứng phó.

Phải phân biệt:

- **Key alias đổi:** tên tham chiếu chuyển sang key mới, nhưng ciphertext cũ có thể còn phụ thuộc key version cũ.
- **KEK rotate/rewrap:** thay khóa bảo vệ DEK.
- **DEK rotate/re-encrypt:** thay khóa trực tiếp bảo vệ dữ liệu.
- **Revocation:** thu hồi quyền dùng key; có thể khiến dữ liệu không giải mã được nếu làm trước khi chuyển đổi xong.

### 13.4. Idempotent batch re-encryption

Một job re-encrypt theo lô cần đọc keyId hiện hành, decrypt và mã hóa lại bằng key version mới rồi UPDATE theo expectedVersion/keyId cũ. Nếu record bị writer khác thay đổi trong lúc job xử lý, UPDATE phải thất bại hoặc retry dựa trên record mới; không ghi đè dữ liệu mới bằng bản plaintext đọc từ trước.

Dùng checkpoint và đo phạm vi:

~~~sql
SELECT secret_key_id, COUNT(*) AS rows_per_key
FROM customer_profiles
GROUP BY secret_key_id
ORDER BY secret_key_id;
~~~

Số lượng row dùng key cũ giảm về 0 **trong bảng hiện tại** chưa chứng minh backup, archive, replica offline hoặc event log không còn phụ thuộc key cũ. Rotation plan phải bao phủ phạm vi retention và DR.

## 14. Bảo vệ backup, WAL, replica và khả năng khôi phục

Một database có cột mã hóa không đồng nghĩa các thành phần phục hồi đã an toàn. Với dữ liệu quan trọng, phải nhìn toàn bộ chu kỳ **ghi – sao chép – lưu trữ – phục hồi**.

### 14.1. WAL và point-in-time recovery

PostgreSQL dùng WAL để hỗ trợ crash recovery và replication. Khi database ghi plaintext vào bảng theo cơ chế truyền thống, WAL có thể chứa thông tin về những thay đổi cần phục hồi; bảo vệ data files mà bỏ qua WAL archive là không đủ.

Những điểm cần hỏi:

- WAL đang được giữ trên volume nào? Volume đó có mã hóa không?
- WAL archive được truyền qua TLS tới đâu và được lưu thế nào?
- Ai có quyền tải/download WAL và backup?
- WAL retention có tương thích với RPO, restore và chính sách xóa dữ liệu không?
- Nếu dùng app-level encrypted field, liệu các bản ghi WAL và full backup chỉ chứa ciphertext của field đó hay còn luồng ghi plaintext ở nơi khác?

Đừng ghi đường dẫn chứa credentials, token hoặc bản dump nhạy cảm vào các log vận hành chỉ để tiện debug.

### 14.2. Replication cũng cần kiểm tra encryption ở cả hai đầu

~~~text
Primary data volume: encrypted
      |
      | WAL streaming qua kết nối cần kiểm tra TLS
      v
Replica data volume: cũng phải được bảo vệ
      |
      v
Replica snapshot/backup: bảo vệ riêng
~~~

Primary được mã hóa tại rest không tự đảm bảo replica có cùng chính sách. Chọn standby từ managed service khác, tạo cross-region DR hoặc restore sang môi trường staging đều mở thêm nơi dữ liệu xuất hiện. Cần kiểm tra cả endpoint TLS, IAM, volume encryption và quyền của các service account trong DR site.

Một replica được mã hóa cũng **không thay thế backup**: xóa nhầm hoặc thao tác ghi sai có thể được replicate. Backup lịch sử và recovery test là kiểm soát riêng.

### 14.3. Restore phải phục hồi cả dữ liệu và quyền dùng khóa

Một bài kiểm thử restore hợp lệ phải chứng minh:

1. Khôi phục database tới thời điểm yêu cầu thành công.
2. Dữ liệu mã hóa ở application layer vẫn có keyId và envelope đúng.
3. KeyProvider/KMS trong môi trường restore có **quyền hợp lệ** tới key version cần thiết.
4. Các bản ghi lịch sử có thể giải mã, xác thực tag và AAD theo contract.
5. Recovery user/role không bị mở rộng quyền chỉ để “cho restore chạy được”.
6. Backup chứa cả metadata cần thiết để map key version, nhưng không vô tình chứa plaintext master key.
7. Cấu hình TLS, audit và network policy được khôi phục phù hợp.

Có hai kiểu outage khác nhau: **database không phục hồi được** và **database phục hồi được nhưng dữ liệu không thể giải mã vì mất khóa**. Cần kịch bản diễn tập cho cả hai.

### 14.4. Backup encryption có thể dùng khóa khác

Khóa mã hóa backup không nhất thiết phải là cùng key với field-level encryption hoặc disk encryption. Phân tách key giúp giảm blast radius, nhưng làm tăng công việc quản lý phiên bản và quyền khôi phục.

Với export CSV/PDF ngoài DB, quy định khi nào được tạo bản plaintext, người nào được tải, thời hạn xóa, kênh phân phối và có cần mã hóa file ứng dụng riêng không.

## 15. Mã hóa, hashing, tokenization và masking khác nhau thế nào?

| Kỹ thuật | Có thể phục hồi plaintext gốc? | Mục đích điển hình | Chú ý |
|---|---|---|---|
| Mã hóa đối xứng (AES-GCM) | Có, với key | Bảo vệ PII cần đọc lại | Nonce/key/tag/AAD và quản lý khóa |
| Password hashing thích hợp | Không theo chức năng thiết kế | Xác minh mật khẩu | Dùng password hashing như Argon2id, scrypt hoặc bcrypt theo policy và thư viện hiện hành; salt riêng, cost phù hợp |
| HMAC/blind index | Không phải cơ chế decrypt | Tra cứu bằng nhau hoặc xác thực message | Cần khóa riêng, vẫn rò equality/frequency |
| Tokenization | Theo thiết kế, có thể map qua vault | Giảm phạm vi xử lý dữ liệu thật | Vault và quyền detokenize là phần nhạy cảm |
| Masking/redaction | Không nhằm phục hồi đầy đủ | Ẩn dữ liệu trong UI/log | Không thay encryption at rest |
| Base64/hex | Có thể decode ngay không cần secret | Encoding binary | Hoàn toàn không phải mã hóa |
| Compression | Có thể decompress | Giảm kích thước | Không có bảo đảm bảo mật |

### 15.1. Không dùng AES để lưu mật khẩu người dùng

Hệ thống thường chỉ cần **kiểm tra** mật khẩu, không cần giải mã lấy lại chuỗi gốc. Nên dùng password hashing chuyên dụng, chống brute force bằng hàm đủ tốn tài nguyên và tham số được đánh giá phù hợp.

Không dùng SHA-256 đơn thuần hoặc mã hóa AES có thể đảo ngược như một thay thế cho password hash. Nếu cần tương tác với một secret thực sự phải phục hồi (ví dụ credential để gọi hệ ngoài), đó là bài toán secret storage có access control, rotation và KMS riêng, không phải password storage thông thường.

### 15.2. Masking không làm mất dữ liệu gốc khỏi database

API trả số điện thoại dạng 09*****123 không chứng minh cột database đã mã hóa. Masking chỉ thay đổi representation ở nơi hiển thị. Một người có quyền SELECT bản gốc vẫn có thể thấy đầy đủ dữ liệu nếu thiếu authorization và encryption tương ứng.

## 16. Mã hóa trong mô hình multi-tenant và dữ liệu nhạy cảm

Multi-tenant cần phân biệt:

- **Data isolation:** tenant A không đọc dữ liệu tenant B.
- **Key isolation:** tenant nào hoặc service nào được quyền dùng khóa giải mã của tập dữ liệu nào.
- **Operational isolation:** backup/restore/log/cache/search có phân biệt phạm vi tenant hay không.

Một app-level AEAD dùng AAD chứa tenantId giúp phát hiện ciphertext được đưa sang tenant khác khi giải mã, nhưng **không thay** truy vấn có WHERE tenant_id hoặc RLS. Nếu một endpoint SELECT cả hai tenant rồi cố giải mã, nó vẫn có thể lộ metadata hoặc sinh lỗi không mong muốn.

### 16.1. Ranh giới application và persistence

~~~text
API request
   |
   +-- Authenticate principal
   +-- Authorize tenant, action, purpose
   |
   v
Application Service
   |
   +-- Lấy key theo identity / scope được phép
   +-- Encrypt hoặc decrypt đúng field
   |
   v
Repository/DAO
   |
   +-- Parameterized SQL với tenant scope
   +-- Ghi ciphertext và metadata nguyên tử
   +-- Kiểm soát expectedVersion/concurrency
~~~

Không để controller gửi arbitrary keyId rồi tự chọn bất kỳ key trong KMS. KeyId được lưu như metadata phải được kiểm tra thuộc phạm vi dữ liệu và identity đang xử lý. Việc app có quyền giải mã mọi key theo một role quá rộng làm mất nhiều lợi ích phân tách DB reader và decryptor.

### 16.2. AAD, record ID và di chuyển dữ liệu

Nếu AAD gắn tenantId + customerId, việc chuyển ownership một record từ tenant A sang B hoặc đổi customerId không thể chỉ sửa cột tenant_id rồi giữ ciphertext cũ. Decrypt sẽ thất bại với AAD mới.

Cần định nghĩa migration chính thức:

1. Đọc và xác thực record trong ngữ cảnh cũ.
2. Kiểm tra quyền chuyển ownership.
3. Encrypt lại với AAD/key policy của ngữ cảnh mới và nonce mới.
4. Ghi metadata/ciphertext và tenant/record mapping nguyên tử khi có thể.
5. Kiểm thử read path mới; đối soát và xử lý record cũ theo retention.

Không tắt AAD để cho việc chuyển tenant “dễ hơn”; như vậy mở lại rủi ro ciphertext bị chuyển qua ngữ cảnh sai.

### 16.3. Cache và log là những đường đi vòng

Một service decrypt dữ liệu từ DB rồi cache DTO plaintext ở Redis có thể vô tình đưa dữ liệu nhạy cảm sang một store với quyền truy cập rộng hơn. Tương tự, log một record Java bằng toString() sau decrypt có thể tạo bản sao plaintext lâu dài trong hệ thống quan sát.

Cần quy tắc:

- Trường nào được cache, ở dạng rõ hay ciphertext, trong thời gian bao lâu?
- Ai có quyền đọc cache hoặc traces?
- Cache key có cần tenant/actor/scope không?
- Khi dữ liệu hoặc quyền bị thu hồi, cache/invalidation xử lý thế nào?
- Có thể lấy record qua search index mà không qua kiểm tra quyền Java không?

## 17. Migrate plaintext sang ciphertext không làm gián đoạn ứng dụng

Ví dụ hệ thống đang có cột customer_phone plaintext, muốn bổ sung mã hóa field-level. Thay đổi này tương tự một bài **tiến hóa dữ liệu** có backfill và mixed-version rollout, không phải một câu ALTER COLUMN đơn lẻ.

### 17.1. Expand schema

~~~sql
ALTER TABLE customer_profiles
ADD COLUMN phone_key_id text,
ADD COLUMN phone_nonce bytea,
ADD COLUMN phone_ciphertext bytea;
~~~

Tạm giữ cột phone plaintext trong giai đoạn chuyển tiếp nếu cần tương thích. Đây là thời kỳ **có hai bản biểu diễn**, tăng bề mặt rủi ro dữ liệu, cần giới hạn thời gian, quyền và logging.

### 17.2. Triển khai writer tương thích

Trong giai đoạn chuyển tiếp, các writer mới có thể ghi plaintext cũ và ciphertext mới trong cùng transaction theo chính sách rollout; hoặc dùng một giai đoạn chuyển riêng để buộc mọi writer mới chỉ ghi encrypted sau khi reader tương thích. Cần kiểm kê toàn bộ API, batch, consumer và admin tools để không còn writer cũ bỏ qua ciphertext.

**Không tin rằng trigger PostgreSQL có thể tự app-encrypt bằng key mà DB tuyệt đối không được biết.** Nếu mục tiêu là tách quyền giải mã khỏi DB, backfill và writer cần chạy trong ứng dụng/worker có quyền key thích hợp.

### 17.3. Backfill theo lô, tránh giữ plaintext lâu

~~~text
Chọn N record thiếu ciphertext
    |
    +-- Đọc plaintext trong scope DB/Java được bảo vệ
    +-- Encrypt bằng key và nonce mới, AAD đúng
    +-- UPDATE ciphertext với expectedVersion/điều kiện còn đúng
    +-- COMMIT batch
    +-- Lưu checkpoint theo cơ chế replay idempotent
    +-- Kiểm tra số lỗi/tag/NULL/mismatch
~~~

Nếu worker đọc plaintext rồi chờ rất lâu mới UPDATE, một writer khác có thể đã sửa số điện thoại. Backfill phải dùng expectedVersion hoặc điều kiện so sánh nguồn cũ và retry theo row mới, không ghi ciphertext của giá trị đã cũ đè lên nội dung mới.

Cần tránh lưu plaintext trong checkpoint/log hoặc queue. Một job có thể resume bằng ID và trạng thái, không cần ghi lại số điện thoại của khách hàng vào file công việc.

### 17.4. Đối soát trước cutover

Các kiểm tra:

- Mọi record trong phạm vi có keyId, nonce và ciphertext hợp lệ.
- Giải mã ciphertext bằng AAD/key thích hợp khớp plaintext nguồn trong cùng snapshot hợp lệ.
- Không còn writer mới bỏ qua ciphertext hoặc ghi sai key version.
- Tài khoản không có quyền decrypt chỉ thấy ciphertext dù SELECT được bảng.
- Các đường đọc ứng dụng mới, search, export, cache và API không phụ thuộc cột cũ.
- Dữ liệu encrypted có backup và restore thử thành công với key version cần thiết.
- Metrics decrypt failure, KMS timeout và query latency ở trong ngưỡng.

Đối soát sâu có thể rất tốn KMS calls; chia batch/canary và kiểm soát concurrency. Chỉ sampling không thể chứng minh toàn bộ record đúng nếu hợp đồng yêu cầu tuyệt đối; cần có phép kiểm tra đầy đủ và có kiểm soát tài nguyên.

### 17.5. Contract và xóa plaintext cũ

Sau khi chuyển reader/writer, không vội DROP cột plaintext chỉ vì ứng dụng đã chạy phiên bản mới. Cần:

- Thời gian quan sát và bằng chứng read/write mới ổn định.
- Rollback/forward fix khả thi nếu lỗi decryption hoặc KMS xảy ra.
- Kiểm kê tất cả log, export, snapshot và backup cũ còn chứa plaintext.
- Xác định policy retention/xóa dữ liệu và quyền truy cập bản backup cũ.
- Đánh giá việc DROP không đồng nghĩa đã xóa vật lý mọi byte cũ trên storage/WAL/snapshot ngay lập tức.

Nếu phạm vi threat model đòi xóa dấu vết plaintext lịch sử, phải có runbook retention, re-encryption/secure deletion và kiểm soát bản sao phù hợp hạ tầng; không chỉ chạy một câu ALTER TABLE.

## 18. Kiểm thử an toàn theo tình huống lỗi

Kiểm thử một kết nối thành công hoặc một lần encrypt/decrypt thành công không đủ. Một hệ thống bảo mật tốt phải **từ chối sai cấu hình** và phục hồi đúng khi thành phần phụ trợ gặp lỗi.

### 18.1. Test TLS/JDBC

| Tình huống | Kỳ vọng |
|---|---|
| Server có chứng chỉ CA tin cậy, đúng hostname | Kết nối verify-full thành công |
| Server có chứng chỉ hợp lệ nhưng hostname khác | Kết nối thất bại |
| Server có CA không nằm trong trust anchor được cấu hình | Kết nối thất bại |
| Chứng chỉ hết hạn/chưa hợp lệ | Kết nối thất bại |
| Server không hỗ trợ TLS theo policy bắt buộc | Không fallback non-TLS |
| Proxy terminate TLS và hop tiếp plaintext không được phép | Kiểm tra kiến trúc phát hiện và chặn |
| CA/server cert được rotate | Connection mới được xác minh, pool được thay phiên đúng |
| Một instance thiếu CA trust store | Readiness/check phải phát hiện, không đưa vào traffic |
| Client mTLS thiếu client certificate hợp lệ | Kết nối bị từ chối theo policy |
| Password đúng nhưng certificate server sai | Vẫn bị từ chối |

Có thể dựng môi trường tích hợp chuyên dụng với PostgreSQL có certificate test. Không dùng certificate production trong unit test hoặc commit private key test trùng với production.

### 18.2. Test dữ liệu at rest

- Ghi một hồ sơ chứa giá trị nhạy cảm đặc trưng rồi kiểm tra bảng thực sự chỉ lưu ciphertext ở những field đã thiết kế.
- Kiểm tra backup/export/log/cache có xuất hiện giá trị đó ở dạng plaintext ngoài những sink được phê duyệt không.
- Kiểm tra app không có quyền decrypt vẫn truy vấn được metadata cần thiết nhưng không lấy được plaintext.
- Hoán đổi ciphertext giữa tenant, customer ID hoặc field để chứng minh AAD check làm decrypt thất bại.
- Thay một byte ciphertext/tag để xác nhận không im lặng trả dữ liệu.
- Test key v1/v2 cùng hoạt động trong cửa sổ migration.
- Restore backup cũ với key version cũ rồi giải mã được record, theo quyền phù hợp.
- Cố ý ngắt KMS: API xử lý tạm lỗi có kiểm soát; không trả plaintext từ một kênh fallback không được bảo vệ.
- Theo dõi mức tiêu thụ bộ nhớ/latency khi mã hóa nhiều field/batch, không làm connection pool cạn do giữ transaction khi gọi KMS.
- Kiểm tra rotation/re-encrypt dưới cập nhật đồng thời, không ghi đè phiên bản mới bằng plaintext cũ.

### 18.3. Test lỗi cấp khóa và partial write

~~~text
T1: đọc hồ sơ version 7, giải mã với key-v1
T2: cập nhật hồ sơ version 8, ghi ciphertext mới
T1: re-encrypt bản đọc cũ thành key-v2
T1: UPDATE WHERE version=7 -> 0 rows
T1: đọc lại version 8, mã hóa đúng dữ liệu mới
~~~

Nếu job rotation chỉ UPDATE theo ID mà không có expectedVersion, nó có thể ghi đè thay đổi hợp lệ của T2. Đây là lỗi **đồng thời/persistence**, không phải lỗi thuật toán AES.

Các cột keyId/nonce/ciphertext phải commit nguyên tử. Nếu một thao tác mã hóa thành công nhưng UPDATE SQL thất bại, không báo record đã được lưu. Nếu COMMIT mất ACK, cần kiểm tra kết quả theo ID/version hoặc replay idempotent; không tạo thêm record nghiệp vụ mới.

### 18.4. Quan sát và metric, nhưng không log bí mật

| Metric hoặc sự kiện | Công dụng |
|---|---|
| TLS handshake failures theo loại | Phát hiện CA, cert, DNS và policy lỗi |
| Certificate expiry window | Chủ động rotate trước khi hết hạn |
| Current/legacy key usage | Biết có bao nhiêu record còn phụ thuộc key cũ |
| KMS latency và error rate | Đánh giá ảnh hưởng tới API p95/p99 |
| Decrypt/authentication-tag failures | Cảnh báo hỏng dữ liệu, sai key hoặc tampering |
| Re-encryption backlog và mismatch | Theo dõi trạng thái migration |
| Backup restore success với key cũ | Xác minh khả năng DR thực |
| Data leakage scan của logs/exports | Phát hiện plaintext ngoài phạm vi cho phép |
| IAM/key policy changes | Kiểm toán thay đổi quyền truy cập |
| DB query/connection pool latency | Tìm ảnh hưởng hiệu năng do encryption và routing |

Không dùng plaintext, key bytes, bản token nhạy cảm hoặc cả ciphertext làm label metric có cardinality cao. Khi cần điều tra, dùng correlation ID, key version, loại lỗi và metadata đã được phân loại an toàn.

## 19. Case study: hồ sơ khách hàng của Order Service

### 19.1. Bối cảnh

Hệ thống đặt hàng có:

- Java Spring Boot tiếp nhận thông tin khách hàng, địa chỉ giao hàng và đơn hàng.
- PostgreSQL primary + read replica.
- Redis phục vụ một số read projection.
- Backup dùng snapshot và WAL archive.
- Object storage giữ các report được phép xuất.
- KMS quản lý quyền dùng khóa ứng dụng.

Yêu cầu: giảm rủi ro dữ liệu nhạy cảm bị lộ nếu bản dump PostgreSQL hoặc tài khoản chỉ có quyền SELECT bị chiếm, nhưng vẫn giữ được khả năng tra cứu đơn theo orderId và tenantId.

### 19.2. Thiết kế đề xuất

~~~mermaid
flowchart TD
    A["API request HTTPS"] --> B["Spring Service"]
    B --> C["Authorization theo tenant"]
    C --> D["AES-GCM encrypt PII với AAD"]
    D --> E["JDBC TLS verify-full"]
    E --> F[("PostgreSQL ciphertext + metadata")]
    B --> K["KMS theo service identity"]
    F --> R[("Replica có encryption + TLS")]
    F --> Q["Encrypted backup + WAL archive"]
    B --> O["DTO có dữ liệu tối thiểu"]
    O --> X["Cache/log chỉ nội dung được phê duyệt"]
~~~

Các quyết định:

1. HTTPS từ client tới gateway và TLS/mTLS theo các hop nội bộ phù hợp.
2. PgJDBC verify-full khi kết nối đúng endpoint DB và CA.
3. Volume encryption cho primary, replica, snapshot và backup theo hạ tầng.
4. Các trường như địa chỉ/số liên hệ nhạy cảm được AES-GCM ở Java trước JDBC khi threat model yêu cầu.
5. Ciphertext có key version, nonce, tag và AAD gắn tenant/customer/field.
6. OrderId, tenantId và trạng thái nghiệp vụ không nhất thiết phải mã hóa field-level nếu cần truy vấn/index và đã có kiểm soát thích hợp.
7. Cache/read model không tự lưu plaintext PII ngoài trường được phép hiển thị.
8. KMS quyền decrypt chỉ cấp cho service/use case cần thiết, không cấp rộng cho report worker.
9. Job re-encrypt và restore backup được thử nghiệm trước khi rotate/xóa key version cũ.
10. Quyền SQL, RLS khi thích hợp, transaction và optimistic concurrency vẫn được bảo vệ như trước khi thêm mã hóa.

### 19.3. Những câu hỏi quyết định

| Tình huống | Không nên suy điều gì | Hành động đúng |
|---|---|---|
| TLS bật từ Java tới DB | Mọi hop đều TLS | Xác minh gateway, replica, broker, backup paths |
| Volume được mã hóa | DB user không đọc plaintext | Phân quyền và cân nhắc app-level field encryption |
| Tài khoản DB chỉ đọc lộ | Mọi PII đều lập tức lộ nếu field mã hóa và key tách biệt | Xác định phạm vi DB/metadata và kiểm tra key separation |
| KMS timeout | DB đã mất dữ liệu | Phân loại lỗi giải mã/khóa và fail-closed |
| Backup restore xong | Tất cả field giải mã được | Test key version, AAD và decryption sau restore |
| Cùng field bị encrypt lại cho cùng record | Ciphertext bắt buộc phải giống | AEAD randomized tạo nonce/ciphertext mới |
| App đổi customerId | Có thể giữ nguyên ciphertext | Cần re-encrypt nếu AAD gắn ID cũ |
| Đổi key alias | Toàn bộ backup đã an toàn dưới key mới | Kiểm chứng key wrapping và phụ thuộc dữ liệu lịch sử |

## 20. Bài tập tự kiểm tra

### A. TLS nhưng không kiểm tra hostname

Java dùng sslmode=require và kết nối thành công. DNS bị điều hướng tới máy chủ giả có chứng chỉ của attacker.

**Hỏi:** Vì sao mã hóa kênh chưa đủ và nên sửa như thế nào?

**Gợi ý:** Client chưa xác minh đầy đủ danh tính server. Dùng verify-full cùng trust anchor và hostname đúng; test chứng chỉ sai phải bị từ chối.

### B. Volume mã hóa nhưng database account bị lộ

Đĩa PostgreSQL được mã hóa bằng KMS của cloud. Một tài khoản ứng dụng có quyền SELECT toàn bảng bị lộ.

**Hỏi:** Disk encryption có ngăn đọc record khi DB đang chạy không?

**Gợi ý:** Không. DB đọc dữ liệu sau khi storage giải mã. Cần credential security, least privilege, query authorization, giám sát và có thể thêm field-level encryption với key separation.

### C. Dùng cùng IV cho mọi record

Một developer cố định nonce AES-GCM vì muốn kết quả encrypt có thể dự đoán và dễ test.

**Hỏi:** Điều gì nguy hiểm?

**Gợi ý:** Lặp nonce với cùng key làm hỏng tính an toàn của GCM. Dùng nonce mới mỗi operation và test qua round trip, không cố định IV sản xuất.

### D. Ciphertext hợp lệ bị chuyển sang tenant khác

Attacker copy cả ciphertext + tag từ tenant A sang record thuộc tenant B. Cả hai dùng cùng encryption key.

**Hỏi:** Cơ chế nào giúp phát hiện?

**Gợi ý:** AAD có tenantId, recordId, fieldName; khi decrypt bằng AAD B, tag không khớp. Vẫn phải có tenant-scoped SQL và authorization.

### E. Rotate current key rồi xóa key cũ

Mọi bản ghi mới dùng key-v2, nhưng 30% record và các backup tuần trước còn dùng key-v1. Kỹ sư xóa key-v1.

**Hỏi:** Hậu quả?

**Gợi ý:** Dữ liệu cũ không thể giải mã, restore có thể thất bại. Giữ khóa đọc cho phiên bản cũ đến khi hoàn tất migration/retention và test DR.

### F. Field encryption và tìm kiếm email

Email được AES-GCM randomized rồi lưu ciphertext. Team muốn tra cứu bằng cách encrypt email nhập vào rồi so ciphertext.

**Hỏi:** Vì sao không ổn?

**Gợi ý:** Nonce mới tạo ciphertext khác. Cần index/query strategy phù hợp như keyed blind index được đánh giá rò thông tin hoặc tra theo ID; không bỏ nonce ngẫu nhiên.

### G. Password của người dùng

Team cần xác thực mật khẩu đăng nhập, không cần lấy lại mật khẩu gốc, nhưng định lưu AES-GCM để “mã hóa mạnh”.

**Hỏi:** Có lựa chọn phù hợp hơn không?

**Gợi ý:** Password hashing chuyên dụng như Argon2id/scrypt/bcrypt với salt và tham số cost phù hợp; không lưu mật khẩu ở dạng có thể đảo ngược nếu không cần.

### H. Backup có thể khôi phục nhưng không thể đọc

Một database restore được về staging từ snapshot cũ, nhưng service không còn quyền hoặc key version để giải mã các record lịch sử.

**Hỏi:** Restore có được tính là thành công hoàn chỉnh không?

**Gợi ý:** Chưa. Kiểm tra key lifecycle, KMS policy và decrypt sample/invariants sau restore.

### I. Chuyển plaintext sang ciphertext

Backfill đọc số điện thoại từ version 3, writer đồng thời cập nhật số điện thoại sang version 4; backfill vẫn UPDATE ciphertext từ version 3.

**Hỏi:** Làm sao tránh ghi đè dữ liệu mới?

**Gợi ý:** UPDATE theo expectedVersion hoặc đối chiếu source hiện hành, retry theo bản mới và bảo đảm writer trong rollout tuân thủ contract.

### J. TLS chỉ ở gateway

Trình duyệt dùng HTTPS nhưng gateway gọi Java bằng HTTP qua mạng nội bộ; Java gọi PostgreSQL bằng TLS.

**Hỏi:** Có thể tuyên bố dữ liệu được mã hóa trên toàn bộ đường truyền không?

**Gợi ý:** Không. Phải đánh giá hop gateway–Java, áp dụng TLS/mTLS theo boundary và xác định nơi terminate plaintext.

## 21. Checklist khi thiết kế mã hóa persistence

- [ ] Có bản đồ data flow, classification và threat model cho từng field/hop.
- [ ] Biết nơi plaintext xuất hiện trong Java, DB, proxy, cache, log và backup.
- [ ] JDBC PostgreSQL dùng TLS theo policy, xác minh CA và hostname khi cần bảo vệ chống server giả.
- [ ] Không tắt certificate validation để khắc phục lỗi kết nối; có test fail-closed.
- [ ] Kiểm tra tất cả hop liên quan, không chỉ API ingress hoặc JDBC.
- [ ] Server/CA/client cert có người quản lý, lifecycle rotation và cảnh báo hết hạn.
- [ ] Connection pool được kiểm tra khi thay cert/CA; không hardcode secret trong source.
- [ ] Primary, replica, data files, WAL, temp, backup, snapshot và exports có chính sách encryption at rest rõ.
- [ ] Đã xác nhận khả năng/giới hạn mã hóa của đúng DB product/version đang dùng.
- [ ] Không nhầm volume/TDE encryption với việc DB user không thể SELECT plaintext.
- [ ] Nếu dùng field-level encryption, chọn AEAD được hỗ trợ; không tái sử dụng nonce cùng key.
- [ ] Ciphertext và keyId, nonce, tag, format version được lưu/đọc cùng contract.
- [ ] AAD được encode không mơ hồ, gắn tenant/record/field khi cần.
- [ ] Mã hóa field không phá query/index/UNIQUE hoặc đã có thay thế được kiểm chứng.
- [ ] Các khóa encryption, HMAC/index và backup có phân quyền, phạm vi và lifecycle phù hợp.
- [ ] KMS/HSM có policy least privilege, audit, rotation và khả năng DR.
- [ ] Không xóa key cũ khi ciphertext hoặc backup còn phụ thuộc key ấy.
- [ ] Migration plaintext → ciphertext có writer compatibility, backfill idempotent và đối soát.
- [ ] Data retention, log/trace redaction và cache scope không làm lộ plaintext qua đường phụ.
- [ ] Password được lưu bằng password hashing thích hợp, không dùng AES đảo ngược nếu không cần.
- [ ] Có integration test certificate/hostname sai, AEAD tag sai, KMS unavailable và backup restore.
- [ ] Authorization, tenant isolation, parameterized SQL, transaction và idempotency vẫn được bảo vệ độc lập.
- [ ] Có metrics về TLS handshake, key usage, decryption failures, rotation progress và restore success.

## 22. Kết luận

**Mã hóa đường truyền** bảo vệ các byte khi đi trên từng kết nối; **mã hóa dữ liệu được lưu** bảo vệ bản ghi trên phương tiện lưu trữ theo phạm vi và ranh giới khóa đã thiết kế. Chúng không thay thế nhau và cũng không thay authentication, authorization hoặc tính đúng đắn của persistence.

Đối với Java và PostgreSQL, một kiến trúc hợp lý thường bắt đầu bằng TLS được xác minh đầy đủ, mã hóa storage/backup, phân quyền tối thiểu, secret management và kiểm thử phục hồi. Chỉ những trường có threat model phù hợp mới cần thêm application-level encryption, với AEAD, nonce, AAD, version key và chiến lược truy vấn/rotation rõ ràng.

Dấu hiệu của một thiết kế an toàn không phải chỉ là “đã bật encryption”, mà là **người vận hành có thể chứng minh dữ liệu được bảo vệ ở các hop và bản lưu cần thiết, hệ thống từ chối cấu hình yếu, khóa có vòng đời kiểm soát và dữ liệu vẫn khôi phục được khi xảy ra sự cố**.

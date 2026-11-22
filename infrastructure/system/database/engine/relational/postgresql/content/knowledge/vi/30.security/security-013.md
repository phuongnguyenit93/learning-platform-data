# Mã hóa, che dữ liệu và giới hạn bảo vệ của từng lớp trong PostgreSQL

## 1. Tình huống: dữ liệu đã mã hóa nhưng vẫn bị lộ

Một hệ thống lưu thông tin khách hàng trong PostgreSQL:

```text
customer_id | full_name | email                | phone
------------+-----------+----------------------+--------------
101         | An        | an@example.invalid   | 0900000001
102         | Bình      | binh@example.invalid | 0900000002
```

Nhóm vận hành bật **mã hóa ổ đĩa**, thiết lập **TLS** cho kết nối ứng dụng và tạo một view hiển thị email dưới dạng `a***@example.invalid` cho nhân viên hỗ trợ. Họ kết luận: “Thông tin cá nhân đã được bảo vệ”.

Nhưng những tình huống sau vẫn có thể làm lộ dữ liệu:

- Tài khoản ứng dụng có quyền `SELECT email FROM customers` trực tiếp, không đi qua view che dữ liệu.
- DBA hoặc hệ điều hành đang chạy PostgreSQL có thể đọc bản rõ sau khi hệ thống giải mã lớp ổ đĩa.
- Ứng dụng ghi email, số điện thoại hoặc khóa giải mã vào log.
- Backup, file export, cache, hệ thống phân tích hoặc bản sao phục vụ tìm kiếm không áp cùng chính sách.
- Một API `SECURITY DEFINER` trả dữ liệu chưa che cho role không phù hợp.
- Khóa mã hóa nằm cùng database, cùng backup và cùng phạm vi quyền với ciphertext.
- Cơ chế “che” chỉ thay đổi chuỗi hiển thị, nhưng người dùng vẫn được quyền lọc, sắp xếp hoặc suy ra dữ liệu gốc bằng truy vấn khác.

Đây là lý do bảo vệ dữ liệu phải được thiết kế theo **nhiều lớp, mỗi lớp đối phó một nhóm mối đe dọa**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **encryption**, **hashing**, **masking**, **tokenization**, **anonymization** và **access control**.
2. Lập mô hình đe dọa cho dữ liệu PostgreSQL theo đường truyền, thiết bị lưu trữ, database, ứng dụng, bản sao và con người.
3. Thiết lập tư duy đúng về TLS, xác minh danh tính server và giới hạn của mã hóa trong truyền tải.
4. Giải thích phạm vi bảo vệ của disk/volume encryption, backup encryption và các giải pháp at-rest khác.
5. Sử dụng `pgcrypto` ở mức minh họa để mã hóa/giải mã trường dữ liệu, đồng thời chỉ ra vì sao DB-side encryption không che bản rõ trước chính database server.
6. Hiểu application-layer encryption, envelope encryption, KMS/HSM, key rotation và phân quyền dùng khóa.
7. Phân biệt mã hóa xác suất với mã hóa xác định; hiểu rủi ro dò tìm, đếm tần suất và xây “blind index” có kiểm soát.
8. Che trường nhạy cảm qua SQL views, phân quyền cột và các hàm hiển thị.
9. Phân biệt masking với RLS; giải thích vì sao mỗi cơ chế chỉ giải quyết một chiều truy cập.
10. Nhận diện những rò rỉ qua logs, `RETURNING`, `COPY`, backups, WAL, replication, statistics, search indexes và BI exports.
11. Thiết kế lab phân tầng và các phép thử xác nhận vai trò nào nhìn thấy dữ liệu gì.
12. Chọn đúng lớp bảo vệ cho từng mối đe dọa mà không đánh đồng “đã mã hóa” với “đã an toàn”.

---

## 2. Phân loại dữ liệu trước khi chọn công cụ

Không phải dữ liệu nào cũng cần cùng chính sách.

| Nhóm | Ví dụ | Rủi ro khi lộ | Hướng bảo vệ |
|---|---|---|---|
| Công khai | Tên sản phẩm được công bố | Thấp, tùy tính chính xác | Integrity, availability, backup |
| Nội bộ | Mức chiết khấu, lịch giao hàng | Lộ bí mật kinh doanh | Roles, row/column permissions, TLS, encryption |
| Thông tin cá nhân | Email, số điện thoại, địa chỉ | Xâm phạm quyền riêng tư | Tối thiểu hóa, masking, encryption, access control |
| Dữ liệu nhạy cảm cao | Số giấy tờ, tài khoản ngân hàng | Gian lận, rủi ro pháp lý | Field encryption, key separation, audit, retention |
| Mật khẩu người dùng | Password đăng nhập | Chiếm tài khoản | **Password hashing** chuyên dụng, không lưu plaintext |
| Credentials/hệ thống | API key, refresh token | Truy cập trái phép hệ khác | Secret manager, hạn quyền, rotation, kiểm soát log |
| Khóa mã hóa | DEK/KEK, private keys | Mất tính bí mật của ciphertext | KMS/HSM, không để cùng phạm vi với dữ liệu |

### 2.1. Xác định mục đích sử dụng trước

Cùng một email có thể cần:

- Gửi thông báo.
- Đăng nhập.
- Tra cứu chính xác.
- Hiển thị dạng che cho nhân viên hỗ trợ.
- Phân tích số khách theo tên miền.
- Xuất dữ liệu theo quyền chủ thể dữ liệu.

Không có một phương thức mã hóa đơn nhất tự hỗ trợ tất cả các mục đích mà vẫn bảo mật tối ưu. Cần quyết định **trường nào được giải mã, bởi ai và tại thời điểm nào**.

### 2.2. Tối thiểu hóa dữ liệu thường hiệu quả hơn mã hóa mọi thứ

Nếu nghiệp vụ không cần lưu số giấy tờ, **đừng lưu**. Nếu chỉ cần bốn chữ số cuối, cân nhắc chỉ lưu bốn chữ số ấy theo chính sách và pháp luật áp dụng.

Dữ liệu không thu thập thì không cần bảo vệ khỏi việc rò rỉ trong database của bạn.

## 3. Những thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Có thể lấy lại giá trị gốc? | Bảo vệ chủ yếu |
|---|---|---|---|
| **Encryption** | Dùng khóa mã hóa bản rõ thành ciphertext | Có, nếu có khóa/quyền | Confidentiality trước đối tượng không có khóa |
| **Hashing** | Biến dữ liệu thành digest một chiều | Không giải mã; có thể đoán/brute-force nếu đầu vào yếu | So sánh, integrity hoặc thành phần xác minh |
| **Password hashing** | Hash có salt và chi phí tính toán phù hợp | Không giải mã | Bảo vệ mật khẩu đã lưu trước tấn công offline |
| **Masking** | Thay/ẩn một phần dữ liệu khi hiển thị hoặc tạo bản sao | Có thể vẫn tồn tại bản gốc ở nơi khác | Giảm mức tiết lộ tới một nhóm người xem |
| **Tokenization** | Thay giá trị bằng token liên kết với giá trị thật qua dịch vụ/kho ánh xạ | Có nếu hệ thống detokenize được | Hạn chế lan truyền dữ liệu gốc |
| **Pseudonymization** | Thay identifier bằng một mã liên kết | Có thể liên kết ngược | Giảm lộ trực tiếp, chưa chắc ẩn danh |
| **Anonymization** | Loại khả năng liên hệ lại một cá nhân trong threat model phù hợp | Mục tiêu là không thể nhận diện lại hợp lý | Bảo vệ riêng tư, yêu cầu đánh giá tái nhận diện |
| **Authorization** | Quyết định ai được phép làm gì | Không liên quan trực tiếp | Ngăn truy cập trái phép |

### 3.1. Masking không phải encryption

```text
Bản gốc:   an@example.invalid
Bản che:   a***@example.invalid
Bản mã:    <bytea hoặc ciphertext không đọc được>
```

Chuỗi đã che vẫn có thể làm lộ chữ cái đầu và tên miền; nó cũng không bảo đảm chuỗi gốc không còn ở bảng, log hoặc memory.

### 3.2. Hash không phải encryption

```sql
SELECT encode(digest('an@example.invalid', 'sha256'), 'hex');
```

Nếu dùng `pgcrypto`, câu trên trả một digest. Không có “decrypt SHA-256”. Tuy nhiên email có entropy thấp và có thể đoán từ danh sách email nên **hash SHA-256 thuần không biến email thành dữ liệu ẩn danh an toàn**.

### 3.3. Access control không phải encryption

Role có quyền `SELECT` không cần khóa để đọc cột plaintext. Một ciphertext ở database có thể che giá trị với role không có khóa, nhưng role ấy vẫn có thể thao tác những metadata mà quyền SQL cho phép.

### 3.4. Confidentiality khác integrity và availability

- **Confidentiality:** người không có quyền không đọc được.
- **Integrity:** dữ liệu không bị sửa sai mà không phát hiện/ngăn chặn.
- **Availability:** dữ liệu và dịch vụ vẫn hoạt động khi cần.

Mã hóa chỉ giải quyết một phần confidentiality; nhiều chế độ mã hóa cần xác thực tính toàn vẹn riêng. Nó không thay backups, kiểm tra constraints hay ứng phó ransomware.

## 4. Xây threat model trước khi chọn lớp mã hóa

Một threat model hữu ích trả lời:

1. Tài sản nào cần bảo vệ?
2. Ai có thể tấn công/đọc trộm: người dùng, role ứng dụng, DBA, nhân viên hạ tầng, nhà cung cấp cloud, kẻ lấy cắp đĩa, kẻ lấy cắp backup?
3. Kẻ tấn công kiểm soát lớp nào: mạng, SQL session, VM, hệ điều hành, disk snapshot, KMS, ứng dụng hay log?
4. Khóa nằm ở đâu, ai có quyền dùng, ai có thể tạo phiên giải mã?
5. Dữ liệu hiện diện ở những đâu: bảng chính, WAL, backup, replica, cache, exports, queue, metrics?
6. Mục tiêu là không đọc được bản rõ hay chỉ không hiển thị đầy đủ trong một giao diện?
7. Cần khả năng tìm kiếm, lọc, join hoặc phân tích trên trường được bảo vệ không?
8. Cần phục hồi và rotation trong trường hợp lộ khóa như thế nào?

### 4.1. Ma trận threat model rút gọn

| Đối tượng tấn công | TLS | Disk encryption | DB-side field encryption | App-side field encryption | Masked view/RLS |
|---|---|---|---|---|---|
| Nghe lén mạng giữa app và DB | Bảo vệ nếu xác minh đúng | Không | Chỉ một số payload | Bảo vệ payload đã mã hóa | Không |
| Lấy trộm ổ đĩa đã tắt | Không | Có nếu cấu hình/khóa đúng | Có với field được mã hóa | Có | Không |
| Có backup plaintext của PostgreSQL | Không | Không bảo vệ file export đã giải mã | Che các trường ciphertext nếu khóa tách riêng | Che các trường ciphertext nếu khóa tách riêng | Không |
| SQL role chỉ được xem view đã che | Không giải quyết trực tiếp | Không | Phụ thuộc quyền giải mã | Bản gốc ở app, DB có thể chỉ thấy ciphertext | Có tác dụng ở SQL boundary |
| SQL injection vào role ứng dụng có SELECT full | Không | Không | Không nếu role cũng gọi được decrypt/đọc khóa | Có thể hạn chế plaintext trong DB | Không nếu role được đọc bảng gốc |
| DBA/superuser có quyền đọc server | Không | Không | Có thể thấy plaintext khi giải mã ở DB; key tùy nơi | Không tự có app key, nhưng metadata/backup vẫn lộ | Thường vượt qua SQL masking/RLS |
| Ứng dụng bị chiếm và có quyền gọi KMS | Không | Không | Không bảo đảm | Có thể bị giải mã qua quyền ứng dụng | Không bảo đảm |
| Lộ nhật ký chứa plaintext | Không | Không | Không | Không, nếu app log plaintext | Không nếu log ngoài view |

**Đọc bảng như phạm vi điển hình, không phải chứng nhận bảo mật.** Hiệu quả phụ thuộc cấu hình, quyền, khóa, luồng dữ liệu và khả năng của đối tượng tấn công.

## 5. Defense in depth: nhiều lớp nhưng mỗi lớp có giới hạn

Một kiến trúc có thể gồm:

```text
Người dùng
   |
   | HTTPS + xác thực + phân quyền API
   v
Ứng dụng
   |
   | TLS tới PostgreSQL
   |      +-- Có thể mã hóa trường bằng app key trước khi gửi
   v
PostgreSQL
   |
   | SQL roles / GRANT / RLS / views / audit
   |      +-- Có thể dùng pgcrypto theo yêu cầu
   v
File dữ liệu + WAL + replicas
   |
   | Volume/disk encryption, khóa hạ tầng
   v
Backups / snapshots / exports
   |
   | Backup encryption và phân quyền storage riêng
   v
Lưu trữ phục hồi
```

Song song:

```text
KMS / HSM / secret manager
   |
   +-- quản lý key policies
   +-- cấp phép encrypt/decrypt theo identity
   +-- rotation / disable / audit
```

Không nên giải thích “đã có 5 lớp” thành “không còn đường rò rỉ”. Nếu một tài khoản ứng dụng có cả quyền đọc mọi hàng lẫn quyền giải mã mọi trường, một SQL injection chiếm được quyền ấy có thể vượt qua nhiều lớp cùng lúc.

## 6. Mã hóa dữ liệu trên đường truyền: TLS

Khi ứng dụng nói chuyện với PostgreSQL qua mạng, TLS giúp:

- Giảm nguy cơ nghe lén thông tin xác thực, câu SQL, giá trị bind và kết quả.
- Bảo vệ tính toàn vẹn của luồng truyền theo giao thức TLS.
- Xác minh server khi client kiểm tra chứng chỉ/hostname đúng.

### 6.1. Một chuỗi kết nối an toàn hơn

Ví dụ với libpq/psql:

```text
host=db.example.invalid
port=5432
dbname=appdb
user=app_reader
sslmode=verify-full
sslrootcert=/path/to/trusted-root-ca.crt
```

Đây là **mẫu cấu hình**, không phải server thực và không chứa mật khẩu.

### 6.2. sslmode không tương đương nhau

| Chế độ libpq | Ý nghĩa bảo mật khái quát |
|---|---|
| `disable` | Không dùng TLS |
| `prefer` | Ưu tiên TLS nhưng có thể fallback |
| `require` | Yêu cầu kênh TLS, nhưng không luôn có mức xác minh hostname mong muốn |
| `verify-ca` | Kiểm tra chuỗi chứng chỉ với CA tin cậy |
| `verify-full` | Kiểm tra chứng chỉ và tên máy chủ theo quy tắc kết nối |

**Ưu tiên `verify-full`** khi có hạ tầng chứng chỉ tin cậy. `require` không nên được coi mặc nhiên tương đương xác minh danh tính server đầy đủ; chi tiết còn tùy trust store và tham số của client.

### 6.3. Cấu hình phía PostgreSQL

Phía server cần bật TLS và cấu hình chứng chỉ/khóa phù hợp:

```conf
# Mẫu postgresql.conf (không phải toàn bộ cấu hình TLS):
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
```

Trong `pg_hba.conf`, có thể dùng những luật `hostssl` để chỉ cho phép kết nối TCP qua TLS đối với các role/địa chỉ đã chỉ định:

```conf
# Mẫu minh họa, thay dải IP và cơ chế auth cho môi trường:
hostssl appdb app_reader 10.20.0.0/16 scram-sha-256
```

Phải quản lý thứ tự rules, mạng thực tế, xác thực và quyền file private key đúng theo triển khai.

### 6.4. Kiểm tra kết nối hiện tại

Một truy vấn có thể đọc trạng thái TLS của backend đang chạy:

```sql
SELECT
    ssl,
    version,
    cipher,
    bits
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
```

Nếu `ssl=true`, connection backend ấy dùng TLS. Điều này **không chứng minh client đã xác minh hostname đúng**; đó là một cấu hình client-side cần kiểm tra riêng.

### 6.5. TLS bảo vệ được đến đâu?

TLS không bảo vệ:

- Dữ liệu sau khi database giải mã và trả cho ứng dụng.
- Credentials trong application logs.
- Dữ liệu ở RAM/server sau khi kết nối TLS kết thúc.
- Đĩa, backup hoặc file xuất không được mã hóa.
- Các truy vấn được gửi bởi role đã xác thực nhưng bị lạm dụng.

Không dùng TLS làm lý do bỏ qua mã hóa và phân quyền ở các lớp còn lại.

## 7. Mã hóa at rest: ổ đĩa, volume và storage

At-rest encryption thường được triển khai ở một hoặc nhiều tầng:

- Full disk encryption.
- Volume/block-device encryption.
- Encrypted cloud disks/snapshots.
- Encrypted backup object storage.
- Một số sản phẩm/dịch vụ cung cấp cơ chế mã hóa dữ liệu database chuyên biệt tùy phiên bản.

### 7.1. Nó bảo vệ tốt trước mối đe dọa nào?

Ví dụ kẻ tấn công lấy được **ổ đĩa đã tháo khỏi máy và không có key**. Disk encryption được cấu hình đúng có thể ngăn họ đọc file PostgreSQL trực tiếp.

### 7.2. Nó không bảo vệ trước mối đe dọa nào?

Khi hệ thống đang chạy và filesystem đã được mở khóa:

- PostgreSQL truy cập các page dữ liệu theo cách bình thường.
- Role SQL được cấp quyền có thể đọc plaintext của các cột không mã hóa ở lớp cao hơn.
- Người có quyền kiểm soát hệ điều hành/database có thể truy cập vùng đã được mở khóa theo năng lực của họ.

Đó là **mã hóa storage**, không phải authorization cho mỗi SQL query.

### 7.3. Có nên nói PostgreSQL luôn có TDE built-in?

Không khẳng định như vậy. Khả năng mã hóa dữ liệu ở storage/database layer phụ thuộc **phiên bản PostgreSQL, phân phối, nhà cung cấp managed service, extension và cấu hình hạ tầng**. Cần xác minh chính xác giải pháp đang triển khai, cách quản lý key, WAL/temp files, backups và replication.

### 7.4. File nào cũng cần xét?

PostgreSQL dùng nhiều loại dữ liệu vật lý:

```text
Base table/index files
WAL segments
Temporary files / spill
Physical backups / snapshots
Archive WAL
Replication copies
Filesystem copies, crash dumps
```

Không chỉ mã hóa `base/` rồi bỏ qua WAL hoặc backup. Một giá trị plaintext từng được INSERT có thể tồn tại trong nhiều nơi theo ngữ nghĩa lưu trữ và vận hành.

## 8. Backup encryption khác disk encryption

Giả sử volume production được mã hóa, nhưng nightly job chạy:

```text
pg_dump -> backup.sql -> upload vào bucket
```

File `backup.sql` có thể chứa **plaintext** của cột email/phone. Disk encryption của production không tự động mã hóa file dump ngoài máy.

### 8.1. Backup cần các kiểm soát riêng

- Mã hóa backup archive/object.
- Khóa backup tách quyền khỏi người đọc database thông thường.
- IAM/storage ACL chặt.
- Retention và lifecycle.
- Kiểm soát nơi sao chép backup.
- Audit truy cập và tải xuống.
- Khả năng kiểm tra restore định kỳ.
- Quy trình xóa bản sao quá hạn.

### 8.2. Mã hóa backup vẫn có giới hạn

Một người có quyền **decrypt key và download backup** có thể phục hồi toàn bộ. Cần phân tách quyền quản lý khóa, tải file và thực thi restore theo nhu cầu vận hành.

### 8.3. Đừng quên logical exports

Không chỉ `pg_dump`:

- `COPY TO`.
- CSV exports.
- BI tools.
- Reports gửi email.
- ETL pipelines.
- Search indexes.
- Data warehouses.
- Developer database clones.

Mỗi bản sao tạo một **trust boundary** mới.

## 9. Mã hóa ở cấp trường (field/column encryption)

Giả sử chỉ trường `national_identifier` cần độ bảo mật cao hơn những cột khác.

Thiết kế có thể lưu:

```text
customer_id       bigint
display_name      text
identifier_cipher bytea
key_version       text
```

Ưu điểm:

- Kẻ lấy file dữ liệu hoặc chỉ có SELECT ciphertext không thể đọc identifier nếu không có khóa.
- Có thể bảo vệ khác nhau giữa cột nhạy cảm và cột công khai.
- Có thể phân quyền khóa giải mã cho ít dịch vụ hơn.

Giới hạn:

- Không thể dùng `ILIKE` hay B-tree equality trên bản rõ nếu chỉ còn ciphertext ngẫu nhiên.
- Phải quản lý khóa và rotation.
- Có thể phát sinh plaintext khi decrypt và qua logs/app.
- Metadata như customer_id, chiều dài ciphertext, tần suất truy cập vẫn có thể bị lộ.
- Kết quả giải mã có thể nằm trong RAM và có vòng đời cần kiểm soát.

### 9.1. Mã hóa field không tự thay thế column privileges

Một role không cần decrypt key vẫn có thể đọc ciphertext nếu được quyền SELECT. Điều đó có thể chấp nhận được hoặc không tùy threat model. Cần phân quyền cột/tables phù hợp.

### 9.2. Mã hóa field không tự bảo vệ khỏi sửa/xóa ciphertext

Dùng cơ chế mã hóa có xác thực/tính toàn vẹn phù hợp và database constraints. Kẻ có quyền UPDATE vẫn có thể xóa hoặc thay ciphertext; xác thực giúp phát hiện một số thay đổi, không nhất thiết ngăn được hành vi phá dữ liệu.

## 10. pgcrypto: mã hóa ngay trong PostgreSQL

PostgreSQL có extension `pgcrypto` với nhiều nhóm hàm:

- `pgp_sym_encrypt` và `pgp_sym_decrypt`: xử lý dữ liệu theo OpenPGP với passphrase.
- `pgp_pub_encrypt` và `pgp_pub_decrypt`: dùng khóa công khai/bí mật theo định dạng hỗ trợ.
- `digest` và `hmac`: hash/MAC.
- `crypt` và `gen_salt`: password hashing theo những thuật toán được extension hỗ trợ.
- Các hàm mã hóa mức thấp: cần hiểu mode, IV/nonce, authentication, không nên tự lắp giao thức thiếu an toàn.

### 10.1. Kiểm tra extension

Trong database học tập, nếu có quyền và server được build hỗ trợ:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

Mức quyền cài extension và các thuật toán khả dụng phụ thuộc phiên bản PostgreSQL, build OpenSSL, cấu hình và chính sách môi trường.

### 10.2. pgcrypto xử lý dữ liệu ở đâu?

Khi gửi:

```sql
SELECT pgp_sym_encrypt(p_plaintext, p_passphrase);
```

plaintext và passphrase **được truyền đến PostgreSQL** và xử lý **bên trong server**.

Vì vậy pgcrypto phù hợp cho nhiều bài toán field encryption, nhưng **không đáp ứng yêu cầu “DB server tuyệt đối không bao giờ nhìn thấy bản rõ”**.

### 10.3. Khóa không nên nằm trong câu SQL hard-coded

Không viết code production kiểu:

```sql
-- Ví dụ KHÔNG AN TOÀN trong production:
SELECT pgp_sym_encrypt(
    'identifier-sensitive',
    'HARDCODED-SECRET-KEY'
);
```

SQL text có thể xuất hiện trong lịch sử client, logs, tracing, audit events hoặc bản sao mã nguồn. Phần thực hành sau chỉ dùng **chuỗi giả** và cố ý nêu rõ rủi ro này.

## 11. Lab: schema minh họa cho che và mã hóa

**Mọi dữ liệu bên dưới đều là giả và không đại diện cá nhân có thật.** Chỉ chạy trên database thực hành.

```sql
CREATE SCHEMA IF NOT EXISTS sec390;

CREATE TABLE sec390.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    full_name text NOT NULL,
    email text NOT NULL,
    phone text,
    national_identifier text,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO sec390.customers(
    tenant_id,
    full_name,
    email,
    phone,
    national_identifier
)
VALUES
    (7, 'An', 'an@example.invalid', '000-000-0001', 'FAKE-ID-001'),
    (7, 'Bình', 'binh@example.invalid', '000-000-0002', 'FAKE-ID-002'),
    (8, 'Chi', 'chi@example.invalid', '000-000-0003', 'FAKE-ID-003');
```

Vì đây là bảng plaintext demo, người có quyền SELECT toàn bảng có thể thấy các trường nhạy cảm. Chúng ta sẽ dùng nó để học **masking và quyền**, không xem nó là mô hình lưu PII production.

### 11.1. Chia trách nhiệm theo trường

- `customer_id`: khóa kỹ thuật.
- `tenant_id`: ranh giới dữ liệu tổ chức.
- `full_name`: hiển thị tùy quyền.
- `email/phone`: thông tin liên hệ.
- `national_identifier`: trường nhạy cảm cao, không nên xuất rộng.
- `created_at`: metadata có thể có yêu cầu retention.

### 11.2. Không dùng dữ liệu thật để thử mã hóa

Môi trường phát triển/lab có thể bị chia sẻ hoặc log mạnh hơn production. Tạo dữ liệu giả, không copy PII thật vào fixture để “kiểm thử gần thực tế”.

## 12. pgp_sym_encrypt/pgp_sym_decrypt: minh họa có kiểm soát

Tạo bảng ciphertext riêng:

```sql
CREATE TABLE sec390.encrypted_notes (
    note_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES sec390.customers(customer_id),
    encrypted_note bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Một pattern dành cho driver hỗ trợ PostgreSQL bind parameters:

```sql
INSERT INTO sec390.encrypted_notes(
    customer_id,
    encrypted_note
)
VALUES (
    $1::bigint,
    pgp_sym_encrypt(
        $2::text,
        $3::text,
        'cipher-algo=aes256'
    )
)
RETURNING note_id;
```

Trong câu lệnh ở trên:

- `$1` = customer_id.
- `$2` = nội dung ghi chú **giả**.
- `$3` = passphrase lấy từ secret manager thông qua ứng dụng được phép.
- `encrypted_note` lưu ciphertext dạng `bytea`.

**Lưu ý:** đoạn SQL có `$1/$2/$3` minh họa query có bind parameters do application/driver cung cấp, không phải câu SQL tự chạy trực tiếp trong psql khi chưa chuẩn bị tham số.

### 12.1. Xem ciphertext

```sql
SELECT
    note_id,
    customer_id,
    octet_length(encrypted_note) AS encrypted_bytes,
    created_at
FROM sec390.encrypted_notes
ORDER BY note_id;
```

Không cần SELECT raw ciphertext trong mọi API, dù bản mã không phải plaintext.

### 12.2. Giải mã với passphrase được cung cấp có quyền

```sql
SELECT
    pgp_sym_decrypt(
        encrypted_note,
        $1::text
    ) AS note_plaintext
FROM sec390.encrypted_notes
WHERE note_id = $2::bigint;
```

Chỉ nên thực thi trong luồng ứng dụng đã xác thực và ủy quyền. Sau khi giải mã, kết quả là **plaintext** và có thể đi vào app memory, telemetry hoặc response.

### 12.3. Khóa sai không được “trả dữ liệu gần đúng”

Giải mã ciphertext bằng passphrase/khóa sai có thể báo lỗi. Không viết logic production bắt lỗi rồi tự gửi ciphertext hoặc giá trị nhạy cảm vào exception message.

### 12.4. Không nhầm passphrase với key management tốt

Một passphrase lưu trong cấu hình, source code hoặc một bảng cạnh ciphertext có thể triệt tiêu lợi ích bảo mật. Giải pháp an toàn cần quản lý vòng đời khóa, quyền, backup và rotation.

## 13. Ví dụ trực tiếp dành riêng cho lab

Nếu muốn quan sát một phép mã hóa/giải mã mà không viết app, dùng **chuỗi hoàn toàn giả** và **passphrase vô giá trị**:

```sql
-- CHỈ LAB: passphrase literal dễ vào history/log!
WITH encrypted AS (
    SELECT pgp_sym_encrypt(
        'TRAINING-ONLY-NOT-PII',
        'LAB-KEY-DO-NOT-REUSE',
        'cipher-algo=aes256'
    ) AS ciphertext
)
SELECT
    octet_length(ciphertext) AS ciphertext_bytes,
    pgp_sym_decrypt(
        ciphertext,
        'LAB-KEY-DO-NOT-REUSE'
    ) AS restored_text
FROM encrypted;
```

Kết quả `restored_text` dự kiến:

```text
TRAINING-ONLY-NOT-PII
```

### 13.1. Những điều ví dụ không chứng minh

- Không chứng minh hệ thống đã quản lý khóa an toàn.
- Không chứng minh dữ liệu không xuất hiện trong logs.
- Không chứng minh mã hóa bảo vệ trước database superuser.
- Không chứng minh ciphertext có thể tìm kiếm bằng `LIKE`.
- Không chứng minh đã có ứng dụng encryption-at-rest production.

Nó chỉ cho thấy **một vòng encrypt/decrypt** khi có đúng passphrase.

## 14. DB-side encryption bảo vệ khỏi ai?

Giả sử cột `identifier_cipher` được mã hóa bởi `pgcrypto`.

| Vai trò | Biết passphrase? | Đọc ciphertext? | Đọc plaintext? |
|---|---|---|---|
| Role chỉ có SELECT ciphertext | Không | Có nếu được GRANT | Không bằng hàm decrypt thiếu key |
| Dịch vụ được quyền gọi decrypt với key | Có | Có thể | Có |
| SQL injection chạy dưới role có sẵn key trong session | Có thể | Có | Có thể |
| DBA kiểm soát server và theo dõi quá trình giải mã | Có thể quan sát plaintext/keys khi chúng đến server | Có | Có nguy cơ |
| Người có backup chỉ chứa ciphertext, không có key | Không | Có | Khó nếu thuật toán/key đúng |

### 14.1. Key separation là điều kiện quan trọng

Một database backup chứa cả:

```text
encrypted_identifier bytea
encryption_key text
```

có thể để người lấy backup đọc được mọi thứ bằng cách giải mã.

Phải tách key khỏi dữ liệu và khỏi cùng phạm vi backup/permission khi threat model đòi hỏi.

### 14.2. Mã hóa trong PostgreSQL không bảo vệ mọi thao tác SQL

Ngay cả khi cột PII được mã hóa, role có quyền DELETE có thể phá dữ liệu; role có quyền UPDATE có thể thay ciphertext. Encryption không phải substitute cho `GRANT`, RLS, constraints, WAL backup và phục hồi.

## 15. Application-layer encryption: PostgreSQL chỉ nhận ciphertext

Một giải pháp cần chống việc **DB server nhìn thấy bản rõ** có thể dùng mã hóa ở ứng dụng.

Sơ đồ:

```text
Plaintext (trong service có quyền)
       |
       v
App sử dụng vetted crypto library + key từ KMS
       |
       v
Ciphertext + nonce + auth tag + key version
       |
       | TLS
       v
PostgreSQL: lưu bytea/metadata, không nhận plaintext trường đó
       |
       v
Ứng dụng được ủy quyền đọc ciphertext
       |
       v
App lấy quyền giải mã qua KMS/keystore
       |
       v
Plaintext chỉ ở service cần sử dụng
```

### 15.1. Chọn authenticated encryption

Thường cần một chuẩn **AEAD (Authenticated Encryption with Associated Data)** như AES-GCM hoặc ChaCha20-Poly1305 thông qua thư viện mật mã đáng tin, theo chính sách nền tảng.

AEAD cung cấp tính bí mật và khả năng kiểm chứng toàn vẹn/xác thực của ciphertext trong threat model phù hợp, nhưng:

- Nonce/IV cần tạo và quản lý theo quy tắc của thuật toán.
- Không được tái sử dụng nonce với cùng key trong các trường hợp thuật toán yêu cầu nonce unique.
- Associated Data (AAD) cần thiết kế ổn định nếu dùng tenant_id/customer_id làm ràng buộc ngữ cảnh.
- Key rotation và metadata phiên bản phải được bảo đảm.
- Không tự viết giao thức mã hóa mới bằng SQL string operations.

### 15.2. Một cấu trúc lưu trữ có thể gồm

```sql
CREATE TABLE sec390.secure_identifiers (
    customer_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    ciphertext bytea NOT NULL,
    nonce bytea NOT NULL,
    authentication_tag bytea NOT NULL,
    algorithm text NOT NULL,
    key_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

Các cột là **hợp đồng lưu trữ minh họa**. Không phải mã nguồn tự thực hiện AES-GCM; ứng dụng phải dùng thư viện triển khai đúng cách và xác minh tính hợp lệ của format.

### 15.3. Lớp bảo vệ

Application-layer encryption hạn chế việc DB thấy plaintext trong trường đã mã hóa. Tuy nhiên:

- Ứng dụng có quyền giải mã vẫn nhìn thấy plaintext.
- Nếu app bị chiếm hoàn toàn, kẻ tấn công có thể lợi dụng quyền KMS.
- Metadata/indices vẫn có thể tiết lộ thông tin.
- Nếu plaintext được ghi vào log/cache, ưu thế này bị suy giảm.
- DBA có thể xóa/đổi ciphertext và phá dịch vụ; AEAD giúp phát hiện tampering, không bảo đảm availability.

## 16. Envelope encryption và KMS

Khi số bản ghi lớn, không nên có một passphrase hard-coded duy nhất sống mãi.

Một kiến trúc phổ biến:

```text
KMS-managed KEK (Key Encryption Key)
           |
           +-- bảo vệ / wrap DEK
                    |
                    v
           DEK (Data Encryption Key)
                    |
                    +-- mã hóa trường dữ liệu
                    |
                    v
              Ciphertext
```

Metadata có thể gồm:

```text
record_id
ciphertext
nonce/tag
wrapped_dek
kek_key_id
key_version
algorithm
```

### 16.1. Vì sao tách KEK và DEK?

- Cho phép hạn chế quyền dùng master key/KEK.
- Dễ thiết kế luồng key rotation.
- Có thể cấp key cho nhóm dữ liệu khác nhau.
- Giảm phạm vi một key nếu phân tách đúng.
- Hỗ trợ audit request tới KMS/HSM.

### 16.2. KMS không tự động an toàn nếu quyền quá rộng

Nếu service role có quyền gọi `Decrypt` với mọi DEK của mọi tenant, việc chiếm role có thể vẫn dẫn tới lộ hàng loạt.

Nên áp:

- Least privilege.
- Phân tách environment/tenant theo risk profile.
- Key policy/identity context.
- Audit decrypt calls.
- Quota/rate limiting thích hợp.
- Cơ chế thu hồi và xử lý sự cố.

### 16.3. Nơi nào giữ plaintext?

Một service giải mã cần có plaintext trong RAM để sử dụng. Cần kiểm soát lifetime của dữ liệu ở memory, crash dumps, debugging/tracing và responses. “Không lưu key trong DB” chưa đồng nghĩa “không còn bản rõ ở bất cứ nơi nào”.

## 17. Key rotation: thay khóa không giống thay mật khẩu kết nối

Các lớp khóa có lịch rotation khác nhau:

| Khóa | Bảo vệ | Khi đổi cần xét |
|---|---|---|
| TLS private key/cert | Kết nối mạng | Chứng chỉ, trust, rollout clients |
| Volume encryption key | Storage block | Nhà cung cấp, snapshots, recoverability |
| Field DEK | Từng bản mã/dataset | Re-encrypt dữ liệu, versioning |
| KMS KEK | Bảo vệ DEKs | Rewrap DEKs hoặc chiến lược phiên bản |
| Application secret/token | Kết nối/API | Rollout dịch vụ và phiên hoạt động |

### 17.1. Rotation phải có version

Nếu chỉ lưu `ciphertext` nhưng không biết key version, sau nhiều vòng rotation sẽ khó xác định key dùng để giải mã.

Thông thường metadata phải ghi rõ:

```text
key_version = "v3"
algorithm = "AES-256-GCM"
ciphertext = ...
```

Các giá trị là minh họa cấu trúc, không phải một format chuẩn bắt buộc.

### 17.2. Rotating KEK không luôn phải re-encrypt toàn bộ dữ liệu

Nếu dùng envelope encryption đúng cách, có thể **rewrap DEKs** bằng KEK mới thay vì giải mã/mã hóa lại mọi data record, tùy chính sách và threat model.

Nếu DEK đã lộ hoặc thuật toán/mode cần thay, có thể phải **re-encrypt dữ liệu** với DEK mới.

### 17.3. Rotation và backup

Một backup cũ có thể vẫn cần key cũ để restore. Không xóa keys trước khi:

- Biết dữ liệu/backups nào dùng key ấy.
- Hoàn tất migration/re-encryption cần thiết.
- Cân nhắc retention và quy định xóa.
- Kiểm thử khôi phục được dữ liệu hợp lệ.

Ngược lại, việc giữ mọi key mãi mãi cũng tăng rủi ro. Phải có chính sách cân bằng recoverability và retention.

## 18. Hashing mật khẩu: không giải mã, không masking

Mật khẩu đăng nhập **không nên lưu dạng mã hóa có thể đảo ngược** chỉ để có thể đọc lại.

Hướng tốt là dùng **password hashing chuyên dụng** với:

- Salt ngẫu nhiên riêng cho mỗi mật khẩu.
- Tham số chi phí được kiểm soát.
- Thuật toán phù hợp hiện tại, ví dụ Argon2id qua thư viện xác thực đáng tin.
- Rehash khi policy/parameters thay đổi.
- Rate limiting/MFA/credential breach defenses ở tầng ứng dụng.

### 18.1. Vì sao SHA-256(password) không đủ?

```sql
SELECT digest('my-password', 'sha256');
```

SHA-256 là fast hash, thuận lợi cho brute-force nếu password yếu. Không dùng như giải pháp password storage mới chỉ vì đã có `digest`.

### 18.2. pgcrypto có crypt/gen_salt

Một ví dụ giáo dục trong DB:

```sql
-- Dữ liệu giả, không dùng mật khẩu thật trong SQL literals.
SELECT crypt(
    'TRAINING-PASSWORD',
    gen_salt('bf', 10)
) AS stored_hash;
```

Kiểm tra dạng legacy:

```sql
SELECT
    crypt('candidate-password', stored_hash)
    = stored_hash AS password_matches
FROM some_login_table
WHERE account_id = $1;
```

Dòng thứ hai là **khuôn mẫu** vì bảng `some_login_table` không được tạo trong lab.

### 18.3. Giới hạn của bcrypt/blowfish

Một số implementation bcrypt có giới hạn độ dài password tính theo bytes (thường 72 bytes) và các hành vi chuẩn hóa cần quan tâm. Vì vậy với hệ thống mới, thường ưu tiên Argon2id trong thư viện xác thực ứng dụng theo policy phù hợp.

### 18.4. Không gửi mật khẩu thật qua câu SQL literal

Khi hashing ở DB server, plaintext password đi tới DB. Nếu điều đó trái threat model hoặc log policy, hãy hash/verify trong service xác thực và chỉ lưu hash được thiết kế đúng.

## 19. Hash email hoặc định danh: nguy cơ dictionary attack

Một địa chỉ email không phải secret ngẫu nhiên 256 bit. Nếu attacker thấy:

```text
SHA256("an@example.invalid")
```

họ có thể thử nhiều email dự đoán và so digest.

### 19.1. “Đã hash” không có nghĩa đã ẩn danh

Hash không có khóa của một miền giá trị nhỏ dễ bị tấn công đoán trước. Một digest ổn định còn có thể giúp liên kết cùng người qua nhiều bảng/dataset.

### 19.2. Dùng keyed HMAC khi bài toán là equality token

Nếu cần token đối chiếu exact-match, một lựa chọn có kiểm soát là **HMAC** với secret được quản lý riêng:

```sql
-- Ví dụ cấu trúc: $1 = email giả đã được normalize,
-- $2 = secret chỉ ứng dụng được phép cung cấp.
SELECT hmac(
    'email:v1:' || lower(trim($1::text)),
    $2::text,
    'sha256'
) AS lookup_token;
```

Secret không được lưu cùng bản copy token nếu mục tiêu là chống offline guessing.

### 19.3. HMAC cũng không phải mã hóa

HMAC có thể hỗ trợ so sánh equality bằng token, không cho phép giải mã email từ token. Nếu vẫn cần gửi email cho khách, bạn phải có đường lưu/giải mã email hợp lệ ở nơi khác.

### 19.4. Normalization là hợp đồng

`lower(trim(email))` là một ví dụ rất đơn giản; email và các identifier khác có quy tắc canonicalization phức tạp theo miền nghiệp vụ. Không tự viết normalization có thể hợp nhất hai định danh khác nhau rồi coi đã “bảo mật”.

## 20. Searchable encryption: đánh đổi giữa truy vấn và rò rỉ

Mã hóa dữ liệu có ba dạng đặc tính thường gặp:

| Cách lưu | Có thể lọc exact equality? | Rò rỉ/giới hạn |
|---|---|---|
| Plaintext | Có | Đọc được nếu có SELECT |
| Randomized encryption/AEAD | Không trực tiếp bằng ciphertext equality ổn định | Giấu so sánh plaintext tốt hơn, nhưng cần decrypt hoặc index phụ |
| Deterministic encryption | Có thể so ciphertext equality khi điều kiện phù hợp | Lộ các giá trị bằng nhau, tần suất |
| HMAC/blind index song song ciphertext | Có thể lọc equality theo token | Lộ equality/frequency và cấu trúc truy cập |
| App decrypt rồi scan | Có ở app logic | Tốn I/O, dữ liệu ra app, khó scale |

### 20.1. Vì sao randomized encryption không hỗ trợ LIKE?

Hai lần encrypt cùng email với nonce ngẫu nhiên đúng cách thường cho hai ciphertext khác nhau. Khi đó:

```sql
WHERE email_ciphertext = :encrypted_candidate
```

không hoạt động như so sánh plaintext, trừ khi thiết kế có cơ chế hỗ trợ đặc thù.

Tương tự, `LIKE '%@example.com'` trên bytea ciphertext không thể hiểu ngữ nghĩa của email ban đầu.

### 20.2. Deterministic encryption làm lộ equality

Kẻ đọc ciphertext có thể biết hai bản ghi có **cùng plaintext** nếu mã hóa xác định đúng theo điều kiện ấy. Với những giá trị có entropy thấp, sự phân bố có thể lộ thông tin đáng kể.

Không dùng deterministic encryption theo cách tự chế chỉ để “index được ciphertext” mà bỏ qua leakage.

### 20.3. Blind index không bảo vệ khỏi mọi suy luận

HMAC token ổn định có thể cho biết:

- Hai khách có cùng identifier đã normalize hay không.
- Giá trị nào xuất hiện nhiều.
- Một token có nằm ở nhiều record hay không.

Khi service bị chiếm và key lộ, offline guessing lại có thể khả thi. Phải xem đây là **rò rỉ được chấp nhận có chủ đích**, không phải mã hóa có thể tìm kiếm mà không lộ gì.

## 21. Một schema lưu ciphertext và blind index

Ví dụ cấu trúc dữ liệu, không triển khai cryptography tự chế:

```sql
CREATE TABLE sec390.encrypted_contacts (
    customer_id bigint PRIMARY KEY
        REFERENCES sec390.customers(customer_id),
    tenant_id integer NOT NULL,
    email_ciphertext bytea NOT NULL,
    email_nonce bytea NOT NULL,
    email_tag bytea NOT NULL,
    email_lookup_token bytea,
    key_version text NOT NULL
);

CREATE INDEX idx_sec390_email_lookup
ON sec390.encrypted_contacts(
    tenant_id,
    email_lookup_token
);
```

Giả định ứng dụng:

1. Chuẩn hóa email theo hợp đồng.
2. Tạo HMAC token bằng lookup key độc lập từ KMS/keystore.
3. Mã hóa email bằng AEAD với key được phép.
4. Ghi ciphertext/nonce/tag/token/key version trong một transaction.
5. Khi lookup, tạo lại token từ email query, lọc theo tenant và token.
6. Giải mã ứng viên theo quyền và xác minh đúng điều kiện nghiệp vụ cần thiết.

### 21.1. Vì sao có tenant_id ở index?

Đó là một dimension truy vấn và phân tách dữ liệu. Nhưng index có tenant_id **không tự làm RLS**; application và database vẫn phải thực hiện authorization.

### 21.2. Lookup key và encryption key nên khác mục đích

Không mặc định tái sử dụng cùng key cho HMAC và AEAD. Key separation/domain separation giúp giảm rủi ro liên quan việc dùng một key cho nhiều giao thức không được thiết kế chung.

### 21.3. Khi rotate lookup key

Nếu lookup token đổi, dữ liệu hiện tại có thể cần recompute/dual-write/dual-read có kiểm soát trong thời gian migration. Không xóa token cũ trước khi các query và index mới đã sẵn sàng.

## 22. Masking: ẩn dữ liệu ở đúng thời điểm hiển thị

Một view có thể không trả cột gốc mà chỉ trả biểu diễn đã che:

```sql
CREATE VIEW sec390.customer_support_view
WITH (security_barrier = true)
AS
SELECT
    c.customer_id,
    c.tenant_id,
    c.full_name,
    CASE
        WHEN position('@' IN c.email) > 0 THEN
            left(c.email, 1) || '***@'
            || split_part(c.email, '@', 2)
        ELSE '***'
    END AS email_masked,
    CASE
        WHEN c.phone IS NULL THEN NULL
        ELSE '***-' || right(c.phone, 4)
    END AS phone_masked
FROM sec390.customers AS c;
```

Kiểm tra:

```sql
SELECT
    customer_id,
    full_name,
    email_masked,
    phone_masked
FROM sec390.customer_support_view
ORDER BY customer_id;
```

Kết quả minh họa:

| customer_id | full_name | email_masked | phone_masked |
|---:|---|---|---|
| 1 | An | a***@example.invalid | ***-0001 |
| 2 | Bình | b***@example.invalid | ***-0002 |
| 3 | Chi | c***@example.invalid | ***-0003 |

### 22.1. Masking ở đây làm được gì?

Giao diện view chỉ xuất ra email/phone dạng che. Cột `national_identifier` không được đưa vào view.

### 22.2. Masking chưa làm được gì?

Bảng `sec390.customers` vẫn giữ plaintext. Người có quyền SELECT trực tiếp email/phone ở bảng gốc có thể đọc toàn bộ.

### 22.3. Dữ liệu che vẫn có thể nhạy cảm

Tên miền email và bốn chữ số cuối số điện thoại có thể đủ để nhận diện một người khi kết hợp các thuộc tính khác. Hãy quyết định mức che theo use case/threat model.

### 22.4. security_barrier không tạo chính sách tenant

Tùy chọn `security_barrier` giúp xử lý một số rủi ro query optimization/predicate evaluation với view được dùng như security boundary, nhưng nó **không tự kiểm tra** người gọi thuộc tenant nào. View demo vẫn hiển thị cả tenant 7 và 8 nếu không có RLS/authorization.

## 23. Masking view cần phân quyền bảng gốc

Nếu cấp cho role hỗ trợ:

```sql
GRANT SELECT ON sec390.customers TO support_role;
```

thì role ấy có thể bỏ qua view và đọc plaintext. Một thiết kế tốt cần:

- Không cấp SELECT toàn bảng gốc cho role chỉ nên xem masked output.
- Chỉ cấp USAGE trên schema và SELECT trên view.
- Kiểm tra view owner/privileges.
- Không cấp quyền tạo function/view trong schema đáng tin cho role không tin cậy.
- Kiểm tra mọi API khác có đường truy cập tới bảng gốc.

### 23.1. Ví dụ tạo role (chỉ DBA/role có CREATEROLE)

```sql
-- Chỉ chạy trong môi trường học tập với quyền quản trị phù hợp.
CREATE ROLE sec390_support NOLOGIN;

GRANT USAGE ON SCHEMA sec390
TO sec390_support;

GRANT SELECT ON sec390.customer_support_view
TO sec390_support;

REVOKE ALL ON sec390.customers
FROM PUBLIC;
```

Không có lệnh grant trên bảng gốc cho `sec390_support`. Nếu nó không được thừa hưởng quyền qua role khác, chỉ view mới là đường truy vấn được cấp ở ví dụ.

### 23.2. REVOKE FROM PUBLIC không thu hồi quyền owner

Owner table vẫn có những quyền vốn có. Nếu role hỗ trợ được tạo là owner hoặc được gán role có SELECT bảng gốc, ví dụ trên không đủ.

**Cần kiểm tra effective privileges** của tài khoản thực sự đăng nhập, cả membership và khả năng SET ROLE.

### 23.3. View owner và base table privileges

Theo semantics view mặc định của PostgreSQL, việc truy cập bảng nền thường được kiểm tra theo quyền của **view owner**, không phải đơn giản theo role invoker. Vì vậy một role có SELECT trên view có thể đọc kết quả view dù không có SELECT trên bảng gốc.

Đây là tính năng hữu ích để giới hạn cột, nhưng cũng tạo trách nhiệm lớn cho người tạo view: một view vô tình SELECT toàn bộ PII sẽ mở lối đọc tương ứng.

### 23.4. Dùng role thực để kiểm tra

Hãy thử bằng connection/role có cùng membership với ứng dụng hỗ trợ, không chỉ dùng superuser rồi kết luận việc thu hồi quyền hoạt động.

## 24. Column-level privileges: không phải role nào cũng đọc được mọi cột

PostgreSQL cho phép grant SELECT trên một số cột:

```sql
-- Dùng trên role học tập nếu role có tồn tại.
GRANT SELECT (
    customer_id,
    tenant_id,
    full_name
)
ON sec390.customers
TO sec390_support;
```

Nếu role không có SELECT toàn bảng qua đường khác, nó được đọc các cột được grant, không mặc nhiên được đọc `email`, `phone` hoặc `national_identifier`.

### 24.1. Lời gọi hợp lệ

```sql
SELECT customer_id, full_name
FROM sec390.customers;
```

Lời gọi trên cần quyền thích hợp khi chạy dưới role hỗ trợ.

### 24.2. Lời gọi không được phép

```sql
-- Với role chỉ được cấp các cột ở trên:
SELECT email
FROM sec390.customers;
```

Dự kiến bị từ chối bởi quyền SELECT của cột/bảng, trừ khi còn quyền từ role khác.

### 24.3. Không thể bảo vệ cột bằng cách “chỉ ẩn nó trong UI”

Nếu database login có SELECT toàn bảng, việc client chỉ render hai cột không phải column security. Một SQL injection hoặc admin query vẫn có thể SELECT cột không hiển thị.

### 24.4. Column GRANT và masked view bổ sung cho nhau

- Column privileges: **ngăn truy cập SQL** tới cột không được phép.
- Masked view: **cung cấp một biểu diễn giới hạn** của cột nhạy cảm cho người có quyền dùng view.

Tùy quyền và mục tiêu, có thể dùng một hoặc kết hợp hai cơ chế.

## 25. Dynamic masking theo role: cần thiết kế cẩn thận

Có ứng dụng yêu cầu:

```text
Nhân viên support:  a***@example.invalid
Nhân viên PII-team: an@example.invalid
```

Có thể thiết kế hai view/endpoint với quyền rõ ràng thay vì một biểu thức role-dependent phức tạp:

```text
sec390.customer_support_view -> dữ liệu đã che
sec390.customer_private_view -> dữ liệu đầy đủ, grant rất hạn chế
```

### 25.1. Vì sao hai view đôi khi dễ audit hơn?

Đường truy cập rõ ràng:

- Role hỗ trợ chỉ SELECT view đã che.
- Role chuyên trách có quyền view full hoặc chức năng reveal đã kiểm soát.
- Mỗi view có thể có audit/log policy khác.
- Dễ kiểm tra grants và phát hiện mở quyền ngoài ý muốn.

### 25.2. Nếu dùng CASE theo quyền

Một function/view có thể dựa trên `current_user`, role membership hoặc authorization context để chọn biểu diễn, nhưng phải hiểu:

- `session_user` khác `current_user` trong một số tình huống như SET ROLE/SECURITY DEFINER.
- Role membership và quyền SET ROLE ảnh hưởng kết quả.
- Không lấy một biến GUC do client tùy ý SET làm bằng chứng quyền.
- Người có quyền SELECT base table vẫn bỏ qua masking.
- Query optimization và user-defined functions có thể tạo đường suy luận.

Không thiết kế “dynamic masking” bằng một CASE đơn giản rồi coi mọi đường đọc đã an toàn.

## 26. security_invoker view và bài toán quyền bảng gốc

PostgreSQL hiện đại có tùy chọn view `security_invoker`, ảnh hưởng cách quyền và RLS đối với quan hệ nền được kiểm tra.

Ví dụ cú pháp (cần phiên bản hỗ trợ):

```sql
CREATE VIEW sec390.customer_invoker_view
WITH (security_invoker = true)
AS
SELECT
    customer_id,
    full_name
FROM sec390.customers;
```

### 26.1. Không nhầm với view mặc định

Với security_invoker view, base table privileges của invoker trở nên quan trọng theo semantics của PostgreSQL. Một role chỉ có SELECT view nhưng không có quyền cần thiết trên bảng gốc có thể không truy vấn được.

### 26.2. Một rủi ro thiết kế

Để view security_invoker chạy, team có thể vội cấp:

```sql
GRANT SELECT ON sec390.customers TO support_role;
```

Việc này có thể làm mất ý nghĩa che dữ liệu nếu đồng thời cấp quyền đọc toàn bảng plaintext.

Cần chọn:

- Mô hình view owner-based + view đã giới hạn.
- Invoker-based view + column privileges/RLS phù hợp.
- Hoặc một thiết kế API khác.

Quyết định phải kiểm tra bằng role thực, không chỉ đọc DDL.

## 27. RLS: che cột khác với giới hạn hàng

Masking thường trả lời: “**Cột này được hiển thị tới mức nào?**”

Row Level Security trả lời: “**Role này được xem hoặc sửa những hàng nào?**”

Ví dụ:

```text
tenant_id 7 -> khách An, Bình
tenant_id 8 -> khách Chi
```

Nếu role tenant 7 chỉ được nhìn tenant 7, masking email thành `c***@example.invalid` **không giải quyết** rò rỉ rằng Chi thuộc tenant 8. Phải chặn luôn hàng đó.

### 27.1. RLS có thể áp dụng trên bảng

Mẫu minh họa khi role đã được tạo và được cấp quyền cần thiết:

```sql
CREATE ROLE sec390_tenant7 NOLOGIN;

ALTER TABLE sec390.customers
ENABLE ROW LEVEL SECURITY;

CREATE POLICY sec390_tenant7_read
ON sec390.customers
FOR SELECT
TO sec390_tenant7
USING (tenant_id = 7);
```

Đây là chính sách ví dụ theo role, không phải cơ chế tự suy ra mọi tenant. Tùy yêu cầu, cần thêm chính sách INSERT/UPDATE/DELETE và xác thực role/tenant đúng.

### 27.2. RLS không che cột được phép xem

Nếu role tenant 7 có SELECT toàn bảng và policy chỉ lọc tenant=7, role vẫn thấy email/phone/identifier của **những hàng tenant 7**.

RLS và column masking là **hai chiều độc lập**.

### 27.3. Owner, superuser, BYPASSRLS

RLS có quy tắc bypass, đặc biệt với superuser, roles có quyền BYPASSRLS và chủ bảng trong điều kiện thông thường. PostgreSQL hỗ trợ `FORCE ROW LEVEL SECURITY` cho một số trường hợp owner.

Không kiểm tra RLS bằng superuser rồi kết luận role ứng dụng cũng có hành vi y hệt.

### 27.4. GUC tenant_id không phải danh tính được xác minh

Ví dụ thường gặp:

```sql
USING (tenant_id = current_setting('app.tenant_id')::integer)
```

Nếu client tự có thể `SET app.tenant_id = '8'`, điều kiện này **không tự là authorization**. Chỉ dùng context đã được ràng buộc với identity tin cậy và cơ chế ngăn client giả mạo.

### 27.5. RLS và view owner có thể tương tác ngoài dự kiến

View thông thường dùng base permissions/RLS context theo semantics owner/view options. Vì vậy ngay cả khi bảng gốc đã bật RLS, view của owner có quyền bypass có thể trả hàng mà app user không kỳ vọng.

Cần kiểm tra **đường truy cập cụ thể**: direct table, owner-based view, security_invoker view, SECURITY DEFINER function và mọi role membership.

## 28. SECURITY DEFINER: có thể phá mô hình che nếu dùng sai

Trong PostgreSQL:

- `SECURITY INVOKER` là mặc định của function.
- `SECURITY DEFINER` chạy với quyền của owner theo semantics function.

Một SECURITY DEFINER function có quyền đọc bảng plaintext có thể vô tình cấp quyền reveal rộng hơn cho caller.

### 28.1. Ví dụ API reveal sai thiết kế

Một function như:

```sql
-- KHUÔN MẪU NGUY HIỂM NẾU GRANT EXECUTE RỘNG:
CREATE FUNCTION sec390.reveal_identifier(p_customer_id bigint)
RETURNS text
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec390, pg_temp
AS $$
    SELECT c.national_identifier
    FROM sec390.customers AS c
    WHERE c.customer_id = p_customer_id;
$$;
```

Nếu owner có quyền đọc các hàng và `EXECUTE` được cấp cho role không phù hợp, caller có thể đọc identifier theo ID bất kỳ.

### 28.2. Không phải cứ SET search_path an toàn là đủ

Một search_path an toàn chỉ giúp giảm nguy cơ object shadowing. Nó **không** thay:

- Kiểm tra caller có quyền xem đúng khách hay không.
- Tenant isolation.
- Rate limiting.
- Audit reveal.
- Thu hồi EXECUTE từ PUBLIC nếu cần.
- Giới hạn SQL injection tại app.
- Bảo vệ secret/key.

### 28.3. Secure by design

Nếu phải có chức năng reveal:

1. Tài liệu hóa mục đích và role được phép.
2. Kiểm tra authorization theo identity đáng tin bên trong boundary.
3. Tránh nhận một `tenant_id` tùy ý như bằng chứng quyền.
4. Khóa search_path và qualify bảng/hàm quan trọng.
5. REVOKE EXECUTE FROM PUBLIC rồi chỉ GRANT cho role có thẩm quyền.
6. Audit việc reveal theo chính sách và không log plaintext.
7. Xem xét khóa giải mã tách khỏi DB nếu threat model đòi hỏi.

## 29. Data redaction trong kết quả truy vấn khác thay đổi dữ liệu gốc

Có ít nhất ba cách “che”:

### 29.1. Che khi đọc

```sql
SELECT left(email, 1) || '***'
FROM sec390.customers;
```

Bảng vẫn giữ email nguyên văn. Đây là presentation/query-time masking.

### 29.2. Tạo bản dữ liệu đã che cho môi trường thử nghiệm

Một ETL có thể xuất dataset đã được giả danh hoặc xóa những trường nhạy cảm. Tuy nhiên cần xét tính **không thể tái nhận diện** khi kết hợp tuổi, vùng địa lý, ngày mua, mã đơn...

### 29.3. Ghi đè hoặc xóa dữ liệu nhạy cảm gốc

```sql
UPDATE sec390.customers
SET phone = NULL
WHERE customer_id = ...;
```

Đây là thay đổi dữ liệu nghiệp vụ, không đơn giản là masking. MVCC, WAL, replicas, backups và retention có thể khiến giá trị cũ còn tồn tại trong các bản sao hoặc lịch sử trong một khoảng thời gian.

Không hứa xóa dữ liệu “ngay tức thì khỏi mọi bản sao” chỉ vì UPDATE đã commit.

## 30. Masking có thể bị suy luận ngược

Giả sử view chỉ hiển thị:

```text
a***@example.invalid
```

Nhưng cùng role có quyền:

```sql
SELECT count(*)
FROM sec390.customers
WHERE email = 'an@example.invalid';
```

Người dùng có thể thử các ứng viên cho tới khi tìm thấy giá trị đúng, dù kết quả SELECT không hiển thị email gốc.

### 30.1. Bảo vệ phải kiểm tra cả query capabilities

Một role không được xem plaintext cũng không nên có những quyền cho phép lọc/sắp xếp/so khớp trực tiếp trên cột bí mật theo cách tạo oracle.

### 30.2. Count, order và timing đều có thể lộ

Các rò rỉ có thể xảy ra qua:

- Tổng số hàng thỏa điều kiện.
- Sort order theo giá trị bí mật.
- Error messages cho các giá trị cụ thể.
- Response timing giữa các query.
- Trạng thái tồn tại/không tồn tại khi thử ID.
- Facets và aggregations.
- Pagination và các liên kết từ data khác.

### 30.3. security_barrier là một công cụ, không phép màu

View `security_barrier` giải quyết một số vấn đề thứ tự đánh giá/pushdown trong threat model view, nhưng không làm biến mất mọi kênh timing/inference, cũng không thay column privileges hay RLS.

## 31. Logs là một “bản sao dữ liệu” cần được bảo vệ

Nhiều sự cố rò rỉ không bắt đầu từ bảng chính mà từ log:

```text
INFO sql="INSERT INTO customers(email) VALUES('an@example...')"
INFO request_body={"password":"..."}
DEBUG token=...
ERROR decrypt failed for plaintext=...
```

### 31.1. Những chỗ có thể ghi dữ liệu nhạy cảm

- Application request/response logs.
- ORM SQL debug output.
- PostgreSQL statement logs.
- Error logs.
- Audit extensions.
- Query monitoring/tracing.
- APM spans.
- Crash dumps/core dumps.
- Job/ETL logs.
- Deployment/CI logs.
- Terminal và psql history.

### 31.2. Parameterization không đảm bảo tuyệt đối không log values

Bind parameters giảm rủi ro SQL injection và giúp tách câu SQL khỏi giá trị, nhưng một driver, database log setting hoặc observability agent vẫn có thể ghi bind values tùy cấu hình.

Cần cấu hình redaction, logging scope, retention, access và kiểm thử thực tế.

### 31.3. pg_stat_statements không phải kho bí mật

Các công cụ thống kê query có thể chuẩn hóa câu SQL, nhưng không nên xem đó là cam kết tuyệt đối rằng không có giá trị nào rò rỉ qua mọi hệ thống telemetry. Tránh đặt keys/plaintext vào identifiers, comments hay thông báo lỗi.

### 31.4. Không ghi mã hóa key vào RAISE NOTICE

`RAISE NOTICE 'key: %', secret;` trong PL/pgSQL có thể đưa key vào server/client logs. Hạn chế cả debug statements có khả năng lộ PII và secrets.

## 32. WAL, replication và CDC cũng nằm trong phạm vi kiểm soát

Khi PostgreSQL ghi dữ liệu:

- WAL có thể chứa thông tin cần cho recovery/replication.
- Physical replica phục hồi/duy trì dữ liệu database.
- Logical replication/CDC có thể phát các giá trị cột theo cấu hình.
- Backup và snapshot ghi lại dữ liệu tại thời điểm khác nhau.

### 32.1. Nếu cột là plaintext trong PostgreSQL

Các bản sao hoặc luồng có thể mang thông tin đủ để tái tạo plaintext, tùy định dạng và cấu hình. Disk encryption trên một server không tự bảo vệ mọi replica và downstream consumer.

### 32.2. Nếu cột là app-encrypted ciphertext

Database và bản sao thường thấy ciphertext cho trường ấy, nhưng vẫn có:

- Metadata.
- Search tokens/blind indexes.
- IDs và quan hệ.
- Kích thước bản mã.
- Thời gian tạo/sửa.
- Những trường plaintext khác.

Không giả định toàn bộ sự kiện CDC đã trở thành dữ liệu vô hại.

### 32.3. Quyền replication/CDC là quyền nhạy cảm

Một replication connector có thể nhận nhiều bản ghi vượt phạm vi một tenant hoặc một API bình thường. Cần quản lý credentials, publication filters, network, logs và storage của consumer.

## 33. Index, cache, materialized view và search index

Một trường dữ liệu nhạy cảm có thể xuất hiện ở nơi khác ngay trong database:

```sql
CREATE INDEX ... ON ... (email);
```

Hoặc ở:

- Generated columns.
- Expression indexes.
- Materialized views.
- Cached API responses.
- Search engines.
- Reporting tables.
- Message queues.
- Analytics warehouses.

### 33.1. Masking view không tự che những bản sao này

Nếu bạn tạo `customer_support_view` chỉ che email, nhưng có một bảng `customer_search` lưu email plaintext và role hỗ trợ được SELECT bảng ấy, khả năng lộ vẫn tồn tại.

### 33.2. Tìm kiếm encrypted fields cần thiết kế riêng

B-tree index trên ciphertext ngẫu nhiên không phục hồi ngữ nghĩa tìm kiếm theo email gốc. Nếu cần equality lookup, dùng một thiết kế index/token có threat model rõ, không “giải mã toàn bảng để so sánh” mà không xét chi phí/risks.

### 33.3. Cache và TTL

Nếu role vừa mất quyền xem PII, cache chứa plaintext có thể còn hợp lệ nếu không có cơ chế invalidation/revocation. Mã hóa storage không tự xóa cache khi quyền thay đổi.

## 34. Role và quyền tối thiểu trong PostgreSQL

Một thiết kế nên phân biệt các vai trò:

```text
app_public       -> SELECT dữ liệu công khai
app_support      -> SELECT view đã che
app_private      -> giới hạn xem field cần thiết
app_writer       -> INSERT/UPDATE qua API rõ
app_migration    -> DDL có kiểm soát
db_operator      -> vận hành DB và backup
key_operator     -> quản trị khóa trong KMS
auditor          -> xem audit metadata theo quyền
```

Tách vai trò **database operation**, **business data access** và **key use** khi có thể.

### 34.1. Không cấp SUPERUSER cho application

Superuser vượt qua rất nhiều lớp quyền PostgreSQL. Một tài khoản ứng dụng có SUPERUSER làm RLS, view masking và các grants trở nên vô nghĩa đối với kẻ chiếm tài khoản ấy.

### 34.2. Không cấp owner role cho support

Owner có quyền quản lý object và trong nhiều trường hợp RLS bypass nếu không có FORCE. Role chỉ cần xem view không nên là owner bảng PII.

### 34.3. Default privileges cần được quản lý

Một migration tạo bảng/view/function mới có thể vô tình cấp quyền rộng hoặc thiếu REVOKE phù hợp. Dùng quy trình migration và `ALTER DEFAULT PRIVILEGES` theo owner/schema khi cần.

### 34.4. EXPLAIN cũng là một góc nhìn

Một tài khoản có khả năng chạy query/EXPLAIN trên dữ liệu hoặc thống kê có thể quan sát metadata, cardinality, plans và timings. Đừng xem một môi trường query tùy ý là cùng mức rủi ro với API chỉ cho phép vài truy vấn đã kiểm soát.

## 35. Kiểm tra quyền thực tế, đừng đoán từ một GRANT

PostgreSQL có các hàm để xem hiệu lực quyền:

```sql
SELECT
    has_table_privilege(
        'sec390_support',
        'sec390.customers',
        'SELECT'
    ) AS can_select_entire_table,
    has_column_privilege(
        'sec390_support',
        'sec390.customers',
        'email',
        'SELECT'
    ) AS can_select_email_column,
    has_table_privilege(
        'sec390_support',
        'sec390.customer_support_view',
        'SELECT'
    ) AS can_select_masked_view;
```

### 35.1. Một bảng có column grants không đồng nghĩa SELECT cả bảng

Role được cấp SELECT cho một vài cột có thể dùng một số truy vấn hợp lệ, nhưng không có quyền SELECT mọi cột. Phải xem cả table-level và column-level privileges.

### 35.2. Kiểm tra bằng role thực với dữ liệu giả

Nếu có thể, mở session dưới effective role của ứng dụng để xác minh:

- SELECT bảng gốc bị từ chối đúng mức.
- SELECT view che thành công.
- Query không thể lọc trên cột bí mật.
- Không nhìn thấy hàng tenant khác.
- Không gọi được function giải mã nhạy cảm.
- Không truy cập được schema/bảng nguồn qua object khác.

### 35.3. Kiểm tra permission chưa đủ để chứng minh encryption

Role không thể SELECT email có thể do GRANT hạn chế, trong khi data files vẫn chứa plaintext. Đây là hai lớp bảo vệ độc lập.

## 36. Quy trình xử lý yêu cầu “chỉ cho support xem 4 số cuối”

Giả sử policy:

> Support có thể xác nhận bốn chữ số cuối của phone, nhưng không được thấy số đầy đủ hay số giấy tờ.

Một quy trình:

1. Xác định vì sao cần bốn chữ số cuối.
2. Nếu có thể, lưu/trả chỉ bốn số cuối cho chức năng xác nhận.
3. Nếu vẫn cần số đầy đủ ở hệ thống, hạn chế đường lưu và key use.
4. Tạo view/endpoint chỉ xuất trường cần thiết.
5. Không cấp quyền SELECT raw phone/national_identifier cho support.
6. Kiểm tra RLS/tenant scope ở cùng đường truy cập.
7. Kiểm tra API logs và exports.
8. Thử các truy vấn có thể suy ra dữ liệu.
9. Audit việc truy cập theo chính sách.
10. Định kỳ review vai trò/quyền.

### 36.1. Kiểm thử ví dụ

```sql
SELECT
    customer_id,
    full_name,
    phone_masked
FROM sec390.customer_support_view
WHERE tenant_id = 7
ORDER BY customer_id;
```

Trong lab, query cho hai hàng tenant 7. Nhưng **lọc tenant_id=7 trong SQL của client không phải authorization** nếu client có thể tự đổi 7 thành 8. Với production cần binding vào identity/role hoặc RLS đúng.

## 37. Dynamic data masking không phải tính năng lõi đồng nhất ở mọi PostgreSQL

Một số hệ quản trị hoặc nhà cung cấp có tính năng tên “dynamic masking policy”. Đừng áp máy móc cú pháp của một RDBMS khác vào PostgreSQL.

Trong PostgreSQL, các cách tiếp cận có thể gồm:

- Views và biểu thức `CASE`/string functions.
- Column-level privileges.
- RLS.
- API/functions được cấp quyền hạn chế.
- Extension hoặc sản phẩm chuyên dụng (nếu có và được kiểm chứng).
- Data redaction tại application.
- ETL tạo sanitized datasets.

### 37.1. Không coi mọi extension masking là một security boundary được chứng minh

Nếu dùng extension, cần đánh giá:

- Phiên bản/khả năng bảo trì.
- Cơ chế role/DDL.
- Quyền owner/superuser.
- Cách làm việc với views/functions/copy/replication.
- Performance/overhead.
- Backups/restore.
- Kênh log và các đường truy xuất khác.

### 37.2. Data masking test không phải anonymization mặc nhiên

Che vài chữ số hoặc thay tên bằng giá trị giả trong một bản export có thể vẫn giữ khóa liên kết với hệ thống thật. Để tuyên bố dữ liệu đã được anonymize, cần đánh giá nguy cơ tái nhận diện theo threat model/quy định áp dụng.

## 38. Mã hóa có xác thực và toàn vẹn dữ liệu

Chỉ có confidentiality không nhất thiết đủ. Một ciphertext bị sửa có thể:

- Giải mã lỗi.
- Trả plaintext sai với một số mode không xác thực.
- Gây lỗi xử lý phía ứng dụng.

### 38.1. Ưu tiên AEAD trong thiết kế mới

Ứng dụng nên dùng thư viện AEAD có cấu hình được kiểm chứng thay vì tự tạo:

```text
AES-CBC + tự thêm checksum
```

mà không hiểu padding oracle, MAC, key separation và cách xác thực.

### 38.2. pgcrypto raw encryption cần thận trọng

Những hàm mã hóa cấp thấp của `pgcrypto` có tập tùy chọn/giới hạn riêng; chúng không tự cung cấp toàn bộ property của một giao thức mã hóa có xác thực hiện đại chỉ vì chọn `aes`.

Nếu cần app-level authenticated encryption, dùng thư viện mật mã đã được review thay vì xây custom protocol dựa trên các hàm raw SQL.

### 38.3. AAD có thể ràng buộc ngữ cảnh

Ví dụ có thể đưa tenant_id, record type hoặc stable record ID vào AAD nếu thiết kế cho phép, giúp phát hiện ciphertext bị tráo giữa các ngữ cảnh. Cần bảo đảm khi ID/tenant thay đổi thì xử lý AAD và re-encryption đúng; không tự chọn AAD thay đổi liên tục làm tất cả dữ liệu không thể giải mã.

## 39. Rotation và migration không được làm mất dữ liệu

Một quy trình migration từ plaintext sang app-encrypted fields:

```text
Giai đoạn 1: thêm ciphertext/key_version columns
          |
Giai đoạn 2: deploy ứng dụng dual-write có kiểm soát
          |
Giai đoạn 3: backfill ciphertext bằng key mới
          |
Giai đoạn 4: đối soát count/ID/integrity/authorization
          |
Giai đoạn 5: chuyển read path sang ciphertext
          |
Giai đoạn 6: dừng ghi plaintext
          |
Giai đoạn 7: theo dõi, xử lý dữ liệu lệch
          |
Giai đoạn 8: xóa plaintext theo retention,
             đánh giá WAL/backups/exports
```

### 39.1. Không xóa cột gốc ngay sau backfill

Có thể tồn tại hàng chưa backfill, lỗi key version, retry hoặc instance ứng dụng cũ còn đang đọc plaintext.

### 39.2. Dual-write phải kiểm soát tính nhất quán

Nếu app ghi plaintext rồi ghi ciphertext bằng hai transaction độc lập, có thể tạo lệch. Dùng transaction DB phù hợp và outbox/retry nếu cần đồng bộ giữa các dịch vụ.

### 39.3. Hậu migration có thể vẫn còn bản cũ

WAL, backup, replicas, logs và cache có thể chứa plaintext từ trước. Cần kế hoạch retention và xóa theo yêu cầu, không hứa “ALTER TABLE DROP COLUMN là đã xóa mọi dấu vết”.

## 40. Incident response: nếu khóa hoặc backup đã lộ

Cần chuẩn bị trước:

- Danh mục keys và key owners.
- Mapping giữa dữ liệu và key versions.
- Khả năng disable/revoke quyền KMS.
- Khả năng rotate DEK/KEK.
- Quy trình re-encrypt theo batch.
- Audit logs không chứa plaintext.
- Backup inventory và downstream destinations.
- Khả năng xác định khoảng thời gian lộ và dữ liệu ảnh hưởng.
- Kế hoạch thông báo theo quy định/chính sách áp dụng.
- Kiểm thử restore với keys còn hợp lệ.

### 40.1. Nếu key lộ nhưng data files không lộ

Phải đánh giá thực tế: kẻ tấn công có quyền KMS tới đâu, có thể lấy ciphertext ở đâu, thời gian key bị dùng, log audit có gì. Chưa thể tự kết luận “an toàn” hoặc “đã lộ mọi dữ liệu”.

### 40.2. Nếu chỉ backup lộ nhưng key được tách đúng

Field encryption có thể hạn chế rò rỉ plaintext cho các trường đã mã hóa. Nhưng các cột plaintext, metadata và khả năng đoán/tra cứu vẫn cần được đánh giá.

### 40.3. Nếu application đã bị chiếm

Mã hóa ứng dụng có thể không bảo vệ các dữ liệu mà ứng dụng đang được phép decrypt. Thu hồi credentials, key permissions, tokens, vá lỗ hổng và phân tích truy cập là những bước độc lập với re-encryption.

## 41. Hiệu năng và vận hành của encryption/masking

Tất cả cơ chế đều có chi phí:

| Cơ chế | Chi phí phổ biến |
|---|---|
| TLS | CPU handshake/cryptography, quản lý certs |
| Disk encryption | Chi phí mã hóa storage, quản lý volume keys |
| pgcrypto per field | CPU encrypt/decrypt trong DB, thêm kích thước ciphertext |
| App AEAD | CPU/memory ở app, network thêm metadata, KMS calls |
| Masking view | Biểu thức tính toán, giới hạn pushdown trong một số view |
| RLS | Predicate/policy evaluation, tác động plan và query |
| Blind index | Thêm dữ liệu/index, key lifecycle, equality leakage |
| KMS per operation | Latency/cost/availability và rate limits |
| Audit/log redaction | Vận hành pipeline logging và giám sát |

### 41.1. Không đo chỉ một SELECT nhỏ

Benchmark cần xét:

- p50/p95/p99 theo workload thật.
- Số lần giải mã.
- KMS caching và thời gian key validity.
- CPU/memory ở application/DB.
- Kích thước WAL/backups.
- Query plans khi RLS/view áp dụng.
- Latency khi gọi KMS lỗi/chậm.
- Khả năng backfill/rekey hàng triệu record.

### 41.2. Encryption không phải cách tối ưu query

Một cột ciphertext thường khó index theo plaintext hơn. Giải mã trong WHERE:

```sql
-- Ý tưởng KHÔNG NÊN dùng làm chiến lược tìm kiếm quy mô lớn:
WHERE decrypt(ciphertext, key) = search_value
```

có thể phải xử lý rất nhiều hàng, tăng chi phí và khiến plaintext tiếp xúc database. Nếu cần tìm kiếm, thiết kế lookup token/index chuyên dụng theo risk assessment.

### 41.3. Giảm KMS calls không có nghĩa cache key vô hạn

DEK caching có thể cải thiện latency nhưng tăng thời gian key nằm trong memory và rủi ro khi application bị chiếm. Thiết kế TTL, giới hạn quyền, invalidation và audit tương ứng.

## 42. Bảng quyết định: lớp nào giải quyết yêu cầu nào?

| Yêu cầu | Công cụ/lớp thường phù hợp | Còn thiếu điều gì? |
|---|---|---|
| Chống nghe lén DB traffic | TLS + server identity validation | Không bảo vệ app/DB sau giải mã |
| Chống lấy trộm ổ đĩa đã tắt | Disk/volume encryption | Không ngăn DBA/SQL role đọc plaintext |
| Bảo vệ exported backup | Backup encryption + storage ACL | Người có key và file vẫn có thể restore |
| DB không được thấy plaintext của một field | App-layer AEAD | App/key authority vẫn có plaintext |
| Chỉ role đặc biệt được giải mã | KMS policies + app authorization | Phải ngăn lạm dụng role/app |
| Support chỉ xem email che | Masked view/API + restricted grants | Phải chặn đường đọc bảng gốc |
| Tenant không xem tenant khác | RLS/permissions + trusted identity | Không tự che PII của tenant hợp lệ |
| Không đọc một cột cụ thể | Column-level privileges | Chưa mã hóa file dữ liệu |
| Lưu mật khẩu đăng nhập | Argon2id/password hashing | Rate limiting/MFA vẫn cần |
| Equality lookup trên encrypted email | HMAC/blind index có kiểm soát | Lộ equality/frequency |
| Xóa dữ liệu quá hạn | Retention/deletion workflow | Backup/WAL/replicas có lifecycle riêng |
| Phát hiện truy cập bất thường | Audit/monitoring | Log không được chứa PII/keys |
| Ngăn SQL injection | Parameterized SQL + input validation | Không thay authorization |
| Chống mất dữ liệu | Backups, restore drills, HA | Encryption không bảo đảm availability |
| Kiểm tra dữ liệu hợp lệ | Constraints/validation | Không làm dữ liệu bí mật |
| Bảo vệ key | KMS/HSM, secret manager, least privilege | Key-use authorization và app compromise |

**Không có “một nút bật bảo mật” bao phủ mọi hàng trong bảng.** Phải xác định rõ đối tượng tấn công trước khi chọn công cụ.

## 43. Những lỗi thiết kế thường gặp

### 43.1. “Đã bật TLS nên backup an toàn”

Sai. TLS bảo vệ kênh truyền, không tự mã hóa file `pg_dump` đã xuất.

### 43.2. “Đã mã hóa ổ đĩa nên DBA không đọc được PII”

Sai trong nhiều triển khai. Database server đọc dữ liệu đã được giải mã khi volume mở.

### 43.3. “Dùng pgcrypto nên PostgreSQL không nhìn thấy plaintext”

Sai. pgcrypto mã hóa/giải mã bên trong server, passphrase và plaintext đi vào server.

### 43.4. “Dùng SHA-256 cho mật khẩu là đủ”

Sai. Passwords cần password hashing phù hợp, salt và cost, không chỉ fast hash.

### 43.5. “Hash email là ẩn danh hoàn toàn”

Sai. Miền email đoán được, hash có thể bị dictionary attack hoặc linkability.

### 43.6. “Mã hóa deterministic không lộ thông tin”

Sai. Equality và frequency thường bị lộ, có thể dẫn tới inference.

### 43.7. “Có masked view nên cấp SELECT bảng gốc cũng được”

Sai. Role có thể bỏ qua view.

### 43.8. “RLS tự che tất cả PII”

Sai. RLS chủ yếu hạn chế hàng; role có SELECT cột PII trong hàng hợp lệ vẫn xem được.

### 43.9. “Role owner kiểm thử RLS thành công nên app cũng vậy”

Role owner/superuser có những quy tắc bypass. Cần kiểm tra với effective role thực.

### 43.10. “SECURITY DEFINER luôn an toàn vì đã SET search_path”

Sai. Nó vẫn cần check authorization, EXECUTE grants và tránh lộ plaintext.

### 43.11. “Không SELECT cột bí mật thì không thể suy ra nó”

Có thể suy luận qua WHERE, ORDER BY, counts, errors và timing nếu caller có đủ query capabilities.

### 43.12. “Key lưu cùng bảng ciphertext vẫn an toàn”

Sai trong threat model nơi kẻ tấn công lấy cả database/backup.

### 43.13. “Một key cho mọi tenant là đơn giản và đủ”

Có thể tạo blast radius rất lớn. Phân tách keys/permissions theo rủi ro và yêu cầu nghiệp vụ.

### 43.14. “Rotate key xong có thể xóa key cũ ngay”

Có thể làm backup hoặc dữ liệu cũ không giải mã được. Cần inventory, rewrap/re-encrypt và restore tests.

### 43.15. “DROP COLUMN là xóa ngay plaintext khỏi mọi nơi”

Sai. WAL, backups, replicas, exports, logs có thể giữ bản sao theo lifecycle.

### 43.16. “Bind parameters chắc chắn không vào log”

Sai như một khẳng định tuyệt đối. Một số logging/tracing cấu hình có thể ghi bind values.

### 43.17. “Masking khiến dữ liệu thành anonymous”

Sai. Dữ liệu đã che có thể vẫn nhận diện lại từ tổ hợp thuộc tính.

### 43.18. “Encrypted field có thể LIKE và ORDER BY như plaintext”

Không trực tiếp với randomized encryption; cần thiết kế search phù hợp.

### 43.19. “AEAD bảo vệ availability”

Không. Kẻ tấn công có thể xóa/từ chối dịch vụ dù không giải mã được.

### 43.20. “KMS key không xuất ra ngoài nên app không thể bị lộ PII”

App được cấp quyền decrypt vẫn có thể nhận plaintext và có thể bị chiếm.

### 43.21. “security_barrier view làm mọi truy vấn an toàn”

Không. Nó không thay role grants, RLS, xác thực người dùng và các kiểm soát inference khác.

### 43.22. “Chỉ production DB có PII”

Staging clones, backups, BI, support tools và crash dumps có thể chứa PII thật nếu không được kiểm soát.

### 43.23. “Tạo HMAC token là không còn lộ gì”

Equality/frequency, membership và access patterns vẫn có thể lộ; nếu key lộ có nguy cơ dictionary attack.

### 43.24. “Mã hóa nghĩa là không cần audit”

Không. Phải biết ai gọi decrypt, truy cập bản rõ, tải backups và thay key policies.

## 44. Bài tập thực hành có giải thích

### Bài 1. Nghe lén đường truyền app → PostgreSQL

**Đề:** Kẻ tấn công có thể quan sát gói tin giữa app và DB. Cần lớp bảo vệ nào?

**Đáp án:** TLS với xác minh chứng chỉ/hostname đúng, thường `sslmode=verify-full` ở libpq và cấu hình server thích hợp. Phải có authentication và network controls, không chỉ TLS.

### Bài 2. Server đang chạy và role SELECT email

**Đề:** Đã bật disk encryption. Role có thể SELECT plaintext email không?

**Đáp án:** có nếu role có quyền SQL thích hợp và cột lưu plaintext. Disk encryption không tự ngăn SQL access.

### Bài 3. Backup SQL xuất ra bucket

**Đề:** Production volume encrypted có bảo vệ backup SQL không?

**Đáp án:** không tự động; cần mã hóa và phân quyền backup riêng.

### Bài 4. pgcrypto decrypt diễn ra ở đâu?

**Đáp án:** trong PostgreSQL server, nên DB có thể nhìn thấy plaintext trong ngữ cảnh giải mã.

### Bài 5. Muốn DB hoàn toàn không nhận plaintext identifier

**Đáp án:** cân nhắc mã hóa ứng dụng bằng vetted AEAD library trước khi INSERT; chỉ gửi ciphertext và metadata phù hợp.

### Bài 6. Có nên lưu DEK cạnh ciphertext dưới dạng plaintext?

**Đáp án:** không nếu threat model cần người lấy DB backup không thể decrypt. Dùng KMS/HSM hoặc key separation thích hợp.

### Bài 7. Khóa KMS lộ qua quyền app

**Đề:** App có quyền giải mã mọi customer. Có chắc hệ thống vẫn an toàn?

**Đáp án:** không; kẻ chiếm app có thể lạm dụng quyền decrypt. Cần least privilege, segmentation, audit và incident response.

### Bài 8. Masking email bằng một SQL expression

```sql
SELECT
    left(email, 1) || '***@'
    || split_part(email, '@', 2) AS masked_email
FROM sec390.customers;
```

**Đáp án:** làm thay đổi biểu diễn ở output, không thay dữ liệu gốc.

### Bài 9. Support có SELECT masked view và bảng gốc

**Đáp án:** thiết kế có lỗ hổng vì role vẫn có thể SELECT email/phone trực tiếp từ bảng gốc.

### Bài 10. Giới hạn support chỉ đọc ID và tên

**Đáp án:**

```sql
GRANT SELECT(customer_id, full_name)
ON sec390.customers
TO sec390_support;
```

Nhưng cần bảo đảm role không có quyền rộng qua membership/other grants.

### Bài 11. RLS lọc tenant 7 có che email tenant 7?

**Đáp án:** không; nếu role có SELECT email, nó vẫn có thể thấy plaintext email của các hàng tenant 7.

### Bài 12. Masked view có loại tenant 8 không?

**Đáp án:** không tự động nếu view không có policy/WHERE/authorization về tenant. Lab view minh họa chứa cả tenant 7 và 8.

### Bài 13. current_setting('app.tenant_id') có phải auth token chắc chắn?

**Đáp án:** không, nếu client có thể tùy ý SET giá trị. Phải ràng buộc với identity đáng tin.

### Bài 14. Tại sao view owner cần được review?

**Đáp án:** base permissions/RLS context có thể theo view owner; nếu owner có quyền rộng, view có thể thấy nhiều hơn invoker dự kiến.

### Bài 15. security_invoker view có luôn làm masking tốt hơn?

**Đáp án:** không. Nếu phải cấp SELECT toàn bảng gốc để invoker query được, có thể làm mất lớp che. Cần thiết kế quyền phù hợp.

### Bài 16. SECURITY DEFINER function reveal theo customer_id

**Đáp án:** cần authorization theo caller và tenant, giới hạn EXECUTE, safe search_path và audit; một p_customer_id bất kỳ không tự xác định quyền.

### Bài 17. Hash SHA-256 mật khẩu có đủ?

**Đáp án:** không. Dùng Argon2id/password hashing phù hợp với salt/cost và các lớp chống tấn công đăng nhập.

### Bài 18. Hash email bằng SHA-256 có “ẩn danh” không?

**Đáp án:** không. Email có thể bị đoán bằng dictionary attack, digest còn tạo khả năng liên kết.

### Bài 19. HMAC khác SHA-256 thuần như thế nào?

**Đáp án:** HMAC có secret key, nên việc tạo/kiểm tra token không chỉ dựa vào một giá trị công khai; vẫn cần key management và leak analysis.

### Bài 20. HMAC token có thể giải mã lấy email không?

**Đáp án:** không. Nếu cần email thật phải có nguồn giá trị/đường decrypt riêng.

### Bài 21. Randomized encryption có cùng ciphertext cho cùng plaintext?

**Đáp án:** với nonce/randomness được dùng đúng, thường không; đó là một lý do equality search trên ciphertext khó.

### Bài 22. Deterministic encryption lộ gì?

**Đáp án:** equality của các plaintext và tần suất xuất hiện trong ngữ cảnh tương ứng.

### Bài 23. Blind index bảo vệ hết mọi thông tin không?

**Đáp án:** không. Token equality/frequency và access patterns có thể lộ.

### Bài 24. Search bằng LIKE trên ciphertext có hoạt động không?

**Đáp án:** không theo ngữ nghĩa plaintext với ciphertext được mã hóa đúng; cần thiết kế lookup/search riêng.

### Bài 25. Dùng AES-CBC raw mà không MAC có đủ?

**Đáp án:** không nên giả định đủ tính toàn vẹn/xác thực. Ưu tiên thiết kế AEAD qua thư viện được review.

### Bài 26. Tại sao lưu key_version?

**Đáp án:** biết khóa/thuật toán tương ứng để giải mã, quản lý rotation và restore dữ liệu cũ.

### Bài 27. Rotate KEK có cần re-encrypt mọi row?

**Đáp án:** không phải luôn; envelope encryption có thể cho phép rewrap DEKs. Nếu DEK lộ hoặc chính sách yêu cầu thì có thể phải re-encrypt.

### Bài 28. DROP COLUMN sau migration xóa hết plaintext chưa?

**Đáp án:** chưa thể kết luận; WAL/backups/replicas/exports/logs cần retention và xử lý riêng.

### Bài 29. Log một SQL statement với literal password là an toàn?

**Đáp án:** không; SQL lịch sử/log có thể chứa password. Dùng bind và logging redaction, nhưng vẫn kiểm tra cấu hình values logging.

### Bài 30. Tại sao backup có thể là điểm yếu hơn production DB?

**Đáp án:** backup có thể là plaintext export, rộng quyền, phân tán nhiều nơi và giữ lâu, dù production DB có volume encryption.

### Bài 31. Cách kiểm tra TLS kết nối hiện tại

```sql
SELECT ssl, version, cipher
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
```

**Đáp án:** xem backend connection TLS, không thay kiểm tra hostname verification ở client.

### Bài 32. Cần hỗ trợ chỉ xem 4 số cuối điện thoại

**Đáp án:** API/view trả `right(phone,4)` có scope phù hợp, không grant raw column, chặn access paths khác; xét dữ liệu vẫn có thể nhận diện qua tổ hợp.

### Bài 33. Kẻ tấn công có thể WHERE email='known@example.invalid' nhưng không SELECT email

**Đáp án:** câu hỏi là role có được phép dùng cột đó trong WHERE hay không. Nếu có, sự tồn tại một match có thể tạo oracle; cần giới hạn SQL privileges/query capabilities.

### Bài 34. Nếu người dùng có SUPERUSER?

**Đáp án:** các ranh giới SQL permissions/RLS có thể bị bypass. Không cấp superuser cho app; dùng key separation nếu threat model muốn hạn chế DBA đọc field.

### Bài 35. Làm sao kiểm tra role support được đọc cột email?

```sql
SELECT has_column_privilege(
    'sec390_support',
    'sec390.customers',
    'email',
    'SELECT'
);
```

**Đáp án:** kiểm tra effective privilege, đồng thời cần test thực tế với role.

### Bài 36. Dữ liệu app-encrypted có xuất hiện plaintext trong WAL không?

**Đáp án:** nếu chỉ ciphertext được gửi vào PostgreSQL cho trường đó, WAL thường chứa biểu diễn ciphertext/metadata của dữ liệu ấy, nhưng các cột plaintext khác và logs/downstream vẫn cần bảo vệ.

### Bài 37. KMS mất kết nối thì rủi ro gì?

**Đáp án:** một service có thể không giải mã được dữ liệu, làm ảnh hưởng availability; cần thiết kế caching/timeout/fallback theo risk policy, không mở quyền decrypt vô hạn để tránh lỗi.

### Bài 38. Có nên log key khi decrypt lỗi?

**Đáp án:** không. Ghi error code/correlation ID, key version hoặc metadata không nhạy cảm phù hợp, không ghi secret/plaintext.

### Bài 39. Dữ liệu ở staging có cần che không?

**Đáp án:** có nếu staging chứa PII. Tốt hơn dùng fixture giả/sanitized dữ liệu được xử lý theo chính sách; không mặc định môi trường không production là vô hại.

### Bài 40. Chọn hai lớp cho support xem tenant đúng mà email bị che

**Đáp án:** cần **row authorization** (ví dụ RLS/permissions) và **column masking** (view/API hoặc quyền cột), cùng xác thực đáng tin và không cho đường truy cập bảng gốc bỏ qua cơ chế.

## 45. Checklist triển khai bảo vệ dữ liệu PostgreSQL

| Câu hỏi | Mục cần xác nhận |
|---|---|
| Đã phân loại dữ liệu và mục đích sử dụng? | PII/secrets/public/internal |
| Có dữ liệu không cần thu thập? | Data minimization |
| Đã mô hình hóa đối tượng tấn công? | Network, disk, SQL role, DBA, app, backups |
| Kết nối app–DB có TLS? | Cấu hình client/server |
| Client có verify hostname và CA? | verify-full khi phù hợp |
| At-rest encryption bao phủ gì? | Volumes, WAL, temp, snapshots |
| Backup exports được mã hóa riêng? | Storage ACL và KEK |
| Replica/CDC/data warehouse có quyền bảo vệ tương đương? | Downstream inventory |
| Dữ liệu nào phải không hiện plaintext trong DB? | App-layer encryption |
| Dùng thuật toán AEAD được review? | Nonce/tag/AAD handling |
| Keys có nằm ngoài DB và backups? | KMS/HSM/key separation |
| Có phân quyền decrypt theo identity/tenant? | Least privilege |
| Có key_version và kế hoạch rotation? | Restore/rekey |
| Cần equality lookup encrypted data? | Leakage của HMAC/blind index |
| Passwords có được hash đúng? | Argon2id/salt/cost |
| Có dùng fast SHA-256 cho password? | Không |
| Support được xem đúng trường và mức che? | Masked view/API |
| Role support có SELECT bảng gốc? | Không nếu không cần |
| Column privileges đã xem với effective role? | has_column_privilege |
| Tenant boundary đã bảo vệ? | RLS/trusted identity |
| Đã kiểm tra owner/BYPASSRLS/superuser? | Không suy diễn RLS |
| View owner/security_invoker được đánh giá? | Base-table access |
| SECURITY DEFINER có quyền reveal rộng? | EXECUTE grants/search_path |
| Query capabilities có gây oracle? | WHERE/COUNT/ORDER BY |
| Logs/tracing có redaction? | Không PII/keys/bind secrets |
| Backups/clones/staging có retention? | Phục hồi và xóa dữ liệu |
| Có audit decrypt/backup/export? | Monitoring |
| Có incident response và revoke keys? | Kế hoạch khi lộ |
| Có test role và dữ liệu giả? | Không chỉ test superuser |
| Có đánh giá CPU/latency/KMS outage? | Performance và availability |
| Có kiểm chứng restore key cũ? | Rotation không làm mất dữ liệu |
| Có chính sách pháp lý/retention phù hợp? | Không chỉ SQL kỹ thuật |

## 46. Bảng tra cứu nhanh

| Muốn... | Hướng thường dùng | Không nhầm với... |
|---|---|---|
| Mã hóa kết nối DB | TLS | Disk encryption |
| Chống đọc đĩa offline | Volume encryption | SQL authorization |
| Mã hóa một trường trong DB | pgcrypto, nếu threat model cho phép | DB không thấy plaintext |
| DB không thấy bản rõ của một trường | App-layer AEAD | Quyền KMS tự an toàn |
| Quản lý key có rotation | KMS/HSM/envelope encryption | Lưu key trong bảng |
| Che email cho support | Masked view/API | Encrypt toàn bộ DB |
| Ngăn SELECT cột email | Column privileges | Ẩn cột trong UI |
| Chặn tenant khác | RLS/trusted authorization | CASE masking |
| Hash mật khẩu | Argon2id/password hashing | SHA-256 đơn giản |
| Tìm equality trên encrypted email | HMAC/blind index có quản lý key | Không lộ tần suất |
| Giới hạn backup exposure | Backup encryption + ACL | TLS kết nối DB |
| Ngăn SQL injection | Bind parameters | Named masking |
| Kiểm soát lộ qua logging | Redaction và retention | “Có TLS là đủ” |
| Ngăn mất dữ liệu | Backup/restore/HA | Encryption |
| Bảo vệ bản sao test | Dữ liệu giả/sanitized + access control | Chỉ đổi tên cột |
| Chứng minh giới hạn quyền | Test dưới effective role | Test superuser |

## 47. Tài liệu chính thức và hướng tìm hiểu

**PostgreSQL:**

- [SSL Support](https://www.postgresql.org/docs/current/ssl-tcp.html) — cấu hình TLS phía server.
- [libpq SSL Support](https://www.postgresql.org/docs/current/libpq-ssl.html) — xác minh CA/hostname và sslmode.
- [pg_stat_ssl](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-SSL-VIEW) — trạng thái TLS backend.
- [pgcrypto](https://www.postgresql.org/docs/current/pgcrypto.html) — mã hóa PGP, hashing, HMAC và các cảnh báo về dữ liệu/khóa.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — GRANT/REVOKE và quyền theo cột.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS, owner/bypass và cách hoạt động.
- [CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html) — security_barrier/security_invoker và quyền views.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html) — SECURITY DEFINER, ownership, privileges.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html) — search_path và an toàn khi sử dụng hàm.
- [Logging](https://www.postgresql.org/docs/current/runtime-config-logging.html) — nguy cơ và cấu hình ghi log SQL/parameters.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — các dạng backup và giới hạn khôi phục.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — lưu trữ WAL và phục hồi.

**Ngoài PostgreSQL:**

- Tài liệu hiện hành của thư viện mật mã và KMS/HSM mà tổ chức sử dụng.
- Khuyến nghị password storage của OWASP và tài liệu thuật toán Argon2id.
- Chính sách pháp lý, phân loại dữ liệu, retention và thông báo sự cố áp dụng trong tổ chức.

Các ví dụ chỉ mang tính hướng dẫn và sử dụng dữ liệu giả. Khi triển khai thật phải xác minh phiên bản, quyền cài extension, chế độ mã hóa, key policies, kết nối TLS, grants/RLS, ứng dụng và backups. **Không coi các đoạn SQL trong bài là kết quả đã chạy trên một PostgreSQL instance.**

## 48. Tổng kết: mỗi lớp bảo vệ một phần của hệ thống

Sơ đồ ghi nhớ:

```text
Dữ liệu nhạy cảm
    |
    +-- Có thực sự cần lưu không?
    |       -> Nếu không, đừng thu thập
    |
    +-- Khi truyền?
    |       -> TLS + xác minh server
    |
    +-- Khi nằm trên storage?
    |       -> Disk/backup encryption
    |
    +-- DB có được thấy plaintext?
    |       -> Có thể dùng pgcrypto nếu được phép
    |       -> Nếu không, app-layer encryption + KMS
    |
    +-- Ai được giải mã?
    |       -> Key policies, least privilege, audit
    |
    +-- Ai được đọc những hàng nào?
    |       -> Authentication, GRANT, RLS
    |
    +-- Ai được thấy những cột nào?
    |       -> Column privileges, masked views/APIs
    |
    +-- Dữ liệu có bị copy tới nơi khác?
    |       -> Logs, WAL, backups, replicas, CDC, BI, cache
    |
    +-- Nếu bị lộ hoặc mất key?
            -> Rotation, incident response, restore
```

### Những nguyên tắc cần nhớ

1. **Mã hóa không thay quyền truy cập.** TLS/volume encryption không chặn role có SELECT đọc plaintext của cột được phép.
2. **Masking không phải encryption.** View chỉ trả một biểu diễn đã che; dữ liệu gốc vẫn có thể tồn tại.
3. **RLS và column privileges giải quyết hai chiều khác nhau.** RLS giới hạn hàng; masking/column permissions giới hạn cột và dạng hiển thị.
4. **DB-side pgcrypto khác app-layer encryption.** pgcrypto xử lý plaintext/key ở DB; app-layer encryption có thể giảm bản rõ mà DB nhìn thấy.
5. **Key separation quyết định hiệu quả thực tế của field encryption.** Nếu kẻ lấy ciphertext cũng lấy được key, lớp bảo vệ suy yếu nghiêm trọng.
6. **Hash mật khẩu phải có thuật toán chuyên dụng.** Fast SHA-256 và reversible encryption không phải phương án mặc định cho password storage.
7. **Hash hoặc HMAC định danh không mặc nhiên ẩn danh.** Cần xét đoán giá trị, equality leakage, key management và liên kết giữa các datasets.
8. **Không có encrypted search miễn phí về leakage.** Tìm kiếm equality thường đánh đổi khả năng so khớp với việc lộ một số thông tin.
9. **Mọi bản sao là một phạm vi rủi ro mới.** WAL, backup, logs, search, BI, staging và caches đều cần được kiểm soát.
10. **SECURITY DEFINER, view ownership và RLS bypass phải được kiểm tra trên effective roles.** Không dùng superuser để tự chứng minh authorization.
11. **Rotation và xóa dữ liệu là một quy trình nhiều bước.** Không xóa key hoặc plaintext ngay khi chưa đối soát restore, replication và retention.
12. **Threat model đi trước lựa chọn công cụ.** Xác định đối tượng tấn công, dữ liệu cần bảo vệ và trust boundary trước khi chọn pgcrypto, KMS, view, RLS hay disk encryption.

**Một câu để nhớ:** *TLS bảo vệ đường truyền; disk/backup encryption bảo vệ bản sao lưu trữ; field encryption bảo vệ giá trị khi thiếu khóa; masking giới hạn điều được nhìn thấy; GRANT/RLS giới hạn điều được phép truy cập; và key management quyết định lớp mã hóa có thực sự giữ được bí mật hay không.* Chỉ khi các lớp được thiết kế cùng nhau, đúng threat model và kiểm chứng theo từng role, dữ liệu PostgreSQL mới được bảo vệ một cách có ý nghĩa.


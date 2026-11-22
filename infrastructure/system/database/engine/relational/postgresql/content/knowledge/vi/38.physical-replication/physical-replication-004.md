# Role sao chép, TLS và giới hạn truy cập trong PostgreSQL

Physical replication cho phép một PostgreSQL standby nhận và phát lại WAL từ primary để duy trì bản sao vật lý của cluster. Kết nối giữa standby và primary thường sử dụng replication protocol qua TCP. Vì kết nối này có thể truyền WAL chứa thay đổi của nhiều database, quyền replication cần được cấp có chủ đích, giới hạn theo nguồn kết nối và bảo vệ bằng TLS.

Ba lớp kiểm soát cần phối hợp:

1. **Role** xác định tài khoản nào được phép đăng nhập và sử dụng replication protocol.
2. **pg_hba.conf và network controls** xác định kết nối đến từ đâu, được phép dùng phương thức xác thực nào.
3. **TLS** mã hóa dữ liệu trên đường truyền và có thể xác minh danh tính server/client bằng chứng chỉ.

Một role có thuộc tính REPLICATION không tự động được phép kết nối từ mọi địa chỉ. Một dòng pg_hba.conf cho phép kết nối cũng không tự tạo role hoặc cấp quyền replication. TLS thành công cũng không thay thế xác thực PostgreSQL.

~~~mermaid
flowchart TD
    S["Standby / pg_basebackup"] --> N["Network firewall"]
    N --> T["TLS handshake"]
    T --> H["pg_hba.conf: hostssl + source CIDR"]
    H --> A["Authentication: SCRAM hoặc certificate"]
    A --> R["Role: LOGIN + REPLICATION"]
    R --> P["Replication protocol / WAL sender"]
    P --> W["WAL stream tới standby"]
~~~

Bài học thuộc chương **Sao chép vật lý**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ tìm hiểu replication role, HBA rules, password authentication, TLS server/client certificates, cấu hình standby, giới hạn kết nối, replication slots và cách giám sát kết nối an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao physical replication cần role có thuộc tính REPLICATION.
2. Tạo role replication với quyền tối thiểu cần thiết.
3. Phân biệt quyền LOGIN, REPLICATION và SUPERUSER.
4. Hiểu replication connection dùng database selector đặc biệt trong pg_hba.conf.
5. Viết HBA rule giới hạn user, địa chỉ nguồn và TLS.
6. Hiểu thứ tự khớp rule trong pg_hba.conf.
7. Phân biệt SCRAM-SHA-256, MD5, password file và certificate authentication.
8. Bật TLS trên primary và cấu hình certificate/key.
9. Cấu hình standby xác minh server bằng sslmode=verify-full.
10. Hiểu mutual TLS và xác minh client certificate.
11. Kết hợp TLS với pg_basebackup và streaming replication.
12. Giới hạn kết nối bằng firewall, listen_addresses và role connection limit.
13. Hiểu max_wal_senders và max_replication_slots.
14. Quản lý mật khẩu, chứng chỉ và vòng đời rotation.
15. Giám sát kết nối bằng pg_stat_replication và pg_stat_ssl.
16. Kiểm tra HBA rules và reload cấu hình an toàn.
17. Chẩn đoán lỗi authentication, TLS, certificate và replication.
18. Xây dựng checklist bảo mật và kiểm thử failover/rotation.

## 2. Physical replication sử dụng kết nối nào?

Physical streaming replication truyền WAL records từ primary tới standby. Primary chạy WAL sender process; standby chạy WAL receiver process. Kết nối này dùng replication protocol thay vì một phiên SQL thông thường gắn với database ứng dụng.

~~~text
Primary PostgreSQL
  |
  +-- WAL sender
        |
        | TCP + TLS + PostgreSQL authentication
        |
        v
Standby PostgreSQL
  |
  +-- WAL receiver
        |
        +-- ghi và replay WAL
~~~

Standby có thể được khởi tạo bằng pg_basebackup rồi tiếp tục streaming WAL. Khi standby kết nối lại sau restart hoặc network interruption, nó sử dụng thông tin trong primary_conninfo và cơ chế xác thực đã cấu hình.

### Replication connection không phải SQL connection bình thường

Trong pg_hba.conf, physical replication connection thường được khớp bằng database field đặc biệt:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256
~~~

Từ khóa `replication` ở database field khớp replication connection. Nó không phải tên database ứng dụng cần tạo.

Với logical replication, subscriber kết nối tới một database cụ thể và dùng replication protocol cho logical replication; HBA rule thường phải chỉ rõ database thực tế thay vì giả định mọi kết nối replication đều dùng từ khóa này.

## 3. Role replication là gì?

PostgreSQL sử dụng role để xác định quyền của người dùng. Để một tài khoản đăng nhập bằng replication protocol, role cần:

- Thuộc tính LOGIN để có thể mở session.
- Thuộc tính REPLICATION để được phép bắt đầu replication connection và thực hiện các hoạt động replication được hỗ trợ.
- Không cần SUPERUSER chỉ để làm physical replication thông thường.

Ví dụ tạo role:

~~~sql
CREATE ROLE standby_repl
    WITH LOGIN
         REPLICATION
         NOSUPERUSER
         NOCREATEDB
         NOCREATEROLE
         NOINHERIT;
~~~

Role này có thể dùng để kết nối replication. Mật khẩu nên được thiết lập bằng prompt an toàn trong psql:

~~~text
\password standby_repl
~~~

Lệnh \password yêu cầu nhập mật khẩu và tránh phải viết mật khẩu rõ trong câu SQL lưu vào history hoặc log.

### Vì sao không dùng postgres/superuser cho standby?

Superuser có quyền vượt xa nhu cầu streaming replication. Nếu credential bị lộ, kẻ tấn công có thể thực hiện nhiều thao tác quản trị nguy hiểm.

Tạo một role chuyên dụng giúp:

- Giới hạn mục đích sử dụng.
- Dễ rotation và revoke.
- Dễ theo dõi trong logs/statistics.
- Giảm hậu quả nếu secret bị lộ.
- Tách quyền replication khỏi tài khoản DBA và ứng dụng.

### REPLICATION không đồng nghĩa với quyền SELECT mọi bảng

Thuộc tính REPLICATION cho phép dùng replication protocol theo PostgreSQL. Nó không đơn giản là một GRANT SELECT trên mọi table, và cũng không biến role thành superuser. Các quyền của replication role cần được xem riêng với quyền SQL thông thường.

## 4. Xác minh thuộc tính role

Có thể xem role attributes:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolreplication,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolconnlimit,
    rolvaliduntil
FROM pg_roles
WHERE rolname = 'standby_repl';
~~~

Các cột quan trọng:

- rolcanlogin: role có được đăng nhập không.
- rolreplication: role có thuộc tính REPLICATION không.
- rolsuper: role có quyền superuser không.
- rolcreatedb: có được tạo database không.
- rolcreaterole: có được tạo/đổi role khác không.
- rolconnlimit: giới hạn connection của role.
- rolvaliduntil: thời điểm hết hạn mật khẩu, nếu được đặt.

Không xuất password hash từ catalog vào báo cáo không cần thiết. pg_roles che password hash đối với người dùng không có quyền phù hợp, nhưng thông tin xác thực vẫn cần được bảo vệ.

## 5. Giới hạn connection của role

Có thể đặt connection limit:

~~~sql
ALTER ROLE standby_repl CONNECTION LIMIT 3;
~~~

Điều này giới hạn số kết nối đồng thời của role theo semantics PostgreSQL. Cần tính số standby, backup jobs và công cụ quản trị cùng dùng credential đó.

Có thể đặt thời hạn role/password:

~~~sql
ALTER ROLE standby_repl VALID UNTIL '2027-01-01 00:00:00+00';
~~~

Đây là ví dụ thời điểm; hãy đặt theo quy trình rotation thực tế. Nếu password hết hạn mà standby vẫn dùng credential cũ, reconnect có thể thất bại. Hãy lên lịch thay credential trên standby trước khi hết hạn.

### Khi nào nên dùng role riêng cho từng standby?

Nếu có nhiều standby, tạo một role riêng cho từng node có thể giúp:

- Revoke riêng một standby bị mất.
- Phân biệt kết nối trong logs.
- Rotation độc lập.
- Giới hạn connection theo node.
- Thu hẹp HBA source address theo đúng máy.

Đổi lại, cần quản lý nhiều secrets và tránh để role cũ không còn sử dụng vẫn tồn tại lâu dài.

## 6. Cấp quyền REPLICATION cho role có sẵn

Nếu role đã tồn tại và cần dùng cho replication:

~~~sql
ALTER ROLE standby_repl WITH LOGIN REPLICATION;
~~~

Thuộc tính REPLICATION là quyền nhạy cảm. Chỉ cấp cho role chuyên dụng đã được kiểm soát.

Nếu role ứng dụng hiện tại đang có nhiều quyền SQL, không nên tùy tiện thêm REPLICATION vào role đó. Tách tài khoản giúp phân định trách nhiệm và thu hẹp phạm vi truy cập.

Thu hồi khi không còn cần:

~~~sql
ALTER ROLE standby_repl NOREPLICATION;
~~~

Hoặc khóa đăng nhập:

~~~sql
ALTER ROLE standby_repl NOLOGIN;
~~~

Thay đổi này có thể làm streaming replication hiện tại hoặc lần reconnect tiếp theo thất bại. Chỉ thực hiện sau khi xác nhận standby đã được loại khỏi topology hoặc có credential thay thế.

## 7. pg_hba.conf kiểm soát ai được kết nối

pg_hba.conf là Host-Based Authentication configuration. File này xác định:

- Loại kết nối: local, host, hostssl, hostnossl.
- Database hoặc replication connection.
- User/role.
- Địa chỉ nguồn.
- Authentication method.
- Một số tùy chọn bổ sung.

Ví dụ chỉ cho phép standby tại 10.20.0.12 kết nối TLS:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256
~~~

Ý nghĩa:

| Trường | Giá trị | Mục đích |
| --- | --- | --- |
| Type | hostssl | Chỉ chấp nhận TCP connection có SSL/TLS |
| Database | replication | Replication protocol connection |
| User | standby_repl | Role được phép |
| Address | 10.20.0.12/32 | Một địa chỉ IPv4 cụ thể |
| Method | scram-sha-256 | Xác thực mật khẩu SCRAM |

Nếu standby có địa chỉ IPv6, cần rule tương ứng, ví dụ prefix /128 cho một địa chỉ IPv6.

### Giới hạn theo subnet

Nếu có dải standby riêng:

~~~conf
hostssl  replication  standby_repl  10.20.0.0/24  scram-sha-256
~~~

Dải rộng hơn tiện quản lý nhưng mở rộng phạm vi nguồn có thể kết nối. Ưu tiên địa chỉ /32 hoặc /128 khi topology cố định.

## 8. Thứ tự rule trong pg_hba.conf

PostgreSQL kiểm tra pg_hba.conf từ trên xuống. **Rule đầu tiên khớp các thuộc tính kết nối sẽ được sử dụng.** Nếu authentication theo rule đó thất bại, PostgreSQL không tiếp tục thử các dòng phía sau như một fallback.

Ví dụ:

~~~conf
host     replication  all  0.0.0.0/0       reject
hostssl  replication  standby_repl 10.20.0.12/32 scram-sha-256
~~~

Dòng đầu tiên khớp mọi kết nối replication IPv4 và reject, vì vậy dòng cho phép bên dưới không bao giờ được áp dụng cho kết nối đó.

Thứ tự đúng:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256
host     replication  all           0.0.0.0/0      reject
~~~

Có thể thêm rule IPv6 tương ứng. Hãy giữ rule cụ thể trước rule rộng.

### Phân biệt host, hostssl và hostnossl

- host: khớp TCP connections có hoặc không dùng TLS.
- hostssl: chỉ khớp TCP connections dùng SSL/TLS.
- hostnossl: chỉ khớp TCP connections không dùng SSL/TLS.
- local: kết nối qua Unix-domain socket trên hệ điều hành hỗ trợ.

Nếu muốn bắt buộc TLS cho replication, dùng hostssl cho allow rule và bảo đảm không có host rule rộng hơn cho phép cùng user/source mà không mã hóa.

## 9. Chặn kết nối replication không dùng TLS

Có thể đặt rule reject cho kết nối không TLS trước các rule khác phù hợp:

~~~conf
hostnossl  replication  all  0.0.0.0/0  reject
hostnossl  replication  all  ::/0       reject

hostssl    replication  standby_repl  10.20.0.12/32  scram-sha-256
hostssl    replication  standby_repl  2001:db8:20::12/128  scram-sha-256
~~~

Các địa chỉ 2001:db8::/32 trong ví dụ thuộc dải documentation, không phải địa chỉ production. Thay bằng địa chỉ IPv6 thực tế đã được quản lý.

Cần kiểm tra toàn bộ HBA file vì một dòng host khác có thể mở quyền cho nguồn kết nối không mong muốn. Hãy xem các rule theo đúng thứ tự, kể cả include files nếu cấu hình sử dụng chúng.

## 10. Authentication bằng SCRAM-SHA-256

SCRAM-SHA-256 là phương thức password authentication được khuyến nghị cho các cấu hình PostgreSQL hiện đại.

Ví dụ:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256
~~~

Có thể cấu hình password encryption cho mật khẩu mới:

~~~conf
password_encryption = 'scram-sha-256'
~~~

Sau đó đặt lại password cho role để PostgreSQL lưu verifier theo cơ chế mong muốn. Thay đổi password_encryption không tự chuyển đổi password hashes đã tồn tại.

### Vì sao tránh trust?

Phương thức trust cho phép kết nối không cần xác minh mật khẩu theo cách thông thường. Nếu dùng cho replication từ mạng không đáng tin cậy, bất kỳ client nào có thể thỏa rule có nguy cơ giả danh role.

Không dùng trust cho replication production.

### MD5

MD5 authentication đã bị deprecated trong PostgreSQL hiện đại. Nên chuyển sang SCRAM và kiểm tra client compatibility. Các client cũ có thể không hỗ trợ SCRAM; hãy nâng cấp client thay vì hạ mức bảo mật toàn hệ thống nếu có thể.

## 11. Mật khẩu và password file

Standby phải tự reconnect sau restart hoặc network interruption. Nhập password bằng tay không phù hợp cho một service tự động.

Libpq hỗ trợ password file .pgpass trên Unix-like systems hoặc pgpass.conf theo vị trí tương ứng trên Windows.

Một dòng ví dụ:

~~~text
primary.example.net:5432:replication:standby_repl:REPLACE_WITH_SECRET
~~~

Trường database dùng replication cho replication connection.

### Quyền file

Trên Unix-like systems, password file cần permission đủ chặt; libpq bỏ qua file nếu quyền cho phép người khác đọc. Thông thường dùng:

~~~bash
chmod 0600 ~/.pgpass
~~~

Trên Windows, password file có vị trí và cơ chế ACL riêng; áp dụng quyền chỉ cho account dịch vụ cần thiết.

Không commit password file vào Git, không ghi secret vào log, ticket hoặc command history.

### Escaping trong pgpass

Các ký tự : và \ trong field cần được escape theo cú pháp password file. Nếu mật khẩu có các ký tự này, kiểm tra quy tắc escaping của libpq và test connection trước khi đưa vào standby.

## 12. TLS bảo vệ replication connection

TLS cung cấp:

- Mã hóa dữ liệu truyền qua mạng.
- Xác thực server khi client kiểm tra certificate.
- Có thể xác thực client certificate khi cấu hình mutual TLS.
- Bảo vệ chống nghe lén và một số kiểu giả mạo endpoint.

TLS không thay thế:

- Role privileges.
- pg_hba.conf.
- Firewall/network segmentation.
- Secret management.
- Kiểm soát replication slots.
- Giám sát và rotation.

Một kết nối có mã hóa nhưng client không xác minh server certificate vẫn có thể kết nối tới một server giả mạo nếu DNS/routing bị kiểm soát bởi kẻ tấn công.

## 13. Bật TLS trên primary

Ví dụ cấu hình server:

~~~conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_ca_file = 'root.crt'
ssl_min_protocol_version = 'TLSv1.2'
~~~

Ý nghĩa:

- ssl=on: bật SSL/TLS listener.
- ssl_cert_file: certificate server.
- ssl_key_file: private key của server.
- ssl_ca_file: CA certificate dùng cho xác minh client certificate khi cần.
- ssl_min_protocol_version: phiên bản TLS tối thiểu theo policy.

Các file path có thể là relative to data directory hoặc absolute path theo PostgreSQL configuration rules.

### Server certificate cần gì?

Certificate server nên:

- Được ký bởi CA mà standby tin cậy.
- Có SAN (Subject Alternative Name) chứa hostname standby dùng để kết nối.
- Chưa hết hạn.
- Có chain certificate phù hợp.
- Dùng key/certificate pair khớp nhau.

Khi standby kết nối bằng hostname primary.example.net, certificate phải xác minh được hostname đó. Đừng dùng IP trong primary_conninfo nếu certificate chỉ có DNS SAN mà không có IP SAN tương ứng.

### Private key permissions

Private key phải được bảo vệ để chỉ account PostgreSQL service hoặc administrator phù hợp có thể đọc. Trên Unix-like systems, PostgreSQL yêu cầu quyền file private key chặt chẽ; cấu hình phổ biến là owner-only read (0600), hoặc một số cách bố trí root-owned theo quy tắc PostgreSQL. Kiểm tra tài liệu hệ điều hành/version đang dùng.

## 14. Xác minh server certificate từ standby

Trên standby, libpq cần CA certificate tin cậy và sslmode phù hợp.

Dùng:

~~~text
sslmode=verify-full
sslrootcert=/etc/postgresql/certs/root.crt
~~~

verify-full thực hiện hai việc:

1. Xác minh certificate chain theo CA tin cậy.
2. Xác minh hostname kết nối khớp certificate identity.

So sánh các chế độ phổ biến:

| sslmode | Mã hóa | Kiểm tra CA | Kiểm tra hostname |
| --- | --- | --- | --- |
| disable | Không | Không | Không |
| allow/prefer | Có thể không | Không theo nghĩa verify | Không |
| require | Có | Không bảo đảm xác minh identity | Không |
| verify-ca | Có | Có | Không |
| verify-full | Có | Có | Có |

Với replication qua network không đáng tin cậy, verify-full thường là lựa chọn phù hợp nhất nếu PKI và hostname được quản lý đúng.

require chỉ bảo đảm kết nối dùng TLS trong cấu hình tương ứng; đừng coi nó tương đương verify-full.

## 15. Cấu hình primary_conninfo trên standby

Standby sử dụng primary_conninfo để kết nối primary.

Ví dụ:

~~~conf
primary_conninfo = 'host=primary.example.net port=5432 user=standby_repl application_name=standby_1 sslmode=verify-full sslrootcert=/etc/postgresql/certs/root.crt'
~~~

Không ghi password trực tiếp trong file cấu hình nếu có thể dùng password file. Kết hợp .pgpass với dòng database là replication.

Nếu cần khai báo client certificate:

~~~conf
primary_conninfo = 'host=primary.example.net port=5432 user=standby_repl application_name=standby_1 sslmode=verify-full sslrootcert=/etc/postgresql/certs/root.crt sslcert=/etc/postgresql/certs/standby.crt sslkey=/etc/postgresql/certs/standby.key'
~~~

Các connection parameters là libpq parameters; kiểm tra đúng path và quyền đọc file trên standby host.

### Cấu hình được ghi ở đâu?

Khi dùng pg_basebackup -R, PostgreSQL tạo standby.signal và ghi cấu hình kết nối vào postgresql.auto.conf theo cơ chế phiên bản. Administrator có thể bổ sung TLS parameters vào cấu hình được quản lý tương ứng.

Không chỉnh sửa nhầm file cấu hình hoặc để nhiều primary_conninfo xung đột. Xác định nguồn setting bằng pg_settings và SHOW primary_conninfo (cẩn thận không in secrets nếu có).

## 16. Mutual TLS: xác thực cả client và server

Mutual TLS (mTLS) yêu cầu client cung cấp certificate để server xác minh danh tính client, đồng thời client xác minh server certificate.

Trên primary:

- Cấu hình server certificate/key.
- Cấu hình CA tin cậy trong ssl_ca_file.
- HBA rule yêu cầu client certificate theo policy.
- Bảo đảm certificate client được CA tin cậy ký.

Ví dụ HBA:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256 clientcert=verify-full
~~~

Rule này yêu cầu xác minh client certificate cùng với phương thức xác thực SCRAM. Hành vi clientcert và các lựa chọn có thể phụ thuộc PostgreSQL version; kiểm tra trang Client Certificate Authentication của version đang dùng.

Ở client, cung cấp sslcert và sslkey trong libpq connection parameters.

### Certificate authentication thay password

Có thể dùng phương thức cert trong pg_hba.conf:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  cert
~~~

Với cert authentication, PostgreSQL xác minh certificate client theo CA và đối chiếu certificate identity với database user theo quy tắc cert auth, mặc định dựa trên CN trừ khi cấu hình map phù hợp.

Đây là một phương thức authentication riêng. Không nhầm clientcert=verify-full với cert: một cấu hình yêu cầu client certificate có thể vẫn kết hợp password method như SCRAM; phương thức cert dùng certificate làm cơ sở xác thực role.

## 17. Khi nào chọn SCRAM hay mTLS?

| Tiêu chí | TLS + SCRAM | TLS + client certificate |
| --- | --- | --- |
| Mã hóa đường truyền | Có | Có |
| Xác minh server | Có thể dùng verify-full | Có thể dùng verify-full |
| Secret phía client | Password | Private key + certificate |
| Rotation | Thay password | Thay certificate/key |
| Identity | Database role + password | Certificate mapping/identity |
| Quản trị | Đơn giản hơn | Cần PKI/certificate lifecycle |
| Phù hợp | Nhiều hệ thống thông thường | Hệ thống có PKI và yêu cầu mTLS |

Có thể kết hợp client certificate verification với SCRAM để có hai lớp xác minh client identity, tùy policy. Nhưng càng nhiều cơ chế càng cần quy trình rotation và troubleshooting rõ ràng.

## 18. pg_hba.conf với SCRAM và TLS: ví dụ hoàn chỉnh

Giả sử:

- Primary hostname: primary.example.net.
- Standby IP: 10.20.0.12.
- Role: standby_repl.
- Primary listen trên port 5432.
- CA đã được cấu hình và standby có thể xác minh certificate.

HBA:

~~~conf
# Cho phép standby đã định danh kết nối replication bằng TLS + SCRAM
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256

# Từ chối replication không mã hóa từ IPv4/IPv6
hostnossl replication  all          0.0.0.0/0      reject
hostnossl replication  all          ::/0           reject
~~~

Cần đặt allow rule trước reject rule vì PostgreSQL dùng first-match semantics. Ngoài các dòng minh họa, rà soát toàn bộ HBA để chắc chắn không có rule rộng hơn cho phép kết nối không TLS.

Nếu dùng mTLS:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256 clientcert=verify-full
~~~

Không copy nguyên địa chỉ, user hoặc path ví dụ vào production khi chưa thay bằng thông tin thật và kiểm tra certificate.

## 19. Network controls: listen_addresses và firewall

TLS và pg_hba.conf không thay thế network perimeter.

Trên primary:

~~~conf
listen_addresses = '10.20.0.10'
port = 5432
~~~

Chỉ bind vào interface cần thiết. Giá trị mặc định thường chỉ lắng nghe loopback; cấu hình cụ thể tùy topology.

Firewall/security group nên:

- Cho phép TCP 5432 từ đúng standby IP/subnet.
- Chặn các nguồn không cần thiết.
- Hạn chế truy cập từ public internet.
- Dùng private network/VPN khi phù hợp.
- Ghi log các kết nối bị chặn theo policy.
- Tách management network khỏi replication network nếu kiến trúc yêu cầu.

Không mở 0.0.0.0/0 cho PostgreSQL chỉ để giải quyết lỗi kết nối. Hãy xác định nguồn thật và mở phạm vi tối thiểu.

## 20. Cấu hình các tham số replication liên quan

Primary thường cần:

~~~conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
~~~

Ý nghĩa:

- wal_level=replica: tạo đủ WAL information cho physical replication.
- max_wal_senders: số WAL sender processes tối đa đồng thời.
- max_replication_slots: số replication slots tối đa.

Giá trị chỉ là ví dụ. Tính số standby, backup jobs, logical subscribers và headroom cho reconnect/failover.

### Các tham số khác

- wal_keep_size: lượng WAL tối thiểu được giữ lại trong pg_wal theo cấu hình.
- max_slot_wal_keep_size: giới hạn lượng WAL mà replication slots có thể giữ lại, theo version.
- wal_sender_timeout: phát hiện sender connection bị treo.
- wal_receiver_timeout: phát hiện receiver không nhận được phản hồi phù hợp.
- hot_standby: cho phép read-only queries trên standby.

Không dùng wal_keep_size như thay thế replication slots cho mọi topology. Mỗi cơ chế có semantics retention khác nhau.

### Slot có thể làm đầy disk

Một physical replication slot không được consumer tiến lên có thể giữ WAL lâu dài. Theo dõi slot lag và dung lượng pg_wal. Cần có runbook khi standby mất kết nối dài ngày; không xóa slot đang cần cho một standby mà chưa xác định hậu quả.

## 21. Khởi tạo standby bằng pg_basebackup

Một lệnh ví dụ:

~~~bash
pg_basebackup \
  -h primary.example.net \
  -p 5432 \
  -U standby_repl \
  -D /var/lib/postgresql/data \
  -R \
  -X stream \
  -P
~~~

Ý nghĩa:

- -h, -p, -U: kết nối primary.
- -D: thư mục data directory đích.
- -R: tạo cấu hình standby, gồm standby.signal và primary connection settings.
- -X stream: stream WAL trong quá trình backup.
- -P: hiển thị progress.

Trên standby, cấu hình libpq SSL parameters và password file theo cách triển khai. Có thể truyền connection string với sslmode=verify-full và sslrootcert bằng option connection tương ứng; kiểm tra pg_basebackup --help của client.

### Dữ liệu đầu ra

pg_basebackup tạo physical base backup, không phải archive logical của pg_dump. Data directory phải được chuẩn bị đúng theo quy trình; không ghi đè data directory đang chạy.

## 22. Replication slot khi tạo standby

Có thể dùng physical replication slot để giữ WAL cho standby khi nó tạm thời mất kết nối.

Ví dụ tạo slot trên primary:

~~~sql
SELECT *
FROM pg_create_physical_replication_slot('standby_1_slot');
~~~

Sau đó cấu hình standby dùng slot:

~~~conf
primary_slot_name = 'standby_1_slot'
~~~

Một số workflow pg_basebackup hỗ trợ tạo slot cùng lúc bằng option -C -S slot_name; xem pg_basebackup --help và version cụ thể trước khi sử dụng.

### Slot lifecycle

- Slot phải có tên duy nhất trong cluster.
- Slot có thể tồn tại dù standby không hoạt động.
- WAL retention tăng nếu consumer không tiến.
- Cần theo dõi restart_lsn và wal_status theo version.
- Chỉ drop slot sau khi xác định không còn standby/consumer cần nó.

Slot là stateful resource; không phải credential hay HBA rule.

## 23. Giới hạn truy cập bằng connection limit và topology

Một thiết kế an toàn nên áp dụng nhiều lớp:

| Lớp | Cơ chế | Mục tiêu |
| --- | --- | --- |
| Network | Firewall/security group | Giới hạn IP/subnet |
| Listener | listen_addresses | Chỉ bind interface cần thiết |
| HBA | hostssl + user + replication + CIDR | Lọc connection và authentication |
| Role | LOGIN + REPLICATION | Giới hạn quyền account |
| Authentication | SCRAM hoặc cert | Xác minh client |
| TLS | verify-full, CA, certificate | Mã hóa và xác minh server |
| Operations | Monitoring/rotation | Phát hiện và xử lý thay đổi |

Một rule HBA chặt không bảo vệ nếu firewall mở rộng quá mức và có một rule HBA khác cho phép nguồn không mong muốn. Cần review tổng thể.

## 24. Xác minh HBA rules trước reload

PostgreSQL cung cấp view pg_hba_file_rules để xem nội dung parse từ HBA file:

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

Tìm lỗi:

~~~sql
SELECT
    line_number,
    error
FROM pg_hba_file_rules
WHERE error IS NOT NULL;
~~~

View giúp phát hiện syntax errors và xem các rule đã được parse. Nó không mô phỏng chính xác mọi kết nối thực tế hoặc chứng minh rule nào sẽ match trước; cần review thứ tự và test từ đúng source host.

### Reload HBA

Sau khi chỉnh file:

~~~sql
SELECT pg_reload_conf();
~~~

Hoặc dùng pg_ctl reload theo cách vận hành server.

HBA changes thường được áp dụng bằng reload, không cần restart. Nếu reload không thành công, kiểm tra server logs và pg_hba_file_rules.error.

Không xóa rule đang duy trì kết nối replication duy nhất trước khi xác minh rule thay thế. Một kết nối đang mở có thể vẫn hoạt động, nhưng standby reconnect sau restart sẽ thất bại nếu HBA mới sai.

## 25. Kiểm tra TLS đang được sử dụng

View pg_stat_ssl cho biết trạng thái SSL của các backend:

~~~sql
SELECT
    pid,
    ssl,
    version,
    cipher,
    bits,
    client_dn,
    issuer_dn
FROM pg_stat_ssl
ORDER BY pid;
~~~

Ý nghĩa:

- ssl: session có dùng SSL/TLS không.
- version: TLS protocol version.
- cipher: cipher suite.
- bits: độ dài khóa cipher được báo cáo.
- client_dn: distinguished name của client certificate nếu có.
- issuer_dn: CA issuer của client certificate nếu có.

Không phải mọi kết nối đều có client certificate. Với SCRAM qua TLS, client_dn có thể NULL mà TLS vẫn được sử dụng.

### Ghép với pg_stat_activity

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    a.backend_type,
    s.ssl,
    s.version,
    s.cipher
FROM pg_stat_activity AS a
LEFT JOIN pg_stat_ssl AS s
    ON s.pid = a.pid
WHERE a.backend_type = 'walsender'
ORDER BY a.pid;
~~~

Tên backend type và khả năng hiển thị phụ thuộc version. Query này giúp kiểm tra WAL sender sessions có TLS hay không.

## 26. Giám sát standby trên primary

Xem các standby đang kết nối:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
~~~

Các trường hữu ích:

- client_addr: địa chỉ client standby.
- application_name: tên standby.
- state: trạng thái streaming/catchup...
- sync_state: trạng thái synchronous replication nếu áp dụng.
- LSN fields: tiến độ gửi/ghi/flush/replay WAL.
- Lag fields: độ trễ ước lượng theo thống kê, có thể NULL khi idle hoặc không đủ sample.

Kết hợp với pg_stat_ssl để xác nhận TLS cho PID tương ứng.

### Không kết luận chỉ từ một lần query

Lag có thể thay đổi theo workload và thời điểm lấy mẫu. Theo dõi trend, WAL generation, replay rate và disk. Một standby không xuất hiện có thể đang down, chưa kết nối, bị HBA/authentication từ chối hoặc không nằm trong topology hiện tại.

## 27. Kiểm tra cấu hình hiệu lực

Dùng pg_settings:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'ssl',
    'ssl_min_protocol_version',
    'ssl_cert_file',
    'ssl_key_file',
    'ssl_ca_file',
    'listen_addresses',
    'port',
    'wal_level',
    'max_wal_senders',
    'max_replication_slots',
    'wal_keep_size',
    'max_slot_wal_keep_size'
)
ORDER BY name;
~~~

Các tham số có context khác nhau:

- Một số thay đổi cần restart.
- Một số có thể reload.
- Một số có thể thay theo session hoặc role/database.
- pending_restart cho biết có thay đổi chờ restart đối với setting tương ứng.

Đừng giả định mọi tham số TLS hoặc listener có thể áp dụng bằng reload. Kiểm tra context, source và tài liệu version.

## 28. Chẩn đoán lỗi: no pg_hba.conf entry

Thông báo kiểu:

~~~text
FATAL: no pg_hba.conf entry for replication connection
       from host "10.20.0.12", user "standby_repl", SSL encryption
~~~

Kiểm tra:

1. Đúng database selector replication chưa?
2. Đúng username không?
3. Source IP có khớp CIDR không?
4. HBA có hostssl rule không?
5. Rule nào xuất hiện trước và match?
6. Client đang dùng TLS hay không?
7. HBA file có được reload không?
8. Có include file nào chứa rule khác không?

Không mở rộng CIDR thành toàn mạng để chữa nhanh. Xác định đúng địa chỉ source mà primary nhìn thấy, kể cả NAT.

## 29. Chẩn đoán lỗi: password authentication failed

Thông báo:

~~~text
FATAL: password authentication failed for user "standby_repl"
~~~

Kiểm tra:

- Role có tồn tại và LOGIN không?
- Role có thuộc tính REPLICATION không?
- Secret trong password file có đúng không?
- Entry pgpass có database field replication không?
- File permission/ACL có hợp lệ không?
- HBA method có đúng SCRAM/client support không?
- Password có bị rotate ở primary nhưng chưa cập nhật standby không?
- Có VALID UNTIL hết hạn không?
- Standby có đang dùng đúng primary host/port không?

Đổi password trên primary không tự cập nhật secret ở standby. Phải triển khai rotation theo trình tự có kiểm soát.

## 30. Chẩn đoán lỗi TLS: certificate verify failed

Các nguyên nhân thường gặp:

- CA certificate không đúng hoặc không được tin cậy.
- Certificate server hết hạn.
- Hostname không khớp SAN.
- Standby dùng IP nhưng certificate chỉ có DNS SAN.
- Certificate chain thiếu intermediate CA.
- File sslrootcert sai path/quyền.
- Đồng hồ hệ thống sai làm certificate bị coi là chưa có hiệu lực/hết hạn.
- Client đang dùng sslmode không phù hợp.

Kiểm tra certificate bằng công cụ PKI của tổ chức hoặc openssl theo quy trình được phê duyệt. Không hạ sslmode xuống require như một cách sửa lâu dài khi verify-full báo lỗi.

## 31. Chẩn đoán lỗi: server does not support SSL

Nếu client yêu cầu TLS nhưng server không hỗ trợ:

- Kiểm tra ssl=on.
- Kiểm tra PostgreSQL build có SSL support.
- Kiểm tra server certificate/key path.
- Xem logs lúc startup/reload.
- Kiểm tra đang kết nối đúng host/port.
- Kiểm tra proxy/load balancer ở giữa.

Một server có ssl=on nhưng certificate/key lỗi có thể không khởi động hoặc không reload được cấu hình mong muốn. Xem server logs thay vì suy luận từ một thông báo client duy nhất.

## 32. Chẩn đoán standby không streaming

Nếu role/HBA/TLS đúng nhưng standby không stream:

1. Xem pg_stat_replication trên primary.
2. Xem logs của standby và primary.
3. Xác nhận primary_conninfo.
4. Kiểm tra standby.signal.
5. Kiểm tra primary_slot_name nếu dùng slot.
6. Kiểm tra max_wal_senders còn slot.
7. Kiểm tra max_replication_slots và slot state.
8. Kiểm tra firewall, DNS và route.
9. Kiểm tra TLS/password authentication.
10. Kiểm tra WAL availability và timeline/history.

Một lỗi streaming có thể do WAL gap hoặc timeline mismatch chứ không phải credential. Không tạo lại base backup ngay nếu chưa đọc logs và xác định nguyên nhân.

## 33. Giới hạn truy cập bằng connection limit và topology

Các giới hạn nên khớp topology:

- Một role riêng cho từng standby.
- Một source IP hoặc subnet rõ ràng.
- HBA chỉ cho replication connection.
- Firewall chỉ mở port từ standby.
- Connection limit đủ cho reconnect/failover.
- max_wal_senders đủ cho standby và backup operations.
- max_replication_slots đủ cho slot đang quản lý.

Nếu có nhiều standby và pg_basebackup chạy cùng lúc, các sender slots có thể được dùng hết. Để một ít headroom cho backup/failover operations theo capacity plan.

### Connection limit không thay HBA

Role connection limit chỉ giới hạn số session của role. Nó không giới hạn source IP hoặc loại database. HBA vẫn phải giới hạn nguồn và loại kết nối.

## 34. Rotation mật khẩu replication

Một quy trình rotation an toàn:

1. Xác định standby nào đang dùng role/secret.
2. Tạo credential mới hoặc chuẩn bị thời điểm đổi password.
3. Cập nhật password file/secret store trên standby theo quy trình.
4. Thay password role trên primary vào thời điểm đã lên lịch.
5. Kiểm tra kết nối/reconnect và pg_stat_replication.
6. Theo dõi logs để phát hiện auth failures.
7. Thu hồi credential cũ và cập nhật inventory.
8. Ghi lại thời gian, owner và kết quả.

Với một role dùng chung cho nhiều standby, rotation cần phối hợp tất cả nodes. Tách role theo standby giúp thay credential độc lập hơn.

### Có thể dùng hai role song song để rotation

Trong hệ thống cần tránh gián đoạn, có thể tạo role mới, cập nhật một standby hoặc nhóm standby sang credential mới, xác minh kết nối rồi mới revoke role cũ. Cách làm cần phối hợp với HBA rules và capacity để không tạo hai luồng replication ngoài ý muốn.

## 35. Rotation TLS certificate

Certificate rotation cần kế hoạch cho cả CA, server và client certificates.

### Khi đổi server certificate

- Đưa CA mới vào trust store của standby trước.
- Cài certificate/key mới trên primary.
- Kiểm tra SAN, chain, expiry và file permissions.
- Reload/restart theo yêu cầu của setting/version.
- Xác nhận standby reconnect và TLS vẫn verify-full.
- Sau thời gian chuyển tiếp, loại CA cũ khỏi trust store.

### Khi đổi client certificate

- Đưa CA client mới vào ssl_ca_file của primary nếu CA thay đổi.
- Cài client cert/key trên standby.
- Kiểm tra identity mapping và certificate expiry.
- Chuyển standby sang cert mới.
- Xác minh pg_stat_ssl.client_dn.
- Thu hồi hoặc ngừng tin cậy certificate cũ theo PKI policy.

Không xóa CA cũ khỏi trust store trước khi các standby hợp lệ chuyển xong, nếu không có thể làm mất kết nối replication.

## 36. TLS và chứng chỉ hết hạn

Certificate hết hạn có thể khiến reconnect thất bại. Theo dõi:

- notBefore và notAfter.
- CA chain expiry.
- Server certificate SAN.
- Client certificate identity.
- Certificate revocation policy nếu tổ chức áp dụng.
- Đồng hồ hệ thống/NTP.
- Thời gian còn lại trước expiry.

Tạo alert trước hạn đủ lâu để có thời gian phối hợp rotation và kiểm thử. Không đợi tới lúc standby down mới phát hiện certificate hết hạn.

## 37. Hạn chế quyền và bảo vệ file cấu hình

Bảo vệ:

- postgresql.conf.
- postgresql.auto.conf.
- pg_hba.conf.
- Server private key.
- Client private key.
- .pgpass/pgpass.conf.
- CA bundles.
- Backup của cấu hình.

Chỉ administrator và service account cần thiết được đọc/sửa. Không để private key trong repository, shared folder công khai hoặc artifact build không kiểm soát.

SHOW primary_conninfo có thể hiển thị connection string. Tránh đưa output có password/secret vào logs, ticket hoặc dashboard.

## 38. Logical replication khác physical replication ở đâu?

Bài này tập trung physical streaming replication, nhưng cần phân biệt:

| Đặc điểm | Physical replication | Logical replication |
| --- | --- | --- |
| Dữ liệu truyền | WAL physical changes | Logical row changes |
| Phạm vi | Cluster-level physical standby | Database/publication/subscription |
| Kết nối | Replication protocol | Replication protocol trên database cụ thể |
| Role | LOGIN + REPLICATION | LOGIN + REPLICATION cùng quyền SQL cần thiết |
| HBA database selector | replication cho physical connection | Database cụ thể của subscriber |
| Standby state | Physical standby/recovery | Subscriber áp dụng changes vào tables |
| DDL | Theo WAL physical | Không tự replicate mọi DDL như physical |

Logical replication có các yêu cầu privilege và object khác. Không copy nguyên HBA database selector replication cho subscriber mà không kiểm tra connection type/database thực tế.

## 39. Kiểm tra cấu hình role/HBA sau triển khai

### Role

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolreplication,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolconnlimit,
    rolvaliduntil
FROM pg_roles
WHERE rolname LIKE 'standby_%'
ORDER BY rolname;
~~~

### HBA parse errors

~~~sql
SELECT line_number, error
FROM pg_hba_file_rules
WHERE error IS NOT NULL;
~~~

### Standby connection

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sync_state
FROM pg_stat_replication
ORDER BY application_name;
~~~

### TLS state

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    s.ssl,
    s.version,
    s.cipher,
    s.client_dn
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s USING (pid)
WHERE a.backend_type = 'walsender';
~~~

Các query chỉ là một phần kiểm tra. Cần test từ đúng standby host và xem logs của cả hai phía.

## 40. Ví dụ cấu hình end-to-end: TLS + SCRAM

Giả sử primary:

- Hostname: primary.example.net.
- Address: 10.20.0.10.
- Port: 5432.

Standby:

- Address: 10.20.0.12.
- Role: standby_repl.

### Bước 1: Tạo role trên primary

~~~sql
CREATE ROLE standby_repl
    WITH LOGIN
         REPLICATION
         NOSUPERUSER
         NOCREATEDB
         NOCREATEROLE;

\password standby_repl
~~~

### Bước 2: Cấu hình TLS trên primary

~~~conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_min_protocol_version = 'TLSv1.2'
~~~

Certificate phải được CA tin cậy ký và SAN phải chứa primary.example.net.

### Bước 3: HBA

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256
hostnossl replication all           0.0.0.0/0      reject
hostnossl replication all           ::/0           reject
~~~

Đảm bảo rule cụ thể đứng trước reject rule và không có allow rule rộng khác.

### Bước 4: Cấu hình password file trên standby

~~~text
primary.example.net:5432:replication:standby_repl:REPLACE_WITH_SECRET
~~~

Đặt quyền file phù hợp với hệ điều hành/service account.

### Bước 5: Khởi tạo base backup

~~~bash
pg_basebackup \
  -h primary.example.net \
  -p 5432 \
  -U standby_repl \
  -D /var/lib/postgresql/data \
  -R \
  -X stream \
  -P
~~~

Đảm bảo libpq connection từ standby sử dụng sslmode=verify-full và sslrootcert trỏ tới CA phù hợp. Có thể thiết lập qua service definition hoặc connection parameters mà pg_basebackup nhận.

### Bước 6: Khởi động standby và xác minh

Trên primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state
FROM pg_stat_replication;
~~~

Kiểm tra TLS cho walsender:

~~~sql
SELECT
    a.pid,
    a.application_name,
    s.ssl,
    s.version,
    s.cipher
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s USING (pid)
WHERE a.backend_type = 'walsender';
~~~

Chỉ hoàn tất triển khai khi standby streaming, TLS được xác nhận và không có auth/TLS errors trong logs.

## 41. Ví dụ end-to-end: mutual TLS

Giả sử tổ chức có PKI riêng:

- Primary certificate do internal server CA ký.
- Standby client certificate do internal client CA ký.
- Primary tin cậy client CA.
- Standby tin cậy server CA.

Trên primary:

~~~conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_ca_file = 'client-root.crt'
~~~

HBA:

~~~conf
hostssl replication standby_repl 10.20.0.12/32 scram-sha-256 clientcert=verify-full
~~~

Trên standby, primary_conninfo có các tham số:

~~~text
host=primary.example.net
port=5432
user=standby_repl
sslmode=verify-full
sslrootcert=/etc/postgresql/certs/server-root.crt
sslcert=/etc/postgresql/certs/standby.crt
sslkey=/etc/postgresql/certs/standby.key
~~~

Có thể đặt chúng trong một connection string duy nhất trong cấu hình. Bảo đảm private key chỉ service account đọc được.

Kiểm tra client certificate được ghi nhận qua pg_stat_ssl.client_dn nếu phiên bản/cấu hình cung cấp trường đó.

## 42. Giám sát bất thường và audit

Các tín hiệu cần theo dõi:

- Nhiều authentication failures cho replication role.
- Kết nối từ source IP không nằm trong inventory.
- TLS version/cipher không đúng policy.
- Certificate sắp hết hạn.
- Standby reconnect liên tục.
- pg_stat_replication thiếu standby dự kiến.
- Replication lag tăng.
- Replication slot inactive và WAL retention tăng.
- Role có attributes thay đổi ngoài change window.
- HBA file thay đổi hoặc parse error.

Ghi lại:

- Role owner.
- Standby node mapping.
- Source IP/CIDR.
- Certificate serial/expiry.
- HBA rule line/change ticket.
- Thời điểm rotation.
- Người phê duyệt và kết quả test.

Không log password hoặc private key material.

## 43. Các lỗi bảo mật thường gặp

1. **Dùng SUPERUSER cho standby**, làm tăng hậu quả nếu credential bị lộ.
2. **Dùng một role ứng dụng cho replication**, trộn quyền không liên quan.
3. **Dùng trust authentication trên network**, cho phép kết nối không xác minh credential.
4. **Dùng host rule rộng**, vô tình cho phép cả kết nối không TLS.
5. **Đặt reject rule trước allow rule**, khiến standby không thể match rule cho phép.
6. **Dùng database name của ứng dụng trong physical replication HBA rule**, thay vì selector replication.
7. **Quên source IP thực tế sau NAT**, khiến HBA không match.
8. **Mở firewall toàn internet**, thay vì giới hạn standby subnet.
9. **Bật TLS nhưng dùng sslmode=require**, rồi cho rằng hostname/server identity đã được xác minh.
10. **Không kiểm tra SAN**, dẫn đến verify-full thất bại hoặc dùng sai hostname.
11. **Lưu password trong primary_conninfo, shell history hoặc log**, làm lộ secret.
12. **Để .pgpass có quyền đọc quá rộng**, khiến secret bị lộ.
13. **Không rotate password/certificate**, dẫn tới credential hết hạn hoặc tồn tại quá lâu.
14. **Xóa CA cũ quá sớm**, làm các standby chưa chuyển certificate bị mất kết nối.
15. **Không theo dõi replication slots**, làm WAL giữ lại và đầy disk.
16. **Tăng connection limit/worker count không tính capacity**, gây cạn connection resources.
17. **Không kiểm tra pg_hba_file_rules**, để syntax error sau thay đổi.
18. **Không kiểm tra pg_stat_ssl**, không biết replication session có TLS thật hay không.
19. **Không phân biệt physical và logical replication**, viết sai database selector trong HBA.
20. **Thu hồi role khi standby vẫn đang hoạt động**, khiến reconnect sau restart thất bại.

## 44. Bài tập thực hành có đáp án

### Bài 1. Role physical replication cần thuộc tính nào?

**Đáp án:** LOGIN và REPLICATION. Không cần SUPERUSER cho streaming replication thông thường.

### Bài 2. Tạo role replication

~~~sql
CREATE ROLE standby_repl WITH LOGIN REPLICATION NOSUPERUSER;
~~~

**Đáp án:** Tạo role có thể đăng nhập và dùng replication protocol mà không có superuser.

### Bài 3. REPLICATION có đồng nghĩa SUPERUSER không?

**Đáp án:** Không. Đây là thuộc tính riêng, cấp quyền replication protocol và các hoạt động liên quan.

### Bài 4. HBA database field cho physical replication là gì?

**Đáp án:** Từ khóa đặc biệt replication.

### Bài 5. Viết rule TLS + SCRAM cho một standby

~~~conf
hostssl replication standby_repl 10.20.0.12/32 scram-sha-256
~~~

**Đáp án:** Cho phép role từ đúng IPv4 source qua TLS và SCRAM.

### Bài 6. hostssl khác host thế nào?

**Đáp án:** hostssl chỉ match TCP connection dùng TLS; host có thể match cả TLS và không TLS.

### Bài 7. HBA dùng thứ tự nào?

**Đáp án:** Dòng đầu tiên khớp connection được chọn; authentication failure không làm PostgreSQL thử dòng kế tiếp.

### Bài 8. Vì sao reject rule rộng phải đặt sau allow rule cụ thể?

**Đáp án:** Nếu reject match trước, allow rule phía dưới không được xét.

### Bài 9. SCRAM-SHA-256 có phải mã hóa đường truyền không?

**Đáp án:** Không. SCRAM là password authentication; TLS mới bảo vệ dữ liệu trên đường truyền.

### Bài 10. sslmode=verify-full làm gì?

**Đáp án:** Mã hóa, xác minh certificate chain và kiểm tra hostname khớp certificate identity.

### Bài 11. sslmode=require có xác minh hostname không?

**Đáp án:** Không bảo đảm. Nó không tương đương verify-full.

### Bài 12. Server cần những TLS settings cơ bản nào?

**Đáp án:** ssl=on, ssl_cert_file và ssl_key_file; ssl_ca_file khi cần xác minh client certificate.

### Bài 13. primary_conninfo dùng để làm gì?

**Đáp án:** Cung cấp connection parameters để standby kết nối primary.

### Bài 14. pg_basebackup -R làm gì?

**Đáp án:** Tạo cấu hình standby, bao gồm standby.signal và connection settings theo version.

### Bài 15. Vì sao password file database field dùng replication?

**Đáp án:** Physical replication connection dùng pseudo-database selector replication trong libpq authentication.

### Bài 16. Mutual TLS là gì?

**Đáp án:** Client và server đều xác minh certificate identity của phía kia.

### Bài 17. clientcert=verify-full khác cert thế nào?

**Đáp án:** clientcert yêu cầu/xác minh client certificate nhưng có thể kết hợp password authentication; cert dùng certificate authentication làm phương thức xác thực role.

### Bài 18. pg_stat_ssl dùng để làm gì?

**Đáp án:** Kiểm tra SSL/TLS status, protocol, cipher và client certificate metadata của sessions.

### Bài 19. pg_stat_replication cho biết gì?

**Đáp án:** Các standby đang kết nối, địa chỉ, trạng thái streaming, sync state và LSN/lag metrics.

### Bài 20. max_wal_senders có vai trò gì?

**Đáp án:** Giới hạn số WAL sender processes đồng thời.

### Bài 21. max_replication_slots có vai trò gì?

**Đáp án:** Giới hạn số replication slots có thể tồn tại.

### Bài 22. Vì sao replication slot có thể làm đầy disk?

**Đáp án:** Slot giữ WAL cần thiết cho consumer; nếu consumer không tiến lên, WAL có thể tích tụ.

### Bài 23. pg_hba_file_rules dùng để làm gì?

**Đáp án:** Xem HBA rules được parse và phát hiện syntax errors.

### Bài 24. Reload pg_hba.conf bằng cách nào?

~~~sql
SELECT pg_reload_conf();
~~~

**Đáp án:** Yêu cầu PostgreSQL reload các cấu hình hỗ trợ reload, bao gồm HBA.

### Bài 25. Có nên dùng cùng role cho ứng dụng và standby?

**Đáp án:** Không nên. Tách role giúp giảm quyền và quản lý credential độc lập.

### Bài 26. Nếu certificate SAN không chứa hostname trong primary_conninfo thì sao?

**Đáp án:** verify-full thất bại vì hostname không khớp certificate identity.

### Bài 27. Khi rotate CA, nên làm gì trước?

**Đáp án:** Đưa CA mới vào trust store của clients trước khi chuyển server certificate, duy trì trust overlap theo kế hoạch.

### Bài 28. Nếu password trên primary đã đổi nhưng standby chưa cập nhật thì sao?

**Đáp án:** Kết nối mới/reconnect có thể bị password authentication failed.

### Bài 29. Physical và logical replication dùng cùng HBA database selector không?

**Đáp án:** Không mặc định. Physical replication dùng selector replication; logical subscriber kết nối tới database cụ thể.

### Bài 30. Điều kiện hoàn tất triển khai replication an toàn?

**Đáp án:** Role least privilege, HBA giới hạn đúng source, TLS verify-full hoặc mTLS theo policy, standby streaming, pg_stat_ssl xác nhận TLS, logs sạch và monitoring/rotation đã sẵn sàng.

## 45. Checklist vận hành

- [ ] Dùng role riêng có LOGIN và REPLICATION.
- [ ] Không cấp SUPERUSER cho standby nếu không có lý do quản trị riêng.
- [ ] Tắt CREATEDB/CREATEROLE cho role replication.
- [ ] Đặt connection limit phù hợp topology.
- [ ] Lập inventory role, standby, source IP và owner.
- [ ] Dùng database selector replication cho physical HBA rule.
- [ ] Chỉ allow source IP/CIDR cần thiết.
- [ ] Đặt HBA allow rule cụ thể trước reject rule rộng.
- [ ] Bắt buộc TLS bằng hostssl.
- [ ] Reject replication connections không mã hóa.
- [ ] Dùng SCRAM-SHA-256 hoặc certificate authentication.
- [ ] Không dùng trust trên network.
- [ ] Cấu hình server certificate/key đúng.
- [ ] Bảo vệ private key bằng file permissions/ACL.
- [ ] Đảm bảo server certificate SAN khớp hostname.
- [ ] Dùng sslmode=verify-full trên standby.
- [ ] Cấu hình sslrootcert đúng CA.
- [ ] Dùng client certificate nếu policy yêu cầu mTLS.
- [ ] Bảo vệ .pgpass/secret store và không log password.
- [ ] Kiểm tra listen_addresses và firewall.
- [ ] Cấu hình max_wal_senders/max_replication_slots theo capacity.
- [ ] Theo dõi replication slots và WAL retention.
- [ ] Kiểm tra HBA parse errors trước/sau reload.
- [ ] Kiểm tra pg_stat_replication và pg_stat_ssl.
- [ ] Lên lịch password/certificate rotation.
- [ ] Test reconnect sau rotation và restart.
- [ ] Giữ CA overlap trong quá trình chuyển đổi.
- [ ] Có runbook khi authentication/TLS/replication failure.
- [ ] Phân biệt physical và logical replication trong HBA.
- [ ] Không mở traffic production trước khi xác minh streaming và TLS.

## 46. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — role attributes và quyền.
- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html) — LOGIN, REPLICATION, CONNECTION LIMIT và VALID UNTIL.
- [ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html) — thay đổi role attributes và password.
- [The pg_hba.conf File](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html) — HBA rule syntax, order và authentication methods.
- [Password Authentication](https://www.postgresql.org/docs/current/auth-password.html) — SCRAM và password methods.
- [Client Certificate Authentication](https://www.postgresql.org/docs/current/auth-cert.html) — cert và clientcert options.
- [SSL Support](https://www.postgresql.org/docs/current/ssl-tcp.html) — TLS server configuration, certificates và client verification.
- [libpq Connection Parameters](https://www.postgresql.org/docs/current/libpq-connect.html) — sslmode, sslrootcert, sslcert và sslkey.
- [The Password File](https://www.postgresql.org/docs/current/libpq-pgpass.html) — password file và replication connection entry.
- [Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html) — physical streaming replication.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — tạo physical base backup và standby configuration.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — wal_level, WAL senders, slots và related settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_replication, pg_stat_ssl và pg_stat_activity.
- [System View pg_hba_file_rules](https://www.postgresql.org/docs/current/view-pg-hba-file-rules.html) — kiểm tra HBA parsing.
- [Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS) — slot behavior và WAL retention.

Các URL /current/ trỏ tới tài liệu PostgreSQL hiện hành. Một số option, authentication behavior, TLS protocol defaults và view columns có thể khác giữa major versions; kiểm tra tài liệu cùng version server/client trước khi triển khai.

## 47. Tổng kết

**Bảo vệ physical replication cần xác thực đúng role, giới hạn đúng nguồn và mã hóa/xác minh kết nối bằng TLS.** Ba lớp phải được cấu hình nhất quán và kiểm tra sau mỗi thay đổi.

1. **Role chuyên dụng cần LOGIN và REPLICATION.** Không dùng superuser cho streaming replication thông thường.
2. **Physical replication HBA dùng database selector replication.** Giới hạn user và source CIDR cụ thể.
3. **HBA dùng first-match semantics.** Rule allow cụ thể phải đứng trước rule reject rộng.
4. **SCRAM xác thực password; TLS bảo vệ đường truyền.** Hai cơ chế giải quyết hai mục tiêu khác nhau.
5. **sslmode=verify-full xác minh cả CA và hostname.** Chỉ require không đủ để xác minh server identity.
6. **mTLS có thể xác minh client certificate.** Phân biệt clientcert verification với cert authentication.
7. **Firewall, listen_addresses và HBA bổ sung cho nhau.** Không mở PostgreSQL tới mọi nguồn.
8. **Password file và private keys phải được bảo vệ.** Không lưu secret trong source control hoặc logs.
9. **Replication slots cần monitoring.** Consumer ngừng tiến có thể giữ WAL và làm đầy disk.
10. **pg_stat_replication và pg_stat_ssl giúp xác minh topology và TLS.**
11. **Rotation phải có overlap và kiểm thử reconnect.** Đổi password/certificate thiếu phối hợp có thể làm standby ngừng stream.
12. **Logical replication có connection/database semantics khác physical replication.** Viết HBA rule đúng loại kết nối.

Khi role, HBA, TLS, network và monitoring được triển khai cùng nhau, PostgreSQL có thể duy trì physical standby qua kết nối được xác thực, mã hóa và giới hạn theo đúng topology.

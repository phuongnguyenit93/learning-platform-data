# TLS, chứng chỉ và xác minh danh tính máy chủ trong PostgreSQL

Một ứng dụng Java kết nối PostgreSQL qua mạng để đọc dữ liệu khách hàng, nhận thông tin thanh toán hoặc thực hiện giao dịch. Nếu không bảo vệ kết nối đúng cách, dữ liệu truy vấn, kết quả và thông tin xác thực có thể bị quan sát hoặc can thiệp trên đường truyền. **TLS (Transport Layer Security)** là lớp bảo vệ phổ biến giữa client và PostgreSQL server.

Tuy nhiên, chỉ “bật SSL” hoặc thấy kết nối có mã hóa **chưa đủ**. Client còn cần biết nó đang nói chuyện với **đúng máy chủ PostgreSQL được tin cậy**, chứ không phải một endpoint giả mạo có khả năng làm trung gian (*man-in-the-middle*, MITM).

~~~text
Ứng dụng Java / psql                              PostgreSQL server
       |                                                 |
       |---- Kết nối TCP và đề nghị dùng TLS ----------->|
       |<--- Thỏa thuận thiết lập TLS -------------------|
       |                                                 |
       |<--- Chứng chỉ máy chủ và chuỗi trung gian -------|
       |                                                 |
       |    Client kiểm tra:
       |    1. Chuỗi chứng chỉ dẫn tới CA tin cậy?
       |    2. Chứng chỉ còn hiệu lực và hợp mục đích?
       |    3. Tên DNS/IP của server có khớp SAN?
       |                                                 |
       |==== Kênh TLS mã hóa, xác thực máy chủ ==========|
       |                                                 |
       |---- Xác thực PostgreSQL (ví dụ SCRAM) --------->|
       |<--- Thành công / thất bại ----------------------|
       |                                                 |
       |==== Trao đổi truy vấn, kết quả qua kênh TLS ====|
~~~

Ví dụ kết nối chủ động xác minh máy chủ bằng công cụ `psql`:

~~~bash
psql "host=db.example.internal port=5432 dbname=appdb user=app_user sslmode=verify-full sslrootcert=/etc/postgresql/client/ca.crt"
~~~

Với chế độ `verify-full`, client không chỉ yêu cầu mã hóa mà còn kiểm tra chuỗi chứng chỉ có nguồn tin cậy và tên server được kết nối có khớp danh tính trong chứng chỉ. Nếu không thỏa điều kiện, **kết nối phải thất bại thay vì âm thầm hạ xuống mức không an toàn**.

> **Phạm vi:** Bài tập trung vào PostgreSQL, `libpq`/`psql` và PostgreSQL JDBC Driver (PGJDBC). Một số đường dẫn, tham số và khả năng hỗ trợ phụ thuộc phiên bản PostgreSQL, OpenSSL, driver, hệ điều hành và nhà cung cấp dịch vụ. Những đoạn triển khai chứng chỉ chỉ dành cho **lab**; trong production cần tuân theo PKI và quy trình quản trị khóa của tổ chức.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **mã hóa**, **xác thực máy chủ** và **xác thực người dùng**.
2. Giải thích TLS handshake, public/private keys, chứng chỉ X.509, CA và chuỗi chứng chỉ.
3. Hiểu các trường **Subject Alternative Name (SAN)**, tên DNS/IP, thời hạn hiệu lực và trust anchor.
4. So sánh sáu chế độ `sslmode`: `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full`.
5. Giải thích tại sao `sslmode=require` không thay thế mặc định cho xác thực hostname.
6. Tạo/đọc chứng chỉ thử nghiệm từ một CA nội bộ, có SAN phù hợp.
7. Cấu hình PostgreSQL server với `ssl=on`, `ssl_cert_file`, `ssl_key_file` và phiên bản TLS tối thiểu.
8. Phân biệt cấu hình chứng chỉ **server** với CA để PostgreSQL xác minh chứng chỉ **client**.
9. Sử dụng `pg_hba.conf` và `hostssl` để giới hạn kết nối mạng không mã hóa.
10. Kết nối qua `psql` và JDBC với `sslmode=verify-full` cùng CA tin cậy.
11. Kiểm tra kênh hiện tại bằng `pg_stat_ssl`; biết giới hạn của việc quan sát từ phía server.
12. Nhận diện lỗi certificate expired, untrusted CA, hostname mismatch, thiếu intermediate và quyền file khóa.
13. Thiết kế quy trình luân chuyển/thu hồi chứng chỉ, monitoring hết hạn và điều tra sự cố.
14. Biết khi nào cần **mutual TLS (mTLS)** và cách nó khác xác thực password/SCRAM.

## 2. Ba câu hỏi bảo mật khác nhau

Một kết nối PostgreSQL an toàn cần trả lời những câu hỏi riêng biệt.

### 2.1. Dữ liệu truyền đi có bị đọc trộm không?

**Mã hóa đường truyền:** TLS cung cấp bảo mật dữ liệu giữa hai endpoint của phiên TLS, chống việc một người nghe lén trên đường mạng đọc được bản rõ.

### 2.2. Client có kết nối đúng server không?

**Xác thực danh tính máy chủ:** client kiểm tra chứng chỉ server có được CA tin cậy ký và tên máy yêu cầu có khớp chứng chỉ. Đây là lý do `verify-full` quan trọng.

### 2.3. Ai được đăng nhập database?

**Xác thực người dùng PostgreSQL:** server xác minh role/client bằng phương thức từ `pg_hba.conf`, ví dụ `scram-sha-256`, certificate authentication hoặc cơ chế phù hợp khác.

| Lớp bảo vệ | Trả lời | Ví dụ |
| --- | --- | --- |
| TLS encryption | Có bị nghe lén trên đoạn mạng này? | TLS 1.3 với bộ mã phù hợp |
| Server certificate verification | Có phải server đúng tên và được CA tin cậy xác nhận? | `sslmode=verify-full` |
| PostgreSQL authentication | Client có quyền đăng nhập với user đã khai báo? | `scram-sha-256` |
| Database authorization | User được phép truy cập bảng/hàm nào? | `GRANT`, role, RLS |
| Application authorization | Người dùng cuối có quyền với tài nguyên nào? | Tenant/ownership/business ACL |

### 2.4. TLS không thay thế quyền SQL

Dù kết nối đã dùng TLS và server được xác minh đúng, một role có `SELECT` trên bảng nhạy cảm vẫn có thể đọc bảng ấy. Phải phân quyền tối thiểu ở PostgreSQL và ứng dụng.

### 2.5. Password không tự chứng minh server đúng

Ứng dụng có thể xác thực bằng SCRAM với một endpoint mà nó tưởng là server thật. Nếu không xác minh danh tính endpoint TLS, một kẻ tấn công có thể gây nhiễu, chuyển tiếp hoặc tấn công những cơ chế/luồng ứng dụng khác. **Xác thực máy chủ phải là bước chủ động của client.**

## 3. TLS giải quyết mối đe dọa nào?

Giả sử app và database chạy ở hai máy khác nhau:

~~~text
App host ---- switch/router/proxy ---- DB host
~~~

Đường mạng có thể đi qua nhiều hệ thống bạn không trực tiếp quản lý. TLS bảo vệ khỏi:

- **Nghe lén:** quan sát dữ liệu query/response và trao đổi xác thực có nguy cơ lộ thông tin.
- **Can thiệp trên đường truyền:** kẻ trung gian thay đổi gói tin và giả mạo thông điệp.
- **Giả mạo server** khi client *thực sự* xác minh CA và hostname.

### 3.1. TLS không giải quyết mọi mối đe dọa

TLS không ngăn:

- Ứng dụng hoặc database host đã bị chiếm quyền.
- SQL injection trong câu SQL không được parameterize.
- Role database bị cấp quá nhiều quyền.
- Log ứng dụng vô tình ghi password hoặc dữ liệu nhạy cảm.
- Proxy kết thúc TLS rồi chuyển tiếp bản rõ ở đoạn mạng phía sau.
- CA tin cậy sai hoặc khóa riêng của server bị lộ.

### 3.2. Mã hóa một đoạn mạng không đồng nghĩa end-to-end

~~~text
Client ==TLS==> Proxy ----plaintext----> PostgreSQL
~~~

Ở mô hình này, TLS kết thúc tại proxy. Nếu đoạn proxy → PostgreSQL không có lớp bảo vệ riêng, dữ liệu có thể xuất hiện dạng rõ trên đoạn đó. Phải xác định **endpoint TLS thực sự là ai** và đánh giá từng hop.

### 3.3. MITM khi không xác minh server

~~~text
Client === TLS === Attacker === TLS === DB thật
~~~

Một bên trung gian có thể trình bày chứng chỉ do chính họ tạo. Nếu client chỉ kiểm tra “có TLS” mà không kiểm tra đúng CA/hostname, việc mã hóa riêng từng đoạn **không bảo đảm client nói chuyện trực tiếp với DB thật**.

## 4. Chứng chỉ X.509 gồm những gì?

TLS server certificate chứa một khóa công khai và các thông tin nhận dạng, được ký bởi CA hoặc theo một chuỗi tin cậy.

| Thành phần | Vai trò |
| --- | --- |
| Public key | Khóa công khai được công bố trong chứng chỉ |
| Private key | Bí mật do endpoint sở hữu, không gửi cho client |
| Subject | Thông tin định danh trong certificate |
| Subject Alternative Name (SAN) | Danh sách tên DNS/IP mà certificate có thể đại diện |
| Issuer | Bên phát hành/ký certificate |
| Validity (`notBefore`/`notAfter`) | Khoảng thời gian chứng chỉ hợp lệ |
| Signature | Cho phép xác minh chứng chỉ được bên phát hành ký |
| Basic Constraints | Phân biệt vai trò CA với end-entity trong PKI |
| Key Usage / Extended Key Usage | Giới hạn mục đích sử dụng key/certificate |
| Serial number | Định danh certificate trong phạm vi issuer, phục vụ quản lý/thu hồi |

### 4.1. Public key khác private key

Certificate server thường được chia sẻ với client, nhưng **private key phải được giữ bí mật** trên server hoặc kho khóa thích hợp. Lộ private key có thể cho phép kẻ tấn công giả mạo endpoint nếu các điều kiện tin cậy khác cho phép.

### 4.2. Không gửi private key cho client để “xác thực server”

Client cần **CA certificate** hoặc trust anchor phù hợp để kiểm tra server; không cần nhận private key của server.

### 4.3. Certificate có thể hợp lệ về định dạng nhưng không được tin cậy

Một certificate tự ký bất kỳ cũng có thể mã hóa TLS. Nhưng nếu CA của nó không nằm trong trust store đã được cấp đúng, client dùng `verify-full` cần **từ chối**.

## 5. CA, intermediate CA và chuỗi tin cậy

Trong PKI, server certificate thường được cấp bởi một intermediate CA; intermediate lại được cấp bởi root CA.

~~~text
Root CA (trust anchor của client)
        |
        v
Intermediate CA
        |
        v
Server certificate: db.example.internal
        |
        v
Server private key (bí mật tại server)
~~~

### 5.1. Root CA là mốc tin cậy

Client cần tin tưởng root CA (hoặc trust anchor được cấu hình phù hợp). Không phải cứ certificate “được ký” là đáng tin; nó phải có chuỗi hợp lệ **dẫn về một trust anchor được client chấp nhận**.

### 5.2. Intermediate phải được cung cấp đúng

Nếu server chỉ gửi leaf certificate và client không có intermediate phù hợp, quá trình xây chuỗi có thể thất bại dù root CA đã được tin cậy.

### 5.3. CA nội bộ và CA công cộng

- **CA nội bộ:** phù hợp nhiều database chỉ hoạt động trong mạng doanh nghiệp; cần phân phối CA certificate an toàn tới clients.
- **CA công cộng:** có thể phù hợp với tên DNS hợp lệ và mô hình phát hành tương ứng; client có thể dùng trust store hệ thống khi driver hỗ trợ và được cấu hình đúng.

### 5.4. Không dùng tùy tiện CA công cộng cho mọi database

Nhiều DB dùng tên nội bộ hoặc private endpoints; certificate issuance phải tuân chính sách PKI và quy tắc xác thực tên. Việc dùng CA nội bộ không có nghĩa kém an toàn nếu cấp phát, lưu giữ khóa, phân phối trust anchor và rotation được quản trị tốt.

### 5.5. Không sao chép khóa CA lên database server

Server cần private key của chính endpoint TLS; **root CA private key** nên được giữ tách biệt trong hệ thống phát hành chứng chỉ. Nếu root CA key bị đánh cắp, rủi ro lan rộng tới nhiều server.

## 6. SAN: xác minh tên máy chủ

Client muốn kết nối:

~~~text
db.example.internal:5432
~~~

Certificate server nên có SAN kiểu:

~~~text
DNS:db.example.internal
~~~

### 6.1. Tên kết nối phải khớp tên chứng chỉ

Với `sslmode=verify-full`, libpq kiểm tra hostname được yêu cầu theo quy tắc xác minh tên. Nếu client dùng `db-read.example.internal` mà certificate chỉ có `db-write.example.internal`, xác minh có thể thất bại.

### 6.2. SAN được ưu tiên

Với chứng chỉ hiện đại, đặt tên DNS vào `subjectAltName`; đừng dựa vào CN để thay SAN. Một số phiên bản client vẫn có khả năng fallback về common name theo quy tắc riêng, nhưng **không nên thiết kế PKI mới dựa trên fallback này**.

### 6.3. Kết nối qua địa chỉ IP

Nếu client dùng:

~~~bash
psql "host=192.0.2.10 dbname=appdb sslmode=verify-full ..."
~~~

certificate cần danh tính IP phù hợp theo cơ chế client; thông thường sử dụng SAN loại `IP:192.0.2.10`, không phải chỉ thêm chuỗi IP như một DNS SAN.

### 6.4. Hostname alias và DNS failover

Nếu ứng dụng kết nối qua tên ổn định `db.service.internal` trỏ tới một backend có thể thay đổi, certificate được trình bày ở TLS endpoint cần có tên đó. Trường hợp nhiều hosts/failover, **mỗi endpoint được chọn phải có danh tính phù hợp tên mà client xác minh**.

### 6.5. Chỉ đổi DNS không giải quyết certificate mismatch

Đổi DNS để tên A trỏ tới server B không làm certificate B tự có SAN tên A. Cần cấp phát/chọn certificate khớp mô hình tên truy cập thực.

## 7. Handshake PostgreSQL và TLS

Trong cơ chế PostgreSQL thông thường qua TCP, client liên hệ server và thương lượng sử dụng TLS trước khi gửi thông tin phiên ứng dụng.

~~~text
Client                           Server
  |---- Kết nối TCP -------------->|
  |---- Yêu cầu SSL/TLS ---------->|
  |<--- Hỗ trợ / không hỗ trợ -----|
  |---- TLS ClientHello --------->|
  |<--- TLS ServerHello, cert ----|
  |---- Kiểm tra chain và SAN ----|
  |<=== TLS session keys ========>|
  |---- PostgreSQL startup ------>|
  |<--- Authentication ----------|
  |---- Thông tin xác thực ------>|
  |<--- ReadyForQuery -----------|
~~~

Đây là sơ đồ logic; các phiên bản mới có thể hỗ trợ dạng thương lượng TLS trực tiếp với tùy chọn tương ứng. Tham số cụ thể như `sslnegotiation` phải được dùng theo khả năng phiên bản `libpq`/server, không giả định mọi bản đều hỗ trợ giống nhau.

### 7.1. TLS có handshake và kiểm chứng trước SQL

Nếu CA hoặc tên server không hợp lệ và client dùng chế độ xác minh nghiêm ngặt, phiên phải thất bại **trước khi trở thành một kết nối PostgreSQL được chấp nhận để chạy SQL**.

### 7.2. GSS encryption là nhánh khác

Trong một số môi trường hỗ trợ GSSAPI encryption, libpq có thể chọn GSS encryption thay vì TLS theo cấu hình và ưu tiên. Nếu yêu cầu kiểm chứng **TLS/X.509 cụ thể**, cần kiểm tra `gssencmode` và khả năng của client; không kết luận chỉ từ `sslmode` rằng kết nối chắc chắn đã dùng TLS.

### 7.3. TLS không tự xác thực user database

Sau handshake TLS, PostgreSQL vẫn sử dụng quy tắc `pg_hba.conf` để quyết định phương thức xác thực user, trừ khi chính sách chọn certificate authentication hoặc cơ chế khác.

## 8. Sáu chế độ sslmode của libpq

`sslmode` là tham số kết nối quan trọng khi ứng dụng yêu cầu PostgreSQL bảo vệ đường truyền.

| `sslmode` | Hành vi chính | Kiểm tra CA? | Kiểm tra hostname? |
| --- | --- | --- | --- |
| `disable` | Không đề nghị TLS | Không | Không |
| `allow` | Thử không TLS trước, có thể thử TLS | Không theo chế độ này | Không |
| `prefer` | Thử TLS trước, có thể fallback không TLS | Không theo chế độ này | Không |
| `require` | Bắt buộc có TLS | Thông thường không; có tương thích lịch sử với root.crt | Không xác minh tên như verify-full |
| `verify-ca` | Bắt buộc TLS; kiểm tra chuỗi CA | Có | Không |
| `verify-full` | Bắt buộc TLS; kiểm tra CA và tên máy | Có | Có |

**Khuyến nghị:** với TCP tới PostgreSQL trong production, ưu tiên `sslmode=verify-full` và cấu hình trust anchor đúng.

### 8.1. disable

~~~bash
psql "host=db.example.internal dbname=appdb sslmode=disable"
~~~

Không dùng TLS. Chỉ phù hợp tình huống được chấp thuận riêng; không sử dụng cho đường mạng chứa dữ liệu nhạy cảm.

### 8.2. allow

Client có thể thử kết nối không mã hóa trước, rồi dùng TLS theo quy tắc fallback. Mô hình này không phù hợp yêu cầu *encryption required*.

### 8.3. prefer

Là mặc định thông dụng của libpq khi kết nối TCP, nhưng cho phép fallback nếu server không dùng TLS. Nó ưu tiên tiện dụng và tương thích, **không phải chính sách bắt buộc bảo mật**.

### 8.4. require

`require` ngăn kết nối plaintext trong luồng SSL bình thường nhưng **không đồng nghĩa mặc định đã xác minh đúng hostname**. Trong libpq có hành vi tương thích ngược: nếu phát hiện tệp CA gốc ở vị trí mặc định hoặc thiết lập tương ứng, `require` có thể hành xử giống `verify-ca` ở một số trường hợp. Vì sự khác biệt này, đừng dùng `require` làm chứng cứ bảo đảm xác thực máy chủ.

### 8.5. verify-ca

Client xác minh server certificate dẫn về CA được tin cậy. Nhưng nếu cùng CA cấp chứng chỉ cho hai máy `db-a.internal` và `db-b.internal`, chỉ kiểm tra CA có thể **không ngăn việc kết nối nhầm máy**, vì tên đích chưa được kiểm tra.

### 8.6. verify-full

Kết hợp **bắt buộc TLS + chứng chỉ CA hợp lệ + đúng tên DNS/IP**. Đây là mức nên chọn khi client đã biết endpoint mong đợi.

## 9. Vì sao prefer và require chưa đủ để chống MITM?

Giả sử client yêu cầu `db-prod.internal`.

### 9.1. Với prefer

Nếu TLS không khả dụng hoặc hành vi thương lượng bị can thiệp theo một đường yếu, client có thể rơi về kết nối không TLS. Điều này mâu thuẫn yêu cầu “không plaintext”.

### 9.2. Với require

Kết nối có TLS nhưng client không nhất thiết xác minh **chính danh tính của db-prod.internal**. Một endpoint giả mạo có certificate riêng có thể vẫn hoàn tất TLS nếu chính sách không kiểm tra chain/hostname phù hợp.

### 9.3. Với verify-ca

CA tin cậy chưa đủ để biết đó là **đúng tên máy**. Khi CA đã cấp certificate cho nhiều server, cần chống việc dùng certificate hợp lệ của máy khác.

### 9.4. Với verify-full

Certificate phải thỏa đồng thời các điều kiện về trust chain và tên endpoint. Khi một trong hai sai, client sẽ từ chối.

### 9.5. Xác minh vẫn phụ thuộc trust store được quản lý đúng

Nếu client tin một CA không phù hợp, hoặc CA nội bộ bị xâm phạm và cấp certificate sai, việc verify-full không có phép màu để cứu toàn bộ PKI. Cần kiểm soát quy trình cấp phát, phân phối CA, bảo vệ private keys và thu hồi.

## 10. Cấu hình kết nối với libpq và psql

Một câu lệnh thực tế:

~~~bash
psql "host=db.example.internal port=5432 dbname=appdb user=app_user sslmode=verify-full sslrootcert=/etc/postgresql/client/ca.crt"
~~~

### 10.1. sslrootcert là certificate CA tin cậy

`sslrootcert` chỉ đường dẫn tệp CA/trust anchor mà client dùng để xác minh **server certificate**.

Đây không phải private key server, không phải một token đăng nhập và cũng không phải mật khẩu database.

### 10.2. sslcert và sslkey là chứng chỉ client

`sslcert` và `sslkey` dùng khi **client cần trình bày certificate của chính mình**, chẳng hạn với mTLS. Chúng không thay vai trò `sslrootcert` trong kiểm tra server.

### 10.3. Không lưu password trên command line

Tránh viết:

~~~bash
# Không khuyến nghị:
# psql "host=... user=... password=very_secret ..."
~~~

vì password có thể xuất hiện trong shell history, thông tin tiến trình hoặc nhật ký. Có thể dùng prompt, file mật khẩu được bảo vệ như `.pgpass`, secret manager hoặc cơ chế xác thực thích hợp.

### 10.4. Đường dẫn CA phụ thuộc hệ điều hành

libpq có mặc định tìm các tệp trong thư mục cấu hình PostgreSQL của người dùng (ví dụ `~/.postgresql/root.crt` trên hệ Unix). Trên Windows, đường dẫn và cơ chế sử dụng khác theo client. Để môi trường deploy có thể tái lập, dùng `sslrootcert` tường minh theo hướng dẫn của phiên bản driver.

### 10.5. Không dựa vào kết nối qua Unix socket

Khi dùng Unix-domain socket trên cùng máy, TLS là cơ chế dành cho kết nối TCP; `sslmode` không có cùng ý nghĩa. Muốn kiểm thử TLS, chỉ rõ `host` là tên/địa chỉ TCP và xác minh bằng `pg_stat_ssl`.

## 11. Phân biệt host, hostaddr và certificate name

libpq có thể nhận cả:

~~~text
host=db.example.internal
hostaddr=192.0.2.10
~~~

### 11.1. host

Tên logic của server, quan trọng cho lựa chọn endpoint và **kiểm tra hostname** trong `verify-full`.

### 11.2. hostaddr

Địa chỉ mạng để kết nối TCP mà không cần phân giải tên theo cơ chế thông thường. Có thể hữu ích cho route đặc biệt hoặc debug.

### 11.3. Trường hợp kết hợp

~~~bash
psql "host=db.example.internal hostaddr=192.0.2.10 port=5432 dbname=appdb sslmode=verify-full sslrootcert=/etc/postgresql/client/ca.crt"
~~~

Khi cung cấp cả hai, libpq có thể dùng `hostaddr` để tạo TCP connection nhưng vẫn dùng tên `host` cho các bước liên quan tới danh tính (bao gồm kiểm tra hostname) theo quy tắc client. Đây có thể là công cụ kiểm thử khi DNS hay tunnel phức tạp; không dùng để âm thầm chuyển production sang endpoint không được quản trị.

### 11.4. Không dùng hostaddr đơn lẻ để giả vờ certificate DNS khớp

Nếu chỉ dùng IP và certificate không có danh tính IP phù hợp, `verify-full` có thể thất bại. Đó là kết quả bảo vệ mong muốn, không phải lỗi cần khắc phục bằng `sslmode=require`.

### 11.5. Multi-host và failover

Nếu connection string có nhiều hosts, mỗi server có thể trình bày certificate khác nhau. Cần cấp chứng chỉ hợp lệ cho từng tên endpoint có thể được chọn; đừng xác minh một host rồi tự suy mọi host trong danh sách đều đáng tin.

## 12. Cấu hình TLS phía PostgreSQL server

Những cấu hình điển hình trong `postgresql.conf`:

~~~conf
# Chỉ là ví dụ: đường dẫn phụ thuộc hệ điều hành/packaging.
ssl = on
ssl_cert_file = '/etc/postgresql/tls/server.crt'
ssl_key_file  = '/etc/postgresql/tls/server.key'
ssl_min_protocol_version = 'TLSv1.2'
~~~

### 12.1. ssl = on

Cho phép PostgreSQL nhận kết nối TLS khi build/server có hỗ trợ. Nó **không tự bắt mọi client phải dùng TLS**; chính sách client và `pg_hba.conf` cần được cấu hình phù hợp.

### 12.2. ssl_cert_file

Tệp certificate server. Nếu cần intermediate certificates, cần tổ chức chain PEM đúng theo tài liệu/PKI. Không gửi private key của CA trong tệp này.

### 12.3. ssl_key_file

Private key server. Quyền đọc phải được hạn chế cho tài khoản chạy PostgreSQL hoặc cơ chế quản lý key được chấp thuận.

### 12.4. ssl_min_protocol_version

Đặt phiên bản tối thiểu theo chính sách bảo mật tổ chức và tương thích client. TLS 1.2 là một ngưỡng phổ biến; TLS 1.3 được ưu tiên khi hai bên hỗ trợ. Đừng bật những phiên bản giao thức cũ chỉ để một client lỗi thời kết nối được mà không đánh giá rủi ro.

### 12.5. Các tham số cipher

PostgreSQL cũng có các tham số như `ssl_ciphers`, nhưng cách kiểm soát cipher suites phụ thuộc phiên bản TLS/OpenSSL: tùy chọn cho TLS 1.2 không nhất thiết điều khiển TLS 1.3 giống hệt. Đo thực tế qua `pg_stat_ssl` và chính sách crypto thay vì suy toàn bộ từ một dòng config.

### 12.6. Không lưu private key trong source repository

Certificate public và private key không có cùng mức nhạy cảm. Không commit `server.key`, CA private key hoặc mật khẩu khóa vào git, image công khai, log hoặc tài liệu chia sẻ.

## 13. Quyền file private key

Trên hệ Unix, ví dụ dùng một tài khoản chạy PostgreSQL có quyền hợp lệ:

~~~bash
# Minh họa trên máy chủ do DBA quản lý.
chown postgres:postgres /etc/postgresql/tls/server.key
chmod 0600 /etc/postgresql/tls/server.key
~~~

### 13.1. Vì sao quyền 0600?

Private key nên chỉ được tài khoản dịch vụ phù hợp đọc. PostgreSQL có kiểm tra quyền bảo vệ key trên nhiều hệ thống; cấu hình file quá rộng có thể khiến server từ chối khởi động hoặc nạp chứng chỉ.

### 13.2. Các môi trường có phương án quyền khác

Một số packaging cho phép key thuộc root với quyền nhóm nhất định theo quy tắc được hỗ trợ; trên Windows là ACL chứ không phải `chmod`. Hãy theo hướng dẫn của PostgreSQL và môi trường cụ thể, không sao chép lệnh trên vào máy không có role/đường dẫn ấy.

### 13.3. Container và secret mount

Khi chạy PostgreSQL trong container/Kubernetes, có thể mount secret theo đường dẫn riêng. Phải đảm bảo UID/GID, quyền và lifecycle của secret phù hợp tiến trình PostgreSQL; không chuyển mọi secret sang biến môi trường hoặc copy khóa vào image chỉ để tránh lỗi permission.

### 13.4. Backup và private key

Backup chứa private key phải được bảo vệ như dữ liệu bí mật; nếu key bị lộ, chỉ khôi phục file không đủ — cần thực hiện rotation/revocation theo quy trình PKI.

## 14. ssl_ca_file phía server dùng để làm gì?

Đây là điểm thường gây nhầm:

~~~conf
ssl_ca_file = '/etc/postgresql/tls/client-ca.crt'
~~~

### 14.1. CA của server không phải CA mà client tự động tin

Khi cấu hình `ssl_ca_file` ở PostgreSQL server, nó chủ yếu cung cấp trust anchor để **server kiểm tra client certificates** trong các cơ chế xác thực certificate liên quan.

### 14.2. Client vẫn phải có trust anchor riêng

Client dùng `sslmode=verify-full` phải có CA hoặc trust store hợp lệ **ở phía client** — ví dụ qua `sslrootcert`. Việc đặt CA lên server không tự gửi một “cam kết tin cậy” đến tất cả clients.

### 14.3. Chỉ server certificate verification không cần client cert

Nếu app dùng password/SCRAM và chỉ cần xác minh server, client không nhất thiết phải có `sslcert`/`sslkey`. Server cũng không bắt buộc phải yêu cầu client certificate.

### 14.4. mTLS mới cần chính sách client certificate

Khi server phải xác minh chứng chỉ client, cần CA phía server và quy tắc `pg_hba.conf` tương ứng. Sẽ có phần riêng.

## 15. pg_hba.conf: bắt buộc TLS ở phía server

`sslmode=verify-full` là chính sách của client. Để ngăn một client tự ý kết nối plaintext, server cần chính sách chấp nhận kết nối phù hợp, trong đó `hostssl` là cơ chế quan trọng.

Ví dụ chỉ chấp nhận mạng ứng dụng:

~~~conf
# Ví dụ các dòng trong pg_hba.conf; điều chỉnh CIDR và role thật.
hostssl appdb app_user 10.20.0.0/16 scram-sha-256

# Từ chối các TCP connections không TLS.
hostnossl all all 0.0.0.0/0 reject
hostnossl all all ::/0      reject
~~~

### 15.1. hostssl

Dòng `hostssl` chỉ match kết nối TCP có TLS, và còn lọc database/user/address. Nó không tự cấp quyền nếu phương thức authentication thất bại.

### 15.2. hostnossl

Dòng `hostnossl` match kết nối TCP không TLS. Dòng `reject` giúp thể hiện rõ chính sách không plaintext.

### 15.3. Thứ tự dòng rất quan trọng

`pg_hba.conf` được xét theo thứ tự. Một dòng `host all all ...` rộng hơn nằm trước có thể làm client match quy tắc khác với chính sách bạn dự định. Phải đọc **toàn bộ thứ tự những dòng liên quan** trong cấu hình thực tế.

### 15.4. Đừng quên IPv6

Nếu ứng dụng hoặc server có IPv6, một chính sách chỉ từ chối `0.0.0.0/0` cho IPv4 có thể không bao phủ mọi đường IPv6. Kiểm tra các rule tương ứng.

### 15.5. Ngay cả hostssl vẫn chưa bắt client verify-full

Server có thể biết kết nối đang dùng TLS. Server **không biết một cách đáng tin cậy** client có xác minh hostname/CA đúng chính sách của chính client hay không. Vì vậy vẫn phải buộc cấu hình app/JDBC sử dụng `verify-full`.

## 16. TLS và phương thức xác thực SCRAM

Một ví dụ:

~~~conf
hostssl appdb app_user 10.20.0.0/16 scram-sha-256
~~~

### 16.1. Hai lớp độc lập

- `hostssl`: kết nối phải dùng TLS để match rule.
- `scram-sha-256`: server sử dụng cơ chế xác thực dựa trên mật khẩu SCRAM.

### 16.2. SCRAM không thay TLS

SCRAM giảm một số rủi ro của xác thực mật khẩu so với cơ chế cũ, nhưng không tự mã hóa toàn bộ SQL và kết quả. TLS vẫn cần để bảo vệ kênh dữ liệu.

### 16.3. TLS không thay SCRAM

Một client có thể kết nối tới đúng server qua TLS nhưng bị từ chối vì mật khẩu/role sai. Đó là hành vi xác thực người dùng đúng.

### 16.4. Channel binding bổ sung lớp ràng buộc

Một số phiên bản client/server hỗ trợ SCRAM channel binding để liên kết xác thực với kênh TLS đã thiết lập. Trong libpq có tham số `channel_binding` với các lựa chọn như `disable`, `prefer` và `require`.

### 16.5. Channel binding không thay verify-full

Channel binding là cơ chế bổ sung chống một số kiểu relay/MITM khi cấu hình và phía server hỗ trợ phù hợp. Nó **không phải lý do bỏ xác minh CA/hostname** trong `verify-full`.

## 17. Kiểm tra kết nối có TLS bằng pg_stat_ssl

Sau khi đăng nhập thành công:

~~~sql
SELECT
    pid,
    ssl,
    version,
    cipher,
    bits
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
~~~

### 17.1. ssl

Nếu `ssl=true`, backend hiện tại dùng TLS theo quan sát từ PostgreSQL server.

### 17.2. version

Cho biết phiên bản TLS được negotiated, chẳng hạn `TLSv1.3`, nếu được hỗ trợ.

### 17.3. cipher

Cho biết cipher được chọn cho phiên TLS. Không hardcode kỳ vọng đúng một chuỗi cipher trên mọi OS/OpenSSL/PG version.

### 17.4. bits

Thông tin về số bit của mã hóa được báo cáo bởi server; không tự suy “bits càng lớn là toàn bộ kết nối luôn an toàn” nếu không kiểm tra giao thức, xác thực và chính sách khóa.

### 17.5. Giới hạn quan sát

**Server thấy TLS hay không, nhưng không thể từ hàng `pg_stat_ssl` xác nhận rằng client thực sự dùng `sslmode=verify-full`.** Đây là cấu hình và quá trình xác minh phía client.

## 18. SHOW ssl và pg_stat_ssl khác nhau

~~~sql
SHOW ssl;
~~~

trả trạng thái cấu hình server có bật hỗ trợ SSL/TLS hay không.

~~~sql
SELECT ssl, version, cipher
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
~~~

trả trạng thái **kết nối hiện tại**.

### 18.1. Server bật TLS vẫn có thể nhận plaintext

Nếu `ssl=on` nhưng `pg_hba.conf` cho phép `host` hoặc `hostnossl` kết nối không TLS và client đặt `sslmode=disable`, một TCP connection plaintext có thể được chấp nhận.

### 18.2. server on không có nghĩa ứng dụng đang dùng TLS

Không dùng `SHOW ssl` làm bằng chứng duy nhất trong báo cáo tuân thủ về bảo mật đường truyền.

### 18.3. Kiểm tra đúng session app

Một DBA dùng psql với TLS không chứng minh connection pool của ứng dụng cũng dùng TLS. Cần kiểm tra cấu hình client app và trạng thái backend/session tương ứng.

### 18.4. pg_stat_ssl còn có cột client certificate

Ở các phiên bản thích hợp, `pg_stat_ssl` có thông tin như `client_dn`, `client_serial`, `issuer_dn` khi dùng client certificate. Những cột này liên quan mTLS; chúng không mô tả certificate server mà client đã tin cậy như thế nào.

## 19. Kiểm tra thông tin TLS trong psql

Trong một phiên `psql`, meta-command:

~~~text
\conninfo
~~~

có thể hiển thị thông tin kết nối, bao gồm việc dùng SSL/TLS và các chi tiết liên quan tùy phiên bản.

### 19.1. Kết hợp client và server evidence

Một quy trình kiểm tra tốt:

1. Xác nhận connection string dùng `sslmode=verify-full`.
2. Xác nhận trust anchor/certificate name đúng.
3. Kết nối thành công bằng đúng endpoint.
4. Dùng `\conninfo` và `pg_stat_ssl` xem phiên TLS.
5. Thử negative cases trong lab: CA sai hoặc hostname sai **phải thất bại**.

### 19.2. Vì sao thử negative cases?

Nếu bạn sửa `sslrootcert` sang CA không cấp server certificate nhưng kết nối vẫn thành công, có thể ứng dụng chưa áp chính sách verify-full như bạn tưởng, hoặc dùng đường kết nối/bộ tin cậy khác. Điều tra client/driver thay vì coi đó là bình thường.

### 19.3. Không kiểm thử bằng cách phá certificate production

Tạo endpoint lab hoặc môi trường staging có host/certificate cố ý sai để kiểm tra failure modes. Đừng làm hỏng chứng chỉ production rồi quan sát dashboard.

## 20. Lab: dựng CA thử nghiệm và server certificate có SAN

Phần này minh họa PKI cho học tập trên môi trường Unix có OpenSSL. **Không sử dụng khóa test cho production.** Tên miền `db.lab.internal` chỉ là ví dụ: bạn phải có hostname/resolution phù hợp hoặc dùng cơ chế test được quản lý.

### 20.1. Sơ đồ tệp

~~~text
pg-tls-lab/
    ca.key          # Private key của CA: BÍ MẬT
    ca.crt          # Public CA certificate: cấp cho client tin cậy
    server.key      # Private key của server: BÍ MẬT
    server.csr      # Certificate signing request
    server.ext      # SAN, EKU, key usages
    server.crt      # Chứng chỉ server được CA ký
~~~

### 20.2. Tạo thư mục

~~~bash
mkdir -p ./pg-tls-lab
cd ./pg-tls-lab
umask 077
~~~

`umask 077` giúp các tệp mới tạo mặc định hạn chế quyền trên hệ Unix phù hợp. Vẫn cần xác nhận quyền cuối cùng trước khi PostgreSQL đọc key.

### 20.3. Tạo CA thử nghiệm

~~~bash
openssl req -x509 -newkey rsa:3072 -nodes \
  -days 90 -sha256 \
  -subj "/CN=PostgreSQL Training Root CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -keyout ca.key -out ca.crt
~~~

**Giải thích:**

- `-x509` tạo certificate tự ký cho CA thử nghiệm.
- `-newkey rsa:3072` sinh khóa RSA ví dụ.
- `-nodes` tạo key không có passphrase; chỉ thuận tiện cho lab, không khuyến nghị với CA private key production.
- `-days 90` là hạn hiệu lực ngắn cho CA lab.
- `basicConstraints CA:TRUE` đánh dấu vai trò CA.
- `keyCertSign` thể hiện quyền ký chứng chỉ.

Các tùy chọn `-addext` yêu cầu OpenSSL phiên bản hỗ trợ. Môi trường production thường dùng PKI/CA manager, không cấp CA thủ công bằng dòng lệnh đơn giản này.

### 20.4. Tạo private key và CSR cho server

~~~bash
openssl req -new -newkey rsa:3072 -nodes \
  -subj "/CN=db.lab.internal" \
  -keyout server.key -out server.csr
~~~

### 20.5. Tạo file extension server.ext

~~~ini
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:db.lab.internal,IP:127.0.0.1
~~~

Trong thực tế, danh sách SAN phải được quyết định theo những tên DNS/IP **được dùng thực sự** để kết nối. Ví dụ IP `127.0.0.1` chỉ để demo localhost khi chính server PostgreSQL chạy ở máy đó hoặc kết nối tunnel được kiểm soát.

### 20.6. Ký certificate server bằng CA

~~~bash
openssl x509 -req \
  -in server.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt \
  -days 30 -sha256 \
  -extfile server.ext
~~~

Certificate này được ký bởi CA lab đã tạo. Nó **không tự được mọi máy tin**; client phải được cấp `ca.crt` đúng và sử dụng chế độ xác minh.

### 20.7. Kiểm tra certificate

~~~bash
openssl x509 -in server.crt -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

Bạn cần thấy issuer trỏ tới CA lab và SAN có tên mong đợi.

### 20.8. Verify chain và hostname ngoài PostgreSQL

~~~bash
openssl verify \
  -CAfile ca.crt \
  -purpose sslserver \
  -verify_hostname db.lab.internal \
  server.crt
~~~

Lệnh hỗ trợ trên các bản OpenSSL tương thích có thể kiểm tra certificate với CA và hostname đã cho. Đây là **kiểm tra tệp certificate**, không thay kiểm thử một kết nối PostgreSQL thật bằng driver/`sslmode=verify-full`.

## 21. Gắn chứng chỉ thử nghiệm vào PostgreSQL

Giả sử bạn có quyền quản trị database lab và đã đặt các tệp certificate vào thư mục mà tiến trình PostgreSQL được phép đọc:

~~~conf
ssl = on
ssl_cert_file = '/path/to/lab/server.crt'
ssl_key_file  = '/path/to/lab/server.key'
ssl_min_protocol_version = 'TLSv1.2'
~~~

Đường dẫn này là **placeholder**, phải đổi thành đường dẫn thực của môi trường lab.

### 21.1. Kiểm tra private key permissions

Tệp `server.key` phải có ownership/permissions hợp lệ theo PostgreSQL trên hệ điều hành. Không đặt `chmod 777` để “chữa lỗi SSL”.

### 21.2. Áp dụng cấu hình

Một số tham số liên quan SSL cần reload và một số thay đổi cấu hình cần restart tùy ngữ cảnh/phiên bản. Có thể xem:

~~~sql
SELECT
    name,
    setting,
    pending_restart
FROM pg_settings
WHERE name IN (
    'ssl',
    'ssl_cert_file',
    'ssl_key_file',
    'ssl_ca_file',
    'ssl_min_protocol_version'
)
ORDER BY name;
~~~

Không kết luận `pg_reload_conf()` đã kích hoạt mọi thay đổi chỉ vì câu lệnh trả về true. Theo dõi server logs, trạng thái hiệu lực và yêu cầu restart của môi trường.

### 21.3. Kết nối bằng CA lab

~~~bash
psql "host=db.lab.internal port=5432 dbname=appdb user=app_user sslmode=verify-full sslrootcert=/path/to/lab/ca.crt"
~~~

Tên `db.lab.internal` phải phân giải tới server chứa đúng `server.crt`, hoặc bạn phải cung cấp route/tên phù hợp có quản trị.

### 21.4. Chỉ chứa root CA trong trust store được phân phối đúng

Không sao chép `ca.key` sang client. Chỉ phân phối public `ca.crt` qua kênh đáng tin cậy và xác minh provenance của nó.

## 22. Thử nghiệm tích cực và tiêu cực

Hãy dùng **database lab** với CA/certificate nói trên.

### 22.1. Trường hợp đúng

~~~bash
psql "host=db.lab.internal dbname=appdb user=app_user sslmode=verify-full sslrootcert=/path/to/lab/ca.crt"
~~~

Kết nối thành công khi DNS/route, certificate, quyền và PostgreSQL authentication đều đúng.

### 22.2. CA sai

~~~bash
psql "host=db.lab.internal dbname=appdb user=app_user sslmode=verify-full sslrootcert=/path/to/other-ca.crt"
~~~

Nếu `other-ca.crt` không phải trust anchor cho certificate server, quá trình xác minh phải thất bại.

### 22.3. Hostname sai

~~~bash
psql "host=not-db.lab.internal dbname=appdb user=app_user sslmode=verify-full sslrootcert=/path/to/lab/ca.crt"
~~~

Ngay cả khi route được thiết kế để kết nối cùng server, tên `not-db.lab.internal` không có trong SAN thì xác minh tên phải từ chối theo quy tắc client.

### 22.4. Certificate hết hạn

Nếu server certificate nằm ngoài thời gian hiệu lực được phép, client nghiêm ngặt phải từ chối trong điều kiện clock/validation đúng.

### 22.5. Plaintext cố tình thử

~~~bash
psql "host=db.lab.internal dbname=appdb user=app_user sslmode=disable"
~~~

Nếu server policy đã chặn plaintext qua `pg_hba.conf`, kết nối này không được chấp nhận.

### 22.6. Đừng “sửa” test âm bằng require

Nếu `verify-full` báo lỗi xác minh, **không đổi sang `require` để đưa production trở lại hoạt động một cách im lặng**. Phải xác định nguyên nhân: SAN, CA, intermediate, hostname, clock, trust store, proxy hay certificate thực tế.

## 23. PostgreSQL JDBC: kết nối có verify-full

Trong ứng dụng Java:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Properties;

public class SecurePgConnection {
    public static void main(String[] args) throws Exception {
        String url =
            "jdbc:postgresql://db.example.internal:5432/appdb";

        Properties props = new Properties();
        props.setProperty("user", "app_user");
        props.setProperty(
            "password",
            System.getenv("DB_PASSWORD")
        );
        props.setProperty("sslmode", "verify-full");
        props.setProperty(
            "sslrootcert",
            "/etc/postgresql/client/ca.crt"
        );

        try (Connection conn =
                 DriverManager.getConnection(url, props);
             PreparedStatement ps = conn.prepareStatement(
                 "SELECT ssl, version, cipher " +
                 "FROM pg_stat_ssl WHERE pid = pg_backend_pid()"
             );
             ResultSet rs = ps.executeQuery()) {

            if (rs.next()) {
                System.out.println(
                    "TLS=" + rs.getBoolean("ssl")
                    + ", version=" + rs.getString("version")
                );
            }
        }
    }
}
~~~

### 23.1. PGJDBC và libpq là những clients khác nhau

PGJDBC có các properties tương tự `sslmode`/`sslrootcert`, nhưng cách xử lý tệp, trust store và SSL factory có thể khác libpq. Đừng suy “psql hoạt động thì JDBC chắc chắn hoạt động” nếu chúng dùng CA khác.

### 23.2. sslmode=verify-full ở JDBC

Đặt tường minh giúp chính sách dễ đọc và tránh phụ thuộc mặc định của driver/connection pool. Các tùy chọn như `ssl=true` có ngữ nghĩa theo phiên bản PGJDBC; khi cần chính sách cụ thể, ưu tiên khai báo `sslmode=verify-full` và kiểm thử.

### 23.3. Chứng chỉ phải khớp host trong URL

`jdbc:postgresql://db.example.internal:5432/appdb` sử dụng tên `db.example.internal` cho danh tính endpoint theo cơ chế driver. Nếu URL chuyển sang IP không có IP SAN thích hợp, việc xác minh có thể thất bại.

### 23.4. Quản lý mật khẩu

Ví dụ lấy `DB_PASSWORD` từ môi trường để ngắn gọn, nhưng production nên dùng secrets manager/secret injection được kiểm soát, tránh log `Properties` chứa password. Nếu biến không tồn tại, ứng dụng cần báo lỗi cấu hình rõ ràng trước khi kết nối.

### 23.5. Dùng driver phù hợp

Phải có dependency PGJDBC version được hỗ trợ trên classpath; TLS features, SSL factories và JDK truststore behavior cần được kiểm tra theo version driver/JDK đang triển khai.

## 24. JDBC URL, Properties và connection pool

Có thể cấu hình trong URL:

~~~text
jdbc:postgresql://db.example.internal:5432/appdb?sslmode=verify-full&sslrootcert=/etc/postgresql/client/ca.crt
~~~

Hoặc qua `Properties` như ví dụ trên.

### 24.1. Chú ý ký tự đặc biệt của query string

Nếu đường dẫn CA có khoảng trắng, dấu `&` hoặc ký tự đặc biệt, cần URL-encode theo quy tắc của JDBC URL hoặc dùng `Properties` để tránh parser hiểu sai.

### 24.2. Connection pool không tự cải thiện security

HikariCP hoặc connection pool khác quản lý kết nối, nhưng nếu driver properties thiết lập `sslmode=prefer`, pool chỉ tạo nhiều phiên với cùng chính sách yếu. Phải cấu hình TLS ngay tại datasource.

### 24.3. Cert rotation và kết nối lâu sống

Phiên TLS đang hoạt động có thể tiếp tục dùng trạng thái bảo mật từ handshake trước. Việc thay certificate server không có nghĩa mọi pooled connection đang mở lập tức làm một handshake mới. Cần chính sách tuổi kết nối/rollout/reconnect và giám sát.

### 24.4. Không chỉ nhìn kết nối quản trị

Muốn kiểm chứng môi trường Java, nên dùng chính datasource, driver, trust material và endpoint production-like, rồi kiểm tra `pg_stat_ssl` trên connection của ứng dụng.

## 25. Trust store: CA riêng, hệ thống và Java

Không phải mọi client lấy CA từ cùng một nơi.

### 25.1. libpq

Thường có `sslrootcert` và tệp CA mặc định trong thư mục PostgreSQL client. Một số phiên bản có lựa chọn trust store hệ thống riêng với ngữ nghĩa đi kèm; chỉ dùng khi đã xác nhận phiên bản.

### 25.2. PGJDBC

Với cấu hình mặc định của những SSL factories liên quan, `sslrootcert` có thể dùng tệp CA cho xác minh chứng chỉ. Một số cơ chế Java/JSSE dùng truststore JVM hoặc SSL factory khác. Cần xác định driver **thực sự dùng trust material nào**.

### 25.3. OS/browser trust không tự áp dụng cho mọi Java client

Một CA được trust bởi trình duyệt hoặc công cụ hệ điều hành chưa chắc được PGJDBC với SSL factory đang dùng tin tưởng, và ngược lại.

### 25.4. Tránh cấu hình trust-all

Một custom SSL factory chấp nhận mọi certificate hoặc bỏ hostname verification có thể khiến ứng dụng hoạt động nhưng mất ý nghĩa xác thực máy chủ. Không dùng trust-all ngoài môi trường kiểm thử cô lập và không đưa nó vào build production.

### 25.5. Trust anchor là một cấu hình bảo mật

Khi thay `ca.crt` hoặc JVM truststore, hãy quản lý review/versioning/rollout như thay đổi security policy, không coi là một file dữ liệu vô hại.

## 26. Mutual TLS (mTLS) là gì?

Thông thường TLS xác minh server; client đăng nhập PostgreSQL bằng SCRAM.

Trong **mTLS**, server cũng yêu cầu và xác minh certificate **của client**:

~~~text
Client                                       PostgreSQL
  |---- ClientHello ---------------------------->|
  |<--- Server cert -----------------------------|
  |---- Client verify CA + hostname ------------|
  |<--- Server yêu cầu client certificate -------|
  |---- Client certificate + proof of key ------>|
  |<--- Server verify client CA / identity ------|
  |==== TLS channel được xác thực hai phía ======|
  |---- PostgreSQL auth phù hợp pg_hba.conf ---->|
~~~

### 26.1. Hai certificate khác vai trò

| Đối tượng | Private key nằm ở đâu? | CA được bên nào trust? |
| --- | --- | --- |
| Server cert | Server/TLS proxy phù hợp | Client trust để xác minh server |
| Client cert | Ứng dụng/client | PostgreSQL trust để xác minh client |

### 26.2. Cấp certificate riêng cho từng service

Đừng phát một client private key dùng chung cho mọi ứng dụng. Nên có danh tính, vòng đời và quyền riêng theo service/role để có thể thu hồi một client mà không ảnh hưởng tất cả.

### 26.3. mTLS không thay authorization

Server xác minh client certificate không tự cho phép role ấy đọc mọi bảng. Vẫn cần PostgreSQL authentication/role mapping và `GRANT`/RLS.

### 26.4. mTLS tăng chi phí vận hành PKI

Bạn phải phát hành, phân phối, luân chuyển và thu hồi **client certificates**, giám sát certificate expiry và xử lý việc key bị lộ trên mỗi workload.

## 27. Bật xác minh client certificate ở server

Trên server, chỉ rõ CA dùng để xác minh certificates của clients:

~~~conf
ssl = on
ssl_cert_file = '/etc/postgresql/tls/server.crt'
ssl_key_file  = '/etc/postgresql/tls/server.key'
ssl_ca_file   = '/etc/postgresql/tls/client-ca.crt'
~~~

### 27.1. Sử dụng clientcert trong pg_hba.conf

Ví dụ yêu cầu **cả SCRAM password và certificate client**:

~~~conf
hostssl appdb app_user 10.20.0.0/16 scram-sha-256 clientcert=verify-full
~~~

Theo chính sách này, client phải thỏa điều kiện TLS, certificate client được server xác minh đúng và SCRAM authentication (cùng quy tắc identity/mapping phù hợp).

### 27.2. verify-ca và verify-full của clientcert

Trong ngữ cảnh `clientcert` của `pg_hba.conf`:

- `verify-ca` tập trung xác thực certificate client được một CA tin cậy ký.
- `verify-full` còn áp điều kiện tên/identity của client certificate theo quy tắc PostgreSQL/mapping.

Đừng nhầm chúng với `sslmode=verify-ca` và `sslmode=verify-full` của **client xác minh server**.

### 27.3. Certificate authentication

PostgreSQL cũng hỗ trợ phương thức `cert` trong `pg_hba.conf`, dùng certificate client làm cơ sở xác thực role theo quy tắc và mapping. Đây là hướng thiết kế khác với `scram-sha-256 clientcert=verify-full`, vốn kết hợp điều kiện certificate và password.

### 27.4. pg_ident.conf

Khi cần ánh xạ danh tính certificate với PostgreSQL role, có thể dùng `map` và `pg_ident.conf` theo cơ chế được hỗ trợ. Cần tránh giả định CN của certificate luôn trùng 100% với role hoặc không cần quản lý mapping.

## 28. Cấu hình client certificate

Với libpq, một kết nối mTLS có thể dùng:

~~~bash
psql "host=db.example.internal dbname=appdb user=app_user sslmode=verify-full sslrootcert=/etc/postgresql/client/server-ca.crt sslcert=/etc/postgresql/client/app-client.crt sslkey=/etc/postgresql/client/app-client.key"
~~~

### 28.1. Ba file khác vai trò

- `server-ca.crt`: trust anchor để client xác minh certificate server.
- `app-client.crt`: certificate được app trình bày cho server.
- `app-client.key`: private key của app; phải giữ bí mật.

### 28.2. Client certificate không chứng minh đúng server

Ngay cả khi bạn cung cấp `sslcert` và `sslkey`, client **vẫn cần `sslrootcert` và `verify-full`** nếu muốn bảo vệ danh tính server.

### 28.3. Key permissions ở client

Client private key cũng cần quyền file bảo vệ phù hợp. PGJDBC, libpq và OS có cơ chế đọc key khác nhau; cấp quyền tối thiểu cho tiến trình service.

### 28.4. Không dùng lại khóa test

Không đem `server.key` của lab làm `app-client.key`. Certificate phải có mục đích sử dụng và danh tính thích hợp, không dùng một cặp key bừa bãi cho nhiều vai trò.

## 29. Chứng chỉ hết hạn: ảnh hưởng thực tế

Certificate có ngày:

~~~text
notBefore = ...
notAfter  = ...
~~~

Khi server certificate hết hiệu lực theo đánh giá của client, những kết nối mới với verification đúng có thể thất bại.

### 29.1. Giám sát trước khi hết hạn

Nên cảnh báo trước nhiều ngưỡng (ví dụ 30 ngày, 14 ngày, 7 ngày, 1 ngày) phù hợp chu kỳ phát hành tổ chức. Đây là các ngưỡng ví dụ, không phải chuẩn bắt buộc.

### 29.2. Thời gian hệ thống

Máy client/server có clock sai lớn có thể khiến certificate bị coi là “not yet valid” hoặc “expired” dù PKI được cấp đúng. Duy trì đồng bộ thời gian và kiểm tra clock khi chẩn đoán.

### 29.3. Không hạ sslmode để vượt sự cố

Certificate hết hạn là tín hiệu cần rotation/khắc phục PKI, không phải lý do đổi `verify-full` thành `prefer`.

### 29.4. Connection pool và sự cố chậm

Những pooled connections đã tồn tại có thể tiếp tục hoạt động trong khi các kết nối mới lỗi vì certificate hết hạn hoặc trust store mới. Điều này có thể khiến sự cố xuất hiện không đồng thời giữa các pods/instances.

## 30. Luân chuyển server certificate

Một quy trình rotation nên giữ khả năng xác minh cho các clients trong suốt thời gian cutover.

~~~text
1. Kiểm tra tên DNS/IP và SAN hiện đang sử dụng.
2. Phát hành certificate mới từ CA được tin cậy.
3. Xác nhận key, chain, thời hạn, EKU và SAN.
4. Đưa certificate + private key vào secret storage an toàn.
5. Cập nhật server theo cơ chế reload/restart hỗ trợ.
6. Mở kết nối mới verify-full từ clients đại diện.
7. Kiểm tra pg_stat_ssl và logs lỗi handshake.
8. Theo dõi pool reconnect, failover nodes và replicas.
9. Gỡ certificate/key cũ theo lịch được phê duyệt.
~~~

### 30.1. Nếu chỉ thay leaf cùng CA

Client vẫn tin CA cũ có thể tiếp tục xác minh server sau khi server dùng certificate mới, miễn SAN/chain và thời hạn hợp lệ.

### 30.2. Nếu thay CA

Đây là thay đổi lớn hơn: clients phải có trust anchor mới đúng thời điểm. Một giai đoạn phân phối cả CA cũ và CA mới trong bundle được kiểm soát có thể giúp rollout an toàn; không gỡ CA cũ khi còn server chưa được chuyển, trừ khi có kế hoạch cutover chặt chẽ.

### 30.3. Đừng luân chuyển độc lập từng node mà quên kết nối mới

Trong cluster có nhiều hosts/proxy, một client có thể chọn endpoint khác sau failover. Tất cả các TLS endpoints liên quan phải được cấp certificate phù hợp trước khi có thể nhận traffic.

### 30.4. Phải có rollback có kiểm soát

Nếu certificate mới lỗi SAN/chain/quyền file, cần một phương án khôi phục certificate hợp lệ được phép sử dụng. Đừng rollback về key đã bị đánh cắp hoặc certificate đã hết hạn chỉ vì thao tác dễ hơn.

## 31. Thu hồi chứng chỉ và key bị lộ

Certificate có thể chưa hết hạn nhưng private key bị lộ hoặc danh tính không còn được phép dùng.

### 31.1. Không chỉ xóa tệp trên server

Nếu một attacker đã lấy private key, xóa bản local không khiến khóa đã bị sao chép mất hiệu lực. Cần cấp cặp khóa mới, thu hồi certificate cũ theo chính sách CA và cập nhật hệ thống tin cậy.

### 31.2. CRL/OCSP và khả năng thực thi

Hệ sinh thái PostgreSQL/libpq hỗ trợ những tùy chọn liên quan danh sách thu hồi certificate (ví dụ `sslcrl`/`sslcrldir` phía client tùy version, `ssl_crl_file` phía server cho client cert). Cách kiểm tra revocation không giống mọi browser/OS và có thể không tự bật như bạn nghĩ.

### 31.3. Chính sách cần thực nghiệm

Muốn cam kết revoked certificate không đăng nhập được, phải xác nhận client/server thực sự kiểm tra CRL/OCSP bằng cơ chế được hỗ trợ và kiểm thử một certificate đã bị thu hồi trong lab.

### 31.4. Ngắn hạn hiệu lực vẫn hữu ích

Certificates ngắn hạn và tự động rotation giảm thời gian một certificate cũ còn có giá trị. Nhưng nó không thay thế bảo vệ private key và quy trình incident response.

## 32. Kiểm tra chứng chỉ qua OpenSSL

Xem nội dung tệp:

~~~bash
openssl x509 -in server.crt -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

Kiểm tra public certificate/key khớp về public key (minh họa, cần bảo vệ private key):

~~~bash
openssl x509 -in server.crt -pubkey -noout > cert.pub
openssl pkey -in server.key -pubout > key.pub
diff cert.pub key.pub
~~~

Nếu khác nhau, certificate và private key có thể không phải một cặp.

### 32.1. Không gửi private key cho dịch vụ kiểm chứng online

Các lệnh này chạy trên môi trường tin cậy. Không upload `server.key`/`ca.key` lên trang web công cộng để “kiểm tra”.

### 32.2. Kiểm tra server đang trình bày certificate nào

Trên một số phiên bản OpenSSL, có thể dùng:

~~~bash
openssl s_client \
  -starttls postgres \
  -connect db.example.internal:5432 \
  -servername db.example.internal \
  -showcerts
~~~

Khả năng `-starttls postgres`/SNI và cú pháp phụ thuộc phiên bản OpenSSL. Đây là công cụ chẩn đoán chain và handshake, không thay việc thử **client driver thật** với `verify-full`.

### 32.3. SNI và multi-tenant proxy

Khi kết nối đi qua proxy dùng SNI để chọn certificate/backend, cần xác minh client/proxy hỗ trợ truyền tên đúng. Nếu proxy trình bày certificate không khớp tên, sửa cấu hình SNI/certificate — không bỏ hostname verification.

## 33. Những lỗi TLS thường gặp

### 33.1. Certificate verify failed

Khả năng:

- CA chưa có trong trust anchor.
- Chứng chỉ server do CA khác ký.
- Intermediate thiếu.
- Certificate hết hạn hoặc chưa có hiệu lực.
- Extended Key Usage/purpose không phù hợp.
- Hệ thống thời gian sai.

### 33.2. Hostname mismatch

Client kết nối bằng tên/IP không nằm trong SAN phù hợp. Thường do dùng endpoint alias mới, localhost, IP trực tiếp hoặc certificate chỉ cấp cho tên backend.

### 33.3. Server does not support SSL

Server/proxy không đáp ứng quá trình TLS negotiation như client kỳ vọng, hoặc server chưa bật TLS/không hỗ trợ. Kiểm tra cấu hình server, đường TCP, proxy và phiên bản.

### 33.4. No pg_hba.conf entry

Có thể client đã bắt tay TLS được, nhưng không match một rule phù hợp cho database/user/address/SSL state. Kiểm tra rule và thứ tự; đừng thay `verify-full` thành `disable`.

### 33.5. Could not load private key

Đường dẫn không đúng, key format không phù hợp, owner/permissions sai hoặc key không khớp certificate. Đọc server logs và kiểm tra quyền file trên host.

### 33.6. Client unexpectedly does not use TLS

Có thể kết nối qua Unix socket, `sslmode` chưa được truyền tới driver, GSS encryption được chọn hoặc đang quan sát session khác. Kiểm tra connection properties, `pg_stat_ssl` và đường kết nối thực.

### 33.7. Old clients cannot negotiate protocol/cipher

Client JDK/OpenSSL/driver cũ có thể không hỗ trợ TLS policy mới. Hướng khắc phục bền vững là **nâng cấp client/driver** hoặc tương thích có đánh giá bảo mật; không mặc nhiên bật TLS 1.0/1.1.

### 33.8. Mismatch xảy ra sau failover

Node failover có certificate thiếu SAN cho alias dịch vụ, CA khác hoặc chain chưa hoàn chỉnh. Kiểm chứng từng endpoint và chuỗi trust trước khi cutover.

## 34. Sự khác nhau giữa SSL, TLS, chứng chỉ và password

| Thuật ngữ | Nghĩa trong bối cảnh PostgreSQL |
| --- | --- |
| SSL | Tên lịch sử vẫn xuất hiện trong các tham số như `sslmode` |
| TLS | Giao thức hiện đại bảo vệ phiên truyền tải |
| Server certificate | Public identity/key của TLS server |
| Server private key | Khóa bí mật server dùng trong handshake |
| CA certificate | Trust anchor để xác minh certificate đã được cấp |
| Server identity | Tên DNS/IP được client mong đợi và kiểm tra |
| Client certificate | Public identity/key do client trình bày cho mTLS |
| Client private key | Khóa bí mật của client |
| SCRAM password auth | Cơ chế xác thực user PostgreSQL |
| GRANT/RLS | Phân quyền dữ liệu sau khi đã xác thực |

### 34.1. Tên ssl trong config không có nghĩa dùng giao thức SSL lỗi thời

PostgreSQL giữ các tham số `ssl`, `sslmode` theo lịch sử. Một kết nối hiện đại thường thương lượng TLS 1.2 hoặc TLS 1.3 tùy phía client/server.

### 34.2. Certificate không phải user password

Certificate chứng minh mối liên hệ giữa key và identity trong PKI. Tùy `pg_hba.conf`, server vẫn có thể yêu cầu password và/hoặc client certificate riêng.

### 34.3. Xác thực máy chủ khác xác thực máy khách

`sslmode=verify-full` trên client xác minh server. `clientcert=verify-full` trong `pg_hba.conf` của server xác minh danh tính certificate client theo quy tắc mTLS. Cùng tên “verify-full” nhưng **hai chiều xác minh khác nhau**.

## 35. Chính sách TLS trong môi trường đa lớp

Một triển khai thường có:

~~~text
App -> Sidecar / pooler -> Load balancer -> PostgreSQL
~~~

### 35.1. Xác định TLS termination

Với mỗi hop, liệt kê:

- Ai là TLS client?
- Ai trình bày server certificate?
- Client xác minh hostname nào?
- CA/trust store nằm ở đâu?
- Đoạn phía sau có mã hóa riêng không?

### 35.2. PgBouncer

Nếu dùng PgBouncer, có thể có TLS giữa ứng dụng và PgBouncer, và TLS khác giữa PgBouncer và PostgreSQL. Cấu hình bảo vệ client-side và server-side của pooler phải được xem **độc lập**. Việc app `verify-full` chứng chỉ PgBouncer không tự chứng minh kết nối PgBouncer → DB đã xác minh server.

### 35.3. Cloud-managed databases

Nhà cung cấp có thể dùng CA bundles/rotation và endpoint aliases riêng. Phải lấy CA đúng từ nguồn được xác thực theo hướng dẫn dịch vụ; không tải CA từ liên kết tùy ý hoặc dùng trust-all cho tiện.

### 35.4. DNS discovery và service mesh

Nếu client dùng service hostname nhưng endpoint TLS là sidecar/proxy, certificate phải khớp identity mà client thực sự xác minh. Mô hình mesh mTLS có thể bảo vệ một hop, nhưng không mặc nhiên áp đúng PostgreSQL hostname verification nếu app dùng một đường khác.

## 36. TLS cho read replicas và failover

Khi client có thể chuyển giữa:

~~~text
db-primary.example.internal
db-replica-a.example.internal
db-replica-b.example.internal
~~~

cần quản lý certificate/trust cho từng endpoint.

### 36.1. Danh tính backend riêng

Mỗi node có thể có certificate riêng với SAN đúng hostname node. Điều này hỗ trợ kiểm chứng host cụ thể.

### 36.2. Danh tính dịch vụ chung

Nếu app chỉ kết nối `db.service.internal` và load balancer là TLS endpoint, certificate của load balancer phải có tên dịch vụ. Nếu TLS passthrough tới backend, backend được chọn phải có chứng chỉ tương thích với tên app đang kiểm chứng.

### 36.3. target_session_attrs không thay TLS

Một số libpq clients dùng `target_session_attrs=read-write` để chọn server có trạng thái role phù hợp. Điều này là logic chọn endpoint **sau khi kết nối**; không thay việc xác minh certificate của từng host được thử.

### 36.4. Không sao chép một private key lên tất cả nodes tùy tiện

Việc dùng chung certificate/key giữa nodes có rủi ro blast radius. Cân nhắc cấp per-node certificate, service identity và phương pháp termination theo kiến trúc/PKI được phê duyệt.

## 37. Kết nối nội bộ có cần TLS không?

“Chỉ chạy trong private subnet” không tự chứng minh mọi traffic an toàn.

### 37.1. Private network không phải trust boundary tuyệt đối

Một host nội bộ bị chiếm quyền, cấu hình network sai hoặc sự thay đổi route có thể tăng khả năng truy cập trái phép.

### 37.2. Mức bảo vệ theo dữ liệu và quy định

Một tổ chức có thể yêu cầu mã hóa mọi kết nối DB kể cả internal traffic. Khi có yêu cầu đó, cấu hình `verify-full` và server-side TLS-only rules nên nằm trong baseline.

### 37.3. Unix socket cùng máy

Với Unix-domain socket, bảo mật dựa trên cơ chế local OS/socket permissions và PostgreSQL auth; TLS không áp dụng như TCP. Không nhầm điều này với việc chấp nhận plaintext TCP trên mạng.

### 37.4. Performance không phải lý do bỏ xác minh hostname

TLS có chi phí handshake/mã hóa, nhưng đối với workloads thông thường chi phí đó cần được đo trước khi đánh đổi an toàn. Connection pooling và điều chỉnh quy mô phù hợp thường tốt hơn bỏ TLS.

## 38. Quan sát, alert và baseline vận hành

Một baseline quản trị TLS có thể gồm:

1. Tên các endpoints PostgreSQL được phép.
2. CA bundles/trust anchors được quản lý tập trung.
3. Yêu cầu `sslmode=verify-full` cho mọi TCP client.
4. Server-side `hostssl`/chính sách từ chối plaintext.
5. Phiên bản TLS/cipher policy được chấp thuận.
6. Thời hạn certificates và cảnh báo sắp hết hạn.
7. Quy trình rotation/thu hồi.
8. Danh sách nơi TLS termination/proxy.
9. Quan sát kênh thực tế từ app và server.
10. Kiểm thử negative CA/hostname trong staging.

### 38.1. Query TLS versions đang hoạt động

~~~sql
SELECT
    ssl,
    version,
    cipher,
    count(*) AS connections
FROM pg_stat_ssl
GROUP BY ssl, version, cipher
ORDER BY ssl DESC, connections DESC;
~~~

Kết quả phản ánh các backends/connections được quan sát, không thay cho inventory của mọi client có thể kết nối.

### 38.2. Theo dõi kết nối không TLS

~~~sql
SELECT
    count(*) FILTER (WHERE ssl) AS tls_connections,
    count(*) FILTER (WHERE NOT ssl) AS non_tls_connections
FROM pg_stat_ssl;
~~~

**Lưu ý:** Một số backends/local connections không dùng TLS vì không phải client TCP từ mạng; đừng chỉ lấy số đếm và kết luận mọi non-TLS là sự cố mà không xem PID/backend/nguồn kết nối.

### 38.3. Không dùng pg_stat_ssl để tự động xác nhận verify-full

Muốn audit client-side verification, cần kiểm soát cấu hình connection string, version driver, trust material, policy validation và test âm trong pipeline, không chỉ đọc chỉ số từ server.

## 39. Checklist xử lý sự cố kết nối verify-full

Khi một app báo không kết nối được sau khi bật TLS:

1. **Có phải TCP tới đúng endpoint và port không?**
2. **Có proxy/load balancer/sidecar nào ở giữa không?**
3. **Tên host trong URL/connstring là gì?**
4. **Server/proxy trình bày certificate có SAN khớp tên ấy không?**
5. **CA nào đã ký leaf/intermediate?**
6. **Client đang tin CA nào, từ file hoặc JVM truststore nào?**
7. **Chain có thiếu intermediate không?**
8. **Certificate có còn hiệu lực và clock có đúng không?**
9. **Server private key có đúng cặp và quyền file hợp lệ không?**
10. **Server có bật TLS/phiên bản và cipher tương thích không?**
11. **pg_hba.conf rule đúng thứ tự, đúng IP và đúng method chưa?**
12. **Kết nối dùng SCRAM/client cert có hoàn thành auth không?**
13. **Ứng dụng Java có dùng đúng datasource properties không?**
14. **Có node failover với certificate khác không?**
15. **Có GSS encryption hoặc Unix socket khiến quan sát sai không?**
16. **Khi dùng CA/hostname cố tình sai trong staging, kết nối có thất bại không?**

### 39.1. Phân lớp lỗi

| Giai đoạn | Dấu hiệu | Nơi kiểm tra |
| --- | --- | --- |
| DNS/TCP | Không resolve/timeout/refused | Network, DNS, listener |
| TLS handshake | Protocol/cipher/cert mismatch | TLS server/client logs |
| Server identity | CA/hostname verification failed | SAN, CA chain, trust store |
| PostgreSQL authentication | Password/role/cert mapping failed | `pg_hba.conf`, roles |
| SQL authorization | Permission denied for table/schema | `GRANT`, role, RLS |
| Pool/replica | Chỉ một số requests lỗi | Pool nodes, endpoints, rotation |

### 39.2. Không tiết lộ private keys khi debug

Khi gửi logs cho người khác, không đính kèm `*.key`, mật khẩu, connection strings có secrets hoặc certificate bundles nội bộ chưa được phép chia sẻ.

### 39.3. Không sửa bảo mật bằng cách tắt bảo mật

Đổi sang `sslmode=disable`/`require`/trust-all để “qua được kết nối” có thể che lỗi đúng ra phải sửa ở PKI, SAN, CA hoặc endpoint.

## 40. Lỗi hiểu sai thường gặp

### Lỗi 1. Bật ssl=on nghĩa là mọi client có TLS

Không. `ssl=on` chỉ bật khả năng TLS; phía client và `pg_hba.conf` có thể cho phép các đường không TLS.

### Lỗi 2. sslmode=require tương đương verify-full

Không. `require` yêu cầu kênh TLS nhưng không có cùng chính sách xác minh hostname/CA như `verify-full`.

### Lỗi 3. sslmode=prefer là chính sách bắt buộc TLS

Không. `prefer` có thể fallback plaintext, không phù hợp yêu cầu mã hóa bắt buộc.

### Lỗi 4. verify-ca đủ để chống giả mạo tên máy

Không. Một certificate hợp lệ từ cùng CA có thể thuộc server khác. `verify-full` mới kiểm tra tên mong đợi.

### Lỗi 5. Certificate CN đủ thay cho SAN

Không nên dựa vào CN fallback. Hãy cấp certificate với SAN đúng các tên DNS/IP sử dụng.

### Lỗi 6. IP literal được kiểm tra như một DNS SAN

Tên IP nên được biểu diễn bằng IP SAN phù hợp. Một DNS SAN chứa ký tự trông như địa chỉ IP không phải lúc nào được client xử lý như IP identity.

### Lỗi 7. Server có ssl_ca_file thì client tự tin CA ấy

Không. Server `ssl_ca_file` chủ yếu để kiểm tra certificate client; client phải có trust store riêng để xác minh server.

### Lỗi 8. sslcert và sslkey dùng để kiểm tra server

Không. Chúng là identity/key **của client**, dùng khi cần mTLS.

### Lỗi 9. Password đúng là đủ bảo vệ danh tính server

Không. PostgreSQL auth user và xác minh TLS server là các lớp khác nhau.

### Lỗi 10. hostssl ép client dùng verify-full

Không. `hostssl` yêu cầu kết nối có TLS; server không thể chứng minh client đã xác minh hostname của server.

### Lỗi 11. Một kết nối psql có TLS chứng minh Java app có TLS

Không. App có thể dùng driver, trust store, URL và pool khác.

### Lỗi 12. pg_stat_ssl.ssl=true nghĩa là hostname đã được xác minh

Không. Server không biết client đã dùng `sslmode` gì.

### Lỗi 13. Kết nối qua Unix socket là kết nối TLS

Không. SSL mode không áp dụng như TCP; kiểm tra loại socket và cơ chế local security riêng.

### Lỗi 14. CA public luôn hợp lệ cho mọi tên nội bộ

Không. Việc phát hành certificate cho tên và chính sách CA có giới hạn; dùng PKI phù hợp cho tên dịch vụ thực tế.

### Lỗi 15. Certificate hợp lệ nhưng thiếu intermediate sẽ luôn hoạt động

Không. Client có thể thất bại khi không xây được chain tới CA tin cậy.

### Lỗi 16. Certificate mới không cần kiểm tra SAN

Không. Đổi/rotate server certificate có thể làm hostname mismatch dù issuer hợp lệ.

### Lỗi 17. Certificate hết hạn thì đổi sslmode xuống prefer

Không. Phải rotate certificate, sửa clock/PKI và giữ chính sách xác minh.

### Lỗi 18. Private key có thể commit git vì chỉ ở repo nội bộ

Không. Private key là bí mật; repo, CI logs và image có blast radius rất lớn.

### Lỗi 19. Đặt chmod 777 để sửa permission

Không. Server private key cần hạn chế quyền; cấp quyền quá rộng làm tăng rủi ro hoặc khiến PostgreSQL từ chối key.

### Lỗi 20. TLS qua một proxy là bảo vệ mọi hop

Không. Phải kiểm tra kết nối giữa proxy và PostgreSQL, cũng như hostname mà mỗi hop xác minh.

### Lỗi 21. mTLS thay PostgreSQL GRANT/RLS

Không. Client certificate xác thực một workload/service, không tự cấp quyền đọc/ghi dữ liệu.

### Lỗi 22. Client cert dùng được cho mọi role

Không mặc định. `clientcert`, `cert`, subject mapping và `pg_ident.conf` quyết định cách gắn certificate identity với database role.

### Lỗi 23. SNI/failover luôn chọn certificate khớp

Không. Multi-node hoặc proxy có thể trình bày certificate khác; phải kiểm thử từng đích.

### Lỗi 24. Root CA private key phải đặt cùng server.key

Không. Root CA key phải ở môi trường phát hành tin cậy, không trên tất cả server.

### Lỗi 25. Cấp certificate ngắn hạn tự giải quyết revocation

Không. Vẫn cần bảo vệ key, cơ chế thu hồi/phản ứng sự cố và kiểm soát trust.

### Lỗi 26. Mọi client đều dùng CA từ OS

Không. libpq, PGJDBC và JSSE có cách chọn trust store khác nhau theo cấu hình/phiên bản.

### Lỗi 27. Dùng trust-all SSL factory trong production

Làm mất ý nghĩa xác minh server, mở đường cho MITM dù TLS handshake thành công.

### Lỗi 28. Chỉ kiểm tra chứng chỉ lúc deploy, không giám sát expiry

Certificate hết hạn về sau gây lỗi kết nối mới; cần monitoring và rotation.

### Lỗi 29. PG SSL settings thay đổi thì mọi phiên cũ handshake lại

Không. Connection pools có thể giữ TLS sessions đã thiết lập; cần quản lý reconnect khi rotation/chính sách thay đổi.

### Lỗi 30. TLS giải quyết SQL injection

Không. SQL phải parameterized và quyền phải hạn chế.

## 41. Bài tập thực hành

Các bài sau áp dụng với PostgreSQL có TLS được bật trong môi trường lab. Những câu cấu hình server/CA cần quyền quản trị và **không sửa production** chỉ để thử. Kết quả minh họa có thể khác giữa các phiên bản PostgreSQL/OpenSSL/PGJDBC.

### Bài 1. Ba lớp bảo mật

Phân biệt TLS encryption, server certificate verification và PostgreSQL user authentication.

### Bài 2. Hai đầu mạng

Vì sao client và database đang trao đổi qua TLS vẫn có thể bị MITM nếu không kiểm tra certificate name/CA?

### Bài 3. Xác thực server

Chế độ sslmode nào nên chọn nếu bắt buộc TLS và muốn xác minh đúng tên database server?

### Bài 4. prefer

`sslmode=prefer` có đảm bảo không bao giờ dùng plaintext TCP không? Vì sao?

### Bài 5. require

`sslmode=require` có đồng nghĩa với việc kiểm tra SAN hostname không?

### Bài 6. verify-ca

Cho CA đã cấp chứng chỉ cho db-a và db-b. Vì sao verify-ca chưa chắc phát hiện việc kết nối nhầm db-b?

### Bài 7. SAN

App kết nối tới `db.shop.internal`. Certificate nên có SAN gì?

### Bài 8. IP address

App kết nối qua `192.0.2.10`. Vì sao DNS SAN `DNS:192.0.2.10` không phải cách khai báo chuẩn cho IP identity?

### Bài 9. Root CA

Mô tả file CA public và CA private key. Client cần file nào để xác minh server?

### Bài 10. Intermediate

Một server certificate được intermediate CA ký nhưng server không cung cấp intermediate. Điều gì có thể xảy ra?

### Bài 11. Cấu hình server

Viết `postgresql.conf` bật TLS, chỉ định server cert/key và minimum TLSv1.2.

### Bài 12. ssl_ca_file

`ssl_ca_file` trên PostgreSQL server thường phục vụ việc gì?

### Bài 13. hostssl

Viết rule `pg_hba.conf` chỉ cho user `app_user` từ mạng `10.20.0.0/16` vào `appdb` qua TLS và SCRAM.

### Bài 14. Plaintext policy

Viết rule từ chối tất cả plaintext IPv4 và IPv6 TCP.

### Bài 15. Kiểm tra kênh hiện tại

Viết SQL xem `ssl`, `version` và `cipher` cho backend hiện tại.

### Bài 16. SHOW ssl

Vì sao `SHOW ssl` không đủ chứng minh connection app hiện đang có TLS?

### Bài 17. Client verification từ server

Một DBA nhìn `pg_stat_ssl.ssl=true`. Có thể kết luận client đang dùng verify-full không?

### Bài 18. psql

Viết câu kết nối psql tới `db.shop.internal` qua port 5432, dbname `shopdb`, user `shop_app`, sslmode verify-full và file CA `/etc/shop/db-ca.crt`.

### Bài 19. Certificate expired

Nêu nguyên nhân/sửa đúng khi client báo certificate expired.

### Bài 20. Hostname mismatch

Certificate chỉ có `DNS:db-a.internal` nhưng app dùng `db-service.internal`. Sửa thế nào mà vẫn giữ verify-full?

### Bài 21. Negative test

Đề xuất hai negative tests để chứng minh client thực sự xác minh danh tính server.

### Bài 22. JDBC URL

Viết JDBC URL kết nối `db.shop.internal:5432/shopdb` với sslmode verify-full và sslrootcert.

### Bài 23. Java Properties

Đặt `sslmode` và `sslrootcert` trong `Properties` cho PGJDBC.

### Bài 24. Password handling

Vì sao không nên ghi database password trực tiếp trong URL/CLI hoặc log?

### Bài 25. mTLS

mTLS bổ sung bước xác minh gì so với TLS một chiều thông thường?

### Bài 26. Client cert files

Phân biệt `sslrootcert`, `sslcert` và `sslkey` trên client.

### Bài 27. SCRAM và clientcert

Viết mẫu hostssl yêu cầu `scram-sha-256` và `clientcert=verify-full`.

### Bài 28. Mapping identity

Tại sao việc certificate client có CN “service-a” không tự đảm bảo PostgreSQL role tên “app_user” được đăng nhập?

### Bài 29. Channel binding

Channel binding có thay việc xác minh CA/hostname không?

### Bài 30. PgBouncer

Nếu client verify-full chứng chỉ PgBouncer, điều đó có chứng minh PgBouncer → PostgreSQL mã hóa và xác thực server không?

### Bài 31. Failover

Hai node failover có certificate riêng. Khi app dùng tên service ổn định, cần kiểm tra yếu tố gì?

### Bài 32. CA rotation

Bạn thay từ CA A sang CA B. Vì sao không nên loại CA A trên mọi client ngay khi node đầu tiên chuyển sang B?

### Bài 33. Server key

Vì sao `server.key` không được commit git hoặc cấp quyền đọc cho mọi user?

### Bài 34. OpenSSL inspect

Viết lệnh xem subject, issuer, ngày hiệu lực và SAN của `server.crt`.

### Bài 35. pg_stat_ssl histogram

Viết SQL đếm kết nối theo TLS version và cipher.

### Bài 36. Connection pool

Vì sao rotate server certificate không làm mọi pooled connection handshake lại ngay?

### Bài 37. TLS policy compliance

Kể tên ít nhất năm dấu hiệu/kiểm tra cần có trước khi công bố app→PostgreSQL an toàn bằng TLS.

### Bài 38. SQL injection

Một hệ thống đã dùng verify-full. Nó còn cần prepared statements và GRANT/RLS không?

### Bài 39. Unix socket

Tại sao chạy psql không truyền host trên Unix có thể không phải là một test TLS?

### Bài 40. GSS encryption

Nếu kết nối dùng GSS encryption thay vì TLS, cần cẩn thận gì khi đánh giá yêu cầu X.509/TLS của tổ chức?

## 42. Gợi ý lời giải

### Bài 1–3. Các lớp và verify-full

TLS mã hóa truyền tải, certificate verification đảm bảo client nhận diện đúng server theo trust chain và tên, PostgreSQL authentication xác minh user/role. TLS không kiểm tra CA/hostname có thể bị MITM. `sslmode=verify-full` là lựa chọn phù hợp để bắt buộc TLS và xác minh server đầy đủ.

### Bài 4–6. Các sslmode

`prefer` có thể fallback plaintext. `require` không mặc định bảo đảm hostname verification, dù libpq có hành vi tương thích liên quan CA file. `verify-ca` kiểm tra CA nhưng không kiểm tra đúng tên db-a so với db-b; `verify-full` giải quyết bước tên.

### Bài 7–8. SAN

Cho hostname `db.shop.internal`, dùng SAN `DNS:db.shop.internal`. Với IP `192.0.2.10`, dùng SAN loại `IP:192.0.2.10` theo chuẩn certificate/driver tương ứng.

### Bài 9–10. CA chain

Client nhận **CA public certificate/trust anchor**, không nhận CA private key. Nếu thiếu intermediate, client có thể không hoàn tất chain validation dù root CA được tin cậy.

### Bài 11. Server config

~~~conf
ssl = on
ssl_cert_file = '/etc/postgresql/tls/server.crt'
ssl_key_file  = '/etc/postgresql/tls/server.key'
ssl_min_protocol_version = 'TLSv1.2'
~~~

Các path là ví dụ; phải có tệp thật và permissions phù hợp.

### Bài 12. ssl_ca_file

Nó chủ yếu cung cấp CA trust ở phía server để kiểm tra certificates **của client** khi dùng authentication liên quan. Nó không tự phân phối trust anchor tới applications.

### Bài 13–14. pg_hba.conf

~~~conf
hostssl appdb app_user 10.20.0.0/16 scram-sha-256
hostnossl all all 0.0.0.0/0 reject
hostnossl all all ::/0 reject
~~~

Phải đặt/kiểm tra thứ tự các rule thực tế để không có `host` rộng hơn nằm trước vô hiệu hóa ý định.

### Bài 15. pg_stat_ssl

~~~sql
SELECT ssl, version, cipher
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
~~~

### Bài 16–17. Hạn chế observability

`SHOW ssl` cho biết khả năng TLS của server, không phải kết nối hiện tại. `pg_stat_ssl.ssl=true` cho biết kết nối TLS đang dùng, nhưng server không tự biết client có bật verify-full hay không.

### Bài 18. psql

~~~bash
psql "host=db.shop.internal port=5432 dbname=shopdb user=shop_app sslmode=verify-full sslrootcert=/etc/shop/db-ca.crt"
~~~

### Bài 19–20. Sửa certificate

Certificate expired: kiểm tra thời gian máy, phát hành và triển khai certificate hợp lệ trước khi hết hạn. Host mismatch: cấp server certificate có SAN `db-service.internal` tại TLS endpoint tương ứng, hoặc sửa tên kết nối để khớp danh tính thực đã được chấp thuận; **không hạ sslmode**.

### Bài 21. Negative tests

Trong staging, thử CA không tin cậy và hostname không có trong SAN. Cả hai phải thất bại khi app/driver thực sự dùng verify-full.

### Bài 22–23. PGJDBC

~~~text
jdbc:postgresql://db.shop.internal:5432/shopdb?sslmode=verify-full&sslrootcert=/etc/shop/db-ca.crt
~~~

~~~java
Properties props = new Properties();
props.setProperty("sslmode", "verify-full");
props.setProperty("sslrootcert", "/etc/shop/db-ca.crt");
~~~

### Bài 24. Mật khẩu

URL/CLI và log có thể làm lộ secrets qua shell history, cấu hình chia sẻ hoặc monitoring. Sử dụng secret management, prompt hoặc cơ chế xác thực thích hợp và không log password.

### Bài 25–27. mTLS

mTLS yêu cầu PostgreSQL server xác minh **client certificate**, ngoài việc client xác minh server.

`sslrootcert` xác minh server; `sslcert` và `sslkey` là certificate/private key của client.

~~~conf
hostssl appdb app_user 10.20.0.0/16 scram-sha-256 clientcert=verify-full
~~~

Server cần CA trust phù hợp trong `ssl_ca_file` và identity/mapping đúng.

### Bài 28. Certificate identity

PostgreSQL có quy tắc ánh xạ certificate identity ↔ role/database user qua cấu hình authentication/`pg_ident.conf`. Chỉ có một CN bất kỳ không mặc nhiên cấp quyền đăng nhập `app_user`.

### Bài 29. Channel binding

Không. Nó liên kết authentication với TLS channel khi được hỗ trợ, nhưng vẫn cần CA/hostname verification đúng chính sách.

### Bài 30. PgBouncer

Không. Có hai hop có thể có hai TLS sessions/chính sách riêng. Phải xác minh PgBouncer kết nối PostgreSQL bằng chính sách TLS/CA/hostname phù hợp, không suy từ hop app→PgBouncer.

### Bài 31–32. Failover/CA rotation

Mỗi TLS endpoint được chọn khi failover cần certificate khớp service hostname hoặc identity client dùng. Khi rotate CA theo từng đợt, cần quản lý giai đoạn trust cả CA cũ và mới theo kế hoạch; gỡ A quá sớm khiến clients không xác minh được những nodes chưa chuyển.

### Bài 33. Server private key

Nếu private key lộ, kẻ tấn công có thể giả mạo endpoint theo điều kiện PKI. Chỉ dịch vụ được phép đọc và lưu khóa trong secret storage phù hợp.

### Bài 34. OpenSSL

~~~bash
openssl x509 -in server.crt -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

### Bài 35. TLS inventory

~~~sql
SELECT
    version,
    cipher,
    count(*) AS connections
FROM pg_stat_ssl
WHERE ssl
GROUP BY version, cipher
ORDER BY connections DESC;
~~~

### Bài 36. Pooling

Connections đã mở giữ trạng thái TLS từ handshake của chúng; rotation ảnh hưởng các TLS handshakes mới. Cần policy reconnect/connection lifetime và theo dõi việc chuyển đổi.

### Bài 37. Baseline

Ví dụ: verify-full trong app, trust anchor đúng, SAN khớp, server hostssl/TLS-only rules, TLS version/cipher đúng, test CA/hostname âm thất bại, pg_stat_ssl xác nhận phiên TLS, CA/key rotation, monitoring expiry và phân quyền SQL.

### Bài 38. Query security

Có. TLS không thay prepared statements chống SQL injection hoặc `GRANT`/RLS/tenant authorization.

### Bài 39. Unix socket

libpq có thể chọn Unix-domain socket khi không chỉ rõ TCP host trên Unix; TLS được thiết kế cho TCP và không nhất thiết được dùng trong kết nối local socket ấy. Chỉ rõ host và xem `pg_stat_ssl` khi kiểm thử.

### Bài 40. GSS encryption

GSS encryption là cơ chế khác với TLS/X.509; muốn chứng minh chính sách verify-full phải xác nhận cơ chế kết nối và điều chỉnh `gssencmode`/driver theo version được hỗ trợ, không mặc định chỉ từ `sslmode`.

## 43. Bảng tra cứu nhanh

| Nhu cầu | Tùy chọn/công cụ |
| --- | --- |
| Bắt buộc TLS và xác minh đúng server | `sslmode=verify-full` |
| Chỉ xác minh CA, chưa hostname | `sslmode=verify-ca` |
| Bắt TLS nhưng không tương đương verify-full | `sslmode=require` |
| Có thể fallback plaintext | `sslmode=prefer` |
| Chỉ định CA tin cậy phía client | `sslrootcert=/path/to/ca.crt` |
| Client certificate cho mTLS | `sslcert` |
| Client private key cho mTLS | `sslkey` |
| Bật TLS tại PostgreSQL | `ssl=on` |
| Chỉ định chứng chỉ server | `ssl_cert_file` |
| Chỉ định khóa riêng server | `ssl_key_file` |
| Trust client certificates ở server | `ssl_ca_file` |
| Thiết lập phiên bản TLS thấp nhất | `ssl_min_protocol_version` |
| Rule chỉ cho TLS TCP | `hostssl` trong `pg_hba.conf` |
| Rule chỉ cho plaintext TCP | `hostnossl` |
| Yêu cầu SCRAM | `scram-sha-256` |
| Bắt client certificate kèm SCRAM | `clientcert=verify-full` |
| Certificate-only authentication | `cert` auth method |
| Identity mapping | `pg_ident.conf` |
| Xem server bật SSL chưa | `SHOW ssl` |
| Xem phiên hiện tại có TLS | `pg_stat_ssl` + `pg_backend_pid()` |
| Xem TLS trong psql | `\conninfo` |
| Xem thông tin SAN/expiry | `openssl x509` |
| Kiểm tra chain/hostname ở lab | `openssl verify -verify_hostname` |
| Xem config cần restart | `pg_settings.pending_restart` |
| Java PostgreSQL TLS | PGJDBC `sslmode`/`sslrootcert` |
| TLS channel binding với SCRAM | `channel_binding` khi được hỗ trợ |
| Đảm bảo dữ liệu chỉ cho phép user phù hợp | `GRANT`, RLS, application ACL |

## 44. Checklist triển khai PostgreSQL TLS trong production

1. **Xác định mọi TCP endpoints** app, admin, batch, ETL, pooler, replica, proxy có thể sử dụng.
2. Đã biết TLS kết thúc tại PostgreSQL hay proxy nào chưa?
3. Từng hop mạng chứa dữ liệu cần được mã hóa ở đâu?
4. Có CA/tên DNS/IP được phê duyệt cho từng endpoint?
5. Mỗi server certificate có SAN đúng tên mà client thực dùng?
6. Client có dùng `sslmode=verify-full` và CA/trust store phù hợp?
7. Có kiểm thử CA sai và hostname sai **phải thất bại**?
8. Server có `ssl=on` và minimum protocol version phù hợp?
9. `pg_hba.conf` chỉ chấp nhận TLS trên những mạng bắt buộc?
10. Không có rule `host` sớm hơn vô tình cho phép plaintext?
11. Cả IPv4 và IPv6 đã được xem xét?
12. PostgreSQL auth có dùng cơ chế được phê duyệt như SCRAM/mTLS?
13. Client certificates nếu có được cấp riêng theo service?
14. `ssl_ca_file` và `sslrootcert` có được dùng đúng hai chiều?
15. Server private key và client private key được bảo vệ khỏi đọc trái phép?
16. Không có trust-all SSL factory/hostname-verification bypass?
17. Tài khoản ứng dụng có quyền SQL tối thiểu?
18. JDBC datasource/connection pool dùng đúng properties bảo mật?
19. Có kiểm tra phiên app qua `pg_stat_ssl`, không chỉ phiên DBA?
20. Mọi replica/failover/proxy có certificate và trust policy nhất quán?
21. Có lịch certificate rotation và cảnh báo expiry trước nhiều ngưỡng?
22. Có kế hoạch CA overlap khi đổi trust anchor?
23. Có quy trình xử lý key compromised/revocation?
24. Có kiểm soát phiên TLS đang mở khi rotation và pool reconnect?
25. Có kiểm tra TLS 1.2/1.3, cipher phù hợp và client compatibility?
26. Có đồng bộ thời gian cho clients/server?
27. Có phân biệt lỗi network, TLS, authentication và authorization?
28. Không ghi password/private key vào logs/CLI/source control?
29. Có chứng cứ về cấu hình client-side verify-full phục vụ audit?
30. Có runbook xử lý hostname/CA mismatch mà không hạ bảo mật?

## 45. Tổng kết

Để bảo vệ một kết nối PostgreSQL qua mạng, cần nhìn TLS như **một cơ chế vừa mã hóa vừa xác thực đúng endpoint**, không chỉ là việc bật tham số `ssl=on`.

Các nguyên tắc quan trọng:

1. **Mã hóa ≠ xác minh danh tính máy chủ ≠ xác thực người dùng.** TLS bảo vệ kênh, certificate verification xác nhận server, còn PostgreSQL authentication và SQL authorization kiểm soát ai được đăng nhập/làm gì.
2. **`sslmode=verify-full` là lựa chọn mặc định nên ưu tiên cho client TCP production.** Nó yêu cầu TLS, xác minh chuỗi tới CA tin cậy và kiểm tra tên DNS/IP phù hợp. `prefer` có thể fallback plaintext; `require` không thay thế hostname verification; `verify-ca` chưa kiểm tra đúng tên.
3. **Certificate server phải có SAN phù hợp** tên kết nối của ứng dụng. CA private key, server private key và client private key đều là secrets; chỉ phân phối public CA certificate/trust anchor cho clients.
4. **Phía server cũng cần chính sách TLS.** `ssl=on`, certificate/key hợp lệ và `hostssl`/`hostnossl` trong `pg_hba.conf` giúp ngăn kết nối plaintext không được phép, nhưng server không thể tự xác nhận client đã dùng verify-full.
5. **mTLS xác thực thêm client**, không thay `GRANT`/RLS và không làm client bớt cần xác minh server.
6. **Vận hành TLS là công việc liên tục:** quản lý CA/chain, DNS/SAN, rotation, expiry, revocation, proxy hops, failover, driver/JDK và kiểm thử âm. Không hạ cấp bảo mật để vượt lỗi certificate.

Một quy trình kiểm chứng ngắn gọn: **xác nhận endpoint/tên → cấp certificate đúng SAN → phân phối CA tin cậy → cấu hình `verify-full` → yêu cầu TLS phía server → kiểm tra kênh bằng `pg_stat_ssl` → thử CA/hostname sai phải thất bại → theo dõi vòng đời chứng chỉ**.

Khi tất cả các bước này được quản lý nhất quán từ ứng dụng đến PostgreSQL, TLS mới đem lại cả **tính bí mật trên đường truyền** lẫn **niềm tin rằng ứng dụng đang kết nối đúng máy chủ cơ sở dữ liệu**.

# TLS, kiểm tra chứng thư và hạn chế kết nối không bảo vệ

Khi ứng dụng kết nối MySQL qua mạng, dữ liệu SQL, kết quả truy vấn và thông tin xác thực đi qua một kênh truyền. Nếu kênh này không được bảo vệ, người có khả năng quan sát hoặc can thiệp lưu lượng mạng có thể đọc dữ liệu, sửa nội dung trao đổi hoặc giả mạo máy chủ. TLS (Transport Layer Security) bảo vệ dữ liệu trên đường truyền, đồng thời cho phép ứng dụng xác minh máy chủ MySQL đang kết nối.

Vận hành TLS an toàn cần ba lớp phối hợp: máy chủ được cấu hình chứng thư và phiên bản TLS phù hợp; ứng dụng xác minh chuỗi tin cậy và tên máy chủ; MySQL từ chối các kết nối không đáp ứng chính sách. Chỉ bật mã hóa mà bỏ qua xác minh danh tính máy chủ vẫn có thể để ứng dụng kết nối tới một máy chủ giả mạo.

## 1. Mục tiêu bảo vệ và các khái niệm cần biết

TLS bảo vệ kết nối MySQL theo ba mục tiêu chính:

- **Bí mật:** người nghe lén trên mạng không đọc được câu lệnh SQL, dữ liệu trả về hay thông tin xác thực trong phiên TLS.
- **Toàn vẹn:** dữ liệu bị sửa trên đường truyền sẽ bị phát hiện và phiên kết nối không tiếp tục như một phiên hợp lệ.
- **Xác thực máy chủ:** ứng dụng có thể kiểm tra máy chủ đang nói chuyện có chứng thư được một CA tin cậy cấp cho đúng tên DNS mà ứng dụng sử dụng hay không.

Một số thuật ngữ thường gặp:

| Thuật ngữ | Ý nghĩa trong kết nối MySQL |
|---|---|
| CA (Certificate Authority) | Tổ chức hoặc hệ thống nội bộ ký chứng thư và tạo chuỗi tin cậy. |
| Chứng thư máy chủ | Chứa khóa công khai, danh tính máy chủ và chữ ký của CA. MySQL gửi chứng thư này khi bắt đầu TLS. |
| Khóa riêng | Bí mật tương ứng với khóa công khai trong chứng thư. Tiến trình `mysqld` dùng khóa này; không được gửi cho ứng dụng. |
| SAN (Subject Alternative Name) | Danh sách DNS name hoặc địa chỉ IP mà chứng thư có hiệu lực. Tên ứng dụng kết nối phải khớp với SAN. |
| Chuỗi chứng thư | Chứng thư máy chủ và các chứng thư trung gian dẫn tới CA gốc được ứng dụng tin cậy. |
| mTLS | Mutual TLS: ngoài việc ứng dụng xác minh máy chủ, máy chủ còn yêu cầu và xác minh chứng thư của ứng dụng. |

TLS bảo vệ dữ liệu **trên đường truyền**. Nó không tự mã hóa dữ liệu trong tablespace, binary log, file export hay bản sao lưu; các vùng lưu trữ đó cần chính sách mã hóa và kiểm soát truy cập riêng. TLS cũng không thay thế xác thực tài khoản MySQL, phân quyền tối thiểu, firewall hoặc giám sát.

## 2. TLS diễn ra như thế nào khi kết nối MySQL

Với kết nối TCP, MySQL và client thương lượng TLS trước khi trao đổi thông tin đăng nhập và câu lệnh SQL. Ở mức khái quát, trình tự là:

1. Client mở kết nối TCP tới địa chỉ và cổng MySQL.
2. Client và server thương lượng phiên bản TLS cùng bộ mã hóa (cipher suite) mà cả hai hỗ trợ.
3. Server gửi chứng thư. Client kiểm tra chữ ký của chuỗi chứng thư, thời hạn và danh tính máy chủ theo tên DNS hoặc IP đang kết nối.
4. Nếu dùng mTLS, server yêu cầu client gửi chứng thư; server kiểm tra chứng thư đó theo CA và các điều kiện tài khoản.
5. Sau khi bắt tay TLS thành công, hai bên trao đổi thông tin xác thực MySQL và dữ liệu phiên làm việc bên trong kênh đã mã hóa.

TLS và xác thực MySQL là hai việc khác nhau. Chứng thư hợp lệ chứng minh danh tính ở tầng TLS; nó không tự cấp quyền truy cập schema. Ngược lại, mật khẩu MySQL đúng cũng không chứng minh client đang kết nối tới đúng máy chủ.

Các chế độ xác minh của MySQL client có ý nghĩa khác nhau:

| Chế độ `--ssl-mode` | Mã hóa kết nối | Xác minh CA | Xác minh tên máy chủ |
|---|---:|---:|---:|
| `DISABLED` | Không | Không | Không |
| `PREFERRED` | Có nếu thương lượng được; có thể fallback | Không đảm bảo | Không |
| `REQUIRED` | Có | Không | Không |
| `VERIFY_CA` | Có | Có | Không |
| `VERIFY_IDENTITY` | Có | Có | Có |

Với ứng dụng production, ưu tiên `VERIFY_IDENTITY`. `REQUIRED` chỉ yêu cầu kênh mã hóa, nên client vẫn có thể chấp nhận chứng thư không xác minh được danh tính. `VERIFY_CA` kiểm tra chuỗi tin cậy nhưng không bảo đảm chứng thư được cấp cho đúng máy chủ. `PREFERRED` có thể chuyển sang kết nối không mã hóa khi TLS không dùng được, vì vậy không phù hợp làm chính sách bắt buộc bảo vệ dữ liệu.

## 3. Chuẩn bị và kiểm tra chứng thư

Trong môi trường production, nên dùng chứng thư do CA doanh nghiệp hoặc CA được tổ chức tin cậy cấp. Máy chủ cần chứng thư, khóa riêng tương ứng và chuỗi CA cần thiết. Client cần CA gốc hoặc trust store chứa CA mà tổ chức đã phê duyệt.

Tên trong SAN của chứng thư phải khớp với địa chỉ mà client dùng để kết nối. Ví dụ, nếu ứng dụng kết nối tới `db.example.internal`, chứng thư cần có SAN `DNS:db.example.internal`. Nếu ứng dụng kết nối bằng IP, chứng thư phải có SAN kiểu IP tương ứng. Không nên dựa vào việc tên máy chủ tình cờ khớp với Common Name; hãy phát hành chứng thư với SAN rõ ràng.

Có thể kiểm tra thông tin chứng thư bằng OpenSSL:

```bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates -ext subjectAltName
```

Lệnh trên giúp xem chủ thể, CA cấp, thời hạn và SAN. Kiểm tra chuỗi tin cậy và tên DNS bằng:

```bash
openssl verify -CAfile ca.pem -verify_hostname db.example.internal server-cert.pem
```

Lệnh xác minh tên DNS cần phiên bản OpenSSL có hỗ trợ `-verify_hostname`. Nếu tổ chức dùng CA trung gian, cung cấp thêm chuỗi intermediate theo định dạng mà công cụ yêu cầu. Kết quả xác minh chứng thư bằng OpenSSL là một bước kiểm tra; vẫn cần thử kết nối bằng chính MySQL client hoặc driver mà ứng dụng sử dụng.

MySQL có thể tự tạo một số chứng thư tự ký khi khởi tạo data directory nếu chưa có chứng thư do người vận hành cung cấp. Chúng hữu ích cho một số môi trường thử nghiệm, nhưng không nên mặc định xem chúng là danh tính máy chủ đã được client tin cậy trong production. Hãy triển khai CA và chứng thư theo quy trình quản lý khóa của tổ chức.

Khóa riêng phải được bảo vệ nghiêm ngặt:

- Chỉ tài khoản hệ điều hành chạy `mysqld` và người quản trị được ủy quyền mới có quyền đọc khóa.
- Không đưa khóa riêng vào Git, image container dùng chung, log, ticket hoặc kho artifact công khai.
- Không dùng chung khóa riêng của máy chủ cho nhiều máy chủ nếu quy trình PKI có thể cấp khóa riêng biệt.
- Theo dõi ngày hết hạn và có kế hoạch thay thế trước khi chứng thư hết hạn.

## 4. Cấu hình TLS và bắt buộc kết nối an toàn ở máy chủ

Ví dụ cấu hình trong file cấu hình MySQL, thường nằm trong nhóm `[mysqld]`:

```ini
[mysqld]
ssl_ca=/etc/mysql/tls/ca.pem
ssl_cert=/etc/mysql/tls/server-cert.pem
ssl_key=/etc/mysql/tls/server-key.pem
tls_version=TLSv1.2,TLSv1.3
require_secure_transport=ON
```

Ý nghĩa các tùy chọn:

- `ssl_ca` chỉ CA mà server dùng để xác minh chứng thư client khi có yêu cầu xác thực chứng thư client.
- `ssl_cert` trỏ tới chứng thư máy chủ.
- `ssl_key` trỏ tới khóa riêng tương ứng với chứng thư máy chủ.
- `tls_version` giới hạn các phiên bản TLS được phép thương lượng. Danh sách cần tương thích với phiên bản MySQL, thư viện SSL/OpenSSL và client đang dùng.
- `require_secure_transport=ON` yêu cầu kết nối sử dụng transport an toàn. Với kết nối TCP từ xa, client phải dùng TLS; kết nối local qua Unix socket (và các transport local an toàn được MySQL hỗ trợ) vẫn có thể được chấp nhận.

Không bật các phiên bản TLS cũ chỉ để làm một client lỗi thời kết nối được. Nếu client không hỗ trợ TLS 1.2 hoặc TLS 1.3 theo chính sách, hãy nâng cấp client hoặc driver. TLS 1.3 phụ thuộc vào phiên bản MySQL và thư viện SSL/OpenSSL trong bản dựng; hãy kiểm tra tài liệu đúng phiên bản đang vận hành trước khi đặt cấu hình.

Sau khi triển khai, bảo đảm đường dẫn tồn tại, định dạng chứng thư hợp lệ, khóa khớp chứng thư và quyền đọc khóa phù hợp. Các thay đổi liên quan tới file chứng thư hoặc tùy chọn khởi động có thể cần nạp lại cấu hình TLS hoặc khởi động lại server, tùy phiên bản và tùy chọn. Thực hiện trong cửa sổ thay đổi đã kiểm soát và xác minh bằng một kết nối mới.

`require_secure_transport` là lớp kiểm soát ở cấp server. Khi bật, nó ngăn client TCP từ xa hạ cấp xuống kết nối không mã hóa, kể cả khi client không yêu cầu TLS. Nó không thay thế xác minh danh tính ở phía client: client vẫn cần cấu hình CA và chế độ `VERIFY_IDENTITY`.

## 5. Cấu hình MySQL client để xác minh máy chủ

Ví dụ kết nối bằng MySQL command-line client:

```bash
mysql \
  --protocol=TCP \
  --host=db.example.internal \
  --port=3306 \
  --user=orders_app \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/app/pki/company-root-ca.pem
```

`--password` khiến client hỏi mật khẩu tương tác, tránh ghi mật khẩu trực tiếp vào command line hoặc lịch sử shell. `--ssl-ca` chỉ CA mà client tin cậy để xác minh chứng thư server. `--host` cần là tên có trong SAN của chứng thư; nếu dùng một alias DNS khác, chứng thư cũng phải bao phủ alias đó.

Nếu chỉ dùng:

```bash
mysql --host=db.example.internal --user=orders_app --password --ssl-mode=REQUIRED
```

client yêu cầu mã hóa nhưng không xác minh đầy đủ danh tính server. Cấu hình này có thể phù hợp cho kiểm tra tạm thời trong môi trường kiểm soát, nhưng không đạt mục tiêu chống giả mạo máy chủ như `VERIFY_IDENTITY`.

Các thư viện ứng dụng có tên thuộc tính khác nhau. Ví dụ, MySQL Connector/J dùng thuộc tính `sslMode`; các driver khác có thể dùng các thuộc tính CA, trust store hoặc cờ xác minh chứng thư riêng. Khi cấu hình driver, cần xác nhận cả ba điều: TLS được bật, chuỗi CA được xác minh và hostname được xác minh. Một tùy chọn có tên chung như `ssl=true` không nhất thiết có nghĩa là đã xác minh hostname. Kiểm tra tài liệu driver và phiên bản cụ thể đang triển khai.

## 6. Bắt buộc TLS theo tài khoản MySQL

Ngoài chính sách toàn server, MySQL cho phép đặt yêu cầu TLS theo từng tài khoản. Ví dụ tạo tài khoản ứng dụng chỉ được kết nối từ một địa chỉ nguồn cụ thể và phải dùng TLS:

```sql
CREATE USER 'orders_app'@'10.20.30.41'
  IDENTIFIED BY RANDOM PASSWORD
  REQUIRE SSL;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON orders.*
  TO 'orders_app'@'10.20.30.41';
```

`IDENTIFIED BY RANDOM PASSWORD` yêu cầu MySQL tạo mật khẩu ngẫu nhiên; lưu mật khẩu được trả về vào secret manager theo quy trình của tổ chức. Trong thực tế, thay host mẫu bằng địa chỉ hoặc phạm vi nguồn thực tế và chỉ cấp quyền SQL mà ứng dụng cần.

Nếu tài khoản phải trình chứng thư client hợp lệ, dùng `REQUIRE X509`:

```sql
CREATE USER 'batch_client'@'10.20.30.52'
  IDENTIFIED BY RANDOM PASSWORD
  REQUIRE X509;
```

Khi đó client cần gửi chứng thư và khóa riêng của mình. Ví dụ:

```bash
mysql \
  --protocol=TCP \
  --host=db.example.internal \
  --user=batch_client \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/app/pki/company-root-ca.pem \
  --ssl-cert=/etc/app/pki/batch-client-cert.pem \
  --ssl-key=/etc/app/pki/batch-client-key.pem
```

`REQUIRE X509` buộc client có chứng thư được CA server tin cậy xác minh. Có thể ràng buộc chặt hơn theo chủ thể hoặc CA phát hành:

```sql
ALTER USER 'batch_client'@'10.20.30.52'
  REQUIRE SUBJECT '/CN=batch-client'
  AND ISSUER '/CN=Company Client CA';
```

Giá trị `SUBJECT` và `ISSUER` phải khớp với Distinguished Name thực tế trong chứng thư theo cách MySQL so sánh. Hãy lấy giá trị từ chứng thư được CA cấp và kiểm thử trước khi áp dụng cho tài khoản production; chuỗi ví dụ phía trên chỉ minh họa cú pháp.

Phân biệt các điều kiện:

- `REQUIRE SSL`: yêu cầu kết nối của tài khoản dùng SSL/TLS, nhưng không bắt buộc client có chứng thư riêng.
- `REQUIRE X509`: yêu cầu client trình chứng thư hợp lệ.
- `REQUIRE SUBJECT` và `REQUIRE ISSUER`: giới hạn thêm danh tính hoặc CA của chứng thư client.
- `require_secure_transport=ON`: áp dụng chính sách transport an toàn ở cấp server, hữu ích để ngăn kết nối TCP không mã hóa trên toàn hệ thống.

Lưu ý: `REQUIRE SSL` là điều kiện SSL/TLS của tài khoản. Một kết nối local qua Unix socket không phải phiên TLS, nên có thể không đáp ứng điều kiện này dù Unix socket được xem là transport an toàn bởi `require_secure_transport`. Khi thay đổi điều kiện tài khoản, kiểm tra cả các tác vụ quản trị local có sử dụng tài khoản đó.

Kiểm tra định nghĩa tài khoản và quyền hiện tại:

```sql
SHOW CREATE USER 'orders_app'@'10.20.30.41';
SHOW GRANTS FOR 'orders_app'@'10.20.30.41';
```

Không dùng tài khoản ứng dụng chung cho nhiều dịch vụ nếu có thể tách danh tính. Khi thu hồi hoặc thay chứng thư client, cập nhật đúng tài khoản và quy trình cấp phát chứng thư tương ứng.

## 7. Xác minh phiên kết nối đang được mã hóa

Sau khi kết nối bằng client, chạy các câu lệnh sau ngay trong **chính phiên cần kiểm tra**:

```sql
SHOW SESSION STATUS LIKE 'Ssl_version';
SHOW SESSION STATUS LIKE 'Ssl_cipher';
```

`Ssl_version` cho biết phiên bản TLS được thương lượng; `Ssl_cipher` cho biết cipher đang sử dụng. Nếu `Ssl_cipher` rỗng, phiên hiện tại không dùng TLS. Hãy xác nhận rằng bạn đang kiểm tra đúng kết nối TCP cần bảo vệ; kết nối local qua Unix socket có thể không có cipher TLS.

Kiểm tra chính sách và cấu hình server:

```sql
SHOW GLOBAL VARIABLES LIKE 'require_secure_transport';
SHOW GLOBAL VARIABLES LIKE 'tls_version';
SHOW GLOBAL VARIABLES LIKE 'ssl_ca';
SHOW GLOBAL VARIABLES LIKE 'ssl_cert';
SHOW GLOBAL VARIABLES LIKE 'ssl_key';
```

Có thể xem các bộ đếm TLS ở cấp server bằng:

```sql
SHOW GLOBAL STATUS LIKE 'Ssl_%';
```

Các bộ đếm này hỗ trợ theo dõi hoạt động TLS tổng thể, nhưng không thay thế việc kiểm tra `Ssl_version` và `Ssl_cipher` trên từng phiên. Cũng cần kiểm tra chính sách tài khoản qua `SHOW CREATE USER` và quyền truy cập qua `SHOW GRANTS`.

Một quy trình xác minh nên có cả kiểm tra thành công và kiểm tra bị từ chối:

1. Kết nối bằng `VERIFY_IDENTITY` và CA đúng; xác nhận phiên có `Ssl_version` và `Ssl_cipher`.
2. Kết nối bằng CA không tin cậy; client phải từ chối bắt tay.
3. Kết nối bằng hostname không khớp SAN; `VERIFY_IDENTITY` phải từ chối.
4. Với server đã bật `require_secure_transport`, thử kết nối TCP bằng `--ssl-mode=DISABLED`; server phải từ chối.
5. Với tài khoản `REQUIRE X509`, thử kết nối không gửi chứng thư client; server phải từ chối.

Ví dụ kiểm tra server từ chối TCP không mã hóa:

```bash
mysql \
  --protocol=TCP \
  --host=db.example.internal \
  --user=orders_app \
  --password \
  --ssl-mode=DISABLED
```

Chỉ chạy phép thử từ chối trong môi trường kiểm thử hoặc theo cửa sổ kiểm tra đã thống nhất. Không dùng một kết nối socket local để kết luận rằng server đang cho phép TCP không mã hóa.

## 8. Vận hành, thay chứng thư và xử lý sự cố

Chứng thư có thời hạn. Đưa ngày hết hạn vào giám sát, xác định người chịu trách nhiệm và bắt đầu gia hạn đủ sớm để có thời gian cập nhật client. Khi xoay vòng chứng thư hoặc CA, nên triển khai theo trình tự:

1. Cấp chứng thư mới với SAN đúng, thời hạn phù hợp và chuỗi CA đầy đủ.
2. Cài chứng thư cùng khóa riêng trên server; kiểm tra quyền đọc và tính tương ứng giữa khóa với chứng thư.
3. Cập nhật trust store của client để tin cậy CA mới. Nếu đổi CA, có thể cần giai đoạn chuyển tiếp trong đó client tin cả CA cũ và mới.
4. Nạp lại TLS theo cơ chế được phiên bản MySQL hỗ trợ hoặc khởi động lại server theo quy trình vận hành.
5. Mở kết nối mới bằng `VERIFY_IDENTITY`, xác minh phiên bản/cipher và thử các tình huống từ chối.
6. Chỉ loại bỏ CA cũ sau khi các client đã chuyển hoàn toàn và không còn phụ thuộc vào chuỗi cũ.

Ở các phiên bản MySQL hỗ trợ, có thể dùng câu lệnh sau để yêu cầu nạp lại cấu hình TLS sau khi thay file chứng thư:

```sql
ALTER INSTANCE RELOAD TLS;
```

Khả năng và hành vi nạp lại phụ thuộc phiên bản MySQL cùng loại thay đổi. Kiểm tra tài liệu đúng phiên bản trước khi dùng; nếu phiên bản không hỗ trợ hoặc thay đổi yêu cầu khởi động lại, thực hiện restart có kiểm soát. Sau khi nạp lại, tạo kết nối mới để xác minh chứng thư mới đã được dùng; các phiên hiện hữu có thể vẫn tiếp tục với trạng thái TLS đã thương lượng trước đó.

Các lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Client báo không tin cậy chứng thư | Thiếu CA gốc hoặc CA trung gian, dùng sai file CA, chuỗi chứng thư server chưa đầy đủ | Kiểm tra issuer/chain; cài CA được phê duyệt vào trust store; cấu hình đúng `--ssl-ca`. |
| `VERIFY_IDENTITY` thất bại nhưng `VERIFY_CA` thành công | Hostname hoặc IP kết nối không có trong SAN | Kết nối bằng DNS name đã cấp trong SAN hoặc phát hành lại chứng thư với SAN phù hợp. |
| Kết nối thất bại sau khi bật `require_secure_transport` | Client đang dùng TCP không mã hóa hoặc driver chưa cấu hình TLS | Bật TLS và xác minh CA/hostname trong driver; kiểm tra `Ssl_cipher` sau khi kết nối. |
| Tài khoản bị từ chối dù TLS đã bật | Tài khoản có `REQUIRE X509` nhưng client không gửi chứng thư, hoặc SUBJECT/ISSUER không khớp | Kiểm tra `SHOW CREATE USER`; kiểm tra chứng thư client và CA server tin cậy. |
| MySQL không khởi động hoặc không nạp được TLS | Sai đường dẫn, quyền đọc khóa, PEM không hợp lệ, khóa không khớp chứng thư | Kiểm tra error log, quyền file và cặp chứng thư/khóa; sửa cấu hình rồi nạp lại theo quy trình. |
| Client cũ không thương lượng được TLS | Phiên bản TLS hoặc cipher không còn được server cho phép | Nâng cấp driver/client; chỉ điều chỉnh chính sách sau khi đánh giá tương thích và rủi ro. |
| Kết nối hoạt động nhưng `Ssl_cipher` rỗng | Client đang dùng transport không mã hóa hoặc không phải phiên kết nối dự định kiểm tra | Xác nhận `--protocol=TCP`, chế độ SSL của driver và kiểm tra trong đúng session. |

Không khắc phục lỗi chứng thư bằng cách tắt kiểm tra CA/hostname hoặc hạ `tls_version` xuống giao thức cũ. Hãy tìm nguyên nhân ở chuỗi tin cậy, SAN, thời hạn, quyền file, driver hoặc cấu hình server.

## 9. Tình huống thực hành

Một dịch vụ đặt hàng kết nối tới MySQL tại `db.example.internal`. Yêu cầu là mọi kết nối TCP từ dịch vụ phải được mã hóa, ứng dụng phải xác minh đúng máy chủ, và server không chấp nhận kết nối TCP không mã hóa.

**Bước 1 — Chuẩn bị chứng thư.** Đội vận hành cấp chứng thư server từ CA nội bộ. SAN chứa `DNS:db.example.internal`. Khóa riêng chỉ cho tài khoản hệ điều hành chạy MySQL đọc; client được cấp CA gốc qua kênh phân phối tin cậy.

**Bước 2 — Bật TLS và chính sách server.** Cấu hình `ssl_ca`, `ssl_cert`, `ssl_key`, giới hạn `tls_version` theo phiên bản được hỗ trợ và đặt `require_secure_transport=ON`. Nạp cấu hình theo quy trình thay đổi của môi trường.

**Bước 3 — Tạo danh tính ứng dụng.** Tạo `orders_app` với host nguồn phù hợp, `REQUIRE SSL` và chỉ cấp quyền cần thiết trên schema `orders`. Mật khẩu được lưu trong secret manager.

**Bước 4 — Cấu hình ứng dụng.** Driver kết nối bằng hostname `db.example.internal`, tin cậy CA nội bộ và bật xác minh cả chuỗi CA lẫn hostname. Không xem việc bật một cờ `ssl` chung là bằng chứng đủ.

**Bước 5 — Kiểm tra.** Kết nối thành công phải hiển thị phiên bản TLS và cipher trong session. Kết nối với CA sai hoặc hostname không khớp phải thất bại ở client. Kết nối TCP với TLS bị tắt phải bị server từ chối.

Nếu dịch vụ có yêu cầu xác thực hai chiều, cấp thêm chứng thư riêng cho client, cấu hình `ssl_cert` và `ssl_key` phía ứng dụng, đồng thời đổi điều kiện tài khoản sang `REQUIRE X509` hoặc ràng buộc SUBJECT/ISSUER phù hợp. Việc này tăng mức xác thực nhưng cũng làm quy trình cấp phát, thu hồi và xoay vòng chứng thư client trở nên quan trọng hơn.

## 10. Checklist trước khi đưa vào production

- [ ] Server có chứng thư do CA được phê duyệt cấp; SAN khớp hostname/IP mà client sử dụng.
- [ ] Khóa riêng có quyền đọc tối thiểu và không xuất hiện trong repository, log hoặc artifact dùng chung.
- [ ] Server chỉ cho phép các phiên bản TLS còn được tổ chức hỗ trợ.
- [ ] `require_secure_transport=ON` được bật và đã kiểm thử với kết nối TCP.
- [ ] Client dùng `VERIFY_IDENTITY` hoặc cơ chế tương đương có xác minh CA lẫn hostname.
- [ ] Tài khoản ứng dụng có host nguồn và quyền SQL tối thiểu; dùng `REQUIRE SSL` hoặc `REQUIRE X509` theo yêu cầu.
- [ ] Đã kiểm tra `Ssl_version` và `Ssl_cipher` trong phiên ứng dụng thực tế.
- [ ] Các phép thử CA sai, hostname sai, thiếu TLS và thiếu chứng thư client (nếu dùng mTLS) đều bị từ chối.
- [ ] Có giám sát hạn chứng thư, quy trình gia hạn, xoay vòng CA và phương án khôi phục.
- [ ] Có chính sách riêng để bảo vệ dữ liệu lưu trữ, binary log và bản sao lưu.

Khi các bước này được áp dụng đồng bộ, kết nối MySQL được mã hóa, ứng dụng có cơ sở xác minh đúng máy chủ và server có thể từ chối các kết nối không đáp ứng chính sách bảo vệ dữ liệu trên đường truyền.

# Oracle Net encryption, TLS/TCPS, wallet và quản lý chứng thư

Kết nối Oracle Net đi qua mạng giữa client, listener và database service. Nếu dữ liệu truyền qua mạng không được bảo vệ, người có khả năng quan sát đường truyền có thể đọc thông tin nhạy cảm; nếu client không xác minh đúng máy chủ, nó còn có nguy cơ kết nối tới endpoint giả mạo. Một cấu hình an toàn cần xác định rõ hai mục tiêu: **bảo mật dữ liệu trên đường truyền** và **xác thực danh tính đầu bên kia**.

Oracle hỗ trợ hai hướng bảo vệ thường gặp:

- **Native Network Encryption (NNE)**: mã hóa và kiểm tra tính toàn vẹn ở tầng Oracle Net trên kết nối TCP. Cấu hình bằng các tham số SQLNET.ENCRYPTION_* và SQLNET.CRYPTO_CHECKSUM_*; không cần chứng thư TLS.
- **TLS qua TCPS**: Oracle Net chạy trên TLS. TLS bảo vệ kênh truyền, xác thực máy chủ bằng chứng thư và có thể yêu cầu chứng thư client để mutual TLS (mTLS). Cấu hình listener/client bằng protocol TCPS và wallet hoặc trust store phù hợp.

Wallet của Oracle có thể chứa private key, user certificate và trusted certificates. Wallet phải được tạo, bảo vệ, phân phối, gia hạn và thu hồi theo quy trình PKI. Một wallet sai đường dẫn, thiếu intermediate CA, chứng thư hết hạn hoặc hostname không khớp đều có thể làm kết nối thất bại.

Bài học này dùng Oracle Database 19c làm mốc và trình bày:
- Phân biệt NNE, TLS và TCPS.
- Cấu hình mã hóa/integrity cho TCP.
- Cấu hình TCPS listener, client connect descriptor và wallet.
- Tạo private key/CSR, import CA chain và user certificate bằng orapki.
- Server-auth TLS và mutual TLS.
- Kiểm tra hostname/SAN/DN, expiry, trust chain và TLS policy.
- Kết nối SQL*Plus, JDBC Thin và OCI.
- Gia hạn, xoay vòng, backup và thu hồi chứng thư.
- Kiểm tra kết nối, chẩn đoán lỗi và vận hành an toàn.

Cú pháp một số tham số, TLS version/cipher và hành vi driver phụ thuộc Oracle release, Release Update, JDK và platform. Luôn đối chiếu Oracle Net Services Administrator's Guide, JDBC Developer's Guide và tài liệu PKI đúng phiên bản trước khi áp dụng production.

## 1. Mục tiêu bảo mật của kết nối Oracle Net

Một kết nối database an toàn thường cần các thuộc tính sau:

1. **Confidentiality**: dữ liệu truyền không thể đọc được nếu bị nghe lén trên mạng.
2. **Integrity**: dữ liệu không bị sửa đổi mà client/server không phát hiện.
3. **Server authentication**: client xác minh đang kết nối đúng database endpoint.
4. **Client authentication**: server xác minh danh tính client nếu mô hình yêu cầu.
5. **Lifecycle management**: chứng thư và khóa được gia hạn, thay thế, thu hồi đúng hạn.
6. **Operational control**: log, wallet password, private key, quyền file và thay đổi cấu hình được quản lý.

Mã hóa không tự giải quyết mọi vấn đề. Ví dụ, TCPS bảo vệ dữ liệu trên đường truyền nhưng không ngăn tài khoản database có quyền quá rộng đọc dữ liệu sau khi kết nối. TLS cũng không thay thế authentication/authorization ở database, auditing, network segmentation hoặc bảo vệ endpoint.

### 1.1. Bảo vệ dữ liệu khi truyền và khi lưu

| Phạm vi | Công nghệ/kiểm soát thường dùng |
| --- | --- |
| Client ↔ listener/database | TCPS/TLS hoặc Native Network Encryption |
| Dữ liệu trong datafile/backup | Transparent Data Encryption (TDE), backup encryption |
| Xác thực người dùng database | Password, Kerberos, certificate/external authentication, enterprise identity |
| Quyền truy cập | Roles, privileges, schemas, Database Vault nếu phù hợp |
| Bí mật ứng dụng | Secret manager, Oracle wallet/external password store, OS permissions |

Không nhầm Oracle Net wallet với TDE keystore. Chúng đều có thể dùng khái niệm wallet/keystore nhưng phục vụ mục đích và cấu hình khác nhau. Wallet dùng cho TLS/Oracle Net giữ chứng thư và private key để bảo vệ kết nối; TDE keystore giữ master encryption keys cho dữ liệu at rest.

## 2. NNE, TLS và TCPS khác nhau thế nào?

### 2.1. Native Network Encryption

NNE là cơ chế Oracle Net mã hóa dữ liệu và có thể kiểm tra tính toàn vẹn trên TCP. Hai phía thương lượng thuật toán dựa trên policy của client/server.

Đặc điểm:
- Cấu hình qua sqlnet.ora.
- Có thể dùng AES cho encryption và SHA cho crypto-checksum.
- Không cần CA certificate hoặc wallet TLS.
- Bảo vệ nội dung Oracle Net trên đường truyền.
- Không cung cấp mô hình certificate-based server identity như TLS.

NNE phù hợp khi cần mã hóa Oracle Net trên TCP trong môi trường đã có cách xác thực endpoint khác và muốn dùng cơ chế native của Oracle.

### 2.2. TLS

TLS là giao thức bảo mật tầng transport. Nó cung cấp encryption, integrity và cơ chế xác thực certificate. Trong TLS handshake, client và server thương lượng phiên bản/cipher suite, xác minh chứng thư và thiết lập session keys.

Chứng thư server thường được CA ký. Client cần trust CA chain và xác minh server identity. Nếu bật mTLS, server cũng yêu cầu và xác minh certificate của client.

### 2.3. TCPS

TCPS là Oracle Net protocol sử dụng TLS. Khi connect descriptor dùng PROTOCOL=TCPS, Oracle Net thực hiện kết nối TLS trước khi trao đổi Oracle Net protocol.

Ví dụ:
- TCP listener thường dùng port 1521.
- TCPS thường được cấu hình trên port 2484.

Port 2484 là quy ước thường gặp, không phải yêu cầu bắt buộc. Có thể dùng port khác nếu listener, firewall, load balancer và client cùng cấu hình.

### 2.4. So sánh

| Tiêu chí | NNE trên TCP | TLS qua TCPS |
| --- | --- | --- |
| Network protocol | TCP | TCPS |
| Mã hóa dữ liệu | Có | Có |
| Integrity | Crypto-checksum | TLS record integrity |
| Certificate/CA | Không bắt buộc | Có |
| Xác thực danh tính server bằng certificate | Không | Có |
| Mutual TLS | Không theo cơ chế TLS | Có thể bật |
| Cấu hình chính | SQLNET.ENCRYPTION/CRYPTO_CHECKSUM | Listener TCPS, wallet, TLS parameters |
| Client compatibility | Oracle Net client hỗ trợ NNE | Client/driver hỗ trợ TCPS và trust store |

Không nên suy luận rằng bật NNE đồng nghĩa đã có TLS server identity validation. Cũng không coi TCPS chỉ là một tên khác của NNE. Chọn một mô hình theo yêu cầu bảo mật, khả năng tương thích và chính sách PKI của tổ chức.

## 3. Native Network Encryption trên TCP

Nếu chỉ cần mã hóa và integrity ở tầng Oracle Net, NNE có thể được cấu hình mà không đổi TCP listener sang TCPS.

### 3.1. Cấu hình phía server

Trong sqlnet.ora của Oracle server:

~~~text
SQLNET.ENCRYPTION_SERVER = REQUIRED
SQLNET.ENCRYPTION_TYPES_SERVER = (AES256, AES192, AES128)

SQLNET.CRYPTO_CHECKSUM_SERVER = REQUIRED
SQLNET.CRYPTO_CHECKSUM_TYPES_SERVER = (SHA512, SHA384, SHA256)
~~~

Ý nghĩa:
- REQUIRED yêu cầu phía kết nối phải thương lượng được dịch vụ tương ứng.
- ENCRYPTION_TYPES_SERVER liệt kê thuật toán encryption được chấp nhận.
- CRYPTO_CHECKSUM_SERVER yêu cầu kiểm tra integrity.
- CRYPTO_CHECKSUM_TYPES_SERVER liệt kê thuật toán checksum được chấp nhận.

Tên thuật toán và mức hỗ trợ phải khớp với release/RU của cả client lẫn server. Ví dụ trên minh họa một policy hiện đại; hãy kiểm tra danh sách thuật toán được Oracle hỗ trợ trên môi trường thực tế.

### 3.2. Cấu hình phía client

Trong sqlnet.ora của client:

~~~text
SQLNET.ENCRYPTION_CLIENT = REQUESTED
SQLNET.ENCRYPTION_TYPES_CLIENT = (AES256, AES192, AES128)

SQLNET.CRYPTO_CHECKSUM_CLIENT = REQUESTED
SQLNET.CRYPTO_CHECKSUM_TYPES_CLIENT = (SHA512, SHA384, SHA256)
~~~

REQUESTED cho biết client yêu cầu dịch vụ nhưng vẫn cho phép negotiation theo policy. Khi server đặt REQUIRED, client phải hỗ trợ và thương lượng được thuật toán tương thích; nếu không, kết nối bị từ chối.

Có thể đặt REQUIRED ở cả hai phía nếu chính sách yêu cầu bắt buộc và tất cả client đã được kiểm kê/kiểm thử. Không thay đổi server sang REQUIRED trước khi xác nhận mọi ứng dụng, batch, monitoring agent và công cụ quản trị đều hỗ trợ.

### 3.3. ACCEPTED, REQUESTED và REQUIRED

Các giá trị policy có ý nghĩa khác nhau:
- ACCEPTED: chấp nhận dịch vụ nếu phía bên kia yêu cầu và có thể thương lượng.
- REQUESTED: yêu cầu dịch vụ nhưng negotiation vẫn phụ thuộc policy phía còn lại.
- REQUIRED: kết nối phải sử dụng dịch vụ, nếu không sẽ thất bại.

Chi tiết negotiation và kết quả khi client/server dùng các giá trị khác nhau cần đối chiếu bảng tương thích trong Oracle Net Services Reference. Không dựa vào việc “kết nối vẫn thành công” để kết luận encryption đã được bật.

### 3.4. Kiểm tra NNE

Sau khi kết nối, xem banner dịch vụ mạng của session:

~~~sql
SELECT
    sid,
    serial#,
    network_service_banner
FROM v$session_connect_info
WHERE sid = SYS_CONTEXT('USERENV', 'SID');
~~~

Output có thể chứa dòng mô tả Encryption service và Crypto-checksumming service cùng thuật toán được thương lượng. Nội dung banner cụ thể tùy phiên bản và cấu hình.

Nếu không thấy dịch vụ encryption/integrity như mong đợi:
- Xác nhận client đang đọc đúng sqlnet.ora.
- Xác nhận server đang đọc đúng sqlnet.ora.
- Kiểm tra Oracle Home/TNS_ADMIN của process.
- Kiểm tra policy và danh sách thuật toán có giao nhau.
- Xác nhận kết nối thực sự đi qua Oracle Net client được cấu hình.
- Kiểm tra listener/server log khi negotiation thất bại.

NNE không dùng wallet TLS. Không tạo wallet chỉ để bật SQLNET.ENCRYPTION_*.

## 4. TLS handshake và chứng thư số

TLS dựa trên public key infrastructure (PKI). Một certificate liên kết danh tính với public key và được CA ký để bên nhận có thể kiểm tra tính tin cậy.

### 4.1. Thành phần của certificate

Chứng thư X.509 thường có:
- Subject: danh tính chủ thể.
- Issuer: CA phát hành chứng thư.
- Subject Public Key Info: public key.
- Serial Number: số serial do CA cấp.
- Validity: Not Before và Not After.
- Subject Alternative Name (SAN): DNS name/IP mà chứng thư đại diện.
- Key Usage và Extended Key Usage.
- Signature Algorithm và chữ ký CA.

Private key tương ứng không nằm trong certificate công khai. Private key phải được bảo vệ trong wallet hoặc keystore.

### 4.2. Root CA, intermediate CA và leaf certificate

Chuỗi tin cậy thường có dạng:

~~~text
Client trust store
       |
       v
Root CA (trust anchor)
       |
       v
Intermediate CA
       |
       v
Server leaf certificate
       |
       v
TLS endpoint: db.example.com
~~~

Root CA là trust anchor được client tin cậy. Intermediate CA được root hoặc CA cấp cao hơn ký. Leaf certificate được cấp cho server hoặc client endpoint.

Nếu server chỉ gửi leaf certificate nhưng thiếu intermediate, một số client không thể xây dựng chain và sẽ báo lỗi validation. Cần cài đầy đủ chain theo hướng dẫn của CA và Oracle wallet.

### 4.3. Server certificate và SAN

Certificate server phải đại diện cho hostname mà client dùng để kết nối. Nếu ứng dụng kết nối db-prod.example.com, certificate cần SAN DNS tương ứng. Không nên chỉ dựa vào Common Name (CN); SAN là nơi hiện đại dùng để xác định DNS/IP identity.

Nếu client kết nối bằng IP, certificate phải có IP SAN phù hợp hoặc ứng dụng phải dùng DNS name nằm trong SAN. Cấu hình DNS alias, load balancer và failover cần được đưa vào danh sách SAN/identity theo kiến trúc thực tế.

### 4.4. DN matching

Oracle Net có tham số SSL_SERVER_DN_MATCH để yêu cầu client kiểm tra danh tính server trong certificate. Có thể chỉ định SSL_SERVER_CERT_DN trong connect descriptor để ràng buộc DN mong đợi.

Ví dụ connect descriptor:

~~~text
ORCL_TCPS =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCPS)
      (HOST = db-prod.example.com)
      (PORT = 2484)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = orclpdb.example.com)
    )
    (SECURITY =
      (SSL_SERVER_DN_MATCH = YES)
    )
  )
~~~

Khi dùng explicit DN pinning, thêm SSL_SERVER_CERT_DN theo đúng DN của certificate server và cú pháp client đang dùng. Không copy DN minh họa vào production; lấy DN thực tế từ certificate và xác nhận cách so khớp của driver/release.

Bật server DN matching là bước quan trọng chống kết nối nhầm endpoint. Chỉ mã hóa TLS mà không xác minh danh tính server có thể để lại nguy cơ man-in-the-middle nếu trust/identity validation bị bỏ qua.

## 5. Oracle Wallet là gì?

Oracle Wallet là container bảo mật dùng để lưu trữ certificate, private key và trusted certificate. Wallet cũng có thể được dùng cho các mục đích khác như secure external password store; chức năng cụ thể phụ thuộc nội dung và cách ứng dụng cấu hình.

### 5.1. Các file thường gặp

Một wallet dạng PKCS#12 có thể có:
- ewallet.p12: wallet được bảo vệ bằng password.
- cwallet.sso: auto-login wallet, cho phép process truy cập wallet theo cơ chế auto-login mà không cần nhập password mỗi lần.

Tên file và cách tạo phụ thuộc loại wallet/công cụ. Không sửa hoặc đổi tên file wallet tùy tiện.

### 5.2. Wallet chứa gì?

Một wallet TLS có thể chứa:
- User certificate của server hoặc client.
- Private key tương ứng với user certificate.
- Trusted root CA certificates.
- Trusted intermediate CA certificates.
- Certificate revocation information nếu được cấu hình/hỗ trợ.

Server wallet cần identity certificate/private key cho TLS server. Client trust wallet cần CA chain để xác minh server. Trong mTLS, server cần trust client CA và client cần identity certificate/private key cùng trust chain của server.

### 5.3. Wallet password và auto-login

Wallet password bảo vệ file wallet có password. Auto-login wallet giúp listener/client process mở wallet mà không phải nhập password tương tác. Đổi lại, quyền truy cập file auto-login trở thành một phần quan trọng của security boundary.

- Giới hạn quyền đọc thư mục và file wallet cho OS account cần thiết.
- Không commit wallet vào Git hoặc đưa vào image/container công khai.
- Không gửi private key qua email/chat.
- Mã hóa backup và giới hạn người được khôi phục.
- Theo dõi quyền file sau khi copy/restore.
- Nếu dùng auto-login local, lưu ý wallet được ràng buộc với môi trường/máy tạo theo cơ chế của Oracle; kiểm tra khả năng sử dụng khi chuyển host.

## 6. Tạo wallet và chuẩn bị CA chain bằng orapki

orapki là tiện ích Oracle PKI dùng để quản lý wallet, certificate request, trusted certificate và CRL. Đường dẫn chương trình phụ thuộc Oracle Home, thường nằm dưới ORACLE_HOME/bin.

Các lệnh dưới đây là ví dụ cho môi trường Linux. Dùng thư mục wallet riêng cho từng mục đích và thay password/đường dẫn bằng secret được quản lý an toàn. Không đặt password thật vào tài liệu, source code hoặc shell history.

### 6.1. Tạo thư mục wallet

Ví dụ:

~~~bash
mkdir -p /u01/app/oracle/admin/ORCL/wallet/tcps_server
chmod 700 /u01/app/oracle/admin/ORCL/wallet/tcps_server
~~~

Thư mục phải thuộc OS account mà listener/database process cần dùng. Trên Windows, dùng ACL tương ứng thay vì chmod.

### 6.2. Tạo wallet

~~~bash
orapki wallet create \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -pwd '<WALLET_PASSWORD>' \
  -auto_login
~~~

Lệnh tạo wallet có password và auto-login file. Cần kiểm tra output và file được tạo. Một số môi trường dùng -auto_login_local để ràng buộc auto-login wallet với host; chỉ dùng khi quy trình triển khai yêu cầu và đã kiểm tra khả năng khôi phục/migration.

Không dùng password placeholder trong production. Truyền password qua cơ chế bảo mật phù hợp với môi trường và chính sách shell/automation.

### 6.3. Import root CA và intermediate CA

Giả sử CA cung cấp:
- root-ca.pem
- issuing-ca.pem

Thêm các trusted certificate:

~~~bash
orapki wallet add \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -trusted_cert \
  -cert root-ca.pem \
  -pwd '<WALLET_PASSWORD>'

orapki wallet add \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -trusted_cert \
  -cert issuing-ca.pem \
  -pwd '<WALLET_PASSWORD>'
~~~

Root và intermediate phải đến từ nguồn PKI đáng tin cậy. Xác minh fingerprint qua kênh độc lập trước khi trust; không import certificate chỉ vì nó được gửi kèm một email/request không xác thực.

### 6.4. Tạo private key và certificate request

Tạo key pair trong wallet và sinh certificate request:

~~~bash
orapki wallet add \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -dn "CN=db-prod.example.com,OU=Database,O=Example Corp,C=VN" \
  -keysize 2048 \
  -pwd '<WALLET_PASSWORD>'

orapki wallet export \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -dn "CN=db-prod.example.com,OU=Database,O=Example Corp,C=VN" \
  -request /secure/requests/db-prod.csr \
  -pwd '<WALLET_PASSWORD>'
~~~

Private key được tạo trong wallet; CSR chứa public key và thông tin subject, không chứa private key. Gửi CSR cho CA theo quy trình cấp chứng thư. CA phải cấp SAN DNS phù hợp, key usage và extended key usage phù hợp với TLS server.

Không tự ý tạo private key bằng một công cụ khác rồi import riêng nếu chưa hiểu quy trình ghép key/certificate của wallet. Tạo key trong wallet rồi export CSR thường giúp Oracle giữ private key ở đúng vị trí.

### 6.5. Import certificate do CA ký

Sau khi CA trả certificate leaf và chain:

~~~bash
orapki wallet add \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -user_cert \
  -cert db-prod-server.crt \
  -pwd '<WALLET_PASSWORD>'
~~~

Certificate leaf phải khớp public key của CSR đã tạo trong wallet. Nếu import sai certificate/key pair, wallet có thể từ chối hoặc TLS handshake không thành công.

### 6.6. Xem nội dung wallet

~~~bash
orapki wallet display \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -complete \
  -pwd '<WALLET_PASSWORD>'
~~~

Kiểm tra:
- User certificate đúng Subject/SAN.
- Issuer đúng CA.
- Validity còn hiệu lực.
- Trusted certificate có root/intermediate cần thiết.
- Wallet có private key identity phù hợp.
- Không có certificate cũ hoặc CA không còn được phép trust.

Cũng có thể kiểm tra certificate file bằng OpenSSL:

~~~bash
openssl x509 -in db-prod-server.crt -noout -subject -issuer -dates -ext subjectAltName
~~~

Nếu file DER, cần dùng option phù hợp để đọc. OpenSSL chỉ là công cụ xem certificate; wallet vẫn cần được quản lý theo Oracle PKI workflow.

## 7. Cấu hình TCPS listener phía server

Listener cần lắng nghe địa chỉ TCPS. Có thể giữ cả TCP và TCPS trong thời gian migration, nhưng phải có kế hoạch loại bỏ TCP nếu policy yêu cầu mọi client dùng TLS.

### 7.1. Ví dụ listener.ora

~~~text
LISTENER_TCPS =
  (DESCRIPTION_LIST =
    (DESCRIPTION =
      (ADDRESS =
        (PROTOCOL = TCPS)
        (HOST = db-prod.example.com)
        (PORT = 2484)
      )
    )
  )
~~~

HOST phải là hostname mà client sử dụng và certificate có thể xác thực. Nếu có nhiều NIC, VIP, SCAN hoặc load balancer, cấu hình phải phản ánh endpoint thực tế.

### 7.2. Wallet location trong sqlnet.ora

Ví dụ cấu hình Oracle Net phía server:

~~~text
WALLET_LOCATION =
  (SOURCE =
    (METHOD = FILE)
    (METHOD_DATA =
      (DIRECTORY = /u01/app/oracle/admin/ORCL/wallet/tcps_server)
    )
  )

SSL_CLIENT_AUTHENTICATION = FALSE
~~~

Đặt cấu hình trong Oracle Net admin directory mà listener process thực sự sử dụng, thường là TNS_ADMIN hoặc network/admin của Oracle Home. Nếu listener chạy dưới Oracle Home khác, nó có thể đọc file sqlnet.ora khác với database client của DBA.

Với server-auth TLS, SSL_CLIENT_AUTHENTICATION=FALSE cho biết server không bắt buộc client trình certificate. Client vẫn có thể xác thực vào database bằng username/password hoặc phương thức database authentication được cấu hình.

Nếu triển khai mTLS, đặt SSL_CLIENT_AUTHENTICATION=TRUE và cấu hình trust client CA phù hợp trong server wallet. Kiểm tra tài liệu Oracle release về yêu cầu authentication service và certificate mapping.

### 7.3. Khởi động và kiểm tra listener

~~~bash
lsnrctl start LISTENER_TCPS
lsnrctl status LISTENER_TCPS
lsnrctl services LISTENER_TCPS
~~~

Nếu listener đã chạy, áp dụng thay đổi bằng reload/restart theo quy trình vận hành và xác nhận listener đang dùng wallet/config đúng. Không giả định sửa file tự động có hiệu lực với process đang chạy.

Kiểm tra log listener để xác nhận endpoint TCPS đã được bind và service đăng ký. Nếu listener không mở được wallet, kiểm tra Oracle Home, TNS_ADMIN, quyền thư mục và wallet path.

## 8. Cấu hình client kết nối TCPS

Client cần dùng protocol TCPS, xác minh server certificate và tin cậy CA chain.

### 8.1. Client trust wallet

Tạo wallet riêng cho client, thêm root/intermediate CA của server:

~~~bash
orapki wallet create \
  -wallet /opt/app/oracle/wallet/db_trust \
  -pwd '<CLIENT_WALLET_PASSWORD>' \
  -auto_login

orapki wallet add \
  -wallet /opt/app/oracle/wallet/db_trust \
  -trusted_cert \
  -cert root-ca.pem \
  -pwd '<CLIENT_WALLET_PASSWORD>'

orapki wallet add \
  -wallet /opt/app/oracle/wallet/db_trust \
  -trusted_cert \
  -cert issuing-ca.pem \
  -pwd '<CLIENT_WALLET_PASSWORD>'
~~~

Client chỉ cần trust CA chain nếu server-auth TLS dùng certificate do CA này cấp. Không cần copy private key server sang client.

### 8.2. Client sqlnet.ora

~~~text
WALLET_LOCATION =
  (SOURCE =
    (METHOD = FILE)
    (METHOD_DATA =
      (DIRECTORY = /opt/app/oracle/wallet/db_trust)
    )
  )

SSL_SERVER_DN_MATCH = YES
~~~

SSL_SERVER_DN_MATCH=YES yêu cầu client xác minh server identity theo quy tắc Oracle Net. Kết nối phải dùng hostname/DN phù hợp certificate. Không tắt DN matching chỉ để làm cho một kết nối sai hostname chạy được.

### 8.3. tnsnames.ora

~~~text
ORCL_TCPS =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCPS)
      (HOST = db-prod.example.com)
      (PORT = 2484)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = orclpdb.example.com)
    )
    (SECURITY =
      (SSL_SERVER_DN_MATCH = YES)
    )
  )
~~~

SERVICE_NAME phải là service database đã đăng ký với listener. SID và SERVICE_NAME không phải lúc nào cũng có thể thay thế cho nhau.

Nếu cần ràng buộc certificate DN cụ thể, có thể thêm SSL_SERVER_CERT_DN trong SECURITY theo cú pháp của Oracle Net client đang dùng. Lấy DN thực tế từ certificate; không dùng DN minh họa.

### 8.4. Kiểm tra name resolution và kết nối

~~~bash
tnsping ORCL_TCPS
sqlplus -L app_user@ORCL_TCPS
~~~

tnsping hữu ích để kiểm tra alias resolution và khả năng tiếp cận listener ở mức Oracle Net naming, nhưng không chứng minh login database thành công hoặc certificate validation đã đúng toàn bộ. Hãy thực hiện login thật và kiểm tra server identity/encryption.

Không đặt password trực tiếp trong command line hoặc script chia sẻ. Để client hỏi password tương tác hoặc dùng secret store phù hợp.

## 9. Mutual TLS (mTLS) và client certificate authentication

Trong server-auth TLS thông thường, client xác minh server certificate; server không bắt buộc client certificate. Với mTLS, hai phía đều trình certificate:
- Client xác minh certificate server.
- Server xác minh certificate client.

mTLS phù hợp khi cần danh tính máy/ứng dụng ở tầng TLS, ví dụ service-to-database trong môi trường kiểm soát certificate. Nó bổ sung lớp xác thực transport, nhưng không tự động thay thế database user/role authorization.

### 9.1. Wallet phía server

Server wallet cần:
- Server identity certificate/private key.
- Trusted CA chain có thể xác minh certificate client.

Ví dụ server sqlnet.ora:

~~~text
WALLET_LOCATION =
  (SOURCE =
    (METHOD = FILE)
    (METHOD_DATA =
      (DIRECTORY = /u01/app/oracle/admin/ORCL/wallet/tcps_server)
    )
  )

SSL_CLIENT_AUTHENTICATION = TRUE
~~~

Nếu client certificate do CA khác cấp, thêm CA root/intermediate đó vào trusted certificates của server wallet.

### 9.2. Wallet phía client

Client wallet cần:
- Client identity certificate/private key.
- Trusted CA chain xác minh server certificate.

Tạo key/CSR trong client wallet tương tự server wallet, nhưng Subject/SAN và certificate policy phải đại diện cho client identity theo PKI của tổ chức. Gửi CSR cho CA cấp clientAuth certificate rồi import certificate vào wallet.

### 9.3. Xác thực certificate khác với database authorization

Có thể phân biệt:
- TLS handshake: xác minh client certificate được CA tin cậy cấp và còn hiệu lực.
- Oracle authentication: ánh xạ certificate hoặc thông tin đăng nhập thành database identity theo cấu hình.
- Authorization: kiểm tra user được phép SELECT/INSERT/EXECUTE trên object nào.

Nếu dùng certificate để đăng nhập Oracle externally authenticated user, cần cấu hình Oracle SSL authentication/enterprise user mapping đúng tài liệu. Nếu dùng mTLS như lớp xác thực transport bổ sung và vẫn dùng database username/password, xác định rõ hai lớp identity và cách audit chúng.

### 9.4. Không dùng một client certificate cho mọi ứng dụng

Mỗi service/ứng dụng quan trọng nên có identity riêng hoặc nhóm identity có quản lý. Nếu mọi ứng dụng dùng chung một private key, thu hồi hoặc điều tra một client bị xâm nhập sẽ ảnh hưởng toàn bộ hệ thống và khó xác định nguồn kết nối.

## 10. TLS version, cipher suite và thuật toán

TLS negotiation phụ thuộc Oracle Database/RU, Oracle Client, JDBC driver, JDK, wallet provider và policy bảo mật. Một phía chỉ hỗ trợ cipher/version cũ có thể khiến handshake thất bại hoặc buộc phải hạ policy.

### 10.1. TLS version

Ưu tiên phiên bản TLS được Oracle release/RU và client driver hỗ trợ, theo security baseline hiện tại của tổ chức. TLS 1.2 là baseline thường gặp trong nhiều triển khai Oracle 19c; khả năng TLS 1.3 phụ thuộc release/RU và stack client cụ thể, không nên giả định mọi bản 19c đều hỗ trợ giống nhau.

Nếu dùng tham số SSL_VERSION trong sqlnet.ora hoặc thuộc tính tương ứng của driver, kiểm tra giá trị được hỗ trợ bởi đúng Oracle Home/JDBC driver. Không sao chép cấu hình TLS version từ một bản Oracle khác mà không kiểm tra.

### 10.2. Cipher suites

Cipher suite xác định thuật toán trao đổi khóa, xác thực và mã hóa dữ liệu. Chỉ cho phép cipher được tổ chức phê duyệt và cả hai đầu hỗ trợ. Tránh bật cipher yếu hoặc legacy chỉ để tương thích với một client cũ; nâng cấp client/RU thường là hướng giải quyết bền vững.

### 10.3. Certificate signature và key size

PKI policy cần quy định:
- Key algorithm và key size phù hợp baseline.
- Certificate signature algorithm được chấp nhận.
- Validity period.
- Key Usage và Extended Key Usage.
- SAN DNS/IP.
- CA hierarchy và revocation policy.

Ví dụ CSR với RSA 2048 bit là minh họa tương thích phổ biến, không thay thế chính sách key management hiện tại. Một số môi trường có thể yêu cầu RSA lớn hơn hoặc elliptic-curve key theo khả năng stack Oracle/driver.

### 10.4. Kiểm tra tương thích trước khi enforce

Trước khi đặt server policy bắt buộc TLS version/cipher mới:
1. Kiểm kê Oracle Client, JDBC driver, JDK và integration tools.
2. Kiểm tra release/RU và khả năng cipher.
3. Thử trên staging với đúng wallet/certificate.
4. Kiểm tra failover, connection pool và monitoring.
5. Theo dõi lỗi handshake sau rollout.
6. Chỉ loại bỏ phiên bản/cipher cũ khi mọi client đã chuyển đổi.

## 11. JDBC Thin, OCI và ứng dụng Java

Ứng dụng Java có thể dùng Oracle JDBC Thin hoặc OCI driver. Cấu hình TLS và wallet phải phù hợp driver, JDK và cách đóng gói ứng dụng.

### 11.1. JDBC Thin với TCPS connect descriptor

Ví dụ URL:

~~~java
String url =
    "jdbc:oracle:thin:@(DESCRIPTION=" +
    "(ADDRESS=(PROTOCOL=TCPS)(HOST=db-prod.example.com)(PORT=2484))" +
    "(CONNECT_DATA=(SERVICE_NAME=orclpdb.example.com))" +
    "(SECURITY=(SSL_SERVER_DN_MATCH=YES)))";
~~~

Dùng connection properties theo tài liệu JDBC driver. Khi dùng Oracle Wallet, JDBC Thin hỗ trợ cấu hình wallet location qua thuộc tính Oracle Net tương ứng, ví dụ:

~~~java
Properties props = new Properties();
props.setProperty(
    "oracle.net.wallet_location",
    "(SOURCE=(METHOD=FILE)(METHOD_DATA=(DIRECTORY=/opt/app/oracle/wallet/db_trust)))"
);
props.setProperty("oracle.net.ssl_server_dn_match", "true");

// Truyền username/password qua secret provider phù hợp.
Connection connection =
    DriverManager.getConnection(url, props);
~~~

Tên thuộc tính, cách đọc wallet và hỗ trợ TLS phụ thuộc phiên bản JDBC driver. Kiểm tra Oracle JDBC Developer's Guide của đúng driver; không mặc định driver cũ hiểu mọi thuộc tính mới.

### 11.2. JDBC dùng Java truststore

Một lựa chọn khác là Java KeyStore (JKS/PKCS12) được cấu hình cho JSSE qua JVM properties:

~~~text
-Djavax.net.ssl.trustStore=/opt/app/security/oracle-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Nếu truststore được bảo vệ bằng password, truyền password qua secret mechanism phù hợp của runtime, không ghi vào command line công khai hoặc file cấu hình có quyền đọc rộng.

Không trộn lẫn wallet location và Java truststore mà không hiểu precedence của driver. Chọn một mô hình được tài liệu driver hỗ trợ, kiểm tra server DN matching và xác minh certificate chain.

### 11.3. OCI client

OCI-based clients như SQL*Plus có thể dùng Oracle Net configuration và wallet từ Oracle Home/TNS_ADMIN. Đảm bảo:
- Process đọc đúng sqlnet.ora.
- Wallet path tồn tại và OS account có quyền.
- TNS alias dùng TCPS.
- Client Oracle Home hỗ trợ TLS/cipher policy.
- Không có file sqlnet.ora khác ghi đè hoặc được ưu tiên ngoài dự kiến.

### 11.4. Connection pool

Với pool:
- Mỗi physical connection được tạo qua TCPS theo cấu hình.
- Thay wallet/certificate có thể không tác động ngay connection đã mở.
- Cần quy trình drain/recycle pool sau certificate rotation nếu handshake mới phải dùng cert mới.
- Không log wallet password hoặc private key.
- Theo dõi lỗi tạo connection mới, không chỉ connection đang sống.

## 12. Wallet, credential store và password

Oracle Wallet có thể chứa certificate và private key, đồng thời một số wallet có thể được dùng như Secure External Password Store để lưu credential database.

Hai mục đích cần được phân biệt:
- TLS wallet: trust chain, server/client certificate và private key.
- External password store: username/password để client kết nối bằng credential alias.

Ví dụ khởi tạo credential store bằng mkstore (cú pháp và hành vi tùy Oracle Client):

~~~bash
mkstore -wrl /opt/app/oracle/wallet/credentials -create
mkstore -wrl /opt/app/oracle/wallet/credentials \
  -createCredential ORCL_TCPS app_user
~~~

Lệnh yêu cầu nhập password theo prompt/cơ chế của công cụ. Kết nối bằng external password store có thể dùng:

~~~text
SQLNET.WALLET_OVERRIDE = TRUE
~~~

Và client có thể dùng connect alias theo cú pháp /@ORCL_TCPS khi wallet/credential mapping được cấu hình đúng.

Không coi việc lưu username/password trong wallet là thay thế TLS. Có thể dùng cả credential store và TCPS: một phần cung cấp database credential, một phần bảo vệ và xác thực kênh truyền.

## 13. Quản lý vòng đời certificate

Certificate không phải tài sản tạo một lần rồi quên. Cần quy trình quản lý từ yêu cầu cấp, triển khai, theo dõi expiry, renewal, rotation đến revocation.

### 13.1. Inventory

Duy trì danh sách:
- Tên wallet và đường dẫn.
- Host/service/client identity.
- Certificate subject, issuer, serial, fingerprint.
- SAN DNS/IP.
- Not Before/Not After.
- CA chain.
- Owner kỹ thuật và owner nghiệp vụ.
- Oracle Home, listener, JDBC driver và service đang dùng.
- Lịch gia hạn và nơi lưu backup.

### 13.2. Theo dõi expiry

Dùng orapki display hoặc công cụ PKI/monitoring để theo dõi thời hạn. Ví dụ:

~~~bash
orapki wallet display \
  -wallet /u01/app/oracle/admin/ORCL/wallet/tcps_server \
  -complete \
  -pwd '<WALLET_PASSWORD>'
~~~

Có thể dùng OpenSSL xem ngày hiệu lực certificate file:

~~~bash
openssl x509 -in db-prod-server.crt -noout -dates -subject -issuer
~~~

Đặt cảnh báo trước expiry đủ lâu để hoàn thành CA approval, cấp cert, rollout staging, production và rollback. Không đợi tới ngày hết hạn mới bắt đầu renewal.

### 13.3. Renewal và rotation

Quy trình gợi ý:
1. Xác nhận CA, subject/SAN, key usage và validity mới.
2. Tạo key/CSR theo chính sách (reuse hay rotate key phải được quyết định rõ).
3. Nhận certificate mới và xác minh chain/fingerprint.
4. Import certificate vào wallet mục tiêu.
5. Kiểm tra wallet display, private key association và validity.
6. Triển khai wallet lên server/client theo đợt.
7. Reload/restart listener/process theo yêu cầu.
8. Tạo kết nối mới từ từng loại client.
9. Kiểm tra server DN match, trust chain và service login.
10. Drain connection pool cũ nếu cần.
11. Giữ rollback wallet/certificate theo policy trong thời gian cho phép.
12. Loại bỏ cert cũ khi không còn client phụ thuộc và đã qua thời gian rollback.

Không xóa certificate cũ hoặc CA trust anchor trước khi mọi endpoint đã chuyển đổi. Khi CA root/intermediate thay đổi, có thể cần giai đoạn overlap để client trust cả chain cũ và mới.

### 13.4. Revocation

Nếu private key bị lộ hoặc certificate không còn đáng tin cậy, phải revoke theo CA process và cập nhật trạng thái revocation theo cơ chế được cấu hình (CRL/OCSP nếu stack hỗ trợ và policy yêu cầu).

Chỉ xóa certificate khỏi wallet không tương đương thu hồi tại CA. Các client khác có thể vẫn tin certificate đó cho đến khi trust/revocation state được cập nhật.

### 13.5. Backup và recovery

Backup cần:
- File wallet password-protected.
- Auto-login wallet nếu được sử dụng và policy cho phép.
- Wallet password lưu riêng trong secret manager.
- Metadata certificate/fingerprint/expiry.
- Quy trình khôi phục và test trên host phù hợp.
- Quyền truy cập backup được audit.

Không backup private key bằng cách gửi file qua email hoặc repository. Kiểm tra backup có thể khôi phục, không chỉ kiểm tra file tồn tại.

## 14. Cấu hình mTLS và database identity

Khi tổ chức yêu cầu certificate client làm identity, cần thiết kế đầy đủ chuỗi:
1. CA cấp client certificate cho workload identity.
2. Client giữ private key trong wallet/keystore.
3. Server trust CA cấp client cert.
4. TLS listener yêu cầu client certificate.
5. Oracle xác thực/map certificate tới database identity theo cấu hình.
6. Database user được cấp role/privilege tối thiểu.

### 14.1. External user mapping

Oracle hỗ trợ external authentication dựa trên certificate trong các mô hình SSL authentication phù hợp. User mapping cần được thiết lập theo subject/DN hoặc enterprise identity configuration đúng hướng dẫn Oracle.

Không tạo user external chỉ dựa trên ví dụ DN trong tài liệu. Phải xác nhận DN format, mapping rule, certificate chain và authentication service ở cả client/server.

### 14.2. Certificate identity và user identity

Một certificate có thể đại diện cho một service account hoặc workload. Cần tránh dùng cùng certificate cho nhiều ứng dụng nếu muốn audit chính xác. Nếu một ứng dụng có nhiều database users, xác định rõ certificate xác thực transport/client còn database credential xác định database user, hoặc dùng external mapping theo thiết kế.

### 14.3. Kiểm soát quyền

Sau TLS authentication, vẫn áp dụng:
- Least privilege.
- Roles theo chức năng.
- Không dùng SYS/SYSTEM cho ứng dụng.
- Credential rotation.
- Audit logon/logoff và privileged operations.
- Network ACL/firewall.
- Tách schema owner và runtime user.

## 15. Kiểm tra kết nối và xác minh encryption

Một kết nối được tạo thành công chưa đủ để chứng minh cấu hình bảo mật đúng. Xác minh cả listener, TLS handshake, server identity, database login và negotiated service.

### 15.1. Kiểm tra listener

~~~bash
lsnrctl status LISTENER_TCPS
lsnrctl services LISTENER_TCPS
~~~

Xác nhận:
- Endpoint TCPS và port đúng.
- Service được đăng ký.
- Listener dùng đúng Oracle Home/TNS_ADMIN.
- Không có lỗi mở wallet hoặc load certificate.

### 15.2. Kiểm tra certificate chain bằng OpenSSL

~~~bash
openssl s_client \
  -connect db-prod.example.com:2484 \
  -servername db-prod.example.com \
  -showcerts
~~~

Lệnh giúp xem TLS handshake và certificate chain từ endpoint. Nó không thay thế Oracle Net login test và không xác nhận mọi Oracle Net option đã được áp dụng. Kết quả verify phụ thuộc OpenSSL trust store và môi trường chạy lệnh.

### 15.3. Kiểm tra wallet

~~~bash
orapki wallet display \
  -wallet /opt/app/oracle/wallet/db_trust \
  -complete \
  -pwd '<CLIENT_WALLET_PASSWORD>'
~~~

Kiểm tra trusted root/intermediate, certificate expiry và nội dung wallet. Không hiển thị hoặc export private key ra nơi không bảo vệ.

### 15.4. Kiểm tra session đã kết nối

~~~sql
SELECT
    sid,
    serial#,
    network_service_banner
FROM v$session_connect_info
WHERE sid = SYS_CONTEXT('USERENV', 'SID');
~~~

V$SESSION_CONNECT_INFO có thể cung cấp banner về network service, encryption và crypto-checksum theo cơ chế/phiên bản. Hãy đọc output thực tế; đừng suy luận chỉ từ port hoặc TNS alias.

### 15.5. Kiểm tra đúng service và user

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'HOST') AS client_host
FROM dual;
~~~

Xác nhận client kết nối đúng database/service/user sau khi TLS handshake hoàn tất.

### 15.6. tnsping không phải kiểm thử đầy đủ

tnsping chủ yếu kiểm tra Oracle Net naming và khả năng tiếp cận listener. Nó không chứng minh user có quyền login, service database hoạt động, ứng dụng dùng đúng wallet hoặc mọi chính sách certificate validation đều được áp dụng. Luôn có smoke test login bằng đúng loại client/driver của ứng dụng.

## 16. Chẩn đoán lỗi TLS/TCPS

### 16.1. ORA-29024: Certificate validation failure

Nguyên nhân có thể:
- Thiếu root/intermediate CA.
- Certificate hết hạn hoặc chưa đến Not Before.
- Certificate chain không hợp lệ.
- Hostname/SAN/DN không khớp.
- Trust store/wallet client không đúng.
- Certificate bị revoke hoặc policy validation không chấp nhận.

Cách điều tra:
1. Xem subject, issuer, SAN, dates và fingerprint.
2. Kiểm tra wallet client có đúng CA chain.
3. Xác nhận hostname client dùng khớp SAN.
4. Bật DN matching và kiểm tra explicit DN nếu có.
5. Kiểm tra CRL/OCSP policy và trạng thái certificate.
6. Xem listener/client trace khi cần.

Không chữa ORA-29024 bằng cách tắt server DN matching hoặc trust mọi certificate.

### 16.2. ORA-28860: Fatal SSL error

Đây là lỗi SSL tổng quát. Có thể do:
- TLS version không giao nhau.
- Cipher suite không tương thích.
- Certificate/key/chain lỗi.
- Wallet không đọc được.
- Peer đóng handshake.
- Client/server library không tương thích.

Kiểm tra listener log, sqlnet trace, Oracle Home/JDK version và handshake output. Tăng trace chỉ trong khoảng ngắn và bảo vệ log vì có thể chứa metadata nhạy cảm.

### 16.3. ORA-28759: Failure to open file

Thường liên quan wallet/file path hoặc quyền truy cập:
- Sai DIRECTORY trong WALLET_LOCATION.
- Process chạy dưới OS account không có quyền.
- File ewallet.p12/cwallet.sso thiếu hoặc không đọc được.
- TNS_ADMIN/Oracle Home không đúng.
- Wallet được copy thiếu file hoặc sai ownership.

Kiểm tra từ đúng OS account của listener/client process, không chỉ từ shell của DBA.

### 16.4. ORA-12154 và ORA-12514

- ORA-12154: client không resolve được connect identifier/alias.
- ORA-12514: listener nhận kết nối nhưng không biết service name được yêu cầu.

Hai lỗi này thường là naming/service registration, không phải lỗi certificate trực tiếp. Kiểm tra tnsnames.ora, TNS_ADMIN, SERVICE_NAME và lsnrctl services.

### 16.5. Handshake thành công nhưng login thất bại

TLS có thể đã hoàn tất nhưng database authentication/authorization thất bại. Kiểm tra:
- Username/password hoặc external authentication mapping.
- User account lock/expiry.
- Service/PDB và container.
- Database listener service registration.
- Database audit/error log.
- Client certificate mapping nếu dùng mTLS external auth.

Không nhầm lỗi database login với TLS trust failure.

## 17. Bảo mật file và cấu hình

### 17.1. Quyền wallet

- Chỉ process cần thiết có quyền đọc wallet.
- Thư mục wallet không được writable bởi user ứng dụng không liên quan.
- Auto-login wallet vẫn cần bảo vệ bằng OS ACL.
- Backup wallet được mã hóa và access-controlled.
- Không đưa wallet/private key vào source control, artifact công khai hoặc log.

### 17.2. Bảo vệ sqlnet.ora và tnsnames.ora

Các file này có thể chứa wallet path, DN, encryption policy và endpoint. Không đặt password thật trong file nếu không cần. Quản lý config bằng version control nội bộ có kiểm soát; tách secret ra khỏi config và kiểm tra quyền file.

### 17.3. TNS_ADMIN và Oracle Home

Một host có thể cài nhiều Oracle Home hoặc nhiều ứng dụng dùng TNS_ADMIN riêng. Khi cấu hình TCPS, phải xác định chính xác process đọc file nào. Kiểm tra environment của service/systemd/container/Windows service, không chỉ shell tương tác.

### 17.4. Container và Kubernetes

Nếu ứng dụng chạy container:
- Mount wallet từ secret volume hoặc secret manager integration.
- Không bake private key vào image.
- Giới hạn read-only mount nếu phù hợp.
- Cập nhật pod/connection pool theo quy trình rotation.
- Kiểm tra file ownership/UID/GID.
- Không log secret khi startup.
- Đảm bảo DNS hostname trong certificate khớp service endpoint mà container dùng.

## 18. Checklist triển khai production

### Thiết kế
- Xác định dùng NNE hay TCPS.
- Xác định có cần mTLS hay server-auth TLS là đủ.
- Chọn TLS version/cipher theo security baseline và khả năng client.
- Kiểm kê tất cả Oracle Client, JDBC driver, JDK và agent.
- Xác định hostname/service, DNS, VIP, SCAN và load balancer.

### PKI
- Có CA được phê duyệt.
- Certificate có SAN đúng endpoint.
- Key Usage/EKU đúng mục đích serverAuth/clientAuth.
- Trust chain đầy đủ.
- Fingerprint được xác minh qua kênh độc lập.
- Private key được tạo/lưu trong wallet hoặc keystore được bảo vệ.
- Expiry/renewal/revocation có owner và cảnh báo.

### Oracle Net
- Listener TCPS mở đúng address/port.
- Listener đọc đúng wallet và sqlnet.ora.
- Client dùng PROTOCOL=TCPS.
- Server DN matching được bật.
- Client trust CA chain.
- mTLS policy nhất quán nếu được bật.
- Service name đăng ký đúng.

### Ứng dụng
- JDBC/OCI driver hỗ trợ cấu hình đã chọn.
- Wallet/truststore được mount đúng.
- Connection pool tạo được connection mới qua TCPS.
- Không lưu password/private key trong source/log.
- Failover/reconnect và rotation đã được kiểm thử.

### Vận hành
- Có smoke test TLS và database login.
- Có log/trace và quy trình thu thập khi lỗi.
- Có backup/restore test wallet.
- Có kế hoạch overlap certificate khi rotation.
- Có rollback config/wallet.
- Theo dõi handshake failures và certificate expiry.

## 19. Lab: triển khai TCPS server-auth

Thực hiện trong môi trường lab do bạn quản trị, có CA lab hoặc certificate được cấp hợp lệ.

### Bước 1: Chuẩn bị endpoint

Chọn hostname lab, ví dụ db-lab.example.test, và bảo đảm client resolve được hostname đó. Certificate server phải có SAN DNS tương ứng.

### Bước 2: Tạo server wallet và CSR

Dùng các lệnh ở mục 6 để:
- Tạo wallet.
- Import root/intermediate CA.
- Tạo key pair.
- Export CSR.
- Gửi CSR tới CA lab.
- Import leaf certificate đã ký.

### Bước 3: Cấu hình listener TCPS

Thêm address PROTOCOL=TCPS vào listener.ora và cấu hình wallet location trong sqlnet.ora của listener. Khởi động/reload listener rồi kiểm tra lsnrctl status.

### Bước 4: Tạo client trust wallet

Tạo wallet phía client và import CA root/intermediate. Không copy server private key.

### Bước 5: Cấu hình TNS alias

Tạo alias dùng TCPS port và SERVICE_NAME đúng. Bật SSL_SERVER_DN_MATCH=YES.

### Bước 6: Kiểm tra handshake

Dùng openssl s_client để xem chain nếu OpenSSL có mặt. Sau đó dùng SQL*Plus/SQLcl kết nối bằng alias. Kiểm tra V$SESSION_CONNECT_INFO và USERENV context.

### Bước 7: Thử lỗi có kiểm soát

Trong môi trường lab:
- Thử alias dùng hostname không có trong SAN.
- Thử client trust wallet thiếu intermediate CA.
- Thử wallet path sai.
- Thử service name không tồn tại.

Ghi lại lỗi ở từng tầng: name resolution, TLS handshake, certificate validation, listener service registration hay database authentication. Sau đó khôi phục cấu hình đúng.

## 20. Lab: mTLS và certificate rotation

### 20.1. mTLS

1. Tạo client wallet riêng.
2. Tạo client key/CSR với identity được CA lab cấp.
3. Import client certificate vào client wallet.
4. Thêm client CA chain vào server wallet trust store.
5. Đặt SSL_CLIENT_AUTHENTICATION=TRUE ở server.
6. Cấu hình client sử dụng wallet có private key/client certificate.
7. Kiểm tra handshake và database authentication.
8. Thử kết nối không có client certificate để xác nhận server từ chối theo policy.

Nếu cần map client certificate thành database user, thực hiện theo Oracle SSL external authentication documentation; không coi handshake thành công là đã có database authorization.

### 20.2. Rotation

1. Tạo certificate mới với SAN/identity tương ứng.
2. Kiểm tra chain, dates, fingerprint và key usage.
3. Import vào wallet mới hoặc quy trình wallet versioned.
4. Thử staging với client thực tế.
5. Triển khai server wallet mới.
6. Reload/restart listener theo yêu cầu.
7. Tạo kết nối mới và xác nhận certificate mới được trình.
8. Recycle connection pool nếu cần.
9. Giữ rollback trong thời gian đã định.
10. Gỡ certificate cũ/trust anchor cũ khi không còn dependency.

Không sửa trực tiếp wallet production mà không backup và không có phương án rollback.

## 21. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| TCP kết nối được nhưng TCPS thất bại | Listener chưa mở TCPS hoặc sai port | Kiểm tra listener.ora và lsnrctl status |
| ORA-29024 | Trust chain, expiry, SAN/DN hoặc revocation không hợp lệ | Kiểm tra certificate và trust wallet |
| ORA-28860 | TLS/cipher/version hoặc handshake failure | Kiểm tra RU, driver, JDK, listener/sqlnet trace |
| ORA-28759 | Wallet path hoặc quyền file sai | Kiểm tra TNS_ADMIN, Oracle Home, owner/ACL |
| ORA-12154 | Không resolve được alias | Kiểm tra tnsnames.ora và TNS_ADMIN |
| ORA-12514 | Service name chưa đăng ký/không đúng | Kiểm tra SERVICE_NAME và lsnrctl services |
| Certificate còn hạn nhưng bị reject | SAN/DN/issuer/chain không đúng | Kiểm tra SAN, trust anchor và DN matching |
| Chỉ một máy client lỗi | Wallet, CA bundle, driver hoặc clock khác | So sánh môi trường client và thời gian hệ thống |
| Listener chạy nhưng không mở wallet | Listener dùng Oracle Home/TNS_ADMIN khác | Kiểm tra process environment và file config |
| mTLS server từ chối client | Client cert thiếu, CA không trusted hoặc EKU sai | Kiểm tra client wallet và CA trust phía server |
| JDBC lỗi nhưng SQL*Plus chạy | Driver/JDK properties hoặc truststore khác | Kiểm tra JDBC driver config và JVM |
| Rotation làm connection pool lỗi | Connection cũ/new connection dùng cert khác nhau | Drain/recycle pool và xác minh cert mới |
| tnsping thành công nhưng login thất bại | tnsping không kiểm tra đầy đủ database authentication | Thực hiện smoke test login thật |
| NNE không thương lượng | Policy hoặc thuật toán client/server không giao nhau | Kiểm tra SQLNET.ENCRYPTION/CRYPTO_CHECKSUM hai phía |
| Mã hóa bật nhưng không xác thực server | Chỉ bật NNE hoặc tắt DN matching | Dùng TCPS với trust chain và identity validation |

## 22. Bài tập thực hành

### Bài 1 — So sánh NNE và TCPS

Viết bảng so sánh encryption, integrity, server authentication, client authentication, wallet và client compatibility. Chọn mô hình cho một service nội bộ và giải thích.

### Bài 2 — NNE negotiation

Cấu hình server REQUIRED, client REQUESTED với thuật toán tương thích. Kết nối rồi xem V$SESSION_CONNECT_INFO. Thử bỏ thuật toán chung trong lab và ghi nhận kết quả.

### Bài 3 — Certificate inspection

Dùng orapki và OpenSSL xem Subject, Issuer, SAN, validity, key usage và fingerprint. Giải thích root, intermediate và leaf certificate.

### Bài 4 — Server-auth TCPS

Tạo wallet, CSR, import CA/leaf certificate, mở listener TCPS và kết nối từ client trust wallet. Xác nhận hostname matching.

### Bài 5 — DN matching

Thử hostname đúng SAN và hostname không đúng SAN. Ghi nhận khác biệt khi SSL_SERVER_DN_MATCH bật. Khôi phục hostname đúng sau thử nghiệm.

### Bài 6 — mTLS

Tạo client certificate, bật SSL_CLIENT_AUTHENTICATION và kiểm tra client có/không có certificate. Phân biệt TLS handshake với database user authentication.

### Bài 7 — JDBC Thin

Dùng JDBC Thin kết nối bằng TCPS. Thử wallet property hoặc Java truststore theo driver. Xác nhận connection pool tạo được connection mới.

### Bài 8 — Certificate renewal

Tạo certificate mới, triển khai wallet mới ở staging, kiểm tra handshake rồi mô phỏng rollback. Ghi rõ thứ tự overlap CA và leaf certificate.

### Bài 9 — Troubleshooting

Tạo tình huống sai wallet path, thiếu CA, sai hostname và service name. Phân loại lỗi thuộc naming, listener, TLS trust hay database login.

### Bài 10 — Production runbook

Viết runbook có inventory, expiry alert, backup, rotation, validation, pool recycle, rollback và owner cho mỗi certificate.

## 23. Dọn dẹp môi trường lab

Sau khi hoàn tất:
- Tắt listener lab nếu không còn sử dụng.
- Xóa hoặc archive đúng wallet lab theo chính sách.
- Thu hồi certificate lab nếu PKI yêu cầu.
- Xóa CSR/test certificate không còn cần.
- Thu hồi secret/password lab khỏi nơi lưu tạm.
- Khôi phục listener.ora, sqlnet.ora và tnsnames.ora.
- Xác nhận không còn client trỏ tới endpoint lab.

Không xóa wallet, CA hoặc certificate dùng chung của môi trường khác.

## Tổng kết

Oracle Net có thể bảo vệ kết nối bằng Native Network Encryption trên TCP hoặc TLS qua TCPS. NNE cấu hình bằng SQLNET.ENCRYPTION_* và SQLNET.CRYPTO_CHECKSUM_*; nó mã hóa/integrity nhưng không cung cấp certificate-based server identity như TLS. TCPS dùng TLS, wallet/trust store và certificate chain để mã hóa, xác minh server; có thể bật mTLS để yêu cầu client certificate.

Wallet chứa private key, identity certificate và trusted CA certificates. Quy trình an toàn gồm tạo key/CSR, xác minh CA, import chain và leaf certificate, cấu hình listener/client, bật server DN matching, kiểm tra TLS handshake và database login bằng đúng driver. Certificate cần inventory, expiry alert, renewal, rotation, revocation, backup và quyền file chặt chẽ. Khi chẩn đoán, phân biệt lỗi name resolution, listener/service, wallet access, TLS validation và database authentication; không tắt certificate validation để né lỗi.

## Tài liệu Oracle tham khảo

- [Oracle Database Net Services Administrator's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/) — Oracle Net, TLS/TCPS, listener và client configuration.
- [Oracle Database Net Services Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/netrf/) — sqlnet.ora parameters, encryption, wallet và connect descriptor.
- [Oracle Database Security Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/) — authentication, network security và certificate-based security.
- [Oracle Database JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — JDBC Thin/OCI và kết nối bảo mật.
- [Oracle Database Licensing Information User Manual (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — thông tin license các tùy chọn database có liên quan.

Khi triển khai trên Oracle release/RU khác 19c, hãy đối chiếu Oracle Net Services Administrator's Guide, Net Services Reference và JDBC driver documentation đúng phiên bản, đặc biệt TLS version/cipher support, wallet location, DN matching, mTLS và certificate validation.

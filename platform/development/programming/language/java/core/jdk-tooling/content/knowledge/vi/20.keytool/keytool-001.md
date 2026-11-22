# Lệnh keytool trong Java

`keytool` là công cụ dòng lệnh đi kèm JDK để quản lý key pair, certificate, certificate chain và keystore. Công cụ này thường được dùng khi cấu hình TLS/HTTPS, chuẩn bị chứng chỉ cho server, quản lý truststore, ký hoặc xác minh artifact và chuyển đổi dữ liệu bảo mật giữa các định dạng keystore.

Bài này sử dụng JDK 17 trở lên. Bạn sẽ thực hành tạo key pair, xem certificate, xuất public certificate, tạo Certificate Signing Request (CSR), nhập certificate do CA ký, quản lý truststore và bảo vệ keystore. Các lệnh mẫu dùng PKCS12 và để `keytool` hỏi mật khẩu tương tác, tránh ghi mật khẩu thật vào lịch sử shell.

## 1. keytool dùng để làm gì?

`keytool` quản lý dữ liệu bảo mật được lưu trong keystore. Các công việc chính gồm:

- Tạo cặp khóa public/private.
- Tạo certificate tự ký để thử nghiệm hoặc dùng trong môi trường kiểm soát.
- Tạo CSR để gửi Certificate Authority (CA) ký.
- Nhập certificate hoặc certificate chain.
- Xuất public certificate để trao đổi.
- Xem thông tin, fingerprint và thời hạn certificate.
- Chuyển entry giữa các keystore.
- Đổi mật khẩu, đổi alias hoặc xóa entry.
- Quản lý secret key dùng cho một số tác vụ mã hóa đối xứng.

Certificate X.509 là dữ liệu được issuer ký, liên kết public key với thông tin subject. Private key được giữ bí mật và dùng cho các thao tác như ký hoặc chứng minh quyền sở hữu khóa; public key có thể được phân phối cùng certificate.

`keytool` là công cụ quản lý khóa và certificate. Nó không tự biến certificate tự ký thành certificate được các trình duyệt hoặc hệ điều hành tin cậy. Việc tin cậy phụ thuộc vào trust anchor và chính sách của ứng dụng/môi trường.

## 2. Keystore, truststore và các loại entry

### 2.1. Keystore và truststore

Keystore và truststore đều là kho dữ liệu được truy cập qua API `KeyStore`. Khác biệt chủ yếu nằm ở mục đích sử dụng:

| Kho | Nội dung thường lưu | Dùng để làm gì |
|---|---|---|
| Keystore | Private key cùng certificate chain của chính ứng dụng/server | Chứng minh danh tính của ứng dụng hoặc server |
| Truststore | Certificate của CA hoặc peer mà ứng dụng tin cậy | Xác minh certificate của server/peer khác |

Một ứng dụng server TLS thường cần keystore chứa private key và certificate của server. Một ứng dụng client TLS có thể cần truststore chứa CA mà client chấp nhận.

Keystore và truststore không phải hai định dạng file khác nhau. Cả hai có thể dùng PKCS12 hoặc JKS; vai trò được quyết định bởi cách ứng dụng sử dụng nội dung bên trong.

### 2.2. Ba loại entry phổ biến

| Loại entry | Nội dung | Ví dụ |
|---|---|---|
| `PrivateKeyEntry` | Private key và certificate chain tương ứng | Khóa TLS của server |
| `trustedCertEntry` | Một certificate được cấu hình là trusted | Root CA trong truststore |
| `SecretKeyEntry` | Secret key dùng cho mã hóa đối xứng | Khóa AES |

Mỗi entry được định danh bằng một alias. Alias phải xác định đúng entry khi dùng `-list`, `-exportcert`, `-importcert`, `-delete` hoặc các lệnh quản lý khác.

## 3. Định dạng keystore: PKCS12 và JKS

Trong JDK 9 trở lên, loại keystore mặc định tiêu chuẩn là `PKCS12`. Đây là định dạng phổ biến, có khả năng tương tác giữa nhiều nền tảng và công cụ.

`JKS` là định dạng keystore truyền thống của Java. JDK vẫn hỗ trợ JKS để tương thích với các hệ thống cũ.

| Định dạng | Đặc điểm | Khi dùng |
|---|---|---|
| `PKCS12` | Chuẩn trao đổi phổ biến, hỗ trợ private key và certificate | Lựa chọn mặc định phù hợp cho dự án mới |
| `JKS` | Định dạng keystore truyền thống của Java | Tương thích hệ thống cũ cần JKS |

Nên chỉ định rõ `-storetype PKCS12` hoặc `-storetype JKS` trong các lệnh quan trọng để tránh phụ thuộc cấu hình môi trường.

Phần mở rộng `.p12`, `.pfx` hoặc `.jks` chỉ là quy ước đặt tên. Loại keystore thực tế được xác định bởi định dạng dữ liệu và tùy chọn `-storetype`, không chỉ bởi phần mở rộng file.

## 4. Cú pháp chung và cách xem trợ giúp

Cú pháp khái quát:

~~~text
keytool <command> [options]
~~~

Mỗi lần gọi `keytool` chỉ thực hiện một command. Các option của command đó có thể xuất hiện theo nhiều thứ tự.

Xem danh sách command:

~~~powershell
keytool -help
~~~

Xem trợ giúp cho một command cụ thể:

~~~powershell
keytool -list -help
keytool -genkeypair -help
keytool -importcert -help
~~~

Một số option thường gặp:

| Option | Ý nghĩa |
|---|---|
| `-alias` | Tên entry cần tạo hoặc thao tác |
| `-keystore` | Đường dẫn file keystore |
| `-storetype` | Định dạng keystore, ví dụ `PKCS12` hoặc `JKS` |
| `-storepass` | Mật khẩu bảo vệ keystore |
| `-keypass` | Mật khẩu bảo vệ private/secret key của entry |
| `-file` | File certificate, CSR hoặc dữ liệu đầu vào/đầu ra |
| `-dname` | Distinguished Name của subject |
| `-validity` | Số ngày certificate có hiệu lực |
| `-keyalg` | Thuật toán tạo key pair |
| `-keysize` | Kích thước khóa |
| `-ext` | X.509 certificate extension |
| `-v` | Hiển thị thông tin chi tiết |

Nếu giá trị option có khoảng trắng, đặt giá trị trong dấu ngoặc kép. Không đưa mật khẩu thật vào ví dụ, script hoặc command history; khi không truyền mật khẩu, `keytool` sẽ hỏi tại terminal.

## 5. Tạo keystore và key pair với -genkeypair

`-genkeypair` tạo public/private key pair. Nếu không chỉ định signer, `keytool` tạo certificate X.509 v3 tự ký chứa public key và lưu private key cùng certificate chain một phần tử trong keystore.

Ví dụ tạo keystore PKCS12 cho môi trường local development:

~~~powershell
keytool -genkeypair `
  -alias local-server `
  -keyalg RSA `
  -keysize 3072 `
  -storetype PKCS12 `
  -keystore server.p12 `
  -validity 365 `
  -dname "CN=localhost, OU=Development, O=Example, L=Ho Chi Minh City, C=VN" `
  -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

Trong PowerShell, dấu backtick cuối dòng nối lệnh nhiều dòng. Có thể viết lệnh trên thành một dòng.

Giải thích:

- `-alias local-server`: đặt tên entry là `local-server`.
- `-keyalg RSA`: dùng thuật toán RSA.
- `-keysize 3072`: tạo khóa RSA 3072 bit.
- `-storetype PKCS12`: chọn định dạng PKCS12.
- `-keystore server.p12`: tạo hoặc mở file keystore.
- `-validity 365`: certificate tự ký có hiệu lực 365 ngày.
- `-dname`: thông tin Distinguished Name của subject.
- `-ext "SAN=..."`: khai báo Subject Alternative Name cho hostname và IP dùng trong ví dụ.

Khi chạy, `keytool` hỏi mật khẩu keystore và có thể hỏi mật khẩu private key. Nếu ở prompt mật khẩu private key bạn nhấn Enter theo hướng dẫn, key password sẽ dùng cùng mật khẩu keystore. `keytool` yêu cầu key password có ít nhất sáu ký tự; trên thực tế hãy chọn passphrase mạnh, duy nhất.

Certificate tự ký trong ví dụ chỉ phù hợp cho local development hoặc môi trường thử nghiệm có kiểm soát. Nó không tự động được hệ điều hành, trình duyệt hay client bên ngoài tin cậy.

### Vì sao SAN quan trọng?

`SAN` (Subject Alternative Name) ghi những DNS name hoặc IP address mà certificate đại diện. Khi xác minh hostname TLS, client hiện đại thường kiểm tra SAN; chỉ ghi `CN=localhost` không thay thế việc khai báo SAN.

Nếu server được truy cập qua `api.example.test`, certificate cần có SAN tương ứng với tên thực tế mà client dùng. Không sao chép SAN `localhost` vào certificate production.

## 6. Liệt kê entry bằng -list

Liệt kê entry trong keystore:

~~~powershell
keytool -list -keystore server.p12 -storetype PKCS12
~~~

Xem chi tiết một alias:

~~~powershell
keytool -list -v -alias local-server -keystore server.p12 -storetype PKCS12
~~~

Thông tin thường thấy:

- Alias name.
- Entry type, ví dụ `PrivateKeyEntry`.
- Ngày tạo entry.
- Số lượng certificate trong chain.
- Subject và issuer.
- Thời hạn `Valid from` / `until`.
- Fingerprint SHA-256.

Có thể dùng `-rfc` để hiển thị certificate theo định dạng PEM/Base64:

~~~powershell
keytool -list -rfc -alias local-server -keystore server.p12 -storetype PKCS12
~~~

Nếu alias không tồn tại, kiểm tra chính tả alias, đúng file keystore và đúng `-storetype`.

## 7. Xem certificate bằng -printcert

`-printcert` đọc certificate từ file và in thông tin của nó:

~~~powershell
keytool -printcert -file local-server.pem
~~~

Có thể xem chi tiết hơn:

~~~powershell
keytool -printcert -v -file local-server.pem
~~~

Để xem certificate server mà không cần xuất file trước:

~~~powershell
keytool -printcert -sslserver example.com:443
~~~

Các trường cần xem:

| Trường | Ý nghĩa |
|---|---|
| Owner/Subject | Danh tính được certificate mô tả |
| Issuer | CA hoặc entity đã ký certificate |
| Serial Number | Số serial do issuer cấp |
| Valid from/until | Khoảng thời gian certificate có hiệu lực |
| SHA-256 fingerprint | Dấu vân tay dùng đối chiếu certificate |
| Subject Alternative Name | DNS/IP mà certificate đại diện |
| Key Usage / Extended Key Usage | Mục đích sử dụng khóa được cho phép |

`-printcert` chỉ hiển thị dữ liệu certificate. Việc nhìn thấy certificate hoặc thấy thời hạn còn hiệu lực không tự chứng minh certificate đáng tin cậy. Cần kiểm tra chain, hostname, thời hạn và nguồn phát hành.

## 8. Xuất public certificate bằng -exportcert

`-exportcert` xuất certificate gắn với alias. Ví dụ xuất certificate của server sang PEM:

~~~powershell
keytool -exportcert -rfc `
  -alias local-server `
  -keystore server.p12 `
  -storetype PKCS12 `
  -file local-server.pem
~~~

Option `-rfc` tạo dạng văn bản PEM, thường bắt đầu bằng:

~~~text
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
~~~

Nếu bỏ `-rfc`, output mặc định là dữ liệu nhị phân DER.

Lệnh này chỉ xuất certificate/public key, không xuất private key. Không gửi private key hoặc file keystore chứa private key cho người cần xác minh public certificate.

Kiểm tra file vừa xuất:

~~~powershell
keytool -printcert -file local-server.pem
~~~

## 9. Tạo Certificate Signing Request bằng -certreq

Trong môi trường production, thông thường tổ chức không dùng certificate tự ký cho server công khai. Thay vào đó, server tạo key pair riêng và gửi CSR cho CA.

CSR chứa public key cùng thông tin subject và yêu cầu extension. Private key vẫn nằm trong keystore của server.

Tạo CSR từ alias đã sinh:

~~~powershell
keytool -certreq `
  -alias local-server `
  -keystore server.p12 `
  -storetype PKCS12 `
  -file local-server.csr `
  -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

Xem nội dung CSR:

~~~powershell
keytool -printcertreq -file local-server.csr
~~~

Quy trình:

1. Tạo key pair trong keystore.
2. Dùng `-certreq` tạo CSR từ alias giữ private key.
3. Gửi CSR tới CA theo quy trình của tổ chức.
4. CA xác minh yêu cầu và trả về certificate cùng intermediate certificate nếu có.
5. Nhập CA certificate cần tin cậy vào keystore/truststore phù hợp.
6. Nhập certificate reply dưới đúng alias đã tạo key pair.
7. Kiểm tra certificate chain bằng `-list -v`.

CA có thể áp dụng chính sách riêng cho subject và extension trong CSR. Không mặc định rằng CA sẽ giữ nguyên mọi extension; hãy kiểm tra certificate được cấp có SAN và mục đích sử dụng đúng yêu cầu.

## 10. Nhập certificate và certificate chain bằng -importcert

`-importcert` có hai trường hợp sử dụng chính:

- Import một trusted certificate vào alias mới.
- Import certificate reply do CA trả về vào alias đang giữ private key.

### 10.1. Import CA certificate vào truststore

Trước khi tin cậy một CA certificate, hãy xem fingerprint:

~~~powershell
keytool -printcert -file company-root.pem
~~~

Đối chiếu fingerprint SHA-256 với giá trị nhận được từ một kênh độc lập, đáng tin cậy, chẳng hạn tài liệu nội bộ đã xác thực hoặc quản trị viên CA. Không chỉ tin vào certificate được gửi cùng email hoặc cùng một kênh chưa xác minh.

Sau khi xác nhận fingerprint, import vào truststore riêng của ứng dụng:

~~~powershell
keytool -importcert `
  -alias company-root `
  -file company-root.pem `
  -keystore app-truststore.p12 `
  -storetype PKCS12
~~~

`keytool` sẽ hiển thị thông tin và hỏi xác nhận trước khi thêm trusted certificate. Chỉ chấp nhận sau khi xác minh đúng certificate.

### 10.2. Import CA reply vào private-key entry

Khi CA trả certificate chain cho server, nhập certificate reply vào đúng alias đã dùng để tạo CSR:

~~~powershell
keytool -importcert `
  -alias local-server `
  -file server-reply.p7b `
  -keystore server.p12 `
  -storetype PKCS12 `
  -trustcacerts
~~~

Ở đây `local-server` phải là alias chứa private key đã tạo CSR. Public key trong certificate reply phải khớp public key của entry đó. Khi hợp lệ, certificate tự ký cũ được thay bằng certificate chain do CA cấp.

Nếu CA nội bộ chưa được tin cậy qua `cacerts`, hãy thiết lập trust anchor theo quy trình của tổ chức trước khi nhập certificate reply. Có thể nhập CA certificate vào cùng keystore hoặc cấu hình truststore phù hợp. Không import một certificate không xác minh chỉ để làm cho lệnh thành công.

### 10.3. Phân biệt alias khi import

| Alias được chỉ định | `keytool` hiểu thao tác là |
|---|---|
| Alias chưa tồn tại | Thêm một trusted certificate entry |
| Alias đang là key entry | Import certificate reply thay chain của private-key entry |

Không dùng alias mới khi mục tiêu là cập nhật certificate cho private key hiện có. Nếu dùng alias sai, bạn có thể tạo một trusted certificate entry riêng mà không cập nhật chain của server.

`-noprompt` tắt bước hỏi xác nhận. Không dùng tùy chọn này cho certificate chưa được xác minh hoặc trong quy trình tương tác cần kiểm tra fingerprint.

## 11. Quản lý truststore và cacerts

JDK đi kèm truststore hệ thống tên `cacerts`, chứa tập root CA mặc định. Có thể liệt kê nội dung:

~~~powershell
keytool -list -cacerts
~~~

Xem chi tiết:

~~~powershell
keytool -list -v -cacerts
~~~

`-cacerts` yêu cầu `keytool` thao tác trên kho `cacerts`; không kết hợp option này với `-keystore` hoặc `-storetype` trong cùng lệnh.

Đường dẫn phổ biến của `cacerts` là:

- Windows: `JAVA_HOME\lib\security\cacerts`
- Linux/macOS: `JAVA_HOME/lib/security/cacerts`

`cacerts` là truststore dùng chung của JDK. Thay đổi nó có thể ảnh hưởng nhiều ứng dụng sử dụng cùng runtime. Với ứng dụng cần trust policy riêng, nên tạo truststore riêng thay vì sửa trực tiếp truststore toàn hệ thống.

Nếu certificate CA không còn được tin cậy, quản trị viên có thể xóa entry bằng `-delete` sau khi đánh giá ảnh hưởng. Không xóa root CA khỏi `cacerts` chỉ dựa trên tên alias mà chưa xác minh certificate tương ứng.

## 12. Chuyển đổi keystore bằng -importkeystore

Có thể chuyển các entry từ JKS sang PKCS12 hoặc từ một keystore khác sang định dạng đích.

Ví dụ chuyển toàn bộ entry từ JKS sang PKCS12:

~~~powershell
keytool -importkeystore `
  -srckeystore legacy.jks `
  -srcstoretype JKS `
  -destkeystore migrated.p12 `
  -deststoretype PKCS12
~~~

`keytool` sẽ hỏi mật khẩu source và destination khi cần. Sau khi chuyển đổi, liệt kê cả hai file để so sánh alias, loại entry và certificate chain:

~~~powershell
keytool -list -v -keystore legacy.jks -storetype JKS
keytool -list -v -keystore migrated.p12 -storetype PKCS12
~~~

Có thể chuyển một alias cụ thể bằng `-srcalias` và đặt alias mới bằng `-destalias`.

Một số công cụ bên ngoài yêu cầu password của private key entry trong PKCS12 phải giống store password. Nếu cần tương thích với công cụ đó, hãy đặt `-destkeypass` bằng `-deststorepass` theo yêu cầu của công cụ đích.

Không xóa keystore cũ ngay sau khi chuyển. Trước tiên hãy kiểm tra file mới, thử nạp bằng ứng dụng thực tế và giữ backup an toàn cho tới khi migration được xác nhận.

## 13. Quản lý alias, mật khẩu và xóa entry

Các command quản lý phổ biến:

| Command | Chức năng |
|---|---|
| `-storepasswd` | Đổi mật khẩu bảo vệ keystore |
| `-keypasswd` | Đổi mật khẩu bảo vệ private/secret key entry |
| `-changealias` | Đổi tên alias |
| `-delete` | Xóa entry |

Đổi mật khẩu keystore:

~~~powershell
keytool -storepasswd -keystore server.p12 -storetype PKCS12
~~~

Đổi mật khẩu private key entry:

~~~powershell
keytool -keypasswd -alias local-server -keystore server.p12 -storetype PKCS12
~~~

Đổi alias:

~~~powershell
keytool -changealias `
  -alias local-server `
  -destalias api-server `
  -keystore server.p12 `
  -storetype PKCS12
~~~

Xóa entry:

~~~powershell
keytool -delete -alias old-entry -keystore server.p12 -storetype PKCS12
~~~

Các command thay đổi dữ liệu nên được thực hiện sau khi xác nhận đúng file và alias. Tạo bản sao lưu keystore trước khi đổi password, đổi alias hoặc xóa entry. Xóa `PrivateKeyEntry` có thể khiến server không còn private key cần để xác thực TLS.

## 14. Một số command keytool khác

Ngoài luồng tạo key pair và certificate, `keytool` còn hỗ trợ:

| Command | Mục đích |
|---|---|
| `-genseckey` | Tạo secret key và lưu thành `SecretKeyEntry` |
| `-gencert` | Ký CSR và tạo certificate; thường dùng khi vận hành CA |
| `-importpass` | Nhập passphrase thành secret-key entry |
| `-printcertreq` | Hiển thị nội dung CSR |
| `-printcrl` | Hiển thị Certificate Revocation List |
| `-showinfo` | Hiển thị thông tin liên quan tới security provider/runtime |

`-gencert` cần alias signer trỏ tới private-key entry có quyền ký certificate. Không dùng nó như cách thay thế CA công khai; việc vận hành CA đòi hỏi bảo vệ signing key, quy trình xác minh danh tính, chính sách certificate và kiểm soát phát hành.

## 15. Luồng thực hành tổng hợp: tạo và kiểm tra certificate local

Ví dụ sau tạo một certificate tự ký cho `localhost`, xem entry và xuất public certificate. Thực hiện trong thư mục dự án thử nghiệm.

Tạo key pair và keystore:

~~~powershell
keytool -genkeypair -alias local-server -keyalg RSA -keysize 3072 -storetype PKCS12 -keystore server.p12 -validity 365 -dname "CN=localhost, OU=Development, O=Example, L=Ho Chi Minh City, C=VN" -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

Liệt kê entry:

~~~powershell
keytool -list -v -alias local-server -keystore server.p12 -storetype PKCS12
~~~

Xuất public certificate:

~~~powershell
keytool -exportcert -rfc -alias local-server -keystore server.p12 -storetype PKCS12 -file local-server.pem
~~~

Đọc certificate vừa xuất:

~~~powershell
keytool -printcert -file local-server.pem
~~~

Kết quả cụ thể về serial number, fingerprint, thời hạn và encoding phụ thuộc lần tạo key pair. Hãy kiểm tra các trường thực tế thay vì so sánh với một fingerprint cố định trong tài liệu.

Nếu cần CA ký thay vì certificate tự ký, tạo CSR từ alias đó:

~~~powershell
keytool -certreq -alias local-server -keystore server.p12 -storetype PKCS12 -file local-server.csr -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

Sau khi CA trả certificate reply, xác minh CA chain rồi import vào alias `local-server` như phần 10.2.

## 16. Bảo mật khi sử dụng keytool

Keystore có thể chứa private key hoặc secret key. Hãy xử lý nó như dữ liệu nhạy cảm:

- Không commit file keystore chứa private key lên Git hoặc gửi qua kênh chat/email thông thường.
- Không ghi `-storepass` hoặc `-keypass` thật trực tiếp vào command line, script hay log. `keytool` có thể hỏi mật khẩu khi bạn không cung cấp option password.
- Dùng passphrase mạnh và khác nhau giữa các môi trường; lưu bằng secret manager hoặc cơ chế quản lý bí mật của tổ chức.
- Giới hạn quyền đọc file keystore cho đúng tài khoản chạy ứng dụng.
- Giữ backup được mã hóa và có quy trình khôi phục.
- Kiểm tra alias, entry type, certificate chain, SAN, thời hạn và fingerprint trước khi triển khai.
- Xác minh fingerprint của CA certificate qua một kênh độc lập trước khi import làm trusted certificate.
- Không dùng `-noprompt` để bỏ qua việc xác minh certificate.
- Không dùng certificate tự ký local làm certificate production công khai.
- Không sửa `cacerts` dùng chung nếu ứng dụng chỉ cần truststore riêng.

Mật khẩu được truyền trực tiếp trên command line có thể xuất hiện trong process listing, shell history hoặc log. Với automation, dùng cơ chế cung cấp secret được bảo vệ của môi trường build thay vì hard-code giá trị.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `keytool is not recognized` | JDK `bin` chưa nằm trên PATH hoặc đang dùng runtime không có công cụ | Cài JDK phù hợp và gọi `keytool` từ thư mục `bin` |
| `Keystore was tampered with, or password was incorrect` | Sai store password hoặc sai loại keystore | Xác nhận password, file và `-storetype` |
| `Alias ... does not exist` | Alias sai hoặc đang mở nhầm keystore | Dùng `-list` để kiểm tra alias và đúng đường dẫn file |
| `Alias ... already exists` | Đang import trusted certificate vào alias đã có | Chọn alias mới hoặc xác định đúng thao tác cập nhật certificate reply |
| `Certificate reply does not contain public key for ...` | Certificate reply không khớp key pair đã tạo CSR | Tạo lại CSR từ đúng alias hoặc yêu cầu CA cấp lại certificate cho đúng public key |
| `Failed to establish chain from reply` | Thiếu intermediate/root CA hoặc trust anchor không được tìm thấy | Nhập đúng CA chain và dùng trust anchor đã xác minh |
| Certificate hết hạn hoặc chưa có hiệu lực | Thời gian hệ thống sai hoặc certificate ngoài thời hạn | Kiểm tra đồng hồ hệ thống và cấp/nhập certificate hợp lệ |
| Hostname verification thất bại | SAN không chứa DNS/IP mà client sử dụng | Cấp lại certificate với SAN đúng hostname/IP |
| `Unrecognized keystore format` | Dùng sai `-storetype` hoặc file không phải keystore hợp lệ | Xác định định dạng nguồn và chọn đúng `-storetype` |
| Không thể ghi keystore | Thư mục không có quyền ghi hoặc file đang bị khóa | Kiểm tra quyền file, đường dẫn và tiến trình đang sử dụng |
| Ứng dụng không tin cậy CA đã import | Import vào truststore khác với truststore mà ứng dụng đang đọc | Kiểm tra cấu hình runtime và đường dẫn truststore của ứng dụng |

Khi xử lý lỗi, không nên xóa keystore hoặc tạo key pair mới ngay. Trước tiên hãy dùng `-list -v` để xác định alias, entry type, chain và thời hạn. Nếu certificate reply không khớp private key, tạo CSR mới từ đúng private-key entry và yêu cầu CA cấp certificate tương ứng.

## 18. Quy trình làm việc khuyến nghị

Đối với certificate TLS cho một server, quy trình thường là:

1. Chọn vị trí keystore và định dạng, ưu tiên PKCS12 cho dự án mới.
2. Tạo key pair bằng `-genkeypair`, dùng alias dễ nhận diện và SAN đúng hostname.
3. Tạo CSR bằng `-certreq` từ đúng alias.
4. Gửi CSR tới CA theo quy trình xác minh của tổ chức.
5. Xác minh CA certificate và fingerprint từ nguồn đáng tin cậy.
6. Nhập certificate chain/trust anchor phù hợp.
7. Import certificate reply vào alias đã tạo key pair.
8. Dùng `-list -v` để xác nhận `PrivateKeyEntry` và certificate chain.
9. Cấu hình server/application trỏ tới đúng keystore và alias.
10. Kiểm thử TLS, hostname, chain và thời hạn trên môi trường triển khai.
11. Bảo vệ private key, backup keystore và theo dõi lịch gia hạn certificate.

Đối với client cần tin cậy CA, tạo truststore riêng, import CA certificate đã xác minh rồi cấu hình ứng dụng sử dụng đúng truststore đó. Không nhầm truststore chứa CA tin cậy với keystore chứa private key của server.

## 19. Checklist trước khi triển khai

- [ ] Đã xác định mục đích là lưu private key, trusted certificate hay secret key.
- [ ] Đã chọn `PKCS12` hoặc định dạng tương thích với hệ thống đích.
- [ ] Alias duy nhất và phản ánh đúng mục đích của entry.
- [ ] Certificate có subject, SAN, validity và key usage phù hợp.
- [ ] CSR được tạo từ đúng private-key entry.
- [ ] Certificate CA và fingerprint đã được xác minh qua kênh độc lập.
- [ ] Certificate reply khớp public key của alias đã tạo CSR.
- [ ] Certificate chain có đủ intermediate và trust anchor cần thiết.
- [ ] `keytool -list -v` hiển thị đúng entry type và chain.
- [ ] Ứng dụng trỏ tới đúng keystore/truststore.
- [ ] Mật khẩu không bị hard-code hoặc ghi vào shell history/log.
- [ ] Private key được bảo vệ, keystore có backup và quyền file phù hợp.
- [ ] Certificate được kiểm thử trên hostname và môi trường thực tế.

`keytool` là công cụ nền tảng để quản lý key pair, certificate và keystore trong Java. Hãy bắt đầu bằng việc xác định bạn cần giữ private key hay tin cậy certificate của bên khác; sau đó chọn đúng keystore/truststore, alias và định dạng. Với TLS, tạo key pair và CSR, xác minh CA certificate trước khi import, nhập certificate reply vào đúng alias và kiểm tra lại chain trước khi triển khai.

## Tài liệu tham khảo

- Oracle, The keytool Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- Oracle, Java Security Developer's Guide, JDK 17: https://docs.oracle.com/en/java/javase/17/security/java-security-overview1.html

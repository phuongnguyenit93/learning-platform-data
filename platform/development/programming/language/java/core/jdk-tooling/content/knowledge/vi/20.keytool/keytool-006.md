# Xuất certificate bằng keytool

`keytool -exportcert` là lệnh của JDK dùng để xuất một chứng chỉ số (X.509 certificate) từ keystore theo alias. Lệnh lấy certificate gắn với entry được chọn và ghi ra file hoặc standard output. Định dạng mặc định là DER nhị phân; thêm `-rfc` để xuất dạng văn bản Base64 PEM.

Certificate chứa public key và thông tin nhận dạng, hiệu lực của chủ thể. `-exportcert` chỉ xuất certificate, không xuất private key. Nếu alias trỏ tới một key entry có certificate chain, lệnh trả về **certificate đầu tiên trong chain** (certificate của entity được alias đại diện), không xuất toàn bộ chain.

## 1. Khi nào cần export certificate?

Certificate thường được xuất để chia sẻ public key và thông tin chứng chỉ với hệ thống khác, chẳng hạn:

- Cấu hình TLS cho một dịch vụ hoặc máy chủ.
- Cung cấp certificate cho ứng dụng client, gateway hoặc reverse proxy.
- Chuyển certificate sang truststore của một ứng dụng khác sau khi đã xác minh.
- Kiểm tra subject, issuer, thời hạn, fingerprint và các extension.
- Lưu certificate ra file để dùng với công cụ như `keytool`, `openssl` hoặc nền tảng triển khai.

Export certificate không làm thay đổi entry trong keystore. Nó cũng không tự làm certificate trở thành trusted. Việc một hệ thống chấp nhận certificate phụ thuộc vào cấu hình trust, chuỗi chứng thực, thời hạn, hostname, mục đích sử dụng và chính sách xác minh của hệ thống đó.

Certificate là dữ liệu public, nhưng có thể tiết lộ hostname, tên tổ chức, email, serial number hoặc thông tin hạ tầng. Chỉ chia sẻ ở nơi phù hợp với chính sách của hệ thống.

## 2. Xác định keystore và alias trước khi export

Trước khi xuất, cần biết file keystore, loại keystore và alias chứa certificate. Có thể liệt kê các entry:

~~~sh
keytool -list -keystore app.p12 -storetype PKCS12
~~~

Keytool sẽ yêu cầu mật khẩu keystore nếu cần. Để xem chi tiết một alias:

~~~sh
keytool -list -v -alias server -keystore app.p12 -storetype PKCS12
~~~

Kết quả chi tiết có thể cho biết:

- **Entry type**: ví dụ `PrivateKeyEntry` hoặc `trustedCertEntry`.
- **Certificate chain length**: số certificate trong chain của key entry.
- **Owner/Subject** và **Issuer**.
- **Serial number**, thời hạn `Valid from` và fingerprint.
- Các extension như Subject Alternative Name, Key Usage và Extended Key Usage.

Các entry thường gặp:

| Entry type | Nội dung | Kết quả khi export |
|---|---|---|
| `PrivateKeyEntry` | Private key và certificate chain | Xuất certificate đầu tiên trong chain; private key không được xuất |
| `trustedCertEntry` | Một certificate được lưu làm trusted certificate | Xuất certificate đó |
| `SecretKeyEntry` | Secret key đối xứng, không có certificate | Không có certificate để xuất; lệnh sẽ thất bại |

Nếu alias không đúng hoặc entry không chứa certificate, keytool không thể xuất certificate mong muốn. Vì vậy, hãy kiểm tra alias và entry type trước khi chạy lệnh.

## 3. Cú pháp cơ bản của keytool -exportcert

Cú pháp tổng quát:

~~~sh
keytool -exportcert -alias <alias> -keystore <keystore-file> -file <output-file>
~~~

Ví dụ xuất certificate từ alias `server` trong PKCS#12 keystore:

~~~sh
keytool -exportcert -alias server -keystore app.p12 -storetype PKCS12 -file server.cer
~~~

Nếu keystore yêu cầu mật khẩu, keytool sẽ nhắc nhập khi chạy lệnh mà không truyền `-storepass`. Cách này tránh đặt mật khẩu trực tiếp trong command line hoặc lịch sử shell.

Ý nghĩa các tùy chọn chính:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-exportcert` | Chọn thao tác xuất certificate |
| `-alias <alias>` | Chọn entry trong keystore |
| `-keystore <file>` | Chỉ định keystore nguồn |
| `-file <file>` | Chỉ định file certificate đầu ra |
| `-storetype <type>` | Chỉ định loại keystore, ví dụ JKS hoặc PKCS12 |
| `-storepass <arg>` | Cung cấp mật khẩu keystore |
| `-rfc` | Xuất ở định dạng văn bản RFC/PEM |
| `-cacerts` | Dùng keystore chứng chỉ CA mặc định của JDK |
| `-v` | Hiển thị thông tin chi tiết hơn khi thực hiện lệnh |

Nếu keystore là JKS, có thể chỉ định rõ:

~~~sh
keytool -exportcert -alias server -keystore app.jks -storetype JKS -file server.cer
~~~

JDK hiện đại thường dùng PKCS#12 làm loại keystore mặc định, nhưng không nên dựa vào mặc định khi làm việc với file cũ hoặc môi trường có cấu hình khác. Hãy chọn `-storetype` đúng với keystore thực tế.

Nếu bỏ `-file`, certificate được ghi ra standard output. Với định dạng DER mặc định, stdout chứa dữ liệu nhị phân nên không nên in trực tiếp ra terminal; hãy dùng `-file` hoặc chuyển hướng output nhị phân vào file. Dùng `-rfc` nếu cần output PEM dạng văn bản.

## 4. DER mặc định và PEM với -rfc

`keytool -exportcert` mặc định xuất certificate dưới dạng **DER binary**. Đây là dữ liệu nhị phân ASN.1 được mã hóa theo Distinguished Encoding Rules. File thường dùng phần mở rộng .cer hoặc .der, nhưng phần mở rộng không quyết định nội dung thực tế.

Ví dụ xuất DER:

~~~sh
keytool -exportcert -alias server -keystore app.p12 -storetype PKCS12 -file server.der
~~~

Thêm `-rfc` để xuất certificate dưới dạng Base64 PEM:

~~~sh
keytool -exportcert -rfc -alias server -keystore app.p12 -storetype PKCS12 -file server.pem
~~~

File PEM thường có cấu trúc:

~~~text
-----BEGIN CERTIFICATE-----
MIID...Base64 encoded certificate data...
-----END CERTIFICATE-----
~~~

Dòng Base64 ở giữa là nội dung certificate đã được mã hóa văn bản; dấu mở đầu và kết thúc xác định loại dữ liệu PEM. Nội dung thật phụ thuộc certificate nên không có một chuỗi đầu ra cố định.

So sánh hai định dạng:

| Đặc điểm | DER mặc định | PEM (`-rfc`) |
|---|---|---|
| Dạng dữ liệu | Nhị phân | Văn bản Base64 có header/footer |
| Có thể mở bằng text editor | Không thuận tiện | Có |
| Phần mở rộng thường gặp | .cer, .der | .pem, .crt, .cer |
| Dùng cho | Java và công cụ nhận certificate DER | TLS server, proxy, công cụ cần PEM |
| Kích thước | Thường nhỏ hơn | Lớn hơn do Base64 và header |

Không thể xác định định dạng chỉ bằng tên file. Một file .cer có thể chứa DER hoặc PEM. Hãy kiểm tra nội dung hoặc dùng `keytool -printcert` để xác nhận.

## 5. Ví dụ thực hành hoàn chỉnh

Có thể tạo một keystore thử nghiệm với certificate tự ký để thực hành. Lệnh sau tạo key pair và lưu entry có alias `demo` trong file PKCS#12:

~~~sh
keytool -genkeypair -alias demo -keyalg RSA -keysize 2048 -validity 365 -dname "CN=localhost" -keystore demo.p12 -storetype PKCS12
~~~

Keytool sẽ yêu cầu nhập mật khẩu keystore. Trong môi trường học tập, hãy dùng một mật khẩu thử nghiệm và không tái sử dụng mật khẩu thật. Lệnh tạo certificate tự ký cho mục đích minh họa; certificate này không tự động được hệ thống khác tin cậy.

Xuất certificate dạng DER:

~~~sh
keytool -exportcert -alias demo -keystore demo.p12 -storetype PKCS12 -file demo.der
~~~

Xuất cùng certificate dạng PEM:

~~~sh
keytool -exportcert -rfc -alias demo -keystore demo.p12 -storetype PKCS12 -file demo.pem
~~~

Hai lệnh export sẽ hỏi mật khẩu keystore nếu cần. Chúng tạo hai file biểu diễn cùng certificate nhưng dùng hai định dạng khác nhau. Các file được ghi vào thư mục hiện tại; bảo đảm thư mục đích phù hợp và tránh ghi đè nhầm file cần giữ.

Xem nội dung certificate DER:

~~~sh
keytool -printcert -file demo.der
~~~

Xem nội dung certificate PEM:

~~~sh
keytool -printcert -file demo.pem
~~~

Cả hai lệnh đều hiển thị thông tin certificate ở dạng dễ đọc. Các trường cụ thể phụ thuộc certificate vừa tạo, ví dụ Owner/Subject, Issuer, Serial number, Validity, SHA-256 fingerprint và extension. Vì serial, fingerprint và thời điểm bắt đầu hiệu lực được tạo theo lần chạy, không nên mong đợi một output cố định.

Kiểm tra entry nguồn và chain length:

~~~sh
keytool -list -v -alias demo -keystore demo.p12 -storetype PKCS12
~~~

Với key pair demo, alias thường là `PrivateKeyEntry`; certificate chain length thường là 1 vì certificate tự ký. Lệnh `-exportcert` lấy certificate đầu tiên của chain đó.

## 6. Xuất certificate từ cacerts

JDK có keystore CA mặc định thường được gọi là `cacerts`. Có thể dùng tùy chọn `-cacerts` để truy cập keystore này thay vì chỉ định đường dẫn `-keystore`.

Ví dụ xuất một CA certificate theo alias:

~~~sh
keytool -exportcert -cacerts -alias <ca-alias> -rfc -file ca-certificate.pem
~~~

Thay `<ca-alias>` bằng alias thực tế trong `cacerts`. Có thể liệt kê alias trước bằng:

~~~sh
keytool -list -cacerts
~~~

Nếu môi trường yêu cầu quyền hoặc mật khẩu để đọc keystore, hãy làm theo cơ chế xác thực của máy. Không chỉnh sửa hay thay thế `cacerts` chỉ để xuất certificate; thao tác export chỉ cần đọc entry.

## 7. Certificate chain: exportcert chỉ trả về certificate đầu tiên

Một key entry có thể chứa certificate chain gồm certificate của máy chủ/ứng dụng và các certificate CA trung gian. Khi alias trỏ tới key entry có chain, `keytool -exportcert` trả về **certificate đầu tiên trong chain**, tức certificate xác thực public key của entity được alias đại diện.

Ví dụ, nếu chain gồm:

~~~text
server certificate
        |
        v
intermediate CA
        |
        v
root CA
~~~

Lệnh export từ alias `server` chỉ xuất server certificate. Nó không tự tạo file chứa cả ba certificate và cũng không xuất private key.

Để xem chain có bao nhiêu certificate và thứ tự của chúng:

~~~sh
keytool -list -v -alias server -keystore app.p12 -storetype PKCS12
~~~

Nếu ứng dụng cần full chain, phải cung cấp riêng các intermediate/root certificate theo yêu cầu định dạng và nền tảng đích. Có thể xuất từng certificate nếu chúng có alias riêng trong keystore, hoặc dùng công cụ phù hợp với container/format đang lưu chain. Không giả định file tạo bởi `-exportcert` đã chứa toàn bộ chain.

## 8. Xác minh certificate sau khi export

Sau khi export, hãy kiểm tra file thay vì chỉ dựa vào việc lệnh kết thúc thành công.

In thông tin certificate:

~~~sh
keytool -printcert -file server.pem
~~~

Hoặc với DER:

~~~sh
keytool -printcert -file server.der
~~~

Đối chiếu các thông tin:

- **Subject/Owner**: certificate thuộc về chủ thể nào.
- **Issuer**: CA hoặc chủ thể nào đã ký certificate.
- **Serial number**: số định danh certificate do issuer cấp.
- **Validity**: thời gian bắt đầu và kết thúc hiệu lực.
- **SHA-256 fingerprint**: dấu vân tay của certificate.
- **Subject Alternative Name (SAN)**: hostname/IP được certificate bảo vệ.
- **Key Usage / Extended Key Usage**: mục đích sử dụng được cho phép.

Khi nhận certificate từ nguồn khác hoặc chuẩn bị import vào truststore, hãy so sánh SHA-256 fingerprint với giá trị được cung cấp qua một kênh đáng tin cậy. Việc certificate tự in ra fingerprint không chứng minh nó đáng tin; người kiểm tra cần có fingerprint kỳ vọng độc lập.

Có thể kiểm tra alias nguồn bằng `keytool -list -v` và so sánh Subject, Issuer, serial, thời hạn cùng fingerprint với file đã export. Nếu khác nhau, có thể đã chọn nhầm alias, nhầm keystore hoặc nhầm file đầu ra.

## 9. Mật khẩu và an toàn khi export

`-storepass` cho phép truyền mật khẩu keystore, nhưng ghi mật khẩu trực tiếp trên command line có thể làm lộ bí mật qua shell history, process listing, log hoặc công cụ giám sát.

Khi thao tác tương tác, nên bỏ `-storepass` để keytool hỏi mật khẩu. Nếu tự động hóa, hãy dùng cơ chế quản lý secret phù hợp với nền tảng và cân nhắc cơ chế password-protected được keytool hỗ trợ như `-protected` khi provider/môi trường có cấu hình tương ứng.

Một số nguyên tắc:

- Không gửi file keystore chứa private key khi chỉ cần chia sẻ certificate.
- Không đưa mật khẩu keystore vào script hoặc repository.
- Chỉ xuất certificate từ đúng alias và đúng keystore.
- Kiểm tra fingerprint trước khi tin cậy hoặc import certificate.
- Hạn chế chia sẻ certificate có thông tin nhận dạng nội bộ nếu không cần thiết.
- Giữ bản keystore gốc và không xóa entry sau khi export.

Certificate được xuất là public data, nhưng thao tác truy cập keystore vẫn cần được bảo vệ. Không nhầm việc xuất public certificate với việc xuất private key.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Alias <name> does not exist` | Alias sai hoặc đang đọc nhầm keystore | Dùng `keytool -list` để kiểm tra alias và đường dẫn |
| `Keystore was tampered with, or password was incorrect` | Mật khẩu sai hoặc file keystore không đọc được | Xác nhận mật khẩu, file nguồn và `-storetype` |
| Không có certificate để export | Alias là secret key entry hoặc entry không có certificate | Kiểm tra entry type; chọn alias có certificate |
| File export không đọc được bằng text editor | Certificate được xuất ở định dạng DER nhị phân | Dùng `-rfc` để tạo PEM |
| Ứng dụng đích báo thiếu intermediate CA | Chỉ export certificate đầu tiên của chain | Kiểm tra chain bằng `keytool -list -v` và cung cấp các CA certificate cần thiết |
| Certificate có Subject không đúng | Chọn nhầm alias hoặc keystore | Kiểm tra Subject, Issuer, serial và fingerprint trước khi sử dụng |
| Certificate đã hết hạn hoặc chưa có hiệu lực | Thời hạn certificate không phù hợp thời điểm hiện tại | Kiểm tra Validity và xin certificate hợp lệ |
| Hostname TLS không khớp | SAN không chứa hostname mà client truy cập | Kiểm tra Subject Alternative Name và cấp certificate đúng hostname |
| Không tìm thấy output file | Thư mục đích không tồn tại hoặc không có quyền ghi | Tạo thư mục, kiểm tra đường dẫn và quyền ghi |

## 11. Quy trình export certificate

Khi cần xuất certificate từ keystore, thực hiện theo thứ tự:

1. Xác định file keystore và loại keystore (JKS hoặc PKCS12).
2. Dùng `keytool -list` để tìm alias cần xuất.
3. Dùng `keytool -list -v -alias ...` để kiểm tra entry type và chain length.
4. Chọn định dạng: DER mặc định hoặc PEM với `-rfc`.
5. Chạy `keytool -exportcert` với alias, keystore và output file rõ ràng.
6. Không truyền mật khẩu trực tiếp trên command line nếu có thể để keytool nhắc nhập.
7. Dùng `keytool -printcert` để xác minh file đã xuất.
8. So sánh fingerprint với nguồn đáng tin cậy trước khi import hoặc phân phối.
9. Nếu cần full chain, kiểm tra và cung cấp intermediate/root certificate riêng.

### Checklist

- [ ] Đã xác định đúng keystore và `-storetype`.
- [ ] Đã chọn đúng alias có certificate.
- [ ] Đã xác nhận entry type và chain length.
- [ ] Đã chọn DER hoặc PEM theo yêu cầu hệ thống đích.
- [ ] Đã dùng `-file` để lưu đúng vị trí.
- [ ] Đã hiểu `-exportcert` chỉ trả về certificate đầu tiên của key-entry chain.
- [ ] Đã xác minh certificate bằng `keytool -printcert`.
- [ ] Đã kiểm tra fingerprint, Subject, Issuer, validity và SAN.
- [ ] Đã bảo vệ mật khẩu keystore và private key.
- [ ] Đã xác nhận certificate được cung cấp đúng mục đích và trust policy.

`keytool -exportcert` là cách trực tiếp để lấy public certificate từ một alias trong keystore. Chọn đúng alias, định dạng DER/PEM và xác minh fingerprint sẽ giúp certificate có thể được chuyển sang hệ thống khác mà không làm lộ private key hoặc nhầm lẫn giữa certificate đơn lẻ và toàn bộ chain.

## Tài liệu tham khảo

- [Oracle JDK 21 — The keytool Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)
- [Oracle JDK 25 — The keytool Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html)
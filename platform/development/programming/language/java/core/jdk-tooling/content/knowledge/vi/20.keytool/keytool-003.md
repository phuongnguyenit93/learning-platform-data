# Truststore trong Java

**Truststore** là một kho chứng chỉ mà ứng dụng Java dùng để xác định những Certificate Authority (CA) hoặc peer certificate nào được tin cậy. Trong kết nối TLS/HTTPS, phía client nhận certificate chain từ server và cần xác minh chuỗi đó dẫn tới một trust anchor có trong truststore. Java thực hiện việc kiểm tra này thông qua TrustManager của JSSE.

Truststore thường chứa các trusted certificate entries, ví dụ chứng chỉ root CA hoặc CA nội bộ. Nó thường không chứa private key của ứng dụng. Private key và certificate chain dùng để chứng minh danh tính của chính ứng dụng thường nằm trong keystore và được KeyManager sử dụng.

Truststore và keystore có thể dùng cùng định dạng file như PKCS12 hoặc JKS, nhưng chúng có vai trò khác nhau. Một file keystore về mặt kỹ thuật có thể chứa nhiều loại entry; tên gọi truststore mô tả cách ứng dụng sử dụng một KeyStore để lưu các chứng chỉ mà nó tin cậy.

## 1. Truststore hoạt động trong TLS như thế nào?

Khi Java client kết nối tới một HTTPS server, TLS handshake thường diễn ra theo trình tự khái quát:

1. Client mở kết nối tới server.
2. Server gửi certificate của nó và các intermediate certificates cần thiết.
3. Client xây dựng và kiểm tra certificate path từ certificate server tới một trust anchor.
4. TrustManager kiểm tra chữ ký, thời hạn hiệu lực, chính sách thuật toán và các điều kiện của certificate chain.
5. TLS tiếp tục nếu xác thực thành công và các kiểm tra khác, gồm hostname verification, cũng đạt yêu cầu.

Ví dụ một chuỗi certificate:

~~~text
api.example.com
      |
      | được ký bởi
      v
Example Issuing CA
      |
      | được ký bởi
      v
Example Root CA
      |
      | có trong truststore
      v
Trusted certificate entry
~~~

Truststore giúp Java xác định root CA hoặc certificate được cấu hình là trust anchor. Nó không có nghĩa là chỉ cần đặt một file certificate vào truststore thì mọi kết nối tới server đó đều hợp lệ. Certificate vẫn phải đáp ứng các điều kiện xác thực khác.

### Truststore không thay thế hostname verification

Certificate chain có thể được ký bởi CA đáng tin cậy nhưng kết nối vẫn phải thất bại nếu certificate không hợp lệ cho hostname đang truy cập.

Ví dụ, ứng dụng kết nối api.example.com nhưng Subject Alternative Name (SAN) trong certificate chỉ chứa internal.example.com. TrustManager có thể xây dựng được đường dẫn tin cậy, nhưng hostname verification vẫn phát hiện tên không khớp.

Các kiểm tra độc lập gồm:

- **Trust path**: certificate chain có dẫn tới trust anchor đáng tin cậy không?
- **Validity**: certificate đã hết hạn hoặc chưa tới thời điểm hiệu lực chưa?
- **Hostname**: SAN có khớp hostname của server không?
- **Usage và constraints**: certificate có phù hợp mục đích TLS và chính sách thuật toán không?

Không tắt hostname verification để khắc phục lỗi truststore. Hãy sửa certificate, hostname hoặc cấu hình CA đúng cách.

## 2. Phân biệt truststore và keystore

Hai loại kho có thể dùng chung API KeyStore và định dạng file, nhưng được dùng cho các mục đích khác nhau.

| Tiêu chí | Truststore | Keystore |
|---|---|---|
| Mục đích | Lưu certificate được tin cậy | Lưu danh tính và khóa của ứng dụng |
| Nội dung thường gặp | Root CA, intermediate CA hoặc peer certificate được tin cậy | Private key, certificate của chủ thể và certificate chain |
| Entry thường gặp | trustedCertEntry | PrivateKeyEntry |
| Thành phần sử dụng trong JSSE | TrustManager | KeyManager |
| Câu hỏi được trả lời | Tôi tin cậy certificate của peer nào? | Tôi chứng minh danh tính của mình bằng khóa nào? |
| Ví dụ | Client tin cậy CA ký certificate của server | Server trình certificate và private key của mình |

### HTTPS client thông thường

Một client truy cập HTTPS server công khai thường cần truststore để kiểm tra certificate của server. Nó không nhất thiết cần keystore vì client không phải trình certificate để xác thực bằng client certificate.

### Mutual TLS

Trong mutual TLS (mTLS), hai bên đều xác thực certificate:

- Client dùng truststore để xác minh certificate của server.
- Client dùng keystore để giữ private key và certificate chain của chính client.
- Server dùng truststore để xác minh certificate do client gửi.
- Server dùng keystore để trình certificate và private key của server.

Truststore và keystore có thể nằm trong hai file riêng để phân quyền và quản lý vòng đời độc lập.

## 3. Định dạng truststore: PKCS12 và JKS

Truststore là một đối tượng KeyStore được lưu dưới một định dạng cụ thể. JDK hỗ trợ nhiều loại keystore thông qua security providers.

| Định dạng | Đặc điểm | Khi sử dụng |
|---|---|---|
| PKCS12 | Định dạng chuẩn, tương thích đa nền tảng | Lựa chọn mặc định phù hợp cho dự án mới |
| JKS | Định dạng keystore riêng của Java | Tương thích với hệ thống legacy |
| JCEKS | Định dạng Java cũ hỗ trợ secret-key entries | Chỉ dùng khi hệ thống có yêu cầu tương thích cụ thể |

Từ JDK 9, loại keystore mặc định là **PKCS12**. Nếu không truyền tùy chọn store type, keytool và API KeyStore sử dụng giá trị của security property keystore.type. Trong cấu hình JDK tiêu chuẩn hiện đại, giá trị này là pkcs12.

Nên chỉ rõ store type trong script triển khai để tránh phụ thuộc cấu hình của máy build hoặc runtime:

~~~bash
keytool -list -keystore app-truststore.p12 -storetype PKCS12
~~~

Một số bản JDK hiện đại phát cảnh báo về JKS và JCEKS vì các định dạng này được xem là legacy. Với hệ thống mới, ưu tiên PKCS12; với hệ thống cũ, xác nhận khả năng tương thích trước khi chuyển đổi.

### Mở rộng và chuyển đổi JKS sang PKCS12

Nếu đang có truststore cũ dạng JKS:

~~~bash
keytool -importkeystore \
  -srckeystore legacy-truststore.jks \
  -srcstoretype JKS \
  -destkeystore app-truststore.p12 \
  -deststoretype PKCS12
~~~

keytool sẽ yêu cầu password nguồn và password đích nếu chưa cung cấp. Sau khi chuyển đổi, kiểm tra lại số lượng entry, alias, fingerprint và certificate chain:

~~~bash
keytool -list -v -keystore app-truststore.p12 -storetype PKCS12
~~~

Không xóa file cũ ngay sau khi chuyển đổi. Hãy kiểm tra ứng dụng và quy trình triển khai bằng file mới trước khi thay thế bản đang sử dụng.

## 4. Truststore mặc định của JDK: cacerts

JDK phân phối một kho CA mặc định có tên **cacerts**. Kho này chứa một tập root CA được lựa chọn cho hệ sinh thái Java. Nó thường nằm trong thư mục bảo mật của Java home:

~~~text
JAVA_HOME/
  lib/
    security/
      cacerts
~~~

Có thể xem các certificate trong kho mặc định:

~~~bash
keytool -list -cacerts
~~~

Xem chi tiết:

~~~bash
keytool -list -v -cacerts
~~~

Có thể tìm một alias cụ thể:

~~~bash
keytool -list -cacerts -alias example-root-ca
~~~

### cacerts không phải danh sách mọi CA trên thế giới

cacerts chỉ chứa tập root certificate được đóng gói và quản lý theo chính sách của bản JDK. Một CA nội bộ, CA của môi trường doanh nghiệp hoặc CA mới có thể chưa nằm trong kho này.

Không nên giả định mọi certificate đều được tin cậy chỉ vì Java đã cài đặt thành công. Nếu server sử dụng private PKI, ứng dụng có thể cần truststore riêng chứa CA tương ứng.

### jssecacerts và thứ tự tìm truststore

Với JSSE reference implementation, khi không cấu hình system property javax.net.ssl.trustStore, default SSLContext tìm truststore theo thứ tự:

1. File jssecacerts trong thư mục security của Java home.
2. File cacerts trong cùng thư mục nếu jssecacerts không tồn tại.
3. Nếu không tìm thấy cả hai, TrustManager sử dụng một truststore rỗng.

Nếu property javax.net.ssl.trustStore được chỉ định, file đó được dùng làm truststore. Nếu property đã được đặt nhưng đường dẫn trỏ tới file không tồn tại, JSSE reference implementation không tự quay về cacerts; trường hợp này dẫn tới việc không sử dụng truststore được chỉ định.

Đây là lý do cần kiểm tra chính xác đường dẫn khi triển khai custom truststore.

## 5. Tạo truststore riêng bằng keytool

Cách thường dùng là tạo truststore riêng cho ứng dụng và import certificate của CA mà ứng dụng cần tin cậy.

Giả sử CA nội bộ cung cấp file:

~~~text
certificates/
  company-root-ca.pem
~~~

### Bước 1: Xem certificate trước khi import

~~~bash
keytool -printcert -file certificates/company-root-ca.pem
~~~

Lệnh hiển thị các thông tin như subject, issuer, thời hạn hiệu lực và SHA-256 fingerprint.

Không nên tin certificate chỉ vì file được gửi kèm email hoặc tải từ một server. Hãy so sánh SHA-256 fingerprint với giá trị được CA hoặc quản trị viên cung cấp qua một kênh độc lập và đáng tin cậy.

### Bước 2: Import certificate

~~~bash
keytool -importcert \
  -alias company-root-ca \
  -file certificates/company-root-ca.pem \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

keytool sẽ yêu cầu password nếu cần tạo hoặc mở truststore, sau đó hiển thị thông tin certificate và hỏi người dùng có tin cậy certificate hay không.

Chỉ xác nhận import sau khi đã xác minh fingerprint và danh tính CA.

Nếu alias đã tồn tại trong truststore dưới dạng trusted certificate entry, keytool sẽ báo lỗi thay vì tự ghi đè entry đó. Hãy kiểm tra alias trước khi quyết định thay thế.

### Bước 3: Xác nhận entry đã được thêm

~~~bash
keytool -list -v \
  -keystore app-truststore.p12 \
  -storetype PKCS12 \
  -alias company-root-ca
~~~

Kiểm tra:

- Alias đúng với tên đã chọn.
- Entry type là trustedCertEntry.
- Subject và issuer đúng với CA dự kiến.
- Validity dates hợp lệ.
- SHA-256 fingerprint khớp giá trị đã xác minh.

Ví dụ output rút gọn minh họa:

~~~text
Alias name: company-root-ca
Entry type: trustedCertEntry

Owner: CN=Company Root CA, O=Example Corp
Issuer: CN=Company Root CA, O=Example Corp
Valid from: ...
Certificate fingerprints:
         SHA256: ...
~~~

Các giá trị ngày tháng và fingerprint thực tế phụ thuộc certificate được import.

## 6. Import certificate chain và chọn đúng CA

Một server thường gửi certificate leaf cùng các intermediate certificates. Root CA có thể không được server gửi trong handshake vì client dự kiến đã có trust anchor đó.

Ví dụ:

~~~text
api.internal.example
       |
       v
Example TLS Issuing CA
       |
       v
Example Root CA
~~~

Nếu ứng dụng cần tin cậy hệ thống CA nội bộ, thông thường hãy import root CA được tổ chức xác nhận. Trong một số mô hình PKI, tổ chức có thể chỉ định một intermediate CA làm trust anchor; quyết định này cần theo chính sách PKI.

Không nên import mọi certificate mà server gửi vào truststore mà không hiểu vai trò của từng certificate. Certificate leaf có thể được import như một trusted certificate entry, nhưng cách này gắn niềm tin trực tiếp với certificate cụ thể và làm quy trình gia hạn hoặc thay certificate khó khăn hơn.

### Kiểm tra certificate chain từ server

keytool có thể hiển thị certificate mà server trình bày:

~~~bash
keytool -printcert -sslserver api.internal.example:443
~~~

Lệnh này hữu ích để quan sát certificate chain đang được server gửi. Nó không tự chứng minh certificate đó đáng tin cậy. Vẫn phải xác minh fingerprint và danh tính CA qua nguồn độc lập.

### Import certificate từ file PEM hoặc DER

keytool hỗ trợ certificate X.509 ở dạng binary DER hoặc printable Base64/PEM. Một file PEM thường có cấu trúc:

~~~text
-----BEGIN CERTIFICATE-----
Base64 encoded certificate data
-----END CERTIFICATE-----
~~~

keytool cũng hỗ trợ certificate chain ở định dạng PKCS#7 hoặc chuỗi certificate X.509 theo định dạng được tài liệu quy định.

Nếu file chứa nhiều certificate, hãy xác định thứ tự và vai trò của từng certificate trước khi import. Không dùng một file bundle không rõ nguồn gốc làm trust anchor.

## 7. Dùng truststore với ứng dụng Java qua JSSE

JSSE reference implementation hỗ trợ các system properties để cấu hình truststore mặc định.

| System property | Công dụng |
|---|---|
| javax.net.ssl.trustStore | Đường dẫn truststore |
| javax.net.ssl.trustStoreType | Định dạng truststore, ví dụ PKCS12 |
| javax.net.ssl.trustStorePassword | Password để mở truststore |
| javax.net.ssl.keyStore | Đường dẫn keystore chứa danh tính local |
| javax.net.ssl.keyStoreType | Định dạng keystore |
| javax.net.ssl.keyStorePassword | Password keystore |

Ví dụ khởi chạy ứng dụng với truststore riêng:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/etc/acme/app-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar app.jar
~~~

Nếu truststore được bảo vệ bằng password khác chuỗi rỗng, ứng dụng cần cung cấp property javax.net.ssl.trustStorePassword thông qua cấu hình bảo mật của môi trường triển khai.

Không ghi password thật vào source code, file cấu hình được commit, lệnh build hoặc log. Ưu tiên secret manager hoặc cơ chế bảo vệ secret của nền tảng triển khai. Nếu dùng keytool trong script, JDK 26 hỗ trợ nhận password từ environment variable hoặc file qua các dạng password modifier tương ứng.

### Khi nào JSSE đọc các property?

Các system properties này được dùng khi default SSLContext và TrustManager tương ứng được khởi tạo. Hãy đặt cấu hình trước khi ứng dụng tạo TLS client hoặc khởi tạo default SSLContext.

Nếu thư viện đã tạo và cache SSLContext trước thời điểm đặt property, thay đổi property sau đó có thể không tác động tới context đang dùng.

### Custom SSLContext

Nếu ứng dụng tự tạo SSLContext hoặc TrustManagerFactory, ứng dụng có thể truyền KeyStore riêng trực tiếp qua API thay vì dựa vào default system properties.

Ví dụ luồng cấu hình:

~~~java
KeyStore trustStore = KeyStore.getInstance("PKCS12");

try (InputStream input = Files.newInputStream(trustStorePath)) {
    trustStore.load(input, trustStorePassword);
}

TrustManagerFactory trustManagerFactory =
        TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());

trustManagerFactory.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        null,
        trustManagerFactory.getTrustManagers(),
        null);
~~~

Đây là đoạn cấu hình cốt lõi; các biến trustStorePath và trustStorePassword phải được cung cấp từ cấu hình ứng dụng hoặc secret manager. Khi dùng custom SSLContext, hãy xác nhận HTTP client hoặc TLS client thực sự sử dụng socket factory/context này.

## 8. Truststore riêng có thay thế cacerts không?

Khi cấu hình javax.net.ssl.trustStore trỏ tới một file riêng, JSSE dùng file đó cho default TrustManager. Nó không tự động hợp nhất các entry trong custom truststore với cacerts.

Ví dụ:

~~~text
JDK cacerts:
  Public Root CA A
  Public Root CA B
  Public Root CA C

app-truststore.p12:
  Company Root CA
~~~

Nếu ứng dụng chỉ dùng app-truststore.p12, các public root CA từ cacerts không tự động được thêm vào custom truststore. Ứng dụng có thể tin cậy CA nội bộ nhưng lại thất bại khi truy cập website công khai.

Có ba hướng triển khai:

1. **Chỉ dùng custom CA**: phù hợp ứng dụng chỉ kết nối tới hệ thống nội bộ có PKI riêng.
2. **Tạo truststore kết hợp**: đưa các public CA cần thiết và internal CA vào cùng một truststore do ứng dụng quản lý.
3. **Dùng custom TrustManager strategy**: ứng dụng kiểm soát rõ cách kết hợp nhiều nguồn trust theo yêu cầu bảo mật.

Nếu cần cả public CA và internal CA, hãy tạo truststore kết hợp bằng cách import những certificate đã được xác minh từ các nguồn tin cậy. Ghi lại nguồn, fingerprint và quy trình cập nhật của từng CA.

Không nên sao chép toàn bộ cacerts vào ứng dụng một cách máy móc. Tập CA cần dùng phụ thuộc vào hệ thống, chính sách bảo mật và vòng đời certificate.

## 9. Quản lý truststore mặc định cacerts

Có thể import certificate vào kho mặc định của JDK bằng tùy chọn -cacerts:

~~~bash
keytool -importcert \
  -cacerts \
  -alias company-root-ca \
  -file company-root-ca.pem
~~~

keytool có thể yêu cầu password và quyền ghi phù hợp. Trên một số hệ thống, thư mục cài đặt JDK không cho user thông thường ghi trực tiếp.

Xem lại entry:

~~~bash
keytool -list -v -cacerts -alias company-root-ca
~~~

Xóa entry khi CA không còn được tin cậy hoặc đã bị thu hồi theo chính sách tổ chức:

~~~bash
keytool -delete -cacerts -alias company-root-ca
~~~

### Vì sao nên thận trọng khi sửa cacerts?

cacerts là kho CA dùng chung của Java home. Thay đổi có thể ảnh hưởng nhiều ứng dụng chạy trên cùng JDK, không chỉ một ứng dụng.

Một số lưu ý:

- Chỉ thêm CA đã được xác minh và được phép tin cậy.
- Lưu lại alias, subject, issuer và fingerprint.
- Kiểm soát quyền ghi đối với file cacerts.
- Sao lưu theo quy trình quản trị hệ thống trước khi thay đổi.
- Theo dõi việc CA hết hạn, bị thu hồi hoặc bị chính sách JDK distrust.
- Kiểm tra ứng dụng sau khi cập nhật hoặc xóa certificate.

Password ban đầu của cacerts trong một số bản phân phối JDK được tài liệu mô tả là changeit, nhưng quản trị viên có thể thay đổi password và quyền truy cập. Không nên dựa vào password mặc định như một bảo đảm cho mọi môi trường.

## 10. Kiểm tra và chẩn đoán truststore

### Liệt kê toàn bộ entry

~~~bash
keytool -list \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

### Xem chi tiết một certificate

~~~bash
keytool -list -v \
  -keystore app-truststore.p12 \
  -storetype PKCS12 \
  -alias company-root-ca
~~~

### Xem certificate file trước khi import

~~~bash
keytool -printcert -file company-root-ca.pem
~~~

### Xem certificate server đang trình bày

~~~bash
keytool -printcert -sslserver api.example.com:443
~~~

### Xem version của keytool

~~~bash
keytool -version
~~~

### Bật JSSE debug khi điều tra TLS

Có thể bật diagnostic của JSSE:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar app.jar
~~~

Output có thể rất dài và chứa thông tin về handshake, certificate chain và quyết định trust. Chỉ bật khi điều tra có kiểm soát, không để debug log nhạy cảm tồn tại lâu trong production.

## 11. Lỗi thường gặp khi dùng truststore

| Lỗi hoặc hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| PKIX path building failed | Không tìm được đường dẫn từ certificate server tới trust anchor | Kiểm tra chain, CA cần tin cậy và truststore đang được ứng dụng sử dụng |
| unable to find valid certification path | Thiếu root/intermediate CA hoặc chain server gửi không đầy đủ | Xác minh CA và import trust anchor phù hợp |
| Trust anchor for certification path not found | Certificate chain không kết thúc ở CA được tin cậy | Kiểm tra certificate, alias và truststore |
| Keystore was tampered with, or password was incorrect | Sai password, sai store type hoặc file bị hỏng | Kiểm tra password, PKCS12/JKS và tính toàn vẹn file |
| Unrecognized keystore format | Khai báo sai store type hoặc file không phải keystore hợp lệ | Dùng đúng --storetype và xác nhận file |
| File truststore không được tìm thấy | Đường dẫn system property sai hoặc file chưa được triển khai | Kiểm tra đường dẫn tuyệt đối và quyền đọc |
| Certificate import báo alias đã tồn tại | Alias đang trỏ tới trusted certificate entry | Kiểm tra entry trước khi thay đổi alias |
| Certificate expired | Certificate hoặc CA đã hết hạn | Yêu cầu certificate mới và cập nhật chain |
| No subject alternative DNS name matching | Hostname không khớp SAN của certificate | Sửa hostname hoặc cấp certificate đúng SAN |
| Certificate signature algorithm disabled | Thuật toán bị chính sách bảo mật của JDK vô hiệu hóa | Dùng certificate và thuật toán còn được hỗ trợ |
| Public HTTPS không còn kết nối sau khi cấu hình truststore riêng | Custom truststore không chứa public root CA cần thiết | Tạo truststore kết hợp nếu ứng dụng cần cả public và private CA |
| Import thành công nhưng TLS vẫn lỗi | Ứng dụng dùng SSLContext hoặc TrustManager khác | Kiểm tra cấu hình TLS thực tế của HTTP client |

## 12. Certificate chain và các nguyên tắc tin cậy

Không phải certificate nào cũng nên được import vào truststore. Trước khi import, cần xác định certificate đó có vai trò gì.

| Certificate | Vai trò | Cách xử lý thường gặp |
|---|---|---|
| Root CA | Trust anchor ở đầu chuỗi | Import nếu tổ chức xác nhận cần tin cậy CA này |
| Intermediate CA | CA ký certificate cho server hoặc CA cấp dưới | Thường được server gửi trong chain; chỉ dùng làm trust anchor khi chính sách yêu cầu |
| Server/leaf certificate | Chứng minh danh tính hostname cụ thể | Không tự động tin cậy chỉ vì lấy được từ server |
| Self-signed certificate | Certificate tự ký, thường dùng trong lab hoặc private service | Chỉ trust khi đã xác minh fingerprint và có chính sách rõ ràng |

### Vì sao phải xác minh fingerprint?

Bất kỳ ai cũng có thể tạo một certificate tự ký với Subject DN giống một CA nổi tiếng. Tên trong certificate không tự chứng minh public key thuộc đúng CA đó.

Trước khi import certificate:

1. Lấy certificate từ nguồn được tổ chức hoặc CA xác nhận.
2. Dùng keytool -printcert để xem fingerprint.
3. So sánh SHA-256 fingerprint với fingerprint công bố qua một kênh độc lập.
4. Kiểm tra subject, issuer và validity.
5. Xác định certificate có phải trust anchor mà ứng dụng cần hay không.
6. Chỉ sau đó mới import vào truststore.

Không dùng -noprompt để tự động chấp nhận certificate chưa được xác minh. Tự động hóa quy trình import cần có bước kiểm tra fingerprint hoặc kiểm soát nguồn certificate đáng tin cậy.

## 13. Cập nhật, xoay vòng và xóa certificate

Certificate có vòng đời. Root CA có thể bị thay thế, intermediate CA có thể được gia hạn, certificate server có thể được cấp mới và chính sách trust có thể thay đổi.

Quy trình cập nhật nên bao gồm:

1. Xác định CA cũ và CA mới.
2. Thu thập certificate mới từ nguồn chính thức.
3. Xác minh fingerprint, subject và issuer.
4. Import certificate mới với alias rõ ràng.
5. Kiểm tra truststore sau khi import.
6. Triển khai ứng dụng và test TLS.
7. Xác nhận các kết nối đang sử dụng chain mới.
8. Xóa certificate cũ khi không còn cần thiết theo chính sách.

Nếu cần đổi alias:

~~~bash
keytool -changealias \
  -alias old-company-ca \
  -destalias company-root-ca \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

Nếu cần xóa certificate:

~~~bash
keytool -delete \
  -alias old-company-ca \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

Không xóa CA cũ trước khi xác nhận tất cả hệ thống liên quan đã chuyển sang chain mới. Việc thay đổi trust anchor có thể làm gián đoạn các kết nối còn phụ thuộc certificate cũ.

## 14. Bảo vệ truststore trong môi trường triển khai

Certificate công khai không cần giữ bí mật như private key, nhưng truststore vẫn cần bảo vệ tính toàn vẹn. Kẻ tấn công có thể thêm certificate không đáng tin cậy vào truststore nếu có quyền sửa file, khiến ứng dụng chấp nhận một CA giả mạo.

Các biện pháp phù hợp:

- Chỉ cho tài khoản triển khai hoặc quản trị viên được sửa truststore.
- Cho ứng dụng quyền đọc tối thiểu cần thiết.
- Không đặt truststore trong thư mục tạm hoặc thư mục có quyền ghi công khai.
- Kiểm soát password và cơ chế bảo vệ file theo môi trường.
- Lưu fingerprint và nguồn gốc certificate trong cấu hình quản trị.
- Theo dõi thay đổi truststore qua version control hoặc artifact quản lý phù hợp, không đưa secret vào repository.
- Kiểm tra file truststore sau khi deploy.
- Có quy trình thu hồi CA khi phát hiện certificate hoặc private key CA bị xâm phạm.

Password của truststore chủ yếu bảo vệ tính toàn vẹn của kho. Certificate là dữ liệu công khai; mục tiêu bảo mật quan trọng là ngăn người không được phép thay đổi tập trust anchor.

## 15. Quy trình triển khai truststore cho ứng dụng

Một quy trình có thể áp dụng trong dự án:

1. Xác định TLS endpoint và CA mà ứng dụng cần tin cậy.
2. Xác định ứng dụng đang dùng default SSLContext hay custom SSLContext.
3. Lấy CA certificate từ nguồn được xác nhận.
4. Kiểm tra SHA-256 fingerprint và certificate validity.
5. Tạo truststore riêng dạng PKCS12 bằng keytool.
6. Import certificate bằng alias có ý nghĩa.
7. Dùng keytool -list -v để xác minh entry.
8. Cấu hình javax.net.ssl.trustStore và trustStoreType trước khi SSLContext được tạo, hoặc cấu hình TrustManagerFactory trực tiếp.
9. Nếu cần cả public CA và private CA, tạo truststore kết hợp có kiểm soát.
10. Chạy integration test HTTPS và xác nhận hostname verification vẫn bật.
11. Triển khai truststore với quyền đọc phù hợp.
12. Ghi lại fingerprint, nguồn certificate, ngày hiệu lực và lịch cập nhật.

Với ứng dụng mTLS, thực hiện thêm bước cấu hình keystore để ứng dụng trình client certificate. Truststore và keystore cần được kiểm tra độc lập vì lỗi xác thực server và lỗi trình client identity là hai vấn đề khác nhau.

## 16. Ghi nhớ

- Truststore lưu các certificate được tin cậy để xác minh certificate chain của peer.
- TrustManager sử dụng truststore; KeyManager sử dụng keystore chứa private key và certificate identity.
- Truststore thường chứa trustedCertEntry, chẳng hạn root CA hoặc CA nội bộ.
- Truststore và keystore có thể dùng cùng định dạng file nhưng không có cùng vai trò.
- JDK 9 trở lên mặc định sử dụng PKCS12; JKS là định dạng legacy cần cân nhắc chuyển đổi.
- cacerts là truststore CA mặc định của JDK; jssecacerts được JSSE reference implementation ưu tiên tìm trước cacerts khi không có trustStore property.
- javax.net.ssl.trustStore cấu hình file truststore cho default JSSE TrustManager.
- Custom truststore không tự động hợp nhất với cacerts.
- Certificate chain hợp lệ và hostname verification là hai kiểm tra riêng biệt.
- Luôn xác minh SHA-256 fingerprint qua nguồn độc lập trước khi import certificate.
- Không dùng -noprompt để chấp nhận certificate không được xác minh.
- Dùng keytool -list, -printcert và -importcert để kiểm tra, xem và thêm certificate.
- Truststore cần được bảo vệ khỏi thay đổi trái phép và cập nhật theo vòng đời CA.

## Tài liệu tham khảo chính thức

- [The keytool Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html)
- [Security Developer's Guide — Customizing JSSE, JDK 26](https://docs.oracle.com/en/java/javase/26/security/security-developer-guide.pdf)
- [JDK Trust Management](https://ops.java/security/trust)
- [JDK 26 Release Notes — Security Changes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [Java KeyStore API — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html)
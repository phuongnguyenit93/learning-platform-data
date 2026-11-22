# TLS, chứng thư máy chủ, private key và chuỗi chứng thư trong Spring Boot

**Ngữ cảnh:** Spring Boot → web-runtime → TLS và HTTP/2. Bài này giải thích cách HTTPS xác thực máy chủ qua chứng thư X.509, vai trò của khóa riêng và public key, chuỗi tin cậy CA, cách lắp đặt HTTPS trong Spring Boot (PKCS12, PEM và SSL bundles), kiểm tra bằng `keytool`/`openssl`/`curl`, vận hành chứng thư, TLS termination, mTLS và mối liên hệ với HTTP/2.

**Môi trường ví dụ:** Java 17+, Maven, Spring Boot **3.5.0**, Spring MVC với embedded Tomcat. Các thông số domain, đường dẫn, password và file chứng thư trong bài là **minh họa**. Chỉ tạo chứng thư tự ký để học trên `localhost`; production phải dùng danh tính và chuỗi CA đúng với hạ tầng của mình.

## 1. Bức tranh tổng thể: HTTPS dùng TLS để làm gì?

**HTTPS = HTTP chạy qua TLS**. TLS là giao thức thiết lập một kênh được mã hóa và kiểm tra toàn vẹn giữa hai đầu kết nối. Trong mô hình HTTPS public thông thường, TLS giúp:

1. **Xác thực máy chủ:** client có thể kiểm tra máy chủ đang nói chuyện thực sự kiểm soát khóa riêng tương ứng với chứng thư hợp lệ cho hostname mà client định truy cập.
2. **Bảo mật nội dung trên đường truyền:** bên thứ ba quan sát mạng không đọc trực tiếp HTTP request/response đã mã hóa.
3. **Phát hiện sửa đổi trên đường truyền:** dữ liệu được xác thực bằng cơ chế mật mã của phiên TLS.
4. **Thương lượng tham số kết nối:** phiên bản TLS, thuật toán và trong nhiều triển khai cả giao thức ứng dụng (ALPN: `h2` hoặc `http/1.1`).

TLS **không** tự xác thực người dùng vào tài khoản, không sửa lỗ hổng SQL injection/XSS, không che giấu mọi metadata mạng (ví dụ địa chỉ IP đích), và không bảo vệ dữ liệu sau khi ứng dụng đã giải mã tại điểm TLS termination.

~~~text
                       HTTPS request
Browser/client ─────────────────────────────────────► HTTPS endpoint
   │                      TLS handshake                    │
   │  1. ClientHello, SNI, ciphers, key shares, ALPN        │
   │  2. ServerHello + chứng thư X.509 và chain             │
   │  3. Kiểm tra hostname, CA, thời hạn, key usage         │
   │  4. Server chứng minh có private key; hoàn tất keys    │
   │◄───────────────────────────────────────────────────────│
   │             Sau đó gửi HTTP được mã hóa                │
   │◄══════════════════ dữ liệu bảo mật ═══════════════════►│
~~~

Lưu ý: sơ đồ là diễn giải ở mức khái niệm, **không phải** bản chép thứ tự chính xác mọi thông điệp TLS 1.2/1.3. Ở TLS 1.3, một phần handshake (gồm certificate messages) đã được bảo vệ bằng handshake traffic keys. TLS 1.3 thường dùng (EC)DHE để thiết lập shared secret; private key gắn với certificate được dùng **xác thực/signature**, không nên nói đơn giản rằng “server lấy private key giải mã toàn bộ HTTPS traffic”.

## 2. Bốn đối tượng cần phân biệt

| Đối tượng | Chứa gì? | Được gửi cho client? | Phải giữ bí mật? |
| --- | --- | --- | --- |
| **Server certificate (leaf/end-entity)** | X.509: public key, SAN/identity, issuer, serial, validity, extensions, chữ ký của CA | **Có** trong handshake | **Không**, nhưng thông tin trong cert có thể cần phân loại |
| **Server private key** | Khóa bí mật khớp với public key trong leaf certificate | **Không bao giờ** đưa theo handshake | **Có — tuyệt đối** |
| **Intermediate CA certificate(s)** | Public key và danh tính các CA cấp trung gian, được CA cấp trên ký | **Thường có**, server gửi kèm leaf | Không; đây là public certificates |
| **Root CA certificate / trust anchor** | Public key của CA gốc được client đặt tin cậy qua trust store | Thường **không cần** gửi từ server; client đã có | Certificate không bí mật; **root CA private key** cực kỳ nhạy cảm |

Cách ghi nhớ: **chứng thư nói “public key này thuộc về danh tính nào, do ai xác nhận”**, **private key chứng minh quyền kiểm soát public key đó**, còn **certificate chain đưa ra lộ trình xác thực về một CA mà client tin cậy**.

### 2.1. Không đồng nhất certificate với private key

Một chứng thư có thể xem bằng lệnh `openssl x509 -text` vì nó là dữ liệu công khai. Việc copy certificate không khiến ai có quyền giả làm website, nếu kẻ đó **không sở hữu private key tương ứng**. Ngược lại, khi private key bị lộ, đối tượng khác có thể giả làm endpoint cho chứng thư hợp lệ trong những điều kiện phù hợp; cần **thu hồi/thay thế key và certificate**, không chỉ thay password Java KeyStore rồi coi như đã an toàn.

Certificate file thường có block:

~~~text
-----BEGIN CERTIFICATE-----
... Base64-encoded X.509 certificate ...
-----END CERTIFICATE-----
~~~

Private key PEM có thể ở dạng PKCS#8:

~~~text
-----BEGIN PRIVATE KEY-----
... private key material: TUYỆT ĐỐI không chia sẻ ...
-----END PRIVATE KEY-----
~~~

Hoặc encrypted PKCS#8 bắt đầu bằng `-----BEGIN ENCRYPTED PRIVATE KEY-----`. Không dán private key thật vào issue, log, chat, README, Git, container image công khai hoặc URL. Placeholder ở đây **không phải khóa thật**.

### 2.2. CSR là gì?

**Certificate Signing Request (CSR)** chứa thông tin yêu cầu cấp chứng thư và public key, thường có signature chứng minh người xin giữ private key. CSR được gửi tới CA để kiểm tra chủ thể/domain và cấp chứng thư. **Không gửi private key cho CA** trong quy trình cấp chứng thư thông thường.

~~~text
Người sở hữu domain:
  Tạo key pair → giữ private key bí mật
               → tạo CSR (public key + identity)
               → gửi CSR / xác thực quyền quản lý domain
CA:
  Kiểm tra chính sách → ký leaf certificate
Người sở hữu domain:
  Nhận leaf cert và chain
  Triển khai leaf + intermediates + private key cùng cặp
~~~

Một CSR được CA chấp thuận không đảm bảo mọi SAN người xin đưa vào đều được cấp: CA có thể giới hạn theo xác thực domain/policy. Với client công khai, tên miền phải khớp **SAN của certificate thực tế** mà server gửi.

## 3. Đọc một chứng thư X.509 máy chủ

Các trường/extensions quan trọng:

| Trường | Ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- |
| **Subject / CN** | Subject được ghi trong chứng thư | Không dùng CN thay SAN như quy tắc hostname hiện đại |
| **Subject Alternative Name (SAN)** | DNS name/IP mà chứng thư bao phủ | `DNS:api.example.com` hay `IP:192.0.2.10` phải khớp với tên truy cập |
| **Issuer** | CA cấp chứng thư | Có chain hợp lệ từ issuer đến root tin cậy |
| **Not Before / Not After** | Thời gian hiệu lực | Đồng hồ client/server và thời hạn chứng thư |
| **Subject Public Key Info** | Algorithm và public key | Khớp với private key nằm trong keystore |
| **Signature Algorithm** | Cách issuer ký chứng thư | Thuật toán đủ mạnh và client hỗ trợ |
| **Basic Constraints** | `CA:FALSE` ở leaf; `CA:TRUE` ở CA | Không nhầm leaf certificate với CA certificate |
| **Key Usage** | Ví dụ `digitalSignature`; ở CA thường có `keyCertSign` | Phù hợp chức năng chứng thư |
| **Extended Key Usage (EKU)** | Ví dụ `serverAuth`, `clientAuth` | Server TLS certificate cần hợp lệ cho server authentication theo chính sách client |
| **Serial Number / SKI / AKI** | Định danh và gợi ý liên kết issuer | Hữu ích khi debug chain và rotation |

**Hostname phải khớp SAN đúng loại.** Nếu truy cập `https://api.example.com`, certificate phải phù hợp `DNS:api.example.com` hoặc wildcard hợp lệ. Nếu truy cập qua `https://127.0.0.1`, một SAN chỉ có `DNS:localhost` không tương đương `IP:127.0.0.1`. Wildcard `*.example.com` thường khớp một nhãn như `api.example.com` nhưng **không** mặc nhiên khớp `example.com` hay `a.b.example.com`.

**Không phải cứ chưa hết hạn là certificate hợp lệ.** Một certificate còn trong khoảng thời gian nhưng sai hostname, thiếu intermediate, bị cấp sai purpose, không đến được trust anchor, hoặc key không khớp đều có thể làm handshake/xác thực thất bại.

## 4. Chuỗi chứng thư (certificate chain) và trust store

Ví dụ hệ thống PKI đơn giản:

~~~text
                       CLIENT TRUST STORE
                    ┌─────────────────────┐
                    │ Root CA certificate │  ◄── Trust anchor
                    │   public key Root   │      do client chọn tin
                    └──────────┬──────────┘
                               │ verify issuer signature
                    ┌──────────▼──────────┐
                    │ Intermediate CA cert│  ◄── Server thường gửi
                    │  public key Inter   │
                    └──────────┬──────────┘
                               │ verify issuer signature
                    ┌──────────▼──────────┐
                    │ Server leaf cert    │  ◄── Server gửi trước
                    │ SAN: api.example.com│
                    │ public key Server   │
                    └──────────┬──────────┘
                               │ verify proof of key possession
                    ┌──────────▼──────────┐
                    │ SERVER private key  │  ◄── Chỉ lưu ở server
                    └─────────────────────┘
~~~

**Mô tả hướng xác minh:** client dùng public key của intermediate CA để kiểm chứng chữ ký trên leaf; dùng public key của root CA để kiểm chứng chữ ký trên intermediate; root được tin bởi **trust policy của client**, không phải chỉ vì root tự ký. Client còn kiểm tra SAN, thời gian, CA constraints, EKU, chữ ký/thuật toán và chính sách xác thực/thu hồi tùy môi trường.

Một root tự ký **không tự trở thành đáng tin**. Việc đưa root của riêng bạn vào trust store là quyết định tin cậy độc lập của máy khách/tổ chức.

### 4.1. Server cần gửi những certificate nào?

Trong triển khai thông thường, server gửi chain theo thứ tự:

1. **Leaf/server certificate** (chứa public key khớp với server private key).
2. Một hoặc nhiều **intermediate CA certificates**, lần lượt nối đến trust anchor.
3. **Root CA certificate thường không cần đưa vào fullchain**; client phải sẵn tin root đó. Gửi root không tự khiến client chấp nhận root lạ.

~~~text
fullchain.pem  (chỉ gồm các certificate công khai)
  -----BEGIN CERTIFICATE-----  # leaf: api.example.com
  ...
  -----END CERTIFICATE-----
  -----BEGIN CERTIFICATE-----  # intermediate CA
  ...
  -----END CERTIFICATE-----

privkey.pem    (file KHÁC, chứa private key)
  -----BEGIN PRIVATE KEY-----
  ...
  -----END PRIVATE KEY-----
~~~

**Không đưa private key vào `fullchain.pem`.** Một cấu hình server cần **certificate chain + private key tương ứng**; nhầm chỉ cung cấp intermediate thay leaf, dùng private key của bản cert khác, hay thiếu intermediate là lỗi vận hành phổ biến.

Một số CA cung cấp file riêng `cert.pem` (leaf), `chain.pem` (intermediates), `fullchain.pem` (leaf + intermediates). **Tên file chỉ là convention**: hãy kiểm tra nội dung thật thay vì suy ra chắc chắn từ tên.

### 4.2. Keystore và truststore là hai mục đích khác nhau

- **Server keystore / key material:** giữ server private key **và** certificate chain tương ứng để server thực hiện TLS handshake.
- **Client truststore:** chứa các trust anchors (CA certificates) mà client dùng để quyết định certificate của server nào đáng tin. Browser, JVM, OS và một số ứng dụng có trust store riêng.
- **Server truststore** có ý nghĩa khi server cần **xác thực certificate của client** (mTLS), hoặc khi JVM làm TLS client gọi dịch vụ bên ngoài qua trust config tương ứng. Nó không thay certificate chain server phải trình bày.

**Nhầm lẫn thường gặp:** Import root CA vào keystore chứa server key rồi nghĩ HTTPS đã tự hợp lệ trên máy client. Máy khách chưa tin root đó thì vẫn có thể từ chối. Ngược lại, đưa root CA vào browser trust store **không sửa được** lỗi server thiếu private key hoặc SAN sai.

## 5. TLS 1.3 handshake: public key và private key tham gia ra sao?

Ở TLS 1.3 server authentication bằng certificate, luồng rút gọn:

1. Browser gửi `ClientHello`, trong đó có TLS versions/cipher suites, key shares (để trao đổi khóa), có thể kèm **SNI** (`api.example.com`) và **ALPN** (`h2`, `http/1.1`).
2. Server chọn tham số, trả `ServerHello`, cùng các handshake messages cần thiết; hai bên tính ra handshake traffic secrets từ (EC)DHE hoặc cơ chế phù hợp.
3. Server gửi certificate chain; client kiểm chứng nó đến trust anchor cùng hostname, thời gian và các constraints.
4. Server gửi `CertificateVerify`, ký transcript handshake bằng **private key tương ứng với leaf certificate** để chứng minh quyền sở hữu key.
5. Hai bên xác thực `Finished`, sinh application traffic keys, tiếp tục truyền HTTP được bảo vệ.

**Private key không được gửi qua mạng.** Trong TLS 1.3, private key của certificate không phải “khóa đối xứng dùng mã hóa từng HTTP packet”; khóa traffic được dẫn xuất từ key exchange/handshake. Bởi vậy có thể thay đổi key/cert theo chính sách mà không nhầm với cơ chế session key; TLS 1.3 hiện đại cung cấp đặc tính forward secrecy trong các handshake dùng ephemeral DHE phù hợp.

Certificate không tự mã hóa request; nó đóng vai trò **xác thực** đầu bên kia trong handshake TLS. Một attacker có thể tạo chứng thư tự ký cho `api.example.com`, nhưng trình duyệt bình thường sẽ **không tin** trừ khi attacker có thể đưa trust anchor của mình vào client truststore hoặc lợi dụng sự cố PKI.

### 5.1. SNI và ALPN không phải cùng một thứ

- **SNI (Server Name Indication):** client gửi hostname để server/proxy chọn certificate phù hợp khi nhiều tên miền dùng chung IP:port. Có SNI **không chứng minh** certificate hợp lệ; client vẫn phải kiểm tra SAN và chain.
- **ALPN (Application-Layer Protocol Negotiation):** TLS handshake chọn protocol ứng dụng như `h2` (HTTP/2 over TLS) hoặc `http/1.1`. Certificate hợp lệ **không đồng nghĩa** chắc chắn dùng HTTP/2.
- **TLS termination:** nơi kết nối TLS bị kết thúc và HTTP được giải mã (load balancer, ingress, reverse proxy hoặc chính Spring Boot). Certificate/private key phải nằm ở **điểm thực sự terminate TLS**, không nhất thiết ở JVM.

## 6. Các dạng file certificate/key phổ biến

| Định dạng | Đặc điểm | Dùng trong Java/Spring Boot |
| --- | --- | --- |
| **PEM** | Base64 + `BEGIN/END ...`; có thể chứa cert, chain, private key (thường chia file) | Spring Boot hỗ trợ cấu hình PEM trực tiếp hoặc PEM SSL bundle |
| **DER** | Dữ liệu nhị phân ASN.1/X.509 | Có thể chuyển sang PEM để xem/cấu hình |
| **PKCS#12** (`.p12`, `.pfx`) | Container có thể chứa private key + certificate chain, thường được mã hóa bằng password | `server.ssl.key-store` hoặc JKS-type SSL bundle có type `PKCS12` |
| **JKS** | Keystore truyền thống của Java | `keytool` và cấu hình `server.ssl.*` hoặc SSL bundle |
| **PKCS#8** | Định dạng private key (có thể PEM/DER, encrypted/unencrypted) | Ưu tiên cho private key PEM với Spring Boot |
| **CSR** (`.csr`) | Yêu cầu cấp certificate và public key, **không phải server certificate** | Gửi cho CA, không dùng làm certificate máy chủ |

PEM `-----BEGIN RSA PRIVATE KEY-----` có thể là PKCS#1; `-----BEGIN EC PRIVATE KEY-----` là dạng EC truyền thống. Tài liệu Spring Boot khuyến nghị **PKCS#8** khi có thể, với `-----BEGIN PRIVATE KEY-----` hoặc `-----BEGIN ENCRYPTED PRIVATE KEY-----`. Đối với file private key hiện có ở dạng khác, có thể chuyển theo quy trình kiểm soát an toàn, ví dụ:

~~~bash
# Dành cho môi trường an toàn; lệnh này tạo private key PKCS#8 không mã hóa.
openssl pkcs8 -topk8 -nocrypt -in legacy-server.key -out server-pkcs8.key
~~~

**Cảnh báo:** `-nocrypt` tạo private key không có password. Chỉ dùng khi key được bảo vệ nghiêm bằng file permission, secret volume, giới hạn truy cập, backup/encryption và quy trình rotation phù hợp. Không coi PKCS#8 mặc định là key đã được mã hóa.

## 7. Lab chạy được: Spring Boot HTTPS trên localhost với PKCS12

Ví dụ tối giản gồm một class Java, một file properties và một keystore tự tạo bằng JDK `keytool`. App có endpoint `GET /` trả text chính xác, giúp thử thật sự HTTPS, SAN và trust. **Không yêu cầu CA công khai**, nên client chưa thêm trust sẽ cảnh báo certificate tự ký.

### 7.1. Tạo project Maven

Cây thư mục:

~~~text
tls-demo/
├── pom.xml
├── certs/                       # local-dev.p12, local-dev.crt (không commit)
└── src/main/
    ├── java/com/example/tlsdemo/TlsDemoApplication.java
    └── resources/application.properties
~~~

**`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>tls-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**`src/main/java/com/example/tlsdemo/TlsDemoApplication.java`**:

~~~java
package com.example.tlsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class TlsDemoApplication {
    @GetMapping("/")
    public String hello() {
        return "HTTPS ready\n";
    }

    public static void main(String[] args) {
        SpringApplication.run(TlsDemoApplication.class, args);
    }
}
~~~

Đây là Java chạy trong Spring Boot nên dùng Maven để lấy dependencies và biên dịch, **không** chỉ gọi `javac TlsDemoApplication.java` trừ khi tự cung cấp đầy đủ classpath Spring Framework.

### 7.2. Tạo private key và certificate tự ký cùng SAN

Ở **thư mục gốc project `tls-demo`**, tạo thư mục `certs`. Trong Bash:

~~~bash
mkdir -p certs
keytool -genkeypair \
  -alias local-server \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 7 \
  -storetype PKCS12 \
  -keystore certs/local-dev.p12 \
  -storepass changeit \
  -keypass changeit \
  -dname "CN=localhost, OU=Training, O=Example, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" \
  -ext "EKU=serverAuth"
~~~

Trên PowerShell, có thể viết toàn bộ lệnh `keytool` trên **một dòng** (hoặc dùng backtick continuation theo cú pháp PowerShell, không copy dấu `\` của Bash như ký tự continuation). Lệnh tạo một `PrivateKeyEntry` có RSA private key và certificate tự ký hiệu lực 7 ngày, với SAN cho **localhost** và **127.0.0.1**. Password `changeit` chỉ là **giá trị demo**, không dùng cho production và không commit keystore.

Xuất certificate **công khai** ra PEM để cho `curl` tin certificate cụ thể trong lab:

~~~bash
keytool -exportcert -rfc \
  -alias local-server \
  -keystore certs/local-dev.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -file certs/local-dev.crt
~~~

Quan trọng: file `local-dev.crt` **chỉ chứa certificate**, không chứa private key. `local-dev.p12` có private key **phải** được bảo vệ. Chỉ xuất certificate ra file public để cấp trust trong môi trường test.

Kiểm tra keystore:

~~~bash
keytool -list -v \
  -keystore certs/local-dev.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -alias local-server
~~~

Trong đầu ra, tìm `Entry type: PrivateKeyEntry`, `Certificate chain length: 1` (self-signed demo), `SubjectAlternativeName` chứa `localhost`/`127.0.0.1` và hạn dùng. Không kỳ vọng chain 1 được browser tin: chứng thư tự ký chưa nằm trong public root stores.

### 7.3. Cấu hình HTTPS với server.ssl.* (PKCS12)

File **`src/main/resources/application.properties`**:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:./certs/local-dev.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=local-server

# Optional: bật HTTP/2 khi embedded web server/runtime hỗ trợ.
server.http2.enabled=true
~~~

`file:./certs/local-dev.p12` được phân giải tương đối với **working directory** của tiến trình, không phải thư mục Java source; chạy từ root project khi thử. Khi deploy bằng JAR/Docker, có thể dùng đường dẫn tuyệt đối `file:/etc/tls/server.p12` do container volume cung cấp.

**Không hard-code keystore password trong `application.properties`**. Đặt biến môi trường để Spring đọc `${TLS_KEYSTORE_PASSWORD}`. Ở Bash (chỉ lab local):

~~~bash
TLS_KEYSTORE_PASSWORD=changeit mvn spring-boot:run
~~~

Ở PowerShell:

~~~powershell
$env:TLS_KEYSTORE_PASSWORD = "changeit"
mvn spring-boot:run
~~~

Biến môi trường là ví dụ đơn giản, **không** thay thế secret manager của production. Đừng in password vào log, đừng commit shell history chứa secret thật, và giới hạn người đọc secret trong runtime.

Khi có `server.ssl.key-store` và SSL config hợp lệ, Spring Boot mở HTTPS tại **8443**. App không đồng thời tạo một HTTP connector 8080 chỉ vì trước đây mặc định 8080; muốn vừa HTTP vừa HTTPS riêng trên embedded server thường cần thêm cấu hình programmatic hoặc dùng proxy/ingress.

### 7.4. Chạy kiểm thử đúng về trust

Trong terminal khác:

~~~bash
# Chỉ để xem lỗi expected của self-signed certificate chưa được tin.
curl -v https://localhost:8443/

# Cho curl tin certificate cụ thể của lab; vẫn kiểm tra hostname.
curl --cacert certs/local-dev.crt -sS https://localhost:8443/
~~~

**Expected stdout của dòng thứ hai (response body):**

~~~text
HTTPS ready
~~~

Body có newline ở cuối vì Java method trả `"HTTPS ready\n"`. Dòng `curl -v` đầu thường thất bại với lỗi trust/self-signed certificate — điều này **đúng và mong đợi**, không phải lỗi Spring Boot. Sau khi cung cấp `--cacert`, `curl` dùng file chứng thư như trust anchor cho lab; điều này chỉ tin certificate cụ thể, **không tự đưa nó vào trust store của mọi trình duyệt/JVM**.

Có thể test truy cập qua `127.0.0.1` khi SAN đã có `IP:127.0.0.1`:

~~~bash
curl --cacert certs/local-dev.crt -sS https://127.0.0.1:8443/
~~~

Không sử dụng `-k`/`--insecure` làm cách “sửa SSL” ở production: nó tắt xác thực certificate/hostname và che dấu lỗi thực. Nếu dùng tạm để phân biệt routing với trust trong lab, phải ghi rõ chỉ phục vụ chẩn đoán cục bộ.

**Lưu ý khi kiểm thử HTTP/2:** Nếu `curl` được biên dịch có HTTP/2, có thể gọi:

~~~bash
curl --http2 --cacert certs/local-dev.crt -v https://localhost:8443/
~~~

Quan sát ALPN, HTTP version trong output. Kết quả `h2` phụ thuộc runtime/cấu hình thực tế; nếu chỉ `http/1.1`, HTTPS vẫn có thể hoạt động đúng. **HTTP/2 là lựa chọn giao thức HTTP, không phải chứng minh chain đã tin cậy**.

## 8. Cấu hình PEM và SSL bundle trong Spring Boot

Spring Boot 3.5 hỗ trợ nhiều cách cung cấp TLS key material. **Chọn một kiểu cấu hình cho cùng connector**; tránh trộn lẫn các nguồn certificate/key khiến không biết material nào được dùng.

### 8.1. PEM trực tiếp qua server.ssl.*

Nếu có certificate chain và private key ở PEM:

~~~properties
server.port=8443
server.ssl.certificate=file:/etc/tls/fullchain.pem
server.ssl.certificate-private-key=file:/etc/tls/privkey.pem
server.http2.enabled=true
~~~

Đây là **phương án thay thế** PKCS12 ở phần 7, không dùng đồng thời với `server.ssl.key-store` trên cùng connector. `fullchain.pem` chứa leaf và các intermediates theo đúng thứ tự; `privkey.pem` phải là private key tương ứng với leaf, tốt nhất ở PKCS#8. Permission của file chứa private key phải đủ chặt.

### 8.2. SSL bundle với PEM (cách cấu hình có tên, dễ tái sử dụng)

~~~properties
server.port=8443

spring.ssl.bundle.pem.web.keystore.certificate=file:/etc/tls/fullchain.pem
spring.ssl.bundle.pem.web.keystore.private-key=file:/etc/tls/privkey.pem

server.ssl.bundle=web
server.http2.enabled=true
~~~

Một **SSL bundle** gom certificate/key/trust/options thành một nhóm có tên. `server.ssl.bundle=web` chỉ định web server dùng bundle đó. Các kết nối outgoing như HTTP client, database cũng có thể được cấu hình sử dụng bundle riêng khi integration hỗ trợ; **bundle cho server không mặc nhiên thay truststore của mọi client outbound**.

**Quan trọng:** `server.ssl.bundle` **không được kết hợp** với các discrete keystore/PEM options `server.ssl.key-store`, `server.ssl.certificate`, v.v. Các thuộc tính `server.ssl.ciphers`, `server.ssl.enabled-protocols` và `server.ssl.protocol` bị bỏ qua khi dùng bundle; các tùy chọn TLS đó phải đặt vào `spring.ssl.bundle.<type>.<name>.options` theo documentation tương ứng.

### 8.3. SSL bundle với PKCS12

Nếu cert/key đã ở PKCS12:

~~~properties
server.port=8443

spring.ssl.bundle.jks.web.keystore.location=file:/etc/tls/server.p12
spring.ssl.bundle.jks.web.keystore.type=PKCS12
spring.ssl.bundle.jks.web.keystore.password=${TLS_KEYSTORE_PASSWORD}
spring.ssl.bundle.jks.web.key.alias=server

server.ssl.bundle=web
~~~

Nhóm property `jks` hỗ trợ vật liệu keystore loại **JKS hoặc PKCS12**, không có nghĩa phải chuyển PKCS12 về định dạng JKS. Alias `server` phải đúng với alias đang chứa **PrivateKeyEntry** trong `server.p12` (xem bằng `keytool -list`).

### 8.4. Reload certificate đã thay đổi trên disk

Với Spring Boot tương thích và PEM bundle, có thể bật:

~~~properties
spring.ssl.bundle.pem.web.reload-on-update=true
spring.ssl.bundle.pem.web.keystore.certificate=file:/etc/tls/fullchain.pem
spring.ssl.bundle.pem.web.keystore.private-key=file:/etc/tls/privkey.pem
server.ssl.bundle=web
~~~

Spring Boot có watcher phát hiện thay đổi và reload bundle; **consumer phải hỗ trợ reload**, ví dụ các web server **Tomcat** và **Netty** được tài liệu Spring Boot liệt kê. Không suy ra mọi embedded container, mọi kết nối đang mở hay mọi custom SSLContext tự động nhận certificate mới. Việc reload **không tạo/renew certificate**: Certbot/ACME controller/CA và quy trình vận hành bên ngoài vẫn chịu trách nhiệm cấp mới và cập nhật file.

Khi tự động rotation, dùng cách thay file đủ an toàn (ví dụ atomic update hoặc quy trình phối hợp key/cert) để watcher không bắt được **certificate mới + private key cũ** giữa chừng. Theo dõi error log, handshake sau reload và ngày hết hạn. Với deployment nhiều instances, phải bảo đảm tất cả nhận đúng phiên bản tương ứng.

## 9. Certificate chain cho production: leaf, intermediate và root

Giả sử tổ chức nhận được:
- `leaf.pem`: certificate đã cấp cho `api.example.com`;
- `intermediate.pem`: certificate(s) trung gian từ CA;
- `root.pem`: root CA **công khai**, chỉ dùng test path validation theo trust policy;
- `privkey.pem`: private key được tạo và giữ an toàn từ trước.

### 9.1. Ghép fullchain đúng thứ tự

Trong Bash:

~~~bash
cat leaf.pem intermediate.pem > fullchain.pem
~~~

Nếu nhiều intermediates, thêm chúng theo thứ tự từ issuer gần leaf nhất lên root. **Không nối private key vào fullchain**. Root thường không cần gửi. Trên Windows, tránh nối file PEM bằng thao tác làm thay đổi encoding thành UTF-16 hoặc thêm ký tự lạ; dùng công cụ bảo toàn bytes.

### 9.2. Kiểm tra chain và hostname

~~~bash
openssl verify \
  -purpose sslserver \
  -verify_hostname api.example.com \
  -CAfile root.pem \
  -untrusted intermediate.pem \
  leaf.pem
~~~

Khi CA root được bạn đặt tin trong lệnh và chain/purpose/hostname hợp lệ, kết quả điển hình là:

~~~text
leaf.pem: OK
~~~

**`openssl verify ... -CAfile root.pem` không chứng minh root đó đã được tin bởi Chrome, Java hoặc mọi máy client**. Nó chỉ kiểm tra dưới **trust root bạn vừa chỉ định**. Trên production, phải kiểm tra chain với hệ thống trust anchors thật của các clients mục tiêu.

Inspect certificate:

~~~bash
openssl x509 -in leaf.pem -noout -subject -issuer -dates -serial
openssl x509 -in leaf.pem -noout -ext subjectAltName
openssl x509 -in intermediate.pem -noout -text
~~~

Đọc `Basic Constraints: CA:TRUE` ở intermediate, SAN của leaf, thời gian và thuật toán. Việc certificate hết hạn có thể làm client từ chối dù Spring Boot process vẫn đang chạy bình thường.

### 9.3. Kiểm tra private key có khớp leaf certificate

Một phép kiểm tra an toàn là so **SHA-256 của public key ở dạng DER** trích từ hai nguồn:

~~~bash
# Public key được ghi trong leaf certificate:
openssl x509 -in leaf.pem -pubkey -noout \
  | openssl pkey -pubin -outform DER \
  | openssl dgst -sha256

# Public key được suy ra từ private key:
openssl pkey -in privkey.pem -pubout -outform DER \
  | openssl dgst -sha256
~~~

Nếu hai digest giống nhau, public/private key thuộc cùng cặp (theo phương pháp biểu diễn công khai dùng để so sánh). **Không** cần xuất hoặc in nội dung private key ra terminal/log để kiểm tra. Nếu private key mã hóa, OpenSSL có thể yêu cầu passphrase; quản lý an toàn input.

### 9.4. Đóng gói thành PKCS12 khi cần

Nếu Spring Boot cần PKCS12 thay vì PEM:

~~~bash
openssl pkcs12 -export \
  -inkey privkey.pem \
  -in leaf.pem \
  -certfile intermediate.pem \
  -name server \
  -out server.p12
~~~

OpenSSL sẽ hỏi password bảo vệ file xuất. Kiểm tra:

~~~bash
keytool -list -v -storetype PKCS12 -keystore server.p12
~~~

Alias `server` cần có **PrivateKeyEntry** và certificate chain (thường length 2 hoặc nhiều hơn theo intermediates). Đừng import mỗi leaf certificate như `trustedCertEntry` rồi mong embedded server có private key để chứng minh danh tính.

**Không đưa root CA private key vào server keystore.** Root public certificate có thể để client tin cậy qua truststore; private key root phải được bảo vệ riêng theo chính sách CA.

## 10. Sử dụng OpenSSL để kiểm tra endpoint thực tế

### 10.1. Xem server đang gửi certificate nào

~~~bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -showcerts \
  -verify_return_error < /dev/null
~~~

Quan sát:
- Chain máy chủ gửi (thường leaf, intermediate).
- `subject`, `issuer`, thời hạn và SAN của leaf.
- Kết quả xác minh theo trust store mà OpenSSL đang dùng.
- Protocol/cipher negotiated.

`-servername` cung cấp **SNI**, rất quan trọng khi shared IP có nhiều virtual hosts. Nếu bỏ `-servername`, server có thể trả **default certificate của domain khác**, gây hiểu nhầm “trên server cài sai cert”. Chạy `s_client` một mình không thay toàn bộ logic hostname validation của trình duyệt; khi cần kiểm tra hostname ở CLI, dùng:

~~~bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -verify_hostname api.example.com \
  -verify_return_error < /dev/null
~~~

Tùy OpenSSL version, output và exit code có thể khác; kiểm tra cụ thể `Verify return code` và error, không kết luận chỉ từ dòng `CONNECTED` (nó mới cho biết mở được TCP).

### 10.2. Kiểm tra bằng curl

~~~bash
curl -v https://api.example.com/health
curl --http2 -v https://api.example.com/health
~~~

Lệnh `curl --http2` chỉ hoạt động khi build curl có hỗ trợ HTTP/2, và việc thương lượng thành công còn phụ thuộc server/proxy. Không thêm `-k` để “bắt chạy”: nếu TLS verification lỗi, nên sửa SAN, chain, CA trust hoặc system time.

Với private CA đã được quản lý và có file root public:

~~~bash
curl --cacert root.pem -v https://api.internal.example/health
~~~

`--cacert` làm curl tin CA được chỉ định **cho request đó**. Phải kiểm tra hostname phù hợp SAN; không ép resolve tên sai bằng IP URL khi cert chỉ có DNS SAN.

### 10.3. Phân biệt root/intermediate và local trust

Tình huống A: server gửi leaf nhưng **quên intermediate**. Client không có bản intermediate sẵn có thể lỗi `unable to get local issuer certificate` hoặc `PKIX path building failed`. Giải pháp chính là cài **fullchain** đúng ở server; không nên bắt tất cả clients tự import intermediate.

Tình huống B: server gửi đầy đủ leaf + intermediate nhưng root của private CA **không có trong trust store client**. Phải quản lý việc cấp/ủy thác trust root cho clients được phép, không sửa chain bằng cách nối thêm một root lạ rồi cho rằng trình duyệt sẽ tự tin.

Tình huống C: leaf cert đúng chain nhưng hostname sai. Thay certificate với **SAN đúng**, không nhập root CA khác để bỏ qua hostname validation.

## 11. SNI và nhiều domain trên cùng cổng HTTPS

Trên một load balancer hoặc embedded server có thể phục vụ nhiều hostname dùng chung IP:443. Client gửi `server_name` trong TLS ClientHello để endpoint chọn certificate phù hợp. Mỗi certificate vẫn phải khớp SAN của domain tương ứng.

Spring Boot 3.5 có hỗ trợ mapping **SSL bundles theo SNI** ở các embedded servers tương thích. Ví dụ các bundle `web`, `web-alt` đã được khai báo:

~~~properties
server.port=8443
server.ssl.bundle=web

server.ssl.server-name-bundles[0].server-name=alt.example.com
server.ssl.server-name-bundles[0].bundle=web-alt
~~~

Bundle `web` là mặc định; `web-alt` cho `alt.example.com`. Tính hỗ trợ SNI có khác biệt giữa **Tomcat, Netty, Undertow và Jetty**; theo tài liệu Spring Boot 3.5, cách cấu hình explicit server-name bundles áp dụng cho Tomcat/Netty/Undertow; Jetty có cơ chế SNI tự chọn khi có nhiều certificates. Cần test đúng embedded server và Java version.

**Chú ý quan trọng:** SNI xảy ra **trước HTTP request path**. Không thể chọn certificate dựa vào `/api/v1` hay controller khi TLS handshake còn chưa hoàn tất. SNI hostname và HTTP Host nên được kiểm tra phù hợp; một reverse proxy có thể route dựa trên host nhưng phải bảo vệ trước các Host header không được phép.

## 12. TLS và HTTP/2: có liên quan nhưng không phải một

HTTP/2 là phiên bản protocol **ở tầng HTTP**, TLS ở tầng bảo vệ transport. Spring Boot có property:

~~~properties
server.http2.enabled=true
~~~

Nếu server dùng TLS, client/server có thể thương lượng HTTP/2 over TLS (ALPN protocol **`h2`**) khi cả hai hỗ trợ. Nếu không dùng TLS trong một số cấu hình/stack, Spring Boot có thể hỗ trợ **h2c** (HTTP/2 cleartext) cho backend hoặc kết nối nội bộ qua proxy. Trình duyệt web hiện đại thường dùng HTTPS cho HTTP/2 public.

So sánh:

| Tình huống | Client ↔ điểm TLS | Điểm TLS ↔ Spring Boot | Điều quan sát |
| --- | --- | --- | --- |
| Spring Boot tự terminate TLS | `https://app.example.com` → Spring Boot | Không có proxy terminator | Cert/key nằm trong JVM/embedded server; ALPN có thể chọn h2 |
| Proxy terminate TLS | `https://app.example.com` → Nginx/Ingress/LB | Proxy → Boot có thể HTTP/1.1/h2c hoặc TLS mới | Cert public nằm ở proxy; Boot không nhất thiết cần private key public-domain |
| End-to-end/re-encryption | TLS client → proxy | TLS proxy → Boot (một TLS hop khác) | Hai handshake, hai bộ cert/trust có thể khác |
| TLS 1.3 thành công nhưng HTTP/1.1 | TLS vẫn đúng | Bất kỳ | Server/client không chọn h2 hoặc h2 bị tắt, không phải certificate lỗi |

Nếu TLS termination ở proxy, `server.http2.enabled=true` tại Spring Boot **không tự buộc** browser dùng HTTP/2; browser thương lượng ALPN với **proxy**. Cần cấu hình proxy tương ứng. Khi proxy chuyển `X-Forwarded-Proto`/`Forwarded`, Spring Boot phải được cấu hình trust và parse forwarded headers **từ proxy tin cậy**, tránh cho client bên ngoài giả mạo scheme/host qua header.

**Redirect HTTPS và HSTS:** Với website public, cân nhắc redirect HTTP → HTTPS và `Strict-Transport-Security` phù hợp. Chỉ bật HSTS (đặc biệt `includeSubDomains` hoặc preload) khi toàn bộ domain/subdomains đáp ứng HTTPS bền vững; thiết lập sai có thể làm môi trường thử nghiệm khó truy cập.

## 13. Server authentication khác mutual TLS (mTLS)

**TLS server authentication** phổ biến: server trình certificate, client kiểm tra server; client xác thực người dùng ở tầng ứng dụng (cookie, OAuth, token...) nếu cần.

**mTLS (mutual TLS):** thêm bước **server yêu cầu và kiểm tra client certificate**. Hai phía đều có key material; server cần truststore/CA policy để xác thực certificate client.

~~~text
TLS một chiều:
  Client ── kiểm tra server certificate/chain/SAN ─► Server
  Server có private key; client không nhất thiết có client certificate.

mTLS:
  Client ⇄ Server
  Client kiểm tra server certificate.
  Server kiểm tra client certificate/chain/purpose/policy.
  Client chứng minh giữ client private key.
~~~

Trong Spring Boot cấu hình server mTLS có các property như:

~~~properties
server.ssl.client-auth=need
server.ssl.trust-store=file:/etc/tls/client-ca-truststore.p12
server.ssl.trust-store-type=PKCS12
server.ssl.trust-store-password=${CLIENT_TRUSTSTORE_PASSWORD}
~~~

**Đây là mảnh cấu hình minh họa, không phải thay thế server certificate config:** vẫn cần keystore/SSL bundle của server. `need` yêu cầu client certificate (không có/không hợp lệ thì handshake thường thất bại); `want` yêu cầu tùy chọn, tùy chính sách xác thực. Truststore ở đây dành cho **xác minh client cert**, không phải chứa server private key.

Trong mô hình mTLS ở ingress/proxy, chính **proxy** có thể xác thực client certificate rồi truyền danh tính được xác minh đến Spring Boot. App không được tin header như `X-Client-Cert` từ client công khai nếu header có thể bị giả mạo; chỉ nhận từ proxy được tin, qua đường truyền bảo vệ và cấu hình strip/overwrite header.

mTLS xác thực một danh tính máy/ứng dụng hoặc người sở hữu certificate; **quyền thực hiện nghiệp vụ** vẫn cần authorization. Không biến “có certificate hợp lệ” thành quyền admin vô hạn.

## 14. Quy trình vận hành chứng thư và private key an toàn

### 14.1. Tạo, cấp, triển khai, xoay vòng

Quy trình production nên được thiết kế như một vòng đời:

1. **Xác định ownership** của domain, hostname, TLS termination point, môi trường và người chịu trách nhiệm.
2. **Sinh key pair** bằng công cụ/HSM/KMS phù hợp; hạn chế việc private key rời khỏi nơi bảo vệ.
3. **Tạo CSR** chứa public key và SAN cần cấp; CA xác minh domain/policy và ký certificate.
4. **Nhận leaf + intermediates**, xác minh SAN, Key Usage/EKU, key match, validity và chain đến CA được clients tin.
5. **Triển khai** cert/key ở đúng TLS terminator; bảo vệ private key và passwords, cấu hình file permissions/secrets volume.
6. **Kiểm tra thật qua hostname** bằng curl/OpenSSL/browser/JVM client, bao gồm clients có truststores khác nhau.
7. **Giám sát ngày hết hạn**, lỗi TLS handshake, certificate chain được trình bày, HTTP/2 ALPN nếu sử dụng.
8. **Renew/rotate trước hạn** bằng ACME/CA workflow; đảm bảo cert mới khớp key mới (nếu xoay key), reload/rollout từng instance an toàn.
9. Khi nghi ngờ **private key bị lộ**, phát hành key pair/cert mới, thu hồi cert cũ khi phù hợp, loại key cũ khỏi nơi lưu và điều tra phạm vi ảnh hưởng.

Spring Boot không phải ACME client tự sinh/renew cert bằng việc bật SSL. Ví dụ Let's Encrypt/Certbot thường cung cấp `fullchain.pem` và `privkey.pem` rồi công cụ ngoài chịu trách nhiệm renew; Boot có thể reload PEM bundle khi file thay đổi trên compatible server.

### 14.2. Tránh rò rỉ private key

- Không lưu private key/password thật vào Git, Docker image public, artifact phát hành hoặc log.
- Giới hạn OS file permission/ACL chỉ cho process cần đọc; mount secret volume read-only khi khả thi.
- Tránh gửi private key vào hệ thống chat/ticket hoặc pipeline stdout; không in nội dung PEM private key trong log debug.
- Mã hóa backup và quản lý quyền/rotation; không phát tán keystore password cho nhiều người dùng chung.
- Không dùng cùng private key production trên laptop development.
- Không đưa root/intermediate CA private key vào web server. Web server chỉ cần **private key leaf** của chính nó.

### 14.3. Cấu hình TLS version và cipher suites

Trên Java 17 với embedded server/provider phù hợp, nên ưu tiên **TLS 1.3** và khi cần tương thích dùng **TLS 1.2** theo chính sách tổ chức. Không bật TLS 1.0/1.1/SSLv3 cho dịch vụ mới. Chọn cipher suites theo JDK, TLS provider, client population và security policy; đừng copy một danh sách cipher quá hẹp rồi làm tất cả clients thất bại handshake.

Ví dụ khi **không dùng SSL bundle**:

~~~properties
server.ssl.enabled-protocols=TLSv1.3,TLSv1.2
~~~

Nếu **dùng `server.ssl.bundle`**, tùy chọn về protocols/ciphers phải nằm dưới `spring.ssl.bundle.<type>.<name>.options`; `server.ssl.enabled-protocols` không phải nơi điều khiển bundle. Đừng đoán client đang dùng TLS 1.3 chỉ từ properties; dùng `openssl s_client` hoặc TLS metrics để kiểm tra thực tế.

## 15. Sự cố thường gặp và bảng chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý đúng |
| --- | --- | --- |
| Browser báo `CERT_AUTHORITY_INVALID` hoặc OpenSSL `self-signed certificate` | Root không được tin, certificate tự ký local | Với local lab dùng `--cacert`; production dùng CA tin cậy/managed internal CA |
| `PKIX path building failed` / `unable to get local issuer certificate` | Thiếu intermediate hoặc client không tin root | Kiểm tra `-showcerts`, fullchain leaf→intermediate và truststore client |
| `certificate verify failed: hostname mismatch` | SAN không khớp tên truy cập | Cấp certificate có DNS/IP SAN đúng; dùng hostname đúng |
| `certificate has expired` | Quá `Not After` | Renew, rollout và kiểm tra mọi replicas |
| `certificate is not yet valid` | `Not Before` ở tương lai hoặc đồng hồ lệch | Kiểm tra thời gian/đồng bộ NTP, certificate validity |
| Spring không start, `keystore password was incorrect` | Password PKCS12/JKS sai | Kiểm tra secret mapping, `keytool -list`, không in secret |
| `Cannot recover key` / alias không tồn tại | Alias hoặc key password sai; chỉ có trustedCertEntry | Kiểm tra `PrivateKeyEntry`, alias và password |
| `Private key does not match certificate` | Cert mới + key cũ, hoặc PEM sai file | So SHA-256 public key từ leaf/private key; triển khai cặp khớp |
| Server gửi chứng thư của domain khác | SNI thiếu hoặc default bundle chọn sai | `openssl s_client -servername ...`, xem SNI routing ở terminator |
| `curl: (35) wrong version number` | Dùng HTTPS tới cổng HTTP hoặc proxy route sai | Kiểm tra port/scheme và TLS termination |
| Java client lỗi nhưng browser chạy | Truststore JVM khác browser/OS; proxy/chain policy | Kiểm tra JVM `cacerts`/SSL bundles và trust anchors thực |
| TLS handshake thành công nhưng HTTP trả 404 | URL/router/backend không đúng | Debug HTTP routing sau TLS, không thay certificate |
| HTTPS hoạt động nhưng không có HTTP/2 | h2 không enabled/không ALPN hoặc proxy không thương lượng | Kiểm tra `server.http2.enabled` và ALPN ở điểm TLS |
| Thay file PEM mà server vẫn dùng cert cũ | Không bật reload, consumer không hỗ trợ hoặc symlink/rollout chưa đổi | Kiểm tra SSL bundle reload support, deploy và handshake thực |
| mTLS client thất bại trước HTTP | Client cert không có/không tin, server `client-auth=need` | Kiểm tra client key/cert, CA trust, EKU và policy |
| Chỉ một node phục vụ cert cũ | Rolling deployment hoặc secret mount không đồng nhất | So fingerprint/SNI theo từng node, rà soát rotation |
| SSL bundle và direct properties báo lỗi | Dùng đồng thời `server.ssl.bundle` với `server.ssl.key-store`/`certificate` | Chọn một chiến lược cấu hình |
| Kiểm tra chỉ bằng `curl -k` luôn “OK” | Bỏ qua certificate validation | Bỏ `-k`, sửa SAN, issuer chain, root trust và time |

**Tách các lớp khi debug:**
1. **TCP/DNS:** client có kết nối đến đúng IP:port và đúng TLS termination point?
2. **TLS handshake:** SNI, TLS version, certificate/key/chain và validator có đúng?
3. **HTTP/ALPN:** negotiated `h2`/`http/1.1` và request routing có đúng?
4. **Spring Boot app:** server đã bind 8443? Controller, security, reverse proxy forwarded headers?
5. **Deployment:** cert mới đã đến mọi instances? Có cặp key/cert mismatch khi rotate?

Đừng chỉ kiểm tra thời hạn certificate **trong file local**; certificate thật client nhìn thấy có thể đến từ load balancer, một replica cũ hoặc một SNI virtual host khác.

## 16. Thực hành kiểm tra một môi trường staging hoặc production

Checklist theo thứ tự thực tế:

1. Liệt kê domain/SAN cần phục vụ: `api.example.com`, `app.example.com` và (nếu có) endpoint nội bộ bằng IP riêng.
2. Xác định TLS nằm tại load balancer/proxy hay embedded web server Spring Boot.
3. Xem cert live theo **SNI hostname** bằng `openssl s_client -servername ... -showcerts`.
4. Xem leaf SAN, validity, issuer, signature và chain intermediates; xác minh leaf/key match ở nơi được phép truy cập private key.
5. Kiểm tra hostname và trust bằng `curl -v https://...` hoặc `openssl verify -verify_hostname` với đúng trust policy.
6. So trùng `Not After` ở mọi domain/replicas, lên lịch rotate trước hết hạn.
7. Kiểm tra key material không nằm trong image source, logs, Git; password lấy từ secret management.
8. Nếu cần mTLS, kiểm tra client certificate CA/purpose và authorization sau handshake.
9. Nếu bật HTTP/2, nhìn ALPN ở điểm terminate TLS thực tế, không chỉ đọc `server.http2.enabled` trong app.
10. Test restart/reload với cặp cert/key mới trước khi áp dụng auto-renew production; theo dõi handshake failures sau deploy.
11. Xác minh proxy không làm lộ backend HTTP không được bảo vệ trong vùng rủi ro và không tin forwarded headers từ người ngoài.
12. Ghi lại runbook: người vận hành, đường dẫn secret, CA renewal workflow, time-to-expiry alerts, rollback và xử lý key compromise.

## 17. Bài tập tự kiểm tra

1. Certificate có chứa private key không? Client có nhận private key trong TLS handshake không?
2. Leaf certificate do intermediate CA ký, intermediate do root ký. Server thường gửi những certificate nào?
3. Tại sao gửi root certificate kèm handshake không tự làm client tin root đó?
4. Website `https://api.example.com` có leaf SAN chỉ gồm `DNS:app.example.com`. Cho root vào truststore có sửa hostname mismatch không?
5. Truy cập `https://127.0.0.1:8443` với cert SAN chỉ có `DNS:localhost` có hợp lệ không? Muốn dùng IP phải bổ sung gì?
6. `server.ssl.key-store` khác `server.ssl.trust-store` ở nhiệm vụ gì?
7. Khi dùng `server.ssl.bundle=web`, có nên giữ cả `server.ssl.certificate` và `server.ssl.key-store` trên cùng connector?
8. Trong Spring Boot PEM bundle, `keystore.certificate` nên trỏ leaf hay fullchain? `keystore.private-key` chứa gì?
9. Khi private key bị lộ, vì sao chỉ đổi password của `server.p12` không khôi phục an toàn?
10. Tại sao certificate hợp lệ không bảo đảm HTTP/2 đã bật?
11. Với load balancer terminate TLS, cert public phải ở proxy hay nhất thiết ở Spring Boot app?
12. `curl -k` có phù hợp để xác nhận hệ thống HTTPS production an toàn không?
13. Nếu Java client bị `PKIX path building failed` nhưng trình duyệt vẫn truy cập được, cần so sánh truststore nào?
14. Vì sao dùng `CN=localhost` thôi là chưa đủ? Lệnh lab đã thêm extension gì?
15. `mTLS` bổ sung điều gì so với HTTPS một chiều? Có tự cấp quyền truy cập mọi API không?
16. Khi cert renew thành công trên disk nhưng client vẫn nhìn thấy cert cũ, bạn kiểm tra những nơi nào?
17. Làm sao kiểm tra leaf cert và server private key đúng cặp mà không in private key?
18. Vì sao TLS 1.3 dùng private key để chứng minh danh tính chứ không dùng nó làm khóa mã hóa từng HTTP response?

**Gợi ý đáp án:** (1) Không, cert chỉ mang public key/metadata; server giữ private key. (2) Leaf + intermediates, root thường ở truststore client. (3) Trust anchor do client tự chọn. (4) Không, SAN phải khớp `api.example.com`. (5) Không, cần `IP:127.0.0.1` SAN. (6) Keystore server giữ key+chain; truststore giữ các CA được tin khi verify peer. (7) Không trộn direct options với bundle. (8) Fullchain leaf trước intermediates; private key tương ứng leaf. (9) Key đã lộ vẫn dùng được, phải rotate key/cert. (10) HTTP/2 qua ALPN và server/proxy support. (11) Ở điểm thực sự terminate TLS. (12) Không, nó bỏ xác minh cert. (13) JVM `cacerts`/custom truststore so với OS/browser trust. (14) Hostname validation hiện đại theo SAN, dùng `SAN=dns:localhost,ip:127.0.0.1`. (15) Server xác thực client cert, vẫn cần authorization. (16) Reload/rollout, SNI, các replicas, proxy cert cache. (17) So SHA-256 public key DER của leaf và key. (18) TLS 1.3 có ephemeral key exchange và dẫn xuất traffic secrets riêng; leaf private key chứng minh danh tính qua chữ ký.

## 18. Tài liệu chính thức và tiêu chuẩn

- RFC 8446, **TLS 1.3**, `CertificateVerify` và handshake: https://www.rfc-editor.org/rfc/rfc8446.html
- RFC 5280, **Internet X.509 PKI Certificate and CRL Profile**, chain validation và extensions: https://www.rfc-editor.org/rfc/rfc5280.html
- RFC 6125 và RFC 9525, **Service Identity in TLS** (DNS SAN, hostname verification): https://www.rfc-editor.org/rfc/rfc9525.html
- Spring Boot 3.5, **Configure SSL / PEM / PKCS12 / SSL Bundles / SNI / HTTP/2**: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5, **SSL bundles and reload**: https://docs.spring.io/spring-boot/3.5/reference/features/ssl.html
- Spring Boot 3.5, **Common Application Properties**: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Oracle Java 17, **keytool Command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- Oracle Java 17, **Java Secure Socket Extension (JSSE) Reference Guide**: https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html
- OpenSSL, **s_client**: https://docs.openssl.org/3.0/man1/openssl-s_client/
- OpenSSL, **verify**: https://docs.openssl.org/3.0/man1/openssl-verification-options/

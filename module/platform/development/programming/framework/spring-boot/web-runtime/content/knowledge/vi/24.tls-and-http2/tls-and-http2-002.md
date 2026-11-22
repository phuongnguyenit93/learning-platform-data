# Cấu hình `server.ssl.*` với keystore JKS hoặc PKCS12 trong Spring Boot

## 1. Mục tiêu: bật HTTPS đúng cách, không nhầm TLS với HTTP/2

Một Spring Boot web application có thể cung cấp HTTP qua cổng 8080 hoặc HTTPS qua cổng 8443/443. Khi bật HTTPS trực tiếp trên **embedded web server** (Tomcat mặc định của Spring MVC, hoặc một server khác được hỗ trợ), server phải có **chứng chỉ X.509 và private key tương ứng**. Spring Boot có nhóm thuộc tính `server.ssl.*` để chọn key material, giao thức và tùy chọn xác thực client; Java keystore định dạng **JKS** hoặc **PKCS12** là hai cách lưu key material phổ biến.

Trong bài này cần trả lời chính xác:

1. Keystore chứa gì? Khác truststore thế nào?
2. Tạo JKS và PKCS12 bằng `keytool` với alias và Subject Alternative Name (SAN) ra sao?
3. Cấu hình các thuộc tính `server.ssl.key-store`, `key-store-type`, `key-store-password`, `key-alias`, `key-password` ra sao để Spring Boot nạp được private key?
4. Cách kiểm thử HTTPS, hostname, chuỗi chứng chỉ và HTTP/2/ALPN?
5. Làm sao xử lý khác biệt dev/prod, secret, reverse proxy, mTLS và lỗi khởi động?

Phạm vi: **Spring Boot 3.3.x, Java 17+**, minh họa chạy bằng Spring Boot 3.3.13/Java 21 với embedded Tomcat. Các lệnh shell tập trung vào Linux/macOS; Windows có cách khai báo biến môi trường tương ứng. Đừng dùng chứng chỉ self-signed của môi trường học tập làm chứng chỉ công khai cho production.

**Phân biệt hai cấu hình quan trọng:**

```properties
# HTTPS/TLS: server phải trình bày certificate + private key.
server.ssl.enabled=true

# HTTP/2: tùy chọn giao thức HTTP (bật riêng, không tự sinh certificate).
server.http2.enabled=true
```

Trong Spring Boot 3.3, `server.http2.enabled=true` với SSL hỗ trợ HTTP/2 over TLS (`h2`); khi SSL không bật, server có thể hỗ trợ cleartext HTTP/2 (`h2c`) tùy stack. **Bật HTTP/2 không thay thế TLS**, và bật TLS cũng không mặc định bảo đảm mọi client sẽ dùng HTTP/2.

## 2. Khái niệm nền: TLS certificate, private key, keystore và truststore

Khi một browser kết nối tới `https://api.example.com`, server trình bày **certificate chain** (leaf certificate và các intermediate certificates cần thiết). Browser kiểm tra tên miền, thời hạn, đường dẫn tin cậy tới một Certificate Authority (CA), trạng thái và các yếu tố khác theo policy của browser. Server chứng minh đang nắm **private key** tương ứng thông qua TLS handshake.

| Khái niệm | Nội dung | Trách nhiệm |
| --- | --- | --- |
| Private key | Khóa bí mật của server; không được chia sẻ cho client | Server chứng minh sở hữu danh tính TLS |
| Leaf certificate | Chứng chỉ X.509 gắn public key với domain/IP (qua SAN) | Client kiểm tra danh tính endpoint |
| Intermediate/root CA certificate | Các chứng chỉ trong chuỗi xác thực | Giúp client xây trust path |
| **Keystore** | Container chứa `PrivateKeyEntry` + certificate chain và có thể các entry khác | Cung cấp **server identity** cho HTTPS |
| **Truststore** | Chứa CA/chứng chỉ được tin cậy, thường là `trustedCertEntry` | Server/client dùng để **xác minh peer** |
| Keystore password | Mật khẩu mở/kiểm tra kho khóa | `server.ssl.key-store-password` |
| Private-key password | Mật khẩu truy cập private-key entry, có thể khác store password | `server.ssl.key-password` |
| Alias | Tên entry của cặp khóa và chain trong keystore | `server.ssl.key-alias` |

**Keystore không đơn giản là một file `.crt` chứa certificate.** Để HTTPS trực tiếp hoạt động, keystore server phải có **private key entry**; chỉ import một CA certificate vào một truststore không đủ để server ký handshake.

Với HTTPS thông thường, server cần keystore có private key và certificate chain; **không cần khai báo `server.ssl.trust-store` chỉ để client/browser tin server**. Sự tin cậy của browser dựa trên trust store và policy **ở phía browser**, không phải truststore server. Truststore phía server thường dùng khi xác thực chứng chỉ **client** trong mutual TLS (mTLS).

```text
Browser (trust anchors / CA policy)
     |
     |  GET https://localhost:8443/hello
     |  TLS handshake: server certificate + proof of private key
     v
Embedded Tomcat (server.ssl.* -> keystore)
     |
     +-- PrivateKeyEntry: alias web-local
           +-- private key
           +-- leaf certificate
           +-- certificate chain
```

Một self-signed certificate có thể dùng để thử local nhưng browser không tự tin nó: chưa được CA tin cậy. `curl -k` bỏ qua xác minh server certificate **chỉ nên dùng khi debug local**, không phải bản cấu hình release.

## 3. JKS và PKCS12: giống nhau ở vai trò, khác nhau về định dạng

**JKS (Java KeyStore)** là định dạng keystore truyền thống của Java. **PKCS12 (`.p12`, `.pfx`)** là định dạng chuẩn trao đổi key/certificate phổ biến giữa Java, OpenSSL, hệ thống vận hành và các công cụ certificate. Java hiện đại dùng PKCS12 làm định dạng keystore mặc định của `keytool`/`KeyStore` trong nhiều trường hợp, nhưng **không nên dựa vào tên file để suy ra format**.

| Tiêu chí | JKS | PKCS12 |
| --- | --- | --- |
| Đuôi file thường dùng | `.jks` | `.p12`, `.pfx` |
| Tên cấu hình Spring Boot | `server.ssl.key-store-type=JKS` | `server.ssl.key-store-type=PKCS12` |
| Có thể chứa private key + cert chain | Có | Có |
| Dùng với Java `keytool` | Có | Có |
| Khả năng tương tác ngoài Java | Thường thấp hơn PKCS12 | Phổ biến hơn |
| Khi nên chọn | Hệ thống Java cũ/đã chuẩn hóa JKS | Lựa chọn linh hoạt cho dự án mới |

Không có quy tắc “JKS luôn an toàn hơn PKCS12” hoặc ngược lại chỉ dựa trên đuôi file. Bảo vệ thực tế đến từ thuật toán khóa, mật khẩu, quyền file, chứng chỉ hợp lệ, cấu hình TLS, quản trị bí mật và quy trình cập nhật.

Keystore có thể chứa nhiều aliases, nhưng trong ứng dụng web thông thường nên **chỉ định alias server** rõ ràng nếu có khả năng có nhiều key entries. Nếu `key-alias` sai hoặc entry không có private key, server có thể không khởi động hoặc không trình bày chứng chỉ mong đợi.

## 4. Sinh keystore PKCS12 cho HTTPS local bằng `keytool`

Trên JDK 17 hoặc 21, `keytool` có sẵn trong `bin` của JDK. Để kiểm tra:

```bash
java -version
keytool -help
```

Ví dụ tạo **cặp khóa RSA 3072 bit** và **self-signed certificate** có SAN cho cả `localhost` và IP loopback. Chạy tại một thư mục thử nghiệm **ngoài Git repository** hoặc dưới vị trí đã được `.gitignore` bảo vệ; không đưa file chứa private key lên source control.

```bash
keytool -genkeypair \
  -alias web-local \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 365 \
  -storetype PKCS12 \
  -keystore local-keystore.p12 \
  -dname "CN=localhost,OU=Development,O=Example,L=HCM,ST=HCM,C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

`keytool` sẽ yêu cầu password tương tác nếu chưa được chỉ rõ. Với ví dụ PKCS12, sử dụng một password mạnh và dùng cùng password cho private key nếu công cụ yêu cầu/quy ước. **Không ghi mật khẩu vào command line `-storepass ...`** trên máy dùng chung nếu không chấp nhận rủi ro shell history, process arguments hoặc build logs.

Giải thích các tham số:

- `-genkeypair`: tạo cặp public/private key cùng certificate self-signed để thử local.
- `-alias web-local`: tên key entry, sẽ dùng trong `server.ssl.key-alias`.
- `-keyalg RSA`, `-keysize 3072`: ví dụ thuật toán và kích thước khóa; trong hệ thống thật chọn theo policy PKI.
- `-validity 365`: chứng chỉ self-signed có thời hạn 365 ngày, **không tự được CA công khai tin cậy**.
- `-storetype PKCS12`: cố định format, không dựa vào mặc định của JDK.
- `-keystore local-keystore.p12`: file được tạo tại working directory hiện hành.
- `-dname`: Distinguished Name của chủ thể; `CN` không thay thế `SAN`.
- `-ext SAN=...`: đặt Subject Alternative Name tương ứng với host/IP mà client sẽ truy cập.

**SAN rất quan trọng:** Khi client gọi `https://localhost:8443`, certificate cần `DNS:localhost`; khi gọi `https://127.0.0.1:8443`, cần `IP Address:127.0.0.1`. Chỉ có `CN=localhost` có thể không đủ với các client hiện đại.

Kiểm tra alias, entry type, SAN, ngày hết hạn:

```bash
keytool -list -v \
  -keystore local-keystore.p12 \
  -storetype PKCS12 \
  -alias web-local
```

Trong output, xem `Entry type: PrivateKeyEntry`, `Certificate chain length`, `Owner`, `Issuer`, validity và `SubjectAlternativeName`. Đừng chỉ kiểm tra `keytool -list` có in một alias: một `trustedCertEntry` **không có private key** sẽ không dùng làm server identity.

## 5. Sinh JKS và chuyển đổi giữa JKS ↔ PKCS12

Nếu hệ thống đã dùng JKS, có thể tạo tương tự:

```bash
keytool -genkeypair \
  -alias web-local \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 365 \
  -storetype JKS \
  -keystore local-keystore.jks \
  -dname "CN=localhost,OU=Development,O=Example,L=HCM,ST=HCM,C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Ở JKS, công cụ có thể hỏi riêng mật khẩu key entry; để đơn giản khi học, có thể chọn **cùng mật khẩu keystore**. Khi key entry có password khác, phải cấu hình `server.ssl.key-password` đúng với password key. Một số phiên bản JDK khuyến nghị dùng PKCS12 cho keystore mới; JKS vẫn là format được Java hỗ trợ.

Kiểm tra:

```bash
keytool -list -v \
  -keystore local-keystore.jks \
  -storetype JKS \
  -alias web-local
```

Nếu cần chuyển JKS sang PKCS12:

```bash
keytool -importkeystore \
  -srckeystore local-keystore.jks \
  -srcstoretype JKS \
  -destkeystore converted-keystore.p12 \
  -deststoretype PKCS12
```

Lệnh yêu cầu mật khẩu nguồn và đích tương ứng; nếu private-key password khác store password, công cụ có thể cần mật khẩu key nguồn. Không thay file gốc ngay khi chưa kiểm tra đầu ra.

```bash
keytool -list -v \
  -keystore converted-keystore.p12 \
  -storetype PKCS12 \
  -alias web-local
```

Sau conversion, kiểm tra alias, **PrivateKeyEntry**, certificate chain và thử handshake thật; đừng chỉ đổi tên file `.jks` thành `.p12`. Việc đổi đuôi **không chuyển định dạng**. Ứng dụng phải khai `key-store-type` khớp format thực và sử dụng password/alias của file đích.

## 6. Bảng thuộc tính `server.ssl.*` thường dùng trong Spring Boot 3.3

| Property | Chức năng | Lưu ý thực hành |
| --- | --- | --- |
| `server.ssl.enabled` | Bật/tắt TLS trên embedded server connector | Ví dụ đặt `true`; chỉ có `enabled=true` mà thiếu key material sẽ không tạo certificate |
| `server.ssl.key-store` | Spring resource location của keystore | `classpath:tls/keystore.p12` (demo) hoặc `file:/etc/myapp/tls/server.p12` (triển khai) |
| `server.ssl.key-store-type` | Format: `JKS` hoặc `PKCS12` | Khớp format thực; khai tường minh |
| `server.ssl.key-store-password` | Password mở keystore | Lấy từ secret/env; không commit password |
| `server.ssl.key-alias` | Chọn private key entry | Kiểm tra alias bằng `keytool -list -v` |
| `server.ssl.key-password` | Password của private key nếu cần | Có thể khác `key-store-password`, đặc biệt trong JKS |
| `server.ssl.key-store-provider` | Java security provider | Chỉ cần khi có provider đặc biệt |
| `server.ssl.protocol` | Protocol family để tạo TLS/SSL context | Mặc định `TLS`, **không tự ép phiên bản TLSv1.2** |
| `server.ssl.enabled-protocols` | Danh sách phiên bản TLS được phép | Ví dụ `TLSv1.3,TLSv1.2` theo policy và JVM/server |
| `server.ssl.ciphers` | Giới hạn cipher suites | Cần khớp tên suite và khả năng của JVM/container |
| `server.ssl.client-auth` | Kiểm tra chứng chỉ client (`none`, `want`, `need`) | Chỉ bật mTLS nếu thực sự cần |
| `server.ssl.trust-store` | Trust material để xác thực client certificate | Thường chỉ cần khi `client-auth` yêu cầu |
| `server.ssl.trust-store-type` | Format truststore | Ví dụ `PKCS12` |
| `server.ssl.trust-store-password` | Mật khẩu truststore | Lưu bằng secret |
| `server.ssl.bundle` | Tham chiếu tới SSL bundle được cấu hình bằng `spring.ssl.bundle.*` | **Không kết hợp** với các tùy chọn keystore/PEM rời |
| `server.port` | Cổng lắng nghe | Demo `8443`; không phải tên property SSL |
| `server.http2.enabled` | Bật HTTP/2 | Không tự cung cấp certificate/TLS |

Các giá trị hợp lệ phải phù hợp phiên bản Java, container và cách đóng gói đang dùng. Chẳng hạn chỉ định cipher không được JVM hỗ trợ có thể khiến TLS negotiation không có thuật toán chung.

**Tuyệt đối không nhầm:** `server.ssl.key-store-password` không phải mã hóa truyền thông HTTP; nó chỉ bảo vệ keystore at rest / lúc nạp key. TLS sử dụng private key và phiên bắt tay, không gửi store password cho browser.

## 7. Ví dụ `application.properties` chạy HTTPS với PKCS12

Cấu hình này nạp keystore thông qua **resource location** nằm trong biến môi trường, thay vì commit private key hoặc mật khẩu vào Git:

**`src/main/resources/application.properties`:**

```properties
server.port=8443
server.ssl.enabled=true

server.ssl.key-store=${TLS_KEYSTORE_LOCATION}
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=web-local

# Dùng khi private-key password khác store password:
# server.ssl.key-password=${TLS_KEY_PASSWORD}

# Tùy chọn giới hạn các TLS phiên bản phù hợp JVM/policy:
server.ssl.enabled-protocols=TLSv1.3,TLSv1.2

# Tùy chọn độc lập: cho phép HTTP/2 khi client/server hỗ trợ.
server.http2.enabled=true
```

Ví dụ cấu hình environment cho Linux/macOS, nếu đang đứng tại thư mục chứa file `local-keystore.p12`:

```bash
export TLS_KEYSTORE_LOCATION="file:$(pwd)/local-keystore.p12"

# Nhập password mà không hiện trên màn hình:
read -rs TLS_KEYSTORE_PASSWORD
export TLS_KEYSTORE_PASSWORD
printf '\n'
```

`read -rs` là shell builtin trong Bash/zsh. Trên Windows PowerShell, cách khai biến môi trường khác; **không sử dụng nguyên cú pháp Bash**. Trong production, tốt hơn lấy secret từ secret manager/mount đã được bảo vệ thay vì nhập tay.

Một cấu hình `file:` bên ngoài JAR giúp thay keystore theo kế hoạch triển khai mà không cần nhúng private key vào build artifact. Nó vẫn đòi hỏi quyền đọc của account chạy app và **restart/reload theo cơ chế đã xác nhận** sau khi cập nhật certificate; không tự giả định thay bytes file đang chạy sẽ cập nhật TLS context ngay lập tức.

Nếu muốn minh họa keystore **bên trong classpath** cho môi trường development, có thể đặt file tại:

```text
src/main/resources/tls/local-keystore.p12
```

và cấu hình:

```properties
server.ssl.key-store=classpath:tls/local-keystore.p12
```

Nhưng không khuyến nghị đóng gói **production private key** vào JAR hoặc public repository. `classpath:` dùng Spring resource loader; nó không đòi hỏi resource nằm ngoài JAR dưới dạng file hệ thống writable.

## 8. Cấu hình tương đương cho JKS và YAML

Khi sử dụng `local-keystore.jks`, thay các thuộc tính liên quan:

```properties
server.port=8443
server.ssl.enabled=true

server.ssl.key-store=${TLS_KEYSTORE_LOCATION}
server.ssl.key-store-type=JKS
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=web-local

# Chỉ thêm khi private key trong JKS có mật khẩu riêng:
# server.ssl.key-password=${TLS_KEY_PASSWORD}

server.http2.enabled=true
```

Biến `TLS_KEYSTORE_LOCATION` lúc này phải trỏ đến JKS, ví dụ `file:/etc/myapp/tls/local-keystore.jks`. **Không đồng thời giữ `key-store-type=PKCS12` và trỏ vào JKS** rồi dựa vào keystore autodetection của JDK: cấu hình tường minh giúp tránh hành vi phụ thuộc phiên bản/provider.

Cùng cấu hình ở dạng `application.yml`:

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: ${TLS_KEYSTORE_LOCATION}
    key-store-type: JKS
    key-store-password: ${TLS_KEYSTORE_PASSWORD}
    key-alias: web-local
  http2:
    enabled: true
```

Đây là **hai phương án tương đương**, không nên định nghĩa trùng các key với giá trị khác nhau ở cả `.properties` và `.yml` trong cùng config location. Spring Boot có thứ tự ưu tiên configuration sources/profiles/env vars; cần xác nhận effective value khi debug.

Nếu key password **khác** keystore password:

```properties
server.ssl.key-password=${TLS_KEY_PASSWORD}
```

Nếu private key dùng **cùng password**, cấu hình đơn giản thường không cần khai thêm `key-password`. Với lỗi `UnrecoverableKeyException`, luôn kiểm tra cả **store password**, **private-key password** và alias, không chỉ file format.

## 9. Ứng dụng Spring Boot tối thiểu để kiểm thử HTTPS

Ví dụ dùng Gradle, Java 21 và Spring Boot 3.3.13. Các mã bên dưới tạo ứng dụng chạy được khi đã có `gradlew` của dự án, JDK thích hợp, các dependencies được tải và keystore từ mục 4 hoặc 5.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/tls/TlsApplication.java`:**

```java
package com.example.tls;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TlsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TlsApplication.class, args);
    }
}
```

**`src/main/java/com/example/tls/HelloController.java`:**

```java
package com.example.tls;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "secure-ok";
    }
}
```

**`src/main/resources/application.properties`** dùng cấu hình PKCS12 từ mục 7 (hoặc JKS từ mục 8, **không cả hai cùng lúc**). Khi khởi động, Spring Boot binding `server.ssl.*` vào `ServerProperties`, auto-configure embedded server factory và áp dụng TLS cho connector. Bạn không cần tự viết `SSLContext`/`TomcatServletWebServerFactory` cho use case cơ bản.

Trong terminal có `TLS_KEYSTORE_LOCATION`, `TLS_KEYSTORE_PASSWORD` đã được cấu hình:

```bash
./gradlew bootRun
```

Sau khi server sẵn sàng, thử:

```bash
# Chỉ để kiểm tra tự ký trên môi trường development:
curl -k -i https://localhost:8443/hello
```

Body thành công là:

```text
secure-ok
```

Các header, TLS version, status line và ALPN output có thể thay đổi theo client/server; **chỉ body literal `secure-ok` là cố định theo controller**. `curl -k` vô hiệu hóa certificate verification nên không phải cách xác minh production đạt chuẩn.

Nếu chọn JKS thay vì PKCS12, cách kiểm thử HTTP giống nhau: chỉ thay keystore file, type, password và alias tại server. Browser không biết server đọc private key từ JKS hay PKCS12; client chỉ thấy public certificate và kết quả TLS negotiation.

## 10. Kiểm tra TLS thật, không phụ thuộc `curl -k`

### 10.1. Xuất public certificate của keystore test

Với keystore PKCS12 self-signed từ mục 4:

```bash
keytool -exportcert \
  -rfc \
  -alias web-local \
  -keystore local-keystore.p12 \
  -storetype PKCS12 \
  -file local-cert.pem
```

`-exportcert` xuất **certificate công khai**, không xuất private key. Lệnh yêu cầu password nếu cần; tệp `local-cert.pem` vẫn nên được đối chiếu fingerprint nếu sử dụng làm trust anchor.

Sau đó kiểm tra có xác minh certificate và hostname (mục đích local, không phải CA công khai):

```bash
curl --cacert local-cert.pem -i https://localhost:8443/hello
```

Với self-signed leaf certificate, một curl/OpenSSL build phù hợp có thể tin certificate được chỉ định rõ làm local trust anchor. Nếu client có chính sách PKI khác hoặc xác minh chain thất bại, cần xem lý do xác minh và cấu hình trust thích hợp thay vì thêm `-k` cho production.

Trong môi trường production, dùng certificate do CA được client tin cậy cấp cho **đúng hostname** và cài chain hợp lệ; thông thường `curl https://api.example.com/...` chạy thành công mà không thêm `--cacert`. Không bỏ hostname verification hoặc vô hiệu hóa certificate checks để chữa lỗi certificate.

### 10.2. Xem certificate và TLS handshake bằng OpenSSL

```bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -showcerts </dev/null
```

Kiểm tra **subject, issuer, validity, chain, negotiated protocol/cipher** và các thông báo verify. `-servername` gửi SNI khi cần; nó không tự chứng minh hostname verification đã thành công. Muốn OpenSSL xác minh hostname/trust, phải thêm lựa chọn phù hợp như `-verify_hostname localhost` và `-CAfile local-cert.pem` khi đang tin self-signed certificate.

Một lệnh `s_client` kết nối thành công không chứng minh endpoint HTTP trả đúng nội dung, và cũng không chứng minh certificate đã được browser tin cậy.

### 10.3. Tách kiểm tra HTTPS và HTTP

```bash
# HTTPS đã bật trên 8443:
curl -k -i https://localhost:8443/hello

# KHÔNG tự kỳ vọng HTTP trên cùng port 8443:
curl -i http://localhost:8443/hello
```

Request HTTP thuần gửi vào cổng HTTPS không phải request hợp lệ. Không diễn giải lỗi handshake/protocol ở request thứ hai thành lỗi `@GetMapping`.

Theo tài liệu Spring Boot 3.3, cấu hình HTTPS bằng `server.ssl.*` **không đồng thời tạo sẵn HTTP connector trên 8080**. Muốn có cả hai connectors trong embedded server, phải cấu hình ít nhất một connector bằng code hoặc đặt HTTP redirect tại reverse proxy. **Không có auto redirect 8080 → 8443 chỉ bằng cách set `server.ssl.key-store`.**

## 11. Bật HTTP/2 qua TLS (h2) và xác nhận ALPN

HTTP/2 là phiên bản giao thức HTTP; TLS bảo vệ kênh truyền. Để dùng `h2` trực tiếp trong ví dụ này:

```properties
server.ssl.enabled=true
server.http2.enabled=true
```

Trong Spring Boot 3.3 với embedded Tomcat 10.1.x và Java 17+, h2 over TLS được hỗ trợ. Khi browser/curl kết nối, việc chọn `h2` thường diễn ra qua **ALPN (Application-Layer Protocol Negotiation)** trong TLS handshake. Nếu client không hỗ trợ HTTP/2, kết nối có thể được phục vụ qua HTTP/1.1; bật property ở server không buộc mọi client luôn dùng h2.

Kiểm tra phiên bản curl và HTTP/2 support:

```bash
curl -V
```

Nếu trong output có feature HTTP2, dùng:

```bash
curl -k --http2 -v https://localhost:8443/hello
```

Với đúng cấu hình và build client/server hỗ trợ, verbose output cho biết ALPN accepted protocol là `h2`, status line có thể thể hiện `HTTP/2 200`; body là `secure-ok`. **Không suy rằng `curl --http2` thành công nếu binary curl không được build với HTTP/2 support.**

Có thể kiểm tra ALPN ở tầng TLS:

```bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -alpn h2,http/1.1 </dev/null
```

Nếu được chọn, OpenSSL thường in `ALPN protocol: h2`. Nếu không, xem stack server, client, TLS parameters và proxy/terminator; đừng vội thay JKS sang PKCS12 vì keystore format không quyết định HTTP version.

**`h2c` khác `h2`:** Nếu SSL disabled mà HTTP/2 enabled, Spring Boot có thể hỗ trợ h2c trên cleartext TCP, ví dụ phía sau proxy thực hiện TLS termination. Public browser traffic thông thường dùng h2 qua TLS; không xem h2c công khai là HTTPS.

Spring Boot 3.3 hỗ trợ HTTP/2 với nhiều server, nhưng dependency requirements khác nhau: Tomcat 10.1.x và Undertow hỗ trợ h2/h2c theo tài liệu; Jetty có thể cần dependency HTTP/2/ALPN bổ sung; Reactor Netty (WebFlux) hỗ trợ h2/h2c và có tuỳ chọn native libraries để tối ưu. Không sao chép một cấu hình Jetty sang Tomcat mà không kiểm tra stack.

## 12. Bài thực hành Java 17 độc lập: xác minh keystore thực sự chứa private key

`keytool -list` hữu ích, nhưng Java cũng có thể mở keystore và xác minh alias là **key entry**, chứ không chỉ certificate entry. Chương trình sau dùng **chỉ Java 17+**, không phụ thuộc Spring, đọc password từ biến môi trường `KS_PASSWORD` và không in password.

**Tệp `KeyStoreCheck.java`:**

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;

public class KeyStoreCheck {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                    "Usage: java KeyStoreCheck PKCS12|JKS path alias");
            System.exit(2);
        }

        String value = System.getenv("KS_PASSWORD");
        if (value == null || value.isEmpty()) {
            throw new IllegalStateException("KS_PASSWORD is not set");
        }

        char[] password = value.toCharArray();
        try {
            KeyStore store = KeyStore.getInstance(args[0]);
            try (InputStream input =
                         Files.newInputStream(Path.of(args[1]))) {
                store.load(input, password);
            }

            String alias = args[2];
            System.out.println("type=" + store.getType());
            System.out.println("alias=" + alias);
            System.out.println("hasPrivateKey=" + store.isKeyEntry(alias));

            var chain = store.getCertificateChain(alias);
            System.out.println("certificateChainLength="
                    + (chain == null ? 0 : chain.length));
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Biên dịch:

```bash
javac KeyStoreCheck.java
```

Đặt biến môi trường bằng cách nhập password không echo (Bash/zsh):

```bash
read -rs KS_PASSWORD
export KS_PASSWORD
printf '\n'
```

Chạy với keystore PKCS12 mới tạo ở mục 4:

```bash
java KeyStoreCheck PKCS12 local-keystore.p12 web-local
```

**Stdout dự kiến chính xác** khi file chỉ chứa cặp khóa và self-signed cert do lệnh mục 4 tạo, alias nguyên vẹn:

```text
type=PKCS12
alias=web-local
hasPrivateKey=true
certificateChainLength=1
```

Với file JKS được tạo bởi lệnh mục 5:

```bash
java KeyStoreCheck JKS local-keystore.jks web-local
```

Trường `type` sẽ là `JKS`; các dòng còn lại tương tự nếu alias/private-key entry hợp lệ. Nếu chương trình ném `IOException: keystore password was incorrect`, `UnrecoverableKeyException` hoặc exception provider, cần đọc nguyên nhân thực thay vì bỏ xác minh password.

Lưu ý bảo mật: Biến môi trường có thể được thấy bởi các process có quyền trên hệ thống và `String` Java chứa password không được xóa bộ nhớ như `char[]`; ví dụ này chỉ nhằm kiểm tra key entry và hạn chế in secret, không phải hướng dẫn quản lý secret hoàn chỉnh.

## 13. Dùng certificate do CA cấp trong production

Self-signed certificate hữu ích để học TLS nhưng không thích hợp cho website public. Với production, luồng PKI thường là:

1. Sinh private key và CSR (Certificate Signing Request) theo chính sách.
2. Gửi CSR cho CA nội bộ hoặc CA công khai có thẩm quyền.
3. Nhận **leaf certificate** cho đúng DNS names/SAN và các intermediate certificates cần thiết.
4. Ghép leaf + chain với **đúng private key** trong keystore hoặc import certificate reply vào alias đang chứa private key.
5. Kiểm tra certificate chain, SAN, validity, key usage, Extended Key Usage và hostname.
6. Triển khai keystore với quyền truy cập tối thiểu; xác minh handshake bằng client thực.

Ví dụ tạo CSR từ keystore PKCS12 có alias `web-local`:

```bash
keytool -certreq \
  -alias web-local \
  -keystore local-keystore.p12 \
  -storetype PKCS12 \
  -file server.csr \
  -ext "SAN=dns:api.example.com"
```

**Đây là ví dụ lệnh CSR**, không có nghĩa CA sẽ cấp chứng chỉ ngay lập tức. Private key gốc ở keystore; CSR chứa public key và thông tin yêu cầu. Trong production, thường nên **sinh cặp khóa dành riêng cho tên miền production** thay vì tái dùng self-signed local key/certificate.

Sau khi CA trả leaf và chain hợp lệ, có thể dùng `keytool -importcert` để nhập certificate reply vào **đúng alias private-key entry**, với chain được xây dựng đúng theo tài liệu PKI và chính sách CA:

```bash
keytool -importcert \
  -alias web-local \
  -keystore server-keystore.p12 \
  -storetype PKCS12 \
  -file server-chain.pem
```

Lệnh là **mẫu thao tác**: cần `server-keystore.p12` chứa cặp khóa tương ứng với CSR và file `server-chain.pem` đúng dạng certificate reply/chain. Với CA trung gian, có thể phải import các CA certificates hoặc cung cấp chain theo trình tự mà `keytool` nhận diện. **Không gõ lệnh import reply vào keystore không có private key tương ứng**, không ép kết quả bằng cách bỏ xác minh trust/chain.

Kiểm tra sau import bằng `keytool -list -v`, `openssl s_client -showcerts` và client trust check. Domain phải khớp SAN; ngày hết hạn và issuer phải đúng; leaf certificate không thay thế intermediate chain trong triển khai đòi hỏi client xây trust path.

## 14. `server.ssl.trust-store` và mTLS: trường hợp riêng, không bắt buộc cho HTTPS

HTTPS bình thường thường dùng **server certificate** để client xác minh server. mTLS bổ sung bước server **xác minh certificate của client**. Trong Spring Boot:

```properties
server.ssl.client-auth=need

server.ssl.trust-store=file:/etc/myapp/tls/client-ca-truststore.p12
server.ssl.trust-store-type=PKCS12
server.ssl.trust-store-password=${TLS_TRUSTSTORE_PASSWORD}
```

`need` yêu cầu client cung cấp certificate hợp lệ theo trust material trên server. `want` yêu cầu/đề nghị nhưng có thể chấp nhận client không có chứng chỉ, tùy TLS implementation; `none` không yêu cầu client certificate. Cấu hình mTLS này **đi cùng keystore server HTTPS**, chứ không thay thế nó.

Ví dụ tạo truststore chứa **CA được phép phát hành client certificates**:

```bash
keytool -importcert \
  -alias permitted-client-ca \
  -file client-ca.pem \
  -storetype PKCS12 \
  -keystore client-ca-truststore.p12
```

Chỉ import CA certificate sau khi đã xác minh nguồn/fingerprint theo kênh tin cậy. Đưa cả certificate công khai của một user tùy ý vào truststore không tương đương với chính sách cho phép mọi user khác.

Quan trọng hơn, **TLS client authentication không tự là authorization của ứng dụng**. Server chấp nhận certificate từ một CA chỉ chứng minh chain hợp lệ theo truststore; Spring Security hoặc business layer vẫn cần ánh xạ certificate/principal sang user, tenant và roles theo policy. Không tự xem mọi client certificate được CA ký là admin.

Nếu Spring Boot chạy sau reverse proxy và **proxy** làm mTLS với client, `server.ssl.client-auth` ở backend có thể không được dùng cho client gốc. Khi cần ứng dụng nhận thông tin danh tính client do proxy chuyển tiếp, phải cấu hình một cơ chế tin cậy cụ thể, tránh tin những HTTP headers do public client tự gửi.

## 15. Server keystore không cấu hình TLS outbound client

Một nhầm lẫn hay gặp: có `server.ssl.key-store` thì mọi `RestClient`, `RestTemplate`, `WebClient`, JDBC, Kafka hoặc HTTP client trong app tự dùng truststore/chứng chỉ đó. **Không đúng.**

`server.ssl.*` cấu hình kết nối **đi vào embedded web server**. Khi ứng dụng gọi HTTPS đến server khác, nó là **TLS client** và cần trust material/client key material riêng theo HTTP client/driver đang dùng.

| Luồng | Ai là TLS server? | Nơi thường cấu hình |
| --- | --- | --- |
| Browser → Spring Boot HTTPS | Spring Boot | `server.ssl.*` |
| Spring Boot → HTTPS API khác | API từ xa | Java client/HTTP client SSL context hoặc SSL bundle |
| NGINX (HTTPS) → Spring Boot (HTTP) | NGINX là TLS server phía client công khai | TLS cert trên NGINX, backend không cần `server.ssl.*` nếu transport nội bộ chủ đích là HTTP |
| NGINX (HTTPS) → Spring Boot (HTTPS) | Cả NGINX và Boot ở hai TLS hops | Cấu hình TLS độc lập ở từng hop |
| Spring Boot → DB `jdbc:...ssl...` | DB là TLS server | JDBC driver/DataSource SSL settings, không phải `server.ssl.*` |

Spring Boot hỗ trợ `spring.ssl.bundle.jks` và `spring.ssl.bundle.pem` để định nghĩa các bộ SSL material có tên dùng ở nhiều nơi khi thư viện tích hợp hỗ trợ. Nhưng một `server.ssl.bundle` dành cho inbound server **không tự chuyển tất cả outbound clients sang cùng truststore**.

## 16. SSL bundles là lựa chọn thay thế, KHÔNG trộn với discrete `server.ssl.key-store`

Spring Boot 3.3 có SSL bundles để quản lý key/trust material bằng tên. Đây là **một lựa chọn khác** so với cấu hình `server.ssl.key-store` trực tiếp:

```properties
# Phương án bundle, thay thế cho discrete key-store configs:
spring.ssl.bundle.jks.web.keystore.location=${TLS_KEYSTORE_LOCATION}
spring.ssl.bundle.jks.web.keystore.password=${TLS_KEYSTORE_PASSWORD}
spring.ssl.bundle.jks.web.keystore.type=PKCS12
spring.ssl.bundle.jks.web.key.alias=web-local

server.port=8443
server.ssl.bundle=web
server.http2.enabled=true
```

**Không dùng đồng thời**:

```properties
server.ssl.bundle=web
server.ssl.key-store=file:/etc/myapp/tls/server.p12
```

Hai cách này xung đột về lựa chọn SSL material. Tài liệu Spring Boot 3.3 nêu `server.ssl.bundle` **không được kết hợp** với các tùy chọn Java keystore hoặc PEM rời dưới `server.ssl`. Khi dùng bundle, các property `server.ssl.ciphers`, `server.ssl.enabled-protocols`, `server.ssl.protocol` cũng không phải nơi điều khiển TLS options của bundle; hãy cấu hình bằng `spring.ssl.bundle.<type>.<name>.options` tương ứng.

Ví dụ dạng bundle dùng `spring.ssl.bundle.jks.web...` dù keystore file có format `PKCS12`: chữ `jks` trong **nhóm property SSL bundle** biểu thị Java KeyStore-based configuration, hỗ trợ JKS **và** PKCS12.

Bài này tập trung cách cấu hình `server.ssl.*` dạng discrete với JKS/PKCS12. Chỉ chuyển sang bundle khi muốn tổ chức SSL material nhất quán, tái sử dụng theo component hoặc hỗ trợ cách tổ chức certificate hiện đại hơn; không thay đổi chỉ vì gặp lỗi alias/password chưa được chẩn đoán.

## 17. HTTPS trực tiếp và TLS termination ở reverse proxy

Trong production, có hai kiến trúc phổ biến.

**A. TLS kết thúc ngay tại Spring Boot**

```text
Client -- HTTPS (443/8443) --> Spring Boot embedded server
                                  server.ssl.key-store
```

Ứng dụng cần keystore có certificate phù hợp hostname public. Nếu dùng nhiều replicas, mỗi instance được cấp đúng material hoặc sử dụng TLS management strategy tương ứng. Cần chính sách private-key storage, rotation, network exposure, HSTS/redirect tại edge và giám sát cert expiry.

**B. TLS kết thúc tại reverse proxy/load balancer**

```text
Client -- HTTPS --> NGINX/Ingress/LB -- HTTP hoặc HTTPS --> Spring Boot
                      cert/key trên edge               backend transport
```

Khi proxy làm TLS termination, `server.ssl.*` trên Spring Boot **không quyết định browser-facing certificate**. Có thể backend dùng HTTP trên mạng private có kiểm soát; nếu yêu cầu end-to-end encryption thì cấu hình HTTPS cả ở backend với certificate và trust policy riêng.

Bảo vệ forwarded headers: ứng dụng chỉ nên tin `X-Forwarded-Proto`, `Forwarded` và các headers tương tự từ **proxy đáng tin cậy**; đừng để public client tự đặt header rồi đánh lừa logic xác định scheme/cookie/redirect. Trong Spring Boot có nhóm `server.forward-headers-strategy`, nhưng cách bật phải phù hợp topology và allowlist proxies của hạ tầng.

**Không tự thêm `server.ssl.*` vào backend để “sửa” chứng chỉ trên load balancer**: nếu browser TLS terminate tại edge, phải sửa certificate/trust/hostname ở edge.

## 18. Chứng chỉ, SNI, tên miền và port: những điểm dễ sai

### 18.1. CN khác SAN

Chứng chỉ cho `api.example.com` phải có `subjectAltName` chứa `DNS:api.example.com`. Trong local demo, SAN gồm `DNS:localhost` và `IP:127.0.0.1`. Các browser hiện đại đánh giá SAN; `CN` một mình không thay thế việc liệt kê DNS/IP chính xác.

### 18.2. Certificate chain phải đầy đủ

Leaf certificate từ CA thường cần intermediate chain để client xây trust path. Nếu keystore chỉ có leaf và thiếu intermediate cần thiết, một số client vẫn kết nối được nhờ cached CA nhưng client khác thất bại. Kiểm tra chain từ **server trên mạng**, không chỉ `keytool` đọc file local.

### 18.3. Mỗi SNI hostname có thể cần certificate khác

Nếu cùng embedded web server phục vụ nhiều hostnames với certificates riêng, Spring Boot 3.3 hỗ trợ SNI thông qua `server.ssl.server-name-bundles` khi server phù hợp (Tomcat/Netty/Undertow theo tài liệu; Jetty có cơ chế riêng). Đây là chủ đề nâng cao dùng **SSL bundles** chứ không phải nhiều alias tùy tiện cùng một JKS rồi mong Boot tự chọn theo hostname.

Một certificate có SAN cho nhiều hostnames cũng có thể phục vụ các host ấy nếu policy PKI cho phép. Đừng coi alias name của keystore là hostname trong URL; alias là nhãn nội bộ của key entry.

### 18.4. Port 443 và 8443

`server.port=8443` chỉ chọn cổng; TLS do `server.ssl.*` quyết định. Khi cấu hình HTTPS trên port 8443, request HTTP thuần vào port này không hợp lệ. HTTPS production thường dùng 443 tại edge hoặc server; cổng thấp trên Linux có yêu cầu permissions/capabilities, nên nhiều deployment chọn 8443 ở app và 443 tại load balancer.

## 19. Bảo mật keystore và secret trong môi trường thực

**Keystore chứa private key là bí mật cấp cao.** Không commit `.jks`, `.p12` có private key vào Git, container image public hoặc thư mục static. Không in file base64, password, PEM private key hoặc `keytool -list -v` nhạy cảm lên ticket/log công khai.

Một kế hoạch quản lý đúng gồm:

- **Secret source:** secret manager, vault, Kubernetes Secret với RBAC/encryption at rest theo hạ tầng, hoặc file mount được bảo vệ; environment variables có mặt lợi/hại và có thể bị lộ trong diagnostics/process context.
- **Filesystem ACL:** tài khoản service chỉ có read quyền cần thiết với keystore; không world-readable; thư mục tổ tiên không cho user không tin cậy thay file.
- **Password:** không đưa trực tiếp vào `application.properties` đã commit; dùng placeholder từ secret/env và loại secret ra khỏi logs/config endpoints.
- **Certificate rotation:** quản lý expiry monitoring và quy trình thay cert/key trước khi hết hạn. Thay keystore và password nhất quán, khởi động/restart có kiểm soát theo capability của server.
- **Rollback:** giữ bản chứng chỉ hợp lệ trước đó theo chính sách bảo mật và bảo đảm có cách phục hồi nếu cert/chain mới sai.
- **Least privilege:** tách vai trò quản lý certificate, deploy và đọc logs; tránh phân phối private key tới mọi service không cần thiết.
- **Audit:** log kết quả TLS config và certificate metadata được phép (alias, expiry, fingerprint đã kiểm soát), không log private key/password.

Đặc biệt, “base64-encode password hoặc keystore” **không phải mã hóa bí mật**; bất kỳ ai có chuỗi base64 cũng có thể giải mã. SSL bundle hỗ trợ nguồn base64 ở một số cấu hình nhưng việc bảo mật vẫn phụ thuộc secret management.

## 20. Lỗi thường gặp và cách chẩn đoán có thứ tự

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `Keystore was tampered with, or password was incorrect` hoặc lỗi MAC | Sai password/format/provider hoặc file bị lỗi | `keytool -list -storetype ... -keystore ...`, kiểm tra secret |
| `UnrecoverableKeyException` | Key entry password khác store password | Kiểm tra `server.ssl.key-password` và cách import key |
| `Alias name ... does not identify a key entry` | Alias sai hoặc entry chỉ là certificate | `keytool -list -v -alias ...`, cần `PrivateKeyEntry` |
| `FileNotFoundException`/resource không tồn tại | `classpath:`/`file:` path sai, file không được đóng gói/mount | Kiểm tra tuyệt đối path, resource URL và quyền |
| `Invalid keystore format`/load failed | Định dạng file khác property hoặc file hỏng | Kiểm tra `key-store-type`, conversion, provider |
| SSL server khởi động nhưng browser báo self-signed | Browser không tin CA của cert demo | Dùng CA tin cậy trong production; local trust đúng mục đích |
| `NET::ERR_CERT_COMMON_NAME_INVALID` | Hostname không khớp SAN | Kiểm tra DNS/IP trong certificate và URL thực |
| Certificate expired/not yet valid | Validity hoặc đồng hồ host/client sai | `keytool -list -v`, thời gian hệ thống, rotation |
| `PKIX path building failed` ở client | Trust chain không đầy đủ/CA không tin, hoặc client truststore không phù hợp | Xác nhận chain server gửi và client trust anchors |
| `No appropriate protocol` / handshake failure | TLS version/cipher suites không có giao nhau | Đối chiếu JDK, TLS config, OpenSSL/curl negotiated values |
| `curl: (35) ...` hoặc handshake bất thường | Gọi HTTP sai port HTTPS, TLS mismatch, proxy | So sánh URL scheme, port, proxy và server logs |
| HTTPS 8443 chạy, HTTP 8080 không chạy | Bình thường khi Boot chỉ cấu hình HTTPS connector | Muốn thêm HTTP connector phải dùng code/proxy |
| `curl --http2` không ra h2 | curl thiếu HTTP2 support, ALPN không chọn h2, proxy hoặc server stack | `curl -V`, verbose ALPN, `server.http2.enabled` |
| HTTPS ở backend nhưng browser vẫn thấy cert edge | TLS termination tại reverse proxy | Kiểm tra cert của edge, không sửa nhầm backend |
| Server yêu cầu client certificate | `server.ssl.client-auth=need` và truststore mTLS | Test client cert, client trust chain, policy |
| SNI hostname khác hiển thị cert không đúng | Nhiều hostnames nhưng mapping/bundle khác thực tế | Kiểm tra `-servername`, SAN, SNI bundle config |
| Chạy IDE được, `java -jar` lỗi keystore | Dùng relative file path, keystore không nằm trong JAR hoặc secret chưa cấp | Kiểm tra `file:`/`classpath:`, mount, env của process thật |

**Cách debug đúng lớp:**

1. Xác nhận **tiến trình và cổng** (`server.port`, reverse proxy).
2. Xác nhận **file keystore** ở runtime, định dạng và `PrivateKeyEntry` qua `keytool`.
3. Xác nhận **secret** và key password, alias.
4. Xác nhận **handshake** bằng `openssl s_client`; đọc chứng chỉ server gửi.
5. Xác nhận **hostname/SAN và trust chain** từ góc nhìn client.
6. Xác nhận HTTP path qua `curl` (có thể ứng dụng trả 404 dù TLS hoạt động đúng).
7. Nếu dùng HTTP/2, xác nhận **ALPN h2**, server container và curl feature.
8. Nếu có proxy, phân biệt rõ public TLS hop và backend TLS hop.

Có thể chạy ứng dụng với `--debug` để xem Spring Boot Condition Evaluation Report, nhưng báo cáo này không tự giải mã mọi lỗi certificate/key. `javax.net.debug=ssl,handshake` có thể hỗ trợ debug JSSE trong môi trường kiểm soát; **cẩn thận log có thể rất dài và chứa thông tin nhạy cảm về TLS session/peer**.

## 21. Kiểm thử tích hợp và kiểm tra trước khi deploy

Một test HTTPS phải kiểm tra cả **chứng chỉ server và response HTTP**. Ví dụ controller trong mục 9 có thể kiểm tra theo hai tầng.

**Tầng A — kiểm tra key material trước khi chạy:**

```bash
keytool -list -v \
  -storetype PKCS12 \
  -keystore local-keystore.p12 \
  -alias web-local
```

Xác minh entry là `PrivateKeyEntry`, certificate còn hạn, SAN có `localhost`, chain hợp lý và password đúng.

**Tầng B — HTTP over TLS sau khi boot:**

```bash
curl --cacert local-cert.pem -i https://localhost:8443/hello
```

Expected body:

```text
secure-ok
```

Thử negative cases trong môi trường test được kiểm soát:

- Đổi alias sang tên không tồn tại → server phải báo lỗi cấu hình thay vì âm thầm phục vụ bằng identity khác.
- Đưa sai keystore password → khởi động lỗi; không bỏ TLS để chạy tạm.
- Đổi `TLS_KEYSTORE_LOCATION` sang path không tồn tại → lỗi resource, cần sửa đường dẫn.
- Gọi một hostname không có SAN tương ứng → client xác minh hostname thất bại.
- Không có CA tin cậy → client xác minh chain thất bại; chỉ dùng `-k` để phân biệt TLS engine đang chạy trong local.
- `server.http2.enabled=false` → TLS vẫn có thể dùng HTTP/1.1, không có nghĩa HTTPS đã tắt.
- Test qua proxy → so sánh response cert ở public URL với backend; kết quả có thể thuộc hai TLS hop khác nhau.

Với automated tests, không nên commit private key production để test. Sinh self-signed keystore riêng trong temporary directory hoặc dùng test fixture bảo vệ riêng, cấu hình ephemeral TLS port và keystore password dành cho test. Khi dùng JUnit `@SpringBootTest(webEnvironment = RANDOM_PORT)`, có thể cần cấu hình trust material riêng cho HTTP test client nếu server dùng self-signed certificate; không suy rằng `TestRestTemplate` tự luôn tin self-signed cert như browser được CA cấp.

Đối với traffic production, ngoài chứng chỉ hợp lệ còn cần xét TLS security policy, HTTP response headers, HSTS tại HTTPS edge, rate limiting và monitoring. **Bật TLS không đồng nghĩa mọi endpoint đã được xác thực và phân quyền bởi Spring Security.**

## 22. Các hiểu nhầm quan trọng

**“Có file `.p12` là chắc chắn có private key.”** Sai. Nó có thể chỉ là truststore với `trustedCertEntry`. HTTPS server cần key entry và certificate chain tương ứng.

**“JKS và PKCS12 chỉ khác đuôi.”** Sai. Format binary khác nhau; phải dùng `keytool -importkeystore` khi cần conversion, không đổi tên file.

**“`server.ssl.trust-store` làm browser tin server.”** Sai. Browser cần trust anchors của **browser** và chain/SAN hợp lệ. Truststore ở server dùng kiểm tra peer (đặc biệt client cert trong mTLS).

**“Đặt `server.ssl.enabled=true` nhưng không có keystore thì Boot tự cấp cert.”** Sai. Phải có key material hợp lệ (keystore hoặc cấu hình PEM/bundle theo phương án khác).

**“Bật `server.http2.enabled=true` nghĩa là đã có HTTPS.”** Sai. HTTP/2 và TLS là các lớp khác nhau. H2 over TLS yêu cầu SSL enabled; h2c có thể là HTTP/2 cleartext.

**“Bật HTTPS trên 8443 sẽ tự redirect 8080 sang 8443.”** Sai. Boot không tự tạo cả hai connectors chỉ bằng application properties. Redirect thường làm ở reverse proxy hoặc cấu hình connector bổ sung.

**“Có `CN=localhost` thì client chắc chắn chấp nhận hostname.”** Sai. Xác minh hostname hiện đại dựa vào SAN và trust chain.

**“Cấu hình password trong `application.yml` sẽ được mã hóa vì dùng HTTPS.”** Sai. TLS bảo vệ network traffic, không mã hóa file cấu hình/secret at rest.

**“Dùng SSL bundle và discrete key-store cùng lúc cho chắc.”** Sai; hai phương án không được kết hợp.

**“Cứ bắt client cert qua mTLS thì mọi user đều được quyền.”** Sai. mTLS xác minh peer certificate; authorization vẫn là policy của ứng dụng.

**“Có server keystore thì outbound API clients tự dùng nó.”** Sai. Inbound server và outbound TLS client phải được cấu hình đúng vai trò.

## 23. Tự kiểm tra và bài tập nâng cao

**Câu hỏi ôn tập:**

1. `server.ssl.key-store` phải trỏ đến loại entry nào để server có thể trình bày danh tính TLS? Vì sao chỉ có `trustedCertEntry` chưa đủ?
2. Trong PKCS12 local với alias `web-local`, những thuộc tính `server.ssl.*` tối thiểu nào cần phù hợp?
3. Nếu JKS dùng password riêng cho private-key entry, thiếu property nào có thể khiến `UnrecoverableKeyException`?
4. `-ext SAN=dns:localhost,ip:127.0.0.1` có vai trò gì so với `CN=localhost`?
5. Vì sao cấu hình `server.ssl.key-store=file:/...` khác `classpath:...` khi đóng gói và luân chuyển certificate?
6. Nếu reverse proxy đã terminate TLS, chứng chỉ mà browser thấy nằm ở đâu? Khi nào backend vẫn cần HTTPS?
7. Tại sao `curl -k` kết nối thành công chưa chứng minh certificate hợp lệ cho production?
8. `server.http2.enabled=true` có thể chọn `h2`, `h2c` hoặc HTTP/1.1 khi nào? Vai trò ALPN là gì?
9. Muốn kiểm tra client certificates trong mTLS, server cần keystore nào và truststore nào?
10. Vì sao `server.ssl.bundle` không nên cấu hình cùng `server.ssl.key-store`?
11. Khi certificate rotation, tại sao cập nhật file trên disk chưa đủ chứng minh server đang phục vụ certificate mới?
12. Nếu SSL handshake thành công nhưng `GET /hello` trả 404, tầng nào cần debug và tại sao không nên đổi format keystore?

**Bài tập:** Tạo lần lượt `local-keystore.p12` và `local-keystore.jks` với cùng alias, chỉnh `server.ssl.key-store-type` và `TLS_KEYSTORE_LOCATION` tương ứng; chạy demo `/hello`; dùng `keytool`, `openssl s_client`, `curl --cacert` để ghi nhận certificate, TLS protocol, negotiated HTTP version. Thử chỉnh sai từng property **trên môi trường test** rồi mô tả lỗi thuộc tầng keystore load, TLS handshake hay HTTP routing.

**Kết luận:** `server.ssl.*` cung cấp cách cấu hình HTTPS trực tiếp trên embedded server, trong đó **keystore phải chứa private key cùng certificate chain**, format là **JKS** hoặc **PKCS12**, đường dẫn/password/alias phải khớp. HTTP/2 là cấu hình bổ sung (`server.http2.enabled`), mTLS cần truststore/policy riêng, và production phải có certificate do CA thích hợp cấp, secret management, rotation và kiểm thử thực tế theo từng TLS hop.

### Tài liệu chính thức

- Spring Boot 3.3, Embedded Web Servers — Configure SSL, SSL Bundles, HTTP/2: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3, Common Application Properties (`server.ssl.*`, `server.http2.enabled`): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3, SSL Bundles (JKS/PKCS12): https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
- Java 17 `keytool`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- JSSE Reference Guide: https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html
- RFC 8446 — TLS 1.3: https://www.rfc-editor.org/rfc/rfc8446
- RFC 9113 — HTTP/2: https://www.rfc-editor.org/rfc/rfc9113
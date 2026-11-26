# Chuẩn bị chứng thư và truststore cho bài TLS

## 1. Mục tiêu và phạm vi

Trong **Spring Vault**, ứng dụng Java gọi HashiCorp Vault qua các API như **VaultTemplate** để đọc KV secrets, mã hóa bằng Transit, xin chứng chỉ PKI và sử dụng token hoặc lease. Trước khi Vault nhận request và đánh giá policy, ứng dụng phải thiết lập được kết nối tới **đúng máy chủ Vault**. Khi dùng HTTPS, bước này phụ thuộc vào chứng thư (certificate), tên máy chủ và chuỗi tin cậy TLS.

Bài học thuộc chương **Môi trường thực hành**, hướng dẫn chuẩn bị một **CA cục bộ**, chứng thư TLS cho Vault server và **PKCS#12 truststore** cho JVM. Ta sẽ chạy một Vault **non-dev một node** có TLS để quan sát các lỗi thực tế như CA không tin cậy, hostname không khớp, chứng thư hết hạn và server còn sealed. Bài tập tập trung vào **xác thực máy chủ qua TLS**, khác với việc ứng dụng đăng nhập Vault bằng token hoặc AppRole.

Sau bài này, bạn có thể:

1. Phân biệt **CA certificate**, **server certificate**, **private key**, **truststore** và **keystore**.
2. Tạo CA thử nghiệm và ký server certificate có **Subject Alternative Name (SAN)** phù hợp địa chỉ truy cập.
3. Cấu hình listener HTTPS của Vault và xác minh bằng **OpenSSL**, **curl** và Vault CLI.
4. Nhập CA certificate vào truststore dạng **PKCS#12** bằng **keytool**.
5. Cấu hình JVM để **VaultTemplate** tin cậy Vault server, đồng thời vẫn sử dụng token có quyền tối thiểu.
6. Xác định lỗi thuộc TLS, authentication, authorization hay trạng thái Vault; lập kế hoạch xoay vòng chứng thư và kiểm thử tích hợp.

**Giới hạn:** Toàn bộ lệnh dùng cho phòng lab cục bộ với dữ liệu giả. Khóa CA tự tạo, chứng thư ngắn hạn, storage một node và cách nhập thủ công thông tin quản trị chỉ phù hợp môi trường học. Trong vận hành thật cần quản lý CA, bảo vệ private key, HA, backup, seal/unseal, audit, quy trình cấp lại chứng thư và quyền truy cập theo workload.

## 2. Mô hình TLS và các loại tệp

~~~mermaid
flowchart LR
    CA["CA của phòng lab<br/>ca.crt / ca.key"] -->|"ký"| Cert["Vault server<br/>vault.crt / vault.key"]
    CA -->|"nhập chứng thư CA"| Store["JVM truststore<br/>vault-truststore.p12"]
    Client["Java / VaultTemplate"] -->|"HTTPS, kiểm tra SAN<br/>và chain tới CA"| Cert
    Client -->|"tải trust anchors"| Store
    Cert --> Vault["Vault listener :8200"]
    Client -. "sau TLS: client token" .-> Vault
~~~

| Thành phần | Ai sử dụng? | Có bí mật không? | Vai trò |
| --- | --- | --- | --- |
| **ca.key** | Người quản trị CA | **Có, rất nhạy cảm** | Ký các chứng thư thử nghiệm |
| **ca.crt** | Máy khách và người xác minh chuỗi chứng thư | Không | Chứng thư gốc được tin cậy (trust anchor) |
| **vault.key** | Vault server | **Có** | Chứng minh server sở hữu khóa riêng ứng với chứng thư |
| **vault.crt** | Vault server trình cho client | Không | Danh tính server, SAN, thời hạn và thông tin bên ký |
| **vault.csr** | Công đoạn xin ký chứng thư | Không phải private key | Certificate Signing Request; chỉ cần lúc phát hành |
| **vault-truststore.p12** | JVM chạy Spring Vault | Cần bảo vệ tính toàn vẹn | Chứa CA được client tin cậy; không cần giữ **ca.key** |
| **VAULT_TOKEN** | Vault client | **Có** | Xác thực request API sau khi TLS được thiết lập |

**Truststore** trả lời câu hỏi “client tin chứng thư do CA nào ký?”. **Keystore chứa private key** thường phục vụ server TLS hoặc client mTLS. Một file PKCS#12 có thể chứa chứng thư và khóa riêng, nhưng truststore ở bài này chỉ nhập **ca.crt**, không nhập **ca.key** hay **vault.key**.

Ba kiểm tra quan trọng của kết nối TLS từ Java:

1. **Chain of trust:** chứng thư server có thể được xác minh tới một CA trong truststore.
2. **Hostname/IP:** tên host trong URL khớp một giá trị **DNS** hoặc **IP** của trường SAN.
3. **Validity:** chứng thư còn hiệu lực, dùng được cho **TLS server authentication** và thuật toán được nền tảng hỗ trợ.

TLS **không** tự cấp quyền đọc KV hoặc giải mã Transit. Sau handshake, Vault vẫn cần token hoặc auth method phù hợp, rồi áp dụng policy lên endpoint thực tế.

## 3. Chuẩn bị cấu trúc thư mục và công cụ

Cần:

- **OpenSSL** để tạo khóa, CSR, ký và kiểm tra chứng thư; trên Windows có thể chạy trong WSL/Git Bash với bộ OpenSSL phù hợp.
- **JDK** có lệnh **keytool** và runtime Java để chạy ứng dụng.
- **Docker Engine/Docker Desktop** và **Docker Compose v2** để chạy Vault.
- Cổng **8200** còn trống trên máy host và một thư mục lab tách khỏi repository chứa code ứng dụng.

Tạo cấu trúc dự kiến:

~~~text
spring-vault-tls-lab/
├── compose.yaml
├── vault.hcl
├── tls/
│   ├── ca.cnf
│   ├── ca.key                 # private, KHÔNG commit
│   ├── ca.crt
│   ├── vault.key              # private, KHÔNG commit
│   ├── vault.csr
│   ├── server.ext
│   ├── vault.crt
│   └── vault-truststore.p12   # tạo ở bước 7
└── policies/
    └── lab-reader.hcl
~~~

Các tệp sẽ được tạo theo thứ tự trong bài, không cần có sẵn từ đầu. Tạo thư mục **tls/** và **policies/** trước khi chạy lệnh. **Không commit** các tệp private key, truststore, token hoặc thư mục dữ liệu Vault; dùng quy tắc ignore phù hợp với repository. Trên Linux/macOS, giới hạn quyền đọc khóa riêng cho tài khoản cần thiết, ví dụ **chmod 600 tls/ca.key**. Với **vault.key**, phải bảo đảm tài khoản chạy tiến trình Vault trong container vẫn có quyền đọc bằng owner/group/ACL thích hợp; không mở quyền đọc công khai để chữa lỗi permission. Trên Windows, kiểm tra ACL tương đương. Container Vault chỉ cần **đọc** khóa server, không cần quyền truy cập khóa CA.

Trong các lệnh sau, mọi đường dẫn tương đối đều tính từ thư mục **spring-vault-tls-lab/**. Để đơn giản, tên trong chứng thư là **localhost** (truy cập từ máy host) và **vault** (truy cập giữa các container cùng mạng Compose); địa chỉ IP cục bộ **127.0.0.1** cũng được đưa vào SAN.

## 4. Tạo CA cục bộ dành cho học tập

### 4.1. Khóa riêng CA và cấu hình extension

Tạo khóa RSA cho CA:

~~~bash
openssl genrsa -out tls/ca.key 3072
~~~

Tạo tệp **tls/ca.cnf**:

~~~ini
[req]
prompt = no
distinguished_name = dn
x509_extensions = v3_ca

[dn]
CN = Spring Vault Learning Lab CA

[v3_ca]
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
~~~

Ký chứng thư gốc tự ký cho CA, thời hạn 30 ngày:

~~~bash
openssl req -new -x509 -sha256 -days 30 -key tls/ca.key -out tls/ca.crt -config tls/ca.cnf
openssl x509 -in tls/ca.crt -noout -subject -issuer -dates
~~~

**ca.crt** là chứng thư công khai mà Java sẽ tin cậy. **ca.key** là khóa riêng của CA và phải được giữ tách biệt; nếu bị lộ, người có khóa có thể ký chứng thư giả mạo được các client tin CA này chấp nhận. Không gắn **ca.key** vào container Vault và không sao chép nó vào JAR hoặc image ứng dụng.

Để nhận dạng CA trước khi import, xem fingerprint:

~~~bash
openssl x509 -in tls/ca.crt -noout -fingerprint -sha256
openssl x509 -in tls/ca.crt -noout -text
~~~

Ở lab, người học kiểm tra fingerprint trên tệp CA mình vừa tạo. Trong môi trường thật, phải đối chiếu fingerprint/chuỗi CA bằng một kênh xác thực độc lập, tránh tin một CA chỉ vì nó xuất hiện trên mạng.

## 5. Tạo server certificate có SAN đúng

### 5.1. Khóa server và CSR

Tạo khóa riêng của Vault server và yêu cầu ký:

~~~bash
openssl genrsa -out tls/vault.key 3072
openssl req -new -sha256 -key tls/vault.key -out tls/vault.csr -subj "/CN=localhost"
~~~

**CN=localhost** trong CSR không thay thế yêu cầu SAN. Client hiện đại kiểm tra SAN của certificate, đặc biệt khi kết nối bằng địa chỉ IP.

Tạo tệp **tls/server.ext**:

~~~ini
[server_cert]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @names

[names]
DNS.1 = localhost
DNS.2 = vault
IP.1 = 127.0.0.1
~~~

Ý nghĩa các SAN:

| URL được gọi | Giá trị SAN tương ứng | Tình huống |
| --- | --- | --- |
| **https://localhost:8200** | **DNS:localhost** | Java, curl, CLI trên máy host |
| **https://127.0.0.1:8200** | **IP:127.0.0.1** | Kết nối bằng IPv4 loopback |
| **https://vault:8200** | **DNS:vault** | Java nằm trong container cùng mạng Compose |

Nếu sau này dùng **https://vault.example.internal:8200**, phải cấp chứng thư có SAN **DNS:vault.example.internal** và bảo đảm DNS kết nối đúng server. Chỉ thay URL trong Java không làm chứng thư cũ hợp lệ với tên mới.

### 5.2. Ký và kiểm tra chứng thư server

~~~bash
openssl x509 -req -in tls/vault.csr -CA tls/ca.crt -CAkey tls/ca.key -CAcreateserial -out tls/vault.crt -days 7 -sha256 -extfile tls/server.ext -extensions server_cert
openssl verify -CAfile tls/ca.crt tls/vault.crt
openssl x509 -in tls/vault.crt -noout -subject -issuer -dates -ext subjectAltName
~~~

Kết quả **openssl verify** mong đợi là **tls/vault.crt: OK**. Kiểm tra issuer là CA lab, SAN có ba giá trị đã chọn và ngày hết hạn còn phù hợp. Nếu OpenSSL báo lỗi, không khởi chạy Vault trước khi giải quyết; lỗi có thể do sai CA, sai cặp khóa, thiếu extension hoặc file bị hỏng.

Ở môi trường vận hành, CA được cấp phát/quản lý theo quy trình PKI của tổ chức hoặc nền tảng. Thao tác ký trực tiếp bằng **ca.key** trong thư mục lab chỉ nhằm giúp người học thấy rõ chuỗi tin cậy.

## 6. Khởi chạy Vault non-dev với HTTPS

Để sử dụng chứng thư đã chuẩn bị, ta cấu hình Vault listener TLS. Ví dụ dùng **storage file một node** để nhìn rõ init/unseal và giữ trạng thái qua restart. Đây là môi trường thử nghiệm, **không phải cấu hình HA/production**.

### 6.1. Cấu hình vault.hcl

Tạo **vault.hcl**:

~~~hcl
ui = true
api_addr = "https://localhost:8200"

# Chỉ để giảm yêu cầu quyền mlock của phòng lab container.
disable_mlock = true

storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address = "0.0.0.0:8200"
  tls_cert_file = "/vault/tls/vault.crt"
  tls_key_file = "/vault/tls/vault.key"
  tls_min_version = "tls12"
}
~~~

Trong listener, **0.0.0.0:8200** là địa chỉ nghe *bên trong container*. Ta sẽ chỉ xuất cổng lên **127.0.0.1** của host. **api_addr** ở đây phù hợp với máy học một node; đối với cụm nhiều node hoặc reverse proxy, địa chỉ được quảng bá và cấu hình TLS/DNS cần thiết kế theo topology thực.

### 6.2. Cấu hình Docker Compose

Tạo **compose.yaml**:

~~~yaml
services:
  vault:
    image: hashicorp/vault:1.19.0
    cap_add:
      - IPC_LOCK
    command: server -config=/vault/config/vault.hcl
    environment:
      VAULT_ADDR: https://127.0.0.1:8200
      VAULT_CACERT: /vault/tls/ca.crt
    volumes:
      - ./vault.hcl:/vault/config/vault.hcl:ro
      - ./tls/ca.crt:/vault/tls/ca.crt:ro
      - ./tls/vault.crt:/vault/tls/vault.crt:ro
      - ./tls/vault.key:/vault/tls/vault.key:ro
      - vault-storage:/vault/file
    ports:
      - "127.0.0.1:8200:8200"
    restart: "no"

volumes:
  vault-storage:
~~~

**VAULT_CACERT** giúp **Vault CLI bên trong container** tin CA vừa tạo; biến này không tự thêm CA vào truststore của JVM. Compose chỉ mount **ca.crt**, **vault.crt** và **vault.key** dạng chỉ đọc, không đưa **ca.key** vào container. Server cần **vault.key** để chạy TLS, nhưng không cần khóa riêng của CA. Với môi trường thật, khóa server cũng nên do hệ thống quản lý bí mật/cấp phát chứng thư bảo vệ và cấp quyền đọc tối thiểu.

Khởi chạy:

~~~bash
docker compose up -d
docker compose ps
docker compose logs --tail=80 vault
~~~

Nếu container không chạy, kiểm tra quyền đọc **vault.key**, **vault.crt**, quyền ghi storage, cấu hình HCL và log Vault. Khi mount thư mục được chia sẻ từ Windows hoặc macOS, quyền file/volume có thể khác Linux; cần kiểm chứng trong môi trường đang sử dụng.

### 6.3. Init/unseal của non-dev

Kiểm tra từ CLI trong container:

~~~bash
docker compose exec -T vault vault status
~~~

Vault non-dev **chưa init** sẽ không ở trạng thái ready. Lệnh **vault status** có thể trả exit code khác 0 khi sealed hoặc uninitialized; đó là trạng thái mong đợi ban đầu, chưa phải lỗi TLS.

Khởi tạo **một lần** cho lab mới; ví dụ Shamir seal với một share và ngưỡng một (chỉ phù hợp phòng lab):

~~~bash
docker compose exec -T vault vault operator init -key-shares=1 -key-threshold=1
~~~

Vault in ra **Unseal Key 1** và **Initial Root Token**. Giữ chúng ngoài code, Git và log chia sẻ. Không chạy lại **operator init** trên một Vault đã initialized; một Vault dùng persistent volume có thể vẫn giữ trạng thái qua **docker compose down** rồi **up**.

Mở khóa qua phiên terminal tương tác:

~~~bash
docker compose exec vault vault operator unseal
docker compose exec vault vault status
~~~

Nhập unseal key khi CLI yêu cầu. Sau khi unseal thành công, **Sealed: false**. Với Vault non-dev thực tế, có thể sử dụng auto-unseal qua cơ chế seal được hỗ trợ; khi đó thao tác và quản lý recovery key khác với ví dụ Shamir này.

Để tạo dữ liệu lab trong các bước sau, đăng nhập root token một cách tương tác trong container:

~~~bash
docker compose exec vault vault login
~~~

Nhập initial root token ở prompt. Vault CLI có thể lưu token bằng token helper của phiên/container; đừng đưa token vào tham số dòng lệnh hoặc lưu file token helper vào Git. Những lệnh quản trị phía sau giả định CLI trong container truy cập được token vừa login; nếu container bị tạo lại và token helper mất, cần đăng nhập lại.

**Phân biệt ba kết quả:** HTTPS handshake thành công chỉ chứng minh kênh TLS được xác lập; **HTTP 501** có thể nghĩa Vault chưa initialized, **503** nghĩa Vault sealed; **403** từ một request API thường liên quan authentication/authorization. Chúng là các tầng lỗi khác nhau.

## 7. Xác minh TLS trước khi chạy Java

### 7.1. Kiểm tra chứng thư bằng OpenSSL

Từ thư mục lab trên máy host:

~~~bash
openssl s_client -connect localhost:8200 -servername localhost -CAfile tls/ca.crt -verify_return_error -verify_hostname localhost
~~~

Tìm dòng **Verify return code: 0 (ok)** và kiểm tra subject, issuer, thời hạn trong kết quả. Tùy phiên bản OpenSSL, lệnh có thể giữ kết nối để chờ nhập thêm; kết thúc bằng Ctrl+C khi đã xem xong. Tham số **-servername** gửi SNI; **-verify_hostname** kiểm tra tên, còn **-CAfile** cung cấp CA tin cậy. Nếu chỉ chạy **openssl s_client** mà không đặt rõ điều kiện verify, đầu ra có thể khiến người học tưởng mọi chứng thư đều hợp lệ.

Với kết nối bằng IP, có thể kiểm tra IP SAN:

~~~bash
openssl s_client -connect 127.0.0.1:8200 -CAfile tls/ca.crt -verify_return_error -verify_ip 127.0.0.1
~~~

Kết quả xác minh mong đợi là thành công vì server certificate có **IP:127.0.0.1** trong SAN. Một URL sử dụng hostname khác, chẳng hạn **vault.example.internal**, sẽ không được chấp nhận nếu SAN chưa chứa hostname đó.

### 7.2. Kiểm tra bằng curl

~~~bash
curl -i --cacert tls/ca.crt https://localhost:8200/v1/sys/health
curl -i --cacert tls/ca.crt https://127.0.0.1:8200/v1/sys/health
~~~

Trên Windows PowerShell 5.1, dùng **curl.exe** nếu **curl** đang là alias của **Invoke-WebRequest**.

Kết quả cần đọc ở hai tầng:

| Tầng kiểm tra | Điều gì cho thấy thành công? | Ví dụ thất bại |
| --- | --- | --- |
| TLS | curl chấp nhận chuỗi CA, tên SAN và hoàn thành HTTPS handshake | **SSL certificate problem**, tên không khớp, chứng thư hết hạn |
| Vault health | Vault trả mã HTTP phản ánh trạng thái | **501** uninitialized, **503** sealed, **200** active và unsealed |

Ví dụ: Nếu Vault chưa init nhưng **curl --cacert** nhận được **HTTP 501**, điều đó vẫn chứng minh *kết nối HTTPS đã thành công*. HTTP 501 là trạng thái Vault chưa khởi tạo, không phải lỗi CA.

Không dùng **curl -k** hoặc **--insecure** để đánh dấu phép thử TLS là đạt. Các tùy chọn đó bỏ qua xác minh server certificate, khiến bài tập về truststore và SAN mất ý nghĩa.

### 7.3. Kiểm tra Vault CLI trên host

Nếu đã cài Vault CLI trên host, cấu hình **VAULT_ADDR** và **VAULT_CACERT**:

~~~bash
# Bash / zsh
export VAULT_ADDR="https://localhost:8200"
export VAULT_CACERT="$PWD/tls/ca.crt"
vault status
~~~

~~~powershell
# PowerShell
$env:VAULT_ADDR = "https://localhost:8200"
$env:VAULT_CACERT = (Resolve-Path "./tls/ca.crt").Path
vault status
~~~

Nếu CLI kết nối thành công và Vault đã được unseal, **vault status** hiển thị thông tin của server. **VAULT_CACERT** là cấu hình **Vault CLI**; nó không tự động điều chỉnh CA được JVM tin cậy, trừ khi chính ứng dụng có cơ chế nạp biến này.

## 8. Tạo PKCS#12 truststore cho JVM

### 8.1. Import CA certificate bằng keytool

JVM cần tin cậy CA vừa dùng để ký **vault.crt**. Tạo **tls/vault-truststore.p12**:

~~~bash
keytool -importcert -trustcacerts -alias vault-lab-ca -file tls/ca.crt -keystore tls/vault-truststore.p12 -storetype PKCS12
~~~

**keytool** sẽ hỏi mật khẩu cho truststore mới và có thể hỏi xác nhận tin cậy chứng thư; chọn mật khẩu lab và xác nhận sau khi đã đối chiếu fingerprint. Tránh đưa mật khẩu trực tiếp vào tham số **-storepass** trong command history.

Kiểm tra nội dung truststore:

~~~bash
keytool -list -v -keystore tls/vault-truststore.p12 -storetype PKCS12 -alias vault-lab-ca
~~~

Kết quả dự kiến có alias **vault-lab-ca** và certificate được nhập là **trustedCertEntry**, với subject/issuer/fingerprint tương ứng **ca.crt**.

**Tại sao import CA thay vì certificate của server?** Import CA giúp client tin các server certificate hợp lệ do cùng CA cấp, bao gồm chứng thư được cấp lại khi khóa server được xoay vòng. Nếu chỉ pin chứng thư leaf **vault.crt**, khi đổi leaf certificate thường phải cập nhật truststore, dù CA không đổi. Trong production, mức độ tin cậy nên giới hạn trong CA phù hợp, không tùy tiện thêm một CA có phạm vi cấp phát quá rộng.

### 8.2. Đọc truststore không đồng nghĩa với sở hữu private key

Truststore của bài chỉ chứa **ca.crt**. JVM **không cần** khóa **vault.key** hoặc **ca.key** để thiết lập HTTPS thông thường. Vault server gửi certificate chain và chứng minh mình có private key của leaf certificate qua handshake; JVM kiểm tra chain và hostname dựa trên CA đã tin.

Nếu một hệ thống yêu cầu **mutual TLS (mTLS)**, client có thể cần *client certificate + private key* riêng và phía Vault phải được cấu hình chấp nhận/xác minh client certificate. Đây là một luồng khác; **bài này không bật mTLS**. Việc tin server certificate không tự thay thế credential như AppRole hoặc client token để gọi Vault API.

### 8.3. Cấu hình truststore cho tiến trình Java

Ví dụ với một JAR ứng dụng đã được xây dựng và JVM dùng truststore vừa tạo:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/absolute/path/to/tls/vault-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=<lab-truststore-password> \
  -jar app.jar
~~~

Trên PowerShell, nhập lệnh trên một dòng hoặc dùng ký tự nối dòng phù hợp. Thay đường dẫn tuyệt đối và mật khẩu placeholder bằng giá trị trong môi trường lab; không viết nguyên dòng lệnh có mật khẩu vào tài liệu dùng chung. Một số công cụ có thể hiển thị JVM arguments ở process list, log hoặc hệ thống giám sát. Khi triển khai thật, cần quản lý cấu hình SSL và credential bảo mật theo cơ chế của nền tảng, thay vì gắn mật khẩu vào câu lệnh được lưu lại.

**Những điểm phải hiểu về JVM:**

- **javax.net.ssl.trustStore** là đường dẫn file *bên trong môi trường thực thi của JVM*. Nếu Java chạy trong container, đường dẫn trên máy host không tự động tồn tại trong container.
- **javax.net.ssl.trustStoreType=PKCS12** chọn kiểu truststore phù hợp với file đã tạo.
- Cài đặt này thường ảnh hưởng đến **default SSLContext/JSSE trust managers** được HTTP client của ứng dụng sử dụng. Nếu ứng dụng cấu hình một HTTP client với **SSLContext riêng**, cần nạp CA vào trust configuration của client đó.
- Việc chọn truststore tùy chỉnh có thể thay đổi tập CA được tin trong phạm vi JVM; các HTTPS endpoint khác mà ứng dụng gọi cũng cần được xem xét.
- Java 11+ thường hỗ trợ PKCS#12; cú pháp và cách cấu hình trong môi trường Spring Boot/Gradle/Maven phụ thuộc cách bạn chạy ứng dụng, vì JVM options phải được truyền vào **đúng tiến trình Java**, không chỉ vào terminal bên ngoài.

Nếu cấu hình qua biến môi trường **JAVA_TOOL_OPTIONS** hoặc runtime configuration của nền tảng, hãy kiểm tra công cụ có ghi giá trị tham số vào log không. Không in mật khẩu truststore hoặc client token ra console khi debug.

## 9. Kiểm chứng bằng VaultTemplate và token giới hạn

Chỉ sau khi **curl** và CLI xác minh HTTPS, mới cần kiểm tra lớp Java. Việc này giúp phân biệt lỗi certificate với lỗi code hoặc policy.

### 9.1. Tạo dữ liệu và policy thử nghiệm

Trong Vault non-dev đã init, unseal và login bằng tài khoản quản trị lab:

~~~bash
docker compose exec -T vault vault secrets enable -path=lab-kv kv-v2
docker compose exec -T vault vault kv put -mount=lab-kv apps/orders/config app_name=orders-api tls=enabled
docker compose exec -T vault vault kv get -mount=lab-kv apps/orders/config
~~~

Chỉ bật mount **lab-kv/** khi nó chưa tồn tại; chạy lại **kv put** sẽ tạo thêm version KV v2. Trong ví dụ, trường **tls=enabled** chỉ là dữ liệu giả để kiểm tra đọc thành công.

Tạo **policies/lab-reader.hcl**:

~~~hcl
path "lab-kv/data/apps/orders/config" {
  capabilities = ["read"]
}
~~~

Nạp policy và phát token ngắn hạn cho Java:

~~~bash
docker compose cp policies/lab-reader.hcl vault:/tmp/lab-reader.hcl
docker compose exec -T vault vault policy write lab-reader /tmp/lab-reader.hcl
docker compose exec -T vault vault token create -policy=lab-reader -ttl=15m -field=token
~~~

Lệnh cuối trả token ứng dụng. Lưu tạm trong biến môi trường của máy chạy Java:

~~~bash
# Bash / zsh
export VAULT_ADDR="https://localhost:8200"
export VAULT_TOKEN="<lab-reader-token-vua-tao>"
~~~

~~~powershell
# PowerShell
$env:VAULT_ADDR = "https://localhost:8200"
$env:VAULT_TOKEN = "<lab-reader-token-vua-tao>"
~~~

Không đưa **Initial Root Token** vào ứng dụng Java. Mặc dù TLS đã hoạt động, Vault vẫn áp dụng policy **lab-reader**: token này chỉ có quyền đọc secret mẫu và không được tự động có quyền ghi KV, decrypt Transit hoặc issue PKI.

### 9.2. Smoke test Java

Thư viện cần thiết là **org.springframework.vault:spring-vault-core** với phiên bản tương thích với Spring Framework/Spring Boot của dự án. Ví dụ này dùng token tĩnh để cô lập việc xác minh HTTPS:

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

public class TlsVaultSmokeTest {
    public static void main(String[] args) {
        String address = System.getenv("VAULT_ADDR");
        String token = System.getenv("VAULT_TOKEN");
        if (address == null || address.isBlank()
                || token == null || token.isBlank()) {
            throw new IllegalStateException(
                    "VAULT_ADDR and VAULT_TOKEN are required");
        }

        VaultTemplate template = new VaultTemplate(
                VaultEndpoint.from(URI.create(address)),
                new TokenAuthentication(token));

        Versioned<Map<String, Object>> version = template
                .opsForVersionedKeyValue("lab-kv")
                .get("apps/orders/config");

        if (version == null || version.getData() == null) {
            throw new IllegalStateException("No KV data returned");
        }
        // Chỉ in tên các trường, không xuất secret.
        System.out.println("Read fields: " + version.getData().keySet());
    }
}
~~~

Chạy chương trình với truststore cấu hình ở bước 8. Kết quả mong đợi là tên trường **app_name** và **tls**, không có **SSLHandshakeException**. Spring Vault dùng endpoint HTTPS theo **VAULT_ADDR** và policy tương ứng với API path **lab-kv/data/apps/orders/config**.

Thử đổi địa chỉ thành HTTP để thấy rằng listener này yêu cầu TLS, rồi khôi phục HTTPS. Thử dùng một token thiếu policy đọc KV: **kết nối TLS vẫn thành công**, nhưng Vault trả lỗi quyền. Hai phép thử giúp tách lỗi **kênh truyền** và **authorization**.

Khi triển khai dài hạn, cấu hình **ClientAuthentication** theo workload (AppRole, Kubernetes, JWT/cloud auth tùy môi trường) và **SessionManager** thích hợp cho token TTL, renew/re-login. Truststore không thay thế quản lý token hoặc lease; KV v2 secret tĩnh cũng không tự sinh dynamic lease khi được đọc.

### 9.3. Java chạy trong container

Nếu ứng dụng Java chạy trong Compose cùng mạng với Vault, không dùng **https://localhost:8200** để trỏ tới Vault: **localhost** trong container Java là chính container Java. Trong ví dụ này:

~~~text
Trên máy host:           VAULT_ADDR=https://localhost:8200
Trong Java container:    VAULT_ADDR=https://vault:8200
~~~

Certificate đã có **DNS:vault**, nên URL nội bộ khớp SAN. Cần bảo đảm container Java nhìn thấy **vault-truststore.p12** (thông qua volume hoặc image được xây dựng phù hợp) và JVM sử dụng **đường dẫn bên trong container**. Đường dẫn **/absolute/path/to/tls/...** trên host không thể dùng nguyên xi cho file không được mount vào container.

Không nên đưa truststore kèm secret token vào image dùng chung. Chứng thư CA công khai có thể được phân phối qua cơ chế cấu hình tin cậy, còn token/secret ID cần kênh cấp phát bí mật riêng.

## 10. Sự khác nhau giữa TLS của Vault listener và PKI secrets engine

Vault có thể vận hành **PKI secrets engine** để cấp chứng chỉ cho các ứng dụng khác. Tuy vậy, chứng thư HTTPS phục vụ **listener của chính Vault** phải có sẵn khi Vault khởi động. Bài học dùng CA ngoài Vault để tránh phụ thuộc vòng: client cần HTTPS để gọi Vault, trong khi muốn xin chứng thư từ PKI của Vault lại phải kết nối Vault trước.

| Nhu cầu | Thành phần liên quan | Ghi chú |
| --- | --- | --- |
| Bảo vệ HTTP API của Vault | **listener "tcp"** và server certificate | Client cần CA truststore và SAN phù hợp |
| Java xác minh Vault server | **JSSE truststore / SSLContext** | Có thể cấu hình ở JVM hoặc HTTP client |
| Ứng dụng đăng nhập Vault | **AppRole/token/Kubernetes/JWT/...** | Diễn ra sau khi TLS được thiết lập |
| Ứng dụng gọi Transit | **lab-transit/encrypt/...** và policy | TLS bảo vệ đường truyền; Transit mã hóa nội dung theo khóa riêng trong Vault |
| Vault phát hành chứng chỉ ứng dụng | **PKI secrets engine** và role/policy | Một API nghiệp vụ của Vault, không tự thay listener certificate |
| Chứng chỉ client mTLS (nếu bật) | **client keypair + server trust config** | Khác với truststore chỉ chứa CA để kiểm tra server |

Khi xin chứng chỉ PKI qua VaultTemplate hoặc Vault API, phải chú ý **TTL**, giới hạn role, bảo vệ private key và việc cấp/triển khai chứng chỉ mới trước ngày hết hạn. **TTL của chứng chỉ không tương đương với việc có thể kéo dài tùy ý bằng vault lease renew**.

## 11. Chẩn đoán lỗi theo tầng

| Triệu chứng | Tầng có khả năng lỗi | Cách xác minh |
| --- | --- | --- |
| **PKIX path building failed** / unable to find valid certification path | JVM không tin CA ký certificate server | Kiểm tra truststore path, alias, fingerprint và certificate chain |
| **No subject alternative DNS name matching...** | Hostname validation | So URL Java với SAN trong **vault.crt** |
| **No subject alternative names matching IP address...** | IP SAN không khớp | Kiểm tra **IP:127.0.0.1** hoặc cấp lại cert cho IP cần dùng |
| **CertificateExpiredException** | Certificate hết hạn | **openssl x509 -noout -dates**, thời gian máy |
| **Keystore was tampered with / password incorrect** hoặc lỗi tải PKCS#12 | Mật khẩu/định dạng truststore | **keytool -list**, store type, file và mật khẩu |
| **Wrong version number**, handshake failure | HTTP/HTTPS lẫn lộn hoặc TLS protocol/cipher không tương thích | Kiểm tra scheme, listener, TLS settings và client runtime |
| **Connection refused** / timeout | Mạng/tiến trình, chưa tới bước TLS | **docker compose ps**, port, log Vault |
| **HTTP 501** | Vault chưa khởi tạo | **vault status**, **operator init** lần đầu |
| **HTTP 503** | Vault đang sealed | **vault status**, unseal/auto-unseal |
| **HTTP 403** sau TLS thành công | Token không hợp lệ hoặc policy không cho phép | **vault token lookup**, API path KV v2, policy |
| **HTTP 404** trên một secret | Mount/key/version không tồn tại hoặc path sai | **vault secrets list**, **vault kv get -mount=...** |

Với TLS, cách kiểm tra nên đi từ ngoài vào trong: **DNS/port → handshake → CA chain → SAN → HTTP health → Vault token → policy/API path**. Không chữa lỗi **PKIX** bằng cách tắt xác minh TLS; không chữa lỗi **403** bằng cách nới quyền của root token trong mã nguồn.

Để quan sát lỗi Java khi thật sự cần, có thể bật **-Djavax.net.debug=ssl,handshake** trong một lượt chạy lab và chỉ giữ đoạn thông tin liên quan. Debug TLS có thể chứa nhiều dữ liệu môi trường và certificate; cần kiểm soát log, tránh bật thường trực trên môi trường vận hành.

## 12. Xoay vòng chứng thư và dọn môi trường thực hành

### 12.1. Gia hạn certificate theo cùng CA

Server certificate trong bài có hạn 7 ngày, CA có hạn 30 ngày. Trước khi hết hạn, người học có thể tạo khóa/certificate server mới, ký bằng CA còn hợp lệ và thay các file **vault.key/vault.crt** theo một quy trình có kiểm soát, sau đó khởi động lại Vault trong **lab** để listener nạp certificate. Truststore của Java thường **không cần đổi** nếu certificate mới vẫn được ký bởi cùng CA và hostname SAN đúng.

**Đừng nhầm thay leaf certificate với đổi CA.** Khi CA được thay thế, cần phân phối trust anchor mới đến từng JVM/client và có giai đoạn chuyển tiếp hợp lý để tránh mất kết nối; nếu muốn hỗ trợ cả hai CA trong giai đoạn chuyển đổi, có thể import cả hai certificate tin cậy vào truststore trước khi rút CA cũ.

Trong vận hành thực tế, kế hoạch cấp lại chứng thư phải xét tới khả năng reload certificate của từng phiên bản Vault, reverse proxy/load balancer, thời gian triển khai, HA và rollback. Dùng lệnh restart như bài lab chỉ khi biết rõ ảnh hưởng tới tính sẵn sàng.

### 12.2. Dừng lab

~~~bash
docker compose down
~~~

Lệnh này dừng và xóa container/network của Compose, nhưng mặc định **không xóa named volume vault-storage**. Khi tạo lại container từ cùng Compose project và volume, Vault non-dev có thể giữ dữ liệu đã init; trạng thái sealed/unsealed phụ thuộc cơ chế seal và việc khởi động lại. Không giả định phải **operator init** lần nữa.

Nếu muốn tạo một lab hoàn toàn mới, cần cố ý xử lý volume cũ sau khi đã kiểm tra tên và phạm vi Compose project; xóa volume có thể làm mất dữ liệu Vault vĩnh viễn. Tránh dùng lệnh xóa volume khi chưa chắc chắn đây là phòng lab chỉ chứa dữ liệu giả.

Các file **ca.key**, **vault.key**, truststore và token còn nằm trên máy host dù container đã dừng. Bảo vệ hoặc dọn chúng theo chính sách quản lý dữ liệu của môi trường học; không đưa chúng vào repository để “lưu lại bài làm”.

## 13. Bài tập và tiêu chí hoàn thành

**Bài 1 — Chuỗi tin cậy.** Chứng minh **curl --cacert tls/ca.crt** và **openssl s_client -CAfile tls/ca.crt** xác minh được Vault. Chạy curl mà không chỉ định CA riêng trên một máy chưa cài CA lab vào trust store hệ thống và so sánh lỗi. Giải thích vì sao hệ thống có thể tin một CA còn JVM chạy ứng dụng khác lại chưa tin.

**Bài 2 — SAN và hostname.** Kiểm tra cả **https://localhost:8200** và **https://127.0.0.1:8200**. Tạo một hostname giả khác không có trong SAN và xác minh client từ chối khi tên không khớp. Gợi ý Bash có thể thử **curl --resolve wrong-vault.local:8200:127.0.0.1** với HTTPS; không dùng **--insecure**.

**Bài 3 — Truststore.** Nhập CA vào PKCS#12 bằng **keytool** và kiểm tra fingerprint. Chạy một smoke test Java với truststore đúng, sau đó thử một truststore không chứa CA lab để quan sát lỗi xác minh. Đừng thay hoặc xóa truststore đang được ứng dụng thật sử dụng.

**Bài 4 — Tách TLS khỏi quyền Vault.** Với truststore đúng, chạy **VaultTemplate** bằng token chỉ đọc **lab-kv/data/apps/orders/config**. Xác nhận đọc thành công nhưng ghi cùng key bị **403**. Thay token bằng token không có policy và giải thích vì sao TLS vẫn thành công nhưng thao tác KV thất bại.

**Bài 5 — Container Java.** Đặt một client Java trong cùng Compose network và truy cập **https://vault:8200**. Chỉ ra tại sao **localhost** trong container Java không trỏ đến Vault, cách SAN **DNS:vault** được sử dụng và cần mount truststore vào đâu để JVM tìm thấy.

**Bài 6 — Vòng đời.** Giải thích điều gì cần thay khi thay server certificate bằng một leaf mới do **cùng CA** cấp; điều gì cần thay khi đổi **CA**; vì sao PKI issue, token TTL và dynamic lease là các cơ chế khác với TLS handshake.

Checklist cuối bài:

- [ ] Đã tạo CA tự ký với extension **CA:TRUE** và giữ **ca.key** ngoài container Vault.
- [ ] Server certificate có **SAN** chính xác cho **localhost**, **127.0.0.1** và **vault**.
- [ ] Vault lắng nghe HTTPS và **curl/openssl** xác minh được certificate mà không tắt kiểm tra TLS.
- [ ] Phân biệt được mã health **501/503/200** với lỗi certificate và lỗi policy **403**.
- [ ] Đã tạo **vault-truststore.p12** chứa **ca.crt**, xem được alias và fingerprint qua **keytool**.
- [ ] Java/VaultTemplate đọc được KV v2 bằng HTTPS và token có quyền hạn chế.
- [ ] Biết cách cấu hình endpoint/truststore đúng cho ứng dụng chạy trên host và trong container.
- [ ] Có phương án xử lý certificate hết hạn, đổi CA, xoay vòng token và bảo vệ private key.

**Kết quả mong đợi:** Bạn hiểu rằng cấu hình HTTPS của Vault bao gồm cả danh tính server và chuỗi tin cậy phía client. Khi Spring Vault gặp sự cố, có thể kiểm tra độc lập **TLS**, **trạng thái Vault**, **xác thực workload**, **policy** và **đường dẫn API**, thay vì sửa quyền secret hoặc bỏ qua xác minh certificate để làm request thành công.

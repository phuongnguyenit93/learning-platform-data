# Keystore, alias và mật khẩu bảo vệ khóa

Spring Cloud Config Server có thể mã hóa giá trị cấu hình nhạy cảm trước khi lưu vào Git hoặc một kho cấu hình dùng chung. Với mã hóa bất đối xứng RSA, server dùng **public key** để mã hóa và cần **private key** tương ứng để giải mã. Một keystore là nơi lưu key pair và certificate; alias chọn đúng entry cần dùng, còn mật khẩu bảo vệ keystore và private key.

Ba thông tin này có vai trò khác nhau. Nếu đặt sai `location`, server không mở được kho khóa. Nếu alias không tồn tại hoặc trỏ tới entry không có private key, server có thể mã hóa nhưng không giải mã được. Nếu mật khẩu sai, Config Server không thể mở keystore hoặc lấy private key. Vì vậy, quản lý keystore, alias và password là một phần của quy trình vận hành cấu hình mã hóa, không chỉ là bước tạo file `.jks`.

Bài học thuộc chương **Mã hóa cấu hình** của module **SPRING_CLOUD_CORE**. Ta sẽ tạo một RSA key pair bằng `keytool`, cấu hình Config Server, phân biệt store password với key password, kiểm tra `/encrypt` và `/decrypt`, lưu ciphertext vào repository, rồi thực hiện xoay vòng alias an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của keystore, key pair, certificate, alias và private-key password.
- Phân biệt symmetric encryption với asymmetric encryption trong Spring Cloud Config.
- Tạo keystore bằng `keytool` và xác minh alias, loại entry, certificate.
- Cấu hình `encrypt.keyStore.location`, `password`, `alias`, `secret` và `type`.
- Hiểu luồng public-key encryption và private-key decryption.
- Dùng `/encrypt` và `/decrypt` để kiểm tra khóa trong môi trường được bảo vệ.
- Lưu giá trị `{cipher}` trong cấu hình remote và hiểu khi nào Config Server giải mã trước khi trả cho client.
- Quản lý nhiều alias, thay khóa và xoay vòng ciphertext mà không làm gián đoạn việc đọc cấu hình.
- Bảo vệ private key, password, endpoint mã hóa và bản sao keystore trong môi trường production.

## 2. Keystore, key pair và alias là gì?

### 2.1. Keystore

**Keystore** là một container do Java KeyStore API quản lý. Nó có thể chứa một hoặc nhiều entry, chẳng hạn:

- **PrivateKeyEntry:** private key cùng certificate chain tương ứng. Certificate chứa public key và thông tin nhận diện.
- **TrustedCertificateEntry:** certificate được tin cậy, không chứa private key.

Với Spring Cloud Config dùng RSA, Config Server cần entry có public key để mã hóa. Muốn giải mã tại server, entry phải có private key tương ứng và server phải mở được entry đó.

Keystore có thể được lưu dưới dạng JKS hoặc PKCS12. Spring Cloud Config mặc định `encrypt.keyStore.type` là `jks`; nếu tạo file theo định dạng khác, phải cấu hình type đúng với file đã tạo.

### 2.2. Key pair và certificate

RSA key pair gồm:

- **Public key:** dùng để mã hóa dữ liệu.
- **Private key:** dùng để giải mã dữ liệu đã được mã hóa bằng public key tương ứng.

Certificate X.509 thường gắn public key với thông tin chủ thể và được ký bởi CA hoặc tự ký. Trong bài thực hành, `keytool -genkeypair` tạo key pair và self-signed certificate để phục vụ thử nghiệm.

Không thể suy ra private key từ certificate công khai. Vì vậy, có thể phân phối certificate/public key tới một thành phần chỉ cần mã hóa, trong khi giữ private key tại nơi có trách nhiệm giải mã.

### 2.3. Alias

**Alias** là tên định danh một entry trong keystore. Một keystore có thể chứa nhiều key pair; alias giúp chọn đúng entry.

Ví dụ:

| Alias | Mục đích |
| --- | --- |
| `config-key-2026` | Khóa đang dùng để mã hóa cấu hình mới |
| `config-key-2025` | Khóa cũ còn cần để giải mã ciphertext đã phát hành |
| `config-key-test` | Khóa dùng riêng cho môi trường kiểm thử |

Alias không phải tên file keystore và cũng không phải mật khẩu. Đổi alias trong cấu hình không đổi nội dung khóa; nó chỉ thay entry mà Config Server tìm trong keystore.

### 2.4. Hai loại mật khẩu

Spring Cloud Config có hai cấu hình mật khẩu cần phân biệt:

| Thuộc tính | Vai trò |
| --- | --- |
| `encrypt.keyStore.password` | Mở keystore container |
| `encrypt.keyStore.secret` | Mở private-key entry được chọn; nếu bỏ qua, secret mặc định dùng keystore password |

Tên `secret` trong cấu hình Spring Cloud Config là giá trị bí mật dùng cho key entry. Với JKS, store password và key password có thể khác nhau. Với PKCS12 trên JDK 11 trở lên, `keytool` có thể bỏ qua key password riêng; thực tế nên đặt key password bằng store password để tránh cảnh báo và sai lệch cấu hình.

Không dùng lại các giá trị ví dụ trong tài liệu làm mật khẩu thật. Tạo password riêng, đủ mạnh, lưu trong secret manager hoặc cơ chế credential của nền tảng.

## 3. Mã hóa đối xứng và bất đối xứng trong Config Server

Spring Cloud Config hỗ trợ hai lựa chọn chính:

| Cơ chế | Khóa | Ưu điểm | Lưu ý |
| --- | --- | --- | --- |
| Symmetric | Một secret dùng cho mã hóa và giải mã | Cấu hình đơn giản, dễ triển khai | Thành phần mã hóa và giải mã đều cần giữ cùng secret |
| Asymmetric RSA | Public key mã hóa, private key giải mã | Có thể phân phối public key rộng hơn và giới hạn nơi giữ private key | Cần quản lý key pair, alias, certificate và vòng đời khóa |

Với symmetric key, Config Server dùng `encrypt.key` hoặc biến môi trường `ENCRYPT_KEY`. Với RSA keystore, cấu hình `encrypt.keyStore.*`. `encrypt.key` không thay thế được keystore cho chế độ asymmetric.

Sơ đồ luồng RSA:

~~~mermaid
flowchart LR
    P[Plaintext secret] --> PUB[Public key]
    PUB --> ENC[Encrypt]
    ENC --> C[Ciphertext in Git]
    C --> DEC[Decrypt]
    PRIV[Private key in keystore] --> DEC
    DEC --> OUT[Plaintext for authorized client]
~~~

Nếu Config Server giải mã giá trị trước khi trả cấu hình, private key nằm ở server và client nhận plaintext qua kết nối đã được bảo vệ. Nếu muốn client tự giải mã, cần thiết kế phân phối private key cho client có quyền và cấu hình server không giải mã outgoing properties. Không phát tán private key tới mọi client chỉ để tránh một bước xử lý ở server.

RSA phù hợp để mã hóa các giá trị cấu hình ngắn như password, token hoặc secret key. Kích thước plaintext tối đa phụ thuộc độ dài khóa và padding; không dùng RSA trực tiếp để mã hóa file lớn hoặc toàn bộ tài liệu cấu hình. Với dữ liệu lớn, dùng cơ chế mã hóa dữ liệu phù hợp và bảo vệ khóa dữ liệu bằng một key-management service.

## 4. Tạo keystore bằng keytool

`keytool` được phân phối cùng JDK. Có thể dùng lệnh này để tạo một RSA key pair và certificate tự ký phục vụ thử nghiệm.

### 4.1. Tạo JKS cho bài thực hành

Tạo keystore:

~~~bash
keytool -genkeypair \
  -alias config-key-2026 \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -storetype JKS \
  -keystore config-server.jks \
  -dname "CN=Config Server, OU=Platform, O=Example" \
  -validity 3650
~~~

`keytool` sẽ yêu cầu nhập:

1. Mật khẩu bảo vệ keystore.
2. Mật khẩu bảo vệ private key của alias `config-key-2026`.

Với JKS, có thể dùng hai password khác nhau. Trong thực tế, không đưa password thật vào command line hoặc script được commit. Lệnh trên để `keytool` hỏi password tương tác, giúp tránh lưu trực tiếp giá trị trong lịch sử shell.

### 4.2. Tạo PKCS12

PKCS12 là định dạng trao đổi keystore phổ biến. Có thể tạo file như sau:

~~~bash
keytool -genkeypair \
  -alias config-key-2026 \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -storetype PKCS12 \
  -keystore config-server.p12 \
  -dname "CN=Config Server, OU=Platform, O=Example" \
  -validity 3650
~~~

Với JDK 11 trở lên, PKCS12 có thể không hỗ trợ store password và key password khác nhau; `keytool` có thể cảnh báo rằng password của key bị bỏ qua. Hãy dùng cùng password cho hai mục và cấu hình `encrypt.keyStore.secret` bằng cùng giá trị `encrypt.keyStore.password`, hoặc dùng định dạng/provider có hành vi đã được kiểm chứng nếu chính sách yêu cầu password tách biệt.

### 4.3. Kiểm tra keystore

Liệt kê entry:

~~~bash
keytool -list -v \
  -keystore config-server.jks \
  -storetype JKS
~~~

Kiểm tra các thông tin:

- Alias đúng là `config-key-2026`.
- Entry type là `PrivateKeyEntry`.
- Certificate có public key RSA.
- Ngày hiệu lực certificate và thời hạn sử dụng phù hợp với chính sách.
- Fingerprint của certificate khớp với bản đã được kiểm tra/phê duyệt.

Nếu entry là `trustedCertEntry`, keystore chỉ chứa certificate tin cậy, không có private key để giải mã. Trường hợp đó phù hợp với một thành phần chỉ mã hóa, nhưng không đủ để Config Server giải mã ciphertext.

### 4.4. Xem alias và xuất certificate

Xem thông tin certificate:

~~~bash
keytool -exportcert \
  -alias config-key-2026 \
  -keystore config-server.jks \
  -storetype JKS \
  -rfc \
  -file config-key-2026.crt
~~~

Lệnh xuất certificate/public key, không xuất private key. Có thể dùng certificate để phân phối public key tới thành phần chỉ cần mã hóa hoặc để đối chiếu fingerprint. Không gửi file keystore chứa `PrivateKeyEntry` qua kênh phân phối certificate công khai.

## 5. Cấu hình keystore cho Config Server

Đặt keystore ở vị trí chỉ Config Server truy cập được. Ví dụ local có thể dùng classpath để thử nghiệm; production nên mount file từ secret manager hoặc volume được kiểm soát.

### 5.1. Cấu hình application.yml

Ví dụ dùng JKS:

~~~yaml
encrypt:
  keyStore:
    location: "file:/run/secrets/config-server/config-server.jks"
    password: "${ENCRYPT_KEYSTORE_PASSWORD}"
    alias: "config-key-2026"
    secret: "${ENCRYPT_PRIVATE_KEY_PASSWORD}"
    type: "JKS"
~~~

Ý nghĩa:

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `location` | `file:/run/secrets/config-server/config-server.jks` | Resource path tới keystore |
| `password` | `ENCRYPT_KEYSTORE_PASSWORD` | Password mở keystore |
| `alias` | `config-key-2026` | Alias mặc định được chọn |
| `secret` | `ENCRYPT_PRIVATE_KEY_PASSWORD` | Password mở private-key entry |
| `type` | `JKS` | Định dạng keystore |

Các tên thuộc tính trên thuộc namespace `encrypt.keyStore.*` của Spring Cloud Config. Với PKCS12, thay `location` bằng file `.p12` và `type: PKCS12`; đồng bộ password theo hành vi provider/JDK.

### 5.2. Dùng classpath trong môi trường local

Để thực hành nhanh, có thể đặt keystore ở `src/main/resources` và cấu hình:

~~~yaml
encrypt:
  keyStore:
    location: "classpath:/config-server.jks"
    password: "${ENCRYPT_KEYSTORE_PASSWORD}"
    alias: "config-key-2026"
    secret: "${ENCRYPT_PRIVATE_KEY_PASSWORD}"
    type: "JKS"
~~~

Không nên đóng gói private keystore và password vào JAR dùng chung. Nếu file nằm trong classpath, bất kỳ ai lấy được artifact đều có thể trích xuất file; bảo vệ password ở nơi khác không xóa được rủi ro từ việc phát tán private key quá rộng.

### 5.3. Cung cấp password từ môi trường

Trên Linux/macOS:

~~~bash
export ENCRYPT_KEYSTORE_PASSWORD='load-from-secret-manager'
export ENCRYPT_PRIVATE_KEY_PASSWORD='load-from-secret-manager'
java -jar config-server.jar
~~~

Trên PowerShell:

~~~powershell
$env:ENCRYPT_KEYSTORE_PASSWORD = "load-from-secret-manager"
$env:ENCRYPT_PRIVATE_KEY_PASSWORD = "load-from-secret-manager"
java -jar config-server.jar
~~~

Các chuỗi trên chỉ là placeholder để minh họa cách truyền biến. Trong production, nền tảng nên inject secret từ Vault, Kubernetes Secret được mã hóa, cloud secret manager hoặc cơ chế credential tương đương. Không ghi giá trị thực vào `application.yml`, Git, Dockerfile, image layer hoặc log.

Nếu ứng dụng dùng legacy bootstrap (`spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true`), các thuộc tính mã hóa cần được nạp ở giai đoạn bootstrap theo hướng dẫn của release train đang dùng. Với Config Data import hiện đại, kiểm tra tài liệu Spring Cloud Config đúng phiên bản để đặt thuộc tính ở nguồn được nạp đủ sớm.

## 6. Alias mặc định và nhiều alias

### 6.1. Alias mặc định

`encrypt.keyStore.alias` chỉ định key entry mặc định mà Config Server dùng khi không có chỉ dẫn alias riêng trong ciphertext.

Ví dụ:

~~~yaml
encrypt:
  keyStore:
    alias: "config-key-2026"
~~~

Khi gọi `/encrypt` không chỉ định alias, server dùng alias mặc định này. Nếu alias sai chính tả hoặc không tồn tại trong keystore, quá trình lấy key sẽ thất bại.

### 6.2. Chọn alias cho từng ciphertext

Spring Cloud Config hỗ trợ prefix `{key:alias}` trước ciphertext. Ví dụ:

~~~yaml
payment:
  gateway:
    password: '{cipher}{key:config-key-2025}BASE64_CIPHERTEXT'
database:
  password: '{cipher}{key:config-key-2026}BASE64_CIPHERTEXT'
~~~

Khi giải mã, Config Server đọc alias trong prefix và yêu cầu locator lấy key tương ứng. Điều này cho phép cùng một Config Server giữ nhiều key pair trong một keystore trong giai đoạn chuyển đổi khóa.

Alias được ghi trong ciphertext trở thành một phần metadata cần giữ ổn định. Không xóa alias cũ khi repository vẫn còn giá trị `{cipher}` tham chiếu tới alias đó.

### 6.3. Prefix secret

Ciphertext có thể mang thêm `{secret:...}` để chỉ secret của key entry. Nếu không có prefix secret, default locator dùng keystore password làm secret mặc định theo tài liệu Spring Cloud Config. Nếu sử dụng secret riêng, phải bảo vệ nó và cân nhắc custom `SecretLocator` để quản lý secret theo chính sách của hệ thống.

Không đặt plaintext secret trong repository chỉ vì ciphertext đã được mã hóa. Nếu secret xuất hiện trong `{secret:...}`, nó có thể làm suy yếu lợi ích của việc giữ private-key entry được bảo vệ.

## 7. Mã hóa và giải mã bằng endpoint

Config Server cung cấp `/encrypt` và `/decrypt` khi có cấu hình khóa. Các endpoint này là giao diện quản trị nhạy cảm và phải được bảo vệ bằng authentication, authorization, TLS và network policy.

### 7.1. Mã hóa một giá trị

Gửi plaintext bằng POST:

~~~bash
curl -sS -X POST \
  --data-binary 'change-this-example-password' \
  http://localhost:8888/encrypt
~~~

Response là ciphertext. Nếu Config Server có alias mặc định `config-key-2026`, server dùng alias đó.

Khi cần chọn alias cụ thể, gửi prefix key cùng plaintext theo cú pháp hỗ trợ của Config Server:

~~~bash
curl -sS -X POST \
  --data-binary '{key:config-key-2026}change-this-example-password' \
  http://localhost:8888/encrypt
~~~

Kiểm tra cú pháp alias trên đúng release train đang triển khai. Endpoint `/encrypt` không phải API công khai cho người dùng cuối; chỉ cấp quyền cho pipeline hoặc operator được phép tạo ciphertext.

### 7.2. Giải mã để kiểm tra

~~~bash
curl -sS -X POST \
  --data-binary 'BASE64_CIPHERTEXT' \
  http://localhost:8888/decrypt
~~~

Với giá trị đã mã hóa theo alias cụ thể, kiểm tra ciphertext theo định dạng đầy đủ mà Config Server lưu, bao gồm các prefix `{cipher}` và `{key:...}` nếu có. Chỉ thực hiện việc giải mã trong terminal hoặc môi trường quản trị được bảo vệ; không đưa plaintext vào ticket, chat, log CI hoặc output lưu trữ lâu dài.

### 7.3. Kiểm tra lỗi

Nếu server không giải mã được một giá trị, Config Server loại giá trị ciphertext khỏi property source trả về và thêm một key có prefix `invalid` với giá trị thông báo không áp dụng (thường là `<n/a>`). Cách xử lý này ngăn ciphertext bị ứng dụng hiểu nhầm là password hoặc secret hợp lệ.

Khi gặp lỗi:

- Kiểm tra alias có tồn tại và entry có private key hay không.
- Kiểm tra keystore type và location.
- Kiểm tra store password và key-entry secret.
- Kiểm tra ciphertext có được tạo bằng đúng key pair hay không.
- Kiểm tra prefix `{key:...}` có trỏ tới alias cũ đã bị xóa hay không.

Không sửa bằng cách bỏ prefix hoặc thay ciphertext bằng plaintext ngay trong repository production. Trước tiên phải xác định đúng key và nguồn gốc dữ liệu.

## 8. Lưu ciphertext trong repository cấu hình

Sau khi mã hóa, lưu ciphertext với prefix `{cipher}`.

Trong `application.yml`:

~~~yaml
spring:
  datasource:
    username: app_user
    password: '{cipher}BASE64_CIPHERTEXT'
~~~

Nếu cần chỉ rõ alias:

~~~yaml
spring:
  datasource:
    username: app_user
    password: '{cipher}{key:config-key-2026}BASE64_CIPHERTEXT'
~~~

YAML cần quote giá trị bắt đầu bằng `{cipher}` để tránh parser hiểu nó như flow mapping. Với file `.properties`, giá trị `{cipher}...` không cần quote:

~~~properties
spring.datasource.username=app_user
spring.datasource.password={cipher}BASE64_CIPHERTEXT
~~~

Không quote giá trị ciphertext trong `.properties` nếu phiên bản Config Server đang dùng yêu cầu prefix `{cipher}` ở đầu value; dấu quote có thể khiến quá trình nhận diện/decrypt không hoạt động như mong đợi.

### 8.1. Config Server giải mã trước khi trả client

Theo mặc định, Config Server phát hiện giá trị bắt đầu bằng `{cipher}`, giải mã trước khi gửi property source qua HTTP. Git giữ ciphertext ở trạng thái lưu trữ; client được cấp quyền nhận giá trị plaintext sau khi server giải mã.

Điều này bảo vệ secret ở trạng thái lưu trong repository, nhưng không thay thế:

- TLS giữa Config Client và Config Server.
- Authentication/authorization cho Config Server.
- Phân quyền repository và bảo vệ branch.
- Bảo vệ log, heap dump, actuator endpoint và biến môi trường trên client.
- Quản lý private key và password ở server.

Nếu Config Server giải mã, mọi client được phép lấy cấu hình có thể nhận plaintext. Hãy cấp quyền theo application và môi trường, không coi việc ciphertext nằm trong Git là lý do để chia sẻ cấu hình rộng rãi.

### 8.2. Client tự giải mã

Một kiến trúc khác là Config Server trả ciphertext cho client, để client giữ private key và giải mã cục bộ. Khi đã cấu hình `encrypt.*` để server phục vụ endpoint mã hóa/giải mã nhưng muốn giữ ciphertext trong response, đặt:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
~~~

Tài liệu Spring Cloud Config yêu cầu đặt thuộc tính `spring.cloud.config.server.encrypt.enabled=false` trong `bootstrap.yml` hoặc `bootstrap.properties` cho chế độ serving encrypted properties. Chỉ dùng mô hình này khi có kế hoạch phân phối private key, alias và password tới từng client được phép; việc này làm tăng số nơi cần bảo vệ khóa.

## 9. Quản lý vòng đời alias và xoay vòng khóa

Xoay vòng khóa không chỉ là tạo alias mới rồi xóa alias cũ. Mỗi ciphertext đã phát hành phải tiếp tục giải mã được trong suốt thời gian chuyển đổi.

### 9.1. Quy trình rotation có thể rollback

Giả sử alias hiện tại là `config-key-2025` và alias mới là `config-key-2026`.

1. Tạo key pair mới với alias `config-key-2026`.
2. Cập nhật keystore trên tất cả Config Server instance để chứa cả alias cũ và alias mới.
3. Xác minh cả hai alias đều có thể lấy key và giải mã ciphertext thử nghiệm.
4. Chuyển alias mặc định sang `config-key-2026` cho các giá trị mới.
5. Mã hóa lại từng property cần chuyển và lưu prefix `{key:config-key-2026}`.
6. Deploy repository và xác nhận mọi Config Server replica trả cấu hình thành công.
7. Kiểm tra không còn ciphertext nào tham chiếu `config-key-2025`.
8. Sau thời gian rollback đã thống nhất, mới loại alias cũ khỏi keystore.

### 9.2. Sơ đồ chuyển đổi

~~~mermaid
flowchart TD
    A[Keystore: old alias] --> B[Add new alias]
    B --> C[Both aliases available on all servers]
    C --> D[Encrypt new values with new alias]
    D --> E[Update ciphertext references]
    E --> F[Verify every property decrypts]
    F --> G{Any old alias references?}
    G -->|Yes| E
    G -->|No| H[Keep rollback window]
    H --> I[Remove old alias]
~~~

Nếu có sự cố sau bước chuyển đổi, khôi phục ciphertext dùng alias cũ trong khi cả hai alias vẫn còn trong keystore. Không xóa alias cũ trước khi hoàn tất xác minh và hết thời gian rollback.

### 9.3. Khi nào cần rotate?

Không nhất thiết xoay khóa theo lịch ngắn nếu key chỉ dùng để mã hóa vài byte cấu hình và được bảo vệ tốt. Tuy nhiên, phải thay khóa khi có dấu hiệu lộ private key/password, mất quyền kiểm soát keystore, thay đổi chính sách mật mã hoặc khi quy định tổ chức yêu cầu.

Nếu private key đã bị lộ, coi ciphertext được mã hóa bằng key đó có nguy cơ bị giải mã. Chỉ đổi alias cho các giá trị mới không làm ciphertext cũ an toàn trở lại; cần mã hóa lại bằng key mới và đánh giá việc thay secret thực tế liên quan.

## 10. Bảo vệ keystore và password trong production

### 10.1. Vị trí file

- Dùng `file:` trỏ tới volume hoặc secret mount được bảo vệ trong production.
- Hạn chế quyền đọc file cho user chạy Config Server.
- Không đóng gói private keystore vào JAR, Docker image hoặc repository source.
- Không mount keystore vào client không cần giải mã.
- Backup keystore và password theo quy trình backup secret; kiểm thử khả năng khôi phục.

### 10.2. Password

- Lấy password từ secret manager hoặc nền tảng quản lý credential.
- Không ghi password trong Git, CI variable dạng plaintext, Dockerfile hoặc log.
- Giới hạn quyền đọc secret theo workload identity/service account.
- Có quy trình thay password và kiểm thử khôi phục trước khi triển khai.
- Với PKCS12, xác minh hành vi của JDK/provider; nếu key password phải bằng store password, quản lý chúng như cùng một secret thay vì tạo hai giá trị gây nhầm lẫn.

### 10.3. Endpoint và mạng

- Bảo vệ `/encrypt` và `/decrypt` bằng Spring Security.
- Chỉ cho phép pipeline hoặc operator được cấp quyền gọi endpoint.
- Chỉ expose trên management/network segment nội bộ.
- Dùng HTTPS/TLS; không gửi plaintext qua HTTP không bảo vệ.
- Không ghi request/response body của endpoint vào access log hoặc tracing.
- Không dùng endpoint decrypt trong health check hoặc luồng nghiệp vụ công khai.

### 10.4. Public key và private key

Nếu chỉ mã hóa ở một thành phần và giải mã ở một thành phần khác:

- Phân phối public key/certificate cho bên mã hóa.
- Giữ private key trong keystore tại thành phần giải mã.
- Xác minh fingerprint certificate trước khi phân phối.
- Thu hồi và thay key khi có sự cố.

Config Server có thể chỉ cần public key nếu nó chỉ thực hiện mã hóa và một thành phần khác giữ private key để giải mã. Nếu Config Server cần tự giải mã property trước khi trả client, nó phải có quyền truy cập private key tương ứng.

## 11. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Config Server không khởi động | Sai location hoặc không mở được keystore | Kiểm tra resource path, mount và quyền đọc file |
| `UnrecoverableKeyException` | Store password hoặc key-entry secret sai | Kiểm tra `password`, `secret` và entry tương ứng |
| Alias không tồn tại | Alias trong cấu hình/ciphertext sai hoặc chưa được deploy | Chạy `keytool -list -v` và đối chiếu alias |
| Có thể encrypt nhưng không decrypt | Keystore chỉ có certificate/public key hoặc private key/password không đúng | Xác minh entry là `PrivateKeyEntry` và kiểm tra private-key access |
| Ciphertext cũ không giải mã được | Alias cũ bị xóa hoặc key pair đã thay | Khôi phục alias/key cũ từ backup và xác định ciphertext đang tham chiếu |
| `/encrypt` trả lỗi | Không có encryptor/key hợp lệ hoặc request sai | Kiểm tra cấu hình keystore, alias và log đã che secret |
| Client nhận `invalid.*` | Config Server không giải mã được property | Kiểm tra key, alias, password, ciphertext và log server |
| PKCS12 cảnh báo key password bị bỏ qua | Provider/JDK không hỗ trợ password riêng cho key entry | Đồng nhất store/key password và cấu hình `secret` phù hợp |
| YAML không giải mã giá trị | `{cipher}` không được quote hoặc cú pháp/prefix bị thay đổi | Kiểm tra value trong YAML và format ciphertext |

Không in toàn bộ cấu hình `encrypt.*` hoặc password ra log để chẩn đoán. Có thể log tên alias, loại keystore, trạng thái load và fingerprint certificate sau khi đã xác định mức thông tin đó được phép công bố.

## 12. Bài tập thực hành

### Bài 1 — Tạo và kiểm tra keystore

1. Dùng `keytool -genkeypair` tạo một JKS với alias `config-key-lab`.
2. Chạy `keytool -list -v`.
3. Xác nhận entry là `PrivateKeyEntry`.
4. Ghi lại fingerprint certificate và thời hạn.
5. Thử mở keystore với password sai và quan sát lỗi.

### Bài 2 — Cấu hình Config Server

1. Cấu hình `encrypt.keyStore.location`, `password`, `alias`, `secret`, `type`.
2. Khởi động Config Server.
3. Gửi plaintext thử nghiệm tới `/encrypt`.
4. Gửi ciphertext tới `/decrypt`.
5. Xác nhận plaintext khớp dữ liệu ban đầu.

### Bài 3 — Thử alias thứ hai

1. Thêm key pair với alias `config-key-next` vào keystore.
2. Mã hóa một giá trị với prefix `{key:config-key-next}`.
3. Lưu ciphertext có alias mới vào file cấu hình thử nghiệm.
4. Kiểm tra Config Server có thể giải mã cả alias mặc định và alias mới.

### Bài 4 — Xoay vòng khóa

1. Giữ ciphertext cũ dùng alias `config-key-lab`.
2. Chuyển alias mặc định sang `config-key-next`.
3. Mã hóa lại một property và thay prefix alias.
4. Kiểm tra mọi property vẫn đọc được.
5. Chỉ xóa alias cũ sau khi xác nhận không còn ciphertext tham chiếu và hết thời gian rollback.

**Tiêu chí hoàn thành:** bạn có thể giải thích mỗi password bảo vệ phần nào, xác định alias mà một ciphertext cần, chứng minh Config Server mã hóa/giải mã được bằng key pair tương ứng và xoay khóa mà không làm mất khả năng giải mã dữ liệu đã phát hành.

## 13. Tổng kết

Keystore là container lưu key pair và certificate; alias chọn entry cụ thể; `encrypt.keyStore.password` mở keystore và `encrypt.keyStore.secret` mở private-key entry. Với RSA, public key dùng để mã hóa, private key dùng để giải mã. Config Server có thể dùng alias mặc định hoặc alias được chỉ định trong prefix `{key:alias}` của ciphertext.

Quy trình an toàn gồm tạo keystore, xác minh `PrivateKeyEntry`, mount file và password từ nguồn secret được bảo vệ, kiểm tra `/encrypt`/`/decrypt`, lưu ciphertext với prefix `{cipher}`, rồi xoay vòng alias theo giai đoạn có thể rollback. Không commit private keystore hoặc password, không mở endpoint mã hóa/giải mã công khai và không xóa alias cũ khi repository còn ciphertext phụ thuộc vào nó.

## Tài liệu tham khảo

- [Spring Cloud Config — Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html): symmetric key, RSA keystore, location, password, alias và type.
- [Spring Cloud Config — Creating a Key Store for Testing](https://docs.spring.io/spring-cloud-config/reference/server/creating-a-key-store-for-testing.html): tạo key pair bằng `keytool`, cấu hình keystore và lưu ý PKCS12 trên JDK 11 trở lên.
- [Spring Cloud Config — Using Multiple Keys and Key Rotation](https://docs.spring.io/spring-cloud-config/reference/server/using-multiple-keys-and-key-rotation.html): prefix `{key:alias}`, secret locator và thay đổi alias khi xoay khóa.
- [Spring Cloud Config — Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html): giữ ciphertext trong response để client tự giải mã.
- [Java Keytool Documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): các lệnh quản lý keystore, key pair, certificate và alias.

Các thuộc tính và hành vi keystore cần được đối chiếu với release train Spring Cloud, JDK và provider đang triển khai. Ví dụ JKS/PKCS12 trong bài nhằm minh họa cấu hình; hãy kiểm thử việc mở key entry và giải mã bằng đúng runtime production trước khi phát hành.

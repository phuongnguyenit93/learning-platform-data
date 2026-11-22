# Không giải mã được giá trị cipher

Khi Spring Cloud Config Server đọc một property có tiền tố `{cipher}`, server sẽ thử giải mã trước khi trả cấu hình cho Config Client. Nếu không giải mã được, server loại giá trị cipher khỏi property source và thêm một key có tiền tố `invalid.`, thường mang giá trị `<n/a>`. Ứng dụng có thể vẫn khởi động nhưng nhận giá trị mặc định từ nguồn cấu hình thấp hơn, hoặc thiếu hẳn một property bắt buộc.

Sự cố thường xuất phát từ key mã hóa không khớp, keystore/alias sai, ciphertext bị thay đổi khi copy, cú pháp file cấu hình không đúng, hoặc cấu hình đang dùng chế độ giải mã ở phía khác với dự kiến. Bài này hướng dẫn xác định đúng lớp gây lỗi, kiểm tra khóa và ciphertext, đọc phản hồi Config Server, khôi phục cấu hình an toàn và phòng ngừa tái diễn.

Bài học thuộc chương **Chẩn đoán sự cố** của module **SPRING_CLOUD_CORE**. Phạm vi tập trung vào encryption/decryption của Spring Cloud Config, gồm symmetric key, RSA keystore, tiền tố `{cipher}`, endpoint `/encrypt` và `/decrypt`, nhiều key/rotation, cấu hình Config Server/Client, kiểm thử và bảo vệ secret.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích nơi Spring Cloud Config giải mã property và ý nghĩa của tiền tố `{cipher}`.
- Nhận biết dấu hiệu giải mã thất bại qua property `invalid.*`.
- Phân biệt lỗi ciphertext, lỗi key, lỗi keystore và lỗi cấu hình phía server/client.
- Kiểm tra symmetric key `encrypt.key` và RSA keystore `encrypt.keyStore.*`.
- Kiểm tra alias của key qua `{key:alias}` và `TextEncryptorLocator`.
- Dùng `/decrypt` để xác minh ciphertext bằng chính cấu hình key đang chạy.
- Sửa lỗi quote, ký tự đặc biệt, Base64 bị cắt hoặc bị URL decode.
- Phân biệt server-side decryption với client-side decryption.
- Xây dựng quy trình key rotation mà vẫn đọc được các ciphertext cũ trong giai đoạn chuyển đổi.
- Viết kiểm thử tích hợp để xác nhận vòng đời encrypt/decrypt.
- Bảo vệ endpoint và dữ liệu nhạy cảm trong log, CI và repository.

## 2. Cơ chế giải mã của Spring Cloud Config

Config Server có thể lưu ciphertext trong Git hoặc backend cấu hình. Property được mã hóa thường bắt đầu bằng `{cipher}`. Khi Config Server xử lý Environment response, nó nhận diện tiền tố này và giải mã giá trị trước khi gửi cho client qua HTTP.

Ví dụ file `application.yml` trong repository:

~~~yaml
spring:
  datasource:
    username: app_user
    password: '{cipher}BASE64_CIPHERTEXT'
~~~

Giá trị `BASE64_CIPHERTEXT` chỉ là placeholder minh họa, không phải ciphertext dùng được. YAML cần đặt toàn bộ giá trị trong dấu nháy đơn vì chuỗi bắt đầu bằng `{` có thể được parser hiểu như flow mapping.

Trong file `.properties`, không đặt dấu nháy quanh giá trị cipher:

~~~properties
spring.datasource.username=app_user
spring.datasource.password={cipher}BASE64_CIPHERTEXT
~~~

Spring Cloud Config quy định encrypted value trong `.properties` không được bọc trong quote; nếu có quote, server có thể không nhận diện và giải mã giá trị. Với YAML, quote là cần thiết để giữ nguyên chuỗi `{cipher}...`.

### 2.1. Server-side decryption mặc định

Trong cấu hình thông thường, Config Server giải mã property trước khi gửi cho Config Client:

~~~mermaid
flowchart LR
    A[Git / Config repository] --> B["{cipher} ciphertext"]
    B --> C[Config Server]
    K[encrypt.key or keystore] --> C
    C --> D[Decrypt property]
    D --> E[Plain value in Environment response]
    E --> F[Config Client]
~~~

Client nhận giá trị đã giải mã. Client không cần giữ private key chỉ để đọc cấu hình trong mô hình này. Key giải mã tập trung ở Config Server, vì vậy server phải được bảo vệ chặt chẽ.

### 2.2. Điều gì xảy ra khi giải mã thất bại?

Nếu Config Server không giải mã được một property, nó loại property cipher khỏi source và thêm key có tiền tố `invalid.`. Ví dụ:

~~~json
{
  "propertySources": [
    {
      "name": "application-production.yml",
      "source": {
        "invalid.spring.datasource.password": "<n/a>"
      }
    },
    {
      "name": "application.yml",
      "source": {
        "spring.datasource.password": "fallback-value"
      }
    }
  ]
}
~~~

Trong ví dụ, Config Server không trả ciphertext như một password. Client có thể lấy `fallback-value` từ source thấp hơn nếu property đó tồn tại. Vì vậy, ứng dụng có thể không crash nhưng kết nối database vẫn thất bại hoặc vô tình dùng giá trị cũ.

Khi thấy `invalid.<property>` trong Environment response, hãy coi đó là lỗi giải mã cần xử lý. Không tắt cơ chế prefix-invalid chỉ để response trông có vẻ bình thường; nếu tắt, ciphertext có thể được chuyển tiếp tới client như một giá trị property thông thường.

Property điều khiển hành vi này là:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          prefix-invalid-properties: true
~~~

Giữ hành vi mặc định bật trong hầu hết hệ thống. Chỉ thay đổi khi đã hiểu rõ hậu quả và có cơ chế phát hiện lỗi khác.

## 3. Phân biệt lỗi ở Config Server và Config Client

Trước khi thay key hoặc tạo lại ciphertext, xác định nơi đang thực hiện giải mã.

| Mô hình | Nơi giải mã | Thành phần cần key |
| --- | --- | --- |
| Server-side decryption | Config Server | Config Server |
| Client-side decryption | Config Client | Từng client cần giải mã |

Server-side decryption là mô hình thông thường. Nếu server có key phù hợp, Environment response chứa plain value.

Nếu muốn client tự giải mã, Config Server phải tắt giải mã outgoing properties bằng:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
~~~

Khi đó client cần được cấu hình key/decryption support tương ứng. Cấu hình key ở client mà server vẫn giải mã outgoing properties không phải là lý do để client tiếp tục giải mã lần thứ hai.

Nếu response từ Config Server vẫn chứa `{cipher}...`, kiểm tra mô hình client-side decryption, property `spring.cloud.config.server.encrypt.enabled` và key tại client. Nếu response có `invalid.<property>`, lỗi xảy ra trong bước giải mã mà Config Server đang thực hiện.

## 4. Nguyên nhân thường gặp

| Nguyên nhân | Dấu hiệu | Hướng kiểm tra |
| --- | --- | --- |
| Symmetric key không khớp | `/decrypt` thất bại với ciphertext cũ; log báo lỗi decrypt | So sánh nguồn cấp `encrypt.key` ở đúng Config Server instance/profile |
| RSA private key hoặc alias sai | Keystore mở được nhưng không tìm thấy key phù hợp hoặc decrypt lỗi | Kiểm tra `encrypt.keyStore.location`, alias và private key entry |
| Ciphertext bị cắt hoặc thay đổi | Base64 decode lỗi, padding/block error hoặc decrypt thất bại | So sánh nguyên văn giá trị trong repository với bản tạo ra từ `/encrypt` |
| Quote sai trong `.properties` | Property không được nhận diện là cipher | Bỏ quote quanh `{cipher}...` trong `.properties` |
| YAML không giữ chuỗi nguyên vẹn | Parser hiểu `{cipher}` thành cấu trúc YAML hoặc giá trị khác dự kiến | Quote toàn bộ giá trị cipher trong YAML |
| Thiếu tiền tố `{cipher}` | Giá trị được chuyển tiếp như chuỗi thông thường | Kiểm tra marker ở đầu giá trị |
| Sai key alias sau rotation | Cipher có `{key:oldAlias}` nhưng server chỉ còn key alias mới | Khôi phục alias cũ hoặc migrate ciphertext sang alias mới |
| Khác chế độ giải mã | Server trả cipher cho client hoặc server đã giải mã nhưng client lại xử lý tiếp | Xác minh `spring.cloud.config.server.encrypt.enabled` và vị trí key |
| Key không được nạp đúng phase | Config Server chạy bootstrap legacy nhưng key đặt trong file/property source không được nạp ở bootstrap | Đặt `encrypt.key` trong `bootstrap.properties` khi dùng bootstrap legacy |
| Ký tự `+`, `/`, `=` bị biến đổi | Ciphertext gửi qua HTTP khác giá trị lưu trong Git | Gửi body dạng `text/plain` hoặc dùng `--data-urlencode` đúng cách |
| File plain-text endpoint không được giải mã | YAML/JSON/properties resource trả cipher thô | Kiểm tra `plainTextEncrypt` và loại extension |
| Crypto policy/runtime không tương thích | Lỗi cụ thể như `Illegal key size` hoặc provider không hỗ trợ transformation | Kiểm tra JDK, security provider và thuật toán đã dùng |

Không kết luận chỉ từ một exception. Cùng một thông báo bề mặt có thể bắt nguồn từ key sai, ciphertext hỏng hoặc key alias không được tìm thấy. Dùng `/decrypt` trên đúng instance và đúng cấu hình để thu hẹp phạm vi.

## 5. Kiểm tra symmetric key

Với symmetric encryption, Config Server dùng cùng một secret key để mã hóa và giải mã. Cấu hình phổ biến là:

~~~yaml
encrypt:
  key: ${ENCRYPT_KEY}
~~~

Hoặc đặt biến môi trường `ENCRYPT_KEY` trong secret manager/container environment. Không commit key thật vào Git hoặc file cấu hình dùng chung.

### 5.1. Kiểm tra đúng giá trị và đúng instance

Trong môi trường có nhiều Config Server replica, mọi instance có thể cần cùng key để giải mã cùng ciphertext. Nếu một replica dùng key mới và replica khác vẫn dùng key cũ, kết quả sẽ không ổn định theo load balancer.

Kiểm tra:

- Secret manager đang cấp đúng version cho tất cả replica.
- Biến môi trường `ENCRYPT_KEY` có được inject vào process Config Server không.
- Không có profile hoặc environment variable khác override key.
- Pod/container đã được restart sau khi thay secret nếu runtime không tự reload biến môi trường.
- Các instance đang phục vụ cùng một phiên bản key trong thời gian rollout.

Không in key vào log để so sánh. Có thể so sánh secret version/secret reference hoặc fingerprint được tính trong quy trình quản lý bí mật nội bộ, nhưng không lưu fingerprint yếu có thể hỗ trợ dò đoán một key entropy thấp.

### 5.2. Trường hợp dùng bootstrap legacy

Nếu Config Server có `spring-cloud-starter-bootstrap` hoặc bật `spring.cloud.bootstrap.enabled=true`, tài liệu Spring Cloud Config yêu cầu `encrypt.key` được đặt trong `bootstrap.properties` để key có mặt trong bootstrap phase.

Ví dụ:

~~~properties
encrypt.key=${ENCRYPT_KEY}
~~~

Đặt trong `bootstrap.properties` của Config Server khi ứng dụng thật sự dùng bootstrap legacy. Với ứng dụng chỉ dùng Config Data, hãy cấu hình key ở property source được nạp trước khi encryption subsystem khởi tạo; xác minh bằng integration test và không copy máy móc hướng dẫn bootstrap cũ sang ứng dụng hiện đại.

### 5.3. Kiểm tra mà không làm lộ key

Không dùng endpoint Actuator `env` để dump `encrypt.key`. Nếu cần xác nhận cấu hình đã có mặt, kiểm tra trạng thái secret reference trong deployment hoặc kiểm tra bean/configuration state bằng test không trả giá trị secret.

Nếu key được lấy từ secret manager, kiểm tra quyền đọc secret, version alias và thời điểm rotate. Một Config Server có thể khởi động được nhưng key không được nạp do secret provider trả về giá trị rỗng hoặc quyền truy cập không đủ.

## 6. Kiểm tra RSA keystore

Với asymmetric encryption, Config Server dùng public key để mã hóa và private key để giải mã. `encrypt.key` chỉ dành cho symmetric key; không dùng nó để cấu hình RSA key pair.

Ví dụ cấu hình keystore:

~~~yaml
encrypt:
  keyStore:
    location: classpath:/config-server-keys.jks
    password: ${CONFIG_KEYSTORE_PASSWORD}
    alias: config-encryption
    secret: ${CONFIG_PRIVATE_KEY_PASSWORD}
    type: jks
~~~

Các property chính:

| Property | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| `encrypt.keyStore.location` | Resource chứa keystore | Sai path, file không được đóng gói, quyền đọc không đủ |
| `encrypt.keyStore.password` | Mật khẩu mở keystore | Sai password hoặc secret chưa được inject |
| `encrypt.keyStore.alias` | Alias của key trong keystore | Alias không tồn tại hoặc trỏ tới certificate-only entry |
| `encrypt.keyStore.secret` | Password của private key entry nếu khác store password | Password sai hoặc không phù hợp format keystore |
| `encrypt.keyStore.type` | Loại keystore; mặc định JKS | File PKCS12 nhưng cấu hình type không đúng |

### 6.1. Liệt kê alias bằng keytool

Chạy `keytool` trên keystore của môi trường kiểm thử hoặc trên bản sao được phép kiểm tra:

~~~bash
keytool -list -v \
  -keystore config-server-keys.jks \
  -storetype JKS
~~~

Lệnh yêu cầu store password. Kiểm tra:

- Alias được cấu hình có tồn tại.
- Entry là `PrivateKeyEntry` nếu server phải giải mã bằng private key.
- Certificate/public key tương ứng là key đã dùng để mã hóa ciphertext.
- Keystore type đúng với file thực tế.

Không xuất private key hoặc đưa file keystore production vào ticket/log. Chỉ chia sẻ metadata không nhạy cảm như alias, loại entry, validity và fingerprint certificate khi được phép.

### 6.2. JKS và PKCS12

Một số keystore PKCS12 không hỗ trợ password riêng cho private key entry theo cách giống JKS. Với JDK mới, `keytool` có thể cảnh báo rằng `keypass` khác `storepass` bị bỏ qua. Nếu dùng PKCS12, kiểm tra password thực tế và cấu hình `encrypt.keyStore.type: PKCS12`.

Không đổi loại keystore hoặc alias chỉ để hết lỗi. Trước hết xác minh file, password, alias và private key entry. Nếu cần chuyển đổi, tạo keystore mới trong quy trình kiểm soát khóa, kiểm tra decrypt bằng ciphertext thử nghiệm rồi mới rollout.

### 6.3. Mã hóa bằng public key, giải mã bằng private key

Trong mô hình RSA:

- Công cụ mã hóa cần public key đúng với private key đang giữ.
- Config Server cần private key tương ứng nếu server-side decryption được bật.
- Nếu Config Server chỉ có public key, nó có thể mã hóa nhưng không thể giải mã outgoing properties bằng private key bị thiếu.

Nếu ciphertext được tạo bởi public key từ một cặp khác, private key hiện tại không thể giải mã. Việc alias tồn tại không chứng minh public/private key thuộc cùng một cặp; đối chiếu fingerprint certificate/public key trong quy trình quản lý khóa.

## 7. Kiểm tra alias và nhiều key

Khi cần giữ nhiều key cùng lúc, Spring Cloud Config hỗ trợ metadata prefix trước ciphertext:

~~~yaml
spring:
  datasource:
    password: '{cipher}{key:config-2026}BASE64_CIPHERTEXT'
~~~

`{key:config-2026}` yêu cầu `TextEncryptorLocator` tìm encryptor/key alias tương ứng. Với keystore, default locator dùng alias này để chọn key. Alias phải tồn tại trên Config Server đang xử lý request.

### 7.1. Default locator và custom locator

Default `TextEncryptorLocator` không tự phân chia key theo từng application/profile; mặc định các phép mã hóa dùng cùng key. Nếu cần key riêng cho từng application hoặc profile, cung cấp bean `TextEncryptorLocator` có logic chọn encryptor phù hợp.

Ví dụ về cách tổ chức:

| Cipher metadata | Key được chọn |
| --- | --- |
| `{cipher}...` | Key mặc định |
| `{cipher}{key:config-2025}...` | Alias `config-2025` |
| `{cipher}{key:config-2026}...` | Alias `config-2026` |

Không tự tạo alias prefix nếu Config Server chưa được cấu hình locator tương ứng. Một ciphertext có `{key:config-2026}` nhưng keystore chỉ có `config-2025` sẽ không giải mã được.

### 7.2. Secret trong prefix

Config Server cũng hỗ trợ `{secret:...}` prefix. Nếu không cung cấp secret riêng, default locator dùng keystore password. Nếu cung cấp secret, tài liệu khuyến nghị dùng `SecretLocator` tùy chỉnh để xử lý secret này an toàn.

Tránh nhúng secret trực tiếp vào file cấu hình dùng chung hoặc log. Nếu cần secret theo tenant/application, đưa việc phân phối secret vào secret manager và custom locator có kiểm thử rõ ràng.

## 8. Quy trình chẩn đoán theo từng bước

Thực hiện lần lượt để xác định lỗi nằm ở dữ liệu mã hóa, key đang chạy hay cách Config Server phục vụ property.

### Bước 1 — Xác định application, profile và label

Ghi lại đầy đủ:

- `spring.application.name` mà Config Client gửi.
- Active profile theo đúng thứ tự.
- Git label/branch/commit được Config Server chọn.
- Property source chứa key bị lỗi.
- Config Server replica đã xử lý request.

Ciphertext có thể được tạo theo key riêng cho application/profile. Nếu request đi tới sai application hoặc profile, Config Server có thể chọn sai `TextEncryptor` khi dùng custom locator.

### Bước 2 — Kiểm tra Environment response

Gọi đúng endpoint Environment của Config Server trong mạng quản trị:

~~~bash
curl -fsS \
  "https://config.internal/orders-service/production/main" \
  -o config-response.json
~~~

Đường dẫn ví dụ có dạng `/{application}/{profile}/{label}`. Không in toàn bộ response vào terminal hoặc CI log vì response có thể chứa nhiều giá trị nhạy cảm.

Nếu có `jq`, chỉ liệt kê tên source và key lỗi:

~~~bash
jq -r '
  .propertySources[] as $source
  | ($source.source // {} | keys[])
  | select(startswith("invalid."))
  | "\($source.name): \(.)"
' config-response.json
~~~

Kết quả như `invalid.spring.datasource.password` cho biết Config Server không giải mã được key đó. Kiểm tra cả property source cấp application và profile-specific source; một source thấp hơn có thể đang cung cấp giá trị fallback.

Sau khi chẩn đoán, xóa file response khỏi workspace tạm hoặc bảo đảm nó được bảo vệ như dữ liệu cấu hình nhạy cảm.

### Bước 3 — Thử giải mã bằng đúng Config Server instance

Lấy phần ciphertext sau tiền tố `{cipher}` từ repository, không lấy giá trị đã bị biến đổi trong log. Gửi ciphertext tới `/decrypt` của chính replica đang xử lý request:

~~~bash
curl -fsS \
  -H "Content-Type: text/plain" \
  --data-binary "BASE64_CIPHERTEXT" \
  https://config.internal/decrypt
~~~

Không gửi tiền tố `{cipher}` trong body. Nếu ciphertext có metadata key như `{key:config-2026}`, giữ metadata cần thiết khi kiểm tra key selection.

Nếu `/decrypt` trả plaintext đúng, key và ciphertext có thể giải mã được trên instance đó; chuyển sang kiểm tra cú pháp property source, chế độ decryption và request application/profile. Nếu `/decrypt` thất bại, tiếp tục kiểm tra key, alias, keystore và tính toàn vẹn ciphertext.

Endpoint `/decrypt` có thể trả secret dưới dạng plaintext. Chỉ gọi từ mạng quản trị, dùng quyền phù hợp và không lưu body/response vào log. Không bật endpoint này công khai để tiện debug.

### Bước 4 — Kiểm tra cách gửi body và ký tự đặc biệt

Ciphertext Base64 có thể chứa `+`, `/` và `=`. Nếu gửi dưới dạng `application/x-www-form-urlencoded`, dấu `+` có thể bị hiểu thành khoảng trắng. Hãy dùng `Content-Type: text/plain` cùng `--data-binary`, hoặc `--data-urlencode` theo hướng dẫn của Spring Cloud Config.

Khi mã hóa plaintext bằng `/encrypt`:

~~~bash
curl -fsS \
  -H "Content-Type: text/plain" \
  --data-binary "VALUE_TO_ENCRYPT" \
  https://config.internal/encrypt
~~~

Nếu dùng `curl --data-urlencode`, tài liệu hướng dẫn đặt `=` trước nội dung được encode. Dùng `-s` hoặc `-fsS` để không vô tình copy thống kê curl vào ciphertext. Luôn lưu đúng response body, không copy khoảng trắng, dấu nháy hoặc dòng thông báo từ terminal.

### Bước 5 — Đối chiếu key configuration

Với symmetric key, xác minh `ENCRYPT_KEY`/`encrypt.key` được nạp trên đúng replica. Với RSA, xác minh:

1. Keystore path tồn tại trong runtime container.
2. Store password mở được keystore.
3. Alias có mặt.
4. Alias trỏ tới private key entry nếu server phải giải mã.
5. Private key password đúng.
6. Ciphertext được tạo bằng public key tương ứng.

Nếu dùng `{key:alias}`, xác minh alias được truyền đúng và locator có thể tìm thấy nó. Không đổi key trước khi xác định ciphertext được tạo bởi key nào.

### Bước 6 — Kiểm tra format trong repository

Đối chiếu file nguồn:

- YAML: quote toàn bộ giá trị `{cipher}...`.
- `.properties`: không quote giá trị cipher.
- Ciphertext không bị xuống dòng, cắt ngắn hoặc có dấu cách ở đầu/cuối.
- Tiền tố `{cipher}` nằm ngay đầu giá trị.
- Nếu dùng key alias, metadata `{key:alias}` nằm ngay sau `{cipher}`.

Nếu file được sinh bởi pipeline, kiểm tra bước template/render có escape hoặc thay thế ký tự đặc biệt hay không. Không sửa thủ công chỉ trên một Config Server instance; sửa source of truth rồi triển khai lại.

### Bước 7 — Xác nhận mô hình giải mã

Kiểm tra `spring.cloud.config.server.encrypt.enabled`:

- `true` hoặc không tắt: Config Server giải mã outgoing properties theo cấu hình hiện hành.
- `false`: Config Server có thể giữ ciphertext để client giải mã cục bộ; client phải có key/decryption support tương ứng.

Nếu lấy cấu hình từ plain-text resource endpoint, decryption bị tắt mặc định. Chỉ bật `spring.cloud.config.server.encrypt.plainTextEncrypt=true` cùng `spring.cloud.config.server.encrypt.enabled=true` nếu cần giải mã property trong các file YAML, JSON hoặc `.properties` được phục vụ qua endpoint đó.

### Bước 8 — So sánh tất cả replica

Gọi `/decrypt` trên từng replica bằng cùng một ciphertext thử nghiệm không nhạy cảm. Nếu kết quả khác nhau, so sánh secret version, keystore version, alias và deployment revision. Đừng dùng một lần request thành công qua load balancer để kết luận tất cả replica đều đồng bộ.

## 9. Cấu hình và định dạng đúng

### 9.1. YAML

~~~yaml
spring:
  datasource:
    password: '{cipher}BASE64_CIPHERTEXT'
~~~

Quote đơn giữ nguyên `{cipher}` như một scalar YAML. Không thêm quote lồng bên trong ciphertext và không chèn khoảng trắng vào Base64.

### 9.2. Properties

~~~properties
spring.datasource.password={cipher}BASE64_CIPHERTEXT
~~~

Không dùng:

~~~properties
spring.datasource.password="{cipher}BASE64_CIPHERTEXT"
~~~

Dấu quote trong `.properties` trở thành một phần giá trị và có thể khiến Config Server không nhận diện được marker.

### 9.3. Tạo ciphertext mới

Dùng `/encrypt` trên đúng Config Server/key sẽ giải mã ở runtime. Ví dụ:

~~~bash
curl -fsS \
  -H "Content-Type: text/plain" \
  --data-binary "NEW_VALUE_TO_ENCRYPT" \
  https://config.internal/encrypt
~~~

Lưu response body và thêm tiền tố `{cipher}` khi cập nhật repository. Nếu cần key alias:

~~~yaml
spring:
  datasource:
    password: '{cipher}{key:config-2026}BASE64_CIPHERTEXT'
~~~

Sau khi cập nhật, gọi Environment endpoint và xác minh không còn `invalid.<property>`. Không đưa plaintext trả về từ `/decrypt` vào Git, pull request, issue hoặc CI artifact.

## 10. Key rotation và tương thích ciphertext cũ

Lỗi giải mã thường xuất hiện ngay sau khi đổi `encrypt.key`, thay keystore hoặc deploy một Config Server replica với key mới. Ciphertext được tạo bởi key cũ không tự chuyển sang key mới.

### 10.1. Quy trình rotation có thời gian chuyển tiếp

Với hệ thống dùng nhiều key alias, quy trình an toàn thường là:

1. Tạo key/alias mới trong key management process.
2. Cài key mới trên tất cả Config Server replica trong khi vẫn giữ key cũ.
3. Xác minh cả ciphertext cũ và ciphertext thử nghiệm mới đều giải mã được.
4. Mã hóa lại property bằng key mới và thêm `{key:new-alias}` vào source config.
5. Triển khai repository/config update, theo dõi `invalid.*` và startup của client.
6. Xác nhận không còn property nào dùng alias cũ.
7. Chỉ sau khi đã xác nhận toàn bộ ciphertext được migrate, mới loại bỏ alias cũ theo quy trình quản lý khóa.

Không xóa key cũ ngay khi deploy key mới. Trong thời gian chuyển tiếp, Config Server cần giải mã được cả giá trị chưa migrate và giá trị mới.

### 10.2. Dùng nhiều alias trong cùng keystore

Ví dụ source config có thể chứa hai alias khác nhau:

~~~yaml
spring:
  datasource:
    username: '{cipher}{key:config-2025}OLD_CIPHERTEXT'
    password: '{cipher}{key:config-2026}NEW_CIPHERTEXT'
~~~

Đây chỉ là ví dụ cấu trúc. Alias `config-2025` và `config-2026` phải tồn tại trong keystore hoặc được custom locator hỗ trợ. Mỗi ciphertext phải được mã hóa bằng đúng public key/key tương ứng với alias.

### 10.3. Rotation khi dùng symmetric key đơn

Nếu chỉ cấu hình một `encrypt.key` mà không có custom `TextEncryptorLocator`, không có alias cũ/mới để chọn tự động. Đổi key đơn sẽ làm ciphertext cũ không còn giải mã được.

Với symmetric key đơn, hãy lập kế hoạch migrate ciphertext trước hoặc triển khai cơ chế locator hỗ trợ nhiều key. Không rollout một key mới tới Config Server trong khi repository vẫn chứa ciphertext chỉ giải mã được bằng key cũ.

### 10.4. Key bị lộ

Nếu key bị lộ, coi đây là sự cố bảo mật. Thu hồi quyền truy cập key cũ, tạo key mới, mã hóa lại các property bị ảnh hưởng, cập nhật Config Server/client và rà soát lịch sử truy cập repository, endpoint `/decrypt`, log và artifact CI. Thời gian giữ key cũ để tương thích phải được quyết định theo chính sách incident response; không kéo dài chỉ để rollout thuận tiện.

## 11. Plain-text resource endpoint và client-side decryption

Hai chế độ này thường bị nhầm với lỗi key.

### 11.1. Decrypt property trong plain-text resource endpoint

Mặc định, encrypted value trong plain-text resource files không được giải mã. Nếu Config Server phục vụ tài nguyên YAML, JSON hoặc `.properties` qua resource endpoint và cần decrypt cipher trong nội dung file, bật:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: true
          plainTextEncrypt: true
~~~

Tính năng này chỉ hỗ trợ các extension YAML, JSON và properties. Nếu request extension khác, encrypted value có thể vẫn được trả về nguyên dạng.

### 11.2. Client-side decryption

Nếu chủ ý để client tự giải mã:

1. Config Server phải giữ ciphertext trong Environment response bằng `spring.cloud.config.server.encrypt.enabled=false`.
2. Client phải có decryption support và key phù hợp.
3. Mỗi client cần được bảo vệ như một nơi giữ khóa.
4. Phải kiểm thử trên đúng Config Client version và Config Data/bootstrap mode.

Mô hình này có thể phù hợp khi Config Server chỉ giữ public key hoặc một số client được phép giữ private key. Đổi lại, quy trình phân phối và rotation key phức tạp hơn vì key được phân tán tới nhiều client.

Không trộn hai mô hình trên cùng một property nếu không có thiết kế rõ ràng. Xác minh Environment response để biết ciphertext được giải mã ở server hay client.

## 12. Crypto runtime và lỗi thuật toán

Nếu log báo lỗi cụ thể như `InvalidKeyException: Illegal key size`, kiểm tra JDK và crypto policy của runtime. Đây có thể là vấn đề policy/provider ở một JDK cũ, nhưng các JDK hiện đại thường đã bật unlimited-strength cryptography theo mặc định. Không cài các gói policy JCE cũ một cách máy móc.

Kiểm tra:

- JDK vendor và version giống nhau giữa local, staging và production.
- Provider crypto cần thiết có trong runtime image.
- JDK image tối giản không bị thiếu provider/module.
- Ciphertext được tạo bằng cùng loại key và thuật toán mà runtime hiện tại hỗ trợ.
- Không đổi thuật toán hoặc provider trong lúc key/ciphertext cũ vẫn còn được sử dụng.

Nếu lỗi chỉ xảy ra sau khi đổi base image/JDK, thử giải mã cùng ciphertext trong môi trường kiểm thử dùng runtime cũ và mới. Nếu chỉ một runtime thất bại, so sánh provider, security properties và thuật toán trước khi thay key.

Không tự giải mã bằng một thuật toán AES/RSA tự chọn để “sửa” dữ liệu. Spring Cloud Config phải dùng đúng `TextEncryptor` đã tạo ciphertext; tự đổi thuật toán sẽ tạo thêm một định dạng cipher không tương thích.

## 13. Kiểm thử encrypt/decrypt

Không dùng key production hoặc secret thật trong test. Dùng key test riêng và dữ liệu giả, đồng thời không in plaintext/ciphertext vào log.

### 13.1. Kiểm thử vòng đời endpoint

Với Config Server test có bật encryption và endpoint được expose, có thể dùng `TestRestTemplate` để kiểm tra round trip:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "encrypt.key=test-only-key-not-for-production")
class ConfigServerEncryptionEndpointTests {

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void encryptThenDecryptReturnsOriginalTestValue() {
        String original = "synthetic-config-value";

        ResponseEntity<String> encrypted =
                restTemplate.postForEntity("/encrypt", original, String.class);

        assertThat(encrypted.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(encrypted.getBody()).isNotBlank();

        ResponseEntity<String> decrypted =
                restTemplate.postForEntity(
                        "/decrypt", encrypted.getBody(), String.class);

        assertThat(decrypted.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(decrypted.getBody()).isEqualTo(original);
    }
}
~~~

Nếu test application dùng Spring Security, cấu hình test authentication/authorization cho endpoint theo security policy của ứng dụng. Không tắt security trong production để làm test pass. Với asymmetric key, dùng keystore test và alias test thay cho `encrypt.key`.

### 13.2. Kiểm thử Config Server trả property đã giải mã

Tạo một Config Server test dùng repository giả hoặc file fixture. Đưa một property cipher được mã hóa bằng test key vào source, sau đó gọi Environment endpoint:

1. Xác minh response có property name gốc.
2. Xác minh response không có `invalid.<property>`.
3. Xác minh giá trị trả về bằng test plaintext.
4. Thay ciphertext bằng dữ liệu không hợp lệ và xác minh server phát hiện lỗi giải mã.
5. Kiểm tra behavior khi `prefix-invalid-properties` giữ mặc định bật.

Không assert toàn bộ JSON response vì metadata có thể thay đổi giữa phiên bản. Chỉ assert property source, property name và trạng thái giải mã cần thiết.

### 13.3. Kiểm thử key alias và rotation

Với keystore có hai alias test:

- Mã hóa bằng alias cũ và xác minh decrypt thành công.
- Mã hóa bằng alias mới và xác minh decrypt thành công.
- Thử alias không tồn tại và xác minh có cảnh báo/lỗi phù hợp.
- Bỏ alias cũ trong test riêng và xác minh ciphertext cũ không còn decrypt được.

Test này giúp chứng minh quy trình rotation có thể chạy trong giai đoạn hai key cùng tồn tại và phát hiện sớm việc xóa alias quá sớm.

## 14. Bảng troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Response có `invalid.db.password` | Config Server không giải mã được property | Gọi `/decrypt` trên đúng replica; kiểm tra key/alias và ciphertext |
| `/decrypt` trả lỗi với mọi ciphertext | Key chưa nạp, key sai hoặc keystore không mở được | Kiểm tra `ENCRYPT_KEY`, `encrypt.keyStore.*`, secret manager và startup log |
| Chỉ một Config Server replica lỗi | Các replica dùng key/keystore version khác nhau | Đồng bộ secret version, keystore và deployment revision |
| `/decrypt` thành công nhưng Environment vẫn có `invalid.*` | Sai source/profile/label, custom locator chọn key khác hoặc property source khác chứa ciphertext | Gọi đúng Environment path và kiểm tra application/profile/label |
| Ciphertext hoạt động ở staging nhưng lỗi production | Key, alias, JDK/provider hoặc secret version khác | So sánh cấu hình tham chiếu và runtime metadata, không in secret |
| Giá trị property bắt đầu bằng `{cipher}` ở client | Server tắt outgoing decryption hoặc dùng client-side decryption | Kiểm tra `spring.cloud.config.server.encrypt.enabled` và key ở client |
| YAML parse lỗi ở dòng password | `{cipher}` chưa được quote | Quote toàn bộ scalar YAML bằng dấu nháy đơn |
| `.properties` không decrypt | Ciphertext được bọc trong quote | Bỏ dấu quote quanh giá trị |
| Ciphertext chỉ lỗi khi gửi qua curl | Dấu `+` bị đổi thành khoảng trắng hoặc body bị encode sai | Gửi `text/plain` với `--data-binary` |
| Alias không tìm thấy | Sai `{key:alias}` hoặc alias chưa được deploy | Kiểm tra keystore và `TextEncryptorLocator` |
| Ciphertext cũ lỗi sau rotation | Key cũ đã bị xóa trước khi migrate hết property | Khôi phục alias cũ tạm thời và hoàn tất migration |
| `/encrypt` và `/decrypt` trả 404 | Endpoint encryption không được đăng ký hoặc request tới sai base path | Kiểm tra Config Server dependency/version và mapping |
| `/encrypt` trả 401/403 | Security policy chặn caller | Dùng credential/role quản trị đúng; không mở endpoint công khai |
| Resource endpoint vẫn trả cipher | `plainTextEncrypt` chưa bật hoặc extension không hỗ trợ | Kiểm tra `spring.cloud.config.server.encrypt.plainTextEncrypt` và định dạng file |
| Lỗi `Illegal key size` | JDK/crypto policy/provider không tương thích | Kiểm tra JDK và security provider; tránh cài policy JCE cũ một cách máy móc |
| Ứng dụng dùng fallback mà không crash | Source thấp hơn vẫn có giá trị cùng key | Kiểm tra `invalid.*` và property source precedence; không chỉ nhìn startup status |

### 14.1. Quy trình điều tra nhanh

1. Lấy application, profile, label và replica Config Server.
2. Kiểm tra Environment response để tìm `invalid.<property>`.
3. Gọi `/decrypt` với ciphertext gốc trên đúng replica.
4. Nếu decrypt thất bại, xác minh key/keystore/alias và ciphertext.
5. Nếu decrypt thành công, xác minh file format, property source và chế độ server-side/client-side.
6. Lặp lại kiểm tra trên từng replica.
7. Chạy integration test bằng test key trước khi cập nhật repository hoặc rollout.

## 15. Bảo mật endpoint và dữ liệu giải mã

Endpoint `/encrypt` và `/decrypt` là endpoint nhạy cảm. `/decrypt` có thể trả trực tiếp secret plaintext; `/encrypt` có thể bị lạm dụng như một oracle mã hóa. Chỉ cho phép service identity hoặc operator có quyền quản trị gọi các endpoint này.

### 15.1. Bảo vệ endpoint

- Đặt Config Server sau private network, gateway hoặc service mesh có policy phù hợp.
- Bật authentication và authorization cho `/encrypt` và `/decrypt`.
- Chỉ cấp quyền cho nhóm vận hành/key-management cần thiết.
- Dùng TLS khi truyền ciphertext, key metadata và response.
- Không expose endpoint decrypt ra Internet hoặc management port công khai.
- Kiểm tra security matcher không vô tình cho phép anonymous access do path matcher quá rộng.

Tài liệu Spring Cloud Config nêu rõ các endpoint encryption được cung cấp với giả định chúng đã được bảo vệ và chỉ caller được ủy quyền mới truy cập.

### 15.2. Không ghi plaintext hoặc key vào log

Không log:

- Giá trị trả về từ `/decrypt`.
- Nội dung request body gửi tới `/encrypt` hoặc `/decrypt`.
- `encrypt.key`, keystore password hoặc private key.
- Toàn bộ Environment response khi response có thể chứa secret.
- Ciphertext cùng metadata đủ để xác định key alias nếu log không được bảo vệ.

Log các metadata cần điều tra như request ID, application, profile, label, replica ID, alias name (nếu policy cho phép), outcome và exception category. Không log secret value.

### 15.3. Quản lý key

Đưa symmetric key, keystore password và private key password vào secret manager hoặc hệ thống quản lý khóa. Hạn chế quyền đọc theo service identity. Theo dõi version/rotation event và có runbook rollback. Không dùng cùng một key test, staging và production.

## 16. Runbook khôi phục

Khi property quan trọng không giải mã được trong production:

1. Xác định application/profile/label và replica trả `invalid.<property>`.
2. Kiểm tra có fallback property nào đang được dùng không; đánh giá tác động tới kết nối database, message broker hoặc downstream service.
3. Gọi `/decrypt` bằng ciphertext thử nghiệm trên một replica quản trị để xác định key hiện tại hoạt động.
4. Kiểm tra secret version, alias và keystore deployment; không sửa key ngay khi chưa biết ciphertext được tạo bằng key nào.
5. Nếu vừa rotation, bảo đảm key cũ còn tồn tại trong giai đoạn chuyển tiếp.
6. Nếu ciphertext hỏng, lấy lại source of truth hoặc mã hóa lại từ plaintext được phép truy cập theo quy trình quản lý secret.
7. Triển khai sửa đổi lên một replica/canary trước, gọi Environment endpoint và xác minh `invalid.<property>` biến mất.
8. Xác minh Config Client nhận đúng property và bean binding/health hoạt động.
9. Triển khai các replica còn lại và kiểm tra tính đồng nhất.
10. Thu hồi key cũ sau khi xác nhận không còn ciphertext phụ thuộc, trừ khi incident response yêu cầu thu hồi khẩn cấp.

Không thay tất cả ciphertext trong Git bằng một chuỗi mới chỉ để hết cảnh báo. Phải xác minh giá trị plaintext đúng từ nguồn được ủy quyền và bảo đảm key/alias mới đã có mặt trên mọi Config Server replica.

## 17. Bài tập thực hành

### Bài 1 — Nhận diện invalid property

Tạo Config Server test với một property cipher hợp lệ và một ciphertext không giải mã được. Gọi Environment endpoint, tìm key `invalid.*` và giải thích vì sao Config Client có thể nhận fallback từ source khác.

### Bài 2 — Kiểm tra symmetric key

Tạo test Config Server dùng `encrypt.key` giả. Gọi `/encrypt`, sau đó `/decrypt`. Thay key và xác minh ciphertext cũ không còn giải mã được.

### Bài 3 — Kiểm tra RSA keystore

Tạo keystore test bằng `keytool`. Kiểm tra alias và private key entry. Mã hóa bằng public key, giải mã bằng private key tương ứng. Thử sai alias/password để quan sát lỗi.

### Bài 4 — Sửa lỗi định dạng

Tạo hai fixture YAML và `.properties`. Đặt ciphertext có quote đúng/sai và xác minh khác biệt. Thử gửi ciphertext có dấu `+` bằng form encoding và `text/plain`.

### Bài 5 — Key rotation

Tạo hai alias test. Giữ cả hai alias trong keystore, chuyển một property sang alias mới và xác minh property cũ/mới đều giải mã được. Sau đó mô phỏng loại alias cũ trong test riêng.

### Bài 6 — Bảo vệ endpoint

Thêm security test cho `/encrypt` và `/decrypt`: caller không xác thực bị từ chối, operator được cấp quyền gọi, và response plaintext không xuất hiện trong log.

**Tiêu chí hoàn thành:** bạn có thể xác định nguyên nhân một property không giải mã được, kiểm chứng key/ciphertext bằng test, khôi phục cấu hình đúng và chứng minh endpoint/secret được bảo vệ.

## 18. Tổng kết

Khi Spring Cloud Config không giải mã được giá trị cipher, hãy bắt đầu từ Environment response và tìm `invalid.<property>`. Đây là tín hiệu cho biết Config Server đã loại ciphertext khỏi property source vì không thể giải mã. Kiểm tra đúng application/profile/label, gọi `/decrypt` trên đúng replica, rồi xác minh symmetric key hoặc RSA keystore, alias, ciphertext và format file.

YAML cần quote giá trị `{cipher}`; `.properties` không được quote. Khi truyền ciphertext qua HTTP, dùng `text/plain` hoặc cách URL encode phù hợp để không làm biến đổi `+`, `/`, `=`. Trong quá trình rotation, giữ key cũ cho đến khi mọi ciphertext đã được migrate và kiểm chứng. Nếu dùng client-side decryption hoặc plain-text resource endpoint, xác minh rõ các property điều khiển chế độ giải mã.

Endpoint `/decrypt` có thể trả plaintext nên phải được bảo vệ, không ghi body/response vào log và không dùng key production trong test. Bộ kiểm thử round-trip, Environment response và key alias giúp phát hiện lỗi trước khi triển khai.

## Tài liệu tham khảo

- [Spring Cloud Config 5.0.6 — Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html): tiền tố `{cipher}`, hành vi `invalid.*`, endpoint `/encrypt` và `/decrypt`.
- [Spring Cloud Config 5.0.6 — Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html): symmetric key, RSA key pair và cấu hình keystore.
- [Spring Cloud Config 5.0.6 — Using Multiple Keys and Key Rotation](https://docs.spring.io/spring-cloud-config/reference/server/using-multiple-keys-and-key-rotation.html): alias prefix, `TextEncryptorLocator` và rotation.
- [Spring Cloud Config 5.0.6 — Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html): server-side và client-side decryption.
- [Spring Cloud Config 5.0.6 — Actuator and Security](https://docs.spring.io/spring-cloud-config/reference/server/actuator-and-security.html): cấu hình Actuator và bảo vệ Config Server.

Đối chiếu tài liệu của đúng Spring Cloud release train và JDK đang chạy. Cấu hình key, crypto provider, endpoint security và bootstrap lifecycle có thể khác nhau giữa các thế hệ phiên bản.

# Giải mã cục bộ và giải mã tại nguồn cấu hình từ xa

Bài học thuộc chương **Mã hóa cấu hình** của module **SPRING_CLOUD_CORE**. Spring Cloud Config cho phép lưu property đã mã hóa trong repository và giải mã khi cung cấp cho ứng dụng. Có hai vị trí giải mã phổ biến:

- **Giải mã tại Config Server:** server đọc giá trị bắt đầu bằng `{cipher}`, giải mã rồi trả plaintext cho Config Client.
- **Giải mã cục bộ tại Config Client:** server trả ciphertext còn nguyên; client có key material phù hợp và tự giải mã trước khi ứng dụng sử dụng property.

Hai mô hình cùng bảo vệ dữ liệu khi lưu trữ, nhưng khác nhau về nơi giữ khóa, ranh giới tin cậy và chi phí vận hành. Bài học trình bày cả hai luồng, endpoint `/encrypt` và `/decrypt`, khóa đối xứng/bất đối xứng, lỗi giải mã và các kiểm soát cần có khi triển khai.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích tiền tố `{cipher}` và lý do ciphertext có thể được lưu trong repository cấu hình.
2. Mô tả luồng giải mã tại Config Server trước khi trả property cho client.
3. Cấu hình Config Server giữ ciphertext và Config Client giải mã cục bộ.
4. Phân biệt khóa đối xứng với cặp khóa bất đối xứng.
5. Dùng `/encrypt` và `/decrypt` để mã hóa/giải mã giá trị trong môi trường được bảo vệ.
6. Cấu hình `encrypt.key` hoặc `encrypt.keyStore.*` đúng nơi và đúng thời điểm.
7. Nhận diện phản hồi `invalid.<property>` khi Config Server không giải mã được.
8. Hiểu tác động của `{cipher}` trong YAML và `.properties`.
9. Kiểm thử response Config Server và giá trị cuối cùng trong Environment của client.
10. Thiết kế lưu trữ khóa, phân quyền, TLS, luân chuyển khóa và xử lý sự cố an toàn.

## 2. Mã hóa cấu hình bảo vệ dữ liệu ở đâu?

Giả sử cấu hình ứng dụng có thông tin kết nối database:

~~~yaml
spring:
  datasource:
    username: orders_app
    password: "a-secret-value"
~~~

Nếu file này được commit vào Git hoặc lưu trong backend dùng chung, người có quyền đọc repository có thể nhìn thấy password. Mã hóa property trước khi lưu giúp repository chỉ chứa ciphertext:

~~~yaml
spring:
  datasource:
    username: orders_app
    password: '{cipher}ENCRYPTED_VALUE'
~~~

Khi Config Server xử lý property source, tiền tố `{cipher}` báo rằng giá trị theo sau là dữ liệu đã mã hóa. Config Server hoặc Config Client sẽ giải mã tùy mô hình được cấu hình.

~~~mermaid
flowchart LR
    P["Plaintext secret"] --> ENC["/encrypt hoặc công cụ mã hóa"]
    ENC --> C["{cipher}..."]
    C --> G["Git / remote configuration store"]
    G --> S["Spring Cloud Config Server"]
    S -->|Giải mã tại server| PT1["Plaintext trong response"]
    S -->|Giữ ciphertext| CT["Ciphertext trong response"]
    CT --> CL["Config Client có key"]
    CL --> PT2["Plaintext trong Environment"]
~~~

Mã hóa ở trạng thái lưu trữ không thay thế TLS. Khi plaintext được gửi qua mạng, nạp vào JVM hoặc sử dụng bởi bean, nó vẫn cần được bảo vệ bằng network security, access control và chính sách quản lý secret.

## 3. Hai vị trí giải mã

### 3.1. Giải mã tại Config Server

Đây là mô hình mặc định khi Config Server được cấu hình key material để giải mã:

1. Quản trị viên mã hóa secret bằng `/encrypt` hoặc công cụ tương thích.
2. Ciphertext được thêm tiền tố `{cipher}` và lưu vào repository cấu hình.
3. Config Server đọc property source.
4. Config Server giải mã bằng khóa của server.
5. Config Server trả property đã giải mã cho Config Client qua HTTP(S).
6. Client nhận plaintext và đưa vào Environment.

Ưu điểm:
- Khóa giải mã tập trung ở server.
- Client không cần giữ khóa giải mã của repository.
- Quản lý và luân chuyển khóa có thể tập trung hơn.

Đổi lại, Config Server có quyền truy cập plaintext của tất cả secret mà nó giải mã. Cần bảo vệ server, filesystem, process environment, log, heap dump và các endpoint quản trị.

### 3.2. Giải mã cục bộ tại Config Client

Trong mô hình này, Config Server giữ ciphertext khi gửi property source:

1. Secret được mã hóa trước khi commit.
2. Config Server đọc và trả `{cipher}...` nguyên trạng.
3. Config Client nhận property source chứa ciphertext.
4. Spring Cloud Context phía client sử dụng `encrypt.*` để tìm khóa giải mã.
5. Client giải mã property trước khi ứng dụng sử dụng Environment.

Để bật mô hình này, Config Server cần được cấu hình:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
~~~

Tài liệu Spring Cloud Config yêu cầu đặt thuộc tính này trong `bootstrap.yml` hoặc `bootstrap.properties` của Config Server. Nếu server vẫn cần endpoint `/encrypt` và `/decrypt`, server có thể tiếp tục cấu hình `encrypt.*` để định vị khóa; chỉ tắt việc giải mã các property outgoing.

Nếu không cần các endpoint mã hóa/giải mã ở server, tài liệu cho biết có thể không cấu hình key hoặc cờ enabled cho chức năng đó. Hãy kiểm tra chế độ bootstrap và phiên bản Spring Cloud Config của ứng dụng.

### 3.3. So sánh hai mô hình

| Tiêu chí | Giải mã tại Config Server | Giải mã tại Config Client |
| --- | --- | --- |
| Nơi giữ khóa giải mã | Config Server. | Từng client hoặc hệ thống khóa mà client truy cập. |
| Dữ liệu server gửi | Plaintext sau giải mã. | Ciphertext `{cipher}...`. |
| Client cần khóa giải mã | Không cần khóa của repository. | Cần key material phù hợp. |
| Phạm vi ảnh hưởng khi lộ khóa | Có thể ảnh hưởng nhiều ứng dụng/profile dùng khóa đó. | Phụ thuộc từng khóa/client hoặc nhóm client. |
| Vận hành | Quản lý khóa tập trung. | Phân phối, bảo vệ và luân chuyển khóa phía client. |
| Phù hợp | Config Server là vùng tin cậy và muốn tập trung quản lý khóa. | Muốn server chỉ phân phối ciphertext và chỉ client được cấp key mới giải mã. |

Không có mô hình nào tự động an toàn hơn trong mọi tình huống. Hãy chọn dựa trên ranh giới tin cậy, khả năng quản lý khóa và số lượng client.

## 4. Định dạng {cipher} trong file cấu hình

### 4.1. YAML

Giá trị mã hóa trong YAML thường được đặt trong dấu nháy đơn để YAML parser giữ nguyên tiền tố và chuỗi ciphertext:

~~~yaml
spring:
  datasource:
    username: orders_app
    password: '{cipher}ENCRYPTED_VALUE'
~~~

Dấu nháy đơn là cú pháp YAML; giá trị property sau khi parse vẫn bắt đầu bằng `{cipher}`.

### 4.2. application.properties

Trong file `.properties`, không đặt giá trị mã hóa trong dấu nháy:

~~~properties
spring.datasource.username=orders_app
spring.datasource.password={cipher}ENCRYPTED_VALUE
~~~

Tài liệu Spring Cloud Config lưu ý encrypted value trong `application.properties` không được bọc trong quotes; nếu có quotes, giá trị có thể không được giải mã.

### 4.3. Tiền tố là tín hiệu xử lý, không phải thuật toán

`{cipher}` cho biết giá trị cần được giải mã. Nó không cho biết khóa nào được dùng hoặc thuật toán cụ thể nào đã tạo ciphertext. Cơ chế chọn encryptor có thể phụ thuộc `encrypt.*`, keystore, alias hoặc `TextEncryptorLocator`.

Không tự tạo chuỗi `{cipher}` bằng cách Base64-encode plaintext. Base64 chỉ là encoding, không phải mã hóa bảo mật. Hãy dùng `/encrypt`, Spring Cloud CLI hoặc công cụ mã hóa tương thích với cấu hình khóa của hệ thống.

## 5. Cấu hình khóa đối xứng

### 5.1. Một shared secret

Với mã hóa đối xứng, cùng một secret key được dùng để mã hóa và giải mã. Config Server có thể được cấu hình bằng:

~~~yaml
encrypt:
  key: ${ENCRYPT_KEY}
~~~

Có thể dùng biến môi trường `ENCRYPT_KEY` để không ghi key trực tiếp vào file cấu hình. Nếu ứng dụng sử dụng `spring-cloud-starter-bootstrap` hoặc bật bootstrap bằng system property, tài liệu Spring Cloud yêu cầu đặt `encrypt.key` trong `bootstrap.properties` để khóa có sẵn ở giai đoạn phù hợp.

Trong mô hình giải mã cục bộ, client cũng cần `encrypt.key` tương ứng, được cấp qua secret manager hoặc environment của client. Shared key được phân phối đến các client có quyền giải mã; cần giới hạn phạm vi truy cập và luân chuyển khóa khi có sự cố.

Không commit `encrypt.key` vào Git, không đặt key trong chính repository chứa ciphertext và không log key trong startup diagnostics.

### 5.2. Ưu và nhược điểm

Ưu điểm:
- Cấu hình đơn giản.
- Chỉ cần một giá trị khóa.
- Phù hợp với lab hoặc hệ thống có secret distribution được kiểm soát.

Nhược điểm:
- Bất kỳ bên nào có shared key đều có khả năng giải mã dữ liệu tương ứng.
- Mỗi client cần nhận cùng secret nếu client tự giải mã.
- Khi key bị lộ, cần đánh giá tất cả ciphertext được mã hóa bằng key đó.

### 5.3. Ví dụ cấu hình phía client

Trong mô hình client-side decryption, key cần có sẵn cho client trước khi bước giải mã property source chạy. Ví dụ với biến môi trường:

~~~text
ENCRYPT_KEY=<value-from-secret-manager>
~~~

Nếu cấu hình key qua file, đặt nó trong nguồn cấu hình bảo mật và đúng giai đoạn bootstrap mà phiên bản ứng dụng yêu cầu. Không lấy khóa giải mã từ chính remote property source đang cần giải mã; điều đó tạo phụ thuộc vòng và có thể làm lộ key.

## 6. Cấu hình khóa bất đối xứng

### 6.1. Cặp public key và private key

Mã hóa bất đối xứng sử dụng một cặp khóa:

- **Public key:** dùng để mã hóa dữ liệu.
- **Private key:** dùng để giải mã dữ liệu.

Spring Cloud Config có thể dùng keystore. Các thuộc tính chính:

| Thuộc tính | Vai trò |
| --- | --- |
| `encrypt.keyStore.location` | Resource location của keystore. |
| `encrypt.keyStore.password` | Password mở keystore. |
| `encrypt.keyStore.alias` | Alias của key/certificate được sử dụng. |
| `encrypt.keyStore.type` | Loại keystore; mặc định là `jks`. |

Ví dụ cấu hình YAML:

~~~yaml
encrypt:
  key-store:
    location: classpath:config-encryption.jks
    password: ${CONFIG_KEYSTORE_PASSWORD}
    alias: config-encryption
    type: jks
~~~

Đây là cấu trúc thuộc tính minh họa. Location, alias và loại keystore phải khớp keystore thực tế.

### 6.2. Server chỉ giữ public key, client giữ private key

Một mô hình phù hợp cho giải mã cục bộ:

- Config Server được cấu hình keystore chứa public key/certificate để mã hóa.
- Config Client được cấu hình keystore chứa private key tương ứng để giải mã.
- Repository chỉ lưu ciphertext.
- Config Server được tắt giải mã outgoing bằng `spring.cloud.config.server.encrypt.enabled=false`.

Cách này tránh phân phối private key tới Config Server. Chỉ client có private key tương ứng mới giải mã được. Cần bảo vệ private keystore, password và quyền truy cập filesystem của từng client.

Tài liệu Spring Cloud lưu ý mã hóa bằng public key và cần private key để giải mã. Có thể cấu hình chỉ public key ở server nếu việc giải mã được thực hiện cục bộ.

### 6.3. Khi nào chọn bất đối xứng?

| Tình huống | Hướng cân nhắc |
| --- | --- |
| Một server và vài client trong môi trường lab | Shared key có thể đơn giản hơn. |
| Nhiều client với ranh giới tin cậy khác nhau | Public/private key giúp cấp quyền giải mã theo client hoặc nhóm client. |
| Config Server không nên có private key | Chỉ cấp public key cho server, private key cho client. |
| Cần quản lý khóa tập trung | Server-side decryption có thể đơn giản hơn nếu server là vùng tin cậy. |

Bất đối xứng không tự giải quyết mọi vấn đề quản lý khóa. Cần bảo vệ private key, quản lý certificate/alias, backup, rotation và thu hồi quyền truy cập.

## 7. Dùng endpoint /encrypt và /decrypt

### 7.1. Endpoint /encrypt

Config Server cung cấp endpoint `/encrypt` để mã hóa plaintext thành ciphertext bằng key material đã cấu hình.

Ví dụ minh họa trong môi trường lab:

~~~bash
curl -s \
  --request POST \
  --header "Content-Type: text/plain" \
  --data-binary "secret-value" \
  http://localhost:8888/encrypt
~~~

Response là ciphertext. Lấy ciphertext và thêm tiền tố `{cipher}` khi lưu vào YAML hoặc `.properties`.

Khi dùng `curl` với dữ liệu có ký tự đặc biệt như `+`, khoảng trắng hoặc ký tự URL-sensitive, hãy dùng `--data-urlencode` theo cú pháp tài liệu hướng dẫn hoặc gửi `Content-Type: text/plain` rõ ràng. Không để thống kê hoặc thông báo curl bị ghép vào ciphertext.

Không đưa plaintext thật vào shell history, ticket, terminal transcript hoặc log CI. Với secret production, dùng quy trình quản trị secret đã được phê duyệt và tránh copy/paste qua kênh không bảo mật.

### 7.2. Endpoint /decrypt

Endpoint `/decrypt` thực hiện thao tác ngược lại nếu server có key phù hợp:

~~~bash
curl -s \
  --request POST \
  --header "Content-Type: text/plain" \
  --data-binary "ENCRYPTED_VALUE" \
  http://localhost:8888/decrypt
~~~

Response là plaintext. Chỉ dùng endpoint này trong môi trường được bảo vệ và bởi principal có quyền cần thiết. Không ghi response plaintext vào file tạm không được bảo vệ hoặc log.

### 7.3. Thêm {cipher} trước khi lưu

Quy trình điển hình:

1. Nhận plaintext qua secret-handling channel.
2. Gửi plaintext tới endpoint `/encrypt` đã bảo vệ.
3. Nhận ciphertext.
4. Thêm `{cipher}` ở đầu ciphertext.
5. Đặt giá trị vào property phù hợp.
6. Kiểm tra cú pháp YAML/properties.
7. Commit ciphertext vào repository cấu hình.
8. Kiểm thử Config Server trả đúng dữ liệu theo mô hình giải mã đã chọn.

Không commit plaintext trước rồi mới mã hóa ở commit tiếp theo. Secret có thể còn trong Git history và bản clone; nếu đã lộ, cần xử lý lịch sử theo quy trình incident/secret rotation.

### 7.4. Endpoint theo application và profile

Các endpoint mã hóa/giải mã cũng hỗ trợ path dạng:

~~~text
/{application}/{profiles}/encrypt
/{application}/{profiles}/decrypt
~~~

Cách này cho phép xác định application/profile khi dùng cơ chế mã hóa theo ngữ cảnh. Tuy nhiên, để dùng khóa khác nhau theo application/profile, cần cung cấp bean `TextEncryptorLocator` tự triển khai. Locator mặc định không tự chọn một khóa khác cho từng application/profile; mặc định dùng cùng key.

Không suy luận rằng thêm tên application vào URL tự động tạo ra key riêng.

## 8. Giải mã tại Config Server

### 8.1. Cấu hình server-side decryption

Trong mô hình này, Config Server giữ khóa giải mã. Ví dụ dùng shared key:

~~~yaml
encrypt:
  key: ${ENCRYPT_KEY}

spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: true
~~~

Giá trị mặc định của server là giải mã property encrypted trước khi trả client khi key/config phù hợp. Có thể cấu hình rõ `enabled: true` để thể hiện ý định. Nếu sử dụng bootstrap mode, đặt các thiết lập cần thiết trong bootstrap configuration theo hướng dẫn phiên bản.

### 8.2. Luồng từ Git tới client

~~~mermaid
sequenceDiagram
    participant Git as Config repository
    participant Server as Config Server
    participant Key as Server key material
    participant Client as Config Client
    Git->>Server: Đọc application.yml chứa {cipher}...
    Server->>Key: Tìm encryptor/key
    Key-->>Server: Key phù hợp
    Server->>Server: Giải mã property
    Server-->>Client: Property source có plaintext
    Client->>Client: Bind Environment / @ConfigurationProperties
~~~

Client không cần khóa giải mã repository trong mô hình này. Tuy nhiên, plaintext đã xuất hiện trong response Config Server và trong process client. Bảo vệ TLS, quyền truy cập Config Server, log, actuator, heap dump và diagnostics của client.

### 8.3. Lợi ích và giới hạn

Lợi ích:
- Quản lý key tập trung ở server.
- Client đơn giản hơn và không phải phân phối private/shared key.
- Key rotation có thể được điều phối tập trung.

Giới hạn:
- Config Server có quyền giải mã mọi property thuộc phạm vi key.
- Nếu server bị xâm nhập, ciphertext có thể được giải mã tại chính nơi lưu trữ.
- Plaintext được gửi qua mạng; TLS và authentication vẫn bắt buộc.
- Log hoặc trace vô tình chứa response plaintext đều có thể làm lộ secret.

## 9. Giải mã cục bộ tại Config Client

### 9.1. Tắt giải mã outgoing trên server

Trong Config Server, đặt:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
~~~

Theo tài liệu Spring Cloud Config, thiết lập này được đặt trong `bootstrap.yml` hoặc `bootstrap.properties` của server. Nếu server vẫn cấu hình `encrypt.*`, các endpoint `/encrypt` và `/decrypt` vẫn có thể được dùng; chỉ việc giải mã các property outgoing bị tắt.

### 9.2. Client nhận ciphertext và tự giải mã

Config Client phải có key material tương ứng.

**Với shared key:**

~~~yaml
encrypt:
  key: ${ENCRYPT_KEY}
~~~

**Với keystore/private key:**

~~~yaml
encrypt:
  key-store:
    location: file:/run/secrets/config-client-keystore.jks
    password: ${CONFIG_KEYSTORE_PASSWORD}
    alias: config-client
    type: jks
~~~

Đây là cấu hình minh họa. Đảm bảo file keystore và password được cấp từ secret management, không đưa vào repository cấu hình dùng chung.

Client phải có key sẵn trước khi Spring Cloud Context thực hiện giải mã property source. Nếu dùng bootstrap mode, đặt `encrypt.*` trong bootstrap configuration hoặc một nguồn local/environment được nạp đủ sớm. Không dựa vào key nằm trong remote source đang cần được giải mã.

### 9.3. Luồng xử lý phía client

~~~mermaid
sequenceDiagram
    participant Repo as Git / remote config store
    participant Server as Config Server
    participant Client as Config Client
    participant Crypto as Client encryptor
    participant Env as Client Environment
    Repo->>Server: Đọc {cipher}...
    Server->>Server: Không giải mã outgoing
    Server-->>Client: Trả ciphertext
    Client->>Crypto: Tìm key từ encrypt.*
    Crypto-->>Client: Giải mã giá trị
    Client->>Env: Đưa property plaintext vào Environment
    Env-->>Client: Bean binding / ứng dụng sử dụng
~~~

### 9.4. Lợi ích và giới hạn

Lợi ích:
- Config Server không cần private key hoặc shared decryption key nếu chỉ làm nhiệm vụ lưu trữ/phân phối ciphertext.
- Client không có key sẽ không giải mã được dữ liệu.
- Có thể giới hạn nhóm client được cấp private key.

Giới hạn:
- Key material phải được cấp và bảo vệ ở từng client.
- Rotation cần phối hợp giữa server, client và ciphertext trong repository.
- Nếu nhiều client dùng shared key, lộ key ở một client có thể ảnh hưởng các client khác.
- Client phải xử lý lỗi giải mã trước khi ứng dụng sử dụng cấu hình.
- Client local key phải có sẵn đủ sớm trong startup lifecycle.

## 10. Xử lý lỗi giải mã

### 10.1. Server không giải mã được

Nếu Config Server không giải mã được giá trị `{cipher}`, mặc định nó loại property gốc khỏi property source response và thêm property có tiền tố `invalid.`.

Ví dụ response:

~~~json
{
  "propertySources": [
    {
      "name": "application-prod.yml",
      "source": {
        "invalid.SharedPassword": "<n/a>"
      }
    },
    {
      "name": "application.yml",
      "source": {
        "SharedPassword": "fallback-value"
      }
    }
  ]
}
~~~

Trong ví dụ, `SharedPassword` ở file profile không giải mã được. Property gốc bị loại khỏi source đó; `invalid.SharedPassword` là marker cho lỗi. Nếu source thấp hơn có `SharedPassword`, client có thể nhận fallback value từ source đó.

Hành vi này giúp ciphertext lỗi không bị dùng nhầm như password và tránh lộ chuỗi mã hóa vào ứng dụng.

### 10.2. Tắt prefix invalid

Có thể cấu hình:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          prefix-invalid-properties: false
~~~

Khi tắt prefix invalid, giá trị không giải mã được có thể được trả dưới tên property gốc dưới dạng ciphertext. Trong mô hình client-side decryption, client có thể tiếp tục xử lý ciphertext nếu có key phù hợp. Nhưng nếu client cũng không có key, nó sẽ nhận giá trị mã hóa thay vì plaintext.

Không tắt prefix invalid chỉ để che lỗi key mismatch. Trước hết hãy kiểm tra key, alias, profile, ciphertext và thuật toán tương thích.

### 10.3. Các nguyên nhân phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Property có `invalid.` prefix | Server không tìm được key hoặc decrypt thất bại. | Kiểm tra `encrypt.*`, alias, keystore, ciphertext và log server. |
| Client nhận chuỗi `{cipher}...` | Server đã tắt giải mã outgoing hoặc client decrypt chưa chạy/không có key. | Xác minh mô hình server/client-side và `encrypt.*` trên client. |
| `/decrypt` trả lỗi | Key sai, thiếu private key, ciphertext bị cắt hoặc dữ liệu gửi sai encoding. | Kiểm tra key material, Content-Type và ciphertext nguyên vẹn. |
| Một profile giải mã được, profile khác không | Profile dùng key/alias khác hoặc ciphertext được tạo bằng key khác. | Kiểm tra `{key:alias}`, application/profile path và keystore alias. |
| Property lấy fallback thay vì giá trị profile | Property profile bị loại do decrypt fail; source thấp hơn cung cấp cùng key. | Kiểm tra `invalid.<key>` trong response và thứ tự PropertySource. |
| YAML parse được nhưng không decrypt | Cú pháp quote/prefix không đúng hoặc ciphertext bị sửa. | Đối chiếu quy tắc `{cipher}` cho YAML và `.properties`. |

## 11. Mã hóa file plaintext và property source từ xa

### 11.1. Decrypt plain-text file không mặc định bật

Spring Cloud Config mặc định không giải mã giá trị encrypted trong mọi plain-text file được phục vụ như resource. Nếu cần chức năng đó, tài liệu hướng dẫn cấu hình tại Config Server:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: true
          plain-text-encrypt: true
~~~

Tính năng này chỉ hỗ trợ file có extension YAML, JSON và `.properties`. Nếu client yêu cầu extension không được hỗ trợ, các giá trị encrypted trong file đó sẽ không được giải mã.

### 11.2. Phân biệt Environment endpoint và resource endpoint

Config Server có thể cung cấp:
- Environment resource, thường được Config Client sử dụng để nạp property sources.
- Resource/plain-text file endpoint, dùng khi client cần lấy một file cụ thể.

Không mặc định rằng quy tắc xử lý encrypted value của Environment endpoint tự áp dụng cho mọi loại file/resource. Hãy kiểm tra extension và cờ `plain-text-encrypt` khi thiết kế luồng.

## 12. Nhiều khóa và luân chuyển khóa

### 12.1. Chỉ định key alias trong ciphertext

Khi dùng keystore với nhiều key, Config Server hỗ trợ prefix bổ sung trước ciphertext, ví dụ:

~~~yaml
app:
  database:
    password: '{cipher}{key:orders-key-v2}ENCRYPTED_VALUE'
~~~

Prefix `{key:orders-key-v2}` cho locator biết alias cần dùng. `TextEncryptorLocator` nhận metadata này để tìm encryptor phù hợp. Với locator mặc định và keystore, alias có thể được dùng để chọn key.

Prefix metadata đứng sau `{cipher}` và trước ciphertext. Đừng tự thêm alias nếu alias đó chưa có trong keystore của thành phần chịu trách nhiệm giải mã.

### 12.2. Quy trình rotation có kiểm soát

Một quy trình rotation điển hình:

1. Tạo key/alias mới trong keystore hoặc secret manager.
2. Cấp key mới cho server/client theo mô hình giải mã đã chọn.
3. Xác minh tất cả instance cần giải mã đều có key mới.
4. Mã hóa lại secret bằng key mới.
5. Cập nhật `{key:new-alias}` trong repository cấu hình nếu dùng nhiều alias.
6. Deploy/cập nhật config theo thứ tự tương thích.
7. Xác minh giải mã và hành vi nghiệp vụ.
8. Thu hồi key cũ sau khi không còn ciphertext hoặc client cần nó.
9. Ghi audit và giữ kế hoạch rollback trong thời gian chuyển đổi.

Không xóa key cũ trước khi toàn bộ ciphertext đã được mã hóa lại và mọi client đã chuyển sang alias mới. Nếu key bị lộ, xử lý như một sự cố bảo mật: đánh giá phạm vi ciphertext, xoay credential thật và rà soát Git history/logs.

## 13. Kiểm thử hai mô hình

### 13.1. Kiểm thử server-side decryption

1. Cấu hình key cho Config Server.
2. Mã hóa một giá trị lab bằng `/encrypt`.
3. Lưu ciphertext với tiền tố `{cipher}` trong repository.
4. Yêu cầu Config Server trả Environment resource cho application/profile.
5. Xác minh response chứa plaintext ở property gốc, không còn ciphertext.
6. Yêu cầu Config Client và xác minh Environment/bean nhận plaintext.
7. Thử key sai trong môi trường test và kiểm tra `invalid.<key>`.

Không dùng secret production cho test. Dùng giá trị giả và key riêng cho test profile.

### 13.2. Kiểm thử client-side decryption

1. Cấu hình Config Server với `spring.cloud.config.server.encrypt.enabled=false`.
2. Lưu một property `{cipher}...` trong repository.
3. Cấp key phù hợp cho Config Client qua nguồn local/secret.
4. Yêu cầu Config Server trả Environment resource.
5. Xác minh payload từ server vẫn có ciphertext.
6. Khởi động Config Client và xác minh Environment cuối cùng có plaintext.
7. Chạy test với client không có key hoặc key sai; xác minh lỗi giải mã và không sử dụng ciphertext làm credential.

### 13.3. Ma trận kiểm chứng

| ID | Mô hình | Tình huống | Kết quả cần xác minh |
| --- | --- | --- | --- |
| C1 | Server-side | Ciphertext hợp lệ, server có key. | Server trả plaintext cho client. |
| C2 | Server-side | Server không có key phù hợp. | Response có `invalid.<key>` theo mặc định. |
| C3 | Server-side | Tắt `prefix-invalid-properties`. | Ciphertext có thể nằm dưới key gốc; không coi là plaintext. |
| C4 | Client-side | Server tắt decrypt outgoing, client có key đúng. | Server trả ciphertext; client Environment có plaintext. |
| C5 | Client-side | Client không có key. | Client không thể giải mã; ứng dụng không được coi ciphertext là secret hợp lệ. |
| C6 | Client-side | Client có key sai. | Giải mã thất bại và được quan sát rõ ràng. |
| C7 | Cả hai | YAML dùng quote đúng cho `{cipher}`. | YAML parse và decrypt đúng. |
| C8 | Cả hai | `.properties` bọc ciphertext trong quotes. | Test phát hiện giá trị không được decrypt như mong đợi. |
| C9 | Cả hai | Ciphertext có ký tự `+` hoặc ký tự đặc biệt. | Request `/encrypt` giữ nguyên dữ liệu đầu vào. |
| C10 | Multi-key | Alias mới có mặt ở keystore. | Ciphertext có `{key:alias}` được giải mã bằng đúng alias. |
| C11 | Rotation | Ciphertext vẫn dùng alias cũ. | Client/server còn key cũ giải mã được trong giai đoạn chuyển tiếp. |
| C12 | Plain-text resource | YAML/JSON/properties với `plain-text-encrypt=true`. | Giá trị encrypted được giải mã theo hỗ trợ extension. |

## 14. Bảo mật và vận hành

1. **Bảo vệ endpoint:** `/encrypt` và đặc biệt `/decrypt` chỉ dành cho principal quản trị. Giới hạn network, authentication, authorization và audit.
2. **Dùng TLS:** ciphertext và plaintext đều cần bảo vệ khi truyền. Không dùng HTTP không mã hóa trên mạng không tin cậy.
3. **Không lưu khóa cạnh ciphertext:** repository chứa ciphertext; key material phải nằm trong secret manager, keystore hoặc hệ thống quản lý khóa.
4. **Giới hạn quyền Config Server:** nếu server giữ private/shared key, bảo vệ process, filesystem, container secrets, heap dump và log.
5. **Giới hạn quyền Config Client:** nếu client-side decryption, chỉ cấp private/shared key cho client cần dùng secret.
6. **Không log plaintext:** tránh log request `/decrypt`, response Config Server, property dump hoặc exception có chứa secret.
7. **Kiểm soát fallback:** khi decrypt lỗi, kiểm tra `invalid.<key>` và fallback source; không để ứng dụng âm thầm dùng credential mặc định không mong muốn.
8. **Rotation có kế hoạch:** hỗ trợ nhiều alias trong giai đoạn chuyển tiếp và chỉ thu hồi key cũ khi đã hoàn tất.
9. **Không nhầm encryption với secret lifecycle:** mã hóa ciphertext trong Git không tự xoay password database, token hay certificate.
10. **Kiểm tra mọi replica:** client-side decryption cần key ở từng instance; một replica thiếu key có thể khởi động lỗi trong khi replica khác hoạt động.

## 15. Checklist hoàn thành

- [ ] Giải thích được ý nghĩa tiền tố `{cipher}`.
- [ ] Phân biệt giải mã tại Config Server và giải mã cục bộ tại Config Client.
- [ ] Biết Config Server giải mã property encrypted trước khi trả client khi được cấu hình key.
- [ ] Biết tắt server-side outgoing decryption bằng `spring.cloud.config.server.encrypt.enabled=false`.
- [ ] Biết client cần `encrypt.*` key material có sẵn đủ sớm để giải mã.
- [ ] Phân biệt `encrypt.key` với `encrypt.keyStore.*`.
- [ ] Giải thích public key dùng để mã hóa và private key dùng để giải mã.
- [ ] Dùng được `/encrypt` và `/decrypt` trong môi trường được bảo vệ.
- [ ] Thêm `{cipher}` trước ciphertext khi lưu trong YAML/properties.
- [ ] Biết quy tắc quote khác nhau giữa YAML và `.properties`.
- [ ] Nhận diện `invalid.<key>` khi Config Server không giải mã được.
- [ ] Hiểu `prefix-invalid-properties=false` và hệ quả với ciphertext.
- [ ] Phân biệt Environment resource với plain-text resource và `plain-text-encrypt`.
- [ ] Hiểu `{key:alias}` và quy trình luân chuyển khóa.
- [ ] Có test cho cả server-side và client-side decryption.
- [ ] Có TLS, access control, audit, secret manager và kế hoạch rotation.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Cloud Config – Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html): định dạng cipher, endpoint mã hóa/giải mã, lỗi giải mã và prefix invalid.
- [Spring Cloud Config – Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html): cấu hình để client giải mã cục bộ và tắt server-side outgoing decryption.
- [Spring Cloud Config – Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html): shared key, keystore, public/private key và cách giữ key material.
- [Spring Cloud Config – Using Multiple Keys and Key Rotation](https://docs.spring.io/spring-cloud-config/reference/server/using-multiple-keys-and-key-rotation.html): alias, TextEncryptorLocator và rotation.

Tên thuộc tính, bootstrap behavior và API có thể khác theo release train. Hãy đối chiếu Spring Boot/Spring Cloud Config BOM của dự án và kiểm thử response thực tế của Config Server trước khi triển khai.

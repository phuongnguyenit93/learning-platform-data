# Giải mã phía Config Server so với giải mã phía client

## 1. Hai nơi có thể giải mã cấu hình

Spring Cloud Config cho phép lưu giá trị nhạy cảm dưới dạng ciphertext trong repository, thường với tiền tố `{cipher}`. Khi Config Client yêu cầu cấu hình, hệ thống phải giải mã giá trị trước khi ứng dụng sử dụng nó. Có hai vị trí có thể thực hiện công việc này:

1. **Giải mã phía Config Server**: Config Server đọc ciphertext từ Git hoặc backend, giải mã bằng khóa của server rồi trả giá trị rõ cho client qua HTTP.
2. **Giải mã phía client**: Config Server trả ciphertext cho client; mỗi ứng dụng giải mã cục bộ bằng khóa được cấp cho nó trước khi các property được dùng trong Spring `Environment`.

Mặc định, nếu Config Server được cấu hình key material và nhận property value bắt đầu bằng `{cipher}`, server giải mã trước khi gửi response. Mô hình client-side cần tắt việc giải mã outgoing properties ở server và cấu hình cơ chế giải mã trong từng client.

Việc chọn vị trí giải mã quyết định ai nắm khóa, plaintext xuất hiện ở đâu, cách triển khai và phạm vi ảnh hưởng khi khóa bị lộ. Đây là quyết định kiến trúc bảo mật, không chỉ là một thay đổi cú pháp YAML.

## 2. Luồng giải mã phía Config Server

Trong mô hình mặc định, Config Server giữ khóa giải mã hoặc private key. Git repository chỉ lưu ciphertext:

```yaml
spring:
  datasource:
    username: app_user
    password: '{cipher}ENCRYPTED_VALUE_FROM_CONFIG_SERVER'
```

Khi client yêu cầu:

```text
GET /order-service/prod/main
```

Config Server thực hiện:

1. Đọc các property source phù hợp với application, profile và label.
2. Phát hiện giá trị có tiền tố `{cipher}`.
3. Dùng key material ở server để giải mã.
4. Đưa plaintext vào `Environment` response.
5. Trả response cho Config Client qua HTTP/HTTPS.

```mermaid
flowchart LR
    G[(Git repository<br/>{cipher}...)] --> S[Config Server]
    K[Server key / private key] --> S
    S -->|decrypt| P[Plaintext property]
    P -->|HTTPS response| C[Config Client]
    C --> A[Spring Environment / beans]
```

Client không cần giữ khóa mã hóa chỉ để đọc cấu hình đã được server giải mã. Nó vẫn phải được xác thực và phân quyền để chỉ lấy cấu hình thuộc phạm vi được phép.

## 3. Cấu hình key material cho server-side decryption

Spring Cloud Config hỗ trợ khóa đối xứng và khóa bất đối xứng.

### Khóa đối xứng

Khóa đối xứng là một secret được dùng cho cả mã hóa và giải mã. Có thể cấp qua biến môi trường:

```yaml
encrypt:
  key: ${CONFIG_ENCRYPT_KEY}
```

Trong ví dụ, `CONFIG_ENCRYPT_KEY` được cấp qua secret manager hoặc secret store của nền tảng. Không commit giá trị khóa thật vào Git repository cấu hình hoặc file `application.yml` dùng chung.

Khóa đối xứng đơn giản để cấu hình, nhưng bất kỳ thành phần nào có khóa đều có khả năng giải mã ciphertext được tạo bằng khóa đó. Nếu cùng một khóa được chia sẻ cho nhiều ứng dụng, việc lộ khóa ở một client có thể ảnh hưởng đến tất cả dữ liệu dùng khóa đó.

### Khóa bất đối xứng RSA

Với RSA, public key được dùng để mã hóa và private key được dùng để giải mã. Config Server có thể lấy key material từ keystore:

```yaml
encrypt:
  key-store:
    location: ${CONFIG_KEYSTORE_LOCATION}
    password: ${CONFIG_KEYSTORE_PASSWORD}
    alias: config-server-key
    type: PKCS12
```

Các thuộc tính xác định vị trí keystore, mật khẩu mở keystore, alias của key và loại keystore. Trong server-side decryption, server phải có private key tương ứng để giải mã giá trị mà client yêu cầu.

RSA thuận tiện khi cần phân tách quyền mã hóa và giải mã: bên tạo ciphertext chỉ cần public key, còn private key được giữ ở nơi giải mã. Tuy nhiên, cần quản lý keystore, password, alias và luân chuyển key cẩn thận.

## 4. Luồng giải mã phía client

Ở mô hình client-side, Config Server không giải mã property khi tạo response. Client nhận ciphertext và tự giải mã trong môi trường cục bộ trước khi ứng dụng sử dụng cấu hình.

```mermaid
flowchart LR
    G[(Git repository<br/>{cipher}...)] --> S[Config Server]
    S -->|ciphertext over HTTPS| C[Config Client]
    K[Client key / private key] --> C
    C -->|local decrypt| P[Plaintext property]
    P --> A[Spring Environment / beans]
```

Để Config Server tiếp tục trả ciphertext, đặt thuộc tính sau trong bootstrap configuration của Config Server:

```yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
```

Theo hướng dẫn Spring Cloud Config, thuộc tính này được đặt trong `bootstrap.yml` hoặc `bootstrap.properties` của server. Nếu server vẫn cần cung cấp endpoint `/encrypt` và `/decrypt`, có thể cấu hình `encrypt.*` để định vị key material nhưng tắt outgoing decryption như trên. Nếu không cần các endpoint mã hóa/giải mã ở server, có thể không cấu hình key hoặc enabled flag theo mô hình tài liệu hỗ trợ.

Config Client cần cơ chế giải mã cục bộ. Spring Cloud Commons cung cấp Environment pre-processor cho các property dạng `{cipher}...`; ứng dụng cần dependency `spring-security-rsa` trên classpath để sử dụng tính năng này. Cấu hình key material phải có sẵn ở client đủ sớm để giải mã trước khi các property được bind vào bean.

Ví dụ với khóa đối xứng ở client:

```yaml
encrypt:
  key: ${CONFIG_DECRYPT_KEY}
```

Với RSA, client cần keystore chứa private key tương ứng. Cấp private key và mật khẩu qua secret store; không đặt chúng trong repository dùng chung mà Config Server trả cho mọi ứng dụng.

## 5. So sánh hai mô hình

| Tiêu chí | Giải mã phía Config Server | Giải mã phía client |
|---|---|---|
| Nơi giữ khóa giải mã | Config Server giữ symmetric key hoặc private key. | Mỗi client giữ key được cấp; với RSA, client giữ private key. |
| Response HTTP | Chứa plaintext sau giải mã. | Chứa ciphertext `{cipher}...`. |
| Client cần dependency giải mã | Không cần chỉ để nhận giá trị đã giải mã từ server. | Cần cơ chế giải mã cục bộ, gồm `spring-security-rsa`. |
| Quản lý khóa | Tập trung ở server, dễ kiểm soát số nơi có private key. | Phân phối khóa đến các client, phức tạp hơn khi nhiều dịch vụ. |
| Rủi ro khi server bị xâm nhập | Kẻ tấn công có thể tiếp cận key và plaintext mà server xử lý. | Server có thể chỉ giữ public key; ciphertext bị lộ nhưng không tự giải mã được nếu private key an toàn. |
| Rủi ro khi client bị xâm nhập | Client có thể lấy plaintext cấu hình mà nó được phép đọc. | Client có thể làm lộ key riêng và plaintext mà key đó giải mã được. |
| Phù hợp khi | Muốn tập trung key management và có thể tin cậy Config Server. | Muốn hạn chế plaintext xuất hiện trên server hoặc chỉ một số client có private key mới đọc được secret. |

Không có mô hình nào loại bỏ nhu cầu TLS. Với server-side, plaintext nằm trong response nên HTTPS đặc biệt quan trọng. Với client-side, ciphertext vẫn cần được bảo vệ trên đường truyền và request vẫn cần xác thực; TLS còn bảo vệ tính toàn vẹn, danh tính server và các metadata khác.

## 6. Chọn mô hình theo ranh giới tin cậy

### Khi nên giải mã ở Config Server

Mô hình server-side thường phù hợp khi:

- Config Server là thành phần hạ tầng được bảo vệ nghiêm ngặt và được tin cậy để xử lý plaintext.
- Muốn tập trung key management và không phân phối private key đến từng client.
- Có nhiều client nhưng cần một chính sách mã hóa, giải mã và luân chuyển key thống nhất.
- Client chỉ cần nhận property value cuối cùng, không cần tự quản lý cryptographic material.

Đổi lại, Config Server trở thành nơi xử lý plaintext và giữ khóa giải mã. Cần hạn chế quyền truy cập vào server, bảo vệ response bằng TLS, không log giá trị bí mật và phân quyền theo application.

### Khi nên giải mã ở client

Mô hình client-side có thể phù hợp khi:

- Muốn Config Server không cần giữ private key giải mã.
- Chỉ một nhóm client nhỏ cần đọc một tập secret cụ thể.
- Có khả năng cấp và bảo vệ private key riêng trong từng workload.
- Muốn ciphertext vẫn được giữ nguyên trong response từ server đến client.

Đổi lại, key management được phân tán. Cần bảo đảm client chỉ nhận ciphertext mà nó được phép giải mã, private key không bị đưa vào image hoặc Git, và key của một client không mở khóa secret của dịch vụ khác.

Nếu tất cả client dùng cùng một symmetric key, lợi ích cô lập giảm đáng kể: một client bị xâm nhập có thể giải mã các giá trị dùng chung key. Với yêu cầu cô lập theo dịch vụ, cân nhắc RSA key pair hoặc key riêng theo application/profile và một `TextEncryptorLocator` phù hợp.

## 7. Dùng /encrypt và /decrypt để tạo ciphertext

Config Server cung cấp endpoint `POST /encrypt` và `POST /decrypt` khi có cấu hình key material phù hợp. Ví dụ mã hóa một giá trị trong môi trường thử nghiệm:

```bash
curl -s -X POST \
  -H "Content-Type: text/plain" \
  --data-binary "sample-value" \
  http://localhost:8888/encrypt
```

Endpoint trả ciphertext. Thêm tiền tố `{cipher}` vào giá trị trước khi lưu vào file YAML:

```yaml
spring:
  datasource:
    password: '{cipher}ENCRYPTED_VALUE_FROM_ENDPOINT'
```

Với file `.properties`, giá trị cần có dạng:

```properties
spring.datasource.password={cipher}ENCRYPTED_VALUE_FROM_ENDPOINT
```

Tài liệu Spring Cloud Config lưu ý giá trị `{cipher}` trong `.properties` không nên được bọc trong dấu nháy, vì việc đó có thể khiến server không nhận diện để giải mã. Trong YAML, nên quote chuỗi bắt đầu bằng `{cipher}` để YAML parser hiểu đó là scalar string.

Endpoint `/decrypt` thực hiện thao tác ngược lại khi thành phần gọi có quyền và server có key phù hợp:

```bash
curl -s -X POST \
  -H "Content-Type: text/plain" \
  --data-binary "ENCRYPTED_VALUE_FROM_ENDPOINT" \
  http://localhost:8888/decrypt
```

Không truyền secret production trực tiếp trên command line của máy dùng chung nếu shell history, process list hoặc log có thể lưu lại. Dùng công cụ quản lý secret và quy trình mã hóa nội bộ được kiểm soát. Không ghi plaintext hoặc response của `/decrypt` vào log.

## 8. Cấu hình server cho client-side decryption

Nếu chọn client-side, cấu hình server phải giữ nguyên ciphertext trong response:

```yaml
# bootstrap.yml của Config Server
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
```

Với RSA, có thể chỉ cấu hình public key ở server để mã hóa dữ liệu mới, còn private key được cấp cho đúng client cần giải mã. Tài liệu Spring Cloud Config lưu ý rằng cách này có thể hữu ích khi Config Server không phải nơi được tin cậy để giữ private key và chỉ một số ít client cần secret.

Nếu server vẫn giữ cả private key thì về mặt kỹ thuật server vẫn có khả năng giải mã, dù outgoing decryption đã tắt. Việc tắt xử lý outgoing không làm private key biến mất khỏi server. Nếu mục tiêu là server không thể giải mã, phải thiết kế key material để server chỉ có public key và kiểm tra rằng không có private key khác được mount hoặc cấp vào runtime.

## 9. Cấu hình client cho local decryption

Client cần dependency hỗ trợ giải mã và key material riêng.

Ví dụ dependency Maven:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-rsa</artifactId>
</dependency>
```

Ví dụ cấu hình client dùng symmetric key:

```yaml
encrypt:
  key: ${CONFIG_DECRYPT_KEY}
```

Với RSA, cấu hình keystore của client trỏ đến keystore chứa private key:

```yaml
encrypt:
  key-store:
    location: ${CLIENT_KEYSTORE_LOCATION}
    password: ${CLIENT_KEYSTORE_PASSWORD}
    alias: payment-service-private
    type: PKCS12
```

Các giá trị trên phải được cấp từ secret store hoặc workload identity phù hợp. Cần xác minh phiên bản Spring Cloud Commons, Spring Security RSA và cách nạp bootstrap/config data của ứng dụng để key có sẵn ở thời điểm Environment pre-processor giải mã.

Không để `CONFIG_DECRYPT_KEY`, private keystore hoặc password trong Config Server repository chung. Nếu client nhận key của chính nó từ cùng remote repository mà nó cần giải mã, sẽ xuất hiện phụ thuộc vòng: client cần key để đọc cấu hình nhưng key lại nằm trong cấu hình cần giải mã.

## 10. Quản lý khóa riêng theo application và profile

Nếu nhiều ứng dụng dùng cùng một key, phạm vi ảnh hưởng khi key bị lộ sẽ rộng. Spring Cloud Config hỗ trợ endpoint mã hóa theo application/profile và cơ chế `TextEncryptorLocator` để chọn encryptor khác nhau.

Đường dẫn endpoint có thể bao gồm application và profile, ví dụ dạng:

```text
POST /encrypt/{application}/{profiles}
```

Để thực sự chọn key khác nhau theo application/profile, cần cung cấp bean `TextEncryptorLocator` triển khai logic định vị encryptor. Locator mặc định không tự tạo một key riêng cho mỗi application/profile; nếu không tùy biến, các thao tác có thể vẫn dùng cùng một key.

Với RSA và keystore có nhiều alias, ciphertext có thể chứa metadata key alias:

```yaml
payment:
  password: '{cipher}{key:payment-2026}ENCRYPTED_VALUE'
```

Server dùng alias trong prefix để tìm encryptor phù hợp theo cơ chế key locator. Khi luân chuyển key, cần bảo đảm alias mới có mặt ở nơi giải mã trước khi commit ciphertext sử dụng alias đó.

Không nhúng secret hoặc private key vào `{key:...}`. Prefix này chỉ định danh key/alias; nó không phải nơi lưu key material.

## 11. Lỗi giải mã và cách nhận biết

### Server-side decryption thất bại

Nếu Config Server không giải mã được một property, theo mặc định server loại giá trị đó khỏi property source và thêm property có tên bắt đầu bằng `invalid`, ví dụ:

```json
{
  "source": {
    "invalid.spring.datasource.password": "<n/a>"
  }
}
```

Hành vi này giúp ciphertext không bị sử dụng nhầm như mật khẩu. Nếu cùng khóa có giá trị ở property source ưu tiên thấp hơn, ứng dụng có thể nhận giá trị dự phòng đó. Vì vậy, phải kiểm tra `invalid.*` trong response và log server, không chỉ nhìn thấy ứng dụng khởi động thành công.

Có thể cấu hình `spring.cloud.config.server.encrypt.prefix-invalid-properties=false` để không đổi tên property lỗi giải mã. Tuy nhiên, khi làm vậy response có thể chứa ciphertext dưới tên khóa gốc; client có nguy cơ dùng ciphertext như plaintext nếu không xử lý đúng. Chỉ thay đổi hành vi này khi đã có cơ chế phát hiện lỗi rõ ràng.

### Client-side decryption thất bại

Ở mô hình client-side, cần kiểm tra:

- Client có dependency `spring-security-rsa` phù hợp không.
- Key hoặc keystore có được nạp đủ sớm không.
- Symmetric key có khớp key dùng để mã hóa không.
- RSA private key có tương ứng với public key đã mã hóa không.
- Ciphertext có bị cắt, đổi ký tự hoặc mất prefix `{cipher}` không.
- Key alias trong prefix có tồn tại và được phép sử dụng không.

Không log ciphertext cùng plaintext, key hoặc exception context chứa secret. Khi giải mã thất bại, hãy dừng khởi động hoặc đánh dấu cấu hình không hợp lệ theo chính sách của dịch vụ; không tự động dùng chuỗi ciphertext như password.

## 12. Bảo mật các endpoint mã hóa/giải mã

`/encrypt` và `/decrypt` là endpoint nhạy cảm. Người có quyền gọi `/decrypt` với ciphertext phù hợp có thể lấy plaintext. Vì vậy:

- Bảo vệ endpoint bằng xác thực và phân quyền chặt chẽ.
- Chỉ cho phép service account hoặc nhóm vận hành có nhiệm vụ quản lý secret truy cập.
- Dùng HTTPS và giới hạn endpoint trong mạng quản trị.
- Không expose `/encrypt` hoặc `/decrypt` công khai chỉ vì endpoint tiện cho developer.
- Không log request body, response plaintext, symmetric key, private key hoặc keystore password.
- Theo dõi audit: ai mã hóa/giải mã, thời điểm và phạm vi ứng dụng/profile, nhưng không ghi nội dung bí mật.
- Có quy trình thu hồi credential và key rotation khi phát hiện lộ khóa.

Mã hóa giá trị trong Git chỉ bảo vệ dữ liệu ở trạng thái lưu trữ khỏi người không có key. Nó không thay thế TLS, authorization, secret manager hoặc bảo vệ plaintext trong memory, Actuator endpoint, heap dump và log ứng dụng.

## 13. Quy trình luân chuyển khóa

Khi khóa bị lộ hoặc cần thay đổi định kỳ, không thay key một cách đột ngột khi repository vẫn chứa ciphertext chỉ giải mã được bằng key cũ.

Quy trình tham khảo:

1. Tạo key mới và lưu ở secret manager/keystore an toàn.
2. Cấp key mới đến đúng nơi giải mã: Config Server nếu server-side, hoặc các client đích nếu client-side.
3. Xác nhận tất cả instance có thể nạp key mới và alias tương ứng.
4. Mã hóa lại các giá trị cần chuyển bằng key mới; với keystore nhiều alias, thêm prefix `{key:new-alias}` theo cơ chế đã cấu hình.
5. Review và commit ciphertext mới vào repository.
6. Xác nhận endpoint Config Server trả đúng dạng ciphertext/plaintext theo mô hình đã chọn.
7. Refresh hoặc restart client theo yêu cầu, rồi kiểm tra kết nối thực tế dùng secret mới.
8. Sau thời gian chuyển đổi và xác nhận không còn ciphertext cần key cũ, thu hồi key cũ.

Nếu có sự cố lộ key, rút ngắn thời gian chuyển đổi theo quy trình incident response. Không xóa key cũ trước khi biết tất cả ciphertext còn được sử dụng đã được mã hóa lại.

## 14. Chọn mô hình theo tình huống

| Tình huống | Hướng phù hợp để đánh giá | Lý do |
|---|---|---|
| Nhiều client, muốn tập trung key management | Server-side decryption | Chỉ server giữ key giải mã; client nhận plaintext qua TLS. |
| Server không nên giữ private key | Client-side với RSA | Server có thể chỉ giữ public key; private key ở client. |
| Một nhóm nhỏ client cần một secret riêng | Client-side với key riêng theo application/profile | Có thể giới hạn client nào có private key phù hợp. |
| Tổ chức chưa có quy trình cấp key cho workload | Server-side có kiểm soát chặt | Tránh phát tán key đến nhiều ứng dụng, nhưng phải bảo vệ server và response. |
| Tất cả client dùng chung một symmetric key | Cần đánh giá lại blast radius | Một client bị xâm nhập có thể giải mã mọi ciphertext dùng cùng key. |

Trong nhiều hệ thống, secret manager hoặc Vault có thể phù hợp hơn việc tự quản lý ciphertext trong Git. Hãy so sánh yêu cầu audit, rotation, access policy và vận hành trước khi quyết định dùng tính năng mã hóa của Config Server.

## 15. Bài thực hành

### Bước 1: Mã hóa một property

Thiết lập Config Server trong môi trường local với key thử nghiệm. Gọi `POST /encrypt`, thêm prefix `{cipher}` và lưu ciphertext vào `application.yml` trong repository thử nghiệm.

**Kết quả cần đạt:** xác nhận repository lưu ciphertext, không lưu plaintext.

### Bước 2: Thử server-side decryption

Giữ outgoing decryption ở trạng thái mặc định, gọi endpoint `/{application}/{profile}/{label}` và quan sát property response. Xác nhận giá trị trả về đã là plaintext trong môi trường thử nghiệm được bảo vệ.

**Kết quả cần đạt:** hiểu Config Server giữ key và giải mã trước khi trả client.

### Bước 3: Thử client-side decryption

Đặt `spring.cloud.config.server.encrypt.enabled=false` trong bootstrap config của server. Thêm `spring-security-rsa` và key thử nghiệm vào client. Gọi endpoint server để xác nhận response còn ciphertext, sau đó kiểm tra Environment cục bộ đã giải mã.

**Kết quả cần đạt:** phân biệt response HTTP với giá trị ứng dụng thực sự sử dụng.

### Bước 4: Thử lỗi key

Dùng sai key hoặc alias trong môi trường thử nghiệm. Quan sát log, `invalid.*` nếu server-side giải mã thất bại, hoặc lỗi local decryption ở client. Khôi phục key đúng và xác nhận ứng dụng hoạt động.

**Kết quả cần đạt:** không để ciphertext bị dùng nhầm như plaintext.

### Bước 5: Kiểm tra ranh giới bảo mật

Thử gọi `/decrypt` bằng danh tính không có quyền, kiểm tra HTTPS, log và Actuator. Xác nhận client không có key không thể giải mã ciphertext trong mô hình RSA client-side.

**Kết quả cần đạt:** hiểu rằng quyền đọc Config Server và quyền giải mã secret là hai quyền cần quản lý riêng khi chọn client-side.

### Bước 6: Diễn tập key rotation

Tạo key/alias mới, mã hóa lại property, triển khai key mới đến nơi giải mã, cập nhật ciphertext, refresh client và chỉ sau khi xác nhận mới thu hồi key cũ.

**Kết quả cần đạt:** luân chuyển key không làm gián đoạn ứng dụng hoặc khiến ciphertext không thể giải mã.

## 16. Tự kiểm tra

1. Theo mặc định, Config Server xử lý giá trị `{cipher}` trước khi gửi client như thế nào?
2. Khác biệt quan trọng nhất giữa server-side và client-side decryption là gì?
3. Vì sao server-side decryption yêu cầu bảo vệ plaintext response bằng TLS?
4. Khi client-side decryption, thuộc tính nào tắt outgoing decryption ở Config Server?
5. Client cần dependency nào để giải mã property cục bộ?
6. Khóa đối xứng và RSA phân chia quyền mã hóa/giải mã khác nhau thế nào?
7. Vì sao dùng chung một symmetric key cho nhiều client làm tăng blast radius?
8. Server có thể chỉ giữ public key trong mô hình RSA client-side không?
9. Khi server không giải mã được property, `invalid.*` có ý nghĩa gì?
10. Vì sao phải bảo vệ `/encrypt` và `/decrypt`?
11. `TextEncryptorLocator` giúp ích gì khi dùng key riêng theo application/profile?
12. Trình tự an toàn khi luân chuyển key gồm những bước nào?

Khi hoàn thành bài thực hành, người học có thể lựa chọn nơi giải mã phù hợp với ranh giới tin cậy, cấu hình key cho server hoặc client, nhận biết lỗi giải mã và quản lý vòng đời khóa mà không làm lộ plaintext hoặc làm gián đoạn dịch vụ.

## Tài liệu tham khảo

- [Spring Cloud Config – Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html): `{cipher}`, `/encrypt`, `/decrypt` và xử lý lỗi giải mã.
- [Spring Cloud Config – Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html): tắt giải mã outgoing để client giải mã cục bộ.
- [Spring Cloud Config – Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html): symmetric key, RSA keystore và phân chia public/private key.
- [Spring Cloud Commons – Encryption and Decryption](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html#encryption-and-decryption): Environment pre-processor và dependency giải mã ở client.

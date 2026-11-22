# Xoay vòng khóa và khả năng đọc cấu hình đã mã hóa

Mã hóa cấu hình chỉ có ích khi ứng dụng còn có thể giải mã dữ liệu trong suốt vòng đời vận hành. Một mật khẩu đã được mã hóa trong Git vẫn phải được Config Server hoặc Config Client giải mã đúng lúc khởi động. Khi thay khóa, hệ thống cần tiếp tục đọc được ciphertext được tạo bằng khóa cũ trong thời gian chuyển tiếp, đồng thời bắt đầu tạo ciphertext mới bằng khóa mới.

Trong Spring Cloud Config, Config Server hỗ trợ khóa đối xứng và khóa bất đối xứng. Với keystore có nhiều alias, ciphertext có thể chỉ rõ alias cần dùng bằng tiền tố như {key:config-2026}. Cơ chế này cho phép giữ khóa cũ và khóa mới đồng thời trong giai đoạn migration. Sau khi mọi cấu hình và bản rollback còn được hỗ trợ đã chuyển sang khóa mới, alias cũ mới có thể được gỡ khỏi keyring đang hoạt động.

Bài học thuộc chương **Mã hóa cấu hình** của module **SPRING_CLOUD_CORE**. Nội dung kết nối cấu hình bên ngoài, Spring Cloud Config, quản lý secret, refresh và khả năng khôi phục ứng dụng. Trọng tâm là duy trì khả năng đọc ciphertext cũ, triển khai khóa mới có kiểm soát và xác minh từng Config Server trước khi kết thúc chuyển đổi.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt khóa đối xứng, khóa bất đối xứng và vai trò của keystore alias.
2. Giải thích cách Config Server xử lý giá trị có tiền tố {cipher}.
3. Cấu hình khóa mã hóa qua secret được inject lúc chạy thay vì commit vào repository.
4. Dùng nhiều alias để duy trì khả năng giải mã trong quá trình xoay vòng khóa.
5. Lập kế hoạch triển khai dual-key trước khi đổi ciphertext trong Git.
6. Phân biệt mã hóa/giải mã ở Config Server với giải mã tại Config Client.
7. Nhận diện lỗi giải mã và tránh dùng ciphertext như giá trị mật khẩu.
8. Kiểm thử khả năng đọc cấu hình cũ, cấu hình mới và bản rollback.
9. Bảo vệ endpoint /encrypt, /decrypt và tài liệu chứa ciphertext.
10. Xây dựng quy trình xoay vòng định kỳ và xử lý sự cố khi khóa bị lộ.

## 2. Vì sao phải xoay vòng khóa có kế hoạch?

Giả sử Config Server đang dùng khóa K1 để mã hóa mật khẩu kết nối database. Repository lưu ciphertext C1 và các client lấy cấu hình thông qua Config Server.

Khi tổ chức thay K1 bằng K2, nếu chỉ thay key trên Config Server thì C1 có thể không còn giải mã được. Ứng dụng có thể nhận lỗi cấu hình, giá trị bị loại bỏ hoặc một giá trị fallback từ property source khác. Hệ quả có thể là service không khởi động, không kết nối database hoặc dùng một giá trị không mong muốn.

Một lần thay khóa vì vậy liên quan tới ba thứ:

- **Khóa đang hoạt động:** key material hoặc alias mà Config Server có thể sử dụng.
- **Ciphertext đang lưu:** các giá trị đã mã hóa trong Git, file hoặc nguồn cấu hình.
- **Các phiên bản cấu hình cần hỗ trợ:** revision hiện tại, nhánh triển khai, tag release và revision có thể cần rollback.

~~~mermaid
flowchart TD
    A[Repository chứa ciphertext C1] --> B[Config Server]
    K1[Key K1] --> B
    B --> C[Giải mã cấu hình]
    C --> D[Config Client nhận giá trị]
    E[Thay K1 bằng K2 ngay lập tức] --> F[C1 không còn giải mã được]
    F --> G[Startup hoặc refresh lỗi]
~~~

Thay khóa mà không chuyển ciphertext là một thay đổi không tương thích. Quy trình an toàn cần có khoảng thời gian mà hệ thống giải mã được cả ciphertext cũ và ciphertext mới.

## 3. Cơ chế mã hóa của Spring Cloud Config

### 3.1. Tiền tố {cipher}

Config Server nhận diện giá trị mã hóa bằng tiền tố {cipher}. Ví dụ trong file YAML:

~~~yaml
spring:
  datasource:
    username: app_user
    password: '{cipher}CIPHERTEXT_FROM_CONFIG_SERVER'
~~~

Dấu nháy đơn quanh giá trị YAML giúp parser giữ nguyên chuỗi có dấu ngoặc nhọn. Trong file application.properties, ghi giá trị không bọc dấu nháy:

~~~properties
spring.datasource.username=app_user
spring.datasource.password={cipher}CIPHERTEXT_FROM_CONFIG_SERVER
~~~

Tài liệu Spring Cloud Config lưu ý giá trị mã hóa trong file Properties không được bọc dấu nháy, nếu không quá trình giải mã có thể không nhận diện đúng.

Khi Config Server nhận property source từ repository, giá trị bắt đầu bằng {cipher} được giải mã trước khi gửi cho client theo chế độ mặc định. Nhờ vậy, repository có thể lưu ciphertext trong khi client nhận giá trị plaintext qua kết nối Config Server được bảo vệ bằng TLS.

### 3.2. Mã hóa lúc lưu và plaintext lúc sử dụng

Mã hóa cấu hình trong Git chủ yếu bảo vệ dữ liệu **at rest**. Nó không có nghĩa secret luôn được mã hóa trong toàn bộ vòng đời:

1. Plaintext được gửi tới endpoint mã hóa hoặc công cụ mã hóa tin cậy.
2. Ciphertext được lưu trong repository.
3. Config Server đọc ciphertext.
4. Config Server giải mã trong bộ nhớ.
5. Client nhận plaintext nếu server-side decryption đang bật.
6. Giá trị có thể tồn tại trong Environment, object cấu hình hoặc bộ nhớ của client.

Do đó vẫn cần bảo vệ TLS, Config Server, quyền truy cập repository, log, Actuator, memory dump và quyền đọc cấu hình theo từng ứng dụng. Không coi tiền tố {cipher} là một hệ thống quản lý secret hoàn chỉnh.

### 3.3. Endpoint mã hóa và giải mã

Config Server cung cấp hai endpoint:

- POST /encrypt: mã hóa plaintext và trả về ciphertext.
- POST /decrypt: giải mã ciphertext và trả về plaintext.

Ví dụ dùng giá trị được cấp qua biến môi trường trong shell:

~~~bash
printf '%s' "$SECRET_VALUE" | curl -sS \
  -X POST \
  -H 'Content-Type: text/plain' \
  --data-binary @- \
  https://config.example.internal/encrypt
~~~

Để giải mã, gửi ciphertext đã nhận tới endpoint /decrypt:

~~~bash
printf '%s' "$CIPHERTEXT" | curl -sS \
  -X POST \
  -H 'Content-Type: text/plain' \
  --data-binary @- \
  https://config.example.internal/decrypt
~~~

Đây là ví dụ minh họa. Không đưa secret thật trực tiếp vào command history, ticket, chat hoặc log CI. Endpoint /decrypt trả plaintext nên cần quyền truy cập chặt hơn; không expose endpoint này cho người dùng hoặc mạng công khai.

Nếu gửi giá trị có ký tự đặc biệt bằng curl, cần bảo đảm request body được truyền nguyên vẹn. Tài liệu Spring Cloud Config gợi ý dùng --data-urlencode với cú pháp phù hợp hoặc đặt Content-Type là text/plain; dấu cộng (+) là một ký tự dễ bị xử lý sai nếu body bị encode không đúng.

## 4. Các loại khóa và nơi lưu khóa

### 4.1. Khóa đối xứng

Khóa đối xứng dùng cùng một bí mật cho mã hóa và giải mã. Config Server có thể nhận khóa qua thuộc tính:

~~~properties
encrypt.key=SECRET_VALUE_INJECTED_AT_RUNTIME
~~~

Hoặc qua biến môi trường:

~~~bash
ENCRYPT_KEY
~~~

Không commit giá trị thật của encrypt.key vào application.yml, application.properties, Docker image hoặc Git. Hãy inject từ secret manager, môi trường triển khai hoặc cơ chế quản lý secret của nền tảng.

Ưu điểm:

- Cấu hình đơn giản.
- Một giá trị khóa cần quản lý.
- Phù hợp với mô hình chỉ Config Server giữ khóa và giải mã.

Hạn chế:

- Thành phần có khóa có thể vừa mã hóa vừa giải mã.
- Nếu khóa bị lộ, ciphertext được bảo vệ bằng khóa đó có nguy cơ bị giải mã.
- Một khóa dùng chung cho nhiều ứng dụng làm tăng phạm vi ảnh hưởng khi xảy ra sự cố.
- Việc thay khóa cần chuyển đổi ciphertext hoặc có chiến lược hỗ trợ nhiều encryptor.

Không giả định cơ chế nhiều alias của keystore tự động áp dụng cho một giá trị encrypt.key đối xứng đơn lẻ. Tài liệu Spring Cloud Config mô tả key alias trong luồng nhiều khóa với keystore và TextEncryptorLocator; nếu cần nhiều khóa đối xứng, phải thiết kế locator/encryptor tùy chỉnh hoặc chuyển đổi dữ liệu theo quy trình tương thích riêng.

### 4.2. Khóa bất đối xứng

Mã hóa bất đối xứng sử dụng một cặp khóa:

- Public key dùng để mã hóa.
- Private key dùng để giải mã.

Spring Cloud Config có thể đọc key pair từ keystore. Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| encrypt.keyStore.location | Vị trí Resource chứa keystore |
| encrypt.keyStore.password | Mật khẩu mở keystore |
| encrypt.keyStore.alias | Alias xác định key entry |
| encrypt.keyStore.type | Loại keystore; mặc định JKS theo tài liệu |

Ví dụ cấu trúc cấu hình, với giá trị bí mật được inject từ môi trường triển khai:

~~~yaml
encrypt:
  keyStore:
    location: file:/run/secrets/config-server.jks
    type: JKS
    alias: config-current
    password: KEYSTORE_PASSWORD_INJECTED_AT_RUNTIME
~~~

Đây chỉ là giá trị minh họa cho mật khẩu được inject; không dùng chuỗi ví dụ làm mật khẩu thật. Đường dẫn keystore phải được bảo vệ và chỉ Config Server hoặc thành phần có trách nhiệm mới được đọc private key.

### 4.3. Phân tách quyền mã hóa và giải mã

Với khóa bất đối xứng, về nguyên tắc có thể chỉ cung cấp public key cho thành phần thực hiện mã hóa và giữ private key ở nơi giải mã. Cách này giảm số thành phần cần giữ khả năng giải mã.

Nếu Config Server giải mã trước khi gửi client, Config Server phải có private key. Nếu client giải mã cục bộ, private key phải được cung cấp tới client. Điều đó mở rộng phạm vi phân phối và quản lý private key tới nhiều service, làm tăng trách nhiệm bảo vệ khóa.

### 4.4. Keystore không tự động là KMS

Keystore là định dạng lưu trữ key material và metadata. Nó không tự cung cấp đầy đủ các tính năng như:

- Phê duyệt truy cập theo danh tính workload.
- Audit tập trung cho mọi lần sử dụng khóa.
- Rotation policy tự động.
- HSM-backed key operations.
- Revocation và phân quyền theo môi trường.
- Phân tách quyền giữa người mã hóa và người giải mã.

Có thể tích hợp secret manager, Vault, KMS hoặc HSM để bảo vệ khóa và mật khẩu keystore. Việc tích hợp cụ thể cần được thiết kế theo nền tảng; không giả định chỉ khai báo encrypt.keyStore.location là Spring Cloud Config đã kết nối một KMS.

## 5. Khả năng đọc ciphertext cũ

### 5.1. Vấn đề khi thay khóa ngay lập tức

Giả sử repository có:

~~~yaml
database:
  password: '{cipher}CIPHERTEXT_ENCRYPTED_WITH_K1'
~~~

Config Server hiện chỉ có K1. Nếu thay toàn bộ key material bằng K2 mà chưa mã hóa lại giá trị trong repository, server không còn khả năng giải mã ciphertext cũ.

Một ứng dụng có thể gặp các biểu hiện:

- Giá trị cấu hình bị đánh dấu invalid.
- Property không được cung cấp như mong đợi.
- Một property source thấp hơn cung cấp fallback cùng tên được chọn.
- Bean cấu hình không bind được.
- Client khởi động nhưng kết nối dependency thất bại.

Không nên coi việc ứng dụng vẫn khởi động là bằng chứng migration thành công. Cần xác minh giá trị cuối cùng và nguồn cung cấp nó.

### 5.2. Duy trì hai khóa trong thời gian chuyển tiếp

Với keystore nhiều alias, có thể giữ K1 và K2 đồng thời:

~~~text
Config Server keystore
  config-legacy  -> private key K1
  config-current -> private key K2
~~~

Ciphertext cũ chỉ alias K1:

~~~yaml
database:
  password: '{cipher}{key:config-legacy}CIPHERTEXT_OLD'
~~~

Ciphertext mới chỉ alias K2:

~~~yaml
database:
  password: '{cipher}{key:config-current}CIPHERTEXT_NEW'
~~~

Config Server dùng alias trong tiền tố để tìm key phù hợp. Trong giai đoạn chuyển tiếp, cả hai alias phải có mặt và khả dụng trên **mọi replica Config Server** có thể nhận request từ client.

Không chỉ thêm key mới vào một node. Nếu load balancer gửi request tới node còn thiếu alias mới, kết quả giải mã sẽ không nhất quán giữa các request.

### 5.3. Tiền tố key alias

Với keystore, Spring Cloud Config hỗ trợ tiền tố dạng:

~~~text
{cipher}{key:config-current}BASE64_CIPHERTEXT
~~~

Default locator dùng alias được chỉ ra trong tiền tố để tìm key trong keystore. Tài liệu cũng mô tả tiền tố secret tùy chọn; nếu cung cấp secret riêng, cần triển khai SecretLocator phù hợp để xử lý bí mật đó.

Tên alias nên thể hiện mục đích hoặc phiên bản, ví dụ:

~~~text
config-2025
config-2026
config-incident-rotation-01
~~~

Không đưa secret hoặc mật khẩu vào alias. Alias là định danh không bí mật để chọn key entry, không phải nơi lưu key material.

### 5.4. Default locator và tùy biến

Spring Cloud Config dùng TextEncryptorLocator để tìm encryptor phù hợp cho ciphertext. Default locator hỗ trợ chọn alias từ keystore theo tiền tố key. Nếu muốn chọn encryptor theo application, profile, tenant hoặc chính sách riêng, có thể cung cấp TextEncryptorLocator tùy chỉnh.

Tài liệu hiện hành lưu ý default locator không tự tạo một key riêng cho từng application/profile; mặc định các lần mã hóa dùng chung key. Nếu cần tách khóa theo ứng dụng hoặc profile, phải tự thiết kế locator và kiểm thử rõ cách định tuyến.

## 6. Quy trình xoay vòng khóa với keystore nhiều alias

Một quy trình chuyển K1 sang K2 nên chia thành các giai đoạn. Mục tiêu là không có thời điểm Config Server nhận ciphertext mới mà thiếu key để giải mã, đồng thời vẫn giữ khả năng đọc revision cũ trong thời gian rollback.

### 6.1. Giai đoạn 0 — Kiểm kê

Trước khi thay đổi, lập danh sách:

- Các ứng dụng và profile đang dùng ciphertext.
- Repository, branch, tag và label chứa ciphertext.
- Alias hiện đang được tham chiếu.
- Các Config Server instance và keystore của từng instance.
- Cơ chế backup/restore keystore.
- Quyền truy cập endpoint /encrypt và /decrypt.
- Quy trình rollback và thời gian cần hỗ trợ revision cũ.

Không tìm kiếm secret bằng cách giải mã hàng loạt vào log hoặc file tạm không được bảo vệ. Chỉ cần inventory alias, property path và revision; không cần công bố plaintext.

### 6.2. Giai đoạn 1 — Thêm khóa mới vào keyring

Tạo key pair mới và thêm alias mới vào keystore. Mỗi Config Server instance phải có khả năng đọc alias cũ và mới.

~~~text
Before:
  config-legacy

Transition:
  config-legacy
  config-current
~~~

Triển khai keystore tương thích tới toàn bộ Config Server replica trước khi cập nhật ciphertext trong repository.

Kiểm tra trên từng node:

1. Keystore được mount đúng đường dẫn.
2. Mật khẩu keystore được inject thành công.
3. Alias cũ tồn tại.
4. Alias mới tồn tại.
5. Config Server có thể khởi tạo encryptor với từng alias.
6. Không có log chứa private key hoặc mật khẩu.

Không xóa alias cũ ở bước này.

### 6.3. Giai đoạn 2 — Kiểm thử hai chiều

Trước khi sửa repository, dùng một giá trị test không nhạy cảm để xác minh:

- Ciphertext cũ giải mã được bằng alias cũ.
- Ciphertext mới tạo bằng alias mới giải mã được bằng alias mới.
- Tất cả Config Server replica trả cùng kết quả.
- Client lấy được giá trị cấu hình dự kiến.
- Không có replica nào đang dùng keystore cũ.

Nếu có nhiều Config Server sau load balancer, kiểm thử từng instance trực tiếp trong mạng quản trị và sau đó kiểm thử qua endpoint chung.

### 6.4. Giai đoạn 3 — Tạo ciphertext mới

Có thể gửi tiền tố alias trong nội dung POST tới /encrypt để yêu cầu Config Server dùng key tương ứng. Ví dụ minh họa:

~~~bash
printf '%s' "$SECRET_VALUE" | curl -sS \
  -X POST \
  -H 'Content-Type: text/plain' \
  --data-binary @- \
  https://config.example.internal/encrypt
~~~

Nếu cần chọn alias, gửi tiền tố key theo cú pháp mà Config Server hỗ trợ trong request plaintext, hoặc dùng công cụ mã hóa được cấu hình với alias mới. Xác minh kết quả có đúng alias mong muốn trước khi ghi vào repository.

Không giả định endpoint /encrypt luôn chọn alias mới chỉ vì alias mới vừa được thêm vào keystore. Alias mặc định và lựa chọn key phụ thuộc cấu hình keystore/locator. Phải kiểm tra ciphertext đầu ra hoặc dùng cơ chế chọn alias tường minh.

### 6.5. Giai đoạn 4 — Cập nhật repository

Thay ciphertext cũ bằng ciphertext mới:

~~~yaml
spring:
  datasource:
    password: '{cipher}{key:config-current}CIPHERTEXT_ENCRYPTED_WITH_K2'
~~~

Giữ nguyên property name, kiểu dữ liệu và profile scope để giảm thay đổi ngoài ý muốn. Nếu thay đổi cả tên property hoặc cấu trúc cấu hình cùng lúc, việc chẩn đoán lỗi sẽ khó hơn.

Với file Properties:

~~~properties
spring.datasource.password={cipher}{key:config-current}CIPHERTEXT_ENCRYPTED_WITH_K2
~~~

Không bọc giá trị Properties trong dấu nháy. Với YAML, bọc chuỗi bằng dấu nháy để parser không hiểu phần dấu ngoặc nhọn như cấu trúc YAML.

### 6.6. Giai đoạn 5 — Xác minh client và rollout

Sau khi repository có ciphertext mới:

1. Lấy cấu hình theo đúng application/profile/label.
2. Xác nhận Config Server giải mã thành công.
3. Kiểm tra property cuối cùng trong Environment của client ở môi trường được bảo vệ.
4. Kiểm tra bean cấu hình và kết nối dependency.
5. Thực hiện refresh hoặc restart client theo khả năng hỗ trợ của thay đổi.
6. Theo dõi mọi replica client, không chỉ một instance.
7. Ghi nhận revision cấu hình đã xác minh.

Nếu server-side decryption được bật, client nhận plaintext. Không cần đưa private key K2 tới client trong mô hình này.

### 6.7. Giai đoạn 6 — Giữ khóa cũ trong cửa sổ rollback

Sau khi cấu hình mới chạy ổn định, giữ alias cũ trong thời gian đã xác định. Các nguồn còn có thể chứa ciphertext cũ gồm:

- Branch chưa được merge.
- Tag release cũ.
- Revision cấu hình đang được một môi trường khác sử dụng.
- Backup repository.
- Artifact hoặc snapshot có chứa cấu hình.
- Bản cấu hình được lưu để rollback.

Nếu rollback về revision cũ, Config Server vẫn phải có key để giải mã ciphertext cũ. Xóa K1 quá sớm có thể khiến rollback thất bại.

### 6.8. Giai đoạn 7 — Gỡ alias cũ

Chỉ gỡ alias cũ khỏi keyring đang hoạt động khi:

- Mọi cấu hình cần hỗ trợ đã được chuyển sang K2.
- Không còn môi trường nào dùng ciphertext K1.
- Cửa sổ rollback đã đóng hoặc đã có kế hoạch re-encrypt bản rollback.
- Backup cần phục hồi đã được xử lý theo chính sách retention.
- Kiểm thử xác nhận cấu hình mới vẫn đọc được khi chỉ còn K2.

Nếu K1 bị lộ, quy trình ứng phó sự cố có thể cần rút ngắn thời gian giữ khóa cũ. Khi đó ưu tiên ngăn khả năng giải mã trái phép, re-encrypt và triển khai khẩn cấp; mọi bản rollback dùng K1 phải được coi là không còn an toàn để phục hồi nguyên trạng.

~~~mermaid
flowchart TD
    A[Kiểm kê ciphertext và alias cũ] --> B[Thêm K2, giữ K1 trên mọi Config Server]
    B --> C[Kiểm thử giải mã K1 và K2]
    C --> D[Mã hóa secret mới bằng K2]
    D --> E[Commit ciphertext có alias K2]
    E --> F[Client đọc cấu hình và xác minh]
    F --> G[Giữ K1 trong cửa sổ rollback]
    G --> H{Còn revision cần K1?}
    H -->|Có| G
    H -->|Không| I[Gỡ alias K1 theo quy trình]
~~~

## 7. Xử lý khóa đối xứng khi không dùng keystore alias

Nếu Config Server chỉ dùng một encrypt.key đối xứng, việc thay giá trị khóa ngay lập tức làm ciphertext cũ không thể giải mã bằng khóa mới.

Một quy trình chuyển đổi đơn giản cần:

1. Lập inventory toàn bộ ciphertext được tạo bằng K1.
2. Bảo đảm có thể giải mã bằng K1 trong môi trường được kiểm soát.
3. Tạo ciphertext mới bằng K2 cho tất cả property cần giữ.
4. Xác minh từng ciphertext mới bằng K2.
5. Triển khai K2 cùng repository đã được chuyển đổi theo một trình tự tương thích.
6. Giữ bản phục hồi cần thiết theo chính sách, nhưng không để khóa bị lộ tiếp tục có quyền truy cập rộng.
7. Sau khi chuyển đổi hoàn tất, loại K1 khỏi cấu hình đang hoạt động.

Điểm khó là nếu không có cơ chế chọn key theo ciphertext, một Config Server chỉ có một symmetric key không thể mặc định đọc cả ciphertext K1 và K2 cùng lúc. Cần lên kế hoạch tránh khoảng thời gian cấu hình và key không tương thích.

Nếu cần dual-key cho symmetric encryption, có thể triển khai TextEncryptorLocator tùy chỉnh để định tuyến theo key ID/version trong tiền tố hoặc metadata đã được thiết kế. Cần kiểm tra tính tương thích, quản lý secret và khả năng giải mã dữ liệu cũ bằng integration test. Không tự chế tiền tố tùy ý rồi giả định default locator hiểu được.

## 8. Giải mã ở Config Server hay Config Client?

### 8.1. Server-side decryption — mặc định

Theo cơ chế mặc định, Config Server giải mã giá trị có tiền tố {cipher} trước khi trả property source qua HTTP.

~~~mermaid
sequenceDiagram
    participant Git as Config repository
    participant Server as Config Server
    participant Key as Keystore / key
    participant Client as Config Client
    Git->>Server: Ciphertext {cipher}
    Server->>Key: Chọn alias và giải mã
    Key-->>Server: Plaintext
    Server-->>Client: Property source đã giải mã
~~~

Ưu điểm:

- Private key hoặc symmetric key tập trung ở Config Server.
- Client không cần giữ khóa giải mã.
- Việc xoay vòng khóa tập trung hơn.
- Client không cần tự triển khai crypto integration.

Đổi lại, Config Server trở thành thành phần có quyền truy cập plaintext của nhiều ứng dụng. Cần bảo vệ service, giới hạn quyền đọc theo application/profile và kiểm soát operator có thể gọi endpoint giải mã.

### 8.2. Client-side decryption

Trong một số kiến trúc, muốn client nhận ciphertext và tự giải mã cục bộ. Spring Cloud Config có tùy chọn tắt giải mã outgoing properties:

~~~properties
spring.cloud.config.server.encrypt.enabled=false
~~~

Tài liệu Spring Cloud Config mô tả cấu hình này trong bootstrap configuration của Config Server. Hãy kiểm tra đúng chế độ bootstrap/Config Data và phiên bản đang sử dụng trước khi đặt property.

Khi client giải mã cục bộ:

- Config Server có thể giữ ciphertext và không cần private key để phục vụ cấu hình.
- Client phải được cung cấp key material phù hợp.
- Private key/symmetric key được phân phối tới nhiều workload hơn.
- Mỗi client phải có quy trình rotation và kiểm thử tương thích.
- Một client bị xâm nhập có thể làm lộ key dùng chung nếu phạm vi khóa quá rộng.

Chỉ chọn client-side decryption khi có lý do kiến trúc rõ ràng và khả năng quản lý khóa phân tán phù hợp.

### 8.3. Không trộn lẫn hai mô hình trong cùng một giả định

Nếu server-side decryption bật, client thường nhận plaintext. Nếu server-side decryption tắt, client có thể nhận ciphertext và cần decrypt local. Cần ghi rõ mô hình trong kiến trúc, tài liệu vận hành và test.

Không giả định chỉ vì client có Config Client starter là nó tự có private key hoặc sẽ tự giải mã mọi ciphertext trong mọi cấu hình. Kiểm tra integration, key material và hành vi response thực tế.

## 9. Lỗi giải mã và property invalid

### 9.1. Hành vi mặc định khi giải mã thất bại

Nếu Config Server không giải mã được giá trị, nó loại property đó khỏi property source và thêm một property có tên bắt đầu bằng invalid, ví dụ:

~~~json
{
  "propertySources": [
    {
      "name": "application-prod.yml",
      "source": {
        "invalid.database.password": "<n/a>"
      }
    }
  ]
}
~~~

Hành vi này giúp tránh việc ciphertext bị dùng nhầm làm password và vô tình rò rỉ sang log hoặc client.

### 9.2. Fallback từ property source thấp hơn

Nếu một property source khác có cùng key ở mức ưu tiên thấp hơn, client có thể nhận giá trị từ nguồn đó. Ví dụ, cấu hình chung có password mặc định trong khi profile production có ciphertext không giải mã được. Config Server có thể đánh dấu key invalid ở nguồn profile; client sau đó có thể resolve giá trị cùng tên từ nguồn khác.

Điều này có thể làm ứng dụng khởi động với fallback không mong muốn. Với secret bắt buộc, cần validation và kiểm thử để không âm thầm dùng credential mặc định.

### 9.3. Tắt invalid prefix có hệ quả gì?

Thuộc tính:

~~~properties
spring.cloud.config.server.encrypt.prefix-invalid-properties=false
~~~

có thể tắt hành vi thêm tiền tố invalid. Khi đó, nếu server không giải mã được, giá trị mã hóa có thể được trả về cho client như một chuỗi thông thường. Nếu client không giải mã tại chỗ, ciphertext có thể bị bind như password hoặc token và gây lỗi khó hiểu.

Không tắt invalid prefix chỉ để che cảnh báo. Chỉ cân nhắc khi kiến trúc client-side decryption đã được thiết kế, kiểm thử và bảo vệ đầy đủ.

### 9.4. Chẩn đoán mà không làm lộ secret

Khi gặp lỗi, ghi nhận:

- Application, profile và label được yêu cầu.
- Property name bị đánh dấu invalid.
- Alias/key ID được tham chiếu.
- Config Server instance xử lý request.
- Revision repository.
- Thời điểm và correlation ID.

Không ghi plaintext, private key, mật khẩu keystore hoặc toàn bộ ciphertext vào log nếu không cần thiết. Ciphertext không phải plaintext, nhưng vẫn là dữ liệu cần kiểm soát vì nó có thể được giải mã khi key bị lộ.

## 10. Bảo vệ endpoint /encrypt và /decrypt

### 10.1. Endpoint mã hóa không phải API công khai

Endpoint /encrypt nhận plaintext và trả ciphertext. Người được phép gọi có thể mã hóa dữ liệu sẽ được lưu trong repository. Cần xác thực, phân quyền và audit ai đã tạo ciphertext.

### 10.2. Endpoint giải mã có mức nhạy cảm cao hơn

Endpoint /decrypt trả plaintext. Quyền gọi endpoint này gần tương đương quyền đọc secret tương ứng. Chỉ cấp cho operator hoặc pipeline được ủy quyền và chỉ khi thực sự cần.

Không đưa /decrypt vào một route công khai hoặc dashboard không xác thực. Có thể tách quyền encrypt và decrypt để người tạo cấu hình không mặc nhiên có quyền xem mọi secret.

### 10.3. Bảo vệ Config Server

Các biện pháp cần có:

- TLS/HTTPS cho mọi client và operator.
- Authentication và authorization theo ứng dụng.
- Quyền repository tối thiểu.
- Phân tách quyền đọc cấu hình theo application/profile.
- Giới hạn network tới endpoint mã hóa/giải mã.
- Audit truy cập và thay đổi cấu hình.
- Secret injection cho key và keystore password.
- Không commit key material vào Git hoặc image.
- Không expose Actuator env/configprops và endpoint quản trị không cần thiết.

Theo tài liệu Spring Cloud Config, nếu không có access control theo application, một client đã xác thực có thể yêu cầu cấu hình của application khác bằng cách thay tên application trong URL. Nếu repository chứa secret cần cô lập theo service, phải triển khai authorization policy phù hợp.

### 10.4. Mã hóa không thay thế TLS

Ciphertext trong Git bảo vệ dữ liệu khi lưu. Khi server-side decryption được bật, plaintext đi từ Config Server tới client. Bắt buộc bảo vệ đường truyền bằng TLS và giới hạn quyền đọc. Không dùng mã hóa at-rest làm lý do bỏ HTTPS.

## 11. Tích hợp secret manager, Vault và KMS

Spring Cloud Config cung cấp cơ chế mã hóa cấu hình, nhưng tổ chức có thể cần một hệ thống quản lý key chuyên dụng.

Có thể phân tách trách nhiệm:

| Thành phần | Trách nhiệm |
| --- | --- |
| Git repository | Lưu ciphertext và lịch sử thay đổi |
| Config Server | Lấy property source, giải mã theo cấu hình và phục vụ client |
| Keystore | Lưu key entry và alias |
| Secret manager/Vault | Cung cấp mật khẩu keystore hoặc secret runtime theo quyền |
| KMS/HSM | Bảo vệ key operations và quản trị key material theo khả năng nền tảng |
| Deployment platform | Inject secret vào process/container và kiểm soát danh tính workload |

Không đưa toàn bộ trách nhiệm vào Git. Repository có thể chứa ciphertext nhưng không nên chứa private key, symmetric key, keystore password hoặc credential truy cập KMS.

Nếu dùng Vault/KMS, thiết kế adapter hoặc secret injection theo nền tảng. Kiểm tra startup order: Config Server phải lấy được key material trước khi xử lý request cấu hình. Nếu secret manager tạm thời không sẵn sàng, cần chính sách startup/failover rõ ràng thay vì chạy với khóa rỗng hoặc khóa mặc định.

## 12. Kiểm thử khả năng đọc cấu hình cũ và mới

Một bài test rotation không chỉ kiểm tra endpoint /encrypt. Nó cần xác nhận toàn bộ đường đi từ ciphertext trong repository đến giá trị mà client sử dụng.

### 12.1. Ma trận kiểm thử

| Trường hợp | Keyring Config Server | Ciphertext | Kết quả mong đợi |
| --- | --- | --- | --- |
| Trước rotation | K1 | Ciphertext K1 | Giải mã thành công |
| Dual-key transition | K1 + K2 | Ciphertext K1 | Giải mã thành công |
| Dual-key transition | K1 + K2 | Ciphertext K2 | Giải mã thành công |
| Sau migration | K2 | Ciphertext K2 | Giải mã thành công |
| Sau migration | K2 | Ciphertext K1 | Giải mã thất bại có kiểm soát |
| Alias không tồn tại | K1 + K2 | Ciphertext alias K3 | Không được dùng nhầm key khác |
| Sai private key/password | Keyring không mở được | Ciphertext bất kỳ | Startup hoặc decrypt báo lỗi rõ ràng |
| Rollback revision | K1 + K2 | Revision cũ dùng K1 | Giải mã thành công trong cửa sổ rollback |

### 12.2. Test trên từng Config Server replica

Nếu có ba Config Server node, kiểm tra cả ba:

1. Node 1 giải mã ciphertext cũ và mới.
2. Node 2 giải mã ciphertext cũ và mới.
3. Node 3 giải mã ciphertext cũ và mới.
4. Request qua load balancer cho kết quả nhất quán.
5. Không node nào còn mount keystore cũ thiếu alias K2.

Không chỉ kiểm tra một request qua load balancer; request có thể luôn tới cùng một node trong một lần thử.

### 12.3. Test Config Client

Từ một Config Client test:

- Request đúng application/profile/label.
- Xác nhận property source có giá trị dự kiến.
- Kiểm tra key invalid không xuất hiện.
- Kiểm tra bean @ConfigurationProperties bind thành công.
- Kiểm tra datasource/client có thể dùng credential mới.
- Kiểm tra refresh/restart theo cơ chế ứng dụng.
- Xác nhận log không chứa plaintext.

### 12.4. Test rollback

Khôi phục revision cũ trong môi trường kiểm thử trong khi keyring vẫn có K1 và K2. Xác nhận client vẫn đọc được ciphertext cũ. Sau khi gỡ K1 trong môi trường thử nghiệm, chạy lại test rollback để chứng minh chính sách retention đã được áp dụng đúng.

## 13. Quy trình xử lý khi khóa bị lộ

Xoay vòng định kỳ và ứng phó khóa bị lộ có mục tiêu khác nhau.

### 13.1. Đánh giá phạm vi ảnh hưởng

Xác định:

- Khóa nào bị lộ.
- Ciphertext nào được mã hóa bằng khóa đó.
- Ai có khả năng truy cập key material.
- Secret nào cần thay mới ở hệ thống đích.
- Các Config Server replica và client nào đã sử dụng khóa.
- Có bản backup hoặc artifact nào chứa key material không.

### 13.2. Thay secret đích, không chỉ thay encryption key

Nếu mật khẩu database đã bị giải mã bởi người không được phép, chỉ mã hóa lại cùng mật khẩu bằng K2 không thu hồi quyền truy cập của kẻ đã biết plaintext.

Cần cân nhắc:

1. Tạo credential mới ở database hoặc hệ thống đích.
2. Cập nhật ciphertext bằng K2.
3. Triển khai keyring mới tới Config Server.
4. Cập nhật cấu hình và refresh/restart client.
5. Thu hồi credential cũ.
6. Xác minh mọi client dùng credential mới.
7. Xử lý bản backup, log hoặc repository có thể đã chứa ciphertext và key cũ.

Rotation của encryption key không thay thế credential rotation ở database, broker hoặc API provider.

### 13.3. Thu hồi key bị xâm phạm

Nếu key bị lộ nghiêm trọng, không nên giữ key đó hoạt động lâu chỉ để thuận tiện rollback. Tạo ciphertext mới, chuyển client và thu hồi key bị xâm phạm theo quy trình incident response. Bản cấu hình rollback cần được mã hóa lại bằng khóa an toàn trước khi sử dụng.

Không khôi phục private key bị xâm phạm vào keystore production chỉ để làm một revision cũ chạy lại.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Cấu hình cũ không giải mã sau rotation | K1 đã bị gỡ trước khi ciphertext K1 được chuyển | Khôi phục khả năng giải mã an toàn hoặc re-encrypt dữ liệu |
| Một số Config Server giải mã được, số khác không | Keystore giữa các replica không đồng nhất | Đồng bộ alias/keyring và kiểm tra từng node |
| Ciphertext mới không giải mã | Sai alias, alias chưa có hoặc key pair không khớp | Kiểm tra tiền tố key và keystore |
| Config Server trả property invalid | Decryption thất bại | Kiểm tra key alias, key password, ciphertext và revision |
| Client dùng password mặc định | Property encrypted bị invalid và nguồn thấp hơn cung cấp fallback | Validate secret bắt buộc, kiểm tra property source |
| Client nhận ciphertext thay vì plaintext | Server-side decryption bị tắt hoặc decrypt thất bại | Kiểm tra encrypt.enabled và client-side decryption |
| /decrypt trả 401/403 | Security policy không cho phép caller | Kiểm tra quyền operator; không mở endpoint công khai |
| Plaintext xuất hiện trong log | Debug request/response hoặc shell command không an toàn | Xóa log theo chính sách, hạn chế log và audit |
| Rollback thất bại | Alias cũ đã bị xóa hoặc revision cũ không được re-encrypt | Duy trì rollback window và kiểm thử revision cũ |
| Rotation xong vẫn phải đổi secret đích | Encryption key đổi nhưng credential cũ đã bị lộ | Thay credential ở hệ thống đích và thu hồi credential cũ |
| Một application dùng nhầm key | Default locator dùng chung key hoặc custom locator định tuyến sai | Kiểm tra TextEncryptorLocator và application/profile |
| Keystore không mở được sau deploy | Sai password, path, quyền file hoặc type | Kiểm tra secret injection và mount trong từng replica |

## 15. Checklist trước khi kết thúc rotation

### Key material

- [ ] Khóa mới đã được tạo và lưu ở nơi được bảo vệ.
- [ ] Alias mới đã có trong keystore của mọi Config Server replica.
- [ ] Alias cũ vẫn còn trong giai đoạn chuyển tiếp.
- [ ] Mật khẩu keystore được inject runtime, không commit vào Git.
- [ ] Quyền đọc keystore và backup đã được giới hạn.

### Ciphertext và repository

- [ ] Inventory ciphertext theo application/profile/label đã hoàn tất.
- [ ] Ciphertext mới dùng đúng alias.
- [ ] File YAML dùng quoting phù hợp cho giá trị có dấu ngoặc nhọn.
- [ ] File Properties không bọc giá trị cipher trong dấu nháy.
- [ ] Không còn revision đang triển khai tham chiếu alias đã bị gỡ.

### Config Server và client

- [ ] Mọi Config Server replica giải mã được ciphertext cũ và mới trong giai đoạn chuyển tiếp.
- [ ] Client nhận giá trị plaintext đúng theo mô hình server-side decryption.
- [ ] Không có property invalid.
- [ ] Bean cấu hình và dependency hoạt động với secret mới.
- [ ] Log không chứa plaintext hoặc key material.

### Rollback và thu hồi

- [ ] Revision cũ đã được kiểm thử trong cửa sổ rollback.
- [ ] Có kế hoạch re-encrypt bản backup cần phục hồi.
- [ ] Alias cũ chỉ được gỡ khi không còn nhu cầu đọc ciphertext cũ.
- [ ] Nếu khóa bị lộ, credential đích cũng được thay và thu hồi.
- [ ] Có audit và người chịu trách nhiệm phê duyệt việc kết thúc rotation.

## 16. Bài tập vận dụng

**Bài tập 1 — Server-side encryption.** Cấu hình Config Server với khóa đối xứng lấy từ biến môi trường. Dùng /encrypt để mã hóa một giá trị test, lưu ciphertext với tiền tố {cipher} trong repository và xác nhận client nhận giá trị đã giải mã.

**Bài tập 2 — Keystore alias.** Tạo keystore có hai alias test-key-old và test-key-new. Tạo hai ciphertext dùng hai alias và xác nhận Config Server giải mã được cả hai khi keyring có đủ key entry.

**Bài tập 3 — Dual-key migration.** Triển khai keyring có K1 và K2 tới hai Config Server instance. Cập nhật repository từ ciphertext K1 sang K2, sau đó gọi lần lượt từng instance để xác minh khả năng đọc.

**Bài tập 4 — Rollback.** Khôi phục revision cũ chứa ciphertext K1 trong khi keyring vẫn có K1 và K2. Sau đó thử lại khi chỉ còn K2 và phân tích vì sao rollback không còn tương thích.

**Bài tập 5 — Decryption failure.** Cố ý dùng alias không tồn tại. Quan sát property invalid trong response và kiểm tra client có vô tình dùng giá trị fallback từ property source khác hay không.

**Bài tập 6 — Client-side decryption.** Tắt server-side decryption theo hướng dẫn phiên bản đang dùng. Kiểm tra client nhận ciphertext và thiết kế cách phân phối private key an toàn cho workload.

**Bài tập 7 — Incident response.** Giả định K1 bị lộ và credential database đã bị đọc. Lập quy trình tạo credential mới, mã hóa bằng K2, triển khai keyring, cập nhật client, thu hồi credential cũ và xác minh.

**Bài tập 8 — Security review.** Đánh giá quyền gọi /encrypt và /decrypt, TLS, per-application authorization, log và quyền truy cập keystore. Chứng minh một Config Client không thể đọc secret của service khác.

## 17. Ghi nhớ và nguồn tra cứu

- Config Server nhận diện ciphertext qua tiền tố {cipher}; ở chế độ mặc định, server giải mã trước khi gửi cấu hình cho client.
- Khóa đối xứng dùng cùng secret để mã hóa và giải mã; khóa bất đối xứng dùng public key để mã hóa và private key để giải mã.
- Keystore có thể chứa nhiều alias; tiền tố {key:alias} cho phép chọn key tương ứng khi giải mã.
- Khi xoay vòng, triển khai keyring chứa cả alias cũ và mới lên mọi Config Server trước khi đổi ciphertext.
- Giữ alias cũ trong cửa sổ rollback; chỉ gỡ khi mọi cấu hình cần hỗ trợ đã được chuyển đổi.
- Default TextEncryptorLocator không tự tách key theo application/profile; cần locator tùy chỉnh nếu muốn chính sách riêng.
- Khi giải mã thất bại, Config Server mặc định loại property và thêm tên property có tiền tố invalid.
- Server-side decryption tập trung key management; client-side decryption mở rộng phạm vi phân phối private key.
- Mã hóa at-rest không thay thế TLS, authorization, secret manager hoặc bảo vệ plaintext trong runtime.
- Nếu key bị lộ, phải thay cả credential ở hệ thống đích; re-encrypt cùng credential cũ không thu hồi quyền truy cập đã bị lộ.

Nguồn chính thức để đối chiếu theo phiên bản Spring Cloud Config/Spring Boot của dự án:

1. [Spring Cloud Config – Using Multiple Keys and Key Rotation](https://docs.spring.io/spring-cloud-config/reference/server/using-multiple-keys-and-key-rotation.html)
2. [Spring Cloud Config – Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html)
3. [Spring Cloud Config – Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html)
4. [Spring Cloud Config – Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html)
5. [Spring Cloud Config – Security](https://docs.spring.io/spring-cloud-config/reference/server/security.html)
6. [Spring Cloud Config – Client Side Usage](https://docs.spring.io/spring-cloud-config/reference/client.html)
7. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)

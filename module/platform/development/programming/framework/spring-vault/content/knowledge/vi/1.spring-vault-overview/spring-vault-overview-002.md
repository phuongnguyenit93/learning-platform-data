# Thông tin xác thực, khóa mã hóa và cấu hình nhạy cảm

> **Chương:** Bản đồ Spring Vault  
> **Bối cảnh:** Trong ứng dụng Java dùng Spring Vault, điều cần quyết định trước khi gọi `VaultTemplate` là **đang bảo vệ loại dữ liệu nào**, ai được phép sử dụng, dữ liệu tồn tại bao lâu và sẽ được thay thế hoặc thu hồi ra sao.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **thông tin xác thực (credentials)**, **khóa mã hóa/ký số (cryptographic keys)** và **cấu hình nhạy cảm (sensitive configuration)**; hiểu trường hợp các nhóm này giao nhau.
2. Giải thích vì sao một bí mật vẫn có thể bị lộ khi đã chuyển ra khỏi Git, và nhận diện đường đi của bí mật trong suốt vòng đời ứng dụng.
3. Chọn đúng vai trò của KV, Database, Transit và PKI trong HashiCorp Vault.
4. Thiết kế quyền truy cập theo **danh tính workload**, API path và hành động cần làm; phân biệt quyền đọc secret với quyền yêu cầu Vault thực hiện thao tác mã hóa.
5. Áp dụng `VaultOperations`/`VaultTemplate` để đọc một secret KV v2 và gọi Transit trong Java.
6. Lập kế hoạch rotation, TTL, thu hồi, xử lý lỗi, giám sát và kiểm thử tích hợp cho từng loại bí mật.

## 1. Vì sao cần phân loại secret trước khi cất vào Vault?

Xét dịch vụ `orders-service` nhận đơn hàng, gọi đối tác thanh toán và lưu thông tin khách hàng. Service có thể cần:

- Mật khẩu tài khoản PostgreSQL, hoặc một tài khoản database được cấp động.
- API key của cổng thanh toán và OAuth client secret.
- Bearer token để gọi dịch vụ khác.
- Khóa mã hóa để bảo vệ trường dữ liệu trong database, hoặc khả năng **yêu cầu Vault mã hóa** mà không lấy khóa về.
- Khóa riêng và chứng chỉ X.509 cho mTLS.
- Chuỗi kết nối chứa username/password, mật khẩu mở keystore hoặc cấu hình xác thực client.

Chúng đều liên quan bảo mật nhưng **không có cách lưu và vòng đời giống nhau**. Nếu lưu tất cả như chuỗi tĩnh trong một KV path, ứng dụng có thể hoạt động ban đầu nhưng dễ bỏ lỡ credential động, quyền thao tác mật mã được tách riêng và quá trình cấp chứng chỉ ngắn hạn.

### 1.1. Ba nhóm chính

| Nhóm | Ví dụ | Nếu bị lộ, kẻ khác có thể làm gì? | Cơ chế Vault thường phù hợp |
|---|---|---|---|
| **Thông tin xác thực** | DB password, API key, OAuth client secret, access token | Mạo danh ứng dụng/người dùng, gọi API hoặc truy cập tài nguyên | KV cho giá trị tĩnh; Database cho tài khoản động; auth method cho Vault token |
| **Khóa mã hóa/ký số** | AES key, HMAC key, private signing key, khóa bao bọc dữ liệu | Giải mã, giả mạo dữ liệu/chữ ký hoặc phá ranh giới bảo mật tùy loại khóa | Transit để dùng khóa qua API; PKI cho vòng đời chứng chỉ và khóa liên quan |
| **Cấu hình nhạy cảm** | Database URL có mật khẩu, chuỗi kết nối, keystore password, cấu hình client certificate + private key | Tiết lộ credential hoặc đường dẫn/hạ tầng nội bộ, làm tăng khả năng bị tấn công | KV v2 hoặc nguồn cấu hình tích hợp Vault; tách field theo nhu cầu truy cập |

Các nhóm **có thể giao nhau**. Một private key dùng trong mTLS vừa là khóa mật mã vừa chứng minh danh tính client; một JDBC URL có username/password vừa là cấu hình vừa chứa credential. Hãy phân loại theo **cách sử dụng và tác động khi lộ**, không chỉ theo tên biến.

### 1.2. Cái gì không nhất thiết là secret?

Tên database, timeout, cổng TCP, tên Kafka topic và feature flag thông thường không mặc nhiên là bí mật. Public key, certificate công khai và CA certificate thường không cần giữ bí mật; **tính toàn vẹn và nguồn tin cậy** của chúng vẫn rất quan trọng. Dữ liệu cá nhân nhạy cảm không phải lúc nào cũng là “credential”; nó có thể cần mã hóa, kiểm soát truy cập và thời hạn lưu trữ nhưng không nên tự động đem toàn bộ hồ sơ khách hàng vào Vault KV.

Một quy tắc ban đầu:

> Nếu biết giá trị này đủ để **mạo danh**, **giải mã/ký thay**, hoặc **vượt qua cơ chế bảo vệ**, hãy quản lý nó như secret. Nếu nó chỉ mô tả hệ thống, đánh giá riêng yêu cầu **bí mật, toàn vẹn và sẵn sàng**.

Để tránh nhầm lẫn, nhớ ba câu hỏi:

1. **Authentication:** Chủ thể đang chứng minh mình là ai? Ví dụ `orders-service` đăng nhập Vault nhờ Kubernetes ServiceAccount JWT.
2. **Authorization:** Chủ thể đó được làm gì? Ví dụ policy cho đọc một KV key và gọi `transit/encrypt`, nhưng không cho `transit/decrypt`.
3. **Secret:** Dữ liệu/quyền năng nào cần bảo vệ? Ví dụ API key của đối tác, hoặc khóa mã hóa mà Transit giữ phía Vault.

## 2. Vòng đời và các vị trí secret có thể bị lộ

Mối đe dọa không kết thúc ở thao tác “lưu trong kho an toàn”. Secret đi qua nhiều nơi trước, trong và sau khi ứng dụng sử dụng:

~~~mermaid
flowchart LR
    I["Nguồn phát hành<br/>secret / credential"] --> V["Vault<br/>lưu hoặc cấp phát"]
    W["Danh tính<br/>workload"] --> A["Vault auth<br/>role + policy"]
    A --> T["Vault token<br/>giới hạn TTL"]
    T --> C["Spring Vault<br/>client"]
    V --> C
    C --> M["Bộ nhớ ứng dụng<br/>hoặc TLS context"]
    M --> S["Database / API / dịch vụ đích"]
    R["Rotation / revoke<br/>kết thúc vòng đời"] -.-> V
    R -.-> M
~~~

| Giai đoạn | Lỗ hổng thường gặp | Cách giảm rủi ro |
|---|---|---|
| Tạo hoặc nhập secret | Tạo khóa yếu, gửi trong chat/ticket, import qua máy cá nhân | Tạo bằng cơ chế an toàn, dùng kênh cấp phát có kiểm soát và giới hạn người biết |
| Lưu trữ | Commit vào Git, lưu plaintext trong backup, chia sẻ secret giữa môi trường | Sử dụng Vault phù hợp, phân tách dev/test/prod, kiểm soát backup và quyền quản trị |
| Bootstrap ứng dụng | Hard-code Vault root token, copy cùng token cho nhiều pod | Dùng danh tính workload và auth method thích hợp |
| Truyền tải | HTTP không mã hóa, bỏ kiểm tra chứng chỉ TLS | Kết nối HTTPS với CA trust/hostname verification đúng |
| Sử dụng trong runtime | Log payload, dump biến môi trường, giữ secret trong cache quá lâu | Giảm nơi sao chép, redact log, giới hạn thời gian giữ trong bộ nhớ |
| Thay thế/thu hồi | Khóa cũ còn trong version KV, credential cũ vẫn hợp lệ | Rotation phối hợp với hệ thống phát hành; revoke/disable giá trị cũ |
| Audit và sự cố | Không biết workload nào đã truy cập, log vô tình chứa secret | Bật audit devices phù hợp, kiểm soát log, theo dõi lỗi theo metadata |

**Di chuyển secret từ `application.yml` sang biến môi trường không tự giải quyết toàn bộ vòng đời.** Biến môi trường có thể xuất hiện trong cấu hình container, môi trường của process con, dump chẩn đoán hoặc giao diện vận hành tùy quyền. Kubernetes Secret cũng cần RBAC, mã hóa lưu trữ, giới hạn quyền với node/pod và chính sách rotation. Vault có thể phối hợp với các cơ chế đó; không thay thế việc bảo vệ ở mọi lớp.

Hai ranh giới tin cậy cần vẽ rõ:

- **Trước khi nhận secret:** Vault xác thực workload, áp policy, kiểm tra API path. Quyền đọc/ký/giải mã phụ thuộc token, role và engine.
- **Sau khi nhận secret hoặc plaintext:** chính ứng dụng chịu trách nhiệm với dữ liệu trong heap, log, HTTP request, trace, cache và các hệ thống downstream. Vault không thể ngăn ứng dụng đã được cấp quyền tự ghi plaintext ra log.

## 3. Thông tin xác thực: ai đang đăng nhập vào đâu?

### 3.1. Không nhầm Vault token với credential của hệ thống đích

Một ứng dụng có thể dùng **hai lớp thông tin xác thực**:

1. **Để gọi Vault:** workload đưa ra bằng chứng danh tính qua auth method (Kubernetes, AppRole, JWT/OIDC, cloud IAM tùy môi trường). Vault cấp token gắn với policy và TTL.
2. **Để gọi hệ thống đích:** ứng dụng đọc API key từ KV, hoặc nhận username/password tạm thời từ Database secrets engine; ứng dụng dùng credential đó để kết nối cổng thanh toán hay database.

Vault token không tự trở thành mật khẩu PostgreSQL, và gia hạn Vault token không mặc nhiên gia hạn lease của credential Database.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as orders-service
    participant Vault as Vault
    participant DB as PostgreSQL
    App->>Vault: Auth bằng danh tính workload
    Vault-->>App: Vault token + policies + TTL
    App->>Vault: GET database/creds/orders-readwrite
    Vault-->>App: username/password động + lease ID/TTL
    App->>DB: Kết nối bằng credential vừa cấp
    Note over App,Vault: Theo dõi lease; làm mới / gia hạn khi được phép
    Note over App,DB: Pool kết nối cần xử lý credential hết hạn
~~~

### 3.2. Credential tĩnh: thường quản lý trong KV

Một API key được bên thứ ba phát hành thường có vòng đời do **bên thứ ba** quyết định. Vault KV có thể cất và cung cấp giá trị này cho đúng workload, nhưng không tự gọi bên thứ ba để tạo key mới hay thu hồi key cũ.

Ví dụ cấu trúc logic của **KV v2**:

~~~text
Mount: secret/                    # cấu hình engine KV v2
  prod/orders/payment             # key logic chứa api-key
  prod/orders/partner-oauth       # key logic chứa client-id, client-secret
  prod/inventory/supplier         # key khác, policy khác
  test/orders/payment             # môi trường test, credential riêng
~~~

Tốt hơn việc nhét nhiều ứng dụng chung một key `secret/data/shared/all`: nếu một service được phép đọc key ấy, service có thể nhận mọi field bên trong response. Quyền policy của Vault áp ở cấp **path/capability**, không tự lọc từng field JSON theo role trong một key KV.

KV v2 có version/metadata, nhưng **version mới không có nghĩa credential cũ đã bị vô hiệu hóa**. Các version cũ có thể còn tồn tại theo retention và quyền truy cập; cần kiểm soát lịch sử và chủ động thu hồi tại hệ thống phát hành.

### 3.3. Credential động: Database secrets engine

Với Database secrets engine, Vault được cấu hình để phát hành credential database theo role, thời hạn và quyền SQL cụ thể. Ứng dụng đọc tại API path như `database/creds/orders-readwrite`, nhận username/password cùng dữ liệu lease.

Đây là **credential có thể được cấp và thu hồi theo lease**, khác hẳn một mật khẩu dài hạn trong KV. Khi lease hết hạn hoặc bị revoke:

- Credential có thể không còn được chấp nhận cho kết nối mới.
- Connection pool có thể đang giữ kết nối cũ; tác động chính xác phụ thuộc database, plugin và cách pool quản lý connection.
- Ứng dụng phải có cách nhận credential mới, tạo kết nối mới và phối hợp quá trình chuyển đổi.

Trong Spring Vault, API `VaultOperations` cho phép đọc những path động này; quản lý lease là một phần vòng đời tách biệt với session dùng để lấy Vault token. Không giả định mọi credential trả về đều tự gia hạn vô hạn.

### 3.4. Token và OAuth client secret cũng là secret

Một **bearer token** thường cho phép người giữ token thực hiện hành động trong phạm vi quyền của nó, nên phải bảo vệ như mật khẩu cho đến khi hết hạn/thu hồi. OAuth `client_id` có thể là định danh không bí mật tùy kiểu client; `client_secret` là credential cần bảo vệ. Access token, refresh token và client secret có mục đích, TTL và cơ chế thu hồi khác nhau; không lưu chúng vào một trường chung tên `token` rồi dùng chung chiến lược rotation.

Đối với Vault, nên ưu tiên **short-lived, least-privilege login token** do auth method phát hành cho workload. Không đưa root token, unseal/recovery key hoặc token operator vào ứng dụng nghiệp vụ.

## 4. Khóa mã hóa: bí mật nằm ở khóa hay ở khả năng sử dụng khóa?

Khóa mật mã không chỉ là chuỗi ngẫu nhiên cần cất giữ; việc **ai được phép dùng khóa để làm thao tác gì** quan trọng không kém việc biết khóa ở đâu.

### 4.1. Phân biệt các loại khóa

| Loại | Vai trò | Cần bảo vệ điều gì? |
|---|---|---|
| Khóa đối xứng, ví dụ AES | Cùng khóa dùng trong cơ chế mã hóa/giải mã tương ứng | **Bí mật khóa** và quyền dùng khóa |
| Khóa HMAC | Tạo/xác minh mã xác thực thông điệp | Khóa HMAC và quyền tạo MAC; phân định use case xác minh |
| Private key bất đối xứng | Ký số hoặc giải mã tùy thuật toán | **Private key**; quyền ký/giải mã |
| Public key / public certificate | Kiểm tra chữ ký hoặc mã hóa tới bên nhận | Chủ yếu tính xác thực/toàn vẹn và nguồn phân phối; không mặc nhiên cần giữ bí mật |
| Data Encryption Key (DEK) | Mã hóa dữ liệu nghiệp vụ | Plaintext DEK, thời gian tồn tại và cách bao bọc |
| Key Encryption Key (KEK) | Bao bọc/giải bọc DEK | Quyền unwrap; giới hạn sử dụng khóa gốc |

**Encoding không phải encryption.** Base64 chỉ biểu diễn bytes bằng ký tự, không làm plaintext trở thành bí mật. Hash password cũng là bài toán khác mã hóa có thể giải ngược: mật khẩu người dùng nên được xác minh bằng hàm băm mật khẩu thích hợp (ví dụ Argon2id hoặc bcrypt với tham số phù hợp), không cần lưu plaintext để “giải mã khi đăng nhập”.

### 4.2. Transit encryption: ứng dụng dùng khóa qua API

Với **Transit secrets engine**, Vault quản lý key material và nhận yêu cầu mã hóa, giải mã, ký hoặc xác minh theo khả năng thuật toán/key. Thay vì phát cho Java một AES key để giữ dài hạn trong bộ nhớ hoặc cấu hình, ứng dụng gửi dữ liệu cần mã hóa qua TLS và nhận ciphertext. Vault không phải nơi cất các bản ghi ciphertext nghiệp vụ; ứng dụng lưu ciphertext ở database/object store của mình.

~~~mermaid
flowchart LR
    A["Java orders-service<br/>plaintext cần bảo vệ"] -->|"Gửi plaintext<br/>đã base64 hóa qua TLS"| E["Vault Transit<br/>encrypt/orders-pii"]
    E -->|"Trả vault:vN:..."| A
    A -->|"Lưu ciphertext"| D[("Database ứng dụng")]
    D -->|"Lấy ciphertext"| B["Ứng dụng được quyền giải mã"]
    B -->|"Gọi decrypt qua TLS"| X["Vault Transit<br/>decrypt/orders-pii"]
    X -->|"Trả plaintext base64"| B
~~~

Trong Transit API, trường `plaintext` của request mã hóa thường là **chuỗi base64 của dữ liệu gốc**. Ciphertext trả về có định dạng của Vault, ví dụ tiền tố phiên bản `vault:v1:...`. Không tự cắt tiền tố hoặc tự diễn giải ciphertext như base64 của plaintext.

Một policy có thể cho một service **mã hóa** mà không cho **giải mã**. Đó là phân quyền theo năng lực; hữu ích khi service chỉ tiếp nhận dữ liệu. Khả năng triển khai phụ thuộc việc thiết kế endpoint và luồng nghiệp vụ chính xác.

### 4.3. Xoay vòng khóa và mã hóa dữ liệu đã lưu

Rotation khóa Transit tạo key version mới cho hoạt động phù hợp, nhưng **không tự viết lại toàn bộ ciphertext cũ trong database của ứng dụng**. Vault có thể giải mã dữ liệu cũ bằng key version còn được cho phép; để cập nhật ciphertext, cần quy trình `rewrap` hoặc mã hóa lại theo thiết kế và chính sách. Cấu hình giới hạn phiên bản được phép giải mã có thể khiến ciphertext quá cũ không còn giải được.

Không được dùng “đã mã hóa” như lời hứa tuyệt đối về an toàn: bảo vệ các request chứa plaintext, hạn chế ai được gọi decrypt, giới hạn log, timeout, khả năng phục hồi khóa và tính sẵn sàng của Vault. Nếu hệ thống cần mã hóa cục bộ khối dữ liệu lớn, hãy đánh giá mô hình **envelope encryption** với DEK tạm thời được bao bọc bằng KEK thích hợp, thay vì gửi toàn bộ lưu lượng dữ liệu qua Transit.

## 5. PKI: certificate, private key và danh tính mTLS

Với mTLS, một workload thường có:

- **Certificate X.509** gắn public key với danh tính và thời hạn hiệu lực.
- **Private key** tương ứng để chứng minh quyền sở hữu khóa.
- **Trust anchors/CA certificates** để xác minh certificate của bên kia.

Private key là bí mật; certificate công khai thường không phải secret nhưng phải được xác minh. **PKI secrets engine** của Vault có thể cấp và quản lý chứng chỉ theo role: tên miền, thời hạn, loại chứng chỉ và những giới hạn khác.

Hai cách triển khai có ranh giới khác nhau:

| Luồng PKI | Điều diễn ra | Điểm cần chú ý |
|---|---|---|
| Vault tạo key và cấp certificate qua `pki/issue/<role>` | Response có thể chứa certificate và private key tương ứng | Private key đi qua kênh API và vào bộ nhớ client; phải kiểm soát nơi lưu và log |
| Ứng dụng/hạ tầng tạo private key, gửi CSR qua `pki/sign/<role>` | Vault ký CSR và cấp certificate theo role | Private key có thể được giữ trong keystore/HSM hoặc môi trường tạo key, không cần gửi đến Vault |

Không có nghĩa CSR tự động an toàn trong mọi trường hợp: xác minh danh tính của requester và giới hạn trong PKI role vẫn là phần cốt lõi. Certificate ngắn hạn cần **cấp lại và nạp lại vào TLS context**; chỉ “đổi secret trong Vault” không bảo đảm socket hoặc connection pool hiện hữu dùng chứng chỉ mới.

## 6. Cấu hình nhạy cảm: ranh giới giữa cấu hình và credential

Một cấu hình Spring Boot có thể trộn dữ liệu công khai và bí mật:

~~~yaml
# Chỉ mô tả cấu trúc; không chứa secret thật
payment:
  endpoint: https://api.payment.example
  timeout: 3s
  api-key: "${PAYMENT_API_KEY}"  # placeholder, KHÔNG phải cơ chế quản lý vòng đời

spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    password: "${DB_PASSWORD}"
~~~

Thay vì coi cả file là secret, nên biết trường nào cần quản trị trong Vault. `endpoint` và `timeout` thường là cấu hình bình thường. `api-key` và `password` là credentials. `username` đôi khi có thể công khai theo thiết kế, đôi khi cần hạn chế; quan trọng là quyền ghép với password/role để kết nối. Một JDBC URL có password gắn trong query string phải được xử lý như secret và tránh ghi log nguyên vẹn.

### 6.1. Thiết kế đường dẫn để dễ cấp quyền

Giả sử Vault dùng KV v2 mount `secret/`:

~~~text
secret/                         # tên mount
  prod/orders/payment           # KV key logic
      api-key
  prod/orders/partner-oauth     # KV key logic
      client-id
      client-secret
  prod/notifications/smtp       # KV key logic của service khác
      username
      password
~~~

Với key logic `prod/orders/payment`, đường dẫn HTTP API của KV v2 để đọc dữ liệu là **`secret/data/prod/orders/payment`**. Trong khi đó, `VaultOperations.opsForKeyValue("secret", KV_2).get("prod/orders/payment")` nhận **key logic**, không thêm `data/` thủ công. Path dùng cho policy là path API thực tế.

Không có quyền đọc riêng từng field trong một document KV: nếu cùng key chứa `api-key` và `client-secret`, workload có quyền `read` key đó sẽ nhận cả hai. Hãy tách thành các KV key nếu hai nhóm người dùng/workload cần quyền khác nhau.

### 6.2. Spring Vault và Spring Cloud Vault

Hai cách dùng thường gặp:

- **Spring Vault (`VaultOperations`/`VaultTemplate`):** ứng dụng gọi Vault tại điểm nghiệp vụ cần credential, hoặc gọi Transit/PKI theo API; thuận tiện khi muốn tự điều khiển response, lỗi và thời điểm sử dụng.
- **Spring Cloud Vault:** tích hợp dữ liệu Vault vào **Spring Environment/configuration** tại điểm thích hợp trong quá trình khởi tạo ứng dụng. Cần kiểm tra phiên bản Spring Boot/Spring Cloud Vault và cách cấu hình, refresh hỗ trợ; không mặc định secret thay đổi trong Vault thì bean/JDBC pool tự nhận giá trị mới.

Cả hai cách đều cần **xác thực workload**, TLS, policies và thiết kế vòng đời. Việc secret xuất hiện trong `Environment` có thể thuận tiện cho cấu hình nhưng cũng mở rộng phạm vi code/framework có thể đọc được giá trị, nên cần bảo vệ các endpoint quản trị và hệ thống hiển thị config.

## 7. Ví dụ Java: đọc credential và gọi Transit bằng `VaultOperations`

Giả sử người quản trị đã cấu hình:

- Vault endpoint chạy HTTPS với certificate được client tin cậy.
- Workload `orders-service` đăng nhập qua auth method phù hợp; ứng dụng được inject một bean `VaultOperations` đã cấu hình.
- KV v2 mount `secret/`, có key logic `prod/orders/payment` với field `api-key`.
- Transit mount `transit/` có key `orders-pii`; policy cho phép mã hóa nhưng không nhất thiết giải mã.

Code dưới đây minh họa **hai mục đích có vòng đời khác nhau**: đọc một credential tĩnh và yêu cầu Vault mã hóa dữ liệu. Không nhúng Vault token hoặc khóa mã hóa vào source:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersSecretService {

    private final VaultOperations vault;
    private final VaultKeyValueOperations kv;

    public OrdersSecretService(VaultOperations vault) {
        this.vault = vault;
        this.kv = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
    }

    // Chỉ trả key cho thành phần cần dùng; không log/serialize ra response.
    public String paymentApiKey() {
        VaultResponse response = kv.get("prod/orders/payment");
        if (response == null) {
            throw new IllegalStateException("Required payment secret is absent");
        }

        Object value = response.getRequiredData().get("api-key");
        if (!(value instanceof String key) || key.isBlank()) {
            throw new IllegalStateException("Required payment field is absent");
        }
        return key;
    }

    // Transit nhận plaintext được base64 hóa, không phải plaintext trực tiếp.
    public String encryptCustomerReference(String plaintext) {
        String encoded = Base64.getEncoder().encodeToString(
            plaintext.getBytes(StandardCharsets.UTF_8));

        VaultResponse response = vault.write(
            "transit/encrypt/orders-pii",
            Map.of("plaintext", encoded));

        if (response == null) {
            throw new IllegalStateException("No Transit response");
        }
        Object value = response.getRequiredData().get("ciphertext");
        if (!(value instanceof String ciphertext) || ciphertext.isBlank()) {
            throw new IllegalStateException("No Transit ciphertext returned");
        }
        return ciphertext; // Lưu ciphertext trong database ứng dụng.
    }
}
~~~

**Điều kiện và giới hạn của ví dụ:**

1. `VaultOperations` được cấu hình bởi ứng dụng ở nơi khác; chỉ inject nó không tự thiết lập authentication hay tin cậy TLS.
2. `kv.get(...)` đọc dữ liệu theo **KV v2**; secret/mount sai hoặc policy thiếu sẽ không được Spring tự sửa.
3. `vault.write("transit/encrypt/orders-pii", ...)` gửi request đến Transit; policy cần capability phù hợp cho endpoint, thông thường `update`.
4. `encoded` chỉ là bản mã hóa biểu diễn (base64) của plaintext, **không được xem là ciphertext**; không ghi request hay input ra log.
5. `String` của Java có thể tồn tại trong heap cho đến khi được thu gom; ứng dụng phải hạn chế giữ/nhân bản secret. Ví dụ không giải quyết retry, cache, rotation hoặc việc tích hợp với cổng thanh toán.
6. Khi cần giải mã, gọi endpoint `transit/decrypt/orders-pii` với ciphertext và xử lý response plaintext base64; cấp riêng quyền `decrypt` cho đúng workload cần thiết.

Ví dụ chọn API thấp vừa đủ để thấy rõ mối quan hệ giữa path, payload và quyền. Với từng phiên bản Spring Vault, có thể dùng các abstraction riêng cho engine nếu phù hợp; luôn đối chiếu chữ ký API và hướng dẫn chính thức của phiên bản đang chạy.

## 8. Thiết kế policy theo loại bí mật và chức năng

Một policy cho `orders-service` **chỉ đọc API key và mã hóa dữ liệu** có thể như sau:

~~~hcl
# KV v2 mount secret/, key logic prod/orders/payment
path "secret/data/prod/orders/payment" {
  capabilities = ["read"]
}

# Chỉ cho mã hóa với Transit key orders-pii
path "transit/encrypt/orders-pii" {
  capabilities = ["update"]
}
~~~

Chính sách trên **không** cho đọc secret của service khác, liệt kê metadata KV hoặc gọi decrypt Transit. Nếu cần giải mã ở một service riêng, tạo role/policy đúng cho service đó:

~~~hcl
path "transit/decrypt/orders-pii" {
  capabilities = ["update"]
}
~~~

Nếu `orders-service` sử dụng Database dynamic secrets, role riêng có thể được cấp `read` cho `database/creds/orders-readwrite`. Nếu cần xin certificate qua PKI, role phù hợp có thể cần `update` cho `pki/issue/orders-client` hoặc `pki/sign/orders-client` tùy workflow. **Không gom các capability này cho tất cả service** chỉ để tiện triển khai.

Một bảng áp quyền theo thực tế:

| Nhu cầu | Path API tham khảo | Capability thường cần |
|---|---|---|
| Đọc KV v2 key | `secret/data/prod/orders/payment` | `read` |
| Liệt kê danh sách KV v2 keys | `secret/metadata/prod/orders` | `list` (chỉ khi thật sự cần) |
| Nhận credential Database động | `database/creds/orders-readwrite` | `read` |
| Transit encrypt | `transit/encrypt/orders-pii` | `update` |
| Transit decrypt | `transit/decrypt/orders-pii` | `update` |
| PKI issue/sign certificate | `pki/issue/orders-client` hoặc `pki/sign/orders-client` | `update` |

Mỗi cột path chỉ là **ví dụ theo mount/role đặt tên trong bài**. Tên mount thực tế có thể khác; policy và khả năng của engine phải kiểm tra ở Vault server. Role và policy nên ràng buộc với danh tính cụ thể của workload (Kubernetes ServiceAccount/namespace, identity cloud, AppRole...), tránh phát token dùng chung dài hạn.

## 9. Rotation, expiration và revocation khác nhau thế nào?

**Rotation** thay credential/khóa/chứng chỉ đang sử dụng bằng giá trị hoặc phiên bản mới. **Expiration** là trạng thái hết hiệu lực theo thời hạn. **Revocation** là hành động chủ động thu hồi quyền trước hoặc khi kết thúc vòng đời. Không phải mọi loại secret đều hỗ trợ ba hành vi theo cùng một cách.

| Loại | Ai có thể thay thế/thu hồi? | Điều ứng dụng cần làm |
|---|---|---|
| API key đối tác trong KV | Nhà cung cấp API tạo/revoke; quản trị viên cập nhật KV | Cập nhật cache/config, hỗ trợ giai đoạn chồng lấp key nếu nhà cung cấp cho phép; loại key cũ |
| Vault login token | Vault auth/token subsystem theo role, TTL, renewability | Gia hạn nếu hợp lệ hoặc login lại; phản ứng với token bị revoke |
| DB dynamic credential | Vault Database engine và DB plugin theo lease | Xin credential mới, quản lý connection pool và kết nối đang mở |
| Transit key | Vault/Transit quản lý key versions và chính sách dùng key | Quy hoạch rewrap/re-encrypt và giải mã ciphertext cũ theo phiên bản cho phép |
| PKI certificate | Vault PKI và cơ chế revocation/expiration liên quan | Cấp mới, thay keystore/TLS context, kiểm tra chain và thời hạn |
| Cấu hình nhạy cảm không có TTL | Chủ sở hữu cấu hình/hệ thống nguồn | Theo dõi thay đổi, phân phối phiên bản mới và rollback an toàn |

### 9.1. Ví dụ thay API key không gây ngắt quãng

Giả sử cổng thanh toán hỗ trợ đồng thời **hai key** trong một khoảng thời gian:

1. Phát hành key mới tại cổng thanh toán, giới hạn đúng scope.
2. Ghi phiên bản KV mới cho `prod/orders/payment`, để `orders-service` lấy key mới theo chiến lược refresh đã kiểm thử.
3. Kiểm tra các instance đang dùng key mới; quan sát lỗi xác thực từ đối tác.
4. Thu hồi key cũ ở cổng thanh toán khi mọi phiên bản ứng dụng đã chuyển xong.
5. Xác nhận không còn bản sao cũ trong cache, pipeline, image, backup có quyền truy cập rộng hoặc lịch sử KV không cần thiết.

Nếu đối tác **không** hỗ trợ hai key song song, cần kế hoạch chuyển đổi khác có tính đến gián đoạn có thể xảy ra. Ghi version KV mới không thu hồi tự động key cũ.

### 9.2. Token TTL khác với secret lease TTL

Vault token được client dùng để gọi API Vault. Database credential động có thể đi kèm **lease riêng**. Khi login token được renew, không có nghĩa database lease tự tăng TTL; khi lease hết hạn, việc token vẫn còn hợp lệ không giúp DB password cũ hoạt động. Với Spring Vault, quản lý session và lifecycle của secrets phải được thiết kế/kiểm tra riêng theo cách tích hợp cụ thể.

### 9.3. Xử lý tình huống Vault tạm thời không sẵn sàng

Không có chính sách cache/khôi phục dùng chung cho mọi secret:

- API key tĩnh đã được lấy trước có thể được giữ ngắn hạn nếu rủi ro rotation/revocation được chấp nhận và quy trình bảo vệ bộ nhớ rõ ràng.
- Token hoặc credential có TTL có thể hết hạn ngay khi hệ thống mất kết nối; giữ mãi một bản cũ sẽ không làm chúng hợp lệ trở lại.
- Transit encrypt/decrypt cần Vault sẵn sàng nếu ứng dụng chỉ sử dụng phép mật mã phía Vault. Thiết kế timeout, retry có giới hạn và cách phản hồi khi mất dịch vụ là một phần SLA.
- PKI cần cơ chế cấp mới trước khi certificate hết hạn; phải thử nghiệm thực tế việc thay chứng chỉ trong runtime.

Khi một secret bắt buộc không thể lấy hoặc không còn hợp lệ, ứng dụng nên có hành vi **fail closed** phù hợp để không vô tình chuyển sang mật khẩu mặc định hoặc bỏ qua mã hóa.

## 10. Quan sát, xử lý lỗi và kiểm thử tích hợp theo nhóm secret

### 10.1. Phân biệt lỗi để xử lý đúng

| Dấu hiệu | Khả năng cần kiểm tra | Điều không nên làm |
|---|---|---|
| HTTP 403 từ Vault | Token/policy sai, thiếu quyền trên `data/` hay Transit path | Không tự động đổi sang root token |
| HTTP 404 hoặc thiếu field | KV key/version không tồn tại, mount sai, role không có | Không mặc định trả chuỗi trống rồi tiếp tục |
| Token invalid/expired | TTL, revoked, auth method/session | Không retry mãi với cùng token đã chết |
| Lease DB hết hạn | Credential động/pool chưa thay đúng | Không giả định gia hạn Vault token khắc phục được |
| Transit trả lỗi | Sai key path, request base64 không hợp lệ, thiếu capability, loại key/operation không phù hợp | Không fallback sang plaintext lưu DB |
| TLS handshake thất bại | CA trust, certificate hoặc hostname | Không tắt kiểm tra TLS để “chạy được” |
| Timeout, Vault quá tải, lỗi 5xx | Kết nối mạng, Vault/engine bị gián đoạn | Không retry vô hạn hoặc log request chứa plaintext |

Trả lỗi ra ngoài theo mã nghiệp vụ/thông báo phù hợp, không đưa payload Vault, token, private key, plaintext hoặc ciphertext chứa metadata nhạy cảm vào exception trả cho người dùng. Log nội bộ cũng phải tuân theo chính sách bảo vệ dữ liệu.

### 10.2. Giám sát được hệ thống mà không lộ secret

Các chỉ số hữu ích: tỷ lệ login thành công/thất bại, số lỗi đọc KV theo loại, độ trễ gọi Vault, tần suất `403`, lỗi Transit/PKI, mức gần hết TTL của token/lease/certificate, thời gian hoàn tất rotation. Chỉ ghi nhãn ở mức **service, loại thao tác, status và môi trường** sau khi đánh giá độ nhạy cảm; không đặt token, plaintext hay đường dẫn chứa dữ liệu cá nhân vào metric label.

Vault có **audit devices** để hỗ trợ kiểm toán truy cập. Phải bật và vận hành đúng, bảo vệ điểm đích audit và quyền đọc log. Audit không thay thế metric sức khỏe ứng dụng hoặc việc kiểm soát secret trong log phía client.

### 10.3. Bài kiểm thử tích hợp nên thực hiện

Một môi trường test cô lập dùng Vault thật (ví dụ Vault dev server/container chỉ dành cho test) giúp kiểm tra policy và engine thực tế. Mock `VaultOperations` chỉ kiểm tra logic gọi hàm; không xác minh được auth method, path KV v2 hay quyền Transit:

1. Tạo workload identity/role thử nghiệm có quyền đúng `secret/data/prod/orders/payment`; xác nhận đọc được secret và service khác bị `403`.
2. Tạo KV v2 key với nhiều phiên bản; xác nhận ứng dụng dùng key logic đúng, xử lý key/field bị thiếu và không giả định version KV là TTL.
3. Gọi Transit encrypt bằng token chỉ có `update` trên encrypt; xác nhận **decrypt bị từ chối** với token đó; không ghi plaintext vào log test.
4. Nếu dùng Database engine, tạo credential động, kiểm tra lease/TTL và cách connection pool thay credential sau khi hết hạn.
5. Nếu dùng PKI, phát hành certificate thời hạn ngắn, xác minh chain, TTL và cơ chế reload của TLS context.
6. Thử token revoke, Vault timeout, lỗi TLS và thiếu policy; kiểm tra ứng dụng có hành vi fail closed, retry giới hạn và không lộ secret trong lỗi.

## 11. Bài tập thiết kế: chọn đúng chỗ lưu và cấp quyền

Một công ty có ba workload:

- `orders-api` nhận thông tin khách hàng và **chỉ cần mã hóa** dữ liệu trước khi lưu.
- `fraud-review` được phép **giải mã** một trường để điều tra gian lận.
- `billing-job` kết nối PostgreSQL để tổng hợp thanh toán; có chứng chỉ mTLS khi gọi dịch vụ nội bộ.

Hãy chọn cơ chế phù hợp:

| Nhu cầu | Hướng triển khai gợi ý | Ranh giới phân quyền |
|---|---|---|
| `orders-api` mã hóa trường khách hàng | Transit `encrypt/customer-data` | Chỉ `update` trên endpoint encrypt, không cấp decrypt |
| `fraud-review` giải mã có kiểm soát | Transit `decrypt/customer-data` | Role riêng, audit đầy đủ và quyền tối thiểu |
| `billing-job` lấy DB username/password | Database dynamic credentials | `read` trên role `database/creds/billing-report`; quản lý lease |
| `billing-job` cần certificate mTLS | PKI issue/sign theo role | Role PKI giới hạn danh tính, DNS/SAN và TTL; quản lý private key |
| Mỗi service gọi API đối tác bằng API key tĩnh | KV v2 theo service/môi trường | `read` đúng từng KV key; rotation ở đối tác |

Kiểm tra lại thiết kế với hai câu hỏi: “Nếu `orders-api` bị chiếm quyền, nó có thể đọc API key của `billing-job` hay giải mã dữ liệu không?” và “Khi credential của `billing-job` hết hạn, hệ thống có thể cấp lại và thay kết nối không?”. Nếu câu trả lời chưa rõ, sơ đồ quyền và vòng đời vẫn chưa hoàn chỉnh.

## 12. Ghi nhớ và tự kiểm tra

**Thông tin xác thực** giúp chứng minh danh tính hoặc truy cập hệ thống đích; **khóa mật mã** cho phép thực hiện phép mã hóa/ký/giải mã; **cấu hình nhạy cảm** chứa các giá trị hoặc ngữ cảnh phải hạn chế tiết lộ. Vault hỗ trợ kiểm soát ba nhóm qua nhiều engine và policy khác nhau, còn Spring Vault cung cấp API Java như `VaultTemplate`/`VaultOperations` để ứng dụng truy cập và sử dụng đúng theo quyền.

Điều cần nhớ không chỉ là “đặt secret ở Vault”: phải xác định **ai dùng**, **dùng vào thao tác gì**, **lấy từ đâu**, **tồn tại bao lâu** và **thu hồi bằng cách nào**.

Tự trả lời trước khi học phần tiếp:

1. Public certificate có phải secret không? Private key đi kèm khác ở điểm nào?
2. Tại sao `client_id`, `client_secret`, access token và refresh token không nên được coi là cùng một loại giá trị?
3. Một KV v2 key chứa ba field có thể cấp quyền đọc riêng từng field bằng Vault policy hay không?
4. Vì sao Base64 không bảo vệ được plaintext, và tại sao Transit ciphertext vẫn phải được quản lý phiên bản?
5. Khi một database credential động hết hạn, tại sao chỉ renew Vault login token là chưa đủ?
6. Với ứng dụng chỉ cần mã hóa, policy Transit nào là hợp lý hơn việc cấp cả encrypt và decrypt?
7. Nếu thay API key ở KV mà chưa revoke tại nhà cung cấp, rủi ro nào vẫn tồn tại?

## Tài liệu chính thức để đọc thêm

- [Spring Vault — Reference Documentation](https://docs.spring.io/spring-vault/reference/)
- [Spring Vault — VaultTemplate / VaultOperations](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — Authentication](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [HashiCorp Vault — KV Secrets Engine v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)
- [HashiCorp Vault — Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- [HashiCorp Vault — Transit Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
- [HashiCorp Vault — PKI Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/pki)
- [HashiCorp Vault — Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — Lease, Renew, and Revoke](https://developer.hashicorp.com/vault/docs/concepts/lease)

> **Lưu ý phiên bản:** Chi tiết API của Spring Vault, endpoint/role của từng secrets engine và hành vi gia hạn có thể khác theo phiên bản và cấu hình thực tế. Mã và path trong bài là ví dụ có mục đích minh họa; cần đối chiếu tài liệu của phiên bản đang vận hành trước khi áp dụng vào production.

# Vòng đời token, lease và thông tin xác thực động

Spring Cloud Vault giúp ứng dụng Spring Boot lấy thông tin xác thực từ HashiCorp Vault mà không phải lưu mật khẩu cố định trong file cấu hình. Nhưng lấy được credential mới chỉ là bước đầu. Ứng dụng còn phải quản lý thời hạn sử dụng, gia hạn, thay thế và thu hồi credential đúng lúc.

Trong Vault có hai vòng đời liên quan nhưng độc lập: **session token** dùng để ứng dụng xác thực với Vault, và **secret lease** gắn với một secret động như tài khoản database do Vault tạo. Session token hết hạn có thể khiến ứng dụng không gọi được Vault để gia hạn secret. Secret lease hết hạn có thể khiến username/password mà ứng dụng đang dùng bị thu hồi. Hai tình huống này cần được theo dõi riêng.

Bài học này trình bày cách Spring Cloud Vault quản lý hai vòng đời đó, cách đọc TTL và trạng thái renewable, cách xử lý thông tin xác thực database động, cùng giới hạn cần tính đến khi lease đạt **max_ttl**.

Sau bài học, bạn có thể:

- Phân biệt Vault session token với lease của một secret động.
- Giải thích các khái niệm TTL, max_ttl, renewable, lease ID và expiry.
- Phân biệt renew, rotate và revoke.
- Cấu hình Spring Cloud Vault quản lý vòng đời token và lease.
- Lấy thông tin xác thực database động từ Vault.
- Nhận biết giới hạn của tích hợp database khi lease đạt max_ttl.
- Thiết kế quy trình thay credential, tái tạo connection pool và xử lý shutdown.
- Theo dõi lỗi gia hạn, thu hồi và credential sắp hết hạn.

## 1. Hai vòng đời khác nhau trong một ứng dụng

Khi ứng dụng kết nối Vault, nó cần một danh tính để gọi API. Vault cấp một **session token** sau quá trình xác thực, ví dụ Kubernetes auth hoặc AppRole. Token này có TTL, policy và có thể có max TTL.

Khi ứng dụng đọc một secret động, chẳng hạn **database/creds/order-service**, Vault có thể tạo một tài khoản database riêng và trả về username/password cùng một **lease**. Lease mô tả thời gian credential có hiệu lực và liệu có thể gia hạn hay không.

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Boot khởi động"] --> B["Xác thực với Vault"]
    B --> C["Session token"]
    C --> D["Đọc secret động"]
    D --> E["Vault tạo credential"]
    E --> F["Lease ID + TTL + renewable"]
    F --> G["Ứng dụng dùng credential"]
    C --> H["Quản lý session token"]
    F --> I["Quản lý secret lease"]
    H --> J["Renew hoặc re-login"]
    I --> K["Renew, rotate hoặc revoke"]
~~~

Hai vòng đời này có quan hệ phụ thuộc nhưng không đồng nhất:

- Session token cho phép ứng dụng gọi Vault.
- Secret lease xác định thời gian một credential động có hiệu lực.
- Token còn hạn không bảo đảm database credential còn hạn.
- Database credential còn hạn cũng không giúp ích nếu session token đã hết hạn và ứng dụng không thể gọi Vault để gia hạn.
- Gia hạn session token không tự gia hạn tất cả secret lease.
- Gia hạn secret lease không tự cấp một session token mới.

Hãy theo dõi chúng bằng hai nhóm trạng thái và hai nhóm cảnh báo riêng.

## 2. Các khái niệm TTL, max_ttl và renewable

Mỗi dynamic secret có một lease. Vault trả metadata của lease cùng dữ liệu secret.

| Thuộc tính | Ý nghĩa |
|---|---|
| **TTL (Time To Live)** | Thời gian còn hiệu lực của token hoặc secret lease tại thời điểm được cấp/gia hạn |
| **max_ttl** | Giới hạn thời gian tối đa mà token hoặc lease có thể tồn tại theo cấu hình liên quan |
| **renewable** | Cho biết token/lease có được phép gia hạn hay không |
| **lease_id** | Định danh lease dùng để tra cứu, gia hạn hoặc thu hồi secret |
| **expiry** | Thời điểm lease hoặc token hết hạn nếu không được gia hạn |

Ví dụ một role database được cấu hình:

~~~text
default_ttl = 1h
max_ttl     = 24h
~~~

Vault có thể cấp credential với TTL ban đầu một giờ. Nếu lease renewable, ứng dụng có thể yêu cầu gia hạn trước khi hết hạn. Vault quyết định TTL mới dựa trên chính sách của backend và giới hạn role; yêu cầu gia hạn không bảo đảm Vault cấp đúng khoảng thời gian mà client đề nghị.

Khi tổng thời gian đã đạt giới hạn **max_ttl**, lease không thể tiếp tục gia hạn. Ứng dụng cần có phương án cấp credential mới và chuyển sang dùng credential đó trước khi credential cũ bị thu hồi.

**max_ttl** không phải một TTL khác được cộng thêm vào TTL hiện tại. Nó là giới hạn trên của vòng đời lease/token theo chính sách Vault. Một yêu cầu gia hạn có thể được cấp thời gian ngắn hơn yêu cầu hoặc bị từ chối.

## 3. Phân biệt renew, rotate và revoke

Ba thao tác thường bị nhầm lẫn:

| Thao tác | Điều xảy ra | Giá trị secret |
|---|---|---|
| **Renew** | Gia hạn thời gian sử dụng của lease nếu Vault cho phép | Thông thường giữ nguyên credential hiện tại |
| **Rotate** | Lấy hoặc tạo credential mới rồi chuyển ứng dụng sang dùng credential mới | Credential thay đổi |
| **Revoke** | Thu hồi lease và vô hiệu hóa secret liên quan | Credential cũ mất hiệu lực |

Gia hạn không phải là xoay vòng mật khẩu. Nếu Vault gia hạn lease của một tài khoản database, username/password thường vẫn giữ nguyên; chỉ thời gian sử dụng được kéo dài.

Khi revoke, Vault yêu cầu secrets engine thu hồi credential. Với database engine, plugin có thể chạy câu lệnh thu hồi để vô hiệu hóa hoặc xóa tài khoản được tạo. Sau khi lease bị thu hồi, không thể tiếp tục gia hạn lease đó.

Với dynamic secrets, Vault bắt buộc gắn lease để buộc consumer kiểm tra lại trạng thái định kỳ. Backend KV lưu giá trị tĩnh không cấp lease thực, dù một số response có thể chứa trường thời lượng. Không dùng TTL xuất hiện trong response KV như bằng chứng rằng secret KV sẽ tự động được rotate hoặc revoke.

## 4. Vòng đời session token

Spring Cloud Vault sử dụng **SessionManager** của Spring Vault để quản lý session token. Trong cấu hình mặc định, session lifecycle được bật. Token được lấy khi ứng dụng thực hiện thao tác đầu tiên cần session với Vault; sau đó Spring Cloud Vault quản lý token theo TTL và khả năng gia hạn của token/auth method.

Spring Cloud Vault lấy session token theo cơ chế lazy: lần sử dụng Vault đầu tiên mới kích hoạt login. Token được giữ đến khi hết hạn; khi một thao tác tiếp theo cần session token mới, Spring Cloud Vault có thể login lại theo auth method. Với token có thể renew, session manager quản lý thời điểm gia hạn trước expiry. Khi ứng dụng shutdown bình thường, Spring Cloud Vault cố gắng revoke token còn hoạt động để kết thúc session. Cơ chế cụ thể phụ thuộc auth method và phiên bản thư viện.

Ví dụ cấu hình session lifecycle:

~~~yaml
spring:
  cloud:
    vault:
      session:
        lifecycle:
          enabled: true
          refresh-before-expiry: 10s
          expiry-threshold: 20s
~~~

Ý nghĩa các thuộc tính:

- **enabled:** bật hoặc tắt quản lý vòng đời session token; mặc định được bật.
- **refresh-before-expiry:** thời điểm dự kiến làm mới token trước khi hết hạn. Tài liệu hiện hành nêu mặc định 5 giây.
- **expiry-threshold:** TTL tối thiểu để token còn được coi là hợp lệ. Token có TTL ngắn hơn ngưỡng này sẽ được coi như đã hết hạn; mặc định hiện hành là 7 giây.
- **expiry-threshold** nên lớn hơn **refresh-before-expiry** để tránh token hết hạn trước khi quá trình làm mới có thể hoàn tất.

Không tắt session lifecycle nếu ứng dụng dựa vào token do Spring Cloud Vault quản lý mà chưa có một cơ chế thay thế. Nếu token hết hạn, client có thể mất khả năng đọc secret mới hoặc gia hạn lease.

### Chọn phương thức xác thực phù hợp

Không nên đặt một Vault token tĩnh có quyền rộng trong application.yml. Hãy dùng danh tính workload phù hợp với nền tảng:

- **Kubernetes auth:** Vault xác minh ServiceAccount token của Pod và role được ràng buộc với service account/namespace.
- **AppRole:** phù hợp với workload cần cơ chế cấp RoleID/SecretID; SecretID phải được bảo vệ và có thể dùng response wrapping.
- **AWS IAM, Azure MSI hoặc GCP IAM:** tận dụng danh tính workload của cloud provider khi nền tảng hỗ trợ.
- **TLS certificate auth:** dùng client certificate đã được đăng ký với Vault.

Ví dụ Kubernetes auth:

~~~yaml
spring:
  config:
    import: vault://
  application:
    name: order-service
  cloud:
    vault:
      uri: https://vault.internal.example:8200
      authentication: KUBERNETES
      kubernetes:
        role: order-service
        service-account-token-file: /var/run/secrets/kubernetes.io/serviceaccount/token
      fail-fast: true
~~~

Role trong Vault cần được ràng buộc với ServiceAccount và namespace được phép. Policy cấp cho role chỉ nên đọc đúng các secret path mà ứng dụng cần. **fail-fast: true** khiến ứng dụng dừng khởi động nếu không thể lấy cấu hình từ Vault; đây là lựa chọn phù hợp khi ứng dụng không thể hoạt động an toàn nếu thiếu secret bắt buộc.

Với token auth tĩnh, **spring.cloud.vault.token** có thể nhận token từ biến môi trường hoặc secret mount. Tuy nhiên, token tĩnh không được Spring Cloud Vault lease lifecycle tự động renew/revoke như token do session login tạo ra. Không dùng root token cho ứng dụng.

## 5. Vòng đời secret lease trong Spring Cloud Vault

Spring Cloud Vault dùng **SecretLeaseContainer** của Spring Vault để theo dõi lease của các secret được quản lý. Lease renewable được lên lịch gia hạn trước khi hết hạn. Khi ứng dụng shutdown bình thường, các lease renewable đã lấy có thể được revoke.

Với lease không renewable, không thể kéo dài credential cũ bằng renew. Cơ chế quản lý secret có thể cần yêu cầu secret thay thế khi lease hết hạn; việc cập nhật ứng dụng phụ thuộc backend, loại property source và cách consumer tiếp nhận secret mới. Riêng database backend tích hợp tiêu chuẩn có giới hạn tại max_ttl được trình bày ở phần sau.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    vault:
      config:
        lifecycle:
          enabled: true
          min-renewal: 10s
          expiry-threshold: 1m
~~~

Các thuộc tính quan trọng:

| Thuộc tính | Vai trò |
|---|---|
| **spring.cloud.vault.config.lifecycle.enabled** | Bật/tắt quản lý lifecycle của lease; mặc định bật |
| **spring.cloud.vault.config.lifecycle.min-renewal** | Khoảng thời gian tối thiểu trước khi một lần gia hạn được thực hiện, tránh gọi renew quá dày |
| **spring.cloud.vault.config.lifecycle.expiry-threshold** | Khoảng thời gian trước expiry mà lease được lên lịch gia hạn |
| **spring.cloud.vault.config.lifecycle.lease-endpoints** | Chọn nhóm endpoint renew/revoke phù hợp với phiên bản Vault |
| **spring.cloud.vault.config.lifecycle.lease-strategy** | Quyết định giữ hoặc bỏ theo dõi lease sau lỗi gia hạn |

**lease-endpoints** có khác biệt giữa API cũ và mới. Tài liệu Spring Cloud Vault mô tả lựa chọn Legacy và SysLeases; hãy dùng cấu hình phù hợp với phiên bản Vault và Spring Cloud Vault của hệ thống thay vì sao chép giá trị từ một ví dụ cũ.

Một số phiên bản hỗ trợ các chiến lược lỗi:

- **DropOnError:** bỏ lease khỏi cơ chế theo dõi khi gặp lỗi.
- **RetainOnError:** giữ lease khi có lỗi.
- **RetainOnIoError:** giữ lease khi lỗi I/O.

Chiến lược giữ lease không làm credential tự hợp lệ trở lại. Nó chỉ quyết định cách container tiếp tục quản lý lease sau lỗi. Hãy thiết kế cảnh báo và quy trình phục hồi riêng.

Tắt **spring.cloud.vault.config.lifecycle.enabled** có thể khiến lease hết hạn mà ứng dụng không biết để xử lý; credential còn hiệu lực sau khi ứng dụng shutdown cũng có thể không được thu hồi ngay. Chỉ tắt khi đã có một cơ chế quản lý lifecycle khác và đã kiểm thử đầy đủ.

## 6. Lấy credential database động

Vault Database Secrets Engine có thể tạo username/password riêng theo role. Mỗi lần đọc endpoint **database/creds/<role>**, Vault tạo credential và lease riêng. Cách này giúp truy vết quyền truy cập đến từng workload hoặc instance, đồng thời giới hạn thời gian sử dụng credential.

Spring Cloud Vault cần dependency database backend:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-vault-config</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-vault-config-databases</artifactId>
</dependency>
~~~

Dùng Spring Cloud BOM phù hợp để quản lý phiên bản dependency, tránh tự chọn một version khác release train của ứng dụng.

Ví dụ cấu hình cho JDBC:

~~~yaml
spring:
  config:
    import: vault://
  application:
    name: order-service
  cloud:
    vault:
      uri: https://vault.internal.example:8200
      authentication: KUBERNETES
      kubernetes:
        role: order-service
      database:
        enabled: true
        role: order-readwrite
        backend: database
        username-property: spring.datasource.username
        password-property: spring.datasource.password
      config:
        lifecycle:
          enabled: true
          min-renewal: 10s
          expiry-threshold: 1m
~~~

Spring Cloud Vault đưa username/password nhận được vào các property tương ứng. Spring Boot có thể dùng chúng khi tạo **DataSource**.

Cần cấu hình Database Secrets Engine ở phía Vault trước:

~~~bash
vault secrets enable database
~~~

Vault operator cấu hình kết nối database, tài khoản quản trị riêng cho Vault và role tạo credential. Ví dụ role có TTL một giờ, max TTL một ngày:

~~~bash
vault write database/roles/order-readwrite \
  db_name=orders \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl=1h \
  max_ttl=24h
~~~

Đây là ví dụ minh họa cho PostgreSQL; câu lệnh tạo role và quyền phải điều chỉnh theo loại database, schema và yêu cầu nghiệp vụ. Tài khoản mà Vault dùng để tạo/xóa database user cần có quyền đúng mức, nhưng không nên là tài khoản ứng dụng thông thường.

Khi đọc:

~~~bash
vault read database/creds/order-readwrite
~~~

Vault trả về các trường như:

- **lease_id:** định danh lease.
- **lease_duration:** TTL hiện tại.
- **renewable:** có được gia hạn hay không.
- **username** và **password:** credential do Vault tạo.

Không ghi username/password vào log, terminal transcript chia sẻ hoặc ticket. Khi cần điều tra lease, chỉ lưu metadata cần thiết và che giá trị nhạy cảm.

## 7. Lease renewal không thay đổi database credential

Giả sử Vault cấp credential lúc 09:00 với TTL một giờ. Ứng dụng sử dụng credential đó để kết nối database. Trước khi TTL hết hạn, Spring Cloud Vault yêu cầu gia hạn lease.

Nếu Vault chấp nhận, TTL được kéo dài. Username/password thường vẫn là credential cũ. Đây là renewal, không phải rotation.

~~~mermaid
sequenceDiagram
    participant App as Spring Cloud Vault
    participant Vault as Vault
    participant DB as Database

    App->>Vault: Đọc database/creds/order-readwrite
    Vault->>DB: Tạo user động
    DB-->>Vault: User đã tạo
    Vault-->>App: Username + password + lease ID + TTL
    App->>DB: Kết nối bằng credential mới
    Note over App,DB: Ứng dụng sử dụng cùng credential
    App->>Vault: Renew lease trước expiry
    Vault-->>App: Lease được gia hạn, credential vẫn như cũ
    Note over App,DB: TTL mới được áp dụng
~~~

Nếu lease không renewable, Vault không cho phép renew. Ứng dụng cần có cơ chế lấy credential thay thế trước khi lease hết hạn, hoặc chấp nhận việc credential mất hiệu lực và workload phải được khởi động lại theo kế hoạch.

Nếu lease đã đạt **max_ttl**, Vault có thể từ chối renew. Không thể giả định việc gọi renew liên tục sẽ kéo dài credential vô hạn.

## 8. Giới hạn quan trọng khi database lease đạt max_ttl

Tài liệu Spring Cloud Vault nêu rõ tích hợp database backend tiêu chuẩn không hỗ trợ lấy credential mới và cấu hình lại **DataSource** khi thời gian lease tối đa đã đạt. Ví dụ, nếu **max_ttl** của role là 24 giờ, sau 24 giờ ứng dụng có thể không còn xác thực được với database bằng credential ban đầu.

Điều này đặc biệt quan trọng với ứng dụng chạy lâu dài:

- Lease có thể được gia hạn nhiều lần trước khi đạt **max_ttl**.
- Renewal kéo dài thời gian sử dụng cùng credential.
- Khi đạt giới hạn tối đa, renewal không thể tiếp tục.
- Database credential cũ có thể bị Vault thu hồi.
- **DataSource** và connection pool đã khởi tạo không tự động thay username/password chỉ vì một property source thay đổi.

Không coi **spring.cloud.vault.config.lifecycle.enabled=true** là bảo đảm rotation hoàn chỉnh cho database pool. Lifecycle quản lý lease; nó không tự giải quyết toàn bộ việc tạo credential mới, thay pool, chuyển request và đóng connection cũ ở thời điểm max TTL.

Có ba hướng vận hành thường được cân nhắc:

1. **Rolling restart trước max_ttl:** khởi động instance mới để lấy credential mới, kiểm tra readiness rồi chuyển traffic và dừng instance cũ trước khi credential cũ bị thu hồi.
2. **Tự xây dựng credential rotation:** dùng API lifecycle của Spring Vault như **SecretLeaseContainer** hoặc **ManagedSecret**, nhận secret mới rồi thay thế pool theo quy trình có kiểm soát.
3. **Điều chỉnh chính sách role:** chọn TTL/max_ttl phù hợp với vòng đời triển khai, cửa sổ bảo trì và khả năng phục hồi của ứng dụng.

Nếu tự xây dựng rotation cho **DataSource**, cần tạo pool mới bằng credential mới, kiểm tra kết nối, chuyển các request mới sang pool mới, drain các connection đang dùng từ pool cũ rồi đóng pool cũ. Chỉ gán lại hai biến username/password trong một object không chứng minh các connection đã mở được xác thực lại.

## 9. Dùng SecretLeaseContainer khi cần điều khiển rotation

Spring Vault cung cấp **SecretLeaseContainer** để quản lý lease và phát các sự kiện vòng đời. Các sự kiện có thể gồm:

- **SecretLeaseCreatedEvent:** secret và lease mới được tạo.
- **AfterSecretLeaseRenewedEvent:** lease được gia hạn thành công.
- **SecretLeaseRotatedEvent:** secret mới được cấp trong luồng rotation.
- **SecretLeaseExpiredEvent:** lease đã hết hạn.
- **SecretLeaseErrorEvent:** Vault trả lỗi hoặc có lỗi I/O.
- **BeforeSecretLeaseRevocationEvent** và **AfterSecretLeaseRevocationEvent:** trước/sau khi revoke.

Có thể đăng ký listener để phản ứng với những sự kiện đó. Listener cần được đăng ký trước khi container khởi động hoặc trước khi yêu cầu secret để không bỏ lỡ các event ban đầu.

Ở mức thiết kế, một quy trình rotation database có thể thực hiện:

1. Yêu cầu secret mới từ Vault.
2. Nhận username/password mới cùng lease mới.
3. Tạo một **DataSource** hoặc pool mới bằng credential mới.
4. Kiểm tra pool mới kết nối và thực hiện truy vấn kiểm tra.
5. Chuyển traffic hoặc bean routing sang pool mới.
6. Chờ các transaction/connection của pool cũ hoàn tất.
7. Đóng pool cũ và revoke lease cũ nếu không còn cần.
8. Ghi nhận revision/lease metadata mới mà không ghi secret.

Ví dụ dưới đây là pseudocode mô tả điểm tích hợp, không phải lớp có thể copy trực tiếp vào ứng dụng:

~~~java
void onCredentialRotated(DatabaseCredentials credentials) {
    DataSource replacement = poolFactory.create(credentials);

    healthCheck.verify(replacement);

    DataSource previous = dataSourceRouter.swap(replacement);

    previousPoolDrainer.drainAndClose(previous);
}
~~~

Điểm quan trọng là ứng dụng phải điều khiển vòng đời của pool và các request đang chạy. **SecretLeaseContainer** quản lý lease; nó không tự biết cách thay thế an toàn mọi resource bên ngoài.

Với Spring Vault phiên bản có **ManagedSecret**, API này cung cấp cách khai báo secret cần quản lý và callback khi secret được tạo/rotate. Hãy kiểm tra tài liệu Spring Vault tương ứng với version đang dùng và kiểm thử tương tác với **DataSource** thực tế.

## 10. Thu hồi lease và shutdown ứng dụng

Khi ứng dụng shutdown bình thường, Spring Cloud Vault có thể revoke session token còn hoạt động và các renewable lease đã lấy. Với database dynamic credentials, thao tác revoke thường khiến database user do Vault tạo bị xóa hoặc vô hiệu hóa theo câu lệnh revocation của role.

Các lệnh quản trị thường dùng:

~~~bash
vault lease lookup <LEASE_ID>
vault lease renew <LEASE_ID>
vault lease revoke <LEASE_ID>
~~~

Có thể thu hồi nhiều lease theo prefix nếu operator có quyền phù hợp:

~~~bash
vault lease revoke -prefix database/creds/order-readwrite
~~~

Hãy kiểm tra phạm vi prefix trước khi chạy. Revoke theo prefix có thể ảnh hưởng nhiều instance đang dùng credential từ cùng role.

Shutdown callback không chạy nếu process bị kill cưỡng bức, máy chủ mất điện hoặc container bị terminate trước khi có thời gian dọn dẹp. Khi đó Vault sẽ thu hồi lease khi hết hạn theo chính sách backend. Vì vậy TTL phải đủ ngắn để giới hạn thời gian credential tồn tại sau sự cố, nhưng đủ dài để ứng dụng có thời gian phục hồi khi Vault tạm thời không sẵn sàng.

Không revoke lease đang được instance khác sử dụng. Nếu nhiều instance cùng dùng chung một lease ID, một instance shutdown có thể ảnh hưởng các instance còn lại. Thiết kế nên cấp credential/lease riêng theo workload instance hoặc có owner quản lý rõ ràng.

## 11. Điều gì xảy ra khi gia hạn thất bại?

Gia hạn có thể thất bại vì nhiều nguyên nhân:

- Vault không truy cập được do network, DNS hoặc TLS.
- Session token đã hết hạn, bị revoke hoặc không còn quyền gọi endpoint renew.
- Policy thiếu quyền cần thiết.
- Lease đã đạt max_ttl hoặc không renewable.
- Secrets engine hoặc database plugin không thể thực hiện thao tác.
- Đồng hồ hệ thống lệch, scheduler chạy trễ hoặc ứng dụng quá tải.
- Lease đã bị operator thu hồi trong quá trình xử lý sự cố.

Không xử lý mọi lỗi theo cùng một cách. Cần phân biệt lỗi tạm thời và lỗi vĩnh viễn.

| Lỗi | Hướng xử lý |
|---|---|
| Vault timeout hoặc lỗi I/O ngắn hạn | Retry có backoff và jitter; cảnh báo nếu TTL còn lại giảm nhanh |
| Token hết hạn | Xác thực lại theo auth method; kiểm tra session lifecycle và policy |
| Permission denied | Kiểm tra policy path, capability và identity của workload |
| Lease không renewable | Lấy credential thay thế hoặc thực hiện rollout trước expiry |
| Đạt max_ttl | Chuyển sang quy trình cấp credential mới; renew thêm không giải quyết được |
| Lease bị revoke | Ngừng sử dụng credential cũ, lấy credential mới nếu được phép |
| Secret backend lỗi | Điều tra plugin/database; không đánh dấu rotation thành công khi credential chưa được xác minh |

Không tiếp tục sử dụng credential sau khi lease hết hạn chỉ vì connection pool vẫn còn connection đang mở. Hành vi của database khi credential bị thu hồi phụ thuộc engine và cơ chế revoke. Hãy kiểm tra khả năng xác thực cho connection mới và hành vi của connection hiện hữu.

## 12. Theo dõi vòng đời token và lease

Một hệ thống production cần quan sát cả Vault và ứng dụng. Các chỉ số nên có:

| Nhóm | Thông tin cần theo dõi |
|---|---|
| Session token | Auth method, thời điểm login, TTL còn lại, renew/re-login thành công hoặc thất bại |
| Secret lease | Lease path/role, TTL, renewable, thời điểm expiry, renew/revoke result |
| Database | Connection failures, pool active/idle, lỗi authentication, thời điểm pool thay thế |
| Vault | API latency, error rate, audit events, trạng thái secrets engine |
| Ứng dụng | Credential generation/version, readiness, rotation result và thời gian chuyển pool |

Không log token, password, private key hoặc toàn bộ response của Vault. Lease ID cũng là metadata nhạy cảm về vận hành; nếu cần đối chiếu, hãy giới hạn quyền truy cập log và cân nhắc lưu dạng rút gọn hoặc fingerprint.

Cảnh báo nên phát ra trước khi TTL còn quá ít để phục hồi. Ví dụ, nếu renewal thường mất vài giây nhưng cảnh báo chỉ được phát khi còn một giây, operator không có đủ thời gian xử lý lỗi Vault hoặc network.

Nên kiểm thử cả tình huống Vault tạm thời mất kết nối và tình huống lease bị revoke chủ động. Một ứng dụng có thể hoạt động bình thường trong nhiều giờ nhưng thất bại khi token hoặc lease lần đầu đến hạn.

## 13. Thiết kế TTL và max_ttl

TTL ngắn làm giảm thời gian credential bị lộ có thể bị lạm dụng, nhưng tăng số lần giao tiếp với Vault và yêu cầu hệ thống phục hồi nhanh. TTL dài giảm tần suất renew nhưng kéo dài thời gian tồn tại của credential sau sự cố.

Khi chọn TTL/max_ttl, cân nhắc:

- Thời gian trung bình và tối đa mà ứng dụng chạy liên tục.
- Thời gian cần để phát hiện lỗi Vault.
- Thời gian retry và phục hồi kết nối.
- Khả năng cấp credential mới và thay pool.
- Thời gian drain transaction/connection cũ.
- Chính sách thu hồi và audit.
- Khả năng triển khai rolling restart trước max_ttl.

Ví dụ role database có **default_ttl=1h**, **max_ttl=24h**. Ứng dụng có thể renew lease trong vòng 24 giờ nhưng cần có kế hoạch thay credential hoặc restart trước khi chạm giới hạn này. Nếu workload chạy lâu hơn 24 giờ mà không có rotation path, role đó không đáp ứng vòng đời của ứng dụng.

Không chọn max_ttl chỉ dựa trên thời gian trung bình. Hãy kiểm thử trong staging với đúng role, database plugin, connection pool và quy trình deploy.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng không đọc được secret sau một thời gian | Session token hết hạn hoặc không thể login lại | Kiểm tra session lifecycle, auth method và token policy |
| Database credential hết hạn dù ứng dụng vẫn chạy | Lease không được renew hoặc đã đạt max_ttl | Kiểm tra lease ID, TTL, renewable và role max_ttl |
| Thấy renew thành công nhưng password không đổi | Renew kéo dài lease của cùng credential | Phân biệt renewal với rotation |
| Shutdown xong database user vẫn còn | Process bị kill hoặc lease không được revoke | Kiểm tra TTL, revoke policy và shutdown lifecycle |
| Ứng dụng dùng credential mới trong Environment nhưng DB vẫn lỗi | DataSource/pool giữ cấu hình lúc khởi tạo | Thay pool an toàn hoặc rolling restart |
| Tắt lifecycle để tránh lỗi renew | Ứng dụng không còn quản lý expiry/revoke | Khôi phục lifecycle hoặc xây cơ chế thay thế đã kiểm thử |
| Nhiều instance mất kết nối database cùng lúc sau revoke | Các instance dùng chung lease bị thu hồi | Cấp lease riêng hoặc điều phối owner rõ ràng |
| Credential không được tạo lúc startup | Backend chưa bật, thiếu dependency hoặc role/policy sai | Kiểm tra secret engine, dependency, path và policy |
| Rotation event bị bỏ lỡ | Listener đăng ký sau khi container đã start/request secret | Đăng ký listener trước khi start container và kiểm thử lại |

## 15. Checklist production

- Dùng auth method theo danh tính workload; tránh root token hoặc token tĩnh có quyền rộng.
- Bật session lifecycle và secret lease lifecycle.
- Đặt min-renewal, expiry-threshold và refresh-before-expiry theo TTL thực tế.
- Kiểm tra renewable, TTL và max_ttl của từng secret engine/role.
- Tách session token lifecycle khỏi secret lease lifecycle trong metric và cảnh báo.
- Cấp policy chỉ cho phép đọc role/path cần thiết và renew/revoke đúng phạm vi.
- Dùng TLS và xác minh certificate khi kết nối Vault.
- Không log token, password hoặc secret response.
- Kiểm thử renewal thất bại, Vault unavailable, token hết hạn và lease bị revoke.
- Với database dynamic credentials, lập kế hoạch trước khi đạt max_ttl.
- Nếu cần rotation không gián đoạn, xây dựng quy trình thay pool, drain connection và đóng pool cũ.
- Revoke lease khi shutdown bình thường và có phương án TTL cho shutdown cưỡng bức.
- Không để một lease dùng chung bị một instance revoke khi các instance khác vẫn đang sử dụng.

## 16. Tự kiểm tra

1. Session token và secret lease khác nhau ở điểm nào?
2. TTL và max_ttl mô tả hai giới hạn nào?
3. Khi renew lease database, username/password có nhất thiết thay đổi không?
4. Điều gì xảy ra khi lease bị revoke?
5. Vì sao static token không được Spring Cloud Vault lease lifecycle tự động renew/revoke?
6. spring.cloud.vault.session.lifecycle và spring.cloud.vault.config.lifecycle quản lý hai vòng đời nào?
7. Vì sao credential database có thể hoạt động qua nhiều lần renew nhưng vẫn thất bại khi đạt max_ttl?
8. Tại sao việc thay giá trị trong Spring Environment không bảo đảm DataSource đang chạy sử dụng credential mới?
9. Cần làm gì để thay connection pool an toàn khi nhận credential mới?
10. Vì sao shutdown bình thường và shutdown cưỡng bức có kết quả revoke khác nhau?

Hãy dựng một ứng dụng Spring Boot kết nối Vault bằng Kubernetes auth hoặc AppRole. Bật database secrets engine và tạo role có TTL ngắn cùng max_ttl giới hạn. Cho ứng dụng đọc credential, ghi nhận lease metadata, quan sát một lần renew thành công rồi thử revoke trong môi trường test. Sau đó kiểm thử khi Vault tạm thời không truy cập được và khi session token hết hạn. Cuối cùng, mô phỏng max_ttl: xác minh ứng dụng không nhầm renew với rotation, thực hiện rolling restart hoặc thay pool theo quy trình đã thiết kế, rồi xác nhận credential cũ được thu hồi sau khi không còn được sử dụng.

## Tài liệu tham khảo

- [Spring Cloud Vault — Advanced Topics and Lease Lifecycle](https://docs.spring.io/spring-cloud-vault/reference/advanced-topics.html)
- [Spring Cloud Vault — Authentication](https://docs.spring.io/spring-cloud-vault/reference/authentication.html)
- [Spring Cloud Vault — Secret Backends and Database Credentials](https://docs.spring.io/spring-cloud-vault/reference/secret-backends.html)
- [Spring Vault — Credential Rotation and SecretLeaseContainer](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
- [HashiCorp Vault — Lease, Renew, and Revoke](https://developer.hashicorp.com/vault/docs/concepts/lease)
- [HashiCorp Vault — Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- [HashiCorp Vault — Token Renewal](https://developer.hashicorp.com/vault/docs/commands/token/renew)


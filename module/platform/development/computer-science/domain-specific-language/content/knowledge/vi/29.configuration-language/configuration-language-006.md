# Quản lý bí mật

## 1. Quản lý bí mật trong DSL cấu hình

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) dùng cho cấu hình thường mô tả dịch vụ, database, kết nối mạng, workflow, tài khoản kỹ thuật và các tham số triển khai. Một số giá trị cấu hình có thể công khai, nhưng một số khác cho phép truy cập vào hệ thống hoặc dữ liệu quan trọng, chẳng hạn mật khẩu database, API token, private key, signing key và credential của dịch vụ.

**Quản lý bí mật (secrets management)** là quá trình tạo, lưu trữ, phân phối, sử dụng, xoay vòng, thu hồi và kiểm toán các giá trị nhạy cảm đó trong suốt vòng đời của chúng. Mục tiêu là để thành phần được cấp quyền có thể sử dụng bí mật khi cần, trong khi hạn chế tối đa việc bí mật xuất hiện trong source code, repository, log, artifact, cache, giao diện hoặc bản sao không cần thiết.

Ví dụ một DSL cấu hình dịch vụ:

~~~text
service "billing" {
    database {
        host = "db.internal"
        username = "billing_app"
        password = secret_ref("prod/billing/database-password")
    }

    payment_api {
        endpoint = "https://payments.example"
        token = secret_ref("prod/billing/payment-token")
    }
}
~~~

Trong ví dụ, source chỉ chứa tham chiếu đến bí mật. Runtime dùng danh tính workload để lấy giá trị từ secret manager khi cần. Password và token không được ghi trực tiếp vào file DSL.

Quản lý bí mật cần được xem là một phần của ngữ nghĩa cấu hình và kiến trúc runtime, không chỉ là một tiện ích che dấu chuỗi. Một DSL an toàn cần xác định ai được phép tham chiếu bí mật nào, bí mật được phân giải ở thời điểm nào, có thể đi qua những thành phần nào và được bảo vệ ra sao khi lưu hoặc truyền.

## 2. Phân biệt dữ liệu cấu hình và bí mật

Không phải mọi giá trị cấu hình đều là secret. Phân loại đúng giúp áp dụng biện pháp bảo vệ tương xứng.

### 2.1. Cấu hình thông thường

Ví dụ:

- Tên dịch vụ.
- Port lắng nghe.
- Số worker.
- Tên môi trường.
- Địa chỉ endpoint công khai.
- Giới hạn timeout.
- Tên feature flag không nhạy cảm.

Những giá trị này thường có thể được lưu trong source control và hiển thị trong log, tùy chính sách của hệ thống.

### 2.2. Bí mật xác thực

Ví dụ:

- Password.
- API key.
- Access token.
- Refresh token.
- Database credential.
- Client secret.
- Service account credential.

Những giá trị này cho phép một chủ thể chứng minh danh tính hoặc được cấp quyền truy cập.

### 2.3. Khóa mật mã

Ví dụ:

- Private key dùng ký số.
- Khóa mã hóa dữ liệu.
- Khóa HMAC.
- Khóa giải mã backup.
- Certificate private key.

Khóa mật mã có vòng đời và yêu cầu bảo vệ riêng. Một số khóa nên được giữ trong HSM hoặc KMS và chỉ cho phép thao tác ký/mã hóa mà không xuất khóa thô.

### 2.4. Dữ liệu nhạy cảm khác

Một số cấu hình có thể không phải credential nhưng vẫn nhạy cảm: thông tin cá nhân, connection string chứa định danh, internal hostname, thông tin tenant hoặc dữ liệu vận hành. Chính sách bảo vệ cần dựa trên mức độ nhạy cảm, không chỉ tên trường.

### 2.5. Secret classification

Có thể phân loại theo mức độ:

| Nhóm | Ví dụ | Cách xử lý gợi ý |
|---|---|---|
| Public | Tên sản phẩm, endpoint công khai | Có thể lưu trong source |
| Internal | Hostname nội bộ, tên project | Giới hạn chia sẻ theo workspace |
| Confidential | Thông tin khách hàng, cấu hình vận hành nhạy cảm | Kiểm soát truy cập và logging |
| Secret | Password, token, private key | Secret manager, quyền tối thiểu, audit, rotation |

Tên phân loại là ví dụ. Tổ chức cần định nghĩa chính sách và cách xử lý cụ thể cho từng loại.

## 3. Vì sao không nên đặt secret trực tiếp trong DSL

Ví dụ không an toàn:

~~~text
database {
    username = "billing_app"
    password = "p@ssword-value"
}
~~~

Khi giá trị được ghi trực tiếp, nó có thể lan ra nhiều nơi:

- Git commit và lịch sử repository.
- Pull request, code review và bản sao local.
- Build log và diagnostic.
- Generated source hoặc bytecode.
- Container image và deployment bundle.
- Cache của compiler hoặc CI.
- Backup và snapshot.
- Screenshot, ticket và tài liệu hỗ trợ.
- Telemetry hoặc crash report.

Xóa dòng password khỏi phiên bản mới không loại bỏ bản sao đã tồn tại trong lịch sử hoặc artifact. Nếu secret đã bị lộ, cần xem xét thu hồi hoặc xoay vòng secret; chỉ sửa source là chưa đủ.

### 3.1. Placeholder không phải biện pháp bảo vệ

Thay password bằng chuỗi che như ******** trong giao diện không làm giá trị gốc an toàn nếu source, log hoặc API vẫn chứa secret thật.

### 3.2. Mã hóa source không giải quyết mọi vấn đề

Mã hóa toàn bộ file cấu hình có thể bảo vệ nội dung khi lưu, nhưng runtime vẫn phải giải mã. Nếu khóa giải mã nằm cạnh file hoặc trong cùng repository, attacker có thể lấy cả hai. Ngoài ra, việc giải mã có thể làm secret xuất hiện trong bộ nhớ, log hoặc process argument.

### 3.3. Tách cấu hình và giá trị bí mật

Source nên mô tả:

- Bí mật nào cần thiết.
- Secret identifier hoặc logical path.
- Provider hoặc namespace nếu cần.
- Phiên bản hoặc policy tham chiếu.
- Kiểu dữ liệu mong đợi.

Secret manager chịu trách nhiệm lưu giá trị thật và cấp quyền truy cập. Cách tách này giúp cùng một cấu hình có thể chạy ở nhiều môi trường mà không đưa credential vào source.

## 4. Secret reference trong DSL

Một DSL cấu hình có thể cung cấp cú pháp tham chiếu bí mật thay vì nhận giá trị thô.

### 4.1. Hàm tham chiếu

~~~text
password = secret_ref("prod/billing/db-password")
~~~

Hàm secret_ref tạo một giá trị tham chiếu có kiểu, không phải password đã được phân giải.

### 4.2. Cấu trúc tường minh

~~~text
password = secret {
    provider = "vault-prod"
    path = "billing/database"
    key = "password"
}
~~~

Cấu trúc tường minh phù hợp khi cần provider, namespace, key hoặc version. Tuy nhiên, DSL nên tránh cho phép người viết tự do truyền thông tin xác thực để truy cập provider.

### 4.3. Reference có version

~~~text
token = secret_ref(
    path = "prod/billing/payment-token",
    version = "7"
)
~~~

Pin version giúp build hoặc deployment tái lập. Reference theo alias như current hoặc active thuận tiện cho rotation tự động nhưng có thể khiến hai lần khởi chạy nhận giá trị khác nhau. Cần chọn theo yêu cầu reproducibility và chính sách cập nhật.

### 4.4. Reference có kiểu

Compiler có thể biểu diễn kiểu riêng:

~~~text
SecretRef<String>
SecretRef<PrivateKey>
SecretRef<DatabaseCredential>
~~~

Kiểu riêng giúp phân biệt secret reference với string bình thường. Semantic analyzer có thể kiểm tra trường password nhận loại credential phù hợp và ngăn việc nối chuỗi tùy tiện với một SecretRef.

### 4.5. Secret reference không phải secret value

Đây là khác biệt quan trọng:

| Thành phần | Nội dung | Có thể lưu trong source? |
|---|---|---|
| Secret reference | ID hoặc path để tìm secret | Thường có, nếu không tiết lộ thông tin nhạy cảm |
| Secret value | Password, token hoặc khóa thật | Không |
| Secret metadata | Version, expiry, owner, policy | Tùy mức nhạy cảm |
| Access credential | Danh tính dùng để gọi secret manager | Không nên nhúng trực tiếp |

Ngay cả path cũng có thể tiết lộ tên khách hàng, môi trường hoặc hệ thống nội bộ. Cần đánh giá metadata theo threat model.

## 5. Kiến trúc quản lý bí mật

Một kiến trúc điển hình tách DSL authoring, compiler, secret manager và runtime:

~~~text
DSL Source
   |
   | secret_ref("prod/billing/db-password")
   v
Parser / Semantic Analyzer
   |
   | giữ SecretRef, không lấy giá trị
   v
Configuration Artifact
   |
   v
Runtime Workload Identity
   |
   | authenticate
   v
Secret Manager / KMS
   |
   | authorize + resolve
   v
Secret Value
   |
   v
Protected Runtime Use
   |
   v
Database / API / Signing Operation
~~~

Các thành phần:

- **DSL source:** lưu cấu trúc cấu hình và secret reference.
- **Compiler:** parse, kiểm tra kiểu, kiểm tra policy và tạo artifact chứa reference.
- **Secret manager:** lưu và phân phối secret value.
- **Identity provider:** cấp danh tính cho workload hoặc user.
- **Policy engine:** quyết định danh tính nào được đọc secret nào.
- **Runtime resolver:** phân giải reference đúng thời điểm.
- **Audit system:** ghi nhận ai hoặc workload nào đã truy cập secret và khi nào.

### 5.1. Không đưa secret vào compiler nếu không cần

Compiler thường chỉ cần xác nhận reference có cấu trúc hợp lệ và loại secret phù hợp. Việc lấy secret thật nên diễn ra ở runtime hoặc một bước triển khai được kiểm soát riêng. Điều này giảm số hệ thống cần quyền đọc bí mật.

### 5.2. Phân tách trách nhiệm

Có thể tách:

- Developer được tạo reference.
- CI được kiểm tra artifact nhưng không cần đọc mọi production secret.
- Deployment controller được cấp quyền lấy secret cho workload cụ thể.
- Runtime chỉ nhận secret cần cho service của nó.
- Security administrator quản lý policy và key.

Không nên dùng một credential quản trị toàn quyền cho mọi giai đoạn.

## 6. Secret manager và secret store

Secret manager là dịch vụ hoặc thành phần chuyên quản lý giá trị bí mật, metadata, policy, version và vòng đời.

Các loại hệ thống có thể gặp:

- Cloud secret manager.
- Vault service tự quản lý.
- Kubernetes Secrets kết hợp encryption và access control phù hợp.
- HSM hoặc KMS cho thao tác khóa mật mã.
- Secret store nội bộ tích hợp với identity provider.

Việc chọn sản phẩm cụ thể phụ thuộc nền tảng và yêu cầu vận hành. Không nên giả định mọi secret store có cùng khả năng mã hóa, audit, rotation hoặc access policy.

### 6.1. Những năng lực cần xem xét

- Mã hóa dữ liệu khi lưu.
- Bảo vệ khi truyền.
- Authentication của client.
- Authorization theo secret path hoặc resource.
- Versioning.
- Rotation và revocation.
- Audit log.
- Replication và availability.
- Backup và recovery.
- API và SDK.
- Rate limit và quota.
- Multi-region hoặc multi-tenant support.

### 6.2. Secret store và KMS

Secret manager thường lưu và phân phối secret value. KMS tập trung quản lý key và thực hiện thao tác mật mã. Một hệ thống có thể dùng KMS để mã hóa dữ liệu trong secret manager.

Không phải mọi private key đều cần xuất ra khỏi KMS. Nếu chỉ cần ký, runtime có thể yêu cầu KMS ký payload thay vì tải private key thô về bộ nhớ.

### 6.3. Availability

Nếu runtime cần secret khi khởi động, secret manager trở thành dependency quan trọng. Cần xác định:

- Hành vi khi provider tạm thời không truy cập được.
- Có retry và backoff hay không.
- Có cache secret trong thời gian ngắn không.
- Workload hiện tại có tiếp tục chạy khi provider gián đoạn không.
- Khởi động mới có bị chặn không.

Cache có thể tăng availability nhưng cũng kéo dài thời gian secret cũ còn được sử dụng. Đây là trade-off cần cấu hình rõ.

## 7. Authentication và workload identity

Runtime cần chứng minh danh tính trước khi secret manager cấp dữ liệu.

### 7.1. Không dùng một master credential chung

Nếu mọi service dùng chung một token quản trị, việc xâm nhập một service có thể làm lộ tất cả secret. Mỗi workload nên có danh tính riêng và quyền tối thiểu.

### 7.2. Workload identity

Workload identity cho phép service xác thực bằng danh tính được nền tảng cấp, chẳng hạn service account, managed identity hoặc workload federation.

Ví dụ mô hình:

~~~text
service billing
    identity = "workload:billing-prod"
    secret_access = [
        "prod/billing/database-password",
        "prod/billing/payment-token"
    ]
~~~

Đây là cú pháp minh họa. Runtime dùng identity đã được nền tảng xác thực; không nên tin một chuỗi identity do DSL tự khai báo nếu chưa được ràng buộc với danh tính thực.

### 7.3. Human identity và workload identity

Người dùng đăng nhập để chỉnh sửa hoặc triển khai cấu hình không nhất thiết là danh tính mà ứng dụng dùng khi chạy. Cần phân biệt quyền của developer, CI job, deployment controller và service runtime.

### 7.4. Short-lived credentials

Credential có thời hạn ngắn làm giảm thời gian sử dụng được nếu bị lộ. Runtime có thể lấy token ngắn hạn từ identity provider thay vì lưu access key dài hạn.

### 7.5. Authentication không đồng nghĩa authorization

Authentication xác định chủ thể là ai. Authorization quyết định chủ thể đó được phép thực hiện hành động nào trên secret nào. Cần kiểm tra cả hai.

## 8. Authorization và nguyên tắc quyền tối thiểu

Quyền truy cập secret nên được cấp theo nhu cầu cụ thể.

### 8.1. Least privilege

Một service thanh toán chỉ nên đọc các secret cần cho hoạt động thanh toán. Nó không cần quyền đọc credential của database nhân sự hoặc signing key của dịch vụ khác.

### 8.2. Policy theo path

~~~text
allow identity "workload:billing-prod"
    read secret "prod/billing/*"

deny identity "workload:billing-prod"
    read secret "prod/payroll/*"
~~~

Đây là ví dụ policy giả định. Policy thực tế cần định nghĩa wildcard, inheritance, explicit deny và thứ tự đánh giá rõ ràng.

### 8.3. Phân quyền theo môi trường

Development, staging và production nên dùng namespace hoặc policy tách biệt. Credential thử nghiệm không được tự động có quyền truy cập production.

### 8.4. Phân quyền theo hành động

Các hành động có thể gồm:

- Create.
- Read.
- Update.
- Rotate.
- Revoke.
- Delete.
- List metadata.
- Manage policy.

Quyền list secret có thể tiết lộ cấu trúc hệ thống dù người dùng không đọc được giá trị. Nên cấp riêng theo nhu cầu.

### 8.5. Kiểm tra quyền tại runtime

Compiler có thể kiểm tra policy tĩnh nếu metadata sẵn có, nhưng runtime vẫn phải kiểm tra quyền thật khi phân giải secret. Quyền có thể bị thu hồi sau khi compile hoặc khác nhau giữa môi trường.

### 8.6. Multi-tenancy

Trong hệ thống nhiều tenant, secret của tenant A không được truy cập bởi workload tenant B. Cần gắn tenant identity vào authorization context và kiểm tra ở cả API lẫn storage layer.

## 9. Vòng đời của secret

Secret có vòng đời từ lúc tạo đến lúc hết hiệu lực và bị xóa.

~~~text
Create
  |
  v
Store securely
  |
  v
Grant access
  |
  v
Use
  |
  v
Rotate / Renew
  |
  v
Revoke
  |
  v
Expire / Destroy
~~~

### 9.1. Create

Secret nên được sinh bằng nguồn ngẫu nhiên mật mã phù hợp hoặc cấp bởi hệ thống có thẩm quyền. Không dùng password dễ đoán hoặc giá trị cố định dùng chung cho nhiều môi trường.

### 9.2. Store

Secret được lưu trong secret manager hoặc hệ thống bảo vệ tương đương. Quyền truy cập storage và khóa mã hóa cần được kiểm soát.

### 9.3. Distribute

Secret được cấp cho workload qua kênh xác thực và bảo vệ. Không gửi qua ticket, chat hoặc log thông thường.

### 9.4. Use

Runtime chỉ giữ secret trong phạm vi và thời gian cần thiết. Tránh sao chép sang nhiều object, file tạm hoặc biến môi trường toàn cục nếu có phương án an toàn hơn.

### 9.5. Rotate

Thay giá trị cũ bằng giá trị mới theo quy trình có kiểm soát. Cần phối hợp giữa provider và consumer để tránh downtime.

### 9.6. Revoke

Thu hồi quyền hoặc làm secret cũ mất hiệu lực khi không còn được phép sử dụng, bị lộ hoặc chủ thể không còn hoạt động.

### 9.7. Destroy

Xóa secret và các bản sao theo chính sách retention. Cần hiểu rằng backup, replica hoặc snapshot có thể còn giữ dữ liệu trong thời gian nhất định.

## 10. Rotation và cập nhật secret

Rotation là việc thay secret định kỳ hoặc theo sự kiện để giảm rủi ro khi credential bị lộ hoặc quá cũ.

### 10.1. Rotation thủ công

Quản trị viên tạo giá trị mới, cập nhật secret store, triển khai consumer và thu hồi giá trị cũ. Quy trình cần có xác nhận rằng mọi consumer đã chuyển sang giá trị mới.

### 10.2. Rotation tự động

Secret manager có thể tạo credential mới, cập nhật version và thông báo cho consumer. Tự động hóa giảm thao tác thủ công nhưng cần thiết kế retry, rollback và đồng bộ trạng thái.

### 10.3. Overlap period

Một số hệ thống cho phép hai credential cùng hợp lệ trong thời gian chuyển đổi:

1. Tạo credential mới.
2. Cho phép cả cũ và mới.
3. Cập nhật consumer sang mới.
4. Xác nhận consumer đã chuyển.
5. Thu hồi credential cũ.

Không phải hệ thống nào cũng hỗ trợ hai credential cùng lúc. Nếu không có overlap, cần kế hoạch bảo trì hoặc cơ chế chuyển đổi khác.

### 10.4. Rotation và connection pool

Database password có thể đã được dùng để tạo connection hiện tại. Thay password trong secret store không tự thay credential của connection đang mở. Runtime có thể cần tạo connection mới, drain pool cũ và đóng kết nối cũ theo trình tự.

### 10.5. Dynamic secrets

Một số secret manager có thể tạo credential ngắn hạn theo yêu cầu, ví dụ user database có TTL. Runtime nhận credential có thời hạn, dùng trong khoảng lease và gia hạn hoặc lấy mới theo policy.

### 10.6. Rotation không đồng nghĩa đổi reference

Nếu reference trỏ đến alias hiện hành, giá trị có thể đổi mà source không đổi. Nếu reference pin một version, cần cập nhật cấu hình hoặc deployment để chuyển sang version mới. Cần chọn semantics rõ.

## 11. Versioning, pinning và reproducibility

Secret reference có thể dùng version cụ thể hoặc alias động.

### 11.1. Pin version

~~~text
api_token = secret_ref(
    path = "prod/billing/payment-token",
    version = "12"
)
~~~

Pin version giúp xác định chính xác secret version mà deployment mong đợi. Nó hỗ trợ audit và tái lập, nhưng có thể làm rotation cần một thay đổi cấu hình.

### 11.2. Alias động

~~~text
api_token = secret_ref(
    path = "prod/billing/payment-token",
    version = "current"
)
~~~

Alias thuận tiện cho rotation. Tuy nhiên, cùng artifact có thể resolve thành giá trị khác ở các thời điểm khác nhau. Cần ghi lại version ID thực tế đã được resolve trong deployment metadata, không ghi giá trị secret.

### 11.3. Immutable release

Với deployment cần tái lập, có thể tạo release manifest ghi secret version ID thay vì secret value. Khi redeploy, hệ thống có thể yêu cầu đúng version đó nếu policy cho phép.

### 11.4. Version đã bị thu hồi

Nếu một version bị thu hồi vì lộ, pinning không được phép buộc runtime sử dụng lại version đó. Revocation policy phải có ưu tiên cao hơn yêu cầu tái lập.

### 11.5. Secret metadata

Metadata hữu ích có thể gồm owner, purpose, createdAt, expiresAt, version, rotation policy và classification. Không lưu secret value trong metadata.

## 12. Bảo vệ secret khi lưu trữ

Secret store cần bảo vệ dữ liệu khi nằm trên đĩa, trong backup và trong replica.

### 12.1. Encryption at rest

Mã hóa khi lưu giúp giảm rủi ro nếu storage media hoặc backup bị truy cập trái phép. Cần bảo vệ encryption key riêng, lý tưởng qua KMS hoặc HSM tùy yêu cầu.

### 12.2. Envelope encryption

Envelope encryption dùng data encryption key để mã hóa dữ liệu; key đó lại được mã hóa bằng key quản lý trong KMS.

~~~text
Secret plaintext
      |
      | encrypt with DEK
      v
Encrypted secret

DEK
 |
 | encrypt with KEK in KMS
 v
Wrapped DEK
~~~

Khi giải mã, hệ thống yêu cầu KMS unwrap DEK rồi dùng DEK giải mã secret. Việc tách key dữ liệu và key bảo vệ giúp xoay vòng key quản lý linh hoạt hơn.

### 12.3. Encryption in transit

Secret phải được truyền qua kênh được xác thực và mã hóa, ví dụ TLS với cấu hình phù hợp. Cần xác minh server identity và tránh bỏ qua certificate validation.

### 12.4. Backup

Backup secret store cũng chứa dữ liệu nhạy cảm. Cần mã hóa, giới hạn quyền restore, audit và kiểm tra quy trình phục hồi.

### 12.5. Replica

Replication có thể tăng availability nhưng mở rộng số nơi chứa dữ liệu. Cần bảo vệ từng replica và xác định chính sách xóa/thu hồi nhất quán.

### 12.6. Xóa an toàn

Xóa một record khỏi database không nhất thiết xóa mọi bản sao vật lý, snapshot hoặc backup. Cần chính sách retention và cryptographic erasure nếu phù hợp với kiến trúc.

## 13. Bảo vệ secret trong compiler và artifact

Compiler là một ranh giới quan trọng vì nó có thể tạo nhiều bản sao dữ liệu.

### 13.1. Không resolve secret khi parse

Parser chỉ nên tạo node SecretRef từ source. Nó không cần gọi secret manager.

### 13.2. Không nhúng secret vào AST hoặc IR

AST, IR và generated code thường được lưu, cache hoặc in ra để debug. Nếu secret value đi vào những cấu trúc này, nó có thể bị lưu ngoài ý muốn.

### 13.3. Artifact giữ reference

Artifact triển khai nên chứa secret reference và policy metadata cần thiết. Runtime mới lấy giá trị theo danh tính và quyền được cấp.

### 13.4. Compile-time secret

Một số hệ thống cần secret trong quá trình build, ví dụ ký artifact. Nếu thật sự cần, nên dùng signing service hoặc KMS để thực hiện thao tác mà không xuất private key. Hạn chế quyền CI và thời gian credential có hiệu lực.

### 13.5. Build cache

Không đưa secret value vào cache key, cache output hoặc build log. Nếu build result phụ thuộc vào secret, cần cân nhắc liệu secret có thực sự nên ảnh hưởng kết quả build hay có thể chuyển sang runtime.

### 13.6. Generated source

Không sinh password hoặc token vào source code, script hoặc file cấu hình đã render. Nếu một target buộc cần materialized secret, phải dùng vùng lưu tạm được bảo vệ và xóa theo chính sách; ưu tiên cơ chế runtime injection.

## 14. Bảo vệ secret trong runtime

Runtime là nơi secret thường được phân giải và sử dụng.

### 14.1. Just-in-time resolution

Lấy secret gần thời điểm sử dụng giúp giảm thời gian giữ giá trị trong bộ nhớ và giúp áp dụng rotation mới. Tuy nhiên, gọi provider cho mỗi thao tác có thể tăng latency và phụ thuộc availability. Cần chọn thời điểm và cache policy phù hợp.

### 14.2. In-memory handling

Một số nguyên tắc:

- Giới hạn số object chứa secret.
- Không giữ secret lâu hơn cần thiết.
- Không đưa secret vào exception message.
- Tránh tạo nhiều bản sao string.
- Dùng API hỗ trợ buffer có thể xóa khi phù hợp.
- Không giả định garbage collection xóa ngay dữ liệu nhạy cảm.

Trong Java, String là immutable và có thể tồn tại trong heap đến khi được thu hồi; việc xóa nội dung khỏi bộ nhớ không được bảo đảm. Với dữ liệu cần kiểm soát vòng đời chặt, có thể cân nhắc byte[] hoặc char[] và ghi đè buffer sau khi sử dụng, nhưng vẫn cần hiểu các bản sao trung gian và giới hạn của JVM.

### 14.3. Environment variables

Environment variable là một cách truyền cấu hình phổ biến, nhưng không phải secret manager. Giá trị có thể bị lộ qua process inspection, crash dump, child process hoặc tooling tùy hệ điều hành và cách triển khai.

Nếu dùng, giới hạn quyền đọc process, tránh in environment vào log và ưu tiên workload identity hoặc secret file/mount được bảo vệ khi nền tảng hỗ trợ.

### 14.4. Command-line arguments

Không truyền secret trực tiếp qua command-line argument nếu có thể tránh. Argument có thể xuất hiện trong process list, shell history hoặc log của công cụ orchestration.

### 14.5. Temporary files

Nếu buộc phải dùng file tạm:

- Tạo trong thư mục có quyền hạn chế.
- Dùng tên không dễ đoán và không ghi đè file khác.
- Không để file trong workspace hoặc artifact directory.
- Xóa sau khi sử dụng.
- Bảo vệ backup và snapshot của filesystem.

Xóa file không bảo đảm mọi bản sao trên storage đã biến mất.

### 14.6. Process isolation

Workload không cần secret không nên chạy cùng quyền hoặc cùng process context với workload có quyền đọc secret. Tách process/container và identity giúp giảm ảnh hưởng khi một thành phần bị xâm nhập.

## 15. Ngăn rò rỉ qua log, diagnostics và telemetry

Một lỗi phổ biến là source không chứa secret nhưng log lại ghi giá trị đã resolve.

### 15.1. Redaction

Trước khi ghi log, runtime nên loại hoặc che trường nhạy cảm:

~~~text
database.password = [REDACTED]
payment.token = [REDACTED]
database.host = db.internal
~~~

Redaction cần dựa trên type hoặc sensitivity metadata, không chỉ tìm tên field có chữ password. Một token có thể nằm trong URL, exception hoặc payload tùy ý.

### 15.2. Structured logging

Structured logging giúp đánh dấu field nhạy cảm:

~~~text
{
    "event": "database_connection_failed",
    "service": "billing",
    "secret_ref": "prod/billing/database-password",
    "secret_value": "[REDACTED]"
}
~~~

Log secret reference cũng cần xem xét vì path có thể tiết lộ cấu trúc nội bộ. Có thể dùng opaque ID hoặc redact một phần.

### 15.3. Exception handling

Không nối secret vào exception message. Khi provider trả lỗi, log mã lỗi, request ID và secret reference đã được lọc thay vì payload phản hồi chứa thông tin nhạy cảm.

### 15.4. Tracing

Trace span có thể chứa attributes. Cần áp dụng chính sách redaction tương tự log; không ghi credential vào span event hoặc baggage.

### 15.5. Metrics và labels

Không dùng secret value làm metric label. Labels có thể được lưu lâu và nhân bản sang nhiều hệ thống. Dùng loại secret, provider hoặc trạng thái thay vì giá trị.

### 15.6. Crash dump

Heap dump và core dump có thể chứa secret trong bộ nhớ. Quyền tạo, lưu, tải và retention của dump cần được kiểm soát. Trong môi trường nhạy cảm, cân nhắc tắt hoặc hạn chế dump theo chính sách.

## 16. Secret trong editor, CLI và CI/CD

Quy trình phát triển cũng là một nguồn rò rỉ.

### 16.1. Editor

Editor nên hiển thị reference, không tải secret value chỉ để autocomplete hoặc hover. Nếu có chức năng preview giá trị, cần xác thực quyền rõ ràng và tránh lưu vào history hoặc telemetry.

### 16.2. CLI

CLI có thể nhận secret reference và yêu cầu runtime resolve. Không nên yêu cầu người dùng dán token vào command line. Có thể dùng device login, browser flow hoặc secret manager integration.

### 16.3. CI/CD

CI job chỉ nên có quyền truy cập secret cần cho job đó. Tách credential build, test, deploy và production runtime.

### 16.4. Masked variables

Một số CI platform hỗ trợ masked variable, nhưng masking chỉ giúp che trong một số log. Nó không bảo vệ khỏi script độc hại, artifact, process dump hoặc quyền truy cập quá rộng.

### 16.5. Pull request từ bên ngoài

Không cấp production secret cho pipeline chạy code không tin cậy từ fork hoặc pull request chưa được phê duyệt. Một script build có thể đọc mọi secret mà job được cấp.

### 16.6. Build logs

Tránh bật debug mode có thể in toàn bộ environment, HTTP headers hoặc request payload. Cần kiểm thử redaction trong các failure path, không chỉ log thành công.

## 17. Secret scanning và phát hiện lộ lọt

Secret scanning tìm các mẫu có khả năng là credential trong repository, commit, artifact hoặc log.

### 17.1. Pattern scanning

Scanner có thể nhận diện:

- Token theo định dạng nhà cung cấp.
- Private key header.
- Connection string có password.
- Credential có entropy cao.
- Các mẫu đã biết của API key.

Pattern scanning có thể tạo false positive và không phát hiện mọi secret. Không nên xem việc scanner không tìm thấy gì là bằng chứng source hoàn toàn sạch.

### 17.2. Push protection

Repository có thể chặn commit chứa secret đã nhận diện. Điều này giảm khả năng credential đi vào lịch sử Git.

### 17.3. Historical scanning

Quét cả lịch sử commit vì secret có thể nằm trong revision cũ dù file hiện tại đã được sửa.

### 17.4. Artifact scanning

Quét package, container image, generated file và build artifact. Secret có thể bị nhúng trong binary hoặc file cấu hình được render.

### 17.5. Xử lý khi phát hiện

Khi tìm thấy secret:

1. Xác định loại secret và phạm vi ảnh hưởng.
2. Thu hồi hoặc xoay vòng credential.
3. Kiểm tra audit log để xác định truy cập bất thường.
4. Xóa hoặc thay nội dung khỏi nguồn hiện tại.
5. Xử lý lịch sử và artifact theo quy trình của tổ chức.
6. Xác định đường rò rỉ và bổ sung guardrail.

Không nên chỉ xóa commit hoặc sửa file rồi tiếp tục dùng credential cũ nếu có khả năng đã bị lộ.

## 18. Secret taint và kiểm soát luồng dữ liệu

Một compiler hoặc runtime nâng cao có thể theo dõi dữ liệu nhạy cảm qua các biểu thức.

### 18.1. Taint label

Giá trị có thể mang nhãn:

~~~text
Public<String>
Internal<String>
Secret<String>
~~~

Khi một biểu thức dùng secret làm đầu vào, kết quả có thể kế thừa nhãn Secret theo quy tắc propagation.

### 18.2. Sink nhạy cảm

Các sink có thể bị hạn chế:

- Logger.
- Diagnostic message.
- Telemetry.
- File output.
- Public API response.
- Command-line output.
- Visualization label.

Compiler hoặc policy engine có thể cảnh báo khi Secret value đi vào sink không được phép.

### 18.3. Declassification

Một số phép biến đổi có thể tạo dữ liệu an toàn hơn, ví dụ kiểm tra secret có tồn tại hoặc lấy trạng thái credential mà không trả giá trị. Declassification cần được định nghĩa tường minh và giới hạn.

### 18.4. Secret reference trong expression

Không nên cho phép nối SecretRef với chuỗi tùy ý rồi vô tình tạo ra secret value trong nơi không được kiểm soát. DSL có thể yêu cầu hàm resolve rõ ràng hoặc chỉ cho phép truyền reference vào các trường có kiểu secret-compatible.

### 18.5. Giới hạn của static analysis

Phân tích tĩnh có thể bỏ sót đường đi qua plugin, native code, dynamic expression hoặc dữ liệu runtime. Taint tracking giúp giảm rủi ro nhưng không thay thế kiểm soát quyền và redaction tại runtime.

## 19. Secret và cấu hình theo môi trường

Một DSL thường được triển khai ở development, staging và production.

### 19.1. Cùng cấu trúc, reference khác nhau

~~~text
environment "development" {
    database_password = secret_ref("dev/billing/db-password")
}

environment "production" {
    database_password = secret_ref("prod/billing/db-password")
}
~~~

Mỗi môi trường có secret riêng. Không nên copy credential production sang development chỉ để tiện kiểm thử.

### 19.2. Environment overlay

Có thể dùng cấu hình cơ sở và override reference theo môi trường. Cần xác định thứ tự merge và bảo đảm override không vô tình thay một secret reference bằng giá trị plaintext.

### 19.3. Environment promotion

Khi promote artifact từ staging sang production, artifact có thể giữ logical secret name và runtime resolve theo namespace production. Cách này giúp không phải đóng gói secret value trong artifact.

### 19.4. Configuration drift

Alias động hoặc secret version thay đổi có thể khiến các instance chạy cùng release dùng giá trị khác nhau. Cần quan sát version ID đã resolve và policy rollout.

### 19.5. Separation of duties

Developer có thể chỉnh cấu hình nhưng không được đọc production secret. Người quản trị secret có thể quản lý credential nhưng không nhất thiết được thay đổi logic workflow. Phân tách này giảm nguy cơ lạm dụng quyền.

## 20. Dynamic secret, certificate và key management

Không phải bí mật nào cũng là một chuỗi tĩnh.

### 20.1. Dynamic credentials

Secret manager có thể tạo credential theo yêu cầu với thời hạn ngắn và quyền giới hạn. Runtime nhận lease ID hoặc expiry metadata để gia hạn và thu hồi.

### 20.2. Certificate lifecycle

Certificate và private key có thể có:

- Subject hoặc service identity.
- Validity period.
- Issuer.
- Chain.
- Renewal policy.
- Revocation status.

Visualizer hoặc validator có thể cảnh báo certificate sắp hết hạn mà không hiển thị private key.

### 20.3. Private key non-exportable

Nếu key được lưu trong HSM/KMS, runtime có thể yêu cầu ký hoặc giải mã qua API. Key material không cần rời thiết bị bảo vệ.

### 20.4. Key rotation

Khi xoay key mã hóa, có thể cần giữ key cũ để giải mã dữ liệu đã mã hóa trước đó, trong khi dùng key mới cho dữ liệu mới. Rotation key mã hóa dữ liệu khác với rotation password của service; semantics cần được tách.

### 20.5. Certificate pinning và trust roots

Nếu DSL cấu hình trust root hoặc certificate pin, cần quy trình cập nhật để tránh outage khi certificate đổi. Không nhúng private key vào source chỉ để thiết lập trust.

## 21. Kiểm thử và phát triển với secret

Môi trường test không nên phụ thuộc credential production.

### 21.1. Fake secret provider

Trong unit test, có thể dùng provider giả trả giá trị test:

~~~text
secret_provider = fake {
    "test/billing/db-password" = "test-only-value"
}
~~~

Giá trị ví dụ chỉ dùng trong test và không được tái sử dụng ở production.

### 21.2. Test credential riêng

Integration test có thể dùng account riêng, quyền tối thiểu và thời hạn ngắn. Sau test, thu hồi credential hoặc để lease tự hết hạn.

### 21.3. Không snapshot secret thật

Golden file, snapshot test và fixture không nên chứa secret thật. Dùng placeholder hoặc reference ổn định.

### 21.4. Kiểm thử redaction

Tạo lỗi có chứa secret trong input hoặc exception giả lập và xác nhận log, diagnostics, tracing và output không làm lộ giá trị.

### 21.5. Kiểm thử rotation

Xác nhận consumer nhận version mới, connection pool được làm mới, version cũ bị thu hồi và workload phục hồi khi provider tạm thời không sẵn sàng.

### 21.6. Kiểm thử authorization

Kiểm tra cả trường hợp được phép và bị từ chối:

- Workload đúng identity đọc đúng secret.
- Workload khác không đọc được.
- Production identity không dùng trong development.
- User không có quyền không thể list hoặc resolve secret.
- Revoked identity bị từ chối.

## 22. Triển khai secret provider bằng Java

Một runtime Java có thể tách việc tìm secret khỏi phần thực thi DSL bằng interface provider.

### 22.1. Mô hình reference

~~~java
public record SecretReference(
        String provider,
        String path,
        String version
) {
}
~~~

Reference chỉ chứa metadata định vị secret. Không đặt secret value trong object này.

### 22.2. Provider interface

~~~java
import java.util.Optional;

public interface SecretProvider {
    Optional<SecretValue> resolve(SecretReference reference);
}
~~~

SecretValue là kiểu được kiểm soát riêng, không nên tự động in giá trị trong toString.

### 22.3. Value wrapper

~~~java
import java.util.Arrays;

public final class SecretValue implements AutoCloseable {
    private final char[] value;

    public SecretValue(char[] value) {
        this.value = value.clone();
    }

    public char[] copyForUse() {
        return value.clone();
    }

    @Override
    public String toString() {
        return "[REDACTED]";
    }

    @Override
    public void close() {
        Arrays.fill(value, '\0');
    }
}
~~~

Đây là ví dụ minh họa cách giới hạn vòng đời một buffer. Việc ghi đè mảng không bảo đảm mọi bản sao đã được tạo trong JVM hoặc thư viện bên dưới đều bị xóa. API production cần giảm việc copy và quy định rõ ai sở hữu, ai đóng SecretValue.

### 22.4. Resolve trong runtime

~~~java
void connect(
        SecretProvider provider,
        SecretReference reference
) {
    try (SecretValue secret = provider.resolve(reference)
            .orElseThrow()) {
        char[] credential = secret.copyForUse();
        try {
            openDatabaseConnection(credential);
        } finally {
            java.util.Arrays.fill(credential, '\0');
        }
    }
}
~~~

Ví dụ giả định API database có thể nhận char array. Nhiều thư viện chỉ nhận String; khi đó cần đánh giá vòng đời và khả năng lộ của String. Không ghi giá trị vào exception hoặc log.

### 22.5. Authorization context

Provider nên nhận identity từ runtime security context đã được xác thực, không lấy một chuỗi identity tùy ý từ DSL:

~~~java
public interface SecretProvider {
    SecretValue resolve(
        WorkloadIdentity identity,
        SecretReference reference
    );
}
~~~

Provider hoặc secret manager phải xác minh quyền của identity cho reference cụ thể. Kiểm tra tại compiler không thay thế authorization tại thời điểm truy cập.

### 22.6. Error handling

Phân biệt:

- Secret không tồn tại.
- Version không tồn tại.
- Access denied.
- Provider unavailable.
- Credential hết hạn.
- Response không đúng định dạng.

Message có thể chứa secret reference đã được lọc và request ID, nhưng không chứa response body hoặc secret value.

## 23. Audit và observability

Quản lý bí mật cần khả năng trả lời ai đã truy cập secret, vào thời điểm nào và trong ngữ cảnh nào.

### 23.1. Audit event

Một event có thể ghi:

- Principal hoặc workload identity.
- Secret identifier hoặc opaque resource ID.
- Action: read, rotate, revoke, policy change.
- Timestamp.
- Result: allowed hoặc denied.
- Request/correlation ID.
- Source environment.
- Version ID nếu phù hợp.

Không ghi secret value vào audit log.

### 23.2. Alerting

Có thể cảnh báo khi:

- Một identity truy cập secret ngoài phạm vi thông thường.
- Một service đọc số lượng secret bất thường.
- Secret bị đọc từ môi trường không mong đợi.
- Có nhiều lần access denied.
- Secret sắp hết hạn.
- Key hoặc certificate bị thu hồi.
- Policy thay đổi ngoài quy trình.

### 23.3. Access inventory

Liệt kê workload nào đang dùng secret nào. Inventory hỗ trợ thu hồi credential cũ và phát hiện secret không còn consumer.

### 23.4. Rotation status

Theo dõi version hiện tại, consumer đã chuyển đổi, lease còn hiệu lực và thời điểm credential cũ bị thu hồi. Trạng thái này nên được lưu riêng với secret value.

### 23.5. Audit log protection

Audit log cần quyền ghi và đọc được kiểm soát, có retention phù hợp và khả năng phát hiện sửa đổi. Nếu attacker có thể xóa dấu vết truy cập secret, audit không còn đáng tin.

## 24. Xử lý sự cố lộ secret

Khi nghi ngờ secret bị lộ, cần ưu tiên ngăn truy cập tiếp tục và xác định phạm vi.

Quy trình tổng quát:

1. Xác định secret, loại credential, owner và các consumer.
2. Đánh giá khả năng secret đã bị sử dụng trái phép.
3. Thu hồi hoặc vô hiệu hóa credential cũ theo mức độ khẩn cấp.
4. Tạo credential mới và phân phối qua kênh tin cậy.
5. Cập nhật workload và xác nhận hoạt động bình thường.
6. Kiểm tra audit log, access history và hệ thống có liên quan.
7. Tìm các bản sao trong repository, CI log, artifact, backup và telemetry.
8. Xử lý lịch sử và artifact theo quy trình tổ chức.
9. Xác định nguyên nhân gốc và bổ sung biện pháp ngăn tái diễn.
10. Ghi nhận thời điểm, quyết định và phạm vi ảnh hưởng.

### 24.1. Revoke trước hay rotate trước?

Thứ tự phụ thuộc khả năng overlap và mức độ khẩn cấp. Nếu credential đang bị lạm dụng, thu hồi ngay có thể quan trọng hơn duy trì availability. Nếu hệ thống hỗ trợ hai credential đồng thời, có thể tạo mới, chuyển consumer rồi thu hồi cũ. Cần có runbook theo từng loại secret.

### 24.2. Secret trong Git history

Nếu secret đã commit, xóa file ở commit mới không loại bỏ giá trị trong history, fork hoặc clone. Việc rewrite history có thể giảm khả năng tiếp tục tìm thấy secret nhưng không thay thế rotation.

### 24.3. Secret trong image và artifact

Artifact đã phát hành có thể được mirror hoặc cache. Cần xác định nơi lưu và thu hồi quyền truy cập nếu cần. Secret value đã nhúng không thể được bảo vệ chỉ bằng cách phát hành một manifest mới.

### 24.4. Incident evidence

Giữ audit và log cần thiết để điều tra, nhưng tránh sao chép secret value vào báo cáo sự cố. Dùng secret ID, version ID và dấu vết truy cập.

## 25. Những sai lầm thường gặp

### 25.1. Ghi password trực tiếp trong DSL

Source thường được commit, review, copy và lưu lâu dài. Dùng secret reference và để runtime resolve giá trị.

### 25.2. Coi environment variable là secret manager

Environment variable chỉ là một kênh truyền giá trị. Nó không tự cung cấp versioning, rotation, authorization, audit hoặc revocation.

### 25.3. Dùng credential toàn quyền cho mọi workload

Một credential chung làm tăng blast radius. Cấp identity và policy riêng cho từng service, môi trường và mục đích.

### 25.4. Resolve secret trong compiler

Điều này làm compiler và CI cần quyền đọc secret, đồng thời có nguy cơ nhúng giá trị vào AST, IR, cache hoặc generated artifact. Chỉ resolve ở build time khi có lý do rõ và kiểm soát riêng.

### 25.5. Log request hoặc exception đầy đủ

Response của secret provider hoặc connection string có thể chứa credential. Dùng structured logging, redaction và mã lỗi an toàn.

### 25.6. Không xoay vòng secret

Credential tồn tại quá lâu làm tăng thời gian attacker có thể sử dụng nếu bị lộ. Xây rotation policy và theo dõi consumer.

### 25.7. Rotate nhưng không cập nhật consumer

Secret store có giá trị mới nhưng connection pool hoặc service vẫn dùng credential cũ. Cần xác nhận rollout và trạng thái sử dụng thực tế.

### 25.8. Cache không có TTL hoặc invalidation

Cache vô thời hạn làm secret cũ tiếp tục có hiệu lực sau rotation hoặc revoke. Đặt TTL, refresh policy và hành vi khi provider lỗi.

### 25.9. Coi secret reference là vô hại

Path hoặc metadata có thể tiết lộ tên hệ thống, tenant hoặc mục đích. Giới hạn quyền list và redact khi cần.

### 25.10. Nhúng private key vào artifact

Artifact thường được sao chép rộng. Với thao tác ký, ưu tiên KMS/HSM hoặc signing service để private key không rời vùng bảo vệ.

### 25.11. Chỉ quét source hiện tại

Secret có thể nằm trong Git history, build log, container image, cache và backup. Quét các nơi có thể lưu bản sao.

### 25.12. Không có quy trình incident

Khi phát hiện lộ secret, nhóm cần biết ai có quyền thu hồi, cách cấp mới, cập nhật consumer và kiểm tra audit. Không nên thiết kế quy trình lần đầu trong lúc sự cố xảy ra.

### 25.13. Coi che dấu giao diện là bảo mật

Ẩn giá trị trên UI không bảo vệ source, API, memory, log hoặc artifact. Bảo vệ phải được thực hiện xuyên suốt đường đi của dữ liệu.

## 26. Quy trình thiết kế quản lý bí mật cho DSL

Một quy trình triển khai có thể gồm:

1. **Phân loại dữ liệu.** Xác định trường nào là public, internal, confidential hoặc secret.
2. **Xác định threat model.** Xem ai có thể đọc source, artifact, log, runtime memory và secret store.
3. **Thiết kế SecretRef.** Định nghĩa cú pháp, kiểu, provider, path, version và metadata được phép.
4. **Tách compile và resolve.** Compiler giữ reference; runtime hoặc service chuyên trách lấy giá trị.
5. **Chọn secret manager.** Đánh giá API, encryption, identity, policy, audit, rotation và availability.
6. **Thiết kế workload identity.** Cấp danh tính riêng, ngắn hạn và quyền tối thiểu.
7. **Định nghĩa authorization.** Giới hạn secret theo workload, môi trường, tenant và hành động.
8. **Thiết kế vòng đời.** Create, store, distribute, use, rotate, revoke và destroy.
9. **Bảo vệ storage và transport.** Mã hóa, quản lý key, backup và replica.
10. **Bảo vệ compiler artifact.** Không nhúng secret value vào AST, IR, cache, generated source hoặc package.
11. **Bảo vệ runtime.** Giảm bản sao trong bộ nhớ, giới hạn TTL và quản lý resource.
12. **Ngăn rò rỉ.** Redact log, diagnostics, trace, metrics, dump và output.
13. **Thêm scanning và audit.** Quét repository/artifact và theo dõi truy cập.
14. **Kiểm thử.** Bao phủ authorization, rotation, revoke, provider outage và redaction.
15. **Chuẩn bị incident response.** Có runbook thu hồi, cấp mới, rollout và điều tra.

Mức triển khai phụ thuộc loại DSL và mức độ nhạy cảm. Tuy nhiên, mọi hệ thống có secret thật đều cần biết secret nằm ở đâu, ai có thể lấy, nó đi qua thành phần nào và cách thu hồi khi cần.

## 27. Câu hỏi tự kiểm tra

1. Quản lý bí mật là gì và vì sao quan trọng với DSL cấu hình?
2. Phân biệt cấu hình thông thường, secret, khóa mật mã và dữ liệu nhạy cảm khác.
3. Vì sao không nên ghi password hoặc API token trực tiếp trong source DSL?
4. Secret reference khác secret value như thế nào?
5. Một kiến trúc secret management điển hình gồm những thành phần nào?
6. Phân biệt secret manager và KMS.
7. Workload identity hỗ trợ xác thực runtime ra sao?
8. Authentication khác authorization như thế nào?
9. Least privilege và separation of duties giúp giảm rủi ro gì?
10. Trình bày vòng đời của secret từ create đến destroy.
11. Rotation có overlap period giúp tránh downtime như thế nào?
12. Secret version pinning và alias động có trade-off gì?
13. Encryption at rest, encryption in transit và envelope encryption bảo vệ những giai đoạn nào?
14. Vì sao compiler nên giữ SecretRef thay vì resolve secret value khi parse hoặc generate code?
15. Những nguy cơ nào xuất hiện khi secret đi qua environment variable, command-line argument, temporary file hoặc JVM heap?
16. Redaction cần được áp dụng ở log, diagnostic, tracing và metrics ra sao?
17. Secret scanning có thể tìm thấy những loại rò rỉ nào và giới hạn của nó là gì?
18. Secret taint tracking có thể ngăn dữ liệu nhạy cảm đi vào những sink nào?
19. Khi secret bị lộ trong Git history hoặc artifact, vì sao chỉ xóa file hiện tại là chưa đủ?
20. Hãy thiết kế quy trình resolve một SecretRef cho service production, gồm identity, authorization, cache, rotation và audit.
21. Hãy đề xuất runbook xử lý sự cố khi API token của một workload bị lộ.

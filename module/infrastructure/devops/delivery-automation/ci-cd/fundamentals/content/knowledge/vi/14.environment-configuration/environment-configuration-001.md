# Phân biệt mã ứng dụng, cấu hình và thông tin bí mật

Một ứng dụng có thể chạy ở môi trường phát triển, kiểm thử, staging và production. Phần lớn logic nghiệp vụ cần giữ nguyên giữa các môi trường, nhưng địa chỉ database, mức log, giới hạn kết nối, feature flag và thông tin xác thực có thể khác nhau. Nếu trộn các giá trị này vào mã nguồn hoặc đóng gói tất cả vào một artifact, việc triển khai sẽ khó kiểm soát, khó truy vết và dễ làm lộ dữ liệu nhạy cảm.

Khi thiết kế CI/CD, cần phân biệt rõ ba nhóm:

- **Mã ứng dụng (application code):** mô tả hành vi và logic của phần mềm, được quản lý bằng version control, review và build thành artifact.
- **Cấu hình (configuration):** các giá trị điều khiển cách ứng dụng hoạt động trong một môi trường hoặc một lần chạy, chẳng hạn endpoint, timeout, mức log và feature flag.
- **Thông tin bí mật (secrets):** dữ liệu xác thực hoặc khóa nhạy cảm cần được bảo vệ, chẳng hạn mật khẩu, access token, private key và credential kết nối.

Ba nhóm có vòng đời, quyền truy cập và cách phân phối khác nhau. Tách chúng giúp một artifact đã kiểm thử có thể được đưa qua nhiều môi trường, cấu hình có thể được thay đổi có kiểm soát và bí mật được cấp đúng nơi cần dùng.

## 1. Nhận diện ba nhóm dữ liệu

### Mã ứng dụng

Mã ứng dụng định nghĩa chương trình làm gì và xử lý yêu cầu như thế nào. Nó bao gồm source code, test, schema hoặc tài nguyên được quản lý như một phần của sản phẩm, build script và các định nghĩa cần thiết để tạo artifact.

Ví dụ:

- Quy tắc tính phí, xác thực nghiệp vụ và xử lý đơn hàng.
- API endpoint mà ứng dụng cung cấp.
- Cách ứng dụng đọc cấu hình và kết nối tới dịch vụ.
- Quy tắc retry, xử lý lỗi và kiểm tra dữ liệu đầu vào.
- Mã kiểm thử, migration và cấu hình build có liên quan tới sản phẩm.

Mã ứng dụng thường được lưu trong repository, thay đổi qua commit và Pull Request. Một phiên bản mã nguồn cụ thể được nhận diện bằng commit SHA và có thể được build thành artifact như JAR, binary hoặc container image.

### Cấu hình

Cấu hình cung cấp giá trị để điều khiển hành vi của cùng một phiên bản ứng dụng trong các bối cảnh khác nhau. Cấu hình có thể thay đổi theo môi trường, tenant, vùng triển khai hoặc thời điểm vận hành.

Ví dụ:

- URL của database, message broker hoặc API bên ngoài.
- Mức log, timeout, retry limit và connection pool size.
- Số worker, giới hạn request hoặc kích thước batch.
- Feature flag, chế độ bảo trì và giới hạn nghiệp vụ có thể điều chỉnh.
- Tên bucket, queue hoặc namespace.
- Đường dẫn tới chứng thư công khai hoặc endpoint của secret manager.

Cấu hình không nhất thiết là bí mật. Một URL nội bộ có thể nhạy cảm về kiến trúc nhưng không phải credential; một log level như INFO thường không cần bảo vệ như mật khẩu. Tuy nhiên, cấu hình vẫn cần được quản lý, review và giới hạn quyền thay đổi vì giá trị sai có thể làm ứng dụng ngừng hoạt động hoặc tạo rủi ro bảo mật.

### Thông tin bí mật

Secret là dữ liệu mà người không được phép biết hoặc sử dụng có thể gây truy cập trái phép, giả mạo danh tính, đọc dữ liệu hoặc thay đổi hệ thống.

Ví dụ:

- Mật khẩu database và tài khoản dịch vụ.
- API token, OAuth client secret và access token.
- Private key dùng để ký artifact, chứng thư hoặc xác thực.
- Credential của cloud, registry và hệ thống deploy.
- Khóa mã hóa và recovery key.
- Chuỗi kết nối có chứa username/password hoặc token.

Không phải mọi dữ liệu nhạy cảm đều là secret. Dữ liệu cá nhân, dữ liệu khách hàng hoặc thông tin nội bộ có thể thuộc nhóm dữ liệu cần bảo vệ riêng theo chính sách dữ liệu. Phân loại secret tập trung vào khả năng xác thực, cấp quyền hoặc giải mã; phân loại dữ liệu cần xem thêm tính riêng tư và quy định lưu trữ.

### Bảng phân biệt nhanh

| Tiêu chí | Mã ứng dụng | Cấu hình | Secret |
|---|---|---|---|
| Mục đích | Định nghĩa hành vi phần mềm | Điều chỉnh hành vi theo môi trường hoặc lần chạy | Xác thực, cấp quyền hoặc bảo vệ dữ liệu |
| Ví dụ | Logic tính phí, API handler | DB host, log level, timeout | DB password, API token, private key |
| Nơi quản lý chính | Source repository | Config repository, config store hoặc platform config | Secret manager hoặc kho secret được bảo vệ |
| Review thay đổi | Code review, test, build | Review theo chính sách cấu hình | Review quyền và quy trình cấp/thu hồi |
| Phân phối | Checkout và build artifact | Inject hoặc mount khi triển khai/chạy | Cấp ngắn hạn hoặc inject vào workload cần dùng |
| Vòng đời | Commit, release, version | Version, rollout, validate, rollback | Tạo, cấp quyền, rotate, revoke, audit |
| Rủi ro chính | Lỗi logic, lỗ hổng mã | Sai giá trị, drift, cấu hình không tương thích | Rò rỉ hoặc lạm dụng quyền |
| Có nên đưa vào image ứng dụng? | Có, sau build | Chỉ khi là cấu hình mặc định không phụ thuộc môi trường | Không |

## 2. Vì sao phải tách code, config và secret?

### Giữ một artifact dùng được ở nhiều môi trường

Nếu URL database, tên bucket và endpoint staging được ghi trực tiếp vào mã, nhóm có thể phải build artifact riêng cho từng môi trường. Điều này tạo ra nhiều đầu ra khác nhau từ cùng một thay đổi, làm tăng khả năng triển khai nhầm và khiến việc xác minh artifact khó hơn.

Khi cấu hình được cung cấp lúc triển khai hoặc lúc ứng dụng khởi động, cùng một artifact có thể được promote qua dev, staging và production. Mỗi môi trường nhận bộ cấu hình phù hợp nhưng vẫn chạy cùng nội dung ứng dụng đã được kiểm tra.

### Tránh đưa bí mật vào lịch sử mã nguồn

Một mật khẩu được commit có thể tồn tại lâu dài trong Git history, fork, clone, cache và bản sao lưu. Xóa dòng mật khẩu khỏi commit mới không làm credential cũ tự mất khỏi lịch sử.

Nếu secret bị commit hoặc xuất hiện trong log, cần coi nó đã bị lộ: thu hồi hoặc rotate credential, kiểm tra phạm vi truy cập và xử lý lịch sử theo quy trình bảo mật của tổ chức. Việc xóa file khỏi repository chỉ là một phần của xử lý sự cố.

### Cho phép thay đổi vận hành có kiểm soát

Một số thay đổi không cần thay đổi logic ứng dụng: tăng timeout, đổi endpoint, giảm mức log hoặc tắt tạm một feature. Nếu các giá trị này là cấu hình runtime, nhóm có thể thay đổi theo quy trình được review, kiểm tra và audit mà không cần tạo một bản build mới.

Tuy nhiên, cấu hình vẫn có thể ảnh hưởng hành vi và tương thích. Không phải mọi thay đổi config đều an toàn để áp dụng trực tiếp; cần validate, rollout và khả năng quay lại giá trị trước đó.

### Giới hạn quyền truy cập

Nhà phát triển có thể cần đọc mã nguồn và cấu hình không nhạy cảm, nhưng không nhất thiết cần quyền đọc credential production. Người vận hành có thể thay đổi một số tham số production mà không có quyền sửa code. Job build có thể cần quyền đọc dependency nhưng không cần quyền deploy.

Tách dữ liệu giúp áp dụng quyền tối thiểu theo vai trò, môi trường và mục đích.

## 3. Cấu hình mặc định và cấu hình theo môi trường

Ứng dụng thường có một tập giá trị mặc định an toàn để chạy trong môi trường phát triển. Giá trị mặc định nên hỗ trợ khởi động và test, nhưng không nên chứa thông tin riêng của production.

Ví dụ cấu hình mặc định:

~~~yaml
app:
  name: order-service
  request-timeout: 3s
  retry:
    max-attempts: 2

logging:
  level:
    root: INFO
~~~

Các giá trị này có thể được quản lý cùng mã nguồn nếu chúng là mặc định chung và không chứa secret. Mỗi môi trường cung cấp các giá trị ghi đè khi cần:

| Thuộc tính | Development | Staging | Production |
|---|---|---|---|
| Log level | DEBUG | INFO | INFO hoặc WARN |
| Database endpoint | Local/dev DB | Staging DB | Production DB |
| Request timeout | Có thể thấp để test | Gần production | Theo SLO và đặc tính dịch vụ |
| Feature flag thử nghiệm | Có thể bật | Bật theo kế hoạch kiểm thử | Chỉ bật khi được phê duyệt |
| External API | Sandbox | Sandbox hoặc pre-production | Endpoint production |
| Credential | Tài khoản dev | Secret staging | Secret production riêng |

Không nên sao chép toàn bộ cấu hình production vào file được commit. Repository có thể lưu schema, tên thuộc tính, giá trị mặc định an toàn và ví dụ đã loại bỏ dữ liệu nhạy cảm. Giá trị thật được cung cấp bởi hệ thống quản lý cấu hình hoặc nền tảng triển khai.

### Tránh cấu hình mặc định nguy hiểm

Các giá trị mặc định như bật debug endpoint, cho phép anonymous access, dùng mật khẩu yếu hoặc tắt TLS verification có thể khiến môi trường thử nghiệm thuận tiện nhưng tạo rủi ro nếu vô tình được đưa lên production.

Nên thiết kế default theo nguyên tắc an toàn:

- Từ chối khởi động nếu thiếu cấu hình bắt buộc.
- Không tự chuyển sang credential mặc định khi secret không tồn tại.
- Tắt chức năng debug nguy hiểm theo mặc định.
- Yêu cầu TLS verification trong môi trường triển khai.
- Dùng quyền tối thiểu cho tài khoản dịch vụ.
- Chỉ bật feature có ảnh hưởng lớn khi đã được cấu hình rõ ràng.

## 4. Phân biệt cấu hình build-time và runtime

Không phải mọi cấu hình đều có thể thay đổi sau khi artifact được tạo. Cần phân biệt giá trị được sử dụng trong lúc build với giá trị được ứng dụng đọc khi chạy.

### Build-time configuration

Build-time config ảnh hưởng tới nội dung artifact hoặc cách compiler đóng gói sản phẩm.

Ví dụ:

- Phiên bản ứng dụng được sinh vào manifest.
- Cờ biên dịch hoặc target runtime.
- Feature được loại bỏ hoặc nhúng vào bundle trong lúc build.
- URL được compile trực tiếp vào ứng dụng frontend.
- Cấu hình tối ưu hóa hoặc profile của compiler.

Vì các giá trị này ảnh hưởng artifact, chúng cần được xem là đầu vào của build, được ghi nhận và kiểm soát để hỗ trợ tái lập. Không đưa secret vào build-time config. Giá trị được nhúng vào binary, JavaScript bundle hoặc image có thể được người nhận artifact trích xuất.

### Runtime configuration

Runtime config được cung cấp khi ứng dụng khởi động hoặc trong quá trình chạy, không cần build lại artifact.

Ví dụ:

- Database URL, connection pool size và timeout.
- Endpoint của service phụ trợ.
- Log level, sampling rate và giới hạn request.
- Feature flag có thể thay đổi theo chính sách.
- Tên queue, bucket hoặc namespace.

Runtime config hỗ trợ build once, promote many: build một lần, sau đó đưa cùng artifact qua nhiều môi trường bằng cách cung cấp cấu hình phù hợp.

### Ví dụ với frontend

Biến môi trường trong quá trình build frontend thường được thay thế vào bundle JavaScript. Những giá trị như API base URL có thể được xem là thông tin công khai sau khi build. Không đưa API secret, private key hoặc mật khẩu vào biến được nhúng vào frontend.

Nếu muốn cùng một bundle chạy ở nhiều môi trường, có thể phục vụ một file runtime configuration công khai khi ứng dụng khởi động trên trình duyệt. File đó chỉ chứa các giá trị được phép công khai, không chứa credential.

## 5. Quản lý cấu hình theo môi trường

Cấu hình có thể được lưu trong cùng repository, một repository riêng hoặc hệ thống config store. Lựa chọn phụ thuộc quy mô, quyền truy cập và cách vận hành.

### Cùng repository với ứng dụng

Phù hợp khi cấu hình nhỏ, ít môi trường và cùng nhóm chịu trách nhiệm. Có thể tổ chức:

~~~text
service/
  src/
  config/
    defaults.yaml
    development.yaml
    staging.yaml
    production.example.yaml
  deploy/
    manifests/
  .env.example
~~~

File production.example.yaml chỉ chứa cấu trúc và giá trị minh họa an toàn. Không lưu secret thật hoặc thông tin xác thực.

Ưu điểm là thay đổi code và config có thể được review cùng nhau. Hạn chế là quyền đọc repository có thể rộng hơn quyền đọc cấu hình production; cần phân quyền bổ sung hoặc tách dữ liệu nhạy cảm.

### Repository cấu hình riêng

Một repository cấu hình riêng có thể quản lý manifest theo môi trường, version, review và lịch sử thay đổi độc lập với ứng dụng.

Ví dụ:

~~~text
service-config/
  development/
    order-service.yaml
  staging/
    order-service.yaml
  production/
    order-service.yaml
~~~

Repository này không nên chứa secret plaintext. Nó có thể chứa tham chiếu tới secret manager, tên secret, version hoặc resource identity.

Tách repository giúp phân quyền vận hành rõ hơn và theo dõi cấu hình như một sản phẩm riêng. Cần ghi nhận config revision nào được triển khai cùng artifact revision nào.

### Config store hoặc control plane

Với hệ thống lớn, cấu hình có thể được quản lý bởi hệ thống trung tâm, nền tảng orchestration hoặc dịch vụ feature flag. Ứng dụng nhận cấu hình qua API, file mount, environment variable hoặc agent.

Cần xác định:

- Nguồn nào là nguồn dữ liệu chuẩn.
- Ai được phép thay đổi và phê duyệt.
- Ứng dụng cập nhật cấu hình theo cách nào.
- Cấu hình có version và audit history hay không.
- Điều gì xảy ra nếu config service không truy cập được.
- Cách rollback về phiên bản trước.
- Cách kiểm soát thay đổi đồng thời và drift.

Không nên để cùng một thuộc tính được chỉnh sửa tùy tiện ở nhiều nơi mà không có quy tắc precedence. Khi có nhiều nguồn, cần quy định rõ nguồn nào thắng và ghi nhận giá trị cuối cùng đã được ứng dụng sử dụng.

## 6. Quản lý secret bằng secret manager

Secret cần được lưu trong hệ thống chuyên dụng hoặc kho secret được nền tảng bảo vệ. Các ví dụ phổ biến gồm secret store của cloud, HashiCorp Vault, Kubernetes Secret kết hợp mã hóa và quyền truy cập phù hợp, hoặc secret manager tích hợp trong nền tảng CI/CD.

Một secret manager thường cung cấp một số khả năng:

- Mã hóa dữ liệu khi lưu và khi truyền.
- Kiểm soát quyền đọc theo identity hoặc policy.
- Audit ai đã truy cập secret và khi nào.
- Versioning và rotation.
- Cấp credential động hoặc ngắn hạn.
- Thu hồi quyền và credential khi có sự cố.

Không phải mọi hệ thống mang tên Secret đều tự động an toàn. Cần kiểm tra encryption at rest, access control, audit, backup, rotation và cách workload xác thực.

### Ưu tiên identity và credential ngắn hạn

Nếu nền tảng hỗ trợ workload identity hoặc federation, pipeline có thể dùng danh tính của job để nhận credential ngắn hạn thay vì lưu access key dài hạn trong repository.

Luồng tổng quát:

~~~text
CI job starts
     |
     v
Authenticate with workload identity
     |
     v
Secret manager checks identity and policy
     |
     v
Issue short-lived credential
     |
     v
Job uses credential for one task
     |
     v
Credential expires or is revoked
~~~

Credential ngắn hạn giảm thời gian một token bị lạm dụng nếu lộ. Tuy nhiên, quyền được cấp vẫn phải giới hạn theo repository, branch, environment và mục đích của job.

### Secret không phải cấu hình thông thường

Không đặt mật khẩu vào file application.yaml chỉ vì framework hỗ trợ đọc file đó. Nếu cần cấp secret qua file, nên mount từ secret manager hoặc volume được bảo vệ với quyền filesystem hạn chế, vòng đời rõ ràng và cơ chế thu hồi phù hợp.

Kubernetes Secret mặc định được biểu diễn bằng dữ liệu base64 trong manifest API; base64 chỉ là encoding, không phải mã hóa. Cần bật encryption at rest cho datastore theo cấu hình nền tảng, hạn chế RBAC, tránh commit secret manifest plaintext và cân nhắc tích hợp external secret store hoặc CSI driver.

## 7. Cách đưa cấu hình và secret vào ứng dụng

Có nhiều cơ chế phân phối; chọn theo nền tảng, độ nhạy dữ liệu và khả năng reload.

| Cơ chế | Phù hợp với | Lưu ý |
|---|---|---|
| Environment variables | Cấu hình nhỏ, đơn giản và một số secret được nền tảng inject | Có thể xuất hiện trong process inspection, crash dump hoặc log debug |
| File cấu hình được mount | Cấu hình nhiều trường hoặc ứng dụng cần file | Phải kiểm soát quyền file, ownership và vòng đời |
| Secret volume hoặc CSI | Secret cần được cung cấp dưới dạng file | Cần hiểu hành vi rotation và cập nhật file |
| Secret manager API | Workload lấy credential theo identity | Cần xử lý timeout, retry và quyền truy cập |
| Config service | Cấu hình có thể thay đổi động | Cần xác định cache, fallback, version và audit |
| Platform manifest | ConfigMap, task definition hoặc deployment spec | Cần tránh lưu secret plaintext trong repository |

### Environment variables

Environment variable tiện cho ứng dụng cloud-native vì dễ inject qua container runtime và hệ thống CI. Tên biến nên rõ ràng, thống nhất và có tài liệu.

Ví dụ:

~~~sh
APP_LOG_LEVEL=INFO
APP_REQUEST_TIMEOUT=3s
DATABASE_URL=jdbc:postgresql://orders-db.internal:5432/orders
FEATURE_NEW_CHECKOUT=false
~~~

Những biến trên là cấu hình minh họa, không chứa password. Secret có thể được nền tảng inject theo cơ chế bảo vệ, nhưng cần tránh in toàn bộ environment ra log hoặc cho tiến trình không tin cậy đọc được.

### File cấu hình

File cấu hình phù hợp với cấu trúc nhiều trường, danh sách hoặc object lồng nhau. Có thể mount file theo môi trường hoặc đọc từ thư mục cấu hình được khai báo.

Cần xác định file nào là mặc định, file nào là override, thứ tự nạp và hành vi khi file không tồn tại. Không để ứng dụng âm thầm dùng cấu hình production mặc định khi file bắt buộc bị thiếu.

### Cấu hình qua API

Một config service có thể cung cấp feature flag hoặc tham số runtime. Ứng dụng cần kiểm soát:

- Xác thực và quyền đọc.
- Version của cấu hình.
- Cache và thời gian hiệu lực.
- Xử lý khi service mất kết nối.
- Cập nhật nguyên tử để tránh trạng thái nửa cũ nửa mới.
- Cách quay lại phiên bản trước nếu cấu hình mới gây lỗi.

Không phải mọi cấu hình đều phù hợp để thay đổi động. Các thuộc tính ảnh hưởng kết nối database hoặc cấu trúc tài nguyên có thể cần restart hoặc rollout có kiểm soát.

## 8. Quy tắc đặt tên, cấu trúc và precedence

Cấu hình cần dễ tìm và dễ hiểu. Tên nên thể hiện mục đích, phạm vi và đơn vị đo.

Ví dụ tốt:

- DATABASE_CONNECTION_TIMEOUT_SECONDS
- HTTP_MAX_CONNECTIONS
- APP_LOG_LEVEL
- FEATURE_CHECKOUT_V2_ENABLED

Tên mơ hồ như TIMEOUT, VALUE hoặc ENABLED dễ bị dùng sai. Với giá trị số, ghi rõ đơn vị hoặc quy ước đơn vị trong schema và tài liệu.

### Xác định thứ tự ưu tiên

Một ứng dụng có thể đọc cấu hình từ nhiều nguồn:

1. Giá trị mặc định trong ứng dụng.
2. File cấu hình chung.
3. File cấu hình theo profile/môi trường.
4. Environment variables.
5. Tham số command line hoặc override do nền tảng cấp.
6. Config service hoặc secret store theo cơ chế tích hợp.

Thứ tự thực tế phụ thuộc framework. Ví dụ Spring Boot có quy tắc property source precedence riêng; không nên giả định danh sách trên tự động đúng với mọi ứng dụng.

Hãy công bố precedence của ứng dụng và tránh để cùng một giá trị được đặt ở nhiều nơi mà không ai biết nguồn nào thắng. Khi cần điều tra, nên có khả năng xem tên nguồn và version cấu hình mà không in secret.

### Không nhầm cấu hình với tham số dòng lệnh

Tham số dòng lệnh có thể override config trong một lần chạy. Nếu pipeline hoặc người vận hành dùng override, cần ghi lại tham số không nhạy cảm và bảo đảm chúng không vô tình lưu secret trong process list hoặc log.

## 9. Validate cấu hình trước khi ứng dụng phục vụ traffic

Cấu hình sai có thể khiến ứng dụng khởi động nhưng chỉ lỗi khi có request. Nên xác thực ngay lúc startup hoặc trước khi rollout.

Các nhóm kiểm tra:

- **Kiểu dữ liệu:** số, boolean, duration, URL, danh sách hoặc enum.
- **Giới hạn:** timeout lớn hơn 0, pool size trong phạm vi hợp lý.
- **Bắt buộc:** endpoint hoặc tên resource cần có.
- **Tương thích:** phiên bản schema và API phù hợp với ứng dụng.
- **Quan hệ giữa các trường:** min không lớn hơn max; retry delay phù hợp timeout.
- **An toàn:** TLS verification bật; debug endpoint không mở ngoài ý muốn.
- **Kết nối:** kiểm tra endpoint hoặc credential theo cách không làm lộ secret.

Ví dụ, nếu APP_REQUEST_TIMEOUT nhận giá trị "abc", ứng dụng nên báo lỗi cấu hình rõ ràng và dừng khởi động thay vì tự chuyển sang một giá trị không được dự kiến.

### Fail fast có kiểm soát

Với cấu hình bắt buộc, fail fast giúp phát hiện lỗi trước khi nhận traffic. Thông báo lỗi nên nêu tên thuộc tính và quy tắc vi phạm, nhưng không in giá trị secret.

Không phải mọi lỗi cấu hình đều cần dừng toàn bộ ứng dụng. Một feature tùy chọn có thể tắt an toàn khi thiếu cấu hình; một endpoint phụ trợ không thiết yếu có thể làm chức năng tương ứng ở trạng thái degraded. Cần xác định hành vi theo mức độ quan trọng của tính năng.

## 10. Cấu hình trong pipeline CI/CD

Pipeline cũng có code, config và secret. File workflow là mã điều khiển tự động hóa; giá trị như JDK version hoặc test profile là cấu hình; token publish và credential deploy là secret.

Ví dụ workflow có cấu hình không nhạy cảm:

~~~yaml
jobs:
  verify:
    runs-on: ubuntu-24.04
    env:
      APP_LOG_LEVEL: INFO
      TEST_PROFILE: ci
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon check
~~~

Các secret cần thiết cho một job có thể được lấy từ kho secret của nền tảng hoặc secret manager theo identity. Chỉ job thực hiện thao tác cần secret mới được cấp quyền đọc; job lint hoặc unit test không nên nhận credential production nếu không có lý do cụ thể.

### Phân tách quyền giữa các job

Một pipeline có thể chia thành:

| Job | Cấu hình cần | Secret/quyền cần |
|---|---|---|
| Lint và unit test | Toolchain, test profile | Thường không cần secret production |
| Integration test | Endpoint và thông tin service thử nghiệm | Credential riêng của môi trường test nếu cần |
| Build/package | Version, build flags | Quyền đọc dependency; không cần deploy credential |
| Publish artifact | Registry endpoint, repository | Quyền ghi đúng registry |
| Deploy staging | Target, namespace, rollout settings | Credential staging |
| Deploy production | Target production, release policy | Identity production riêng và approval |

Việc tách job giúp giảm phạm vi ảnh hưởng nếu một bước bị xâm nhập. Các job vẫn cần bảo vệ artifact và kết quả kiểm tra giữa các bước.

### Không để secret đi qua artifact hoặc cache

Không upload file .env chứa credential, thư mục home của runner, token file hoặc log debug như artifact dùng chung. Không cache thư mục chứa secret hoặc file cấu hình runtime nhạy cảm.

Artifact cần được tạo từ đầu ra có chủ đích, không phải toàn bộ workspace. Trước khi upload, xác định chính xác đường dẫn và kiểm tra nội dung được đưa vào.

## 11. Không nhúng secret vào image hoặc build argument

Dockerfile và image build thường bị dùng nhầm để truyền credential.

Ví dụ không an toàn:

~~~dockerfile
ARG DB_PASSWORD
ENV DB_PASSWORD=$DB_PASSWORD
~~~

Giá trị có thể xuất hiện trong metadata, layer history, build log hoặc được lưu trong image. Không nên dùng ARG hoặc ENV như kho lưu secret.

Nếu build cần credential để tải dependency riêng, hãy dùng cơ chế secret mount của builder hoặc credential ngắn hạn được cấp riêng cho bước đó. Secret mount cần được sử dụng trong đúng bước, không copy vào layer và không ghi ra log.

Runtime secret nên được cấp khi container được chạy thông qua secret manager, orchestrator hoặc workload identity. Image chỉ chứa ứng dụng, runtime và cấu hình mặc định không nhạy cảm.

## 12. Theo dõi version cấu hình và config drift

Cấu hình cũng cần version và lịch sử thay đổi. Nếu ứng dụng version 2.4.1 đang chạy với config revision C17, deployment record nên lưu cả hai định danh.

Config drift xảy ra khi trạng thái thực tế khác với cấu hình mong muốn đã được khai báo. Ví dụ:

- Một người sửa biến môi trường trực tiếp trên máy production.
- Một giá trị được đổi qua giao diện console nhưng không cập nhật repository cấu hình.
- Hai replica chạy với hai config revision khác nhau.
- Một secret được rotate nhưng workload cũ chưa nhận credential mới.
- ConfigMap hoặc deployment manifest không còn khớp với Git.

Để kiểm soát drift:

- Quản lý cấu hình mong muốn trong nguồn có version.
- Ghi audit log cho thay đổi trực tiếp.
- Định kỳ so sánh trạng thái thực tế với trạng thái mong muốn.
- Dùng GitOps hoặc cơ chế reconciliation nếu phù hợp.
- Gắn config revision với release/deployment record.
- Cảnh báo khi các instance chạy cấu hình không đồng nhất.

Không phải mọi drift đều cần tự động ghi đè. Một thay đổi khẩn cấp có thể cần giữ tạm thời; cần ghi nhận, đánh giá và đưa trạng thái về nguồn chuẩn theo quy trình.

## 13. Thay đổi cấu hình, rollout và rollback

Một thay đổi cấu hình có thể tác động nhanh tới toàn bộ instance nếu được áp dụng đồng thời. Nên triển khai config change như một thay đổi phát hành có kiểm soát.

Quy trình tham khảo:

1. Tạo thay đổi cấu hình trong nguồn được quản lý.
2. Validate schema, kiểu dữ liệu, giới hạn và quan hệ giữa các trường.
3. Review tác động, đặc biệt với timeout, pool, feature flag và quyền.
4. Thử trên development hoặc staging.
5. Rollout theo nhóm instance hoặc canary nếu nền tảng hỗ trợ.
6. Theo dõi error rate, latency, resource usage và hành vi nghiệp vụ.
7. Mở rộng rollout khi tín hiệu đạt.
8. Lưu config revision và kết quả xác minh.

### Tương thích giữa code và config

Ứng dụng mới có thể yêu cầu một thuộc tính cấu hình mà phiên bản cũ không hiểu. Ngược lại, xóa thuộc tính có thể làm phiên bản đang chạy lỗi.

Khi triển khai rolling update, nhiều phiên bản ứng dụng có thể cùng tồn tại. Cần thiết kế schema cấu hình tương thích trong khoảng chuyển tiếp:

- Thêm thuộc tính mới với default an toàn nếu có thể.
- Triển khai ứng dụng có khả năng đọc cả cấu hình cũ và mới.
- Chuyển cấu hình sau khi các instance đã hỗ trợ.
- Chỉ xóa thuộc tính cũ khi không còn phiên bản nào phụ thuộc.

### Rollback cấu hình

Nếu config mới gây lỗi, cần biết config revision trước đó và cách khôi phục. Rollback có thể thực hiện độc lập với code nếu phiên bản ứng dụng hiện tại vẫn tương thích với cấu hình cũ.

Nếu thay đổi config đi kèm schema hoặc hành vi mới, có thể cần rollback cả ứng dụng hoặc thực hiện một bước chuyển tiếp. Không giả định mọi config đều có thể quay lại ngay lập tức, đặc biệt với migration, credential rotation hoặc thay đổi dữ liệu.

## 14. Ví dụ tổ chức cấu hình cho ứng dụng Java

Với Spring Boot, có thể lưu cấu hình không nhạy cảm mặc định trong application.yaml:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  datasource:
    url: jdbc:postgresql://localhost:5432/orders

app:
  request-timeout: 3s
  retry:
    max-attempts: 2

logging:
  level:
    root: INFO
~~~

Môi trường triển khai cung cấp giá trị ghi đè qua profile hoặc environment variables. Ví dụ, trong staging:

~~~sh
SPRING_PROFILES_ACTIVE=staging
SPRING_DATASOURCE_URL=jdbc:postgresql://staging-db.internal:5432/orders
APP_REQUEST_TIMEOUT=3s
APP_RETRY_MAX_ATTEMPTS=2
~~~

Credential database được lấy từ secret manager hoặc cơ chế secret injection của nền tảng. Không commit username/password production vào application.yaml, profile file hoặc Docker image.

Một số lưu ý:

- Profile giúp tổ chức cấu hình theo môi trường, nhưng file profile vẫn là nội dung version control và không nên chứa secret thật.
- Spring Boot hỗ trợ relaxed binding từ environment variable sang property; cần kiểm tra quy tắc tên cho thuộc tính lồng nhau và kiểu dữ liệu.
- Có thể dùng validation annotation hoặc cơ chế cấu hình có kiểu để phát hiện giá trị không hợp lệ khi startup.
- Không log toàn bộ configuration object vì nó có thể chứa secret hoặc dữ liệu nhạy cảm.
- Nếu cần xem cấu hình đang hiệu lực, chỉ công bố các thuộc tính đã được cho phép và che giá trị nhạy cảm.

## 15. Những sai lầm thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Hard-code endpoint production trong source | Phải build riêng hoặc sửa code khi đổi môi trường | Đưa giá trị thành runtime config |
| Commit password vào Git | Secret tồn tại trong history và bản sao | Dùng secret manager; rotate nếu đã lộ |
| Lưu secret trong file profile | File dễ bị copy vào artifact hoặc log | Chỉ lưu tham chiếu và inject secret lúc chạy |
| Dùng Docker ARG/ENV để truyền password build | Secret có thể lọt vào layer hoặc metadata | Dùng secret mount và credential ngắn hạn |
| Dùng cùng credential cho dev/staging/prod | Sự cố ở một môi trường ảnh hưởng môi trường khác | Tách identity và secret theo môi trường |
| In toàn bộ environment để debug | Log có thể chứa token và mật khẩu | Chỉ log tên cấu hình được phép, che giá trị |
| Dùng default credential khi secret thiếu | Ứng dụng có thể khởi động với quyền không an toàn | Fail fast hoặc tắt chức năng theo chính sách |
| Đặt cùng thuộc tính ở nhiều nguồn không có precedence | Khó xác định giá trị thực tế | Tài liệu hóa và kiểm tra nguồn thắng |
| Sửa config trực tiếp trên production | Tạo config drift, khó audit và rollback | Quản lý thay đổi qua nguồn có version |
| Đưa secret vào cache/artifact | Nhiều job hoặc người dùng có thể đọc được | Giới hạn đường dẫn upload/cache và quyền truy cập |
| Thay đổi config đồng loạt không kiểm chứng | Sự cố lan tới toàn bộ instance | Validate, canary và theo dõi rollout |
| Cho mọi job quyền đọc secret production | Tăng bề mặt ảnh hưởng khi pipeline bị xâm nhập | Tách job và cấp quyền tối thiểu |

## 16. Checklist phân tách code, config và secret

### Mã ứng dụng

- [ ] Logic và hành vi được quản lý trong source repository.
- [ ] Thay đổi đi qua commit, review và test.
- [ ] Artifact có version hoặc digest gắn với commit.
- [ ] Không chứa credential, private key hoặc token.
- [ ] Không nhúng giá trị môi trường riêng nếu có thể cung cấp lúc runtime.

### Cấu hình

- [ ] Mỗi thuộc tính có tên, kiểu, đơn vị và ý nghĩa rõ.
- [ ] Có default an toàn và quy tắc cho giá trị bắt buộc.
- [ ] Cấu hình theo môi trường được version và review.
- [ ] Build-time và runtime config được phân biệt.
- [ ] Thứ tự precedence được tài liệu hóa.
- [ ] Cấu hình được validate trước khi nhận traffic.
- [ ] Config revision được gắn với deployment record.
- [ ] Có cách phát hiện drift và rollback.

### Secret

- [ ] Secret được lưu trong secret manager hoặc kho được bảo vệ.
- [ ] Quyền truy cập được giới hạn theo identity, job và environment.
- [ ] Ưu tiên credential ngắn hạn hoặc workload identity khi hỗ trợ.
- [ ] Secret không nằm trong Git, image, artifact, cache hoặc log.
- [ ] Có quy trình rotation, revoke và xử lý khi lộ.
- [ ] Mỗi môi trường dùng credential riêng.
- [ ] Secret injection và file permission được kiểm soát.
- [ ] Audit log ghi nhận việc truy cập và thay đổi.

### Pipeline và triển khai

- [ ] Job chỉ nhận cấu hình và secret thực sự cần.
- [ ] Job test không có quyền deploy production ngoài nhu cầu rõ ràng.
- [ ] Artifact được build một lần và promote qua môi trường.
- [ ] Runtime config được cấp tại môi trường đích.
- [ ] Config thay đổi được validate, review và rollout có kiểm soát.
- [ ] Deployment record lưu artifact version và config revision.
- [ ] Có kiểm tra sau triển khai và kế hoạch rollback.

## Kết luận

Mã ứng dụng định nghĩa hành vi, cấu hình điều chỉnh cách hành vi đó hoạt động trong từng môi trường, còn secret bảo vệ danh tính và quyền truy cập. Tách ba nhóm giúp duy trì một artifact nhất quán qua nhiều môi trường, thay đổi cấu hình có kiểm soát và giới hạn phạm vi lộ credential. Trong CI/CD, hãy version hóa code và cấu hình không nhạy cảm, cấp runtime config tại môi trường đích, quản lý secret bằng identity và secret manager, rồi ghi nhận cả artifact revision lẫn config revision trong mỗi lần triển khai.


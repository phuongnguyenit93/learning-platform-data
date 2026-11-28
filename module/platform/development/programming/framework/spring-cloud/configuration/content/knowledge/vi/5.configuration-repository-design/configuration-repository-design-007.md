# Giữ bí mật, tệp nhị phân và dữ liệu lớn ngoài kho cấu hình

Kho cấu hình của Spring Cloud Config nên chứa những giá trị văn bản nhỏ, có cấu trúc và cần được quản lý theo ứng dụng, profile hoặc phiên bản. Mật khẩu, token, private key, chứng thư nhạy cảm, tệp nhị phân và dữ liệu lớn có vòng đời, quyền truy cập và cách phân phối khác với các thuộc tính thông thường. Đưa tất cả vào Git khiến việc bảo vệ, luân chuyển, tải xuống và kiểm soát kích thước repository trở nên khó khăn.

Thiết kế tốt tách **cấu hình mô tả cách ứng dụng hoạt động** khỏi **dữ liệu hoặc bí mật mà ứng dụng cần sử dụng**. Spring Cloud Config có thể lưu tham chiếu, tên secret hoặc phiên bản artifact; ứng dụng lấy nội dung thật từ secret manager, object storage, volume hoặc hệ thống phân phối artifact bằng danh tính và quyền truy cập phù hợp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt cấu hình thông thường, bí mật, tệp nhị phân và dữ liệu lớn.
- Giải thích vì sao không đưa bí mật hoặc payload lớn vào kho Git cấu hình.
- Chọn nơi lưu trữ phù hợp cho secret, chứng thư, keystore, tệp và dataset.
- Thiết kế cách tham chiếu tài nguyên bên ngoài từ cấu hình Spring Boot.
- Kiểm soát quyền truy cập, luân chuyển, phiên bản, tính toàn vẹn và khả năng sẵn sàng của dữ liệu ngoài.
- Xử lý đúng khi bí mật đã từng bị commit vào Git.

## Phân loại trước khi quyết định nơi lưu

Không phải mọi giá trị cấu hình đều có cùng mức độ nhạy cảm hoặc cách sử dụng. Hãy phân loại theo nội dung, kích thước, tần suất thay đổi và yêu cầu bảo mật:

| Loại dữ liệu | Ví dụ | Nơi lưu phù hợp |
|---|---|---|
| Cấu hình văn bản thông thường | URL dịch vụ, timeout, số worker, feature flag | Git repository được Config Server đọc |
| Bí mật và thông tin xác thực | Mật khẩu DB, API token, OAuth client secret, private key | Secret manager hoặc hệ thống quản lý danh tính và bí mật |
| Tệp nhị phân nhạy cảm | Keystore PKCS12, private key, chứng thư có khóa riêng | Secret manager, kho chứng thư hoặc volume được bảo vệ |
| Tệp nhị phân không nhạy cảm | Mô hình ML, bản đồ, template lớn, tệp media | Object storage hoặc artifact repository |
| Dữ liệu lớn, thay đổi thường xuyên | Dataset, danh mục đồng bộ, dữ liệu tham chiếu | Database, data lake, object storage hoặc hệ thống dữ liệu chuyên dụng |

Một tệp nhỏ vẫn có thể là bí mật; một tệp văn bản lớn vẫn có thể là dữ liệu. Không quyết định nơi lưu chỉ dựa trên phần mở rộng hoặc số byte.

## Vì sao không đưa bí mật vào Git?

Git được thiết kế để lưu lịch sử thay đổi. Khi một token hoặc mật khẩu được commit, xóa dòng đó trong commit mới không xóa các bản cũ. Bí mật có thể còn trong lịch sử nhánh, tag, bản clone, fork, cache CI hoặc bản sao lưu. Người có quyền đọc repository cũng có thể đọc nội dung bí mật đã commit.

Mã hóa ổ đĩa hoặc HTTPS bảo vệ dữ liệu ở một số chặng, nhưng không giải quyết vấn đề quyền đọc lịch sử Git. Mã hóa một secret rồi lưu ciphertext trong Git có thể giảm nguy cơ lộ nội dung trực tiếp, nhưng vẫn cần quản lý khóa giải mã, quyền truy cập và vòng đời secret ở nơi khác.

Các rủi ro chính gồm:

- **Phạm vi lộ rộng:** quyền đọc repository thường được cấp cho nhiều người và hệ thống hơn quyền sử dụng một secret cụ thể.
- **Khó thu hồi:** commit cũ và bản clone vẫn có thể giữ giá trị đã lộ.
- **Luân chuyển phức tạp:** đổi mật khẩu hoặc token phải đồng bộ với nhiều bản cấu hình và instance.
- **Thiếu phân quyền chi tiết:** một ứng dụng có thể vô tình đọc được bí mật của ứng dụng hoặc môi trường khác.
- **Rò rỉ qua log và giao diện quản trị:** giá trị bí mật có thể xuất hiện trong exception, log, endpoint quản lý hoặc bản dump nếu không kiểm soát.

Vì vậy, repository cấu hình nên chứa tên tham chiếu và các tham số không nhạy cảm. Secret manager giữ giá trị thật và quyết định ai được phép đọc nó.

## Lưu bí mật trong Secret Manager

Secret manager chuyên trách lưu trữ và phân phối dữ liệu nhạy cảm. Một số lựa chọn thường gặp là HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Google Secret Manager hoặc dịch vụ quản lý secret của nền tảng triển khai. Với Kubernetes, Secret có thể được mount hoặc đưa vào môi trường chạy; cần bật mã hóa dữ liệu at rest trong etcd, giới hạn RBAC và kiểm soát quyền truy cập node.

Một secret manager phù hợp thường hỗ trợ:

- Xác thực ứng dụng bằng danh tính workload, service account, certificate hoặc cơ chế tương đương.
- Phân quyền theo secret path, ứng dụng, môi trường và thao tác đọc/ghi.
- Audit việc truy cập, tạo phiên bản và thay đổi quyền.
- Luân chuyển hoặc tạo phiên bản secret mới, có thể kết hợp thời hạn và thu hồi.
- Mã hóa khi lưu trữ và truyền tải, quản lý khóa tách biệt với repository cấu hình.

Không nên cấp một token quản trị chung cho tất cả Config Client. Mỗi ứng dụng hoặc nhóm workload nên có danh tính riêng và chỉ đọc đúng secret cần thiết. Ví dụ `order-service` ở môi trường `prod` không nên dùng credential cho phép đọc toàn bộ secret của mọi dịch vụ trong tổ chức.

### Cách Config Client nhận secret

Có nhiều cách đưa secret vào ứng dụng; chọn cách phù hợp với nền tảng và mô hình vận hành:

1. **Inject qua biến môi trường:** nền tảng hoặc agent lấy secret rồi đưa vào process environment. Spring Boot đọc giá trị như một property thông thường.
2. **Mount thành tệp:** secret manager hoặc orchestrator mount tệp có quyền truy cập hạn chế vào container/host. Ứng dụng đọc đường dẫn được cấu hình.
3. **Đọc bằng SDK hoặc client chuyên dụng:** ứng dụng xác thực bằng workload identity và truy vấn secret manager khi cần.
4. **Dùng Config Server với backend secret:** Config Server tích hợp một backend như Vault để phân phối các giá trị được phép theo context ứng dụng/profile.

Ví dụ Config Server lưu URL và tham chiếu biến môi trường, còn secret thật được nền tảng triển khai inject vào `order-service`:

```yaml
# order-service-prod.yml trong config repository
payment:
  gateway:
    base-url: https://payments.example.com
    api-key: ${PAYMENT_GATEWAY_API_KEY}
    connect-timeout: 3s
```

Ứng dụng Spring Boot có thể bind thuộc tính `payment.gateway.api-key` từ property source sau khi placeholder được phân giải theo cấu hình môi trường. Hệ thống triển khai chịu trách nhiệm cấp `PAYMENT_GATEWAY_API_KEY` từ secret manager cho đúng workload. Không đặt giá trị thật của biến này trong file Git, Docker image hoặc file `.env` được commit.

Một phương án khác là lưu tên secret thay vì placeholder:

```yaml
payment:
  gateway:
    base-url: https://payments.example.com
    credential-secret-name: prod/order-service/payment-gateway
```

Ứng dụng dùng SDK hoặc integration phù hợp để đọc secret có tên đó. `credential-secret-name` chỉ là tham chiếu minh họa; cú pháp đường dẫn và cách đọc thực tế phụ thuộc secret manager được chọn.

### Tích hợp Vault hoặc backend bí mật

Spring Cloud Config Server có thể dùng backend Vault trong những kiến trúc phù hợp. Khi đó, server cần thông tin xác thực đến Vault, chính sách truy cập giới hạn và cách ánh xạ context theo ứng dụng/profile. Bí mật xác thực của chính Config Server cũng phải được cấp từ một nguồn an toàn, không lưu trong cùng repository mà server phục vụ.

Trước khi chọn để Config Server đọc secret thay cho từng client, cần quyết định ranh giới tin cậy: server sẽ đọc secret thay mặt client hay client tự xác thực với secret manager. Nếu server có quyền đọc mọi bí mật, server trở thành thành phần có đặc quyền cao và cần bảo vệ, giám sát, phân quyền cùng quy trình xoay credential tương ứng.

### Mã hóa giá trị trong Spring Cloud Config

Spring Cloud Config hỗ trợ cơ chế mã hóa/giải mã giá trị cấu hình, ví dụ giá trị được đánh dấu bằng tiền tố `{cipher}`. Cách này có thể hữu ích khi cần lưu ciphertext trong repository và để Config Server giải mã khi phục vụ client. Khóa mã hóa phải được lưu và bảo vệ ngoài Git, có quy trình thay thế và giới hạn người có quyền sử dụng.

Ví dụ minh họa một thuộc tính đã mã hóa trong kho cấu hình:

```yaml
payment:
  gateway:
    api-key: "{cipher}AQB...encrypted-value..."
```

Chuỗi trên chỉ là ciphertext minh họa, không phải secret có thể sử dụng. Nếu bật endpoint mã hóa/giải mã của Config Server, cần giới hạn truy cập bằng xác thực, phân quyền và mạng tin cậy; endpoint giải mã đặc biệt nhạy cảm. Có thể tắt các endpoint này nếu quy trình không cần dùng.

Mã hóa trong Config Server không thay thế hoàn toàn secret manager. Nó không tự giải quyết việc cấp quyền theo từng secret, luân chuyển token ở hệ thống đích, thu hồi phiên bản bị lộ hoặc quản lý vòng đời chứng thư. Với bí mật quan trọng, secret manager thường là nơi lưu giữ chính; cơ chế `{cipher}` là một lựa chọn bổ sung tùy yêu cầu.

## Đưa tệp nhị phân ra khỏi kho cấu hình

Tệp nhị phân không được xử lý như các thuộc tính YAML hoặc properties thông thường. Ví dụ gồm keystore, truststore, chứng thư, ảnh, mô hình máy học, file nén, tệp template lớn và gói dữ liệu. Đưa chúng vào repository cấu hình làm tăng kích thước clone, gây nhiễu lịch sử và khó kiểm soát quyền tải xuống.

Chọn nơi lưu theo mục đích:

| Tài nguyên | Nơi lưu phù hợp | Cách ứng dụng sử dụng |
|---|---|---|
| Keystore chứa private key | Secret manager hoặc secret volume | Mount tệp vào runtime, lấy mật khẩu riêng từ secret manager |
| Truststore/chứng thư công khai | Certificate manager hoặc artifact repository có kiểm soát | Phân phối theo phiên bản và cập nhật truststore |
| Mô hình hoặc gói tài nguyên lớn | Object storage hoặc artifact repository | Tải đúng phiên bản khi deploy hoặc khi khởi động |
| Tệp dữ liệu nghiệp vụ | Database, data lake hoặc object storage | Đọc qua API/SDK, không bind toàn bộ nội dung vào `Environment` |

Ví dụ cấu hình chỉ lưu vị trí và phiên bản artifact:

```yaml
recommendation:
  model:
    object-key: models/recommendation/model-2026-11-15.bin
    version: 7
    sha256: 9f2c...example-digest...a81d
```

Ứng dụng dùng SDK object storage hoặc một dịch vụ nội bộ để tải artifact theo `object-key` và `version`, sau đó kiểm tra checksum trước khi sử dụng. Ví dụ digest là chuỗi minh họa; trong triển khai thực tế phải lưu giá trị SHA-256 đầy đủ do pipeline phát hành tạo ra. Không đặt access key của object storage trong YAML; ứng dụng nên dùng workload identity hoặc credential ngắn hạn.

Với keystore, cấu hình có thể chứa đường dẫn mount và tên biến môi trường chứa mật khẩu:

```yaml
server:
  ssl:
    key-store: file:/var/run/app-secrets/server-keystore.p12
    key-store-password: ${SERVER_KEYSTORE_PASSWORD}
    key-store-type: PKCS12
```

Tệp `server-keystore.p12` được mount từ nguồn được bảo vệ, còn mật khẩu được inject riêng. Nếu keystore chứa private key, coi toàn bộ tệp là bí mật và giới hạn quyền đọc, bản sao, backup và quyền truy cập node.

## Đưa dữ liệu lớn ra khỏi kho cấu hình

Spring Cloud Config phục vụ property source, không phải nền tảng truyền tải dataset. Các dữ liệu lớn hoặc thay đổi thường xuyên nên được đặt trong hệ thống chuyên dụng để có thể phân trang, streaming, cache, kiểm soát vòng đời và tối ưu chi phí.

Ví dụ, danh sách sản phẩm hàng triệu dòng nên nằm trong database hoặc object storage; Config chỉ lưu URL dịch vụ, tên bucket, prefix hoặc mã phiên bản dataset. Ứng dụng truy cập dữ liệu bằng API/SDK và chỉ tải phần cần dùng.

Đối với dữ liệu ngoài, hãy quản lý ít nhất các thông tin sau:

- **Định danh ổn định:** bucket/key, artifact name, dataset ID hoặc API endpoint.
- **Phiên bản bất biến:** version ID, tag phát hành hoặc snapshot ID; tránh tham chiếu một alias luôn trỏ đến nội dung thay đổi không kiểm soát.
- **Tính toàn vẹn:** checksum hoặc chữ ký để phát hiện nội dung sai lệch hay bị thay thế.
- **Quyền truy cập:** workload identity và quyền tối thiểu cho đúng tài nguyên.
- **Khả năng sẵn sàng:** timeout, retry có giới hạn, cache và xử lý khi kho dữ liệu không truy cập được.
- **Vòng đời:** retention, backup, xóa, lưu trữ và quy trình rollback.

Nếu dùng Git LFS cho một số tệp nhị phân, cần hiểu rằng LFS chỉ thay đổi cách lưu và tải nội dung lớn trong quy trình Git. Nó không tự cung cấp secret manager, phân quyền theo ứng dụng, phân phối runtime, chính sách retention dữ liệu hay khả năng đọc theo API. Chỉ dùng khi tài nguyên thực sự thuộc vòng đời mã nguồn và nhóm chấp nhận mô hình vận hành đó; không biến kho cấu hình thành nơi lưu mọi file lớn.

## Thiết kế repository cấu hình gọn và rõ

Một repository cấu hình có thể giữ các giá trị mô tả, tham chiếu và quy tắc theo môi trường:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── order-service.yml
├── order-service-prod.yml
└── inventory-service-prod.yml
```

Ví dụ `order-service-prod.yml` có thể chứa URL dịch vụ, timeout, tên secret và phiên bản model:

```yaml
payment:
  gateway:
    base-url: https://payments.example.com
    api-key: ${PAYMENT_GATEWAY_API_KEY}

recommendation:
  model:
    object-key: models/recommendation/model-2026-11-15.bin
    version: 7
```

Git giữ lịch sử các thay đổi văn bản. Secret manager giữ giá trị bí mật. Object storage giữ tệp và dữ liệu lớn. Mỗi nơi có quyền truy cập, audit, backup và quy trình phát hành riêng. Repository cấu hình liên kết các thành phần bằng tham chiếu có phiên bản.

Không nên đưa URL tải xuống có chữ ký còn hiệu lực dài hạn hoặc credential nhúng trong URL vào Git. Nếu cần URL có chữ ký, tạo nó ngắn hạn tại runtime sau khi ứng dụng xác thực. Thông tin tham chiếu trong cấu hình không được vô tình trở thành thông tin xác thực.

## Quản lý quyền, luân chuyển và audit

Tách secret theo ứng dụng và môi trường. Cấp quyền đọc theo danh tính workload; tránh credential dùng chung giữa `dev`, `test` và `prod`. Người phát triển có thể được quyền đọc secret thử nghiệm, trong khi quyền production chỉ cấp cho workload và nhóm vận hành có trách nhiệm.

Luân chuyển secret nên có kế hoạch để tránh gián đoạn:

1. Tạo phiên bản credential mới trong secret manager hoặc hệ thống đích.
2. Cấp quyền cho ứng dụng sử dụng phiên bản mới; nếu hệ thống đích hỗ trợ, duy trì giai đoạn chấp nhận cả hai credential.
3. Cập nhật tham chiếu hoặc để ứng dụng lấy phiên bản mới theo chính sách.
4. Refresh/restart theo cách phù hợp và xác nhận các instance đã sử dụng credential mới.
5. Thu hồi credential cũ sau khi xác nhận không còn workload sử dụng.

Ghi audit việc đọc và thay đổi secret, nhưng không ghi nội dung secret vào audit log. Log nên chứa danh tính workload, tên secret, thời điểm, hành động và kết quả. Giới hạn việc hiển thị thuộc tính nhạy cảm qua Actuator, exception, tracing và diagnostic dump.

Đối với binary hoặc dataset, áp dụng nguyên tắc tương tự: chỉ workload cần thiết được tải tài nguyên, ghi nhận version/checksum được sử dụng và giữ lại phiên bản trước trong thời gian rollback cho phép.

## Nếu bí mật đã bị commit vào Git

Xóa dòng bí mật khỏi file ở commit mới là chưa đủ. Hãy xem bí mật đó đã bị lộ và xử lý theo thứ tự:

1. **Thu hồi hoặc rotate ngay:** đổi password, token, certificate hoặc key ở hệ thống đích. Không chờ viết lại lịch sử Git mới thu hồi.
2. **Xác định phạm vi:** kiểm tra repository, nhánh, tag, pull request, fork, log CI, artifact và bản clone có thể đã nhận giá trị.
3. **Làm sạch nơi lưu nếu cần:** phối hợp với quản trị repository để viết lại lịch sử và hướng dẫn đồng bộ lại clone; hiểu rằng việc này không đảm bảo xóa mọi bản sao.
4. **Đưa secret vào đúng nơi:** chuyển sang secret manager hoặc nguồn cấp runtime, cập nhật quyền và cấu hình tham chiếu.
5. **Kiểm tra nguyên nhân:** rà soát quyền truy cập, pipeline, pre-commit hook và secret scanning để ngăn lặp lại.

Không dựa vào việc xóa file hoặc force-push như bằng chứng rằng secret đã an toàn. Nếu credential còn hiệu lực, người đã có bản clone hoặc bản sao lưu vẫn có thể sử dụng nó.

## Kiểm tra tự động trong quy trình thay đổi

Pipeline cho repository cấu hình nên có các bước phù hợp với rủi ro:

- Secret scanning trên thay đổi mới và, khi có thể, trên lịch sử repository.
- Kiểm tra cú pháp YAML/properties và schema hoặc hợp đồng cấu hình.
- Kiểm tra tham chiếu secret, tên tài nguyên và phiên bản artifact có tồn tại trong môi trường mục tiêu.
- Xác minh checksum/chữ ký của artifact khi tải hoặc trước khi triển khai.
- Review bắt buộc cho thay đổi production, quyền secret và tham chiếu tài nguyên nhạy cảm.
- Kiểm tra rollback: phiên bản dữ liệu hoặc secret cũ có còn khả dụng trong thời gian chuyển đổi hay không.

Secret scanning giúp phát hiện dấu hiệu rò rỉ nhưng không chứng minh repository hoàn toàn không có bí mật. Khi scanner phát hiện credential thật, phải coi đó là sự cố cần thu hồi/rotate, không chỉ đánh dấu false positive hoặc xóa dòng khỏi commit mới.

## Kết luận

Kho cấu hình Spring Cloud Config nên giữ các thuộc tính văn bản nhỏ và những tham chiếu cần thiết để ứng dụng biết cách kết nối tới tài nguyên. Bí mật thuộc về secret manager hoặc nguồn cấp runtime được bảo vệ; tệp nhị phân thuộc về secret/certificate store hoặc artifact repository; dữ liệu lớn thuộc về database, data lake hoặc object storage.

Khi tham chiếu tài nguyên bằng tên và phiên bản ổn định, cấp quyền theo workload, kiểm tra tính toàn vẹn và có quy trình luân chuyển/rollback, Git vẫn giữ được vai trò quản lý lịch sử cấu hình mà không trở thành nơi chứa mọi dữ liệu mà ứng dụng cần.

# Bảo vệ bí mật

## 1. Bí mật trong hệ sinh thái DSL là gì?

Bí mật (secret) là thông tin nhạy cảm được dùng để xác thực, cấp quyền hoặc bảo vệ một hệ thống và dữ liệu. Ví dụ thường gặp gồm password, API key, access token, refresh token, private key, certificate, database credential, signing key và encryption key.

Trong một hệ sinh thái DSL (Domain-Specific Language), secret có thể được dùng bởi compiler service, build worker, plugin, query engine, workflow runtime, connector hoặc deployment agent. Một workflow có thể cần credential để gọi payment service; query engine cần database identity để đọc dữ liệu; build pipeline cần token để tải dependency private hoặc ký artifact.

Ví dụ cấu hình:

~~~text
connector paymentGateway {
    endpoint: "https://payments.example"
    credential: secretRef("payment-api-key")
}
~~~

Source chỉ khai báo định danh của secret. Giá trị thực tế được lấy từ secret manager hoặc một cơ chế cấp credential đáng tin cậy khi cần. Cách này giúp tránh đưa password hoặc token trực tiếp vào DSL source, repository và artifact.

Bảo vệ bí mật không chỉ là mã hóa một file cấu hình. Nó bao gồm toàn bộ vòng đời: tạo, lưu, phân quyền, phân phối, sử dụng, ghi log, rotation, thu hồi, backup và xử lý khi secret bị lộ.

## 2. Vì sao DSL cần bảo vệ bí mật?

DSL thường mô tả hành vi có thể chạy trên dữ liệu hoặc gọi service. Nếu secret xuất hiện trong source hoặc được cấp cho runtime quá rộng, người có quyền đọc hoặc sửa DSL có thể chiếm quyền truy cập vào hệ thống phía sau.

Các rủi ro thường gặp:

- Developer commit API key vào repository.
- Secret bị in trong compiler diagnostic hoặc runtime log.
- Workflow state lưu token lâu hơn thời hạn cần thiết.
- Plugin IDE đọc toàn bộ environment variable của developer.
- Build script lấy credential phát hành trong một pull request không tin cậy.
- Query connector dùng database account có quyền admin.
- Một tenant có thể resolve secret thuộc tenant khác.
- Secret cũ tiếp tục có hiệu lực sau khi nhân sự hoặc service thay đổi.
- Artifact chứa giá trị bí mật đã được resolve trong lúc build.
- Backup hoặc crash dump vô tình lưu credential.

Bảo vệ secret giúp giảm tác động của việc lộ source, log, artifact hoặc workspace. Nó cũng giới hạn thiệt hại nếu một component bị xâm nhập.

## 3. Phân loại secret

Không phải mọi secret đều có cùng mục đích hoặc mức độ rủi ro. Nên phân loại để xác định cách lưu, thời hạn, quyền sử dụng và quy trình rotation.

| Loại | Mục đích | Ví dụ |
|---|---|---|
| Password | Xác thực tài khoản | Database password |
| API key | Gọi API | Payment API key |
| Access token | Truy cập ngắn hạn | OAuth access token |
| Refresh token | Cấp access token mới | OAuth refresh token |
| Private key | Ký hoặc giải mã | Artifact signing key |
| Certificate | Xác thực danh tính | Client certificate |
| Encryption key | Mã hóa dữ liệu | Data encryption key |
| Signing secret | Ký request hoặc webhook | HMAC secret |
| Connection credential | Kết nối backend | Database username/password |
| Recovery code | Khôi phục quyền truy cập | Backup authentication code |

Có thể phân loại thêm theo phạm vi:

- Developer secret: dùng trên máy cá nhân.
- Build secret: dùng trong CI để tải dependency hoặc tạo artifact.
- Runtime secret: dùng bởi service hoặc workflow khi chạy.
- Deployment secret: dùng để triển khai hoặc quản trị hạ tầng.
- Tenant secret: thuộc một khách hàng hoặc tổ chức.
- Platform secret: dùng cho hoạt động quản trị của toàn nền tảng.

Không nên dùng chung một credential cho nhiều mục đích nếu có thể cấp credential riêng. Khi một credential bị lộ, phạm vi thu hồi và thay thế sẽ nhỏ hơn.

## 4. Nguyên tắc thiết kế

Một hệ thống bảo vệ secret nên tuân theo các nguyên tắc:

1. Không ghi giá trị secret trực tiếp vào DSL source hoặc repository.
2. Lưu secret trong secret manager hoặc hệ thống quản lý credential chuyên dụng.
3. Chỉ cấp secret cho workload cần sử dụng nó.
4. Dùng identity của workload thay cho credential dùng chung khi nền tảng hỗ trợ.
5. Giới hạn thời hạn và phạm vi quyền của credential.
6. Resolve secret gần thời điểm sử dụng và trong đúng execution context.
7. Không ghi secret vào log, trace, diagnostic hoặc error message.
8. Không đóng gói secret vào artifact, container image hoặc cache.
9. Hỗ trợ rotation và revocation mà không phải sửa source.
10. Audit việc tạo, đọc, thay đổi và thu hồi secret.
11. Tách secret theo môi trường và tenant.
12. Có quy trình xử lý khi secret bị lộ.

Mục tiêu là giảm số nơi có thể nhìn thấy giá trị bí mật và giảm thời gian secret tồn tại trong bộ nhớ hoặc hệ thống.

## 5. Secret reference trong DSL

DSL nên tham chiếu secret bằng một định danh có cấu trúc thay vì chứa giá trị thật.

Ví dụ:

~~~text
connector inventory {
    endpoint: "https://inventory.example"
    credential: secretRef("inventory-reader")
}
~~~

Secret reference có thể là:

- Tên logic trong secret manager.
- URI có namespace và version.
- Alias do platform cấp.
- Resource ID của cloud secret service.
- Binding name được khai báo trong deployment manifest.

Một reference có thể biểu diễn:

~~~text
secret://production/payments/api-key
~~~

Định dạng cụ thể phụ thuộc hệ thống. Quan trọng là reference không chứa credential và được resolve bằng một identity có quyền.

### 5.1. Reference không phải quyền truy cập

Biết tên secret không có nghĩa caller được phép đọc nó. Secret manager phải xác thực principal và kiểm tra quyền trên secret resource.

Nếu người dùng sửa DSL để tham chiếu một secret khác, runtime phải kiểm tra quyền lại. Không được xem việc source đã compile thành công là bằng chứng caller có quyền sử dụng secret.

### 5.2. Alias và version

Reference có thể trỏ tới alias như current hoặc một version cụ thể. Alias thuận tiện cho rotation vì có thể đổi target mà không sửa source. Pin version hữu ích khi cần tái lập hoặc kiểm soát rollout.

Một chính sách có thể:

- Dùng alias cho runtime credential được rotation thường xuyên.
- Dùng version cố định cho artifact signing hoặc quy trình cần kiểm soát chặt.
- Ghi lại version thực tế được resolve trong audit metadata, không ghi giá trị secret.

## 6. Secret manager và kho lưu trữ an toàn

Secret manager là dịch vụ hoặc thành phần chuyên quản lý secret. Nó cung cấp các thao tác như tạo, lưu, đọc, version, rotate, revoke và audit.

Một secret manager thường có:

- Encrypted storage.
- Authentication và authorization.
- Secret versioning.
- Rotation workflow.
- Audit log.
- Access policy.
- API hoặc SDK để workload lấy secret.
- Backup và recovery.

Có thể dùng dịch vụ quản lý secret của cloud, hệ thống vault nội bộ hoặc secret store của nền tảng triển khai. Việc lựa chọn phụ thuộc hạ tầng, yêu cầu vận hành, compliance và khả năng tích hợp identity.

### 6.1. Encryption at rest

Secret cần được mã hóa khi lưu trữ. Key mã hóa nên được quản lý riêng và có chính sách truy cập, rotation và backup phù hợp.

Mã hóa at rest không ngăn được một workload đã được cấp quyền đọc secret. Vì vậy, authorization và audit vẫn cần thiết.

### 6.2. Encryption in transit

Secret cần được truyền qua kênh được bảo vệ, chẳng hạn TLS. Client cần xác minh danh tính server và không bỏ qua certificate validation trong production.

### 6.3. Access policy

Secret manager cần policy theo secret hoặc namespace. Ví dụ, payment worker chỉ được đọc payment credential của môi trường production mà nó phục vụ.

Không nên cấp quyền đọc toàn bộ secret store cho mọi worker chỉ vì việc cấu hình ban đầu thuận tiện hơn.

## 7. Workload identity và cấp credential

Workload identity cho phép một service hoặc worker chứng minh danh tính của chính nó để nhận quyền. Ví dụ, một pod, virtual machine hoặc build runner có thể nhận identity từ nền tảng mà không cần lưu một password dài hạn trong file cấu hình.

Luồng khái niệm:

~~~mermaid
flowchart TD
    A["DSL workflow"] --> B["Workflow runtime"]
    B --> C["Workload identity"]
    C --> D["Secret manager"]
    D --> E["Short-lived credential"]
    E --> F["External service"]
~~~

Runtime xác thực với identity provider, secret manager kiểm tra policy, sau đó cấp secret hoặc token phù hợp.

### 7.1. Least privilege

Credential chỉ nên có quyền cần thiết:

- Read-only nếu chỉ cần đọc.
- Chỉ một database/schema nếu có thể.
- Chỉ một API scope.
- Chỉ một tenant hoặc resource group.
- Chỉ một môi trường.
- Chỉ một loại operation.

Ví dụ, query engine đọc báo cáo không nên dùng database administrator credential. Workflow gửi email không cần quyền quản lý tài khoản người dùng.

### 7.2. Short-lived credentials

Credential có thời hạn ngắn giúp giảm rủi ro khi bị lộ. Runtime có thể lấy token mới khi token cũ gần hết hạn.

Cần xác định cách refresh khi một workflow dài đang chạy. Không nên lưu access token lâu dài trong workflow state nếu có thể lấy lại bằng workload identity.

### 7.3. Service identity riêng

Mỗi service hoặc nhóm workload nên có identity riêng. Nếu tất cả worker dùng chung một credential, khó xác định component nào đã truy cập secret và việc thu hồi có thể ảnh hưởng quá rộng.

## 8. Resolve secret trong quá trình thực thi

Secret nên được resolve tại runtime khi workload thực sự cần sử dụng. Compiler có thể kiểm tra reference về mặt cú pháp hoặc schema nhưng không nên lấy giá trị secret để nhúng vào output.

Một luồng điển hình:

1. Parser đọc secret reference.
2. Semantic validation xác nhận reference có định dạng hợp lệ.
3. Deployment binding xác định secret resource cho môi trường.
4. Runtime xác thực workload identity.
5. Secret manager kiểm tra policy.
6. Runtime nhận credential hoặc token.
7. Connector sử dụng credential để gọi service.
8. Runtime xóa hoặc giải phóng bản sao tạm khi không còn cần.
9. Audit ghi principal, secret ID, version và thời điểm truy cập.

### 8.1. Compile-time và runtime

Không nên resolve runtime secret trong lúc compile. Nếu compiler lấy secret rồi ghi vào generated source hoặc bytecode, artifact sẽ chứa dữ liệu nhạy cảm và có thể được phân phối rộng hơn phạm vi quyền ban đầu.

Build có thể cần secret để tải dependency private hoặc ký artifact. Đây là build secret riêng, cần được cấp trong bước CI tương ứng và không được đưa vào artifact output.

### 8.2. Binding theo môi trường

Cùng một DSL source có thể chạy ở development, staging và production:

~~~yaml
bindings:
  payment-api-key:
    development: secret://dev/payment/key
    staging: secret://staging/payment/key
    production: secret://prod/payment/key
~~~

Binding cần được quản lý bởi deployment configuration có quyền phù hợp. Source không nên tự chọn production secret khi chạy trong môi trường development.

## 9. Scope và tenant isolation

Trong hệ thống multi-tenant, secret của tenant này không được resolve bởi workload của tenant khác.

Một policy có thể ràng buộc:

~~~text
allow secret.read
when
    principal.tenantId == secret.tenantId
    and principal.workload == secret.allowedWorkload
~~~

Tenant context phải đến từ identity đã xác thực, không lấy trực tiếp từ query parameter hoặc field do client tự gửi.

### 9.1. Namespace

Secret nên được tổ chức theo application, environment và tenant:

~~~text
tenant-a/production/payment-api
tenant-b/production/payment-api
platform/production/artifact-signing
~~~

Tên namespace giúp tổ chức và quản trị nhưng không thay thế authorization. Secret manager vẫn phải kiểm tra quyền trên resource.

### 9.2. Shared worker

Nếu worker xử lý job của nhiều tenant, nó cần nhận context giới hạn cho từng job. Không nên tải toàn bộ tenant secrets vào bộ nhớ worker rồi chọn thủ công theo input.

Có thể dùng token ngắn hạn hoặc delegated capability chỉ cho phép đọc secret cần thiết của tenant đang xử lý.

## 10. Secret trong source code và repository

Không nên ghi secret literal trong DSL:

~~~text
connector database {
    username: "report_user"
    password: "real-password-value"
}
~~~

Thay vào đó:

~~~text
connector database {
    credential: secretRef("reporting-db-credential")
}
~~~

Các thực hành:

- Không commit password, token hoặc private key.
- Dùng secret reference trong source và config.
- Thêm file local secret vào ignore rules phù hợp.
- Cung cấp file example chỉ chứa placeholder.
- Dùng pre-commit hoặc repository scanning để phát hiện secret.
- Không xem file bị xóa khỏi working tree là đã biến mất khỏi Git history.

### 10.1. Nếu secret đã bị commit

Xóa secret khỏi file mới không đủ vì giá trị có thể còn trong commit history, fork, clone, build log hoặc artifact.

Cần:

1. Thu hồi hoặc rotate credential ngay.
2. Xác định nơi secret đã được sử dụng và phạm vi quyền.
3. Kiểm tra audit log để tìm truy cập bất thường.
4. Làm sạch repository history nếu policy yêu cầu.
5. Xóa hoặc thay artifact chứa secret.
6. Cập nhật secret binding và xác minh service hoạt động.
7. Ghi nhận incident và nguyên nhân.

Ưu tiên thu hồi credential vì không thể bảo đảm mọi bản sao lịch sử đã được xóa.

## 11. Secret trong generated code và artifact

Compiler, code generator và packager không được vô tình nhúng secret đã resolve vào output.

Các vị trí cần xem xét:

- Generated source.
- Bytecode constant pool.
- Build metadata.
- Container image layer.
- Archive manifest.
- Debug symbols.
- Documentation sample.
- Error report.

Artifact nên chứa reference hoặc binding key, không chứa giá trị credential. Nếu một công cụ cần secret trong build, phải bảo đảm secret không xuất hiện trong output, cache hoặc build log.

### 11.1. Build cache

Không đưa secret literal vào cache key nếu cache key có thể bị chia sẻ hoặc quan sát. Cũng không cache output chứa secret.

Nếu build output phụ thuộc vào credential, cần thiết kế lại để credential chỉ cấp quyền truy cập dependency và không ảnh hưởng nội dung artifact. Khi không thể tránh, cache cần được cô lập theo security context và có policy rõ.

### 11.2. Container image

Không truyền secret qua Dockerfile build argument hoặc lưu trong image layer nếu cơ chế build khiến giá trị có thể được truy xuất. Dùng secret mount hoặc cơ chế cấp credential tạm thời của build platform.

Image cuối cùng chỉ nên chứa application artifact và cấu hình không nhạy cảm.

## 12. Secret trong workflow state và event history

Workflow engine có thể lưu input, output, retry state và event history để phục hồi sau restart. Nếu activity output chứa token hoặc password, secret có thể bị lưu lâu hơn thời gian cần thiết.

Các nguyên tắc:

- Không đưa secret vào workflow variable nếu chỉ cần dùng trong một activity.
- Không lưu access token trong event history nếu có thể refresh.
- Lưu secret reference hoặc credential handle thay vì giá trị.
- Mask field nhạy cảm trong workflow inspection UI.
- Giới hạn quyền đọc history và execution payload.
- Xác định retention và deletion policy.

Ví dụ:

~~~text
step callPartner {
    with credential = secretRef("partner-api")
    call partnerApi.submit(request)
}
~~~

Runtime có thể resolve credential trong phạm vi activity và không đưa giá trị vào persisted workflow state.

### 12.1. Replay

Replay workflow không nên cần khôi phục secret cũ từ event history. Nếu cần gọi lại service, runtime nên resolve credential hiện hành theo policy và version workflow.

Tuy nhiên, credential mới có thể có quyền hoặc semantics khác credential cũ. Cần xác định replay có dùng current binding hay binding đã snapshot, và kiểm tra authorization trước khi tạo side effect.

## 13. Secret trong log, trace và diagnostic

Secret có thể bị lộ qua:

- Compiler error message.
- Runtime exception.
- HTTP request/response logging.
- Debugger variable inspection.
- Workflow history viewer.
- Trace attribute.
- Crash dump.
- Shell command output.
- Support bundle.

Các nguyên tắc:

1. Không log secret value.
2. Mask header và field nhạy cảm ở HTTP client.
3. Không đưa token vào exception message.
4. Redact query parameter hoặc workflow input trước khi log.
5. Hạn chế quyền đọc trace và crash dump.
6. Có retention policy và audit cho log store.
7. Kiểm tra redaction cả ở thư viện và connector.

Ví dụ log an toàn:

~~~text
secret_access:
  secret_id: production/payment-api
  version: 12
  principal: payment-worker
  result: allowed
  request_id: req-812
~~~

Log này ghi metadata truy cập mà không ghi giá trị bí mật.

### 13.1. Masking và redaction

Masking thay một phần giá trị để hiển thị, còn redaction loại bỏ hoàn toàn trường nhạy cảm. Với token và private key, thường nên redact toàn bộ.

Không nên chỉ dựa trên tên field như password hoặc token. Secret có thể nằm trong URL, query string, nested JSON, stack trace hoặc custom header. Redaction cần được áp dụng ở boundary và được kiểm thử bằng dữ liệu giả có marker dễ nhận biết.

## 14. Secret trong IDE và developer workstation

IDE plugin và language server có thể chạy với quyền của người dùng developer. Chúng có thể đọc workspace, environment, process và file cấu hình.

Rủi ro:

- Extension đọc file chứa credential.
- Debugger hiển thị secret trong variable view.
- Language server gửi source hoặc config tới service không được phê duyệt.
- Terminal task in token ra output.
- Local cache lưu credential không mã hóa.
- Plugin telemetry thu thập nội dung nhạy cảm.

Biện pháp:

- Giới hạn extension được cài.
- Tách secret khỏi workspace source.
- Dùng OS credential store hoặc secret manager.
- Không đưa secret vào editor setting đồng bộ cloud.
- Mask debugger variable theo schema.
- Kiểm soát telemetry và support bundle.
- Giới hạn language server chỉ đọc file cần thiết.
- Xóa credential local khi logout hoặc thu hồi thiết bị.

Developer workstation là môi trường có nhiều công cụ và quyền truy cập. Không nên giả định mọi extension đều đáng tin chỉ vì được cài trong IDE.

## 15. Secret trong CI/CD

CI pipeline có thể cần secret để tải dependency private, truy cập registry, ký artifact hoặc triển khai. Những secret này thường có giá trị cao và cần được giới hạn chặt.

### 15.1. Cấp secret theo job

Chỉ job cần secret mới được nhận secret đó. Job chạy lint hoặc parse source không cần deployment credential.

### 15.2. Untrusted pull request

Build từ fork hoặc pull request chưa được review không nên nhận secret phát hành. Một script độc hại có thể in environment hoặc gửi token ra ngoài.

### 15.3. Masking output

CI nên mask secret trong log, nhưng masking không thay thế việc tránh in secret. Encoding hoặc biến đổi giá trị có thể làm masking thất bại.

### 15.4. Short-lived token

Ưu tiên token có thời hạn ngắn và audience giới hạn thay cho access key dài hạn. Nếu nền tảng hỗ trợ workload identity federation, dùng nó để tránh lưu credential tĩnh trong CI.

### 15.5. Signing key

Private signing key không nên được tải xuống và lưu trên runner nếu có thể dùng signing service hoặc hardware-backed key. Pipeline chỉ gửi artifact digest tới signing service có authorization.

## 16. Rotation

Rotation là quá trình thay secret bằng giá trị mới theo lịch hoặc khi cần. Rotation giúp giảm thời gian một credential bị lộ có thể được sử dụng.

Một quy trình rotation:

1. Tạo credential mới ở hệ thống đích.
2. Lưu credential mới trong secret manager.
3. Cập nhật alias hoặc binding.
4. Cho workload chuyển sang credential mới.
5. Xác minh hoạt động và audit.
6. Thu hồi credential cũ.
7. Theo dõi lỗi từ client còn dùng giá trị cũ.

Ví dụ alias:

~~~text
secretRef("payment-api-key/current")
~~~

Khi alias chuyển từ version 11 sang 12, source không cần thay đổi. Runtime có thể lấy version mới ở lần resolve tiếp theo.

### 16.1. Overlap period

Một số service cho phép hai credential cùng hợp lệ trong thời gian ngắn. Có thể dùng overlap để rollout an toàn:

- Tạo credential mới.
- Triển khai workload dùng credential mới.
- Xác nhận không còn request từ credential cũ.
- Thu hồi credential cũ.

Không nên để overlap kéo dài vô hạn. Ghi rõ thời điểm kết thúc và kiểm tra client còn dùng credential cũ.

### 16.2. Rotation tự động

Rotation tự động giảm công việc thủ công nhưng cần xử lý:

- Secret manager và target service có đồng bộ không?
- Workload refresh credential thế nào?
- Connection pool có cần tái tạo không?
- Request đang chạy có bị ảnh hưởng không?
- Nếu rotation thất bại thì rollback ra sao?
- Có alert khi credential sắp hết hạn không?

## 17. Revocation và xử lý credential bị lộ

Revocation là thu hồi quyền sử dụng secret. Nó cần được thực hiện khi credential bị lộ, người dùng rời tổ chức, service ngừng hoạt động hoặc quyền không còn cần thiết.

Một incident response có thể gồm:

1. Xác định secret ID, version và phạm vi quyền.
2. Thu hồi hoặc disable credential tại hệ thống đích.
3. Rotate secret liên quan.
4. Thu hồi token/session còn hiệu lực nếu cần.
5. Tìm các workload và artifact đã dùng secret.
6. Kiểm tra audit log và hoạt động bất thường.
7. Xóa hoặc thay artifact, cache và config bị ảnh hưởng.
8. Cập nhật binding và xác minh service.
9. Ghi incident, nguyên nhân và biện pháp phòng ngừa.

Nếu secret bị lộ trong repository, log hoặc artifact, cần giả định mọi người có quyền đọc các bản sao đó đều có thể đã nhìn thấy giá trị. Xóa bản hiển thị không thay thế revocation.

## 18. Secret caching và thời gian tồn tại trong bộ nhớ

Đọc secret từ manager cho mỗi request có thể tăng latency và tải. Cache có thể cải thiện hiệu năng nhưng tạo ra thời gian secret cũ tiếp tục được sử dụng sau rotation hoặc revocation.

Cần xác định:

- Cache ở process, worker hay connector?
- TTL bao lâu?
- Có refresh trước expiry không?
- Làm sao invalidation khi revoke?
- Có cache riêng theo tenant và identity không?
- Secret có bị ghi vào disk hoặc snapshot không?

Với credential nhạy cảm, cache nên có TTL ngắn và được bảo vệ trong bộ nhớ. Nếu secret manager hỗ trợ notification hoặc version check, runtime có thể cập nhật sớm khi rotation.

### 18.1. In-memory handling

Ngôn ngữ và runtime có thể tạo nhiều bản sao chuỗi trong heap. Không phải lúc nào cũng có thể xóa chắc chắn từng bản sao ngay lập tức, đặc biệt với immutable string.

Có thể giảm exposure bằng cách:

- Giữ secret trong scope ngắn.
- Tránh copy không cần thiết.
- Không giữ secret trong object dùng chung lâu dài.
- Hạn chế heap dump và core dump.
- Dùng API credential provider thay vì trả secret cho nhiều lớp.
- Giải phóng buffer có thể xóa khi nền tảng hỗ trợ.

Không nên tuyên bố memory zeroization tuyệt đối nếu runtime không bảo đảm điều đó.

## 19. Secret và cache/build artifacts

Secret không được xuất hiện trong:

- Build cache.
- Compiler intermediate output.
- Container layer.
- Package archive.
- Generated documentation.
- Test report.
- Crash dump.
- CI artifact.

Nếu một bước build cần secret để truy cập registry, secret chỉ nên có mặt trong environment của bước đó và không được truyền vào process con không cần quyền.

Cache key cũng không nên chứa secret literal. Nếu cần phân vùng cache theo credential scope, dùng identity hoặc scope ID không nhạy cảm thay vì giá trị token.

## 20. Phân quyền theo môi trường

Development, staging và production nên có secret riêng:

| Môi trường | Ví dụ credential | Quyền |
|---|---|---|
| Development | Sandbox API key | Dữ liệu giả lập |
| Staging | Test service credential | Môi trường kiểm thử |
| Production | Live API credential | Chỉ workload production được phê duyệt |

Không nên copy production secret sang máy developer để tiện debug. Nếu cần tái hiện lỗi, ưu tiên dữ liệu và credential test có phạm vi hạn chế.

Deployment manifest nên tham chiếu secret theo environment binding. Runtime cần xác minh environment identity trước khi resolve.

## 21. Secret và policy-as-code

Một DSL có thể khai báo secret binding hoặc policy, nhưng việc cấp quyền đọc secret cần được quản lý riêng.

Ví dụ policy:

~~~text
policy paymentWorkerSecretAccess {
    allow secret.read("production/payment-api")
    when principal.workload == "payment-worker"
      and principal.environment == "production"
}
~~~

Policy nên:

- Có owner và version.
- Được review trước khi áp dụng.
- Có test cho permit và deny.
- Áp dụng least privilege.
- Được audit khi thay đổi.
- Không cho workload tự cấp quyền cho chính nó.

Nếu policy compiler tạo policy artifact, artifact đó cần được xác minh integrity và triển khai theo quy trình có thẩm quyền.

## 22. Secret trong connector và external service

Connector là nơi secret thường được sử dụng để gọi database, API hoặc message broker.

Connector contract nên khai báo:

- Loại credential được hỗ trợ.
- Secret reference hoặc identity provider.
- Scope cần thiết.
- Thời hạn credential.
- Cách refresh.
- Cách xử lý authentication failure.
- Các header hoặc field cần redact.

Ví dụ:

~~~text
connector analyticsDatabase {
    endpoint: config("analytics.endpoint")
    authentication: workloadIdentity()
    requiredScope: "analytics.read"
    connectionTimeout: 3 seconds
}
~~~

Nếu backend hỗ trợ workload identity, có thể không cần password tĩnh. Nếu buộc phải dùng credential, lấy nó qua secret provider và không đưa vào query text.

## 23. Secret và backup/disaster recovery

Backup secret manager cần bảo vệ tương đương hệ thống chính. Nếu backup không mã hóa hoặc quyền đọc quá rộng, nó trở thành một đường rò rỉ lớn.

Cần xác định:

- Backup được mã hóa bằng key nào?
- Ai có quyền restore?
- Key encryption được backup và recovery thế nào?
- Secret version history được giữ bao lâu?
- Khi restore, secret đã revoke có được phục hồi nhầm không?
- Có audit thao tác restore không?

Disaster recovery cần cân bằng khả năng khôi phục với việc không hồi sinh credential đã bị thu hồi. Một quy trình restore có thể cần reconciliation với trạng thái credential hiện tại tại hệ thống đích.

## 24. Secret scanning và prevention

Secret scanning tìm giá trị có dạng credential trong source, commit, artifact hoặc log.

Có thể tích hợp:

- Pre-commit scanner.
- Repository push protection.
- CI secret scan.
- Container/image scan.
- Artifact scan.
- Log scanning.
- Periodic scan lịch sử repository.

Scanner có thể phát hiện false positive và không nhận diện mọi định dạng secret. Vì vậy, cần quy trình triage và không xem scan sạch là bằng chứng tuyệt đối không có secret.

### 24.1. Test marker

Trong test, dùng giá trị giả có marker riêng để xác nhận redaction:

~~~text
TEST_SECRET_MARKER_9f4a2
~~~

Chạy qua compiler error, runtime exception, trace và CI log; xác nhận marker không xuất hiện trong output được lưu.

Không dùng credential thật để kiểm tra masking.

## 25. Kiểm thử bảo vệ bí mật

Các lớp kiểm thử có thể gồm:

### 25.1. Source scanning test

Kiểm tra source và generated file không chứa secret literal hoặc pattern credential bị cấm.

### 25.2. Authorization test

Principal không có quyền phải bị từ chối khi resolve secret. Kiểm tra cả trường hợp sửa reference trong DSL.

### 25.3. Tenant isolation test

Workload tenant A không thể resolve secret của tenant B qua alias, path, cache hoặc connector.

### 25.4. Log redaction test

Đưa test marker qua các đường error, debug, HTTP logging, trace và workflow history. Xác nhận marker không bị lưu.

### 25.5. Rotation test

Đổi alias sang version mới và xác nhận workload chuyển sang credential mới; credential cũ được thu hồi theo kế hoạch.

### 25.6. Revocation test

Thu hồi credential và xác nhận request mới không còn dùng được nó, kể cả qua cache sau thời gian invalidation được công bố.

### 25.7. Artifact inspection

Quét generated source, bytecode, package, image layer và build cache bằng secret marker giả.

### 25.8. CI isolation test

Xác nhận pull request không tin cậy không nhận secret phát hành và log không in environment credential.

### 25.9. Recovery test

Khôi phục backup trong môi trường thử nghiệm và xác nhận credential đã revoke không được tái kích hoạt ngoài ý muốn.

## 26. Những lỗi thiết kế thường gặp

### Ghi secret trực tiếp trong DSL

Source control và code review trở thành nơi lưu credential. Dùng secret reference và secret manager.

### Xem reference là authorization

Caller đổi tên secret để thử đọc resource khác. Kiểm tra quyền trên secret manager mỗi lần resolve.

### Dùng chung credential cho nhiều workload

Khó truy vết và thu hồi. Cấp identity và credential riêng theo service, environment và tenant.

### Resolve secret trong compile-time

Giá trị có thể bị nhúng vào artifact hoặc cache. Resolve runtime secret khi workload thực sự cần.

### Ghi token vào workflow history

Secret tồn tại lâu hơn cần thiết và có thể lộ qua UI hoặc backup. Lưu reference hoặc handle.

### Chỉ dựa vào log masking mặc định

Custom connector hoặc exception có thể in secret theo cách khác. Kiểm thử redaction ở mọi đường output.

### Rotation nhưng không thu hồi credential cũ

Hai credential cùng có hiệu lực vô thời hạn. Có overlap period và deadline thu hồi rõ ràng.

### Cache secret quá lâu

Credential cũ tiếp tục được sử dụng sau revoke. TTL ngắn, refresh và invalidation có kiểm soát.

### Đưa secret vào container build argument

Giá trị có thể còn trong layer hoặc build metadata. Dùng secret mount hoặc workload identity.

### Cấp production secret cho mọi CI job

Script không tin cậy có thể lấy credential. Cấp secret theo job và chỉ cho pipeline được phê duyệt.

### Cho rằng xóa file là đã xử lý secret lộ

Git history, fork, log và artifact có thể vẫn chứa giá trị. Revoke/rotate trước, sau đó xử lý bản sao.

## 27. Quy trình quản lý secret cho DSL

Một quy trình vận hành có thể gồm:

1. **Kiểm kê secret.** Liệt kê credential theo application, environment, tenant và owner.
2. **Phân loại.** Xác định mục đích, độ nhạy cảm, quyền và thời hạn.
3. **Chọn secret manager.** Dùng kho lưu trữ có encryption, policy, version và audit.
4. **Thiết kế reference.** Source chỉ chứa alias hoặc resource ID.
5. **Cấp workload identity.** Mỗi service nhận identity riêng và quyền tối thiểu.
6. **Resolve ở runtime.** Lấy credential gần thời điểm sử dụng.
7. **Bảo vệ dữ liệu trung gian.** Không ghi secret vào artifact, state, cache hoặc log.
8. **Thiết lập rotation.** Có lịch, overlap period và thu hồi credential cũ.
9. **Thiết lập revocation.** Có quy trình khẩn cấp khi secret bị lộ.
10. **Audit.** Ghi ai đọc hoặc thay đổi secret mà không ghi giá trị.
11. **Scan và test.** Quét repository, artifact, image và log.
12. **Review định kỳ.** Xác nhận owner, quyền và credential còn cần thiết.

Mỗi secret nên có owner, purpose, scope, expiry/rotation policy và contact xử lý incident. Secret không có owner hoặc không rõ mục đích cần được điều tra và loại bỏ an toàn.

## 28. Ví dụ end-to-end: workflow gọi payment service

Giả sử một workflow DSL cần gọi payment API trong môi trường production.

Workflow:

~~~text
workflow capturePayment {
    step charge {
        call paymentGateway.charge(
            orderId,
            amount,
            idempotencyKey = workflow.id
        )
    }
}
~~~

Connector binding:

~~~yaml
connector: paymentGateway
endpoint: https://payments.example
authentication:
  type: secretReference
  secretId: production/payments/api-key
~~~

Policy:

~~~text
allow secret.read("production/payments/api-key")
when principal.workload == "payment-worker"
  and principal.environment == "production"
~~~

Luồng thực thi:

1. Workflow artifact được xác minh trước khi load.
2. Worker nhận job và workload identity từ platform.
3. Runtime kiểm tra identity và tenant context.
4. Connector yêu cầu secret manager resolve secret reference.
5. Secret manager kiểm tra policy và cấp credential hiện hành.
6. Connector gọi payment API qua TLS.
7. Runtime không ghi credential vào workflow state hoặc log.
8. Audit ghi secret ID, version, principal và request ID.
9. Khi rotation, alias chuyển sang version mới và worker refresh credential.
10. Credential cũ được thu hồi sau overlap period.

Nếu token bị lộ, operator thu hồi credential, kiểm tra audit, tạo version mới và xác minh worker đã chuyển sang credential mới. Source workflow không cần chứa hoặc thay đổi giá trị secret.

## 29. Checklist câu hỏi khi thiết kế

**Inventory và ownership**

- Secret nào được sử dụng bởi compiler, build, runtime và connector?
- Ai là owner và secret phục vụ mục đích nào?
- Có credential dùng chung giữa môi trường hoặc tenant không?

**Storage và access**

- Secret được lưu ở đâu và mã hóa thế nào?
- Workload identity được xác minh ra sao?
- Có least privilege và short-lived credential không?
- Reference có thể bị caller sửa để truy cập secret khác không?

**Lifecycle**

- Rotation diễn ra theo lịch hay theo sự kiện?
- Credential cũ được thu hồi khi nào?
- Có quy trình khẩn cấp khi secret bị lộ không?
- Backup restore có thể hồi sinh secret đã revoke không?

**Exposure**

- Secret có thể xuất hiện trong source, artifact, cache hoặc workflow history không?
- Compiler, connector và CI log có redaction không?
- Debugger, trace và crash dump có chứa credential không?

**Verification**

- Có secret scanning và marker-based redaction test không?
- Có kiểm tra tenant isolation và authorization không?
- Có rotation, revocation và recovery test không?

## 30. Kết luận

Bảo vệ bí mật trong hệ sinh thái DSL là quản lý toàn bộ vòng đời credential từ lúc tạo tới khi thu hồi. DSL source nên tham chiếu secret bằng định danh; secret manager chịu trách nhiệm lưu trữ, version, authorization và audit; runtime dùng workload identity để resolve credential đúng phạm vi và gần thời điểm sử dụng.

Secret cần được tách theo môi trường, tenant và workload; cấp quyền tối thiểu; ưu tiên credential ngắn hạn; và không để giá trị xuất hiện trong generated artifact, workflow history, cache, log hoặc CI output. Rotation và revocation phải có quy trình rõ ràng, bao gồm xử lý các bản sao đã tồn tại khi secret bị lộ.

Một thiết kế an toàn kết hợp secret reference, workload identity, secret manager, least privilege, redaction, scanning, audit và kiểm thử. Khi những kiểm soát này được thực thi ở đúng trust boundary, DSL có thể gọi service và xử lý dữ liệu cần thiết mà không biến source code hoặc artifact thành nơi lưu trữ credential.

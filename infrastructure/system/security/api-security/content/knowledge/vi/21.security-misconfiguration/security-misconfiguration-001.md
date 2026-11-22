# Default credential, debug mode và verbose error

Một API có thể dùng HTTPS, xác thực JWT và kiểm tra quyền trên từng endpoint nhưng vẫn dễ bị xâm nhập nếu môi trường triển khai giữ tài khoản mặc định, bật debug mode hoặc trả lỗi quá chi tiết. Những cấu hình này thường xuất hiện trong giai đoạn phát triển để giúp cài đặt nhanh và chẩn đoán thuận tiện. Nếu chúng được đưa nguyên trạng lên production, attacker có thể đoán hoặc sử dụng credential ban đầu, đọc thông tin nội bộ qua error response, truy cập công cụ quản trị hoặc khai thác giao diện debug.

Đây là nhóm rủi ro **Security Misconfiguration**. Lỗi không nhất thiết nằm trong một dòng code nghiệp vụ; nó có thể đến từ profile sai, biến môi trường thiếu, cấu hình mặc định chưa được thay, endpoint quản trị bị expose, proxy thêm header không an toàn hoặc một thay đổi triển khai làm bật lại debug. Cấu hình bảo mật cần được kiểm soát như một phần của thiết kế API và quy trình release.

Trong phạm vi `SECURITY_API_SECURITY`, cần đánh giá misconfiguration theo endpoint, object và luồng nghiệp vụ. Một cấu hình yếu có thể vô hiệu hóa authentication, authorization, validation, bảo vệ dữ liệu hoặc giới hạn tài nguyên ở nhiều endpoint cùng lúc. Vì vậy, hãy xác định rõ cấu hình nào được phép ở từng môi trường, kiểm tra trạng thái thực tế khi ứng dụng khởi động và giám sát drift sau khi triển khai.

## 1. Ba nhóm cấu hình nguy hiểm

| Nhóm | Mục đích hợp lệ khi phát triển | Rủi ro khi dùng ở production |
|---|---|---|
| Default credential | Cài đặt nhanh, demo hoặc bootstrap tài khoản đầu tiên | Attacker biết hoặc đoán được mật khẩu, token, API key hay secret ban đầu |
| Debug mode | Chẩn đoán lỗi, inspect request, hot reload hoặc remote debugging | Lộ stack trace, biến môi trường, request data; có thể mở giao diện hoặc cổng điều khiển |
| Verbose error | Giúp developer hiểu nguyên nhân lỗi và vị trí xảy ra | Lộ framework, class, SQL, schema, filesystem path, upstream detail hoặc dữ liệu nhạy cảm |

Ba nhóm thường kết hợp với nhau. Ví dụ một trang debug có thể được bảo vệ bằng tài khoản mặc định; một exception handler trả stack trace có thể tiết lộ đường dẫn đến file cấu hình; thông tin đó lại giúp attacker tìm secret hoặc endpoint quản trị.

Không nên coi misconfiguration chỉ là việc “đổi mật khẩu admin”. Cần review toàn bộ default, debug endpoint, error handler, profile, secret source, management port, CORS, TLS, logging và quyền truy cập của từng route nhạy cảm.

## 2. Default credential và tài khoản bootstrap

Default credential là thông tin xác thực được nhà cung cấp, framework, template, image hoặc đội phát triển đặt sẵn để hệ thống có thể chạy lần đầu. Nó có thể là username/password, API key, signing secret, database password, token tích hợp hoặc tài khoản quản trị được tạo tự động.

Các nguồn thường gặp:

- Tài khoản admin trong sample data hoặc demo seed.
- Username/password được ghi trong README, Docker Compose, Helm values hoặc file cấu hình mẫu.
- Mật khẩu chung được nhúng trong container image hoặc script cài đặt.
- API key dùng chung giữa staging và production.
- Secret ký JWT hoặc session có giá trị cố định trong source code.
- Tài khoản bootstrap được tạo nhưng không bị vô hiệu hóa sau lần cài đặt đầu tiên.
- Credential của database, message broker, object storage hoặc service account vẫn giữ giá trị ví dụ.

### 2.1. Vì sao đổi tên tài khoản là chưa đủ?

Attacker thường thử các credential phổ biến hoặc lấy từ tài liệu, repository, image và hệ thống demo. Đổi username từ `admin` sang tên khác không khắc phục được nếu password vẫn dùng chung hoặc secret nằm trong artifact. Credential cần được sinh riêng cho từng môi trường và từng workload, có quyền tối thiểu và có khả năng thu hồi.

Không dùng một credential cho nhiều service. Nếu một key dùng chung cho gateway, worker và admin tool bị lộ, phạm vi ảnh hưởng sẽ lan rộng. Tách credential giúp giới hạn blast radius và xác định chính xác workload nào cần rotate.

### 2.2. Bootstrap an toàn

Hệ thống đôi khi cần tạo admin đầu tiên. Quy trình bootstrap nên có các đặc điểm:

1. Tài khoản hoặc secret ban đầu được sinh ngẫu nhiên và duy nhất cho từng deployment.
2. Secret được cung cấp qua kênh provisioning an toàn, chỉ hiển thị một lần nếu phù hợp.
3. Bắt buộc thay credential hoặc hoàn tất thiết lập MFA trước khi cấp quyền quản trị đầy đủ.
4. Tài khoản bootstrap có thời hạn hoặc trạng thái `PENDING_SETUP`, không tồn tại như một tài khoản dùng chung lâu dài.
5. Ghi audit cho việc tạo, kích hoạt, đổi và vô hiệu hóa bootstrap credential.
6. Sau khi thiết lập thành công, thu hồi credential bootstrap và xác minh nó không còn được chấp nhận.

Không tự động tạo một admin có password cố định để “đảm bảo hệ thống luôn truy cập được”. Nếu bootstrap thất bại, deployment nên dừng hoặc yêu cầu thao tác provisioning có kiểm soát.

### 2.3. Tài khoản mặc định không dùng được trong production

Nếu sản phẩm cần demo user hoặc sample account, chỉ tạo trong môi trường demo cô lập với dữ liệu giả. Production seed không được tạo user/password chung. Có thể thêm startup validation để phát hiện giá trị mẫu còn tồn tại và từ chối khởi động.

Ví dụ kiểm tra cấu hình:

```java
@Component
class ProductionCredentialGuard implements ApplicationRunner {
    private final Environment environment;

    ProductionCredentialGuard(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!environment.acceptsProfiles(Profiles.of("prod", "production"))) {
            return;
        }

        boolean bootstrapEnabled = environment.getProperty(
            "bootstrap.admin.enabled", Boolean.class, false);
        if (bootstrapEnabled) {
            throw new IllegalStateException(
                "Bootstrap admin must be disabled after production provisioning");
        }
    }
}
```

Đây là ví dụ minh họa, không phải cơ chế kiểm tra secret hoàn chỉnh. So sánh với một vài chuỗi mẫu chỉ phát hiện được một số lỗi rõ ràng; nó không chứng minh secret có entropy cao hoặc chưa bị tái sử dụng. Production nên lấy secret từ secret manager, kiểm tra policy về nguồn và vòng đời, đồng thời tránh log giá trị secret khi startup fail.

## 3. Quản lý secret và credential theo môi trường

Secret không nên nằm trong source code, image, repository, log hoặc tài liệu vận hành công khai. Dùng secret manager, KMS, workload identity hoặc cơ chế cấp credential của nền tảng khi có thể.

Các nguyên tắc:

- Mỗi môi trường và workload có credential riêng.
- Cấp đúng quyền và audience; không dùng admin credential cho service-to-service thông thường.
- Không hard-code password, API key, JWT signing key hoặc database credential.
- Không commit file `.env`, secret values, private key hoặc certificate private vào Git.
- Không bake secret vào Docker image hoặc build artifact.
- Giới hạn ai và workload nào có thể đọc secret.
- Có rotation, expiry, revoke và quy trình xử lý khi secret bị lộ.
- Audit việc đọc, tạo, thay thế và thu hồi secret.

### 3.1. Biến môi trường không tự động là secret manager

Environment variable thường thuận tiện cho cấu hình, nhưng vẫn có thể bị lộ qua process inspection, crash dump, debug endpoint, diagnostic bundle hoặc log nếu ứng dụng in toàn bộ environment. Nếu nền tảng hỗ trợ secret injection hoặc workload identity, ưu tiên cơ chế đó và hạn chế quyền đọc của process.

Không log toàn bộ `System.getenv()`, Spring `Environment`, startup configuration hoặc command line arguments. Nếu cần kiểm tra cấu hình, chỉ log tên property và trạng thái đã được redact, ví dụ `db.password=configured`, không log giá trị.

### 3.2. Tách config và secret

Config không nhạy cảm như port, feature flag, timeout hoặc log level có thể được quản lý bằng config system. Secret như password, API key, signing key và private key cần storage/permission khác. Đừng để một endpoint debug hiển thị toàn bộ config map chỉ vì một phần config không nhạy cảm.

### 3.3. Rotation và thu hồi

Rotation cần có kế hoạch overlap khi nghiệp vụ cho phép, nhưng credential bị compromise cần được thu hồi khẩn cấp. Với JWT signing key, API key và database password, xác định:

- Key/secret nào đang được workload sử dụng.
- Thời gian phân phối secret mới đến tất cả instance.
- Thời gian cache credential cũ còn hiệu lực.
- Cách kiểm chứng credential cũ bị từ chối.
- Cách rollback nếu migration thất bại mà không khôi phục secret đã lộ.

Không kéo dài overlap vô thời hạn chỉ để tránh sửa client. Tài khoản bootstrap và credential mẫu phải được loại bỏ sau khi provisioning hoàn tất.

## 4. Debug mode và debug endpoint

Debug mode có thể bật nhiều khả năng chẩn đoán: stack trace chi tiết, request/response dump, variable inspection, interactive console, hot reload, debug toolbar, remote debugger hoặc actuator/diagnostic endpoint. Một số khả năng chỉ nên tồn tại trong môi trường local.

Rủi ro phụ thuộc framework và cách triển khai, nhưng có thể gồm:

- Hiển thị stack trace và source path cho caller.
- Tiết lộ biến môi trường, cấu hình, token hoặc dữ liệu request.
- Mở endpoint thực thi lệnh hoặc interactive console.
- Expose remote debug port mà không có authentication phù hợp.
- Bỏ qua cache, CORS, CSRF hoặc security filter trong cấu hình dev.
- Cho phép truy cập actuator, heap dump, thread dump, env/config properties hoặc log.
- Bật auto-reload hoặc development server trên interface public.

### 4.1. Debugger không phải endpoint quản trị thông thường

Remote debugger có thể cho phép inspect state và trong một số cấu hình thực thi code trong process. Nếu cổng debug bị public, người truy cập có thể kiểm soát ứng dụng với quyền của process. Không expose remote debugger trong production. Khi cần chẩn đoán production, dùng công cụ vận hành có authentication mạnh, network restriction, approval và audit; bật trong thời gian ngắn theo runbook.

### 4.2. Debug mode không nên phụ thuộc vào query parameter

Không bật debug bằng tham số request như `?debug=true`, header do client gửi hoặc cookie dễ đoán. Nếu có diagnostic mode khẩn cấp, phải được điều khiển bởi operator identity có quyền riêng, có thời hạn tự tắt, giới hạn mạng và audit. Không để user có quyền gọi API thông thường thay đổi log level hoặc expose management endpoint.

### 4.3. Cấu hình Spring Boot cho production

Ví dụ cấu hình cơ bản:

```yaml
server:
  error:
    include-exception: false
    include-message: never
    include-binding-errors: never
    include-stacktrace: never

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
```

Các property và semantics cần đối chiếu với phiên bản Spring Boot đang dùng. Cấu hình `include-stacktrace: never` giúp không đưa stack trace vào error response mặc định; nó không tự động bảo vệ mọi exception handler tùy chỉnh hoặc mọi endpoint diagnostic. `health` và `info` cũng cần review nội dung trả về và network/authentication policy. Không expose tất cả actuator endpoints chỉ để tiện vận hành.

Đừng dựa vào việc “không ai biết URL actuator”. Endpoint quản trị cần được bảo vệ bằng authentication, authorization, network policy và cấu hình exposure rõ ràng. Với thông tin nhạy cảm, tốt nhất không expose qua public application listener.

## 5. Verbose error và thông tin nội bộ

Error response giúp client hiểu request thất bại, nhưng không cần chứa chi tiết implementation. Những thông tin sau thường không nên trả trực tiếp:

- Stack trace, package/class/method và số dòng source.
- SQL, tên database/schema/table/column/constraint.
- Filesystem path, tên file tạm hoặc mount point.
- Framework exception, dependency version hoặc cấu hình nội bộ.
- Request headers, cookie, bearer token, API key hoặc rejected value.
- Raw response từ upstream/provider.
- Secret, biến môi trường, internal hostname, IP hoặc service topology.
- Chi tiết policy/rule nội bộ giúp attacker né kiểm soát.

Ví dụ lỗi không an toàn:

```json
{
  "error": "org.springframework.dao.DataIntegrityViolationException",
  "message": "duplicate key violates constraint uk_customer_email",
  "sql": "insert into customer(email, tenant_id, ...) values (...) ",
  "stackTrace": "com.example.CustomerRepository.save(CustomerRepository.java:81)"
}
```

Client thường chỉ cần biết một giá trị không hợp lệ, dữ liệu đang xung đột hoặc hệ thống tạm thời không thể xử lý. Có thể trả public error code ổn định như `VALIDATION_FAILED`, `RESOURCE_CONFLICT` hoặc `INTERNAL_ERROR`, cùng một `traceId` để support tra cứu log nội bộ.

### 5.1. Error response theo hợp đồng công khai

Ví dụ:

```json
{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "detail": "The request could not be completed.",
  "code": "INTERNAL_ERROR",
  "traceId": "01J..."
}
```

Thông điệp này không cho biết exception, SQL hay file nào gặp lỗi. `traceId` chỉ là reference để support tra cứu; không được dùng nó như credential để lấy log hoặc dữ liệu nội bộ.

Với validation, có thể trả field công khai và mã lỗi cụ thể như `INVALID_FORMAT` hoặc `OUT_OF_RANGE`, nhưng không trả rejected value, tên property nội bộ hoặc validator class. Với authorization, tránh response làm lộ object hoặc tenant ngoài phạm vi caller.

### 5.2. Account và object enumeration

Thông báo lỗi có thể vô tình trở thành oracle:

- `User not found` khác `Wrong password` cho phép dò tài khoản.
- `Order exists but belongs to another tenant` xác nhận ID có thật.
- `API key prefix recognized` có thể hỗ trợ dò credential.
- Thời gian response khác biệt lớn có thể tiết lộ nhánh xử lý.

Chọn response masking theo threat model. Ví dụ login có thể trả cùng thông điệp cho account không tồn tại và password sai. Object ngoài tenant có thể trả `404` để che giấu sự tồn tại. Không cần làm mọi response giống hệt tuyệt đối, nhưng tránh tiết lộ thông tin không cần thiết.

## 6. Cấu hình mặc định nguy hiểm ngoài credential và debug

Default credential, debug và verbose error thường xuất hiện cùng các cấu hình rộng khác. Cần kiểm tra các nhóm sau vì chúng có thể làm suy yếu API ở quy mô toàn hệ thống.

### 6.1. Authorization permissive

Các cấu hình như `permitAll()` cho toàn bộ API, fallback `.authenticated()` cho mọi route quản trị hoặc `@EnableMethodSecurity` bị thiếu có thể làm mất kiểm soát quyền. Đặc biệt, endpoint mới có thể vô tình được phép nếu security matcher không có deny-by-default.

Hãy lập inventory endpoint và permission, đặt rule cụ thể trước fallback, từ chối route/method chưa phân loại và kiểm thử qua security filter chain thực tế. Không dựa vào frontend ẩn nút hoặc gateway duy nhất để bảo vệ service.

### 6.2. CORS quá rộng

Không bật `Access-Control-Allow-Origin: *` cùng credential hoặc phản chiếu mọi Origin mà không kiểm tra. CORS không thay authentication/authorization, nhưng cấu hình sai có thể cho website ngoài đọc response mà browser gửi kèm credential. Allowlist origin theo ứng dụng, method và header cần thiết; không coi CORS là firewall.

### 6.3. TLS và cookie

Production cần TLS trên các đường truyền phù hợp, certificate validation và cấu hình redirect/secure transport đúng. Session cookie nên có `Secure`, `HttpOnly`, `SameSite` phù hợp; không đặt token nhạy cảm trong URL. Không tắt certificate verification trong HTTP client chỉ để vượt lỗi môi trường.

### 6.4. Management endpoint và actuator

Health, metrics, env, config props, heap dump, thread dump, mappings, loggers và shutdown có mức độ nhạy cảm khác nhau. Chỉ expose endpoint cần thiết, tách management port/network nếu phù hợp, bảo vệ bằng quyền riêng và không trả detail nội bộ cho public caller. Endpoint có side effect như shutdown hoặc thay log level cần quyền vận hành và audit.

### 6.5. Default headers và static resources

Review security headers, cache policy, content type sniffing, directory listing, static file exposure và default error page của reverse proxy. Không để file `.env`, backup, heap dump, config export hoặc source map chứa secret nằm trong web root hoặc object storage public.

## 7. Quản lý profile và configuration drift

Nhiều sự cố xảy ra vì ứng dụng chạy nhầm profile hoặc cấu hình production bị ghi đè bởi biến môi trường, command line, config server hoặc Helm values.

### 7.1. Phân tách môi trường

| Môi trường | Mục đích | Cấu hình phù hợp |
|---|---|---|
| Local development | Phát triển trên máy cá nhân | Debug có kiểm soát, dữ liệu giả, credential local riêng |
| Test/CI | Kiểm thử tự động | Credential ngắn hạn, fixture, không dùng secret production |
| Staging | Mô phỏng production | Cấu hình gần production, dữ liệu đã mask, không bật debug công khai |
| Production | Phục vụ người dùng thật | Debug tắt, secret riêng, error tối giản, management endpoint giới hạn |

Không copy nguyên file `application-dev.yml` sang production. Profile dev có thể bật console, seed account, verbose logging hoặc security rule permissive. Production cần một bộ cấu hình rõ ràng và có kiểm tra.

### 7.2. Fail fast khi thiếu cấu hình bảo mật

Nếu production không có signing key, database credential, allowed origin hoặc secret cần thiết, ứng dụng nên fail startup thay vì dùng giá trị mặc định yếu. Với các feature tùy chọn, có thể disable feature và cảnh báo nếu điều đó an toàn; nhưng không tự chuyển sang credential mẫu.

Không in giá trị secret khi báo lỗi. Chỉ nêu property name và nguồn cấu hình dự kiến, ví dụ `security.jwt.signing-key is missing; configure it through the secret provider`.

### 7.3. Configuration precedence

Framework có thứ tự ưu tiên giữa command line, environment, config file, config server và default. Một property an toàn trong file có thể bị override bởi biến môi trường hoặc Helm value. Cần xác định nguồn cuối cùng đang có hiệu lực và kiểm tra cấu hình runtime đã resolve, không chỉ review một file YAML.

### 7.4. Drift detection

Sau khi deploy, cấu hình có thể bị thay đổi thủ công hoặc một rollout cũ khôi phục giá trị không an toàn. Dùng policy-as-code, configuration inventory, admission policy hoặc periodic checks để phát hiện:

- Debug/log level chi tiết được bật ngoài môi trường cho phép.
- Management endpoint mới được expose.
- Default account/secret còn hoạt động.
- CORS origin hoặc security matcher bị mở rộng ngoài phê duyệt.
- TLS verification hoặc secure cookie bị tắt.
- Public storage/bucket chứa artifact nhạy cảm.
- Security filter/authorization policy bị disable.

Mọi ngoại lệ cần owner, lý do, phạm vi và thời hạn. Không để exception vận hành tồn tại vô thời hạn mà không review.

## 8. Logging chi tiết mà không bật verbose error cho client

Tắt verbose error ở public response không có nghĩa là mất khả năng debug. Cần tách rõ hai kênh:

- **Client response:** mã lỗi, thông điệp an toàn, field công khai cần sửa và trace ID.
- **Internal telemetry:** exception type, stack trace, service, endpoint, correlation ID và ngữ cảnh đã redact để điều tra.

Log nội bộ vẫn cần data minimization. Không ghi access token, refresh token, API key, password, private key, cookie hoặc toàn bộ request body. Dùng structured logging, giới hạn quyền đọc, retention rõ và giám sát truy cập log.

### 8.1. Correlation ID

Mỗi request nên có request/correlation ID do hệ thống tạo hoặc xác minh. Nếu nhận ID từ client, giới hạn format/length và tránh cho client giả mạo ID của request khác. Trả trace ID trong response giúp support tìm log, nhưng không được để endpoint tra cứu log chỉ dựa trên trace ID mà không có authorization.

### 8.2. Không log toàn bộ configuration

Một số startup diagnostic in toàn bộ properties, environment hoặc request headers. Đây là cách dễ làm lộ secret. Hãy dùng allowlist property có thể log và redact theo tên/nguồn dữ liệu; tốt nhất không log giá trị secret ngay cả khi đã mask một phần.

### 8.3. Bảo vệ log

Log cần được gửi đến nơi lưu trữ có quyền truy cập hạn chế, chống sửa/xóa ngoài quyền và có retention phù hợp. Nhân viên có quyền deploy không mặc nhiên cần quyền đọc mọi dữ liệu audit hoặc log chứa thông tin cá nhân. Truy cập log nhạy cảm cũng nên được audit.

## 9. Checklist hardening cho Spring Boot API

Một baseline tham khảo cho production:

```yaml
server:
  error:
    include-exception: false
    include-message: never
    include-binding-errors: never
    include-stacktrace: never

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
```

Đây chỉ là ví dụ minh họa và cần rà soát theo phiên bản Spring Boot, Actuator và nhu cầu vận hành. Không cấu hình remote devtools trong production; tốt hơn là không đóng gói/bật remote development capability ở môi trường đó. Việc chỉ giới hạn actuator exposure không thay authentication/network policy.

Checklist thực tế:

- Tắt debug mode, remote debugger, devtools remote và interactive console ở production.
- Không expose stack trace, exception message hoặc binding detail ra public API.
- Không có default admin/demo account hoặc credential mẫu còn hoạt động.
- Secret được cấp riêng theo môi trường/workload từ secret manager hoặc nguồn tin cậy.
- Không có secret trong source, image, build artifact, public storage hoặc log.
- Startup guard phát hiện profile/config không an toàn và fail fast khi cần.
- Actuator/management endpoints chỉ expose phần cần thiết, có authentication/authorization và network restriction.
- Security matcher deny-by-default; method/object authorization được bật và kiểm thử.
- CORS chỉ cho phép origin/method/header cần thiết.
- TLS verification và cookie security được bật theo threat model.
- Error response dùng schema công khai ổn định; không forward raw upstream/database exception.
- Log chi tiết được bảo vệ, redact secret và có correlation ID.
- Có drift detection, audit thay đổi cấu hình và quy trình emergency access có thời hạn.

## 10. Kiểm thử default credential, debug mode và verbose error

Không chỉ review file cấu hình. Cần kiểm tra ứng dụng sau khi khởi động trong từng môi trường, qua đúng listener/gateway mà người dùng có thể truy cập.

| Nhóm kiểm thử | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Default credential | Thử credential mẫu trong môi trường test được phép; kiểm tra bootstrap account | Credential mẫu bị từ chối hoặc không tồn tại trong production |
| Credential riêng | Kiểm tra mỗi env/workload dùng secret riêng | Không tái sử dụng secret dev/staging/production |
| Secret source | Kiểm tra artifact, image, repository và log bằng secret sentinel | Không có secret thật trong artifact/log |
| Debug page | Gửi request gây lỗi có kiểm soát | Không có stack trace, source path hoặc variable dump |
| Remote debugger | Kiểm tra port/listener từ network zone không được phép | Không thể truy cập production debugger |
| Actuator | Thử truy cập từng endpoint từ public và management network | Chỉ endpoint được duyệt, caller có quyền phù hợp |
| Error response | Gửi input sai, gây validation/parse/database error trong test | Chỉ có public code/message, không có SQL/path/class/secret |
| Upstream failure | Mock provider trả body lỗi chứa sentinel secret | API không forward raw body |
| Authorization fallback | Gọi endpoint admin chưa khai báo permission | Bị deny-by-default |
| Profile | Khởi động với profile thiếu hoặc sai | Fail fast hoặc disable feature theo policy; không fallback insecure |
| Config precedence | Override property qua env/command line trong test | Guard phát hiện giá trị production không an toàn |
| CORS/TLS/cookie | Kiểm tra response header và browser flow | Không có wildcard/credential misconfiguration; TLS và cookie phù hợp |
| Logging | Gửi token/password giả rồi kiểm tra log test | Không ghi secret hoặc raw request nhạy cảm |
| Drift | Thay đổi cấu hình sau deploy trong môi trường test | Alert/policy check phát hiện thay đổi trái phép |

### 10.1. Dùng sentinel để tìm rò rỉ

Trong test, dùng chuỗi giả có thể nhận diện, ví dụ `MISCONFIG_TEST_SECRET_7F31`. Gửi nó trong field nhạy cảm hoặc cấu hình test, sau đó kiểm tra response, log, diagnostic output và artifact. Nếu sentinel xuất hiện ở nơi không được phép, test phải fail.

Không dùng secret production thật làm dữ liệu thử. Test cần chạy trong môi trường cô lập, không gọi dịch vụ ngoài hoặc hệ thống thật ngoài phạm vi được phép.

### 10.2. Kiểm tra bằng quyền của caller thực tế

Một actuator endpoint có thể bị chặn từ Internet nhưng lại mở cho mọi service account trong mạng nội bộ. Test cần dùng nhiều identity: anonymous, user thường, service account, tenant admin, platform operator. Xác minh quyền theo endpoint/action và không dựa vào vị trí mạng duy nhất.

### 10.3. Kiểm tra sau deployment

Thực hiện smoke test từ góc nhìn bên ngoài và từ management network. Xác minh debug endpoint không lộ, error response an toàn, default credential không dùng được, actuator chỉ expose đúng phần và log pipeline không nhận secret. Lưu kết quả theo release để so sánh drift giữa các lần triển khai.

## 11. Giám sát và xử lý sự cố

Theo dõi các dấu hiệu:

- Đăng nhập thành công bằng tài khoản bootstrap hoặc credential có tên/nguồn mẫu.
- Nhiều lần thử credential phổ biến hoặc một credential dùng từ nhiều nguồn bất thường.
- Request truy cập debug, actuator, env/config, heap dump hoặc remote management port.
- Error response chứa trường bất thường hoặc kích thước response tăng đột biến.
- Log xuất hiện token, password, API key hoặc secret sentinel.
- Production profile thay đổi, debug/log level bị bật hoặc security matcher bị sửa.
- Secret được đọc bởi workload không nằm trong allowlist.
- Management endpoint được expose ra public listener hoặc network mới.

Khi phát hiện credential mặc định hoặc secret bị lộ:

1. Xác định credential, workload, môi trường và phạm vi quyền bị ảnh hưởng.
2. Thu hồi/rotate credential; không chỉ đổi username hoặc ẩn endpoint.
3. Vô hiệu hóa tài khoản bootstrap hoặc debug capability không cần thiết.
4. Kiểm tra access/audit log để tìm hoạt động đã xảy ra trong khoảng thời gian phơi lộ.
5. Đánh giá secret khác có thể bị lộ qua cùng log, dump hoặc image.
6. Sửa nguồn cấu hình và thêm guard/test để lỗi không quay lại ở lần deploy sau.
7. Ghi nhận incident, owner, thời điểm thu hồi và bằng chứng xác minh.

Nếu verbose error đã làm lộ secret, cần coi secret đó là đã bị compromise và rotate theo mức độ ảnh hưởng. Xóa response khỏi log hoặc cache không làm credential đã lộ trở nên an toàn trở lại.

## 12. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Giữ admin/password mặc định | Attacker có thể đăng nhập bằng thông tin công khai | Bootstrap credential riêng, bắt buộc setup và revoke |
| Dùng secret chung giữa môi trường | Lộ một môi trường ảnh hưởng môi trường khác | Secret riêng theo env/workload |
| Hard-code signing key hoặc API key | Secret tồn tại trong source/image/history | Secret manager, rotation và secret scanning |
| Bật debug để dễ support production | Lộ state, stack trace hoặc cổng điều khiển | Debug off; diagnostic access có thời hạn và audit |
| Expose actuator toàn bộ | Lộ config/metrics hoặc thao tác quản trị | Allowlist endpoint và bảo vệ management plane |
| Trả exception message/stack trace | Lộ implementation và dữ liệu | Public error contract, log nội bộ đã redact |
| Dùng profile dev trong production | Kích hoạt sample data và security rule yếu | Explicit production profile và startup guard |
| Chỉ review file config, không xem runtime | Env/Helm/config server override giá trị | Kiểm tra effective config và drift |
| Tin mạng nội bộ là đủ bảo vệ | Caller nội bộ bị xâm nhập có thể gọi admin endpoint | Authentication/authorization tại service |
| Chỉ ẩn endpoint hoặc đổi URL | Không ngăn truy cập trực tiếp | Access control và network policy thực sự |
| Tắt TLS verification để sửa lỗi | Cho phép MITM và credential interception | Sửa trust store/certificate chain đúng cách |

## 13. Checklist review cuối cùng

- [ ] Không có default username/password, demo account hoặc API key mẫu trong production.
- [ ] Bootstrap flow tạo credential duy nhất, có thời hạn và được thu hồi sau setup.
- [ ] Secret được lưu ở nguồn phù hợp, không nằm trong source, image, artifact hoặc log.
- [ ] Credential tách biệt theo môi trường, tenant và workload; có rotation/revoke.
- [ ] Debug mode, remote debugger, devtools remote và interactive console bị tắt ở production.
- [ ] Verbose error, stack trace và exception detail không xuất hiện trong public response.
- [ ] Error response dùng public code ổn định và trace ID không có quyền truy cập ngầm.
- [ ] Actuator/management endpoint được allowlist, authenticate, authorize và giới hạn network.
- [ ] Production profile được xác định rõ; startup fail fast khi cấu hình bảo mật bắt buộc thiếu/sai.
- [ ] Effective configuration và configuration drift được kiểm tra sau deploy.
- [ ] Authorization endpoint/method/object dùng deny-by-default và có test thực tế.
- [ ] CORS, TLS, cookie, static file và security header được review.
- [ ] Log nội bộ có structured fields, redaction, access control, retention và audit.
- [ ] Có test default credential, debug exposure, verbose error, secret leakage và actuator access.
- [ ] Có alert và runbook cho credential lộ, debug bật nhầm và config drift.

Default credential, debug mode và verbose error đều bắt nguồn từ những lựa chọn tiện lợi trong phát triển hoặc vận hành. Khi production dùng secret riêng, bootstrap có vòng đời, debug capability bị tắt hoặc giới hạn, error response theo hợp đồng công khai và cấu hình runtime được kiểm tra liên tục, các lỗi cấu hình khó có thể vô hiệu hóa những lớp bảo vệ API còn lại. Việc hardening cần được xác minh sau mỗi deployment và gắn với quy trình quản lý thay đổi, thay vì chỉ dựa vào một file cấu hình mẫu.

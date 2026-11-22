# Environment parity và configuration validation

Một API có thể hoạt động an toàn trong staging nhưng lại mở endpoint quản trị ở production, chấp nhận issuer JWT khác dự kiến hoặc bỏ qua kiểm tra TLS khi kết nối tới service nội bộ. Nguyên nhân thường không nằm ở code nghiệp vụ mà ở cấu hình, topology hoặc khác biệt giữa các môi trường triển khai. Nếu staging không mô phỏng đủ các ranh giới bảo mật của production, kết quả kiểm thử ở staging không phản ánh đáng tin cậy hành vi thực tế.

**Environment parity** là mức độ tương đương có chủ đích giữa các môi trường phát triển, kiểm thử, staging và production đối với những thuộc tính có ảnh hưởng tới hành vi ứng dụng. Với API Security, parity cần bao phủ authentication, authorization, TLS, network exposure, secret handling, gateway, rate limit, logging, dependency và cách cấu hình được nạp. Parity không có nghĩa mọi môi trường phải dùng chung dữ liệu, credential, tài khoản hoặc tài nguyên.

**Configuration validation** là quá trình xác minh cấu hình có đầy đủ, đúng kiểu, nằm trong giới hạn được phép và phù hợp với môi trường trước khi ứng dụng phục vụ request. Cấu hình thiếu issuer, bật debug ở production, cho phép wildcard CORS hoặc tắt certificate validation phải làm deployment thất bại hoặc bị chặn theo policy, thay vì âm thầm dùng giá trị mặc định nguy hiểm.

Trong API Security, code chỉ là một phần của security control. Cùng một binary có thể có hành vi rất khác khi profile, environment variable, secret, ingress, gateway policy hoặc service identity thay đổi. Bài học này trình bày cách thiết kế parity, xác thực cấu hình, phát hiện drift và kiểm thử cấu hình runtime để bảo đảm mỗi môi trường có mức bảo vệ phù hợp.

Sau bài học, người đọc có thể:

- Phân biệt environment parity với việc sao chép toàn bộ production sang staging.
- Xác định các security invariant cần được giữ giữa các môi trường.
- Quản lý khác biệt có chủ đích về dữ liệu, credential, endpoint và quyền truy cập.
- Thiết kế schema cấu hình có kiểu, giới hạn và validation fail-fast.
- Kiểm tra Spring Boot configuration, Kubernetes manifests, ingress và secret references.
- Phát hiện cấu hình nguy hiểm như debug mode, wildcard origin, trust-all TLS và anonymous endpoint ngoài dự kiến.
- Phát hiện configuration drift giữa khai báo, deployment và runtime.
- Tích hợp configuration validation vào CI/CD và kiểm thử sau deploy.

## 1. Environment parity trong API Security là gì?

Một ứng dụng thường chạy ở nhiều môi trường:

- Local development: developer chạy ứng dụng trên máy cá nhân.
- Development/shared dev: môi trường tích hợp code đang phát triển.
- Test/QA: môi trường chạy test tự động và kiểm thử chức năng.
- Staging/pre-production: môi trường diễn tập release với topology gần production.
- Production: môi trường phục vụ người dùng và dữ liệu thật.

Mỗi môi trường có mục đích khác nhau nên không cần giống nhau ở mọi chi tiết. Tuy nhiên, những khác biệt ảnh hưởng đến quyết định bảo mật phải được nhận diện, kiểm soát và kiểm thử.

Ví dụ, production và staging có thể dùng database khác nhau, domain khác nhau, keypair khác nhau và dữ liệu khác nhau. Nhưng cả hai cần xác minh JWT signature, issuer và audience; kiểm tra object/tenant authorization; áp dụng TLS verification; giới hạn request body; và bảo vệ endpoint quản trị. Nếu staging tắt authorization để thuận tiện test, kết quả test không còn phản ánh policy production.

### 1.1. Parity là tương đương hành vi bảo mật

Nên xác định parity theo từng nhóm:

| Nhóm | Điều cần tương đương | Điều có thể khác theo môi trường |
|---|---|---|
| Authentication | Cùng cơ chế verify, issuer/audience policy và expiry rules | Test issuer, test key, tenant và client registration riêng |
| Authorization | Cùng policy function/object/property/tenant | Test users, fixture và dữ liệu khác |
| TLS | Verification luôn bật; protocol/cipher policy đạt baseline | Certificate, hostname và CA bundle phù hợp từng domain |
| Network | Trust boundary và nguyên tắc least privilege | CIDR, subnet, firewall rule theo topology |
| API Gateway | Auth, rate limit, request size và route policy | Hostname, quota test và backend target |
| CORS | Cùng nguyên tắc allowlist và credential policy | Origin riêng cho local, staging và production |
| Secrets | Không hard-code; least privilege; rotation | Secret value và secret reference riêng |
| Logging | Cùng schema, redaction và event semantics | Sink, retention và sampling theo môi trường |
| Resource limits | Có giới hạn và hành vi khi vượt giới hạn | Ngưỡng được điều chỉnh theo capacity đã đo |
| Dependencies | Cùng contract và security requirements | Test service/sandbox thay provider production |

Parity cần được mô tả bằng các invariant có thể kiểm tra. Ví dụ: mọi endpoint chứa dữ liệu riêng tư đều phải yêu cầu authentication; mọi truy cập object phải kiểm tra tenant; mọi outbound TLS connection phải xác minh certificate; không environment nào được dùng trust-all certificate manager.

### 1.2. Không đồng nhất parity với cùng cấu hình tuyệt đối

Sao chép nguyên production config sang staging có thể gây rủi ro:

- Staging dùng nhầm production database hoặc gửi email/SMS thật.
- Credential production bị đưa vào CI log hoặc test runner.
- Staging có quyền truy cập dữ liệu khách hàng thật không cần thiết.
- Callback hoặc webhook staging gửi sự kiện sang hệ thống production.
- Autoscaling, quota và resource allocation không phù hợp tải test.

Mục tiêu là giữ security invariant và mô phỏng hành vi, trong khi tách riêng secret, data, identity, destination và quyền truy cập. Khác biệt nào có thể ảnh hưởng security phải được ghi thành exception có owner, lý do và test bù.

## 2. Vì sao khác biệt môi trường tạo ra lỗ hổng?

Một số lỗi thường chỉ xuất hiện sau deploy:

### 2.1. Authentication policy khác nhau

Staging có thể dùng mock identity provider hoặc chấp nhận token test quá rộng. Production có thể dùng issuer riêng nhưng cấu hình audience bị bỏ trống. Một profile vô tình tắt JWT validator hoặc cho phép anonymous để test UI có thể được đóng gói vào release.

### 2.2. Authorization chỉ được kiểm tra ở một lớp

Staging đi qua API Gateway có policy, còn production service có thể được truy cập trực tiếp qua load balancer. Nếu authorization chỉ đặt tại gateway, đường bypass có thể bỏ qua kiểm soát. Ngược lại, một gateway rule khác nhau giữa staging và production có thể khiến test không phát hiện endpoint production bị mở.

### 2.3. TLS bị nới lỏng trong môi trường test

Developer có thể thêm trust-all certificate manager để gọi service có certificate tự ký. Nếu code này được dùng ở production, attacker có thể giả mạo downstream service. Cần kiểm tra cả outbound HTTP client và inbound TLS termination.

### 2.4. CORS và cookie khác nhau

Staging có thể cho phép mọi origin hoặc bật credential rộng để frontend test thuận tiện. Nếu cấu hình này đi vào production, origin không tin cậy có thể đọc response trong browser theo điều kiện phù hợp. Cookie domain, SameSite và Secure cũng có thể khác khiến hành vi authentication không được test đúng.

### 2.5. Secret và service identity dùng chung

Chia sẻ API key, database password hoặc signing key giữa staging và production làm tăng phạm vi ảnh hưởng khi một môi trường bị xâm nhập. Test runner hoặc developer workstation có thể trở thành đường truy cập vào production.

### 2.6. Gateway, network và resource controls khác nhau

Staging có thể không bật WAF, request size limit, rate limit hoặc timeout giống production. Một endpoint upload hoặc export có thể vượt qua test chức năng nhưng làm cạn tài nguyên production. Internal API có thể bị expose do ingress annotation hoặc firewall rule sai.

### 2.7. Logging và monitoring không đồng nhất

Staging có thể ghi payload để debug, production redaction khác; hoặc production không phát security event vì logging config không được nạp. Một kiểm thử bảo mật chỉ hữu ích nếu event, alert và audit path thực tế hoạt động.

## 3. Xây dựng security invariants cho mọi môi trường

Thay vì chỉ so sánh file cấu hình, hãy định nghĩa các điều kiện bảo mật mà mọi môi trường phải đáp ứng.

Ví dụ:

| Invariant | Điều kiện kiểm tra |
|---|---|
| Token verification | Không chấp nhận token thiếu/sai chữ ký, sai issuer hoặc audience |
| Account state | User disabled/locked không thể xác thực |
| Object authorization | Không đọc/sửa object ngoài owner/tenant scope |
| Property filtering | Không cho client ghi field nhạy cảm ngoài allowlist |
| TLS | Certificate chain và hostname luôn được xác minh |
| CORS | Chỉ origin đã đăng ký được đọc response; credential không đi với wildcard |
| Secrets | Không có secret plaintext trong source, image hoặc manifest |
| Admin exposure | Management endpoint chỉ nằm trong network/identity boundary được phép |
| Resource controls | Body size, pagination, timeout, concurrency và quota có giới hạn |
| File handling | File chưa scan không thể download/preview/forward |
| Webhook | Signature, timestamp và replay protection luôn được kiểm tra |
| Logging | Token/password/cookie không xuất hiện trong log hoặc trace |

Mỗi invariant cần có:

- Owner chịu trách nhiệm.
- Nguồn cấu hình hoặc code thực thi.
- Cách kiểm tra tự động.
- Environment áp dụng.
- Mức độ nghiêm trọng nếu vi phạm.
- Exception có thời hạn nếu thực sự cần.

### 3.1. Security baseline và environment overlay

Có thể chia cấu hình thành hai lớp:

1. **Security baseline:** các quy tắc không được nới lỏng theo môi trường, ví dụ JWT validation, TLS verification, authorization enforcement và secret redaction.
2. **Environment overlay:** giá trị riêng cho môi trường, ví dụ hostname, issuer test, database URL, storage bucket, quota và log sink.

Overlay không được phép vô hiệu hóa baseline. Nếu cần một khác biệt như test endpoint không yêu cầu login, phải giới hạn trong test fixture/profile riêng, không nằm trong artifact hoặc profile production.

## 4. Quản lý cấu hình theo schema có kiểu

Configuration validation bắt đầu từ việc xác định cấu hình nào bắt buộc, kiểu dữ liệu gì, giá trị hợp lệ ra sao và phụ thuộc với trường khác như thế nào.

Một schema nên mô tả:

- Required/optional.
- Data type và format.
- Allowed values/range.
- Default có an toàn hay không.
- Environment scope.
- Secret hay non-secret.
- Dependency giữa các field.
- Validation rule.
- Owner và version.

Ví dụ một phần cấu hình API security:

~~~yaml
security:
  jwt:
    enabled: true
    issuer: https://identity.example.test
    audience: order-api
    jwksUri: https://identity.example.test/.well-known/jwks.json
    clockSkew: 30s
  cors:
    allowedOrigins:
      - https://app.example.test
    allowCredentials: true
  tls:
    verifyCertificates: true
  request:
    maxBodyBytes: 1048576
    timeout: 5s
~~~

Đây là ví dụ cấu trúc, không phải giá trị dùng chung cho mọi ứng dụng. Hostname, audience, body limit và timeout phải được xác định theo service contract. Không đặt secret trực tiếp trong YAML được commit vào repository.

### 4.1. Không dùng default nguy hiểm

Các default như sau thường tạo ra fail-open:

- Nếu thiếu issuer thì bỏ qua issuer validation.
- Nếu không có allowed origins thì cho phép mọi origin.
- Nếu thiếu TLS setting thì trust mọi certificate.
- Nếu không có rate limit thì dùng unlimited.
- Nếu không có authentication config thì cho phép anonymous.
- Nếu thiếu secret thì dùng một chuỗi mặc định.

Với security-critical configuration, thiếu giá trị phải làm startup/deployment thất bại. Default chỉ nên dùng khi nó an toàn, rõ ràng và phù hợp mọi môi trường liên quan.

### 4.2. Phân biệt unset, empty và disabled

Không coi ba trạng thái này là một:

- **Unset:** cấu hình không được cung cấp.
- **Empty:** có cấu hình nhưng giá trị rỗng.
- **Disabled:** có chủ đích tắt tính năng.

Ví dụ allowedOrigins rỗng có thể có nghĩa không cho phép cross-origin, không nhất thiết là cho phép mọi origin. jwt.enabled=false phải là trạng thái explicit và có thể chỉ hợp lệ trong một test profile cô lập. Schema cần định nghĩa ý nghĩa từng trạng thái.

## 5. Validation fail-fast và fail-closed

Có hai thời điểm kiểm tra:

- **Startup/deployment validation:** kiểm tra cấu hình trước khi nhận traffic.
- **Runtime validation:** kiểm tra input và trạng thái động trong từng request hoặc khi cấu hình được reload.

Security configuration sai phải được phát hiện sớm. Ví dụ:

- Production thiếu issuer/audience: không khởi động hoặc không pass deployment gate.
- CORS bật credential với wildcard origin: cấu hình không hợp lệ.
- TLS verification bị tắt trong production: deployment bị chặn.
- Management endpoint expose public ngoài policy: manifest validation thất bại.
- Secret reference không tồn tại hoặc workload không đọc được: readiness không đạt.

Fail-fast giúp lỗi cấu hình xuất hiện ở deploy thay vì khi người dùng thực hiện giao dịch. Fail-closed nghĩa là khi không thể xác minh credential, policy hoặc dependency bảo mật, hệ thống không tự cấp quyền.

Không nên biến mọi lỗi dependency thành startup failure nếu service có khả năng chạy an toàn ở chế độ degraded. Cần phân loại: nếu thiếu key xác minh JWT thì không thể nhận request protected; nếu telemetry sink tạm thời lỗi, có thể giữ request theo policy nhưng phải có buffer/alert và không làm mất audit bắt buộc. Hành vi degraded phải được định nghĩa trước.

### 5.1. Validation cross-field

Một field riêng lẻ có thể hợp lệ nhưng tổ hợp lại nguy hiểm:

- allowCredentials=true cùng wildcard CORS origin.
- jwt.enabled=true nhưng issuer hoặc audience rỗng.
- tls.verifyCertificates=false trong production.
- management.endpoints.web.exposure.include=* trên public interface.
- debug=true trong production.
- cookie.secure=false khi cookie session dùng trên HTTPS production.
- rateLimit.enabled=false cho endpoint export hoặc login.

Schema cần hỗ trợ validation quan hệ giữa các field, không chỉ kiểm tra kiểu.

## 6. Spring Boot: bind và validate configuration

Spring Boot hỗ trợ bind cấu hình vào object có kiểu và xác thực bằng Jakarta Bean Validation. Điều này giúp tránh đọc chuỗi tùy ý ở nhiều nơi trong code.

Ví dụ:

~~~java
@Validated
@ConfigurationProperties(prefix = "security.jwt")
public record JwtSecurityProperties(
        @NotBlank String issuer,
        @NotBlank String audience,
        @NotNull URI jwksUri,
        @NotNull Duration clockSkew
) {
    @AssertTrue(message = "clockSkew must be between 0 and 2 minutes")
    public boolean isClockSkewAllowed() {
        return clockSkew != null
                && !clockSkew.isNegative()
                && clockSkew.compareTo(Duration.ofMinutes(2)) <= 0;
    }
}
~~~

Đăng ký properties:

~~~java
@Configuration
@EnableConfigurationProperties(JwtSecurityProperties.class)
class SecurityConfiguration {
}
~~~

Ứng dụng sẽ báo lỗi binding/validation khi cấu hình thiếu hoặc không hợp lệ, thay vì để service chạy với giá trị không xác định. Cần bảo đảm validation starter và cấu hình properties được bật đúng trong project.

### 6.1. Validate URL và environment

@NotNull URI chỉ bảo đảm field có giá trị parse được; chưa bảo đảm URL an toàn. Cần kiểm tra:

- Scheme là HTTPS trong production.
- Host nằm trong danh sách identity provider được phê duyệt.
- Không chứa userinfo hoặc fragment không cần thiết.
- Không trỏ tới localhost, link-local hoặc metadata endpoint ngoài policy.
- DNS/egress policy giới hạn kết nối runtime tới destination được phép.

Không chỉ kiểm tra hostname lúc startup nếu DNS có thể thay đổi; network egress và outbound client cần bảo vệ thêm. Với endpoint do client cung cấp, áp dụng SSRF defense riêng; không dùng cùng validation đơn giản của config trusted.

### 6.2. Conditional validation theo môi trường

Một số giá trị chỉ bắt buộc ở production. Có thể dùng validator tùy chỉnh hoặc validation group để biểu đạt rõ:

- Production bắt buộc issuer thật đã phê duyệt, TLS verification và secure cookie.
- Local có thể dùng issuer test và HTTP loopback, nhưng chỉ trong profile local.
- CI test có thể dùng JWKS server giả lập và test key.
- Staging dùng domain và secret riêng, nhưng giữ cùng validation chain.

Tránh nhúng điều kiện profile rải rác khắp service. Tập trung policy theo environment và kiểm tra cả cấu hình đã bind lẫn effective configuration.

### 6.3. Không log secret khi validation thất bại

Configuration binding error có thể in giá trị property. Với secret hoặc URI chứa credential, không đưa value vào exception/log. Log tên property, nguồn cấu hình và reason code; che giá trị. Không đặt token, password hoặc private key trong property name hay command line argument.

## 7. Quản lý profile và precedence cấu hình

Spring Boot có thể nạp cấu hình từ nhiều nguồn: file mặc định, profile-specific file, environment variable, system property, command line, config tree hoặc external config provider. Giá trị cuối cùng phụ thuộc precedence.

Rủi ro xuất hiện khi:

- Một biến môi trường ghi đè giá trị an toàn bằng giá trị yếu.
- Profile production và staging cùng được kích hoạt ngoài ý muốn.
- File cấu hình cũ còn nằm trong image và được nạp trước/sau nguồn khác.
- Config server trả version không đồng bộ giữa các instance.
- Một property được khai báo ở nhiều nguồn mà không ai biết giá trị effective.

### 7.1. Profile không phải security boundary

Profile giúp chọn cấu hình, nhưng không tự bảo đảm môi trường an toàn. Không coi việc profile tên prod là bằng chứng mọi giá trị production đã được áp dụng. Cần kiểm tra:

- Profile active thực tế.
- Property source và precedence.
- Effective value của security-critical fields.
- Không có profile test/debug cùng active trong production.
- Không có endpoint hoặc bean chỉ bị disable bởi một điều kiện cấu hình có thể bị override.

### 7.2. Không đặt secret trong profile file

File cấu hình có thể chứa reference tới secret store hoặc config tree, nhưng không nên commit secret thật. Ví dụ:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Tên và cách mount secret phụ thuộc deployment. Với secret bắt buộc cho authentication hoặc ký webhook, không dùng optional nếu việc thiếu secret khiến service không thể hoạt động an toàn. Kiểm tra quyền filesystem và secret volume; không expose mount vào container không cần truy cập.

## 8. Secrets, keys và identity phải tách theo môi trường

Mỗi môi trường cần credential riêng cho:

- JWT signing/verification key nếu service tự phát hành token.
- API key và client secret.
- Database user/password.
- Webhook signing secret.
- mTLS private key/certificate.
- Cloud workload identity và storage credentials.
- Encryption key và key-encryption key.

Không dùng chung secret production với staging, local hoặc CI. Nếu staging bị xâm nhập, attacker không được dùng secret staging để xác thực với production hoặc giải mã dữ liệu production.

### 8.1. Phân biệt key ký và key xác minh

Resource server thường chỉ cần public key để xác minh JWT asymmetric; không cần giữ private signing key của identity provider. Hạn chế lưu private key ở service không có trách nhiệm ký. Với HMAC, shared secret phải được giới hạn đúng provider/service và có kế hoạch rotation.

### 8.2. Secret reference và rotation

Configuration nên tham chiếu tới secret manager hoặc mounted secret, không ghi giá trị secret vào manifest. Mỗi secret cần:

- Owner và mục đích sử dụng.
- Scope/environment.
- Quyền đọc tối thiểu cho workload.
- Rotation/revocation process.
- Thời hạn và alert trước expiry nếu áp dụng.
- Audit access và thay đổi.

Khi rotation, cần xác định overlap hợp lệ, cập nhật verifier/key cache và thu hồi key cũ. Test rotation trong staging bằng keypair riêng trước khi áp dụng production.

### 8.3. Không để secret xuất hiện trong build artifact

Không truyền secret production qua Docker build ARG, image layer, source map, test report hoặc CI artifact. Build artifact nên bất biến và không chứa credential theo environment; runtime inject secret từ hệ thống quản lý được bảo vệ.

## 9. Network, ingress và TLS parity

API security phụ thuộc cách traffic đi vào và đi ra service. Cần kiểm tra:

- Public/private ingress và host routing.
- Gateway authentication, rate limit, body limit và timeout.
- Network policy, security group và firewall.
- Service mesh/mTLS identity.
- Outbound egress và DNS.
- TLS termination và forwarded header trust.
- Direct service exposure có bypass gateway hay không.

### 9.1. Inbound TLS

Production và staging cần baseline TLS tương đương: HTTPS, certificate chain hợp lệ, hostname verification và protocol/cipher policy theo chuẩn tổ chức. Certificate có thể khác theo hostname/môi trường; hành vi xác minh không được khác.

Nếu TLS terminate tại load balancer, cần kiểm tra đoạn từ load balancer tới service. Network nội bộ không tự động đáng tin. Dùng mTLS hoặc cơ chế bảo vệ tương ứng khi threat model yêu cầu.

### 9.2. Outbound TLS

Không dùng trust-all TrustManager, hostname verifier luôn trả true hoặc tắt certificate validation trong profile test rồi để cấu hình đó lọt vào production. Test client phải dùng test CA/certificate hợp lệ. Nếu cần trust private CA, cài CA cụ thể thay vì trust mọi certificate.

### 9.3. Forwarded headers

Chỉ tin Forwarded, X-Forwarded-For, X-Forwarded-Host và X-Forwarded-Proto từ proxy đã xác thực. Proxy cần xóa giá trị client gửi rồi ghi lại. Khác biệt proxy configuration giữa staging và production có thể làm sai scheme/host, ảnh hưởng redirect, secure cookie, origin checks và canonical signature verification.

## 10. CORS, cookie và browser security theo môi trường

Origin frontend thường khác nhau:

| Environment | Frontend origin mẫu | API host mẫu |
|---|---|---|
| Local | http://localhost:3000 | http://localhost:8080 |
| Development | https://dev-app.example.test | https://dev-api.example.test |
| Staging | https://staging-app.example.test | https://staging-api.example.test |
| Production | https://app.example.com | https://api.example.com |

Các giá trị chỉ là minh họa. Mỗi origin cần được allowlist rõ ràng. Không dùng wildcard production để tránh phải cập nhật origin khi deploy.

Kiểm tra:

- Production không nhận origin development/staging trừ khi có yêu cầu rõ.
- allowCredentials=true không đi cùng wildcard origin.
- Cookie session có Secure, HttpOnly và SameSite phù hợp.
- Cookie domain không rộng hơn cần thiết.
- CSRF policy phù hợp authentication model.
- CORS preflight không bị chặn bởi authentication filter sai thứ tự.
- Error response và cache có Vary: Origin khi cần.

Không kiểm thử CORS chỉ bằng curl; dùng browser automation hoặc browser thật vì CORS là chính sách browser thực thi. Tuy vậy, server vẫn phải xác thực và phân quyền actual request.

## 11. Kubernetes và container configuration

Kubernetes manifest có thể làm thay đổi security posture dù application code không đổi. Cần validate:

- Namespace/environment mapping.
- Service type, Ingress và Gateway route.
- NetworkPolicy và egress.
- ServiceAccount và RBAC.
- Pod security context, non-root và read-only filesystem khi phù hợp.
- Secret/ConfigMap references.
- Resource requests/limits.
- Liveness/readiness/startup probes.
- Container image digest và provenance.
- Management port và actuator exposure.

### 11.1. Ví dụ Deployment an toàn hơn

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      serviceAccountName: order-api
      automountServiceAccountToken: false
      containers:
        - name: app
          image: registry.example.test/order-api@sha256:REPLACE_WITH_DIGEST
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: production
          envFrom:
            - secretRef:
                name: order-api-runtime
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
~~~

Đây là ví dụ minh họa; image digest, secret, port và resource values phải lấy từ release thực tế. Nếu ứng dụng cần ghi file tạm, mount writable volume riêng thay vì mở toàn bộ root filesystem. automountServiceAccountToken=false phù hợp khi workload không cần Kubernetes API; nếu cần, cấp RBAC tối thiểu và kiểm thử.

### 11.2. ConfigMap và Secret

ConfigMap dành cho cấu hình không bí mật; Secret dành cho dữ liệu nhạy cảm nhưng bản thân Kubernetes Secret không tự động bảo đảm mã hóa ở mọi cấu hình cluster. Cần cấu hình encryption at rest, RBAC, audit, secret management và giới hạn mount. Không commit secret thật trong YAML dù file được mã hóa base64.

Không mount toàn bộ secret namespace vào mọi pod. Chỉ cung cấp đúng key cần thiết. Tránh đưa secret vào environment nếu process dump/debug có thể làm lộ; chọn cơ chế injection phù hợp threat model và nền tảng.

### 11.3. NetworkPolicy và ingress parity

Kiểm tra staging có cùng nguyên tắc deny-by-default và chỉ mở các flow cần thiết. Một policy không chọn đúng pod label có thể không áp dụng. Kiểm tra cả ingress và egress; API có SSRF risk cần egress restrictions tới metadata service, loopback, private ranges và destination không được phép theo kiến trúc.

## 12. Kiểm tra cấu hình gateway và API management

Gateway thường thực hiện một số control tập trung, nhưng không nên là nơi duy nhất bảo vệ object-level authorization.

Kiểm tra:

- Route và method đúng scope.
- Authentication policy không bị disable ở production.
- Token issuer/audience được kiểm tra hoặc token được chuyển tới service theo trust contract.
- Rate limit/quota áp dụng cho login, search, export, upload và endpoint tốn tài nguyên.
- Body size, header size, timeout và connection limit.
- CORS allowlist và credential policy.
- WAF policy và exception có thời hạn.
- Request/response logging có redaction.
- Không có route trực tiếp tới backend bỏ qua gateway ngoài dự kiến.

Nếu gateway và service cùng thực hiện authentication, cần xác định trust model: service tự verify token hay tin identity header từ gateway. Header identity phải được gateway xóa/ghi đè và kết nối downstream phải được xác thực; không nhận header tương tự từ client trực tiếp.

## 13. Configuration drift: khai báo khác runtime

Configuration drift là sự sai lệch giữa cấu hình mong muốn và trạng thái thực tế. Drift có thể xuất hiện do:

- Hotfix thủ công trên cluster.
- Environment variable khác giá trị trong deployment manifest.
- Config server cập nhật một số instance nhưng không phải tất cả.
- Secret rotation không đồng bộ.
- Helm/Kustomize overlay hoặc template render sai.
- Manual ingress/firewall change.
- Một instance chạy image/config version cũ sau rollout.
- Default framework ghi đè property do binding hoặc precedence.

### 13.1. Ba lớp cần đối chiếu

| Lớp | Ví dụ | Câu hỏi |
|---|---|---|
| Desired state | Git manifest, Helm values, policy-as-code | Tổ chức muốn cấu hình nào? |
| Deployed state | Kubernetes live object, gateway config, secret reference | Hệ thống đã deploy gì? |
| Effective runtime state | Active profile, bound properties, actual TLS/CORS/auth behavior | Ứng dụng thực sự đang làm gì? |

Ba lớp phải được đối chiếu. Manifest đúng không chứng minh pod đang chạy đúng version; pod chạy đúng image không chứng minh environment variable effective đúng; property đúng không chứng minh gateway route không bypass service.

### 13.2. Không dump toàn bộ effective configuration

Khi điều tra drift, không xuất toàn bộ environment hoặc actuator config ra log/ticket nếu có secret. Dùng allowlist field không nhạy cảm, fingerprint cấu hình hoặc báo cáo validation chỉ chứa tên property, expected/observed category và nguồn. Secret nên được xác minh bằng metadata/version/reference, không in giá trị.

### 13.3. Phát hiện drift liên tục

Có thể dùng:

- GitOps reconciliation và policy-as-code.
- Kubernetes admission policy.
- Cloud configuration/compliance scanner.
- Config fingerprint/version được phát hành cùng artifact.
- Runtime health check cho security invariant.
- Alert khi profile, issuer, audience, CORS origin hoặc TLS mode thay đổi ngoài kế hoạch.
- Scheduled comparison giữa desired/deployed/runtime state.

Không chỉ phát hiện drift khi release. Thay đổi thủ công sau deploy có thể tạo lỗ hổng ngay cả khi pipeline ban đầu đã pass.

## 14. Configuration validation trong CI/CD

Validation nên chạy trước khi artifact được deploy và sau khi runtime sẵn sàng.

Một pipeline tham khảo:

~~~mermaid
flowchart TD
    A[Commit code và config] --> B[Schema và syntax validation]
    B --> C[Secret scanning và policy checks]
    C --> D[Render environment overlay]
    D --> E[Validate cross-field security invariants]
    E --> F[Build immutable artifact]
    F --> G[Deploy staging]
    G --> H[Runtime smoke/security tests]
    H --> I[Compare desired/deployed/effective config]
    I --> J{All gates pass?}
    J -->|No| K[Block release và tạo finding]
    J -->|Yes| L[Approval và progressive production rollout]
    L --> M[Post-deploy verification và drift monitoring]
~~~

### 14.1. Kiểm tra tĩnh

Trước deploy:

- YAML/JSON syntax và schema hợp lệ.
- Required property có mặt.
- URL/scheme/host nằm trong allowlist.
- Không có wildcard CORS không hợp lệ.
- Không tắt TLS verification.
- Không bật debug/actuator exposure ngoài policy.
- Không có secret plaintext hoặc private key trong repository/image.
- Kubernetes workload có security context và resource limits theo baseline.
- Ingress, service và network policy không mở port/route ngoài scope.

### 14.2. Kiểm tra sau deploy

Sau khi ứng dụng chạy:

- Readiness chỉ đạt khi security-critical configuration đã được load.
- Gửi request không token tới endpoint protected và xác minh bị từ chối.
- Gửi token test sai issuer/audience/signature và xác minh bị từ chối.
- Xác minh object cross-tenant bị chặn bằng fixture an toàn.
- Kiểm tra TLS handshake và hostname verification tới dependency test.
- Kiểm tra CORS bằng browser automation.
- Kiểm tra management endpoint không public.
- Kiểm tra request size/rate limit và security event logging.
- Xác minh không có pod/instance chạy config version cũ.

Không chỉ gọi health endpoint trả 200 rồi kết luận security configuration hợp lệ. Health check nên tách liveness và readiness; readiness cần phản ánh những điều kiện bắt buộc để phục vụ request an toàn.

## 15. Kiểm thử parity giữa các môi trường

Nên tạo một ma trận invariant theo môi trường:

| Security control | Local/dev | Test/QA | Staging | Production |
|---|---|---|---|---|
| JWT signature verification | Bật với test key | Bật với test key | Bật với staging issuer/key | Bật với production issuer/key |
| Issuer/audience validation | Giá trị test cố định | Giá trị test cố định | Giá trị staging | Giá trị production |
| Object/tenant authorization | Bật, fixture | Bật, fixture | Bật, test tenant | Bật, tenant thật |
| TLS verification | Bật; local CA được tin cụ thể | Bật | Bật | Bật |
| CORS | Local origin cụ thể | QA origin | Staging origin | Production origin |
| Secrets | Local dev secret riêng | CI/test secret | Staging secret riêng | Production secret riêng |
| Debug/management exposure | Local only theo kiểm soát | Private test network | Restricted | Restricted, không public mặc định |
| Rate/resource limit | Có giới hạn dev | Có giới hạn test | Gần production | Theo capacity production |
| Logging redaction | Bật | Bật | Bật | Bật |

Các giá trị không cần giống nhau; invariant và cách thực thi mới cần tương đương.

### 15.1. Test khác biệt có chủ đích

Mỗi khác biệt nên được mô tả:

- Tên property/control.
- Environment áp dụng.
- Giá trị hoặc policy khác biệt ở dạng không chứa secret.
- Lý do nghiệp vụ/kỹ thuật.
- Rủi ro phát sinh.
- Kiểm soát bù.
- Owner và ngày hết hạn review.
- Test chứng minh khác biệt không làm yếu security invariant.

Ví dụ: staging dùng test issuer riêng. Điều này hợp lệ nếu decoder vẫn xác minh signature, issuer, audience, expiry và key rotation như production; test key không được chấp nhận ở production.

### 15.2. Parity của dependency

Staging có thể dùng sandbox payment provider thay production provider. Tuy nhiên cần kiểm tra:

- TLS và certificate validation giống nhau.
- Authentication method và credential scope tương đương.
- Error, retry, timeout và webhook signature behavior được mô phỏng.
- Sandbox không gọi production callback hoặc sử dụng production secret.
- Contract/version của provider tương thích với production.

Một mock quá đơn giản có thể che giấu lỗi timeout, token audience, certificate chain hoặc retry. Dùng contract test và sandbox phù hợp; chỉ mock phần không cần xác minh tích hợp.

## 16. Runtime security validation và readiness

Runtime validation xác nhận ứng dụng đang phục vụ với cấu hình bảo mật đã mong đợi. Nên có hai nhóm kiểm tra:

- **Liveness:** process còn hoạt động và có thể tiếp tục chạy.
- **Readiness:** instance đã nạp cấu hình bắt buộc, kết nối dependency thiết yếu và sẵn sàng phục vụ traffic.

Không để readiness expose secret, issuer nội bộ hoặc cấu hình chi tiết. Response chỉ nên cung cấp trạng thái tổng quát và correlation ID; thông tin chi tiết nằm trong log có kiểm soát.

### 16.1. Kiểm tra cấu hình động

Nếu ứng dụng hỗ trợ reload config mà không restart, cần kiểm thử:

- Validation được chạy trước khi config mới có hiệu lực.
- Config không hợp lệ bị từ chối và config cũ an toàn được giữ lại hoặc instance ngừng nhận traffic theo policy.
- Không có trạng thái nửa cũ/nửa mới giữa các bean.
- Key rotation có overlap và revoke rõ ràng.
- Cache JWKS/authorization policy được refresh theo thời hạn.
- Audit ghi nhận ai/nguồn nào thay đổi cấu hình.

Không áp dụng config mới từng phần nếu điều đó có thể tạm thời tắt authentication hoặc mở CORS. Ưu tiên atomic configuration update hoặc rollout instance mới.

### 16.2. Runtime fingerprint

Có thể phát hành một config version/fingerprint không chứa secret để so sánh instance:

~~~json
{
  "configVersion": "2026.11.18.4",
  "imageDigest": "sha256:...",
  "activeProfiles": ["production"],
  "securityPolicyVersion": "api-baseline-7",
  "issuerId": "production-identity",
  "corsPolicyId": "prod-web-origins-v3",
  "tlsVerification": true
}
~~~

Không expose fingerprint này cho public endpoint nếu nó tiết lộ thông tin nội bộ. Dùng internal telemetry/attestation hoặc deployment controller để so sánh các instance. Không đưa secret value vào fingerprint; nếu cần xác minh secret rotation, dùng secret version ID từ secret manager.

## 17. Các cấu hình nguy hiểm cần phát hiện

| Cấu hình | Rủi ro | Kiểm tra |
|---|---|---|
| Debug/verbose errors bật ở production | Lộ stack trace, path, cấu hình | Validate profile và error response |
| JWT issuer/audience không bắt buộc | Chấp nhận token sai trust domain | Startup validation và negative token test |
| TLS trust-all | Man-in-the-middle tới downstream | Static scan và TLS integration test |
| CORS wildcard + credentials | Browser trust boundary sai | Cross-field validation và browser test |
| Anonymous matcher quá rộng | Endpoint riêng tư bị public | Endpoint inventory + unauthenticated smoke test |
| Actuator/management public | Lộ metrics/config hoặc thao tác quản trị | Ingress/network policy và route test |
| Secret default hoặc hard-code | Credential bị biết trước | Secret scan, config validation |
| Shared secret giữa env | Lateral movement giữa môi trường | Secret inventory và identity test |
| Network egress mở rộng | SSRF hoặc data exfiltration | Network policy và egress test |
| Rate limit tắt | Brute force/resource exhaustion | Gateway config và load-safe test |
| Request size unlimited | Memory/disk exhaustion | Static policy và boundary test |
| Log payload/token | Rò rỉ credential và PII | Log capture test |
| Config reload không validate | Runtime policy bị nới lỏng | Negative reload test |

## 18. Kiểm thử failure mode và rollout

Configuration validation phải được kiểm thử khi cấu hình sai hoặc dependency không sẵn sàng:

- Thiếu JWT issuer hoặc audience.
- JWKS endpoint không truy cập được.
- Certificate hết hạn hoặc hostname không khớp.
- Secret reference không tồn tại hoặc workload không có quyền đọc.
- ConfigMap/Secret version không đồng bộ.
- CORS origin sai format hoặc wildcard/credential conflict.
- Management exposure không đúng policy.
- NetworkPolicy chặn dependency thiết yếu.
- Runtime config reload chứa giá trị không hợp lệ.
- Một instance còn chạy image/config version cũ.

Kết quả mong đợi phải được xác định trước: deployment bị block, pod không ready, request protected bị từ chối hoặc instance được đưa khỏi load balancer. Không được âm thầm chuyển sang anonymous, trust-all hoặc unlimited.

### 18.1. Progressive rollout và rollback

Khi thay đổi security configuration:

1. Validate schema và policy trước deploy.
2. Deploy canary hoặc một nhóm instance nhỏ.
3. Chạy smoke test authentication, authorization, TLS và endpoint exposure.
4. So sánh effective config/version giữa các instance.
5. Theo dõi 401/403, TLS errors, gateway rejects, readiness và security events.
6. Mở rộng rollout khi invariant đạt.
7. Nếu sai, rollback về cấu hình đã biết an toàn; không rollback về bản có lỗ hổng đã được xác định.

Rollback secret/key cần đặc biệt cẩn thận: key cũ có thể đã bị revoke hoặc compromise. Không tự khôi phục credential đã thu hồi chỉ để làm service hoạt động lại.

## 19. Ví dụ CI policy checks

Một policy gate có thể kiểm tra rendered config trước khi deploy. Ví dụ logic minh họa:

~~~python
def validate_security_config(config, environment):
    errors = []

    jwt = config["security"]["jwt"]
    cors = config["security"]["cors"]
    tls = config["security"]["tls"]

    if not jwt.get("issuer") or not jwt.get("audience"):
        errors.append("JWT issuer and audience are required")

    if environment == "production":
        if tls.get("verifyCertificates") is not True:
            errors.append("TLS certificate verification must be enabled")

        if config.get("debug") is True:
            errors.append("Debug mode is forbidden in production")

        if cors.get("allowCredentials") is True:
            if "*" in cors.get("allowedOrigins", []):
                errors.append("Credentialed CORS cannot use wildcard origin")

    return errors
~~~

Đây là pseudocode để minh họa policy. Trong pipeline thực tế, cần schema validation, xử lý field thiếu/kiểu sai an toàn, kiểm tra mọi origin pattern, kiểm tra endpoint exposure và không in secret. Không dùng script này làm validator duy nhất cho production; policy nên được test và version hóa.

### 19.1. Policy test cases

| Input config | Kết quả mong đợi |
|---|---|
| Production thiếu issuer | Fail |
| Production thiếu audience | Fail |
| Production TLS verification false | Fail |
| Production debug true | Fail |
| Credentialed CORS với wildcard | Fail |
| Staging dùng test issuer đã allowlist | Pass |
| Staging dùng production secret reference | Fail theo separation policy |
| Secret reference không tồn tại | Fail readiness/deploy |
| Management route public ngoài scope | Fail |
| Rate limit không cấu hình cho login/export | Fail hoặc yêu cầu exception được phê duyệt |

## 20. Checklist trước khi release

- [ ] Security invariants giữa dev/test/staging/production đã được định nghĩa.
- [ ] Khác biệt môi trường có owner, lý do, rủi ro và ngày review.
- [ ] Staging giữ cùng logic authentication, authorization, TLS và logging như production.
- [ ] Dữ liệu, account, credential, key và destination được tách theo môi trường.
- [ ] Security-critical configuration có schema, kiểu và required validation.
- [ ] Thiếu issuer/audience/key hoặc policy bắt buộc làm deploy/readiness thất bại.
- [ ] Không có default fail-open như anonymous, trust-all, wildcard hoặc unlimited.
- [ ] Cross-field validation kiểm tra CORS credentials, TLS, debug và management exposure.
- [ ] Profile active và effective property source được xác minh.
- [ ] Secret không nằm trong source, image, manifest, command line hoặc CI artifact.
- [ ] Workload chỉ đọc secret cần thiết; rotation và revocation đã được diễn tập.
- [ ] Ingress, gateway, network policy và outbound egress được kiểm tra.
- [ ] Forwarded headers chỉ được tin từ proxy xác thực.
- [ ] Kubernetes RBAC, ServiceAccount, security context và resource limits đạt baseline.
- [ ] Desired, deployed và effective runtime configuration được đối chiếu.
- [ ] CI có static config/policy gates và post-deploy security smoke tests.
- [ ] Readiness không đạt khi security-critical config chưa hợp lệ.
- [ ] Có drift monitoring và alert cho thay đổi ngoài kế hoạch.
- [ ] Progressive rollout/rollback không khôi phục secret/key đã compromise hoặc revoke.
- [ ] Log, health endpoint và fingerprint không tiết lộ secret hoặc cấu hình nhạy cảm.

## Kết luận

Environment parity trong API Security là giữ tương đương các security invariant giữa những môi trường, đồng thời tách riêng dữ liệu, credential, identity và destination. Configuration validation phải kiểm tra schema, giá trị, quan hệ giữa các field và effective runtime state; cấu hình thiếu hoặc nguy hiểm cần bị chặn trước khi phục vụ traffic. Hãy kết hợp validation trong CI/CD, kiểm tra sau deploy, đối chiếu desired/deployed/runtime state và theo dõi drift liên tục. Khi staging mô phỏng đúng hành vi bảo mật của production và cấu hình được xác minh tự động, kết quả kiểm thử mới có giá trị dự báo cho lần triển khai thực tế.

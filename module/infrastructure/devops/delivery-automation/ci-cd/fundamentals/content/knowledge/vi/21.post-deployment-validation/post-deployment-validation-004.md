# Kiểm tra kết nối, cấu hình và phụ thuộc tại môi trường đích

Một deployment có thể hoàn tất về mặt thao tác nhưng ứng dụng vẫn không phục vụ được người dùng. Container đã chạy, lệnh cập nhật trả về thành công và controller báo rollout hoàn tất, nhưng ứng dụng có thể không phân giải được DNS, không kết nối được database, thiếu cấu hình runtime, dùng sai chứng thư TLS hoặc không có quyền gọi dịch vụ phụ thuộc.

Vì vậy, sau khi triển khai cần kiểm tra ngay trong môi trường đích rằng ứng dụng có thể khởi động, đọc cấu hình, xác thực danh tính và giao tiếp với những dependency cần thiết. **Post-deployment validation** là tập hợp các kiểm tra sau triển khai nhằm xác minh trạng thái thực tế, không chỉ xác nhận pipeline đã gửi lệnh deploy.

Các kiểm tra này cần chạy từ đúng network, identity và runtime context của ứng dụng. Một lệnh curl thành công trên CI runner không chứng minh pod production có thể truy cập cùng endpoint; hai môi trường có thể khác DNS, route, firewall, proxy, trust store, secret và service account.

## 1. Phân biệt triển khai thành công và ứng dụng sẵn sàng

Có nhiều mốc khác nhau trong một lần phát hành:

- **Deployment command succeeded:** công cụ triển khai đã chấp nhận yêu cầu hoặc hoàn thành lệnh.
- **Workload started:** process hoặc container đã khởi động.
- **Readiness passed:** instance đủ điều kiện nhận traffic theo tiêu chí của ứng dụng.
- **Dependency checks passed:** các kết nối và dịch vụ thiết yếu có thể được sử dụng.
- **Smoke test passed:** một số luồng nghiệp vụ đại diện hoạt động đúng.
- **Release verified:** hệ thống đạt các điều kiện quan sát trong khoảng thời gian đã định.

Không nên gộp tất cả các mốc thành một trạng thái success duy nhất. Ví dụ, Kubernetes có thể tạo đủ pod nhưng pod chưa Ready vì không kết nối được database. Hoặc pod Ready nhưng API thanh toán bên ngoài trả lỗi khi thực hiện giao dịch thử.

Một deployment record nên lưu kết quả từng nhóm kiểm tra, thời điểm, môi trường, artifact digest và cấu hình được xác minh. Điều đó giúp phân biệt lỗi deploy, lỗi khởi động, lỗi kết nối và lỗi nghiệp vụ.

## 2. Kiểm tra từ đúng môi trường đích

Kiểm tra cần phản ánh điều kiện thực tế của workload:

- Chạy từ cùng network segment, namespace, subnet hoặc runtime environment.
- Dùng cùng DNS resolver và proxy configuration mà ứng dụng sử dụng.
- Dùng cùng service identity hoặc workload identity.
- Đọc cùng secret reference và trust store đã được cấp cho workload.
- Gọi đúng hostname, port, protocol và endpoint của môi trường.
- Tôn trọng NetworkPolicy, firewall, security group, service mesh và egress rule.

Nếu smoke test chạy từ một runner bên ngoài cluster, nó có thể chỉ xác minh ingress từ bên ngoài. Nó không kiểm tra được đường kết nối từ pod tới database hoặc broker. Nên kết hợp kiểm tra bên ngoài với kiểm tra nội bộ từ pod hoặc một diagnostic job có cùng policy mạng và identity phù hợp.

Không cấp quyền production rộng cho diagnostic job chỉ để kiểm tra kết nối. Nếu cần một job riêng, cấp đúng quyền đọc hoặc gọi health endpoint cần thiết, giới hạn namespace và thời gian chạy.

## 3. Kiểm tra DNS và khả năng kết nối mạng

Một dependency có thể đang hoạt động nhưng ứng dụng vẫn không truy cập được vì DNS, route hoặc firewall sai.

### DNS

Kiểm tra hostname được cấu hình có phân giải thành địa chỉ dự kiến trong môi trường đích. Những lỗi thường gặp:

- Hostname staging bị dùng nhầm trong production.
- Service name hoặc namespace trong cluster bị sai.
- Private DNS zone chưa được liên kết với VPC/VNet.
- Resolver cache giữ địa chỉ cũ sau khi endpoint thay đổi.
- Search domain làm hostname ngắn được phân giải khác dự kiến.

Ví dụ kiểm tra từ môi trường có cùng DNS context:

```bash
getent hosts db.production.internal
nslookup payments-api.production.internal
```

Các lệnh trên chỉ minh họa; image runtime cần có công cụ tương ứng hoặc dùng diagnostic image được phê duyệt. Không cài công cụ tùy tiện vào container production đang chạy chỉ để kiểm tra.

### TCP, route và port

Sau khi DNS phân giải, kiểm tra kết nối TCP tới port của dependency. Kết nối TCP thành công chỉ chứng minh đường mạng và listener có thể bắt tay; nó chưa chứng minh TLS, xác thực hoặc giao thức ứng dụng hoạt động.

```bash
nc -vz db.production.internal 5432
nc -vz broker.production.internal 9092
```

Nếu timeout, kiểm tra route, firewall, security group, NetworkPolicy, egress proxy và trạng thái listener. Nếu bị refused, endpoint có thể truy cập được nhưng không có process lắng nghe trên port hoặc service chưa sẵn sàng.

Không mở firewall rộng để làm cho kiểm tra xanh. Xác định source identity/network và destination port cụ thể, rồi chỉ mở luồng cần thiết.

## 4. Kiểm tra TLS, chứng thư và giao thức

Kết nối TCP thành công vẫn có thể thất bại khi bắt tay TLS. Các nguyên nhân thường gặp:

- Certificate hết hạn hoặc chưa có hiệu lực.
- Hostname không khớp Subject Alternative Name.
- Container thiếu CA certificate cần thiết.
- TLS version hoặc cipher không tương thích.
- Certificate chain thiếu intermediate certificate.
- mTLS yêu cầu client certificate nhưng workload không có hoặc dùng sai certificate.
- Proxy hoặc service mesh thay đổi đường kết nối.

Có thể kiểm tra handshake và certificate từ môi trường phù hợp:

```bash
openssl s_client \
  -connect payments-api.production.internal:443 \
  -servername payments-api.production.internal \
  -verify_return_error
```

SNI cần đúng hostname dịch vụ. Lệnh này là công cụ chẩn đoán; cần kiểm tra thêm trust store, client certificate và cấu hình thực tế của ứng dụng. Không tắt certificate verification hoặc chuyển sang HTTP không mã hóa chỉ để smoke test thành công.

Sau TLS, kiểm tra đúng giao thức và endpoint. Ví dụ HTTPS health endpoint có thể trả 200 nhưng endpoint nghiệp vụ yêu cầu OAuth scope khác. Vì vậy, cần phân biệt:

- Kết nối mạng.
- TLS và xác minh danh tính máy chủ.
- Xác thực client/service identity.
- Ủy quyền theo resource và action.
- Hành vi ứng dụng ở endpoint cần dùng.

## 5. Xác minh cấu hình runtime

Ứng dụng thường nhận cấu hình từ environment variables, mounted files, config service, command-line arguments hoặc secret manager. Một deployment có thể chạy với cấu hình thiếu hoặc sai mà process vẫn khởi động.

Những cấu hình nên được kiểm tra:

- Environment name và region.
- Hostname, port, protocol và base URL của dependency.
- Database name/schema và connection pool settings.
- Timeout, retry, connection limit và circuit breaker.
- Feature flag hoặc rollout mode.
- Queue/topic, bucket/container và namespace.
- Log level, tracing endpoint và metric exporter.
- Các giá trị bắt buộc, kiểu dữ liệu, giới hạn và quan hệ giữa trường.

### Validate cấu hình khi khởi động

Fail fast với cấu hình bắt buộc giúp phát hiện sai lệch sớm. Ví dụ ứng dụng Java dùng Spring Boot có thể xác thực properties:

```java
@Validated
@ConfigurationProperties(prefix = "payments")
public record PaymentsProperties(
    @NotBlank String baseUrl,
    @NotNull Duration connectTimeout,
    @NotNull Duration readTimeout
) {}
```

Đây là ví dụ khái niệm; cần bật configuration properties scanning và khai báo dependency validation phù hợp với phiên bản Spring Boot của dự án. Ngoài kiểm tra giá trị có mặt, nên xác minh URL có scheme/host hợp lệ, timeout dương và các trường có quan hệ hợp lý.

Không đưa toàn bộ cấu hình ra log để debug. Có thể log tên cấu hình, nguồn, version và trạng thái hợp lệ; che hoặc loại bỏ password, token, private key, connection string chứa credential và dữ liệu cá nhân.

### Kiểm tra nguồn và phiên bản cấu hình

Để truy vết, lưu revision hoặc digest của config bundle, manifest, Helm chart và infrastructure definition. Nếu cấu hình được lấy từ config service, lưu version hoặc snapshot ID. Không chỉ lưu tên environment vì cấu hình có thể thay đổi theo thời gian.

Secret chỉ nên được tham chiếu bằng tên/version hoặc identity của secret manager. Không sao chép secret value vào deployment record, test report hoặc log.

## 6. Kiểm tra secret reference và danh tính runtime

Ứng dụng có thể khởi động dù secret reference chưa hợp lệ, nhưng thất bại ở lần đầu gọi database hoặc API. Cần xác minh:

- Workload identity hoặc service account được gắn đúng.
- Role/policy cho phép đọc đúng secret reference.
- Secret tồn tại ở đúng environment và version.
- Credential chưa hết hạn hoặc bị thu hồi.
- Certificate/private key có định dạng và quyền file phù hợp.
- Token có audience, issuer và scope phù hợp với dịch vụ đích.
- Quy trình rotation không làm instance giữ credential cũ quá lâu.

Không in secret để chứng minh nó đã được mount. Có thể xác minh sự tồn tại, metadata version hoặc thực hiện một thao tác xác thực an toàn tới dependency bằng credential thật trong memory. Khi kiểm tra thất bại, log mã lỗi và secret reference ID đã được làm sạch, không ghi giá trị.

Một job kiểm tra bên ngoài không thể xác minh đầy đủ runtime identity của pod nếu job dùng danh tính khác. Với workload identity, nên kiểm tra từ chính workload hoặc một diagnostic workload được cấu hình tương đương.

## 7. Kiểm tra dependency và thứ tự sẵn sàng

Ứng dụng có thể phụ thuộc vào database, cache, message broker, object storage, identity provider, API nội bộ và dịch vụ bên ngoài. Không phải dependency nào cũng cần sẵn sàng để process bắt đầu, nhưng dependency thiết yếu phải hoạt động trước khi ứng dụng nhận traffic cho chức năng tương ứng.

| Dependency | Kiểm tra phù hợp | Điều cần xác minh |
|---|---|---|
| Database | Kết nối, authentication, query nhẹ | Đúng host/schema, quyền cần thiết, migration tương thích |
| Cache | Kết nối và thao tác đọc/ghi thử có kiểm soát | Endpoint, TLS, auth và namespace |
| Message broker | Kết nối metadata hoặc kiểm tra topic/queue | Broker reachable, quyền publish/consume và tên topic |
| Object storage | Đọc metadata hoặc thao tác trên test object riêng | Bucket/container, region, role và policy |
| Internal API | Health/contract endpoint | DNS, TLS, auth scope và API version |
| External API | Endpoint kiểm tra hoặc request an toàn | Egress, proxy, TLS, credential và quota |
| Identity provider | Discovery/JWKS hoặc token validation test | Issuer, audience, key rotation và clock |

Không nên dùng thao tác có side effect lên dữ liệu thật để kiểm tra dependency. Nếu cần write test, dùng namespace, table, queue hoặc object có tên riêng và cleanup rõ ràng. Tránh tạo giao dịch, gửi email hoặc thanh toán thật trong smoke test.

### Readiness của dependency

Một dịch vụ phụ thuộc có thể đang khởi động hoặc đang bảo trì. Ứng dụng cần có timeout, retry có giới hạn và hành vi degraded phù hợp. Không nên retry vô hạn làm rollout treo hoặc tạo tải dồn dập lên dependency đang lỗi.

Kiểm tra dependency nên xác minh cả khả năng kết nối lẫn quyền thao tác tối thiểu. Một kết nối database thành công nhưng user không có quyền đọc schema cần thiết vẫn là lỗi cấu hình.

## 8. Phân biệt startup, liveness và readiness probe

Trong Kubernetes, ba loại probe có mục đích khác nhau:

- **Startup probe:** cho ứng dụng thời gian khởi động; trước khi probe này thành công, liveness và readiness chưa được thực hiện.
- **Liveness probe:** xác định process có cần được khởi động lại hay không. Không nên làm liveness phụ thuộc vào mọi dịch vụ bên ngoài, vì database tạm lỗi có thể khiến tất cả pod restart liên tục.
- **Readiness probe:** xác định instance có nên nhận traffic hay chưa. Có thể phản ánh những dependency thiết yếu để phục vụ request.

Ví dụ:

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 30

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
```

Các endpoint trên là ví dụ Spring Boot Actuator; cần cấu hình exposure và health groups phù hợp. Không giả định mọi endpoint mặc định đã được bật. Không expose endpoint quản trị hoặc chi tiết dependency ra Internet.

Readiness nên phản ánh khả năng nhận traffic, nhưng tránh phụ thuộc vào các dịch vụ tùy chọn. Nếu một hệ thống analytics tạm ngừng mà API đơn hàng vẫn hoạt động, có thể không cần đánh dấu toàn bộ pod NotReady. Liveness nên tập trung vào tình trạng process; restart không sửa được lỗi network hoặc credential của dependency.

## 9. Smoke test sau triển khai

Smoke test là tập kiểm tra ngắn xác minh các luồng quan trọng hoạt động sau khi deploy. Nó không thay thế toàn bộ integration hoặc end-to-end test.

Một smoke test tốt:

- Dùng endpoint và dữ liệu đại diện nhưng an toàn.
- Xác minh response code, schema và một số điều kiện nghiệp vụ quan trọng.
- Xác minh ứng dụng đọc được dependency thiết yếu.
- Có timeout rõ ràng và số lần retry giới hạn.
- Không tạo side effect không thể đảo ngược.
- Chạy bằng danh tính và network path gần với người dùng hoặc workload thực tế.
- Lưu kết quả cùng deployment ID, artifact digest và config revision.

Ví dụ:

```bash
curl --fail --silent --show-error \
  --connect-timeout 3 \
  --max-time 10 \
  https://orders.production.example.com/health/ready

curl --fail --silent --show-error \
  --connect-timeout 3 \
  --max-time 10 \
  https://orders.production.example.com/api/version
```

Endpoint và hostname là placeholder. Health endpoint cần trả trạng thái phù hợp, còn version endpoint nên cung cấp thông tin không nhạy cảm như release ID hoặc commit rút gọn. Không trả environment variables, secret, internal host list hoặc chi tiết cấu hình trong endpoint công khai.

Với luồng nghiệp vụ, có thể dùng một tài khoản kiểm thử và dữ liệu riêng, ví dụ tạo rồi hủy một đơn hàng test trong sandbox. Nếu không thể cleanup an toàn, dùng endpoint read-only hoặc synthetic transaction được thiết kế riêng.

## 10. Kiểm tra cấu hình môi trường và drift

Development, staging và production có thể khác nhau về hostname, certificate, region, identity, quota và policy mạng. Vì vậy, cần kiểm tra đúng cấu hình của target thay vì chỉ xác nhận file cấu hình đã tồn tại.

Những lỗi thường gặp:

- Production vô tình dùng URL hoặc credential của staging.
- ConfigMap/secret reference trỏ tới namespace khác.
- Chart values hoặc overlay không khớp environment.
- Feature flag bật ngoài cohort dự kiến.
- Resource limit quá thấp làm ứng dụng restart khi tải tăng.
- Proxy hoặc CA bundle khác với môi trường build.
- NetworkPolicy chặn một dependency mới.

Đối chiếu desired configuration với observed configuration sau deployment. Nếu có thay đổi thủ công, record cần thể hiện drift và nguồn thay đổi. Không tự động ghi đè drift nếu chưa biết thay đổi đó có chủ ý hay không; theo policy, có thể chặn rollout, cảnh báo hoặc yêu cầu review.

## 11. Kiểm tra tương thích version và migration

Kết nối database thành công chưa chứng minh ứng dụng có thể dùng schema đúng. Sau deployment, cần xác minh:

- Migration cần thiết đã chạy và ở đúng version.
- Database user có quyền tối thiểu cần thiết.
- Ứng dụng mới tương thích với schema hiện tại.
- Các consumer/producer cùng đọc và ghi message format tương thích.
- API dependency đang ở version được hỗ trợ.
- Cache key hoặc serialization format không gây xung đột giữa phiên bản cũ và mới.

Với rolling deployment, phiên bản cũ và mới có thể chạy đồng thời. Database migration và message contract nên hỗ trợ giai đoạn coexistence. Dùng expand-and-contract để thêm cấu trúc trước, triển khai code tương thích, chuyển dữ liệu và chỉ loại bỏ cấu trúc cũ sau khi hết thời gian rollback.

Không tự chạy migration phá hủy trong bước smoke test. Migration cần có job riêng, quyền riêng, record riêng và kế hoạch phục hồi phù hợp.

## 12. Theo dõi sau khi smoke test đạt

Smoke test chỉ kiểm tra một số điểm tại một thời điểm. Một lỗi có thể xuất hiện khi traffic thật tăng, cache lạnh, background worker chạy hoặc batch job bắt đầu.

Trong khoảng quan sát sau deploy, theo dõi:

- Error rate và tỷ lệ request thành công.
- Latency p50/p95/p99 của endpoint quan trọng.
- CPU, memory, thread pool, connection pool và restart count.
- Database connection, query latency và migration error.
- Broker lag, consumer error và retry/dead-letter count.
- External API timeout, rate limit và authentication failure.
- Business metric như tỷ lệ tạo đơn, thanh toán thành công hoặc xử lý event.

So sánh với baseline trước deploy và ngưỡng đã định nghĩa. Một metric đơn lẻ có thể không đủ; cần kết hợp kỹ thuật và nghiệp vụ. Nếu lỗi vượt ngưỡng trong canary, dừng tăng traffic hoặc kích hoạt rollback theo policy.

## 13. Tự động hóa validation trong pipeline

Một chuỗi post-deployment validation có thể gồm:

1. Chờ rollout controller báo trạng thái đã hội tụ.
2. Xác minh deployment ID, release ID và artifact digest trên workload.
3. Kiểm tra DNS, network, TLS và runtime identity từ môi trường đích.
4. Kiểm tra cấu hình bắt buộc và version của config bundle.
5. Kiểm tra dependency thiết yếu bằng health/diagnostic operation an toàn.
6. Chạy smoke test read-only hoặc synthetic transaction.
7. Theo dõi metric trong một khoảng quan sát.
8. Ghi kết quả, report và trạng thái deployment.
9. Nếu check bắt buộc thất bại, dừng rollout hoặc phục hồi theo policy.

Ví dụ workflow khái niệm:

```yaml
jobs:
  deploy_staging:
    steps:
      - name: Deploy approved digest
        run: ./scripts/deploy-by-digest.sh

      - name: Wait for rollout
        run: ./scripts/wait-for-rollout.sh

      - name: Validate target connectivity and configuration
        run: ./scripts/validate-runtime.sh

      - name: Run smoke tests
        run: ./scripts/smoke-test.sh

      - name: Publish deployment evidence
        if: always()
        run: ./scripts/publish-deployment-evidence.sh
```

Các script là placeholder, cần triển khai theo nền tảng và môi trường. Bước publish evidence có thể chạy sau failure để giữ log, nhưng không được biến kết quả deploy thất bại thành success. Job tổng hợp cần phân biệt pass, fail, skipped và cancelled.

Validation nên dùng timeout tổng thể và retry có backoff. Nếu dependency chưa sẵn sàng trong thời gian cho phép, ghi rõ dependency, endpoint đã kiểm tra, loại lỗi và số lần thử; tránh retry vô hạn.

## 14. Xử lý validation thất bại

Không phải lỗi nào cũng cần rollback toàn bộ. Cần phân loại theo phạm vi và tác động:

| Phát hiện | Hành động tham khảo |
|---|---|
| DNS/route/TLS sai cho dependency thiết yếu | Dừng rollout; kiểm tra network/config và rollback nếu phiên bản mới gây lỗi |
| Thiếu cấu hình bắt buộc | Không nhận traffic; sửa config hoặc phục hồi revision trước |
| Secret reference không hợp lệ | Giữ workload ngoài traffic, sửa identity/secret mapping và kiểm tra lại |
| Dependency tùy chọn không sẵn sàng | Chạy degraded mode nếu được thiết kế; cảnh báo và theo dõi |
| Readiness không đạt | Không chuyển traffic; giữ instance cũ nếu rollout strategy hỗ trợ |
| Smoke test nghiệp vụ thất bại | Dừng tăng traffic, điều tra và rollback/roll-forward theo mức độ |
| Metric xấu sau canary | Dừng rollout hoặc chuyển traffic về stable version |

Trước rollback, kiểm tra tương thích database, message và cấu hình. Nếu lỗi do network hoặc secret mapping bên ngoài artifact, rollback có thể không giải quyết được nguyên nhân. Có thể cần khôi phục config hoặc policy trước. Deployment record nên liên kết lỗi với hành động khắc phục và kết quả xác minh sau đó.

## 15. Bảo vệ thông tin trong health check và diagnostics

Health endpoint và log có thể vô tình tiết lộ thông tin nội bộ. Chỉ trả mức trạng thái cần thiết cho caller:

- Endpoint công khai có thể trả trạng thái tổng quát.
- Chi tiết dependency nên được bảo vệ bằng network hoặc authorization phù hợp.
- Không trả connection string, token, certificate private key, environment variable hoặc dữ liệu cá nhân.
- Không ghi credential, header Authorization hoặc query string nhạy cảm vào log.
- Dùng correlation ID và dependency name đã chuẩn hóa để điều tra.
- Giới hạn tần suất diagnostic check để tránh tạo tải lên dependency.

Nếu cần debug sâu, dùng log có kiểm soát quyền và thời hạn lưu; không mở actuator/env/config endpoint công khai trong production.

## 16. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra deploy command trả về 0 | Ứng dụng có thể chưa sẵn sàng | Kiểm tra rollout, readiness và smoke test |
| Test kết nối từ CI runner thay vì target | Kết quả không phản ánh DNS/network/identity của ứng dụng | Chạy từ runtime context hoặc diagnostic job tương đương |
| Chỉ kiểm tra TCP port | Bỏ sót TLS, auth, permission và protocol | Kiểm tra toàn bộ handshake và thao tác cần thiết |
| In toàn bộ config để debug | Có thể lộ secret | Log version, key name và trạng thái đã che dữ liệu |
| Dùng liveness phụ thuộc mọi external service | Dependency lỗi gây restart hàng loạt | Tách liveness và readiness |
| Smoke test tạo dữ liệu thật không cleanup | Gây side effect hoặc làm bẩn dữ liệu production | Dùng synthetic data và cleanup có kiểm soát |
| Retry vô hạn khi dependency lỗi | Rollout treo và tăng tải | Timeout tổng, retry giới hạn và backoff |
| Chỉ kiểm tra một lần ngay sau deploy | Bỏ sót lỗi khi traffic tăng | Có observation window và theo dõi metric |
| Rollback mà bỏ qua migration/config | Phiên bản cũ không tương thích hoặc lỗi vẫn còn | Kiểm tra schema và phục hồi config cùng release context |

## 17. Checklist kiểm chứng tại môi trường đích

- [ ] Kiểm tra từ đúng network, namespace, DNS và workload identity.
- [ ] DNS phân giải đúng hostname và route tới endpoint dự kiến.
- [ ] TCP port, firewall, NetworkPolicy và egress rule cho phép đúng luồng cần thiết.
- [ ] TLS certificate, hostname, CA chain, SNI và mTLS hợp lệ.
- [ ] Runtime config có đủ giá trị, đúng environment và đúng revision.
- [ ] Secret reference tồn tại, identity có quyền tối thiểu và credential còn hiệu lực.
- [ ] Database, cache, broker, object storage và API thiết yếu có thể được sử dụng.
- [ ] Startup, liveness và readiness probe có mục đích riêng và cấu hình phù hợp.
- [ ] Rollout hoàn tất và observed artifact digest khớp desired digest.
- [ ] Smoke test xác minh luồng quan trọng mà không tạo side effect ngoài ý muốn.
- [ ] Metric/log/trace được theo dõi trong observation window.
- [ ] Deployment record lưu config revision, dependency result, evidence và trạng thái cuối.
- [ ] Có timeout, retry giới hạn, hành động khi fail và phương án phục hồi đã xác định.
- [ ] Health endpoint và diagnostics không làm lộ secret hoặc thông tin nội bộ.

Kiểm tra kết nối, cấu hình và phụ thuộc tại môi trường đích giúp xác nhận ứng dụng thực sự có thể hoạt động sau khi deploy. Khi validation chạy trong đúng runtime context, kiểm tra từ DNS/TLS đến identity và dependency, rồi xác minh bằng smoke test cùng telemetry, nhóm có bằng chứng đáng tin cậy để tiếp tục rollout hoặc dừng và phục hồi kịp thời.

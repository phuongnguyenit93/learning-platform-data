# Quản lý môi trường thử nghiệm, staging và production trong microservices

## 1. Bài toán: một hệ thống, nhiều môi trường vận hành

Trong kiến trúc microservices, một yêu cầu nghiệp vụ có thể đi qua API gateway, nhiều dịch vụ độc lập, cơ sở dữ liệu, message broker, cache và dịch vụ bên thứ ba. Khi đưa một thay đổi từ máy của lập trình viên tới production, nhóm cần trả lời không chỉ “mã này đã chạy được chưa?” mà còn:

- Nó đã được kiểm thử trong môi trường nào, với các dịch vụ và cấu hình phụ thuộc nào?
- Bản chạy ở staging có thật sự là artifact sẽ đưa lên production?
- Một thử nghiệm lỗi hoặc tải cao có thể ảnh hưởng dữ liệu production không?
- Ai có thể thay đổi cấu hình, credential và phiên bản dịch vụ ở từng môi trường?
- Làm sao biết thay đổi ứng dụng, cấu hình, dữ liệu và hạ tầng nào đã gây ra sự cố?
- Khi cần rollback, môi trường còn giữ được artifact và trạng thái dữ liệu tương thích hay không?

**Quản lý môi trường** là tổ chức hạ tầng, cấu hình, dữ liệu, quyền truy cập, kiểm thử, triển khai và quan sát của từng giai đoạn trong vòng đời phần mềm theo chính sách rõ ràng. Mục đích là tạo tín hiệu tin cậy trước khi phát hành, đồng thời cô lập rủi ro để hoạt động thử nghiệm không gây ảnh hưởng sản xuất.

Các môi trường phổ biến:
- **Development/local:** hỗ trợ vòng lặp viết mã và chạy thử nhanh.
- **Test/integration:** kiểm thử tự động, hợp đồng dịch vụ, tình huống lỗi và luồng tích hợp.
- **Staging/pre-production:** diễn tập phát hành, kiểm tra ứng dụng với cấu hình và topology đại diện production.
- **Production:** phục vụ lưu lượng và dữ liệu thật, chịu ràng buộc về độ sẵn sàng, bảo mật và vận hành.

Một tổ chức có thể bổ sung môi trường preview theo pull request, performance test, security test hoặc disaster recovery. Tên gọi không phải yếu tố quyết định; **mỗi môi trường phải có mục đích, chủ sở hữu, dữ liệu, quyền và tiêu chí sử dụng**.

## 2. Phân biệt trách nhiệm các môi trường

| Thuộc tính | Test / integration | Staging / pre-production | Production |
| --- | --- | --- | --- |
| Mục tiêu chính | Phát hiện lỗi chức năng, hợp đồng và tích hợp | Kiểm chứng bản sắp phát hành và quy trình triển khai | Phục vụ người dùng thật an toàn |
| Chu kỳ thay đổi | Thường xuyên, có thể tạo/xóa theo bộ test | Có kiểm soát, đồng bộ với ứng viên release | Theo release policy, quan sát từng đợt |
| Dữ liệu | Tổng hợp, giả lập, seed/reset được | Đại diện hình dạng, khối lượng, không lộ dữ liệu nhạy cảm | Dữ liệu thực có chính sách bảo vệ |
| Dependency | Kết hợp dịch vụ thật, mock, stub, test container | Ưu tiên phiên bản và cách kết nối gần production | Phụ thuộc đang vận hành thật |
| Quyền truy cập | Nhà phát triển và hệ thống test theo phạm vi | QA, release owner, nhóm vận hành theo phân quyền | Hạn chế tối đa và có audit |
| Tính sẵn sàng | Có thể thấp, ưu tiên tốc độ phản hồi | Đủ ổn định để xác nhận release | Theo SLO/SLA được cam kết |
| Sự cố | Có thể reset và tái tạo | Chặn promote và điều tra | Incident response, giảm tác động người dùng |
| Quan sát | Log/test report, trace giúp debug | Dashboard, alert và smoke test như production | Telemetry liên tục, cảnh báo và on-call |

**Test** trả lời “hành vi và hợp đồng có đúng trong các tình huống được kiểm chứng?”. **Staging** trả lời “ứng viên release và cách triển khai có hoạt động ở môi trường đại diện production?”. **Production** trả lời “thay đổi có đáp ứng cam kết vận hành với người dùng thật?”. Ba câu hỏi cần tín hiệu khác nhau.

Không phải test nào cũng cần staging. Một số kiểm thử đơn vị nên chạy nhanh tại CI; kiểm thử tải lớn cần môi trường riêng để tránh làm sai lệch kết quả staging; kiểm thử lỗi hạ tầng chỉ chạy ở môi trường có quyền cô lập phù hợp.

## 3. Ranh giới môi trường trong microservices

Một môi trường không chỉ là biến `APP_ENV=staging`. Nó thường gồm:
1. **Compute:** cluster, namespace, VM hoặc workload runtime.
2. **Network:** DNS, gateway/ingress, firewall, service discovery, egress policies.
3. **State:** database, cache, object storage, search index, message broker.
4. **Identity:** service account, IAM roles, secret stores, certificates.
5. **Configuration:** endpoint, flags, quotas, timeout, resource requests/limits.
6. **Observability:** logs, metrics, traces, dashboards, alert routes.
7. **Delivery controls:** CI/CD runner, deployment identity, release policy và audit trail.

Ranh giới mong muốn phụ thuộc mức độ rủi ro. Production có thể cần tài khoản cloud hoặc cluster riêng; test và staging có thể dùng các namespace khác nhau trên cùng cluster nếu quota, RBAC, network và dữ liệu thực sự được cô lập. Việc chọn cluster riêng hay dùng chung cần xét cả mức độ cách ly, chi phí, năng lực vận hành và các yêu cầu của tổ chức.

**Không có ranh giới an toàn chỉ nhờ tiền tố tên.** Đặt database `prod_orders` và `staging_orders` chung một máy chủ, nhưng dùng cùng credential có quyền ghi cả hai, vẫn tạo khả năng thử nghiệm chạm dữ liệu thật.

### 3.1. Mức độ cô lập tăng dần

| Mô hình | Lợi ích | Rủi ro chính |
| --- | --- | --- |
| Cùng tiến trình, khác profile | Nhanh, ít chi phí, thích hợp local | Dễ dùng nhầm endpoint/state |
| Cùng cluster, khác namespace | Tái sử dụng hạ tầng, quản lý tập trung | Có thể tranh tài nguyên; network/RBAC sai gây lan lỗi |
| Khác cluster, cùng cloud account | Cách ly tài nguyên và lifecycle tốt hơn | IAM hoặc dịch vụ chung vẫn có thể ảnh hưởng chéo |
| Khác account/project, cluster riêng | Ranh giới quyền và billing rõ | Chi phí và gánh nặng vận hành lớn hơn |

Không có một mô hình áp dụng cho mọi dịch vụ. Với dữ liệu thanh toán hoặc dịch vụ có ảnh hưởng lớn, ranh giới account và secret riêng có thể quan trọng hơn tính tiện dụng. Với test ephemeral, namespace có TTL và quota thường là lựa chọn thực tế.

### 3.2. Cô lập luồng mạng

Hạn chế lưu lượng giữa test/staging và production bằng network policies và quyền truy cập có chủ đích. Một dịch vụ staging không được gọi nhầm gateway production chỉ vì tên miền hoặc biến môi trường chưa thay. Nếu cần kiểm thử với provider thật, sử dụng sandbox endpoint và credential riêng khi provider hỗ trợ; nếu không, phải có cơ chế kiểm soát yêu cầu không tạo tác động thật.

## 4. Quản lý cấu hình: giống ở cách chạy, khác ở giá trị

Nguyên tắc là **một codebase, artifact bất biến; cấu hình được cung cấp từ môi trường một cách có kiểm soát**. Cùng một image dịch vụ có thể chạy ở test, staging và production với endpoint, credential, tài nguyên và feature flag khác nhau.

Ví dụ nhóm cấu hình:

| Loại | Test | Staging | Production |
| --- | --- | --- | --- |
| Database URL | Database dành cho test, có thể reset | Database đại diện production, dữ liệu đã khử nhạy cảm | Database production có backup/HA |
| Log level | DEBUG có kiểm soát | INFO, tăng chi tiết khi điều tra | INFO/WARN, giới hạn dữ liệu nhạy cảm |
| External provider | Stub/sandbox | Sandbox hoặc môi trường đại diện | Endpoint thật |
| Resource/quota | Thấp hơn, tối ưu chi phí | Đại diện đủ cho smoke/rollout | Theo load và SLO |
| Feature flags | Mở tính năng thử nghiệm | Diễn tập cấu hình release | Mở có kiểm soát theo nhóm |
| Secret | Credential test không có quyền production | Credential staging | Credential production qua secret manager |

Để không tạo trôi cấu hình, định nghĩa **schema cấu hình chung**: tên key, kiểu dữ liệu, điều kiện bắt buộc, miền giá trị, giá trị mặc định an toàn. Hệ thống phát hiện thiếu hoặc sai cấu hình ngay khi startup, thay vì âm thầm chuyển sang endpoint khác.

Trong Java/Spring Boot có thể sử dụng một bộ `application.yml` với các placeholder và các cấu hình theo môi trường:

~~~yaml
# Minh họa: giá trị được cung cấp bởi cơ chế quản lý môi trường.
spring:
  application:
    name: catalog-service
  datasource:
    url: ${CATALOG_DB_URL}
    username: ${CATALOG_DB_USER}
    password: ${CATALOG_DB_PASSWORD}
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
catalog:
  pricingServiceUrl: ${PRICING_SERVICE_URL}
  checkoutTimeoutMs: ${CHECKOUT_TIMEOUT_MS:1200}
~~~

Đây là cấu hình minh họa, cần điều chỉnh loại datasource, endpoint Actuator và policy bảo mật theo hệ thống thực tế. Không công khai endpoint nội bộ hoặc metric nhạy cảm ra internet chỉ vì đã bật Actuator.

### 4.1. Spring profiles và cấu hình triển khai

`SPRING_PROFILES_ACTIVE` có thể lựa chọn nhóm cấu hình theo môi trường, nhưng không nên dùng profile như cơ chế phân quyền hoặc bảo vệ secret. Ví dụ `application-staging.yml` chỉ nên giữ các giá trị không nhạy cảm, có thể review như timeout hoặc mức log; secret phải được cấp qua hệ thống secret management.

Nguy cơ thường gặp:
- File production chứa mật khẩu thật được commit vào repository.
- Bản staging cấu hình trỏ đến queue, bucket hoặc database production.
- Một key bị thiếu và fallback sang endpoint production mặc định.
- Tên profile `dev` được dùng trong production để bỏ qua authentication.
- Thay đổi cấu hình trực tiếp trong dashboard mà không cập nhật Git.

Tách cấu hình thành ba lớp khi cần: **cấu hình ứng dụng được version hóa**, **tham số theo môi trường được review**, và **secret được kiểm soát bằng danh tính workload**. Ghi lại phiên bản của cấu hình khi deploy để có thể truy nguyên.

## 5. Secret, chứng chỉ và danh tính theo môi trường

Các môi trường phải có credential riêng. Không dùng tài khoản database production cho integration test, không sao chép private key production sang staging, và không reuse một token có quyền cao trên mọi cluster.

Quy trình tham chiếu:
1. Secret được lưu trong vault/secret manager hoặc cơ chế được tổ chức phê duyệt.
2. Workload nhận danh tính riêng theo service và environment.
3. IAM policy chỉ cho phép đọc secret cần thiết của chính môi trường.
4. Runtime nạp secret qua cơ chế injection phù hợp; hạn chế đặt secret trong build args hoặc image.
5. Secret rotation có kế hoạch; theo dõi lỗi xác thực và có rollback khi đổi credential.
6. Log, traces, crash dump và kết quả test được lọc để tránh làm lộ secret.

Khi pipeline chạy từ CI, ưu tiên credential ngắn hạn và danh tính liên kết như OIDC nếu nền tảng hỗ trợ, giảm phụ thuộc vào key tĩnh. Tách quyền build, quyền publish image và quyền deploy production. Pull request từ nguồn không tin cậy không được nhận secret production.

**Khác môi trường phải khác quyền.** Có thể dùng cùng logic deployment nhưng identity production cần chính sách chặt hơn: approval, audit, branch protection, allowlist artifact/provenance và quyền emergency rõ ràng.

## 6. Tạo môi trường bằng Infrastructure as Code

Infrastructure as Code (IaC) diễn tả tài nguyên bằng cấu hình có version, review và kiểm chứng. Các công cụ như Terraform, OpenTofu, Pulumi, CloudFormation hoặc template Kubernetes có thể thực hiện những phần khác nhau của cùng quy trình.

Tư duy tổ chức:

~~~text
infra/
├── modules/
│   ├── service-runtime/
│   ├── datastore/
│   └── observability/
├── environments/
│   ├── test/
│   ├── staging/
│   └── production/
└── policies/
    ├── network/
    └── deployment/
~~~

Mẫu này chỉ minh họa cách chia module dùng chung và tham số môi trường. Trạng thái IaC (state) cần được cô lập và có quyền truy cập riêng; lưu state production cùng chỗ và cùng quyền với test có thể cho phép một lệnh test thay đổi tài nguyên production.

Các thực hành quan trọng:
- Dùng module chung để giảm sai khác cấu trúc, cấu hình instance size và số replica theo tải.
- Mọi thay đổi hạ tầng có plan/diff, review và audit trước khi apply.
- State backend có locking và bảo vệ dữ liệu nhạy cảm; không commit state vào repository.
- Hạn chế thay đổi thủ công; phát hiện và xử lý drift định kỳ.
- Tách thông số môi trường khỏi danh tính resource đang được quản lý.
- Với production, cân nhắc bảo vệ xóa nhầm, backup, rollback và thao tác apply có phê duyệt.

**Môi trường tương đồng không đồng nghĩa phải có cùng số node.** Staging có thể nhỏ hơn, nhưng những khác biệt ảnh hưởng tính đúng đắn — cách xác thực, network policy, service discovery, kiểu database, chế độ message delivery, cơ chế autoscaling — cần được hiểu và kiểm chứng.

## 7. GitOps và quản lý trạng thái mong muốn

GitOps là cách lấy cấu hình đã phê duyệt trong repository làm trạng thái mong muốn của hệ thống triển khai. Controller như Argo CD hoặc Flux có thể đối chiếu trạng thái đang chạy với định nghĩa đã version hóa.

~~~mermaid
flowchart TD
    A[CI build và kiểm thử] --> B[Image registry<br/>digest bất biến]
    B --> C[Pull request cập nhật môi trường]
    C --> D[Review policy và xác nhận release]
    D --> E[GitOps repository<br/>desired state]
    E --> F[Controller đồng bộ]
    F --> G[Test / staging / production]
    G --> H[Metrics, logs, traces<br/>và trạng thái rollout]
~~~

Nên tách trách nhiệm:
- Repository mã nguồn: logic nghiệp vụ, test, build và định nghĩa artifact.
- Repository hoặc thư mục cấu hình môi trường: digest triển khai, resource limits, routing, feature flags và thay đổi được review.
- Secret store: giá trị nhạy cảm và danh tính cấp quyền.
- Hệ thống quan sát: bằng chứng trạng thái thật của từng môi trường.

GitOps controller tự đồng bộ không đồng nghĩa “mọi thay đổi đều an toàn”. Production vẫn cần gate xác nhận artifact, kiểm tra migration, policy và hiệu quả rollout. Khi drift xuất hiện, phải biết controller sẽ tự khôi phục hay yêu cầu điều tra để tránh lặp lại thay đổi lỗi.

## 8. Build một lần, đưa qua nhiều môi trường

Một lỗi điển hình là test build từ nhánh `main`, staging build lại từ `main`, rồi production cũng build lại. Cùng tên version không bảo đảm cùng byte vì dependency, base image hoặc build timestamp có thể thay đổi.

Quy trình đúng:
1. Merge commit qua review và CI.
2. CI tạo một image/package, ghi commit SHA, build run, SBOM/provenance nếu có, và digest bất biến.
3. Triển khai **đúng digest đó** đến test, chạy các bài kiểm chứng phù hợp.
4. Promote cùng digest sang staging; diễn tập migration, smoke test, traffic và quan sát.
5. Sau khi đạt release gate, deploy production bằng chính digest đã phê duyệt.
6. Ghi deployment record cho từng môi trường gồm artifact digest **và phiên bản cấu hình tương ứng**.

Ví dụ manifest môi trường theo mô hình mô tả:

~~~yaml
service: catalog-service
artifact: registry.example/catalog-service@sha256:<approved-digest>
environments:
  test:
    configRevision: test-config-41
    replicas: 1
  staging:
    configRevision: staging-config-56
    replicas: 2
  production:
    configRevision: production-config-88
    replicas: 6
~~~

YAML trên **không phải Kubernetes manifest có thể áp dụng trực tiếp**. Digest là placeholder cần thay bằng digest thật. Mục tiêu của ví dụ là giữ artifact đồng nhất trong khi version cấu hình và quy mô hạ tầng được phép khác nhau.

Một phát hành thực tế không chỉ có một version ứng dụng. Nó gồm tuple hữu ích:

`(service, image digest, config revision, schema/migration state, deployment time, environment)`

Tuple này cho phép giải thích vì sao cùng image hoạt động ở staging nhưng có hành vi khác production: có thể do dữ liệu, tải, quyền, cấu hình hoặc dependency chứ không nhất thiết do code khác nhau.

## 9. Chiến lược kiểm thử theo từng môi trường

### 9.1. Test/integration: kiểm thử nhanh và có thể lặp lại

Ở môi trường test:
- Unit test chạy nhanh trong CI, không phụ thuộc hạ tầng bên ngoài khi không cần.
- Integration test dùng database/broker thật ở phiên bản đại diện khi cần xác nhận behavior adapter.
- Contract test bảo vệ tương thích API và event giữa producer/consumer.
- Component test kiểm tra một service với các dependency stub có khả năng kiểm soát lỗi.
- End-to-end test chỉ tập trung luồng nghiệp vụ trọng yếu; tránh đưa mọi kịch bản vào bộ test end-to-end cồng kềnh.
- Test data seed có thể reset để lần chạy sau không thừa hưởng trạng thái rác.

Không mặc định dùng toàn bộ microservices thật cho mọi unit hoặc integration test. Sự phụ thuộc vào môi trường dùng chung làm pipeline chậm, khó tái hiện và dễ sai lệch kết quả khi dịch vụ của nhóm khác đang deploy.

### 9.2. Staging: xác nhận điều kiện phát hành

Ở staging, ưu tiên kiểm tra những thuộc tính phụ thuộc cách triển khai:
- Image/digest chính xác và chính sách artifact verification.
- Startup, readiness và liveness phù hợp; việc kết nối database, broker và service discovery thành công.
- Thay đổi schema hoặc event vẫn tương thích khi old/new version tồn tại cùng thời điểm.
- Smoke test các luồng chính sau deploy.
- AuthN/AuthZ, ingress, service-to-service security, TLS và DNS.
- Quan sát trace xuyên dịch vụ, log, metric và alert có route đúng.
- Canary/rolling update, rollback hoặc roll forward được mô phỏng khi phù hợp.
- Test khả năng chịu tải đại diện trong giới hạn không làm ảnh hưởng hạ tầng khác.

Staging có thể thiếu traffic thật và sự đa dạng dữ liệu production; vì vậy **staging xanh chưa đủ để bảo đảm production sẽ không phát sinh lỗi**. Kế hoạch phát hành vẫn cần rollout có kiểm soát và quan sát trực tiếp.

### 9.3. Production: xác nhận sau triển khai

Sau khi triển khai production, dùng health probe, smoke test không phá dữ liệu, metric kỹ thuật và tín hiệu nghiệp vụ để quyết định tiếp tục hay dừng rollout. Ví dụ dịch vụ checkout nên theo dõi tỷ lệ đặt hàng thành công bên cạnh latency và HTTP error; response 200 không bảo đảm giao dịch đã được ghi đúng.

Không chạy bộ kiểm thử có thao tác phá hủy hoặc tạo giao dịch thật không được kiểm soát trong production. Các thử nghiệm production phải có thiết kế an toàn, quyền và cơ chế hủy phù hợp.

## 10. Môi trường preview theo pull request

**Preview environment** là môi trường tạm thời cho một pull request hoặc branch, giúp review UI/API, chạy integration test và xác nhận hành vi trước khi merge.

Một workflow phổ biến:
1. Pull request được mở, CI build ứng viên.
2. Hệ thống cấp namespace hoặc stack tạm với tên định danh khó xung đột.
3. Tạo database/schema/broker topic thử nghiệm, inject credential test ngắn hạn.
4. Triển khai service đang thay đổi và các dependency cần thiết; dùng fake/stub cho provider có side effect.
5. Chạy test, xuất URL truy cập có bảo vệ và log/trace liên quan.
6. Khi pull request đóng hoặc hết TTL, tự thu hồi tài nguyên và xóa dữ liệu test.

Preview cần quota, TTL, giới hạn chi phí, network policy và secret isolation; nếu không, nhiều pull request có thể chiếm cạn tài nguyên test hoặc giữ credential tồn tại quá lâu.

**Không coi preview là staging release cuối.** Preview phục vụ thảo luận thay đổi chưa merge; staging dùng artifact ứng viên từ revision đã được kiểm soát.

## 11. Quản lý dữ liệu theo môi trường

Dữ liệu là nguyên nhân lớn khiến staging khác production. Chỉ sao chép schema và vài dòng dữ liệu giả có thể bỏ sót trường hợp business edge case, phân bố kích thước hoặc phân quyền phức tạp. Ngược lại, sao chép dữ liệu người dùng thật sang staging có thể vi phạm chính sách bảo mật và tạo nguy cơ rò rỉ.

Thiết kế dữ liệu test/staging nên xác định:
- **Nguồn:** synthetic data, fixture có cấu trúc, dữ liệu đã khử định danh theo chính sách.
- **Coverage:** dữ liệu bình thường, null, trùng lặp, giá trị lớn, Unicode, ranh giới thời gian, concurrency.
- **Khối lượng:** đủ đại diện để đánh giá index, query plan, cache và pagination khi cần.
- **Tính nhất quán:** giữ quan hệ khóa ngoại và liên kết cross-service hợp lệ.
- **Lifecycle:** seed/reset trước và sau test; TTL và quyền xóa dữ liệu có kiểm soát.
- **An toàn:** không dùng token, email, số điện thoại, thông tin giao dịch thật trong môi trường truy cập rộng.

Nếu dùng snapshot production để tạo dataset đại diện, cần kiểm soát trích xuất, khử định danh đủ mạnh, quyền người dùng, thời hạn lưu, audit và các nghĩa vụ pháp lý phù hợp. Việc “đổi tên” một vài cột không nhất thiết làm dữ liệu hết nhạy cảm, đặc biệt khi có thể liên kết các thuộc tính để tái nhận diện.

### 11.1. Database schema migration

Khi các phiên bản microservice được deploy lệch nhau, migration phải tính đến việc bản cũ và mới cùng truy cập schema trong thời gian rollout.

Mẫu **expand → migrate → contract**:
1. **Expand:** thêm cột, index, table hoặc trường mới mà code cũ vẫn hoạt động.
2. **Migrate:** code mới đọc/ghi theo đường tương thích, chuyển dữ liệu từng phần, xác minh dữ liệu.
3. **Contract:** chỉ xóa cấu trúc cũ sau khi không còn consumer hoặc instance phụ thuộc.

Ở test có thể reset database; ở staging cần kiểm chứng migration theo cấu trúc và kích thước đủ đại diện; ở production cần backup, đánh giá lock/timeouts, giới hạn tải và phương án xử lý migration chạy dở. Rollback image không tự đảo ngược migration phá hủy dữ liệu. Có thể phải **roll forward** bằng bản sửa mới.

**Không sử dụng một database chung có quyền ghi cho cả staging và production.** Nếu buộc kết nối một phần đến dữ liệu production để quan sát, phải thiết kế read-only, kiểm soát mạng và phê duyệt cụ thể; tránh biến việc truy vấn thử thành thao tác có side effect.

## 12. Message broker, event và tác động liên môi trường

Với event-driven microservices, tách database nhưng dùng chung topic hoặc queue có thể vẫn gây sự cố. Ví dụ staging consumer đọc mất message dành cho production hoặc staging producer gửi sự kiện giả vào topic production, kích hoạt email/hóa đơn thật.

Ranh giới tối thiểu cần xác định:
- Broker/cluster riêng hoặc namespace/tenant/topic có ACL cô lập rõ.
- Credential publisher/subscriber theo môi trường.
- Tên topic, subscription và dead-letter queue theo quy ước.
- Consumer group tách biệt, không để test tiêu thụ hàng production.
- Retention, retry, idempotency và cơ chế replay dữ liệu phù hợp.
- Event schema compatibility được kiểm chứng trước release.

Tương tự, với object storage và cache phải có bucket/prefix/keyspace kèm IAM policy không thể ghi xuyên môi trường. Đừng dựa vào một chuỗi tiền tố để thay thế quyền truy cập thật.

## 13. Dịch vụ bên thứ ba và sandbox

Các microservice có thể gửi email, xử lý thanh toán, bản đồ, SMS, giao vận hoặc webhook. Test “thành công” nhưng gọi API thật sẽ tạo đơn hàng, phí, thông báo hoặc thay đổi trạng thái ngoài ý muốn.

Quy tắc phù hợp:
- **Unit/component:** stub, mock hoặc simulator kiểm soát timeout, lỗi và response.
- **Integration:** provider sandbox nếu hỗ trợ; dùng credential và quota riêng.
- **Staging:** diễn tập tương tác đại diện; lưu ý sandbox thường khác sản phẩm thật về rate limit và behavior.
- **Production:** chỉ phát yêu cầu thật từ phiên bản được phê duyệt; dùng canary, feature flag và circuit breaker khi phù hợp.

Cần test timeout, retry, idempotency key và webhook trùng lặp. Đối với hệ thống gửi thông báo, staging nên dùng sink mailbox hoặc allowlist địa chỉ để tránh phát tán cho khách hàng. Đối với thanh toán, tuyệt đối không coi sandbox là có đầy đủ các quy tắc hoàn tiền hoặc chống gian lận giống production.

## 14. Staging gần production đến mức nào?

**Production parity** là mức độ staging tái hiện được những điều kiện có ảnh hưởng đến kết quả release. Nó không đòi hỏi chi phí hạ tầng giống hệt 100%, nhưng phải hiểu được chênh lệch quan trọng.

Các lớp cần xem xét:
1. **Runtime parity:** cùng ngôn ngữ runtime, container base, ingress, service discovery và cơ chế cấu hình.
2. **Dependency parity:** phiên bản database, broker, cache và chính sách giao tiếp đại diện.
3. **Security parity:** xác thực, mTLS, network policy, secret injection và quyền service account.
4. **Deployment parity:** cùng Helm chart/manifest pattern, readiness/rollout strategy, autoscaling và health checks.
5. **Data parity:** schema, phân bố, trường hợp biên và kích thước đủ để phát hiện vấn đề.
6. **Traffic parity:** mẫu tải, burst, latency mạng và fan-out tương đối đại diện.
7. **Observability parity:** metric, trace, correlation ID và alert tương tự.

Ví dụ staging có 2 replica và production có 20 replica có thể chấp nhận cho smoke test; tuy nhiên nếu production dùng autoscaling và service mesh mà staging không có, một lớp lỗi quan trọng sẽ không được kiểm chứng. Với kiểm thử hiệu năng, dùng môi trường chuyên biệt đủ gần production để tránh kết luận sai từ cơ sở hạ tầng quá nhỏ.

**Danh sách sai khác có chủ đích** nên được quản lý như cấu hình: thuộc tính khác, lý do, ảnh hưởng đến độ tin cậy của kiểm thử và cách kiểm tra bổ sung. Không nên mặc định staging giống production chỉ vì cả hai dùng Kubernetes.

## 15. Phát hành tự chủ giữa các microservice

Một service có thể release độc lập khi:
- Có image/digest riêng và pipeline test/build/deploy riêng.
- Hợp đồng API/event hỗ trợ phiên bản cũ trong cửa sổ chuyển đổi.
- Schema và dữ liệu không yêu cầu tất cả service deploy đồng thời.
- Cấu hình, secret, rollout và quyền deploy không ghi đè service khác.
- Có thể nhận biết và xử lý lỗi của chính release đó qua telemetry.
- Các chính sách dùng chung được áp dụng, nhưng không buộc mọi thay đổi chờ release train tổng.

Ví dụ catalog-service thêm trường tùy chọn vào response. CI build image mới của catalog; integration và contract test xác nhận cart-service, checkout-service vẫn hiểu response cũ; staging deploy catalog mới bên cạnh các consumer hiện hành. Khi đạt gate, production rollout catalog theo digest. Cart và checkout không cần redeploy nếu hợp đồng tương thích.

Ngược lại, khi đổi kiểu productId từ số thành object và consumer cũ không hỗ trợ, cần một giai đoạn tương thích hoặc kế hoạch phối hợp rõ ràng. **Có ba môi trường tách biệt không tự động tạo được khả năng release độc lập**.

## 16. Cổng chuyển đổi giữa test → staging → production

Cổng phát hành (promotion gate) nên xác định điều kiện và bằng chứng:

| Chuyển đổi | Kiểm chứng tối thiểu | Quyết định khi thất bại |
| --- | --- | --- |
| Merge → Test | Review, build, unit test, security checks cơ bản | Không tạo ứng viên release |
| Test → Staging | Integration/contract tests, artifact digest, dependency verification | Giữ lại ở test, điều tra lỗi |
| Staging → Production | Smoke test, migration readiness, policy verification, release owner approval khi cần | Chặn promote, xử lý thay đổi |
| Production canary → Full | Error rate, latency, saturation, tín hiệu nghiệp vụ và error budget | Dừng rollout, rollback/roll forward |
| Release → Stable | Theo dõi sau release và cập nhật deployment record/runbook | Duy trì sự cố dưới quản lý vận hành |

Một số tổ chức tự động hóa toàn bộ promotion khi tín hiệu đủ tốt; nơi khác yêu cầu duyệt thủ công cho thay đổi có rủi ro cao. Điều quan trọng là cổng duyệt dựa trên chính sách và evidence, không phụ thuộc cảm tính “staging nhìn có vẻ ổn”.

Mọi approval nên gắn vào **artifact digest + revision cấu hình + môi trường đích**, tránh tình huống người duyệt bản A nhưng hệ thống triển khai bản B sau khi tag bị cập nhật.

## 17. Progressive delivery trong production

Các chiến lược triển khai phổ biến:

- **Rolling update:** thay thế từng nhóm instance; phiên bản cũ và mới cùng tồn tại tạm thời.
- **Canary:** cho phần nhỏ traffic vào bản mới, quan sát rồi tăng dần.
- **Blue/green:** duy trì hai tập workload, chuyển traffic khi tập mới đã sẵn sàng.
- **Feature flags:** tách việc deploy code khỏi việc bật hành vi cho người dùng.

Quy trình canary minh họa:

~~~text
Deploy image digest X vào nhóm canary
    ↓
5% traffic → theo dõi và so với baseline
    ↓ đạt điều kiện
25% traffic → kiểm tra error budget và nghiệp vụ
    ↓ đạt điều kiện
50% traffic → quan sát trong cửa sổ dài hơn
    ↓ đạt điều kiện
100% traffic → xác nhận release và lưu record
~~~

Các tỷ lệ chỉ để giải thích, không phải công thức chuẩn. Với lưu lượng thấp, 5% có thể không đủ mẫu; với giao dịch rủi ro cao, cần giới hạn theo nhóm người dùng, loại giao dịch hoặc thời điểm. Đặt thời gian quan sát dựa trên đặc tính hệ thống.

Nếu lỗi xuất hiện, không chỉ “rollback image” rồi coi như xong. Cần đánh giá migration, sự kiện đã phát, dữ liệu đã thay đổi và các side effect bên thứ ba. Có lúc phải tắt flag, tạm dừng lưu lượng, khôi phục phiên bản cũ hoặc phát hành bản sửa theo hướng roll forward.

## 18. Observability phân tách theo môi trường và phiên bản

Để kết quả từ staging có ý nghĩa và production đủ khả năng chẩn đoán, mỗi service nên có telemetry gắn nhãn môi trường và phiên bản:

~~~text
service.name = catalog-service
deployment.environment = production
service.version = 1.8.3
container.image.digest = sha256:<digest>
trace.id = <correlation-id>
~~~

Tên thuộc tính cụ thể phụ thuộc stack observability; ví dụ trên minh họa cách nhận diện, không phải một schema bắt buộc. Không cho phép nhãn chứa ID người dùng hoặc dữ liệu nhạy cảm làm tăng cardinality và rủi ro lộ dữ liệu.

Nên theo dõi:
- **Golden signals:** traffic, errors, latency, saturation.
- **Hành vi nghiệp vụ:** số đơn hàng hoàn thành, tỷ lệ checkout thành công, tồn kho bất thường.
- **Hạ tầng:** memory, CPU, queue lag, database pool, connection errors.
- **Dependency:** timeout, retry rate, circuit breaker, event processing failures.
- **Release:** thời điểm triển khai, image digest, cấu hình, người/automation phê duyệt.

Test/staging vẫn cần trace và dashboard để debug, nhưng alert routing khác production. Cảnh báo staging không nên đánh thức on-call production một cách vô tội vạ; ngược lại, phải có người nhận tín hiệu phát hành thất bại.

## 19. Chính sách bảo mật và quyền vận hành

**Nguyên tắc quyền tối thiểu:** developer có thể debug test, release owner có thể promote staging, CI có quyền publish artifact, CD identity có quyền deploy theo chính sách, còn production secrets và dữ liệu thật chỉ được truy cập bởi chủ thể cần thiết.

Ví dụ phân quyền:

| Tác nhân | Test | Staging | Production |
| --- | --- | --- | --- |
| Developer | Triển khai và debug trong phạm vi được giao | Xem log/đề xuất thay đổi | Chỉ đọc telemetry cần thiết |
| CI build identity | Build, test, publish image | Không tự ý sửa hạ tầng | Không có quyền ghi production |
| CD service identity | Deploy theo policy | Promote ứng viên đã kiểm chứng | Deploy digest đã được cho phép |
| Release owner | Xem kết quả test | Phê duyệt/gỡ blocker | Phê duyệt thay đổi rủi ro cao khi cần |
| Platform/SRE | Quản lý chuẩn hạ tầng | Bảo trì, quan sát | Incident response và thay đổi được audit |

Đây là mô hình gợi ý, phải áp dụng theo cơ chế RBAC/IAM thực tế. Cần ghi lại hoạt động thay đổi configuration, secret, network và resource của production. Quyền emergency có thể tồn tại nhưng phải có lý do, thời điểm, người sử dụng và bước hậu kiểm.

Các cơ chế quan trọng gồm: secret rotation, admission policy, artifact signature/provenance verification, image scanning, network policy, pod security, encryption at rest/in transit và audit log. Không cho môi trường test trở thành lối đi gián tiếp vào production qua IAM role hoặc network share.

## 20. Ngăn configuration drift

**Drift** là khác biệt giữa cấu hình mong muốn đã được quản lý và trạng thái đang chạy. Drift thường xuất hiện khi ai đó hotfix trực tiếp trên cluster, thay một biến môi trường ở dashboard nhưng quên cập nhật Git, hoặc chỉnh một resource thông qua console cloud.

Hậu quả:
- Staging và production có hành vi khác dù cùng image.
- Lần deploy tiếp theo ghi đè bản sửa tạm hoặc khôi phục lỗi cũ.
- Khó tái hiện sự cố vì Git không phản ánh trạng thái thực.
- Security policy bị nới mà không có review.

Cách quản lý:
1. Hạn chế quyền thay đổi trực tiếp ngoài IaC/GitOps.
2. Đối chiếu desired state với live state thường xuyên.
3. Ghi lại mọi thay đổi khẩn cấp và đưa về nguồn cấu hình canonical sau incident.
4. Cảnh báo khi production phát hiện image digest hoặc config revision ngoài release history.
5. Dùng policy validation cho các thay đổi quyền, public endpoint, secret và resource.

Cần định nghĩa rõ với từng loại drift: tự động reconcile, cảnh báo hay yêu cầu điều tra. Không bật tự khôi phục một cách mù quáng cho các tài nguyên chứa state hoặc thay đổi khẩn cấp đang phục vụ incident response.

## 21. Sự cố chỉ có ở một môi trường: cách điều tra

Ví dụ: `order-service` chạy tốt ở test và staging nhưng production bắt đầu timeout khi gọi `inventory-service`.

Thứ tự tìm nguyên nhân nên theo **sự khác biệt có thể quan sát**:
1. Kiểm tra order đang chạy image digest nào ở từng môi trường; có phải cùng ứng viên đã được test?
2. Đối chiếu config revision, timeout, retry, endpoint, DNS và quyền service identity.
3. So sánh phiên bản inventory, API contract và chính sách rate limit.
4. Kiểm tra lưu lượng, p95/p99 latency, queue lag, database pool, connection saturation và autoscaling.
5. Xem trace để xác định latency nằm ở order, network hay inventory.
6. Kiểm tra dữ liệu lớn, hot key, lock hoặc query plan chỉ xuất hiện ở production.
7. Đánh giá rollback/roll forward hoặc điều chỉnh cấu hình sau khi hiểu rủi ro.

Không kết luận “do production mạnh/yếu hơn staging” chỉ từ sự khác biệt môi trường. Cần bằng chứng runtime và release record; cùng artifact có thể gặp tải thật, dữ liệu và dependency khác.

### 21.1. Một ví dụ lỗi cross-environment

Một developer đặt `PAYMENT_URL` bằng endpoint production trong secret staging. Smoke test tạo giao dịch thanh toán thật.

Tổ chức có thể phòng tránh bằng nhiều lớp:
- Staging không có credential production.
- Network policy chặn egress tới payment production, trừ exception được duyệt.
- Cấu hình được validate để `deployment.environment=staging` chỉ dùng allowlist endpoint staging.
- Payment sandbox có dữ liệu và tài khoản riêng.
- Pipeline kiểm tra manifest/secret reference trước deploy.
- Monitoring phát hiện request từ workload identity staging tới hệ thống production.

Một lớp bảo vệ đơn lẻ có thể bị cấu hình sai; kiểm soát chéo giúp giảm khả năng gây hại.

## 22. Quản lý chi phí và vòng đời môi trường

Môi trường test có mục tiêu tốc độ và độ bao phủ, không cần chạy liên tục ở kích cỡ production. Chi phí có thể tăng mạnh khi mỗi pull request tạo một database, broker và namespace riêng mà không có chính sách dọn dẹp.

Các thực hành:
- TTL cho preview, sandbox và dữ liệu tạm.
- Quota CPU/memory/storage/network theo namespace và nhóm sở hữu.
- Tự động xóa resource sau khi pull request đóng, giữ log/test evidence theo thời hạn hợp lý.
- Tắt hoặc giảm quy mô workload nonprod ngoài giờ khi không ảnh hưởng pipeline cần chạy.
- Dùng môi trường hiệu năng chuyên biệt theo lịch cho test tải nặng.
- Gắn nhãn owner, project, môi trường, thời điểm hết hạn và cost center nếu tổ chức cần.
- Tránh xóa staging giữa một release gate đang chạy hoặc làm mất bằng chứng incident.

Không tối ưu chi phí bằng cách chia sẻ production database hoặc production credentials cho test. Ranh giới bảo mật và tính đúng đắn là điều kiện tiên quyết.

## 23. Quản lý thay đổi cấu hình, schema và feature flags

Không phải mọi thay đổi có cùng quy trình rollback:

| Loại thay đổi | Đối tượng được version hóa | Phương án khôi phục |
| --- | --- | --- |
| Code/image | Artifact digest | Rollback digest nếu dữ liệu tương thích |
| Config | Config revision, manifest Git | Revert cấu hình, kiểm tra tác động runtime |
| Secret | Secret version và identity policy | Rotate/revoke, kiểm tra tính hợp lệ và thời hạn |
| Database schema | Migration version và dữ liệu thực | Expand/contract hoặc roll forward, không giả định rollback DDL |
| Feature flags | Flag config/version và rollout rule | Disable/đổi targeting sau khi kiểm tra side effect |
| Event schema | Schema ID, producer/consumer compatibility | Giữ trường cũ, tương thích hai chiều theo chính sách |

Điều này giải thích vì sao chỉ lưu Git SHA của service là chưa đủ. Cần biết **bộ trạng thái triển khai** khi sự cố diễn ra. Với microservices, một release có thể phụ thuộc phiên bản API và schema của các dịch vụ khác. Đánh dấu dependency liên quan trong release record giúp tìm nguồn lỗi nhanh hơn.

## 24. Quy trình phát hành mẫu cho một microservice

Giả sử hệ thống thương mại điện tử có:
- `catalog-service`: thông tin sản phẩm.
- `cart-service`: giỏ hàng.
- `checkout-service`: tạo đơn.
- `notification-service`: gửi thông báo.

Nhóm catalog muốn thêm thuộc tính `productCategory` tùy chọn vào response.

**Bước A — Phát triển:** code và unit test trên nhánh tính năng. Pull request được review, chạy static analysis, dependency scan, unit tests. Preview environment có thể cho người review thử API mới trên synthetic data.

**Bước B — Tích hợp:** CI build artifact từ commit đã merge và ghi digest. Triển khai catalog vào integration test environment; consumer contract test xác nhận cart và checkout vẫn xử lý response khi trường mới xuất hiện. Test kết nối database và message broker trong phạm vi riêng.

**Bước C — Staging:** promote đúng digest vào staging. Chạy migration thêm cột theo hướng tương thích, smoke test xem sản phẩm, tìm kiếm, thêm vào giỏ. Kiểm tra cấu hình auth, endpoint, DNS, logging và readiness; quan sát metric. Nếu staging phụ thuộc phiên bản checkout có khác biệt so với production, ghi rõ trước khi duyệt.

**Bước D — Production:** pipeline xác minh nguồn artifact, chính sách và các test cần thiết. Nhóm release bắt đầu canary 5% traffic nếu phù hợp lưu lượng thực tế; kiểm tra lỗi, latency, request rate và tỷ lệ xem/thêm sản phẩm thành công. Khi đủ bằng chứng, tăng dần tới 100%.

**Bước E — Sau phát hành:** lưu record gồm digest, config revision, schema version, người/automation phê duyệt, cửa sổ canary và kết quả. Nếu bản mới lỗi, tắt flag hoặc rollback digest theo khả năng tương thích dữ liệu.

Điểm cần chú ý: cart, checkout và notification không cần deploy lại nếu hợp đồng với catalog vẫn tương thích. Quản lý môi trường tốt tạo điều kiện để từng service phát hành độc lập nhưng vẫn chia sẻ những tiêu chuẩn chung.

## 25. Kịch bản thao tác với Kubernetes và GitOps

Giả sử một tổ chức dùng Kubernetes; các phần YAML sau minh họa ý nghĩa, cần hoàn thiện theo cluster, policy và chart thực tế.

**Tham chiếu image theo digest trong deployment:**

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
  namespace: catalog-staging
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
        environment: staging
    spec:
      containers:
        - name: catalog
          image: registry.example/catalog-service@sha256:<approved-digest>
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: staging
            - name: CATALOG_DB_URL
              valueFrom:
                secretKeyRef:
                  name: catalog-staging-db
                  key: url
~~~

Trong môi trường thực tế, placeholder digest phải thay bằng SHA-256 hợp lệ. Dùng Secret reference trong PodSpec giảm việc ghi trực tiếp credential, nhưng Kubernetes Secret không tự giải quyết mọi yêu cầu bảo mật; vẫn cần encryption, RBAC, audit và external secret management khi phù hợp.

**Policy cần áp dụng bên ngoài ví dụ:**
- Chỉ workload identity staging đọc `catalog-staging-db`.
- Network policy chỉ cho phép catalog gọi dependency staging.
- Resource requests/limits và pod security theo chuẩn nền tảng.
- Readiness/liveness/startup probes được định nghĩa theo ứng dụng.
- Production dùng namespace, secret, service account và config riêng.
- Admission policy xác nhận image provenance và danh tính builder khi tổ chức yêu cầu.

**Lưu ý về giá trị môi trường:** Không để `SPRING_PROFILES_ACTIVE=staging` trở thành điều kiện duy nhất phân biệt staging với production. Identity, network và data store phải được tách bằng quyền thật.

## 26. Những anti-pattern cần tránh

### 26.1. “Staging chỉ là production thu nhỏ”

Nếu staging bỏ qua TLS, auth, queue, autoscaling hoặc migration, nhiều lỗi quan trọng không xuất hiện trước release. Mục tiêu không phải giống số máy, mà là giống những hành vi và lớp hạ tầng làm thay đổi kết quả.

### 26.2. Dùng chung database hoặc broker giữa staging và production

Một test reset database hoặc consumer staging đọc message production có thể tạo incident. Cần cô lập resource và quyền, không chỉ dùng naming convention.

### 26.3. Build lại ứng dụng ở từng môi trường

Cùng version nhưng không cùng byte; kết quả test không còn ràng buộc với production artifact. Cần promote digest bất biến.

### 26.4. Chỉ thay biến cấu hình bằng tay

Dẫn tới drift và thiếu lịch sử. Dùng IaC/GitOps, review config, audit và cơ chế emergency change có lưu vết.

### 26.5. E2E test phụ thuộc toàn bộ môi trường dùng chung

Test chậm, flaky vì nhóm khác đang deploy; khó cô lập nguyên nhân. Dùng unit, component và contract tests sớm; giữ E2E cho luồng quan trọng.

### 26.6. Thông qua staging nên chắc chắn production an toàn

Staging không thể tái hiện mọi dữ liệu, traffic và sự cố runtime. Cần canary, monitoring, alert và phương án dừng rollout.

### 26.7. Dùng quyền quản trị cho mọi pipeline

Một lỗi hoặc runner bị chiếm có thể tác động nhiều môi trường. Tách danh tính, quyền deployment và kiểm chứng artifact.

### 26.8. Rollback chỉ bằng `kubectl rollout undo`

Có thể đảo image nhưng không đảo migration, event, side effect hay config ngoài Kubernetes. Cần runbook và đánh giá dữ liệu trước khi rollback.

## 27. Checklist thiết kế môi trường cho một service mới

Khi chuẩn bị triển khai một microservice, nhóm có thể trả lời các câu hỏi:

1. Service thuộc nhóm nào, ai sở hữu vận hành và SLO?
2. Test, staging, production chạy ở cluster/account/namespace nào?
3. Database, broker, cache, bucket và external API có cô lập quyền không?
4. Những cấu hình nào được version hóa trong Git, những dữ liệu nào phải nằm trong secret manager?
5. Artifact được định danh bằng digest và promotion dùng cùng digest chưa?
6. CI chạy những loại test nào; cổng lên staging và production dựa vào bằng chứng nào?
7. Preview environment có TTL, quota và quyền mạng riêng chưa?
8. Có dữ liệu tổng hợp hoặc khử nhạy cảm đủ đại diện để kiểm thử?
9. Migration có xử lý old/new version cùng tồn tại và phương án lỗi khi chạy dở?
10. Có đủ log, metric, trace và dashboard gắn environment/version để phân tích release?
11. Ai được approve production, thay secret, can thiệp khẩn cấp và điều tra?
12. Rollback/roll forward đã được mô tả dựa trên artifact và trạng thái dữ liệu chưa?
13. Có cách phát hiện drift giữa Git/IaC và trạng thái đang chạy?
14. Có retention, backup, phục hồi và chính sách chi phí cho từng môi trường?

Checklist này là công cụ thiết kế và trao đổi giữa service team với platform team; nội dung phải được cụ thể hóa theo rủi ro của từng dịch vụ.

## 28. Bài tập vận dụng

Một hệ thống đặt hàng có `product-service`, `order-service`, `payment-service` và `notification-service`. Hiện tại:

- Test và staging dùng chung một message broker.
- Staging gọi thẳng `payment-service` production để “thử giống thật”.
- CI build một image ở test, rebuild ở staging và production.
- Nhà phát triển sửa trực tiếp environment variables trên cluster production.
- Một migration xóa cột cũ được chạy cùng lúc với rolling update `order-service`.
- Khi production lỗi, nhóm không biết pod đang chạy digest nào và chỉ có log không gắn version.

**Yêu cầu 1 — Vẽ ranh giới:** thiết kế sơ đồ mạng/dữ liệu tách test, staging và production; mô tả IAM, secret, broker topic, database, external payment sandbox. Phải chặn được một request test vô tình tạo thanh toán thật.

**Yêu cầu 2 — Thiết kế đường phát hành:** bắt đầu từ source commit, build một artifact bất biến, chạy unit/integration/contract tests, promote qua staging tới production bằng cùng digest. Nêu các cổng xác nhận và record phải lưu.

**Yêu cầu 3 — Xử lý database:** thay migration phá hủy bằng expand → migrate → contract; mô tả tương thích khi hai version `order-service` cùng tồn tại, xử lý khi migration chạy dở.

**Yêu cầu 4 — Quan sát và dừng rollout:** chọn metric kỹ thuật và nghiệp vụ của checkout/payment; đề xuất điều kiện tạm dừng canary, rollback image hoặc roll forward.

**Yêu cầu 5 — Drift và bảo mật:** mô tả cách chuyển các thay đổi production thủ công về IaC/GitOps; thiết kế quyền developer/CI/CD/release owner và cơ chế audit.

Một phương án thuyết phục phải cho thấy test có thể reset, staging đủ đại diện để kiểm chứng release, production được bảo vệ theo quyền và chính sách, đồng thời mỗi service có thể triển khai riêng khi hợp đồng tương thích.

## 29. Câu hỏi tự kiểm tra

1. Vì sao có ba namespace không chứng minh ba môi trường đã an toàn?
2. Điều gì nên giữ giống nhau giữa staging và production, và điều gì có thể khác?
3. Vì sao cần kiểm chứng staging bằng đúng artifact digest dự kiến đưa production?
4. Khi cùng digest nhưng chỉ production bị lỗi, nên so sánh những lớp nào?
5. Khác biệt giữa config revision và image digest là gì?
6. Tại sao database migration có thể cản trở rollback dù container được trả về phiên bản cũ?
7. Tình huống nào nên dùng mock, sandbox provider và dependency thật?
8. Khi nào preview environment nên bị xóa và chứng cứ nào cần lưu lại?
9. Làm sao ngăn staging consumer đọc message production?
10. Vì sao chỉ số HTTP 200 không đủ đánh giá release thành công?
11. Production nên tự reconcile mọi drift hay phải phân biệt từng loại thay đổi?
12. Tự chủ release của microservice phụ thuộc những điều kiện tương thích nào?

## 30. Kết luận

Quản lý môi trường trong microservices không chỉ là duy trì một bộ server test, staging và production. Đó là **xây dựng các ranh giới an toàn có mục đích**, quản lý hạ tầng và cấu hình có thể truy vết, thử nghiệm với dữ liệu phù hợp, promote artifact bất biến và kiểm chứng sau phát hành.

Test mang lại tín hiệu phát triển nhanh và tái lập. Staging diễn tập ứng viên release với topology và policy đủ đại diện. Production triển khai có kiểm soát, giám sát bằng cả chỉ số kỹ thuật lẫn nghiệp vụ, và có kế hoạch ứng phó sự cố.

Khi các môi trường được thiết kế đúng, mỗi microservice có thể thay đổi theo nhịp riêng mà vẫn tuân thủ hợp đồng, bảo mật, khả năng quan sát và tiêu chuẩn phát hành chung của hệ thống.

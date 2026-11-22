# Vai trò của nhóm nền tảng trong hỗ trợ phát triển tự phục vụ

Trong một tổ chức sử dụng kiến trúc microservices, mỗi nhóm phát triển có thể sở hữu vài service, API, consumer, database và pipeline triển khai riêng. Nếu muốn tạo một service mới, developer phải tự tìm cách dựng repository, xin quyền CI/CD, tạo namespace, cấp secrets, cấu hình monitoring, đăng ký tên miền, thiết lập network policy và làm tài liệu vận hành. Khi mọi nhóm làm lại những bước này theo cách khác nhau, tổ chức gặp hai vấn đề: **tốc độ phát triển giảm** và **mức độ an toàn/vận hành thiếu nhất quán**.

**Nhóm nền tảng (platform team)** giải quyết phần khó lặp lại bằng cách cung cấp **sản phẩm nền tảng nội bộ** để các nhóm phát triển có thể tự phục vụ (self-service) trong những ranh giới được quản trị. Thay vì phải gửi ticket cho từng thao tác, developer có thể chọn một “đường đi chuẩn” (*golden path/paved road*), tạo service từ template, tự lấy môi trường test, triển khai qua pipeline, xem tài liệu và xác định sự cố. Nền tảng cung cấp tự động hóa, danh tính, chính sách và khả năng quan sát; nhóm sở hữu service vẫn chịu trách nhiệm về code và kết quả nghiệp vụ.

Bài học tập trung vào **vai trò, sản phẩm, ranh giới trách nhiệm, kiến trúc, quy trình triển khai và cách đo hiệu quả** của nhóm platform engineering trong tổ chức microservices. Công cụ như Kubernetes, Backstage, Terraform, Argo CD hoặc các dịch vụ cloud chỉ là phương tiện có thể lựa chọn; mục tiêu không phải xây một portal cho đẹp mà là giảm gánh nặng nhận thức và làm cho con đường triển khai an toàn trở nên dễ sử dụng nhất.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao platform team tồn tại và thế nào là **developer self-service có kiểm soát**.
2. Phân biệt platform engineering với DevOps, SRE, infrastructure operations, security và nhóm sản phẩm.
3. Xác định khách hàng nội bộ của nền tảng, các nhiệm vụ developer thường làm và vấn đề cần giải quyết trước.
4. Thiết kế một Internal Developer Platform (IDP) gồm portal/API, service catalog, templates, CI/CD, provisioning, observability và governance.
5. Định nghĩa golden path tạo microservice, database, môi trường preview, pipeline và các thao tác day-2.
6. Áp dụng guardrails bằng policy-as-code, IAM/RBAC, quotas, approvals có chọn lọc và audit.
7. Xây dựng hợp đồng trách nhiệm rõ giữa platform team và service team, kể cả khi xảy ra sự cố.
8. Chọn mức abstraction phù hợp mà không che mất những chi tiết quan trọng của hạ tầng.
9. Đo time-to-first-deploy, lead time, change failure, reliability, adoption và trải nghiệm developer một cách cân bằng.
10. Lập roadmap nền tảng theo giá trị sử dụng, tránh xây quá nhiều tính năng trước khi có nhu cầu thực.

## 2. Bài toán trước khi có nền tảng tự phục vụ

Giả sử có 25 nhóm phát triển và khoảng 160 microservices. Mỗi service cần:

- Repository, branching/pull request conventions và code quality checks.
- Container image, registry và quản lý dependency.
- CI pipeline, artifacts và quy trình phát hành.
- Kubernetes Deployment, namespace, resources, health probes, ingress và service discovery.
- Database, queue/topic, cache hoặc object storage.
- Secrets, workload identity, IAM và network policies.
- Tracing, metrics, logging, dashboards và alerting.
- Runbooks, service catalog, ownership, on-call và tài liệu onboarding.
- Chính sách cost, security, backup, retention và disaster recovery.

Nếu mỗi nhóm tự xây các thành phần trên:

- Cùng một lỗi hạ tầng có thể được lặp lại ở hàng chục repositories.
- Một số service triển khai nhanh nhưng thiếu alert, RBAC hoặc rollback.
- Developer mới mất nhiều ngày mới biết “cách đúng để deploy”.
- Platform/infrastructure team bị quá tải ticket tạo namespace, database và quyền.
- Security phải kiểm tra thủ công nhiều triển khai không đồng nhất.
- Việc tìm service owner, API contract, SLO và dependency chậm.
- Thay đổi policy chung đòi hỏi sửa từng pipeline.
- Chi phí hạ tầng tăng do thiếu defaults và visibility theo nhóm.

Tự phục vụ không có nghĩa developer nhận quyền quản trị tùy ý. Nó có nghĩa **những yêu cầu hợp lệ, lặp lại và đã được thiết kế trước có thể được thực hiện bằng workflow đáng tin, có kiểm tra tự động và có kết quả quan sát được**.

## 3. Platform engineering là gì, và không phải gì?

**Platform engineering** là cách xây, vận hành và phát triển một tập năng lực nội bộ được đóng gói thành sản phẩm, dùng để hỗ trợ các nhóm tạo và vận hành phần mềm an toàn, nhanh hơn, ít phải hiểu mọi chi tiết hạ tầng.

Phân biệt một số vai trò:

| Vai trò | Mục tiêu chính | Ví dụ |
|---|---|---|
| **Product/service development team** | Xây và vận hành chức năng mang giá trị nghiệp vụ | Order Service, Billing API, Notification Worker |
| **Platform team** | Cung cấp workflow tự phục vụ và abstraction dùng chung | Service template, provisioning API, deployment workflow |
| **SRE** | Độ tin cậy, SLO, incident response và tự động hóa vận hành | Error budget, alerting, capacity, reliability practices |
| **Infrastructure/operations** | Năng lực hạ tầng nền, vận hành cluster/network/storage tùy mô hình tổ chức | Kubernetes clusters, network, backups |
| **Security/IAM** | Chính sách bảo mật, nhận diện, kiểm soát quyền và bằng chứng tuân thủ | Identity federation, policy, secret governance |
| **Architecture enablement** | Định hướng hợp đồng và tiêu chuẩn kỹ thuật xuyên nhóm | API conventions, data ownership, integration patterns |
| **Developer experience (DevEx)** | Tối ưu hành trình phát triển và giảm ma sát công cụ/quy trình | Documentation, templates, feedback, workflow UX |

Trong thực tế, một tổ chức nhỏ có thể gộp nhiều chức năng vào cùng nhóm; một tổ chức lớn tách thành các team chuyên biệt. Điều quan trọng là **rõ sản phẩm và trách nhiệm**, không phải tên bộ phận.

### 3.1. Những hiểu nhầm thường gặp

- “Có Kubernetes là có nền tảng”: Kubernetes cung cấp primitive hạ tầng nhưng không tự giải quyết đường tạo service, quyền, docs, chuẩn vận hành và trải nghiệm developer.
- “Mọi thao tác phải qua platform team”: như vậy platform trở thành helpdesk và bottleneck, trái mục tiêu self-service.
- “Dùng một template cho mọi use case”: các workload HTTP, batch, streaming, stateful có nhu cầu khác nhau.
- “Platform chịu trách nhiệm mọi sự cố của mọi service”: platform giữ nền tảng và hợp đồng của nó; service team vẫn phải sở hữu hành vi nghiệp vụ, code và SLO theo thỏa thuận.
- “Portal là sản phẩm”: portal chỉ là giao diện; giá trị nằm ở workflows hoạt động được, guardrails, APIs và support.
- “Đã có CLI nên tài liệu không cần”: API, CLI và portal vẫn cần mô tả contract, lỗi, ví dụ và escalation.

## 4. Nền tảng là sản phẩm dành cho người dùng nội bộ

Platform team cần tư duy như nhóm phát triển sản phẩm:

1. **Khách hàng:** developer, tech lead, QA, SRE, security, data engineer, nhóm sản phẩm.
2. **Jobs to be done:** tạo service, triển khai an toàn, tìm dependency, xin database, xem log, rollback, xoay credential.
3. **Value proposition:** bớt thao tác lặp lại, ít lựa chọn khó, có mặc định tốt và phản hồi nhanh.
4. **Product contract:** những tính năng được hỗ trợ, API, giới hạn, quyền, SLA/SLO, versioning.
5. **Feedback:** discovery interviews, support tickets, usage telemetry, khảo sát developer, shadowing.
6. **Roadmap:** ưu tiên vấn đề có tác động lớn tới nhiều nhóm, không chỉ công nghệ thú vị.
7. **Support:** docs, self-diagnostics, issue tracker, on-call và lịch deprecation.
8. **Adoption:** đo chất lượng hành trình thật, không chỉ số lượt vào portal.

Nền tảng tốt giúp developer làm việc **với nền tảng** chứ không phải **xin phép nền tảng** cho từng bước. Trong trường hợp rủi ro cao, workflow có thể yêu cầu approval; sự phê duyệt phải là điểm kiểm soát có lý do, có scope và có lịch sử, không phải cổng thủ công bắt buộc với tất cả thay đổi.

### “Khách hàng” có thể có nhu cầu đối lập

- Developer muốn tạo môi trường ngay lập tức.
- Security muốn ngăn cấp quyền quá rộng.
- Finance muốn kiểm soát cost.
- SRE muốn workloads có readiness, limits và alerts.
- Platform muốn chuẩn hóa để giảm gánh vận hành.

Thiết kế self-service phải đưa các mục tiêu này vào **defaults và policy**: tạo được môi trường nhanh nhưng chỉ trong quota; lấy được secret nhưng qua identity đúng; triển khai nhanh nhưng phải qua CI checks và giới hạn blast radius.

## 5. Hiểu “cognitive load” của developer

Mỗi microservice có nhiều khái niệm ngoài bài toán nghiệp vụ: DNS, TLS, mTLS, connection pools, Kubernetes manifests, IAM roles, pipeline syntax, broker ACL, storage classes, dashboards. Khi developer phải hiểu tất cả để thực hiện một việc đơn giản, thời gian phát triển và xác suất lỗi đều tăng.

**Cognitive load** là lượng kiến thức/ra quyết định mà một nhóm phải mang để hoàn thành công việc. Platform không xóa các chi tiết kỹ thuật khỏi thế giới, mà **đóng gói các quyết định lặp lại thành những lựa chọn có tên, có giới hạn và có đường thoát khi cần**.

Ví dụ nhu cầu nghiệp vụ: “Tôi muốn một HTTP service Java kết nối PostgreSQL trong staging.”

Thay vì yêu cầu developer tự viết nhiều file YAML, nền tảng có thể đưa ra các lựa chọn:

~~~text
Workload type: HTTP API
Runtime: Java
Environment: staging
Database: PostgreSQL
Data class: internal
Availability profile: standard
Team owner: payments
~~~

Sau khi nhận dữ liệu, hệ thống tạo repository, pipeline, workload identity, database instance/schema, health/observability và service catalog record theo chính sách. Những gì thật sự không thể tự quyết định, như quyền truy cập dữ liệu cực nhạy cảm, vẫn phải chuyển qua workflow phê duyệt cụ thể.

## 6. Internal Developer Platform (IDP): kiến trúc tham chiếu

IDP không nhất thiết là một sản phẩm duy nhất. Thường nó là tập thành phần được kết nối bằng một contract chung:

~~~text
                      Developer
               CLI / Portal / IDE / API
                         |
                         v
               Developer Experience Layer
              - catalog, docs, templates
              - workflows, permissions
                         |
                         v
               Platform Control Plane
              - workflow orchestration
              - policies & approvals
              - identity & audit
              - resource ownership
                         |
             +-----------+------------+
             |                        |
             v                        v
     Delivery Capabilities     Resource Capabilities
     - source repository       - namespace/runtime
     - build/test pipeline     - database/cache/broker
     - artifact registry       - secrets/workload identity
     - GitOps/deployment       - DNS/network/storage
             |                        |
             +-----------+------------+
                         |
                         v
                  Runtime Environments
                 clusters, cloud, services
                         |
                         v
             Metrics / logs / traces / cost
                         |
                         v
                Feedback & Governance
~~~

Các thành phần điển hình:

- **Service catalog:** danh sách services, owner, API, dependencies, on-call, SLO, docs.
- **Self-service portal:** giao diện tạo service, chọn template, yêu cầu tài nguyên và xem trạng thái.
- **Scaffolding templates:** mã khởi đầu, CI, Dockerfile, tests, configs, deployment manifests và docs.
- **Provisioning workflows:** tạo namespace, database, broker topic, cloud storage, secrets/identity.
- **Delivery platform:** CI/CD, artifact signing, GitOps, progressive rollout, rollback.
- **Security and governance:** RBAC/IAM, policy-as-code, approvals, audit và cost quotas.
- **Operational experience:** dashboards, alerts, health, logs/traces, runbooks và support.

Không phải mọi nơi cần portal ngay. Một nhóm nhỏ có thể bắt đầu bằng repository template, CLI và workflow API, rồi bổ sung catalog/portal khi nhu cầu discovery và số lượng services tăng.

## 7. Self-service phải có hợp đồng rõ

Một năng lực được gọi là tự phục vụ khi người dùng có thể thực hiện từ đầu đến cuối trong phạm vi được phép, không phải nhắn người vận hành để hoàn tất nửa sau.

Ví dụ “Request PostgreSQL database” cần contract:

| Trường | Ý nghĩa |
|---|---|
| Input | Owner team, environment, data classification, sizing tier, backup profile |
| Eligibility | Ai được tạo database trong môi trường nào |
| Policy | Quota, region, encryption, network, naming, retention, approvals |
| Workflow | Validate → provision → verify → register → notify |
| Output | Database reference, connection endpoint, credential mechanism, status |
| Failure | Error code, retry/recovery, cleanup, escalation |
| Ownership | Ai chịu trách nhiệm DB engine, schema, queries, cost và backup |
| Lifecycle | Upgrade, resize, rotate, suspend, delete, restore |
| Audit | Ai yêu cầu, policy version nào, resource IDs, kết quả |
| SLO | Thời gian xử lý, tỷ lệ thành công, availability của control plane |

Người dùng cần biết **được hỗ trợ điều gì, kết quả là gì và nếu thất bại phải làm gì**. Một biểu mẫu chỉ “gửi ticket tới platform team” chưa đạt self-service automation, dù giao diện đẹp.

## 8. Golden paths: con đường mặc định an toàn

Golden path là quy trình đã được platform team đóng gói, kiểm thử và hỗ trợ để xử lý một use case phổ biến. Nó tạo **defaults đáng tin** để developer không phải tự tái phát minh từng phần.

Ví dụ các golden paths:

| Loại workload | Các năng lực mặc định |
|---|---|
| HTTP REST API | Service skeleton, health probes, auth conventions, tracing, CI, deployment |
| gRPC service | Protobuf structure, contract checks, service identity, observability |
| Event consumer | Broker config, idempotency template, DLQ policy, lag alerts |
| Scheduled job | Schedule, concurrency policy, retries, logs/metrics, execution identity |
| Batch data pipeline | Dataset ownership, schema contracts, lineage, checkpoints, costs |
| Public frontend | Build, CDN, caching, TLS, runtime config, monitoring |
| Internal admin tool | Access policy, audit log, environment isolation |

### Nguyên tắc thiết kế

- Bắt đầu bằng **mẫu được dùng thường xuyên**, không ôm mọi trường hợp.
- Template sinh mã có các kiểm tra tối thiểu, không chỉ thư mục trống.
- Default có lý do và được version hóa, ví dụ timeout, resource requests, readiness.
- Phân biệt **bắt buộc** (security invariants) và **khuyến nghị** (style/architecture).
- Có đường tùy biến chính thức cho những workloads không khớp.
- Template có owner, hỗ trợ, changelog, deprecation và upgrade path.
- Developer có thể hiểu “đã tạo những gì” và sửa business code bình thường.
- Không khóa developer vào abstraction không thể debug.

Golden path là **đường được khuyến khích**, không đồng nghĩa mọi team bị buộc dùng duy nhất một stack. Những ngoại lệ có giá trị phải được xem xét theo chi phí và rủi ro, có ownership và governance rõ, tránh biến đường tắt không được hỗ trợ thành chuẩn ngầm.

## 9. Hành trình tạo một microservice tự phục vụ

Một developer muốn tạo `inventory-reservation-service`:

~~~text
1. Chọn "New Java HTTP Service" trong portal/CLI
                     |
                     v
2. Nhập owner, service name, data class, repo access
                     |
                     v
3. Validate naming, permissions, quotas, policy
                     |
                     v
4. Generate repository từ template đã version hóa
                     |
                     v
5. Register service catalog + docs + on-call owner
                     |
                     v
6. Provision runtime identity + namespace/config
                     |
                     v
7. Configure CI pipeline, registry, GitOps manifest
                     |
                     v
8. Deploy to development, run smoke/health checks
                     |
                     v
9. Trả URL, dashboards, runbook, docs, status
~~~

### Những điều một workflow tốt phải bảo đảm

- Tất cả tài nguyên có owner và định danh duy nhất, tránh trùng tên.
- Nếu bước 7 lỗi, workflow có thể tiếp tục/rollback phần đã tạo, không bỏ lại quyền và tài nguyên mồ côi.
- Không dùng shared admin credential để thao tác theo danh tính developer.
- Secrets được tạo qua secret manager hoặc identity flow, không in giá trị vào portal/CI logs.
- Hành động có audit record: caller, action, approval, generated resource IDs, status.
- Template version và commit nguồn được ghi để sau này nâng cấp.
- Hệ thống trả **trạng thái thật**; không thông báo “success” khi cluster chưa triển khai hoặc smoke test chưa đạt.
- Có timeouts và error messages có thể hành động, ví dụ `QUOTA_EXCEEDED` hoặc `NAME_CONFLICT`.

## 10. Ví dụ mô tả yêu cầu tạo service

Một API tự phục vụ có thể nhận manifest (schema minh họa, không phải định dạng bắt buộc của công cụ cụ thể):

~~~yaml
apiVersion: platform.example/v1
kind: ServiceRequest
metadata:
  name: inventory-reservation
spec:
  ownerTeam: fulfillment
  workloadType: http-api
  runtime: java
  environment: development
  deploymentProfile: standard
  dataClassification: internal
  dependencies:
    - type: postgresql
      tier: small
    - type: messaging
      topic: inventory-reservation-events
  observability:
    tracing: enabled
    alertsProfile: http-standard
  exposure:
    mode: internal
~~~

Nền tảng kiểm tra:

1. `ownerTeam` có tồn tại trong hệ thống quản trị không?
2. Caller có thuộc team và được tạo resource trong environment này không?
3. `workloadType`/`runtime` có nằm trong supported catalog không?
4. `tier` và quota có phù hợp chi phí không?
5. Data classification có cho phép region/runtime đó không?
6. Tên service/topic có va chạm hoặc vi phạm convention không?
7. Có yêu cầu approval nếu target là production hoặc tài nguyên đắt/nhạy cảm không?
8. Dependency và ownership có tạo sự phụ thuộc hoặc quyền truy cập không hợp lệ không?

Sau khi validate, hệ thống tạo các tài nguyên và trả lại references, không nhúng credentials vào response. Input phải có schema, type constraints, giới hạn độ dài và versioning; không cho phép user chèn Kubernetes YAML tùy ý với quyền vượt kiểm soát.

## 11. Service catalog và discoverability

Không chỉ tạo mới; developer còn phải tìm được **service hiện có** để tránh xây trùng và biết cách tích hợp.

Một service catalog có thể mô tả:

- Service ID, tên hiển thị, domain và business capability.
- Team owner, contact, on-call, escalation.
- Repository, API documentation và schema registry references.
- Runtime, môi trường triển khai, maturity/lifecycle.
- Upstream/downstream dependencies và dữ liệu sở hữu.
- SLO/SLI, dashboards, alerts, runbooks.
- Bản release đang chạy và deployment health.
- Data classification, security controls, compliance profile.
- Cost center hoặc cost allocation tags.
- Bằng chứng service được tạo từ template nào và version nào.

### Ví dụ descriptor khái niệm

~~~yaml
service:
  id: order-api
  displayName: Order API
  owner:
    team: commerce-orders
    onCallRef: oncall-commerce-orders
  lifecycle: production
  kind: http-api
  repositoryRef: repo-order-api
  apiRef: openapi-order-v3
  dependencies:
    - inventory-api
    - payment-api
    - orders-db
  operational:
    sloRef: slo-order-api
    dashboardRef: dashboard-order-api
    runbookRef: runbook-order-api
  platform:
    template: java-http-service
    templateVersion: "2.4"
    deploymentProfile: critical
~~~

Đây là descriptor minh họa, không phải YAML đặc thù của Backstage hoặc Kubernetes. Với công cụ catalog cụ thể, dùng schema và định danh thật theo phiên bản.

### Catalog phải có owner và cập nhật được

Một catalog được tạo khi onboarding rồi không được cập nhật có thể gây hại: người trực đã đổi, endpoint ngừng dùng, SLO chưa theo phiên bản hiện tại. Ưu tiên đồng bộ metadata từ repository, CI/CD, registry, IAM và monitoring **khi nguồn dữ liệu đủ tin cậy**, thay vì bắt developer điền thủ công những thông tin có thể tự lấy.

Không cho người dùng tự sửa `ownerTeam` của service production trong portal để trốn trách nhiệm; thay owner cần có cơ chế xác minh và bàn giao.

## 12. Tài liệu là một phần của giao diện sản phẩm

Một self-service API thiếu ví dụ, limitations và cách sửa lỗi vẫn tạo support tickets. Developer documentation nên được tổ chức theo **user journey**, không chỉ liệt kê tất cả nút của portal.

Tối thiểu mỗi năng lực nên có:

1. **Quickstart:** từ trạng thái chưa có gì đến kết quả nhỏ nhưng hoạt động.
2. **When to use:** điều kiện sử dụng và giới hạn được hỗ trợ.
3. **Inputs/outputs:** schema, defaults, ví dụ hợp lệ.
4. **Security:** identity, quyền, nơi lưu secret và dữ liệu.
5. **Error handling:** nguyên nhân lỗi, self-diagnostics, retry/cleanup.
6. **Lifecycle:** nâng phiên bản, xóa, restore, rotate, scale.
7. **SLO/support:** trạng thái service, kênh hỗ trợ và escalation.
8. **Advanced path:** cách vượt abstraction khi trường hợp đặc biệt hợp lệ.
9. **Changelog:** thay đổi breaking/deprecation và migration instructions.

Một quickstart tốt xác minh hành trình đầy đủ, không chỉ hướng dẫn chạy lệnh tạo repo. Developer nên nhìn thấy service mới trên catalog, build xanh, endpoint health trả kết quả đúng và dashboard đã xuất hiện.

## 13. Nền tảng cung cấp API, CLI, portal hay cả ba?

Các bề mặt dùng chung không thay thế nhau hoàn toàn:

| Bề mặt | Lợi thế | Giới hạn |
|---|---|---|
| **Portal** | Dễ khám phá, tổng hợp thông tin và trạng thái | Dễ biến thành nhiều form phức tạp hoặc click ops |
| **CLI** | Nhanh trong terminal, dễ script | Cần phân phối phiên bản, docs, xử lý credentials và error output |
| **API** | Có thể tự động hóa, tích hợp IDE/CI/ChatOps | Cần contract, idempotency, authz, lifecycle và backward compatibility |
| **GitOps pull request** | Review/audit rõ, reconcile desired state | Không luôn phù hợp cho hành động tức thời hoặc quy trình nhiều giai đoạn |
| **IDE integration** | Giảm chuyển ngữ cảnh cho developer | Phải bảo đảm phù hợp API và quyền của platform |

Một kiến trúc hợp lý là **cùng một backend workflow và policy** cho portal, CLI và API. Nếu portal thực hiện một đường tạo namespace riêng và CLI dùng script khác, quy tắc quyền dễ lệch.

Ví dụ:

~~~text
Portal ----\
CLI --------+--> Self-Service API --> Policy --> Orchestrator --> Resources
CI/GitOps --/                         |
                                      +--> Audit / Status / Events
~~~

API nên hỗ trợ request ID và idempotency key cho các thao tác tạo resource để retry network không vô tình tạo trùng database hoặc namespace.

## 14. Control plane và data plane

Một lỗi thiết kế thường thấy là buộc mọi request người dùng chạy qua portal/backend platform. Cần phân biệt:

- **Control plane:** khai báo, cấp phát, áp policy, quản lý lifecycle và trạng thái tài nguyên.
- **Data plane:** request của khách hàng thực sự đi qua microservice, database, cache, broker và network runtime.

Ví dụ:

~~~text
CONTROL PLANE
Portal / API / GitOps -> orchestrator -> K8s API / IAM / DB provisioner
                              |
                              v
                          Desired State

DATA PLANE
Customer -> Gateway -> Order Service -> Database / Broker
~~~

Nếu portal down, microservices production nên tiếp tục phục vụ theo thiết kế. Portal outage có thể làm chậm việc tạo mới hoặc deploy, nhưng không nên tự làm critical request path ngừng hoạt động nếu không có lý do kiến trúc cụ thể.

Control plane cần có HA, backup và khôi phục nhưng mục tiêu SLO khác data plane. Cần đặc biệt cẩn trọng với platform policy proxy hoặc dynamic config nằm trong từng request; nếu nó lỗi có thể ảnh hưởng dịch vụ ngay.

## 15. Ranh giới trách nhiệm: platform team và service teams

Mô hình **“you build it, you run it”** và platform engineering không mâu thuẫn khi trách nhiệm được định nghĩa rõ.

| Phạm vi | Platform team | Service team |
|---|---|---|
| Cluster/runtime nền | Vận hành hoặc cung cấp contract năng lực được hỗ trợ | Sử dụng trong profile/quota hợp lệ |
| Service template | Xây, version, kiểm thử và bảo trì template | Chọn, tùy biến business code và cập nhật dependency của service |
| CI/CD capability | Cung cấp runner, workflow primitives, signing/policy | Sở hữu test coverage và release của service |
| Workload identity | Cung cấp cơ chế tin cậy, policy và lifecycle | Khai báo quyền cần thiết, không dùng sai credentials |
| Database provisioning | Tạo/vận hành hạ tầng theo profile | Sở hữu schema, query, migration và data correctness, trừ khi đã thỏa thuận khác |
| Observability | Cung cấp pipeline và mẫu dashboard/alerts | Định nghĩa domain SLI, quan sát service và xử lý lỗi code |
| SLO nền tảng | Định nghĩa availability của provisioning/delivery/runtime capabilities | Định nghĩa SLO của API/business operation |
| Cost policy | Cung cấp quota, tagging, dashboards và budgets | Chọn tài nguyên phù hợp, xử lý chi phí của workload |
| Incident | Khôi phục năng lực nền, phối hợp cross-service | Khôi phục hành vi service, xác minh dữ liệu/side effects |

Bảng là mô hình mẫu. Khi dùng managed database hay SaaS, trách nhiệm engine/backup có thể nằm ở provider; ownership phải được mô tả theo contract thực tế, không tự suy đoán.

### 15.1. Nên tránh “đẩy việc” dưới tên self-service

Platform chỉ đưa một file Terraform dài cho developer rồi tuyên bố “tự phục vụ” có thể chỉ chuyển việc hạ tầng xuống đội sản phẩm. Một golden path đúng phải giảm các quyết định không liên quan đến business, trong khi vẫn cho service team khả năng quan sát và xử lý khi lỗi.

Ngược lại, nếu platform team phải duyệt mỗi thay đổi application code, đó là dấu hiệu platform đang chặn autonomy. Hai nhóm cần thương lượng ranh giới tự chủ và guardrails phù hợp.

## 16. Self-service provisioning: quy trình chứ không chỉ nút bấm

Một workflow cấp tài nguyên thường có nhiều bước không nguyên tử:

~~~text
Request
  |
  v
Authenticate caller
  |
  v
Authorize scope + apply policy
  |
  v
Reserve name / quota / budget
  |
  v
Create desired state / PR
  |
  v
Provision resource
  |
  v
Verify health + permissions
  |
  v
Register ownership / catalog
  |
  v
Return references & operation status
~~~

Vấn đề thực tế:

- API timeouts nhưng Terraform đã tạo resource.
- Người dùng bấm “Create” hai lần.
- Database tạo thành công nhưng cấp quyền thất bại.
- Resource có nhưng chưa route network.
- Đã tạo quyền quá rộng rồi không rollback khi provisioning fail.
- Controller nhận request v1 nhưng template v2 vừa được nâng cấp.

Giải pháp: idempotency key, operation ID, state machine bền vững, reconciliation, deadline, resource tags, ownership, retry có giới hạn và cơ chế cleanup/compensation. Không ghi `SUCCESS` trước khi kiểm tra đủ các hậu điều kiện theo contract.

### 16.1. Trạng thái một workflow

~~~text
REQUESTED -> VALIDATING -> APPROVED? -> PROVISIONING
    |             |             |              |
    |             +-- REJECTED  |              +-- FAILED
    |                           |              |
    +---------------------------+              v
                                          VERIFYING
                                              |
                                  +-----------+----------+
                                  |                      |
                                READY                  DEGRADED
                                  |                      |
                                  v                      v
                              REGISTERED            RECONCILE
~~~

State machine chỉ minh họa. Trạng thái bị lỗi phải có mã nguyên nhân, khả năng retry an toàn hoặc hướng dẫn dọn tài nguyên. Người dùng cần xem được operation history thay vì chỉ một spinner không kết thúc.

## 17. Templates phải có tests và vòng đời

Service template là một dependency kỹ thuật, không phải đoạn mã mẫu được copy rồi bỏ quên.

Ví dụ cấu trúc Java HTTP service:

~~~text
inventory-reservation/
├── README.md
├── build.gradle
├── settings.gradle
├── src/
│   ├── main/java/.../
│   └── test/java/.../
├── Dockerfile
├── .github/workflows/ci.yml
├── deploy/
│   ├── base/
│   └── overlays/
├── docs/
│   ├── api.md
│   ├── runbook.md
│   └── slo.md
└── catalog/
    └── service.yaml
~~~

Một template đáng dùng thường được kiểm tra:

- Scaffold tạo repository hợp lệ với tên/owner khác nhau.
- Project compile và unit test pass.
- Container build reproducible và không chạy với quyền không cần thiết.
- Health/readiness và graceful shutdown hoạt động.
- Correlation/trace context và structured logging được cấu hình an toàn.
- Secret không nằm trong code hoặc CI logs.
- Deployment có labels, resource requests/limits và rollout policy phù hợp.
- Pipeline chạy cả policy checks và contract tests theo workload.
- Dashboard/alerts có owner và SLI mặc định hữu ích.
- Documentation và runbook link không bị hỏng.

### Nâng template sau khi đã tạo hàng trăm service

Một khó khăn lớn là **template drift**. Khi phiên bản template mới có security fix, không thể chỉ sửa template repository và coi mọi service cũ đã được vá. Cần:

1. Lưu template ID/version trong catalog.
2. Biết service nào còn dùng cấu hình/pipeline đã lỗi thời.
3. Ưu tiên các security-critical controls có thể áp tập trung qua admission/policy.
4. Cung cấp migration PR hoặc codemod khi cần cập nhật code/template.
5. Có changelog, compatibility window và deprecation deadline.
6. Đo adoption và lỗi migration.
7. Cho teams biết thay đổi nào là bắt buộc, thay đổi nào tùy chọn.

Không tự sửa hàng trăm repository production mà thiếu test, ownership và rollback; self-service upgrade path cũng cần kiểm soát phát hành.

## 18. CI/CD như một năng lực nền tảng

Một golden path có thể có pipeline tiêu chuẩn:

~~~text
Pull Request
  -> lint + compile + unit tests
  -> static analysis + secret scan
  -> contract tests
  -> build artifact
  -> SBOM / provenance / signature theo policy
  -> integration smoke tests
  -> deploy development
  -> staging verification
  -> production progressive rollout
  -> SLO/business gates
  -> release record
~~~

Platform team có thể cung cấp reusable workflow, runner pool, artifact registry, identity federation và deployment controller. Service team sở hữu test cases của domain, compatibility với consumer và quyết định phát hành theo policy.

### Điểm quan trọng

- **Build một lần, promote cùng artifact.** Dùng image digest bất biến.
- **Không cấp production admin credentials cho job build** nếu job chỉ cần compile.
- **Deploy identity khác runtime identity.** CI có quyền phù hợp với môi trường.
- **Có concurrency control.** Hai rollout không đè nhau trên cùng service.
- **Có rollback/abort.** “Deploy successful” chỉ là một bước, chưa chứng minh business flow hoạt động.
- **Không bypass policy vì nhanh.** Emergency path cần owner, evidence và audit.
- **Giữ đường thoát.** Với workload đặc thù, cho phép pipeline extension có kiểm soát.

Nền tảng nên cung cấp **khả năng delivery** (deploy/rollback/observe) chứ không chỉ một file YAML CI làm mẫu.

## 19. Guardrails: tự chủ trong ranh giới quản trị

Đặt mọi quyết định vào approval thủ công sẽ làm chậm delivery. Cho mọi developer quyền quản trị mọi resource lại tạo rủi ro lớn. Guardrails là các quy tắc được nhúng vào workflow và runtime.

Các nhóm guardrails:

| Nhóm | Ví dụ |
|---|---|
| **Identity & access** | Caller thuộc team owner; workload identity riêng; role tối thiểu |
| **Security** | Image source được tin cậy, non-root, TLS, secret manager, policy admission |
| **Reliability** | Health checks, resource requests, rollout budget, SLO/alerts |
| **Cost** | Namespace quotas, database tier allowlist, budget tags, idle cleanup |
| **Data** | Region theo classification, encryption, backup, retention, access audit |
| **Networking** | Approved ingress, egress destinations, DNS, service-to-service policy |
| **Compliance** | Approval cho dữ liệu nhạy cảm, record thay đổi và evidence |
| **Lifecycle** | Owner bắt buộc, expiry cho preview, policy deprecation và cleanup |

Tự phục vụ có kiểm soát nghĩa là một yêu cầu hợp lệ **qua nhanh**, yêu cầu không hợp lệ **bị từ chối sớm với lý do rõ**, yêu cầu ngoại lệ **đi qua quy trình có chủ sở hữu**.

### 19.1. Policy-as-code

Các quy tắc có thể được kiểm tra trong CI, admission controller hoặc workflow API. Ví dụ chính sách khái niệm:

~~~text
IF environment = production:
    REQUIRE service_owner
    REQUIRE approved_image_digest
    REQUIRE workload_identity
    REQUIRE readiness_probe
    REQUIRE resource_requests
    REQUIRE telemetry_profile
    REQUIRE deployment_gate_policy

IF data_classification = restricted:
    REQUIRE approved_region
    REQUIRE encryption_profile
    REQUIRE security_approval
    DENY public_ingress_unless_exception

IF requested_database_tier > team_quota:
    HOLD for budget review

IF wildcard_cluster_permissions requested:
    DENY unless formally approved exception
~~~

Đây là pseudocode, không phải cú pháp OPA/Rego hay một policy engine thực tế. Các conditions cần được kiểm thử bằng những manifest hợp lệ và cố ý vi phạm, đồng thời có policy version/audit.

## 20. Không dùng “security by ticket”

Giả sử developer muốn service đọc một object trong storage. Một cách tốn công:

~~~text
Developer -> ticket -> platform operator
          -> cloud console -> shared service key
          -> gửi key qua chat -> developer cấu hình
~~~

Một cách self-service có kiểm soát:

~~~text
Developer -> self-service request
          -> verify team/environment/data scope
          -> apply IAM permission template
          -> bind workload identity
          -> return resource reference
          -> log audit and policy version
~~~

Tập trung vào **quyền hạn được cấp**, không cung cấp access key dài hạn cho mọi Pod. Nếu cloud hỗ trợ OIDC/workload identity, dùng token ngắn hạn với audience/subject/scope phù hợp. Không coi Kubernetes ServiceAccount tự động có cloud IAM permission nếu chưa thiết lập trust policy.

Một platform team nên làm việc với Security để **chuẩn hóa phần có thể tự động**, thay vì gom mọi yêu cầu về một người có quyền root.

## 21. Secrets và cấu hình dưới dạng dịch vụ tự phục vụ

Một workload có thể cần DB credential, API token, certificate hoặc signing key. Golden path nên:

1. Phân loại giá trị cần cấp là secret hay non-secret.
2. Chọn cơ chế: secret manager, workload identity, managed identity hoặc Kubernetes Secret theo policy.
3. Cấp quyền theo đúng workload/environment.
4. Giữ secret ngoài Git, build logs và portal response.
5. Thiết kế rotation, expiry, revocation và audit.
6. Cho phép developer xem **trạng thái/reference/version** mà không lộ giá trị.
7. Có hướng dẫn xử lý thiếu key, IAM denied, token refresh failure.
8. Kiểm thử rằng secret không chảy vào log/trace/baggage.

Self-service không nghĩa portal hiển thị raw secret của production. Một user có quyền deploy không nhất thiết có quyền xem credential. Dùng separation of duties để người tạo cấu hình, người cấp quyền và runtime identity không tự động có mọi quyền giống nhau.

### 21.1. Sự khác biệt giữa env và volume

Kubernetes Secret dùng dưới dạng environment variable không tự cập nhật trong process khi object thay đổi; Pod thường cần rollout/restart. Mounted Secret/ConfigMap volume có thể cập nhật theo cơ chế eventual update, nhưng ứng dụng phải reload và mount `subPath` có ngoại lệ. Platform cần cung cấp rotation workflow phù hợp, không tuyên bố “đã update secret manager” là mọi app lập tức dùng credential mới.

## 22. Observability có sẵn ngay từ ngày đầu

Nếu một service được scaffold mà không có health checks, dashboards và tracing, nhóm sẽ phải bổ sung sau khi có sự cố. Platform có thể cung cấp defaults:

- OpenTelemetry instrumentation/profile theo runtime.
- Structured logging với trace correlation và redaction.
- Metrics HTTP/gRPC/message processing và resource saturation.
- Base dashboards theo service/version/environment.
- Alert rules dùng SLO và dependency health.
- Runbook template, links trong service catalog.
- Release/config annotations trên dashboard.
- Quy trình truy xuất log/trace theo team với RBAC.
- Retention và sampling policy theo data classification.

Nhưng platform không thể tự biết business correctness của mọi service. Service team phải định nghĩa những tín hiệu như **orders completed, payments reconciled, inventory reservations valid** và mục tiêu SLO của luồng mình sở hữu.

### 22.1. Tránh metric “đẹp” nhưng không giúp vận hành

Một dashboard CPU xanh không chứng minh checkout hoạt động. Cần đo cả:

~~~text
HTTP success ratio
p95/p99 latency
dependency timeout/error rate
queue lag / consumer processing latency
business completion ratio
data integrity / idempotency failures
deployment health by version
~~~

Platform cung cấp instrumentation và cơ chế query; service team cung cấp định nghĩa business-specific và xử lý suy giảm. Metadata labels không nên chứa user ID, email, raw URL hoặc secret.

## 23. SLO của sản phẩm nền tảng

Nếu self-service API tạo database lỗi trong giờ làm việc, nhiều teams có thể bị chặn. Bản thân platform là một sản phẩm vận hành và cần SLO.

Ví dụ các chỉ số:

| Năng lực | SLI minh họa |
|---|---|
| Service provisioning | Tỷ lệ request hợp lệ hoàn tất trong thời hạn |
| Deployment controller | Tỷ lệ thao tác deploy hợp lệ được xử lý đúng |
| Artifact registry | Read/write availability và latency |
| Secrets integration | Tỷ lệ cấp/refresh credential thành công |
| Developer portal | Availability và thời gian phản hồi của các workflow trọng yếu |
| Policy evaluation | Tỷ lệ quyết định chính xác/đầy đủ và latency |
| Catalog | Độ mới metadata, tỷ lệ service có owner hợp lệ |
| Documentation | Tỷ lệ quickstart pass trong môi trường kiểm chứng |
| Support | Time to first meaningful response, resolution time theo priority |

Mục tiêu không nhất thiết giống SLO của dịch vụ kinh doanh. Ví dụ portal chưa sẵn sàng trong 5 phút có thể không làm checkout production ngừng hoạt động, nhưng gây trễ việc khắc phục sự cố nếu portal là đường duy nhất mở rollback.

### Tách control plane và runtime dependencies

Một nguyên tắc tốt là runtime service không phụ thuộc đồng bộ vào portal cho mọi request. Nếu platform control plane tạm unavailable, những service đã được triển khai nên tiếp tục phục vụ khi có thể; cũng cần có đường break-glass có audit để khôi phục service nếu control plane chính bị lỗi.

## 24. Day-2 operations: nền tảng không kết thúc ở “Create”

Khởi tạo service chỉ là một phần rất nhỏ trong vòng đời. Nền tảng phải xử lý hoặc hỗ trợ:

- Nâng runtime và dependency.
- Thay cấu hình theo môi trường.
- Xoay secret/certificate.
- Scale replicas và resource limits.
- Tạo replica/read-only database hoặc thay storage tier.
- Thêm topic/queue, permission hoặc endpoint.
- Mở/đóng feature flag, canary rollout và rollback.
- Debug lỗi readiness, image pull, DNS, IAM, connection pool.
- Nâng Kubernetes cluster, API deprecations và runtime images.
- Restore backup, failover và disaster recovery drill.
- Di chuyển service sang team owner khác.
- Sunset/decommission service và dữ liệu.
- Xem chi phí, quota, risk và trạng thái compliance.

Nếu portal chỉ có nút “Create Service” nhưng mọi thay đổi tiếp theo đều cần ticket, phần gánh nặng lớn vẫn tồn tại.

### 24.1. Một menu day-2 minh họa

~~~text
My Services
  └── order-api
      ├── Deploy revision
      ├── Rollback revision
      ├── Adjust autoscaling profile
      ├── Request database tier change
      ├── Rotate secret reference
      ├── View SLO / dashboard / traces
      ├── View dependency graph
      ├── Start approved incident runbook
      ├── Manage on-call / ownership
      └── Request decommission
~~~

Không phải thao tác nào cũng hoàn toàn tự động. Ví dụ xóa database production có thể yêu cầu backup, xác nhận chủ dữ liệu và approval nhiều bước. Điều quan trọng là workflow minh bạch, có trạng thái và không phụ thuộc giao tiếp không cấu trúc.

## 25. Xây dựng service profiles thay vì vô số tham số thấp tầng

Developer không nên phải chọn từng cờ cấu hình hạ tầng nếu nhu cầu chung đã được đóng gói. Có thể cung cấp các **profiles**:

| Profile | Mô tả | Defaults gợi ý |
|---|---|---|
| `development-small` | Thử nghiệm, tài nguyên hạn chế | Quota nhỏ, TTL preview, log retention ngắn |
| `standard-http` | API bình thường | Readiness, autoscaling, basic SLO, rollout mặc định |
| `critical-http` | Luồng nghiệp vụ trọng yếu | Redundancy, policy rollback chặt hơn, SLO/alerts nâng cao |
| `event-consumer` | Worker bất đồng bộ | Retry budget, idempotency, DLQ, queue lag SLI |
| `scheduled-job` | Batch/cron | Concurrency policy, retry, result retention, timeout |
| `sensitive-data` | Xử lý dữ liệu nhạy cảm | Region restrictions, encryption, strict access, audit |

Một profile cần giải thích **đổi lấy điều gì**: `critical-http` có thể tăng chi phí vì nhiều replicas/zones, nhưng cung cấp khả năng chịu lỗi và SLO phù hợp. Profile không phải giấy chứng nhận rằng ứng dụng có thể chịu mọi lỗi; code, dependency và data design vẫn quan trọng.

Đừng cho người dùng 80 cờ Kubernetes thô nhưng gọi đó là “self-service đơn giản”. Với use case nâng cao, nên có **escape hatch** chính thức có kiểm soát hơn là giấu mọi chi tiết.

## 26. Nền tảng và microservice boundaries

Platform có thể tạo common libraries/client SDK và service templates, nhưng không nên tạo ra một **distributed monolith** bằng cách bắt mọi microservice dùng chung một data model hoặc release schedule.

Nguyên tắc:

- Shared library nên tập trung cross-cutting concerns như tracing, auth client, config validation; không nhúng domain logic của nhiều nhóm.
- Libraries có semantic versioning và migration path; tránh thay đổi breaking bắt buộc mọi service deploy đồng loạt.
- Service catalog không biến thành cơ chế chia sẻ database trực tiếp.
- Templates hỗ trợ REST, gRPC hoặc messaging, nhưng consumer/provider contracts vẫn thuộc service owners.
- Shared gateway/mesh policy không thay thế application authorization.
- Tránh coupling về runtime theo một platform API nằm trên mọi request nếu không cần.
- Nền tảng cung cấp cách triển khai và vận hành, không sở hữu mọi business schema.

Mục tiêu của microservices là khả năng phát triển và phát hành có mức độc lập phù hợp. Nền tảng giúp chuẩn hóa **cách vận hành** trong khi tôn trọng **ranh giới nghiệp vụ**.

## 27. Quyết định build, buy hoặc tích hợp

Không phải tổ chức nào cũng nên tự xây portal, secret manager, CI system, service mesh và observability stack.

### Cân nhắc trước khi tự xây

1. Capability đó có tạo lợi thế khác biệt cho tổ chức không?
2. Các giải pháp hiện có có đáp ứng security/scale/compliance không?
3. Có thể dùng managed service với SLA và khả năng tích hợp không?
4. Chi phí bảo trì, nâng cấp, on-call, deprecation trong 3–5 năm là bao nhiêu?
5. Chức năng nào developer thực sự dùng, chức năng nào chỉ là mong muốn?
6. Có đủ năng lực product management và UX cho internal users không?
7. Dữ liệu/quyền nào sẽ đi qua nhà cung cấp mới?
8. Chiến lược rời nền tảng/vendor nếu yêu cầu thay đổi là gì?

**Tích hợp** thường là hướng đi thực dụng: dùng công cụ có sẵn để giải quyết infrastructure primitives rồi xây lớp workflow/contract và trải nghiệm nhất quán ở phần nội bộ. Dù dùng Backstage, một portal tự phát triển hay CLI, cần sở hữu product contract và lifecycle, không chỉ cấu hình một công cụ.

### Ví dụ hệ sinh thái

- Backstage hoặc service catalog tương đương cho discovery/scaffolding.
- Terraform/OpenTofu hoặc infrastructure provisioning API cho tài nguyên.
- Kubernetes cùng controller/GitOps cho runtime và desired state.
- CI system với reusable pipelines và artifact registry.
- Secret manager/workload identity cho credential.
- OpenTelemetry, metrics/logs/traces backend cho observability.
- OPA/Gatekeeper/Kyverno hoặc policy engine tương đương cho admission/policy.

Tên công cụ là ví dụ về loại năng lực, không có nghĩa phải cài tất cả. Sự phù hợp phụ thuộc stack, phiên bản, hệ thống đã có và nguồn lực vận hành.

## 28. Ví dụ: policy và provisioning cho một namespace

Một yêu cầu tạo namespace có thể gồm owner team, môi trường và quota profile. Platform có thể sinh manifest theo profile thay vì cho caller tùy ý khai báo.

Ví dụ ResourceQuota Kubernetes (tham số minh họa):

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-standard-quota
  namespace: team-fulfillment-dev
spec:
  hard:
    requests.cpu: "4"
    requests.memory: "8Gi"
    limits.memory: "16Gi"
    pods: "30"
    services: "10"
~~~

Ví dụ một ServiceAccount không cần gọi Kubernetes API:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: inventory-reservation
  namespace: team-fulfillment-dev
automountServiceAccountToken: false
~~~

Những manifest trên chỉ minh họa một phần; môi trường thực có thể cần LimitRange, Pod Security admission, NetworkPolicy, registry, storage và workload identity riêng. **Không cấp quyền `cluster-admin` mặc định chỉ vì developer tạo namespace thành công.** Quyền developer, deploy identity và runtime identity phải được tách.

Nếu workload cần cloud resource, platform workflow tạo IAM binding theo policy và trả reference, không xuất raw cloud credential trong ticket hoặc log.

## 29. Service catalog không phải nguồn sự thật duy nhất cho mọi thông tin

Một nền tảng có nhiều hệ thống giữ sự thật:

| Loại dữ liệu | Nguồn có thẩm quyền điển hình |
|---|---|
| Source code | Git repository |
| Artifact bytes/digest | Artifact registry |
| Desired deployment state | GitOps/config repository hoặc release controller |
| Runtime Pods/health | Kubernetes API/runtime |
| Service owner | Đăng ký ownership có xác minh |
| On-call schedule | Hệ thống on-call |
| Cloud IAM bindings | Cloud IAM/control plane |
| Secrets | Secret manager |
| API schema | API registry hoặc repository được version hóa |
| SLI/SLO measurements | Monitoring system |
| Cost data | Billing/cost platform |
| Catalog display | Tổng hợp references/metadata của các nguồn trên |

Portal có thể hiển thị “Service Healthy” nhưng nếu dữ liệu lấy từ cache cũ, trạng thái có thể sai. Cần hiển thị timestamp/freshness, link tới nguồn và phân biệt desired/actual. Không cho phép cập nhật thủ công một trường phản ánh runtime mà không reconcile từ nguồn tin cậy.

## 30. Quyền truy cập theo nhóm và vòng đời nhân sự

Developer self-service chỉ đúng nếu danh tính và ownership đáng tin. Quy trình IAM cần hỗ trợ:

- Người mới gia nhập team nhận đúng quyền theo vai trò.
- Người chuyển team không tiếp tục có quyền production cũ.
- Người nghỉ việc được thu hồi quyền và token.
- Tài khoản bot/service account không phụ thuộc email cá nhân.
- Temporary elevated access có approval, time-to-live và audit.
- Team owners được xác minh, không tự điền chuỗi để cấp quyền.
- Quyền đọc telemetry và production data tách khỏi quyền deploy khi cần.
- Namespace/region/tenant isolation được thực thi ở backend, không chỉ giao diện portal.

Một portal chỉ ẩn nút “Delete DB” không đủ làm authorization. Backend API và policy engine phải kiểm tra caller dù yêu cầu đến qua CLI hoặc API trực tiếp.

## 31. Quản trị ngoại lệ mà không phá đường tự phục vụ

Có những trường hợp team cần một loại database chưa hỗ trợ, network egress đặc biệt hoặc runtime mới. Nền tảng nên có **exception workflow**:

1. User giải thích nhu cầu và tại sao profile hiện tại không đủ.
2. Hệ thống xác định policy nào bị ảnh hưởng, resource scope và mức rủi ro.
3. Người có thẩm quyền đánh giá giải pháp thay thế và kiểm soát bổ sung.
4. Phê duyệt có thời hạn và version; không có “permanent bypass” vô danh.
5. Nền tảng cung cấp reference/permission cụ thể, không cấp role toàn cluster.
6. Ghi log quyết định và theo dõi expiry/review.
7. Nếu ngoại lệ phổ biến, đưa nó vào roadmap capability có hỗ trợ chính thức.
8. Nếu ngoại lệ không còn cần, thu hồi quyền/tài nguyên.

**Escape hatch** không có nghĩa cho người dùng tự inject shell command có quyền admin vào workflow. Nó là con đường được quản trị để xử lý những nhu cầu khác biệt có căn cứ.

## 32. Chi phí và capacity trong self-service

Nếu mỗi developer có thể bấm tạo DB không giới hạn, self-service có thể làm chi phí tăng nhanh và tài nguyên cạn. Cần cơ chế:

- Quotas theo team/environment.
- Tier và sizing profiles theo use case.
- Budget ownership/cost center tags.
- Preview environment TTL và idle cleanup.
- Notifications khi gần vượt quota.
- Rightsizing gợi ý theo metrics.
- Cơ chế request tăng quota có evidence.
- Phân biệt production reserved capacity với ephemeral capacity.
- Báo cáo chi phí theo service/team có tỷ lệ phân bổ đáng tin.

Không để cost guardrail tự động xóa tài nguyên production chưa được xác minh chỉ vì đo thiếu activity. Decommission phải hiểu data retention, ownership và recovery.

### 32.1. Ví dụ môi trường preview

Một preview environment có thể có:

~~~text
Request: PR #1842
Owner: fulfillment
TTL: 48 giờ sau hoạt động cuối theo policy
Resources: app container + fake/test database
Access: team only
Data: synthetic only
Network: không được kết nối production
Cleanup: event-driven + scheduled reconciliation
~~~

Quá trình cleanup phải có cảnh báo và policy ngoại lệ khi môi trường cần giữ cho kiểm thử, đồng thời xóa secrets/roles/network resources và dữ liệu test khi hết hạn.

## 33. Cải thiện developer experience theo hành trình

Hãy chọn một hành trình cụ thể thay vì đo “độ hài lòng chung” rồi đoán nguyên nhân.

Ví dụ hành trình tạo service:

~~~text
Developer starts
   |
   | Tìm docs/template
   v
Select a supported workload
   |
   | Có quyền? policy có rõ?
   v
Create repository & resources
   |
   | Workflow có thành công?
   v
Commit first change
   |
   | CI có chạy?
   v
Deploy to development
   |
   | Có endpoint?
   v
Find logs, metrics, traces
   |
   | Có tự debug được?
   v
First meaningful change delivered
~~~

Đo ở từng đoạn: thời gian chờ, số bước thủ công, tỷ lệ thất bại, số tickets, thời gian xử lý và mức độ developer tự giải quyết lỗi. Khi người dùng bị chặn, quan sát **nơi họ dừng**, thay vì thêm hướng dẫn chung ở trang chủ.

### Mục tiêu là flow, không chỉ automation

Tự động hóa một thao tác sai có thể làm việc sai xảy ra nhanh hơn. Một platform feature tốt nên làm rõ **quy trình đúng**, giảm số quyết định tùy ý và trả lỗi có thể hành động. Không tối ưu thời gian tạo namespace nếu thời gian tìm owner và sửa permission còn lâu hơn nhiều.

## 34. Chỉ số đo hiệu quả của platform team

Không nên đánh giá platform chỉ bằng số lượng API endpoints hoặc số dòng Terraform đã viết. Cần một tập chỉ số phản ánh người dùng, vận hành và chi phí:

| Nhóm | Chỉ số gợi ý | Cách diễn giải |
|---|---|---|
| **Adoption** | Tỷ lệ services/team dùng golden path | Cao chỉ tốt nếu workflow thật hữu ích, không bị ép dùng bất hợp lý |
| **Time-to-value** | Time to first successful deploy | Đo từ lúc bắt đầu workflow đến khi service hoạt động |
| **Self-service success** | Tỷ lệ provisioning không cần người can thiệp | Phân biệt lỗi caller và lỗi nền tảng |
| **Friction** | Số ticket / 100 provisioning operations | Theo dõi nhóm vấn đề thực, không đơn thuần giảm số ticket bằng cách ẩn support |
| **Delivery** | Lead time for changes, deployment frequency | Có thể tham khảo DORA; không dùng để ép team deploy vô nghĩa |
| **Reliability** | Change failure rate, recovery time, platform SLO | Xét cả service impact và maturity |
| **Security** | Compliance coverage, policy violations, secret exposure | Chú ý chất lượng kiểm soát, không chỉ số cảnh báo |
| **Cost** | Cost per workload/profile, idle resources | Cần quy ước phân bổ dùng chung |
| **Experience** | Developer satisfaction, perceived friction, docs usefulness | Kết hợp survey với hành vi thực |
| **Support** | First response/resolution time, recurring issues | Theo dõi root cause để giảm ticket lặp |

### 34.1. Đo có ngữ cảnh

Nếu deployment frequency tăng nhưng change failure rate tăng mạnh, nền tảng chưa chắc tốt hơn. Nếu số tickets giảm vì người dùng bỏ cuộc hoặc chuyển sang tự quản hạ tầng không được hỗ trợ, chỉ số cũng đánh lừa. Cần kết hợp số liệu và phỏng vấn.

Không dùng số lượng commits hoặc portal clicks làm thước đo năng suất cá nhân. Chỉ số platform nên phục vụ cải tiến hệ thống và developer workflows, tránh tạo incentive game metrics.

## 35. Ví dụ bảng mục tiêu quý đầu tiên

Một roadmap giả định sau discovery:

| Mục tiêu | Baseline giả định | Mục tiêu minh họa | Cách kiểm chứng |
|---|---:|---:|---|
| Tạo HTTP service và deploy dev | 2 ngày | Dưới 60 phút | E2E user journey test với developer mới |
| Thao tác cấp database cần ticket | 85% | Dưới 20% | Workflow telemetry + ticket taxonomy |
| Services có owner/on-call hợp lệ | 55% | Trên 90% | Catalog đối chiếu ownership system |
| Service mới có tracing và alert profile | 40% | Trên 90% | Runtime inventory + dashboard availability |
| Provisioning success rate | 82% | Trên 98% | Operation status, loại trừ yêu cầu không hợp lệ |
| Preview env tồn tại quá TTL | 30% | Dưới 5% | Resource inventory và cleanup evidence |

Tất cả con số trong bảng là **ví dụ để minh họa cách đặt mục tiêu**, không phải chuẩn chung hoặc kết quả thật. Trước khi áp dụng phải xác định baseline, time window, loại request hợp lệ và khả năng đo. Một nhóm nhỏ có thể ưu tiên một hành trình hơn là cố đạt mọi chỉ số.

## 36. Cách tổ chức platform backlog

Platform backlog không chỉ gồm “nâng Kubernetes” hoặc “chuyển sang tool X”. Nên phân loại theo outcomes:

- **Onboarding:** developer mới chưa tạo được service nhanh.
- **Delivery:** pipeline trùng lặp, khó rollback, deploy bị chặn không rõ lý do.
- **Provisioning:** quá nhiều ticket tạo database, topic, namespace.
- **Reliability:** runtime/CI/secrets integration thiếu SLO và runbook.
- **Security:** IAM cấp rộng, secret rotation thủ công, policy drift.
- **Discoverability:** không biết owner/dependency/API của services.
- **Cost:** preview environments không được cleanup, sizing sai.
- **Migration:** template/library cũ khó nâng, compliance controls không đồng đều.

Mỗi item nên có: người dùng, vấn đề, mức ảnh hưởng, evidence, phương án, chỉ số thành công, rủi ro và owner.

### Ưu tiên thế nào?

Một cách thực dụng:

1. Chọn những friction points xuất hiện ở nhiều nhóm.
2. Đánh giá cost của việc tiếp tục làm thủ công.
3. Ưu tiên security/reliability fixes có ảnh hưởng lớn.
4. Cân nhắc effort tích hợp và chi phí vận hành dài hạn.
5. Thử giải pháp nhỏ với nhóm pilot trước khi mở rộng.
6. Đo adoption, lỗi và thay đổi hành trình sau khi phát hành.

Không xây một tính năng chỉ vì nó có trong bản demo của sản phẩm IDP khác. Một workflow sửa lỗi deployment thường có giá trị cao hơn dashboard catalog phức tạp nếu người dùng hiện tại đang phải mất hàng giờ tìm nguyên nhân deploy fail.

## 37. Roadmap tăng trưởng theo giai đoạn

### Giai đoạn 1 — Tìm vấn đề và chọn pilot

Phỏng vấn các service teams, lấy mẫu onboarding, thống kê support tickets và deployment incidents. Chọn 1–2 journeys có tần suất cao như tạo Java HTTP service hoặc xin database staging. Xác định owner, phạm vi và chỉ số.

### Giai đoạn 2 — Chuẩn hóa primitives

Tạo reusable CI workflows, container base image, service identity, Kubernetes profiles, secrets integration và observability conventions. Ghi rõ contract, giới hạn và chính sách nâng cấp.

### Giai đoạn 3 — Đóng gói self-service

Cung cấp API/CLI/portal templates có orchestration, idempotency, permissions, status, retry, audit và documentation. Chạy pilot với một số nhóm thực tế.

### Giai đoạn 4 — Vận hành như sản phẩm

Thiết lập platform SLO, support, roadmap, feedback, versioned APIs, deprecation và quy trình giải quyết sự cố. Đo change failure và time-to-value, không chỉ số lượng resource tạo.

### Giai đoạn 5 — Mở rộng an toàn

Thêm workload types, day-2 workflows, production profiles, policy-as-code, costs và cross-service discoverability. Mở rộng theo evidence về nhu cầu và adoption.

### Giai đoạn 6 — Giảm legacy và drift

Gắn version cho templates, inventory các service cũ, cung cấp migration path, policy enforcement và cleanup tài nguyên/credential không còn dùng. Không bắt mọi team chuyển trong một ngày nếu migration có rủi ro downtime/data incompatibility.

## 38. Migration từ mô hình ticket thủ công

Một tổ chức thường có các yêu cầu như:

~~~text
Ticket: "Create namespace"
Ticket: "Create staging database"
Ticket: "Add role for service"
Ticket: "Deploy to dev"
Ticket: "Configure dashboard"
Ticket: "Rotate API key"
~~~

Chuyển đổi nên tiến hành có kiểm soát:

1. Phân tích ticket volume, loại thao tác và nguyên nhân phát sinh.
2. Định nghĩa các workflows chuẩn hóa có yêu cầu ổn định.
3. Chuyển cách cấp tài nguyên sang declarative/reconciled state khi phù hợp.
4. Đảm bảo inventory và ownership của những tài nguyên đã có.
5. Tự động hóa quyền cho các request được phép; các ngoại lệ đi qua approval.
6. Chạy song song có giới hạn và theo dõi sai lệch giữa đường mới/cũ.
7. Cung cấp hỗ trợ di chuyển cho teams có cấu hình đặc thù.
8. Chỉ deprecate quy trình thủ công khi đường mới đủ tin cậy và có recovery.
9. Sau deprecation, chặn các bypass không được hỗ trợ bằng policy/audit.
10. Xem lại tickets còn lại để bổ sung capability, thay vì duy trì helpdesk vĩnh viễn.

Không di chuyển nhầm production resource hoặc thay identity hiện tại khi chưa hiểu tác động đến runtime. Những việc liên quan schema/data/secret cần đường chuyển tiếp và rollback/roll-forward riêng.

## 39. Self-service và dữ liệu/stateful resources

Tạo một stateless HTTP service thường dễ hơn quản lý database, broker hoặc storage. Với stateful capability, self-service cần nhiều thông tin hơn:

- Data classification, retention và residency.
- Availability/replication tier.
- Backup, restore và recovery objectives.
- Database schema ownership, migration rules.
- Encryption và key management.
- Access control theo workload identity, không shared admin credentials.
- Network scope và audit.
- Sizing, quota và cost.
- Deletion grace period và khôi phục trước khi xóa.
- Trạng thái resource khi provisioning, failover hoặc backup lỗi.

Một nút “Create database” không nên trả mật khẩu root vào trình duyệt rồi coi như hoàn thành. Tốt hơn là tạo resource với policy, cấp identity/credential qua secret manager và trả connection reference; service owner quản lý schema và truy cập theo phạm vi được cấp.

### 39.1. Quy trình xóa stateful resource

~~~text
Request delete
   |
   v
Verify owner + scope + approval
   |
   v
Check consumers and active workloads
   |
   v
Validate retention / backup / legal hold
   |
   v
Quiesce traffic and disable new writes
   |
   v
Create/verify final snapshot if required
   |
   v
Deprovision with audit
   |
   v
Revoke credentials, DNS, policies
   |
   v
Verify cleanup and record outcome
~~~

Sự tồn tại của một resource có thể kéo theo trách nhiệm dữ liệu lâu hơn vòng đời application. Không tự xóa production DB chỉ vì service catalog bị xóa.

## 40. Platform và reliability: hoạt động trong ngày sự cố

Khi một incident xảy ra, vai trò thường được tách:

~~~text
Service team on-call:
  Detect service SLO regression
  Diagnose business/app dependency
  Mitigate feature, retries, traffic

Platform on-call:
  Diagnose shared runtime/control plane
  Restore cluster/network/registry/secrets
  Support deploy/rollback tooling

Incident commander:
  Coordinate severity, ownership, communication
  Decide cross-team mitigation
~~~

Nếu cluster DNS lỗi, platform team có thể dẫn xử lý. Nếu Order Service phát event trùng do business code, service team dẫn xử lý, platform hỗ trợ broker observability. Nếu shared CI/CD không thể deploy hotfix, platform trở thành critical dependency của incident recovery.

Cần có:

- Platform status page và incident severity.
- Runbooks cho lỗi cluster, registry, GitOps, IAM, secret manager, portal.
- Đường rollback thủ công/break-glass có audit khi control plane lỗi.
- Capacity và failure-domain isolation.
- DR exercise và backup restore cho metadata/catalog/workflow state.
- Escalation rõ giữa service owner và platform.
- Mốc SLO/error budget cho từng capability.

**Không làm platform thành single point of failure trong data plane** chỉ để đạt sự đồng nhất của portal.

## 41. Kiểm thử platform workflow

Một tính năng nền tảng mới cần kiểm thử từ API tới resource thật, không chỉ test UI.

### 41.1. Happy path

- Developer đúng team tạo service từ template.
- Repository và pipeline hợp lệ, build pass.
- Workload deploy vào môi trường được phép.
- Secret/identity được cấp đúng.
- Service có catalog owner và documentation.
- Endpoint readiness và dashboard hoạt động.
- Operation status chuyển READY khi hậu điều kiện thực sự được xác minh.

### 41.2. Failure paths

- Tên service trùng, request bị từ chối có mã lỗi rõ.
- Quota vượt, không tạo tài nguyên dở dang.
- Caller thuộc team A không thể tạo resource cho team B.
- Caller development không thể tự tạo production resource quyền cao.
- Provisioner timeout sau khi đã tạo DB: retry không tạo DB thứ hai.
- Policy engine unavailable: hành động nhạy cảm không được bypass.
- Secret manager lỗi: workflow phản hồi đúng và không log giá trị.
- GitOps apply thành công nhưng Pods không Ready: không báo READY.
- User đóng tab giữa workflow: operation tiếp tục hoặc được cleanup theo policy.
- Parallel requests cùng tên: một kết quả chuẩn, không race tạo hai resources.
- Template mới không còn tương thích pipeline cũ: versioning/migration policy hoạt động.

### 41.3. Day-2 tests

- Nâng config revision có rollout/validation.
- Rotation secret không làm mọi Pod mất kết nối.
- Rollback trả service về trạng thái chấp nhận.
- Xóa preview environment thu hồi tài nguyên/roles đúng.
- Restore database test từ backup có thể đọc dữ liệu.
- Policy upgrade chặn manifest không hợp lệ nhưng không phá các workload còn hợp lệ.
- Catalog owner thay đổi có audit và propagation đến on-call/permissions.

## 42. Kiểm thử security của self-service API

Nền tảng thường có quyền tạo/sửa rất nhiều tài nguyên, nên API là bề mặt nhạy cảm.

Kiểm tra:

- Caller authentication và authorization ở **backend** cho mọi endpoint.
- Tenant/team/environment scope không chỉ dựa vào giá trị client gửi.
- Input schema và naming validation để ngăn path/command/template injection.
- Không cho user cung cấp raw shell script có quyền platform-admin nếu không có sandbox/policy.
- Không hiển thị raw secret/token trong response, errors, logs hoặc traces.
- Workflow không dùng một token admin dài hạn chia sẻ cho tất cả tasks khi có thể dùng scoped identities.
- Resource labels/tags và ownership không bị caller sửa để chiếm resource khác.
- Rate limits, quotas và concurrency limits giảm abuse.
- Sensitive actions có approval, expiring privilege và audit.
- Supply-chain controls cho templates, plugins và third-party actions.
- Logs/audit có eventId, actor, target, policy version nhưng không lộ PII không cần thiết.
- Điều kiện race giữa policy evaluation và provisioning được xử lý bằng reconciliation hoặc kiểm tra lại khi thích hợp.

Cần có threat model cho khả năng control plane bị xâm nhập: ảnh hưởng có thể lan toàn cluster/cloud. Platform tự phục vụ phải giảm blast radius bằng phân tách quyền và môi trường.

## 43. Các tình huống vận hành thường gặp

### 43.1. Developer tạo service nhưng không deploy được

Triệu chứng: portal báo SUCCESS, CI xanh nhưng Pod `ImagePullBackOff`.

Phân tích: workflow phải phân biệt **repository created**, **artifact built**, **deployment applied** và **runtime ready**. Kiểm tra registry permissions/image digest, imagePullSecret hoặc registry identity. Không báo service đã hoạt động khi runtime chưa Ready.

Cải tiến: operation state có bước deploy verification, link tới diagnostics và remediation rõ.

### 43.2. Lệnh tạo database bị timeout

Triệu chứng: request mất kết nối; user bấm lại tạo ra hai database.

Phân tích: provisioning thiếu idempotency và operation ID. Backend phải lưu request với resource key duy nhất, trả trạng thái hiện có khi retry và cleanup khi partial failure.

Cải tiến: idempotency key, durable workflow state, unique constraints và reconciler.

### 43.3. Self-service IAM cấp quyền quá rộng

Triệu chứng: một runtime service đọc được secrets của team khác.

Phân tích: quyền được cấp theo wildcard, thiếu tenant isolation hoặc caller có thể chọn ServiceAccount quyền cao. Không giải quyết chỉ bằng ẩn nút portal.

Cải tiến: scoped IAM/RBAC, backend policy, admission và kiểm thử truy cập bị từ chối.

### 43.4. Template phiên bản mới phá service cũ

Triệu chứng: upgrade shared library hoặc pipeline khiến nhiều nhóm không build được.

Phân tích: template và reusable workflows là sản phẩm có versioning. Một breaking change cần compatibility window, migration guide và pilot.

Cải tiến: semantic/versioned contract, compatibility tests, deprecation notice và bản vá theo mức ưu tiên.

### 43.5. Catalog cho biết sai team owner

Triệu chứng: incident tới sai on-call, không ai nhận trách nhiệm.

Phân tích: metadata được điền thủ công lâu ngày không cập nhật. Catalog cần policy owner hợp lệ và đồng bộ với hệ thống nhận diện/on-call.

Cải tiến: drift detection, owner verification và quy trình bàn giao service.

### 43.6. Portal outage chặn rollback

Triệu chứng: service production gặp lỗi, nhưng portal điều khiển rollout unavailable.

Phân tích: quá phụ thuộc một control plane. Cần đường break-glass được bảo vệ, có runbook và source of truth không lệ thuộc chỉ vào UI.

Cải tiến: độc lập điều khiển traffic/rollout ở tầng runtime hoặc CLI/API dự phòng, diễn tập và audit.

## 44. Những sai lầm phổ biến

1. **Xây portal trước khi hiểu nhu cầu:** có nhiều trang nhưng developer vẫn gửi ticket cho thao tác quan trọng.
2. **Tự phục vụ thực chất là ticket form:** thiếu orchestration, status, retry và cleanup.
3. **Gộp platform và service ownership:** khi sự cố không biết ai chịu trách nhiệm code/data.
4. **Bắt mọi service cùng một stack:** cản use case khác biệt và tạo escape hatch không được quản trị.
5. **Dùng template rồi không bảo trì:** drift và security fixes không tới services cũ.
6. **Không version API/workflows:** thay platform phá integrations.
7. **Quyền admin dùng chung:** một lỗ hổng có thể tạo blast radius toàn tổ chức.
8. **Dựa vào giao diện để kiểm soát quyền:** API/CLI bypass được hidden buttons.
9. **Không kiểm tra trạng thái runtime:** báo resource READY quá sớm.
10. **Không có idempotency:** retry tạo resources trùng.
11. **Không có cleanup:** preview DB/namespace/quyền tồn tại mãi.
12. **Cho mọi user tạo resource không quota:** chi phí và cluster saturation tăng.
13. **Chỉ đo số lượt click:** không biết developer có ship được service hay không.
14. **Đẩy vận hành cho developer mà không cung cấp công cụ:** tăng cognitive load thay vì giảm.
15. **Đưa mọi yêu cầu qua approval thủ công:** platform trở thành điểm nghẽn.
16. **Không có cơ chế ngoại lệ hợp lệ:** teams tự xây shadow infrastructure.
17. **Không có docs/supported versions:** support tickets lặp đi lặp lại.
18. **Catalog không có owner đáng tin:** incident escalation thất bại.
19. **Platform nằm trong critical request path vô cớ:** portal downtime kéo theo service outage.
20. **Không có đường phục hồi khi nền tảng lỗi:** incident không thể triển khai hotfix.
21. **Cấp secret trực tiếp trong portal response:** tạo điểm rò rỉ dữ liệu nhạy cảm.
22. **Không tính cost vận hành nền tảng:** xây nhiều controllers không có on-call và lifecycle.
23. **Giả định compliance tự động đúng vì manifest pass:** cần kiểm tra runtime và audit evidence.
24. **Đồng nhất DevOps với một team chuyên nhận tickets:** mất mục tiêu tự chủ và chia sẻ trách nhiệm.

## 45. Checklist xây capability tự phục vụ

- [ ] Có người dùng mục tiêu và user journey rõ.
- [ ] Vấn đề được xác minh bằng evidence, không chỉ giả định.
- [ ] Input/output schema và error codes được version hóa.
- [ ] Workflow end-to-end, có operation ID và status thật.
- [ ] Caller được xác thực và backend áp quyền theo team/environment.
- [ ] Policy/quota/approval được thực thi như guardrails.
- [ ] Secrets và identities được cấp theo phạm vi tối thiểu.
- [ ] Retry an toàn, idempotency và partial-failure cleanup.
- [ ] Resource có owner, catalog entry và lifecycle metadata.
- [ ] CI/CD, deployment, health và observability được cấu hình.
- [ ] Có dashboard, documentation, runbook và support path.
- [ ] Có SLO cho capability/platform API.
- [ ] Có test happy path, failure path và security denied cases.
- [ ] Có audit cho hành động nhạy cảm và resource changes.
- [ ] Có retention, backup, restore/decommission khi liên quan stateful resource.
- [ ] Có kế hoạch nâng version/migration/deprecation.
- [ ] Đo adoption, lead time, friction, cost, reliability và experience.
- [ ] Có pilot, feedback loop và đường ngoại lệ chính thức.

## 46. Bài tập tình huống: nền tảng cho 30 nhóm microservices

Một tổ chức có:

~~~text
30 development teams
200 microservices
3 Kubernetes clusters (dev/staging/prod)
Multiple PostgreSQL databases
Managed message broker
Cloud secret manager
CI pipelines viết riêng từng repository
Trung bình 120 tickets hạ tầng mỗi tháng
~~~

Các vấn đề:

- Tạo service mới mất 3 ngày.
- Mọi nhóm có Dockerfile, tracing và health probes khác nhau.
- Tạo database staging phải chờ admin.
- Team on-call khó tìm owner của 40 service cũ.
- Nhiều preview environments còn chạy sau khi PR đã đóng.
- Một số service dùng cloud access key dài hạn trong biến môi trường.
- Security muốn kiểm soát thay đổi production mà không duyệt tay mọi deployment.

### Câu hỏi

1. Chọn hai user journeys nào để tạo MVP nền tảng? Vì sao?
2. Phân tách trách nhiệm giữa platform team, service team, SRE và security ra sao?
3. Một golden path Java HTTP Service phải sinh ra những artifact/metadata nào?
4. Thiết kế workflow tạo database staging với input, policies, output và retry semantics.
5. Làm thế nào gắn owner/on-call chính xác cho catalog mà không phụ thuộc nhập tay mãi?
6. Làm cách nào thay cloud key dài hạn bằng danh tính workload có kiểm soát?
7. Trình bày policy để triển khai production an toàn nhưng không bắt tất cả thay đổi qua approval.
8. Nên theo dõi những chỉ số nào trong quý đầu để biết nền tảng thực sự giúp developer?
9. Khi portal down nhưng Order Service đang cần rollback, đường xử lý nào nên tồn tại?
10. Làm thế nào migration các services cũ mà không gây mass breaking change?

### Gợi ý triển khai

**MVP:** chọn golden path tạo service mới và tự cấp PostgreSQL staging, vì cả hai có tần suất cao và giảm tickets trực tiếp. Có thể đưa owner/catalog/tracing/CI vào golden path ngay từ đầu, nhưng không cần xây mọi khả năng day-2 cùng lúc.

**RACI thực dụng:** platform sở hữu provisioning workflows, CI primitives, runtime profiles và policy implementation; service teams sở hữu domain code, service SLO, data schemas và business correctness; SRE đồng thiết kế reliability; Security định nghĩa trust/policy và kiểm tra quyền.

**Golden path:** repository, code skeleton, tests, container build, CI, deployment manifests, ServiceAccount, minimal RBAC, config schema, dashboard, tracing, runbook và catalog metadata.

**Database workflow:** owner/environment/tier/data class → validate scope/quota → create desired state → provision → verify network/identity/backup → return reference/status. Retry bằng idempotency key, không gửi password thô.

**Ownership:** liên kết catalog với team directory và on-call, kiểm tra không có owner rỗng hoặc không tồn tại, tạo chuyển giao có audit.

**Cloud identities:** dùng cơ chế federation/workload identity và policy chỉ đọc resource cần, thay key theo lộ trình có kiểm chứng; không thay credentials production đột ngột.

**Production delivery:** build artifact bất biến, CI checks, canary/feature flag, SLO gates, rollback và approvals theo mức rủi ro.

**Chỉ số:** time to first deploy, self-service completion, số tickets cần người can thiệp, template adoption, SLO của provisioning, change failure, satisfaction và cost.

**Portal outage:** có controller và runbook thao tác kiểm soát traffic/rollback tách khỏi UI, quyền break-glass có audit.

**Migration:** theo profile/version, pilot, generated PR/codemod, backward-compatible defaults, deprecation schedule và kiểm chứng mỗi nhóm.

## 47. Bài tập thực hành: thiết kế workflow tạo môi trường preview

Yêu cầu: Developer mở PR cho Order Service và muốn một preview environment chạy code mới mà không ảnh hưởng production.

Hãy thiết kế một request:

~~~yaml
request:
  kind: PreviewEnvironment
  team: commerce-orders
  repositoryRef: order-api
  pullRequest: 1842
  environment: preview
  profile: small
  dataSource: synthetic
  lifetimeHours: 48
  exposure: team-only
~~~

Đầu ra mong đợi:

- Image build từ commit PR có digest cụ thể.
- Namespace/identifier chứa PR và team đã xác minh.
- ResourceQuota và giới hạn CPU/memory.
- ServiceAccount riêng, quyền tối thiểu.
- Config không trỏ production DB.
- Test database và message topics nếu cần.
- URL preview chỉ nhóm được phép truy cập.
- Logs/traces/dashboard có labels theo preview operation, không chứa secrets.
- Cleanup tự động khi PR đóng hoặc TTL hết, có audit.
- Retry không tạo hai environment trùng.
- Nếu provision fail giữa chừng, cleanup hoặc reconciler xử lý.

Câu hỏi mở rộng: Nếu developer PR tới từ fork không tin cậy, có nên cho workflow nhận production secrets hoặc cloud IAM role quyền rộng không? Cần tách trust level, hạn chế secrets, sandbox runtime và kiểm soát egress. PR không đáng tin không tự có quyền tương đương code đã được review.

## 48. Ghi nhớ

Một nhóm nền tảng thành công không được đo bằng số lượng công cụ đã cài hoặc số thao tác họ có thể làm thay developer. Thành công thể hiện ở việc **nhóm phát triển có thể tự làm những công việc phổ biến nhanh và an toàn, hiểu rõ trách nhiệm, tìm được trợ giúp và vận hành service theo chuẩn đáng tin**.

Hãy coi nền tảng là **sản phẩm nội bộ** với khách hàng, APIs, SLO, roadmap, documentation, support và lifecycle. Bắt đầu bằng vài golden paths phổ biến; triển khai self-service từ đầu tới cuối với identity, policy, idempotency, observability và audit; mở rộng sang day-2 operations khi có evidence. Platform tạo đường đi thuận tiện và guardrails, còn service team giữ quyền chủ động và trách nhiệm với hệ thống nghiệp vụ.

Mục tiêu cuối cùng là **giảm cognitive load, tăng khả năng tự chủ trong phạm vi được quản trị và cải thiện tốc độ thay đổi mà không đánh đổi reliability, security hoặc cost**.

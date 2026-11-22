# Quyền sở hữu khi một nhóm quản lý nhiều dịch vụ

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Tổ chức nhóm. README này trình bày cách thiết kế và vận hành **quyền sở hữu dịch vụ (service ownership)** khi **một nhóm kỹ thuật chịu trách nhiệm cho nhiều microservice**. Nội dung đi từ mô hình tổ chức, trách nhiệm kỹ thuật và nghiệp vụ, quyền quyết định, phân chia công việc, on-call, SLO, service catalog, dữ liệu, security, chi phí, vòng đời dịch vụ tới phương pháp giảm cognitive load và chuyển giao ownership an toàn.

## 1. Bài toán: nhiều dịch vụ nhưng chỉ một nhóm chịu trách nhiệm

Microservices được chia theo năng lực nghiệp vụ và ranh giới triển khai, nhưng cấu trúc đội ngũ không nhất thiết có quan hệ một-một với số lượng service. Ví dụ một nhóm Checkout gồm sáu kỹ sư có thể quản lý:

- `cart-service`: quản lý giỏ hàng.
- `order-service`: tạo và theo dõi đơn.
- `pricing-service`: tính giá và khuyến mại.
- `checkout-orchestrator`: phối hợp luồng checkout.
- `order-events-worker`: phát, tiêu thụ và đối soát event.
- `checkout-admin-api`: công cụ vận hành và xử lý ngoại lệ.

Trong khi đó, nhóm khác sở hữu Inventory Service, Payment Service, Gateway, Kafka platform và cơ sở hạ tầng Kubernetes dùng chung. Nhóm Checkout vẫn cần hiểu dependency và hành trình người dùng dù không sở hữu tất cả service trong chuỗi.

Nếu không có mô hình ownership rõ, các vấn đề thường xuất hiện:

1. Service có code nhưng không có người nhận page khi production lỗi.
2. Mỗi service có một tech lead danh nghĩa nhưng không ai chịu trách nhiệm **toàn bộ kết quả**.
3. Một người trở thành “chủ sở hữu vĩnh viễn” của service do họ tạo, dù đã đổi nhóm hoặc nghỉ việc.
4. Nhóm ưu tiên feature mới, còn dependency updates, test, alert và backup của các service cũ bị bỏ quên.
5. Nhiều service nhỏ làm số pipeline, dashboard, secrets, database và lịch trực tăng hơn khả năng vận hành của nhóm.
6. Code ownership, runtime ownership và data ownership không khớp nhau.
7. Khi checkout lỗi xuyên service, các nhóm tranh luận lỗi thuộc về ai thay vì phối hợp giảm tác động người dùng.
8. Thay đổi schema/API/event không có nhóm chịu trách nhiệm tương thích với consumer đang hoạt động.
9. Hạ tầng hoặc thư viện dùng chung được coi là “của platform” nên product team bỏ qua phần ứng dụng phải xử lý.
10. Khi tách/nhập nhóm, việc chuyển repository không đi kèm runbook, on-call, credential và SLO.

**Mục tiêu:** mỗi service phải có một **nhóm chịu trách nhiệm cuối cùng được xác định**, trong khi nhóm đó có mô hình làm việc đủ bền vững để sở hữu nhiều service mà không tăng sự phụ thuộc vào một cá nhân.

## 2. “Ownership” không chỉ là người được phép sửa code

Trong một hệ thống microservices, quyền sở hữu là tổ hợp **trách nhiệm, quyền quyết định và năng lực thực thi**.

| Thành phần ownership | Nội dung | Ví dụ |
| --- | --- | --- |
| Product/business ownership | Dịch vụ hỗ trợ năng lực nghiệp vụ nào, giá trị và ưu tiên ra sao | Checkout Product Owner ưu tiên việc xác nhận đơn |
| Technical ownership | Thiết kế API, code, test, dependency, deployment | Checkout Team sở hữu Order Service |
| Runtime/operational ownership | SLO, monitoring, alerts, on-call, sự cố, rollback | Checkout on-call được page khi Order 5xx |
| Data stewardship | Schema, retention, quality, migration, quyền dữ liệu | Order Team chịu trách nhiệm Order DB và dữ liệu đơn |
| Security responsibility | Authentication/authorization, secrets, threat model, patching | Checkout Team triển khai auth đúng; Security đặt policy |
| Cost/capacity responsibility | Quota, cloud spend, traffic growth, hiệu quả tài nguyên | Checkout Team phân tích cost của DB và replicas |
| Dependency contract ownership | API/event version, compatibility, consumer communication | Order Team công bố `OrderCreated` contract |
| Lifecycle responsibility | Tạo, thay đổi, nâng cấp, ngừng dịch vụ | Checkout Team xóa service cũ an toàn |
| Incident/journey accountability | Ai phối hợp khi người dùng không hoàn thành tác vụ | Checkout journey owner điều phối, Payment owner xử lý payment |

**Ownership không có nghĩa một nhóm làm mọi việc một mình.** Platform Team có thể vận hành cluster, DB platform và messaging infrastructure. Security Team có thể quy định IAM. Tuy nhiên Checkout Team phải bảo đảm ứng dụng dùng đúng những nền tảng này, kiểm soát tác động tới người dùng và phối hợp khi dependency lỗi.

Một định nghĩa ngắn gọn: **nhóm sở hữu dịch vụ có quyền và nghĩa vụ đưa dịch vụ từ ý tưởng đến production, duy trì mức chất lượng đã cam kết và chuyển giao hoặc ngừng nó một cách an toàn.**

## 3. Nguyên tắc: một primary accountable owner cho mỗi dịch vụ

Một service có thể có nhiều nhóm đóng góp, nhưng cần có **một nhóm đầu mối chịu trách nhiệm chính**.

~~~text
Service: order-service
  Primary accountable team: Checkout Team
  Secondary support: Platform, Database, Security
  Product capability owner: Checkout Product
  On-call: checkout-primary -> checkout-secondary
  Lifecycle: production
~~~

Điều này không cấm hai nhóm cùng code review hoặc deploy; nó ngăn tình huống “hai nhóm cùng chịu trách nhiệm” nhưng không có nhóm nào thực sự phản hồi page.

**Quy ước phân quyền:**

- Primary owner được quyền ưu tiên backlog, đưa thay đổi vào roadmap kỹ thuật, điều phối production incident và nhận chất lượng dịch vụ.
- Những thay đổi thuộc hạ tầng dùng chung vẫn cần tuân theo policy của platform/security.
- Người đóng góp từ nhóm khác được tham gia theo interface và code review, nhưng không tự động sở hữu SLO.
- Nếu ownership phải thực sự chia đôi vì lý do pháp lý hoặc domain, hãy chia service/data boundaries hoặc lập cơ chế decision authority rõ; đừng để “shared ownership” là một nhãn mơ hồ.

**Không đồng nhất cá nhân và nhóm.** Có thể chỉ định một **service steward/DRI cá nhân** phụ trách theo dõi tình trạng trong một khoảng thời gian, nhưng nhóm vẫn là owner liên tục. Khi steward nghỉ phép hoặc đổi công việc, trách nhiệm không biến mất.

## 4. Một nhóm quản lý nhiều service khi nào hợp lý?

Mô hình một nhóm–nhiều service phù hợp khi:

- Các service thuộc **một bounded context** hoặc năng lực nghiệp vụ liên quan, ví dụ cart, order và checkout orchestration.
- Nhóm đủ năng lực hiểu, triển khai, giám sát và xử lý sự cố của các service.
- Tổng tải vận hành, số dependency và mức thay đổi nằm trong khả năng đáp ứng của nhóm.
- Có thể tổ chức on-call và backup không phụ thuộc một người biết một service.
- Đường đi triển khai và test đủ tự động; không cần thao tác thủ công cho mỗi release.
- Các service có roadmap và ưu tiên có thể phối hợp mà không tạo xung đột liên tục.
- Quyền dữ liệu và security đủ nhất quán để nhóm vận hành một cách an toàn.
- Việc có nhiều deployable mang lại lợi ích thực sự: scale khác nhau, isolation, release cadence hoặc công nghệ/tính chất runtime khác nhau.

Mô hình bắt đầu nguy hiểm khi một nhóm có quá nhiều service không liên quan: ví dụ cùng quản lý Checkout, Search, Internal Billing, Fraud, Notifications và Data Ingestion chỉ vì nhóm từng xây dựng chúng. Khi đó cognitive load tăng nhưng không có lợi thế domain rõ ràng.

**Không có tỷ lệ chuẩn cố định như “một nhóm được sở hữu tối đa năm microservice”.** Một service có nhiều payment providers và yêu cầu pháp lý cao có thể khó vận hành hơn mười worker nhỏ. Cần đo độ phức tạp và tải thực tế.

## 5. Tách ba câu hỏi: ai sở hữu service, ai sở hữu platform, ai sở hữu journey?

~~~text
Customer Checkout Journey
       |
       +-- API Gateway ------------- Platform Team
       |
       +-- Cart Service ------------ Checkout Team
       +-- Order Service ----------- Checkout Team
       +-- Checkout Orchestrator --- Checkout Team
       |
       +-- Inventory Service ------- Inventory Team
       +-- Payment Service --------- Payment Team
       |
       +-- Kafka Cluster ----------- Platform/Messaging Team
       +-- Order DB Infrastructure - Data Platform
       +-- Order Data Schema ------- Checkout Team
~~~

Ba khái niệm cần phân biệt:

1. **Service ownership:** nhóm chịu trách nhiệm code, API, triển khai, vận hành và dữ liệu dịch vụ.
2. **Platform ownership:** nhóm xây dựng và vận hành năng lực dùng chung như cluster, ingress, broker service, database platform và observability.
3. **User journey ownership:** nhóm hoặc vai trò theo dõi thành công cuối cùng của một hành trình, điều phối khi nhiều service cùng tham gia.

Khi Payment API lỗi, Payment Team vẫn là owner xử lý Payment Service. Nhưng Checkout journey owner phải nắm được ảnh hưởng checkout, giao tiếp với sản phẩm, lựa chọn degraded behavior và theo dõi SLO hành trình. Không được đẩy mọi vấn đề user journey sang nhóm sở hữu dependency rồi ngừng theo dõi.

## 6. Bounded context và ranh giới nghiệp vụ quan trọng hơn repository

Một nhóm quản lý nhiều service nên có **cohesion nghiệp vụ**. Dựa vào Domain-Driven Design:

- **Bounded context:** nơi các thuật ngữ và quy tắc nghiệp vụ có ý nghĩa nhất quán.
- **Aggregate:** ranh giới nhất quán giao dịch và bất biến.
- **Service boundary:** nơi triển khai, scaling, release và fault isolation có thể khác nhau.
- **Team boundary:** nhóm có thể đưa ra thay đổi trong một vùng trách nhiệm mà không phải xin nhiều team khác.

Không phải mọi aggregate cần thành microservice. Một bounded context có thể được triển khai bằng **modular monolith** hoặc nhiều service, tùy trade-off. Nếu một nhóm buộc phải release ba service cùng lúc cho mọi thay đổi và luôn chỉnh sửa cả ba schema, có thể ranh giới service đang bị phân tách quá mức.

Các dấu hiệu boundary phù hợp:

| Tín hiệu | Diễn giải |
| --- | --- |
| Mỗi service có contract và dữ liệu sở hữu rõ | Tốt cho autonomy |
| Các thay đổi nghiệp vụ hầu hết nằm trong một nhóm | Tốt cho phối hợp |
| Các service có deployment cadence khác nhau có lý do | Có lợi ích tách deploy |
| Phải sửa năm service khi thay một field nhỏ | Có thể chia quá nhỏ hoặc contract sai |
| Team khác phải biết bảng DB nội bộ của service | Ranh giới dữ liệu bị phá |
| Mỗi incident phải mời nhiều team chỉ để tìm hiểu call graph | Dependency/ownership chưa rõ |
| Một service chỉ proxy 1:1 và không có rule riêng | Xem xét giá trị thật của service |

**Thiết kế service và tổ chức nhóm ảnh hưởng lẫn nhau.** Nếu cấu trúc team thay đổi, nên xem lại interface và ranh giới triển khai; nhưng không tự ý tách dữ liệu/service chỉ để sơ đồ tổ chức trông cân xứng.

## 7. Mối quan hệ với Team Topologies và tải nhận thức

Một nhóm sản phẩm có thể vận hành theo kiểu **stream-aligned team**: tập trung vào dòng giá trị checkout, sở hữu các service cần thiết để tạo thay đổi. **Platform team** cung cấp năng lực self-service, **enabling team** hỗ trợ nâng kỹ năng tạm thời và **complicated-subsystem team** có thể sở hữu phần chuyên môn đòi hỏi cao.

Điểm quan trọng không phải gán tên mô hình, mà là giảm **cognitive load**:

- Người trực có thể hiểu các đường đi chính và những gì xảy ra khi dependency lỗi không?
- Người mới mất bao lâu để deploy an toàn một service?
- Có bao nhiêu công nghệ runtime, database, broker, framework khác nhau?
- Có bao nhiêu alert với cách khắc phục riêng?
- Mỗi thay đổi cần phối hợp bao nhiêu owner?
- Service nào chỉ một cá nhân biết rõ?
- Nhóm có đủ thời gian bảo trì, bảo mật và reliability hay bị feature work chiếm hết?
- Có bao nhiêu tình huống phải quay sang ticket platform thay vì dùng self-service?

Nếu một nhóm quản lý 12 service nhưng tất cả cùng runtime, bộ mẫu deploy, logging và contract conventions, tải có thể thấp hơn nhóm quản lý ba service nhưng ba hệ sinh thái độc lập phức tạp. Đo bằng **khả năng thay đổi và phục hồi**, không chỉ số tên service.

## 8. Ownership gắn với toàn bộ vòng đời dịch vụ

| Pha | Trách nhiệm nhóm sở hữu | Bằng chứng cần có |
| --- | --- | --- |
| Đề xuất | Xác định nhu cầu tách service, domain, SLO, chi phí | ADR và service charter |
| Thiết kế | API/event contracts, data boundary, failure modes | Design review, threat model |
| Phát triển | Code, tests, migrations, CI, compatibility | Test report, contract verification |
| Ra mắt | Deploy, dashboard, runbook, on-call, rollbacks | Production readiness review |
| Vận hành | SLO, alert, incident, capacity, cost, patching | Dashboards, incident log |
| Tiến hóa | Deprecation, API version, DB schema migration | Migration/compatibility plan |
| Chuyển giao | Bàn giao code, data, credentials, knowledge | Ownership transfer checklist |
| Ngừng dùng | Tắt traffic, xử lý lưu trữ dữ liệu, xóa resources | Decommission record |

**Không cho service lên production mà không có owner, on-call, SLO tối thiểu và rollback/runbook phù hợp.** “Sau này sẽ bổ sung” rất dễ trở thành nợ vận hành kéo dài.

Service prototype chưa nhận production traffic có thể có tiêu chuẩn khác; phải ghi rõ lifecycle để không page một thử nghiệm như dịch vụ khách hàng quan trọng.

## 9. Service catalog là nguồn sự thật của ownership

Dùng service catalog (ví dụ một kho metadata có kiểm soát) để tìm được owner trong vài giây, không phải hỏi trong chat “service này của ai?”.

Ví dụ YAML minh họa:

~~~yaml
service:
  name: order-service
  system: checkout
  domain: commerce
  lifecycle: production
  tier: critical
  primary_owner_team: checkout-team
  product_owner_group: checkout-product
  technical_steward_role: order-steward
  oncall:
    primary_rotation: "<checkout-oncall-link>"
    secondary_rotation: "<checkout-secondary-link>"
  repository: "<git-repository-link>"
  deployment: "<deployment-dashboard-link>"
  runbook: "<order-runbook-link>"
  slo: "<checkout-slo-dashboard-link>"
  api_contract: "<openapi-contract-link>"
  event_contracts:
    - "<order-created-schema-link>"
    - "<order-paid-schema-link>"
  dependencies:
    - inventory-service
    - payment-service
    - order-database
    - messaging-platform
  data_classification: restricted-business
  environment: production
  last_ownership_review: "YYYY-MM-DD"
~~~

Đây là schema minh họa, không phải định dạng bắt buộc của công cụ cụ thể. Giá trị `<...>` chỉ là placeholder; không copy nguyên vào production catalog.

Các thuộc tính thiết yếu:

1. Tên duy nhất, domain/system và lifecycle.
2. Primary owner team và cách tìm người trực hiện tại.
3. Product/journey owner nếu khác service owner.
4. Repository, pipeline và artifact/deployment liên quan.
5. API/event contracts và dependency graph.
6. SLI/SLO, runbook, dashboard và pager routing.
7. Data stores, mức độ nhạy cảm, backup/DR objectives.
8. Tier, expected load và policy khi sự cố.
9. Chi phí/resource allocation nếu tổ chức theo chargeback.
10. Ngày xem xét ownership và người phê duyệt.

Nên cập nhật catalog tự động từ repo/CI/IaC khi khả thi. Không hard-code tên một cá nhân là owner vĩnh viễn; có thể thêm steward nhưng phải có **rotation source of truth** cho on-call.

## 10. CODEOWNERS không phải bản hợp đồng ownership đầy đủ

Một file CODEOWNERS có thể yêu cầu review từ nhóm Checkout đối với code:

~~~text
/services/cart-service/           @org/checkout-team
/services/order-service/          @org/checkout-team
/services/pricing-service/        @org/checkout-team
/services/checkout-orchestrator/  @org/checkout-team
```

Nhưng CODEOWNERS không đảm bảo:

- Team đang có quyền deploy/rollback production.
- SLO và alert được route đúng.
- API/event contracts được publish và versioned.
- Database, topic và cloud resources có owner.
- Người trực biết service và các failure modes.
- Người ngoài nhóm không thể gây thay đổi bằng config/IaC khác repository.
- Một service đã chuyển nhóm được cập nhật mọi nơi.

**Dùng CODEOWNERS để bảo vệ review** và service catalog + IAM + CI/CD + on-call routing để hiện thực trách nhiệm. Những nguồn dữ liệu này cần được kiểm tra tính nhất quán, không để mỗi nơi ghi một tên team khác nhau.

## 11. Phân công trách nhiệm nội bộ khi một nhóm có nhiều service

Một nhóm có thể định nghĩa các vai trò:

- **Team accountable owner:** phụ trách chất lượng và ưu tiên tổng cho toàn portfolio, thường là engineering manager/technical lead theo tổ chức.
- **Service steward:** người hoặc cặp người theo dõi sức khỏe một service, roadmap nợ kỹ thuật, migration và tài liệu trong khoảng thời gian.
- **Feature lead:** người chịu trách nhiệm một thay đổi xuyên nhiều service.
- **Incident commander:** người điều phối sự cố cụ thể, không nhất thiết là steward.
- **Primary/secondary on-call:** người nhận page và có quyền triage theo ca.
- **Data/security delegate:** người phụ trách kết nối với nhóm chuyên môn cho vấn đề dữ liệu/bảo mật.

Một cách phân công ví dụ:

| Service | Accountable team | Steward phiên này | Back-up steward | On-call |
| --- | --- | --- | --- | --- |
| cart-service | Checkout | Engineer A | Engineer B | Checkout rotation |
| order-service | Checkout | Engineer B | Engineer C | Checkout rotation |
| pricing-service | Checkout | Engineer C | Engineer D | Checkout rotation |
| order-events-worker | Checkout | Engineer D | Engineer A | Checkout rotation |

Tên A/B/C/D là minh họa. Steward không phải “sở hữu tư nhân” code hay người duy nhất được sửa. Mỗi service cần tài liệu, test và reviewer đủ để **nhóm** giữ trách nhiệm dài hạn.

Có thể luân chuyển steward theo quý/học kỳ kỹ thuật. Khi thay steward, nên có handoff về metrics, incident, dependency và backlog; không chỉ thay tên trong bảng.

## 12. Ma trận quyền quyết định: ai được làm gì?

Với một nhóm quản lý nhiều service, nên phân biệt:

| Quyết định | Owner chính | Nhóm cần tham gia | Kiểm soát |
| --- | --- | --- | --- |
| Thay business rule của Order | Checkout | Product, QA | Test/ADR nếu thay behavior lớn |
| Thay public API Order | Checkout | Consumer teams | Contract compatibility/versioning |
| Thay event schema `OrderPaid` | Checkout | Consumers, Messaging | Schema compatibility gate |
| Chạy migration Order DB | Checkout | Data Platform/DBA khi rủi ro cao | Backward-compatible rollout/backup |
| Thay cluster/network policy | Platform | Checkout/Security | Change policy, blast-radius review |
| Cập nhật authorization scopes | Checkout + Security policy | Identity/Consumer | Security review, audit |
| Thay shared Kafka cluster | Messaging Platform | Owners của topics/consumers | Platform SLO và migration plan |
| Rollback Order Service | Checkout on-call | Platform khi cần | Runbook, compatibility check |
| Xử lý payment reconciliation | Payment owner | Checkout/Finance | Financial control, audit |
| Đổi tier/SLO của Checkout | Business/journey owner | Checkout/SRE | Product impact/SLO approval |
| Ngừng dùng Cart API cũ | Checkout | Active consumers | Deprecation window và verification |

**Quyền quyết định phải đi đôi với trách nhiệm.** Một nhóm bị page vì Order lỗi nhưng không có quyền xem logs hoặc rollback thì ownership chỉ mang tính danh nghĩa. Ngược lại, quyền đổi database schema cho tất cả teams mà không có review/audit có thể phá tính độc lập của các service.

Các thao tác nhạy cảm cần least privilege, hai người phê duyệt hoặc emergency workflow phù hợp chính sách; ownership không cho phép bỏ qua kiểm soát an toàn.

## 13. RACI cho một thay đổi xuyên service

Ví dụ nhóm Checkout muốn thêm loại giảm giá mới, cần Order, Pricing và Cart cùng thay đổi, có thể chạm Payment:

- **R (Responsible):** người trực tiếp thực hiện.
- **A (Accountable):** người chịu trách nhiệm kết quả và quyết định cuối.
- **C (Consulted):** người cần tham khảo.
- **I (Informed):** người cần nhận thông tin.

| Công việc | Checkout | Payment | Platform | Product |
| --- | --- | --- | --- | --- |
| Thiết kế logic giảm giá | R | C | I | A |
| Cập nhật Pricing API/contract | A/R | C | I | C |
| Cập nhật Cart/Order clients | A/R | C | I | C |
| Cập nhật rule tính phí Payment | C | A/R | I | C |
| Kiểm tra performance/SLO | A/R | C | C | I |
| Rollout feature flag/canary | A/R | C | C | I |
| Bảo vệ cluster/quota chung | C | C | A/R | I |

RACI chỉ là mô hình minh họa; mỗi tổ chức phải xác định authority thật, đặc biệt với thay đổi payment hoặc dữ liệu quan trọng. Tránh nhiều A cho một quyết định không có người chốt.

RACI có ích khi phối hợp đa nhóm, nhưng trong incident khẩn cần biết **người nào đang trực và quyền nào có thể sử dụng ngay**, không chỉ nhóm trên giấy.

## 14. On-call: một vòng trực cho nhiều service có thể hoạt động thế nào?

Mô hình phổ biến là một **team-level rotation**, trong đó primary chịu trách nhiệm cảnh báo của các service team sở hữu.

~~~text
Service alerts
  cart-service ---------+
  order-service --------+
  pricing-service ------+--> Checkout primary on-call
  order-events-worker --+          |
  admin-api ------------+          +--> Secondary
                                    |
                                    +--> Service steward / domain SME
                                    |
                                    +--> Platform/DB/Messaging/Payment
```

Ưu điểm: một đầu mối nhận alert, điều phối theo hành trình checkout; người trực không phải đoán service owner. Nhược điểm: nếu portfolio quá rộng hoặc có nhiều stack khác nhau, một người khó xử lý mọi alert.

Thiết kế rotation cần:

1. Primary và secondary có coverage thực, timezone và ngày lễ rõ.
2. Tất cả service critical có runbook và dashboard tại chỗ.
3. Người trực biết ít nhất thao tác triage, giảm tác động và escalation cho từng service.
4. Các việc production high-risk có quyền/phê duyệt rõ.
5. Page routing dựa vào service catalog và mức tác động, không theo người viết code.
6. Alert được deduplicate theo sự cố để không nhận 30 page cùng một nguyên nhân.
7. Hand-off ca có thay đổi deploy, backlog, degraded dependencies và incident đang mở.
8. On-call load được đo và có cơ chế điều chỉnh portfolio/nhân sự.
9. Không ép người chưa được đào tạo thực hiện DB failover hoặc consumer-offset reset.
10. Có diễn tập/kiểm tra lại khi thêm một service mới vào rotation.

**Không chia mỗi service một lịch trực riêng nếu thực chất vẫn là cùng sáu người** trừ khi có giá trị rõ. Năm rotation chồng nhau có thể làm một người nhận page từ mọi dịch vụ không minh bạch.

## 15. Trách nhiệm của nhóm khi service đã lên production

Một nhóm sở hữu nhiều service thường chịu trách nhiệm các mức:

**Reliability:** SLI/SLO, error budget, incident response, capacity, autoscaling, retry/circuit breaker, graceful degradation.

**Maintainability:** tests, CI, code review, dependency upgrades, Java/JDK framework updates, schema evolution, technical debt.

**Operability:** dashboards, structured logging, tracing, alert routing, runbook, backup verification, DR drills, on-call.

**Security:** threat model, authN/authZ, secrets, vulnerability remediation, audit, PII classification, least privilege.

**Product correctness:** invariant nghiệp vụ, validation, payment/idempotency, eventual consistency, user experience và support escalations.

**Data integrity:** migrations, schema ownership, retention, export/delete, outbox, CDC, reconciliation.

**Cost and performance:** cache effectiveness, p95/p99 latency, resource consumption, cloud spend và dependency budgets.

**Lifecycle:** deprecation, ownership transfer, decommission và lưu trữ dữ liệu đúng chính sách.

Những trách nhiệm này phải được xem là **công việc thực** trong roadmap. Không thể mong nhóm chịu toàn bộ trách nhiệm rồi lên kế hoạch sprint với 100% thời gian chỉ dành cho feature mới.

## 16. SLO và tier hóa portfolio nhiều service

Không phải service nào cũng phải có cùng mức SLO hay yêu cầu trực 24/7.

| Tier minh họa | Loại service | Mục tiêu vận hành điển hình | Quy trình |
| --- | --- | --- | --- |
| Tier 0 – trọng yếu | Payment/Order write path, identity trung tâm | SLO nghiêm, alert tác động ngay, DR/backup chặt | On-call liên tục nếu kinh doanh yêu cầu |
| Tier 1 – quan trọng | Cart/Pricing/Search core | SLO cụ thể, sự cố có escalation rõ | On-call theo mức ảnh hưởng |
| Tier 2 – hỗ trợ | Recommendations, analytics enrichment | Cho phép degrade hoặc phục hồi chậm hơn | Alert/ticket theo risk |
| Tier 3 – nội bộ/thử nghiệm | Admin tools, prototypes chưa phục vụ khách hàng | Theo vòng đời và giờ hỗ trợ | Không page ngoài giờ nếu không cần |

Tier và giá trị SLO là quyết định theo Business Impact Analysis, không dựa vào việc service viết bằng công nghệ nào. Một worker nhỏ không có UI có thể là Tier 0 nếu nó quyết định ledger, đối soát hoặc nghĩa vụ pháp lý.

Khi một team có nhiều service, tier giúp phân bổ sức chú ý: không để bot gửi email thử nghiệm tranh cùng mức ưu tiên với lỗi thanh toán. Nhưng **Tier thấp không có nghĩa service không cần owner, data retention hay security**.

## 17. SLO của từng service khác với SLO hành trình người dùng

Một Checkout flow có thể gọi Cart, Pricing, Inventory, Payment và Order.

~~~text
User Journey: Checkout succeeded
        |
        +-- Cart API success
        +-- Pricing result valid
        +-- Inventory reservation succeeds
        +-- Payment state confirmed/pending safely
        +-- Order durable commit
        +-- UI communicates final state
```

Một service trả HTTP 200 không đảm bảo hành trình thành công. Cần:

- Service-level SLIs: latency, error rate, queue lag, durable state, availability.
- Journey-level SLIs: tỷ lệ checkout hoàn tất theo định nghĩa, thời gian từ thao tác đến trạng thái có ý nghĩa.
- Business invariants: không double charge, không duplicate order effect, không mất inventory reservation.
- Reliability ownership: nhóm Checkout điều phối end-to-end, dù Payment/Inventory do nhóm khác xử lý.
- On-call collaboration: khi Alert Journey burn-rate cao, page primary hành trình và route đến service owner theo root-cause evidence.

Một service hỗ trợ nhiều hành trình có thể cần nhiều owner sản phẩm tham gia SLO design. Tuy nhiên một owner kỹ thuật chính vẫn nhận trách nhiệm tổng cho service để tránh alert rơi giữa các nhóm.

## 18. Kiểm soát alert fatigue khi một nhóm nhận nhiều service

Một nhóm có sáu service có thể bị đánh thức mỗi khi một Pod restart, broker lag tăng nhẹ, cache miss tăng hoặc deployment test thất bại. Nếu không lọc, on-call trở thành bottleneck.

Phân loại:

| Loại tín hiệu | Ví dụ | Phản ứng |
| --- | --- | --- |
| User-impact page | Checkout success giảm nhanh, Payment status không xác định | Gọi primary và escalation |
| Imminent risk page | Order backlog/oldest age sắp vượt ngưỡng nghiệp vụ | Page nếu con người cần hành động ngay |
| Ticket | Dependency update sắp hết hỗ trợ, disk growth trong vài tuần | Backlog owner |
| Dashboard | 1 Pod restart nhưng redundancy và SLO bình thường | Quan sát, không page |
| Security | Credential leak, bất thường truy cập | Security incident workflow riêng |
| Deployment gate | Contract incompatibility trong CI | Block deploy, route tới change owner |

**Một page nên có hành động hữu ích.** Alert cần include service, environment, tier, SLI impact, owner, dashboard, runbook và escalation. Deduplicate correlated failures: nếu DB outage khiến 4 service cùng báo lỗi, có thể có một incident chính và các tín hiệu phụ, thay vì 40 page không có phân cấp.

Các thước đo: pages/person/week, actionability ratio, false positive rate, sleep interruptions, MTTA, escalation vì thiếu runbook, repeat incidents. Đừng giảm page bằng cách tắt hoàn toàn monitoring; phải điều chỉnh routing và alert để phù hợp tác động.

## 19. Service steward và chống rủi ro “bus factor”

Một nhóm nhiều service thường có lịch sử không đồng đều:

- Engineer A viết cart-service nên mọi người chỉ hỏi A.
- Engineer B hiểu Kafka consumers.
- Engineer C biết secret rotation.
- Engineer D duy trì database migrations.

Rủi ro: nếu A/B nghỉ, người trực không thể giải quyết lỗi dù trên giấy Checkout Team là owner.

Các cơ chế giảm:

1. **Primary + backup steward** cho service quan trọng.
2. Hai người review thay đổi rủi ro; rotate pairing để chia sẻ kiến thức.
3. Runbook tập trung vào failure modes, không phải một người.
4. Diễn tập onboarding: người mới phải chạy service, deploy test và xử lý synthetic incident.
5. Service ownership health review: ai có thể rollback? Ai biết schema? Ai nhận page?
6. Code conventions/golden path để giảm những ngoại lệ không cần thiết.
7. ADR ngắn cho lựa chọn quan trọng và trade-offs.
8. Hạn chế service chỉ chạy được trên máy của tác giả.
9. Handoff khi chuyển steward/đổi team.
10. Bảo đảm manager dành thời gian cho khắc phục technical debt và đào tạo.

**Bus factor** không chỉ là “bao nhiêu người từng commit”. Năng lực thực tế gồm quyền truy cập, hiểu dependency, biết thao tác production và có thể đưa ra quyết định khi áp lực.

## 20. Đánh giá tải nhận thức và ngưỡng cần tái cấu trúc nhóm

Số service chỉ là một chỉ báo. Nhóm nên theo dõi đồng thời:

| Chỉ số | Dấu hiệu tải cao |
| --- | --- |
| Số runtime/language khác nhau | Mỗi service có toolchain và on-call semantics riêng |
| Số data stores và migrations | Dữ liệu bị phân tán, restore phức tạp |
| Số external integrations | Nhiều failure modes, hợp đồng thay đổi |
| Số deployments/config changes | Mỗi ngày có nhiều release khó theo dõi |
| Page volume và alert noise | Người trực không đủ sức hành động |
| Time to understand/restore service | Người mới cần lâu để phục hồi |
| Cross-team dependencies per feature | Thường xuyên chờ nhóm khác |
| Số service không có tests/runbook | Operational debt tích tụ |
| Critical-person dependencies | Mất một người là mất khả năng vận hành |
| Flow time của thay đổi đơn giản | Thay một API mất nhiều tuần |
| SLO violations và recurring incidents | Portfolio vượt capacity của team |

Một buổi **portfolio review** nên phân loại từng service: criticality, usage, cost, incident burden, roadmap, dependencies, steward coverage và cơ hội gom/tách/ngừng.

Các lựa chọn khi quá tải:
- Giảm số deployables không tạo giá trị, chuyển về module trong cùng runtime.
- Standardize stack và golden paths.
- Tạo platform self-service cho CI/CD, telemetry, secrets, DB provisioning.
- Chuyển service sang nhóm domain phù hợp có đủ quyền/năng lực.
- Tăng capacity hoặc lập team mới khi domain đã đủ lớn.
- Ngừng/retire service không có người dùng.
- Giảm feature WIP và dành thời gian trả nợ vận hành.

Không nên tự động “tách nhóm vì sở hữu quá 10 service”; cần quyết định dựa trên ranh giới domain và bằng chứng tổ chức.

## 21. Portfolio ownership: nhìn nhiều service như một sản phẩm vận hành

Nếu một team quản lý cả Cart, Pricing và Order, nên có **portfolio backlog** bao gồm:

- Product feature commitments.
- SLO/reliability improvements.
- Security patches và dependency upgrades.
- DB migration và schema compatibility.
- API/event deprecations.
- Capacity và cost optimization.
- Observability/runbook/DR tests.
- Tech debt và domain simplification.
- Incident action items.

Một mô hình ưu tiên:

| Loại việc | Điều kiện ưu tiên | Chủ động lên lịch |
| --- | --- | --- |
| Vi phạm SLO hoặc mất dữ liệu | Phục hồi và xử lý rủi ro cao nhất | Ngay, theo severity |
| Lỗ hổng security critical | Theo chính sách xử lý rủi ro | Có owner/deadline |
| API/event contract breaking | Chặn consumer hoặc deploy | Trước khi release |
| Feature user-impact lớn | Theo sản phẩm và năng lực | Trong kế hoạch |
| Cải thiện CI/observability | Giảm lead time và incident toil | Duy trì đều |
| Dead service/deprecation | Giảm chi phí và tải nhận thức | Đưa vào roadmap |
| Tối ưu không ảnh hưởng người dùng | Theo đo lường thực | Không lấn át nghĩa vụ bắt buộc |

Một nhóm không thể nhận thêm service vô hạn chỉ vì “code không nhiều”. Mỗi service production tạo **chi phí sở hữu thường xuyên** dù tuần này không có commit.

## 22. Ownership và repository topology: monorepo hoặc multirepo

Monorepo và multirepo đều hỗ trợ một team sở hữu nhiều service.

**Monorepo:**

~~~text
commerce/
  cart-service/
  order-service/
  pricing-service/
  order-events-worker/
  shared-contracts/
  infra/
~~~

Ưu điểm: dễ thấy các thay đổi liên quan, chia sẻ tooling và review. Rủi ro: coupling build, deploy hàng loạt ngoài ý muốn, boundary code bị lỏng hoặc một thư viện “shared” thành cơ chế phụ thuộc sâu.

**Multirepo:**

~~~text
org/cart-service
org/order-service
org/pricing-service
org/order-events-worker
org/checkout-contracts
```

Ưu điểm: release và access policy độc lập. Rủi ro: khó audit contract changes xuyên repo, dependency updates nhiều nơi, service catalog thiếu thông tin nếu không tự động hóa.

**Không quyết định ownership bằng việc repo nằm ở đâu.** Một repo có thể chứa nhiều service của cùng nhóm; một service có thể gồm code, IaC, schema và assets ở nhiều repo. Catalog/CI phải nối được các artifact với owner thực.

Với cả hai mô hình, bảo vệ độc lập deploy bằng build/test scopes, artifact versions và contract compatibility gates. Không tự nhiên deploy tất cả service chỉ vì cùng commit trong monorepo.

## 23. Quy tắc giao tiếp giữa các service do cùng một nhóm sở hữu

“Cùng team” không phải giấy phép bỏ qua API contracts:

- Service A không truy cập trực tiếp bảng private của service B nếu boundary dữ liệu quy định không cho phép.
- Public API/event có version và thay đổi có quy trình tương thích.
- Internal calls vẫn cần timeouts, retry budgets, idempotency, auth và observability.
- Consumer/provider tests nên bao phủ những interaction quan trọng.
- Đừng hard-code response assumptions chỉ vì các developer cùng ngồi một phòng.
- Khi có nhiều deployable, rolling deployment tạo cửa sổ version cũ/mới cùng tồn tại.
- Ownership catalog nên phản ánh service dependencies để incident nhanh chóng tìm được hướng điều tra.
- Release phối hợp có thể sử dụng feature flags và expand/contract schema.
- Không gộp shared library cho business logic của hai bounded contexts khác nhau chỉ vì tiện.
- Schema evolution phải tính cả message tồn trong broker, không chỉ API request hiện tại.

Một team vẫn có thể triển khai các service ở thời điểm khác nhau. Nếu Order v2 yêu cầu Pricing v2 nhưng Pricing v1 còn chạy ở một region, cần compatibility matrix hoặc rollout order rõ.

## 24. API contract ownership khi nhóm khác là consumer

Giả sử Checkout Team sở hữu `order-service` và `OrderCreated` event, còn Fulfillment Team tiêu thụ.

**Checkout Team chịu trách nhiệm:**

1. Công bố event schema, semantics, field required/optional và version.
2. Thông báo deprecation timeline.
3. Verify compatibility với consumer đang active.
4. Theo dõi producer publish success và outbox delivery guarantees.
5. Sửa tài liệu khi behavior thay đổi.

**Fulfillment Team chịu trách nhiệm:**

1. Consumer đúng contract đã công bố.
2. Idempotency khi event trùng hoặc replay.
3. Xử lý event cũ/mới theo hỗ trợ.
4. Monitoring consumer lag, retry, DLQ.
5. Tham gia plan migration nếu producer thay đổi.

Cả hai nhóm cần phối hợp khi thay contract, nhưng không có nghĩa không ai sở hữu lỗi. Khi producer phát payload sai schema đã hứa, Checkout là owner chính sửa producer; khi consumer không xử lý được event hợp lệ, Fulfillment là owner chính sửa consumer.

**Contract verification không thay thế production monitoring**: một version pair có thể pass schema nhưng vẫn lỗi do network, IAM, quota, timeout hoặc dữ liệu thực.

## 25. Event và data ownership: tránh “shared database = shared responsibility”

Một trong những lỗi nghiêm trọng nhất là nhiều service/nhóm cùng ghi một database schema mà không có quyền quyết định rõ.

~~~text
Order Service --> Order DB (Checkout-owned schema)
Payment Service --> Payment DB (Payment-owned schema)
Inventory Service --> Inventory DB (Inventory-owned schema)

OrderCreated / PaymentAuthorized / StockReserved
       -> event contracts và integration workflows
```

Một nhóm quản lý nhiều service có thể dùng chung DB infrastructure để tiết kiệm, nhưng vẫn nên ghi rõ **schema/table ownership** và migration quyền nào. Nếu hai service của cùng nhóm ghi cùng một bảng, việc này tạo coupling giữa deployables; có thể chấp nhận trong một giải pháp tạm thời có rationale, nhưng nên nhận thức transaction/migration impact.

Với dữ liệu cá nhân hoặc giao dịch:
- Xác định authoritative source of truth.
- Retention, encryption, deletion/export và audit theo chính sách.
- Data classification/PII và data access boundaries.
- Change approvals cho migration destructive.
- Backup/RPO/RTO và kiểm thử restore.
- CDC/outbox, event schema, consumer offsets, reconciliation.
- Quy tắc consistency và retry side effects.

Một service “có owner” nhưng dữ liệu quan trọng không có người chịu trách nhiệm integrity vẫn là ownership chưa hoàn chỉnh.

## 26. Shared libraries, SDK và internal platform responsibilities

Một nhóm có nhiều service dễ tạo `common-utils` hoặc `shared-domain` để tái sử dụng code. Cần phân biệt:

**Shared technical library:** logging, tracing, HTTP client, resilience policy, validation helpers. Có thể thuộc Platform Team hoặc maintainers cụ thể; version và deprecation rõ.

**Shared business library:** logic tính giá, trạng thái đơn, tax rules. Nếu nhiều service depend vào cùng code và cần deploy đồng bộ, việc này có thể phá boundary. Nên cân nhắc một service/domain API hoặc module trong cùng deployment.

**Generated client từ contract:** tăng tính nhất quán, nhưng contract owner vẫn chịu trách nhiệm backward compatibility; không xem generated code là bằng chứng hai runtime tương thích.

Với shared library do Checkout sở hữu:
- Có maintainer/release policy.
- Có compatibility tests.
- Không buộc mọi service upgrade ngay một lúc.
- Có dependency vulnerability scanning.
- Có versioning và hướng dẫn migration.
- Không dùng library để bypass API/service boundaries.

Nếu library được nhiều nhóm dùng, mô hình ownership có thể chuyển từ product team sang platform/inner-source maintainers khi có bằng chứng nhu cầu chung.

## 27. Platform team cung cấp golden path thay vì gánh mọi service

Để một nhóm quản lý nhiều service có thể bền vững, platform nên cung cấp self-service:

| Năng lực nền tảng | Kỳ vọng của team sở hữu service |
| --- | --- |
| Template Java/Spring Boot hoặc runtime được hỗ trợ | Dùng bộ chuẩn, không tự viết mọi thứ từ đầu |
| CI build/test/scanning | Team chịu trách nhiệm code và kết quả test |
| Deployment GitOps/Helm | Team điều khiển release theo policy |
| Secrets/identity | Team cấu hình quyền đúng, Platform/Security cung cấp cơ chế |
| Observability | Team định nghĩa SLIs, alert, runbook và dùng instrumentation |
| Database provisioning/backups | Team quản lý schema, migrations và kiểm thử khôi phục nghiệp vụ |
| Messaging provisioning | Team sở hữu topic contracts/consumer behavior |
| Service catalog | Team cập nhật metadata, ownership và dependency |
| Runtime upgrades | Platform hỗ trợ toolchain, Team nâng service và kiểm thử |
| Cost visibility | Team chịu trách nhiệm footprint, platform cung cấp đo lường |

**“Platform owns Kubernetes” không đồng nghĩa “Platform owns availability của Order”.** Platform cung cấp infrastructure SLO; Checkout Team chịu trách nhiệm SLO của ứng dụng và phối hợp khi dependency bị lỗi.

Một team tự viết cách deploy khác cho từng service sẽ tăng toil. Golden paths có thể giảm đáng kể cognitive load khi service count tăng.

## 28. Tránh ticket dependencies và cơ chế interaction giữa team

Khi nhóm Checkout cần một database, topic hoặc policy mới, một yêu cầu ticket chờ nhiều tuần sẽ hạn chế autonomy. Có thể thiết kế interaction:

- **X-as-a-Service:** Platform cung cấp self-service templates, API và docs.
- **Collaboration:** Hai nhóm phối hợp tạm thời khi thay kiến trúc hoặc data contract.
- **Facilitating:** Chuyên gia hỗ trợ team cải thiện năng lực trong một giai đoạn, không tạo dependency vĩnh viễn.

Với mỗi interaction, ghi:
- Mục đích và phạm vi.
- Owner của interface/contract.
- Mức service support/response mong muốn.
- Cách debug và escalation.
- Những quyền team có thể tự thực hiện.
- Khi nào phải xin phê duyệt.
- Khi nào interaction kết thúc.

Nếu mọi thay đổi của Order Service đều phải nhờ Platform chỉnh YAML thủ công, nhóm Checkout chưa thực sự có năng lực sở hữu service đầy đủ. Platform nên cải thiện tooling hoặc phân quyền có guardrail.

## 29. Incident cross-service: trách nhiệm không biến mất ở ranh giới API

Tình huống: Checkout success rate giảm; Order Service p99 tăng vì Payment API trả timeout.

~~~text
Checkout SLO alert
     |
     v
Checkout on-call nhận page
     |
     +-- Kiểm tra Order traces, deadlines, retry attempts
     +-- Xác định Payment downstream timeout
     +-- Mời Payment on-call vào incident
     +-- Xác định degraded mode / pending state
     +-- Bảo vệ idempotency, không double charge
     +-- Theo dõi user journey recovery
```

**Checkout Team** không có trách nhiệm sửa toàn bộ code Payment nhưng chịu trách nhiệm:
- Nhận/triage journey impact.
- Không để Order retry vô hạn hoặc tạo tác động nghiệp vụ trùng.
- Truyền trạng thái đáng tin cho frontend.
- Phối hợp mitigations và theo dõi hiệu quả.
- Cung cấp trace IDs và test case cho Payment Team.
- Xác minh toàn bộ hành trình đã phục hồi.

**Payment Team** chịu trách nhiệm Payment service/provider behavior và payment reconciliation theo scope của họ.

**Incident commander** có thể được chỉ định theo impact và policy, không nhất thiết luôn là Checkout lead. Mỗi action trong incident có owner cụ thể và thời hạn cập nhật.

Không nên kết luận “đã tìm ra lỗi ở service khác, xong việc” trong khi checkout khách hàng vẫn không thể hoàn tất.

## 30. On-call runbook cho portfolio nhiều service

Một index runbook nên cho phép người trực tìm ngay:

~~~text
Checkout Team / On-call Index
  1. Checkout journey burn-rate alert
  2. order-service 5xx / stuck PENDING
  3. pricing-service timeout / cache miss storm
  4. cart-service high latency
  5. order-events-worker consumer lag / DLQ
  6. DB pool saturation / migration lock
  7. External Payment failure / reconciliation
  8. Kubernetes rollout / Not Ready
  9. Security incident / credential compromise
 10. DR restore / regional failover
```

Mỗi runbook cần:
- Trigger alert và tác động người dùng.
- Owner, secondary và các dependency contacts.
- Dashboard/log/trace queries có thể mở được.
- Bước read-only triage.
- Decision tree theo failure modes.
- Mitigations phù hợp quyền thực tế.
- Stop conditions và escalation khi rủi ro.
- Verification theo SLO và domain data invariants.
- Rollback/failback, không chỉ “restart pods”.
- Last reviewed và cách cập nhật.

Lệnh production cần chỉ rõ context/namespace, scope, quyền và expected outcome; không dùng wildcard destructive làm ví dụ mặc định. Người trực phải có khả năng dừng tại bước không đủ bằng chứng.

## 31. Ví dụ runbook: Order API tăng lỗi

**Sự kiện:** SLO checkout báo tỷ lệ tạo đơn thành công giảm và Order API có nhiều 5xx.

**Bước 1: Xác định impact**
- Region/tenant/user journey nào bị ảnh hưởng?
- Traffic/latency có tăng hay giảm? Có code/config deploy gần thời điểm lỗi?
- Mỗi nhóm error code: 500/502/503/504, validation 4xx, timeouts?
- Có nguy cơ create order trùng hoặc trạng thái payment không rõ?

**Bước 2: Khoanh root cause**
- API gateway và ingress routing.
- Order JVM/thread pools, DB connection wait, GC, Pod readiness.
- Inventory/Payment downstream latency và circuit breaker state.
- Outbox backlog, broker lag, consumer failure.
- DB migration/schema mismatch.

**Bước 3: Mitigation có kiểm soát**
- Nếu release gây regression và rollback tương thích, rollback theo change policy.
- Nếu provider lỗi, giảm retry và dùng trạng thái PENDING/compensation theo contract.
- Nếu DB bị saturation, rate limit/admission và gọi DBA/Platform theo quyền.
- Nếu queue backlog, không purge hoặc reset offset tùy tiện.

**Bước 4: Verification**
- Journey SLI/SLO phục hồi, error-rate/latency giảm theo observation window.
- Không có double charge, duplicate order hoặc mất outbox event.
- Backlog và pending reconciliation được theo dõi tới khi an toàn.
- Ghi timeline, action owner, change revision và follow-up.

Một runbook phải phục vụ người trực **không phải tác giả** của service. Nếu mọi bước yêu cầu gọi một cá nhân cụ thể, runbook chưa giải quyết bus factor.

## 32. Data migration và release nhiều service do cùng team sở hữu

Việc một nhóm cùng sở hữu Order/Pricing/Cart có thể khiến họ “dễ” deploy đồng thời, nhưng vẫn phải kiểm soát version overlap:

1. Phát hành provider/API chấp nhận cả contract cũ và mới.
2. Deploy consumer mới sau khi provider hỗ trợ.
3. Theo dõi các consumer thực đang chạy trên nhiều region.
4. Migrate data bằng expand/contract: thêm schema mới, backfill, dual-read/write khi cần, rồi bỏ schema cũ sau.
5. Dùng feature flags và canary để hạn chế blast radius.
6. Test migration/rollback compatibility.
7. Đảm bảo event cũ trong broker còn xử lý được sau deploy.
8. Bỏ đường tương thích cũ khi có bằng chứng không còn consumer dùng.

**Cùng team không có nghĩa không có distributed systems issues.** Khi các service độc lập triển khai, vẫn có partial failures, network partitions, retries và version skew.

Các thay đổi xuyên nhiều service nên có một **change owner** tổng và từng service reviewer; không dùng một release script bí mật chỉ tác giả mới hiểu.

## 33. Data/contract review khi nhóm quản lý nhiều domain nhỏ

Một nhóm có thể quản lý nhiều service nhưng mỗi service có loại dữ liệu và retention riêng. Ownership review nên trả lời:

- Service nào là authoritative source của trường dữ liệu?
- Hệ khác được đọc dữ liệu qua API/event hay copy DB?
- Khi data subject yêu cầu xóa/xuất dữ liệu, service nào thực hiện?
- Khi schema thay đổi, ai kiểm tra consumer compatibility?
- Có event chứa PII vượt nhu cầu consumer không?
- TTL, retention và object storage lifecycle thuộc team nào?
- Backup/DR đã đo RPO/RTO chưa?
- Idempotency/dedupe records có được backup cùng dữ liệu nghiệp vụ không?
- Audit log có quyền truy cập và thời hạn lưu theo chính sách không?
- Có thao tác thủ công hỗ trợ khách hàng nào có thể thay đổi trạng thái production không?

Một nhóm Checkout không nên coi tất cả dữ liệu customer profile là của mình chỉ vì họ hiển thị địa chỉ giao hàng; Profile/Identity có thể là source of truth và Checkout chỉ giữ một snapshot được phép theo domain contract.

## 34. Security khi một nhóm sở hữu nhiều service

Một lỗi cấu hình IAM có thể tác động cả portfolio nếu các service dùng chung service account và secret quá rộng.

Các nguyên tắc:

- Mỗi service có workload identity/secret phạm vi tối thiểu; không để một key truy cập toàn bộ DB của cả nhóm.
- Phân quyền runtime theo service và environment; không dùng credential production trong tests.
- Code review/security checks áp dụng cho mọi service, kể cả worker ít được thay đổi.
- Inventory secrets, certificates, APIs, ingress và external callbacks với owner.
- Threat model cho dữ liệu và luồng nhạy cảm.
- Dependency scanning và patch cadence cho service không còn nhiều feature.
- Rate limiting, authN/authZ, tenant isolation ở mỗi boundary.
- Rotation/credential revocation có runbook và kế hoạch giảm downtime.
- Security incident routing khác với availability incident khi cần bảo toàn bằng chứng.
- Không đưa token/PII vào logs, dashboards, runbooks hoặc incident channels.

Nếu một service có requirement pháp lý/kiểm toán vượt xa các service khác, có thể xem xét owner chuyên trách hoặc cơ chế review sâu hơn thay vì áp cùng policy nhẹ cho toàn bộ nhóm.

## 35. Chi phí vận hành: nhiều service làm tăng fixed cost

Mỗi deployable thường kéo theo:

- CI pipeline/build/cache.
- Container image, registry, SBOM và vulnerability scanning.
- Config, secrets, IAM role.
- Deployment/manifests/rollouts.
- Dashboards, tracing và log retention.
- SLO, alert, runbook và on-call knowledge.
- Data store/migration hoặc network dependencies.
- Backup/DR coverage.
- Library/runtime upgrades.
- Định kỳ test compatibility với consumer/provider.
- Quota, capacity planning và billing metadata.

Vì vậy có thể có lợi thế của microservices ở **independent scaling và failure isolation** nhưng cũng có fixed cost tăng. Một nhóm nhiều service nên đánh giá cost-to-operate và số lần cần deploy độc lập.

**Tổng chi phí không chỉ là CPU/RAM**. Thời gian kỹ sư tìm lỗi, giấy phép observability, egress, backup, CI minutes và on-call interruptions đều là chi phí thực.

Có thể theo dõi spend theo service/team qua labels/tags, nhưng không dùng số chi phí đơn lẻ để quyết định xóa service nếu nó cung cấp isolation/availability quan trọng.

## 36. Cấu trúc tài liệu cho một team owning nhiều service

Một workspace đơn giản:

~~~text
checkout-team/
  README.md                  # mission, owners, on-call
  SERVICE_CATALOG.md         # services and lifecycle
  OPERATIONS.md              # team SLO and incident playbook
  DEPENDENCIES.md            # upstream/downstream contracts
  RUNBOOK_INDEX.md           # navigation to per-service runbooks
  ONBOARDING.md              # local setup / permissions / reviews
  CHANGE_POLICY.md           # release/rollback and migration
  DR_PLAYBOOK.md             # recovery drills and evidence
  services/
    cart-service/
      README.md
      runbook.md
      slo.md
    order-service/
      README.md
      runbook.md
      slo.md
    pricing-service/
      README.md
      runbook.md
      slo.md
```

Có thể phân tán vào repo dịch vụ, service catalog và incident platform; ví dụ chỉ mô tả **các loại thông tin cần tìm được**. Tránh duplicate cùng một quy tắc ở năm tài liệu làm chúng nhanh chóng mâu thuẫn; dùng link đến source of truth.

Team homepage nên có:
- Mission và phạm vi domain.
- Danh sách service đang production, owner và priority.
- Link SLO/journey metrics và alert routing.
- On-call schedule hiện hành.
- Các dependency/platform support contacts.
- Hướng dẫn deploy, rollback, DR và escalation.
- Quy tắc review changes, data contract và incident follow-up.
- Các mục sản phẩm đã deprecate hoặc chưa sở hữu rõ.

## 37. Onboarding người mới vào portfolio nhiều service

Một onboarding tốt không yêu cầu người mới đọc mã của mọi service trong tuần đầu tiên. Chọn **hành trình end-to-end**:

1. Hiểu user journey Checkout và các bounded contexts.
2. Mở service catalog để tìm từng service owner, deployment và dependency.
3. Chạy một service local cùng test dependencies giả lập hoặc container.
4. Tìm một request bằng trace ID qua Order, Pricing và Inventory.
5. Sửa một bug nhỏ hoặc thêm test contract.
6. Deploy vào môi trường test và biết rollback an toàn.
7. Đọc on-call runbook, diễn tập một alert vô hại.
8. Tìm dashboard cho một SLO và giải thích user impact.
9. Hiểu quy tắc access to production/secret rotation.
10. Cùng buddy triage một sự cố giả lập, học escalation.

Tăng dần số service cần hiểu. Không yêu cầu một người mới trực một mình toàn bộ portfolio ngay khi chưa có quyền và kỹ năng. Có thể đặt checklist “on-call ready” thay vì chỉ “đã hoàn thành onboarding”.

## 38. Chuyển giao ownership từ nhóm A sang nhóm B

Chuyển repository không đủ. Một ownership transfer cần **thay đổi trách nhiệm thật**.

### 38.1. Trước bàn giao

- Xác định phạm vi: service, DB/schema, topics, API contracts, secrets, cloud resources.
- Thỏa thuận lý do chuyển: domain ownership, giảm tải, tái tổ chức hoặc dự án kết thúc.
- Xác nhận nhóm nhận có kỹ năng, capacity và quyền vận hành.
- Ghi trạng thái code/dependencies, nợ kỹ thuật, open incidents, SLO và backlog.
- Chốt thời điểm và điều kiện chấp nhận bàn giao.
- Lập kế hoạch hỗ trợ giai đoạn đầu, không “cắt đứt” ngay lập tức.

### 38.2. Trong bàn giao

1. Nhóm nhận chạy local/CI và deploy test được.
2. Nhóm nhận xem logs/traces/dashboard và biết service dependencies.
3. Nhóm nhận thực hành rollback, một drill outage và data restore nếu critical.
4. Chuyển CODEOWNERS, catalog, pager routing, IAM/quyền deploy và runbook.
5. Chuyển issue backlog, SLA/SLO reviews và các hợp đồng consumer.
6. Chuyển cost allocation và ownership của data/backup.
7. Thử page test để xác minh route tới người trực mới.
8. Tạo handover record: người phê duyệt, ngày, trách nhiệm còn mở.

### 38.3. Sau bàn giao

- Nhóm nhận là primary accountable owner kể từ mốc có hiệu lực.
- Nhóm cũ có thể là secondary support trong giai đoạn chuyển tiếp có thời hạn.
- Monitor incident load, flow time và knowledge gaps.
- Kết thúc secondary support chỉ khi nhóm nhận đủ năng lực.

**Không tồn tại tình trạng “code thuộc B, incident thuộc A” vô thời hạn** trừ khi đó là một thỏa thuận dịch vụ vận hành chính thức có trách nhiệm và quyền rõ ràng.

## 39. Khi nào nên tách một service hoặc nhóm mới?

Có thể xem xét tách khi:

- Một domain cần roadmap/tốc độ phát hành độc lập thực sự.
- Có specialist knowledge rất khác, ví dụ Fraud Risk hoặc Payment Ledger.
- On-call load của portfolio vượt mức bền vững.
- Nhu cầu compliance/security khác biệt đáng kể.
- Một team liên tục chờ review/deploy vì WIP quá nhiều.
- Product boundaries đã ổn định và contract đủ trưởng thành.
- Có thể chuyển data, ownership và khả năng vận hành mà không tạo gap.
- Nhóm mới có đủ người, backup, pager coverage và platform support.

**Không tách chỉ vì muốn sơ đồ org có nhiều nhóm.** Tách một service mà không có đủ nhân sự để on-call có thể tạo dịch vụ vô chủ mới. Khi chia nhóm, phải thiết kế lại API contracts, escalations, budgets và journey owner; một tổ chức mới không tự làm hệ phân tán đơn giản hơn.

Một lựa chọn khác là **gộp các service quá mảnh thành modular monolith** khi cùng team, cùng release cadence, cùng data transaction và không có nhu cầu scale độc lập.

## 40. Khi nào nên gộp hoặc ngừng dịch vụ?

Dấu hiệu một service không còn xứng đáng là một deployable riêng:

- Chỉ phục vụ một caller và không có logic nghiệp vụ độc lập.
- Luôn release lockstep với service khác.
- Có DB/table shared tightly coupled và phải thay schema cùng lúc.
- Không cần scale/security/isolation riêng.
- Rất ít traffic nhưng vẫn gây alert/patching/CI/DR cost.
- Chức năng đã được thay thế bởi một service khác hoặc platform capability.
- Không còn consumer thật, nhưng chưa ai dọn DNS/credential/topic.
- Service owner rất khó xác định vì dự án cũ đã kết thúc.

Kế hoạch decommission an toàn gồm inventory consumers, redirect/deprecation timeline, dữ liệu retention/export, message/topic cleanup, alert/pager removal, resource and secret revoke, billing cleanup và ghi nhận lifecycle. Không delete DB hoặc topic khi chưa xác minh trách nhiệm dữ liệu.

**Giảm số lượng deployables** có thể là biện pháp tổ chức giúp một nhóm quản lý portfolio tốt hơn mà không giảm tính module hóa logic.

## 41. Multi-team contribution và inner-source

Một service có primary owner nhưng vẫn nhận đóng góp từ nhiều nhóm:

- Publish contribution guide, API contract và test commands.
- CODEOWNERS yêu cầu review với owner ở file rủi ro.
- Consumer team có thể gửi PR thay đổi client/test hoặc đề xuất API.
- Owner kiểm soát release, compatibility và rollback.
- Quy định ai chịu trách nhiệm xử lý regression do một PR từ team khác.
- Hạn chế quyền production thay đổi trực tiếp ngoài policy.
- Không chờ approval vô thời hạn; có review SLA/internal support expectations.
- Những thay đổi lớn có ADR và migration plan.
- Service stewardship có thể luân phiên nhưng ownership vẫn rõ.

Nếu một platform library được mọi nhóm dùng, cần maintenance capacity và change policy giống như một internal product, không thể chỉ gọi nó là “shared” rồi không ai dành thời gian nâng cấp.

## 42. Multi-tenant ownership và dữ liệu theo vùng

Một team có thể quản lý cùng service ở nhiều region/tenant, kéo theo các câu hỏi:

- Region nào cần SLO/DR riêng?
- Có data residency/legal requirements không?
- On-call timezone/follow-the-sun có được hỗ trợ?
- Tenant lớn có tác động tới tenant nhỏ qua queue/DB pool không?
- Traffic routing/failover có một owner duy nhất?
- Deployment rollout/canary có phân vùng theo tenant không?
- DB backup/recovery và secret replication đã được thử?
- External provider có cho phép callback từ từng region?

Một single owner team vẫn có thể sở hữu toàn service multi-region, nhưng cần hệ quan sát và runbook đủ chi tiết. Khi follow-the-sun, nhiều nhóm địa lý có thể luân phiên **thực thi on-call** trong khi **accountable engineering owner** vẫn được xác định; phải ghi rõ escalation khi service SME không ở cùng múi giờ.

## 43. Capacity, cost và error budget theo nhóm

Một portfolio review có thể dùng bảng:

| Service | Tier | Journey impact | p95 / success SLI | On-call pages | Cost trend | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| order-service | Critical | Checkout write | Theo SLO đã định | Cao nếu DB issue | Tăng | Fix pool waits |
| cart-service | Important | Add-to-cart | Theo SLO đã định | Thấp | Ổn định | Maintenance |
| pricing-service | Critical | Checkout pricing | Theo SLO đã định | Vừa | Tăng cache | Audit miss storm |
| order-events-worker | Critical | Confirmation/reconciliation | Message age & DLQ | Cao khi broker outage | Ổn định | Replay drill |
| checkout-admin-api | Internal | Operations workflow | Theo giờ hỗ trợ | Thấp | Thấp | Review auth |

Số liệu trên là khung, không phải trạng thái hệ thống thật. Chỉ số p95/success phải đo theo population và cửa sổ rõ; không suy p95 của user journey bằng cách cộng p95 service.

Nhóm nên nhìn cả **error budget burn và cost/engineering time**. Nếu một service tiêu thụ phần lớn page và thời gian triage, ưu tiên xử lý cause hơn là giao thêm feature cho steward của service đó.

## 44. Mô hình review định kỳ để tránh ownership drift

Một nhịp review ngắn mỗi tháng/quý tùy mức độ thay đổi:

**Service portfolio health**
- Service mới, deprecated hoặc không còn traffic.
- Tier/SLO có còn phản ánh tác động người dùng?
- Missing on-call routing/runbook/backup/DR check.
- Critical vulnerabilities và runtime EOL.
- Incident/alert volume và repeat root causes.
- Cost growth, capacity và unknown owners.

**Team cognitive load**
- Service mới có làm tăng stack diversity?
- Đã có người backup cho những service critical?
- Người trực có thực hiện được rollback/drill không?
- Tỷ lệ thời gian dành cho toil và technical debt?
- Có những phụ thuộc chờ platform quá lâu?
- Có thể chuẩn hóa tooling hay giảm deployables?

**Cross-team contracts**
- Active consumers và những API/event versions đang được dùng.
- Deprecation windows và compatibility matrix.
- Ownership của data stewardship và provider integrations.
- Open change requests không có accountable decision-maker.

Output của review là **action items có owner, hạn và acceptance criteria**, không chỉ một slide liệt kê service.

## 45. Ví dụ ma trận phân công một nhóm sáu người

Giả định Checkout Team có sáu kỹ sư E1–E6, quản lý bốn dịch vụ Tier 0/1 và hai service nội bộ.

**Mô hình đề xuất:**

- Một team-level primary/secondary on-call rotation theo policy.
- Mỗi service Tier 0/1 có steward + backup, không bắt một người duy nhất biết mọi vấn đề.
- Những dự án cross-service có một feature/change lead và reviewer cho mỗi service impacted.
- Một người phụ trách portfolio reliability improvements trong một giai đoạn, luân phiên để tránh vai trò vĩnh viễn.
- Senior/manager chịu trách nhiệm capacity và priority conflicts, không trực tiếp làm bottleneck mọi PR.
- Platform/Data/Security là supporting teams có contract/escalation.
- Service catalog cập nhật tự động hoặc có ownership review định kỳ.

Ví dụ:

~~~text
Team Checkout
  ├─ Mission: hoàn tất hành trình checkout an toàn
  ├─ On-call: E1 primary / E2 secondary (theo ca ví dụ)
  ├─ Order: E3 steward / E4 backup
  ├─ Pricing: E4 steward / E5 backup
  ├─ Cart: E5 steward / E6 backup
  ├─ Events: E6 steward / E3 backup
  ├─ Admin API / Orchestrator: theo phân công sprint
  └─ SLO owner: team, technical lead review
```

Các E1–E6 chỉ minh họa vai trò, không phải tên người thật. Lịch trực phải dựa vào policy lao động, timezone, mức độ critical và coverage thực, không mặc định sáu người đủ cho mọi mức 24/7 toàn cầu.

**Điểm cần tránh:** E3 chịu toàn bộ Order incident vì là steward, dù không đang on-call. Primary vẫn nhận và triage; escalation tới E3 chỉ khi cần kiến thức chuyên sâu và đúng chính sách, với backup để không phụ thuộc một người.

## 46. Bộ nguyên tắc ownership tối thiểu

Một nhóm nhiều service có thể áp dụng những quy tắc sau:

1. Mỗi service production có đúng một primary accountable team và ít nhất một con đường escalation rõ.
2. Team-level on-call nhận page theo SLO/rủi ro; không phụ thuộc vào tác giả code.
3. Mỗi service có catalog entry, runbook, dashboards, contract và lifecycle state.
4. Dữ liệu, event, API và secrets có owner cụ thể, không chỉ “shared”.
5. SLO hành trình và SLO service được phân biệt, cùng có người phối hợp khi lỗi xuyên nhóm.
6. Thay đổi breaking phải có compatibility plan và consumer communication.
7. Production release, rollback và high-risk operations có quyền/phê duyệt rõ.
8. Stewardship có backup và được luân chuyển; kiến thức được tài liệu hóa.
9. Alert và operational toil nằm trong backlog của nhóm.
10. Platform cung cấp golden paths để giảm cognitive load, không nuốt toàn bộ application ownership.
11. Ownership transfer bao gồm Pager, IAM, data, CI, docs và cost, không chỉ repository.
12. Portfolio được review để gộp, tách, chuẩn hóa hoặc retire service theo bằng chứng.

## 47. Checklist khi thêm service mới vào portfolio

- [ ] Service có bounded context/capability và lý do tách deployment rõ.
- [ ] Primary accountable team được chỉ định trong catalog.
- [ ] Product owner/journey impact và stakeholder được ghi nhận.
- [ ] Code repository, CODEOWNERS, CI/CD và artifact versioning hoạt động.
- [ ] API/event contracts có version và compatibility tests.
- [ ] Database/schema/topic/queue, data classification và retention có owner.
- [ ] Service identity/secret/IAM theo least privilege.
- [ ] SLI/SLO/tier phù hợp nghiệp vụ, alert routing đến rotation.
- [ ] Dashboard, logs/traces, incident runbook và escalation path mở được.
- [ ] Có rollback strategy, migrations và DR objectives khi cần.
- [ ] Test local/integration/contract và triển khai môi trường thử được.
- [ ] Steward + backup biết build, deploy, triage và rollback.
- [ ] Ước lượng on-call load, cost và capacity, có budget để duy trì.
- [ ] Dependency graph với upstream/downstream owners được cập nhật.
- [ ] Security/performance/capacity concerns được review trước production.
- [ ] Không tạo một service mà nhóm không còn khả năng duy trì dài hạn.

## 48. Checklist vận hành định kỳ khi một nhóm có nhiều service

- [ ] Catalog owner không trống hoặc lỗi thời.
- [ ] Mọi service critical route page đúng rotation primary/secondary.
- [ ] Mỗi alert có runbook và một hành động có ích.
- [ ] Cảnh báo có đo tác động người dùng, không chỉ CPU/Pod count.
- [ ] Deploys/migrations có change record và rollback path.
- [ ] Dependency upgrades/security patches được theo dõi.
- [ ] SLO và error budget được review theo service và journey.
- [ ] Data backups/restore/DR drill có evidence và owner.
- [ ] API/event schema evolution không phá consumer active.
- [ ] Có người backup về kiến thức lẫn quyền production cho mỗi service critical.
- [ ] Quá tải toil/on-call được đo và xử lý, không chỉ “chịu khó”.
- [ ] Service cũ không còn dùng có lifecycle/decommission plan.
- [ ] Cross-team provider/support contracts được cập nhật.
- [ ] Cloud spend/capacity có owner và đúng tags.
- [ ] Incident action items có deadline và verification.
- [ ] Portfolio review có quyết định giảm complexity khi cần.

## 49. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| “Ai viết service thì người đó trực mãi” | Bus factor thấp, cá nhân kiệt sức | Team-level ownership, rotation, cross-training |
| Mỗi service thuộc “nhiều team” nhưng không có primary | Alert thất lạc, quyết định chậm | Một accountable owner, support contracts rõ |
| Giao code cho team mới nhưng pager vẫn team cũ | Ownership split lâu dài | Transfer checklist gồm IAM/CI/SLO/on-call |
| Service mới có repo nhưng không runbook/SLO | Khó vận hành, sự cố kéo dài | Production readiness gate |
| Team quản lý quá nhiều stack không liên quan | Cognitive load cao | Standardize/golden path, split hoặc retire |
| SLO chỉ đo mỗi API mà bỏ user journey | Không phát hiện hành trình lỗi | Journey owner và end-to-end SLI |
| Platform bị yêu cầu sửa lỗi business semantics | Trách nhiệm sai, chậm incident | Domain owner chịu business correctness |
| Product team tự quản Kafka cluster không có kỹ năng | Hạ tầng shared mất ổn định | Platform capability, rõ ownership của topics |
| Shared DB không có schema owner | Migration phá dữ liệu chéo | Data contracts, schema ownership |
| Deploy đồng thời mọi service để “cho chắc” | Coupling, rollback khó | Independent releases + compatibility |
| Alert cho mọi Pod restart | Page fatigue | SLO-driven alerts, correlation/dedup |
| Không có backup steward | Nghỉ phép là mất khả năng ứng cứu | Pairing, drills, docs và rotation |
| Không dành thời gian bảo trì | Vulnerability, outages, framework EOL | Portfolio roadmap có reliability capacity |
| Secret dùng chung cả team | Blast radius bảo mật lớn | Per-service workload identity |
| Release version floating latest | Không tái hiện được incident | Pin image/config/contract revision |
| Mọi thay đổi phải mở ticket chờ Platform | Team không tự chủ | Self-service platform + guardrails |
| Tách service theo từng bảng/entity không có nhu cầu | Deployable explosion | Bounded contexts, modular monolith khi phù hợp |
| “Owner = một tên trên wiki” | Không route page hoặc cấp quyền thực | Catalog, IAM, on-call sources đồng bộ |
| Delete dead service không kiểm tra consumers | Data loss, broken integrations | Decommission checklist và deprecation |
| “Phát hiện Payment lỗi rồi đóng incident Checkout” | User vẫn bị ảnh hưởng | Journey accountability đến phục hồi |

## 50. Câu hỏi thường gặp

**Một team có thể sở hữu nhiều microservice không?**

Có. Điều đó phổ biến và có thể hợp lý khi các service thuộc cùng năng lực nghiệp vụ và tổng tải vận hành trong khả năng nhóm. Cần rõ primary accountable team, service metadata, on-call, SLO, data contracts và cơ chế chia sẻ kiến thức.

**Một microservice có thể có nhiều owner không?**

Nhiều nhóm có thể đóng góp hoặc hỗ trợ, nhưng nên có một đầu mối chịu trách nhiệm chính cho quyết định và vận hành. Nếu cần co-ownership chính thức, phải ghi rõ authority, support agreement và escalation để không tạo khoảng trống.

**Có nên chia cho mỗi developer một service riêng?**

Không mặc định. Người có thể là steward trong một giai đoạn, nhưng nhóm phải có khả năng vận hành thay thế. Nếu mỗi service chỉ một người hiểu, nghỉ phép hoặc đổi việc sẽ tạo rủi ro lớn.

**Đội Platform có phải nhận mọi page của mọi service không?**

Không. Platform nhận vấn đề của nền tảng shared mà họ sở hữu. Service owner cần nhận page của business/service SLO và phối hợp với Platform nếu hạ tầng là nguyên nhân.

**Khi một workflow lỗi ở dependency thuộc team khác, ai chịu trách nhiệm?**

Technical owner của dependency chịu trách nhiệm sửa phần họ. Journey/incident owner phải theo dõi tác động toàn hành trình, điều phối và xác minh người dùng phục hồi. Một incident có thể có nhiều action owners nhưng cần IC và primary contact rõ.

**Số lượng service tối đa trên mỗi nhóm là bao nhiêu?**

Không có con số đúng cho mọi đội. Tùy complexity, stack diversity, criticality, số incident, external dependencies, autonomy và khả năng trực. Theo dõi cognitive load, lead time, pages và quality để quyết định khi nào giảm/tách portfolio.

**Có nên tách thêm team khi service count tăng?**

Chỉ khi domain/team boundaries và workload chứng minh cần thiết, nhóm mới có capacity và on-call coverage. Trước đó có thể chuẩn hóa tooling, giảm alert noise, gộp service quá nhỏ hoặc retire service ít giá trị.

**Khi team đang sở hữu Order, có nên truy cập trực tiếp Pricing DB vì cùng team không?**

Nên ưu tiên giữ data ownership và interface rõ ngay cả khi cùng nhóm. Nếu một database shared có lý do kỹ thuật, phải ghi rõ schema ownership, migration coordination và coupling; không mặc nhiên cross-service DB access là an toàn.

**CODEOWNERS có thay service catalog được không?**

Không. CODEOWNERS giúp code review. Catalog cần owner, SLO, pager, deploy, runbook, data, dependencies và lifecycle; IAM/CI phải thực sự hiện thực quyền.

**Làm sao để một người trực không bị quá tải bởi 10 service?**

Giảm page nhiễu, runbook chuẩn, alert theo SLO, dedup incidents, golden paths, chia sẻ kiến thức, secondary rotation và tách các service có specialist requirements. Nếu vẫn quá tải, giảm số service/điều chỉnh đội ngũ.

**Khi chuyển service sang team khác, mốc nào mới được coi là bàn giao xong?**

Khi team nhận có quyền và năng lực build/deploy/rollback, nhận pager, hiểu SLO/incident runbooks, quản lý data/secret/backup và được ghi trong catalog. Chuyển repo mà pager vẫn ở team cũ chưa phải bàn giao đầy đủ.

**Nếu service không còn nhiều feature mới, có thể bỏ owner không?**

Không khi service vẫn chạy production hoặc lưu dữ liệu cần trách nhiệm. Bảo trì security, schema, backup, cost, on-call và decommission vẫn cần owner. Nếu không còn giá trị, lập kế hoạch ngừng an toàn.

**Có cần làm một on-call rotation riêng cho mỗi service không?**

Không nhất thiết. Team-level rotation có thể phù hợp khi có nhiều service cùng domain. Nếu một subset có requirement khác biệt (ví dụ payment ledger 24/7), cân nhắc tier và chuyên môn theo chính sách thay vì sao chép cùng một rota cho mọi service.

**SLO của service và SLO của sản phẩm có phải một không?**

Không. User journey có thể đi qua nhiều service, UI và dependency. Service owner tối ưu phạm vi mình, còn journey owner đo và điều phối outcome cuối. Cần liên kết hai cấp để không có API xanh mà checkout vẫn thất bại.

**Nên đánh giá ownership thế nào trong tổ chức?**

Không chỉ kiểm tra bảng tên team. Hãy diễn tập: người trực được page đúng không, mở dashboard/runbook được không, deploy/rollback được không, hiểu dữ liệu và dependency không, có backup knowledge không, data/contract/SLO có bằng chứng không.

---

**Nguyên lý ghi nhớ:** *Một nhóm có thể sở hữu nhiều microservice khi quyền quyết định, trách nhiệm về người dùng và dữ liệu, on-call, contract và lifecycle được ghi rõ; đồng thời nhóm có đủ capacity và cơ chế giảm cognitive load để thực hiện trách nhiệm đó. Ownership không nằm ở người đã viết service hay vị trí repository, mà ở khả năng thay đổi, bảo vệ và khôi phục dịch vụ một cách liên tục và có người chịu trách nhiệm.*
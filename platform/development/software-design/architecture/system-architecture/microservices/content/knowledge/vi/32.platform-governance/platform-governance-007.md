# Phân biệt năng lực nền tảng với logic nghiệp vụ dùng chung

Trong kiến trúc microservices, các đội thường muốn tái sử dụng những thứ “giống nhau” giữa các dịch vụ. Logging, tracing, quản lý secret, CI/CD, định tuyến request, xác minh danh tính, kiểm thử hợp đồng, gửi sự kiện và quy tắc tính phí đều có thể xuất hiện trong nhiều repository. Tuy nhiên, **xuất hiện ở nhiều nơi không đồng nghĩa với việc thuộc cùng một nền tảng**. Nếu đặt mọi thứ “dùng chung” vào một platform hoặc common library, tổ chức rất dễ tạo thành một monolith phân tán: một thay đổi của Order hoặc Payment buộc nhiều service phải cập nhật đồng thời, đội nền tảng trở thành nút cổ chai và trách nhiệm đúng/sai của nghiệp vụ bị mờ.

Một ranh giới cơ bản:

- **Năng lực nền tảng (platform capability):** khả năng kỹ thuật tự phục vụ, có hợp đồng và mức dịch vụ rõ, giúp nhiều đội xây dựng, triển khai và vận hành phần mềm với ít công việc lặp lại hơn. Ví dụ: tạo service mới, pipeline build, secrets delivery, quan sát hệ thống, broker provisioning, policy enforcement, developer portal.
- **Logic nghiệp vụ (domain/business logic):** các quy tắc, trạng thái và quyết định thể hiện cách một doanh nghiệp tạo giá trị hoặc thực hiện cam kết với người dùng. Ví dụ: điều kiện được hoàn tiền, cách phân bổ tồn kho, công thức tính giá, điều kiện duyệt hạn mức, quyền phê duyệt đơn hàng.
- **Logic nghiệp vụ dùng chung:** quy tắc thực sự được dùng ở nhiều luồng sản phẩm, nhưng vẫn có **người sở hữu trong miền nghiệp vụ**. Nó có thể được cung cấp qua một domain service hoặc contract có phiên bản, chứ không mặc nhiên thuộc quyền quyết định của Platform Team.

Câu hỏi cốt lõi không phải “bao nhiêu service đang dùng đoạn code này?”, mà là: **Ai có thẩm quyền quyết định ý nghĩa của nó, ai chịu trách nhiệm khi hành vi sai, nó cần thay đổi theo nhịp kỹ thuật hay nhịp nghiệp vụ, và consumer có được nâng cấp độc lập không?**

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt platform capability, technical shared library, domain shared capability và business rule.
2. Phân loại một thành phần bằng các tiêu chí: thẩm quyền quyết định, phạm vi thay đổi, dữ liệu sở hữu, tương thích, mức độ tự phục vụ và failure mode.
3. Giải thích vì sao đẩy business rules vào common-core hoặc platform starter làm tăng coupling và làm giảm khả năng triển khai độc lập.
4. Thiết kế ranh giới giữa authentication, authorization enforcement, business authorization, feature flags, event infrastructure và domain events.
5. Lựa chọn giữa thư viện dùng chung, dịch vụ nghiệp vụ có API, dữ liệu tham chiếu versioned, contract/schema và quy tắc nằm riêng trong mỗi bounded context.
6. Xây dựng platform “như sản phẩm nội bộ” có golden path, self-service, API, SLO, owner, compatibility và kênh hỗ trợ.
7. Thiết kế cơ chế quản trị chung mà không biến Platform Team thành người quyết định logic giá, kho, thanh toán và quy trình duyệt.
8. Lập phương án tách một shared module lớn để các service nâng cấp theo lịch riêng.

## 2. Bốn lớp thường bị trộn lẫn

Hãy xem sơ đồ khái niệm:

~~~text
                       SẢN PHẨM / NGƯỜI DÙNG
                                |
                  Hành trình, cam kết và chính sách
                                |
           +--------------------+-------------------+
           |                                        |
    DOMAIN / PRODUCT TEAMS                     PLATFORM TEAM
           |                                        |
    Order, Payment, Inventory              CI/CD, runtime, observability
    Pricing, Fraud, Loyalty                secrets, broker provisioning
           |                                        |
       Domain contracts                  Platform APIs / golden paths
           |                                        |
           +--------------------+-------------------+
                                |
                       HẠ TẦNG / RUNTIME
~~~

Trong thực tế nên phân biệt ít nhất bốn lớp:

| Lớp | Câu hỏi trách nhiệm | Ví dụ |
|---|---|---|
| Hạ tầng cơ sở | Có tài nguyên an toàn, hoạt động và được vận hành không? | Compute, network, storage, managed database |
| Năng lực nền tảng | Các đội có thể tiêu thụ hạ tầng/chuẩn kỹ thuật qua giao diện nhất quán và tự phục vụ không? | Deploy pipeline, service catalog, telemetry SDK, secret broker |
| Năng lực miền nghiệp vụ dùng chung | Quy tắc hoặc thực thể nghiệp vụ nào cần một nguồn có thẩm quyền chung? | Customer identity profile, pricing decision, loyalty points |
| Ứng dụng/ngữ cảnh nghiệp vụ | Hành trình này áp dụng quy tắc như thế nào? | Order checkout, cancel flow, payment capture |

Các lớp có thể sử dụng lẫn nhau, nhưng **quyền sở hữu ý nghĩa** không nên thay đổi chỉ vì có code hoặc dữ liệu dùng chung. Ví dụ Platform Team cung cấp khả năng lưu secret; Payment Team quyết định secret nào dùng để gọi payment provider, rotation window và khi nào credential cũ hết hiệu lực trong luồng thanh toán.

## 3. Nền tảng là một sản phẩm nội bộ, không phải “thư mục common”

Platform capability có khách hàng trực tiếp là **các đội phát triển và vận hành service**. Giá trị chính của nó là giảm gánh nặng nhận thức và thao tác lặp lại để product team tập trung vào nghiệp vụ. Một năng lực nền tảng tốt thường có:

- **Giao diện tự phục vụ:** API, CLI, template, portal hoặc khai báo cấu hình được hỗ trợ.
- **Owner rõ:** đội có trách nhiệm về tính ổn định, an toàn, thay đổi và hỗ trợ.
- **Hợp đồng:** mô tả đầu vào, đầu ra, giới hạn, lỗi, quyền và phiên bản.
- **SLO và support model:** mức khả dụng, thời gian provisioning, incident escalation.
- **Golden path:** đường mặc định dễ dùng và an toàn; ngoại lệ được xử lý có kiểm soát.
- **Ranh giới kỹ thuật:** không cần hiểu chi tiết cách tính đơn hàng để cấp một namespace.
- **Quản trị vòng đời:** deprecation, compatibility, cost, quota và documentation.

Nếu Platform Team chỉ nhận ticket “hãy sửa file YAML của service A”, “hãy deploy service B”, “hãy tạo topic C” bằng thao tác thủ công, đó chưa phải self-service tốt dù công việc được gọi là “platform”.

Ngược lại, một thư viện Java chứa hàm tính khuyến mãi được 12 service dùng không biến hàm đó thành platform. Nó vẫn là **một domain policy có owner và rủi ro nghiệp vụ**.

## 4. Shared technical primitive khác shared business decision

Xét hai đoạn yêu cầu:

**Yêu cầu 1:** “Mọi request cần correlation ID để trace qua các microservice.”

Đây là nhu cầu kỹ thuật xuyên service. Platform có thể cung cấp SDK/agent, quy tắc propagation và collector. Order Team quyết định span nào biểu diễn thao tác nghiệp vụ của Order, nhưng không cần tự xây collector mới.

**Yêu cầu 2:** “Mọi đơn có voucher GOLD được giảm 12%, trừ sản phẩm thuộc campaign BLACKOUT.”

Đây là quyết định nghiệp vụ. Nó có thể được sử dụng bởi Checkout, Order và Billing nhưng cần được sở hữu bởi Pricing/Promotion domain. Platform không nên tự nhận quyền thay đổi điều kiện chiết khấu vì nó xuất hiện ở nhiều service.

Một phép thử nhanh:

> Nếu thay đổi kết quả mà một khách hàng phải trả tiền, được xét duyệt, được hoàn tiền, nhận hàng hoặc bị từ chối, thì đây thường là một quyết định nghiệp vụ, dù implementation là hàm nhỏ trong thư viện.

Vẫn có trường hợp platform cung cấp **công cụ thực thi** business rules (rule engine, workflow engine, policy evaluator). Công cụ đó thuộc nền tảng; **nội dung rule, version, phê duyệt và trách nhiệm đúng/sai** vẫn thuộc miền nghiệp vụ.

## 5. Ma trận phân loại những thành phần thường gặp

| Thành phần | Phần thuộc platform | Phần thuộc domain/service owner |
|---|---|---|
| Logging | Collector, format envelope, trace propagation, retention pipeline | Log gì, dữ liệu nào được phép ghi, nghĩa của sự kiện nghiệp vụ |
| Metrics/tracing | SDK, collector, dashboards framework, sampling tooling | SLI, span quan trọng, metric business outcome |
| API Gateway | TLS termination, routing, rate-limit primitives, identity integration | Route behavior, contract API, business error semantics |
| Authentication | Xác minh danh tính, token validation, machine identity | Chính sách quyền sử dụng một nghiệp vụ cụ thể |
| Authorization | Enforcement framework và policy infrastructure | Ai được hoàn tiền, duyệt đơn hoặc xem dữ liệu thuộc domain |
| Feature flag | Flag store, evaluation SDK, rollout controls, audit | Khi nào bật giá/luồng mới, đối tượng nào nhận behavior mới |
| Secrets | Secret manager, delivery, rotation tooling, IAM integration | Credential nào cần, tác động của rotation lên quy trình |
| Message broker | Cluster, topic provisioning, encryption, quota, ACL primitives | Event schema, partition key, retention theo hợp đồng, consumer semantics |
| Database | Cluster provision, backup platform, encryption và engine patching | Schema logic, business invariants, query/migration semantics |
| CI/CD | Template, artifact signing, deployment tooling, policy gates | Release readiness, canary criteria, rollback compatibility |
| Policy-as-code | Engine, rule distribution, audit, enforcement | Ý nghĩa business policy và người phê duyệt thay đổi |
| Pricing | Runtime/hosting nếu platform cung cấp | Công thức giá, promotion precedence, tax/business decisions |
| Payments | Credential plumbing, observability, generic resilience | Capture/refund/idempotency ledger, provider semantics |
| Notification | Message delivery infrastructure chung nếu phù hợp | Nội dung thông báo, trigger, consent, điều kiện gửi |
| Service catalog | Portal, metadata schema, search | Owner, SLO, API, data classification đúng của từng service |

Không phải cột nào cũng yêu cầu hai đội cùng sửa một file. Mô hình tốt là **platform làm phần generic thành API ổn định**, domain quyết định và cấu hình hành vi nghiệp vụ trong giới hạn đã hỗ trợ.

## 6. Câu hỏi quyết định ownership

Khi có một thành phần “dùng chung”, hãy đi qua các câu hỏi theo thứ tự:

1. **Ý nghĩa:** đây là cơ chế kỹ thuật hay quyết định nghiệp vụ?
2. **Nguồn có thẩm quyền:** ai được phép quyết định nó đúng hay sai?
3. **Dữ liệu:** nó sở hữu dữ liệu nghiệp vụ, hay chỉ vận chuyển/lưu trữ dữ liệu cho người khác?
4. **Nhịp thay đổi:** nó thay đổi khi nâng runtime/SDK, hay khi có campaign/sản phẩm/chính sách mới?
5. **Mức khác biệt:** các bounded context có thật sự cần một quy tắc duy nhất không?
6. **Ràng buộc triển khai:** nếu thay đổi thành phần này, bao nhiêu service buộc phải nâng cùng ngày?
7. **Failure behavior:** khi nó lỗi, ai ra quyết định fallback và ai chịu rủi ro?
8. **Độ trưởng thành:** có đủ người duy trì hợp đồng, test, versioning và support window không?
9. **Trải nghiệm tiêu thụ:** người dùng nội bộ cần API tự phục vụ, một SDK, một dịch vụ có endpoint, hay chỉ tài liệu hướng dẫn?
10. **Bảo mật/pháp lý:** ai có quyền phê duyệt rule và kiểm toán tác động?

Có thể quyết định theo logic:

~~~text
Thành phần có đưa ra quyết định nghiệp vụ không?
    |
    +-- Có -> Domain/Product owner
    |          |
    |          +-- Nhiều context cùng một sự thật?
    |                |
    |                +-- Có -> Domain service/contract/data product
    |                +-- Không -> Giữ rule trong từng context
    |
    +-- Không -> Có tạo năng lực kỹ thuật xuyên nhóm?
                 |
                 +-- Có -> Platform capability hoặc technical library
                 +-- Không -> Implementation nội bộ của service
~~~

Sơ đồ là heuristic, không phải máy phân loại tuyệt đối. Ví dụ một hệ thống identity có cả năng lực hạ tầng (xác thực token) và logic sản phẩm (gói tài khoản được quyền sử dụng tính năng). Cần tách hai phần thay vì đẩy cả identity vào một nhãn duy nhất.

## 7. Bounded context: cùng từ ngữ chưa chắc cùng quy tắc

Trong Domain-Driven Design, một thuật ngữ có thể mang ý nghĩa khác nhau ở các bounded context.

Ví dụ "Customer":

- Billing nhìn Customer qua thông tin thanh toán, công nợ, hóa đơn.
- Support nhìn Customer qua ticket, quyền hỗ trợ, lịch sử khiếu nại.
- Loyalty nhìn Customer qua điểm thưởng và cấp thành viên.
- Identity nhìn User/Principal qua đăng nhập và thông tin xác thực.

Việc tất cả cùng có một trường customerId không đòi một class CustomerEntity chung với mọi field. Một “common-customer-model.jar” thường là điểm bùng nổ phụ thuộc khi mỗi nhóm thêm field hoặc constraint.

Giải pháp là:

- Mỗi bounded context có model nội bộ phù hợp mục đích.
- Một hoặc vài nguồn dữ liệu authoritative được công bố rõ cho những thuộc tính thực sự có chủ.
- Dịch vụ tiêu thụ dùng API, event, read model hoặc contract versioned.
- Data mapping/anti-corruption layer giúp giữ sự độc lập về ý nghĩa.
- Không chia sẻ quyền ghi database xuyên service nếu muốn giữ ownership.

**Tái sử dụng tri thức miền** có thể cần contract và phối hợp product, nhưng không nhất thiết cần chia sẻ entity runtime.

## 8. Khi nào logic nghiệp vụ thực sự cần dùng chung?

Không phải cứ có nhiều consumer là phải tạo một domain service mới. Có ít nhất bốn trường hợp:

**Trường hợp A — Một nguồn quyết định duy nhất.** Pricing phải tính giá chính thức để người mua, Order và Billing không mâu thuẫn. Pricing Service có thể là nguồn authoritative; các consumer gọi API hoặc nhận quote đã ký/định danh theo contract.

**Trường hợp B — Quy tắc thống nhất nhưng offline/local evaluation được phép.** Một policy tính thuế hoặc phân loại sản phẩm có thể được xuất bản thành rule package/snapshot versioned, có owner nghiệp vụ, effective date và compatibility. Đây là artifact domain; platform chỉ cung cấp engine/distribution.

**Trường hợp C — Tên giống nhưng quy tắc khác.** Payment và Order có hai phép kiểm tra “valid status”, song lifecycle khác nhau. Cố tạo một ValidStatus utility chung dễ làm mất ranh giới; để mỗi context tự sở hữu rule.

**Trường hợp D — Mã kỹ thuật trùng lặp nhỏ.** Hai service cùng có helper parse UUID hoặc retry-after parser. Có thể dùng technical library ổn định nếu chi phí duy trì thấp; không cần dựng một service RPC chỉ để thay một function.

Khi phân tích, cần xác định **mức nhất quán cần có**: một quyết định giá được quote tại thời điểm checkout có thể cần được lưu lại cùng order để audit; không nên tính lại dựa trên campaign mới khi xuất hóa đơn mà không có hợp đồng.

## 9. Quyết định giữa library, API và event

Ba cách tái sử dụng có trade-off khác nhau:

| Cách | Phù hợp | Ưu điểm | Rủi ro |
|---|---|---|---|
| Shared library | Hàm kỹ thuật nhỏ, ổn định; rule domain có version nếu thật sự cần local | Không thêm network hop, latency thấp | Coupling build/runtime, nhiều bản logic cùng tồn tại |
| Domain service/API | Một nguồn quyết định, trạng thái và quyền sở hữu rõ | Thay logic tập trung, audit một nơi | Dependency runtime, latency, availability, throughput |
| Event/contract | Phát thông tin thay đổi để consumer xây read model | Loose coupling theo thời gian, phản ứng bất đồng bộ | Eventual consistency, duplicate, ordering, schema evolution |
| Rule package/data product | Quy tắc cần dùng offline, phân phối theo snapshot version | Không gọi API mỗi lần, có effective date | Độ trễ update, version skew, trách nhiệm giải thích decision |
| Code trong từng service | Quy tắc khác nhau theo context | Độc lập hoàn toàn | Lặp mã có thể nhiều, nguy cơ drift nếu thật ra là cùng rule |

Ví dụ: tính giá chính thức có thể do Pricing cung cấp Quote với quoteId, version, expiresAt và monetary breakdown. Checkout lưu quote đã duyệt, Order không phải lấy phiên bản package Pricing mới nhất để tính lại. Cách này ưu tiên **một hợp đồng quyết định** hơn là chia sẻ toàn bộ implementation.

### Không nâng thư viện và API cùng lúc vì thuận tiện

Nếu shared rule library được nâng ở 20 service cùng ngày, rollback khó phân biệt tác động. Có thể để các service pin version trong support window, dùng compatibility matrix và release độc lập. Nếu nghiệp vụ bắt buộc mọi consumer dùng rule mới cùng thời điểm vì pháp lý, đó là **business migration có kế hoạch**, không phải thói quen của infrastructure platform.

## 10. Ví dụ: Authentication không đồng nghĩa Authorization nghiệp vụ

Một platform identity service có thể:

- Cấp/kiểm tra token và chứng minh người gọi là ai.
- Cung cấp workload identity, key rotation, JWKS, certificate và session primitives.
- Chuẩn hóa cách dịch vụ kiểm tra chữ ký, expiry, issuer, audience.
- Ghi audit về việc cấp danh tính và kiểm soát secret.

Nhưng việc “người dùng này được hoàn tiền cho order O17 không?” thuộc miền Order/Payment và chính sách sản phẩm tương ứng.

~~~text
Caller -> Gateway/Identity capability
                 |
                 v
       Authenticated principal
                 |
                 v
       Refund API (Payment domain)
                 |
                 v
  Kiểm tra order/ownership/status/amount
                 |
                 v
         Allow / deny / review
~~~

Các bước cần phân biệt:

1. **Authentication:** kiểm tra danh tính/kênh/certificate.
2. **Technical authorization:** có quyền gọi resource/service này theo IAM/scope chung?
3. **Business authorization:** trạng thái đơn, số tiền, vai trò trong tổ chức, giới hạn hoàn tiền và rule compliance có cho phép thao tác không?
4. **Audit:** lưu vì sao quyết định được đưa ra, ở version policy nào, ai yêu cầu.

Platform có thể cung cấp policy evaluation engine và token scopes; **người sở hữu refund business policy** phải có quyền định nghĩa và kiểm tra rule. Không đưa bảng RefundLimitByCustomerTier vào common-auth-starter chỉ vì cần authorization.

## 11. Ví dụ: API Gateway và business orchestration

Một gateway thường làm tốt:

- TLS termination và routing.
- Authentication integration và giới hạn request theo policy.
- Request ID, tracing propagation, access logs.
- Traffic shaping, canary routing và backend health ở mức network.
- Quota có tính kỹ thuật, size limit và circuit protection.

Gateway không nên trở thành nơi thực hiện toàn bộ business orchestration:

~~~text
Anti-pattern:
Gateway:
  Nếu khách VIP -> kiểm tra tồn kho
  -> tính voucher
  -> chọn payment provider
  -> tạo đơn -> gửi email
~~~

Khi đó Gateway release gắn với quy tắc nghiệp vụ của nhiều nhóm, khó test và trở thành shared runtime failure point.

Một mô hình phù hợp hơn:

~~~text
Gateway [routing/auth primitives]
             |
             v
Checkout API / BFF [product orchestration]
             |
       +-----+------+
       v            v
   Inventory      Payment
  [domain]        [domain]
~~~

BFF (Backend for Frontend) hoặc orchestration service có thể thuộc product team nếu nó quyết định luồng người dùng. Gateway vẫn cung cấp “đường vào an toàn” dùng chung.

## 12. Ví dụ: Event broker và event contract

Platform Team có thể vận hành broker với:

- Provision topic/queue và quota.
- TLS, encryption, ACL, network policy.
- Cluster replication, backup/DR, capacity và failover.
- Tooling cho retry/DLQ, monitoring và schema registry.
- Guidelines về partitioning, retention và producer/consumer compatibility.

Nhưng domain producer phải quyết định:

- Event nào là sự thật nghiệp vụ có thể phát công khai.
- Ý nghĩa của OrderConfirmed, PaymentCaptured hoặc InventoryReserved.
- Schema, optional fields, versioning, deprecation và idempotency key.
- Ordering theo aggregate nào thực sự cần.
- Retention tối thiểu theo hợp đồng người tiêu thụ và data policy.
- Khi nào phát, payload chứa dữ liệu nhạy cảm nào.

Ví dụ:

~~~text
Platform:
  Tạo topic payment-events, cấu hình quota và ACL.

Payment Team:
  Định nghĩa PaymentCaptured.v2 và những bất biến
  như providerChargeId, amount, currency, paymentAttemptId.

Order Team:
  Consumer contract + xử lý duplicate/out-of-order.
~~~

Nếu một thay đổi schema nghiệp vụ phải do Platform Team approve từng field dù không ảnh hưởng hạ tầng hay guardrails, platform trở thành nút cổ chai. Nếu Platform Team không áp rule security/retention nào, owner có thể vô tình làm hạ tầng mất an toàn. Hợp đồng hai phía giải quyết được cả hai vấn đề.

## 13. Ví dụ: Database platform và data ownership

Một đội Database Platform có thể sở hữu:

- Database-as-a-service provisioning.
- Engine patching, storage, backup/PITR, monitoring cluster.
- Credential/role lifecycle và encryption.
- Guardrails cho connection pool, query limits, network.
- Công cụ migration, policy về schema và operational support.

Nhóm Order vẫn sở hữu:

- Ý nghĩa bảng orders và trạng thái của đơn.
- Unique business keys, transactional invariant.
- Schema migrations của Order trong giới hạn công cụ.
- Chất lượng query, index logic, retention thuộc sản phẩm.
- Quy tắc sửa trạng thái, idempotency và reconciliation.

**Managed database không đồng nghĩa dữ liệu thuộc platform.** Tương tự, Platform sở hữu object storage không có nghĩa được thay business rule xác định file nào hợp lệ cho một hợp đồng.

### Tránh shared database vì tiện

~~~text
Order service  ----\
Payment service ----> shared commerce database
Inventory service -/
~~~

Nếu mỗi service trực tiếp ghi bảng của nhau, một migration có thể buộc tất cả deploy cùng ngày, mọi nhóm có quyền quá rộng và incident khó xác định owner. Có thể cùng dùng một database server/cluster về vật lý nhưng **schema/permission và owner logic** nên tách rõ theo bounded context; tránh shared writes khi có thể.

## 14. Ví dụ: Feature flags

Platform có thể cung cấp:

- Flag store và evaluation SDK.
- Percentage rollout, targeting primitives, audit history.
- Cache, fallback semantics và propagation.
- Kill-switch/flag lifecycle, permissions và dashboard.
- SLO của flag evaluation và incident escalation.

Domain team quyết định:

- Bật thử nghiệm giá mới ở cohort nào, với chấp thuận product nào.
- Quy tắc eligibility của campaign là gì.
- Điều gì xảy ra nếu flag service không truy cập được.
- Những trạng thái dữ liệu hoặc side effect nào đã phát sinh.
- Khi nào xóa flag và nợ kỹ thuật tương ứng.

Ví dụ Platform cung cấp khả năng evaluate boolean, nhưng một flag "allowRefundWithoutReview" không nên tự động được Platform Team bật cho toàn công ty chỉ vì một rollout template.

**Không gộp flag với quyền truy cập bảo mật.** Nếu một tính năng có yêu cầu authorization, backend vẫn phải kiểm tra business permission; tắt/ẩn nút bằng flag ở frontend không phải là biện pháp kiểm soát quyền đáng tin.

## 15. Ví dụ: Policy engine và policy content

Một OPA-like engine hoặc policy decision point có thể được Platform Team triển khai như một năng lực kỹ thuật:

~~~text
Input attributes + policy bundle -> Evaluate -> Allow/Deny/Metadata
~~~

Nhưng nội dung policy phải có source và owner:

| Policy | Thường thuộc |
|---|---|
| Không chạy container privileged trong namespace production | Platform/Security guardrail |
| Artifact phải có chữ ký đáng tin trước khi deploy | Platform/Security |
| API service-to-service chỉ cho phép identity nhất định | Owner service phối hợp Security |
| Đơn có tổng tiền lớn cần kiểm tra gian lận bổ sung | Fraud/Payment domain |
| Đơn trả hàng quá 30 ngày không được hoàn tiền | Return/Refund domain |
| Quản lý dữ liệu nhạy cảm theo retention bắt buộc | Data governance/Security cùng domain data owner |

Một policy engine có thể chạy mọi loại rule; điều đó **không làm tất cả rule thuộc một người sở hữu**. Nội dung rule cần version, audit, test với case nghiệp vụ, quyền phê duyệt và khả năng rollback riêng.

## 16. Ví dụ: Workflow engine

Platform Team có thể cung cấp workflow orchestration infrastructure: queue, timer, persistence, retry engine và UI quan sát. Nhưng workflow "duyệt yêu cầu vay", "xác nhận thanh toán", "hoàn đơn" thuộc đội sản phẩm tương ứng.

Nếu một workflow dùng chung giữa nhiều domain:

- Tách **engine/runtime** khỏi **workflow definition**.
- Ghi owner và phiên bản cho workflow.
- Xác định state transition và business invariants.
- Xác định backward compatibility cho các workflow đang chạy dở.
- Không migrate state cũ một cách mù khi thay definition.
- Có cơ chế kiểm tra tác động tới external side effect.

Một thay đổi retry framework do Platform phát hành không được âm thầm khiến payment capture có thêm nhiều lần thử mà không bảo vệ idempotency.

## 17. Logging/observability: generic envelope và semantic ownership

Một platform telemetry có thể thống nhất thông tin kỹ thuật:

~~~json
{
  "traceId": "abc123",
  "spanId": "def456",
  "service": "payment-service",
  "environment": "production",
  "severity": "INFO",
  "eventName": "payment.capture.completed",
  "attributes": {
    "providerStatus": "CAPTURED",
    "currency": "VND"
  }
}
~~~

Platform sở hữu khả năng thu thập/giữ/tra cứu dữ liệu và quy tắc bảo mật. Payment Team chịu trách nhiệm tên event biểu diễn nghiệp vụ gì, điều kiện phát event, dữ liệu nào được phép log, và cách SLI correctness được tính.

Sai lầm phổ biến là tạo một shared enum BusinessEventType chứa mọi event của Order, Payment, Inventory. Khi một domain đổi event, toàn bộ library cần phát hành; team khác có thể kéo version mới chỉ vì cùng import enum. Tốt hơn là schema/event catalog có owner riêng từng domain và một envelope kỹ thuật ổn định ở platform.

### Tránh metric cardinality không kiểm soát

Platform cung cấp SDK/guardrail về metric labels và sampling, còn từng service quyết định metric nghiệp vụ nào cần đo. Không nên để productId/orderId thẳng vào Prometheus label cho mọi request chỉ vì platform SDK có hỗ trợ thêm attributes.

## 18. Retry, timeout và circuit breaker: chung cơ chế, riêng chính sách

Một resilience library có thể cung cấp:

- Backoff/jitter utility.
- Deadline propagation.
- Circuit breaker implementation.
- Token bucket và concurrency limiter.
- Metrics, trace integration và config schema.

Nhưng **retry có hợp lệ không và retry bao nhiêu lần** phụ thuộc nghiệp vụ.

| Thao tác | Phải xem xét |
|---|---|
| GET catalog | Có thể retry khi idempotent, có giới hạn deadline |
| Create order | Cần idempotency key, tránh tạo đơn trùng |
| Capture payment | Unknown outcome phải query/reconcile; không tạo charge mới mù |
| Send email | Có thể retry nhưng cần delivery ledger/dedup theo mức contract |
| Reserve inventory | Phải giữ invariant, xử lý token/transaction an toàn |

Nếu Platform Team đổi default "mọi POST retry 3 lần" cho một starter dùng toàn công ty, đó là thay đổi hành vi nghiệp vụ rất nguy hiểm. Mô hình tốt: platform cung cấp primitive, **service owner chủ động chọn policy** theo contract và kiểm thử lỗi timeout/retry.

## 19. Business capability thật sự xuyên nhiều service

Giả sử Pricing đưa ra giá có hiệu lực cho một giỏ hàng. Checkout, Order, Billing và Analytics đều cần kết quả này.

Một giải pháp sai:

~~~text
common-business.jar
  PriceRule
  PromotionRule
  CurrencyRule
  CustomerTierRule
  RefundRule

Mọi service cùng nâng bản khi thay một campaign.
~~~

Các service sẽ khó biết bản rule nào được áp tại thời điểm nào; cùng một class có thể sinh kết quả khác giữa các thời điểm deploy.

Một thiết kế có thẩm quyền:

~~~text
                     Pricing Team
                         |
          Pricing Service / Rule Release
                         |
                   Quote API v1
                         |
           +-------------+-------------+
           v             v             v
        Checkout        Order         Billing
           |             |             |
       quoteId        priceSnap     invoiceSnap
           |             |             |
           +--- lưu version/effective date ---+
~~~

Dữ liệu mẫu:

~~~json
{
  "quoteId": "q-1024",
  "currency": "VND",
  "total": 250000,
  "policyVersion": "pricing-rules-2026-11",
  "expiresAt": "2026-11-12T10:30:00Z"
}
~~~

Đây là một model minh họa, không đủ thành đặc tả tính thuế/giá chính thức. Bản chất là **source of truth và audit trail** cho một quyết định có giá trị nghiệp vụ, thay vì phát tán quy tắc vào mọi service rồi hy vọng tất cả luôn nâng đúng lúc.

### Nếu dịch vụ Pricing lỗi?

Cần hợp đồng rõ: Checkout có thể dùng quote còn hiệu lực không? Có cho phép đặt đơn với giá lưu trước không? Khi nào phải từ chối? Những quyết định này thuộc Pricing/Checkout/Product, không thể để generic platform cache tự quyết.

## 20. Những quy tắc nên nằm cục bộ trong mỗi bounded context

Đôi khi việc lặp mã không gây nguy hiểm bằng việc đồng bộ ngữ nghĩa sai.

Ví dụ cùng một trường status:

~~~text
OrderStatus:
  CREATED, CONFIRMED, CANCELLED, SHIPPED

PaymentStatus:
  PENDING, AUTHORIZED, CAPTURED, REFUNDED

InventoryReservationStatus:
  REQUESTED, RESERVED, RELEASED, EXPIRED
~~~

Các trạng thái đều có concept "PENDING" hoặc "CANCELLED", nhưng transition và quyền thay đổi rất khác nhau. Không tạo CommonStatus enum với mọi giá trị rồi buộc service dùng chung.

Các nguyên tắc:

1. Mỗi aggregate có invariant riêng và owner cụ thể.
2. Mapping giữa context là một trách nhiệm integration/anti-corruption layer.
3. Chỉ công bố những trạng thái cần cho consumer qua contract đã định nghĩa.
4. Cho phép nội bộ thay đổi khi external contract còn tương thích.
5. Khi có quy tắc thật sự đồng nhất, xác định ai là source of truth và cơ chế đồng bộ phù hợp.

**DRY (Don't Repeat Yourself)** không có nghĩa mọi đoạn code giống nhau đều phải trừu tượng hóa ngay. Cần phân biệt **trùng implementation** với **trùng tri thức được sở hữu chung**.

## 21. Common library: chỉ ổn khi public contract ổn định

Một thư viện kỹ thuật dùng chung có thể hữu ích: trace context, serialization adapter, HTTP helper hoặc test fixtures. Nhưng không phải version nào cũng nên buộc mọi service nâng cấp.

Quy tắc đề xuất:

- Thư viện có public API và semantic versioning/compatibility policy rõ.
- Artifact được phát hành bất biến vào registry.
- Consumer pin version riêng và nâng theo release cycle của mình.
- Breaking change cần major release, migration guide hoặc deprecation window.
- Không đổi default gây side effect mà không thông báo.
- Tách core và framework-specific adapter nếu chúng có nhịp nâng khác.
- Có test source/binary/behavior compatibility theo mức rủi ro.
- Không ghép 20 năng lực độc lập vào một mega-starter chỉ để cài đặt tiện.

### Gradle ví dụ

~~~groovy
// order-service/build.gradle
dependencies {
    implementation 'com.example.platform:telemetry-core:1.5.1'
}

// payment-service/build.gradle
dependencies {
    implementation 'com.example.platform:telemetry-core:1.4.8'
}
~~~

Hai service có thể sử dụng phiên bản khác nhau, miễn mỗi classpath riêng và hợp đồng network vẫn tương thích. Khi thư viện là **domain rules package**, owner phát hành phải là domain team và release notes phải giải thích ý nghĩa quy tắc, không chỉ mô tả code diff.

## 22. Tránh mega-starter ôm cả platform và business

Anti-pattern:

~~~text
company-spring-starter
  - logging
  - authentication
  - authorization
  - HTTP retries
  - database migrations
  - CustomerTierRule
  - DiscountCalculator
  - RefundEligibility
  - payment integration
~~~

Một thay đổi nhỏ về telemetry có thể kéo theo:

- Nâng Spring Boot/JDK major.
- Đổi default retry của payment.
- Thay bean graph, security filters hoặc transaction behavior.
- Thay rule giảm giá và điều kiện hoàn tiền.
- Buộc mọi dịch vụ nâng trong cùng một đợt.

Một hướng tách:

~~~text
Platform artifacts:
  telemetry-api
  telemetry-spring-adapter
  service-identity-client
  resilience-primitives
  deployment-templates

Domain-owned contracts:
  pricing-quote-api
  payment-public-client
  inventory-reservation-schema
  refund-policy-contract
~~~

Không phải artifact nào cũng cần thành microservice riêng. Mục tiêu là **version, owner và compatibility boundary** rõ, giúp các service không phải sửa/triển khai đồng loạt.

## 23. Code ví dụ: tách technical capability và business policy

Giả sử Checkout cần ghi audit mỗi khi quyết định refund. Năng lực audit có thể cung cấp một giao diện kỹ thuật trung lập:

~~~java
public interface AuditSink {
    void append(AuditRecord record);
}

public record AuditRecord(
        String eventType,
        String correlationId,
        String actorId,
        String resourceId,
        String outcome
) {}
~~~

Ví dụ ở lớp domain:

~~~java
public final class RefundService {
    private final RefundPolicy refundPolicy;
    private final AuditSink auditSink;

    public RefundService(RefundPolicy refundPolicy, AuditSink auditSink) {
        this.refundPolicy = refundPolicy;
        this.auditSink = auditSink;
    }

    public RefundDecision decide(RefundRequest request) {
        RefundDecision decision = refundPolicy.evaluate(request);

        auditSink.append(new AuditRecord(
                "refund.decision",
                request.correlationId(),
                request.actorId(),
                request.orderId(),
                decision.code()
        ));
        return decision;
    }
}
~~~

RefundPolicy và RefundDecision ở đây là khái niệm domain, có thể là interface/record thuộc Refund context. AuditSink **không được tự quyết** khách có được hoàn tiền hay không; nó chỉ lưu một audit event theo hợp đồng. Ví dụ rút gọn chưa bao phủ atomic persistence, fail-closed audit, privacy redaction hay delivery guarantees.

Một biến thể lỗi:

~~~java
public final class PlatformAuditService {
    public boolean allowRefund(String tier, int daysSincePurchase) {
        return tier.equals("GOLD") || daysSincePurchase < 30;
    }
}
~~~

Nếu method này thuộc platform audit library, platform đã vô tình trở thành owner của một chính sách hoàn tiền. Cần chuyển rule về Refund domain, dùng một audit primitive riêng, và kiểm thử business policy tại đúng nơi.

### Một lưu ý về Java package

Tên package không quyết định kiến trúc. Một lớp nằm trong package com.company.common vẫn có thể là domain policy; một lớp nằm trong package com.company.platform nhưng gọi Pricing DB để quyết định voucher không còn thuần platform. Phải xem **hành vi và quyền sở hữu**, không chỉ folder structure.

## 24. Ranh giới interface giúp thay implementation kỹ thuật

Một service có thể phụ thuộc vào các port/capability interfaces thay vì trực tiếp gắn với SDK hạ tầng:

~~~java
public interface EventPublisher {
    void publish(String topic, String key, byte[] payload);
}

public interface SecretProvider {
    String read(String logicalName);
}
~~~

Platform cung cấp adapter dùng broker hoặc secret manager cụ thể. Domain vẫn quyết định **topic/event nào**, payload semantics, khi nào phát và secret dùng cho mục đích nào.

Tuy nhiên interface quá generic cũng có nguy cơ che các semantics quan trọng: publish có transaction không, ACK nghĩa gì, secret reload thế nào, timeout ra sao? Public contract cần làm rõ delivery guarantees, security, error behavior và versioning. Tránh tạo abstraction chỉ vì muốn giấu tên Kafka hoặc Vault mà làm consumer không thể lý giải lỗi.

## 25. Golden path không phải một business framework toàn quyền

Golden path cho service Java có thể cung cấp:

- Repository template và Gradle/Maven baseline.
- Logging/tracing/metrics starter.
- Container build và SBOM/signing.
- Security/dependency scan.
- Deployment template, readiness/liveness conventions.
- Service catalog registration.
- Secret wiring, CI/CD và policy enforcement.
- Ví dụ integration test và contract test.
- Runbook, on-call và release checklist mẫu.

Nó không nên mặc định cung cấp:

- Quy tắc tính phí áp dụng cho mọi sản phẩm.
- State machine cho mọi order/payment.
- Một entity Customer dùng chung bắt buộc.
- Tự động retry mọi POST không xét idempotency.
- Một schema DB chung mà mọi service phải dùng.
- Một ngày duy nhất buộc tất cả service nâng dependency.

Một golden path tốt **đưa ra mặc định hợp lý** nhưng không xóa quyền quyết định thuộc domain. Nếu workload cần cấu hình khác vì rủi ro đã biết, có thể có cơ chế exception có owner, audit và tiêu chí kiểm soát.

## 26. Platform team nên cung cấp API thay vì danh sách ticket

Một năng lực nền tảng có thể trình bày bằng một giao diện khai báo:

~~~yaml
apiVersion: platform.example/v1
kind: ServiceRuntime
metadata:
  name: order-service
spec:
  ownerTeam: order-team
  environment: production
  runtime: java21
  imageDigest: "sha256:<digest-from-registry>"
  resources:
    cpu: "500m"
    memory: "1Gi"
  observability:
    tracing: enabled
    metrics: enabled
  secrets:
    - reference: order-db-credentials
  exposure:
    type: internal-api
~~~

Đây là **schema minh họa**, không phải CRD sẵn có hoặc một Kubernetes manifest hoàn chỉnh. Platform có thể validate và triển khai thành resource phù hợp, áp policy/guardrails và trả về trạng thái.

Điều người dùng nội bộ nên nhận:

- Cách yêu cầu capability với input/output rõ.
- Thời gian provisioning và failure status có thể truy vết.
- Khả năng xem quota, cost và ownership.
- Cách rollback/update/cancel resource.
- Link docs/support và SLO của platform API.
- Versioning và deprecation để service không bị ép cập nhật đồng thời.

**Platform làm tốt phần cơ chế**, còn Order Team lựa chọn product behavior và kiểm chứng API/order semantics khi sử dụng runtime này.

## 27. Platform as a Product và trải nghiệm người phát triển

Một đội nền tảng không nên chỉ đo số lượng cluster, thư viện hoặc template đã tạo. Nên đo các kết quả mà các đội sử dụng nền tảng thực sự nhận được:

| Khía cạnh | Câu hỏi | Ví dụ tín hiệu |
|---|---|---|
| Onboarding | Một service mới vào production nhanh và an toàn không? | Lead time từ repo đến staging |
| Self-service | Có cần ticket thủ công cho hoạt động thông thường không? | Tỷ lệ provisioning không cần người can thiệp |
| Deploy | Pipeline hoạt động ổn và dễ rollback không? | Deployment success, mean recovery time |
| Observability | Owner có tìm được trace, dashboard và SLO không? | Time to diagnose |
| Security | Guardrails phát hiện vi phạm trước production không? | Policy violations/remediation latency |
| Compatibility | Cập nhật platform có buộc consumer nâng đồng loạt? | Tỷ lệ breaking changes, số migration |
| Reliability | Năng lực nền tảng có đáp ứng SLO? | Availability, latency, provisioning time |
| Cognitive load | Người dùng có hiểu và sử dụng được API không? | Feedback, docs adoption, support demand |
| Cost | Nền tảng giúp tối ưu tiêu thụ mà vẫn đạt SLO? | Cost per workload/business unit |

Không nên dùng một metric riêng lẻ để xếp hạng team. Ví dụ ít ticket có thể do portal tốt, nhưng cũng có thể do developer bỏ cuộc không dùng platform. Cần feedback trực tiếp và quan sát hành trình thực tế.

## 28. Ownership mapping cho Platform và domain

Một mô hình minh họa:

| Nhiệm vụ | Platform Team | Domain Team | Security/Compliance | Product |
|---|---|---|---|---|
| Cấp container runtime | Accountable/Responsible | Consumer | Consulted theo policy | Informed |
| Tạo event broker infrastructure | Accountable/Responsible | Định nghĩa nhu cầu topic | Consulted khi cần | Informed |
| Định nghĩa OrderCreated event schema | Tooling/standards | Accountable/Responsible | Consulted về dữ liệu nhạy cảm | Informed |
| Đặt rule chiết khấu | Không quyết định | Accountable/Responsible (Pricing) | Consulted nếu có rủi ro | Tham gia business approval |
| SLO của Pricing API | Cung cấp observability | Accountable cùng định nghĩa chất lượng | Consulted nếu yêu cầu pháp lý | Đồng thuận kỳ vọng |
| CI signing/admission | Cung cấp và vận hành | Sử dụng, sửa vi phạm artifact | Policy owner | Informed |
| Refund correctness | Không quyết định | Accountable/Responsible (Refund/Payment) | Consulted theo policy | Đồng thuận nghiệp vụ |
| Điều tra platform outage | Accountable/Responsible | Đánh giá tác động service | Tham gia khi security incident | Nhận thông tin |
| Điều tra Order API outage | Hỗ trợ dependency | Accountable/Responsible (Order) | Tham gia khi cần | Đánh giá người dùng |

RACI trong mỗi tổ chức có thể khác. Quan trọng là **một owner quyết định cho từng hành vi**, không biến thẩm quyền thành chuyện ai đang có quyền ghi vào repository.

## 29. Governance: chuẩn kỹ thuật chung nhưng không duyệt mọi thay đổi domain

Nền tảng và quản trị cần bảo vệ tổ chức trước rủi ro hệ thống: dữ liệu nhạy cảm bị lộ, dependency không được vá, không có audit, không có backup hoặc deployment thiếu nguồn gốc.

Governance tốt tập trung vào **guardrails tự động**:

- Identity/IAM theo quyền tối thiểu.
- Image provenance, vulnerability scanning và artifact signing.
- Network policies, encryption, secret handling.
- Service catalog có owner, data classification và on-call.
- Backup/DR, retention và compliance standards.
- API/event contract policy và kiểm tra breaking changes.
- CI policy gates và quy trình exception có audit.
- Quy tắc SLO/incident response cho dịch vụ quan trọng.

Governance không nên:

- Bắt Platform Team review mọi phép tính giá nhỏ.
- Yêu cầu tất cả service dùng một entity class chung.
- Buộc triển khai đồng thời chỉ vì thư viện common mới ra phiên bản.
- Chặn mọi release bằng một ticket thủ công ngay cả khi policy đã được chứng minh.
- Dùng generic templates để thay thế domain modeling.

### Cách diễn đạt guardrail

Không nói: “Mọi service phải chạy đúng code của Pricing Team để được deploy.”

Thay vào đó, có thể nói: “Service nào xuất hóa đơn phải sử dụng một quyết định giá có nguồn xác nhận, version, audit trail và quy tắc làm tròn đã được phê duyệt theo contract.” Pricing/Finance sở hữu tiêu chuẩn nghiệp vụ; Platform có thể giúp thực thi metadata, logging và policy gates.

## 30. Policy-as-code và quyền thay đổi rule

Policy-as-code đem lại lợi ích khi quản lý thay đổi rõ:

~~~text
Rule source
   |
   v
Review bởi đúng owner
   |
   v
Unit/contract/impact tests
   |
   v
Versioned policy artifact
   |
   v
Distribution / Evaluation engine
   |
   v
Audit decision + monitoring
~~~

Với technical guardrail, owner có thể là Security/Platform. Với refund limits, owner phải là Refund/Product và bộ phận kiểm soát phù hợp. Engine chung không xóa yêu cầu phải có **nguồn gốc và lịch sử phê duyệt của chính rule**.

Các thành phần cần lưu:

- Policy ID và version.
- EffectiveFrom/EffectiveTo nếu có.
- Người phê duyệt và lý do.
- Input data contract và missing-data behavior.
- Tập test cases, edge cases và expected decisions.
- Rollback plan cho policy mới.
- Những quyết định đã xảy ra theo policy version cũ.

Không nên thay đổi một rule có hiệu lực với giao dịch lịch sử rồi tính lại kết quả theo bản mới mà không có policy và audit rõ.

## 31. Versioning của platform capability

Mục tiêu của platform là giúp các đội **tiêu thụ khả năng** mà không buộc mọi ứng dụng nâng version đồng thời.

Các cơ chế:

1. Semantic versioning cho thư viện và API đã xác định public contract.
2. Additive API changes, giữ compatibility window.
3. Support policy cho phiên bản cũ.
4. Feature flags/opt-in cho thay đổi hành vi.
5. Compatibility matrix theo Java/Spring/SDK/runtime.
6. Deprecation và migration guide thay vì xóa đột ngột.
7. Canary để xem tác động trên một nhóm consumer trước.
8. Pin artifact version/digest để build có thể tái lập.
9. Consumer contract tests hoặc thử upgrade theo service.
10. Emergency security deadlines có đánh giá rủi ro và lộ trình riêng.

Ví dụ Order vẫn dùng telemetry-core 1.4 trong khi Payment dùng 1.6. Nếu library không thay network contract, đây là chuyện bình thường. Trái lại, nếu một phiên bản thư viện tự đổi retry default của Payment từ 1 lên 5, cần đánh giá **behavior compatibility** chứ không coi đây là thay đổi vô hại.

## 32. Versioning của domain capability

Một domain service thường phải bảo vệ cả API contract, schema/event, semantics và dữ liệu lịch sử.

Ví dụ Pricing Quote v1 và v2:

~~~text
Pricing Quote v1:
  total, currency, quoteId

Pricing Quote v2:
  total, currency, quoteId, taxBreakdown, policyVersion
~~~

Nếu thêm field optional và client cũ được thiết kế bỏ qua unknown fields, v2 có thể tương thích với client cũ. Nhưng không thể kết luận chỉ từ việc "thêm field": parser, business meaning và behavior phải được kiểm thử.

Một thay đổi về **ý nghĩa** có thể breaking dù JSON schema giữ nguyên. Chẳng hạn field total trước đây gồm phí vận chuyển, sau đó không còn gồm phí vận chuyển. Vì vậy domain owner phải công bố semantic contract và migration path.

Platform schema registry chỉ bảo vệ một số đặc tính tương thích kỹ thuật. Nó không tự biết field "total" đang có ý nghĩa tài chính như thế nào.

## 33. Shared data và nguồn sự thật

Nhiều team dùng cùng customer tier, currency rates hoặc danh mục sản phẩm. Cần xác định mô hình chia sẻ dữ liệu:

- **Authoritative service:** một miền sở hữu dữ liệu và API thay đổi/đọc.
- **Reference data snapshot:** bản dữ liệu versioned được phân phối tới các consumer.
- **Event-driven projection:** các consumer tự tạo read model từ event.
- **Cache:** bản sao tạm của dữ liệu có quy tắc freshness và invalidation.
- **Federated query:** phục vụ phân tích hoặc tổng hợp khi phù hợp, không tự tạo quyền ghi xuyên miền.

Điểm phân biệt: Platform cung cấp broker/cache/data pipeline; domain owner quyết định dữ liệu nào đúng, những thay đổi nào hợp lệ, thời gian hiệu lực và ranh giới nhất quán.

### Tránh việc “common database” thành cách tích hợp

Khi Pricing và Checkout cùng update bảng promotion_rule, không ai rõ ai là nguồn quyết định. Tốt hơn là định nghĩa Pricing API/event với hợp đồng, dù đọc qua cache hoặc read model để giảm runtime coupling.

## 34. Cơ chế điều phối chung và orchestration riêng sản phẩm

Một workflow scheduler hoặc job platform có thể:

- Chạy job theo lịch, retry một task kỹ thuật.
- Lưu trạng thái tác vụ, limit concurrency và tạo log.
- Cấp queue/worker và observability.

Nhưng rule “đơn nào được hủy”, “bước nào bắt buộc để hoàn tiền”, “khi nào gửi cảnh báo gian lận” thuộc domain.

Ví dụ một saga giữa Order, Inventory, Payment:

~~~text
OrderCreated
   |
   v
ReserveInventory
   |
   v
AuthorizePayment
   |
   +-- success --> ConfirmOrder
   |
   +-- failure --> ReleaseInventory
~~~

Platform có thể cung cấp saga framework hoặc durable execution engine; **Order/Checkout Team** quyết định thứ tự, failure compensation, deadline và điều kiện transition. Việc có retry engine chung không làm platform trở thành owner của logic hoàn đơn.

## 35. Quản lý vòng đời của platform capability

Một platform API hoặc runtime có vòng đời:

1. **Discovery:** các đội gặp cùng một đau điểm kỹ thuật; thu thập nhu cầu và cost of toil.
2. **Pilot:** một vài service dùng thử, đo hiệu quả và failure modes.
3. **Productize:** định nghĩa API/contract, security model, docs, SLO và support.
4. **Adopt:** hướng dẫn migration, template, compatibility và self-service.
5. **Operate:** theo dõi availability, reliability, cost, support load và usage.
6. **Evolve:** thay đổi version không gây breaking bất ngờ; nhận feedback.
7. **Deprecate:** thông báo, support window, kế hoạch thay thế.
8. **Retire:** chứng minh không còn consumer hoặc có migration phù hợp.

Đừng áp platform cho toàn công ty chỉ sau một prototype thành công trên service ít rủi ro. Một library phù hợp cho Catalog chưa chắc phù hợp cho Payment với invariant tài chính.

### Quy trình exception

Đội service có thể cần đi ngoài golden path vì latency cực thấp, compliance, edge runtime hoặc mô hình dữ liệu đặc biệt. Exception nên ghi:

- Lý do và thời hạn.
- Rủi ro bổ sung và owner.
- Bằng chứng kiểm soát an toàn tương đương.
- Ngày review và điều kiện quay lại supported path.

Đây không phải tự do không kiểm soát; đó là cách tránh biến platform thành trở ngại đối với yêu cầu chính đáng của sản phẩm.

## 36. Team topology và cognitive load

Một nhóm sản phẩm không nên phải hiểu sâu toàn bộ Kubernetes, storage driver, mTLS, Kafka internals, metrics collector và key management để sửa một business rule. Platform giúp giảm cognitive load bằng giao diện đã đóng gói.

Ngược lại, nếu Platform Team sở hữu luôn business rules của mọi service, cognitive load của platform cũng bùng nổ:

~~~text
Platform Team cần biết:
  Order states + Inventory quota + Pricing campaign
  + Payment compliance + Fraud heuristics + Loyalty tiers
  + Kubernetes + IAM + CI/CD + Tracing ...
~~~

Đây là dấu hiệu sai ranh giới. Mục tiêu là:

- Stream-aligned/domain teams tập trung năng lực tạo giá trị.
- Platform team tập trung developer experience và kỹ thuật lặp lại.
- Enabling/specialist teams hỗ trợ tạm thời khi cần kỹ năng sâu.
- Ownership của service/platform được ghi rõ, có escalation và cơ chế incident response chung.

Không có quy tắc một team = một microservice. Một team có thể sở hữu nhiều service thuộc cùng bounded context. Điều cần giảm là những đường phối hợp bắt buộc cho thay đổi thông thường.

## 37. Kinh tế của abstraction: lúc nào đáng chia sẻ?

Một shared component tạo ra cả lợi ích và chi phí:

**Lợi ích có thể có:**

- Giảm công việc lặp lại giữa các team.
- Chuẩn hóa bảo mật/quan sát và cách sử dụng kỹ thuật.
- Tạo khả năng cập nhật hạ tầng đồng nhất trong phạm vi hợp đồng.
- Tăng tốc onboarding và giảm sai lầm phổ biến.
- Tập trung chuyên môn khi điều đó thật sự tạo giá trị.

**Chi phí có thể có:**

- Versioning, compatibility và support của nhiều consumer.
- Thời gian review/approval và phối hợp thay đổi.
- Network dependency hoặc SDK dependency.
- Chi phí migration và rollback khi breaking.
- Thêm failure domain tập trung.
- Vấn đề ownership khi thành phần chứa tri thức của nhiều domain.

Một abstraction tốt giảm tổng chi phí nhiều hơn chi phí nó tạo ra. Nếu hai service chỉ có vài dòng code tương tự nhưng business semantics khác nhau, duplicate có chủ đích có thể rẻ hơn “shared domain library” kéo theo hàng chục consumer.

## 38. Anti-pattern 1: Common-core chứa toàn bộ domain

~~~text
common-core:
  UserEntity
  OrderEntity
  PaymentEntity
  PriceCalculator
  RefundStatus
  InventoryQuota
  PermissionChecker
  DateUtils
  LoggingUtils
~~~

Mỗi domain thêm một field làm tăng version common-core, khiến nhiều service thay đổi dependency dù không liên quan. Shared entity còn có thể ép database schema và persistence model giống nhau.

Cách giải quyết:

1. Xác định chủ sở hữu và ý nghĩa từng class.
2. Đưa domain entity/rule về bounded context phù hợp.
3. Công bố API/event/schema contract cho dữ liệu được chia sẻ thật sự.
4. Giữ technical primitives ổn định trong library nhỏ.
5. Cung cấp migration adapter để consumer chuyển từng bước.
6. Không cắt bỏ class cũ ngay khi còn service chưa thể nâng.

## 39. Anti-pattern 2: Platform vừa cung cấp engine vừa quyết định policy

Ví dụ platform cung cấp một rule engine cho chiết khấu và cũng tự thay rule “VIP được giảm 15%” theo yêu cầu từ nhiều bên không rõ owner.

Hệ quả:

- Không ai đứng ra chịu trách nhiệm khi doanh thu sai.
- Một thay đổi technical runtime có thể đổi business outcomes.
- Product không có audit của những rule đã dùng.
- Service khác được yêu cầu deploy theo policy không rõ hiệu lực.
- Khi lỗi xảy ra, Platform Team thiếu context để chọn compensation.

Cách giải quyết là tách:

~~~text
Policy engine/runtime --> Platform owner
Rule definitions ------> Pricing/Promotion owner
Business approval -----> Product/Finance theo quy trình
Evaluation audit ------> Cơ chế chung + domain event/decision ID
~~~

Khi có tranh chấp kết quả, owner của rule có thể kiểm tra policyVersion/effectiveAt; Platform chịu trách nhiệm engine thực thi đúng contract.

## 40. Anti-pattern 3: Shared adapter lộ nghiệp vụ của provider

Một payment SDK dùng chung có thể ban đầu chỉ giúp HTTP/auth. Dần dần nó chứa:

- Logic quyết định provider cho mỗi loại đơn.
- Công thức thu phí và hoàn tiền.
- Retry capture tự động.
- Hợp đồng idempotency và transition state.
- Rule chống gian lận.

Nếu SDK nằm trong platform mà không có Payment owner, nhiều service sẽ tự triển khai các quyết định payment khác nhau. Nên phân tách:

- Technical HTTP client/resilience/identity primitives: nền tảng hoặc library kỹ thuật.
- Payment API client và domain schema: Payment owner.
- Provider selection, capture/refund correctness và ledger: Payment domain service.
- Authentication/secret delivery mechanism: platform.
- External provider credential policy: Payment phối hợp Security/Platform.

Không phải mọi phần Payment đều cần đi qua service call đồng bộ; có thể dùng event/contract theo yêu cầu latency và consistency. Nhưng quyền quyết định nghiệp vụ phải rõ.

## 41. Anti-pattern 4: Platform thành điểm phê duyệt tất cả

Nếu mọi API đổi field đều phải chờ Platform Team review thủ công, mỗi deploy phải có ticket và mọi database migration đều được một nhóm trung tâm chạy bằng tay, các service có ranh giới source nhưng không còn độc lập delivery.

Giải pháp:

- Chuẩn hóa policy thành automated checks.
- Cung cấp self-service provisioning và deployment.
- Hợp đồng rõ API/schema và test compatibility ở producer/consumer.
- Quyền thay đổi theo guardrails, audit và separation of duties khi cần.
- Escalation cho trường hợp rủi ro cao hoặc ngoại lệ.
- SLO của platform provisioning/CI/CD và support time.

Mục tiêu không phải bỏ mọi kiểm soát, mà chuyển kiểm soát thông thường từ hàng đợi con người sang cơ chế có thể kiểm chứng, được version và theo dõi.

## 42. Incident response: lỗi platform khác lỗi domain

Ví dụ Checkout SLO giảm đột ngột.

~~~text
Checkout user journey thất bại
            |
            v
Checkout owner nhận/điều phối impact
            |
     +------+----------------+
     |                       |
Sai business state        Broker cluster outage
     |                       |
     v                       v
Order/Payment team        Platform/Broker team
điều tra rule/ledger      phục hồi hạ tầng
     |                       |
     +-----------+-----------+
                 |
                 v
Reconcile, smoke test, mở traffic an toàn
~~~

Trách nhiệm không nên phân chia theo “lỗi ở class của ai?”. Một lỗi infrastructure có thể gây duplicate payment sau khi broker phục hồi; broker owner khôi phục log, Payment owner kiểm tra idempotency và reconciles external provider, Checkout owner giám sát hành trình người dùng.

Incident commander có thể điều phối nhiều nhóm. **Không tranh cãi ownership trước khi giảm thiệt hại cho người dùng**; sau sự cố mới điều chỉnh ranh giới và runbook khi thấy khoảng trống.

## 43. Platform SLO và service SLO

Một platform capability cần metric của chính nó:

| Platform capability | SLI minh họa | Không nên nhầm với |
|---|---|---|
| Deployment platform | Tỷ lệ deployment requests hoàn thành theo contract | Tỷ lệ checkout của sản phẩm |
| Secret manager | Tỷ lệ đọc/rotate secret hợp lệ đúng thời hạn | Quyết định cấp quyền hoàn tiền |
| Broker platform | Availability, produce/fetch latency, replication lag | Correctness khi xử lý PaymentCompleted |
| Service catalog | Tỷ lệ lookup thành công và độ mới metadata | Việc service thực sự có owner hành động được |
| Telemetry pipeline | Tỷ lệ ingest không mất/đến đúng hạn | Tính đúng đắn của metric business SLI |
| Database platform | Failover/backup restore success và latency provisioning | Quy tắc update tồn kho |
| CI/CD | Pipeline success và thời gian phục hồi khi lỗi platform | Một release nghiệp vụ có đúng hay không |

Service owner và Product nên cùng định nghĩa SLO end-to-end cho hành trình. Platform SLO giúp xác định dependency nền tảng có đáp ứng nghĩa vụ và phối hợp triage, nhưng không thay thế phép đo trải nghiệm khách hàng.

## 44. Migration: từ common monolith thành ranh giới có owner

Giả sử tổ chức có module common.jar đang được 30 service dùng. Nó chứa Logger, AuthVerifier, DiscountRule, RefundPolicy, InventoryDTO và RetryInterceptor.

### Bước 1 — Inventory phụ thuộc

Liệt kê class/API, service consumer, version đang dùng, public surface, runtime dependency và những thay đổi thường làm consumer gãy. Không sửa mọi service ngay trong một PR.

### Bước 2 — Phân nhóm theo ý nghĩa

~~~text
Telemetry/Logger ----------> platform-telemetry
AuthVerifier --------------> platform-identity-sdk
RetryInterceptor ----------> resilience-primitives
DiscountRule --------------> Pricing domain
RefundPolicy --------------> Refund/Payment domain
InventoryDTO --------------> Inventory public contract
~~~

### Bước 3 — Chỉ định owner và hợp đồng

Mỗi artifact/capability có owner, SLO nếu là runtime service, version policy, API/schema contract và support window. Pricing/Refund cần Product approval cho business rule; platform cần compatibility và security requirements.

### Bước 4 — Tách code theo hướng additive

Tạo các artifact mới; giữ adapter hoặc deprecated facade trong common.jar một giai đoạn. Tránh xóa class mà consumer chưa thể thay. Test source/binary/behavior compatibility theo rủi ro.

### Bước 5 — Chuyển consumer dần

Mỗi service nâng theo lịch của owner: Order trước, Payment sau, Notification sau nữa. Nếu chuyển rule sang API mới, có thể dùng strangler/adapter hoặc data snapshot để tránh bắt mọi service deploy cùng ngày.

### Bước 6 — Kiểm chứng runtime mixed versions

Các consumer cũ và mới có thể hoạt động cùng nhau, đặc biệt khi event schemas, retry policy và domain decisions có thể khác version. Với Pricing, phải định nghĩa effective date và quote version để không làm giá lịch sử thay đổi.

### Bước 7 — Decommission common facade

Khi đã kiểm chứng không còn consumer phụ thuộc, kết thúc support theo chính sách, archive artifact và cập nhật docs/catalog. Không xóa artifact cũ khỏi registry khi nó còn cần cho rollback, audit hoặc rebuild được phép.

## 45. Kịch bản thực hành: Order, Pricing và Platform

Một team đề xuất đưa tất cả quy tắc tính giá, membership tier và HTTP retry vào company-platform-starter để các service “dùng chung cho chuẩn”.

Hãy phân tích:

**Phần phù hợp cho platform:**

- Config-driven timeout, bounded retry primitives.
- Tracing/logging, identity, credential delivery.
- Artifact publishing, CI/CD, deployment templates.
- Registry schema/tooling và kiểm tra compatibility.
- SLO/cost của các năng lực nền tảng.

**Phần cần domain owner:**

- Chính sách giảm giá, stacking/coupon precedence.
- Membership eligibility và effective time.
- Quote semantics, tax/currency rounding theo hợp đồng.
- Khi nào retry một thao tác tạo payment/order; idempotency key và unknown outcome.
- Quy tắc giá đã xác nhận không được thay sau khi checkout.

**Thiết kế đề xuất:**

1. Pricing Team công bố Quote API versioned.
2. Order lưu quoteId, policyVersion và total được phê duyệt.
3. Platform cung cấp HTTP client, identity, telemetry và resilience primitives, không chọn chính sách nghiệp vụ.
4. Checkout/Order owner chọn timeout/retry theo contract và test end-to-end.
5. Các đội triển khai độc lập, có contract tests và support window.
6. Những rule đổi theo luật hoặc chiến dịch có approval/effective date do domain điều phối.

## 46. Một bảng quyết định tái sử dụng nhanh

| Tình huống | Giải pháp nên cân nhắc |
|---|---|
| Nhiều service cần trace ID | Platform telemetry SDK/envelope |
| Nhiều service cần một nơi quản lý secret | Platform secret management service |
| Nhiều service cần tính giá chính thức | Pricing domain service hoặc versioned quote contract |
| Nhiều service có phép validate tên khác nhau | Giữ trong context nếu semantic khác |
| Một rule thống nhất cần đánh giá offline | Domain-owned versioned rule package |
| Nhiều service cùng cần HTTP retry | Technical primitive + consumer-specific policy |
| Nhiều service đọc customer tier | Customer/Loyalty authoritative source + cache/read model |
| Các service cùng phát event qua Kafka | Broker platform + domain-owned event schemas |
| Mỗi team muốn tạo database mới | DB provisioning self-service + team-owned schemas |
| Một service cần chạy approval workflow | Platform execution engine + domain-owned workflow definition |
| Nhiều service dùng cùng customer JPA entity | Tránh; tách model và dùng API/event contract |
| Tất cả service cần policy ngăn image không ký | Platform/Security admission guardrail |
| Refund policy thay đổi theo sản phẩm | Refund domain, không đặt trong generic IAM library |

Không có lựa chọn hoàn hảo cho mọi hệ thống; ranh giới nên phản ánh cách tổ chức vận hành, chi phí giao tiếp và yêu cầu nhất quán thật sự.

## 47. Checklist review một thành phần “dùng chung”

Trước khi đưa nó vào platform hoặc common library, hãy hỏi:

1. Thành phần giải quyết vấn đề kỹ thuật lặp lại hay business decision?
2. Ai chịu trách nhiệm nếu kết quả trả về sai đối với người dùng?
3. Ai có quyền thay đổi rule/contract và khi nào phải hỏi Product?
4. Có state/dữ liệu nghiệp vụ được sở hữu bên trong không?
5. Nếu thay logic, consumer có bị ép triển khai đồng loạt không?
6. Nếu là library, có public API, versioning và support window không?
7. Nếu là runtime service, SLO/owner/DR/escalation đã rõ chưa?
8. Platform có thể cung cấp primitive thay vì ôm policy content không?
9. Đã cân nhắc giữ code riêng nếu semantics khác nhau chưa?
10. Consumer cần local evaluation, API đồng bộ hay event bất đồng bộ?
11. Có data freshness/consistency contract nếu dùng cache/read model?
12. Có kiểm thử source/binary/behavior/wire compatibility?
13. Có thể rollback mà không tính lại dữ liệu nghiệp vụ lịch sử sai không?
14. Nguồn sự thật và identity/version của mỗi quyết định nghiệp vụ đã rõ?
15. Ai quản lý secrets, IAM, quota, audit và những trường hợp ngoại lệ?
16. Hệ thống có giảm hay tăng cognitive load của các nhóm?
17. Có phát sinh single point of failure và dependency runtime mới không?
18. Các quyết định security và compliance nằm đúng quyền phê duyệt?
19. Có documentation, sample, migration guide, dashboard và support?
20. Đội platform có thực sự coi developer là người dùng sản phẩm nội bộ?
21. Đội domain có đủ quyền tự deploy/rollback trong guardrails?
22. Đã xác định phạm vi chi phí và thời hạn duy trì nhiều version chưa?
23. Trường hợp cần thay đổi khẩn vì bảo mật/luật, ai điều phối?
24. Có thể chứng minh mixed-version deployment an toàn không?
25. Nếu deprecate, ai chịu trách nhiệm consumer migration và cleanup?

## 48. Bài tập tự luyện

### Bài A — Phân loại 12 năng lực

Cho danh sách: TraceCollector, KafkaCluster, PaymentRefundPolicy, DatabaseBackupService, PricingCalculator, OrderStateMachine, FeatureFlagService, CampaignEligibility, SecretManager, AuthTokenVerifier, InventoryReservationRule, BuildPipeline. Hãy phân loại nền tảng/miền/kết hợp và ghi owner cho từng phần.

### Bài B — Tách authorization

Một common-security SDK hiện chứa JWT verification và rule "người VIP được hoàn tiền trong 45 ngày". Hãy thiết kế phương án tách technical identity khỏi Refund policy, nêu API/contract và test cần có để chuyển dần consumer.

### Bài C — Tách mega-starter

Company starter chứa 15 module và mọi lần nâng làm Checkout/Payment cùng thay code. Hãy chọn module kỹ thuật nên tách, public API, versioning/deprecation policy và cách rollout từng service.

### Bài D — Chọn API hoặc rule package

Một thuật toán phí vận chuyển được Checkout và Billing dùng. Kết quả phải audit được, và khi phát hóa đơn phải dùng phiên bản quy tắc tại lúc đặt hàng. Hãy so sánh ShippingQuote API với versioned rule package và cách lưu policy version.

### Bài E — Policy engine

Platform Team cung cấp rule engine. Pricing muốn thay discount stacking rules; Security muốn thêm admission policy cho image chưa ký. Hãy xác định ai review, ai deploy, ai quản lý engine, ai bảo trì rollback và audit decision.

### Bài F — Event ownership

Kafka platform có sự cố; PaymentCompleted bị phát lại gây gửi email trùng. Hãy xác định trách nhiệm broker owner, Payment producer, Notification consumer, hành động idempotency và kịch bản reconciliation.

### Bài G — DB ownership

Order và Payment cùng ghi bảng customer_payment trong một shared database. Hãy đề xuất kế hoạch chuyển dần sang domain data ownership mà vẫn giữ API compatibility và khả năng rollback.

### Bài H — Golden path với ngoại lệ

Platform template chuẩn chạy JVM 21/Spring Boot. Một service latency cực thấp cần native binary. Hãy thiết kế cơ chế exception với guardrails, owner, test, security và support thay vì ép đúng một template.

### Bài I — Tính tổng chi phí abstraction

Ba team cùng có 20 dòng xử lý UUID; một team muốn dựng common service có API để tránh lặp code. Hãy đánh giá chi phí network, SLO, support, team coordination so với dùng library nhỏ hoặc giữ riêng code.

### Bài J — Migration từ common.jar

Có 30 consumer, 6 rule nghiệp vụ và 4 helper kỹ thuật trong một artifact. Hãy chia chúng theo ownership, xây version policy, thiết kế adapter và tiến độ migration sao cho không có một ngày big-bang bắt buộc.

### Bài K — SLO

Platform secret manager đạt 99,99% availability nhưng Checkout SLO vi phạm vì secret rotation không tương thích cấu hình Payment. Hãy xác định trách nhiệm shared incident, cách thiết kế contract và phép thử rotation.

### Bài L — Dữ liệu tham chiếu

Một CustomerTier field được dùng bởi Loyalty, Billing và Support, nhưng mỗi team diễn giải GOLD khác nhau. Hãy xác định source of truth, bounded context mapping, contract và những rule nào không nên đặt trong common model.

## 49. Kết luận

**Năng lực nền tảng** là cơ chế kỹ thuật có thể tiêu thụ rộng rãi, đáng tin cậy và tự phục vụ; **logic nghiệp vụ dùng chung** là tri thức và quyết định của một miền nghiệp vụ, dù nhiều service cùng cần kết quả. Hai thứ có thể dùng cùng công cụ triển khai, cùng CI/CD, cùng broker hoặc cùng policy engine, nhưng không nên nhập chung quyền sở hữu.

Cách phân biệt hiệu quả nhất là hỏi: **ai có thẩm quyền định nghĩa “đúng”**, thành phần **có dữ liệu và quyết định nghiệp vụ không**, và **nó thay đổi theo nhịp nào**. Platform Team nên tạo công cụ, guardrails, API và golden path giúp product teams độc lập; domain teams giữ business meaning, data ownership, invariants và hợp đồng consumer.

Khi ranh giới rõ, các nhóm có thể tái sử dụng kỹ thuật mà không nhân bản cơ sở hạ tầng, đồng thời phát hành đổi mới nghiệp vụ theo lịch riêng. Đó là nền tảng để microservices mở rộng cả về **kiến trúc, tổ chức, khả năng vận hành và tốc độ tạo giá trị**, mà không tạo một common-core hoặc platform team trở thành điểm nghẽn của toàn hệ thống.

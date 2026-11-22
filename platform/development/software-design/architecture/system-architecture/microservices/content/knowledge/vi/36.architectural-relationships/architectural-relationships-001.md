# Microservices và SOA: so sánh mục tiêu và cơ chế tích hợp

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Quan hệ kiến trúc.
>
> **Câu hỏi trung tâm:** Microservices và Service-Oriented Architecture (SOA) đều tổ chức hệ thống quanh các service có giao diện và giao tiếp qua mạng. Vậy chúng giống và khác nhau ở mục tiêu, độ hạt, quyền sở hữu, quản trị, tích hợp và vận hành ra sao? Khi nào nên chọn cách tiếp cận nào, và vì sao không thể chỉ nhìn vào việc có REST API hay ESB để kết luận một hệ thống là microservices hay SOA?

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích SOA và microservices như các cách tiếp cận kiến trúc service-oriented, nhận diện phần giao nhau và các khác biệt thường gặp.
2. So sánh mục tiêu: tích hợp năng lực nghiệp vụ trên phạm vi tổ chức với khả năng phát triển, triển khai và vận hành các thành phần nhỏ có mức tự chủ cao.
3. Phân biệt service boundary, service granularity, bounded context, business capability và deployment unit.
4. Hiểu vai trò của Enterprise Service Bus (ESB), integration platform, API Gateway, message broker, event streaming và service mesh.
5. Đánh giá orchestration/choreography, synchronous/asynchronous integration và tác động tới coupling, latency, reliability, observability.
6. So sánh cách quản trị contract, schema, data ownership, security, versioning và governance trong các mô hình SOA và microservices.
7. Nhận diện các định kiến sai như “SOA luôn dùng ESB”, “microservices không cần governance”, “REST là microservices” hoặc “mỗi service phải có database server riêng”.
8. Chọn kiến trúc theo quy mô tổ chức, domain boundaries, legacy landscape, platform maturity, compliance, team topology và nhu cầu thay đổi.
9. Lập lộ trình tiến hóa từ monolith hoặc SOA hiện hữu sang microservices mà không tạo ra distributed monolith.
10. Thiết kế cơ chế tích hợp phù hợp với workflow, dữ liệu, SLA và failure semantics của từng use case.

**Lưu ý về thuật ngữ:** SOA không có một định nghĩa triển khai duy nhất được mọi tổ chức dùng giống nhau. Một số tài liệu dùng SOA theo nghĩa rộng bao gồm cả microservices; một số dùng SOA để chỉ mô hình enterprise integration có service dùng chung và governance tập trung. Bài này nêu các khuynh hướng thường gặp để so sánh, không xem chúng là luật bất biến.

## 2. Bức tranh tổng quan

SOA và microservices cùng đặt service ở vị trí trung tâm: một thành phần cung cấp capability qua contract để thành phần khác sử dụng. Cả hai đều có thể dùng HTTP, gRPC, messaging, event, schema registry, service discovery và API management.

Khác biệt thường nằm ở **mục tiêu thiết kế và cách tổ chức thực hiện**:

- SOA thường xuất hiện trong bối cảnh tích hợp nhiều hệ thống trong một doanh nghiệp, tái sử dụng business capabilities, chuẩn hóa contract và quản lý luồng thông tin giữa các ứng dụng.
- Microservices thường nhấn mạnh service nhỏ theo bounded context, ownership theo team, deploy độc lập, data autonomy, automation và khả năng thay đổi nhanh.

Một sơ đồ SOA theo kiểu enterprise integration thường gặp:

~~~text
 CRM ─────┐
 ERP ─────┼──► Enterprise Integration Layer / ESB
 Billing ─┤             │
 HR ──────┘             ├──► Customer Service
                        ├──► Order Service
                        ├──► Billing Service
                        └──► Notification Service
~~~

Một sơ đồ microservices theo hướng team/domain autonomy thường gặp:

~~~text
                    API Gateway / Edge
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         Customer Team  Order Team  Catalog Team
              │            │            │
          Customer DB    Order DB    Catalog DB
              │            │            │
              └────────────┴────────────┘
                    Events / APIs
                           │
                 Payment / Fulfillment
                  do các team owner
~~~

Sơ đồ thứ hai không có nghĩa mọi microservices phải kết nối trực tiếp với nhau hoặc không được dùng integration platform. Sơ đồ thứ nhất cũng không có nghĩa mọi SOA bắt buộc phải có một ESB trung tâm.

## 3. SOA là gì?

**Service-Oriented Architecture (SOA)** là cách tổ chức hệ thống thành các service cung cấp năng lực nghiệp vụ hoặc kỹ thuật thông qua interface/contract, để các ứng dụng và quy trình khác có thể sử dụng.

SOA thường giải quyết các vấn đề như:

- Nhiều ứng dụng legacy cần trao đổi dữ liệu.
- Một capability (ví dụ Customer, Billing, Identity) được nhiều hệ thống sử dụng.
- Doanh nghiệp muốn chuẩn hóa cách tích hợp và bảo vệ interface.
- Quy trình nghiệp vụ đi qua nhiều ứng dụng/đơn vị.
- Cần quản lý schema, security, routing, transformation và audit ở cấp tổ chức.
- Một số hệ thống thay đổi chậm, có chu kỳ release và công nghệ khác nhau.

### 3.1. Service trong SOA

Một service thường công bố contract gồm:

- Operations và message schemas.
- Protocol và transport.
- Authentication/authorization.
- Error semantics.
- QoS/SLA, timeout và retry.
- Versioning và deprecation policy.
- Ownership và quy trình thay đổi.

Service có thể được triển khai bằng nhiều công nghệ, nhưng consumer phụ thuộc vào contract đã công bố thay vì implementation nội bộ.

### 3.2. Reusable business capability

Ví dụ một tổ chức có CRM, website, mobile app và ERP. Cả bốn hệ thống cần tra cứu Customer. Thay vì mỗi ứng dụng tự duy trì customer master, một Customer capability có thể cung cấp API hoặc service contract chung.

~~~text
CRM ────────────┐
Mobile App ─────┼──► Customer Capability
Web Store ──────┤          │
ERP ────────────┘          ▼
                       Customer Data
~~~

Lợi ích tiềm năng là giảm logic trùng lặp và tạo một nơi quản lý quy tắc nghiệp vụ. Rủi ro là Customer service trở thành bottleneck nếu quá nhiều consumers phụ thuộc vào một interface không đủ năng lực hoặc governance thay đổi quá chậm.

### 3.3. SOA không phải một protocol

SOA không đồng nghĩa SOAP, XML, WSDL hay ESB. Đây là những công nghệ/phương thức từng được dùng phổ biến trong một số triển khai SOA. SOA cũng có thể sử dụng REST/JSON, gRPC, messaging hoặc event-driven integration.

## 4. Microservices là gì?

**Microservices architecture** tổ chức một ứng dụng thành các service tương đối nhỏ, mỗi service tập trung vào một phạm vi nghiệp vụ có ý nghĩa và có thể được phát triển, triển khai, mở rộng, quan sát và vận hành với mức độc lập phù hợp.

Các đặc trưng thường gặp:

- Business capability hoặc bounded context rõ.
- Team chịu trách nhiệm trọn vòng đời service.
- Deployment unit độc lập.
- Contract ổn định, thay đổi có kiểm soát.
- Data ownership riêng; service khác không tùy tiện ghi vào storage nội bộ.
- Automation cho build, test, deploy, monitoring và rollback.
- Failure isolation, timeout, retries, circuit breaker và backpressure.
- Khả năng scale theo workload.
- Observability xuyên service.

### 4.1. “Micro” nói về phạm vi trách nhiệm

Không có số dòng code hoặc kích thước database chính thức định nghĩa một microservice. Service quá nhỏ có thể khiến một workflow đơn giản phải đi qua nhiều network hops. Service quá lớn có thể giữ nhiều domain không liên quan và không triển khai độc lập được.

Một boundary hợp lý thường bao một tập business rules/invariants cohesive, có owner và contract rõ.

### 4.2. Team autonomy là một phần quan trọng

Một microservice được gọi là độc lập khi team có thể thay đổi, kiểm thử, deploy và xử lý incident trong phạm vi của mình mà không cần phối hợp thường xuyên với nhiều team khác.

Nếu Order Service và Payment Service luôn phải deploy cùng nhau, cùng cập nhật một bảng, và một thay đổi nhỏ cần nhiều team sửa đồng thời, hệ thống có thể là **distributed monolith** dù đã chia nhiều process.

### 4.3. Microservices không chỉ là nhiều REST endpoints

Một monolith có 50 REST controllers vẫn là monolith nếu nó là một deployment unit. Một hệ thống SOA có service nhỏ và deploy độc lập có thể có nhiều đặc điểm của microservices. Phải xem boundary, ownership, data, deployment và vận hành, không nhìn số endpoint.

## 5. Điểm chung giữa SOA và microservices

Cả hai cùng chia sẻ những nguyên tắc quan trọng:

1. **Service contract:** consumer dùng interface đã định nghĩa, không phụ thuộc implementation nội bộ.
2. **Loose coupling:** hạn chế phụ thuộc trực tiếp vào cấu trúc bên trong của provider.
3. **Interoperability:** service có thể giao tiếp qua network/protocol hoặc message contract.
4. **Business capability:** service nên phản ánh năng lực có ý nghĩa, không chỉ là technical function.
5. **Reuse có chọn lọc:** capability có thể phục vụ nhiều consumers nếu contract và ownership phù hợp.
6. **Security:** xác thực, phân quyền, bảo vệ dữ liệu và audit tại boundary.
7. **Governance:** quy tắc về naming, versioning, schema, lifecycle và ownership.
8. **Observability:** đo traffic, errors, latency, saturation và theo dõi luồng xuyên service.
9. **Reliability:** timeout, retry, idempotency, circuit breaking và recovery.
10. **Evolution:** service có thể thay implementation khi contract vẫn tương thích.

Vì vậy, so sánh “SOA cũ, microservices mới” là quá đơn giản. Một SOA được thiết kế tốt có thể hiện đại, event-driven và cloud-native. Một hệ microservices có thể mắc lại các vấn đề cũ nếu governance và integration bị thiết kế kém.

## 6. So sánh mục tiêu kiến trúc

| Khía cạnh | SOA theo khuynh hướng enterprise | Microservices theo khuynh hướng autonomy |
| --- | --- | --- |
| Bài toán nổi bật | Tích hợp ứng dụng và capability trên toàn tổ chức | Tăng tốc phát triển và vận hành các domain/service |
| Đơn vị tổ chức | Enterprise service/business capability | Bounded context hoặc capability do team sở hữu |
| Tái sử dụng | Thường nhấn mạnh capability dùng chung | Tái sử dụng qua contract, tránh service dùng chung thành bottleneck |
| Quản trị | Có thể tập trung hơn ở cấp enterprise | Thường phân tán trong guardrails/platform chung |
| Deployment | Có thể độc lập hoặc theo release window | Nhấn mạnh deploy độc lập |
| Data | Có thể có master/shared data services | Nhấn mạnh owner DB/schema theo service |
| Integration | ESB/integration platform, APIs, messaging | APIs, messaging, events, gateway, mesh |
| Team ownership | Có thể theo ứng dụng hoặc service provider | Thường theo stream/domain, chịu trách nhiệm end-to-end |
| Scale | Theo capability hoặc hệ thống tích hợp | Theo service/workload |
| Failure isolation | Phụ thuộc topology và integration design | Là mục tiêu quan trọng, cần thiết kế rõ |
| Công nghệ | Có thể đa dạng và có chuẩn enterprise | Có thể đa dạng nhưng thường chuẩn hóa golden path |
| Governance | Chính sách dùng chung có thể chi tiết | Guardrails và contract ownership ở team, platform hỗ trợ |

Đây là xu hướng thường gặp. Một tổ chức có thể dùng SOA với deployment độc lập và team ownership rõ; một hệ microservices lớn cũng cần enterprise governance cho data, security và API lifecycle.

## 7. Khác biệt về độ hạt (service granularity)

### 7.1. SOA thường gom theo capability tái sử dụng rộng

Ví dụ:

~~~text
Enterprise Customer Service
  ├── Customer Profile
  ├── Customer Search
  ├── Customer Classification
  └── Customer Master Data
~~~

Một Customer service có thể phục vụ nhiều ứng dụng trong tổ chức. Nó có thể được thiết kế thành một domain service tương đối lớn hoặc một nhóm API.

### 7.2. Microservices thường chia theo bounded context

Một tổ chức có thể phân biệt:

- Customer Identity.
- Customer Profile.
- Customer Support.
- Customer Loyalty.
- Billing Account.

Các khái niệm có thể cùng chứa customerId nhưng business rules và ownership khác nhau. Việc tách thành deployables cần có lý do về thay đổi, dữ liệu, scale, security hoặc ownership; không phải cứ có năm bounded contexts là phải tạo năm process.

### 7.3. Granularity quá lớn và quá nhỏ

| Kiểu | Biểu hiện | Rủi ro |
| --- | --- | --- |
| Service quá lớn | Nhiều domain và team cùng thay đổi | Coupling nội bộ, release chậm |
| Service quá nhỏ | Mỗi CRUD/action thành một service | Nhiều network hops, orchestration và on-call |
| Capability cohesive | Một business responsibility rõ | Có thể tạo ownership và contract ổn định |
| Shared utility service | Dùng chung nhiều nơi nhưng không có owner/SLI rõ | Trở thành bottleneck và điểm lỗi chung |

### 7.4. Độ hạt là quyết định theo context

Một Payment domain có thể cần một service duy nhất ban đầu. Khi workload và ownership trưởng thành, có thể tách Payment Authorization, Settlement và Refund nếu chúng có invariants, data lifecycle và operational needs khác biệt. Cũng có thể giữ chúng trong một service nếu thay đổi thường xuyên cùng nhau và transaction/consistency cần gần nhau.

## 8. Integration: ESB và vai trò của integration platform

**Enterprise Service Bus (ESB)** là một kiểu integration middleware hỗ trợ định tuyến, chuyển đổi message, protocol mediation và đôi khi orchestration giữa các ứng dụng/service.

Một sơ đồ điển hình:

~~~text
CRM ──SOAP/XML──┐
ERP ──JMS───────┼──► ESB ──► Customer Service
Billing ──FTP───┤       ├──► Order Service
Legacy ──DB link┘       └──► Notification
~~~

ESB hữu ích khi tổ chức phải tích hợp nhiều hệ thống legacy, nhiều protocol và message format khác nhau, hoặc cần một điểm quản lý transformation/routing tập trung.

### 8.1. Những chức năng thường thấy

- Protocol mediation: SOAP, JMS, HTTP, file transfer.
- Message transformation: XML↔JSON, field mapping, code translation.
- Routing: chọn endpoint theo message/header/business rule.
- Orchestration: điều phối một số workflow.
- Security mediation: identity propagation, policy enforcement.
- Monitoring/audit: theo dõi message và integration flows.
- Adapter/connectors tới hệ thống legacy.

Không phải ESB nào cũng cung cấp đầy đủ các chức năng này, và không phải triển khai SOA nào cũng dùng ESB.

### 8.2. Rủi ro của ESB tập trung

Nếu mọi request và business logic đều đi qua một integration hub:

- Hub trở thành bottleneck throughput/latency.
- Một outage có thể ảnh hưởng nhiều capability.
- Transformation rules bị phân tán khỏi service owner.
- Thay đổi nhỏ cần đội middleware phê duyệt.
- Business logic khó test độc lập.
- Debug một workflow cần hiểu cả ESB routes lẫn service implementations.
- Versioning và release trở nên tập trung.

ESB có thể quản lý integration concerns, nhưng không nên âm thầm trở thành nơi sở hữu mọi business rules.

### 8.3. Lightweight integration

Trong nhiều hệ microservices, integration thường phân bố qua:

- API Gateway cho north-south traffic.
- Message broker/event streaming cho asynchronous communication.
- Direct HTTP/gRPC cho request/response.
- Service mesh cho traffic policies, mTLS và telemetry.
- Adapter/anti-corruption layer ở ranh giới legacy.

Các thành phần này vẫn có thể là platform chung; “lightweight” không có nghĩa không cần governance.

## 9. API Gateway khác ESB

| Khía cạnh | API Gateway | ESB/integration middleware |
| --- | --- | --- |
| Vị trí phổ biến | Edge của hệ thống hoặc API boundary | Giữa các ứng dụng/service |
| Tập trung | API exposure và traffic control | Protocol/message integration |
| Chức năng | Routing, auth, rate limit, TLS, request policies | Routing, transformation, mediation, adapters |
| Consumer | Web/mobile/partner/service clients | Ứng dụng/service và legacy systems |
| Payload transformation | Có thể có nhưng nên giới hạn | Có thể là năng lực chính |
| Orchestration | Thường tránh business orchestration phức tạp | Một số sản phẩm hỗ trợ |
| Failure impact | Có thể ảnh hưởng nhiều entry points | Có thể ảnh hưởng nhiều integration paths |

Một API Gateway không tự trở thành ESB chỉ vì có routing. ESB cũng không tự thay API management cho external consumers. Một hệ thống có thể dùng cả hai với boundary rõ.

### 9.1. Gateway không nên chứa domain logic lớn

Ví dụ Gateway xác thực token, route §POST /orders§ tới Order Service và áp rate limit là hợp lý. Nếu Gateway tính discount, cập nhật tồn kho, gọi Payment và ghi Order DB, nó đang trở thành application orchestrator/monolith ở edge.

### 9.2. BFF và API composition

Backend-for-Frontend có thể tổng hợp API cho từng giao diện. BFF phục vụ nhu cầu presentation và aggregation; cần tránh đưa logic authoritative của nhiều domain vào một lớp không có ownership rõ.

## 10. SOA governance và microservices governance

SOA ở cấp enterprise thường chú trọng chuẩn hóa và kiểm soát interface dùng chung:

- Service registry/catalog.
- Naming và schema conventions.
- Enterprise canonical data models.
- API lifecycle/versioning.
- Security policies.
- Reuse và duplication control.
- Integration standards.
- Approval cho các capability dùng chung.

Microservices thường muốn trao nhiều quyền quyết định hơn cho team:

- Team tự thiết kế API/event trong guardrails.
- Team sở hữu service SLO và on-call.
- CI/CD tự động kiểm contract/security.
- Platform cung cấp default patterns.
- Architecture review tập trung vào boundary, risk và shared standards.
- Consumer/provider phối hợp versioning theo deprecation window.

### 10.1. Tập trung quá mức

Một enterprise architecture board phê duyệt từng field hoặc từng endpoint có thể làm lead time tăng và khiến teams không thể thử nghiệm. Nếu service mới phải chờ nhiều tuần chỉ để đổi optional field, governance trở thành bottleneck.

### 10.2. Phân tán quá mức

Ngược lại, nếu mỗi team tự định nghĩa identity, currency, timestamp, error semantics và trace propagation khác nhau, tích hợp trở nên khó khăn. Microservices vẫn cần chuẩn chung cho những concerns xuyên tổ chức.

### 10.3. Guardrails thay vì kiểm duyệt mọi quyết định

Một cách cân bằng:

- Chuẩn bắt buộc cho security, identity, audit, data classification và contract compatibility.
- Golden paths cho runtime, logging, tracing, CI/CD và secrets.
- Quyền tự chủ cho domain modeling và implementation.
- Review sâu khi thay đổi ảnh hưởng nhiều teams, dữ liệu nhạy cảm hoặc public contract.
- Architecture Decision Records cho lựa chọn có tác động lâu dài.

## 11. Data ownership và database coupling

### 11.1. Một kiểu SOA truyền thống có thể có shared data services

Một số triển khai enterprise dùng Customer Master hoặc Product Master làm nguồn dữ liệu chung, với nhiều hệ thống tích hợp qua interface. Đây có thể là cách hợp lý để quản lý master data, nhưng cần quản lý load, availability và data semantics.

### 11.2. Microservices nhấn mạnh database ownership

Mỗi service có quyền kiểm soát schema và write path của dữ liệu authoritative. Service khác dùng API/event hoặc projection; không query trực tiếp bảng nội bộ.

~~~text
Customer Service → Customer DB
Order Service    → Order DB
Payment Service  → Payment DB
Inventory Service→ Inventory DB
~~~

### 11.3. Không bắt buộc mỗi service một database server

Các service có thể dùng chung cluster vật lý nhưng tách database/schema, roles, grants, migrations và ownership. Physical isolation tăng khi cần capacity/security/failure boundaries khác nhau.

### 11.4. Canonical data model

SOA integration có thể dùng canonical model để giảm số mapping giữa nhiều ứng dụng. Ví dụ mỗi hệ thống chuyển về một Customer schema chung trước khi trao đổi.

Ưu điểm là giảm mapping bùng nổ. Rủi ro là canonical model quá lớn và khó thay đổi, làm mọi domain phải chờ một mô hình enterprise duy nhất.

Trong microservices, contract thường được thiết kế quanh bounded context; có thể chia sẻ những value standards (currency, time, identifiers) nhưng tránh một global DTO ép mọi domain cùng semantics.

### 11.5. Khi nào canonical model có lợi?

- Có nhiều legacy systems với schema khác nhau.
- Dữ liệu master cần governance tập trung.
- Tích hợp partner yêu cầu một format thống nhất.
- Tổ chức có năng lực steward và quy trình schema evolution.
- Model đủ ổn định và có owner.

### 11.6. Khi nào canonical model trở thành gánh nặng?

- Mọi domain phải dùng cùng một entity dù ý nghĩa khác nhau.
- Mỗi thay đổi cần phê duyệt toàn doanh nghiệp.
- Model chứa nhiều optional fields và enum khó hiểu.
- Consumer phụ thuộc vào field không liên quan.
- Release contract bị khóa bởi một nhóm trung tâm.

## 12. Synchronous và asynchronous integration

Cả SOA và microservices đều có thể dùng hai kiểu giao tiếp.

### 12.1. Request/response

~~~text
Order Service ──HTTP/gRPC──► Payment Service
       │                           │
       │◄──── AuthorizationResult ─┘
~~~

Phù hợp khi caller cần kết quả để tiếp tục một quyết định ngay. Ví dụ kiểm tra quyền, tính giá, authorize payment.

Ưu điểm:

- Flow dễ hiểu với request đơn giản.
- Caller nhận response trực tiếp.
- Contract dễ thể hiện status/result.
- Phù hợp với thao tác cần feedback ngay.

Rủi ro:

- Runtime coupling.
- Latency cộng dồn và tail latency.
- Provider unavailable có thể làm caller lỗi.
- Retry amplification.
- Call chain sâu.
- Transaction xuyên service không tự động atomic.

### 12.2. Message/event

~~~text
Order Service ──OrderCreated──► Broker
                                  │
                     ┌────────────┼────────────┐
                     ▼            ▼            ▼
                Fulfillment   Notification  Analytics
~~~

Phù hợp khi consumer có thể xử lý sau, cần fan-out hoặc producer không muốn phụ thuộc availability của tất cả consumers.

Ưu điểm:

- Producer và consumer tách thời điểm xử lý.
- Hấp thụ burst qua queue.
- Fan-out cho nhiều consumers.
- Dễ mở rộng read models và integration flows.

Rủi ro:

- Eventual consistency.
- Duplicate/out-of-order delivery.
- Schema evolution.
- Queue lag và DLQ.
- Debug workflow khó hơn.
- Cần idempotency, replay và ownership.

### 12.3. Chọn theo semantics

Không chọn asynchronous chỉ vì nó “hiện đại”. Nếu người dùng cần xác nhận ngay một thao tác bắt buộc, cần contract response/operation status rõ. Nếu email xác nhận có thể gửi sau, event phù hợp hơn.

### 12.4. Hybrid integration

Một checkout có thể dùng API đồng bộ để authorize/validate và event bất đồng bộ để gửi email, cập nhật analytics. Kiến trúc tốt chọn giao thức theo từng business operation, không áp dụng một cơ chế duy nhất cho mọi edge.

## 13. Orchestration và choreography

### 13.1. Orchestration

Một orchestrator điều khiển thứ tự workflow:

~~~text
Checkout Orchestrator
   ├──► Inventory.reserve()
   ├──► Payment.authorize()
   ├──► Order.confirm()
   └──► Fulfillment.start()
~~~

Ưu điểm:

- Workflow tập trung dễ nhìn.
- Thứ tự, timeout và compensation rõ hơn.
- Có nơi quản lý trạng thái tiến trình.
- Dễ biểu diễn approval/human steps.

Rủi ro:

- Orchestrator có thể trở thành central business bottleneck.
- Logic điều phối phình to.
- Services bị phụ thuộc vào một workflow coordinator.
- Orchestrator phải có persistence/recovery.

### 13.2. Choreography

Các service phản ứng với event:

~~~text
OrderCreated
    │
    ▼
Inventory reserves stock
    │
    ▼
InventoryReserved
    │
    ▼
Payment authorizes
    │
    ▼
PaymentAuthorized
    │
    ▼
Order confirms
~~~

Ưu điểm:

- Producer không cần biết mọi consumer.
- Dễ fan-out và mở rộng event consumers.
- Tránh một orchestrator quá lớn.
- Domain events thể hiện facts đã xảy ra.

Rủi ro:

- Workflow phân tán khó thấy.
- Event cycles/feedback loops.
- Cần quản lý correlation, timeout, retries và compensation.
- Business process có thể khó thay đổi nếu consumers ẩn nhiều.

### 13.3. SOA và microservices đều có thể dùng cả hai

Không nên gắn “SOA = orchestration, microservices = choreography” như một quy tắc. Một SOA có thể event-driven; một hệ microservices có thể dùng saga orchestrator. Quyết định phụ thuộc độ phức tạp workflow và nhu cầu kiểm soát.

### 13.4. Chọn một kiểu theo workflow

- Workflow tuyến tính, cần audit và trạng thái rõ: orchestration có thể phù hợp.
- Event fan-out, consumers độc lập: choreography phù hợp.
- Workflow dài, có human approval/compensation: durable orchestrator hoặc workflow engine có thể hữu ích.
- Đơn giản một lời gọi: API trực tiếp là đủ.

## 14. Ví dụ tích hợp doanh nghiệp: CRM, ERP và Billing

Một doanh nghiệp có:

- CRM quản lý khách hàng và cơ hội bán hàng.
- ERP quản lý đơn mua, kho và kế toán.
- Billing quản lý hóa đơn.
- Customer Portal cho khách hàng.
- Data Warehouse phục vụ báo cáo.

Một integration architecture kiểu SOA:

~~~text
CRM ─────────────┐
ERP ─────────────┼──► Integration Platform / ESB
Billing ─────────┤          │
Portal ──────────┘          ├── Customer Master
                            ├── Order Capability
                            ├── Invoice Capability
                            └── Reporting Feed
~~~

ESB/adapters có thể chuyển đổi schema của CRM/ERP và route message. Các service capability cần owner, SLA và contract rõ.

### 14.1. Khi cách này có lợi

- Hệ thống legacy có protocol và data formats khác nhau.
- Nhiều ứng dụng cần tích hợp theo quy trình enterprise.
- Có một nhóm integration chuyên môn.
- Data master và audit requirements được quản trị tập trung.
- Thay thế toàn bộ legacy một lần là không khả thi.

### 14.2. Những điểm cần bảo vệ

- ESB không được giữ toàn bộ domain logic không rõ owner.
- Shared Customer capability cần capacity/SLO phù hợp.
- Transformation mappings phải versioned.
- Không cho phép integration flows ghi trực tiếp vào mọi database.
- Monitoring phải có correlation qua từng hop.
- Phải có kế hoạch thay thế connector/adapter legacy.

## 15. Ví dụ microservices: thương mại điện tử cloud-native

~~~text
Web/Mobile
    │
API Gateway
    │
    ├──► Catalog Service ──► Catalog DB
    ├──► Cart Service ─────► Cart Store
    ├──► Order Service ────► Order DB
    ├──► Inventory Service ► Inventory DB
    └──► Payment Service ──► Payment DB
                   │
                   ▼
               Event Broker
                ├──► Fulfillment
                ├──► Notification
                └──► Analytics
~~~

Các team có thể sở hữu domain/service và deploy theo nhịp riêng. Platform hỗ trợ Kubernetes, CI/CD, secrets, observability, schema registry và traffic management.

### 15.1. Lợi ích tiềm năng

- Order có thể deploy mà không release Catalog nếu contract tương thích.
- Inventory scale theo lượng reservation.
- Notification worker scale theo queue lag.
- Payment có security/compliance controls riêng.
- Một service lỗi có thể được cô lập nếu timeout/fallback đúng.

### 15.2. Chi phí phải quản lý

- Nhiều deployments và runtime resources.
- Data consistency/eventual consistency.
- Distributed tracing và incident response.
- Versioning, retries, idempotency.
- Network/security configuration.
- Platform/observability cost.
- Team capacity và on-call.

Không có nền tảng tự động hóa và ownership đủ tốt, hệ thống này có thể tốn kém hơn một modular monolith.

## 16. Governance: central standards và team autonomy

### 16.1. Enterprise standards

Các chuẩn thường nên thống nhất:

- Identity và service authentication.
- Encryption, secrets, certificate lifecycle.
- Audit/logging requirements.
- Data classification và retention.
- API/event schema compatibility.
- Error semantics và correlation IDs.
- SLO/incident severity.
- Network segmentation và threat modeling.
- Approved runtime/security baseline.

### 16.2. Những thứ có thể để domain teams quyết định

- Domain model và aggregate boundaries.
- Internal data schema.
- Implementation language trong approved choices.
- Sync/async theo use case.
- Release cadence.
- Internal library và testing strategy.
- Cache/read model design.
- Feature flags và rollout policy.

### 16.3. Governance theo rủi ro

Public API, payment data, identity, cross-region PII hoặc breaking event schema cần review sâu hơn một internal optional field. Guardrails nên tự động kiểm tra những điều có thể kiểm tra, tránh biến mọi quyết định thành cuộc họp.

### 16.4. Service catalog và contract registry

Dù SOA hay microservices, tổ chức cần biết:

- Service có chức năng gì.
- Owner team/on-call.
- API/event contracts.
- Consumers và criticality.
- SLO, dashboards và runbooks.
- Data classification và dependencies.
- Version/deprecation lifecycle.

Catalog giúp giảm “service sprawl” và tìm đúng người khi có incident.

## 17. API lifecycle và versioning

Một contract service có vòng đời:

~~~text
Design → Publish → Adopt → Evolve → Deprecate → Retire
~~~

Cả SOA và microservices cần:

- Version rõ ràng.
- Backward compatibility.
- Consumer/provider contract tests.
- Deprecation window.
- Change notification.
- Migration guide.
- Usage telemetry.
- Owner và ngày retire.

### 17.1. Versioning không chỉ là /v1 và /v2

Có thể version qua URL, media type, schema registry subject, event schema version hoặc compatibility policy. Điều quan trọng là consumer biết contract nào đang dùng và cách nâng cấp.

### 17.2. Additive change cũng có thể phá consumer

Thêm field optional có thể phá strict JSON parser. Thêm enum value có thể làm consumer switch không có default. Đổi semantics hoặc unit có thể nguy hiểm dù schema vẫn parse.

### 17.3. Shared canonical schema

Trong enterprise integration, canonical schema có thể giảm mapping nhưng dễ trở thành bottleneck. Trong microservices, domain-specific contract giảm coupling semantics; cần một số shared primitives có kiểm soát như currency/time/identifiers.

## 18. Service discovery và registry

### 18.1. Service registry

Một registry có thể lưu service endpoints, contracts, owner và metadata. Trong SOA, registry có thể được quản trị ở cấp enterprise để consumers tìm capability.

### 18.2. Runtime discovery

Trong Kubernetes, service DNS/Endpoints/EndpointSlices hoặc service mesh có thể hỗ trợ discovery và routing. Đây là discovery ở runtime, khác với catalog mô tả ownership/contracts.

### 18.3. Đừng nhầm registry với load balancer

Registry cho biết service hoặc endpoint được công bố. Load balancer chọn backend/route traffic. API catalog giúp developer hiểu contract. Ba chức năng có thể tích hợp trong một platform nhưng khái niệm khác nhau.

### 18.4. Service sprawl

Có quá nhiều service không owner, không consumers rõ, hoặc contract không được duy trì làm discovery khó. Cần lifecycle: create, publish, monitor usage, deprecate và retire.

## 19. Reliability và fault isolation

Cả hai kiến trúc đều cần thiết kế lỗi mạng và dependency.

### 19.1. Timeout và deadline

Mỗi lời gọi cần timeout hợp lý, truyền deadline qua các tầng và dành đủ ngân sách cho xử lý/response. Timeout quá dài giữ thread/connections; timeout quá ngắn tạo false failures và retry.

### 19.2. Retry và idempotency

Retry chỉ phù hợp với lỗi có khả năng tạm thời và thao tác an toàn. POST tạo payment/order cần idempotency key hoặc cơ chế dedup tại owner. Retry nhiều tầng có thể nhân tải.

### 19.3. Circuit breaker và bulkhead

Circuit breaker giới hạn calls tới dependency suy giảm. Bulkhead tách concurrency/pools để một dependency không chiếm toàn bộ tài nguyên. Cả hai cần metrics, thresholds và recovery policy phù hợp.

### 19.4. Backpressure và load shedding

Queue có giới hạn, rate limit, concurrency limit và từ chối có kiểm soát giúp bảo vệ downstream. Trả 202 không có nghĩa workflow đã hoàn thành; cần trạng thái pending và SLO phù hợp.

### 19.5. Failure domain

Một ESB trung tâm có thể là điểm lỗi chung nếu không có HA/scale. Một mesh/gateway hoặc broker trong microservices cũng có thể là shared dependency. Số lượng service không tự bảo đảm fault isolation.

## 20. Security và trust boundaries

### 20.1. SOA integration

Một integration platform có thể làm central mediation cho identity, protocol translation và audit. Cần tránh việc mọi service tin ESB quá mức và không kiểm tra authorization phù hợp ở business boundary.

### 20.2. Microservices

Thường dùng workload identity, mTLS/service-to-service authentication, scoped authorization, secrets manager và network policies. Mỗi service cần xác minh caller và tenant context theo contract.

### 20.3. Zero trust

Không mặc định request an toàn chỉ vì nó đi từ mạng nội bộ hoặc qua ESB/service mesh. Xác thực workload, kiểm tra quyền operation và audit vẫn cần ở boundary thích hợp.

### 20.4. Data minimization

Không truyền toàn bộ customer profile hoặc payment data qua integration bus nếu consumer chỉ cần một reference/status. Giảm payload giúp giảm rủi ro và số nơi phải bảo vệ/xóa dữ liệu.

### 20.5. Secrets và key lifecycle

Certificate, token signing keys, provider credentials và secret rotation cần owner, automation và incident process. Một điểm trung tâm cấp secrets có thể hỗ trợ governance nhưng phải có HA và audit.

## 21. Observability xuyên service

Một hệ thống tích hợp tốt phải theo dõi được hành trình end-to-end:

- Trace context/correlation IDs.
- Service name/version/environment.
- Inbound/outbound request rate.
- Error ratio theo operation/dependency.
- p50/p95/p99 latency.
- Saturation: CPU, thread, connection pool, queue.
- Retry attempts, circuit state, DLQ.
- Event lag/freshness.
- Deployment/config annotations.
- SLO và error budget.

### 21.1. Service map không thay data lineage

Service map cho biết ai gọi ai. Data lineage cho biết dữ liệu nào được lấy, biến đổi và lưu ở đâu. Một báo cáo sai có thể do ETL transformation chứ không do runtime service call.

### 21.2. Correlation qua ESB

Nếu ESB nhận message rồi phát một request mới, phải propagate trace/correlation context. Nếu không, trace sẽ bị đứt tại integration layer và khó biết transformation nào làm sai dữ liệu.

### 21.3. Golden signals

Traffic, errors, latency và saturation nên đo ở service boundary và integration edges. Đừng cộng p95 của từng service để suy ra p95 end-to-end; dùng trace/measurement tại user-facing boundary.

## 22. Data consistency và transaction

SOA và microservices đều có thể gặp distributed transaction.

### 22.1. Shared transaction trong legacy SOA

Một số ứng dụng tích hợp có thể dùng XA/distributed transactions hoặc database transaction chung. Chúng có thể hữu ích trong bối cảnh cụ thể nhưng tạo dependency và operational complexity.

### 22.2. Microservices thường ưu tiên local transactions + saga

Mỗi service commit trong data store của mình; workflow liên service dùng event/command và compensation. Điều này làm rõ ownership nhưng chấp nhận trạng thái trung gian/eventual consistency.

### 22.3. Eventual consistency cần business contract

Ví dụ Payment đã authorize nhưng Order projection chưa cập nhật trong 2 giây. UI cần thể hiện PAYMENT_PENDING hoặc xác minh trạng thái, không giả định mọi service cập nhật đồng thời.

### 22.4. Outbox và inbox

Outbox ghi business change và event trong cùng local transaction. Consumer dùng inbox/dedup để xử lý lặp an toàn. Đây là kỹ thuật hữu ích trong microservices, nhưng cũng có thể được dùng trong SOA/event-driven integration.

### 22.5. Exactly-once

Không nên quảng cáo exactly-once end-to-end nếu không chỉ rõ phạm vi và guarantees. Thường cần at-least-once delivery + idempotent consumers + transactional state để đạt kết quả nghiệp vụ đáng tin cậy.

## 23. ESB, broker, event streaming và service mesh: vai trò khác nhau

| Thành phần | Vai trò chính | Ví dụ nhiệm vụ |
| --- | --- | --- |
| ESB/integration platform | Mediation, routing, transformation, adapters | Kết nối SOAP ERP với REST capability |
| Message broker | Delivery và buffering message | RabbitMQ/JMS-style queues |
| Event streaming platform | Durable event log, partitions, replay | Kafka-style event streams |
| API Gateway | Edge routing, auth, quotas, API lifecycle | Public REST APIs |
| Service mesh | East-west traffic policies/telemetry | mTLS, retries, traffic split |
| Service catalog/registry | Discovery metadata và ownership | Tìm endpoint, owner, contract |
| Schema registry | Quản lý schema/version/compatibility | Avro/Protobuf/JSON Schema contracts |
| Workflow engine | Durable process orchestration | Long-running approvals/sagas |

Các công cụ có thể chồng lấn một phần chức năng, nhưng không nên gom tất cả thành “middleware” rồi bỏ qua semantics. Ví dụ broker không tự thực hiện authorization business, service mesh không tự đảm bảo event idempotency, schema registry không tự chứng minh dữ liệu đúng.

## 24. Anti-patterns thường gặp trong SOA

**1. ESB becomes the brain:** business logic phình vào integration bus, service providers trở thành adapter thụ động.

**2. Central canonical model quá lớn:** mọi domain phải chờ một schema duy nhất thay đổi.

**3. Shared database như API:** consumers query/update trực tiếp bảng của provider.

**4. Service reuse cưỡng ép:** một service chung phục vụ mọi use case dù semantics khác nhau, tạo nhiều optional fields và behavior flags.

**5. Central governance thành queue:** mọi thay đổi nhỏ phải qua một nhóm trung tâm.

**6. Point-to-point spaghetti:** mỗi ứng dụng tự kết nối nhiều ứng dụng khác, không có owner/contract.

**7. Integration flow không version:** thay mapping làm consumer lỗi âm thầm.

**8. Không có ownership cho shared service:** nhiều consumers nhưng không ai chịu SLO/capacity.

**9. Protocol-first design:** chọn SOAP/REST/ESB trước khi hiểu business capability và consistency.

**10. Không có end-to-end observability:** khó nối trace/log qua adapter và broker.

## 25. Anti-patterns thường gặp trong microservices

**1. Distributed monolith:** nhiều deployables nhưng phải release cùng lúc.

**2. Nano-services:** tách helper/CRUD quá nhỏ, tăng network hops và on-call.

**3. Shared database writers:** nhiều service sửa cùng authoritative state.

**4. Synchronous call chains sâu:** một request phụ thuộc nhiều service liên tiếp.

**5. Gateway/mesh chứa business logic:** central layer trở thành điểm điều phối và bottleneck.

**6. Event spaghetti:** topic/event không owner, không schema, không correlation.

**7. Copy-paste domain logic:** mỗi service tự diễn giải discount/payment/status khác nhau.

**8. No platform golden path:** mỗi team tự xây CI, security và observability.

**9. No data lifecycle:** projections/caches/exports không có retention hoặc deletion plan.

**10. Microservice count as success metric:** đánh giá kiến trúc theo số process thay vì user outcomes, autonomy và reliability.

## 26. SOA và microservices có thể cùng tồn tại

Một doanh nghiệp lớn có thể có:

- SOA/integration platform để kết nối ERP, CRM và legacy systems.
- Domain services theo microservices cho sản phẩm digital.
- API Gateway cho partner/public APIs.
- Event streaming để phát domain events.
- Data platform cho reporting.
- Master data services cho một số dữ liệu chuẩn.

~~~text
Legacy Enterprise Systems
       │
       ▼
Integration Platform / ESB
       │
       ▼
Domain API / Event Boundary
       │
       ├──► Customer Microservices
       ├──► Order Microservices
       ├──► Payment Microservices
       └──► Fulfillment Microservices
                    │
                    ▼
               Event Platform
                    │
                    ▼
              Analytics / BI
~~~

Điều cần rõ là **ranh giới ownership**: ESB chịu trách nhiệm mediation, domain service chịu trách nhiệm business state, platform chịu trách nhiệm nền tảng, data team chịu trách nhiệm derived datasets.

Không để một integration layer trở thành nơi tất cả teams phải gửi ticket để thực hiện mọi thay đổi.

## 27. Khi nào chọn SOA-style integration?

SOA/integration-oriented approach có thể phù hợp khi:

1. Có nhiều ứng dụng legacy hoặc vendor systems cần kết nối.
2. Doanh nghiệp có các capability dùng chung trên phạm vi rộng.
3. Protocol/data formats rất đa dạng.
4. Có nhu cầu transformation, routing, audit và orchestration tích hợp.
5. Governance, compliance và data standards cần điều phối ở cấp enterprise.
6. Một số systems không thể thay đổi deployment cadence.
7. Tổ chức có đội integration/platform đủ năng lực vận hành.
8. Cần hiện đại hóa từng phần mà không thay toàn bộ landscape.

### 27.1. Ví dụ

Một ngân hàng có core banking legacy, CRM, loan origination, mobile app, fraud engine và reporting. Integration platform giúp chuyển protocol/message và quản lý flows. Các domain service mới có thể được xây theo microservices ở các khu vực có lợi ích rõ.

## 28. Khi nào chọn microservices?

Microservices có thể phù hợp khi:

1. Domain boundaries tương đối rõ và business capability có owner.
2. Nhiều team cần phát triển/release độc lập.
3. Workloads có nhu cầu scale khác nhau.
4. Fault/security isolation có giá trị thực.
5. Platform automation đã đủ trưởng thành.
6. Team có khả năng trực vận hành, observability và xử lý incident.
7. Data ownership và consistency được thiết kế.
8. Contracts/versioning và test automation hoạt động.
9. Lợi ích tốc độ thay đổi/cách ly vượt chi phí distributed systems.

### 28.1. Ví dụ

Một nền tảng thương mại điện tử có traffic biến động lớn: Catalog search, Order, Inventory và Notification có workload khác nhau. Các team domain có thể scale/release theo nhu cầu và sử dụng event-driven integration.

## 29. Khi nào không nên chuyển sang microservices ngay?

Cân nhắc giữ monolith hoặc modular monolith khi:

- Team nhỏ và domain còn thay đổi mạnh.
- Chưa có CI/CD, observability, secrets/IAM hoặc on-call nền tảng.
- Business logic đang thay đổi cùng nhau.
- Chưa rõ data ownership.
- Workload chưa cần scale độc lập.
- Hầu hết requests vẫn cần transaction chung.
- Nhiều services sẽ chỉ là wrappers của cùng một DB.
- Hệ thống chưa có năng lực xử lý event consistency/replay.
- Chưa có lý do rõ để chấp nhận network failures.

Một modular monolith có boundaries tốt có thể là bước tiến kiến trúc có giá trị, và có thể là kiến trúc đích phù hợp lâu dài.

## 30. So sánh về tổ chức và team ownership

| Khía cạnh | SOA enterprise pattern | Microservices pattern |
| --- | --- | --- |
| Service provider | Có thể là shared service team hoặc domain team | Thường là stream/domain team |
| Consumer | Nhiều ứng dụng/team | Nhiều service/clients |
| Integration team | Có thể vận hành ESB/adapters | Platform/integration enablement |
| Release ownership | Có thể phối hợp enterprise cadence | Nhấn mạnh team-owned release |
| On-call | Có thể phân tầng theo shared platform/service | Team sở hữu service và SLO |
| Governance | Có thể tập trung nhiều hơn | Guardrails, automation và team autonomy |
| Reuse | Shared capability là mục tiêu phổ biến | Reuse qua stable contracts, tránh shared bottleneck |
| Team cognitive load | Phụ thuộc governance/integration tooling | Phụ thuộc số services, dependencies và platform maturity |

### 30.1. Team Topologies và microservices

Stream-aligned team có thể sở hữu domain/service; platform team cung cấp golden paths; enabling team giúp nâng năng lực; complicated-subsystem team quản lý subsystem chuyên sâu.

Mô hình này giúp giảm handoffs nhưng không yêu cầu mỗi microservice một team. Một team có thể sở hữu nhiều services cohesive; một service shared có thể có một primary owner với consumer contracts rõ.

### 30.2. SOA và shared capability ownership

Một Customer Master hoặc Integration Platform có thể phục vụ nhiều teams. Đội owner cần sản phẩm nội bộ với SLO, roadmap, API lifecycle, capacity và support model. Nếu chỉ là một hàng đợi ticket, reuse tạo bottleneck.

## 31. So sánh deployment và release

### 31.1. SOA

Các service có thể deploy độc lập, nhưng trong một số enterprise environments còn bị ràng buộc bởi:

- Release windows.
- Shared schema changes.
- Integration test cycles.
- Vendor/legacy maintenance.
- Central approvals.
- Enterprise-wide canonical contract.

Đây là constraints của cách triển khai/governance, không phải đặc tính bắt buộc của SOA.

### 31.2. Microservices

Mục tiêu là deploy độc lập:

- CI/CD cho từng service.
- Backward-compatible API/events.
- Database migration do owner kiểm soát.
- Canary/blue-green và rollback.
- Independent scaling.
- SLO và monitoring riêng.

Nếu contract thay đổi phá consumer hoặc nhiều service cùng release, independence chỉ tồn tại trên sơ đồ.

### 31.3. Deployment independence cần compatibility

Producer nên expand schema, consumer nâng cấp, rồi mới deprecate field cũ. Event consumers có thể xử lý event cũ được replay sau nhiều ngày/tháng. Cần compatibility tests và migration plan.

## 32. Performance và scaling

### 32.1. SOA shared services

Một shared Customer/Identity/Billing service có thể nhận traffic từ nhiều ứng dụng. Cần:

- Capacity planning theo tổng consumers.
- Rate limits và quotas theo consumer.
- Cache/read models.
- Bulkhead và tenant isolation.
- SLO theo operation.
- Upgrade/deploy coordination khi cần.

Một service dùng chung có thể là bottleneck dù business logic đơn giản.

### 32.2. Microservices independent scaling

Có thể scale Order worker theo queue lag, Catalog theo search traffic, Notification theo event backlog. Nhưng tổng throughput vẫn bị giới hạn bởi DB, broker, provider quotas và network.

### 32.3. Scaling không phải lúc nào cũng tuyến tính

Thêm replicas có thể tăng DB connections, cache misses và retries. Nếu downstream bão hòa, scale app có thể làm sự cố tệ hơn. Cần đo capacity end-to-end và giới hạn concurrency.

### 32.4. Multi-tenancy

SOA shared service thường cần quotas và fair usage giữa các ứng dụng/tenants. Microservices cũng cần tenant isolation, data partitioning, noisy-neighbor controls và authorization. Không có kiến trúc nào tự giải quyết vấn đề này chỉ bằng service boundary.

## 33. Migration từ SOA sang microservices

Không nên bắt đầu bằng việc thay ESB bằng Kafka hoặc chia mọi service thành nhỏ hơn. Trước hết xác định **pain point cụ thể**:

- Shared service không thể release độc lập?
- ESB transformation phình to và khó ownership?
- Một capability cần scale khác?
- Shared database làm schema changes rủi ro?
- Team phải chờ central integration team?
- Failure isolation chưa đạt SLO?
- Legacy protocol đang cản product delivery?

### 33.1. Lập inventory

- Applications và service contracts.
- ESB routes/adapters/transformations.
- Service owners/consumers.
- Shared database readers/writers.
- Scheduled jobs và external partners.
- SLO, traffic, latency và incidents.
- Data classification, retention và audit.

### 33.2. Chọn một bounded context có lợi ích rõ

Ví dụ tách Notification khỏi integration flow vì nó có workload async, retry và provider quotas riêng. Không bắt buộc tách Customer Master nếu nó vẫn là capability dùng chung có governance tốt.

### 33.3. Tạo owner service

- Domain model và SoR.
- API/event contracts.
- Database/schema ownership.
- CI/CD và observability.
- IAM/secrets.
- SLO/runbook/on-call.
- Consumer migration plan.

### 33.4. Dùng strangler pattern

~~~text
Consumers
    │
    ▼
Routing Boundary
   ├──► Legacy SOA capability
   └──► New microservice
              │
              ▼
          New data store
~~~

Chuyển operation/consumer theo từng giai đoạn. Đảm bảo một writer authoritative cho từng operation và có reconciliation.

### 33.5. Giữ integration platform ở nơi có giá trị

ESB/adapters vẫn có thể là cầu nối tới ERP, mainframe hoặc partner. Có thể thay từng flow bằng API/event khi có owner và contract mới. Không cần “xóa ESB” như một mục tiêu độc lập.

## 34. Migration từ monolith sang SOA hoặc microservices

Một monolith có thể cần integration layer khi mở rộng tới nhiều ứng dụng, hoặc có thể trích bounded contexts thành services.

Các bước:

1. Xác định domain và business capabilities.
2. Vẽ module/data dependencies.
3. Làm rõ ownership và SoR.
4. Modularize trong codebase trước nếu boundaries còn yếu.
5. Tạo public interface/contracts.
6. Tách một capability có lợi ích rõ.
7. Xử lý data migration và event/API integration.
8. Xây automation/observability/on-call.
9. Đo lead time, SLO và operational cost.
10. Tiếp tục chỉ khi lợi ích thực tế vượt overhead.

### 34.1. Không chia theo bảng CRUD

Một bảng mới không tự tạo ra business service. Cần xem invariants, lifecycle và ai quyết định dữ liệu. Một capability có thể gồm nhiều tables; một bảng legacy có thể chứa data của nhiều contexts.

### 34.2. Không tách vì sơ đồ cần đẹp

Một kiến trúc tốt giải quyết constraint thật. Nếu modular monolith hiện tại đáp ứng delivery, scale và reliability, thêm distributed boundaries có thể giảm chất lượng tổng thể.

## 35. Data migration và coexistence

Trong giai đoạn SOA và microservices cùng tồn tại, có thể có:

- Legacy master database.
- New owner database.
- CDC/outbox replication.
- Shadow reads.
- Consumer adapters.
- API facade.
- Event translation layer.

Cần quản lý:

- Single writer.
- Watermarks/checkpoints.
- Backfill/replay.
- Schema compatibility.
- Duplicate/out-of-order.
- Audit và deletion propagation.
- Rollback sau cutover.

**Không dual-write hai database một cách tùy tiện**; hai commits độc lập có thể divergence. Chọn một authoritative path và cơ chế replication có thể đối soát.

## 36. Chuyển từ ESB-centric sang event/API integration

Một số tổ chức muốn giảm logic trong ESB và chuyển trách nhiệm về domain services.

### 36.1. Trước

~~~text
CRM ──► ESB
         ├─ validate customer
         ├─ apply billing rules
         ├─ transform order
         └─ update inventory
~~~

Nếu ESB chứa cả business rules, khó biết domain owner là ai.

### 36.2. Sau

~~~text
CRM ──► Integration Adapter ──► Customer/Order APIs
                                      │
                                      ▼
                                  Domain Events
                                      │
                                      ▼
                              Billing/Inventory
~~~

Integration adapter tập trung mapping protocol/schema và legacy concerns; business rules thuộc domain owner. Nhưng nếu logic transformation phức tạp thực chất là business decision, cần chuyển tới đúng domain chứ không chỉ đổi vị trí code.

### 36.3. Tách dần

- Phân loại routes: protocol mediation, data transformation, business orchestration.
- Xác định owner từng rule.
- Tách logic nghiệp vụ vào domain service.
- Giữ adapters cho legacy protocols.
- Contract-test cả đường cũ và mới.
- Canary routing.
- Đo latency, errors và reconciliation.
- Retire routes không còn consumers.

## 37. Đánh giá kiến trúc bằng tiêu chí có thể đo

Không dùng số microservices hoặc số API endpoints làm thước đo thành công.

### 37.1. Delivery

- Lead time từ yêu cầu tới outcome.
- Tỷ lệ changes cần phối hợp nhiều teams.
- Deployment frequency và change failure rate.
- Thời gian chờ integration/contract approvals.
- Khả năng rollback độc lập.

### 37.2. Reliability

- User-facing SLI/SLO.
- p95/p99 latency.
- Incident severity và recovery time.
- Retry amplification, dependency failure.
- Queue lag/freshness.
- Failure blast radius.

### 37.3. Ownership và autonomy

- Service có primary owner không?
- Team có quyền deploy/debug/on-call?
- Data SoR rõ không?
- Direct DB access xuyên domain còn bao nhiêu?
- Contract compatibility tests có chạy không?
- Có service orphan hoặc dependency không owner?

### 37.4. Cost và complexity

- Hạ tầng/runtime cost.
- Observability storage và cardinality.
- Pipeline/support toil.
- Number of technology stacks.
- Context switches và handoffs.
- Platform ticket lead time.

### 37.5. Diễn giải cẩn trọng

Một hệ SOA có 20 shared services nhưng contract ổn định, owners rõ và tích hợp legacy tốt có thể hiệu quả. Một hệ microservices có 80 deployables nhưng không có autonomy có thể tốn kém. Đánh giá theo business outcomes và operational evidence.

## 38. Ví dụ quyết định: tích hợp ERP hay xây ERP microservices?

Một công ty có ERP vendor-managed, CRM nội bộ và website. Nhu cầu là đồng bộ trạng thái đơn, tồn kho và hóa đơn.

**Phương án A:** integration platform kết nối ERP/CRM/website qua adapters, mapping và events.

Phù hợp khi ERP không thể thay đổi, nhiều protocol, cần audit và integration flows rõ.

**Phương án B:** xây các domain microservices Order/Inventory/Billing và thay ERP từng phần.

Phù hợp khi có lý do product/scale/ownership dài hạn, đội đủ năng lực domain và kế hoạch migration data.

**Phương án C:** hybrid.

Giữ ERP làm SoR cho một số finance processes; microservices sở hữu digital order/checkout; integration platform chuyển đổi dữ liệu và event.

Cần quyết định:

- Dữ liệu nào ERP vẫn là authoritative?
- Khi nào order được coi là confirmed?
- Inventory reservation nằm ở đâu?
- Invoice status được đối soát như thế nào?
- Nếu integration platform offline, queue/replay ra sao?
- Ai chịu SLO end-to-end?
- Có dual writers hoặc race conditions không?

Không nên tuyên bố “đã chuyển sang microservices” nếu ERP vẫn là nơi quyết định hầu hết state và domain services chỉ làm facade.

## 39. Ví dụ lựa chọn: Customer capability dùng chung hay nhiều Customer microservices?

Một enterprise có 12 applications cần Customer data.

### 39.1. Một shared Customer capability

Ưu điểm:

- Một nơi quản lý profile/master data.
- Reuse rules và verification.
- Governance/consistency tập trung.
- Giảm duplicate writers.

Nhược điểm:

- Tổng traffic từ nhiều consumers.
- Có thể trở thành bottleneck.
- Một thay đổi ảnh hưởng nhiều clients.
- Owner team chịu support burden lớn.

### 39.2. Nhiều context-specific services

Customer Identity, Billing Customer, Support Profile và Marketing Audience có thể tách semantics.

Ưu điểm:

- Mỗi domain sở hữu behavior/data riêng.
- Ít ép một model đáp ứng mọi use cases.
- Có thể scale/security riêng.

Nhược điểm:

- Data replication và reconciliation.
- Identity linking/consent phức tạp.
- Event contracts và privacy propagation.
- Khó bảo đảm profile nhất quán nếu ownership mơ hồ.

### 39.3. Phương án kết hợp

Identity/Customer Master giữ authoritative identifiers và verification; Billing, Support và Marketing có context-specific projections/datasets với purpose/access riêng. Không phải mọi consumer đều cần toàn bộ Customer profile.

## 40. Ví dụ lựa chọn: ESB hay message broker?

| Nhu cầu | ESB/integration platform | Broker/event streaming |
| --- | --- | --- |
| Kết nối SOAP legacy và REST | Rất phù hợp khi có adapters/mediation | Cần adapter/bridge bổ sung |
| Protocol transformation | Thường là năng lực chính | Không phải nhiệm vụ cốt lõi |
| Buffer và delivery queue | Có thể hỗ trợ | Là nhiệm vụ chính |
| Event replay/history | Tùy sản phẩm | Event streaming thường phù hợp hơn |
| Fan-out nhiều consumers | Có thể hỗ trợ | Broker/pub-sub phù hợp |
| Schema compatibility | Cần contract tooling | Schema registry có thể hỗ trợ |
| Long-running workflow | Có thể orchestration | Cần workflow engine/consumer logic |
| Business ownership | Cần tránh nhét logic vào hub | Cần owner producer/consumer rõ |

Hai thành phần có thể cùng tồn tại. Broker không thay thế mọi integration adapter, và ESB không tự tạo event sourcing hoặc replay guarantees.

## 41. Checklist lựa chọn SOA, microservices hoặc hybrid

### Bối cảnh tổ chức

- [ ] Có bao nhiêu ứng dụng/legacy systems cần tích hợp?
- [ ] Domain ownership và team boundaries đã rõ chưa?
- [ ] Có platform/integration team và năng lực on-call không?
- [ ] Governance cần tập trung ở mức nào?
- [ ] Có những systems/vendor không thể thay đổi không?

### Mục tiêu sản phẩm

- [ ] Cần tái sử dụng capability enterprise hay tăng autonomy theo domain?
- [ ] Các workload có nhu cầu scale khác nhau?
- [ ] Có yêu cầu release độc lập?
- [ ] Fault/security isolation mang lại lợi ích đo được?
- [ ] SLO nào quan trọng ở user journey?

### Dữ liệu và tích hợp

- [ ] Source of truth cho từng domain rõ?
- [ ] Consumers cần current data, event hay analytics projection?
- [ ] Shared database/direct SQL coupling ở đâu?
- [ ] Có canonical data model và ai sở hữu nó?
- [ ] Sync/async phù hợp semantics?
- [ ] Retry/idempotency/order/freshness được thiết kế?

### Nền tảng và vận hành

- [ ] CI/CD, observability, secrets, service discovery đủ trưởng thành?
- [ ] ESB/broker/gateway có HA và capacity?
- [ ] Service catalog và contract registry có owner?
- [ ] Incident response xuyên service có runbooks/traces?
- [ ] Backup/restore và RTO/RPO rõ?

### Chi phí và đánh đổi

- [ ] Tổng chi phí deployment boundaries đã được tính?
- [ ] Governance có tạo queue không?
- [ ] Team autonomy có thực sự tăng?
- [ ] Có thể giải quyết bằng modular monolith hoặc adapter thay vì tách service?
- [ ] Có plan migration, rollback và review sau khi triển khai?

## 42. Anti-patterns khi chuyển đổi SOA sang microservices

**1. Chia ESB routes thành một service cho mỗi route.**  
Một route không tự tạo business boundary. Có thể chỉ làm tăng số deployments.

**2. Giữ business logic trong ESB nhưng tuyên bố domain đã tự chủ.**  
Owner service không thể thay đổi behavior nếu mọi rule vẫn nằm trong integration layer.

**3. Chuyển shared DB thành nhiều DB nhưng vẫn ghi chéo.**  
Physical separation không sửa ownership nếu credentials và write paths vẫn chồng lấn.

**4. Dùng event cho mọi integration.**  
Một số operation cần request/response và kết quả ngay; event thêm consistency và replay complexity.

**5. Tạo canonical schema khổng lồ.**  
Mọi domain bị khóa bởi một model chung không phản ánh semantics riêng.

**6. Tạo microservices mà không có platform.**  
Team phải tự xây CI, logs, IAM và deploy, làm cognitive load tăng mạnh.

**7. Dùng API Gateway thay toàn bộ ESB.**  
Gateway không tự cung cấp các adapters, transformation và workflow guarantees cần thiết.

**8. Bỏ ESB ngay trong một lần cutover.**  
Legacy systems và partner integrations có thể bị ảnh hưởng; nên chuyển theo capability/operation.

**9. Tách team theo service count.**  
Một feature có thể phải đi qua nhiều nhóm, tạo handoffs và ownership gaps.

**10. Không đo lợi ích.**  
Số services tăng nhưng lead time, SLO, autonomy và cost không cải thiện.

## 43. Bài tập thực hành

### Bài A — Phân loại kiến trúc

Một công ty có CRM, ERP và Billing tích hợp qua middleware chuyển XML sang JSON. Billing Service được 8 ứng dụng gọi, một team quản lý contract và release hàng tháng.

**Hỏi:** đây có thể là SOA không?

**Gợi ý:** có nhiều đặc điểm SOA/integration-oriented. Không thể chỉ dựa middleware; xem service contracts, reuse, ownership và governance.

### Bài B — Phân loại microservices

Một hệ thống có 20 Spring Boot apps, nhưng tất cả đọc/ghi một PostgreSQL schema, phải deploy cùng lúc và dùng chung credential.

**Hỏi:** có phải microservices architecture tốt không?

**Gợi ý:** có nhiều processes nhưng data/deployment coupling cao; có nguy cơ distributed monolith. Cần làm rõ ownership và contracts.

### Bài C — ESB hay API Gateway?

Mobile app gọi Order API, cần auth, rate limit và route theo path. ERP gửi SOAP messages cần chuyển đổi thành domain events.

**Gợi ý:** API Gateway phù hợp mobile edge; integration adapter/ESB phù hợp SOAP mediation. Có thể dùng cả hai.

### Bài D — Canonical model

Customer trong CRM có lead status; Customer trong Billing có credit status; Customer trong Support có case history.

**Hỏi:** có nên gom tất cả vào một Customer schema chung?

**Gợi ý:** chia semantics theo bounded contexts, có canonical identifiers và các shared attributes có owner. Không ép business concepts khác nhau thành một enum/status.

### Bài E — Chọn sync hay async

Checkout cần xác nhận Payment authorization; Email xác nhận có thể gửi sau vài giây.

**Gợi ý:** authorization cần request/response hoặc workflow status rõ; email có thể event-driven. Định nghĩa idempotency và pending states.

### Bài F — Shared capability bottleneck

Customer service dùng chung nhận traffic từ 15 apps, p99 tăng sau khi onboarding một consumer mới.

**Gợi ý:** đo per-consumer traffic/quotas, cache/read models, capacity, workload isolation và contract. Không vội tạo 15 Customer services trùng logic.

### Bài G — Migration từ ESB

ESB đang chứa discount calculation, inventory reservation và XML transformation.

**Hỏi:** chuyển toàn bộ sang microservices thế nào?

**Gợi ý:** phân loại protocol mapping với business logic; xác định domain owners, tách theo capability, contract/data ownership, canary routing, reconciliation và retire routes theo từng giai đoạn.

### Bài H — Failure isolation

Một microservice gọi qua ESB trung tâm; ESB down khiến toàn bộ checkout fail.

**Hỏi:** đã có fault isolation chưa?

**Gợi ý:** chưa đủ. Đánh giá ESB HA/capacity, alternate routing, async buffering và việc dependency trung tâm có thực sự cần trên critical path.

### Bài I — Chọn modular monolith

Startup có 5 kỹ sư, domain checkout còn thay đổi mỗi tuần, chưa có observability platform.

**Gợi ý:** modular monolith có domain boundaries rõ có thể phù hợp. Tách service khi autonomy/scale/isolation mang lợi ích thực và đội có khả năng vận hành.

### Bài J — Hybrid enterprise

ERP vẫn là SoR cho invoices, Order microservice sở hữu checkout lifecycle, ESB kết nối ERP và broker phát events cho analytics.

**Hỏi:** có mâu thuẫn không?

**Gợi ý:** không. SOA integration và microservices có thể cùng tồn tại nếu ownership, contracts, consistency và incident responsibilities rõ.

## 44. Runbook: đánh giá một integration path mới

1. Xác định business capability và user journey cần tích hợp.
2. Ghi producer, consumer, owner và data authority.
3. Chọn sync request/response, message, event, CDC hoặc batch theo semantics.
4. Định nghĩa contract, schema/version và compatibility.
5. Xác định authn/authz, tenant, classification và audit.
6. Đặt timeout/deadline/retry/idempotency/ordering.
7. Xác định fallback, DLQ, replay và reconciliation.
8. Đo latency/error/traffic/lag và SLO.
9. Thiết kế load test/failure test.
10. Thêm vào service catalog, runbook và ownership map.
11. Review blast radius và shared dependencies.
12. Theo dõi sau release và cập nhật contract consumers.

## 45. Runbook: một integration layer trở thành bottleneck

**Bước 1 — Xác nhận user impact:** SLI, error budget, affected journeys và thời gian.

**Bước 2 — Tách latency theo hop:** caller, integration layer, adapter, provider.

**Bước 3 — Xem saturation:** CPU, queue, threads, connection pools, network và rate limits.

**Bước 4 — Xác định loại lỗi:** routing, transformation, auth, provider timeout, schema mismatch hay capacity.

**Bước 5 — Kiểm tra change events:** route/config/schema/credential/deploy gần incident.

**Bước 6 — Giảm tác động:** rate limit, retry budget, route/failover hoặc queue buffering theo contract.

**Bước 7 — Kiểm tra downstream:** bảo đảm biện pháp không dồn tải sang provider hoặc database.

**Bước 8 — Phục hồi:** xác nhận user SLI, queue lag, DLQ và business outcomes.

**Bước 9 — Cải tiến:** tách business logic sai vị trí, scale adapter, giảm synchronous hops hoặc tạo owner API/event phù hợp.

Không tự động bypass integration layer nếu nó đang thực hiện security/validation bắt buộc.

## 46. Tổng kết

SOA và microservices cùng tổ chức hệ thống quanh service contracts, nhưng thường nhấn mạnh những bài toán khác nhau. **SOA** thường giải quyết việc tích hợp các ứng dụng và business capabilities trong phạm vi enterprise, trong khi **microservices** nhấn mạnh các service theo bounded context có thể được phát triển, triển khai, mở rộng và vận hành với mức tự chủ cao.

Khác biệt không nằm ở một protocol hoặc một middleware duy nhất. ESB có thể hữu ích cho legacy integration; API Gateway quản lý edge traffic; broker/event streaming hỗ trợ asynchronous flows; service mesh quản lý east-west traffic; domain services giữ business rules và authoritative data. Các thành phần có thể cùng tồn tại nếu ownership và contract rõ.

Khi lựa chọn, hãy đánh giá **mục tiêu kinh doanh, domain boundaries, data ownership, team autonomy, governance, integration complexity, platform maturity, reliability và tổng chi phí vận hành**. Một kiến trúc hybrid hoặc modular monolith có thể là lựa chọn đúng trong nhiều giai đoạn. Không nên tăng số microservices chỉ để đạt một hình thức kiến trúc; hãy chọn những ranh giới giúp tổ chức thay đổi an toàn, giảm coupling có ý nghĩa và đáp ứng SLO của người dùng.

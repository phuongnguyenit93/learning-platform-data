# Phân biệt quyết định kiến trúc với lựa chọn framework và nền tảng

> **Lĩnh vực:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Quan hệ kiến trúc (Architecture Relationships)  
> **Mục tiêu:** Phân biệt quyết định kiến trúc có ảnh hưởng lâu dài đến cấu trúc, ranh giới, dữ liệu, luồng điều khiển và thuộc tính chất lượng với lựa chọn framework, thư viện, runtime và nền tảng triển khai; biết cách đánh giá công nghệ dựa trên kiến trúc đã xác định, ghi lại trade-off, quản lý mức độ khó đảo ngược và tránh để công cụ quyết định thay cho bài toán sản phẩm.

## 1. Vì sao cần phân biệt hai loại quyết định?

Khi bắt đầu một hệ thống mới, nhóm thường thảo luận những câu hỏi như:
- Dùng microservices hay modular monolith?
- Dữ liệu nào do service nào sở hữu?
- Giao dịch cần nhất quán đến mức nào?
- Request đồng bộ hay event-driven?
- Có cần cô lập lỗi và scale độc lập không?
- Dùng Spring Boot hay Quarkus?
- Chọn PostgreSQL hay MongoDB?
- Chạy trên Kubernetes hay một nền tảng PaaS?
- Dùng Kafka hay RabbitMQ?

Các câu hỏi này có liên quan nhưng không cùng một cấp. Một số quyết định định hình **cấu trúc và các ràng buộc của hệ thống**; một số lựa chọn **công cụ cụ thể để hiện thực cấu trúc đó**. Nếu gộp chúng thành một cuộc tranh luận “framework nào tốt nhất”, nhóm dễ chọn công nghệ theo xu hướng hoặc sở thích trước khi hiểu nhu cầu thực.

**Quyết định kiến trúc** xác định hệ thống cần có những thành phần, ranh giới, trách nhiệm, luồng tương tác và thuộc tính chất lượng nào. **Lựa chọn framework/nền tảng** xác định công cụ và môi trường nào giúp hiện thực, vận hành các quyết định đó một cách phù hợp.

Ví dụ, “Order sở hữu trạng thái đơn hàng và chỉ Order Service được ghi vào order database” là quyết định về ownership và data boundary. “Dùng Spring Data JPA để truy cập PostgreSQL” là lựa chọn công nghệ triển khai. Có thể đổi JPA sang JDBC mà vẫn giữ ownership; nhưng cho phép Inventory ghi trực tiếp vào bảng Order sẽ thay đổi kiến trúc, dù vẫn dùng Spring Boot và PostgreSQL.

~~~text
Bài toán và mục tiêu sản phẩm
          |
          v
Yêu cầu chức năng, NFR, constraints
          |
          v
Quyết định kiến trúc
- Domain boundaries
- Data ownership
- Interaction / consistency
- Security / reliability
- Deployment independence
          |
          v
Lựa chọn công nghệ phù hợp
- Framework / libraries
- Database / broker
- Runtime / platform
- Build / deploy tools
          |
          v
Implementation and operation
          |
          v
Evidence: outcomes, SLO, cost, changeability
          |
          +---- feedback to architecture decisions
~~~

Framework có thể ảnh hưởng tới kiến trúc vì nó khuyến khích một số cách tổ chức code hoặc runtime. Tuy nhiên, việc framework hỗ trợ một pattern không chứng minh pattern đó phù hợp với sản phẩm. Ngược lại, một quyết định kiến trúc tốt cần xem xét khả năng thực thi thực tế của công nghệ và năng lực vận hành.

## 2. Định nghĩa các khái niệm

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| Business/product decision | Sản phẩm cần đạt điều gì? | Checkout phải xác nhận kết quả trong thời gian cam kết |
| Architecture decision | Hệ thống được cấu trúc và phối hợp thế nào để đạt điều đó? | Payment sở hữu payment state; Order điều phối workflow |
| Design decision | Thành phần cụ thể được thiết kế ra sao? | Dùng strategy để chọn payment provider |
| Technology choice | Dùng công cụ/thư viện nào? | Spring Boot, Hibernate, PostgreSQL |
| Platform choice | Chạy, cấp tài nguyên và vận hành ở đâu/bằng gì? | Kubernetes, managed container platform |
| Configuration choice | Cấu hình công cụ ra sao? | HikariCP pool size, JVM heap, retry timeout |
| Implementation detail | Cài đặt nội bộ thế nào? | Tên class, package, helper method |

Ranh giới không tuyệt đối. Một lựa chọn database có thể là công nghệ ở hệ thống nhỏ nhưng trở thành quyết định kiến trúc nếu nó quyết định partitioning, consistency, data residency, backup, failover và khả năng mở rộng. Một framework có thể là implementation detail ở một module, nhưng là ràng buộc kiến trúc nếu mọi service phải dùng chung lifecycle, serialization hoặc programming model.

Điều cần làm là nêu **tác động và phạm vi của quyết định**, thay vì tranh luận theo nhãn cố định.

### 2.1. Kiến trúc là tập hợp các quyết định và ràng buộc quan trọng

Một quyết định thường được xem là kiến trúc khi nó:
- Ảnh hưởng nhiều thành phần hoặc nhiều nhóm.
- Định hình dependency direction và boundary.
- Tác động tới một hoặc nhiều quality attributes.
- Có chi phí thay đổi đáng kể sau khi nhiều code/dữ liệu đã phụ thuộc.
- Tạo contract lâu dài với consumer, platform hoặc vendor.
- Giới hạn những lựa chọn có thể đưa ra về sau.
- Có tác động lớn đến security, data correctness, reliability hoặc economics.

Không phải mọi quyết định quan trọng đều phải do một “architect” phê duyệt. Người gần domain có thể quyết định; điều quan trọng là quyết định được nhận diện, có owner, được kiểm chứng và có thể tìm lại lý do.

### 2.2. Framework không phải kiến trúc

Spring Boot cung cấp dependency injection, web stack, transaction integration, auto-configuration và nhiều tiện ích. Nhưng Spring Boot không tự quyết định:
- Service boundary đặt ở đâu.
- Ai sở hữu dữ liệu.
- Khi nào dùng synchronous call hay event.
- Giao dịch liên service được phối hợp ra sao.
- Dữ liệu nào được phép stale.
- Blast radius và failure policy là gì.
- Hệ thống cần đáp ứng SLO nào.

Hai ứng dụng cùng Spring Boot có thể có kiến trúc rất khác: một modular monolith, một microservices system, một batch processing platform hoặc một distributed monolith.

### 2.3. Platform không phải kiến trúc đích

Kubernetes cung cấp cơ chế scheduling, service discovery, rollout, resource management và nhiều primitives vận hành. Nó không tự tạo:
- Domain ownership.
- Backward-compatible API.
- Idempotent consumer.
- Data consistency.
- SLO phù hợp.
- Incident ownership.
- Quy trình migration dữ liệu an toàn.

Chạy một monolith trên Kubernetes không biến monolith thành microservices. Dùng service mesh cũng không tự làm các service độc lập nếu chúng vẫn chia sẻ schema, release và business transaction.

## 3. Nhận diện một quyết định kiến trúc bằng tác động

Hãy dùng các câu hỏi sau khi một đề xuất công nghệ xuất hiện:

1. Nó giải quyết vấn đề hoặc quality attribute nào?
2. Nó thay đổi boundary, ownership, dependency hoặc communication không?
3. Nó tạo contract mới với service, client, data store hoặc platform không?
4. Nó tác động tới nhiều team hay chỉ một module?
5. Nó có ảnh hưởng security, privacy, availability, consistency hoặc recovery không?
6. Nếu đổi sau một năm, phải di chuyển dữ liệu, API, người dùng hoặc quy trình nào?
7. Có thể thử nghiệm và rollback nhanh không?
8. Công nghệ có ép tổ chức thay đổi operating model hoặc kỹ năng không?
9. Lợi ích có đo được bằng outcome hay chỉ là tính năng công cụ?
10. Nếu bỏ tên framework/platform khỏi đề xuất, quyết định kiến trúc vẫn có lý do đứng vững không?

Ví dụ:
- “Chọn Kafka vì cần lưu event để nhiều consumer xử lý độc lập, replay theo retention và throughput cao” có một giả thuyết kiến trúc rõ, nhưng vẫn cần so với lựa chọn khác và đo vận hành.
- “Chọn Kafka vì công ty lớn đều dùng” không nêu được nhu cầu.
- “Dùng Kubernetes vì muốn tự động scale mọi service” cần làm rõ loại tải, thời gian scale, resource behavior và chi phí vận hành.
- “Tách Payment thành service vì cần secret isolation, release ownership và failure containment” là giả thuyết kiến trúc có thể kiểm chứng.
- “Tách Payment vì Spring Boot tạo service rất nhanh” chỉ là lý do về công cụ, chưa chứng minh lợi ích của process boundary.

## 4. Phân biệt các tầng quyết định trong một ví dụ

Giả sử hệ thống thương mại điện tử cần xử lý đơn hàng:

| Tầng | Quyết định | Lý do |
|---|---|---|
| Business | Người dùng phải biết đơn đang chờ thanh toán hay đã xác nhận | Tránh hiển thị thành công giả |
| Architecture | Order sở hữu order state; Payment sở hữu payment state | Giữ invariant và ownership |
| Architecture | Workflow nhiều service dùng saga và event | Mỗi service commit local transaction |
| Architecture | API command có idempotency key | Retry không tạo charge/đơn trùng |
| Design | Order state machine có các transition được phép | Ngăn chuyển trạng thái tùy tiện |
| Technology | Spring Boot cho API/application layer | Hợp năng lực Java và ecosystem |
| Technology | PostgreSQL cho transactional state | Constraint, transaction và query phù hợp |
| Technology | Kafka cho event distribution nếu cần retention/replay | Nhiều consumer và throughput |
| Platform | Managed Kubernetes/container platform | Rollout, scaling và isolation |
| Configuration | Timeout, pool size, JVM heap, partition count | Điều chỉnh theo tải và SLO |
| Implementation | Package, class, naming, helper method | Cách hiện thực nội bộ |

Nếu đổi Spring Boot sang một framework Java khác nhưng giữ contract và semantics, phần lớn quyết định kiến trúc vẫn có thể giữ. Nếu đổi từ saga sang một transaction phân tán hoặc cho Order ghi thẳng Payment DB, đó là thay đổi kiến trúc dù framework không đổi.

## 5. Quality attributes phải dẫn dắt kiến trúc và công nghệ

Một đề xuất công nghệ chỉ có ý nghĩa khi gắn với yêu cầu chất lượng cụ thể. Những quality attributes thường cần cân nhắc:

- **Availability:** hệ thống có sẵn sàng phục vụ khi một thành phần lỗi không?
- **Performance:** latency, throughput và tail latency đáp ứng tải không?
- **Scalability:** có thể tăng năng lực theo workload và bottleneck không?
- **Reliability:** hệ thống hoạt động đúng trong thời gian dài và khi lỗi không?
- **Security:** identity, authorization, isolation và secrets được bảo vệ thế nào?
- **Privacy/data governance:** dữ liệu được thu thập, truyền, lưu, xóa ra sao?
- **Modifiability:** thay đổi có ảnh hưởng ít thành phần không?
- **Deployability:** có thể phát hành, canary, rollback độc lập không?
- **Interoperability:** service/client có giao tiếp ổn định không?
- **Observability:** có thể hiểu trạng thái và điều tra lỗi không?
- **Recoverability:** backup/restore, replay và reconciliation có đáp ứng không?
- **Cost efficiency:** chi phí trên đơn vị công việc hữu ích có phù hợp không?
- **Operability:** đội ngũ có đủ năng lực vận hành và hỗ trợ không?

Không thể tối đa hóa mọi thuộc tính cùng lúc. Tăng consistency có thể tăng latency; tăng isolation có thể tăng vận hành; thêm replication có thể tăng chi phí; thêm abstraction có thể giảm coupling nhưng tăng cognitive load.

### 5.1. Viết quality attribute scenario

Một yêu cầu như “hệ thống phải nhanh” quá mơ hồ. Có thể diễn đạt thành scenario:

~~~text
Source: 10,000 concurrent shoppers
Stimulus: flash-sale traffic increases 5x
Environment: normal production, one cache node unavailable
Response: catalog browse continues with bounded degradation
Measure: 99% of browse requests complete within agreed latency target
        and checkout correctness is preserved
~~~

Scenario giúp so sánh công nghệ theo cùng điều kiện. Không dùng con số minh họa như SLO thật nếu chưa được product/business owner phê duyệt.

### 5.2. Tách requirement khỏi solution

“Phải dùng Kafka” là solution constraint, không phải mô tả outcome. Requirement có thể là:
- Nhiều consumer xử lý event độc lập.
- Consumer có thể replay trong một khoảng thời gian.
- Event không bị mất sau khi source transaction commit.
- Throughput và lag đáp ứng SLO.
- Có thể mở rộng consumer theo partition.
- Có quyền truy cập và retention phù hợp.

Sau đó mới đánh giá Kafka, Pulsar, RabbitMQ, managed queue hoặc database outbox + worker. Nếu tổ chức đã có platform standard, đó là một constraint cần ghi nhận, nhưng vẫn cần đánh giá fit và ngoại lệ.

## 6. Bối cảnh và constraints: điều gì thật sự bắt buộc?

Các ràng buộc có thể đến từ:
- Business model và customer journey.
- Quy định pháp lý, hợp đồng và data residency.
- Hệ thống legacy và dữ liệu hiện có.
- Năng lực team và kỹ năng vận hành.
- Cloud/vendor contract và chi phí.
- Security baseline.
- SLO/RTO/RPO.
- Thời gian migration và ngân sách.
- Khả năng tích hợp với client hoặc đối tác.

Phân biệt:
- **Hard constraint:** phải tuân thủ, ví dụ dữ liệu thuộc vùng lưu trữ được phê duyệt hoặc API đối tác chỉ hỗ trợ một giao thức.
- **Soft constraint:** ưu tiên có thể thương lượng, ví dụ team quen Java hoặc muốn dùng một database đã có.
- **Assumption:** giả định cần kiểm chứng, ví dụ traffic sẽ tăng 10 lần trong năm tới.
- **Preference:** sở thích, ví dụ thích framework có annotation ngắn.
- **Non-goal:** điều không nằm trong phạm vi hiện tại, ví dụ chưa tối ưu multi-region active-active.

Nếu không phân loại, sở thích có thể bị trình bày như yêu cầu bắt buộc và làm hẹp lựa chọn quá sớm.

### 6.1. Constraint không miễn trừ việc đánh giá

“Công ty đã chuẩn hóa Kubernetes” là bối cảnh quan trọng. Tuy nhiên, một workload batch đơn giản có thể phù hợp hơn với managed job platform nếu chính sách cho phép. Hãy xác định chuẩn đó là bắt buộc, có ngoại lệ hay chỉ là paved road.

### 6.2. Không thiết kế cho giả định chưa được chứng minh

Ví dụ dự báo “sau này có hàng tỷ user” không đủ để chọn distributed database phức tạp ngay hôm nay. Ghi rõ:
- Bằng chứng hiện có.
- Mốc tăng trưởng dự kiến.
- Ngưỡng kích hoạt thay đổi.
- Cách đo để nhận ra ngưỡng.
- Chi phí nếu chuẩn bị quá sớm và nếu chuẩn bị quá muộn.

Thiết kế có khả năng tiến hóa thường tốt hơn trả trước chi phí cho mọi khả năng giả định.

## 7. Framework lựa chọn implementation sau khi có quyết định kiến trúc

Khi kiến trúc đã nêu nhu cầu, framework được đánh giá theo mức phù hợp.

Ví dụ một service Java cần:
- REST API và validation.
- Dependency injection.
- Transaction với PostgreSQL.
- Metrics/tracing.
- Security integration.
- Build/deploy tiêu chuẩn.
- Team đã có năng lực vận hành Java.

Spring Boot có thể là lựa chọn hợp lý. Nhưng quyết định dùng Spring Boot không trả lời thay:
- Service có nên tồn tại riêng không?
- Transaction boundary đặt ở đâu?
- Có cần reactive programming không?
- API nên synchronous hay async?
- Dữ liệu nào được sở hữu?
- Service có cần scale riêng không?

### 7.1. Các tiêu chí đánh giá framework

| Tiêu chí | Câu hỏi |
|---|---|
| Functional fit | Framework hỗ trợ use cases và programming model cần thiết không? |
| Performance | Latency/throughput/memory trong workload thực thế nào? |
| Security | Có cơ chế phù hợp và được cập nhật không? |
| Ecosystem | Driver, observability, testing, integration có đủ? |
| Operability | Debug, profiling, health, metrics, tracing thế nào? |
| Team capability | Team có thể xây và vận hành an toàn không? |
| Upgrade path | Nâng phiên bản, xử lý CVE và breaking changes ra sao? |
| Compatibility | Tương thích JDK, runtime, platform và thư viện hiện tại không? |
| Lifecycle | Dự án có maintainer, release cadence và support policy? |
| Total cost | License, training, runtime, migration và support tốn bao nhiêu? |
| Reversibility | Có thể thay framework mà giữ domain model/contracts không? |

Không nên chỉ benchmark một endpoint “hello world”. Hãy đo workload representative gồm database, serialization, authentication, observability, concurrency và failure.

### 7.2. Khi nào framework trở thành ràng buộc kiến trúc?

Một framework có thể định hình:
- Threading và execution model.
- Dependency injection/lifecycle.
- Transaction context.
- Persistence mapping.
- Serialization contract.
- Error handling.
- Plugin/module system.
- Startup/shutdown behavior.
- Testing and deployment model.

Ví dụ chuyển từ Spring MVC/JPA sang WebFlux/R2DBC không chỉ là đổi annotation. Threading, transaction context, repository API, blocking calls và backpressure đều thay đổi. Đây là migration có ảnh hưởng thiết kế và vận hành, cần thử nghiệm có phạm vi.

## 8. Platform lựa chọn phải theo operating model

Platform là nơi và cơ chế chạy workload, cung cấp network, identity, storage, deployment, scaling và observability.

Các lựa chọn thường gặp:
- VM hoặc bare metal.
- Managed application platform / PaaS.
- Container runtime và orchestration.
- Kubernetes.
- Serverless functions.
- Managed database, queue, object storage.
- Edge/region-specific infrastructure.

### 8.1. Kubernetes không phải mặc định cho mọi workload

Kubernetes có ích khi tổ chức cần:
- Orchestration cho nhiều workload/container.
- Scheduling và resource management.
- Service discovery và rollout.
- Scaling và workload isolation.
- Ecosystem platform dùng chung.
- Cấu hình vận hành có thể tái sử dụng.

Nhưng nó cần:
- Cluster lifecycle và upgrades.
- Networking, ingress, DNS, policy.
- Security, RBAC, secrets.
- Resource requests/limits.
- Observability và incident response.
- Storage, backup, recovery.
- Năng lực platform engineering.

Nếu một nhóm chỉ có một API nhỏ, PaaS có thể đáp ứng nhanh hơn và ít operational burden. Lựa chọn phụ thuộc vào yêu cầu và khả năng vận hành, không phải số lượng microservice.

### 8.2. Platform tạo ra một phần kiến trúc runtime

Một số quyết định platform có thể trở thành kiến trúc:
- Service có thể chạy stateless hay cần sticky session?
- Workload có thể bị terminate bất cứ lúc nào không?
- Persistent volume và state recovery ra sao?
- Có thể chạy multi-zone/multi-region không?
- Network policy và service identity được enforce thế nào?
- Rollout có thể chạy old/new version song song không?
- Autoscaling signal dựa trên CPU, queue lag hay custom metric?
- Backup/restore và disaster recovery có đáp ứng RTO/RPO?

Không thể chọn platform chỉ bằng danh sách feature; cần kiểm tra behavior trong môi trường vận hành thực.

## 9. Database choice: công nghệ hay quyết định kiến trúc?

Chọn database thường có ảnh hưởng dài hạn vì data model, transaction, consistency, query patterns, migration, backup và skill của team gắn chặt với nó.

Tuy vậy, “PostgreSQL hay MongoDB?” cần bắt đầu từ:
- Dữ liệu có cấu trúc và quan hệ thế nào?
- Invariant nào cần transaction/constraint?
- Read/write pattern ra sao?
- Query/filter/sort/aggregation nào quan trọng?
- Volume, growth và partitioning?
- Consistency và replication cần gì?
- Schema evolution và migration?
- Backup, restore, retention và data residency?
- Team vận hành được gì?
- Cost trên workload thực?

### 9.1. Ví dụ chọn PostgreSQL

Có thể phù hợp khi:
- Quan hệ và join quan trọng.
- Transaction và constraint là yêu cầu chính.
- Query ad hoc/analytics vừa phải cần SQL.
- Ecosystem và operational skill đã có.
- Cần extension hoặc tính năng PostgreSQL phù hợp.

Nhưng cần đo connection pooling, index, lock, query plan, replication và partitioning. Chọn PostgreSQL không tự giải quyết data ownership hoặc transaction xuyên service.

### 9.2. Ví dụ chọn document database

Có thể phù hợp khi:
- Aggregate document có cấu trúc truy cập phù hợp.
- Read/write chủ yếu theo document key.
- Schema biến đổi theo use case.
- Cần scale và replication semantics phù hợp.
- Team hiểu consistency, indexing và transaction limitations.

Không chọn chỉ vì “schema-less nên dễ thay đổi”. Document database vẫn có schema logic, validation, migration và compatibility. Nếu mọi truy vấn cần join phức tạp, lựa chọn này có thể làm ứng dụng phức tạp hơn.

### 9.3. Database-per-service là quyết định ownership

Database-per-service không nhất thiết đồng nghĩa mỗi service một loại database. Một tổ chức có thể dùng PostgreSQL cho nhiều service nhưng mỗi service sở hữu schema/database và write path riêng.

Điểm cốt lõi:
- Service khác không ghi trực tiếp vào dữ liệu owner.
- Contract query/event được công bố.
- Projection/copy có purpose và retention.
- Migration do owner chịu trách nhiệm.
- Credential và permission được tách.
- Khi cần tách physical database, có lộ trình.

Polyglot persistence có ích khi workload khác nhau rõ rệt, nhưng thêm công nghệ cũng thêm backup, monitoring, security patching, incident skill và migration burden. Không dùng nhiều database để chứng minh kiến trúc hiện đại.

## 10. Message broker và event technology

Chọn Kafka, RabbitMQ, cloud queue hoặc giải pháp khác cần gắn với semantics.

| Nhu cầu | Điều cần đánh giá |
|---|---|
| Work queue | Ack, retry, visibility timeout, dead-letter, fairness |
| Event log/replay | Retention, partition, offset, ordering, consumer groups |
| Request/reply | Latency, correlation, timeout, ownership |
| Broadcast/fan-out | Consumer isolation, throughput, subscription lifecycle |
| Scheduled/delayed work | Delay semantics, persistence, cancellation |
| Large payload | Size limits, object reference, retention/security |
| Exactly-once claims | Transaction boundary thực tế, idempotency và failure modes |

Kafka thường phù hợp event streaming, retention và nhiều consumer độc lập theo partition; RabbitMQ thường được dùng cho message routing/queue semantics; managed cloud queues giảm vận hành broker. Những mô tả này chỉ là định hướng, không thay thế đánh giá version, managed service behavior, throughput và contract.

### 10.1. Công nghệ không quyết định business consistency

Dùng Kafka không tự tạo saga. Dùng RabbitMQ không tự bảo đảm consumer xử lý đúng một lần. Dùng cloud queue không tự bảo đảm order của mọi message.

Cần thiết kế:
- Outbox/inbox.
- Idempotency.
- Ordering scope.
- Retry/backoff.
- DLQ/replay.
- Schema versioning.
- Consumer lag SLO.
- Reconciliation.
- Event ownership và data classification.

### 10.2. Chọn broker theo vận hành toàn vòng đời

Tính cả:
- Provisioning và upgrades.
- Partition/queue management.
- Monitoring và alert.
- Schema registry.
- Consumer scaling.
- Retention/storage cost.
- Backup/restore hoặc replay.
- Security ACL và secret rotation.
- Incident skill và on-call.
- Vendor limits và portability.

Một broker nhanh hơn 20% trong benchmark có thể không đáng nếu tổ chức chưa có năng lực vận hành và không cần throughput đó.

## 11. Cache technology không thay thế cache architecture

Redis, Memcached, Caffeine hoặc CDN là công cụ. Quyết định kiến trúc phải làm rõ:
- Dữ liệu nào được cache?
- Ai sở hữu freshness?
- TTL, soft TTL, hard TTL?
- Invalidation khi source thay đổi?
- Cache stampede được ngăn thế nào?
- L1/L2 consistency?
- Cache outage fallback?
- Hot-key và global loader budget?
- Dữ liệu nhạy cảm có được cache không?
- Khi nào source of truth phải được xác minh lại?

Ví dụ Redis có thể cung cấp shared cache và atomic primitives. Nhưng nếu mọi request miss đều gọi DB không giới hạn, Redis không bảo vệ database. Cần single-flight, distributed refresh coordination, stale policy và admission control theo workload.

### 11.1. Cache là một quyết định dữ liệu

Cache tạo bản sao. Cần tính retention, access, encryption, tenant key scope và deletion. Không đưa credential hoặc raw PII vào cache vì “chỉ tồn tại vài phút” nếu hệ thống không thực thi được TTL/invalidation.

### 11.2. Đừng chọn cache trước khi biết bottleneck

Nếu latency chủ yếu do query thiếu index hoặc N+1, thêm Redis có thể tăng complexity mà không sửa nguyên nhân. Đo trace/query plan và cache hit/miss trước; chỉ cache khi có use case và freshness contract.

## 12. API style và serialization

REST, gRPC, GraphQL, messaging và RPC nội bộ là lựa chọn có ảnh hưởng tới integration contract.

### 12.1. REST

Có thể phù hợp cho resource-oriented API, browser/mobile/client integration, HTTP caching và ecosystem rộng. Cần thiết kế:
- Resource/operation semantics.
- Status/error model.
- Pagination.
- Idempotency.
- Versioning/deprecation.
- Auth scopes.
- Rate limits.
- Caching headers.
- Request size/deadline.

### 12.2. gRPC

Có thể phù hợp service-to-service cần contract schema, code generation, streaming hoặc hiệu quả binary protocol. Cần đánh giá:
- Browser/client compatibility.
- Proxy/ingress support.
- Deadline propagation.
- Error/status semantics.
- Protobuf evolution.
- Observability tooling.
- Operational debugging.

### 12.3. GraphQL

Có thể phù hợp client cần chọn shape dữ liệu linh hoạt qua nhiều nguồn. Cần quản lý:
- Query complexity/depth.
- Authorization ở field/resolver.
- N+1/data loader.
- Caching.
- Schema lifecycle.
- Rate/cost limits.
- Error semantics và partial data.

### 12.4. Serialization format

JSON, Protobuf, Avro và các format khác là lựa chọn kỹ thuật, nhưng schema evolution và semantics mới là phần kiến trúc. Thêm field, đổi enum, nullability, default và unit có thể ảnh hưởng consumer.

Không dùng một format chỉ vì nó “nhỏ hơn” mà bỏ qua debug, compatibility, tooling và client ecosystem.

## 13. Framework và platform có thể áp đặt một operating model

Một công nghệ có thể kéo theo cách tổ chức:
- Spring Boot thường phù hợp application service Java với ecosystem phong phú.
- Reactive stack yêu cầu tư duy non-blocking, backpressure và context propagation.
- Serverless khuyến khích stateless execution, event trigger và time-bounded invocation.
- Kubernetes thúc đẩy container lifecycle, health probes, declarative config và rollout.
- Managed database giảm việc quản trị engine nhưng tạo phụ thuộc vào vendor features, quota và service limits.

Trước khi chọn, hỏi:
- Team phải học và vận hành điều gì?
- On-call có thể debug lỗi production không?
- Công nghệ có phù hợp skill hiện tại và tuyển dụng?
- Có lock-in nào ở API, data format, IAM hoặc deployment?
- Nâng cấp có lịch trình và owner?
- Khi service scale, platform có giữ semantics mong muốn?
- Những assumption nào sẽ khó thay đổi sau khi triển khai rộng?

**Developer experience và operational capability là tiêu chí kiến trúc**, không phải yếu tố phụ.

## 14. Reversibility: quyết định nào khó đổi?

Một lựa chọn framework có thể dễ thay nếu domain logic không phụ thuộc sâu vào framework. Một lựa chọn database có thể rất khó đổi khi query, transaction và data model phụ thuộc đặc tính riêng. Một platform có thể tạo lock-in qua IAM, storage, event services và proprietary APIs.

Có thể phân loại:

| Mức | Đặc điểm | Cách ra quyết định |
|---|---|---|
| Dễ đảo ngược | Phạm vi nhỏ, ít dữ liệu/consumer phụ thuộc | Thử nhanh, đo và đổi nếu cần |
| Có chi phí di chuyển | Ảnh hưởng module/service, cần adapter hoặc migration | Prototype, ADR, kế hoạch chuyển |
| Khó đảo ngược | Dữ liệu lớn, nhiều consumer, contract hoặc vendor lock-in | Phân tích sâu, PoC, risk review, migration strategy |
| Gần như không thể đảo ngược trong ngắn hạn | Regulatory, hardware, ecosystem hoặc dữ liệu lịch sử lớn | Executive/business decision, contingency và long-term governance |

Không phải mọi quyết định khó đổi đều phải hoãn. Chỉ cần làm rõ risk, assumptions, cost of delay và cơ chế giảm lock-in.

### 14.1. Giữ domain model độc lập với framework

Một cách giảm coupling:
- Domain model không kế thừa framework base class nếu không cần.
- Dùng adapter cho persistence, messaging và transport.
- Mapping DTO/API ở boundary.
- Transaction boundary đặt ở application layer.
- Không để exception framework lan thành domain contract.
- Test domain logic không cần boot toàn bộ runtime.

Đây không phải quy tắc tuyệt đối. Dùng JPA annotations trên entity có thể là trade-off hợp lý. Mục tiêu là biết dependency đang ở đâu và chi phí thay đổi có chấp nhận được không.

### 14.2. Portability có chi phí

Viết abstraction để có thể đổi mọi database, cloud, broker và framework có thể tạo một lớp generic yếu nhất mẫu số chung, mất tính năng hữu ích và tăng maintenance. Chỉ đầu tư portability khi:
- Có nhiều target thực sự.
- Có yêu cầu disaster recovery/vendor exit.
- Có rủi ro lock-in đáng kể.
- Có lợi ích đàm phán/chi phí.
- Có thể test adapter trên nhiều implementation.

Không xây abstraction “phòng khi một ngày nào đó” mà không có trigger và owner.

## 15. Trade-off analysis: so sánh bằng tiêu chí thống nhất

Một decision matrix có thể dùng:

| Tiêu chí | Trọng số | Option A | Option B | Evidence |
|---|---:|---:|---:|---|
| Functional fit | 20% | 4/5 | 3/5 | Use case coverage |
| Reliability | 20% | 3/5 | 4/5 | Failure test |
| Performance | 15% | 4/5 | 4/5 | Representative benchmark |
| Security/compliance | 15% | 4/5 | 4/5 | Control review |
| Operability | 10% | 4/5 | 2/5 | Team runbook/PoC |
| Team capability | 10% | 5/5 | 2/5 | Skills and support |
| Total cost | 10% | 3/5 | 4/5 | 3-year estimate |

Điểm số chỉ là công cụ thảo luận, không phải thuật toán tự động chọn công nghệ. Một option không đạt hard constraint về security hoặc data residency không thể được bù bằng điểm performance cao.

### 15.1. Trọng số phải có lý do

Một hệ thống thanh toán có thể đặt correctness, security và audit cao hơn developer convenience. Một analytics batch có thể ưu tiên throughput, cost và replay. Không dùng cùng trọng số cho mọi workload.

### 15.2. Phân biệt fact, estimate và opinion

Mỗi đánh giá cần gắn evidence:
- **Fact:** kết quả benchmark trên workload đã mô tả.
- **Estimate:** chi phí vận hành dựa trên giá và mức sử dụng giả định.
- **Assumption:** traffic sẽ tăng 5 lần.
- **Opinion:** team thấy framework dễ dùng hơn.
- **Unknown:** chưa có bằng chứng về failover trong region thứ hai.

Ghi unknown để quyết định có thể chọn PoC hoặc thử nghiệm, thay vì biến suy đoán thành sự thật.

## 16. Prototype và proof of concept

PoC nên kiểm chứng một rủi ro kiến trúc cụ thể. Không xây một ứng dụng demo đầy đủ chỉ để chứng minh framework khởi động được.

Ví dụ câu hỏi PoC:
- Database có chịu được concurrency và transaction pattern cần thiết không?
- Broker có đáp ứng throughput/lag và replay policy?
- Framework có tích hợp tracing/security/transaction đúng cách?
- Platform có đáp ứng startup, graceful shutdown và autoscaling?
- Migration có thể chạy online với downtime cho phép?
- Team có thể vận hành và xử lý lỗi?

### 16.1. PoC phải có exit criteria

~~~text
Hypothesis:
  Managed queue can support the required event workload.

Workload:
  Peak event rate, payload size, consumer count, retention.

Failure cases:
  Consumer crash, duplicate delivery, provider throttling.

Measures:
  p95/p99 processing latency, lag, recovery time, cost.

Exit criteria:
  Meets approved SLO and security/data policy.

Decision:
  Adopt / reject / extend experiment.
~~~

Không để PoC tồn tại vô thời hạn. Khi giả thuyết đã được chứng minh hoặc bác bỏ, lưu kết quả và đưa ra quyết định.

### 16.2. Benchmark phải đại diện

Một benchmark tốt cần:
- Payload và data distribution tương tự production.
- Concurrency và traffic shape.
- Cold/warm cache.
- Authentication và observability.
- Database/broker network.
- Error/timeout/retry.
- Memory/CPU và GC.
- Scale-out và scale-in.
- Failure/recovery.
- Cost ở mức workload dự kiến.

Benchmark “hello world” chỉ đo startup path đơn giản. Nó không đủ để kết luận framework phù hợp cho hệ thống thực.

## 17. Architecture Decision Record (ADR)

ADR ghi lại quyết định có ảnh hưởng đáng kể để người khác hiểu lý do và điều kiện xem lại.

Một cấu trúc ngắn:

~~~markdown
# ADR-042: Use PostgreSQL for Order state

Status: Accepted

## Context
Order requires transactional state changes, unique constraints,
and queries over customer/order/time.

## Decision
Use PostgreSQL as the authoritative store for Order data.
Only Order Service owns writes to its schema.

## Alternatives
- Existing shared database schema
- Document database
- Distributed key-value store

## Consequences
- Order owns migrations, backups and connection budget.
- Other services consume API/events or approved projections.
- Team must manage indexes, transaction duration and restore tests.

## Quality attributes
Correctness, auditability, operability and query flexibility.

## Review triggers
Sustained scale beyond the tested range, new residency constraint,
or change in transaction/query patterns.
~~~

ADR không phải tài liệu quảng cáo công nghệ. Nó nên nêu:
- Context và problem.
- Requirements/constraints.
- Options được cân nhắc.
- Lý do chọn và trade-offs.
- Quality attributes bị ảnh hưởng.
- Owner và status.
- Migration/rollout nếu cần.
- Consequences tích cực và tiêu cực.
- Trigger để xem lại.

### 17.1. Ghi cả quyết định không chọn

Ví dụ không chọn Kafka vì workload chỉ cần queue nhỏ, không cần replay dài, managed queue hiện có đáp ứng SLO và team chưa có năng lực vận hành Kafka. Lý do này giúp người sau không lặp lại cuộc tranh luận dựa trên thông tin cũ.

### 17.2. ADR có trạng thái và lịch sử

Các trạng thái thường dùng:
- Proposed.
- Accepted.
- Rejected.
- Superseded.
- Deprecated.

Không xóa ADR cũ khi quyết định thay đổi; ghi ADR mới supersede ADR trước và giải thích bối cảnh đã thay đổi. Điều này tạo lịch sử tiến hóa kiến trúc.

## 18. Architecture runway và quyết định theo giai đoạn

Không cần chọn mọi công nghệ cho tương lai ngay từ đầu. Có thể tạo runway đủ để hỗ trợ capability kế tiếp, nhưng tránh xây platform quá mức.

Ví dụ:
- Giai đoạn đầu: modular monolith + PostgreSQL + managed deployment.
- Khi team/domain lớn hơn: enforce module boundary và ownership.
- Khi một domain cần scale/isolation riêng: tách process.
- Khi event consumers tăng: đánh giá broker có retention/replay phù hợp.
- Khi multi-region là yêu cầu: thiết kế data replication, routing và recovery.

Mỗi bước nên có:
- Trigger đo được.
- Lợi ích kỳ vọng.
- Chi phí và rủi ro.
- Điều kiện triển khai.
- Cách rollback hoặc chuyển tiếp.
- Owner.

### 18.1. Không over-engineer cho tương lai giả định

Nếu hiện tại chỉ có một team và một workload vừa phải, dùng microservices, service mesh, multi-region active-active, CQRS và event sourcing đồng thời có thể tạo chi phí lớn mà chưa giải quyết vấn đề.

Thiết kế để **có đường tiến hóa**, không nhất thiết triển khai mọi giai đoạn ngay. Giữ boundary, data ownership và contract rõ giúp mở rộng khi có bằng chứng.

### 18.2. Không under-engineer yêu cầu đã biết

Ngược lại, nếu hệ thống có yêu cầu audit pháp lý, tenant isolation, RPO thấp hoặc throughput cao đã được xác nhận, không nên bỏ qua chỉ để giữ kiến trúc đơn giản. Yêu cầu đã biết cần được đưa vào quyết định ngay từ đầu.

## 19. Công nghệ thay đổi, quyết định kiến trúc có thể giữ

Một kiến trúc tốt thường cho phép thay một số implementation mà không thay đổi mục tiêu và contract.

Ví dụ:

~~~text
Order Application
       |
       +-- Order Repository Port
       |        |
       |        +-- JPA Adapter
       |        +-- JDBC Adapter
       |
       +-- Event Publisher Port
       |        |
       |        +-- Kafka Adapter
       |        +-- Managed Queue Adapter
       |
       +-- Payment Port
                |
                +-- HTTP Adapter
                +-- gRPC Adapter
~~~

Ports/adapters có thể cô lập công nghệ, nhưng không nên tạo abstraction vô nghĩa. Nếu adapter thay đổi mà semantics của transaction, ordering hoặc delivery khác, contract phải phản ánh khác biệt đó.

### 19.1. Thay framework không nhất thiết thay kiến trúc

Có thể chuyển từ Spring MVC sang framework khác mà vẫn giữ:
- Domain boundaries.
- Public API.
- Data ownership.
- Transaction semantics.
- Event contracts.
- SLO và security policy.

Tuy nhiên nếu framework mới đổi execution model, transaction context, startup/shutdown hoặc serialization, cần kiểm chứng lại quality attributes và operations.

### 19.2. Thay platform có thể tác động sâu hơn

Chuyển VM sang Kubernetes hoặc từ self-hosted database sang managed database có thể đổi:
- Network topology.
- Identity model.
- Secret delivery.
- Storage durability.
- Failover semantics.
- Autoscaling.
- Cost model.
- Vendor dependency.
- Operational responsibilities.

Vì thế platform migration có thể là chương trình kiến trúc lớn, không chỉ thay file deployment YAML.

## 20. Ví dụ so sánh Spring Boot, Quarkus và Micronaut

Các framework Java có thể đáp ứng cùng một kiến trúc service, nhưng có khác biệt về ecosystem, startup, memory, build-time processing, runtime behavior và team familiarity.

| Tiêu chí | Spring Boot | Quarkus | Micronaut |
|---|---|---|---|
| Ecosystem | Rộng, lâu đời, nhiều tích hợp | Tích hợp mạnh với Kubernetes/GraalVM ecosystem | DI/compile-time processing, cloud-native focus |
| Startup/memory | Phụ thuộc stack/config; có thể tối ưu | Có các hướng tối ưu startup và native | Có thể tối ưu startup/memory |
| Learning curve | Nhiều team Java đã quen | Cần hiểu ecosystem và build model | Cần học conventions và ecosystem |
| Integration | Rất phong phú | Tùy extension | Tùy module và extension |
| Native image | Có hỗ trợ qua ecosystem phù hợp | Một trọng tâm phổ biến | Có hỗ trợ |
| Operational fit | Tùy workload và tuning | Tùy workload và tuning | Tùy workload và tuning |

Không nên đưa ra kết luận chung rằng framework nào luôn nhanh hơn hoặc tốt hơn. Benchmark phụ thuộc:
- JDK và version framework.
- JVM mode hay native image.
- Dependencies thực tế.
- Startup profile và warmup.
- Database/broker/HTTP client.
- Tracing/security instrumentation.
- Heap/GC và concurrency.
- Container resource limits.
- Build time và CI cost.

### 20.1. Câu hỏi đúng trước khi chuyển framework

- Vấn đề hiện tại là startup, memory, throughput hay developer experience?
- Chi phí hiện tại đo được bao nhiêu?
- Có thể tối ưu cấu hình và dependency trước không?
- Chuyển framework có ảnh hưởng transaction, security, observability hoặc API semantics?
- Có cần chạy hai runtime trong giai đoạn migration?
- Team có đủ năng lực và thời gian hỗ trợ?
- Benefit trong 12–24 tháng vượt chi phí chuyển đổi?

Một framework mới không sửa được boundary sai, shared database coupling hoặc business workflow thiếu idempotency.

## 21. Ví dụ lựa chọn platform: Kubernetes hay PaaS

Giả sử có 8 service Java:
- Traffic tương đối ổn định.
- Một service cần autoscale theo queue lag.
- Các service còn lại có tải thấp.
- Team platform có hai người.
- Công ty đã có managed container platform và Kubernetes cluster.

Đánh giá có thể gồm:

| Tiêu chí | Managed PaaS/container | Kubernetes |
|---|---|---|
| Onboarding | Có thể nhanh nếu service đơn giản | Cần template và platform support |
| Control | Hạn chế theo dịch vụ | Nhiều quyền cấu hình hơn |
| Operations | Nhà cung cấp quản lý nhiều phần | Cluster lifecycle và policy do tổ chức quản |
| Autoscaling | Theo capabilities của provider | Linh hoạt, cần cấu hình và vận hành |
| Portability | Có thể gắn provider | Có thể tăng tính nhất quán giữa môi trường, vẫn có lock-in |
| Team skill | Dễ tiếp cận hơn tùy platform | Cần năng lực Kubernetes |
| Cost | Tính theo dịch vụ/resource | Có cluster overhead và shared platform cost |
| Security | Phụ thuộc control của provider | Cần quản lý nhiều lớp cluster/workload |

Nếu PaaS đáp ứng SLO, data policy và scaling, nó có thể là lựa chọn tốt. Kubernetes chỉ đáng khi control, shared platform hoặc workload requirements mang lại lợi ích vượt chi phí vận hành.

### 21.1. Platform decision phải tính tổng ownership

Ai chịu trách nhiệm:
- Cluster upgrade?
- Node failure?
- Ingress/DNS/certificate?
- Network policy?
- Secrets?
- Persistent storage?
- Observability?
- Quota và cost allocation?
- Security patches?
- On-call khi control plane lỗi?

Nếu câu trả lời là “team ứng dụng tự xử lý” nhưng họ không có kỹ năng/quyền, platform choice đã chuyển gánh nặng mà chưa tạo capability.

## 22. Ví dụ lựa chọn database theo access pattern

Giả sử Catalog có:
- Product metadata.
- Category hierarchy.
- Price history.
- Search/filter nhiều tiêu chí.
- Inventory snapshot.
- Audit changes.

Một cuộc thảo luận “SQL hay NoSQL?” cần tách workload:
- Metadata và relation cần constraint/query.
- Search có thể cần search index riêng.
- Price history có thể cần time-series/partition strategy tùy tải.
- Inventory là nguồn nghiệp vụ riêng nếu có invariant reservation.
- Audit cần retention và append semantics.

Không bắt buộc tất cả dữ liệu nằm trong một database, nhưng cũng không nên tách mọi loại dữ liệu thành một công nghệ riêng. Một relational database cùng một search engine có thể đủ; polyglot chỉ khi nhu cầu cụ thể chứng minh lợi ích.

### 22.1. CQRS không đồng nghĩa phải dùng hai database khác nhau

CQRS phân biệt command model và query model. Có thể triển khai cả hai trên cùng database ban đầu. Chỉ dùng read store riêng khi scale/query/availability hoặc model read khác biệt tạo lợi ích thực.

### 22.2. Event sourcing là quyết định mô hình dữ liệu

Chọn Kafka không đồng nghĩa event sourcing. Event sourcing có nghĩa event là source of truth cho state và hệ thống tái tạo state từ event stream theo semantics. Nó kéo theo:
- Event schema evolution.
- Replay/upcasting.
- Snapshot strategy.
- Event retention.
- Privacy/deletion constraints.
- Query projections.
- Operational recovery.

Chỉ áp dụng khi audit/history/time-travel/domain semantics mang lại lợi ích đáng kể so với state storage thông thường.

## 23. Rủi ro lock-in và chiến lược giảm thiểu

Vendor/framework lock-in không tự động xấu. Một managed service có thể giảm toil và tăng reliability đáng kể. Vấn đề là tổ chức có hiểu chi phí rời đi và chấp nhận nó không.

### 23.1. Các loại lock-in

- **API lock-in:** code phụ thuộc API proprietary.
- **Data lock-in:** format/export/migration khó.
- **Identity lock-in:** authorization/secret model phụ thuộc vendor.
- **Operational lock-in:** chỉ một nhóm/vendor biết cách vận hành.
- **Skill lock-in:** kiến thức tập trung vào một cá nhân.
- **Contract lock-in:** client/consumer phụ thuộc semantics đặc thù.
- **Commercial lock-in:** pricing, license, quota và egress.

### 23.2. Giảm lock-in có chọn lọc

- Dùng domain contract độc lập với provider.
- Tách adapter cho external service.
- Duy trì export/backup format có thể khôi phục.
- Không phụ thuộc API proprietary ở domain core nếu không cần.
- Kiểm tra exit plan định kỳ cho dữ liệu quan trọng.
- Version hóa schema và contract.
- Có quyền truy cập và documentation vận hành.
- Chỉ giữ abstraction khi có use case portability thực.

Không cố trừu tượng hóa mọi dịch vụ cloud thành interface chung. Điều đó có thể làm mất feature, tăng code và khiến team không dùng được lợi ích của managed service.

## 24. Quy trình ra quyết định công nghệ có trách nhiệm

Một workflow:

~~~text
1. State the problem and desired outcome
             |
             v
2. Capture functional/NFR requirements
             |
             v
3. Identify architecture decisions and constraints
             |
             v
4. List viable options and trade-offs
             |
             v
5. Separate hard constraints from preferences
             |
             v
6. Prototype only the highest-risk unknowns
             |
             v
7. Record ADR with owner and review triggers
             |
             v
8. Implement behind stable boundaries
             |
             v
9. Measure outcomes in representative workload
             |
             v
10. Keep, adjust or supersede the decision
~~~

### 24.1. Ai tham gia?

- Product/business owner: mục tiêu, user journey, cost/value.
- Domain/service owner: business semantics và data ownership.
- Engineering team: implementation, maintainability, testing.
- Platform team: deployment/runtime/operability.
- Security/privacy: risk, identity, data handling.
- Operations/SRE: SLO, recovery, capacity.
- Finance/FinOps: unit economics và vendor costs.
- Consumers/partners: contract và migration impact.

Không cần mọi vai trò tham gia mọi quyết định. Chỉ mời những người có expertise hoặc bị ảnh hưởng; quyết định nhỏ, dễ đảo ngược nên do team gần code tự quyết.

### 24.2. Decision owner và consultation

Mỗi quyết định có một người/nhóm chịu trách nhiệm chốt. Tham vấn không đồng nghĩa cần consensus tuyệt đối. Khi có xung đột:
- Nêu tiêu chí đã thống nhất.
- Làm rõ constraint nào bắt buộc.
- So sánh evidence.
- Xác định risk owner.
- Ghi ý kiến khác biệt.
- Đặt deadline và review trigger.

Không để một quyết định cục bộ bị chặn chỉ vì team khác thích framework khác; cũng không cho team tự bỏ qua policy chung có ảnh hưởng an toàn.

## 25. Khi nào cần ADR, RFC hay chỉ code review?

| Loại thay đổi | Hồ sơ phù hợp |
|---|---|
| Rename class, refactor private method | Code review |
| Thay thư viện nhỏ trong một module, dễ rollback | Code review hoặc note ngắn |
| Đổi framework ảnh hưởng runtime và transaction | ADR, có thể kèm PoC |
| Chọn database cho domain mới | ADR |
| Thay service boundary hoặc data ownership | ADR/RFC và consumer review |
| Thay API/event breaking | Contract change proposal, migration plan |
| Thay platform toàn tổ chức | RFC, ADR cấp hệ thống và rollout plan |
| Ngoại lệ security/data policy | Quy trình exception có owner và thời hạn |
| Thay config pool size trong phạm vi SLO | Change review/operational validation |

Không tạo ADR cho mọi dependency update. Nhưng khi quyết định có thể ảnh hưởng lâu dài, thiếu ADR khiến người sau phải suy đoán vì sao công nghệ được chọn.

## 26. Đo lường sau khi chọn framework hoặc platform

Đừng kết thúc quyết định ở thời điểm merge cấu hình. Sau rollout, đo:
- SLO và user journey outcome.
- Latency/throughput theo workload representative.
- CPU/memory/startup/GC.
- Failure and recovery behavior.
- Deployment lead time và rollback success.
- Incident toil và support burden.
- Security findings và patch time.
- Cost per successful operation.
- Team onboarding/learning time.
- Upgrade complexity và dependency health.

Nếu framework giúp startup nhanh hơn nhưng làm transaction correctness hoặc observability khó hơn, trade-off cần được nhìn tổng thể. Nếu Kubernetes tăng deployment control nhưng platform team trở thành bottleneck, outcome chưa đạt.

### 26.1. Đặt review trigger trước khi chọn

Ví dụ:
- Nếu p99 latency không đạt sau hai vòng tuning, xem lại runtime/database choice.
- Nếu cost/transaction vượt budget liên tục trong ba chu kỳ, đánh giá architecture/platform.
- Nếu team không thể nâng version trong thời gian support window, giảm coupling hoặc thay dependency.
- Nếu workload vượt capacity đã test, thực hiện scale experiment.
- Nếu vendor đổi pricing/API, mở lại ADR liên quan.

Trigger phải phù hợp quyết định và có thể quan sát. Không mở lại mọi ADR mỗi tháng chỉ để làm thủ tục.

## 27. Những anti-pattern thường gặp

**Chọn framework rồi mới tìm bài toán cho nó.** Team bị dẫn dắt bởi tính năng công cụ và có thể xây hệ thống phức tạp hơn nhu cầu.

**“Kubernetes là kiến trúc.”** Kubernetes là platform/runtime; domain, data và interaction boundaries vẫn phải thiết kế.

**“Spring Boot quyết định phải dùng microservices.”** Spring Boot có thể chạy monolith, modular monolith, worker hoặc service độc lập.

**“NoSQL tự động scale tốt hơn SQL.”** Scale phụ thuộc access pattern, partitioning, consistency, index, workload và operational design.

**“Kafka nghĩa là event-driven architecture.”** Broker chỉ là hạ tầng; event ownership, semantics, idempotency và workflow mới tạo kiến trúc event-driven.

**“Service mesh giải quyết mọi vấn đề giao tiếp.”** Nó có thể hỗ trợ traffic/security/telemetry, nhưng không sửa contract và business coupling.

**“Framework benchmark nhanh nhất luôn tốt nhất.”** Benchmark không đại diện production và bỏ qua ecosystem, skill, security, upgrade và cost.

**“Dùng abstraction để tránh mọi lock-in.”** Abstraction generic có thể che mất semantics và tạo chi phí lớn hơn rủi ro được giảm.

**“Chọn công nghệ theo sở thích cá nhân.”** Preference hữu ích để ước lượng learning curve, nhưng không thay evidence và requirement.

**“Mọi quyết định phải được kiến trúc sư duyệt.”** Tạo bottleneck và làm team mất ownership. Dùng guardrails và decision rights.

**“Không cần ghi lại vì code đã thể hiện.”** Code không lưu đầy đủ assumptions, alternatives, rejected options và trigger xem lại.

**“PoC thành công nghĩa là production-ready.”** Demo path không kiểm tải, security, failure, backup, upgrade và on-call.

**“Đã chọn thì không bao giờ đổi.”** Quyết định có thể đúng trong bối cảnh cũ nhưng không còn phù hợp khi traffic, organization hoặc constraints thay đổi.

**“Chọn nhiều công nghệ để chứng minh tính linh hoạt.”** Polyglot làm tăng cognitive load, security patching và operational skill requirements.

**“Platform có feature nên phải dùng.”** Feature không có nhu cầu thực tạo complexity và chi phí không cần thiết.

**“Tối ưu kỹ thuật là mục tiêu cuối.”** Latency tốt hơn chỉ có giá trị nếu cải thiện user journey, cost hoặc risk theo mục tiêu.

## 28. Bài tập: lựa chọn framework và platform cho Order Service

Một nhóm xây Order Service với yêu cầu giả định:
- 1.500 request/s vào giờ cao điểm.
- Ghi order và order items phải atomic.
- Payment/Inventory là service độc lập.
- Request tạo đơn phải idempotent.
- Sự kiện OrderCreated không được mất sau khi order commit.
- Service cần triển khai độc lập.
- Team có kinh nghiệm Java/Spring.
- Tổ chức đang vận hành PostgreSQL và Kubernetes.
- On-call hiện có hai người cho domain này.

### 28.1. Câu hỏi

1. Những điều nào là architecture decisions?
2. Những điều nào là technology/platform choices?
3. Vì sao @Transactional không bao trùm Payment và Inventory?
4. Có cần Kafka ngay từ đầu không, hay một managed queue/outbox worker đủ?
5. PostgreSQL có đáp ứng transaction và query pattern không? Cần PoC gì?
6. Kubernetes có mang lại lợi ích lớn hơn managed container platform cho team hai người không?
7. Làm sao chứng minh event không bị mất sau commit?
8. Điều kiện nào cho phép đổi framework mà không đổi public contract?
9. Rủi ro lock-in và upgrade nào phải ghi vào ADR?
10. Outcome nào cần đo sau rollout?

### 28.2. Hướng giải

**Architecture decisions:**
- Order sở hữu order state và schema.
- Transaction cục bộ ghi order/items/outbox.
- Outbox relay phát event sau commit.
- Payment/Inventory được gọi theo workflow có timeout/idempotency và saga semantics.
- Service có SLO, data contract và owner.
- Consumer không ghi trực tiếp Order DB.

**Technology choices:**
- Spring Boot cho runtime/application framework.
- PostgreSQL cho local transactional store.
- Broker/managed queue được chọn theo retention, throughput, replay, consumer needs và team operations.
- Kubernetes hoặc PaaS theo platform capability và on-call capacity.

**Bằng chứng cần thu:**
- Integration/concurrency tests.
- Outbox crash/retry test.
- Load test ở traffic representative.
- Failure simulation với Payment/Inventory.
- Backup/restore và migration rehearsal.
- Cost/operation estimate.

**Outcome sau triển khai:**
- Order completion SLO.
- Duplicate order/payment rate.
- Outbox oldest-message age.
- Change lead time và release coupling.
- p99 và connection pool health.
- Cost trên đơn thành công.
- Incident recovery và on-call toil.

Không có một lựa chọn framework/broker/platform đúng cho mọi tổ chức. Quyết định phải dựa vào yêu cầu, evidence, constraints và năng lực vận hành đã xác định.

## 29. Checklist trước khi chốt một lựa chọn công nghệ

1. **Problem:** Vấn đề cụ thể cần giải quyết là gì?
2. **Outcome:** Kết quả nào sẽ cải thiện và đo bằng cách nào?
3. **Architecture:** Boundary, ownership, interaction và consistency đã rõ chưa?
4. **Requirements:** Functional requirements và quality attribute scenarios có cụ thể?
5. **Constraints:** Hard constraint, soft preference, assumption và non-goal được phân biệt?
6. **Alternatives:** Có các lựa chọn khả thi và lý do loại bỏ?
7. **Fit:** Công nghệ phù hợp workload, data model, protocol và scale?
8. **Security:** Identity, authorization, secrets, data residency và patching?
9. **Reliability:** Timeout, retry, failover, backup, restore và SLO?
10. **Operability:** Monitoring, debugging, on-call và incident response?
11. **Team capability:** Có kỹ năng, owner và thời gian học/vận hành?
12. **Lifecycle:** Release cadence, support window, upgrades và deprecation?
13. **Cost:** License, cloud, network, storage, support và engineering toil?
14. **Lock-in:** API/data/identity/operational dependencies có thể rời đi thế nào?
15. **Reversibility:** Chi phí thay đổi sau khi có nhiều consumer/data?
16. **PoC:** Unknown rủi ro cao nào cần kiểm chứng?
17. **ADR:** Có ghi context, alternatives, decision, consequences và review triggers?
18. **Migration:** Rollout, compatibility, rollback và data movement?
19. **Governance:** Ai quyết định, ai được tham vấn, ngoại lệ do ai quản?
20. **Evidence:** Sau rollout, chỉ số nào xác nhận quyết định phù hợp?
21. **Exit trigger:** Điều kiện nào sẽ khiến nhóm mở lại quyết định?
22. **Scope:** Có đang chọn công nghệ để phục vụ kiến trúc hay vô tình để công nghệ áp đặt kiến trúc?

## 30. Ghi nhớ cốt lõi

- **Quyết định kiến trúc định hình cấu trúc, boundary, ownership, interaction và quality attributes.** Framework/platform là công cụ để hiện thực và vận hành những quyết định đó.
- **Không chọn framework hoặc nền tảng trước khi hiểu bài toán và constraints.** Tên công nghệ không thay thế requirement, SLO, data contract hay business semantics.
- **Một framework có thể ảnh hưởng kiến trúc**, nhưng không tự quyết định service boundary, data ownership, consistency hoặc failure behavior.
- **Platform choice có thể tạo ràng buộc dài hạn** qua identity, storage, network, deployment và vendor API; phải tính operating model và exit cost.
- **Đánh giá công nghệ bằng workload representative, security, reliability, operability, team capability và total cost**, không chỉ benchmark hoặc xu hướng.
- **Phân biệt hard constraints, assumptions và preferences** để không biến sở thích thành quy định.
- **ADR lưu lý do, trade-off, alternatives và trigger xem lại**, giúp quyết định tiến hóa có kiểm soát.
- **PoC nên kiểm chứng unknown rủi ro cao**, có workload, failure cases, measures và exit criteria rõ.
- **Giữ boundary ổn định giúp thay framework/platform dễ hơn**, nhưng abstraction chỉ đáng làm khi có lợi ích thực.
- **Đo outcome sau khi triển khai:** user journey, SLO, change lead time, recovery, security và cost trên công việc hữu ích.
- **Công nghệ phục vụ mục tiêu kiến trúc và sản phẩm; số lượng framework, platform hay công cụ không phải bằng chứng hệ thống tốt hơn.**

# Định hướng theo dòng giá trị và năng lực nghiệp vụ trong tổ chức nhóm microservices

## 1. Vấn đề: chia nhóm theo công nghệ thường làm chậm dòng giá trị

Một hệ thống microservices có thể có hàng chục dịch vụ, database, event streams và pipeline. Nhưng chỉ tách mã nguồn và chia nhỏ deployment chưa tạo ra tổ chức có khả năng đưa giá trị tới khách hàng nhanh. Nếu một thay đổi trong hành trình mua hàng phải đi qua nhóm Frontend, nhóm Java Backend, nhóm Database, nhóm Kafka, nhóm API Gateway và nhóm Vận hành, phần lớn thời gian có thể nằm ở **chờ giao việc, chuyển ngữ cảnh, làm rõ yêu cầu và kiểm thử tích hợp**, chứ không phải viết code.

Ví dụ một cải tiến “khách hàng xem được thời gian giao dự kiến trước khi thanh toán”:

```text
Yêu cầu kinh doanh
    |
    v
Frontend team (UI)
    |
    v
Backend team (API)
    |
    v
Data team (nguồn tồn kho)
    |
    v
Integration team (vận chuyển)
    |
    v
QA team (luồng tổng)
    |
    v
Operations team (triển khai)
    |
    v
Khách hàng nhận giá trị
```

Mỗi nhóm có thể tối ưu số lượng task hoàn thành, nhưng người dùng chỉ nhận giá trị **sau khi tất cả điểm nối hoạt động**. Lúc này, một microservice độc lập về kỹ thuật vẫn bị mắc kẹt trong mô hình tổ chức nhiều handoff.

Một cách định hướng là tổ chức nhóm theo:

- **Dòng giá trị (value stream):** chuỗi hoạt động từ nhu cầu/sự kiện đầu vào đến kết quả khách hàng hoặc doanh nghiệp thực sự nhận được.
- **Năng lực nghiệp vụ (business capability):** khả năng ổn định mà doanh nghiệp cần có để tạo ra hoặc hỗ trợ các dòng giá trị, ví dụ Quản lý đơn hàng, Định giá, Quản lý tồn kho, Thanh toán, Quản lý danh tính.
- **Nền tảng và chuyên môn hỗ trợ:** những khả năng dùng chung giúp các nhóm dòng giá trị làm việc tự chủ mà không phải tự xây lại hạ tầng hoặc mọi năng lực chuyên sâu.

Điểm chính là **thiết kế ranh giới trách nhiệm dựa trên luồng tạo giá trị và mô hình nghiệp vụ**, rồi dùng kiến trúc microservices để hỗ trợ; không vẽ sơ đồ tổ chức chỉ bằng cách đếm số repository, class hoặc Kubernetes Deployment.

### Mục tiêu học tập

Sau bài học, bạn có thể:
1. Phân biệt dòng giá trị, value stream mapping, business capability, domain, bounded context, microservice và team.
2. Nhận diện chi phí handoff, queue time và dependency làm chậm lead time.
3. Định hướng nhóm để sở hữu một kết quả khách hàng có thể đo lường.
4. Ánh xạ năng lực nghiệp vụ sang bounded contexts và service ownership mà không ép quan hệ một-một.
5. Phân biệt trách nhiệm stream-aligned, platform, enabling và complicated-subsystem teams khi áp dụng phù hợp.
6. Thiết kế team API, hợp đồng giao tiếp, trách nhiệm vận hành và giới hạn phụ thuộc.
7. Đánh giá tổ chức theo flow metrics, độ tin cậy, thay đổi liên nhóm và cognitive load.
8. Lập kế hoạch chuyển từ silo chức năng sang nhóm liên chức năng theo từng bước có thể kiểm chứng.

## 2. Những khái niệm cơ sở

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Value stream** | Khách hàng bắt đầu từ đâu và nhận giá trị cuối cùng gì? | Từ chọn sản phẩm đến nhận đơn hàng |
| **Value stream mapping (VSM)** | Công việc, thông tin và thời gian chờ di chuyển qua những bước nào? | Yêu cầu → phát triển → kiểm thử → phát hành |
| **Business capability** | Doanh nghiệp phải làm được điều gì, bất kể bộ phận/công nghệ? | Định giá, Quản lý tồn kho, Thu tiền |
| **Business process** | Năng lực được sử dụng theo trình tự nào để đạt một mục tiêu? | Reserve stock → authorize payment → confirm order |
| **Domain / subdomain** | Bài toán và ngôn ngữ nghiệp vụ thuộc phạm vi nào? | Commerce, Fulfillment, Payment |
| **Bounded context** | Mô hình, thuật ngữ và quy tắc nghiệp vụ có hiệu lực trong ranh giới nào? | Order Management Context |
| **Microservice** | Đơn vị runtime/API/data có thể triển khai và vận hành với boundary rõ | Orders Service |
| **Team ownership** | Ai có quyền quyết định, chịu trách nhiệm xây và vận hành? | Team Order Experience |
| **Platform capability** | Nền tảng cung cấp khả năng dùng lại theo kiểu dịch vụ cho nhóm khác? | Identity, observability, deployment platform |

**Không đồng nhất các khái niệm.** Dòng giá trị “Mua hàng” có thể dùng nhiều năng lực như Catalog, Pricing, Inventory và Payments. Một năng lực như Identity lại được dùng trong nhiều dòng giá trị. Một bounded context có thể được hiện thực bởi một hoặc nhiều runtime services; một nhóm nhỏ có thể sở hữu nhiều service. Một repository có thể chứa nhiều team-owned modules nếu ownership rõ.

Vì vậy việc áp “mỗi dòng giá trị = một microservice” hoặc “mỗi capability = một team cố định” thường quá đơn giản. Mục tiêu của mapping là giảm coupling và chuyển giao không cần thiết, không tạo tỷ lệ một-một hình thức.

## 3. Dòng giá trị: đi từ kích hoạt tới kết quả khách hàng

Một value stream cần có **trigger** (sự kiện bắt đầu), **outcome** (kết quả được ghi nhận) và các bước tạo/không tạo giá trị nằm giữa.

Ví dụ dòng giá trị “Đặt và nhận hàng”:

```text
Khách chọn sản phẩm
        |
        v
Xem giá và tồn kho
        |
        v
Đặt hàng
        |
        v
Xác nhận thanh toán
        |
        v
Chuẩn bị và bàn giao vận chuyển
        |
        v
Khách nhận hàng và theo dõi trạng thái
```

Các hoạt động này có thể sử dụng nhiều business capabilities:
- Quản lý Catalog.
- Định giá và khuyến mại.
- Đảm bảo tồn kho.
- Xử lý đơn hàng.
- Chấp nhận thanh toán.
- Điều phối fulfillment.
- Thông báo và theo dõi.
- Chăm sóc sau bán.

Giá trị không chỉ là số API hoạt động. Với khách hàng, kết quả có thể là “đặt thành công, được thu đúng số tiền, nhận đúng hàng và biết thời gian giao”. Từ góc nhìn doanh nghiệp, còn có chi phí xử lý đơn, tỷ lệ hoàn tiền, thời gian fulfill, độ chính xác tồn kho và mức tin cậy.

### Product value stream và delivery value stream

Có hai góc nhìn thường dùng:
1. **Operational/customer value stream:** cách nghiệp vụ cung cấp giá trị trực tiếp cho khách hàng, ví dụ tạo đơn đến giao hàng.
2. **Development/delivery value stream:** cách một ý tưởng/chỉnh sửa đi từ nhu cầu đến phần mềm hoạt động và được người dùng sử dụng.

Chia nhóm tốt cần quan sát cả hai. Một nhóm sở hữu “trải nghiệm thanh toán” có thể tổ chức công nghệ rất tốt nhưng vẫn chờ legal approval, risk policy hoặc API của đối tác. Ngược lại, pipeline deploy vài phút không chứng minh hành trình người dùng đã được cải thiện.

## 4. Năng lực nghiệp vụ: tương đối ổn định dù quy trình thay đổi

**Business capability** mô tả điều doanh nghiệp **có khả năng làm**, không nhất thiết mô tả một phòng ban hiện tại hay một bước tuần tự của quy trình.

Ví dụ một bản đồ capability đơn giản:

```text
Commerce Business Capabilities
|
+-- Customer Management
|    +-- Identity & Access
|    +-- Customer Profile
|    +-- Customer Support
|
+-- Product & Offer Management
|    +-- Catalog
|    +-- Pricing
|    +-- Promotions
|
+-- Order Lifecycle
|    +-- Cart & Checkout
|    +-- Order Management
|    +-- Returns & Refunds
|
+-- Fulfillment
|    +-- Inventory Availability
|    +-- Reservation
|    +-- Shipping Orchestration
|
+-- Financial Operations
     +-- Payment Authorization
     +-- Capture & Settlement
     +-- Reconciliation
```

Một số capability thay đổi ít qua nhiều năm dù UI, API, workflow hoặc tổ chức thay đổi. Đây là lợi thế khi xác định ranh giới **quyền sở hữu dữ liệu và logic nghiệp vụ**.

Tuy nhiên:
- Một capability cấp cao có thể quá rộng để một team sở hữu hết, ví dụ “Fulfillment”.
- Một capability rất nhỏ có thể không đủ giá trị để tạo team/service riêng.
- Một capability có thể phục vụ nhiều value streams, ví dụ Fraud Detection.
- Một domain cần mô hình thuật ngữ và invariants riêng không thể phân biệt bằng sơ đồ tổ chức hiện tại.

Khi map sang microservices, cần xem **cohesion, tốc độ thay đổi, data ownership, nghiệp vụ và tải nhận thức**, chứ không chỉ tên trong capability map.

## 5. Value stream và capability liên hệ như thế nào?

Value stream là **dòng chảy theo chiều thời gian của kết quả**; capability là **khả năng được huy động** tại nhiều bước của dòng chảy.

| Dòng giá trị | Capability được sử dụng | Kết quả mong đợi |
| --- | --- | --- |
| Đặt hàng | Catalog, Pricing, Inventory, Checkout, Payment | Đơn được xác nhận hợp lệ |
| Giao hàng | Order, Warehouse, Shipping, Notification | Hàng được bàn giao và theo dõi |
| Hoàn trả | Returns, Inventory, Refunds, Customer Support | Khách nhận quyết định và hoàn tiền đúng |
| Onboarding người bán | Identity, Compliance, Merchant Profile, Catalog | Người bán đủ điều kiện hoạt động |
| Xử lý khiếu nại | Customer Support, Payment Reconciliation, Order | Khiếu nại được giải quyết có bằng chứng |

Các capability dùng chung không nhất thiết “thuộc” một dòng giá trị duy nhất. Điều này dẫn đến một lựa chọn thiết kế quan trọng:

- Nhóm **stream-aligned** tập trung vào outcome của một dòng giá trị hoặc phân đoạn có ý nghĩa.
- Nhóm **capability/domain** giữ logic chuyên sâu hoặc dữ liệu có ý nghĩa được nhiều dòng giá trị dùng.
- Nhóm **platform** cung cấp khả năng công nghệ dùng chung dưới dạng sản phẩm nội bộ.
- Khi cần, **enabling team** hỗ trợ nâng năng lực các nhóm khác trong thời hạn và phạm vi rõ.

Không nên tạo một nhóm “Payment UI” và một nhóm “Payment DB” chỉ vì kỹ năng khác nhau nếu mục tiêu là phát hành Payment changes tự chủ. Nhưng Payment domain vẫn có thể là một bounded context chuyên biệt phục vụ nhiều hành trình.

## 6. Tổ chức theo lớp kỹ thuật (functional silo) và những hệ quả

Mô hình silo thường hình thành vì tiện quản trị kỹ năng:

```text
Head of Engineering
   |
   +-- Frontend Team
   +-- Backend Team
   +-- Database Team
   +-- Test Team
   +-- DevOps Team
```

Ưu điểm có thể gồm tiêu chuẩn kỹ thuật chuyên sâu, mentoring dễ trong từng chuyên môn và phân bổ người cho công việc đột xuất. Nhưng đối với sản phẩm phát triển liên tục, nó có thể tạo hàng đợi chuyển giao.

Một user story:
1. Frontend làm UI và chờ endpoint.
2. Backend chờ schema migration.
3. Database team ưu tiên công việc khác.
4. QA chờ build tích hợp.
5. Operations nhận yêu cầu phát hành cuối sprint.
6. Khi lỗi production, nhiều nhóm phải phối hợp xác định nguồn.

Cả năm team có thể đạt utilization cao trong khi **cycle time của một yêu cầu** rất dài.

Ngược lại, nhóm liên chức năng sở hữu một kết quả có thể chủ động từ requirement đến vận hành:

```text
Order Experience Team
  Product + Design + Backend + Frontend + Test/Quality
  + đủ năng lực vận hành/observability
           |
           v
  Idea → API/UI/data change → tests → deploy → measure
```

Không có nghĩa mỗi team phải thuê đầy đủ mọi chuyên gia hiếm. Nền tảng tự phục vụ, pair/coaching và shared standards giúp nhóm giữ khả năng tự chủ mà không nhân bản toàn bộ chức năng hạ tầng.

## 7. Team Topologies như mô hình tương tác để giảm cognitive load

Khi áp dụng các khái niệm Team Topologies, có bốn **loại team** thường được mô tả:

| Loại team | Mục đích chính | Dạng giá trị |
| --- | --- | --- |
| **Stream-aligned team** | Sở hữu một dòng hoặc phân đoạn giá trị có ý nghĩa với người dùng | Tính năng và trải nghiệm end-to-end |
| **Platform team** | Cung cấp nền tảng nội bộ dễ tiêu thụ, giảm gánh nặng cho các team khác | Self-service platform capabilities |
| **Enabling team** | Giúp các team khác vượt rào cản năng lực/kỹ thuật trong một giai đoạn | Coaching, facilitation, adoption |
| **Complicated-subsystem team** | Sở hữu phần chuyên môn sâu, khó phân tán nếu nhiều nhóm tự xây | Engine thuật toán, tối ưu routing, specialized risk model |

Các loại team không nhất thiết phải trở thành bốn department cố định. Cần điều chỉnh theo quy mô, nguồn lực và tính phức tạp. Một startup vài người có thể thực hiện nhiều vai trò trong cùng một nhóm, miễn vai trò và quyền quyết định rõ.

Một nguyên tắc quan trọng là **giảm cognitive load**: đội phát triển phải hiểu vừa đủ code, domain, pipeline, hạ tầng và vận hành để ra quyết định đáng tin cậy. Nếu một team sở hữu 45 services, 8 loại database và 3 business domains phức tạp, sự tự chủ trên sơ đồ tổ chức có thể không tồn tại trong thực tế.

## 8. Ba kiểu tương tác giữa các team

Một mô hình phối hợp có thể dùng ba kiểu tương tác có mục đích rõ:

### Collaboration — hợp tác chuyên sâu trong thời gian giới hạn

Hai team cần khám phá ranh giới mới, thiết kế contract hoặc giải bài toán chưa rõ:

```text
Checkout Team ←→ Payments Team
  cùng thiết kế trạng thái "authorization unknown"
  thống nhất idempotency key, callback và timeout
```

Collaboration không nên kéo dài mãi cho các thay đổi bình thường. Nếu mọi release phải họp chung mới làm được, contract hoặc ownership đang chưa đủ rõ.

### X-as-a-Service — tiêu thụ khả năng đã được đóng gói

Platform hoặc domain team cung cấp API, SDK, tài liệu, quota và SLA/SLO nội bộ:

```text
Order Team
   |
   +--> Payment API (versioned contract)
   +--> Deployment Platform (self-service pipelines)
   +--> Observability Platform (traces/metrics)
```

Consumer biết cách tự sử dụng mà không cần mở ticket để mỗi lần được tạo topic, environment hoặc dashboard. Chỉ có cổng self-service không đủ; cần reliability, support channel và feedback loop.

### Facilitating — hỗ trợ học và cải thiện năng lực

Enabling team giúp một nhóm áp dụng contract testing, threat modeling, SLO, container security hoặc data migration:

```text
Enabling Team  --coaching-->  Order Team
  workshop + pair implementation + templates
  → Order Team tự duy trì sau giai đoạn hỗ trợ
```

Facilitating thành công khi team nhận hỗ trợ **tự làm được**, không phụ thuộc vĩnh viễn vào enabling team để phê duyệt từng thao tác.

## 9. Không đồng nhất stream-aligned team với một service

Một lỗi hay gặp là vẽ:

```text
Service A → Team A
Service B → Team B
Service C → Team C
```

... rồi kết luận đó là tổ chức theo value stream. Đây chỉ là ánh xạ ownership theo artifact. Nếu A, B, C phải thay đồng thời cho mỗi user story, nhóm vẫn tốn nhiều handoff.

Một nhóm có thể sở hữu:
- Một service lớn nhưng cohesive.
- Vài services thuộc cùng bounded context hoặc phân đoạn hành trình.
- Một frontend + backend-for-frontend + worker + schema được phân quyền rõ.
- Nhiều artifacts cần deploy riêng nhưng cùng phục vụ outcome.

Ngược lại, một business capability như Payments có thể cần team chuyên biệt vì rủi ro tài chính, compliance, quy tắc settlement và trách nhiệm on-call. Nó vẫn có thể cung cấp contract tốt để nhóm Checkout không phải phụ thuộc vào lịch deploy của Payments.

**Service boundary cần được suy ra từ domain, data ownership, failure isolation và tốc độ thay đổi. Team boundary cần được thiết kế để sở hữu và vận hành các boundary đó với tải nhận thức hợp lý.** Không ép tỷ lệ một-một nếu nó làm tổ chức chậm hơn.

## 10. Domain-Driven Design và bounded contexts

Domain-Driven Design (DDD) giúp phân biệt mô hình nghiệp vụ giữa các ngữ cảnh.

Ví dụ từ `Order` không nhất thiết cùng nghĩa:
- Trong Checkout: một giỏ hàng đang chờ xác nhận.
- Trong Order Management: đơn có vòng đời tạo, xác nhận, hủy.
- Trong Fulfillment: yêu cầu lấy hàng và giao hàng.
- Trong Accounting: nghiệp vụ ghi nhận doanh thu/thu tiền.

Nếu dùng một `OrderEntity` chung cho tất cả service, có nguy cơ biến các bounded contexts thành một shared data model khó thay đổi. Một team thay field sẽ làm nhiều team bị ảnh hưởng dù họ không cùng một invariant.

Ví dụ context map đơn giản:

```text
[Checkout Context]
    |
    | PlaceOrder command / CheckoutCompleted event
    v
[Order Management Context]
    |
    | OrderReadyForFulfillment event
    v
[Fulfillment Context]
    |
    +--> [Shipping Provider ACL]

[Payment Context]
    |
    +--> PaymentAuthorized/PaymentCaptured contracts
```

ACL (Anti-Corruption Layer) ở Fulfillment có thể chuyển đổi ngôn ngữ bên ngoài thành mô hình nội bộ, không để provider áp đặt DTO vào toàn domain.

### Kết nối capability map với DDD

1. Tìm capability quan trọng và các từ vựng nghiệp vụ.
2. Xác định invariants và transactional boundaries.
3. Xác định bounded contexts có mô hình riêng, data owner rõ.
4. Xem những contexts nào được thay đổi thường xuyên cùng nhau.
5. Gán ownership cho team có khả năng vận hành chúng.
6. Thiết kế integration bằng public contract, không chia sẻ internal tables.
7. Đánh giá lại khi năng lực hoặc dòng giá trị thay đổi.

**Capability không tự động là bounded context.** Một capability rộng có thể có nhiều contexts; ngược lại nhiều capability nhỏ có thể được phục vụ chung một context nếu mô hình thống nhất và thay đổi cùng nhau.

## 11. Team ownership phải gắn với kết quả và hệ thống

Một sơ đồ owner tốt có thể mô tả:

| Team | Outcome chính | Artifacts có thể sở hữu | Biên phối hợp |
| --- | --- | --- | --- |
| Checkout Experience | Người mua hoàn tất đặt hàng nhanh, đúng | UI checkout, Checkout API, orchestration | Payment, Inventory, Identity |
| Order Lifecycle | Đơn có trạng thái chính xác, có thể tra cứu và hủy | Orders API, DB, events, projection | Fulfillment, Payments |
| Fulfillment | Giao đúng hàng, đúng hẹn | Reservation/Shipping orchestration, worker | Warehouse, Providers |
| Payments | Thu tiền chính xác, không trùng, đối soát được | Payment API, ledger, reconciliation | Provider, Finance |
| Platform Engineering | Teams deploy và vận hành tự phục vụ | CI templates, K8s platform, telemetry | Mọi stream team |
| Enablement | Nâng năng lực thực hành cho teams | Workshop, patterns, mentoring | Team cần hỗ trợ |

Bảng là ví dụ, không phải ranh giới chuẩn cho mọi doanh nghiệp. Nếu Checkout và Order Lifecycle thường phải triển khai đồng thời, có thể cân nhắc gộp ownership hoặc làm rõ contract. Nếu Fulfillment gồm chuyên môn kho hàng và routing khó, có thể tách subsystem team chuyên biệt.

Ownership tối thiểu nên bao gồm:
- API và event contracts.
- Business rules, data schema/quality và security boundary.
- Build/test/deploy pipeline, artifact versions.
- Observability và SLO của chức năng.
- Incident response, runbook, on-call/escalation.
- Quy trình deprecation/migration khi ảnh hưởng consumer.
- Quyền ưu tiên backlog sản phẩm và reliability work.

Team chỉ “viết code” còn mọi kiểm thử, release và khắc phục sự cố do một hàng đợi tập trung đảm nhiệm có thể thiếu quyền sở hữu end-to-end.

## 12. Chọn dòng giá trị ở mức đủ nhỏ để một nhóm có thể kiểm soát

Value stream có thể rất dài: “khách thấy quảng cáo → mua → giao → hoàn hàng → chăm sóc”. Một team không thể luôn sở hữu toàn bộ công ty.

Khi xác định stream-aligned team, tìm **phân đoạn có outcome ổn định và đủ tự chủ**:

```text
Acquire Customer  |  Shop & Checkout  |  Fulfill Order  |  Support & Returns
       |                   |                  |                   |
     Team A              Team B             Team C               Team D
```

Mỗi phân đoạn có thể có:
- Trigger và outcome rõ.
- Khách hàng trực tiếp hoặc nội bộ xác định được.
- Năng lực kỹ thuật và nghiệp vụ đội cần làm chủ.
- Phạm vi dữ liệu, dependencies và tiêu chuẩn chất lượng.
- Metrics không yêu cầu chỉnh nhiều nhóm khác mới có tác động.

Ví dụ “Checkout Experience” không nhất thiết sở hữu settlement ledger. Team ấy nên sở hữu trải nghiệm và orchestration, còn Payments cung cấp một hợp đồng kết quả có tính tin cậy, để hai bên phát hành riêng.

**Đừng chia theo màn hình** nếu màn hình không tương ứng với boundary nghiệp vụ hoặc nếu logic chính vẫn nằm ở nhóm khác. “Team nút Thanh toán” không phải một stream team chỉ vì có một nút UI.

## 13. Dùng Value Stream Mapping để tìm bottleneck thật

Value Stream Mapping không chỉ liệt kê các bước; nó đo **thời gian xử lý (process time)** và **thời gian chờ (wait time)**.

Ví dụ giả định cho một user story:

| Bước | Process time | Wait time |
| --- | ---: | ---: |
| Làm rõ yêu cầu | 2 giờ | 1 ngày |
| Backend | 6 giờ | 2 ngày chờ API review |
| Frontend | 5 giờ | 1 ngày chờ backend |
| QA tích hợp | 3 giờ | 2 ngày chờ environment |
| Phê duyệt release | 1 giờ | 3 ngày |
| **Tổng xử lý** | **17 giờ** | **9 ngày** |

Các con số chỉ minh họa. Tổng lead time không đơn giản luôn bằng tổng nếu công việc có thể chạy song song, nhưng bảng cho thấy thời gian chờ thường đáng kể hơn thời gian tạo giá trị.

Quy trình mapping:
1. Chọn một loại yêu cầu đã hoàn tất và có hành trình thực.
2. Theo dõi từ lúc có nhu cầu tới lúc user nhận kết quả; không dừng ở “PR merged”.
3. Ghi handoffs, review queues, môi trường kiểm thử, approval và incident hồi phục.
4. Đo process time, wait time, rework và batching.
5. Nhận diện ranh giới gây chậm vì ownership, coupling hoặc công cụ.
6. Thiết kế future state với ít queue hơn và API/platform self-service.
7. Thử trong một phạm vi nhỏ và đo lại.
8. Điều chỉnh tổ chức hoặc kiến trúc nếu bottleneck còn tồn tại.

Không khuyến khích tối ưu để mọi người có utilization 100%: hàng đợi thường lớn khi hệ thống luôn đầy tải. Tập trung vào **flow efficiency** và outcome chung.

## 14. Flow efficiency và công việc đang chờ

Một phép tính minh họa:

```text
Flow efficiency =
  active work time / total elapsed time
```

Nếu 17 giờ thực sự làm việc trong chu trình kéo dài 10 ngày làm việc, tỷ lệ rất thấp. Tuy nhiên cách quy đổi giờ/ngày và loại việc đo phải nhất quán; ví dụ chỉ minh họa vì môi trường thực có công việc song song và các loại chờ hợp lệ.

Các nguyên nhân:
- Backlog của team chuyên môn tập trung.
- Chờ review từ người không biết ngữ cảnh domain.
- Test environment dùng chung và thiếu ổn định.
- Mỗi PR liên service cần nhiều approval không rõ thời hạn.
- Batch deploy lớn khiến thay đổi phải chờ release train.
- Nợ contract khiến producer và consumer phải đổi cùng thời điểm.
- Product backlog không được gắn cùng owner với technical dependencies.

Cách giảm:
- Cross-functional ownership của những bước thường đi cùng nhau.
- Contract-first và backward-compatible change.
- Self-service test/deploy environments.
- Review policy theo ownership path, tránh approval chung chung.
- Canary và automated rollback giảm chi phí kiểm soát release.
- Giới hạn WIP, giảm số ticket chạy song song.
- Đồng bộ ưu tiên các dependent teams thay vì gửi yêu cầu không có committed owner.

## 15. Thay đổi tổ chức không thể sửa coupling kiến trúc bằng phép màu

Nếu ba service có chung DB schema và cần deploy lockstep, việc gộp người vào một team giúp họ phối hợp nhanh hơn nhưng không làm hệ thống triển khai độc lập.

Ngược lại, nếu một flow có ba microservices với APIs backward compatible, khác nhóm sở hữu chưa chắc là bottleneck lớn; các nhóm vẫn có thể phát hành riêng nhờ hợp đồng ổn định.

Phải đánh giá hai chiều:

| | Kiến trúc coupling thấp | Kiến trúc coupling cao |
| --- | --- | --- |
| Phối hợp tốt | Flow nhanh và có thể vận hành tự chủ | Có thể làm nhanh lúc đầu nhưng dễ lockstep |
| Phối hợp kém | Dư địa cải thiện bằng ownership, policy và self-service | Vừa chậm vừa dễ lỗi liên service |

Những việc cần làm đồng thời:
- Tách business invariants và data ownership.
- Định nghĩa contract API/event ổn định, có version.
- Triển khai backward/forward compatibility theo rollout window.
- Giảm handoff và approval không tạo thêm bằng chứng.
- Cải thiện tooling, observability và quyền của nhóm sở hữu.
- Theo dõi cross-team change rate và incident propagation.

**Tổ chức và kiến trúc tác động lẫn nhau**; một sơ đồ team mới nhưng dependency graph và data ownership giữ nguyên có thể chỉ đổi nhãn của vấn đề.

## 16. Conway's Law và reverse Conway maneuver

Conway's Law mô tả xu hướng cấu trúc hệ thống phản ánh cấu trúc giao tiếp của tổ chức. Ví dụ:
- Nếu DB team kiểm soát mọi thay đổi schema, schema có thể trở thành điểm kết nối trung tâm.
- Nếu Frontend và Backend liên lạc qua ticket, API có thể trở thành handoff boundary thay vì product boundary.
- Nếu một nhóm sở hữu toàn bộ shared integration layer, mọi flow có thể phụ thuộc vào nhóm đó.

Một **reverse Conway maneuver** là chủ động điều chỉnh quan hệ nhóm, ownership và kênh phối hợp để khuyến khích kiến trúc mong muốn.

Ví dụ mục tiêu là:
```text
Checkout owns orchestration + UI
Order owns order lifecycle + DB
Payment owns payment ledger + provider
Platform supplies self-service capabilities
```

Tổ chức nên tạo cơ chế:
- Team Checkout thực sự có quyền thay đổi frontend và orchestration.
- Team Payment có API và contract đảm bảo compatibility, không yêu cầu Checkout chỉnh internal tables.
- Platform cung cấp pipeline/observability mà Checkout có thể sử dụng tự phục vụ.
- Các team cùng định nghĩa E2E journey SLI và escalation.

Không nên hiểu reverse Conway là đổi sơ đồ tổ chức một lần rồi mặc nhiên kiến trúc sẽ đổi. Nó là giả thuyết thiết kế cần được kiểm chứng bằng thay đổi hành vi, kiến trúc và kết quả.

## 17. Microservice boundaries dựa trên business capabilities

Một hướng tiếp cận:
1. Xác định các domain và capability ổn định.
2. Lấy các invariants, data lifecycle và thuật ngữ nghiệp vụ.
3. Xác định bounded contexts.
4. Chọn transactional boundaries theo rules.
5. Tìm coupling theo thay đổi thực tế (những file/service nào thường đổi cùng).
6. Chọn service boundaries hỗ trợ deployment, runtime isolation và ownership.
7. Ánh xạ teams vào tập artifacts mà cognitive load cho phép.
8. Xác định public integration contracts và những coordination points cần thiết.

Không dùng kỹ thuật chia máy móc như “một bảng database = một service”:
- Order và OrderLine có thể cùng invariant, nên thuộc cùng transaction và context.
- Các read projections có thể là service/job khác về mặt runtime nhưng cùng ownership.
- Một schema DB nhiều bảng có thể là boundary của một context.
- Một external gateway integration có thể thuộc capability Payment dù nó là client library.

Đặc biệt cẩn trọng với **distributed monolith**: service tách thành 15 repositories nhưng một request phải gọi tuần tự qua tất cả, share database và deploy cùng lịch; việc tách khiến latency, failure handling và tổ chức phức tạp hơn mà không tăng tốc thay đổi.

## 18. Khi nào nên gộp và khi nào nên tách ownership?

### Cân nhắc gộp phạm vi khi

- Hai team liên tục phải sửa cùng một nghiệp vụ cho gần mọi user story.
- Một team không thể đưa outcome ra production khi team khác chưa hoàn thành handoff lặp lại.
- Hai services dùng chung data model quá chặt và chưa có bounded-context boundary thực.
- Ownership mơ hồ khiến incident luôn tranh luận “lỗi của ai”.
- Khối lượng công việc mỗi nhóm quá nhỏ để duy trì full lifecycle và on-call.
- Product decisions ở hai nhóm thường bị lệch nhưng ảnh hưởng một outcome duy nhất.

### Cân nhắc tách khi

- Business capability có invariants và data ownership riêng, thay đổi với nhịp riêng.
- Team hiện tại vượt cognitive load, không còn hiểu hết domain và runtime.
- Có vùng chuyên môn sâu cần tập trung bảo mật hoặc compliance.
- Một subsystem có thuật toán/phần cứng/chuyên gia hiếm, không nên nhân bản.
- Customer segments hoặc value streams có nhu cầu phát triển độc lập.
- Runtime tải cao/cô lập lỗi khác biệt và contract đã rõ.

**Gộp team không nhất thiết gộp service. Tách service không nhất thiết tách team.** Đây là hai quyết định riêng phải hỗ trợ nhau.

## 19. Shared capabilities: tự phục vụ thay vì cổng phê duyệt

Nhiều team cùng cần CI/CD, telemetry, secrets, authentication scaffolding, Kafka topics và container platform. Nếu mỗi team tự xây, cognitive load và rủi ro security tăng. Nếu tất cả phải gửi ticket tới platform team, flow bị chậm.

Một **platform-as-a-product**:
- Có người dùng nội bộ cụ thể: stream-aligned teams.
- Có product manager/owner và roadmap.
- Có documentation, templates, SDK/CLI, self-service UI/API.
- Có service catalog và “golden paths” cho tác vụ lặp lại.
- Có SLO/incident support, feedback loop, adoption và cost visibility.
- Có cơ chế exception cho yêu cầu khác biệt có căn cứ.
- Cung cấp **capability**, không ép business teams giao mọi decision cho Platform.

Ví dụ golden path:

```text
Create new business API
  → chọn service template
  → provision namespace/secrets policy
  → build/test/image signing
  → deploy canary
  → create dashboard + tracing
  → set SLO/alerts
  → team sở hữu service tiếp tục tự vận hành
```

Platform có thể đặt guardrails tự động cho bảo mật và compliance, nhưng không nên biến mỗi release thành yêu cầu phê duyệt thủ công nếu hệ thống đã có bằng chứng tự động đủ.

## 20. Enabling teams và năng lực chuyên gia

Một số kỹ năng không phổ biến ở mọi stream team:
- Threat modeling và security architecture.
- Database migration/partitioning ở quy mô lớn.
- Contract testing hoặc distributed tracing.
- Performance profiling hoặc chaos engineering.
- Event-driven idempotency và recovery semantics.
- Accessibility và trải nghiệm người dùng đặc thù.

Một enabling team có thể hỗ trợ theo vòng:
1. Chọn vấn đề có thể xác định outcome.
2. Thực hiện workshop/pairing cùng stream team.
3. Tạo mẫu thực tế trong code của team nhận hỗ trợ.
4. Chuyển quyền sở hữu và khả năng duy trì cho team đó.
5. Đo kết quả: giảm incidents, tăng test coverage hành vi, rút ngắn lead time.
6. Kết thúc nhiệm vụ hoặc chuyển sang nhóm khác.

Không biến enabling team thành “bộ phận duyệt kiến trúc mọi API” vô thời hạn. Với quy tắc bảo mật bắt buộc, nên tự động hóa guardrail và có escalation path cho ngoại lệ, thay vì duy trì queue lớn.

## 21. Complicated-subsystem team: khi chuyên môn sâu khó phân tán

Ví dụ năng lực Fraud Scoring có:
- Mô hình xác suất phức tạp.
- Dữ liệu đặc thù và thuật toán chuyên sâu.
- Yêu cầu kiểm chứng/regulatory nghiêm ngặt.
- Chi phí sai lầm cao và kỹ năng hiếm.

Nếu mỗi stream team tự xây một fraud model, kết quả có thể không nhất quán, nhiều nợ kỹ thuật và rủi ro. Một đội chuyên trách có thể cung cấp:

```text
Fraud Decision API
  POST /risk-decisions
  inputs: transaction facts, operation ID
  outputs: decision, reason category, policy version
```

Nhưng team này phải cung cấp giao diện rõ ràng, timeout/SLO, versioning và giải thích kết quả đủ cho consumer. Nếu stream team cần chuyên gia Fraud tham gia mọi checkout change, boundary API chưa đủ tự chủ.

Đây là lý do giữ loại team chuyên sâu như một lựa chọn, **không đặt mọi business capability thành platform team**.

## 22. Ví dụ tổ chức cho nền tảng thương mại điện tử

Giả sử công ty có:
- Một ứng dụng mobile/web.
- Các năng lực catalog, pricing, checkout, inventory, payment, shipping, returns.
- Các dịch vụ nền identity, observability và CI/CD.
- Nhu cầu triển khai độc lập nhưng vẫn có business journeys xuyên service.

Một tổ chức minh họa:

```text
Product & Engineering
|
+-- Shop & Discover Stream
|    +-- Product Discovery team
|    +-- Offer & Pricing team
|
+-- Purchase Stream
|    +-- Checkout Experience team
|    +-- Order Lifecycle team
|
+-- Fulfillment Stream
|    +-- Inventory & Reservation team
|    +-- Shipping Experience team
|
+-- After-Sales Stream
|    +-- Returns & Support team
|
+-- Domain/Specialized Capability
|    +-- Payments & Reconciliation team
|
+-- Internal Platform
|    +-- Developer Platform team
|    +-- Reliability/Observability capability
|
+-- Enabling (time-bounded engagements)
     +-- Security and Resilience Coaching
```

Tùy quy mô, có thể gộp vài team hoặc tách sâu hơn. Điều quan trọng là **từng dòng giá trị có outcome owner**, các capabilities chia sẻ có public contract, và người hỗ trợ nền tảng không phải trở thành người viết business logic cho mọi stream.

### Bảng giao tiếp

| Team sản phẩm | Năng lực cần dùng | Kiểu tương tác ưu tiên |
| --- | --- | --- |
| Checkout | Payment Authorization | API contract + SLO; collaborate khi đổi giao thức |
| Order Lifecycle | Inventory reservation | Event/API contract, reconciliation |
| Shipping Experience | Provider integrations | Capability API hoặc subsystem có owner |
| Mọi stream team | CI/CD và observability | Platform self-service |
| Team mới | Contract testing | Enabling team hỗ trợ trong giai đoạn |
| Fraud specialists | Risk scoring | Versioned decision API |

Nếu hầu hết task thường xuyên cần vài team cùng approve trực tiếp, xem lại interface và ưu tiên; không đơn thuần tăng số cuộc họp.

## 23. Các hợp đồng giữa nhóm: “team API”

**Team API** là mô tả có thể tìm thấy về cách làm việc với một team, bên cạnh API kỹ thuật.

Nội dung nên gồm:
- Team chịu trách nhiệm outcome gì.
- Service/repo/data/contract nào thuộc ownership.
- Dịch vụ cung cấp cho nội bộ/ngoài là gì và ai là consumer.
- Cách yêu cầu thay đổi: backlog/issue hoặc product discussion.
- Response expectation cho câu hỏi, incident và change review.
- SLO, support channel và escalation.
- Quy định versioning, deprecation và breaking change.
- Lịch release/canary và thông báo thay đổi nếu cần.
- Những việc self-service không cần sự can thiệp của team.
- Thời hạn collaboration khi có nhiệm vụ chung.

Ví dụ tài liệu nhỏ:

```markdown
# Team API — Payment Capability

Mission:
  Thu tiền chính xác, có đối soát, không tạo capture trùng.

Owns:
  Payment Service, Payments DB, payment-events contracts.

Provides:
  POST /authorizations
  POST /captures (idempotency key required)
  GET /operations/{id}
  PaymentCaptured / PaymentFailed events.

Reliability:
  SLO đo theo operation outcome.
  Dashboard và runbook có trong service catalog.

Engagement:
  Tích hợp chuẩn: xem API docs + sandbox.
  Breaking contract: RFC, consumer verification,
  staged rollout và deprecation window.
  Incident: on-call escalation channel.
```

Đây là mẫu minh họa. Quan trọng là định nghĩa **cách tiêu thụ khả năng và trách nhiệm khi lỗi** để nhóm khác không phải đoán hoặc phụ thuộc vào một cá nhân.

## 24. Team boundaries và data ownership

Một đặc điểm then chốt của microservices là quyền sở hữu dữ liệu:
- Team Order Lifecycle là owner của Order state, schema và invariants.
- Team Payments là owner của Payment ledger và provider reconciliation.
- Team Inventory là owner của reservation/available stock.
- Các nhóm khác sử dụng public API/event hoặc projection có contract.

Không nên cho Checkout query trực tiếp bảng internal của Payments chỉ vì hai team đang cùng công ty. Việc đọc chung bảng có thể làm schema migration trở thành công việc phối hợp lockstep; team Payment mất quyền thay đổi implementation.

Một bản đồ ownership:

```text
Checkout Team
   |  PaymentOperationRequested
   v
Payments Team ---> Payments DB [owned here]
   | PaymentAuthorized/Failed
   v
Checkout/Order Teams

Order Lifecycle Team ---> Orders DB [owned here]
   |
   +-- OrderStatusChanged --> Search Projection

Inventory Team ---> Inventory DB [owned here]
```

**Data product** hoặc shared analytics cần quyền truy cập, provenance, schema evolution và SLO theo nguồn. Không tự động biến warehouse thành shared database cho business writes.

Nếu team không có quyền thay đổi data schema của capability họ sở hữu, hãy ghi rõ delegation/collaboration thực tế và tìm cách giảm dependency thay vì tuyên bố họ đã hoàn toàn tự chủ.

## 25. Thay đổi contract mà không bắt mọi team deploy đồng thời

Giả sử Payments muốn thêm trạng thái `PENDING_REVIEW`, Checkout chưa hiểu. Dù tổ chức theo capability tốt, breaking change có thể làm hỏng cả dòng giá trị.

Một lộ trình:

```text
1) Payments xuất bản contract mở rộng, không bỏ trạng thái cũ
2) Consumer contract verification xác nhận versions được hỗ trợ
3) Checkout/Order xử lý PENDING_REVIEW như trạng thái hợp lệ
4) Các consumer mới được triển khai, quan sát mixed versions
5) Payments bắt đầu phát trạng thái mới có kiểm soát
6) Quan sát và bỏ đường cũ sau cửa sổ deprecation
```

Có thể dùng API schema registry/consumer-driven contracts và event compatibility checks. Nhưng cần xét **semantics**: enum mới không chỉ là field mới; các consumer phải biết xử lý thay vì parse thành lỗi hoặc xác nhận thanh toán sai.

Một hợp đồng team nên trả lời:
- Ai đề xuất và duyệt breaking contract?
- Consumer versions nào đang được hỗ trợ?
- Ai xác nhận tất cả consumer quan trọng đã được nâng cấp?
- Có migration/feature flag và rollback plan chưa?
- Khi runtime có old/new versions, trạng thái dữ liệu còn tương thích không?

**Giảm handoff không đồng nghĩa bỏ phối hợp quan trọng.** Mục tiêu là có giao diện rõ để việc thay đổi bình thường không phải phụ thuộc thủ công mỗi lần.

## 26. Quyền sở hữu SLO theo outcome và service

Mỗi team có thể sở hữu SLO của dịch vụ, nhưng dòng giá trị nhiều service còn cần SLI theo hành trình.

Ví dụ:

| Cấp | SLI | Owner đề xuất |
| --- | --- | --- |
| User journey | Tỷ lệ checkout hoàn tất đúng trong 2 giây | Checkout Value Stream Owner |
| Service | Checkout API đáp ứng hợp đồng | Checkout Team |
| Service | Payment operation có kết quả đúng, không trùng | Payment Team |
| Service | Inventory reservation chính xác | Inventory Team |
| Platform | CI/deployment self-service availability | Platform Team |
| Analytics | Search projection freshness | Discovery/Search owner |

Các ngưỡng là ví dụ; phải xác định population và good events rõ ràng. Một service trả HTTP 200 nhưng workflow treo không nên được coi là user success.

Khi outage xảy ra:
- Stream owner chịu trách nhiệm nhìn tổng user impact và điều phối.
- Service owner chịu trách nhiệm sửa lỗi nằm ở service hoặc data của mình.
- Platform owner hỗ trợ các failure domains chung.
- Product quyết định ưu tiên và thông báo theo outcome.
- Incident commander điều phối khi nhiều team tham gia.

Tránh việc cả ba team “đạt service SLO” nhưng không team nào chịu trách nhiệm checkout journey đang thất bại.

## 27. Product management và kiến trúc phải cùng backlog

Nếu team được gọi là stream-aligned nhưng backlog chỉ chứa các phần việc được bàn giao từ bộ phận khác, họ vẫn thiếu quyền ưu tiên theo outcome.

Một stream team nên có:
- Product goal hoặc business outcome rõ.
- Quyền lựa chọn giải pháp kỹ thuật trong guardrails.
- Backlog bao gồm features, reliability, security và tech debt.
- Feedback từ khách hàng, dữ liệu hành vi và production metrics.
- Khả năng release/canary/rollback trong phạm vi service owner.
- Kênh phối hợp rõ khi cần capability từ team khác.

Ví dụ cùng một KPI “giảm checkout abandonment” có thể khiến team lựa chọn:
- Tăng tốc hiển thị phí vận chuyển.
- Cải thiện validation form.
- Rút ngắn xác nhận thanh toán.
- Thêm trạng thái pending có thông tin rõ.
- Giảm timeout/retry gây treo UI.
- Đo thí nghiệm và khả năng quan sát.

Nếu một team chỉ được giao “làm API X” nhưng không biết API có cải thiện checkout hay không, họ đang vận hành như nhóm giao việc theo component, chưa thực sự hướng theo dòng giá trị.

## 28. Phối hợp thiết kế xuyên nhóm mà không tạo committee cho mọi thay đổi

Microservices vẫn cần nguyên tắc chung về security, API, observability, event schema và data ownership. Nhưng nếu mọi thay đổi phải đợi một “Architecture Board” phê duyệt, velocity có thể giảm.

Cách quản trị phù hợp:
- **Principles/guardrails:** nguyên tắc về auth, data residency, schema compatibility, SLO.
- **Automated checks:** lint/CI policy, contract validation, security tests, SBOM nếu cần.
- **RFC/ADR cho quyết định cross-context:** khi một thay đổi ảnh hưởng nhiều team hoặc rủi ro cao.
- **Delegated authority:** team được tự quyết trong bounded context của mình.
- **Architecture community of practice:** chia sẻ học hỏi, không thành cổng duyệt cho mọi PR.
- **Risk-based review:** hạ tầng chung, thay trust model, đổi public contract cần review sâu hơn.

Một ADR có thể ghi:
- Bối cảnh và mục tiêu user outcome.
- Các lựa chọn (ví dụ sync API, event-driven, shared platform).
- Tradeoff về cognitive load, failure mode, data ownership.
- Owner và affected teams.
- Cách đo thành công và rollback.
- Thời hạn review khi giả định thay đổi.

Cần phân biệt **quyết định về hệ thống chung** và **quyết định local**. Quyền tự chủ được tạo bằng ranh giới rõ, không phải bỏ tất cả tiêu chuẩn.

## 29. Monorepo/polyrepo là phương tiện, không phải mục tiêu tổ chức

Một nhóm theo value stream có thể sở hữu nhiều services trong monorepo hoặc polyrepo. Cách đặt repository không tự quyết định việc họ có thay đổi nhanh hơn hay không.

Monorepo có thể có:
- Ownership theo đường dẫn bằng CODEOWNERS.
- Build/test affected targets và cache.
- API contracts chung nhưng service deploy riêng.
- Review xuyên bounded context khi thay contract.

Polyrepo có thể có:
- Pipeline, quyền truy cập, version và release độc lập.
- Dependency bot, service catalog và contracts registry.
- RFC/issue liên kết khi một thay đổi trải nhiều repo.
- Platform templates để tránh pipeline drift.

Một test thực tế: “thay một business rule trong Checkout có cần mở năm PR hoặc xin năm team approve không?”. Nếu có, tìm nguyên nhân ở ownership, shared code, architecture hoặc quy trình; đổi repo chỉ là một công cụ, không chắc là giải pháp chính.

## 30. Trách nhiệm xây dựng và vận hành: “you build it, you run it” có điều kiện

Định hướng theo stream/capability có hiệu quả khi những người ra quyết định thiết kế chịu được feedback từ production. Tuy nhiên, không thể mặc định mọi nhóm có thể tự quản toàn bộ database cluster, mạng và chứng chỉ.

Một cách phân quyền:
- Stream team quản lý business behavior, API contract, test, deploy, observability, SLO của sản phẩm.
- Platform/SRE cung cấp infrastructure guardrails, self-service tooling, capacity patterns và shared incident support.
- Security định nghĩa chính sách/kiểm soát cần tuân thủ.
- Specialist team quản lý subsystem chuyên sâu có contract.
- Incident response phối hợp theo severity và dependency graph.

Cần có:
- Production access đúng nguyên tắc least privilege.
- Dashboard/log/traces do stream team sử dụng được.
- On-call rotation tương xứng quy mô và độ nghiêm trọng.
- Runbook để phát hiện/rollback failure trong phạm vi sở hữu.
- Quy trình escalation khi lỗi nằm ngoài team.
- Learning từ postmortem không đổ lỗi.

Một team vừa không có quyền xem telemetry vừa phải chịu SLO là mô hình ownership thiếu điều kiện cần. Trách nhiệm phải đi cùng **công cụ, quyền quyết định và năng lực thực hiện**.

## 31. Cognitive load: giới hạn thực tế của một nhóm

Cognitive load không đơn giản bằng số service. Team có thể sở hữu 10 services CRUD tương tự dễ hơn 3 services gồm máy học thời gian thực, settlement ledger và distributed scheduling.

Những yếu tố tăng tải:
- Số domain concepts và luật nghiệp vụ phải nhớ.
- Số deployment/runtime platforms và toolchains.
- Số internal/external dependencies, contracts và consumers.
- Tần suất incident/on-call và compliance reviews.
- Khối lượng dữ liệu/traffic và ràng buộc consistency.
- Số người/nhóm phải phối hợp cho mỗi thay đổi.
- Số feature flags, schema migrations và hỗ trợ legacy.
- Nhu cầu đổi công nghệ hoặc ưu tiên quá thường xuyên.

Các cách giảm:
1. Gộp việc cùng một mô hình domain, bỏ boundary nhân tạo.
2. Dùng platform self-service thay vì mỗi team làm lại hạ tầng.
3. Tách specialist subsystem khi kỹ năng hiếm và domain độc lập.
4. Cải thiện API contracts và documentation.
5. Giảm WIP và dự án song song.
6. Tự động hóa release/observability/security checks.
7. Đưa những dịch vụ không còn owner về một roadmap hợp lý hoặc loại bỏ khi có bằng chứng.

Không đặt ngưỡng “một team sở hữu tối đa X service” như chuẩn phổ quát. Nên đo tải qua khả năng hiểu, vận hành và thay đổi an toàn.

## 32. Metrics đánh giá hiệu quả tổ chức theo dòng giá trị

Một dashboard tổ chức không nên chỉ có commit count, số ticket đóng hoặc utilization từng người.

| Nhóm đo | Metrics | Câu hỏi |
| --- | --- | --- |
| **Flow** | Lead time, cycle time, wait time, WIP, queue age | Mất bao lâu để đưa ý tưởng thành giá trị? |
| **Delivery** | Deployment frequency, change failure rate, time to restore | Phát hành nhanh và an toàn không? |
| **Outcome** | Conversion, fulfillment lead time, retention, CSAT tùy sản phẩm | Người dùng/doanh nghiệp nhận gì? |
| **Reliability** | Journey SLI/SLO, error budget, incident recurrence | Dòng giá trị có vận hành đáng tin không? |
| **Autonomy** | % changes một team hoàn tất, % deploy độc lập | Team có thực sự tự chủ không? |
| **Coordination** | Cross-team PR/approval count, handoff wait time | Dependency nào đang làm chậm? |
| **Platform** | Self-service adoption, onboarding lead time, support ticket rate | Nền tảng giảm tải hay tạo cổng mới? |
| **Cognitive load** | Incident interruptions, domains/tools được sở hữu, survey team | Quy mô trách nhiệm có bền vững không? |

Các metrics phải đặt trong bối cảnh. Deployment frequency cao không chứng minh user outcome tốt. Số team dependencies thấp có thể là do service giấu coupling qua shared DB. Một nhóm có change failure rate thấp nhưng không dám deploy cũng không đạt mục tiêu.

Theo dõi **trước và sau can thiệp** theo nhóm phù hợp, không dùng metrics để xếp hạng cá nhân hoặc các team có sản phẩm/rủi ro không tương đồng.

## 33. Một bảng ánh xạ outcome và trách nhiệm

Ví dụ cho hành trình checkout:

| Outcome/SLI | Primary owner | Supporting capabilities | Dạng phối hợp |
| --- | --- | --- | --- |
| Hoàn tất checkout đúng hạn | Checkout Team | Orders, Inventory, Payments | Outcome coordination + contracts |
| Giá cuối cùng đúng | Offer & Pricing | Catalog, Checkout | Versioned pricing contract |
| Giữ tồn kho đúng | Inventory Team | Orders, Fulfillment | Reservation API + idempotency |
| Không thu tiền trùng | Payments Team | Checkout, Provider | Stable operation ID + reconciliation |
| Đơn có state chính xác | Order Lifecycle | Payment, Inventory | Business events + consistency checks |
| Pipeline deploy an toàn | Developer Platform | Mọi service teams | Self-service + standard guards |
| Security controls | Security/Platform + service owners | Identity, Gateway | Policies + automated verification |

Mỗi dòng nên có **một primary outcome owner** để tránh tình trạng không ai chịu trách nhiệm end-to-end. Điều này không phủ nhận những team khác cũng chịu trách nhiệm lỗi trong vùng họ sở hữu.

Một business outcome như “giảm thất bại thanh toán” có thể cần team Payment và Checkout cùng cải tiến. Ranh giới trách nhiệm rõ giúp phối hợp mục tiêu chứ không biến nó thành cuộc tranh cãi KPI.

## 34. Tổ chức sự kiện và API như giao diện giữa capabilities

Một service trong value stream có thể cần kết nối các context:

```text
Checkout         Orders           Inventory        Payments
   |                |                 |                |
   | PlaceOrder     |                 |                |
   |--------------->|                 |                |
   |                | ReserveStock    |                |
   |                |---------------->|                |
   |                |<----------------|                |
   |                | AuthorizePayment                 |
   |                |--------------------------------->|
   |                |<---------------------------------|
   |                | OrderConfirmed event            |
   |<---------------|                 |                |
```

Thiết kế nên xác định:
- Business operation ID và idempotency.
- Trạng thái khi downstream timeout/unknown.
- Contract version và schema evolution.
- Deadline/timeout/retry budget.
- Data ownership, cancellation/compensation.
- Trace/correlation IDs.
- Consumer-driven contract tests.
- SLO theo operation và owner xử lý lỗi.

Các hợp đồng ổn định giúp team stream-aligned có thể đưa chức năng mới ra production mà không cần gọi người viết implementation của capability ở mỗi release.

Nếu luồng yêu cầu transaction mạnh qua nhiều services và mọi bước phải cùng commit, cân nhắc lại boundary hoặc mô hình giao dịch. Việc tổ chức nhóm theo value stream không làm distributed transaction tự biến mất.

## 35. Tác động của event-driven architecture đến ownership

Event-driven systems có thể giảm coupling thời gian giữa các đội:
- Payments công bố `PaymentCaptured`.
- Orders cập nhật trạng thái theo event.
- Analytics tiêu thụ event theo nhịp riêng.

Nhưng cần phân biệt:
- Producer sở hữu ý nghĩa, schema và điều kiện phát event.
- Consumer sở hữu xử lý, idempotency và data projection riêng.
- Platform sở hữu broker infrastructure, policies và tooling.
- Outcome owner nhìn journey cuối cùng và thời gian eventual consistency.

Không để “event bus” trở thành cách lách contract review. Thay enum, unit tiền tệ hoặc semantic của event là thay đổi public API. Consumer cũ có thể còn đang chạy trong thời gian rolling release hoặc replay từ log lịch sử.

Nếu event name `OrderCompleted` có nghĩa khác ở các team, hãy dùng workshop event storming để thống nhất timeline và ngôn ngữ. **Các domain events phải có ngữ nghĩa rõ trong bounded context**, không chỉ là tên kỹ thuật dễ hiểu.

## 36. Event Storming và khám phá ranh giới cùng các bên liên quan

Một buổi event storming có thể bắt đầu từ câu hỏi “điều gì xảy ra trong hành trình đặt hàng?”. Những sự kiện được ghi theo trình tự:

```text
CartSubmitted
    -> PriceCalculated
    -> InventoryReserved
    -> PaymentAuthorized
    -> OrderConfirmed
    -> ShipmentRequested
    -> ShipmentDispatched
```

Sau đó nhóm khám phá:
1. Event nào là business fact, event nào chỉ là technical notification?
2. Command nào kích hoạt event?
3. Aggregate nào bảo vệ invariant?
4. Policy nào phản ứng với event?
5. Service/team nào có quyền phát hay xác nhận?
6. Điểm nào cần nhất quán tức thời, điểm nào có thể eventual?
7. Khi một bước thất bại, compensation hay reconciliation là gì?
8. Những event nào nhiều team gọi khác tên nhưng cùng ý nghĩa?
9. Những event nào giống tên nhưng thực sự khác nghĩa?
10. User journey đo thành công ở bước nào?

Kết quả có thể gợi ý bounded contexts và capabilities. Không nên dùng event storming để tự động tạo một microservice cho mỗi sticker/event, vì sẽ làm hệ thống phân mảnh và tăng overhead.

Workshop phải có product/domain experts, engineers, vận hành và những chủ thể cần quyết định. Chỉ để nhóm lập trình phỏng đoán nghiệp vụ sẽ dễ tạo sai boundary.

## 37. Quy trình thay đổi tổ chức theo từng giai đoạn

### Pha 1 — Hiểu dòng giá trị hiện tại

- Chọn 1–2 user journeys quan trọng.
- Xác định trigger, outcome và các bước thực.
- Thu thập lead time, wait time, incident, handoff và phụ thuộc.
- Map các capabilities, data owners và dependencies.
- Phỏng vấn nhóm product, vận hành, security và domain experts.
- Ghi nhận điểm đau có bằng chứng, không chỉ sơ đồ giả định.

### Pha 2 — Thiết kế boundary và team API

- Chọn phân đoạn value stream đủ nhỏ.
- Xác định bounded contexts và invariants.
- Đề xuất primary outcome owner cho mỗi phân đoạn.
- Xác định shared capability team nào phải cung cấp API/SLO.
- Thiết kế tương tác collaboration, X-as-a-Service, facilitating.
- Phân quyền code, dữ liệu, deploy và incident.
- Chọn metrics kiểm chứng giả thuyết.

### Pha 3 — Pilot với một dòng giá trị

- Thành lập nhóm liên chức năng có product authority.
- Cho team quyền sửa đủ end-to-end trong scope.
- Platform cung cấp golden path và hỗ trợ.
- Di chuyển backlog từ task-based handoffs sang outcome-oriented priorities.
- Áp dụng contract tests và deploy/rollback độc lập.
- Theo dõi flow efficiency, deployment frequency, reliability và customer outcome.

### Pha 4 — Mở rộng khi có bằng chứng

- Giữ boundary hiệu quả, sửa các boundary gây chờ.
- Tách/nhóm lại capabilities nếu cognitive load lớn.
- Chuyển platform from ticket-driven to self-service.
- Tự động hóa chính sách governance lặp lại.
- Định nghĩa runbook và escalation giữa nhiều team.
- Mở rộng pilot sang stream khác mà không giả định mọi stream giống nhau.

### Pha 5 — Điều chỉnh liên tục

- Review dependency map theo thay đổi thực.
- Đo work item flow và incident theo quý/chu kỳ phù hợp.
- Cập nhật team APIs, service catalog, SLO và architecture decision records.
- Đánh giá churn, burnout, training gaps.
- Tách hoặc hợp nhất teams khi thị trường/capability chuyển đổi.
- Không giữ sơ đồ tổ chức cũ chỉ vì nó từng phù hợp ở giai đoạn trước.

## 38. Ví dụ kế hoạch 30–60–90 ngày

Các mốc chỉ minh họa cho một tổ chức có năng lực thay đổi phù hợp, không phải deadline bắt buộc.

| Giai đoạn | Công việc chính | Bằng chứng hoàn thành |
| --- | --- | --- |
| Ngày 1–30 | Map một value stream, thống kê handoffs, xác định capability owners, chọn pilot | Current-state VSM, dependency map, SLI baseline |
| Ngày 31–60 | Tạo team API, gỡ một handoff lớn, thiết lập self-service hoặc contract tests | Pilot có thể deploy một change nhỏ end-to-end |
| Ngày 61–90 | Đo outcome, sửa coupling, làm runbook/on-call rõ, quyết định mở rộng | So sánh lead time, reliability và coordination cost |

Một trường hợp minh họa:
- Ban đầu thay đổi checkout mất 8 ngày vì chờ Database/Release teams.
- Pilot cho nhóm Checkout quyền thực hiện schema migration an toàn qua pipeline có guardrail và canary.
- Team Payment cung cấp stable API contract.
- Kết quả mong đợi là giảm chờ và vẫn giữ correctness; **không đặt trước một tỷ lệ cải thiện** trước khi đo thực tế.

Nếu rủi ro pháp lý hoặc quyền dữ liệu đòi approval, mục tiêu là làm approval rõ, sớm và tự động phần có thể — không xóa các kiểm soát bắt buộc.

## 39. Trường hợp đặc biệt: tổ chức nhỏ, tăng trưởng nhanh và đa sản phẩm

### Startup ít người

Một nhóm liên chức năng có thể sở hữu toàn bộ ứng dụng modular monolith và một vài integration services. Chưa cần tạo nhiều microservices/team nếu chưa có nhu cầu triển khai và ownership độc lập.

Định hướng theo giá trị vẫn hữu ích:
- Một backlog theo outcome.
- Domain modules và data boundaries rõ.
- Monitoring và customer feedback.
- Chuẩn bị interfaces cho khi cần tách.

### Công ty nhiều sản phẩm

Một capability như Identity, Billing hoặc Messaging có thể phục vụ nhiều product streams. Cần cân nhắc biến nó thành **internal product** với API/SLO/roadmap chứ không ép mỗi sản phẩm tự sao chép.

### Tổ chức có yêu cầu compliance cao

Payments và Risk có thể cần người kiểm soát độc lập, separation of duties, audit và change approval. Stream alignment phải làm việc bên trong constraints này. Cách cải thiện flow là tạo contract rõ và evidence tự động, không bỏ compliance.

### Nhiều múi giờ/địa lý

Thiết kế ownership và team APIs theo khả năng phối hợp bất đồng bộ, tài liệu đầy đủ, on-call escalation và ranh giới time-zone. Nếu công việc thường xuyên đòi họp realtime giữa ba múi giờ, nên xem lại coupling và quyết định phân chia teams.

## 40. Những anti-patterns thường gặp

**“Mỗi microservice tạo một team.”** Dễ tạo team quá nhỏ, on-call yếu và nhiều coupling; số service không phải đơn vị tổ chức mặc định.

**“Mỗi capability là một microservice.”** Capability map là công cụ nghiệp vụ; bounded context và transaction boundary cần phân tích riêng.

**“Stream team sở hữu toàn hành trình từ marketing đến logistics.”** Scope quá rộng, cognitive load không thể kiểm soát; chia thành phân đoạn outcome có ý nghĩa.

**“Platform team là DevOps ticket queue.”** Nếu mọi việc phải xin platform làm hộ, team sản phẩm vẫn phụ thuộc thủ công.

**“Enabling team duyệt mọi PR liên quan bảo mật.”** Dễ thành bottleneck vĩnh viễn; nên coaching và tự động hóa guardrails.

**“Giảm dependency bằng cách mọi team tự xây payment/identity.”** Nhân bản năng lực đặc thù có thể làm tăng rủi ro và chi phí; shared capability được sản phẩm hóa sẽ tốt hơn.

**“Team được gọi là product team nhưng không được tự quyết backlog.”** Thiếu ownership outcome, vẫn vận hành theo đơn đặt hàng task.

**“Team ownership rõ trong slide, nhưng incident không ai nhận.”** Thiếu runbook, on-call và service catalog; quyền phải kèm trách nhiệm.

**“Chỉ đổi sơ đồ tổ chức, không sửa data coupling.”** Shared schema và API breaking changes tiếp tục buộc lockstep deployment.

**“Hạn chế mọi cross-team interaction.”** Một số collaboration là cần thiết để khám phá domain, giải quyết incident và phát triển capability.

**“Tối ưu utilization mọi người.”** Queue và handoff lớn có thể làm end-to-end lead time tăng dù ai cũng bận.

**“Dùng DORA metrics để chấm điểm cá nhân.”** Khuyến khích hành vi sai và đánh mất bối cảnh rủi ro, sản phẩm, khách hàng.

**“Mọi yêu cầu kiến trúc đều phải qua hội đồng.”** Làm giảm autonomy; governance nên có cấp độ rủi ro và tự động hóa.

**“Tổ chức xong thì boundary bất biến.”** Thị trường, sản phẩm và kiến trúc thay đổi; team topology cần tiến hóa.

## 41. Checklist trước khi thành lập hoặc tái cấu trúc nhóm

### Giá trị và nghiệp vụ
- [ ] Có trigger và outcome rõ cho stream được chọn.
- [ ] Có bản đồ capability và domain experts tham gia.
- [ ] Biết customer/user journey nào có giá trị.
- [ ] Có metrics cho outcome thay vì chỉ output kỹ thuật.
- [ ] Scope đủ nhỏ để team hiểu và đủ lớn để tự đưa giá trị ra production.

### Kiến trúc và dữ liệu
- [ ] Bounded contexts và data owners rõ.
- [ ] API/events có contracts và compatibility policy.
- [ ] Mỗi service có owner và runtime/deployment boundary có ý nghĩa.
- [ ] Không dùng shared database làm đường tích hợp ngầm.
- [ ] Có idempotency/reconciliation khi cần workflow phân tán.
- [ ] Có trace, logging, SLO và runbook cho critical journeys.

### Team và quyền
- [ ] Team có quyền product prioritization trong phạm vi.
- [ ] Có đủ năng lực cross-functional hoặc đường hỗ trợ rõ.
- [ ] Cognitive load và on-call workload phù hợp.
- [ ] Không phụ thuộc ticket queue cho mỗi lần test/deploy bình thường.
- [ ] Team API và escalation path được công bố.
- [ ] Có owner của shared capabilities và journey outcomes.

### Đo lường và chuyển đổi
- [ ] Đã đo lead/wait time ban đầu.
- [ ] Có danh sách handoff cần loại bỏ và phụ thuộc giữ lại.
- [ ] Có pilot, hypothesis và thời điểm review.
- [ ] Có guardrails về security/compliance không bị phá.
- [ ] Theo dõi thay đổi reliability và customer impact.
- [ ] Có kế hoạch điều chỉnh khi giả thuyết không đúng.

## 42. Bài tập thực hành

### Bài 1 — Phân biệt khái niệm

Cho danh sách “Quản lý tồn kho”, “Từ khách chọn hàng tới giao hàng”, “Orders Service”, “Payment Bounded Context”, “Checkout Team”, “Tính và thu VAT”. Hãy phân loại thành capability, value stream, service, context, team hoặc nghiệp vụ cụ thể. Giải thích những mục có thể liên hệ nhiều chiều.

### Bài 2 — Value stream map

Một thay đổi hoàn trả hàng phải đi qua Support, Backend, Payments, QA và Release Team. Hãy lập bảng process time/wait time, tìm bottleneck và đề xuất cách giảm handoff mà không bỏ kiểm soát refund.

### Bài 3 — Tái cấu trúc một tổ chức

Tổ chức có Frontend, Java Backend, DBA và DevOps teams. Hãy đề xuất 2–3 stream-aligned teams và một platform capability tối thiểu. Xác định scope, quyền sở hữu, những năng lực nào phải chia sẻ và kênh hỗ trợ chuyên gia.

### Bài 4 — Bounded context và capability

Payment Authorization, Payment Settlement, Refund và Checkout là những khái niệm khác nhau. Phân tích capability/domain boundaries, data owner và vì sao không dùng cùng một `OrderEntity` JPA chung.

### Bài 5 — Team API

Viết Team API cho Inventory Team cung cấp `ReserveStock`, `ReleaseReservation` và `StockReserved` events. Ghi SLO, idempotency, contract versioning, escalation và cách consumer tích hợp mà không phải nhắn người trong team mỗi lần.

### Bài 6 — Stream SLO

Đặt một SLI cho “đặt hàng hoàn tất” và các SLI phụ cho Checkout, Inventory và Payments. Xác định owner nghiệp vụ, service owner và incident coordination khi một dependency làm sai kết quả cuối.

### Bài 7 — Team Topologies

Một nhóm thuật toán tính giá vận chuyển phức tạp phục vụ năm stream teams; một nhóm khác chuyên đào tạo contract tests trong ba tháng. Chọn loại team tương ứng và mô tả kiểu tương tác phù hợp sau khi giai đoạn học kết thúc.

### Bài 8 — Đánh giá cognitive load

Một team sở hữu 18 services, 4 DB engines, 7 consumer groups và hai lĩnh vực compliance khác nhau. Đề xuất cách đo tải và hai phương án giảm tải: platform self-service, tách bounded context, gộp services hoặc specialist subsystem.

### Bài 9 — Thay đổi API không lockstep

Payments thêm event `PaymentPendingReview`. Checkout và Order Lifecycle vẫn chạy bản cũ. Lập thứ tự expand/migrate/contract, test compatibility và owner của từng bước.

### Bài 10 — Đo hiệu quả pilot

Sau 60 ngày tổ chức lại, deployment frequency tăng nhưng checkout SLO giảm, on-call interruptions tăng. Hãy giải thích vì sao không thể tuyên bố pilot thành công và xây kế hoạch điều chỉnh có trách nhiệm.

## 43. Ghi nhớ

- **Value stream là hành trình tạo kết quả; business capability là khả năng doanh nghiệp huy động để thực hiện hành trình.**
- **Team boundary, bounded context và microservice boundary không phải quan hệ một-một bắt buộc.** Chọn ranh giới theo domain cohesion, ownership, cognitive load và độc lập thay đổi.
- **Stream-aligned teams nên có quyền đưa một outcome ra production**, không chỉ nhận từng bước việc theo silo.
- **Platform teams cần cung cấp self-service capabilities**, không trở thành hàng đợi ticket mới.
- **Enabling teams hỗ trợ học và chuyển giao năng lực**; complicated-subsystem teams tập trung kỹ năng đặc biệt khi phù hợp.
- **Team interaction cần có chủ đích**: collaboration có thời hạn, X-as-a-Service và facilitating.
- **Conway's Law nhắc rằng cấu trúc giao tiếp ảnh hưởng cấu trúc phần mềm**; muốn kiến trúc tốt cần thay cả tổ chức và cơ chế phối hợp.
- **Capability ownership phải gồm data, contracts, pipeline và production reliability**, không chỉ source code.
- **Đo lead time, queue, autonomy, SLO và customer outcome**, không dùng số service hay số commit làm đại diện duy nhất cho hiệu quả.
- **Thử nghiệm tổ chức theo từng dòng giá trị và xem lại dựa trên bằng chứng**, không giữ cấu trúc cố định khi công ty/phần mềm thay đổi.

Một tổ chức microservices trưởng thành không phải nơi có nhiều service nhất hay nhiều nhóm nhất. Nó là nơi **các nhóm sở hữu kết quả có ý nghĩa, thay đổi trong boundary rõ ràng, tiêu thụ các năng lực khác bằng hợp đồng đáng tin cậy và cùng chịu trách nhiệm về trải nghiệm người dùng xuyên hệ thống**.

### Tài liệu tham khảo và học thêm

- Team Topologies — Introduction: https://teamtopologies.com/
- Team Topologies — Key Concepts: https://teamtopologies.com/key-concepts
- Martin Fowler — Bounded Context: https://martinfowler.com/bliki/BoundedContext.html
- Martin Fowler — Microservices: https://martinfowler.com/articles/microservices.html
- Martin Fowler — Conway's Law: https://martinfowler.com/bliki/ConwaysLaw.html
- Domain-Driven Design Reference — Eric Evans: https://www.domainlanguage.com/ddd/reference/
- Google SRE Book — Service Level Objectives: https://sre.google/sre-book/service-level-objectives/
- Google SRE Workbook — Implementing SLOs: https://sre.google/workbook/implementing-slos/
- DORA — Research and Capabilities: https://dora.dev/
- Accelerate — Nicole Forsgren, Jez Humble, Gene Kim (sách)
- Team Topologies — Matthew Skelton, Manuel Pais (sách)

Những sơ đồ, nhóm và chỉ số trong bài là ví dụ minh họa. Khi ứng dụng cần dựa trên đặc điểm domain, quy mô tổ chức, yêu cầu security/compliance, dòng công việc và những bằng chứng từ production thay vì sao chép nguyên một mẫu tổ chức.

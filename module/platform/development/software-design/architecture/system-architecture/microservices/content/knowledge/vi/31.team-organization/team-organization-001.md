# Nhóm sở hữu dịch vụ xuyên suốt phát triển và vận hành

Kiến trúc microservices chỉ đem lại khả năng thay đổi và triển khai độc lập khi có **quyền sở hữu rõ ràng đối với từng dịch vụ trong suốt vòng đời của nó**. Việc chia một hệ thống thành nhiều repository, API và container không tự động tạo ra tính độc lập nếu nhóm A viết code, nhóm B chịu trách nhiệm chạy production, nhóm C phải điều tra mọi lỗi và nhóm D mới có quyền thay đổi database. Khi đó một cải tiến nhỏ có thể cần nhiều hàng đợi bàn giao; sự cố xảy ra thì không ai nhìn thấy toàn bộ nguyên nhân và tác động đối với người dùng.

Mô hình **nhóm sở hữu dịch vụ xuyên suốt phát triển và vận hành** (end-to-end service ownership) giao cho một nhóm đủ năng lực và quyền hạn chịu trách nhiệm về kết quả của một năng lực nghiệp vụ: thiết kế, triển khai, kiểm thử, phát hành, quan sát, khắc phục sự cố, bảo mật, dữ liệu, chi phí và lộ trình cải tiến. Mục tiêu không phải bắt một nhóm tự xây mọi hạ tầng hay không được xin hỗ trợ. Mục tiêu là có **một đầu mối chịu trách nhiệm kết quả**, được hỗ trợ bởi nền tảng dùng chung, cơ chế cộng tác và ranh giới hợp đồng rõ.

Bài này đặt trong bối cảnh hệ thống bán hàng gồm Catalog, Checkout, Order, Payment, Inventory và Notification. Các mẫu tổ chức, vai trò, SLO, cách phân công và thời gian cảnh báo đều là ví dụ để hiểu nguyên tắc; cách triển khai thật cần phù hợp quy mô tổ chức, mức độ rủi ro sản phẩm và các chính sách vận hành.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Giải thích vì sao **ownership theo luồng giá trị và ranh giới dịch vụ** hỗ trợ phát hành độc lập hơn cơ chế bàn giao giữa nhiều nhóm chức năng.
- Phân biệt **service owner**, **product/domain owner**, **platform team**, **SRE/reliability specialists**, **security**, **database specialists** và **incident commander**.
- Xác định quyền quyết định, trách nhiệm trực vận hành, phạm vi dữ liệu, hợp đồng API/event và các điểm cần phối hợp.
- Thiết kế service catalog, ownership metadata, on-call rotation, SLO, runbook, dashboard và escalation path.
- Thiết kế quy trình xây dựng–chạy–học hỏi từ production mà không tạo văn hóa đổ lỗi.
- Áp dụng cơ chế phát hành độc lập, kiểm thử hợp đồng, kiểm soát breaking changes, incident response và postmortem.
- Phân tích những anti-pattern: owner “trên giấy”, ownership chia mảnh, platform ticket queue, shared database không có owner và on-call không bền vững.
- Xây dựng lộ trình chuyển đổi tổ chức từ nhóm bàn giao theo chức năng sang nhóm chịu trách nhiệm vòng đời dịch vụ.

## 2. “Sở hữu dịch vụ” nghĩa là gì?

Nhóm sở hữu dịch vụ là nhóm có **trách nhiệm chính và năng lực hành động** đối với các thuộc tính mà người dùng hoặc những dịch vụ khác trông đợi ở service đó.

~~~text
Người dùng / đối tác / dịch vụ tiêu thụ
                   |
                   v
          Hợp đồng và SLO
                   |
                   v
         Service Owner Team
          /       |        \
   Thiết kế    Delivery     Operate
   & dữ liệu    & deploy     & improve
          \       |        /
                   v
           Dịch vụ production
                   |
                   v
    Logs, traces, metrics, user feedback
                   |
                   v
             Cải tiến tiếp
~~~

Đó là một **vòng phản hồi liên tục**. Người thiết kế code cần hiểu lỗi do chính quyết định thiết kế gây ra; người vận hành cần có quyền sửa vấn đề chứ không chỉ đóng vai người chuyển ticket.

Nhưng cần phân biệt ba khái niệm:

- **Accountability:** ai chịu trách nhiệm cuối cùng rằng dịch vụ đạt chất lượng đã thống nhất, kể cả khi các phần việc được hỗ trợ bởi nhóm khác?
- **Responsibility:** ai trực tiếp làm một công việc cụ thể, ví dụ thay cert, nâng database engine, xử lý sự cố hay review API?
- **Authority:** ai có quyền thay đổi source, cấu hình, phát hành, rollback, cấp quyền hoặc ra quyết định trong incident?

Nếu giao accountability nhưng không cấp quyền và công cụ tương ứng, nhóm owner sẽ trở thành người “chịu lỗi” thay vì người có thể cải thiện dịch vụ.

### 2.1. Mô hình trách nhiệm toàn vòng đời

| Giai đoạn | Nhóm sở hữu dịch vụ cần bảo đảm |
|---|---|
| Khám phá nhu cầu | Hiểu hành trình người dùng, năng lực nghiệp vụ và kỳ vọng chất lượng |
| Thiết kế | Ranh giới service, API/event, dữ liệu, mô hình lỗi, bảo mật và chi phí |
| Xây dựng | Code, test, migration, documentation và code review |
| Phát hành | Pipeline, artifact, cấu hình, canary/rollback và điều kiện go/no-go |
| Vận hành | SLI/SLO, alert, on-call, capacity, backup/recovery và sự cố |
| Bảo trì | Vá lỗ hổng, cập nhật dependency, loại bỏ nợ kỹ thuật |
| Tiến hóa | Đổi contract có tương thích, tách/gộp năng lực, đáp ứng sản phẩm |
| Kết thúc vòng đời | Deprecation, migration consumer, lưu giữ/xóa dữ liệu và tắt service an toàn |

Một số hoạt động do platform, SRE hoặc security hỗ trợ thực hiện, nhưng owner phải biết trạng thái, rủi ro và đường xử lý liên quan đến service của mình.

## 3. Từ “you build it, you run it” đến trách nhiệm bền vững

Khẩu hiệu “you build it, you run it” nhấn mạnh rằng người làm ra dịch vụ phải đối diện với hệ quả vận hành của nó. Cách hiểu quá máy móc sẽ dẫn đến yêu cầu mọi developer trực 24/7, tự vận hành database cluster, certificate authority, Kubernetes, CI và hệ thống quan sát, dù quy mô nhóm không đủ.

Cách hiểu thực dụng hơn:

1. Nhóm sở hữu dịch vụ **không bỏ trách nhiệm** sau khi merge code hoặc bàn giao release.
2. Nhóm có khả năng **phát hiện, điều tra, rollback và sửa** lỗi thuộc service của mình.
3. Hạ tầng phổ biến được platform cung cấp dưới dạng năng lực tự phục vụ và hợp đồng hỗ trợ.
4. Chuyên gia SRE, database hoặc security hỗ trợ vấn đề khó; không biến họ thành nơi nhận mọi ticket mà owner mất kết nối với lỗi.
5. Chế độ trực, quy tắc escalation và mức hỗ trợ phải **bền vững với số người và quy mô sản phẩm**.

Một mô hình phối hợp phù hợp có thể là developer-on-call trong một đội đủ lớn, hoặc đội NOC/SRE giám sát tuyến đầu rồi chuyển có ngữ cảnh tới owner, hoặc luân phiên theo khu vực nếu có nhiều múi giờ. Điểm quan trọng là **không có khoảng trống ownership khi production gặp vấn đề**.

## 4. Tổ chức theo năng lực nghiệp vụ thay vì tầng kỹ thuật

So sánh hai kiểu phân chia:

~~~text
Theo chức năng:
  Frontend Team -> Backend Team -> Database Team -> Operations
  Mỗi feature cần nhiều bàn giao và lịch triển khai chung.

Theo năng lực:
  Catalog Team     -> Catalog Service + dữ liệu + vận hành
  Checkout Team    -> Checkout workflow + vận hành
  Payment Team     -> Payment Service + ledger + vận hành
  Platform Team    -> CI/CD, runtime, observability, registry
  Security/SRE     -> Guardrails, chuyên môn và hỗ trợ theo mô hình rõ
~~~

Nhóm theo năng lực thường có kiến thức về tác động người dùng, từ đó đưa ra trade-off tốt giữa chức năng, latency, correctness và availability.

### Vì sao ranh giới tổ chức ảnh hưởng ranh giới kiến trúc?

Nếu mỗi thay đổi business rule đều bắt buộc chỉnh shared database, gọi nhóm DB trung tâm và phát hành đồng thời 5 ứng dụng, ranh giới code dù nhỏ vẫn phụ thuộc mạnh. Ngược lại, khi nhóm sở hữu một bounded context và dữ liệu của nó, đa số thay đổi nội bộ chỉ tác động một đơn vị phát hành.

Đây là điểm liên quan đến Conway's Law: cấu trúc giao tiếp của tổ chức thường phản chiếu trong hệ thống được thiết kế. Không cần “mỗi nhóm một microservice” hoặc “mỗi microservice một nhóm”; điều hữu ích là giảm số đường giao tiếp bắt buộc cho thay đổi thông thường.

### Quy tắc không nên hiểu cứng

- Một đội có thể sở hữu **nhiều service gắn với cùng năng lực nghiệp vụ**.
- Một service có thể cần chuyên môn từ nhiều nhóm, nhưng nên có **owner chính duy nhất được công bố**, kèm cơ chế phối hợp.
- Một sản phẩm lớn có thể cần tách năng lực thành nhiều đội với hợp đồng rõ.
- Một nhóm quá nhỏ không thể trực vận hành một cách bền vững; nên giảm số service, dùng platform/managed services hoặc hợp nhất ownership ở cấp đủ năng lực.

Đừng tách 20 service chỉ để có 20 ô trong sơ đồ tổ chức. Số lượng ranh giới phân phối tạo thêm chi phí vận hành và giao tiếp.

## 5. Service ownership khác code ownership

**Code ownership** thường trả lời ai được review hoặc merge một repository. **Service ownership** rộng hơn, bao gồm hệ thống đang chạy và mọi phụ thuộc cần thiết cho giá trị cung cấp.

Ví dụ Order Team có quyền merge repository `order-service`, nhưng production sử dụng database, topic, schema registry, secret, dashboard và runbook:

~~~text
Service: Order
Source repo ------------------ Order Team
Deployment ------------------- Order Team + Platform runtime
Order DB/schema -------------- Order Team (logical data owner)
Managed DB cluster ----------- Database Platform Team
OrderCreated event contract -- Order Team (producer owner)
Consumer contract tests ------ Order + consumer teams
SLO/error budget ------------- Order Team + Product agreement
On-call route ---------------- Order Team primary, backup escalation
Secrets/config --------------- Order Team defines use; platform secures delivery
~~~

Owner không cần quyền root của database cluster để chịu trách nhiệm về schema, truy vấn, migration và tác động của Order. Nhưng owner cần quy trình và công cụ để yêu cầu thay đổi hạ tầng đúng thời hạn, đồng thời có người chịu trách nhiệm phần managed platform.

### Những đối tượng ownership phải có tên

| Đối tượng | Câu hỏi phải trả lời |
|---|---|
| Service | Nhóm nào chịu trách nhiệm chất lượng và vòng đời? |
| Repository | Ai review/merge và bảo vệ source? |
| Database schema | Ai quyết định thay đổi cấu trúc và dữ liệu? |
| Topic/queue | Ai tạo, bảo vệ retention/ACL và xử lý sự cố message? |
| API/event contract | Ai công bố compatibility và migration policy? |
| CI/CD pipeline | Ai sở hữu logic release/rollback, ai cung cấp pipeline platform? |
| Config/feature flags | Ai quyết định giá trị và ai phê duyệt thao tác nguy hiểm? |
| Secrets/identity | Ai có quyền đọc/rotate, ai chịu trách nhiệm không để lộ? |
| Observability | Ai giữ SLI, dashboard và alert có hành động? |
| Incident | Ai nhận page, ai điều phối, ai có quyền rollback? |
| Data lifecycle | Ai quyết định retention, backup, restore, deletion và compliance? |
| Cost/capacity | Ai thấy bill và quyết định trade-off theo SLO? |

Nếu một thành phần không có owner, nên đưa vào backlog để gán rõ hoặc giảm phụ thuộc, thay vì mặc định “platform sẽ làm”.

## 6. Single accountable owner nhưng không có nghĩa mọi công việc làm một mình

Một mẫu tổ chức thực tế:

| Công việc | Service owner | Platform/SRE | Security | Product |
|---|---|---|---|---|
| Business API behavior | Quyết định thiết kế và tương thích | Cung cấp gateway/standards | Review nguy cơ khi cần | Quyết định kỳ vọng nghiệp vụ |
| Deployment production | Chuẩn bị, xác minh và chủ động rollback | Cung cấp pipeline/runtime/guardrails | Policy artifact | Tham gia quyết định tác động khách hàng |
| Database schema | Sở hữu dữ liệu, migration và rollback | Vận hành cluster nếu managed | Quy tắc bảo vệ dữ liệu | Yêu cầu retention/semantics |
| SLI/SLO | Thiết kế metric, vận hành alert | Cung cấp observability và tư vấn | Yêu cầu theo rủi ro | Đồng thuận mức trải nghiệm |
| Incident service | Khắc phục service và tham gia on-call | Hỗ trợ platform, incident response | Tham gia nếu là security incident | Truyền thông và ưu tiên người dùng |
| Capacity/cost | Đo workload và điều chỉnh tiêu thụ | Cung cấp công cụ, quota và hạ tầng | Chính sách tài nguyên an toàn | Ưu tiên giá trị/cost |
| Security patch | Nâng thư viện/image và test | Vá platform/runtime | Đặt guardrail, tư vấn và giám sát | Chấp nhận trade-off release hợp lệ |

Bảng trên biểu diễn cách cộng tác, **không phải quy trình phê duyệt tuần tự cho mọi thay đổi**. Nếu mỗi deploy phải chờ Platform, Security, Database và SRE duyệt thủ công dù đã đáp ứng policy, tính độc lập phát hành sẽ biến mất.

## 7. RACI và giới hạn của RACI

RACI là một công cụ giúp làm rõ người thực hiện (Responsible), người chịu trách nhiệm cuối cùng (Accountable), người được tham vấn (Consulted), và người cần được thông báo (Informed).

Một ma trận minh họa:

| Hoạt động | Order Team | Platform Team | Security | Product Owner |
|---|---|---|---|---|
| Thay business logic Order | A/R | I | C khi có rủi ro | C |
| Thay schema Order DB | A/R | C cho platform migration | C khi dữ liệu nhạy cảm | I |
| Sửa cluster database bị hỏng | C, xác minh nghiệp vụ | A/R | I | I |
| Chọn Order SLO | R | C | C nếu liên quan rủi ro | A |
| Điều tra lỗi Order endpoint | A/R | C nếu hạ tầng liên quan | I | I |
| Rotate khóa dùng chung của cluster | C, cập nhật client | R/A theo ownership hạ tầng | C | I |
| Rollback một release Order | A/R trong policy | Hỗ trợ công cụ | C khi liên quan bảo mật | I hoặc C tùy tác động |

RACI chỉ hiệu quả khi phản ánh **quyền quyết định thật**. Nếu ô A ghi Order Team nhưng team không có quyền xem log production, chạy rollback hoặc bật chế độ bảo vệ, cần điều chỉnh mô hình quyền, không chỉ cập nhật bảng.

**Không lạm dụng RACI** để ép một incident phải hỏi từng người trong ma trận trước khi giảm thiệt hại. Runbook phải định nghĩa emergency authority và chính sách audit thích hợp.

## 8. Định nghĩa phạm vi và service boundary

Ownership dễ quản lý hơn khi dịch vụ có trách nhiệm nghiệp vụ rõ ràng:

~~~text
Order:
  Owns order lifecycle và order database.
  Public contract: CreateOrder/GetOrder/OrderStatusChanged.
  Does not own direct payment card processing.

Payment:
  Owns payment attempts, provider integration, idempotency ledger.
  Public contract: Authorize/Capture/GetPaymentStatus.
  Does not own Order's internal tables.

Inventory:
  Owns reservation/availability rules.
  Publishes reservation events.
  Does not mutate Order DB directly.
~~~

Nếu Payment Team muốn sửa Order table trực tiếp để “đỡ gọi API”, quyền sở hữu dữ liệu bị phá. Để tăng tốc độ, có thể dùng API, event hoặc read model sao chép phù hợp thay vì shared write database.

### Domain ownership không phải sở hữu mọi bước của hành trình

Checkout user journey đi qua nhiều nhóm. Có thể có **journey owner** chịu trách nhiệm SLO đầu-cuối và điều phối chất lượng; từng service owner vẫn chịu trách nhiệm hợp đồng/thực thi của mình. Không nên biến journey owner thành người không có quyền nhưng bị quy trách nhiệm toàn bộ các dependencies.

Ví dụ Checkout Team điều phối luồng, Payment Team chịu tính đúng của charge, Inventory Team chịu giới hạn tồn kho. SLO checkout được thống nhất trên phép đo người dùng; các nhóm cùng sửa critical path khi bị ảnh hưởng.

## 9. Service catalog là hồ sơ quyền sở hữu sống

Dịch vụ cần được tìm thấy: ai sở hữu, ai trực, chạy ở đâu, giữ dữ liệu gì, có những API/event nào, dashboard và runbook nào.

Ví dụ một khai báo service catalog khái niệm:

~~~yaml
apiVersion: internal.example/v1
kind: Service
metadata:
  name: order-service
  description: "Order lifecycle và quản lý trạng thái đơn"
spec:
  domain: commerce-order
  lifecycle: production
  ownerTeam: order-team
  productContact: commerce-product
  repository: "https://git.example.test/commerce/order-service"
  onCallRoute: "order-primary"
  backupOnCallRoute: "commerce-secondary"
  docs: "https://docs.example.test/services/order"
  runbook: "https://docs.example.test/runbooks/order"
  dashboards:
    - "https://metrics.example.test/order-overview"
  slos:
    - name: create-order-success
      objective: 0.999
      window: rolling-30d
  exposes:
    apis:
      - "POST /orders"
      - "GET /orders/{id}"
    events:
      - "OrderCreated.v1"
  data:
    logicalOwner: "order-team"
    database: "order-db"
    classification: "customer-data"
  dependencies:
    - "inventory-service"
    - "payment-service"
~~~

Đây là **ví dụ dữ liệu mô tả**, không phải schema tiêu chuẩn của một công cụ service catalog nhất định. Các URL và tài khoản chỉ là placeholder. Không đưa password/token, dữ liệu khách hàng hoặc bí mật vào catalog.

### Những trường thực sự hữu ích khi xảy ra sự cố

- Owner chính, backup owner và kênh escalation.
- Link dashboard, runbook, recent releases và deploy history.
- Mức độ quan trọng và các SLO được hỗ trợ.
- Upstream/downstream dependencies và contact của từng nhóm.
- Data owner, retention, backup/restore policy.
- Đường truy cập alert, log, trace theo quyền được cấp.
- Trạng thái vòng đời: active, deprecated, migrating, retired.

Catalog phải được cập nhật khi nhóm đổi tên, service đổi owner hoặc bị tắt. Một trang wiki tồn tại nhưng link on-call sai là nguy cơ vận hành, không phải tài sản hỗ trợ.

## 10. Ownership phải có cả primary và backup

“Owner = một cá nhân” là một điểm lỗi đơn lẻ. Một người có thể nghỉ phép, chuyển dự án hoặc rời tổ chức. Owner nên là **một nhóm có vai trò, lịch trực, người kế nhiệm và cơ chế chia sẻ tri thức**.

Ví dụ:

~~~text
Service owner:       order-team
Technical steward:   thành viên luân phiên được phân công
Primary on-call:     order-oncall-week-1
Secondary on-call:   commerce-backup
Incident escalation: commerce-incident-commander
Product contact:     commerce-product
~~~

Các vai trò cá nhân có thể thay đổi theo lịch; service vẫn giữ owner-team ổn định và được công bố.

### Những điều cần tránh

- Chỉ một engineer hiểu database migration và recovery.
- Chỉ một người có quyền production deploy hoặc khóa SSH.
- On-call đi tới điện thoại cá nhân không có backup.
- Service rơi vào “unowned” khi trưởng nhóm chuyển chức vụ.
- Team đổi ownership nhưng không bàn giao SLO, alert, secret, consumer contracts và data retention.
- Service sống lâu hơn nhóm tạo ra nó mà không có kế hoạch chuyển giao.

Một đội bền vững cần **tài liệu, cross-training và khả năng hỗ trợ lẫn nhau**, không xây hoạt động production quanh kiến thức bí mật của một cá nhân.

## 11. Những quyền hạn tối thiểu nhóm owner cần có

Một team không thể chịu trách nhiệm SLO nếu mọi thao tác liên quan production phải gửi ticket qua nhiều bên.

Những năng lực cần được cung cấp theo quyền tối thiểu:

1. Xem trạng thái deploy, version, image digest và config revision.
2. Xem service dashboard, alert, logs và traces trong phạm vi được phép.
3. Thực hiện rollback/canary của chính service theo chính sách.
4. Cấu hình scale, timeout, feature flag và rate limiting trong guardrails.
5. Thao tác backup/restore thử nghiệm và chạy migration qua pipeline được kiểm soát.
6. Truy cập staging/test data thích hợp để tái hiện lỗi.
7. Tạo/kiểm tra integration contract với dependencies.
8. Xem chi phí, quota, saturation và công suất của service.
9. Cấp quyền tạm thời/elevated access qua cơ chế được audit khi incident đòi hỏi.
10. Có đường escalation nhanh cho vấn đề platform, bảo mật hoặc nhà cung cấp.

Cần giữ phân tách trách nhiệm ở nơi cần thiết: một người không nên tự phê duyệt mọi thay đổi dữ liệu nhạy cảm, tắt audit hoặc cấp quyền admin vô hạn. Mục tiêu là **self-service an toàn**, không phải “tất cả đều có production root”.

## 12. Product và kỹ thuật cùng chịu trách nhiệm về chất lượng

Chất lượng dịch vụ không chỉ là “không có HTTP 500”. Người dùng quan tâm hành trình hoàn tất, tốc độ, tính đúng và tính nhất quán.

Ví dụ người mua bấm thanh toán một lần nhưng thấy lỗi dù tiền đã bị trừ. Backend có thể đạt 99,99% API availability nhưng trải nghiệm checkout và correctness không đạt.

Một cuộc trao đổi về SLO nên có:

- Product xác định hậu quả người dùng và mức trải nghiệm chấp nhận.
- Service owner đề xuất SLI có thể đo, mô hình lỗi và kế hoạch đạt SLO.
- Reliability/SRE hỗ trợ phân tích error budget, alert và capacity.
- Security/compliance tham gia khi dữ liệu/tiền/an toàn có yêu cầu riêng.
- Các nhóm dependency xác định những hợp đồng ảnh hưởng tới SLO đầu-cuối.

Không áp một tỷ lệ 99,99% cho tất cả endpoint. Một notification email trễ ít phút có thể chấp nhận được; thanh toán bị charge trùng là lỗi correctness phải xử lý riêng, không thể “nằm trong 0,1% error budget” như một lỗi nhẹ.

## 13. SLI/SLO là cam kết vận hành của owner

Một định nghĩa SLO có hành động có thể như sau:

~~~text
User journey: Tạo đơn
Event unit: logical create-order attempt
Eligible: yêu cầu hợp lệ, không tính user cancel trước submission
Good: order hợp lệ được xác nhận và hiển thị trong <= 2 giây
Objective: >= 99,9% good events trong rolling 30 days
Source: order outcome ledger + gateway observation
Owner: order-team
Escalation: order-oncall
~~~

Tính toán khái niệm:

~~~text
SLI = good events / eligible events
Allowed bad ratio = 1 - SLO target
Error budget = eligible events * allowed bad ratio
~~~

Nếu trong 30 ngày có 2.000.000 eligible attempts và SLO 99,9%, error budget là 2.000 bad attempts. Nhóm owner phải biết **tại sao một attempt bị bad**, không chỉ biết số 99,94%.

### Trách nhiệm vận hành quanh SLO

- Bảo trì định nghĩa numerator/denominator và logic dedup.
- Kiểm tra telemetry không mất dữ liệu hoặc đổi nghĩa khi deploy.
- Đặt alert theo tác động người dùng, burn rate và số mẫu.
- Điều tra khi budget tiêu nhanh; giảm lỗi trước khi tối ưu dashboard.
- Ghi lại khi exception/feature degradation xảy ra.
- Thỏa thuận chính sách release khi budget gần cạn.
- Review SLO với product khi hành trình hoặc mức sử dụng thay đổi.

Platform có thể cung cấp Prometheus, tracing và alerting; owner chịu trách nhiệm metric của service có phản ánh đúng trải nghiệm và được dùng để ra quyết định hay không.

## 14. On-call là trách nhiệm được thiết kế, không phải hình phạt

Một hệ thống production cần biết ai phản ứng với sự cố ngoài giờ và ai có quyền hỗ trợ. On-call chỉ bền vững khi có **tín hiệu hành động được, đủ người trực và đường xử lý rõ**.

Một mô hình:

~~~text
Alert: Checkout completion ratio giảm mạnh
                   |
                   v
        Primary on-call: Checkout
                   |
             Acknowledge
                   |
            Triage impact
             /          \
       Bug service     Platform failure
            |                |
       Rollback/flag      Escalate SRE
             \          /
              Mitigate
                   |
          Incident review và fixes
~~~

### On-call cần được hỗ trợ bởi hệ thống

- Alert phải chỉ ra service, mức nghiêm trọng, SLI bị ảnh hưởng và link runbook.
- Có secondary/escalation khi primary không phản hồi.
- Có công cụ để xem production trạng thái đúng quyền.
- Có cách giảm thiệt hại: rollback, rate limit, feature flag, queue pause hoặc failover phù hợp.
- Có lịch trực, quy tắc bàn giao và kiểm soát fatigue.
- Có training/game day trước khi một thành viên trực độc lập.
- Có thời gian trong roadmap để xóa toil và sửa những nguyên nhân page lặp lại.

Đừng đánh giá hiệu quả on-call bằng số đêm không ngủ hoặc số lần mọi người “anh hùng” cứu production. Một hệ thống tốt hướng tới **ít sự cố cần đánh thức người hơn**, phát hiện sớm và khả năng khôi phục có kiểm soát.

### Mức độ cảnh báo theo tác động

| Tình huống | Hành động thường hợp lý |
|---|---|
| Checkout không hoạt động với nhiều người dùng | Page khẩn và incident coordination |
| Payment correctness nghiêm trọng | Page ngay, bảo vệ dữ liệu và reconciliation |
| Lượng 5xx tăng nhẹ nhưng dưới ngưỡng SLO | Ticket/điều tra theo ngữ cảnh |
| Một pod restart nhưng user journey ổn | Kiểm tra nguyên nhân, không nhất thiết page |
| Sắp đầy storage hoặc cert gần hết hạn | Alert chủ động đủ sớm; chỉ page nếu nguy cơ sắp hiện hữu |
| Dashboard mất dữ liệu và không thể đo SLO | Alert về telemetry failure; đánh giá tác động |

Ngưỡng thật phải dựa trên SLO, tốc độ tiêu error budget và mức độ rủi ro, không sao chép cứng mọi service.

## 15. Runbook: từ alert đến thao tác phục hồi

Runbook phục vụ người đang trực, không chỉ để thỏa điều kiện tài liệu. Nó cần có thông tin **thực thi được, có giới hạn và có đường rollback**.

Mẫu runbook ngắn:

~~~markdown
# Order Service — Checkout failures

## Nhận diện
- Alert:
- User journey/SLI:
- Mức tác động đã biết:
- Link dashboard:
- Link traces/logs:

## Triage
1. Xác định thời gian bắt đầu và các deploy/flag gần nhất.
2. Phân rã lỗi theo route, tenant, region, dependency.
3. Kiểm tra DB, Inventory, Payment, queue và timeout.
4. Xác nhận lỗi đo telemetry hay lỗi người dùng thật.

## Mitigation theo policy
- Rollback image/config khi tương thích với schema:
- Tắt feature rủi ro bằng flag:
- Giảm concurrency hoặc tạm chặn write nguy hiểm:
- Escalate platform/provider:

## Kiểm tra phục hồi
- Good-event ratio và latency:
- Pending/duplicate payment attempts:
- Queue lag và DLQ:
- Synthetic create-order:

## Hậu sự cố
- Timeline, owner action items và regression tests:
~~~

Các bước có thể điều chỉnh theo hạ tầng; đừng đưa lệnh xóa bảng hoặc thao tác destructive chưa có safety guard vào runbook. Runbook cần được diễn tập định kỳ để không trở thành đường link chết.

## 16. Incident response: owner và incident commander khác vai trò

Khi sự cố lớn ảnh hưởng nhiều service, có thể bổ nhiệm **incident commander** để điều phối quyết định, người liên lạc, ưu tiên và timeline. Incident commander không nhất thiết là người có kiến thức code sâu nhất.

Các vai trò:

| Vai trò | Trọng tâm |
|---|---|
| Incident commander | Điều phối, xác định ưu tiên, bảo đảm thông tin rõ |
| Service owner responder | Điều tra/giảm thiệt hại ở service, đề xuất rollback/fix |
| Platform/SRE responder | Kiểm tra cluster, network, database platform, telemetry |
| Security responder | Nếu có nghi xâm nhập, bảo vệ chứng cứ, khóa credential |
| Communications lead | Thông báo phù hợp cho khách hàng/stakeholders |
| Scribe/timeline owner | Lưu mốc, quyết định, rủi ro và hành động |
| Product representative | Ưu tiên tác động người dùng, degraded mode, tính năng |

Với sự cố nhỏ, một người có thể làm nhiều vai trò; với sự cố lớn nên tách để tránh người đang debug vừa phải trả lời hàng trăm tin nhắn.

### Khi không rõ lỗi thuộc service nào

Có thể có một **first responder** hoặc incident commander nhận trách nhiệm điều phối ban đầu. Không nên buộc người phát hiện chứng minh tuyệt đối lỗi thuộc team khác trước khi được hỗ trợ. Service catalog, trace và dependency graph giúp chuyển đúng nhóm nhanh nhưng mọi người vẫn ưu tiên giảm ảnh hưởng người dùng.

## 17. Postmortem không đổ lỗi và vòng học hỏi

Sau sự cố, mục tiêu là cải thiện hệ thống và cách tổ chức, không phải tìm người để phạt. Một postmortem hữu ích trả lời:

- Người dùng bị ảnh hưởng thế nào, trong bao lâu?
- Tín hiệu nào cho thấy sự cố đầu tiên; thời điểm phát hiện?
- Thay đổi nào hoặc điều kiện nào kích hoạt lỗi?
- Vì sao các lớp bảo vệ hiện tại không ngăn hoặc phát hiện sớm?
- Những quyết định trong incident được đưa ra trên thông tin nào?
- Những yếu tố hệ thống/tổ chức khiến phản ứng chậm?
- Có cơ hội cải thiện test, rollback, contract, alert, runbook hay quyền truy cập?
- Ai sở hữu action items và khi nào kiểm chứng kết quả?

**Blameless** không có nghĩa không có accountability. Hành động vẫn cần owner và thời hạn, nhưng tránh kết luận rằng “lỗi do người vận hành bấm nhầm” khi hệ thống cho phép thao tác nguy hiểm mà không có preview, approval hoặc rollback.

### Ví dụ

Một deploy Order mới gây timeout vì connection pool cấu hình sai. Một bản review không tốt nói “developer triển khai ẩu”. Một bản review hữu ích phân tích tại sao pre-production không phát hiện config mismatch, vì sao SLO alert trễ, vì sao rollback cần xin quyền ngoài giờ, và cách giảm xác suất sự cố lặp lại.

## 18. Vòng feedback từ production tới thiết kế

End-to-end ownership mạnh khi tín hiệu production làm thay đổi cách xây dựng sản phẩm:

~~~text
Production issue
      |
      v
SLO/trace/runbook + phản hồi người dùng
      |
      v
Nhóm owner tìm nguyên nhân và tác động
      |
      v
Test mới, API behavior, timeout, data model,
capacity, retry, deploy guardrail...
      |
      v
Release có kiểm chứng
      |
      v
Đo lại outcome và giảm toil
~~~

Nếu nhóm vận hành chỉ viết ticket để nhóm phát triển “xử lý khi rảnh”, vòng feedback chậm và sự cố lặp lại. Nên dành năng lực định kỳ cho reliability work, gộp những bài học từ incident vào Definition of Done và kế hoạch sản phẩm.

### Ví dụ cải tiến

Service bị nhiều request trùng khi Payment timeout. Owner Payment có thể cải thiện idempotency ledger, test sau commit/trước ACK và trạng thái unknown outcome; Checkout Team cập nhật cách hiển thị Pending; platform cung cấp distributed tracing; product cập nhật kỳ vọng thời gian xác nhận. Đây là cộng tác nhiều nhóm **với trách nhiệm rõ**, không phải một nhóm ôm mọi thành phần.

## 19. Definition of Done cho một thay đổi service

Một feature không “xong” chỉ vì unit test xanh. Với release production, owner nên có tiêu chí hoàn tất phù hợp rủi ro.

Ví dụ:

1. Business behavior được mô tả và người dùng có cách xác nhận kết quả.
2. API/event contracts được cập nhật, có phiên bản/compatibility policy.
3. Unit/integration/contract tests bao phủ đường chính và các lỗi quan trọng.
4. Schema migration có expand-contract/rollback hoặc dữ liệu được bảo vệ.
5. Monitoring/SLI phản ánh behavior mới; alert có owner.
6. Feature flag hoặc rollout strategy được chọn cho thay đổi rủi ro.
7. Secret/config không hardcode, quyền truy cập đúng mức.
8. Artifact có source revision, image digest và quy trình release truy vết.
9. Cập nhật runbook khi phát sinh đường lỗi mới.
10. Security/dependency scan và data classification phù hợp.
11. Có cách giảm thiệt hại khi release lỗi.
12. Team biết rõ ai hỗ trợ nếu dependency/managed platform gặp vấn đề.

Checklist phải cân theo mức rủi ro. Không cần một thay đổi text label trải qua cùng thủ tục như đổi thuật toán capture payment, nhưng **quyền sở hữu kết quả** vẫn là một.

## 20. Nhóm owner và platform team: hợp đồng cộng tác

Platform team tồn tại để giảm gánh nặng nhận thức và thao tác lặp lại cho các nhóm sản phẩm: pipeline, Kubernetes, image registry, service discovery, observability, secrets, database provisioning và developer experience.

Một mô hình tự phục vụ:

~~~text
Order Team                       Platform Team
    |                                  |
    |-- Declare desired resources ---->|
    |                                  |-- Provision theo policy
    |<-- Self-service result ----------|
    |                                  |
    |-- Publish image + deploy ------->|
    |                                  |-- Verify, rollout, monitor
    |<-- Deployment status ------------|
    |                                  |
    |-- Escalate platform issue ------>|
    |<-- Platform recovery ------------|
~~~

Điều cần tránh: mọi service phải tạo ticket rồi chờ platform engineer sửa YAML, mở secret, scale pod hoặc deploy. Khi platform trở thành hàng đợi bắt buộc, microservices bị coupling qua quy trình.

### Product mindset cho internal platform

Một platform tốt có:

- **Đối tượng sử dụng rõ:** các đội service.
- **API/template/documentation:** cung cấp golden path dễ dùng.
- **Reliability/SLI của chính platform:** pipeline availability, provision time, deploy success.
- **Versioning/compatibility:** thay đổi runtime hoặc template không buộc mọi service sửa cùng lúc khi có thể.
- **Support model:** on-call, escalation, maintenance window.
- **Feedback:** đo thời gian tự phục vụ, ticket backlog và đau điểm của team.

Golden path là đường mặc định an toàn, không nên biến thành khóa chặn mọi trường hợp ngoại lệ hợp lệ. Có thể có cơ chế exception có audit khi workload đặc biệt cần giải pháp khác.

## 21. SRE/reliability engineering hỗ trợ nhưng không xóa owner

SRE là chức năng chuyên môn về reliability, automation, observability, capacity và incident response. Tổ chức có thể áp dụng SRE theo nhiều hình thức: đội tập trung, embedded SRE, tư vấn theo giai đoạn hoặc shared reliability guild.

Những nhiệm vụ có thể chia:

| Việc | Service team | SRE/Platform |
|---|---|---|
| Chọn SLI gắn hành trình | Chủ động cùng Product | Tư vấn đo và thiết kế SLO |
| Theo dõi error budget | Điều hành reliability backlog | Cung cấp tooling/policy chung |
| Tối ưu business flow | Sở hữu code/domain invariant | Hỗ trợ phân tích capacity/latency |
| Incident của service | Responder và chủ động fix | Hỗ trợ escalation/coordination |
| Incident cluster/managed platform | Giữ ngữ cảnh tác động | Sở hữu recovery hạ tầng |
| Automation lặp lại | Loại bỏ toil trong service | Xây nền tảng/hệ thống tự động |
| Thiết kế resilience | Định nghĩa failure behavior | Hỗ trợ game day và hướng dẫn kỹ thuật |

Không nên giao mọi error budget của một service cho SRE rồi để team code tiếp tục phát hành mà không nhìn thấy sản phẩm đang hỏng. Trái lại, SRE cũng không nên phải xin quyền từ một nhóm sản phẩm để sửa lỗi platform chung do họ sở hữu.

## 22. Ownership của dữ liệu và schema migration

Microservices thường theo nguyên tắc mỗi bounded context sở hữu dữ liệu và schema của mình. Điều này có nghĩa:

- Order Team quyết định business meaning và schema của Order.
- Payment Team quyết định ledger/idempotency record của Payment.
- Inventory Team sở hữu reservation và availability.
- Platform/DB specialists có thể vận hành cơ sở dữ liệu vật lý hoặc cung cấp công cụ migration.
- Consumers truy cập qua API/event contract hoặc read models được quản lý, không tự sửa bảng nội bộ bên khác.

### Ví dụ migration đúng ownership

Order muốn thêm trường `deliveryPreference`:

1. Order Team thiết kế schema phù hợp và làm migration additive.
2. Phiên bản cũ/mới của Order có thể cùng hoạt động trong cửa sổ rollout.
3. API/event thay đổi có contract tests và chính sách backward compatibility.
4. Consumer tự chọn thời điểm nâng trong thời hạn hỗ trợ.
5. Order Team quan sát query performance, migration lag và dữ liệu cũ.
6. Chỉ loại bỏ trường/hợp đồng cũ khi các consumer và dữ liệu liên quan đã chuyển an toàn.

Nếu Payment bắt buộc sửa bảng Order trực tiếp hoặc phụ thuộc JPA entity của Order, tính độc lập đã bị giảm. Ownership phải đi cùng **ranh giới kỹ thuật thực sự**.

## 23. API và event contract là nơi ownership gặp nhau

Một service có thể triển khai độc lập khi các service khác chỉ phụ thuộc vào **hợp đồng công khai**, không cần biết model hoặc database nội bộ.

Một contract cần có:

- Owner producer và kênh hỏi đáp.
- Versioning và compatibility policy.
- Schema và semantic meaning của từng field.
- Error behavior, timeout, retry và idempotency.
- Ordering/delivery semantics với event.
- Deprecation window và migration guide.
- Consumer contract testing hoặc compatibility matrix.
- Phạm vi dữ liệu nhạy cảm, authentication và authorization.

### Phối hợp mà không đồng bộ deploy

Ví dụ Payment thêm optional field `providerReference` vào PaymentCompleted:

~~~text
Payment v2 producer ----> PaymentCompleted (+ optional field)
       |
       +-- Order v1 consumer vẫn parse được
       +-- Notification v1 consumer vẫn parse được
       +-- Analytics v2 consumer dùng field mới
~~~

Tính tương thích chỉ hợp lệ nếu consumer cũ xử lý unknown field theo hợp đồng, serializer và schema registry cho phép. Không mặc định thêm field luôn an toàn.

Producer owner chịu trách nhiệm công bố contract mới và chạy kiểm tra producer–consumer phù hợp; consumer owner chịu trách nhiệm khi áp version mới. Không nhất thiết triển khai mọi service cùng lúc.

## 24. Chịu trách nhiệm về phụ thuộc nhưng không sở hữu phụ thuộc

Một service có thể dựa vào external provider, managed DB hoặc service của nhóm khác. Owner không thể sửa code của dependency trong mọi tình huống, nhưng vẫn chịu trách nhiệm **thiết kế ứng xử của service khi dependency lỗi**.

Ví dụ Checkout gọi Payment:

- Đặt timeout và deadline phù hợp trải nghiệm checkout.
- Retry có giới hạn và chỉ với operation idempotent/được bảo vệ.
- Circuit breaker/bulkhead để tránh mất toàn bộ worker pool.
- Unknown outcome được hiển thị/đối soát, không tự suy luận “chưa charge”.
- Runbook ghi rõ provider status và escalation contact.
- Monitoring phân biệt lỗi Checkout và lỗi Payment provider.
- Thiết lập hợp đồng giữa nhóm và mục tiêu chất lượng phù hợp.

Owner có thể làm nhiều điều để giảm tác động từ dependency mà không cần nắm quyền hạ tầng của bên đó. Ngược lại, không thể đặt SLO thiếu thực tế nếu dependency có giới hạn khách quan; cần thỏa thuận mục tiêu và kiến trúc dự phòng.

## 25. Service ownership trong một hệ thống có shared components

Các thành phần dùng chung như authentication, API gateway, event broker và shared libraries cần owner riêng theo **phạm vi dịch vụ nền tảng**.

Không nên có “shared” nghĩa là “không ai sở hữu”. Một broker cluster có platform owner chịu trách nhiệm hạ tầng; từng topic/event contract cần business owner xác định retention, schema, partition key và consumer semantics. Một thư viện common-auth có library owner quản lý API/version/security; mỗi service consumer quyết định nâng bản nào theo policy và chịu trách nhiệm cấu hình quyền cho dịch vụ của mình.

### Khi xảy ra incident xuyên nhiều dịch vụ

Ví dụ broker outage gây OrderCompleted backlog:

- Platform/broker owner chịu trách nhiệm phục hồi cluster và độ bền log.
- Order Team xác minh outbox, có event nào chưa phát hoặc phát trùng.
- Payment Team kiểm tra idempotency/reconciliation và xử lý trạng thái bất định.
- Notification Team xử lý backlog/duplication sau recovery.
- Incident commander điều phối các bước để không mở consumer gây side effect quá sớm.

**Trách nhiệm được phân ranh theo hành động**, nhưng sự phục hồi end-to-end được phối hợp.

## 26. Bảo mật thuộc vòng đời dịch vụ

Không thể giao toàn bộ security cho một team trung tâm rồi giả định product team không còn việc làm. Service owner phải hiểu:

- Dữ liệu nào là nhạy cảm, ở đâu, giữ trong bao lâu.
- Authentication/authorization của API, service-to-service identity.
- Secret rotation và cách ứng dụng nhận credential khi chạy.
- Sử dụng thư viện và base image có lỗ hổng; lịch vá.
- Dependency/SBOM và kiểm soát nguồn build.
- Audit các hành động quan trọng.
- Đường xử lý khi dữ liệu bị lộ, credential bị compromise.
- Backup/restore và deletion policy.

Security team có thể cung cấp policy, threat modeling, scanning, incident expertise và kiểm tra độc lập. Platform triển khai secret manager/IAM/admission policies. Service owner cần đảm bảo code, config và data handling đáp ứng guardrails.

### Quyền thay đổi trong incident bảo mật

Có thể cần tạm dừng tính năng, revoke token, rotate secret hoặc hạn chế network. Quyền phê duyệt và trách nhiệm được chuẩn bị trước, không nên phải bắt đầu thương lượng giữa các nhóm khi credential đã bị lộ.

## 27. Chi phí và công suất là một phần ownership

Team sở hữu service nên thấy tác động tài nguyên của quyết định kiến trúc:

- CPU/memory và replica count.
- Database storage, IOPS, query cost và backup retention.
- Message volume, partition count và retention.
- Network egress, CDN/cache hit ratio.
- Log/tracing cardinality và telemetry cost.
- Chi phí managed provider và licensing.
- Hiệu quả sử dụng công suất trong giờ cao điểm và giờ thấp điểm.

Mục tiêu không phải “giảm cost bằng mọi giá”. Nếu tăng cache giúp p99 checkout giảm và giảm database load, đó có thể là đầu tư tốt. Nếu giảm replica khiến SLO vi phạm, khoản tiết kiệm trực tiếp có thể làm tăng thiệt hại người dùng.

Một dashboard service có thể hiển thị:

~~~text
SLO và user outcome
  |-- error budget, latency-good, correctness
Capacity
  |-- QPS, concurrency, saturation, queue depth
Cost
  |-- monthly spend, cost/request, storage growth
Change
  |-- deploy frequency, rollback, incident after changes
~~~

Các chỉ số cần giải thích theo business context. “Chi phí trên mỗi request” có thể tăng khi đầu tư vào encryption hoặc redundancy bắt buộc, không mặc định là thất bại.

## 28. Cân bằng tốc độ delivery và reliability

Khi nhóm owner vừa làm feature vừa vận hành, có nguy cơ reliability bị đẩy xuống cuối backlog do áp lực roadmap. Cần cơ chế quyết định có thể quan sát:

- SLO/error budget là tín hiệu về chất lượng đã cung cấp.
- Định nghĩa những lỗi nghiêm trọng không được “cho phép” bởi error budget (ví dụ charge trùng, mất dữ liệu).
- Product hiểu tác động của degraded mode và thời gian xử lý.
- Reliability backlog có owner, ưu tiên và năng lực thực thi.
- Rollout rủi ro cao có canary/feature flag/rollback.
- Khi burn rate cao, nhóm có quyền ưu tiên giảm thiệt hại và sửa nguyên nhân.
- Review kỹ thuật định kỳ để giảm toil và debt làm đội trực căng thẳng.

**Không coi số incident thấp là bằng chứng tự động đội tốt.** Có thể hệ thống ít traffic hoặc instrumentation kém. Cần nhìn SLI, thời gian khắc phục, độ phủ quan sát và kết quả người dùng.

## 29. Đo hiệu quả tổ chức mà không tạo vanity metrics

Một team ownership tốt thường cải thiện cả delivery và vận hành, nhưng cần dùng metric thận trọng.

| Góc nhìn | Metric có thể hữu ích | Bẫy diễn giải |
|---|---|---|
| User outcome | SLI/SLO, support complaints, conversion impact | Số trung bình che nhóm người dùng nhỏ |
| Delivery | Lead time, deploy frequency, change failure rate | Ép tăng số deploy dù không tạo giá trị |
| Recovery | Time to detect/mitigate/recover, error budget burn | Chỉ đếm thời gian đóng ticket |
| Ownership clarity | % service có owner/on-call/runbook đúng | Catalog có tên nhưng team không có quyền |
| Toil | Giờ lặp lại cho alert/ticket/manual deploy | Người trực có thể chưa ghi lại mọi thao tác |
| Quality | Repeated incidents, rollback success, contract breaks | Đếm bug mà bỏ mức tác động |
| Developer experience | Thời gian self-service provision/deploy | Số template được tạo nhưng ít ai dùng |
| Cost | Cost per unit business value và resource efficiency | Giảm cost làm giảm reliability |

Không dùng metric riêng lẻ để xếp hạng cá nhân, tạo động cơ che lỗi, chia nhỏ deploy giả tạo hay cố tình bỏ metric khó. Đo để **phát hiện nút thắt trong hệ thống công việc**, không để phục vụ một bảng thi đua đơn giản.

## 30. Một trường hợp cụ thể: Checkout Team end-to-end

Giả sử đội Checkout chịu trách nhiệm điều phối đặt hàng, có 7 thành viên gồm backend, frontend, tester có năng lực automation và người tập trung reliability. Payment, Inventory và Platform là các đội khác.

### Quyền sở hữu của Checkout

- Checkout orchestration/API, yêu cầu và session flow.
- Định nghĩa logical checkout attempt.
- SLI về tỷ lệ completion và latency trải nghiệm.
- Timeout/backoff và cách trình bày trạng thái Pending.
- Consumer contracts với Payment/Inventory.
- Release image, config, migration của state riêng, rollback.
- On-call và runbook cho checkout journey.
- Việc phối hợp khi dependency outage ảnh hưởng người mua.

### Checkout không trực tiếp sở hữu

- Ledger và rule xử lý charge của Payment.
- Công thức phân bổ stock và database của Inventory.
- Kubernetes control plane hoặc toàn bộ Kafka cluster.
- Secret/KMS policy toàn tổ chức.
- Mọi client ứng dụng trong hệ sinh thái.

### Luồng thay đổi bình thường

~~~text
Product yêu cầu cải thiện giao diện Pending
             |
             v
Checkout Team chỉnh UI và trạng thái orchestration
             |
             v
Contract test với Payment/Order
             |
             v
Canary riêng Checkout
             |
             v
Đo checkout success, latency, unknown-outcome rate
~~~

Không cần Payment/Inventory cùng deploy khi contract giữ tương thích.

### Luồng sự cố

~~~text
Checkout SLI giảm
      |
      v
Checkout on-call nhận page
      |
      +-- Nếu bug mới ở Checkout: rollback/fix
      |
      +-- Nếu Payment provider lỗi: phối hợp Payment Team,
      |   chuyển trạng thái Pending/giảm retry có kiểm soát
      |
      +-- Nếu broker platform lỗi: escalate broker owner,
          kiểm tra outbox/inbox và backlog
      |
      v
Khôi phục trải nghiệm + kiểm tra đúng dữ liệu
      |
      v
Joint postmortem, owner action items cụ thể
~~~

Dù nhiều đội tham gia, có một đầu mối điều phối hành trình và một owner rõ cho mỗi thành phần.

## 31. Handoff khi chuyển quyền sở hữu dịch vụ

Service có thể đổi nhóm khi tổ chức thay đổi. Chuyển repository không đủ để hoàn tất bàn giao.

Một **handoff package** cần:

1. Service catalog, business capability và contract công khai.
2. Source, CI/CD, artifact, image digests và release history.
3. SLO, error budget, dashboard và alert routing.
4. Runbook, incident history, known failure modes và escalation contacts.
5. Database/schema, migration, backup/restore và data retention.
6. Broker topics, producer/consumer groups, DLQ, replay policy.
7. Secrets/identity và quyền quản lý được cấp đúng policy.
8. Dependency graph, provider SLA và hợp đồng phiên bản.
9. Capacity/cost, forecast và các giới hạn hiện tại.
10. Reliability backlog, debt, lỗ hổng đang xử lý và planned changes.
11. Lịch trực và quy trình primary/secondary có mốc chuyển giao.
12. Một giai đoạn shadowing/paired on-call nếu rủi ro cao.

### Phương án chuyển giao có kiểm chứng

~~~text
T0: Hai đội thống nhất owner tương lai và scope.
T1: Đội mới có read access dashboard/log/runbook.
T2: Paired incident drill, triển khai staging, thử rollback.
T3: Đội mới deploy một thay đổi nhỏ có kiểm chứng.
T4: Đổi primary on-call, đội cũ làm backup theo thời hạn.
T5: Cập nhật catalog/alerts/RACI và đóng bàn giao.
~~~

Không đổi on-call vào cuối ngày mà đội nhận chưa có quyền xem production hoặc chưa từng thử rollback. Nếu phải chuyển gấp, cần ghi rõ rủi ro và hỗ trợ quá độ.

## 32. Onboarding thành viên mới vào một team sở hữu service

Một thành viên mới cần hiểu cả kiến trúc lẫn sản phẩm:

- Bối cảnh business: ai dùng, thao tác nào quan trọng và tác hại khi lỗi.
- Boundaries: service owner, data owner, dependencies và contracts.
- Repo: build/test, cách chạy local và staging.
- Release: branch, CI, canary, feature flags, rollback.
- Observability: đọc dashboard, trace và hiểu SLO.
- Vận hành: xử lý alert thường gặp, game day, incident command.
- Data: migration, backup, restore, reconciliation.
- Security: quyền truy cập, secret handling, loại dữ liệu.
- Cross-team collaboration: cách hỏi provider owner, dùng service catalog.
- Technical debt: những phần khó/rủi ro đã biết.

**Chưa nên giao trực on-call độc lập** chỉ vì người mới đã sửa một bug. Có thể yêu cầu tham gia shadow on-call, tự xử lý một alert giả lập, chạy release thử nghiệm và biết khi nào cần escalation.

## 33. Rủi ro của “nhiều team cùng sở hữu một service”

Một số service cần nhiều nhóm cùng đóng góp. Điều này không sai, nhưng nếu không có authority rõ có thể dẫn đến:

- Không ai quyết định breaking changes.
- Chậm xử lý incident vì từng nhóm nghĩ nhóm kia phụ trách.
- CI pipeline và alert bị sửa mà không báo người vận hành.
- Database migration chồng chéo.
- Quá nhiều người có quyền production nhưng không ai chịu trách nhiệm audit.
- SLO chung không có người bảo trì measurement.
- Tài liệu lỗi thời vì không có đầu mối.

Có thể áp dụng **primary owner + contributing teams**:

~~~text
Primary service owner:  Payment Team
Contributors:            Fraud, Security, Platform
Decision scope:          Payment API/runtime/domain
Mandatory consultation:  Những thay đổi ảnh hưởng fraud/compliance
Emergency authority:     Chính sách đã công bố
Escalation:              Payment primary/secondary + incident commander
~~~

Tách vai trò quyết định chính khỏi vai trò review chuyên môn. Không cần mọi contributor phải ký trước mỗi change nhỏ đã nằm trong contract.

## 34. Anti-pattern thường gặp

### 34.1. “Dev xây, Ops chịu”

Feature team bàn giao artifact rồi không tham gia production incident. Hệ quả là người viết code không biết nó gây timeout/queue lag thế nào; Ops chỉ có thể restart pod. Giải pháp là vòng feedback chung, ownership rõ và quyền rollback/diagnose của team.

### 34.2. “Ai cũng sở hữu” nghĩa là không ai sở hữu

Một service có nhiều team listed nhưng không có primary on-call, budget owner hoặc người quyết định API. Giải pháp là chỉ định accountable owner duy nhất cho mỗi capability, kèm contributors và escalation.

### 34.3. Owner trên catalog nhưng không có production access

Một đội được page nhưng không xem được trace, không rollback và phải mở ticket nhờ Ops. Giải pháp: self-service có guardrails, quyền tối thiểu và emergency escalation.

### 34.4. Platform biến thành ticket queue

Mọi service cần platform engineer thao tác YAML hoặc tạo database thủ công. Giải pháp: productize platform, API/template ổn định, self-service và tài liệu có kiểm chứng.

### 34.5. Team quá nhỏ bị buộc trực 24/7

Một hoặc hai engineer giữ nhiều service quan trọng. Burnout và single-person dependency trở nên nghiêm trọng. Giải pháp: gộp ownership theo năng lực, shared rotation đủ lớn, managed services, giảm số thành phần và tự động hóa.

### 34.6. Ownership bám vào công nghệ thay vì outcome

Một team chỉ tối ưu “Kafka uptime”, nhóm khác tối ưu “DB CPU”, nhưng không ai chịu trách nhiệm checkout bị treo. Giải pháp: SLO end-to-end, journey owner và dependency contracts.

### 34.7. Shared database phá ranh giới

Payment và Order cùng ghi bảng, không ai chịu trách nhiệm schema. Giải pháp: xác định data owner, tách truy cập qua API/event/read model và migrate dần.

### 34.8. Không có kế hoạch kết thúc service

Microservice cũ không ai dùng vẫn chạy, giữ secret cũ, chi phí và nguy cơ bảo mật. Giải pháp: lifecycle state rõ, owner chịu trách nhiệm decommission và xác minh consumer/data retention.

### 34.9. Coi số lượng microservice là thước đo trưởng thành

Tách service rất nhỏ tạo thêm pipeline, alert, contract và network failure, trong khi team không đủ khả năng vận hành. Giải pháp: chỉ tách khi có ranh giới nghiệp vụ, nhu cầu scale/release độc lập và năng lực ownership.

### 34.10. Chỉ làm postmortem nhưng không sửa toil

Incident lặp lại vì action items không có thời gian hoặc owner. Giải pháp: reliability work được ưu tiên trong roadmap, đo số cảnh báo lặp lại và kiểm tra hiệu quả sau sửa.

## 35. Lộ trình chuyển đổi từ tổ chức theo chức năng sang ownership

Không nên tái tổ chức toàn bộ công ty qua một thông báo. Có thể đi từng năng lực:

**Giai đoạn 1 — Inventory.** Lập danh sách service, repo, runtime, data, contract, on-call và người đang xử lý sự cố thật. Xác định service thiếu owner và các điểm phụ thuộc giao tiếp.

**Giai đoạn 2 — Chọn pilot.** Chọn một luồng nghiệp vụ có phạm vi đủ nhỏ nhưng đại diện, ví dụ Cart hoặc Catalog, với ít dependency nguy hiểm và đủ dữ liệu baseline.

**Giai đoạn 3 — Giao authority.** Team pilot có quyền xem production, thay code, chạy pipeline, rollback theo policy, tạo alert và quản lý schema logic. Platform hỗ trợ golden path.

**Giai đoạn 4 — Xây vòng quan sát.** Định nghĩa SLI/SLO cùng Product, làm service catalog, runbook, dashboard, owner của incident và escalation.

**Giai đoạn 5 — Thử release và incident.** Chạy một deploy canary thực, một rollback game day và tình huống dependency outage. Đo thời gian từ phát hiện đến giảm thiệt hại.

**Giai đoạn 6 — Giảm handoff.** Chuyển thao tác lặp lại thành self-service; điều chỉnh RACI ở những bước gây tắc nghẽn mà không tăng rủi ro an toàn.

**Giai đoạn 7 — Mở rộng theo năng lực.** Chuyển các service tiếp theo với handoff package; điều chỉnh số lượng team/service cho phù hợp capacity.

**Giai đoạn 8 — Kiểm chứng liên tục.** Review SLO, on-call fatigue, cost, delivery lead time, incident action items và feedback của người dùng. Nếu team thiếu nhân sự để thực thi ownership, phải điều chỉnh scope thay vì chỉ tăng trách nhiệm.

### Thành công đo bằng gì?

Không phải có bao nhiêu team đổi tên thành “stream-aligned”. Thành công là thay đổi thông thường không cần phối hợp vô lý; người dùng nhận chất lượng đã cam kết; on-call biết cách xử lý; service có khả năng rollback; incidents tạo ra cải tiến; và trách nhiệm không rơi vào khoảng trống.

## 36. Thực hành: xây service ownership charter

Nhóm có thể sử dụng một **ownership charter** ngắn:

~~~markdown
# Service Ownership Charter — Order

## Mục đích
- Năng lực nghiệp vụ:
- Người dùng/consumer:
- Bất biến quan trọng:
- Những việc nằm ngoài scope:

## Ownership
- Primary team:
- Secondary/escalation:
- Product representative:
- Platform/SRE contacts:
- Security/data contacts:

## Giao diện
- Public APIs và event contracts:
- Versioning, deprecation, compatibility:
- Dependencies và provider expectations:

## Vòng đời
- Repository, CI/CD, deploy strategy:
- Config/secret ownership:
- Database/schema và migrations:
- Backups, recovery, data retention:

## Vận hành
- User journey SLI/SLO:
- Dashboard và alert:
- Runbook và incident escalation:
- Capacity/cost:
- Reliability backlog:

## Authority và giới hạn
- Thay đổi nào team tự quyết theo policy?
- Thay đổi nào cần consult/approval?
- Emergency rollback hoặc freeze được phép như thế nào?

## Review
- Thời điểm review:
- Người phê duyệt ranh giới:
- Các dependency/rủi ro còn tồn tại:
~~~

Charter nên được lưu cạnh tài liệu service và liên kết từ catalog. Nó không thay thế các chính sách công ty về an toàn, compliance hoặc quyền production, mà mô tả cách chúng được áp dụng vào service cụ thể.

## 37. Tình huống thực hành 1: Checkout lỗi sau deploy

**Bối cảnh:** Checkout Team deploy một thay đổi timeout. SLO checkout giảm từ 99,95% xuống 98,5% trong 15 phút. Payment Team báo ledger vẫn hoạt động, nhưng retry requests tăng đột biến.

### Câu hỏi đặt ra

1. Ai nhận alert đầu tiên và vì sao?
2. Ai có quyền tạm dừng rollout hoặc rollback Checkout?
3. Team nào điều tra Payment retry/idempotency, team nào điều tra Checkout deadline?
4. Khi nào cần incident commander?
5. Ai xác minh số order/charge bị ảnh hưởng và thông báo người dùng?
6. Sau incident, ai sở hữu việc bổ sung timeout tests và metric?

### Một cách phân công hợp lý

Checkout on-call nhận cảnh báo journey, xác minh deploy và rollback khi phù hợp. Payment Team kiểm tra unknown outcome và idempotency, xử lý các charge cần đối soát. Platform hỗ trợ nếu có vấn đề gateway/observability. Product/communications hỗ trợ thông báo. Incident commander điều phối nếu tác động rộng. Action items có owner, thời hạn và phép đo xác nhận kết quả.

Điều quan trọng không phải đội nào “đáng trách” mà là người dùng được bảo vệ và mọi sửa đổi có nơi thực hiện.

## 38. Tình huống thực hành 2: một shared library buộc nâng đồng loạt

**Bối cảnh:** Platform Team phát hành common starter mới, đổi default retry và TLS config. Tất cả service bị yêu cầu dùng bản mới trong cùng ngày; nhiều đội phải trì hoãn feature.

Phân tích:

- Platform sở hữu starter, public API và release notes.
- Mỗi service owner chịu trách nhiệm đánh giá tác động bản nâng với workload của mình.
- Breaking behavior cần được phân loại, có opt-in/deprecation window nếu khả thi.
- Artifact version phải bất biến và các service được phép pin version trong support window.
- Security emergency có thể có deadline chung, nhưng vẫn nên cho service test/deploy độc lập theo policy.

Bài học: end-to-end service ownership đòi **thư viện và platform cung cấp compatibility contract**, không dùng “one-size-fits-all latest” làm quy tắc mặc định.

## 39. Tình huống thực hành 3: broker outage và consumer backlog

**Bối cảnh:** Shared broker down 20 phút, rồi khôi phục. Order events được phát lại; Notification gửi email trùng; Inventory consumer lag tăng.

Trách nhiệm:

- Broker owner khôi phục cluster, kiểm tra log, replication, ACL và retention.
- Order owner xác minh outbox/events và trạng thái order.
- Inventory owner bảo đảm dedup, invariant reservation và xử lý backlog.
- Notification owner xử lý email idempotency/delivery ledger; không gửi trùng vô hạn.
- Journey owner giám sát trải nghiệm người mua và dữ liệu hiển thị.
- Incident commander phối hợp thứ tự mở lại writes/consumers khi cần.

Một sơ đồ ownership chỉ có “broker là của Platform” không đủ để khôi phục luồng nghiệp vụ. Consumer behavior, external side effects và data correctness vẫn thuộc những owner tương ứng.

## 40. Bài tập tự luyện

### Bài A — Lập service catalog

Một hệ thống có 12 microservice nhưng chỉ 5 service có on-call rõ. Hãy đề xuất những trường tối thiểu trong catalog, thứ tự xử lý service critical chưa có owner và quy tắc cập nhật metadata sau khi đổi team.

### Bài B — Phân ranh RACI

Order Team sở hữu dữ liệu order; Database Platform Team vận hành PostgreSQL cluster. Một migration làm query chậm. Hãy viết RACI cho phát hiện, rollback migration, tune index, nâng cluster và thông báo Product.

### Bài C — Thiết kế sustainable on-call

Một đội 3 người bị page 30 lần mỗi tuần, phần lớn do pod restart tự phục hồi. Hãy thiết kế thay đổi alert, automation, escalation và staffing/scope. Giải thích vì sao không nên đơn giản yêu cầu mỗi người trực nhiều hơn.

### Bài D — SLO gắn trải nghiệm

Checkout API trả 200 phần lớn thời gian nhưng người dùng bị treo ở bước Pending. Hãy định nghĩa một logical checkout SLI, cách xử lý timeout, retry, late success, và phân công owner telemetry.

### Bài E — Breaking event contract

Payment muốn xóa một field mà hai consumer cũ đang dùng. Hãy đề xuất trách nhiệm producer/consumer, compatibility tests, deprecation window và kế hoạch release độc lập.

### Bài F — Chuyển giao service

Một nhóm khác tiếp nhận Notification Service vào cuối tháng. Hãy tạo handoff package, thời gian paired on-call và tiêu chí chứng minh team mới có thể rollback, xử lý DLQ và rotate secret.

### Bài G — Incident đa nhóm

Một cụm Kafka lỗi khiến Checkout, Order và Notification ảnh hưởng. Hãy xác định incident commander, broker owner, business data owners và các acceptance checks trước khi mở lại traffic.

### Bài H — Team topology

Một nhóm 5 người đang sở hữu 18 service nhỏ, 5 database và 8 queue. Hãy đánh giá cognitive load, trách nhiệm on-call, khả năng hợp nhất service và ranh giới domain thay vì chia nhóm theo số repository.

### Bài I — Quyền và guardrails

Team được yêu cầu chịu trách nhiệm production nhưng không có quyền xem log, rollback hay đọc deployment status. Hãy thiết kế self-service với RBAC, audit và emergency access; mô tả giới hạn bảo mật cần giữ.

### Bài J — Product và error budget

Một feature mới làm SLO Search giảm trong khi conversion chưa thay đổi rõ. Hãy mô tả cuộc trao đổi giữa Product và Search Team về user impact, rollout, error budget và thí nghiệm tiếp theo.

### Bài K — Cost và reliability

Một đội muốn giảm 40% chi phí bằng cách giảm replica từ 6 xuống 2, nhưng p99 latency tăng gấp đôi lúc flash sale. Hãy đề xuất bộ số liệu và tiêu chí quyết định cân bằng chi phí với trải nghiệm.

### Bài L — Dịch vụ hết vòng đời

Một service cũ không còn traffic hợp lệ nhưng vẫn giữ database chứa dữ liệu khách hàng và một secret có hạn lâu. Hãy thiết kế plan decommission: kiểm tra consumer, xử lý retention, thu hồi secrets, cập nhật catalog và cách rollback nếu phát hiện dependency ẩn.

## 41. Checklist để áp dụng

Trước khi nói một nhóm đã thực sự sở hữu dịch vụ end-to-end, hãy kiểm tra:

1. Nhóm có **business capability rõ ràng** và ranh giới không chồng lấn vô lý?
2. Service có primary owner/team và kênh backup/escalation?
3. Ownership được ghi trong catalog, không chỉ ở một slide tổ chức?
4. Nhóm có quyền xem metric/log/trace và triển khai/rollback theo policy?
5. API, event, schema, database và data lifecycle có owner rõ?
6. Các dependency và team owner của chúng có thể liên hệ được?
7. SLI/SLO có phản ánh hành trình người dùng và được Product đồng thuận?
8. Alert có hành động, không mặc định page cho mọi pod restart?
9. On-call rotation có đủ người, training, backup và workload bền vững?
10. Có runbook, postmortem và reliability backlog với owner?
11. Release có canary/rollback, contract tests và migration policy?
12. Hệ thống có cách xử lý timeout, retry, duplicate và unknown outcome?
13. Security, secret rotation, patching và data classification đã được tích hợp vào vòng đời?
14. Team có dữ liệu về capacity/cost và quyền quyết định trong guardrails?
15. Platform có self-service, reliability và support model thay vì ticket queue?
16. Có quy trình incident xuyên team, không tranh cãi ownership trước khi giảm tác động?
17. Service mới có acceptance criteria để đi vào production?
18. Khi đổi team, handoff package và quyền production được xác minh?
19. Có phương án retire service không còn cần thiết?
20. Những hạn chế về staffing/cognitive load được xử lý thật thay vì viết thêm trách nhiệm lên giấy?

## 42. Tổng kết

Trong microservices, **service là một đơn vị vận hành và thay đổi**, không chỉ là một chương trình chạy trong container. Một nhóm sở hữu service xuyên suốt cần biết sản phẩm cung cấp giá trị gì, dữ liệu thuộc về ai, hợp đồng với các dịch vụ khác ra sao, người dùng trông đợi mức chất lượng nào và phải làm gì khi production gặp sự cố.

Mô hình ownership hiệu quả có ba trụ cột: **trách nhiệm rõ**, **quyền hạn/công cụ đủ để hành động**, và **vòng phản hồi liên tục từ production về thiết kế sản phẩm**. Platform, SRE, security và database specialists vẫn rất quan trọng; họ cung cấp năng lực, guardrails và chuyên môn thay vì tạo thêm những hàng đợi bàn giao không cần thiết.

Không có một công thức “một nhóm = một service”. Cách chia nhóm tốt là cách giúp các đội duy trì lượng công việc và on-call bền vững, triển khai phần lớn thay đổi độc lập, phối hợp đúng nơi hợp đồng giao nhau và cùng bảo vệ trải nghiệm người dùng. Khi mỗi service có owner thực sự cùng cơ chế cộng tác rõ, tổ chức mới khai thác được lợi ích của microservices mà không biến hệ thống thành một mạng lưới trách nhiệm mơ hồ.

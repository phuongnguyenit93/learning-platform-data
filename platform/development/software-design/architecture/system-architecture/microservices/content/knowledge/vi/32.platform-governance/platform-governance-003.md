# Danh mục dịch vụ, người sở hữu và thông tin vận hành trong microservices

## 1. Bối cảnh: khi hệ thống có hàng chục hoặc hàng trăm dịch vụ

Microservices giúp các nhóm phát triển và phát hành độc lập, nhưng số lượng thành phần vận hành cũng tăng. Một lỗi tại checkout-service có thể liên quan API gateway, inventory-service, pricing-service, payment-service, message broker hoặc một database do đội khác quản lý. Trong sự cố, câu hỏi khẩn cấp thường không phải “dịch vụ này có endpoint nào?” mà là:

- Dịch vụ này do nhóm nào sở hữu và ai trực sự cố?
- Nó phục vụ năng lực nghiệp vụ nào, có quan trọng tới mức nào?
- Repository, pipeline, artifact, môi trường và vùng triển khai ở đâu?
- SLO, dashboard, log, trace và runbook chính xác là gì?
- Nó phụ thuộc dịch vụ, topic, database và nhà cung cấp bên ngoài nào?
- Ai phê duyệt thay đổi, điều phối escalation, quyết định rollback?
- Dịch vụ còn hoạt động hay đã được thay thế nhưng vẫn xuất hiện trên sơ đồ cũ?
- Làm sao một thành viên mới biết đường liên hệ và tiêu chuẩn vận hành trước khi thay đổi code?

**Service catalog (danh mục dịch vụ)** là một tập hợp metadata có cấu trúc giúp con người và hệ thống tìm, hiểu, quản lý và vận hành các service và các thực thể liên quan. Catalog không chỉ là một bảng tên: nó kết nối **năng lực nghiệp vụ – thành phần kỹ thuật – nhóm sở hữu – tài liệu – quan sát – quy trình vận hành**.

Một danh mục có giá trị khi câu hỏi “ai chịu trách nhiệm cho service này, nó ở đâu và làm sao khôi phục khi lỗi?” có thể được trả lời từ một nguồn đáng tin cậy, cập nhật gần với thay đổi thật.

Mục tiêu bài học:
1. Phân biệt service catalog với runtime service discovery và CMDB truyền thống.
2. Xác định metadata tối thiểu, ownership và thông tin vận hành bắt buộc.
3. Xây dựng mô hình thực thể, quan hệ phụ thuộc và vòng đời service.
4. Thiết kế nguồn cập nhật từ Git, CI/CD, cloud, Kubernetes và telemetry.
5. Dùng catalog trong incident response, onboarding, platform engineering và governance.
6. Định nghĩa kiểm tra chất lượng metadata, quyền sửa, cơ chế chống dữ liệu cũ.
7. Thực hành tạo catalog entry và quy trình đăng ký service mới trong hệ thống Java microservices.

## 2. Catalog khác runtime service discovery

Hai hệ thống có thể cùng chứa tên dịch vụ nhưng trả lời những câu hỏi khác nhau.

| Khía cạnh | Service catalog | Runtime service discovery |
| --- | --- | --- |
| Câu hỏi | Dịch vụ là gì, ai sở hữu, vận hành thế nào? | Instance nào hiện sẵn sàng để gửi request? |
| Đối tượng | Service logic, team, API, dependency, system, domain | Pod, endpoint, address, healthy instance |
| Vòng đời thông tin | Theo ngày/commit/release và thay đổi tổ chức | Biến động liên tục theo giây |
| Nguồn | Git metadata, CI/CD, cloud inventory, owners, policy | Kubernetes Service/Endpoints, registry runtime, mesh |
| Người dùng | Developer, SRE, security, kiến trúc sư, incident commander | Load balancer, client SDK, mesh, gateway |
| Trạng thái | Active, proposed, deprecated, retired, ownership | Healthy, unready, terminating, unreachable |
| Nội dung | Runbook, dashboard, SLO, repository, risk tier | Network location, health, route/port |
| Mục đích | Governance, khám phá, tác nghiệp, quản trị rủi ro | Định tuyến và cân bằng tải |

Một service có thể có **một entry catalog** và **hàng chục instance runtime** trong nhiều cluster. Khi scale từ 5 lên 20 pod, thông tin chủ sở hữu không thay đổi. Khi service chuyển owner từ team A sang team B, địa chỉ của các pod không nhất thiết thay đổi.

**CMDB (Configuration Management Database)** thường quản lý configuration items và quan hệ của nhiều loại tài sản, có thể bao gồm server, network, license, ứng dụng và business services. Service catalog dành cho developer/platform có thể là một lớp chuyên biệt hoặc tích hợp với CMDB; không cần tạo hai nguồn sự thật xung đột cho cùng thuộc tính.

**API catalog** liệt kê interface/API; nó có thể là một phần của service catalog. Một service thường có nhiều API và cũng có thể có event, consumer, database, scheduled job. Catalog chỉ liệt kê OpenAPI mà không có owner/runbook sẽ khó phục vụ incident response.

## 3. Các thực thể nên mô hình hóa

Một thiết kế catalog không nên nhồi mọi quan hệ vào trường văn bản tự do.

- **Domain:** vùng nghiệp vụ lớn như Commerce, Payments, Customer.
- **System:** nhóm thành phần hỗ trợ một năng lực sản phẩm, ví dụ Checkout Platform.
- **Component/Service:** ứng dụng deploy độc lập như order-service.
- **API:** interface HTTP/gRPC mà component cung cấp hoặc tiêu thụ.
- **Event/Topic:** hợp đồng sự kiện và kênh pub/sub.
- **Resource:** database, queue, bucket, cache, index, cluster, secret reference.
- **Team/Group:** đơn vị tổ chức chịu trách nhiệm kỹ thuật.
- **User/On-call Role:** người hoặc nhóm trực nhận escalation theo lịch.
- **Environment/Deployment:** bản service cụ thể trong staging, production, region.
- **Documentation/Runbook:** kiến thức thiết kế và thao tác vận hành.
- **Dependency/Relationship:** consumes API, publishes event, owns data, depends on system.
- **SLO/Policy:** tiêu chuẩn chất lượng và yêu cầu quản trị.

Sơ đồ quan hệ khái niệm:

~~~mermaid
flowchart TD
    D[Business domain: Commerce] --> S[System: Checkout]
    S --> O[Component: order-service]
    S --> C[Component: checkout-api]
    T[Team: Order Platform] -- owns --> O
    O -- provides --> A[API: Orders v1]
    O -- publishes --> E[Event: OrderCreated]
    O -- depends on --> I[Component: inventory-service]
    O -- owns --> DB[Resource: orders database]
    O -- operated by --> R[Runbook / SLO / on-call]
    O -- deployed as --> P[Production deployment]
~~~

Quan hệ có chiều và ý nghĩa rõ. Ví dụ team **owns** component khác với component **consumes** API, service **depends on** database khác với service **owns** dữ liệu. Đồ thị phụ thuộc chỉ có ích nếu hướng và loại quan hệ được định nghĩa thống nhất.

## 4. Metadata tối thiểu của một service

Một entry cần đủ thông tin cho những câu hỏi tác nghiệp hằng ngày nhưng không quá nhiều tới mức mọi nhóm bỏ qua. Có thể bắt đầu bằng schema sau:

| Trường | Ví dụ | Tại sao cần |
| --- | --- | --- |
| serviceId | order-service | Định danh ổn định, duy nhất |
| displayName | Order Service | Tên con người dễ nhận biết |
| description | Tạo và quản lý vòng đời đơn hàng | Giải thích vai trò nghiệp vụ |
| lifecycle | production | Biết thành phần còn đang được dùng không |
| ownerTeam | team-order-platform | Có người chịu trách nhiệm |
| technicalContact | Kênh chat/nhóm liên hệ | Hỏi đáp thay đổi thường ngày |
| onCall | Schedule hoặc escalation policy | Phân công khi có sự cố |
| backupOwner | Nhóm dự phòng | Tránh điểm phụ thuộc một người |
| businessDomain | commerce | Khám phá theo năng lực |
| system | checkout | Nhìn quan hệ với toàn hệ thống |
| repository | URL repo nguồn | Tìm code và lịch sử thay đổi |
| pipeline | URL CI/CD | Tìm build/deploy, artifact |
| documentation | URL overview/API/ADR | Onboarding và hiểu thiết kế |
| runbook | URL hướng dẫn tác nghiệp | Xử lý sự cố có thể thực hiện |
| dashboard | URL số liệu vận hành | Nhìn health và SLO |
| alerting | Route/policy cảnh báo | Xác định tín hiệu và người nhận |
| slo | Mục tiêu chất lượng có liên kết | Xác nhận tác động người dùng |
| criticality | Tier 1/2/3 theo policy | Ưu tiên sự cố và thay đổi |
| dataClassification | Internal/Confidential/... | Xác định yêu cầu dữ liệu |
| dependencies | API, topic, database | Phân tích blast radius |
| environments | prod/staging, region/cluster | Biết nơi triển khai |
| lastVerified | Thời điểm xác minh metadata | Phát hiện mục ghi quá cũ |

Không phải mọi trường cần nhập tay. Ví dụ deployment cluster, image digest và commit nên được thu thập từ CI/CD hoặc runtime inventory để giảm sai lệch. Những trường đòi hỏi phán đoán trách nhiệm, như owner và business criticality, cần nhóm có thẩm quyền xác nhận.

### 4.1. Định danh và quy tắc đặt tên

Tên hiển thị có thể đổi nhưng **serviceId** nên ổn định qua đa số lần đổi tên. Nếu dùng ID theo tên hiển thị, mỗi lần đổi tên có thể làm gãy dashboard, alert, link và quan hệ phụ thuộc. Nên có:
- ID canonical ít thay đổi.
- Alias hoặc tên cũ khi cần chuyển tiếp.
- Quy tắc namespace cho service ID trùng trong tổ chức lớn.
- Định danh entity type và environment rõ.
- Không dùng URL repo làm khóa chính tuyệt đối vì repository có thể chuyển.
- Chặn trùng ID và thiết kế trạng thái retired thay vì tái sử dụng ID bừa bãi.

Khi có hai service cùng tên trong hai business domain, cần cách phân biệt không dựa trên việc người dùng nhớ tên team hiện tại.

## 5. Ownership là trách nhiệm, không chỉ là một tên trên trang

Mỗi service production cần ít nhất một **accountable owner** được chỉ định rõ ở cấp team. Người viết nhiều commit nhất không tự trở thành owner. Tác giả repo, người duyệt PR, người trực on-call, người quyết định product priority và người sở hữu dữ liệu có thể khác nhau.

Nên định nghĩa:
1. **Service owner team:** chịu trách nhiệm chất lượng, kiến trúc, lifecycle, SLO và quyền quyết định kỹ thuật của service.
2. **Technical lead/contact:** đầu mối tư vấn thiết kế, thay đổi interface và migration.
3. **On-call responder:** người nhận cảnh báo theo lịch tại thời điểm xảy ra sự cố.
4. **Escalation owner:** người hoặc nhóm tiếp nhận khi responder đầu tiên không xử lý được.
5. **Business owner:** xác nhận ưu tiên và tác động nghiệp vụ nếu cần.
6. **Data owner/steward:** phụ trách phân loại dữ liệu, retention, các quy tắc quản trị dữ liệu liên quan.
7. **Platform dependency owner:** nhóm sở hữu nền tảng chung như ingress, broker, database service.

Một team owner có thể gắn với nhiều thành viên thay đổi theo tổ chức. **Không dùng duy nhất tên cá nhân làm ownership lâu dài** vì người đó có thể nghỉ, chuyển nhóm hoặc không trực ca. Có thể liên kết một schedule on-call riêng và fallback route.

### 5.1. Owner không đồng nghĩa người trực

Owner thường chịu trách nhiệm cải tiến dài hạn, quyết định roadmap và tiếp nhận trách nhiệm cuối cùng; on-call là người phản ứng tại thời điểm incident. Tách hai trường giúp catalog phản ánh đúng:
- “Muốn thay đổi event schema của order-service, hỏi team nào?”
- “Lúc 02:00 checkout lỗi, trang báo ai?”
- “Ai phê duyệt decommission service?”

Một team owner thiếu đường escalation vẫn chưa đáp ứng nhu cầu trực vận hành. Một lịch trực đang hoạt động nhưng không có owner accountable cũng gây khó cho việc nâng cấp lâu dài.

### 5.2. Ví dụ RACI cho service production

| Hoạt động | Service owner | On-call | Platform/SRE | Security | Business owner |
| --- | --- | --- | --- | --- | --- |
| Thiết kế API, contract | A/R | C | C | C | I |
| SLO và capacity | A | R/C | R/C | I | C |
| Triển khai thường lệ | A/R | I | C | C | I |
| Incident triage | A | R | R/C | C khi liên quan | I |
| Backup/restore drill | A | R/C | R | C | I |
| Phân loại dữ liệu | R/C | I | C | A/R tùy tổ chức | C |
| Decommission | A/R | I | C | C | C |

R = Responsible, A = Accountable, C = Consulted, I = Informed. Bảng chỉ là ví dụ. Tổ chức phải xác định **một vai trò accountable rõ ràng** cho từng quyết định quan trọng và điều chỉnh theo mô hình vận hành thực tế, không sao chép bảng như chính sách mặc định.

## 6. Mẫu entry Markdown/YAML có thể quản lý trong Git

Ví dụ custom YAML minh họa, không phải schema bắt buộc của công cụ cụ thể:

~~~yaml
apiVersion: platform.example/v1
kind: Service
metadata:
  id: order-service
  name: Order Service
  description: Quản lý tạo và trạng thái đơn hàng
  tags: [java, spring-boot, commerce]
spec:
  domain: commerce
  system: checkout
  lifecycle: production
  tier: tier-1
  ownerTeam: team-order-platform
  backupTeam: team-checkout-platform
  contacts:
    chat: https://chat.example/teams/order-platform
    onCall: https://oncall.example/schedules/orders
    escalation: https://oncall.example/policies/orders
  source:
    repository: https://git.example/commerce/order-service
    defaultBranch: main
    pipeline: https://ci.example/pipelines/order-service
  interfaces:
    - kind: http
      ref: orders-api-v1
    - kind: event
      ref: order-created-v2
  dependencies:
    - component: inventory-service
      type: synchronous
      criticality: required
    - resource: orders-db
      type: datastore
      criticality: required
  operations:
    runbook: https://docs.example/runbooks/order-service
    dashboard: https://metrics.example/d/order-service
    slo: https://slo.example/services/order-service
  security:
    dataClassification: confidential
    securityContact: team-appsec
  deployment:
    production:
      region: region-a
      cluster: commerce-prod
    staging:
      region: region-a
      cluster: commerce-staging
~~~

Mọi URL, tên team và hệ thống trong ví dụ đều giả định. Nội dung catalog **không nên chứa secret, token, private key, mật khẩu, dữ liệu cá nhân hoặc endpoint quản trị nhạy cảm**. Có thể lưu tham chiếu tới hệ thống secret nhưng không đưa giá trị secret vào catalog.

Một implementation có thể dùng Backstage Software Catalog, cổng developer nội bộ, service registry do tổ chức xây hoặc CMDB tích hợp. Từng nền tảng có schema và cách ingest riêng; cần map custom example vào định dạng của công cụ thực tế, không copy y nguyên rồi coi là file cấu hình có thể import.

## 7. Thiết kế nguồn sự thật cho từng loại metadata

Catalog đáng tin khi từng trường có **nguồn canonical, quyền sửa và quy tắc đồng bộ**.

| Thuộc tính | Nguồn được đề xuất | Người kiểm soát |
| --- | --- | --- |
| Service ID, mô tả, owner, lifecycle | Metadata trong repository hoặc control plane | Service owner |
| Nhóm và membership | Directory tổ chức/identity | Team administration/HR identity |
| Repository, pipeline | SCM và CI/CD platform | DevEx/platform |
| Build digest, commit | CI/CD provenance/release record | Automation |
| Deployment hiện hành | GitOps/Kubernetes/cloud inventory | CD/platform |
| API contract | OpenAPI/AsyncAPI/protobuf/schema registry | API producer và consumer |
| Dashboard, alert routing | Observability/incident tools | Service owner/SRE |
| SLO và error budget | SLO registry hoặc policy repository | Service owner + SRE |
| Data classification | Data governance/security inventory | Data owner/security |
| Cloud resource, database | IaC, cloud inventory | Platform/resource owner |
| On-call schedule | Incident-management platform | On-call team |
| Incident history | Ticketing/incident platform | Incident commander/system |
| Deprecation status | Lifecycle workflow/architecture record | Service owner |

Ví dụ catalog có thể **tham chiếu** URL dashboard từ metadata repository, còn tình trạng dashboard có truy cập được hay không được kiểm tra định kỳ. Đừng yêu cầu developer cập nhật thủ công image digest sau mỗi deploy nếu pipeline đã biết thông tin này.

### 7.1. Source of truth theo trường, không nhất thiết một database duy nhất

Một nguồn dữ liệu trung tâm có thể tổng hợp từ Git, CI/CD và hạ tầng nhưng không tự trở thành authoritative cho mọi thuộc tính. Nếu schedule on-call thay đổi trong công cụ trực, catalog phải đồng bộ hoặc link trực tiếp. Trường được nhập thủ công và trường tự phát hiện cần được phân biệt để tránh người dùng sửa vào một giá trị sẽ bị connector ghi đè.

### 7.2. Provenance của metadata

Metadata được lưu nên có:
- Được khai báo từ nguồn nào.
- Ai/công cụ nào cập nhật.
- Thời điểm và revision cập nhật.
- Trường nào đã được service owner xác nhận.
- Status đồng bộ và lỗi gần nhất.
- Khi nào cần xác minh lại.

Nhờ đó, khi catalog nói production có 6 replica nhưng Kubernetes có 10, người vận hành biết đây là giá trị stale hay discrepancy cần kiểm tra, thay vì tin vào một con số không rõ nguồn.

## 8. Service catalog và developer portal

Một developer portal hữu ích có thể trình bày từ catalog:
- Tìm service theo tên, domain, tag, capability, owner.
- Mở repository, pipeline, API docs và dependency graph.
- Xem deployment theo môi trường và release revision.
- Truy cập dashboard, SLO, alerts, on-call, runbook.
- Đăng ký service mới bằng template/Golden Path.
- Hiển thị scorecard mức độ đáp ứng tiêu chuẩn nền tảng.
- Gửi đề xuất đổi owner hoặc lifecycle.
- Theo dõi deprecation và migration guide.

Developer portal là **giao diện khám phá và thao tác**, còn catalog là **metadata và quan hệ**. Chúng có thể nằm chung một sản phẩm, nhưng cần thiết kế rõ nguồn dữ liệu, quyền thay đổi và cập nhật.

Không cần triển khai portal phức tạp ngay khi chỉ có 5 service. Có thể bắt đầu bằng YAML/README nhất quán trong Git và một trang index tự động; sau đó phát triển portal khi nhu cầu tìm kiếm, governance và tự phục vụ tăng.

## 9. Phân lớp metadata: tĩnh, bán động và động

### 9.1. Metadata tương đối tĩnh

Service ID, mô tả, domain, data owner, criticality hoặc loại dữ liệu thường thay đổi theo tuần/tháng. Đặt trong Git với PR review cho phép version hóa và audit.

### 9.2. Metadata bán động

Repository link, API version, pipeline, on-call schedule, runbook, lifecycle, SLO thường thay đổi theo lần tổ chức thay đổi team, release lớn hoặc quy trình vận hành. Có thể giữ tham chiếu trong Git và lấy trạng thái sống từ công cụ gốc.

### 9.3. Metadata động

Current deployment digest, replica count, health, incident state, alert firing hoặc latest release có thể thay đổi theo phút/giây. Thông tin này nên được **liên kết hoặc đồng bộ tự động** từ nguồn vận hành, có timestamp và độ trễ đồng bộ minh bạch.

Một catalog được cập nhật mỗi giờ không nên tự nhận là nguồn dữ liệu real-time cho pod health. Khi cần định tuyến request, hãy dùng runtime discovery; khi cần quyết định ai sở hữu và đi đâu xử lý, dùng catalog.

## 10. Quy tắc đặt service ID, ownership và tag

Chọn convention dễ tìm:
- Service ID dùng lowercase, dấu gạch nối và tên rõ nghĩa: order-service, inventory-service.
- Domain và system là taxonomy có owner được quản lý.
- Tag biểu diễn công nghệ hoặc đặc tính có thể tìm kiếm: java, spring-boot, kafka, postgresql.
- Criticality dùng enum có định nghĩa, tránh mỗi team tự gọi “tier-0” theo cảm tính.
- Lifecycle dùng tập trạng thái hữu hạn.
- Owner là **team ID canonical**, không phải tên tùy ý như “team anh Nam”.
- On-call dùng schedule/policy ID hoặc link có người duy trì.
- SLO và runbook có URL ổn định, tránh link tới tài liệu cá nhân.

Tránh tag rời rạc không có quy ước: java17, Java-17, jdk17, openjdk-17 là bốn nhãn cùng ý nếu không được chuẩn hóa. Có thể dùng controlled vocabulary và danh sách alias để cải thiện search.

### 10.1. Trường optional và trường bắt buộc

Không phải service nào cũng có OpenAPI, database hoặc SLO riêng. Nhưng production service cần tối thiểu:
- Owner team và đường escalation hợp lệ.
- Repository hoặc nguồn triển khai có thể truy vết.
- Mục đích nghiệp vụ.
- Lifecycle và environment đang hoạt động.
- Tài liệu vận hành đủ để xử lý sự cố.
- Mức độ criticality/rủi ro theo policy tổ chức.
- Phạm vi dữ liệu và dependency quan trọng, nếu có.

Các trường không áp dụng nên được biểu diễn như **not applicable có lý do**, không để trống mơ hồ nếu đó là trường phục vụ policy.

## 11. Vòng đời service và chuyển trạng thái

Một mô hình cơ bản:

~~~mermaid
flowchart LR
    A[Proposed] --> B[Experimental]
    B --> C[Production]
    C --> D[Deprecated]
    D --> E[Retired]
    B --> E
    C --> E
~~~

**Proposed:** đang thiết kế, chưa có production workload. **Experimental:** thử nghiệm/preview, chưa nhận cam kết production. **Production:** hoạt động phục vụ người dùng hoặc workload thật. **Deprecated:** còn hoạt động nhưng khuyến nghị ngừng dùng, có kế hoạch thay thế. **Retired:** không còn xử lý traffic, resource đã dọn hoặc được quản lý theo retention.

Vòng đời catalog không nhất thiết trùng chu kỳ semantic version. Một service production có thể phát hành 30 bản mà lifecycle không đổi. Một service deprecated vẫn cần owner/on-call vì chưa loại bỏ hoàn toàn.

### 11.1. Checklist chuyển vào production

Trước khi đổi status thành production, cần xác nhận theo policy:
1. Owner team và backup contact.
2. Repository, build pipeline, artifact registry và cơ chế deploy.
3. SLO/SLI hoặc xác nhận trường hợp được miễn trừ.
4. Dashboard, log/trace, alert route và on-call.
5. Runbook xử lý sự cố và rollback.
6. API/event contract và ownership của dữ liệu.
7. Data classification, secret/IAM và dependency inventory.
8. Backup/restore hoặc chiến lược tái tạo state nếu có dữ liệu bền.
9. Kế hoạch capacity và change process.
10. Entry catalog được nhập, liên kết đúng deployment.

Không biến kiểm tra thành chướng ngại quan liêu không có căn cứ. Có thể áp dụng các mức yêu cầu khác nhau cho một batch worker nội bộ và payment gateway có dữ liệu nhạy cảm.

### 11.2. Decommission không phải xóa entry ngay

Khi service retired, cần:
- Xác nhận tất cả consumer đã rời API/topic.
- Dừng traffic và background jobs.
- Thu hồi credential, token, secret, IAM.
- Xử lý database, backup, log theo retention.
- Dọn dashboards, alerts, DNS, gateway route, resource.
- Ghi nơi thay thế, thời điểm ngừng và owner cuối.
- Giữ bản ghi catalog archived đủ để hỗ trợ audit và tra cứu.

Xóa entry trước khi biết dependency/owner làm tổ chức mất lịch sử liên quan sự cố và chi phí.

## 12. Đồ thị phụ thuộc giúp phân tích sự cố

Một catalog chỉ chứa tên service và owner mới đáp ứng bước đầu. **Dependency graph** giúp biết:
- Tác động của việc sửa một API/event.
- Những hệ thống phải tham gia DR drill.
- Đường escalation khi một phụ thuộc lỗi.
- Những consumer cần kế hoạch migration khi deprecate.
- Shared resources nào có thể tạo blast radius lớn.
- Vì sao một team cần phối hợp với team khác để nâng cấp.

Ví dụ order-service gọi inventory-service và payment-service, đồng thời publish OrderCreated cho notification-service. Catalog cần tách:
- Synchronous dependency (gRPC/HTTP).
- Asynchronous producer → topic → consumer.
- Database hoặc cache được một service sở hữu.
- Shared platform dependency (gateway, IAM, broker).
- Optional vs required dependency theo chức năng nghiệp vụ.

Quan hệ phụ thuộc được khai báo không tự động chính xác. Có thể đối chiếu với distributed traces, service mesh traffic, API gateway routes và topic consumer groups; tuy nhiên telemetry cũng có blind spots nếu traffic ít, tracing sampled hoặc kết nối dùng cách khác. Cần kết hợp **khai báo của chủ service** và **bằng chứng quan sát**.

### 12.1. Đừng nhầm deployment graph với ownership graph

Hai service cùng chạy trong một cluster không có nghĩa cùng owner. Một team sở hữu ba service nhưng chúng có thể chạy ở ba vùng. Dependency graph và ownership graph phải là các quan hệ khác nhau để hỗ trợ hai kiểu truy vấn khác nhau.

## 13. API, event contract và tài liệu tích hợp

Một service entry nên liên kết hợp đồng giao tiếp, không nhúng một bản copy cũ vào trường mô tả.

Với HTTP:
- OpenAPI/spec link và phiên bản.
- Endpoint base theo môi trường khi cần, nhưng không chứa credential.
- Authentication scheme, retry/idempotency semantics, error model.
- Consumer quan trọng và chính sách deprecation.
- Các giới hạn rate/quota và ownership của API.

Với gRPC:
- Protobuf/schema repository, compatibility policy.
- Deadlines, auth, error mapping và consumer dependencies.

Với event:
- AsyncAPI/schema registry hoặc event definition.
- Producer owner, topic, consumer, event version.
- Retention, ordering scope, duplicate delivery/idempotency.
- Quy trình thêm/sửa/xóa trường.

Catalog entry có thể liên kết đến nơi authoritative của spec, đồng thời lưu quan hệ API/event để query. Ví dụ khi schema OrderCreated thay đổi, chủ service có thể biết subscriber nào cần được thông báo.

## 14. Ownership của dữ liệu và các tài nguyên phụ thuộc

Microservices thường đặt mục tiêu mỗi service sở hữu state nghiệp vụ của nó. Catalog cần biểu diễn quan hệ này, chẳng hạn:
- order-service owns orders-db.
- inventory-service owns inventory-db.
- notification-service consumes order-events.
- order-service depends on product-pricing API.

Không nên ghi “DB team là owner của orders-db” để thay thế ownership nghiệp vụ của order-service. Platform DBA có thể quản lý engine/backup, còn service owner vẫn chịu trách nhiệm schema, query semantics và dữ liệu của domain. Ranh giới trách nhiệm phải rõ.

Với shared database hoặc legacy monolith extraction, hãy ghi nhận tình trạng nợ kiến trúc: nhiều service cùng truy cập schema hoặc cùng ghi bảng, từ đó xác định kế hoạch tách hoặc hợp đồng cho phép. Không nên che giấu coupling để làm catalog trông “chuẩn microservices”.

### 14.1. Tài nguyên và secrets

Resource metadata có thể chỉ đến database cluster, storage bucket, Kafka topic, Redis namespace hoặc KMS key reference. Không lưu password/secret value. Link tới secret manager cũng cần được bảo vệ theo quyền xem metadata nếu tên secret tiết lộ cấu trúc nội bộ.

Tài nguyên chung có thể do platform sở hữu, nhưng quan hệ “service sử dụng resource” vẫn cần ghi để phân tích khi resource gặp sự cố.

## 15. Thông tin vận hành tối thiểu cho production

Một production service nên có một **operational overview** ngắn, cập nhật:

| Nhóm | Nội dung |
| --- | --- |
| Mục đích | Luồng nghiệp vụ, người dùng và output quan trọng |
| Độ quan trọng | Criticality, tier, tác động nếu không khả dụng |
| SLI/SLO | Success ratio, latency, freshness, business completion |
| Deployment | Cluster, region, namespace, digest, config revision |
| Capacity | Traffic bình thường/cao điểm, bottleneck, autoscaling, quotas |
| Health | Readiness, liveness, dependency criticality |
| Observability | Dashboard, logs, traces, alerts |
| On-call | Schedule, escalation, backup team |
| Runbooks | Triage, rollback, cache reset, failover, recovery |
| Data | Database, backup, retention, classification |
| Dependencies | Downstream/upstream và hành vi degraded |
| Security | Auth, IAM, secret owner, data residency |
| Change | Pipeline, release gate, change window hoặc policy |
| Incident history | Link incident gần đây và postmortem hành động |

Một trang chứa 20 link hỏng không tốt hơn tài liệu ngắn nhưng đúng. Catalog cần kiểm tra chất lượng liên kết và thời điểm cập nhật.

### 15.1. Tier dịch vụ và yêu cầu vận hành

Tier có thể dựa trên tác động:
- Tier 1: mất service ảnh hưởng giao dịch cốt lõi, doanh thu, nghĩa vụ nghiêm trọng.
- Tier 2: ảnh hưởng trải nghiệm hoặc công việc đáng kể nhưng có degraded mode.
- Tier 3: batch, thử nghiệm, chức năng nội bộ ít rủi ro.

Đây là ví dụ, tổ chức phải định nghĩa tier chính thức và ràng buộc với SLO, on-call, backup, DR, yêu cầu review và security. Tier không nên được đặt theo mức độ “team thấy service của mình quan trọng”.

## 16. Runbook và playbook: tài liệu gắn với hành động

**Runbook** chứa thao tác cụ thể để xác minh và xử lý tình huống vận hành đã biết. **Playbook** có thể bao gồm quy trình phối hợp cấp cao hơn cho tình huống rộng như region outage hoặc dữ liệu corrupt.

Một runbook hữu ích:
1. Triệu chứng và alert liên quan.
2. Phạm vi ảnh hưởng và cách xác nhận bằng metric/business SLI.
3. Link dashboard, logs/traces, query đã được kiểm chứng.
4. Owner/on-call và cách escalation.
5. Các bước an toàn để giảm tác động.
6. Quyền cần thiết, điều kiện dừng, bước xác nhận trước thao tác nguy hiểm.
7. Rollback/roll forward và caveat dữ liệu.
8. Cách kiểm tra phục hồi thành công.
9. Cách lưu evidence và liên kết incident.
10. Thời điểm cập nhật và chủ sở hữu runbook.

### 16.1. Ví dụ: order-service tăng lỗi 5xx

~~~text
Alert: order-service success ratio giảm dưới ngưỡng SLO
Triage:
  1. Kiểm tra dashboard Order API theo route/region/version.
  2. So sánh image digest trước/sau release.
  3. Kiểm tra DB connection pool, query latency, payment RPC.
  4. Xem queue lag của OrderCreated và timeout retry.
  5. Nếu chỉ một region bị lỗi, kiểm tra infrastructure incidents.
Mitigation:
  - Dừng canary hoặc tắt feature flag nếu lỗi gắn với release.
  - Cân nhắc rollback theo chính sách tương thích schema.
  - Giới hạn retry/throttle nếu dependency bão hòa.
Escalation:
  - On-call: order-platform
  - Database/platform: theo policy nếu vấn đề ở shared infra
Success:
  - Business order creation và error budget burn trở về ngưỡng.
~~~

Đây là ví dụ khái niệm, không phải lệnh tự động để chạy production. Một runbook không nên chứa lệnh xóa dữ liệu nguy hiểm có thể copy/paste mà thiếu điều kiện, quyền và xác nhận.

## 17. SLO, alert và trách nhiệm phản ứng

Catalog nên chỉ rõ SLO liên quan năng lực nghiệp vụ, không chỉ hạ tầng:
- API success rate và error budget.
- p95/p99 latency hoặc tỷ lệ request dưới ngưỡng.
- Message processing completion deadline.
- Data freshness hoặc lag.
- Tỷ lệ checkout/order thành công.
- Availability theo luồng critical dependency.

Khi alert bắn:
1. Alert có service ID canonical và link catalog.
2. Catalog trỏ tới schedule on-call đang còn hiệu lực.
3. Người trực mở dashboard, runbook, deployment history.
4. Dependency graph hỗ trợ xác định upstream/downstream bị ảnh hưởng.
5. Incident được gắn service ID và các resource liên quan.
6. Sau incident, owner cập nhật runbook/metadata nếu phát hiện thông tin sai.

Từ đây có thể thấy service catalog không chỉ phục vụ navigation; nó là lớp **incident context** giúp rút ngắn thời gian tìm người và hiểu hệ thống. Tuy nhiên catalog hỏng không được ngăn việc nhận cảnh báo: alert route có thể duy trì độc lập trong công cụ on-call và catalog liên kết tới đó.

## 18. Tích hợp với CI/CD và GitOps

Một cách giảm stale là khai báo metadata cạnh source code và cập nhật động tự động.

~~~mermaid
flowchart TD
    A[Service repository] --> B[Metadata validation CI]
    B --> C[Build / publish artifact]
    C --> D[Release & deployment records]
    A --> E[Catalog ingest]
    D --> E
    F[Team directory / on-call] --> E
    G[GitOps / cloud runtime] --> E
    H[API & event schema registry] --> E
    E --> I[Developer portal / search / scorecards]
    E --> J[Incident context / ownership graph]
~~~

Trong CI:
- Validate file metadata theo schema, required fields và enum.
- Check owner team ID tồn tại trong directory.
- Check repository/pipeline link và runbook còn truy cập được nếu có khả năng.
- Check các relationship target hợp lệ hoặc được khai báo.
- Check production service có on-call/escalation, dashboard, SLO hoặc exemption có hạn.
- Check deprecated service có migration/deprecation plan.
- Không yêu cầu nhập tay runtime IP, replica hoặc digest nếu pipeline phát hiện được.

Trong CD/GitOps:
- Sau release, gửi event/update về serviceId, environment, cluster, commit, artifact digest, deployment status.
- Không cho deployment record của một serviceId bị ghi nhầm sang service khác.
- Giữ provenance của timestamp và nguồn cập nhật.
- Thông báo metadata drift hoặc unknown running component, thay vì âm thầm xóa entry.

### 18.1. Catalog không nên là điểm lỗi duy nhất của pipeline

Nếu catalog backend tạm unavailable, cần quy tắc rõ: những policy nào được kiểm tra cục bộ tại CI (schema/owner file), những policy nào phụ thuộc dịch vụ tập trung, và có cache/snapshot policy đáng tin để duy trì hoạt động hay không. Không để deployment production bypass policy âm thầm chỉ vì catalog không trả lời.

## 19. Contract cho metadata-as-code

Có thể lưu một tệp YAML trong repo:
- review cùng code khi tạo service hoặc đổi ownership;
- dùng schema validation và lint;
- yêu cầu team owner xác nhận khi đổi lifecycle/criticality;
- tự tạo entry trong catalog từ SCM;
- giữ lịch sử thay đổi phục vụ audit.

Ví dụ các điều kiện logic cho policy engine:

~~~text
IF lifecycle == production THEN
    ownerTeam MUST exist
    onCall MUST exist or exemption MUST be approved
    runbook MUST exist
    dashboard MUST exist
    criticality MUST be classified
    sourceRepository MUST be traceable
END

IF lifecycle == deprecated THEN
    deprecationNotice MUST exist
    replacement OR retirementPlan MUST be documented
END

IF dataClassification == restricted THEN
    securityOwner MUST exist
    residencyPolicy MUST be defined
END
~~~

Đây là pseudocode chính sách. Một tổ chức có thể áp dụng theo business risk và từng loại entity. Cần lưu exception có owner, lý do, ngày hết hạn và audit, tránh tạo đường tắt vĩnh viễn.

## 20. Tạo service mới bằng Golden Path / Software Template

Một quy trình platform self-service có thể:
1. Developer chọn loại service (Java API, Kafka worker, scheduled job).
2. Nhập business domain, team owner, criticality và môi trường.
3. Template tạo repository, build scripts, tests, Dockerfile, CI/CD manifest.
4. Template thêm metadata catalog và link tài liệu mẫu.
5. CI validate metadata, secret policy và license/dependency rules.
6. Hệ thống provision namespace/IAM/database theo quyền.
7. Tạo dashboard, alert, runbook khung và on-call route.
8. Đăng ký service vào catalog.
9. Trước production, hoàn thiện SLO, dependency và operational readiness.

**Golden Path** là một đường làm mặc định giúp nhóm đi đúng chuẩn với ít thao tác thủ công, không phải cơ chế cấm mọi ngoại lệ. Service đặc thù có thể dùng template khác nếu đáp ứng policy tương ứng.

### 20.1. Lợi ích và giới hạn

Điểm mạnh: giảm thời gian tạo service và quên bước ownership; chuẩn hóa resource naming, security baseline và observability. Nhưng template chỉ bảo đảm **bắt đầu đúng**. Sau sáu tháng, owner có thể đổi, runbook có thể hỏng link, dependency có thể thêm; vì vậy cần quy trình cập nhật liên tục.

## 21. Catalog trong môi trường Java/Spring Boot

Ví dụ Java service có repository, Spring Boot Actuator và OpenTelemetry metrics/traces. Một catalog entry có thể dẫn tới:
- Repository chứa Java 21, Gradle/Maven, API spec.
- CI pipeline publish container image.
- Helm/GitOps definition của deployment.
- Actuator health/readiness.
- Dashboard Micrometer/Prometheus và trace backend.
- Runbook, escalation, on-call.
- Database resource và Kafka event contracts.

Spring Boot cung cấp các endpoint vận hành tùy dependency/config và policy, nhưng **không tự sinh một danh mục ownership đầy đủ** chỉ từ Actuator. Runtime health, thông tin build và ownership metadata có thể được liên kết.

### 21.1. Ví dụ Actuator minh họa

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  info:
    env:
      enabled: false
~~~

Config minh họa, phụ thuộc Spring Boot version, Actuator và Prometheus registry phù hợp. Không expose Actuator endpoint chứa thông tin hệ thống ra public internet. Catalog có thể biết **đường dẫn dashboard và runbook**, còn chi tiết health live đến từ hệ thống metrics/probe được bảo vệ.

### 21.2. Build information

CI có thể gắn vào artifact:
- serviceId/order-service;
- git commit SHA;
- build run ID;
- image digest;
- build time;
- config revision.

Các thông tin này nên được đưa vào release record tự động và liên kết catalog. Không nên hiển thị raw environment variables hoặc secret trên endpoint info chỉ để phục vụ developer portal.

### 21.3. Kubernetes labels và annotations

Một manifest deploy có thể có nhãn chuẩn hóa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: commerce-prod
  labels:
    app.kubernetes.io/name: order-service
    app.kubernetes.io/part-of: checkout
    app.kubernetes.io/managed-by: gitops
    platform.example/service-id: order-service
    platform.example/owner-team: team-order-platform
spec:
  replicas: 3
  selector:
    matchLabels:
      app.kubernetes.io/name: order-service
  template:
    metadata:
      labels:
        app.kubernetes.io/name: order-service
        platform.example/service-id: order-service
    spec:
      containers:
        - name: order
          image: registry.example/order-service@sha256:<approved-digest>
          ports:
            - containerPort: 8080
~~~

Đây là ví dụ tối giản, chưa đầy đủ để triển khai production: thiếu resource constraints, probes, security context, service account và policy. Nhãn custom namespace là quy ước giả định. Một collector có thể dùng service ID để đối chiếu running deployments với catalog, nhưng không được tin label do workload không được phép tự đặt để giả mạo ownership hoặc bypass security.

## 22. OpenTelemetry và định danh quan sát

Trong hệ thống trace/metrics, nên giữ định danh ổn định như service.name và deployment.environment. Nếu metadata catalog dùng order-service nhưng telemetry dùng orders-api, search/dependency graph dễ mất liên kết. Có thể quản lý mapping và aliases trong catalog.

Một nhóm nhãn trace ví dụ:
- service.name: order-service
- service.version: 1.8.3
- deployment.environment.name: production (tên chính xác phụ thuộc semantic convention/version)
- k8s.namespace.name: commerce-prod
- k8s.cluster.name: commerce-main
- cloud.region: region-a

Tránh gắn email của người trực, token, userId, orderId hoặc dữ liệu khách hàng vào **metric labels** có cardinality cao. Có thể liên kết serviceId và environment tới runbook/catalog bằng URL trong dashboard thay vì copy thông tin cá nhân vào mọi time series.

Catalog có thể lấy dependency graph từ trace, nhưng trace sampling không đảm bảo quan sát hết những call hiếm. Các mối quan hệ được xác nhận từ owner/spec vẫn cần được giữ.

## 23. Security và quyền truy cập catalog

Catalog thường có nhiều dữ liệu nội bộ: repository, topology, dependency, contact, network locations, data classifications, incidents và tài liệu vận hành. Không nên mặc định công khai toàn bộ.

### 23.1. Phân quyền đọc

- Developer nội bộ có thể tìm owner, API contract và runbook phù hợp vai trò.
- SRE/incident responders truy cập rộng hơn tới operational links.
- Security có thể xem data classification, dependency và policy evidence.
- Khách hàng hoặc đối tác chỉ nhìn metadata được công bố có chủ đích.
- Thông tin network/private architecture hoặc runbook nhạy cảm có thể yêu cầu quyền riêng.

Không cần giữ secret trong catalog. Nếu có thông tin có thể giúp tấn công hạ tầng, cần phân loại và hạn chế quyền đọc phù hợp.

### 23.2. Phân quyền sửa

Metadata-as-code thường có:
- Service owner sửa thông tin dịch vụ của mình qua PR.
- Platform quản lý schema, taxonomy và policy.
- Security/data governance xác nhận các trường phân loại nhạy cảm.
- Directory/on-call system là nguồn tự động cho membership/schedule.
- Automation chỉ ghi những trường được phân công, không ghi đè owner do PR đã review.

Audit ai đổi owner, SLO, criticality, escalation route hoặc lifecycle, vì các thay đổi này ảnh hưởng quy trình xử lý sự cố và trách nhiệm pháp lý.

### 23.3. Chống giả mạo ownership

Nếu một người có thể sửa YAML để tự xóa owner hoặc chuyển owner sang team không biết gì, catalog sẽ mất ý nghĩa. Có thể yêu cầu approval từ chủ cũ/chủ mới hoặc platform owner cho việc transfer, cùng xác nhận nhóm đích tồn tại và đã nhận trách nhiệm. Không sử dụng một chuỗi owner do người dùng tự gõ làm bằng chứng đồng ý của team được nêu.

## 24. Tìm kiếm, taxonomy và trải nghiệm người dùng

Một service có thể được tìm theo:
- Tên, alias và mô tả.
- Business capability hoặc domain.
- Team owner và phụ trách sự cố.
- API được cung cấp hoặc consumed.
- Technology stack.
- Tier/criticality, lifecycle.
- Dữ liệu hoặc resource mà nó sở hữu.
- Cluster/region đang triển khai.

Để tránh catalog trở thành danh sách khó dùng:
- Định nghĩa controlled vocabulary cho domain, system và tag.
- Ưu tiên owner, runbook, dashboard trên trang service chính.
- Phân biệt service active, deprecated và retired khi tìm kiếm.
- Cho phép deep link tới dependency graph và deployment history.
- Hiển thị timestamp/provenance cho thông tin động.
- Phản hồi rõ khi một mục thiếu nguồn hoặc stale.
- Tránh giao diện đẹp nhưng mọi link đều dẫn tới trang không truy cập được.

Ví dụ một developer tìm “thanh toán” có thể thấy payment-service, payment-api, PaymentAuthorized event và team Payments. Kết quả cần cho biết quan hệ chứ không trả bốn thực thể đồng hạng gây nhầm lẫn.

## 25. Scorecard: đo mức độ sẵn sàng vận hành

**Service scorecard** là cách hiển thị bằng chứng tuân thủ tiêu chuẩn platform, ví dụ một service production có:
- Owner team đã được xác thực.
- Runbook và on-call route hoạt động.
- SLI/SLO và dashboard.
- CI/CD với artifact traceability.
- Dependency và data classification.
- Security scan, secret/IAM baseline.
- Backup/DR exercise theo tier.
- Incident follow-up quá hạn hay không.

Một scorecard có ích khi chỉ ra **việc cần cải thiện và owner có thể làm**, không dùng điểm số làm danh hiệu trừu tượng.

### 25.1. Tránh gamification sai hướng

Nếu điểm cao chỉ nhờ điền đủ trường, nhóm có thể đặt runbook placeholder, SLO vô nghĩa hoặc owner giả để vượt gate. Scorecard nên kết hợp:
- Completeness: trường tồn tại.
- Validity: link truy cập được, enum và entity hợp lệ.
- Freshness: xác nhận gần đây hoặc đồng bộ trong thời hạn.
- Coverage: quan hệ quan trọng đầy đủ.
- Operability: runbook/alert/DR drill đã được kiểm chứng.
- Ownership confidence: owner thực sự nhận trách nhiệm.

Không tự động kết luận “chất lượng service tốt” chỉ vì metadata đạt điểm cao. Catalog đo khả năng khám phá/quản trị/vận hành; chất lượng runtime cần SLO, incident data và thử nghiệm riêng.

## 26. Chất lượng dữ liệu và phát hiện drift

Catalog dễ mất giá trị khi service thay đổi nhưng entry không được cập nhật:
- Repo được đổi tên.
- Team bị giải thể/đổi quyền.
- Pipeline được chuyển sang hệ thống mới.
- Runbook bị xóa.
- Service đã ngừng hoạt động nhưng vẫn có status production.
- Service đang chạy production nhưng chưa được đăng ký.
- Một API mới đã được phát hành nhưng dependency graph thiếu consumer.
- On-call schedule không còn người nhận.

Thiết lập kiểm tra nhiều tầng:

| Kiểm tra | Tần suất gợi ý | Cách phát hiện |
| --- | --- | --- |
| YAML/schema hợp lệ | Mỗi PR | Schema validation trong CI |
| Service ID/owner tồn tại | Mỗi PR và định kỳ | So với team directory |
| Link repository/pipeline/runbook | Định kỳ | Link checker và API connector có quyền |
| Running service chưa có entry | Hằng ngày hoặc theo deploy | So sánh Kubernetes/cloud inventory |
| Owner/on-call quá hạn xác minh | Theo chu kỳ phù hợp | Owner attestation, schedule link |
| API/event dependency thay đổi | Khi release contract | Spec registry + telemetry |
| Lifecycle production nhưng không deploy | Theo chu kỳ | Đối chiếu CD records và runtime |
| Deployment digest/config sai nguồn | Sau deploy | Release record và runtime discovery |

### 26.1. Đừng tự xóa entry chỉ vì một thời gian không thấy traffic

Một scheduled worker chạy hàng tuần hoặc service DR standby có thể không phát traffic trong vài ngày. Nếu detector coi “không thấy trace” = “service đã chết”, sẽ xóa nhầm catalog entry. Cần xét loại workload, lifecycle, deployment inventory và xác nhận owner.

### 26.2. Metadata confidence

Có thể hiển thị trạng thái:
- **Verified:** có nguồn và xác nhận trong cửa sổ mong muốn.
- **Stale:** lâu không đồng bộ/không xác minh.
- **Conflict:** hai nguồn báo giá trị khác nhau.
- **Unknown:** chưa có đủ bằng chứng.
- **Not applicable:** loại trường không áp dụng, có lý do.

Đây là mô hình gợi ý; trạng thái phải gắn với **từng trường hoặc nhóm trường** khi cần. Một entry có owner được xác nhận nhưng deployment status stale không nên bị gắn nhãn duy nhất “tất cả đều chính xác”.

## 27. Ownership transfer khi tái tổ chức

Chuyển một service từ team A sang team B cần nhiều hơn sửa một chuỗi:
1. Xác định owner hiện tại và người/phòng ban nhận.
2. Lập danh sách trách nhiệm: roadmap, SLO, on-call, incidents, backlog, data, security.
3. Handover runbook, architecture decisions, known risks và release process.
4. Xác nhận quyền SCM, CI/CD, cloud, secret, dashboard và alert.
5. Team B nhận trách nhiệm và có lịch trực/escalation hoạt động.
6. Cập nhật catalog owner, contact và liên kết liên quan.
7. Ghi effective date và audit.
8. Kiểm tra sau handover rằng alert test có người nhận, pipeline deploy và rollback được.

Không thay owner ngay ở catalog rồi để on-call route còn trỏ team đã giải thể. Đây là ví dụ metadata cần phản ánh **một quy trình tổ chức đã hoàn tất**, không chỉ một PR.

## 28. Incident response từ trang service catalog

Một incident commander khi checkout error rate tăng có thể thực hiện:

~~~text
Alert: checkout success ratio < SLO
  ↓
Service ID: checkout-api
  ↓
Catalog: owner team, on-call, tier, runbook
  ↓
Dashboard và release timeline
  ↓
Dependency graph: order-service, payment-service, inventory-service
  ↓
Tra cứu owner của dependency lỗi
  ↓
Phối hợp triage, mitigation, recovery
  ↓
Gắn incident với affected services
  ↓
Postmortem và cập nhật metadata/runbook
~~~

Một trang service thực dụng có thể có phần “Incident quick access” chứa tối thiểu: on-call, status dashboard, runbook, recent deployments, dependencies và incident channel theo policy. Nếu link lỗi, nên có fallback contact từ team directory.

### 28.1. Những câu hỏi cần trả lời trong 2 phút đầu

- Ai có quyền trực cho service?
- Có đang rollout một bản mới không?
- SLO và traffic quan trọng nào bị ảnh hưởng?
- Phụ thuộc nào đang phát lỗi hoặc có shared platform incident?
- Có mitigation an toàn nào được runbook cho phép?
- Có dữ liệu bền vững cần bảo vệ trước rollback không?

Catalog không giải quyết trực tiếp sự cố; nó giảm chi phí **định vị con người, tài liệu và ngữ cảnh**.

## 29. Tích hợp hệ thống alerting và paging

Service owner và on-call schedule nên liên kết đến hệ thống incident management có quyền riêng. Alert route có thể dựa trên:
- Service ID.
- Environment/region.
- Severity.
- Business capability.
- Loại dependency hoặc resource.
- Escalation policy.

Ví dụ alert labels:
~~~yaml
labels:
  service_id: order-service
  environment: production
  severity: page
  team: team-order-platform
annotations:
  runbook_url: https://docs.example/runbooks/order-service
  catalog_url: https://portal.example/catalog/order-service
~~~

YAML chỉ minh họa ý tưởng, không phải một alerting config hoàn chỉnh. Không dùng routing nhãn team chưa được kiểm soát nếu có thể khiến cảnh báo nghiêm trọng rơi vào người nhận sai. Khi owner chuyển team, cập nhật cả policy alert route và kiểm tra thực tế.

## 30. Metadata ở cấp deployment và môi trường

Service logic thường có một owner nhưng được deploy nhiều nơi:
- test, staging, production;
- region A và region B;
- tenant-dedicated hoặc shared deployment;
- canary/baseline;
- blue/green environment.

Metadata theo deployment gồm:
- serviceId và environment.
- cluster/namespace/region.
- image digest, revision, config version.
- thời điểm deploy, release owner, rollout status.
- endpoint tham chiếu có kiểm soát.
- workload identity và resource references.
- live health reference.

Không nên gộp trạng thái tất cả deployment thành một dấu “healthy” duy nhất. Có thể staging lỗi nhưng production ổn; có thể region A khỏe và region B degraded. Người dùng catalog phải biết **đang xem trạng thái của phạm vi nào**.

### 30.1. Source code không đồng nghĩa deployment

Một repository có thể chứa nhiều deployable services (monorepo). Ngược lại một service logic có thể dùng nhiều repository (app, infra, API spec). Catalog nên cho phép mô hình nhiều-một rõ ràng, không mặc định “1 repository = 1 service”.

Một queue consumer và một HTTP server có thể chung codebase nhưng scale/deploy/on-call khác nhau; nếu vận hành độc lập, có lý do để biểu diễn thành hai component cùng system.

## 31. Khám phá service tự động và giới hạn

Hệ thống có thể tìm service từ:
- GitHub/GitLab repository topics và metadata file.
- Kubernetes Deployments/Services/Ingress.
- CI/CD pipeline definitions.
- OpenAPI/AsyncAPI spec registry.
- Cloud tags và infrastructure-as-code.
- Service mesh/traces.
- Package/artifact registry.

Nhưng **phát hiện kỹ thuật** không luôn biết service thuộc business domain nào hoặc ai chịu trách nhiệm. Một Deployment tên test-order-v2 không nhất thiết là service production riêng; một database có thể thuộc platform team về hạ tầng nhưng thuộc order team về dữ liệu.

Do đó quy trình thường dùng:
1. Discover candidate component.
2. Match với service ID đã đăng ký.
3. Nếu chưa match, tạo yêu cầu owner xác nhận thay vì tự gán bừa.
4. Enrich metadata từ nguồn đáng tin.
5. Detect conflict và đưa vào hàng chờ xử lý.
6. Publish entry đã đủ điều kiện.
7. Giữ provenance của trường tự động.

Không dùng runtime label tự khai để cấp quyền truy cập tài nguyên quan trọng; catalog là lớp thông tin, không phải nguồn xác thực IAM mặc định.

## 32. Governance vừa đủ, không làm giảm tự chủ của nhóm

Trong microservices, một platform team có thể đặt chuẩn chung:
- Service ID và owner bắt buộc.
- Data classification và criticality taxonomy.
- Golden Path tạo service.
- SLO/runbook/on-call cho production.
- Yêu cầu dependency contracts và deprecation plan.
- Metadata schema/lint và release traceability.
- Review/exception policy khi cần.

Nhưng service team vẫn sở hữu kiến trúc và lịch release trong phạm vi guardrail. Catalog không nên trở thành nơi xin phép thủ công cho mọi thay đổi nhỏ. Những policy có thể kiểm tra tự động nên triển khai trong CI và metadata schema.

### 32.1. Trách nhiệm hai chiều

**Platform team:** định nghĩa schema, hỗ trợ tooling, chuẩn hóa integrations, developer portal, policy engine, scorecards và phát hiện drift.

**Service team:** chịu trách nhiệm metadata nghiệp vụ/ownership chính xác, tài liệu vận hành, link, SLO và dependency quan trọng.

**SRE:** giúp xác định readiness, alert/runbook chuẩn, đánh giá RTO/RPO và khắc phục khi sự cố.

**Security/data governance:** hỗ trợ phân loại dữ liệu, security ownership, compliance và audit.

Không chuyển toàn bộ gánh nặng cập nhật catalog sang một nhóm platform duy nhất; họ sẽ không thể hiểu mọi thay đổi nghiệp vụ trong hàng trăm service.

## 33. Những anti-pattern phổ biến

### 33.1. Catalog chỉ là spreadsheet tên dịch vụ

Nếu không có team owner, runbook và link vận hành, khi incident người trực vẫn phải hỏi từng phòng ban. Bắt đầu tối giản được, nhưng phải ưu tiên thông tin tác nghiệp.

### 33.2. Owner là một cá nhân duy nhất

Người đó chuyển nhóm hoặc nghỉ khiến service vô chủ. Dùng team canonical và on-call schedule có phương án dự phòng.

### 33.3. Dữ liệu catalog do một nhóm nhập tay tất cả

Team platform có thể không biết mỗi lần service đổi API, owner hoặc dataset. Dùng metadata-as-code và connector với ownership rõ.

### 33.4. Tự động discovery được coi là đầy đủ

Runtime inventory biết pod đang chạy, nhưng không biết trách nhiệm nghiệp vụ, dữ liệu hay điều kiện decommission. Kết hợp khai báo owner và bằng chứng runtime.

### 33.5. Khai báo mọi dependency là “dependsOn” không loại

Một mối quan hệ dữ liệu khác synchronous RPC hoặc optional feature. Khi incident và impact analysis, cần type, direction và mức criticality.

### 33.6. Catalog dùng làm service discovery real-time

Danh mục thường có độ trễ đồng bộ; không để load balancer lấy endpoint theo catalog thay vì hệ thống runtime discovery được thiết kế cho health/traffic.

### 33.7. Portal đẹp nhưng link hỏng

Không có kiểm tra link, owner hoặc freshness. Thực hành: link validation, owner verification, stale signal và scorecard thực dụng.

### 33.8. Mọi field đều bắt buộc ngay từ ngày đầu

Quá nhiều trường khiến developer điền placeholder hoặc tạo entry kém chất lượng. Chọn minimum viable catalog, bổ sung theo lifecycle/tier và tự động hóa trường có nguồn.

### 33.9. Catalog làm lộ dữ liệu nhạy cảm

Tài liệu có secret, sơ đồ mạng riêng hoặc thông tin cá nhân được chia sẻ quá rộng. Áp phân loại, quyền truy cập và dùng tham chiếu chứ không lưu secret.

### 33.10. Xóa service retired khỏi catalog ngay

Mất lịch sử dependency và incident. Giữ bản ghi archived có lifecycle và retention phù hợp.

## 34. Các chỉ số đánh giá hiệu quả catalog

Không nên đánh giá bằng số lượng entry đơn thuần. Các KPI/metric có thể gồm:

| Chỉ số | Cách hiểu |
| --- | --- |
| Coverage | % production workloads được gắn với service catalog |
| Ownership coverage | % service production có owner team hợp lệ |
| Operational readiness | % service production có on-call, runbook, dashboard |
| Link validity | % link quan trọng hoạt động theo quyền kiểm tra |
| Freshness | % trường quan trọng được cập nhật/xác minh trong ngưỡng |
| Unowned services | Số service không có owner có thể liên hệ |
| Unknown workloads | Số workload đang chạy nhưng chưa match catalog |
| Dependency coverage | % service có khai báo dependency quan trọng |
| Onboarding time | Thời gian tìm đúng service/owner hoặc tạo service mới |
| Incident lookup time | Thời gian từ alert tới tìm được owner/runbook |
| Ownership transfer lead time | Thời gian handover đầy đủ khi đổi team |
| Retirement hygiene | % retired services đã thu hồi access/resource đúng quy trình |

Các tỷ lệ cần denominator rõ. Nếu tính trên mọi repository thay vì **production deployable components**, kết quả dễ sai. Đừng dùng metric một mình để đánh giá cá nhân; cần đọc ý nghĩa và kế hoạch cải thiện.

### 34.1. Ví dụ cải tiến qua hai kỳ

Giả sử tổ chức có 120 production services. Ban đầu 80 service có owner hợp lệ, 50 có runbook, 30 service có link SLO. Sau Golden Path, CI metadata lint và chiến dịch cập nhật:
- 120/120 có owner.
- 110/120 có runbook hợp lệ.
- 90/120 có SLO hoặc exemption được duyệt.
- 5 unknown workloads được phát hiện và bổ sung.

Các số liệu là minh họa. Mục tiêu quan trọng là số lần incident không tìm được người, số link hỏng và thời gian khôi phục giảm, không chỉ tỷ lệ điền đủ trường.

## 35. Kế hoạch triển khai service catalog theo giai đoạn

**Giai đoạn 1 — Inventory đáng tin:** nhập serviceId, tên, mô tả, domain, ownerTeam, repository, lifecycle. Đối chiếu với danh sách production workloads để phát hiện service thiếu.

**Giai đoạn 2 — Operability:** gắn on-call/escalation, dashboard, runbook, SLO, criticality. Ưu tiên các service có ảnh hưởng nghiệp vụ lớn và lịch sử incident.

**Giai đoạn 3 — Relationships:** thêm API/event/resource ownership, dependency graph và data classification. Dùng contract repository và traces để đối chiếu.

**Giai đoạn 4 — Automation:** metadata-as-code, CI schema validation, SCM/CI/CD/Kubernetes connectors, drift detection và owner attestation.

**Giai đoạn 5 — Self-service/governance:** Golden Paths, software templates, scorecards, onboarding/retirement workflow, quyền truy cập và policies theo tier.

**Giai đoạn 6 — Đo cải thiện:** theo dõi coverage, freshness, tìm owner và incident lookup time, giải quyết các nguồn xung đột.

Triển khai nên theo khả năng vận hành của tổ chức. Với một nhóm nhỏ, file YAML cùng trang README index có thể đủ. Với nhiều trăm dịch vụ và nhiều nhóm, developer portal và cơ chế data ownership tự động sẽ giá trị hơn.

## 36. Bài tập thực hành: xây dựng catalog cho nền tảng bán hàng

Một hệ thống có các microservices:
- product-service: quản lý sản phẩm.
- inventory-service: giữ và giải phóng tồn kho.
- order-service: tạo, cập nhật đơn hàng.
- payment-service: gọi đối tác thanh toán.
- notification-worker: gửi thông báo bất đồng bộ.

Mỗi service có repo và CI khác nhau, dùng PostgreSQL hoặc Redis, trao đổi HTTP và Kafka. Hiện tại:
- Có ba repository mới nhưng chưa ai biết owner.
- order-service chạy production, có alert nhưng không có runbook.
- payment-service có hai team cùng nhận mình sở hữu.
- notification-worker không có HTTP endpoint nên bị bỏ khỏi danh mục.
- Một Kafka topic đã đổi tên nhưng dependency graph vẫn ghi tên cũ.
- Product team dùng link dashboard cá nhân đã bị xóa.
- Khi region outage, không có ai biết service nào phải khôi phục trước.

**Yêu cầu A — Thiết kế entity:** xác định domain, system, component, API, topic, database/resource và mối quan hệ cho năm service.

**Yêu cầu B — Ownership:** chọn team accountable, on-call, fallback và data owner; với payment-service phải nêu quy trình xử lý xung đột quyền sở hữu.

**Yêu cầu C — Entry metadata:** viết một catalog YAML đầy đủ cho order-service, có owner, repo, pipeline, on-call, dashboard, runbook, SLO, criticality và dependency.

**Yêu cầu D — Validation:** xây dựng ít nhất 7 rule CI kiểm tra metadata trước khi production deploy. Phân biệt trường tự nhập và lấy từ runtime.

**Yêu cầu E — Incident flow:** khi checkout tăng lỗi, dùng catalog tìm dependency và owner, đề xuất quy trình triage liên kết SLO/metrics/rollout.

**Yêu cầu F — Drift:** thiết kế cách phát hiện topic đổi tên, dashboard link hỏng, owner team không tồn tại, unknown production workload.

**Yêu cầu G — Lifecycle:** mô tả từng bước đưa notification-worker từ experimental lên production, và retirement của một API/event cũ.

**Yêu cầu H — Security:** xác định trường nên công khai nội bộ, trường cần quyền hạn chế và dữ liệu tuyệt đối không lưu trong catalog.

Kết quả nên chứng minh rằng bất kỳ responder được cấp quyền nào cũng có thể trả lời: “dịch vụ này là gì, do ai sở hữu, đang chạy ở đâu, phụ thuộc gì và xử lý thế nào khi lỗi” mà không cần dựa vào trí nhớ của một cá nhân.

## 37. Câu hỏi tự kiểm tra

1. Service catalog và runtime service discovery khác nhau ở vòng đời dữ liệu nào?
2. Vì sao repository URL không phải lúc nào cũng là service ID tốt?
3. Owner team, technical contact và on-call schedule giải quyết ba nhu cầu gì?
4. Một microservice có thể có hai API và một event không, catalog nên mô hình thế nào?
5. Làm sao chọn nguồn sự thật cho từng loại metadata?
6. Vì sao không nên nhập tay image digest/replica count sau mỗi release?
7. Lỗi nào xuất hiện nếu on-call schedule thay đổi nhưng catalog vẫn link cũ?
8. Cách nào giúp catalog không bị stale khi team tái tổ chức?
9. Có thể khám phá owner thực sự chỉ từ service mesh traffic không?
10. Tại sao cần biểu diễn direction/type của dependency?
11. Sự khác nhau giữa lifecycle deprecated và retired là gì?
12. Vì sao một background worker không có API vẫn cần catalog entry?
13. Làm sao ngăn source code và runtime cùng khai báo owner trái nhau?
14. Một scorecard đủ 100% required fields có chứng minh service ổn định không?
15. Những thông tin nào không nên đưa vào public-facing catalog?
16. Service tier ảnh hưởng quy tắc SLO, DR, on-call và release gate ra sao?
17. Catalog cần hỗ trợ những bước nào khi chuyển ownership?
18. Trong incident, tại sao link runbook cần hoạt động khi hệ thống chính lỗi?
19. Cách nào phát hiện production service chạy nhưng chưa có entry?
20. Khi retire service, vì sao vẫn cần giữ bản ghi archived?
21. Làm sao xử lý tenant-dedicated deployment trong cùng một service logic?
22. Một hệ thống catalog unavailable nên ảnh hưởng CI/CD như thế nào?
23. Vì sao catalog nên liên kết SLO hơn là chỉ có green/red health?
24. Cơ chế nào bảo đảm người được gán owner đã chấp nhận trách nhiệm?

## 38. Tổng kết

**Danh mục dịch vụ là bản đồ trách nhiệm và tri thức vận hành của hệ thống microservices.** Nó kết nối entity kỹ thuật với business capability, team owner, API/event, resource, deployment, SLO, dashboard, runbook và quy trình sự cố.

Một catalog tốt không cần gom mọi dữ liệu vào một cơ sở dữ liệu duy nhất; cần **định nghĩa nguồn canonical, cơ chế cập nhật, provenance và quyền truy cập cho từng trường**. Dữ liệu tĩnh có thể quản lý trong Git qua PR, còn trạng thái triển khai và on-call nên được liên kết hoặc đồng bộ từ công cụ vận hành.

Ownership là trách nhiệm có thể hành động được: service có team accountable, người nhận cảnh báo hiện hành, đường escalation và handover khi tổ chức thay đổi. Catalog cần hỗ trợ cả service active, deprecated và retired, đồng thời quản lý các quan hệ phụ thuộc để phân tích tác động thay đổi và sự cố.

Trong kiến trúc microservices quy mô lớn, **service catalog + metadata-as-code + developer portal/Golden Path + drift detection** giúp các nhóm phát hành độc lập nhưng không đánh mất khả năng khám phá, trách nhiệm, tiêu chuẩn bảo mật và năng lực khôi phục của toàn hệ thống.

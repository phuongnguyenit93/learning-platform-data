# Tùy biến theo tenant và quản lý phiên bản sản phẩm

Trong mô hình **SaaS đa khách hàng (multi-tenant)**, nhiều tổ chức cùng sử dụng một sản phẩm và hạ tầng dùng chung ở những mức độ khác nhau. Mỗi tenant có thể khác nhau về thương hiệu, quy trình, gói dịch vụ, tính năng được bật, tích hợp, chính sách dữ liệu và tốc độ nâng cấp. Nếu mọi khác biệt được xử lý bằng nhánh code riêng hoặc triển khai một bản ứng dụng riêng cho từng khách hàng, chi phí phát triển và vận hành sẽ tăng nhanh, đồng thời sản phẩm khó giữ hành vi nhất quán.

**Tùy biến theo tenant (tenant customization)** và **quản lý phiên bản sản phẩm (product version management)** là hai năng lực kiến trúc giúp cung cấp trải nghiệm phù hợp cho từng khách hàng mà vẫn duy trì nền tảng có thể nâng cấp, kiểm soát và hỗ trợ lâu dài. Tùy biến cần có ranh giới rõ giữa cấu hình, extension và thay đổi lõi. Quản lý phiên bản cần xác định phiên bản ứng dụng, schema, API, feature và cấu hình nào đang áp dụng cho từng tenant; cách rollout, tương thích, rollback và kết thúc hỗ trợ ra sao.

Bài học thuộc chương **Kiến trúc đa khách hàng** của lộ trình **Cloud Architecture**. Chương trình học cách thiết kế ứng dụng cloud từ yêu cầu nghiệp vụ tới mạng, compute, dữ liệu và mô hình triển khai, cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Với chủ đề này, trọng tâm là cho phép khác biệt theo tenant mà không làm suy yếu cách ly dữ liệu, khả năng kiểm thử và tốc độ phát hành sản phẩm.

Sau bài học, bạn có thể:

- Phân biệt tenant configuration, feature flags, extension points, plugin và fork sản phẩm.
- Xác định ranh giới tùy biến nào an toàn để quản lý bằng dữ liệu/cấu hình.
- Thiết kế tenant context, inheritance, validation và audit cho cấu hình.
- Quản lý phiên bản ứng dụng, API, schema, cấu hình và feature theo tenant.
- Thiết kế rollout theo cohort, canary, progressive delivery và rollback.
- Xử lý tương thích ngược, migration, tenant pinning và deprecation.
- Bảo vệ tenant isolation khi tùy biến UI, workflow, policy và tích hợp.
- Đo mức độ tùy biến, phân mảnh phiên bản, chi phí và rủi ro vận hành.

## 1. Vì sao tenant cần được tùy biến?

Các tenant cùng dùng một sản phẩm nhưng không có cùng nhu cầu. Một doanh nghiệp cho thuê thiết bị có thể cần quy trình duyệt hợp đồng nhiều cấp; một cửa hàng nhỏ chỉ cần xác nhận tự động. Khách hàng tại những quốc gia khác nhau có thể dùng ngôn ngữ, tiền tệ, timezone và mẫu chứng từ khác nhau. Tenant ở gói cao cấp có thể cần SSO, audit export hoặc tích hợp ERP; tenant ở gói cơ bản không có những tính năng này.

Các khác biệt thường thuộc những nhóm sau:

| Nhóm khác biệt | Ví dụ | Cách biểu diễn thường gặp |
| --- | --- | --- |
| Branding/presentation | Logo, màu, tên miền, email template | Theme và branding configuration |
| Locale | Ngôn ngữ, timezone, currency, định dạng ngày | Locale settings |
| Product entitlement | Giới hạn người dùng, tính năng theo gói | Plan/entitlement policy |
| Feature availability | Bật tính năng beta hoặc module cụ thể | Feature flag/feature policy |
| Business policy | Hạn mức đặt thuê, thời gian giữ chỗ, approval threshold | Policy configuration |
| Workflow | Số bước phê duyệt, vai trò tham gia | Workflow definition/extension |
| Integration | ERP, identity provider, webhook, payment provider | Connector configuration |
| Data retention | Thời gian lưu hồ sơ, export, archive | Data policy |
| Security | SSO, MFA policy, IP allowlist, role mapping | Tenant security configuration |
| Reporting | Trường bổ sung, dashboard và metric riêng | Extension/read model/report definition |

Tùy biến giúp sản phẩm phù hợp hơn với từng khách hàng và có thể tăng khả năng đáp ứng yêu cầu hợp đồng. Nhưng mỗi biến thể tạo ra một tổ hợp hành vi cần hỗ trợ, kiểm thử và quan sát. Tùy biến càng tự do, rủi ro cấu hình sai, khó nâng cấp và khó giải thích hành vi càng lớn.

## 2. Phân biệt cấu hình, feature flag và extension

Không phải mọi khác biệt đều cần một cơ chế plugin. Chọn loại tùy biến theo bản chất của yêu cầu.

### 2.1. Configuration

**Configuration** là dữ liệu mô tả cách một capability đã có hoạt động trong giới hạn mà sản phẩm hỗ trợ. Ví dụ timezone, logo, ngưỡng phê duyệt hoặc template email được chọn từ danh sách an toàn.

Cấu hình nên có schema, kiểu dữ liệu, giá trị mặc định, validation, version và audit. Tránh dùng các trường text tự do để biểu diễn quy tắc phức tạp khi cần kiểm tra và đảm bảo tính đúng đắn.

### 2.2. Feature flag và entitlement

**Feature flag** điều khiển khả năng bật/tắt hoặc chuyển đổi một hành vi của sản phẩm. Flag có thể theo tenant, cohort, môi trường hoặc tỷ lệ traffic.

**Entitlement** xác định tenant được quyền sử dụng capability nào theo hợp đồng/gói dịch vụ, quota hoặc license. Flag là cơ chế phân phối hành vi; entitlement là quyết định về quyền sản phẩm. Không nên dùng feature flag thay thế kiểm tra authorization hoặc entitlement.

Ví dụ: code đã tồn tại nhưng chỉ tenant có entitlement Analytics Advanced mới được phép dùng. Feature flag có thể giữ tính năng ở trạng thái chưa rollout, nhưng cả hai điều kiện phải được kiểm tra ở backend.

### 2.3. Extension point

**Extension point** là giao diện được sản phẩm chủ động thiết kế để khách hàng hoặc module bổ sung hành vi trong phạm vi cho phép. Ví dụ hook trước khi gửi thông báo, custom field, webhook event subscription, formatter hoặc workflow step được hỗ trợ.

Extension cần có hợp đồng, sandbox/quyền hạn, timeout, version và chính sách lỗi. Không nên cho code tùy ý chạy trong tiến trình cốt lõi chỉ để đáp ứng một yêu cầu riêng của tenant.

### 2.4. Plugin và fork

**Plugin** đóng gói phần mở rộng thành module có lifecycle và interface được kiểm soát. **Fork** là nhánh code riêng của sản phẩm cho một khách hàng hoặc nhóm khách hàng.

Fork có thể cần thiết trong một số trường hợp có yêu cầu pháp lý/hạ tầng đặc biệt, nhưng tạo chi phí duy trì bản vá, merge, kiểm thử và hỗ trợ riêng. Với SaaS dùng chung, fork thường nên là ngoại lệ được phê duyệt thay vì cơ chế tùy biến mặc định.

| Cơ chế | Khách hàng tự cấu hình? | Có chạy logic mới? | Chi phí duy trì tương đối | Rủi ro chính |
| --- | --- | --- | --- | --- |
| Configuration | Trong schema cho phép | Không, chọn hành vi đã hỗ trợ | Thấp đến vừa | Cấu hình không hợp lệ hoặc xung đột |
| Feature flag | Theo policy được cấp | Không tự tạo logic mới | Thấp đến vừa | Flag tăng tổ hợp trạng thái |
| Extension point | Trong hợp đồng extension | Có, qua interface giới hạn | Vừa đến cao | Lỗi, quyền và tương thích module |
| Plugin | Theo marketplace/admin policy | Có | Cao | Supply chain, version và isolation |
| Fork | Thường qua team phát triển riêng | Có thể thay đổi bất kỳ phần nào | Rất cao | Phân mảnh sản phẩm và khó nâng cấp |

## 3. Xác định ranh giới tùy biến

Một nguyên tắc thực tế là tùy biến các biến thể có thể dự đoán và kiểm soát bằng cấu hình; chỉ mở extension khi có nhu cầu hành vi khác biệt lặp lại và đủ giá trị; tránh cho mỗi tenant một nhánh logic không có giới hạn.

### 3.1. Phân loại yêu cầu trước khi triển khai

Với mỗi yêu cầu khách hàng, hãy hỏi:

1. Đây là giá trị khác nhau hay một quy tắc nghiệp vụ mới?
2. Khác biệt có thể biểu diễn bằng enum, threshold, template hoặc policy không?
3. Khác biệt có dùng được cho nhiều tenant hay chỉ một khách hàng?
4. Có tác động tới transaction, security boundary hoặc data ownership không?
5. Có cần code chạy tùy ý hoặc gọi dịch vụ bên ngoài không?
6. Ai sở hữu cấu hình và chịu trách nhiệm kiểm thử?
7. Có thể chuyển tenant về mặc định nếu cấu hình lỗi không?
8. Khi nâng cấp sản phẩm, biến thể này có thể tiếp tục hoạt động không?

### 3.2. Ma trận quyết định

| Tình huống | Hướng thiết kế ưu tiên | Vì sao |
| --- | --- | --- |
| Đổi logo, màu, timezone | Configuration | Giá trị có schema và ít ảnh hưởng nghiệp vụ |
| Bật module đã có trong gói | Entitlement + feature policy | Tách quyền sản phẩm khỏi rollout |
| Approval threshold khác nhau | Policy configuration | Giữ logic kiểm tra trong domain service |
| Thêm bước approval chuẩn được hỗ trợ | Workflow definition | Hành vi được mô tả bằng schema có version |
| Tích hợp ERP với protocol khác | Connector/extension point | Cô lập logic tích hợp và credential |
| Chạy script tùy ý sau mọi giao dịch | Không cho phép trực tiếp; thiết kế event/extension giới hạn | Tránh mở quyền thực thi không kiểm soát |
| Thay invariant cốt lõi của booking | Domain capability có policy rõ hoặc sản phẩm riêng được duyệt | Không để tenant override tính đúng đắn tùy ý |

Không nên biến mọi yêu cầu thành cấu hình. Một field như allowNegativeBalance có thể nhìn đơn giản nhưng ảnh hưởng invariant tài chính. Quy tắc cốt lõi cần được domain owner đánh giá và thực thi an toàn.

## 4. Mô hình hóa tenant context

Dịch vụ cần biết request thuộc tenant nào và áp dụng cấu hình nào. Tenant context thường được xác lập tại biên tin cậy từ identity, domain, API key hoặc token đã xác thực.

Một context khái niệm:

~~~json
{
  "tenantId": "tenant-482",
  "plan": "enterprise",
  "locale": "vi-VN",
  "timezone": "Asia/Ho_Chi_Minh",
  "configurationVersion": 12,
  "featurePolicyVersion": 5,
  "requestId": "req-9281"
}
~~~

Đây là ví dụ minh họa, không phải schema bắt buộc. Context không được xây dựng bằng cách tin tenantId do client gửi. Backend phải xác minh caller thuộc tenant nào, resource có thuộc tenant đó không và người dùng có quyền thực hiện hành động được yêu cầu không.

### 4.1. Tenant resolution

Các nguồn tenant resolution thường gặp:

- Subdomain hoặc custom domain đã được ánh xạ và xác thực.
- Claim trong identity token do issuer tin cậy cấp.
- API key/client credential gắn với tenant.
- Context từ gateway/service identity trong hệ thống nội bộ có trust boundary rõ.

Nếu request chứa đồng thời nhiều dấu hiệu tenant, phải có quy tắc ưu tiên và kiểm tra consistency. Ví dụ subdomain tenant A nhưng token thuộc tenant B cần bị từ chối hoặc xử lý theo flow được định nghĩa; không được âm thầm chọn một giá trị.

### 4.2. Propagate context giữa dịch vụ

Khi request đi từ API gateway tới service khác, tenant context phải được truyền qua cơ chế tin cậy, có thể là signed token, claim được xác thực hoặc metadata nội bộ không thể bị client giả mạo. Các service downstream vẫn phải áp authorization thích hợp; không xem header X-Tenant-ID đơn lẻ là bằng chứng quyền.

Context cần tránh chứa toàn bộ cấu hình lớn hoặc secret. Nên truyền tenant identifier, trace/request ID và version/reference cần thiết; service lấy config từ nguồn được kiểm soát.

## 5. Cấu trúc và vòng đời tenant configuration

Cấu hình tenant cần có schema và lifecycle giống một loại dữ liệu sản phẩm quan trọng.

Một bản cấu hình nên có:

| Thuộc tính | Mục đích |
| --- | --- |
| tenantId | Tenant sở hữu cấu hình |
| configurationVersion | Version tăng dần hoặc ID bất biến |
| schemaVersion | Phiên bản schema cấu hình |
| values | Giá trị đã validate |
| inheritedFrom | Nguồn mặc định/plan/parent nếu có |
| updatedBy | Danh tính thực hiện thay đổi |
| updatedAt | Thời điểm thay đổi |
| effectiveAt | Thời điểm cấu hình có hiệu lực |
| status | Draft, validated, active, deprecated hoặc rollback state |
| changeReason | Lý do và ticket/phê duyệt liên quan |

### 5.1. Inheritance và precedence

Một sản phẩm có thể có mặc định toàn hệ thống, mặc định theo gói và override theo tenant. Cần định nghĩa thứ tự rõ, ví dụ:

**Platform default → Product plan default → Tenant override**

Tenant override chỉ được phép với các key có thể override. Chính sách bảo mật bắt buộc hoặc giới hạn pháp lý có thể không được override bởi tenant.

Không nên dùng nhiều lớp inheritance sâu khó dự đoán. Nếu cùng một key được khai báo ở ba nơi, UI quản trị và API phải cho biết giá trị hiệu lực đến từ đâu.

### 5.2. Ví dụ cấu hình có version

~~~yaml
tenantId: tenant-482
configurationVersion: 12
schemaVersion: 3
locale:
  language: vi-VN
  timezone: Asia/Ho_Chi_Minh
branding:
  theme: ocean
bookingPolicy:
  approvalMode: manager
  holdDurationMinutes: 20
notifications:
  receiptTemplate: standard-v2
~~~

Ví dụ trên không chứa thông tin xác thực. Secret của connector hoặc SMTP/API key phải lưu trong secret manager và được tham chiếu bằng ID, không đưa trực tiếp vào configuration document.

### 5.3. Validation và publish

Thay đổi cấu hình nên trải qua trạng thái:

1. Draft được tạo.
2. Kiểm tra schema, enum, range và dependency.
3. Kiểm tra policy và quyền người chỉnh sửa.
4. Preview tác động hoặc chạy validation theo tenant.
5. Review/approval nếu thay đổi nhạy cảm.
6. Publish thành một version bất biến.
7. Tenant/service bắt đầu dùng version mới theo effective time.
8. Theo dõi lỗi và có thể rollback về version trước.

Không chỉnh trực tiếp một document đang dùng mà không lưu version/audit. Version bất biến giúp điều tra vì sao hai request cùng tenant có kết quả khác nhau tại hai thời điểm.

## 6. Phân biệt cấu hình và secret

Cấu hình thông thường như locale, màu theme hoặc timeout có thể lưu trong configuration service. Secret như API key, client secret, private key, password và webhook signing secret cần lưu trong secret manager hoặc vault.

Nguyên tắc:

- Không đưa secret vào source control, feature flag, log, event payload hay client response.
- Configuration chỉ giữ secret reference và metadata cần thiết.
- Cấp quyền truy cập secret theo tenant, integration và environment.
- Có rotation, expiry, revoke và audit.
- Không trả secret cũ khi đọc lại cấu hình; chỉ hiển thị trạng thái đã thiết lập.
- Tách secret dev/staging/production.
- Khi tenant bị offboard, thu hồi connector credential và token liên quan.

Trong multi-tenant system, secret của tenant A không bao giờ được truy cập bởi runtime đang xử lý tenant B chỉ vì hai tenant dùng chung một worker. Secret retrieval phải gắn tenant identity và policy được kiểm tra server-side.

## 7. Quản lý feature và entitlement theo tenant

Một sản phẩm có thể cần ba lớp quyết định:

1. **Availability:** code/module đã được triển khai ở môi trường này chưa?
2. **Entitlement:** tenant có quyền dùng tính năng theo gói/hợp đồng không?
3. **Rollout flag:** tính năng đã được mở cho tenant/cohort này chưa?

Điều kiện cho phép thường phải thỏa cả ba, cùng với authorization của user và điều kiện nghiệp vụ.

~~~mermaid
flowchart TD
    R["Feature request"] --> A{"Available in deployment?"}
    A -- "No" --> D["Feature unavailable"]
    A -- "Yes" --> E{"Tenant entitled?"}
    E -- "No" --> D
    E -- "Yes" --> F{"Rollout enabled?"}
    F -- "No" --> D
    F -- "Yes" --> U{"User authorized?"}
    U -- "No" --> X["Access denied"]
    U -- "Yes" --> O["Execute capability"]
~~~

### 7.1. Tránh dùng flag làm security control

Feature flag có thể bị cache cũ, đọc trễ hoặc cấu hình sai. Nó không thay thế authorization trên từng request/resource. Nếu một thao tác nhạy cảm yêu cầu entitlement, backend phải kiểm tra tại điểm thực thi.

### 7.2. Flag lifecycle

Flag nên có owner, mục đích, ngày tạo, cohort, default, metric theo dõi và ngày dự kiến loại bỏ. Flag rollout tạm thời cần được dọn sau khi feature ổn định; nếu giữ lâu, số tổ hợp trạng thái tăng và tạo gánh nặng test.

## 8. Custom workflow và policy

Workflow tùy tenant có thể được mô tả bằng definition thay vì code riêng cho từng khách hàng. Ví dụ workflow phê duyệt booking có các bước: manager review, finance approval nếu giá trị vượt ngưỡng, rồi xác nhận.

Một workflow definition cần nêu:

- Các trạng thái và transition cho phép.
- Điều kiện/guard cho từng transition.
- Role hoặc nhóm được phép thực hiện.
- Timeout, escalation và hành động khi quá hạn.
- Idempotency và xử lý event trùng.
- Version definition đang áp dụng cho mỗi instance.
- Cách xử lý instance đang chạy khi tenant đổi workflow version.

Không nên cho tenant cấu hình một workflow có thể bỏ qua kiểm soát bắt buộc, tự cấp quyền hoặc thực hiện lệnh code tùy ý. Domain service vẫn phải bảo vệ invariant ở bước ghi cuối cùng.

### 8.1. Workflow version đang chạy

Nếu tenant đổi workflow từ version 4 sang version 5, cần quyết định instance đã bắt đầu theo version 4 sẽ tiếp tục version 4 hay migrate. Thông thường, instance đang chạy nên giữ workflow version đã pin để tránh thay đổi ý nghĩa giữa chừng; instance mới dùng version mới. Một số thay đổi có thể migrate an toàn nhưng cần công cụ và kiểm tra rõ.

## 9. Quản lý phiên bản sản phẩm: không chỉ là version ứng dụng

Trong SaaS đa tenant, “tenant đang ở version nào?” có thể nói tới nhiều loại version khác nhau.

| Loại version | Ví dụ | Ảnh hưởng |
| --- | --- | --- |
| Application/build version | release 2026.11.18 | Mã runtime đang phục vụ request |
| API contract version | v1, v2 | Client/partner contract |
| Database schema version | migration 145 | Cấu trúc dữ liệu |
| Tenant configuration schema | config schema v3 | Cách diễn giải config |
| Configuration version | tenant config 12 | Bộ giá trị hiệu lực |
| Workflow version | approval flow v5 | Instance mới/đang chạy dùng định nghĩa nào |
| Plugin/extension version | ERP connector 2.4 | Compatibility với platform |
| Feature policy version | rollout policy 5 | Feature availability theo tenant |

Một hệ thống có thể chạy cùng application build nhưng các tenant dùng configuration/workflow version khác nhau. Ngược lại, một tenant có thể được pin vào API contract cũ dù backend runtime đã nâng cấp, nếu lớp tương thích vẫn hỗ trợ.

### 9.1. Version phải có owner và nguồn sự thật

Mỗi loại version cần có nơi quản lý chính thức, quy tắc tăng version, compatibility policy và metadata truy vết. Không để version chỉ nằm trong ghi chú thủ công hoặc tên file mà không liên kết với tenant/resource đang chạy.

## 10. Release train và cohort rollout

Có nhiều cách phát hành phiên bản cho tenant.

| Mô hình | Cách hoạt động | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Big-bang | Tất cả tenant nâng cấp cùng lúc | Ít thời gian duy trì nhiều version | Blast radius lớn, khó rollback toàn diện |
| Cohort/wave | Nâng theo nhóm tenant | Giới hạn tác động và học từ wave trước | Cần theo dõi nhiều cohort |
| Canary tenants | Một nhóm nhỏ tenant đại diện dùng trước | Phát hiện lỗi sớm | Cần chọn cohort và tiêu chí đo tốt |
| Progressive rollout | Tăng tỷ lệ/nhóm theo điều kiện | Giảm rủi ro từ từ | Cần automation và observability |
| Tenant-pinned release | Tenant được giữ một version trong thời hạn | Hỗ trợ yêu cầu kiểm soát thay đổi | Tạo ma trận version lớn và kéo dài hỗ trợ |

Không phải tenant nào cũng nên được tự chọn version vô hạn. Pinning cần lý do hợp lệ, thời hạn, owner, chi phí hỗ trợ và kế hoạch nâng cấp.

### 10.1. Chọn cohort đại diện

Canary cohort nên đại diện cho khác biệt thật của hệ thống: region, plan, mức tùy biến, quy mô dữ liệu, tích hợp và traffic. Chỉ chọn tenant nhỏ, cấu hình mặc định có thể bỏ sót vấn đề trên tenant lớn hoặc có workflow phức tạp.

### 10.2. Tiêu chí promotion và rollback

Trước khi mở rộng wave, xem xét:

- Error rate và latency p95/p99.
- Transaction correctness và reconciliation.
- Job/queue backlog, timeout và retry.
- Lỗi connector/plugin.
- Schema migration progress.
- Customer support incidents và tenant-specific anomaly.
- Cost/compute regression.
- Các metric theo cohort và theo mức customization.

Rollback cần được định nghĩa cho application, API behavior, feature flag, configuration và schema riêng. Không phải mọi database migration đều có thể chạy ngược; đôi khi phải dùng forward fix hoặc expand–contract.

## 11. Tương thích ngược và schema migration

Khi platform nâng version, tenant có thể đang dùng client, integration hoặc workflow cũ. Cần quản lý tương thích giữa runtime, API, config và schema.

### 11.1. Expand–migrate–contract

Một quy trình thường dùng:

1. **Expand:** thêm column/field hoặc endpoint mới theo cách tương thích.
2. **Deploy compatible code:** phiên bản cũ và mới có thể hoạt động trong giai đoạn chuyển tiếp.
3. **Migrate/backfill:** chuyển dữ liệu tenant theo batch, có checkpoint và retry.
4. **Switch:** chuyển tenant/consumer sang schema hoặc contract mới.
5. **Verify:** kiểm tra tính đầy đủ, query, lỗi và hiệu năng.
6. **Contract:** chỉ bỏ field/API cũ khi không còn consumer được hỗ trợ.

### 11.2. Tenant migration state

Có thể theo dõi trạng thái migration theo tenant:

~~~yaml
tenantId: tenant-482
fromSchemaVersion: 7
targetSchemaVersion: 8
status: IN_PROGRESS
checkpoint: batch-0042
startedAt: 2026-11-18T01:00:00Z
lastError: null
~~~

Đây là ví dụ minh họa. Migration phải idempotent hoặc có checkpoint tin cậy, giới hạn concurrency và có thể resume. Không chạy một migration lớn đồng thời cho mọi tenant nếu nó làm quá tải database hoặc khóa bảng dùng chung.

### 11.3. Backward compatibility không phải vĩnh viễn

Duy trì API/config/schema cũ vô thời hạn sẽ làm runtime phức tạp. Cần support window, deprecation notice, telemetry về tenant/client còn dùng version cũ và quy trình exception có thời hạn.

## 12. Configuration migration và rollback

Schema cấu hình cũng tiến hóa. Ví dụ version 2 có một trường holdDuration, version 3 tách thành minimumHold và maximumHold. Cần định nghĩa upcaster/default và validation để diễn giải cấu hình cũ.

Các nguyên tắc:

- Giữ raw/original config version nếu cần audit và rollback.
- Viết migration có thể chạy lại an toàn.
- Validate config sau migration trước khi activate.
- Phân biệt null, missing và default.
- Không tự gán giá trị có ảnh hưởng nghiệp vụ khi chưa có quyết định.
- Cho phép preview và migrate theo cohort.
- Có rollback hoặc forward-fix plan.
- Ghi lại ai/chương trình nào đã chuyển cấu hình.

Không rollback một config document cũ nếu product code mới đã thay đổi semantics mà không còn hỗ trợ nó. Khi đó phải chuyển về một version code tương thích trước hoặc thực hiện forward correction.

## 13. Extension/plugin lifecycle và compatibility

Nếu sản phẩm hỗ trợ extension hoặc plugin, cần quản lý như một thành phần phần mềm có dependency và quyền riêng.

Một extension manifest có thể mô tả:

- Plugin ID, vendor và version.
- Platform/API compatibility range.
- Permissions và scopes.
- Required secrets/credentials references.
- Resource/timeout/concurrency limits.
- Event subscriptions hoặc hook points.
- Configuration schema/version.
- Signature/provenance và approval.
- Owner, support status và deprecation date.

Plugin không nên tự động được quyền đọc mọi bảng hoặc gọi mọi API nội bộ. Cần capability-based permission, sandbox/isolation thích hợp, audit và quota. Plugin lỗi phải không làm sập request cốt lõi; timeout và circuit breaker cần bảo vệ host.

### 13.1. Compatibility matrix

Một platform có thể phải hỗ trợ nhiều kết hợp:

| Platform runtime | API contract | Plugin | Config schema | Trạng thái |
| --- | --- | --- | --- | --- |
| R12 | v2 | P3 | C4 | Supported |
| R12 | v1 adapter | P2 | C3 upcast | Transitional |
| R11 | v1 | P2 | C3 | Deprecated |
| R10 | v1 | P1 | C2 | End of support |

Bảng này chỉ minh họa cách suy nghĩ; không phải khuyến nghị giữ nhiều dòng version như nhau. Ma trận càng lớn càng tốn test và incident diagnosis. Cần giới hạn số combination supported và có kế hoạch loại bỏ.

## 14. Tùy biến dữ liệu và custom fields

Custom field giúp tenant bổ sung thuộc tính riêng như mã phòng ban, nhóm tài sản hoặc mã hợp đồng nội bộ. Tuy nhiên, tự do tạo trường có thể gây khó khăn cho indexing, validation, query, export, data governance và schema evolution.

Cần xác định:

- Field type: string, number, date, enum, boolean hay reference.
- Validation: length, range, required, pattern và allowed values.
- Sensitivity: public, internal, confidential, personal data.
- Search/filter/sort được hỗ trợ tới đâu.
- Indexing và quota cho số lượng field.
- Version và lifecycle khi field bị rename/deprecate.
- API/export representation.
- Tenant scoping và authorization.
- Ảnh hưởng tới analytics/warehouse.

Không dùng custom field để thay thế cột lõi có invariant/query quan trọng. Ví dụ trạng thái payment hoặc tenant owner phải là field domain được quản lý rõ, không nên biến thành key tùy ý trong JSON.

## 15. Cách ly tenant trong mọi lớp tùy biến

Một lỗi nghiêm trọng là cấu hình hoặc extension của tenant A được sử dụng khi xử lý request tenant B. Điều này có thể xảy ra ở cache, background job, event consumer, plugin context, secret lookup hoặc shared worker.

Các nguyên tắc:

1. Resolve tenant từ danh tính đã xác thực.
2. Gắn tenant context vào mọi query, job, event và cache key phù hợp.
3. Kiểm tra ownership của resource ở backend, không dựa vào UI.
4. Không tin tenantId từ payload nếu chưa xác thực nguồn và quyền.
5. Tách secret và connector credential theo tenant.
6. Scope custom field, template, workflow và plugin registration theo tenant.
7. Bảo vệ log/export để không trộn dữ liệu tenant.
8. Test cross-tenant access và cache leakage.
9. Có audit cho admin/platform operator khi override tenant configuration.
10. Có break-glass access với thời hạn, lý do và review.

### 15.1. Cache configuration đúng cách

Cache key cần bao gồm tenant ID và version của cấu hình, ví dụ một key khái niệm tenant/config/12. Khi publish version mới, service có thể invalidate hoặc đọc version reference mới. Nếu cache chỉ theo tên key chung như branding hoặc policy, tenant khác có thể nhận nhầm cấu hình.

Cần có TTL/fallback và cách làm mới khi configuration service không khả dụng. Không nên dùng cấu hình cũ vô thời hạn cho policy bảo mật hoặc quyết định nhạy cảm.

## 16. Tenant-specific customization và dữ liệu đa vùng

Một tenant có thể đặt tại region cụ thể theo hợp đồng hoặc quy định dữ liệu. Cấu hình tenant có thể chứa data residency region, nhưng việc lưu trú phải được enforce ở provisioning, storage, backup, logging và processing, không chỉ ở UI.

Cần quản lý:

- Tenant region/placement policy.
- Region-specific database/storage.
- Replication/backup boundary.
- Encryption key location nếu có yêu cầu.
- Service-to-service route và egress.
- Support/operator access.
- Disaster recovery region được phê duyệt.
- Quy trình chuyển tenant giữa region.

Một feature flag không thể bảo đảm data residency. Đây là thuộc tính hạ tầng và data placement cần kiểm soát ở mức platform.

## 17. Tenant onboarding, upgrade và offboarding

### 17.1. Onboarding

Luồng onboarding tenant có thể gồm:

1. Tạo tenant identity và tenant record.
2. Chọn plan/entitlement.
3. Xác định region và data placement.
4. Tạo tenant configuration từ default/plan template.
5. Provision database/schema/resource nếu topology yêu cầu.
6. Thiết lập domain, identity provider và secret reference.
7. Chạy validation và smoke test.
8. Kích hoạt feature policy.
9. Ghi audit và thông báo hoàn tất qua hệ thống hỗ trợ sản phẩm.

Onboarding cần idempotent để retry không tạo duplicate resource. Trạng thái provisioning phải được lưu để tiếp tục sau lỗi.

### 17.2. Upgrade

Upgrade tenant có thể chỉ là chuyển config/feature policy, hoặc cần migration schema/data và plugin. Phải kiểm tra compatibility và lập kế hoạch theo cohort.

### 17.3. Offboarding

Offboarding cần revoke user/session/API credential, vô hiệu domain/integration, export hoặc xóa dữ liệu theo hợp đồng, xóa secrets, dọn resource và xác nhận backup/retention. Không xóa nhầm dữ liệu dùng chung hoặc tenant khác. Audit record về hoạt động offboarding phải được giữ theo policy.

## 18. Vận hành cấu hình: audit, drift và change control

Configuration drift xảy ra khi trạng thái thực tế khác với version được phê duyệt. Một admin có thể thay đổi trực tiếp qua console; một automation lỗi có thể ghi đè configuration; một service cache lâu có thể dùng version cũ.

Cần:

- Lưu mọi thay đổi có actor, timestamp, before/after hoặc diff, reason và approval.
- So sánh desired version với effective version đang được các service sử dụng.
- Phát hiện tenant chưa nhận config mới hoặc migration bị kẹt.
- Có quyền RBAC tách read/edit/publish/approve.
- Hỗ trợ staged rollout cấu hình.
- Giữ lịch sử version bất biến và restore có kiểm soát.
- Không log secret trong diff.
- Có alert khi config bị thay đổi ngoài pipeline/chính sách.

Với cấu hình nhạy cảm, thay đổi cần hai người phê duyệt hoặc workflow kiểm soát theo phân quyền của tổ chức.

## 19. Hiệu năng và scale của configuration service

Khi mọi request đều cần đọc tenant config, configuration service có thể trở thành dependency nóng. Cần chọn cách phân phối cấu hình:

- Local in-memory cache theo tenant/version.
- Distributed cache để giảm đọc database.
- Push invalidation hoặc event khi config publish.
- Signed/versioned snapshot cho worker.
- Preload config cho tenant hoạt động nhiều.
- TTL ngắn hơn cho policy nhạy cảm, dài hơn cho branding ít đổi.
- Fallback và circuit breaker khi config store lỗi.

Không nên cache mọi thứ giống nhau. Locale/theme có thể chấp nhận TTL dài; entitlement/security policy cần freshness và enforcement mạnh hơn. Cache invalidation cần xử lý event trùng, event đến muộn và worker khởi động lại.

## 20. Đo mức độ tùy biến và phân mảnh sản phẩm

Một sản phẩm multi-tenant cần biết mình đang hỗ trợ bao nhiêu biến thể.

Các chỉ số hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| Active configuration versions | Số version cấu hình còn đang được sử dụng |
| Tenant version distribution | Số tenant trên từng runtime/API/schema version |
| Feature flag cardinality | Số flag và số combination thực tế |
| Customization footprint | Số custom fields, workflows, themes, plugins theo tenant |
| Upgrade adoption | Tỷ lệ tenant đã nâng cấp theo wave |
| Unsupported version count | Tenant đang ở version hết hỗ trợ |
| Migration failure/retry | Chất lượng và tiến độ nâng cấp |
| Config propagation delay | Thời gian từ publish tới khi tenant áp dụng |
| Support incidents by customization | Sự cố liên quan từng loại tùy biến |
| Cost per tenant/variant | Chi phí compute, storage, cache và support |

Không chỉ đếm số flag. Hai feature flag độc lập có thể tạo bốn tổ hợp; mười flag có thể tạo tới 1.024 combination về mặt lý thuyết. Không cần test mọi combination một cách mù quáng, nhưng phải quản lý dependency, pairwise coverage và cohort quan trọng.

## 21. Ví dụ tổng thể: nền tảng SaaS đặt thuê thiết bị

Giả sử nền tảng phục vụ ba nhóm tenant:

- Tenant A: doanh nghiệp lớn, cần SSO, approval nhiều cấp, tích hợp ERP và audit export.
- Tenant B: doanh nghiệp vừa, dùng quy trình approval chuẩn và báo cáo cơ bản.
- Tenant C: cửa hàng nhỏ, workflow tự động và cấu hình đơn giản.

### 21.1. Cách mô hình hóa khác biệt

| Capability | Tenant A | Tenant B | Tenant C |
| --- | --- | --- | --- |
| Plan | Enterprise | Business | Starter |
| Authentication | SSO + MFA policy | MFA | Password/SSO nếu được cấp |
| Approval | Multi-step workflow v5 | Standard workflow v3 | Auto-approve theo policy |
| ERP integration | Connector v2.4 | Không bật | Không bật |
| Analytics | Advanced entitlement | Basic entitlement | Basic summary |
| Branding | Custom theme | Theme chuẩn | Theme chuẩn |
| Retention | Theo hợp đồng được duyệt | Standard policy | Standard policy |

### 21.2. Kiến trúc khái niệm

~~~mermaid
flowchart TB
    C["Web / Mobile / Partner clients"] --> EDGE["API gateway and identity"]
    EDGE --> RES["Tenant resolver"]
    RES --> APP["Shared application services"]
    APP --> CP["Tenant configuration / entitlement service"]
    APP --> DOM["Domain services"]
    DOM --> DB[("Tenant-aware data layer")]
    APP --> EXT["Extension and connector runtime"]
    CP --> CACHE["Versioned config cache"]
    CACHE --> APP
    EXT --> ERP["Tenant-specific ERP"]
~~~

Shared application services đọc tenant context và policy version phù hợp. Domain service vẫn bảo vệ invariant. Connector runtime có scope credential theo tenant; config cache dùng tenant/version để tránh trộn cấu hình.

### 21.3. Một lần nâng phiên bản

Giả sử platform phát hành runtime R13, config schema C5 và workflow engine v6:

1. Chạy compatibility test với các config schema đang hỗ trợ.
2. Triển khai R13 ở staging và cohort nội bộ.
3. Canary tenant đại diện cho Starter, Business và Enterprise.
4. Migration config C4 sang C5 theo batch; validate các tenant có custom workflow.
5. Rollout R13 theo wave; workflow instance cũ tiếp tục version đã pin nếu policy quy định.
6. Theo dõi error rate, latency, migration failure và connector health theo tenant.
7. Dừng wave nếu vượt ngưỡng; rollback runtime/flag hoặc forward-fix config theo khả năng tương thích.
8. Gửi thông báo deprecation và kết thúc hỗ trợ version cũ theo thời hạn.

Không giả định mọi thứ rollback cùng lúc. Nếu schema đã được expand và dữ liệu mới đã được ghi, rollback application có thể cần compatibility adapter hoặc forward fix.

## 22. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Fork code cho mỗi tenant | Phân mảnh, merge và patch tốn kém | Configuration/extension có contract; fork là ngoại lệ |
| Dùng feature flag làm authorization | Tenant/user có thể gọi API trực tiếp | Backend kiểm tra entitlement và permission |
| TenantId lấy trực tiếp từ client | Cross-tenant access | Resolve từ identity/domain đã xác thực |
| Cache config không có tenant/version | Dùng nhầm cấu hình tenant khác hoặc version cũ | Cache key theo tenant và version |
| Cho tenant tùy biến invariant cốt lõi | Dữ liệu và quy tắc không nhất quán | Domain service giữ invariant, policy có giới hạn |
| Secret lưu trong config thường | Lộ credential qua log/export | Secret manager và reference |
| Plugin có quyền rộng | Lộ dữ liệu hoặc ảnh hưởng host | Sandbox, scoped capability, quota và audit |
| Giữ mọi API/schema version vô hạn | Ma trận test và runtime phức tạp | Support window và deprecation |
| Migration chạy đồng loạt | Lock/load spike và outage | Cohort, batch, rate limit, checkpoint |
| Không pin workflow instance | Quy trình đang chạy đổi semantics giữa chừng | Instance lưu workflow version |
| Flag không có owner/ngày xóa | Tăng tổ hợp trạng thái và lỗi khó tái hiện | Flag lifecycle và cleanup |
| Rollback config không tương thích code | Runtime diễn giải sai cấu hình cũ | Compatibility matrix và forward-fix plan |
| Không theo dõi tenant adoption | Tenant mắc kẹt ở version cũ | Version distribution và upgrade SLO |
| Không có audit thay đổi admin | Khó giải thích config drift | Change history, approval và actor |
| Xóa tenant nhưng quên secret/export | Credential còn hiệu lực, dữ liệu tồn dư | Offboarding runbook xuyên mọi lớp |

## 23. Quy trình thiết kế và triển khai

1. **Lập danh mục biến thể:** phân loại branding, locale, policy, feature, workflow, integration, data và security.
2. **Định nghĩa tenant context:** nguồn tin cậy, identity, tenant resolution và propagation.
3. **Chọn cơ chế tùy biến:** config, entitlement, flag, extension hay plugin theo ranh giới.
4. **Thiết kế config schema:** default, override precedence, version, validation và secret references.
5. **Bảo vệ domain invariant:** xác định phần nào tenant được thay đổi và phần nào platform bắt buộc.
6. **Định nghĩa version policy:** runtime, API, schema, config, workflow và plugin compatibility.
7. **Thiết kế release:** cohort, canary, metrics, stop condition và rollback/forward-fix.
8. **Thiết kế migration:** idempotency, checkpoint, rate limit, preview và reconciliation.
9. **Bảo mật:** tenant isolation, least privilege, plugin sandbox, audit và data residency.
10. **Vận hành:** cache, invalidation, drift detection, support window và offboarding.
11. **Đo lường:** adoption, config propagation, incidents, customization footprint và cost.
12. **Review định kỳ:** loại bỏ flag/extension/version không còn được hỗ trợ.

## 24. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Config/extension có version và rollback? Migration idempotent? Canary có đo lỗi theo tenant? Workflow đang chạy có giữ đúng version? |
| **Bảo mật** | Tenant context có đáng tin? Cache/secret/plugin có cô lập? Entitlement có được enforce ở backend? Admin override có audit? |
| **Hiệu quả hiệu năng** | Config lookup/cache có tạo bottleneck? Plugin có timeout/quota? Tenant-specific query có gây noisy neighbor? |
| **Tối ưu chi phí** | Số variant, plugin, version và support window có được giới hạn? Chi phí per tenant/extension được đo? |
| **Khả năng vận hành** | Có catalog version, config drift, adoption, migration progress, deprecation và runbook theo tenant? |

### Checklist nghiệm thu

- [ ] Tenant context được resolve từ identity/domain đã xác thực và truyền an toàn.
- [ ] Mọi resource query, cache, event, job và secret đều được scope theo tenant.
- [ ] Cấu hình có schema, default, precedence, validation và immutable version.
- [ ] Secret chỉ được lưu trong secret manager; config chứa reference.
- [ ] Entitlement, feature rollout và authorization được tách rõ.
- [ ] Domain service giữ invariant quan trọng dù tenant có policy override.
- [ ] Workflow/plugin có compatibility version, quyền tối thiểu và giới hạn tài nguyên.
- [ ] Application, API, schema, config và plugin version có owner/source of truth.
- [ ] Rollout có cohort, canary, metric và stop condition.
- [ ] Migration có checkpoint, idempotency, validation và rollback/forward-fix.
- [ ] Support window và deprecation được công bố, đo adoption.
- [ ] Config drift, admin change và override có audit.
- [ ] Data residency, retention và offboarding lan qua mọi bản sao/tích hợp.
- [ ] Cross-tenant cache/resource access đã được kiểm thử.
- [ ] Đo được customization footprint, version distribution, incidents và cost.

## 25. Bài tập áp dụng

Một SaaS quản lý thuê thiết bị có 500 tenant. Một số khách hàng muốn thay logo, ngôn ngữ và currency; 20 doanh nghiệp cần quy trình phê duyệt nhiều cấp; 5 tenant muốn tích hợp ERP riêng; một tenant lớn yêu cầu giữ phiên bản ứng dụng cũ trong 6 tháng do quy trình kiểm định nội bộ. Platform đang chuẩn bị nâng API v1 lên v2 và schema cấu hình C3 lên C4.

Hãy thiết kế:

1. Phân loại yêu cầu thành configuration, entitlement, feature flag, workflow extension, connector/plugin hay ngoại lệ fork.
2. Mô hình tenant context và bảo vệ request/resource khỏi truy cập chéo.
3. Schema config có version, inheritance, validation và secret reference.
4. Chính sách quản lý workflow instance khi tenant publish workflow version mới.
5. Cách rollout API v2, config C4 và runtime mới theo cohort.
6. Điều kiện cho tenant pin version cũ và cách giới hạn support cost/risk.
7. Migration C3 sang C4 có checkpoint, idempotency, preview và rollback/forward-fix.
8. Cách bảo đảm plugin ERP không truy cập dữ liệu tenant khác.
9. Metric theo dõi adoption, config propagation, lỗi extension và số version còn hoạt động.
10. Những điều kiện khiến yêu cầu giữ version cũ phải bị từ chối hoặc chuyển sang deployment riêng.

Một phương án hợp lý có thể dùng config cho branding/locale, workflow definition versioned cho approval, connector runtime với secret riêng cho ERP, còn API/runtime pinning được cấp ngoại lệ có thời hạn và kế hoạch nâng cấp. Mọi command vẫn phải qua domain service có thẩm quyền; feature flag không thay authorization và cache phải scope tenant/version.

**Điểm cốt lõi:** tùy biến tenant tạo khác biệt có kiểm soát trên cùng sản phẩm; quản lý version bảo đảm những khác biệt đó có thể được phát hành, tương thích, quan sát và nâng cấp. Ranh giới tốt giữ cấu hình trong schema được kiểm tra, extension trong capability có giới hạn và invariant trong domain service. Một SaaS đa tenant bền vững phải biết mỗi tenant đang dùng phiên bản nào, giá trị nào có hiệu lực, ai thay đổi, dữ liệu được cô lập ra sao và cách nâng cấp hoặc quay lui an toàn.

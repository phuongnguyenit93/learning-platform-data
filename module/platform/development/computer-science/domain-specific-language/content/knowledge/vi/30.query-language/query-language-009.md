# Kiểm soát quyền truy cập

## 1. Kiểm soát quyền truy cập trong DSL truy vấn là gì?

Kiểm soát quyền truy cập (access control) là tập hợp cơ chế xác định ai được phép truy vấn nguồn dữ liệu nào, đọc trường nào, nhìn thấy bản ghi nào và thực hiện những thao tác nào. Với DSL truy vấn, quyền truy cập là một phần của ngữ nghĩa thực thi: một query có thể hợp lệ về cú pháp và kiểu nhưng vẫn không được phép chạy đối với người gọi hiện tại.

Ví dụ, một người dùng có thể viết:

~~~text
from Orders
where status == APPROVED
select orderId, customerId, total
~~~

Query engine cần xác định người gọi có quyền đọc Orders hay không, có được xem total hay không, và có được xem đơn hàng của mọi khách hàng hay chỉ các đơn thuộc tenant hoặc khu vực được cấp quyền. Chỉ kiểm tra query có parse được hay không là chưa đủ.

Trong hệ thống thực tế, DSL thường được gửi từ editor, dashboard, API hoặc một service khác tới query engine. Nội dung query và tham số có thể do người dùng kiểm soát, vì vậy engine phải thực thi policy ở ranh giới tin cậy. Việc ẩn nút hoặc field trên giao diện không thay thế được kiểm tra quyền ở backend.

## 2. Mục tiêu của access control

Một mô hình kiểm soát quyền truy cập tốt cần đạt các mục tiêu:

1. Chỉ người gọi đã được xác thực mới có thể truy cập chức năng cần bảo vệ.
2. Mỗi người gọi chỉ được thực hiện hành động phù hợp với quyền được cấp.
3. Quyền được áp dụng nhất quán dù query đến từ IDE, API, batch job hay dashboard.
4. Dữ liệu được giới hạn theo tenant, tổ chức, chủ sở hữu hoặc phạm vi nghiệp vụ.
5. Trường nhạy cảm được bảo vệ ở tầng dữ liệu, không chỉ ở giao diện.
6. Function và operator có side effect được kiểm soát theo capability.
7. Query tốn kém được giới hạn bằng timeout, quota và cost budget.
8. Quyết định cho phép hoặc từ chối có thể được giải thích và audit.
9. Policy có thể thay đổi mà không cần sửa từng query source.
10. Các thay đổi quyền có thể được kiểm thử và triển khai có kiểm soát.

Các mục tiêu này cần cân bằng. Nếu policy quá rộng, dữ liệu có thể bị lộ; nếu quá chặt hoặc khó cấu hình, người dùng hợp lệ không thể hoàn thành công việc. Một thiết kế tốt làm rõ chủ thể, tài nguyên, hành động, điều kiện và nơi policy được thực thi.

## 3. Các khái niệm cơ bản

Một quyết định truy cập thường dựa trên các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Subject / Principal | Người hoặc tiến trình đang yêu cầu | user-104, service-reporting |
| Resource | Dữ liệu hoặc chức năng được truy cập | Orders, field customer.email |
| Action | Hành động được yêu cầu | read, export, aggregate, execute |
| Context | Thông tin của request và môi trường | tenant, thời gian, thiết bị, source IP |
| Policy | Quy tắc quyết định quyền | Analyst chỉ đọc đơn hàng trong tenant |
| Decision | Kết quả đánh giá | Permit hoặc Deny |
| Obligation | Điều kiện phải áp dụng khi cho phép | Mask email, giới hạn 100 dòng |

Một mô hình khái niệm:

~~~text
authorize(
    subject,
    action,
    resource,
    context
) -> decision
~~~

Ví dụ:

~~~text
subject: user-104
action: read
resource: Orders.total
context:
  tenant: north-region
  purpose: monthly-report
decision: permit
obligations:
  rowFilter: tenantId == "north-region"
  maxRows: 10000
~~~

Quyết định permit không nhất thiết có nghĩa người dùng được đọc toàn bộ resource. Policy có thể cho phép truy vấn nhưng kèm row filter, field masking, giới hạn kết quả hoặc yêu cầu audit.

## 4. Authentication và authorization

Authentication và authorization giải quyết hai câu hỏi khác nhau:

- **Authentication:** người gọi là ai?
- **Authorization:** người gọi đó được phép làm gì?

Một hệ thống có thể xác thực người dùng bằng session, token, certificate hoặc identity provider. Sau khi xác thực, hệ thống tạo principal có định danh và các claim cần thiết. Query engine dùng principal này để đánh giá policy.

Ví dụ:

~~~text
authenticated principal:
  subjectId: user-104
  tenantId: north-region
  roles:
    - analyst
  groups:
    - finance-readers
~~~

DSL không nên cho người dùng tự khai báo principal hoặc role trong query rồi xem đó là bằng chứng quyền. Những thuộc tính identity phải đến từ nguồn xác thực đáng tin cậy, không lấy từ tham số mà client có thể tùy ý sửa.

### 4.1. Không tin dữ liệu identity từ query

Một query như sau không thể tự cấp quyền:

~~~text
from Orders
where tenantId == "north-region"
options {
    role: "admin"
}
~~~

Giá trị role trong query chỉ là dữ liệu do caller gửi. Server phải lấy principal từ authentication context và áp dụng policy tương ứng. Nếu client có thể tự đặt role hoặc tenant trong payload rồi backend tin giá trị đó, người dùng có thể giả mạo quyền.

### 4.2. Service identity

Không phải mọi query đều do người dùng tương tác trực tiếp. Batch job, scheduler hoặc service có thể gửi query bằng service identity. Cần cấp quyền tối thiểu cho từng service và ghi nhận service nào đã thực hiện truy vấn.

Nếu service thực hiện hành động thay mặt người dùng, hệ thống nên giữ cả caller identity và delegated identity để audit. Không nên ghi mọi truy vấn dưới một tài khoản service chung mà không có thông tin người khởi tạo.

## 5. Authentication context trong query execution

Sau khi xác thực, hệ thống có thể tạo một execution context bất biến cho mỗi request:

~~~text
QueryExecutionContext
  principalId: user-104
  tenantId: north-region
  roles: [analyst]
  scopes: [orders:read]
  requestId: req-812
  purpose: monthly-report
  issuedAt: ...
  expiresAt: ...
~~~

Context được truyền qua các lớp parse, validation, planning và execution theo một cách có kiểm soát. Query source không được ghi đè identity hoặc claim trong context.

Các thuộc tính có thể được dùng để:

- Kiểm tra quyền trên source.
- Áp dụng row-level filter.
- Xác định field được phép đọc.
- Giới hạn function có thể gọi.
- Tính quota và cost budget.
- Gắn audit event với request.

Nếu query engine phân tán qua nhiều service, context cần được truyền qua kênh xác thực và bảo vệ tính toàn vẹn. Không nên tin một header do client gửi nếu nó chưa được gateway hoặc identity service xác minh.

## 6. Authorization theo source và action

Trước khi truy vấn dữ liệu, engine cần xác định caller có quyền thực hiện action trên source hay không.

Các action thường gặp:

- Discover: xem tên source hoặc schema.
- Read: đọc dữ liệu.
- Filter: dùng field trong điều kiện.
- Project: trả field trong kết quả.
- Aggregate: tính toán trên field.
- Join: kết hợp source.
- Export: tải hoặc xuất dữ liệu.
- Subscribe: đăng ký nhận dữ liệu liên tục.
- Execute: gọi function hoặc stored query.
- Administer: thay đổi policy hoặc metadata.

Không nên mặc định quyền read bao gồm mọi hành động khác. Ví dụ, người dùng có thể được xem một số trường nhưng không được export toàn bộ kết quả hoặc tạo truy vấn streaming lâu dài.

### 6.1. Phân biệt discover và read

Có trường hợp người dùng được biết một nguồn tồn tại nhưng không được đọc dữ liệu, hoặc không được biết tên nguồn đó. Policy cần xác định riêng quyền khám phá metadata.

Completion và schema browser cũng có thể tiết lộ tên bảng, field hoặc API. Language server cần dùng quyền phù hợp khi hiển thị thông tin từ workspace hoặc remote schema registry.

### 6.2. Join và nhiều nguồn

Một query có thể đọc nhiều source:

~~~text
from Orders as o
join Customers as c on o.customerId == c.id
select o.orderId, c.name
~~~

Engine cần kiểm tra quyền trên cả Orders và Customers, cũng như các field được dùng trong join, filter và projection. Quyền đọc Orders không tự động cấp quyền đọc Customers.

Nếu một source bị từ chối, query thường phải bị từ chối toàn bộ thay vì trả kết quả một phần mà không có semantics rõ ràng. Nếu DSL hỗ trợ partial result, policy và diagnostic cần mô tả chính xác điều đó.

## 7. Role-Based Access Control (RBAC)

RBAC cấp quyền thông qua vai trò. Người dùng được gán một hoặc nhiều role; role được gán các permission.

Ví dụ:

~~~text
Role Analyst:
  Orders.read
  Products.read
  Reports.create

Role Operator:
  Orders.read
  OrderStatus.read
  Workflow.execute

Role Administrator:
  Orders.read
  Orders.manage
  Policies.manage
~~~

Một principal có role Analyst có thể đọc dữ liệu và tạo báo cáo nhưng không được sửa policy.

### 7.1. Ưu điểm của RBAC

- Dễ hiểu và dễ quản lý khi tổ chức có nhóm vai trò ổn định.
- Permission được định nghĩa tập trung.
- Dễ audit việc gán role.
- Có thể tái sử dụng role giữa nhiều ứng dụng.

### 7.2. Hạn chế của RBAC

RBAC có thể tạo ra quá nhiều role nếu quyền phụ thuộc vào tenant, khu vực, dự án, thời gian hoặc thuộc tính dữ liệu. Một role Analyst có thể được đọc Orders ở tenant A nhưng không được đọc tenant B; role đơn thuần không diễn đạt đầy đủ khác biệt đó.

Có thể kết hợp RBAC với ABAC: role xác định nhóm quyền cơ bản, còn thuộc tính của principal, resource và context quyết định phạm vi cụ thể.

## 8. Attribute-Based Access Control (ABAC)

ABAC đánh giá quyền dựa trên thuộc tính của subject, resource, action và environment.

Ví dụ policy:

~~~text
permit read Orders
when
    subject.role == "analyst"
    and subject.tenantId == resource.tenantId
    and resource.classification <= subject.clearance
~~~

Thuộc tính có thể gồm:

- Subject: department, role, tenant, clearance, employment status.
- Resource: owner, tenant, classification, region, data category.
- Action: read, export, aggregate, update.
- Environment: thời gian, network zone, device trust, request purpose.

ABAC phù hợp khi quyền phụ thuộc vào nhiều yếu tố động. Ví dụ, analyst chỉ được đọc dữ liệu thuộc tenant của mình và chỉ được xem trường tài chính khi có mục đích báo cáo được phê duyệt.

### 8.1. Policy evaluation

Một policy engine có thể đánh giá:

~~~text
decision = policyEngine.evaluate(
    principal,
    action,
    resource,
    environment
)
~~~

Kết quả có thể là Permit, Deny hoặc NotApplicable. Hệ thống cần có quy tắc kết hợp nhiều policy, chẳng hạn deny-overrides hoặc permit-overrides. Với dữ liệu nhạy cảm, deny-overrides thường là lựa chọn dễ kiểm soát hơn khi có policy từ chối rõ ràng.

### 8.2. Thuộc tính phải có nguồn đáng tin cậy

ABAC chỉ an toàn khi thuộc tính được xác minh. Ví dụ tenantId lấy từ token đã xác thực hoặc identity service; classification lấy từ metadata do data owner quản lý; purpose có thể cần workflow phê duyệt.

Không nên cho client gửi clearance hoặc department tùy ý rồi dùng trực tiếp để quyết định quyền.

## 9. Capability-Based Access Control

Capability là quyền cụ thể được cấp cho một chủ thể hoặc tiến trình để thực hiện một thao tác trên một resource. Thay vì chỉ dựa trên role tổng quát, hệ thống truyền capability đã được giới hạn phạm vi.

Ví dụ:

~~~text
capability:
  action: read
  resource: Orders
  tenant: north-region
  fields:
    - orderId
    - status
    - total
  expiresAt: ...
~~~

Capability có thể được cấp cho một service hoặc query session. Nó cần được bảo vệ khỏi giả mạo, sao chép ngoài phạm vi hoặc sử dụng sau khi hết hạn.

Capability hữu ích khi:

- Một service chỉ cần quyền hẹp cho một tác vụ.
- Người dùng chia sẻ quyền truy cập có thời hạn.
- Query chạy trong môi trường plugin hoặc sandbox.
- Hệ thống cần hạn chế function được gọi.

Capability không thay thế authentication. Hệ thống vẫn cần xác định ai đang trình capability và kiểm tra tính hợp lệ, thời hạn, audience và phạm vi của nó.

## 10. Row-Level Security

Row-Level Security (RLS) giới hạn bản ghi mà caller được phép nhìn thấy. Cùng một query source có thể trả về các tập bản ghi khác nhau cho hai người dùng.

Ví dụ, policy yêu cầu mỗi người chỉ xem đơn hàng trong tenant của mình:

~~~text
policy Orders.read:
    rowFilter = Orders.tenantId == context.tenantId
~~~

Người dùng gửi:

~~~text
from Orders
select orderId, total
~~~

Engine thực thi tương đương:

~~~text
from Orders
where tenantId == authenticatedContext.tenantId
select orderId, total
~~~

Filter bảo mật được thêm ở phía server. Caller không được xóa hoặc ghi đè filter này bằng cách sửa query.

### 10.1. Policy filter và query filter

Query filter là điều kiện do người dùng yêu cầu; policy filter là điều kiện bắt buộc do hệ thống áp dụng. Hai loại cần được giữ riêng trong query plan để optimizer không vô tình loại bỏ policy.

Ví dụ:

~~~text
userPredicate:
    status == APPROVED

securityPredicate:
    tenantId == context.tenantId

effectivePredicate:
    status == APPROVED
    and tenantId == context.tenantId
~~~

Engine có thể tối ưu biểu thức kết hợp nhưng phải bảo đảm security predicate luôn được áp dụng trên mọi đường thực thi.

### 10.2. Filter ở database

Nếu backend hỗ trợ RLS, có thể thực thi policy ngay tại database. Cách này tạo thêm lớp bảo vệ nếu ứng dụng vô tình bỏ sót filter. Tuy nhiên, phải bảo đảm database session nhận đúng identity context và không thể bị caller giả mạo.

Nếu engine tự lọc sau khi tải dữ liệu, nó có thể đọc quá nhiều dữ liệu nhạy cảm vào bộ nhớ ứng dụng. Ưu tiên push policy xuống nguồn dữ liệu tin cậy khi backend hỗ trợ semantics tương đương.

## 11. Column-Level Security và Field Masking

Column-Level Security giới hạn field mà người dùng có thể đọc. Một principal có thể được phép xem orderId và status nhưng không được xem customer.email hoặc paymentCard.

Ví dụ:

~~~text
Role Support:
  allow fields:
    - orderId
    - status
    - createdAt

  deny fields:
    - customer.email
    - payment.cardNumber
~~~

Engine cần kiểm tra field ở nhiều vị trí:

- Projection: field có được trả về không?
- Filter: caller có được dùng field nhạy cảm để suy luận dữ liệu không?
- Join: field có được dùng để liên kết source không?
- Grouping: aggregation có làm lộ thông tin qua nhóm nhỏ không?
- Ordering: thứ tự có tiết lộ giá trị của field bị cấm không?

Chỉ chặn field trong SELECT là chưa đủ. Nếu người dùng không được đọc salary nhưng có thể lọc salary > 100000 rồi quan sát số dòng, họ vẫn có thể suy luận thông tin.

### 11.1. Masking

Masking thay đổi cách hiển thị giá trị:

~~~text
customer.email = "a***@example.com"
~~~

Masking có thể được áp dụng cho output hoặc qua một view an toàn. Cần xác định field đã mask có được dùng trong filter, sort hoặc join không. Nếu vẫn cho phép các thao tác đó, kết quả có thể tiết lộ thông tin gốc.

### 11.2. Aggregation và inference

Một người dùng có thể không được xem bản ghi cá nhân nhưng vẫn được phép xem thống kê. Tuy nhiên, nhóm có một phần tử hoặc các truy vấn khác biệt nhỏ có thể làm lộ dữ liệu cá nhân.

Có thể áp dụng:

- Minimum group size.
- Query rate limits.
- Suppression cho nhóm nhỏ.
- Differential privacy nếu use case cần bảo vệ thống kê.
- Kiểm soát các truy vấn liên tiếp có thể kết hợp để suy luận.

Không nên coi aggregation tự động là an toàn chỉ vì output không chứa trực tiếp tên người.

## 12. Tenant Isolation

Trong hệ thống multi-tenant, dữ liệu của mỗi khách hàng hoặc tổ chức phải được cô lập. Tenant identity nên đến từ authentication context đáng tin cậy và được áp dụng cho mọi truy vấn liên quan.

Ví dụ:

~~~text
context.tenantId = "tenant-A"

from Orders
where status == APPROVED
~~~

Query engine tự áp dụng tenant constraint. Người dùng không thể thay tenant bằng cách thêm điều kiện tenantId khác vào query.

### 12.1. Các lớp cô lập

Tenant isolation có thể được thực hiện bằng:

- Database hoặc schema riêng cho từng tenant.
- Partition hoặc collection riêng.
- Shared table với tenant key và RLS.
- Service layer có policy enforcement.
- Kết hợp nhiều lớp.

Mỗi cách có chi phí và đặc tính vận hành khác nhau. Shared table tiết kiệm tài nguyên nhưng cần bảo đảm mọi truy vấn và index đều tuân thủ tenant boundary. Database riêng tạo ranh giới rõ hơn nhưng tăng chi phí quản lý.

### 12.2. Tenant context phải đi xuyên suốt

Khi query được chia thành nhiều bước hoặc gọi nhiều service, tenant context phải được truyền một cách xác thực. Một bước trung gian không được vô tình bỏ context rồi truy vấn nguồn ở phạm vi toàn hệ thống.

Test cần kiểm tra cả join, subquery, view, export, cache và background execution để tránh rò dữ liệu giữa tenant.

## 13. Quyền trên function và operator

Query DSL có thể cho phép gọi function tích hợp:

~~~text
from Orders
where geoDistance(customer.location, store.location) < kilometers(10)
select orderId
~~~

Function có thể:

- Chỉ tính toán thuần.
- Đọc dữ liệu từ nguồn khác.
- Gọi service bên ngoài.
- Tạo bản ghi hoặc gửi thông báo.
- Truy cập file hoặc tài nguyên hệ thống.

Các function có side effect hoặc truy cập dữ liệu cần được kiểm soát riêng. Không nên cho phép query gọi mọi method có sẵn trong host application.

### 13.1. Function registry

Một function registry có thể mô tả:

~~~text
Function: requireManualReview
  signature: (OrderId) -> ReviewRequest
  capability: review:create
  effect: external-write
  allowedRoles:
    - operator
    - workflow-service
~~~

Khi compile hoặc execute, engine kiểm tra function có được export và caller có capability tương ứng hay không.

### 13.2. Pure function và side effect

Pure function chỉ phụ thuộc đầu vào và không thay đổi trạng thái bên ngoài. Chúng thường dễ tối ưu và cache hơn. Function có side effect cần execution policy, audit và có thể cần xác nhận hoặc idempotency.

Nếu query DSL được thiết kế cho việc đọc dữ liệu, nên tách thao tác ghi hoặc hành động bên ngoài thành command DSL hoặc API riêng, hoặc yêu cầu capability rõ ràng cho từng action.

## 14. Parameter Binding và ngăn chặn injection

Query DSL không nên tạo source bằng cách nối chuỗi input:

~~~text
query = "from Users where name == '" + userInput + "'"
~~~

Input có thể chứa dấu nháy hoặc đoạn cú pháp làm thay đổi query. Thay vào đó, dùng parameter binding:

~~~text
from Users
where name == :name
~~~

Engine parse cấu trúc query một lần và truyền giá trị name qua parameter object. Backend có thể dùng prepared statement hoặc API tham số tương ứng.

Parameter binding giúp:

- Tách cú pháp khỏi dữ liệu.
- Giảm nguy cơ injection.
- Hỗ trợ cache query plan.
- Giữ kiểu dữ liệu rõ ràng.
- Tránh lỗi escaping.

Parameter không thể thay thế tên source, tên field hoặc keyword nếu grammar không cho phép. Nếu cần chọn cột động, engine phải resolve identifier qua allowlist và kiểm tra quyền, không ghép một chuỗi tùy ý vào query.

## 15. Kiểm soát truy cập schema và metadata

Metadata cũng có thể nhạy cảm. Tên bảng, field, quan hệ và mô tả schema có thể tiết lộ cấu trúc nghiệp vụ hoặc hệ thống.

Language server, schema browser và completion provider nên áp dụng quyền discover:

- Source nào được liệt kê?
- Field nào được hiển thị?
- Có được xem comment hoặc business description không?
- Có được xem relationship hoặc foreign key không?
- Có được tìm symbol trong module private không?

Một editor không nên nhận toàn bộ schema nhạy cảm rồi chỉ ẩn bớt trên UI. Nếu metadata không được phép tiết lộ, server không nên gửi nó tới client.

Khi completion chỉ hiển thị một phần schema, diagnostics cũng cần tránh tiết lộ tên field bị cấm qua gợi ý hoặc thông báo lỗi.

## 16. Query planning và enforcement point

Quyền cần được kiểm tra ở nơi có thể kiểm soát thực thi. Một pipeline minh họa:

~~~mermaid
flowchart TD
    A["Authenticated request"] --> B["Parse query"]
    B --> C["Resolve schema and symbols"]
    C --> D["Authorize sources and actions"]
    D --> E["Inject row and field policies"]
    E --> F["Build logical plan"]
    F --> G["Check cost and capabilities"]
    G --> H["Optimize with security constraints"]
    H --> I["Execute at trusted backend"]
    I --> J["Mask and validate result"]
    J --> K["Audit decision and outcome"]
~~~

Các điểm kiểm soát:

1. Trước planning: xác minh source, action và field.
2. Trong planning: thêm policy predicate và capability constraint.
3. Trước execution: kiểm tra cost, quota và function permission.
4. Tại backend: áp dụng RLS hoặc policy tương đương nếu có.
5. Sau execution: mask output, giới hạn export và ghi audit.

Không nên chỉ kiểm tra quyền một lần ở UI hoặc lúc parse. Quyết định cần gắn với execution context và được bảo vệ trong suốt quá trình thực thi.

### 16.1. Policy-aware optimizer

Optimizer có thể đẩy filter hoặc đổi thứ tự join. Nó phải giữ nguyên security predicate và không tạo plan có thể bỏ qua policy.

Một lựa chọn là đánh dấu policy node trong logical plan và yêu cầu mọi rewrite bảo toàn node đó. Một lựa chọn khác là biên dịch policy thành view hoặc source đã giới hạn quyền ở backend.

### 16.2. Time-of-check và time-of-use

Quyền có thể thay đổi giữa lúc kiểm tra và lúc query thực thi. Với truy vấn dài hoặc job chạy nền, hệ thống cần quyết định policy được snapshot tại thời điểm bắt đầu hay được kiểm tra lại theo thời gian.

Đối với thao tác nhạy cảm, có thể cần kiểm tra lại quyền ngay trước side effect hoặc export. Token và capability cần có thời hạn phù hợp.

## 17. Query cost, quota và resource limits

Quyền truy cập dữ liệu không chỉ là được đọc hay không. Một người dùng được phép đọc source vẫn có thể gửi query tiêu tốn quá nhiều tài nguyên.

Các giới hạn thường gặp:

- Maximum execution time.
- Maximum rows scanned.
- Maximum result rows.
- Maximum bytes returned.
- Maximum joins hoặc subquery depth.
- Concurrent query limit.
- Per-user hoặc per-tenant quota.
- Rate limit theo API.
- Memory và CPU budget.

Ví dụ:

~~~text
queryOptions {
    timeout: 10s
    maxRows: 5000
    maxBytes: 20MB
}
~~~

Các giá trị phải được engine thực sự thực thi. Không nên chỉ ghi trong query option mà không có enforcement ở runtime.

### 17.1. Cost-based authorization

Policy có thể cho phép một query nhỏ nhưng yêu cầu phê duyệt hoặc từ chối query có estimated cost vượt ngưỡng. Ví dụ, analyst được phép đọc tối đa một khoảng thời gian hoặc số partition nhất định.

Cost estimate không hoàn hảo, vì vậy vẫn cần runtime guard để dừng query nếu thực tế vượt ngân sách.

### 17.2. Cancellation

Khi client đóng trang hoặc hủy request, engine nên hỗ trợ cancel query và giải phóng tài nguyên. Nếu query tiếp tục chạy sau khi client đã rời đi, nó có thể tiêu tốn quota và gây ảnh hưởng người dùng khác.

## 18. Auditing và accountability

Audit ghi nhận ai đã yêu cầu truy vấn, truy vấn loại nào, policy nào được áp dụng và kết quả quyết định ra sao.

Một audit event có thể chứa:

~~~json
{
  "eventType": "query.authorization",
  "requestId": "req-812",
  "principalId": "user-104",
  "tenantId": "north-region",
  "action": "read",
  "resource": "Orders",
  "decision": "PERMIT",
  "policyId": "orders-tenant-read",
  "timestamp": "2026-11-15T03:00:00Z"
}
~~~

Thông tin audit có thể gồm:

- Principal và tenant.
- Resource và action.
- Policy version.
- Decision và lý do.
- Query ID hoặc normalized query hash.
- Thời gian, số dòng và bytes trả về.
- Kết quả thực thi hoặc lỗi.
- Request/correlation ID.

### 18.1. Không ghi dữ liệu nhạy cảm không cần thiết

Audit log không nên lưu toàn bộ kết quả query hoặc literal nhạy cảm nếu không có nhu cầu và kiểm soát phù hợp. Có thể lưu query template hoặc hash cùng metadata đã lọc.

Audit store cần có quyền truy cập riêng, retention policy và khả năng phát hiện sửa đổi nếu dùng cho điều tra hoặc tuân thủ.

### 18.2. Audit cả deny

Các lần từ chối có thể cho thấy cấu hình sai hoặc hành vi dò tìm dữ liệu. Nên ghi nhận deny event với thông tin đủ để điều tra, nhưng tránh trả cho caller quá nhiều chi tiết về resource mà họ không được phép biết.

## 19. Policy administration và quản lý thay đổi

Policy có thể được quản lý trong file cấu hình, policy service hoặc một DSL riêng. Ví dụ:

~~~text
policy orders-read {
    allow action read on Orders
    when principal.role in ["analyst", "operator"]
      and principal.tenantId == resource.tenantId
}
~~~

Policy language cần có semantics rõ, parser và validator riêng nếu được viết như DSL. Cần tránh để policy tự cấp quyền cho chính nó hoặc cho phép người không có quyền sửa policy.

### 19.1. Separation of duties

Người viết query không nhất thiết là người quản trị policy. Người quản lý role không nhất thiết có quyền đọc mọi dữ liệu. Tách vai trò giúp giảm nguy cơ một cá nhân vừa thay đổi policy vừa tự truy cập dữ liệu ngoài phạm vi.

### 19.2. Versioning policy

Policy cần có version, owner, trạng thái và lịch sử thay đổi. Một query audit nên cho biết policy version nào đã quyết định permit hoặc deny.

### 19.3. Policy rollout

Thay đổi policy quan trọng có thể được thử ở chế độ shadow hoặc dry-run:

- Đánh giá policy mới nhưng chưa áp dụng.
- So sánh quyết định mới và cũ.
- Xem số request bị ảnh hưởng.
- Sau review mới chuyển sang enforcement.

Điều này giúp phát hiện policy quá rộng hoặc quá chặt trước khi ảnh hưởng người dùng.

## 20. Fail-open và fail-closed

Nếu policy service không khả dụng, hệ thống phải quyết định có tiếp tục query hay không.

- **Fail-closed:** không có quyết định hợp lệ thì từ chối truy cập.
- **Fail-open:** cho phép truy cập khi không thể kiểm tra policy.

Với dữ liệu nhạy cảm, fail-closed thường an toàn hơn. Fail-open có thể được cân nhắc cho một số dữ liệu ít rủi ro hoặc chức năng không nhạy cảm, nhưng cần policy được phê duyệt rõ ràng.

Không nên biến timeout của authorization service thành quyền truy cập mặc định. Cần timeout, retry có giới hạn, circuit breaker và diagnostic riêng cho lỗi policy service.

## 21. Cache và quyền truy cập

Cache có thể làm query nhanh hơn nhưng cũng tạo rủi ro rò dữ liệu nếu key không chứa đủ context.

Cache key có thể cần:

- Query plan hoặc normalized query.
- Parameter values hoặc hash an toàn.
- Principal hoặc security scope.
- Tenant ID.
- Policy version.
- Schema version.
- Data snapshot/version.

Nếu cache kết quả của tenant A rồi trả cho tenant B chỉ vì query giống nhau, dữ liệu sẽ bị lộ. Một lựa chọn là cache dữ liệu đã phân vùng theo tenant; lựa chọn khác là cache kết quả chỉ trong security context tương ứng.

Khi policy thay đổi, cache có thể cần invalidation. Nếu policy version không được tính vào key, kết quả đã được cho phép theo policy cũ có thể tiếp tục được trả sau khi quyền bị thu hồi.

## 22. Quyền truy cập với subquery, view và stored query

Query DSL thường hỗ trợ query lồng, view hoặc named query:

~~~text
view ActiveOrders {
    from Orders
    where status == APPROVED
}

from ActiveOrders
select orderId, total
~~~

Engine cần xác định quyền được đánh giá theo caller hiện tại hay theo owner của view.

Hai mô hình phổ biến:

- **Invoker rights:** query chạy với quyền của người gọi.
- **Definer rights:** query chạy với quyền của chủ sở hữu hoặc service đã định nghĩa view.

Definer rights có thể hữu ích cho view được kiểm soát, nhưng cần giới hạn rõ để tránh tạo đường vòng vượt quyền. Một view không nên vô tình cấp quyền đọc source mà caller không được phép truy cập nếu policy không chủ đích cho phép.

Subquery cũng không được bỏ qua row policy của source bên trong. Policy cần được áp dụng xuyên suốt mọi cấp query.

## 23. Export và chia sẻ kết quả

Quyền xem kết quả trong editor không tự động bao gồm quyền export hoặc chia sẻ dữ liệu. Export có thể làm dữ liệu rời khỏi hệ thống kiểm soát ban đầu.

Có thể tách action:

- query:execute.
- result:view.
- result:download.
- result:share.
- result:schedule.
- result:publish.

Policy export có thể giới hạn:

- Số dòng hoặc kích thước.
- Định dạng file.
- Trường nhạy cảm.
- Đích lưu trữ.
- Thời hạn link chia sẻ.
- Người nhận.
- Yêu cầu watermark hoặc audit.

Nếu kết quả được lưu trong object storage, access control cần áp dụng cả khi tải file trực tiếp, không chỉ ở endpoint tạo export.

## 24. Kiểm thử access control

Kiểm thử cần bao gồm cả trường hợp được phép và bị từ chối. Chỉ test happy path sẽ bỏ sót lỗi rò dữ liệu.

### 24.1. Authentication test

Kiểm tra request không có identity, token hết hạn, token sai audience hoặc principal không hợp lệ bị xử lý đúng.

### 24.2. Source authorization test

Kiểm tra role hoặc principal được phép đọc source nào, không được đọc source nào và không thể truy cập bằng alias hoặc subquery để né policy.

### 24.3. Row-level test

Tạo dữ liệu của nhiều tenant. Chạy cùng query bằng hai principal và xác nhận mỗi principal chỉ thấy record trong phạm vi của mình.

### 24.4. Column-level test

Kiểm tra field bị cấm không thể lấy qua projection, filter, join, group, sort hoặc aggregate nếu policy không cho phép suy luận.

### 24.5. Function capability test

Kiểm tra function thuần và function có side effect. Principal thiếu capability không được gọi action nhạy cảm.

### 24.6. Injection test

Thử parameter chứa dấu nháy, delimiter và đoạn cú pháp. Xác nhận giá trị không thể thay đổi cấu trúc query.

### 24.7. Tenant isolation test

Kiểm tra join, view, subquery, export, cache và background job không làm lộ dữ liệu giữa tenant.

### 24.8. Policy failure test

Mô phỏng policy service timeout hoặc lỗi. Xác nhận fail-open/fail-closed đúng policy đã chọn.

### 24.9. Audit test

Xác nhận cả permit và deny được ghi với principal, resource, policy version và request ID; đồng thời không ghi dữ liệu nhạy cảm ngoài policy.

### 24.10. Concurrency và revocation test

Thu hồi quyền trong lúc query dài hoặc giữa lúc tạo export. Xác nhận hệ thống áp dụng semantics đã công bố: snapshot quyền, kiểm tra lại hoặc hủy tác vụ.

## 25. Những lỗi thiết kế thường gặp

### Chỉ ẩn field ở giao diện

Client vẫn có thể gửi query trực tiếp tới backend. Thực thi policy ở server và data source.

### Tin tenant hoặc role do client gửi

Người dùng có thể giả mạo context. Lấy identity và claim từ authentication provider đáng tin cậy.

### Chỉ kiểm tra field trong projection

Field cấm vẫn có thể bị suy luận qua filter, sort hoặc aggregate. Kiểm tra mọi cách sử dụng field.

### Để query tự thêm security filter

Caller có thể xóa hoặc sửa điều kiện. Inject policy predicate ở tầng server và bảo vệ nó qua optimizer.

### Bỏ policy trong subquery hoặc view

Query lồng có thể trở thành đường vòng. Áp dụng policy trên mọi source node.

### Cache không phân biệt tenant

Kết quả của người dùng này có thể được trả cho người dùng khác. Phân vùng cache theo security context và policy version.

### Cho phép function tùy ý

Query có thể gọi API hoặc side effect không được kiểm soát. Dùng function registry và capability allowlist.

### Fail-open khi policy service lỗi

Sự cố hạ tầng trở thành quyền truy cập ngoài ý muốn. Chọn fail behavior theo mức độ nhạy cảm và công bố rõ.

### Audit ghi quá nhiều dữ liệu

Log có thể trở thành nguồn rò rỉ mới. Ghi metadata cần thiết và mask parameter/result nhạy cảm.

### Không kiểm thử đường vòng

Test chỉ trên query đơn giản bỏ qua join, alias, view, export và cache. Kiểm thử toàn bộ execution path.

## 26. Quy trình thiết kế access control cho query DSL

Khi triển khai kiểm soát quyền truy cập, có thể thực hiện theo trình tự:

1. **Xác định principal.** Người dùng, service hoặc workload được xác thực bằng cách nào?
2. **Lập danh mục resource.** Source, field, view, function và artifact nào cần bảo vệ?
3. **Định nghĩa action.** Discover, read, filter, export, execute, subscribe và administer có quyền riêng nào?
4. **Chọn mô hình policy.** RBAC, ABAC, capability hoặc kết hợp.
5. **Xác định context đáng tin cậy.** Tenant, role, clearance và purpose đến từ đâu?
6. **Thiết kế row và field policy.** Quy định filter, masking và inference protection.
7. **Đánh dấu function effect.** Phân biệt pure function với thao tác có side effect.
8. **Chọn enforcement point.** Query planner, runtime, backend RLS và output layer.
9. **Đặt resource limits.** Timeout, quota, scan budget và result size.
10. **Thiết kế audit.** Ghi permit/deny, policy version và execution metadata.
11. **Quản lý cache và revocation.** Phân vùng theo security context và xử lý thay đổi quyền.
12. **Kiểm thử âm và dương.** Bao gồm tenant, subquery, export, cache và policy failure.

Policy nên được triển khai theo nguyên tắc least privilege: cấp đúng quyền cần thiết cho công việc và giảm phạm vi khi không còn cần.

## 27. Ví dụ end-to-end: analyst truy vấn đơn hàng

Giả sử một analyst chỉ được đọc đơn hàng trong tenant của mình, xem các field orderId, status và total, không được xem email khách hàng và chỉ được export tối đa 5.000 dòng.

Query người dùng viết:

~~~text
from Orders
where status == APPROVED
select orderId, customerEmail, total
order by total descending
limit 10000
~~~

Execution context từ identity provider:

~~~text
principalId: user-104
tenantId: tenant-A
roles: [analyst]
~~~

Policy:

~~~text
allow read Orders
when role == analyst

rowFilter:
  Orders.tenantId == context.tenantId

allowedFields:
  orderId, status, total

maxRows:
  5000

export:
  denied
~~~

Query engine xử lý:

1. Xác thực principal và tạo context.
2. Parse query và resolve Orders.
3. Kiểm tra action read trên source.
4. Phát hiện customerEmail không nằm trong allowedFields và từ chối query hoặc báo field không được phép theo policy.
5. Nếu caller sửa query để bỏ customerEmail, engine vẫn thêm tenant row filter.
6. Giới hạn limit hiệu lực tối đa 5.000 dòng.
7. Tạo plan có policy predicate được bảo vệ.
8. Thực thi ở backend có RLS nếu khả dụng.
9. Ghi audit event với principal, policy version và kết quả.

Query sau khi người dùng sửa:

~~~text
from Orders
where status == APPROVED
select orderId, status, total
order by total descending
limit 10000
~~~

Query vẫn chỉ trả dữ liệu tenant-A. Giới hạn policy khiến số dòng tối đa không vượt quá 5.000. Người dùng có thể xem kết quả trong phạm vi quyền nhưng yêu cầu export vẫn bị từ chối.

Ví dụ này cho thấy quyền truy cập được áp dụng xuyên suốt source, field, row, result size và action, không phụ thuộc vào việc người dùng có tự viết filter hay không.

## 28. Kết luận

Kiểm soát quyền truy cập trong DSL truy vấn xác định principal nào được khám phá, đọc, lọc, kết hợp, export hoặc thực thi trên từng resource. Một thiết kế an toàn kết hợp authentication context đáng tin cậy với authorization policy theo source, action, row, field, function và tenant.

RBAC phù hợp với nhóm vai trò ổn định; ABAC biểu đạt quyền phụ thuộc thuộc tính; capability giới hạn quyền cho một tác vụ cụ thể. Các mô hình có thể kết hợp với row-level security, column-level security, masking, quota và audit. Policy cần được áp dụng ở phía server và backend tin cậy, bảo toàn qua subquery, view, optimizer, cache và export.

Khi xây dựng, hãy áp dụng least privilege, parameter binding, policy-aware planning, resource limits và audit có kiểm soát. Kiểm thử cả trường hợp permit lẫn deny, đặc biệt là tenant isolation, field inference, cache và function side effect. Nhờ vậy, query DSL có thể cung cấp khả năng truy vấn linh hoạt mà vẫn giữ dữ liệu và tài nguyên trong phạm vi được phép.

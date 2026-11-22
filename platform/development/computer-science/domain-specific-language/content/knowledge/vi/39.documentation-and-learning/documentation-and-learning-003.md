# Ví dụ theo kịch bản

Một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL) được tạo ra để diễn đạt một nhóm vấn đề trong một miền cụ thể. Người học có thể hiểu cú pháp riêng lẻ, nhưng để sử dụng DSL hiệu quả cần biết cách kết hợp type, expression, rule, query, workflow, event và API thành một giải pháp hoàn chỉnh. **Ví dụ theo kịch bản** giúp kết nối những khái niệm đó với nhu cầu thực tế: bắt đầu từ yêu cầu nghiệp vụ, mô hình hóa dữ liệu, viết chương trình DSL, xác định cách thực thi và kiểm tra kết quả.

Một kịch bản tốt không chỉ đưa ra đoạn mã mẫu. Nó giải thích bối cảnh, dữ liệu đầu vào, quy tắc cần biểu đạt, quyết định thiết kế, kết quả mong đợi và các trường hợp biên. Người học cần thấy vì sao một cấu trúc DSL phù hợp với vấn đề, điều gì xảy ra khi dữ liệu thay đổi và cách kiểm thử để tránh hành vi ngoài dự kiến.

Các ví dụ trong bài sử dụng cú pháp minh họa. Một DSL thực tế có thể dùng từ khóa, kiểu dữ liệu hoặc cách khai báo khác. Mục tiêu là học cách phân tích vấn đề và ánh xạ nó sang các thành phần của DSL, không ghi nhớ máy móc một cú pháp duy nhất.

Bài học trình bày phương pháp đọc và xây dựng kịch bản, sau đó đi qua các tình huống về định giá, validation, truy vấn và báo cáo, workflow phê duyệt, xử lý event, policy truy cập, sinh tài liệu và chuyển đổi dữ liệu. Cuối cùng là cách kiểm thử, mở rộng và tự xây dựng kịch bản mới.

## 1. Cách tiếp cận một kịch bản DSL

Trước khi viết DSL, hãy chuyển yêu cầu tự nhiên thành một mô hình có thể kiểm tra.

### 1.1. Đọc yêu cầu nghiệp vụ

Một yêu cầu thường chứa:
- Actor: ai thực hiện hoặc sử dụng chức năng.
- Input: dữ liệu đầu vào.
- Rule: điều kiện hoặc công thức.
- Action: việc hệ thống cần thực hiện.
- Output: kết quả cần tạo.
- Constraint: giới hạn và điều kiện hợp lệ.
- Exception: trường hợp từ chối hoặc lỗi.
- Audit: thông tin cần lưu lại.

Ví dụ yêu cầu “khách hàng hạng Gold được giảm 10% cho đơn hàng từ 500.000 đồng, nhưng không áp dụng cho sản phẩm đang giảm giá” có thể phân tích:

| Thành phần | Nội dung |
| --- | --- |
| Actor | Hệ thống tính giá |
| Input | Hạng khách hàng, tổng tiền, danh sách sản phẩm |
| Rule | Gold, tổng tiền đạt ngưỡng, không có sản phẩm đã giảm |
| Action | Tính discount |
| Output | Số tiền giảm và tổng sau giảm |
| Constraint | Không giảm vượt tổng tiền |
| Exception | Input thiếu hoặc số tiền âm |

### 1.2. Xác định mô hình dữ liệu

Không bắt đầu từ cú pháp. Hãy xác định entity, record, enum và kiểu dữ liệu cần dùng.

~~~text
enum CustomerTier {
  STANDARD
  SILVER
  GOLD
}

record OrderItem {
  productId: ProductId
  quantity: Integer
  unitPrice: Decimal
  alreadyDiscounted: Boolean
}

record Order {
  id: OrderId
  customerTier: CustomerTier
  items: List<OrderItem>
}
~~~

Mô hình dữ liệu giúp type checker kiểm tra field và expression, đồng thời làm rõ các giá trị có thể null hoặc nằm trong miền nào.

### 1.3. Tách điều kiện, phép tính và hành động

Một kịch bản có thể có ba nhóm logic:
- Điều kiện quyết định một rule có áp dụng hay không.
- Phép tính tạo ra giá trị.
- Hành động làm thay đổi hệ thống hoặc gọi service.

Nếu DSL hỗ trợ expression thuần, hãy dùng expression cho điều kiện và phép tính. Side effect nên đi qua action hoặc capability được kiểm soát.

### 1.4. Xác định kết quả mong đợi

Ví dụ cần có input cụ thể và output cụ thể. Nếu chỉ viết một đoạn DSL mà không cho biết kết quả, người học khó biết chương trình có hoạt động đúng không.

### 1.5. Liệt kê trường hợp biên

Ít nhất hãy xem xét:
- Input rỗng.
- Giá trị null.
- Giá trị bằng ngưỡng.
- Giá trị ngay dưới và ngay trên ngưỡng.
- Duplicate.
- Sai kiểu.
- Quyền không đủ.
- Timeout hoặc dependency lỗi.

### 1.6. Vòng đời thực thi

Một kịch bản thường đi qua:

~~~text
Requirement
    |
    v
Domain Model
    |
    v
DSL Source
    |
    v
Parse and Type Check
    |
    v
Validate
    |
    v
Execute
    |
    v
Expected Result
    |
    v
Tests and Diagnostics
~~~

Việc hiểu pipeline giúp phân biệt lỗi cú pháp, lỗi kiểu, lỗi validation và lỗi runtime.

## 2. Kịch bản 1: Tính giá và giảm giá đơn hàng

Kịch bản định giá phù hợp để học record, enum, expression, điều kiện, hàm và kiểm thử boundary value.

### 2.1. Yêu cầu

Một cửa hàng có chính sách:
- Khách hàng GOLD được giảm 10%.
- Khách hàng SILVER được giảm 5%.
- STANDARD không được giảm theo hạng.
- Đơn từ 1.000.000 đồng được giảm thêm 3%.
- Sản phẩm đã có khuyến mại không được tính vào ưu đãi theo hạng.
- Tổng giảm không vượt tổng giá trị đơn.

### 2.2. Mô hình dữ liệu

~~~text
enum CustomerTier {
  STANDARD
  SILVER
  GOLD
}

record Item {
  sku: String
  quantity: Integer
  unitPrice: Decimal
  promotionApplied: Boolean
}

record Order {
  id: String
  tier: CustomerTier
  items: List<Item>
}
~~~

### 2.3. Hàm tính tổng tiền

~~~text
function lineTotal(item: Item): Decimal {
  return item.quantity * item.unitPrice
}

function orderTotal(order: Order): Decimal {
  return order.items.sum(item => lineTotal(item))
}
~~~

Nếu DSL không có lambda hoặc aggregate, có thể dùng cú pháp collection operation khác. Điều quan trọng là tổng tiền được tính từ quantity và unitPrice theo kiểu Decimal.

### 2.4. Xác định tỷ lệ giảm theo hạng

~~~text
function tierRate(tier: CustomerTier): Decimal {
  if tier == GOLD {
    return 0.10
  }

  if tier == SILVER {
    return 0.05
  }

  return 0
}
~~~

Hàm này là expression thuần: cùng input sẽ luôn trả cùng kết quả.

### 2.5. Loại sản phẩm đã có khuyến mại

~~~text
function eligibleSubtotal(order: Order): Decimal {
  return order.items
    .filter(item => not item.promotionApplied)
    .sum(item => lineTotal(item))
}
~~~

Chỉ phần subtotal đủ điều kiện được dùng để tính ưu đãi theo hạng. Điều này tránh áp dụng hai chương trình lên cùng một sản phẩm nếu chính sách không cho phép.

### 2.6. Tính kết quả

~~~text
record PriceResult {
  subtotal: Decimal
  tierDiscount: Decimal
  orderDiscount: Decimal
  totalDiscount: Decimal
  finalTotal: Decimal
}

function calculatePrice(order: Order): PriceResult {
  let subtotal = orderTotal(order)
  let eligible = eligibleSubtotal(order)

  let tierDiscount = eligible * tierRate(order.tier)
  let orderRate = if subtotal >= 1000000 then 0.03 else 0
  let orderDiscount = subtotal * orderRate

  let discount = min(subtotal, tierDiscount + orderDiscount)

  return PriceResult {
    subtotal: subtotal,
    tierDiscount: tierDiscount,
    orderDiscount: orderDiscount,
    totalDiscount: discount,
    finalTotal: subtotal - discount
  }
}
~~~

### 2.7. Ví dụ đầu vào

~~~text
Order {
  id: "ORD-1001",
  tier: GOLD,
  items: [
    Item("A", 2, 200000, false),
    Item("B", 1, 500000, true)
  ]
}
~~~

Tổng trước giảm là 900.000 đồng. Subtotal đủ điều kiện theo hạng là 400.000 đồng. Vì tổng đơn chưa đạt 1.000.000 đồng, ưu đãi theo hạng là 40.000 đồng và ưu đãi theo ngưỡng đơn hàng là 0.

Kết quả:

~~~text
PriceResult {
  subtotal: 900000,
  tierDiscount: 40000,
  orderDiscount: 0,
  totalDiscount: 40000,
  finalTotal: 860000
}
~~~

### 2.8. Trường hợp biên

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Order không có item | Tổng tiền bằng 0 |
| Quantity bằng 0 | Bị validation từ chối hoặc line total bằng 0 theo policy |
| Unit price âm | Input không hợp lệ |
| Tổng tiền đúng 1.000.000 | Được áp dụng ngưỡng nếu điều kiện là lớn hơn hoặc bằng |
| Tất cả item đã khuyến mại | Tier discount bằng 0 |
| Discount lớn hơn subtotal | Final total không âm |

### 2.9. Điều học được

Kịch bản này kết hợp type, record, enum, function, filter, aggregate và conditional expression. Nó cũng cho thấy chính sách nghiệp vụ cần được diễn đạt tách bạch: subtotal đủ điều kiện khác tổng đơn, và mỗi loại discount có thể dùng một cơ sở tính khác nhau.

## 3. Kịch bản 2: Validation hồ sơ đăng ký

Validation DSL thường dùng để kiểm tra dữ liệu trước khi lưu hoặc chuyển sang bước tiếp theo.

### 3.1. Yêu cầu

Một hồ sơ đăng ký doanh nghiệp cần:
- Có mã số thuế.
- Có tên doanh nghiệp.
- Email liên hệ hợp lệ.
- Ngày thành lập không ở tương lai.
- Vốn điều lệ lớn hơn 0.
- Nếu loại hình là COMPANY thì phải có người đại diện.

Một số lỗi là bắt buộc phải sửa; một số cảnh báo chỉ yêu cầu người dùng xác nhận.

### 3.2. Mô hình dữ liệu

~~~text
enum BusinessType {
  COMPANY
  HOUSEHOLD
}

record Registration {
  taxCode: String?
  legalName: String?
  contactEmail: String?
  establishedDate: Date?
  charterCapital: Decimal?
  businessType: BusinessType
  representativeName: String?
}
~~~

Dấu hỏi sau kiểu thể hiện field có thể null trong cú pháp minh họa.

### 3.3. Khai báo rule

~~~text
rule TAX_CODE_REQUIRED {
  when registration.taxCode == null
  severity ERROR
  message "Mã số thuế là bắt buộc"
}

rule LEGAL_NAME_REQUIRED {
  when registration.legalName == null
    or trim(registration.legalName) == ""
  severity ERROR
  message "Tên doanh nghiệp không được để trống"
}

rule CAPITAL_POSITIVE {
  when registration.charterCapital == null
    or registration.charterCapital <= 0
  severity ERROR
  message "Vốn điều lệ phải lớn hơn 0"
}
~~~

### 3.4. Rule có điều kiện

~~~text
rule REPRESENTATIVE_REQUIRED {
  when registration.businessType == COMPANY
    and registration.representativeName == null
  severity ERROR
  message "Doanh nghiệp cần khai báo người đại diện"
}
~~~

Rule chỉ áp dụng khi loại hình là COMPANY. Với HOUSEHOLD, điều kiện này không tạo lỗi.

### 3.5. Validation theo thời gian

~~~text
rule ESTABLISHED_DATE_NOT_FUTURE {
  when registration.establishedDate > executionContext.today
  severity ERROR
  message "Ngày thành lập không thể ở tương lai"
}
~~~

Dùng execution context để truyền ngày hiện tại giúp test có thể tái lập. Nếu rule tự đọc đồng hồ hệ thống, cùng input có thể cho kết quả khác ở các thời điểm khác nhau.

### 3.6. Tập hợp kết quả validation

~~~text
record ValidationIssue {
  code: String
  severity: Severity
  message: String
  field: String?
}

record ValidationResult {
  valid: Boolean
  issues: List<ValidationIssue>
}
~~~

Một validator có thể chạy toàn bộ rule và trả nhiều issue thay vì dừng ở lỗi đầu tiên.

### 3.7. Ví dụ kết quả

Với hồ sơ thiếu taxCode, email sai định dạng và không có representativeName dù loại hình là COMPANY, kết quả có thể là:

~~~text
ValidationResult {
  valid: false,
  issues: [
    { code: "TAX_CODE_REQUIRED", severity: ERROR },
    { code: "EMAIL_INVALID", severity: ERROR },
    { code: "REPRESENTATIVE_REQUIRED", severity: ERROR }
  ]
}
~~~

### 3.8. Error và warning

Không phải mọi rule đều phải chặn lưu:
- ERROR: dữ liệu không thể được chấp nhận.
- WARNING: dữ liệu có thể hợp lệ nhưng cần xem xét.
- INFO: thông tin bổ sung.

Workflow hoặc form UI có thể xử lý từng severity khác nhau.

### 3.9. Điều học được

Kịch bản validation thể hiện cách biến yêu cầu thành các rule nhỏ, có code ổn định, severity và message. Rule nên độc lập, dễ test và không có side effect.

## 4. Kịch bản 3: Truy vấn và tạo báo cáo doanh thu

Query DSL phù hợp khi cần chọn dữ liệu, lọc, join, grouping và projection.

### 4.1. Yêu cầu

Báo cáo cần:
- Chỉ lấy đơn hàng đã thanh toán.
- Giới hạn trong một khoảng thời gian.
- Nhóm theo cửa hàng.
- Tính số đơn và doanh thu.
- Sắp xếp theo doanh thu giảm dần.
- Chỉ hiển thị 10 cửa hàng đứng đầu.

### 4.2. Mô hình

~~~text
record Order {
  id: OrderId
  storeId: StoreId
  status: OrderStatus
  total: Decimal
  paidAt: Instant?
}
~~~

### 4.3. Query

~~~text
from Order as order
where order.status == PAID
  and order.paidAt >= periodStart
  and order.paidAt < periodEnd
group by order.storeId
select {
  storeId: group.key,
  orderCount: group.count(),
  revenue: group.sum(order.total)
}
order by revenue desc
limit 10
~~~

Khoảng thời gian dùng cận dưới inclusive và cận trên exclusive. Cách này giúp ghép các khoảng liền nhau mà không đếm trùng thời điểm ở ranh giới.

### 4.4. Join tên cửa hàng

~~~text
from Order as order
join Store as store on store.id == order.storeId
where order.status == PAID
  and order.paidAt >= periodStart
  and order.paidAt < periodEnd
group by {
  store.id,
  store.name
}
select {
  storeId: group.key.id,
  storeName: group.key.name,
  orderCount: group.count(),
  revenue: group.sum(order.total)
}
order by revenue desc
limit 10
~~~

### 4.5. Output type

~~~text
record StoreRevenue {
  storeId: StoreId
  storeName: String
  orderCount: Integer
  revenue: Decimal
}
~~~

### 4.6. Các vấn đề cần chú ý

- Nếu paidAt null, record không thỏa điều kiện thời gian.
- Nếu store không còn tồn tại, inner join loại đơn đó; left join có thể giữ nhưng storeName nullable.
- Nếu có hoàn tiền, cần xác định revenue là gross hay net.
- Nếu currency khác nhau, không cộng trực tiếp trước khi quy đổi.
- Pagination cần sort key ổn định, có thể thêm storeId làm tie-breaker.
- Query cần index phù hợp trên status, paidAt và storeId.

### 4.7. Kiểm thử

Dùng dữ liệu nhỏ với kết quả tính tay:
- Một cửa hàng có hai đơn đã thanh toán.
- Một đơn pending.
- Một đơn nằm ngoài khoảng.
- Một đơn có paidAt null.
- Hai cửa hàng có doanh thu bằng nhau.

Kiểm tra cả số lượng và giá trị tổng hợp.

## 5. Kịch bản 4: Workflow phê duyệt chi phí

Workflow DSL mô tả trạng thái, event, guard và action trong một quy trình kéo dài.

### 5.1. Yêu cầu

Nhân viên gửi yêu cầu thanh toán chi phí. Quản lý phê duyệt hoặc từ chối. Nếu số tiền vượt hạn mức quản lý, yêu cầu phải được chuyển đến giám đốc. Khi được phê duyệt cuối cùng, hệ thống tạo lệnh thanh toán.

### 5.2. Trạng thái

~~~text
DRAFT
SUBMITTED
WAITING_FOR_MANAGER
WAITING_FOR_DIRECTOR
APPROVED
REJECTED
PAYMENT_PENDING
PAID
FAILED
~~~

### 5.3. Context

~~~text
context ExpenseRequest {
  requestId: RequestId
  employeeId: UserId
  amount: Decimal
  currency: Currency
  managerId: UserId?
  directorId: UserId?
  decisionReason: String?
  paymentReference: String?
}
~~~

### 5.4. Transition

~~~text
initial state DRAFT

transition DRAFT -> SUBMITTED
  on submit
  when amount > 0

transition SUBMITTED -> WAITING_FOR_MANAGER
  on submissionAccepted

transition WAITING_FOR_MANAGER -> APPROVED
  on managerApproved
  when amount <= managerApprovalLimit

transition WAITING_FOR_MANAGER -> WAITING_FOR_DIRECTOR
  on managerApproved
  when amount > managerApprovalLimit

transition WAITING_FOR_MANAGER -> REJECTED
  on managerRejected

transition WAITING_FOR_DIRECTOR -> APPROVED
  on directorApproved

transition WAITING_FOR_DIRECTOR -> REJECTED
  on directorRejected

transition APPROVED -> PAYMENT_PENDING
  on paymentRequested

transition PAYMENT_PENDING -> PAID
  on payment.succeeded

transition PAYMENT_PENDING -> FAILED
  on payment.failed
~~~

### 5.5. Guard và separation of duties

Guard có thể yêu cầu người phê duyệt không phải người tạo yêu cầu:

~~~text
when currentActor.id != request.employeeId
  and currentActor.hasRole("MANAGER")
~~~

Danh tính actor phải đến từ security context đáng tin cậy của host. Không nhận role do client tự khai báo.

### 5.6. Action

Khi vào PAYMENT_PENDING, workflow có thể gọi payment service với idempotency key. Nếu event payment.succeeded được giao nhiều lần, runtime cần deduplicate để không ghi nhận thanh toán lặp.

### 5.7. Timeout

Nếu quản lý không phản hồi trong thời hạn, workflow có thể:
- Gửi reminder.
- Escalate lên người quản lý cấp cao hơn.
- Chuyển sang OVERDUE.
- Giữ nguyên trạng thái và tạo task cho bộ phận vận hành.

Timeout là một trigger độc lập, không phải một trạng thái tự động xuất hiện chỉ vì thời gian đã trôi qua.

### 5.8. Điều học được

Kịch bản workflow cho thấy state mô tả giai đoạn, event kích hoạt chuyển tiếp, guard quyết định quyền hoặc điều kiện nghiệp vụ và action tạo side effect. Cần lưu state bền vững, xử lý event trùng và xác định retry.

## 6. Kịch bản 5: Phản ứng với event tồn kho

Event-driven DSL mô tả cách hệ thống phản ứng với sự kiện được phát ra từ các thành phần khác.

### 6.1. Yêu cầu

Khi số lượng tồn kho của sản phẩm xuống dưới mức an toàn:
- Gửi cảnh báo cho người phụ trách.
- Tạo đề nghị bổ sung hàng nếu chưa có đề nghị đang mở.
- Không tạo đề nghị lặp khi cùng một event được giao nhiều lần.

### 6.2. Event schema

~~~text
event InventoryLevelChanged {
  eventId: EventId
  productId: ProductId
  warehouseId: WarehouseId
  available: Integer
  occurredAt: Instant
}
~~~

### 6.3. Rule

~~~text
on InventoryLevelChanged as event
when event.available < inventoryPolicy.minimum(event.productId)
do {
  notifyStockOwner(event.productId, event.warehouseId)

  if not replenishment.existsOpen(event.productId, event.warehouseId) {
    replenishment.createDraft(
      event.productId,
      event.warehouseId
    )
  }
}
~~~

### 6.4. Idempotency

Event ID giúp nhận biết delivery trùng. Nhưng chỉ lưu event ID sau khi side effect hoàn tất có thể tạo race hoặc mất đồng bộ. Có thể dùng inbox record trong cùng transaction với trạng thái xử lý, hoặc API action idempotent.

### 6.5. Event ordering

Nếu event cũ đến sau event mới, rule không nên ghi đè mức tồn kho hiện tại bằng dữ liệu stale. Có thể dùng sequence number hoặc đọc snapshot mới từ inventory service.

### 6.6. Failure handling

Nếu notification service lỗi:
- Retry theo backoff.
- Không tạo nhiều replenishment request.
- Ghi execution status.
- Đưa vào dead-letter sau số lần thử.
- Cho phép operator replay có kiểm soát.

### 6.7. Điều học được

Kịch bản event giúp phân biệt event với command, dùng correlation và idempotency, xử lý duplicate, ordering và retry. DSL không nên giả định message chỉ được giao một lần.

## 7. Kịch bản 6: Policy kiểm soát truy cập

Policy DSL có thể biểu diễn quyết định cho phép hoặc từ chối một hành động dựa trên subject, resource, action và context.

### 7.1. Yêu cầu

Nhân viên chỉ được xem hồ sơ khách hàng thuộc chi nhánh của mình. Quản lý chi nhánh được xem mọi hồ sơ trong chi nhánh. Nhân viên hỗ trợ có thể xem một số field đã mask.

### 7.2. Mô hình policy

~~~text
record Subject {
  id: UserId
  role: Role
  branchId: BranchId
}

record Resource {
  customerId: CustomerId
  branchId: BranchId
  classification: DataClass
}

record AccessRequest {
  subject: Subject
  resource: Resource
  action: Action
}
~~~

### 7.3. Policy

~~~text
policy customerRead {
  deny if subject.disabled

  allow if action == READ
    and subject.role == BRANCH_MANAGER
    and subject.branchId == resource.branchId

  allow if action == READ
    and subject.role == EMPLOYEE
    and subject.branchId == resource.branchId

  allow if action == READ
    and subject.role == SUPPORT
    and resource.classification == MASKED_VIEW

  default deny
}
~~~

### 7.4. Deny by default

Nếu không có rule nào cho phép, quyết định là deny. Điều này tránh vô tình mở quyền khi thêm một role hoặc resource type mới.

### 7.5. Field-level policy

Có thể quyết định field nào được trả về:

~~~text
if subject.role == SUPPORT {
  project {
    customer.id,
    customer.name,
    maskedPhone: maskPhone(customer.phone)
  }
}
~~~

Tuy nhiên, masking và authorization cần được thực hiện tại service có thẩm quyền. Không dựa riêng vào UI hoặc projection do client điều khiển.

### 7.6. Policy testing

Tạo bảng kiểm thử theo subject, resource, action và expected decision. Kiểm tra cả quyền đúng chi nhánh, sai chi nhánh, subject bị khóa, role không xác định và default deny.

### 7.7. Điều học được

Policy DSL cần semantics rõ về precedence, deny/allow, default behavior và trusted identity. Một policy sai có thể làm lộ dữ liệu nên cần versioning, audit và test theo ma trận.

## 8. Kịch bản 7: Sinh tài liệu từ template

Template DSL giúp tạo email, hợp đồng, báo cáo hoặc tài liệu dựa trên dữ liệu có cấu trúc.

### 8.1. Yêu cầu

Tạo xác nhận đơn hàng gồm:
- Tên khách hàng.
- Mã đơn.
- Danh sách sản phẩm.
- Tổng tiền.
- Ngày dự kiến giao.
- Lời nhắn theo ngôn ngữ của khách.

### 8.2. Template

~~~text
document OrderConfirmation {
  title: "Xác nhận đơn hàng"

  section greeting {
    if customer.locale == "vi-VN" {
      text "Xin chào " + customer.displayName
    } else {
      text "Hello " + customer.displayName
    }
  }

  section orderInfo {
    text "Mã đơn: " + order.id
    table order.items {
      column "Sản phẩm" = item.name
      column "Số lượng" = item.quantity
      column "Thành tiền" = formatMoney(item.total, customer.locale)
    }
  }

  section summary {
    text "Tổng tiền: " + formatMoney(order.total, customer.locale)
    text "Dự kiến giao: " + formatDate(order.estimatedDelivery)
  }
}
~~~

### 8.3. Escaping

Dữ liệu người dùng phải được escape theo output context. HTML text, HTML attribute, URL, JavaScript và SQL có quy tắc khác nhau. Không nối input chưa kiểm soát vào raw markup.

### 8.4. Localization

Format ngày, số và tiền phụ thuộc locale và timezone. Nên truyền locale rõ trong context thay vì dựa vào cấu hình máy chạy.

### 8.5. Template security

Template chỉ nên đọc data được cấp. Không cho phép include file tùy ý, truy cập network hoặc gọi hàm host không giới hạn.

### 8.6. Output validation

Giới hạn kích thước tài liệu, số dòng bảng và độ sâu nested section. Kiểm tra output type và encoding trước khi gửi hoặc lưu.

### 8.7. Điều học được

Kịch bản template kết hợp data binding, conditional, iteration, formatting và output generation. Security phụ thuộc vào context escaping và giới hạn capability.

## 9. Kịch bản 8: Chuyển đổi dữ liệu giữa hai schema

Integration DSL thường ánh xạ dữ liệu từ hệ thống nguồn sang contract của hệ thống đích.

### 9.1. Yêu cầu

Một hệ thống bán hàng gửi order theo schema cũ. Hệ thống kho nhận schema mới:
- customerCode đổi thành customerId.
- itemCode đổi thành sku.
- quantity phải là số nguyên dương.
- currency phải chuẩn hóa theo ISO code.
- Trường ghi chú có thể null.

### 9.2. Source và target schema

~~~text
record LegacyOrder {
  orderNo: String
  customerCode: String
  lines: List<LegacyLine>
  currencyText: String
  note: String?
}

record LegacyLine {
  itemCode: String
  qty: Decimal
}

record WarehouseOrder {
  id: OrderId
  customerId: CustomerId
  items: List<WarehouseItem>
  currency: CurrencyCode
  note: String?
}

record WarehouseItem {
  sku: String
  quantity: Integer
}
~~~

### 9.3. Mapping

~~~text
mapping legacyToWarehouse(source: LegacyOrder): WarehouseOrder {
  return WarehouseOrder {
    id: parseOrderId(source.orderNo),
    customerId: resolveCustomer(source.customerCode),
    items: source.lines.map(line => WarehouseItem {
      sku: normalizeSku(line.itemCode),
      quantity: toIntegerExact(line.qty)
    }),
    currency: parseCurrencyCode(source.currencyText),
    note: source.note
  }
}
~~~

### 9.4. Validation và error handling

Nếu qty là 1,5 thì toIntegerExact phải báo lỗi thay vì âm thầm làm tròn. Nếu currency code không hợp lệ, mapping cần tạo diagnostic có source field để người dùng biết dữ liệu nào gây lỗi.

### 9.5. Versioning

Schema nguồn và đích cần version. Khi hệ thống kho thêm field required, mapping cũ có thể không còn hợp lệ. Có thể duy trì nhiều mapping version hoặc migration theo lộ trình.

### 9.6. Idempotency

Nếu message order được giao lại, target system cần nhận biết cùng order version hoặc event ID để không tạo bản ghi trùng.

### 9.7. Điều học được

Mapping DSL cần type conversion tường minh, validation, error location, schema version và idempotency. Không nên che giấu lỗi chuyển kiểu bằng default tùy tiện.

## 10. Kịch bản 9: Tự động phân tuyến yêu cầu hỗ trợ

Một DSL rule có thể phân loại ticket và chọn queue phù hợp.

### 10.1. Yêu cầu

- Ticket về thanh toán được gửi đến nhóm Billing.
- Ticket có mức độ khẩn cấp cao được ưu tiên.
- Khách hàng VIP được ưu tiên trong cùng mức độ.
- Ticket thiếu thông tin cần được chuyển đến queue bổ sung dữ liệu.

### 10.2. Mô hình

~~~text
enum TicketCategory {
  BILLING
  TECHNICAL
  GENERAL
}

enum Priority {
  LOW
  NORMAL
  HIGH
  URGENT
}

record Ticket {
  id: TicketId
  category: TicketCategory
  priority: Priority
  customerTier: CustomerTier
  hasRequiredDetails: Boolean
}
~~~

### 10.3. Rule

~~~text
rule routeTicket(ticket: Ticket): QueueName {
  if not ticket.hasRequiredDetails {
    return "NEED_INFO"
  }

  if ticket.category == BILLING {
    return "BILLING"
  }

  if ticket.priority == URGENT {
    return "URGENT_SUPPORT"
  }

  if ticket.customerTier == GOLD {
    return "VIP_SUPPORT"
  }

  return "GENERAL_SUPPORT"
}
~~~

### 10.4. Precedence

Thứ tự điều kiện là một phần của chính sách. Nếu ticket vừa BILLING vừa URGENT, ví dụ trên gửi đến BILLING vì điều kiện đó được xét trước. Nếu yêu cầu nghiệp vụ muốn URGENT có ưu tiên cao nhất, cần đổi thứ tự hoặc biểu diễn bằng priority score.

### 10.5. Rule conflict

Nếu các rule được khai báo độc lập và cùng match, DSL cần quy tắc:
- First match.
- Highest priority.
- Collect all actions.
- Reject ambiguity.

Không để thứ tự file hoặc thứ tự load vô tình quyết định routing.

### 10.6. Kiểm thử bảng quyết định

| Category | Priority | Tier | Required details | Queue |
| --- | --- | --- | --- | --- |
| BILLING | NORMAL | STANDARD | Yes | BILLING |
| TECHNICAL | URGENT | STANDARD | Yes | URGENT_SUPPORT |
| GENERAL | LOW | GOLD | Yes | VIP_SUPPORT |
| BILLING | HIGH | GOLD | No | NEED_INFO |

### 10.7. Điều học được

Kịch bản routing cho thấy rule precedence, decision table và thứ tự đánh giá có thể làm thay đổi kết quả. Bảng quyết định giúp kiểm thử tổ hợp điều kiện rõ ràng hơn.

## 11. Kịch bản 10: Tính phí theo bậc và giới hạn

Một DSL công thức có thể mô tả biểu giá theo bậc, ví dụ phí lưu trữ hoặc phí sử dụng API.

### 11.1. Yêu cầu

- 1.000 request đầu miễn phí.
- Từ request 1.001 đến 10.000: 20 đồng mỗi request.
- Trên 10.000: 12 đồng mỗi request vượt ngưỡng.
- Phí tháng không vượt 500.000 đồng.

### 11.2. Công thức

~~~text
function calculateMonthlyFee(requestCount: Integer): Decimal {
  let firstTier = max(0, min(requestCount, 1000))
  let secondTier = max(0, min(requestCount - 1000, 9000))
  let thirdTier = max(0, requestCount - 10000)

  let rawFee = secondTier * 20 + thirdTier * 12
  return min(rawFee, 500000)
}
~~~

### 11.3. Kiểm tra biên

| Request count | Phí |
| ---: | ---: |
| 0 | 0 |
| 1.000 | 0 |
| 1.001 | 20 |
| 10.000 | 180.000 |
| 10.001 | 180.012 |
| Rất lớn | Tối đa 500.000 |

Biến firstTier không ảnh hưởng rawFee vì bậc đầu miễn phí; nó có thể được bỏ nếu DSL không cần dùng. Trong ví dụ thực tế, nên giữ công thức đơn giản và tránh biến thừa.

### 11.4. Kiểu số

Nếu tính tiền, dùng Decimal hoặc kiểu tiền tệ có precision rõ. Không dùng floating-point nhị phân nếu rounding có thể làm sai số tiền.

### 11.5. Điều học được

Biểu giá theo bậc cần định nghĩa cận trên, cận dưới, inclusive/exclusive, rounding và cap. Hãy test ngay tại các điểm chuyển bậc.

## 12. Kịch bản 11: Phân loại dữ liệu theo mức độ nhạy cảm

Một DSL policy có thể gắn nhãn dữ liệu và quy định cách sử dụng.

### 12.1. Yêu cầu

- Dữ liệu công khai có thể hiển thị rộng.
- Dữ liệu nội bộ chỉ dành cho nhân viên.
- Dữ liệu bí mật cần role cụ thể.
- Dữ liệu cá nhân cần mask khi dùng cho hỗ trợ.
- Không xuất dữ liệu bí mật sang môi trường thử nghiệm.

### 12.2. Phân loại

~~~text
enum DataClass {
  PUBLIC
  INTERNAL
  CONFIDENTIAL
  PERSONAL
}
~~~

### 12.3. Policy

~~~text
policy canExport(field: Field, target: Environment): Boolean {
  if field.classification == PUBLIC {
    return true
  }

  if target == PRODUCTION {
    return currentActor.hasRole("DATA_OPERATOR")
  }

  if field.classification == PERSONAL {
    return false
  }

  return field.classification == INTERNAL
}
~~~

### 12.4. Masking

Một policy riêng có thể quyết định cách trình bày:

~~~text
if field.classification == PERSONAL
  and currentActor.hasRole("SUPPORT") {
  return mask(field.value)
}
~~~

Không được coi masking là authorization thay thế. Một số dữ liệu vẫn có thể nhạy cảm ngay cả khi đã che một phần.

### 12.5. Audit

Ghi ai truy cập hoặc export, dữ liệu thuộc classification nào, mục đích, môi trường và policy version. Không log nguyên giá trị cá nhân nếu không cần.

### 12.6. Điều học được

Kịch bản phân loại dữ liệu cho thấy policy DSL có thể hỗ trợ data governance, nhưng enforcement cần nằm ở boundary đáng tin cậy. Không chỉ dựa vào quy tắc do client gửi.

## 13. Kịch bản 12: Tạo workflow xử lý hoàn tiền

Refund là ví dụ có side effect, trạng thái và compensation.

### 13.1. Yêu cầu

- Nhận yêu cầu hoàn tiền.
- Kiểm tra đơn đã thanh toán.
- Kiểm tra số tiền không vượt số tiền có thể hoàn.
- Yêu cầu duyệt nếu số tiền lớn.
- Gọi payment provider.
- Ghi nhận kết quả và thông báo khách hàng.

### 13.2. Trạng thái

~~~text
REQUESTED
VALIDATING
WAITING_FOR_APPROVAL
APPROVED
PROCESSING
REFUNDED
REJECTED
FAILED
~~~

### 13.3. Workflow

~~~text
workflow refundRequest(request: RefundRequest) {
  initial state REQUESTED

  transition REQUESTED -> VALIDATING
    on start

  transition VALIDATING -> WAITING_FOR_APPROVAL
    on validationPassed
    when request.amount > approvalThreshold

  transition VALIDATING -> APPROVED
    on validationPassed
    when request.amount <= approvalThreshold

  transition WAITING_FOR_APPROVAL -> APPROVED
    on managerApproved

  transition WAITING_FOR_APPROVAL -> REJECTED
    on managerRejected

  transition APPROVED -> PROCESSING
    on processRefund
    do paymentProvider.refund(
      request.paymentId,
      request.amount,
      request.idempotencyKey
    )

  transition PROCESSING -> REFUNDED
    on provider.refundSucceeded

  transition PROCESSING -> FAILED
    on provider.refundFailed
}
~~~

### 13.4. Kiểm tra nghiệp vụ

Validation cần kiểm tra:
- Payment tồn tại.
- Payment đã capture.
- Refund amount dương.
- Tổng refund hiện tại cộng refund mới không vượt amount đã capture.
- Request thuộc đúng tenant.
- Currency tương thích.

### 13.5. Idempotency và trạng thái không rõ

Nếu request timeout sau khi provider đã xử lý refund nhưng response không đến, không được gửi một refund mới với key khác. Dùng idempotency key ổn định và reconciliation query để xác định kết quả.

### 13.6. Compensation và manual review

Nếu refund đã thành công nhưng ghi nhận nội bộ thất bại, không thể đơn giản gọi refund lần nữa. Cần reconcile trạng thái provider, ghi lại kết quả hoặc chuyển sang manual review.

### 13.7. Điều học được

Workflow có side effect cần state persistence, idempotency, timeout, retry và reconciliation. Lỗi mạng không đồng nghĩa thao tác nghiệp vụ chưa xảy ra.

## 14. Kịch bản 13: Sinh schema từ mô hình DSL

Một DSL khai báo domain model có thể sinh JSON Schema, SQL DDL hoặc API contract.

### 14.1. Model

~~~text
entity Customer {
  id: CustomerId primary
  name: String required
  email: Email unique
  createdAt: Instant required
  status: CustomerStatus default ACTIVE
}
~~~

### 14.2. Target JSON Schema

Một generator có thể tạo schema tương đương:
- id là required.
- name là string.
- email có format email và unique metadata nếu target hỗ trợ.
- createdAt là date-time.
- status có enum và default.

### 14.3. Target SQL

Generator SQL có thể tạo:
- Primary key.
- Not null.
- Unique constraint.
- Timestamp column.
- Default value.
- Index theo policy.

### 14.4. Mapping semantics

Không phải mọi constraint đều có biểu diễn tương đương ở mọi target. Nếu JSON Schema không hỗ trợ một quy tắc cross-field, generator có thể cần extension hoặc diagnostic.

### 14.5. Reproducibility

Cùng model, generator version và target profile nên tạo output xác định. Lưu generator version và configuration trong artifact metadata.

### 14.6. Điều học được

Kịch bản code generation cho thấy một mô hình logic có thể có nhiều target. Cần định nghĩa mapping semantics và báo rõ constraint không thể biểu diễn.

## 15. Cách đọc và so sánh các kịch bản

Các kịch bản có thể dùng chung một quy trình phân tích dù domain khác nhau.

### 15.1. Xác định loại bài toán

| Loại bài toán | Thành phần DSL thường dùng |
| --- | --- |
| Công thức | Type, expression, function |
| Validation | Rule, predicate, diagnostic |
| Truy vấn | Source, filter, join, group, projection |
| Workflow | State, event, transition, action |
| Event processing | Event schema, handler, idempotency |
| Authorization | Subject, resource, policy, decision |
| Template | Binding, condition, iteration, formatter |
| Data mapping | Schema, conversion, validation |
| Code generation | Model, target, generator, artifact |

### 15.2. Xác định pure và side effect

Đánh dấu thành phần nào chỉ tính toán và thành phần nào thay đổi hệ thống. Pure expression dễ test và tái sử dụng; action cần permission, timeout, retry và audit.

### 15.3. Xác định execution context

Một số kết quả phụ thuộc:
- User hiện tại.
- Tenant.
- Thời gian.
- Locale.
- Environment.
- Policy version.
- External data snapshot.

Đưa các giá trị này vào context rõ ràng để test và replay.

### 15.4. Xác định failure behavior

Không chỉ mô tả happy path. Hãy xác định:
- Input sai.
- Dependency lỗi.
- Timeout.
- Permission denied.
- Duplicate event.
- Partial success.
- Retry exhausted.
- Manual intervention.

### 15.5. Xác định observability

Một kịch bản vận hành được cần có:
- Execution ID.
- Diagnostic code.
- State history nếu có.
- Audit event.
- Duration và outcome.
- Liên kết tới source hoặc artifact.

## 16. Thiết kế test case từ kịch bản

Mỗi kịch bản nên tạo test suite bao phủ cả kết quả bình thường và trường hợp biên.

### 16.1. Example-based test

Đưa input cụ thể và expected output:

~~~text
test "gold customer receives tier discount" {
  given order = sampleGoldOrder()
  when result = calculatePrice(order)
  then result.tierDiscount == 40000
}
~~~

### 16.2. Boundary-value test

Nếu rule dùng ngưỡng 1.000.000, test:
- 999.999.
- 1.000.000.
- 1.000.001.

Điều này phát hiện lỗi dùng lớn hơn thay vì lớn hơn hoặc bằng.

### 16.3. Equivalence partitioning

Chia input thành nhóm có hành vi tương tự:
- Customer tier hợp lệ.
- Customer tier không hợp lệ.
- Amount dương.
- Amount bằng 0.
- Amount âm.

Chọn representative từ mỗi nhóm.

### 16.4. Decision table

Với nhiều điều kiện, decision table giúp tránh bỏ sót tổ hợp:

| Active | Tier | Amount threshold | Expected discount |
| --- | --- | --- | --- |
| Yes | GOLD | Met | Tier + order |
| Yes | GOLD | Not met | Tier |
| Yes | STANDARD | Met | Order |
| No | GOLD | Met | None |

### 16.5. State transition test

Với workflow, test từng transition:
- Source state.
- Event.
- Guard.
- Target state.
- Action.
- Invalid event.

### 16.6. Property-based test

Kiểm tra tính chất tổng quát:
- Final price không âm.
- Discount không vượt subtotal.
- Refund không vượt amount đã capture.
- Policy default deny.
- Một event ID chỉ tạo một side effect logic.

### 16.7. Golden test cho code generation

Lưu expected generated output hoặc semantic representation. So sánh sau mỗi thay đổi compiler. Nếu output text có yếu tố không ổn định, chuẩn hóa hoặc so sánh AST/IR.

### 16.8. Integration test

Kiểm tra host API, database, message broker và sandbox. Mock giúp unit test nhanh nhưng không thay integration test cho các boundary quan trọng.

## 17. Tổ chức thư viện ví dụ DSL

Một thư viện ví dụ có cấu trúc giúp người học tìm đúng mẫu và tái sử dụng an toàn.

### 17.1. Phân loại theo domain

Có thể chia:
- Commerce.
- Finance.
- Support.
- Inventory.
- Identity and access.
- Reporting.
- Integration.
- Workflow.
- Document generation.

### 17.2. Phân loại theo kỹ thuật

Cũng có thể gắn tag:
- Expression.
- Type.
- Validation.
- Query.
- State machine.
- Event.
- Policy.
- Template.
- Mapping.
- Code generation.

### 17.3. Mỗi ví dụ nên có metadata

Một ví dụ nên ghi:
- Tên.
- Domain.
- DSL version.
- Feature được sử dụng.
- Input schema.
- Expected output.
- Required capability.
- Security profile.
- Test cases.
- Limitations.

### 17.4. Ví dụ tối thiểu và ví dụ hoàn chỉnh

Ví dụ tối thiểu giải thích một feature. Ví dụ hoàn chỉnh thể hiện cách nhiều feature kết hợp trong một tình huống thực tế.

Không nên bắt đầu mọi bài bằng một chương trình quá lớn. Hãy giới thiệu khái niệm nhỏ, rồi mở rộng dần.

### 17.5. Version compatibility

Ví dụ cần chỉ rõ DSL version và runtime version. Khi syntax hoặc API thay đổi, cập nhật ví dụ và giữ lịch sử tương thích nếu cần.

### 17.6. Không đưa secret vào ví dụ

Dùng placeholder và fixture giả. Không commit credential, customer data hoặc endpoint nội bộ vào thư viện học tập.

## 18. Chuyển từ yêu cầu tự nhiên sang DSL

Một phương pháp hữu ích là lập bảng ánh xạ trước khi viết code.

| Câu trong yêu cầu | Câu hỏi phân tích | Thành phần DSL |
| --- | --- | --- |
| Khi đơn được thanh toán | Sự kiện nào xảy ra? | Event trigger |
| Nếu tổng tiền lớn hơn ngưỡng | Điều kiện gì? | Guard hoặc predicate |
| Tính phí theo khoảng cách | Công thức nào? | Function/expression |
| Chỉ lấy đơn trong tháng | Tập dữ liệu nào? | Query filter |
| Gom theo cửa hàng | Nhóm theo khóa nào? | Grouping |
| Gửi email xác nhận | Side effect nào? | Action/capability |
| Chờ quản lý duyệt | Trạng thái nào? | Workflow state |
| Không cho tenant khác đọc | Quyền nào cần kiểm tra? | Access policy |

### 18.1. Không dịch từng từ thành cú pháp

Yêu cầu nghiệp vụ thường chứa nhiều ý trong một câu. Hãy phân tích điều kiện và quan hệ trước, sau đó chọn construct DSL.

### 18.2. Làm rõ từ ngữ mơ hồ

Các từ như “gần đây”, “lớn”, “đủ điều kiện”, “ưu tiên” cần định nghĩa:
- Khoảng thời gian cụ thể.
- Ngưỡng.
- Thứ tự ưu tiên.
- Nguồn dữ liệu.
- Cách xử lý null.

### 18.3. Chọn abstraction phù hợp

Một điều kiện chỉ dùng một lần có thể là expression. Một quy tắc được dùng ở nhiều nơi có thể trở thành named predicate. Một chuỗi hành động kéo dài có thể cần workflow thay vì một function lớn.

### 18.4. Giữ business meaning trong tên

Tên như canApproveExpense hoặc eligibleForDiscount diễn đạt mục đích tốt hơn tên như check1 hoặc flagA.

## 19. Debug một kịch bản DSL

Khi output không như mong đợi, điều tra theo các lớp.

### 19.1. Kiểm tra input

Xác nhận dữ liệu thật, nullability, timezone, currency, enum và default. Nhiều lỗi DSL thực ra bắt nguồn từ input sai.

### 19.2. Kiểm tra parse và type

Nếu parser hoặc type checker báo lỗi, xem diagnostic code và source range. Không tiếp tục debug runtime khi chương trình chưa compile hợp lệ.

### 19.3. Kiểm tra giá trị trung gian

Tạm biểu diễn các bước tính toán thành biến có tên:

~~~text
let subtotal = calculateSubtotal(order)
let eligible = calculateEligibleSubtotal(order)
let rate = tierRate(order.customerTier)
let discount = eligible * rate
~~~

Điều này giúp thấy bước nào tạo giá trị bất ngờ.

### 19.4. Kiểm tra branch

Xem điều kiện nào true hoặc false. Với rule có nhiều nhánh, ghi decision trace hoặc dùng debugger nếu runtime hỗ trợ.

### 19.5. Kiểm tra side effect

Xác minh action được gọi bao nhiêu lần, với input nào và outcome nào. Dùng idempotency để tránh debug gây giao dịch lặp.

### 19.6. Kiểm tra state và event

Với workflow, xem state history, event ID, correlation ID và guard result. Event có thể bị giao sai instance hoặc đến không đúng thứ tự.

### 19.7. Kiểm tra policy

Với authorization, ghi decision code và policy version. Tránh log toàn bộ dữ liệu nhạy cảm để tìm lý do deny.

## 20. Bảo mật trong ví dụ học tập

Ví dụ ngắn thường bỏ qua bảo mật để tập trung vào cú pháp, nhưng người học cần biết ranh giới thực tế.

### 20.1. Không tin input

Validate input tại boundary. DSL không nên tự giả định dữ liệu từ form, API hoặc file import đã hợp lệ.

### 20.2. Không tin identity do chương trình khai báo

User, role và tenant context phải đến từ host đã xác thực. Không cho source DSL tự nâng quyền bằng cách gán role.

### 20.3. Hạn chế capability

Ví dụ query chỉ cần read capability. Ví dụ định giá chỉ cần input record. Ví dụ workflow chỉ cần các action cụ thể.

### 20.4. Resource limit

Đặt giới hạn cho query rows, execution time, recursion, collection size, output size và số action.

### 20.5. Không expose secret

Ví dụ dùng reference hoặc mock provider. Không đưa token và password thật vào source.

### 20.6. Kiểm tra output

Host kiểm tra schema, range và business invariant trước khi ghi hoặc trả kết quả.

## 21. Mở rộng một kịch bản theo từng giai đoạn

Một ví dụ học tập có thể phát triển theo các cấp:

1. **Cấp 1 — Expression:** tính một giá trị từ input.
2. **Cấp 2 — Function:** đặt tên và tái sử dụng công thức.
3. **Cấp 3 — Rule:** thêm điều kiện và diagnostic.
4. **Cấp 4 — Data access:** đọc dữ liệu qua query hoặc capability.
5. **Cấp 5 — Workflow:** mô hình hóa trạng thái và event.
6. **Cấp 6 — Integration:** gọi service và xử lý kết quả bất đồng bộ.
7. **Cấp 7 — Operations:** thêm audit, metrics, retry và recovery.

### 21.1. Giữ từng bước có thể chạy

Sau mỗi giai đoạn, chương trình nên parse, validate hoặc test được. Tránh thêm nhiều feature cùng lúc khiến khó xác định lỗi bắt đầu từ đâu.

### 21.2. Giữ output ổn định

Khi thêm feature, tạo regression test để đảm bảo các trường hợp cũ vẫn cho kết quả như trước.

### 21.3. Đánh giá abstraction

Nếu một abstraction chỉ được dùng một lần và làm ví dụ khó hiểu, có thể chưa cần đưa vào. Nếu logic lặp lại hoặc có ý nghĩa nghiệp vụ, abstraction có thể làm chương trình rõ hơn.

## 22. Bài tập thực hành

Các bài tập sau có thể dùng để tự luyện hoặc làm nội dung workshop.

### Bài tập 1: Giá thành viên

Tạo function tính giá theo hạng thành viên. Thêm ngưỡng đơn hàng và giới hạn discount tối đa. Viết test tại các boundary.

### Bài tập 2: Validation đơn hàng

Kiểm tra:
- Có ít nhất một item.
- Quantity dương.
- Unit price không âm.
- Địa chỉ giao hàng có đủ trường.
- Currency được hỗ trợ.

Trả về tất cả diagnostic cùng field liên quan.

### Bài tập 3: Báo cáo khách hàng

Lấy khách hàng có ít nhất ba đơn trong một khoảng thời gian. Chiếu customer ID, tên, số đơn và tổng chi tiêu. Sắp xếp theo tổng chi tiêu.

### Bài tập 4: Workflow nghỉ phép

Mô hình hóa DRAFT, SUBMITTED, APPROVED, REJECTED và CANCELLED. Kiểm tra người tạo không được tự phê duyệt. Thêm timeout cho bước chờ quản lý.

### Bài tập 5: Event cảnh báo tồn kho

Nhận event thay đổi tồn kho. Gửi cảnh báo khi dưới ngưỡng. Xử lý duplicate event và event đến sai thứ tự.

### Bài tập 6: Access policy

Tạo policy đọc hồ sơ theo role và branch. Mặc định deny. Viết decision table cho các tổ hợp subject và resource.

### Bài tập 7: Template hóa đơn

Sinh hóa đơn từ order record. Hỗ trợ locale, format tiền và danh sách item. Escape nội dung và giới hạn output.

### Bài tập 8: Mapping schema

Chuyển dữ liệu từ schema version 1 sang version 2. Kiểm tra conversion lỗi, field bắt buộc và compatibility.

### Bài tập 9: Query phí sử dụng

Tính phí theo bậc từ usage record. Thêm cap, rounding và currency. Test giá trị ngay dưới và trên mỗi ngưỡng.

### Bài tập 10: Tích hợp thanh toán

Mô hình hóa yêu cầu thanh toán bất đồng bộ. Xử lý accepted, declined, timeout, duplicate callback và reconciliation.

## 23. Tiêu chí đánh giá một ví dụ DSL tốt

Một ví dụ hữu ích cần giúp người học hiểu cả vấn đề lẫn cách giải quyết.

### 23.1. Bối cảnh rõ

Người học biết ai sử dụng, mục đích gì và dữ liệu đến từ đâu.

### 23.2. Mô hình phù hợp

Type và schema biểu diễn đúng khái niệm miền. Nullability, enum và constraint được khai báo rõ.

### 23.3. Cú pháp tập trung vào feature

Ví dụ làm nổi bật khái niệm đang học. Không đưa nhiều abstraction không liên quan vào cùng một đoạn.

### 23.4. Output có thể kiểm chứng

Có input cụ thể, expected output hoặc state transition mong đợi.

### 23.5. Có trường hợp biên

Ví dụ không chỉ chạy với dữ liệu lý tưởng. Nó cần cho thấy behavior với null, boundary, duplicate và error.

### 23.6. Có giới hạn và giả định

Nêu rõ phần nào là cú pháp minh họa, feature nào phụ thuộc runtime hoặc provider, và giả định nào được dùng.

### 23.7. Có security context

Không dùng ví dụ để dạy một pattern nguy hiểm như raw SQL, arbitrary network hoặc quyền truy cập không giới hạn mà không giải thích boundary.

### 23.8. Có thể tái lập

Ghi version DSL, input fixture, runtime version hoặc dependency cần thiết. Không phụ thuộc vào dữ liệu production không thể chia sẻ.

## 24. Kết luận

Ví dụ theo kịch bản giúp người học nhìn thấy cách DSL giải quyết một vấn đề từ yêu cầu nghiệp vụ đến dữ liệu, rule, query, workflow, event, policy và output. Các tình huống định giá, validation, báo cáo, phê duyệt, event tồn kho, kiểm soát truy cập, template, mapping và code generation cho thấy mỗi loại bài toán cần một tập construct phù hợp.

Khi xây dựng một ví dụ, hãy bắt đầu từ actor, input, rule, action, output và constraint. Mô hình hóa dữ liệu trước khi viết cú pháp, tách expression thuần khỏi side effect, xác định kết quả mong đợi và kiểm thử cả trường hợp biên. Với workflow và integration, cần thêm state persistence, idempotency, timeout, retry và audit. Với policy và dữ liệu, cần trusted identity, least privilege và enforcement tại host boundary.

Một thư viện ví dụ tốt có nhiều cấp độ, có thể chạy lại, ghi rõ version và đi kèm test. Người học không chỉ sao chép đoạn mã mà còn hiểu cách chọn abstraction, dự đoán hành vi và kiểm chứng kết quả. Khi phương pháp phân tích kịch bản trở thành thói quen, họ có thể tự chuyển những yêu cầu mới thành chương trình DSL rõ ràng, an toàn và dễ bảo trì.


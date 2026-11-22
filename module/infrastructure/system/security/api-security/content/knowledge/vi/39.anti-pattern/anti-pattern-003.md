# Serialize entity đầy đủ rồi che field ở client

Một lỗi thiết kế API thường gặp là trả thẳng entity/database model từ backend, để serializer chuyển gần như toàn bộ thuộc tính thành JSON, rồi dùng frontend ẩn những field mà người dùng không nên thấy. Ví dụ, response chứa `salary`, `internalNote`, `riskScore`, `passwordHash`, `tenantId` hoặc `isAdmin`, nhưng giao diện chỉ render một vài field cần thiết. Cách làm này tạo cảm giác rằng dữ liệu đã được bảo vệ vì người dùng không nhìn thấy nó trên màn hình.

Đây là một **anti-pattern về data exposure**. Khi server đã gửi field trong HTTP response, caller có thể xem nó bằng DevTools, proxy, mobile instrumentation, curl hoặc bất kỳ HTTP client nào. CSS, JavaScript, component condition hoặc quyền hiển thị ở frontend chỉ điều khiển giao diện; chúng không thu hồi được dữ liệu đã gửi qua mạng. API phải quyết định ở server field nào được phép đọc và chỉ serialize tập dữ liệu đó.

Trong phạm vi `SECURITY_API_SECURITY`, response cần được thiết kế theo endpoint, principal, tenant, object và business purpose. Hãy dùng response DTO hoặc projection theo allowlist, áp dụng field-level authorization ở server, kiểm tra nested relationship và chỉ đưa dữ liệu tối thiểu cần thiết vào contract. Entity là mô hình persistence của backend; nó không tự động là hợp đồng công khai của API.

## 1. Vì sao che field ở client không bảo vệ dữ liệu?

Giả sử endpoint trả:

~~~json
{
  "id": "emp-104",
  "displayName": "Nguyen An",
  "department": "Finance",
  "salary": 52000000,
  "bankAccount": "00123456789",
  "internalNote": "Under investigation",
  "riskScore": 87,
  "isAdmin": false
}
~~~

Giao diện chỉ hiển thị `displayName` và `department`. Các field còn lại vẫn nằm trong response body và đã được gửi đến thiết bị của caller. Người dùng có thể:

- Mở tab Network trong browser DevTools và đọc raw JSON.
- Gọi API trực tiếp bằng curl, Postman hoặc script.
- Dùng proxy để lưu response và phân tích.
- Đọc dữ liệu từ memory/state của ứng dụng sau khi parse JSON.
- Sửa JavaScript để bỏ điều kiện ẩn field.
- Trích xuất response từ mobile app hoặc extension.
- Quan sát dữ liệu bị lưu trong cache, analytics, crash report hoặc client log.

Vì vậy, “không render” không đồng nghĩa “không tiết lộ”. Nếu caller không được phép đọc một field, field đó không nên xuất hiện trong response mà caller nhận được.

### 1.1. Client không phải security boundary

Frontend nằm trong môi trường do người dùng kiểm soát. Người dùng có thể thay đổi:

- JavaScript bundle hoặc source map.
- State management/store.
- Component condition và CSS.
- Request URL, query parameter và header.
- Response parser hoặc logic kiểm tra role.
- Mobile application binary/runtime.

Ví dụ sau chỉ ẩn một phần tử giao diện:

~~~javascript
if (currentUser.role !== "HR_ADMIN") {
  hideSalaryColumn();
}
~~~

Nếu API đã trả `salary`, user có thể đọc giá trị mà không cần hiển thị cột. Điều kiện trên có thể hữu ích cho UX, nhưng không phải authorization.

### 1.2. Dữ liệu có thể rời khỏi hệ thống qua nhiều đường

Response body không chỉ được nhìn thấy trên màn hình. Nó có thể được lưu hoặc truyền tiếp bởi:

- Browser cache, service worker và offline storage.
- Mobile local database hoặc application cache.
- Reverse proxy, CDN hoặc API response cache.
- Observability agent, request/response logger và APM.
- Analytics SDK, session replay hoặc crash report.
- Extension, debugging tool và proxy của người dùng.

Không phải mọi hệ thống đều lưu raw response ở các nơi này, nhưng gửi dữ liệu không cần thiết làm tăng số vị trí có thể bị lộ. Data minimization giảm cả bề mặt tấn công và hậu quả khi một lớp logging/cache bị cấu hình sai.

## 2. Entity và API response DTO có mục đích khác nhau

Entity thường mô tả dữ liệu persistence và quan hệ trong domain. Nó có thể chứa field nội bộ, trạng thái workflow, metadata, foreign key, audit field hoặc quan hệ ORM. API response DTO mô tả đúng tập thông tin mà một caller được phép nhận trong một use case.

| Persistence entity | API response DTO |
|---|---|
| Phục vụ lưu trữ và domain logic | Phục vụ contract với consumer |
| Có thể chứa toàn bộ thuộc tính nội bộ | Chỉ chứa field được phép công bố |
| Có quan hệ ORM và lazy proxy | Có cấu trúc response ổn định, tường minh |
| Thay đổi theo schema/domain refactor | Thay đổi theo version và contract |
| Có thể có secret reference, audit data, internal state | Loại bỏ dữ liệu không cần hoặc không được phép |
| Không nên serialize trực tiếp | Là ranh giới serialization có kiểm soát |

Một entity `Employee` có thể chứa `salary`, `bankAccount`, `disciplinaryNote`, `managerId`, `tenantId`, `createdBy` và `updatedAt`. Endpoint directory công khai chỉ cần `id`, `displayName` và `department`. Không nên dùng một entity chung rồi trông chờ từng frontend nhớ ẩn các field nhạy cảm.

### 2.1. Entity không phải contract

Nếu controller trả entity trực tiếp, thay đổi persistence có thể vô tình làm thay đổi API:

- Thêm field nội bộ vào entity có thể tự động xuất hiện trong JSON.
- Đổi quan hệ ORM có thể làm response mở rộng hoặc lặp.
- Rename property có thể phá client.
- Thêm getter có thể làm Jackson serialize thêm một property.
- Một field mới có thể bị trả cho mọi role dù chưa được security review.

Tách DTO giúp thay đổi database/domain mà không tự động thay đổi public contract.

### 2.2. Không dùng một DTO khổng lồ cho mọi role

Một cách khác nhưng vẫn rủi ro là tạo `EmployeeResponse` chứa tất cả field, rồi gắn điều kiện để từng role chỉ thấy một số field. DTO lớn dễ dẫn đến nhầm lẫn, default/null ambiguity và quên kiểm tra quyền khi thêm property.

Ưu tiên response model theo use case:

- `EmployeeDirectoryItem`: field cơ bản cho directory.
- `EmployeeSelfProfile`: thông tin cá nhân người dùng được xem.
- `EmployeeHrRecord`: field nhân sự chỉ HR được phép xem.
- `EmployeePayrollSummary`: dữ liệu payroll dành cho payroll role.

Các DTO có thể dùng chung một số value object an toàn, nhưng phải thể hiện rõ contract và authorization. Nếu cần field động theo permission, quyết định phải được thực hiện ở server trước khi tạo response.

## 3. Data minimization: chỉ trả dữ liệu cần thiết

Data minimization là nguyên tắc chỉ thu thập, xử lý và tiết lộ lượng dữ liệu cần cho mục đích cụ thể. Với API response, hãy hỏi:

1. Consumer cần field này để hoàn thành use case nào?
2. Caller hiện tại có quyền đọc field này không?
3. Field có chứa dữ liệu cá nhân, bí mật, nội bộ hoặc dữ liệu tenant khác không?
4. Có thể trả một giá trị ít nhạy cảm hơn hoặc aggregate thay vì raw value không?
5. Field có cần xuất hiện ở mọi API version và mọi role không?
6. Field có bị copy sang cache, log hoặc analytics không?

Ví dụ:

| Use case | Có thể cần trả | Thường không cần trả |
|---|---|---|
| Danh sách nhân viên | ID, display name, team | Salary, bank account, disciplinary note |
| Hồ sơ cá nhân | Contact info được phép xem/sửa | Internal risk score, admin flags |
| Danh sách order | Order ID, status, total hiển thị | Payment token, internal fraud signal |
| Payment status | Payment ID, status, amount đã được phép xem | Full card data, provider credential |
| Support case | Case ID, public status, message | Internal moderation note, secret debug data |

Không trả field “phòng khi frontend cần sau này”. Khi use case mới xuất hiện, thêm field vào contract sau khi xác định permission, data classification và consumer thực sự cần.

### 3.1. Phân loại dữ liệu trước khi thiết kế response

Có thể dùng các nhóm phân loại nội bộ như:

- Public: được phép công bố không cần xác thực.
- Internal: chỉ dùng trong tổ chức hoặc workload được phép.
- Confidential: dữ liệu khách hàng/nhân viên hoặc nghiệp vụ nhạy cảm.
- Restricted/secret: credential, private key, token, password verifier hoặc dữ liệu có hậu quả nghiêm trọng khi lộ.

Tên và số nhóm tùy policy tổ chức. Điều quan trọng là field có owner, purpose và access rule. Không đưa secret vào DTO rồi trông chờ annotation hoặc client hide.

## 4. Field-level authorization phải được thực thi ở server

Authorization không chỉ quyết định caller có được gọi endpoint hay không. Một endpoint có thể trả một phần dữ liệu khác nhau tùy principal và object.

Ví dụ:

- Nhân viên xem hồ sơ của chính mình.
- Manager xem tên và team của thành viên trong nhóm được quản lý.
- HR được xem một số field nhân sự theo chức năng.
- Payroll service được đọc dữ liệu lương cho kỳ payroll hợp lệ.
- Support operator chỉ xem dữ liệu được cấp theo ticket/time-bound grant.

Không thể suy ra rằng user có `employees:read` thì được đọc mọi field của mọi employee. Cần kết hợp function permission, object scope, tenant boundary và field policy.

### 4.1. Ma trận field và actor

| Field | Employee self | Manager cùng team | HR role | Public directory |
|---|---|---|---|---|
| `displayName` | Read | Read | Read | Read |
| `department` | Read | Read | Read | Read |
| `workEmail` | Read | Read theo scope | Read | Có thể read nếu công bố |
| `salary` | Theo policy | Không mặc định | Read theo purpose | Deny |
| `bankAccount` | Theo workflow riêng | Deny | Role payroll giới hạn | Deny |
| `disciplinaryNote` | Theo quy trình riêng | Deny | Role được cấp | Deny |
| `internalRiskScore` | Deny | Deny | Chỉ role chuyên biệt nếu hợp pháp | Deny |
| `tenantId` | Thường không cần trả | Thường không cần trả | Internal use nếu cần | Deny |

Bảng chỉ là ví dụ. Quyền thực tế phải dựa trên policy, pháp lý, purpose và data classification của hệ thống.

### 4.2. Quyết định field access trước serialization

Một flow an toàn:

1. Xác thực principal/service identity.
2. Tải object trong tenant/scope của principal.
3. Kiểm tra function permission.
4. Kiểm tra object-level authorization.
5. Xác định field được phép đọc cho actor và purpose.
6. Map sang response DTO allowlist.
7. Serialize DTO và trả response.

Không serialize entity đầy đủ rồi xóa field ở response interceptor hoặc client. Nếu có response filter theo role, filter đó phải là server-side, fail-closed, test được và có policy rõ; DTO riêng theo use case thường dễ review hơn.

### 4.3. Không dựa vào role name rải rác trong controller

Logic như `if (role == "ADMIN")` xuất hiện ở nhiều nơi dễ không nhất quán. Dùng permission/policy service hoặc mapper nhận một access context đã xác minh. Tuy nhiên, đừng biến mapper thành nơi tự đoán quyền từ field do client gửi. Principal, tenant và grant phải đến từ trusted security context.

## 5. Response DTO theo allowlist

Allowlist có nghĩa mỗi response model liệt kê rõ các field được phép trả. Khi entity thêm field mới, DTO không tự động đưa field đó vào response.

Ví dụ entity nội bộ:

~~~java
@Entity
class Employee {
    @Id
    private UUID id;
    private String displayName;
    private String department;
    private String workEmail;
    private BigDecimal salary;
    private String bankAccount;
    private String internalNote;
    private UUID tenantId;
    private boolean admin;
    // getters and domain behavior
}
~~~

Không nên trả trực tiếp:

~~~java
@GetMapping("/employees/{id}")
Employee getEmployee(@PathVariable UUID id) {
    return employeeRepository.findById(id).orElseThrow();
}
~~~

Controller trên có thể khiến serializer công bố mọi property mà nó nhận diện, tùy cấu hình Jackson, getter, annotation và proxy. Việc entity có field private không đảm bảo field đó không được serialize nếu có getter hoặc property accessor phù hợp.

Response DTO rõ ràng hơn:

~~~java
public record EmployeeDirectoryResponse(
    UUID id,
    String displayName,
    String department
) {}
~~~

Mapper chỉ copy field cần thiết:

~~~java
EmployeeDirectoryResponse toDirectoryResponse(Employee employee) {
    return new EmployeeDirectoryResponse(
        employee.getId(),
        employee.getDisplayName(),
        employee.getDepartment()
    );
}
~~~

Controller:

~~~java
@GetMapping("/employees/{id}")
EmployeeDirectoryResponse getEmployee(
        @AuthenticationPrincipal ApiPrincipal principal,
        @PathVariable UUID id) {
    Employee employee = employeeService.findVisibleEmployee(principal, id);
    authorization.requireCanReadDirectoryEntry(principal, employee);
    return employeeMapper.toDirectoryResponse(employee);
}
~~~

Ví dụ cần được điều chỉnh theo framework và policy thực tế. `findVisibleEmployee` phải scope theo tenant/visibility; authorization phải kiểm tra object; mapper chỉ tạo response allowlist. DTO không tự thực hiện authorization, và authorization không thay data minimization.

### 5.1. Tách request DTO và response DTO

Không dùng cùng một class cho request và response. Request chỉ chứa field caller được phép gửi; response chỉ chứa field caller được phép đọc. Hai tập field này thường khác nhau:

- `CreateOrderRequest`: product ID, quantity, shipping selection.
- `OrderResponse`: order ID, status, display total, timestamps.
- `OrderEntity`: tenant ID, fraud state, internal notes, audit fields, persistence version.

Không nhận `tenantId`, `ownerId`, `approvedBy` hoặc `isAdmin` từ request nếu server phải xác định chúng. Không trả các field này chỉ vì chúng tồn tại trên entity.

### 5.2. Projection cho query lớn

Với list/search endpoint, có thể query trực tiếp projection chỉ gồm field cần thiết thay vì load toàn entity rồi map. Điều này giảm data access, tránh lazy-loading ngoài ý muốn và làm rõ response contract.

Ví dụ JPQL projection:

~~~java
public record EmployeeRow(
    UUID id,
    String displayName,
    String department
) {}

@Query("""
    select new com.example.api.EmployeeRow(
        e.id, e.displayName, e.department
    )
    from Employee e
    where e.tenantId = :tenantId
    """)
Page<EmployeeRow> findDirectoryRows(
    UUID tenantId, Pageable pageable);
~~~

Tenant ID ở đây phải lấy từ authenticated principal/tenant context đã xác minh, không nhận trực tiếp từ query parameter như nguồn authority. Cần kiểm tra object visibility và permission theo domain policy; query projection giúp giảm field được tải nhưng không thay authorization.

## 6. Nested relationship và object graph serialization

Entity thường có quan hệ như `Employee.manager`, `Employee.payroll`, `Order.customer`, `Order.payment` hoặc `User.roles`. Serialize trực tiếp object graph có thể làm response mở rộng bất ngờ.

Rủi ro:

- Field nhạy cảm nằm trong entity liên quan bị serialize theo.
- Quan hệ hai chiều gây vòng lặp hoặc recursion.
- Lazy relationship được load ngoài dự kiến.
- N+1 query làm endpoint chậm hoặc dễ bị lạm dụng.
- Consumer nhận thêm dữ liệu chỉ vì ORM relation được thêm.
- Một object thuộc tenant khác bị lộ qua nested relationship.

Ví dụ `Order` có `customer` và `payment`; response list order không nhất thiết cần toàn bộ customer entity và payment entity. Nên định nghĩa nested DTO:

~~~java
public record CustomerSummary(UUID id, String displayName) {}

public record OrderResponse(
    UUID id,
    String status,
    BigDecimal displayTotal,
    CustomerSummary customer
) {}
~~~

Chỉ map `CustomerSummary` sau khi kiểm tra relationship đó được phép hiển thị. Không trả `PaymentEntity` đầy đủ chỉ để lấy `payment.status`.

### 6.1. Collection và pagination

Không serialize toàn bộ collection như `customer.orders` hoặc `employee.auditEvents` trong một response. Dùng endpoint riêng, pagination, field selection được kiểm soát và quota. Limit số item, depth và response size.

### 6.2. GraphQL và field resolver

GraphQL cho phép client chọn field, nhưng việc client không yêu cầu field không phải là authorization. Một caller có thể thêm field nhạy cảm vào selection set. Mỗi resolver/field nhạy cảm phải kiểm tra permission và object scope; schema visibility không thay runtime authorization nếu caller có thể truy vấn field.

## 7. Các annotation serializer không phải chiến lược allowlist chính

Jackson có các annotation như `@JsonIgnore`, `@JsonProperty`, `@JsonView` hoặc custom serializer. Chúng hữu ích cho serialization behavior, nhưng dùng trực tiếp trên entity để quản lý security có thể tạo coupling và policy khó kiểm soát.

### 7.1. `@JsonIgnore`

Có thể dùng `@JsonIgnore` như lớp phòng vệ bổ sung cho một field tuyệt đối không được serialize qua bất kỳ API nào. Tuy nhiên:

- Role-specific visibility không thể chỉ dựa vào một annotation tĩnh.
- Một endpoint nội bộ có thể cần field mà endpoint public không được trả.
- Annotation có thể bị override bằng mixin/configuration hoặc serializer khác.
- Developer có thể thêm field mới mà không nhận ra cần annotation.
- Serialization của nested object vẫn cần review.

Không coi `@JsonIgnore` là thay thế cho response DTO và field policy.

### 7.2. `@JsonView`

`@JsonView` có thể tạo các view khác nhau, nhưng cần bảo đảm view được chọn từ server-side policy và mọi endpoint đều chọn đúng view. Nếu controller mặc định dùng view rộng hoặc client có thể điều khiển view, field nhạy cảm có thể bị lộ. Nhiều view chồng lấn cũng khó review khi role và tenant policy phức tạp.

### 7.3. Custom serializer và response advice

Serializer/filter có thể hữu ích cho cross-cutting behavior như redaction hoặc format. Nếu dùng để enforce field authorization, cần:

- Policy rõ ràng và fail-closed khi không có access context.
- Không dùng role/tenant header chưa xác minh.
- Xử lý nested object và collection nhất quán.
- Test mọi endpoint, error path và API version.
- Không mutate shared entity hoặc response state giữa request.

Với phần lớn API business, DTO/projection theo use case dễ audit hơn việc serialize entity rồi xóa field ở cuối pipeline.

## 8. Cache, ETag và response reuse

Ngay cả khi server tạo response đúng cho một user, cache sai key có thể đưa response đó đến user khác. Điều này đặc biệt nguy hiểm với field hiển thị theo role hoặc tenant.

Kiểm tra:

- Public response có thực sự public không?
- Private response có `Cache-Control` phù hợp không?
- Shared proxy/CDN có cache response chứa dữ liệu cá nhân không?
- Cache key có bao gồm mọi dimension cần thiết như tenant, locale hoặc permission version không?
- ETag có vô tình xác nhận resource khác tenant hoặc tiết lộ state không?
- Khi permission bị revoke, cached response có bị invalidate hoặc hết hạn đủ nhanh không?
- Service worker/mobile cache có giữ dữ liệu sau logout hoặc account switch không?

Với response chứa dữ liệu nhạy cảm, thường cần `Cache-Control: private` hoặc `no-store` tùy use case và threat model. Không dựa vào frontend xóa cache như lớp duy nhất; server/proxy và client storage policy phải được thiết kế cùng nhau.

Không dùng một cached superset response rồi để client tự lọc field theo role. Cache phải chứa đúng representation được phép cho cache key đó, hoặc cache dữ liệu nội bộ ở server rồi tạo response DTO theo principal mỗi lần trả.

## 9. Logging, tracing và error response

Sau khi bỏ field khỏi response chính, vẫn cần kiểm tra dữ liệu không bị lộ qua error, log hoặc trace.

- Không log raw entity hoặc full response nếu có field nhạy cảm.
- Không log token, password verifier, API key, bank data hoặc internal note.
- Redact theo schema/data classification, không chỉ theo tên field.
- Error message không trả rejected entity hoặc object dump.
- Trace attribute không chứa PII/secret hoặc nested object.
- Audit lưu thông tin đủ truy vết nhưng chỉ cho role được phép.
- Analytics chỉ nhận field cần thiết và có retention/access control.

Ví dụ không an toàn:

~~~java
catch (Exception ex) {
    log.error("Failed to return employee: {}", employee, ex);
    throw ex;
}
~~~

Nếu entity `toString()` bao gồm field nhạy cảm, log sẽ tạo thêm bản sao của dữ liệu. Nên log ID/operation code đã được kiểm soát và exception class/correlation ID phù hợp, không dump toàn entity.

## 10. Field masking khác với field authorization

Masking thường hiển thị một phần giá trị, ví dụ email `a***@example.com` hoặc số tài khoản chỉ còn bốn số cuối. Masking có thể là cách giảm lộ dữ liệu khi caller có quyền xem một representation giới hạn. Nó không thay authorization.

| Tình huống | Cách xử lý |
|---|---|
| Caller không có quyền đọc field | Không trả field hoặc trả representation theo contract đã định nghĩa |
| Caller được phép xem nhưng chỉ cần nhận diện một phần | Server tạo masked value |
| Caller được phép xem đầy đủ theo purpose | Server trả field đầy đủ qua endpoint/DTO phù hợp |
| Client tự che giá trị sau khi nhận | Không bảo vệ dữ liệu đã truyền |

Không trả cả raw value và masked value rồi hy vọng client chỉ dùng masked version. Nếu caller không được đọc raw value, raw value không được xuất hiện trong response.

## 11. Kiểm thử để chứng minh field nhạy cảm không bị serialize

Security test phải kiểm tra raw HTTP response body, không chỉ component rendering. Tạo fixture có marker duy nhất cho field nhạy cảm để dễ phát hiện rò rỉ.

Ví dụ fixture:

~~~text
displayName = TEST_EMPLOYEE_104
salary = SECRET_SALARY_MARKER_9F2
bankAccount = SECRET_BANK_MARKER_7C1
internalNote = SECRET_NOTE_MARKER_5D4
~~~

Sau đó gọi API bằng nhiều principal và assert:

- User không có quyền không nhận raw field.
- Field không xuất hiện trong nested object, array hoặc metadata.
- Field không xuất hiện trong error response.
- Field không xuất hiện trong log/trace test sink.
- Response DTO chỉ có các property được contract công bố.
- Entity thêm field mới không làm response tự động thêm property.

### 11.1. Ma trận test theo actor và endpoint

| Endpoint/use case | Actor | Kết quả mong đợi |
|---|---|---|
| Directory list | Anonymous/public caller nếu endpoint public | Chỉ field public |
| Directory detail | Employee thường | Field directory, không salary/bank/internal note |
| Self profile | Chính employee | Field self-service được phép |
| Employee detail | Manager cùng team | Chỉ field theo manager policy |
| Employee detail | Manager team khác | Deny hoặc mask theo policy |
| HR record | HR role | Field HR được phép theo purpose |
| Payroll summary | Payroll service identity | Chỉ field payroll và tenant/period được cấp |
| Admin endpoint | User thường | Không nhận admin-only field |
| Cross-tenant lookup | Principal tenant A yêu cầu employee tenant B | Không lộ object hoặc field |
| Search/export | Caller thông thường | Không có field nhạy cảm qua alternate route |

### 11.2. Assert absence, không chỉ assert giá trị null

Field bị cấm tốt nhất là không xuất hiện trong JSON. `salary: null` vẫn có thể tiết lộ schema, sự tồn tại của field hoặc tạo hiểu nhầm rằng client có thể yêu cầu field sau này. Contract có thể quy định null cho một số trường hợp, nhưng phải là quyết định có chủ đích.

Test cần phân biệt:

- Field không tồn tại trong JSON.
- Field có giá trị `null`.
- Field có giá trị masked.
- Field có giá trị thật.

Không dùng assertion quá rộng kiểu “response không chứa từ salary” nếu có thể xuất hiện trong mô tả public hợp lệ. Parse JSON và kiểm tra property path chính xác, bao gồm nested arrays.

### 11.3. Regression test khi entity thay đổi

Thêm một field nhạy cảm giả vào entity trong test fixture hoặc test mapping contract để chứng minh DTO không tự serialize field mới. Kiểm tra OpenAPI/schema snapshot hoặc explicit property allowlist. Đây là cách phát hiện việc thêm property vào entity không vô tình mở rộng API response.

## 12. Ví dụ kiểm thử Spring Boot

Ví dụ dùng `MockMvc` để kiểm tra response contract:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class EmployeeResponseSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "employee-104", authorities = "profile:read")
    void selfProfileDoesNotExposeInternalFields() throws Exception {
        mvc.perform(get("/v1/employees/emp-104"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").exists())
            .andExpect(jsonPath("$.department").exists())
            .andExpect(jsonPath("$.salary").doesNotExist())
            .andExpect(jsonPath("$.bankAccount").doesNotExist())
            .andExpect(jsonPath("$.internalNote").doesNotExist())
            .andExpect(jsonPath("$.admin").doesNotExist());
    }
}
~~~

`@WithMockUser` minh họa việc cung cấp principal/authority trong test; nó không chứng minh JWT signature, issuer, audience hoặc tenant claim mapping hoạt động. Cần thêm test qua resource server filter với token test được ký đúng. Test object authorization cũng phải dùng fixture nhiều tenant và xác minh repository/service scope.

Ví dụ mapper allowlist có thể test độc lập:

~~~java
@Test
void directoryMapperOnlyMapsApprovedFields() {
    Employee entity = employeeWithSensitiveMarkers();

    EmployeeDirectoryResponse response =
        mapper.toDirectoryResponse(entity);

    assertThat(response.displayName()).isEqualTo("TEST_EMPLOYEE_104");
    assertThat(objectMapper.valueToTree(response).toString())
        .doesNotContain("SECRET_SALARY_MARKER_9F2")
        .doesNotContain("SECRET_BANK_MARKER_7C1")
        .doesNotContain("SECRET_NOTE_MARKER_5D4");
}
~~~

Test mapper không thay test endpoint đầy đủ: cần xác minh controller chọn đúng DTO, security filter hoạt động và mọi alternate endpoint cũng không lộ field.

## 13. Những anti-pattern liên quan

| Anti-pattern | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
| Trả trực tiếp JPA entity | Field mới/quan hệ mới có thể tự xuất hiện trong JSON | Response DTO/projection allowlist |
| Trả superset DTO cho mọi role | Một role có thể nhận field ngoài quyền | DTO/use case hoặc field policy server-side |
| Chỉ ẩn field bằng CSS/JavaScript | Raw response vẫn chứa dữ liệu | Không serialize field không được phép |
| Dựa vào `@JsonIgnore` cho mọi policy | Annotation tĩnh khó biểu diễn role/object/tenant | DTO và authorization policy |
| Dùng chung request/response DTO | Field input và output có quyền khác nhau | Tách request model và response model |
| Serialize nested entity graph | Lộ quan hệ, lazy data hoặc cross-tenant field | Nested DTO và relationship authorization |
| Trả raw entity trong error | Stack/error/log có thể chứa secret và PII | Error contract tối thiểu, log có kiểm soát |
| Cache superset response | Caller khác có thể nhận field của role trước | Cache đúng representation hoặc map theo principal |
| Dùng client-selected field list như quyền | Caller tự yêu cầu field nhạy cảm | Server-side allowlist và authorization |
| Thêm field entity mà không review API | Data exposure xảy ra âm thầm | Contract diff và serialization regression test |

## 14. Checklist review response serialization

- [ ] Controller không trả trực tiếp persistence entity hoặc ORM graph.
- [ ] Mỗi endpoint có response DTO/projection theo use case.
- [ ] DTO chỉ chứa field được contract cho phép.
- [ ] Request DTO và response DTO được tách biệt.
- [ ] Function, object, tenant và field authorization chạy ở server trước serialization.
- [ ] Principal, tenant và role lấy từ trusted security context, không từ client field/header tùy ý.
- [ ] Nested relationship được kiểm tra quyền và chỉ map summary cần thiết.
- [ ] Collection, pagination, depth và response size có giới hạn.
- [ ] Field secret/restricted không có trong public DTO.
- [ ] Masking được tạo ở server và không gửi kèm raw value.
- [ ] `@JsonIgnore`, `@JsonView` hoặc custom serializer chỉ là cơ chế hỗ trợ có test, không phải policy duy nhất.
- [ ] Cache key, `Cache-Control`, ETag và client storage phù hợp với dữ liệu/role/tenant.
- [ ] Log, trace, analytics và error response không dump entity hoặc secret.
- [ ] Test raw HTTP response cho nhiều actor, role, tenant và API version.
- [ ] Negative test assert field bị cấm không xuất hiện trong JSON, kể cả nested path.
- [ ] Test kiểm tra database và side effect khi caller bị deny.
- [ ] Contract/schema diff phát hiện field response mới trước release.
- [ ] Có regression test chứng minh thêm entity property không tự mở rộng response.

Serialize entity đầy đủ rồi che field ở client biến persistence model thành một contract công khai ngoài ý muốn. Dữ liệu đã được gửi thì caller có thể đọc, lưu hoặc chuyển tiếp dù giao diện không hiển thị. Thiết kế an toàn bắt đầu từ server: xác định actor, tenant, object và purpose; áp dụng field-level authorization; map sang DTO/projection allowlist; rồi kiểm tra raw response, cache, log và nested relationship. Cách này giảm rò rỉ dữ liệu, giữ API contract ổn định và bảo đảm mỗi endpoint chỉ công bố đúng thông tin mà caller được phép nhận.

# Broken Object Property Level Authorization

## 1. BOPLA là gì?

Broken Object Property Level Authorization (BOPLA) xảy ra khi API cho phép người gọi đọc hoặc thay đổi những thuộc tính của một đối tượng mà họ không được phép truy cập. API có thể đã xác thực người dùng, kiểm tra họ được phép truy cập đối tượng và giới hạn đúng endpoint, nhưng vẫn để lộ hoặc cho sửa một số field bên trong đối tượng.

Ví dụ, người dùng được xem hồ sơ của chính mình qua GET /users/123. Response trả thêm internalRiskScore, roles, accountStatus và thông tin kiểm duyệt mà người dùng không có quyền xem. Ở chiều ghi, endpoint PATCH /users/123 nhận cả role, tenantId, emailVerified hoặc creditLimit rồi bind thẳng vào entity. Người dùng có quyền sửa displayName nhưng có thể tự nâng vai trò hoặc thay đổi hạn mức.

Trong OWASP API Security Top 10 năm 2023, BOPLA là API3:2023. Nhóm rủi ro này bao gồm hai dạng thường gặp:

- **Excessive Data Exposure:** API trả nhiều thuộc tính hơn mức người gọi cần hoặc được phép xem. Việc giao cho frontend tự ẩn field không bảo vệ dữ liệu vì client vẫn nhận được toàn bộ response.
- **Mass Assignment:** API tự động bind các thuộc tính do client gửi vào object hoặc model nội bộ, khiến client sửa được những field không được phép thay đổi.

Không phải mọi lỗi validation đều là BOPLA. Một field có thể đúng kiểu dữ liệu, đúng định dạng và vẫn không được phép đọc hoặc ghi bởi principal hiện tại. Authorization phải được thực hiện theo từng thuộc tính và ngữ cảnh nghiệp vụ.

## 2. Phân biệt BOPLA, BOLA và BFLA

Ba loại lỗi có thể xuất hiện đồng thời nhưng câu hỏi kiểm soát khác nhau:

| Rủi ro | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Broken Function Level Authorization (BFLA) | Người gọi có được phép thực hiện chức năng này không? | User thông thường gọi endpoint quản trị để khóa tài khoản |
| Broken Object Level Authorization (BOLA) | Người gọi có được phép truy cập đối tượng này không? | User A đổi ID đơn hàng để đọc đơn hàng của B |
| Broken Object Property Level Authorization (BOPLA) | Người gọi có được phép đọc hoặc thay đổi field này trên đối tượng này không? | User đọc internalNotes hoặc tự sửa accountStatus của hồ sơ mình |

Một request có thể vượt qua hai lớp đầu nhưng vẫn mắc BOPLA. Ví dụ user có quyền xem đơn hàng của mình, nhưng response chứa fraudReviewNotes chỉ dành cho nhân viên kiểm soát. Hoặc user có quyền cập nhật địa chỉ giao hàng, nhưng payload còn cho phép sửa customerId và paymentStatus.

Do đó, authorization ở cấp endpoint hoặc object không thay thế authorization ở cấp property.

## 3. Thuộc tính cần bảo vệ không chỉ là field trong database

Property có thể là:

- Field lưu trực tiếp trong entity hoặc bảng dữ liệu: email, phone, salary, balance, role.
- Field lồng trong object: shippingAddress.country, payment.cardLast4, employee.manager.compensation.
- Field được tính toán: riskScore, eligibility, availableCredit, isAdmin.
- Metadata: ownerId, tenantId, createdBy, moderationStatus, internalTags.
- Quan hệ và collection: danh sách thành viên, quyền chia sẻ, danh sách người nhận.
- Field được lấy từ dịch vụ khác: trạng thái xác minh, thông tin tín dụng hoặc dữ liệu định danh.
- Giá trị trong command hoặc sự kiện: approvedBy, refundedAmount, workflowState.

Không chỉ response JSON mới có nguy cơ. Property có thể bị lộ qua export CSV, GraphQL, WebSocket, webhook, thông báo, báo cáo, log, cache, tìm kiếm hoặc endpoint tải tệp. Quy tắc bảo vệ cần áp dụng cho mọi đường đưa dữ liệu ra ngoài và mọi đường nhận dữ liệu có thể thay đổi trạng thái.

## 4. Threat model và các tình huống thường gặp

| Tình huống | Cách khai thác | Tác động |
|---|---|---|
| Response trả entity đầy đủ | Gọi endpoint hợp lệ rồi đọc field nội bộ trong JSON | Lộ dữ liệu riêng tư, thông tin vận hành hoặc chống gian lận |
| Frontend chỉ ẩn field | Mở DevTools hoặc gọi API trực tiếp | Lộ dữ liệu dù giao diện không hiển thị |
| Mass assignment | Thêm field ngoài form vào JSON request | Nâng quyền, đổi owner, xác minh email giả hoặc sửa trạng thái |
| Nested property | Gửi object con chứa ownerId hoặc permission | Thay đổi quyền hoặc quan hệ ngoài dự kiến |
| JSON Patch | Dùng path trỏ vào field nhạy cảm | Sửa thuộc tính bị cấm thông qua thao tác patch |
| GraphQL field selection | Yêu cầu field nhạy cảm hoặc truy vấn qua quan hệ | Lộ thuộc tính mà REST endpoint đã ẩn |
| Export và báo cáo | Dùng chức năng tải dữ liệu có projection rộng | Rò rỉ dữ liệu hàng loạt |
| Race condition | Gửi update đồng thời hoặc cập nhật sau khi trạng thái thay đổi | Vượt quy tắc field phụ thuộc workflow |

Tác nhân có thể là người dùng hợp lệ tò mò, tài khoản bị chiếm quyền, client mobile cũ, đối tác tích hợp hoặc service nội bộ cấu hình sai. Không cần giả định kẻ tấn công có quyền truy cập database; chỉ cần endpoint nhận hoặc trả property vượt chính sách.

## 5. Xác định quyền theo principal, object, property và hành động

Quyết định property authorization nên dựa trên nhiều yếu tố:

1. **Principal:** người dùng, service account hoặc client đã được xác thực.
2. **Tenant và phạm vi tổ chức:** principal đang hoạt động trong tenant nào và có quyền ở phạm vi nào.
3. **Object:** đối tượng cụ thể, chủ sở hữu, trạng thái và quan hệ của nó.
4. **Property:** field hoặc nhóm field đang được đọc/thay đổi.
5. **Action:** read, create, update, append, delete, approve, export hoặc transition.
6. **Business context:** trạng thái workflow, mức độ xác minh, quan hệ với khách hàng, mục đích xử lý và thời điểm.
7. **Request context:** nguồn gọi, loại client, mức xác thực hoặc bước xác thực tăng cường nếu nghiệp vụ yêu cầu.

Ví dụ một nhân viên hỗ trợ có thể đọc email và trạng thái đơn hàng để giải quyết yêu cầu, nhưng không được đọc toàn bộ thông tin thanh toán. Nhân viên kiểm soát gian lận có thể xem riskScore và reviewNotes, nhưng không được sửa chúng. Người dùng có thể sửa phone và displayName của hồ sơ mình, nhưng không thể sửa role, tenantId hoặc emailVerified.

Quyền không nên được suy ra chỉ từ tên role. Cùng một vai trò có thể có quyền khác nhau theo tenant, đối tượng, trạng thái hoặc quan hệ công việc. Nên biểu diễn chính sách theo dạng principal + action + resource + property + context.

## 6. Phân loại property và lập ma trận quyền

Trước khi triển khai, phân loại các field của từng resource:

| Nhóm property | Ví dụ | Quy tắc điển hình |
|---|---|---|
| Công khai | displayName công khai, avatar đã công bố | Có thể đọc công khai; vẫn cần kiểm soát nội dung và cập nhật |
| Cá nhân | email, phone, địa chỉ | Chủ thể hoặc người được ủy quyền mới được đọc |
| Nhạy cảm | số định danh, dữ liệu thanh toán, lương | Quyền hẹp, có thể yêu cầu xác thực tăng cường và audit |
| Nội bộ | riskScore, moderationNotes, fraudFlags | Chỉ service hoặc nhóm nghiệp vụ được chỉ định |
| Bất biến/được hệ thống quản lý | id, createdAt, tenantId, ownerId | Client không được tự ghi; server gán hoặc quản lý |
| Điều khiển quyền | role, permissions, accessLevel | Chỉ luồng quản trị được ủy quyền mới thay đổi |
| Trạng thái workflow | approved, paid, refunded, verified | Chỉ thay đổi qua command hợp lệ theo state machine |

Ví dụ ma trận quyền cho resource User:

| Property | Chủ tài khoản | Nhân viên hỗ trợ | Quản trị tenant | Service xác minh |
|---|---|---|---|---|
| displayName | Đọc, sửa | Đọc | Đọc | Không cần |
| email | Đọc, sửa theo flow xác minh | Đọc có điều kiện | Đọc theo chính sách | Đọc để xác minh |
| phone | Đọc, sửa theo flow xác minh | Đọc có điều kiện | Đọc theo chính sách | Đọc để xác minh |
| role | Không | Không | Chỉ qua luồng quản trị | Không |
| tenantId | Không | Không | Không sửa trực tiếp | Không |
| emailVerified | Không sửa | Không sửa | Không sửa trực tiếp | Chỉ service xác minh cập nhật |
| internalRiskScore | Không | Không | Không mặc định | Chỉ service/chức năng được cấp quyền |

Ma trận chỉ là ví dụ. Phải được điều chỉnh theo mô hình tổ chức và trách nhiệm thực tế. Ghi rõ cả quyền đọc và quyền ghi; một field có thể được đọc nhưng không được sửa, hoặc được sửa qua một command chuyên biệt mà không cho phép cập nhật trực tiếp.

## 7. Bảo vệ property khi đọc response

### 7.1 Không serialize trực tiếp entity

Không trả thẳng JPA entity, ORM model hoặc object nội bộ ra API. Entity thường chứa field phục vụ persistence, quan hệ lazy-loaded, cờ nội bộ và dữ liệu mà client không cần.

Ví dụ thiết kế dễ mắc lỗi:

~~~java
@GetMapping("/users/{id}")
public UserEntity getUser(@PathVariable UUID id) {
    return userRepository.findById(id).orElseThrow();
}
~~~

Serializer có thể xuất toàn bộ field được cấu hình public hoặc vô tình truy cập quan hệ. Việc thêm field mới vào entity cũng có thể làm response mở rộng mà không ai rà soát API contract.

Thay vào đó, định nghĩa response DTO chứa đúng những property endpoint được phép trả:

~~~java
public record UserProfileResponse(
    UUID id,
    String displayName,
    String email
) {}
~~~

Service kiểm tra quyền object trước, sau đó chỉ map field được phép:

~~~java
public UserProfileResponse getMyProfile(Principal actor) {
    User user = userRepository.findById(actor.userId())
        .orElseThrow(UserNotFoundException::new);

    authorization.requireCanReadProfile(actor, user);

    return new UserProfileResponse(
        user.getId(),
        user.getDisplayName(),
        authorization.canReadEmail(actor, user)
            ? user.getEmail()
            : null
    );
}
~~~

Trong ví dụ này, null chỉ phù hợp nếu API contract quy định rõ field có thể bị ẩn bằng null. Nếu cần phân biệt field không được phép xem với field thật sự không có giá trị, hãy dùng DTO/representation riêng hoặc bỏ field khỏi response theo contract. Không vô tình biến việc ẩn dữ liệu thành một tín hiệu làm lộ sự tồn tại hoặc trạng thái nội bộ.

### 7.2 Dùng response DTO riêng theo use case

Một UserProfileResponse cho chủ tài khoản, một SupportUserSummaryResponse cho nhân viên hỗ trợ và một RiskReviewResponse cho nhóm kiểm soát thường dễ kiểm tra hơn một entity lớn có hàng chục điều kiện serialize.

Không cần tạo một DTO cho mọi role nếu các field giống nhau. Hãy tách theo use case và tập dữ liệu được phép, tránh logic phân quyền bị rải rác trong controller, serializer và frontend.

### 7.3 Projection ngay tại truy vấn

Khi dữ liệu lớn hoặc có field nhạy cảm, chỉ truy vấn cột cần dùng. Projection giảm khả năng field ngoài ý muốn đi vào object trung gian, cache hoặc log.

Ví dụ truy vấn cho màn hình hỗ trợ có thể chỉ chọn id, displayName, email và accountStatus. Không tải passwordHash, riskScore hay paymentDetails nếu use case không cần. Đây là biện pháp giảm dữ liệu và hiệu năng; quyết định quyền vẫn cần được kiểm tra trước khi trả.

### 7.4 Kiểm soát dữ liệu lồng nhau và quan hệ

Không chỉ lọc field ở cấp ngoài cùng. Một response có thể lộ dữ liệu qua object con:

~~~json
{
  "id": "order-123",
  "shippingAddress": {
    "city": "Da Nang",
    "recipientPhone": "..."
  },
  "payment": {
    "cardLast4": "1234",
    "processorReference": "internal-ref"
  }
}
~~~

Người dùng có thể được xem địa chỉ giao hàng nhưng không được xem processorReference. Cần định nghĩa DTO lồng nhau riêng, kiểm tra quyền trên từng nhóm field và tránh serialize object quan hệ trực tiếp.

Quyền xem một object cha không tự động cấp quyền xem mọi object con. Tương tự, quyền xem một collection không đồng nghĩa được đọc mọi thuộc tính của từng phần tử.

## 8. Bảo vệ property khi ghi request

### 8.1 Dùng request DTO allowlist

Không bind JSON client gửi trực tiếp vào entity:

~~~java
@PatchMapping("/users/{id}")
public UserEntity update(
    @PathVariable UUID id,
    @RequestBody UserEntity body
) {
    // Không an toàn: client có thể gửi mọi field có setter.
    return userRepository.save(body);
}
~~~

Thay bằng DTO chỉ chứa field được phép cập nhật trong use case:

~~~java
public record UpdateMyProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,
    @Pattern(regexp = "^[0-9+ -]{7,20}$")
    String phone
) {}
~~~

Controller hoặc application service lấy user ID từ principal, tìm object trong tenant đúng, kiểm tra quyền và chỉ cập nhật các field trong DTO:

~~~java
public void updateMyProfile(
    Principal actor,
    UpdateMyProfileRequest request
) {
    User user = userRepository.findById(actor.userId())
        .orElseThrow(UserNotFoundException::new);

    authorization.requireCanUpdateProfile(actor, user);
    user.changeDisplayName(request.displayName());
    user.changePhone(request.phone());
    userRepository.save(user);
}
~~~

Client không thể tự truyền id, tenantId, role, ownerId hoặc emailVerified qua DTO này. Nếu nghiệp vụ cho phép đổi email hoặc thay đổi quyền, hãy tạo command/endpoint chuyên biệt với xác minh và audit phù hợp.

### 8.2 Không dùng entity làm request model

Những field như role, tenantId, ownerId, balance, creditLimit, approvedAt, verified, passwordHash, createdAt và internalNotes thường do server quản lý. Không đưa chúng vào request DTO thông thường.

Ẩn field bằng annotation serializer không đủ để bảo vệ chiều ghi. Một field bị ẩn khỏi response vẫn có thể được binder cập nhật nếu request được bind vào entity. Cần tách request model và response model.

### 8.3 Cập nhật một phần và ngữ nghĩa null

PATCH cần quy định rõ ba trạng thái:

- Field không xuất hiện: giữ nguyên giá trị hiện tại.
- Field xuất hiện với giá trị hợp lệ: cập nhật.
- Field xuất hiện với null: xóa giá trị, đặt rỗng hay từ chối theo contract.

Không dùng một DTO với primitive/default value khiến server không phân biệt field vắng mặt với field được gửi giá trị mặc định. Có thể dùng wrapper, Optional theo quy ước rõ ràng, JsonNullable hoặc một command model có trạng thái presence riêng.

Với JSON Merge Patch, null thường biểu thị xóa member; với JSON Patch, mỗi operation có path và op riêng. Cần hiểu đúng semantics mà API công bố, kiểm tra property allowlist và xác thực kiểu dữ liệu trước khi áp dụng.

### 8.4 JSON Patch và đường dẫn property

JSON Patch cho phép thao tác add, remove, replace, move, copy và test trên path. Nếu chỉ kiểm tra object ở cấp cao, người gọi có thể thử path như /role, /tenantId, /payment/status hoặc đường dẫn lồng sâu.

Biện pháp:

- Allowlist operation và path cụ thể cho endpoint.
- Từ chối path tới field bất biến, field nội bộ hoặc quan hệ ngoài quyền.
- Chuẩn hóa và giải mã JSON Pointer đúng một lần; kiểm tra escape như ~0 và ~1.
- Kiểm tra quyền trên cả nguồn và đích của move/copy.
- Giới hạn độ sâu, số operation và kích thước patch.
- Áp dụng patch trên command/DTO được phép, không trực tiếp trên entity đầy đủ.
- Thực hiện kiểm tra business invariant sau khi áp dụng thay đổi.

Nếu use case chỉ cần đổi displayName và phone, DTO allowlist thường đơn giản hơn hỗ trợ JSON Patch tổng quát.

## 9. Property authorization phải gắn với nghiệp vụ

Một số field chỉ được sửa ở một thời điểm nhất định. Ví dụ:

- shippingAddress được sửa khi đơn hàng chưa đóng gói.
- paymentMethod được sửa trước khi thanh toán.
- refundAmount chỉ được tạo bởi luồng hoàn tiền có kiểm tra số tiền đã thanh toán.
- email chỉ được thay sau khi xác minh địa chỉ mới.
- role chỉ được thay bởi người quản trị có quyền quản lý thành viên trong tenant.
- approvedAt và approvedBy được tạo bởi hành động approve, không phải payload cập nhật chung.

Không cho client sửa trực tiếp workflow state bằng cách gửi status=APPROVED hoặc paymentStatus=PAID. Thay vào đó, cung cấp command rõ nghĩa như POST /orders/{id}/approve hoặc POST /payments/{id}/refund; server kiểm tra vai trò, quyền trên object, trạng thái hiện tại và điều kiện chuyển trạng thái.

Field-level authorization không thể chỉ là danh sách field theo role tĩnh. Nó cần xem xét business state và các điều kiện nghiệp vụ. Một user có thể sửa địa chỉ trước khi đơn hàng được xử lý nhưng không được sửa sau khi hàng đã gửi.

## 10. Kiểm tra property ở tầng nào?

Không có một annotation hay middleware đơn lẻ giải quyết mọi trường hợp. Có thể phân chia trách nhiệm:

| Lớp | Trách nhiệm |
|---|---|
| API schema / DTO | Giới hạn field đầu vào và đầu ra theo use case; validation kiểu, độ dài và định dạng |
| Controller / API adapter | Xác thực request, lấy principal đáng tin, chọn command/response phù hợp |
| Application service | Thực thi property authorization theo principal, object, action và business context |
| Domain model | Bảo vệ invariant; chỉ cung cấp method nghiệp vụ hợp lệ để thay đổi trạng thái |
| Repository / query | Lọc tenant/object và projection đúng phạm vi; tránh tải dữ liệu dư |
| Serializer / GraphQL resolver | Chỉ trả property đã được cho phép; không dựa vào frontend để ẩn field |
| Audit / monitoring | Ghi nhận truy cập hoặc thay đổi field nhạy cảm mà không log giá trị bí mật |

Với field tĩnh và endpoint đơn giản, DTO riêng có thể đủ để giảm bề mặt. Với field phụ thuộc object, vai trò hoặc trạng thái, application service cần gọi policy chuyên biệt. Với hệ thống lớn, có thể dùng policy engine nhưng phải bảo đảm policy nhận đúng principal và resource đã được tải trong tenant hợp lệ.

### 10.1 Mô hình policy có thể tái sử dụng

Một policy decision có thể có dạng:

~~~text
canReadProperty(principal, resource, property, context)
canWriteProperty(principal, resource, property, context)
~~~

Ví dụ:

~~~java
boolean canReadEmail(Principal actor, User target) {
    return actor.userId().equals(target.getId())
        || supportPolicy.canReadContact(actor, target);
}

boolean canWriteRole(Principal actor, User target) {
    return tenantAdminPolicy.canManageMembers(actor, target.getTenantId())
        && !target.isProtectedSystemAccount();
}
~~~

Đây là ví dụ minh họa. Các policy thực tế cần kiểm tra tenant, object ownership, quan hệ quản trị, trạng thái và quyền được cấp. Không viết policy chỉ dựa vào một chuỗi role do client gửi.

### 10.2 Fail closed và kiểm tra nhất quán

Nếu policy không xác định được hoặc policy service lỗi, không tự động cho phép đọc/ghi field nhạy cảm. Từ chối có kiểm soát hoặc trả lỗi dịch vụ tùy kiến trúc. Không có quy tắc mặc định “field không biết thì cho qua”.

Nếu cùng một field xuất hiện ở nhiều endpoint, export, GraphQL resolver và event consumer, hãy dùng policy chung hoặc cùng một định nghĩa quyền. Tránh một endpoint ẩn field nhưng endpoint khác trả field đó mà không có kiểm soát tương đương.

## 11. GraphQL, field selection và API linh hoạt

GraphQL cho client tự chọn field cần đọc. Điều này giúp giảm dữ liệu truyền nhưng không phải cơ chế authorization. Client có thể yêu cầu field mà schema công khai hoặc resolver cho phép truy vấn; server vẫn phải quyết định principal hiện tại có quyền xem field đó trên object cụ thể hay không.

Ví dụ:

~~~graphql
query {
  user(id: "123") {
    displayName
    email
    internalRiskScore
  }
}
~~~

Resolver cho internalRiskScore phải kiểm tra quyền riêng. Không chỉ kiểm tra quyền ở resolver user rồi mặc định mọi field con đều được phép. Với nested resolver, phải kiểm tra quan hệ và tenant, tránh N+1 query hoặc DataLoader dùng chung dữ liệu giữa principal khác nhau.

Ở chiều ghi, GraphQL input type nên chỉ chứa field được phép cho mutation đó. Không dùng một UserInput chung gồm mọi thuộc tính của entity cho cả create, update profile và admin management.

Các API hỗ trợ field mask, sparse fieldset hoặc query parameter fields cũng cần allowlist field. Nếu client yêu cầu field không được phép, có thể từ chối hoặc loại bỏ theo contract, nhưng không được trả field chỉ vì nó xuất hiện trong danh sách yêu cầu.

## 12. Tạo và cập nhật object: phân quyền property theo từng operation

Property được phép khi tạo object có thể khác property được phép khi cập nhật. Ví dụ:

| Operation | Field do client cung cấp | Field do server quản lý |
|---|---|---|
| Create user | displayName, email, phone | id, tenantId, role mặc định, emailVerified, createdAt |
| Update profile | displayName, phone | ownerId, tenantId, role, createdAt |
| Admin invite | email, nhóm quyền được phép cấp | inviterId, tenantId, inviteStatus, expiry |
| Approve request | decision, reason trong giới hạn | approvedBy, approvedAt, state transition |
| Refund payment | amount trong giới hạn, reason | payment reference, refund status, ledger entry |

Không tái sử dụng một DTO quá rộng chỉ để tránh tạo nhiều class. Mỗi command nên thể hiện ý định nghiệp vụ và chỉ cho phép tập field cần thiết. Server gán các field do hệ thống quản lý dựa trên principal và trạng thái thực tế.

Khi cập nhật quan hệ, không nhận object lồng đầy đủ từ client rồi lưu cascade một cách tự động. Dùng ID tham chiếu, tải object trong tenant hiện tại, kiểm tra quyền liên kết và chỉ thay đổi quan hệ qua domain method được phép.

## 13. Lỗi phản hồi và side channel

API cần chọn cách phản hồi nhất quán khi người gọi không được phép đọc hoặc ghi property:

- Với field không được phép đọc, có thể bỏ field khỏi response hoặc dùng representation riêng theo contract.
- Với request cố ghi field bị cấm, thường trả 400 hoặc 403 tùy quy ước API: 400 nếu field không thuộc schema/command được hỗ trợ; 403 nếu field được nhận diện nhưng principal không được phép thay đổi.
- Không trả giá trị hiện tại của field nhạy cảm trong thông báo lỗi.
- Không tiết lộ policy nội bộ, tên nhóm quản trị hoặc lý do chống gian lận chi tiết.
- Không để khác biệt lỗi vô tình tiết lộ object có tồn tại hay không khi BOLA/tenant isolation cũng là mối quan tâm.

Phải nhất quán giữa các endpoint. Nếu API im lặng loại bỏ field bị cấm, client có thể tưởng update thành công. Nếu API từ chối, thông báo nên chỉ rõ field nào không được hỗ trợ mà không tiết lộ giá trị hoặc dữ liệu khác. Tài liệu API cần mô tả hành vi này.

## 14. Bảo vệ property ở cache, event và các kênh phụ

Một field bị ẩn ở response chính vẫn có thể bị lộ qua:

- Cache HTTP hoặc cache nội bộ không phân vùng theo tenant/principal.
- Search index, autocomplete, export và báo cáo.
- Webhook hoặc event chứa snapshot đầy đủ của entity.
- Notification, email, audit log và analytics.
- GraphQL subscription hoặc WebSocket message.
- File download, backup và data lake.

Khi publish event, nên tạo event DTO riêng với các field cần cho consumer thay vì serialize toàn bộ entity. Mỗi consumer chỉ nhận dữ liệu phù hợp với quyền và mục đích. Không dùng event nội bộ đầy đủ làm payload webhook công khai.

Cache phải phân biệt representation theo đúng phạm vi. Với response cá nhân hoặc nhạy cảm, cân nhắc no-store/private và cấu hình shared cache tương ứng. Khi quyền thay đổi, xử lý invalidation ở cache, search index và các bản sao liên quan.

## 15. Kiểm thử BOPLA

Kiểm thử phải xác minh cả field được phép lẫn field bị cấm, ở cả chiều đọc và ghi. Một test chỉ kiểm tra HTTP 200 hoặc 403 ở cấp endpoint không chứng minh property authorization đúng.

### 15.1 Ma trận test đọc

| Principal | Object | Property | Kết quả mong đợi |
|---|---|---|---|
| Chủ tài khoản | Hồ sơ của mình | displayName | Được đọc |
| Chủ tài khoản | Hồ sơ của mình | internalRiskScore | Không xuất hiện |
| User A | Hồ sơ của B | email | Bị từ chối ở object authorization |
| Nhân viên hỗ trợ | Hồ sơ thuộc phạm vi hỗ trợ | email | Được đọc nếu policy cho phép |
| Nhân viên hỗ trợ | Hồ sơ bất kỳ | paymentSecret | Không xuất hiện |
| Admin tenant A | User tenant B | role | Không được truy cập chéo tenant |
| Service xác minh | Hồ sơ trong scope | email, verificationState | Chỉ field cần thiết được trả |

### 15.2 Ma trận test ghi

| Principal | Request | Kết quả mong đợi |
|---|---|---|
| Chủ tài khoản | Cập nhật displayName hợp lệ | Thành công |
| Chủ tài khoản | Thêm role=ADMIN vào payload | Bị từ chối hoặc field bị loại theo contract an toàn |
| Chủ tài khoản | Thêm tenantId/ownerId | Không thay đổi dữ liệu; ưu tiên từ chối payload |
| Chủ tài khoản | Gửi emailVerified=true | Không thể tự xác minh email |
| Nhân viên hỗ trợ | Sửa internalRiskScore | Bị từ chối |
| Admin tenant | Cấp role trong phạm vi được phép | Thành công qua command quản trị có audit |
| Bất kỳ principal nào | Thay status trực tiếp bỏ qua workflow | Bị từ chối |
| Client | JSON Patch tới /role hoặc nested ownerId | Bị từ chối |

### 15.3 Kỹ thuật kiểm thử

- Tạo payload chứa field hợp lệ và field nhạy cảm cùng lúc để kiểm tra mass assignment.
- Thử field viết hoa/thường khác nhau, alias, tên property lồng và nested collection.
- Thử null, giá trị mặc định, field vắng mặt, field trùng và unknown field.
- Thử JSON Merge Patch và JSON Patch với path encoding/escaping.
- Gọi API bằng curl/Postman thay vì chỉ dùng UI; frontend có thể đã ẩn field nhưng backend vẫn nhận.
- Kiểm tra response JSON, GraphQL, export, webhook, cache, log và event.
- Kiểm tra cả user cùng tenant, khác tenant, role khác nhau và trạng thái workflow khác nhau.
- Kiểm tra đồng thời và race condition khi quyền hoặc trạng thái object thay đổi giữa lúc kiểm tra và lúc ghi.
- Thêm regression test cho mỗi field nhạy cảm và mỗi đường truy cập mới.

Test phải xác nhận dữ liệu thực sự không thay đổi. Việc API trả 400/403 nhưng transaction đã ghi field nhạy cảm vẫn là lỗi.

## 16. Ví dụ luồng cập nhật hồ sơ an toàn

Giả sử API PATCH /users/me cho phép người dùng cập nhật displayName và phone. Các field role, tenantId, emailVerified, ownerId và internalRiskScore do hệ thống quản lý.

Luồng xử lý:

1. Xác thực access token và lấy principal từ token đã được xác minh.
2. Xác định user và tenant từ principal/session phía server; không lấy userId/tenantId từ body.
3. Parse request thành UpdateMyProfileRequest chỉ gồm displayName và phone.
4. Từ chối field không nằm trong contract, hoặc xử lý theo chính sách unknown-field được công bố.
5. Validate kiểu, độ dài, định dạng và quy tắc nghiệp vụ của từng giá trị.
6. Tải user trong tenant đúng và kiểm tra quyền cập nhật hồ sơ.
7. Gọi domain method changeDisplayName/changePhone; không bind trực tiếp entity.
8. Lưu thay đổi trong transaction và ghi audit metadata phù hợp.
9. Tạo response DTO chỉ gồm field người dùng được đọc; không serialize entity.
10. Nếu email cần thay đổi, khởi tạo quy trình xác minh riêng và chỉ cập nhật emailVerified sau khi service xác minh hoàn tất.

Request hợp lệ:

~~~http
PATCH /api/users/me
Content-Type: application/json
Authorization: Bearer <access-token>
~~~

~~~json
{
  "displayName": "Nguyen An",
  "phone": "+84 901 234 567"
}
~~~

Payload cần bị từ chối:

~~~json
{
  "displayName": "Nguyen An",
  "role": "ADMIN",
  "tenantId": "another-tenant",
  "emailVerified": true,
  "internalRiskScore": 0
}
~~~

Không chỉ dựa vào việc DTO bỏ qua field lạ. Với API nhạy cảm, từ chối unknown/protected fields giúp client phát hiện sớm contract sai và tránh tạo cảm giác rằng mọi thay đổi đã được chấp nhận. Dù chọn từ chối hay bỏ qua, server phải bảo đảm các field bị cấm không thay đổi.

## 17. Giám sát và audit property nhạy cảm

Theo dõi những hành vi có thể chỉ ra thử nghiệm BOPLA:

- Request chứa field ngoài schema hoặc field đặc quyền như role, ownerId, tenantId, balance, status.
- Tỷ lệ 400/403 tăng ở endpoint update.
- User thường xuyên yêu cầu field hiếm dùng hoặc field nội bộ trong GraphQL/field mask.
- Nhiều lần thử thay đổi property bị từ chối.
- Export có số field hoặc số bản ghi bất thường.
- Thay đổi role, owner, tenant, verification state hoặc tài sản có giá trị cao.

Audit log nên ghi principal, tenant, object ID, action, tên property, kết quả policy và correlation ID. Với field nhạy cảm, tránh ghi giá trị cũ/mới đầy đủ nếu không có yêu cầu nghiệp vụ và kiểm soát truy cập rõ. Có thể lưu fingerprint hoặc phiên bản thay đổi để điều tra.

Metric không nên dùng giá trị property hoặc user ID không giới hạn làm label. Hạn chế cardinality và tránh đưa dữ liệu cá nhân vào dashboard. Cảnh báo khi một client thử nhiều field đặc quyền hoặc một tài khoản thay đổi nhiều thuộc tính nhạy cảm trong thời gian ngắn.

## 18. Các lỗi thiết kế thường gặp

1. **Trả entity trực tiếp:** field mới trong database tự xuất hiện trong API response.
2. **Chỉ ẩn field ở frontend:** dữ liệu đã gửi tới client vẫn có thể bị đọc.
3. **Dùng một DTO cho mọi use case:** request chứa nhiều field mà từng endpoint không cần.
4. **Bind request vào entity:** tạo mass assignment và cập nhật quan hệ ngoài dự kiến.
5. **Chỉ kiểm tra role ở endpoint:** bỏ qua object, property và business state.
6. **Cho phép client sửa field hệ thống:** ownerId, tenantId, role, balance hoặc verification state.
7. **Không xử lý field lồng nhau:** nested object/collection có thể thay quyền hoặc dữ liệu nhạy cảm.
8. **Tin GraphQL selection set:** client yêu cầu field không có nghĩa là được quyền đọc.
9. **Không kiểm tra JSON Patch path:** operation hợp lệ về cú pháp vẫn có thể sửa field bị cấm.
10. **Ẩn response nhưng không kiểm soát export/event:** dữ liệu rò rỉ qua kênh phụ.
11. **Không định nghĩa semantics của null và unknown field:** tạo hành vi cập nhật khó dự đoán.
12. **Kiểm tra quyền rồi ghi không nguyên tử:** trạng thái object có thể thay đổi giữa hai bước.

## 19. Quy trình rà soát property authorization cho endpoint

Với mỗi endpoint, thực hiện:

1. Liệt kê resource và toàn bộ property trực tiếp, lồng nhau, quan hệ và field tính toán.
2. Phân loại property: công khai, cá nhân, nhạy cảm, nội bộ, bất biến, quyền điều khiển hoặc workflow.
3. Xác định principal, tenant, object, action và business context.
4. Lập ma trận property read/write cho từng use case; ghi rõ ngoại lệ và điều kiện.
5. Tạo request DTO và response DTO allowlist riêng cho operation.
6. Kiểm tra query projection, serializer, GraphQL resolver, export, event, cache và webhook.
7. Thực thi policy ở application/domain; fail closed khi không xác định được quyền.
8. Kiểm tra nested object, JSON Patch, null, unknown field và race condition.
9. Viết negative test cho từng field nhạy cảm và kiểm tra dữ liệu không bị thay đổi.
10. Thiết lập audit, metric, cảnh báo và review khi schema hoặc nghiệp vụ thay đổi.

## 20. Checklist rà soát

- [ ] Đã phân biệt quyền truy cập endpoint, object và property.
- [ ] Đã lập danh mục property nhạy cảm, nội bộ, bất biến và field điều khiển quyền.
- [ ] Response DTO chỉ chứa field mà use case được phép trả.
- [ ] Không serialize trực tiếp entity hoặc object quan hệ nội bộ.
- [ ] Request DTO dùng allowlist; field owner, tenant, role và trạng thái do server quản lý.
- [ ] Quyền đọc và quyền ghi được đánh giá riêng.
- [ ] Policy xét principal, tenant, object, property, action và business state.
- [ ] Nested object, collection, GraphQL, field mask và JSON Patch được kiểm soát.
- [ ] Semantics của missing/null/unknown field được định nghĩa rõ.
- [ ] Các thay đổi workflow đi qua command hợp lệ và domain invariant.
- [ ] Export, webhook, event, cache, log và notification không làm lộ property bị cấm.
- [ ] Có negative test cho field nhạy cảm, cross-tenant và mass assignment.
- [ ] Audit ghi nhận truy cập/thay đổi property mà không lưu bí mật không cần thiết.

Broken Object Property Level Authorization nhắc rằng quyền truy cập một đối tượng không đồng nghĩa với quyền đọc hoặc sửa mọi field bên trong nó. Thiết kế API an toàn cần kiểm soát property ở cả chiều vào và chiều ra, gắn quyết định với principal, tenant, object và trạng thái nghiệp vụ. DTO allowlist, domain method rõ nghĩa, policy có thể kiểm thử và kiểm soát nhất quán trên mọi kênh dữ liệu giúp ngăn lộ thông tin cũng như thay đổi trái phép.

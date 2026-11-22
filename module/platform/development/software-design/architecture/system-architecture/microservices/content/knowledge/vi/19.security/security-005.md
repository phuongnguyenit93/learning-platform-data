# Phân quyền tại dịch vụ sở hữu dữ liệu và hành vi

## 1. Mục tiêu

Trong kiến trúc Microservices, mỗi dịch vụ nên **chịu trách nhiệm quyết định và thực thi quyền truy cập đối với dữ liệu và hành vi nghiệp vụ mà mình sở hữu**. API Gateway, frontend hoặc dịch vụ gọi có thể chặn sớm một số yêu cầu, nhưng dịch vụ sở hữu tài nguyên vẫn phải kiểm tra quyền tại ranh giới tin cậy của chính nó.

Một câu hỏi xuyên suốt bài này: **Ai được phép thực hiện hành động nào trên đối tượng nào, trong ngữ cảnh nào, và dịch vụ nào có đủ thông tin để quyết định?**

Sau khi đọc, cần phân biệt được:

- Xác thực danh tính (authentication) và phân quyền (authorization).
- Quyền truy cập một API (endpoint-level) với quyền truy cập **một đối tượng dữ liệu cụ thể** (object-level).
- Quyền đọc dữ liệu với quyền thay đổi trạng thái, thực hiện giao dịch hoặc kích hoạt hành vi.
- Vai trò của Gateway, service sở hữu dữ liệu, tầng ứng dụng, domain và database.
- Cách áp dụng phân quyền trong chuỗi gọi giữa microservices, tác vụ nền và sự kiện bất đồng bộ.

**Lưu ý về thuật ngữ:** "Dịch vụ sở hữu dữ liệu" nghĩa là microservice có trách nhiệm nghiệp vụ và quản lý vòng đời của dữ liệu, không đồng nghĩa người dùng cuối là "chủ sở hữu" bản ghi. Cả hai khái niệm có thể tồn tại cùng lúc: Order Service sở hữu aggregate Order, còn một khách hàng có thể là người được phép xem một đơn hàng cụ thể.

## 2. Ví dụ mở đầu: hệ thống đơn hàng

Giả sử hệ thống gồm các dịch vụ:

| Dịch vụ | Dữ liệu/hành vi do dịch vụ sở hữu | Ví dụ quyết định phân quyền |
|---|---|---|
| Identity Service | Danh tính, đăng nhập, nhóm/tenant, thông tin định danh | Ai là principal, token có hiệu lực không |
| Order Service | Đơn hàng, chi tiết đơn, hủy đơn | Khách A có được xem/hủy đơn X không |
| Payment Service | Giao dịch và trạng thái thanh toán | Lệnh thu tiền/hoàn tiền có được chấp nhận không |
| Inventory Service | Tồn kho, giữ/trả hàng | Dịch vụ hay nhân viên nào được thay đổi tồn kho |
| Customer Service | Hồ sơ khách hàng | Ai được xem hoặc sửa dữ liệu cá nhân |

Khách A đăng nhập, nhận access token hợp lệ và gọi GET /orders/123. Nếu đơn 123 thuộc khách B thì **token hợp lệ vẫn không đủ quyền**. Order Service phải từ chối sau khi kiểm tra quan hệ giữa người gọi và chính đơn 123.

Tương tự, nhân viên hỗ trợ có thể xem một đơn trong phạm vi được phân công nhưng chưa chắc được hoàn tiền. Ngay cả khi nút "Hoàn tiền" đã được ẩn trong giao diện, một request trực tiếp tới endpoint hoàn tiền vẫn phải chịu kiểm tra tại Payment Service.

Hai lỗi bảo mật phổ biến cần tránh:

1. **BOLA/IDOR** (Broken Object Level Authorization / Insecure Direct Object Reference): dùng ID của người khác để truy cập một đối tượng mà không kiểm tra quyền với đối tượng đó.
2. **BFLA** (Broken Function Level Authorization): người gọi được truy cập một chức năng hoặc thao tác mà vai trò, quan hệ hoặc điều kiện nghiệp vụ không cho phép.

## 3. Vì sao phải kiểm tra tại dịch vụ sở hữu?

### 3.1. Dịch vụ sở hữu hiểu đối tượng và quy tắc nghiệp vụ

Gateway có thể biết request có token, token có scope orders.read và URL bắt đầu bằng /orders. Nhưng Gateway thường không biết:

- Order 123 thuộc tenant nào, khách nào hoặc nhóm nào.
- Đơn đang ở trạng thái DRAFT, PAID hay SHIPPED.
- Nhân viên được phân công xử lý đơn hay chỉ có quyền đọc tổng hợp.
- Việc hủy/hoàn tiền có đòi hỏi phê duyệt hai bước.
- Một bản ghi được ẩn do quy định bảo mật hoặc đang bị khóa xử lý.

Chỉ service sở hữu aggregate và các policy liên quan mới có đủ ngữ cảnh để đưa ra quyết định chính xác, hoặc để gọi một dịch vụ policy có nguồn dữ liệu phù hợp.

### 3.2. Không giả định "nội bộ là đáng tin"

Một request có thể đi theo nhiều đường:

~~~text
Ứng dụng web  ---> API Gateway ---> Order Service
Ứng dụng mobile ------------------> Order Service (qua ingress khác)
Service A ----mTLS/service token--> Order Service
Job định kỳ ---------------------> Order Service
Consumer sự kiện ---------------> Order Service
~~~

Nếu quyền chỉ được kiểm tra ở một Gateway cụ thể, các đường khác có thể bỏ qua chính sách. Quy tắc cần được áp dụng ở điểm vào đáng tin cậy của Order Service hoặc trong các service method có thể được gọi qua nhiều đường.

**Mọi entry point có thể kích hoạt cùng hành vi phải đi qua cùng policy.** Điều này không có nghĩa lặp code kiểm tra ở mọi controller; nên gom logic phân quyền vào lớp/policy dùng chung, rồi bảo đảm không có đường đi nào bỏ qua nó.

### 3.3. Trách nhiệm phân lớp

| Vị trí | Kiểm tra phù hợp | Không nên giả định |
|---|---|---|
| Client/UI | Ẩn chức năng, thông báo sớm | UI là ranh giới bảo mật |
| API Gateway | TLS, token thô, rate limit, routing, scope tổng quát | Gateway biết quyền trên từng record |
| Service sở hữu | Danh tính được xác minh, tenant, actor, resource, action, context, trạng thái nghiệp vụ | Request nội bộ mặc nhiên được phép |
| Domain/application layer | Invariant, quyền thực hiện command, chuyển trạng thái hợp lệ | Chỉ cần kiểm tra ở HTTP controller |
| Data access/DB | Truy vấn có phạm vi tenant/owner, RLS khi phù hợp | Lọc dữ liệu sau khi đã trả về là đủ |

Nguyên tắc tổ chức: **Kiểm tra ở ranh giới; áp chính sách ở nơi có ngữ cảnh; giới hạn truy vấn ở tầng dữ liệu.**

## 4. Authentication, authorization và các yếu tố quyết định

**Authentication** trả lời "Người hoặc workload này là ai?". Ví dụ: access token đã được kiểm tra chữ ký, issuer, audience, hạn sử dụng; hoặc workload đã được xác thực bằng mTLS.

**Authorization** trả lời "Principal này có được thực hiện action này trên resource này vào thời điểm này không?". Một policy thường có đầu vào:

~~~text
Decision = authorize(
    principal,        // user/service identity
    action,           // order.read, order.cancel, refund.approve
    resource,         // Order #123, Payment #456
    context           // tenant, organization, assignment, thời gian, trạng thái
)
~~~

Ví dụ chính sách đọc một đơn:

~~~text
ALLOW order.read nếu:
  actor đang thuộc tenant của đơn
  VÀ actor có quyền orders.read
  VÀ (
      actor là khách tạo đơn
      HOẶC actor là nhân viên hỗ trợ được phân công
      HOẶC actor có quyền kiểm toán với phạm vi phù hợp
  )
Ngược lại DENY.
~~~

Ví dụ chính sách hủy đơn:

~~~text
ALLOW order.cancel nếu:
  actor thuộc đúng tenant
  VÀ có quyền orders.cancel
  VÀ (là người đặt đơn hoặc nhân viên được ủy quyền)
  VÀ đơn ở trạng thái cho phép hủy
  VÀ đơn chưa bước vào quá trình giao hàng không thể đảo ngược.
~~~

Ở đây điều kiện "được phép hủy theo quyền" và "được phép hủy theo trạng thái" nên được mô hình rõ ràng, dù ứng dụng có thể trả lỗi khác nhau cho trường hợp không có quyền và trường hợp trạng thái không hợp lệ. Không tiết lộ trạng thái của đơn mà người gọi không được biết.

## 5. Mô hình chính sách phân quyền

### 5.1. RBAC — Role-Based Access Control

Quyền được gán qua vai trò. Ví dụ: CUSTOMER có orders.read_own; SUPPORT có orders.read_assigned; FINANCE_APPROVER có refunds.approve.

Ưu điểm: đơn giản, dễ quản lý các nhóm chức năng. Hạn chế: vai trò "SUPPORT" đơn thuần chưa đủ để quyết định **được xem đơn nào**. Nếu tạo vai trò cho mọi quan hệ riêng lẻ sẽ dẫn đến phình to vai trò.

### 5.2. ABAC — Attribute-Based Access Control

Quyết định dựa trên thuộc tính của actor, resource và context:

- actor.tenantId == order.tenantId;
- order.region nằm trong danh sách vùng quản lý của actor;
- order.total <= actor.approvalLimit;
- order.status == PENDING;
- actor đang có phiên xác thực phù hợp với thao tác nhạy cảm.

Ưu điểm: diễn đạt chính sách tinh. Hạn chế: phải xác định nguồn thuộc tính đáng tin, thời điểm cập nhật và khả năng giải thích quyết định.

### 5.3. ReBAC — Relationship-Based Access Control

Quyền được suy ra từ quan hệ, ví dụ "user là owner của order", "user là thành viên của team phụ trách case", "manager quản lý nhóm được phân công".

Phù hợp khi quan hệ và chia sẻ thay đổi thường xuyên. Với đồ thị quan hệ phức tạp, có thể dùng một hệ thống policy/relationship chuyên dụng, nhưng service sở hữu vẫn phải gọi/kiểm tra kết quả và áp các ràng buộc nghiệp vụ còn lại.

### 5.4. Kết hợp thực tế

Nhiều dịch vụ cần **RBAC + ABAC/ReBAC**:

~~~text
CanReadOrder =
    hasPermission(actor, "orders.read")
    AND sameTenant(actor, order)
    AND (
        isOrderCustomer(actor, order)
        OR isAssignedSupport(actor, order)
        OR hasScopedAuditAccess(actor, order)
    )
~~~

Không dùng một cờ isAdmin chung cho mọi tài nguyên trừ khi được định nghĩa rõ, có phạm vi, kiểm toán và phê duyệt. Quyền đặc biệt cũng cần giới hạn theo tenant, nghiệp vụ, loại dữ liệu và thời gian.

**Mặc định deny (deny by default), cấp quyền tối thiểu (least privilege)**. Thiếu thông tin để đánh giá chính sách thì từ chối an toàn, không suy đoán cho phép.

## 6. Phân quyền truy cập dữ liệu ở cấp đối tượng

### 6.1. Không tin ID trong URL

Đoạn xử lý nguy hiểm:

~~~java
@GetMapping("/orders/{id}")
public OrderDto getOrder(@PathVariable UUID id) {
    return OrderDto.from(orderRepository.findById(id).orElseThrow());
}
~~~

Đoạn trên có thể trả đơn của bất kỳ ai nếu người gọi đoán hoặc biết UUID. UUID khó đoán **không phải cơ chế phân quyền**. Tương tự, đổi ID từ 1001 sang 1002 là một bài thử BOLA phổ biến với khóa số tăng dần.

Cần lấy principal/tenant từ một **ngữ cảnh danh tính đã xác thực**, truy vấn dữ liệu trong phạm vi phù hợp, rồi áp policy cụ thể:

~~~text
validatedIdentity = authenticationContext.requirePrincipal()
order = orderRepository.findByIdAndTenantId(
    orderId,
    validatedIdentity.tenantId
)
if order does not exist:
    return not-found (theo chính sách không lộ tồn tại)
authorization.requireCanRead(validatedIdentity, order)
return dataProjectionAllowedFor(validatedIdentity, order)
~~~

**Tenant ID trong header, query string hoặc request body do client tự gửi không được mặc nhiên tin.** Nếu API cho phép chọn tenant đang hoạt động, phải xác nhận actor thực sự là thành viên hoặc có delegation hợp lệ với tenant đó trước khi truy vấn.

### 6.2. Phải phân quyền cho danh sách, tìm kiếm và tổng hợp

Lỗi không chỉ xảy ra với GET /orders/{id}. Cũng phải giới hạn:

- GET /orders: danh sách trả về chỉ những đơn nằm trong phạm vi actor.
- GET /orders/search: điều kiện lọc luôn bao gồm tenant và phạm vi quyền.
- GET /orders/count: tổng số không tiết lộ dữ liệu ngoài quyền.
- Export CSV/Excel/PDF: lặp lại cùng bộ lọc, không bỏ policy vì chạy nền.
- Dashboard, báo cáo thống kê, autocomplete, notification preview: tránh rò rỉ qua dữ liệu gián tiếp.
- GraphQL resolver/gRPC method: vẫn phải kiểm tra trên resource thực tế.

Một cách làm sai là lấy tất cả order rồi lọc ở ứng dụng sau khi phân trang:

~~~text
SELECT * FROM orders ORDER BY created_at DESC LIMIT 20 OFFSET 40;
filter(result, actorAllowed);
~~~

Cách này có thể gây thiếu dòng, lộ count và tốn tài nguyên. Hãy đưa điều kiện tenant/quyền có thể biểu diễn thành SQL vào **truy vấn trước khi LIMIT/OFFSET**, sau đó áp các policy nghiệp vụ còn lại cho từng record khi cần. Nếu policy quan hệ phức tạp và không thể đẩy hoàn toàn xuống SQL, thiết kế chiến lược truy vấn/pagination rõ ràng; đừng âm thầm trả kết quả không chính xác.

### 6.3. Phân quyền ở cấp trường

Được đọc một Order không đồng nghĩa được đọc mọi trường của nó. Ví dụ:

| Principal | Trường có thể nhận | Trường hạn chế |
|---|---|---|
| Khách đặt đơn | Sản phẩm, tổng tiền, trạng thái, địa chỉ giao của chính họ | Ghi chú kiểm soát gian lận nội bộ |
| Nhân viên giao hàng | Thông tin cần cho giao nhận | Dữ liệu thanh toán nhạy cảm |
| Nhân viên hỗ trợ | Trường cần thiết cho case được phân công | Thông tin thẻ, bí mật kỹ thuật |
| Người làm báo cáo | Dữ liệu tổng hợp hoặc đã ẩn danh phù hợp | Dữ liệu cá nhân không cần thiết |

Projection/DTO là công cụ hữu ích: chỉ tạo response bằng trường đã được phép. Không trả toàn bộ entity rồi hy vọng frontend giấu trường nhạy cảm.

### 6.4. Tách biệt tenant

Trong SaaS đa khách hàng (multi-tenant), điều kiện tenant nên có mặt từ truy vấn cơ sở đến việc ghi dữ liệu:

~~~sql
SELECT id, status, amount
FROM orders
WHERE id = :order_id
  AND tenant_id = :trusted_tenant_id;
~~~

Dấu :trusted_tenant_id đại diện giá trị đã được xác minh, không lấy trực tiếp từ input không đáng tin. Có thể bổ sung row-level security (RLS), schema/database theo tenant hoặc các hạn chế truy cập ở DB như lớp phòng vệ bổ sung. RLS không thay thế việc kiểm tra quyền thao tác, quan hệ người dùng và trạng thái nghiệp vụ trong service.

## 7. Phân quyền hành vi: command và chuyển trạng thái

Quyền đọc thường khác quyền làm thay đổi trạng thái. Một user có thể xem đơn nhưng không thể hủy; nhân viên có thể đề xuất hoàn tiền nhưng không được tự duyệt.

Ví dụ các hành vi của Order Service:

| Action | Điều kiện phân quyền điển hình | Invariant nghiệp vụ |
|---|---|---|
| order.read | Cùng tenant, là khách/nhân viên được giao | Tài nguyên tồn tại |
| order.cancel | Khách hoặc nhân viên có quyền hủy | Trạng thái chưa giao và còn có thể hủy |
| order.changeAddress | Khách hoặc support được ủy quyền | Chưa chốt vận đơn |
| order.approveDiscount | Người có giới hạn duyệt phù hợp | Mức chiết khấu và workflow hợp lệ |
| order.export | Có quyền xuất và phạm vi bản ghi | Lọc trường nhạy cảm, giới hạn khối lượng |

Kiểm tra ở service method của **command thực sự**, không chỉ tại UI hay controller:

~~~text
request -> authenticate actor
        -> locate aggregate in tenant scope
        -> authorize action for actor + aggregate
        -> validate domain state/invariants
        -> execute transition in transaction
        -> emit event / audit
~~~

Đừng đồng nhất "actor có role SUPPORT" với "actor được thực hiện mọi hành vi của Order Service". Các action nên có mã quyền riêng và policy riêng; ví dụ orders.read, orders.cancel, orders.address.update.

### 7.1. Khi nào kiểm tra quyền và trạng thái?

Phân quyền dựa trên trạng thái resource có thể đổi giữa lúc đọc và lúc ghi. Với command nhạy cảm, nên thực hiện kiểm tra đối tượng, authorization và cập nhật trong một transaction phù hợp; dùng optimistic locking (version) hoặc row lock nếu cần để tránh race condition.

Ví dụ: hai actor đồng thời muốn duyệt và hủy cùng một đơn. Nếu cả hai đọc trạng thái PENDING rồi cập nhật mà không kiểm soát cạnh tranh, điều kiện nghiệp vụ có thể bị vượt qua. Authorization không thay thế quy tắc nhất quán giao dịch.

### 7.2. Quyền đặc biệt và phê duyệt hai bước

Đối với hoàn tiền lớn, thay đổi quyền quản trị hoặc xuất dữ liệu hàng loạt, có thể cần:

- Quyền thực thi và quyền phê duyệt khác nhau.
- Người tạo không được tự duyệt (separation of duties).
- Giới hạn giá trị, khu vực, tenant hoặc thời gian.
- Xác thực tăng cường hoặc phê duyệt lại cho thao tác nhạy cảm.
- Audit có thể truy vết ai yêu cầu, ai duyệt, quyết định nào được áp dụng.

Các yêu cầu này thuộc policy của dịch vụ sở hữu hành vi, ngay cả khi màn hình phê duyệt nằm trong ứng dụng quản trị dùng chung.

## 8. Kiến trúc thực thi: PEP, PDP và nguồn thuộc tính

Có thể mô tả một lần kiểm tra bằng ba thành phần:

- **PEP (Policy Enforcement Point):** nơi chặn request/command nếu không được phép, thường tại ứng dụng của service sở hữu.
- **PDP (Policy Decision Point):** hàm hoặc dịch vụ ra quyết định allow/deny dựa trên policy.
- **PIP (Policy Information Point):** nơi lấy dữ liệu cần thiết như vai trò, quan hệ, tenant, thuộc tính resource và phiên bản policy.

Luồng tham khảo:

~~~text
                        +---------------------+
Client -> Gateway ----> | Order Service       |
  token kiểm tra sơ bộ  |   PEP               |
                        |   |                 |
                        |   v                 |
                        |   PDP / Policy      |
                        |    ^       ^        |
                        |    |       |        |
                        | resource  actor     |
                        |    |       |        |
                        | Repository / PIP    |
                        |   |                 |
                        |   v                 |
                        |  Domain command     |
                        +---|-----------------+
                            v
                          Database
~~~

PDP có thể là code thuần trong service, policy engine nhúng hoặc dịch vụ phân quyền tập trung. Quyết định triển khai phụ thuộc độ phức tạp, latency, mức nhất quán và việc chia sẻ chính sách giữa nhiều service.

**Tập trung khai báo policy không có nghĩa tập trung bỏ qua enforcement.** Dịch vụ sở hữu vẫn cần PEP chặn ở mọi entry point, bảo đảm không có đường vào nào thực thi command trước khi quyết định được áp dụng.

Nếu PDP không phản hồi, hãy thiết kế hành vi fail closed phù hợp với rủi ro, thay vì ngầm cho phép. Các hoạt động công khai/an toàn đã được định nghĩa riêng có thể có policy đặc thù, nhưng không biến sự cố PDP thành quyền truy cập mặc định.

## 9. Danh tính và ngữ cảnh được tin cậy

### 9.1. Kiểm tra access token đúng đối tượng nhận

Một service nhận JWT không nên chỉ giải mã payload rồi tin vào các claim. Cần xác minh chữ ký, thuật toán được cho phép, issuer, thời hạn, audience dự kiến và các điều kiện triển khai liên quan. Các quyền/scope trong token phải được hiểu theo hợp đồng giữa bên cấp và bên nhận.

Ví dụ payload mang tính minh họa:

~~~json
{
  "iss": "https://identity.example.internal/",
  "sub": "user-42",
  "aud": "orders-api",
  "exp": 1890000000,
  "tenant_id": "tenant-blue",
  "scope": "orders.read orders.cancel"
}
~~~

Chỉ đọc tenant_id hoặc scope sau khi token được xác minh và service chấp nhận nguồn của các claim đó. **Một scope như orders.read chưa nói user-42 có quyền trên order-123**: phải kết hợp quyền trên đối tượng.

### 9.2. Đừng tin trường danh tính tự khai báo

Các header như X-User-Id, X-Tenant-Id, X-Role hoặc trường userId trong JSON không tự chứng minh danh tính. Nếu dùng mô hình trusted gateway, phải bảo đảm backend không thể được truy cập qua đường bỏ qua gateway, header do client gửi đã bị loại bỏ/ghi đè và kênh giao tiếp được xác thực. Cách phổ biến hơn là service tự xác minh access token thích hợp, hoặc sử dụng token nội bộ được phát hành theo cơ chế tin cậy rõ ràng.

### 9.3. Membership và quyền có thể thay đổi

JWT có thời hạn không cho biết trạng thái quyền mới nhất trong database. Nếu user vừa bị loại khỏi một tenant hoặc nhân viên vừa mất quyền duyệt giao dịch, token cũ có thể vẫn chứa claim trước đó. Các cách xử lý tùy độ nhạy:

- Access token ngắn hạn, phiên đăng nhập có cơ chế thu hồi phù hợp.
- Tái kiểm tra membership hoặc trạng thái ủy quyền tại nguồn sự thật với thao tác nhạy cảm.
- Dùng phiên bản policy/membership để nhận diện cache cũ.
- Token introspection hoặc danh sách thu hồi nếu kiến trúc và yêu cầu cho phép.
- Đặt TTL và chiến lược invalidation rõ ràng cho cache quyết định quyền.

Không giả định toàn bộ dữ liệu quyền luôn đồng bộ tức thời giữa các hệ thống; cần tài liệu hóa độ trễ chấp nhận được và cách phản ứng khi thu hồi quyền khẩn cấp.

## 10. Ví dụ Java/Spring Boot: kiểm tra tại service sở hữu

Ví dụ dưới đây minh họa kiến trúc của Order Service. Một số class và method domain/repository được rút gọn để tập trung vào luồng phân quyền.

### 10.1. Nhận dạng actor từ ngữ cảnh đã xác thực

~~~java
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

public record Actor(
        String subjectId,
        String tenantId,
        Set<String> authorities
) {
    public boolean hasScope(String scope) {
        return authorities.contains("SCOPE_" + scope);
    }
}

@Component
class ActorFactory {
    public Actor from(Authentication authentication) {
        if (!(authentication instanceof JwtAuthenticationToken token)
                || !authentication.isAuthenticated()) {
            throw new org.springframework.security.access.AccessDeniedException(
                    "Authenticated JWT required");
        }

        String subject = token.getToken().getSubject();
        String tenant = token.getToken().getClaimAsString("tenant_id");
        if (subject == null || tenant == null || tenant.isBlank()) {
            throw new org.springframework.security.access.AccessDeniedException(
                    "Missing trusted identity context");
        }

        Set<String> authorities = authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toUnmodifiableSet());

        return new Actor(subject, tenant, authorities);
    }
}
~~~

Giả định: bộ bảo mật đã xác thực token, xác minh audience cho orders-api, và chuyển scope thành authority theo quy ước SCOPE_. Nếu hệ thống cho phép một user ở nhiều tenant, phải giải quyết tenant hoạt động từ danh sách tenant **được phép** thay vì tin lựa chọn tùy ý của client.

### 10.2. Cấu hình bảo vệ đường vào

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ApiSecurity {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated());

        http.oauth2ResourceServer(oauth -> oauth.jwt(withDefaults()));
        return http.build();
    }
}
~~~

Cấu hình JWT decoder/issuer và **audience validation** tương ứng môi trường phải được bổ sung cho ứng dụng thật; ví dụ không tự thiết lập đầy đủ các thuộc tính đó. Ở đây Gateway/service filter bảo đảm request có danh tính hợp lệ. Quyền đối tượng và command vẫn thuộc Order Application Service.

### 10.3. Repository luôn giới hạn phạm vi tenant

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<Order, UUID> {
    Optional<Order> findByIdAndTenantId(UUID id, String tenantId);
}
~~~

Các truy vấn danh sách, cập nhật theo ID, xóa, export hoặc bulk action cũng cần giới hạn tương tự. Với cập nhật trực tiếp bằng JPQL/SQL không load entity, phải có điều kiện tenant, policy cần thiết và kiểm tra số row bị tác động.

### 10.4. Policy quyết định quyền cụ thể

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;

@Component
class OrderPolicy {
    void requireRead(Actor actor, Order order) {
        boolean sameTenant = actor.tenantId()
                .equals(order.getTenantId());
        boolean related = actor.subjectId()
                .equals(order.getCustomerId())
                || order.getAssignedSupportIds()
                        .contains(actor.subjectId());

        if (!sameTenant || !actor.hasScope("orders.read") || !related) {
            throw new AccessDeniedException("Order read denied");
        }
    }

    void requireCancel(Actor actor, Order order) {
        boolean sameTenant = actor.tenantId()
                .equals(order.getTenantId());
        boolean customer = actor.subjectId()
                .equals(order.getCustomerId());

        if (!sameTenant || !customer
                || !actor.hasScope("orders.cancel")) {
            throw new AccessDeniedException("Order cancel denied");
        }
    }
}
~~~

Policy này minh họa một quy tắc đơn giản: người mua có thể hủy, người hỗ trợ được phân công chỉ được đọc. Trong hệ thống thật, có thể bổ sung role đặc quyền có phạm vi, delegation và giới hạn nghiệp vụ. Không để chuỗi "SUPPORT" đơn thuần mở quyền trên mọi đơn.

### 10.5. Kiểm tra quyền khi thực hiện nghiệp vụ

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.security.access.AccessDeniedException;

@Service
public class OrderApplicationService {
    private final OrderRepository repository;
    private final OrderPolicy policy;

    public OrderApplicationService(
            OrderRepository repository,
            OrderPolicy policy
    ) {
        this.repository = repository;
        this.policy = policy;
    }

    @Transactional(readOnly = true)
    public OrderView getOrder(UUID orderId, Actor actor) {
        if (!actor.hasScope("orders.read")) {
            throw new AccessDeniedException("Missing read permission");
        }

        Order order = repository.findByIdAndTenantId(
                orderId, actor.tenantId()
        ).orElseThrow(OrderNotFoundException::new);

        policy.requireRead(actor, order);
        return OrderView.from(order);
    }

    @Transactional
    public void cancelOrder(UUID orderId, Actor actor) {
        if (!actor.hasScope("orders.cancel")) {
            throw new AccessDeniedException("Missing cancel permission");
        }

        Order order = repository.findByIdAndTenantId(
                orderId, actor.tenantId()
        ).orElseThrow(OrderNotFoundException::new);

        policy.requireCancel(actor, order);
        order.cancelBy(actor.subjectId());
        // Domain bảo đảm trạng thái cho phép hủy;
        // dùng optimistic locking/locking khi cần.
    }
}
~~~

Order, OrderView, OrderNotFoundException và cancelBy là các type/method miền nghiệp vụ cần định nghĩa. Dịch vụ cần map lỗi theo API contract và thiết lập transaction/locking phù hợp. Điều cốt lõi là **quyết định quyền diễn ra trong application service gần aggregate được sở hữu**, nên các caller hợp lệ khác cũng phải đi qua cùng logic.

Controller chỉ đóng vai trò adapter:

~~~java
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderApplicationService orders;
    private final ActorFactory actors;

    OrderController(OrderApplicationService orders, ActorFactory actors) {
        this.orders = orders;
        this.actors = actors;
    }

    @GetMapping("/{id}")
    OrderView get(@PathVariable UUID id, Authentication authentication) {
        return orders.getOrder(id, actors.from(authentication));
    }

    @PostMapping("/{id}/cancel")
    ResponseEntity<Void> cancel(
            @PathVariable UUID id,
            Authentication authentication
    ) {
        orders.cancelOrder(id, actors.from(authentication));
        return ResponseEntity.noContent().build();
    }
}
~~~

Dùng @PreAuthorize hoặc filter cho các quyền tổng quát là phù hợp nhưng **không thay thế** kiểm tra quan hệ và trạng thái của chính resource. Nếu một annotation policy đã kiểm tra record bằng truy vấn riêng, phải cân nhắc chi phí truy vấn kép và chênh lệch trạng thái trước khi write; có thể gộp policy vào luồng application service để lấy dữ liệu và kiểm tra cùng transaction.

## 11. Gọi dịch vụ sang dịch vụ: không trao quyền bằng sự tin tưởng mơ hồ

### 11.1. Danh tính workload khác danh tính người dùng

Ví dụ Order Service gọi Payment Service để yêu cầu hoàn tiền. Có ít nhất hai chủ thể cần quan tâm:

- **Workload gọi:** Order Service, được xác thực bằng service credential, mTLS hoặc token có audience cho Payment Service.
- **Người khởi xướng:** user-42 hoặc một quy trình tự động; ngữ cảnh này cần được xác minh/delegate nếu policy hoàn tiền phụ thuộc người dùng.

Payment Service không nên hiểu "request đến từ Order Service" là toàn quyền hoàn tiền. Nó cần xác minh service caller được phép gọi action tương ứng, nội dung yêu cầu có tham chiếu order/payment hợp lệ, số tiền phù hợp, trạng thái transaction và các chính sách phê duyệt.

### 11.2. Tránh confused deputy

**Confused deputy** xảy ra khi một service có đặc quyền cao thực hiện hành động thay cho một caller có đặc quyền thấp mà không kiểm tra phạm vi được ủy quyền.

Ví dụ sai:

~~~text
User X không có quyền refund
  -> gọi Order Service /orders/123/refund
  -> Order Service dùng service token đặc quyền cao
  -> Payment Service hoàn tiền vì chỉ tin service token
~~~

Luồng an toàn hơn:

~~~text
User X -> Order Service
  1. Xác thực user
  2. Kiểm tra quyền yêu cầu refund trên order 123
  3. Tạo lệnh nghiệp vụ đã ràng buộc order, payment, amount
  4. Gửi tới Payment Service bằng credential/delegation phù hợp
Payment Service:
  5. Xác thực workload và scope/audience
  6. Kiểm tra lệnh có thẩm quyền, tham chiếu, giới hạn và trạng thái payment
  7. Thực hiện idempotent transaction, audit kết quả
~~~

Có thể dùng token exchange/delegated token mang scope hẹp, audience cụ thể và thời hạn ngắn, hoặc một lệnh nội bộ có integrity và policy xác thực. Không tự tạo header X-Acting-As rồi tin rằng nó chứng minh sự ủy quyền.

### 11.3. Ai quyết định khi quyền nằm ở hai domain?

Ví dụ hủy đơn đồng thời ảnh hưởng thanh toán và vận chuyển. Order Service quyết định actor có được **yêu cầu hủy Order** không. Payment Service quyết định thao tác **hoàn tiền** có được thực hiện trên Payment tương ứng không. Shipping Service kiểm tra có thể **hủy vận đơn** ở trạng thái hiện tại không.

Mỗi dịch vụ bảo vệ **tài nguyên và hành vi của chính mình**. Một orchestration/saga có thể điều phối, nhưng không được thay thế policy và invariant của các dịch vụ tham gia.

## 12. Tác vụ nền, message và event-driven authorization

Một HTTP request có thể trở thành job hoặc event được xử lý vài phút sau. Quyền của người khởi xướng có thể đã đổi trong lúc chờ.

Cần phân biệt hai loại công việc:

1. **System-initiated:** lịch tự động đóng đơn hết hạn, đối soát hoặc tính phí định kỳ; chạy dưới workload identity và quyền dành riêng cho công việc hệ thống.
2. **User-initiated:** xuất dữ liệu, hoàn tiền hoặc xử lý hàng loạt do user yêu cầu; cần lưu danh tính người yêu cầu, tenant, phạm vi đã phê duyệt và tùy yêu cầu phải tái kiểm tra quyền khi thực thi.

Không tùy tiện nhúng access token của user vào message rồi dùng nhiều giờ sau. Token có thể hết hạn, mang audience sai và rò rỉ qua broker/log. Thay vào đó, thiết kế **ủy quyền có phạm vi hoặc job credential** cùng policy revalidation phù hợp.

Một event như OrderCreated là bằng chứng về sự kiện đã xảy ra theo hợp đồng giữa các dịch vụ, nhưng **không phải giấy phép chung** cho consumer truy cập toàn bộ hồ sơ khách hoặc thực hiện mọi command. Consumer vẫn chỉ được phép đọc/ghi tài nguyên theo vai trò và hợp đồng của chính nó.

Nếu một job được chấp thuận lúc tạo nhưng thực hiện sau khi user mất quyền, doanh nghiệp phải quy định rõ: giữ hiệu lực phê duyệt đã phát hành, hay tái kiểm tra rồi hủy job. Quyết định này phụ thuộc tính chất hành vi; cần tránh giả định chung cho cả báo cáo, thanh toán và tác vụ an ninh.

## 13. Policy ở đâu và làm sao giữ nhất quán?

### 13.1. Nguồn sự thật cho từng loại dữ liệu

| Thuộc tính/quyết định | Nguồn đáng tin thường gặp |
|---|---|
| Danh tính và token | Identity provider/authorization server |
| Membership của tenant | Hệ thống danh tính/tổ chức quản lý membership |
| Owner, assignee, trạng thái Order | Order Service |
| Trạng thái refund/payment | Payment Service |
| Quan hệ nhóm/phân công chung | Dịch vụ tổ chức/quan hệ hoặc policy store |
| Quy tắc giới hạn phê duyệt | Domain service hoặc policy engine được quản trị |
| Kết quả allow/deny | PDP theo policy, PEP tại service thực thi |

Không sao chép tùy tiện mọi thuộc tính sang Gateway rồi dùng bản copy lâu ngày để quyết định việc ghi dữ liệu nhạy cảm. Nếu cần cache để giảm latency, phải công bố độ cũ tối đa và quy tắc invalidation.

### 13.2. Local policy hay central policy engine?

**Local policy:** dễ dùng dữ liệu domain trong cùng transaction, latency thấp và không phụ thuộc mạng khi quyết định. Đổi lại, cần quản lý trùng lặp quy tắc xuyên service.

**Central policy engine:** dễ quản trị quy tắc dùng chung và truy vết policy version, thích hợp cho permission graph phức tạp. Đổi lại, service phải cấp đủ context, xử lý timeout/consistency, và vẫn kiểm tra invariant/transaction của domain.

Có thể kết hợp: quy tắc tổ chức chung ở PDP tập trung; quan hệ cụ thể và trạng thái business ở service sở hữu. Bất kể quyết định tập trung hay cục bộ, nơi ghi dữ liệu phải thực thi kết quả.

### 13.3. Time-of-check / time-of-use (TOCTOU)

Trường hợp nguy hiểm: check quyền trên Order khi trạng thái PENDING, chờ vài giây, rồi ghi khi Order đã SHIPPED. Cách ứng phó là transaction phù hợp, version check, điều kiện cập nhật hoặc khóa; với các hệ thống phân tán không có transaction chung, dùng command có precondition và xử lý xung đột một cách rõ ràng.

Phân quyền là **quyết định tại thời điểm sử dụng**; quyền cũ ở cache hay check thành công trước đó không tự đảm bảo thao tác hiện tại còn hợp lệ.

## 14. Trả lỗi mà không rò rỉ dữ liệu

Có thể chọn hành vi HTTP dựa trên hợp đồng API:

| Tình huống | Phản hồi phổ biến | Lưu ý |
|---|---|---|
| Không có/không hợp lệ thông tin xác thực | 401 | Không tiết lộ chi tiết kiểm tra token |
| Có danh tính nhưng không có quyền action | 403 | Không trả field nhạy cảm từ resource |
| Resource không tồn tại hoặc phải che sự tồn tại | 404 | Có thể dùng 404 nhất quán để hạn chế enumeration |
| Có quyền nhưng trạng thái xung đột | 409 | Chỉ trả thông tin trạng thái khi actor có quyền biết |
| Policy engine/nguồn thuộc tính lỗi | 503/5xx hoặc lỗi domain đã định nghĩa | Không biến lỗi thành allow |
| Rate limit | 429 | Chính sách rate limit độc lập với authorization |

Ví dụ nếu user A đoán order ID của B, một thiết kế có thể trả 404 cho cả "không tồn tại" và "tồn tại nhưng ngoài tenant". Tuy nhiên không chỉ sửa mã status: nội dung, thời gian phản hồi, count và các endpoint phụ cũng cần tránh vô tình xác nhận sự tồn tại của dữ liệu.

Thông báo lỗi dành cho user nên ngắn gọn; log phía server có thể chứa mã quyết định nội bộ để điều tra, không chứa token hoặc payload nhạy cảm.

## 15. Audit, đo lường và vận hành

Với hành vi có tác động cao, cần audit theo một cấu trúc có thể truy vết:

~~~json
{
  "time": "2026-11-12T02:00:00Z",
  "actorType": "USER",
  "actorId": "user-42",
  "callingService": "order-api",
  "tenantId": "tenant-blue",
  "resourceType": "ORDER",
  "resourceId": "order-123",
  "action": "order.cancel",
  "decision": "DENY",
  "reasonCode": "NOT_RESOURCE_OWNER",
  "policyVersion": "orders-policy-v7",
  "traceId": "trace-example"
}
~~~

Đây là ví dụ cấu trúc, không phải dữ liệu thật. Với dữ liệu cá nhân hoặc thao tác tài chính, áp dụng mức lưu trữ, bảo vệ và thời hạn giữ log phù hợp; tuyệt đối tránh ghi access token, secret, PAN/thông tin thẻ hoặc toàn bộ request body.

Theo dõi các chỉ số như số lần deny theo action/tenant, lỗi PDP, độ trễ authorize, tỷ lệ cache hit/stale, số lần từ chối cross-tenant và các hành vi truy cập bất thường. Cảnh báo cần phân biệt cấu hình lỗi khiến người dùng hợp lệ bị chặn hàng loạt với hành vi dò tìm ID.

Khi thay đổi policy, nên có version, người duyệt, nhật ký thay đổi, khả năng kiểm tra ảnh hưởng và cơ chế rollback. Một bug policy tập trung có thể tác động nhiều dịch vụ, nên cần triển khai theo từng giai đoạn khi rủi ro cao.

## 16. Các kịch bản kiểm thử bắt buộc về chức năng và bảo mật

| Kịch bản | Kết quả mong đợi |
|---|---|
| Không có token | Không truy cập được endpoint được bảo vệ |
| Token sai issuer/audience hoặc hết hạn | Bị từ chối trước khi vào nghiệp vụ |
| User đúng tenant, đúng owner, đúng quyền | Được đọc/truy cập action hợp lệ |
| User đúng tenant nhưng là người khác | Bị từ chối nếu không có quan hệ/ủy quyền |
| User tenant A dùng ID tài nguyên tenant B | Không trả dữ liệu, không xác nhận không cần thiết về tồn tại |
| User có orders.read nhưng thiếu orders.cancel | Được đọc nhưng không hủy được |
| User có orders.cancel nhưng Order đã SHIPPED | Không hủy, không phá invariant |
| Support chưa được phân công case | Không xem/đổi dữ liệu ngoài phạm vi |
| Support được phân công chỉ có quyền đọc | Không hoàn tiền/hủy nếu policy không cấp |
| List/search/export | Chỉ trả bản ghi và trường thuộc phạm vi quyền |
| Bulk update chứa ID từ nhiều tenant | Mọi ID được kiểm tra, không bỏ qua phần tử ngoài quyền |
| Gọi trực tiếp service, bỏ qua frontend/Gateway | Vẫn phải xác thực và phân quyền |
| Service A gọi Payment Service bằng workload token | Bị giới hạn đúng scope, action và resource |
| Thiếu thuộc tính policy/PDP tạm lỗi | Không tự cho phép |
| Membership hoặc quyền vừa bị thu hồi | Hành vi theo chính sách nhất quán/TTL đã công bố |
| Hai thao tác đồng thời đổi trạng thái | Không vượt qua điều kiện giao dịch/invariant |
| Event/job xử lý chậm | Tuân theo cơ chế ủy quyền ở thời điểm thực hiện |
| Cache quyền sai tenant/actor | Không chia sẻ quyết định giữa những principal không tương đương |

### Kiểm thử không chỉ qua HTTP

Unit test policy với tập actor-resource-action; integration test qua repository; test gọi trực tiếp application service; test từng entry point như job, consumer và gRPC; kiểm thử song song để phát hiện race. Với property-based testing, có thể khẳng định các bất biến như "không có actor tenant A đọc được dữ liệu tenant B" cho nhiều tổ hợp đầu vào.

Đặc biệt với dữ liệu phân trang và export, cần kiểm thử đủ trường hợp count/sort/filter để chắc rằng điều kiện quyền được áp **trước khi dữ liệu rời service**.

## 17. Sai lầm thiết kế thường gặp

1. **Chỉ kiểm tra quyền ở frontend:** người dùng vẫn gọi trực tiếp API.
2. **Chỉ dựa vào Gateway:** các lối vào khác hoặc cuộc gọi nội bộ có thể bỏ qua.
3. **Tin rằng JWT hợp lệ nghĩa là có quyền trên mọi record:** dễ dẫn đến BOLA.
4. **Dùng UUID khó đoán thay cho authorization:** ID có thể bị lộ qua URL, log hoặc nguồn khác.
5. **Tin tenantId/userId từ request:** tạo nguy cơ truy cập chéo tenant.
6. **Chỉ chặn controller, bỏ qua service method/job/consumer:** business action có lối đi khác.
7. **Cấp quyền quá rộng cho service account:** tạo confused deputy.
8. **Lấy danh sách rồi lọc trong UI hoặc sau pagination:** rò rỉ dữ liệu và trả kết quả sai.
9. **Không có field-level policy:** trả entity chứa thông tin không cần thiết.
10. **Policy dùng cache quá cũ:** quyền thu hồi không có hiệu lực theo yêu cầu.
11. **Kiểm tra quyền tách rời cập nhật trạng thái:** race condition làm lộ hoặc thay đổi dữ liệu.
12. **Dùng quyền "admin" không phạm vi:** khó kiểm toán và tăng blast radius.
13. **Policy engine lỗi thì cho phép:** fail open gây rủi ro nghiêm trọng.
14. **Không audit quyết định nhạy cảm:** khó điều tra lạm dụng quyền và thay đổi bất thường.

## 18. Quy trình thiết kế chính sách cho một API mới

Ví dụ yêu cầu: "Thêm API POST /orders/{id}/cancel."

**Bước 1 — Xác định owner.** Order Service sở hữu Order và hành vi hủy; các tác động lên Payment/Shipping phải được phối hợp qua hợp đồng của dịch vụ tương ứng.

**Bước 2 — Định nghĩa actor/action/resource.** Actor có thể là customer hoặc support; action là order.cancel; resource là Order được chỉ bởi id.

**Bước 3 — Liệt kê điều kiện allow.** Đúng tenant, có permission cancel, actor là người đặt/được ủy quyền, state cho phép, các yêu cầu phê duyệt đã thỏa.

**Bước 4 — Xác định dữ liệu cần lấy.** Thông tin tenant, customer, assignee, status, version từ Order Service; membership/delegation từ nguồn được tin cậy.

**Bước 5 — Đặt PEP và transaction.** Controller xác thực và chuẩn hóa request; application service load aggregate trong tenant, áp policy, gọi domain cancel trong transaction/locking phù hợp.

**Bước 6 — Xác định failure semantics.** Thiếu danh tính: 401; thiếu quyền: 403 hoặc 404 theo chính sách; state không hợp lệ: lỗi xung đột hợp đồng; source policy lỗi: từ chối an toàn.

**Bước 7 — Bảo vệ downstream.** Order Service gửi command được ràng buộc ngữ cảnh đến Payment/Shipping; các dịch vụ này xác thực workload và kiểm tra hành vi của riêng mình.

**Bước 8 — Audit và test.** Ghi trace/actor/action/decision an toàn; kiểm thử cross-tenant, owner khác, role thiếu, state thay đổi, gọi trực tiếp service, job và request đồng thời.

## 19. Bài tập ứng dụng

Giả sử một SaaS quản lý tài liệu có Document Service và Sharing Service:

- Alice là owner tài liệu D1 trong tenant T1.
- Bob cùng tenant nhưng chưa được chia sẻ D1.
- Carol thuộc tenant T2.
- Dan là admin của tenant T1 nhưng không có quyền đọc tài liệu nhạy cảm.
- Worker tạo thumbnail được phép đọc nội dung tối thiểu để tạo ảnh xem trước.

Hãy thiết kế policy cho document.read, document.share, document.delete và document.thumbnail.generate:

1. Actor cần mang những claim tối thiểu nào? Claim nào phải được xác minh tại nguồn?
2. Nơi nào lưu quan hệ owner, sharee, tenant và phân loại độ nhạy?
3. Service nào quyết định việc Bob được xem D1 sau khi Alice chia sẻ?
4. Vì sao Dan không mặc nhiên có quyền đọc mọi tài liệu?
5. Worker thumbnail được ủy quyền ra sao để không thể đọc tài liệu bất kỳ?
6. Nếu Alice thu hồi quyền Bob ngay sau khi Bob xếp hàng export thì xử lý thế nào?
7. Truy vấn list/count/search và export bảo đảm không lộ D1 cho Carol như thế nào?

Một thiết kế tốt phải đưa ra được allow/deny có thể giải thích và áp dụng cùng chính sách cho HTTP, job, message và truy cập từ các service khác.

## 20. Checklist khi đưa lên production

- [ ] Đã xác định service sở hữu từng aggregate, API và command.
- [ ] Mọi đường vào service đều có authentication phù hợp với user/workload.
- [ ] JWT hoặc credential được xác minh issuer, audience, thời hạn và nguồn tin cậy.
- [ ] Quyền action không đồng nhất với quyền trên object cụ thể.
- [ ] Policy bao phủ tenant, owner, quan hệ, vai trò, thuộc tính và trạng thái nghiệp vụ.
- [ ] Truy vấn detail, list, count, export, bulk và field projection đều bị giới hạn quyền.
- [ ] Command kiểm tra quyền và invariant trong một ranh giới giao dịch thích hợp.
- [ ] Service account/delegation dùng scope hẹp, hạn chế confused deputy.
- [ ] Không dùng request header hoặc ID do client tự khai làm bằng chứng phân quyền.
- [ ] Chính sách fail closed; có chiến lược cache, thu hồi và xử lý PDP lỗi.
- [ ] 401/403/404/409 không tiết lộ dữ liệu ngoài quyền.
- [ ] Có audit, metrics, test cross-tenant, role, object-level và race condition.
- [ ] Các job, consumer và luồng bất đồng bộ có danh tính/quyền rõ ràng.
- [ ] Thay đổi policy được version, review và phát hành có kiểm soát.

## 21. Ghi nhớ

**Dịch vụ nào sở hữu dữ liệu và hành vi thì dịch vụ đó phải giữ quyền quyết định cuối cùng về việc được đọc, thay đổi và kích hoạt hành vi liên quan.** Gateway giúp lọc yêu cầu và xác thực ban đầu; client giúp trải nghiệm người dùng; database giúp giới hạn truy cập. Nhưng không lớp nào thay thế được policy gắn với resource và quy tắc nghiệp vụ ở service sở hữu.

Mô hình tư duy cần nhớ:

~~~text
Một request có token hợp lệ
    KHÔNG suy ra
quyền trên một resource cụ thể.

Quyền truy cập resource
    KHÔNG suy ra
quyền thực hiện mọi hành vi với resource.

Được tin cậy khi gọi nội bộ
    KHÔNG suy ra
quyền hành động thay cho người khác.
~~~

Phân quyền đúng phải trả lời đủ **ai — làm gì — trên đối tượng nào — thuộc phạm vi nào — tại thời điểm nào**, rồi được thực thi nhất quán trên mọi đường vào của service.